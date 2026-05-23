---
--- LLMChatComponent.lua
--- ======================
--- UnLua 示例：在 Lua 中调用本地 LLM 对话组件
---
--- 功能：
--- - ReceiveInit()   组件初始化（等价于蓝图 BeginPlay）
--- - SendMessage()   发送消息到本地 LLM 服务
--- - 事件回调：OnResponseReceived, OnErrorOccurred
---
--- 使用方法：
--- 1. 将此文件放在 Content/Script/ProjectChat/ 下
--- 2. 在关卡中放置带 LLMChatComponent 的 Actor
--- 3. 运行时自动绑定此 Lua 脚本
---

local LLMChatComponent = UnLua.Class()

--- 组件初始化（等价于蓝图 BeginPlay）
function LLMChatComponent:ReceiveInit()
    print("[LLMChat] 组件已初始化 | Actor=" .. tostring(self:GetOwner()))
    print("[LLMChat] API地址=" .. self.ApiBase)

    -- 可选：设置 NPC 人设
    -- self.SystemPrompt = "你是一个老铁匠NPC，说话豪爽，每次回复不超过50字。"

    -- 可选：启动时检查服务健康
    self:CheckServiceHealth()
end

--- 绑定事件回调（需在 Lua 中手动绑定）
function LLMChatComponent:ReceiveBeginPlay()
    -- 先调用父类
    UnLua.Class.ReceiveBeginPlay(self)

    -- 绑定回调事件
    self.OnResponseReceived:Add(self, self.OnAIResponse)
    self.OnErrorOccurred:Add(self, self.OnAIError)
    self.OnHealthCheckResult:Add(self, self.OnHealthResult)
end

--- 收到完整 AI 回复
function LLMChatComponent:OnAIResponse(ResponseText)
    print("[LLMChat] AI回复: " .. ResponseText)
    -- 在这里处理 AI 回复，比如显示在UI上、控制角色说话动画等
end

--- 发生错误
function LLMChatComponent:OnAIError(ErrorMessage)
    print("[LLMChat] 错误: " .. ErrorMessage)
end

--- 健康检查结果
function LLMChatComponent:OnHealthResult(JsonStr)
    print("[LLMChat] 健康检查: " .. JsonStr)
end

--- 便捷函数：发送消息并自动打印回复
function LLMChatComponent:Say(Message)
    print("[LLMChat] 玩家: " .. Message)
    self:SendMessage(Message)
end

--- 便捷函数：流式对话（逐字回调）
function LLMChatComponent:SayStream(Message)
    print("[LLMChat] 玩家(流式): " .. Message)
    self.OnTokenReceived:Add(self, self.OnToken)      -- 每收到一个字
    self.OnStreamComplete:Add(self, self.OnStreamEnd)  -- 对话结束
    self:SendMessageStream(Message)
end

function LLMChatComponent:OnToken(Token)
    -- 在这里逐字追加到 UI
    -- 例如: self.ChatBox.Text = self.ChatBox.Text .. Token
end

function LLMChatComponent:OnStreamEnd()
    print("[LLMChat] 流式对话完成")
    self.OnTokenReceived:Remove(self, self.OnToken)
    self.OnStreamComplete:Remove(self, self.OnStreamEnd)
end

--- 重置对话历史
function LLMChatComponent:Forget()
    self:ResetConversation()
    print("[LLMChat] 对话已重置")
end

return LLMChatComponent
