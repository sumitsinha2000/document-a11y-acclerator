from pathlib import Path
from typing import Any, Dict, Tuple, List

import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.utils.criteria_summary import build_criteria_summary


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

    metrics_getter = getattr(analyzer, "get_wcag_validator_metrics", None)
    if callable(metrics_getter):
        metrics = metrics_getter()
        if isinstance(metrics, dict):
            summary["wcagCompliance"] = metrics.get("wcagScore", summary.get("wcagCompliance"))
            summary["pdfuaCompliance"] = metrics.get("pdfuaScore", summary.get("pdfuaCompliance"))

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

    wcag_issues = results.get("wcagIssues") or []
    missing_alt = results.get("missingAltText") or []
    fixes = generate_fix_suggestions(results)
    image_fixes = [
        fix for fix in fixes.get("semiAutomated", []) if fix.get("category") == "images"
    ]

    # This PDF is expected to be mostly compliant.
    assert not any(_issue_targets_alt_text(issue) for issue in wcag_issues)
    assert wcag_compliance >= 90
    assert pdfua_compliance >= 90

    total_issues = summary.get("totalIssues", 0)
    assert isinstance(total_issues, (int, float)), "totalIssues should be numeric"

    assert isinstance(wcag_issues, list)
    assert not missing_alt, "Clean fixture should not expose missing alt entries"
    assert not image_fixes, "No image fixes should be proposed when WCAG 1.1.1 passes"


@pytest.mark.slow_pdf
def test_clean_pdf_contrast_summary(fixtures_dir: Path) -> None:
    """Clean fixture should only expose consolidated contrast issues and a non-zero WCAG score."""
    pdf_path = _require_fixture(fixtures_dir, "clean_tagged.pdf")
    results, summary = _run_full_analysis(pdf_path)
    criteria_summary = build_criteria_summary(results)

    wcag_issues = results.get("wcagIssues") or []
    assert wcag_issues == [], "Clean PDF should not expose extra WCAG issues"

    wcag_section = criteria_summary.get("wcag") or {}
    wcag_items = {item["code"]: item for item in wcag_section.get("items", [])}
    assert wcag_items.get("1.1.1", {}).get("status") == "supports"
    assert wcag_items.get("1.4.3", {}).get("status") == "doesNotSupport"
    assert wcag_items.get("1.4.6", {}).get("status") == "doesNotSupport"

    contrast_entries = results.get("poorContrast") or []
    assert len(contrast_entries) == 2, "Contrast issues should be deduplicated into two buckets"
    info_entries = [entry for entry in contrast_entries if entry.get("severity") == "info"]
    medium_entries = [entry for entry in contrast_entries if entry.get("severity") == "medium"]
    assert len(info_entries) == 1
    info_pages = set(info_entries[0].get("pages") or [])
    assert {1, 3}.issubset(info_pages)
    assert len(medium_entries) == 1
    assert medium_entries[0].get("pages") == [2]
    assert medium_entries[0].get("count", 0) > 1

    fixes = generate_fix_suggestions(results)
    manual_fixes = fixes.get("manual", [])
    contrast_fixes = [fix for fix in manual_fixes if "contrast" in (fix.get("title") or "").lower()]
    assert len(contrast_fixes) == 2, "Manual contrast fixes should mirror deduplicated issues"

    wcag_compliance = summary.get("wcagCompliance")
    assert isinstance(wcag_compliance, (int, float))
    # For this clean, tagged fixture we only require that the WCAG score
    # is non-zero and derived from the WCAG criteria, not wiped out by VeraPDF.
    assert 50 <= wcag_compliance <= 100, "WCAG score should not be low for a mostly compliant, tagged PDF"
    assert summary.get("complianceScore", 0) > 60


@pytest.mark.slow_pdf
def test_missing_alt_pdf_reports_image_issues(fixtures_dir: Path) -> None:
    pdf_path = _require_fixture(fixtures_dir, "missing_alt.pdf")
    results, summary = _run_full_analysis(pdf_path)

    assert summary.get("totalIssues", 0) > 0

    wcag_issues = results.get("wcagIssues") or []
    assert isinstance(wcag_issues, list), "Analyzer should return a list of WCAG issues"

    alt_issues = [issue for issue in wcag_issues if _issue_targets_alt_text(issue)]
    assert alt_issues, "WCAG 1.1.1 / alt-text issues should be reported for missing_alt.pdf"

    missing_alt = results.get("missingAltText") or []
    assert missing_alt, "missing_alt.pdf should surface missingAltText entries"

    fixes = generate_fix_suggestions(results)
    semi_automated = fixes.get("semiAutomated", [])
    assert any(fix.get("category") == "images" for fix in semi_automated)

    assert summary.get("wcagCompliance", 100) < 100, "WCAG compliance should reflect missing alt text"
