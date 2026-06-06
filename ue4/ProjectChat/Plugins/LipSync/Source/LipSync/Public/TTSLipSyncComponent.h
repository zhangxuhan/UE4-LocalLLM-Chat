// TTSLipSyncComponent.h
// 离线 TTS + 口型同步组件
//
// 用法（Blueprint / C++）:
//   1. NPC Actor 上 AddComponent<TTSLipSyncComponent>
//   2. 设 ApiBaseUrl = "http://localhost:18080"
//   3. 调用 Speak("你好") → 自动请求 /v1/tts → 播放音频并驱动 MorphTarget

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Http.h"
#include "TTSLipSyncComponent.generated.h"

// ---- 口型关键帧数据结构 ----

USTRUCT(BlueprintType)
struct LIPSYNC_API FPhonemeKeyframe
{
    GENERATED_BODY()

    /** 时间戳（秒） */
    UPROPERTY(BlueprintReadOnly)
    float Time = 0.f;

    /** MorphTarget 名称 → 权重（0~1） */
    UPROPERTY(BlueprintReadOnly)
    TMap<FString, float> MorphWeights;
};

// ---- 事件委托 ----

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTTSOnSpeakStarted);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTTSOnSpeakFinished);

// ---- 组件 ----

UCLASS(ClassGroup = (Custom), Blueprintable, meta = (BlueprintSpawnableComponent))
class LIPSYNC_API UTTSLipSyncComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UTTSLipSyncComponent();

    // ==================== 配置属性 ====================

    /** TTS 服务地址（你的 FastAPI 地址） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "LipSync|Server")
    FString ApiBaseUrl = TEXT("http://localhost:18080");

    /** TTS 合成音色 */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "LipSync|Server")
    FString Voice = TEXT("zh-CN-XiaoxiaoNeural");

    /** 口型驱动目标（如果有 SkeletalMesh 则自动从 Owner 查找） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "LipSync|Target")
    TWeakObjectPtr<class USkeletalMeshComponent> TargetMesh;

    /** 口型过渡平滑时间（秒） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "LipSync|Animation")
    float MorphSmoothSpeed = 8.f;


    // ==================== Blueprint 接口 ====================

    /** 说话！文字 → TTS 请求 → 播放音频 + 驱动口型 */
    UFUNCTION(BlueprintCallable, Category = "LipSync")
    void Speak(const FString& Text);

    /** 说话（指定音色） */
    UFUNCTION(BlueprintCallable, Category = "LipSync")
    void SpeakWithVoice(const FString& Text, const FString& InVoice);

    /** 立即停止说话，重置口型 */
    UFUNCTION(BlueprintCallable, Category = "LipSync")
    void StopSpeaking();

    /** 是否正在说话 */
    UFUNCTION(BlueprintPure, Category = "LipSync")
    bool IsSpeaking() const { return bIsSpeaking; }

    // ==================== 事件 ====================

    UPROPERTY(BlueprintAssignable, Category = "LipSync|Events")
    FTTSOnSpeakStarted OnSpeakStarted;

    UPROPERTY(BlueprintAssignable, Category = "LipSync|Events")
    FTTSOnSpeakFinished OnSpeakFinished;

    /** 当前插值后的口型权重，Lua 每帧通过 ApplyMorphsTo 应用到网格 */
    UPROPERTY(BlueprintReadOnly, Category="LipSync")
    TMap<FName, float> CurrentMorphWeights;

    /** 将当前口型权重应用到指定网格（在 Lua ReceiveTick 里调用，绕过 AnimBP 覆盖） */
    UFUNCTION(BlueprintCallable, Category="LipSync")
    void ApplyMorphsTo(USkeletalMeshComponent* Mesh);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

private:
    // ---- 网络请求 ----
    void SendTTSRequest(const FString& Text);
    void OnTTSResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess);

    // ---- 播放控制 ----
    void StartPlayback(const TArray<uint8>& WavBytes,
        const TArray<FPhonemeKeyframe>& Keyframes,
        float TotalDurationMs);

    // ---- 口型驱动 ----
    void UpdateMorphTargets(float CurrentTime);
    void ResetMorphTargets();
    int32 FindKeyframeIndex(float Time) const;

    // ---- 状态 ----
    UPROPERTY()
    class UAudioComponent* AudioComp = nullptr;

    TArray<FPhonemeKeyframe> PhonemeTimeline;
    TMap<FName, float>        TargetMorphWeights;

    float PlaybackTime = 0.f;
    float TotalDuration = 0.f;
    bool  bIsSpeaking = false;
    bool  bAudioEnded = false;
    bool  bAudioStarted = false;  // 至少一帧后才检查 IsPlaying，避免首帧误判
};
