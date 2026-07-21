import importlib
import unittest


class PackageStructureTest(unittest.TestCase):
    def test_feature_modules_live_in_domain_packages(self):
        expected_modules = [
            "local_course_agent.retrieval.rag",
            "local_course_agent.retrieval.vector_index",
            "local_course_agent.retrieval.citation_check",
            "local_course_agent.retrieval.conversation_context",
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

    def test_legacy_flat_modules_alias_new_implementation_modules(self):
        aliases = {
            "local_course_agent.rag": "local_course_agent.retrieval.rag",
            "local_course_agent.vector_index": "local_course_agent.retrieval.vector_index",
            "local_course_agent.citation_check": "local_course_agent.retrieval.citation_check",
            "local_course_agent.conversation_context": "local_course_agent.retrieval.conversation_context",
            "local_course_agent.rag_eval": "local_course_agent.retrieval.rag_eval",
            "local_course_agent.course_service": "local_course_agent.learning.service",
            "local_course_agent.summary": "local_course_agent.learning.summary",
            "local_course_agent.dashboard": "local_course_agent.learning.dashboard",
            "local_course_agent.mastery": "local_course_agent.learning.mastery",
            "local_course_agent.parser_quality": "local_course_agent.ingestion.parser_quality",
            "local_course_agent.backup": "local_course_agent.ops.backup",
            "local_course_agent.config_status": "local_course_agent.ops.config_status",
            "local_course_agent.telemetry": "local_course_agent.ops.telemetry",
        }

        for legacy_name, canonical_name in aliases.items():
            self.assertIs(importlib.import_module(legacy_name), importlib.import_module(canonical_name))
