"""Debug helpers for inspecting persisted scan_results payloads."""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from backend.utils.app_helpers import (
    SafeJSONResponse,
    _parse_scan_results_json,
    derive_file_status,
    get_db_connection,
)

logger = logging.getLogger("doca11y-debug-scans")

router = APIRouter(prefix="/api/debug/scan", tags=["debug"])


def _status_code_from_summary(summary: dict, raw_status: Optional[str]) -> str:
    """Derive the status code using the same helper as other routes."""
    issues_remaining = summary.get("issuesRemaining", summary.get("remainingIssues"))
    status_code, _ = derive_file_status(
        raw_status,
        issues_remaining=issues_remaining,
        summary_status=summary.get("status"),
    )
    return status_code


@router.get("/{scan_id}")
async def get_scan_debug(scan_id: str):
    """
    Show the persisted scan_results payload along with the derived status code.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT id, group_id, batch_id, status, scan_results
            FROM scans
            WHERE id = %s
            """,
            (scan_id,),
        )
        row = cursor.fetchone()
        if not row:
            return JSONResponse(
                {"error": f"Scan {scan_id} not found"}, status_code=404
            )

        row_dict = dict(row)
        scan_results = _parse_scan_results_json(row_dict.get("scan_results"))
        summary = scan_results.get("summary", {})
        response_payload = {
            "scanId": row_dict.get("id"),
            "groupId": row_dict.get("group_id") or row_dict.get("groupId"),
            "folderId": row_dict.get("batch_id")
            or row_dict.get("folder_id")
            or row_dict.get("batchId")
            or row_dict.get("folderId"),
            "statusCode": _status_code_from_summary(summary, row_dict.get("status")),
            "rawSummaryCompliance": summary.get("complianceScore"),
            "wcagCompliance": summary.get("wcagCompliance"),
            "pdfuaCompliance": summary.get("pdfuaCompliance"),
            "rawSummary": summary,
            "rawScanResults": scan_results,
        }
        return SafeJSONResponse(response_payload)
    except Exception:
        logger.exception("doca11y-backend:debug_scan error")
        return JSONResponse(
            {"error": f"Failed to fetch debug info for scan {scan_id}"},
            status_code=500,
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
