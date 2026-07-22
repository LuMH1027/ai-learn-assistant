from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def extract_pdf_text(path: Path) -> List[Dict]:
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
