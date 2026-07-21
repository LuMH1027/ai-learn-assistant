from __future__ import annotations

import re
from typing import Dict, List, Mapping, Optional, Sequence


ERROR_PATTERNS = (
    "解析失败",
    "无法抽取文本",
    "文件未损坏",
    "缺少 pypdf",
    "no text extracted",
    "extract text failed",
    "parse failed",
)

IMAGE_PLACEHOLDER_PATTERNS = (
    "图片文件已保存",
    "[图片]",
    "[image]",
    "<image>",
    "image placeholder",
)

OCR_PLACEHOLDER_PATTERNS = (
    "ocr",
    "扫描件",
    "scan-only",
    "scanned pdf",
    "需要 ocr",
    "无法识别",
)

DEFAULT_SHORT_PAGE_THRESHOLD = 30
LOW_COVERAGE_THRESHOLD = 0.8


def evaluate_parser_quality(
    pages: Sequence[Mapping],
    expected_pages: Optional[int] = None,
    short_page_threshold: int = DEFAULT_SHORT_PAGE_THRESHOLD,
) -> Dict:
    """Evaluate text extraction quality without performing any IO.

    The input is intentionally shaped like parser.extract_text output:
    [{"page": 1, "text": "..."}]. The returned dict is JSON-serializable so
    callers can persist it next to future OCR/PPTX parse results.
    """

    normalized_pages = [_normalize_page(raw) for raw in pages or []]
    warnings: List[Dict] = []
    metrics = {
        "page_count": len(normalized_pages),
        "expected_pages": expected_pages,
        "non_empty_pages": 0,
        "empty_pages": 0,
        "short_pages": 0,
        "error_pages": 0,
        "image_placeholder_pages": 0,
        "ocr_placeholder_pages": 0,
        "text_characters": 0,
        "coverage": 0.0,
    }

    if not normalized_pages:
        warnings.append(_warning("empty_text", "No extracted pages were returned."))
        return _report("failed", warnings, 0.0, metrics)

    for page in normalized_pages:
        page_number = page["page"]
        text = page["text"]
        stripped = text.strip()
        lowered = stripped.lower()
        usable_text = _strip_known_placeholders(stripped)

        if not stripped:
            metrics["empty_pages"] += 1
            warnings.append(_warning("empty_text", "Extracted page is empty.", page_number))
            continue

        metrics["non_empty_pages"] += 1
        metrics["text_characters"] += len(usable_text)

        if _contains_any(lowered, ERROR_PATTERNS):
            metrics["error_pages"] += 1
            warnings.append(_warning("error_message", "Extractor returned an error message as page text.", page_number))

        if _contains_any(lowered, IMAGE_PLACEHOLDER_PATTERNS):
            metrics["image_placeholder_pages"] += 1
            warnings.append(_warning("image_placeholder", "Extractor returned an image placeholder.", page_number))

        if _contains_any(lowered, OCR_PLACEHOLDER_PATTERNS):
            metrics["ocr_placeholder_pages"] += 1
            warnings.append(_warning("ocr_placeholder", "Text suggests OCR is required or incomplete.", page_number))

        if 0 < len(usable_text) < short_page_threshold and not _contains_any(lowered, IMAGE_PLACEHOLDER_PATTERNS):
            metrics["short_pages"] += 1
            warnings.append(
                _warning(
                    "short_page",
                    f"Extracted page has fewer than {short_page_threshold} usable characters.",
                    page_number,
                )
            )

    inferred_total = _infer_total_pages(normalized_pages, expected_pages)
    if inferred_total > 0:
        covered_pages = len({page["page"] for page in normalized_pages if page["page"] is not None and page["text"].strip()})
        if covered_pages == 0:
            covered_pages = metrics["non_empty_pages"]
        metrics["coverage"] = min(1.0, covered_pages / inferred_total)
    elif metrics["page_count"] > 0:
        metrics["coverage"] = metrics["non_empty_pages"] / metrics["page_count"]

    if metrics["coverage"] < LOW_COVERAGE_THRESHOLD:
        warnings.append(
            _warning(
                "low_page_coverage",
                f"Only {metrics['coverage']:.0%} of expected pages produced non-empty text.",
            )
        )

    score = _quality_score(metrics)
    if score <= 0.2 or metrics["text_characters"] == 0:
        status = "failed"
    elif warnings or score < 0.85:
        status = "warning"
    else:
        status = "ok"
    return _report(status, warnings, score, metrics)


def _quality_score(metrics: Mapping[str, float]) -> float:
    page_count = max(int(metrics.get("page_count") or 0), 1)
    score = 1.0
    score -= float(metrics.get("empty_pages") or 0) / page_count * 0.3
    score -= float(metrics.get("short_pages") or 0) / page_count * 0.15
    score -= float(metrics.get("error_pages") or 0) / page_count * 0.45
    score -= float(metrics.get("image_placeholder_pages") or 0) / page_count * 0.25
    score -= float(metrics.get("ocr_placeholder_pages") or 0) / page_count * 0.2
    coverage = float(metrics.get("coverage") or 0.0)
    if coverage < LOW_COVERAGE_THRESHOLD:
        score -= (LOW_COVERAGE_THRESHOLD - coverage) * 0.5
    return round(max(0.0, min(1.0, score)), 3)


def _normalize_page(raw: Mapping) -> Dict:
    return {
        "page": raw.get("page"),
        "text": str(raw.get("text") or ""),
    }


def _infer_total_pages(pages: Sequence[Mapping], expected_pages: Optional[int]) -> int:
    if expected_pages is not None:
        return max(0, int(expected_pages))
    page_numbers = [page.get("page") for page in pages if isinstance(page.get("page"), int) and page.get("page") > 0]
    if page_numbers:
        return max(page_numbers)
    return len(pages)


def _strip_known_placeholders(text: str) -> str:
    stripped = text
    for pattern in IMAGE_PLACEHOLDER_PATTERNS + OCR_PLACEHOLDER_PATTERNS:
        stripped = re.sub(re.escape(pattern), "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


def _contains_any(text: str, patterns: Sequence[str]) -> bool:
    return any(pattern.lower() in text for pattern in patterns)


def _warning(code: str, message: str, page: Optional[int] = None) -> Dict:
    payload = {"code": code, "message": message}
    if page is not None:
        payload["page"] = page
    return payload


def _report(status: str, warnings: List[Dict], score: float, metrics: Mapping) -> Dict:
    return {
        "status": status,
        "warnings": warnings,
        "score": round(float(score), 3),
        "metrics": dict(metrics),
    }
