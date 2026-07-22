from __future__ import annotations

import re
from typing import Dict, List


def memory_topic(question: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", question.lower())
    stop = {"什么", "怎么", "如何", "为什么", "请问", "一下", "说明", "解释", "作用"}
    useful = [term for term in terms if term not in stop and not term.isdigit()]
    return " / ".join(useful[:3]) or question[:24] or "未命名问题"


def parse_memory_items(text: str) -> List[Dict]:
    items = []
    for line in text.splitlines():
        match = re.fullmatch(r"- 关注 (\d+) 次：(.+?)（最近问题：(.+)）", line.strip())
        if match:
            items.append({"count": int(match.group(1)), "topic": match.group(2), "sample": match.group(3)})
            continue
        legacy = re.fullmatch(r"- 最近关注：(.+)", line.strip())
        if legacy:
            sample = legacy.group(1)
            items.append({"count": 1, "topic": memory_topic(sample), "sample": sample})
    return items


def update_memory_text(current: str, question: str, limit: int = 8) -> str:
    topic = memory_topic(question)
    items = parse_memory_items(current)
    matched = next((item for item in items if item["topic"] == topic), None)
    if matched:
        matched["count"] += 1
        matched["sample"] = question[:80]
    else:
        items.append({"topic": topic, "count": 1, "sample": question[:80]})
    ranked = sorted(enumerate(items), key=lambda pair: (pair[1]["count"], pair[0]), reverse=True)
    items = [item for _, item in ranked[:limit]]
    return "\n".join(
        f"- 关注 {item['count']} 次：{item['topic']}（最近问题：{item['sample']}）" for item in items
    )
