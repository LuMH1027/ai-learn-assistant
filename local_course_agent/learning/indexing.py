from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from local_course_agent.ingestion.parser_quality import evaluate_parser_quality
from local_course_agent.learning.files import iter_files, should_index_course_file
from local_course_agent.parser import extract_text


def build_course_index(
    kb,
    course: dict,
    course_id: str,
    mineru_config=None,
    progress_callback=None,
    extract_text_fn=extract_text,
    parser_quality_fn=evaluate_parser_quality,
) -> dict:
    indexed_files = 0
    documents = []
    quality_files = []
    quality_counts = {"ok": 0, "warning": 0, "failed": 0}
    indexable_files = [
        file_node
        for file_node in iter_files(course.get("children", []))
        if should_index_course_file(course["path"], Path(file_node["path"]))
    ]
    emit_progress(
        progress_callback,
        total_files=len(indexable_files),
        processed_files=0,
        progress=0,
        current_file=None,
    )
    for file_node in indexable_files:
        path = Path(file_node["path"])
        current_file = index_job_file_payload(file_node)
        emit_progress(progress_callback, current_file=current_file)
        try:
            pages = extract_text_fn(path, mineru_config=mineru_config or {})
        except Exception as exc:
            emit_progress(
                progress_callback,
                error_file={**current_file, "error": str(exc)},
                current_file=current_file,
            )
            raise
        quality = parser_quality_fn(pages)
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
        emit_progress(
            progress_callback,
            processed_files=indexed_files,
            progress=round((indexed_files / len(indexable_files)) * 100) if indexable_files else 100,
            current_file=current_file,
        )
    indexed_chunks = kb.rebuild_course(course_id, documents)
    emit_progress(
        progress_callback,
        processed_files=indexed_files,
        progress=100,
        current_file=None,
    )
    return {
        "ok": True,
        "indexed_files": indexed_files,
        "total_chunks": indexed_chunks,
        "parser_quality": {
            "files": quality_files,
            "counts": quality_counts,
        },
    }


def emit_progress(progress_callback, **changes) -> None:
    if not progress_callback:
        return
    progress_callback(changes)


def index_job_file_payload(file_node: dict) -> dict:
    return {
        "file_id": file_node.get("id"),
        "file_name": file_node.get("name", ""),
        "path": str(file_node.get("path", "")),
    }


class CourseIndexJobs:
    def __init__(
        self,
        kb,
        max_workers: int = 1,
        snapshot_path: Path | str | None = Path("data/index_jobs.json"),
        build_index=build_course_index,
    ):
        self.kb = kb
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._snapshot_path = Path(snapshot_path) if snapshot_path else None
        self._build_index = build_index
        self._jobs: dict[str, dict] = self._load_snapshots()
        if self._jobs:
            self._persist_locked()

    def start(self, course_id: str, course: dict, mineru_config=None) -> dict:
        job_id = uuid.uuid4().hex
        now = timestamp_now()
        snapshot = dict(course)
        snapshot["children"] = list(course.get("children", []))
        job = {
            "id": job_id,
            "course_id": course_id,
            "status": "queued",
            "result": None,
            "error": "",
            "started_at": None,
            "updated_at": now,
            "finished_at": None,
            "progress": 0,
            "current_file": None,
            "processed_files": 0,
            "total_files": 0,
            "error_files": [],
        }
        with self._lock:
            self._jobs[job_id] = job
            self._persist_locked()
        self._executor.submit(self._run, job_id, course_id, snapshot, dict(mineru_config or {}))
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job, error_files=list(job.get("error_files", []))) if job else None

    def _run(self, job_id: str, course_id: str, course: dict, mineru_config: dict) -> None:
        self._update(job_id, status="running", started_at=timestamp_now())
        try:
            result = self._build_index(
                self.kb,
                course,
                course_id,
                mineru_config=mineru_config,
                progress_callback=lambda changes: self._update_progress(job_id, changes),
            )
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc), finished_at=timestamp_now(), current_file=None)
            return
        self._update(job_id, status="succeeded", result=result, progress=100, finished_at=timestamp_now(), current_file=None)

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            if job_id in self._jobs:
                changes.setdefault("updated_at", timestamp_now())
                self._jobs[job_id].update(changes)
                self._persist_locked()

    def _update_progress(self, job_id: str, changes: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            error_file = changes.pop("error_file", None)
            if error_file:
                job.setdefault("error_files", []).append(error_file)
            job.update(changes)
            job["updated_at"] = timestamp_now()
            self._persist_locked()

    def _load_snapshots(self) -> dict[str, dict]:
        if not self._snapshot_path or not self._snapshot_path.exists():
            return {}
        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        restored = {}
        now = timestamp_now()
        for job in jobs:
            if not isinstance(job, dict) or not job.get("id"):
                continue
            normalized = self._normalize_job(job)
            if normalized["status"] in {"queued", "running"}:
                normalized.update(
                    {
                        "status": "failed",
                        "error": normalized.get("error") or "索引任务因服务重启中断",
                        "updated_at": now,
                        "finished_at": normalized.get("finished_at") or now,
                        "current_file": None,
                    }
                )
            restored[normalized["id"]] = normalized
        return restored

    def _normalize_job(self, job: dict) -> dict:
        return {
            "id": job.get("id", ""),
            "course_id": job.get("course_id", ""),
            "status": job.get("status", "failed"),
            "result": job.get("result"),
            "error": job.get("error", ""),
            "started_at": job.get("started_at"),
            "updated_at": job.get("updated_at"),
            "finished_at": job.get("finished_at"),
            "progress": int(job.get("progress", 0) or 0),
            "current_file": job.get("current_file"),
            "processed_files": int(job.get("processed_files", 0) or 0),
            "total_files": int(job.get("total_files", 0) or 0),
            "error_files": list(job.get("error_files", [])),
        }

    def _persist_locked(self) -> None:
        if not self._snapshot_path:
            return
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"jobs": list(self._jobs.values())}
            tmp_path = self._snapshot_path.with_suffix(f"{self._snapshot_path.suffix}.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(self._snapshot_path)
        except OSError:
            pass


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")
