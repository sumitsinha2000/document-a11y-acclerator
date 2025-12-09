"""Helper utilities extracted from backend.app for reuse across modules."""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import traceback
import uuid
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import threading

from backend.multi_tier_storage import download_remote_file, upload_file_with_fallback, delete_remote_file
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.auto_fix_engine import AutoFixEngine
from backend.fix_progress_tracker import create_progress_tracker, get_progress_tracker
from backend.utils.wcag_mapping import annotate_wcag_mappings, CATEGORY_CRITERIA_MAP
from backend.utils.criteria_summary import build_criteria_summary
from backend.utils.compliance_scoring import derive_wcag_score

load_dotenv()

logger = logging.getLogger('doca11y-backend')

FILE_STATUS_LABELS: Dict[str, str] = {
    "uploaded": "Uploaded",
    "scanned": "Scanned",
    "partially_fixed": "Partially Fixed",
    "fixed": "Fixed",
    "error": "Error",
}

LEGACY_STATUS_CODE_MAP: Dict[str, str] = {
    "": "uploaded",
    "uploaded": "uploaded",
    "uploading": "uploaded",
    "unprocessed": "uploaded",
    "processing": "uploaded",
    "queued": "uploaded",
    "pending": "uploaded",
    "scanned": "scanned",
    "completed": "scanned",
    "finished": "scanned",
    "processed": "partially_fixed",
    "partially_fixed": "partially_fixed",
    "ai_fix_started": "partially_fixed",
    "fixing": "partially_fixed",
    "fixed": "fixed",
    "compliant": "fixed",
    "error": "error",
}

SUMMARY_PENDING_STATUSES = {"queued", "pending", "uploading", "processing"}

NEON_DATABASE_URL = os.getenv('NEON_DATABASE_URL')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public')

