from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


QUALITY_ORDER = ("none", "partial", "sufficient")


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
            f"- Average answer term rate: {summary.get('average_answer_term_rate', 0):.2%}",
            f"- Answer term pass rate: {summary.get('answer_term_pass_rate', 0):.2%}",
            f"- Citation support pass rate: {summary.get('citation_support_pass_rate', 0):.2%}",
            f"- Forbidden term pass rate: {summary.get('forbidden_term_pass_rate', 0):.2%}",
            f"- ChatFlow structure pass rate: {summary.get('chatflow_structure_pass_rate', 0):.2%}",
            f"- Summary pipeline pass rate: {summary.get('summary_pipeline_pass_rate', 0):.2%}",
            f"- Quality gate passed: {summary.get('quality_gate_passed', summary['passed_cases'] == summary['total_cases'])}",
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
                f"- Expected answer terms: {', '.join(item.get('expected_terms', [])) or '(none)'}",
                f"- Missing answer terms: {', '.join(item.get('missing_answer_terms', [])) or '(none)'}",
                f"- Forbidden term hits: {', '.join(item.get('forbidden_term_hits', [])) or '(none)'}",
                f"- Unsupported claims: {item.get('unsupported_claim_count', 0)}",
                "",
            ]
        )
    _append_quality_section(lines, "ChatFlow Structure Eval", report.get("chatflow_eval"))
    _append_quality_section(lines, "Summary Pipeline Eval", report.get("summary_eval"))
    return "\n".join(lines).rstrip() + "\n"


def _append_quality_section(lines: List[str], title: str, section: Any) -> None:
    if not isinstance(section, Mapping):
        return
    summary = section.get("summary", {}) if isinstance(section.get("summary"), Mapping) else {}
    cases = section.get("cases", []) if isinstance(section.get("cases"), Sequence) else []
    lines.extend(
        [
            f"## {title}",
            "",
            f"- Total cases: {summary.get('total_cases', 0)}",
            f"- Passed cases: {summary.get('passed_cases', 0)}",
            f"- Pass rate: {float(summary.get('pass_rate', 0)):.2%}",
            f"- Failed checks: {summary.get('failed_checks', {}) or '(none)'}",
            "",
        ]
    )
    for item in cases:
        if not isinstance(item, Mapping):
            continue
        status = "PASS" if item.get("passed") else "FAIL"
        metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), Mapping) else {}
        failed = item.get("failed_checks", []) if isinstance(item.get("failed_checks"), Sequence) else []
        failed_names = [
            str(check.get("name"))
            for check in failed
            if isinstance(check, Mapping) and check.get("name")
        ]
        lines.extend(
            [
                f"### {status} {item.get('id', '(unknown)')}",
                "",
                f"- Course: `{item.get('course_id', '')}`",
                f"- Metrics: {metrics}",
                f"- Failed checks: {', '.join(failed_names) or '(none)'}",
                "",
            ]
        )
