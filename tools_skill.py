import os

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")

def _parse_skill_md(path: str):
    """解析 SKILL.md:返回 (name, description, 正文)。
    支持 YAML 块标量(description: > 多行折叠)与引号剥离;无 frontmatter 时回退目录名。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        parts = text.split("---", 2)          # ['', 'frontmatter', '正文']
        name, desc_lines, in_desc = "", [], False
        for line in parts[1].splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
                in_desc = False
            elif line.startswith("description:"):
                val = line.split(":", 1)[1].strip()
                if val in (">", ">-", "|", "|-"):   # YAML 块标量:后续缩进行是内容
                    in_desc, desc_lines = True, []
                else:
                    desc_lines, in_desc = [val], False
            elif in_desc and line[:1] in (" ", "\t") and line.strip():
                desc_lines.append(line.strip())     # 收集多行描述
            else:
                in_desc = False
        desc = " ".join(desc_lines).strip().strip('"').strip("'")
        return name, desc, parts[2].strip()
    return os.path.basename(os.path.dirname(path)), "", text   # 回退:目录名
def list_skills() -> str:
    """扫描 skills 目录,返回"名称: 描述"清单(注入 system prompt,轻量)。"""
    if not os.path.isdir(SKILLS_DIR):
        return ""
    out = []
    for d in sorted(os.listdir(SKILLS_DIR)):
        skill_md = os.path.join(SKILLS_DIR, d, "SKILL.md")
        if os.path.isfile(skill_md):
            name, desc, _ = _parse_skill_md(skill_md)
            out.append(f"- {name or d}: {desc}")
    return "\n".join(out)
def load_skill(name: str) -> str:
    """按名称加载 skill 全文;SKILL_DIR 替换为绝对路径,并告知资源根目录。"""
    skill_dir = os.path.join(SKILLS_DIR, name)
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(path):
        return f"skill「{name}」不存在。可用技能:\n{list_skills() or '(无)'}"
    _, _, body = _parse_skill_md(path)
    body = body.replace("SKILL_DIR", skill_dir)   # minimax 系技能用它引用自带脚本
    return (f"【Skill:{name}】已加载。\n"
            f"本技能资源根目录(指南中出现的 scripts/、references/、templates/ 等相对路径都基于它):\n"
            f"{skill_dir}\n\n"
            f"请严格按以下指南执行:\n\n{body}")
