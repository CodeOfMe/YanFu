#!/usr/bin/env python3
"""Test script: Translate sample.pdf from English to Chinese using Ollama."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from yanfu.core import DocumentProcessor
from yanfu.translator import ConfigManager

def main():
    # Setup config to use local Ollama with qwen3:0.6b
    config = ConfigManager()
    config.set("provider", "ollama")
    config.set("base_url", "http://localhost:11434")
    config.set("model", "qwen3:0.6b")
    config.set("temperature", 0.3)
    config.set("source_lang", "en")
    config.set("target_lang", "zh")
    config.save_config()

    print("=" * 60)
    print("YanFu Test: sample.pdf English → Chinese")
    print("Model: qwen3:0.6b (Ollama)")
    print("=" * 60)

    processor = DocumentProcessor(
        output_dir=str(Path(__file__).parent / "output"),
        target_lang="zh",
        source_lang="en",
        config=config,
        verbose=True,
    )

    result = processor.process(str(Path(__file__).parent / "sample.pdf"))

    if result.success:
        print("\n" + "=" * 60)
        print("✅ Translation completed successfully!")
        print("=" * 60)
        print(f"  Markdown: {result.output_md}")
        print(f"  PDF:      {result.output_pdf}")
        print(f"  Pages:    {result.page_count}")
        print(f"  Time:     {result.total_time:.1f}s")
    else:
        print(f"\n❌ Translation failed: {result.error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
