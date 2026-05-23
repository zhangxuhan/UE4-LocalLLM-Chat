"""
本地LLM实时对话系统 - FastAPI 服务端
======================================
功能:
  - POST /v1/chat         非流式对话（UE4友好）
  - POST /v1/chat/stream  流式对话（SSE）
  - WS   /v1/chat/ws      WebSocket流式对话
  - GET  /v1/models       查看可用模型
  - GET  /v1/health       健康检查
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
    
    请求示例:
    {
        "messages": [{"role": "user", "content": "你好"}],
        "temperature": 0.7,
        "max_tokens": 2048
    }
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
    """
    带会话历史的对话接口（自动管理上下文）
    
    请求示例:
    POST /v1/chat/session?session_id=player_001
    {
        "messages": [{"role": "user", "content": "我叫小明"}],
        "temperature": 0.7
    }
    """
    # 获取历史
    history = get_history(session_id)

    # 若客户端传了定制的 system_prompt，更新或替换 system 消息
    if req.system_prompt:
        sys_msg = {"role": "system", "content": req.system_prompt}
        if history and history[0]["role"] == "system":
            history[0] = sys_msg
        else:
            history.insert(0, sys_msg)

    # 添加新消息到历史
    for msg in req.messages:
        add_to_history(session_id, msg.role, msg.content)

    # 用完整历史调用
    try:
        result = await call_ollama_chat(
            get_history(session_id),  # 重新获取，因为上面修改了
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
    """
    带会话历史的流式对话（SSE格式）
    """
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
            # 保存完整回复
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
    """
    WebSocket流式对话接口
    """
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

            # 重置指令
            if user_msg.strip() == "/reset":
                sessions[session_id] = [{"role": "system", "content": config.system_prompt}]
                history = get_history(session_id)
                await websocket.send_text(json.dumps({"role": "system", "content": "对话已重置"}))
                continue

            # 添加用户消息
            add_to_history(session_id, "user", user_msg)
            await websocket.send_text(json.dumps({"role": "user", "content": user_msg}))

            # 流式生成回复
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

            # 保存并发送完成信号
            add_to_history(session_id, "assistant", full_response)
            await websocket.send_text(json.dumps({
                "role": "assistant",
                "content": "",
                "done": True,
            }))

    except WebSocketDisconnect:
        pass  # 客户端断开
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass


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
╚══════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host=config.api_host, port=config.api_port)
