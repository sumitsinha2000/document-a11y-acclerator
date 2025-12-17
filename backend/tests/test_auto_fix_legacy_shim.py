import re
import shutil
from datetime import datetime
from pathlib import Path

import pikepdf
import pytest

import backend.auto_fix_engine as auto_fix_engine
from backend.auto_fix import AutoFixEngine as LegacyAutoFixEngine
from backend.auto_fix_engine import AutoFixEngine as ModernAutoFixEngine


_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"
)


def _patch_modern_engine(monkeypatch) -> None:
    monkeypatch.setattr(
        auto_fix_engine,
        "generate_fix_suggestions",
        lambda *_: {
            "automated": [
                {
                    "fixType": "addMetadata",
                    "category": "metadata",
                    "action": "Add document metadata",
                    "id": "add-metadata",
                }
            ],
            "semiAutomated": [],
            "manual": [],
            "estimatedTime": 0,
        },
    )
    monkeypatch.setattr(auto_fix_engine.PDFAccessibilityAnalyzer, "analyze", lambda *_: {})
    monkeypatch.setattr(auto_fix_engine.AutoFixEngine, "_analyze_fixed_pdf", lambda *_: {})


def _copy_fixture(tmp_path: Path) -> Path:
    working_pdf = tmp_path / "working.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)
    return working_pdf


def test_legacy_auto_fix_shim_delegates(monkeypatch, tmp_path) -> None:
    working_pdf = _copy_fixture(tmp_path)
    _patch_modern_engine(monkeypatch)

    engine = LegacyAutoFixEngine()
    with pytest.warns(DeprecationWarning):
        result = engine.apply_automated_fixes(str(working_pdf), scan_results={"issues": []})

    assert result.get("success"), result
    for key in ("success", "fixesApplied", "fixedFile", "successCount", "message"):
        assert key in result
    assert result.get("outputPath")


def test_auto_fix_engine_names_output_with_timestamp(monkeypatch, tmp_path) -> None:
    working_pdf = _copy_fixture(tmp_path)
    _patch_modern_engine(monkeypatch)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2, 3, 4, 5)

    monkeypatch.setattr(auto_fix_engine, "datetime", FixedDateTime)

    engine = ModernAutoFixEngine()
    scan_data = {
        "filename": "report.pdf",
        "resolved_file_path": str(working_pdf),
        "scan_results": {"issues": []},
    }
    result = engine.apply_automated_fixes("scan-1", scan_data)

    assert re.search(r"_fixed_20240102_030405\.pdf$", result.get("fixedFile", ""))


def test_metadata_preserves_author_subject_keywords(monkeypatch, tmp_path) -> None:
    working_pdf = _copy_fixture(tmp_path)

    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        pdf.docinfo["/Author"] = "Ada Lovelace"
        pdf.docinfo["/Subject"] = "Accessibility review"
        pdf.docinfo["/Keywords"] = "accessibility, pdf"
        pdf.save(working_pdf)

    _patch_modern_engine(monkeypatch)

    engine = ModernAutoFixEngine()
    scan_data = {
        "filename": working_pdf.name,
        "resolved_file_path": str(working_pdf),
        "scan_results": {"issues": []},
    }
    result = engine.apply_automated_fixes("metadata-preserve", scan_data)

    assert result.get("success"), result
    fixed_path = Path(result["fixedTempPath"])
    with pikepdf.open(fixed_path) as pdf:
        assert str(pdf.docinfo.get("/Author")) == "Ada Lovelace"
        assert str(pdf.docinfo.get("/Subject")) == "Accessibility review"
        assert str(pdf.docinfo.get("/Keywords")) == "accessibility, pdf"

        with pdf.open_metadata() as meta:
            creator = meta.get("dc:creator")
            assert creator
            if isinstance(creator, (list, tuple)):
                assert "Ada Lovelace" in [str(item) for item in creator]
            else:
                assert str(creator) == "Ada Lovelace"

            description = meta.get("dc:description")
            assert description
            assert str(description) == "Accessibility review"

            keywords = meta.get("pdf:Keywords")
            assert keywords
            assert str(keywords) == "accessibility, pdf"
