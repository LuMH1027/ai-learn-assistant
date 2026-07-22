from __future__ import annotations

from typing import Dict, Optional

from local_course_agent.evaluation.demo_fixtures import (
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
)
from local_course_agent.evaluation.gates.fakes import EvalSummaryClient
from local_course_agent.evaluation.gates.results import summary_case_result
from local_course_agent.evaluation.quality import evaluate_summary_payload, summarize_quality_results
from local_course_agent.learning.service import generate_course_summary
from local_course_agent.learning.summary import generate_map_reduce_course_summary
from local_course_agent.retrieval.rag import CourseKnowledgeBase


def run_summary_pipeline_eval(
    knowledge_base: CourseKnowledgeBase,
    course_names: Optional[Dict[str, str]] = None,
) -> Dict:
    course_names = course_names or {
        DEMO_OS_COURSE_ID: "操作系统",
        DEMO_DATA_STRUCTURE_COURSE_ID: "数据结构",
    }
    results = []
    for course_id, course_name in course_names.items():
        service_payload = generate_course_summary(knowledge_base, course_id, course_name, ai_config={})
        service_quality = evaluate_summary_payload(
            service_payload,
            expected_method="extractive",
            min_citation_quote_rate=1.0,
        )
        results.append(summary_case_result(f"summary-service-{course_id}", course_id, service_payload, service_quality))

        map_reduce_payload = generate_map_reduce_course_summary(
            knowledge_base,
            course_id,
            course_name,
            ai_config={"provider": "eval-stub"},
            create_client=lambda _config: EvalSummaryClient(),
        )
        map_reduce_payload["summary_method"] = "map_reduce"
        map_reduce_quality = evaluate_summary_payload(
            map_reduce_payload,
            expected_method="map_reduce",
            min_citation_quote_rate=1.0,
            min_evidence_label_rate=1.0,
        )
        results.append(
            summary_case_result(f"summary-map-reduce-{course_id}", course_id, map_reduce_payload, map_reduce_quality)
        )
    return {
        "summary": summarize_quality_results(results),
        "cases": results,
    }
