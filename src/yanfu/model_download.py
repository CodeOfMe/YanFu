"""YanFu - Download surya/marker models.

Downloads model files from models.datalab.to (HTTP, works from China)
and places them in the correct surya cache directory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests
from huggingface_hub.utils import tqdm

logger = logging.getLogger("yanfu")

# Model definitions with their S3 paths
SURYA_MODELS = {
    "layout": {
        "path": "layout/2025_09_23",
        "files": [
            "model.safetensors",
            "config.json",
            "preprocessor_config.json",
            "tokenizer_config.json",
            "vocab_math.json",
            "special_tokens_map.json",
            "specials_dict.json",
        ],
        "desc": "Layout detection (~1.4GB)",
    },
    "recognition": {
        "path": "text_recognition/2025_09_23",
        "files": [
            "model.safetensors",
            "config.json",
            "preprocessor_config.json",
            "tokenizer_config.json",
            "vocab_math.json",
            "special_tokens_map.json",
            "specials_dict.json",
        ],
        "desc": "Text recognition (~1.4GB)",
    },
    "detection": {
        "path": "text_detection/2025_05_07",
        "files": [
            "model.safetensors",
            "config.json",
            "preprocessor_config.json",
        ],
        "desc": "Text detection (~100MB)",
    },
    "table_rec": {
        "path": "table_recognition/2025_02_18",
        "files": [
            "model.safetensors",
            "config.json",
            "generation_config.json",
        ],
        "desc": "Table recognition (~500MB)",
    },
    "ocr_error": {
        "path": "ocr_error_detection/2025_02_18",
        "files": [
            "model.safetensors",
            "config.json",
        ],
        "desc": "OCR error detection (~300MB)",
    },
}

BASE_URL = "https://models.datalab.to"


def get_surya_cache_dir() -> Path:
    """Get surya model cache directory."""
    from platformdirs import user_cache_dir
    return Path(user_cache_dir("datalab")) / "models"


def download_surya_models(
    progress_callback=None,
    force: bool = False,
) -> tuple[bool, str]:
    """Download all surya models directly via HTTP.

    Downloads from https://models.datalab.to and saves to the
    platform-appropriate cache directory.

    Args:
        progress_callback: Optional callback(current, total, message).
        force: Force re-download even if cached.

    Returns:
        Tuple of (success, message).
    """
    cache_dir = get_surya_cache_dir()
    total_models = len(SURYA_MODELS)
    downloaded = 0
    skipped = 0
    failed_models = []

    print("\n" + "=" * 60)
    print("[YanFu] Downloading surya/marker models")
    print(f"[YanFu] Cache: {cache_dir}")
    print(f"[YanFu] Source: {BASE_URL}")
    print("=" * 60)

    for i, (name, info) in enumerate(SURYA_MODELS.items(), 1):
        target_dir = cache_dir / info["path"]
        msg = f"[{i}/{total_models}] {info['desc']}"

        if progress_callback:
            progress_callback(i, total_models, msg)

        print(f"\n{msg}")
        print(f"  Target: {target_dir}")

        # Check cache
        if target_dir.exists() and not force:
            existing = list(target_dir.glob("model.*"))
            if existing:
                size_mb = sum(f.stat().st_size for f in existing) / 1024 / 1024
                print(f"  ✓ Already cached ({size_mb:.0f}MB)")
                skipped += 1
                continue

        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            for filename in info["files"]:
                url = f"{BASE_URL}/{info['path']}/{filename}"
                filepath = target_dir / filename
                print(f"  Download: {filename}", end="", flush=True)
                _download_file(url, filepath)
                size_mb = filepath.stat().st_size / 1024 / 1024
                print(f" ({size_mb:.0f}MB)")

            print(f"  ✓ Downloaded successfully")
            downloaded += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed_models.append(name)

    print("\n" + "=" * 60)
    summary = f"Downloaded: {downloaded}, Cached: {skipped}"
    if failed_models:
        summary += f", Failed: {len(failed_models)} ({', '.join(failed_models)})"
    print(f"[YanFu] {summary}")
    print(f"[YanFu] Cache: {cache_dir}")
    print("=" * 60)

    if failed_models:
        return False, f"Partial download: {summary}"
    return True, f"All models ready in {cache_dir}"


def _download_file(url: str, filepath: Path, chunk_size: int = 8 * 1024 * 1024):
    """Download a file with progress bar."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "wb") as f:
        with tqdm(total=total, unit="B", unit_scale=True, unit_divisor=1024, desc="  ") as pbar:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                pbar.update(len(chunk))


def ensure_marker_models(progress_callback=None) -> tuple[bool, str]:
    """Ensure marker-pdf models are available (download if needed).
    
    First checks cache, then downloads from models.datalab.to.
    After download, verifies marker can load the models.
    
    Returns:
        Tuple of (success, message).
    """
    # Step 1: Download model files
    success, msg = download_surya_models(progress_callback=progress_callback)
    if not success:
        return False, msg

    # Step 2: Verify marker can load them
    if progress_callback:
        progress_callback(0, 1, "Verifying marker can load models...")
    
    try:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from marker.models import create_model_dict
        create_model_dict()
        return True, "Models downloaded and verified"
    except Exception as e:
        return False, f"Models downloaded but marker failed to load: {e}"
