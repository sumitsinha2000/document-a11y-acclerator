# backend/app.py

# Standard library imports
import os
import re
import sys
import json
import time
import uuid
import shutil
import zipfile
import asyncio
import logging
import threading
import traceback
import tempfile
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO
from uuid import UUID
from dotenv import load_dotenv

from pydantic import BaseModel

# Third-party imports
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import (
    FastAPI,
    Request,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
    HTTPException,
)
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from werkzeug.utils import secure_filename

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Local application imports
from backend.multi_tier_storage import (
    upload_file_with_fallback,
    download_remote_file,
    stream_remote_file,
    has_backblaze_storage,
)
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.auto_fix_engine import AutoFixEngine
from backend.fix_progress_tracker import (
    create_progress_tracker,
    get_progress_tracker,
)
from backend.utils.wcag_mapping import annotate_wcag_mappings

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


MAX_GROUP_NAME_LENGTH = 255


class GroupPayload(BaseModel):
    name: str
    description: Optional[str] = ""


# CORS / environment config
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://document-a11y-accelerator.vercel.app")
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")
DB_SCHEMA = os.getenv("DB_SCHEMA", "public")

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


UPLOAD_FOLDER_PATH = _init_storage_dir(os.getenv("UPLOAD_FOLDER"), "uploads")
FIXED_FOLDER_PATH = _init_storage_dir(os.getenv("FIXED_FOLDER"), "fixed")
TEMP_UPLOAD_DIR_PATH = _init_storage_dir(os.getenv("TEMP_UPLOAD_DIR"), "tmp")
GENERATED_PDFS_BASE = _init_storage_dir(os.getenv("GENERATED_PDFS_FOLDER"), "generated")

UPLOAD_FOLDER = str(UPLOAD_FOLDER_PATH)
FIXED_FOLDER = str(FIXED_FOLDER_PATH)
TEMP_UPLOAD_DIR = str(TEMP_UPLOAD_DIR_PATH)
GENERATED_PDFS_FOLDER = str(GENERATED_PDFS_BASE)

# PDF generator instance - keep original pattern
pdf_generator = PDFGenerator()
generator_dir = getattr(pdf_generator, "output_dir", None)
if generator_dir:
    try:
        Path(generator_dir).mkdir(parents=True, exist_ok=True)
        GENERATED_PDFS_FOLDER = generator_dir
    except Exception:
        logger.warning(
            "[Backend] Could not use PDF generator output dir %s, defaulting to %s",
            generator_dir,
            GENERATED_PDFS_FOLDER,
        )

# Version pattern used in your original code
VERSION_FILENAME_PATTERN = re.compile(r"_v(\d+)\.pdf$", re.IGNORECASE)

# thread lock for psycopg2 usage (synchronous)
db_lock = threading.Lock()
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


def _mount_static_if_available(prefix: str, directory: str, name: str):
    path = Path(directory)
    try:
        if path.exists():
            app.mount(prefix, StaticFiles(directory=directory), name=name)
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


# serve uploaded files (development/test only; remote storage is canonical)
_mount_static_if_available("/uploads", UPLOAD_FOLDER, "uploads")
_mount_static_if_available("/fixed", FIXED_FOLDER, "fixed")
_mount_static_if_available("/generated_pdfs", GENERATED_PDFS_FOLDER, "generated_pdfs")


# ----------------------
# DB helpers (preserve original function names and behavior)
# ----------------------
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
            total_issues = sum(
                len(v) if isinstance(v, list) else 0 for v in results.values()
            )
            summary = {
                "totalIssues": total_issues,
                "highSeverity": 0,
                "complianceScore": max(0, 100 - total_issues * 2),
            }

    if isinstance(summary, dict) and verapdf_status:
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))
        summary.setdefault("pdfaCompliance", verapdf_status.get("pdfaCompliance"))
        combined_score = _combine_compliance_scores(
            summary.get("wcagCompliance"),
            summary.get("pdfuaCompliance"),
            summary.get("pdfaCompliance"),
        )
        if combined_score is not None:
            summary["complianceScore"] = combined_score

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
        "groupId": scan_row.get("group_id") or scan_row.get("groupId"),
        "summary": summary or {},
        "results": results,
        "verapdfStatus": verapdf_status,
        "issues": {
            "total": scan_row.get("total_issues"),
            "fixed": scan_row.get("issues_fixed"),
            "remaining": scan_row.get("issues_remaining"),
        },
        "latestFix": latest_fix,
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


