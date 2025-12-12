# Golden scan snapshots

## Purpose

This directory stores the normalized analyzer payloads that the integration
tests compare against to guard against regressions in the PDF analysis pipeline.
When the analyzer or the source PDFs evolve, refresh the snapshots so the tests
represent the desired behavior, and always verify the resulting diff before
committing.

## General validation

```bash
pytest
```

Run the full suite to ensure analyzer behavior remains stable after any snapshot
changes.

## Refreshing the canonical snapshots [CAREFUL]

```bash
SNAPSHOT_UPDATE=1 pytest backend/tests/test_pdf_integration.py -k snapshot
```

When only the two canonical integration snapshots need updating, this command
regenerates their `*_expected.json` files with the new analyzer output.

## Dumping snapshots for PyPDF-focused suites [CAREFUL]

```bash
python -m backend.tests.utils.dump_expected_snapshots --list
python -m backend.tests.utils.dump_expected_snapshots            # all groups
python -m backend.tests.utils.dump_expected_snapshots --tests contrast metadata
```

Use `--list` to see the available snapshot groups and repeat the module call with
the desired `--tests` argument to update a selection of suites in one pass.

In other words, use `python -m backend.tests.utils.dump_expected_snapshots --list` plus `--tests` to refresh logical groups

## Dumping snapshots for individual PDFs

```bash
python -m backend.tests.utils.dump_expected_snapshots --pdf pdfs/clean_tagged.pdf
```

This is useful when only a specific fixture needs regeneration without touching
other groups.

