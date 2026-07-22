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

    def update_note(self, course_id: str, note_id: str, changes: Dict) -> Dict | None:
        with self._lock_for(course_id):
            notes = self.list_notes(course_id)
            updated_note = None
            for note in notes:
                if str(note.get("id")) != str(note_id):
                    continue
                if "title" in changes:
                    note["title"] = str(changes.get("title") or "").strip() or "学习笔记"
                if "content" in changes:
                    note["content"] = str(changes.get("content") or "").strip()
                note["updated_at"] = now_text()
                updated_note = note
                break
            if updated_note is None:
                return None
            self._write_json(self._notes_path(course_id), notes)
            return updated_note

    def delete_note(self, course_id: str, note_id: str) -> bool:
        with self._lock_for(course_id):
            notes = self.list_notes(course_id)
            remaining = [note for note in notes if str(note.get("id")) != str(note_id)]
            if len(remaining) == len(notes):
                return False
            self._write_json(self._notes_path(course_id), remaining)
            return True
