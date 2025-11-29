"""Helpers for deriving WCAG and PDF/UA criteria summaries from analyzer results."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.utils.wcag_mapping import WCAG_CRITERIA_DETAILS, CATEGORY_CRITERIA_MAP


LANGUAGE_FIX_NOTE = "Note: this tool will set the document language to 'en-US' by default when fixing this issue."

SEVERITY_SCORES = {
    "critical": 3,
    "high": 3,
    "medium": 2,
    "low": 1,
}

STATUS_FAIL = "doesNotSupport"
STATUS_PARTIAL = "partiallySupports"
STATUS_PASS = "supports"

WCAG_CRITERIA_ORDER = [
    "1.1.1",
    "1.3.1",
    "1.3.2",
    "1.4.3",
    "1.4.6",
    "2.4.1",
    "2.4.2",
    "2.4.4",
    "2.4.6",
    "3.1.1",
    "3.3.2",
    "4.1.2",
]

PDFUA_CLAUSE_DETAILS: Dict[str, Dict[str, str]] = {
    "ISO 14289-1:7.1": {
        "name": "Document Identification",
        "summary": "Metadata, tagging, and document title requirements.",
    },
    "ISO 14289-1:7.2": {
        "name": "Structure Tree",
        "summary": "Structure element semantics, RoleMap, and reading order.",
    },
    "ISO 14289-1:7.3": {
        "name": "Artifacts",
        "summary": "Artifacts must be separate from tagged content.",
    },
    "ISO 14289-1:7.4": {
        "name": "Headings",
        "summary": "Heading hierarchy and nesting rules.",
    },
    "ISO 14289-1:7.5": {
        "name": "Tables",
        "summary": "Tables require header associations and structure.",
    },
    "ISO 14289-1:7.18": {
        "name": "Forms & Alt Text",
        "summary": "Interactive elements need names and alternative text.",
    },
    "ISO 14289-1:7.18.1": {
        "name": "Annotations",
        "summary": "Annotations require Contents text for assistive tech.",
    },
}

PDFUA_CLAUSE_ORDER = [
    "ISO 14289-1:7.1",
    "ISO 14289-1:7.2",
    "ISO 14289-1:7.3",
    "ISO 14289-1:7.4",
    "ISO 14289-1:7.5",
    "ISO 14289-1:7.18",
    "ISO 14289-1:7.18.1",
]


def build_criteria_summary(results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return structured WCAG/PDF-UA criteria summaries for the provided scan results."""
    results = results or {}
    payload: Dict[str, Any] = {}

    wcag = _build_wcag_criteria(results)
    if wcag:
        payload["wcag"] = wcag

    pdfua = _build_pdfua_criteria(results)
    if pdfua:
        payload["pdfua"] = pdfua

    return payload


def _build_wcag_criteria(results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    wcag_issues = _collect_unique_issues(_collect_all_wcag_sources(results), key_field="criterion")

    grouped = _group_issues_by_code(wcag_issues, code_key="criterion")
    if not grouped and not wcag_issues:
        grouped = {}

    items = _build_items(
        grouped,
        WCAG_CRITERIA_DETAILS,
        WCAG_CRITERIA_ORDER,
        default_name="WCAG Criterion",
    )
    return {
        "items": items,
        "statusCounts": _count_statuses(items),
    }


def _collect_all_wcag_sources(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    direct_issues = results.get("wcagIssues")
    if isinstance(direct_issues, list):
        for issue in direct_issues:
            prepared = _copy_issue(issue)
            _append_language_note(prepared)
            collected.append(prepared)

    for category, codes in CATEGORY_CRITERIA_MAP.items():
        raw_issues = results.get(category)
        if not isinstance(raw_issues, list):
            continue
        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
            for code in codes:
                prepared = _copy_issue(issue)
                prepared["criterion"] = code
                _append_language_note(prepared)
                collected.append(prepared)
    return collected


def _build_pdfua_criteria(results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pdfua_issues = _collect_unique_issues(results.get("pdfuaIssues"), key_field="clause")
    grouped = _group_issues_by_code(pdfua_issues, code_key="clause")
    if not grouped and not pdfua_issues:
        return None

    items = _build_items(
        grouped,
        PDFUA_CLAUSE_DETAILS,
        PDFUA_CLAUSE_ORDER,
        default_name="PDF/UA Requirement",
    )
    return {
        "items": items,
        "statusCounts": _count_statuses(items),
    }


def _collect_unique_issues(issues: Optional[Iterable[Any]], key_field: str) -> List[Dict[str, Any]]:
    if not isinstance(issues, Iterable):
        return []

    collected: List[Dict[str, Any]] = []
    seen: set = set()

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = issue.get(key_field)
        if not code:
            continue
        normalized_code = str(code).strip()
        if not normalized_code:
            continue

        pages = issue.get("pages") if isinstance(issue.get("pages"), list) else None
        page_tuple = tuple(pages) if pages else tuple()
        key = (
            normalized_code,
            str(issue.get("description", "")).strip(),
            issue.get("page"),
            page_tuple,
            str(issue.get("context", "")).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        prepared = _copy_issue(issue)
        prepared[key_field] = normalized_code
        collected.append(prepared)

    return collected


def _copy_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy containing only serializable primitives."""
    allowed_keys = {
        "description",
        "criterion",
        "clause",
        "level",
        "severity",
        "recommendation",
        "remediation",
        "page",
        "pages",
        "count",
        "wcagCriteria",
        "category",
        "specification",
        "context",
        "title",
    }
    copied = {key: issue[key] for key in allowed_keys if key in issue}
    copied.setdefault("severity", issue.get("severity", "medium"))
    if "pages" in copied and not isinstance(copied["pages"], list):
        copied["pages"] = list(copied["pages"] or [])
    return copied


def _append_language_note(issue: Dict[str, Any]) -> None:
    if not isinstance(issue, dict):
        return
    if str(issue.get("criterion") or "").strip() != "3.1.1":
        return
    recommendation = str(issue.get("recommendation", "")).strip()
    if LANGUAGE_FIX_NOTE in recommendation:
        return
    separator = " " if recommendation else ""
    issue["recommendation"] = f"{recommendation}{separator}{LANGUAGE_FIX_NOTE}".strip()


def _group_issues_by_code(issues: List[Dict[str, Any]], code_key: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        code = issue.get(code_key)
        if not code:
            continue
        grouped.setdefault(code, []).append(issue)
    return grouped


def _build_items(
    grouped: Dict[str, List[Dict[str, Any]]],
    metadata: Dict[str, Dict[str, str]],
    order: List[str],
    *,
    default_name: str,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set = set()

    def _create_item(code: str, issues: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        info = metadata.get(code, {}) if metadata else {}
        return {
            "code": code,
            "name": info.get("name", default_name),
            "level": info.get("level"),
            "summary": info.get("summary"),
            "issues": issues or [],
            "issueCount": len(issues or []),
            "status": _determine_status(issues or []),
        }

    for code in order:
        seen.add(code)
        items.append(_create_item(code, grouped.get(code)))

    for code, issues in sorted(grouped.items(), key=lambda entry: entry[0]):
        if code in seen:
            continue
        seen.add(code)
        items.append(_create_item(code, issues))

    if not items:
        # Provide default ordered entries even when no issues exist to keep UI consistent.
        for code in order:
            items.append(_create_item(code, []))

    return items


def _determine_status(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return STATUS_PASS
    return STATUS_FAIL


def _count_statuses(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        STATUS_PASS: 0,
        STATUS_PARTIAL: 0,
        STATUS_FAIL: 0,
    }
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts
