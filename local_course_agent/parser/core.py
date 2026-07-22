from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from local_course_agent.parser.docx import extract_docx_text
from local_course_agent.parser.mineru import (
    discover_mineru_command,
    extract_with_mineru_api,
    extract_with_mineru_cli,
)
from local_course_agent.parser.pdf import extract_pdf_text
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
        mineru_api_pages = extract_with_mineru_api(path, mineru_config or {})
        if mineru_api_pages:
            return mineru_api_pages
        mineru_pages = extract_with_mineru_cli(path, discover_mineru_command(mineru_config or {}))
        if mineru_pages:
            return mineru_pages
        return extract_pdf_text(path)
    if suffix in {".md", ".markdown", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [{"page": None, "text": text}]
    if suffix == ".docx":
        text = extract_docx_text(path)
        if text:
            return [{"page": None, "text": text}]
        return [{"page": None, "text": f"DOCX 解析失败：{path.name}。请确认文件未损坏，或导出为 PDF/TXT 后入库。"}]
    return []
