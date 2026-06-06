// TTSLipSyncComponent.cpp
// 离线 TTS + 口型同步实现

#include "TTSLipSyncComponent.h"
#include "Json.h"
#include "JsonUtilities/Public/JsonObjectConverter.h"
#include "Misc/Base64.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundWaveProcedural.h"
#include "AudioDevice.h"

// ==================== 生命周期 ====================

UTTSLipSyncComponent::UTTSLipSyncComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = false;
    // PostUpdateWork 确保在 AnimBP 执行完之后再写 MorphTarget，防止被 AnimBP 每帧覆盖回 0
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}

void UTTSLipSyncComponent::BeginPlay()
{
    Super::BeginPlay();

    // 自动从 Owner 找 SkeletalMeshComponent
    if (!TargetMesh.IsValid() && GetOwner())
    {
        TargetMesh = GetOwner()->FindComponentByClass<USkeletalMeshComponent>();
    }

    // 创建 AudioComponent 并挂到 Owner 上
    AudioComp = NewObject<UAudioComponent>(GetOwner());
    AudioComp->RegisterComponent();
    AudioComp->bAutoActivate = false;
    AudioComp->SetVolumeMultiplier(1.0f);

    if (USceneComponent* Root = GetOwner()->GetRootComponent())
    {
        AudioComp->AttachToComponent(Root,
            FAttachmentTransformRules::SnapToTargetIncludingScale);
    }
}

void UTTSLipSyncComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    StopSpeaking();
    Super::EndPlay(Reason);
}

// ==================== Blueprint API ====================

void UTTSLipSyncComponent::Speak(const FString& Text)
{
    if (Text.IsEmpty()) return;

    // 先停止当前播放
    if (bIsSpeaking) StopSpeaking();

    SendTTSRequest(Text);
}

void UTTSLipSyncComponent::SpeakWithVoice(const FString& Text, const FString& InVoice)
{
    Voice = InVoice;
    Speak(Text);
}

void UTTSLipSyncComponent::StopSpeaking()
{
    if (AudioComp && AudioComp->IsPlaying())
    {
        AudioComp->Stop();
    }

    bIsSpeaking = false;
    bAudioEnded = false;
    SetComponentTickEnabled(false);
    ResetMorphTargets();

    OnSpeakFinished.Broadcast();
}

// ==================== HTTP 请求 ====================

void UTTSLipSyncComponent::SendTTSRequest(const FString& Text)
{
    // 构造 JSON 请求体
    TSharedPtr<FJsonObject> ReqObj = MakeShareable(new FJsonObject());
    ReqObj->SetStringField(TEXT("text"), Text);
    ReqObj->SetStringField(TEXT("voice"), Voice);

    FString Body;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
    FJsonSerializer::Serialize(ReqObj.ToSharedRef(), Writer);

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request =
        FHttpModule::Get().CreateRequest();
    Request->SetURL(ApiBaseUrl + TEXT("/v1/tts"));
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetContentAsString(Body);
    Request->SetTimeout(30.f);
    Request->OnProcessRequestComplete().BindUObject(
        this, &UTTSLipSyncComponent::OnTTSResponse);
    Request->ProcessRequest();
}

void UTTSLipSyncComponent::OnTTSResponse(
    FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess)
{
    if (!bSuccess || !Resp.IsValid() || Resp->GetResponseCode() != 200)
    {
        UE_LOG(LogTemp, Error, TEXT("[LipSync] TTS 请求失败"));
        return;
    }

    // 解析 JSON
    TSharedPtr<FJsonObject> Json;
    TSharedRef<TJsonReader<>> Reader =
        TJsonReaderFactory<>::Create(Resp->GetContentAsString());
    if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("[LipSync] JSON 解析失败"));
        return;
    }

    // 解码 WAV 数据
    FString WavBase64;
    TArray<uint8> WavBytes;
    if (Json->TryGetStringField(TEXT("wav_base64"), WavBase64))
    {
        FBase64::Decode(WavBase64, WavBytes);
    }
    else
    {
        UE_LOG(LogTemp, Error, TEXT("[LipSync] 响应中缺少 wav_base64"));
        return;
    }

    // 解析总时长
    double DurationMsVal = 0.0;
    Json->TryGetNumberField(TEXT("duration_ms"), DurationMsVal);
    float DurationMs = (float)DurationMsVal;

    // 解析音素时间线
    TArray<FPhonemeKeyframe> Keyframes;
    const TArray<TSharedPtr<FJsonValue>>* PhonemeArr = nullptr;
    if (Json->TryGetArrayField(TEXT("phonemes"), PhonemeArr))
    {
        for (const auto& Val : *PhonemeArr)
        {
            const TSharedPtr<FJsonObject>* KfObj = nullptr;
            if (!Val->TryGetObject(KfObj)) continue;

            FPhonemeKeyframe Kf;
            double TimeVal = 0.0;
            (*KfObj)->TryGetNumberField(TEXT("time"), TimeVal);
            Kf.Time = (float)TimeVal;

            const TSharedPtr<FJsonObject>* MorphObj = nullptr;
            if ((*KfObj)->TryGetObjectField(TEXT("morph"), MorphObj))
            {
                for (const auto& Pair : (*MorphObj)->Values)
                {
                    double W = 0.0;
                    Pair.Value->TryGetNumber(W);
                    Kf.MorphWeights.Add(Pair.Key, (float)W);
                }
            }
            Keyframes.Add(Kf);
        }
    }

    // 切回 GameThread 开始播放
    AsyncTask(ENamedThreads::GameThread, [this, WavBytes, Keyframes, DurationMs]()
    {
        StartPlayback(WavBytes, Keyframes, DurationMs);
    });
}

