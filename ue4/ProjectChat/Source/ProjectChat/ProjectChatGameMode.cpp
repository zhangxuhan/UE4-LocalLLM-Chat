// Copyright Epic Games, Inc. All Rights Reserved.

#include "ProjectChatGameMode.h"
#include "ProjectChatCharacter.h"
#include "UObject/ConstructorHelpers.h"
#include "Http.h"
#include "Json.h"
#include "JsonUtilities.h"

AProjectChatGameMode::AProjectChatGameMode()
{
	static ConstructorHelpers::FClassFinder<APawn> PlayerPawnBPClass(TEXT("/Game/ThirdPersonCPP/Blueprints/ThirdPersonCharacter"));
	if (PlayerPawnBPClass.Class != NULL)
	{
		DefaultPawnClass = PlayerPawnBPClass.Class;
	}

	LastChatReply = TEXT("");
	bChatReplyReady = false;
}

FString AProjectChatGameMode::GetModuleName_Implementation() const
{
	return TEXT("ProjectChat.ProjectChatGameMode");
}

void AProjectChatGameMode::SendChatMessage(const FString& SessionId, const FString& UserMessage, const FString& SystemPrompt)
{
	bChatReplyReady = false;
	LastChatReply = TEXT("");

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();

	FString URL = FString::Printf(TEXT("http://localhost:18080/v1/chat/session?session_id=%s"), *SessionId);
	Request->SetURL(URL);
	Request->SetVerb("POST");
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));

	TSharedPtr<FJsonObject> BodyJson = MakeShareable(new FJsonObject);

	TArray<TSharedPtr<FJsonValue>> Messages;
	TSharedPtr<FJsonObject> MsgObj = MakeShareable(new FJsonObject);
	MsgObj->SetStringField(TEXT("role"), TEXT("user"));
	MsgObj->SetStringField(TEXT("content"), UserMessage);
	Messages.Add(MakeShareable(new FJsonValueObject(MsgObj)));

	BodyJson->SetArrayField(TEXT("messages"), Messages);
	BodyJson->SetNumberField(TEXT("max_tokens"), 256);

	// 定制 SystemPrompt
	if (!SystemPrompt.IsEmpty())
	{
		BodyJson->SetStringField(TEXT("system_prompt"), SystemPrompt);
	}

	FString Body;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
	FJsonSerializer::Serialize(BodyJson.ToSharedRef(), Writer);

	Request->SetContentAsString(Body);

	// 异步回调：HTTP 完成后写入属性，Lua 的 NativeTick 检测到 bChatReplyReady 后取走
	Request->OnProcessRequestComplete().BindLambda([this](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess)
	{
		FString Reply;
		if (bSuccess && Resp.IsValid())
		{
			TSharedPtr<FJsonObject> JsonObj;
			TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Resp->GetContentAsString());
			if (FJsonSerializer::Deserialize(Reader, JsonObj) && JsonObj.IsValid())
			{
				Reply = JsonObj->GetStringField(TEXT("content"));
			}
		}

		LastChatReply = Reply;
		bChatReplyReady = true;
	});

	Request->ProcessRequest();
}
