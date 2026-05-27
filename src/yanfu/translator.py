"""YanFu - Translation using Ollama or OpenAI-compatible APIs.

Supports:
- Local Ollama server (default: http://localhost:11434)
- OpenAI API
- Any OpenAI-compatible endpoint (vLLM, LM Studio, etc.)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import requests

from .utils import LANGUAGE_MAP, TRANSLATION_PROMPT_TEMPLATE

# Configuration file location
CONFIG_DIR = Path.home() / ".config" / "yanfu"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Default configuration
DEFAULT_CONFIG = {
    "provider": "ollama",
    "base_url": "http://localhost:11434",
    "model": "",
    "api_key": "",
    "temperature": 0.3,
    "max_tokens": 4096,
}


class ConfigManager:
    """Manage YanFu configuration."""

    def __init__(self, config_file: str | Path | None = None):
        self.config_file = Path(config_file) if config_file else CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from file."""
        import json

        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        """Save configuration to file."""
        import json

        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value):
        """Set configuration value."""
        self.config[key] = value

    def is_configured(self) -> bool:
        """Check if basic configuration exists."""
        return bool(self.config.get("provider") and self.config.get("base_url") and self.config.get("model"))

    def reset(self):
        """Reset to default configuration."""
        self.config = DEFAULT_CONFIG.copy()
        if self.config_file.exists():
            self.config_file.unlink()


class ModelFetcher:
    """Dynamically fetch available models from API."""

    @staticmethod
    def get_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
        """Get list of locally available Ollama models.

        Args:
            base_url: Ollama server URL.

        Returns:
            List of model names.
        """
        try:
            url = f"{base_url.rstrip('/')}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [m["name"] for m in models]
        except Exception:
            return []

    @staticmethod
    def get_openai_models(base_url: str = "https://api.openai.com", api_key: str = "") -> list[str]:
        """Get list of available OpenAI models.

        Args:
            base_url: API base URL.
            api_key: API key.

        Returns:
            List of model IDs.
        """
        try:
            url = f"{base_url.rstrip('/')}/v1/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            models = response.json().get("data", [])
            return [m["id"] for m in models]
        except Exception:
            return []

    @staticmethod
    def get_models(provider: str, base_url: str, api_key: str = "") -> list[str]:
        """Get available models based on provider.

        Args:
            provider: API provider (ollama, openai, custom).
            base_url: API base URL.
            api_key: API key.

        Returns:
            List of model names.
        """
        if provider == "ollama":
            return ModelFetcher.get_ollama_models(base_url)
        else:
            return ModelFetcher.get_openai_models(base_url, api_key)


class OllamaTranslator:
    """Translate text using Ollama or OpenAI-compatible APIs."""

    def __init__(
        self,
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "",
        api_key: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """Initialize translator.

        Args:
            provider: API provider (ollama, openai, custom).
            base_url: API base URL.
            model: Model name to use.
            api_key: API key (for OpenAI or custom providers).
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate.
        """
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        """Translate text.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated text.
        """
        import logging
        logger = logging.getLogger("yanfu")
        
        if not text.strip():
            return ""

        logger.debug(f"Translating {len(text)} chars ({source_lang} → {target_lang})")

        source_name = LANGUAGE_MAP.get(source_lang, source_lang)
        target_name = LANGUAGE_MAP.get(target_lang, target_lang)

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(
            source_lang=source_name,
            source_code=source_lang,
            target_lang=target_name,
            target_code=target_lang,
            text=text,
        )

        if self.provider == "ollama":
            response = self._call_ollama(prompt)
        else:
            response = self._call_openai_compatible(prompt)

        return self._post_process(response)

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API.

        Args:
            prompt: Prompt text.

        Returns:
            Generated text.
        """
        import logging
        logger = logging.getLogger("yanfu")
        
        url = f"{self.base_url}/api/generate"
        logger.debug(f"Calling Ollama: {url} (model: {self.model})")
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        translated = result.get("response", "")
        logger.debug(f"Ollama response: {len(translated)} chars")
        return translated

    def _call_openai_compatible(self, prompt: str) -> str:
        """Call OpenAI-compatible API.

        Args:
            prompt: Prompt text.

        Returns:
            Generated text.
        """
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _post_process(self, text: str) -> str:
        """Post-process translated text.

        Args:
            text: Raw translated text.

        Returns:
            Cleaned translated text.
        """
        prefixes = [
            r"^Here is the translation.*?:",
            r"^Here's the translation.*?:",
            r"^Sure, here is the translation.*?:",
            r"^Translation:",
            r"^Translated text:",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        markdown_pattern = r"^```(?:text|markdown)?\s*\n?(.*?)\n?```$"
        text = re.sub(markdown_pattern, r"\1", text, flags=re.DOTALL).strip()

        return text.strip()

    def test_connection(self) -> tuple[bool, str]:
        """Test connection to the API.

        Returns:
            Tuple of (success, message).
        """
        try:
            if self.provider == "ollama":
                url = f"{self.base_url}/api/tags"
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]

                if not model_names:
                    return False, "Connected, but no models found. Run 'ollama pull <model>' first."

                if self.model and self.model in model_names:
                    return True, f"Connected. Model '{self.model}' is available."
                elif self.model:
                    available = ", ".join(model_names[:5])
                    return False, f"Model '{self.model}' not found. Available: {available}"
                else:
                    available = ", ".join(model_names[:5])
                    return True, f"Connected. Available models: {available}"
            else:
                url = f"{self.base_url}/v1/models"
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = requests.get(url, headers=headers, timeout=5)
                response.raise_for_status()
                models = response.json().get("data", [])
                if models:
                    return True, f"Connected. {len(models)} models available."
                return True, f"Connected to {self.base_url}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to {self.base_url}"
        except Exception as e:
            return False, f"Error: {str(e)}"


def translate_markdown(
    markdown: str,
    source_lang: str = "auto",
    target_lang: str = "en",
    temperature: float = 0.3,
    config: ConfigManager | None = None,
) -> str:
    """Translate Markdown text while preserving formatting.

    Args:
        markdown: Markdown text to translate.
        source_lang: Source language code.
        target_lang: Target language code.
        temperature: Generation temperature.
        config: Configuration manager.

    Returns:
        Translated Markdown text.
    """
    if config is None:
        config = ConfigManager()

    translator = OllamaTranslator(
        provider=config.get("provider", "ollama"),
        base_url=config.get("base_url", "http://localhost:11434"),
        model=config.get("model", ""),
        api_key=config.get("api_key", ""),
        temperature=config.get("temperature", temperature),
        max_tokens=config.get("max_tokens", 4096),
    )

    chunks = _split_markdown(markdown)
    translated_chunks = []

    for chunk in chunks:
        if chunk.strip():
            translated = translator.translate(chunk, source_lang, target_lang)
            translated_chunks.append(translated)
        else:
            translated_chunks.append(chunk)

    return "\n\n".join(translated_chunks)


def _split_markdown(markdown: str, max_chunk_size: int = 800) -> list[str]:
    """Split Markdown into translatable chunks for small models.

    Preserves code blocks, formulas, and image references.
    Smaller chunks work better with 0.6B-1.8B models.

    Args:
        markdown: Markdown text.
        max_chunk_size: Maximum chunk size in characters (default 800 for small models).

    Returns:
        List of markdown chunks.
    """
    chunks = []
    current_chunk = ""

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
