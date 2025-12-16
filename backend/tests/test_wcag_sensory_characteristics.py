"""
Regression tests for WCAG 1.3.3 (Sensory Characteristics).

The validator should flag instructions that depend only on color/position cues
and stay silent when instructions already provide non-visual references.
"""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.wcag_validator import WCAGValidator


def _write_pdf_with_lines(dest: Path, lines) -> Path:
    """
    Create a minimal PDF with the provided text lines so pdfplumber can extract them.
    We emit literal `Tj` operators so the text ends up in the content stream and is
    therefore discoverable by the validator's pdfplumber run.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    content_parts = []
    y = 720
    for line in lines:
        content_parts.append(f"BT /F1 12 Tf 72 {y} Td ({line}) Tj ET")
        y -= 18

    stream = DecodedStreamObject()
    stream.set_data("\n".join(content_parts).encode("utf-8"))
    stream_ref = writer._add_object(stream)
    page[NameObject("/Contents")] = stream_ref

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject()
    fonts_dict = DictionaryObject()
    fonts_dict[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts_dict
    page[NameObject("/Resources")] = resources

    with dest.open("wb") as handle:
        writer.write(handle)

    return dest


def _wcag_criteria(results):
    """Return the list of WCAG criterion codes reported by the validator."""
    issues = results.get("wcagIssues") or []
    return [str(issue.get("criterion")) for issue in issues if issue.get("criterion")]


def test_sensory_instructions_raise_wcag_133(tmp_path: Path):
    """Sensory-only instructions should trigger a WCAG 1.3.3 Level A issue."""
    pdf_path = _write_pdf_with_lines(
        tmp_path / "sensory.pdf",
        [
            "Click the red button above to continue.",
            "See the green icon on the right to proceed.",
        ],
    )

    validator = WCAGValidator(str(pdf_path))
    results = validator.validate()

    wcag_issues = results.get("wcagIssues") or []
    sensory_issues = [issue for issue in wcag_issues if str(issue.get("criterion")) == "1.3.3"]

    assert sensory_issues, "Expected at least one WCAG 1.3.3 issue for sensory-only instructions"
    assert all(issue.get("level") == "A" for issue in sensory_issues), "WCAG 1.3.3 issues must be Level A"


def test_non_sensory_instructions_do_not_raise_wcag_133(tmp_path: Path):
    """Instructions that include textual references should not trip WCAG 1.3.3."""
    pdf_path = _write_pdf_with_lines(
        tmp_path / "nonsensory.pdf",
        [
            "Select the option labeled Start to continue.",
            "Press Submit when you are finished.",
        ],
    )

    validator = WCAGValidator(str(pdf_path))
    results = validator.validate()

    criteria = _wcag_criteria(results)
    assert "1.3.3" not in criteria, "Non-sensory instructions should not trigger WCAG 1.3.3 findings"
