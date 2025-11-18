"""Routes for managing folders (a.k.a. batches)."""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.utils.app_helpers import (
    SafeJSONResponse,
    _delete_batch_with_files,
    execute_query,
)

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
    """Normalize batches rows into folder responses."""
    return {
        "folderId": row.get("id"),
        "name": row.get("name"),
        "groupId": row.get("group_id"),
        "groupName": row.get("group_name"),
        "status": row.get("status"),
        "createdAt": row.get("created_at"),
        "totalFiles": row.get("total_files"),
        "unprocessedFiles": row.get("unprocessed_files"),
        "totalIssues": row.get("total_issues"),
        "fixedIssues": row.get("fixed_issues"),
        "remainingIssues": row.get("remaining_issues"),
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
            b.total_files,
            b.unprocessed_files,
            b.total_issues,
            b.fixed_issues,
            b.remaining_issues
        FROM batches b
        LEFT JOIN groups g ON b.group_id = g.id
        {where_clause}
        ORDER BY COALESCE(b.created_at, b.id) DESC
    """
    rows = execute_query(query, tuple(params) or None, fetch=True) or []
    return SafeJSONResponse({"folders": [_serialize_folder(dict(row)) for row in rows]})


@router.get("/{folder_id}")
async def get_folder(folder_id: str):
    folder_rows = execute_query(
        """
        SELECT
            b.id,
            b.name,
            b.group_id,
            g.name AS group_name,
            b.status,
            b.created_at,
            b.total_files,
            b.unprocessed_files,
            b.total_issues,
            b.fixed_issues,
            b.remaining_issues
        FROM batches b
        LEFT JOIN groups g ON b.group_id = g.id
        WHERE b.id = %s
        """,
        (folder_id,),
        fetch=True,
    )
    if not folder_rows:
        return JSONResponse({"error": "Folder not found"}, status_code=404)

    scans = execute_query(
        """
        SELECT
            id,
            filename,
            status,
            upload_date,
            created_at
        FROM scans
        WHERE batch_id = %s
        ORDER BY COALESCE(upload_date, created_at) DESC
        """,
        (folder_id,),
        fetch=True,
    ) or []

    folder = _serialize_folder(dict(folder_rows[0]))
    folder["scans"] = [dict(scan) for scan in scans]
    return SafeJSONResponse({"folder": folder})


@router.post("")
async def create_folder(payload: FolderCreatePayload):
    name = payload.name.strip()
    status = (payload.status or "uploaded").strip()

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
        updates.append("name = %s")
        params.append(payload.name.strip())
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
            "deletedFiles": result.get("deletedFiles"),
            "deletedScans": result.get("deletedScans"),
            "message": "Folder and related files deleted",
        }
    )
