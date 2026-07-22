from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.retrieval.rag_eval import RagEvalCase


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_ROOT = REPO_ROOT / "sample_materials"
DEMO_OS_COURSE_ID = "demo-operating-system"
DEMO_DATA_STRUCTURE_COURSE_ID = "demo-data-structures"


def sample_eval_cases(course_id: str = "sample-course") -> List[RagEvalCase]:
    return [
        RagEvalCase(
            id="os-process-thread",
            course_id=course_id,
            question="进程和线程的区别是什么？",
            expected_files=["README.md"],
            min_quality="partial",
            tags=["process"],
        ),
        RagEvalCase(
            id="os-page-table",
            course_id=course_id,
            question="页表在虚拟内存管理中起什么作用？",
            expected_files=["README.md"],
            min_quality="partial",
            tags=["memory-management"],
        ),
        RagEvalCase(
            id="os-file-system",
            course_id=course_id,
            question="文件系统需要解决哪些核心问题？",
            expected_files=["README.md"],
            min_quality="partial",
            tags=["file-system"],
        ),
    ]


def demo_eval_cases(
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> List[RagEvalCase]:
    """Return eval cases aligned with files under sample_materials."""

    return [
        *sample_eval_cases(os_course_id),
        RagEvalCase(
            id="ds-binary-search-tree",
            course_id=data_structure_course_id,
            question="二叉搜索树为什么适合查找、插入和删除？",
            expected_files=["树.md"],
            min_quality="partial",
            tags=["tree"],
        ),
        RagEvalCase(
            id="ds-balanced-tree",
            course_id=data_structure_course_id,
            question="平衡二叉树为什么能提高查找效率？",
            expected_files=["树.md"],
            min_quality="partial",
            tags=["tree"],
        ),
        RagEvalCase(
            id="ds-stack-queue",
            course_id=data_structure_course_id,
            question="栈和队列分别适合哪些典型场景？",
            expected_files=["栈和队列.md"],
            min_quality="partial",
            tags=["linear-list"],
        ),
    ]


def index_sample_materials(
    knowledge_base: CourseKnowledgeBase,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> Dict:
    """Index the repository demo materials and return a compact manifest."""

    sample_root = Path(sample_root)
    materials = [
        {
            "course_id": os_course_id,
            "file_id": "sample-os-readme",
            "file_name": "README.md",
            "path": sample_root / "操作系统" / "README.md",
        },
        {
            "course_id": os_course_id,
            "file_id": "sample-os-review",
            "file_name": "复习题.txt",
            "path": sample_root / "操作系统" / "复习题.txt",
        },
        {
            "course_id": data_structure_course_id,
            "file_id": "sample-ds-tree",
            "file_name": "树.md",
            "path": sample_root / "数据结构" / "树.md",
        },
        {
            "course_id": data_structure_course_id,
            "file_id": "sample-ds-stack-queue",
            "file_name": "栈和队列.md",
            "path": sample_root / "数据结构" / "栈和队列.md",
        },
    ]
    indexed_files = []
    missing_files = []
    for material in materials:
        path = Path(material["path"])
        if not path.exists():
            missing_files.append(str(path))
            continue
        text = path.read_text(encoding="utf-8")
        chunk_count = knowledge_base.index_text(
            material["course_id"],
            material["file_id"],
            material["file_name"],
            text,
        )
        indexed_files.append(
            {
                "course_id": material["course_id"],
                "file_id": material["file_id"],
                "file_name": material["file_name"],
                "path": str(path),
                "chunks_after_file": chunk_count,
            }
        )
    return {
        "sample_root": str(sample_root),
        "course_ids": [os_course_id, data_structure_course_id],
        "indexed_files": indexed_files,
        "missing_files": missing_files,
    }
