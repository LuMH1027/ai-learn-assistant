from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


def build_grounded_prompt(question: str, evidence: List[Dict], memory: str = "") -> str:
    evidence_text = "\n".join(
        f"[{index}] 文件：{item['file_name']}，页码：{item.get('page') or '无'}，片段：{item.get('chunk_index')}\n{item.get('quote', '')}"
        for index, item in enumerate(evidence, start=1)
    )
    memory_text = memory.strip() or "暂无课程记忆。"
    return (
        "你是一个本地课程学习 Agent。只能依据资料片段回答，不能编造资料中没有的内容。\n"
        "如果资料片段不足以回答，要明确说明“当前课程资料不足以确认”。\n"
        "回答要适合学生复习：先给结论，再解释关键点，最后列出引用编号。\n\n"
        f"课程记忆：\n{memory_text}\n\n"
        f"学生问题：\n{question}\n\n"
        f"资料片段：\n{evidence_text}\n"
    )


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def generate(self, prompt: str) -> Optional[str]:
        if not self.enabled():
            return None
        return self._chat_completion(
            [
                {"role": "system", "content": "你是一个严格基于课程资料回答的学习助手。"},
                {"role": "user", "content": prompt},
            ]
        )

    def generate_with_images(self, prompt: str, image_paths: List[Path]) -> Optional[str]:
        if not self.enabled() or not image_paths:
            return None
        content = [{"type": "text", "text": prompt}]
        for path in image_paths[:4]:
            data_url = image_to_data_url(Path(path))
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
        if len(content) == 1:
            return None
        return self._chat_completion(
            [
                {"role": "system", "content": "你是一个课程截图学习助手。优先解释截图中的内容；看不清时明确说明。"},
                {"role": "user", "content": content},
            ]
        )

    def _chat_completion(self, messages: List[Dict]) -> Optional[str]:
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
            return None
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None


def create_llm_client(ai_config: Dict):
    return OpenAICompatibleClient(
        base_url=(ai_config or {}).get("base_url", ""),
        api_key=(ai_config or {}).get("api_key", ""),
        model=(ai_config or {}).get("model", ""),
    )


def image_to_data_url(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            return None
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError:
        return None
