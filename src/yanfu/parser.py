"""YanFu - Document parsers for PDF and CAJ files.

Handles document parsing with multiple engines.
Supports PDF and CAJ (Chinese Academic Journal) formats.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .utils import clean_markdown, extract_images_from_pdf, save_images_and_update_markdown

logger = logging.getLogger("yanfu")


class EngineInfo:
    """Information about a parsing engine."""
    def __init__(self, name: str, display_name: str, pip_package: str,
                 model_size: str = "None", needs_gpu: bool = False,
                 has_ocr: bool = False, specialty: str = ""):
        self.name = name
        self.display_name = display_name
        self.pip_package = pip_package
        self.model_size = model_size
        self.needs_gpu = needs_gpu
        self.has_ocr = has_ocr
        self.specialty = specialty

# Registry of all supported engines
ENGINES = {
    "auto": EngineInfo("auto", "Auto (Best Available)", "", "", False, False, "Auto-selects best engine"),
    "pymupdf": EngineInfo("pymupdf", "PyMuPDF", "pymupdf4llm", "None", False, False, "Fastest, digital PDFs"),
    "pdfplumber": EngineInfo("pdfplumber", "PDFPlumber", "pdfplumber", "None", False, False, "Tables, lightweight"),
    "marker": EngineInfo("marker", "Marker (Layout + OCR)", "marker-pdf", "~3GB", True, True, "Best overall quality"),
    "docling": EngineInfo("docling", "Docling (IBM)", "docling", "~1.5GB", False, True, "Balanced quality/speed"),
    "mineru": EngineInfo("mineru", "MinerU (Chinese)", "magic-pdf[full]", "~1.5GB", False, True, "Chinese documents"),
    "easyocr": EngineInfo("easyocr", "EasyOCR", "easyocr", "~300MB", False, True, "80+ languages"),
    "doctr": EngineInfo("doctr", "DocTR", "doctr", "~500MB", False, True, "Lightweight OCR"),
    "nougat": EngineInfo("nougat", "Nougat (Academic)", "nougat-ocr", "~1.5GB", True, True, "Academic papers"),
    "surya-lite": EngineInfo("surya-lite", "Surya Lite OCR", "surya-ocr", "~2GB", False, True, "Surya-only OCR"),
    "llamaparse": EngineInfo("llamaparse", "LlamaParse (Cloud)", "llama-parse", "Cloud", False, True, "Excellent quality (API key)"),
    "mathpix": EngineInfo("mathpix", "Mathpix (Cloud)", "requests", "Cloud", False, True, "Math/STEM (API key)"),
    "mineru-cloud": EngineInfo("mineru-cloud", "MinerU Cloud", "requests", "Cloud", False, True, "Chinese docs (API key)"),
    "doc2x": EngineInfo("doc2x", "Doc2X (Cloud)", "requests", "Cloud", False, True, "Formulas/LaTeX (API key)"),
}


class PDFParser:
    """Parse PDF files to Markdown with image and formula extraction.

    Supports multiple parsing engines.
    """

    def __init__(self, engine: str = "auto", use_ocr: bool = False, langs: str = "zh,en", device: str = "auto"):
        """Initialize PDF parser.

        Args:
            engine: Parsing engine (auto, pymupdf, marker, pdfplumber, docling, etc.).
            use_ocr: Whether to use OCR for scanned documents.
            langs: Language codes for OCR.
            device: Device for ML engines (auto/cpu/cuda/mps/dml).
        """
        self.engine = engine
        self.use_ocr = use_ocr
        self.langs = langs
        self.device = device

    @staticmethod
    def list_available_engines() -> list[dict]:
        """List all engines with their availability status.

        Returns:
            List of dicts with engine info.
        """
        results = []
        for name, info in ENGINES.items():
            available, reason = PDFParser._check_engine_available(name)
            results.append({
                "name": name,
                "display_name": info.display_name,
                "pip_package": info.pip_package,
                "model_size": info.model_size,
                "needs_gpu": info.needs_gpu,
                "has_ocr": info.has_ocr,
                "specialty": info.specialty,
                "available": available,
                "reason": reason,
            })
        return results

    @staticmethod
    def _check_engine_available(engine: str) -> tuple[bool, str]:
        """Check if an engine is available.

        Returns:
            Tuple of (available, reason).
        """
        try:
            if engine == "pymupdf":
                import fitz  # noqa: F401
                return True, "Available"
            elif engine == "pdfplumber":
                import pdfplumber  # noqa: F401
                return True, "Available"
            elif engine == "marker":
                from marker.converters.pdf import PdfConverter  # noqa: F401
                return True, "Available"
            elif engine == "docling":
                from docling.document_converter import DocumentConverter  # noqa: F401
                return True, "Available"
            elif engine == "mineru":
                from magic_pdf.data.dataset import PymuDocDataset  # noqa: F401
                return True, "Available"
            elif engine == "easyocr":
                import easyocr  # noqa: F401
                return True, "Available"
            elif engine == "doctr":
                from doctr.io import DocumentFile  # noqa: F401
                return True, "Available"
            elif engine == "nougat":
                from nougat import NougatModel  # noqa: F401
                return True, "Available"
            elif engine == "surya-lite":
                from surya.ocr import run_ocr  # noqa: F401
                return True, "Available"
            elif engine == "llamaparse":
                from llama_parse import LlamaParse  # noqa: F401
                if os.environ.get("LLAMA_CLOUD_API_KEY"):
                    return True, "Available"
                return False, "Requires LLAMA_CLOUD_API_KEY"
            elif engine == "mathpix":
                if os.environ.get("MATHPIX_APP_ID") and os.environ.get("MATHPIX_APP_KEY"):
                    return True, "Available"
                return False, "Requires MATHPIX_APP_ID and MATHPIX_APP_KEY"
            elif engine == "mineru-cloud":
                if os.environ.get("MINERU_API_KEY"):
                    return True, "Available"
                return False, "Requires MINERU_API_KEY"
            elif engine == "doc2x":
                if os.environ.get("DOC2X_API_KEY"):
                    return True, "Available"
                return False, "Requires DOC2X_API_KEY"
            elif engine == "auto":
                return True, "Auto-selects best available"
            else:
                return False, f"Unknown engine: {engine}"
        except ImportError:
            info = ENGINES.get(engine)
            pkg = info.pip_package if info else engine
            return False, f"Install: pip install {pkg}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _detect_best_device() -> str:
        """Detect the best available compute device."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch, 'mps') and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        # Try DirectML (Vulkan-compatible on Windows)
        try:
            import torch_directml  # noqa: F401
            return "dml"
        except ImportError:
            pass
        return "cpu"

    def parse(self, pdf_path: str, output_dir: str | None = None) -> dict[str, Any]:
        """Parse PDF to Markdown, falling back to pymupdf on error.

        Args:
            pdf_path: Path to PDF file.
            output_dir: Directory for output files.

        Returns:
            Dictionary with markdown text, images, and metadata.
        """
        pdf_path = str(Path(pdf_path).resolve())
        logger.debug(f"Resolved PDF path: {pdf_path}")

        if self.engine == "auto":
            self.engine = self._select_engine(pdf_path)
            logger.debug(f"Selected engine: {self.engine}")

        # Try the selected engine, fall back to pymupdf on error
        try:
            return self._try_parse(pdf_path, output_dir)
        except Exception as e:
            logger.warning(f"Engine '{self.engine}' failed: {e}. Falling back to pymupdf...")
            if self.engine != "pymupdf":
                old_engine = self.engine
                self.engine = "pymupdf"
                result = self._try_parse(pdf_path, output_dir)
                result["original_engine"] = old_engine
                return result
            raise

    def _try_parse(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse with the currently selected engine."""
        parsers = {
            "pymupdf": self._parse_with_pymupdf,
            "pdfplumber": self._parse_with_pdfplumber,
            "marker": self._parse_with_marker,
            "docling": self._parse_with_docling,
            "mineru": self._parse_with_mineru,
            "easyocr": self._parse_with_easyocr,
            "doctr": self._parse_with_doctr,
            "nougat": self._parse_with_nougat,
            "surya-lite": self._parse_with_surya_lite,
            "llamaparse": self._parse_with_llamaparse,
            "mathpix": self._parse_with_mathpix,
            "mineru-cloud": self._parse_with_mineru_cloud,
            "doc2x": self._parse_with_doc2x,
        }

        parser_func = parsers.get(self.engine)
        if parser_func:
            return parser_func(pdf_path, output_dir)
        else:
            raise ValueError(f"Unknown engine: {self.engine}")

    def _select_engine(self, pdf_path: str) -> str:
        """Select best parsing engine — NuoYi-style priority order."""
        priority = [
            "marker", "surya-lite", "nougat", "mineru", "docling",
            "easyocr", "doctr", "pymupdf", "pdfplumber",
        ]
        for eng in priority:
            available, reason = self._check_engine_available(eng)
            if available:
                return eng
        return "pymupdf"  # Ultimate fallback

    def _parse_with_pymupdf(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using PyMuPDF."""
        import fitz

        logger.debug(f"Parsing PDF with PyMuPDF: {pdf_path}")

        # Suppress MuPDF stderr errors
        old_stderr = sys.stderr
        try:
            sys.stderr = open(os.devnull, 'w')
            doc = fitz.open(pdf_path)
        finally:
            sys.stderr.close()
            sys.stderr = old_stderr

        logger.debug(f"Opened PDF with {len(doc)} pages")

        markdown_parts = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            try:
                text = page.get_text("markdown")
                if text is None:
                    text = page.get_text("text")
                    logger.debug(f"  Page {page_idx + 1}/{len(doc)}: {len(text)} chars (plain text fallback)")
                else:
                    logger.debug(f"  Page {page_idx + 1}/{len(doc)}: {len(text)} chars (markdown)")
                if text:
                    markdown_parts.append(text)
            except Exception as e:
                logger.warning(f"  Page {page_idx + 1} extraction failed: {e}")
                try:
                    text = page.get_text("text")
                    if text:
                        markdown_parts.append(text)
                except Exception as e2:
                    logger.error(f"  Page {page_idx + 1} plain text also failed: {e2}")

        doc.close()

        markdown = clean_markdown("\n\n".join(markdown_parts))
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        images = {}
        if output_dir:
            image_dir = Path(output_dir) / "images"
            images = extract_images_from_pdf(pdf_path, str(image_dir))
            if images:
                markdown = save_images_and_update_markdown(markdown, images, output_dir)
            logger.debug(f"Extracted {len(images)} images")

        return {
            "markdown": markdown,
            "images": images,
            "page_count": len(fitz.open(pdf_path)),
            "engine": "pymupdf",
        }

    def _parse_with_pdfplumber(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using pdfplumber."""
        try:
            import pdfplumber
        except ImportError as e:
            raise ImportError("Install pdfplumber: pip install pdfplumber") from e

        logger.debug(f"Parsing PDF with PDFPlumber: {pdf_path}")

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
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

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

    def _parse_with_marker(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using marker-pdf."""
        import os

        # Use HF mirror for mainland China
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        # Resolve device
        device = self.device
        if device == "auto":
            device = self._detect_best_device()

        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        logger.debug(f"Parsing PDF with marker-pdf on {device}: {pdf_path}")

        config = {
            "output_format": "markdown",
            "languages": self.langs,
        }
        if self.use_ocr:
            config["force_ocr"] = True

        config_parser = ConfigParser(config)
        artifact_dict = create_model_dict(device=device)

        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=artifact_dict,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
        )

        rendered = converter(pdf_path)
        text, _, images = text_from_rendered(rendered)

        markdown = clean_markdown(text)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        if output_dir and images:
            markdown = save_images_and_update_markdown(markdown, images, output_dir)

        import fitz

        return {
            "markdown": markdown,
            "images": images or {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "marker",
        }

    def _parse_with_docling(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using Docling."""
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as e:
            raise ImportError("Install docling: pip install docling") from e

        logger.debug(f"Parsing PDF with Docling: {pdf_path}")

        converter = DocumentConverter()
        result = converter.convert(pdf_path)

        markdown = result.document.export_to_markdown()
        markdown = clean_markdown(markdown)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        images = {}
        if output_dir and result.document.pictures:
            for pic in result.document.pictures:
                if hasattr(pic, "image") and pic.image is not None:
                    img_name = f"docling_image_{len(images) + 1}.png"
                    images[img_name] = pic.image
            if images:
                markdown = save_images_and_update_markdown(markdown, images, output_dir)

        import fitz

        return {
            "markdown": markdown,
            "images": images,
            "page_count": len(fitz.open(pdf_path)),
            "engine": "docling",
        }

    def _parse_with_mineru(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using MinerU."""
        try:
            from magic_pdf.data.data_reader_writer import FileBasedDataWriter
            from magic_pdf.data.dataset import PymuDocDataset
            from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
        except ImportError as e:
            raise ImportError("Install mineru: pip install magic-pdf[full]") from e

        logger.debug(f"Parsing PDF with MinerU: {pdf_path}")

        # Read PDF
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Parse
        ds = PymuDocDataset(pdf_bytes)
        if self.use_ocr:
            ds = ds.apply(doc_analyze, ocr=True)
        else:
            ds = ds.apply(doc_analyze, ocr=False)

        # Export to markdown
        if output_dir:
            image_dir = Path(output_dir) / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            writer = FileBasedDataWriter(str(image_dir))
            md_content = ds.dump_to_md(writer)
        else:
            md_content = ds.dump_to_md()

        markdown = clean_markdown(md_content)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "mineru",
        }

    def _parse_with_easyocr(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using EasyOCR."""
        try:
            import easyocr
        except ImportError as e:
            raise ImportError("Install easyocr: pip install easyocr") from e

        logger.debug(f"Parsing PDF with EasyOCR: {pdf_path}")

        import fitz
        from PIL import Image
        import io
        import numpy as np

        # Map language codes to easyocr format
        lang_map = {
            "zh": "ch_sim", "zh-Hant": "ch_tra", "en": "en", "ja": "ja",
            "ko": "ko", "fr": "fr", "de": "de", "es": "es", "ru": "ru",
            "ar": "ar", "hi": "hi", "th": "th", "vi": "vi",
        }
        raw_langs = [l.strip() for l in self.langs.split(",") if l.strip()]
        langs = [lang_map.get(l, "en") for l in raw_langs] if raw_langs else ["en"]
        logger.debug(f"EasyOCR langs: {langs} (from: {self.langs})")
        reader = easyocr.Reader(langs)

        doc = fitz.open(pdf_path)
        markdown_parts = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            # Render page to PIL, convert to numpy array for easyocr
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            img_np = np.array(img)

            try:
                result = reader.readtext(img_np, detail=0)
                text = "\n".join(result) if result else ""
            except Exception as e:
                logger.warning(f"  Page {page_idx + 1} OCR failed: {e}")
                text = ""

            if text.strip():
                markdown_parts.append(text)
            logger.debug(f"  Page {page_idx + 1}/{len(doc)}: {len(text)} chars")

        doc.close()

        markdown = clean_markdown("\n\n".join(markdown_parts))
        logger.debug(f"EasyOCR extracted: {len(markdown)} chars from {len(markdown_parts)} pages")

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "easyocr",
        }

    def _parse_with_doctr(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using DocTR."""
        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
        except ImportError as e:
            raise ImportError("Install doctr: pip install doctr") from e

        logger.debug(f"Parsing PDF with DocTR: {pdf_path}")

        doc = DocumentFile.from_pdf(pdf_path)
        predictor = ocr_predictor(pretrained=True)
        result = predictor(doc)

        markdown_parts = []
        for page in result.pages:
            blocks = page.blocks
            for block in blocks:
                for line in block.lines:
                    text = " ".join(word.value for word in line.words)
                    if text:
                        markdown_parts.append(text)
                markdown_parts.append("")

        markdown = clean_markdown("\n\n".join(markdown_parts))
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "doctr",
        }

    def _parse_with_nougat(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using Nougat."""
        try:
            from nougat import NougatModel
            from nougat.utils.dataset import ImageDataset
            from nougat.utils.device import move_to_device
            from nougat.postprocessing import markdown_compatible
        except ImportError as e:
            raise ImportError("Install nougat: pip install nougat-ocr") from e

        logger.debug(f"Parsing PDF with Nougat: {pdf_path}")

        import fitz
        doc = fitz.open(pdf_path)
        markdown_parts = []

        model = NougatModel.from_pretrained("facebook/nougat-base")
        model = move_to_device(model)
        model.eval()

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=96)
            import numpy as np
            from PIL import Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            dataset = ImageDataset([img], partial=model.hparams.partial)
            model_output = model.inference(image_tensors=dataset, early_stopping=False)
            prediction = markdown_compatible(model_output["predictions"][0])
            if prediction:
                markdown_parts.append(prediction)

        doc.close()

        markdown = clean_markdown("\n\n".join(markdown_parts))
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "nougat",
        }

    def _parse_with_surya_lite(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using Surya Lite OCR."""
        try:
            from surya.ocr import run_ocr
            from surya.detection import batch_text_detection
            from surya.layout import batch_layout_detection
            from surya.settings import settings
            from PIL import Image
        except ImportError as e:
            raise ImportError("Install surya-ocr: pip install surya-ocr") from e

        logger.debug(f"Parsing PDF with Surya Lite: {pdf_path}")

        import fitz
        doc = fitz.open(pdf_path)
        markdown_parts = []

        langs = self.langs.split(",")

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=96)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Detect text
            det_results = batch_text_detection([img], settings.DETECTOR_MODEL, settings.DETECTOR_BATCH)

            # OCR
            ocr_results = run_ocr([img], det_results, settings.RECOGNITION_MODEL, settings.RECOGNITION_BATCH, langs)

            page_text = []
            for line in ocr_results[0].text_lines:
                page_text.append(line.text)

            if page_text:
                markdown_parts.append("\n".join(page_text))

        doc.close()

        markdown = clean_markdown("\n\n".join(markdown_parts))
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "surya-lite",
        }

    def _parse_with_llamaparse(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using LlamaParse (Cloud)."""
        try:
            from llama_parse import LlamaParse
        except ImportError as e:
            raise ImportError("Install llama-parse: pip install llama-parse") from e

        logger.debug(f"Parsing PDF with LlamaParse: {pdf_path}")

        parser = LlamaParse(
            result_type="markdown",
            verbose=self.use_ocr,
        )

        documents = parser.load_data(pdf_path)
        markdown = documents[0].text
        markdown = clean_markdown(markdown)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "llamaparse",
        }

    def _parse_with_mathpix(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using Mathpix (Cloud)."""
        import requests
        import base64

        logger.debug(f"Parsing PDF with Mathpix: {pdf_path}")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        response = requests.post(
            "https://api.mathpix.com/v3/pdf",
            headers={
                "app_id": os.environ.get("MATHPIX_APP_ID"),
                "app_key": os.environ.get("MATHPIX_APP_KEY"),
                "Content-Type": "application/pdf",
            },
            data={
                "conversion_formats": "md",
                "math_inline_delims": ["$", "$"],
                "math_display_delims": ["$$", "$$"],
            },
            files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
        )
        response.raise_for_status()
        pdf_id = response.json()["pdf_id"]

        # Poll for result
        import time
        for _ in range(60):
            time.sleep(5)
            result_resp = requests.get(
                f"https://api.mathpix.com/v3/converter/{pdf_id}",
                headers={
                    "app_id": os.environ.get("MATHPIX_APP_ID"),
                    "app_key": os.environ.get("MATHPIX_APP_KEY"),
                },
            )
            result_resp.raise_for_status()
            result = result_resp.json()
            if result.get("status") == "completed":
                markdown = result.get("md", "")
                break
            elif result.get("status") == "error":
                raise RuntimeError(f"Mathpix error: {result.get('error')}")
        else:
            raise RuntimeError("Mathpix timeout")

        markdown = clean_markdown(markdown)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "mathpix",
        }

    def _parse_with_mineru_cloud(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using MinerU Cloud."""
        import requests

        logger.debug(f"Parsing PDF with MinerU Cloud: {pdf_path}")

        # Upload
        with open(pdf_path, "rb") as f:
            response = requests.post(
                "https://api.mineru.net/v1/files/upload",
                headers={"Authorization": f"Bearer {os.environ.get('MINERU_API_KEY')}"},
                files={"file": f},
            )
            response.raise_for_status()
            file_id = response.json()["data"]["file_id"]

        # Parse
        response = requests.post(
            "https://api.mineru.net/v1/parse",
            headers={"Authorization": f"Bearer {os.environ.get('MINERU_API_KEY')}"},
            json={"file_id": file_id},
        )
        response.raise_for_status()
        task_id = response.json()["data"]["task_id"]

        # Poll
        import time
        for _ in range(60):
            time.sleep(5)
            result_resp = requests.get(
                f"https://api.mineru.net/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {os.environ.get('MINERU_API_KEY')}"},
            )
            result_resp.raise_for_status()
            result = result_resp.json()
            if result["data"]["status"] == "completed":
                markdown_url = result["data"]["results"]["md"]
                md_resp = requests.get(markdown_url)
                md_resp.raise_for_status()
                markdown = md_resp.text
                break
            elif result["data"]["status"] == "failed":
                raise RuntimeError(f"MinerU Cloud error: {result['data'].get('error')}")
        else:
            raise RuntimeError("MinerU Cloud timeout")

        markdown = clean_markdown(markdown)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "mineru-cloud",
        }

    def _parse_with_doc2x(self, pdf_path: str, output_dir: str | None) -> dict[str, Any]:
        """Parse PDF using Doc2X (Cloud)."""
        import requests

        logger.debug(f"Parsing PDF with Doc2X: {pdf_path}")

        # Upload
        with open(pdf_path, "rb") as f:
            response = requests.post(
                "https://v2.doc2x.noedgeai.com/api/v2/parse",
                headers={"Authorization": f"Bearer {os.environ.get('DOC2X_API_KEY')}"},
                files={"file": f},
            )
            response.raise_for_status()
            uid = response.json()["data"]["uid"]

        # Poll
        import time
        for _ in range(60):
            time.sleep(5)
            result_resp = requests.get(
                f"https://v2.doc2x.noedgeai.com/api/v2/parse/status?uid={uid}",
                headers={"Authorization": f"Bearer {os.environ.get('DOC2X_API_KEY')}"},
            )
            result_resp.raise_for_status()
            result = result_resp.json()
            if result["data"]["status"] == "success":
                result_url = result["data"]["result"]["pages"]
                md_resp = requests.get(result_url)
                md_resp.raise_for_status()
                markdown = md_resp.text
                break
            elif result["data"]["status"] == "failed":
                raise RuntimeError(f"Doc2X error: {result['data'].get('error')}")
        else:
            raise RuntimeError("Doc2X timeout")

        markdown = clean_markdown(markdown)
        logger.debug(f"Extracted markdown: {len(markdown)} chars")

        import fitz

        return {
            "markdown": markdown,
            "images": {},
            "page_count": len(fitz.open(pdf_path)),
            "engine": "doc2x",
        }

    @staticmethod
    def _table_to_markdown(table: list[list]) -> str:
        """Convert table data to Markdown."""
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
    """Parse CAJ (Chinese Academic Journal) files."""

    def __init__(self, engine: str = "auto", use_ocr: bool = False, langs: str = "zh,en"):
        self.pdf_parser = PDFParser(engine=engine, use_ocr=use_ocr, langs=langs)

    def parse(self, caj_path: str, output_dir: str | None = None) -> dict[str, Any]:
        caj_path = Path(caj_path)

        if not caj_path.exists():
            raise FileNotFoundError(f"CAJ file not found: {caj_path}")

        pdf_path = self._caj_to_pdf(str(caj_path), output_dir)

        try:
            result = self.pdf_parser.parse(pdf_path, output_dir)
            result["original_format"] = "caj"
            return result
        finally:
            if Path(pdf_path).exists() and Path(pdf_path).parent.name.startswith("yanfu_caj_"):
                Path(pdf_path).unlink()

    def _caj_to_pdf(self, caj_path: str, output_dir: str | None) -> str:
        try:
            return self._convert_with_caj2pdf(caj_path, output_dir)
        except (ImportError, FileNotFoundError):
            pass

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
        import caj2pdf

        caj_path = Path(caj_path)

        if output_dir:
            pdf_path = Path(output_dir) / f"{caj_path.stem}.pdf"
        else:
            pdf_path = caj_path.with_suffix(".pdf")

        caj2pdf.convert(str(caj_path), str(pdf_path))
        return str(pdf_path)

    def _extract_pdf_from_caj(self, caj_path: str, output_dir: str | None) -> str:
        import fitz

        caj_path = Path(caj_path)

        if output_dir:
            pdf_path = Path(output_dir) / f"{caj_path.stem}.pdf"
        else:
            temp_dir = tempfile.mkdtemp(prefix="yanfu_caj_")
            pdf_path = Path(temp_dir) / f"{caj_path.stem}.pdf"

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


def parse_document(
    file_path: str,
    engine: str = "auto",
    use_ocr: bool = False,
    langs: str = "zh,en",
    output_dir: str | None = None,
    device: str = "auto",
) -> dict[str, Any]:
    """Parse a document file (PDF or CAJ) to Markdown."""
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        parser = PDFParser(engine=engine, use_ocr=use_ocr, langs=langs, device=device)
        return parser.parse(str(file_path), output_dir)
    elif suffix == ".caj":
        parser = CAJParser(engine=engine, use_ocr=use_ocr, langs=langs)
        return parser.parse(str(file_path), output_dir)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
