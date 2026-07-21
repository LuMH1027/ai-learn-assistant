from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple


EMPTY_SUMMARY_MESSAGE = "当前课程还没有可用于生成章节摘要的资料片段，请先构建知识库。"


class SummaryLLMClient(Protocol):
    def enabled(self) -> bool:
        ...

    def generate(self, prompt: str) -> Optional[str]:
        ...


class CourseSummaryKnowledgeBase(Protocol):
    def summary_chunks(self, course_id: str, limit: int = 6) -> List[Dict]:
        ...


@dataclass(frozen=True)
class SummaryEvidence:
    label: str
    file_id: str
    file_name: str
    file_path: str
    section_title: str
    material_type: str
    page: Optional[int]
    chunk_index: int
    text: str


@dataclass(frozen=True)
class EvidenceGroup:
    group_id: str
    file_id: str
    file_name: str
    section_title: str
    material_type: str
    evidence: Tuple[SummaryEvidence, ...]

    @property
    def title(self) -> str:
        return self.section_title or self.file_name or "未命名章节"


@dataclass(frozen=True)
class MapSummary:
    group_id: str
    title: str
    file_name: str
    section_title: str
    content: str
    evidence_labels: Tuple[str, ...]


def build_summary_pipeline(
    chunks: Sequence[Dict],
    *,
    max_groups: int = 12,
    max_evidence_per_group: int = 5,
    max_text_chars: int = 900,
) -> Dict:
    evidence = normalize_summary_evidence(chunks, max_text_chars=max_text_chars)
    groups = group_evidence_by_section(
        evidence,
        max_groups=max_groups,
        max_evidence_per_group=max_evidence_per_group,
    )
    return {
        "evidence": [evidence_item_to_dict(item) for item in evidence],
        "groups": [evidence_group_to_dict(group) for group in groups],
    }


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
                text=_compact_text(text, max_text_chars),
            )
        )
    return evidence


def group_evidence_by_section(
    evidence: Sequence[SummaryEvidence],
    *,
    max_groups: int = 12,
    max_evidence_per_group: int = 5,
) -> List[EvidenceGroup]:
    ordered: Dict[Tuple[str, str], List[SummaryEvidence]] = {}
    for item in evidence:
        key = (item.file_id or item.file_name, item.section_title or "")
        ordered.setdefault(key, []).append(item)

    groups: List[EvidenceGroup] = []
    for index, ((file_id, section_title), items) in enumerate(ordered.items(), start=1):
        first = items[0]
        groups.append(
            EvidenceGroup(
                group_id=f"G{index}",
                file_id=file_id,
                file_name=first.file_name,
                section_title=section_title,
                material_type=first.material_type,
                evidence=tuple(items[:max_evidence_per_group]),
            )
        )
        if len(groups) >= max_groups:
            break
    return groups


def build_map_prompt(course_name: str, group: EvidenceGroup) -> str:
    evidence_text = "\n\n".join(_format_evidence_block(item) for item in group.evidence)
    section = group.section_title or "无"
    return (
        "你是一个严谨的课程章节摘要助手。只基于给定资料片段总结，不要加入资料外知识，"
        "不要虚构原文没有的结论。\n"
        "请输出 Markdown，结构固定为：\n"
        "## 章节要点\n"
        "- 2-4 条要点，每条句末标注来源，如 [S1]。\n\n"
        "## 关键概念与关系\n"
        "- 提炼概念、条件、步骤或关系；证据不足时写“资料片段不足”。\n\n"
        "## 复习提醒\n"
        "- 写 1-2 条本章节复习时应回看原文的位置或边界。\n\n"
        f"课程名称：{course_name or '当前课程'}\n"
        f"文件：{group.file_name}\n"
        f"章节：{section}\n"
        f"资料片段：\n{evidence_text}\n"
    )


