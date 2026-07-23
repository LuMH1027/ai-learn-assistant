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
class ToolDecision:
    direct_answer: str = ""
    use_course_materials: bool = False
    use_web_search: bool = False
    needs_clarification: bool = False
    reason: str = ""
    llm_status: str = "disabled"


def emit_stream_text(text: str, emit, paced=False, delay=0.016) -> None:
    units = re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\s+|[^\s]", text) if paced else [text]
    for unit in units:
        emit({"type": "delta", "delta": unit})
        if paced and delay:
            time.sleep(delay)


def decide_tool_use(
    question: str,
    *,
    course_name: str = "",
    previous_messages: Sequence[Mapping] | None = None,
    has_attachments: bool = False,
    ai_config=None,
    llm_client_factory=create_llm_client,
) -> ToolDecision:
    client = llm_client_factory(ai_config or {})
    prompt = build_tool_decision_prompt(question, course_name, previous_messages or [], has_attachments)
    generated = generate_tool_decision(client, prompt)
    parsed = parse_tool_decision(generated or "")
    if parsed:
        return ToolDecision(**parsed, llm_status="used")
    return fallback_tool_decision(
        question,
        has_attachments=has_attachments,
        has_previous_messages=bool(previous_messages),
        llm_enabled=client.enabled(),
    )


def build_tool_decision_prompt(
    question: str,
    course_name: str,
    previous_messages: Sequence[Mapping],
    has_attachments: bool,
) -> str:
    recent = []
    for message in previous_messages[-3:]:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip().replace("\n", " ")
        if content:
            recent.append(f"{role}: {content[:160]}")
    history = "\n".join(recent) or "无"
    attachment_hint = "有，附件内容会进入课程检索上下文。" if has_attachments else "无"
    return (
        "你是本地课程学习助手的工具调度与回答模型。请在同一次判断中决定是否需要工具；"
        "不要因为系统有工具就默认调用工具，也不要为了展示能力而搜索。\n\n"
        "可用能力：\n"
        "1. direct_answer：不调用任何工具，直接用模型常识或简短闲聊回答。适合你好、确认、改写、普通概念、无需课程依据的问题。\n"
        "2. course_search：检索当前课程资料。适合用户要求讲课程内容、问当前资料里的概念/题目/引用/附件，或需要结合前文课程上下文。\n"
        "3. web_search：联网补充。只在用户明确要求最新信息、外部资料、竞品、官网、论文、新闻、当前版本，"
        "或课程资料明显不可能覆盖的现实信息时使用；不要把网页搜索当成默认步骤。\n"
        "4. clarify：问题缺少必要对象，例如只有编号、代词但前文无法指代清楚、题目不完整。此时直接请用户补充，不要猜。\n\n"
        "判断原则：\n"
        "- 闲聊和简单确认应 direct_answer，回答要短。\n"
        "- 讲解课程内容时可以 course_search，但不需要 web_search；讲解可以慢一点、有层次。\n"
        "- 如果问题可用通用知识回答且用户没有要求课程依据，可以 direct_answer。\n"
        "- 如果同时需要课程与外部材料，可以同时请求 course_search 和 web_search。\n"
        "- 你只输出 JSON，不要输出 Markdown 或额外文字。\n\n"
        "JSON 格式：\n"
        "{"
        "\"direct_answer\":\"如果不需要工具，在这里给最终回答；需要工具则为空\","
        "\"use_course_materials\":false,"
        "\"use_web_search\":false,"
        "\"needs_clarification\":false,"
        "\"reason\":\"一句话说明判断，40字以内\""
        "}\n\n"
        f"当前课程：{course_name or '未命名课程'}\n"
        f"是否有附件：{attachment_hint}\n"
        f"最近对话：\n{history}\n\n"
        f"用户问题：\n{question}"
    )


def generate_tool_decision(client, prompt: str) -> str | None:
    try:
        return client.generate(prompt, max_tokens=220, timeout=12)
    except TypeError:
        return client.generate(prompt)


def parse_tool_decision(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    direct_answer = str(payload.get("direct_answer") or "").strip()
    use_course = bool(payload.get("use_course_materials"))
    use_web = bool(payload.get("use_web_search"))
    needs_clarification = bool(payload.get("needs_clarification"))
    reason = str(payload.get("reason") or "").strip()[:240]
    if needs_clarification:
        return {
            "direct_answer": "",
            "use_course_materials": False,
            "use_web_search": False,
            "needs_clarification": True,
            "reason": reason,
        }
    if direct_answer:
        return {
            "direct_answer": direct_answer,
            "use_course_materials": False,
            "use_web_search": False,
            "needs_clarification": False,
            "reason": reason,
        }
    return {
        "direct_answer": "",
        "use_course_materials": use_course,
        "use_web_search": use_web,
        "needs_clarification": False,
        "reason": reason,
    }


def fallback_tool_decision(
    question: str,
    *,
    has_attachments: bool,
    has_previous_messages: bool = False,
    llm_enabled: bool,
) -> ToolDecision:
    normalized = question.strip()
    if re.fullmatch(r"[\d一二三四五六七八九十]+[\.。]?", normalized):
        return ToolDecision(
            needs_clarification=True,
            reason="模型不可用，纯编号问题缺少可定位的题目。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    if has_previous_messages:
        return ToolDecision(
            use_course_materials=True,
            reason="模型不可用，追问场景本地降级为课程检索。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    if not has_attachments and len(normalized) <= 8:
        return ToolDecision(
            direct_answer=LIGHT_FALLBACK_ANSWER,
            reason="模型不可用，本地降级为短答。",
            llm_status="fallback" if llm_enabled else "disabled",
        )
    return ToolDecision(
        use_course_materials=True,
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
