"""
本地LLM实时对话系统 - FastAPI 服务端
======================================
功能:
  - POST /v1/chat         非流式对话（UE4友好）
  - POST /v1/chat/stream  流式对话（SSE）
  - WS   /v1/chat/ws      WebSocket流式对话
  - GET  /v1/health       健康检查
  - POST /v1/tts          离线TTS + 口型时间线
  - GET  /v1/models       查看可用模型
  - POST /v1/chat/reset   重置对话历史
"""

import json
import asyncio
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import httpx

from config import config

# ----- FastAPI 应用 -----
app = FastAPI(
    title="Local LLM Chat API",
    description="本地实时对话模型接口 - 供UE4等客户端调用",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- 数据模型 -----
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    system_prompt: Optional[str] = None
    temperature: float = config.default_temperature
    max_tokens: int = config.default_max_tokens
    top_p: float = config.default_top_p
    stream: bool = False


class ChatResponse(BaseModel):
    role: str = "assistant"
    content: str
    done: bool = True


# ----- 对话历史管理（按session_id） -----
sessions: dict[str, list[dict]] = {}


def get_history(session_id: str) -> list[dict]:
    if session_id not in sessions:
        sessions[session_id] = [
            {"role": "system", "content": config.system_prompt}
        ]
    return sessions[session_id]


def add_to_history(session_id: str, role: str, content: str):
    history = get_history(session_id)
    history.append({"role": role, "content": content})
    # 裁剪历史: 保留system prompt + 最近N轮对话(每轮2条)
    max_messages = 1 + config.max_history_turns * 2
    if len(history) > max_messages:
        # 保留 system prompt
        system_msgs = [m for m in history if m["role"] == "system"]
        other_msgs = [m for m in history if m["role"] != "system"]
        sessions[session_id] = system_msgs + other_msgs[-(max_messages - len(system_msgs)):]


# ----- Ollama API 调用 -----
async def call_ollama_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
) -> dict:
    """调用Ollama Chat API (非流式)"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{config.ollama_host}/api/chat",
            json={
                "model": config.model_name,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": top_p,
                },
            },
        )
        resp.raise_for_status()
        return resp.json()


async def call_ollama_chat_stream(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
) -> AsyncGenerator[str, None]:
    """调用Ollama Chat API (流式)"""
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{config.ollama_host}/api/chat",
            json={
                "model": config.model_name,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": top_p,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            yield chunk["message"]["content"]
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue


# ----- API 端点 -----
@app.get("/v1/health")
async def health_check():
    """健康检查 + Ollama连接测试"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{config.ollama_host}/api/tags")
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            current_available = config.model_name in [m["name"] for m in models] or \
                                any(m["name"].startswith(config.model_name) for m in models)
    except Exception:
        model_names = []
        current_available = False

    return {
        "status": "ok",
        "ollama_connected": len(model_names) > 0,
        "current_model": config.model_name,
        "current_model_available": current_available,
        "available_models": model_names,
        "api_version": "1.0.0",
    }


@app.get("/v1/models")
async def list_models():
    """列出Ollama中可用的模型"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{config.ollama_host}/api/tags")
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"无法连接Ollama: {str(e)}")


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    非流式对话接口 - 适合UE4 HTTP调用
    """
    try:
        result = await call_ollama_chat(
            [m.model_dump() for m in req.messages],
            req.temperature,
            req.max_tokens,
            req.top_p,
        )
        content = result.get("message", {}).get("content", "")
        return ChatResponse(content=content, done=True)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama调用失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/session")
async def chat_with_session(req: ChatRequest, session_id: str = "default"):
    """带会话历史的对话接口（自动管理上下文）"""
    history = get_history(session_id)

    if req.system_prompt:
        sys_msg = {"role": "system", "content": req.system_prompt}
        if history and history[0]["role"] == "system":
            history[0] = sys_msg
        else:
            history.insert(0, sys_msg)

    for msg in req.messages:
        add_to_history(session_id, msg.role, msg.content)

    try:
        result = await call_ollama_chat(
            get_history(session_id),
            req.temperature,
            req.max_tokens,
            req.top_p,
        )
        content = result.get("message", {}).get("content", "")
        add_to_history(session_id, "assistant", content)
        return ChatResponse(content=content, done=True)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama调用失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/session/stream")
async def chat_session_stream(req: ChatRequest, session_id: str = "default"):
    """带会话历史的流式对话（SSE格式）"""
    history = get_history(session_id)

    for msg in req.messages:
        add_to_history(session_id, msg.role, msg.content)

    full_response = ""

    async def generate():
        nonlocal full_response
        try:
            async for token in call_ollama_chat_stream(
                get_history(session_id),
                req.temperature,
                req.max_tokens,
                req.top_p,
            ):
                full_response += token
                yield f"data: {json.dumps({'content': token, 'done': False})}\n\n"
            add_to_history(session_id, "assistant", full_response)
            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/v1/chat/reset")
