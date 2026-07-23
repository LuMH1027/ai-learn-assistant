from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from local_course_agent.llm.images import image_to_data_url


class LLMRequestError(RuntimeError):
    """Raised when a configured LLM request fails after retries."""


class OpenAICompatibleClient:
    max_retries = 5

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        retry_callback: Optional[Callable[[int, int, Exception], None]] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retry_callback = retry_callback

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
        data = self._open_json_with_retries(request, timeout or self.timeout)
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
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            emitted = False
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        data_text = line[5:].strip()
                        if data_text == "[DONE]":
                            return
                        data = json.loads(data_text)
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        content = choices[0].get("delta", {}).get("content")
                        if content:
                            emitted = True
                            yield content
                return
            except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
                last_error = exc
                if emitted:
                    break
                if attempt >= self.max_retries:
                    break
                self._notify_retry(attempt + 1, exc)
        raise LLMRequestError(f"LLM 流式调用失败，已重试 {self.max_retries} 次：{last_error}")

    def _open_json_with_retries(self, request: urllib.request.Request, timeout: int) -> Dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self._notify_retry(attempt + 1, exc)
        raise LLMRequestError(f"LLM 调用失败，已重试 {self.max_retries} 次：{last_error}")

    def _notify_retry(self, next_attempt: int, exc: Exception) -> None:
        if self.retry_callback is None:
            return
        self.retry_callback(next_attempt, self.max_retries, exc)
