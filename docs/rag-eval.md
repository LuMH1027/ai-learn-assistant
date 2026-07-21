# RAG 评测集与回归报告

本评测框架用于本地验证课程 RAG 检索质量，不接入服务端接口，也不改变线上问答链路。它直接读取 `data/indexes/<course_id>.json`，对一组样例问题执行检索问答，并统计引用命中率和检索质量分布。

## 用例格式

评测用例是 JSON 列表，或包含 `cases` 字段的对象：

```json
{
  "cases": [
    {
      "id": "page-table-address-translation",
      "course_id": "os",
      "question": "页表如何帮助完成虚拟地址到物理地址的转换？",
      "expected_files": ["教材.md"],
      "min_quality": "partial",
      "tags": ["memory-management"]
    }
  ]
}
```

字段说明：

- `id`：稳定用例 ID，便于回归报告对比。
- `course_id`：课程索引 ID，对应 `data/indexes/<course_id>.json`。
- `question`：评测问题。
- `expected_files`：期望出现在引用中的资料文件名，支持写完整路径或 basename。
- `min_quality`：最低检索质量，取值为 `none`、`partial`、`sufficient`，默认 `partial`。
- `tags`：可选标签，用于后续按知识点或资料类型分组。

## 运行方式

先确保课程已经构建知识库，然后执行：

```bash
python3 scripts/rag_eval.py --cases path/to/rag-cases.json --index-dir data/indexes
```

输出 Markdown 报告：

```bash
python3 scripts/rag_eval.py --cases path/to/rag-cases.json --output /tmp/rag-eval.md
```

输出 JSON 报告：

```bash
python3 scripts/rag_eval.py --cases path/to/rag-cases.json --format json --output /tmp/rag-eval.json
```

如果所有用例通过，脚本返回退出码 `0`；只要有用例失败，返回退出码 `1`，方便接入 CI 或本地回归检查。

## 统计指标

报告包含：

- `pass_rate`：同时满足引用命中和最低检索质量要求的用例比例。
- `citation_hit_rate`：至少命中一个期望引用文件的比例。
- `first_citation_hit_rate`：第一条引用就是期望文件的比例。
- `sufficient_rate`：检索质量达到 `sufficient` 的比例。
- `average_top_score`：第一条引用的平均检索分数。
- `quality_counts`：`none`、`partial`、`sufficient` 分布。

每条用例会列出返回文件、缺失的期望文件、检索质量和 top score。第一阶段只评测“是否检索到正确证据”，暂不评价 LLM 生成文本质量。
