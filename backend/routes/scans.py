"""Routes for scan management."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.fix_suggestions import generate_fix_suggestions
from backend.multi_tier_storage import upload_file_with_fallback
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.utils.wcag_mapping import annotate_wcag_mappings
from backend.utils.criteria_summary import build_criteria_summary
from backend.utils.app_helpers import (
    SafeJSONResponse,
    NEON_DATABASE_URL,
    FILE_STATUS_LABELS,
    build_placeholder_scan_payload,
    build_verapdf_status,
    derive_file_status,
    execute_query,
    get_fixed_version,
    lookup_remote_fixed_entry,
    get_versioned_files,
    prune_fixed_versions,
    save_scan_to_db,
    should_scan_now,
    update_batch_statistics,
    update_group_file_count,
    _analyze_pdf_document,
    _combine_compliance_scores,
    _delete_scan_with_files,
    _ensure_local_storage,
    _fetch_scan_record,
    _parse_scan_results_json,
    _resolve_scan_file_path,
    _serialize_scan_results,
    _temp_storage_root,
    _uploads_root,
    _write_uploadfile_to_disk,
)

logger = logging.getLogger("doca11y-scans")

router = APIRouter(prefix="/api", tags=["scans"])


@router.get("/scans")
async def get_scans():
    try:
        rows = (
            execute_query(
                """
            SELECT
                id,
                filename,
                group_id,
                batch_id,
                status,
                upload_date,
                created_at,
                total_issues,
                issues_fixed,
                issues_remaining,
                scan_results,
                file_path
            FROM scans
            ORDER BY COALESCE(upload_date, created_at) DESC
            LIMIT 250
            """,
                fetch=True,
            )
            or []
        )

        scans: List[Dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row)
            raw_payload = row_dict.get("scan_results") or row_dict.get("results") or {}
            parsed_payload = _parse_scan_results_json(raw_payload)
            summary = parsed_payload.get("summary", {}) or {}
            results = parsed_payload.get("results", parsed_payload) or {}
            criteria_summary = parsed_payload.get("criteriaSummary") or {}

            scan_identifier = row_dict.get("id")
            issues_remaining = (
                row_dict.get("issues_remaining")
                or summary.get("issuesRemaining")
                or summary.get("remainingIssues")
            )
            status_code, status_label = derive_file_status(
                row_dict.get("status"),
                issues_remaining=issues_remaining,
                summary_status=summary.get("status"),
            )

            scans.append(
                {
                    "id": scan_identifier,
                    "scanId": scan_identifier,
                    "filename": row_dict.get("filename"),
                    "groupId": row_dict.get("group_id"),
                    "batchId": row_dict.get("batch_id"),
                    "status": status_label,
                    "statusCode": status_code,
                    "uploadDate": row_dict.get("upload_date")
                    or row_dict.get("created_at"),
                    "filePath": row_dict.get("file_path"),
                    "summary": summary,
                    "results": results if isinstance(results, dict) else {},
                    "criteriaSummary": criteria_summary,
                    "verapdfStatus": parsed_payload.get("verapdfStatus"),
                    "totalIssues": summary.get(
                        "totalIssues", row_dict.get("total_issues", 0)
                    ),
                    "issuesFixed": row_dict.get("issues_fixed")
                    or summary.get("issuesFixed", 0),
                    "issuesRemaining": row_dict.get("issues_remaining")
                    or summary.get(
                        "issuesRemaining", summary.get("remainingIssues", 0)
                    ),
                    "complianceScore": summary.get("complianceScore"),
                }
            )

        return SafeJSONResponse({"scans": scans})
    except Exception as e:
        logger.exception("doca11y-backend:get_scans DB error")
        return JSONResponse({"scans": [], "error": str(e)}, status_code=500)


@router.post("/scan")
async def scan_pdf(
    request: Request,
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
):
    if not file or not file.filename:
        return JSONResponse({"error": "No file provided"}, status_code=400)
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files supported"}, status_code=400)
    if not group_id:
        return JSONResponse({"error": "Group ID is required"}, status_code=400)

    if folder_id:
        folder_rows = execute_query(
            "SELECT id, name, group_id FROM batches WHERE id = %s",
            (folder_id,),
            fetch=True,
        )
        if not folder_rows:
            return JSONResponse({"error": "Folder not found"}, status_code=404)
        folder_record = dict(folder_rows[0])
        folder_group_id = folder_record.get("group_id")
        if folder_group_id and folder_group_id != group_id:
            return JSONResponse(
                {"error": "Folder does not belong to the selected project"},
                status_code=400,
            )

    scan_uid = f"scan_{uuid.uuid4().hex}"
    upload_dir = _temp_storage_root()
    file_path = upload_dir / f"{scan_uid}.pdf"

    try:
        await asyncio.to_thread(file.file.seek, 0)
        await asyncio.to_thread(_write_uploadfile_to_disk, file, str(file_path))
    except Exception:
        with open(str(file_path), "wb") as f:
            content = await file.read()
            f.write(content)

    logger.info(f"[Backend] ✓ File saved: {file_path}")
    storage_reference = str(file_path)
    try:
        storage_details = await asyncio.to_thread(
            upload_file_with_fallback, str(file_path), file.filename, folder="uploads"
        )
        storage_type = storage_details.get("storage")
        storage_reference = (
            storage_details.get("url")
            or storage_details.get("path")
            or storage_reference
        )
        if storage_type == "local":
            logger.warning(
                "[Backend] Scan %s stored %s locally as fallback (%s)",
                scan_uid,
                file.filename,
                storage_reference,
            )
        else:
            logger.info(
                "[Backend] Scan %s uploaded %s to %s (%s)",
                scan_uid,
                file.filename,
                storage_type,
                storage_reference,
            )
    except Exception as storage_err:
        logger.warning(
            "[Backend] Scan %s failed to replicate %s remotely, keeping local copy at %s: %s",
            scan_uid,
            file.filename,
            storage_reference,
            storage_err,
        )

    formatted_results = await _analyze_pdf_document(file_path)
    scan_results = formatted_results.get("results", {})
    summary = formatted_results.get("summary", {}) or {}
    verapdf_status = formatted_results.get("verapdfStatus")
    fix_suggestions = formatted_results.get("fixes", [])

    try:
        total_issues = formatted_results.get("summary", {}).get("totalIssues", 0)
        saved_id = save_scan_to_db(
            scan_uid,
            file.filename,
            formatted_results,
            batch_id=folder_id,
            group_id=group_id,
            file_path=storage_reference,
            total_issues=total_issues,
            issues_remaining=total_issues,
            issues_fixed=0,
        )
        logger.info(
            f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues in group {group_id}"
        )
        if folder_id:
            try:
                update_batch_statistics(folder_id)
            except Exception:
                logger.exception(
                    "[Backend] Failed to refresh statistics for batch %s after scan",
                    folder_id,
                )
        if group_id and NEON_DATABASE_URL:
            try:
                update_group_file_count(group_id)
            except Exception:
                logger.exception(
                    "[Backend] Failed to refresh group %s counts after scan",
                    group_id,
                )
    except Exception:
        logger.exception("Failed to save scan to DB")
        saved_id = scan_uid

    return JSONResponse(
        {
            "scanId": saved_id,
            "filename": file.filename,
            "groupId": group_id,
            "summary": formatted_results["summary"],
            "results": scan_results,
            "criteriaSummary": formatted_results.get("criteriaSummary", {}),
            "fixes": fix_suggestions,
            "timestamp": datetime.now().isoformat(),
            "verapdfStatus": verapdf_status,
        }
    )


@router.post("/scan-batch")
async def scan_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    group_id: Optional[str] = Form(None),
    batch_name: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
):
    try:
        if not files:
            return JSONResponse({"error": "No files provided"}, status_code=400)
        if not group_id:
            return JSONResponse({"error": "Group ID is required"}, status_code=400)

        pdf_files = [f for f in files if f.filename.lower().endswith(".pdf")]
        skipped_files = [f.filename for f in files if f not in pdf_files]

        if not pdf_files:
            return JSONResponse(
                {"error": "No PDF files provided", "skippedFiles": skipped_files},
                status_code=400,
            )

        default_batch_title = batch_name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        scan_now = should_scan_now(scan_mode, request)
        batch_status = "processing" if scan_now else "uploaded"
        batch_id = folder_id or f"batch_{uuid.uuid4().hex}"
        batch_title = default_batch_title

        if folder_id:
            folder_rows = execute_query(
                "SELECT id, name, group_id FROM batches WHERE id = %s",
                (folder_id,),
                fetch=True,
            )
            if not folder_rows:
                return JSONResponse({"error": "Folder not found"}, status_code=404)
            folder_record = dict(folder_rows[0])
            folder_group_id = folder_record.get("group_id")
            if folder_group_id and folder_group_id != group_id:
                return JSONResponse(
                    {"error": "Folder does not belong to the selected project"},
                    status_code=400,
                )
            batch_title = folder_record.get("name") or default_batch_title
        else:
            try:
                execute_query(
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
                    VALUES (%s, %s, %s, NOW(), %s, %s, 0, 0, 0, %s)
                    """,
                    (
                        batch_id,
                        batch_title,
                        group_id,
                        batch_status,
                        len(pdf_files),
                        len(pdf_files),
                    ),
                )
            except Exception:
                logger.exception("[Backend] Failed to create batch %s", batch_id)
                return JSONResponse(
                    {"error": "Failed to create batch record"}, status_code=500
                )

        _ensure_local_storage("Batch uploads")
        upload_dir = _uploads_root()
        upload_dir.mkdir(parents=True, exist_ok=True)

        scan_results_response: List[Dict[str, Any]] = []
        total_batch_issues = 0
        processed_files = 0
        successful_scans = 0
        errors: List[str] = []

        for upload in pdf_files:
            scan_id = f"scan_{uuid.uuid4().hex}"
            file_path = upload_dir / f"{scan_id}.pdf"

            try:
                await asyncio.to_thread(
                    _write_uploadfile_to_disk, upload, str(file_path)
                )
            except Exception as write_err:
                logger.exception(
                    "[Backend] Failed to save %s for batch %s",
                    upload.filename,
                    batch_id,
                )
                errors.append(f"{upload.filename}: {write_err}")
                scan_results_response.append(
                    {
                        "scanId": scan_id,
                        "filename": upload.filename,
                        "batchId": batch_id,
                        "groupId": group_id,
                        "status": "Error",
                        "statusCode": "error",
                        "error": str(write_err),
                    }
                )
                continue

            storage_reference = None
            storage_details: Optional[Dict[str, Any]] = None
            try:
                storage_details = await asyncio.to_thread(
                    upload_file_with_fallback,
                    str(file_path),
                    upload.filename,
                    folder="uploads",
                )
                storage_type = storage_details.get("storage")
                storage_reference = (
                    storage_details.get("url")
                    or storage_details.get("path")
                    or str(file_path)
                )
                if storage_type == "local":
                    logger.warning(
                        "[Backend] Batch %s stored %s locally as fallback (%s)",
                        batch_id,
                        upload.filename,
                        storage_reference,
                    )
                else:
                    logger.info(
                        "[Backend] Batch %s uploaded %s to %s (%s)",
                        batch_id,
                        upload.filename,
                        storage_type,
                        storage_reference,
                    )
            except Exception as storage_err:
                storage_reference = str(file_path)
                logger.warning(
                    "[Backend] Batch %s failed to replicate %s to remote storage, "
                    "keeping local copy at %s: %s",
                    batch_id,
                    upload.filename,
                    storage_reference,
                    storage_err,
                )

            try:
                if scan_now:
                    record_payload = await _analyze_pdf_document(file_path)
                    summary = record_payload.get("summary", {}) or {}
                    total_issues_file = summary.get("totalIssues", 0) or 0
                    remaining_issues = summary.get(
                        "issuesRemaining",
                        summary.get("remainingIssues", total_issues_file),
                    )
                    saved_id = save_scan_to_db(
                        scan_id,
                        upload.filename,
                        record_payload,
                        batch_id=batch_id,
                        group_id=group_id,
                        status="scanned",
                        total_issues=total_issues_file,
                        issues_fixed=0,
                        issues_remaining=remaining_issues,
                        file_path=storage_reference,
                    )
                    successful_scans += 1
                    total_batch_issues += total_issues_file
                    status_code = "scanned"
                else:
                    record_payload = build_placeholder_scan_payload(upload.filename)
                    saved_id = save_scan_to_db(
                        scan_id,
                        upload.filename,
                        record_payload,
                        batch_id=batch_id,
                        group_id=group_id,
                        status="uploaded",
                        total_issues=0,
                        issues_fixed=0,
                        issues_remaining=0,
                        file_path=storage_reference,
                    )
                    status_code = "uploaded"

                processed_files += 1
                scan_results_response.append(
                    {
                        "scanId": saved_id,
                        "id": saved_id,
                        "filename": upload.filename,
                        "batchId": batch_id,
                        "groupId": group_id,
                        "status": FILE_STATUS_LABELS.get(status_code, status_code.title()),
                        "statusCode": status_code,
                        "summary": record_payload.get("summary", {}),
                        "results": record_payload.get("results", {}),
                        "criteriaSummary": record_payload.get("criteriaSummary", {}),
                        "fixes": record_payload.get("fixes", []),
                        "verapdfStatus": record_payload.get("verapdfStatus"),
                        "uploadDate": datetime.utcnow().isoformat(),
                    }
                )
            except Exception as processing_err:
                logger.exception(
                    "[Backend] Failed to process %s in batch %s",
                    upload.filename,
                    batch_id,
                )
                errors.append(f"{upload.filename}: {processing_err}")
                scan_results_response.append(
                    {
                        "scanId": scan_id,
                        "filename": upload.filename,
                        "batchId": batch_id,
                        "groupId": group_id,
                        "status": "Error",
                        "statusCode": "error",
                        "error": str(processing_err),
                    }
                )

        try:
            update_batch_statistics(batch_id)
        except Exception:
            logger.exception(
                "[Backend] Failed to refresh statistics for batch %s", batch_id
            )

        try:
            update_group_file_count(group_id)
        except Exception:
            logger.exception("[Backend] Failed to refresh group %s counts", group_id)

        response_payload = {
            "batchId": batch_id,
            "batchName": batch_title,
            "scanDeferred": not scan_now,
            "scans": scan_results_response,
            "skippedFiles": skipped_files,
            "processedFiles": processed_files,
            "successfulScans": successful_scans,
            "totalBatchIssues": total_batch_issues,
            "errors": errors,
        }

        if errors:
            response_payload["message"] = (
                f"Processed {processed_files} of {len(pdf_files)} files with {len(errors)} error(s)."
            )
        else:
            response_payload["message"] = (
                f"Processed {processed_files} file(s) in batch {batch_title}."
            )

        return SafeJSONResponse(response_payload)
    except Exception as e:
        logger.exception("scan_batch failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/scan/{scan_id}/start")
