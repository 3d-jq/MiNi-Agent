# MiNi Agent

> 实验中的单文件 CLI 编程 Agent —— 从零手写,不依赖 Agent 框架,边学边造。

基于 DeepSeek API(OpenAI 兼容协议)的迷你编程助手,目前约 800 行 Python。
这是一个**处于早期的学习/实验项目**,结构和功能都会持续大改,README 只描述当前状态,不作为稳定接口文档。

## 目前有什么

- **Agent 工具循环** —— 模型自主决定调用哪些工具,结果回填上下文持续推理,直到给出答案
- **10 个工具**:联网搜索(Tavily)、网页抓取、read / grep / write / edit / glob / list_dir、bash、子代理
- **异步并行工具执行** —— `asyncio.gather` + `to_thread`,一次发出的多个工具调用并发跑
- **子代理(Sub-Agent)** —— 独立上下文接受委派,静默干活只回传结论,禁止嵌套防递归
- **上下文自动压缩** —— 占用达窗口 80% 时用 LLM 把旧历史压成结构化检查点;只切 user 消息边界、校验摘要必须更小
- **流式深度思考输出** —— reasoning 过程与回答实时打印
- **KV 缓存命中率统计** —— 从 usage 读 prompt_tokens / 缓存命中 / 窗口占用

## 运行

```bash
pip install openai python-dotenv requests beautifulsoup4 lxml
```

根目录建 `.env`(**别提交到 git**):

```
deepseek_api_key=你的Key
taily_api_key=你的Tavily_Key
```

```bash
python learn.py
```

## 结构一览

单文件 `learn.py`,从上到下大致是:

| 区块 | 内容 |
|---|---|
| 配置区 | 上下文窗口 / 压缩阈值等常量(支持环境变量覆盖) |
| `build_system_prompt()` | XML 化静态 system prompt(为前缀缓存优化) |
| 工具函数 × 10 | 每个工具一个普通函数 |
| `tools` schema + `TOOL_CALL_MAP` | 模型侧的工具描述 与 Python 侧的实现映射 |
| `compress_context()` 等 | 压缩系统:安全切点查找、LLM 摘要、提交校验 |
| `sub_agent()` | 子代理循环(静默版 agent loop) |
| `run_tools_parallel()` | 并行工具执行层(asyncio) |
| `mini_agent_loop()` | 主循环:流式收集 → 工具调度 → 上下文维护 |

## 在想 / 在改的事

- [ ] bash 执行前的确认门(y/n/a)
- [ ] OS 级沙箱(pywin32 受限令牌 + 目录 ACL)
- [ ] 超窗错误的兜底:强制压缩后自动重试
- [ ] 主循环与子代理循环的去重重构
- [ ] Token 预算式尾部保留

## 设计笔记

- **提示词 XML 化且内容静态化**(时间等动态信息不进 system prompt):保住 DeepSeek 前缀 KV 缓存的命中;
- **历史严格追加式**:插入/修改旧消息都会打断缓存;
- **压缩是有意破坏缓存的操作**:压缩后下一轮命中率必然暴跌,属预期代价;
- **并行任务互相隔离**:单个工具异常以错误文本返回,不拖垮其它工具;
- **命令黑名单只能挡低级错误**,真正要防住得靠沙箱(Roadmap 里),当前阶段 bash 请在可控环境使用。

## ⚠️ 免责声明

学习用途。`bash` / `write` / `edit` 会真实修改本地文件系统,请在可控环境下使用;妥善保管 `.env`,密钥泄露请立即吊销。

## License

MIT
