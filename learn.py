# 导入 OpenAI 兼容 SDK（DeepSeek 用 OpenAI 协议）
import asyncio
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import os
import requests
import json
from bs4 import BeautifulSoup
import re
import pathlib
import subprocess
load_dotenv()
client = OpenAI(
    api_key=os.getenv("deepseek_api_key"),
    base_url="https://api.deepseek.com",
)

#提示词xlm化提示词---固定编排提示词---提高命中缓存效果
def build_system_prompt() -> str:
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    return f"""
    <role>MiNi Agent</role>
    <identity>一个全能的CLI 编程助手</identity> # CLI 编程助手
    <mission>帮助用户完成软件工程任务</mission>
    <capabilities>
        <item>回答解决各种编程问题</item>
        <item>你可以并发使用工具</item>
        <item>面对大问题可以使用子代理来协助完成任务</item>
    </capabilities>
     <rules>
        <rule priority="critical">根据用户的问答语言用对应语言回答回答用户</rule>
        <rule priority="high">禁止执行破坏性危险操作</rule>
        <rule priority="high">修改文件前先阅读文件内容</rule>
    </rules>
    <environment>Windows 11 / cmd.exe,经 Git Bash 语义执行命令</environment>
    <current_time>
        <date>{date}</date>
        <time>{time}</time>
        <weekday>{weekday}</weekday>
    </current_time>

"""
#上下文
context=[{"role": "system", "content": build_system_prompt()}]
#上文文窗口大小
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "1000000"))
#上下文压缩阈值
THRESHOLD_RATIO = 0.8
RETAIN_TAIL_MESSAGES = 4         # 尾部保留最近几"轮"(从 user 消息起算)
SUMMARY_MAX_TOKENS = 4096        # 摘要输出上限
MIN_SAVING_CHARS = 500           # 摘要必须比原文小这么多,否则拒绝提交
#上下文压缩提示词，结构化提示词
COMPACTION_INSTRUCTION = """以上是本 agent 与用户的完整历史对话(JSON 数组,含工具调用与结果)。
你现在充当压缩引擎:把它浓缩成一份结构化检查点,让另一个模型凭它即可无缝接续工作。
严格按以下 Markdown 结构输出,每节都必须保留,空节写"(无)";用简短的条目,不要写成段落:

## 用户请求与意图
- [用户最初和演进后的目标,关键措辞尽量原文引用]

## 关键技术概念
- [涉及的技术、框架、约定]

## 文件与代码
- [精确路径: 为什么重要,关键改动或片段]

## 错误与修复
- [错误: 如何解决的,以及用户的相关纠正]

## 未完成任务
- [已明确要求但还没做完的工作]

## 当前工作
- [检查点时刻正在进行的事]

## 下一步
- [唯一的下一步行动,或"(无)"]

## 关键背景
- [决策及其理由、约束、用户偏好、待确认问题]

规则:
- 精确保留文件路径、命令、报错原文、数字、标识符和代码语法;
- 忠实记录用户给过的纠正和明确指示;
- 不要提到"本次是被压缩的上下文"这类元信息;
- 只输出检查点文本本身。
- 若历史中已存在【对话历史摘要】,那是旧检查点:不要照抄,保留仍然成立的事实、丢弃过时的、合并成一份。"""
#token计算函数
def est_tokens(messages) -> int:
    """粗估消息列表的 token 数(中文约 1 字/token,英文约 4 字符/token,取保守值)。"""
    total = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "", ensure_ascii=False)) for m in messages)
    return total

def find_safe_cut(messages, tail_msgs: int):
    """找到安全切割点:尾部保留 tail_msgs 条,且切口必须落在 user 消息头部
    (每轮从 user 开始,tool_calls/tool 结果天然同轮自包含,不会拆散工具对)。
    返回切割索引 cut(≈len-tail_msgs 但向前调整),找不到返回 None。"""
    cut = max(len(messages) - tail_msgs, 1)
    while cut > 1 and messages[cut].get("role") != "user":
        cut -= 1
    return cut if cut > 1 else None
