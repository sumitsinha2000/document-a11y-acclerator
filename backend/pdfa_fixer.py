import logging
import subprocess
from typing import Dict, Any, List
from pikepdf import Pdf, Name, Dictionary, Stream
import os

logger = logging.getLogger(__name__)


class PDFAFixer:
    """
    Attempts to automatically fix common PDF/A conformance issues
    detected by PDFAValidator.
    """

    def __init__(self, pdf: Pdf, issues: List[Dict[str, Any]], icc_profile_path: str = None):
        self.pdf = pdf
        self.issues = issues
        self.icc_profile_path = icc_profile_path or "/usr/share/color/icc/sRGB.icc"
        if not os.path.exists(self.icc_profile_path):
            logger.warning(f"ICC profile not found at {self.icc_profile_path}. Some fixes may fail.")

    def apply_fixes(self) -> List[Dict[str, Any]]:
        """
        Iterates through validator issues and applies corresponding fixes.
        Returns a list of successfully fixed issues.
        """
        fixed = []

        for issue in self.issues:
            message = issue.get("message", "").lower()
            try:
                if "pdf version" in message:
                    self._fix_pdf_version(issue)
                elif "outputintent" in message or "icc color profile" in message:
                    self._fix_output_intents(issue)
                elif "not embedded" in message:
                    self._fix_font_embedding(issue)
                elif "transparency" in message or "blend mode" in message:
                    self._flatten_transparency(issue)
                elif "annotation" in message:
                    self._fix_annotations(issue)
                elif "xmp metadata" in message or "pdfaid:" in message:
                    self._fix_metadata(issue)
                elif "encrypted" in message:
                    self._remove_encryption(issue)
                else:
                    issue["fixNote"] = "No automatic fix available"
                    continue

                issue["fixApplied"] = True
                fixed.append(issue)

            except Exception as e:
                issue["fixError"] = str(e)
                logger.error(f"Error fixing issue: {e}")

        logger.info(f"Total fixes applied: {len(fixed)}")
        return fixed

    # === Individual Fix Methods === #

    def _fix_pdf_version(self, issue):
        """Downgrade version to 1.4 if higher"""
        logger.info("Fixing PDF version...")
        self.pdf.pdf_version = "1.4"
        issue["fixNote"] = "PDF version downgraded to 1.4 for PDF/A-1 compatibility."

    def _fix_output_intents(self, issue):
        """Add a default sRGB OutputIntent if missing or invalid"""
        logger.info("Fixing OutputIntents...")
        try:
            with open(self.icc_profile_path, "rb") as f:
                icc_stream = Stream(self.pdf, f.read())

            intent = Dictionary({
                Name("/Type"): Name("/OutputIntent"),
                Name("/S"): Name("/GTS_PDFA1"),
                Name("/OutputConditionIdentifier"): "sRGB IEC61966-2.1",
                Name("/Info"): "sRGB IEC61966-2.1",
                Name("/DestOutputProfile"): icc_stream
            })
            self.pdf.Root.OutputIntents = [intent]
            issue["fixNote"] = "Added sRGB IEC61966-2.1 OutputIntent."
        except Exception as e:
            raise RuntimeError(f"Failed to add OutputIntent: {e}")

    def _fix_font_embedding(self, issue):
        """
        Font embedding can't be done natively in pikepdf.
        We use Ghostscript to reprocess the file with embedded fonts.
        """
        logger.info("Embedding missing fonts via Ghostscript...")
        temp_in = "temp_fontfix_input.pdf"
        temp_out = "temp_fontfix_output.pdf"
        self.pdf.save(temp_in)

        gs_command = [
            "gs",
            "-dPDFA=1",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            "-sProcessColorModel=DeviceRGB",
            "-sPDFACompatibilityPolicy=1",
            f"-sOutputFile={temp_out}",
            temp_in
        ]
        try:
            subprocess.run(gs_command, check=True)
            fixed_pdf = Pdf.open(temp_out)
            self.pdf.Root = fixed_pdf.Root
            issue["fixNote"] = "Re-embedded fonts using Ghostscript."
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Ghostscript font fix failed: {e}")
        finally:
            for f in [temp_in, temp_out]:
                if os.path.exists(f):
                    os.remove(f)

    def _flatten_transparency(self, issue):
        """
        Transparency fix using Ghostscript flattening.
        """
        logger.info("Flattening transparency...")
        temp_in = "temp_transparency_input.pdf"
        temp_out = "temp_transparency_output.pdf"
        self.pdf.save(temp_in)

        gs_command = [
            "gs",
            "-dPDFA=1",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            "-dProcessColorModel=/DeviceRGB",
            "-sOutputFile=" + temp_out,
            temp_in
        ]
        try:
            subprocess.run(gs_command, check=True)
            fixed_pdf = Pdf.open(temp_out)
            self.pdf.Root = fixed_pdf.Root
            issue["fixNote"] = "Flattened transparency using Ghostscript."
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Transparency flattening failed: {e}")
        finally:
            for f in [temp_in, temp_out]:
                if os.path.exists(f):
                    os.remove(f)

    def _fix_annotations(self, issue):
        """Remove forbidden annotations and add missing appearance streams"""
        logger.info("Fixing annotations...")
        for page in self.pdf.pages:
            if '/Annots' in page:
                new_annots = []
                for annot in page.Annots:
                    subtype = annot.get('/Subtype')
                    if subtype in [Name('/Movie'), Name('/Sound'), Name('/FileAttachment')]:
                        continue  # remove forbidden types
                    if '/AP' not in annot:
                        # add placeholder appearance
                        annot['/AP'] = Dictionary({Name('/N'): Dictionary({})})
                    new_annots.append(annot)
                page.Annots = new_annots
        issue["fixNote"] = "Removed forbidden annotation types and ensured /AP exists."

    def _fix_metadata(self, issue):
        """Add or repair minimal XMP metadata block"""
        logger.info("Fixing XMP metadata...")
        xmp = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
      <pdfaid:part>1</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
        self.pdf.Root.Metadata = Stream(self.pdf, xmp.encode("utf-8"))
        issue["fixNote"] = "Added minimal XMP metadata stream with PDF/A identifiers."

    def _remove_encryption(self, issue):
        """Remove encryption if present"""
        logger.info("Removing encryption...")
        if self.pdf.is_encrypted:
            self.pdf.remove_security()
            issue["fixNote"] = "Encryption removed from document."
