from __future__ import annotations

import threading

from local_course_agent.storage.paths import safe_course_id


class CourseLocksMixin:
    def _lock_for(self, course_id: str) -> threading.RLock:
        key = safe_course_id(course_id)
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.RLock()
            return self._locks[key]
