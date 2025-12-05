from pathlib import Path
from typing import Any, Dict, Tuple, List

import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


@pytest.fixture(scope="module")
def fixtures_dir() -> Path:
    """Return the directory that stores PDF fixtures for integration tests."""
    return Path(__file__).resolve().parent / "fixtures"


def _require_fixture(fixtures_dir: Path, filename: str) -> Path:
    """Fail fast with a skip if the requested fixture is missing."""
    pdf_path = fixtures_dir / filename
    if not pdf_path.exists():
        pytest.skip(f"Fixture PDF {filename} was not found at {pdf_path}")
    return pdf_path


def _run_full_analysis(pdf_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Execute the real analyzer and compute the summary the way the app does.
    Keeping this local avoids depending on backend.utils.app_helpers inside tests.
    """
    analyzer = PDFAccessibilityAnalyzer()
    raw_results = analyzer.analyze(str(pdf_path))
    if not isinstance(raw_results, dict):
        raw_results = {}

    verapdf_status = _estimate_verapdf_status(raw_results)
    try:
        summary = PDFAccessibilityAnalyzer.calculate_summary(raw_results, verapdf_status)
    except TypeError:
        summary = PDFAccessibilityAnalyzer.calculate_summary(raw_results)

    if not isinstance(summary, dict):
        summary = {}

    summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
    summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

    return raw_results, summary


def _estimate_verapdf_status(results: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight stand-in for build_verapdf_status that only inspects analyzer output."""
    status: Dict[str, Any] = {
        "isActive": True,
        "wcagCompliance": 100,
        "pdfuaCompliance": 100,
        "totalVeraPDFIssues": 0,
    }

    if not isinstance(results, dict):
        return status

    def _count_entries(key: str) -> int:
        values = results.get(key) or []
        if isinstance(values, list):
            return len(values)
        return 1

    wcag_issues = _count_entries("wcagIssues")
    pdfua_issues = _count_entries("pdfuaIssues")

    total = wcag_issues + pdfua_issues
    status["totalVeraPDFIssues"] = total

    if total == 0:
        return status

    status["wcagCompliance"] = max(0, 100 - wcag_issues * 10)
    status["pdfuaCompliance"] = max(0, 100 - pdfua_issues * 10)
    return status


def _issue_targets_alt_text(issue: Dict[str, Any]) -> bool:
    """Return True if the WCAG issue clearly references alt text / WCAG 1.1.1."""
    if not isinstance(issue, dict):
        return False

    searchable_fields: List[str] = []
    for field in ("criterion", "description", "remediation", "context"):
        value = issue.get(field)
        if value:
            searchable_fields.append(str(value))

    haystack = " ".join(searchable_fields).lower()
    return "1.1.1" in haystack or "non-text content" in haystack or "alt text" in haystack


@pytest.mark.slow_pdf
def test_clean_pdf_has_high_compliance(fixtures_dir: Path) -> None:
    pdf_path = _require_fixture(fixtures_dir, "clean_tagged.pdf")
    results, summary = _run_full_analysis(pdf_path)

    wcag_compliance = summary.get("wcagCompliance")
    pdfua_compliance = summary.get("pdfuaCompliance")

    assert isinstance(wcag_compliance, (int, float)), "WCAG compliance score should be numeric"
    assert isinstance(pdfua_compliance, (int, float)), "PDF/UA compliance score should be numeric"

    # This PDF is expected to be mostly compliant.
    assert wcag_compliance >= 90
    assert pdfua_compliance >= 90
    assert summary.get("totalIssues", 0) <= 5
    assert isinstance(results.get("wcagIssues", []), list)


@pytest.mark.slow_pdf
def test_missing_alt_pdf_reports_image_issues(fixtures_dir: Path) -> None:
    pdf_path = _require_fixture(fixtures_dir, "missing_alt.pdf")
    results, summary = _run_full_analysis(pdf_path)

    assert summary.get("totalIssues", 0) > 0

    wcag_issues = results.get("wcagIssues") or []
    assert isinstance(wcag_issues, list), "Analyzer should return a list of WCAG issues"

    alt_issues = [issue for issue in wcag_issues if _issue_targets_alt_text(issue)]
    assert alt_issues, "WCAG 1.1.1 / alt-text issues should be reported for missing_alt.pdf"
