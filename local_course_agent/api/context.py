from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local_course_agent.config import load_config
from local_course_agent.learning.service import CourseIndexJobs
from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.retrieval.reranking import create_reranker
from local_course_agent.scanner import CourseCatalogCache
from local_course_agent.store import AppStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "web" / "dist"
CONFIG_PATH = DATA_DIR / "config.json"


def is_safe_material_root(
    root: Path,
    *,
    project_root: Path = PROJECT_ROOT,
    data_dir: Path = DATA_DIR,
) -> bool:
    resolved = Path(root).expanduser().resolve()
    blocked_roots = {resolved.anchor, str(Path(data_dir).resolve()), str(Path(project_root).resolve())}
    if str(resolved) in blocked_roots:
        return False
    try:
        resolved.relative_to(Path(data_dir).resolve())
        return False
    except ValueError:
        return True


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class AppContext:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.store = AppStore(self.data_dir)
        self.kb = CourseKnowledgeBase(self.data_dir / "indexes")
        self.course_cache = CourseCatalogCache()
        self.index_jobs = CourseIndexJobs(self.kb, snapshot_path=self.data_dir / "index_jobs.json")

    @property
    def config(self):
        config = load_config(self.data_dir / "config.json")
        configure = getattr(self.kb, "configure_embeddings", None)
        if callable(configure):
            configure(config.get("ai", {}))
        configure_reranker = getattr(self.kb, "configure_reranker", None)
        if callable(configure_reranker):
            configure_reranker(create_reranker(config.get("ai", {})), config.get("ai", {}))
        return config

    def root(self) -> Path | None:
        root = self.config.get("root_folder", "")
        if not root:
            return None
        return Path(root).expanduser().resolve()

    def courses(self):
        root = self.root()
        if not root:
            return []
        return self.course_cache.get(root)

    def invalidate_courses(self) -> None:
        self.course_cache.invalidate()

    def find_file(self, file_id: str) -> Path | None:
        for course in self.courses():
            found = find_file_node(course.get("children", []), file_id)
            if found:
                return Path(found["path"]).resolve()
        return None

    def find_course(self, course_id: str):
        for course in self.courses():
            if course["id"] == course_id:
                return course
        return None


def find_file_node(nodes, file_id):
    for node in nodes:
        if node["id"] == file_id and node["type"] == "file":
            return node
        if node["type"] == "folder":
            found = find_file_node(node.get("children", []), file_id)
            if found:
                return found
    return None