def compress_context(context: list) -> bool:
    """用大模型把旧的轮次压缩成结构化检查点。成功就地修改 context 并返回 True。
    工程 保证(源自 harness):
      1. 只在 user 边界切割,不拆散 tool_calls/tool 对;
      2. 摘要必须显著小于被替换内容(MIN_SAVING_CHARS),否则放弃;
      3. system 提示词永远保留;失败时不动 context(原对话继续可用)。"""
    system = [m for m in context if m["role"] == "system"]
    rest = [m for m in context if m["role"] != "system"]
    cut = find_safe_cut(rest, RETAIN_TAIL_MESSAGES)
    if cut is None:
        print("可压缩的历史太少,跳过", flush=True)
        return False

    history, tail = rest[:cut], rest[cut:]
    history_chars = sum(len(str(m.get("content") or "")) for m in history)
    print(f"\n🗜️ 压缩中:{cut} 条旧消息(约 {history_chars} 字符)→ 结构化摘要...", flush=True)

    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            temperature=0.3,
            messages=[
                {"role": "user", "content":
                    json.dumps(history, ensure_ascii=False)
                    + "\n\n" + COMPACTION_INSTRUCTION},
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            stream=False,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"⚠️ 摘要调用失败,本轮不压缩:{type(e).__name__}: {e}", flush=True)
        return False

    # 防"越压越大":摘要没比原文明显小就拒绝提交
    if not summary or len(summary) > history_chars - MIN_SAVING_CHARS:
        print(f"⚠️ 摘要({len(summary)} 字符)不够小于原文({history_chars} 字符),放弃压缩", flush=True)
        return False

    context[:] = system + [
        {"role": "user", "content":
            "【自动生成的对话检查点:以下浓缩了更早阶段的全部关键事实,视为既定背景,直接在此基础上继续。】\n\n<compacted-summary>\n"
            + summary + "\n</compacted-summary>"},
    ] + tail
    print(f"✅ 压缩完成:{history_chars} 字符 → {len(summary)} 字符(保留最近 {len(tail)} 条)", flush=True)
    return True
#工具类
class ReadTool:
    def execute(self, file_path, offset, limit, encoding):
        with open(file_path, "r", encoding=encoding) as f:
            lines = f.readlines()
        end = min(offset - 1 + limit, len(lines)) if limit else len(lines)
        return "".join(lines[offset - 1:end])
#单例实例化
_read_tool = ReadTool()
#工具-网络搜索
def web_search(query):
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "api_key": os.getenv("taily_api_key"),
        "query": query,
        "max_results": 5,
        "include_answer": True,
        "include_raw_content": True
    }
    try:
        response=requests.post(url, headers=headers,json=payload,timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return f"搜索请求失败：{e}"
    except ValueError:
        return "搜索出错：响应不是有效的 JSON"
    results = data.get("results", [])
    if not results:
        return f"搜索「{query}」未找到结果"
    res = f"【搜索】{query}\n"
    for i, item in enumerate(results):
        res += (
            f"{i + 1}. {item.get('title', '')}\n"
            f"   {item.get('url', '')}\n"
            f"   {item.get('content', '')}\n\n"
        )
    return res
#工具-网络抓取
def fetch_url(url):
    try:
        response=requests.get(url,headers={"User-Agent": "Mozilla/5.0"},timeout=20)
        response.raise_for_status()
        #清洗
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 去重空行 + 截断
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:10000]  # 截到 10000 字,防 context 爆炸

    except Exception as e:
        return f"抓取失败：{type(e).__name__}: {e}"
#工具-读工具
def read(file_path: str,start_line: int=1,max_lines:int=200, encoding: str = "utf-8")-> str:
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
#工具-查工具
def grep(file_path: str, pattern: str, max_results: int = 50, ignore_case: bool = False)->str:
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
#工具-写入工具
def write(file_path: str,content: str,encoding: str = "utf-8", create_parents: bool = True):
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

