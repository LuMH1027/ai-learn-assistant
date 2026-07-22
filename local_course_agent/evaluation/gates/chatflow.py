from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Dict

from local_course_agent.api.chat import ChatFlow
from local_course_agent.evaluation.demo_fixtures import (
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
)
from local_course_agent.evaluation.gates.fakes import EvalChatStore, StrategyKnowledgeBase
from local_course_agent.evaluation.gates.results import course_name, quality_case_result
from local_course_agent.evaluation.quality import evaluate_chatflow_payload, summarize_quality_results
from local_course_agent.retrieval.rag import CourseKnowledgeBase


def run_chatflow_structure_eval(
    knowledge_base: CourseKnowledgeBase,
    strategy: str = "hybrid",
) -> Dict:
    store = EvalChatStore()
    context = SimpleNamespace(
        config={"ai": {}, "web_search": {}},
        find_course=lambda course_id: {"name": course_name(course_id)},
        kb=StrategyKnowledgeBase(knowledge_base, strategy),
        store=store,
    )
    flow = ChatFlow(context=context, data_dir=Path("/tmp/course-rag-eval-chat"), emit=lambda _event: None)
    cases = [
        {
            "id": "chatflow-page-table",
            "course_id": DEMO_OS_COURSE_ID,
            "question": "页表在虚拟内存管理中起什么作用？",
            "expect_contextual_query": False,
        },
        {
            "id": "chatflow-context-follow-up",
            "course_id": DEMO_OS_COURSE_ID,
            "question": "它和 TLB 有什么关系？",
            "expect_contextual_query": True,
        },
        {
            "id": "chatflow-stack-queue",
            "course_id": DEMO_DATA_STRUCTURE_COURSE_ID,
            "question": "栈和队列分别适合哪些典型场景？",
            "expect_contextual_query": False,
        },
    ]
    results = []
    for case in cases:
        payload = flow.run(case["course_id"], {"question": case["question"], "mode": "answer"}, [])
        quality = evaluate_chatflow_payload(
            payload,
            expect_contextual_query=bool(case["expect_contextual_query"]),
            min_citations=1,
        )
        results.append(
            quality_case_result(
                case_id=case["id"],
                course_id=case["course_id"],
                quality=quality,
                extra={
                    "question": case["question"],
                },
            )
        )
    return {
        "summary": summarize_quality_results(results),
        "cases": results,
    }
