# YanFu

PDF/CAJ document translator with layout-preserving PDF generation using Ollama or OpenAI-compatible APIs.

**Simple setup**: Install once, configure your translation provider, and translate. Supports local Ollama, OpenAI, and any OpenAI-compatible endpoint.

## Features

- **Flexible Translation Providers**: Use local Ollama, OpenAI cloud, or any OpenAI-compatible API (vLLM, LM Studio, etc.)
- **Dynamic Model Discovery**: Automatically fetches available models from your configured provider — no hardcoded model lists
- **Multi-format Support**: Parse PDF and CAJ (Chinese Academic Journal) files
- **Layout Preservation**: Generate PDF output with preserved layout, images, and formulas using marker-pdf
- **OCR Support**: Handle scanned documents with built-in OCR
- **Batch Processing**: Process multiple files or entire directories
- **GUI & CLI**: Beautiful PySide6 graphical interface and command-line interface
- **Python API**: Clean API with ToolResult pattern for programmatic usage
- **Configuration Wizard**: Interactive setup guide for first-time users

## Requirements

- Python 3.10+
- macOS / Linux / Windows
- Ollama (for local translation) or OpenAI API key (for cloud translation)
- CPU-friendly: All document parsing runs efficiently on CPU

## Installation

```bash
# Install with all dependencies (recommended)
pip install yanfu

# Development extras
pip install yanfu[dev]
```

That's it! All core dependencies including PySide6 GUI, marker-pdf OCR, and document parsers are included.

## Quick Start

### Step 1: Configure Your Translation Provider

Run the interactive configuration wizard:

```bash
yanfu --config
```

Or configure via the GUI Settings dialog. Supported providers:

| Provider | Setup | Cost |
|----------|-------|------|
| **Ollama** (Local) | `ollama pull qwen3:0.6b` | Free |
| **OpenAI** (Cloud) | API key required | Pay-per-use |
| **Custom** | Any OpenAI-compatible endpoint | Varies |

### Step 2: Translate

#### GUI Application

```bash
yanfu --gui
```

The GUI features:
- **Side-by-side view**: Original PDF on the left, translation on the right
- **Synchronized scrolling**: Toggle sync to navigate both panels together
- **Separate threads**: PDF parsing and translation run in background threads — UI stays responsive
- **Save options**: Export as Markdown or translated PDF

#### CLI

```bash
# Translate a PDF to Chinese
yanfu paper.pdf -l zh

# Translate to Japanese
yanfu paper.pdf -l ja

# Translate multiple files
yanfu paper1.pdf paper2.pdf -l fr

# Batch process a directory
yanfu ./papers --batch -l es

# Verbose output with detailed logs
yanfu paper.pdf -v

# JSON output
yanfu paper.pdf --json

# List available models from your configured provider
yanfu --list-models

# Test connection to your provider
yanfu --test-connection
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--gui` | Launch graphical interface |
| `--config` | Run configuration wizard |
| `--test-connection` | Test provider connection |
| `--list-models` | List available models from provider |
| `--reset-config` | Reset configuration to defaults |
| `-V`, `--version` | Show version |
| `-v`, `--verbose` | Enable verbose output |
| `-o`, `--output` | Output directory |
| `--json` | JSON output format |
| `-q`, `--quiet` | Suppress non-essential output |
| `-l`, `--lang` | Target language (default: en) |
| `--source-lang` | Source language (default: auto) |
| `--use-ocr` | Enable OCR for scanned docs |
| `--engine` | PDF parser (auto/pymupdf/marker/pdfplumber) |
| `--temperature` | Translation temperature (0.0-1.0) |
| `--batch` | Batch process directory |
| `--list-langs` | List supported languages |

## Supported Languages

| Code | Language | Code | Language |
|------|----------|------|----------|
| en | English | zh | Chinese (Simplified) |
| zh-Hant | Chinese (Traditional) | ja | Japanese |
| ko | Korean | fr | French |
| de | German | es | Spanish |
| ru | Russian | it | Italian |
| pt | Portuguese | ar | Arabic |
| hi | Hindi | th | Thai |
| vi | Vietnamese | | |

## Python API

```python
from yanfu import yanfu_translate_file, ToolResult

# Translate a single file
result = yanfu_translate_file(
    input_path="paper.pdf",
    target_lang="zh",
)

print(result.success)    # True / False
print(result.data)       # Output paths and metadata
print(result.metadata)   # Version and timing info
```

### Batch Processing

```python
from yanfu import yanfu_translate_files

result = yanfu_translate_files(
    input_paths=["paper1.pdf", "paper2.caj"],
    target_lang="ja",
    use_ocr=True,
)

for r in result.data["results"]:
    print(f"{r['file']}: {'OK' if r['success'] else 'Failed'}")
```

### Configuration Management

```python
from yanfu.translator import ConfigManager

config = ConfigManager()

# Check if configured
if not config.is_configured():
    print("Run 'yanfu --config' to set up")

# Modify settings
config.set("provider", "ollama")
config.set("model", "qwen3:0.6b")
config.set("base_url", "http://localhost:11434")
config.save_config()

# Reset to defaults
config.reset()
```

## Architecture

YanFu uses a clean multi-threaded architecture:

```
┌─────────────────────────────────────────────────────┐
│                    GUI (Main Thread)                  │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  PDF Viewer   │    │    Translation Editor     │   │
│  │  (PyMuPDF)    │    │    (QTextEdit)            │   │
│  └──────────────┘    └──────────────────────────┘   │
└─────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│  ParseWorker     │          │  TranslateWorker      │
│  (Background)    │          │  (Background)         │
│  - PDF parsing   │          │  - API calls          │
│  - Image extract │          │  - Chunk translation  │
│  - Markdown gen  │          │  - PDF rendering      │
└─────────────────┘          └──────────────────────┘
```

- **ParseWorker**: Extracts text, images, and formulas from PDF using marker-pdf or PyMuPDF
- **TranslateWorker**: Sends text chunks to Ollama/OpenAI API, assembles results, renders PDF
- **UI Thread**: Remains responsive — no blocking during parsing or translation

## Development

```bash
# Clone and install for development
git clone https://github.com/CodeOfMe/YanFu.git
cd YanFu
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint and format
ruff check .
ruff format .
```

## License

GPL-3.0-or-later

## See Also

- [NuoYi](https://github.com/cycleuser/NuoYi) - PDF/DOCX to Markdown converter
- [TransPaste](https://github.com/CodeOfMe/TransPaste) - Local LLM clipboard translator