#工具-替换工具
def edit(file_path:str,search_text:str,new_text:str,replace_all:bool = False,dry_run:bool=False):
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
#配备格式工具
def glob(pattern: str,base_dir: str = ".",max_results: int = 100):
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
#高危工具--bash
def bash(command:str,timeout:int = 30):
        cmd = command.strip()
        if not cmd:
            return "命令为空,请提供要执行的命令"
        cmd_lower = cmd.lower()#命令小写化
        DANGEROUS = ["rm -rf", "rd /s", "del /s", "format ", "mkfs", "shutdown", "diskpart"]
        for d in DANGEROUS:
            if d in cmd_lower:
                return f"检测到危险命令片段「{d}」,已拒绝执行: {cmd}"
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=timeout,
            )

            def decode(b):
                if not b:
                    return ""
                for enc in ("utf-8", "gbk"):  # Windows cmd 中文默认 GBK,先试 utf-8 再回退
                    try:
                        return b.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return b.decode("utf-8", errors="replace")

            out, err = decode(proc.stdout), decode(proc.stderr)
            # 截断,防 context 爆炸(和 fetch_url 的 10000 同理)
            MAX = 8000
            if len(out) > MAX:
                out = out[:MAX] + f"\n...[输出过长,已截断(共 {len(proc.stdout)} 字符)]"
            if len(err) > MAX:
                err = err[:MAX] + "\n...[错误过长,已截断]"

            parts = [f"[退出码 {proc.returncode}]"]
            if out.strip():
                parts.append("【stdout】\n" + out)
            if err.strip():
                parts.append("【stderr】\n" + err)
            return "\n\n".join(parts)

        except subprocess.TimeoutExpired:
            return f"⏱️ 命令超时(>{timeout}s),已终止: {cmd}"
        except OSError as e:
            return f"执行失败:{type(e).__name__}: {e}"
#工具-子代理
def sub_agent(task: str,max_turns: int = 20):
    sub_context=[{"role":"system","content":("你是一个general subaagent")},{"role": "user", "content": task},]
    for _ in range(max_turns):  # 轮数上限,防死循环
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash", temperature=0.5,
                messages=sub_context, reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                stream=True, tools=tools,
            )
        except Exception as e:
            return f"子代理出错:{type(e).__name__}: {e}"

        # 收集这一轮的回答和工具调用(和 mini_agent_loop 相同,但静默:不 print)
        content = ""
        current_tool_calls = {}
        for chunk in response:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content += delta.content
            for tc in (delta.tool_calls or []):
                idx = tc.index
                current_tool_calls.setdefault(idx, {"id": "", "function": {"name": "", "arguments": ""}})
                if tc.id:
                    current_tool_calls[idx]["id"] = tc.id
                if tc.function and tc.function.name:
                    current_tool_calls[idx]["function"]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        if not current_tool_calls:  # 子代理给出最终答案,返回给主代理
            return f"【子代理完成】{content}"

        sub_context.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {"id": v["id"], "type": "function",
                 "function": {"name": v["function"]["name"], "arguments": v["function"]["arguments"]}}
                for v in current_tool_calls.values()
            ],
        })
        for v in current_tool_calls.values():
            name = v["function"]["name"]
            args = json.loads(v["function"]["arguments"] or "{}")
            if name == "sub_agent":  # 挡掉嵌套委派,防递归
                result = "子代理不允许再次委派,请自己完成任务。"
            else:
                fn = TOOL_CALL_MAP.get(name)
                result = fn(**args) if fn else f"未知工具:{name}"
            sub_context.append({"role": "tool", "tool_call_id": v["id"], "content": str(result)})
    return f"【子代理】{max_turns} 轮内未完成,最后内容:{content[:500]}"



