"""
Tests for the navigation aid checker that enforces WCAG 2.4.5 (Multiple Ways).

Each test builds a minimal PDF on the fly to keep the suite hermetic.
"""

from pathlib import Path
from typing import Callable, Optional

import pytest

pikepdf = pytest.importorskip("pikepdf")

from backend.navigation_aid_checker import check_navigation_aids


PdfMutator = Optional[Callable[[pikepdf.Pdf], None]]


def _build_pdf(path: Path, page_count: int, mutator: PdfMutator = None) -> Path:
    """Create a minimal PDF with blank pages and apply the optional mutator."""
    pdf = pikepdf.Pdf.new()
    for _ in range(page_count):
        pdf.add_blank_page(page_size=(612, 792))

    if mutator:
        mutator(pdf)

    pdf.save(path)
    return path


def _add_outline(pdf: pikepdf.Pdf) -> None:
    """Attach a single bookmark that targets the first page."""
    outlines = pdf.make_indirect(
        pikepdf.Dictionary({"/Type": pikepdf.Name("/Outlines"), "/Count": 1})
    )
    first_entry = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Title": pikepdf.String("Intro"),
                "/Dest": [pdf.pages[0].obj, pikepdf.Name("/XYZ"), 0, 0, 0],
            }
        )
    )
    first_entry["/Parent"] = outlines
    outlines["/First"] = first_entry
    outlines["/Last"] = first_entry
    pdf.Root["/Outlines"] = outlines


def _add_goto_link(pdf: pikepdf.Pdf) -> None:
    """Add a /GoTo annotation on the first page pointing to the second page."""
    if len(pdf.pages) < 2:
        raise ValueError("Need at least two pages for an internal link test.")

    annotation = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Annot"),
                "/Subtype": pikepdf.Name("/Link"),
                "/Rect": [0, 0, 10, 10],
                "/A": pikepdf.Dictionary(
                    {
                        "/S": pikepdf.Name("/GoTo"),
                        "/D": [pdf.pages[1].obj, pikepdf.Name("/XYZ"), 0, 0, 0],
                    }
                ),
            }
        )
    )

    page_obj = pdf.pages[0].obj
    annots = page_obj.get("/Annots")
    if not isinstance(annots, pikepdf.Array):
        annots = pikepdf.Array()
        page_obj["/Annots"] = annots
    annots.append(annotation)


def _add_page_labels(pdf: pikepdf.Pdf) -> None:
    """Attach a /PageLabels dictionary so custom labels are advertised."""
    labels = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Nums": [
                    0,
                    pikepdf.Dictionary(
                        {
                            "/S": pikepdf.Name("/D"),
                            "/P": pikepdf.String("Section "),
                        }
                    ),
                ]
            }
        )
    )
    pdf.Root["/PageLabels"] = labels


def _run_navigation_check(pdf_path: Path, **kwargs):
    """Helper to run the checker and return the parsed navigation aid flags."""
    result = check_navigation_aids(str(pdf_path), **kwargs)
    aids = result["navigation_aids"]
    return result, aids


def test_long_pdf_without_navigation_fails(tmp_path):
    """Long PDFs without any navigation aid must fail the check."""
    pdf_path = _build_pdf(tmp_path / "long_no_nav.pdf", page_count=12)
    result, aids = _run_navigation_check(pdf_path, length_threshold=10)

    assert result["page_count"] == 12
    assert result["status"] == "FAIL"
    assert not aids["outline"]
    assert not aids["table_of_contents_links"]
    assert not aids["page_labels"]


def test_long_pdf_with_bookmarks_passes(tmp_path):
    """Bookmarks/outlines alone are enough for long PDFs to pass."""
    pdf_path = _build_pdf(
        tmp_path / "long_with_bookmark.pdf",
        page_count=12,
        mutator=_add_outline,
    )
    result, aids = _run_navigation_check(pdf_path, length_threshold=10)

    assert result["page_count"] == 12
    assert result["status"] == "PASS"
    assert aids["outline"]
    assert not aids["table_of_contents_links"]
    assert not aids["page_labels"]


def test_long_pdf_with_goto_links_passes(tmp_path):
    """Internal /GoTo links on early pages should satisfy the requirement."""
    pdf_path = _build_pdf(
        tmp_path / "long_with_links.pdf",
        page_count=12,
        mutator=_add_goto_link,
    )
    result, aids = _run_navigation_check(pdf_path, length_threshold=10)

    assert result["page_count"] == 12
    assert result["status"] == "PASS"
    assert not aids["outline"]
    assert aids["table_of_contents_links"]
    assert not aids["page_labels"]


def test_long_pdf_with_page_labels_passes(tmp_path):
    """/PageLabels in the catalog count as a navigation aid."""
    pdf_path = _build_pdf(
        tmp_path / "long_with_page_labels.pdf",
        page_count=12,
        mutator=_add_page_labels,
    )
    result, aids = _run_navigation_check(pdf_path, length_threshold=10)

    assert result["page_count"] == 12
    assert result["status"] == "PASS"
    assert not aids["outline"]
    assert not aids["table_of_contents_links"]
    assert aids["page_labels"]


def test_short_pdf_without_navigation_passes(tmp_path):
    """Short PDFs (<= threshold) may pass even without explicit navigation aids."""
    pdf_path = _build_pdf(tmp_path / "short_no_nav.pdf", page_count=5)
    result, aids = _run_navigation_check(pdf_path, length_threshold=10)

    assert result["page_count"] == 5
    assert result["status"] == "PASS"
    assert not aids["outline"]
    assert not aids["table_of_contents_links"]
    assert not aids["page_labels"]


def test_custom_threshold_is_enforced(tmp_path):
    """Custom thresholds override the default and can force failures on medium PDFs."""
    pdf_path = _build_pdf(tmp_path / "medium_no_nav.pdf", page_count=8)
    result, aids = _run_navigation_check(pdf_path, length_threshold=5)

    assert result["page_count"] == 8
    assert result["status"] == "FAIL"
    assert not aids["outline"]
    assert not aids["table_of_contents_links"]
    assert not aids["page_labels"]
