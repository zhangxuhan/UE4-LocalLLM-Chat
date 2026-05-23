---@type ProjectChatGameMode
local M = UnLua.Class()

--- GameMode 初始化（UnLua 自动调用，此时视口可能未就绪，只打日志）
function M:Initialize(InInitializer)
    print("[ProjectChatGameMode] Lua 绑定成功")
end

--- ReceiveBeginPlay - 引擎生命周期，此时视口已就绪，安全加载 UI
function M:ReceiveBeginPlay()
    print("[ProjectChatGameMode] ReceiveBeginPlay，加载主界面")

    local ok, err = pcall(function()
        -- 加载 UMG_Main 蓝图类
        local widgetClass = UE.UClass.Load("/Game/UMG/UMG_Main.UMG_Main_C")
        if not widgetClass then
            print("[ProjectChatGameMode] 错误：找不到 UMG_Main 蓝图，路径是否正确？")
            return
        end

        -- 创建 Widget 实例（Outer 用 GameMode 本身）
        local widget = NewObject(widgetClass, self)
        if not widget then
            print("[ProjectChatGameMode] 错误：NewObject 创建失败")
            return
        end

        -- 添加到视口
        widget:AddToViewport(0)

        -- 保持引用防止 GC
        self.MainWidget = widget
        print("[ProjectChatGameMode] UMG_MAIN 已添加到视口 ✓")
    end)

    if not ok then
        print("[ProjectChatGameMode] 加载失败: " .. tostring(err))
    end
end

return M
