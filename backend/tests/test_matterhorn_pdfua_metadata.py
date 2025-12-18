import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

import pikepdf
import pytest

from backend.matterhorn_protocol import MatterhornProtocol
from backend.utils.metadata_helpers import ensure_pdfua_metadata_stream

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "pdfuaid": "http://www.aiim.org/pdfua/ns/id/",
}
BASE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "metadata" / "no_title_no_lang_untagged.pdf"


def _metadata_stream(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    """Return the catalog metadata stream and resolve indirect references."""
    metadata_obj = pdf.Root.Metadata
    if hasattr(metadata_obj, "get_object"):
        try:
            metadata_obj = metadata_obj.get_object()
        except Exception:
            pass
    return metadata_obj


def _strip_pdfua_identifier(pdf: pikepdf.Pdf) -> None:
    """Remove pdfuaid:part entries from the in-memory metadata stream."""
    metadata_obj = _metadata_stream(pdf)
    raw_xmp = metadata_obj.read_bytes()
    root = ET.fromstring(raw_xmp.decode("utf-8", errors="ignore"))
    description = root.find(".//rdf:Description", NS)
    if description is not None:
        description[:] = [
            child for child in list(description) if child.tag != f"{{{NS['pdfuaid']}}}part"
        ]
    metadata_obj.write(ET.tostring(root, encoding="utf-8"))


def _checkpoint_issues(issues):
    return [issue for issue in issues if issue.get("checkpoint") == "01-001"]


@pytest.fixture
def matterhorn_protocol() -> MatterhornProtocol:
    return MatterhornProtocol()


@pytest.fixture
def pdf_missing_metadata(tmp_path: Path) -> Path:
    dest = tmp_path / "missing_metadata.pdf"
    shutil.copyfile(BASE_FIXTURE, dest)
    return dest


@pytest.fixture
def pdf_with_metadata_missing_pdfuaid(tmp_path: Path) -> Path:
    dest = tmp_path / "metadata_missing_pdfuaid.pdf"
    shutil.copyfile(BASE_FIXTURE, dest)
    with pikepdf.open(dest, allow_overwriting_input=True) as pdf:
        ensure_pdfua_metadata_stream(pdf, title="Matterhorn Metadata Test")
        _strip_pdfua_identifier(pdf)
        pdf.save(dest)
    return dest


@pytest.fixture
def pdf_with_valid_pdfuaid(tmp_path: Path) -> Path:
    dest = tmp_path / "metadata_with_pdfuaid.pdf"
    shutil.copyfile(BASE_FIXTURE, dest)
    with pikepdf.open(dest, allow_overwriting_input=True) as pdf:
        ensure_pdfua_metadata_stream(pdf, title="Matterhorn Metadata Test")
        pdf.save(dest)
    return dest


def test_matterhorn_reports_missing_metadata_stream(pdf_missing_metadata: Path, matterhorn_protocol: MatterhornProtocol):
    with pikepdf.open(pdf_missing_metadata) as pdf:
        issues = matterhorn_protocol.validate(pdf)

    metadata_issues = _checkpoint_issues(issues)
    descriptions = [issue.get("description") for issue in metadata_issues]
    assert "Document does not contain an XMP metadata stream" in descriptions


def test_matterhorn_reports_missing_pdfua_identifier(
    pdf_with_metadata_missing_pdfuaid: Path, matterhorn_protocol: MatterhornProtocol
):
    with pikepdf.open(pdf_with_metadata_missing_pdfuaid) as pdf:
        issues = matterhorn_protocol.validate(pdf)

    metadata_issues = _checkpoint_issues(issues)
    descriptions = [issue.get("description") for issue in metadata_issues]
    assert (
        "The XMP metadata stream in the Catalog dictionary does not include the PDF/UA identifier"
        in descriptions
    )


def test_matterhorn_accepts_valid_pdfua_identifier(
    pdf_with_valid_pdfuaid: Path, matterhorn_protocol: MatterhornProtocol
):
    with pikepdf.open(pdf_with_valid_pdfuaid) as pdf:
        issues = matterhorn_protocol.validate(pdf)

    metadata_issues = _checkpoint_issues(issues)
    assert not metadata_issues, f"Unexpected metadata checkpoint failures: {metadata_issues}"
