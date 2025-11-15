"""Routes that expose folder-centric APIs backed by the batches table."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Body, HTTPException

from backend.utils.app_helpers import (
    SafeJSONResponse,
    execute_query,
    update_batch_statistics,
    _parse_scan_results_json,
)

logger = logging.getLogger("doca11y-folders")

router = APIRouter(prefix="/api/folders", tags=["folders"])


def _normalize_document_status(raw_status: str | None) -> str:
    status = (raw_status or "").lower()
    if status in {"processing", "scan_pending", "running"}:
        return "Scanning"
    if status in {"fixed", "completed", "scanned"}:
        return "Scanned"
    return "Not Scanned"


def _fetch_folder_record(folder_id: str) -> Dict[str, Any] | None:
    rows = execute_query(
        """
        SELECT
            b.id,
            b.name,
            b.group_id AS project_id,
            b.created_at,
            b.status,
            b.total_files,
            b.total_issues,
            b.fixed_issues,
            b.remaining_issues,
            b.unprocessed_files,
            g.name AS project_name
        FROM batches b
        LEFT JOIN groups g ON g.id = b.group_id
        WHERE b.id = %s
        """,
        (folder_id,),
        fetch=True,
    )
    return rows[0] if rows else None


def _fetch_folder_documents(folder_id: str) -> List[Dict[str, Any]]:
    return execute_query(
        """
        SELECT
            s.id,
            s.filename,
            s.status,
            s.upload_date,
            s.created_at,
            s.total_issues,
            s.issues_fixed,
            s.issues_remaining,
            s.scan_results,
            s.group_id
        FROM scans s
        WHERE s.batch_id = %s
        ORDER BY COALESCE(s.upload_date, s.created_at) DESC
        """,
        (folder_id,),
        fetch=True,
    ) or []


def _map_document_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    parsed_payload = _parse_scan_results_json(
        row.get("scan_results") or row.get("results") or {}
    )
    summary = parsed_payload.get("summary") or {}
    results = parsed_payload.get("results") or parsed_payload or {}

    issues: List[Dict[str, Any]] = []
    if isinstance(results, dict):
        for category, entries in results.items():
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                entry_data = entry if isinstance(entry, dict) else {}
                severity = (entry_data.get("severity") or "Moderate").capitalize()
                if severity not in {"Critical", "Serious", "Moderate", "Minor"}:
                    severity = "Moderate"
                issues.append(
                    {
                        "id": entry_data.get("id")
                        or f"{row.get('id')}-{category}-{index}",
                        "type": entry_data.get("ruleId")
                        or entry_data.get("type")
                        or category
                        or "Issue",
                        "description": entry_data.get("description")
                        or entry_data.get("message")
                        or "Accessibility issue detected.",
                        "location": entry_data.get("location")
                        or entry_data.get("page")
                        or "Unknown location",
                        "status": "Needs Attention",
                        "severity": severity,
                    }
                )

    document_payload = {
        "id": row.get("id"),
        "name": row.get("filename") or "Document",
        "status": row.get("status") or "uploaded",
        "uploadDate": row.get("upload_date") or row.get("created_at"),
        "summary": summary,
        "issues": issues,
        "issueTotals": {
            "total": len(issues) or row.get("total_issues") or 0,
            "remaining": row.get("issues_remaining") or len(issues),
            "fixed": row.get("issues_fixed") or 0,
        },
    }
    return document_payload


def _build_folder_response(folder: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "folderId": folder["id"],
        "name": folder.get("name"),
        "projectId": folder.get("project_id"),
        "projectName": folder.get("project_name"),
        "createdAt": folder.get("created_at"),
        "status": folder.get("status"),
        "totalFiles": folder.get("total_files") or 0,
        "totalIssues": folder.get("total_issues") or 0,
        "fixedIssues": folder.get("fixed_issues") or 0,
        "remainingIssues": folder.get("remaining_issues") or 0,
        "unprocessedFiles": folder.get("unprocessed_files") or 0,
    }


@router.get("")
def list_folders(limit: int = 200):
    try:
        rows = execute_query(
            """
            SELECT
                b.id,
                b.name,
                b.group_id AS project_id,
                b.created_at,
                b.status,
                b.total_files,
                b.total_issues,
                b.fixed_issues,
                b.remaining_issues,
                b.unprocessed_files,
                g.name AS project_name
            FROM batches b
            LEFT JOIN groups g ON g.id = b.group_id
            ORDER BY b.created_at DESC
            LIMIT %s
            """,
            (limit,),
            fetch=True,
        )
        folders = [_build_folder_response(row) for row in rows or []]
        return SafeJSONResponse({"folders": folders})
    except Exception:
        logger.exception("[Folders] Failed to list folders")
        raise HTTPException(status_code=500, detail="Unable to list folders")


@router.post("")
def create_folder(payload: Dict[str, Any] = Body(...)):
    name = (payload.get("name") or "").strip()
    project_id = payload.get("projectId") or payload.get("groupId")
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    folder_id = payload.get("folderId") or f"folder_{uuid.uuid4().hex}"
    try:
        rows = execute_query(
            """
            INSERT INTO batches (
                id, name, group_id, status, created_at,
                total_files, total_issues, remaining_issues,
                fixed_issues, unprocessed_files
            )
            VALUES (%s, %s, %s, %s, NOW(), 0, 0, 0, 0, 0)
            RETURNING
                id, name, group_id AS project_id, created_at, status,
                total_files, total_issues, remaining_issues,
                fixed_issues, unprocessed_files
            """,
            (folder_id, name, project_id, "draft"),
            fetch=True,
        )
        folder = rows[0]
        return SafeJSONResponse({"folder": _build_folder_response(folder)})
    except Exception:
        logger.exception("[Folders] Failed to create folder")
        raise HTTPException(status_code=500, detail="Unable to create folder")


@router.get("/{folder_id}")
def get_folder(folder_id: str):
    folder = _fetch_folder_record(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    documents = [_map_document_payload(row) for row in _fetch_folder_documents(folder_id)]
    return SafeJSONResponse({"folder": _build_folder_response(folder), "documents": documents})


@router.get("/{folder_id}/remediation")
def get_folder_remediation(folder_id: str):
    folder = _fetch_folder_record(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    documents = [_map_document_payload(row) for row in _fetch_folder_documents(folder_id)]

    total_issues = 0
    open_issues = 0
    scores: List[float] = []
    failure_counts: Dict[str, int] = {}

    for document in documents:
        issues = document.get("issues") or []
        total_issues += len(issues)
        for issue in issues:
            failure_counts[issue["type"]] = failure_counts.get(issue["type"], 0) + 1
            if issue.get("status") != "Fixed":
                open_issues += 1
        summary = document.get("summary") or {}
        score = summary.get("complianceScore") or summary.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))

    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    top_failures = sorted(
        [{"type": issue_type, "count": count} for issue_type, count in failure_counts.items()],
        key=lambda item: item["count"],
        reverse=True,
    )[:5]

    payload = {
        "folder": _build_folder_response(folder),
        "documents": documents,
        "stats": {
            "avgScore": avg_score,
            "totalIssues": total_issues,
            "openIssues": open_issues,
            "topFailures": top_failures,
        },
        "filters": {
            "types": sorted(failure_counts.keys()),
            "statuses": ["Needs Attention", "Fixed"],
            "severities": ["Critical", "Serious", "Moderate", "Minor"],
        },
    }
    return SafeJSONResponse(payload)


@router.patch("/{folder_id}")
def rename_folder(folder_id: str, payload: Dict[str, Any] = Body(...)):
    new_name = (payload.get("name") or payload.get("folderName") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    try:
        rows = execute_query(
            """
            UPDATE batches
            SET name = %s
            WHERE id = %s
            RETURNING
                id, name, group_id AS project_id, created_at, status,
                total_files, total_issues, remaining_issues, fixed_issues, unprocessed_files
            """,
            (new_name, folder_id),
            fetch=True,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Folder not found")
        return SafeJSONResponse({"folder": _build_folder_response(rows[0])})
    except HTTPException:
        raise
    except Exception:
        logger.exception("[Folders] Failed to rename folder %s", folder_id)
        raise HTTPException(status_code=500, detail="Unable to rename folder")


def _execute_with_ids(sql: str, params: Tuple[Any, ...]):
    """Helper to run queries that require dynamic placeholders."""
    try:
        execute_query(sql, params)
    except Exception:
        logger.exception("[Folders] Failed executing query: %s", sql)
        raise HTTPException(status_code=500, detail="Database error")


@router.post("/{folder_id}/documents")
def assign_documents(folder_id: str, payload: Dict[str, Any] = Body(...)):
    document_ids = payload.get("documentIds") or payload.get("documents")
    if not document_ids or not isinstance(document_ids, list):
        raise HTTPException(status_code=400, detail="documentIds array is required")

    folder = _fetch_folder_record(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    placeholders = ",".join(["%s"] * len(document_ids))

    existing_rows = execute_query(
        f"SELECT id, batch_id FROM scans WHERE id IN ({placeholders})",
        tuple(document_ids),
        fetch=True,
    )
    if not existing_rows:
        raise HTTPException(status_code=404, detail="No matching documents found")

    _execute_with_ids(
        f"UPDATE scans SET batch_id = %s WHERE id IN ({placeholders})",
        (folder_id, *document_ids),
    )

    previous_batch_ids = {
        row.get("batch_id") for row in existing_rows if row.get("batch_id") and row.get("batch_id") != folder_id
    }

    try:
        update_batch_statistics(folder_id)
    except Exception:
        logger.exception("[Folders] Failed to refresh stats for %s", folder_id)

    for batch_id in previous_batch_ids:
        try:
            update_batch_statistics(batch_id)
        except Exception:
            logger.exception("[Folders] Failed to refresh stats for %s", batch_id)

    return SafeJSONResponse({"folderId": folder_id, "updated": len(document_ids)})
