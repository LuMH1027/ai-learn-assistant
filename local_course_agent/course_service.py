from __future__ import annotations

from datetime import datetime
from pathlib import Path

from local_course_agent.parser import extract_text


def build_course_index(kb, course: dict, course_id: str, mineru_config=None) -> dict:
    indexed_files = 0
    documents = []
    for file_node in iter_files(course.get("children", [])):
        path = Path(file_node["path"])
        if not should_index_course_file(course["path"], path):
            continue
        pages = extract_text(path, mineru_config=mineru_config or {})
        documents.append(
            {
                "file_id": file_node["id"],
                "file_name": file_node["name"],
                "pages": pages,
            }
        )
        indexed_files += 1
    indexed_chunks = kb.rebuild_course(course_id, documents)
    return {"ok": True, "indexed_files": indexed_files, "total_chunks": indexed_chunks}


def create_study_artifact(kb, store, courses_provider, course: dict, course_id: str, artifact_type: str, invalidate=None) -> dict:
    if artifact_type == "summary":
        label = "课程摘要"
        result = kb.generate_summary(course_id)
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
        "artifact": {"name": artifact_path.name, "path": str(artifact_path)},
        "courses": courses_provider(),
    }


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
