from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import tempfile
import os
import traceback

# Import your backend modules
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.pdfa_validator import PDFAValidator
from backend.auto_fix_engine import AutoFixEngine
from backend.fix_progress_tracker import FixProgressTracker

app = FastAPI(title="DocA11y Vercel Backend")

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Utility function to save uploaded file ---
def _save_temp_pdf(upload_file: UploadFile):
    """Save uploaded file temporarily"""
    suffix = os.path.splitext(upload_file.filename)[-1]
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_file.write(upload_file.file.read())
    tmp_file.close()
    return tmp_file.name


# --- Health check ---
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend running successfully on Vercel"}


# --- PDF Accessibility Scan ---
@app.post("/api/scan")
async def scan_pdf(file: UploadFile = File(...)):
    """Analyze uploaded PDF for accessibility and PDF/A compliance"""
    try:
        pdf_path = _save_temp_pdf(file)
        analyzer = PDFAccessibilityAnalyzer()
        results = analyzer.analyze(pdf_path)

        # Run PDF/A validation as well
        validator = PDFAValidator(None)
        import pikepdf
        pdf = pikepdf.open(pdf_path)
        validator = PDFAValidator(pdf)
        pdfa_results = validator.validate()
        pdf.close()

        results["pdfaResults"] = pdfa_results

        return {
            "filename": file.filename,
            "totalIssues": sum(len(v) for v in results.values() if isinstance(v, list)),
            "results": results,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error analyzing PDF: {e}")


# --- Apply Automatic Fixes ---
@app.post("/api/apply-fixes")
async def apply_fixes(file: UploadFile = File(...)):
    """Run automated PDF fixes"""
    try:
        pdf_path = _save_temp_pdf(file)
        tracker = FixProgressTracker(scan_id=file.filename, total_steps=6)
        tracker.add_step("Initialize AutoFix Engine", "Preparing fix engine")
        tracker.start_step(1)

        engine = AutoFixEngine()
        tracker.complete_step(1, "AutoFix Engine initialized")

        tracker.add_step("Analyze PDF", "Running PDF accessibility analysis")
        tracker.start_step(2)
        analyzer = PDFAccessibilityAnalyzer()
        results = analyzer.analyze(pdf_path)
        tracker.complete_step(2, "Analysis complete")

        tracker.add_step("Generate Fix Plan", "Creating automatic fix suggestions")
        tracker.start_step(3)
        fixes = engine.generate_fixes(results)
        tracker.complete_step(3, "Fix plan generated", result_data=fixes)

        tracker.add_step("Apply Fixes", "Applying automated fixes to PDF")
        tracker.start_step(4)
        fixed_data = engine.pdfa_engine.apply_pdfa_fixes(pdf_path)
        tracker.complete_step(4, "Fixes applied successfully")

        tracker.add_step("Re-analyze", "Verifying fixed PDF")
        tracker.start_step(5)
        post_analysis = engine._analyze_fixed_pdf(fixed_data["fixed_pdf_path"])
        tracker.complete_step(5, "Post-analysis complete")

        tracker.complete_all()

        return {
            "filename": file.filename,
            "fixSummary": tracker.__dict__,
            "analysisBefore": results,
            "analysisAfter": post_analysis,
            "fixes": fixes,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error applying fixes: {e}")


# --- AI Fix Strategy (placeholder for your AI module) ---
@app.post("/api/ai-fix-strategy")
async def ai_fix_strategy(file: UploadFile = File(...)):
    """Return AI-based fix strategy (to integrate later)"""
    return {"message": "AI fix strategy endpoint available, integrate OpenAI later"}


# --- PDF/A Validation Only ---
@app.post("/api/pdfa-validate")
async def pdfa_validate(file: UploadFile = File(...)):
    """Validate PDF/A conformance"""
    try:
        pdf_path = _save_temp_pdf(file)
        import pikepdf
        pdf = pikepdf.open(pdf_path)
        validator = PDFAValidator(pdf)
        results = validator.validate()
        pdf.close()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF/A validation failed: {e}")


# --- Fix History Placeholder ---
@app.get("/api/fix-history/{scan_id}")
def fix_history(scan_id: str):
    return {"scan_id": scan_id, "history": ["Analyzed", "Fixed", "Re-analyzed"]}


# Vercel handler
handler = Mangum(app)
