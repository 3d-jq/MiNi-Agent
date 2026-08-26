"""compress_context 的决策逻辑测试:用假 LLM 替身替换 client.chat.completions.create,
不发真实网络请求,测压缩的 4 条核心行为。

为什么这样测:compress_context 的价值在"什么时候压、摘要不够小怎么办、失败怎么兜底",
这些决策逻辑与 LLM 本身无关;LLM 的真实效果(摘要质量)属于集成测试,不做单测。
"""
import json
from types import SimpleNamespace

import pytest

import compaction
from config import COMPACTION_INSTRUCTION


class FakeCompletions:
    def __init__(self, fake):
        self._fake = fake

    def create(self, **kwargs):
        return self._fake.create(**kwargs)


class FakeClient:
    """假 client:记录每次调用的参数,按设定返回摘要或抛异常。
    结构对齐真 client 的嵌套调用链:client.chat.completions.create(...)"""

    def __init__(self, result):
        self.result = result  # str=正常返回;Exception=模拟调用失败
        self.calls = []
        self.chat = SimpleNamespace(completions=FakeCompletions(self))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.result))]
        )


def make_context(history_messages=6, history_len=300, tail_messages=2):
    """构造: 1 条 system + N 条旧历史 + 尾部 user/assistant。"""
    ctx = [{"role": "system", "content": "SYSTEM_PROMPT"}]
    for i in range(history_messages):
        ctx.append({"role": "user", "content": "字" * history_len + str(i)})
    for i in range(tail_messages):
        ctx.append({"role": "assistant", "content": f"近期的回答{i}"})
    return ctx


def test_compress_short_summary_success(monkeypatch):
    ctx = make_context()
    fake = FakeClient("简短的结构化摘要" * 10)  # ~110 字,远小于历史 ~1800 字
    monkeypatch.setattr(compaction, "client", fake)

    assert compaction.compress_context(ctx) is True

    # 1. 只保留 1 条 system,中间是检查点,tail 原样保留
    assert ctx[0] == {"role": "system", "content": "SYSTEM_PROMPT"}
    assert "<compacted-summary>" in ctx[1]["content"]
    # RETAIN_TAIL_MESSAGES=4 → system(1) + 检查点(1) + tail(4) = 6
    assert len(ctx) == 6
    # tail 的 4 条 = 从第 4 条 user(字…+"4")开始的后续消息,原样保留
    assert [m["content"] for m in ctx[2:]] == [
        "字" * 300 + "4", "字" * 300 + "5",
        "近期的回答0", "近期的回答1",
    ]

    # 2. 确实调用了 LLM,且请求里带压缩指令
    assert len(fake.calls) == 1
    sent = fake.calls[0]["messages"][0]["content"]
    # 历史以 JSON 形式传给模型,压缩指令拼在末尾
    assert sent.startswith("[") and COMPACTION_INSTRUCTION in sent
    assert fake.calls[0]["stream"] is False
    assert fake.calls[0]["model"] == "deepseek-v4-flash"


def test_summary_not_smaller_is_rejected(monkeypatch):
    ctx = make_context(history_messages=3, history_len=300)  # 历史 ~900 字
    fake = FakeClient("假" * 2000)  # 2000 字 > 900 - 500,不够小
    monkeypatch.setattr(compaction, "client", fake)
    snapshot = list(ctx)

    assert compaction.compress_context(ctx) is False
    assert ctx == snapshot  # 拒绝提交时 context 必须原封不动


def test_llm_failure_returns_false_keeps_context(monkeypatch):
    ctx = make_context()
    fake = FakeClient(RuntimeError("网络断了"))
    monkeypatch.setattr(compaction, "client", fake)
    snapshot = list(ctx)

    assert compaction.compress_context(ctx) is False
    assert ctx == snapshot  # 失败兜底:不报错、不动 context


def test_no_history_skips_llm_call(monkeypatch):
    # 只有 1 条 user + 1 条 assistant,不够切(需要保留 >=4)
    ctx = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    fake = FakeClient("x" * 1000)
    monkeypatch.setattr(compaction, "client", fake)

    assert compaction.compress_context(ctx) is False
    assert fake.calls == []  # 关键:历史太少时根本不调用 LLM,省钱


def test_empty_summary_rejected(monkeypatch):
    ctx = make_context()
    fake = FakeClient("   \n  ")  # 全是空白 = 无效摘要
    monkeypatch.setattr(compaction, "client", fake)
    snapshot = list(ctx)

    assert compaction.compress_context(ctx) is False
    assert ctx == snapshot