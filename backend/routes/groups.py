"""Routes for group management."""

import logging
import uuid
from typing import Any, Dict, Optional

import psycopg2
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .validation import NAME_ALLOWED_MESSAGE, NAME_REGEX
from backend.utils.app_helpers import (
    SafeJSONResponse,
    _delete_batch_with_files,
    _delete_scan_with_files,
    _ensure_scan_results_compliance,
    _parse_scan_results_json,
    derive_file_status,
    execute_query,
    get_db_connection,
    remap_status_counts,
    update_group_file_count,
)

logger = logging.getLogger("doca11y-groups")

router = APIRouter(prefix="/api/groups", tags=["groups"])

MAX_GROUP_NAME_LENGTH = 50
DEFAULT_CATEGORY_KEY = "other"


def _normalize_category_key(value: Optional[Any]) -> str:
    if value is None:
        return DEFAULT_CATEGORY_KEY
    text = str(value).strip()
    return text or DEFAULT_CATEGORY_KEY


def _normalize_severity_key(value: Optional[Any]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"critical", "high"}:
        return "high"
    if normalized == "medium":
        return "medium"
    return "low"


def _build_issue_fallback_key(issue: Dict[str, Any]) -> Optional[str]:
    parts = []
    for field in ("category", "criterion", "clause", "description"):
        value = issue.get(field)
        if value:
            parts.append(str(value).strip().lower())
    pages = issue.get("pages")
    if isinstance(pages, list) and pages:
        parts.append(",".join(str(page) for page in pages))
    page = issue.get("page")
    if page:
        parts.append(f"p{page}")
    return "|".join(parts) if parts else None


def _accumulate_canonical_issue_stats(
    issues, category_totals: Dict[str, int], severity_totals: Dict[str, int]
) -> bool:
    if not isinstance(issues, (list, tuple)):
        return False

    handled = False
    seen_keys = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_key = issue.get("issueId") or _build_issue_fallback_key(issue)
        if issue_key:
            if issue_key in seen_keys:
                continue
            seen_keys.add(issue_key)
        category = _normalize_category_key(issue.get("category") or issue.get("rawSource"))
        category_totals[category] = category_totals.get(category, 0) + 1
        severity = _normalize_severity_key(issue.get("severity"))
        severity_totals[severity] = severity_totals.get(severity, 0) + 1
        handled = True
    return handled


class GroupPayload(BaseModel):
    name: str
    description: Optional[str] = ""


@router.get("")
async def get_groups():
    try:
        rows = execute_query(
            """
            SELECT g.id, g.name, g.description, g.created_at,
                   COALESCE(g.file_count, 0) AS file_count
            FROM groups g
            ORDER BY g.created_at DESC
            """,
            fetch=True,
        )
        groups = rows or []
        logger.info("[Backend] Returning %d groups", len(groups))
        return SafeJSONResponse({"groups": groups})
    except Exception as e:
        logger.exception("doca11y-backend:get_groups DB error")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/{group_id}/details")
