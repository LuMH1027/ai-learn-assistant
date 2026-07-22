from __future__ import annotations

from pathlib import Path


def safe_course_id(course_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in course_id) or "course"


class CourseStorePaths:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir = self.data_dir / "course_memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def course_dir(self, course_id: str) -> Path:
        path = self.memory_dir / safe_course_id(course_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def messages_path(self, course_id: str) -> Path:
        return self.course_dir(course_id) / "messages.json"

    def memory_path(self, course_id: str) -> Path:
        return self.course_dir(course_id) / "memory.md"

    def notes_path(self, course_id: str) -> Path:
        return self.course_dir(course_id) / "notes.json"

    def study_plan_path(self, course_id: str) -> Path:
        return self.course_dir(course_id) / "study_plan.json"

    def mastery_path(self, course_id: str) -> Path:
        return self.course_dir(course_id) / "mastery.json"
