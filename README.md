# UE4-LocalLLM-Chat

> UE4.27 + UnLua + FastAPI + Ollama によるローカル LLM NPC 対話システム  
> UE4.27 + UnLua + FastAPI + Ollama Local LLM NPC Dialogue System  
> UE4.27 + UnLua + FastAPI + Ollama 本地 LLM 实时 NPC 对话系统

---

## 中文

### 项目简介

**UE4-LocalLLM-Chat** 是一套完整的本地 LLM（大语言模型）NPC 对话系统。它让你在 UE4.27 中使用 UnLua 脚本驱动的 UMG 界面，与本地运行的 Ollama 大模型进行实时对话。

#### 核心特性

- **完全本地运行** — 无需联网，数据不出本地，隐私安全
- **FastAPI 后端** — 异步 HTTP + WebSocket + SSE 流式输出
- **UE4.27 集成** — 通过 UnLua 2.3.6 实现 Lua 脚本驱动 UMG
- **多会话管理** — 按 session_id 隔离不同 NPC 的对话上下文
- **异步非阻塞** — HTTP 异步发送 + K2_SetTimer 轮询，不卡游戏主线程
- **定制 SystemPrompt** — 客户端可动态传入 NPC 人设提示词
- **跨平台模型** — 支持 Ollama 所有模型（qwen2.5、llama3、mistral 等）

#### 架构概览

```
┌──────────────────────────────────────────────┐
│                  UE4.27 Client               │
│  ┌────────────┐    ┌──────────────────────┐  │
│  │ UMG_MAIN   │───▶│ ProjectChatGameMode  │  │
│  │ (UnLua)    │    │ (C++, IUnLuaInterface)│  │
│  └────────────┘    └──────────┬───────────┘  │
│                               │ HTTP POST     │
└───────────────────────────────┼───────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────┐
│          FastAPI Server (localhost:18080)     │
│  ┌──────────────────────────────────────┐    │
│  │  /v1/chat/session?session_id=xxx     │    │
│  │  ChatRequest: messages + system_prompt│    │
│  └──────────────────┬───────────────────┘    │
│                     │                        │
│                     ▼                        │
│  ┌──────────────────────────────────────┐    │
│  │     Session Manager (per NPC)         │    │
│  │  [system][user][assistant][user]...   │    │
│  └──────────────────┬───────────────────┘    │
└─────────────────────┼────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│          Ollama (localhost:11434)             │
│  qwen2.5:7b / llama3 / mistral / ...         │
└──────────────────────────────────────────────┘
```

#### 文件结构

```
UE4-LocalLLM-Chat/
├── README.md                 # 本文件
├── install.bat               # Windows 一键安装脚本
├── server/                   # Python FastAPI 服务端
│   ├── main.py               # API 服务主程序
│   ├── config.py             # 配置文件
│   └── requirements.txt      # Python 依赖
├── client/                   # 测试客户端
│   ├── test_client.py        # 命令行测试工具
│   └── web/
│       └── index.html        # Web 聊天界面
└── ue4/
    └── ProjectChat/          # UE4.27 项目
        ├── ProjectChat.uproject
        ├── Source/
        │   ├── ProjectChat.Target.cs
        │   ├── ProjectChatEditor.Target.cs
        │   └── ProjectChat/
        │       ├── ProjectChat.h / .cpp
        │       ├── ProjectChat.Build.cs
        │       ├── ProjectChatCharacter.h / .cpp
        │       ├── ProjectChatGameMode.h / .cpp     # GameMode（IUnLuaInterface）
        │       └── LLMChatComponent.h / .cpp        # 可选组件（Blueprint 友好）
        └── Content/
            └── Script/                              # UnLua 脚本
                ├── ProjectChat/
                │   ├── ProjectChatGameMode.lua      # GameMode 绑定
                │   └── LLMChatComponent.lua         # 组件绑定
                ├── Tools/
                │   └── Screen.lua                   # 屏幕打印工具
                └── UMG/
                    └── UMG_MAIN.lua                 # 聊天 UI 主逻辑
```

#### 快速开始

