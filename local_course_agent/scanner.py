from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Dict, List


DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SUPPORTED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS


def is_image_file(path_or_name) -> bool:
    return Path(path_or_name).suffix.lower() in IMAGE_EXTENSIONS


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


class CourseScanner:
    """Scans a local root folder where each first-level folder is a course."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()

    def scan(self) -> List[Dict]:
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError(f"资料根目录不存在或不是文件夹: {self.root}")

        courses = []
        for course_dir in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            if not course_dir.is_dir() or course_dir.name.startswith("."):
                continue
            children = self._scan_children(course_dir)
            courses.append(
                {
                    "id": stable_id(str(course_dir)),
                    "name": course_dir.name,
                    "path": str(course_dir),
                    "children": children,
                    "file_count": self._count_files(children),
                }
            )
        return courses

    def _scan_children(self, folder: Path) -> List[Dict]:
        nodes = []
        for item in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                children = self._scan_children(item)
                if children:
                    nodes.append(
                        {
                            "id": stable_id(str(item)),
                            "name": item.name,
                            "path": str(item),
                            "type": "folder",
                            "children": children,
                        }
                    )
                continue
            if item.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            nodes.append(
                {
                    "id": stable_id(str(item)),
                    "name": item.name,
                    "path": str(item),
                    "type": "file",
                    "extension": item.suffix.lower(),
                    "size": item.stat().st_size,
                }
            )
        return nodes

    def _count_files(self, nodes: List[Dict]) -> int:
        total = 0
        for node in nodes:
            if node["type"] == "file":
                total += 1
            else:
                total += self._count_files(node.get("children", []))
        return total


class CourseCatalogCache:
    def __init__(self, ttl_seconds: float = 1.0):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._root: Path | None = None
        self._expires_at = 0.0
        self._courses: List[Dict] | None = None

    def get(self, root: Path) -> List[Dict]:
        resolved = Path(root).expanduser().resolve()
        now = time.monotonic()
        with self._lock:
            if self._courses is not None and self._root == resolved and now < self._expires_at:
                return self._courses
            courses = CourseScanner(resolved).scan()
            self._root = resolved
            self._courses = courses
            self._expires_at = now + self.ttl_seconds
            return courses

    def invalidate(self) -> None:
        with self._lock:
            self._expires_at = 0.0
            self._courses = None
