// ASRComponent.h
// 语音识别组件（服务端录音版）
//
// UE4 只发 HTTP 信号，录音由服务端 Python 负责，彻底规避 UE4 音频捕获兼容问题。
//
// 用法:
//   1. 按住 V → StartRecording()  → POST /v1/asr/start
//   2. 松手  → StopAndRecognize() → POST /v1/asr/stop → OnSpeechRecognized

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Http.h"
#include "ASRComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnSpeechRecognized, const FString&, RecognizedText);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTTSOnRecordingStarted);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTTSOnRecordingStopped);

UCLASS(ClassGroup = (Custom), Blueprintable, meta = (BlueprintSpawnableComponent))
class LIPSYNC_API UASRComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UASRComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ASR|Server")
    FString ApiBaseUrl = TEXT("http://localhost:18080");

    /** 开始录音（通知服务端开始录音） */
    UFUNCTION(BlueprintCallable, Category = "ASR")
    void StartRecording();

    /** 停止录音并获取识别结果 */
    UFUNCTION(BlueprintCallable, Category = "ASR")
    void StopAndRecognize();

    UFUNCTION(BlueprintPure, Category = "ASR")
    bool IsRecording() const { return bIsRecording; }

    UPROPERTY(BlueprintAssignable, Category = "ASR|Events")
    FOnSpeechRecognized OnSpeechRecognized;

    UPROPERTY(BlueprintAssignable, Category = "ASR|Events")
    FTTSOnRecordingStarted OnRecordingStarted;

    UPROPERTY(BlueprintAssignable, Category = "ASR|Events")
    FTTSOnRecordingStopped OnRecordingStopped;

private:
    void PostSimple(const FString& Endpoint);
    void OnStopResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess);

    bool bIsRecording = false;
};
