from __future__ import annotations

from typing import Dict, List, Sequence

from local_course_agent.learning.summary.models import SummaryEvidence


def normalize_summary_evidence(chunks: Sequence[Dict], *, max_text_chars: int = 900) -> List[SummaryEvidence]:
    evidence = []
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("context_text") or chunk.get("quote") or chunk.get("text") or "").strip()
        if not text:
            continue
        evidence.append(
            SummaryEvidence(
                label=f"S{index}",
                file_id=str(chunk.get("file_id") or chunk.get("file_name") or "unknown"),
                file_name=str(chunk.get("file_name") or "未知文件"),
                file_path=str(chunk.get("file_path") or ""),
                section_title=str(chunk.get("section_title") or ""),
                material_type=str(chunk.get("material_type") or ""),
                page=chunk.get("page"),
                chunk_index=int(chunk.get("chunk_index") or index),
                text=compact_summary_text(text, max_text_chars),
            )
        )
    return evidence


def compact_summary_text(text: str, max_chars: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."
