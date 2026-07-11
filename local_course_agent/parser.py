from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from local_course_agent.mineru_api import MineruAgentClient


def extract_text(path: Path, mineru_config=None) -> List[Dict]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        mineru_api_pages = _extract_with_mineru_api(path, mineru_config or {})
        if mineru_api_pages:
            return mineru_api_pages
        mineru_pages = _extract_with_mineru(path, discover_mineru_command(mineru_config or {}))
        if mineru_pages:
            return mineru_pages
        return _extract_pdf(path)
    if suffix in {".md", ".markdown", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [{"page": None, "text": text}]
    if suffix == ".docx":
        return [{"page": None, "text": f"DOCX 文件已发现：{path.name}。当前轻量版未安装 DOCX 解析依赖，请导出为 PDF 或 TXT 后入库。"}]
    return []


def _extract_with_mineru_api(path: Path, mineru_config) -> List[Dict]:
    if not (mineru_config or {}).get("api_enabled", True):
        return []
    try:
        text = MineruAgentClient(token=(mineru_config or {}).get("token", "")).parse_file(
            path,
            language=(mineru_config or {}).get("language", "ch"),
        )
    except Exception:
        return []
    if not text:
        return []
    return [{"page": None, "text": text}]


def discover_mineru_command(mineru_config) -> str:
    if isinstance(mineru_config, str):
        return mineru_config.strip()
    command = (mineru_config or {}).get("command", "").strip()
    if command:
        return command
    if not (mineru_config or {}).get("auto", True):
        return ""
    for binary, template in (
        ("mineru", 'mineru -p "{input}"'),
        ("magic-pdf", 'magic-pdf -p "{input}"'),
    ):
        if shutil.which(binary):
            return template
    return ""


def _extract_with_mineru(path: Path, mineru_command: str) -> List[Dict]:
    command = (mineru_command or "").strip()
    if not command:
        return []
    try:
        completed = subprocess.run(
            command.format(input=str(path)),
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:
        return []
    text = (completed.stdout or "").strip()
    if completed.returncode != 0 or not text:
        return []
    return [{"page": None, "text": text}]


def _extract_pdf(path: Path) -> List[Dict]:
    try:
        from pypdf import PdfReader
    except Exception:
        return [{"page": None, "text": f"PDF 文件已发现：{path.name}。当前环境缺少 pypdf，无法抽取文本。"}]

    pages = []
    try:
        reader = PdfReader(str(path))
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({"page": index, "text": text})
    except Exception as exc:
        pages.append({"page": None, "text": f"PDF 解析失败：{path.name}，原因：{exc}"})
    return pages
