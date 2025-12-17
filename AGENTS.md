# AGENTS.md

## Repository Description

Document Accessibility Hub is a monorepo that powers an end-to-end PDF accessibility scanner, automated remediation engine, and reporting suite aligned with WCAG 2.1/2.2 and PDF/UA standards.
The project delivers a responsive React + Vite frontend (light and dark modes) backed by a modular FastAPI service responsible for PDF parsing, accessibility validation, remediation logic, and export workflows.

### Top-level structure

- `backend/` — FastAPI app (`app.py`) exposing routes for uploads, scan results, and remediation actions. Core modules include `pdf_analyzer.py`, `wcag_validator.py`, `pdf_fix_engine.py`, `auto_fix_engine.py`, and `unified_conformance_checker.py`, supported by helpers for OCR, metadata repair, PDF/A validation, and veraPDF integration. Includes documentation, database scripts, and pytest suites under `backend/tests`.

- `frontend/` — React 18 + Vite client with Tailwind styling, a professional loading screen, upload area, dashboards, and project/folder management views. Axios services are configured via `VITE_BACKEND_URL`. Accessibility considerations (focus states, contrast, keyboard support) are consistently enforced across components.

- `scripts/` — SQL migrations and administrative utilities for provisioning the PostgreSQL database used for scan history, projects, folders, and user accounts.

- `documentation/` — Deployment, validator, and infrastructure guides referenced from the main README.

- Deployment assets — `public/`, `vercel.json`, `render.yaml`, and related files for hosting both frontend and backend services.

---

## Application Workflow

Users land on the Project Dashboard. From here:

1. They may create or select a project.
2. Expanding a project displays its folders.
3. Selecting a folder opens the Folder Dashboard, which presents:

    - upload area for single or multiple PDFs
    - preview and removal of selected files before upload
    - scan results, grouped by severity and standards
    - automated remediation actions
    - export options for PDF or CSV reports

From the Folder Dashboard, users can:

- upload documents
- initiate scans
- view issue summaries
- apply automated fixes
- download the remediated file or issue reports

Pages such as history and advanced project analytics are intentionally disabled.

---

## Dev Environment

- The sandbox cannot run Python, pytest, or execute code files.
  Use only basic shell commands (`ls`, `git`, `grep`, `cat`, `tail`, etc.).
  This is agent-mode, not full shell access.

- When asked to “run” something, provide the correct local command rather than executing it.

---

## Testing

- Tests are located under `backend/tests` and use pytest.
- Do not run tests inside the sandbox.
- When requested, provide only the local pytest command to run, such as:

  - `pytest backend/tests -vv`
  - `pytest backend/tests/test_pdf_analyzer.py`

---

## Git Commits

- Never commit, push, merge, or open PRs.
- When the user asks for a commit message:

  1. Read staged files (fallback to unstaged if none).
  2. Output:

     Title:
     `[fix|feat|chore|refactor|docs|test] <title>`

     Body:

     - unordered bullet list summarizing the changes

Example:

```markdown
[fix] correct alt-text fallback

- Adjust MCID lookup to avoid false missing-alt in <file_name>
- Prevent duplicate issues across WCAG buckets <file_name 2>
```

---

## General Instructions

- When modifying or building UI components under `/frontend`, always ensure adherence to WCAG accessibility standards.

- **NOTE**: The whole repo is in a state of switching 2 certain words in the frontend - group / projects and batch / folder. Right now, the user facing elements have been changed accordingly while the backend and logic has been left to avoid breaking. Slowly bit by bit where possible, Project and Folder will be used.
