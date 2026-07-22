from __future__ import annotations

from typing import Dict, Mapping, Sequence

from local_course_agent.retrieval.citations.labels import (
    CITATION_RE,
    build_citation_quote_map,
    label_sort_key,
)
from local_course_agent.retrieval.citations.schema import ClaimCheck
from local_course_agent.retrieval.citations.tokenization import (
    is_assertive_claim,
    split_sentences,
    tokenize,
)


def check_citations(
    answer: str,
    citations: Sequence[Mapping],
    *,
    min_overlap: float = 0.18,
    min_claim_tokens: int = 4,
) -> Dict:
    """Validate that assertive answer sentences are backed by cited quotes."""
    citation_quotes = build_citation_quote_map(citations)
    checks = [
        check_sentence(sentence, citation_quotes, min_overlap=min_overlap, min_claim_tokens=min_claim_tokens)
        for sentence in split_sentences(answer)
    ]
    unsupported = [item for item in checks if item.assertive and not item.supported]
    uncited = [item for item in unsupported if item.reason == "missing_citation"]
    return {
        "supported": not unsupported,
        "claims": [item.as_dict() for item in checks],
        "unsupported_claims": [item.as_dict() for item in unsupported],
        "uncited_claims": [item.as_dict() for item in uncited],
        "citation_labels": sorted(citation_quotes.keys(), key=label_sort_key),
        "stats": {
            "claim_count": len(checks),
            "assertive_claim_count": sum(1 for item in checks if item.assertive),
            "unsupported_count": len(unsupported),
            "uncited_count": len(uncited),
        },
    }


def check_sentence(
    sentence: str,
    citation_quotes: Mapping[str, str],
    *,
    min_overlap: float,
    min_claim_tokens: int,
) -> ClaimCheck:
    labels = [label.upper() for label in CITATION_RE.findall(sentence)]
    claim_text = CITATION_RE.sub("", sentence).strip()
    claim_tokens = set(tokenize(claim_text))
    assertive = is_assertive_claim(claim_text, len(claim_tokens), min_claim_tokens)
    overlaps: Dict[str, float] = {}
    for label in labels:
        quote = citation_quotes.get(label, "")
        overlaps[label] = token_overlap(claim_text, quote)
    max_overlap = max(overlaps.values(), default=0.0)

    supported = True
    reason = "ok"
    if assertive and not labels:
        supported = False
        reason = "missing_citation"
    elif assertive and any(label not in citation_quotes for label in labels):
        supported = False
        reason = "unknown_citation"
    elif assertive and max_overlap < min_overlap:
        supported = False
        reason = "low_overlap"
    elif not assertive:
        reason = "non_assertive"

    return ClaimCheck(
        sentence=sentence,
        labels=labels,
        assertive=assertive,
        token_count=len(claim_tokens),
        max_overlap=max_overlap,
        overlaps=overlaps,
        supported=supported,
        reason=reason,
    )


def token_overlap(claim: str, quote: str) -> float:
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 0.0
    quote_tokens = set(tokenize(quote))
    if not quote_tokens:
        return 0.0
    return len(claim_tokens & quote_tokens) / len(claim_tokens)
