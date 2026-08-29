"""工具注册表:模型侧 schema(tools)与 Python 侧实现(TOOL_CALL_MAP)的唯一连接点。
tools / TOOL_CALL_MAP / TOOL_EMOJI 三个字典的 key 必须一一对应(有测试保证)。
"""
from sub_agent import sub_agent
from tools_bash import bash
from tools_files import edit, glob, grep, list_dir, read, write
from tools_web import fetch_url, web_search
from tools_memory import clear_memory, save_memory,edit_memory,delete_memory
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网，获取实时信息。当用户询问当前事件、新闻或需要实时数据时使用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            },
            "required": ["query"]
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓取并返回网页正文。当用户提供链接或说'帮我看看这个链接'时调用。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "网页链接"}},
            },
            "required": ["url"]
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "读取文件内容。支持 offset/limit 部分读取",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "start_line": {"type": "integer", "description": "起始行号", "default": 1},
                    "max_lines": {"type": "integer", "description": "最大读取行数", "default": 200},
                    "encoding": {"type": "string", "description": "文本编码", "default": "utf-8"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在文件里搜索关键词或正则,返回匹配的行号和内容。适合定位代码/日志/大文件的关键位置,避免全文读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "pattern": {"type": "string", "description": "搜索关键词或正则表达式"},
                    "max_results": {"type": "integer", "description": "最多返回多少条", "default": 50},
                    "ignore_case": {"type": "boolean", "description": "是否忽略大小写", "default": False},
                },
                "required": ["file_path", "pattern"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "整体写入文件（覆盖式），自动创建父目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                    "encoding": {"type": "string", "description": "编码", "default": "utf-8"},
                    "create_parents": {"type": "boolean", "description": "自动创建父目录", "default": True}
                },
                "required": ["file_path", "content"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "精确替换文件中的某段文本(类似 IDE 的查找替换)。默认要求匹配唯一,防止误改。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "search_text": {"type": "string", "description": "要查找并替换的文本(必须跟文件里完全一致)"},
                    "new_text": {"type": "string", "description": "替换成什么"},
                    "replace_all": {"type": "boolean", "description": "替换所有匹配,默认 False(要求唯一)", "default": False},
                    "dry_run": {"type": "boolean", "description": "只预览不真改,默认 False", "default": False},
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
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "把重要信息写入长期记忆(跨会话保留)。适合记录:用户偏好、项目约定、重要决策、任务状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要记住的内容,一句话完整自包含"},
                    "time":{"type": "string","description":"对应内容的具体时间"}
                },
                "required": ["content","time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_memory",
            "description": "清空全部长期记忆(高危,需用户确认后调用)。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
            "type": "function",
            "function": {
                "name": "edit_memory",
                "description": "修改一条已有记忆。old_text 必须引用记忆里的原文片段(要求唯一匹配)。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string", "description": "要修改的原文片段(唯一匹配)"},
                        "new_text": {"type": "string", "description": "替换成的内容"}
                    },
                    "required": ["old_text", "new_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_memory",
                "description": "删除包含关键词的记忆条目。",
                "parameters": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string", "description": "关键词,包含它的记忆行会被删除"}},
                    "required": ["keyword"]
                }
            }
        },

]

# 工具注册表
TOOL_CALL_MAP = {
    "web_search": web_search,
    "fetch_url": fetch_url,
    "read": read,
    "grep": grep,
    "write": write,
    "edit": edit,
    "glob": glob,
    "list_dir": list_dir,
    "bash": bash,
    "sub_agent": sub_agent,
    "save_memory":save_memory,
    "clear_memory":clear_memory,
    "edit_memory": edit_memory,
    "delete_memory": delete_memory,

}

TOOL_EMOJI = {
    "web_search": "🔍",
    "fetch_url": "🌐",
    "read": "📄",
    "grep": "🪛",
    "write": "✍️",
    "edit": "✏️",
    "glob": "🗂️",
    "list_dir": "📁",
    "bash": "💻",
    "sub_agent": "🧩",
    "save_memory":"🧠",
    "clear_memory":"🗑️",
    "edit_memory": "✏️",
    "delete_memory": "🗑️",
}