from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from local_course_agent.ops.config_status.model import capability


def data_dir_status(data_dir: Path) -> Dict:
    exists = data_dir.exists()
    writable = is_writable(data_dir)
    if exists and writable:
        return capability("data_dir", "数据目录", "ok", True, str(data_dir))
    if exists:
        return capability("data_dir", "数据目录", "warning", False, "数据目录存在，但当前不可写。")
    return capability("data_dir", "数据目录", "warning", False, "数据目录尚未创建，首次写入时会尝试创建。")


def material_root_status(root: Optional[Path]) -> Dict:
    if root is None:
        return capability("material_root", "资料根目录", "warning", False, "尚未设置资料根目录。", ["root_folder"])
    expanded = root.expanduser()
    if expanded.exists() and expanded.is_dir():
        return capability("material_root", "资料根目录", "ok", True, str(expanded))
    return capability("material_root", "资料根目录", "error", False, f"资料根目录不存在：{expanded}")


def is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
