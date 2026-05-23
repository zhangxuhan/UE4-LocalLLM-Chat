@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════════════╗
echo ║   本地 LLM 实时对话系统 - 一键安装脚本       ║
echo ╚══════════════════════════════════════════════╝
echo.

:: ===== Step 1: 检查 Ollama =====
echo [1/4] 检查 Ollama...
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   Ollama 未安装，正在下载...
    echo   请手动访问 https://ollama.com/download/windows 下载安装
    echo   安装完成后重新运行此脚本
    pause
    exit /b 1
)
echo   Ollama 已安装 ✓

:: ===== Step 2: 启动 Ollama 服务 =====
echo [2/4] 确保 Ollama 服务运行中...
ollama list >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   启动 Ollama 服务...
    start "Ollama" ollama serve
    timeout /t 3 >nul
)
echo   Ollama 服务就绪 ✓

:: ===== Step 3: 拉取模型 =====
echo [3/4] 拉取模型 (qwen2.5:7b)...
echo   这可能需要几分钟，取决于网速...
ollama pull qwen2.5:7b
if %ERRORLEVEL% NEQ 0 (
    echo   模型拉取失败，请检查网络或尝试其他模型
    echo   备选: ollama pull qwen2.5:7b-instruct
    pause
    exit /b 1
)
echo   模型拉取完成 ✓

:: ===== Step 4: 安装 Python 依赖 =====
echo [4/4] 安装 Python 依赖...
pip install -r "%~dp0server\requirements.txt" -q
if %ERRORLEVEL% NEQ 0 (
    echo   Python依赖安装失败，请检查Python环境
    pause
    exit /b 1
)
echo   Python依赖安装完成 ✓

:: ===== Step 5: 启动 API 服务 =====
echo.
echo [5/5] 启动本地 LLM 对话服务...
start "LLM Chat API" /d "%~dp0server" python main.py

timeout /t 3 >nul
echo   服务启动中，请稍候...

echo.
echo ╔══════════════════════════════════════════════╗
echo ║           安装完成！                          ║
echo ╠══════════════════════════════════════════════╣
echo ║  项目路径: E:\Project\ChatDemo                   ║
echo ║                                             ║
echo ║  启动服务（首次安装后自动启动，后续手动）:       ║
echo ║    cd /d E:\Project\ChatDemo\server            ║
echo ║    python main.py                              ║
echo ║                                             ║
echo ║  服务地址: http://localhost:18080             ║
echo ║  Web界面: 双击 client\web\index.html          ║
echo ║  API文档: http://localhost:18080/docs         ║
echo ╚══════════════════════════════════════════════╝
echo.
echo 服务已在后台启动，访问 http://localhost:18080/docs 测试
pause
