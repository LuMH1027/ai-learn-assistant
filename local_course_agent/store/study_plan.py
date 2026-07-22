from __future__ import annotations

from typing import Dict, List

from local_course_agent.storage.study_plan import normalize_study_plan_item, now_text


class StudyPlanStoreMixin:
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
