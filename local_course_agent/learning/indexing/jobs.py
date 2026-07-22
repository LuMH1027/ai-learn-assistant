from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from local_course_agent.learning.indexing.builder import build_course_index


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
        self._update(
            job_id,
            status="succeeded",
            result=result,
            progress=100,
            finished_at=timestamp_now(),
            current_file=None,
        )

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
