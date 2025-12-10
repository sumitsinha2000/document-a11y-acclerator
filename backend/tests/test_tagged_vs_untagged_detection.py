from pathlib import Path
from typing import Any, Dict

import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tagging"


def _require_tagging_fixture(filename: str) -> Path:
    """Resolve the requested tagging fixture or skip when it is unavailable."""
    pdf_path = _FIXTURE_DIR / filename
    if not pdf_path.exists():
        pytest.skip(f"Tagging fixture {filename} was not found at {pdf_path}")
    return pdf_path


def _run_tagging_detection(pdf_path: Path) -> PDFAccessibilityAnalyzer:
    """
    Execute the analyzer paths that decide whether a document is tagged and
    prime the downstream table/list/heading logic.
    """
    analyzer = PDFAccessibilityAnalyzer()
    analyzer._analyze_with_pypdf2(str(pdf_path))
    analyzer._analyze_with_pdfplumber(str(pdf_path))
    return analyzer


def _has_generic_table_fallback(issues: Dict[str, Any]) -> bool:
    """
    Return True when the analyzer emitted the untagged fallback table message,
    which indicates that tag-dependent analysis was skipped.
    """
    table_issues = issues.get("tableIssues") or []
    if not isinstance(table_issues, list):
        return False

    for issue in table_issues:
        description = str(issue.get("description") or "").lower()
        if "may lack proper header markup" in description:
            return True
    return False


def test_struct_tree_root_and_markinfo_true_mark_doc_as_tagged() -> None:
    """
    Well-tagged documents should be treated as tagged and keep the analyzer on the
    tagged path so table/list/heading logic can run normally.
    """
    pdf_path = _require_tagging_fixture("well_tagged.pdf")
    analyzer = _run_tagging_detection(pdf_path)
    issues = analyzer.issues

    untagged_content = issues.get("untaggedContent") or []
    assert untagged_content == [], "Tagged fixture should not emit generic untagged issues"

    tagging_state = analyzer._tagging_state
    assert tagging_state["is_tagged"] is True, "Tagging detection should recognize tagged documents"
    assert tagging_state["has_struct_tree"] is True, "Well-tagged PDFs should expose StructTreeRoot"
    assert tagging_state["tables_reviewed"] is True, "Tagged documents should mark tables as reviewed"

    assert not _has_generic_table_fallback(issues), (
        "Tagged fixture should not fall back to the untagged table heuristic"
    )

    wcag_issues = issues.get("wcagIssues")
    assert isinstance(wcag_issues, list), "Tagged path should allow WCAG logic to run"


def test_no_markinfo_treated_as_untagged_even_if_other_metadata_present() -> None:
    """
    PDFs without /MarkInfo or /StructTreeRoot remain on the untagged path despite having
    other metadata such as /Lang, and the analyzer should emit the untagged heuristics.
    """
    pdf_path = _require_tagging_fixture("metadata_only_but_untagged.pdf")
    analyzer = _run_tagging_detection(pdf_path)
    issues = analyzer.issues

    untagged_content = issues.get("untaggedContent") or []
    assert untagged_content, "Expected generic untagged-content issue when tagging markers are absent"
    tagging_state = analyzer._tagging_state
    assert tagging_state["is_tagged"] is False, "Missing MarkInfo should force the untagged path"
    assert tagging_state["has_struct_tree"] is False, "StructTreeRoot should be absent in untagged fixture"
    assert tagging_state["tables_reviewed"] is False, "Untagged documents should not mark tables as reviewed"

    missing_language = issues.get("missingLanguage") or []
    assert missing_language == [], "Presence of /Lang metadata should prevent missing-language issues"
