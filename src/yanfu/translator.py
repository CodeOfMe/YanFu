"""YanFu - Local LLM translation using GGUF models.

Handles translation of Markdown text using GGUF-format models
downloaded automatically from ModelScope on first run.
No Ollama or external service configuration needed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .utils import LANGUAGE_MAP, TRANSLATION_PROMPT_TEMPLATE

# Model definitions with GGUF download sources
MODEL_DEFINITIONS = {
    "gemma3:1b": {
        "name": "Google Gemma 3 1B",
        "gguf_repo": "bartowski/gemma-3-1b-it-GGUF",
        "gguf_file": "gemma-3-1b-it-Q4_K_M.gguf",
        "size_mb": 780,
        "quality": "Good balance of speed and quality",
    },
    "qwen3:0.6b": {
        "name": "Alibaba Qwen 3 0.6B",
        "gguf_repo": "Qwen/Qwen3-0.6B-GGUF",
        "gguf_file": "qwen3-0.6b-q4_k_m.gguf",
        "size_mb": 420,
        "quality": "Fastest, lower quality",
    },
    "qwen3:1.8b": {
        "name": "Alibaba Qwen 3 1.8B",
        "gguf_repo": "Qwen/Qwen3-1.8B-GGUF",
        "gguf_file": "qwen3-1.8b-q4_k_m.gguf",
        "size_mb": 1100,
        "quality": "Better quality, slower",
    },
}

# Default model cache directory
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "yanfu" / "models"


class ModelManager:
    """Manage GGUF model downloads and caching.

    Automatically downloads models from HuggingFace/ModelScope on first use.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        """Initialize model manager.

        Args:
            cache_dir: Directory to store downloaded models.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_model_path(self, model_name: str) -> Path | None:
        """Get the local path for a model.

        Args:
            model_name: Model identifier.

        Returns:
            Path to GGUF file or None if not downloaded.
        """
        model_def = MODEL_DEFINITIONS.get(model_name)
        if not model_def:
            return None

        gguf_file = model_def["gguf_file"]
        model_path = self.cache_dir / model_name / gguf_file

        if model_path.exists():
            return model_path
        return None

    def is_model_downloaded(self, model_name: str) -> bool:
        """Check if a model is already downloaded.

        Args:
            model_name: Model identifier.

        Returns:
            True if model exists locally.
        """
        return self.get_model_path(model_name) is not None

    def download_model(self, model_name: str, force: bool = False) -> Path:
        """Download a model from HuggingFace/ModelScope.

        Args:
            model_name: Model identifier.
            force: Force re-download even if exists.

        Returns:
            Path to downloaded GGUF file.
        """
        model_def = MODEL_DEFINITIONS.get(model_name)
        if not model_def:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(MODEL_DEFINITIONS.keys())}")

        model_dir = self.cache_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)

        gguf_file = model_def["gguf_file"]
        model_path = model_dir / gguf_file

        if model_path.exists() and not force:
            print(f"[YanFu] Model already exists: {model_path}")
            return model_path

        print(f"[YanFu] Downloading {model_def['name']} ({model_def['size_mb']}MB)...")
        print(f"[YanFu] Source: {model_def['gguf_repo']}/{gguf_file}")

        # Try HuggingFace first, then ModelScope
        try:
            self._download_from_huggingface(model_def, model_dir)
        except Exception as hf_error:
            print(f"[YanFu] HuggingFace download failed: {hf_error}")
            print("[YanFu] Trying ModelScope...")
            try:
                self._download_from_modelscope(model_def, model_dir)
            except Exception as ms_error:
                raise RuntimeError(
                    f"Failed to download model from both sources.\n"
                    f"HuggingFace: {hf_error}\n"
                    f"ModelScope: {ms_error}"
                ) from ms_error

        if not model_path.exists():
            raise RuntimeError(f"Model file not found after download: {model_path}")

        print(f"[YanFu] Model downloaded successfully: {model_path}")
        return model_path

    def _download_from_huggingface(self, model_def: dict, model_dir: Path):
        """Download model from HuggingFace.

        Args:
            model_def: Model definition dictionary.
            model_dir: Target directory.
        """
        from huggingface_hub import hf_hub_download

        hf_hub_download(
            repo_id=model_def["gguf_repo"],
            filename=model_def["gguf_file"],
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
        )

    def _download_from_modelscope(self, model_def: dict, model_dir: Path):
        """Download model from ModelScope.

        Args:
            model_def: Model definition dictionary.
            model_dir: Target directory.
        """
        from modelscope.hub.snapshot_download import snapshot_download

        # ModelScope uses original model repos, not GGUF repos
        # We need to map GGUF repos to ModelScope equivalents
        gguf_repo = model_def["gguf_repo"]
        if "bartowski" in gguf_repo:
            # Map bartowski GGUF to ModelScope equivalent
            ms_repo = gguf_repo.replace("bartowski/", "")
        else:
            ms_repo = gguf_repo

        snapshot_download(
            model_id=ms_repo,
            cache_dir=str(model_dir),
            allow_patterns=[model_def["gguf_file"]],
        )

    def list_downloaded_models(self) -> list[str]:
        """List all downloaded models.

        Returns:
            List of model names.
        """
        downloaded = []
        for model_name in MODEL_DEFINITIONS:
            if self.is_model_downloaded(model_name):
                downloaded.append(model_name)
        return downloaded

    def get_model_size(self, model_name: str) -> int:
        """Get the size of a downloaded model in bytes.

        Args:
            model_name: Model identifier.

        Returns:
            File size in bytes, or 0 if not downloaded.
        """
        model_path = self.get_model_path(model_name)
        if model_path:
            return model_path.stat().st_size
        return 0

    def cleanup(self, model_name: str | None = None):
        """Remove downloaded models to free disk space.

        Args:
            model_name: Specific model to remove, or None for all.
        """
        if model_name:
            model_dir = self.cache_dir / model_name
            if model_dir.exists():
                import shutil
                shutil.rmtree(model_dir)
                print(f"[YanFu] Removed model: {model_name}")
        else:
            if self.cache_dir.exists():
                import shutil
                shutil.rmtree(self.cache_dir)
                print(f"[YanFu] Removed all models from {self.cache_dir}")


class GGUFTranslator:
    """Translate text using GGUF models via llama-cpp-python.

    Zero-configuration: models are auto-downloaded on first use.
    """

    def __init__(
        self,
        model_name: str = "gemma3:1b",
        model_path: str | Path | None = None,
        n_ctx: int = 4096,
        n_threads: int = -1,
        temperature: float = 0.3,
        cache_dir: str | Path | None = None,
    ):
        """Initialize translator.

        Args:
            model_name: Model identifier.
            model_path: Direct path to GGUF file (optional).
            n_ctx: Context window size.
            n_threads: Number of CPU threads (-1 = auto).
            temperature: Generation temperature.
            cache_dir: Model cache directory.
        """
        self.model_name = model_name
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads if n_threads > 0 else os.cpu_count() or 4
        self.temperature = temperature
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._model = None
        self._model_manager = ModelManager(self.cache_dir)

    def _ensure_model(self):
        """Ensure model is downloaded and loaded."""
        if self._model is not None:
            return

        # Get model path
        if self.model_path:
            gguf_path = Path(self.model_path)
        else:
            gguf_path = self._model_manager.get_model_path(self.model_name)
            if gguf_path is None:
                print("[YanFu] Model not found locally, downloading...")
                gguf_path = self._model_manager.download_model(self.model_name)

        if not gguf_path.exists():
            raise FileNotFoundError(f"GGUF model file not found: {gguf_path}")

        print(f"[YanFu] Loading model: {gguf_path}")

        # Load model with llama-cpp-python
        from llama_cpp import Llama

        self._model = Llama(
            model_path=str(gguf_path),
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_gpu_layers=0,  # CPU only for compatibility
            verbose=False,
        )

        print("[YanFu] Model loaded successfully")

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        """Translate text.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated text.
        """
        if not text.strip():
            return ""

        self._ensure_model()

        source_name = LANGUAGE_MAP.get(source_lang, source_lang)
        target_name = LANGUAGE_MAP.get(target_lang, target_lang)

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(
            source_lang=source_name,
            source_code=source_lang,
            target_lang=target_name,
            target_code=target_lang,
            text=text,
        )

        response = self._model(
            prompt,
            max_tokens=4096,
            temperature=self.temperature,
            stop=["\n\n\n", "</s>"],
            echo=False,
        )

        translated = response["choices"][0]["text"]
        return self._post_process(translated)

    def _post_process(self, text: str) -> str:
        """Post-process translated text.

        Args:
            text: Raw translated text.

        Returns:
            Cleaned translated text.
        """
        # Remove common LLM prefixes
        prefixes = [
            r"^Here is the translation.*?:",
            r"^Here's the translation.*?:",
            r"^Sure, here is the translation.*?:",
            r"^Translation:",
            r"^Translated text:",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        # Remove markdown code blocks if present
        markdown_pattern = r"^```(?:text|markdown)?\s*\n?(.*?)\n?```$"
        text = re.sub(markdown_pattern, r"\1", text, flags=re.DOTALL).strip()

        return text.strip()

    def cleanup(self):
        """Free model memory."""
        if self._model is not None:
            del self._model
            self._model = None
        import gc
        gc.collect()


def translate_markdown(
    markdown: str,
    source_lang: str = "auto",
    target_lang: str = "en",
    model_name: str = "gemma3:1b",
    model_path: str | None = None,
    device: str = "auto",
    temperature: float = 0.3,
    cache_dir: str | None = None,
) -> str:
    """Translate Markdown text while preserving formatting.

    Args:
        markdown: Markdown text to translate.
        source_lang: Source language code.
        target_lang: Target language code.
        model_name: Model identifier.
        model_path: Direct path to GGUF file.
        device: Ignored (always CPU for GGUF).
        temperature: Generation temperature.
        cache_dir: Model cache directory.

    Returns:
        Translated Markdown text.
    """
    translator = GGUFTranslator(
        model_name=model_name,
        model_path=model_path,
        temperature=temperature,
        cache_dir=cache_dir,
    )

    try:
        # Split markdown into chunks for better translation
        chunks = _split_markdown(markdown)
        translated_chunks = []

        for chunk in chunks:
            if chunk.strip():
                translated = translator.translate(chunk, source_lang, target_lang)
                translated_chunks.append(translated)
            else:
                translated_chunks.append(chunk)

        return "\n\n".join(translated_chunks)
    finally:
        translator.cleanup()


def _split_markdown(markdown: str, max_chunk_size: int = 2000) -> list[str]:
    """Split Markdown into translatable chunks.

    Preserves code blocks, formulas, and image references.

    Args:
        markdown: Markdown text.
        max_chunk_size: Maximum chunk size in characters.

    Returns:
        List of markdown chunks.
    """
    chunks = []
    current_chunk = ""

    # Split by paragraphs
    paragraphs = markdown.split("\n\n")

    for para in paragraphs:
        if len(current_chunk) + len(para) > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
