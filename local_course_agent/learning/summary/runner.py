from __future__ import annotations

from typing import Callable, Dict, List, Optional, Protocol, Sequence

from local_course_agent.learning.summary.citations import summary_citation_from_chunk
from local_course_agent.learning.summary.models import MapSummary
from local_course_agent.learning.summary.pipeline import build_summary_pipeline
from local_course_agent.learning.summary.prompts import build_map_prompt, build_reduce_prompt
from local_course_agent.learning.summary.serialization import evidence_group_from_dict, map_summary_to_dict


EMPTY_SUMMARY_MESSAGE = "当前课程还没有可用于生成章节摘要的资料片段，请先构建知识库。"


class SummaryLLMClient(Protocol):
    def enabled(self) -> bool:
        ...

    def generate(self, prompt: str) -> Optional[str]:
        ...


class CourseSummaryKnowledgeBase(Protocol):
    def summary_chunks(self, course_id: str, limit: int = 6) -> List[Dict]:
        ...


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
    groups = [evidence_group_from_dict(group) for group in pipeline["groups"]]
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
        return map_reduce_fallback_payload(
            status="client_error",
            reason=f"create_client_failed: {exc}",
            citations=citations,
        )

    try:
        result = run_map_reduce_summary(chunks, client, course_name=course_name)
    except Exception as exc:
        return map_reduce_fallback_payload(
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
            "fallback_reason": "" if not fallback_needed else fallback_reason_for_status(status),
        }
    )
    return result


def map_reduce_fallback_payload(*, status: str, reason: str, citations: Sequence[Dict]) -> Dict:
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


def fallback_reason_for_status(status: str) -> str:
    reasons = {
        "empty": "no_summary_chunks",
        "disabled": "llm_disabled",
        "failed": "llm_generation_failed",
    }
    return reasons.get(status, "map_reduce_summary_unavailable")
