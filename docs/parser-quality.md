# Parser Quality Evaluation

`local_course_agent.parser_quality` provides a pure quality gate for text returned by `extract_text()`.
It does not parse files, call OCR, or write state. The goal is to make parser health visible before
PPTX, OCR, and richer document pipelines are wired into the main ingestion flow.

## API

```python
from local_course_agent.parser_quality import evaluate_parser_quality

report = evaluate_parser_quality(
    pages=[
        {"page": 1, "text": "第一页正文..."},
        {"page": 2, "text": "第二页正文..."},
    ],
    expected_pages=2,
)
```

The function accepts the same shape currently returned by `extract_text()`:

- `page`: page number when known, otherwise `None`
- `text`: extracted text or parser placeholder text

It returns a JSON-serializable report:

```json
{
  "status": "ok",
  "warnings": [],
  "score": 1.0,
  "metrics": {
    "page_count": 2,
    "expected_pages": 2,
    "non_empty_pages": 2,
    "empty_pages": 0,
    "short_pages": 0,
    "error_pages": 0,
    "image_placeholder_pages": 0,
    "ocr_placeholder_pages": 0,
    "text_characters": 42,
    "coverage": 1.0
  }
}
```

## Status

- `ok`: no warnings and score is high enough for normal indexing
- `warning`: parser returned usable text, but quality signals suggest partial or degraded extraction
- `failed`: no pages, no usable text, or the score is too low to trust

## Warning Codes

- `empty_text`: no pages were returned, or a returned page has no text
- `error_message`: page text looks like a parser error message such as PDF/DOCX parse failure
- `short_page`: extracted page has fewer usable characters than the configured threshold
- `image_placeholder`: output is an image placeholder instead of extracted text
- `ocr_placeholder`: output indicates scanned content or OCR is required/incomplete
- `low_page_coverage`: fewer than 80% of expected pages produced non-empty text

## Scoring

The score starts at `1.0` and applies bounded penalties for empty pages, short pages, parser error
messages, image placeholders, OCR placeholders, and low page coverage. It is intentionally heuristic:
the score is a triage signal for ingestion UX and logging, not a semantic correctness metric.

## Future Integration Points

- OCR pipeline: route `failed` or `warning` reports with `ocr_placeholder` / `image_placeholder` to an
  OCR-capable extractor.
- PPTX pipeline: estimate `expected_pages` from slide count and use `coverage` to detect slide text
  extraction gaps.
- RAG retrieval: skip or down-rank chunks from files with `failed` quality once parser metadata is
  persisted into the chunk index.

## Index Build Result

`build_course_index()` evaluates every indexed file immediately after `extract_text()` returns pages.
The existing `indexed_files` and `total_chunks` fields keep their original meaning; parser quality is
reported as an additional summary field:

```json
{
  "ok": true,
  "indexed_files": 2,
  "total_chunks": 8,
  "parser_quality": {
    "counts": {
      "ok": 1,
      "warning": 1,
      "failed": 0
    },
    "files": [
      {
        "file_id": "notes",
        "file_name": "notes.md",
        "path": "/course/notes.md",
        "status": "ok",
        "warnings": [],
        "score": 1.0
      },
      {
        "file_id": "scan",
        "file_name": "scan.pdf",
        "path": "/course/scan.pdf",
        "status": "warning",
        "warnings": [
          {
            "code": "ocr_placeholder",
            "message": "Text suggests OCR is required or incomplete.",
            "page": 1
          }
        ],
        "score": 0.65
      }
    ]
  }
}
```

Low-quality files are still counted in `indexed_files` and their extracted text is still passed to the
knowledge-base rebuild step. The report is currently visibility-only so callers can surface degraded
ingestion without changing indexing semantics.
