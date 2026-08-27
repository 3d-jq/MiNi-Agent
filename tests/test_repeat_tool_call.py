"""重复工具调用检测(observe_tool_call)测试:连续链、参数归一化、阈值阶梯、重置。

纯逻辑,无网络、无 API。测试会操作 agent_loop 模块级的 _tool_chain 状态,
每个测试用 fixture 先重置,避免测试之间互相污染。
"""
import pytest

import agent_loop


@pytest.fixture(autouse=True)
def reset_chain():
    """每个测试前清空连续链(与 main() 里用户新输入时的重置一致)。"""
    agent_loop._tool_chain["key"] = None
    agent_loop._tool_chain["count"] = 0
    yield


def call(name, args):
    """一次 observe 调用,返回提醒文本或 None。"""
    return agent_loop.observe_tool_call(name, args)


# ---------- 连续链语义 ----------

def test_first_call_no_reminder():
    assert call("read", {"file_path": "a.py"}) is None


def test_repeated_same_call_hits_threshold():
    # 1、2 次无提醒,第 3 次(阈值[0])触发温和提醒
    assert call("read", {"file_path": "a.py"}) is None
    assert call("read", {"file_path": "a.py"}) is None
    reminder = call("read", {"file_path": "a.py"})
    assert reminder is not None
    assert "重复" in reminder


def test_chain_breaks_on_different_tool():
    # 中间换了工具,连续链断裂,计数重置
    call("read", {"file_path": "a.py"})
    call("read", {"file_path": "a.py"})
    call("grep", {"file_path": "a.py", "pattern": "x"})  # 打断链
    assert call("read", {"file_path": "a.py"}) is None     # 重新从 1 计数


def test_chain_breaks_on_different_args():
    # 同一工具但参数不同,同样打断链
    call("read", {"file_path": "a.py"})
    call("read", {"file_path": "a.py"})
    call("read", {"file_path": "b.py"})   # 参数变了
    assert call("read", {"file_path": "a.py"}) is None


# ---------- 参数归一化 ----------

def test_args_key_ignores_property_order():
    # 参数顺序不同应视为同一调用(write a=1,b=2 与 b=2,a=1 相同)
    assert call("write", {"content": "x", "file_path": "f.txt"}) is None
    assert call("write", {"file_path": "f.txt", "content": "x"}) is None
    reminder = call("write", {"content": "x", "file_path": "f.txt"})
    assert reminder is not None


# ---------- 阈值阶梯 ----------

def test_threshold_ladder_3_5_8():
    # 第 3 次温和提醒,第 4 次无,第 5 次详细提醒,第 6-7 无,第 8 次详细提醒
    for i in range(1, 9):
        reminder = call("bash", {"command": "dir"})
        if i == 3:
            assert reminder is not None
            assert "重复" in reminder and "连续次数" not in reminder   # 温和版:无结构化详情
        elif i in (5, 8):
            assert reminder is not None and "连续次数" in reminder     # 详细版:点名工具/次数
        else:
            assert reminder is None


def test_reminder_includes_tool_name_and_count():
    # 温和提醒(第 3 次)不含结构化字段;详细版(第 5 次)才含工具名和次数
    call("bash", {"command": "dir"})
    call("bash", {"command": "dir"})
    call("bash", {"command": "dir"})   # 第 3 次:温和
    call("bash", {"command": "dir"})   # 第 4 次:无
    reminder = call("bash", {"command": "dir"})  # 第 5 次:详细
    assert reminder is not None
    assert "bash" in reminder and "连续次数" in reminder and "5" in reminder


# ---------- 重置(与用户新输入场景一致) ----------

def test_manual_reset_clears_chain():
    call("read", {"file_path": "a.py"})
    call("read", {"file_path": "a.py"})
    agent_loop._tool_chain["count"] = 0   # main() 里用户新输入做的重置
    assert call("read", {"file_path": "a.py"}) is None


# ---------- 与 run_tools_parallel 的集成 ----------

def test_parallel_integration_reminder_appended(monkeypatch):
    """连续 3 次相同调用,第 3 次的工具结果里应带 ⚠️ 提醒。"""
    import asyncio
    import time
    from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI

    def fake_read(file_path, start_line=1, max_lines=200, encoding="utf-8"):
        return "内容:" + file_path

    monkeypatch.setitem(TOOL_CALL_MAP, "read", fake_read)
    TOOL_EMOJI.setdefault("read", "📄")

    def tc(i):
        return {"id": f"id{i}", "function": {"name": "read", "arguments": '{"file_path": "a.py"}'}}

    calls = {i: tc(i) for i in range(4)}
    results = asyncio.run(agent_loop.run_tools_parallel(calls))
    assert results["id0"] == "内容:a.py"      # 第 1 次:正常
    assert results["id2"].endswith("内容:a.py") or "内容:a.py" in results["id2"]  # 第 3 次:仍执行
    assert "⚠️" in results["id2"]             # 但带了提醒