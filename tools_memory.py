#记忆工具，支持记忆的追加，删除,加载
import os
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.md")
#记忆加载
def load_memory()->str:
    #判断记忆文件是否存在
    if not  os.path.exists(MEMORY_FILE):
        return ""
    #存在全部读取出来
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return f.read()

#记忆追加保存
def save_memory(content: str, time: str) -> str:
    """追加一条记忆,单行一条(日期+内容)。文件非空且末尾无换行时先补换行。"""
    entry = f"- [{time}]:{content.strip()}\n"
    prefix = ""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            existing = f.read()
        if existing and not existing.endswith("\n"):
            prefix = "\n"            # 上一条没换行,补一个,保证条目各占一行
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(prefix + entry)
    return f"✓ 已记住:{content[:50]}" + ("..." if len(content) > 50 else "")
#记忆清空
def clear_memory() -> str:
    """清空记忆文件。"""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write("")
    return "✓ 记忆已清空"
#编辑记忆
def edit_memory(old_text: str, new_text: str) ->str:
    """编辑记忆:把 old_text 替换为 new_text。要求匹配唯一,防误改其他条目。"""
    if not os.path.exists(MEMORY_FILE):
        return "记忆文件不存在,无可编辑内容"
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    count = text.count(old_text)
    if count == 0:
        return f"没找到包含「{old_text[:50]}」的记忆"
    if count > 1:
        return f"找到 {count} 处匹配,为防误改请引用更长的原文片段(要求唯一)"
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(text.replace(old_text, new_text, 1))
    return f"✓ 已更新记忆:{new_text[:50]}"
#删除包含关键词的记忆条目(整行删除)
def delete_memory(keyword: str) -> str:
    """删除包含关键词的记忆条目(整行删除)。"""
    if not os.path.exists(MEMORY_FILE):
        return "记忆文件不存在,无可删除内容"
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    kept = [line for line in lines if keyword not in line]
    removed = len(lines) - len(kept)
    if removed == 0:
        return f"没找到包含「{keyword[:50]}」的记忆"
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(kept)
    return f"✓ 已删除 {removed} 条记忆"




