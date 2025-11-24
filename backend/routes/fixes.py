"""Routes for applying fixes, managing batches, and download/export utilities."""

import os
import re
import asyncio
import json
import logging
import traceback
import zipfile
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

from backend.auto_fix_engine import AutoFixEngine
from backend.pdf_generator import PDFGenerator
from backend.multi_tier_storage import has_backblaze_storage, stream_remote_file
from backend.utils.app_helpers import (
    FIXED_FOLDER,
    NEON_DATABASE_URL,
    UPLOAD_FOLDER,
    FILE_STATUS_LABELS,
    SafeJSONResponse,
    archive_fixed_pdf_version,
    create_progress_tracker,
    derive_file_status,
    execute_query,
    get_db_connection,
    get_fixed_version,
    lookup_remote_fixed_entry,
    get_progress_tracker,
    get_scan_by_id,
    get_versioned_files,
    save_fix_history,
    save_scan_to_db,
    scan_results_changed,
    update_batch_statistics,
    update_scan_status,
    resolve_uploaded_file_path,
    _build_scan_export_payload,
    _delete_batch_with_files,
    _extract_version_from_path,
    _fetch_scan_record,
    _fixed_root,
    _mirror_file_to_remote,
    _parse_scan_results_json,
    _perform_automated_fix,
    _resolve_scan_file_path,
    _truthy,
    _uploads_root,
)


logger = logging.getLogger("doca11y-fixes")

router = APIRouter(prefix="/api", tags=["fixes"])
report_pdf_generator = PDFGenerator()


@router.post("/batch/{batch_id}/fix-file/{scan_id}")
async def apply_batch_fix(batch_id: str, scan_id: str):
    status, payload = await asyncio.to_thread(
        _perform_automated_fix, scan_id, {}, batch_id
    )
    if status == 200:
        payload.setdefault("batchId", batch_id)
    return JSONResponse(payload, status_code=status)


@router.post("/batch/{batch_id}/fix-all")
async def apply_batch_fix_all(batch_id: str):
    scans = execute_query(
        "SELECT id FROM scans WHERE batch_id = %s",
        (batch_id,),
        fetch=True,
    )
    if not scans:
        return JSONResponse(
            {"success": False, "error": f"No scans found for batch {batch_id}"},
            status_code=404,
        )

    success_count = 0
    errors: List[Dict[str, Any]] = []

    for scan in scans:
        scan_id = scan.get("id") if isinstance(scan, dict) else scan[0]
        status, payload = await asyncio.to_thread(
            _perform_automated_fix, scan_id, {}, batch_id
        )
        if status == 200 and payload.get("success"):
            success_count += 1
        else:
            errors.append(
                {
                    "scanId": scan_id,
                    "error": payload.get("error", "Unknown error"),
                }
            )

    update_batch_statistics(batch_id)

    total_files = len(scans)
    response_payload = {
        "success": success_count > 0,
        "successCount": success_count,
        "totalFiles": total_files,
        "errors": errors,
        "batchId": batch_id,
    }
    status_code = 200 if success_count > 0 else 500
    return JSONResponse(response_payload, status_code=status_code)


@router.get("/batch/{batch_id}")
async def get_batch_details(batch_id: str):
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
            (batch_id,),
        )
        batch = cursor.fetchone()
        if not batch:
            return JSONResponse(
                {"error": f"Batch {batch_id} not found"}, status_code=404
            )

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
            (batch_id,),
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

        initial_summary = {}
        if isinstance(scan_results, dict):
            initial_summary = scan_results.get("summary") or {}
        results = scan_results.get("results", scan_results) or {}

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
                current_issues = scan.get("issues_remaining") or initial_summary.get(
                    "totalIssues", 0
                )
            current_compliance = scan.get("compliance_after")
            if current_compliance is None:
                current_compliance = initial_summary.get("complianceScore", 0)
            current_high = scan.get("high_severity_after")
            if current_high is None:
                current_high = initial_summary.get("highSeverity", 0)
        else:
            fixes_applied = []
            current_issues = scan.get("issues_remaining") or initial_summary.get(
                "totalIssues", 0
            )
            current_compliance = initial_summary.get("complianceScore", 0)
            current_high = initial_summary.get("highSeverity", 0)
        status_code, status_label = derive_file_status(
            scan.get("status"),
            has_fix_history=has_fix_history,
            issues_remaining=current_issues,
            summary_status=initial_summary.get("status"),
        )

        current_issues = current_issues or 0
        current_compliance = current_compliance or 0
        current_high = current_high or 0

        total_issues += current_issues
        total_high += current_high
        total_compliance += current_compliance

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
                "latestVersion": latest_version_entry.get("version")
                if latest_version_entry
                else None,
                "latestFixedFile": latest_version_entry.get("relative_path")
                if latest_version_entry
                else None,
                "versionHistory": version_history,
            }
        )

    avg_compliance = (
        round(total_compliance / len(processed_scans), 2) if processed_scans else 0
    )

    batch_total_issues = batch.get("total_issues")
    batch_fixed_issues = batch.get("fixed_issues")
    batch_remaining_issues = batch.get("remaining_issues")
    batch_unprocessed_files = batch.get("unprocessed_files")
    batch_total_files = batch.get("total_files")

    response = {
        "batchId": batch_id,
        "batchName": batch.get("name"),
        "name": batch.get("name"),
        "createdAt": batch.get("created_at"),
        "uploadDate": batch.get("created_at"),
        "groupId": batch.get("group_id"),
        "status": batch.get("status"),
        "fileCount": batch_total_files
        if batch_total_files is not None
        else len(processed_scans),
        "totalIssues": batch_total_issues
        if batch_total_issues is not None
        else total_issues,
        "fixedIssues": batch_fixed_issues
        if batch_fixed_issues is not None
        else max(
            (batch_total_issues if batch_total_issues is not None else total_issues)
            - (batch_remaining_issues or 0),
            0,
        ),
        "remainingIssues": batch_remaining_issues
        if batch_remaining_issues is not None
        else max(total_issues - (batch_fixed_issues or 0), 0),
        "unprocessedFiles": batch_unprocessed_files
        if batch_unprocessed_files is not None
        else sum(
            1
            for scan in processed_scans
            if (scan.get("statusCode") or "uploaded") == "uploaded"
        ),
        "highSeverity": total_high,
        "avgCompliance": avg_compliance,
        "scans": processed_scans,
    }
    return SafeJSONResponse(response)


