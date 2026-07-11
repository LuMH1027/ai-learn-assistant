import tempfile
import unittest
from pathlib import Path

from local_course_agent.scanner import CourseScanner


class CourseScannerTest(unittest.TestCase):
    def test_first_level_folders_are_courses_and_keep_nested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Operating Systems" / "week1").mkdir(parents=True)
            (root / "Operating Systems" / "week1" / "intro.pdf").write_bytes(b"%PDF-1.4")
            (root / "Operating Systems" / "notes.md").write_text("# Notes", encoding="utf-8")
            (root / "not-a-course.txt").write_text("ignored", encoding="utf-8")

            courses = CourseScanner(root).scan()

            self.assertEqual(len(courses), 1)
            self.assertEqual(courses[0]["name"], "Operating Systems")
            self.assertEqual(courses[0]["path"], str((root / "Operating Systems").resolve()))
            file_names = {node["name"] for node in courses[0]["children"]}
            self.assertIn("week1", file_names)
            self.assertIn("notes.md", file_names)

    def test_unsupported_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Math").mkdir()
            (root / "Math" / "chapter.pdf").write_bytes(b"%PDF-1.4")
            (root / "Math" / "video.mp4").write_bytes(b"binary")

            course = CourseScanner(root).scan()[0]
            names = {node["name"] for node in course["children"]}

            self.assertEqual(names, {"chapter.pdf"})


if __name__ == "__main__":
    unittest.main()