# helper to save scan metadata (preserve naming)
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
                json.dumps(fixes_applied),
                json.dumps(fix_suggestions or []),
                json.dumps(issues_before),
                json.dumps(issues_after),
                total_issues_before,
                total_issues_after,
                high_severity_before,
                high_severity_after,
                compliance_before,
                compliance_after,
                success_count,
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


# ----------------------
# Small helpers copied & preserved from your original file
# ----------------------
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
        entries.append(
            {
                "version": version_number,
                "absolute_path": str(path.resolve()),
                "relative_path": str(path.relative_to(base_dir)),
                "filename": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    # sort by version asc
    entries.sort(key=lambda e: e["version"])
    return entries


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
        result = upload_file_with_fallback(str(local_path), local_path.name, folder=folder)
        remote_path = result.get("url")
        if remote_path:
            return remote_path
        return result.get("path")
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
        "pdfaCompliance": base_status.get("pdfaCompliance"),
        "complianceScore": _combine_compliance_scores(
            base_status.get("wcagCompliance"),
            base_status.get("pdfuaCompliance"),
            base_status.get("pdfaCompliance"),
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

    return {
        "results": scan_results,
        "summary": summary if isinstance(summary, dict) else {},
        "verapdfStatus": verapdf_status,
        "fixes": fix_suggestions,
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
    upload_dir = _uploads_root()
    candidates: List[Path] = [
        upload_dir / f"{scan_id}.pdf",
        upload_dir / scan_id,
    ]
    remote_references: List[str] = []

    if scan_record:
        filename = scan_record.get("filename")
        if filename:
            candidates.append(upload_dir / filename)

        stored_path = scan_record.get("path") or scan_record.get("file_path")
        if not stored_path:
            parsed_results = _parse_scan_results_json(
                scan_record.get("scan_results")
            )
            if isinstance(parsed_results, dict):
                stored_path = (
                    parsed_results.get("filePath")
                    or parsed_results.get("file_path")
                )
        if stored_path:
            stored_str = str(stored_path)
            if stored_str.lower().startswith(("http://", "https://")):
                remote_references.append(stored_str)
            else:
                path_obj = Path(stored_str)
                candidates.append(path_obj)
                # If the stored path does not currently exist locally, treat it as remote key
                if not path_obj.exists():
                    remote_references.append(stored_str)

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

    relative_path = dest_path.relative_to(_fixed_root())
    return {
        "version": next_version,
        "filename": dest_path.name,
        "absolute_path": str(dest_path),
        "relative_path": str(relative_path),
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
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
            }
        match = next((entry for entry in version_entries if entry.get("version") == version), None)
        if match:
            return {
                "version": match.get("version"),
                "filename": match.get("filename"),
                "absolute_path": match.get("absolute_path"),
                "relative_path": match.get("relative_path"),
            }

    fixed_dir = _fixed_root()
    for ext in ("", ".pdf"):
        candidate = fixed_dir / f"{scan_id}{ext}"
        if candidate.exists():
            relative = candidate.relative_to(fixed_dir)
            return {
                "version": 1,
                "filename": candidate.name,
                "absolute_path": str(candidate),
                "relative_path": str(relative),
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
        path = entry.get("absolute_path")
        if not path:
            continue
        try:
            os.remove(path)
            removed_files.append(entry.get("filename", os.path.basename(path)))
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("[Backend] Failed to remove fixed version %s", path)

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

        if tracker:
            tracker.complete_all()

        scan_results_payload = result.get("scanResults") or {
            "results": result.get("results"),
            "summary": result.get("summary"),
            "verapdfStatus": result.get("verapdfStatus"),
            "fixes": result.get("fixesApplied", []),
        }
        summary = scan_results_payload.get("summary") or result.get("summary") or {}
        remaining_issues = summary.get("totalIssues", 0) or 0
        total_issues_before = scan_row.get("total_issues") or remaining_issues
        issues_fixed = max(total_issues_before - remaining_issues, 0)
        status = "fixed" if remaining_issues == 0 else "processed"

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

        fixes_applied = result.get("fixesApplied", [])
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
                fix_metadata={"automated": True},
                batch_id=scan_row.get("batch_id"),
                group_id=scan_row.get("group_id"),
                total_issues_before=total_issues_before,
                total_issues_after=remaining_issues,
                high_severity_before=initial_summary.get("highSeverity"),
                high_severity_after=summary.get("highSeverity"),
                success_count=result.get("successCount"),
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
            "successCount": result.get("successCount", len(fixes_applied)),
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
    wcag_issues = len(results.get("wcagIssues", []))
    pdfua_issues = len(results.get("pdfuaIssues", []))
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


# ----------------------
# Routes — keep original function names, adapted for FastAPI
# ----------------------


@app.post("/api/upload")
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
):
    """
    Upload endpoint (synchronous):
    - Saves uploaded file to a temporary location
    - Uses upload_file_with_fallback() for multi-tier storage
    - Cleans up temporary file
    """
    temp_path = None
    try:
        # Save temp file safely
        with tempfile.NamedTemporaryFile(
            delete=False, dir="/tmp", suffix=f"_{file.filename}"
        ) as tmp:
            temp_path = tmp.name
            tmp.write(file.file.read())

        file_size = os.path.getsize(temp_path)
        logger.info(f"[API] Received upload: {file.filename} ({file_size} bytes)")

        # Upload with fallback
        result = upload_file_with_fallback(temp_path, file.filename, folder="uploads")
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

        # When a group is provided, create a placeholder scan entry so dashboards
        # can track the upload even before analysis runs.
        if group_id and NEON_DATABASE_URL:
            logger.info("[API] saving scan metadata for %s", file.filename)

            placeholder = build_placeholder_scan_payload(file.filename)
            if storage_reference:
                placeholder = dict(placeholder)
                placeholder["filePath"] = storage_reference
            scan_id = f"scan_{uuid.uuid4().hex}"
            try:
                saved_id = save_scan_to_db(
                    scan_id,
                    file.filename,
                    placeholder,
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
                    }
                )
                response_payload["result"].update(
                    {
                        "scanId": saved_id,
                        "groupId": group_id,
                        "status": "uploaded",
                        "filePath": storage_reference,
                    }
                )
                try:
                    update_group_file_count(group_id)
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
        # Always clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"[API] Temporary file removed: {temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"[API] Cleanup failed for {temp_path}: {cleanup_error}")


@app.get("/api/scans")
async def get_scans():
    try:
        rows = execute_query(
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
        ) or []

        scans: List[Dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row)
            raw_payload = (
                row_dict.get("scan_results") or row_dict.get("results") or {}
            )
            parsed_payload = _parse_scan_results_json(raw_payload)
            summary = parsed_payload.get("summary", {}) or {}
            results = parsed_payload.get("results", parsed_payload) or {}

            scan_identifier = row_dict.get("id")

            scans.append(
                {
                    "id": scan_identifier,
                    "scanId": scan_identifier,
                    "filename": row_dict.get("filename"),
                    "groupId": row_dict.get("group_id"),
                    "batchId": row_dict.get("batch_id"),
                    "status": row_dict.get("status", "unprocessed"),
                    "uploadDate": row_dict.get("upload_date")
                    or row_dict.get("created_at"),
                    "filePath": row_dict.get("file_path"),
                    "summary": summary,
                    "results": results if isinstance(results, dict) else {},
                    "verapdfStatus": parsed_payload.get("verapdfStatus"),
                    "totalIssues": summary.get(
                        "totalIssues", row_dict.get("total_issues", 0)
                    ),
                    "issuesFixed": row_dict.get("issues_fixed")
                    or summary.get("issuesFixed", 0),
                    "issuesRemaining": row_dict.get("issues_remaining")
                    or summary.get("issuesRemaining", summary.get("remainingIssues", 0)),
                    "complianceScore": summary.get("complianceScore"),
                }
            )

        return SafeJSONResponse({"scans": scans})
    except Exception as e:
        logger.exception("doca11y-backend:get_scans DB error")
        return JSONResponse({"scans": [], "error": str(e)}, status_code=500)


@app.get("/api/groups")
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


@app.get("/api/groups/{group_id}/details")
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
            SELECT scan_results, status
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
        fixed_count = 0
        severity_totals = {"high": 0, "medium": 0, "low": 0}
        category_totals: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}

        for scan in scans:
            scan_results = _parse_scan_results_json(scan.get("scan_results"))
            summary = scan_results.get("summary", {})
            results = scan_results.get("results", {})

            total_issues += summary.get("totalIssues", 0)
            total_compliance += summary.get("complianceScore", 0)

            status_key = (scan.get("status") or "unknown").lower()
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            if isinstance(results, dict):
                for category, issues in results.items():
                    if not isinstance(issues, list):
                        continue
                    category_totals[category] = category_totals.get(category, 0) + len(
                        issues
                    )
                    for issue in issues:
                        if not isinstance(issue, dict):
                            continue
                        severity = (issue.get("severity") or "").lower()
                        if severity in severity_totals:
                            severity_totals[severity] += 1

            if status_key == "fixed":
                fixed_count += 1
                issues_fixed += summary.get("totalIssues", 0)

        avg_compliance = (
            round(total_compliance / total_files, 2) if total_files > 0 else 0
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
            "status_counts": status_counts,
        }

        return SafeJSONResponse(response)
    except Exception:
        logger.exception("doca11y-backend:get_group_details DB error")
        return JSONResponse({"error": "Failed to fetch group details"}, status_code=500)


@app.get("/api/groups/{group_id}/files")
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
            files.append(
                {
                    "id": row_dict["id"],
                    "filename": row_dict["filename"],
                    "status": row_dict.get("status", "unprocessed"),
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


@app.get("/api/groups/{group_id}")
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


# @app.get("/api/scans")
# def get_scans():
#     scans = execute_query(
#         """
#         SELECT id, filename, upload_date, status
#         FROM scans
#         ORDER BY upload_date DESC NULLS LAST, created_at DESC
#         """,
#         fetch=True,
#     )
#     return SafeJSONResponse({"scans": scans or []})


@app.post("/api/groups")
async def create_group(payload: GroupPayload):
    """Create a new group"""
    name = payload.name.strip()
    description = (payload.description or "").strip()

    if not name:
        return JSONResponse({"error": "Group name is required"}, status_code=400)

    if len(name) > MAX_GROUP_NAME_LENGTH:
        return JSONResponse(
            {"error": "Group name must be less than 255 characters"}, status_code=400
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


@app.put("/api/groups/{group_id}")
async def update_group(group_id: str, payload: GroupPayload):
    """Update group details"""
    name = payload.name.strip()
    description = (payload.description or "").strip()

    if not name:
        return JSONResponse({"error": "Group name is required"}, status_code=400)

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


@app.delete("/api/groups/{group_id}")
async def delete_group(group_id: str):
    """Delete a group (scans will have group_id set to NULL)"""
    try:
        rows = execute_query(
            "SELECT id FROM groups WHERE id = %s", (group_id,), fetch=True
        )
        if not rows:
            return JSONResponse({"error": "Group not found"}, status_code=404)

        execute_query("DELETE FROM groups WHERE id = %s", (group_id,), fetch=False)
        logger.info("[Backend] ✓ Deleted group: %s", group_id)
        return SafeJSONResponse(
            {"success": True, "message": "Group deleted successfully"}
        )
    except Exception as e:
        logger.exception("doca11y-backend:delete_group error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/health")
async def health():
    return {"status": "ok", "uploads": UPLOAD_FOLDER, "fixed": FIXED_FOLDER}


@app.get("/api/download-generated/{filename}")
async def download_generated_pdf(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = os.path.join(GENERATED_PDFS_FOLDER, safe_name)
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
    accessibility_options = (
        payload.get("accessibilityOptions")
        if isinstance(payload.get("accessibilityOptions"), dict)
        else None
    )

    try:
        accessible_fn = getattr(pdf_generator, "create_accessible_pdf", None)
        inaccessible_fn = getattr(pdf_generator, "create_inaccessible_pdf", None)
        if pdf_type == "accessible":
            if not callable(accessible_fn):
                raise AttributeError("Accessible PDF generator unavailable")
            output_path = await asyncio.to_thread(
                accessible_fn,
                company_name,
                services,
            )
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


# === PDF Scan ===
# Preserve function name: scan_pdf
@app.post("/api/scan")
async def scan_pdf(
    request: Request,
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
):
    # validate file presence and extension (same checks as original)
    if not file or not file.filename:
        return JSONResponse({"error": "No file provided"}, status_code=400)
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files supported"}, status_code=400)
    if not group_id:
        return JSONResponse({"error": "Group ID is required"}, status_code=400)

    # create unique scan id and save file
    scan_uid = f"scan_{uuid.uuid4().hex}"
    upload_dir = _temp_storage_root()
    file_path = upload_dir / f"{scan_uid}.pdf"

    # Save file using non-blocking thread
    try:
        await asyncio.to_thread(file.file.seek, 0)
        await asyncio.to_thread(_write_uploadfile_to_disk, file, str(file_path))
    except Exception:
        # fallback: manual streaming
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

    # Save to DB preserving original function name and logic
    try:
        total_issues = formatted_results.get("summary", {}).get("totalIssues", 0)
        saved_id = save_scan_to_db(
            scan_uid,
            file.filename,
            formatted_results,
            group_id=group_id,
            file_path=storage_reference,
            total_issues=total_issues,
            issues_remaining=total_issues,
            issues_fixed=0,
        )
        logger.info(
            f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues in group {group_id}"
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
        # still return results but note DB failure
        saved_id = scan_uid

    return JSONResponse(
        {
            "scanId": saved_id,
            "filename": file.filename,
            "groupId": group_id,
            "summary": formatted_results["summary"],
            "results": scan_results,
            "fixes": fix_suggestions,
            "timestamp": datetime.now().isoformat(),
            "verapdfStatus": verapdf_status,
        }
    )


@app.post("/api/scan-batch")
async def scan_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    group_id: Optional[str] = Form(None),
    batch_name: Optional[str] = Form(None),
    scan_mode: Optional[str] = Form(None),
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

        batch_id = f"batch_{uuid.uuid4().hex}"
        batch_title = batch_name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        scan_now = should_scan_now(scan_mode, request)
        batch_status = "processing" if scan_now else "uploaded"

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
                await asyncio.to_thread(_write_uploadfile_to_disk, upload, str(file_path))
            except Exception as write_err:
                logger.exception(
                    "[Backend] Failed to save %s for batch %s", upload.filename, batch_id
                )
                errors.append(f"{upload.filename}: {write_err}")
                scan_results_response.append(
                    {
                        "scanId": scan_id,
                        "filename": upload.filename,
                        "batchId": batch_id,
                        "groupId": group_id,
                        "status": "error",
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
                        status="completed",
                        total_issues=total_issues_file,
                        issues_fixed=0,
                        issues_remaining=remaining_issues,
                        file_path=storage_reference,
                    )
                    successful_scans += 1
                    total_batch_issues += total_issues_file
                    status_value = "completed"
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
                    status_value = "uploaded"

                processed_files += 1
                scan_results_response.append(
                    {
                        "scanId": saved_id,
                        "id": saved_id,
                        "filename": upload.filename,
                        "batchId": batch_id,
                        "groupId": group_id,
                        "status": status_value,
                        "summary": record_payload.get("summary", {}),
                        "results": record_payload.get("results", {}),
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
                        "status": "error",
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


@app.post("/api/scan/{scan_id}/start")
async def start_deferred_scan(scan_id: str):
    """
    Trigger analysis for a scan that was previously uploaded in deferred mode.
    """
    if not NEON_DATABASE_URL:
        return JSONResponse({"error": "Database not configured"}, status_code=500)

    scan_record = _fetch_scan_record(scan_id)
    if not scan_record:
        return JSONResponse({"error": "Scan not found"}, status_code=404)

    file_path = _resolve_scan_file_path(scan_id, scan_record)
    if not file_path or not file_path.exists():
        return JSONResponse(
            {"error": "Original file not found for scanning"}, status_code=404
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
                "unprocessed",
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
            "status": "unprocessed",
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.post("/api/scan/{scan_id}/prune-fixed")
async def prune_fixed_files(scan_id: str, request: Request):
    """Delete older fixed PDF versions for a scan, keeping the latest by default."""
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


@app.delete("/api/scan/{scan_id}")
async def delete_scan(scan_id: str):
    """Delete an individual scan and its associated files."""
    logger.info("[Backend] Deleting scan %s", scan_id)
    try:
        scan_record = _fetch_scan_record(scan_id)
        if not scan_record:
            return JSONResponse({"error": "Scan not found"}, status_code=404)

        resolved_id = scan_record.get("id") or scan_id
        group_id = scan_record.get("group_id")
        original_filename = scan_record.get("filename")

        uploads_dir = _uploads_root()
        fixed_dir = _fixed_root()
        deleted_files = 0

        def _delete_path(path: Path) -> bool:
            try:
                if path.exists():
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    return True
            except Exception:
                logger.exception("[Backend] Failed to delete %s", path)
            return False

        candidate_names = {scan_id, resolved_id}
        if original_filename:
            candidate_names.add(original_filename)

        for folder in (uploads_dir, fixed_dir):
            for name in candidate_names:
                if not name:
                    continue
                candidate = folder / name
                if _delete_path(candidate):
                    deleted_files += 1
                if not name.lower().endswith(".pdf"):
                    pdf_candidate = folder / f"{name}.pdf"
                    if _delete_path(pdf_candidate):
                        deleted_files += 1

        # Remove versioned history directory
        version_dirs = {fixed_dir / str(resolved_id), fixed_dir / str(scan_id)}
        for version_dir in version_dirs:
            if version_dir.exists() and version_dir.is_dir():
                removed_count = sum(
                    1 for child in version_dir.glob("**/*") if child.is_file()
                )
                if _delete_path(version_dir):
                    deleted_files += removed_count

        # Delete related DB records
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

        if group_id:
            update_group_file_count(group_id)

        logger.info(
            "[Backend] ✓ Deleted scan %s (removed %d files)", scan_id, deleted_files
        )
        return JSONResponse(
            {
                "success": True,
                "message": f"Deleted scan and {deleted_files} file(s)",
                "deletedFiles": deleted_files,
                "groupId": group_id,
            }
        )
    except Exception as exc:
        logger.exception("[Backend] Error deleting scan %s", scan_id)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/scan/{scan_id}")
async def get_scan(scan_id: str):
    """Fetch individual scan details by id or filename."""
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
            summary.setdefault("pdfaCompliance", verapdf_status.get("pdfaCompliance"))
            combined_score = _combine_compliance_scores(
                summary.get("wcagCompliance"),
                summary.get("pdfuaCompliance"),
                summary.get("pdfaCompliance"),
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
        response_verapdf = verapdf_status or {
            "isActive": False,
            "wcagCompliance": None,
            "pdfuaCompliance": None,
            "pdfaCompliance": None,
            "totalVeraPDFIssues": len(results_dict.get("wcagIssues", []))
            + len(results_dict.get("pdfaIssues", []))
            + len(results_dict.get("pdfuaIssues", [])),
        }

        response_data = {
            "scanId": scan.get("id"),
            "filename": scan.get("filename"),
            "status": scan.get("status", "completed"),
            "groupId": scan.get("group_id"),
            "uploadDate": scan.get("upload_date") or scan.get("created_at"),
            "summary": summary,
            "results": results_dict,
            "fixes": scan_results.get("fixes", []),
            "verapdfStatus": response_verapdf,
        }

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


@app.get("/api/scan/{scan_id}/current-state")
async def get_scan_current_state(scan_id: str):
    """
    Return combined scan + latest fix data to reflect the current remediation state.
    """
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

            response["currentState"] = {
                "status": "fixed",
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
            response["currentState"] = {
                "status": scan.get("status", "scanned"),
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


# Helper to write UploadFile to disk using file.stream (preserve streaming behavior)
def _write_uploadfile_to_disk(upload_file: UploadFile, dest_path: str):
    # upload_file.file is a SpooledTemporaryFile or similar; rewind and copy.
    upload_file.file.seek(0)
    with open(dest_path, "wb") as out_f:
        shutil.copyfileobj(upload_file.file, out_f)


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


@app.delete("/api/batch/{batch_id}")
async def delete_batch(batch_id: str):
    try:
        logger.info("[Backend] Deleting batch: %s", batch_id)
        scans_query = "SELECT id, group_id FROM scans WHERE batch_id = %s"
        scans = execute_query(scans_query, (batch_id,), fetch=True) or []
        if not scans:
            return JSONResponse(
                {"success": False, "error": f"Batch {batch_id} not found"},
                status_code=404,
            )

        affected_groups = {scan["group_id"] for scan in scans if scan.get("group_id")}

        uploads_dir = _uploads_root()
        fixed_dir = _fixed_root()
        deleted_files = 0

        for scan in scans:
            scan_id = scan["id"]
            for folder in [uploads_dir, fixed_dir]:
                for ext in ("", ".pdf"):
                    file_path = folder / f"{scan_id}{ext}"
                    if file_path.exists():
                        file_path.unlink()
                        deleted_files += 1

        execute_query(
            "DELETE FROM fix_history WHERE scan_id IN (SELECT id FROM scans WHERE batch_id = %s)",
            (batch_id,),
            fetch=False,
        )
        execute_query("DELETE FROM scans WHERE batch_id = %s", (batch_id,), fetch=False)
        execute_query("DELETE FROM batches WHERE id = %s", (batch_id,), fetch=False)

        for group_id in affected_groups:
            update_group_file_count(group_id)
            logger.info("[Backend] Updated file count for group: %s", group_id)

        logger.info(
            "[Backend] ✓ Deleted batch %s with %d scans and %d files",
            batch_id,
            len(scans),
            deleted_files,
        )

        return SafeJSONResponse(
            {
                "success": True,
                "message": f"Deleted batch with {len(scans)} scans",
                "deletedFiles": deleted_files,
                "affectedGroups": list(affected_groups),
            }
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
            result = await apply_fn(scan_id, scan_data, tracker, resolved_path=resolved_pdf_path)
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
                    "description": fix.get(
                        "description", "Semi-automated fix applied"
                    ),
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
            archive_info = archive_fixed_pdf_version(
                scan_id=scan_id,
                original_filename=original_filename,
                source_path=source_path,
            )
            if archive_info:
                fixed_filename = archive_info.get("relative_path")

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

        update_scan_status(
            scan_id, "fixed" if total_issues_after == 0 else "processed"
        )

        response_payload: Dict[str, Any] = {
            "status": "success",
            "fixedFile": fixed_filename,
            "fixedFilePath": fixed_filename,
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
                }
            )

        return SafeJSONResponse(response_payload)
    except Exception as exc:
        logger.exception("[Backend] ERROR in apply_semi_automated_fixes for %s", scan_id)
        if tracker:
            tracker.fail_all(str(exc))
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
        selected_version: Optional[Dict[str, Any]] = None
        scan_id_for_version = scan_id_param

        requested_path: Optional[Path]
        try:
            requested_path = (fixed_dir / filename).resolve()
        except Exception:
            requested_path = None

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
            target_scan_id = scan_id_param or filename
            versions = get_versioned_files(target_scan_id)
            if versions:
                latest = versions[-1]
                selected_version = latest
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
                    if (
                        match.get("version") != latest.get("version")
                        and not allow_old
                    ):
                        return JSONResponse(
                            {
                                "error": "Only the latest version is downloadable by default",
                                "latestVersion": latest.get("version"),
                                "requestedVersion": match.get("version"),
                            },
                            status_code=403,
                        )
                    selected_version = match

                file_path = Path(selected_version["absolute_path"])
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

        if not file_path:
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
            download_name = selected_version.get("filename") or file_path.name
        else:
            download_name = file_path.name
        if not download_name.lower().endswith(".pdf"):
            download_name = f"{Path(download_name).stem}.pdf"

        return FileResponse(file_path, media_type="application/pdf", filename=download_name)
    except Exception as exc:
        logger.exception("[Backend] Error downloading fixed file %s", filename)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/pdf-file/{scan_id}")
async def serve_pdf_file(scan_id: str, request: Request):
    """Serve PDF file for preview in PDF Editor."""
    try:
        uploads_dir = _uploads_root()
        fixed_dir = _fixed_root()

        version_param = request.query_params.get("version")
        file_path: Optional[Path] = None

        if version_param:
            try:
                requested_version = int(version_param)
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "Invalid version parameter"}, status_code=400
                )
            version_info = get_fixed_version(scan_id, requested_version)
            if version_info:
                file_path = Path(version_info["absolute_path"])
        else:
            latest_version = get_fixed_version(scan_id)
            if latest_version:
                file_path = Path(latest_version["absolute_path"])

        if not file_path:
            for folder in (fixed_dir, uploads_dir):
                for ext in ("", ".pdf"):
                    candidate = folder / f"{scan_id}{ext}"
                    if candidate.exists():
                        file_path = candidate
                        break
                if file_path:
                    break

        if not file_path:
            return JSONResponse({"error": "PDF file not found"}, status_code=404)

        return FileResponse(file_path, media_type="application/pdf")
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

        pdf_path = _resolve_scan_file_path(scan_id, scan_data if isinstance(scan_data, dict) else None)
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
                logger.exception(
                    "[Storage] Remote download failed for %s", remote_key
                )
                continue

            headers = {
                "Content-Disposition": f'attachment; filename="{safe_name}"'
            }
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
        background_tasks.add_task(asyncio.to_thread, _perform_automated_fix, scan_id, {}, None)

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
        return SafeJSONResponse({"history": rows})
    except Exception:
        logger.exception("fix_history DB error")
        return JSONResponse({"history": []})


# === Export endpoint ===
@app.get("/api/export/{scan_id}")
async def export_scan(scan_id: str):
    conn = None
    cur = None
    try:
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
    logger.exception("doca11y-backend:" + str(exc))
    return JSONResponse(
        status_code=404, content={"error": "Route not found:" + str(exc)}
    )


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
