# MiNi Agent

> 专注编程与办公的 CLI Agent —— 按主流 Agent 架构从零手写,不依赖任何框架,边学边造。

基于 DeepSeek API(OpenAI 兼容协议)的迷你 Agent,专注编程与办公任务:写代码、改项目,也能产出/编辑 Word、Excel、PPT、PDF 文档。
这是一个处于早期的学习/实验项目,结构和功能都会持续大改,README 只描述当前状态,不作为稳定接口文档。

## 目前有什么

- **Agent 工具循环** —— 模型自主决定调用哪些工具,结果回填上下文持续推理,直到给出答案
- **15 个工具**:联网搜索(Tavily)、网页抓取、read / grep / write / edit / glob / list_dir、bash、子代理、记忆四件套(save / edit / delete / clear)、load_skill
- **技能系统(Skills)** —— 渐进披露设计:system prompt 只放清单,任务匹配时 `load_skill` 按需加载全文;支持 YAML 多行 description、`SKILL_DIR` 路径解析。内置 `create_skill` 元技能(教模型创建新技能的自我扩展闭环)+ 办公四件套(docx / pdf / xlsx / pptx)
- **长期记忆系统** —— 跨会话持久化(`memory.md`),模型自主判断"值得记"的内容并调用工具写入;启动时注入 system prompt,改/删/清各有工具
- **上下文自动压缩** —— 占用达窗口 80% 时用 LLM 把旧历史压成结构化检查点;只切 user 消息边界、校验摘要必须更小
- **异步并行工具执行** —— `asyncio.gather` + `to_thread`,一次发出的多个工具调用并发跑
- **重复调用检测** —— 连续重复链(同工具+同参数)触发阶梯提醒(3/5/8 次),只提醒不拦截,给模型自我纠正的机会
- **ESC 键盘中断** —— agent 运行期间随时按 ESC 中断本轮:流式输出立即停(部分回答保留进上下文),工具做完手头的就停
- **回答 Markdown 流式渲染** —— `rich Live` 原地刷新,标题/代码块/列表实时渲染;思考过程保持逐字打印
- **工具参数预览** —— 调用日志里长参数自动截断(换行压成 ⏎),既看得到模型在干嘛又不刷屏
- **子代理(Sub-Agent)** —— 独立上下文接受委派,静默干活只回传结论,禁止嵌套防递归
- **KV 缓存命中率统计** —— 从 usage 读 prompt_tokens / 缓存命中 / 窗口占用
- **83 个测试用例** —— 82 个离线单测 + 1 个真实 LLM 集成测试(默认跳过)

## 运行

```bash
pip install openai python-dotenv requests beautifulsoup4 lxml rich pytest
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
- **单测**:用 FakeClient 假对象替换 LLM 调用,测**决策逻辑**——压缩触发与提交校验、重复调用检测的连续链、并行并发语义、记忆读写、skill 解析与加载、schema 与实现一致性;
- **集成**:真实调用 DeepSeek API,只断言**结构**(system 保留、摘要小节、尾部原样保留),不断言具体文字(模型输出不稳定)。

## 结构一览

代码按职责拆分,`learn.py` 只做入口转发:

| 模块 | 职责 |
|---|---|
| `learn.py` | 入口转发(启动命令不变:python learn.py) |
| `config.py` | 上下文窗口 / 压缩阈值等常量(支持环境变量覆盖) |
| `llm_client.py` | OpenAI 客户端单例(统一读取 .env) |
| `prompts.py` | system prompt(XML 化静态编排 + 记忆/技能注入,保前缀缓存) |
| `tools_web.py` | web_search(Tavily)/ fetch_url |
| `tools_files.py` | read / grep / write / edit / glob / list_dir |
| `tools_bash.py` | bash(危险命令黑名单 + 超时 + 输出截断) |
| `tools_memory.py` | 长期记忆:load / save / edit / delete / clear(memory.md) |
| `tools_skill.py` | 技能:frontmatter 解析、清单扫描、按需加载、SKILL_DIR 路径解析 |
| `sub_agent.py` | 子代理循环(函数内 import 打破与注册表循环依赖) |
| `tool_registry.py` | tools schema + TOOL_CALL_MAP + TOOL_EMOJI 唯一连接点 |
| `compaction.py` | 压缩系统:token 估算、安全切点、LLM 摘要、提交校验 |
| `agent_loop.py` | 会话 context、并行工具执行、重复调用检测、ESC 中断、主循环 |
| `skills/` | 技能库:create_skill 元技能 + 办公四件套(docx/pdf/xlsx/pptx) |
| `tests/` | 10 个测试文件,83 个用例 |

## ⚠️ 免责声明

学习用途。`bash` / `write` / `edit` 会真实修改本地文件系统,请在可控环境下使用;妥善保管 `.env` 与 `memory.md`(均不入库),密钥泄露请立即吊销。

## License

MIT