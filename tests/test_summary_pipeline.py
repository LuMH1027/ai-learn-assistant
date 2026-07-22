import unittest

from local_course_agent.learning.summary import (
    EMPTY_SUMMARY_MESSAGE,
    EvidenceGroup,
    MapSummary,
    SummaryEvidence,
    build_map_prompt,
    build_reduce_prompt,
    build_summary_pipeline,
    evidence_group_from_dict,
    evidence_group_to_dict,
    evidence_item_from_dict,
    evidence_item_to_dict,
    generate_map_reduce_course_summary,
    group_evidence_by_section,
    map_summary_from_dict,
    map_summary_to_dict,
    normalize_summary_evidence,
    run_map_reduce_summary,
    summary_citation_from_chunk,
)
from local_course_agent.learning.summary_prompts import format_evidence_block
from local_course_agent.learning.summary_runner import map_reduce_fallback_payload
from local_course_agent.learning.summary_schema import compact_summary_text


class StubSummaryClient:
    def __init__(self, responses=None, enabled=True):
        self.responses = list(responses or [])
        self._enabled = enabled
        self.prompts = []

    def enabled(self):
        return self._enabled

    def generate(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            return None
        return self.responses.pop(0)


class FakeSummaryKnowledgeBase:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.calls = []

    def summary_chunks(self, course_id, limit=6):
        self.calls.append((course_id, limit))
        return self.chunks[:limit]


class SummaryPipelineTest(unittest.TestCase):
    def test_groups_evidence_by_file_and_section(self):
        evidence = normalize_summary_evidence(
            [
                {
                    "file_id": "os",
                    "file_name": "操作系统.md",
                    "section_title": "进程",
                    "chunk_index": 1,
                    "text": "进程是资源分配的基本单位。",
                },
                {
                    "file_id": "os",
                    "file_name": "操作系统.md",
                    "section_title": "进程",
                    "chunk_index": 2,
                    "text": "线程是调度的基本单位。",
                },
                {
                    "file_id": "os",
                    "file_name": "操作系统.md",
                    "section_title": "内存",
                    "chunk_index": 3,
                    "text": "页表用于虚拟地址到物理地址转换。",
                },
            ]
        )

        groups = group_evidence_by_section(evidence)

        self.assertEqual([group.title for group in groups], ["进程", "内存"])
        self.assertEqual([item.label for item in groups[0].evidence], ["S1", "S2"])
        self.assertEqual([item.label for item in groups[1].evidence], ["S3"])

    def test_builds_map_and_reduce_prompts_with_source_labels(self):
        evidence = normalize_summary_evidence(
            [
                {
                    "file_id": "ds",
                    "file_name": "栈.md",
                    "section_title": "栈的定义",
                    "page": 2,
                    "chunk_index": 7,
                    "text": "栈是后进先出的线性表，常用于函数调用。",
                }
            ]
        )
        group = group_evidence_by_section(evidence)[0]

        map_prompt = build_map_prompt("数据结构", group)
        self.assertIn("课程名称：数据结构", map_prompt)
        self.assertIn("[S1]", map_prompt)
        self.assertIn("栈的定义", map_prompt)
        self.assertIn("片段：7", map_prompt)

        reduce_prompt = build_reduce_prompt(
            "数据结构",
            [
                type(
                    "MapSummaryLike",
                    (),
                    {
                        "group_id": "G1",
                        "file_name": "栈.md",
                        "section_title": "栈的定义",
                        "evidence_labels": ("S1",),
                        "content": "## 章节要点\n- 栈限制访问顺序。[S1]",
                    },
                )()
            ],
        )
        self.assertIn("[G1]", reduce_prompt)
        self.assertIn("[S1]", reduce_prompt)
        self.assertIn("课程复习摘要", reduce_prompt)

    def test_run_map_reduce_summary_uses_stub_client_in_order(self):
        chunks = [
            {
                "file_id": "process",
                "file_name": "进程.md",
                "section_title": "进程调度",
                "chunk_index": 1,
                "text": "调度算法决定就绪进程获得 CPU 的顺序。",
            },
            {
                "file_id": "memory",
                "file_name": "内存.md",
                "section_title": "页表",
                "chunk_index": 2,
                "text": "页表记录虚拟页到物理页框的映射。",
            },
        ]
        client = StubSummaryClient(
            [
                "## 章节要点\n- 调度决定 CPU 分配顺序。[S1]",
                "## 章节要点\n- 页表保存地址映射。[S2]",
                "课程复习摘要\n\n## 总体脉络\n- 进程调度和内存管理分别处理运行与寻址。[S1][S2]",
            ]
        )

        result = run_map_reduce_summary(chunks, client, course_name="操作系统")

        self.assertEqual(result["llm_status"], "used")
        self.assertIn("课程复习摘要", result["content"])
        self.assertEqual(len(result["map_summaries"]), 2)
        self.assertEqual(len(client.prompts), 3)
        self.assertIn("进程调度", client.prompts[0])
        self.assertIn("页表", client.prompts[1])
        self.assertIn("章节摘要", client.prompts[2])

    def test_empty_and_disabled_states_do_not_call_generation(self):
        empty_client = StubSummaryClient(["unused"])

        empty = run_map_reduce_summary([], empty_client, course_name="空课程")

        self.assertEqual(empty["llm_status"], "empty")
        self.assertEqual(empty["content"], EMPTY_SUMMARY_MESSAGE)
        self.assertEqual(empty_client.prompts, [])

        disabled_client = StubSummaryClient(enabled=False)
        disabled = run_map_reduce_summary(
            [
                {
                    "file_id": "queue",
                    "file_name": "队列.md",
                    "section_title": "队列",
                    "chunk_index": 1,
                    "text": "队列是先进先出的线性表。",
                }
            ],
            disabled_client,
            course_name="数据结构",
        )

        self.assertEqual(disabled["llm_status"], "disabled")
        self.assertEqual(disabled_client.prompts, [])
        self.assertEqual(len(disabled["map_prompts"]), 1)

    def test_pipeline_returns_plain_dicts_for_api_integration_later(self):
        pipeline = build_summary_pipeline(
            [
                {
                    "file_id": "tree",
                    "file_name": "树.md",
                    "section_title": "二叉树",
                    "chunk_index": 4,
                    "text": "二叉树的每个结点最多有两个孩子。",
                }
            ]
        )

        self.assertEqual(pipeline["groups"][0]["title"], "二叉树")
        self.assertEqual(pipeline["groups"][0]["evidence"][0]["label"], "S1")

    def test_schema_round_trips_and_direct_modules_are_importable(self):
        evidence = SummaryEvidence(
            label="S9",
            file_id="db",
            file_name="数据库.md",
            file_path="/course/db.md",
            section_title="事务",
            material_type="讲义",
            page=8,
            chunk_index=3,
            text="事务的隔离级别影响并发异常。",
        )
        evidence_dict = evidence_item_to_dict(evidence)
        self.assertEqual(evidence_item_from_dict(evidence_dict), evidence)

        group = EvidenceGroup(
            group_id="G2",
            file_id="db",
            file_name="数据库.md",
            section_title="事务",
            material_type="讲义",
            evidence=(evidence,),
        )
        self.assertEqual(evidence_group_from_dict(evidence_group_to_dict(group)), group)

        summary = MapSummary(
            group_id="G2",
            title="事务",
            file_name="数据库.md",
            section_title="事务",
            content="## 章节要点\n- 隔离级别影响并发异常。[S9]",
            evidence_labels=("S9",),
        )
        self.assertEqual(map_summary_from_dict(map_summary_to_dict(summary)), summary)
        self.assertIn("[S9]", format_evidence_block(evidence))
        self.assertEqual(compact_summary_text("a  b\nc", 10), "a b c")

        citation = summary_citation_from_chunk(
            {
                "file_id": "db",
                "file_name": "数据库.md",
                "file_path": "/course/db.md",
                "page": 8,
                "chunk_index": 3,
                "context_text": "事务需要隔离性。",
            }
        )
        self.assertEqual(citation["location"], "第 8 页")

    def test_runner_fallback_payload_is_explicit(self):
        payload = map_reduce_fallback_payload(
            status="summary_error",
            reason="map_reduce_failed: boom",
            citations=[{"file_id": "db"}],
        )

        self.assertEqual(payload["status"], "summary_error")
        self.assertTrue(payload["fallback_needed"])
        self.assertEqual(payload["citations"], [{"file_id": "db"}])

    def test_generate_map_reduce_course_summary_uses_kb_and_client_factory(self):
        kb = FakeSummaryKnowledgeBase(
            [
                {
                    "file_id": "net",
                    "file_name": "网络.md",
                    "file_path": "/course/网络.md",
                    "section_title": "TCP",
                    "material_type": "教材",
                    "page": 3,
                    "chunk_index": 1,
                    "context_text": "TCP 通过确认、重传和序号提供可靠传输。",
                },
                {
                    "file_id": "net",
                    "file_name": "网络.md",
                    "file_path": "/course/网络.md",
                    "section_title": "UDP",
                    "material_type": "教材",
                    "page": 4,
                    "chunk_index": 2,
                    "context_text": "UDP 面向无连接，首部开销较小。",
                },
            ]
        )
        client = StubSummaryClient(
            [
                "## 章节要点\n- TCP 通过确认和重传保证可靠性。[S1]",
                "## 章节要点\n- UDP 首部开销较小。[S2]",
                "课程复习摘要\n\n## 总体脉络\n- TCP 与 UDP 体现不同传输层取舍。[S1][S2]",
            ]
        )
        created_configs = []

        def create_client(config):
            created_configs.append(config)
            return client

        result = generate_map_reduce_course_summary(
            kb,
            "network",
            "计算机网络",
            {"model": "stub"},
            create_client,
        )

        self.assertEqual(kb.calls, [("network", 12)])
        self.assertEqual(created_configs, [{"model": "stub"}])
        self.assertEqual(result["status"], "used")
        self.assertFalse(result["fallback_needed"])
        self.assertEqual(result["fallback_reason"], "")
        self.assertIn("课程复习摘要", result["content"])
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(result["citations"][0]["section_title"], "TCP")
        self.assertEqual(result["citations"][0]["location"], "第 3 页")
        self.assertEqual(len(result["map_summaries"]), 2)
        self.assertEqual(len(client.prompts), 3)

    def test_generate_map_reduce_course_summary_marks_disabled_as_fallback(self):
        kb = FakeSummaryKnowledgeBase(
            [
                {
                    "file_id": "algo",
                    "file_name": "算法.md",
                    "section_title": "排序",
                    "chunk_index": 1,
                    "text": "归并排序使用分治思想。",
                }
            ]
        )
        client = StubSummaryClient(enabled=False)

        result = generate_map_reduce_course_summary(kb, "algo", "算法", None, lambda config: client)

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["llm_status"], "disabled")
        self.assertTrue(result["fallback_needed"])
        self.assertEqual(result["fallback_reason"], "llm_disabled")
        self.assertEqual(result["content"], "")
        self.assertEqual(len(result["map_prompts"]), 1)

    def test_generate_map_reduce_course_summary_handles_empty_and_client_error(self):
        empty = generate_map_reduce_course_summary(
            FakeSummaryKnowledgeBase([]),
            "empty",
            "空课程",
            {},
            lambda config: StubSummaryClient(["unused"]),
        )

        self.assertEqual(empty["status"], "empty")
        self.assertTrue(empty["fallback_needed"])
        self.assertEqual(empty["fallback_reason"], "no_summary_chunks")
        self.assertEqual(empty["content"], EMPTY_SUMMARY_MESSAGE)

        def create_broken_client(config):
            raise RuntimeError("bad config")

        failed = generate_map_reduce_course_summary(
            FakeSummaryKnowledgeBase(
                [
                    {
                        "file_id": "db",
                        "file_name": "数据库.md",
                        "section_title": "事务",
                        "chunk_index": 1,
                        "text": "事务需要满足 ACID。",
                    }
                ]
            ),
            "db",
            "数据库",
            {"model": "broken"},
            create_broken_client,
        )

        self.assertEqual(failed["status"], "client_error")
        self.assertTrue(failed["fallback_needed"])
        self.assertIn("create_client_failed", failed["fallback_reason"])
        self.assertEqual(len(failed["citations"]), 1)


if __name__ == "__main__":
    unittest.main()
