# 多对话与本地存储

每门课程可以包含多个对话。对话之间独立保存消息和压缩记忆；课程笔记、掌握度和课程索引仍由整门课程共享。

## 用户行为

- 在左侧“对话”区域新建、切换、重命名或删除对话。
- 新对话发送第一条用户消息后，会自动使用该消息前 24 个字符作为标题。
- 切换对话只加载该对话的消息和记忆。
- 每个对话的输入草稿、待发送附件、流式回答和停止按钮彼此独立；在一个对话生成回答时，可以切到另一个对话继续发送消息。
- 切换对话不会丢弃后台流式输出；回到原对话后会继续显示已经生成的内容。
- “清空记忆”只清空当前对话的消息和 `memory.md`，不删除课程资料、其他对话或课程笔记。
- 删除最后一个对话时，存储层会自动创建一个空白新对话；当前前端在只剩一个对话时禁用删除按钮。
- 正在生成回答的对话暂时不能删除，需要先停止或等待生成结束。

## HTTP API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/courses/{course_id}/conversations` | 列出对话 |
| POST | `/api/courses/{course_id}/conversations` | 新建对话，可传 `title` |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}` | 重命名对话 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/delete` | 删除对话 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/read` | 标记已读 |
| GET | `/api/courses/{course_id}/conversations/{conversation_id}/messages` | 读取消息 |
| GET | `/api/courses/{course_id}/conversations/{conversation_id}/memory` | 读取压缩记忆 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/chat` | 在指定对话中问答 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/summary` | 生成摘要并写入该对话 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/quiz` | 生成练习题并写入该对话 |
| POST | `/api/courses/{course_id}/conversations/{conversation_id}/memory/clear` | 清空指定对话 |

未带 `/conversations/{id}` 的旧课程消息、记忆、聊天和学习产物接口继续映射到默认对话，用于兼容旧客户端。

## 文件布局

```text
data/course_memory/<course_id>/
├─ conversations.json
├─ conversations/
│  ├─ default/
│  │  ├─ messages.json
│  │  └─ memory.md
│  └─ conv-<id>/
│     ├─ messages.json
│     └─ memory.md
├─ notes.json
├─ mastery.json
├─ messages.json       # 旧版兼容数据，迁移后不再是主要写入位置
└─ memory.md           # 旧版兼容数据，迁移后不再是主要写入位置
```

`conversations.json` 保存标题、创建/更新时间、消息数和未读数。对话 ID 经过安全化后才用于目录名。

## 旧数据迁移

第一次列出对话时，如果还没有 `conversations.json`，存储层会创建 `default` 对话，并把旧版课程级 `messages.json` 和 `memory.md` 复制到 `conversations/default/`。有历史内容时标题为“历史对话”，没有内容时为“新对话”。迁移不会删除旧文件，因此回滚旧版本时仍可读取原数据。

备份工具包含整个 `course_memory/**`，因此会覆盖对话清单、每个对话的消息和记忆，以及课程级笔记与掌握度；真实 `config.json` 和聊天附件不在备份范围内。
