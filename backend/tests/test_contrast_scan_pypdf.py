from pathlib import Path
from typing import Any, Dict, List

import PyPDF2
import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures/contrast"


def _require_fixture(filename: str) -> Path:
    """Return a fixture path or skip if it is missing in the workspace."""
    pdf_path = _FIXTURE_DIR / filename
    if not pdf_path.exists():
        pytest.skip(f"Fixture PDF {filename} was not found at {pdf_path}")
    return pdf_path


def _run_contrast_scan(pdf_path: Path) -> List[Dict[str, Any]]:
    """Invoke the analyzer's contrast path and return consolidated issues."""
    analyzer = PDFAccessibilityAnalyzer()
    analyzer._analyze_contrast_basic(str(pdf_path))
    analyzer._consolidate_poor_contrast_issues()

    issues = analyzer.issues.get("poorContrast")
    if isinstance(issues, list):
        return issues
    return []


def _issue_text_haystack(issue: Dict[str, Any]) -> str:
    """Flatten all text fields inside an issue for substring checks."""
    fragments: List[str] = []

    def _collect(value: Any) -> None:
        if isinstance(value, str):
            fragments.append(value.lower())
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _collect(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                _collect(item)

    _collect(issue)
    return " ".join(fragments)


def _extract_fixture_keyword(pdf_path: Path) -> str:
    """
    Read textual content from a PDF and return a representative lowercase word.
    Used to ensure the contrast issue exposes a sample from the actual text.
    """
    try:
        reader = PyPDF2.PdfReader(str(pdf_path))
    except Exception as exc:
        pytest.skip(f"Unable to read fixture text from {pdf_path}: {exc}")

    tokens: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        tokens.extend(text.split())

    for token in tokens:
        normalized = "".join(ch for ch in token if ch.isalpha())
        if len(normalized) >= 4:
            return normalized.lower()

    pytest.skip(f"Could not find textual tokens inside {pdf_path} for sample assertion")


def _filter_contrast_flags(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only contrast failures (exclude manual info reminders)."""
    return [issue for issue in issues if issue.get("severity") != "info"]


def test_low_contrast_text_yields_single_issue() -> None:
    """
    Low-contrast fixture mimics multiple offending text runs and should be
    deduplicated into a single consolidated issue that exposes sample text.
    """
    pdf_path = _require_fixture("low_contrast_text.pdf")
    issues = _filter_contrast_flags(_run_contrast_scan(pdf_path))

    assert len(issues) == 1, "Expected exactly one deduplicated contrast issue"
    issue = issues[0]

    pages = issue.get("pages") or []
    assert pages == [1], f"Expected issue to reference page 1, got {pages}"

    keyword = _extract_fixture_keyword(pdf_path)
    haystack = _issue_text_haystack(issue)
    assert keyword in haystack, (
        f"Contrast issue should expose sample text containing '{keyword}'"
    )


def test_high_contrast_text_does_not_cause_issue() -> None:
    """
    High-contrast fixture ensures normal rg/RG sequences are ignored and do
    not emit contrast violations.
    """
    pdf_path = _require_fixture("high_contrast_text.pdf")
    issues = _filter_contrast_flags(_run_contrast_scan(pdf_path))

    assert issues == [], "High-contrast text should not trigger contrast issues"


def test_no_content_stream_triggers_manual_contrast_fallback_not_crash() -> None:
    """
    A PDF with missing/empty content streams should not crash the analyzer and
    should emit a manual-review reminder rather than raising an exception.
    """
    pdf_path = _require_fixture("no_content_stream.pdf")
    issues = _run_contrast_scan(pdf_path)

    assert issues, "Expected a manual fallback entry when no content stream is present"
    info_entries = [issue for issue in issues if issue.get("severity") == "info"]
    assert info_entries, "Manual fallback should be informational, not a failure"

    descriptions = " ".join(
        issue.get("description", "").lower()
        for issue in info_entries
        if isinstance(issue.get("description"), str)
    )
    assert "manual review" in descriptions, (
        "Manual fallback entry should instruct the user to perform manual contrast review"
    )
