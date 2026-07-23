# Course Dashboard

`local_course_agent.learning.dashboard` provides a pure aggregation layer for the course dashboard. It does not read files, call the RAG engine, mutate course state, or depend on the HTTP server.

The HTTP server exposes this aggregation through:

```http
GET /api/courses/:id/dashboard
```

The route is read-only. It loads the course tree from the current `AppContext.find_course`, messages/notes from `AppContext.store`, estimates index stats from `data/indexes/:course_id.json`, and returns:

```json
{
  "dashboard": {
    "course": {},
    "recent_activity": [],
    "materials": {},
    "mastery": {},
    "generated_artifacts": {}
  }
}
```

## Function

```python
from local_course_agent.learning.dashboard import build_course_dashboard

payload = build_course_dashboard(
    course=course,
    messages=messages,
    notes=notes,
    mastery_state=mastery_state,
    index_stats=index_stats,
)
```

Inputs are plain dictionaries/lists already used by the scanner, store, and index jobs:

- `course`: scanned course tree with `children`.
- `messages`: chat messages with `role`, `content`, and `created_at`.
- `notes`: note records with `title`, `content`, and `created_at`.
- `mastery_state`: optional course mastery state from `AppStore.get_mastery_state`.
- `index_stats`: optional index metadata such as `indexed_files`, `total_chunks`, `schema_version`, and `tokenizer_version`.

## Payload

The returned dashboard has five product-facing sections:

- `learning_progress`: retained as a zero-value compatibility field; the learning plan feature is no longer exposed.
- `recent_activity`: recent messages, notes, and generated artifacts sorted by timestamp.
- `materials`: source material file count, byte size, extension distribution, generated file count, and index stats.
- `review_queue`: retained as an empty compatibility field; mastery due reviews are shown from `mastery`.
- `mastery`: average score, tracked point count, level counts, due review count, open mistake count, weakest points, and due reviews.
- `generated_artifacts`: total generated files plus summary/quiz/other counts and the latest generated artifact.

Generated artifacts are detected from files under the `AI生成` folder. They are counted separately from source materials so dashboard stats match the RAG rule that generated outputs should not be reindexed as course evidence.

## Server Integration

`server.py` calls `build_course_dashboard(...)` after loading:

- course tree from the scanner/cache
- messages and notes from `AppStore`
- mastery state from `AppStore.get_mastery_state`
- index stats from the knowledge base index file

Index stats support both the current object-shaped index payload and the legacy list-shaped payload. Missing or unreadable indexes report zero indexed files/chunks instead of failing the dashboard route.

## Frontend Status

The Pinia course store still exposes `loadDashboard()` and keeps the latest payload in `course.dashboard` for API compatibility. It calls:

```http
GET /api/courses/:id/dashboard
```

and applies the response only when the selected course and root version still match the original request. Switching courses or changing the root clears the dashboard state.

The current `CourseSidebar.vue` does not call or render the dashboard. The visible sidebar contains courses, conversations, the current file tree, a compact configuration summary, and the upload drop zone. Therefore the following aggregation data is backend-only in the current UI:

- indexed/source material count
- indexed chunk count
- average mastery score
- a compact mastery block with due review count, open mistake count, weakest mastery points, and per-point correct/wrong actions
- latest activity

The API and store actions remain available for tests or a future UI, but user and acceptance documentation must not describe a visible “课程概览” or mastery control area.
