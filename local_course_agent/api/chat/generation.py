from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from local_course_agent.llm.config import create_llm_client
from local_course_agent.llm.prompts import build_grounded_prompt


CLARIFICATION_ANSWER = "你的问题信息不足，请补充完整题目、知识点名称，或说明输入的编号对应哪一道题。为避免误导，本次没有联网搜索，也没有调用模型猜测。"
LIGHT_FALLBACK_ANSWER = "我在。"


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
    course_name: str,
    previous_messages: Sequence[Mapping],
    has_attachments: bool,
    observations: Sequence[Mapping],
) -> str:
    recent = []
    for message in previous_messages[-3:]:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip().replace("\n", " ")
        if content:
            recent.append(f"{role}: {content[:160]}")
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
        "必要时调用工具，资料足够时直接 final。不要预先固定要不要工具，也不要为了展示能力而调用工具。\n\n"
        "可用 action：\n"
        "- final：直接给最终回答。适合闲聊、简单问题、或已有 observation 足够时。\n"
        "- course_search：检索当前课程资料。适合讲课程内容、题目、附件、引用或前文课程追问。\n"
        "- web_search：联网补充。只在用户明确要最新、竞品、官网、论文、新闻、当前版本等外部信息时使用。\n"
        "- course_and_web_search：同一问题同时需要课程资料和外部资料时使用。\n"
        "- clarify：问题缺少必要对象，不能可靠定位。\n\n"
        "要求：\n"
        "- 闲聊和普通短问题直接 final，1-3 句话。\n"
        "- 讲课程内容优先 course_search，不默认联网。\n"
        "- 已有课程/网页 observation 时，优先基于 observation final，不要重复调用同一工具。\n"
        "- final 中引用课程结论可写 [L1]、网页结论可写 [W1]；没有 observation 不要伪造引用。\n"
        "- 只输出 JSON，不要输出 Markdown 代码块或额外文字。\n\n"
        "JSON 格式：\n"
        "{"
        "\"action\":\"final\","
        "\"answer\":\"action 为 final/clarify 时填写给用户的文本，否则为空\","
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
        return client.generate(prompt)


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
    if action in {"final", "clarify"} and not answer:
        return None
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
            answer="我已拿到可用资料，但当前模型没有成功生成最终回答。请稍后重试，或换一个更具体的问题。",
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
    if not has_attachments and len(normalized) <= 8:
        return AgentStep(
            action="final",
            answer=LIGHT_FALLBACK_ANSWER,
            reason="模型不可用，本地降级为短答。",
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
    ) -> tuple[str, str]:
        if needs_clarification:
            answer = adapt_answer_by_mode(mode, CLARIFICATION_ANSWER)
            self._emit_delta(answer)
            return answer, "skipped"

        if self.stream_format:
            prefix = answer_mode_prefix(mode)
            if prefix:
                self._emit_delta(prefix)
            generated, llm_status = self.synthesize_stream(
                search_question,
                combined_result,
                emit_delta=self._emit_delta,
                image_paths=image_paths,
                ai_config=ai_config,
            )
            return prefix + generated, llm_status

        answer, llm_status = self.synthesize(
            search_question,
            combined_result,
            image_paths=image_paths,
            ai_config=ai_config,
        )
        return adapt_answer_by_mode(mode, answer), llm_status

    def _emit_delta(self, delta: str) -> None:
        emit_stream_text(delta, self.emit, paced=self.stream_format == "ndjson")


def synthesize_answer(
    question: str,
    result: dict,
    image_paths=None,
    ai_config=None,
    llm_client_factory=create_llm_client,
):
    image_paths = image_paths or []
    client = llm_client_factory(ai_config or {})
    llm_configured = client.enabled()
    if image_paths:
        image_prompt = image_grounded_prompt(question, result)
        generated = client.generate_with_images(image_prompt, image_paths)
        if generated:
            return generated, "used"
        fallback = result["answer"]
        return (
            f"{fallback}\n\n"
            "已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认 `data/config.json` 中配置的是支持视觉输入的模型，或把截图中的文字复制到聊天框。"
        ), "fallback" if llm_configured else "disabled"
    prompt = build_grounded_prompt(question, result["citations"], memory="")
    generated = client.generate(prompt)
    if generated:
        return generated, "used"
    return result["answer"], "fallback" if llm_configured else "disabled"


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
    llm_client_factory=create_llm_client,
):
    image_paths = image_paths or []
    client = llm_client_factory(ai_config or {})
    llm_configured = client.enabled()
    prompt = build_grounded_prompt(question, result["citations"], memory="")
    if image_paths:
        image_prompt = image_grounded_prompt(question, result)
        chunks = client.stream_with_images(image_prompt, image_paths)
        fallback_generate = lambda: client.generate_with_images(image_prompt, image_paths)
    else:
        chunks = client.stream(prompt)
        fallback_generate = lambda: client.generate(prompt)

    generated_parts = []
    for chunk in chunks or []:
        generated_parts.append(chunk)
        emit_delta(chunk)
    if generated_parts:
        return "".join(generated_parts), "used"

    generated = fallback_generate()
    if generated:
        emit_delta(generated)
        return generated, "used"
    fallback = result["answer"]
    if image_paths:
        fallback += (
            "\n\n已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认模型支持视觉输入，或把截图中的文字复制到聊天框。"
        )
    emit_delta(fallback)
    return fallback, "fallback" if llm_configured else "disabled"


def image_grounded_prompt(question: str, result: dict) -> str:
    return (
        "学生上传了课程截图或图片。请先理解图片内容，再结合课程资料回答。\n"
        "如果图片中文字看不清，直接说明看不清，不要编造。\n\n"
        f"学生问题：\n{question}\n\n"
        f"课程检索结果：\n{result.get('answer', '')}"
    )


def adapt_answer_by_mode(mode: str, answer: str) -> str:
    return answer_mode_prefix(mode) + answer


def answer_mode_prefix(mode: str) -> str:
    prefixes = {
        "socratic": "启发式提示：先不要急着看完整答案，可以根据资料中的关键词自己复述一遍。\n\n",
        "homework": "作业提示模式：以下只给思路和资料依据，不直接替你完成作业。\n\n",
        "review": "复习模式：建议把下面内容整理成概念、易错点和自测题。\n\n",
    }
    return prefixes.get(mode, "")
