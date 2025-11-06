# backend/app.py
import os
import json
import shutil
import threading
import time
import uuid
import logging
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# FastAPI imports
from fastapi import (
    FastAPI,
    Request,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
    HTTPException,
)
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# DB (psycopg2) - preserving your original DB usage (Neon)
import psycopg2
from psycopg2.extras import RealDictCursor

# Business logic modules (preserve exact imports and names)
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.auto_fix_engine import AutoFixEngine
from backend.fix_progress_tracker import create_progress_tracker, get_progress_tracker
# The original used PDFGenerator; keep it
try:
    from backend.pdf_generator import PDFGenerator
except Exception:
    # If pdf_generator missing, create a minimal stub to avoid import errors
    class PDFGenerator:
        def __init__(self):
            self.output_dir = "generated_pdfs"

        def generate(self, *args, **kwargs):
            return None

# werkzeug secure_filename used previously
from werkzeug.utils import secure_filename

# ----------------------
# Logging & Config
# ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doca11y-backend")
import json
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

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

# CORS / environment config
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://document-a11y-accelerator.vercel.app")
NEON_DATABASE_URL = os.getenv("DATABASE_URL")
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
    "https://document-a11y-accelerator.vercel.app",  # your Vercel frontend
    "https://document-a11y-accelerator.onrender.com",  # backend Render domain
    "http://localhost:3000",  # local dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,         # exact origins allowed
    allow_credentials=True,
    allow_methods=["*"],           # allow all HTTP verbs
    allow_headers=["*"],           # allow all headers
)

