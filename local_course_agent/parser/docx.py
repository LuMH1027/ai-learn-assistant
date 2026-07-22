from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree


def extract_docx_text(path: Path) -> str:
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
