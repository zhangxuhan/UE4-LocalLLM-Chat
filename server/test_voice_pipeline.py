"""
语音管线端到端测试脚本
=======================
不需要 UE4，直接在命令行测试完整流程：
  1. 用麦克风录音（按 Enter 开始/停止）
  2. 发送到 /v1/asr 识别文字
  3. 把文字发送给 /v1/chat/session 对话
  4. 把回复发送到 /v1/tts 生成音频
  5. 用系统播放器播放音频

用法:
  python test_voice_pipeline.py

依赖:
  pip install sounddevice numpy httpx
  （服务端 faster-whisper 已在 requirements.txt 里）
"""

import sys
import io
import struct
import wave
import time
import tempfile
import os
import threading
import httpx

API = "http://localhost:18080"
SESSION_ID = "test_voice_pipeline"

# -------- 录音 --------
def record_audio(sample_rate=16000):
    """按 Enter 开始录音，再按 Enter 停止，返回 PCM-16 字节"""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("请先安装 sounddevice: pip install sounddevice")
        sys.exit(1)

    print("\n[录音] 按 Enter 开始录音...")
    input()

    frames = []
    stop_event = threading.Event()

    def callback(indata, frame_count, time_info, status):
        if stop_event.is_set():
            raise sd.CallbackStop()
        frames.append(indata.copy())

    print("[录音] 录音中... 再按 Enter 停止")
    with sd.InputStream(samplerate=sample_rate, channels=1,
                        dtype='float32', callback=callback):
        input()
        stop_event.set()

    print("[录音] 录音结束")
    if not frames:
        return b"", sample_rate

    import numpy as np
    audio = np.concatenate(frames, axis=0).flatten()
    pcm = (audio * 32767).astype(np.int16).tobytes()
    return pcm, sample_rate


# -------- ASR --------
def recognize(pcm_bytes: bytes, sample_rate: int) -> str:
    print(f"[ASR] 发送识别请求 ({len(pcm_bytes)//2/sample_rate:.1f}秒音频)...")
    resp = httpx.post(
        f"{API}/v1/asr",
        params={"sample_rate": sample_rate},
        files={"file": ("audio.pcm", pcm_bytes, "application/octet-stream")},
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["text"]
    print(f"[ASR] 识别结果: 「{text}」")
    return text


# -------- LLM --------
def chat(text: str) -> str:
    print(f"[LLM] 发送对话请求...")
    resp = httpx.post(
        f"{API}/v1/chat/session",
        params={"session_id": SESSION_ID},
        json={"messages": [{"role": "user", "content": text}]},
        timeout=60,
    )
    resp.raise_for_status()
    reply = resp.json()["content"]
    print(f"[LLM] 回复: 「{reply}」")
    return reply


# -------- TTS --------
def speak(text: str):
    print(f"[TTS] 合成语音...")
    resp = httpx.post(f"{API}/v1/tts", json={"text": text}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    import base64
    wav_bytes = base64.b64decode(data["wav_base64"])
    dur_ms = data["duration_ms"]
    frames = data.get("phonemes", [])
    print(f"[TTS] 合成完成: {dur_ms}ms, {len(frames)} 个口型关键帧")

    # 写临时文件后播放
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name

    print(f"[TTS] 播放音频...")
    if sys.platform == "win32":
        os.system(f'start /wait "" "{tmp_path}"')
    elif sys.platform == "darwin":
        os.system(f'afplay "{tmp_path}"')
    else:
        os.system(f'aplay "{tmp_path}" 2>/dev/null || ffplay -nodisp -autoexit "{tmp_path}" 2>/dev/null')

    os.unlink(tmp_path)


# -------- 健康检查 --------
def check_health():
    try:
        resp = httpx.get(f"{API}/v1/health", timeout=5)
        info = resp.json()
        model_ok = info.get("current_model_available", False)
        print(f"[健康] 服务在线 | 模型: {info.get('current_model')} | "
              f"{'✓ 可用' if model_ok else '✗ 不可用，请先 ollama pull'}")
        return True
    except Exception as e:
        print(f"[错误] 无法连接服务: {e}")
        print("请先启动服务: python main.py")
        return False


# -------- 主循环 --------
def main():
    print("=" * 50)
    print("  语音对话管线测试（ASR → LLM → TTS）")
    print("=" * 50)

    if not check_health():
        return

    while True:
        try:
            pcm, sr = record_audio()
            if not pcm:
                continue

            text = recognize(pcm, sr)
            if not text:
                print("[ASR] 未识别到文字，请重试")
                continue

            reply = chat(text)
            if not reply:
                continue

            speak(reply)

        except KeyboardInterrupt:
            print("\n退出")
            break
        except httpx.HTTPStatusError as e:
            print(f"[错误] HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"[错误] {e}")


if __name__ == "__main__":
    main()