// ==================== 播放控制 ====================

void UTTSLipSyncComponent::StartPlayback(
    const TArray<uint8>& WavBytes,
    const TArray<FPhonemeKeyframe>& Keyframes,
    float TotalDurationMs)
{
    PhonemeTimeline = Keyframes;
    TotalDuration = TotalDurationMs / 1000.f;  // ms → 秒
    PlaybackTime = 0.f;
    bIsSpeaking = true;
    bAudioEnded = false;
    bAudioStarted = false;
    CurrentMorphWeights.Empty();
    TargetMorphWeights.Empty();

    // 创建 SoundWaveProcedural 并填入 PCM（跳过 44-byte WAV header）
    USoundWaveProcedural* SoundWave = NewObject<USoundWaveProcedural>();
    SoundWave->SetSampleRate(24000);
    SoundWave->NumChannels = 1;
    SoundWave->Duration = INDEFINITELY_LOOPING_DURATION;
    SoundWave->SoundGroup = SOUNDGROUP_Voice;
    SoundWave->bLooping = false;

    if (WavBytes.Num() > 44)
    {
        SoundWave->QueueAudio(
            WavBytes.GetData() + 44,
            WavBytes.Num() - 44);
    }

    if (IsValid(AudioComp))
    {
        AudioComp->SetSound(SoundWave);
        AudioComp->Play();
    }

    // 开启 Tick 驱动口型
    SetComponentTickEnabled(true);
    OnSpeakStarted.Broadcast();
}

// ==================== 口型驱动 (Tick) ====================

void UTTSLipSyncComponent::TickComponent(
    float DeltaTime, ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

    if (!bIsSpeaking) return;

    // 用 DeltaTime 累积推算播放进度
    PlaybackTime += DeltaTime;

    // 音频播放结束检测（首帧跳过 IsPlaying 检查，避免音频系统异步导致误判）
    if (!bAudioEnded)
    {
        if (!bAudioStarted)
        {
            bAudioStarted = true;  // 下一帧起才检查
        }
        else
        {
            bool bAudioStopped = IsValid(AudioComp) && !AudioComp->IsPlaying();
            bool bTimeExceeded = PlaybackTime >= TotalDuration;
            if (bAudioStopped || bTimeExceeded)
                bAudioEnded = true;
        }
    }

    // 更新口型
    if (PhonemeTimeline.Num() >= 2 && PlaybackTime <= TotalDuration)
    {
        UpdateMorphTargets(PlaybackTime);
    }

    // 音频播完 → 结束
    if (bAudioEnded)
    {
        bIsSpeaking = false;
        SetComponentTickEnabled(false);
        ResetMorphTargets();
        OnSpeakFinished.Broadcast();
    }
}

void UTTSLipSyncComponent::UpdateMorphTargets(float CurrentTime)
{
    if (!TargetMesh.IsValid() || PhonemeTimeline.Num() < 2) return;

    int32 Idx = FindKeyframeIndex(CurrentTime);
    const FPhonemeKeyframe& A = PhonemeTimeline[Idx];
    const FPhonemeKeyframe& B = PhonemeTimeline[Idx + 1];

    float Duration = B.Time - A.Time;
    float Alpha = Duration > 0.f ?
        FMath::Clamp((CurrentTime - A.Time) / Duration, 0.f, 1.f) : 1.f;

    float DeltaTime = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.016f;
    float SmoothFactor = FMath::Clamp(DeltaTime * MorphSmoothSpeed, 0.f, 1.f);

    TSet<FString> AllKeys;
    for (const auto& Pair : A.MorphWeights) AllKeys.Add(Pair.Key);
    for (const auto& Pair : B.MorphWeights) AllKeys.Add(Pair.Key);

    for (const FString& Key : AllKeys)
    {
        float WA = A.MorphWeights.Contains(Key) ? A.MorphWeights[Key] : 0.f;
        float WB = B.MorphWeights.Contains(Key) ? B.MorphWeights[Key] : 0.f;
        TargetMorphWeights.FindOrAdd(FName(*Key)) = FMath::Lerp(WA, WB, Alpha);
    }

    // 只更新 CurrentMorphWeights，不直接 SetMorphTarget
    // 由 Lua 的 ReceiveTick 调用 ApplyMorphsTo 来实际写入，绕过 AnimBP 覆盖
    if (DeltaTime > 0.f)
    {
        for (auto& Pair : TargetMorphWeights)
        {
            float Current = CurrentMorphWeights.FindRef(Pair.Key);
            float Smoothed = FMath::Lerp(Current, Pair.Value, SmoothFactor);
            CurrentMorphWeights.Add(Pair.Key, Smoothed);
        }
    }
}

int32 UTTSLipSyncComponent::FindKeyframeIndex(float Time) const
{
    int32 Lo = 0, Hi = PhonemeTimeline.Num() - 2;
    while (Lo < Hi)
    {
        int32 Mid = (Lo + Hi + 1) / 2;
        if (PhonemeTimeline[Mid].Time <= Time)
            Lo = Mid;
        else
            Hi = Mid - 1;
    }
    return Lo;
}

void UTTSLipSyncComponent::ResetMorphTargets()
{
    CurrentMorphWeights.Empty();
    TargetMorphWeights.Empty();
    // 实际清零由 Lua 在 OnSpeakFinished 里调用 ApplyMorphsTo 完成
}

void UTTSLipSyncComponent::ApplyMorphsTo(USkeletalMeshComponent* Mesh)
{
    if (!Mesh) return;
    for (auto& Pair : CurrentMorphWeights)
    {
        Mesh->SetMorphTarget(Pair.Key, Pair.Value, false);
    }
}