def build_reduce_prompt(course_name: str, map_summaries: Sequence[MapSummary]) -> str:
    summaries_text = "\n\n".join(_format_map_summary_block(item) for item in map_summaries)
    return (
        "你是一个严谨的课程总摘要助手。请只基于下列章节摘要做归纳，不要加入资料外知识，"
        "不要虚构章节、定义、结论或引用。\n"
        "请输出 Markdown，结构固定为：\n"
        "课程复习摘要\n\n"
        "## 总体脉络\n"
        "- 2-4 条概括章节之间的主题、先后关系或依赖关系。\n\n"
        "## 分章节重点\n"
        "- 按章节列出重点；每条保留来源标签，如 [S1]。\n\n"
        "## 易混点与复习提醒\n"
        "- 提炼跨章节容易混淆的边界；证据不足时明确写“资料片段不足”。\n\n"
        "## 下一步学习建议\n"
        "- 给出 2-3 条可执行复习动作。\n\n"
        f"课程名称：{course_name or '当前课程'}\n"
        f"章节摘要：\n{summaries_text}\n"
    )


def run_map_reduce_summary(
    chunks: Sequence[Dict],
    llm_client: SummaryLLMClient,
    *,
    course_name: str = "",
    max_groups: int = 12,
    max_evidence_per_group: int = 5,
    max_text_chars: int = 900,
) -> Dict:
    pipeline = build_summary_pipeline(
        chunks,
        max_groups=max_groups,
        max_evidence_per_group=max_evidence_per_group,
        max_text_chars=max_text_chars,
    )
    groups = [
        EvidenceGroup(
            group_id=group["group_id"],
            file_id=group["file_id"],
            file_name=group["file_name"],
            section_title=group["section_title"],
            material_type=group["material_type"],
            evidence=tuple(_evidence_from_dict(item) for item in group["evidence"]),
        )
        for group in pipeline["groups"]
    ]
    if not groups:
        return {
            "content": EMPTY_SUMMARY_MESSAGE,
            "llm_status": "empty",
            "map_summaries": [],
            "map_prompts": [],
            "reduce_prompt": "",
            "evidence_groups": pipeline["groups"],
        }
    if not llm_client.enabled():
        return {
            "content": "",
            "llm_status": "disabled",
            "map_summaries": [],
            "map_prompts": [build_map_prompt(course_name, group) for group in groups],
            "reduce_prompt": "",
            "evidence_groups": pipeline["groups"],
        }

    map_prompts = [build_map_prompt(course_name, group) for group in groups]
    map_summaries: List[MapSummary] = []
    for group, prompt in zip(groups, map_prompts):
        generated = llm_client.generate(prompt)
        if not generated:
            return {
                "content": "",
                "llm_status": "failed",
                "map_summaries": [map_summary_to_dict(item) for item in map_summaries],
                "map_prompts": map_prompts,
                "reduce_prompt": "",
                "evidence_groups": pipeline["groups"],
            }
        map_summaries.append(
            MapSummary(
                group_id=group.group_id,
                title=group.title,
                file_name=group.file_name,
                section_title=group.section_title,
                content=generated.strip(),
                evidence_labels=tuple(item.label for item in group.evidence),
            )
        )

    reduce_prompt = build_reduce_prompt(course_name, map_summaries)
    final_summary = llm_client.generate(reduce_prompt)
    if not final_summary:
        return {
            "content": "",
            "llm_status": "failed",
            "map_summaries": [map_summary_to_dict(item) for item in map_summaries],
            "map_prompts": map_prompts,
            "reduce_prompt": reduce_prompt,
            "evidence_groups": pipeline["groups"],
        }
    return {
        "content": final_summary.strip(),
        "llm_status": "used",
        "map_summaries": [map_summary_to_dict(item) for item in map_summaries],
        "map_prompts": map_prompts,
        "reduce_prompt": reduce_prompt,
        "evidence_groups": pipeline["groups"],
    }


