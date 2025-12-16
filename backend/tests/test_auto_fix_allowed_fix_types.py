import shutil
from pathlib import Path

import pikepdf

import backend.auto_fix_engine as auto_fix_engine
from backend.auto_fix_engine import AutoFixEngine
from backend.pdf_structure_standards import COMMON_ROLEMAP_MAPPINGS


_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"
)


def test_auto_fix_skips_when_no_automated_suggestions(monkeypatch, tmp_path):
    working_pdf = tmp_path / "working.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)

    monkeypatch.setattr(
        auto_fix_engine, "generate_fix_suggestions", lambda *_: {"automated": [], "semiAutomated": [], "manual": [], "estimatedTime": 0}
    )
    monkeypatch.setattr(auto_fix_engine.PDFAccessibilityAnalyzer, "analyze", lambda self, path: {})

    engine = AutoFixEngine()
    scan_data = {"filename": working_pdf.name, "resolved_file_path": str(working_pdf)}
    result = engine.apply_automated_fixes("no-suggestions", scan_data)

    assert result.get("success"), result
    fixes_applied = result.get("fixesApplied") or []
    assert all(fix.get("implicit") for fix in fixes_applied)
    assert result.get("successCount") == 0


def test_auto_fix_runs_rolemap_when_suggested(monkeypatch, tmp_path):
    working_pdf = tmp_path / "rolemap.pdf"

    shutil.copyfile(_FIXTURE, working_pdf)
    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        pdf.Root.StructTreeRoot = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot"))
        )
        pdf.Root.StructTreeRoot.K = pdf.make_indirect(pikepdf.Array())
        pdf.Root.StructTreeRoot.RoleMap = pdf.make_indirect(
            pikepdf.Dictionary({"/Aside": "/P"})
        )
        pdf.save(working_pdf)

    engine = AutoFixEngine()
    monkeypatch.setattr(engine, "_analyze_fixed_pdf", lambda *_: {})

    scan_data = {
        "filename": working_pdf.name,
        "resolved_file_path": str(working_pdf),
        "scan_results": {"roleMapMissingMappings": ["Aside"]},
    }
    result = engine.apply_automated_fixes("rolemap-suggestion", scan_data)

    assert result.get("success"), result
    fixes_applied = result.get("fixesApplied") or []
    rolemap_fixes = [
        fix for fix in fixes_applied if fix.get("fixType") == "fixRoleMap" and fix.get("success")
    ]
    assert rolemap_fixes, "RoleMap fix should run when suggested"
    assert rolemap_fixes[0].get("suggestionId") == "fix-rolemap-1"
    assert not rolemap_fixes[0].get("implicit")
    assert result.get("successCount") == len(rolemap_fixes) == 1


def test_auto_fix_rolemap_no_change_does_not_count(monkeypatch, tmp_path):
    working_pdf = tmp_path / "rolemap-complete.pdf"

    shutil.copyfile(_FIXTURE, working_pdf)
    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        pdf.Root.StructTreeRoot = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot"))
        )
        pdf.Root.StructTreeRoot.K = pdf.make_indirect(pikepdf.Array())
        rolemap_entries = {
            custom: standard for custom, standard in COMMON_ROLEMAP_MAPPINGS.items()
        }
        pdf.Root.StructTreeRoot.RoleMap = pdf.make_indirect(
            pikepdf.Dictionary(rolemap_entries)
        )
        pdf.save(working_pdf)

    engine = AutoFixEngine()
    monkeypatch.setattr(engine, "_analyze_fixed_pdf", lambda *_: {})

    scan_data = {
        "filename": working_pdf.name,
        "resolved_file_path": str(working_pdf),
        "scan_results": {"roleMapMissingMappings": list(COMMON_ROLEMAP_MAPPINGS.keys())},
    }
    result = engine.apply_automated_fixes("rolemap-complete", scan_data)

    assert result.get("success"), result
    fixes_applied = result.get("fixesApplied") or []
    rolemap_fixes = [
        fix for fix in fixes_applied if fix.get("fixType") == "fixRoleMap" and fix.get("success")
    ]
    assert not rolemap_fixes
    assert result.get("successCount") == 0