async def get_group_details(group_id: str):
    """
    Returns group-level summary with total files, issues, and compliance averages.
    Used by GroupDashboard.jsx
    """
    try:
        update_group_file_count(group_id)
        group_rows = execute_query(
            """
            SELECT id, name, description, created_at
            FROM groups
            WHERE id = %s
            """,
            (group_id,),
            fetch=True,
        )
        if not group_rows:
            return JSONResponse(
                {"error": f"Group {group_id} not found"}, status_code=404
            )

        scans = (
            execute_query(
                """
            SELECT scan_results, status, COALESCE(issues_fixed, 0) AS issues_fixed
            FROM scans
            WHERE group_id = %s
            """,
                (group_id,),
                fetch=True,
            )
            or []
        )

        total_files = len(scans)
        total_issues = 0
        issues_fixed = 0
        total_compliance = 0
        scored_count = 0
        fixed_count = 0
        severity_totals = {"high": 0, "medium": 0, "low": 0}
        category_totals: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}

        for scan in scans:
            scan_results = _parse_scan_results_json(scan.get("scan_results"))
            if isinstance(scan_results, dict):
                scan_results = _ensure_scan_results_compliance(scan_results)
            else:
                scan_results = {}
            summary = scan_results.get("summary", {})
            results = scan_results.get("results", {})

            issues_remaining = summary.get(
                "issuesRemaining", summary.get("remainingIssues")
            )
            status_code, _ = derive_file_status(
                scan.get("status"),
                issues_remaining=issues_remaining,
                summary_status=summary.get("status"),
            )
            status_counts[status_code] = status_counts.get(status_code, 0) + 1

            total_issues += summary.get("totalIssues", 0)
            compliance_score = summary.get("complianceScore")
            has_valid_score = status_code != "uploaded" and compliance_score is not None
            if has_valid_score:
                total_compliance += compliance_score
                scored_count += 1

            scan_issues_fixed = scan.get("issues_fixed")
            if scan_issues_fixed is None:
                scan_issues_fixed = summary.get("issuesFixed")
            if scan_issues_fixed is None and issues_remaining is not None:
                total_for_scan = summary.get("totalIssues", 0) or 0
                scan_issues_fixed = max(total_for_scan - (issues_remaining or 0), 0)
            issues_fixed += scan_issues_fixed or 0

            if isinstance(results, dict):
                handled_canonical = False
                canonical_issues = results.get("issues")
                if isinstance(canonical_issues, list) and canonical_issues:
                    handled_canonical = _accumulate_canonical_issue_stats(
                        canonical_issues, category_totals, severity_totals
                    )

                if not handled_canonical:
                    for category, issues in results.items():
                        if category == "issues" or not isinstance(issues, list):
                            continue
                        normalized_category = _normalize_category_key(category)
                        category_totals[normalized_category] = (
                            category_totals.get(normalized_category, 0) + len(issues)
                        )
                        for issue in issues:
                            if not isinstance(issue, dict):
                                continue
                            severity = _normalize_severity_key(issue.get("severity"))
                            severity_totals[severity] = severity_totals.get(severity, 0) + 1

            if status_code == "fixed":
                fixed_count += 1

        avg_compliance = (
            round(total_compliance / scored_count, 2) if scored_count > 0 else 0
        )

        group = group_rows[0]
        total_severity_count = (
            severity_totals["high"] + severity_totals["medium"] + severity_totals["low"]
        )
        severity_gap = total_issues - total_severity_count
        if severity_gap > 0:
            severity_totals["low"] += severity_gap

        response = {
            "groupId": group["id"],
            "name": group["name"],
            "description": group.get("description", ""),
            "file_count": total_files,
            "total_issues": total_issues,
            "issues_fixed": issues_fixed,
            "avg_compliance": avg_compliance,
            "fixed_files": fixed_count,
            "category_totals": category_totals,
            "severity_totals": severity_totals,
            "status_counts": remap_status_counts(status_counts),
        }

        return SafeJSONResponse(response)
    except Exception:
        logger.exception("doca11y-backend:get_group_details DB error")
        return JSONResponse({"error": "Failed to fetch group details"}, status_code=500)


