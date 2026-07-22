# 章节级 Map-Reduce 摘要 Pipeline

当前实现已通过 `local_course_agent.learning.artifacts.generate_course_summary()` 接入课程摘要接口，并由 `local_course_agent.learning.service.generate_course_summary()` 保持旧导入兼容。纯函数式 pipeline 仍保持不读写文件、不直接创建网络 client 的边界，由学习产物服务注入现有 OpenAI-compatible LLM client，并在失败时降级到 single prompt 或本地抽取式摘要。

## 目标

课程摘要从“一组代表片段直接生成”升级为两阶段流程：

1. Map：按 `file_id + section_title` 聚合 evidence，对每个章节/文件生成章节摘要 prompt。
2. Reduce：把章节摘要归并为课程总摘要 prompt，保留原始 evidence 标签，例如 `[S1]`。

这样可以在资料较多时先压缩章节局部信息，再做课程级归纳，减少单次 prompt 过长和章节关系丢失。

## 模块边界

实现已从单文件拆成职责明确的子模块，`local_course_agent/learning/summary/` 是兼容入口和内部实现包：

- `local_course_agent/learning/summary/models.py`：定义 `SummaryEvidence`、`EvidenceGroup`、`MapSummary`。
- `local_course_agent/learning/summary/normalization.py`：负责 evidence normalize 和文本压缩。
- `local_course_agent/learning/summary/pipeline.py`：负责 evidence 分组和 pipeline payload 组装。
- `local_course_agent/learning/summary/serialization.py`：负责 dataclass 与 dict 的 round-trip。
- `local_course_agent/learning/summary/citations.py`：负责 summary citation payload。
- `local_course_agent/learning/summary/schema.py`：兼容导出旧 schema 入口。
- `local_course_agent/learning/summary/prompts.py`：负责 map/reduce prompt 构造，以及 evidence/map-summary block formatting。
- `local_course_agent/learning/summary/runner.py`：负责 `run_map_reduce_summary()` 状态机、LLM client 协议、高层 service adapter 和 fallback payload。
- `local_course_agent/learning/summary/__init__.py`：re-export 旧符号，保证 `from local_course_agent.learning.summary import ...` 继续可用。

兼容入口仍暴露以下核心函数：

- `summary.schema.normalize_summary_evidence(chunks)`：把 RAG chunk/citation 字典规范化为 `SummaryEvidence`。
- `summary.schema.group_evidence_by_section(evidence)`：按文件和章节聚合 evidence。
- `summary.prompts.build_map_prompt(course_name, group)`：生成单个章节的 map prompt。
- `summary.prompts.build_reduce_prompt(course_name, map_summaries)`：生成课程总摘要 reduce prompt。
- `summary.schema.build_summary_pipeline(chunks)`：返回纯字典结构，方便后续 API 集成和调试。
- `summary.runner.run_map_reduce_summary(chunks, llm_client, course_name=...)`：用注入的 LLM client 执行 map-reduce。
- `summary.runner.generate_map_reduce_course_summary(kb, course_id, course_name, ai_config, create_client)`：面向学习产物服务的高层适配函数，从 `kb.summary_chunks()` 取证据、创建 LLM client、返回可直接用于摘要接口的 payload。

`run_map_reduce_summary` 不读写文件，不读取配置，不创建网络 client。调用方需要传入满足以下协议的 client：

```python
class SummaryLLMClient:
    def enabled(self) -> bool: ...
    def generate(self, prompt: str) -> str | None: ...
```

`generate_map_reduce_course_summary` 同样不读写文件，也不直接导入 `learning/service.py` 或 `llm/`。调用方通过 `create_client(ai_config)` 注入现有 OpenAI-compatible client 工厂，避免在摘要 pipeline 中绑定服务层实现。

## 输入

输入是现有 RAG chunk 或 citation 形态的字典列表，优先读取：

- `context_text`
- `quote`
- `text`

元数据字段：

- `file_id`
- `file_name`
- `file_path`
- `section_title`
- `material_type`
- `page`
- `chunk_index`

缺失字段会使用安全默认值。

## 输出

`run_map_reduce_summary` 返回：

- `content`：最终课程摘要。
- `llm_status`：`used`、`empty`、`disabled` 或 `failed`。
- `map_summaries`：每个章节的中间摘要。
- `map_prompts`：实际生成的章节 prompt。
- `reduce_prompt`：实际生成的总摘要 prompt。
- `evidence_groups`：章节/文件聚合后的 evidence。

`generate_map_reduce_course_summary` 在上述字段基础上补充：

- `citations`：由 summary chunks 派生的引用信息，包含文件、页码、章节、片段和 quote。
- `status`：高层状态。成功时为 `used`；失败或不可用时可能是 `empty`、`disabled`、`failed`、`client_error`、`summary_error`。
- `fallback_needed`：布尔值。`status != "used"` 时为 `true`，服务层可据此沿用旧的本地摘要 fallback。
- `fallback_reason`：明确回退原因，例如 `no_summary_chunks`、`llm_disabled`、`llm_generation_failed`、`create_client_failed: ...`。

成功 payload 示例：

```json
{
  "content": "课程复习摘要\n\n## 总体脉络\n- ... [S1]",
  "llm_status": "used",
  "status": "used",
  "fallback_needed": false,
  "fallback_reason": "",
  "citations": [
    {
      "file_id": "net",
      "file_name": "网络.md",
      "section_title": "TCP",
      "location": "第 3 页",
      "quote": "TCP 通过确认、重传和序号提供可靠传输。"
    }
  ]
}
```

## 服务层接入

`local_course_agent.learning.artifacts.generate_course_summary()` 已按以下顺序执行摘要策略，`learning.service` 仅代理该入口以保持兼容：

1. 调用 `generate_map_reduce_course_summary(kb, course_id, course_name, ai_config, create_llm_client)`。
2. 当 `fallback_needed` 为 `false` 时返回 `summary_method = "map_reduce"`，并保留 `map_summaries` 与 `evidence_groups` 供调试。
3. 当 map-reduce 不可用但有代表片段时，使用 `llm.build_course_summary_prompt()` 走 single prompt 摘要，返回 `summary_method = "single_prompt"`。
4. 当模型不可用、生成失败或没有片段时，沿用 `kb.generate_summary()` 本地抽取式摘要，返回 `summary_method = "extractive"`。

`GET /api/courses/{course_id}/summary` 返回即时摘要 payload；`POST /api/courses/{course_id}/summary` 会把摘要写入课程目录的 `AI生成/*.md`，并保存一条助手消息。

## 验证

测试文件：`tests/test_summary_pipeline.py`

覆盖内容：

- evidence 按 file/section 分组。
- map prompt 和 reduce prompt 保留来源标签。
- LLM stub 按 map prompts -> reduce prompt 的顺序被调用。
- 空 evidence 与 disabled client 不触发生成。
- pipeline 输出纯字典，便于后续 API 集成。
- 高层函数可以直接用 `kb.summary_chunks()` 和 stub client 生成摘要 payload。
- 高层函数在 empty、disabled、client error 时返回明确 `fallback_needed` 与 `fallback_reason`。
- schema round-trip、prompt formatting 和 runner fallback helper 可从拆分模块直接测试。