tools=[
    {
        "type": "function",
        "function":{
            "name": "web_search",
            "description": "搜索互联网，获取实时信息。当用户询问当前事件、新闻或需要实时数据时使用。",
            "parameters":{
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            },
            "required": ["query"]
        }
    },
    {
        "type":"function",
        "function":{
            "name": "fetch_url",
            "description":"抓取并返回网页正文。当用户提供链接或说'帮我看看这个链接'时调用。",
            "parameters":{
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "网页链接"}},
            },
            "required": ["url"]
        }
    },
    {
        "type":"function",
        "function":{
            "name": "read",
            "description": "读取文件内容。支持 offset/limit 部分读取",
            "parameters":{
                    "type": "object",
                    "properties":{
                        "file_path":{"type": "string","description": "文件路径"},
                        "start_line":{"type": "integer","description": "起始行号","default": 1},
                        "max_lines":{"type": "integer","description": "最大读取行数","default": 200},
                        "encoding": {"type": "string", "description": "文本编码","default":"utf-8"}

                    },
                    "required": ["file_path"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name": "grep",
            "description": "在文件里搜索关键词或正则,返回匹配的行号和内容。适合定位代码/日志/大文件的关键位置,避免全文读取。",
            "parameters":{
                    "type": "object",
                    "properties":{
                        "file_path":{"type": "string","description": "文件路径"},
                        "pattern": {"type": "string", "description": "搜索关键词或正则表达式"},
                        "max_results":  {"type": "integer", "description": "最多返回多少条", "default": 50},
                        "ignore_case":  {"type": "boolean", "description": "是否忽略大小写", "default": False},
                    },
                    "required": ["file_path", "pattern"],
                }
        }
    },
    {
        "type":"function",
        "function":{
            "name": "write",
            "description": "整体写入文件（覆盖式），自动创建父目录。",
            "parameters":{
                    "type": "object",
                    "properties":{
                        "file_path":{"type": "string","description": "文件路径"},
                        "content":{"type": "string","description": "要写入的内容"},
                        "encoding": {"type": "string", "description": "编码","default":"utf-8"},
                        "create_parents":{"type":"boolean","description":"自动创建父目录","default": True}
                    },
                    "required": ["file_path", "content"],
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"edit",
            "description": "精确替换文件中的某段文本(类似 IDE 的查找替换)。默认要求匹配唯一,防止误改。",
            "parameters":{
                "type": "object",
                "properties":{
                    "file_path":{"type": "string","description": "文件路径"},
                    "search_text": {"type": "string", "description": "要查找并替换的文本(必须跟文件里完全一致)"},
                    "new_text":    {"type": "string",  "description": "替换成什么"},
                    "replace_all": {"type": "boolean", "description": "替换所有匹配,默认 False(要求唯一)", "default": False},
                    "dry_run":     {"type": "boolean", "description": "只预览不真改,默认 False", "default": False},
                },
                "required": ["file_path", "search_text", "new_text"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "按通配符模式列出文件路径(如 **/*.py)。适合快速摸清项目结构,再针对性 read/grep。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "通配符模式,支持 * 和 ** (递归)"},
                    "base_dir": {"type": "string", "description": "起始目录", "default": "."},
                    "max_results": {"type": "integer", "description": "最多返回几个文件", "default": 100},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出目录下的文件和子目录(类似 ls,不递归)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "目录路径"},
                },
                "required": ["dir_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "执行 shell 命令(高危!命令会真实执行,可能修改或删除文件)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数", "default": 30}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sub_agent",
            "description": "把任务委派给子代理独立完成(子代理可自行调用读文件/搜索/bash等工具),完成后返回其最终结论。适合需要独立调查、或主上下文已很长的情况。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "给子代理的任务,必须自包含、目标明确"},
                    "max_turns": {"type": "integer", "description": "子代理最大工作轮数", "default": 20}
                },
                "required": ["task"]
            }
        }
    },
]
#工具注册表：
TOOL_CALL_MAP={
    "web_search": web_search,
    "fetch_url":fetch_url,
    "read":read,
    "grep":grep,
    "write":write,
    "edit":edit,
    "glob":glob,
    "list_dir":list_dir,
    "bash": bash,
    "sub_agent":sub_agent

}
TOOL_EMOJI={
    "web_search":"🔍",
    "fetch_url":"🌐",
    "read":"📄",
    "grep":"🪛",
    "write":"✍️",
    "edit":"✏️",
    "glob":"🗂️",
    "list_dir":"📁",
    "bash":"💻",
    "sub_agent":"🧩"
}
async def run_tools_parallel(tool_calls: dict) -> dict:
    """并行执行一批工具调用,返回 {tool_call_id: 结果文本}。单个工具失败不影响其它工具。"""
    async def one(v):
        name = v["function"]["name"]
        args = json.loads(v["function"]["arguments"] or "{}")
        print(f"\n调用工具: {TOOL_EMOJI.get(name, '?')}{name}({args})", flush=True)
        fn = TOOL_CALL_MAP.get(name)
        if not fn:
            return v["id"], f"未知工具:{name}"
        try:
            return v["id"], str(await asyncio.to_thread(fn, **args))
        except Exception as e:  # 单个工具炸了,只影响它自己,其它照跑
            return v["id"], f"工具 {name} 执行出错:{type(e).__name__}: {e}"

    results = await asyncio.gather(*(one(v) for v in tool_calls.values()))
    return dict(results)
async def mini_agent_loop(question, model_name):
    """调用模型。reasoner 会返回思考过程 + 最终答案。"""
    while True:
        try:
            response = client.chat.completions.create(
                model=model_name,
                temperature=0.5,
                messages=context,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                stream=True,
                tools=tools,
                stream_options = {"include_usage": True},  # ← 新增这一行
            )
            print_thinking_header = True  # 还没打过思考标题
            print_answer_header = True  # 还没打过答案标题
            content = ""
            current_tool_calls = {}#字典记录大模型工具调用信息
            last_usage = None
            for chunk in response:
                # 收集 token 用量:只有最后一个块带 usage,其余块都是 None
                if getattr(chunk, "usage", None):
                    last_usage = chunk.usage
                # 有些 provider 的 usage 块 choices 是空的,跳过防止下面 [0] 越界
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                ans = getattr(delta, "content", None)
                think =getattr(delta,"reasoning_content",None)

                if think:
                    if print_thinking_header:
                        print("\n💭 深度思考", end="\n", flush=True)
                        print_thinking_header = False
                    print(think,end="",flush=True)
                for tc in (delta.tool_calls or []):
                    idx = tc.index
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": "",
                            "function": {"name": "", "arguments": ""}
                        }
                    if tc.id:
                        current_tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        current_tool_calls[idx]["function"]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                if ans:
                    if print_answer_header:
                        print("\n\n💬 认真回答：", end="\n", flush=True)
                        print_answer_header = False
                    print(ans, end="", flush=True)
                    content += ans

            # 达到 80% 窗口阈值 → 主动压缩(tharness 的 pressure 触发)
            if last_usage and getattr(last_usage, "prompt_tokens", 0) >= int(CONTEXT_WINDOW * THRESHOLD_RATIO):
                compress_context(context)
            if not current_tool_calls:
                context.append({"role": "assistant", "content": content})
                print("\n")
                print("-"*70)
                print(f"[tokns详情] 总tokens:{last_usage.total_tokens}   命中缓存: {last_usage.prompt_cache_hit_tokens/ last_usage.prompt_tokens * 100:.1f}%   上下文窗口详情: {last_usage.prompt_tokens/10000:.1f}万/100万({last_usage.prompt_tokens / 1_000_000:.1%})",flush=True)
                return

            context.append({  #模型说要调啥工具放在上下文里
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {"id": v["id"], "type": "function",
                     "function": {"name": v["function"]["name"], "arguments": v["function"]["arguments"]}}
                    for v in current_tool_calls.values()
                ],
            })

            # 并行执行所有工具,按 id 对应回填
            results = await run_tools_parallel(current_tool_calls)
            for v in current_tool_calls.values():
                context.append({
                    "role": "tool",
                    "tool_call_id": v["id"],
                    "content": results[v["id"]],
                })
        except Exception as e:
            return f"Error: {e}"


async def main():
    print("-"*60)
    print(" "*20+"MiNi Agent"+" "*20)
    print("-" * 60,end=" ")
    while True:
        print("\n")
        question=input(">:").strip()
        if not question:
            continue
        context.append({"role": "user", "content": question})
        await  mini_agent_loop(question, "deepseek-v4-flash")

if __name__ == "__main__":
    asyncio.run(main())