async def start_deferred_scan(scan_id: str):
    if not NEON_DATABASE_URL:
        return JSONResponse({"error": "Database not configured"}, status_code=500)

    scan_record = _fetch_scan_record(scan_id)
    if not scan_record:
        return JSONResponse({"error": "Scan not found"}, status_code=404)

    file_path = _resolve_scan_file_path(scan_id, scan_record)
    if not file_path or not file_path.exists():
        history_entry = lookup_remote_fixed_entry(scan_id)
        return JSONResponse(
            {
                "error": "Original file not found for scanning",
                "scanId": scan_id,
                "remotePath": history_entry.get("remote_path") if history_entry else None,
            },
            status_code=404,
        )

    analyzer = PDFAccessibilityAnalyzer()
    analyze_fn = getattr(analyzer, "analyze", None)
    if analyze_fn is None:
        return JSONResponse({"error": "Analyzer not available"}, status_code=500)

    if asyncio.iscoroutinefunction(analyze_fn):
        scan_results = await analyze_fn(str(file_path))
    else:
        scan_results = await asyncio.to_thread(analyze_fn, str(file_path))

    verapdf_status = build_verapdf_status(scan_results, analyzer)
    summary: Dict[str, Any] = {}
    try:
        if hasattr(analyzer, "calculate_summary"):
            calc = getattr(analyzer, "calculate_summary")
            if asyncio.iscoroutinefunction(calc):
                summary = await calc(scan_results, verapdf_status)
            else:
                summary = await asyncio.to_thread(calc, scan_results, verapdf_status)
    except Exception:
        logger.exception("[Backend] calculate_summary failed for %s", scan_id)
        summary = {}

    if isinstance(summary, dict) and verapdf_status:
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

    fix_suggestions = (
        generate_fix_suggestions(scan_results)
        if callable(generate_fix_suggestions)
        else []
    )

    formatted_results = {
        "results": scan_results,
        "summary": summary,
        "verapdfStatus": verapdf_status,
        "fixes": fix_suggestions,
    }

    total_issues = summary.get("totalIssues", 0) if isinstance(summary, dict) else 0

    try:
        execute_query(
            """
            UPDATE scans
            SET scan_results = %s,
                status = %s,
                total_issues = %s,
                issues_remaining = %s,
                issues_fixed = %s
            WHERE id = %s
            """,
            (
                _serialize_scan_results(formatted_results),
                "scanned",
                total_issues,
                total_issues,
                0,
                scan_id,
            ),
        )
    except Exception:
        logger.exception(
            "[Backend] Failed to update scan %s after deferred run", scan_id
        )
        return JSONResponse(
            {"error": "Failed to update scan record after analysis"}, status_code=500
        )

    batch_id = scan_record.get("batch_id")
    if batch_id:
        try:
            update_batch_statistics(batch_id)
        except Exception:
            logger.exception(
                "[Backend] Failed to update batch statistics for %s", batch_id
            )

    logger.info("[Backend] ✓ Deferred scan %s processed", scan_id)

    return JSONResponse(
        {
            "scanId": scan_id,
            "filename": scan_record.get("filename"),
            "groupId": scan_record.get("group_id"),
            "summary": summary,
            "results": scan_results,
            "fixes": fix_suggestions,
            "verapdfStatus": verapdf_status,
            "status": FILE_STATUS_LABELS.get("scanned", "Scanned"),
            "statusCode": "scanned",
            "timestamp": datetime.now().isoformat(),
        }
    )


