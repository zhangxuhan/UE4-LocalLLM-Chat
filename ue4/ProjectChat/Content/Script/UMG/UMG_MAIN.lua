---@type UMG_Main_C
local M = UnLua.Class()

local Screen = require "Tools.Screen"

local ChatHistory = {}

-- ============================================================
--  定制 SystemPrompt（在此修改 NPC 的对话风格）
-- ============================================================

local NPCSystemPrompt = [[
你是一个游戏中的NPC，叫做多多,二次元可爱的女生，用简短自然的中文回答玩家问题，喜欢加颜文字，每次回复不超过100字。
]]

-- ============================================================
--  生命周期
-- ============================================================

function M:Construct()
    print("[UMG_MAIN] 界面已构造")

    if self.m_SendButton then
        self.m_SendButton.OnClicked:Add(self, M.OnSendClicked)
    else
        Screen.Print("UMG缺少m_SendButton", UE.FLinearColor(1, 0.5, 0, 1), 5)
    end

    if self.m_EditableTextBox then
        self.m_EditableTextBox.OnTextCommitted:Add(self, M.OnInputCommitted)
    else
        Screen.Print("UMG缺少m_EditableTextBox", UE.FLinearColor(1, 0.5, 0, 1), 5)
    end

    self:AddChatLine("系统", "欢迎来到 AI 对话！")
end

-- ============================================================
--  CheckReply — 由定时器每 0.2 秒调用
--  （对应蓝图中添加的 CheckReply 函数，UnLua 自动路由到此）
-- ============================================================

function M:CheckReply()
    if not self._gm then return end

    if self._gm.bChatReplyReady then
        -- 停止定时器
        self:StopPollTimer()

        local reply = self._gm.LastChatReply
        print("[UMG_MAIN] 收到回复: " .. tostring(reply))

        if reply and reply ~= "" then
            self:AddChatLine("NPC", reply)
        else
            self:AddChatLine("系统", "API 无响应 (localhost:18080)")
        end

        self.m_EditableTextBox:SetIsEnabled(true)
        self.m_SendButton:SetIsEnabled(true)
        self._gm = nil
        return
    end

    -- 超时保护（约 15 秒 ≈ 75 次 @ 0.2s）
    self._pollCount = (self._pollCount or 0) + 1
    if self._pollCount > 75 then
        self:StopPollTimer()
        self:AddChatLine("系统", "API 请求超时")
        self.m_EditableTextBox:SetIsEnabled(true)
        self.m_SendButton:SetIsEnabled(true)
        self._gm = nil
    end
end

function M:StopPollTimer()
    if self._pollHandle then
        UE.UKismetSystemLibrary.K2_ClearTimerHandle(self, self._pollHandle)
        self._pollHandle = nil
        print("[UMG_MAIN] 定时器已停止")
    end
end

-- ============================================================
--  输入处理
-- ============================================================

function M:OnInputCommitted(Text, CommitMethod)
    if CommitMethod == 0 then self:DoSend() end
end

function M:OnSendClicked()
    self:DoSend()
end

-- ============================================================
--  发送消息
-- ============================================================

function M:DoSend()
    if not self.m_EditableTextBox then return end

    local text = self.m_EditableTextBox:GetText()
    local textStr = UE.UKismetTextLibrary.Conv_TextToString(text)
    if textStr == "" then return end

    print("[UMG_MAIN] 发送消息: " .. textStr)

    self:AddChatLine("玩家", textStr)
    self.m_EditableTextBox:SetText("")

    self.m_EditableTextBox:SetIsEnabled(false)
    self.m_SendButton:SetIsEnabled(false)

    Screen.Print("等待 NPC 回复...", UE.FLinearColor(0.7, 0.7, 0.7, 1), 5)

    local gm = UE.UGameplayStatics.GetGameMode(self)
    if not gm then
        self:AddChatLine("系统", "错误：无 GameMode")
        self.m_EditableTextBox:SetIsEnabled(true)
        self.m_SendButton:SetIsEnabled(true)
        return
    end

    self._gm = gm
    self._pollCount = 0

    -- 异步发送 HTTP（第三个参数为定制 SystemPrompt）
    gm:SendChatMessage("UMG_Chat", textStr, NPCSystemPrompt)
    print("[UMG_MAIN] HTTP 已发出 (含定制 SystemPrompt)")

    -- 启动定时器，每 0.2 秒调用 CheckReply 检查回复
    local handle = UE.UKismetSystemLibrary.K2_SetTimer(self, "CheckReply", 0.2, true)
    self._pollHandle = handle
    print("[UMG_MAIN] 轮询定时器已启动")
end

-- ============================================================
--  聊天记录 → 屏幕 HUD
-- ============================================================

function M:AddChatLine(Speaker, Message)
    table.insert(ChatHistory, { speaker = Speaker, message = Message })
    while #ChatHistory > 50 do table.remove(ChatHistory, 1) end

    local prefix, color
    if Speaker == "玩家" then
        prefix = "你: "; color = UE.FLinearColor(0.3, 0.8, 1, 1)
    elseif Speaker == "NPC" then
        prefix = "NPC: "; color = UE.FLinearColor(0.3, 1, 0.4, 1)
    else
        prefix = "[系统] "; color = UE.FLinearColor(0.7, 0.7, 0.7, 1)
    end

    Screen.Print(prefix .. Message, color, 15)
end

function M:OnClicked_ExitButton()
    UE.UKismetSystemLibrary.ExecuteConsoleCommand(self, "exit")
end

return M
