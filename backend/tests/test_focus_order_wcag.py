from typing import Dict, List, Sequence, Tuple

import pikepdf
import pytest

from backend.wcag_validator import WCAGValidator
from backend.utils.criteria_summary import build_criteria_summary


Rect = Tuple[float, float, float, float]


def _make_annotation(pdf: pikepdf.Pdf, subtype: str, rect: Rect) -> pikepdf.Object:
    """Create an indirect annotation with the given subtype and rectangle."""
    annot_dict = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/Annot"),
            "/Subtype": pikepdf.Name(f"/{subtype}"),
            "/Rect": pikepdf.Array(rect),
        }
    )
    return pdf.make_indirect(annot_dict)


def _add_page_with_annots(pdf: pikepdf.Pdf, rects: Sequence[Rect], subtypes: Sequence[str]) -> pikepdf.Page:
    """Add a page containing the provided annotations (ordered as supplied)."""
    page = pdf.add_blank_page(page_size=(300, 800))
    annots = pikepdf.Array()
    for rect, subtype in zip(rects, subtypes):
        annots.append(_make_annotation(pdf, subtype, rect))
    page.Annots = pdf.make_indirect(annots)
    return page


def _add_structure_tree(pdf: pikepdf.Pdf, entries: List[Tuple[pikepdf.Page, pikepdf.Object]]) -> None:
    """Attach a minimal structure tree that references the provided annotations in order."""
    struct_entries = []

    def _direct(obj: pikepdf.Object) -> pikepdf.Object:
        return getattr(obj, "obj", obj)

    for page, annot in entries:
        struct_entries.append(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/StructElem"),
                    "/S": pikepdf.Name("/Annot"),
                    "/Pg": _direct(page),
                    "/K": pikepdf.Dictionary(
                        {
                            "/Type": pikepdf.Name("/OBJR"),
                            "/Obj": _direct(annot),
                        }
                    ),
                }
            )
        )

    struct_tree = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pdf.make_indirect(pikepdf.Array(struct_entries)),
        }
    )
    pdf.Root.StructTreeRoot = pdf.make_indirect(struct_tree)


def _wcag_issues_for(pdf_path: str) -> List[Dict[str, str]]:
    validator = WCAGValidator(pdf_path)
    results = validator.validate()
    wcag_issues = results.get("wcagIssues") or []
    assert isinstance(wcag_issues, list)
    return wcag_issues


def _issues_for_criterion(issues: List[Dict[str, str]], criterion: str) -> List[Dict[str, str]]:
    return [issue for issue in issues if str(issue.get("criterion")) == criterion]


def test_focus_order_passes_with_logical_layout(tmp_path):
    pdf_path = tmp_path / "focus_pass.pdf"
    with pikepdf.new() as pdf:
        rects = [
            (50, 700, 100, 730),  # top-left
            (200, 700, 250, 730),  # top-right
            (50, 600, 100, 630),  # bottom-left
        ]
        subtypes = ["Widget", "Link", "Widget"]
        _add_page_with_annots(pdf, rects, subtypes)
        pdf.save(pdf_path)

    issues = _wcag_issues_for(str(pdf_path))
    focus_issues = _issues_for_criterion(issues, "2.4.3")
    assert not focus_issues, "Logical tab order should not raise WCAG 2.4.3 issues"


def test_focus_order_flags_non_linear_sequence(tmp_path):
    pdf_path = tmp_path / "focus_non_linear.pdf"
    with pikepdf.new() as pdf:
        rects = [
            (50, 700, 100, 730),  # left column top
            (50, 600, 100, 630),  # left column bottom
            (200, 700, 250, 730),  # right column top
        ]
        subtypes = ["Widget", "Widget", "Link"]
        page = _add_page_with_annots(pdf, rects, subtypes)
        page["/Tabs"] = pikepdf.Name("/C")  # Column order to force non-linear path
        pdf.save(pdf_path)

    issues = _wcag_issues_for(str(pdf_path))
    focus_issues = _issues_for_criterion(issues, "2.4.3")
    assert focus_issues, "Non-linear focus order should raise WCAG 2.4.3"
    assert all(issue.get("level") == "A" for issue in focus_issues)


def test_focus_order_flags_page_jump_in_structure(tmp_path):
    pdf_path = tmp_path / "focus_page_jump.pdf"
    with pikepdf.new() as pdf:
        page1_rects = [(50, 700, 100, 730), (60, 650, 110, 680)]
        page2_rects = [(50, 700, 100, 730)]
        page1 = _add_page_with_annots(pdf, page1_rects, ["Widget", "Link"])
        page2 = _add_page_with_annots(pdf, page2_rects, ["Widget"])

        # Structure order: page1 first annot -> page2 annot -> page1 second annot
        _add_structure_tree(
            pdf,
            [
                (page1, page1.Annots[0]),
                (page2, page2.Annots[0]),
                (page1, page1.Annots[1]),
            ],
        )
        pdf.save(pdf_path)

    issues = _wcag_issues_for(str(pdf_path))
    focus_issues = _issues_for_criterion(issues, "2.4.3")
    assert focus_issues, "Page jumps in focus order should raise WCAG 2.4.3"
    assert all(issue.get("level") == "A" for issue in focus_issues)


def test_focus_order_flags_structure_annotation_mismatch(tmp_path):
    pdf_path = tmp_path / "focus_structure_mismatch.pdf"
    with pikepdf.new() as pdf:
        rects = [
            (50, 700, 100, 730),  # first visually
            (200, 700, 250, 730),  # second visually
        ]
        page = _add_page_with_annots(pdf, rects, ["Widget", "Link"])

        # Structure order intentionally reversed relative to annotation order
        _add_structure_tree(
            pdf,
            [
                (page, page.Annots[1]),
                (page, page.Annots[0]),
            ],
        )
        pdf.save(pdf_path)

    issues = _wcag_issues_for(str(pdf_path))
    focus_issues = _issues_for_criterion(issues, "2.4.3")
    assert focus_issues, "Structure/annotation mismatch should raise WCAG 2.4.3"
    assert all(issue.get("level") == "A" for issue in focus_issues)


def test_focus_order_reports_each_inversion_with_context(tmp_path):
    pdf_path = tmp_path / "focus_multiple_inversions.pdf"
    with pikepdf.new() as pdf:
        rects = [
            (50, 720, 100, 750),  # top-left
            (200, 720, 250, 750),  # top-right
            (50, 620, 100, 650),  # bottom-left
            (200, 620, 250, 650),  # bottom-right
        ]
        page = _add_page_with_annots(pdf, rects, ["Widget", "Widget", "Link", "Widget"])
        page["/Tabs"] = pikepdf.Name("/S")

        # Structure order forces two inversions relative to visual order
        _add_structure_tree(
            pdf,
            [
                (page, page.Annots[2]),
                (page, page.Annots[0]),
                (page, page.Annots[3]),
                (page, page.Annots[1]),
            ],
        )
        pdf.save(pdf_path)

    issues = _wcag_issues_for(str(pdf_path))
    focus_issues = _issues_for_criterion(issues, "2.4.3")

    assert len(focus_issues) == 2, "Each focus inversion should emit a separate issue"
    assert all(issue.get("page") == 1 for issue in focus_issues)
    assert all(issue.get("context") for issue in focus_issues)

    summary = build_criteria_summary({"issues": issues})
    wcag_items = summary.get("wcag", {}).get("items", [])
    focus_item = next(item for item in wcag_items if item.get("code") == "2.4.3")
    assert focus_item["issueCount"] == 2