@router.get("/{group_id}/files")
async def get_group_files(group_id: str):
    """Get all files/scans for a specific group"""
    try:
        query = """
            SELECT id, filename, status, upload_date,
                   total_issues, issues_fixed, scan_results
            FROM scans
            WHERE group_id = %s
            ORDER BY upload_date DESC
        """
        rows = execute_query(query, (group_id,), fetch=True) or []

        files = []
        for row in rows:
            row_dict = dict(row)
            scan_results = _parse_scan_results_json(row_dict.get("scan_results") or {})
            summary = scan_results.get("summary", {})
            issues_remaining = summary.get(
                "issuesRemaining", summary.get("remainingIssues")
            )
            status_code, status_label = derive_file_status(
                row_dict.get("status"),
                issues_remaining=issues_remaining,
                summary_status=summary.get("status"),
            )
            files.append(
                {
                    "id": row_dict["id"],
                    "filename": row_dict["filename"],
                    "status": status_label,
                    "statusCode": status_code,
                    "uploadDate": row_dict.get("upload_date"),
                    "totalIssues": summary.get(
                        "totalIssues", row_dict.get("total_issues", 0)
                    ),
                    "issuesFixed": row_dict.get("issues_fixed", 0),
                    "complianceScore": summary.get("complianceScore", 0),
                }
            )

        return SafeJSONResponse({"files": files})
    except Exception as e:
        logger.exception("doca11y-backend:get_group_files error")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/{group_id}")
