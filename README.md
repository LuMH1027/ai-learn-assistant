# 本地课程 RAG Agent 学习助手

面向学生日常学习的本地课程资料工作台。系统按照“一级文件夹 = 一门课程”识别资料，支持文件预览、课程独立问答、引用溯源、课程笔记、摘要和练习题。

前端使用 Vue 3、TypeScript、Vite 和 Pinia；后端使用 Python 标准库 HTTP 服务、文件型记忆和 JSON 轻量索引。课程文件与聊天记录均保存在本机。

## 核心能力

- 自动识别本地课程目录与多级文件树。
- 三栏工作区支持百分比拖动、紧凑侧栏和可关闭资料预览。
- 在同一预览区阅读 PDF、图片、文本，以及经过排版渲染的 Markdown。
- 每门课程独立构建知识库、会话、记忆和笔记。
- 每门课程自动生成可持久化的学习计划，按真实资料文件拆分阅读、练习和复盘项。
- 侧栏显示学习进度、剩余预计时间和下一步学习项，并支持手动新增与状态推进。
- 支持答疑、启发、作业提示和复习模式。
- 一键生成 LLM 课程摘要与本地练习题，并保存回课程目录；模型不可用时摘要会回退为本地抽取式摘要。
- 回答附带来源文件、原文片段和 PDF 页码。
- 检索采用标题感知切块、BM25、持久向量索引、多路 RRF 融合、本地 rerank、MMR 去重和相邻上下文扩展；配置 `ai.embedding_model` 后可使用 OpenAI-compatible embedding。
- 回答优先使用课程资料；未检索到依据时，可由已配置模型明确标注后使用通用知识补充。
- 本地证据不足或问题具有时效性时，可按需调用 Web Search MCP，并显示可点击网页来源。
- 对话从请求接收、课程检索、联网到模型生成全程流式反馈，模型文本按 token 增量显示。
- 支持课程资料上传和聊天临时附件。
- 可选接入 OpenAI-compatible 模型、embedding、rerank、Web Search MCP 与 MinerU；未配置时会在配置健康区显示降级提示，并使用本地轻量能力。

## 环境要求

- Python 3.9 或以上。
- Node.js 20.19 或以上，或者 Node.js 22.12 或以上。
- npm。
- Chrome、Edge、Safari 等现代浏览器。
- 一个本地课程资料目录。

## 一键安装全部项目依赖

安装脚本会创建隔离的 `.venv`、安装 `requirements.txt` 中的 Python 包，并根据 `frontend/package-lock.json` 执行 `npm ci --include=dev` 安装 Vue、Vite、TypeScript、Pinia 和测试工具。它覆盖 pip 与 npm 两套依赖，不会把 Python 包写入系统环境。

Windows：

```bat
install-deps.bat
```

macOS/Linux：

```bash
chmod +x install-deps.sh start.sh
./install-deps.sh
```

脚本不自动修改系统级运行时。若缺少 Python、Node.js 或 npm，会明确提示先安装符合“环境要求”的版本。只有 pip 与 npm 都成功后才会写入安装完成标记；下载中断后直接重试即可。重复执行安装脚本会按锁文件重新校准依赖，适合依赖损坏或切换分支后修复环境。

只需重装某一类依赖时，也可以手动执行：

```bash
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
```

## 一键启动

脚本发现 `.venv` 或 `frontend/node_modules` 缺失时会先调用对应平台的依赖安装器，随后把 Vue 前端构建到 `web/dist`，最后使用 `.venv` 中的 Python 启动服务。

Windows：

```bat
start.bat
```

macOS/Linux：

```bash
chmod +x start.sh
./start.sh
```

浏览器访问：

```text
http://127.0.0.1:8000
```

监听地址可在 `data/config.json` 的 `server.host` / `server.port` 中配置，也可用环境变量临时覆盖：

```bash
COURSE_AGENT_PORT=8010 ./start.sh
```

Windows：

```bat
set COURSE_AGENT_PORT=8010
start.bat
```

如果绕过脚本直接执行 Python 但尚未构建前端，服务会提示先运行启动脚本。

## 开发模式

终端 1 启动 Python API：

```bash
.venv/bin/python run.py
```

终端 2 启动 Vite，开发服务器会把 `/api` 代理到 Python：

```bash
npm run dev --prefix frontend
```

