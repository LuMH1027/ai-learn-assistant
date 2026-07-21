from __future__ import annotations

import shutil
import subprocess
import zipfile
from xml.etree import ElementTree
from pathlib import Path
from typing import Dict, List

from local_course_agent.mineru_api import MineruAgentClient
from local_course_agent.scanner import is_image_file


def extract_text(path: Path, mineru_config=None) -> List[Dict]:
    path = Path(path)
    suffix = path.suffix.lower()
    if is_image_file(path):
        return [
            {
                "page": None,
                "text": f"图片文件已保存：{path.name}。如果当前 Kimi 模型支持视觉输入，聊天时会直接读取截图内容。",
            }
        ]
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
        text = _extract_docx(path)
        if text:
            return [{"page": None, "text": text}]
        return [{"page": None, "text": f"DOCX 解析失败：{path.name}。请确认文件未损坏，或导出为 PDF/TXT 后入库。"}]
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


def _extract_docx(path: Path) -> str:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(path) as archive:
            document = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        return ""
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{{{namespace['w']}}}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{{{namespace['w']}}}tab":
                parts.append("\t")
            elif node.tag == f"{{{namespace['w']}}}br":
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs).strip()
