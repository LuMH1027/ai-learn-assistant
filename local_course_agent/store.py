from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List

from local_course_agent.learning.mastery import (
    apply_answer_result,
    create_mastery_state,
    normalize_state,
    upsert_knowledge_point,
)
from local_course_agent.store_codecs import atomic_write_text, read_json, write_json, write_text
from local_course_agent.store_memory import memory_topic, parse_memory_items, update_memory_text
from local_course_agent.store_migration import migrate_legacy_sqlite
from local_course_agent.store_paths import CourseStorePaths, safe_course_id
from local_course_agent.store_study_plan import normalize_study_plan_item, now_text

__all__ = [
    "AppStore",
    "atomic_write_text",
    "memory_topic",
    "normalize_study_plan_item",
    "now_text",
    "parse_memory_items",
    "safe_course_id",
]


class AppStore:
    """File-backed per-course state.

    A course's chat, compact memory, and notes live under:
    data/course_memory/<course_id>/

    Deleting one of those files clears that part of the course state.
    """

    def __init__(self, data_dir: Path):
        self.paths = CourseStorePaths(data_dir)
        self.data_dir = self.paths.data_dir
        self.memory_dir = self.paths.memory_dir
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        migrate_legacy_sqlite(self.data_dir, self.paths)

    def add_message(self, course_id: str, role: str, content: str, citations=None, trace=None) -> None:
        with self._lock_for(course_id):
            messages = self.list_messages(course_id)
            messages.append(
                {
                    "role": role,
                    "content": content,
                    "citations": citations or [],
                    "trace": trace or [],
                    "created_at": now_text(),
                }
            )
            self._write_json(self._messages_path(course_id), messages)

    def list_messages(self, course_id: str) -> List[Dict]:
        return self._read_json(self._messages_path(course_id), [])

    def get_memory(self, course_id: str) -> str:
        path = self._memory_path(course_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def update_memory_from_question(self, course_id: str, question: str) -> str:
        with self._lock_for(course_id):
            current = self.get_memory(course_id)
            compact = update_memory_text(current, question)
            self._write_text(self._memory_path(course_id), compact)
            return compact

    def add_note(self, course_id: str, title: str, content: str) -> None:
        with self._lock_for(course_id):
            notes = self.list_notes(course_id)
            next_id = max([int(note.get("id", 0)) for note in notes] or [0]) + 1
            notes.insert(
                0,
                {
                    "id": next_id,
                    "title": title,
                    "content": content,
                    "created_at": now_text(),
                },
            )
            self._write_json(self._notes_path(course_id), notes)

    def list_notes(self, course_id: str) -> List[Dict]:
        return self._read_json(self._notes_path(course_id), [])

    def list_study_plan(self, course_id: str) -> List[Dict]:
        return self._read_json(self._study_plan_path(course_id), [])

    def ensure_study_plan(self, course_id: str, seed_items: List[Dict]) -> List[Dict]:
        with self._lock_for(course_id):
            current = self.list_study_plan(course_id)
            if current:
                return current
            now = now_text()
            items = []
            for index, item in enumerate(seed_items, start=1):
                items.append(normalize_study_plan_item({**item, "id": index}, now))
            self._write_json(self._study_plan_path(course_id), items)
            return items

    def add_study_plan_item(self, course_id: str, item: Dict) -> List[Dict]:
        with self._lock_for(course_id):
            items = self.list_study_plan(course_id)
            next_id = max([int(plan_item.get("id", 0)) for plan_item in items] or [0]) + 1
            items.append(normalize_study_plan_item({**item, "id": next_id}, now_text()))
            self._write_json(self._study_plan_path(course_id), items)
            return items

    def update_study_plan_item(self, course_id: str, item_id: int, changes: Dict) -> List[Dict]:
        with self._lock_for(course_id):
            items = self.list_study_plan(course_id)
            updated = []
            found = False
            for item in items:
                if int(item.get("id", 0)) != int(item_id):
                    updated.append(item)
                    continue
                found = True
                next_item = dict(item)
                for key in ("title", "kind", "status", "estimated_minutes"):
                    if key in changes:
                        next_item[key] = changes[key]
                next_item["updated_at"] = now_text()
                if next_item.get("status") == "done" and not next_item.get("completed_at"):
                    next_item["completed_at"] = next_item["updated_at"]
                elif next_item.get("status") != "done":
                    next_item["completed_at"] = ""
                updated.append(normalize_study_plan_item(next_item, next_item["updated_at"]))
            if not found:
                raise KeyError(f"study plan item not found: {item_id}")
            self._write_json(self._study_plan_path(course_id), updated)
            return updated

    def get_mastery_state(self, course_id: str) -> Dict:
        return normalize_state(self._read_json(self._mastery_path(course_id), create_mastery_state()))

    def save_mastery_state(self, course_id: str, state: Dict) -> Dict:
        with self._lock_for(course_id):
            normalized = normalize_state(state)
            self._write_json(self._mastery_path(course_id), normalized)
            return normalized

    def upsert_mastery_knowledge_point(self, course_id: str, point: Dict) -> Dict:
        with self._lock_for(course_id):
            state = self.get_mastery_state(course_id)
            next_state = upsert_knowledge_point(state, point)
            self._write_json(self._mastery_path(course_id), next_state)
            return next_state

    def apply_mastery_answer_result(self, course_id: str, point_id: str, correct: bool, **kwargs) -> Dict:
        with self._lock_for(course_id):
            state = self.get_mastery_state(course_id)
            next_state = apply_answer_result(state, point_id, correct=correct, **kwargs)
            self._write_json(self._mastery_path(course_id), next_state)
            return next_state

    def _course_dir(self, course_id: str) -> Path:
        return self.paths.course_dir(course_id)

    def _messages_path(self, course_id: str) -> Path:
        return self.paths.messages_path(course_id)

    def _memory_path(self, course_id: str) -> Path:
        return self.paths.memory_path(course_id)

    def _notes_path(self, course_id: str) -> Path:
        return self.paths.notes_path(course_id)

    def _study_plan_path(self, course_id: str) -> Path:
        return self.paths.study_plan_path(course_id)

    def _mastery_path(self, course_id: str) -> Path:
        return self.paths.mastery_path(course_id)

    def _lock_for(self, course_id: str) -> threading.RLock:
        key = safe_course_id(course_id)
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.RLock()
            return self._locks[key]

    def _read_json(self, path: Path, default):
        return read_json(path, default)

    def _write_json(self, path: Path, data) -> None:
        write_json(path, data)

    def _write_text(self, path: Path, text: str) -> None:
        write_text(path, text)
