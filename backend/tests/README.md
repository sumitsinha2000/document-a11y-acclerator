# Backend Testing

All backend tests live under `backend/tests/` and use pytest fixtures plus PDF fixtures stored in `backend/tests/fixtures/`. There are three primary suites:

- `test_health.py` – Fast sanity check that the FastAPI health endpoint responds with a 200 status.
- `test_alt_detection.py` – Unit-tests the low-level WCAG validator helpers. Includes one `alt_fallback` scenario that only asserts the AU_sample.pdf heuristic and is intentionally skipped by default.
- `test_pdf_integration.py` – Full end-to-end analyzer runs against fixture PDFs. These are tagged `slow_pdf` because they open real documents.

## Running the tests

### Default run (fast tests + slow PDF suites)

```bash
pytest -v
```

Pytest is configured via `pytest.ini` with `addopts = -m "not alt_fallback"`, so the AU fallback test is excluded from normal runs.

### Fast tests only

```bash
pytest -v -m "not slow_pdf"
```

### Slow PDF analyzer tests only

```bash
pytest -v -m slow_pdf
```

### AU fallback regression (disabled by default)

The Accessible University fallback case lives in `test_alt_detection.py` and is marked `@pytest.mark.alt_fallback`. To execute it you need to override the default marker filter:

```bash
pytest -v -m alt_fallback --override-ini addopts=
```

This command clears the default `addopts` filter so the fallback test can run on demand.
