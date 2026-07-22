from __future__ import annotations

from typing import Dict, List

from local_course_agent.storage.study_plan import now_text


class NotesStoreMixin:
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