async def reset_session(session_id: str = "default"):
    """重置指定会话的对话历史"""
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "ok", "message": f"会话 {session_id} 已重置"}


@app.websocket("/v1/chat/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket流式对话接口"""
    await websocket.accept()
    session_id = "ws_default"
    history = get_history(session_id)

    try:
        while True:
            data = await websocket.receive_text()
            req = json.loads(data)

            user_msg = req.get("message", "")
            if not user_msg:
                await websocket.send_text(json.dumps({"error": "message字段不能为空"}))
                continue

            if user_msg.strip() == "/reset":
                sessions[session_id] = [{"role": "system", "content": config.system_prompt}]
                history = get_history(session_id)
                await websocket.send_text(json.dumps({"role": "system", "content": "对话已重置"}))
                continue

            add_to_history(session_id, "user", user_msg)
            await websocket.send_text(json.dumps({"role": "user", "content": user_msg}))

            temperature = req.get("temperature", config.default_temperature)
            max_tokens = req.get("max_tokens", config.default_max_tokens)
            top_p = req.get("top_p", config.default_top_p)

            full_response = ""
            async for token in call_ollama_chat_stream(
                get_history(session_id), temperature, max_tokens, top_p
            ):
                full_response += token
                await websocket.send_text(json.dumps({
                    "role": "assistant",
                    "content": token,
                    "done": False,
                }))

            add_to_history(session_id, "assistant", full_response)
            await websocket.send_text(json.dumps({
                "role": "assistant",
                "content": "",
                "done": True,
            }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass


# ----- TTS 口型同步端点（离线 Demo 版） -----
# 说明: 纯 stdlib 实现，无需额外依赖，生成演示用 WAV + 口型时间线
# 后续可替换为 kokoro-onnx / edge-tts 生成真实语音

import base64
import io
import math
import struct
import time

from fastapi import UploadFile, File

# 口型映射表（Preston Blair 简化版）
# MorphTarget 名对应 skl_Anime_MaleAverage：
#   Mouth_Wide    宽嘴（啊、额）
#   Mouth_Narrow  窄嘴（乌、迂、哦）
#   Mouth_Grimace 龇牙（一、咧嘴辅音）
#   Mouth_Smile   微笑（过渡用，让说话更自然）
_PHONEME_TABLE = {
    "a":    {"Mouth_Wide": 1.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.15},
    "o":    {"Mouth_Wide": 0.30, "Mouth_Narrow": 1.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "e":    {"Mouth_Wide": 0.70, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.40, "Mouth_Smile": 0.20},
    "i":    {"Mouth_Wide": 0.15, "Mouth_Narrow": 0.00, "Mouth_Grimace": 1.00, "Mouth_Smile": 0.70},
    "u":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 1.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "v":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.90, "Mouth_Grimace": 0.30, "Mouth_Smile": 0.00},
    "b":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "p":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "m":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "f":    {"Mouth_Wide": 0.15, "Mouth_Narrow": 0.40, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "s":    {"Mouth_Wide": 0.30, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.55, "Mouth_Smile": 0.15},
    "sh":   {"Mouth_Wide": 0.20, "Mouth_Narrow": 0.35, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "n":    {"Mouth_Wide": 0.20, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.30, "Mouth_Smile": 0.08},
    "l":    {"Mouth_Wide": 0.35, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.20, "Mouth_Smile": 0.15},
    "rest": {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
}

# 常见汉字 → 主元音（简化映射，demo 够用）
_CHAR_TO_PHONEME = {
    "啊": "a", "阿": "a", "八": "a", "大": "a", "打": "a", "他": "a",
    "妈": "a", "马": "a", "那": "a", "啦": "a", "发": "a", "答": "a",
    "哦": "o", "我": "o", "握": "o", "波": "o", "破": "o", "摸": "o",
    "额": "e", "得": "e", "特": "e", "乐": "e", "这": "e", "车": "e",
    "一": "i", "以": "i", "比": "i", "地": "i", "你": "i", "里": "i",
    "期": "i", "机": "i", "西": "i", "力": "i", "题": "i", "气": "i",
    "乌": "u", "五": "u", "不": "u", "步": "u", "图": "u", "路": "u",
    "书": "u", "出": "u", "住": "u", "湖": "u", "哭": "u", "入": "u",
    "于": "v", "雨": "v", "女": "v", "绿": "v", "去": "v", "许": "v",
    "，": "rest", "。": "rest", "？": "rest", "！": "rest",
    "、": "rest", "；": "rest", "：": "rest", " ": "rest",
}

_DEFAULT_PHONEME = "a"


def _char_to_phoneme(ch: str) -> str:
    return _CHAR_TO_PHONEME.get(ch, _DEFAULT_PHONEME)


def _build_timeline(text: str, cps: float = 3.5) -> list:
    """文本 → 口型关键帧时间线（字间不归零，嘴巴保持连续开合）"""
    timeline = []
    dur = 1.0 / cps
    for i, ch in enumerate(text):
        t = i * dur
        ph = _char_to_phoneme(ch)
        morph = dict(_PHONEME_TABLE.get(ph, _PHONEME_TABLE["rest"]))
        timeline.append({"time": round(t, 3), "morph": morph})
    # 只在结尾归零
    total = len(text) * dur
    timeline.append({"time": round(total, 3), "morph": dict(_PHONEME_TABLE["rest"])})
    return timeline


def _generate_wav(text: str, sample_rate: int = 24000) -> bytes:
    """生成演示用 WAV（正弦波交替，纯 stdlib）"""
    cps = 4.0
    total_samples = int(len(text) / cps * sample_rate)
    buf = bytearray()

    for i, ch in enumerate(text):
        s_start = int(i * total_samples / max(len(text), 1))
        s_end = int((i + 1) * total_samples / max(len(text), 1))
        is_punct = ch in "，。？！、；："
        freq = 0 if is_punct else 400
        for s in range(s_end - s_start):
            t = (s_start + s) / sample_rate
            if freq > 0:
                env = 0.3 * (1.0 - 0.3 * s / max(s_end - s_start, 1))
                sample = int(env * 32767 * math.sin(2 * math.pi * freq * t))
            else:
                sample = 0
            buf.extend(struct.pack("<h", max(-32768, min(32767, sample))))

    # WAV header
    wav = io.BytesIO()
    wav.write(b"RIFF")
    wav.write(struct.pack("<I", 36 + len(buf)))
    wav.write(b"WAVEfmt ")
    wav.write(struct.pack("<I", 16))
    wav.write(struct.pack("<H", 1))
    wav.write(struct.pack("<H", 1))
    wav.write(struct.pack("<I", sample_rate))
    wav.write(struct.pack("<I", sample_rate * 2))
    wav.write(struct.pack("<H", 2))
    wav.write(struct.pack("<H", 16))
    wav.write(b"data")
    wav.write(struct.pack("<I", len(buf)))
    wav.write(bytes(buf))
    return wav.getvalue()


class TTSRequestModel(BaseModel):
    text: str
    voice: str = "zh"
    speed: float = 1.0


async def _synthesize_edge_tts(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bytes:
    """用 edge-tts 合成真实语音，返回 WAV bytes（24000Hz 单声道）"""
    import edge_tts, tempfile, os, subprocess
    # edge-tts 输出 mp3，用 ffmpeg 转 wav；若无 ffmpeg 则 fallback 到 mp3 直接返回
    communicate = edge_tts.Communicate(text, voice)
    mp3_path = tempfile.mktemp(suffix=".mp3")
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        await communicate.save(mp3_path)
        # 尝试用 ffmpeg 转成 pcm16 wav
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path,
             "-ar", "24000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True, timeout=15
        )
        if result.returncode == 0:
            data = open(wav_path, "rb").read()
        else:
            # ffmpeg 不可用，直接返回 mp3 bytes（UE4 SoundWaveProcedural 需要 pcm，降级用 demo wav）
            data = b""
    finally:
        for p in [mp3_path, wav_path]:
            try: os.unlink(p)
            except: pass
    return data


@app.post("/v1/tts")
async def tts_endpoint(req: TTSRequestModel):
    """TTS + 口型时间线（优先 edge-tts 真实语音，失败降级为 Demo 正弦波）"""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    text = req.text.strip()
    t0 = time.time()

    # 先尝试 edge-tts
    wav_bytes = b""
    try:
        wav_bytes = await _synthesize_edge_tts(text, req.voice or "zh-CN-XiaoxiaoNeural")
    except Exception as e:
        print(f"[TTS] edge-tts 失败: {e}，降级到 Demo 模式")

    # 降级：用 demo 正弦波
    if not wav_bytes:
        wav_bytes = _generate_wav(text)

    wav_b64 = base64.b64encode(wav_bytes).decode("utf-8")
    timeline = _build_timeline(text)
    # 从 WAV 头读实际时长（字节数-44） / (采样率*2)
    if len(wav_bytes) > 44:
        duration_ms = int((len(wav_bytes) - 44) / (24000 * 2) * 1000)
    else:
        duration_ms = int(len(text) / 4.0 * 1000)

    print(f"[TTS] '{text[:20]}' gen={int((time.time()-t0)*1000)}ms duration={duration_ms}ms")

    return {
        "wav_base64": wav_b64,
        "duration_ms": duration_ms,
        "phonemes": timeline,
        "text": text,
    }


# ----- ASR 端点（服务端录音版）-----
# UE4 不负责录音，只发 start/stop 信号；Python 用 sounddevice 录，录完直接识别

import threading
import numpy as np

_asr_recording = False
_asr_frames: list = []
_asr_thread: threading.Thread | None = None
_ASR_SAMPLE_RATE = 16000


def _record_worker():
    """后台线程：持续录音直到 _asr_recording=False"""
    try:
        import sounddevice as sd
    except ImportError:
        print("[ASR] sounddevice 未安装，请运行: pip install sounddevice")
        return

    global _asr_frames
    _asr_frames = []

    def callback(indata, frames, time_info, status):
        if _asr_recording:
            _asr_frames.append(indata.copy())

    with sd.InputStream(samplerate=_ASR_SAMPLE_RATE, channels=1,
                        dtype='float32', callback=callback, blocksize=1024):
        while _asr_recording:
            import time as _time
            _time.sleep(0.05)


@app.post("/v1/asr/start")
async def asr_start():
    """UE4 按下录音键时调用，开始服务端录音"""
    global _asr_recording, _asr_thread
    if _asr_recording:
        return {"status": "already_recording"}
    _asr_recording = True
    _asr_thread = threading.Thread(target=_record_worker, daemon=True)
    _asr_thread.start()
    print("[ASR] 开始录音...")
    return {"status": "recording"}


@app.post("/v1/asr/stop")
async def asr_stop():
    """UE4 松开录音键时调用，停止录音并返回识别文字"""
    global _asr_recording, _asr_frames

    if not _asr_recording:
        return {"text": "", "error": "未在录音"}

    _asr_recording = False
    if _asr_thread:
        _asr_thread.join(timeout=1.0)

    if not _asr_frames:
        return {"text": "", "error": "录音数据为空"}

    audio = np.concatenate(_asr_frames, axis=0).flatten()
    pcm_bytes = (audio * 32767).astype(np.int16).tobytes()
    duration = len(audio) / _ASR_SAMPLE_RATE
    print(f"[ASR] 录音结束，时长 {duration:.1f}s，开始识别...")

    if duration < 0.3:
        return {"text": "", "error": "录音太短"}

    try:
        from asr_service import transcribe_pcm
        t0 = time.time()
        # 在线程池里跑，不阻塞事件循环
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None, lambda: transcribe_pcm(pcm_bytes, sample_rate=_ASR_SAMPLE_RATE)
        )
        print(f"[ASR] 识别完成 {int((time.time()-t0)*1000)}ms | '{text}'")
        return {"text": text, "language": "zh"}
    except ImportError:
        raise HTTPException(status_code=503,
            detail="请运行: pip install faster-whisper numpy sounddevice")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/asr")
async def asr_upload(
    file: UploadFile = File(...),
    sample_rate: int = 16000,
):
    """兼容旧接口：接收上传的 PCM 文件做识别"""
    pcm_bytes = await file.read()
    if not pcm_bytes:
        raise HTTPException(status_code=400, detail="音频数据为空")
    try:
        from asr_service import transcribe_pcm
        text = transcribe_pcm(pcm_bytes, sample_rate=sample_rate)
        return {"text": text, "language": "zh"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----- 启动入口 -----
if __name__ == "__main__":
    import uvicorn
    print(f"""
╔══════════════════════════════════════════════╗
║        Local LLM Chat API Server            ║
╠══════════════════════════════════════════════╣
║  Model: {config.model_name:<36} ║
║  API:   http://{config.api_host}:{config.api_port:<5}               ║
╠══════════════════════════════════════════════╣
║  Endpoints:                                 ║
║    GET  /v1/health       健康检查             ║
║    GET  /v1/models       模型列表             ║
║    POST /v1/chat         直接对话             ║
║    POST /v1/chat/session 会话对话(带上下文)    ║
║    POST /v1/chat/reset   重置会话             ║
║    WS   /v1/chat/ws      WebSocket流式对话    ║
║    POST /v1/tts          TTS + 口型时间线     ║
║    POST /v1/asr          语音识别(ASR)        ║
╚══════════════════════════════════════════════╝
    """)
    # 预加载 Whisper 模型，避免第一次请求时超时
    print("[ASR] 预加载 Whisper 模型...")
    try:
        from asr_service import get_model
        get_model()
        print("[ASR] 模型就绪")
    except Exception as e:
        print(f"[ASR] 模型加载失败（ASR 功能不可用）: {e}")

    uvicorn.run(app, host=config.api_host, port=config.api_port)
