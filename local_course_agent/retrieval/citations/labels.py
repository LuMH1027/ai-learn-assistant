from __future__ import annotations

import re
from typing import Dict, Mapping, Sequence


CITATION_RE = re.compile(r"\[([A-Za-z]?\d+)\]")


def build_citation_quote_map(citations: Sequence[Mapping]) -> Dict[str, str]:
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


def label_sort_key(label: str):
    prefix_match = re.match(r"([A-Z]*)(\d+)$", label)
    if not prefix_match:
        return (label, 0)
    prefix, number = prefix_match.groups()
    return (prefix, int(number))
