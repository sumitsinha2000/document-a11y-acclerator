import shutil
from pathlib import Path

from backend.auto_fix_engine import AutoFixEngine
from backend.pdf_analyzer import PDFAccessibilityAnalyzer

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"


def _issue_ids(result):
    issues = result.get("issues") if isinstance(result, dict) else []
    return {
        issue.get("issueId")
        for issue in issues
        if isinstance(issue, dict) and issue.get("issueId")
    }


def test_auto_fix_adds_metadata_stream_for_pdfua(tmp_path):
    working_pdf = tmp_path / "working.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)

    analyzer = PDFAccessibilityAnalyzer()
    initial_results = analyzer.analyze(str(working_pdf))
    initial_ids = _issue_ids(initial_results)

    expected_issue_ids = {"metadata-iso14289-1-7-1"}
    assert initial_ids & expected_issue_ids, "Baseline scan should flag missing metadata stream"

    engine = AutoFixEngine()
    scan_data = {"filename": working_pdf.name, "resolved_file_path": str(working_pdf)}
    fix_result = engine.apply_automated_fixes("metadata-stream-test", scan_data)

    assert fix_result.get("success"), fix_result.get("error")

    scan_results = fix_result.get("scanResults") or {}
    rescanned_results = scan_results.get("results") or scan_results
    fixed_ids = _issue_ids(rescanned_results)

    assert not (fixed_ids & expected_issue_ids), "Metadata stream issue should be resolved after fixes"
    assert len(rescanned_results.get("issues", [])) < len(initial_results.get("issues", []))
