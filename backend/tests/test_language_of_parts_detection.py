import shutil
from pathlib import Path
from typing import Any, Optional

import pikepdf
import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.utils.criteria_summary import build_criteria_summary
from backend.utils.pdf_language_diagnostics import collect_language_diagnostics


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "clean_tagged.pdf"
_LANGUAGE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "language_of_parts"


def _ensure_struct_tree(pdf: pikepdf.Pdf) -> Any:
    """Return a StructTreeRoot with an initialized K array."""
    struct_tree = getattr(pdf.Root, "StructTreeRoot", None)
    if not struct_tree:
        struct_tree = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot"))
        )
        pdf.Root.StructTreeRoot = struct_tree
    if not hasattr(struct_tree, "K") or struct_tree.K is None:
        struct_tree.K = pdf.make_indirect(pikepdf.Array())
    return struct_tree


def _prepare_language_parts_pdf(tmp_path: Path) -> Path:
    if not _FIXTURE.exists():
        pytest.skip(f"Fixture PDF was not found at {_FIXTURE}")

    working_pdf = tmp_path / "language_parts.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)

    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        if not getattr(pdf.Root, "Lang", None):
            pdf.Root.Lang = "en-US"

        struct_tree = _ensure_struct_tree(pdf)
        page = pdf.pages[0]
        page_ref = page.obj

        def _make_struct_elem(struct_type: str, *, lang: Optional[str], text: str) -> Any:
            mcid_index = len(struct_tree.K)
            elem = pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/StructElem"),
                    "/S": pikepdf.Name(f"/{struct_type}"),
                    "/Pg": page_ref,
                    "/K": pikepdf.Array([pikepdf.Dictionary({"/MCID": mcid_index, "/Pg": page_ref})]),
                    "/ActualText": text,
                    "/Alt": text,
                }
            )
            if lang is not None:
                elem[pikepdf.Name("/Lang")] = lang
            return pdf.make_indirect(elem)

        struct_tree.K.append(_make_struct_elem("P", lang="english-US", text="Hello world"))
        struct_tree.K.append(_make_struct_elem("Span", lang=None, text="Пример текста"))
        pdf.save(working_pdf)

    return working_pdf


def test_language_of_parts_flags_invalid_and_missing_override(tmp_path: Path) -> None:
    working_pdf = _prepare_language_parts_pdf(tmp_path)

    analyzer = PDFAccessibilityAnalyzer()
    results = analyzer.analyze(str(working_pdf))

    wcag_issues = results.get("wcagIssues") or []
    language_issues = [issue for issue in wcag_issues if str(issue.get("criterion")) == "3.1.2"]

    assert len(language_issues) >= 2, "WCAG 3.1.2 issues should be surfaced for invalid and missing language tags"

    invalid_issue = next((issue for issue in language_issues if "invalid" in str(issue.get("description", "")).lower()), None)
    missing_override = next((issue for issue in language_issues if "override" in str(issue.get("description", "")).lower()), None)

    assert invalid_issue, "Invalid /Lang value should be reported"
    assert missing_override, "Missing language override should be reported when foreign script is present"
    assert missing_override.get("scriptHint") == "Cyrillic"


def _get_language_issues(results: dict) -> list:
    issues = results.get("issues") or []
    wcag_issues = results.get("wcagIssues") or []
    candidates = [issue for issue in wcag_issues if isinstance(issue, dict)] + [
        issue for issue in issues if isinstance(issue, dict)
    ]
    return [issue for issue in candidates if str(issue.get("criterion")) == "3.1.2"]


def test_language_of_parts_fail_is_flagged() -> None:
    pdf_path = _LANGUAGE_FIXTURES / "language_of_parts_fail.pdf"
    analyzer = PDFAccessibilityAnalyzer()
    results = analyzer.analyze(str(pdf_path))

    language_issues = _get_language_issues(results)
    missing_language = results.get("missingLanguage") or []

    assert language_issues or missing_language, "WCAG 3.1.2 should surface for mixed-language content without overrides"

    scripts = {issue.get("scriptHint") for issue in language_issues}
    assert scripts.intersection({"CJK", "Indic"}), "Non-Latin scripts should be detected on the failing fixture"

    summary = build_criteria_summary(results)
    wcag_items = (summary.get("wcag") or {}).get("items") or []
    wcag_status = {item.get("code"): item.get("status") for item in wcag_items}
    assert wcag_status.get("3.1.2") == "doesNotSupport", "Criteria summary must not claim support when language overrides are missing"


def test_language_of_parts_pass_is_clean() -> None:
    pdf_path = _LANGUAGE_FIXTURES / "language_of_parts_pass.pdf"
    analyzer = PDFAccessibilityAnalyzer()
    results = analyzer.analyze(str(pdf_path))

    language_issues = _get_language_issues(results)

    assert not language_issues, "Language overrides in the passing fixture should avoid WCAG 3.1.2 issues"
    assert not results.get("missingLanguage"), "Document-level language metadata should not regress"

    summary = build_criteria_summary(results)
    wcag_items = (summary.get("wcag") or {}).get("items") or []
    wcag_status = {item.get("code"): item.get("status") for item in wcag_items}
    assert wcag_status.get("3.1.2") == "supports", "Passing fixture should remain compliant in the criteria summary"


def test_language_of_parts_fixtures_have_expected_markup() -> None:
    passing = collect_language_diagnostics(str(_LANGUAGE_FIXTURES / "language_of_parts_pass.pdf"))
    failing = collect_language_diagnostics(str(_LANGUAGE_FIXTURES / "language_of_parts_fail.pdf"))

    assert passing.document_language == "en-US"
    assert failing.document_language == "en-US"

    assert passing.has_marked_content_language, "PASS fixture should carry BDC/EMC language overrides"
    assert not failing.has_marked_content_language, "FAIL fixture should omit language overrides by design"

    pass_scripts = {hint for page in passing.pages for hint in page.script_hints}
    fail_scripts = {hint for page in failing.pages for hint in page.script_hints}
    assert {"CJK", "Indic"}.issubset(pass_scripts.union(fail_scripts)), "Fixture text should expose non-Latin scripts"
    assert {"CJK", "Indic"}.issubset(fail_scripts), "Failing fixture should expose each non-Latin script without overrides"
