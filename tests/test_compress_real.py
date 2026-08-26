"""真实 LLM 集成测试:用真实 DeepSeek API 验证压缩整体链路。

与 test_compress_context.py(FakeClient 测决策逻辑)互补:
- 这里测的是「真实模型真的会按 8 节结构生成摘要」;
- 断言只测结构不测内容(真实模型输出不稳定,不能断言具体文字)。

默认跳过:会花 API 费用、依赖 .env 中的 key。
启用方式:RUN_REAL_LLM_TESTS=1 python -m pytest tests/test_compress_real.py -v
"""
import os

import pytest

import compaction

REAL = os.getenv("RUN_REAL_LLM_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not REAL,
    reason="真实 LLM 集成测试会调用 API,设 RUN_REAL_LLM_TESTS=1 启用",
)


def make_rich_context():
    """构造一段包含多轮问答与工具结果的历史(模拟真实长对话,历史远大于摘要)。"""
    ctx = [{"role": "system", "content": "SYSTEM_PROMPT"}]
    ctx.append({"role": "user", "content": "帮我调研 asyncio.to_thread 的并发模型,重点看它与线程池的关系"})
    ctx.append({"role": "assistant", "content": "好的,我先搜索资料再整理。"})
    # 工具结果模拟真实场景的一长段输出(数千字符,否则摘要会比原文长被保护机制拒绝)
    ctx.append({"role": "tool", "content": (
        "asyncio.to_thread 是 Python 3.9 新增的异步函数,内部使用默认线程池执行器(ThreadPoolExecutor),"
        "适用于 IO 密集任务。它与直接使用 ThreadPoolExecutor 的区别在于:to_thread 更简洁,"
        "每个调用自动提交一个任务;而 ThreadPoolExecutor 可以复用线程池、控制 max_workers、"
        "提交多个任务后统一 result()。gather 用于并发等待多个协程,按传入顺序返回结果,"
        "其中一个失败会传播。\n" + "补充资料：" + "详情" * 3000
    )})
    ctx.append({"role": "user", "content": "顺便比较与 ThreadPoolExecutor 的适用场景差异,还有 gather 的用法"})
    ctx.append({"role": "assistant", "content": (
        "to_thread 更简洁但每次新建任务;ThreadPoolExecutor 可复用池。gather 用于并发等待多个协程。"
        + "具体来说:" + "要点" * 300
    )})
    ctx.append({"role": "user", "content": "最近的消息(不应被压缩)"})
    ctx.append({"role": "assistant", "content": "这是最近回答"})
    return ctx


def test_real_compression_produces_structured_summary():
    ctx = make_rich_context()
    ok = compaction.compress_context(ctx)
    assert ok is True, "真实调用下压缩应该成功"

    # —— 结构断言(真实模型只测结构,不测具体文字) ——
    assert ctx[0]["role"] == "system"  # system 永远保留
    checkpoint = ctx[1]["content"]
    assert checkpoint.startswith("【自动生成的对话检查点")
    assert "<compacted-summary>" in checkpoint

    # 尾部原样保留:最后一条是最近回答
    assert ctx[-1]["content"] == "这是最近回答"

    # 摘要正文包含 8 节结构中的核心小节
    body = checkpoint.split("<compacted-summary>")[1].split("</compacted-summary>")[0]
    for section in ["用户请求与意图", "关键技术概念", "当前工作", "下一步"]:
        assert section in body, f"摘要缺少小节:{section}"