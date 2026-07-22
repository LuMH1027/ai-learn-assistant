# Vector Retrieval Infrastructure

## Scope

This module provides the dense retrieval side of the production hybrid RAG flow. Course indexing now writes a persistent `<course_id>.vector.json` file beside the lexical JSON index, and `CourseKnowledgeBase.search(..., strategy="hybrid")` loads that vector index before falling back to request-time rebuilds.

The implementation is split across `local_course_agent/retrieval/embeddings.py`
and `local_course_agent/retrieval/vector_index.py`:

- `OpenAICompatibleEmbeddingModel`: real `/embeddings` client for OpenAI-compatible providers, with batching, retry, timeout, and diagnostic errors.
- `create_embedding_model(config)`: selects a real embedding provider when `ai.embedding_model` is configured, otherwise uses the local fallback.
- `FakeEmbeddingModel`: deterministic hash-based embeddings for tests and offline local development.
- `VectorIndex.add()`: add or replace a document by id.
- `VectorIndex.search()`: rank documents with cosine similarity.
- `VectorIndex.save()` / `VectorIndex.load()`: JSON persistence.
- `cosine_similarity()`: shared scoring primitive with zero-vector and dimension validation.
- `build_vector_index_from_chunks()`: build a vector index directly from existing RAG chunks.
- `hybrid_merge_lexical_vector()`: merge lexical RAG hits and vector hits in the main hybrid RAG flow.

## Data Model

Saved index files use schema version `1`:

```json
{
  "schema_version": 1,
  "embedding_model": {
    "type": "fake-hash-embedding-v1",
    "dimensions": 64,
    "fingerprint": "sha256:..."
  },
  "documents": [
    {
      "id": "chunk-id",
      "text": "chunk text",
      "metadata": {
        "course_id": "os",
        "file_name": "memory.md"
      },
      "vector": [0.0, 0.1]
    }
  ]
}
```

`metadata` is deliberately free-form so the existing chunk fields can be copied in later: course id, file id, file name, section title, page, material type, and chunk id.

For OpenAI-compatible providers, the saved `embedding_model` object also includes a non-secret `base_url` and a fingerprint derived from provider type, base URL, and model name. The API key is never written to the vector index.

On load, `VectorIndex.load(path, embedding_model=...)` verifies the saved model id, fingerprint, and dimensions against the configured embedding model. A mismatch raises `VectorIndexCompatibilityError`, which signals callers to rebuild the vector index with the current embedding provider.

## RAG Adapter Functions

`build_vector_index_from_chunks(chunks, embedding_model)` accepts the same chunk dictionaries produced by `CourseKnowledgeBase`:

```json
{
  "id": "file-a-3-7",
  "course_id": "os",
  "file_id": "file-a",
  "file_name": "memory.md",
  "file_path": "notes/memory.md",
  "section_title": "虚拟内存",
  "material_type": "note",
  "page": 3,
  "chunk_index": 7,
  "text": "页表用于虚拟地址到物理地址的转换。"
}
```

The adapter skips empty text chunks, copies RAG metadata into the vector document, and excludes transient lexical fields such as `tokens` and `context_text`. If a chunk does not have `id`, it creates a compatible id from `file_id`, `page`, and `chunk_index`.

`hybrid_merge_lexical_vector(lexical_hits, vector_hits, limit)` accepts:

- lexical hits shaped like `CourseKnowledgeBase.search()` output.
- vector hits shaped either as `VectorSearchResult` or plain dictionaries.

It returns dictionaries compatible with current RAG hits. Duplicate chunks are merged by `id` first, then by file/chunk identity. The merged hit keeps:

- `lexical_score`: original lexical score.
- `vector_score`: original vector cosine score.
- `hybrid_rrf_score`: rank-fusion score.
- `score`: rounded fused score for existing citation and trace consumers.
- `retrieval_sources`: `["lexical"]`, `["vector"]`, or `["lexical", "vector"]`.
- `retrieval_method`: `hybrid_lexical_vector_rrf`, `vector`, or the lexical method.

This function intentionally uses rank fusion instead of directly adding scores because current lexical scores and cosine scores live on different scales.

## Embedding Providers

Real embedding is enabled through `data/config.json` under `ai`:

```json
{
  "ai": {
    "base_url": "https://api.example.com/v1",
    "api_key": "secret",
    "embedding_model": "text-embedding-model",
    "embedding_dimensions": 1024,
    "embedding_base_url": "",
    "embedding_api_key": "",
    "embedding_timeout": 30,
    "embedding_batch_size": 32,
    "embedding_max_retries": 2,
    "embedding_retry_delay": 1.0
  }
}
```

When `embedding_model`, an API key, and a base URL are present, indexing calls `POST {embedding_base_url || base_url}/embeddings` and stores normalized vectors in `<course_id>.vector.json`. Query-time vector search uses the same provider to embed the student question.

Provider reliability options:

- `embedding_batch_size`: maximum texts per `/embeddings` request.
- `embedding_max_retries`: retry count after the first failed attempt for transient network errors, HTTP 408/409/425/429, and 5xx responses.
- `embedding_retry_delay`: seconds to sleep between retries.
- `embedding_timeout`: per-request timeout in seconds.

HTTP, network, JSON decode, response count, and response dimension failures are raised as `EmbeddingRequestError` with endpoint, batch, attempt, and mismatch context. Error messages intentionally omit request headers and keys.

If embedding is not configured, the system uses `FakeEmbeddingModel`. This preserves fully offline behavior and deterministic tests, but retrieval quality is weaker than a semantic embedding model.

## Local Fallback

`FakeEmbeddingModel` is not a semantic model. It tokenizes English words, numbers, Chinese characters, and adjacent Chinese bigrams, then hashes tokens into a fixed-size vector with stable `blake2b` buckets.

This gives repeatable behavior across processes and machines, which is enough for unit tests and integration scaffolding. It should not be used as the final retrieval quality layer.

## Main RAG Flow

1. Course indexing writes the lexical index and then attempts to write the vector index.
2. `retrieval/query.py` normalizes the query, removes stop tokens, expands course-domain aliases, and extracts phrase/semantic features.
3. `retrieval/scoring.py` builds sparse candidates with BM25, phrase, metadata, and local semantic signals.
4. It loads the persistent vector index and searches dense candidates.
5. `retrieval/selection.py` calls `hybrid_merge_lexical_vector()` to fuse lexical and vector rankings, then runs MMR-style diverse selection.

`retrieval/ranking.py` remains a compatibility facade for existing imports; new ranking behavior should usually live in `query.py`, `scoring.py`, or `selection.py` according to responsibility.

Embedding failures do not fail course indexing. The lexical JSON index remains authoritative, and hybrid retrieval degrades to lexical/rerank results when vector loading or embedding calls fail. If a saved vector index was built with a different embedding model, base URL, or dimension, the hybrid flow treats it as stale and rebuilds it before falling back.
