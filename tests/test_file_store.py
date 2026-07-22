import tempfile
import unittest
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from local_course_agent.learning.service import save_study_artifact
from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.store import AppStore, atomic_write_text


class FileStoreTest(unittest.TestCase):
    def test_course_state_is_saved_as_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            store.add_message("course-1", "user", "什么是页表？")
            memory = store.update_memory_from_question("course-1", "什么是页表？")
            store.add_note("course-1", "页表", "记录虚拟页到物理页框的映射")

            course_dir = Path(tmp) / "course_memory" / "course-1"
            self.assertTrue((course_dir / "messages.json").exists())
            self.assertTrue((course_dir / "memory.md").exists())
            self.assertTrue((course_dir / "notes.json").exists())
            self.assertIn("页表", memory)
            self.assertEqual(store.list_messages("course-1")[0]["content"], "什么是页表？")

    def test_study_plan_is_seeded_and_updated_as_course_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            seeded = store.ensure_study_plan(
                "course-1",
                [{"title": "阅读第一章", "kind": "read", "estimated_minutes": 30}],
            )
            unchanged = store.ensure_study_plan(
                "course-1",
                [{"title": "不应覆盖", "kind": "practice"}],
            )
            updated = store.update_study_plan_item("course-1", seeded[0]["id"], {"status": "done"})

            course_dir = Path(tmp) / "course_memory" / "course-1"
            self.assertTrue((course_dir / "study_plan.json").exists())
            self.assertEqual(unchanged[0]["title"], "阅读第一章")
            self.assertEqual(updated[0]["status"], "done")
            self.assertTrue(updated[0]["completed_at"])

    def test_mastery_state_is_saved_and_updated_as_course_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            state = store.upsert_mastery_knowledge_point(
                "course-1",
                {"id": "kp-page-table", "title": "页表地址转换"},
            )
            updated = store.apply_mastery_answer_result(
                "course-1",
                "kp-page-table",
                correct=False,
                question="解释页表地址转换。",
                user_answer="直接访问物理地址。",
                expected_answer="页号查页表得到页框号，再拼接偏移。",
            )

            course_dir = Path(tmp) / "course_memory" / "course-1"
            loaded = store.get_mastery_state("course-1")
            self.assertTrue((course_dir / "mastery.json").exists())
            self.assertEqual(state["knowledge_points"][0]["title"], "页表地址转换")
            self.assertEqual(updated["mastery"]["kp-page-table"]["wrong_count"], 1)
            self.assertEqual(loaded["mistakes"][0]["point_id"], "kp-page-table")

    def test_study_plan_normalizes_invalid_user_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            items = store.add_study_plan_item(
                "course-1",
                {"title": "", "kind": "broken", "status": "invalid", "estimated_minutes": 999},
            )

            self.assertEqual(items[0]["title"], "未命名学习项")
            self.assertEqual(items[0]["kind"], "read")
            self.assertEqual(items[0]["status"], "todo")
            self.assertEqual(items[0]["estimated_minutes"], 240)

    def test_concurrent_message_writes_are_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            def write_message(index):
                store.add_message("course-1", "user", f"问题 {index}")

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write_message, range(40)))

            messages = store.list_messages("course-1")

            self.assertEqual(len(messages), 40)
            self.assertEqual({message["content"] for message in messages}, {f"问题 {index}" for index in range(40)})

    def test_memory_tracks_repeated_focus_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            store.update_memory_from_question("course-1", "解释页表的作用")
            memory = store.update_memory_from_question("course-1", "解释页表的作用")

            self.assertIn("关注 2 次", memory)
            self.assertIn("页表", memory)

    def test_memory_migrates_legacy_recent_focus_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            memory_path = Path(tmp) / "course_memory" / "course-1" / "memory.md"
            memory_path.parent.mkdir(parents=True)
            memory_path.write_text("- 最近关注：什么是进程调度？", encoding="utf-8")

            memory = store.update_memory_from_question("course-1", "解释进程调度")

            self.assertIn("关注", memory)
            self.assertIn("进程调度", memory)

    def test_notes_can_be_updated_and_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.add_note("course-1", "旧标题", "旧内容")
            note_id = str(store.list_notes("course-1")[0]["id"])

            updated = store.update_note("course-1", note_id, {"title": " 新标题 ", "content": " 新内容 "})
            missing = store.update_note("course-1", "missing", {"title": "不存在"})
            deleted = store.delete_note("course-1", note_id)

            self.assertEqual(updated["title"], "新标题")
            self.assertEqual(updated["content"], "新内容")
            self.assertTrue(updated["updated_at"])
            self.assertIsNone(missing)
            self.assertTrue(deleted)
            self.assertEqual(store.list_notes("course-1"), [])
            self.assertFalse(store.delete_note("course-1", note_id))

    def test_note_update_uses_default_title_for_blank_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.add_note("course-1", "旧标题", "旧内容")
            note_id = str(store.list_notes("course-1")[0]["id"])

            updated = store.update_note("course-1", note_id, {"title": "", "content": "  保留内容  "})

            self.assertEqual(updated["title"], "学习笔记")
            self.assertEqual(updated["content"], "保留内容")

    def test_messages_and_memory_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.add_message("course-1", "user", "什么是页表？")
            store.update_memory_from_question("course-1", "什么是页表？")

            messages = store.clear_messages("course-1")
            memory = store.clear_memory("course-1")

            self.assertEqual(messages, [])
            self.assertEqual(memory, "")
            self.assertEqual(store.list_messages("course-1"), [])
            self.assertEqual(store.get_memory("course-1"), "")

    def test_state_writes_replace_files_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"

            atomic_write_text(path, '{"ok": true}')
            atomic_write_text(path, '{"ok": false}')

            self.assertEqual(path.read_text(encoding="utf-8"), '{"ok": false}')
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_legacy_sqlite_state_is_migrated_to_course_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE messages ("
                    "id INTEGER PRIMARY KEY, course_id TEXT, role TEXT, content TEXT, "
                    "citations TEXT, trace TEXT, created_at TEXT)"
                )
                conn.execute("CREATE TABLE memories (course_id TEXT, content TEXT)")
                conn.execute(
                    "CREATE TABLE notes ("
                    "course_id TEXT, id INTEGER, title TEXT, content TEXT, created_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (1, "course-1", "user", "旧消息", '[{"file_name":"a.md"}]', "[]", "2026-01-01 10:00:00"),
                )
                conn.execute(
                    "INSERT INTO memories VALUES (?, ?)",
                    ("course-1", "- 最近关注：旧问题"),
                )
                conn.execute(
                    "INSERT INTO notes VALUES (?, ?, ?, ?, ?)",
                    ("course-1", 7, "旧笔记", "旧内容", "2026-01-01 10:01:00"),
                )

            store = AppStore(Path(tmp))

            self.assertEqual(store.list_messages("course-1")[0]["content"], "旧消息")
            self.assertIn("旧问题", store.get_memory("course-1"))
            self.assertEqual(store.list_notes("course-1")[0]["title"], "旧笔记")

    def test_index_writes_use_valid_replaceable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))

            kb.index_text("os", "f1", "教材.md", "页表用于地址转换。")
            kb.clear_course("os")

            payload = json.loads((Path(tmp) / "os.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["chunks"], [])
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_study_artifact_is_saved_inside_course_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "操作系统"
            course_dir.mkdir()

            saved = save_study_artifact(
                course_dir,
                "课程摘要",
                "课程复习摘要\n\n- 进程与线程",
                [{"file_name": "chapter1.pdf", "page": 3, "chunk_index": 2}],
            )

            self.assertEqual(saved.parent.name, "AI生成")
            text = saved.read_text(encoding="utf-8")
            self.assertIn("课程复习摘要", text)
            self.assertIn("chapter1.pdf 第 3 页", text)


if __name__ == "__main__":
    unittest.main()
