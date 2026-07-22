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

- `api/chat/`：聊天编排、阶段上下文和 LLM 答案生成，入口为 `api.chat`。
- `api/server/`：HTTP handler、routes 和 chat streaming adapter。
- `api/course.py`：课程 API 服务入口；如果继续增长，应按 course 子域拆包。

`learning`：

- `learning/dashboard/`：课程概览投影，入口为 `learning.dashboard`。
- `learning/summary/`：LLM 课程摘要 pipeline，入口为 `learning.summary`。
- `learning/mastery/`：掌握度与错题模型，入口为 `learning.mastery`。
- `learning/service.py`：课程学习服务的协调入口，不能继续吸收 dashboard/summary/mastery 内部细节。

`retrieval`：

- `retrieval/rag/`：课程知识库编排、chunk store、检索搜索、答案合成和本地学习产物。
- `retrieval/embeddings/`：embedding 配置、模型协议、provider 和向量工具。
- `retrieval/reranking/`：候选重排协议、fallback、provider adapter 和候选文本转换。
- `retrieval/vector/`：向量索引构建、持久化、融合和数学工具。
- `retrieval/citations/`：引用检查与后处理。
- `retrieval/evaluation/`：RAG 检索评测 case、执行和报告适配入口。

`evaluation`：

- `evaluation/quality/`：ChatFlow 和 Summary 质量 gate 及通用汇总工具。
- `evaluation/rag_quality.py`：旧入口兼容门面，只做 re-export。

`ops`：

- `ops/config_status/`：配置能力检查、文件系统检查和 capability payload。
- `ops/telemetry/`：telemetry recorder、recorders 和 payload 工具，入口为 `ops.telemetry`。

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
- `ops/telemetry_core.py`
- `ops/telemetry_recorders.py`
- `ops/telemetry_utils.py`

如果确实需要扩展这些能力，应该在对应子包下添加更具体的模块，并通过包入口暴露稳定 API。
