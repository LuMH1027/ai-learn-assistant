import importlib
import unittest
from pathlib import Path


class PackageStructureTest(unittest.TestCase):
    def test_feature_modules_live_in_domain_packages(self):
        expected_modules = [
            "local_course_agent.api.chat",
            "local_course_agent.api.chat_steps",
            "local_course_agent.api.course",
            "local_course_agent.api.http",
            "local_course_agent.api.router",
            "local_course_agent.api.telemetry",
            "local_course_agent.retrieval.rag",
            "local_course_agent.retrieval.chunking",
            "local_course_agent.retrieval.ranking",
            "local_course_agent.retrieval.vector_index",
            "local_course_agent.retrieval.citation_check",
            "local_course_agent.retrieval.conversation_context",
            "local_course_agent.retrieval.embeddings",
            "local_course_agent.retrieval.rag_eval",
            "local_course_agent.learning.service",
            "local_course_agent.learning.summary",
            "local_course_agent.learning.dashboard",
            "local_course_agent.learning.mastery",
            "local_course_agent.ingestion.parser_quality",
            "local_course_agent.ops.backup",
            "local_course_agent.ops.config_status",
            "local_course_agent.ops.telemetry",
        ]

        for module_name in expected_modules:
            module = importlib.import_module(module_name)
            self.assertEqual(module_name, module.__name__)

    def test_legacy_flat_feature_modules_are_removed(self):
        package_dir = Path(__file__).resolve().parents[1] / "local_course_agent"
        legacy_modules = [
            "rag",
            "vector_index",
            "citation_check",
            "conversation_context",
            "rag_eval",
            "course_service",
            "summary",
            "dashboard",
            "mastery",
            "parser_quality",
            "backup",
            "config_status",
            "telemetry",
        ]

        for module_name in legacy_modules:
            self.assertFalse((package_dir / f"{module_name}.py").exists(), module_name)
            with self.assertRaises(ModuleNotFoundError, msg=module_name):
                importlib.import_module(f"local_course_agent.{module_name}")
