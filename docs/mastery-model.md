# 知识点掌握度与错题闭环模型

本文档描述 `local_course_agent.learning.mastery` 的知识点掌握度与错题闭环模型。当前实现已接入课程级本地持久化、后端 API 和课程 Dashboard 汇总；模型函数仍保持纯数据输入输出，便于测试和后续扩展。

实现按职责拆分：

- `local_course_agent.learning.mastery.schema`：创建和规范化 state、knowledge point、mastery record、mistake record，并处理文本、引用和 ID 的稳定化。
- `local_course_agent.learning.mastery.policy`：定义分数边界、难度权重、分数增减、等级划分和复习间隔建议。
- `local_course_agent.learning.mastery`：兼容入口和薄编排层，继续导出旧调用方依赖的公开函数，同时串联 schema 与 policy 完成知识点 upsert、答题更新和错题订正。

## 目标

- 以知识点为粒度记录学习状态。
- 根据答题结果调整掌握度分数。
- 答错时生成错题记录。
- 根据掌握度和最近答题结果给出下一次复习时间。
- 所有输入输出都是可 JSON 序列化的 `dict` / `list`，便于后续直接写入本地文件或数据库。
- 每门课程的状态保存在 `data/course_memory/<course_id>/mastery.json`。
- 课程 Dashboard 会汇总平均掌握分、薄弱知识点、待复习数量和未解决错题数。

## State Schema

```json
{
  "schema_version": 1,
  "knowledge_points": [],
  "mastery": {},
  "mistakes": [],
  "created_at": "2026-07-21 10:00:00",
  "updated_at": "2026-07-21 10:00:00"
}
```

### Knowledge Point

```json
{
  "id": "kp-address",
  "title": "页表地址转换",
  "aliases": ["虚拟地址转换"],
  "source_refs": [
    {
      "file_name": "操作系统.md",
      "section_title": "分页存储",
      "page": "3",
      "chunk_id": "12"
    }
  ],
  "created_at": "2026-07-21 10:00:00",
  "updated_at": "2026-07-21 10:00:00"
}
```

### Mastery Record

`mastery` 是以知识点 ID 为 key 的对象：

```json
{
  "kp-address": {
    "point_id": "kp-address",
    "score": 62,
    "level": "familiar",
    "attempts": 3,
    "correct_count": 2,
    "wrong_count": 1,
    "streak": 1,
    "last_result": "correct",
    "last_answered_at": "2026-07-21 10:00:00",
    "next_review_at": "2026-07-25 10:00:00",
    "review_interval_days": 4,
    "updated_at": "2026-07-21 10:00:00"
  }
}
```

`level` 由 `score` 推导：

| 分数区间 | level |
| --- | --- |
| 0-39 | `weak` |
| 40-59 | `building` |
| 60-79 | `familiar` |
| 80-100 | `mastered` |

### Mistake Record

```json
{
  "id": "mistake-xxxxxxxxxxxx",
  "point_id": "kp-address",
  "question": "解释页表如何完成地址转换。",
  "user_answer": "直接查物理地址。",
  "expected_answer": "先用页号查页表得到页框号，再拼接页内偏移。",
  "source_ref": {
    "file_name": "操作系统.md",
    "section_title": "分页存储"
  },
  "status": "open",
  "review_count": 0,
  "created_at": "2026-07-21 10:00:00",
  "updated_at": "2026-07-21 10:00:00",
  "resolved_at": ""
}
```

## 更新规则

核心入口是 `apply_answer_result()`。它位于兼容入口 `learning.mastery`，内部先用 `mastery.schema.normalize_state()` 固定输入形态，再用 `mastery.policy.score_delta()` 和 `mastery.policy.review_suggestion()` 计算策略结果：

```python
next_state = apply_answer_result(
    state,
    point_id="kp-address",
    correct=False,
    question="解释页表如何完成地址转换。",
    user_answer="直接查物理地址。",
    expected_answer="先用页号查页表得到页框号，再拼接页内偏移。",
    difficulty="normal",
    confidence=0.6,
    timestamp="2026-07-21 10:00:00",
)
```