@router.delete("/batch/{batch_id}")
async def delete_batch(batch_id: str):
    try:
        logger.info("[Backend] Deleting batch: %s", batch_id)
        result = _delete_batch_with_files(batch_id)

        logger.info(
            "[Backend] ✓ Deleted batch %s with %d scans and %d files",
            batch_id,
            result.get("deletedScans", 0),
            result.get("deletedFiles", 0),
        )

        return SafeJSONResponse(
            {
                "success": True,
                "message": f"Deleted batch with {result.get('deletedScans', 0)} scans",
                "deletedFiles": result.get("deletedFiles", 0),
                "deletedScans": result.get("deletedScans", 0),
                "batchId": result.get("batchId"),
                "batchName": result.get("batchName"),
                "affectedGroups": result.get("affectedGroups", []),
            }
        )
    except LookupError as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=404
        )
    except Exception as e:
        logger.exception("[Backend] Error deleting batch")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/batch/{batch_id}/download")
async def download_batch(batch_id: str):
    try:
        scans = execute_query(
            "SELECT id, filename FROM scans WHERE batch_id = %s",
            (batch_id,),
            fetch=True,
        )
        if not scans:
            return JSONResponse({"error": "No files found in batch"}, status_code=404)

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
        batch_result = execute_query(
            "SELECT name FROM batches WHERE id = %s", (batch_id,), fetch=True
        )
        batch_name = batch_result[0]["name"] if batch_result else batch_id
        headers = {
            "Content-Disposition": f'attachment; filename="{batch_name}.zip"',
        }
        return StreamingResponse(
            iter([zip_buffer.getvalue()]),
            media_type="application/zip",
            headers=headers,
        )

    except Exception as e:
        logger.exception("[Backend] Error creating batch ZIP")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/batch/{batch_id}/export")
