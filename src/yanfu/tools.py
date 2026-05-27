"""YanFu - OpenAI function-calling tool definitions.

Provides TOOLS list and dispatch() for LLM agent integration.
"""

from __future__ import annotations

import json
from typing import Any

from .translator import MODEL_DEFINITIONS

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "yanfu_translate_file",
            "description": (
                "Translate a PDF or CAJ document to a target language using local GGUF models. "
                "Parses the document, translates the content, and generates a layout-preserving "
                "PDF output. Models auto-download on first use from ModelScope/HuggingFace. "
                "No external services or API keys needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to the input PDF or CAJ file.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory path (default: same as input).",
                    },
                    "target_lang": {
                        "type": "string",
                        "description": "Target language code (e.g., 'en', 'zh', 'ja').",
                        "default": "en",
                    },
                    "source_lang": {
                        "type": "string",
                        "description": "Source language code ('auto' for auto-detect).",
                        "default": "auto",
                    },
                    "model_name": {
                        "type": "string",
                        "enum": list(MODEL_DEFINITIONS.keys()),
                        "description": "Translation model name.",
                        "default": "gemma3:1b",
                    },
                    "model_path": {
                        "type": "string",
                        "description": "Direct path to GGUF model file (optional).",
                    },
                    "use_ocr": {
                        "type": "boolean",
                        "description": "Use OCR for scanned documents.",
                        "default": False,
                    },
                    "parse_engine": {
                        "type": "string",
                        "enum": ["auto", "pymupdf", "marker", "pdfplumber"],
                        "description": "PDF parsing engine.",
                        "default": "auto",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Translation temperature (0.0-1.0).",
                        "default": 0.3,
                    },
                    "page_size": {
                        "type": "string",
                        "enum": ["A4", "letter"],
                        "description": "Output PDF page size.",
                        "default": "A4",
                    },
                    "font_name": {
                        "type": "string",
                        "description": "Output PDF font name (auto-detects CJK fonts).",
                    },
                    "font_size": {
                        "type": "integer",
                        "description": "Output PDF font size.",
                        "default": 11,
                    },
                    "margin": {
                        "type": "number",
                        "description": "Output PDF margin in mm.",
                        "default": 20.0,
                    },
                    "cache_dir": {
                        "type": "string",
                        "description": "Model cache directory.",
                    },
                },
                "required": ["input_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "yanfu_translate_files",
            "description": (
                "Translate multiple PDF or CAJ documents to a target language. "
                "Batch processes files and returns results for each file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of input file paths.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory path.",
                    },
                    "target_lang": {
                        "type": "string",
                        "description": "Target language code.",
                        "default": "en",
                    },
                    "source_lang": {
                        "type": "string",
                        "description": "Source language code.",
                        "default": "auto",
                    },
                    "model_name": {
                        "type": "string",
                        "enum": list(MODEL_DEFINITIONS.keys()),
                        "description": "Translation model name.",
                        "default": "gemma3:1b",
                    },
                    "use_ocr": {
                        "type": "boolean",
                        "description": "Use OCR for scanned documents.",
                        "default": False,
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Translation temperature.",
                        "default": 0.3,
                    },
                },
                "required": ["input_paths"],
            },
        },
    },
]


def dispatch(name: str, arguments: dict[str, Any] | str) -> dict:
    """Dispatch a tool call to the appropriate API function.

    Args:
        name: Tool name.
        arguments: Tool arguments.

    Returns:
        Tool result dictionary.
    """
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    if name == "yanfu_translate_file":
        from .api import yanfu_translate_file

        result = yanfu_translate_file(**arguments)
        return result.to_dict()

    if name == "yanfu_translate_files":
        from .api import yanfu_translate_files

        result = yanfu_translate_files(**arguments)
        return result.to_dict()

    raise ValueError(f"Unknown tool: {name}")
