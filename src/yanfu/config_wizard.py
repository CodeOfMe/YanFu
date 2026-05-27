"""YanFu - Interactive configuration wizard.

Guides users through setting up Ollama or OpenAI-compatible API.
Models are dynamically fetched from the API.
"""

from __future__ import annotations

import sys

from .translator import ConfigManager, ModelFetcher, OllamaTranslator


def run_config_wizard():
    """Run interactive configuration wizard in terminal."""
    print("=" * 60)
    print("  YanFu Configuration Wizard")
    print("=" * 60)
    print()

    config = ConfigManager()

    # Step 1: Choose provider
    print("Step 1: Choose your translation provider")
    print("  1. Ollama (Local, free, requires Ollama installed)")
    print("  2. OpenAI API (Cloud, requires API key)")
    print("  3. Custom OpenAI-compatible endpoint (vLLM, LM Studio, etc.)")
    print()

    while True:
        choice = input("Select provider [1-3]: ").strip()
        if choice == "1":
            provider = "ollama"
            break
        elif choice == "2":
            provider = "openai"
            break
        elif choice == "3":
            provider = "custom"
            break
        print("Invalid choice. Please enter 1, 2, or 3.")

    config.set("provider", provider)

    # Step 2: Configure based on provider
    if provider == "ollama":
        print()
        print("Step 2: Ollama Configuration")
        base_url = input("  Ollama URL [http://localhost:11434]: ").strip()
        if not base_url:
            base_url = "http://localhost:11434"
        config.set("base_url", base_url)

        # Fetch available models
        print()
        print("Fetching available models...")
        models = ModelFetcher.get_ollama_models(base_url)
        if models:
            print(f"  Found {len(models)} model(s):")
            for i, m in enumerate(models, 1):
                print(f"  {i}. {m}")
            print()
            print("  Or enter a custom model name (e.g., pull a new one with 'ollama pull <model>')")
            print()

            while True:
                choice = input(f"Select model [1-{len(models)} or custom name]: ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(models):
                        model = models[idx]
                        break
                elif choice:
                    model = choice
                    break
                print("Invalid choice.")
        else:
            print("  No models found. Please pull a model first (e.g., 'ollama pull gemma3:1b')")
            print()
            model = input("  Enter model name to use: ").strip()
            if not model:
                print("Model name is required.")
                sys.exit(1)

        config.set("model", model)

    elif provider == "openai":
        print()
        print("Step 2: OpenAI Configuration")
        api_key = input("  OpenAI API Key: ").strip()
        if not api_key:
            print("Error: API key is required for OpenAI.")
            sys.exit(1)
        config.set("api_key", api_key)
        config.set("base_url", "https://api.openai.com")

        # Fetch available models
        print()
        print("Fetching available models...")
        models = ModelFetcher.get_openai_models("https://api.openai.com", api_key)
        if models:
            # Filter to common chat models
            chat_models = [m for m in models if "gpt" in m.lower() or "o1" in m.lower() or "o3" in m.lower()]
            if chat_models:
                print(f"  Found {len(chat_models)} chat model(s):")
                for i, m in enumerate(chat_models[:20], 1):  # Show first 20
                    print(f"  {i}. {m}")
                print()
                print("  Or enter a custom model name")
                print()

                while True:
                    choice = input(f"Select model [1-{min(20, len(chat_models))} or custom name]: ").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(chat_models):
                            model = chat_models[idx]
                            break
                    elif choice:
                        model = choice
                        break
                    print("Invalid choice.")
            else:
                print("  No chat models found.")
                model = input("  Enter model name to use: ").strip()
        else:
            print("  Could not fetch models. Please enter manually.")
            model = input("  Model name (e.g., gpt-4o-mini): ").strip()

        if not model:
            print("Model name is required.")
            sys.exit(1)
        config.set("model", model)

    else:  # custom
        print()
        print("Step 2: Custom Endpoint Configuration")
        base_url = input("  API Base URL (e.g., http://localhost:8000): ").strip()
        if not base_url:
            print("Error: Base URL is required.")
            sys.exit(1)
        config.set("base_url", base_url)

        api_key = input("  API Key (leave empty if not required): ").strip()
        config.set("api_key", api_key)

        # Try to fetch models
        print()
        print("Fetching available models...")
        models = ModelFetcher.get_openai_models(base_url, api_key)
        if models:
            print(f"  Found {len(models)} model(s):")
            for i, m in enumerate(models[:20], 1):
                print(f"  {i}. {m}")
            print()
            print("  Or enter a custom model name")
            print()

            while True:
                choice = input(f"Select model [1-{min(20, len(models))} or custom name]: ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(models):
                        model = models[idx]
                        break
                elif choice:
                    model = choice
                    break
                print("Invalid choice.")
        else:
            print("  Could not fetch models. Please enter manually.")
            model = input("  Model name: ").strip()

        if not model:
            print("Model name is required.")
            sys.exit(1)
        config.set("model", model)

    # Step 3: PDF Parsing Engine
    print()
    print("Step 3: Choose PDF parsing engine")
    print("  1. Docling (IBM, balanced, ~1.5GB — recommended default)")
    print("  2. Marker (Layout+OCR+Images, ~3GB)")
    print("  3. Auto (Best available)")
    print("  4. EasyOCR (80 languages, ~300MB)")
    print("  5. PyMuPDF (Fast, no models)")
    print("  6. PDFPlumber (Tables, no models)")
    print()

    engine_map = {"1": "docling", "2": "marker", "3": "auto", "4": "easyocr", "5": "pymupdf", "6": "pdfplumber"}
    while True:
        choice = input("Select engine [1-5]: ").strip()
        if choice in engine_map:
            config.set("parse_engine", engine_map[choice])
            break
        print("Invalid choice. Please enter 1, 2, 3, or 4.")

    # Step 4: Test connection
    print()
    print("Testing connection...")
    translator = OllamaTranslator(
        provider=config.get("provider"),
        base_url=config.get("base_url"),
        model=config.get("model"),
        api_key=config.get("api_key", ""),
    )
    success, message = translator.test_connection()

    if success:
        print(f"  ✓ {message}")
    else:
        print(f"  ✗ {message}")
        print()
        retry = input("Connection test failed. Continue anyway? [y/N]: ").strip().lower()
        if retry != "y":
            print("Configuration cancelled.")
            sys.exit(0)

    # Step 5: Save configuration
    config.save_config()
    print()
    print("=" * 60)
    print("  Configuration saved successfully!")
    print("=" * 60)
    print()
    print(f"  Provider: {config.get('provider')}")
    print(f"  Base URL: {config.get('base_url')}")
    print(f"  Model:    {config.get('model')}")
    print(f"  Engine:   {config.get('parse_engine', 'auto')}")
    print()
    print("You can re-run this wizard anytime with: yanfu --config")
    print()


if __name__ == "__main__":
    run_config_wizard()
