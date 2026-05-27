#!/usr/bin/env python3
"""Download and bundle models for MSI/DMG packaging.

This script downloads GGUF models to the models/ directory
so they can be bundled in the installer.

Usage:
    python scripts/bundle_models.py              # Download default model
    python scripts/bundle_models.py --all        # Download all models
    python scripts/bundle_models.py --model gemma3:1b
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from yanfu.translator import MODEL_DEFINITIONS, ModelManager


def download_model(model_name: str, output_dir: Path) -> Path:
    """Download a model to the specified directory.

    Args:
        model_name: Model identifier.
        output_dir: Directory to save the model.

    Returns:
        Path to downloaded model.
    """
    model_dir = output_dir / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    mm = ModelManager(cache_dir=output_dir)

    if mm.is_model_downloaded(model_name):
        print(f"[Bundle] Model '{model_name}' already exists in {model_dir}")
        return mm.get_model_path(model_name)

    print(f"[Bundle] Downloading '{model_name}' to {model_dir}...")
    print(f"[Bundle] Size: ~{MODEL_DEFINITIONS[model_name]['size_mb']}MB")

    try:
        path = mm.download_model(model_name)
        print(f"[Bundle] Downloaded: {path}")
        return path
    except Exception as e:
        print(f"[Bundle] Error downloading '{model_name}': {e}")
        raise


def get_model_size(path: Path) -> float:
    """Get model file size in MB.

    Args:
        path: Path to model file.

    Returns:
        Size in MB.
    """
    if path.exists():
        return path.stat().st_size / 1024 / 1024
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Bundle models for packaging")
    parser.add_argument(
        "--model",
        default="gemma3:1b",
        help="Model to download (default: gemma3:1b)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all available models",
    )
    parser.add_argument(
        "--output",
        default="models",
        help="Output directory for models (default: models/)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove downloaded models",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List bundled models",
    )

    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.list:
        if not output_dir.exists():
            print("No models directory found.")
            return

        print("Bundled models:")
        for model_dir in output_dir.iterdir():
            if model_dir.is_dir():
                for gguf in model_dir.glob("*.gguf"):
                    size = get_model_size(gguf)
                    print(f"  {model_dir.name}/{gguf.name} ({size:.0f}MB)")
        return

    if args.cleanup:
        if output_dir.exists():
            shutil.rmtree(output_dir)
            print(f"Removed {output_dir}")
        else:
            print("No models directory found.")
        return

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download models
    if args.all:
        models_to_download = list(MODEL_DEFINITIONS.keys())
    else:
        models_to_download = [args.model]

    total_size = 0
    for model_name in models_to_download:
        if model_name not in MODEL_DEFINITIONS:
            print(f"Error: Unknown model '{model_name}'")
            print(f"Available: {list(MODEL_DEFINITIONS.keys())}")
            sys.exit(1)

        try:
            path = download_model(model_name, output_dir)
            total_size += get_model_size(path)
        except Exception as e:
            print(f"Failed to download '{model_name}': {e}")
            sys.exit(1)

    print(f"\n[Bundle] Summary:")
    print(f"  Models downloaded: {len(models_to_download)}")
    print(f"  Total size: {total_size:.0f}MB ({total_size / 1024:.1f}GB)")
    print(f"  Location: {output_dir.absolute()}")
    print(f"\n[Bundle] Models are ready for packaging!")


if __name__ == "__main__":
    main()
