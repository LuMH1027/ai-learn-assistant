from __future__ import annotations

from local_course_agent.storage.memory import update_memory_text


class MemoryStoreMixin:
    def get_memory(self, course_id: str, conversation_id: str | None = None) -> str:
        conversation = self.get_conversation(course_id, conversation_id)
        path = self._conversation_memory_path(course_id, conversation["id"])
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def update_memory_from_question(self, course_id: str, question: str, conversation_id: str | None = None) -> str:
        with self._lock_for(course_id):
            conversation = self.get_conversation(course_id, conversation_id)
            current = self.get_memory(course_id, conversation["id"])
            compact = update_memory_text(current, question)
            self._write_text(self._conversation_memory_path(course_id, conversation["id"]), compact)
            if conversation["id"] == "default":
                self._write_text(self._memory_path(course_id), compact)
            return compact

    def clear_memory(self, course_id: str, conversation_id: str | None = None) -> str:
        with self._lock_for(course_id):
            conversation = self.get_conversation(course_id, conversation_id)
            self._write_text(self._conversation_memory_path(course_id, conversation["id"]), "")
            if conversation["id"] == "default":
                self._write_text(self._memory_path(course_id), "")
            return ""
