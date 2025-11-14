# backend/app.py

# Standard library imports
import os
import sys
import uuid
import asyncio
import logging
import traceback
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Third-party imports
from fastapi import (
    FastAPI,
    Request,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from werkzeug.utils import secure_filename

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Local application imports
from backend.multi_tier_storage import upload_file_with_fallback
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.auto_fix_engine import AutoFixEngine
from backend.routes import health_router, groups_router, scans_router, fixes_router
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
mount_static_if_available(app, "/fixed", FIXED_FOLDER, "fixed")
mount_static_if_available(
    app, "/generated_pdfs", app_helpers.GENERATED_PDFS_FOLDER, "generated_pdfs"
)

app.include_router(health_router)
app.include_router(groups_router)
app.include_router(scans_router)
app.include_router(fixes_router)


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
    services = (
        payload.get("services") if isinstance(payload.get("services"), list) else None
    )
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
        return JSONResponse(
            {"error": str(exc) or "Failed to generate PDF"}, status_code=500
        )


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
