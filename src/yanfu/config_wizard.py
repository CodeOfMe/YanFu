"""YanFu - Interactive configuration wizard.

Guides users through setting up Ollama or OpenAI-compatible API.
"""

from __future__ import annotations

import sys

from .translator import ConfigManager, MODEL_PRESETS, OllamaTranslator


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

        print()
        print("Step 3: Choose a model")
        print("  Available presets:")
        for i, (key, info) in enumerate(MODEL_PRESETS.items(), 1):
            if info["provider"] == "ollama":
                print(f"  {i}. {key} - {info['description']}")
        print("  Or enter a custom model name (e.g., llama3.2:1b)")
        print()

        while True:
            choice = input("Select model [1-4 or custom name]: ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                ollama_presets = [(k, v) for k, v in MODEL_PRESETS.items() if v["provider"] == "ollama"]
                if 0 <= idx < len(ollama_presets):
                    model = ollama_presets[idx][1]["model"]
                    break
            elif choice:
                model = choice
                break
            print("Invalid choice.")

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

        print()
        print("Step 3: Choose a model")
        print("  1. gpt-4o-mini (Fast and affordable)")
        print("  2. gpt-4o (High quality)")
        print("  Or enter a custom model name")
        print()

        while True:
            choice = input("Select model [1-2 or custom name]: ").strip()
            if choice == "1":
                model = "gpt-4o-mini"
                break
            elif choice == "2":
                model = "gpt-4o"
                break
            elif choice:
                model = choice
                break
            print("Invalid choice.")

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

        print()
        model = input("  Model name: ").strip()
        if not model:
            print("Error: Model name is required.")
            sys.exit(1)
        config.set("model", model)

    # Step 3: Test connection
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

    # Step 4: Save configuration
    config.save_config()
    print()
    print("=" * 60)
    print("  Configuration saved successfully!")
    print("=" * 60)
    print()
    print(f"  Provider: {config.get('provider')}")
    print(f"  Base URL: {config.get('base_url')}")
    print(f"  Model:    {config.get('model')}")
    print()
    print("You can re-run this wizard anytime with: yanfu --config")
    print()


if __name__ == "__main__":
    run_config_wizard()
