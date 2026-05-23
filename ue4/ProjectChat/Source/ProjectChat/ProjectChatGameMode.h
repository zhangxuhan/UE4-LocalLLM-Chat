// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "UnLuaInterface.h"
#include "ProjectChatGameMode.generated.h"

UCLASS(minimalapi)
class AProjectChatGameMode : public AGameModeBase, public IUnLuaInterface
{
	GENERATED_BODY()

public:
	AProjectChatGameMode();

	virtual FString GetModuleName_Implementation() const override;

	/** 异步发送聊天消息。Lua 调用后通过 bChatReplyReady + LastChatReply 取结果。
	 *  @param SystemPrompt  定制系统提示词（为空则使用服务端默认） */
	UFUNCTION(BlueprintCallable, Category = "AI Chat")
	void SendChatMessage(const FString& SessionId, const FString& UserMessage, const FString& SystemPrompt = TEXT(""));

	/** LLM 返回的回复文本 */
	UPROPERTY(BlueprintReadOnly, Category = "AI Chat")
	FString LastChatReply;

	/** true = 回复已就绪，可取用 LastChatReply */
	UPROPERTY(BlueprintReadOnly, Category = "AI Chat")
	bool bChatReplyReady;
};
