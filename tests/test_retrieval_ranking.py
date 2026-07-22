import unittest

from local_course_agent.retrieval import query, ranking, scoring, selection
from local_course_agent.retrieval.chunking import tokenize
from local_course_agent.retrieval.rerankers import SiliconFlowReranker, apply_external_rerank, create_reranker


class RetrievalRankingStructureTest(unittest.TestCase):
    def test_ranking_facade_preserves_legacy_exports(self):
        self.assertIs(ranking.normalize_query, query.normalize_query)
        self.assertIs(ranking.expand_query_tokens, query.expand_query_tokens)
        self.assertIs(ranking.rank_candidates, scoring.rank_candidates)
        self.assertIs(ranking.local_rerank_score, scoring.local_rerank_score)
        self.assertIs(ranking.select_hybrid_vector_hits, selection.select_hybrid_vector_hits)
        self.assertIs(ranking.representative_chunks, selection.representative_chunks)
        self.assertIs(ranking.create_reranker, create_reranker)
        self.assertIn("rank_candidates", ranking.__all__)
        self.assertIn("select_hybrid_vector_hits", ranking.__all__)

    def test_query_scoring_and_selection_modules_compose(self):
        chunks = [
            {
                "id": "memory-1",
                "file_id": "book",
                "file_name": "内存.md",
                "section_title": "虚拟内存",
                "material_type": "textbook",
                "page": 1,
                "text": "页表保存虚拟页到物理页框的映射，用于完成地址转换。",
            },
            {
                "id": "process-1",
                "file_id": "slides",
                "file_name": "进程.md",
                "section_title": "进程",
                "material_type": "slides",
                "page": 2,
                "text": "进程调度决定 CPU 在多个进程之间的分配。",
            },
        ]
        for chunk in chunks:
            chunk["tokens"] = tokenize(query.indexable_chunk_text(chunk))

        normalized = query.normalize_query("页表如何完成地址转换？")
        tokens = query.expand_query_tokens(normalized, tokenize(normalized))
        candidates = scoring.rank_candidates(chunks, normalized, tokens, limit=2)
        selected = selection.select_diverse(candidates, limit=1)

        self.assertEqual(selected[0]["id"], "memory-1")
        self.assertGreater(selected[0]["local_rerank_score"], 0)

    def test_external_reranker_can_override_candidate_order(self):
        class FakeReranker:
            model_id = "fake-reranker"

            def rerank(self, query, documents, top_n=None):
                return [
                    {"index": 1, "score": 0.95},
                    {"index": 0, "score": 0.1},
                ]

        candidates = [
            {"id": "a", "file_id": "f1", "file_name": "a.md", "text": "apple", "rrf_score": 1.0},
            {"id": "b", "file_id": "f2", "file_name": "b.md", "text": "banana", "rrf_score": 0.5},
        ]

        ranked = apply_external_rerank(candidates, query="Apple", reranker=FakeReranker())

        self.assertEqual(ranked[0]["id"], "b")
        self.assertEqual(ranked[0]["rerank_model"], "fake-reranker")
        self.assertEqual(ranked[0]["local_rerank_score"], 0.95)

    def test_create_reranker_uses_siliconflow_endpoint_when_configured(self):
        reranker = create_reranker(
            {
                "base_url": "https://api.siliconflow.cn/v1",
                "api_key": "secret",
                "rerank_model": "Qwen/Qwen3-Reranker-8B",
            }
        )

        self.assertIsInstance(reranker, SiliconFlowReranker)
        self.assertEqual(reranker.base_url, "https://api.siliconflow.cn/v1")
        self.assertEqual(reranker.model, "Qwen/Qwen3-Reranker-8B")


if __name__ == "__main__":
    unittest.main()
