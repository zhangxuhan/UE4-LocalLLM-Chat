# UE4-LocalLLM-Chat

> **v2.0** UE4.27 + UnLua + FastAPI + Ollama — 本地 LLM 语音对话 + 口型同步系统  
> **v2.0** UE4.27 + UnLua + FastAPI + Ollama — Local LLM Voice Dialogue + Lip Sync System

---

<img width="617" height="387" alt="13225a32-e3c9-459c-94af-1553c9553cd2" src="https://github.com/user-attachments/assets/82029e0c-7934-4cbb-8260-9f9229744b05" />
<img width="864" height="474" alt="63b362ba0106d5d83d91fdea004e8b13" src="https://github.com/user-attachments/assets/5df85db8-4632-4e8d-8115-7d8c4b56f633" />
<img width="327" height="555" alt="dd78281b-dbf5-4c84-b2d7-6abf41975326" src="https://github.com/user-attachments/assets/2b46fcc1-349a-474d-851e-073176d7588e" />
<img width="315" height="297" alt="97b06084-2ebd-44f7-a9b4-4ae7661233b0" src="https://github.com/user-attachments/assets/b919b792-811f-4ebf-a61e-fa431f94bfb6" />

## 中文

### 项目简介

**UE4-LocalLLM-Chat v2.0** 在 v1.0 文字对话系统的基础上，新增了完整的**语音输入（ASR）→ LLM 对话 → 语音输出（TTS）→ 口型同步**链路，实现真正意义上的语音驱动 NPC 对话系统。所有模块均支持本地离线运行。

#### v2.0 新增特性

| 模块 | 技术方案 | 说明 |
|------|----------|------|
| 语音识别 ASR | faster-whisper base | 服务端麦克风采集 + Whisper 离线识别 |
| 语音合成 TTS | edge-tts + ffmpeg | 微软神经网络 TTS，小晓音色 |
| 口型同步 | MorphTarget 时间线 | 音素映射 → 关键帧 → UE4 SetMorphTarget |
| Lua 集成 | UnLua + ReceiveTick | 绑定三个组件，热重载无需重编译 |

#### 架构概览

```
[玩家按住 V 键]
      │
      ▼
┌─────────────────────────────────────────────┐
│            UE4.27 Client (UnLua)            │
│                                             │
│  ASRComponent ──HTTP POST──▶ /v1/asr/start  │
│      │                                      │
│  [松开 V]──HTTP POST──▶ /v1/asr/stop        │
│      │                                      │
│  OnSpeechRecognized                         │
│      │                                      │
│  LLMChatComponent ──HTTP──▶ /v1/chat/session│
│      │                                      │
│  OnResponseReceived                         │
│      │                                      │
│  TTSLipSyncComponent ──HTTP──▶ /v1/tts      │
│      │                                      │
│  播放音频 + ReceiveTick 驱动 MorphTarget      │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│       FastAPI Server (localhost:18080)       │
│                                             │
│  POST /v1/asr/start  ── sounddevice 录音    │
│  POST /v1/asr/stop   ── Whisper 识别        │
│  POST /v1/chat/session ── Ollama LLM        │
│  POST /v1/tts        ── edge-tts + 音素线  │
└─────────────────────────────────────────────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   Ollama (11434)        edge-tts / ffmpeg
   qwen2.5:7b            zh-CN-XiaoxiaoNeural
```

#### 文件结构

```
UE4-LocalLLM-Chat/
├── README.md
├── install.bat               # 基础环境安装
├── install_voice.bat         # 语音模块安装（v2.0 新增）
├── server/
│   ├── main.py               # API 服务（含 ASR/TTS 端点）
│   ├── asr_service.py        # faster-whisper 封装（v2.0 新增）
│   ├── tts_service.py        # TTS + 音素时间线
│   ├── config.py             # 配置
│   ├── requirements.txt      # 依赖（含 faster-whisper, edge-tts）
│   └── test_voice_pipeline.py # 语音管线端到端测试（v2.0 新增）
├── client/
│   ├── test_client.py
│   └── web/index.html
└── ue4/ProjectChat/
    ├── Plugins/
    │   └── LipSync/          # 语音对话插件（v2.0 新增）
    │       ├── LipSync.uplugin
    │       └── Source/LipSync/
    │           ├── Public/
    │           │   ├── ASRComponent.h        # 语音识别组件
    │           │   └── TTSLipSyncComponent.h # TTS + 口型同步组件
    │           └── Private/
    │               ├── ASRComponent.cpp
    │               ├── TTSLipSyncComponent.cpp
    │               └── LipSyncModule.cpp
    ├── Source/ProjectChat/
    │   ├── LLMChatComponent.h / .cpp   # LLM 对话组件
    │   └── ...
    └── Content/Script/
        ├── ThirdPersonCPP/
        │   └── ThirdPersonCharacter.lua # 语音对话主逻辑（v2.0 新增）
        ├── ProjectChat/
        └── UMG/
```

