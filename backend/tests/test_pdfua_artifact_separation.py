from pathlib import Path

import pikepdf
import pytest

from backend.tests.utils.pdfua_artifact_checks import (
    collect_content_artifacts,
    count_tagged_elements,
    extract_structure_elements,
    find_artifacts_inside_structure,
    find_artifact_elements,
)


def _build_tagged_pdf(output_path: Path, *, add_structure_artifact: bool = False) -> None:
    """Create a minimal tagged PDF to exercise UA1:7.1-1 logic without pdf_generator."""
    pdf = pikepdf.Pdf.new()
    pdf.Root.Language = "en-US"
    pdf.Root.MarkInfo = pdf.make_indirect(pikepdf.Dictionary(Marked=True, Suspects=False))

    font = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name("/Font"), Subtype=pikepdf.Name("/Type1"), BaseFont=pikepdf.Name("/Helvetica"))
    )
    resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    media_box = pikepdf.Array([0, 0, 612, 792])
    page_dict = pikepdf.Dictionary(
        Type=pikepdf.Name("/Page"),
        MediaBox=media_box,
        Resources=resources,
        Contents=None,
    )
    page = pikepdf.Page(page_dict)
    pdf.pages.append(page)

    struct_tree = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/StructTreeRoot"),
            K=pikepdf.Array([]),
            ParentTree=pdf.make_indirect(pikepdf.Dictionary(Nums=pikepdf.Array([]), ParentTreeNext=1)),
            RoleMap=pdf.make_indirect(pikepdf.Dictionary()),
        )
    )
    pdf.Root.StructTreeRoot = struct_tree

    page_ref = page.obj
    document = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name("/StructElem"), S=pikepdf.Name("/Document"), K=pikepdf.Array([]), Pg=page_ref)
    )
    struct_tree.K.append(document)

    heading_mcid = 0
    para_mcid = 1

    heading = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/StructElem"),
            S=pikepdf.Name("/H1"),
            K=pikepdf.Array([pikepdf.Dictionary(Type=pikepdf.Name("/MCR"), Pg=page_ref, MCID=heading_mcid)]),
            Pg=page_ref,
            P=document,
        )
    )
    paragraph = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/StructElem"),
            S=pikepdf.Name("/P"),
            K=pikepdf.Array([pikepdf.Dictionary(Type=pikepdf.Name("/MCR"), Pg=page_ref, MCID=para_mcid)]),
            Pg=page_ref,
            P=document,
        )
    )
    document.K.extend([heading, paragraph])

    if add_structure_artifact:
        rogue_artifact = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructElem"), S=pikepdf.Name("/Artifact"), K=pikepdf.Array([]), P=document)
        )
        document.K.append(rogue_artifact)

    page.obj.StructParents = 0
    struct_tree.ParentTree.Nums = pikepdf.Array([0, pikepdf.Array([heading, paragraph])])

    content_stream = "\n".join(
        [
            "/Artifact << /Type /Layout >> BDC % Decorative header kept outside tags",
            "BT /F1 12 Tf 50 760 Td (Decorative Header) Tj ET",
            "EMC",
            "/H1 <</MCID 0>> BDC",
            "BT /F1 16 Tf 50 700 Td (Accessible Heading) Tj ET",
            "EMC",
            "/P <</MCID 1>> BDC",
            "BT /F1 12 Tf 50 660 Td (Meaningful paragraph text.) Tj ET",
            "EMC",
            "/Artifact << /Type /Pagination >> BDC",
            "BT /F1 10 Tf 300 40 Td (Page 1) Tj ET",
            "EMC",
        ]
    ).encode("utf-8")
    page.obj.Contents = pdf.make_indirect(pikepdf.Stream(pdf, content_stream))
    pdf.save(output_path)

# Fixtures ---------------------------------------------------------------------


@pytest.fixture(scope="session")
def compliant_pdf(tmp_path_factory) -> Path:
    """Generate a PDF/UA sample with artifacts outside tagged content."""
    tmp_dir = tmp_path_factory.mktemp("pdfua_artifacts")
    pdf_path = Path(tmp_dir) / "ua1_artifact_ok.pdf"
    _build_tagged_pdf(pdf_path)
    return pdf_path


@pytest.fixture(scope="session")
def noncompliant_pdf(compliant_pdf: Path, tmp_path_factory) -> Path:
    """
    Clone the compliant PDF and inject an /Artifact element inside the structure tree
    to simulate UA1:7.1-1 violation.
    """
    bad_dir = tmp_path_factory.mktemp("pdfua_artifacts_bad")
    bad_path = Path(bad_dir) / "noncompliant_artifact_in_tree.pdf"
    _build_tagged_pdf(bad_path, add_structure_artifact=True)
    return bad_path


# Tests ------------------------------------------------------------------------


def test_struct_tree_exists(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        assert "/StructTreeRoot" in pdf.Root, "PDF/UA UA1:7.1-1 violation: missing /StructTreeRoot"


def test_no_artifacts_in_structure_tree(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        elements = extract_structure_elements(pdf)
        tagged_count = count_tagged_elements(elements)
        artifacts = find_artifacts_inside_structure(elements)
        assert not artifacts, (
            f"PDF/UA UA1:7.1-1 violation: artifacts found in structure tree "
            f"(tagged elements={tagged_count}, artifacts={len(artifacts)})"
        )


def test_artifacts_not_tagged(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        elements = extract_structure_elements(pdf)
        artifacts = find_artifact_elements(elements)
        for path, elem in artifacts:
            assert "/S" not in elem and "/K" not in elem, (
                f"PDF/UA UA1:7.1-1 violation: artifact dict tagged at path {'>'.join(path)} "
                f"(object={elem.objgen})"
            )


def test_decorative_content_marked_as_artifact(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        content_data = collect_content_artifacts(pdf)
        assert content_data["artifacts"] > 0, "Expected decorative content to be marked /Artifact"
        assert {"Layout", "Pagination"} & set(content_data["artifact_types"]), (
            "Expected /Artifact to use /Type /Layout or /Pagination (PDF/UA UA1:7.1-1)"
        )


def test_tagged_content_not_marked_artifact(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        elements = extract_structure_elements(pdf)
        for path, elem in elements:
            struct_type = str(elem.get("/S") or "").lstrip("/")
            assert struct_type not in ("Artifact",), f"Tagged element mis-marked as Artifact at path {'>'.join(path)}"


def test_page_content_stream_marking(compliant_pdf: Path):
    with pikepdf.open(compliant_pdf) as pdf:
        content_data = collect_content_artifacts(pdf)
        assert not content_data["nested_in_tagged_pages"], (
            f"PDF/UA UA1:7.1-1 violation: /Artifact nested inside tagged scope on pages "
            f"{content_data['nested_in_tagged_pages']}"
        )


def test_negative_artifact_violation(noncompliant_pdf: Path):
    with pikepdf.open(noncompliant_pdf) as pdf:
        elements = extract_structure_elements(pdf)
        artifacts = find_artifacts_inside_structure(elements)
        assert artifacts, "Expected violation PDF to expose artifact elements inside structure tree"
        path_str = ">".join(artifacts[0][0])
        assert path_str, f"PDF/UA UA1:7.1-1 violation should identify structure path"
