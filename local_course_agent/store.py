from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class AppStore:
    """File-backed per-course state.

    A course's chat, compact memory, and notes live under:
    data/course_memory/<course_id>/

    Deleting one of those files clears that part of the course state.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir = self.data_dir / "course_memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._migrate_legacy_sqlite()

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
            topic = memory_topic(question)
            items = parse_memory_items(current)
            matched = next((item for item in items if item["topic"] == topic), None)
            if matched:
                matched["count"] += 1
                matched["sample"] = question[:80]
            else:
                items.append({"topic": topic, "count": 1, "sample": question[:80]})
            items = sorted(items, key=lambda item: (item["count"], items.index(item)), reverse=True)[:8]
            compact = "\n".join(
                f"- 关注 {item['count']} 次：{item['topic']}（最近问题：{item['sample']}）"
                for item in items
            )
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

    def _course_dir(self, course_id: str) -> Path:
        path = self.memory_dir / safe_course_id(course_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _messages_path(self, course_id: str) -> Path:
        return self._course_dir(course_id) / "messages.json"

    def _memory_path(self, course_id: str) -> Path:
        return self._course_dir(course_id) / "memory.md"

    def _notes_path(self, course_id: str) -> Path:
        return self._course_dir(course_id) / "notes.json"

    def _study_plan_path(self, course_id: str) -> Path:
        return self._course_dir(course_id) / "study_plan.json"

    def _lock_for(self, course_id: str) -> threading.RLock:
        key = safe_course_id(course_id)
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.RLock()
            return self._locks[key]

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)

    def _migrate_legacy_sqlite(self) -> None:
        db_path = self.data_dir / "app.db"
        if not db_path.exists():
            return
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                tables = {
                    row["name"]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                if "messages" in tables:
                    rows = conn.execute(
                        "SELECT course_id, role, content, citations, trace, created_at FROM messages ORDER BY id"
                    ).fetchall()
                    grouped = {}
                    for row in rows:
                        grouped.setdefault(row["course_id"], []).append(
                            {
                                "role": row["role"],
                                "content": row["content"],
                                "citations": json.loads(row["citations"] or "[]"),
                                "trace": json.loads(row["trace"] or "[]"),
                                "created_at": row["created_at"],
                            }
                        )
                    for course_id, messages in grouped.items():
                        path = self._messages_path(course_id)
                        if not path.exists():
                            self._write_json(path, messages)
                if "memories" in tables:
                    rows = conn.execute("SELECT course_id, content FROM memories").fetchall()
                    for row in rows:
                        path = self._memory_path(row["course_id"])
                        if not path.exists():
                            self._write_text(path, row["content"] or "")
                if "notes" in tables:
                    rows = conn.execute(
                        "SELECT course_id, id, title, content, created_at FROM notes ORDER BY id DESC"
                    ).fetchall()
                    grouped = {}
                    for row in rows:
                        grouped.setdefault(row["course_id"], []).append(dict(row))
                    for course_id, notes in grouped.items():
                        path = self._notes_path(course_id)
                        if not path.exists():
                            self._write_json(path, notes)
        except (sqlite3.Error, json.JSONDecodeError):
            return


def safe_course_id(course_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in course_id) or "course"


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def memory_topic(question: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", question.lower())
    stop = {"什么", "怎么", "如何", "为什么", "请问", "一下", "说明", "解释", "作用"}
    useful = [term for term in terms if term not in stop and not term.isdigit()]
    return " / ".join(useful[:3]) or question[:24] or "未命名问题"


def parse_memory_items(text: str) -> List[Dict]:
    items = []
    for line in text.splitlines():
        match = re.fullmatch(r"- 关注 (\d+) 次：(.+?)（最近问题：(.+)）", line.strip())
        if match:
            items.append({"count": int(match.group(1)), "topic": match.group(2), "sample": match.group(3)})
            continue
        legacy = re.fullmatch(r"- 最近关注：(.+)", line.strip())
        if legacy:
            sample = legacy.group(1)
            items.append({"count": 1, "topic": memory_topic(sample), "sample": sample})
    return items


def normalize_study_plan_item(item: Dict, timestamp: str) -> Dict:
    title = str(item.get("title", "")).strip()[:120]
    if not title:
        title = "未命名学习项"
    kind = str(item.get("kind", "read"))
    if kind not in {"read", "review", "practice"}:
        kind = "read"
    status = str(item.get("status", "todo"))
    if status not in {"todo", "doing", "done"}:
        status = "todo"
    try:
        estimated_minutes = int(item.get("estimated_minutes", 25))
    except (TypeError, ValueError):
        estimated_minutes = 25
    estimated_minutes = min(max(estimated_minutes, 5), 240)
    return {
        "id": int(item.get("id", 0)),
        "title": title,
        "kind": kind,
        "status": status,
        "estimated_minutes": estimated_minutes,
        "source_file_id": str(item.get("source_file_id", "")),
        "source_file_name": str(item.get("source_file_name", "")),
        "created_at": str(item.get("created_at") or timestamp),
        "updated_at": str(item.get("updated_at") or timestamp),
        "completed_at": str(item.get("completed_at") or ""),
    }


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
