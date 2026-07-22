from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional

from local_course_agent.api.chat import ChatFlow
from local_course_agent.evaluation.demo_fixtures import (
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
)
from local_course_agent.evaluation.quality import (
    evaluate_chatflow_payload,
    evaluate_summary_payload,
    summarize_quality_results,
)
from local_course_agent.learning.service import generate_course_summary
from local_course_agent.learning.summary import generate_map_reduce_course_summary
from local_course_agent.retrieval.rag import CourseKnowledgeBase


def run_chatflow_structure_eval(
    knowledge_base: CourseKnowledgeBase,
    strategy: str = "hybrid",
) -> Dict:
    store = _EvalChatStore()
    context = SimpleNamespace(
        config={"ai": {}, "web_search": {}},
        find_course=lambda course_id: {"name": _course_name(course_id)},
        kb=_StrategyKnowledgeBase(knowledge_base, strategy),
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
            {
                "id": case["id"],
                "course_id": case["course_id"],
                "question": case["question"],
                "passed": quality["passed"],
                "checks": quality["checks"],
                "failed_checks": quality["failed_checks"],
                "metrics": quality["metrics"],
            }
        )
    return {
        "summary": summarize_quality_results(results),
        "cases": results,
    }


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
        results.append(_summary_eval_case(f"summary-service-{course_id}", course_id, service_payload, service_quality))

        map_reduce_payload = generate_map_reduce_course_summary(
            knowledge_base,
            course_id,
            course_name,
            ai_config={"provider": "eval-stub"},
            create_client=lambda _config: _EvalSummaryClient(),
        )
        map_reduce_payload["summary_method"] = "map_reduce"
        map_reduce_quality = evaluate_summary_payload(
            map_reduce_payload,
            expected_method="map_reduce",
            min_citation_quote_rate=1.0,
            min_evidence_label_rate=1.0,
        )
        results.append(
            _summary_eval_case(f"summary-map-reduce-{course_id}", course_id, map_reduce_payload, map_reduce_quality)
        )
    return {
        "summary": summarize_quality_results(results),
        "cases": results,
    }


class _StrategyKnowledgeBase:
    def __init__(self, knowledge_base: CourseKnowledgeBase, strategy: str):
        self.knowledge_base = knowledge_base
        self.strategy = strategy

    def answer(self, course_id: str, query: str) -> Dict:
        return self.knowledge_base.answer(course_id, query, strategy=self.strategy)


class _EvalChatStore:
    def __init__(self):
        self.messages_by_course: Dict[str, List[Dict]] = {}

    def list_messages(self, course_id: str) -> List[Dict]:
        return list(self.messages_by_course.get(course_id, []))

    def add_message(self, course_id: str, role: str, content: str, citations=None, trace=None) -> None:
        self.messages_by_course.setdefault(course_id, []).append(
            {
                "role": role,
                "content": content,
                "citations": list(citations or []),
                "trace": list(trace or []),
            }
        )

    def update_memory_from_question(self, course_id: str, question: str) -> str:
        return f"- Eval memory: {question[:40]}"

    def get_memory(self, course_id: str) -> str:
        return ""


class _EvalSummaryClient:
    def enabled(self) -> bool:
        return True

    def generate(self, prompt: str) -> str:
        labels = re.findall(r"\[S\d+\]", prompt)
        unique_labels = list(dict.fromkeys(labels))
        label_text = " ".join(unique_labels) or "[S1]"
        if "章节摘要：" in prompt:
            return (
                "课程复习摘要\n\n"
                "## 总体脉络\n"
                f"- 本课程围绕样例资料中的核心概念展开，保留证据标签 {label_text}。\n\n"
                "## 分章节重点\n"
                f"- 按来源回看材料并核对边界。{label_text}\n\n"
                "## 易混点与复习提醒\n"
                "- 资料片段不足时不扩展到课外结论。\n\n"
                "## 下一步学习建议\n"
                "- 先复述概念，再回到引用片段核对。"
            )
        return (
            "## 章节要点\n"
            f"- 该章节的要点来自当前证据片段。{label_text}\n\n"
            "## 关键概念与关系\n"
            "- 只保留资料中出现的概念关系。\n\n"
            "## 复习提醒\n"
            f"- 回看对应证据标签 {label_text}。"
        )


def _summary_eval_case(case_id: str, course_id: str, payload: Mapping[str, Any], quality: Dict[str, Any]) -> Dict:
    return {
        "id": case_id,
        "course_id": course_id,
        "passed": quality["passed"],
        "checks": quality["checks"],
        "failed_checks": quality["failed_checks"],
        "metrics": quality["metrics"],
        "summary_method": payload.get("summary_method"),
        "llm_status": payload.get("llm_status"),
        "fallback_reason": payload.get("fallback_reason", ""),
    }


def _course_name(course_id: str) -> str:
    names = {
        DEMO_OS_COURSE_ID: "操作系统",
        DEMO_DATA_STRUCTURE_COURSE_ID: "数据结构",
    }
    return names.get(course_id, course_id)
