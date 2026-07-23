from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from local_course_agent.llm.client import LLMRequestError
from local_course_agent.llm.config import create_llm_client
from local_course_agent.llm.prompts import build_grounded_prompt

from .modes import get_study_mode_policy, normalize_study_mode


CLARIFICATION_ANSWER = "你的问题信息不足，请补充完整题目、知识点名称，或说明输入的编号对应哪一道题。为避免误导，本次没有联网搜索，也没有调用模型猜测。"
MODEL_UNAVAILABLE_ANSWER = "当前大模型不可用，无法生成回答。请检查模型配置、网络或稍后重试。"
LIGHT_FALLBACK_ANSWER = MODEL_UNAVAILABLE_ANSWER
LIGHT_CHAT_PATTERNS = (
    r"^(你|您)?好[啊呀]?[。!！?？]*$",
    r"^(hi|hello|hey)[。!！?？]*$",
    r"^在吗[。!！?？]*$",
)


@dataclass(frozen=True)
class AgentStep:
    action: str = "final"
    answer: str = ""
    query: str = ""
    reason: str = ""
    llm_status: str = "disabled"


AGENT_ACTIONS = {"final", "course_search", "web_search", "course_and_web_search", "clarify"}


def emit_stream_text(text: str, emit, paced=False, delay=0.016) -> None:
    units = re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\s+|[^\s]", text) if paced else [text]
    for unit in units:
        emit({"type": "delta", "delta": unit})
        if paced and delay:
            time.sleep(delay)


def plan_agent_step(
    question: str,
    *,
    mode: str = "answer",
    course_name: str = "",
    previous_messages: Sequence[Mapping] | None = None,
    has_attachments: bool = False,
    observations: Sequence[Mapping] | None = None,
    ai_config=None,
    llm_client_factory=create_llm_client,
) -> AgentStep:
    client = llm_client_factory(ai_config or {})
    prompt = build_react_prompt(
        question,
        mode,
        course_name,
        previous_messages or [],
        has_attachments,
        observations or [],
    )
    generated = generate_agent_step(client, prompt)
    parsed = parse_agent_step(generated or "")
    if parsed:
        return AgentStep(**parsed, llm_status="used")
    return fallback_agent_step(
        question,
        has_attachments=has_attachments,
        has_previous_messages=bool(previous_messages),
        has_observations=bool(observations),
        llm_enabled=client.enabled(),
    )


def build_react_prompt(
    question: str,
    mode: str,
    course_name: str,
    previous_messages: Sequence[Mapping],
    has_attachments: bool,
    observations: Sequence[Mapping],
) -> str:
    policy = get_study_mode_policy(mode)
    recent = []
    for message in previous_messages[-6:]:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip().replace("\n", " ")
        if content:
            recent.append(f"{role}: {content[:260]}")
    history = "\n".join(recent) or "无"
    attachment_hint = "有，附件内容会进入课程检索上下文。" if has_attachments else "无"
    observation_lines = []
    for item in observations[-4:]:
        observation_lines.append(
            f"{item.get('action', 'tool')}：{str(item.get('summary', ''))[:900]}"
        )
    observation_text = "\n\n".join(observation_lines) or "无"
    return (
        "你是本地课程学习 Agent，按 ReAct 工作：先根据问题和已有 observation 决定下一步 action，"
        "必要时调用工具，资料足够时返回 final 交给最终作答器。不要预先固定要不要工具，也不要为了展示能力而调用工具。\n\n"
        "可用 action：\n"
        "- final：资料足够或无需工具，进入最终作答。适合闲聊、简单问题、或已有 observation 足够时。\n"
        "- course_search：检索当前课程资料。适合讲课程内容、题目、附件、引用或前文课程追问。\n"
        "- web_search：联网补充。只在用户明确要最新、竞品、官网、论文、新闻、当前版本等外部信息时使用。\n"
        "- course_and_web_search：同一问题同时需要课程资料和外部资料时使用。\n"
        "- clarify：问题缺少必要对象，不能可靠定位。\n\n"
        f"当前学习模式：{policy.label}（{policy.key}）\n"
        "模式规划规则：\n"
        f"{policy.planning_rules}\n\n"
        "要求：\n"
        "- 闲聊和普通短问题直接 final，1-3 句话。\n"
        "- 讲课程内容优先 course_search，不默认联网。\n"
        "- 已有课程/网页 observation 时，优先基于 observation final，不要重复调用同一工具。\n"
        "- final 只表示可以作答，不要在 planner 里写最终答案。\n"
        "- clarify 可以直接写需要向学生追问的澄清问题。\n"
        "- 只输出 JSON，不要输出 Markdown 代码块或额外文字。\n\n"
        "JSON 格式：\n"
        "{"
        "\"action\":\"final\","
        "\"answer\":\"action 为 clarify 时填写澄清问题；final 和搜索 action 置空\","
        "\"query\":\"调用搜索工具时填写搜索问题，否则为空\","
        "\"reason\":\"一句话说明判断，40字以内\""
        "}\n\n"
        f"当前课程：{course_name or '未命名课程'}\n"
        f"是否有附件：{attachment_hint}\n"
        f"最近对话：\n{history}\n\n"
        f"已有 observation：\n{observation_text}\n\n"
        f"用户问题：\n{question}"
    )


