from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from local_course_agent.llm import build_course_summary_prompt, create_llm_client
from local_course_agent.parser import extract_text
from local_course_agent.parser_quality import evaluate_parser_quality
from local_course_agent.rag import citation_from_chunk
from local_course_agent.summary import generate_map_reduce_course_summary

PLAN_FILE_LIMIT = 8


def build_course_index(kb, course: dict, course_id: str, mineru_config=None) -> dict:
    indexed_files = 0
    documents = []
    quality_files = []
    quality_counts = {"ok": 0, "warning": 0, "failed": 0}
    for file_node in iter_files(course.get("children", [])):
        path = Path(file_node["path"])
        if not should_index_course_file(course["path"], path):
            continue
        pages = extract_text(path, mineru_config=mineru_config or {})
        quality = evaluate_parser_quality(pages)
        status = quality.get("status", "failed")
        quality_counts[status] = quality_counts.get(status, 0) + 1
        quality_files.append(
            {
                "file_id": file_node["id"],
                "file_name": file_node["name"],
                "path": str(path),
                "status": status,
                "warnings": quality.get("warnings", []),
                "score": quality.get("score", 0.0),
            }
        )
        documents.append(
            {
                "file_id": file_node["id"],
                "file_name": file_node["name"],
                "path": str(path),
                "pages": pages,
            }
        )
        indexed_files += 1
    indexed_chunks = kb.rebuild_course(course_id, documents)
    return {
        "ok": True,
        "indexed_files": indexed_files,
        "total_chunks": indexed_chunks,
        "parser_quality": {
            "files": quality_files,
            "counts": quality_counts,
        },
    }


class CourseIndexJobs:
    def __init__(self, kb, max_workers: int = 1):
        self.kb = kb
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(self, course_id: str, course: dict, mineru_config=None) -> dict:
        job_id = uuid.uuid4().hex
        snapshot = dict(course)
        snapshot["children"] = list(course.get("children", []))
        job = {
            "id": job_id,
            "course_id": course_id,
            "status": "queued",
            "result": None,
            "error": "",
        }
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run, job_id, course_id, snapshot, dict(mineru_config or {}))
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _run(self, job_id: str, course_id: str, course: dict, mineru_config: dict) -> None:
        self._update(job_id, status="running")
        try:
            result = build_course_index(self.kb, course, course_id, mineru_config=mineru_config)
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
            return
        self._update(job_id, status="succeeded", result=result)

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)


def create_study_artifact(
    kb,
    store,
    courses_provider,
    course: dict,
    course_id: str,
    artifact_type: str,
    invalidate=None,
    ai_config=None,
) -> dict:
    if artifact_type == "summary":
        label = "课程摘要"
        result = generate_course_summary(kb, course_id, course.get("name", ""), ai_config=ai_config)
    else:
        label = "练习题"
        result = kb.generate_quiz(course_id)
    course_path = Path(course["path"])
    artifact_path = save_study_artifact(course_path, label, result["content"], result.get("citations", []))
    message = f"{label}已生成并保存到课程资料：{artifact_path.relative_to(course_path)}\n\n{result['content']}"
    store.add_message(course_id, "assistant", message, result.get("citations", []))
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


def generate_course_summary(kb, course_id: str, course_name: str = "", ai_config=None, limit: int = 8) -> dict:
    map_reduce = generate_map_reduce_course_summary(
        kb,
        course_id,
        course_name,
        ai_config=ai_config or {},
        create_client=create_llm_client,
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
    client = create_llm_client(ai_config or {})
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


def build_default_study_plan(course: dict) -> list[dict]:
    files = []
    for file_node in iter_files(course.get("children", [])):
        path = Path(file_node["path"])
        if not should_index_course_file(course["path"], path):
            continue
        if path.suffix.lower() not in {".pdf", ".md", ".markdown", ".txt", ".docx"}:
            continue
        files.append(file_node)

    ranked = sorted(files, key=study_plan_file_rank)[:PLAN_FILE_LIMIT]
    if not ranked:
        return [
            {
                "title": f"整理《{course.get('name', '课程')}》资料目录",
                "kind": "read",
                "status": "todo",
                "estimated_minutes": 25,
            }
        ]

    items = []
    for file_node in ranked:
        title, kind, minutes = study_plan_item_from_file(file_node)
        items.append(
            {
                "title": title,
                "kind": kind,
                "status": "todo",
                "estimated_minutes": minutes,
                "source_file_id": file_node["id"],
                "source_file_name": file_node["name"],
            }
        )
    items.append(
        {
            "title": "完成一次错题与薄弱点复盘",
            "kind": "review",
            "status": "todo",
            "estimated_minutes": 30,
        }
    )
    return items


def study_plan_file_rank(file_node: dict) -> tuple[int, str]:
    name = str(file_node.get("name", "")).lower()
    priority = 2
    if any(keyword in name for keyword in ("教材", "chapter", "lecture", "课件", "讲义")):
        priority = 0
    elif any(keyword in name for keyword in ("习题", "练习", "quiz", "作业", "复习")):
        priority = 1
    return priority, name


def study_plan_item_from_file(file_node: dict) -> tuple[str, str, int]:
    name = str(file_node.get("name", "课程资料"))
    lower_name = name.lower()
    if any(keyword in lower_name for keyword in ("习题", "练习", "quiz", "作业")):
        return f"完成并订正 {name}", "practice", 35
    if any(keyword in lower_name for keyword in ("复习", "summary", "总结")):
        return f"复盘 {name}", "review", 25
    return f"阅读并提炼 {name}", "read", 30


def study_plan_stats(items: list[dict]) -> dict:
    total = len(items)
    completed = len([item for item in items if item.get("status") == "done"])
    doing = len([item for item in items if item.get("status") == "doing"])
    remaining_minutes = sum(
        int(item.get("estimated_minutes", 0) or 0)
        for item in items
        if item.get("status") != "done"
    )
    next_item = next((item for item in items if item.get("status") == "doing"), None)
    if next_item is None:
        next_item = next((item for item in items if item.get("status") == "todo"), None)
    return {
        "total": total,
        "completed": completed,
        "doing": doing,
        "remaining_minutes": remaining_minutes,
        "progress_percent": round((completed / total) * 100) if total else 0,
        "next_item_id": next_item.get("id") if next_item else None,
    }


def study_plan_payload(store, course_id: str, course: dict) -> dict:
    items = store.ensure_study_plan(course_id, build_default_study_plan(course))
    return {"items": items, "stats": study_plan_stats(items)}


def iter_files(nodes):
    for node in nodes:
        if node["type"] == "file":
            yield node
        else:
            yield from iter_files(node.get("children", []))


def save_study_artifact(course_path: Path, label: str, content: str, citations: list) -> Path:
    target_dir = course_path / "AI生成"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = target_dir / f"{label}-{timestamp}.md"
    citation_lines = []
    for citation in citations:
        page = f" 第 {citation.get('page')} 页" if citation.get("page") else ""
        citation_lines.append(f"- {citation.get('file_name', '未知文件')}{page}，片段 {citation.get('chunk_index')}")
    text = f"# {label}\n\n{content.strip()}\n"
    if citation_lines:
        text += "\n## 来源\n\n" + "\n".join(citation_lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def should_index_course_file(course_path, file_path) -> bool:
    try:
        relative = Path(file_path).resolve().relative_to(Path(course_path).resolve())
    except ValueError:
        return False
    return "AI生成" not in relative.parts
