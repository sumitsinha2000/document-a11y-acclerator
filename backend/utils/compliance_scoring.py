"""Shared helpers for deriving compliance scores from analyzer output.

The custom WCAG validator feeds `results["wcagIssues"]` and the
`criteriaSummary` builder aggregates those findings by success criterion.
VeraPDF-style statistics (`verapdfStatus`) remain advisory – they may
surface additional context but must not override the main WCAG score.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from backend.utils.criteria_summary import build_criteria_summary

_SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 1.0,
    "medium": 0.75,
    "low": 0.45,
    "info": 0.15,
}


def derive_wcag_score(
    results: Optional[Dict[str, Any]],
    criteria_summary: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """
    Return a WCAG percentage derived from the grouped criteria summary.

    The calculation intentionally favors the richer WCAG validator output:
    - Each criterion starts at full credit (100% / total criteria).
    - Confirmed issues subtract weight based on severity/penalty.
    - Info-only advisories barely change the score so manual checks do not
      imply a total failure.
    """
    wcag_summary = None
    if isinstance(criteria_summary, dict):
        wcag_summary = criteria_summary.get("wcag")
    if not wcag_summary and isinstance(results, dict):
        derived = build_criteria_summary(results or {})
        wcag_summary = derived.get("wcag") if derived else None

    if not isinstance(wcag_summary, dict):
        return None

    items = wcag_summary.get("items") or []
    if not items:
        return 100.0

    total_criteria = len(items)
    penalty = 0.0
    for item in items:
        issues = item.get("issues") if isinstance(item, dict) else None
        penalty += _criterion_penalty(issues)

    normalized = max(0.0, (total_criteria - penalty) / total_criteria) * 100
    return round(normalized, 2)


def _criterion_penalty(issues: Optional[Iterable[Any]]) -> float:
    if not issues:
        return 0.0

    penalty = 0.0
    for issue in issues:
        penalty = max(penalty, _issue_penalty(issue))
    return min(penalty, 1.0)


def _issue_penalty(issue: Any) -> float:
    if not isinstance(issue, dict):
        return 0.5

    severity = str(issue.get("severity") or "").strip().lower()
    severity_weight = _SEVERITY_WEIGHTS.get(severity, _SEVERITY_WEIGHTS["medium"])

    penalty_weight = issue.get("penaltyWeight")
    normalized = 0.0
    if isinstance(penalty_weight, (int, float)):
        normalized = min(max(penalty_weight / 5.0, 0.05), 1.0)

    if severity == "info":
        return min(severity_weight, normalized or severity_weight)

    if normalized > 0:
        return max(normalized, severity_weight)
    return severity_weight


__all__ = ["derive_wcag_score"]
