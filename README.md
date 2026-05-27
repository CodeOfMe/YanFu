# YanFu (言附)

**PDF/CAJ document translator with layout-preserving PDF generation using Ollama or OpenAI-compatible APIs.**

![](https://img.shields.io/badge/python-3.10+-blue) ![](https://img.shields.io/badge/license-GPL--3.0-green)

---

## Features

- **14 PDF parsers**: marker, docling (default), mineru, easyocr, doctr, nougat, pymupdf, pdfplumber, llamaparse, mathpix, mineru-cloud, doc2x, and auto mode
- **Flexible translation**: local Ollama, OpenAI, or any OpenAI-compatible endpoint
- **Dynamic model discovery**: auto-fetches available models from your provider
- **Three-panel GUI**: original PDF | parsed markdown | translated output — all resizable
- **Rendered + plain view**: toggle between formatted HTML (tables, headings, code) and raw markdown
- **Synchronized scrolling**: PDF and translation scroll together (toggleable)
- **Background threads**: parsing and translation never block the UI
- **CLI + Python API**: `yanfu paper.pdf -l zh` or `from yanfu import yanfu_translate_file`
- **Config wizard**: `yanfu --config` guides first-time setup

---

## Requirements

- Python 3.10+
- Windows / macOS / Linux
- **Ollama** (free, local) or **OpenAI API key** (cloud)
- Disk: ~3GB for marker models, ~1.5GB for docling, or 0 for pymupdf/pdfplumber

---

## Installation

```bash
pip install yanfu
```

All 14 engines and GUI dependencies are included. No extra `[gui]` or `[all]` needed.

```bash
# Verify installation
yanfu --version
```

---

## Quick Start

### 1. Configure your provider

```bash
yanfu --config
```

Choose provider → select model → pick engine. Defaults: **Ollama + gemma3:1b + docling**.

Or pull models manually:

```bash
ollama pull gemma3:1b        # Default model
ollama pull qwen2.5:1.5b     # Better for Chinese
ollama pull qwen2.5:7b       # Best quality
```

### 2. Launch the GUI

```bash
yanfu --gui
```

### 3. Translate

| Step | Button | What happens |
|------|--------|-------------|
| Open PDF | 📂 Open PDF | Load PDF into left panel |
| Parse | 📄 Parse PDF | Extract text (middle panel shows markdown) |
| Translate | ▶ Translate | Translate parsed text (right panel shows result) |
| Save | 💾 Save MD / 💾 Save PDF | Export translation |

**Or one-click**: open PDF → click ▶ Translate (auto-parses, then translates).

### 4. CLI

```bash
# Translate to Chinese
yanfu paper.pdf -l zh

# Translate to Japanese
yanfu paper.pdf -l ja

# Use specific engine
yanfu paper.pdf --engine marker -l zh

# Batch directory
yanfu ./papers --batch -l es -v

# JSON output
yanfu paper.pdf --json
```

---

## GUI Walkthrough

```
┌────────────────┬─────────────────────┬─────────────────────┐
│  📄 Original   │  📝 Parsed Markdown │  🌐 Translation     │
│  ┌──────────┐  │  🔄Plain ✕Clear    │  🔗Sync 🔄Plain ✕   │
│  │          │  │  📄Parse ▶Translate │  ▶Translate 💾Save  │
│  │   PDF    │  │  ┌──────────────┐   │  ┌──────────────┐   │
│  │  Viewer  │  │  │ Rendered or  │   │  │ Rendered or  │   │
│  │          │  │  │ Plain text   │   │  │ Plain text   │   │
│  │          │  │  │              │   │  │              │   │
│  └──────────┘  │  └──────────────┘   │  └──────────────┘   │
│  ◀ page 1/11▶ │  Tables in tables   │  ### 方法          │
│                │  |col1|col2|        │  |列1|列2|          │
│                │  [Formula]          │  [公式]             │
└────────────────┴─────────────────────┴─────────────────────┘
│  Status: Parsing PDF...   Progress: [████████░░] 80%      │
└──────────────────────────────────────────────────────────┘
```

### Panels

| Panel | Content | Actions |
|-------|---------|--------|
| Left | PDF viewer with page navigation | Open, prev/next page |
| Middle | Parsed markdown (rendered or plain) | Parse, Clear, toggle view |
| Right | Translated markdown (rendered or plain) | Translate, Clear, Save, toggle view |

### Toolbar

- 📂 Open PDF
- ▶ Translate
- 💾 Save (Markdown or PDF)
- 🔗 Sync Scroll (toggle)

### Settings

**File → Settings** (Ctrl+,):

| Section | Options |
|---------|---------|
| Translation Provider | Provider (Ollama/OpenAI/Custom), Base URL, API Key, Model |
| Model list | Refresh Models, Test Connection |
| PDF Parsing Engine | 14 engines with availability status (green ✓ / red ✗) |
| Device | Auto / CPU / CUDA / Apple MPS / DirectML(Vulkan) |
| Download / Re-download | Download models for selected engine (Force clears cache) |
| Translation Settings | Source/Target language, Temperature |
| Output Settings | Page size, Font size, Margin |

---

## PDF Parsing Engines (14 total)

| Engine | Type | Models | OCR | Best For |
|--------|------|--------|:---:|----------|
| **docling** (default) | Local | ~1.5GB | ✓ | Balanced quality/speed, good tables |
| **marker** | Local | ~3GB | ✓ | Best overall: layout + OCR + images + formulas |
| **mineru** | Local | ~1.5GB | ✓ | Chinese documents |
| **easyocr** | Local | ~300MB | ✓ | 80+ languages, lightweight |
| **doctr** | Local | ~500MB | ✓ | Rotated text, lightweight |
| **nougat** | Local | ~1.5GB | ✓ | Academic papers |
| **pymupdf** | Local | None | ✗ | Fastest, digital PDFs |
| **pdfplumber** | Local | None | ✗ | Table extraction |
| **llamaparse** | Cloud | Cloud | ✓ | Excellent quality (LlamaCloud key) |
| **mathpix** | Cloud | Cloud | ✓ | Math/STEM formulas |
| **mineru-cloud** | Cloud | Cloud | ✓ | Chinese docs (API key) |
| **doc2x** | Cloud | Cloud | ✓ | Best formula LaTeX output |
| **auto** | N/A | N/A | - | Auto-selects best available |

**Formula tip**: For PDFs with heavy math, use **Marker** or **Doc2X**.

---

## CLI Reference

```
yanfu [OPTIONS] [input ...]

Options:
  --gui              Launch graphical interface
  --config           Run configuration wizard
  --test-connection  Test provider connection
  --list-models      List models from provider
  --reset-config     Reset to defaults
  -V, --version      Show version
  -v, --verbose      Detailed output
  -o, --output DIR   Output directory
  --json             JSON output
  -l, --lang CODE    Target language (default: en)
  --source-lang CODE Source language (default: auto)
  --engine ENGINE    PDF parser (docling/marker/pymupdf/...)
  --temperature FLOAT Translation temperature (0.0-1.0)
  --batch            Batch process directory
  --list-langs       List supported languages
```

### Languages

| Code | Language | Code | Language |
|------|----------|------|----------|
| en | English | zh | Chinese (Simplified) |
| zh-Hant | Chinese (Traditional) | ja | Japanese |
| ko | Korean | fr | French |
| de | German | es | Spanish |
| ru | Russian | ar | Arabic |
| hi | Hindi | th | Thai |
| vi | Vietnamese | it | Italian |
| pt | Portuguese | | |

---

## Python API

```python
from yanfu import yanfu_translate_file, ToolResult
from yanfu.translator import ConfigManager

# Configure
config = ConfigManager()
config.set("provider", "ollama")
config.set("model", "gemma3:1b")
config.save_config()

# Translate
result = yanfu_translate_file("paper.pdf", target_lang="zh", config=config)
print(result.data["output_pdf"])  # Path to translated PDF
```

### Batch

```python
from yanfu import yanfu_translate_files

result = yanfu_translate_files(
    ["paper1.pdf", "paper2.pdf"],
    target_lang="ja",
    config=config,
)
for r in result.data["results"]:
    print(r["file"], "✓" if r["success"] else "✗")
```

---

## Model Download

### Auto-download

Engines auto-download models on first use (terminal shows tqdm progress bars). You can pre-download in Settings:

1. Settings → select engine → click **⬇ Download Selected Engine Models**
2. Terminal shows download progress and cache location
3. Click **🔄 Re-download (Force)** to clear cache and re-download

### Cache locations

| Engine | Cache Path |
|--------|-----------|
| marker | `~/.cache/datalab/models/` (Linux/Mac) or `%LOCALAPPDATA%\datalab\models\` (Windows) |
| docling / doctr | `~/.cache/huggingface/hub/` |
| easyocr | `<easyocr_package>/model/` |
| pymupdf / pdfplumber | No cache needed |

---

## China Mirror / ModelScope

YanFu defaults to `HF_ENDPOINT=https://hf-mirror.com` for HuggingFace downloads. Marker/surya models download from `https://models.datalab.to` (accessible from China).

For engines that need HuggingFace models (docling, doctr), the mirror is used automatically.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: PySide6` | `pip install yanfu` (includes all deps) |
| Translation empty | Check Ollama: `ollama list` → model installed? Try larger model |
| "No extractable text" | PDF is image-based: use EasyOCR or Marker engine |
| Docling formulas missing | Use Marker engine for formulas, or Doc2X cloud |
| QThread crash | Update to latest version (`git pull`) |
| Download hangs | Use Settings → Re-download (Force) to clear cache |
| Model path unknown | Terminal prints cache path during download |

---

## Development

```bash
git clone https://github.com/CodeOfMe/YanFu.git
cd YanFu
pip install -e ".[dev]"
pytest tests/ -v
ruff check .
```

---

## License

GPL-3.0-or-later
