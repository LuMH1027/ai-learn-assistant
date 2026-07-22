import importlib
import unittest
from pathlib import Path


class PackageStructureTest(unittest.TestCase):
    def test_feature_modules_live_in_domain_packages(self):
        expected_modules = [
            "local_course_agent.api.chat",
            "local_course_agent.api.chat.generation",
            "local_course_agent.api.chat.steps",
            "local_course_agent.api.context",
            "local_course_agent.api.course",
            "local_course_agent.api.http",
            "local_course_agent.api.router",
            "local_course_agent.api.server",
            "local_course_agent.api.server.chat_adapter",
            "local_course_agent.api.server.handler",
            "local_course_agent.api.server.routes",
            "local_course_agent.api.static",
            "local_course_agent.api.system",
            "local_course_agent.api.telemetry",
            "local_course_agent.web.mcp_client",
            "local_course_agent.web.normalization",
            "local_course_agent.web.policy",
            "local_course_agent.web.quality",
            "local_course_agent.retrieval.rag",
            "local_course_agent.retrieval.rag.answering",
            "local_course_agent.retrieval.rag.artifacts",
            "local_course_agent.retrieval.rag.indexing",
            "local_course_agent.retrieval.rag.search",
            "local_course_agent.retrieval.rag.store",
            "local_course_agent.retrieval.rag.vector_cache",
            "local_course_agent.retrieval.chunking",
            "local_course_agent.retrieval.query",
            "local_course_agent.retrieval.ranking",
            "local_course_agent.retrieval.reranking",
            "local_course_agent.retrieval.reranking.documents",
            "local_course_agent.retrieval.reranking.providers",
            "local_course_agent.retrieval.scoring",
            "local_course_agent.retrieval.selection",
            "local_course_agent.retrieval.vector.builders",
            "local_course_agent.retrieval.vector.index",
            "local_course_agent.retrieval.vector.math",
            "local_course_agent.retrieval.vector.merge",
            "local_course_agent.retrieval.vector.persistence",
            "local_course_agent.retrieval.vector.schema",
            "local_course_agent.retrieval.vector_index",
            "local_course_agent.retrieval.citation_check",
            "local_course_agent.retrieval.citations",
            "local_course_agent.retrieval.citations.checker",
            "local_course_agent.retrieval.citations.labels",
            "local_course_agent.retrieval.citations.postprocess",
            "local_course_agent.retrieval.citations.schema",
            "local_course_agent.retrieval.citations.tokenization",
            "local_course_agent.retrieval.conversation_context",
            "local_course_agent.retrieval.embeddings",
            "local_course_agent.retrieval.embeddings.config",
            "local_course_agent.retrieval.embeddings.models",
            "local_course_agent.retrieval.embeddings.providers",
            "local_course_agent.retrieval.embeddings.utils",
            "local_course_agent.retrieval.evaluation",
            "local_course_agent.retrieval.evaluation.rag",
            "local_course_agent.storage.codecs",
            "local_course_agent.storage.memory",
            "local_course_agent.storage.migration",
            "local_course_agent.storage.paths",
            "local_course_agent.storage.study_plan",
            "local_course_agent.evaluation.demo_baseline",
            "local_course_agent.evaluation.demo_fixtures",
            "local_course_agent.evaluation.gates",
            "local_course_agent.evaluation.quality",
            "local_course_agent.evaluation.quality.chatflow",
            "local_course_agent.evaluation.quality.common",
            "local_course_agent.evaluation.quality.summary",
            "local_course_agent.evaluation.rag_quality",
            "local_course_agent.evaluation.reports",
            "local_course_agent.learning.service",
            "local_course_agent.learning.indexing",
            "local_course_agent.learning.study_plan",
            "local_course_agent.learning.artifacts",
            "local_course_agent.learning.files",
            "local_course_agent.learning.summary",
            "local_course_agent.learning.summary.schema",
            "local_course_agent.learning.summary.prompts",
            "local_course_agent.learning.summary.runner",
            "local_course_agent.learning.dashboard",
            "local_course_agent.learning.dashboard.activity",
            "local_course_agent.learning.dashboard.mastery",
            "local_course_agent.learning.dashboard.materials",
            "local_course_agent.learning.dashboard.progress",
            "local_course_agent.learning.dashboard.utils",
            "local_course_agent.learning.mastery",
            "local_course_agent.learning.mastery.schema",
            "local_course_agent.learning.mastery.policy",
            "local_course_agent.ingestion.parser_quality",
            "local_course_agent.ops.backup",
            "local_course_agent.ops.config_status",
            "local_course_agent.ops.config_status.collectors",
            "local_course_agent.ops.config_status.filesystem",
            "local_course_agent.ops.config_status.model",
            "local_course_agent.ops.telemetry",
            "local_course_agent.ops.telemetry.core",
            "local_course_agent.ops.telemetry.recorders",
            "local_course_agent.ops.telemetry.utils",
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
            "store_codecs",
            "store_memory",
            "store_migration",
            "store_paths",
            "store_study_plan",
        ]

        for module_name in legacy_modules:
            self.assertFalse((package_dir / f"{module_name}.py").exists(), module_name)
            with self.assertRaises(ModuleNotFoundError, msg=module_name):
                importlib.import_module(f"local_course_agent.{module_name}")

    def test_learning_domains_do_not_regrow_flat_helpers(self):
        learning_dir = Path(__file__).resolve().parents[1] / "local_course_agent" / "learning"
        flat_helpers = [
            "dashboard_activity.py",
            "dashboard_mastery.py",
            "dashboard_materials.py",
            "dashboard_progress.py",
            "dashboard_utils.py",
            "summary_schema.py",
            "summary_prompts.py",
            "summary_runner.py",
            "mastery_schema.py",
            "mastery_policy.py",
        ]

        for filename in flat_helpers:
            self.assertFalse((learning_dir / filename).exists(), filename)

    def test_retrieval_domains_do_not_regrow_flat_helpers(self):
        retrieval_dir = Path(__file__).resolve().parents[1] / "local_course_agent" / "retrieval"
        flat_helpers = [
            "indexing.py",
            "knowledge_store.py",
            "rag_answering.py",
            "rag_artifacts.py",
            "rag_retrieval.py",
            "vector_cache.py",
            "embedding_config.py",
            "embedding_models.py",
            "embedding_providers.py",
            "embedding_utils.py",
            "rerankers.py",
            "rag_eval.py",
        ]

        for filename in flat_helpers:
            self.assertFalse((retrieval_dir / filename).exists(), filename)

    def test_api_domains_do_not_regrow_flat_chat_helpers(self):
        api_dir = Path(__file__).resolve().parents[1] / "local_course_agent" / "api"
        flat_helpers = [
            "chat_generation.py",
            "chat_steps.py",
        ]

        for filename in flat_helpers:
            self.assertFalse((api_dir / filename).exists(), filename)

    def test_ops_domains_do_not_regrow_flat_telemetry_helpers(self):
        ops_dir = Path(__file__).resolve().parents[1] / "local_course_agent" / "ops"
        flat_helpers = [
            "telemetry_core.py",
            "telemetry_recorders.py",
            "telemetry_utils.py",
        ]

        for filename in flat_helpers:
            self.assertFalse((ops_dir / filename).exists(), filename)

    def test_evaluation_quality_facade_stays_thin(self):
        facade = Path(__file__).resolve().parents[1] / "local_course_agent" / "evaluation" / "rag_quality.py"
        implementation_dir = facade.with_name("quality")

        self.assertTrue(implementation_dir.is_dir())
        self.assertLessEqual(len(facade.read_text(encoding="utf-8").splitlines()), 24)
