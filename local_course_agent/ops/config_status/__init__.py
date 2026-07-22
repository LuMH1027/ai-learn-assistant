from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

from local_course_agent.config import normalize_config
from local_course_agent.ops.config_status.collectors import collect_config_capabilities
from local_course_agent.ops.config_status.model import overall_status


def build_config_status(
    data_dir: Path,
    config: Mapping,
    courses: Optional[Iterable[Mapping]] = None,
) -> Dict:
    normalized = normalize_config(dict(config or {}))
    root_folder = str(normalized.get("root_folder") or "")
    root_path = Path(root_folder).expanduser() if root_folder else None
    data_path = Path(data_dir)
    capabilities = collect_config_capabilities(
        data_path=data_path,
        root_path=root_path,
        ai_config=normalized.get("ai", {}),
        web_config=normalized.get("web_search", {}),
        mineru_config=normalized.get("mineru", {}),
        courses=courses,
    )

    return {
        "data_dir": str(data_path),
        "root_folder": root_folder,
        "overall": overall_status(capabilities),
        "setup_required": _setup_required(capabilities),
        "setup_steps": _setup_steps(capabilities),
        "degradation_notices": _degradation_notices(capabilities),
        "capabilities": capabilities,
    }


def _setup_required(capabilities: Iterable[Mapping]) -> bool:
    by_key = {item.get("key"): item for item in capabilities}
    root = by_key.get("material_root", {})
    rag = by_key.get("rag_index", {})
    return root.get("status") != "ok" or int(rag.get("total_chunks") or 0) == 0


def _setup_steps(capabilities: Iterable[Mapping]) -> list[Dict]:
    by_key = {item.get("key"): item for item in capabilities}
    root = by_key.get("material_root", {})
    rag = by_key.get("rag_index", {})
    ai = by_key.get("ai", {})
    vector = by_key.get("vector", {})
    steps = [
        {
            "key": "material_root",
            "label": "设置资料根目录",
            "status": "done" if root.get("status") == "ok" else "todo",
            "detail": root.get("detail", "选择包含课程一级文件夹的本地目录。"),
        },
        {
            "key": "rag_index",
            "label": "构建课程知识库",
            "status": "done" if int(rag.get("total_chunks") or 0) > 0 else "todo",
            "detail": rag.get("detail", "选择课程后构建索引，问答才能引用课程资料。"),
        },
        {
            "key": "ai",
            "label": "配置大模型",
            "status": "done" if ai.get("enabled") else "optional",
            "detail": ai.get("detail", "未配置时使用本地检索和抽取式摘要。"),
        },
        {
            "key": "vector",
            "label": "配置真实 embedding",
            "status": "done" if vector.get("provider") == "openai_compatible" else "optional",
            "detail": vector.get("detail", "未配置时使用本地确定性 embedding。"),
        },
    ]
    return steps


def _degradation_notices(capabilities: Iterable[Mapping]) -> list[Dict]:
    notices = []
    for item in capabilities:
        key = str(item.get("key") or "")
        if key == "ai" and not item.get("enabled"):
            notices.append({
                "key": "ai",
                "label": "大模型未启用",
                "detail": "回答、摘要和练习题会优先使用课程检索与本地抽取式结果。",
            })
        elif key == "vector" and item.get("provider") == "local":
            notices.append({
                "key": "vector",
                "label": "语义向量降级",
                "detail": "当前使用本地确定性 embedding；同义表达和跨语言召回效果会弱于真实 embedding。",
            })
        elif key == "rerank" and not item.get("enabled"):
            notices.append({
                "key": "rerank",
                "label": "重排降级",
                "detail": "当前使用本地重排；复杂问题的证据排序可能不如外部 rerank provider。",
            })
        elif key == "web_search" and not item.get("enabled"):
            notices.append({
                "key": "web_search",
                "label": "联网搜索未启用",
                "detail": "时效性问题不会调用外部搜索，只会使用本地课程资料和已配置模型。",
            })
        elif key == "mineru" and not item.get("enabled"):
            notices.append({
                "key": "mineru",
                "label": "高质量 PDF 解析未启用",
                "detail": "扫描件、复杂版式和图片文字会退回到基础解析能力。",
            })
    return notices


__all__ = ["build_config_status"]
