from __future__ import annotations

from local_course_agent.storage.memory import update_memory_text


class MemoryStoreMixin:
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
