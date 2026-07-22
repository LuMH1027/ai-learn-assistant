import os
import tempfile
import unittest
import time
from pathlib import Path
from unittest import mock

from local_course_agent.config import normalize_config, resolve_server_settings, resolve_siliconflow_api_key
from local_course_agent.ops.config_status import build_config_status
from local_course_agent.ops.config_status.collectors import (
    ai_generation_status,
    backup_status,
    collect_config_capabilities,
    mineru_status,
    rag_index_status,
    rerank_status,
    telemetry_status,
    vector_status,
    web_search_status,
)
from local_course_agent.uploads import (
    MAX_UPLOAD_FILE_BYTES,
    cleanup_chat_uploads,
    safe_upload_name,
    save_chat_upload,
    save_course_upload,
)


class ConfigAndUploadsTest(unittest.TestCase):
    def test_config_status_collectors_keep_public_imports(self):
        exported = [
            collect_config_capabilities,
            ai_generation_status,
            web_search_status,
            mineru_status,
            rag_index_status,
            vector_status,
            rerank_status,
            telemetry_status,
            backup_status,
        ]

        self.assertEqual(
            [func.__name__ for func in exported],
            [
                "collect_config_capabilities",
                "ai_generation_status",
                "web_search_status",
                "mineru_status",
                "rag_index_status",
                "vector_status",
                "rerank_status",
                "telemetry_status",
                "backup_status",
            ],
        )
        self.assertEqual(ai_generation_status.__module__, "local_course_agent.ops.config_status.ai")
        self.assertEqual(web_search_status.__module__, "local_course_agent.ops.config_status.web")
        self.assertEqual(mineru_status.__module__, "local_course_agent.ops.config_status.mineru")
        self.assertEqual(rag_index_status.__module__, "local_course_agent.ops.config_status.rag")
        self.assertEqual(vector_status.__module__, "local_course_agent.ops.config_status.vector")
        self.assertEqual(rerank_status.__module__, "local_course_agent.ops.config_status.rerank")
        self.assertEqual(telemetry_status.__module__, "local_course_agent.ops.config_status.runtime")
        self.assertEqual(backup_status.__module__, "local_course_agent.ops.config_status.runtime")

    def test_normalize_config_keeps_legacy_values_and_nests_ai(self):
        config = normalize_config(
            {
                "root_folder": "D:/Study",
                "ai": {
                    "base_url": "https://api.siliconflow.cn/v1",
                    "api_key": "test-key",
                    "model": "Qwen/Qwen3.5-35B-A3B",
                },
            }
        )

        self.assertEqual(config["root_folder"], "D:/Study")
        self.assertEqual(config["server"]["host"], "127.0.0.1")
        self.assertEqual(config["server"]["port"], 8000)
        self.assertEqual(config["ai"]["provider"], "openai_compatible")
        self.assertEqual(config["ai"]["base_url"], "https://api.siliconflow.cn/v1")
        self.assertEqual(config["ai"]["model"], "Qwen/Qwen3.5-35B-A3B")
        self.assertEqual(config["ai"]["embedding_model"], "Qwen/Qwen3-VL-Embedding-8B")
        self.assertEqual(config["ai"]["embedding_base_url"], "https://api.siliconflow.cn/v1")
        self.assertEqual(config["ai"]["rerank_model"], "Qwen/Qwen3-Reranker-8B")
        self.assertEqual(config["ai"]["rerank_base_url"], "https://api.siliconflow.cn/v1")
        self.assertIn("rerank_model", config["ai"])
        self.assertTrue(config["mineru"]["auto"])
        self.assertFalse(config["web_search"]["enabled"])
        self.assertEqual(config["web_search"]["provider"], "mcp")

    def test_normalize_config_keeps_web_search_settings(self):
        config = normalize_config({
            "web_search": {
                "enabled": True,
                "mcp_url": "https://search.example/mcp",
                "tool_name": "web_search",
            }
        })

        self.assertTrue(config["web_search"]["enabled"])
        self.assertEqual(config["web_search"]["mcp_url"], "https://search.example/mcp")

    def test_server_settings_resolve_from_config_and_env(self):
        config = normalize_config({"server": {"host": "0.0.0.0", "port": 8010}})
        self.assertEqual(resolve_server_settings(config), ("0.0.0.0", 8010))
        with mock.patch.dict(os.environ, {"COURSE_AGENT_HOST": "127.0.0.1", "COURSE_AGENT_PORT": "8020"}):
            self.assertEqual(resolve_server_settings(config), ("127.0.0.1", 8020))

    def test_config_status_reports_health_without_leaking_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            root = Path(tmp) / "materials"
            index_dir = data_dir / "indexes"
            root.mkdir()
            index_dir.mkdir(parents=True)
            (index_dir / "course-1.json").write_text(
                '{"schema_version": 2, "chunks": [{"file_id": "f1", "text": "页表"}]}',
                encoding="utf-8",
            )

            status = build_config_status(
                data_dir,
                {
                    "root_folder": str(root),
                    "ai": {
                        "base_url": "https://llm.example/v1",
                        "api_key": "secret-token",
                        "model": "course-model",
                    },
                    "web_search": {
                        "enabled": True,
                        "mcp_url": "https://search.example/mcp",
                        "tool_name": "web_search",
                    },
                    "mineru": {"token": "mineru-secret"},
                },
                courses=[{"id": "course-1"}],
            )

        encoded = str(status)
        self.assertEqual(status["overall"], "ok")
        self.assertFalse(status["setup_required"])
        self.assertIn("setup_steps", status)
        self.assertIn("degradation_notices", status)
        self.assertIn("data_dir", status)
        self.assertNotIn("secret-token", encoded)
        self.assertNotIn("mineru-secret", encoded)
        by_key = {item["key"]: item for item in status["capabilities"]}
        self.assertTrue(by_key["ai"]["enabled"])
        self.assertTrue(by_key["web_search"]["enabled"])
        self.assertEqual(by_key["rag_index"]["total_chunks"], 1)
        self.assertEqual(by_key["vector"]["model"], "openai-compatible:Qwen/Qwen3-VL-Embedding-8B")
        self.assertEqual(by_key["vector"]["provider"], "openai_compatible")
        self.assertTrue(by_key["rerank"]["enabled"])
        self.assertEqual(by_key["rerank"]["model"], "siliconflow-rerank:Qwen/Qwen3-Reranker-8B")

    def test_config_status_marks_missing_root_and_ai_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = build_config_status(Path(tmp) / "data", {}, courses=[])

        by_key = {item["key"]: item for item in status["capabilities"]}
        self.assertEqual(status["overall"], "warning")
        self.assertTrue(status["setup_required"])
        self.assertIn("设置资料根目录", [item["label"] for item in status["setup_steps"]])
        self.assertIn("大模型未启用", [item["label"] for item in status["degradation_notices"]])
        self.assertIn("联网搜索未启用", [item["label"] for item in status["degradation_notices"]])
        self.assertEqual(by_key["material_root"]["status"], "warning")
        self.assertIn("root_folder", by_key["material_root"]["missing"])
        self.assertEqual(by_key["ai"]["status"], "warning")
        self.assertEqual(by_key["ai"]["missing"], ["api_key"])

    def test_siliconflow_key_can_resolve_from_env_reference(self):
        with mock.patch.dict(os.environ, {"SILICONFLOW_API_KEY": "env-secret"}):
            self.assertEqual(resolve_siliconflow_api_key("$SILICONFLOW_API_KEY"), "env-secret")
            self.assertEqual(resolve_siliconflow_api_key("${SILICONFLOW_API_KEY}"), "env-secret")
            self.assertEqual(resolve_siliconflow_api_key(""), "env-secret")

    def test_safe_upload_name_removes_path_segments(self):
        self.assertEqual(safe_upload_name("../evil.pdf"), "evil.pdf")
        self.assertEqual(safe_upload_name("C:\\tmp\\note.md"), "note.md")

    def test_save_course_upload_copies_supported_file_into_drop_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "操作系统"
            course_dir.mkdir()

            saved = save_course_upload(course_dir, "chapter.md", b"# Chapter")

            self.assertEqual(saved.parent.name, "拖入资料")
            self.assertEqual(saved.read_bytes(), b"# Chapter")

    def test_save_chat_upload_accepts_screenshot_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = save_chat_upload(Path(tmp), "course-1", "screen.png", b"png-bytes")

            self.assertEqual(saved.parent.name, "course-1")
            self.assertEqual(saved.suffix, ".png")
            self.assertEqual(saved.read_bytes(), b"png-bytes")

    def test_save_upload_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "操作系统"
            course_dir.mkdir()

            with self.assertRaisesRegex(ValueError, "文件过大"):
                save_course_upload(course_dir, "chapter.md", b"x" * (MAX_UPLOAD_FILE_BYTES + 1))

    def test_chat_upload_cleanup_removes_oldest_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chat_uploads" / "course-1"
            target.mkdir(parents=True)
            for index in range(3):
                path = target / f"{index}.md"
                path.write_text("note", encoding="utf-8")
                timestamp = time.time() - (10 - index)
                path.touch()
                os.utime(path, (timestamp, timestamp))

            cleanup_chat_uploads(target, max_files=2, max_age_seconds=1000)

            self.assertEqual({path.name for path in target.iterdir()}, {"1.md", "2.md"})


if __name__ == "__main__":
    unittest.main()
