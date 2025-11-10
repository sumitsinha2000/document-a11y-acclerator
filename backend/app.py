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
from backend.multi_tier_storage import upload_file_with_fallback
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.auto_fix_engine import AutoFixEngine
from backend.fix_progress_tracker import (
    create_progress_tracker,
    get_progress_tracker,
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
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
FIXED_FOLDER = os.getenv("FIXED_FOLDER", "fixed")
GENERATED_PDFS_FOLDER = None

# create folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FIXED_FOLDER, exist_ok=True)

# PDF generator instance - keep original pattern
pdf_generator = PDFGenerator()
GENERATED_PDFS_FOLDER = getattr(pdf_generator, "output_dir", "generated_pdfs")
os.makedirs(GENERATED_PDFS_FOLDER, exist_ok=True)

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

# serve uploaded files (development/test)
app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
app.mount("/fixed", StaticFiles(directory=FIXED_FOLDER), name="fixed")
app.mount(
    "/generated_pdfs",
    StaticFiles(directory=GENERATED_PDFS_FOLDER),
    name="generated_pdfs",
)


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
        logger.exception("Database connection failed")
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
            logger.exception("Query execution failed")
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
        logger.exception("[Backend] ⚠ Failed to update batch statistics for %s", batch_id)
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
):
    """
    Insert or update a scan record into scans table. Preserves your original DB logic style.
    Returns saved scan_id or raises on error.
    """
    # Convert results to JSON
    results_json = json.dumps(scan_results)
    now = datetime.utcnow()
    try:
        if not is_update:
            # Insert new
            execute_query(
                """
                INSERT INTO scans (scan_id, filename, results, batch_id, group_id, status, upload_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scan_id,
                    original_filename,
                    results_json,
                    batch_id,
                    group_id,
                    "completed",
                    now,
                ),
            )
        else:
            # Update existing
            execute_query(
                """
                UPDATE scans SET filename=%s, results=%s, batch_id=%s, group_id=%s, status=%s, upload_date=%s
                WHERE scan_id=%s
                """,
                (
                    original_filename,
                    results_json,
                    batch_id,
                    group_id,
                    "completed",
                    now,
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
            "UPDATE scans SET status=%s WHERE scan_id=%s",
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
    return Path(UPLOAD_FOLDER).resolve()


def _fixed_root() -> Path:
    return Path(FIXED_FOLDER).resolve()


def _ensure_local_storage(context: str = ""):
    """Ensure uploads/fixed directories exist."""
    try:
        _uploads_root().mkdir(parents=True, exist_ok=True)
        _fixed_root().mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("[Backend] Failed to ensure local storage for %s", context)


def build_placeholder_scan_payload(filename: Optional[str] = None) -> Dict[str, Any]:
    summary = {
        "totalIssues": 0,
        "highSeverity": 0,
        "complianceScore": 0,
        "status": "queued",
    }
    if filename:
        summary["filename"] = filename
    return {
        "results": {},
        "summary": summary,
        "verapdfStatus": None,
        "fixes": [],
    }


def should_scan_now(scan_mode: Optional[str] = None, request: Optional[Request] = None) -> bool:
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


def get_fixed_version(scan_id: str) -> Optional[Dict[str, Any]]:
    """Return the latest fixed file entry for a scan if present."""
    version_entries = get_versioned_files(scan_id)
    if version_entries:
        latest = version_entries[-1]
        return {
            "version": latest.get("version"),
            "filename": latest.get("filename"),
            "absolute_path": latest.get("absolute_path"),
            "relative_path": latest.get("relative_path"),
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
async def upload_file(file: UploadFile = File(...)):
    try:
        # Save temp file locally
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())

        # Upload with fallback logic
        result = upload_file_with_fallback(temp_path, file.filename)
        return {"message": "File uploaded successfully", "result": result}

    except Exception as e:
        return {"error": str(e)}


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

        scans = execute_query(
            """
            SELECT scan_results, status
            FROM scans
            WHERE group_id = %s
            """,
            (group_id,),
            fetch=True,
        ) or []

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
                    category_totals[category] = (
                        category_totals.get(category, 0) + len(issues)
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
        return JSONResponse(
            {"error": "Failed to fetch group details"}, status_code=500
        )


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
            scan_results = _parse_scan_results_json(
                row_dict.get("scan_results") or {}
            )
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


# === PDF Scan ===
# Preserve function name: scan_pdf
@app.post("/api/scan")
async def scan_pdf(file: UploadFile = File(...), group_id: Optional[str] = Form(None)):
    # validate file presence and extension (same checks as original)
    if not file or not file.filename:
        return JSONResponse({"error": "No file provided"}, status_code=400)
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files supported"}, status_code=400)
    if not group_id:
        return JSONResponse({"error": "Group ID is required"}, status_code=400)

    # create unique scan id and save file
    scan_uid = f"scan_{uuid.uuid4().hex}"
    upload_dir = Path(UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)
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

    # Run analyzer (prefer async if available, else to_thread)
    analyzer = PDFAccessibilityAnalyzer()
    analyze_fn = getattr(analyzer, "analyze", None)
    if analyze_fn:
        if asyncio.iscoroutinefunction(analyze_fn):
            scan_results = await analyze_fn(str(file_path))
        else:
            scan_results = await asyncio.to_thread(analyze_fn, str(file_path))
    else:
        logger.warning(
            "PDFAccessibilityAnalyzer.analyze not found; returning empty results"
        )
        scan_results = {}

    verapdf_status = build_verapdf_status(scan_results, analyzer)
    # some analyzers define calculate_summary
    summary = {}
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

    # Save to DB preserving original function name and logic
    try:
        saved_id = save_scan_to_db(
            scan_uid, file.filename, formatted_results, group_id=group_id
        )
        total_issues = formatted_results.get("summary", {}).get("totalIssues", 0)
        logger.info(
            f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues in group {group_id}"
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


# Helper to write UploadFile to disk using file.stream (preserve streaming behavior)
def _write_uploadfile_to_disk(upload_file: UploadFile, dest_path: str):
    # upload_file.file is a SpooledTemporaryFile or similar; rewind and copy.
    upload_file.file.seek(0)
    with open(dest_path, "wb") as out_f:
        shutil.copyfileobj(upload_file.file, out_f)


# === Scan History / List ===
@app.get("/api/scans")
async def get_scans():
    try:
        rows = execute_query(
            "SELECT id, filename, upload_date, status FROM scans ORDER BY upload_date DESC",
            fetch=True,
        )
        return SafeJSONResponse({"scans": rows})
    except Exception as e:
        logger.exception("doca11y-backend:get_scans DB error")
        return JSONResponse({"scans": [], "error": str(e)}, status_code=500)


# === Batch Upload ===
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
            return JSONResponse({"error": "No PDF files provided"}, status_code=400)

        batch_id = f"batch_{uuid.uuid4().hex}"
        batch_title = batch_name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        scan_now = should_scan_now(scan_mode, request)
        batch_status = "processing" if scan_now else "uploaded"

        execute_query(
            """
            INSERT INTO batches (id, name, group_id, created_at, status, total_files, total_issues, remaining_issues, fixed_issues, unprocessed_files)
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

        logger.info(
            "[Backend] ✓ Created batch %s (%s) with %d files (scan_now=%s)",
            batch_id,
            batch_title,
            len(pdf_files),
            scan_now,
        )

        _ensure_local_storage("Batch uploads")
        upload_dir = _uploads_root()
        upload_dir.mkdir(parents=True, exist_ok=True)

        scan_results_response: List[Dict[str, Any]] = []
        total_batch_issues = 0
        processed_files = len(pdf_files)
        successful_scans = 0

        for file in pdf_files:
            scan_id = f"scan_{uuid.uuid4().hex}"
            file_path = upload_dir / f"{scan_id}.pdf"
            await asyncio.to_thread(_write_uploadfile_to_disk, file, str(file_path))

            if not scan_now:
                placeholder = build_placeholder_scan_payload(file.filename)
                execute_query(
                    """
                    INSERT INTO scans (
                        id, filename, scan_results, status, upload_date, created_at,
                        group_id, batch_id, total_issues, issues_remaining, issues_fixed
                    ) VALUES (
                        %s, %s, %s, %s, NOW(), NOW(),
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        scan_id,
                        file.filename,
                        _serialize_scan_results(placeholder),
                        "uploaded",
                        group_id,
                        batch_id,
                        0,
                        0,
                        0,
                    ),
                )
                scan_results_response.append(
                    {
                        "scanId": scan_id,
                        "filename": file.filename,
                        "totalIssues": 0,
                        "status": "uploaded",
                        "summary": placeholder.get("summary", {}),
                        "results": placeholder.get("results", {}),
                        "verapdfStatus": placeholder.get("verapdfStatus"),
                        "fixes": placeholder.get("fixes", []),
                        "groupId": group_id,
                        "batchId": batch_id,
                    }
                )
                continue

            analyzer = PDFAccessibilityAnalyzer()
            analyze_fn = getattr(analyzer, "analyze", None)
            if not analyze_fn:
                logger.warning("Analyzer missing analyze() method; skipping %s", file.filename)
                continue

            if asyncio.iscoroutinefunction(analyze_fn):
                scan_data = await analyze_fn(str(file_path))
            else:
                scan_data = await asyncio.to_thread(analyze_fn, str(file_path))

            verapdf_status = build_verapdf_status(scan_data, analyzer)
            summary = {}
            try:
                if hasattr(analyzer, "calculate_summary"):
                    calc = getattr(analyzer, "calculate_summary")
                    if asyncio.iscoroutinefunction(calc):
                        summary = await calc(scan_data, verapdf_status)
                    else:
                        summary = await asyncio.to_thread(calc, scan_data, verapdf_status)
            except Exception:
                logger.exception("calculate_summary failed for %s", file.filename)
                summary = {}

            if isinstance(summary, dict) and verapdf_status:
                summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
                summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

            fixes = (
                generate_fix_suggestions(scan_data)
                if callable(generate_fix_suggestions)
                else []
            )

            formatted_results = {
                "results": scan_data,
                "summary": summary,
                "verapdfStatus": verapdf_status,
                "fixes": fixes,
            }

            total_issues = summary.get("totalIssues", 0) if isinstance(summary, dict) else 0
            total_batch_issues += total_issues

            execute_query(
                """
                INSERT INTO scans (
                    id, filename, scan_results, status, upload_date, created_at,
                    group_id, batch_id, total_issues, issues_remaining, issues_fixed
                ) VALUES (
                    %s, %s, %s, %s, NOW(), NOW(),
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    scan_id,
                    file.filename,
                    _serialize_scan_results(formatted_results),
                    "unprocessed",
                    group_id,
                    batch_id,
                    total_issues,
                    total_issues,
                    0,
                ),
            )

            scan_results_response.append(
                {
                    "scanId": scan_id,
                    "filename": file.filename,
                    "totalIssues": total_issues,
                    "status": "unprocessed",
                    "summary": summary,
                    "results": scan_data,
                    "verapdfStatus": verapdf_status,
                    "fixes": fixes,
                    "groupId": group_id,
                    "batchId": batch_id,
                }
            )
            successful_scans += 1

        if not scan_now:
            unprocessed_files = len(pdf_files)
            batch_status = "uploaded"
            remaining_issues = 0
        else:
            unprocessed_files = max(len(pdf_files) - successful_scans, 0)
            remaining_issues = total_batch_issues
            if successful_scans == len(pdf_files):
                batch_status = "completed"
            elif successful_scans == 0:
                batch_status = "failed"
            else:
                batch_status = "partial"

        execute_query(
            """
            UPDATE batches
            SET total_issues = %s,
                remaining_issues = %s,
                unprocessed_files = %s,
                status = %s,
                total_files = %s
            WHERE id = %s
            """,
            (
                total_batch_issues,
                remaining_issues,
                unprocessed_files,
                batch_status,
                len(pdf_files),
                batch_id,
            ),
        )

        update_batch_statistics(batch_id)
        update_group_file_count(group_id)

        logger.info(
            "[Backend] ✓ Batch %s upload complete: %d scans, %d issues",
            batch_id,
            len(scan_results_response),
            total_batch_issues,
        )

        return SafeJSONResponse(
            {
                "batchId": batch_id,
                "groupId": group_id,
                "scans": scan_results_response,
                "totalIssues": total_batch_issues,
                "timestamp": datetime.now().isoformat(),
                "processedFiles": processed_files,
                "successfulScans": successful_scans,
                "skippedFiles": skipped_files,
                "scanDeferred": not scan_now,
                "batchStatus": batch_status,
            }
        )

    except Exception as e:
        logger.exception("scan_batch failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# === Batch fix/download/details endpoints ===
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
            return JSONResponse({"error": f"Batch {batch_id} not found"}, status_code=404)

        cursor.execute(
            """
            SELECT 
                s.id AS scan_id,
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

        version_entries = get_versioned_files(scan["scan_id"])
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
                "scanId": scan["scan_id"],
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
            return JSONResponse({"error": f"Batch {batch_id} not found"}, status_code=404)

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
            return JSONResponse({"error": "No scans found for this batch"}, status_code=404)

        def _sanitize(value: Optional[str], fallback: str) -> str:
            text = value or fallback
            return re.sub(r"[^A-Za-z0-9._-]", "_", text)

        def _deserialize_payload(value, fallback):
            if not value:
                return fallback
            if isinstance(value, (list, dict)):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return fallback
            return fallback

        def _to_export_payload(scan_row):
            scan_results = scan_row.get("scan_results", {})
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception:
                    scan_results = {}

            results = scan_results.get("results", scan_results) or {}
            summary = scan_results.get("summary", {}) or {}
            verapdf_status = scan_results.get("verapdfStatus")

            if verapdf_status is None:
                verapdf_status = build_verapdf_status(results)

            if not summary or "totalIssues" not in summary:
                try:
                    summary = PDFAccessibilityAnalyzer.calculate_summary(
                        results, verapdf_status
                    )
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
                fix_list = _deserialize_payload(scan_row.get("fixes_applied"), [])
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

            export_payload = {
                "scanId": scan_row.get("id"),
                "filename": scan_row.get("filename"),
                "status": scan_row.get("status"),
                "uploadDate": scan_row.get("upload_date").isoformat()
                if scan_row.get("upload_date")
                else None,
                "summary": summary,
                "results": results,
                "verapdfStatus": verapdf_status,
                "issues": {
                    "total": scan_row.get("total_issues"),
                    "fixed": scan_row.get("issues_fixed"),
                    "remaining": scan_row.get("issues_remaining"),
                },
                "latestFix": latest_fix,
            }
            return export_payload

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
                scan_export = _to_export_payload(scan_row)
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
                    "SELECT * FROM scans WHERE scan_id=%s", (scan_id,), fetch=True
                )
                if rows:
                    scan_data = rows[0]
        except Exception:
            logger.exception("DB lookup for scan data failed; proceeding")

        pdf_path = Path(UPLOAD_FOLDER) / f"{scan_id}.pdf"
        if not pdf_path.exists():
            possible_paths = [
                Path(UPLOAD_FOLDER) / scan_id,
                Path(UPLOAD_FOLDER) / f"{scan_id.replace('.pdf', '')}.pdf",
            ]
            if original_filename:
                possible_paths.append(Path(UPLOAD_FOLDER) / original_filename)
            if scan_data.get("path"):
                possible_paths.append(Path(scan_data["path"]))

            found = None
            for candidate in possible_paths:
                if candidate and candidate.exists():
                    found = candidate
                    break
            if found:
                pdf_path = found

        if not pdf_path.exists():
            return JSONResponse({"error": "PDF file not found"}, status_code=404)

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
                batch_id=scan_data.get("batch_id") if isinstance(scan_data, dict) else None,
                group_id=scan_data.get("group_id") if isinstance(scan_data, dict) else None,
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
    # call auto_fix_engine.apply_all or apply_fixes as in your original modules
    engine = AutoFixEngine()
    fn = (
        getattr(engine, "apply_fixes", None)
        or getattr(engine, "apply_all", None)
        or getattr(engine, "apply", None)
    )
    if not fn:
        return JSONResponse({"error": "Auto fix function not found"}, status_code=500)
    # schedule background job if sync
    if asyncio.iscoroutinefunction(fn):
        background_tasks.add_task(fn, scan_id)
    else:
        background_tasks.add_task(asyncio.to_thread, fn, scan_id)
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


# === Export endpoint stub ===
@app.get("/api/export/{scan_id}")
async def export_scan(scan_id: str):
    # Keep as simple stub; integrate your export logic as before
    return JSONResponse({"scan_id": scan_id, "export_url": f"/exports/{scan_id}.zip"})


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
    return JSONResponse(status_code=404, content={"error": "Route not found:" + str(exc)})


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
