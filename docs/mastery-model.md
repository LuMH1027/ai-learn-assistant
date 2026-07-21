# 知识点掌握度与错题闭环模型

本文档描述 `local_course_agent.learning.mastery` 的纯数据模型。当前切片不接入 `store.py`、`server.py` 或前端，只提供后续持久化和接口开发可复用的 schema 与更新函数。

## 目标

- 以知识点为粒度记录学习状态。
- 根据答题结果调整掌握度分数。
- 答错时生成错题记录。
- 根据掌握度和最近答题结果给出下一次复习时间。
- 所有输入输出都是可 JSON 序列化的 `dict` / `list`，便于后续直接写入本地文件或数据库。

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

核心入口是 `apply_answer_result()`：

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

## 后续接入建议

1. 在持久化层为每门课程增加 `mastery.json` 或等价字段。
2. 练习题批改后调用 `apply_answer_result()`。
3. RAG 引用可以作为 `source_ref` 写入知识点和错题。
4. 前端课程 Dashboard 可读取 `mastery` 聚合弱项、待复习项和未解决错题。
5. 后续可以把固定评分规则替换为可配置策略，但保持当前 schema 不变。
