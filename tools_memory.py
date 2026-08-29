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

#记忆追加
def save_memory(content: str, time:str)->str:
    """追加一条记忆,带日期。"""
    entry = f"\n- [{time}]:\n{content.strip()}"
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    return f"✓ 已记住:{content[:50]}" + ("..." if len(content) > 50 else "")
#记忆清空
def clear_memory() -> str:
    """清空记忆文件。"""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write("")
    return "✓ 记忆已清空"