**前置要求**
- Python 3.9+
- [Ollama](https://ollama.com/) 已安装并拉取模型
- UE 4.27 + Visual Studio 2019
- [UnLua 2.3.6](https://github.com/Tencent/UnLua) 插件

**1. 安装并启动服务端**

```bash
# 一键安装（Windows）
install.bat

# 或手动执行
cd server
pip install -r requirements.txt
ollama pull qwen2.5:7b
python main.py
```

**2. 测试 API**

```bash
# 健康检查
curl http://localhost:18080/v1/health

# 命令行对话
cd client
python test_client.py "你好！"

# 或打开 client/web/index.html 在浏览器中对话
```

**3. UE4 集成**
- 安装 UnLua 2.3.6 插件到 `Plugins/UnLua/`
- 打开 `ue4/ProjectChat/ProjectChat.uproject`
- UMG_MAIN Widget 实现 `IUnLuaInterface` 接口
- 在蓝图中添加 `CheckReply` 函数（空实现即可）
- 编译运行

#### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/health` | 健康检查 |
| GET | `/v1/models` | 列出可用模型 |
| POST | `/v1/chat` | 单次对话（无上下文） |
| POST | `/v1/chat/session?session_id=xxx` | 带上下文对话 ⭐ |
| POST | `/v1/chat/session/stream` | SSE 流式对话 |
| POST | `/v1/chat/reset?session_id=xxx` | 重置会话 |
| WS | `/v1/chat/ws` | WebSocket 实时对话 |

#### 定制 NPC 人设

在 `Content/Script/UMG/UMG_MAIN.lua` 中修改 `NPCSystemPrompt`：

```lua
local NPCSystemPrompt = [[
你是一个生活在冒险岛世界的NPC角色，名字叫"安牛"。
你性格活泼开朗，喜欢帮助冒险者。
请始终用NPC的语气说话。
回答控制在2-3句话以内，用中文。
不要暴露自己是AI或模型。
]]
```

Lua → C++ → Python 整条链路自动将定制提示词传递给 LLM。

#### License

MIT

---

## 日本語

### プロジェクト概要

**UE4-LocalLLM-Chat** は、UE4.27 内でローカル LLM（大規模言語モデル）と NPC 対話を実現する統合システムです。UnLua で駆動する UMG ウィジェットを通じて、ローカル実行中の Ollama モデルとリアルタイムに対話できます。

#### 主な特徴

- **完全オフライン** — インターネット不要、データはローカルに留まりプライバシー保護
- **FastAPI バックエンド** — 非同期 HTTP + WebSocket + SSE ストリーミング対応
- **UE4.27 統合** — UnLua 2.3.6 による Lua スクリプト駆動 UMG
- **マルチセッション** — session_id 単位で NPC ごとの会話コンテキストを分離
- **ノンブロッキング非同期** — HTTP 非同期送信 + K2_SetTimer ポーリング、ゲームスレッドをブロックしない
- **カスタム SystemPrompt** — クライアントから NPC のキャラクター設定を動的に注入可能
- **マルチモデル対応** — Ollama がサポートする全モデル（qwen2.5、llama3、mistral 等）に対応

#### アーキテクチャ

```
┌──────────────────────────────┐
│       UE4.27 クライアント      │
│  UMG_MAIN (UnLua)            │
│       ↓                      │
│  ProjectChatGameMode (C++)   │
│       ↓ HTTP POST            │
└───────┼──────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│  FastAPI Server (:18080)     │
│  /v1/chat/session            │
│  Session Manager (per NPC)   │
└───────┼──────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│  Ollama (:11434)             │
│  qwen2.5:7b / llama3 / ...  │
└──────────────────────────────┘
```

#### クイックスタート

**前提条件**
- Python 3.9+
- [Ollama](https://ollama.com/) インストール済み
- UE 4.27 + Visual Studio 2019
- [UnLua 2.3.6](https://github.com/Tencent/UnLua) プラグイン

**サーバー起動**

```bash
install.bat
# または
cd server && pip install -r requirements.txt
ollama pull qwen2.5:7b
python main.py
```

**API テスト**

```bash
curl http://localhost:18080/v1/health
cd client && python test_client.py "こんにちは！"
```

**UE4 セットアップ**
- `Plugins/UnLua/` に UnLua を配置
- `ue4/ProjectChat/ProjectChat.uproject` を開く
- UMG_MAIN に `IUnLuaInterface` を実装
- ブループリントに `CheckReply` 関数を追加（空実装）
- コンパイルして実行

#### API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/v1/health` | ヘルスチェック |
| GET | `/v1/models` | 利用可能モデル一覧 |
| POST | `/v1/chat` | 単発対話（コンテキストなし） |
| POST | `/v1/chat/session?session_id=xxx` | コンテキスト付き対話 ⭐ |
| POST | `/v1/chat/session/stream` | SSE ストリーミング |
| POST | `/v1/chat/reset?session_id=xxx` | セッションリセット |
| WS | `/v1/chat/ws` | WebSocket リアルタイム対話 |

#### NPC キャラクター設定

`Content/Script/UMG/UMG_MAIN.lua` 内の `NPCSystemPrompt` を編集してください：

```lua
local NPCSystemPrompt = [[
あなたは冒険島の世界に住むNPC「アンギュウ」です。
明るく活発な性格で、冒険者を助けるのが大好きです。
常にNPCらしい口調で話してください。
回答は2〜3文以内、日本語でお願いします。
自分がAIやモデルであることは絶対に明かさないでください。
]]
```

#### ライセンス

MIT

---

## English

### Overview

**UE4-LocalLLM-Chat** is a complete local LLM (Large Language Model) NPC dialogue system. It enables real-time conversation between UE4.27 UMG widgets (driven by UnLua scripts) and locally running Ollama models.

#### Key Features

- **Fully Offline** — No internet required, all data stays local for privacy
- **FastAPI Backend** — Async HTTP + WebSocket + SSE streaming support
- **UE4.27 Integration** — UnLua 2.3.6 Lua scripting for UMG widgets
- **Multi-Session** — Per-NPC conversation context isolation via session_id
- **Non-Blocking Async** — HTTP async send + K2_SetTimer polling, zero game thread blocking
- **Custom SystemPrompt** — Dynamically inject NPC persona from the client side
- **Multi-Model** — Supports all Ollama models (qwen2.5, llama3, mistral, etc.)

#### Architecture

```
┌──────────────────────────────┐
│       UE4.27 Client           │
│  UMG_MAIN (UnLua)             │
│       ↓                       │
│  ProjectChatGameMode (C++)    │
│       ↓ HTTP POST             │
└───────┼───────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│  FastAPI Server (:18080)      │
│  /v1/chat/session             │
│  Session Manager (per NPC)    │
└───────┼───────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│  Ollama (:11434)              │
│  qwen2.5:7b / llama3 / ...   │
└──────────────────────────────┘
```

#### Quick Start

**Prerequisites**
- Python 3.9+
- [Ollama](https://ollama.com/) installed with models pulled
- UE 4.27 + Visual Studio 2019
- [UnLua 2.3.6](https://github.com/Tencent/UnLua) plugin

**Start the Server**

```bash
# One-click install (Windows)
install.bat

# Or manually
cd server
pip install -r requirements.txt
ollama pull qwen2.5:7b
python main.py
```

**Test the API**

```bash
# Health check
curl http://localhost:18080/v1/health

# Command-line chat
cd client
python test_client.py "Hello!"

# Or open client/web/index.html in a browser
```

**UE4 Setup**
- Place UnLua 2.3.6 in `Plugins/UnLua/`
- Open `ue4/ProjectChat/ProjectChat.uproject`
- Implement `IUnLuaInterface` on UMG_MAIN Widget
- Add a `CheckReply` function in Blueprint (empty body)
- Compile and run

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health` | Health check |
| GET | `/v1/models` | List available models |
| POST | `/v1/chat` | Single-turn chat (no context) |
| POST | `/v1/chat/session?session_id=xxx` | Context-aware chat ⭐ |
| POST | `/v1/chat/session/stream` | SSE streaming chat |
| POST | `/v1/chat/reset?session_id=xxx` | Reset session |
| WS | `/v1/chat/ws` | WebSocket real-time chat |

#### Custom NPC Persona

Edit `NPCSystemPrompt` in `Content/Script/UMG/UMG_MAIN.lua`:

```lua
local NPCSystemPrompt = [[
You are an NPC living in the MapleStory world named "Angus".
You are cheerful and love helping adventurers.
Always speak in an NPC-like tone.
Keep responses within 2-3 sentences.
Never reveal that you are an AI or a model.
]]
```

The Lua → C++ → Python pipeline automatically delivers your custom prompt to the LLM.

#### License

MIT
