from __future__ import annotations

from typing import Dict, List

from local_course_agent.storage.study_plan import now_text


class MessagesStoreMixin:
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

    def clear_messages(self, course_id: str) -> List[Dict]:
        with self._lock_for(course_id):
            messages: List[Dict] = []
            self._write_json(self._messages_path(course_id), messages)
            return messages