# serve uploaded files (development/test)
app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
app.mount("/fixed", StaticFiles(directory=FIXED_FOLDER), name="fixed")
app.mount("/generated_pdfs", StaticFiles(directory=GENERATED_PDFS_FOLDER), name="generated_pdfs")


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
                (scan_id, original_filename, results_json, batch_id, group_id, "completed", now),
            )
        else:
            # Update existing
            execute_query(
                """
                UPDATE scans SET filename=%s, results=%s, batch_id=%s, group_id=%s, status=%s, upload_date=%s
                WHERE scan_id=%s
                """,
                (original_filename, results_json, batch_id, group_id, "completed", now, scan_id),
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
):
    """
    Save fix history record - preserve original names.
    """
    try:
        execute_query(
            """
            INSERT INTO fixes (scan_id, original_filename, fixed_filename, fixes_applied, fix_type, issues_before, issues_after, compliance_before, compliance_after, suggestions, metadata, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (
                scan_id,
                original_filename,
                fixed_filename,
                json.dumps(fixes_applied),
                fix_type,
                json.dumps(issues_before),
                json.dumps(issues_after),
                compliance_before,
                compliance_after,
                json.dumps(fix_suggestions or []),
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
        logger.warning("PDFAccessibilityAnalyzer.analyze not found; returning empty results")
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

    fix_suggestions = generate_fix_suggestions(scan_results) if callable(generate_fix_suggestions) else []

    formatted_results = {
        "results": scan_results,
        "summary": summary,
        "verapdfStatus": verapdf_status,
        "fixes": fix_suggestions,
    }

    # Save to DB preserving original function name and logic
    try:
        saved_id = save_scan_to_db(scan_uid, file.filename, formatted_results, group_id=group_id)
        total_issues = formatted_results.get("summary", {}).get("totalIssues", 0)
        logger.info(f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues in group {group_id}")
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
            "SELECT id, filename, upload_date, status FROM scans ORDER BY upload_date DESC", fetch=True
        )
        return JSONResponse(to_json_safe({"scans": rows}))
    except Exception as e:
        logger.exception("doca11y-backend:get_scans DB error")
        return JSONResponse({"scans": [], "error": str(e)}, status_code=500)


# === Batch Upload ===
@app.post("/api/scan-batch")
async def scan_batch(files: List[UploadFile] = File(...), group_id: Optional[str] = Form(None)):
    try:
        if not files:
            return JSONResponse({"error": "No files provided"}, status_code=400)
        batch_id = f"batch_{uuid.uuid4().hex}"
        results = []
        for f in files:
            fname = f.filename
            scan_id = f"scan_{uuid.uuid4().hex}"
            upload_dir = Path(UPLOAD_FOLDER)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / f"{scan_id}.pdf"
            await asyncio.to_thread(_write_uploadfile_to_disk, f, str(file_path))
            # run analyzer in background thread
            analyzer = PDFAccessibilityAnalyzer()
            analyze_fn = getattr(analyzer, "analyze", None)
            if analyze_fn:
                if asyncio.iscoroutinefunction(analyze_fn):
                    # schedule coroutine in background using create_task
                    asyncio.create_task(analyze_fn(str(file_path)))
                else:
                    asyncio.create_task(asyncio.to_thread(analyze_fn, str(file_path)))
            results.append({"scanId": scan_id, "filename": fname})
        return JSONResponse(to_json_safe({"batchId": batch_id, "scans": results}))
       
    except Exception as e:
        logger.exception("scan_batch failed")
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
        original_filename = payload.get("original_filename") or payload.get("originalFilename")
        page = payload.get("page")

        # Find pdf path using same heuristics as original code
        scan_data = {}
        # attempt DB lookup for scan metadata if available
        try:
            if NEON_DATABASE_URL:
                rows = execute_query("SELECT * FROM scans WHERE scan_id=%s", (scan_id,), fetch=True)
                if rows:
                    scan_data = rows[0]
        except Exception:
            logger.exception("DB lookup for scan data failed; proceeding")

        pdf_path = Path(UPLOAD_FOLDER) / f"{scan_id}.pdf"
        if not pdf_path.exists():
            possible_paths = [
                Path(UPLOAD_FOLDER) / scan_id,
                Path(UPLOAD_FOLDER) / f"{scan_id.replace('.pdf','')}.pdf",
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
            return JSONResponse({"error": "Manual fix function not available"}, status_code=500)

        # call sync or async appropriately using to_thread if necessary
        if asyncio.iscoroutinefunction(apply_manual_fn):
            fix_result = await apply_manual_fn(str(pdf_path), fix_type, fix_data, page)
        else:
            fix_result = await asyncio.to_thread(apply_manual_fn, str(pdf_path), fix_type, fix_data, page)

        if not fix_result.get("success"):
            return JSONResponse({"error": fix_result.get("error", "Failed to apply manual fix")}, status_code=500)

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
                batch_id=scan_data.get("batch_id") if isinstance(scan_data, dict) else None,
                group_id=scan_data.get("group_id") if isinstance(scan_data, dict) else None,
                is_update=True,
            )
        except Exception:
            logger.exception("Failed to save updated scan to DB after manual fix")

        # Prepare fix history record
        fixes_applied = [
            {
                "type": "manual",
                "issueType": fix_type,
                "description": fix_result.get("description", "Manual fix applied successfully"),
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
        return FileResponse(str(upload_path), media_type="application/pdf", filename=safe_name)
    if fixed_path.exists():
        return FileResponse(str(fixed_path), media_type="application/pdf", filename=safe_name)
    return JSONResponse({"error": "File not found"}, status_code=404)


# === Apply Fixes Endpoint (wrapper around auto_fix_engine) ===
@app.post("/api/apply-fixes/{scan_id}")
async def apply_fixes(scan_id: str, background_tasks: BackgroundTasks):
    # call auto_fix_engine.apply_all or apply_fixes as in your original modules
    engine = AutoFixEngine()
    fn = getattr(engine, "apply_fixes", None) or getattr(engine, "apply_all", None) or getattr(engine, "apply", None)
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
        rows = execute_query("SELECT * FROM fixes WHERE scan_id=%s ORDER BY created_at DESC", (scan_id,), fetch=True)
        return JSONResponse(to_json_safe({"history": rows}))
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
        return JSONResponse({"scan_id": scan_id, "issues_detected": 0, "summary": "AI analyzer not implemented"})
    if asyncio.iscoroutinefunction(fn):
        res = await fn(scan_id)
    else:
        res = await asyncio.to_thread(fn, scan_id)
    return JSONResponse(res)


@app.post("/api/ai-fix-strategy/{scan_id}")
async def ai_fix_strategy(scan_id: str):
    fn = getattr(AutoFixEngine(), "generate_ai_strategy", None) or getattr(AutoFixEngine(), "ai_fix_strategy", None)
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
    fn = getattr(AutoFixEngine(), "generate_alt_text", None) or getattr(PDFAccessibilityAnalyzer(), "generate_alt_text", None)
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
    fn = getattr(AutoFixEngine(), "apply_ai_fixes", None) or getattr(AutoFixEngine(), "ai_apply_fixes", None)
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
    return JSONResponse(status_code=404, content={"error": "Route not found"})


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
