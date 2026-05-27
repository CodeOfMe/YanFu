"""YanFu - Unified Python API.

Provides ToolResult-based wrappers for programmatic usage
and agent integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .core import DocumentProcessor


@dataclass
class ToolResult:
    """Standard result wrapper for API functions.

    Attributes:
        success: Whether the operation succeeded.
        data: Result data.
        error: Error message if failed.
        metadata: Additional metadata.
    """
    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


def yanfu_translate_file(
    input_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    target_lang: str = "en",
    source_lang: str = "auto",
    model_name: str = "gemma3:1b",
    model_path: str | None = None,
    use_ocr: bool = False,
    parse_engine: str = "auto",
    temperature: float = 0.3,
    page_size: str = "A4",
    font_name: str | None = None,
    font_size: int = 11,
    margin: float = 20.0,
    cache_dir: str | None = None,
) -> ToolResult:
    """Translate a PDF or CAJ file to target language.

    Parses the document, translates using local GGUF model, and generates
    a layout-preserving PDF. Models auto-download on first use.

    Args:
        input_path: Path to input PDF or CAJ file.
        output_dir: Output directory. Defaults to input file's directory.
        target_lang: Target language code (e.g., 'en', 'zh', 'ja').
        source_lang: Source language code ('auto' for auto-detect).
        model_name: Translation model name (gemma3:1b, qwen3:0.6b, qwen3:1.8b).
        model_path: Direct path to GGUF model file (optional).
        use_ocr: Use OCR for scanned documents.
        parse_engine: Parsing engine (auto, pymupdf, marker, pdfplumber).
        temperature: Translation temperature (0.0-1.0).
        page_size: Output PDF page size (A4, letter).
        font_name: Output PDF font name.
        font_size: Output PDF font size.
        margin: Output PDF margin in mm.
        cache_dir: Model cache directory.

    Returns:
        ToolResult with success status and output paths.
    """
    input_path = Path(input_path)

    if not input_path.exists():
        return ToolResult(
            success=False,
            error=f"File not found: {input_path}",
        )

    suffix = input_path.suffix.lower()
    if suffix not in (".pdf", ".caj"):
        return ToolResult(
            success=False,
            error=f"Unsupported format: {suffix}. Use .pdf or .caj",
        )

    if output_dir is None:
        output_dir = input_path.parent
    else:
        output_dir = Path(output_dir)

    try:
        processor = DocumentProcessor(
            output_dir=str(output_dir),
            target_lang=target_lang,
            source_lang=source_lang,
            model_name=model_name,
            model_path=model_path,
            use_ocr=use_ocr,
            parse_engine=parse_engine,
            temperature=temperature,
            page_size=page_size,
            font_name=font_name,
            font_size=font_size,
            margin=margin,
            cache_dir=cache_dir,
            verbose=False,
        )

        result = processor.process(str(input_path))

        if result.success:
            return ToolResult(
                success=True,
                data={
                    "markdown": result.markdown,
                    "output_pdf": result.output_pdf,
                    "output_md": result.output_md,
                    "image_count": len(result.images),
                    "page_count": result.page_count,
                },
                metadata={
                    "input_path": str(input_path),
                    "target_lang": target_lang,
                    "model": model_name,
                    "translation_time": result.translation_time,
                    "total_time": result.total_time,
                    "version": __version__,
                },
            )
        else:
            return ToolResult(
                success=False,
                error=result.error,
                metadata={
                    "input_path": str(input_path),
                    "total_time": result.total_time,
                    "version": __version__,
                },
            )

    except Exception as e:
        return ToolResult(
            success=False,
            error=str(e),
            metadata={
                "input_path": str(input_path),
                "version": __version__,
            },
        )


def yanfu_translate_files(
    input_paths: list[str | Path],
    *,
    output_dir: str | Path | None = None,
    target_lang: str = "en",
    source_lang: str = "auto",
    model_name: str = "gemma3:1b",
    model_path: str | None = None,
    use_ocr: bool = False,
    parse_engine: str = "auto",
    temperature: float = 0.3,
    page_size: str = "A4",
    font_name: str | None = None,
    font_size: int = 11,
    margin: float = 20.0,
    cache_dir: str | None = None,
) -> ToolResult:
    """Translate multiple PDF or CAJ files to target language.

    Args:
        input_paths: List of input file paths.
        output_dir: Output directory.
        target_lang: Target language code.
        source_lang: Source language code.
        model_name: Translation model name.
        model_path: Direct path to GGUF model file.
        use_ocr: Use OCR.
        parse_engine: Parsing engine.
        temperature: Translation temperature.
        page_size: Output PDF page size.
        font_name: Output PDF font.
        font_size: Output PDF font size.
        margin: Output PDF margin.
        cache_dir: Model cache directory.

    Returns:
        ToolResult with batch processing results.
    """
    if not input_paths:
        return ToolResult(
            success=False,
            error="No input files provided",
        )

    # Validate all files
    valid_paths = []
    errors = []

    for path in input_paths:
        path = Path(path)
        if not path.exists():
            errors.append(f"File not found: {path}")
        elif path.suffix.lower() not in (".pdf", ".caj"):
            errors.append(f"Unsupported format: {path.suffix}")
        else:
            valid_paths.append(str(path))

    if not valid_paths:
        return ToolResult(
            success=False,
            error=f"No valid files: {'; '.join(errors)}",
        )

    if output_dir is None:
        output_dir = Path(valid_paths[0]).parent
    else:
        output_dir = Path(output_dir)

    try:
        processor = DocumentProcessor(
            output_dir=str(output_dir),
            target_lang=target_lang,
            source_lang=source_lang,
            model_name=model_name,
            model_path=model_path,
            use_ocr=use_ocr,
            parse_engine=parse_engine,
            temperature=temperature,
            page_size=page_size,
            font_name=font_name,
            font_size=font_size,
            margin=margin,
            cache_dir=cache_dir,
            verbose=False,
        )

        results = processor.process_batch(valid_paths)

        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count

        return ToolResult(
            success=failed_count == 0,
            data={
                "results": [
                    {
                        "file": r.metadata.get("source_file", ""),
                        "success": r.success,
                        "output_pdf": r.output_pdf,
                        "output_md": r.output_md,
                        "error": r.error,
                    }
                    for r in results
                ],
                "success_count": success_count,
                "failed_count": failed_count,
            },
            metadata={
                "total_files": len(valid_paths),
                "target_lang": target_lang,
                "model": model_name,
                "errors": errors,
                "version": __version__,
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            error=str(e),
            metadata={
                "total_files": len(valid_paths),
                "version": __version__,
            },
        )
