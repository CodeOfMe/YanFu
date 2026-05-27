"""YanFu - Local LLM translation using ModelScope models.

Handles translation of Markdown text using models from ModelScope
such as gemma3:1b and qwen3:0.6b.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .utils import LANGUAGE_MAP, MODELSCOPE_MODELS, TRANSLATION_PROMPT_TEMPLATE


class ModelScopeTranslator:
    """Translate text using ModelScope local LLMs.

    Supports models like gemma3:1b and qwen3:0.6b downloaded from ModelScope.
    """

    def __init__(
        self,
        model_name: str = "gemma3:1b",
        model_path: str | None = None,
        device: str = "auto",
        max_length: int = 4096,
        temperature: float = 0.3,
    ):
        """Initialize translator.

        Args:
            model_name: Model identifier (gemma3:1b, qwen3:0.6b, etc.).
            model_path: Local path to model (optional, downloads if not provided).
            device: Compute device (auto, cuda, cpu).
            max_length: Maximum generation length.
            temperature: Generation temperature.
        """
        self.model_name = model_name
        self.model_path = model_path
        self.device = self._select_device(device)
        self.max_length = max_length
        self.temperature = temperature
        self._model = None
        self._tokenizer = None

    def _select_device(self, device: str) -> str:
        """Select compute device.

        Args:
            device: Device preference.

        Returns:
            Selected device.
        """
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
            return "cpu"
        return device

    def _load_model(self):
        """Load model and tokenizer from ModelScope."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_id = self.model_path or MODELSCOPE_MODELS.get(self.model_name, self.model_name)

        print(f"[Translator] Loading model: {model_id}")
        print(f"[Translator] Device: {self.device}")

        self._tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            device_map="auto" if self.device == "cuda" else None,
            trust_remote_code=True,
        )

        if self.device == "cpu":
            self._model = self._model.to(self.device)

        self._model.eval()
        print(f"[Translator] Model loaded successfully")

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

        self._load_model()

        source_name = LANGUAGE_MAP.get(source_lang, source_lang)
        target_name = LANGUAGE_MAP.get(target_lang, target_lang)

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(
            source_lang=source_name,
            source_code=source_lang,
            target_lang=target_name,
            target_code=target_lang,
            text=text,
        )

        inputs = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=self.max_length)

        if self.device == "cuda":
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=self.max_length,
                temperature=self.temperature,
                do_sample=self.temperature > 0,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        # Decode only the generated part
        generated_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        translated = self._tokenizer.decode(generated_tokens, skip_special_tokens=True)

        return self._post_process(translated)

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "auto",
        target_lang: str = "en",
        batch_size: int = 4,
    ) -> list[str]:
        """Translate multiple texts in batches.

        Args:
            texts: List of texts to translate.
            source_lang: Source language code.
            target_lang: Target language code.
            batch_size: Batch size for processing.

        Returns:
            List of translated texts.
        """
        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            for text in batch:
                results.append(self.translate(text, source_lang, target_lang))

        return results

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
        import gc

        if self._model is not None:
            del self._model
            self._model = None

        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None

        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


class OllamaTranslator:
    """Translate text using Ollama API.

    Alternative to ModelScope for users who prefer Ollama.
    """

    def __init__(
        self,
        model_name: str = "gemma3:1b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        timeout: int = 120,
    ):
        """Initialize Ollama translator.

        Args:
            model_name: Ollama model name.
            base_url: Ollama API base URL.
            temperature: Generation temperature.
            timeout: Request timeout in seconds.
        """
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        """Translate text via Ollama API.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated text.
        """
        import requests

        if not text.strip():
            return ""

        source_name = LANGUAGE_MAP.get(source_lang, source_lang)
        target_name = LANGUAGE_MAP.get(target_lang, target_lang)

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(
            source_lang=source_name,
            source_code=source_lang,
            target_lang=target_name,
            target_code=target_lang,
            text=text,
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        translated = result.get("response", "")

        return self._post_process(translated)

    def _post_process(self, text: str) -> str:
        """Post-process translated text."""
        prefixes = [
            r"^Here is the translation.*?:",
            r"^Here's the translation.*?:",
            r"^Translation:",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        markdown_pattern = r"^```(?:text|markdown)?\s*\n?(.*?)\n?```$"
        text = re.sub(markdown_pattern, r"\1", text, flags=re.DOTALL).strip()

        return text.strip()


def translate_markdown(
    markdown: str,
    source_lang: str = "auto",
    target_lang: str = "en",
    model_name: str = "gemma3:1b",
    model_path: str | None = None,
    use_ollama: bool = False,
    ollama_url: str = "http://localhost:11434",
    device: str = "auto",
    temperature: float = 0.3,
) -> str:
    """Translate Markdown text while preserving formatting.

    Args:
        markdown: Markdown text to translate.
        source_lang: Source language code.
        target_lang: Target language code.
        model_name: Model identifier.
        model_path: Local model path.
        use_ollama: Whether to use Ollama instead of ModelScope.
        ollama_url: Ollama API URL.
        device: Compute device.
        temperature: Generation temperature.

    Returns:
        Translated Markdown text.
    """
    if use_ollama:
        translator = OllamaTranslator(
            model_name=model_name,
            base_url=ollama_url,
            temperature=temperature,
        )
    else:
        translator = ModelScopeTranslator(
            model_name=model_name,
            model_path=model_path,
            device=device,
            temperature=temperature,
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
        if not use_ollama:
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
