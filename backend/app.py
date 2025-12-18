# backend/app.py

# Standard library imports
import os
import re
import sys
import uuid
import json
import datetime
import zipfile
import asyncio
import logging
import traceback
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List
from dotenv import load_dotenv
from io import BytesIO

# Third-party imports
from fastapi import (
    FastAPI,
    Request,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
    HTTPException,
    Body,
    Response,
)
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from werkzeug.utils import secure_filename
from psycopg2.extras import RealDictCursor

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Local application imports
from backend.services.multi_tier_storage import (
    upload_file_with_fallback,
    has_backblaze_storage,
    stream_remote_file,
)
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.auto_fix_engine import AutoFixEngine
from backend.routes import (
    health_router,
    groups_router,
    folders_router,
    scans_router,
    fixes_router,
    debug_scans_router,
)
import backend.utils.app_helpers as app_helpers
from backend.utils.app_helpers import (
    SafeJSONResponse,
    NEON_DATABASE_URL,
    UPLOAD_FOLDER,
    FIXED_FOLDER,
    mount_static_if_available,
    set_generated_pdfs_folder,
    build_placeholder_scan_payload,
    update_group_file_count,
    save_scan_to_db,
    _perform_automated_fix,
    execute_query,
    update_batch_statistics,
    get_db_connection,
    get_versioned_files,
    _delete_batch_with_files,
    _uploads_root,
    _build_scan_export_payload,
    get_fixed_version,
    lookup_remote_fixed_entry,
    _fetch_scan_record,
    _resolve_scan_file_path,
    _parse_scan_results_json,
    create_progress_tracker,
    get_progress_tracker,
    schedule_tracker_cleanup,
    scan_results_changed,
    resolve_uploaded_file_path,
    archive_fixed_pdf_version,
    save_fix_history,
    update_scan_status,
    derive_file_status,
    get_scan_by_id,
    update_scan_file_reference,
    _fixed_root,
    _truthy,
    _extract_version_from_path,
    _mirror_file_to_remote,
)

try:
    from backend.pdf_generator import PDFGenerator
except Exception:
    # If pdf_generator missing, create a minimal stub to avoid import errors
    class PDFGenerator:
        def __init__(self):
            self.output_dir = "generated_pdfs"

        def generate(self, *args, **kwargs):
            return None


# ----------------------
# Logging & Config
# ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doca11y-backend")

load_dotenv()


# CORS / environment config
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://document-a11y-accelerator.vercel.app")

# PDF generator instance - keep original pattern
pdf_generator = PDFGenerator()
generator_dir = getattr(pdf_generator, "output_dir", None)
if generator_dir:
    try:
        Path(generator_dir).mkdir(parents=True, exist_ok=True)
        set_generated_pdfs_folder(generator_dir)
    except Exception:
        logger.warning(
            "[Backend] Could not use PDF generator output dir %s, defaulting to %s",
            generator_dir,
            app_helpers.GENERATED_PDFS_FOLDER,
        )

# ----------------------
# FastAPI app + CORS
# ----------------------
app = FastAPI(title="Doc A11y Accelerator API")


# === Allow frontend (Vercel) to call backend (Render) ===
origins = [
    "https://document-a11y-acclerator.vercel.app",  # your Vercel frontend
    "https://document-a11y-acclerator.onrender.com",  # backend Render domain
    "http://localhost:3000",  # local dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # exact origins allowed
    allow_credentials=True,
    allow_methods=["*"],  # allow all HTTP verbs
    allow_headers=["*"],  # allow all headers
)

# serve uploaded files (development/test only; remote storage is canonical)
mount_static_if_available(app, "/uploads", UPLOAD_FOLDER, "uploads")


def _extract_client_export_payload(raw_body: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_body, dict):
        return None
    payload_candidate = raw_body.get("payload")
    if isinstance(payload_candidate, dict):
        return payload_candidate
    return raw_body


