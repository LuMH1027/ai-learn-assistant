from __future__ import annotations

import re
from typing import Dict, List

from local_course_agent.retrieval.rag import CourseKnowledgeBase


class StrategyKnowledgeBase:
    def __init__(self, knowledge_base: CourseKnowledgeBase, strategy: str):
        self.knowledge_base = knowledge_base
        self.strategy = strategy

    def answer(self, course_id: str, query: str) -> Dict:
        return self.knowledge_base.answer(course_id, query, strategy=self.strategy)


class EvalChatStore:
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


class EvalSummaryClient:
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
