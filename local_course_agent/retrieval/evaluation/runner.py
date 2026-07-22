from __future__ import annotations

from typing import Dict, Sequence

from local_course_agent.retrieval.citation_check import check_citations
from local_course_agent.retrieval.evaluation.metrics import QUALITY_ORDER, answer_term_coverage, rate, same_file
from local_course_agent.retrieval.evaluation.schema import RagEvalCase
from local_course_agent.retrieval.rag import CourseKnowledgeBase


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
        quality: rate(count, total)
        for quality, count in quality_counts.items()
    }

    return {
        "summary": {
            "total_cases": total,
            "passed_cases": passed,
            "pass_rate": rate(passed, total),
            "citation_hit_rate": rate(citation_hits, total),
            "first_citation_hit_rate": rate(first_hits, total),
            "sufficient_rate": rate(quality_counts.get("sufficient", 0), total),
            "average_top_score": round(sum(top_scores) / len(top_scores), 4) if top_scores else 0.0,
            "average_answer_term_rate": round(sum(answer_term_rates) / len(answer_term_rates), 4) if answer_term_rates else 0.0,
            "answer_term_pass_rate": rate(answer_term_passed, total),
            "citation_support_pass_rate": rate(citation_support_passed, total),
            "forbidden_term_pass_rate": rate(forbidden_term_passed, total),
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
        if any(same_file(expected, returned) for returned in returned_files)
    ]
    missing_files = [expected for expected in expected_files if expected not in matched_files]
    first_citation_hit = bool(
        expected_files
        and returned_files
        and any(same_file(expected, returned_files[0]) for expected in expected_files)
    )
    retrieval_quality = str(answer.get("retrieval_quality", "none"))
    quality_ok = QUALITY_ORDER.get(retrieval_quality, 0) >= QUALITY_ORDER.get(case.min_quality, 1)
    citation_hit = bool(matched_files) if expected_files else bool(returned_files)
    top_score = citations[0].get("score") if citations else None
    found_terms, missing_terms, answer_term_rate = answer_term_coverage(answer_text, case.expected_terms)
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


__all__ = ["run_rag_eval"]
