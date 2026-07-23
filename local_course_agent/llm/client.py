from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from local_course_agent.llm.images import image_to_data_url


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def generate(self, prompt: str, max_tokens: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        if not self.enabled():
            return None
        return self._chat_completion(self._text_messages(prompt), max_tokens=max_tokens, timeout=timeout)

    def stream(self, prompt: str):
        if not self.enabled():
            return
        yield from self._stream_chat_completion(self._text_messages(prompt))

    def generate_with_images(self, prompt: str, image_paths: List[Path]) -> Optional[str]:
        if not self.enabled() or not image_paths:
            return None
        content = self._image_content(prompt, image_paths)
        if len(content) == 1:
            return None
        return self._chat_completion(self._image_messages(content))

    def stream_with_images(self, prompt: str, image_paths: List[Path]):
        if not self.enabled() or not image_paths:
            return
        content = self._image_content(prompt, image_paths)
        if len(content) == 1:
            return
        yield from self._stream_chat_completion(self._image_messages(content))

    def _text_messages(self, prompt: str) -> List[Dict]:
        return [
            {"role": "system", "content": "你是课程资料优先的学习助手；资料未覆盖时可明确标注后使用通用知识补充。"},
            {"role": "user", "content": prompt},
        ]

    def _image_content(self, prompt: str, image_paths: List[Path]) -> List[Dict]:
        content = [{"type": "text", "text": prompt}]
        for path in image_paths[:4]:
            data_url = image_to_data_url(Path(path))
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
        return content

    def _image_messages(self, content: List[Dict]) -> List[Dict]:
        return [
            {"role": "system", "content": "你是一个课程截图学习助手。优先解释截图中的内容；看不清时明确说明。"},
            {"role": "user", "content": content},
        ]

    def _chat_completion(
        self,
        messages: List[Dict],
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        request_payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        if max_tokens is not None:
            request_payload["max_tokens"] = max_tokens
        payload = json.dumps(request_payload).encode("utf-8")
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
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
            return None
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None

    def _stream_chat_completion(self, messages: List[Dict]):
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": 0.2, "stream": True}
        ).encode("utf-8")
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
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    data = json.loads(data_text)
                    content = data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield content
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
            return
