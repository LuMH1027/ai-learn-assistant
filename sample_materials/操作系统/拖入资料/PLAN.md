# 本地课程 RAG Agent 学习助手方案（课程助手案例增强版）

## Summary
系统定位为：**Windows 本地课程资料浏览 + PDF 预览 + 独立课程 RAG Agent 学习助手**。用户选择资料根目录后，一级文件夹自动识别为课程；每门课程拥有独立文件树、PDF 预览、知识库、会话、记忆、笔记和错题记录。

## 可借鉴的课程助手案例
- Khanmigo：强调“不直接给答案”，而是通过追问、提示、引导学生自己思考；还提供教师侧的 lesson plan、quiz、rubric、exit ticket 等工具。可借鉴为“启发式答疑模式”和“生成练习题/学习目标/复习检测”。来源：[Khanmigo](https://www.khanmigo.ai/)
- CourseAssist：面向计算机课程，使用 RAG、意图分类、问题拆解，让回答对齐课程资料和学习目标。可借鉴为“先判断问题类型，再分解问题，再检索资料回答”。来源：[CourseAssist paper](https://arxiv.org/abs/2407.10246)
- RAGMan：为一门编程课配置多个作业专属 AI tutor，限制 AI 不直接给作业答案，而是给提示和建议。可借鉴为“课程内多模式助手”：答疑模式、作业提示模式、复习模式。来源：[RAGMan paper](https://arxiv.org/abs/2407.15718)
- KITE：面向算法学习，采用 intent-aware Socratic strategy，给提示、引导问题、逐步支架。可借鉴为“分层提示”：先给方向，再给关键概念，再给完整解释。来源：[KITE paper](https://arxiv.org/abs/2605.12988)
- Moodle AI Teaching & Learning Assistant：基于教师资料的 RAG，强调 human-in-the-loop 和降低幻觉。可借鉴为“答案必须基于课程资料，引用来源；资料无依据时明确说明”。来源：[Moodle RAG tutor paper](https://arxiv.org/abs/2605.06963)
- Kwame 2.0：课程论坛里的 AI 助教，结合 RAG 和人工监督，服务大规模在线编程教育。可借鉴为“问答日志、常见问题沉淀、后续扩展教师审核”。来源：[Kwame 2.0 paper](https://arxiv.org/abs/2603.29159)

## Key Features
- 前端三栏布局：
  - 左侧：课程列表和本地文件树。
  - 中间：PDF.js 文件预览，支持翻页、缩放、引用页码跳转。
  - 右侧：当前课程 Agent 会话。
- 每门课程独立空间：
  - 独立 Chroma collection。
  - 独立会话历史、课程记忆、笔记、错题、摘要。
  - 默认只检索当前课程资料。
- 课程 Agent 模式：
  - 答疑模式：基于资料回答，带引用。
  - 启发模式：参考 Khanmigo/KITE，不直接给最终答案，先给提示和追问。
  - 作业提示模式：参考 RAGMan，只给思路、相关知识点和检查方向。
  - 复习模式：生成复习提纲、重点难点、选择题、简答题。
  - 定位模式：帮用户找到某个概念在哪个 PDF、哪一页。
- 省 token 策略：
  - 向量检索 + BM25 混合召回。
  - rerank 后只送少量高质量片段。
  - 长文档先用章节摘要，必要时再读原文片段。
  - 课程记忆保存结构化信息，不直接塞完整聊天记录。

## Implementation Changes
- `CourseScanner`：按一级文件夹识别课程，保留多级文件结构。
- `DocumentParser`：PDF 用 MinerU，预览用 PDF.js，DOCX/MD/TXT 使用 Python 解析。
- `CourseRetriever`：支持当前课程过滤、文件过滤、页码引用、混合检索。
- `CourseAgent`：增加意图分类和模式选择：直接答疑、启发引导、作业提示、复习生成、资料定位。
- `CourseMemory`：记录学习目标、薄弱知识点、已读文件、常问问题、错题类型。
- `CitationNavigator`：前端点击引用后跳转到对应 PDF 文件和页码。

## Report Fit
- 需求分析：加入“课程助手不是通用聊天机器人，而是基于课程资料的学习支架系统”。
- 概要设计：系统结构图展示 PDF.js、MinerU、RAG 检索、CourseAgent、课程记忆模块。
- 详细设计：流程图增加“意图识别 → 检索 → 答案策略选择 → 引用生成 → 记忆更新”。
- 程序模块：代码只展示 CourseAgent 路由或 RAG 引用生成逻辑，不超过半页。
- 个人体会：可写项目借鉴成熟教育 AI 的启发式答疑、课程资料 grounding、引用溯源和省 token 检索策略。

## Test Plan
- 点击课程名能展开本地文件树。
- 点击 PDF 能预览，并能从 AI 引用跳转到对应页。
- 不同课程的会话和记忆互不影响。
- 答疑模式必须带引用。
- 启发模式先提示，不直接给最终答案。
- 作业提示模式不给完整作业答案，只给思路。
- 复习模式能生成提纲、重点、题目和答案。
- 无资料依据时明确提示，不编造。
