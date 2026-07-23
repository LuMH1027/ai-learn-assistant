from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict

from local_course_agent.storage.codecs import read_json, write_json, write_text
from local_course_agent.storage.migration import migrate_legacy_sqlite
from local_course_agent.storage.paths import CourseStorePaths

from .conversations import ConversationsStoreMixin
from .locks import CourseLocksMixin
from .mastery import MasteryStoreMixin
from .memory import MemoryStoreMixin
from .messages import MessagesStoreMixin
from .notes import NotesStoreMixin
from .study_plan import StudyPlanStoreMixin


class AppStore(
    CourseLocksMixin,
    ConversationsStoreMixin,
    MessagesStoreMixin,
    MemoryStoreMixin,
    NotesStoreMixin,
    StudyPlanStoreMixin,
    MasteryStoreMixin,
):
    """File-backed per-course state.

    A course's chat, compact memory, and notes live under:
    data/course_memory/<course_id>/

    Deleting one of those files clears that part of the course state.
    """

    def __init__(self, data_dir: Path):
        self.paths = CourseStorePaths(data_dir)
        self.data_dir = self.paths.data_dir
        self.memory_dir = self.paths.memory_dir
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        migrate_legacy_sqlite(self.data_dir, self.paths)

    def _course_dir(self, course_id: str) -> Path:
        return self.paths.course_dir(course_id)

    def _messages_path(self, course_id: str) -> Path:
        return self.paths.messages_path(course_id)

    def _memory_path(self, course_id: str) -> Path:
        return self.paths.memory_path(course_id)

    def _notes_path(self, course_id: str) -> Path:
        return self.paths.notes_path(course_id)

    def _study_plan_path(self, course_id: str) -> Path:
        return self.paths.study_plan_path(course_id)

    def _mastery_path(self, course_id: str) -> Path:
        return self.paths.mastery_path(course_id)

    def _read_json(self, path: Path, default):
        return read_json(path, default)

    def _write_json(self, path: Path, data) -> None:
        write_json(path, data)

    def _write_text(self, path: Path, text: str) -> None:
        write_text(path, text)
