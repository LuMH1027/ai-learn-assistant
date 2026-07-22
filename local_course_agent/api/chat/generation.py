from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from local_course_agent.llm.config import create_llm_client
from local_course_agent.llm.prompts import build_grounded_prompt


CLARIFICATION_ANSWER = "你的问题信息不足，请补充完整题目、知识点名称，或说明输入的编号对应哪一道题。为避免误导，本次没有联网搜索，也没有调用模型猜测。"


def emit_stream_text(text: str, emit, paced=False, delay=0.016) -> None:
    units = re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\s+|[^\s]", text) if paced else [text]
    for unit in units:
        emit({"type": "delta", "delta": unit})
        if paced and delay:
            time.sleep(delay)


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
            "请确认 `data/config.json` 中配置的是支持视觉输入的 Kimi 模型，或把截图中的文字复制到聊天框。"
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
