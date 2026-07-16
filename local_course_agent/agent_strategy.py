from __future__ import annotations


def build_agent_trace(
    course_name: str,
    question: str,
    has_attachments: bool,
    citation_count: int,
    memory_updated: bool,
    llm_status: str = "disabled",
    web_status: str = "skipped",
    web_source_count: int = 0,
):
    answer_details = {
        "used": "已调用配置的大模型，并结合可用的课程与网页证据生成回答",
        "fallback": "大模型调用失败，已降级为本地课程检索回答",
        "disabled": "大模型未配置，使用本地课程检索回答",
    }
    web_details = {
        "used": f"本地证据不足或问题具有时效性，已采用 {web_source_count} 条网页来源",
        "empty": "已执行网页搜索，但没有得到可引用的 HTTP 来源",
        "failed": "网页搜索失败，已继续使用本地资料或模型能力回答",
        "disabled": "判断需要联网，但尚未配置 Web Search MCP",
        "skipped": "本地课程证据充分，无需联网",
    }
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
            "label": "联网",
            "status": "ok" if web_status == "used" else ("skip" if web_status in {"skipped", "disabled"} else "empty"),
            "detail": web_details.get(web_status, web_details["failed"]),
        },
        {
            "label": "回答",
            "status": "ok" if llm_status == "used" else "skip",
            "detail": answer_details.get(llm_status, answer_details["fallback"]),
        },
        {
            "label": "记忆",
            "status": "ok" if memory_updated else "skip",
            "detail": "已更新课程独立记忆" if memory_updated else "未更新记忆",
        },
    ]
