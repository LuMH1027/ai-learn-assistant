from __future__ import annotations

from pathlib import Path

from local_course_agent.parser import extract_text
from local_course_agent.scanner import is_image_file, stable_id
from local_course_agent.uploads import save_chat_upload

from .errors import ChatFlowError


def index_chat_uploads(context, data_dir: Path, course_id: str, uploads: list):
    if not uploads:
        return "", []
    config = context.config
    extracted_parts = []
    image_paths = []
    for upload in uploads:
        try:
            path = save_chat_upload(Path(data_dir), course_id, upload["filename"], upload["content"])
        except ValueError as exc:
            raise ChatFlowError(str(exc)) from exc
        if is_image_file(path):
            image_paths.append(path)
            extracted_parts.append(f"截图 {path.name} 已保存为聊天附件。")
            continue
        file_id = f"chat-{stable_id(str(path))}"
        page_texts = extract_text(path, mineru_config=config.get("mineru", {}))
        for page in page_texts:
            text = page.get("text", "")
            if not text.strip():
                continue
            context.kb.index_text(
                course_id=course_id,
                file_id=file_id,
                file_name=f"聊天附件/{path.name}",
                text=text,
                page=page.get("page"),
            )
            extracted_parts.append(f"文件 {path.name}：\n{text}")
    return "\n\n".join(extracted_parts), image_paths
