"""YanFu - Core processing pipeline.

Orchestrates document parsing, translation, and PDF generation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .parser import parse_document
from .renderer import render_pdf
from .translator import ConfigManager, translate_markdown
from .utils import clean_markdown


@dataclass
class ProcessingResult:
    """Result of document processing.

    Attributes:
        success: Whether processing succeeded.
        markdown: Translated Markdown text.
        output_pdf: Output PDF path.
        output_md: Output Markdown path.
        images: Extracted images.
        page_count: Number of pages.
        translation_time: Translation time in seconds.
        total_time: Total processing time in seconds.
        error: Error message if failed.
        metadata: Additional metadata.
    """
    success: bool
    markdown: str = ""
    output_pdf: str = ""
    output_md: str = ""
    images: dict = field(default_factory=dict)
    page_count: int = 0
    translation_time: float = 0.0
    total_time: float = 0.0
    error: str = ""
    metadata: dict = field(default_factory=dict)


class DocumentProcessor:
    """Process documents through parse-translate-render pipeline.

    Handles PDF and CAJ files, translates using Ollama or OpenAI-compatible APIs,
    and generates layout-preserving PDF output.
    """

    def __init__(
        self,
        output_dir: str | None = None,
        target_lang: str = "en",
        source_lang: str = "auto",
        use_ocr: bool = False,
        parse_engine: str = "auto",
        temperature: float = 0.3,
        page_size: str = "A4",
        font_name: str | None = None,
        font_size: int = 11,
        margin: float = 20.0,
        config: ConfigManager | None = None,
        verbose: bool = False,
    ):
        """Initialize document processor.

        Args:
            output_dir: Output directory.
            target_lang: Target language code.
            source_lang: Source language code.
            use_ocr: Use OCR for scanning.
            parse_engine: Parsing engine.
            temperature: Translation temperature.
            page_size: Output PDF page size.
            font_name: Output PDF font.
            font_size: Output PDF font size.
            margin: Output PDF margin.
            config: Configuration manager.
            verbose: Enable verbose output.
        """
        self.output_dir = output_dir
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.use_ocr = use_ocr
        self.parse_engine = parse_engine
        self.temperature = temperature
        self.page_size = page_size
        self.font_name = font_name
        self.font_size = font_size
        self.margin = margin
        self.config = config if config else ConfigManager()
        self.verbose = verbose

    def process(self, file_path: str) -> ProcessingResult:
        """Process a single document file.

        Args:
            file_path: Path to document file.

        Returns:
            Processing result.
        """
        start_time = time.time()
        file_path = Path(file_path)

        if not file_path.exists():
            return ProcessingResult(
                success=False,
                error=f"File not found: {file_path}",
            )

        suffix = file_path.suffix.lower()
        if suffix not in (".pdf", ".caj"):
            return ProcessingResult(
                success=False,
                error=f"Unsupported file format: {suffix}",
            )

        # Create output directory
        output_dir = self.output_dir or str(file_path.parent)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectory for images
        image_dir = output_dir / f"{file_path.stem}_images"
        image_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._log(f"Parsing {file_path.name}...")

            # Step 1: Parse document
            parse_result = parse_document(
                str(file_path),
                engine=self.parse_engine,
                use_ocr=self.use_ocr,
                output_dir=str(image_dir),
            )

            markdown = parse_result["markdown"]
            images = parse_result.get("images", {})
            page_count = parse_result.get("page_count", 0)

            self._log(f"Parsed: {page_count} pages, {len(images)} images")

            # Step 2: Translate
            self._log(f"Translating to {self.target_lang}...")
            translation_start = time.time()

            translated_markdown = translate_markdown(
                markdown,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                temperature=self.temperature,
                config=self.config,
            )

            translation_time = time.time() - translation_start
            translated_markdown = clean_markdown(translated_markdown)

            self._log(f"Translation completed in {translation_time:.1f}s")

            # Step 3: Save Markdown
            output_md = str(output_dir / f"{file_path.stem}_{self.target_lang}.md")
            Path(output_md).write_text(translated_markdown, encoding="utf-8")

            self._log(f"Saved Markdown: {output_md}")

            # Step 4: Render PDF
            output_pdf = str(output_dir / f"{file_path.stem}_{self.target_lang}.pdf")

            render_pdf(
                translated_markdown,
                output_path=output_pdf,
                image_dir=str(image_dir),
                page_size=self.page_size,
                font_name=self.font_name,
                font_size=self.font_size,
                margin=self.margin,
            )

            self._log(f"Saved PDF: {output_pdf}")

            total_time = time.time() - start_time

            return ProcessingResult(
                success=True,
                markdown=translated_markdown,
                output_pdf=output_pdf,
                output_md=output_md,
                images=images,
                page_count=page_count,
                translation_time=translation_time,
                total_time=total_time,
                metadata={
                    "source_file": str(file_path),
                    "source_lang": self.source_lang,
                    "target_lang": self.target_lang,
                    "model": self.config.get("model", "unknown"),
                    "parse_engine": parse_result.get("engine", "unknown"),
                },
            )

        except Exception as e:
            total_time = time.time() - start_time
            return ProcessingResult(
                success=False,
                error=str(e),
                total_time=total_time,
            )

    def process_batch(self, file_paths: list[str]) -> list[ProcessingResult]:
        """Process multiple document files.

        Args:
            file_paths: List of document file paths.

        Returns:
            List of processing results.
        """
        results = []

        for i, file_path in enumerate(file_paths, 1):
            self._log(f"\n[{i}/{len(file_paths)}] Processing {Path(file_path).name}...")
            result = self.process(file_path)
            results.append(result)

            if result.success:
                self._log(f"✓ {Path(file_path).name} completed")
            else:
                self._log(f"✗ {Path(file_path).name} failed: {result.error}")

        return results

    def _log(self, message: str):
        """Log message if verbose mode is enabled.

        Args:
            message: Log message.
        """
        if self.verbose:
            print(f"[YanFu] {message}")


def process_document(
    input_path: str,
    *,
    output_dir: str | None = None,
    target_lang: str = "en",
    source_lang: str = "auto",
    use_ocr: bool = False,
    parse_engine: str = "auto",
    temperature: float = 0.3,
    page_size: str = "A4",
    font_name: str | None = None,
    font_size: int = 11,
    margin: float = 20.0,
    config: ConfigManager | None = None,
    verbose: bool = False,
) -> ProcessingResult:
    """Process a document file through the full pipeline.

    Args:
        input_path: Input document path.
        output_dir: Output directory.
        target_lang: Target language code.
        source_lang: Source language code.
        use_ocr: Use OCR for scanning.
        parse_engine: Parsing engine.
        temperature: Translation temperature.
        page_size: Output PDF page size.
        font_name: Output PDF font.
        font_size: Output PDF font size.
        margin: Output PDF margin.
        config: Configuration manager.
        verbose: Enable verbose output.

    Returns:
        Processing result.
    """
    processor = DocumentProcessor(
        output_dir=output_dir,
        target_lang=target_lang,
        source_lang=source_lang,
        use_ocr=use_ocr,
        parse_engine=parse_engine,
        temperature=temperature,
        page_size=page_size,
        font_name=font_name,
        font_size=font_size,
        margin=margin,
        config=config,
        verbose=verbose,
    )

    return processor.process(input_path)
