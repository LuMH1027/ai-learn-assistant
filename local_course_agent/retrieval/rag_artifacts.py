from __future__ import annotations

from typing import Dict, Iterable, List

from local_course_agent.retrieval.ranking import compact_sentence, pick_keyword


def summarize_evidence(query: str, hits: Iterable[Dict]) -> str:
    first = next(iter(hits))
    text = first["text"]
    if len(text) > 260:
        text = text[:260] + "..."
    return f"问题“{query}”与资料《{first['file_name']}》中的内容最相关。{text}"


def citation_from_chunk(chunk: Dict) -> Dict:
    return {
        "source_type": "local",
        "file_id": chunk["file_id"],
        "file_name": chunk["file_name"],
        "section_title": chunk.get("section_title", ""),
        "material_type": chunk.get("material_type", ""),
        "page": chunk.get("page"),
        "chunk_index": chunk["chunk_index"],
        "score": chunk.get("score", 0),
        "quote": chunk.get("context_text", chunk["text"])[:600],
    }


def generate_summary_from_chunks(chunks: List[Dict]) -> Dict:
    if not chunks:
        return {"content": "当前课程还没有可用于生成摘要的资料片段，请先构建知识库。", "citations": []}
    citations = [citation_from_chunk(chunk) for chunk in chunks]
    points = ["课程复习摘要", "", "## 核心知识点"]
    for chunk in chunks:
        keyword = pick_keyword(chunk["text"])
        points.append(f"- {keyword}：{compact_sentence(chunk['text'])}（来源：《{chunk['file_name']}》）")
    points.extend(["", "## 复习建议"])
    points.append("- 先按上面的核心知识点复述定义，再回到来源文件核对例子、条件和易错边界。")
    return {
        "content": "\n".join(points),
        "citations": citations,
    }


def generate_quiz_from_chunks(chunks: List[Dict]) -> Dict:
    if not chunks:
        return {"content": "当前课程还没有可用于生成练习题的资料片段，请先构建知识库。", "citations": []}
    questions = ["课程自测题"]
    for index, chunk in enumerate(chunks, start=1):
        keyword = pick_keyword(chunk["text"])
        questions.append(
            f"{index}. 基础题：说明“{keyword}”的含义或作用，并指出它解决了什么问题。\n"
            f"   应用题：结合《{chunk['file_name']}》中的材料，举一个使用“{keyword}”的场景。\n"
            f"   参考要点：{compact_sentence(chunk['text'])}"
        )
    return {
        "content": "\n\n".join(questions),
        "citations": [citation_from_chunk(chunk) for chunk in chunks],
    }