常用验证命令：

```bash
npm test --prefix frontend -- --run
npm run typecheck --prefix frontend
npm run build --prefix frontend
python3 -m unittest discover -s tests -v
```

生产构建输出目录是 `web/dist`，该目录由启动脚本生成，不提交到 Git。

## 后端结构

后端按职责分层，避免新增能力继续堆在 `local_course_agent/` 顶层：

```text
local_course_agent/
├─ api/         # HTTP glue、AppContext、系统接口、课程接口和聊天编排
├─ retrieval/   # RAG 检索、向量融合、引用校验、追问改写、RAG 评测
├─ learning/    # 课程索引任务、摘要、dashboard、掌握度模型
├─ ingestion/   # 解析质量评估等资料入库前处理
├─ ops/         # 备份恢复、配置健康状态、遥测诊断
├─ server.py    # ThreadingHTTPServer 与 Handler glue
├─ llm.py       # LLM 客户端与 Prompt
├─ parser.py    # 文档解析入口
├─ scanner.py   # 本地课程目录扫描
└─ store.py     # 文件型状态存储
```

功能模块不再保留顶层兼容 alias。业务代码应直接导入子包路径，例如 `local_course_agent.retrieval.rag`、`local_course_agent.learning.summary`、`local_course_agent.ops.backup`。

## 资料目录

系统按一级文件夹识别课程：

```text
StudyMaterials/
├─ 操作系统/
│  ├─ 教材/chapter1.pdf
│  ├─ 课件/process.pdf
│  └─ notes.md
├─ 数据结构/
│  ├─ stack.pdf
│  └─ queue.txt
└─ 高等数学/
   └─ limit.pdf
```

支持 `.pdf`、`.txt`、`.md`、`.markdown`、`.docx`、`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif` 和 `.bmp`。PDF、图片、文本和 Markdown 会在右侧预览区打开；Markdown 会渲染标题、列表、表格、引用和代码块。DOCX 支持基础文本抽取用于入库，复杂版式、批注、页眉页脚、扫描件和图片文字仍建议转换为 PDF，或配合 MinerU 等更高质量解析工具。

## 配置

复制脱敏示例：

```bash
cp data/config.example.json data/config.json
```

Windows：

```bat
copy data\config.example.json data\config.json
```

主要字段：

- `root_folder`：课程资料根目录。
- `server.host/server.port`：本地服务监听地址；默认 `127.0.0.1:8000`，也可用 `COURSE_AGENT_HOST` / `COURSE_AGENT_PORT` 临时覆盖。
- `ai.base_url/api_key/model`：OpenAI-compatible 模型配置；默认使用 SiliconFlow `Qwen/Qwen3.5-35B-A3B`，`api_key` 可写 `$SILICONFLOW_API_KEY`。
- `ai.embedding_model/embedding_dimensions`：可选的 OpenAI-compatible embedding 配置；留空时使用本地确定性 embedding fallback。
- `ai.embedding_base_url/embedding_api_key`：可选的 embedding 专用 endpoint 和 key；默认接 SiliconFlow `Qwen/Qwen3-VL-Embedding-8B`，key 留空时读取 `SILICONFLOW_API_KEY`。
- `ai.embedding_batch_size/embedding_max_retries/embedding_retry_delay`：embedding 批大小、失败重试次数和重试间隔，用于提升外部 provider 的稳定性。
- `ai.rerank_model/rerank_base_url/rerank_api_key`：可选的 SiliconFlow `/rerank` 配置；默认模型为 `Qwen/Qwen3-Reranker-8B`，无 key 时使用本地 rerank。
- `web_search`：MCP Web Search 配置；`enabled` 开启后才会向外部服务发送学生问题。
- `mineru.token`：MinerU API token。

