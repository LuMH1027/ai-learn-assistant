from __future__ import annotations

from typing import Dict, List

from local_course_agent.storage.study_plan import now_text


class MessagesStoreMixin:
    def add_message(self, course_id: str, role: str, content: str, citations=None, trace=None, conversation_id: str | None = None) -> None:
        with self._lock_for(course_id):
            conversation = self.get_conversation(course_id, conversation_id)
            target_id = conversation["id"]
            messages = self.list_messages(course_id, target_id)
            messages.append(
                {
                    "role": role,
                    "content": content,
                    "citations": citations or [],
                    "trace": trace or [],
                    "created_at": now_text(),
                }
            )
            self._write_json(self._conversation_messages_path(course_id, target_id), messages)
            if target_id == "default":
                self._write_json(self._messages_path(course_id), messages)
            self._touch_conversation(course_id, target_id, role=role, content=content)

    def list_messages(self, course_id: str, conversation_id: str | None = None) -> List[Dict]:
        conversation = self.get_conversation(course_id, conversation_id)
        return self._read_json(self._conversation_messages_path(course_id, conversation["id"]), [])

    def clear_messages(self, course_id: str, conversation_id: str | None = None) -> List[Dict]:
        with self._lock_for(course_id):
            conversation = self.get_conversation(course_id, conversation_id)
            messages: List[Dict] = []
            self._write_json(self._conversation_messages_path(course_id, conversation["id"]), messages)
            if conversation["id"] == "default":
                self._write_json(self._messages_path(course_id), messages)
            conversations = self.ensure_conversation_state(course_id)
            for item in conversations:
                if item["id"] == conversation["id"]:
                    item["message_count"] = 0
                    item["unread_count"] = 0
                    item["updated_at"] = now_text()
                    break
            self._write_json(self._conversations_path(course_id), conversations)
            return messages
