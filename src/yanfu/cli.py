"""YanFu - Command-line interface for document translation.

Translates PDF and CAJ files to target language using local GGUF models.
Zero-configuration: models auto-download on first run.
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .api import ToolResult, yanfu_translate_file, yanfu_translate_files
from .translator import MODEL_DEFINITIONS, ModelManager
from .utils import LANGUAGE_MAP, find_documents


def main():
    """Main entry point for YanFu CLI."""
    parser = argparse.ArgumentParser(
        prog="yanfu",
        description="YanFu - Translate PDF/CAJ documents using local LLMs (zero-configuration)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  yanfu paper.pdf                              # Translate to English (default)
  yanfu paper.pdf -l zh                        # Translate to Chinese
  yanfu paper.pdf -l ja --model qwen3:0.6b     # Translate to Japanese with Qwen
  yanfu paper.pdf paper2.pdf -l fr             # Translate multiple files
  yanfu ./papers --batch -l es                 # Batch translate directory
  yanfu paper.pdf -o ./output -l de -v         # Verbose output
  yanfu paper.pdf --json                       # JSON output

Translation Models (auto-downloaded on first use):
  gemma3:1b    Google Gemma 3 1B (default, ~780MB)
  qwen3:0.6b   Alibaba Qwen 3 0.6B (fastest, ~420MB)
  qwen3:1.8b   Alibaba Qwen 3 1.8B (best quality, ~1.1GB)

Languages:
  en   English (default target)
  zh   Chinese (Simplified)
  zh-Hant  Chinese (Traditional)
  ja   Japanese
  ko   Korean
  fr   French
  de   German
  es   Spanish
  ru   Russian
  ... (see full list with --list-langs)

Zero-Configuration:
  - All dependencies installed with pip
  - Models auto-download from ModelScope/HuggingFace on first run
  - No Ollama, no API keys, no external services needed
  - Works completely offline after first download
        """,
    )

    parser.add_argument(
        "input",
        nargs="*",
        help="Input PDF/CAJ file(s) or directory",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"YanFu {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default="en",
        help="Target language code (default: en)",
    )
    parser.add_argument(
        "--source-lang",
        default="auto",
        help="Source language code (default: auto)",
    )
    parser.add_argument(
        "--model",
        default="gemma3:1b",
        help="Translation model (default: gemma3:1b)",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Direct path to GGUF model file (optional)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Model cache directory (default: ~/.cache/yanfu/models)",
    )
    parser.add_argument(
        "--use-ocr",
        action="store_true",
        help="Use OCR for scanned documents",
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "pymupdf", "marker", "pdfplumber"],
        help="PDF parsing engine",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Translation temperature (0.0-1.0)",
    )
    parser.add_argument(
        "--page-size",
        default="A4",
        choices=["A4", "letter"],
        help="Output PDF page size",
    )
    parser.add_argument(
        "--font",
        default=None,
        help="Output PDF font name",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=11,
        help="Output PDF font size",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=20.0,
        help="Output PDF margin in mm",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch process directory",
    )
    parser.add_argument(
        "--list-langs",
        action="store_true",
        help="List supported languages",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available translation models",
    )
    parser.add_argument(
        "--download-model",
        metavar="MODEL",
        help="Download a model without translating",
    )
    parser.add_argument(
        "--list-downloaded",
        action="store_true",
        help="List downloaded models",
    )
    parser.add_argument(
        "--cleanup-models",
        action="store_true",
        help="Remove all downloaded models",
    )

    args = parser.parse_args()

    # Handle model management commands
    if args.list_langs:
        print("Supported languages:")
        for code, name in LANGUAGE_MAP.items():
            if code != "auto":
                print(f"  {code:8s}  {name}")
        sys.exit(0)

    if args.list_models:
        print("Available translation models (auto-downloaded on first use):")
        print()
        for model_id, info in MODEL_DEFINITIONS.items():
            status = ""
            mm = ModelManager()
            if mm.is_model_downloaded(model_id):
                size = mm.get_model_size(model_id)
                status = f" [Downloaded: {size / 1024 / 1024:.0f}MB]"
            print(f"  {model_id:15s}  {info['name']}")
            print(f"                   {info['quality']} (~{info['size_mb']}MB){status}")
        print()
        print("Models are downloaded to: ~/.cache/yanfu/models/")
        sys.exit(0)

    if args.list_downloaded:
        mm = ModelManager(args.cache_dir)
        downloaded = mm.list_downloaded_models()
        if downloaded:
            print("Downloaded models:")
            for m in downloaded:
                size = mm.get_model_size(m)
                print(f"  {m:15s}  ({size / 1024 / 1024:.0f}MB)")
        else:
            print("No models downloaded yet.")
            print("Models will be auto-downloaded on first use.")
        sys.exit(0)

    if args.download_model:
        mm = ModelManager(args.cache_dir)
        try:
            path = mm.download_model(args.download_model)
            print(f"Model downloaded: {path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    if args.cleanup_models:
        mm = ModelManager(args.cache_dir)
        mm.cleanup()
        print("All models removed.")
        sys.exit(0)

    # Validate input
    if not args.input:
        parser.print_help()
        print("\nError: Input file(s) or directory required.")
        sys.exit(1)

    # Configure logging
    import logging

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Process files
    if args.batch:
        result = _process_batch(args)
    else:
        result = _process_files(args)

    # Output results
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_result(result, args.verbose)

    sys.exit(0 if result.success else 1)


def _process_files(args) -> ToolResult:
    """Process individual files.

    Args:
        args: Parsed arguments.

    Returns:
        ToolResult with processing results.
    """
    if len(args.input) == 1:
        return yanfu_translate_file(
            args.input[0],
            output_dir=args.output,
            target_lang=args.lang,
            source_lang=args.source_lang,
            model_name=args.model,
            model_path=args.model_path,
            temperature=args.temperature,
            page_size=args.page_size,
            font_name=args.font,
            font_size=args.font_size,
            margin=args.margin,
            cache_dir=args.cache_dir,
        )
    else:
        return yanfu_translate_files(
            args.input,
            output_dir=args.output,
            target_lang=args.lang,
            source_lang=args.source_lang,
            model_name=args.model,
            model_path=args.model_path,
            temperature=args.temperature,
            page_size=args.page_size,
            font_name=args.font,
            font_size=args.font_size,
            margin=args.margin,
            cache_dir=args.cache_dir,
        )


def _process_batch(args) -> ToolResult:
    """Process directory in batch mode.

    Args:
        args: Parsed arguments.

    Returns:
        ToolResult with batch processing results.
    """
    input_path = Path(args.input[0])

    if not input_path.is_dir():
        return ToolResult(
            success=False,
            error=f"Not a directory: {input_path}",
        )

    files = find_documents(input_path, recursive=True)

    if not files:
        return ToolResult(
            success=False,
            error=f"No PDF/CAJ files found in {input_path}",
        )

    if not args.quiet:
        print(f"Found {len(files)} document(s) in {input_path}")

    return yanfu_translate_files(
        [str(f) for f in files],
        output_dir=args.output or str(input_path),
        target_lang=args.lang,
        source_lang=args.source_lang,
        model_name=args.model,
        model_path=args.model_path,
        temperature=args.temperature,
        page_size=args.page_size,
        font_name=args.font,
        font_size=args.font_size,
        margin=args.margin,
        cache_dir=args.cache_dir,
    )


def _print_result(result: ToolResult, verbose: bool = False):
    """Print processing result.

    Args:
        result: ToolResult to print.
        verbose: Enable verbose output.
    """
    if result.success:
        data = result.data or {}

        if "results" in data:
            # Batch result
            print("\nBatch processing completed:")
            print(f"  Success: {data.get('success_count', 0)}")
            print(f"  Failed: {data.get('failed_count', 0)}")

            if verbose:
                for r in data.get("results", []):
                    status = "✓" if r["success"] else "✗"
                    print(f"  {status} {Path(r['file']).name}")
                    if r.get("output_pdf"):
                        print(f"    PDF: {r['output_pdf']}")
                    if r.get("output_md"):
                        print(f"    MD:  {r['output_md']}")
                    if r.get("error"):
                        print(f"    Error: {r['error']}")
        else:
            # Single file result
            print("\nTranslation completed:")
            print(f"  PDF: {data.get('output_pdf', 'N/A')}")
            print(f"  MD:  {data.get('output_md', 'N/A')}")
            print(f"  Pages: {data.get('page_count', 0)}")
            print(f"  Images: {data.get('image_count', 0)}")

            if verbose:
                meta = result.metadata or {}
                print(f"  Model: {meta.get('model', 'N/A')}")
                print(f"  Translation time: {meta.get('translation_time', 0):.1f}s")
                print(f"  Total time: {meta.get('total_time', 0):.1f}s")
    else:
        print(f"\nError: {result.error}")

        if verbose and result.metadata:
            print(f"Metadata: {result.metadata}")


if __name__ == "__main__":
    main()
