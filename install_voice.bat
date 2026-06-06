@echo off
chcp 65001 > nul
echo ============================================
echo   安装语音识别依赖（ASR）
echo ============================================

cd /d "%~dp0server"

echo.
echo [1/2] 安装 Python 依赖...
pip install faster-whisper numpy python-multipart sounddevice

echo.
echo [2/2] 预下载 Whisper base 模型（约 150MB，仅需一次）...
python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('[OK] 模型下载完成')"

echo.
echo ============================================
echo   安装完成！
echo.
echo   测试语音管线:
echo     1. 先启动服务: python main.py
echo     2. 再运行测试: python test_voice_pipeline.py
echo ============================================
pause
