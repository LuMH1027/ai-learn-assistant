from __future__ import annotations

from typing import Dict

from local_course_agent.learning.mastery import (
    apply_answer_result,
    create_mastery_state,
    normalize_state,
    resolve_mistake,
    upsert_knowledge_point,
)


class MasteryStoreMixin:
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

    def resolve_mastery_mistake(self, course_id: str, mistake_id: str) -> Dict | None:
        with self._lock_for(course_id):
            state = self.get_mastery_state(course_id)
            next_mistakes = []
            resolved = None
            for mistake in state["mistakes"]:
                if mistake["id"] == str(mistake_id):
                    resolved = resolve_mistake(mistake)
                    next_mistakes.append(resolved)
                else:
                    next_mistakes.append(mistake)
            if resolved is None:
                return None
            state["mistakes"] = next_mistakes
            state["updated_at"] = resolved["updated_at"]
            self._write_json(self._mastery_path(course_id), state)
            return state
