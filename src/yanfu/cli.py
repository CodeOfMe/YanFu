"""YanFu - Command-line interface for document translation.

Translates PDF and CAJ files to target language using Ollama or OpenAI-compatible APIs.
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .api import ToolResult, yanfu_translate_file, yanfu_translate_files
from .translator import ConfigManager, ModelFetcher
from .utils import LANGUAGE_MAP, find_documents


def main():
    """Main entry point for YanFu CLI."""
    parser = argparse.ArgumentParser(
        prog="yanfu",
        description="YanFu - Translate PDF/CAJ documents using Ollama or OpenAI-compatible APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  yanfu --gui                                # Launch graphical interface
  yanfu --config                             # Run configuration wizard
  yanfu paper.pdf                            # Translate to English (default)
  yanfu paper.pdf -l zh                      # Translate to Chinese
  yanfu paper.pdf -l ja                      # Translate to Japanese
  yanfu paper.pdf paper2.pdf -l fr           # Translate multiple files
  yanfu ./papers --batch -l es               # Batch translate directory
  yanfu paper.pdf -o ./output -l de -v       # Verbose output
  yanfu paper.pdf --json                     # JSON output
  yanfu --list-models                        # List available models from configured provider

Configuration:
  Run 'yanfu --config' to set up your translation provider.
  Configuration is saved to ~/.config/yanfu/config.json
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
        help="List available translation model presets",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Run configuration wizard",
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test connection to configured translation provider",
    )
    parser.add_argument(
        "--reset-config",
        action="store_true",
        help="Reset configuration to defaults",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch graphical user interface",
    )

    args = parser.parse_args()

    # Handle configuration commands
    if args.config:
        from .config_wizard import run_config_wizard
        run_config_wizard()
        sys.exit(0)

    if args.reset_config:
        config = ConfigManager()
        config.reset()
        print("Configuration reset to defaults.")
        sys.exit(0)

    if args.test_connection:
        config = ConfigManager()
        if not config.is_configured():
            print("Not configured. Run 'yanfu --config' to set up.")
            sys.exit(1)

        from .translator import OllamaTranslator
        translator = OllamaTranslator(
            provider=config.get("provider"),
            base_url=config.get("base_url"),
            model=config.get("model"),
            api_key=config.get("api_key", ""),
        )
        success, message = translator.test_connection()
        print(message)
        sys.exit(0 if success else 1)

    if args.list_langs:
        print("Supported languages:")
        for code, name in LANGUAGE_MAP.items():
            if code != "auto":
                print(f"  {code:8s}  {name}")
        sys.exit(0)

    if args.list_models:
        config = ConfigManager()
        if not config.is_configured():
            print("Not configured. Run 'yanfu --config' first.")
            sys.exit(1)

        provider = config.get("provider", "ollama")
        base_url = config.get("base_url", "http://localhost:11434")
        api_key = config.get("api_key", "")

        print(f"Fetching models from {provider} ({base_url})...")
        models = ModelFetcher.get_models(provider, base_url, api_key)

        if models:
            print(f"\nAvailable models ({len(models)}):")
            for m in models:
                print(f"  {m}")
        else:
            print("\nNo models found. Check your connection and configuration.")
            sys.exit(1)
        sys.exit(0)

    if args.gui:
        from .gui import run_gui
        run_gui()
        sys.exit(0)

    # Check configuration before processing
    config = ConfigManager()
    if not config.is_configured():
        print("YanFu is not configured yet.")
        print("Run 'yanfu --config' to set up your translation provider.")
        print()
        parser.print_help()
        sys.exit(1)

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
        result = _process_batch(args, config)
    else:
        result = _process_files(args, config)

    # Output results
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_result(result, args.verbose)

    sys.exit(0 if result.success else 1)


def _process_files(args, config: ConfigManager) -> ToolResult:
    """Process individual files.

    Args:
        args: Parsed arguments.
        config: Configuration manager.

    Returns:
        ToolResult with processing results.
    """
    if len(args.input) == 1:
        return yanfu_translate_file(
            args.input[0],
            output_dir=args.output,
            target_lang=args.lang,
            source_lang=args.source_lang,
            temperature=args.temperature,
            page_size=args.page_size,
            font_name=args.font,
            font_size=args.font_size,
            margin=args.margin,
            config=config,
        )
    else:
        return yanfu_translate_files(
            args.input,
            output_dir=args.output,
            target_lang=args.lang,
            source_lang=args.source_lang,
            temperature=args.temperature,
            page_size=args.page_size,
            font_name=args.font,
            font_size=args.font_size,
            margin=args.margin,
            config=config,
        )


def _process_batch(args, config: ConfigManager) -> ToolResult:
    """Process directory in batch mode.

    Args:
        args: Parsed arguments.
        config: Configuration manager.

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
        temperature=args.temperature,
        page_size=args.page_size,
        font_name=args.font,
        font_size=args.font_size,
        margin=args.margin,
        config=config,
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
