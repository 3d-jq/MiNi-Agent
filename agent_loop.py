"""Agent 主循环:会话状态(context)、并行工具执行层、对话循环与 CLI 入口。"""
import asyncio
import json

from compaction import compress_context
from config import CONTEXT_WINDOW, MODEL_NAME, THRESHOLD_RATIO
from llm_client import client
from prompts import build_system_prompt
from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI, tools

from rich.live import Live
from rich.console import Console
from rich.markdown import Markdown

import shutil  # 顶部 import 区加

console = Console()
# 上下文(会话全局状态,system prompt 固定在前,历史严格追加式以保 KV 缓存命中)
context = [{"role": "system", "content": build_system_prompt()}]
#
REPEAT_THRESHOLDS = [3, 5, 8]          # 升序阶梯,hits 即提醒
_tool_chain = {"key": None, "count": 0}
def observe_tool_call(name: str, args: dict):
    """连续重复检测:与上次相同则+1,不同则重置。命中阈值返回提醒文本,否则 None。"""
    key = json.dumps([name, json.dumps(args, sort_keys=True, ensure_ascii=False)], ensure_ascii=False)
    if _tool_chain["key"] == key:
        _tool_chain["count"] += 1
    else:
        _tool_chain["key"], _tool_chain["count"] = key, 1

    count = _tool_chain["count"]
    if count not in REPEAT_THRESHOLDS:
        return None
    if count == REPEAT_THRESHOLDS[0]:  # 温和提醒
        return ("你在用完全相同的参数重复调用同一个工具。调用前仔细分析上一次的结果:"
                "若任务未完成,换一种方法或换参数,而不是重复同一调用。")
    return (f"检测到重复工具调用:\n- tool: {name}\n- 连续次数: {count}\n"
            f"- 参数: {str(args)[:500]}\n"   # 展示截断,防大参数撑爆上下文
            "这些重复调用没有产生进展,不要再用完全相同参数调用该工具。"
            "查看最近一次结果,选不同动作/参数,证据足够就结束任务。")
async def run_tools_parallel(tool_calls: dict) -> dict:
    """并行执行一批工具调用,返回 {tool_call_id: 结果文本}。单个工具失败不影响其它工具。"""
    async def one(v):
        name = v["function"]["name"]
        args = json.loads(v["function"]["arguments"] or "{}")
        print(f"\n调用工具: {TOOL_EMOJI.get(name, '?')}{name}", flush=True)
        fn = TOOL_CALL_MAP.get(name)
        if not fn:
            result = f"未知工具:{name}"
        else:
            try:
                result = str(await asyncio.to_thread(fn, **args))
            except Exception as e:  # 单个工具炸了,只影响它自己,其它照跑
                result = f"工具 {name} 执行出错:{type(e).__name__}: {e}"
        # 连续重复检测(执行后计数——成功/失败/未知工具都计入)
        reminder = observe_tool_call(name, args)
        if reminder:
            result += "\n\n⚠️ " + reminder  # 提醒拼进工具结果,模型下一轮自然看到
        return v["id"], result

    results = await asyncio.gather(*(one(v) for v in tool_calls.values()))
    return dict(results)

async def mini_agent_loop(question, model_name):
    """调用模型。reasoner 会返回思考过程 + 最终答案。"""
    while True:
        try:
            response = client.chat.completions.create(
                model=model_name,
                temperature=0.5,
                messages=context,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                stream=True,
                tools=tools,
                stream_options={"include_usage": True},
            )
            print_thinking_header = True  # 还没打过思考标题
            print_answering_header =True# 回答标题是否已打
            content = ""
            current_tool_calls = {}  # 字典记录大模型工具调用信息
            last_usage = None
            live = None  # 回答开始后才创建 Live,避免与 thinking 的 print 冲突
            for chunk in response:
                # 收集 token 用量:只有最后一个块带 usage,其余块都是 None
                if getattr(chunk, "usage", None):
                    last_usage = chunk.usage
                # 有些 provider 的 usage 块 choices 是空的,跳过防止下面 [0] 越界
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                ans = getattr(delta, "content", None)
                think = getattr(delta, "reasoning_content", None)

                if think:
                    if print_thinking_header:
                        print("\n🧠 深度思考", end="\n", flush=True)
                        print_thinking_header = False
                    print(think, end="", flush=True)
                for tc in (delta.tool_calls or []):
                    idx = tc.index
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": "",
                            "function": {"name": "", "arguments": ""}
                        }
                    if tc.id:
                        current_tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        current_tool_calls[idx]["function"]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                if ans:  # 回答用 markdown 流式渲染,不 print
                    if print_answering_header:
                        print("\n\n💬 认真回答：", end="\n", flush=True)
                        print_answering_header = False
                    if live is None:
                        live = Live(Markdown(""), refresh_per_second=12, console=console)
                        live.start()
                    content += ans
                    live.update(Markdown(content))  # ← 每次更新,Live 内部 12Hz 节流

                    # ← 收尾移到 for 循环【外】:所有块处理完才 stop
            if live is not None:
                live.stop()
                console.print("")  # 保证后续输出换行
            # 达到 80% 窗口阈值 → 主动压缩(参考 harness 的 pressure 触发)
            if last_usage and getattr(last_usage, "prompt_tokens", 0) >= int(CONTEXT_WINDOW * THRESHOLD_RATIO):
                compress_context(context)
            if not current_tool_calls:
                context.append({"role": "assistant", "content": content})
                width = shutil.get_terminal_size().columns
                print("-" * width)
                if last_usage:
                    print(f"[tokens详情] 总tokens:{last_usage.total_tokens}   命中缓存: {last_usage.prompt_cache_hit_tokens / last_usage.prompt_tokens * 100:.1f}%   上下文窗口详情: {last_usage.prompt_tokens / 10000:.1f}万/100万({last_usage.prompt_tokens / 1_000_000:.1%})", flush=True)
                return

            context.append({  # 模型说要调啥工具放在上下文里
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {"id": v["id"], "type": "function",
                     "function": {"name": v["function"]["name"], "arguments": v["function"]["arguments"]}}
                    for v in current_tool_calls.values()
                ],
            })

            # 并行执行所有工具,按 id 对应回填
            results = await run_tools_parallel(current_tool_calls)
            for v in current_tool_calls.values():
                context.append({
                    "role": "tool",
                    "tool_call_id": v["id"],
                    "content": results[v["id"]],
                })
        except Exception as e:
            return f"Error: {e}"


async def main():
    width = shutil.get_terminal_size().columns
    print("-" * width)
    banner = f"MiNi Agent | 模型:{MODEL_NAME} | 工作区:{123}"
    print(f"{banner:^{width}}")
    print("-" * width, end=" ")
    while True:
        print("\n")
        question = input(">:").strip()
        if not question:
            continue
        _tool_chain["count"] = 0  # 用户新输入打断"连续"语义,跨问话不算循环
        context.append({"role": "user", "content": question})
        await mini_agent_loop(question, MODEL_NAME)


if __name__ == "__main__":
    asyncio.run(main())