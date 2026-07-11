# 本地课程 RAG Agent 学习助手

这是一个可在 Windows 本地部署的课程资料浏览与 AI 学习助手原型。用户选择一个资料根目录后，系统会按“一级文件夹 = 一门课程”的规则识别课程，并在网页中展示课程文件树。点击 PDF 可以直接预览，构建知识库后可在每门课程内进行独立问答、引用溯源和课程记忆记录。

当前版本强调本地可运行和课程设计验收可展示，因此核心服务采用 Python 标准库 HTTP 服务、文件型记忆、JSON 轻量索引、浏览器原生前端。环境中如果已安装 `pypdf`，PDF 会抽取文本用于问答；配置 MinerU 后会优先使用 MinerU 解析 PDF。

## 核心能力

- 根据本地文件夹结构自动识别课程。
- 在网页左侧展开课程和多级文件树。
- 点击 PDF 通过独立窗口预览，点击 TXT/MD 显示文本。
- 每门课程独立构建知识库。
- 每门课程独立会话、独立记忆、独立笔记扩展接口。
- 可在页面中保存课程笔记，形成简单学习空间。
- 课程 Agent 支持答疑模式、启发模式、作业提示模式、复习模式。
- 支持一键生成课程摘要和练习题。
- 回答附带来源文件、页码或片段编号。
- 无资料依据时明确提示，避免伪造答案。
- 可选接入硅基流动 Kimi-K2.6，配置写在本地 `data/config.json`。
- PDF 自动尝试 MinerU Agent 轻量解析 API，失败时降级本地 `pypdf`。
- 支持拖文件加入课程资料，也支持拖进聊天框作为临时附件让 AI 读取。

## 依赖说明

### 必需环境

- Python 3.9 或以上。
- Chrome、Edge 或其他现代浏览器。
- 一个本地课程资料文件夹，例如 `D:\StudyMaterials`。

本项目没有 Node.js、Vue、MySQL、Redis、向量数据库等强制依赖。前端是原生 HTML/CSS/JavaScript，后端主要使用 Python 标准库，方便同学直接在 Windows 本地运行。

### 建议安装的 Python 依赖

建议安装：

```bash
pip install -r requirements.txt
```

当前 `requirements.txt` 只有：

```text
pypdf>=4.0.0
```

`pypdf` 的作用是在 MinerU API 不可用、网络失败或未配置 token 时，作为本地 PDF 文本抽取的降级方案。如果不安装，系统仍能启动和浏览课程文件，但 PDF 入库问答效果会变弱。

### 可选外部服务

- 硅基流动 Kimi-K2.6 API：用于生成更自然的课程问答，也用于截图问答。没有配置时，系统会使用本地轻量 RAG 回答。
- MinerU token：用于解析 PDF，尤其是表格、公式、版面更复杂的资料。当前开发测试阶段建议 PDF 小于 20 页。

### 配置示例文件

`data/` 目录里提供了可上传给同学的脱敏示例：

```text
data/config.example.json
```

同学第一次运行时，可以复制这个文件为本地真实配置：

```bat
copy data\config.example.json data\config.json
```

macOS/Linux：

```bash
cp data/config.example.json data/config.json
```

然后打开 `data/config.json`，修改这些信息：

- `root_folder`：自己的课程资料根目录，例如 `D:/StudyMaterials`。
- `ai.api_key`：自己的硅基流动 API Key；没有 Key 可以先留空，系统会退回轻量回答。
- `ai.model`：建议使用 `Pro/moonshotai/Kimi-K2.6`。文本问答和截图问答都使用这一套模型配置。
- `mineru.token`：自己的 MinerU token；没有 token 时，系统会尝试本地 `pypdf` 降级解析。

不要把真实的 `data/config.json` 发给别人或提交到仓库。`.gitignore` 会忽略 `data/` 里的运行数据，只放行 `data/config.example.json`。

### 不需要安装的组件

- 不需要安装 Node.js 或 npm。
- 不需要安装数据库，聊天记录、课程记忆和笔记都保存在本地文件里。
- 不需要安装向量数据库，当前版本使用本地 JSON 轻量索引。
- 不需要单独部署前端，运行 `run.py` 后浏览器访问本地地址即可。

## 快速启动

Windows 第一次运行建议先安装 PDF 降级解析依赖：

```bat
py -m pip install -r requirements.txt
```

然后启动：

```bat
start.bat
```

macOS/Linux 第一次运行建议先安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

然后启动：

