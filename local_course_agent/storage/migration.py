from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_course_agent.storage.codecs import write_json, write_text
from local_course_agent.storage.paths import CourseStorePaths


def migrate_legacy_sqlite(data_dir: Path, paths: CourseStorePaths) -> None:
    db_path = Path(data_dir) / "app.db"
    if not db_path.exists():
        return
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "messages" in tables:
                _migrate_messages(conn, paths)
            if "memories" in tables:
                _migrate_memories(conn, paths)
            if "notes" in tables:
                _migrate_notes(conn, paths)
    except (sqlite3.Error, json.JSONDecodeError):
        return


def _migrate_messages(conn: sqlite3.Connection, paths: CourseStorePaths) -> None:
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
        path = paths.messages_path(course_id)
        if not path.exists():
            write_json(path, messages)


def _migrate_memories(conn: sqlite3.Connection, paths: CourseStorePaths) -> None:
    rows = conn.execute("SELECT course_id, content FROM memories").fetchall()
    for row in rows:
        path = paths.memory_path(row["course_id"])
        if not path.exists():
            write_text(path, row["content"] or "")


def _migrate_notes(conn: sqlite3.Connection, paths: CourseStorePaths) -> None:
    rows = conn.execute("SELECT course_id, id, title, content, created_at FROM notes ORDER BY id DESC").fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["course_id"], []).append(dict(row))
    for course_id, notes in grouped.items():
        path = paths.notes_path(course_id)
        if not path.exists():
            write_json(path, notes)
