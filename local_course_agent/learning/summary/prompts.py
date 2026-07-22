from __future__ import annotations

from typing import Sequence

from local_course_agent.learning.summary.models import EvidenceGroup, MapSummary, SummaryEvidence


def build_map_prompt(course_name: str, group: EvidenceGroup) -> str:
    evidence_text = "\n\n".join(format_evidence_block(item) for item in group.evidence)
    section = group.section_title or "无"
    return (
        "你是一个严谨的课程章节摘要助手。只基于给定资料片段总结，不要加入资料外知识，"
        "不要虚构原文没有的结论。\n"
        "请输出 Markdown，结构固定为：\n"
        "## 章节要点\n"
        "- 2-4 条要点，每条句末标注来源，如 [S1]。\n\n"
        "## 关键概念与关系\n"
        "- 提炼概念、条件、步骤或关系；证据不足时写“资料片段不足”。\n\n"
        "## 复习提醒\n"
        "- 写 1-2 条本章节复习时应回看原文的位置或边界。\n\n"
        f"课程名称：{course_name or '当前课程'}\n"
        f"文件：{group.file_name}\n"
        f"章节：{section}\n"
        f"资料片段：\n{evidence_text}\n"
    )


def build_reduce_prompt(course_name: str, map_summaries: Sequence[MapSummary]) -> str:
    summaries_text = "\n\n".join(format_map_summary_block(item) for item in map_summaries)
    return (
        "你是一个严谨的课程总摘要助手。请只基于下列章节摘要做归纳，不要加入资料外知识，"
        "不要虚构章节、定义、结论或引用。\n"
        "请输出 Markdown，结构固定为：\n"
        "课程复习摘要\n\n"
        "## 总体脉络\n"
        "- 2-4 条概括章节之间的主题、先后关系或依赖关系。\n\n"
        "## 分章节重点\n"
        "- 按章节列出重点；每条保留来源标签，如 [S1]。\n\n"
        "## 易混点与复习提醒\n"
        "- 提炼跨章节容易混淆的边界；证据不足时明确写“资料片段不足”。\n\n"
        "## 下一步学习建议\n"
        "- 给出 2-3 条可执行复习动作。\n\n"
        f"课程名称：{course_name or '当前课程'}\n"
        f"章节摘要：\n{summaries_text}\n"
    )


def format_evidence_block(item: SummaryEvidence) -> str:
    page = item.page or "无"
    section = item.section_title or "无"
    return (
        f"[{item.label}] 文件：{item.file_name}，章节：{section}，页码：{page}，片段：{item.chunk_index}\n"
        f"{item.text}"
    )


def format_map_summary_block(item: MapSummary) -> str:
    source_labels = ", ".join(f"[{label}]" for label in item.evidence_labels)
    section = item.section_title or "无"
    return (
        f"[{item.group_id}] 文件：{item.file_name}，章节：{section}，来源：{source_labels}\n"
        f"{item.content}"
    )
