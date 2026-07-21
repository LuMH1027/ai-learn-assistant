# 多轮对话上下文检索改写

## 目标

该模块提供一组纯函数，把“这个”“上面”“第二问”等追问改写成更适合 RAG 检索的自包含查询。它不访问存储、不调用模型、不直接改动 RAG 引擎；聊天接口会在调用知识库检索前使用改写后的 `retrieval_query`。

## 当前能力

- `detect_follow_up_signals(question)`：识别显式指代、上一轮引用和短追问。
- `recent_conversation_turns(messages, max_turns=3)`：从消息列表压缩最近 N 轮用户/助手对话。
- `extract_referenced_text(question, turns)`：当问题包含“第 N 问/第 N 题”时，从最近上下文提取对应编号小问。
- `build_contextual_retrieval_query(question, messages)`：组合以上逻辑，返回 `ContextualQuery`。

## 改写策略

完整问题不会被改写，例如“解释页表在地址转换中的作用”会原样返回。

追问会拼接最近上下文和当前问题，例如：

```text
对话上下文
用户：TLB 在页表地址转换中起什么作用？
助手：TLB 缓存常用页表项，减少访问页表次数。
当前追问
这个为什么更快？
```

编号追问会优先提取被引用的小问，例如“第二问怎么做？”会从“1. 解释页表。2. TLB 为什么能加速地址转换？3. 缺页中断流程。”中提取第二问，避免把其他小问混入检索查询。

## 边界

该模块只负责生成检索查询，不保证回答正确性。最终答案仍必须由课程资料检索结果和引用约束决定。当前实现是规则型、确定性的，适合作为最小可合并切片；后续可以在不破坏接口的前提下接入 LLM 查询改写或课程术语表。

## 聊天接口接入

`server.chat()` 会在保存当前用户消息前读取历史消息，并调用：

```python
build_contextual_retrieval_query(question, previous_messages)
```

保存到聊天记录的用户消息仍是原始 `question`。用于 `CTX.kb.answer(...)` 和后续 LLM grounded prompt 的输入是 `retrieval_query`；如果有聊天附件，附件文本会继续追加到这个检索查询后面。

响应中的 `retrieval_trace.contextual_query` 会包含：

- `used`：是否触发追问改写。
- `original_query`：用户原始问题。
- `retrieval_query`：实际用于课程资料检索的问题。
- `signals`：命中的追问信号，例如 `这个`、`第二问`。
- `context_turns_used`：用于改写的最近历史轮数。
- `referenced_text`：编号追问抽取到的具体小问，没有则为空。

同时，`trace` 会增加一条 `上下文` 步骤，标明本次是否使用上下文改写。

## 验证

```bash
python3 -m unittest tests.test_conversation_context -v
python3 -m unittest tests.test_server_llm_routing -v
```
