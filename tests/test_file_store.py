import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from local_course_agent.server import save_study_artifact
from local_course_agent.store import AppStore


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
