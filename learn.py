"""MiNi Agent 入口文件。

代码已按职责拆分到各模块(config / prompts / llm_client / tools_* /
sub_agent / tool_registry / compaction / agent_loop),本文件只做转发,
保持旧的启动命令不变:python learn.py
"""
import asyncio

from agent_loop import main

if __name__ == "__main__":
    asyncio.run(main())