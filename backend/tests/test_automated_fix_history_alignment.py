"""
Ensure automated fix history, summaries, and DB events stay consistent when remediation runs.
"""

import json

from backend.utils import app_helpers


class FakeCursor:
    def __init__(self, scan_row):
        self.scan_row = scan_row
        self.executed = []
        self.closed = False
        self._fetched = False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self._fetched:
            return None
        self._fetched = True
        return self.scan_row

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self, cursor_factory=None):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _run_remediation(monkeypatch, engine_result, initial_total=4):
    initial_summary = {"totalIssues": initial_total, "issuesRemaining": initial_total}
    initial_scan_payload = {
        "summary": initial_summary,
        "results": {
            "issues": [{"issueId": f"issue-{idx}"} for idx in range(initial_total)]
        },
    }
    scan_row = {
        "id": "scan-123",
        "filename": "example.pdf",
        "batch_id": None,
        "group_id": None,
        "scan_results": json.dumps(initial_scan_payload),
        "file_path": None,
        "total_issues": initial_total,
        "issues_fixed": 0,
        "issues_remaining": initial_total,
    }

    cursor = FakeCursor(scan_row)
    conn = FakeConnection(cursor)
    saved_history = []

    monkeypatch.setattr(app_helpers, "get_db_connection", lambda: conn)
    monkeypatch.setattr(app_helpers, "get_progress_tracker", lambda scan_id: None)
    monkeypatch.setattr(app_helpers, "create_progress_tracker", lambda scan_id: None)
    monkeypatch.setattr(app_helpers, "update_batch_statistics", lambda batch_id: None)
    monkeypatch.setattr(app_helpers, "archive_fixed_pdf_version", lambda *_, **__: None)
    monkeypatch.setattr(app_helpers, "_resolve_scan_file_path", lambda *_: None)

    def _save_fix_history(**kwargs):
        saved_history.append(kwargs)

    monkeypatch.setattr(app_helpers, "save_fix_history", _save_fix_history)

    class FakeEngine:
        def apply_automated_fixes(self, scan_id, scan_data, tracker=None):
            return engine_result

    monkeypatch.setattr(app_helpers, "AutoFixEngine", lambda: FakeEngine())

    status, payload = app_helpers._perform_automated_fix("scan-123", {}, None)
    return status, payload, saved_history


def test_automated_fix_without_history_keeps_zero_counts(monkeypatch):
    engine_result = {
        "success": True,
        "fixesApplied": [],
        "scanResults": {"summary": {"totalIssues": 4, "issuesRemaining": 4}, "results": {}},
    }

    status, payload, history = _run_remediation(monkeypatch, engine_result, initial_total=4)

    assert status == 200
    assert payload["fixesApplied"] == []
    assert payload["summary"]["issuesFixed"] == 0
    assert payload["summary"]["issuesRemaining"] == 4
    assert history == []


def test_automated_fix_counts_follow_history_entries(monkeypatch):
    fixes_applied = [
        {"type": "addLanguage", "description": "added language", "success": True},
        {"type": "addTitle", "description": "added title", "success": True},
    ]
    engine_result = {
        "success": True,
        "fixesApplied": fixes_applied,
        "scanResults": {"summary": {"totalIssues": 3, "issuesRemaining": 3}, "results": {}},
    }

    status, payload, history = _run_remediation(monkeypatch, engine_result, initial_total=5)

    assert status == 200
    summary = payload["summary"]
    assert payload["fixesApplied"] == fixes_applied
    assert summary["issuesFixed"] == len(fixes_applied)
    assert summary["issuesRemaining"] == 3
    assert summary["totalIssues"] == 5
    assert len(history) == 1
    assert history[0]["success_count"] == len(fixes_applied)
    assert len(history[0]["fixes_applied"]) == len(fixes_applied)
