"""
TTS + 口型时间线服务（离线 Demo 版）
=====================================
- 纯 stdlib 生成 WAV（无需额外依赖）
- 基于中文字符估算口型时间线
- 后续可替换为 kokoro-onnx / edge-tts 生成真实语音

端点:
  POST /v1/tts  body: {"text": "你好世界", "voice": "zh"}
  返回: {"wav_base64": "...", "duration_ms": 1200, "phonemes": [{"time": 0.0, "morph": {...}}, ...]}
"""

import base64
import io
import json
import math
import struct
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["tts"])


# ========== 1. 中文字符 → 口型映射（Preston Blair 简化版） ==========

# 每个韵母/声母对应的口型权重
# 实际口型由多个 MorphTarget 加权混合
PHONEME_TABLE = {
    "a":    {"Mouth_Wide": 0.90, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.10},
    "o":    {"Mouth_Wide": 0.20, "Mouth_Narrow": 0.70, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "e":    {"Mouth_Wide": 0.55, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.30, "Mouth_Smile": 0.15},
    "i":    {"Mouth_Wide": 0.10, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.70, "Mouth_Smile": 0.50},
    "u":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.85, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "v":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.75, "Mouth_Grimace": 0.20, "Mouth_Smile": 0.00},
    "b":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "p":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "m":    {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "f":    {"Mouth_Wide": 0.10, "Mouth_Narrow": 0.30, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "s":    {"Mouth_Wide": 0.20, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.40, "Mouth_Smile": 0.10},
    "sh":   {"Mouth_Wide": 0.15, "Mouth_Narrow": 0.25, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
    "n":    {"Mouth_Wide": 0.15, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.20, "Mouth_Smile": 0.05},
    "l":    {"Mouth_Wide": 0.25, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.15, "Mouth_Smile": 0.10},
    "rest": {"Mouth_Wide": 0.00, "Mouth_Narrow": 0.00, "Mouth_Grimace": 0.00, "Mouth_Smile": 0.00},
}

# 常见汉字 → 主元音（简化映射，覆盖常用字即可跑 demo）
# 完整方案应用 pinyin 库做 G2P，demo 用查表够用
CHAR_TO_PHONEME = {
    # 啊系列
    "啊": "a", "阿": "a", "哎": "a", "唉": "a", "哎": "a",
    "巴": "a", "把": "a", "爸": "a", "八": "a", "怕": "a",
    "马": "a", "妈": "a", "骂": "a", "发": "a", "答": "a",
    "大": "a", "打": "a", "他": "a", "她": "a", "踏": "a",
    "拿": "a", "哪": "a", "那": "a", "辣": "a", "拉": "a",
    # 哦系列
    "哦": "o", "喔": "o", "我": "o", "握": "o", "窝": "o",
    "波": "o", "播": "o", "博": "o", "伯": "o", "破": "o",
    "摸": "o", "磨": "o", "末": "o", "佛": "o",
    # 额系列
    "额": "e", "俄": "e", "饿": "e", "特": "e", "讷": "e",
    "得": "e", "德": "e", "乐": "e", "了": "e", "这": "e",
    "者": "e", "车": "e", "社": "e", "热": "e", "测": "e",
    "色": "e", "册": "e", "择": "e",
    # 一系列
    "一": "i", "以": "i", "意": "i", "义": "i", "医": "i",
    "比": "i", "必": "i", "笔": "i", "米": "i", "秘": "i",
    "皮": "i", "批": "i", "地": "i", "滴": "i", "抵": "i",
    "体": "i", "踢": "i", "力": "i", "立": "i", "离": "i",
    "你": "i", "里": "i", "理": "i", "济": "i", "机": "i",
    "期": "i", "七": "i", "气": "i", "西": "i", "吸": "i",
    "习": "i", "题": "i", "提": "i", "泥": "i", "衣": "i",
    # 乌系列
    "乌": "u", "五": "u", "物": "u", "无": "u", "吴": "u",
    "不": "u", "步": "u", "布": "u", "补": "u", "普": "u",
    "木": "u", "目": "u", "墓": "u", "福": "u", "夫": "u",
    "都": "u", "读": "u", "度": "u", "图": "u", "土": "u",
    "路": "u", "陆": "u", "努": "u", "怒": "u", "粗": "u",
    "苏": "u", "书": "u", "树": "u", "入": "u", "如": "u",
    "助": "u", "初": "u", "出": "u", "住": "u", "主": "u",
    "湖": "u", "虎": "u", "哭": "u", "古": "u", "顾": "u",
    # 迂系列（ü）
    "于": "v", "与": "v", "雨": "v", "语": "v", "女": "v",
    "绿": "v", "旅": "v", "句": "v", "巨": "v", "聚": "v",
    "去": "v", "区": "v", "趣": "v", "需": "v", "许": "v",
    # 标点符号 → 休止
    "，": "rest", "。": "rest", "？": "rest", "！": "rest",
    "、": "rest", "；": "rest", "：": "rest", "「": "rest", "」": "rest",
    " ": "rest", "\n": "rest",
}

# 未查到映射的字符，默认用 "a"（开口音兜底）
DEFAULT_PHONEME = "a"


def char_to_phoneme(ch: str) -> str:
    """单个字符 → 音素标签"""
    return CHAR_TO_PHONEME.get(ch, DEFAULT_PHONEME)


def get_morph_for_phoneme(ph: str) -> dict:
    """音素标签 → MorphTarget 权重字典"""
    return PHONEME_TABLE.get(ph, PHONEME_TABLE["rest"]).copy()


# ========== 2. 生成音素时间线 ==========

def build_phoneme_timeline(text: str, chars_per_second: float = 4.0) -> list:
    """
    将文本转换为口型关键帧时间线
    text: 输入文本（中文）
    chars_per_second: 每秒朗读字数（中文约 3~5 字/秒）
    返回: [{"time": float, "morph": dict}, ...]
    """
    timeline = []
    char_duration = 1.0 / chars_per_second  # 每个字占多少秒

    for i, ch in enumerate(text):
        t_start = i * char_duration
        ph = char_to_phoneme(ch)
        morph = get_morph_for_phoneme(ph)

        # 字开始：设口型
        timeline.append({"time": round(t_start, 3), "morph": morph})
        # 字结束前 50ms：回归静音（避免口型突然跳变）
        t_end = t_start + char_duration - 0.05
        if t_end > t_start:
            timeline.append({"time": round(t_end, 3), "morph": PHONEME_TABLE["rest"].copy()})

    return timeline


# ========== 3. 生成演示用 WAV（纯 stdlib，无需 numpy/soundfile） ==========

def generate_demo_wav(text: str, sample_rate: int = 24000) -> bytes:
    """
    生成演示用 WAV 音频（正弦波 + 静音交替，模拟朗读节奏）
    纯 stdlib 实现，不依赖 numpy/soundfile
    """
    chars_per_second = 4.0
    total_chars = len(text)
    duration = total_chars / chars_per_second  # 总时长（秒）
    num_samples = int(duration * sample_rate)

    # 生成音频数据：朗读时发 400Hz 正弦波，标点时静音
    audio_bytes = bytearray()

    for i, ch in enumerate(text):
        # 当前字对应样本数
        start_sample = int(i * num_samples / total_chars)
        end_sample = int((i + 1) * num_samples / total_chars)
        n_samples = end_sample - start_sample

        is_punct = ch in "，。？！、；："
        freq = 0 if is_punct else 400  # 标点符号发静音

        for s in range(n_samples):
            t = (start_sample + s) / sample_rate
            if freq > 0:
                # 400Hz 正弦波，幅度渐弱模拟自然语音
                envelope = 0.3 * (1.0 - 0.3 * (s / max(n_samples, 1)))
                sample = int(envelope * 32767 * math.sin(2 * math.pi * freq * t))
            else:
                sample = 0
            audio_bytes.extend(struct.pack("<h", max(-32768, min(32767, sample))))

    # 写 WAV 文件（PCM16，单声道）
    wav_buf = io.BytesIO()
    # WAV Header (44 bytes)
    wav_buf.write(b"RIFF")
    data_size = len(audio_bytes)
    wav_buf.write(struct.pack("<I", 36 + data_size))  # ChunkSize
    wav_buf.write(b"WAVE")
    wav_buf.write(b"fmt ")
    wav_buf.write(struct.pack("<I", 16))              # Subchunk1Size (PCM)
    wav_buf.write(struct.pack("<H", 1))               # AudioFormat (PCM)
    wav_buf.write(struct.pack("<H", 1))               # NumChannels (mono)
    wav_buf.write(struct.pack("<I", sample_rate))      # SampleRate
    wav_buf.write(struct.pack("<I", sample_rate * 2)) # ByteRate
    wav_buf.write(struct.pack("<H", 2))               # BlockAlign
    wav_buf.write(struct.pack("<H", 16))              # BitsPerSample
    wav_buf.write(b"data")
    wav_buf.write(struct.pack("<I", data_size))        # Subchunk2Size
    wav_buf.write(bytes(audio_bytes))

    return wav_buf.getvalue()


# ========== 4. FastAPI 端点 ==========

class TTSRequest(BaseModel):
    text: str
    voice: str = "zh"
    speed: float = 1.0  # 语速倍率（预留，当前未用）


class TTSResponse(BaseModel):
    wav_base64: str
    duration_ms: float
    phonemes: list
    text: str


@router.post("/tts", response_model=TTSResponse)
async def tts_endpoint(req: TTSRequest):
    """
    离线 TTS + 口型时间线接口（Demo 版）
    
    请求: {"text": "你好世界", "voice": "zh"}
    返回: {"wav_base64": "...", "duration_ms": 1000, "phonemes": [...]}
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    text = req.text.strip()

    # 生成 WAV（纯 stdlib）
    t0 = time.time()
    wav_bytes = generate_demo_wav(text)
    wav_b64 = base64.b64encode(wav_bytes).decode("utf-8")
    gen_ms = int((time.time() - t0) * 1000)

    # 生成口型时间线
    timeline = build_phoneme_timeline(text)

    # 估算时长（ms）
    duration_ms = int(len(text) / 4.0 * 1000)

    print(f"[TTS Demo] text='{text[:20]}...' gen={gen_ms}ms duration={duration_ms}ms "
          f"phonemes={len(timeline)} frames")

    return TTSResponse(
        wav_base64=wav_b64,
        duration_ms=duration_ms,
        phonemes=timeline,
        text=text,
    )


# ========== 5. 挂载函数（供 main.py 调用） ==========
def register_tts_routes(app):
    """在 main.py 中调用: from tts_service import register_tts_routes; register_tts_routes(app)"""
    app.include_router(router)
    print("[TTS] 离线口型同步端点已注册: POST /v1/tts")
