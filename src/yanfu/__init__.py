"""YanFu - PDF/CAJ to Markdown translator with layout-preserving PDF generation.

A tool that converts PDF and CAJ documents to Markdown, translates them
using local LLMs from ModelScope (gemma3:1b, qwen3:0.6b), and generates
PDF files with preserved layout, images, and formulas.
"""

__version__ = "0.1.0"

from .api import ToolResult, yanfu_translate_file, yanfu_translate_files

__all__ = [
    "__version__",
    "ToolResult",
    "yanfu_translate_file",
    "yanfu_translate_files",
]
