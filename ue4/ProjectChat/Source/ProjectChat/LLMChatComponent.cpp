/**
 * LLMChatComponent.cpp
 * UE4 本地 LLM 对话组件实现
 */

#include "LLMChatComponent.h"

ULLMChatComponent::ULLMChatComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
    bStreamDone = false;
}

void ULLMChatComponent::BeginPlay()
{
    Super::BeginPlay();

    // 自动生成 SessionId（用 Actor 名 + 组件名，保证唯一）
    if (SessionId.IsEmpty() && GetOwner())
    {
        SessionId = FString::Printf(TEXT("%s_%s"),
            *GetOwner()->GetName(),
            *GetName());
    }
}

FString ULLMChatComponent::GetModuleName_Implementation() const
{
    return TEXT("ProjectChat.LLMChatComponent");
}

FString ULLMChatComponent::BuildRequestBody(const FString& PlayerMessage, bool bIsStreaming)
{
    TSharedPtr<FJsonObject> RootObj = MakeShareable(new FJsonObject);

    // 构建 messages 数组
    TArray<TSharedPtr<FJsonValue>> Messages;

    // System prompt
    if (!SystemPrompt.IsEmpty())
    {
        TSharedPtr<FJsonObject> SysMsg = MakeShareable(new FJsonObject);
        SysMsg->SetStringField("role", "system");
        SysMsg->SetStringField("content", SystemPrompt);
        Messages.Add(MakeShareable(new FJsonValueObject(SysMsg)));
    }

    // User message
    TSharedPtr<FJsonObject> UserMsg = MakeShareable(new FJsonObject);
    UserMsg->SetStringField("role", "user");
    UserMsg->SetStringField("content", PlayerMessage);
    Messages.Add(MakeShareable(new FJsonValueObject(UserMsg)));

    RootObj->SetArrayField("messages", Messages);
    RootObj->SetNumberField("temperature", Temperature);
    RootObj->SetNumberField("max_tokens", MaxTokens);
    RootObj->SetBoolField("stream", bIsStreaming);

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(RootObj.ToSharedRef(), Writer);
    return OutputString;
}

void ULLMChatComponent::SendMessage(const FString& PlayerMessage)
{
    if (!GetOwner() || !GetOwner()->GetWorld())
    {
        HandleError(TEXT("Component未正确初始化"));
        return;
    }

    FString URL = FString::Printf(TEXT("%s/v1/chat/session?session_id=%s"),
        *ApiBase, *SessionId);

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(URL);
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetContentAsString(BuildRequestBody(PlayerMessage, false));
    Request->SetTimeout(TimeoutSeconds);

    // 绑定回调（Lambda 捕获 this 指针）
    Request->OnProcessRequestComplete().BindLambda(
        [this](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bWasSuccessful)
        {
            HandleNonStreamResponse(Req, Resp, bWasSuccessful);
        });

    if (!Request->ProcessRequest())
    {
        HandleError(TEXT("HTTP请求发送失败"));
    }
}

void ULLMChatComponent::SendMessageStream(const FString& PlayerMessage)
{
    if (!GetOwner() || !GetOwner()->GetWorld())
    {
        HandleError(TEXT("Component未正确初始化"));
        return;
    }

    FString URL = FString::Printf(TEXT("%s/v1/chat/session/stream?session_id=%s"),
        *ApiBase, *SessionId);

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(URL);
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetContentAsString(BuildRequestBody(PlayerMessage, true));
    Request->SetTimeout(TimeoutSeconds);

    // 重置流式状态
    StreamBuffer.Empty();
    bStreamDone = false;
    FullStreamResponse.Empty();

    // SSE 需要监听进度事件（逐包回调）
    Request->OnRequestProgress().BindLambda(
        [this](FHttpRequestPtr Req, int32 BytesSent, int32 BytesReceived)
        {
            if (bStreamDone) return;
            HandleStreamResponse(Req, Req->GetResponse(), true);
        });

    Request->OnProcessRequestComplete().BindLambda(
        [this](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bWasSuccessful)
        {
            // 确保最后的数据包被处理
            if (!bStreamDone)
            {
                HandleStreamResponse(Req, Resp, bWasSuccessful);
                if (!bStreamDone)
                {
                    // 强制完成
                    AsyncTask(ENamedThreads::GameThread, [this]()
                    {
                        OnStreamComplete.Broadcast();
                    });
                    bStreamDone = true;
                }
            }
        });

    if (!Request->ProcessRequest())
    {
        HandleError(TEXT("流式请求发送失败"));
    }
}

void ULLMChatComponent::ResetConversation()
{
    FString URL = FString::Printf(TEXT("%s/v1/chat/reset?session_id=%s"),
        *ApiBase, *SessionId);

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(URL);
    Request->SetVerb(TEXT("POST"));
    Request->OnProcessRequestComplete().BindLambda(
        [](FHttpRequestPtr, FHttpResponsePtr Resp, bool bSuccess)
        {
            if (bSuccess && Resp.IsValid())
            {
                UE_LOG(LogTemp, Log, TEXT("[LLMChat] 会话已重置"));
            }
        });
    Request->ProcessRequest();
}

