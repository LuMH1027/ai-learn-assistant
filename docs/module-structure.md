# 模块层级结构约束

本项目不再用“新增一个同级 `*_xxx.py` 文件”的方式扩展功能。目录结构需要体现领域、入口、内部层级和外部适配边界。

## 基本规则

- 顶层 `local_course_agent/` 只放启动入口、跨领域门面和真正全局的基础模块。
- 一个领域能力超过两个协作模块时，必须建子包，例如 `api/chat/`、`learning/summary/`、`retrieval/rag/`、`retrieval/embeddings/`。
- 兼容入口放在子包的 `__init__.py`，负责 re-export 公开 API；业务实现放在子模块里。
- 子包内按职责命名，而不是按历史文件名横向增长：优先使用 `schema.py`、`policy.py`、`providers.py`、`adapters.py`、`store.py`、`runner.py`、`search.py`、`artifacts.py`。
- HTTP、文件系统、外部模型、联网能力都属于 adapter/provider 边界，不能塞回核心纯函数模块。
- 新增测试时直接 import 新结构路径；只有用户级稳定入口才继续通过门面 import。

## 当前领域布局

`api`：

- `api/chat/`：聊天编排、三模式策略、阶段上下文、附件 adapter、联网 adapter 和 LLM 答案生成；`api.chat` 只做兼容导出。
- `api/server/`：HTTP handler、routes 和 chat streaming adapter。
- `api/course/`：课程 API 索引、产物、上传、dashboard 和 mastery 适配，入口为 `api.course`。

`llm`：

- `llm/`：OpenAI-compatible chat client、JSON 配置解析、图片 data URL 和课程 prompt 构造，入口为 `llm`。

`parser`：

- `parser/`：文件类型路由、PDF/DOCX 解析、MinerU API/CLI fallback，入口为 `parser`。
- `mineru_api.py`：旧入口兼容门面，只做 re-export。

`learning`：

- `learning/dashboard/`：课程概览投影，入口为 `learning.dashboard`。
- `learning/indexing/`：课程索引构建、文档抽取、进度事件和后台任务快照。
- `learning/summary/`：LLM 课程摘要 pipeline，按 `models`、`normalization`、`pipeline`、`serialization`、`citations`、`prompts`、`runner` 拆分，入口为 `learning.summary`。
- `learning/mastery/`：掌握度与错题模型，按 `builders`、`normalization`、`policy`、`operations` 拆分，入口为 `learning.mastery`。
- `learning/service.py`：课程学习服务的协调入口，不能继续吸收 dashboard/summary/mastery 内部细节。
- `learning/study_plan.py`：保留的旧学习计划核心实现；当前没有公开 HTTP 路由或前端入口，不属于现行产品能力。

`retrieval`：

- `retrieval/rag/`：课程知识库编排、chunk store、检索搜索、答案合成和本地学习产物；`CourseKnowledgeBase` 位于 `knowledge_base.py`，`retrieval.rag` 只做兼容导出。
- `retrieval/embeddings/`：embedding 配置、模型协议、fake fallback、OpenAI-compatible provider、HTTP client、payload parser 和向量工具。
- `retrieval/reranking/`：候选重排协议、fallback、provider adapter、外部 provider 和候选文本转换，入口只做兼容导出。
- `retrieval/vector/`：向量索引构建、持久化、融合和数学工具。
- `retrieval/citations/`：引用检查与后处理。
- `retrieval/conversation_context/`：追问信号识别、历史轮次压缩、编号引用抽取和检索查询改写。
- `retrieval/evaluation/`：RAG 检索评测 schema、loader、metrics、runner 和 demo/report 兼容入口。

`evaluation`：

- `evaluation/gates/`：RAG demo baseline 的 ChatFlow gate、Summary gate、eval-only 替身和结果适配。
- `evaluation/quality/`：ChatFlow 和 Summary payload 质量检查及通用汇总工具。
- `evaluation/rag_quality.py`：旧入口兼容门面，只做 re-export。

`ops`：

- `ops/config_status/`：配置能力检查、文件系统检查和 capability payload。
- `ops/backup/`：备份收集、归档、恢复和 archive 安全校验。
- `ops/telemetry/`：telemetry recorder、recorders 和 payload 工具，入口为 `ops.telemetry`。

`store`：

- `store/`：文件型状态存储，按 conversations、messages、memory、notes、mastery、legacy study plan 和 locks 拆分，入口为 `store`。

`storage`：

- `storage/`：路径、安全 ID、JSON/文本编码与旧 SQLite/单会话数据迁移。

`web`：

- `web/`：MCP Streamable HTTP 客户端、联网策略、结果规范化与质量过滤；`web_search.py` 是稳定门面。

## 禁止回流

`tests/test_package_structure.py` 会失败以下回流模式：

- `learning/dashboard_*.py`
- `learning/summary_*.py`
- `learning/mastery_*.py`
- `retrieval/rag_*.py`
- `retrieval/embedding_*.py`
- `retrieval/rerankers.py`
- `retrieval/rag_eval.py`
- `retrieval/indexing.py`
- `retrieval/knowledge_store.py`
- `retrieval/vector_cache.py`
- `api/chat_generation.py`
- `api/chat_steps.py`
- `api/chat_uploads.py`
- `api/chat_web.py`
- `api/chat_llm_adapter.py`
- `api/course.py`
- `llm.py`
- `parser.py`
- `store.py`
- `retrieval/conversation_context.py`
- `learning/indexing.py`
- `ops/backup.py`
- `ops/telemetry_core.py`
- `ops/telemetry_recorders.py`
- `ops/telemetry_utils.py`

如果确实需要扩展这些能力，应该在对应子包下添加更具体的模块，并通过包入口暴露稳定 API。
