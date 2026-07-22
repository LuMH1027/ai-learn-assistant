import unittest

from local_course_agent.learning.dashboard import build_course_dashboard
from local_course_agent.learning.dashboard.materials import materials_stats, split_course_files
from local_course_agent.learning.dashboard.progress import review_queue


class CourseDashboardTest(unittest.TestCase):
    def test_dashboard_aggregates_learning_progress_and_review_queue(self):
        dashboard = build_course_dashboard(
            _course_fixture(),
            messages=[
                {
                    "role": "user",
                    "content": "解释页表的地址转换流程",
                    "created_at": "2026-07-20 10:00:00",
                }
            ],
            notes=[
                {
                    "id": 1,
                    "title": "TLB 易错点",
                    "content": "命中后不需要访问页表。",
                    "created_at": "2026-07-21 09:00:00",
                }
            ],
            study_plan=[
                {
                    "id": 1,
                    "title": "阅读内存管理",
                    "kind": "read",
                    "status": "done",
                    "estimated_minutes": 30,
                    "completed_at": "2026-07-19 18:00:00",
                },
                {
                    "id": 2,
                    "title": "订正页表练习",
                    "kind": "practice",
                    "status": "doing",
                    "estimated_minutes": 40,
                    "updated_at": "2026-07-21 10:30:00",
                    "source_file_name": "复习题.txt",
                },
                {
                    "id": 3,
                    "title": "完成错题复盘",
                    "kind": "review",
                    "status": "todo",
                    "estimated_minutes": 20,
                    "created_at": "2026-07-18 08:00:00",
                },
            ],
            mastery_state={
                "schema_version": 1,
                "knowledge_points": [
                    {"id": "kp-page-table", "title": "页表地址转换"},
                    {"id": "kp-tlb", "title": "TLB"},
                ],
                "mastery": {
                    "kp-page-table": {
                        "score": 35,
                        "level": "weak",
                        "next_review_at": "2026-07-21 09:00:00",
                        "wrong_count": 2,
                    },
                    "kp-tlb": {
                        "score": 82,
                        "level": "mastered",
                        "next_review_at": "2026-07-28 09:00:00",
                    },
                },
                "mistakes": [
                    {"point_id": "kp-page-table", "question": "页表如何转换？", "status": "open"}
                ],
            },
            index_stats={
                "indexed_files": 2,
                "total_chunks": 12,
                "schema_version": 2,
                "tokenizer_version": "zh_ngrams_v2",
            },
            timestamp="2026-07-22 10:00:00",
        )

        self.assertEqual(dashboard["course"]["name"], "操作系统")
        self.assertEqual(dashboard["learning_progress"]["progress_percent"], 33)
        self.assertEqual(dashboard["learning_progress"]["remaining_minutes"], 60)
        self.assertEqual(dashboard["learning_progress"]["completed_minutes"], 30)
        self.assertEqual(dashboard["learning_progress"]["next_item_id"], 2)
        self.assertEqual([item["id"] for item in dashboard["review_queue"]], [2, 3])
        self.assertEqual(dashboard["mastery"]["average_score"], 58)
        self.assertEqual(dashboard["mastery"]["weak_count"], 1)
        self.assertEqual(dashboard["mastery"]["mastered_count"], 1)
        self.assertEqual(dashboard["mastery"]["due_review_count"], 1)
        self.assertEqual(dashboard["mastery"]["open_mistake_count"], 1)
        self.assertEqual(dashboard["mastery"]["weakest_points"][0]["title"], "页表地址转换")

    def test_dashboard_reports_materials_and_generated_artifacts(self):
        dashboard = build_course_dashboard(
            _course_fixture(),
            index_stats={"indexed_files": 2, "indexed_chunks": 9},
        )

        self.assertEqual(dashboard["materials"]["file_count"], 3)
        self.assertEqual(dashboard["materials"]["generated_file_count"], 3)
        self.assertEqual(dashboard["materials"]["total_bytes"], 600)
        self.assertEqual(dashboard["materials"]["by_extension"], {".md": 1, ".pdf": 1, ".txt": 1})
        self.assertEqual(dashboard["materials"]["indexed_chunks"], 9)
        self.assertEqual(dashboard["generated_artifacts"]["total"], 3)
        self.assertEqual(dashboard["generated_artifacts"]["summaries"], 1)
        self.assertEqual(dashboard["generated_artifacts"]["quizzes"], 1)
        self.assertEqual(dashboard["generated_artifacts"]["other"], 1)
        self.assertEqual(dashboard["generated_artifacts"]["latest"]["title"], "课程摘要-20260721-100000.md")

    def test_recent_activity_is_sorted_across_messages_notes_plan_and_artifacts(self):
        dashboard = build_course_dashboard(
            _course_fixture(),
            messages=[{"role": "assistant", "content": "回答", "created_at": "2026-07-21 08:00:00"}],
            notes=[{"title": "笔记", "created_at": "2026-07-21 09:00:00"}],
            study_plan=[{"id": 1, "title": "复盘", "status": "done", "completed_at": "2026-07-21 11:00:00"}],
        )

        activities = dashboard["recent_activity"]

        self.assertEqual(activities[0]["title"], "复盘")
        self.assertEqual(activities[1]["title"], "课程摘要-20260721-100000.md")
        self.assertEqual(activities[2]["title"], "笔记")
        self.assertNotIn("sort_key", activities[0])

    def test_empty_inputs_return_stable_defaults(self):
        dashboard = build_course_dashboard({"id": "empty", "name": "空课程", "path": "/courses/empty"})

        self.assertEqual(dashboard["learning_progress"]["progress_percent"], 0)
        self.assertEqual(dashboard["materials"]["file_count"], 0)
        self.assertEqual(dashboard["review_queue"], [])
        self.assertEqual(dashboard["mastery"]["tracked_count"], 0)
        self.assertEqual(dashboard["generated_artifacts"]["total"], 0)
        self.assertEqual(dashboard["recent_activity"], [])

    def test_projection_modules_are_independently_callable(self):
        material_files, generated_files = split_course_files(_course_fixture())
        review_items = review_queue(
            [
                {"id": 1, "title": "已完成", "status": "done", "kind": "read"},
                {"id": 2, "title": "进行中", "status": "doing", "kind": "practice"},
                {"id": 3, "title": "复习", "status": "todo", "kind": "review"},
            ]
        )

        self.assertEqual(len(material_files), 3)
        self.assertEqual(len(generated_files), 3)
        self.assertEqual(materials_stats(material_files, generated_files, {})["by_extension"], {".md": 1, ".pdf": 1, ".txt": 1})
        self.assertEqual([item["id"] for item in review_items], [2, 3])


