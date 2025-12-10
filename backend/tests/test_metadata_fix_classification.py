"""
Tests that metadata-related fixes are routed to the correct buckets so guided remediation
for author/subject information only appears in the semi-automated list.
"""

from backend.auto_fix import AutoFixEngine as LegacyAutoFixEngine
from backend.auto_fix_engine import AutoFixEngine as ModernAutoFixEngine


def _build_issue(description: str, severity: str = "medium") -> dict:
    """Simple helper to produce a metadata issue payload."""
    return {"description": description, "severity": severity, "page": 1}


def test_auto_fix_engine_promotes_author_subject_to_semi() -> None:
    engine = ModernAutoFixEngine()
    scan_results = {
        "missingMetadata": [
            _build_issue("PDF is missing document title in metadata", "high"),
            _build_issue("PDF is missing author information", "medium"),
            _build_issue("PDF is missing subject/description", "low"),
        ]
    }

    fixes = engine.generate_fixes(scan_results)
    automated = [fix for fix in fixes.get("automated", []) if fix.get("category") == "missingMetadata"]
    semi = [fix for fix in fixes.get("semiAutomated", []) if fix.get("category") == "missingMetadata"]

    assert automated, "Title/general metadata issues should still produce an automated fix"
    assert all("author" not in fix.get("title", "").lower() for fix in automated)
    assert all("subject" not in fix.get("title", "").lower() for fix in automated)

    assert any("author" in fix.get("title", "").lower() for fix in semi)
    assert any("subject" in fix.get("title", "").lower() for fix in semi)


def test_legacy_auto_fix_honors_metadata_guidance() -> None:
    engine = LegacyAutoFixEngine()
    issues = {
        "missingMetadata": [
            _build_issue("PDF is missing document title in metadata", "high"),
            _build_issue("PDF is missing author information", "medium"),
            _build_issue("PDF is missing subject/description", "low"),
        ]
    }

    fixes = engine.generate_fixes(issues)
    automated = fixes.get("automated", [])
    semi = fixes.get("semiAutomated", [])

    assert automated, "Automated metadata fix should remain if title/general metadata problems exist"
    assert all("author" not in fix.get("action", "").lower() for fix in automated)
    assert all("subject" not in fix.get("action", "").lower() for fix in automated)

    assert any("author" in fix.get("action", "").lower() for fix in semi)
    assert any("subject" in fix.get("action", "").lower() for fix in semi)
