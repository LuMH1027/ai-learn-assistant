from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from local_course_agent.rag import CourseKnowledgeBase


QUALITY_ORDER = {"none": 0, "partial": 1, "sufficient": 2}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_ROOT = REPO_ROOT / "sample_materials"
DEMO_OS_COURSE_ID = "demo-operating-system"
DEMO_DATA_STRUCTURE_COURSE_ID = "demo-data-structures"


@dataclass(frozen=True)
class RagEvalCase:
    id: str
    course_id: str
    question: str
    expected_files: List[str]
    min_quality: str = "partial"
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict) -> "RagEvalCase":
        expected_files = payload.get("expected_files") or payload.get("expected_reference_files") or []
        if isinstance(expected_files, str):
            expected_files = [expected_files]
        return cls(
            id=str(payload.get("id") or payload["question"][:32]),
            course_id=str(payload["course_id"]),
            question=str(payload["question"]),
            expected_files=[str(item) for item in expected_files],
            min_quality=str(payload.get("min_quality", "partial")),
            tags=[str(item) for item in payload.get("tags", [])],
        )


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


def run_demo_baseline(
    index_dir: Path,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    strategy: str = "hybrid",
) -> Dict:
    knowledge_base = CourseKnowledgeBase(Path(index_dir))
    manifest = index_sample_materials(knowledge_base, Path(sample_root))
    cases = demo_eval_cases()
    report = run_rag_eval(knowledge_base, cases, strategy=strategy)
    report["baseline"] = {
        "name": "sample_materials demo baseline",
        "sample_root": manifest["sample_root"],
        "course_ids": manifest["course_ids"],
        "indexed_files": len(manifest["indexed_files"]),
        "missing_files": manifest["missing_files"],
        "case_ids": [case.id for case in cases],
    }
    return report


def load_eval_cases(path: Path) -> List[RagEvalCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError("RAG eval cases must be a JSON list or an object with a 'cases' list.")
    return [RagEvalCase.from_dict(item) for item in raw_cases]


def run_rag_eval(
    knowledge_base: CourseKnowledgeBase,
    cases: Sequence[RagEvalCase],
    strategy: str = "hybrid",
) -> Dict:
    case_results = [_evaluate_case(knowledge_base, case, strategy=strategy) for case in cases]
    total = len(case_results)
    passed = sum(1 for item in case_results if item["passed"])
    citation_hits = sum(1 for item in case_results if item["citation_hit"])
    first_hits = sum(1 for item in case_results if item["first_citation_hit"])
    quality_counts = {quality: 0 for quality in QUALITY_ORDER}
    top_scores = []
    for item in case_results:
        quality_counts[item["retrieval_quality"]] = quality_counts.get(item["retrieval_quality"], 0) + 1
        if item["top_score"] is not None:
            top_scores.append(float(item["top_score"]))
    quality_distribution = {
        quality: _rate(count, total)
        for quality, count in quality_counts.items()
    }

    return {
        "summary": {
            "total_cases": total,
            "passed_cases": passed,
            "pass_rate": _rate(passed, total),
            "citation_hit_rate": _rate(citation_hits, total),
            "first_citation_hit_rate": _rate(first_hits, total),
            "sufficient_rate": _rate(quality_counts.get("sufficient", 0), total),
            "average_top_score": round(sum(top_scores) / len(top_scores), 4) if top_scores else 0.0,
            "quality_counts": quality_counts,
            "quality_distribution": quality_distribution,
        },
        "cases": case_results,
    }


def render_markdown_report(report: Dict) -> str:
    summary = report["summary"]
    baseline = report.get("baseline")
    lines = [
        "# RAG Eval Baseline Report" if baseline else "# RAG Eval Report",
        "",
    ]
    if baseline:
        lines.extend(
            [
                "## Baseline",
                "",
                f"- Name: {baseline['name']}",
                f"- Sample root: `{baseline['sample_root']}`",
                f"- Course IDs: {', '.join(baseline['course_ids'])}",
                f"- Indexed files: {baseline['indexed_files']}",
                f"- Missing files: {', '.join(baseline['missing_files']) or '(none)'}",
                "",
            ]
        )
    quality_distribution = summary.get("quality_distribution", {})
    quality_distribution_text = ", ".join(
        f"{quality} {quality_distribution.get(quality, 0):.2%}"
        for quality in QUALITY_ORDER
    )
    lines.extend(
        [
        "## Summary",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Passed cases: {summary['passed_cases']}",
        f"- Pass rate: {summary['pass_rate']:.2%}",
        f"- Citation hit rate: {summary['citation_hit_rate']:.2%}",
        f"- First citation hit rate: {summary['first_citation_hit_rate']:.2%}",
        f"- Sufficient rate: {summary['sufficient_rate']:.2%}",
        f"- Average top score: {summary['average_top_score']}",
        f"- Quality counts: {summary['quality_counts']}",
        f"- Quality distribution: {quality_distribution_text}",
        "",
        "## Cases",
        "",
        ]
    )
    for item in report["cases"]:
        status = "PASS" if item["passed"] else "FAIL"
        lines.extend(
            [
                f"### {status} {item['id']}",
                "",
                f"- Course: `{item['course_id']}`",
                f"- Question: {item['question']}",
                f"- Expected files: {', '.join(item['expected_files']) or '(none)'}",
                f"- Returned files: {', '.join(item['returned_files']) or '(none)'}",
                f"- Retrieval quality: {item['retrieval_quality']}",
                f"- Top score: {item['top_score'] if item['top_score'] is not None else '(none)'}",
                f"- Missing expected files: {', '.join(item['missing_expected_files']) or '(none)'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _evaluate_case(knowledge_base: CourseKnowledgeBase, case: RagEvalCase, strategy: str) -> Dict:
    answer = knowledge_base.answer(case.course_id, case.question, strategy=strategy)
    citations = answer.get("citations", [])
    returned_files = [str(citation.get("file_name", "")) for citation in citations if citation.get("file_name")]
    expected_files = list(case.expected_files)
    matched_files = [
        expected
        for expected in expected_files
        if any(_same_file(expected, returned) for returned in returned_files)
    ]
    missing_files = [expected for expected in expected_files if expected not in matched_files]
    first_citation_hit = bool(
        expected_files
        and returned_files
        and any(_same_file(expected, returned_files[0]) for expected in expected_files)
    )
    retrieval_quality = str(answer.get("retrieval_quality", "none"))
    quality_ok = QUALITY_ORDER.get(retrieval_quality, 0) >= QUALITY_ORDER.get(case.min_quality, 1)
    citation_hit = bool(matched_files) if expected_files else bool(returned_files)
    top_score = citations[0].get("score") if citations else None
    return {
        "id": case.id,
        "course_id": case.course_id,
        "question": case.question,
        "tags": list(case.tags),
        "expected_files": expected_files,
        "returned_files": returned_files,
        "matched_expected_files": matched_files,
        "missing_expected_files": missing_files,
        "citation_hit": citation_hit,
        "first_citation_hit": first_citation_hit,
        "retrieval_quality": retrieval_quality,
        "min_quality": case.min_quality,
        "quality_ok": quality_ok,
        "passed": citation_hit and quality_ok,
        "top_score": top_score,
        "selected_trace": answer.get("retrieval_trace", {}).get("selected", []),
    }


def _same_file(expected: str, returned: str) -> bool:
    expected_name = Path(expected).name
    returned_name = Path(returned).name
    return expected == returned or expected_name == returned_name


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0
