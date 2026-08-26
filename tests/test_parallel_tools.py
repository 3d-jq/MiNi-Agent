"""并行工具执行测试:不真调 LLM,用假工具验证 run_tools_parallel 的并发语义。"""
import asyncio
import time

import pytest

from agent_loop import run_tools_parallel


def make_registry(monkeypatch, calls_log):
    """构造一个临时的 TOOL_CALL_MAP / TOOL_EMOJI,记录每个工具被调用的时刻。"""
    def slow_a():
        calls_log.append(("a", time.monotonic()))
        time.sleep(0.3)
        return "A"

    def slow_b():
        calls_log.append(("b", time.monotonic()))
        time.sleep(0.3)
        return "B"

    def boom(x):
        raise ValueError(f"bad x={x}")

    from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI

    monkeypatch.setitem(TOOL_CALL_MAP, "slow_a", slow_a)
    monkeypatch.setitem(TOOL_CALL_MAP, "slow_b", slow_b)
    monkeypatch.setitem(TOOL_CALL_MAP, "boom", boom)
    TOOL_EMOJI.setdefault("slow_a", "🅰")
    TOOL_EMOJI.setdefault("slow_b", "🅱")
    TOOL_EMOJI.setdefault("boom", "💥")


def tool_call(i, name, args_json):
    return {"id": f"id{i}", "function": {"name": name, "arguments": args_json}}


def test_results_mapped_by_id(monkeypatch):
    calls = []
    make_registry(monkeypatch, calls)
    tc = {
        0: tool_call(0, "slow_a", "{}"),
        1: tool_call(1, "boom", '{"x": 42}'),
    }
    results = asyncio.run(run_tools_parallel(tc))
    assert results["id0"] == "A"
    assert results["id1"].startswith("工具 boom 执行出错") and "ValueError" in results["id1"]


def test_calls_run_concurrently(monkeypatch):
    # 若为串行:0.3 + 0.3 = 0.6s+;并发应 < 0.5s
    calls = []
    make_registry(monkeypatch, calls)
    tc = {0: tool_call(0, "slow_a", "{}"), 1: tool_call(1, "slow_b", "{}")}
    t0 = time.monotonic()
    asyncio.run(run_tools_parallel(tc))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.55, f"疑似串行执行:{elapsed:.2f}s"


def test_single_failure_does_not_kill_others(monkeypatch):
    calls = []
    make_registry(monkeypatch, calls)
    tc = {
        0: tool_call(0, "boom", '{"x": 1}'),
        1: tool_call(1, "slow_a", "{}"),
        2: tool_call(2, "slow_b", "{}"),
    }
    results = asyncio.run(run_tools_parallel(tc))
    assert len(results) == 3                 # 三个都有结果
    assert results["id1"] == "A"             # 好的两个正常返回
    assert "出错" in results["id0"]          # 坏的只影响自己


def test_unknown_tool_reported(monkeypatch):
    make_registry(monkeypatch, [])
    tc = {0: tool_call(0, "no_such_tool", "{}")}
    results = asyncio.run(run_tools_parallel(tc))
    assert "未知工具" in results["id0"]


def test_is_async_native():
    # run_tools_parallel 必须是协程函数(asyncio.run 只接受协程)
    assert asyncio.iscoroutinefunction(run_tools_parallel)
