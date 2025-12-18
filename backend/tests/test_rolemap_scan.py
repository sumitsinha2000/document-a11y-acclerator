import shutil
from pathlib import Path

import pikepdf

from backend.fix_suggestions import generate_fix_suggestions
from backend.matterhorn_protocol import MatterhornProtocol
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.pdf_structure_standards import COMMON_ROLEMAP_MAPPINGS


_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"
)


def _ensure_struct_tree(pdf):
    struct_tree = getattr(pdf.Root, "StructTreeRoot", None)
    if not struct_tree:
        pdf.Root.StructTreeRoot = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot"))
        )
        struct_tree = pdf.Root.StructTreeRoot
    if not hasattr(struct_tree, "K"):
        struct_tree.K = pdf.make_indirect(pikepdf.Array())
    return struct_tree


def _make_rolemap_fixture(tmp_path: Path, filename: str, mapping: dict) -> Path:
    """Copy a base fixture and apply a provided RoleMap mapping."""
    working_pdf = tmp_path / filename
    shutil.copyfile(_FIXTURE, working_pdf)

    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        struct_tree = _ensure_struct_tree(pdf)
        struct_tree.RoleMap = pdf.make_indirect(pikepdf.Dictionary(mapping))
        pdf.save(working_pdf)

    return working_pdf


def test_scan_surfaces_rolemap_missing_mappings(tmp_path):
    working_pdf = tmp_path / "rolemap_scan.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)

    custom_type = "/Heading"
    expected_standard = COMMON_ROLEMAP_MAPPINGS[custom_type]

    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        struct_tree = _ensure_struct_tree(pdf)
        struct_tree.RoleMap = pdf.make_indirect(
            pikepdf.Dictionary({custom_type: "/Div"})
        )
        pdf.save(working_pdf)

    analyzer = PDFAccessibilityAnalyzer()
    results = analyzer.analyze(str(working_pdf))

    missing_rolemap_entries = results.get("roleMapMissingMappings")
    assert isinstance(missing_rolemap_entries, list) and missing_rolemap_entries, (
        "RoleMap detection should surface missing or incorrect mappings"
    )
    recorded_pairs = {(entry.get("from"), entry.get("to")) for entry in missing_rolemap_entries}
    assert (custom_type, expected_standard) in recorded_pairs

    fixes = generate_fix_suggestions(results)
    automated = fixes.get("automated") or []
    rolemap_fixes = [fix for fix in automated if fix.get("fixType") == "fixRoleMap"]
    assert len(rolemap_fixes) == 1
    assert rolemap_fixes[0].get("category") == "structure"


def test_scan_reports_rolemap_cycle(tmp_path):
    working_pdf = tmp_path / "rolemap_cycle.pdf"
    shutil.copyfile(_FIXTURE, working_pdf)

    with pikepdf.open(working_pdf, allow_overwriting_input=True) as pdf:
        struct_tree = _ensure_struct_tree(pdf)
        struct_tree.RoleMap = pdf.make_indirect(
            pikepdf.Dictionary({
                "/CustomA": "/CustomB",
                "/CustomB": "/CustomC",
                "/CustomC": "/CustomA",
            })
        )
        pdf.save(working_pdf)

    analyzer = PDFAccessibilityAnalyzer()
    results = analyzer.analyze(str(working_pdf))

    pdfua_issues = results.get("pdfuaIssues") or []
    cycle_issues = [
        issue for issue in pdfua_issues
        if str(issue.get("findingId")) == "pdfua.rolemap.circular"
        or "circular rolemap" in str(issue.get("description", "")).lower()
    ]
    assert cycle_issues, "Circular RoleMap mappings should surface as PDF/UA issues"
    cycle_issue = cycle_issues[0]
    assert cycle_issue.get("matterhornId") == "02-003"
    assert "CustomA" in (cycle_issue.get("details") or "")


def test_rolemap_cycle_fail_and_pass_paths(tmp_path):
    fail_pdf = _make_rolemap_fixture(
        tmp_path,
        "rolemap_cycle_fail.pdf",
        {"/TagA": "/TagB", "/TagB": "/TagA"},
    )
    pass_pdf = _make_rolemap_fixture(
        tmp_path,
        "rolemap_cycle_pass.pdf",
        {"/MyPara": "/P", "/MySpan": "/Span"},
    )

    fail_results = PDFAccessibilityAnalyzer().analyze(str(fail_pdf))
    pass_results = PDFAccessibilityAnalyzer().analyze(str(pass_pdf))

    fail_pdfua = fail_results.get("pdfuaIssues") or []
    cycle_issue = next(
        (issue for issue in fail_pdfua if issue.get("findingId") == "pdfua.rolemap.circular"),
        None,
    )
    assert cycle_issue is not None, "Circular RoleMap should emit pdfua.rolemap.circular finding"
    assert cycle_issue.get("cyclePath") == ["/TagA", "/TagB", "/TagA"]
    assert "/TagA -> /TagB" in (cycle_issue.get("description") or "")

    pass_pdfua = pass_results.get("pdfuaIssues") or []
    assert not any(issue.get("findingId") == "pdfua.rolemap.circular" for issue in pass_pdfua), (
        "Terminating RoleMap chains should not emit circular findings"
    )


def test_matterhorn_protocol_detects_rolemap_cycles(tmp_path):
    fail_pdf = _make_rolemap_fixture(
        tmp_path,
        "matterhorn_rolemap_cycle_fail.pdf",
        {"/TagA": "/TagB", "/TagB": "/TagA"},
    )
    pass_pdf = _make_rolemap_fixture(
        tmp_path,
        "matterhorn_rolemap_cycle_pass.pdf",
        {"/MyPara": "/P"},
    )

    with pikepdf.open(fail_pdf) as pdf:
        issues = MatterhornProtocol().validate(pdf)
    cycle_issue = next((issue for issue in issues if issue.get("checkpoint") == "02-003"), None)
    assert cycle_issue is not None, "Matterhorn protocol should emit checkpoint 02-003 for circular RoleMap"
    assert cycle_issue.get("roleMapCycle") == ["/TagA", "/TagB", "/TagA"]

    with pikepdf.open(pass_pdf) as pdf:
        pass_issues = MatterhornProtocol().validate(pdf)
    assert not any(issue.get("checkpoint") == "02-003" for issue in pass_issues)
