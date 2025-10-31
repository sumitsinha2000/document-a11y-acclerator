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

DATABASE_URL = os.getenv("DATABASE_URL")

db_lock = threading.Lock()

UPLOAD_FOLDER = "uploads"
FIXED_FOLDER = "fixed"

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
    - Updates the existing record if is_update=True with "fixed" status.
    - Properly stores scan_results as JSONB with all issue data
    """
    conn = None
    c = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        # Ensure scan_results is properly formatted
        if isinstance(scan_results, dict):
            # If scan_results has 'results' and 'summary' keys, use them
            if 'results' in scan_results and 'summary' in scan_results:
                formatted_results = scan_results
            else:
                # Otherwise, wrap it properly
                formatted_results = {
                    'results': scan_results,
                    'summary': {
                        'totalIssues': sum(len(v) if isinstance(v, list) else 0 for v in scan_results.values()),
                        'critical': 0,
                        'error': 0,
                        'warning': 0
                    }
                }
        else:
            formatted_results = scan_results

        if is_update:
            # === UPDATE EXISTING SCAN ===
            print(f"[Backend] 🔄 Updating scan record: {scan_id}")
            query = '''
                UPDATE scans
                SET scan_results = %s,
                    filename = %s,
                    upload_date = NOW(),
                    status = 'fixed'
                WHERE id = %s
            '''
            c.execute(query, (json.dumps(formatted_results), filename, scan_id))
            conn.commit()
            print(f"[Backend] ✅ Updated existing scan successfully: {scan_id}")
            return scan_id

        else:
            # === INSERT NEW SCAN (always new record, even same filename) ===
            try:
                query = '''
                    INSERT INTO scans (id, filename, scan_results, batch_id, status, upload_date, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET scan_results = EXCLUDED.scan_results,
                        status = EXCLUDED.status,
                        created_at = NOW()
                '''
                status = 'completed'
                c.execute(query, (scan_id, filename, json.dumps(formatted_results), batch_id, status))
                conn.commit()
                print(f"[Backend] ✅ Inserted new scan record: {scan_id} ({filename})")
                return scan_id

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

    scan_id = f"scan_{uuid.uuid4().hex}"
    upload_dir = Path(UPLOAD_FOLDER)
    upload_dir.mkdir(exist_ok=True)
    
    # Ensure .pdf extension
    file_path = upload_dir / f"{scan_id}.pdf"
    file.save(str(file_path))
    print(f"[Backend] ✓ File saved: {file_path}")

    analyzer = PDFAccessibilityAnalyzer()
    scan_results = analyzer.analyze(str(file_path))
    summary = analyzer.calculate_summary(scan_results)
    
    fix_suggestions = generate_fix_suggestions(scan_results)
    
    wcag_issues = scan_results.get('wcagIssues', [])
    pdfa_issues = scan_results.get('pdfaIssues', [])
    pdfua_issues = scan_results.get('pdfuaIssues', [])
    total_issues = sum(len(v) if isinstance(v, list) else 0 for v in scan_results.values())
    
    wcag_compliance = max(0, 100 - len(wcag_issues) * 5) if wcag_issues else 100
    pdfa_compliance = max(0, 100 - len(pdfa_issues) * 5) if pdfa_issues else 100
    pdfua_compliance = max(0, 100 - len(pdfua_issues) * 5) if pdfua_issues else 100
    
    formatted_results = {
        'results': scan_results,
        'summary': {
            'totalIssues': total_issues,
            'highSeverity': len([i for issues in scan_results.values() if isinstance(issues, list) for i in issues if isinstance(i, dict) and i.get('severity') in ['high', 'critical']]),
            'complianceScore': max(0, 100 - total_issues * 2),
            'wcagCompliance': wcag_compliance,
            'pdfaCompliance': pdfa_compliance,
            'pdfuaCompliance': pdfua_compliance,
            'critical': summary.get('critical', 0),
            'error': summary.get('error', 0),
            'warning': summary.get('warning', 0)
        },
        'fixes': fix_suggestions
    }

    saved_id = save_scan_to_db(scan_id, file.filename, formatted_results)
    print(f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues")

    return jsonify({
        "scanId": saved_id,
        "filename": file.filename,
        "summary": formatted_results['summary'],
        "results": scan_results,
        "fixes": fix_suggestions,
        "timestamp": datetime.now().isoformat(),
        "verapdfStatus": {
            "isActive": True,
            "wcagCompliance": wcag_compliance,
            "pdfuaCompliance": pdfua_compliance,
            "totalVeraPDFIssues": len(wcag_issues) + len(pdfa_issues) + len(pdfua_issues)
        }
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
        tracker = get_progress_tracker(scan_id)  # Use scan_id instead of progress_id
        
        engine = AutoFixEngine()
        
        result = engine.apply_automated_fixes(scan_id, scan_data, tracker)
        
        if result.get('success'):
            # Update existing scan with new results
            save_scan_to_db(scan_id, filename, result, is_update=True)
            
            # Save fix history
            save_fix_history(scan_id, scan_data['filename'], result.get('fixesApplied', []), result.get('fixedFile'))
            
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
        data = request.get_json()
        fixes = data.get("fixes", [])
        
        print(f"[Backend] ========== APPLY SEMI-AUTOMATED FIXES ==========")
        print(f"[Backend] Scan ID: {scan_id}")
        
        # Get scan data
        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404
        
        original_filename = scan_data.get('filename', 'document.pdf')
        print(f"[Backend] Filename: {original_filename}")
        print(f"[Backend] Fixes to apply: {len(fixes)}")
        
        # Initialize engine
        engine = AutoFixEngine()
        
        # Apply fixes
        result = engine.apply_semi_automated_fixes(scan_id, scan_data, fixes)
        
        if result.get('success'):
            # Preserve original filename with "fixed_" prefix
            base_name = original_filename.rsplit('.', 1)[0]
            extension = original_filename.rsplit('.', 1)[1] if '.' in original_filename else 'pdf'
            fixed_filename = f"fixed_{base_name}.{extension}"
            
            # Update scan with "fixed" status
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                UPDATE scans 
                SET status = 'fixed', 
                    filename = %s,
                    upload_date = NOW()
                WHERE id = %s
            ''', (fixed_filename, scan_id))
            conn.commit()
            c.close()
            conn.close()
            
            # Save fix history
            save_fix_history(scan_id, original_filename, result.get('fixesApplied', []), result.get('fixedFile'))
            
            return jsonify({
                "status": "success",
                "fixedFile": result.get('fixedFile'),
                "summary": result,
                "filename": fixed_filename
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
    uploads_dir = Path(UPLOAD_FOLDER)
    fixed_dir = Path(FIXED_FOLDER)

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
            SELECT id, scan_id as "scanId", original_filename as "originalFile",
                   fixed_filename as "fixedFile", fixes_applied as "fixesApplied",
                   applied_at as "timestamp"
            FROM fix_history 
            WHERE scan_id = %s 
            ORDER BY applied_at DESC
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
    """Fetch individual scan details by scan_id with WCAG and PDF/A stats"""
    try:
        print(f"[Backend] Fetching scan details for: {scan_id}")
        
        # Try multiple query strategies to find the scan
        query = "SELECT * FROM scans WHERE id = %s"
        result = execute_query(query, (scan_id,), fetch=True)
        
        if not result or len(result) == 0:
            # Try without .pdf extension
            scan_id_no_ext = scan_id.replace('.pdf', '')
            result = execute_query(query, (scan_id_no_ext,), fetch=True)
        
        if not result or len(result) == 0:
            # Try by filename
            query = "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1"
            result = execute_query(query, (scan_id,), fetch=True)
        
        if result and len(result) > 0:
            scan = dict(result[0])
            
            # Parse scan_results if it's a string
            scan_results = scan.get('scan_results', {})
            if isinstance(scan_results, str):
                scan_results = json.loads(scan_results)
            
            results = scan_results.get('results', scan_results)
            summary = scan_results.get('summary', {})
            
            if not summary or 'totalIssues' not in summary or summary.get('totalIssues', 0) == 0:
                total_issues = sum(len(v) if isinstance(v, list) else 0 for v in results.values())
                wcag_issues = results.get('wcagIssues', [])
                pdfa_issues = results.get('pdfaIssues', [])
                pdfua_issues = results.get('pdfuaIssues', [])
                
                summary = {
                    'totalIssues': total_issues,
                    'highSeverity': len([i for issues in results.values() if isinstance(issues, list) for i in issues if isinstance(i, dict) and i.get('severity') in ['high', 'critical']]),
                    'complianceScore': max(0, 100 - total_issues * 2),
                    'wcagCompliance': max(0, 100 - len(wcag_issues) * 5),
                    'pdfaCompliance': max(0, 100 - len(pdfa_issues) * 5),
                    'pdfuaCompliance': max(0, 100 - len(pdfua_issues) * 5)
                }
            
            fix_suggestions = generate_fix_suggestions(results)
            
            response_data = {
                'scanId': scan['id'],
                'id': scan['id'],
                'filename': scan['filename'],
                'fileName': scan['filename'],
                'uploadDate': scan.get('upload_date', scan.get('created_at')),
                'timestamp': scan.get('upload_date', scan.get('created_at')),
                'status': scan.get('status', 'completed'),
                'results': results,
                'summary': summary,
                'fixes': fix_suggestions,
                'verapdfStatus': {
                    'isActive': True,
                    'wcagCompliance': summary.get('wcagCompliance', 0),
                    'pdfuaCompliance': summary.get('pdfaCompliance', 0),
                    'totalVeraPDFIssues': len(results.get('wcagIssues', [])) + len(results.get('pdfaIssues', [])) + len(results.get('pdfuaIssues', []))
                }
            }
            
            print(f"[Backend] ✓ Found scan: {scan_id}, Total issues: {summary.get('totalIssues', 0)}, WCAG: {summary.get('wcagCompliance', 0)}%, PDF/A: {summary.get('pdfaCompliance', 0)}%")
            return jsonify(response_data)
        
        print(f"[Backend] Scan not found: {scan_id}")
        return jsonify({"error": f"Scan not found: {scan_id}"}), 404
        
    except Exception as e:
        print(f"[Backend] Error fetching scan: {e}")
        import traceback
        traceback.print_exc()
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
        uploads_dir = Path(UPLOAD_FOLDER)
        fixed_dir = Path(FIXED_FOLDER)
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
def save_fix_history(scan_id, original_filename, fixes_applied, fixed_file_path):
    """Save fix history with proper filename preservation"""
    conn = None
    c = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Extract just the filename from the path if it's a full path
        if fixed_file_path and '/' in fixed_file_path:
            fixed_filename = fixed_file_path.split('/')[-1]
        elif fixed_file_path and '\\' in fixed_file_path:
            fixed_filename = fixed_file_path.split('\\')[-1]
        else:
            fixed_filename = fixed_file_path
        
        # Preserve original filename with "fixed_" prefix
        if original_filename:
            base_name = original_filename.rsplit('.', 1)[0]
            extension = original_filename.rsplit('.', 1)[1] if '.' in original_filename else 'pdf'
            fixed_filename = f"fixed_{base_name}.{extension}"
        
        query = '''
            INSERT INTO fix_history (scan_id, original_filename, fixed_filename, fixes_applied, applied_at)
            VALUES (%s, %s, %s, %s, NOW())
        '''
        c.execute(query, (scan_id, original_filename, fixed_filename, json.dumps(fixes_applied)))
        conn.commit()
        
        print(f"[Backend] ✓ Fix history saved: {original_filename} -> {fixed_filename}")
        return True
    except Exception as e:
        print(f"[Backend] ERROR saving fix history: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if c:
            c.close()
        if conn:
            conn.close()


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


@app.route("/api/fix-progress/<scan_id>", methods=["GET"])
def get_fix_progress(scan_id):
    """Get real-time progress of fix application"""
    try:
        from fix_progress_tracker import get_progress_tracker
        
        tracker = get_progress_tracker(scan_id)
        if not tracker:
            return jsonify({
                "error": "No progress tracking found for this scan",
                "scanId": scan_id
            }), 404
        
        progress = tracker.get_progress()
        return jsonify(progress), 200
        
    except Exception as e:
        print(f"[Backend] Error getting fix progress: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# Add download endpoint for fix history files
@app.route("/api/download-fix-history/<scan_id>", methods=["GET"])
def download_fix_history_file(scan_id):
    """Download the fixed PDF from fix history"""
    try:
        # Get the latest fix history for this scan
        query = """
            SELECT fixed_filename FROM fix_history 
            WHERE scan_id = %s 
            ORDER BY applied_at DESC 
            LIMIT 1
        """
        result = execute_query(query, (scan_id,), fetch=True)
        
        if not result or len(result) == 0:
            return jsonify({"error": "No fix history found"}), 404
        
        fixed_filename = result[0]['fixed_filename']
        fixed_dir = Path(FIXED_FOLDER)
        
        # Try multiple file path strategies
        file_path = None
        for ext in ['', '.pdf']:
            path = fixed_dir / f"{scan_id}{ext}"
            if path.exists():
                file_path = path
                break
        
        if not file_path:
            # Try using the fixed_filename directly
            path = fixed_dir / fixed_filename
            if path.exists():
                file_path = path
        
        if not file_path:
            return jsonify({"error": "Fixed file not found"}), 404
        
        return send_file(
            file_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=fixed_filename
        )
        
    except Exception as e:
        print(f"[Backend] Error downloading fix history file: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Download Fixed File ===
@app.route("/api/download-fixed/<scan_id>", methods=["GET"])
def download_fixed_file(scan_id):
    """Download the fixed PDF file"""
    try:
        # Get fix history to find the fixed file
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            SELECT fixed_filename, original_filename 
            FROM fix_history 
            WHERE scan_id = %s 
            ORDER BY applied_at DESC 
            LIMIT 1
        ''', (scan_id,))
        result = c.fetchone()
        c.close()
        conn.close()
        
        if not result:
            return jsonify({"error": "No fixed file found"}), 404
        
        fixed_filename = result[0]
        original_filename = result[1]
        
        # Construct file path
        file_path = os.path.join(FIXED_FOLDER, fixed_filename)
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Fixed file not found on disk"}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=fixed_filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"[Backend] ERROR downloading fixed file: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[Backend] 🚀 Starting Flask server...")
    app.run(host="0.0.0.0", port=5000, debug=True)