def to_json_safe(data):
    """
    Recursively convert data into JSON-safe types:
    - datetime/date -> ISO string
    - Decimal -> float
    - UUID -> string
    - set -> list
    - bytes -> utf-8 string
    - Nested dicts/lists handled automatically
    """
    if isinstance(data, (datetime, date)):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, UUID):
        return str(data)
    elif isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except Exception:
            return str(data)
    elif isinstance(data, set):
        return list(data)
    elif isinstance(data, dict):
        return {k: to_json_safe(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [to_json_safe(v) for v in data]
    elif isinstance(data, tuple):
        return tuple(to_json_safe(v) for v in data)
    else:
        return data

class SafeJSONResponse(JSONResponse):
    def render(self, content: any) -> bytes:
        safe = to_json_safe(content)
        return json.dumps(safe, ensure_ascii=False).encode("utf-8")

def _coerce_int(value: Any) -> Optional[int]:
    """Best-effort conversion to int."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, Decimal)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None

def normalize_file_status(raw_status: Optional[str]) -> str:
    """Map legacy status strings into the canonical status code."""
    if raw_status is None:
        return "uploaded"
    normalized = raw_status.strip().lower()
    return LEGACY_STATUS_CODE_MAP.get(normalized, normalized or "uploaded")

def derive_file_status(
    raw_status: Optional[str],
    *,
    has_fix_history: bool = False,
    issues_remaining: Optional[int] = None,
    summary_status: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Determine the canonical status code + label for a scan based on legacy
    status fields, fix history, and remaining issue counts.
    """
    normalized = normalize_file_status(raw_status)
    remaining = _coerce_int(issues_remaining)
    summary_normalized = (
        normalize_file_status(summary_status)
        if summary_status is not None
        else None
    )

    if has_fix_history:
        normalized = "fixed" if (remaining is not None and remaining <= 0) else "partially_fixed"
    elif normalized not in FILE_STATUS_LABELS or normalized == "uploaded":
        if (
            summary_normalized
            and summary_normalized not in SUMMARY_PENDING_STATUSES
            and summary_normalized in {"scanned", "partially_fixed", "fixed"}
        ):
            normalized = "scanned"

    if remaining is not None and remaining <= 0 and normalized != "uploaded":
        normalized = "fixed"

    if normalized not in FILE_STATUS_LABELS:
        normalized = "uploaded"

    return normalized, FILE_STATUS_LABELS[normalized]

def remap_status_counts(raw_counts: Optional[Dict[str, int]]) -> Dict[str, int]:
    """Normalize aggregated status counts into the canonical buckets."""
    normalized_counts: Dict[str, int] = {
        "uploaded": 0,
        "scanned": 0,
        "partially_fixed": 0,
        "fixed": 0,
    }
    if not raw_counts:
        return normalized_counts

    for status_key, count in raw_counts.items():
        if not count:
            continue
        code = normalize_file_status(status_key)
        if code not in normalized_counts:
            continue
        normalized_counts[code] += count

    return normalized_counts

def _init_storage_dir(env_value: Optional[str], default_suffix: str) -> Path:
    """
    Resolve a storage directory path. Prefer the explicit env var; otherwise
    fall back to a temp-based runtime directory that is always writable in
    deployment environments without persistent disks.
    """
    candidates = []
    if env_value:
        candidates.append(Path(env_value).expanduser())
    runtime_base = Path(tempfile.gettempdir()) / "doca11y"
    candidates.append(runtime_base / default_suffix)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            logger.warning(
                "[Backend] Failed to create storage dir %s; trying fallback", candidate
            )
            logger.debug(traceback.format_exc())
    # Last resort: use the system temp dir itself
    fallback = Path(tempfile.gettempdir()) / f"doca11y_{default_suffix}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


UPLOAD_FOLDER_PATH = _init_storage_dir(os.getenv('UPLOAD_FOLDER'), 'uploads')
FIXED_FOLDER_PATH = _init_storage_dir(os.getenv('FIXED_FOLDER'), 'fixed')
TEMP_UPLOAD_DIR_PATH = _init_storage_dir(os.getenv('TEMP_UPLOAD_DIR'), 'tmp')
GENERATED_PDFS_BASE = _init_storage_dir(os.getenv('GENERATED_PDFS_FOLDER'), 'generated')

UPLOAD_FOLDER = str(UPLOAD_FOLDER_PATH)
FIXED_FOLDER = str(FIXED_FOLDER_PATH)
TEMP_UPLOAD_DIR = str(TEMP_UPLOAD_DIR_PATH)
GENERATED_PDFS_FOLDER = str(GENERATED_PDFS_BASE)

VERSION_FILENAME_PATTERN = re.compile(r'_v(\d+)\.pdf$', re.IGNORECASE)

db_lock = threading.Lock()

def mount_static_if_available(app_instance: Any, prefix: str, directory: str, name: str):
    path = Path(directory)
    try:
        if path.exists():
            app_instance.mount(prefix, StaticFiles(directory=directory), name=name)
        else:
            logger.info(
                "[Backend] Skipping static mount for %s; directory %s not available",
                prefix,
                directory,
            )
    except Exception:
        logger.warning(
            "[Backend] Failed to mount static directory %s at %s", directory, prefix
        )
        logger.debug(traceback.format_exc())

def get_db_connection():
    """
    Synchronous psycopg2 connection as in original file.
    Keep using RealDictCursor for compatibility.
    """
    if not NEON_DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    try:
        conn = psycopg2.connect(NEON_DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.exception("Database connection failed: ", e)
        raise

def execute_query(query: str, params: Optional[tuple] = None, fetch: bool = False):
    """
    Execute a synchronous SQL query with thread lock (same pattern as original).
    Returns fetched rows if fetch=True, else True on success.
    """
    with db_lock:
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(query, params or ())
            if fetch:
                result = cur.fetchall()
                conn.commit()
                conn.close()
                return result
            else:
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            if conn:
                conn.rollback()
                conn.close()
            logger.exception("Query execution failed: ", e)
            raise

def update_batch_statistics(batch_id: str):
    """Recalculate aggregate metrics for a batch and persist them."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_files,
                COALESCE(SUM(total_issues), 0) AS total_issues,
                COALESCE(SUM(issues_remaining), 0) AS remaining_issues,
                COALESCE(SUM(issues_fixed), 0) AS fixed_issues,
                SUM(CASE WHEN status IN ('unprocessed', 'processing', 'uploaded') THEN 1 ELSE 0 END) AS unprocessed_files,
                SUM(CASE WHEN status = 'fixed' THEN 1 ELSE 0 END) AS fixed_files,
                SUM(CASE WHEN status = 'uploaded' THEN 1 ELSE 0 END) AS uploaded_files
            FROM scans
            WHERE batch_id = %s
            """,
            (batch_id,),
        )
        stats = cursor.fetchone() or {}

        total_files = stats.get("total_files") or 0
        total_issues = stats.get("total_issues") or 0
        remaining_issues = stats.get("remaining_issues") or 0
        fixed_issues = stats.get("fixed_issues")
        if fixed_issues is None:
            fixed_issues = max(total_issues - remaining_issues, 0)
        unprocessed_files = stats.get("unprocessed_files") or 0
        fixed_files = stats.get("fixed_files") or 0
        uploaded_files = stats.get("uploaded_files") or 0

        if total_files == 0:
            batch_status = "empty"
        elif uploaded_files == total_files:
            batch_status = "uploaded"
        elif uploaded_files > 0:
            batch_status = "partial"
        elif remaining_issues == 0:
            batch_status = "completed"
        elif fixed_files == 0 and unprocessed_files == total_files:
            batch_status = "processing"
        else:
            batch_status = "partial"

        cursor.execute(
            """
            UPDATE batches
            SET total_files = %s,
                total_issues = %s,
                remaining_issues = %s,
                fixed_issues = %s,
                unprocessed_files = %s,
                status = %s
            WHERE id = %s
            """,
            (
                total_files,
                total_issues,
                remaining_issues,
                fixed_issues,
                unprocessed_files,
                batch_status,
                batch_id,
            ),
        )
        conn.commit()
        logger.info(
            "[Backend] ✓ Batch %s statistics updated: total=%s remaining=%s status=%s",
            batch_id,
            total_issues,
            remaining_issues,
            batch_status,
        )
    except Exception:
        if conn:
            conn.rollback()
        logger.exception(
            "[Backend] ⚠ Failed to update batch statistics for %s", batch_id
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def _parse_scan_results_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Failed to parse scan_results JSON: %s", value)
            return {}
    return {}

def _deserialize_json_field(value: Any, fallback: Any):
    """Best-effort JSON deserializer that tolerates strings and native objects."""
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            logger.debug("[Backend] Unable to deserialize JSON field: %s", value)
            return fallback
    return fallback

def _build_scan_export_payload(scan_row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize scan export payloads for single-scan and batch exports."""
    scan_results = _parse_scan_results_json(scan_row.get("scan_results"))
    results = scan_results.get("results", scan_results) or {}
    if not isinstance(results, dict):
        results = {}
    else:
        results = annotate_wcag_mappings(results)

    summary = scan_results.get("summary") or {}
    verapdf_status = scan_results.get("verapdfStatus")

    if verapdf_status is None:
        verapdf_status = build_verapdf_status(results)

    if not summary or "totalIssues" not in summary:
        try:
            summary = PDFAccessibilityAnalyzer.calculate_summary(results, verapdf_status)
        except Exception as calc_error:
            logger.warning(
                "[Backend] Warning: unable to regenerate summary for export (%s): %s",
                scan_row.get("id"),
                calc_error,
            )
            canonical_list = results.get("issues") if isinstance(results, dict) else None
            canonical_count = len(canonical_list) if isinstance(canonical_list, list) else 0
            total_issues = canonical_count or sum(
                len(v) if isinstance(v, list) else 0
                for key, v in results.items()
                if key != "issues"
            )
            summary = {
                "totalIssues": total_issues,
                "totalIssuesRaw": total_issues,
                "highSeverity": 0,
                "issuesRemaining": total_issues,
                "remainingIssues": total_issues,
                "issuesRemainingRaw": total_issues,
                "complianceScore": max(0, 100 - total_issues * 2),
            }

    if isinstance(summary, dict) and verapdf_status:
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))
        # PDF/A compliance is intentionally omitted; we aggregate only WCAG and PDF/UA scores now.
        combined_score = _combine_compliance_scores(
            summary.get("wcagCompliance"),
            summary.get("pdfuaCompliance"),
        )
        if combined_score is not None:
            summary["complianceScore"] = combined_score

    criteria_summary = scan_results.get("criteriaSummary")
    if not isinstance(criteria_summary, dict):
        criteria_summary = build_criteria_summary(results)

    latest_fix = None
    if scan_row.get("applied_at"):
        fix_list = _deserialize_json_field(scan_row.get("fixes_applied"), [])
        latest_fix = {
            "fixedFilename": scan_row.get("fixed_filename"),
            "fixType": scan_row.get("fix_type"),
            "appliedAt": scan_row.get("applied_at").isoformat()
            if scan_row.get("applied_at")
            else None,
            "fixesApplied": fix_list,
            "issuesAfter": scan_row.get("issues_after"),
            "complianceAfter": scan_row.get("compliance_after"),
        }

    upload_date = scan_row.get("upload_date") or scan_row.get("uploadDate")
    if isinstance(upload_date, datetime):
        upload_date = upload_date.isoformat()

    return {
        "scanId": scan_row.get("id"),
        "filename": scan_row.get("filename"),
        "status": scan_row.get("status"),
        "uploadDate": upload_date,
        "batchId": scan_row.get("batch_id") or scan_row.get("batchId"),
        "folderId": scan_row.get("batch_id") or scan_row.get("batchId"),
        "groupId": scan_row.get("group_id") or scan_row.get("groupId"),
        "groupName": scan_row.get("group_name") or scan_row.get("groupName"),
        "folderName": (
            scan_row.get("folder_name")
            or scan_row.get("folderName")
            or scan_row.get("batch_name")
            or scan_row.get("batchName")
        ),
        "summary": summary or {},
        "results": results,
        "verapdfStatus": verapdf_status,
        "issues": {
            "total": scan_row.get("total_issues"),
            "fixed": scan_row.get("issues_fixed"),
            "remaining": scan_row.get("issues_remaining"),
        },
        "latestFix": latest_fix,
        "criteriaSummary": criteria_summary,
    }

def update_group_file_count(group_id: str):
    """Update the file_count for a group based on actual scans."""
    try:
        execute_query(
            """
            UPDATE groups
            SET file_count = (
                SELECT COUNT(*)
                FROM scans
                WHERE group_id = %s
            )
            WHERE id = %s
        """,
            (group_id, group_id),
            fetch=False,
        )
        logger.info("[Backend] ✓ Updated file count for group %s", group_id)
    except Exception:
        logger.exception("[Backend] Error updating group file count for %s", group_id)

def save_scan_to_db(
    scan_id: str,
    original_filename: str,
    scan_results: Dict[str, Any],
    batch_id: Optional[str] = None,
    group_id: Optional[str] = None,
    is_update: bool = False,
    status: str = "completed",
    upload_date: Optional[datetime] = None,
    total_issues: Optional[int] = None,
    issues_fixed: Optional[int] = None,
    issues_remaining: Optional[int] = None,
    file_path: Optional[str] = None,
):
    """
    Insert or update a scan record while keeping compatibility with older schemas.
    Returns saved scan_id or raises on error.
    """
    payload_dict = scan_results if isinstance(scan_results, dict) else {}
    payload_dict = _ensure_scan_results_compliance(payload_dict)
    summary = payload_dict.get("summary", {}) if isinstance(payload_dict, dict) else {}
    computed_total = (
        total_issues if total_issues is not None else summary.get("totalIssues", 0)
    ) or 0
    computed_fixed = (
        issues_fixed if issues_fixed is not None else summary.get("issuesFixed", 0)
    ) or 0
    computed_remaining = (
        issues_remaining
        if issues_remaining is not None
        else summary.get("issuesRemaining", summary.get("remainingIssues"))
    )
    if computed_remaining is None:
        computed_remaining = max(computed_total - computed_fixed, 0)

    payload_json = _serialize_scan_results(payload_dict)
    timestamp = upload_date or datetime.utcnow()

    try:
        if not is_update:
            execute_query(
                """
                INSERT INTO scans (
                    id,
                    filename,
                    scan_results,
                    batch_id,
                    group_id,
                    status,
                    upload_date,
                    total_issues,
                    issues_remaining,
                    issues_fixed,
                    file_path
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scan_id,
                    original_filename,
                    payload_json,
                    batch_id,
                    group_id,
                    status,
                    timestamp,
                    computed_total,
                    computed_remaining,
                    computed_fixed,
                    file_path,
                ),
            )
        else:
            execute_query(
                """
                UPDATE scans
                SET filename=%s,
                    scan_results=%s,
                    batch_id=%s,
                    group_id=%s,
                    status=%s,
                    upload_date=%s,
                    total_issues=%s,
                    issues_remaining=%s,
                    issues_fixed=%s,
                    file_path=%s
                WHERE id=%s
                """,
                (
                    original_filename,
                    payload_json,
                    batch_id,
                    group_id,
                    status,
                    timestamp,
                    computed_total,
                    computed_remaining,
                    computed_fixed,
                    file_path,
                    scan_id,
                ),
            )
        return scan_id
    except Exception:
        logger.exception("save_scan_to_db failed")
        raise


def _is_skipped_fix_entry(fix: Any) -> bool:
    if not isinstance(fix, dict):
        return False
    if fix.get("skipped") is True:
        return True
    success_flag = fix.get("success")
    if success_flag is False:
        return True
    description = fix.get("description")
    if isinstance(description, str) and "skipp" in description.lower():
        return True
    return False


def _filter_skipped_fixes(fixes: Any) -> List[Dict[str, Any]]:
    if not isinstance(fixes, list):
        return []
    return [fix for fix in fixes if not _is_skipped_fix_entry(fix)]


def _count_successful_fix_entries(fixes: Any) -> int:
    if not isinstance(fixes, list):
        return 0
    count = 0
    for fix in fixes:
        if isinstance(fix, dict):
            if fix.get("success", True) is not False:
                count += 1
        else:
            count += 1
    return count


def save_fix_history(
    scan_id: str,
    original_filename: str,
    fixed_filename: str,
    fixes_applied: List[Dict[str, Any]],
    fix_type: str,
    issues_before: Any,
    issues_after: Any,
    compliance_before: Any,
    compliance_after: Any,
    fix_suggestions: Optional[List[Dict[str, Any]]] = None,
    fix_metadata: Optional[Dict[str, Any]] = None,
    batch_id: Optional[str] = None,
    group_id: Optional[str] = None,
    total_issues_before: Optional[int] = None,
    total_issues_after: Optional[int] = None,
    high_severity_before: Optional[int] = None,
    high_severity_after: Optional[int] = None,
    success_count: Optional[int] = None,
):
    """
    Save fix history record - preserve original names.
    """
    normalized_fixes = _filter_skipped_fixes(fixes_applied or [])
    stored_success_count = (
        success_count
        if success_count is not None
        else _count_successful_fix_entries(normalized_fixes)
    )
    try:
        original_file = original_filename or fixed_filename or "unknown.pdf"
        fixed_file = fixed_filename or original_filename or "fixed.pdf"
        execute_query(
            """
            INSERT INTO fix_history (
                scan_id,
                batch_id,
                group_id,
                original_file,
                fixed_file,
                original_filename,
                fixed_filename,
                fix_type,
                fixes_applied,
                fix_suggestions,
                issues_before,
                issues_after,
                total_issues_before,
                total_issues_after,
                high_severity_before,
                high_severity_after,
                compliance_before,
                compliance_after,
                success_count,
                fix_metadata,
                applied_at
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
            )
            """,
            (
                scan_id,
                batch_id,
                group_id,
                original_file,
                fixed_file,
                original_filename,
                fixed_filename,
                fix_type,
                json.dumps(normalized_fixes),
                json.dumps(fix_suggestions or []),
                json.dumps(issues_before),
                json.dumps(issues_after),
                total_issues_before,
                total_issues_after,
                high_severity_before,
                high_severity_after,
                compliance_before,
                compliance_after,
                stored_success_count,
                json.dumps(fix_metadata or {}),
            ),
        )
    except Exception:
        logger.exception("save_fix_history failed")
        raise

def update_scan_status(scan_id: str, status: str = "completed"):
    try:
        execute_query(
            "UPDATE scans SET status=%s WHERE id=%s",
            (status, scan_id),
        )
    except Exception:
        logger.exception("update_scan_status failed")
        raise

def _truthy(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def _fixed_scan_dir(scan_id, ensure_exists=False):
    path = Path(FIXED_FOLDER) / str(scan_id)
    if ensure_exists:
        path.mkdir(parents=True, exist_ok=True)
    return path

def _sanitize_version_base(original_name, fallback):
    candidate = ""
    if original_name:
        candidate = Path(original_name).stem
    candidate = secure_filename(candidate) if candidate else ""
    if not candidate:
        candidate = secure_filename(str(fallback)) or str(fallback)
    return candidate

def _extract_version_from_path(path_obj: Path):
    match = VERSION_FILENAME_PATTERN.search(path_obj.name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def _fixed_metadata_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".json")


def _write_fixed_metadata(pdf_path: Path, metadata: Dict[str, Any]):
    meta_path = _fixed_metadata_path(pdf_path)
    if not metadata:
        if meta_path.exists():
            try:
                meta_path.unlink()
            except Exception:
                logger.warning("[Backend] Failed to remove metadata for %s", pdf_path)
        return
    try:
        with meta_path.open("w", encoding="utf-8") as meta_file:
            json.dump(metadata, meta_file)
    except Exception:
        logger.warning("[Backend] Failed to record metadata for %s", pdf_path)


def _read_fixed_metadata(pdf_path: Path) -> Dict[str, Any]:
    meta_path = _fixed_metadata_path(pdf_path)
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open("r", encoding="utf-8") as meta_file:
            return json.load(meta_file)
    except Exception:
        logger.warning("[Backend] Failed to read metadata for %s", pdf_path)
        return {}


def get_versioned_files(scan_id: str):
    scan_dir = _fixed_scan_dir(scan_id, ensure_exists=False)
    if not scan_dir.exists():
        return []
    base_dir = Path(FIXED_FOLDER)
    entries = []
    for path in scan_dir.glob("*.pdf"):
        version_number = _extract_version_from_path(path)
        if version_number is None:
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        metadata = _read_fixed_metadata(path)
        entries.append(
            {
                "version": version_number,
                "absolute_path": str(path.resolve()),
                "relative_path": str(path.relative_to(base_dir)),
                "filename": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "remote_path": metadata.get("remote_path"),
            }
        )
    # sort by version asc
    entries.sort(key=lambda e: e["version"])
    return entries


def lookup_remote_fixed_entry(
    scan_id: str, target_relative: Optional[str] = None, version: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Inspect fix history for remote storage references when local fixed files are unavailable.
    """
    try:
        rows = execute_query(
            """
            SELECT fixed_filename, fix_metadata
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY applied_at DESC
            LIMIT 50
            """,
            (scan_id,),
            fetch=True,
        )
    except Exception:
        logger.exception("[Backend] lookup_remote_fixed_entry failed for %s", scan_id)
        return None

    if not rows:
        return None

    normalized_target = None
    target_filename = None
    if target_relative:
        normalized_target = str(Path(target_relative).as_posix())
        target_filename = Path(target_relative).name

    for row in rows:
        metadata_raw = row.get("fix_metadata")
        metadata = {}
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except Exception:
                metadata = {}
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw

        relative_path = metadata.get("relativePath")
        remote_path = metadata.get("remotePath")
        entry_version = metadata.get("version")
        filename = (
            Path(relative_path).name
            if relative_path
            else row.get("fixed_filename")
        )

        if version is not None and entry_version != version:
            continue
        if normalized_target and relative_path:
            if relative_path != normalized_target:
                continue
        elif target_filename and filename:
            if filename != target_filename:
                continue

        if remote_path or relative_path:
            return {
                "remote_path": remote_path,
                "relative_path": relative_path,
                "filename": filename,
                "version": entry_version,
            }

    return None

def _uploads_root() -> Path:
    return UPLOAD_FOLDER_PATH

def _fixed_root() -> Path:
    return FIXED_FOLDER_PATH

def _ensure_local_storage(context: str = ""):
    """Ensure uploads/fixed directories exist."""
    try:
        _uploads_root().mkdir(parents=True, exist_ok=True)
        _fixed_root().mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("[Backend] Failed to ensure local storage for %s", context)

def _temp_storage_root() -> Path:
    TEMP_UPLOAD_DIR_PATH.mkdir(parents=True, exist_ok=True)
    return TEMP_UPLOAD_DIR_PATH

def _mirror_file_to_remote(local_path: Path, folder: str) -> Optional[str]:
    """
    Upload a local file to remote storage (if configured) and return the remote path.
    """
    if not local_path or not local_path.exists():
        return None
    try:
        result = upload_file_with_fallback(
            str(local_path), local_path.name, folder=folder
        )
        storage_type = result.get("storage")
        remote_identifier = (
            result.get("key") or result.get("path") or result.get("url")
        )
        if storage_type == "local" or not remote_identifier:
            raise RuntimeError(
                "Remote storage upload failed or is not configured properly"
            )
        return remote_identifier
    except Exception:
        logger.exception(
            "[Storage] Failed to mirror %s to remote folder '%s'",
            local_path,
            folder,
        )
        return None

def _download_remote_to_temp(remote_identifier: str, scan_id: str) -> Optional[Path]:
    """
    Download a remote file (URL or storage key) into the temp directory for processing.
    """
    if not remote_identifier:
        return None
    tmp_dir = _temp_storage_root()
    suffix = Path(remote_identifier).suffix or ".pdf"
    safe_prefix = secure_filename(scan_id) or scan_id or "scan"
    tmp_path = tmp_dir / f"{safe_prefix}_{uuid.uuid4().hex}{suffix}"
    try:
        logger.info(
            "[Storage] Downloading remote file for scan %s from %s",
            scan_id,
            remote_identifier,
        )
        download_remote_file(remote_identifier, tmp_path)
        if tmp_path.exists():
            logger.info(
                "[Storage] Remote download complete for scan %s -> %s",
                scan_id,
                tmp_path,
            )
            return tmp_path
        return None
    except FileNotFoundError:
        logger.warning(
            "[Storage] Remote reference not found for scan %s: %s",
            scan_id,
            remote_identifier,
        )
        return None
    except Exception:
        logger.exception(
            "[Storage] Failed to download remote file %s for scan %s",
            remote_identifier,
            scan_id,
        )
        return None

def build_placeholder_scan_payload(filename: Optional[str] = None) -> Dict[str, Any]:
    base_status = build_verapdf_status({})
    summary = {
        "totalIssues": 0,
        "highSeverity": 0,
        "mediumSeverity": 0,
        "lowSeverity": 0,
        "wcagCompliance": base_status.get("wcagCompliance"),
        "pdfuaCompliance": base_status.get("pdfuaCompliance"),
        "complianceScore": _combine_compliance_scores(
            base_status.get("wcagCompliance"),
            base_status.get("pdfuaCompliance"),
        )
        or 0,
        "status": "queued",
    }
    if filename:
        summary["filename"] = filename
    return {
        "results": {},
        "summary": summary,
        "verapdfStatus": base_status,
        "fixes": [],
        "criteriaSummary": {},
    }

def should_scan_now(
    scan_mode: Optional[str] = None, request: Optional[Request] = None
) -> bool:
    """Determine whether files should be scanned immediately."""
    mode = (scan_mode or "").strip().lower()
    if not mode and request:
        header_mode = request.headers.get("x-scan-mode")
        if header_mode:
            mode = header_mode.strip().lower()
        elif "scan_mode" in request.query_params:
            mode = request.query_params.get("scan_mode", "").strip().lower()
    if not mode:
        return True
    return mode not in {"upload_only", "deferred", "defer"}

def _serialize_scan_results(payload: Dict[str, Any]) -> str:
    return json.dumps(to_json_safe(payload))

def _combine_compliance_scores(*scores: Optional[float]) -> Optional[float]:
    numeric = [s for s in scores if isinstance(s, (int, float))]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 2)

def _ensure_scan_results_compliance(scan_results: Dict[str, Any]) -> Dict[str, Any]:
    """Keep summary fields in sync with WCAG validator metrics and VeraPDF advisories."""
    if not isinstance(scan_results, dict):
        return scan_results

    summary = scan_results.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        scan_results["summary"] = summary

    derived_wcag = derive_wcag_score(
        scan_results.get("results"),
        scan_results.get("criteriaSummary"),
    )
    if derived_wcag is not None:
        summary["wcagCompliance"] = derived_wcag

    verapdf_status = scan_results.get("verapdfStatus")
    if isinstance(verapdf_status, dict):
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

    combined_score = _combine_compliance_scores(
        summary.get("wcagCompliance"), summary.get("pdfuaCompliance")
    )
    if combined_score is not None:
        summary["complianceScore"] = combined_score

    return scan_results

async def _analyze_pdf_document(file_path: Path) -> Dict[str, Any]:
    """
    Run the PDF accessibility analyzer for the given file and return the normalized payload.
    """
    try:
        analyzer = PDFAccessibilityAnalyzer()
    except Exception:
        logger.exception("[Backend] Failed to initialize PDFAccessibilityAnalyzer")
        return {"results": {}, "summary": {}, "verapdfStatus": None, "fixes": []}

    analyze_fn = getattr(analyzer, "analyze", None)
    scan_results: Dict[str, Any] = {}

    if analyze_fn:
        try:
            if asyncio.iscoroutinefunction(analyze_fn):
                scan_results = await analyze_fn(str(file_path))
            else:
                scan_results = await asyncio.to_thread(analyze_fn, str(file_path))
        except Exception:
            logger.exception("[Backend] Analyzer analyze() failed for %s", file_path)
            scan_results = {}
    else:
        logger.warning(
            "PDFAccessibilityAnalyzer.analyze not found; returning empty results"
        )
        scan_results = {}

    if not isinstance(scan_results, dict):
        scan_results = {}
    else:
        scan_results = annotate_wcag_mappings(scan_results)

    # Analyzer results contain the custom WCAG validator findings. We still
    # synthesize VeraPDF-style stats so the UI can show advisory counts, but
    # they remain secondary to the native WCAG/PDF-UA pipeline.
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
        logger.exception("calculate_summary failed")
        summary = {}

    wcag_metrics = None
    metrics_getter = getattr(analyzer, "get_wcag_validator_metrics", None)
    if callable(metrics_getter):
        try:
            wcag_metrics = metrics_getter()
        except Exception:
            wcag_metrics = None

    if isinstance(summary, dict) and isinstance(wcag_metrics, dict):
        # WCAG validator drives the primary compliance score; VeraPDF stays advisory.
        summary["wcagCompliance"] = wcag_metrics.get("wcagScore", summary.get("wcagCompliance"))
        summary["pdfuaCompliance"] = wcag_metrics.get("pdfuaScore", summary.get("pdfuaCompliance"))
        if wcag_metrics.get("wcagCompliance"):
            summary["wcagLevels"] = wcag_metrics["wcagCompliance"]
        if wcag_metrics.get("pdfuaCompliance"):
            summary["pdfuaLevels"] = wcag_metrics["pdfuaCompliance"]

    if isinstance(summary, dict) and verapdf_status:
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

    try:
        fix_suggestions = (
            generate_fix_suggestions(scan_results)
            if callable(generate_fix_suggestions)
            else []
        )
    except Exception:
        logger.exception("generate_fix_suggestions failed")
        fix_suggestions = []

    criteria_summary = build_criteria_summary(scan_results)
    if isinstance(summary, dict):
        derived_wcag = derive_wcag_score(scan_results, criteria_summary)
        if derived_wcag is not None:
            summary["wcagCompliance"] = derived_wcag
            combined_score = _combine_compliance_scores(
                summary.get("wcagCompliance"),
                summary.get("pdfuaCompliance"),
            )
            if combined_score is not None:
                summary["complianceScore"] = combined_score

    return {
        "results": scan_results,
        "summary": summary if isinstance(summary, dict) else {},
        "verapdfStatus": verapdf_status,
        "fixes": fix_suggestions,
        "criteriaSummary": criteria_summary,
    }

def _fetch_scan_record(scan_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a scan row by its primary id. Returns None if no record exists.
    """
    if not NEON_DATABASE_URL:
        return None

    rows = execute_query(
        """
        SELECT
            id,
            filename,
            group_id,
            batch_id,
            scan_results,
            status,
            file_path,
            upload_date,
            created_at,
            total_issues,
            issues_fixed,
            issues_remaining
        FROM scans
        WHERE id = %s
        LIMIT 1
        """,
        (scan_id,),
        fetch=True,
    )
    return rows[0] if rows else None

def get_scan_by_id(scan_id: str) -> Optional[Dict[str, Any]]:
    """Legacy compatibility wrapper."""
    return _fetch_scan_record(scan_id)

def _resolve_scan_file_path(
    scan_id: str, scan_record: Optional[Dict[str, Any]] = None
) -> Optional[Path]:
    """
    Try common filename patterns to find the uploaded PDF on disk.
    """
    if not scan_record and NEON_DATABASE_URL:
        scan_record = _fetch_scan_record(scan_id)

    remote_candidates: List[Tuple[str, str]] = []

    latest_fixed = get_fixed_version(scan_id)
    if latest_fixed:
        fixed_path = latest_fixed.get("absolute_path")
        if fixed_path:
            path_obj = Path(fixed_path)
            if path_obj.exists():
                return path_obj
        remote_reference = latest_fixed.get("remote_path")
        if remote_reference:
            remote_candidates.append(("fixed_version", remote_reference))

    remote_history_entry = lookup_remote_fixed_entry(scan_id)
    if remote_history_entry:
        remote_reference = remote_history_entry.get("remote_path")
        if remote_reference:
            remote_candidates.append(("fix_history", remote_reference))

    remote_references: List[str] = []

    for label, remote_identifier in remote_candidates:
        if not remote_identifier:
            continue
        logger.info(
            "[Storage] Attempting remote resolution for %s via %s: %s",
            scan_id,
            label,
            remote_identifier,
        )
        try:
            downloaded = _download_remote_to_temp(remote_identifier, scan_id)
        except Exception:
            logger.exception(
                "[Storage] Remote resolution failed for %s via %s",
                scan_id,
                label,
            )
            downloaded = None
        if downloaded and downloaded.exists():
            return downloaded
        remote_references.append(remote_identifier)

    upload_dir = _uploads_root()
    candidates: List[Path] = [
        upload_dir / f"{scan_id}.pdf",
        upload_dir / scan_id,
    ]

    if scan_record:
        filename = scan_record.get("filename")
        if filename:
            candidates.append(upload_dir / filename)

        stored_values: List[str] = []
        file_path_value = scan_record.get("file_path")
        if file_path_value:
            stored_values.append(str(file_path_value))
        legacy_path = scan_record.get("path")
        if legacy_path:
            stored_values.append(str(legacy_path))
        parsed_results = _parse_scan_results_json(scan_record.get("scan_results"))
        if isinstance(parsed_results, dict):
            for candidate_key in ("filePath", "file_path", "path"):
                candidate_value = parsed_results.get(candidate_key)
                if candidate_value:
                    stored_values.append(str(candidate_value))

        seen_values: Set[str] = set()

        def _looks_like_remote_identifier(value: str) -> bool:
            normalized = value.strip()
            if not normalized:
                return False
            lowered = normalized.lower()
            if lowered.startswith(("http://", "https://")):
                return True
            if lowered.startswith(("uploads/", "fixed/")):
                return True
            return False

        def _process_stored_reference(reference: str):
            cleaned = reference.strip()
            if not cleaned or cleaned in seen_values:
                return
            seen_values.add(cleaned)
            if _looks_like_remote_identifier(cleaned):
                remote_references.append(cleaned)
                return
            path_obj = Path(cleaned)
            candidates.append(path_obj)
            if not path_obj.exists() and not path_obj.is_absolute():
                remote_references.append(cleaned)

        for stored_value in stored_values:
            _process_stored_reference(stored_value)

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate

    for remote_ref in remote_references:
        remote_file = _download_remote_to_temp(remote_ref, scan_id)
        if remote_file and remote_file.exists():
            return remote_file
    logger.error(
        "[Backend] Unable to resolve file path for scan %s; tried %s and remote refs %s",
        scan_id,
        [str(c) for c in candidates],
        remote_references,
    )
    return None

def resolve_uploaded_file_path(
    scan_id: str, scan_record: Optional[Dict[str, Any]] = None
) -> Optional[Path]:
    """Compatibility wrapper used by legacy code paths."""
    return _resolve_scan_file_path(scan_id, scan_record)


def update_scan_file_reference(scan_id: str, reference: Optional[str]):
    """
    Persist the canonical file reference (usually a remote storage key) for a scan.
    """
    try:
        execute_query(
            "UPDATE scans SET file_path = %s WHERE id = %s",
            (reference, scan_id),
            fetch=False,
        )
    except Exception:
        logger.exception("[Backend] Failed to update file reference for scan %s", scan_id)

def scan_results_changed(
    *,
    issues_before: Optional[Dict[str, Any]],
    summary_before: Optional[Dict[str, Any]],
    compliance_before: Optional[float],
    issues_after: Optional[Dict[str, Any]],
    summary_after: Optional[Dict[str, Any]],
    compliance_after: Optional[float],
) -> bool:
    """Detect whether scan result payloads changed in a meaningful way."""
    if compliance_before != compliance_after:
        return True
    before_summary = to_json_safe(summary_before or {})
    after_summary = to_json_safe(summary_after or {})
    if before_summary != after_summary:
        return True
    before_issues = to_json_safe(issues_before or {})
    after_issues = to_json_safe(issues_after or {})
    return before_issues != after_issues

def archive_fixed_pdf_version(
    *,
    scan_id: str,
    original_filename: Optional[str],
    source_path: Optional[Path],
) -> Optional[Dict[str, Any]]:
    """Copy the provided PDF into the versioned fixed directory."""
    if not source_path or not Path(source_path).exists():
        return None
    scan_dir = _fixed_scan_dir(scan_id, ensure_exists=True)
    existing_versions = get_versioned_files(scan_id)
    next_version = existing_versions[-1]["version"] + 1 if existing_versions else 1
    base_name = _sanitize_version_base(original_filename, scan_id)
    dest_name = f"{base_name}_v{next_version}.pdf"
    dest_path = scan_dir / dest_name
    try:
        shutil.copy2(source_path, dest_path)
    except Exception:
        logger.exception(
            "[Backend] Failed to archive fixed PDF for %s into %s", scan_id, dest_path
        )
        return None

    try:
        stat = dest_path.stat()
    except FileNotFoundError:
        return None

    remote_path = _mirror_file_to_remote(dest_path, folder=f"fixed/{scan_id}")
    if not remote_path:
        raise RuntimeError("Remote storage reference missing for fixed PDF")
    metadata = {"remote_path": remote_path}
    _write_fixed_metadata(dest_path, metadata)

    relative_path = dest_path.relative_to(_fixed_root())
    return {
        "version": next_version,
        "filename": dest_path.name,
        "absolute_path": str(dest_path),
        "relative_path": str(relative_path),
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "remote_path": remote_path,
    }

def get_fixed_version(scan_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Return the latest or specific fixed file entry for a scan if present."""
    version_entries = get_versioned_files(scan_id)
    if version_entries:
        if version is None:
            latest = version_entries[-1]
            return {
                "version": latest.get("version"),
                "filename": latest.get("filename"),
                "absolute_path": latest.get("absolute_path"),
                "relative_path": latest.get("relative_path"),
                "remote_path": latest.get("remote_path"),
            }
        match = next((entry for entry in version_entries if entry.get("version") == version), None)
        if match:
            return {
                "version": match.get("version"),
                "filename": match.get("filename"),
                "absolute_path": match.get("absolute_path"),
                "relative_path": match.get("relative_path"),
                "remote_path": match.get("remote_path"),
            }

    fixed_dir = _fixed_root()
    for ext in ("", ".pdf"):
        candidate = fixed_dir / f"{scan_id}{ext}"
        if candidate.exists():
            relative = candidate.relative_to(fixed_dir)
            metadata = _read_fixed_metadata(candidate)
            return {
                "version": 1,
                "filename": candidate.name,
                "absolute_path": str(candidate),
                "relative_path": str(relative),
                "remote_path": metadata.get("remote_path"),
            }
    return None

def prune_fixed_versions(scan_id: str, keep_latest: bool = True) -> Dict[str, Any]:
    """
    Delete older fixed PDF versions for a scan.
    Returns metadata about removed files and remaining versions.
    """
    entries = get_versioned_files(scan_id)
    removed_files: List[str] = []

    if not entries:
        return {"removed": 0, "removedFiles": [], "remainingVersions": []}

    to_keep = 1 if keep_latest else 0
    if to_keep >= len(entries):
        return {"removed": 0, "removedFiles": [], "remainingVersions": entries}

    to_remove = entries[: len(entries) - to_keep]
    for entry in to_remove:
        path_value = entry.get("absolute_path")
        if not path_value:
            continue
        try:
            path_obj = Path(path_value)
            os.remove(path_obj)
            meta_path = _fixed_metadata_path(path_obj)
            if meta_path.exists():
                meta_path.unlink()
            removed_files.append(entry.get("filename", os.path.basename(path_value)))
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("[Backend] Failed to remove fixed version %s", path_value)

    remaining = get_versioned_files(scan_id)
    return {
        "removed": len(removed_files),
        "removedFiles": removed_files,
        "remainingVersions": remaining,
    }

def _perform_automated_fix(
    scan_id: str,
    payload: Optional[Dict[str, Any]] = None,
    expected_batch_id: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Apply automated fixes to a scan and update database state."""
    conn = None
    cursor = None
    tracker = get_progress_tracker(scan_id) or create_progress_tracker(scan_id)
    payload = payload or {}

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT id, filename, batch_id, group_id, scan_results,
                   file_path,
                   COALESCE(total_issues, 0) AS total_issues,
                   COALESCE(issues_fixed, 0) AS issues_fixed,
                   COALESCE(issues_remaining, 0) AS issues_remaining
            FROM scans
            WHERE id = %s
            """,
            (scan_id,),
        )
        scan_row = cursor.fetchone()
        if not scan_row:
            return 404, {
                "success": False,
                "error": f"Scan {scan_id} not found",
            }

        if expected_batch_id and scan_row.get("batch_id") != expected_batch_id:
            return 400, {
                "success": False,
                "error": f"Scan {scan_id} does not belong to batch {expected_batch_id}",
            }

        initial_scan_payload = scan_row.get("scan_results")
        if isinstance(initial_scan_payload, str):
            try:
                initial_scan_payload = json.loads(initial_scan_payload)
            except Exception:
                initial_scan_payload = {}
        elif not isinstance(initial_scan_payload, dict):
            initial_scan_payload = {}
        initial_summary = (
            initial_scan_payload.get("summary", {})
            if isinstance(initial_scan_payload, dict)
            else {}
        )

        resolved_path = _resolve_scan_file_path(scan_id, scan_row)
        if resolved_path and resolved_path.exists():
            scan_row["resolved_file_path"] = str(resolved_path)
        else:
            logger.warning("[Backend] Could not resolve file path for fix %s", scan_id)
        engine = AutoFixEngine()
        result = engine.apply_automated_fixes(scan_id, scan_row, tracker=tracker)
        if not result.get("success"):
            if tracker:
                tracker.fail_all(result.get("error", "Automated fix failed"))
            return 500, {
                "success": False,
                "error": result.get("error", "Automated fix failed"),
                "scanId": scan_id,
            }

        archive_info = None
        temp_fixed_path = result.get("fixedTempPath")
        if temp_fixed_path:
            temp_path_obj = Path(temp_fixed_path)
            if temp_path_obj.exists():
                try:
                    archive_info = archive_fixed_pdf_version(
                        scan_id=scan_id,
                        original_filename=scan_row.get("filename"),
                        source_path=temp_path_obj,
                    )
                except Exception as archive_exc:
                    logger.exception(
                        "[Backend] Failed to archive fixed PDF for %s", scan_id
                    )
                    if tracker:
                        tracker.fail_all(str(archive_exc))
                    return 500, {
                        "success": False,
                        "error": str(archive_exc),
                        "scanId": scan_id,
                    }
                if archive_info:
                    result["fixedFile"] = archive_info.get("relative_path")
                    result["fixedFileRemote"] = archive_info.get("remote_path")
                    result["fixedVersion"] = archive_info.get("version")
                    try:
                        temp_path_obj.unlink(missing_ok=True)
                    except Exception:
                        logger.warning(
                            "[Backend] Could not remove temp fixed file %s",
                            temp_path_obj,
                        )
                else:
                    logger.warning(
                        "[Backend] Failed to archive fixed PDF for %s; leaving temp file at %s",
                        scan_id,
                        temp_path_obj,
                    )
                if archive_info and archive_info.get("remote_path"):
                    try:
                        update_scan_file_reference(
                            scan_id, archive_info.get("remote_path")
                        )
                    except Exception:
                        logger.exception(
                            "[Backend] Failed to persist remote reference for %s",
                            scan_id,
                        )

        result.pop("fixedTempPath", None)

        if tracker:
            tracker.complete_all()

        raw_fixes_applied = result.get("fixesApplied") or []
        filtered_fixes_applied = _filter_skipped_fixes(raw_fixes_applied)
        result["fixesApplied"] = filtered_fixes_applied
        successful_fixes = [
            fix for fix in filtered_fixes_applied if fix.get("success", True) is not False
        ]
        success_count = len(successful_fixes)
        skipped_fix_count = max(len(raw_fixes_applied) - len(filtered_fixes_applied), 0)

        scan_results_payload = result.get("scanResults")
        suggested_fixes = []
        if isinstance(scan_results_payload, dict):
            suggested_fixes = scan_results_payload.get("fixes") or result.get("fixes") or []
            scan_results_payload.setdefault("fixes", suggested_fixes)
        else:
            suggested_fixes = result.get("fixes") or []
            scan_results_payload = {
                "results": result.get("results"),
                "summary": result.get("summary"),
                "verapdfStatus": result.get("verapdfStatus"),
                "fixes": suggested_fixes,
            }
        scan_results_payload["fixesApplied"] = filtered_fixes_applied
        summary = scan_results_payload.get("summary") or result.get("summary") or {}
        reported_remaining = summary.get("totalIssues") or 0
        total_issues_before = scan_row.get("total_issues") or reported_remaining
        issues_fixed = success_count
        estimated_remaining = max(total_issues_before - issues_fixed, 0)
        remaining_issues = max(reported_remaining, estimated_remaining)
        total_issues_after = remaining_issues + issues_fixed
        summary["totalIssues"] = total_issues_after
        summary["issuesRemaining"] = remaining_issues
        summary["issuesFixed"] = issues_fixed
        skipped_issue_delta = max(remaining_issues - reported_remaining, 0)
        if skipped_issue_delta > 0:
            summary["skippedIssues"] = skipped_issue_delta
        if skipped_fix_count:
            summary["skippedFixes"] = skipped_fix_count
        status = "fixed" if remaining_issues == 0 else "processed"
        result["successCount"] = success_count

        scan_results_payload = _ensure_scan_results_compliance(scan_results_payload)

        cursor.execute(
            """
            UPDATE scans
            SET scan_results = %s,
                status = %s,
                issues_fixed = %s,
                issues_remaining = %s,
                total_issues = %s
            WHERE id = %s
            """,
            (
                _serialize_scan_results(scan_results_payload),
                status,
                issues_fixed,
                remaining_issues,
                max(total_issues_before, remaining_issues),
                scan_id,
            ),
        )

        fixes_applied = filtered_fixes_applied
        fix_metadata = {"automated": True}
        if archive_info:
            fix_metadata.update(
                {
                    "version": archive_info.get("version"),
                    "versionLabel": f"V{archive_info.get('version')}",
                    "relativePath": archive_info.get("relative_path"),
                    "storedFilename": archive_info.get("filename"),
                    "fileSize": archive_info.get("size"),
                    "remotePath": archive_info.get("remote_path"),
                }
            )
        if success_count > 0:
            try:
                save_fix_history(
                    scan_id=scan_id,
                    original_filename=scan_row.get("filename"),
                    fixed_filename=result.get("fixedFile") or scan_row.get("filename"),
                    fixes_applied=fixes_applied,
                    fix_type="automated",
                    issues_before=initial_scan_payload.get("results")
                    if isinstance(initial_scan_payload, dict)
                    else {},
                    issues_after=scan_results_payload.get("results"),
                    compliance_before=initial_summary.get("complianceScore"),
                    compliance_after=summary.get("complianceScore"),
                    fix_suggestions=scan_results_payload.get("fixes"),
                    fix_metadata=fix_metadata,
                    batch_id=scan_row.get("batch_id"),
                    group_id=scan_row.get("group_id"),
                    total_issues_before=total_issues_before,
                    total_issues_after=remaining_issues,
                    high_severity_before=initial_summary.get("highSeverity"),
                    high_severity_after=summary.get("highSeverity"),
                    success_count=success_count,
                )
            except Exception:
                logger.exception("[Backend] Failed to record fix history for %s", scan_id)

        conn.commit()

        batch_id = scan_row.get("batch_id")
        if batch_id:
            update_batch_statistics(batch_id)

        response_payload = {
            "success": True,
            "scanId": scan_id,
            "batchId": batch_id,
            "summary": summary,
            "results": scan_results_payload.get("results"),
            "verapdfStatus": scan_results_payload.get("verapdfStatus"),
            "fixesApplied": fixes_applied,
            "fixedFile": result.get("fixedFile"),
            "fixedFileRemote": result.get("fixedFileRemote"),
            "fixedVersion": result.get("fixedVersion"),
            "successCount": success_count,
            "message": result.get("message", "Automated fixes applied"),
        }
        return 200, response_payload
    except Exception as exc:
        if conn:
            conn.rollback()
        if tracker:
            tracker.fail_all(str(exc))
        logger.exception("[Backend] Error performing automated fix for %s", scan_id)
        return 500, {
            "success": False,
            "error": str(exc),
            "scanId": scan_id,
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def build_verapdf_status(results, analyzer=None):
    """Approximate VeraPDF compliance so UI can show advisory statistics."""
    status = {
        "isActive": False,
        "wcagCompliance": None,
        "pdfuaCompliance": None,
        "totalVeraPDFIssues": 0,
    }
    if analyzer and hasattr(analyzer, "get_verapdf_status"):
        try:
            computed = analyzer.get_verapdf_status()
            if computed:
                return computed
        except Exception:
            logger.exception("analyzer.get_verapdf_status failed")
    if not isinstance(results, dict):
        return status

    canonical = results.get("issues")
    if isinstance(canonical, list) and canonical:
        seen = set()
        wcag_issues = 0
        pdfua_issues = 0
        for issue in canonical:
            if not isinstance(issue, dict):
                continue
            issue_id = issue.get("issueId")
            if issue_id and issue_id in seen:
                continue
            if issue_id:
                seen.add(issue_id)
            if issue.get("criterion"):
                wcag_issues += 1
            if issue.get("clause"):
                pdfua_issues += 1
        total = wcag_issues + pdfua_issues
    else:
        wcag_issues = len(results.get("wcagIssues", []))
        pdfua_issues = len(results.get("pdfuaIssues", []))
        for category in CATEGORY_CRITERIA_MAP:
            category_issues = results.get(category)
            if isinstance(category_issues, list):
                wcag_issues += len(category_issues)
        total = wcag_issues + pdfua_issues
    status["totalVeraPDFIssues"] = total
    if total == 0:
        status["isActive"] = True
        status["wcagCompliance"] = 100
        status["pdfuaCompliance"] = 100
        return status
    if wcag_issues or pdfua_issues:
        status["isActive"] = True
        status["wcagCompliance"] = max(0, 100 - wcag_issues * 10)
        status["pdfuaCompliance"] = max(0, 100 - pdfua_issues * 10)
    return status

def _delete_scan_with_files(scan_id: str) -> Dict[str, Any]:
    """Remove a scan record, its history, and associated files."""
    logger.info("[Backend] Deleting scan %s", scan_id)

    scan_record = _fetch_scan_record(scan_id)
    if not scan_record:
        raise LookupError("Scan not found")

    resolved_id = scan_record.get("id") or scan_id
    group_id = scan_record.get("group_id")
    batch_id = scan_record.get("batch_id")
    original_filename = scan_record.get("filename")

    uploads_dir = _uploads_root()
    fixed_dir = _fixed_root()
    deleted_local_files = 0
    deleted_remote_files = 0
    remote_references: Set[str] = set()

    def _looks_remote_reference(value: Optional[str]) -> bool:
        if not value:
            return False
        normalized = str(value).strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        if lowered.startswith(("http://", "https://", "s3://", "gs://", "b2://")):
            return True
        if normalized.startswith("uploads/") or normalized.startswith("fixed/"):
            return True
        if not os.path.isabs(normalized) and "/" in normalized:
            return True
        return False

    def _register_remote_reference(value: Optional[str]):
        if not value:
            return
        normalized = str(value).strip()
        if not normalized:
            return
        remote_references.add(normalized)

    def _collect_remote_refs_from_metadata(payload: Any) -> Set[str]:
        refs: Set[str] = set()

        def _walk(node: Any, key_hint: str = ""):
            if isinstance(node, dict):
                for key, child in node.items():
                    next_hint = f"{key_hint}.{key}" if key_hint else str(key)
                    _walk(child, next_hint)
            elif isinstance(node, (list, tuple, set)):
                for child in node:
                    _walk(child, key_hint)
            elif isinstance(node, str):
                hint = key_hint.lower()
                if "remote" in hint or _looks_remote_reference(node):
                    refs.add(node)

        if isinstance(payload, (dict, list, tuple, set)):
            _walk(payload)
        return refs

    def _delete_path(path: Path) -> bool:
        try:
            if path.exists():
                if path.is_file():
                    path.unlink()
                    if path.suffix.lower() == ".pdf":
                        meta_path = _fixed_metadata_path(path)
                        if meta_path.exists():
                            meta_path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                return True
        except Exception:
            logger.exception("[Backend] Failed to delete %s", path)
        return False

    candidate_names = {scan_id, resolved_id}
    if original_filename:
        candidate_names.add(original_filename)

    file_path_reference = scan_record.get("file_path")
    if file_path_reference and _looks_remote_reference(file_path_reference):
        _register_remote_reference(file_path_reference)

    version_entries = get_versioned_files(resolved_id)
    for version_entry in version_entries:
        remote_path = version_entry.get("remote_path")
        if remote_path and _looks_remote_reference(remote_path):
            _register_remote_reference(remote_path)

    fix_history_rows: List[Dict[str, Any]] = []
    try:
        fix_history_rows = execute_query(
            "SELECT fix_metadata FROM fix_history WHERE scan_id = %s AND fix_metadata IS NOT NULL",
            (resolved_id,),
            fetch=True,
        )
    except Exception:
        logger.exception("[Backend] Failed to fetch fix history metadata for %s", scan_id)
        fix_history_rows = []

    for row in fix_history_rows:
        metadata_raw = row.get("fix_metadata")
        metadata: Dict[str, Any] = {}
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except Exception:
                metadata = {}
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw
        for remote_candidate in _collect_remote_refs_from_metadata(metadata):
            if _looks_remote_reference(remote_candidate):
                _register_remote_reference(remote_candidate)

    for remote_reference in sorted(remote_references):
        try:
            if delete_remote_file(remote_reference):
                deleted_remote_files += 1
        except Exception:
            logger.exception(
                "[Backend] Unexpected error deleting remote reference %s", remote_reference
            )

    for folder in (uploads_dir, fixed_dir):
        for name in candidate_names:
            if not name:
                continue
            candidate = folder / name
            if _delete_path(candidate):
                deleted_local_files += 1
            if not name.lower().endswith(".pdf"):
                pdf_candidate = folder / f"{name}.pdf"
                if _delete_path(pdf_candidate):
                    deleted_local_files += 1

    version_dirs = {fixed_dir / str(resolved_id), fixed_dir / str(scan_id)}
    for version_dir in version_dirs:
        if version_dir.exists() and version_dir.is_dir():
            removed_count = sum(
                1 for child in version_dir.glob("**/*") if child.is_file()
            )
            if _delete_path(version_dir):
                deleted_local_files += removed_count

    primary_id = scan_record.get("id")

    if primary_id:
        execute_query(
            "DELETE FROM fix_history WHERE scan_id = %s",
            (primary_id,),
            fetch=False,
        )
    execute_query(
        "DELETE FROM scans WHERE id = %s",
        (primary_id or resolved_id,),
        fetch=False,
    )

    if batch_id:
        try:
            update_batch_statistics(batch_id)
        except Exception:
            logger.exception("[Backend] Failed to refresh batch %s after scan delete", batch_id)

    if group_id:
        update_group_file_count(group_id)

    total_deleted_files = deleted_local_files + deleted_remote_files
    logger.info(
        "[Backend] ✓ Deleted scan %s (removed %d files: %d local, %d remote)",
        scan_id,
        total_deleted_files,
        deleted_local_files,
        deleted_remote_files,
    )
    return {
        "scanId": primary_id or resolved_id,
        "groupId": group_id,
        "deletedFiles": total_deleted_files,
        "deletedLocalFiles": deleted_local_files,
        "deletedRemoteFiles": deleted_remote_files,
        "batchId": batch_id,
    }


def _delete_batch_with_files(batch_id: str) -> Dict[str, Any]:
    """Delete a batch, its scans, and associated files."""
    batch_rows = execute_query(
        "SELECT id, name FROM batches WHERE id = %s", (batch_id,), fetch=True
    )
    if not batch_rows:
        raise LookupError("Batch not found")

    scans = execute_query(
        "SELECT id FROM scans WHERE batch_id = %s", (batch_id,), fetch=True
    ) or []

    deleted_scans = 0
    deleted_files = 0
    affected_groups: Set[str] = set()

    for scan in scans:
        scan_id = scan["id"]
        try:
            result = _delete_scan_with_files(scan_id)
        except LookupError:
            logger.warning(
                "[Backend] Scan %s referenced by batch %s not found during deletion",
                scan_id,
                batch_id,
            )
            continue

        deleted_scans += 1
        deleted_files += result.get("deletedFiles", 0) or 0
        if result.get("groupId"):
            affected_groups.add(result["groupId"])

    execute_query("DELETE FROM batches WHERE id = %s", (batch_id,), fetch=False)

    return {
        "batchId": batch_id,
        "batchName": batch_rows[0].get("name"),
        "deletedScans": deleted_scans,
        "deletedFiles": deleted_files,
        "affectedGroups": list(affected_groups),
    }


def _write_uploadfile_to_disk(upload_file: UploadFile, dest_path: str):
    # upload_file.file is a SpooledTemporaryFile or similar; rewind and copy.
    upload_file.file.seek(0)
    with open(dest_path, "wb") as out_f:
        shutil.copyfileobj(upload_file.file, out_f)


def set_generated_pdfs_folder(path: str) -> None:
    """Update the generated PDFs folder path at runtime."""
    global GENERATED_PDFS_FOLDER
    GENERATED_PDFS_FOLDER = path


__all__ = [
    "SafeJSONResponse",
    "NEON_DATABASE_URL",
    "UPLOAD_FOLDER",
    "FIXED_FOLDER",
    "mount_static_if_available",
    "set_generated_pdfs_folder",
    "build_placeholder_scan_payload",
    "build_verapdf_status",
    "execute_query",
    "get_db_connection",
    "update_batch_statistics",
    "_parse_scan_results_json",
    "_build_scan_export_payload",
    "update_group_file_count",
    "save_scan_to_db",
    "save_fix_history",
    "update_scan_status",
    "_truthy",
    "get_versioned_files",
    "_extract_version_from_path",
    "_uploads_root",
    "_fixed_root",
    "_ensure_local_storage",
    "_temp_storage_root",
    "_mirror_file_to_remote",
    "should_scan_now",
    "_serialize_scan_results",
    "_combine_compliance_scores",
    "_ensure_scan_results_compliance",
    "_analyze_pdf_document",
    "_fetch_scan_record",
    "get_scan_by_id",
    "_resolve_scan_file_path",
    "resolve_uploaded_file_path",
    "update_scan_file_reference",
    "scan_results_changed",
    "archive_fixed_pdf_version",
    "get_fixed_version",
    "lookup_remote_fixed_entry",
    "prune_fixed_versions",
    "_delete_scan_with_files",
    "_delete_batch_with_files",
    "_perform_automated_fix",
    "_write_uploadfile_to_disk",
    "FILE_STATUS_LABELS",
    "normalize_file_status",
    "derive_file_status",
    "remap_status_counts",
]
