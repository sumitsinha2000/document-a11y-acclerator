"""
Generate snapshot JSON baselines for analyzer regression tests.

This helper targets every backend test module that exercises the PyPDF2 → pypdf
migration paths so we can refresh their golden payloads from one place.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Sequence

from backend.tests.utils.normalization import normalize_scan
from backend.tests.utils.test_entrypoints import run_scan_for_tests

ROOT = Path(__file__).resolve().parents[3]
PDF_DIR = (ROOT / "backend" / "tests" / "fixtures").resolve()
EXPECTED_DIR = (ROOT / "backend" / "tests" / "fixtures" / "expected").resolve()

PYPDF_TEST_FIXTURES = {
    # Full analyzer regression coverage (test_pdf_integration + table suites)
    "integration": [
        "clean_tagged.pdf",
        "missing_alt.pdf",
        "tables/tagged_tables.pdf",
        "tables/untagged_tables.pdf",
    ],
    # test_contrast_scan_pypdf.py
    "contrast": [
        "contrast/low_contrast_text.pdf",
        "contrast/high_contrast_text.pdf",
        "contrast/no_content_stream.pdf",
    ],
    # test_metadata_analyzer_pypdf.py
    "metadata": [
        "metadata/no_title_no_lang_untagged.pdf",
        "metadata/empty_title_tagged.pdf",
        "metadata/invalid_title_catalog.pdf",
        "metadata/lang_only_untagged.pdf",
    ],
    # test_tagged_vs_untagged_detection.py
    "tagging": [
        "tagging/well_tagged.pdf",
        "tagging/metadata_only_but_untagged.pdf",
    ],
    # test_pdf_error_handling_pypdf.py
    "error_handling": [
        "error_handling/encrypted_no_password.pdf",
        "error_handling/truncated.pdf",
    ],
    # test_link_annotation_detection.py (pypdf-based validator smoke tests)
    "link_annotations": [
        "link_annotations.pdf",
    ],
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dump normalized analyzer snapshots for PyPDF regression tests.",
    )
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=sorted(PYPDF_TEST_FIXTURES.keys()),
        help="Limit generation to specific test groups (default: all groups).",
    )
    parser.add_argument(
        "--pdf",
        nargs="+",
        metavar="PATH",
        help="Generate snapshots for additional fixture paths relative to backend/tests/fixtures.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available test groups and the fixtures they cover.",
    )
    return parser


def _list_groups() -> None:
    for name, fixtures in PYPDF_TEST_FIXTURES.items():
        print(f"{name}:")
        for fixture in fixtures:
            print(f"  - {fixture}")


def _normalize_pdf_name(name: str) -> str:
    return str(Path(name))


def _collect_targets(test_groups: Sequence[str], extra_pdfs: Sequence[str]) -> List[str]:
    ordered: List[str] = []
    seen = set()

    for group in test_groups:
        fixtures = PYPDF_TEST_FIXTURES.get(group, [])
        for fixture in fixtures:
            normalized = _normalize_pdf_name(fixture)
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(fixture)

    for pdf_name in extra_pdfs:
        normalized = _normalize_pdf_name(pdf_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(pdf_name)

    return ordered


def _ensure_relative_path(pdf_name: str) -> Path:
    relative = Path(pdf_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Fixture name must be a relative path inside backend/tests/fixtures: {pdf_name}")
    return relative


def _relative_snapshot_path(pdf_name: str) -> Path:
    relative_pdf = _ensure_relative_path(pdf_name)
    snapshot_relative = relative_pdf.with_suffix("").with_name(relative_pdf.stem + "_expected.json")
    return EXPECTED_DIR / snapshot_relative


def dump_snapshot(pdf_name: str, label: str | None = None) -> Path:
    relative_pdf = _ensure_relative_path(pdf_name)
    pdf_path = (PDF_DIR / relative_pdf).resolve()
    try:
        pdf_path.relative_to(PDF_DIR)
    except ValueError as exc:
        raise ValueError(f"Fixture {pdf_name} resolves outside {PDF_DIR}") from exc
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fixture {pdf_name} was not found at {pdf_path}")

    result = run_scan_for_tests(pdf_path)
    normalized = normalize_scan(result)

    out_path = _relative_snapshot_path(pdf_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")

    label_prefix = f"[{label}] " if label else ""
    print(f"{label_prefix}Snapshot saved to: {out_path}")
    return out_path


def generate_snapshots(test_groups: Iterable[str], extra_pdfs: Sequence[str] | None = None) -> None:
    extra = list(extra_pdfs or [])
    targets = _collect_targets(list(test_groups), extra)
    for pdf_name in targets:
        group_label = next(
            (name for name, fixtures in PYPDF_TEST_FIXTURES.items() if pdf_name in fixtures),
            None,
        )
        dump_snapshot(pdf_name, label=group_label)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.list:
        _list_groups()
        return

    selected_tests = args.tests or list(PYPDF_TEST_FIXTURES.keys())
    extra_pdfs = args.pdf or []
    if not selected_tests and not extra_pdfs:
        parser.error("No tests or fixture paths selected. Use --list to view available groups.")

    generate_snapshots(selected_tests, extra_pdfs)


if __name__ == "__main__":
    main()
