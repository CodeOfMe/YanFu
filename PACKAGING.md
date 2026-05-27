# YanFu Packaging Guide

This guide explains how to package YanFu into standalone installers (MSI/DMG/AppImage) with bundled models.

## Overview

YanFu uses [Briefcase](https://briefcase.readthedocs.io/) for packaging. The installers include:
- All Python dependencies
- PySide6 GUI
- Pre-downloaded GGUF models
- No internet connection required after installation

## Prerequisites

```bash
pip install briefcase
```

## Quick Start

### Build MSI (Windows)

```bash
# Download default model and build MSI
./scripts/build_msi.sh

# Or specify a model
./scripts/build_msi.sh qwen3:0.6b

# Windows batch file
scripts\build_msi.bat gemma3:1b
```

### Build DMG (macOS)

```bash
briefcase create macOS dmg
briefcase build macOS dmg
briefcase package macOS dmg
```

### Build AppImage (Linux)

```bash
briefcase create linux appimage
briefcase build linux appimage
briefcase package linux appimage
```

## Model Bundling

Models are bundled in the `models/` directory:

```
models/
├── gemma3:1b/
│   └── gemma-3-1b-it-Q4_K_M.gguf
└── qwen3:0.6b/
    └── qwen3-0.6b-q4_k_m.gguf
```

### Download Models

```bash
# Download default model
python scripts/bundle_models.py

# Download all models
python scripts/bundle_models.py --all

# Download specific model
python scripts/bundle_models.py --model qwen3:0.6b

# List bundled models
python scripts/bundle_models.py --list

# Cleanup
python scripts/bundle_models.py --cleanup
```

## Installer Size

| Model | Installer Size |
|-------|----------------|
| gemma3:1b | ~850MB |
| qwen3:0.6b | ~500MB |
| qwen3:1.8b | ~1.2GB |

## Post-Installation

After installation, YanFu:
1. Checks for bundled models in the installation directory
2. Falls back to `~/.cache/yanfu/models/` if not bundled
3. Downloads models on first use if not found

### Environment Variables

- `YANFU_MODEL_DIR`: Override model directory path

## Troubleshooting

### MSI build fails on Windows

Ensure you have:
- Windows 10/11
- Python 3.10+ installed
- Briefcase installed: `pip install briefcase`

### Model not found after installation

Check the model directory:
```python
from yanfu.translator import BUNDLED_MODELS_DIR, ModelManager

print(f"Bundled models: {BUNDLED_MODELS_DIR}")
mm = ModelManager()
print(f"Downloaded: {mm.list_downloaded_models()}")
```

### Large installer size

Use a smaller model:
```bash
./scripts/build_msi.sh qwen3:0.6b
```

## Briefcase Configuration

See `pyproject.toml` for Briefcase settings:

```toml
[tool.briefcase.app.yanfu.windows]
bundles_models = true
model_dir = "models"
installer_type = "msi"
output_format = "msi"
```

## Release Checklist

- [ ] Run tests: `pytest tests/ -v`
- [ ] Lint: `ruff check src/yanfu/`
- [ ] Download models: `python scripts/bundle_models.py --model gemma3:1b`
- [ ] Build installer: `./scripts/build_msi.sh`
- [ ] Test installer on clean machine
- [ ] Verify offline functionality
- [ ] Create GitHub release
