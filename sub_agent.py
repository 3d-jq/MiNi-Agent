"""子代理工具:拥有独立上下文的静默工作循环,完成后把结论返回主代理。

注意:sub_agent 在函数体内 import tool_registry(tools/TOOL_CALL_MAP),
而不是模块顶部 —— 因为 tool_registry 反过来要导入 sub_agent 做注册,
顶部互导会形成循环依赖。函数内 import 利用 Python 的 import 缓存,零开销。
"""
import json

from config import MODEL_NAME
from llm_client import client


def sub_agent(task: str, max_turns: int = 20):
    from tool_registry import TOOL_CALL_MAP, tools  # 循环依赖在此打破

    sub_context = [
        {"role": "system", "content": "你是一个 general subaagent"},
        {"role": "user", "content": task},
    ]
    for _ in range(max_turns):  # 轮数上限,防死循环
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, temperature=0.5,
                messages=sub_context, reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                stream=True, tools=tools,
            )
        except Exception as e:
            return f"子代理出错:{type(e).__name__}: {e}"

        # 收集这一轮的回答和工具调用(和 mini_agent_loop 相同,但静默:不 print)
        content = ""
        current_tool_calls = {}
        for chunk in response:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content += delta.content
            for tc in (delta.tool_calls or []):
                idx = tc.index
                current_tool_calls.setdefault(idx, {"id": "", "function": {"name": "", "arguments": ""}})
                if tc.id:
                    current_tool_calls[idx]["id"] = tc.id
                if tc.function and tc.function.name:
                    current_tool_calls[idx]["function"]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        if not current_tool_calls:  # 子代理给出最终答案,返回给主代理
            return f"【子代理完成】{content}"

        sub_context.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {"id": v["id"], "type": "function",
                 "function": {"name": v["function"]["name"], "arguments": v["function"]["arguments"]}}
                for v in current_tool_calls.values()
            ],
        })
        for v in current_tool_calls.values():
            name = v["function"]["name"]
            args = json.loads(v["function"]["arguments"] or "{}")
            if name == "sub_agent":  # 挡掉嵌套委派,防递归
                result = "子代理不允许再次委派,请自己完成任务。"
            else:
                fn = TOOL_CALL_MAP.get(name)
                result = fn(**args) if fn else f"未知工具:{name}"
            sub_context.append({"role": "tool", "tool_call_id": v["id"], "content": str(result)})
    return f"【子代理】{max_turns} 轮内未完成,最后内容:{content[:500]}"