# Vector Retrieval Infrastructure

## Scope

This module provides the dense retrieval side of the production hybrid RAG flow. Course indexing now writes a persistent `<course_id>.vector.json` file beside the lexical JSON index, and `CourseKnowledgeBase.search(..., strategy="hybrid")` loads that vector index before falling back to request-time rebuilds.

The implementation lives in `local_course_agent/retrieval/vector_index.py` and provides:

- `OpenAICompatibleEmbeddingModel`: real `/embeddings` client for OpenAI-compatible providers.
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
    "dimensions": 64
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
    "embedding_dimensions": 1024
  }
}
```

When these fields are present, indexing calls `POST {base_url}/embeddings` and stores normalized vectors in `<course_id>.vector.json`. Query-time vector search uses the same provider to embed the student question.

If embedding is not configured, the system uses `FakeEmbeddingModel`. This preserves fully offline behavior and deterministic tests, but retrieval quality is weaker than a semantic embedding model.

## Local Fallback

`FakeEmbeddingModel` is not a semantic model. It tokenizes English words, numbers, Chinese characters, and adjacent Chinese bigrams, then hashes tokens into a fixed-size vector with stable `blake2b` buckets.

This gives repeatable behavior across processes and machines, which is enough for unit tests and integration scaffolding. It should not be used as the final retrieval quality layer.

## Main RAG Flow

1. Course indexing writes the lexical index and then attempts to write the vector index.
2. Hybrid search builds sparse candidates with BM25, phrase, metadata, and local semantic signals.
3. It loads the persistent vector index and searches dense candidates.
4. `hybrid_merge_lexical_vector()` fuses lexical and vector rankings.
5. MMR-style diverse selection still runs after fusion.

Embedding failures do not fail course indexing. The lexical JSON index remains authoritative, and hybrid retrieval degrades to lexical/rerank results when vector loading or embedding calls fail.
