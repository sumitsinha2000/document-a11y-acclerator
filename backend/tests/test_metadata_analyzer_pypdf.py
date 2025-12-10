from pathlib import Path
from typing import Dict, List, Any

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


# Directory containing the pre-generated catalog fixtures
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "metadata"


def _fixture_path(name: str) -> str:
    """Resolve a catalog fixture filename to an absolute path string."""
    path = _FIXTURE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Expected fixture not found: {path}")
    return str(path)


def _analyze_catalog_fixture(filename: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run the analyzer's PyPDF-based path against a single catalog fixture and
    return the issues dictionary. This targets the metadata/lang/tagging logic
    that will be exercised during the PyPDF2 → pypdf migration.
    """
    analyzer = PDFAccessibilityAnalyzer()

    # NOTE: Once the migration renames this helper (e.g. to _analyze_with_pypdf),
    # update this call in one place instead of every test.
    analyzer._analyze_with_pypdf2(_fixture_path(filename))

    return analyzer.issues


def test_untagged_pdf_emits_missing_title_lang_and_untagged_issue() -> None:
    """
    An untagged document with no /Title, no /Lang, and no tagging markers
    should report:
      - at least one missing-metadata issue (high severity),
      - at least one missing-language issue,
      - at least one untagged-content issue covering page 1.
    """
    issues = _analyze_catalog_fixture("no_title_no_lang_untagged.pdf")

    missing_metadata = issues.get("missingMetadata", [])
    missing_language = issues.get("missingLanguage", [])
    untagged_content = issues.get("untaggedContent", [])

    # We don't care exactly how many metadata sub-issues you emit, only that
    # the analyzer recognises the gap and treats it as serious.
    assert missing_metadata, "Expected at least one missingMetadata issue"
    assert any(issue.get("severity") == "high" for issue in missing_metadata), (
        "Expected at least one high-severity missingMetadata issue"
    )

    # Language should be flagged as missing at least once.
    assert missing_language, "Expected at least one missingLanguage issue"

    # Document should be treated as untagged, with page 1 implicated.
    assert untagged_content, "Expected at least one untaggedContent issue"
    pages = set(untagged_content[0].get("pages") or [])
    assert 1 in pages, "Expected page 1 to be marked as untagged"


def test_tagged_pdf_with_empty_title_emits_empty_title_not_missing_language_or_untagged() -> (
    None
):
    """
    A tagged PDF with /Lang set and an empty Info /Title should:
      - emit a missing/empty title issue,
      - NOT emit missingLanguage issues,
      - NOT emit generic untagged-content issues.
    """
    issues = _analyze_catalog_fixture("empty_title_tagged.pdf")

    missing_metadata = issues.get("missingMetadata", [])
    missing_language = issues.get("missingLanguage", [])
    untagged_content = issues.get("untaggedContent", [])

    # We expect at least one metadata issue corresponding to the empty title,
    # and we assert it is treated as high severity.
    assert missing_metadata, "Expected a missingMetadata issue for empty title"
    assert any(issue.get("severity") == "high" for issue in missing_metadata), (
        "Expected empty title to be treated as high severity"
    )

    # Because /Lang and tagging markers are present, these should be clean.
    assert missing_language == [], "Did not expect missingLanguage issues"
    assert untagged_content == [], "Did not expect untaggedContent issues"


def test_invalid_title_value_is_treated_as_missing_and_does_not_crash() -> None:
    """
    A PDF whose Info /Title is a non-string value (e.g. pikepdf.Array or Dictionary)
    should not crash the analyzer. Instead, it should be treated as missing/invalid
    metadata and generate at least one missingMetadata issue.
    """
    issues = _analyze_catalog_fixture("invalid_title_catalog.pdf")

    missing_metadata = issues.get("missingMetadata", [])

    # The core guarantee: no exception was raised and we have a metadata issue.
    assert missing_metadata, "Expected missingMetadata issues for invalid /Title value"
    assert any(issue.get("severity") == "high" for issue in missing_metadata), (
        "Expected invalid /Title to be treated as high severity"
    )


def test_lang_only_catalog_is_treated_as_untagged_but_not_missing_language() -> None:
    """
    A PDF whose catalog declares /Lang but lacks /MarkInfo and /StructTreeRoot
    should:
      - NOT emit missingLanguage issues (language is present),
      - STILL be treated as untagged content.
    """
    issues = _analyze_catalog_fixture("lang_only_untagged.pdf")

    missing_language = issues.get("missingLanguage", [])
    untagged_content = issues.get("untaggedContent", [])

    # /Lang is present, so we should not mark language as missing.
    assert missing_language == [], (
        "Did not expect missingLanguage issues when /Lang is present"
    )

    # But because tagging markers are absent, we still consider the document untagged.
    assert untagged_content, "Expected untaggedContent issues without tagging markers"
    pages = set(untagged_content[0].get("pages") or [])
    assert 1 in pages, "Expected page 1 to be marked as untagged in lang-only catalog"
