"""Routes for managing folders (a.k.a. batches)."""

import asyncio
import json
import logging
import re
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from .validation import NAME_ALLOWED_MESSAGE, NAME_REGEX
from backend.utils.app_helpers import (
    FILE_STATUS_LABELS,
    SafeJSONResponse,
    _build_scan_export_payload,
    _delete_batch_with_files,
    _fixed_root,
    _perform_automated_fix,
    _uploads_root,
    derive_file_status,
    execute_query,
    get_db_connection,
    get_fixed_version,
    get_versioned_files,
    update_batch_statistics,
)
from backend.utils.criteria_summary import build_criteria_summary

logger = logging.getLogger("doca11y-folders")

# NOTE: The UI now refers to these records as "folders", but the underlying
# database table is still named "batches". These routes keep the DB naming so
# we do not break existing upload logic while exposing cleaner folder APIs.
router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderCreatePayload(BaseModel):
    name: str = Field(..., max_length=255)
    groupId: str = Field(..., alias="groupId")
    status: Optional[str] = "uploaded"


class FolderUpdatePayload(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None


def _serialize_folder(row) -> dict:
    """Normalize batches rows into folder responses with project aliases."""
    total_files = row.get("total_files") or row.get("totalFiles") or 0
    unprocessed_files = row.get("unprocessed_files") or row.get("unprocessedFiles") or 0
    total_issues = row.get("total_issues") or row.get("totalIssues") or 0
    fixed_issues = row.get("fixed_issues") or row.get("fixedIssues") or 0
    remaining_issues = row.get("remaining_issues") or row.get("remainingIssues") or 0
    group_id = row.get("group_id") or row.get("groupId") or row.get("projectId")
    name = row.get("name") or row.get("folderName") or row.get("batchName")
    folder_id = row.get("id") or row.get("folderId") or row.get("batchId")

    return {
        "folderId": folder_id,
        "batchId": folder_id,
        "folderName": name,
        "name": name,
        "groupId": group_id,
        "projectId": group_id,
        "groupName": row.get("group_name") or row.get("groupName") or row.get("projectName"),
        "status": row.get("status"),
        "createdAt": row.get("created_at") or row.get("createdAt"),
        "fileCount": total_files,
        "totalFiles": total_files,
        "unprocessedFiles": unprocessed_files,
        "totalIssues": total_issues,
        "fixedIssues": fixed_issues,
        "remainingIssues": remaining_issues,
    }


@router.get("")
async def list_folders(groupId: Optional[str] = None, status: Optional[str] = None):
    filters: List[str] = []
    params: List[str] = []

    if groupId:
        filters.append("b.group_id = %s")
        params.append(groupId)
    if status:
        filters.append("b.status = %s")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT
            b.id,
            b.name,
            b.group_id,
            g.name AS group_name,
            b.status,
            b.created_at,
            COALESCE(stats.total_files, b.total_files, 0) AS total_files,
            COALESCE(stats.unprocessed_files, b.unprocessed_files, 0) AS unprocessed_files,
            COALESCE(stats.total_issues, b.total_issues, 0) AS total_issues,
            COALESCE(stats.fixed_issues, b.fixed_issues, 0) AS fixed_issues,
            COALESCE(stats.remaining_issues, b.remaining_issues, 0) AS remaining_issues
        FROM batches b
        LEFT JOIN groups g ON b.group_id = g.id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)::int AS total_files,
                COALESCE(SUM(s.total_issues), 0)::int AS total_issues,
                COALESCE(SUM(s.issues_remaining), 0)::int AS remaining_issues,
                COALESCE(SUM(s.issues_fixed), 0)::int AS fixed_issues,
                SUM(
                    CASE
                        WHEN COALESCE(s.status, 'uploaded') IN ('unprocessed', 'processing', 'uploaded', 'queued', 'pending')
                            THEN 1
                        ELSE 0
                    END
                )::int AS unprocessed_files
            FROM scans s
            WHERE s.batch_id = b.id
        ) stats ON TRUE
        {where_clause}
        ORDER BY b.created_at DESC NULLS LAST, b.id DESC
    """
    rows = execute_query(query, tuple(params) or None, fetch=True) or []
    return SafeJSONResponse({"folders": [_serialize_folder(dict(row)) for row in rows]})


@router.get("/{folder_id}")
async def get_folder(folder_id: str):
    """
    Fetch folder details with scans, mirroring /api/batch/{id} so the frontend can switch
    endpoints without behavioral changes.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT
                id,
                name,
                created_at,
                group_id,
                status,
                total_files,
                total_issues,
                fixed_issues,
                remaining_issues,
                unprocessed_files
            FROM batches
            WHERE id = %s
            """,
            (folder_id,),
        )
        batch = cursor.fetchone()
        if not batch:
            return JSONResponse({"error": f"Folder {folder_id} not found"}, status_code=404)

        cursor.execute(
            """
            SELECT
                s.id,
                s.filename,
                s.scan_results,
                s.status,
                s.upload_date,
                s.group_id,
                s.total_issues AS initial_total_issues,
                s.issues_fixed,
                s.issues_remaining,
                fh.id AS fix_id,
                fh.fixed_filename,
                fh.fixes_applied,
                fh.applied_at AS applied_at,
                fh.fix_type,
                fh.issues_after,
                fh.compliance_after,
                fh.total_issues_after,
                fh.high_severity_after
            FROM scans s
            LEFT JOIN LATERAL (
                SELECT
                    fh_inner.*
                FROM fix_history fh_inner
                WHERE fh_inner.scan_id = s.id
                ORDER BY fh_inner.applied_at DESC
                LIMIT 1
            ) fh ON true
            WHERE s.batch_id = %s
            ORDER BY COALESCE(s.upload_date, s.created_at) DESC
            """,
            (folder_id,),
        )
        scans = cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    processed_scans = []
    total_issues = 0
    total_compliance = 0
    scanned_files_for_compliance = 0
    total_high = 0

    for scan in scans or []:
        scan_results = scan.get("scan_results")
        if isinstance(scan_results, str):
            try:
                scan_results = json.loads(scan_results)
            except Exception:
                scan_results = {}
        elif not isinstance(scan_results, dict):
            scan_results = {}

        initial_summary = scan_results.get("summary", {}) if isinstance(scan_results, dict) else {}
        results = scan_results.get("results", scan_results) or {}
        criteria_summary = scan_results.get("criteriaSummary")
        if not isinstance(criteria_summary, dict):
            criteria_summary = build_criteria_summary(results if isinstance(results, dict) else {})

        has_fix_history = bool(scan.get("fix_id"))
        if has_fix_history:
            fixes_applied = scan.get("fixes_applied")
            if isinstance(fixes_applied, str):
                try:
                    fixes_applied = json.loads(fixes_applied)
                except Exception:
                    fixes_applied = []
            elif not isinstance(fixes_applied, list):
                fixes_applied = []
            issues_after = scan.get("issues_after")
            if isinstance(issues_after, str):
                try:
                    issues_after = json.loads(issues_after)
                except Exception:
                    issues_after = {}
            current_issues = scan.get("total_issues_after")
            if current_issues is None:
                current_issues = scan.get("issues_remaining") or initial_summary.get("totalIssues", 0)
            current_compliance = scan.get("compliance_after")
            if current_compliance is None:
                current_compliance = initial_summary.get("complianceScore", 0)
            current_high = scan.get("high_severity_after")
            if current_high is None:
                current_high = initial_summary.get("highSeverity", 0)
        else:
            fixes_applied = []
            current_issues = scan.get("issues_remaining") or initial_summary.get("totalIssues", 0)
            current_compliance = initial_summary.get("complianceScore", 0)
            current_high = initial_summary.get("highSeverity", 0)
        status_code, status_label = derive_file_status(
            scan.get("status"),
            has_fix_history=has_fix_history,
            issues_remaining=current_issues,
            summary_status=initial_summary.get("status"),
        )
        if status_code == "uploaded":
            current_compliance = 0

        current_issues = current_issues or 0
        current_compliance = current_compliance or 0
        current_high = current_high or 0

        total_issues += current_issues
        total_high += current_high
        if status_code != "uploaded":
            total_compliance += current_compliance
            scanned_files_for_compliance += 1

        version_entries = get_versioned_files(scan["id"])
        latest_version_entry = version_entries[-1] if version_entries else None
        version_history = []
        if version_entries:
            for entry in reversed(version_entries):
                created_at = entry.get("created_at")
                if hasattr(created_at, "isoformat"):
                    created = created_at.isoformat()
                else:
                    created = created_at
                version_history.append(
                    {
                        "version": entry.get("version"),
                        "label": f"V{entry.get('version')}",
                        "relativePath": entry.get("relative_path"),
                        "createdAt": created,
                        "downloadable": latest_version_entry
                        and entry.get("version") == latest_version_entry.get("version"),
                        "fileSize": entry.get("size"),
                    }
                )

        processed_scans.append(
            {
                "scanId": scan["id"],
                "filename": scan["filename"],
                "status": status_label,
                "statusCode": status_code,
                "uploadDate": scan.get("upload_date"),
                "groupId": scan.get("group_id"),
                "fixedFilename": scan.get("fixed_filename"),
                "lastFixApplied": scan.get("applied_at"),
                "fixType": scan.get("fix_type"),
                "fixesApplied": fixes_applied,
                "summary": {
                    "totalIssues": current_issues,
                    "highSeverity": current_high,
                    "complianceScore": current_compliance,
                },
                "initialSummary": {
                    "totalIssues": initial_summary.get("totalIssues", 0),
                    "highSeverity": initial_summary.get("highSeverity", 0),
                    "complianceScore": initial_summary.get("complianceScore", 0),
                },
                "results": results if isinstance(results, dict) else {},
                "criteriaSummary": criteria_summary,
                "latestVersion": latest_version_entry.get("version") if latest_version_entry else None,
                "latestFixedFile": latest_version_entry.get("relative_path") if latest_version_entry else None,
                "versionHistory": version_history,
            }
        )

    avg_compliance = (
        round(total_compliance / scanned_files_for_compliance, 2)
        if scanned_files_for_compliance
        else 0
    )
    response = {
        "batchId": folder_id,
        "folderId": folder_id,
        "batchName": batch.get("name"),
        "name": batch.get("name"),
        "createdAt": batch.get("created_at"),
        "uploadDate": batch.get("created_at"),
        "groupId": batch.get("group_id"),
        "status": batch.get("status"),
        "fileCount": batch.get("total_files") if batch.get("total_files") is not None else len(processed_scans),
        "totalIssues": batch.get("total_issues") if batch.get("total_issues") is not None else total_issues,
        "fixedIssues": batch.get("fixed_issues")
        if batch.get("fixed_issues") is not None
        else max(
            (batch.get("total_issues") if batch.get("total_issues") is not None else total_issues)
            - (batch.get("remaining_issues") or 0),
            0,
        ),
        "remainingIssues": batch.get("remaining_issues")
        if batch.get("remaining_issues") is not None
        else max(total_issues - (batch.get("fixed_issues") or 0), 0),
        "unprocessedFiles": batch.get("unprocessed_files")
        if batch.get("unprocessed_files") is not None
        else sum(
            1
            for scan in processed_scans
            if (scan.get("statusCode") or "uploaded") == "uploaded"
        ),
        "avgCompliance": avg_compliance,
        "highSeverity": total_high,
        "scans": processed_scans,
    }
    return SafeJSONResponse(response)


@router.post("")
async def create_folder(payload: FolderCreatePayload):
    name = payload.name.strip()
    status = (payload.status or "uploaded").strip()

    if not NAME_REGEX.match(name):
        return JSONResponse(
            {"error": f"Folder name {NAME_ALLOWED_MESSAGE}"},
            status_code=400,
        )

    folder_id = f"batch_{uuid.uuid4().hex}"
    rows = execute_query(
        """
        INSERT INTO batches (
            id,
            name,
            group_id,
            created_at,
            status,
            total_files,
            total_issues,
            remaining_issues,
            fixed_issues,
            unprocessed_files
        )
        VALUES (%s, %s, %s, NOW(), %s, 0, 0, 0, 0, 0)
        RETURNING id, name, group_id, status, created_at
        """,
        (folder_id, name, payload.groupId, status),
        fetch=True,
    )
    folder = dict(rows[0])
    logger.info("[Backend] ✓ Created folder %s for project %s", folder_id, payload.groupId)
    return SafeJSONResponse({"folder": _serialize_folder(folder)})


@router.patch("/{folder_id}")
async def update_folder(folder_id: str, payload: FolderUpdatePayload):
    updates: List[str] = []
    params: List[str] = []

    if payload.name:
        clean_name = payload.name.strip()
        if not NAME_REGEX.match(clean_name):
            return JSONResponse(
                {"error": f"Folder name {NAME_ALLOWED_MESSAGE}"},
                status_code=400,
            )
        updates.append("name = %s")
        params.append(clean_name)
    if payload.status:
        updates.append("status = %s")
        params.append(payload.status.strip())

    if not updates:
        return JSONResponse({"error": "No changes supplied"}, status_code=400)

    params.append(folder_id)
    rows = execute_query(
        f"""
        UPDATE batches
        SET {', '.join(updates)}
        WHERE id = %s
        RETURNING id, name, group_id, status, created_at, total_files,
                  unprocessed_files, total_issues, fixed_issues, remaining_issues
        """,
        tuple(params),
        fetch=True,
    )
    if not rows:
        return JSONResponse({"error": "Folder not found"}, status_code=404)

    logger.info("[Backend] ✓ Updated folder %s", folder_id)
    return SafeJSONResponse({"folder": _serialize_folder(dict(rows[0]))})


@router.patch("/{folder_id}/rename")
async def rename_folder(folder_id: str, payload: dict = Body(...)):
    """Compatibility endpoint that mirrors /api/batch/{id}/rename."""
    new_name = payload.get("folderName") or payload.get("batchName") or payload.get("name")
    if not isinstance(new_name, str) or not new_name.strip():
        return JSONResponse({"error": "Folder name is required to rename"}, status_code=400)
    clean_name = new_name.strip()
    if not NAME_REGEX.match(clean_name):
        return JSONResponse(
            {"error": f"Folder name {NAME_ALLOWED_MESSAGE}"},
            status_code=400,
        )
    rows = execute_query(
        "UPDATE batches SET name = %s WHERE id = %s RETURNING id, name, group_id",
        (clean_name, folder_id),
        fetch=True,
    )
    if not rows:
        return JSONResponse({"error": f"Folder {folder_id} not found"}, status_code=404)
    updated = dict(rows[0])
    return SafeJSONResponse(
        {
            "folderId": updated["id"],
            "batchId": updated["id"],
            "name": updated["name"],
            "groupId": updated["group_id"],
        }
    )


@router.delete("/{folder_id}")
async def delete_folder(folder_id: str):
    try:
        result = _delete_batch_with_files(folder_id)
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception:
        logger.exception("[Backend] Error deleting folder %s", folder_id)
        return JSONResponse({"error": "Failed to delete folder"}, status_code=500)

    return SafeJSONResponse(
        {
            "success": True,
            "folderId": result.get("batchId"),
            "batchId": result.get("batchId"),
            "folderName": result.get("batchName"),
            "deletedFiles": result.get("deletedFiles"),
            "deletedScans": result.get("deletedScans"),
            "affectedGroups": result.get("affectedGroups", []),
            "message": f"Deleted folder with {result.get('deletedScans', 0)} scans",
        }
    )


@router.post("/{folder_id}/fix-file/{scan_id}")
async def fix_folder_file(folder_id: str, scan_id: str):
    status, payload = await asyncio.to_thread(_perform_automated_fix, scan_id, {}, folder_id)
    if status == 200:
        payload.setdefault("folderId", folder_id)
        payload.setdefault("batchId", folder_id)
    return JSONResponse(payload, status_code=status)


@router.post("/{folder_id}/fix-all")
async def fix_folder_all(folder_id: str):
    scans = execute_query(
        "SELECT id FROM scans WHERE batch_id = %s",
        (folder_id,),
        fetch=True,
    )
    if not scans:
        return JSONResponse({"success": False, "error": f"No scans found for folder {folder_id}"}, status_code=404)

    success_count = 0
    errors: List[dict] = []
    for scan in scans:
        scan_id = scan.get("id") if isinstance(scan, dict) else scan[0]
        status, payload = await asyncio.to_thread(_perform_automated_fix, scan_id, {}, folder_id)
        if status == 200 and payload.get("success"):
            success_count += 1
        else:
            errors.append({"scanId": scan_id, "error": payload.get("error", "Unknown error")})

    update_batch_statistics(folder_id)

    total_files = len(scans)
    response_payload = {
        "success": success_count > 0,
        "successCount": success_count,
        "totalFiles": total_files,
        "errors": errors,
        "folderId": folder_id,
        "batchId": folder_id,
    }
    status_code = 200 if success_count > 0 else 500
    return JSONResponse(response_payload, status_code=status_code)
def _sanitize(value: Optional[str], fallback: str) -> str:
    text = value or fallback
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


@router.get("/{folder_id}/download")
async def download_folder(folder_id: str):
    scans = execute_query(
        "SELECT id, filename FROM scans WHERE batch_id = %s",
        (folder_id,),
        fetch=True,
    )
    if not scans:
        return JSONResponse({"error": "No files found in folder"}, status_code=404)

    zip_buffer = BytesIO()
    uploads_dir = _uploads_root()
    fixed_dir = _fixed_root()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for scan in scans:
            scan_id = scan["id"]
            filename = scan["filename"]
            file_path = None

            for folder in [fixed_dir, uploads_dir]:
                for ext in ("", ".pdf"):
                    candidate = folder / f"{scan_id}{ext}"
                    if candidate.exists():
                        file_path = candidate
                        break
                if file_path:
                    break

            if file_path and file_path.exists():
                zip_file.write(file_path, filename)
                logger.info("[Backend] Added to ZIP: %s", filename)

    zip_buffer.seek(0)
    folder_result = execute_query("SELECT name FROM batches WHERE id = %s", (folder_id,), fetch=True)
    folder_name = folder_result[0]["name"] if folder_result else folder_id
    headers = {"Content-Disposition": f'attachment; filename="{_sanitize(folder_name, folder_id)}.zip"'}
    return StreamingResponse(iter([zip_buffer.getvalue()]), media_type="application/zip", headers=headers)


@router.get("/{folder_id}/export")
async def export_folder(folder_id: str):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, name, group_id, created_at, status,
                   total_files, total_issues, fixed_issues, remaining_issues, unprocessed_files
            FROM batches
            WHERE id = %s
            """,
            (folder_id,),
        )
        batch = cur.fetchone()
        if not batch:
            return JSONResponse({"error": f"Folder {folder_id} not found"}, status_code=404)

        cur.execute(
            """
            SELECT s.id, s.filename, s.scan_results, s.status, s.upload_date,
                   s.total_issues, s.issues_fixed, s.issues_remaining,
                   fh.fixed_filename, fh.fixes_applied, fh.applied_at AS applied_at, fh.fix_type,
                   fh.issues_after, fh.compliance_after, fh.total_issues_after, fh.high_severity_after
            FROM scans s
            LEFT JOIN LATERAL (
                SELECT fh_inner.*
                FROM fix_history fh_inner
                WHERE fh_inner.scan_id = s.id
                ORDER BY fh_inner.applied_at DESC
                LIMIT 1
            ) fh ON true
            WHERE s.batch_id = %s
            ORDER BY COALESCE(s.upload_date, s.created_at)
            """,
            (folder_id,),
        )
        scans = cur.fetchall()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    if not scans:
        return JSONResponse({"error": "No scans found for this folder"}, status_code=404)

    safe_folder_name = _sanitize(batch.get("name"), folder_id)
    export_summary = {
        "folder": {
            "id": folder_id,
            "name": batch.get("name"),
            "groupId": batch.get("group_id"),
            "createdAt": batch.get("created_at").isoformat() if batch.get("created_at") else None,
            "status": batch.get("status"),
        },
        "totals": {
            "files": batch.get("total_files"),
            "issues": batch.get("total_issues"),
            "fixedIssues": batch.get("fixed_issues"),
            "remainingIssues": batch.get("remaining_issues"),
            "unprocessedFiles": batch.get("unprocessed_files"),
        },
        "generatedAt": datetime.utcnow().isoformat() + "Z",
    }

    zip_buffer = BytesIO()
    uploads_dir = _uploads_root()
    fixed_dir = _fixed_root()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            f"{safe_folder_name}/folder_summary.json",
            json.dumps(export_summary, indent=2, default=str),
        )

        for scan_row in scans:
            scan_export = _build_scan_export_payload(scan_row)
            sanitized_filename = _sanitize(scan_row.get("filename"), scan_row.get("id"))

            zip_file.writestr(
                f"{safe_folder_name}/scans/{sanitized_filename}.json",
                json.dumps(scan_export, indent=2, default=str),
            )

            scan_id = scan_row.get("id")
            pdf_added = False
            latest_fixed_entry = get_fixed_version(scan_id)
            if latest_fixed_entry and latest_fixed_entry.get("absolute_path"):
                arcname = f"{safe_folder_name}/files/{latest_fixed_entry['filename']}"
                zip_file.write(latest_fixed_entry["absolute_path"], arcname)
                pdf_added = True
                logger.info("[Backend] Added latest fixed PDF to export: %s", latest_fixed_entry["absolute_path"])

            if not pdf_added:
                candidates = [uploads_dir / f"{scan_id}.pdf"]
                original_name = scan_row.get("filename")
                if original_name:
                    candidates.append(uploads_dir / original_name)
                for candidate in candidates:
                    if candidate and candidate.exists():
                        arcname = f"{safe_folder_name}/files/{candidate.name}"
                        zip_file.write(candidate, arcname)
                        pdf_added = True
                        logger.info("[Backend] Added original PDF to export: %s", candidate)
                        break

            version_entries = get_versioned_files(scan_id)
            if version_entries:
                for entry in version_entries:
                    relative = entry.get("relative_path")
                    if relative and (fixed_dir / relative).exists():
                        arcname = f"{safe_folder_name}/versions/{entry.get('filename')}"
                        zip_file.write(fixed_dir / relative, arcname)

    zip_buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{safe_folder_name}.zip"'}
    return StreamingResponse(iter([zip_buffer.getvalue()]), media_type="application/zip", headers=headers)
