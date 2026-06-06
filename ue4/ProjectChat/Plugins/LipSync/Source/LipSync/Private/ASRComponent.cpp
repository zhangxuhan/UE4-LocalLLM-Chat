// ASRComponent.cpp
// 服务端录音版：UE4 只发 start/stop 信号，录音和识别全在 Python 端

#include "ASRComponent.h"
#include "Json.h"

UASRComponent::UASRComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UASRComponent::StartRecording()
{
    if (bIsRecording) return;
    bIsRecording = true;
    PostSimple(TEXT("/v1/asr/start"));
    OnRecordingStarted.Broadcast();
    UE_LOG(LogTemp, Log, TEXT("[ASR] 发送开始录音信号"));
}

void UASRComponent::StopAndRecognize()
{
    if (!bIsRecording) return;
    bIsRecording = false;
    OnRecordingStopped.Broadcast();

    // POST /v1/asr/stop，响应里包含识别文字
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request =
        FHttpModule::Get().CreateRequest();
    Request->SetURL(ApiBaseUrl + TEXT("/v1/asr/stop"));
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetTimeout(60.f);
    Request->OnProcessRequestComplete().BindUObject(this, &UASRComponent::OnStopResponse);
    Request->ProcessRequest();

    UE_LOG(LogTemp, Log, TEXT("[ASR] 发送停止录音信号，等待识别结果..."));
}

void UASRComponent::PostSimple(const FString& Endpoint)
{
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req =
        FHttpModule::Get().CreateRequest();
    Req->SetURL(ApiBaseUrl + Endpoint);
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Req->SetTimeout(5.f);
    Req->ProcessRequest();
}

void UASRComponent::OnStopResponse(
    FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess)
{
    if (!bSuccess || !Resp.IsValid() || Resp->GetResponseCode() != 200)
    {
        UE_LOG(LogTemp, Error, TEXT("[ASR] 识别请求失败，HTTP %d"),
            Resp.IsValid() ? Resp->GetResponseCode() : 0);
        return;
    }

    TSharedPtr<FJsonObject> Json;
    TSharedRef<TJsonReader<>> Reader =
        TJsonReaderFactory<>::Create(Resp->GetContentAsString());
    if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid()) return;

    FString Text;
    if (Json->TryGetStringField(TEXT("text"), Text) && !Text.IsEmpty())
    {
        UE_LOG(LogTemp, Log, TEXT("[ASR] 识别结果: %s"), *Text);
        AsyncTask(ENamedThreads::GameThread,
            [this, Text]() { OnSpeechRecognized.Broadcast(Text); });
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("[ASR] 未识别到文字"));
    }
}
