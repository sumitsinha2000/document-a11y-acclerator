from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime
import threading
import time
from pathlib import Path
import shutil
import uuid  # ✅ Added import for unique ID generation

import psycopg2
from psycopg2.extras import RealDictCursor

from pdf_analyzer import PDFAccessibilityAnalyzer
from fix_suggestions import generate_fix_suggestions
from auto_fix_engine import AutoFixEngine
from fix_progress_tracker import create_progress_tracker, get_progress_tracker

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

NEON_DATABASE_URL = os.getenv("DATABASE_URL")

db_lock = threading.Lock()


# === Database Connection ===
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"[Backend] ✗ Database connection failed: {e}")
        raise


def execute_query(query, params=None, fetch=False):
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
            print(f"[Backend] ✗ Query execution failed: {e}")
            raise


# === Fixed save_scan_to_db ===
def save_scan_to_db(scan_id, filename, scan_results, batch_id=None, is_update=False):
    """
    Unified save logic:
    - Inserts a new record if is_update=False (always creates a new scan even if same file name).
    - Updates the existing record if is_update=True.
    """
    conn = None
    c = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        if is_update:
            # === UPDATE EXISTING SCAN ===
            print(f"[Backend] 🔄 Updating scan record: {scan_id}")
            query = '''
                UPDATE scans
                SET scan_results = %s,
                    filename = %s,
                    upload_date = NOW(),
                    status = 'updated'
                WHERE id = %s
            '''
            c.execute(query, (json.dumps(scan_results), filename, scan_id))
            conn.commit()
            print(f"[Backend] ✅ Updated existing scan successfully: {scan_id}")
            return scan_id

        else:
            # === INSERT NEW SCAN (always new record, even same filename) ===
            try:
                unique_id = f"scan_{uuid.uuid4().hex}"
                query = '''
                    INSERT INTO scans (id, filename, scan_results, batch_id, status, upload_date, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET scan_results = EXCLUDED.scan_results,
                        status = EXCLUDED.status,
                        created_at = NOW()
                '''
                status = 'completed'
                c.execute(query, (unique_id, filename, json.dumps(scan_results), batch_id, status))
                conn.commit()
                print(f"[Backend] ✅ Inserted new scan record: {unique_id} ({filename})")
                return unique_id

            except Exception as e:
                conn.rollback()
                print(f"[Backend] ✗ Insert failed: {e}")
                import traceback
                traceback.print_exc()
                return None

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[Backend] ✗ Failed to save scan: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if c:
            c.close()
        if conn:
            conn.close()


# === Health Check ===
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


# === PDF Scan ===
@app.route("/api/scan", methods=["POST"])
def scan_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files supported"}), 400

    scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / f"{scan_id}.pdf"
    file.save(str(file_path))
    print(f"[Backend] ✓ File saved: {file_path}")

    analyzer = PDFAccessibilityAnalyzer()
    scan_results = analyzer.analyze(str(file_path))
    summary = analyzer.calculate_summary(scan_results)
    fix_suggestions = generate_fix_suggestions(scan_results)

    saved_id = save_scan_to_db(scan_id, file.filename, {"results": scan_results, "summary": summary})
    print(f"[Backend] ✓ Scan record saved as {saved_id}")

    return jsonify({
        "scanId": saved_id,
        "filename": file.filename,
        "summary": summary,
        "results": scan_results,
        "fixes": fix_suggestions,
        "timestamp": datetime.now().isoformat()
    })


# === Scan History ===
@app.route("/api/scans", methods=["GET"])
def get_scans():
    scans = execute_query(
        "SELECT id, filename, upload_date, status FROM scans ORDER BY upload_date DESC",
        fetch=True
    )
    return jsonify({"scans": scans})