#### 快速开始

**前置要求**
- Python 3.9+ / UE 4.27 / Visual Studio 2022 / ffmpeg（在 PATH 中）
- [Ollama](https://ollama.com/) 已安装并执行 `ollama pull qwen2.5:7b`
- [UnLua 2.3.6](https://github.com/Tencent/UnLua)

**1. 安装依赖并启动服务**

```bash
# 安装所有依赖（含 Whisper 模型首次下载约 150MB）
install_voice.bat

# 启动服务
cd server
python main.py
```

**2. UE4 插件设置**

```
1. 将 ue4/ProjectChat/Plugins/LipSync/ 复制到你的项目 Plugins/
2. 在角色 Blueprint 的 Components 面板添加：
   - ASRComponent
   - LLMChatComponent
   - TTSLipSyncComponent
3. 在角色 Blueprint 的 Class Settings → Interfaces 添加 UnLuaInterface
4. 实现 GetModuleName，返回 "ThirdPersonCPP.ThirdPersonCharacter"
5. 编译运行
```

**3. 使用**

```
按住 V  → 开始录音
松开 V  → 识别 → LLM 回复 → 播音 + 口型同步
```

#### API 端点（v2.0 完整版）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/health` | 健康检查 |
| GET | `/v1/models` | 可用模型列表 |
| POST | `/v1/chat` | 单次对话 |
| POST | `/v1/chat/session` | 带上下文对话 ⭐ |
| POST | `/v1/chat/session/stream` | SSE 流式对话 |
| POST | `/v1/chat/reset` | 重置会话 |
| WS | `/v1/chat/ws` | WebSocket 对话 |
| POST | `/v1/asr/start` | 开始录音（v2.0）⭐ |
| POST | `/v1/asr/stop` | 停止录音 + 识别（v2.0）⭐ |
| POST | `/v1/tts` | TTS + 口型时间线（v2.0）⭐ |

#### 口型同步原理

服务端将 LLM 回复文本拆分为音节，映射到对应的嘴型 MorphTarget 权重，生成关键帧时间线随音频一起返回 UE4：

```python
# 音素 → MorphTarget 权重示例
"a" → {"Mouth_Wide": 1.0, "Mouth_Narrow": 0.0, ...}  # 啊
"u" → {"Mouth_Wide": 0.0, "Mouth_Narrow": 1.0, ...}  # 乌
```

UE4 的 `TTSLipSyncComponent` 在 Tick 中线性插值并驱动网格的 MorphTarget，口型跟随音频同步变化。

#### v1.0 → v2.0 升级说明

v2.0 完全向下兼容 v1.0。新增的 LipSync 插件和 Lua 脚本是独立模块，不影响原有文字对话功能。

#### License

MIT

---

## English

### Overview

**UE4-LocalLLM-Chat v2.0** extends the v1.0 text chat system with a complete **voice input (ASR) → LLM → voice output (TTS) → lip sync** pipeline. All components run fully offline.

#### What's New in v2.0

| Module | Technology | Description |
|--------|-----------|-------------|
| ASR | faster-whisper base | Server-side mic capture + offline Whisper recognition |
| TTS | edge-tts + ffmpeg | Microsoft Neural TTS (Xiaoxi voice) |
| Lip Sync | MorphTarget timeline | Phoneme mapping → keyframes → UE4 SetMorphTarget |
| Lua Integration | UnLua + ReceiveTick | Hot-reloadable, no recompile needed |

#### Architecture

```
[Player holds V key]
      │
      ▼
UE4 ASRComponent ──POST──▶ /v1/asr/start  (mic recording begins server-side)
      │
[Release V]──POST──▶ /v1/asr/stop  ──▶  Whisper ASR  ──▶  {"text": "..."}
      │
      ▼
LLMChatComponent ──POST──▶ /v1/chat/session  ──▶  Ollama  ──▶  {"content": "..."}
      │
      ▼
TTSLipSyncComponent ──POST──▶ /v1/tts  ──▶  edge-tts + phoneme timeline
      │
      ▼
Play WAV audio  +  ReceiveTick drives MorphTargets per keyframe
```

#### Quick Start

```bash
# Install all dependencies (downloads ~150MB Whisper model on first run)
install_voice.bat

# Start server
cd server && python main.py
```

Add three components to your NPC Blueprint: `ASRComponent`, `LLMChatComponent`, `TTSLipSyncComponent`.  
Bind `ThirdPersonCharacter.lua` via `IUnLuaInterface`.  
Hold **V** to talk, release to get a voiced + lip-synced response.

#### License

MIT
