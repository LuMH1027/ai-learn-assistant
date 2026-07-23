from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudyModePolicy:
    key: str
    label: str
    planning_rules: str
    response_rules: str


ANSWER_POLICY = StudyModePolicy(
    key="answer",
    label="答疑",
    planning_rules=(
        "目标：准确、直接地消除学生当前疑问。\n"
        "- 闲聊、简单通用问题可以直接回答。\n"
        "- 涉及当前课程概念、题目、附件、原文引用时，优先检索课程资料。\n"
        "- 只有用户明确要求最新信息、官网、论文或外部对比时才联网。"
    ),
    response_rules=(
        "- 先给结论，再解释原因。\n"
        "- 根据问题复杂度补充定义、推导、例子或易错点。\n"
        "- 可以直接给出完整答案，但不得省略关键依据。\n"
        "- 简单问题控制在 1-3 句话，复杂课程问题再分层展开。"
    ),
)

GUIDE_POLICY = StudyModePolicy(
    key="guide",
    label="启发提示",
    planning_rules=(
        "目标：帮助学生自己完成推理，而不是第一轮直接代答。\n"
        "- 题目、作业和课程概念优先检索课程资料，确保提示有依据。\n"
        "- 先结合最近对话判断学生已有尝试、当前卡点和已获得的提示层级。\n"
        "- 用户没有展示尝试时，从一级提示开始。\n"
        "- 用户明确要求完整答案，或历史中已有至少两次有效尝试但仍卡住时，才允许完整讲解。"
    ),
    response_rules=(
        "- 一级提示：指出思考方向或需要回忆的概念。\n"
        "- 二级提示：给出关键条件、公式、资料关键词或中间步骤。\n"
        "- 三级提示：给出接近解法的步骤，但仍留出最后推导。\n"
        "- 默认结构为“思考方向 / 关键线索 / 你可以继续尝试”。\n"
        "- 不用“我不能告诉你答案”阻断交流；达到披露条件后给出完整解法，并解释关键转折。"
    ),
)

REVIEW_POLICY = StudyModePolicy(
    key="review",
    label="复习",
    planning_rules=(
        "目标：帮助学生建立知识结构并进行主动回忆。\n"
        "- 涉及课程主题、章节或综合复习时优先检索课程资料。\n"
        "- 范围过大时先聚焦主题，信息不足才请求澄清。\n"
        "- 不为展示能力而联网；只有用户明确需要外部更新时才联网。"
    ),
    response_rules=(
        "- 优先组织为“核心脉络 / 关键概念 / 易混点 / 自测题”。\n"
        "- 窄问题保持简短，不机械输出完整模板。\n"
        "- 自测题默认不给答案；用户作答后再反馈。\n"
        "- 结尾给出一个可执行的下一步复习动作。"
    ),
)

STUDY_MODE_POLICIES = {
    ANSWER_POLICY.key: ANSWER_POLICY,
    GUIDE_POLICY.key: GUIDE_POLICY,
    REVIEW_POLICY.key: REVIEW_POLICY,
}

STUDY_MODE_ALIASES = {
    "socratic": "guide",
    "homework": "guide",
}


def normalize_study_mode(value) -> str:
    raw = str(value or "answer").strip().lower()
    key = STUDY_MODE_ALIASES.get(raw, raw)
    return key if key in STUDY_MODE_POLICIES else "answer"


def get_study_mode_policy(value) -> StudyModePolicy:
    return STUDY_MODE_POLICIES[normalize_study_mode(value)]
