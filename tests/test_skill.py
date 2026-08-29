"""Skill 系统测试:frontmatter 解析、清单扫描、按需加载、容错、注册一致性。

隔离原则:monkeypatch 把 SKILLS_DIR 指向 pytest 临时目录,
不读写真实 skills/ 目录(避免依赖用户自建技能)。
"""
import os

import pytest

import tools_skill
from tools_skill import list_skills, load_skill

SAMPLE_SKILL = """---
name: test-skill
description: 当测试任务出现时使用。
---

# 测试技能指南

1. 第一步
2. 第二步
"""


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    """把 SKILLS_DIR 指向临时目录,可选预置一个示例技能。"""
    fake = tmp_path / "skills"
    fake.mkdir()
    monkeypatch.setattr(tools_skill, "SKILLS_DIR", str(fake))
    return fake


def make_skill(base, name, content=SAMPLE_SKILL):
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


# ---------- _parse_skill_md ----------

def test_parse_extracts_frontmatter_and_body(skills_dir):
    d = make_skill(skills_dir, "test-skill")
    name, desc, body = tools_skill._parse_skill_md(str(d / "SKILL.md"))
    assert name == "test-skill"
    assert desc == "当测试任务出现时使用。"
    assert "第一步" in body


def test_parse_tolerates_missing_frontmatter(skills_dir):
    d = skills_dir / "plain"
    d.mkdir()
    (d / "SKILL.md").write_text("# 纯正文没有 frontmatter", encoding="utf-8")
    name, desc, body = tools_skill._parse_skill_md(str(d / "SKILL.md"))
    assert name == "plain"            # 回退为目录名
    assert "纯正文" in body


# ---------- list_skills ----------

def test_list_shows_name_and_description(skills_dir):
    make_skill(skills_dir, "test-skill")
    out = list_skills()
    assert "- test-skill: 当测试任务出现时使用。" in out


def test_list_ignores_dirs_without_skill_md(skills_dir):
    make_skill(skills_dir, "good")
    (skills_dir / "empty-dir").mkdir()     # 没有 SKILL.md,应跳过
    out = list_skills()
    assert "test-skill: 当测试任务出现时使用。" in out   # frontmatter 的 name 优先
    assert "empty-dir" not in out


def test_list_empty_dir_returns_empty_string(skills_dir):
    assert list_skills() == ""


def test_list_missing_dir_returns_empty_string(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_skill, "SKILLS_DIR", str(tmp_path / "ghost"))
    assert list_skills() == ""


# ---------- load_skill ----------

def test_load_returns_guided_body(skills_dir):
    make_skill(skills_dir, "test-skill")
    out = load_skill("test-skill")
    assert "【Skill:test-skill】" in out    # 引导语
    assert "第一步" in out                  # 正文


def test_load_missing_reports_available_list(skills_dir):
    make_skill(skills_dir, "test-skill")
    out = load_skill("不存在")
    assert "不存在" in out
    assert "test-skill" in out              # 附上可用清单,模型能自我纠正


# ---------- YAML 兼容(minimax 系技能的写法) ----------

def test_parse_multiline_description(skills_dir):
    """description: > 的 YAML 块标量:后续缩进行合并为一段。"""
    content = (
        "---\nname: mini\ndescription: >\n"
        "  第一行触发词。\n  第二行触发词。\n"
        "---\n# 正文\n"
    )
    make_skill(skills_dir, "mini", content)
    name, desc, body = tools_skill._parse_skill_md(str(skills_dir / "mini" / "SKILL.md"))
    assert name == "mini"
    assert desc == "第一行触发词。 第二行触发词。"
    assert "正文" in body


def test_parse_strips_yaml_quotes(skills_dir):
    content = '---\nname: quoted\ndescription: "带引号的描述"\n---\n正文'
    make_skill(skills_dir, "quoted", content)
    _, desc, _ = tools_skill._parse_skill_md(str(skills_dir / "quoted" / "SKILL.md"))
    assert desc == "带引号的描述"


def test_load_replaces_skill_dir_placeholder(skills_dir):
    """minimax 系技能用 SKILL_DIR 引用自带脚本,加载时必须替换为绝对路径。"""
    content = "---\nname: with-scripts\ndescription: d\n---\n运行 python3 SKILL_DIR/scripts/run.py"
    make_skill(skills_dir, "with-scripts", content)
    out = load_skill("with-scripts")
    assert str(skills_dir / "with-scripts") in out
    assert "SKILL_DIR" not in out


# ---------- 注册表一致性 ----------

def test_load_skill_registered():
    from tool_registry import TOOL_CALL_MAP, TOOL_EMOJI
    assert TOOL_CALL_MAP["load_skill"] is load_skill
    assert TOOL_EMOJI["load_skill"]