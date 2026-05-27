"""YanFu - Download surya/marker models from ModelScope.

For mainland China users who cannot access models.datalab.to.
Downloads surya model files from ModelScope mirrors and places them
in the correct cache directory.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from huggingface_hub.utils import tqdm

logger = logging.getLogger("yanfu")

# ModelScope model IDs for surya components
SURYA_MODELSCOPE_MODELS = {
    "layout": {
        "model_id": "datalab/surya_layout",
        "revision": "master",
        "cache_subdir": "layout/2025_09_23",
        "description": "Layout detection model",
    },
    "recognition": {
        "model_id": "datalab/surya_recognition",
        "revision": "master",
        "cache_subdir": "text_recognition/2025_09_23",
        "description": "Text recognition model",
    },
    "detection": {
        "model_id": "datalab/surya_detection",
        "revision": "master",
        "cache_subdir": "text_detection/2025_05_07",
        "description": "Text detection model",
    },
    "table_rec": {
        "model_id": "datalab/surya_table_rec",
        "revision": "master",
        "cache_subdir": "table_recognition/2025_02_18",
        "description": "Table recognition model",
    },
    "ocr_error": {
        "model_id": "datalab/surya_ocr_error",
        "revision": "master",
        "cache_subdir": "ocr_error_detection/2025_02_18",
        "description": "OCR error detection model",
    },
}


def get_surya_cache_dir() -> Path:
    """Get surya model cache directory."""
    from platformdirs import user_cache_dir
    return Path(user_cache_dir("datalab")) / "models"


def download_surya_from_modelscope(
    progress_callback=None,
    force: bool = False,
) -> tuple[bool, str]:
    """Download all surya models from ModelScope mirrors.

    Args:
        progress_callback: Optional callback(current, total, message).
        force: Force re-download even if cached.

    Returns:
        Tuple of (success, message).
    """
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        return False, "ModelScope not installed. Run: pip install modelscope"

    cache_dir = get_surya_cache_dir()
    total_models = len(SURYA_MODELSCOPE_MODELS)
    downloaded = 0
    skipped = 0
    failed = []

    print("\n" + "=" * 60)
    print("[YanFu] Downloading surya models from ModelScope...")
    print(f"[YanFu] Cache: {cache_dir}")
    print("=" * 60)

    for i, (name, info) in enumerate(SURYA_MODELSCOPE_MODELS.items(), 1):
        target_dir = cache_dir / info["cache_subdir"]
        msg = f"[{i}/{total_models}] {info['description']}"

        if progress_callback:
            progress_callback(i, total_models, msg)

        print(f"\n{msg}")
        print(f"  ModelScope: {info['model_id']}")
        print(f"  Cache:      {target_dir}")

        # Check if already downloaded
        if target_dir.exists() and any(target_dir.iterdir()) and not force:
            print(f"  ✓ Already cached")
            skipped += 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Download from ModelScope
            # Use environment variable for HF mirror compatibility
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

            snapshot_download(
                model_id=info["model_id"],
                revision=info["revision"],
                cache_dir=str(target_dir),
                local_dir=str(target_dir),
            )
            print(f"  ✓ Downloaded successfully")
            downloaded += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed.append(name)

    print("\n" + "=" * 60)
    summary = f"Downloaded: {downloaded}, Cached: {skipped}"
    if failed:
        summary += f", Failed: {len(failed)} ({', '.join(failed)})"
    print(f"[YanFu] {summary}")
    print("=" * 60)

    if failed:
        return False, f"Partial download: {summary}"
    return True, f"All models ready: {summary}"


def download_surya_via_marker(
    progress_callback=None,
) -> tuple[bool, str]:
    """Download surya models using marker-pdf's built-in downloader.

    Tries ModelScope first (HF_ENDPOINT=hf-mirror.com), falls back
    to direct download from models.datalab.to.

    Args:
        progress_callback: Optional callback(current, total, message).

    Returns:
        Tuple of (success, message).
    """
    # Use HF mirror for mainland China
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

    # Enable progress bars
    from huggingface_hub.utils import enable_progress_bars
    enable_progress_bars()

    print("\n" + "=" * 60)
    print("[YanFu] Downloading marker-pdf/surya models...")
    print("[YanFu] Using HF mirror: https://hf-mirror.com")
    print("=" * 60)
    print()

    try:
        from marker.models import create_model_dict

        if progress_callback:
            progress_callback(0, 100, "Loading marker-pdf models...")

        artifact_dict = create_model_dict()

        print("\n[YanFu] ✅ All models loaded successfully!")
        print("=" * 60)
        return True, "Models loaded successfully"
    except Exception as e:
        print(f"\n[YanFu] ❌ Download failed: {e}")
        print(f"[YanFu] Try downloading from ModelScope manually:")
        print(f"  pip install modelscope")
        print(f"  python -m yanfu.download_models --modelscope")
        return False, str(e)
