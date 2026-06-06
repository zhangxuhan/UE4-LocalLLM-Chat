---@type ACharacter
local M = UnLua.Class()

-- ==================== 初始化 ====================

function M:ReceiveBeginPlay()
    -- 按模块路径加载类，避免插件类未注册到全局表的问题
    local ASRClass = UE.UClass.Load("/Script/LipSync.ASRComponent")
    local LLMClass = UE.UClass.Load("/Script/ProjectChat.LLMChatComponent")
    local TTSClass = UE.UClass.Load("/Script/LipSync.TTSLipSyncComponent")

    self.ASRComp = ASRClass and self:GetComponentByClass(ASRClass) or nil
    self.LLMComp = LLMClass and self:GetComponentByClass(LLMClass) or nil
    self.TTSComp = TTSClass and self:GetComponentByClass(TTSClass) or nil

    print("[Voice] ASR="  .. tostring(self.ASRComp))
    print("[Voice] LLM="  .. tostring(self.LLMComp))
    print("[Voice] TTS="  .. tostring(self.TTSComp))

    if not self.ASRComp or not self.LLMComp or not self.TTSComp then
        print("[Voice] 错误: 组件未找到，请确认 NPC 上已添加三个组件")
        return
    end

    -- 缓存头部网格（CharacterMesh0 含所有 MorphTarget）
    local meshClass = UE.UClass.Load("/Script/Engine.SkeletalMeshComponent")
    local meshComps = self:K2_GetComponentsByClass(meshClass)
    for i = 1, meshComps:Num() do
        local m = meshComps:Get(i)
        if m:GetName() == "CharacterMesh0" then
            self.HeadMesh = m
            break
        end
    end
    print("[Voice] HeadMesh=" .. tostring(self.HeadMesh))

    -- 串联事件：ASR → LLM → TTS
    self.ASRComp.OnSpeechRecognized:Add(self, self.OnSpeechRecognized)
    self.ASRComp.OnRecordingStarted:Add(self, self.OnRecordingStarted)
    self.ASRComp.OnRecordingStopped:Add(self, self.OnRecordingStopped)
    self.LLMComp.OnResponseReceived:Add(self, self.OnLLMResponse)
    self.LLMComp.OnErrorOccurred:Add(self, self.OnLLMError)
    self.TTSComp.OnSpeakStarted:Add(self, self.OnSpeakStarted)
    self.TTSComp.OnSpeakFinished:Add(self, self.OnSpeakFinished)

    -- 播放待机动画
    -- 使用专为该动漫角色骨骼制作的待机动画，头部骨骼位置正确，头发不会悬空
    local bodyIdle = UE.UAnimationAsset.Load("/Game/AnimeCharacters/Animations/Locomotion/a_manM_idle")

    if self.HeadMesh and bodyIdle then
        self.HeadMesh:PlayAnimation(bodyIdle, true)
        print("[Voice] 身体待机动画已播放: " .. bodyIdle:GetName())
    else
        print("[Voice] 警告: 身体待机动画未找到")
    end


    self.bVKeyDown = false
    print("[Voice] 初始化完成，按住 V 开始说话")
end

-- ==================== Tick 轮询按键 ====================

-- UE.FKey("V") 无法正确设置 KeyName，通过反射直接赋字段
local VKey = UE.FKey()
VKey.KeyName = "V"

function M:ReceiveTick(DeltaTime)
    self._tick = (self._tick or 0) + 1
    if self._tick == 1 then
        print("[Voice] ReceiveTick 已启动")
    end

    if not self.ASRComp then return end

    local PC = self:GetController()
    if not PC then return end

    local isDown = PC:IsInputKeyDown(VKey)
    if isDown and not self.bVKeyDown then
        self.bVKeyDown = true
        self:OnVoiceKeyPressed()
    elseif not isDown and self.bVKeyDown then
        self.bVKeyDown = false
        self:OnVoiceKeyReleased()
    end

    -- 每帧把 TTSLipSyncComponent 计算好的口型权重应用到头部网格
    if self.HeadMesh and self.TTSComp then
        local ok = pcall(self.TTSComp.ApplyMorphsTo, self.TTSComp, self.HeadMesh)
        if not ok then
            self.TTSComp = nil  -- 引用已失效，清掉避免后续报错
        end
    end
end

-- ==================== 按键处理 ====================

function M:OnVoiceKeyPressed()
    if self.TTSComp:IsSpeaking() then return end
    self.ASRComp:StartRecording()
end

function M:OnVoiceKeyReleased()
    self.ASRComp:StopAndRecognize()
end

-- ==================== 事件回调 ====================

function M:OnRecordingStarted()
    print("[Voice] 录音中...")
end

function M:OnRecordingStopped()
    print("[Voice] 识别中，请稍候...")
end

function M:OnSpeechRecognized(Text)
    print("[Voice] 识别结果: " .. Text)
    self.LLMComp:SendMessage(Text)
end

function M:OnLLMResponse(ResponseText)
    print("[Voice] NPC回复: " .. ResponseText)
    self.TTSComp:Speak(ResponseText)
end

function M:OnLLMError(ErrorMsg)
    print("[Voice] LLM错误: " .. ErrorMsg)
end

function M:OnSpeakStarted()
    print("[Voice] 开始播音 —— 打印所有网格的 MorphTarget")

    local meshClass = UE.UClass.Load("/Script/Engine.SkeletalMeshComponent")
    local meshComps = self:K2_GetComponentsByClass(meshClass)

    for i = 1, meshComps:Num() do
        local mesh = meshComps:Get(i)
        local skMesh = mesh.SkeletalMesh
        local assetName = skMesh and skMesh:GetName() or "nil"
        print(string.format("[Voice] --- 组件[%s] 资产=%s ---", mesh:GetName(), assetName))

        if skMesh then
            local morphList = skMesh.MorphTargets
            if morphList and morphList:Num() > 0 then
                for j = 1, morphList:Num() do
                    local mt = morphList:Get(j)
                    if mt then
                        print("  MorphTarget: " .. mt:GetName())
                    end
                end
            else
                print("  （无 MorphTarget）")
            end
        end
    end
end

function M:OnSpeakFinished()
    print("[Voice] 播音结束")
    -- 口型归零
    if self.HeadMesh then
        local morphs = {"Mouth_Wide","Mouth_Narrow","Mouth_Grimace","Mouth_Smile"}
        for _, name in ipairs(morphs) do
            self.HeadMesh:SetMorphTarget(name, 0.0, true)
        end
    end
end

return M
