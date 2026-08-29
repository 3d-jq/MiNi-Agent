"""记忆系统测试:load/save/clear 读写行为 + system prompt 注入逻辑。

隔离原则:所有测试通过 monkeypatch 把 tools_memory.MEMORY_FILE 指向 pytest
临时目录,绝不读写真实的 memory.md(里面可能有用户隐私数据)。
"""
import pytest

import tools_memory
from tools_memory import clear_memory, delete_memory, edit_memory, load_memory, save_memory


@pytest.fixture
def memory_file(tmp_path, monkeypatch):
    """把 MEMORY_FILE 指到临时文件,测试结束自动清理。"""
    fake = tmp_path / "memory.md"
    monkeypatch.setattr(tools_memory, "MEMORY_FILE", str(fake))
    return fake


# ---------- load_memory ----------

def test_load_returns_empty_when_file_missing(memory_file):
    assert not memory_file.exists()
    assert load_memory() == ""          # 不存在 → 空串(让"有记忆才注入"生效)


def test_load_returns_content_when_file_exists(memory_file):
    memory_file.write_text("- [2026-08-29] 用户是四川人", encoding="utf-8")
    assert "四川人" in load_memory()


# ---------- save_memory ----------

def test_save_appends_with_time(memory_file):
    msg = save_memory("用户是四川人", time="2026-08-29")
    assert "已记住" in msg
    text = memory_file.read_text(encoding="utf-8")
    assert "- [2026-08-29]:" in text          # 带日期标注
    assert "用户是四川人" in text


def test_save_is_append_not_overwrite(memory_file):
    save_memory("第一条", time="2026-08-29")
    save_memory("第二条", time="2026-08-29")
    text = memory_file.read_text(encoding="utf-8")
    assert "第一条" in text and "第二条" in text   # 两条都在 = 追加语义


def test_save_long_content_truncated_in_message(memory_file):
    msg = save_memory("长" * 100, time="2026-08-29")
    assert "..." in msg                        # 返回提示截断
    assert "长" * 100 in memory_file.read_text(encoding="utf-8")  # 但文件存全文


# ---------- clear_memory ----------

def test_clear_empties_file(memory_file):
    save_memory("会被清掉", time="2026-08-29")
    clear_memory()
    assert memory_file.read_text(encoding="utf-8") == ""
    assert load_memory() == ""


def test_clear_on_missing_file_creates_empty(memory_file):
    clear_memory()                             # 文件不存在也能安全清空
    assert memory_file.exists() and load_memory() == ""


# ---------- system prompt 注入集成 ----------

def test_prompt_includes_memory_when_present(memory_file, monkeypatch):
    memory_file.write_text("- [2026-08-29] 用户是四川人", encoding="utf-8")
    from prompts import build_system_prompt
    prompt = build_system_prompt()
    assert "<memory>" in prompt
    assert "四川人" in prompt                  # 记忆内容进了 system prompt
    assert "已知背景" in prompt                # 带引导语


def test_prompt_omits_memory_block_when_empty(memory_file):
    from prompts import build_system_prompt
    prompt = build_system_prompt()
    assert "<memory>" not in prompt            # 无记忆时整块不输出


# ---------- edit_memory ----------

def test_edit_replaces_unique_match(memory_file):
    save_memory("用户是四川人", time="2026-08-29")
    msg = edit_memory("四川人", "重庆人")
    assert "已更新" in msg
    text = load_memory()
    assert "重庆人" in text and "四川人" not in text


def test_edit_no_match_message(memory_file):
    save_memory("用户是四川人", time="2026-08-29")
    assert "没找到" in edit_memory("不存在的文本", "x")
    assert "四川人" in load_memory()          # 文件未动


def test_edit_refuses_multiple_matches(memory_file):
    save_memory("喜欢 Python", time="2026-08-29")
    save_memory("喜欢 Rust", time="2026-08-29")
    before = load_memory()
    msg = edit_memory("喜欢", "热爱")          # 两处匹配
    assert "2 处匹配" in msg                   # 拒绝并提示
    assert load_memory() == before             # 文件必须原样


def test_edit_on_missing_file(memory_file):
    assert "不存在" in edit_memory("a", "b")


# ---------- delete_memory ----------

def test_delete_removes_matching_line_only(memory_file):
    save_memory("用户是四川人", time="2026-08-29")
    save_memory("用户喜欢 Python", time="2026-08-29")
    msg = delete_memory("四川")
    assert "已删除 1 条记忆" in msg
    text = load_memory()
    assert "四川人" not in text
    assert "Python" in text                    # 其他记忆保留


def test_delete_no_match_keeps_file(memory_file):
    save_memory("用户是四川人", time="2026-08-29")
    assert "没找到" in delete_memory("不存在的关键词")
    assert "四川人" in load_memory()


def test_delete_on_missing_file(memory_file):
    assert "不存在" in delete_memory("a")


def test_delete_all_then_load_empty(memory_file):
    save_memory("A 条目", time="2026-08-29")
    save_memory("B 条目", time="2026-08-29")
    delete_memory("A 条目")
    delete_memory("B 条目")
    assert load_memory() == ""


# ---------- 注册表一致性(编辑/删除) ----------

# ---------- 注册表一致性 ----------

def test_memory_tools_registered():
    from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI
    assert TOOL_CALL_MAP["save_memory"] is save_memory
    assert TOOL_CALL_MAP["clear_memory"] is clear_memory
    assert TOOL_EMOJI["save_memory"]
    assert TOOL_EMOJI["clear_memory"]


def test_edit_delete_memory_registered():
    from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI
    assert TOOL_CALL_MAP["edit_memory"] is edit_memory
    assert TOOL_CALL_MAP["delete_memory"] is delete_memory
    assert TOOL_EMOJI["edit_memory"]
    assert TOOL_EMOJI["delete_memory"]