def generate_agent_step(client, prompt: str) -> str | None:
    try:
        return client.generate(prompt, max_tokens=900, timeout=45)
    except TypeError:
        try:
            return client.generate(prompt)
        except LLMRequestError:
            return None
    except LLMRequestError:
        return None


def light_chat_answer(question: str) -> str:
    normalized = question.strip().lower()
    if any(re.fullmatch(pattern, normalized) for pattern in LIGHT_CHAT_PATTERNS):
        return LIGHT_FALLBACK_ANSWER
    return ""


def parse_agent_step(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    action = str(payload.get("action") or "").strip().lower()
    if action not in AGENT_ACTIONS:
        return None
    answer = str(payload.get("answer") or "").strip()
    query = str(payload.get("query") or "").strip()
    reason = str(payload.get("reason") or "").strip()[:240]
    if action == "clarify" and not answer:
        return None
    if action == "final":
        answer = ""
    if action in {"course_search", "web_search", "course_and_web_search"} and not query:
        query = ""
    return {
        "action": action,
        "answer": answer,
        "query": query,
        "reason": reason,
    }


def fallback_agent_step(
    question: str,
    *,
    has_attachments: bool,
    has_previous_messages: bool = False,
    has_observations: bool = False,
    llm_enabled: bool,
) -> AgentStep:
    normalized = question.strip()
    if has_observations:
        return AgentStep(
            action="final",
            answer="",
            reason="模型不可用，已有 observation 但无法生成。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    if re.fullmatch(r"[\d一二三四五六七八九十]+[\.。]?", normalized):
        return AgentStep(
            action="clarify",
            answer=CLARIFICATION_ANSWER,
            reason="模型不可用，纯编号问题缺少可定位的题目。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    if has_previous_messages:
        return AgentStep(
            action="course_search",
            query=question,
            reason="模型不可用，追问场景本地降级为课程检索。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    if not has_attachments and light_chat_answer(normalized):
        return AgentStep(
            action="final",
            answer="",
            reason="模型不可用，问候类问题仍交给最终回答器。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    return AgentStep(
        action="course_search",
        query=question,
        reason="模型不可用，本地降级为课程检索。",
        llm_status="fallback" if llm_enabled else "disabled",
    )


class ChatAnswerGenerator:
    def __init__(
        self,
        *,
        emit: Callable[[dict], None],
        stream_format: str | None = None,
        synthesize=None,
        synthesize_stream=None,
    ):
        self.emit = emit
        self.stream_format = stream_format
        self.synthesize = synthesize or synthesize_answer
        self.synthesize_stream = synthesize_stream or synthesize_answer_stream

    def generate(
        self,
        *,
        mode: str,
        needs_clarification: bool,
        search_question: str,
        combined_result: dict,
        image_paths: list[Path],
        ai_config: dict,
        previous_messages: Sequence[Mapping] | None = None,
        direct_answer: str = "",
    ) -> tuple[str, str]:
        mode = normalize_study_mode(mode)
        if direct_answer.strip():
            answer = direct_answer.strip()
            self._emit_delta(answer)
            return answer, "skipped"

        if needs_clarification:
            answer = combined_result.get("answer") or CLARIFICATION_ANSWER
            self._emit_delta(answer)
            return answer, "skipped"

        if self.stream_format:
            generated, llm_status = self._call_synthesize_stream(
                search_question,
                combined_result,
                emit_delta=self._emit_delta,
                image_paths=image_paths,
                ai_config=ai_config,
                mode=mode,
                previous_messages=previous_messages or [],
            )
            return generated, llm_status

        answer, llm_status = self._call_synthesize(
            search_question,
            combined_result,
            image_paths=image_paths,
            ai_config=ai_config,
            mode=mode,
            previous_messages=previous_messages or [],
        )
        return answer, llm_status

    def _emit_delta(self, delta: str) -> None:
        emit_stream_text(delta, self.emit, paced=self.stream_format == "ndjson")

    def _call_synthesize(self, question: str, result: dict, **kwargs):
        try:
            return self.synthesize(question, result, **kwargs)
        except TypeError:
            legacy_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in {"image_paths", "ai_config"}
            }
            return self.synthesize(question, result, **legacy_kwargs)

    def _call_synthesize_stream(self, question: str, result: dict, **kwargs):
        try:
            return self.synthesize_stream(question, result, **kwargs)
        except TypeError:
            legacy_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in {"emit_delta", "image_paths", "ai_config"}
            }
            return self.synthesize_stream(question, result, **legacy_kwargs)


def synthesize_answer(
    question: str,
    result: dict,
    image_paths=None,
    ai_config=None,
    mode: str = "answer",
    previous_messages: Sequence[Mapping] | None = None,
    llm_client_factory=create_llm_client,
):
    image_paths = image_paths or []
    client = llm_client_factory(ai_config or {})
    llm_configured = client.enabled()
    if image_paths:
        image_prompt = image_grounded_prompt(question, result, mode=mode, previous_messages=previous_messages or [])
        try:
            generated = client.generate_with_images(image_prompt, image_paths)
        except LLMRequestError:
            generated = None
        if generated:
            return generated, "used"
        fallback = mode_fallback_answer(mode, result, question, previous_messages or [])
        return (
            f"{fallback}\n\n"
            "已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认 `data/config.json` 中配置的是支持视觉输入的模型，或把截图中的文字复制到聊天框。"
        ), "fallback" if llm_configured else "disabled"
    prompt = build_responder_prompt(question, result, mode=mode, previous_messages=previous_messages or [])
    try:
        generated = client.generate(prompt)
    except LLMRequestError:
        generated = None
    if generated:
        return generated, "used"
    return mode_fallback_answer(mode, result, question, previous_messages or []), "fallback" if llm_configured else "disabled"


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
    mode: str = "answer",
    previous_messages: Sequence[Mapping] | None = None,
    llm_client_factory=create_llm_client,
):
    image_paths = image_paths or []
    previous_messages = previous_messages or []
    client = llm_client_factory(ai_config or {})
    llm_configured = client.enabled()
    prompt = build_responder_prompt(question, result, mode=mode, previous_messages=previous_messages)
    stream_error = False
    if image_paths:
        image_prompt = image_grounded_prompt(question, result, mode=mode, previous_messages=previous_messages)
        try:
            chunks = client.stream_with_images(image_prompt, image_paths)
        except LLMRequestError:
            chunks = []
            stream_error = True
        fallback_generate = lambda: client.generate_with_images(image_prompt, image_paths)
    else:
        try:
            chunks = client.stream(prompt)
        except LLMRequestError:
            chunks = []
            stream_error = True
        fallback_generate = lambda: client.generate(prompt)

    generated_parts = []
    try:
        for chunk in chunks or []:
            generated_parts.append(chunk)
            emit_delta(chunk)
    except LLMRequestError:
        stream_error = True
        if generated_parts:
            return "".join(generated_parts), "used"
    if generated_parts:
        return "".join(generated_parts), "used"

    try:
        generated = None if stream_error else fallback_generate()
    except LLMRequestError:
        generated = None
    if generated:
        emit_delta(generated)
        return generated, "used"
    fallback = mode_fallback_answer(mode, result, question, previous_messages)
    if image_paths:
        fallback += (
            "\n\n已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认模型支持视觉输入，或把截图中的文字复制到聊天框。"
        )
    emit_delta(fallback)
    return fallback, "fallback" if llm_configured else "disabled"


def build_responder_prompt(
    question: str,
    result: dict,
    *,
    mode: str = "answer",
    previous_messages: Sequence[Mapping] | None = None,
) -> str:
    policy = get_study_mode_policy(mode)
    return build_grounded_prompt(
        question,
        result.get("citations", []),
        memory="",
        mode_label=f"{policy.label}（{policy.key}）",
        response_policy=policy.response_rules,
        conversation_history=format_recent_history(previous_messages or []),
    )


def image_grounded_prompt(
    question: str,
    result: dict,
    *,
    mode: str = "answer",
    previous_messages: Sequence[Mapping] | None = None,
) -> str:
    policy = get_study_mode_policy(mode)
    return (
        "学生上传了课程截图或图片。请先理解图片内容，再结合课程资料回答。\n"
        "如果图片中文字看不清，直接说明看不清，不要编造。\n\n"
        f"当前学习模式：{policy.label}（{policy.key}）\n"
        f"模式作答规则：\n{policy.response_rules}\n\n"
        f"最近学习对话：\n{format_recent_history(previous_messages or [])}\n\n"
        f"学生问题：\n{question}\n\n"
        f"课程检索结果：\n{result.get('answer', '')}"
    )


def adapt_answer_by_mode(mode: str, answer: str) -> str:
    return answer


def answer_mode_prefix(mode: str) -> str:
    return ""


def format_recent_history(messages: Sequence[Mapping]) -> str:
    recent = []
    for message in messages[-6:]:
        role = str(message.get("role", "")).strip() or "message"
        content = str(message.get("content", "")).strip().replace("\n", " ")
        if content:
            recent.append(f"{role}: {content[:320]}")
    return "\n".join(recent) or "无"


def mode_fallback_answer(
    mode: str,
    result: dict,
    question: str,
    previous_messages: Sequence[Mapping] | None = None,
) -> str:
    mode = normalize_study_mode(mode)
    base = str(result.get("answer") or "").strip()
    citations = result.get("citations") or []
    if mode == "guide" and not guide_disclosure_allowed(question, previous_messages or []):
        source_names = []
        for citation in citations[:3]:
            name = str(citation.get("file_name") or "课程资料").strip()
            if name and name not in source_names:
                source_names.append(name)
        source_hint = "、".join(source_names) if source_names else "课程资料"
        return (
            "思考方向\n"
            f"先回到{source_hint}，找出题目里真正要用的定义、条件或公式。\n\n"
            "关键线索\n"
            f"- 把问题中的关键词拆出来：{question[:80]}\n"
            "- 先写出已知条件，再判断它们分别对应哪个课程概念。\n\n"
            "你可以继续尝试\n"
            "先给出你的第一步推理或卡住的位置，我再给下一层提示。"
        )
    if mode == "review":
        content = base or "当前没有检索到足够课程资料，以下只能作为通用复习框架。"
        return (
            "核心脉络\n"
            f"{content}\n\n"
            "易混点\n"
            "- 回到课程原文核对定义边界、适用条件和例外情况。\n\n"
            "自测题\n"
            "- 不看资料，用自己的话概括这个知识点解决什么问题。\n\n"
            "下一步\n"
            "用 3 分钟写出一版概念图，再对照资料补缺。"
        )
    return base or MODEL_UNAVAILABLE_ANSWER


def guide_disclosure_allowed(question: str, previous_messages: Sequence[Mapping]) -> bool:
    explicit_patterns = (
        r"直接.*答案",
        r"完整.*(答案|解法|讲解)",
        r"(告诉|给).*答案",
        r"不要提示",
    )
    if any(re.search(pattern, question) for pattern in explicit_patterns):
        return True
    attempt_markers = ("我觉得", "我认为", "我算", "我试", "推导", "因为", "所以", "得到", "答案是", "卡在")
    attempts = 0
    for message in previous_messages:
        if str(message.get("role", "")).lower() != "user":
            continue
        content = str(message.get("content") or "")
        if len(content.strip()) >= 12 and any(marker in content for marker in attempt_markers):
            attempts += 1
    return attempts >= 2