def _course_fixture():
    return {
        "id": "os",
        "name": "操作系统",
        "path": "/courses/os",
        "children": [
            {
                "id": "folder-materials",
                "name": "资料",
                "type": "folder",
                "path": "/courses/os/资料",
                "children": [
                    {
                        "id": "book",
                        "name": "教材.pdf",
                        "type": "file",
                        "path": "/courses/os/资料/教材.pdf",
                        "extension": ".pdf",
                        "size": 300,
                    },
                    {
                        "id": "notes",
                        "name": "课堂笔记.md",
                        "type": "file",
                        "path": "/courses/os/资料/课堂笔记.md",
                        "extension": ".md",
                        "size": 200,
                    },
                ],
            },
            {
                "id": "quiz",
                "name": "复习题.txt",
                "type": "file",
                "path": "/courses/os/复习题.txt",
                "extension": ".txt",
                "size": 100,
            },
            {
                "id": "generated",
                "name": "AI生成",
                "type": "folder",
                "path": "/courses/os/AI生成",
                "children": [
                    {
                        "id": "summary",
                        "name": "课程摘要-20260721-100000.md",
                        "type": "file",
                        "path": "/courses/os/AI生成/课程摘要-20260721-100000.md",
                        "extension": ".md",
                        "size": 1000,
                        "modified_at": "2026-07-21 10:00:00",
                    },
                    {
                        "id": "exercise",
                        "name": "练习题-20260720-100000.md",
                        "type": "file",
                        "path": "/courses/os/AI生成/练习题-20260720-100000.md",
                        "extension": ".md",
                        "size": 800,
                        "modified_at": "2026-07-20 10:00:00",
                    },
                    {
                        "id": "other",
                        "name": "错题整理.md",
                        "type": "file",
                        "path": "/courses/os/AI生成/错题整理.md",
                        "extension": ".md",
                        "size": 500,
                        "modified_at": "2026-07-19 10:00:00",
                    },
                ],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
