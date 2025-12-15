"""
Utilities for aligning applied fixes with their originating suggestions.

Each automated remediation step is linked to the suggestion (criterion/clause)
that justified the fix so audit logs, UI, and history entries remain traceable.
"""

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


# Maps auto-fix execution identifiers to their canonical suggestion metadata. This
# keeps a single source of truth for traceability across legacy and modern fix
# engines without changing how the fixes run.
AUTOFIX_SUGGESTION_MAP: Dict[str, Dict[str, Any]] = {
    "addLanguage": {
        "fixType": "addLanguage",
        "category": "language",
        "matchIds": {"fix-language", "set-language"},
        "matchCategories": {"language", "missinglanguage"},
        "defaultCriterion": "3.1.1",
    },
    "addTitle": {
        "fixType": "addTitle",
        "category": "metadata",
        "matchIds": {
            "wcag-title-info",
            "wcag-metadata",
            "add-metadata-title",
            "add-metadata",
        },
        "matchCategories": {"metadata", "missingmetadata"},
    },
    "addMetadata": {
        "fixType": "addMetadata",
        "category": "metadata",
        "matchIds": {"add-metadata", "wcag-metadata"},
        "matchCategories": {"metadata", "missingmetadata"},
    },
    "markTagged": {
        "fixType": "markTagged",
        "category": "structure",
        "matchIds": {"tag-content", "fix-structure", "pdfua-structure-tree"},
        "matchCategories": {"structure", "structureissues", "untaggedcontent"},
        # Validation-only step; suggestion generator never lists "already tagged"
        # so this mapping only exists to categorize implicit behavior.
    },
    "fixViewerPreferences": {
        "fixType": "fixViewerPreferences",
        "category": "metadata",
        "matchCategories": {"viewerpreferencesissues", "metadata", "pdfuaissues"},
    },
    "createStructureTree": {
        "fixType": "fixRoleMap",
        "category": "structure",
        "matchIds": {"pdfua-structure-tree", "fix-rolemap-1", "fix-rolemap"},
        "matchCategories": {"structure", "structureissues", "pdfuaissues"},
        "matchFixTypes": {"fixrolemap"},
        # RoleMap enhancements now rely on real suggestions; keep the mapping so traceability
        # still binds to the structure bucket.
    },
    "fixRoleMap": {
        "fixType": "fixRoleMap",
        "category": "structure",
        "matchIds": {"fix-rolemap-1", "fix-rolemap"},
        "matchCategories": {"structure", "rolemapissues"},
        "matchFixTypes": {"fixrolemap"},
    },
    "pdfuaNotice": {
        "fixType": "pdfuaNotice",
        "category": "pdfuaIssues",
        "matchCategories": {"pdfuaissues"},
        "defaultClause": "PDF/UA",
    },
}


def get_canonical_fix_type(fix_key: str) -> str:
    metadata = AUTOFIX_SUGGESTION_MAP.get(fix_key, {})
    return metadata.get("fixType") or fix_key


def _normalize_iterable(values: Iterable[str]) -> Set[str]:
    return {_normalize_value(value) for value in values if value}


def _derive_fix_type_from_suggestion(suggestion: Dict[str, Any]) -> Optional[str]:
    explicit = suggestion.get("fixType")
    if explicit:
        return str(explicit)

    normalized_id = _normalize_value(suggestion.get("id"))
    normalized_id_base = normalized_id
    if normalized_id and normalized_id.split("-")[-1].isdigit():
        normalized_id_base = "-".join(normalized_id.split("-")[:-1]) or normalized_id
    normalized_action = _normalize_value(suggestion.get("action"))
    normalized_category = _normalize_value(suggestion.get("category"))

    for fix_key, metadata in AUTOFIX_SUGGESTION_MAP.items():
        canonical = _normalize_value(metadata.get("fixType") or fix_key)
        if normalized_id:
            desired_ids = _normalize_iterable(metadata.get("matchIds", []))
            if normalized_id in desired_ids or normalized_id_base in desired_ids:
                return metadata.get("fixType") or fix_key
            if normalized_id == canonical:
                return metadata.get("fixType") or fix_key
        if normalized_action and normalized_action in _normalize_iterable(
            metadata.get("matchActions", [])
        ):
            return metadata.get("fixType") or fix_key
        if normalized_category and normalized_category in _normalize_iterable(
            metadata.get("matchCategories", [])
        ):
            return metadata.get("fixType") or fix_key
        if normalized_action and normalized_action == canonical:
            return metadata.get("fixType") or fix_key

    if normalized_id:
        return suggestion.get("id")
    if normalized_action:
        return suggestion.get("action")
    return None


def derive_allowed_fix_types(suggestions: Dict[str, Any]) -> Set[str]:
    automated = suggestions.get("automated") or []
    allowed: Set[str] = set()
    for suggestion in automated:
        if not isinstance(suggestion, dict):
            continue
        fix_type = _derive_fix_type_from_suggestion(suggestion)
        if fix_type:
            allowed.add(_normalize_value(fix_type))
    return allowed


