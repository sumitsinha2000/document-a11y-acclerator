"""
Tests for PDF/UA metadata compliance:
Verifies the catalog metadata stream contains the PDF/UA identifier (pdfuaid:part=1).
"""

from __future__ import annotations

import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

import pikepdf
import pytest

from backend.utils.metadata_helpers import ensure_pdfua_metadata_stream
from backend.wcag_validator import WCAGValidator

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "pdfuaid": "http://www.aiim.org/pdfua/ns/id/",
}


# --- Helper utilities ---------------------------------------------------------

def extract_xmp_bytes(pdf_path: Path) -> bytes:
    """Return the raw XMP packet from the catalog /Metadata stream."""
    with pikepdf.open(pdf_path) as pdf:
        assert "/Metadata" in pdf.Root, "Expected catalog to expose /Metadata"
        metadata_obj = _metadata_stream(pdf)
        return bytes(metadata_obj.read_bytes())


def parse_xmp(xmp_bytes: bytes) -> ET.Element:
    """Parse XMP XML into an ElementTree root."""
    return ET.fromstring(xmp_bytes.decode("utf-8"))


def _rewrite_metadata(pdf: pikepdf.Pdf, xml_bytes: bytes) -> None:
    """Overwrite the catalog metadata stream with new XML."""
    metadata_obj = _metadata_stream(pdf)
    metadata_obj.write(xml_bytes)


