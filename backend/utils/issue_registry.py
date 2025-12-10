"""Canonical issue registry for analyzer results.

Each issue is assigned a stable ``issueId`` so individual findings can be
referenced across multiple buckets without double-counting.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional


def _slug(value: str) -> str:
    """Return a lowercase slug with non-alphanumerics replaced by hyphens."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "issue"


def _normalize_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().lower()
    return (
        text.replace(" ", "")
        .replace("/", "")
        .replace(":", "-")
        .replace(".", "-")
    )


def _normalize_pages(pages: Optional[Iterable[Any]]) -> List[int]:
    if not pages:
        return []

    normalized: List[int] = []
    for page in pages:
        try:
            normalized.append(int(page))
        except Exception:
            continue

    return sorted(set(normalized))


def _page_token(pages: List[int]) -> Optional[str]:
    if not pages:
        return None
    unique = sorted(set(pages))
    if len(unique) == 1:
        return f"p{unique[0]}"

    first, last = unique[0], unique[-1]
    contiguous = unique == list(range(first, last + 1))
    if contiguous:
        return f"p{first}-{last}"

    limited = "_".join(str(num) for num in unique[:4])
    if len(unique) > 4:
        limited = f"{limited}_plus"
    return f"p{limited}"


def _normalize_extra(extra: Any) -> Optional[str]:
    if extra is None:
        return None
    if isinstance(extra, (int, float, str)):
        text = str(extra).strip()
        return text or None
    try:
        return json.dumps(extra, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(extra)


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


def build_issue_id(
    kind: str,
    *,
    criterion: Optional[str] = None,
    clause: Optional[str] = None,
    pages: Optional[Iterable[Any]] = None,
    extra: Optional[str] = None,
) -> str:
    """Return a deterministic issueId for a single scan."""
    parts: List[str] = [_slug(kind)]

    criterion_token = _normalize_code(criterion)
    clause_token = _normalize_code(clause)
    pages_token = _page_token(_normalize_pages(pages))
    extra_token = _normalize_extra(extra)

    if criterion_token:
        parts.append(criterion_token)
    if clause_token:
        parts.append(clause_token)
    if pages_token:
        parts.append(pages_token)
    if extra_token:
        parts.append(_short_hash(extra_token))

    return "-".join(parts)


class IssueRegistry:
    """Track canonical issues and avoid duplicates across buckets."""

    def __init__(self) -> None:
        self._issues: List[Dict[str, Any]] = []
        self._index: Dict[str, Dict[str, Any]] = {}

    def reset(self) -> None:
        self._issues = []
        self._index = {}

    def register_issue(
        self,
        *,
        kind: str,
        criterion: Optional[str],
        clause: Optional[str],
        pages: Optional[Iterable[Any]],
        use_pages_in_id: bool = True,
        severity: Optional[str],
        description: str,
        wcag_criteria: Optional[str] = None,
        pdfua_clause: Optional[str] = None,
        raw_source: Optional[str] = None,
        penalty_weight: Optional[Any] = None,
        meta: Optional[Dict[str, Any]] = None,
        extra: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Register or return an existing canonical issue."""
        pages_list = _normalize_pages(pages)
        issue_id = build_issue_id(
            kind,
            criterion=criterion,
            clause=clause or pdfua_clause,
            pages=pages_list if use_pages_in_id else [],
            extra=extra,
        )

        incoming: Dict[str, Any] = {
            "issueId": issue_id,
            "category": kind,
            "criterion": criterion,
            "clause": clause,
            "pages": pages_list,
            "severity": (severity or "medium") if severity else "medium",
            "description": description,
        }
        if wcag_criteria:
            incoming["wcagCriteria"] = wcag_criteria
        if pdfua_clause:
            incoming["pdfuaClause"] = pdfua_clause
        if raw_source:
            incoming["rawSource"] = raw_source
        if penalty_weight is not None:
            incoming["penaltyWeight"] = penalty_weight
        if meta:
            incoming["meta"] = dict(meta)

        existing = self._index.get(issue_id)
        if existing:
            self._merge_issue(existing, incoming)
            return existing

        self._issues.append(incoming)
        self._index[issue_id] = incoming
        return incoming

    def _merge_issue(self, target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        """Merge new context into an existing canonical issue."""
        incoming_pages = incoming.get("pages")
        target_pages = target.get("pages")
        if isinstance(incoming_pages, list):
            merged = set(target_pages or [])
            merged.update(incoming_pages)
            target["pages"] = sorted(merged)

        for key in (
            "criterion",
            "clause",
            "wcagCriteria",
            "pdfuaClause",
            "severity",
            "description",
            "rawSource",
            "penaltyWeight",
        ):
            if key not in target or not target.get(key):
                value = incoming.get(key)
                if value:
                    target[key] = value

        if isinstance(incoming.get("meta"), dict):
            target_meta = target.setdefault("meta", {})
            for key, value in incoming["meta"].items():
                target_meta.setdefault(key, value)

    @property
    def issues(self) -> List[Dict[str, Any]]:
        return list(self._issues)


__all__ = ["IssueRegistry", "build_issue_id"]
