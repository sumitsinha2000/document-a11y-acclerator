import re
from typing import Dict, Iterable, List, Tuple

import pikepdf
from pikepdf import Name


def _resolve(obj):
    try:
        getter = getattr(obj, "get_object", None)
        if getter and callable(getter):
            return getter()
    except Exception:
        return obj
    return obj


def _iter_kids(value) -> Iterable:
    value = _resolve(value)
    if isinstance(value, pikepdf.Dictionary):
        if "/K" in value:
            yield from _iter_kids(value["/K"])
        elif "/S" in value:
            yield value
    elif isinstance(value, (list, pikepdf.Array)):
        for item in value:
            yield from _iter_kids(item)


def extract_structure_elements(pdf: pikepdf.Pdf) -> List[Tuple[List[str], pikepdf.Dictionary]]:
    """
    Return all structure elements and their paths.
    Used by tests enforcing PDF/UA UA1:7.1-1 (artifacts outside tagged content).
    """
    struct_tree = pdf.Root.get("/StructTreeRoot")
    if not struct_tree or "/K" not in struct_tree:
        return []

    elements: List[Tuple[List[str], pikepdf.Dictionary]] = []

    def _walk(node, path: List[str]):
        node = _resolve(node)
        if isinstance(node, (list, pikepdf.Array)):
            for child in node:
                _walk(child, path)
            return
        if isinstance(node, pikepdf.Dictionary):
            struct_type = str(node.get("/S") or "").lstrip("/")
            next_path = path + ([struct_type] if struct_type else [])
            if struct_type:
                elements.append((next_path, node))
            kids = node.get("/K")
            if kids is None:
                return
            if isinstance(kids, (list, pikepdf.Array)):
                for child in kids:
                    _walk(child, next_path)
            elif isinstance(kids, pikepdf.Dictionary):
                _walk(kids, next_path)

    _walk(struct_tree.get("/K"), [])
    return elements


def find_artifact_elements(elements: List[Tuple[List[str], pikepdf.Dictionary]]):
    """Locate structure elements that are /Artifact or typed as artifact."""
    violations = []
    for path, elem in elements:
        struct_type = str(elem.get("/S") or "").lstrip("/")
        if struct_type == "Artifact":
            violations.append((path, elem))
        if elem.get("/Type") == Name("/Artifact"):
            violations.append((path, elem))
        kids = elem.get("/K")
        if isinstance(kids, pikepdf.Dictionary) and kids.get("/Type") == Name("/Artifact"):
            violations.append((path, kids))
    return violations


def collect_content_artifacts(pdf: pikepdf.Pdf) -> Dict[str, object]:
    """
    Inspect page content streams for /Artifact BDC/BMC scopes and detect nesting
    inside tagged content (PDF/UA UA1:7.1-1 requires artifacts outside tagged scopes).
    """
    artifacts = 0
    artifact_types = set()
    nested_in_tagged_pages = set()
    tagged_scopes = {"P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "L", "LI", "Lbl", "LBody", "Table"}

    for page_index, page in enumerate(pdf.pages, start=1):
        try:
            operations = pikepdf.parse_content_stream(page)
        except Exception:
            try:
                operations = pikepdf.parse_content_stream(getattr(page, "Contents", page))
            except Exception:
                operations = []

        stack: List[str] = []
        try:
            for operands, operator in operations:
                try:
                    name = str(getattr(operator, "name", operator)).lstrip("/")
                except Exception:
                    name = ""

                if name in ("BDC", "BMC"):
                    tag = ""
                    if isinstance(operands, (list, tuple, pikepdf.Array)) and operands:
                        tag = str(operands[0]).lstrip("/")
                        if len(operands) > 1 and isinstance(operands[1], pikepdf.Dictionary):
                            artifact_type = operands[1].get("/Type")
                            if artifact_type:
                                artifact_types.add(str(artifact_type).lstrip("/"))
                    stack.append(tag)
                    if tag == "Artifact":
                        artifacts += 1
                        if any(scope not in ("Artifact", "") for scope in stack[:-1]):
                            nested_in_tagged_pages.add(page_index)
                elif name == "EMC":
                    if stack:
                        stack.pop()
        except Exception:
            # Fall back to raw stream analysis below
            pass

        # Fallback: count raw markers
        try:
            raw = bytes(getattr(page, "Contents", b""))
            artifacts = max(artifacts, raw.count(b"/Artifact"))
            for match in re.finditer(rb"/Artifact\s*<<[^>]*?/Type\s*/([A-Za-z]+)", raw):
                artifact_types.add(match.group(1).decode(errors="ignore"))
        except Exception:
            pass

    return {
        "artifacts": artifacts,
        "artifact_types": artifact_types,
        "nested_in_tagged_pages": sorted(nested_in_tagged_pages),
    }


def count_tagged_elements(elements: List[Tuple[List[str], pikepdf.Dictionary]]) -> int:
    return sum(1 for _ in elements)


def find_artifacts_inside_structure(elements: List[Tuple[List[str], pikepdf.Dictionary]]):
    """Alias kept for readability in tests."""
    return find_artifact_elements(elements)
