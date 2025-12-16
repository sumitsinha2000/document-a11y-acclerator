"""
Normalization helpers to produce deterministic, snapshot-friendly scan payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

VOLATILE_KEY_NAMES = {
    "scanid",
    "id",
    "issueid",
    "fileid",
    "batchid",
    "groupid",
    "createdat",
    "updatedat",
    "timestamp",
    "created_at",
    "updated_at",
    "uuid",
}

ISSUE_LIST_KEYS = {
    "issues",
    "wcagIssues",
    "pdfuaIssues",
    "missingAltText",
    "missingMetadata",
    "untaggedContent",
    "poorContrast",
    "missingLanguage",
    "formIssues",
    "tableIssues",
    "structureIssues",
    "readingOrderIssues",
    "linkIssues",
    "pdfaIssues",
}


def normalize_scan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a deterministic, snapshot-friendly version of a scan payload:
    - Remove volatile IDs and timestamps
    - Sort issues and criteria summaries deterministically
    """
    source = payload if isinstance(payload, dict) else {}
    cleaned = _deep_clean(source)
    normalized = _sort_data(cleaned)
    return normalized if isinstance(normalized, dict) else {}


def _deep_clean(value: Any) -> Any:
    """Recursively remove volatile keys and normalize nested structures."""
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, nested_value in value.items():
            if _is_volatile_key(key):
                continue
            cleaned[key] = _deep_clean(nested_value)
        return cleaned
    if isinstance(value, list):
        return [_deep_clean(item) for item in value]
    return value


def _is_volatile_key(key: str) -> bool:
    normalized = key.replace("_", "").lower()
    return normalized in VOLATILE_KEY_NAMES


def _sort_data(value: Any, *, parent_key: str | None = None) -> Any:
    """Recursively sort issue lists and criteria summaries for determinism."""
    if isinstance(value, dict):
        sorted_dict: Dict[str, Any] = {}
        for key, nested_value in value.items():
            sorted_value = _sort_data(nested_value, parent_key=key)
            if key == "criteriaSummary":
                sorted_value = _sort_criteria_summary(sorted_value)
            sorted_dict[key] = sorted_value
        return sorted_dict
    if isinstance(value, list):
        sorted_list = [_sort_data(item, parent_key=parent_key) for item in value]
        if parent_key and _is_issue_list_key(parent_key):
            sorted_list = sorted(sorted_list, key=_issue_sort_key)
        return sorted_list
    return value


def _is_issue_list_key(key: str) -> bool:
    return key in ISSUE_LIST_KEYS or key.lower().endswith("issues")


def _issue_sort_key(item: Any) -> Any:
    if not isinstance(item, dict):
        return ("", "", 0, str(item))

    def _coerce_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    criterion = str(item.get("criterion") or "")
    code = str(item.get("code") or "")
    page_number = item.get("pageNumber", item.get("page", 0))
    message = str(item.get("message") or item.get("description") or "")

    return (criterion, code, _coerce_int(page_number), message)


def _sort_criteria_summary(criteria_summary: Any) -> Any:
    if not isinstance(criteria_summary, dict):
        return criteria_summary

    sorted_summary: Dict[str, Any] = {}
    for key, value in criteria_summary.items():
        if not isinstance(value, dict):
            sorted_summary[key] = value
            continue

        items = value.get("items")
        sorted_items = _sort_criteria_items(items)
        section = dict(value)
        if sorted_items is not None:
            section["items"] = sorted_items
        sorted_summary[key] = section

    return sorted_summary


def _sort_criteria_items(items: Any) -> Union[List[Any], None]:
    if not isinstance(items, (list, tuple)):
        return None

    sortable_items: List[Any] = []
    for item in items:
        sortable_items.append(_sort_data(item, parent_key="issues"))

    def _item_key(entry: Any) -> str:
        if not isinstance(entry, dict):
            return ""
        return str(entry.get("criterion") or entry.get("code") or "")

    return sorted(sortable_items, key=_item_key)
