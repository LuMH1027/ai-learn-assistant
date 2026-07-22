# RAG Eval Demo Baseline

This baseline uses the repository `sample_materials` folder to produce a small, repeatable RAG quality report. It does not call the HTTP server, the frontend, or any external LLM provider. The script builds a local demo index from sample files, runs built-in retrieval cases, executes the real in-process `ChatFlow.run()` structure gate, runs summary quality gates with local fallback and a stub map-reduce client, then renders one combined quality report.

## What It Covers

The built-in demo cases cover two sample courses:

- `demo-operating-system`: `sample_materials/操作系统/README.md` and `复习题.txt`
- `demo-data-structures`: `sample_materials/数据结构/树.md` and `栈和队列.md`

The retrieval cases check whether RAG can find source files for:

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

## Quality Gates

`--demo-baseline` combines three gates:

- Retrieval gate: checks expected citation files, retrieval quality, answer term constraints, forbidden terms, and citation support where configured.
- ChatFlow gate: instantiates `ChatFlow.run()` directly and checks payload structure, trace coverage, contextual follow-up metadata, citation checks, `llm_status`, `web_search_status`, and telemetry stages.
- Summary gate: checks the service-layer extractive fallback summary and the map-reduce summary pipeline. The map-reduce path uses a deterministic local stub client, not an external model.

## Report Fields

- `citation_hit_rate`: percentage of cases whose returned citations include at least one expected file.
- `first_citation_hit_rate`: percentage of cases whose top citation is an expected file.
- `quality_counts`: raw count of `none`, `partial`, and `sufficient` retrieval quality.
- `quality_distribution`: percentage distribution for each retrieval quality bucket.
- `average_top_score`: average score of the first citation when a citation exists.
- `chatflow_structure_pass_rate`: percentage of ChatFlow structure cases that pass.
- `summary_pipeline_pass_rate`: percentage of summary cases that pass.
- `quality_gate_passed`: combined result; demo baseline passes only when retrieval, ChatFlow, and summary gates all pass.

The baseline intentionally evaluates local evidence and orchestration contracts, not prose style from a hosted LLM. A demo run passes only when retrieval cases, ChatFlow structure cases, and summary pipeline cases all pass.

## Current Use

Use this as a smoke baseline before and after RAG changes:

```bash
python3 scripts/rag_eval.py --demo-baseline --index-dir /tmp/course-rag-demo-index
```

If a retrieval change lowers citation hit rate or shifts many cases from `partial/sufficient` to `none`, inspect the per-case returned files before changing prompts or answer generation. If `quality_gate_passed` fails while retrieval still passes, inspect the ChatFlow or Summary sections for missing payload fields, trace stages, or summary evidence labels.
