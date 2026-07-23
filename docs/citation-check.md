# Citation Check

`local_course_agent.retrieval.citation_check` provides the compatibility facade for a lightweight post-generation check for grounded answers. The implementation lives under `local_course_agent.retrieval.citations`, split into schema, label mapping, tokenization, checking, and postprocess adapters.

## Goal

The checker catches three common citation failures:

- Assertive sentences that do not include a citation label.
- Sentences that reference an unknown citation label.
- Sentences whose cited quote has too little token overlap with the claim.

It does not perform semantic entailment. A high overlap means the sentence shares enough lexical evidence with the quoted source; it does not prove the source fully supports the claim.

## API

```python
from local_course_agent.retrieval.citation_check import check_citations

result = check_citations(answer, citations)
```

For endpoint integration, use the post-processing adapter:

```python
from local_course_agent.retrieval.citation_check import postprocess_answer_with_citation_check

payload = postprocess_answer_with_citation_check(answer, citations, strict=False)
```

The adapter returns the answer, the full citation check result, and a top-level
`unsupported_claims` list. It is designed to be called after LLM generation and
before persisting or returning the assistant message.

With `strict=True`, unsupported claims are annotated with `（未找到引用支撑）`.
The adapter does not delete, reorder, or rewrite generated content.

`answer` is the generated Markdown/text answer. `citations` is the existing citation list, where each item may contain:

- `quote`: quoted source text used for overlap.
- `source_type`: `local`, `web`, or `summary`.
- `label` or `source_label`: optional explicit label such as `L1`.

When no explicit label exists, labels are inferred as:

- Local sources: `L1`, `L2`, ...
- Web sources: `W1`, `W2`, ...
- Summary sources: `S1`, `S2`, ...
- Positional fallback: `1`, `2`, ...

## Output

The return value is JSON-friendly:

```python
{
    "supported": False,
    "claims": [...],
    "unsupported_claims": [...],
    "uncited_claims": [...],
    "citation_labels": ["L1"],
    "stats": {
        "claim_count": 2,
        "assertive_claim_count": 1,
        "unsupported_count": 1,
        "uncited_count": 1,
    },
}
```

Each claim contains the sentence text, labels, assertive flag, token count, overlap scores, support status, and reason.

The post-processing adapter returns:

```python
{
    "answer": "页表保存虚拟页到物理页框的映射。（未找到引用支撑）",
    "citation_check": {...},
    "unsupported_claims": [...],
}
```

## Current Limits

- The checker uses sentence splitting and token overlap only.
- Advice, questions, headings, and explicit generic-knowledge markers are treated as non-assertive.
- Chinese tokenization is lightweight and based on characters plus bigrams.
- `ChatFlow` calls the post-processing adapter after answer generation and before persistence. Chat responses expose `citation_check` and `unsupported_claims`, and telemetry records the citation-check stage.
- Summary and other generated-artifact paths do not currently run this post-processing adapter.
