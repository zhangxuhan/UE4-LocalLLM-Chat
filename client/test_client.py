"""
命令行测试客户端
用法:
    python test_client.py                    # 进入交互模式
    python test_client.py "你好，你是谁？"     # 单次对话
    python test_client.py --stream "讲个笑话" # 流式输出
"""

import sys
import json
import asyncio
import httpx
import websockets

API_BASE = "http://localhost:18080"
WS_URL = "ws://localhost:18080/v1/chat/ws"


async def check_health():
    """检查服务是否正常运行"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_BASE}/v1/health", timeout=5.0)
            data = resp.json()
            print(f"服务状态: {data['status']}")
            print(f"Ollama连接: {'OK' if data['ollama_connected'] else 'FAIL'}")
            print(f"当前模型: {data['current_model']} {'(可用)' if data['current_model_available'] else '(未下载!)'}")
            if not data['current_model_available']:
                print(f"可用模型: {data['available_models']}")
                return False
            return True
        except Exception as e:
            print(f"无法连接到API服务: {e}")
            return False


async def single_chat(message: str, stream: bool = False, session_id: str = "cli_test"):
    """单次对话"""
    if stream:
        # SSE流式
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/v1/chat/session/stream?session_id={session_id}",
                json={
                    "messages": [{"role": "user", "content": message}],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
            ) as resp:
                print("Assistant: ", end="", flush=True)
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data.get("error"):
                            print(f"\n错误: {data['error']}")
                            break
                        if data.get("done"):
                            print()
                            break
                        print(data.get("content", ""), end="", flush=True)
    else:
        # 非流式
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{API_BASE}/v1/chat/session?session_id={session_id}",
                json={
                    "messages": [{"role": "user", "content": message}],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
            )
            data = resp.json()
            print(f"Assistant: {data['content']}")


async def interactive_mode():
    """交互模式 - WebSocket流式"""
    print("\n进入交互模式，输入消息开始对话（输入 /reset 重置，/quit 退出）\n")

    async with websockets.connect(WS_URL) as ws:
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input == "/quit":
                    break

                # 发送消息
                await ws.send(json.dumps({"message": user_input}))

                # 接收流式响应
                print("Assistant: ", end="", flush=True)
                while True:
                    data = json.loads(await ws.recv())

                    if data.get("role") == "user":
                        continue  # 跳过回显

                    if data.get("role") == "system":
                        print(data["content"])
                        break

                    if data.get("done"):
                        print()
                        break

                    if data.get("error"):
                        print(f"\n错误: {data['error']}")
                        break

                    print(data.get("content", ""), end="", flush=True)

            except KeyboardInterrupt:
                print("\n")
                break


async def main():
    if not await check_health():
        print("\n请先启动Ollama并下载模型:")
        print("  ollama serve")
        print("  ollama pull qwen2.5:7b")
        sys.exit(1)

    args = sys.argv[1:]

    if not args:
        # 无参数 -> 交互模式
        await interactive_mode()
    elif args[0] == "--stream":
        # 流式单次对话
        message = " ".join(args[1:]) if len(args) > 1 else "你好"
        await single_chat(message, stream=True)
    else:
        # 非流式单次对话
        message = " ".join(args)
        await single_chat(message, stream=False)


if __name__ == "__main__":
    asyncio.run(main())
