"""YanFu - Document parsers for PDF and CAJ files.

Handles document parsing, OCR, image extraction, and formula detection.
Supports both PDF and CAJ (Chinese Academic Journal) formats.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from .utils import clean_markdown, extract_images_from_pdf, save_images_and_update_markdown


class PDFParser:
    """Parse PDF files to Markdown with image and formula extraction.

    Supports multiple parsing engines:
    - pymupdf: Fast, no OCR, good for digital PDFs
    - marker: Best quality with OCR, layout preservation
    - pdfplumber: Lightweight, good for tables
    """

    def __init__(self, engine: str = "auto", use_ocr: bool = False, langs: str = "zh,en"):
        """Initialize PDF parser.

        Args:
            engine: Parsing engine (auto, pymupdf, marker, pdfplumber).
            use_ocr: Whether to use OCR for scanned documents.
            langs: Language codes for OCR.
        """
        self.engine = engine
        self.use_ocr = use_ocr
        self.langs = langs

    def parse(self, pdf_path: str, output_dir: str | None = None) -> dict[str, Any]:
        """Parse PDF to Markdown.

        Args:
            pdf_path: Path to PDF file.
            output_dir: Directory for output files.

        Returns:
            Dictionary with markdown text, images, and metadata.
        """
        pdf_path = str(Path(pdf_path).resolve())

        if self.engine == "auto":
            self.engine = self._select_engine(pdf_path)

        if self.engine == "marker":
            return self._parse_with_marker(pdf_path, output_dir)
        elif self.engine == "pdfplumber":
            return self._parse_with_pdfplumber(pdf_path, output_dir)
        else:
            return self._parse_with_pymupdf(pdf_path, output_dir)

    def _select_engine(self, pdf_path: str) -> str:
        """Select best parsing engine based on PDF characteristics.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Engine name.
        """
        if self.use_ocr:
            if MarkerConverter.is_available():
                return "marker"
            return "pymupdf"

        if MarkerConverter.is_available():
            return "marker"

        if PyMuPDFConverter.is_available():
            return "pymupdf"

        if PDFPlumberConverter.is_available():
            return "pdfplumber"

        return "pymupdf"

    def _parse_with_pymupdf(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file.
            output_dir: Output directory.

        Returns:
            Parse result dictionary.
        """
        import fitz

        doc = fitz.open(pdf_path)
        markdown_parts = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("markdown")
            if text:
                markdown_parts.append(text)

        doc.close()

        markdown = clean_markdown("\n\n".join(markdown_parts))

        # Extract images
        images = {}
        if output_dir:
            image_dir = Path(output_dir) / "images"
            images = extract_images_from_pdf(pdf_path, str(image_dir))
            if images:
                markdown = save_images_and_update_markdown(markdown, images, output_dir)

        return {
            "markdown": markdown,
            "images": images,
            "page_count": len(fitz.open(pdf_path)),
            "engine": "pymupdf",
        }

    def _parse_with_marker(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using marker-pdf.

        Args:
            pdf_path: Path to PDF file.
            output_dir: Output directory.

        Returns:
            Parse result dictionary.
        """
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        config = {
            "output_format": "markdown",
            "languages": self.langs,
        }

        if self.use_ocr:
            config["force_ocr"] = True

        config_parser = ConfigParser(config)
        artifact_dict = create_model_dict()

        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=artifact_dict,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
        )

        rendered = converter(pdf_path)
        text, _, images = text_from_rendered(rendered)

        markdown = clean_markdown(text)

        if output_dir and images:
            markdown = save_images_and_update_markdown(markdown, images, output_dir)

        import fitz

        return {
            "markdown": markdown,
            "images": images or {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "marker",
        }

    def _parse_with_pdfplumber(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using pdfplumber.

        Args:
            pdf_path: Path to PDF file.
            output_dir: Output directory.

        Returns:
            Parse result dictionary.
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("Install pdfplumber: pip install pdfplumber")

        parts = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                tables = page.extract_tables()

                for table in tables or []:
                    if table:
                        parts.append(self._table_to_markdown(table))

                if text.strip():
                    parts.append(text.strip())

        markdown = clean_markdown("\n\n".join(parts))

        images = {}
        if output_dir:
            image_dir = Path(output_dir) / "images"
            images = extract_images_from_pdf(pdf_path, str(image_dir))
            if images:
                markdown = save_images_and_update_markdown(markdown, images, output_dir)

        import fitz

        return {
            "markdown": markdown,
            "images": images,
            "page_count": len(fitz.open(pdf_path)),
            "engine": "pdfplumber",
        }

    @staticmethod
    def _table_to_markdown(table: list[list]) -> str:
        """Convert table data to Markdown.

        Args:
            table: Table data as list of lists.

        Returns:
            Markdown table string.
        """
        if not table or not table[0]:
            return ""

        lines = []
        header = [str(c) if c else "" for c in table[0]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        for row in table[1:]:
            cells = [str(c) if c else "" for c in row]
            cells.extend([""] * (len(header) - len(cells)))
            lines.append("| " + " | ".join(cells[: len(header)]) + " |")

        return "\n".join(lines)


class CAJParser:
    """Parse CAJ (Chinese Academic Journal) files.

    CAJ is a proprietary format used by CNKI (China National Knowledge Infrastructure).
    This parser converts CAJ to PDF first, then uses PDFParser.
    """

    def __init__(self, engine: str = "auto", use_ocr: bool = False, langs: str = "zh,en"):
        """Initialize CAJ parser.

        Args:
            engine: Parsing engine for converted PDF.
            use_ocr: Whether to use OCR.
            langs: Language codes for OCR.
        """
        self.pdf_parser = PDFParser(engine=engine, use_ocr=use_ocr, langs=langs)

    def parse(self, caj_path: str, output_dir: str | None = None) -> dict[str, Any]:
        """Parse CAJ to Markdown.

        Args:
            caj_path: Path to CAJ file.
            output_dir: Output directory.

        Returns:
            Parse result dictionary.
        """
        caj_path = Path(caj_path)

        if not caj_path.exists():
            raise FileNotFoundError(f"CAJ file not found: {caj_path}")

        # Convert CAJ to PDF
        pdf_path = self._caj_to_pdf(str(caj_path), output_dir)

        try:
            # Parse the converted PDF
            result = self.pdf_parser.parse(pdf_path, output_dir)
            result["original_format"] = "caj"
            return result
        finally:
            # Clean up temporary PDF
            if Path(pdf_path).exists() and Path(pdf_path).parent.name.startswith("yanfu_caj_"):
                Path(pdf_path).unlink()

    def _caj_to_pdf(self, caj_path: str, output_dir: str | None) -> str:
        """Convert CAJ file to PDF.

        Args:
            caj_path: Path to CAJ file.
            output_dir: Output directory.

        Returns:
            Path to converted PDF file.
        """
        # Try using caj2pdf tool if available
        try:
            return self._convert_with_caj2pdf(caj_path, output_dir)
        except (ImportError, FileNotFoundError):
            pass

        # Fallback: Try to extract using PyMuPDF if CAJ is PDF-based
        try:
            return self._extract_pdf_from_caj(caj_path, output_dir)
        except Exception:
            pass

        raise NotImplementedError(
            "CAJ conversion requires caj2pdf tool.\n"
            "Install with: pip install caj2pdf\n"
            "Or convert manually using CAJViewer and save as PDF."
        )

    def _convert_with_caj2pdf(self, caj_path: str, output_dir: str | None) -> str:
        """Convert CAJ to PDF using caj2pdf library.

        Args:
            caj_path: Path to CAJ file.
            output_dir: Output directory.

        Returns:
            Path to PDF file.
        """
        import caj2pdf

        caj_path = Path(caj_path)

        if output_dir:
            pdf_path = Path(output_dir) / f"{caj_path.stem}.pdf"
        else:
            pdf_path = caj_path.with_suffix(".pdf")

        caj2pdf.convert(str(caj_path), str(pdf_path))
        return str(pdf_path)

    def _extract_pdf_from_caj(self, caj_path: str, output_dir: str | None) -> str:
        """Extract embedded PDF from CAJ file.

        Some CAJ files contain embedded PDF data.

        Args:
            caj_path: Path to CAJ file.
            output_dir: Output directory.

        Returns:
            Path to extracted PDF.
        """
        import fitz

        caj_path = Path(caj_path)

        if output_dir:
            pdf_path = Path(output_dir) / f"{caj_path.stem}.pdf"
        else:
            temp_dir = tempfile.mkdtemp(prefix="yanfu_caj_")
            pdf_path = Path(temp_dir) / f"{caj_path.stem}.pdf"

        # Try to open as PDF (some CAJ files are PDF-based)
        try:
            doc = fitz.open(caj_path)
            if doc.is_pdf:
                doc.save(str(pdf_path))
                doc.close()
                return str(pdf_path)
            doc.close()
        except Exception:
            pass

        raise ValueError(f"Cannot extract PDF from CAJ: {caj_path}")


class MarkerConverter:
    """Marker PDF converter with lazy loading."""

    _instance = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if marker is available."""
        try:
            from marker.converters.pdf import PdfConverter
            return True
        except ImportError:
            return False


class PyMuPDFConverter:
    """PyMuPDF converter availability check."""

    @staticmethod
    def is_available() -> bool:
        """Check if PyMuPDF is available."""
        try:
            import fitz
            return True
        except ImportError:
            return False


class PDFPlumberConverter:
    """PDFPlumber converter availability check."""

    @staticmethod
    def is_available() -> bool:
        """Check if pdfplumber is available."""
        try:
            import pdfplumber
            return True
        except ImportError:
            return False


def parse_document(
    file_path: str,
    engine: str = "auto",
    use_ocr: bool = False,
    langs: str = "zh,en",
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Parse a document file (PDF or CAJ) to Markdown.

    Args:
        file_path: Path to document file.
        engine: Parsing engine.
        use_ocr: Whether to use OCR.
        langs: Language codes for OCR.
        output_dir: Output directory.

    Returns:
        Parse result dictionary.
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        parser = PDFParser(engine=engine, use_ocr=use_ocr, langs=langs)
        return parser.parse(str(file_path), output_dir)
    elif suffix == ".caj":
        parser = CAJParser(engine=engine, use_ocr=use_ocr, langs=langs)
        return parser.parse(str(file_path), output_dir)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
