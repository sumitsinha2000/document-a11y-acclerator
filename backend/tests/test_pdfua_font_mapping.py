from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


FONT_MAPPING_MESSAGE = (
    "Font mapping is incomplete: CID fonts must include usable /ToUnicode mappings and "
    "CIDFontType2 fonts also need /CIDToGIDMap entries (ISO 14289-1:7.11 Fonts)."
)
WEAK_MAPPING_MESSAGE = (
    "Unicode mapping exists but is not meaningful for assistive technology (ISO 14289-1:7.11 Fonts)."
)
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "font_mapping"


def _run_font_check(monkeypatch: pytest.MonkeyPatch, fonts: List[Dict[str, Any]]):
    analyzer = PDFAccessibilityAnalyzer()
    monkeypatch.setattr(analyzer, "_find_cid_fonts_missing_maps", lambda path: fonts)
    analyzer._check_pdfua_font_mappings("dummy.pdf")
    return analyzer.issues.get("pdfuaIssues", [])


def test_font_mapping_pass(monkeypatch):
    issues = _run_font_check(monkeypatch, [])
    assert not issues, "No fonts should mean no PDF/UA font mapping issues"


def test_font_mapping_fail(monkeypatch):
    fonts = [
        {
            "id": "font-1",
            "name": "AptosDisplay",
            "source": "pikepdf",
            "missingToUnicode": True,
            "missingCidToGid": False,
        }
    ]
    issues = _run_font_check(monkeypatch, fonts)

    assert len(issues) == 1, "Missing font mappings must surface exactly one issue per font"
    issue = issues[0]
    assert issue.get("severity") == "high"
    assert issue.get("clause") == "ISO 14289-1:7.11"
    assert issue.get("documentWide") is True
    assert issue.get("autoFixAvailable") is False
    assert issue.get("description") == FONT_MAPPING_MESSAGE
    assert issue.get("remediation", "").startswith(
        "Re-embed each CID font with valid /ToUnicode and, for CIDFontType2 fonts"
    )
    assert issue.get("pages") == []
    assert "text" not in issue.get("description", "").lower().replace("font mapping is incomplete", "")


def test_font_mapping_trivial_tounicode(monkeypatch):
    fonts = [
        {
            "id": "font-2",
            "name": "Glyphless",
            "source": "pypdf",
            "missingToUnicode": False,
            "missingCidToGid": False,
            "unusableToUnicode": True,
            "toUnicodeStatus": "notdefOnly",
        }
    ]
    issues = _run_font_check(monkeypatch, fonts)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.get("description") == WEAK_MAPPING_MESSAGE
    assert issue.get("severity") == "high"
    assert issue.get("clause") == "ISO 14289-1:7.11"
    assert issue.get("remediation", "").startswith("Regenerate each font's ToUnicode")
    assert issue.get("meta", {}).get("toUnicodeStatus") == "notdefOnly"


def test_font_mapping_meta_includes_descendant(monkeypatch):
    fonts = [
        {
            "id": "font-3",
            "name": "STSong-Light",
            "source": "pikepdf",
            "missingToUnicode": True,
            "missingCidToGid": False,
            "unusableToUnicode": False,
            "descendantSubtype": "/CIDFontType0",
            "failedRequirements": ["ToUnicodeMissing"],
        }
    ]
    issues = _run_font_check(monkeypatch, fonts)

    assert len(issues) == 1
    meta = issues[0].get("meta", {})
    assert meta.get("descendantSubtype") == "/CIDFontType0"
    assert meta.get("failedRequirements") == ["ToUnicodeMissing"]


def test_cidfonttype0_fixture_not_flagged():
    analyzer = PDFAccessibilityAnalyzer()
    fixture = _FIXTURE_DIR / "stsong_type0.pdf"
    fonts = analyzer._find_cid_fonts_missing_maps(str(fixture))

    assert fonts == [], "CIDFontType0 with usable ToUnicode must not require CIDToGIDMap"


def test_cmap_analysis_empty_and_notdef_only():
    analyzer = PDFAccessibilityAnalyzer()

    empty_result = analyzer._analyze_cmap_text("")
    assert empty_result["meaningful"] is False
    assert empty_result["reason"] == "empty"

    trivial_cmap = "1 beginbfchar\n<01><0000>\nendbfchar"
    trivial_result = analyzer._analyze_cmap_text(trivial_cmap)
    assert trivial_result["meaningful"] is False
    assert trivial_result["reason"] in {"notdefOnly", "noValidUnicode"}


def test_cmap_analysis_valid_mapping():
    analyzer = PDFAccessibilityAnalyzer()
    cmap = "1 beginbfchar\n<01><0041>\nendbfchar"
    result = analyzer._analyze_cmap_text(cmap)

    assert result["meaningful"] is True
    assert result["validMappings"] >= 1
