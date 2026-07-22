from __future__ import annotations

import time
import urllib.error
import urllib.request

from local_course_agent.retrieval.embeddings.models import EmbeddingRequestError
from local_course_agent.retrieval.embeddings.utils import http_error_detail, retryable_http_status


class OpenAIEmbeddingHTTPClient:
    """Small urllib-based client for OpenAI-compatible embedding endpoints."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout: float,
        max_retries: int,
        retry_delay: float,
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.retry_delay = float(retry_delay)

    def post_embeddings(self, payload: bytes, *, batch_number: int) -> str:
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                self.endpoint,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                last_error = exc
                if not retryable_http_status(exc.code) or attempt == attempts:
                    detail = http_error_detail(exc)
                    raise EmbeddingRequestError(
                        f"embedding HTTP error for {self.endpoint} "
                        f"(batch {batch_number}, attempt {attempt}/{attempts}): "
                        f"{exc.code} {exc.reason}{detail}"
                    ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == attempts:
                    raise EmbeddingRequestError(
                        f"embedding request failed for {self.endpoint} "
                        f"(batch {batch_number}, attempt {attempt}/{attempts}): {exc.reason}"
                    ) from exc
            if attempt < attempts and self.retry_delay:
                time.sleep(self.retry_delay)
        raise EmbeddingRequestError(f"embedding request failed for {self.endpoint}: {last_error}")
