/**
 * LLMChatComponent.h
 * ==================
 * UE4 组件封装 - 挂载到任意 Actor 即可使用
 * 
 * 功能：
 * - 封装 HTTP 请求细节，Blueprint 直接调用
 * - 支持非流式和流式两种模式
 * - 自动管理会话上下文（SessionId 自动取 Actor 名）
 * - 内置错误处理和超时管理
 * 
 * 用法：
 * 1. 将此组件添加到 NPC Actor 上
 * 2. 在蓝图中调用 SendMessage(PlayerMessage)
 * 3. 绑定 OnResponseReceived / OnTokenReceived / OnErrorOccurred 事件
 */

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Http.h"
#include "Json.h"
#include "JsonUtilities.h"
#include "UnLuaInterface.h"
#include "LLMChatComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnResponseReceived, const FString&, ResponseText);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnTokenReceived, const FString&, Token);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnStreamComplete);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnErrorOccurred, const FString&, ErrorMessage);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class PROJECTCHAT_API ULLMChatComponent : public UActorComponent, public IUnLuaInterface
{
    GENERATED_BODY()

public:
    ULLMChatComponent();

protected:
    virtual void BeginPlay() override;

    // ===== 可配置属性（在 Blueprint 细节面板设置）=====
public:
    /** LLM API 服务地址 */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat")
    FString ApiBase = TEXT("http://localhost:18080");

    /** 会话ID（留空则自动使用 Actor 名） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat")
    FString SessionId;

    /** 回复最大 Token 数（越小越快，适合游戏内快速回复） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat", meta = (ClampMin = "64", ClampMax = "4096"))
    int32 MaxTokens = 512;

    /** 温度（0.1=很严谨，1.0=很随机） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat", meta = (ClampMin = "0.0", ClampMax = "2.0"))
    float Temperature = 0.7f;

    /** 系统提示词（定义NPC性格/身份） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat", meta = (MultiLine = true))
    FString SystemPrompt = TEXT("你是一个游戏中的NPC，用简短自然的中文回答玩家问题，每次回复不超过100字。");

    /** 请求超时时间（秒） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AI Chat", meta = (ClampMin = "5", ClampMax = "300"))
    float TimeoutSeconds = 30.0f;

    // ===== Blueprint 可调用函数 =====

    /** 发送消息（非流式，简单快速） */
    UFUNCTION(BlueprintCallable, Category = "AI Chat", meta = (ToolTip = "发送消息，等待完整回复后触发OnResponseReceived"))
    void SendMessage(const FString& PlayerMessage);

    /** 发送消息（流式，逐字输出，适合对话UI逐字显示） */
    UFUNCTION(BlueprintCallable, Category = "AI Chat", meta = (ToolTip = "发送消息，每个token触发OnTokenReceived，结束后触发OnStreamComplete"))
    void SendMessageStream(const FString& PlayerMessage);

    /** 重置此NPC的对话历史 */
    UFUNCTION(BlueprintCallable, Category = "AI Chat")
    void ResetConversation();

    /** 检查服务是否在线 */
    UFUNCTION(BlueprintCallable, Category = "AI Chat")
    void CheckServiceHealth();

    // ===== IUnLuaInterface =====
    /** 返回对应的 Lua 模块路径（相对于 Content/Script） */
    virtual FString GetModuleName_Implementation() const override;

    // ===== Blueprint 可绑定事件 =====

    /** 收到完整回复时触发（非流式模式） */
    UPROPERTY(BlueprintAssignable, Category = "AI Chat")
    FOnResponseReceived OnResponseReceived;

    /** 收到一个token时触发（流式模式，用于逐字显示） */
    UPROPERTY(BlueprintAssignable, Category = "AI Chat")
    FOnTokenReceived OnTokenReceived;

    /** 流式对话完成时触发 */
    UPROPERTY(BlueprintAssignable, Category = "AI Chat")
    FOnStreamComplete OnStreamComplete;

    /** 发生错误时触发 */
    UPROPERTY(BlueprintAssignable, Category = "AI Chat")
    FOnErrorOccurred OnErrorOccurred;

    /** 服务健康检查完成时触发，返回JSON字符串 */
    UPROPERTY(BlueprintAssignable, Category = "AI Chat")
    FOnResponseReceived OnHealthCheckResult;

private:
    /** 构建完整的 JSON 请求体 */
    FString BuildRequestBody(const FString& PlayerMessage, bool bIsStreaming);

    /** 处理非流式 HTTP 响应 */
    void HandleNonStreamResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);

    /** 处理流式 HTTP 响应（逐包解析SSE） */
    void HandleStreamResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);

    /** 解析 SSE 数据行，提取 token */
    void ParseSSEChunk(const FString& Chunk);

    /** 统一的错误处理 */
    void HandleError(const FString& ErrorMsg);

    // 流式状态
    FString StreamBuffer;
    bool bStreamDone;
    FString FullStreamResponse;
};
