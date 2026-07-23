from __future__ import annotations

from pathlib import Path

from local_course_agent.learning.files import save_study_artifact
from local_course_agent.learning.summary import generate_map_reduce_course_summary
from local_course_agent.llm.config import create_llm_client
from local_course_agent.llm.prompts import build_course_summary_prompt
from local_course_agent.retrieval.rag import citation_from_chunk


def create_study_artifact(
    kb,
    store,
    courses_provider,
    course: dict,
    course_id: str,
    artifact_type: str,
    conversation_id: str | None = None,
    invalidate=None,
    ai_config=None,
    summary_builder=None,
) -> dict:
    if artifact_type == "summary":
        label = "课程摘要"
        builder = summary_builder or generate_course_summary
        result = builder(kb, course_id, course.get("name", ""), ai_config=ai_config)
    else:
        label = "练习题"
        result = kb.generate_quiz(course_id)
    course_path = Path(course["path"])
    artifact_path = save_study_artifact(course_path, label, result["content"], result.get("citations", []))
    message = f"{label}已生成并保存到课程资料：{artifact_path.relative_to(course_path)}\n\n{result['content']}"
    store.add_message(course_id, "assistant", message, result.get("citations", []), conversation_id=conversation_id)
    if invalidate:
        invalidate()
    return {
        "ok": True,
        "content": result["content"],
        "citations": result.get("citations", []),
        "llm_status": result.get("llm_status"),
        "summary_method": result.get("summary_method"),
        "artifact": {"name": artifact_path.name, "path": str(artifact_path)},
        "courses": courses_provider(),
    }


def generate_course_summary(
    kb,
    course_id: str,
    course_name: str = "",
    ai_config=None,
    limit: int = 8,
    create_client=create_llm_client,
) -> dict:
    map_reduce = generate_map_reduce_course_summary(
        kb,
        course_id,
        course_name,
        ai_config=ai_config or {},
        create_client=create_client,
    )
    if not map_reduce.get("fallback_needed"):
        return {
            "content": map_reduce["content"],
            "citations": map_reduce.get("citations", []),
            "llm_status": "used",
            "summary_method": "map_reduce",
            "map_summaries": map_reduce.get("map_summaries", []),
            "evidence_groups": map_reduce.get("evidence_groups", []),
        }

    chunks = kb.summary_chunks(course_id, limit)
    if not chunks:
        result = kb.generate_summary(course_id, limit=limit)
        result["llm_status"] = "skipped"
        result["summary_method"] = "extractive"
        return result
    citations = [citation_from_chunk(chunk) for chunk in chunks]
    evidence = [
        {
            **citation,
            "quote": chunk.get("context_text") or chunk.get("text", ""),
        }
        for citation, chunk in zip(citations, chunks)
    ]
    client = create_client(ai_config or {})
    generated = client.generate(build_course_summary_prompt(course_name, evidence))
    if generated:
        return {
            "content": generated,
            "citations": citations,
            "llm_status": "used",
            "summary_method": "single_prompt",
            "fallback_reason": map_reduce.get("fallback_reason", ""),
        }
    result = kb.generate_summary(course_id, limit=limit)
    result["llm_status"] = "fallback" if client.enabled() else "disabled"
    result["summary_method"] = "extractive"
    result["fallback_reason"] = map_reduce.get("fallback_reason", "")
    return result
