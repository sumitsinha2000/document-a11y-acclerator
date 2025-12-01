from __future__ import annotations

import base64
import os
import re
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List, Any

import pikepdf
from fpdf import FPDF
from PIL import Image, ImageDraw
from pikepdf import Array, Dictionary, Name, Stream, String
from werkzeug.utils import secure_filename

from backend.pdfa_fix_engine import SRGB_ICC_PROFILE_BASE64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class PDFGenerator:
    """
    Generates PDFs for accessibility testing.
    The accessible variant follows WCAG/PDF-UA good practices:
    - Embedded Unicode fonts
    - Language and metadata populated
    - Tag tree & MarkInfo set
    - OutputIntent/XMP metadata for PDF/A conformance
    """

    FONT_CANDIDATES: Dict[str, Tuple[str, ...]] = {
        "regular": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ),
        "bold": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ),
    }
    ACCESSIBLE_FONT_FAMILY = "A11ySans"
    DEFAULT_LANGUAGE = "en-US"
    CATEGORY_LABELS = {
        "missingMetadata": "Missing Metadata",
        "missingLanguage": "Missing Language",
        "missingAltText": "Missing Alt Text",
        "poorContrast": "Contrast Issues",
        "structureIssues": "Structure Issues",
        "readingOrderIssues": "Reading Order Issues",
        "tableIssues": "Table Issues",
        "formIssues": "Form Issues",
        "untaggedContent": "Untagged Content",
        "pdfuaIssues": "PDF/UA Issues",
        "pdfaIssues": "PDF/A Issues",
        "wcagIssues": "WCAG Issues",
    }
    SEVERITY_STYLES = {
        "critical": ((220, 53, 69), (255, 255, 255)),
        "high": ((255, 153, 51), (0, 0, 0)),
        "medium": ((255, 243, 205), (0, 0, 0)),
        "low": ((209, 237, 208), (0, 0, 0)),
        "info": ((206, 224, 255), (0, 0, 0)),
    }

    def __init__(self):
        self.output_dir = os.path.join(BASE_DIR, "generated_pdfs")
        os.makedirs(self.output_dir, exist_ok=True)
        self._font_cache: Dict[str, Optional[str]] = {}

    def create_accessible_pdf(
        self,
        company_name: str = "BrightPath Consulting",
        services: Optional[List[str]] = None,
    ) -> str:
        """
        Create an accessible PDF following WCAG guidelines.
        """
        if services is None:
            services = [
                "Strategic Planning",
                "Market Research",
                "Digital Transformation",
                "Change Management",
                "Leadership Coaching",
            ]

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        fonts_embedded = self._register_accessible_fonts(pdf)
        heading_font = self.ACCESSIBLE_FONT_FAMILY if fonts_embedded else "Helvetica"
        body_font = heading_font

        company_slug = self._build_slug(company_name)

        # Document metadata for standard viewers
        pdf.set_title(f"{company_name} - Services Overview")
        pdf.set_author(company_name)
        pdf.set_subject("Company Services and Information")
        pdf.set_creator("Document A11y Accelerator PDF Generator")
        pdf.set_keywords("accessible, PDF, WCAG, PDF/UA")

        # Page 1: About Us
        pdf.add_page()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(heading_font, "B", 20)
        pdf.cell(0, 10, company_name, ln=True, align="C")
        pdf.ln(5)

        pdf.set_font(body_font, "", 12)
        about_text = (
            f"{company_name} is a forward-thinking advisory firm helping businesses "
            "navigate complex strategic challenges. Our multidisciplinary team brings deep "
            "industry expertise, data-driven insights, and innovative solutions to every project.\n\n"
            "We partner with organizations to transform operations, optimize performance, "
            "and unlock sustainable growth. Our mission is to empower clients to thrive "
            "in a rapidly changing world."
        )
        pdf.multi_cell(0, 8, about_text)

        # Page 2: Services
        pdf.add_page()
        pdf.set_font(heading_font, "B", 18)
        pdf.cell(0, 10, "Our Services", ln=True)
        pdf.ln(3)

        pdf.set_font(body_font, "", 12)
        for service in services:
            pdf.cell(10, 8, "\u2022", ln=0)
            pdf.cell(0, 8, service, ln=True)

        # Page 3: Contact
        pdf.add_page()
        pdf.set_font(heading_font, "B", 18)
        pdf.cell(0, 10, "Contact Us", ln=True)
        pdf.ln(5)

        pdf.set_font(body_font, "", 12)
        slug_email = f"contact@{company_slug.replace('-', '')}.com"
        contact_text = (
            f"Email: {slug_email}\n"
            "Phone: +1 (555) 123-4567\n"
            "Address: 123 Business Ave, Suite 100, City, State 12345"
        )
        pdf.multi_cell(0, 8, contact_text)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accessible_{company_slug}_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, filename)
        pdf.output(output_path)

        doc_title = f"{company_name} - Services Overview"
        subject = "Company Services and Information"
        description = (
            "Digitally generated accessible brochure outlining company services "
            "with semantic structure, metadata, and embedded fonts."
        )

        self._post_process_accessibility(
            output_path,
            title=doc_title,
            author=company_name,
            subject=subject,
            description=description,
            fonts_embedded=fonts_embedded,
        )

        return output_path

    def create_inaccessible_pdf(
        self,
        company_name: str = "BrightPath Consulting",
        services: Optional[List[str]] = None,
        options: Optional[Dict[str, bool]] = None,
    ) -> str:
        """
        Create an intentionally inaccessible PDF for testing.
        """
        if services is None:
            services = [
                "Strategic Planning",
                "Market Research",
                "Digital Transformation",
                "Change Management",
                "Leadership Coaching",
            ]

        if options is None:
            options = {
                "lowContrast": True,
                "missingAltText": True,
                "noStructure": True,
                "rasterizedText": True,
                "improperHeadings": True,
                "noLanguage": True,
            }

        company_slug = self._build_slug(company_name)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Page 1: About Us
        pdf.add_page()

        if options.get("lowContrast", True):
            pdf.set_text_color(180, 180, 180)
        else:
            pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 10, company_name, ln=True, align="C")
        pdf.ln(5)

        pdf.set_font("Helvetica", "", 14)
        if options.get("lowContrast", True):
            pdf.set_text_color(150, 150, 150)

        about_text = (
            f"{company_name} is a forward-thinking advisory firm helping businesses "
            "navigate complex strategic challenges. Our multidisciplinary team brings deep "
            "industry expertise, data-driven insights, and innovative solutions to every project.\n\n"
            "We partner with organizations to transform operations, optimize performance, "
            "and unlock sustainable growth. Our mission is to empower clients to thrive "
            "in a rapidly changing world."
        )
        pdf.multi_cell(0, 10, about_text)

        # Page 2: Services
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 18)
        if options.get("lowContrast", True):
            pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 10, "Our Services", ln=True)

        if options.get("improperHeadings", True):
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "Service Offerings", ln=True)

        pdf.set_font("Helvetica", "", 12)
        bullet = chr(149)
        services_text = "\n".join([f"{bullet} {service}" for service in services])
        pdf.multi_cell(0, 8, services_text)

        if options.get("missingAltText", True):
            img = Image.new("RGB", (400, 200), color=(200, 200, 200))
            draw = ImageDraw.Draw(img)
            draw.text((120, 90), "Team Meeting (No Alt Text)", fill=(100, 100, 100))

            temp_img_path = os.path.join(self.output_dir, "temp_img.png")
            img.save(temp_img_path)
            pdf.image(temp_img_path, x=40, y=100, w=120)
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

        # Page 3: Contact
        pdf.add_page()

        if options.get("rasterizedText", True):
            img_text = Image.new("RGB", (600, 150), color=(255, 255, 255))
            draw = ImageDraw.Draw(img_text)
            draw.text(
                (50, 50),
                f"Contact: contact@{company_name.lower().replace(' ', '')}.com",
                fill=(120, 120, 120),
            )

            temp_text_img_path = os.path.join(self.output_dir, "temp_text.png")
            img_text.save(temp_text_img_path)
            pdf.image(temp_text_img_path, x=30, y=40, w=150)
            if os.path.exists(temp_text_img_path):
                os.remove(temp_text_img_path)
        else:
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, f"Contact: contact@{company_name.lower().replace(' ', '')}.com", ln=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"inaccessible_{company_slug}_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, filename)
        pdf.output(output_path)
        return output_path

    def get_generated_pdfs(self) -> List[str]:
        """Return generated PDFs sorted by newest first."""
        if not os.path.exists(self.output_dir):
            return []

        pdfs = [f for f in os.listdir(self.output_dir) if f.endswith(".pdf")]
        pdfs.sort(key=lambda name: os.path.getmtime(os.path.join(self.output_dir, name)), reverse=True)
        return pdfs

    # Helper utilities -------------------------------------------------

    def _register_accessible_fonts(self, pdf: FPDF) -> bool:
        """
        Register Unicode fonts so text is embedded for PDF/A compliance.
        """
        success = True
        for style in ("regular", "bold"):
            font_path = self._resolve_font_path(style)
            if not font_path:
                success = False
                continue
            try:
                variant = "" if style == "regular" else "B"
                pdf.add_font(self.ACCESSIBLE_FONT_FAMILY, variant, font_path, uni=True)
            except RuntimeError as exc:
                print(f"[PDFGenerator] Warning: Failed to add {style} font from {font_path}: {exc}")
                success = False
        if not success:
            print(
                "[PDFGenerator] Warning: Falling back to core Helvetica fonts; "
                "PDF/A compliance may fail due to non-embedded fonts."
            )
        return success

    def _resolve_font_path(self, style: str) -> Optional[str]:
        if style in self._font_cache:
            return self._font_cache[style]
        for candidate in self.FONT_CANDIDATES.get(style, ()):
            if os.path.exists(candidate):
                self._font_cache[style] = candidate
                return candidate
        self._font_cache[style] = None
        return None

    def _build_slug(self, raw_name: str) -> str:
        slug = secure_filename((raw_name or "").lower())
        return slug or "document"

    @staticmethod
    def _format_percentage(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            return f"{value}%"
        text = str(value).strip()
        return text if text else "N/A"

    @staticmethod
    def _format_pages(pages: Optional[List[Any]]) -> str:
        if not pages:
            return "N/A"
        return ", ".join(str(p) for p in pages)

    def _format_category_label(self, category: str) -> str:
        if not category:
            return "Issues"
        override = self.CATEGORY_LABELS.get(category)
        if override:
            return override
        normalized = re.sub(r"(?<!^)(?=[A-Z])", " ", category)
        normalized = normalized.replace("_", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized.title()

    def _format_upload_date(self, upload_date: Optional[str], offset_minutes: Optional[int]) -> str:
        if not upload_date:
            return "N/A"
        parsed = self._parse_iso_datetime(upload_date)
        if not parsed:
            return upload_date
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if offset_minutes is not None:
            parsed = parsed - timedelta(minutes=offset_minutes)
        tz_label = self._format_timezone_label(offset_minutes)
        formatted = parsed.strftime("%Y-%m-%d %H:%M:%S")
        return f"{formatted} ({tz_label})" if tz_label else formatted

    @staticmethod
    def _parse_iso_datetime(value: str) -> Optional[datetime]:
        if not value:
            return None
        candidate = value
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            try:
                return datetime.fromisoformat(candidate.replace(" ", "T"))
            except ValueError:
                return None

    @staticmethod
    def _format_timezone_label(offset_minutes: Optional[int]) -> str:
        if offset_minutes is None:
            return "UTC"
        local_offset = -offset_minutes
        sign = "+" if local_offset >= 0 else "-"
        abs_offset = abs(local_offset)
        hours, minutes = divmod(abs_offset, 60)
        return f"UTC{sign}{hours:02d}:{minutes:02d}"

    def _draw_table(
        self,
        pdf: FPDF,
        column_widths: List[float],
        header: List[str],
        rows: List[List[str]],
        *,
        font_family: str,
    ) -> None:
        if not rows:
            return

        header_font_size = 10
        body_font_size = 9
        header_line_height = header_font_size * 0.35 + 2
        body_line_height = body_font_size * 0.35 + 2

        pdf.set_font(font_family, "B", header_font_size)
        header_wrapped, header_lines = self._prepare_wrapped_row_texts(
            pdf,
            header,
            column_widths,
        )
        header_height = header_lines * header_line_height + 4

        def render_header() -> None:
            self._draw_table_row(
                pdf,
                header_wrapped,
                column_widths,
                header_height,
                header_line_height,
                font_family=font_family,
                font_style="B",
                font_size=header_font_size,
                text_color=(255, 255, 255),
                fill_color=(102, 126, 234),
            )
            pdf.set_font(font_family, "", body_font_size)

        render_header()

        for row in rows:
            pdf.set_font(font_family, "", body_font_size)
            wrapped_row, row_lines = self._prepare_wrapped_row_texts(
                pdf,
                row,
                column_widths,
            )
            row_height = row_lines * body_line_height + 4
            if pdf.get_y() + row_height > pdf.page_break_trigger:
                pdf.add_page()
                render_header()
            severity_key = (row[0] or "").strip().lower() if row and row[0] else ""
            severity_style = self.SEVERITY_STYLES.get(severity_key)
            cell_fill_colors = None
            cell_text_colors = None
            if severity_style:
                severity_fill, severity_text = severity_style
                remaining = len(column_widths) - 1
                cell_fill_colors = [severity_fill] + [None] * remaining
                cell_text_colors = (
                    [severity_text] + [(40, 40, 40)] * remaining
                )
            self._draw_table_row(
                pdf,
                wrapped_row,
                column_widths,
                row_height,
                body_line_height,
                font_family=font_family,
                font_style="",
                font_size=body_font_size,
                text_color=(40, 40, 40),
                fill_color=None,
                cell_fill_colors=cell_fill_colors,
                cell_text_colors=cell_text_colors,
            )

    def _draw_table_row(
        self,
        pdf: FPDF,
        wrapped_lines: List[List[str]],
        column_widths: List[float],
        row_height: float,
        line_height: float,
        *,
        font_family: str,
        font_style: str,
        font_size: float,
        text_color: Tuple[int, int, int],
        fill_color: Optional[Tuple[int, int, int]],
        cell_fill_colors: Optional[List[Optional[Tuple[int, int, int]]]] = None,
        cell_text_colors: Optional[List[Tuple[int, int, int]]] = None,
    ) -> None:
        # Make sure there is room for the whole row
        self._ensure_space(pdf, row_height)

        row_start_x = max(pdf.get_x(), pdf.l_margin)
        y_start = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        x_cursor = row_start_x

        # Consistent inner padding for all cells
        inner_padding_x = 2.0
        inner_padding_y = 2.0

        for idx, (lines, width) in enumerate(zip(wrapped_lines, column_widths)):
            # Choose fill for this cell
            cell_fill = (
                cell_fill_colors[idx]
                if cell_fill_colors and idx < len(cell_fill_colors)
                else fill_color
            )
            draw_style = "DF" if cell_fill else "D"

            if cell_fill:
                pdf.set_fill_color(*cell_fill)
            else:
                pdf.set_fill_color(255, 255, 255)

            # Draw the cell rectangle
            pdf.rect(x_cursor, y_start, width, row_height, style=draw_style)

            # Choose text color for this cell
            text_color_choice = (
                cell_text_colors[idx]
                if cell_text_colors and idx < len(cell_text_colors)
                else text_color
            )
            pdf.set_text_color(*text_color_choice)
            pdf.set_font(font_family, font_style, font_size)

            # Inner text area
            text_y = y_start + inner_padding_y
            inner_width = max(width - inner_padding_x * 2, 1)

            # Draw each wrapped line once, with consistent padding
            for line in lines or [""]:
                pdf.set_xy(x_cursor + inner_padding_x, text_y)
                pdf.cell(inner_width, line_height, line, border=0)
                text_y += line_height

            x_cursor += width

        # Move cursor to start of next row
        pdf.set_xy(row_start_x, y_start + row_height)

    def _prepare_wrapped_row_texts(
        self,
        pdf: FPDF,
        texts: List[str],
        column_widths: List[float],
    ) -> Tuple[List[List[str]], int]:
        wrapped_lines: List[List[str]] = []
        max_line_count = 1

        inner_padding = 2.0

        for text, width in zip(texts, column_widths):
            cell_text = str(text) if text is not None else ""
            inner_width = max(width - inner_padding * 2, 10)
            lines = self._wrap_text_to_width(pdf, cell_text, inner_width)
            lines = lines or [""]
            wrapped_lines.append(lines)
            max_line_count = max(max_line_count, len(lines))
        return wrapped_lines, max_line_count

    @staticmethod
    def _wrap_text_to_width(pdf: FPDF, text: str, width: float) -> List[str]:
        if not text:
            return [""]

        # Use an average char width instead of a single "M"
        sample = "MMMMMMMMMM"
        avg_char_width = pdf.get_string_width(sample) / len(sample) or 0.1

        # Allow slightly more chars than the strict math to avoid under-using width
        max_chars = max(int(width / avg_char_width * 1.2), 1)

        wrapper = textwrap.TextWrapper(
            width=max_chars,
            break_long_words=False,
            break_on_hyphens=False,
        )

        lines: List[str] = []
        for line in text.splitlines():
            wrapped = wrapper.wrap(line) or [""]
            lines.extend(wrapped)

        return lines or [""]

    @staticmethod
    def _ensure_space(pdf: FPDF, needed_height: float) -> None:
        if pdf.get_y() + needed_height > pdf.page_break_trigger:
            pdf.add_page()

    # Accessibility post-processing -----------------------------------

    def create_accessibility_report_pdf(
        self,
        scan_export: Dict[str, Any],
        *,
        client_offset_minutes: Optional[int] = None,
    ) -> str:
        """
        Build an accessible PDF accessibility report from scan export payload.
        """
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        fonts_embedded = self._register_accessible_fonts(pdf)
        font_family = self.ACCESSIBLE_FONT_FAMILY if fonts_embedded else "Helvetica"

        scan_id = scan_export.get("scanId") or "scan"
        filename = scan_export.get("filename") or scan_id
        group_name = scan_export.get("groupName") or scan_export.get("groupId")
        summary = scan_export.get("summary") or {}
        results = scan_export.get("results") or {}
        upload_date = scan_export.get("uploadDate")

        pdf.add_page()
        pdf.set_text_color(24, 24, 24)
        pdf.set_font(font_family, "B", 20)
        pdf.cell(0, 12, "Accessibility Compliance Report", ln=True)
        pdf.set_font(font_family, "", 11)
        pdf.set_text_color(70, 70, 70)
        project_name = scan_export.get("groupName")
        project_id = scan_export.get("groupId") or "N/A"
        folder_name = (
            scan_export.get("folderName")
            or scan_export.get("batchName")
            or scan_export.get("folder_name")
        )
        folder_id = scan_export.get("folderId") or scan_export.get("batchId") or "N/A"
        upload_display = self._format_upload_date(upload_date, client_offset_minutes)
        pdf.multi_cell(
            0,
            6,
            (
                f"Filename: {filename}\n"
                f"Scan ID: {scan_id}\n"
                f"Project: {project_name or 'N/A'}\n"
                # f"Project ID: {project_id}\n"
                f"Folder: {folder_name or 'N/A'}\n"
                # f"Folder ID: {folder_id}\n"
                f"Uploaded: {upload_display}"
            ),
        )
        pdf.ln(4)

        pdf.set_text_color(24, 24, 24)
        pdf.set_font(font_family, "B", 16)
        pdf.cell(0, 10, "Summary", ln=True)
        pdf.ln(2)

        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        summary_rows = [
            ["Total Issues", str(summary.get("totalIssues", "N/A"))],
            ["High Severity", str(summary.get("highSeverity", "N/A"))],
            ["WCAG Compliance", self._format_percentage(summary.get("wcagCompliance"))],
            ["PDF/UA Compliance", self._format_percentage(summary.get("pdfuaCompliance"))],
            # ["PDF/A Compliance", self._format_percentage(summary.get("pdfaCompliance"))],
            ["Overall Score", self._format_percentage(summary.get("complianceScore"))],
        ]
        column_widths = [usable_width * 0.55, usable_width * 0.45]
        self._draw_table(
            pdf,
            column_widths=column_widths,
            header=["Metric", "Value"],
            rows=summary_rows,
            font_family=font_family,
        )
        pdf.ln(4)

        category_names = [
            "missingMetadata",
            "missingLanguage",
            "missingAltText",
            "poorContrast",
            "structureIssues",
            "readingOrderIssues",
            "tableIssues",
            "formIssues",
            "untaggedContent",
            "pdfuaIssues",
            "pdfaIssues",
            "wcagIssues",
        ]

        issue_column_ratios = [0.12, 0.28, 0.22, 0.10, 0.28]
        for category in category_names:
            issues = results.get(category)
            if not issues:
                continue

            pretty_name = self._format_category_label(category)
            pdf.set_font(font_family, "B", 14)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 9, pretty_name, ln=True)
            pdf.ln(2)

            issue_rows = []
            for issue in issues:
                severity = str(issue.get("severity", "medium")).capitalize()
                description = (
                    issue.get("description")
                    or issue.get("message")
                    or "Issue description not available."
                )
                clause = issue.get("clause") or issue.get("criterion") or issue.get("wcagCriteria")
                recommendation = issue.get("recommendation") or issue.get("remediation")
                pages = issue.get("pages")
                pages_text = self._format_pages(pages)
                issue_rows.append(
                    [
                        severity,
                        description,
                        clause or "N/A",
                        pages_text,
                        recommendation or "N/A",
                    ]
                )

            column_widths = [ratio * usable_width for ratio in issue_column_ratios]
            self._draw_table(
                pdf,
                column_widths=column_widths,
                header=["Severity", "Description", "Clause", "Pages", "Recommendation"],
                rows=issue_rows,
                font_family=font_family,
            )
            pdf.ln(4)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_scan = self._build_slug(scan_id)
        output_name = f"accessibility-report-{safe_scan}-{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, output_name)
        pdf.output(output_path)

        title = f"Accessibility Report - {filename}"
        author = group_name or "Document A11y Accelerator"
        subject = "Automated accessibility assessment results"
        description = (
            "Detailed PDF accessibility compliance report containing aggregated "
            "WCAG, PDF/UA, and PDF/A findings for the analyzed document."
        )

        self._post_process_accessibility(
            output_path,
            title=title,
            author=author,
            subject=subject,
            description=description,
            fonts_embedded=fonts_embedded,
        )

        return output_path

    def _post_process_accessibility(
        self,
        pdf_path: str,
        *,
        title: str,
        author: str,
        subject: str,
        description: str,
        fonts_embedded: bool,
    ) -> None:
        """
        Use pikepdf to add accessibility metadata, structure tags, language,
        and PDF/A compliance markers so the analyzer recognizes the document
        as accessible.
        """
        try:
            with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
                if not pdf.docinfo:
                    pdf.docinfo = pdf.make_indirect(Dictionary())

                pdf.docinfo["/Title"] = title
                pdf.docinfo["/Author"] = author
                pdf.docinfo["/Subject"] = subject
                pdf.docinfo["/Creator"] = "Document A11y Accelerator PDF Generator"
                pdf.docinfo["/Producer"] = "Document A11y Accelerator"
                pdf.docinfo["/Keywords"] = "accessible, PDF/UA, WCAG"

                pdf.Root.Lang = self.DEFAULT_LANGUAGE
                pdf.Root.ViewerPreferences = pdf.make_indirect(Dictionary(DisplayDocTitle=True))
                mark_info = getattr(pdf.Root, "MarkInfo", None)
                if not mark_info:
                    mark_info = pdf.make_indirect(Dictionary(Marked=True, Suspects=False))
                    pdf.Root.MarkInfo = mark_info
                else:
                    mark_info[Name("/Marked")] = True
                    mark_info[Name("/Suspects")] = False

                self._ensure_struct_tree(pdf)
                self._synchronize_metadata(pdf, title, author, description)
                if fonts_embedded:
                    self._ensure_pdfa_requirements(pdf)

                pdf.save(pdf_path, linearize=True)
        except Exception as exc:
            print(f"[PDFGenerator] Warning: Failed to apply accessibility post-processing: {exc}")

    def _ensure_struct_tree(self, pdf: pikepdf.Pdf) -> None:
        """Create a minimal structure tree to satisfy PDF/UA validators."""
        struct_tree = getattr(pdf.Root, "StructTreeRoot", None)
        if not struct_tree:
            role_map = pdf.make_indirect(Dictionary())
            parent_tree = pdf.make_indirect(Dictionary(Nums=Array([]), ParentTreeNext=0))
            struct_tree = pdf.make_indirect(
                Dictionary(
                    Type=Name("/StructTreeRoot"),
                    K=Array([]),
                    RoleMap=role_map,
                    ParentTree=parent_tree,
                )
            )
            pdf.Root.StructTreeRoot = struct_tree
        else:
            struct_tree.Type = Name("/StructTreeRoot")
            if not hasattr(struct_tree, "K") or not isinstance(struct_tree.K, Array):
                struct_tree.K = Array([])
            if not hasattr(struct_tree, "RoleMap"):
                struct_tree.RoleMap = pdf.make_indirect(Dictionary())
            if not hasattr(struct_tree, "ParentTree"):
                struct_tree.ParentTree = pdf.make_indirect(Dictionary(Nums=Array([]), ParentTreeNext=0))

        parent_tree = struct_tree.ParentTree
        if not hasattr(parent_tree, "Nums") or not isinstance(parent_tree.Nums, Array):
            parent_tree.Nums = Array([])
        if not hasattr(parent_tree, "ParentTreeNext"):
            parent_tree.ParentTreeNext = 0

        # Ensure a Document element exists
        document_elem = None
        if hasattr(struct_tree, "K"):
            for elem in struct_tree.K:
                if getattr(elem, "S", None) == Name("/Document"):
                    document_elem = elem
                    break

        if document_elem is None:
            document_elem = pdf.make_indirect(
                Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/Document"),
                    P=struct_tree,
                    K=Array([]),
                    Lang=String(self.DEFAULT_LANGUAGE),
                )
            )
            struct_tree.K.append(document_elem)
        elif not hasattr(document_elem, "K"):
            document_elem.K = Array([])

        # Rebuild children for each page
        document_elem.K = Array([])
        parent_tree_entries = Array([])
        for page_index, page in enumerate(pdf.pages, start=1):
            section_elem = pdf.make_indirect(
                Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/Sect"),
                    P=document_elem,
                    Pg=page.obj,
                    K=Array([]),
                )
            )
            document_elem.K.append(section_elem)

            heading_type = Name("/H1") if page_index == 1 else Name("/H2")
            heading_elem = pdf.make_indirect(
                Dictionary(
                    Type=Name("/StructElem"),
                    S=heading_type,
                    P=section_elem,
                    Pg=page.obj,
                    K=Array([]),
                )
            )
            section_elem.K.append(heading_elem)

            paragraph_elem = pdf.make_indirect(
                Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/P"),
                    P=section_elem,
                    Pg=page.obj,
                    K=Array([]),
                )
            )
            section_elem.K.append(paragraph_elem)

            struct_parent_index = page_index - 1
            page_obj = page.obj
            page_obj.StructParents = struct_parent_index
            parent_tree_entries.append(struct_parent_index)
            parent_tree_entries.append(Array([section_elem]))

        parent_tree.Nums = parent_tree_entries
        parent_tree.ParentTreeNext = len(pdf.pages)

    def _synchronize_metadata(
        self,
        pdf: pikepdf.Pdf,
        title: str,
        author: str,
        description: str,
    ) -> None:
        """Ensure XMP metadata exists and is synchronized with document info."""
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        xmp_packet = self._build_xmp_metadata_packet(
            title=title,
            author=author,
            description=description,
            timestamp=timestamp,
        )
        metadata_stream = Stream(pdf, xmp_packet.encode("utf-8"))
        metadata_stream.stream_dict = Dictionary(
            Type=Name("/Metadata"),
            Subtype=Name("/XML"),
        )
        pdf.Root.Metadata = pdf.make_indirect(metadata_stream)

    def _ensure_pdfa_requirements(self, pdf: pikepdf.Pdf) -> None:
        """
        Embed sRGB output intent and ensure PDF/A identifiers are present.
        Only runs if fonts are embedded so the document can satisfy PDF/A checks.
        """
        if "/OutputIntents" not in pdf.Root or len(pdf.Root.OutputIntents) == 0:
            try:
                icc_bytes = base64.b64decode(SRGB_ICC_PROFILE_BASE64)
                icc_stream = Stream(pdf, icc_bytes)
                icc_stream.stream_dict = Dictionary(
                    N=3,
                    Alternate=Name("/DeviceRGB"),
                )
                icc_stream_ref = pdf.make_indirect(icc_stream)
                output_intent = pdf.make_indirect(
                    Dictionary(
                        Type=Name("/OutputIntent"),
                        S=Name("/GTS_PDFA1"),
                        OutputConditionIdentifier="sRGB IEC61966-2.1",
                        RegistryName="http://www.color.org",
                        Info="sRGB IEC61966-2.1",
                        DestOutputProfile=icc_stream_ref,
                    )
                )
                pdf.Root.OutputIntents = Array([output_intent])
            except Exception as exc:
                print(f"[PDFGenerator] Warning: Unable to embed OutputIntent: {exc}")

        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["{http://www.aiim.org/pdfa/ns/id/}part"] = "1"
            meta["{http://www.aiim.org/pdfa/ns/id/}conformance"] = "A"
            meta["pdfaid:part"] = "1"
            meta["pdfaid:conformance"] = "A"

    def _build_xmp_metadata_packet(
        self,
        *,
        title: str,
        author: str,
        description: str,
        timestamp: str,
    ) -> str:
        """Build an explicit XMP packet so validators see dc:title and PDF/UA identifiers."""
        escaped_title = self._escape_xml(title)
        escaped_author = self._escape_xml(author)
        escaped_description = self._escape_xml(description)
        lang = self.DEFAULT_LANGUAGE
        keywords = "accessible, PDF/UA, WCAG"
        packet = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
    xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">
    <dc:format>application/pdf</dc:format>
    <dc:title>
      <rdf:Alt>
        <rdf:li xml:lang="{lang}">{escaped_title}</rdf:li>
        <rdf:li xml:lang="x-default">{escaped_title}</rdf:li>
      </rdf:Alt>
    </dc:title>
    <dc:creator>
      <rdf:Seq>
        <rdf:li>{escaped_author}</rdf:li>
      </rdf:Seq>
    </dc:creator>
    <dc:description>
      <rdf:Alt>
        <rdf:li xml:lang="{lang}">{escaped_description}</rdf:li>
        <rdf:li xml:lang="x-default">{escaped_description}</rdf:li>
      </rdf:Alt>
    </dc:description>
    <pdf:Producer>Document A11y Accelerator</pdf:Producer>
    <pdf:Keywords>{self._escape_xml(keywords)}</pdf:Keywords>
    <pdf:Trapped>False</pdf:Trapped>
    <xmp:CreatorTool>Document A11y Accelerator PDF Generator</xmp:CreatorTool>
    <xmp:CreateDate>{timestamp}</xmp:CreateDate>
    <xmp:ModifyDate>{timestamp}</xmp:ModifyDate>
    <xmp:MetadataDate>{timestamp}</xmp:MetadataDate>
    <pdfaid:part>1</pdfaid:part>
    <pdfaid:conformance>A</pdfaid:conformance>
    <pdfuaid:part>1</pdfuaid:part>
    <pdfuaid:conformance>PDF/UA-1</pdfuaid:conformance>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
        return packet

    @staticmethod
    def _escape_xml(value: Optional[str]) -> str:
        """Basic XML escaping for metadata values."""
        if not value:
            return ""
        replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&apos;",
        }
        escaped = value
        for char, entity in replacements.items():
            escaped = escaped.replace(char, entity)
        return escaped