void ULLMChatComponent::CheckServiceHealth()
{
    FString URL = ApiBase + TEXT("/v1/health");

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(URL);
    Request->SetVerb(TEXT("GET"));
    Request->SetTimeout(5.0f);
    Request->OnProcessRequestComplete().BindLambda(
        [this](FHttpRequestPtr, FHttpResponsePtr Resp, bool bWasSuccessful)
        {
            FString Result;
            if (bWasSuccessful && Resp.IsValid())
            {
                Result = Resp->GetContentAsString();
            }
            else
            {
                Result = TEXT("{\"error\":\"无法连接服务\"}");
            }
            AsyncTask(ENamedThreads::GameThread, [this, Result]()
            {
                OnHealthCheckResult.Broadcast(Result);
            });
        });
    Request->ProcessRequest();
}

void ULLMChatComponent::HandleNonStreamResponse(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    bool bWasSuccessful)
{
    if (!bWasSuccessful || !Response.IsValid())
    {
        HandleError(TEXT("网络请求失败，请检查LLM服务是否启动"));
        return;
    }

    int32 StatusCode = Response->GetResponseCode();
    if (StatusCode != 200)
    {
        FString Body = Response->GetContentAsString();
        HandleError(FString::Printf(TEXT("HTTP错误 %d: %s"), StatusCode, *Body));
        return;
    }

    FString Body = Response->GetContentAsString();

    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Body);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
    {
        HandleError(FString::Printf(TEXT("JSON解析失败: %s"), *Body));
        return;
    }

    FString Content;
    if (JsonObj->TryGetStringField(TEXT("content"), Content))
    {
        // 成功拿到回复，切换到游戏线程广播
        AsyncTask(ENamedThreads::GameThread, [this, Content]()
        {
            OnResponseReceived.Broadcast(Content);
        });
    }
    else if (JsonObj->HasField(TEXT("error")))
    {
        FString Err = JsonObj->GetStringField(TEXT("error"));
        HandleError(Err);
    }
    else
    {
        HandleError(TEXT("响应格式异常"));
    }
}

void ULLMChatComponent::HandleStreamResponse(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    bool bWasSuccessful)
{
    if (!bWasSuccessful || !Response.IsValid() || bStreamDone)
        return;

    // 获取当前已收到的所有数据
    const TArray<uint8>& Raw = Response->GetContent();
    FString NewData = FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(Raw.GetData())));

    // 增量解析：只处理新增部分
    StreamBuffer += NewData;

    // 按行分割 SSE 数据
    TArray<FString> Lines;
    StreamBuffer.ParseIntoArrayLines(Lines);

    // 保留最后一行（可能不完整）
    if (Lines.Num() > 0 && !StreamBuffer.EndsWith(TEXT("\n")))
    {
        StreamBuffer = Lines.Last();
        Lines.RemoveAt(Lines.Num() - 1);
    }
    else
    {
        StreamBuffer.Empty();
    }

    for (const FString& Line : Lines)
    {
        ParseSSEChunk(Line);
        if (bStreamDone) return;
    }
}

void ULLMChatComponent::ParseSSEChunk(const FString& Chunk)
{
    if (!Chunk.StartsWith(TEXT("data: ")))
        return;

    FString JsonStr = Chunk.RightChop(6).TrimStartAndEnd();
    if (JsonStr.IsEmpty() || JsonStr == TEXT(""))
        return;

    TSharedPtr<FJsonObject> DataObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonStr);

    if (!FJsonSerializer::Deserialize(Reader, DataObj) || !DataObj.IsValid())
        return;

    // 错误处理
    if (DataObj->HasField(TEXT("error")))
    {
        FString Err = DataObj->GetStringField(TEXT("error"));
        AsyncTask(ENamedThreads::GameThread, [this, Err]()
        {
            HandleError(Err);
        });
        bStreamDone = true;
        return;
    }

    // 完成信号
    bool bDone = false;
    DataObj->TryGetBoolField(TEXT("done"), bDone);
    if (bDone)
    {
        bStreamDone = true;
        AsyncTask(ENamedThreads::GameThread, [this]()
        {
            OnStreamComplete.Broadcast();
        });
        return;
    }

    // 提取 token
    FString Token;
    if (DataObj->TryGetStringField(TEXT("content"), Token) && !Token.IsEmpty())
    {
        FullStreamResponse += Token;
        AsyncTask(ENamedThreads::GameThread, [this, Token]()
        {
            OnTokenReceived.Broadcast(Token);
        });
    }
}

void ULLMChatComponent::HandleError(const FString& ErrorMsg)
{
    UE_LOG(LogTemp, Error, TEXT("[LLMChat] 错误: %s"), *ErrorMsg);
    AsyncTask(ENamedThreads::GameThread, [this, ErrorMsg]()
    {
        OnErrorOccurred.Broadcast(ErrorMsg);
    });
}