# === Apply Fixes ===
@app.route("/api/apply-fixes/<scan_id>", methods=["POST"])
def apply_fixes(scan_id):
    try:
        data = request.get_json()
        fixes = data.get("fixes", [])
        filename = data.get("filename", "fixed_document.pdf")
        
        # Ensure filename has .pdf extension
        if not filename.lower().endswith('.pdf'):
            filename = f"{filename}.pdf"

        print(f"[Backend] Applying fixes for scan: {scan_id}")
        
        # Get scan data from database
        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404

        progress_id = create_progress_tracker(scan_id)
        tracker = get_progress_tracker(progress_id)
        
        engine = AutoFixEngine()
        
        result = engine.apply_automated_fixes(scan_id, scan_data, tracker)
        
        if result.get('success'):
            # Update existing scan with new results
            save_scan_to_db(scan_id, filename, result, is_update=True)
            
            # Save fix history
            save_fix_history(scan_id, filename, result.get('fixesApplied', []), result.get('fixedFile'))
            
            return jsonify({
                "status": "success",
                "fixedFile": result.get('fixedFile'),
                "summary": result
            })
        else:
            return jsonify({
                "status": "error",
                "error": result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        print(f"[Backend] ERROR in apply_fixes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Apply Semi-Automated Fixes ===
@app.route("/api/apply-semi-automated-fixes/<scan_id>", methods=["POST"])
def apply_semi_automated_fixes(scan_id):
    try:
        print(f"[Backend] ========== APPLY SEMI-AUTOMATED FIXES ==========")
        print(f"[Backend] Scan ID: {scan_id}")
        
        data = request.get_json()
        fixes = data.get("fixes", [])
        filename = data.get("filename", "document.pdf")
        
        # Ensure filename has .pdf extension
        if not filename.lower().endswith('.pdf'):
            filename = f"{filename}.pdf"
        
        print(f"[Backend] Filename: {filename}")
        print(f"[Backend] Fixes to apply: {len(fixes)}")
        
        # Get scan data from database
        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404
        
        # Create progress tracker
        progress_id = create_progress_tracker(scan_id)
        tracker = get_progress_tracker(progress_id)
        
        # Initialize engine and apply fixes
        engine = AutoFixEngine()
        
        # Use the correct method name
        result = engine.apply_semi_automated_fixes(scan_id, scan_data, tracker)
        
        if result.get('success'):
            # Update existing scan record (don't create new one)
            save_scan_to_db(scan_id, filename, result, is_update=True)
            
            # Save fix history (don't delete existing history)
            save_fix_history(scan_id, filename, result.get('fixesApplied', []), result.get('fixedFile'))
            
            return jsonify({
                "status": "success",
                "fixedFile": result.get('fixedFile'),
                "summary": result
            })
        else:
            return jsonify({
                "status": "error",
                "error": result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        print(f"[Backend] ERROR in apply_semi_automated_fixes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Download File ===
@app.route("/api/download/<path:scan_id>", methods=["GET"])
def download_file(scan_id):
    uploads_dir = Path("uploads")
    fixed_dir = Path("fixed")

    file_path = None
    for folder in [fixed_dir, uploads_dir]:
        path = folder / f"{scan_id}.pdf"
        if path.exists():
            file_path = path
            break

    if not file_path:
        return jsonify({"error": "File not found"}), 404

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{scan_id}.pdf"
    )


# === Progress Tracker ===
@app.route("/api/progress/<scan_id>", methods=["GET"])
def get_progress(scan_id):
    progress = get_progress_tracker(scan_id)
    return jsonify(progress)


# === History Component ===
@app.route("/api/history", methods=["GET", "OPTIONS"])
def get_history():
    """Get all scans and batches for history view"""
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        scans = execute_query(
            """
            SELECT id, filename, upload_date as "uploadDate", status, scan_results
            FROM scans 
            ORDER BY upload_date DESC
            """,
            fetch=True
        )
        
        for scan in scans:
            scan_data = scan.get('scan_results', {})
            if isinstance(scan_data, str):
                scan_data = json.loads(scan_data)
            
            summary = scan_data.get('summary', {})
            scan['summary'] = {
                'totalIssues': summary.get('total_issues', 0),
                'critical': summary.get('critical', 0),
                'error': summary.get('error', 0),
                'warning': summary.get('warning', 0)
            }
            # Remove scan_results from response to keep it clean
            del scan['scan_results']
        
        # Get all batches (if batch table exists)
        batches = []
        try:
            batches = execute_query(
                """
                SELECT id as "batchId", name, upload_date as "uploadDate", 
                       status, file_count as "fileCount", total_issues as "totalIssues"
                FROM batches 
                ORDER BY upload_date DESC
                """,
                fetch=True
            )
        except Exception as e:
            print(f"[Backend] No batches table or error: {e}")
        
        return jsonify({
            "scans": scans,
            "batches": batches
        })
    except Exception as e:
        print(f"[Backend] Error fetching history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Fix History ===
@app.route("/api/fix-history/<scan_id>", methods=["GET", "OPTIONS"])
def get_fix_history(scan_id):
    """Get fix history for a specific scan"""
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        print(f"[Backend] Fetching fix history for scan: {scan_id}")
        
        fixes = execute_query(
            """
            SELECT id, scan_id as "scanId", original_file as "originalFile",
                   fixed_file as "fixedFile", fixes_applied as "fixesApplied",
                   success_count as "successCount", timestamp
            FROM fix_history 
            WHERE scan_id = %s 
            ORDER BY timestamp DESC
            """,
            (scan_id,),
            fetch=True
        )
        
        print(f"[Backend] Found {len(fixes)} fixes for scan {scan_id}")
        return jsonify({"fixes": fixes})
    except Exception as e:
        print(f"[Backend] Error fetching fix history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Individual Scan Details ===
@app.route("/api/scan/<scan_id>", methods=["GET"])
def get_scan(scan_id):
    """Fetch individual scan details by scan_id"""
    try:
        print(f"[Backend] Fetching scan details for: {scan_id}")
        
        # Try multiple query strategies to find the scan
        # Strategy 1: Query by id
        query = "SELECT * FROM scans WHERE id = %s"
        result = execute_query(query, (scan_id,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            print(f"[Backend] ✓ Found scan by id: {scan_id}")
            return jsonify(scan)
        
        # Strategy 2: Try without .pdf extension
        scan_id_no_ext = scan_id.replace('.pdf', '')
        result = execute_query(query, (scan_id_no_ext,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            print(f"[Backend] ✓ Found scan by id (no extension): {scan_id_no_ext}")
            return jsonify(scan)
        
        # Strategy 3: Query by filename
        query = "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1"
        result = execute_query(query, (scan_id,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            print(f"[Backend] ✓ Found scan by filename: {scan_id}")
            return jsonify(scan)
        
        # If still not found, list all available scans for debugging
        print(f"[Backend] Scan not found: {scan_id}")
        all_scans = execute_query("SELECT id, filename FROM scans ORDER BY created_at DESC LIMIT 10", fetch=True)
        print(f"[Backend] Available scans in database:")
        for s in all_scans:
            print(f"[Backend]   - id: '{s['id']}', filename: '{s['filename']}'")
        
        return jsonify({"error": f"Scan not found: {scan_id}"}), 404
        
    except Exception as e:
        print(f"[Backend] Error fetching scan: {e}")
        return jsonify({"error": str(e)}), 500


# === Delete Scan ===
@app.route("/api/scan/<scan_id>", methods=["DELETE"])
def delete_scan(scan_id):
    """Delete an individual scan and its associated files"""
    try:
        print(f"[Backend] Deleting scan: {scan_id}")
        
        # Get scan info before deleting
        scan = get_scan_by_id(scan_id)
        if not scan:
            return jsonify({"error": "Scan not found"}), 404
        
        # Delete physical files
        uploads_dir = Path("uploads")
        fixed_dir = Path("fixed")
        deleted_files = 0
        
        for folder in [uploads_dir, fixed_dir]:
            # Try with and without .pdf extension
            for ext in ['', '.pdf']:
                file_path = folder / f"{scan_id}{ext}"
                if file_path.exists():
                    file_path.unlink()
                    deleted_files += 1
                    print(f"[Backend] Deleted file: {file_path}")
        
        # Delete from database
        execute_query("DELETE FROM fix_history WHERE scan_id = %s", (scan_id,), fetch=False)
        execute_query("DELETE FROM scans WHERE id = %s", (scan_id,), fetch=False)
        
        print(f"[Backend] ✓ Deleted scan {scan_id} ({deleted_files} files)")
        
        return jsonify({
            "success": True,
            "message": f"Deleted scan and {deleted_files} file(s)",
            "deletedFiles": deleted_files
        })
        
    except Exception as e:
        print(f"[Backend] Error deleting scan: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Save Fix History ===
def save_fix_history(scan_id, original_file, fixes_applied, fixed_file):
    """Save fix history without deleting existing records"""
    try:
        # Ensure filenames have .pdf extension
        if not original_file.lower().endswith('.pdf'):
            original_file = f"{original_file}.pdf"
        if fixed_file and not fixed_file.lower().endswith('.pdf'):
            fixed_file = f"{fixed_file}.pdf"
        
        query = """
            INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count, timestamp)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """
        
        import json
        execute_query(
            query,
            (scan_id, original_file, fixed_file, json.dumps(fixes_applied), len(fixes_applied)),
            fetch=False
        )
        
        print(f"[Backend] ✓ Saved fix history for scan: {scan_id}")
        return True
    except Exception as e:
        print(f"[Backend] ✗ Error saving fix history: {e}")
        import traceback
        traceback.print_exc()
        return False


# === Get Scan by ID ===
def get_scan_by_id(scan_id):
    """Get scan by ID with multiple fallback strategies and ensure .pdf extension"""
    try:
        print(f"[Backend] Looking up scan: {scan_id}")
        
        # Strategy 1: Query by exact id
        query = "SELECT * FROM scans WHERE id = %s"
        result = execute_query(query, (scan_id,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            if 'file_path' in scan and not scan['file_path'].endswith('.pdf'):
                scan['file_path'] = f"{scan['file_path']}.pdf"
            print(f"[Backend] ✓ Found scan by id")
            return scan
        
        # Strategy 2: Try without .pdf extension
        scan_id_no_ext = scan_id.replace('.pdf', '')
        result = execute_query(query, (scan_id_no_ext,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            if 'file_path' in scan and not scan['file_path'].endswith('.pdf'):
                scan['file_path'] = f"{scan['file_path']}.pdf"
            print(f"[Backend] ✓ Found scan by id (without extension)")
            return scan
        
        # Strategy 3: Query by filename
        query = "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1"
        result = execute_query(query, (scan_id,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            if 'file_path' in scan and not scan['file_path'].endswith('.pdf'):
                scan['file_path'] = f"{scan['file_path']}.pdf"
            print(f"[Backend] ✓ Found scan by filename")
            return scan
        
        print(f"[Backend] ✗ Scan not found: {scan_id}")
        return None
        
    except Exception as e:
        print(f"[Backend] Error getting scan: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("[Backend] 🚀 Starting Flask server...")
    app.run(host="0.0.0.0", port=5000, debug=True)
