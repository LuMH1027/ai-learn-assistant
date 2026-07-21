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
- 检索采用标题感知切块、BM25、多路 RRF 融合、本地 rerank、MMR 去重和相邻上下文扩展。
- 回答优先使用课程资料；未检索到依据时，可由已配置模型明确标注后使用通用知识补充。
- 本地证据不足或问题具有时效性时，可按需调用 Web Search MCP，并显示可点击网页来源。
- 对话从请求接收、课程检索、联网到模型生成全程流式反馈，模型文本按 token 增量显示。
- 支持课程资料上传和聊天临时附件。
- 可选接入 OpenAI-compatible 模型与 MinerU；未配置时使用本地轻量能力。

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

支持 `.pdf`、`.txt`、`.md`、`.markdown`、`.docx`、`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif` 和 `.bmp`。Markdown 会在预览区渲染标题、列表、表格、引用和代码块；DOCX 当前仅识别文件，建议转换为 PDF 后入库。

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
- `ai.base_url/api_key/model`：OpenAI-compatible 模型配置。
- `web_search`：MCP Web Search 配置；`enabled` 开启后才会向外部服务发送学生问题。
- `mineru.token`：MinerU API token。

示例：

```json
{
  "root_folder": "D:/StudyMaterials",
  "ai": {
    "provider": "openai_compatible",
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "",
    "model": "Pro/moonshotai/Kimi-K2.6"
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
```

生成的摘要与练习题保存在对应课程的 `AI生成/` 文件夹。

检索索引会记录 schema/tokenizer 版本、章节标题、资料类型和来源路径；回答接口会返回检索 trace，便于核对命中片段、匹配词、分数和证据充分性。检索实现、研究依据与后续向量检索路线见 [`docs/rag-retrieval-strategy.md`](docs/rag-retrieval-strategy.md)。

项目开发中遇到的 UI、异步状态、RAG、联网、流式传输、跨平台依赖和配置安全问题，以及对应解决过程，见 [`docs/开发问题与解决记录.md`](docs/开发问题与解决记录.md)。
