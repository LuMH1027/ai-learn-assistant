from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_course_agent.retrieval.rag import CourseKnowledgeBase  # noqa: E402
from local_course_agent.retrieval.rag_eval import (  # noqa: E402
    load_eval_cases,
    render_markdown_report,
    run_demo_baseline,
    run_rag_eval,
    sample_eval_cases,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run local RAG retrieval evaluation cases.")
    parser.add_argument("--index-dir", default="data/indexes", help="Directory containing course index JSON files.")
    parser.add_argument("--cases", help="JSON file with eval cases. Uses sample cases when omitted.")
    parser.add_argument(
        "--demo-baseline",
        action="store_true",
        help="Index repository sample_materials and run the built-in demo baseline cases.",
    )
    parser.add_argument("--sample-root", default="sample_materials", help="sample_materials root for --demo-baseline.")
    parser.add_argument("--course-id", help="Override course_id for all loaded or sample cases.")
    parser.add_argument("--strategy", default="hybrid", choices=["lexical", "hybrid"], help="RAG search strategy.")
    parser.add_argument("--format", default="markdown", choices=["markdown", "json"], help="Report output format.")
    parser.add_argument("--output", help="Optional path to write the report.")
    args = parser.parse_args(argv)

    if args.demo_baseline:
        if args.cases or args.course_id:
            parser.error("--demo-baseline cannot be combined with --cases or --course-id.")
        report = run_demo_baseline(Path(args.index_dir), sample_root=Path(args.sample_root), strategy=args.strategy)
    else:
        cases = load_eval_cases(Path(args.cases)) if args.cases else sample_eval_cases(args.course_id or "sample-course")
        if args.course_id:
            cases = [
                type(case)(
                    id=case.id,
                    course_id=args.course_id,
                    question=case.question,
                    expected_files=case.expected_files,
                    min_quality=case.min_quality,
                    tags=case.tags,
                )
                for case in cases
            ]
        report = run_rag_eval(CourseKnowledgeBase(Path(args.index_dir)), cases, strategy=args.strategy)
    content = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else render_markdown_report(report)
    )
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0 if report["summary"]["passed_cases"] == report["summary"]["total_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