示例：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000
  },
  "root_folder": "D:/StudyMaterials",
  "ai": {
    "provider": "openai_compatible",
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "$SILICONFLOW_API_KEY",
    "model": "Qwen/Qwen3.5-35B-A3B",
    "embedding_model": "Qwen/Qwen3-VL-Embedding-8B",
    "embedding_dimensions": "",
    "embedding_base_url": "https://api.siliconflow.cn/v1",
    "embedding_api_key": "$SILICONFLOW_API_KEY",
    "embedding_timeout": 30,
    "embedding_batch_size": 32,
    "embedding_max_retries": 2,
    "embedding_retry_delay": 1.0,
    "rerank_model": "Qwen/Qwen3-Reranker-8B",
    "rerank_base_url": "https://api.siliconflow.cn/v1",
    "rerank_api_key": "$SILICONFLOW_API_KEY",
    "rerank_timeout": 30,
    "rerank_top_n": 12
  },
  "web_search": {
    "enabled": false,
    "provider": "mcp",
    "mcp_url": "https://mcp.exa.ai/mcp",
    "tool_name": "web_search_exa",
    "query_argument": "query",
    "max_results_argument": "",
    "max_results": 5,
    "timeout": 20,
    "api_key": "",
    "auth_header": "x-api-key",
    "auth_scheme": ""
  },
  "mineru": {
    "auto": true,
    "api_enabled": true,
    "language": "ch",
    "token": ""
  }
}
```

项目实现 MCP `2025-06-18` Streamable HTTP 客户端，支持 JSON 与 SSE 响应。示例使用 [Exa 官方 Web Search MCP](https://exa.ai/docs/reference/exa-mcp)；免费额度可不填 key，超过限额后在 `api_key` 填写 Exa key。也可以替换成其他返回结构化 URL、标题和摘要的搜索 MCP。

联网判断规则：本地检索证据充分且问题不要求最新信息时跳过联网；本地无结果、相关性不足、包含“最新/目前/联网”或明确年份时调用搜索。只向 MCP 发送学生问题，不发送课程片段或附件正文。处理过程会显示联网是否被跳过、未配置、无结果或失败。

课程摘要使用已入库的代表性课程片段构造专用 Prompt，再调用 `ai` 中配置的 OpenAI-compatible 模型生成分层 Markdown 摘要。摘要要求只基于课程片段输出，并保留来源引用；如果未配置模型或模型调用失败，系统会自动使用本地抽取式摘要兜底。

首次启动时，侧栏底部的“配置健康”会显示启动清单：设置资料根目录、构建课程知识库、可选配置大模型和真实 embedding。AI、真实 embedding、rerank、Web Search MCP 或 MinerU 未配置时，系统会明确显示对应降级提示。

不要提交真实 `data/config.json`。`.gitignore` 只允许提交 `data/config.example.json`。

## 使用流程

1. 启动系统并设置资料根目录。
2. 在左栏选择课程与文件。
3. 构建当前课程知识库。
4. 在中央对话区选择模式并提问。
5. 点击回答引用，在右栏核对原文和页码。
6. 在左栏推进学习计划，按需生成摘要、练习题或保存课程笔记。

## 数据位置

```text
data/
├─ config.json
├─ course_memory/<course_id>/
│  ├─ messages.json
│  ├─ memory.md
│  ├─ notes.json
│  └─ study_plan.json
├─ chat_uploads/
└─ indexes/
   ├─ <course_id>.json
   └─ <course_id>.vector.json
```

生成的摘要与练习题保存在对应课程的 `AI生成/` 文件夹。该目录中的文件可在文件树中预览，但构建知识库时会被排除，避免模型生成内容再次成为后续回答的课程证据。

检索索引会记录 schema/tokenizer 版本、章节标题、资料类型和来源路径，并在同目录保存持久向量索引；回答接口会返回检索 trace，便于核对命中片段、匹配词、分数和证据充分性。检索实现见 [`docs/rag-retrieval-strategy.md`](docs/rag-retrieval-strategy.md)，向量检索见 [`docs/vector-retrieval.md`](docs/vector-retrieval.md)，答案级评测见 [`docs/rag-eval.md`](docs/rag-eval.md)。

课程摘要优先使用章节级 map-reduce LLM pipeline，失败时降级为 single prompt 或本地抽取式摘要；实现边界见 [`docs/summary-pipeline.md`](docs/summary-pipeline.md)。配置能力状态、内存遥测诊断和本地数据备份恢复分别见 [`docs/telemetry.md`](docs/telemetry.md) 与 [`docs/backup-and-migration.md`](docs/backup-and-migration.md)。

项目开发中遇到的 UI、异步状态、RAG、联网、流式传输、跨平台依赖和配置安全问题，以及对应解决过程，见 [`docs/开发问题与解决记录.md`](docs/开发问题与解决记录.md)。
