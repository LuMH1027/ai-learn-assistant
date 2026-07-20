import time
import tempfile
import unittest
from pathlib import Path

from local_course_agent.course_service import CourseIndexJobs
from local_course_agent.rag import CourseKnowledgeBase


class CourseServiceTest(unittest.TestCase):
    def test_index_job_reports_successful_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "OS"
            source.mkdir()
            material = source / "notes.md"
            material.write_text("页表用于虚拟地址到物理地址转换。", encoding="utf-8")
            kb = CourseKnowledgeBase(Path(tmp) / "indexes")
            jobs = CourseIndexJobs(kb)

            started = jobs.start(
                "course-1",
                {
                    "path": str(source),
                    "children": [
                        {
                            "id": "notes",
                            "name": "notes.md",
                            "path": str(material),
                            "type": "file",
                        }
                    ],
                },
            )

            for _ in range(50):
                current = jobs.get(started["id"])
                if current and current["status"] == "succeeded":
                    break
                time.sleep(0.01)

            self.assertEqual(current["status"], "succeeded")
            self.assertEqual(current["result"]["indexed_files"], 1)
            self.assertGreaterEqual(current["result"]["total_chunks"], 1)


if __name__ == "__main__":
    unittest.main()