def _metadata_stream(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    """Return the catalog metadata stream, resolving indirect references safely."""
    metadata_obj = pdf.Root.Metadata
    if hasattr(metadata_obj, "get_object"):
        try:
            metadata_obj = metadata_obj.get_object()
        except Exception:
            pass
    return metadata_obj


def _strip_pdfuaid_parts(pdf_path: Path, dest: Path) -> Path:
    """Produce a copy of pdf_path with pdfuaid:part removed."""
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        root = parse_xmp(bytes(_metadata_stream(pdf).read_bytes()))
        description = root.find(".//rdf:Description", NS)
        if description is not None:
            description[:] = [child for child in list(description) if child.tag != f"{{{NS['pdfuaid']}}}part"]
        _rewrite_metadata(pdf, ET.tostring(root, encoding="utf-8"))
        pdf.save(dest)
    return dest


def _duplicate_pdfuaid_part(pdf_path: Path, dest: Path) -> Path:
    """Produce a copy with multiple pdfuaid:part entries."""
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        root = parse_xmp(bytes(_metadata_stream(pdf).read_bytes()))
        description = root.find(".//rdf:Description", NS)
        duplicate = ET.Element(f"{{{NS['pdfuaid']}}}part")
        duplicate.text = "1"
        if description is None:
            description = ET.SubElement(root, f"{{{NS['rdf']}}}Description")
        description.append(duplicate)
        _rewrite_metadata(pdf, ET.tostring(root, encoding="utf-8"))
        pdf.save(dest)
    return dest


# --- Fixtures -----------------------------------------------------------------

@pytest.fixture
def base_fixture_pdf() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"


@pytest.fixture
def pdf_with_pdfuaid(tmp_path: Path, base_fixture_pdf: Path) -> Path:
    """Create a working PDF that has dc:title and pdfuaid:part=1 attached to the catalog."""
    working = tmp_path / "pdfuaid_positive.pdf"
    shutil.copyfile(base_fixture_pdf, working)
    with pikepdf.open(working, allow_overwriting_input=True) as pdf:
        ensure_pdfua_metadata_stream(pdf, title="Sample Fixture Title")
        pdf.save(working)
    return working


@pytest.fixture
def pdf_without_pdfuaid(tmp_path: Path, pdf_with_pdfuaid: Path) -> Path:
    """Copy with metadata present but without the pdfuaid:part identifier."""
    dest = tmp_path / "pdfuaid_missing.pdf"
    shutil.copyfile(pdf_with_pdfuaid, dest)
    return _strip_pdfuaid_parts(dest, dest)


@pytest.fixture
def pdf_with_duplicate_pdfuaid(tmp_path: Path, pdf_with_pdfuaid: Path) -> Path:
    """Copy with two pdfuaid:part elements to exercise duplicate detection."""
    dest = tmp_path / "pdfuaid_duplicate.pdf"
    shutil.copyfile(pdf_with_pdfuaid, dest)
    return _duplicate_pdfuaid_part(dest, dest)


# --- Tests --------------------------------------------------------------------

def test_catalog_metadata_entry_is_stream(pdf_with_pdfuaid: Path):
    """Catalog must have /Metadata and it must be a stream object."""
    with pikepdf.open(pdf_with_pdfuaid) as pdf:
        assert "/Metadata" in pdf.Root, "Catalog dictionary should expose /Metadata"
        metadata_obj = _metadata_stream(pdf)
        assert isinstance(metadata_obj, pikepdf.Stream), "Metadata entry must be a stream"


def test_xmp_contains_pdfua_namespace(pdf_with_pdfuaid: Path):
    """XMP must declare the pdfuaid namespace."""
    root = parse_xmp(extract_xmp_bytes(pdf_with_pdfuaid))
    namespaces = {
        elem.tag.split("}")[0].strip("{")
        for elem in root.iter()
        if elem.tag.startswith("{")
    }
    assert NS["pdfuaid"] in namespaces, "Expected pdfuaid namespace to be declared in XMP"


def test_xmp_contains_single_pdfua_part_value(pdf_with_pdfuaid: Path):
    """Exactly one pdfuaid:part tag with value '1' must be present."""
    root = parse_xmp(extract_xmp_bytes(pdf_with_pdfuaid))
    parts = root.findall(".//pdfuaid:part", NS)
    assert len(parts) == 1, f"Expected exactly one pdfuaid:part element, found {len(parts)}"
    assert (parts[0].text or "").strip() == "1", "pdfuaid:part must equal '1'"


def test_xmp_preserves_existing_fields(pdf_with_pdfuaid: Path):
    """Existing metadata (e.g., dc:title) must remain after adding PDF/UA identifier."""
    root = parse_xmp(extract_xmp_bytes(pdf_with_pdfuaid))
    titles = root.findall(".//dc:title", NS)
    assert titles, "dc:title should still be present in XMP metadata"
    # The dc:title element should include at least one language alternative entry.
    title_text = "".join((titles[0].itertext()))
    assert title_text.strip(), "dc:title text should not be empty"
    description = root.find(".//rdf:Description", NS)
    assert description is not None, "XMP Description node should still exist"
    assert len(description) >= 2, "Adding pdfuaid must not remove other metadata fields"


def test_validator_flags_missing_pdfua_identifier(pdf_without_pdfuaid: Path):
    """Validator should report when pdfuaid:part is absent."""
    validator = WCAGValidator(str(pdf_without_pdfuaid))
    results = validator.validate()
    pdfua_issues = results.get("pdfuaIssues") or []
    messages = " | ".join([issue.get("description", "") for issue in pdfua_issues])
    assert any("pdfuaid:part" in issue.get("description", "").lower() for issue in pdfua_issues), (
        f"Expected missing PDF/UA identifier issue; found: {messages}"
    )
    assert results.get("pdfuaCompliance") is False, "PDF/UA compliance should be false when identifier is missing"


def test_validator_flags_duplicate_pdfua_identifier(pdf_with_duplicate_pdfuaid: Path):
    """Validator should fail when multiple pdfuaid:part elements are present."""
    validator = WCAGValidator(str(pdf_with_duplicate_pdfuaid))
    results = validator.validate()
    pdfua_issues = results.get("pdfuaIssues") or []
    descriptions = " | ".join([issue.get("description", "") for issue in pdfua_issues])
    assert any("multiple" in issue.get("description", "").lower() for issue in pdfua_issues), (
        f"Expected duplicate PDF/UA identifier issue; found: {descriptions}"
    )
    assert results.get("pdfuaCompliance") is False, "PDF/UA compliance should be false when duplicates exist"
