# 三模式与 ReAct 数据流

聊天学习模式统一为三种：

- `answer`：答疑，直接消除当前疑问。
- `guide`：启发提示，合并旧 `socratic` 与 `homework`，默认渐进披露。
- `review`：复习，组织知识结构并引导主动回忆。

旧客户端仍可发送 `socratic` 或 `homework`，后端会在请求入口归一为 `guide`，HTTP 响应也返回归一化后的模式。未知模式回退为 `answer`。

## 模式策略

后端在 `local_course_agent/api/chat/modes.py` 集中维护 `StudyModePolicy`，包含：

- `key`：规范枚举值。
- `label`：中文展示名。
- `planning_rules`：注入 ReAct planner，用来影响是否检索课程资料、是否联网、是否澄清。
- `response_rules`：注入 responder，用来影响最终回答结构、披露层级和复习组织方式。

共享工具规则仍只维护一份，模式策略以文本块注入，不复制三套 ReAct prompt。

## ReAct 数据流

1. 请求入口归一化 `mode`。
2. Planner 读取问题、最近对话、附件状态、已有 observation 和模式规划规则。
3. Planner 只返回 `final`、`course_search`、`web_search`、`course_and_web_search` 或 `clarify`，以及查询词和原因。
4. 工具调用结果进入 observation；如果 planner 再次请求已执行过的同类工具，流程停止重复调用并使用已有 observation。
5. `clarify` 直接返回澄清问题。
6. `final` 或达到最多三轮后，Responder 读取完整 evidence、最近对话和模式作答规则，生成最终回答并流式输出。`final` 是 planner 的终止 action，不是最终答案本身。
7. 模型不可用时走本地降级：答疑返回检索结果，启发提示返回方向和关键词，复习返回摘要、自测题和下一步动作。

这里的“模型不可用”指未配置模型或 client 被禁用。已配置模型后的瞬时连接错误最多共尝试五次，界面会显示重试进度；持续失败会返回请求错误。流式生成已经收到 token 后不会重放，以免重复内容。

## 对话与流事件

planner 和 responder 只读取当前 `conversation_id` 的最近消息。所有正常问题都会先经过 planner；简单问题由 planner 返回 `final` 后进入 responder，不在 planner 前固定回复。切换到同一课程的另一个对话后，追问改写、提示披露层级和记忆都会重新以该对话为边界。

流式接口可能发送：

- `status`：附件、思考、检索、联网、最终 responder 调用或 `llm_retry` 阶段。
- `thought`：planner 选择的 action、原因和可选查询词；前端显示在“当前思考”。
- `delta`：回答增量，前端实时渲染 Markdown。
- `error`：请求失败。
- `done`：最终答案、引用、trace、mode 和 telemetry。

## 启发提示披露

`guide` 默认不在第一轮直接代答：

- 首次或没有展示尝试：一级提示，只给思考方向。
- 已有一次有效尝试：二级提示，给关键条件、公式、关键词或中间步骤。
- 明确索要完整答案，或最近历史中已有至少两次有效尝试仍卡住：允许完整讲解，并解释关键转折。

这个规则由 responder prompt 执行；本地降级路径会用简单文本特征判断是否允许完整披露。
