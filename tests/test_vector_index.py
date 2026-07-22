import json
import urllib.error
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_course_agent.retrieval.vector_index import (
    EmbeddingRequestError,
    FakeEmbeddingModel,
    OpenAICompatibleEmbeddingModel,
    VectorIndex,
    VectorIndexCompatibilityError,
    VectorSearchResult,
    build_vector_index_from_chunks,
    cosine_similarity,
    create_embedding_model,
    hybrid_merge_lexical_vector,
)


class VectorIndexTest(unittest.TestCase):
    def test_fake_embedding_is_deterministic(self):
        model = FakeEmbeddingModel(dimensions=16)

        first = model.embed("页表 virtual memory")
        second = model.embed("页表 virtual memory")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_cosine_similarity_handles_basic_cases(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(cosine_similarity([0.0, 0.0], [1.0, 1.0]), 0.0)
        with self.assertRaises(ValueError):
            cosine_similarity([1.0], [1.0, 0.0])

    def test_search_returns_most_similar_documents(self):
        index = VectorIndex(FakeEmbeddingModel(dimensions=64))
        index.add("memory", "页表保存虚拟页到物理页框的映射，用于虚拟内存地址转换。", {"file_name": "内存.md"})
        index.add("process", "进程调度决定 CPU 在多个进程之间的分配。", {"file_name": "进程.md"})
        index.add("queue", "队列是先进先出的线性表。", {"file_name": "队列.md"})

        results = index.search("虚拟内存页表如何做地址转换？", limit=2)

        self.assertEqual(results[0].id, "memory")
        self.assertGreaterEqual(results[0].score, results[1].score)
        self.assertEqual(results[0].metadata["file_name"], "内存.md")

    def test_search_supports_min_score_and_limit(self):
        index = VectorIndex(FakeEmbeddingModel(dimensions=32))
        index.add("a", "alpha beta")
        index.add("b", "gamma delta")

        results = index.search("alpha", limit=1, min_score=-1.0)

        self.assertEqual(len(results), 1)

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            index = VectorIndex(FakeEmbeddingModel(dimensions=24))
            index.add("memory", "页表用于地址转换。", {"course_id": "os"})

            index.save(path)
            loaded = VectorIndex.load(path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["embedding_model"]["dimensions"], 24)
            self.assertIn("fingerprint", payload["embedding_model"])
            self.assertEqual(loaded.documents[0].id, "memory")
            self.assertEqual(loaded.documents[0].metadata["course_id"], "os")
            self.assertEqual(loaded.search("页表地址转换", limit=1)[0].id, "memory")

    def test_load_rejects_dimension_mismatch_so_caller_can_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            index = VectorIndex(FakeEmbeddingModel(dimensions=24))
            index.add("memory", "页表用于地址转换。")
            index.save(path)

            with self.assertRaisesRegex(VectorIndexCompatibilityError, "dimension mismatch"):
                VectorIndex.load(path, embedding_model=FakeEmbeddingModel(dimensions=16))

    def test_save_openai_embedding_metadata_excludes_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            model = OpenAICompatibleEmbeddingModel(
                base_url="https://llm.example/v1",
                api_key="sk-supersecret12345",
                model="embedding-model",
                dimensions=3,
            )
            index = VectorIndex(model)
            index.add("doc", "text", vector=[1.0, 0.0, 0.0])

            index.save(path)

            payload_text = path.read_text(encoding="utf-8")
            payload = json.loads(payload_text)
            self.assertEqual(payload["embedding_model"]["type"], "openai-compatible:embedding-model")
            self.assertEqual(payload["embedding_model"]["base_url"], "https://llm.example/v1")
            self.assertIn("fingerprint", payload["embedding_model"])
            self.assertNotIn("sk-supersecret12345", payload_text)
            self.assertNotIn("api_key", payload_text)

            loaded = VectorIndex.load(path, embedding_model=model)
            self.assertEqual(loaded.documents[0].id, "doc")

    def test_load_rejects_openai_base_url_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            original = OpenAICompatibleEmbeddingModel(
                base_url="https://llm.example/v1",
                api_key="secret",
                model="embedding-model",
                dimensions=3,
            )
            index = VectorIndex(original)
            index.add("doc", "text", vector=[1.0, 0.0, 0.0])
            index.save(path)
            changed = OpenAICompatibleEmbeddingModel(
                base_url="https://other.example/v1",
                api_key="secret",
                model="embedding-model",
                dimensions=3,
            )

            with self.assertRaisesRegex(VectorIndexCompatibilityError, "fingerprint mismatch"):
                VectorIndex.load(path, embedding_model=changed)

    def test_add_replaces_document_with_same_id(self):
        index = VectorIndex(FakeEmbeddingModel(dimensions=16))

        index.add("doc", "旧内容")
        index.add("doc", "新内容", {"version": 2})

        self.assertEqual(len(index.documents), 1)
        self.assertEqual(index.documents[0].text, "新内容")
        self.assertEqual(index.documents[0].metadata["version"], 2)

    def test_build_vector_index_from_chunks_preserves_rag_metadata(self):
        chunks = [
            {
                "id": "chunk-a",
                "course_id": "os",
                "file_id": "file-a",
                "file_name": "memory.md",
                "section_title": "虚拟内存",
                "material_type": "note",
                "page": 3,
                "chunk_index": 7,
                "text": "页表用于虚拟地址到物理地址的转换。",
                "tokens": ["页表"],
            },
            {
                "id": "empty",
                "file_id": "file-b",
                "chunk_index": 8,
                "text": "",
            },
        ]

        index = build_vector_index_from_chunks(chunks, FakeEmbeddingModel(dimensions=32))

        self.assertEqual(len(index.documents), 1)
        document = index.documents[0]
        self.assertEqual(document.id, "chunk-a")
        self.assertEqual(document.text, "页表用于虚拟地址到物理地址的转换。")
        self.assertEqual(document.metadata["file_id"], "file-a")
        self.assertEqual(document.metadata["section_title"], "虚拟内存")
        self.assertEqual(document.metadata["chunk_index"], 7)
        self.assertNotIn("tokens", document.metadata)

    def test_build_vector_index_from_chunks_generates_compatible_id(self):
        chunks = [
            {
                "file_id": "file-a",
                "file_name": "chapter.md",
                "page": 2,
                "chunk_index": 4,
                "text": "没有显式 id 的片段。",
            }
        ]

        index = build_vector_index_from_chunks(chunks, FakeEmbeddingModel(dimensions=16))

        self.assertEqual(index.documents[0].id, "file-a-2-4")
        self.assertEqual(index.documents[0].metadata["id"], "file-a-2-4")

    def test_build_vector_index_from_chunks_batches_embedding_calls(self):
        class BatchModel:
            model_id = "batch"
            dimensions = 2

            def __init__(self):
                self.calls = []

            def embed(self, text):
                raise AssertionError("build should use embed_many")

            def embed_many(self, texts):
                items = list(texts)
                self.calls.append(items)
                return [[1.0, 0.0] for _ in items]

        model = BatchModel()
        chunks = [
            {"id": "a", "text": "alpha"},
            {"id": "b", "text": "beta"},
        ]

        index = build_vector_index_from_chunks(chunks, model)

        self.assertEqual(model.calls, [["alpha", "beta"]])
        self.assertEqual([document.id for document in index.documents], ["a", "b"])

    def test_hybrid_merge_keeps_vector_only_and_lexical_only_hits(self):
        lexical_hits = [
            {"id": "lex", "file_id": "f1", "chunk_index": 1, "text": "BM25 命中", "score": 51.0},
        ]
        vector_hits = [
            VectorSearchResult(
                id="vec",
                text="向量命中",
                metadata={"file_id": "f2", "file_name": "vector.md", "chunk_index": 2},
                score=0.91,
            )
        ]

        merged = hybrid_merge_lexical_vector(lexical_hits, vector_hits, limit=5)

        self.assertEqual({hit["id"] for hit in merged}, {"lex", "vec"})
        by_id = {hit["id"]: hit for hit in merged}
        self.assertEqual(by_id["lex"]["lexical_score"], 51.0)
        self.assertEqual(by_id["lex"]["retrieval_sources"], ["lexical"])
        self.assertEqual(by_id["vec"]["vector_score"], 0.91)
        self.assertEqual(by_id["vec"]["retrieval_sources"], ["vector"])
        self.assertEqual(by_id["vec"]["retrieval_method"], "vector")

    def test_hybrid_merge_deduplicates_and_preserves_scores(self):
        lexical_hits = [
            {
                "id": "same",
                "file_id": "f1",
                "file_name": "memory.md",
                "chunk_index": 1,
                "text": "页表地址转换",
                "score": 88.5,
                "retrieval_method": "hybrid_bm25_semantic_rrf_mmr",
            },
            {"id": "lex-only", "file_id": "f2", "chunk_index": 2, "text": "进程调度", "score": 20.0},
        ]
        vector_hits = [
            VectorSearchResult(
                id="same",
                text="页表地址转换",
                metadata={"file_id": "f1", "file_name": "memory.md", "chunk_index": 1, "section_title": "地址转换"},
                score=0.83,
            ),
            VectorSearchResult(
                id="vec-only",
                text="TLB 加速地址转换",
                metadata={"file_id": "f3", "file_name": "tlb.md", "chunk_index": 3},
                score=0.79,
            ),
        ]

        merged = hybrid_merge_lexical_vector(lexical_hits, vector_hits, limit=5)

        self.assertEqual(len(merged), 3)
        same = next(hit for hit in merged if hit["id"] == "same")
        self.assertEqual(same["retrieval_sources"], ["lexical", "vector"])
        self.assertEqual(same["lexical_score"], 88.5)
        self.assertEqual(same["vector_score"], 0.83)
        self.assertEqual(same["score"], round(same["hybrid_rrf_score"] * 1000, 4))
        self.assertEqual(same["retrieval_method"], "hybrid_lexical_vector_rrf")
        self.assertEqual(same["section_title"], "地址转换")

    def test_hybrid_merge_respects_limit_and_orders_by_fused_rank(self):
        lexical_hits = [
            {"id": "a", "file_id": "f1", "chunk_index": 1, "text": "A", "score": 10},
            {"id": "b", "file_id": "f2", "chunk_index": 2, "text": "B", "score": 9},
        ]
        vector_hits = [
            {"id": "b", "file_id": "f2", "chunk_index": 2, "text": "B", "score": 0.9},
            {"id": "c", "file_id": "f3", "chunk_index": 3, "text": "C", "score": 0.8},
        ]

        merged = hybrid_merge_lexical_vector(lexical_hits, vector_hits, limit=2)

        self.assertEqual([hit["id"] for hit in merged], ["b", "a"])

    def test_hybrid_merge_returns_empty_for_non_positive_limit(self):
        self.assertEqual(hybrid_merge_lexical_vector([{"id": "a"}], [{"id": "b"}], limit=0), [])

    def test_create_embedding_model_uses_openai_compatible_when_configured(self):
        model = create_embedding_model(
            {
                "base_url": "https://llm.example/v1",
                "api_key": "secret",
                "embedding_model": "text-embedding-demo",
                "embedding_dimensions": 3,
            }
        )

        self.assertIsInstance(model, OpenAICompatibleEmbeddingModel)
        self.assertEqual(model.model_id, "openai-compatible:text-embedding-demo")
        self.assertEqual(model.dimensions, 3)
        self.assertEqual(model.batch_size, 32)

    def test_create_embedding_model_passes_embedding_reliability_config(self):
        model = create_embedding_model(
            {
                "base_url": "https://llm.example/v1",
                "api_key": "secret",
                "embedding_model": "text-embedding-demo",
                "embedding_batch_size": 8,
                "embedding_max_retries": 4,
                "embedding_retry_delay": 0.25,
            }
        )

        self.assertIsInstance(model, OpenAICompatibleEmbeddingModel)
        self.assertEqual(model.batch_size, 8)
        self.assertEqual(model.max_retries, 4)
        self.assertEqual(model.retry_delay, 0.25)

    def test_create_embedding_model_preserves_zero_retry_config(self):
        model = create_embedding_model(
            {
                "base_url": "https://llm.example/v1",
                "api_key": "secret",
                "embedding_model": "text-embedding-demo",
                "embedding_max_retries": 0,
                "embedding_retry_delay": 0,
            }
        )

        self.assertIsInstance(model, OpenAICompatibleEmbeddingModel)
        self.assertEqual(model.max_retries, 0)
        self.assertEqual(model.retry_delay, 0.0)

    def test_openai_compatible_embedding_model_calls_embeddings_endpoint(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {"index": 0, "embedding": [3, 0, 0]},
                            {"index": 1, "embedding": [0, 4, 0]},
                        ]
                    }
                ).encode("utf-8")

        model = OpenAICompatibleEmbeddingModel(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="embedding-model",
            dimensions=3,
        )

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            vectors = model.embed_many(["alpha", "beta"])

        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://llm.example/v1/embeddings")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(body["model"], "embedding-model")
        self.assertEqual(body["input"], ["alpha", "beta"])
        self.assertEqual(vectors, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    def test_openai_compatible_embedding_model_batches_requests(self):
        class FakeResponse:
            def __init__(self, values):
                self.values = values

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {"index": index, "embedding": value}
                            for index, value in enumerate(self.values)
                        ]
                    }
                ).encode("utf-8")

        model = OpenAICompatibleEmbeddingModel(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="embedding-model",
            dimensions=2,
            batch_size=2,
        )

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse([[1, 0], [0, 1]]),
                FakeResponse([[2, 0]]),
            ],
        ) as urlopen:
            vectors = model.embed_many(["alpha", "beta", "gamma"])

        self.assertEqual(urlopen.call_count, 2)
        first_body = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second_body = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(first_body["input"], ["alpha", "beta"])
        self.assertEqual(second_body["input"], ["gamma"])
        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])

    def test_openai_compatible_embedding_model_retries_network_errors(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps({"data": [{"index": 0, "embedding": [3, 0]}]}).encode("utf-8")

        model = OpenAICompatibleEmbeddingModel(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="embedding-model",
            dimensions=2,
            max_retries=1,
            retry_delay=0,
        )

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[urllib.error.URLError("temporary outage"), FakeResponse()],
        ) as urlopen:
            vectors = model.embed_many(["alpha"])

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(vectors, [[1.0, 0.0]])

    def test_openai_compatible_embedding_model_reports_http_error_without_key(self):
        model = OpenAICompatibleEmbeddingModel(
            base_url="https://llm.example/v1",
            api_key="sk-supersecret12345",
            model="embedding-model",
            dimensions=2,
            max_retries=0,
        )
        error = urllib.error.HTTPError(
            "https://llm.example/v1/embeddings",
            401,
            "Unauthorized",
            {},
            mock.Mock(read=lambda: b'{"error":"bad key sk-supersecret12345"}'),
        )

        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(EmbeddingRequestError) as raised:
                model.embed_many(["alpha"])

        message = str(raised.exception)
        self.assertIn("HTTP error", message)
        self.assertIn("401 Unauthorized", message)
        self.assertNotIn("sk-supersecret12345", message)

    def test_openai_compatible_embedding_model_reports_json_errors(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b"{bad json"

        model = OpenAICompatibleEmbeddingModel(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="embedding-model",
            dimensions=2,
            max_retries=0,
        )

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(EmbeddingRequestError, "JSON decode failed"):
                model.embed_many(["alpha"])


if __name__ == "__main__":
    unittest.main()
