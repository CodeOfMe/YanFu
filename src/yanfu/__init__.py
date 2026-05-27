"""YanFu - PDF/CAJ to Markdown translator with layout-preserving PDF generation.

A tool that converts PDF and CAJ documents to Markdown, translates them
using Ollama or OpenAI-compatible APIs, and generates PDF files with
preserved layout, images, and formulas.
"""

__version__ = "0.2.4"

from .api import ToolResult, yanfu_translate_file, yanfu_translate_files

__all__ = [
    "__version__",
    "ToolResult",
    "yanfu_translate_file",
    "yanfu_translate_files",
]
