from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from local_course_agent.retrieval.citation_check import check_citations
from local_course_agent.retrieval.rag import CourseKnowledgeBase


QUALITY_ORDER = {"none": 0, "partial": 1, "sufficient": 2}


@dataclass(frozen=True)
class RagEvalCase:
    id: str
    course_id: str
    question: str
    expected_files: List[str]
    min_quality: str = "partial"
    tags: List[str] = field(default_factory=list)
    expected_terms: List[str] = field(default_factory=list)
    forbidden_terms: List[str] = field(default_factory=list)
    min_answer_term_rate: float = 0.0
    max_unsupported_claims: Optional[int] = None

    @classmethod
    def from_dict(cls, payload: Dict) -> "RagEvalCase":
        expected_files = payload.get("expected_files") or payload.get("expected_reference_files") or []
        if isinstance(expected_files, str):
            expected_files = [expected_files]
        expected_terms = payload.get("expected_terms") or payload.get("expected_answer_terms") or []
        if isinstance(expected_terms, str):
            expected_terms = [expected_terms]
        forbidden_terms = payload.get("forbidden_terms") or []
        if isinstance(forbidden_terms, str):
            forbidden_terms = [forbidden_terms]
        max_unsupported = payload.get("max_unsupported_claims")
        return cls(
            id=str(payload.get("id") or payload["question"][:32]),
            course_id=str(payload["course_id"]),
            question=str(payload["question"]),
            expected_files=[str(item) for item in expected_files],
            min_quality=str(payload.get("min_quality", "partial")),
            tags=[str(item) for item in payload.get("tags", [])],
            expected_terms=[str(item) for item in expected_terms],
            forbidden_terms=[str(item) for item in forbidden_terms],
            min_answer_term_rate=float(payload.get("min_answer_term_rate", 0.0) or 0.0),
            max_unsupported_claims=None if max_unsupported in (None, "") else int(max_unsupported),
        )


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
    answer_term_rates = []
    answer_term_passed = 0
    citation_support_passed = 0
    forbidden_term_passed = 0
    for item in case_results:
        quality_counts[item["retrieval_quality"]] = quality_counts.get(item["retrieval_quality"], 0) + 1
        if item["top_score"] is not None:
            top_scores.append(float(item["top_score"]))
        answer_term_rates.append(float(item.get("answer_term_rate", 0.0)))
        answer_term_passed += 1 if item.get("answer_terms_ok") else 0
        citation_support_passed += 1 if item.get("citation_support_ok") else 0
        forbidden_term_passed += 1 if item.get("forbidden_terms_ok") else 0
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
            "average_answer_term_rate": round(sum(answer_term_rates) / len(answer_term_rates), 4) if answer_term_rates else 0.0,
            "answer_term_pass_rate": _rate(answer_term_passed, total),
            "citation_support_pass_rate": _rate(citation_support_passed, total),
            "forbidden_term_pass_rate": _rate(forbidden_term_passed, total),
            "quality_counts": quality_counts,
            "quality_distribution": quality_distribution,
        },
        "cases": case_results,
    }


def _evaluate_case(knowledge_base: CourseKnowledgeBase, case: RagEvalCase, strategy: str) -> Dict:
    answer = knowledge_base.answer(case.course_id, case.question, strategy=strategy)
    citations = answer.get("citations", [])
    answer_text = str(answer.get("answer") or "")
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
    found_terms, missing_terms, answer_term_rate = _answer_term_coverage(answer_text, case.expected_terms)
    forbidden_hits = [term for term in case.forbidden_terms if term and term in answer_text]
    citation_check = check_citations(answer_text, citations)
    unsupported_count = int(citation_check.get("stats", {}).get("unsupported_count") or 0)
    answer_terms_ok = answer_term_rate >= case.min_answer_term_rate
    forbidden_terms_ok = not forbidden_hits
    citation_support_ok = (
        True
        if case.max_unsupported_claims is None
        else unsupported_count <= case.max_unsupported_claims
    )
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
        "answer": answer_text,
        "expected_terms": list(case.expected_terms),
        "found_answer_terms": found_terms,
        "missing_answer_terms": missing_terms,
        "answer_term_rate": answer_term_rate,
        "min_answer_term_rate": case.min_answer_term_rate,
        "answer_terms_ok": answer_terms_ok,
        "forbidden_terms": list(case.forbidden_terms),
        "forbidden_term_hits": forbidden_hits,
        "forbidden_terms_ok": forbidden_terms_ok,
        "unsupported_claim_count": unsupported_count,
        "max_unsupported_claims": case.max_unsupported_claims,
        "citation_support_ok": citation_support_ok,
        "citation_check": citation_check,
        "passed": citation_hit and quality_ok and answer_terms_ok and forbidden_terms_ok and citation_support_ok,
        "top_score": top_score,
        "selected_trace": answer.get("retrieval_trace", {}).get("selected", []),
    }


def _same_file(expected: str, returned: str) -> bool:
    expected_name = Path(expected).name
    returned_name = Path(returned).name
    return expected == returned or expected_name == returned_name


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _answer_term_coverage(answer: str, expected_terms: Sequence[str]) -> tuple[List[str], List[str], float]:
    terms = [str(term) for term in expected_terms if str(term).strip()]
    if not terms:
        return [], [], 1.0
    found = [term for term in terms if term.lower() in answer.lower()]
    missing = [term for term in terms if term not in found]
    return found, missing, round(len(found) / len(terms), 4)


DEFAULT_SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample_materials"
DEMO_OS_COURSE_ID = "demo-operating-system"
DEMO_DATA_STRUCTURE_COURSE_ID = "demo-data-structures"


def sample_eval_cases(course_id: str = "sample-course") -> List[RagEvalCase]:
    from local_course_agent.evaluation.demo_fixtures import sample_eval_cases as _sample_eval_cases

    return _sample_eval_cases(course_id)


def demo_eval_cases(
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> List[RagEvalCase]:
    from local_course_agent.evaluation.demo_fixtures import demo_eval_cases as _demo_eval_cases

    return _demo_eval_cases(os_course_id, data_structure_course_id)


def index_sample_materials(
    knowledge_base: CourseKnowledgeBase,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> Dict:
    from local_course_agent.evaluation.demo_fixtures import index_sample_materials as _index_sample_materials

    return _index_sample_materials(knowledge_base, sample_root, os_course_id, data_structure_course_id)


def run_demo_baseline(
    index_dir: Path,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    strategy: str = "hybrid",
) -> Dict:
    from local_course_agent.evaluation.demo_baseline import run_demo_baseline as _run_demo_baseline

    return _run_demo_baseline(index_dir, sample_root=sample_root, strategy=strategy)


def run_chatflow_structure_eval(knowledge_base: CourseKnowledgeBase, strategy: str = "hybrid") -> Dict:
    from local_course_agent.evaluation.gates import run_chatflow_structure_eval as _run_chatflow_structure_eval

    return _run_chatflow_structure_eval(knowledge_base, strategy=strategy)


def run_summary_pipeline_eval(knowledge_base: CourseKnowledgeBase, course_names: Optional[Dict[str, str]] = None) -> Dict:
    from local_course_agent.evaluation.gates import run_summary_pipeline_eval as _run_summary_pipeline_eval

    return _run_summary_pipeline_eval(knowledge_base, course_names=course_names)


def render_markdown_report(report: Dict) -> str:
    from local_course_agent.evaluation.reports import render_markdown_report as _render_markdown_report

    return _render_markdown_report(report)
