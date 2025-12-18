from pathlib import Path

import pytest
import pikepdf

from backend.pdf_analyzer import PDFAccessibilityAnalyzer


def _build_rolemap_pdf(tmp_path: Path, filename: str, rolemap: dict) -> Path:
    """Create a minimal tagged PDF with a provided RoleMap."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(300, 300))

    pdf.Root.MarkInfo = pdf.make_indirect(pikepdf.Dictionary(Marked=True))
    struct_tree = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/StructTreeRoot"),
                "/K": pdf.make_indirect(pikepdf.Array()),
            }
        )
    )
    struct_tree.RoleMap = pdf.make_indirect(pikepdf.Dictionary(rolemap))
    pdf.Root.StructTreeRoot = struct_tree

    output = tmp_path / filename
    pdf.save(output)
    return output


class TestPdfUaRoleMapStandardRemap:
    """PDF/UA Rule 02-004: standard structure types must not be remapped."""

    def _scan(self, path: Path) -> dict:
        return PDFAccessibilityAnalyzer().analyze(str(path))

    @pytest.mark.parametrize(
        "rolemap_entry",
        [
            ("/P", "/Span"),
            ("/H1", "/P"),
            ("/Span", "/P"),
        ],
    )
    def test_standard_type_remap_fails(self, tmp_path, rolemap_entry):
        """Standard tags remapped to any type should trigger 02-004."""
        src, target = rolemap_entry
        pdf_path = _build_rolemap_pdf(tmp_path, "rolemap_standard_remap_fail.pdf", {src: target})

        results = self._scan(pdf_path)
        issues = results.get("pdfuaIssues") or []
        remap_issue = next(
            (issue for issue in issues if issue.get("findingId") == "pdfua.rolemap.standard_remap"),
            None,
        )

        assert remap_issue is not None, "Expected standard RoleMap remap finding (02-004)"
        assert remap_issue.get("matterhornId") == "02-004"
        details = remap_issue.get("details") or ""
        assert src in details and target in details, "Finding should describe offending mapping"
        offending = remap_issue.get("offendingMappings") or []
        mapping_pairs = {(entry.get("from"), entry.get("to")) for entry in offending}
        assert (src, target) in mapping_pairs
        paths = {entry.get("objectPath") for entry in offending}
        assert any(str(src).lstrip("/") in path for path in paths), "Object path should reference StructTreeRoot.RoleMap"

    def test_custom_to_standard_passes(self, tmp_path):
        """Custom tags mapped to standard types should pass rule 02-004."""
        pdf_path = _build_rolemap_pdf(
            tmp_path,
            "rolemap_custom_map_pass.pdf",
            {"/MyPara": "/P", "/MySpan": "/Span"},
        )

        results = self._scan(pdf_path)
        issues = results.get("pdfuaIssues") or []
        remap_issue = next(
            (issue for issue in issues if issue.get("findingId") == "pdfua.rolemap.standard_remap"),
            None,
        )

        assert remap_issue is None, "Custom -> standard mappings should not trigger 02-004"
        assert results.get("analysisErrors") in (None, [], {}), "Scan should succeed without errors"

    def test_empty_rolemap_passes(self, tmp_path):
        """Empty RoleMap dictionary should not trigger 02-004."""
        pdf_path = _build_rolemap_pdf(tmp_path, "rolemap_empty_rolemap_pass.pdf", {})

        results = self._scan(pdf_path)
        issues = results.get("pdfuaIssues") or []
        assert not any(issue.get("matterhornId") == "02-004" for issue in issues)

    def test_mixed_rolemap_reports_only_standard_entries(self, tmp_path):
        """Mixed RoleMap should report only illegal standard remaps."""
        pdf_path = _build_rolemap_pdf(
            tmp_path,
            "rolemap_mixed_fail.pdf",
            {"/MyPara": "/P", "/P": "/Span", "/CustomSpan": "/Span"},
        )

        results = self._scan(pdf_path)
        issues = results.get("pdfuaIssues") or []
        remap_issue = next(
            (issue for issue in issues if issue.get("findingId") == "pdfua.rolemap.standard_remap"),
            None,
        )

        assert remap_issue is not None, "Standard remap should be reported when mixed with valid entries"
        offending = remap_issue.get("offendingMappings") or []
        pairs = {(entry.get("from"), entry.get("to")) for entry in offending}
        assert pairs == {("/P", "/Span")}, "Only standard entries should be flagged"
        paths = {entry.get("objectPath") for entry in offending}
        assert "StructTreeRoot.RoleMap.P" in paths
