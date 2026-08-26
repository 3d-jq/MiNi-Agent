# MiNi Agent

> 实验中的 CLI 编程 Agent —— 无 Agent 框架,从零手写,边学边造。

基于 DeepSeek API(OpenAI 兼容协议)的迷你编程助手。
这是一个处于早期的学习/实验项目,结构和功能都会持续大改,README 只描述当前状态,不作为稳定接口文档。

## 目前有什么

- **Agent 工具循环** —— 模型自主决定调用哪些工具,结果回填上下文持续推理,直到给出答案
- **10 个工具**:联网搜索(Tavily)、网页抓取、read / grep / write / edit / glob / list_dir、bash、子代理
- **异步并行工具执行** —— `asyncio.gather` + `to_thread`,一次发出的多个工具调用并发跑
- **子代理(Sub-Agent)** —— 独立上下文接受委派,静默干活只回传结论,禁止嵌套防递归
- **上下文自动压缩** —— 占用达窗口 80% 时用 LLM 把旧历史压成结构化检查点;只切 user 消息边界、校验摘要必须更小
- **流式深度思考输出** —— reasoning 过程与回答实时打印
- **KV 缓存命中率统计** —— 从 usage 读 prompt_tokens / 缓存命中 / 窗口占用
- **44 个测试用例** —— 43 个离线单测 + 1 个真实 LLM 集成测试(默认跳过)

## 运行

```bash
pip install openai python-dotenv requests beautifulsoup4 lxml pytest
```

根目录建 `.env`(**别提交到 git**):

```
deepseek_api_key=你的Key
taily_api_key=你的Tavily_Key
```

```bash
python learn.py
```

## 测试

```bash
# 单测:全部离线,不花钱
python -m pytest

# 集成:真实 API 验证压缩链路(需要 .env 有 key,花少量费用)
RUN_REAL_LLM_TESTS=1 python -m pytest tests/test_compress_real.py -v
```

两层测试的分工:
- **单测**(`tests/test_compress_context.py` 等):用 FakeClient 假对象替换 LLM 调用,测**决策逻辑**——摘要太长拒绝、异常兜底、历史太少不调用、schema 与实现一致、并行并发语义;
- **集成**(`tests/test_compress_real.py`):真实调用 DeepSeek API,只断言**结构**(system 保留、8 节摘要小节、尾部原样保留),不断言具体文字(模型输出不稳定)。

## 结构一览

代码按职责拆分为 11 个模块,`learn.py` 只做入口转发:

| 模块 | 职责 |
|---|---|
| `learn.py` | 入口转发(启动命令不变:python learn.py) |
| `config.py` | 上下文窗口 / 压缩阈值等常量(支持环境变量覆盖) |
| `llm_client.py` | OpenAI 客户端单例(统一读取 .env) |
| `prompts.py` | system prompt(XML 化静态编排,保前缀缓存) |
| `tools_web.py` | web_search(Tavily)/ fetch_url |
| `tools_files.py` | read / grep / write / edit / glob / list_dir |
| `tools_bash.py` | bash(危险命令黑名单 + 超时 + 输出截断) |
| `sub_agent.py` | 子代理循环(函数内 import 打破与注册表循环依赖) |
| `tool_registry.py` | tools schema + TOOL_CALL_MAP + TOOL_EMOJI 唯一连接点 |
| `compaction.py` | 压缩系统:token 估算、安全切点、LLM 摘要、提交校验 |
| `agent_loop.py` | 会话 context、并行工具执行层、主循环、CLI 入口 |
| `tests/` | 7 个测试文件,44 个用例 |

## ⚠️ 免责声明

学习用途。`bash` / `write` / `edit` 会真实修改本地文件系统,请在可控环境下使用;妥善保管 `.env`,密钥泄露请立即吊销。

## License

MIT