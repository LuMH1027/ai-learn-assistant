# RAG 检索策略

## 目标与回答边界

系统采用“课程资料优先，模型知识补充”的两层回答策略：

1. 检索到课程证据时，先基于课程资料回答，资料支持的结论必须带引用编号。
2. 课程资料只覆盖部分问题时，模型可以增加“补充知识”小节，但必须说明该部分不是课程原文，且不能附课程引用。
3. 未检索到课程证据时，模型可以使用通用知识回答，但必须先声明“本回答未找到课程资料依据”。
4. 未配置模型或模型调用失败时，保留本地回退回答，不把本地模板伪装成模型知识。

## 按需联网与来源融合

联网不是每轮固定执行。系统先完成本地检索，再根据以下信号决定是否调用 Web Search MCP：

- 本地证据质量为 `none` 或 `partial`；
- 问题包含“最新、目前、近期、联网”等时效或显式联网意图；
- 问题出现明确年份，需要核对可能变化的信息。

本地证据充分且没有时效要求时跳过联网。搜索只发送学生问题，不发送课程原文或附件内容。网页工具返回内容按不可信数据处理：只接受 `http/https` URL 的结果，忽略其中试图改变系统规则或要求执行操作的指令。

融合回答使用两套编号：`[L1]` 表示本地课程来源，`[W1]` 表示网页来源。网页来源在界面中显示为可点击外链；课程来源继续打开本地预览。MCP 调用状态会记录在 Agent 处理过程里。

聊天接口使用 SSE 流依次发送 `status`、`delta` 和 `done` 事件，并通过 HTTP/1.1 chunked transfer 立即刷新。前端异步消费每个 delta，在同一网络分块包含多个 token 时也会逐个让出浏览器绘制帧；模型不支持 streaming 时仍保留阶段反馈并回退到普通生成。

## 当前已实现

检索链路保持 Python 标准库实现，不增加本地数据库依赖；向量侧支持 OpenAI-compatible embedding provider，未配置时使用本地确定性 embedding fallback：

```text
问题
  -> 中文词组、2/3 字 n-gram 与英文词切分
  -> BM25 正文排序 + 精确短语排序 + 文件名元数据排序
  -> 加载持久向量索引并执行 dense search
  -> Reciprocal Rank Fusion (RRF) 合并 sparse/dense 多个排名
  -> Maximal Marginal Relevance (MMR) 去除近重复结果、增加来源多样性
  -> 相邻片段扩展上下文
  -> 最多 4 条课程证据进入模型
```

- **BM25**：加入文档长度归一化和词频饱和，避免重复堆砌某个词的片段占据首位。
- **多路召回**：正文相关性、精确短语和文件名命中分别排序，降低单一路径漏检的风险。
- **持久向量索引**：构建课程索引时同步写入 `<course_id>.vector.json`；查询时优先读取持久向量，失败时回退到 lexical/rerank。
- **真实 embedding provider**：配置 `ai.embedding_model` 后调用 `{ai.base_url}/embeddings`；未配置时使用本地 hash embedding，保证离线可运行。
- **RRF**：用排名而非不同检索器的原始分数做融合，避免分数量纲不一致。
- **MMR**：在相关性与结果差异之间取舍，减少 4 条引用都来自同一份文件的相似段落。
- **相邻上下文**：命中片段前后各补一个同文件、同页片段，缓解固定切块截断定义或推导过程的问题。
- **生成内容隔离**：`AI生成/` 中的摘要和练习题仍可预览，但构建知识库时不会重新索引；旧索引中的生成文件也会在查询时过滤，避免模型输出循环成为后续回答的“课程证据”。
- **索引兼容**：旧 JSON 索引在查询时按新分词规则重新计算 token，不要求用户立即重建知识库。

## 调研结论与后续路线

以下方法有明确研究依据；其中 sparse/dense 融合和基础评测已经落地，剩余方向适合作为下一阶段升级：

| 优先级 | 策略 | 适合解决的问题 | 接入建议 |
| --- | --- | --- | --- |
| P1 | BGE-M3 混合检索 | 中文同义表达、跨语言资料、长文档语义召回 | 当前已支持 OpenAI-compatible embedding；后续可补 multi-vector 与专门中文模型默认配置 |
| P1 | Cross-encoder 或 ColBERTv2 重排 | 召回结果主题相近，但与问题的具体关系不同 | 仅重排前 20 条，控制延迟；低配设备可关闭 |
| P1 | 检索与答案评测集 | 无法量化“改完是否更准” | 当前已统计引用命中、检索质量、答案术语覆盖、禁用词和引用支撑；后续可加入人工标注答案分 |
| P2 | HyDE / 多查询改写 | 学生问题口语化、与教材术语不一致 | 由模型生成假设答案或 2-3 个检索改写，只用于检索；仍以真实课程片段作为最终证据 |
| P2 | RAPTOR 层次索引 | 跨章节总结、综合题、多步推理 | 为长教材生成章节级和课程级摘要树，与原始片段联合检索 |
| P2 | CRAG / Self-RAG 式检索评估 | 低相关证据误导生成、固定检索条数不合理 | 增加相关性/充分性判定，按置信度决定继续检索、补充知识或直接回答 |

不建议把整本教材直接塞入长上下文。研究显示，相关信息处于长上下文中间时，模型利用效果可能明显下降；检索后只提供少量、高质量、去重复且保留邻接关系的证据更稳妥。

## 参考资料

- Cormack, Clarke, & Buettcher (2009), [Reciprocal Rank Fusion](https://doi.org/10.1145/1571941.1572114).
- Carbonell & Goldstein (1998), [Maximal Marginal Relevance](https://doi.org/10.1145/290941.291025).
- Gao et al. (2022), [HyDE: Precise Zero-Shot Dense Retrieval without Relevance Labels](https://arxiv.org/abs/2212.10496).
- Santhanam et al. (2022), [ColBERTv2](https://arxiv.org/abs/2112.01488).
- Chen et al. (2024), [M3-Embedding / BGE-M3](https://arxiv.org/abs/2402.03216).
- Sarthi et al. (2024), [RAPTOR](https://arxiv.org/abs/2401.18059).
- Asai et al. (2023), [Self-RAG](https://arxiv.org/abs/2310.11511).
- Yan et al. (2024), [Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884).
- Liu et al. (2023), [Lost in the Middle](https://arxiv.org/abs/2307.03172).

## 验收建议

RAG 改动应先跑固定评测集，而不是只看单次聊天效果。至少覆盖：教材原词问题、同义改写、跨段问题、跨文件问题、课程外问题和无法回答的问题。课程外问题用于验证通用知识回退，无法回答的问题用于验证模型不会伪造课程引用。答案级用例应补 `expected_terms`、`forbidden_terms` 和 `max_unsupported_claims`。
