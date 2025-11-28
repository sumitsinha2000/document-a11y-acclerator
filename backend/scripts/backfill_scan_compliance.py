"""Backfill scans whose stored summary compliance score differs from the computed value."""

import logging
from typing import Any, Dict

from ..utils.app_helpers import (
    execute_query,
    _parse_scan_results_json,
    _serialize_scan_results,
    _ensure_scan_results_compliance,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doca11y-backfill-compliance")

BACKFILL_QUERY = """
SELECT
    id,
    scan_results
FROM scans
WHERE scan_results->'summary' IS NOT NULL
  AND (scan_results->'summary'->>'complianceScore') = '0'
  AND (
        scan_results->'summary'->>'wcagCompliance' IS NOT NULL
     OR scan_results->'summary'->>'pdfuaCompliance' IS NOT NULL
  )
ORDER BY id
"""


def _update_row(scan_id: str, scan_results: Any) -> bool:
    parsed = _parse_scan_results_json(scan_results)
    if not isinstance(parsed, dict):
        return False

    before_score = parsed.get("summary", {}).get("complianceScore")
    normalized = _ensure_scan_results_compliance(parsed)
    after_score = normalized.get("summary", {}).get("complianceScore")
    if after_score is None or after_score == before_score:
        return False

    execute_query(
        "UPDATE scans SET scan_results=%s WHERE id=%s",
        (_serialize_scan_results(normalized), scan_id),
        fetch=False,
    )
    logger.info(
        "Adjusted scan %s complianceScore %s -> %s", scan_id, before_score, after_score
    )
    return True


def main():
    rows = execute_query(BACKFILL_QUERY, fetch=True) or []
    if not rows:
        logger.info("No scans qualify for the compliance backfill.")
        return

    updated = 0
    skipped_missing = 0
    for row in rows:
        scan_id = row.get("id")
        if not scan_id:
            continue

        try:
            if _update_row(scan_id, row.get("scan_results")):
                updated += 1
            else:
                skipped_missing += 1
        except Exception:
            logger.exception("Failed to backfill scan %s", scan_id)

    logger.info(
        "Backfill complete: %d rows updated, %d skipped", updated, skipped_missing
    )


if __name__ == "__main__":
    main()
