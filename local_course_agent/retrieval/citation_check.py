from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence


CITATION_RE = re.compile(r"\[([A-Za-z]?\d+)\]")
WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

CHINESE_STOP_CHARS = set("的一是在和与或及了为把对中上下面里个种这那其有就都而被并")
UNCERTAIN_MARKERS = (
    "可能",
    "也许",
    "大概",
    "或许",
    "不一定",
    "建议",
    "可以",
    "请",
    "复习时",
    "下一步",
    "如果",
    "当",
)
SUPPLEMENT_MARKERS = ("补充知识", "通用知识", "资料未覆盖", "未找到课程资料依据")


@dataclass
class ClaimCheck:
    sentence: str
    labels: List[str]
    assertive: bool
    token_count: int
    max_overlap: float
    overlaps: Dict[str, float]
    supported: bool
    reason: str

    def as_dict(self) -> Dict:
        return {
            "sentence": self.sentence,
            "labels": self.labels,
            "assertive": self.assertive,
            "token_count": self.token_count,
            "max_overlap": round(self.max_overlap, 3),
            "overlaps": {label: round(score, 3) for label, score in self.overlaps.items()},
            "supported": self.supported,
            "reason": self.reason,
        }


def check_citations(
    answer: str,
    citations: Sequence[Mapping],
    *,
    min_overlap: float = 0.18,
    min_claim_tokens: int = 4,
) -> Dict:
    """Validate that assertive answer sentences are backed by cited quotes.

    The checker is intentionally lightweight and deterministic. It does not try
    to prove semantic entailment; it catches obvious missing citations and cited
    claims that share too little lexical evidence with their quoted sources.
    """
    citation_quotes = _build_citation_quote_map(citations)
    checks = [
        _check_sentence(sentence, citation_quotes, min_overlap=min_overlap, min_claim_tokens=min_claim_tokens)
        for sentence in split_sentences(answer)
    ]
    unsupported = [item for item in checks if item.assertive and not item.supported]
    uncited = [item for item in unsupported if item.reason == "missing_citation"]
    return {
        "supported": not unsupported,
        "claims": [item.as_dict() for item in checks],
        "unsupported_claims": [item.as_dict() for item in unsupported],
        "uncited_claims": [item.as_dict() for item in uncited],
        "citation_labels": sorted(citation_quotes.keys(), key=_label_sort_key),
        "stats": {
            "claim_count": len(checks),
            "assertive_claim_count": sum(1 for item in checks if item.assertive),
            "unsupported_count": len(unsupported),
            "uncited_count": len(uncited),
        },
    }


def postprocess_answer_with_citation_check(
    answer: str,
    citations: Sequence[Mapping],
    *,
    strict: bool = False,
) -> Dict:
    """Attach citation check output to an answer payload.

    This is the integration-friendly adapter for chat or summary endpoints. In
    normal mode it leaves the generated answer untouched. In strict mode it
    annotates unsupported claims, but deliberately does not delete or rewrite
    the model output.
    """
    citation_check = check_citations(answer, citations)
    unsupported_claims = citation_check["unsupported_claims"]
    processed_answer = answer
    if strict and unsupported_claims:
        processed_answer = _annotate_unsupported_claims(answer, unsupported_claims)

    return {
        "answer": processed_answer,
        "citation_check": citation_check,
        "unsupported_claims": unsupported_claims,
    }


def split_sentences(answer: str) -> List[str]:
    sentences: List[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)、]\s+", "", line)
        if not line:
            continue
        sentences.extend(_split_line(line))
    return sentences


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in WORD_RE.finditer(text.lower()):
        value = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", value):
            chars = [char for char in value if char not in CHINESE_STOP_CHARS]
            tokens.extend(chars)
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        elif len(value) > 1:
            tokens.append(value)
    return tokens


def _check_sentence(
    sentence: str,
    citation_quotes: Mapping[str, str],
    *,
    min_overlap: float,
    min_claim_tokens: int,
) -> ClaimCheck:
    labels = [label.upper() for label in CITATION_RE.findall(sentence)]
    claim_text = CITATION_RE.sub("", sentence).strip()
    claim_tokens = set(tokenize(claim_text))
    assertive = _is_assertive_claim(claim_text, len(claim_tokens), min_claim_tokens)
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


def _build_citation_quote_map(citations: Sequence[Mapping]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    local_index = 0
    web_index = 0
    summary_index = 0
    plain_index = 0
    for citation in citations:
        quote = str(citation.get("quote") or "")
        explicit_label = str(citation.get("label") or citation.get("source_label") or "").strip().strip("[]")
        if explicit_label:
            labels[explicit_label.upper()] = quote
            continue

        source_type = citation.get("source_type", "local")
        if source_type == "web":
            web_index += 1
            labels[f"W{web_index}"] = quote
        elif source_type == "summary":
            summary_index += 1
            labels[f"S{summary_index}"] = quote
        else:
            local_index += 1
            labels[f"L{local_index}"] = quote

        plain_index += 1
        labels[str(plain_index)] = quote
    return labels


def _annotate_unsupported_claims(answer: str, unsupported_claims: Sequence[Mapping]) -> str:
    annotated = answer
    marker = "（未找到引用支撑）"
    for claim in unsupported_claims:
        sentence = str(claim.get("sentence") or "").strip()
        if not sentence or marker in sentence:
            continue
        target = sentence
        replacement = f"{sentence}{marker}"
        if target in annotated:
            annotated = annotated.replace(target, replacement, 1)
    return annotated


def _split_line(line: str) -> List[str]:
    parts: List[str] = []
    start = 0
    index = 0
    while index < len(line):
        char = line[index]
        if char in "。！？!?；;":
            end = index + 1
            while True:
                cursor = end
                while cursor < len(line) and line[cursor].isspace():
                    cursor += 1
                label_match = CITATION_RE.match(line, cursor)
                if not label_match:
                    break
                end = label_match.end()
            while end < len(line) and line[end].isspace():
                end += 1
            parts.append(line[start:end].strip())
            start = end
            index = end
            continue
        index += 1
    tail = line[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _is_assertive_claim(text: str, token_count: int, min_claim_tokens: int) -> bool:
    if token_count < min_claim_tokens:
        return False
    stripped = text.strip()
    if not stripped or stripped.endswith(("?", "？")):
        return False
    if any(marker in stripped for marker in SUPPLEMENT_MARKERS):
        return False
    if any(stripped.startswith(marker) for marker in UNCERTAIN_MARKERS):
        return False
    return True


def _label_sort_key(label: str):
    prefix_match = re.match(r"([A-Z]*)(\d+)$", label)
    if not prefix_match:
        return (label, 0)
    prefix, number = prefix_match.groups()
    return (prefix, int(number))
