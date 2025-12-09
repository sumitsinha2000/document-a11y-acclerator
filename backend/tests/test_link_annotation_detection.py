from pathlib import Path
from typing import Any, Dict, List

import pytest
from pypdf import PdfReader

from backend import wcag_validator


@pytest.fixture(scope="module")
def fixtures_dir() -> Path:
    """Return directory containing PDF fixtures."""
    return Path(__file__).resolve().parent / "fixtures"


def _require_fixture(fixtures_dir: Path, filename: str) -> Path:
    """Skip the test module when the requested fixture is missing."""
    pdf_path = fixtures_dir / filename
    if not pdf_path.exists():
        pytest.skip(f"Fixture PDF {filename} was not found at {pdf_path}")
    return pdf_path


@pytest.fixture(scope="module")
def link_fixture(fixtures_dir: Path) -> Path:
    """Provide the shared link annotation PDF used across tests."""
    return _require_fixture(fixtures_dir, "link_annotations.pdf")


def _annot_ref_to_dict(ref: Any) -> Dict[str, Any]:
    """Resolve a pypdf annotation reference to a dictionary-like object."""
    if hasattr(ref, "get_object"):
        try:
            resolved = ref.get_object()
        except Exception:
            return {}
    else:
        resolved = ref
    if isinstance(resolved, dict):
        return resolved
    return {}


def _collect_pypdf_annotation_summary(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Walk annotations through pypdf to mirror how PyPDF2 behaved pre-migration.
    Returns dictionaries describing subtype/content so that tests can compare
    with downstream WCAG validator results.
    """
    reader = PdfReader(str(pdf_path))
    summary: List[Dict[str, Any]] = []

    for page_index, page in enumerate(reader.pages, start=1):
        annotations = page.get("/Annots")
        if not annotations:
            continue
        if hasattr(annotations, "get_object"):
            annotations = annotations.get_object()
        if not isinstance(annotations, list):
            annotations = [annotations]

        for ref in annotations:
            annot = _annot_ref_to_dict(ref)
            subtype = str(annot.get("/Subtype"))
            contents = annot.get("/Contents")
            summary.append(
                {
                    "page": page_index,
                    "subtype": subtype,
                    "contents": str(contents).strip() if contents is not None else None,
                }
            )

    return summary


@pytest.mark.parametrize(
    "data_dict",
    [
        {"Subtype": "/Link"},
        {"/Subtype": "/Link"},
        {"subtype": "Link"},
    ],
)
def test_link_subtype_annotations_are_detected_across_key_variants(
    link_fixture: Path, data_dict: Dict[str, Any]
) -> None:
    validator = wcag_validator.WCAGValidator(str(link_fixture))
    annotation = {"data": data_dict}

    assert validator._annotation_is_link(annotation) is True


def test_non_link_annotations_are_ignored(link_fixture: Path) -> None:
    validator = wcag_validator.WCAGValidator(str(link_fixture))

    annotation = {"data": {"Subtype": "/Text"}}

    assert validator._annotation_is_link(annotation) is False


def test_walking_annotations_from_pypdf_reader_produces_same_wcag_issues(
    link_fixture: Path,
) -> None:
    annotations = _collect_pypdf_annotation_summary(link_fixture)
    link_annots = [annot for annot in annotations if annot.get("subtype") == "/Link"]
    text_annots = [annot for annot in annotations if annot.get("subtype") == "/Text"]

    # Fixture should expose two link annotations (generic text + icon) and a control /Text note.
    assert len(link_annots) == 2, "Expected two link annotations inside fixture PDF"
    assert text_annots, "Fixture should expose at least one /Text annotation for comparison"

    validator = wcag_validator.WCAGValidator(str(link_fixture))
    validator._validate_link_purposes()

    wcag_issues = [
        issue
        for issue in validator.issues.get("wcag", [])
        if issue.get("criterion") == "2.4.4"
    ]

    assert len(wcag_issues) == len(
        link_annots
    ), "Non-link annotations should not produce WCAG 2.4.4 findings"

    contexts = [
        (issue.get("context") or "").strip().lower()
        for issue in wcag_issues
        if issue.get("context")
    ]
    descriptions = [(issue.get("description") or "").lower() for issue in wcag_issues]

    assert any(
        context == "click here" for context in contexts
    ), "Generic 'click here' link should be called out explicitly"
    assert any(
        "lacks descriptive text" in description for description in descriptions
    ), "Icon-only link should trigger the missing description error"