@router.post("/scan/{scan_id}/prune-fixed")
async def prune_fixed_files(scan_id: str, request: Request):
    try:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        keep_latest = (
            bool(payload.get("keepLatest", True)) if isinstance(payload, dict) else True
        )
        result = prune_fixed_versions(scan_id, keep_latest=keep_latest)

        message = (
            "No previous versions were found."
            if result["removed"] == 0
            else f"Removed {result['removed']} older version(s)."
        )

        return JSONResponse(
            {
                "success": True,
                "message": message,
                "removed": result["removed"],
                "removedFiles": result["removedFiles"],
                "remainingVersions": result["remainingVersions"],
            }
        )
    except Exception as exc:
        logger.exception("[Backend] Error pruning fixed versions for %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.delete("/scan/{scan_id}")
async def delete_scan(scan_id: str):
    try:
        result = _delete_scan_with_files(scan_id)
        return JSONResponse(
            {
                "success": True,
                "message": f"Deleted scan and {result['deletedFiles']} file(s)",
                "deletedFiles": result["deletedFiles"],
                "groupId": result["groupId"],
            }
        )
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("[Backend] Error deleting scan %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/scan/{scan_id}")
async def get_scan(scan_id: str):
    logger.info("[Backend] Fetching scan details for %s", scan_id)
    resolved_scan_id = scan_id
    try:
        result = None

        candidate_ids = [scan_id]
        scan_id_no_ext = scan_id.replace(".pdf", "")
        if scan_id_no_ext != scan_id:
            candidate_ids.append(scan_id_no_ext)

        for candidate in candidate_ids:
            rows = execute_query(
                "SELECT * FROM scans WHERE id = %s",
                (candidate,),
                fetch=True,
            )
            if rows:
                result = rows
                resolved_scan_id = candidate
                break

        if not result:
            rows = execute_query(
                "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1",
                (scan_id,),
                fetch=True,
            )
            if rows:
                result = rows
                resolved_scan_id = str(rows[0].get("id") or scan_id)

        if not result:
            logger.warning("[Backend] Scan not found: %s", scan_id)
            return JSONResponse(
                {"error": f"Scan not found: {scan_id}"}, status_code=404
            )

        scan = dict(result[0])
        raw_scan_results = scan.get("scan_results") or scan.get("results") or {}
        scan_results = _parse_scan_results_json(raw_scan_results)
        results = scan_results.get("results", scan_results) or {}
        if isinstance(results, dict):
            results = annotate_wcag_mappings(results)
        else:
            results = {}

        summary = scan_results.get("summary", {}) or {}
        criteria_summary = scan_results.get("criteriaSummary")
        if not isinstance(criteria_summary, dict):
            criteria_summary = build_criteria_summary(results if isinstance(results, dict) else {})
        verapdf_status = scan_results.get("verapdfStatus")
        if verapdf_status is None:
            verapdf_status = build_verapdf_status(results)

        if (
            not summary
            or "totalIssues" not in summary
            or summary.get("totalIssues", 0) == 0
        ):
            try:
                summary = PDFAccessibilityAnalyzer.calculate_summary(
                    results, verapdf_status
                )
            except Exception as calc_error:
                logger.warning(
                    "[Backend] Failed to rebuild summary for scan %s: %s",
                    scan_id,
                    calc_error,
                )
                issue_lists = results.values() if isinstance(results, dict) else []
                total_issues = sum(
                    len(items) if isinstance(items, list) else 0
                    for items in issue_lists
                )
                high_severity = len(
                    [
                        issue
                        for issues in issue_lists
                        if isinstance(issues, list)
                        for issue in issues
                        if isinstance(issue, dict)
                        and (issue.get("severity") or "").lower()
                        in {"high", "critical"}
                    ]
                )
                compliance_score = max(0, 100 - total_issues * 2)
                summary = {
                    "totalIssues": total_issues,
                    "highSeverity": high_severity,
                    "complianceScore": compliance_score,
                }

        if isinstance(summary, dict) and verapdf_status:
            summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
            summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))
            # PDF/A compliance tracking disabled so we only average WCAG and PDF/UA scores.
            combined_score = _combine_compliance_scores(
                summary.get("wcagCompliance"),
                summary.get("pdfuaCompliance"),
            )
            if combined_score is not None:
                summary["complianceScore"] = combined_score

        latest_version = get_fixed_version(resolved_scan_id)
        version_entries = get_versioned_files(resolved_scan_id)
        version_history: List[Dict[str, Any]] = []
        latest_version_number = (
            latest_version.get("version") if latest_version else None
        )

        for entry in reversed(version_entries or []):
            created_at = entry.get("created_at")
            if hasattr(created_at, "isoformat"):
                created = created_at.isoformat()  # type: ignore[call-arg]
            else:
                created = created_at
            version_history.append(
                {
                    "version": entry.get("version"),
                    "label": f"V{entry.get('version')}",
                    "relativePath": entry.get("relative_path"),
                    "createdAt": created,
                    "fileSize": entry.get("size"),
                    "downloadable": (
                        latest_version_number is not None
                        and entry.get("version") == latest_version_number
                    ),
                }
            )

        results_dict = results if isinstance(results, dict) else {}
        current_issue_count = sum(
            len(items)
            for items in results_dict.values()
            if isinstance(items, list)
        )
        total_issues_value = summary.get("totalIssues")
        if not isinstance(total_issues_value, (int, float)):
            total_issues_value = current_issue_count
        remaining_issues_value = summary.get("remainingIssues")
        if not isinstance(remaining_issues_value, (int, float)):
            remaining_issues_value = summary.get("issuesRemaining")
        if not isinstance(remaining_issues_value, (int, float)):
            remaining_issues_value = current_issue_count
        summary["totalIssues"] = total_issues_value
        summary["remainingIssues"] = remaining_issues_value
        summary["issuesRemaining"] = remaining_issues_value
        response_verapdf = verapdf_status or {
            "isActive": False,
            "wcagCompliance": None,
            "pdfuaCompliance": None,
            "totalVeraPDFIssues": len(results_dict.get("wcagIssues", []))
            + len(results_dict.get("pdfuaIssues", [])),
        }

        batch_info = None
        batch_id_value = scan.get("batch_id") or scan.get("batchId")
        if batch_id_value:
            batch_rows = execute_query(
                """
                SELECT id, name
                FROM batches
                WHERE id = %s
                LIMIT 1
                """,
                (batch_id_value,),
                fetch=True,
            )
            if batch_rows:
                batch_info = batch_rows[0]

        remaining_issues = remaining_issues_value
        status_code, status_label = derive_file_status(
            scan.get("status"),
            issues_remaining=remaining_issues,
            summary_status=summary.get("status"),
        )

        response_data = {
            "scanId": scan.get("id"),
            "filename": scan.get("filename"),
            "status": status_label,
            "statusCode": status_code,
            "groupId": scan.get("group_id"),
            "batchId": batch_id_value,
            "folderId": batch_id_value,
            "uploadDate": scan.get("upload_date") or scan.get("created_at"),
            "summary": summary,
            "totalIssues": total_issues_value,
            "remainingIssues": remaining_issues_value,
            "issuesRemaining": remaining_issues_value,
            "results": results_dict,
            "criteriaSummary": criteria_summary,
            "fixes": scan_results.get("fixes", []),
            "verapdfStatus": response_verapdf,
        }

        if batch_info:
            response_data["batchName"] = batch_info.get("name")
            response_data["folderName"] = batch_info.get("name")

        if latest_version:
            response_data["latestVersion"] = latest_version.get("version")
            response_data["latestFixedFile"] = latest_version.get("relative_path")
            response_data["versionHistory"] = version_history

        logger.info(
            "[Backend] ✓ Found scan %s with %s issues",
            scan_id,
            summary.get("totalIssues", 0) if isinstance(summary, dict) else "unknown",
        )
        return SafeJSONResponse(response_data)
    except Exception as exc:
        logger.exception("[Backend] Error fetching scan %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/scan/{scan_id}/current-state")
