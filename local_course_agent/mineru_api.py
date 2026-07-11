from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


BASE_URL = "https://mineru.net/api/v1/agent"


class MineruAgentClient:
    def __init__(self, token: str = "", timeout: int = 120, interval: int = 3):
        self.token = (token or "").strip()
        self.timeout = timeout
        self.interval = interval

    def parse_file(self, path: Path, language: str = "ch") -> Optional[str]:
        path = Path(path)
        if path.stat().st_size > 10 * 1024 * 1024:
            return None
        task = self._create_file_task(path.name, language)
        if not task:
            return None
        if not self._upload_file(task["file_url"], path):
            return None
        markdown_url = self._poll_markdown_url(task["task_id"])
        if not markdown_url:
            return None
        return self._download_text(markdown_url)

    def _create_file_task(self, file_name: str, language: str):
        payload = json.dumps(
            {
                "file_name": file_name,
                "language": language,
                "enable_table": True,
                "is_ocr": False,
                "enable_formula": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{BASE_URL}/parse/file",
            data=payload,
            headers=self._headers({"Content-Type": "application/json"}),
            method="POST",
        )
        data = self._json_request(request)
        if not data or data.get("code") != 0:
            return None
        task_data = data.get("data", {})
        if not task_data.get("task_id") or not task_data.get("file_url"):
            return None
        return task_data

    def _upload_file(self, file_url: str, path: Path) -> bool:
        request = urllib.request.Request(file_url, data=path.read_bytes(), method="PUT")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status in (200, 201)
        except (OSError, urllib.error.URLError):
            return False

    def _poll_markdown_url(self, task_id: str) -> Optional[str]:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            request = urllib.request.Request(f"{BASE_URL}/parse/{task_id}", headers=self._headers(), method="GET")
            data = self._json_request(request)
            task_data = (data or {}).get("data", {})
            state = task_data.get("state")
            if state == "done":
                return task_data.get("markdown_url")
            if state == "failed":
                return None
            time.sleep(self.interval)
        return None

    def _download_text(self, url: str) -> Optional[str]:
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore")
        except (OSError, urllib.error.URLError):
            return None

    def _json_request(self, request):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return None

    def _headers(self, headers=None):
        merged = dict(headers or {})
        if self.token:
            merged["Authorization"] = f"Bearer {self.token}"
        return merged
