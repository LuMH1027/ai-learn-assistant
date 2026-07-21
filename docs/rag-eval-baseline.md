# RAG Eval Demo Baseline

This baseline uses the repository `sample_materials` folder to produce a small, repeatable RAG retrieval report. It does not call the server, the frontend, or an LLM. The script builds a local demo index from sample files, runs built-in eval cases, and renders citation hit rates plus retrieval quality distribution.

## What It Covers

The built-in demo cases cover two sample courses:

- `demo-operating-system`: `sample_materials/操作系统/README.md` and `复习题.txt`
- `demo-data-structures`: `sample_materials/数据结构/树.md` and `栈和队列.md`

The cases currently check whether retrieval can find source files for:

- process vs thread
- page table and virtual memory
- file system responsibilities
- binary search tree operations
- balanced tree lookup efficiency
- stack and queue scenarios

## Run

```bash
python3 scripts/rag_eval.py --demo-baseline --index-dir /tmp/course-rag-demo-index --output /tmp/rag-eval-baseline.md
```

For JSON output:

```bash
python3 scripts/rag_eval.py --demo-baseline --index-dir /tmp/course-rag-demo-index --format json --output /tmp/rag-eval-baseline.json
```

Use a different sample root when validating copied fixtures:

```bash
python3 scripts/rag_eval.py --demo-baseline --sample-root path/to/sample_materials
```

## Report Fields

- `citation_hit_rate`: percentage of cases whose returned citations include at least one expected file.
- `first_citation_hit_rate`: percentage of cases whose top citation is an expected file.
- `quality_counts`: raw count of `none`, `partial`, and `sufficient` retrieval quality.
- `quality_distribution`: percentage distribution for each retrieval quality bucket.
- `average_top_score`: average score of the first citation when a citation exists.

The baseline intentionally evaluates retrieval evidence, not final LLM answer style. A case passes only when it hits an expected citation file and meets its `min_quality`.

## Current Use

Use this as a smoke baseline before and after RAG changes:

```bash
python3 scripts/rag_eval.py --demo-baseline --index-dir /tmp/course-rag-demo-index
```

If a retrieval change lowers citation hit rate or shifts many cases from `partial/sufficient` to `none`, inspect the per-case returned files before changing prompts or answer generation.
