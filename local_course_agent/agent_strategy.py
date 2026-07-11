from __future__ import annotations


def build_agent_trace(course_name: str, question: str, has_attachments: bool, citation_count: int, memory_updated: bool):
    return [
        {
            "label": "感知",
            "status": "ok",
            "detail": f"当前课程：{course_name or '未选择'}；问题长度：{len(question)} 字",
        },
        {
            "label": "读取",
            "status": "ok" if has_attachments else "skip",
            "detail": "已读取聊天附件并写入临时检索上下文" if has_attachments else "无聊天附件，使用课程知识库",
        },
        {
            "label": "检索",
            "status": "ok" if citation_count else "empty",
            "detail": f"命中 {citation_count} 条课程资料片段" if citation_count else "当前资料未命中可靠依据",
        },
        {
            "label": "回答",
            "status": "ok",
            "detail": "基于引用片段合成回答，避免整篇资料进入上下文",
        },
        {
            "label": "记忆",
            "status": "ok" if memory_updated else "skip",
            "detail": "已更新课程独立记忆" if memory_updated else "未更新记忆",
        },
    ]

