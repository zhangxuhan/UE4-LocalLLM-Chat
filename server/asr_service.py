"""
离线语音识别服务（ASR）
========================
使用 faster-whisper，首次运行自动下载 base 模型（~150MB）。

端点:
  POST /v1/asr   multipart/form-data, file=<PCM 原始字节>
                 query param: sample_rate=16000（UE4 实际采样率）
  返回: {"text": "识别出的文字", "language": "zh"}
"""

import struct
import numpy as np
from faster_whisper import WhisperModel

# ---------- 单例 ----------
_model: WhisperModel | None = None

def get_model() -> WhisperModel:
    global _model
    if _model is None:
        print("[ASR] 首次加载 Whisper base 模型（自动下载约 150MB，仅需一次）...")
        _model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",  # CPU 推理用 int8，速度快
        )
        print("[ASR] 模型加载完成")
    return _model


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """PCM-16 LE 字节 → float32 [-1, 1]"""
    n = len(pcm_bytes) // 2
    samples = struct.unpack_from(f"<{n}h", pcm_bytes, 0)
    return np.array(samples, dtype=np.float32) / 32768.0


def resample(audio: np.ndarray, src_rate: int, dst_rate: int = 16000) -> np.ndarray:
    """线性插值简单重采样（demo 够用，不依赖 scipy）"""
    if src_rate == dst_rate:
        return audio
    ratio = dst_rate / src_rate
    new_len = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, new_len)
    left = np.floor(indices).astype(int)
    right = np.minimum(left + 1, len(audio) - 1)
    frac = indices - left
    return audio[left] * (1 - frac) + audio[right] * frac


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    PCM-16 原始字节 → 中文识别文字
    sample_rate: UE4 AudioCapture 实际采样率（常见 48000 或 16000）
    """
    if len(pcm_bytes) < sample_rate // 10 * 2:  # 不足 0.1 秒
        return ""

    audio = pcm16_to_float32(pcm_bytes)

    # 重采样到 Whisper 要求的 16000Hz
    if sample_rate != 16000:
        audio = resample(audio, sample_rate, 16000)

    model = get_model()
    segments, _info = model.transcribe(
        audio,
        language="zh",
        beam_size=1,        # 速度优先
        vad_filter=True,    # 自动过滤静音段
        vad_parameters={"min_silence_duration_ms": 300},
    )

    text = "".join(seg.text for seg in segments).strip()
    return text
