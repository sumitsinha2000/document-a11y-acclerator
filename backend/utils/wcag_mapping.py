"""
Helpers for annotating analyzer issues with WCAG 2.1 success criterion details.
"""

from typing import Any, Dict, Iterable, List, Optional

LANGUAGE_FIX_NOTE = "Note: this tool will set the document language to 'en-US' by default when fixing this issue."

WCAG_CRITERIA_DETAILS: Dict[str, Dict[str, str]] = {
    "1.1.1": {
        "name": "Non-text Content",
        "level": "A",
        "summary": "Provide text alternatives for non-text content.",
    },
    "1.3.1": {
        "name": "Info and Relationships",
        "level": "A",
        "summary": "Preserve semantics so assistive technology can convey relationships.",
    },
    "1.3.2": {
        "name": "Meaningful Sequence",
        "level": "A",
        "summary": "Ensure reading order preserves intended meaning.",
    },
    "1.3.3": {
        "name": "Sensory Characteristics",
        "level": "A",
        "summary": "Instructions must not rely solely on color, shape, size, visual location, or sound cues.",
    },
    "1.4.3": {
        "name": "Contrast (Minimum)",
        "level": "AA",
        "summary": "Text/background contrast must be at least 4.5:1 for body text.",
    },
    "1.4.6": {
        "name": "Contrast (Enhanced)",
        "level": "AAA",
        "summary": "Enhanced 7:1 contrast aids users with low vision.",
    },
    "2.4.1": {
        "name": "Bypass Blocks",
        "level": "A",
        "summary": "Provide the ability to skip repeated content via clear headings or bookmarks.",
    },
    "2.4.2": {
        "name": "Page Titled",
        "level": "A",
        "summary": "Provide descriptive titles so users can identify content.",
    },
    "2.4.4": {
        "name": "Link Purpose (In Context)",
        "level": "AA",
        "summary": "Ensure link text, tooltips, or alt descriptions clearly explain the target destination.",
    },
    "2.4.6": {
        "name": "Headings and Labels",
        "level": "AA",
        "summary": "Use clear headings/labels for navigation.",
    },
    "3.1.1": {
        "name": "Language of Page",
        "level": "A",
        "summary": "Declare the primary language for pronunciation support.",
    },
    "3.3.2": {
        "name": "Labels or Instructions",
        "level": "A",
        "summary": "Provide instructions so users know required input.",
    },
    "4.1.2": {
        "name": "Name, Role, Value",
        "level": "A",
        "summary": "Expose UI semantics programmatically.",
    },
}

CATEGORY_CRITERIA_MAP: Dict[str, List[str]] = {
    "missingMetadata": ["2.4.2"],
    "missingLanguage": ["3.1.1"],
    "missingAltText": ["1.1.1"],
    "untaggedContent": ["1.3.1", "1.3.2"],
    "structureIssues": ["1.3.1", "2.4.6"],
    "readingOrderIssues": ["1.3.2"],
    "tableIssues": ["1.3.1"],
    "formIssues": ["3.3.2", "4.1.2"],
    "poorContrast": ["1.4.3", "1.4.6"],
    "linkIssues": ["2.4.4"],
}


def _format_single_criterion(code: str, fallback_level: Optional[str] = None) -> Optional[str]:
    """Return a human-friendly label for a WCAG success criterion code."""
    if not code:
        return None

    normalized = code.strip()
    details = WCAG_CRITERIA_DETAILS.get(normalized)
    level = fallback_level or (details.get("level") if details else None)
    level_text = f" (Level {level.upper()})" if level else ""

    if details:
        summary = f" – {details['summary']}" if details.get("summary") else ""
        return f"{normalized} {details['name']}{level_text}{summary}"

    return f"{normalized}{level_text}".strip()


def _format_criteria_list(criteria: Iterable[str]) -> str:
    """Combine multiple codes into a single readable string."""
    formatted = [label for code in criteria if (label := _format_single_criterion(code))]
    return "; ".join(formatted)


def _annotate_direct_wcag_issue(issue: Dict[str, Any]) -> None:
    """Attach formatted criterion info to a WCAG issue."""
    if not isinstance(issue, dict) or issue.get("wcagCriteria"):
        return

    criterion = issue.get("criterion")
    level = issue.get("level")
    formatted = _format_single_criterion(criterion, level)
    if formatted:
        issue["wcagCriteria"] = formatted


def _append_language_fix_note(issue: Dict[str, Any]) -> None:
    if not isinstance(issue, dict):
        return
    criterion = str(issue.get("criterion") or "").strip()
    if criterion != "3.1.1":
        return
    recommendation = str(issue.get("recommendation", "")).strip()
    if LANGUAGE_FIX_NOTE in recommendation:
        return
    separator = " " if recommendation else ""
    issue["recommendation"] = f"{recommendation}{separator}{LANGUAGE_FIX_NOTE}".strip()


def annotate_wcag_mappings(results: Any) -> Any:
    """
    Ensure issue lists contain human-friendly WCAG mapping metadata.

    Args:
        results: Analyzer results with categorized issue arrays.

    Returns:
        Same structure with wcagCriteria strings populated when possible.
    """
    if not isinstance(results, dict):
        return results

    for category, issues in results.items():
        if not isinstance(issues, list):
            continue

        if category == "wcagIssues":
            for issue in issues:
                if isinstance(issue, dict):
                    _annotate_direct_wcag_issue(issue)
                    _append_language_fix_note(issue)
            continue

        mapped_codes = CATEGORY_CRITERIA_MAP.get(category)
        if not mapped_codes:
            continue

        mapping_text = _format_criteria_list(mapped_codes)
        if not mapping_text:
            continue

        for issue in issues:
            if isinstance(issue, dict) and not issue.get("wcagCriteria"):
                issue["wcagCriteria"] = mapping_text
            if isinstance(issue, dict):
                _append_language_fix_note(issue)

    return results
