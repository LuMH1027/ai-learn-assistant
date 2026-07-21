# Course Dashboard

`local_course_agent.learning.dashboard` provides a pure aggregation layer for the course dashboard. It does not read files, call the RAG engine, mutate course state, or depend on the HTTP server.

The HTTP server exposes this aggregation through:

```http
GET /api/courses/:id/dashboard
```

The route is read-only. It loads the course tree from `CTX.find_course`, messages/notes/study plan from `CTX.store`, estimates index stats from `data/indexes/:course_id.json`, and returns:

```json
{
  "dashboard": {
    "course": {},
    "learning_progress": {},
    "recent_activity": [],
    "materials": {},
    "review_queue": [],
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
    study_plan=study_plan,
    index_stats=index_stats,
)
```

Inputs are plain dictionaries/lists already used by the scanner, store, and index jobs:

- `course`: scanned course tree with `children`.
- `messages`: chat messages with `role`, `content`, and `created_at`.
- `notes`: note records with `title`, `content`, and `created_at`.
- `study_plan`: plan items with `kind`, `status`, `estimated_minutes`, and timestamps.
- `index_stats`: optional index metadata such as `indexed_files`, `total_chunks`, `schema_version`, and `tokenizer_version`.

## Payload

The returned dashboard has five product-facing sections:

- `learning_progress`: total/done/doing/todo counts, percent complete, completed and remaining minutes, and the next active item.
- `recent_activity`: recent messages, notes, plan updates, and generated artifacts sorted by timestamp.
- `materials`: source material file count, byte size, extension distribution, generated file count, and index stats.
- `review_queue`: the current review-oriented queue, prioritizing `doing` and `review` items.
- `generated_artifacts`: total generated files plus summary/quiz/other counts and the latest generated artifact.

Generated artifacts are detected from files under the `AI生成` folder. They are counted separately from source materials so dashboard stats match the RAG rule that generated outputs should not be reindexed as course evidence.

## Server Integration

`server.py` calls `build_course_dashboard(...)` after loading:

- course tree from the scanner/cache
- messages and notes from `AppStore`
- study plan from `AppStore.list_study_plan`
- index stats from the knowledge base index file

Index stats support both the current object-shaped index payload and the legacy list-shaped payload. Missing or unreadable indexes report zero indexed files/chunks instead of failing the dashboard route.

## Frontend Integration

The course store exposes `loadDashboard()` and keeps the latest payload in `course.dashboard`.
The store calls:

```http
GET /api/courses/:id/dashboard
```

and applies the response only when the selected course and root version still match the original request. Switching courses or changing the root clears the dashboard state, matching the existing study-plan request behavior.

`CourseSidebar.vue` renders a compact "课程概览" section near the learning plan. It shows:

- learning progress percent
- indexed/source material count
- indexed chunk count
- generated artifact count
- next learning item
- top review items
- latest activity

The sidebar triggers `loadDashboard()` when the active course changes and also provides a manual refresh button. It does not reimplement aggregation client-side; it only displays the backend payload.
