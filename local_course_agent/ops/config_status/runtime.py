from __future__ import annotations

from pathlib import Path
from typing import Dict

from local_course_agent.ops.backup import collect_backup_entries
from local_course_agent.ops.config_status.model import capability


def telemetry_status() -> Dict:
    return capability(
        "telemetry",
        "遥测诊断",
        "ok",
        True,
        "内存遥测记录器可用，用于索引、检索和 LLM 诊断。",
        [],
        {"mode": "in_memory"},
    )


def backup_status(data_dir: Path) -> Dict:
    try:
        entries = collect_backup_entries(data_dir)
    except OSError:
        return capability("backup", "备份恢复", "warning", False, "无法读取可备份数据。")
    return capability(
        "backup",
        "备份恢复",
        "ok",
        True,
        f"可备份 {len(entries)} 个数据文件。",
        [],
        {"backup_file_count": len(entries)},
    )