async def get_group(group_id: str):
    """Get group details with all scans"""
    try:
        update_group_file_count(group_id)
        query = """
            SELECT g.*, 
                   COUNT(s.id) AS file_count
            FROM groups g
            LEFT JOIN scans s ON g.id = s.group_id
            WHERE g.id = %s
            GROUP BY g.id
        """
        rows = execute_query(query, (group_id,), fetch=True) or []

        if not rows:
            return JSONResponse({"error": "Group not found"}, status_code=404)

        group = dict(rows[0])
        scans_query = """
            SELECT id, filename, status, upload_date, created_at
            FROM scans
            WHERE group_id = %s
            ORDER BY upload_date DESC
        """
        scans = execute_query(scans_query, (group_id,), fetch=True) or []
        group["scans"] = scans

        return SafeJSONResponse({"group": group})
    except Exception:
        logger.exception("doca11y-backend:get_group DB error")
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("")
async def create_group(payload: GroupPayload):
    """Create a new group"""
    name = payload.name.strip()
    description = (payload.description or "").strip()

    if not name:
        return JSONResponse({"error": "Group name is required"}, status_code=400)

    if len(name) > MAX_GROUP_NAME_LENGTH:
        return JSONResponse(
            {"error": f"Group name must be {MAX_GROUP_NAME_LENGTH} characters or fewer"},
            status_code=400,
        )

    if not NAME_REGEX.match(name):
        return JSONResponse(
            {"error": f"Group name {NAME_ALLOWED_MESSAGE}"},
            status_code=400,
        )

    group_id = f"group_{uuid.uuid4().hex}"

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM groups
            WHERE LOWER(name) = LOWER(%s)
            LIMIT 1
            """,
            (name,),
        )
        if cur.fetchone():
            return JSONResponse(
                {"error": "A group with this name already exists"}, status_code=409
            )

        cur.execute(
            """
            INSERT INTO groups (id, name, description, created_at, file_count)
            VALUES (%s, %s, %s, NOW(), 0)
            RETURNING id, name, description, created_at, file_count
            """,
            (group_id, name, description),
        )
        result = cur.fetchone()
        conn.commit()

        if result:
            group = dict(result)
            logger.info("[Backend] ✓ Created group: %s (%s)", name, group_id)
            return SafeJSONResponse({"group": group}, status_code=201)

        conn.rollback()
        return JSONResponse({"error": "Failed to create group"}, status_code=500)
    except psycopg2.IntegrityError as e:
        logger.exception("doca11y-backend:create_group integrity error: %s", e)
        conn.rollback()
        return JSONResponse(
            {"error": "A group with this name already exists"}, status_code=409
        )
    except Exception as e:
        logger.exception("doca11y-backend:create_group error: %s", e)
        if conn:
            conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@router.put("/{group_id}")
async def update_group(group_id: str, payload: GroupPayload):
    """Update group details"""
    name = payload.name.strip()
    description = (payload.description or "").strip()

    if not name:
        return JSONResponse({"error": "Group name is required"}, status_code=400)

    if len(name) > MAX_GROUP_NAME_LENGTH:
        return JSONResponse(
            {"error": f"Group name must be {MAX_GROUP_NAME_LENGTH} characters or fewer"},
            status_code=400,
        )

    if not NAME_REGEX.match(name):
        return JSONResponse(
            {"error": f"Group name {NAME_ALLOWED_MESSAGE}"},
            status_code=400,
        )

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM groups WHERE id = %s", (group_id,))
        if not cur.fetchone():
            return JSONResponse({"error": "Group not found"}, status_code=404)

        cur.execute(
            """
            SELECT id FROM groups
            WHERE LOWER(name) = LOWER(%s) AND id <> %s
            LIMIT 1
            """,
            (name, group_id),
        )
        if cur.fetchone():
            return JSONResponse(
                {"error": "A group with this name already exists"}, status_code=409
            )

        cur.execute(
            """
            UPDATE groups
            SET name = %s, description = %s
            WHERE id = %s
            RETURNING id, name, description, created_at, file_count
            """,
            (name, description, group_id),
        )
        result = cur.fetchone()
        conn.commit()

        if result:
            group = dict(result)
            logger.info("[Backend] ✓ Updated group: %s (%s)", name, group_id)
            return SafeJSONResponse({"group": group})

        conn.rollback()
        return JSONResponse({"error": "Failed to update group"}, status_code=500)
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return JSONResponse(
            {"error": "A group with this name already exists"}, status_code=409
        )
    except Exception as e:
        logger.exception("doca11y-backend:update_group error: %s", e)
        if conn:
            conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@router.delete("/{group_id}")
async def delete_group(group_id: str):
    """Delete a group along with all related batches, scans, and files."""
    try:
        rows = execute_query(
            "SELECT id, name FROM groups WHERE id = %s", (group_id,), fetch=True
        )
        if not rows:
            return JSONResponse({"error": "Group not found"}, status_code=404)

        group_name = rows[0].get("name")

        scan_rows = execute_query(
            "SELECT id, batch_id FROM scans WHERE group_id = %s",
            (group_id,),
            fetch=True,
        ) or []
        batch_rows = execute_query(
            "SELECT id FROM batches WHERE group_id = %s", (group_id,), fetch=True
        ) or []
        batches_to_delete = {batch["id"] for batch in batch_rows}

        deleted_scans = 0
        deleted_files = 0
        deleted_batches = 0

        for scan in scan_rows:
            batch_id = scan.get("batch_id")
            if batch_id and batch_id in batches_to_delete:
                continue

            try:
                result = _delete_scan_with_files(scan["id"])
            except LookupError:
                logger.warning(
                    "[Backend] Scan %s already missing while deleting group %s",
                    scan["id"],
                    group_id,
                )
                continue

            deleted_scans += 1
            deleted_files += result.get("deletedFiles", 0) or 0

        for batch in batch_rows:
            batch_id = batch["id"]
            try:
                batch_result = _delete_batch_with_files(batch_id)
                deleted_batches += 1
                deleted_scans += batch_result.get("deletedScans", 0) or 0
                deleted_files += batch_result.get("deletedFiles", 0) or 0
            except LookupError:
                logger.warning(
                    "[Backend] Batch %s missing scans while deleting group %s",
                    batch_id,
                    group_id,
                )
                execute_query(
                    "DELETE FROM batches WHERE id = %s", (batch_id,), fetch=False
                )
                deleted_batches += 1

        execute_query("DELETE FROM groups WHERE id = %s", (group_id,), fetch=False)
        logger.info(
            "[Backend] ✓ Deleted group %s with %d scans, %d batches, %d files",
            group_id,
            deleted_scans,
            deleted_batches,
            deleted_files,
        )
        return SafeJSONResponse(
            {
                "success": True,
                "message": "Group and associated content deleted successfully",
                "groupName": group_name,
                "deletedScans": deleted_scans,
                "deletedBatches": deleted_batches,
                "deletedFiles": deleted_files,
            }
        )
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as e:
        logger.exception("doca11y-backend:delete_group error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
