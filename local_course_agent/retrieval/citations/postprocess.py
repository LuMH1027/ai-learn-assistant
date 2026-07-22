from __future__ import annotations

from typing import Dict, Mapping, Sequence

from local_course_agent.retrieval.citations.checker import check_citations


def postprocess_answer_with_citation_check(
    answer: str,
    citations: Sequence[Mapping],
    *,
    strict: bool = False,
) -> Dict:
    """Attach citation check output to an answer payload."""
    citation_check = check_citations(answer, citations)
    unsupported_claims = citation_check["unsupported_claims"]
    processed_answer = answer
    if strict and unsupported_claims:
        processed_answer = annotate_unsupported_claims(answer, unsupported_claims)

    return {
        "answer": processed_answer,
        "citation_check": citation_check,
        "unsupported_claims": unsupported_claims,
    }


def annotate_unsupported_claims(answer: str, unsupported_claims: Sequence[Mapping]) -> str:
    annotated = answer
    marker = "（未找到引用支撑）"
    for claim in unsupported_claims:
        sentence = str(claim.get("sentence") or "").strip()
        if not sentence or marker in sentence:
            continue
        if sentence in annotated:
            annotated = annotated.replace(sentence, f"{sentence}{marker}", 1)
    return annotated