```bash
python3 run.py
```

启动后打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 本地资料目录要求

系统按一级文件夹识别课程，例如：

```text
D:\StudyMaterials
├─ 操作系统
│  ├─ 教材
│  │  └─ chapter1.pdf
│  ├─ 课件
│  │  └─ process.pdf
│  └─ notes.md
├─ 数据结构
│  ├─ stack.pdf
│  └─ queue.txt
└─ 高等数学
   └─ limit.pdf
```

在网页顶部输入 `D:\StudyMaterials`，点击“设置目录”，系统会自动展示“操作系统、数据结构、高等数学”三门课程。

支持的文件类型：

- `.pdf`
- `.txt`
- `.md`
- `.markdown`
- `.docx`，当前轻量版只识别文件，完整解析建议后续接入 DOCX 解析器或转 PDF。
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`
- `.gif`
- `.bmp`

## 基本使用流程

1. 启动系统并打开网页。
2. 在顶部输入资料根目录。
3. 点击“设置目录”。
5. 左侧点击课程名，展开文件树。
6. 点击 PDF 文件，通过独立窗口预览。
7. 点击“构建知识库”，系统抽取当前课程文件内容并建立课程索引。
8. 在右侧课程 Agent 中选择答疑、启发、作业提示或复习模式并提问。
9. 可以拖文件到左侧课程资料区，加入当前课程资料。
10. 可以拖文件到聊天框，作为临时附件让 AI 读取。
11. 点击“生成摘要”或“生成练习题”，快速得到复习材料。
12. 查看回答和引用来源。
13. 点击引用来源，可打开对应文件预览。
14. 在“课程笔记”区保存重点、错题或 AI 回答。

## 可选 AI 与 MinerU 配置

系统默认不依赖大模型，也可以完成课程浏览、资料索引和带引用的轻量问答。若要接入硅基流动 Kimi，请编辑本地配置文件：

```text
data/config.json
```

硅基流动 Kimi 示例：

```json
{
  "root_folder": "D:/StudyMaterials",
  "ai": {
    "provider": "openai_compatible",
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "sk-你的硅基流动Key",
    "model": "Pro/moonshotai/Kimi-K2.6"
  },
  "mineru": {
    "auto": true,
    "api_enabled": true,
    "language": "ch",
    "token": "你的MinerU Token"
  }
}
```

截图问答说明：

- 普通文本问答和截图问答都使用 `ai.provider/base_url/api_key/model` 这一套配置。
- 如果拖入截图，系统会把图片作为聊天附件发给 Kimi。
- 如果接口返回失败或图片过大，系统会提示无法直接读取图片内容，可以把截图里的文字复制到聊天框。

系统会先检索课程资料，再把少量引用片段发给配置的大模型生成更自然的回答。大模型不可用时会自动退回本地轻量回答。

PDF 解析会自动优先尝试 MinerU Agent 轻量解析 API。该接口会上传 PDF 到 MinerU 获取 Markdown 结果；如果网络不可用、文件过大或解析失败，会自动降级到本地 `pypdf`。

## 推荐演示问题

完成知识库构建后，可以在某门课程内尝试：

```text
这门课的第一章主要讲了什么？
```

```text
进程和线程有什么区别？请根据资料回答。
```

```text
帮我生成 5 道复习题。
```

```text
这个概念在哪个文件里出现过？
```

## 数据保存位置

运行后系统会自动创建：

```text
data/
├─ course_memory/
│  └─ <course_id>/
│     ├─ messages.json
│     ├─ memory.md
│     └─ notes.json
├─ config.json
├─ chat_uploads/
└─ indexes/
```

- `config.json` 保存资料根目录。
- `course_memory/` 按课程保存聊天记录、课程记忆和笔记；想清空某门课的记忆，删除对应课程文件夹或其中某个文件即可。
- `chat_uploads/` 保存拖进聊天框的临时阅读附件。
- `indexes/` 保存每门课程的轻量知识库索引。
- 生成的摘要和练习题会保存到对应课程目录的 `AI生成/` 文件夹，可在文件树中预览。

## 后续升级方向

- PDF 解析升级为 MinerU，保留公式、表格、页码和版面结构。
- 向量库升级为 ChromaDB，实现 embedding 检索。
- 模型接入硅基流动 Kimi OpenAI-compatible API。
- 前端升级为 Vue3，保留当前三栏交互结构。
- 增加登录、课程资源审核、后台统计，扩展为完整课程资源共享平台。
