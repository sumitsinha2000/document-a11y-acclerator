"""Utilities for synchronizing document metadata and ensuring a PDF/UA metadata stream."""

from __future__ import annotations

from typing import Optional, Tuple

import pikepdf
from pikepdf import Dictionary, Name, Stream


def _escape_xml(value: str) -> str:
    """Return a minimally escaped XML-safe string."""
    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
    }
    escaped = str(value or "")
    for needle, replacement in replacements.items():
        escaped = escaped.replace(needle, replacement)
    return escaped


def _has_metadata_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(str(item).strip() for item in value)
    return bool(str(value).strip())


def _build_pdfua_xmp(
    title: str,
    author: Optional[str] = None,
    subject: Optional[str] = None,
    keywords: Optional[str] = None,
) -> bytes:
    """Construct a lightweight XMP packet with dc:title and PDF/UA identification."""
    escaped_title = _escape_xml(title or "Untitled Document")
    author_entry = ""
    subject_entry = ""
    keywords_entry = ""
    if author:
        author_entry = f"""    <dc:creator>
      <rdf:Seq>
        <rdf:li>{_escape_xml(author)}</rdf:li>
      </rdf:Seq>
    </dc:creator>
"""
    if subject:
        subject_entry = f"""    <dc:description>
      <rdf:Alt>
        <rdf:li xml:lang="x-default">{_escape_xml(subject)}</rdf:li>
      </rdf:Alt>
    </dc:description>
"""
    if keywords:
        keywords_entry = f"""    <pdf:Keywords>{_escape_xml(keywords)}</pdf:Keywords>
"""

    packet = f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
    xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">
    <dc:title>
      <rdf:Alt>
        <rdf:li xml:lang="x-default">{escaped_title}</rdf:li>
      </rdf:Alt>
    </dc:title>
{author_entry}{subject_entry}{keywords_entry}    <pdfuaid:part>1</pdfuaid:part>
    <pdfuaid:conformance>A</pdfuaid:conformance>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return packet.encode("utf-8")

def _write_catalog_metadata(pdf: pikepdf.Pdf, metadata_packet: bytes) -> Tuple[bool, bool]:
    """
    Attach or update the catalog /Metadata stream with the supplied XMP packet.

    Returns a tuple of (stream_updated, stream_created) to help downstream callers
    avoid double-counting changes.
    """
    stream_updated = False
    stream_created = False

    try:
        existing_ref = getattr(pdf.Root, "Metadata", None)
        existing_stream = None
        if existing_ref is not None:
            try:
                existing_stream = existing_ref.get_object()
            except Exception:
                existing_stream = existing_ref
        if isinstance(existing_stream, Stream):
            existing_stream.write(metadata_packet)
            # Ensure the stream dictionary advertises the XMP type/subtype so PDF/UA validators see it.
            sd = existing_stream.stream_dict
            if Name("/Type") not in sd:
                sd[Name("/Type")] = Name("/Metadata")
            if Name("/Subtype") not in sd:
                sd[Name("/Subtype")] = Name("/XML")
            stream_updated = True
            return stream_updated, stream_created
    except Exception:
        # Fall through to create a fresh stream
        pass

    metadata_stream = Stream(pdf, metadata_packet)
    metadata_stream.stream_dict = Dictionary(Type=Name("/Metadata"), Subtype=Name("/XML"))
    pdf.Root.Metadata = pdf.make_indirect(metadata_stream)
    stream_updated = True
    stream_created = True
    return stream_updated, stream_created


def ensure_pdfua_metadata_stream(pdf: pikepdf.Pdf, title: str) -> bool:
    """
    Ensure the PDF catalog has a /Metadata stream containing dc:title and PDF/UA markers.

    Returns True if any metadata was added or updated (DocInfo, XMP, or the catalog stream).
    """
    changed = False
    safe_title = str(title or "").strip() or "Untitled Document"
    docinfo_author = ""
    docinfo_subject = ""
    docinfo_keywords = ""

    # Make sure DocInfo exists and carries a Title.
    try:
        if not getattr(pdf, "docinfo", None):
            pdf.docinfo = pdf.make_indirect(Dictionary())
            changed = True
        current_title = str(pdf.docinfo.get("/Title", "") or "").strip()
        if not current_title:
            pdf.docinfo["/Title"] = safe_title
            changed = True
        docinfo_author = str(pdf.docinfo.get("/Author", "") or "").strip()
        docinfo_subject = str(pdf.docinfo.get("/Subject", "") or "").strip()
        docinfo_keywords = str(pdf.docinfo.get("/Keywords", "") or "").strip()
    except Exception:
        # Keep going; we'll still try to write XMP metadata.
        pass

    # Try to set dc:title and PDF/UA identifiers via XMP.
    metadata_packet: Optional[bytes] = None
    rebuilt_packet = False
    metadata_changed = False
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
            # Ensure the PDF/UA identification schema is registered so <pdfuaid:part> serializes correctly.
            try:
                meta.register_namespace("pdfuaid", "http://www.aiim.org/pdfua/ns/id/")
            except Exception:
                pass

            if not meta.get("dc:title") or not str(meta.get("dc:title")).strip():
                meta["dc:title"] = safe_title
                metadata_changed = True
            if not meta.get("pdfuaid:part"):
                meta["pdfuaid:part"] = "1"
                metadata_changed = True
            if not meta.get("pdfuaid:conformance"):
                meta["pdfuaid:conformance"] = "A"
                metadata_changed = True
            if docinfo_author and not _has_metadata_value(meta.get("dc:creator")):
                meta["dc:creator"] = [docinfo_author]
                changed = True
            if docinfo_subject and not _has_metadata_value(meta.get("dc:description")):
                meta["dc:description"] = docinfo_subject
                changed = True
            if docinfo_keywords and not _has_metadata_value(meta.get("pdf:Keywords")):
                meta["pdf:Keywords"] = docinfo_keywords
                changed = True

            try:
                metadata_packet = meta.serialize() if hasattr(meta, "serialize") else None
            except Exception:
                metadata_packet = None
    except Exception:
        metadata_packet = None

    if metadata_packet is None:
        # Build a minimal, standards-compliant packet when we cannot read/serialize existing XMP.
        metadata_packet = _build_pdfua_xmp(
                safe_title,
                docinfo_author or None,
                docinfo_subject or None,
                docinfo_keywords or None,
            )
        rebuilt_packet = True
    elif isinstance(metadata_packet, str):
        metadata_packet = metadata_packet.encode("utf-8")

    should_write_stream = metadata_changed or "/Metadata" not in pdf.Root or rebuilt_packet
    if should_write_stream and metadata_packet is not None:
        stream_written, stream_created = _write_catalog_metadata(pdf, metadata_packet)
        return changed or metadata_changed or stream_written or stream_created

    return changed or metadata_changed
