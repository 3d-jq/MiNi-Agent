"""上下文压缩系统:token 估算、安全切点查找、LLM 结构化摘要。

设计要点(参考 deepseek-harness):
1. 只在 user 消息边界切割,不拆散 tool_calls/tool 结果对;
2. 摘要必须显著小于被替换内容(MIN_SAVING_CHARS),否则拒绝提交;
3. system 提示词永远保留;失败时不动 context(原对话继续可用)。
"""
import json

from config import COMPACTION_INSTRUCTION, MIN_SAVING_CHARS, MODEL_NAME, RETAIN_TAIL_MESSAGES, SUMMARY_MAX_TOKENS
from llm_client import client


def est_tokens(messages) -> int:
    """粗估消息列表的 token 数(中文约 1 字/token,英文约 4 字符/token,取保守值)。"""
    total = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "", ensure_ascii=False)) for m in messages)
    return total


def find_safe_cut(messages, tail_msgs: int):
    """找到安全切割点:尾部保留 tail_msgs 条,且切口必须落在 user 消息头部
    (每轮从 user 开始,tool_calls/tool 结果天然同轮自包含,不会拆散工具对)。
    返回切割索引 cut(≈len-tail_msgs 但向前调整),找不到返回 None。"""
    cut = max(len(messages) - tail_msgs, 1)
    while cut > 1 and messages[cut].get("role") != "user":
        cut -= 1
    return cut if cut > 1 else None


def compress_context(context: list) -> bool:
    """用大模型把旧的轮次压缩成结构化检查点。成功就地修改 context 并返回 True。"""
    system = [m for m in context if m["role"] == "system"]
    rest = [m for m in context if m["role"] != "system"]
    cut = find_safe_cut(rest, RETAIN_TAIL_MESSAGES)
    if cut is None:
        print("可压缩的历史太少,跳过", flush=True)
        return False

    history, tail = rest[:cut], rest[cut:]
    history_chars = sum(len(str(m.get("content") or "")) for m in history)
    print(f"\n🗜️ 压缩中:{cut} 条旧消息(约 {history_chars} 字符)→ 结构化摘要...", flush=True)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.3,
            messages=[
                {"role": "user", "content":
                    json.dumps(history, ensure_ascii=False)
                    + "\n\n" + COMPACTION_INSTRUCTION},
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            stream=False,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"⚠️ 摘要调用失败,本轮不压缩:{type(e).__name__}: {e}", flush=True)
        return False

    # 防"越压越大":摘要没比原文明显小就拒绝提交
    if not summary or len(summary) > history_chars - MIN_SAVING_CHARS:
        print(f"⚠️ 摘要({len(summary)} 字符)不够小于原文({history_chars} 字符),放弃压缩", flush=True)
        return False

    context[:] = system + [
        {"role": "user", "content":
            "【自动生成的对话检查点:以下浓缩了更早阶段的全部关键事实,视为既定背景,直接在此基础上继续。】\n\n<compacted-summary>\n"
            + summary + "\n</compacted-summary>"},
    ] + tail
    print(f"✅ 压缩完成:{history_chars} 字符 → {len(summary)} 字符(保留最近 {len(tail)} 条)", flush=True)
    return True