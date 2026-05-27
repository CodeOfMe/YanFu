# YanFu

PDF/CAJ document translator with layout-preserving PDF generation using local LLMs.

**Zero-configuration**: Install once, run immediately. Models auto-download on first use.

## Features / 功能特性

- **Zero-Config Setup**: `pip install yanfu` then run. No Ollama, no API keys, no external services.
- **Auto-Download Models**: GGUF models download automatically from ModelScope/HuggingFace on first run.
- **Multi-format Support**: Parse PDF and CAJ (Chinese Academic Journal) files.
- **Local LLM Translation**: Translate using GGUF models (gemma3:1b, qwen3:0.6b) via llama-cpp-python.
- **Layout Preservation**: Generate PDF output with preserved layout, images, and formulas.
- **OCR Support**: Handle scanned documents with OCR.
- **Batch Processing**: Process multiple files or entire directories.
- **CLI & API**: Command-line interface and Python API with ToolResult pattern.
- **Agent Integration**: OpenAI function-calling tools for LLM agents.

- **零配置**：`pip install yanfu` 后即可运行。无需 Ollama、无需 API 密钥、无需外部服务。
- **自动下载模型**：GGUF 模型在首次运行时自动从 ModelScope/HuggingFace 下载。
- **多格式支持**：解析 PDF 和 CAJ（中国学术期刊）文件。
- **本地大模型翻译**：使用 GGUF 模型（gemma3:1b、qwen3:0.6b）通过 llama-cpp-python 翻译。
- **排版保留**：生成保留排版、图片和公式的 PDF 输出。
- **OCR 支持**：处理扫描文档。
- **批量处理**：处理多个文件或整个目录。
- **CLI 和 API**：命令行界面和带有 ToolResult 模式的 Python API。
- **智能体集成**：用于 LLM 智能体的 OpenAI 函数调用工具。

## Requirements / 系统要求

- Python 3.10+
- macOS / Linux / Windows
- CPU only (GGUF models run on CPU, no GPU required)
- ~1GB disk space for model

## Installation / 安装

```bash
# Basic installation (includes all dependencies)
pip install yanfu

# With OCR support
pip install yanfu[ocr]

# Full installation
pip install yanfu[all]
```

That's it! No additional setup needed. Models will auto-download on first run.

## Quick Start / 快速开始

### GUI Application / 图形界面

```bash
# Launch GUI
yanfu --gui

# Or with PySide6 installed
pip install yanfu[gui]
yanfu --gui
```

### CLI / 命令行

```bash
# Translate a PDF to English (model downloads automatically on first run)
yanfu paper.pdf

# Translate to Chinese
yanfu paper.pdf -l zh

# Translate to Japanese with faster model
yanfu paper.pdf -l ja --model qwen3:0.6b

# Translate multiple files
yanfu paper1.pdf paper2.pdf -l fr

# Batch process a directory
yanfu ./papers --batch -l es

# Verbose output
yanfu paper.pdf -v

# JSON output
yanfu paper.pdf --json
```

## Usage / 使用方法

### CLI Flags / 命令行参数

| Flag | Description |
|------|-------------|
| `-V`, `--version` | Show version |
| `-v`, `--verbose` | Enable verbose output |
| `-o`, `--output` | Output directory |
| `--json` | JSON output format |
| `-q`, `--quiet` | Suppress non-essential output |
| `-l`, `--lang` | Target language (default: en) |
| `--source-lang` | Source language (default: auto) |
| `--model` | Translation model (default: gemma3:1b) |
| `--model-path` | Direct path to GGUF file |
| `--cache-dir` | Model cache directory |
| `--use-ocr` | Enable OCR for scanned docs |
| `--engine` | PDF parser (auto/pymupdf/marker/pdfplumber) |
| `--temperature` | Translation temperature (0.0-1.0) |
| `--batch` | Batch process directory |
| `--list-langs` | List supported languages |
| `--list-models` | List available models |
| `--download-model` | Download a model without translating |
| `--list-downloaded` | List downloaded models |
| `--cleanup-models` | Remove all downloaded models |

### Translation Models / 翻译模型

| Model | Size | Quality | Speed |
|-------|------|---------|-------|
| gemma3:1b | ~780MB | Good | Medium |
| qwen3:0.6b | ~420MB | Basic | Fast |
| qwen3:1.8b | ~1.1GB | Best | Slow |

Models are stored in `~/.cache/yanfu/models/` after download.

### Supported Languages / 支持的语言

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

## Standalone Installer / 独立安装包

### Windows MSI

Download the MSI installer for a complete offline experience:

```bash
# Build MSI with bundled model
./scripts/build_msi.sh

# Or on Windows
scripts\build_msi.bat gemma3:1b
```

The MSI installer includes:
- All dependencies
- PySide6 GUI
- Pre-downloaded GGUF model (~780MB)
- No internet required after installation

### macOS DMG / Linux AppImage

```bash
briefcase create macOS dmg && briefcase build macOS dmg && briefcase package macOS dmg
briefcase create linux appimage && briefcase build linux appimage && briefcase package linux appimage
```

See [PACKAGING.md](PACKAGING.md) for detailed instructions.

## Python API

```python
from yanfu import yanfu_translate_file, ToolResult

# Translate a single file (model auto-downloads on first use)
result = yanfu_translate_file(
    input_path="paper.pdf",
    target_lang="zh",
    model_name="gemma3:1b",
)

print(result.success)    # True / False
print(result.data)       # Output paths and metadata
print(result.metadata)   # Version and timing info
```

### Batch Processing / 批量处理

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

### Model Management / 模型管理

```python
from yanfu.translator import ModelManager

mm = ModelManager()

# List downloaded models
print(mm.list_downloaded_models())

# Download a specific model
mm.download_model("qwen3:0.6b")

# Check if model exists
print(mm.is_model_downloaded("gemma3:1b"))

# Cleanup to free disk space
mm.cleanup()  # Remove all models
mm.cleanup("qwen3:0.6b")  # Remove specific model
```

## Agent Integration / 智能体集成

YanFu provides OpenAI function-calling tools for LLM agent integration:

```python
from yanfu.tools import TOOLS, dispatch

# TOOLS contains the function schema for OpenAI API
# dispatch() routes tool calls to the appropriate function

# Example with OpenAI API
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Translate this PDF to Chinese"}],
    tools=TOOLS,
)

# Dispatch the tool call
tool_call = response.choices[0].message.tool_calls[0]
result = dispatch(tool_call.function.name, tool_call.function.arguments)
```

## CLI Help / 命令行帮助

```
$ yanfu --help
usage: yanfu [-h] [-V] [-v] [-o OUTPUT] [--json] [-q] [-l LANG]
             [--source-lang SOURCE_LANG] [--model MODEL] [--model-path MODEL_PATH]
             [--cache-dir CACHE_DIR] [--use-ocr] [--engine ENGINE]
             [--temperature TEMPERATURE] [--page-size PAGE_SIZE]
             [--font FONT] [--font-size FONT_SIZE] [--margin MARGIN] [--batch]
             [--list-langs] [--list-models] [--download-model MODEL]
             [--list-downloaded] [--cleanup-models]
             [input ...]

YanFu - Translate PDF/CAJ documents using local LLMs (zero-configuration)
```

## Development / 开发

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

## License / 许可证

GPL-3.0-or-later

## See Also / 参见

- [NuoYi](https://github.com/cycleuser/NuoYi) - PDF/DOCX to Markdown converter
- [TransPaste](https://github.com/CodeOfMe/TransPaste) - Local LLM clipboard translator