def _merge_export_payload(base: Optional[Dict[str, Any]], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(base, dict):
        base = {}
    if not isinstance(override, dict):
        return base
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_export_payload(merged.get(key), value)
        else:
            merged[key] = value
    return merged
mount_static_if_available(app, "/fixed", FIXED_FOLDER, "fixed")
mount_static_if_available(
    app, "/generated_pdfs", app_helpers.GENERATED_PDFS_FOLDER, "generated_pdfs"
)

app.include_router(health_router)
app.include_router(groups_router)
app.include_router(folders_router)
app.include_router(scans_router)
app.include_router(fixes_router)
app.include_router(debug_scans_router)


# ----------------------
# Routes — keep original function names, adapted for FastAPI
# ----------------------


@app.get("/favicon.ico")
async def serve_favicon():
    icon_path = Path("public/favicon.ico")
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/x-icon")
    return Response(status_code=204)


async def _run_blocking(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _write_temp_file_bytes(content: bytes, filename: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=f"_{filename}") as tmp:
        tmp.write(content)
        return tmp.name


@app.post("/api/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
):
    temp_path = None
    file_bytes = None
    try:
        file_bytes = await file.read()
        temp_path = await _run_blocking(_write_temp_file_bytes, file_bytes, file.filename)
        file_size = len(file_bytes)
        logger.info(f"[API] Received upload: {file.filename} ({file_size} bytes)")

        result = await _run_blocking(
            upload_file_with_fallback, temp_path, file.filename, folder="uploads"
        )
        storage_reference = result.get("url") or result.get("path") or result.get("key")
        response_payload: Dict[str, Any] = {
            "message": "File uploaded successfully",
            "result": dict(result),
        }
        logger.info(
            "[API] Upload received: filename=%s, group_id=%s (type=%s), NEON_DATABASE_URL=%s",
            file.filename,
            group_id,
            type(group_id),
            bool(NEON_DATABASE_URL),
        )

        folder_record = None
        if folder_id:
            folder_rows = await _run_blocking(
                execute_query,
                "SELECT id, name, group_id FROM batches WHERE id = %s",
                (folder_id,),
                fetch=True,
            )
            if not folder_rows:
                return JSONResponse({"error": "Folder not found"}, status_code=404)
            folder_record = dict(folder_rows[0])
            folder_group_id = folder_record.get("group_id")
            if folder_group_id and group_id and folder_group_id != group_id:
                return JSONResponse(
                    {"error": "Folder does not belong to the selected project"},
                    status_code=400,
                )

        if group_id and NEON_DATABASE_URL:
            logger.info("[API] saving scan metadata for %s", file.filename)

            placeholder = build_placeholder_scan_payload(file.filename)
            if storage_reference:
                placeholder = dict(placeholder)
                placeholder["filePath"] = storage_reference
            scan_id = f"scan_{uuid.uuid4().hex}"
            try:
                saved_id = await _run_blocking(
                    save_scan_to_db,
                    scan_id,
                    file.filename,
                    placeholder,
                    batch_id=folder_id,
                    group_id=group_id,
                    status="uploaded",
                    file_path=storage_reference,
                    total_issues=0,
                    issues_remaining=0,
                    issues_fixed=0,
                )
                response_payload.update(
                    {
                        "scanId": saved_id,
                        "groupId": group_id,
                        "scanDeferred": True,
                        "status": "uploaded",
                        "filePath": storage_reference,
                        "batchId": folder_id,
                        "folderId": folder_id,
                        "folderName": folder_record.get("name") if folder_record else None,
                    }
                )
                response_payload["result"].update(
                    {
                        "scanId": saved_id,
                        "groupId": group_id,
                        "status": "uploaded",
                        "filePath": storage_reference,
                        "batchId": folder_id,
                        "folderId": folder_id,
                    }
                )
                try:
                    if folder_id:
                        await _run_blocking(update_batch_statistics, folder_id)
                except Exception:
                    logger.exception(
                        "[API] Failed to refresh batch %s after upload", folder_id
                    )
                try:
                    await _run_blocking(update_group_file_count, group_id)
                except Exception:
                    logger.exception(
                        "[API] Failed to refresh group %s counts after upload", group_id
                    )
            except Exception:
                logger.exception("[API] Failed to create placeholder scan for upload")
                response_payload["warning"] = (
                    "File stored, but metadata was not saved. Please retry later."
                )

        return response_payload

    except Exception as e:
        logger.error(f"[API] Upload failed: {e}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}

    finally:
        if temp_path:
            try:
                exists = await _run_blocking(os.path.exists, temp_path)
                if exists:
                    await _run_blocking(os.remove, temp_path)
                    logger.debug(f"[API] Temporary file removed: {temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"[API] Cleanup failed for {temp_path}: {cleanup_error}")


@app.get("/api/download-generated/{filename}")
async def download_generated_pdf(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = os.path.join(app_helpers.GENERATED_PDFS_FOLDER, safe_name)
    if not os.path.exists(file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(file_path, media_type="application/pdf", filename=safe_name)


@app.post("/api/generate-pdf")
async def generate_pdf_endpoint(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    pdf_type = (payload.get("pdfType") or "inaccessible").lower()
    company_name = payload.get("companyName") or "BrightPath Consulting"
    services = payload.get("services") if isinstance(payload.get("services"), list) else None
    accessibility_options = payload.get("accessibilityOptions") if isinstance(payload.get("accessibilityOptions"), dict) else None

    try:
        # Prefer structured/tagged generation when content metadata is provided
        has_structured_content = any(
            key in payload for key in ("contentBlocks", "content", "html", "structuredContent")
        ) or payload.get("mode") == "tagged"

        if has_structured_content:
            tagged_fn = getattr(pdf_generator, "generate_tagged_pdf_from_content", None)
            if not callable(tagged_fn):
                raise AttributeError("Tagged PDF generator unavailable")
            result = await asyncio.to_thread(tagged_fn, payload)
            output_path = result.get("output_path")
            filename = os.path.basename(output_path) if output_path else None
            report = result.get("report") or {}
            if not filename:
                raise RuntimeError("PDF generator returned no output path")
            return SafeJSONResponse({"filename": filename, "report": report}, status_code=201)

        accessible_fn = getattr(pdf_generator, "create_accessible_pdf", None)
        inaccessible_fn = getattr(pdf_generator, "create_inaccessible_pdf", None)
        if pdf_type == "accessible":
            if not callable(accessible_fn):
                raise AttributeError("Accessible PDF generator unavailable")
            output_path = await asyncio.to_thread(accessible_fn, company_name, services)
        else:
            if not callable(inaccessible_fn):
                raise AttributeError("Inaccessible PDF generator unavailable")
            output_path = await asyncio.to_thread(
                inaccessible_fn,
                company_name,
                services,
                accessibility_options,
            )
        filename = os.path.basename(output_path) if output_path else None
        if not filename:
            raise RuntimeError("PDF generator returned no output path")
        return SafeJSONResponse({"filename": filename}, status_code=201)
    except Exception as exc:
        logger.exception("[Backend] PDF generation failed")
        return JSONResponse({"error": str(exc) or "Failed to generate PDF"}, status_code=500)


@app.get("/api/generated-pdfs")
async def list_generated_pdfs():
    try:
        list_fn = getattr(pdf_generator, "get_generated_pdfs", None)
        if not callable(list_fn):
            raise AttributeError("PDF generator list function unavailable")
        pdfs = await asyncio.to_thread(list_fn)
        return SafeJSONResponse({"pdfs": pdfs or []})
    except Exception:
        logger.exception("[Backend] Listing generated PDFs failed")
        return JSONResponse({"error": "Unable to list generated PDFs"}, status_code=500)


# Helper to write UploadFile to disk using file.stream (implemented in app_helpers)


@app.post("/api/batch/{batch_id}/fix-file/{scan_id}")
async def apply_batch_fix(batch_id: str, scan_id: str):
    status, payload = await asyncio.to_thread(
        _perform_automated_fix, scan_id, {}, batch_id
    )
    if status == 200:
        payload.setdefault("batchId", batch_id)
    return JSONResponse(payload, status_code=status)


@app.post("/api/batch/{batch_id}/fix-all")
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


@app.get("/api/batch/{batch_id}")
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

        initial_summary = (
            scan_results.get("summary", {}) if isinstance(scan_results, dict) else {}
        )
        results = scan_results.get("results", scan_results) or {}

        if scan.get("fix_id"):
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
            current_status = "fixed"
        else:
            fixes_applied = []
            current_issues = scan.get("issues_remaining") or initial_summary.get(
                "totalIssues", 0
            )
            current_compliance = initial_summary.get("complianceScore", 0)
            current_high = initial_summary.get("highSeverity", 0)
            current_status = scan.get("status") or "scanned"

        status_code, _ = derive_file_status(
            scan.get("status"),
            has_fix_history=bool(scan.get("fix_id")),
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
                "status": current_status,
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
            if (scan.get("status") or "").lower()
            in {"uploaded", "unprocessed", "processing"}
        ),
        "highSeverity": total_high,
        "avgCompliance": avg_compliance,
        "scans": processed_scans,
    }
    return SafeJSONResponse(response)


@app.patch("/api/batch/{batch_id}/rename")
async def rename_batch(batch_id: str, payload: Dict[str, Any] = Body(...)):
    batch_name = payload.get("batchName") or payload.get("name")
    if not isinstance(batch_name, str) or not batch_name.strip():
        return JSONResponse(
            {"error": "Batch name is required to rename"}, status_code=400
        )
    clean_name = batch_name.strip()
    try:
        updated_rows = execute_query(
            "UPDATE batches SET name = %s WHERE id = %s RETURNING id, name, group_id",
            (clean_name, batch_id),
            fetch=True,
        )
        if not updated_rows:
            return JSONResponse(
                {"error": f"Batch {batch_id} not found"}, status_code=404
            )
        updated_batch = updated_rows[0]
        return SafeJSONResponse(
            {
                "batchId": updated_batch["id"],
                "name": updated_batch["name"],
                "groupId": updated_batch["group_id"],
            }
        )
    except Exception:
        logger.exception("[Backend] Error renaming batch %s", batch_id)
        return JSONResponse(
            {"error": "Unable to rename batch at this time"}, status_code=500
        )


@app.delete("/api/batch/{batch_id}")
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


@app.get("/api/batch/{batch_id}/download")
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


@app.get("/api/batch/{batch_id}/export")
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
@app.post("/api/apply-semi-automated-fixes/{scan_id}")
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
                schedule_tracker_cleanup(scan_id)
            return JSONResponse(
                {"status": "error", "error": result.get("error", "Unknown error")},
                status_code=500,
            )

        if tracker:
            tracker.complete_all()
            schedule_tracker_cleanup(scan_id)

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
            "criteriaSummary": scan_results_after.get("criteriaSummary", {}),
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
                remote_reference = archive_info.get("remote_path")
                if remote_reference:
                    try:
                        update_scan_file_reference(scan_id, remote_reference)
                    except Exception:
                        logger.exception(
                            "[Backend] Failed to record remote reference for %s",
                            scan_id,
                        )

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
            schedule_tracker_cleanup(scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


# === Progress Tracker ===
@app.get("/api/progress/{scan_id}")
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


@app.get("/api/fix-progress/{scan_id}")
async def get_fix_progress_alias(scan_id: str):
    """Alias endpoint for legacy compatibility."""
    return await get_fix_progress(scan_id)


@app.get("/api/download-fixed/{filename:path}")
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
                relative_parts = relative_request.parts
                if relative_parts:
                    derived_scan_id = relative_parts[0]
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


@app.get("/api/pdf-file/{scan_id}")
async def serve_pdf_file(scan_id: str, request: Request):
    """Serve PDF file for preview in PDF Editor."""
    try:
        uploads_dir = _uploads_root()
        fixed_dir = _fixed_root()

        file_path: Optional[Path] = None
        remote_identifier: Optional[str] = None

        version_info = get_fixed_version(scan_id)

        if version_info:
            remote_identifier = version_info.get("remote_path")
            absolute_candidate = version_info.get("absolute_path")
            if absolute_candidate:
                candidate_path = Path(absolute_candidate)
                if candidate_path.exists():
                    file_path = candidate_path

        if not file_path and not remote_identifier:
            history_entry = lookup_remote_fixed_entry(scan_id)
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
@app.post("/api/apply-manual-fix")
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
            "criteriaSummary": rescan_data.get("criteriaSummary", {}),
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

        before_summary = rescan_data.get("before_summary")
        if not isinstance(before_summary, dict):
            before_summary = {}
        total_issues_before = before_summary.get("totalIssues")
        high_severity_before = before_summary.get("highSeverity")
        compliance_before = before_summary.get("complianceScore")
        total_issues_after = summary.get("totalIssues")
        high_severity_after = summary.get("highSeverity")
        compliance_after = summary.get("complianceScore")
        issues_before = rescan_data.get("before", {})
        issues_after = results
        issues_fixed = max(
            (total_issues_before or 0) - (total_issues_after or 0), 0
        )

        try:
            save_fix_history(
                scan_id=scan_id,
                original_filename=original_filename,
                fixed_filename=pdf_path.name,
                fixes_applied=fixes_applied,
                fix_type="manual",
                issues_before=issues_before,
                issues_after=issues_after,
                compliance_before=compliance_before,
                compliance_after=compliance_after,
                fix_suggestions=suggestions,
                fix_metadata={"page": page, "manual": True},
                batch_id=scan_data.get("batch_id")
                if isinstance(scan_data, dict)
                else None,
                group_id=scan_data.get("group_id")
                if isinstance(scan_data, dict)
                else None,
                total_issues_before=total_issues_before,
                total_issues_after=total_issues_after,
                high_severity_before=high_severity_before,
                high_severity_after=high_severity_after,
                success_count=issues_fixed,
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
                "successCount": issues_fixed,
                "verapdfStatus": verapdf_status,
                "fixSuggestions": suggestions,
            }
        )

    except Exception as e:
        logger.exception("ERROR in apply_manual_fix")
        return JSONResponse({"error": str(e)}, status_code=500)


# === Download File ===
@app.get("/api/download/{filename}")
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


@app.get("/api/history")
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

            results = scan_results.get("results", scan_results)
            total_issues = scan_dict.get("totalIssues", 0)

            # Recalculate total issues if missing
            if not total_issues and results:
                total_issues = sum(
                    len(v) if isinstance(v, list) else 0 for v in results.values()
                )

            # Default status fallback
            status = scan_dict.get("status") or "unprocessed"

            formatted_scans.append(
                {
                    "id": scan_dict["id"],
                    "filename": scan_dict["filename"],
                    "uploadDate": scan_dict.get("uploadDate"),
                    "status": status,
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
@app.post("/api/apply-fixes/{scan_id}")
async def apply_fixes(scan_id: str, background_tasks: BackgroundTasks):
    """Trigger the automated fix workflow for a scan."""

    # Ensure progress tracker exists immediately so the frontend can poll without a 404
    create_progress_tracker(scan_id)

    if asyncio.iscoroutinefunction(_perform_automated_fix):
        background_tasks.add_task(_perform_automated_fix, scan_id, {}, None)
    else:
        background_tasks.add_task(
            asyncio.to_thread, _perform_automated_fix, scan_id, {}, None
        )

    return JSONResponse({"scan_id": scan_id, "status": "started"})


# === Fix history endpoint ===
@app.get("/api/fix-history/{scan_id}")
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
@app.api_route("/api/export/{scan_id}", methods=["GET", "POST"])
async def export_scan(scan_id: str, request: Request):
    conn = None
    cur = None
    try:
        requested_format = (request.query_params.get("format") or "json").lower()
        tz_offset = request.query_params.get("tzOffset")
        client_offset = None
        if tz_offset is not None:
            try:
                client_offset = int(tz_offset)
            except ValueError:
                client_offset = None
        client_payload = None
        if request.method != "GET":
            try:
                raw_body = await request.json()
            except (json.JSONDecodeError, ValueError):
                raw_body = None
            if raw_body:
                client_payload = _extract_client_export_payload(raw_body)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        base_query = """
            SELECT s.id, s.filename, s.status, s.batch_id, s.group_id,
                   COALESCE(s.upload_date, s.created_at) AS upload_date,
                   s.scan_results, s.total_issues, s.issues_fixed, s.issues_remaining,
                   fh.fixed_filename, fh.fixes_applied, fh.applied_at AS applied_at, fh.fix_type,
                   fh.issues_after, fh.compliance_after,
                   b.name AS folder_name,
                   g.name AS group_name
            FROM scans s
            LEFT JOIN batches b ON s.batch_id = b.id
            LEFT JOIN groups g ON s.group_id = g.id
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
        if client_payload:
            export_payload = _merge_export_payload(export_payload, client_payload)

        if requested_format == "pdf":
            try:
                pdf_path = await asyncio.to_thread(
                    pdf_generator.create_accessibility_report_pdf,
                    export_payload,
                    client_offset_minutes=client_offset,
                )
            except Exception:
                logger.exception("[Backend] Error generating PDF export for %s", scan_id)
                return JSONResponse({"error": "Failed to generate PDF report"}, status_code=500)

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


# === AI endpoints wrappers preserving names ===
@app.post("/api/ai-analyze/{scan_id}")
async def ai_analyze(scan_id: str):
    analyzer = PDFAccessibilityAnalyzer()
    fn = getattr(analyzer, "ai_analyze", None)
    if not fn:
        return JSONResponse(
            {
                "scan_id": scan_id,
                "issues_detected": 0,
                "summary": "AI analyzer not implemented",
            }
        )
    if asyncio.iscoroutinefunction(fn):
        res = await fn(scan_id)
    else:
        res = await asyncio.to_thread(fn, scan_id)
    return JSONResponse(res)


@app.post("/api/ai-fix-strategy/{scan_id}")
async def ai_fix_strategy(scan_id: str):
    fn = getattr(AutoFixEngine(), "generate_ai_strategy", None) or getattr(
        AutoFixEngine(), "ai_fix_strategy", None
    )
    if not fn:
        return JSONResponse({"scan_id": scan_id, "strategy": []})
    if asyncio.iscoroutinefunction(fn):
        res = await fn(scan_id)
    else:
        res = await asyncio.to_thread(fn, scan_id)
    return JSONResponse(res)


@app.post("/api/ai-manual-guide")
async def ai_manual_guide(payload: Dict[str, Any]):
    fn = getattr(AutoFixEngine(), "manual_guide", None)
    if not fn:
        return JSONResponse({"guide": "not available"})
    if asyncio.iscoroutinefunction(fn):
        res = await fn(payload)
    else:
        res = await asyncio.to_thread(fn, payload)
    return JSONResponse(res)


@app.post("/api/ai-generate-alt-text")
async def ai_generate_alt_text(payload: Dict[str, Any]):
    fn = getattr(AutoFixEngine(), "generate_alt_text", None) or getattr(
        PDFAccessibilityAnalyzer(), "generate_alt_text", None
    )
    if not fn:
        return JSONResponse({"generated_alt_text": None})
    if asyncio.iscoroutinefunction(fn):
        res = await fn(payload)
    else:
        res = await asyncio.to_thread(fn, payload)
    return JSONResponse({"generated_alt_text": res})


@app.post("/api/ai-suggest-structure/{scan_id}")
async def ai_suggest_structure(scan_id: str):
    fn = getattr(PDFAccessibilityAnalyzer(), "suggest_structure", None)
    if not fn:
        return JSONResponse({"scan_id": scan_id, "structure": []})
    if asyncio.iscoroutinefunction(fn):
        res = await fn(scan_id)
    else:
        res = await asyncio.to_thread(fn, scan_id)
    return JSONResponse(res)


@app.post("/api/ai-apply-fixes/{scan_id}")
async def ai_apply_fixes(scan_id: str, background_tasks: BackgroundTasks):
    fn = getattr(AutoFixEngine(), "apply_ai_fixes", None) or getattr(
        AutoFixEngine(), "ai_apply_fixes", None
    )
    if not fn:
        return JSONResponse({"scan_id": scan_id, "status": "not_supported"})
    if asyncio.iscoroutinefunction(fn):
        background_tasks.add_task(fn, scan_id)
    else:
        background_tasks.add_task(asyncio.to_thread, fn, scan_id)
    return JSONResponse({"scan_id": scan_id, "status": "ai_fix_started"})


# ----------------------
# Error handlers (basic)
# ----------------------
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    path = request.url.path
    hint = "Use /api/health for the health endpoint." if path == "/health" else None
    logger.warning("doca11y-backend: route not found: %s", path)
    payload = {"error": "Route not found", "path": path}
    if hint:
        payload["hint"] = hint
    return JSONResponse(status_code=404, content=payload)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"error": str(exc)})


# ----------------------
# Run locally with: python app.py
# ----------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