答对时：

- `score` 增加，接近 100 时增幅自动变小。
- `attempts`、`correct_count`、`streak` 增加。
- 不生成错题。
- 根据新分数给出下一次复习时间。

答错时：

- `score` 降低，当前分越高惩罚越明显。
- `attempts`、`wrong_count` 增加，`streak` 清零。
- 生成一条 `status = "open"` 的错题记录。
- 下一次复习固定建议为 1 天后。

## 接入点

### Store

`AppStore` 提供课程级读写入口：

- `get_mastery_state(course_id)`：读取并规范化 `mastery.json`，缺失时返回空状态。
- `upsert_mastery_knowledge_point(course_id, point)`：新增或合并知识点，同时确保存在 mastery record。
- `apply_mastery_answer_result(course_id, point_id, correct, **kwargs)`：写入一次答题结果，更新掌握分并在答错时记录错题。

### API

后端路由：

- `GET /api/courses/<course_id>/mastery` 返回 `{ "mastery": MasteryState }`。
- `POST /api/courses/<course_id>/mastery` 接受 `knowledge_point` 和/或 `answer_result`，返回 `{ "ok": true, "mastery": MasteryState }`。

示例：

```json
{
  "knowledge_point": {
    "id": "kp-address",
    "title": "页表地址转换",
    "aliases": ["虚拟地址转换"],
    "source_refs": [{ "file_name": "操作系统.md", "page": "3" }]
  },
  "answer_result": {
    "point_id": "kp-address",
    "correct": false,
    "question": "解释页表如何完成地址转换。",
    "user_answer": "直接查物理地址。",
    "expected_answer": "先用页号查页表得到页框号，再拼接页内偏移。",
    "difficulty": "normal",
    "confidence": 0.6
  }
}
```

### Dashboard

`GET /api/courses/<course_id>/dashboard` 的原有字段保持不变，并新增 `dashboard.mastery`：

```json
{
  "knowledge_point_count": 2,
  "tracked_count": 2,
  "average_score": 58,
  "weak_count": 1,
  "building_count": 0,
  "familiar_count": 1,
  "mastered_count": 0,
  "due_review_count": 1,
  "open_mistake_count": 1,
  "weakest_points": [],
  "due_reviews": []
}
```

前端课程概览使用该字段展示平均掌握分。`CourseSidebar.vue` 还渲染轻量“掌握度”区块，直接展示：

- `due_review_count` / `due_reviews`：待复习知识点数量与队列。
- `open_mistake_count`：仍未订正的错题数量。
- `weakest_points`：当前最薄弱知识点。

掌握度区块中的“对 / 错”按钮会调用既有 `POST /api/courses/<course_id>/mastery`，仅提交：

```json
{
  "answer_result": {
    "point_id": "kp-address",
    "correct": true
  }
}
```

请求成功后前端刷新 dashboard，让待复习数、未订正数和薄弱点回到后端汇总结果。

`difficulty` 支持：

| 难度 | 权重 |
| --- | --- |
| `easy` | 0.75 |
| `normal` | 1.0 |
| `hard` | 1.25 |

`confidence` 范围为 `0.0-1.0`。当前规则把它作为轻量系数处理，用于表达“答题结果的可信度”，不是用户主观自评的最终模型。

## 复习建议

`review_suggestion(score, correct, timestamp)` 根据分数和最近结果返回：

```json
{
  "next_review_at": "2026-07-25 10:00:00",
  "interval_days": 4,
  "reason": "掌握度中等，适合几天后巩固。"
}
```

默认间隔：

| 条件 | 间隔 |
| --- | --- |
| 最近答错 | 1 天 |
| score < 40 | 1 天 |
| score < 60 | 2 天 |
| score < 80 | 4 天 |
| score >= 80 | 7 天 |

## 后续扩展建议

1. 练习题批改后调用 `apply_answer_result()`。
2. RAG 引用可以作为 `source_ref` 写入知识点和错题。
3. 后续可以把固定评分规则替换为可配置策略，但保持当前 schema 不变。
