"""文件操作工具:read / grep / write / edit / glob / list_dir。"""
import os
import pathlib
import re


# 工具类
class ReadTool:
    def execute(self, file_path, offset, limit, encoding):
        with open(file_path, "r", encoding=encoding) as f:
            lines = f.readlines()
        end = min(offset - 1 + limit, len(lines)) if limit else len(lines)
        return "".join(lines[offset - 1:end])


# 单例实例化
_read_tool = ReadTool()


# 工具-读工具
def read(file_path: str, start_line: int = 1, max_lines: int = 200, encoding: str = "utf-8") -> str:
    try:
        result = _read_tool.execute(file_path=file_path, offset=start_line, limit=max_lines, encoding=encoding)
        return result
    except FileNotFoundError:
        return f"文件不存在：{file_path}，请检查路径是否正确"
    except PermissionError:
        return f"没有权限读取：{file_path}"
    except IsADirectoryError:
        return f"{file_path} 是目录不是文件"
    except UnicodeDecodeError:
        return f"文件编码不是 {encoding}，试试 encoding='gbk' 或 'utf-8-sig'"
    except (OSError, UnicodeDecodeError) as e:
        return f"读取失败：{type(e).__name__}: {e}"


# 工具-查工具
def grep(file_path: str, pattern: str, max_results: int = 50, ignore_case: bool = False) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        flags = re.IGNORECASE if ignore_case else 0
        rx = re.compile(pattern, flags)

        hits = [
            (i + 1, line.rstrip())  # 1-based 行号
            for i, line in enumerate(lines)
            if rx.search(line)
        ]

        if not hits:
            return f"在 {file_path} 里没找到匹配「{pattern}」"

        total = len(hits)
        shown = hits[:max_results]
        out_lines = [f"行 {n}: {l}" for n, l in shown]
        result = "\n".join(out_lines)

        # 元信息:让 LLM 知道还剩多少
        meta = f"[共找到 {total} 处匹配,显示前 {len(shown)} 处]"
        if total > max_results:
            meta += (
                f"\n[还有 {total - max_results} 处未显示,"
                f"可缩小 pattern 或增大 max_results 继续搜]"
            )
        return meta + "\n\n---\n" + result

    except FileNotFoundError:
        return f"文件不存在：{file_path}"
    except PermissionError:
        return f"没有权限读取：{file_path}"
    except re.error as e:
        return f"正则表达式错误：{e}"
    except Exception as e:
        return f"搜索失败：{type(e).__name__}: {e}"


# 工具-写入工具
def write(file_path: str, content: str, encoding: str = "utf-8", create_parents: bool = True):
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✓ 已写入 {file_path}（{len(content)} 字符）"
    except PermissionError:
        return f"没有权限写入:{file_path}"
    except IsADirectoryError:
        return f"{file_path} 是目录,不是文件"
    except Exception as e:
        return f"写入失败:{type(e).__name__}: {e}"


# 工具-替换工具
def edit(file_path: str, search_text: str, new_text: str, replace_all: bool = False, dry_run: bool = False):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(search_text)
        if count == 0:
            return (
                f"没找到这段文本:\n---\n{search_text}\n---\n"
                f"请确认 search_text 跟文件里的一致(含空格/缩进/换行)"
            )

        if count > 1 and not replace_all:
            return (
                f"找到 {count} 处匹配,但 replace_all=False\n"
                f"为防止误改,默认要求唯一。要全部替换传 replace_all=True"
            )

        if dry_run:
            return f"[干跑] 将会替换 {count} 处,文件未修改"

        new_content = (
            content.replace(search_text, new_text)
            if replace_all
            else content.replace(search_text, new_text, 1)
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"✓ 已替换 {count} 处"

    except FileNotFoundError:
        return f"文件不存在:{file_path}"
    except PermissionError:
        return f"没有权限:{file_path}"
    except Exception as e:
        return f"替换失败:{type(e).__name__}: {e}"


# 配备格式工具
def glob(pattern: str, base_dir: str = ".", max_results: int = 100):
    """列出匹配通配符模式的文件路径"""
    try:
        base = pathlib.Path(base_dir)
        if not base.exists():
            return f"目录不存在:{base_dir}"
        if not base.is_dir():
            return f"{base_dir} 不是目录"

        # pathlib 的 glob:** 表示递归任意层级
        matches = sorted(base.glob(pattern))
        # 只要文件,不要目录本身
        matches = [m for m in matches if m.is_file()]

        if not matches:
            return f"在 {base_dir} 里没找到匹配「{pattern}」的文件"

        total = len(matches)
        shown = matches[:max_results]
        # 相对路径更易读
        out = "\n".join(str(m.relative_to(base)) for m in shown)

        meta = f"[共找到 {total} 个文件,显示前 {len(shown)} 个]"
        if total > max_results:
            meta += (
                f"\n[还有 {total - max_results} 个未显示,"
                f"可缩小 pattern(如 *.py → test_*.py)或增大 max_results]"
            )
        return meta + "\n\n---\n" + out

    except Exception as e:
        return f"搜索失败:{type(e).__name__}: {e}"


def list_dir(dir_path: str):
    """列出目录下的文件和子目录"""
    try:
        p = pathlib.Path(dir_path)
        if not p.exists():
            return f"路径不存在:{dir_path}"
        if not p.is_dir():
            return f"{dir_path} 不是目录"

        dirs = sorted([e.name for e in p.iterdir() if e.is_dir()])
        files = sorted([e.name for e in p.iterdir() if e.is_file()])

        if not dirs and not files:
            return f"{dir_path} 是空目录"

        out = [f"目录:{dir_path}", ""]
        for d in dirs:
            out.append(f"  📁 {d}/")
        for f in files:
            out.append(f"    {f}")
        return "\n".join(out)

    except PermissionError:
        return f"没有权限读取:{dir_path}"
    except Exception as e:
        return f"读取失败:{type(e).__name__}: {e}"