def generate_map_reduce_course_summary(
    kb: CourseSummaryKnowledgeBase,
    course_id: str,
    course_name: str,
    ai_config: Optional[Dict],
    create_client: Callable[[Dict], SummaryLLMClient],
) -> Dict:
    chunks = kb.summary_chunks(course_id, limit=12)
    citations = [summary_citation_from_chunk(chunk) for chunk in chunks]
    if not chunks:
        return {
            "content": EMPTY_SUMMARY_MESSAGE,
            "citations": [],
            "llm_status": "empty",
            "status": "empty",
            "fallback_needed": True,
            "fallback_reason": "no_summary_chunks",
            "map_summaries": [],
            "map_prompts": [],
            "reduce_prompt": "",
            "evidence_groups": [],
        }

    try:
        client = create_client(ai_config or {})
    except Exception as exc:
        return _map_reduce_fallback_payload(
            status="client_error",
            reason=f"create_client_failed: {exc}",
            citations=citations,
        )

    try:
        result = run_map_reduce_summary(chunks, client, course_name=course_name)
    except Exception as exc:
        return _map_reduce_fallback_payload(
            status="summary_error",
            reason=f"map_reduce_failed: {exc}",
            citations=citations,
        )

    status = str(result.get("llm_status") or "failed")
    fallback_needed = status != "used"
    result.update(
        {
            "citations": citations,
            "status": status,
            "fallback_needed": fallback_needed,
            "fallback_reason": "" if not fallback_needed else _fallback_reason_for_status(status),
        }
    )
    return result


def evidence_item_to_dict(item: SummaryEvidence) -> Dict:
    return {
        "label": item.label,
        "file_id": item.file_id,
        "file_name": item.file_name,
        "file_path": item.file_path,
        "section_title": item.section_title,
        "material_type": item.material_type,
        "page": item.page,
        "chunk_index": item.chunk_index,
        "text": item.text,
    }


def summary_citation_from_chunk(chunk: Dict) -> Dict:
    page = chunk.get("page")
    location = f"第 {page} 页" if page else f"片段 {chunk.get('chunk_index', 0)}"
    section_title = str(chunk.get("section_title") or "")
    return {
        "file_id": chunk.get("file_id", ""),
        "file_name": chunk.get("file_name", "未知文件"),
        "file_path": chunk.get("file_path") or chunk.get("path", ""),
        "page": page,
        "chunk_index": chunk.get("chunk_index", 0),
        "location": location,
        "quote": chunk.get("context_text") or chunk.get("text", ""),
        "section_title": section_title,
        "material_type": chunk.get("material_type", ""),
    }


def _map_reduce_fallback_payload(*, status: str, reason: str, citations: Sequence[Dict]) -> Dict:
    return {
        "content": "",
        "citations": list(citations),
        "llm_status": status,
        "status": status,
        "fallback_needed": True,
        "fallback_reason": reason,
        "map_summaries": [],
        "map_prompts": [],
        "reduce_prompt": "",
        "evidence_groups": [],
    }


def _fallback_reason_for_status(status: str) -> str:
    reasons = {
        "empty": "no_summary_chunks",
        "disabled": "llm_disabled",
        "failed": "llm_generation_failed",
    }
    return reasons.get(status, "map_reduce_summary_unavailable")


def evidence_group_to_dict(group: EvidenceGroup) -> Dict:
    return {
        "group_id": group.group_id,
        "file_id": group.file_id,
        "file_name": group.file_name,
        "section_title": group.section_title,
        "material_type": group.material_type,
        "title": group.title,
        "evidence": [evidence_item_to_dict(item) for item in group.evidence],
    }


def map_summary_to_dict(item: MapSummary) -> Dict:
    return {
        "group_id": item.group_id,
        "title": item.title,
        "file_name": item.file_name,
        "section_title": item.section_title,
        "content": item.content,
        "evidence_labels": list(item.evidence_labels),
    }


def _evidence_from_dict(item: Dict) -> SummaryEvidence:
    return SummaryEvidence(
        label=item["label"],
        file_id=item["file_id"],
        file_name=item["file_name"],
        file_path=item.get("file_path", ""),
        section_title=item.get("section_title", ""),
        material_type=item.get("material_type", ""),
        page=item.get("page"),
        chunk_index=item["chunk_index"],
        text=item["text"],
    )


def _format_evidence_block(item: SummaryEvidence) -> str:
    page = item.page or "无"
    section = item.section_title or "无"
    return (
        f"[{item.label}] 文件：{item.file_name}，章节：{section}，页码：{page}，片段：{item.chunk_index}\n"
        f"{item.text}"
    )


def _format_map_summary_block(item: MapSummary) -> str:
    source_labels = ", ".join(f"[{label}]" for label in item.evidence_labels)
    section = item.section_title or "无"
    return (
        f"[{item.group_id}] 文件：{item.file_name}，章节：{section}，来源：{source_labels}\n"
        f"{item.content}"
    )


def _compact_text(text: str, max_chars: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."