async def get_scan_current_state(scan_id: str):
    try:
        scan_rows = execute_query(
            """
            SELECT id, filename, group_id, status, upload_date,
                   scan_results, total_issues, issues_fixed, issues_remaining
            FROM scans
            WHERE id = %s
            LIMIT 1
            """,
            (scan_id,),
            fetch=True,
        )

        if not scan_rows:
            return JSONResponse({"error": "Scan not found"}, status_code=404)

        scan = dict(scan_rows[0])
        resolved_id = scan.get("id") or scan_id

        latest_fix_rows = execute_query(
            """
            SELECT id, fixed_filename, fixes_applied, applied_at, fix_type,
                   issues_after, compliance_after, total_issues_after,
                   high_severity_after, fix_suggestions
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY applied_at DESC
            LIMIT 1
            """,
            (resolved_id,),
            fetch=True,
        )
        latest_fix = dict(latest_fix_rows[0]) if latest_fix_rows else None

        scan_results = _parse_scan_results_json(scan.get("scan_results"))
        initial_results = scan_results.get("results", {})
        initial_summary = scan_results.get("summary", {})

        response: Dict[str, Any] = {
            "scanId": scan.get("id"),
            "filename": scan.get("filename"),
            "groupId": scan.get("group_id"),
            "uploadDate": scan.get("upload_date"),
            "initialScan": {
                "results": initial_results,
                "summary": initial_summary,
                "totalIssues": scan.get("total_issues", 0),
            },
        }

        version_entries = get_versioned_files(resolved_id)
        latest_version_entry = version_entries[-1] if version_entries else None

        if latest_fix:
            fixes_applied = latest_fix.get("fixes_applied")
            if isinstance(fixes_applied, str):
                try:
                    fixes_applied = json.loads(fixes_applied)
                except json.JSONDecodeError:
                    fixes_applied = []

            issues_after = latest_fix.get("issues_after")
            if isinstance(issues_after, str):
                try:
                    issues_after = json.loads(issues_after)
                except json.JSONDecodeError:
                    issues_after = {}

            fix_suggestions = latest_fix.get("fix_suggestions")
            if isinstance(fix_suggestions, str):
                try:
                    fix_suggestions = json.loads(fix_suggestions)
                except json.JSONDecodeError:
                    fix_suggestions = []
            remaining_after = latest_fix.get("total_issues_after")
            status_code, status_label = derive_file_status(
                "fixed",
                has_fix_history=True,
                issues_remaining=remaining_after,
            )
            response["currentState"] = {
                "status": status_label,
                "statusCode": status_code,
                "fixedFilename": latest_fix.get("fixed_filename"),
                "lastFixApplied": latest_fix.get("applied_at"),
                "fixType": latest_fix.get("fix_type"),
                "fixesApplied": fixes_applied or [],
                "remainingIssues": issues_after or {},
                "complianceScore": latest_fix.get("compliance_after", 0),
                "totalIssues": latest_fix.get("total_issues_after", 0),
                "highSeverity": latest_fix.get("high_severity_after", 0),
                "suggestions": fix_suggestions or [],
            }

            if latest_version_entry:
                response["currentState"]["version"] = latest_version_entry.get(
                    "version"
                )
                response["currentState"]["fixedFilePath"] = latest_version_entry.get(
                    "relative_path"
                )
        else:
            remaining_initial = scan.get("issues_remaining") or initial_summary.get(
                "issuesRemaining", initial_summary.get("remainingIssues")
            )
            status_code, status_label = derive_file_status(
                scan.get("status"),
                issues_remaining=remaining_initial,
                summary_status=initial_summary.get("status"),
            )
            response["currentState"] = {
                "status": status_label,
                "statusCode": status_code,
                "remainingIssues": initial_results,
                "complianceScore": initial_summary.get("complianceScore", 0),
                "totalIssues": scan.get("total_issues", 0),
                "highSeverity": initial_summary.get("highSeverity", 0),
            }

        if latest_version_entry:
            response["latestVersion"] = latest_version_entry.get("version")
            response["latestFixedFile"] = latest_version_entry.get("relative_path")
            history: List[Dict[str, Any]] = []
            for entry in reversed(version_entries):
                created_at = entry.get("created_at")
                if hasattr(created_at, "isoformat"):
                    created = created_at.isoformat()  # type: ignore[call-arg]
                else:
                    created = created_at

                history.append(
                    {
                        "version": entry.get("version"),
                        "label": f"V{entry.get('version')}",
                        "relativePath": entry.get("relative_path"),
                        "createdAt": created,
                        "downloadable": entry.get("version")
                        == latest_version_entry.get("version"),
                        "fileSize": entry.get("size"),
                    }
                )
            response["versionHistory"] = history

        return SafeJSONResponse(response)
    except Exception as exc:
        logger.exception("[Backend] ERROR in get_scan_current_state for %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)
