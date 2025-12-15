import shutil
from pathlib import Path

import pikepdf

from backend.fix_suggestions import generate_fix_suggestions
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
