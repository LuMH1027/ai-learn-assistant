from __future__ import annotations

from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from local_course_agent.storage.study_plan import now_text


DEFAULT_CONVERSATION_ID = "default"


def _message_count(messages: list[dict]) -> int:
    return sum(1 for message in messages if message.get("role") in {"user", "assistant"})


def _conversation_title(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "user":
            content = str(message.get("content", "")).strip()
            if content:
                return content[:24]
    return "新对话"


class ConversationsStoreMixin:
    def _conversations_path(self, course_id: str) -> Path:
        return self.paths.conversations_path(course_id)

    def _conversation_messages_path(self, course_id: str, conversation_id: str) -> Path:
        return self.paths.conversation_messages_path(course_id, conversation_id)

    def _conversation_memory_path(self, course_id: str, conversation_id: str) -> Path:
        return self.paths.conversation_memory_path(course_id, conversation_id)

    def _legacy_messages_path(self, course_id: str) -> Path:
        return self.paths.messages_path(course_id)

    def _legacy_memory_path(self, course_id: str) -> Path:
        return self.paths.memory_path(course_id)

    def ensure_conversation_state(self, course_id: str) -> List[Dict]:
        path = self._conversations_path(course_id)
        conversations = self._read_json(path, None)
        if conversations is not None:
            if conversations:
                return conversations
            return [self.create_conversation(course_id)]

        legacy_messages_path = self._legacy_messages_path(course_id)
        legacy_memory_path = self._legacy_memory_path(course_id)
        legacy_messages = self._read_json(legacy_messages_path, []) if legacy_messages_path.exists() else []
        legacy_memory = legacy_memory_path.read_text(encoding="utf-8") if legacy_memory_path.exists() else ""
        now = now_text()
        default = {
            "id": DEFAULT_CONVERSATION_ID,
            "title": "历史对话" if legacy_messages or legacy_memory else "新对话",
            "created_at": legacy_messages[0].get("created_at", now) if legacy_messages else now,
            "updated_at": legacy_messages[-1].get("created_at", now) if legacy_messages else now,
            "last_read_at": now,
            "message_count": _message_count(legacy_messages),
            "unread_count": 0,
        }
        self._write_json(self._conversation_messages_path(course_id, DEFAULT_CONVERSATION_ID), legacy_messages)
        self._write_text(self._conversation_memory_path(course_id, DEFAULT_CONVERSATION_ID), legacy_memory)
        conversations = [default]
        self._write_json(path, conversations)
        return conversations

    def list_conversations(self, course_id: str) -> List[Dict]:
        with self._lock_for(course_id):
            conversations = self.ensure_conversation_state(course_id)
            return sorted(conversations, key=lambda item: item.get("updated_at", ""), reverse=True)

    def create_conversation(self, course_id: str, title: str | None = None) -> Dict:
        with self._lock_for(course_id):
            conversations_path = self._conversations_path(course_id)
            conversations = self._read_json(conversations_path, []) if conversations_path.exists() else self.ensure_conversation_state(course_id)
            now = now_text()
            conversation = {
                "id": f"conv-{uuid4().hex[:12]}",
                "title": (title or "新对话").strip() or "新对话",
                "created_at": now,
                "updated_at": now,
                "last_read_at": now,
                "message_count": 0,
                "unread_count": 0,
            }
            conversations.append(conversation)
            self._write_json(self._conversations_path(course_id), conversations)
            self._write_json(self._conversation_messages_path(course_id, conversation["id"]), [])
            self._write_text(self._conversation_memory_path(course_id, conversation["id"]), "")
            return conversation

    def get_conversation(self, course_id: str, conversation_id: str | None = None) -> Dict:
        conversations = self.ensure_conversation_state(course_id)
        target_id = conversation_id or conversations[0]["id"]
        for conversation in conversations:
            if conversation["id"] == target_id:
                return conversation
        raise KeyError(target_id)

    def update_conversation(self, course_id: str, conversation_id: str, changes: dict) -> Dict:
        with self._lock_for(course_id):
            conversations = self.ensure_conversation_state(course_id)
            for conversation in conversations:
                if conversation["id"] == conversation_id:
                    title = str(changes.get("title", conversation["title"])).strip()
                    if title:
                        conversation["title"] = title[:64]
                    conversation["updated_at"] = now_text()
                    self._write_json(self._conversations_path(course_id), conversations)
                    return conversation
        raise KeyError(conversation_id)

    def delete_conversation(self, course_id: str, conversation_id: str) -> List[Dict]:
        with self._lock_for(course_id):
            conversations = self.ensure_conversation_state(course_id)
            remaining = [item for item in conversations if item["id"] != conversation_id]
            if len(remaining) == len(conversations):
                raise KeyError(conversation_id)
            if not remaining:
                remaining = [self.create_conversation(course_id)]
            self._write_json(self._conversations_path(course_id), remaining)
            return sorted(remaining, key=lambda item: item.get("updated_at", ""), reverse=True)

    def mark_conversation_read(self, course_id: str, conversation_id: str) -> Dict:
        with self._lock_for(course_id):
            conversations = self.ensure_conversation_state(course_id)
            for conversation in conversations:
                if conversation["id"] == conversation_id:
                    conversation["last_read_at"] = now_text()
                    conversation["unread_count"] = 0
                    self._write_json(self._conversations_path(course_id), conversations)
                    return conversation
        raise KeyError(conversation_id)

    def _touch_conversation(self, course_id: str, conversation_id: str, *, role: str | None = None, content: str = "") -> None:
        conversations = self.ensure_conversation_state(course_id)
        now = now_text()
        for conversation in conversations:
            if conversation["id"] == conversation_id:
                conversation["updated_at"] = now
                conversation["message_count"] = int(conversation.get("message_count", 0)) + 1
                if role == "assistant":
                    conversation["unread_count"] = int(conversation.get("unread_count", 0)) + 1
                if conversation.get("title") == "新对话" and role == "user":
                    title = content.strip()
                    if title:
                        conversation["title"] = title[:24]
                self._write_json(self._conversations_path(course_id), conversations)
                return
        raise KeyError(conversation_id)