def count_successful_fixes(fixes: Any) -> int:
    if not isinstance(fixes, list):
        return 0
    count = 0
    for fix in fixes:
        if isinstance(fix, dict):
            if fix.get("skipped"):
                continue
            if fix.get("implicit"):
                continue
            if fix.get("success", True) is False:
                continue
            count += 1
        else:
            # Legacy string-based entries count as successful fixes when no metadata is available.
            count += 1
    return count


class FixTraceabilityFormatter:
    """Provides normalized fix entries linked back to fix suggestions."""

    def __init__(self, suggestion_payload: Optional[Dict[str, Any]] = None):
        self.suggestions = suggestion_payload or {}
        self._flat_suggestions = self._flatten_suggestions(self.suggestions)
        self._fallback_counters: Dict[str, int] = defaultdict(int)
        self._used_orders: Set[int] = set()

    @staticmethod
    def _normalize(value: Any) -> str:
        return _normalize_value(value)

    def _flatten_suggestions(self, suggestions: Dict[str, Any]) -> List[Dict[str, Any]]:
        flat = []
        order = 0
        for bucket in ("automated", "semiAutomated", "manual"):
            for suggestion in suggestions.get(bucket, []) or []:
                order += 1
                flat.append(
                    {
                        "bucket": bucket,
                        "order": order,
                        "suggestion": suggestion,
                        "normalizedId": self._normalize(suggestion.get("id")),
                        "normalizedCategory": self._normalize(
                            suggestion.get("category")
                        ),
                        "normalizedFixType": self._normalize(
                            suggestion.get("fixType")
                        ),
                        "normalizedAction": self._normalize(
                            suggestion.get("action")
                        ),
                    }
                )
        return flat

    def _build_fallback_id(self, base_fix_type: str) -> str:
        normalized = self._normalize(base_fix_type) or "fix"
        self._fallback_counters[normalized] += 1
        return f"{normalized}-{self._fallback_counters[normalized]}"

    def _match_suggestion(
        self, fix_key: str, metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        priorities = [
            ("matchIds", "normalizedId"),
            ("matchFixTypes", "normalizedFixType"),
            ("matchActions", "normalizedAction"),
            ("matchCategories", "normalizedCategory"),
        ]
        for mapping_key, attr in priorities:
            desired = _normalize_iterable(metadata.get(mapping_key, []))
            if not desired:
                continue
            for entry in self._flat_suggestions:
                if entry["order"] in self._used_orders:
                    continue
                value = entry.get(attr)
                if value and value in desired:
                    self._used_orders.add(entry["order"])
                    return entry

        # Fall back to a direct fixType/action match if the suggestion payload
        # already provides canonical names.
        normalized_fix_type = self._normalize(metadata.get("fixType") or fix_key)
        for entry in self._flat_suggestions:
            if entry["order"] in self._used_orders:
                continue
            if entry["normalizedFixType"] == normalized_fix_type:
                self._used_orders.add(entry["order"])
                return entry
            if entry["normalizedAction"] == normalized_fix_type:
                self._used_orders.add(entry["order"])
                return entry
        return None

    def build_entry(
        self,
        fix_key: str,
        description: str,
        success: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata = AUTOFIX_SUGGESTION_MAP.get(fix_key, {})
        canonical_fix_type = metadata.get("fixType") or fix_key
        default_category = metadata.get("category") or "unknown"
        entry: Dict[str, Any] = {
            "type": fix_key,
            "fixType": canonical_fix_type,
            "description": description,
            "success": success,
        }
        payload_extra = dict(extra) if extra else None
        skip_match = bool(payload_extra and payload_extra.pop("skipSuggestionLink", None))
        suggestion_entry = None if skip_match else self._match_suggestion(fix_key, metadata)
        if suggestion_entry:
            suggestion = suggestion_entry["suggestion"]
            entry["category"] = suggestion.get("category") or default_category
            entry["suggestionId"] = suggestion.get("id") or self._build_fallback_id(
                canonical_fix_type
            )
            if suggestion.get("criterion"):
                entry["criterion"] = suggestion.get("criterion")
            if suggestion.get("clause"):
                entry["clause"] = suggestion.get("clause")
            entry["suggestionRef"] = suggestion_entry["order"]
        else:
            entry["category"] = default_category
            if extra and extra.get("implicit"):
                entry["suggestionId"] = self._build_fallback_id(canonical_fix_type)
            else:
                entry["suggestionId"] = None
            if metadata.get("defaultCriterion"):
                entry["criterion"] = metadata["defaultCriterion"]
            if metadata.get("defaultClause"):
                entry["clause"] = metadata["defaultClause"]

        if payload_extra:
            entry.update(payload_extra)
        return entry
