"""
本地LLM对话系统 - 配置文件
"""

from pydantic import BaseModel
from typing import Optional


class Config(BaseModel):
    # Ollama 服务地址（本地默认）
    ollama_host: str = "http://localhost:11434"

    # 使用的模型名称（需先通过 ollama pull 下载）
    # 推荐: qwen2.5:7b-instruct (中文能力强，7B适合16GB显存)
    # 备选: qwen2.5:14b-instruct (更强但占用更多显存)
    # 备选: llama3.1:8b-instruct
    model_name: str = "qwen2.5:7b"

    # API 服务配置
    api_host: str = "0.0.0.0"
    api_port: int = 18080

    # 对话参数默认值
    default_temperature: float = 0.7
    default_max_tokens: int = 2048
    default_top_p: float = 0.9

    # 历史记录最大轮数（对话轮次，每轮=用户+助手）
    max_history_turns: int = 20

    # 系统提示词
    system_prompt: str = (
        "你是一个有用、友好的AI助手。"
        "请用简洁清晰的中文回答问题。"
        "如果问题涉及编程，请提供可运行的代码示例。"
        "回答时请保持专业且亲和的态度。"
    )


# 全局单例
config = Config()
