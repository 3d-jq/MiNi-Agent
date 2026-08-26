"""LLM 客户端单例:统一从 .env 读取配置,所有模块共用这一个 client。"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.getenv("deepseek_api_key"),
    base_url="https://api.deepseek.com",
)