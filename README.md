# 本地课程 RAG Agent 学习助手

这是一个可在 Windows 本地部署的课程资料浏览与 AI 学习助手原型。用户选择一个资料根目录后，系统会按“一级文件夹 = 一门课程”的规则识别课程，并在网页中展示课程文件树。点击 PDF 可以直接预览，构建知识库后可在每门课程内进行独立问答、引用溯源和课程记忆记录。

当前版本强调本地可运行和课程设计验收可展示，因此采用零下载依赖的实现：Python 标准库 HTTP 服务、SQLite、JSON 轻量索引、浏览器原生前端。环境中如果已安装 `pypdf`，PDF 会抽取文本用于问答；后续可接入 MinerU、ChromaDB、Ollama 和 Vue3。

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
- 可选接入 Ollama 本地大模型，配置写在本地 `data/config.json`。
- PDF 自动尝试 MinerU Agent 轻量解析 API，失败时降级本地 `pypdf`。
- 支持拖文件加入课程资料，也支持拖进聊天框作为临时附件让 AI 读取。

## 快速启动

Windows：

```bat
start.bat
```

macOS/Linux：

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

系统默认不依赖大模型，也可以完成课程浏览、资料索引和带引用的轻量问答。若要接入 DeepSeek 或 Ollama，请编辑本地配置文件：

```text
data/config.json
```

DeepSeek 示例：

```json
{
  "root_folder": "D:/StudyMaterials",
  "ai": {
    "provider": "openai_compatible",
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-你的DeepSeekKey",
    "model": "deepseek-chat"
  },
  "mineru": {
    "auto": true,
    "api_enabled": true,
    "language": "ch",
    "token": "你的MinerU Token"
  }
}
```

Ollama 示例：

```json
{
  "root_folder": "D:/StudyMaterials",
  "ai": {
    "provider": "ollama",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:7b"
  },
  "mineru": {
    "auto": true,
    "api_enabled": true,
    "language": "ch"
  }
}
```

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
- 模型接入 Ollama 和 OpenAI-compatible API。
- 前端升级为 Vue3，保留当前三栏交互结构。
- 增加登录、课程资源审核、后台统计，扩展为完整课程资源共享平台。
