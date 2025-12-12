# Backend Testing

All backend tests live under `backend/tests/` and use pytest fixtures plus PDF fixtures stored in `backend/tests/fixtures/`.

## Test Suites

- `test_health.py` – Fast sanity check that the FastAPI health endpoint returns HTTP 200 using the shared `client` fixture.
- `test_alt_detection.py` – Unit tests for WCAG alt-text detection helpers using tagged PDFs. Contains one `alt_fallback` regression test that is intentionally skipped by default.
- `test_contrast_scan_pypdf.py` – Exercises the PyPDF-backed contrast scanner with controlled synthetic PDFs covering low/high contrast and missing content streams.
- `test_metadata_analyzer_pypdf.py` – Validates metadata extraction (title, language, tagging) using catalog fixtures, ensuring backward compatibility while parser logic evolves.
- `test_pdf_integration.py` – End-to-end analyzer runs against real PDFs. These are tagged `slow_pdf` because they open full documents, parse all pages, and compute summaries/fix suggestions.
- `test_automated_fix_history_alignment.py` – Exercises the automated remediation helper in `backend.utils.app_helpers` to keep summary counters and saved history aligned with fix output.
- `test_link_annotation_detection.py` – Ensures WCAG link-purpose validation handles varied annotation encodings and respects descriptive-text heuristics (2.4.4) by walking PyPDF annotations.
- `test_metadata_fix_classification.py` – Verifies both legacy and modern `AutoFixEngine` instances send author/subject guidance to the semi-automated bucket while keeping other metadata fixes automated.
- `test_metadata_stream_fix.py` – Confirms the metadata stream fix workflow actually removes the canonical `metadata-iso14289-1-7-1` issue and shrinks the issue list after remediation.
- `test_pdf_error_handling_pypdf.py` – Posts malformed fixtures against `/api/scan` to assert they surface clean failure responses without leaking stack traces or fabricated compliance data.
- `test_tagged_vs_untagged_detection.py` – Tests whether tagging detection toggles the analyzer between tagged/untagged paths and only emits generic heuristics when tagging markers are missing.

---

## Fixtures

Fixture PDFs live in `backend/tests/fixtures/` and are grouped by purpose:

### Alt-text fixtures

- `clean_tagged.pdf` – Baseline mostly compliant PDF; used to assert near-zero failures.
- `missing_alt.pdf` – Purposefully missing alternate text to verify WCAG 1.1.1 failures.
- `AU_sample.pdf` – Accessible University logo sample; runs only under `alt_fallback`.

### Contrast fixtures (`fixtures/contrast/`)

- `low_contrast_text.pdf` – Multiple low-contrast text runs that should deduplicate into one issue.
- `high_contrast_text.pdf` – High-contrast text ensuring the scanner remains quiet when colors are valid.
- `no_content_stream.pdf` – Lacks content streams; analyzer should emit an info-level manual review entry.

### Metadata fixtures (`fixtures/metadata/`)

- `no_title_no_lang_untagged.pdf` – Missing `/Title`, `/Lang`, and tagging metadata.
- `empty_title_tagged.pdf` – Tagged PDF with `/Lang` set but no title string.
- `invalid_title_catalog.pdf` – `/Title` is not a string; verifies robust parsing.
- `lang_only_untagged.pdf` – Has `/Lang` but no `/MarkInfo` or `/StructTreeRoot`.

### Table structure fixtures (`fixtures/tables/`)

- `tagged_tables.pdf` – Tagged tables that should not trigger redundant structure warnings.
- `untagged_tables.pdf` – Untagged tables, used to assert missing structure errors.

Each test module provides its own fixture directory helper (like `_FIXTURE_DIR`), ensuring tests run cleanly even when executed individually.

## Golden snapshots

The normalized analyzer payloads in `backend/tests/fixtures/expected/` drive the integration and PyPDF-focused tests. Check `backend/tests/fixtures/expected/README.md` for the full workflow before refreshing data.

### Refresh the canonical integration or other snapshots

Refer to [Snapshots README to update snapshots](./fixtures/expected/README.md)

## Running the Tests

### Default run (fast tests + slow PDF suites)

```bash
pytest -v
```

`pytest.ini` contains:

```markdown
addopts = -m "not alt_fallback"
```

This excludes the AU fallback regression test unless explicitly requested.

### Fast tests only

```bash
pytest -v -m "not slow_pdf"
```

### Slow PDF analyzer tests only

```bash
pytest -v -m slow_pdf
```

### AU fallback regression (disabled by default)

The fallback test in `test_alt_detection.py` is marked `@pytest.mark.alt_fallback`.
Run it by overriding the default marker filter:

```bash
pytest -v -m alt_fallback --override-ini addopts=
```

This clears the default `addopts` so the test can run on demand.

---

## Pytest Command Reference

### Run tests in a specific file

```bash
pytest -v backend/tests/test_contrast_scan_pypdf.py
```

### Run a single test function

```bash
pytest backend/tests/test_contrast_scan_pypdf.py::test_low_contrast_text_yields_single_issue
```

### Show live output (disable capture)

```bash
pytest -s
```

### Show reasons for skipped tests

```bash
pytest -rs
```

### Live output -and- skip reasons

```bash
pytest -s -rs
```

### Filter tests by keyword (test names, not markers)

```bash
pytest -k "contrast"
pytest -k "contrast and not high"
pytest backend/tests/test_contrast_scan_pypdf.py -k "low"
```

### Filter tests by marker expression

(`-m` selects tests decorated with markers like `@pytest.mark.slow_pdf`)

```bash
pytest -m slow_pdf
pytest -m "backend and not integration"
```

Tests not matching the expression are deselected.

---

## Option Details

### `-s`

- Disables output capture.
- Useful for debugging or viewing analyzer messages.

### `-rs`

- Shows reasons for skipped tests.
- Can include other letters (e.g., failures) via `-rfs`.

### `-k`

- Matches substrings in test names / node IDs.
- Does not use markers.

### `-m`

- Filters by pytest markers.
- Non-matching tests are deselected, not skipped.

---

## Test Marker Definitions

### `slow_pdf`

Marks tests that:

- Process full PDF files
- Perform multi-page analysis
- Are significantly slower than standard unit tests

Exclude:

```bash
pytest -v -m "not slow_pdf"
```

Run only slow tests:

```bash
pytest -v -m slow_pdf
```

### `alt_fallback`

Marks the Accessible University fallback regression test.

- Disabled by default via `pytest.ini` (`-m "not alt_fallback"`).
- Ensures heuristic alt-text detection remains stable when MCIDs or real alt text are missing.

Run explicitly:

```bash
pytest -v -m alt_fallback --override-ini addopts=
```

### `backend` -(optional marker)-

Logical grouping for backend tests.

Run:

```bash
pytest -v -m backend
```

Exclude:

```bash
pytest -v -m "not backend"
```

---

## Summary of Marker Usage

| Marker                 | Default Run | Purpose                            | Typical Use                                      |
| ---------------------- | ----------- | ---------------------------------- | ------------------------------------------------ |
| `slow_pdf`             | ✔ Included  | Marks expensive PDF analyzer tests | `pytest -m slow_pdf`                             |
| `alt_fallback`         | ✖ Excluded  | AU fallback regression             | `pytest -m alt_fallback --override-ini addopts=` |
| `backend` -(optional)- | ✔ Included  | Logical grouping                   | `pytest -m backend`                              |
