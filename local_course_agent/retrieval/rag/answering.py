from __future__ import annotations

from typing import Dict, List

from local_course_agent.retrieval.rag.artifacts import citation_from_chunk, summarize_evidence
from local_course_agent.retrieval.ranking import retrieval_quality, retrieval_trace


def no_basis_answer() -> Dict:
    return {
        "answer": "未在当前课程资料中找到可靠依据。建议先确认该课程资料是否已完成入库，或换一种更贴近资料原文的提问方式。",
        "citations": [],
        "mode": "no_basis",
        "retrieval_quality": "none",
    }


def grounded_answer(query: str, hits: List[Dict]) -> Dict:
    citations = [citation_from_chunk(hit) for hit in hits]
    evidence = "\n".join(f"{idx}. {hit['context_text']}" for idx, hit in enumerate(hits, start=1))
    answer = (
        "基于当前课程资料，可以这样理解：\n"
        f"{summarize_evidence(query, hits)}\n\n"
        "依据片段：\n"
        f"{evidence}"
    )
    max_coverage = max((hit.get("query_coverage", 0) for hit in hits), default=0)
    max_score = max((hit.get("score", 0) for hit in hits), default=0)
    quality = retrieval_quality(max_coverage, max_score, len(hits))
    return {
        "answer": answer,
        "citations": citations,
        "mode": "grounded",
        "retrieval_quality": quality,
        "retrieval_trace": retrieval_trace(hits),
    }