async def export_batch(batch_id: str):
    try:
        update_batch_statistics(batch_id)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, name, group_id, created_at, status,
                   total_files, total_issues, fixed_issues,
                   remaining_issues, unprocessed_files
            FROM batches
            WHERE id = %s
            """,
            (batch_id,),
        )
        batch = cur.fetchone()
        if not batch:
            cur.close()
            conn.close()
            return JSONResponse(
                {"error": f"Batch {batch_id} not found"}, status_code=404
            )

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
            (batch_id,),
        )
        scans = cur.fetchall()
        cur.close()
        conn.close()

        if not scans:
            return JSONResponse(
                {"error": "No scans found for this batch"}, status_code=404
            )

        def _sanitize(value: Optional[str], fallback: str) -> str:
            text = value or fallback
            return re.sub(r"[^A-Za-z0-9._-]", "_", text)

        batch_name = batch.get("name") or batch_id
        safe_batch_name = _sanitize(batch_name, batch_id)

        export_summary = {
            "batch": {
                "id": batch_id,
                "name": batch_name,
                "groupId": batch.get("group_id"),
                "createdAt": batch.get("created_at").isoformat()
                if batch.get("created_at")
                else None,
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

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(
                f"{safe_batch_name}/batch_summary.json",
                json.dumps(export_summary, indent=2, default=str),
            )

            uploads_dir = _uploads_root()
            fixed_dir = _fixed_root()

            for scan_row in scans:
                scan_export = _build_scan_export_payload(scan_row)
                sanitized_filename = _sanitize(
                    scan_row.get("filename"), scan_row.get("id")
                )

                zip_file.writestr(
                    f"{safe_batch_name}/scans/{sanitized_filename}.json",
                    json.dumps(scan_export, indent=2, default=str),
                )

                scan_id = scan_row.get("id")
                pdf_added = False
                latest_fixed_entry = get_fixed_version(scan_id)
                if latest_fixed_entry and latest_fixed_entry.get("absolute_path"):
                    arcname = (
                        f"{safe_batch_name}/files/{latest_fixed_entry['filename']}"
                    )
                    zip_file.write(latest_fixed_entry["absolute_path"], arcname)
                    pdf_added = True
                    logger.info(
                        "[Backend] Added latest fixed PDF to export: %s",
                        latest_fixed_entry["absolute_path"],
                    )

                if not pdf_added:
                    candidates = [uploads_dir / f"{scan_id}.pdf"]
                    original_name = scan_row.get("filename")
                    if original_name:
                        candidates.append(uploads_dir / original_name)
                    for candidate in candidates:
                        if candidate and candidate.exists():
                            arcname = f"{safe_batch_name}/files/{candidate.name}"
                            zip_file.write(candidate, arcname)
                            pdf_added = True
                            logger.info(
                                "[Backend] Added original PDF to export: %s", candidate
                            )
                            break

                version_entries = get_versioned_files(scan_id)
                if version_entries:
                    for entry in version_entries:
                        arcname = (
                            f"{safe_batch_name}/fixed/{scan_id}/{entry['filename']}"
                        )
                        zip_file.write(entry["absolute_path"], arcname)
                        logger.info(
                            "[Backend] Added version V%s to export: %s",
                            entry["version"],
                            entry["absolute_path"],
                        )

        zip_buffer.seek(0)
        download_name = f"{safe_batch_name}.zip"
        headers = {
            "Content-Disposition": f'attachment; filename="{download_name}"',
        }
        logger.info(
            "[Backend] ✓ Batch export prepared: %s with %d scans",
            download_name,
            len(scans),
        )
        return StreamingResponse(
            iter([zip_buffer.getvalue()]),
            media_type="application/zip",
            headers=headers,
        )

    except Exception as e:
        logger.exception("[Backend] Error exporting batch")
        return JSONResponse({"error": str(e)}, status_code=500)


# === Apply Semi-Automated Fixes ===
@router.post("/apply-semi-automated-fixes/{scan_id}")
async def apply_semi_automated_fixes(scan_id: str, request: Request):
    tracker = None
    try:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        fixes = payload.get("fixes") or []
        use_ai = payload.get("useAI")
        if use_ai:
            return JSONResponse(
                {
                    "error": "AI-powered semi-automated fixes are no longer available.",
                    "success": False,
                },
                status_code=400,
            )

        scan_data = _fetch_scan_record(scan_id)
        if not scan_data:
            return JSONResponse({"error": "Scan not found"}, status_code=404)

        resolved_pdf_path = _resolve_scan_file_path(scan_id, scan_data)
        if not resolved_pdf_path or not resolved_pdf_path.exists():
            return JSONResponse({"error": "PDF file not found"}, status_code=404)

        scan_data["resolved_file_path"] = str(resolved_pdf_path)

        original_filename = scan_data.get("filename")
        if not original_filename:
            return JSONResponse({"error": "Scan filename not found"}, status_code=400)

        initial_scan_results = _parse_scan_results_json(
            scan_data.get("scan_results") or scan_data.get("results")
        )
        issues_before = initial_scan_results.get("results", {})
        summary_before = initial_scan_results.get("summary", {}) or {}
        compliance_before = summary_before.get("complianceScore", 0)
        total_issues_before = summary_before.get("totalIssues", 0)
        high_severity_before = summary_before.get("highSeverity", 0)

        tracker = create_progress_tracker(scan_id)
        engine = AutoFixEngine()
        apply_fn = getattr(engine, "apply_semi_automated_fixes", None)
        if not apply_fn:
            raise RuntimeError("Semi-automated fix function unavailable")

        if asyncio.iscoroutinefunction(apply_fn):
            result = await apply_fn(
                scan_id, scan_data, tracker, resolved_path=resolved_pdf_path
            )
        else:
            result = await asyncio.to_thread(
                apply_fn, scan_id, scan_data, tracker, resolved_path=resolved_pdf_path
            )

        if not result.get("success"):
            if tracker:
                tracker.fail_all(result.get("error", "Unknown error"))
            return JSONResponse(
                {"status": "error", "error": result.get("error", "Unknown error")},
                status_code=500,
            )

        if tracker:
            tracker.complete_all()

        fixes_applied = result.get("fixesApplied") or []
        if not fixes_applied and fixes:
            fixes_applied = [
                {
                    "type": "semi-automated",
                    "issueType": fix.get("type", "unknown"),
                    "description": fix.get("description", "Semi-automated fix applied"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                for fix in fixes
            ]

        scan_results_after = result.get("scanResults") or {}
        issues_after = scan_results_after.get("results", issues_before) or {}
        summary_after = scan_results_after.get("summary", summary_before) or {}
        compliance_after = summary_after.get("complianceScore", compliance_before)
        total_issues_after = summary_after.get("totalIssues", total_issues_before)
        high_severity_after = summary_after.get("highSeverity", high_severity_before)
        fixed_filename = result.get("fixedFile")
        fixed_file_remote = result.get("fixedFileRemote")

        changes_detected = scan_results_changed(
            issues_before=issues_before,
            summary_before=summary_before,
            compliance_before=compliance_before,
            issues_after=issues_after,
            summary_after=summary_after,
            compliance_after=compliance_after,
        )

        formatted_results = {
            "results": issues_after,
            "summary": summary_after,
            "verapdfStatus": scan_results_after.get("verapdfStatus"),
            "fixes": result.get("suggestions", []),
        }

        try:
            save_scan_to_db(
                scan_id,
                original_filename,
                formatted_results,
                batch_id=scan_data.get("batch_id"),
                group_id=scan_data.get("group_id"),
                is_update=True,
                status="fixed" if total_issues_after == 0 else "processed",
                total_issues=total_issues_after,
                issues_fixed=max(total_issues_before - total_issues_after, 0),
                issues_remaining=total_issues_after,
            )
        except Exception:
            logger.exception(
                "[Backend] Failed to save semi-automated scan results for %s", scan_id
            )

        archive_info = None
        if changes_detected:
            source_path = resolve_uploaded_file_path(scan_id, scan_data)
            try:
                archive_info = archive_fixed_pdf_version(
                    scan_id=scan_id,
                    original_filename=original_filename,
                    source_path=source_path,
                )
            except Exception as archive_exc:
                logger.exception(
                    "[Backend] Failed to archive fixed PDF for %s", scan_id
                )
                return JSONResponse(
                    {"error": str(archive_exc), "scan_id": scan_id}, status_code=500
                )
            if archive_info:
                fixed_filename = archive_info.get("relative_path")
                fixed_file_remote = archive_info.get("remote_path") or fixed_file_remote

        save_success = False
        if changes_detected:
            metadata_payload: Dict[str, Any] = {
                "user_selected_fixes": len(fixes),
                "engine_version": "1.0",
            }
            if archive_info:
                metadata_payload.update(
                    {
                        "version": archive_info.get("version"),
                        "versionLabel": f"V{archive_info.get('version')}",
                        "relativePath": archive_info.get("relative_path"),
                        "storedFilename": archive_info.get("filename"),
                        "fileSize": archive_info.get("size"),
                        "remotePath": archive_info.get("remote_path"),
                    }
                )
            try:
                save_fix_history(
                    scan_id=scan_id,
                    original_filename=original_filename,
                    fixed_filename=fixed_filename or original_filename,
                    fixes_applied=fixes_applied,
                    fix_type="semi-automated",
                    issues_before=issues_before,
                    issues_after=issues_after,
                    compliance_before=compliance_before,
                    compliance_after=compliance_after,
                    total_issues_before=total_issues_before,
                    total_issues_after=total_issues_after,
                    high_severity_before=high_severity_before,
                    high_severity_after=high_severity_after,
                    fix_suggestions=fixes,
                    fix_metadata=metadata_payload,
                )
                save_success = True
            except Exception:
                logger.exception(
                    "[Backend] Failed to record semi-automated fix history for %s",
                    scan_id,
                )
        else:
            logger.info(
                "[Backend] No changes detected after semi-automated fixes for %s",
                scan_id,
            )

        update_scan_status(scan_id, "fixed" if total_issues_after == 0 else "processed")

        response_payload: Dict[str, Any] = {
            "status": "success",
            "fixedFile": fixed_filename,
            "fixedFilePath": fixed_filename,
            "fixedFileRemote": fixed_file_remote,
            "scanResults": scan_results_after,
            "summary": summary_after,
            "fixesApplied": fixes_applied,
            "historyRecorded": save_success,
            "changesDetected": changes_detected,
        }
        if archive_info:
            response_payload.update(
                {
                    "version": archive_info.get("version"),
                    "versionLabel": f"V{archive_info.get('version')}",
                    "fixedFile": archive_info.get("relative_path"),
                    "fixedFilePath": archive_info.get("relative_path"),
                    "fixedFileRemote": archive_info.get("remote_path") or fixed_file_remote,
                }
            )

        return SafeJSONResponse(response_payload)
    except Exception as exc:
        logger.exception(
            "[Backend] ERROR in apply_semi_automated_fixes for %s", scan_id
        )
        if tracker:
            tracker.fail_all(str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)


# === Progress Tracker ===
@router.get("/progress/{scan_id}")
async def get_fix_progress(scan_id: str):
    """Get real-time progress of fix application."""
    try:
        tracker = get_progress_tracker(scan_id)
        if not tracker:
            return JSONResponse(
                {
                    "error": "No progress tracking found for this scan",
                    "scanId": scan_id,
                },
                status_code=404,
            )
        return SafeJSONResponse(tracker.get_progress())
    except Exception as exc:
        logger.exception("[Backend] Error getting fix progress for %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/fix-progress/{scan_id}")
async def get_fix_progress_alias(scan_id: str):
    """Alias endpoint for legacy compatibility."""
    return await get_fix_progress(scan_id)


@router.get("/download-fixed/{filename:path}")
async def download_fixed_file(filename: str, request: Request):
    """Download a fixed PDF file."""
    try:
        fixed_dir = _fixed_root()
        uploads_dir = _uploads_root()

        allow_old = _truthy(request.query_params.get("allowDownload"))
        version_param = request.query_params.get("version")
        scan_id_param = request.query_params.get("scanId")

        file_path: Optional[Path] = None
        remote_identifier: Optional[str] = None
        selected_version: Optional[Dict[str, Any]] = None
        scan_id_for_version = scan_id_param

        requested_path: Optional[Path]
        relative_request: Optional[Path] = None
        relative_str: Optional[str] = None
        try:
            requested_path = (fixed_dir / filename).resolve()
        except Exception:
            requested_path = None
        else:
            try:
                relative_request = requested_path.relative_to(fixed_dir)
                relative_str = relative_request.as_posix()
            except ValueError:
                relative_request = None

        base_fixed = fixed_dir.resolve()
        if (
            requested_path
            and requested_path.exists()
            and str(requested_path).startswith(str(base_fixed))
        ):
            file_path = requested_path
            scan_id_for_version = requested_path.parent.name
            version_number = _extract_version_from_path(requested_path)
            if scan_id_for_version:
                versions = get_versioned_files(scan_id_for_version)
                latest = versions[-1] if versions else None
                if version_number and latest:
                    selected_version = next(
                        (
                            entry
                            for entry in versions
                            if entry.get("version") == version_number
                        ),
                        None,
                    )
                    if (
                        selected_version
                        and latest
                        and version_number != latest.get("version")
                        and not allow_old
                    ):
                        return JSONResponse(
                            {
                                "error": "Only the latest version is downloadable by default",
                                "latestVersion": latest.get("version"),
                                "requestedVersion": version_number,
                            },
                            status_code=403,
                        )
        else:
            derived_scan_id = scan_id_param
            if not derived_scan_id and relative_request:
                rel_parts = relative_request.parts
                if rel_parts:
                    derived_scan_id = rel_parts[0]
            target_scan_id = derived_scan_id or filename
            requested_number: Optional[int] = None
            versions = get_versioned_files(target_scan_id)
            if versions:
                latest = versions[-1]
                selected_version = latest
                requested_filename = relative_request.name if relative_request else None
                if version_param:
                    try:
                        requested_number = int(version_param)
                    except (ValueError, TypeError):
                        return JSONResponse(
                            {"error": "Invalid version specified"}, status_code=400
                        )
                    match = next(
                        (
                            entry
                            for entry in versions
                            if entry.get("version") == requested_number
                        ),
                        None,
                    )
                    if not match:
                        return JSONResponse(
                            {"error": f"Version {requested_number} not found"},
                            status_code=404,
                        )
                    if match.get("version") != latest.get("version") and not allow_old:
                        return JSONResponse(
                            {
                                "error": "Only the latest version is downloadable by default",
                                "latestVersion": latest.get("version"),
                                "requestedVersion": match.get("version"),
                            },
                            status_code=403,
                        )
                    selected_version = match
                elif requested_filename:
                    match = next(
                        (
                            entry
                            for entry in versions
                            if entry.get("filename") == requested_filename
                        ),
                        None,
                    )
                    if match:
                        selected_version = match

                remote_identifier = selected_version.get("remote_path")
                absolute_candidate = selected_version.get("absolute_path")
                if absolute_candidate:
                    candidate_path = Path(absolute_candidate)
                    if candidate_path.exists():
                        file_path = candidate_path
                scan_id_for_version = target_scan_id
            else:
                history_entry = lookup_remote_fixed_entry(
                    target_scan_id,
                    target_relative=relative_str,
                    version=requested_number,
                )
                if history_entry:
                    selected_version = {
                        "version": history_entry.get("version"),
                        "filename": history_entry.get("filename"),
                        "relative_path": history_entry.get("relative_path"),
                        "absolute_path": None,
                        "remote_path": history_entry.get("remote_path"),
                    }
                    remote_identifier = history_entry.get("remote_path")
                    scan_id_for_version = target_scan_id
                else:
                    for folder in (fixed_dir, uploads_dir):
                        for ext in ("", ".pdf"):
                            candidate = folder / f"{filename}{ext}"
                            if candidate.exists():
                                file_path = candidate
                                break
                        if file_path:
                            break

        if selected_version and not remote_identifier:
            remote_identifier = selected_version.get("remote_path")
            if not remote_identifier:
                lookup_scan_id = (
                    scan_id_for_version
                    or scan_id_param
                    or (derived_scan_id if "derived_scan_id" in locals() else None)
                    or filename
                )
                history_entry = lookup_remote_fixed_entry(
                    lookup_scan_id,
                    target_relative=(selected_version.get("relative_path") or relative_str),
                    version=selected_version.get("version"),
                )
                if history_entry:
                    remote_identifier = history_entry.get("remote_path")

        if not file_path and not remote_identifier:
            return JSONResponse({"error": "File not found"}, status_code=404)

        original_filename = None
        if scan_id_for_version:
            scan_record = get_scan_by_id(scan_id_for_version)
            if scan_record:
                original_filename = scan_record.get("filename")

        if selected_version and original_filename:
            download_name = (
                f"{Path(original_filename).stem}_V{selected_version['version']}.pdf"
            )
        elif selected_version:
            download_name = selected_version.get("filename") or (file_path.name if file_path else filename)
        else:
            download_name = file_path.name if file_path else filename
        if not download_name.lower().endswith(".pdf"):
            download_name = f"{Path(download_name).stem}.pdf"
        if remote_identifier:
            try:
                remote_stream = stream_remote_file(remote_identifier)
                headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
                return StreamingResponse(
                    remote_stream,
                    media_type="application/pdf",
                    headers=headers,
                )
            except FileNotFoundError:
                remote_identifier = None
            except Exception:
                logger.exception("[Backend] Remote download failed for %s", remote_identifier)

        if file_path:
            return FileResponse(
                file_path, media_type="application/pdf", filename=download_name
            )

        return JSONResponse({"error": "File not found"}, status_code=404)
    except Exception as exc:
        logger.exception("[Backend] Error downloading fixed file %s", filename)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/pdf-file/{scan_id}")
async def serve_pdf_file(scan_id: str, request: Request):
    """Serve PDF file for preview in PDF Editor."""
    try:
        uploads_dir = _uploads_root()
        fixed_dir = _fixed_root()

        version_param = request.query_params.get("version")
        file_path: Optional[Path] = None
        remote_identifier: Optional[str] = None
        requested_version: Optional[int] = None

        version_info = None
        if version_param:
            try:
                requested_version = int(version_param)
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "Invalid version parameter"}, status_code=400
                )
            version_info = get_fixed_version(scan_id, requested_version)
        else:
            version_info = get_fixed_version(scan_id)

        if version_info:
            remote_identifier = version_info.get("remote_path")
            absolute_candidate = version_info.get("absolute_path")
            if absolute_candidate:
                candidate_path = Path(absolute_candidate)
                if candidate_path.exists():
                    file_path = candidate_path

        if not file_path and not remote_identifier:
            history_entry = lookup_remote_fixed_entry(
                scan_id,
                version=requested_version,
            )
            if history_entry:
                remote_identifier = history_entry.get("remote_path")

        if not file_path:
            for folder in (fixed_dir, uploads_dir):
                for ext in ("", ".pdf"):
                    candidate = folder / f"{scan_id}{ext}"
                    if candidate.exists():
                        file_path = candidate
                        break
                if file_path:
                    break

        if remote_identifier:
            try:
                remote_stream = stream_remote_file(remote_identifier)
                return StreamingResponse(remote_stream, media_type="application/pdf")
            except FileNotFoundError:
                remote_identifier = None
            except Exception:
                logger.exception("[Backend] Remote preview fetch failed for %s", scan_id)

        if file_path:
            return FileResponse(file_path, media_type="application/pdf")

        return JSONResponse({"error": "PDF file not found"}, status_code=404)
    except Exception as exc:
        logger.exception("[Backend] Error serving PDF file for %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


# === Apply manual fix ===
@router.post("/apply-manual-fix")
async def apply_manual_fix(request: Request):
    """
    Preserve function name and behavior from original file.
    The original used form-encoded JSON fields; here we parse JSON body or form as needed.
    """
    try:
        # Accept both JSON and form data
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            # convert to dict
            payload = dict(form)

        # required fields in original: scan_id, fix_type, fix_data, original_filename, page
        scan_id = payload.get("scan_id") or payload.get("scanId")
        fix_type = payload.get("fix_type") or payload.get("fixType")
        fix_data = payload.get("fix_data") or payload.get("fixData") or {}
        original_filename = payload.get("original_filename") or payload.get(
            "originalFilename"
        )
        page = payload.get("page")

        # Find pdf path using same heuristics as original code
        scan_data = {}
        # attempt DB lookup for scan metadata if available
        try:
            if NEON_DATABASE_URL:
                rows = execute_query(
                    "SELECT * FROM scans WHERE id=%s",
                    (scan_id,),
                    fetch=True,
                )
                if rows:
                    scan_data = rows[0]
        except Exception:
            logger.exception("DB lookup for scan data failed; proceeding")

        pdf_path = _resolve_scan_file_path(
            scan_id, scan_data if isinstance(scan_data, dict) else None
        )
        if not pdf_path and original_filename:
            candidate = Path(UPLOAD_FOLDER) / original_filename
            if candidate.exists():
                pdf_path = candidate

        if not pdf_path or not pdf_path.exists():
            return JSONResponse({"error": "PDF file not found"}, status_code=404)

        uploads_root = _uploads_root().resolve()
        pdf_resolved = pdf_path.resolve()
        try:
            pdf_resolved.relative_to(uploads_root)
        except ValueError:
            target_path = uploads_root / pdf_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, target_path)
            pdf_path = target_path

        # call your AutoFixEngine.apply_manual_fix (preserve name)
        engine = AutoFixEngine()
        apply_manual_fn = getattr(engine, "apply_manual_fix", None)
        if apply_manual_fn is None:
            # try alternative name
            apply_manual_fn = getattr(engine, "apply_manual", None)

        if apply_manual_fn is None:
            return JSONResponse(
                {"error": "Manual fix function not available"}, status_code=500
            )

        # call sync or async appropriately using to_thread if necessary
        if asyncio.iscoroutinefunction(apply_manual_fn):
            fix_result = await apply_manual_fn(str(pdf_path), fix_type, fix_data, page)
        else:
            fix_result = await asyncio.to_thread(
                apply_manual_fn, str(pdf_path), fix_type, fix_data, page
            )

        if not fix_result.get("success"):
            return JSONResponse(
                {"error": fix_result.get("error", "Failed to apply manual fix")},
                status_code=500,
            )

        # re-analyze the fixed pdf using engine._analyze_fixed_pdf if exists
        rescan_data = {}
        analyze_fixed_fn = getattr(engine, "_analyze_fixed_pdf", None)
        if analyze_fixed_fn:
            if asyncio.iscoroutinefunction(analyze_fixed_fn):
                rescan_data = await analyze_fixed_fn(str(pdf_path))
            else:
                rescan_data = await asyncio.to_thread(analyze_fixed_fn, str(pdf_path))

        summary = rescan_data.get("summary", {}) or {}
        results = rescan_data.get("results", {}) or {}
        verapdf_status = rescan_data.get("verapdfStatus")
        suggestions = rescan_data.get("suggestions", []) or []

        formatted_results = {
            "results": results,
            "summary": summary,
            "verapdfStatus": verapdf_status,
            "fixes": suggestions,
        }

        remote_file_path = _mirror_file_to_remote(
            pdf_path, folder=f"fixed/{scan_id or 'manual'}"
        )

        # Save scan update to DB
        try:
            save_scan_to_db(
                scan_id,
                original_filename,
                formatted_results,
                batch_id=scan_data.get("batch_id")
                if isinstance(scan_data, dict)
                else None,
                group_id=scan_data.get("group_id")
                if isinstance(scan_data, dict)
                else None,
                is_update=True,
                file_path=remote_file_path,
            )
        except Exception:
            logger.exception("Failed to save updated scan to DB after manual fix")

        # Prepare fix history record
        fixes_applied = [
            {
                "type": "manual",
                "issueType": fix_type,
                "description": fix_result.get(
                    "description", "Manual fix applied successfully"
                ),
                "page": page,
                "timestamp": datetime.now().isoformat(),
                "metadata": fix_data,
            }
        ]

        try:
            save_fix_history(
                scan_id=scan_id,
                original_filename=original_filename,
                fixed_filename=pdf_path.name,
                fixes_applied=fixes_applied,
                fix_type="manual",
                issues_before=rescan_data.get("before", {}),
                issues_after=results,
                compliance_before=rescan_data.get("before_summary", {}),
                compliance_after=summary.get("complianceScore", None),
                fix_suggestions=suggestions,
                fix_metadata={"page": page, "manual": True},
                batch_id=scan_data.get("batch_id")
                if isinstance(scan_data, dict)
                else None,
                group_id=scan_data.get("group_id")
                if isinstance(scan_data, dict)
                else None,
                total_issues_before=(
                    rescan_data.get("before_summary", {}).get("totalIssues")
                    if isinstance(rescan_data.get("before_summary"), dict)
                    else None
                ),
                total_issues_after=summary.get("totalIssues"),
                high_severity_before=(
                    rescan_data.get("before_summary", {}).get("highSeverity")
                    if isinstance(rescan_data.get("before_summary"), dict)
                    else None
                ),
                high_severity_after=summary.get("highSeverity"),
                success_count=len(fixes_applied),
            )
        except Exception:
            logger.exception("Failed to save fix history")

        try:
            update_scan_status(scan_id)
        except Exception:
            logger.exception("Failed to update scan status")

        return JSONResponse(
            {
                "success": True,
                "message": fix_result.get("message", "Manual fix applied successfully"),
                "fixedFile": pdf_path.name,
                "summary": summary,
                "results": results,
                "scanResults": formatted_results,
                "fixesApplied": fixes_applied,
                "verapdfStatus": verapdf_status,
                "fixSuggestions": suggestions,
            }
        )

    except Exception as e:
        logger.exception("ERROR in apply_manual_fix")
        return JSONResponse({"error": str(e)}, status_code=500)


# === Download File ===
@router.get("/download/{filename}")
async def download_file(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    # search in uploads and fixed directories
    upload_path = Path(UPLOAD_FOLDER) / safe_name
    fixed_path = Path(FIXED_FOLDER) / safe_name
    if upload_path.exists():
        return FileResponse(
            str(upload_path), media_type="application/pdf", filename=safe_name
        )
    if fixed_path.exists():
        return FileResponse(
            str(fixed_path), media_type="application/pdf", filename=safe_name
        )

    if has_backblaze_storage():
        remote_candidates = [
            f"uploads/{safe_name}",
            f"fixed/{safe_name}",
        ]
        for remote_key in remote_candidates:
            try:
                remote_stream = stream_remote_file(remote_key)
            except FileNotFoundError:
                continue
            except Exception:
                logger.exception("[Storage] Remote download failed for %s", remote_key)
                continue

            headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
            return StreamingResponse(
                remote_stream,
                media_type="application/pdf",
                headers=headers,
            )

    return JSONResponse({"error": "File not found"}, status_code=404)


@router.get("/history")
async def get_history():
    """Get all scans and batches with full details for history page"""
    try:
        print("[v0] Fetching history...")

        batches_query = """
            SELECT b.id as "batchId", b.name, b.group_id as "groupId", g.name as "groupName",
                   b.created_at as "uploadDate", b.status, b.total_files as "fileCount",
                   b.total_issues as "totalIssues", b.fixed_issues as "fixedIssues",
                   b.remaining_issues as "remainingIssues", b.unprocessed_files as "unprocessedFiles"
            FROM batches b
            LEFT JOIN groups g ON b.group_id = g.id
            ORDER BY b.created_at DESC
        """
        batches = execute_query(batches_query, fetch=True)

        scans_query = """
            SELECT s.id, s.filename, s.status, 
                   COALESCE(s.upload_date, s.created_at) as "uploadDate",
                   s.created_at, s.batch_id as "batchId", s.group_id as "groupId",
                   g.name as "groupName", 
                   COALESCE(s.total_issues, 0) as "totalIssues",
                   COALESCE(s.issues_fixed, 0) as "issuesFixed", 
                   COALESCE(s.issues_remaining, s.total_issues, 0) as "issuesRemaining",
                   s.scan_results
            FROM scans s
            LEFT JOIN groups g ON s.group_id = g.id
            WHERE s.batch_id IS NULL
            ORDER BY COALESCE(s.upload_date, s.created_at) DESC
        """
        scans = execute_query(scans_query, fetch=True)

        formatted_scans = []
        for scan in scans:
            scan_dict = dict(scan)

            # Parse scan_results JSON safely
            scan_results = scan_dict.get("scan_results", {})
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception as e:
                    print(f"[Backend] Warning: Failed to parse scan_results JSON: {e}")
                    scan_results = {}

            summary = scan_results.get("summary", {}) if isinstance(scan_results, dict) else {}
            results = scan_results.get("results", scan_results)
            total_issues = scan_dict.get("totalIssues", 0)

            # Recalculate total issues if missing
            if not total_issues and results:
                total_issues = sum(
                    len(v) if isinstance(v, list) else 0 for v in results.values()
                )

            issues_remaining = scan_dict.get("issuesRemaining") or summary.get(
                "issuesRemaining", summary.get("remainingIssues")
            )
            status_code, status_label = derive_file_status(
                scan_dict.get("status"),
                issues_remaining=issues_remaining,
                summary_status=summary.get("status"),
            )

            formatted_scans.append(
                {
                    "id": scan_dict["id"],
                    "filename": scan_dict["filename"],
                    "uploadDate": scan_dict.get("uploadDate"),
                    "status": status_label,
                    "statusCode": status_code,
                    "groupId": scan_dict.get("groupId"),
                    "groupName": scan_dict.get("groupName"),
                    "totalIssues": total_issues,
                    "issuesFixed": scan_dict.get("issuesFixed", 0),
                    "issuesRemaining": scan_dict.get("issuesRemaining", total_issues),
                    "batchId": scan_dict.get("batchId"),
                }
            )

        print(f"[v0] Returning {len(batches)} batches and {len(formatted_scans)} scans")

        return SafeJSONResponse(
            {"batches": [dict(b) for b in batches], "scans": formatted_scans}
        )

    except Exception as e:
        print(f"[Backend] Error fetching history: {e}")
        traceback.print_exc()
        return JSONResponse(
            {"error": str(e), "trace": traceback.format_exc()}, status_code=500
        )


# === Apply Fixes Endpoint (wrapper around auto_fix_engine) ===
@router.post("/apply-fixes/{scan_id}")
async def apply_fixes(scan_id: str):
    """Trigger the automated fix workflow for a scan and return its result."""

    # Ensure progress tracker exists immediately (even though we now await completion)
    tracker = get_progress_tracker(scan_id) or create_progress_tracker(scan_id)

    try:
        status, payload = await asyncio.to_thread(
            _perform_automated_fix, scan_id, {}, None
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("[Backend] apply_fixes crashed for %s", scan_id)
        if tracker:
            tracker.fail_all(str(exc))
        return JSONResponse(
            {"success": False, "error": str(exc) or "Automated fix failed"},
            status_code=500,
        )

    # _perform_automated_fix already marks the tracker as completed/failed,
    # but ensure failures bubble up to the HTTP response.
    if status >= 400 and tracker and tracker.status != "failed":
        tracker.fail_all(payload.get("error", "Automated fix failed"))

    return JSONResponse(payload, status_code=status)


# === Fix history endpoint ===
@router.get("/fix-history/{scan_id}")
async def fix_history(scan_id: str):
    try:
        rows = execute_query(
            "SELECT * FROM fix_history WHERE scan_id=%s ORDER BY applied_at DESC",
            (scan_id,),
            fetch=True,
        )
        history: List[Dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            metadata = entry.get("fix_metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            elif not isinstance(metadata, dict):
                metadata = {}
            entry["fix_metadata"] = metadata
            entry["fixedFileRemote"] = metadata.get("remotePath")
            entry["fixedFilePath"] = metadata.get("relativePath") or entry.get(
                "fixed_filename"
            )
            entry["fixedFileVersion"] = metadata.get("version")
            history.append(entry)
        return SafeJSONResponse({"history": history})
    except Exception:
        logger.exception("fix_history DB error")
        return JSONResponse({"history": []})


# === Export endpoint ===
@router.get("/export/{scan_id}")
async def export_scan(scan_id: str, request: Request):
    conn = None
    cur = None
    try:
        requested_format = (request.query_params.get("format") or "json").lower()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        base_query = """
            SELECT s.id, s.filename, s.status, s.batch_id, s.group_id,
                   COALESCE(s.upload_date, s.created_at) AS upload_date,
                   s.scan_results, s.total_issues, s.issues_fixed, s.issues_remaining,
                   fh.fixed_filename, fh.fixes_applied, fh.applied_at AS applied_at, fh.fix_type,
                   fh.issues_after, fh.compliance_after
            FROM scans s
            LEFT JOIN LATERAL (
                SELECT fh_inner.*
                FROM fix_history fh_inner
                WHERE fh_inner.scan_id = s.id
                ORDER BY fh_inner.applied_at DESC
                LIMIT 1
            ) fh ON true
            WHERE {condition}
            LIMIT 1
        """

        cur.execute(base_query.format(condition="s.id = %s"), (scan_id,))
        scan_row = cur.fetchone()

        if not scan_row:
            cur.execute(base_query.format(condition="s.filename = %s"), (scan_id,))
            scan_row = cur.fetchone()

        if not scan_row:
            return JSONResponse({"error": f"Scan {scan_id} not found"}, status_code=404)

        export_payload = _build_scan_export_payload(scan_row)

        if requested_format == "pdf":
            try:
                pdf_path = await asyncio.to_thread(
                    report_pdf_generator.create_accessibility_report_pdf, export_payload
                )
            except Exception:
                logger.exception("[Backend] Error generating PDF export for %s", scan_id)
                return JSONResponse(
                    {"error": "Failed to generate PDF report"}, status_code=500
                )

            download_name = os.path.basename(pdf_path)
            background = BackgroundTask(os.remove, pdf_path)
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=download_name,
                background=background,
            )

        return SafeJSONResponse(export_payload)
    except Exception:
        logger.exception("[Backend] Error exporting scan %s", scan_id)
        return JSONResponse({"error": "Failed to prepare export"}, status_code=500)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
