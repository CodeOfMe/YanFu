#!/usr/bin/env python3
"""Test script: Parse sample.pdf and generate Markdown + PDF (mock translation)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from yanfu.parser import parse_document
from yanfu.renderer import render_pdf
from yanfu.utils import clean_markdown

def main():
    print("=" * 60)
    print("YanFu Test: sample.pdf Parse & Render")
    print("=" * 60)

    # Step 1: Parse PDF
    print("\n[1/3] Parsing sample.pdf...")
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    image_dir = output_dir / "sample_images"
    image_dir.mkdir(exist_ok=True)

    result = parse_document(
        str(Path(__file__).parent / "sample.pdf"),
        engine="pymupdf",
        output_dir=str(image_dir),
    )

    markdown = result["markdown"]
    print(f"  Pages: {result['page_count']}")
    print(f"  Images: {len(result.get('images', {}))}")
    print(f"  Engine: {result['engine']}")
    print(f"  Markdown length: {len(markdown)} chars")

    # Save original markdown
    original_md = output_dir / "sample_original.md"
    original_md.write_text(markdown, encoding="utf-8")
    print(f"  Saved: {original_md}")

    # Step 2: Simulate translation (add Chinese prefix for testing)
    print("\n[2/3] Simulating translation (adding Chinese markers)...")
    # In real usage, this would call the LLM API
    translated_markdown = "# 译文示例 (Translated Sample)\n\n" + markdown
    translated_markdown = clean_markdown(translated_markdown)

    translated_md = output_dir / "sample_translated.md"
    translated_md.write_text(translated_markdown, encoding="utf-8")
    print(f"  Saved: {translated_md}")

    # Step 3: Render PDF
    print("\n[3/3] Rendering translated PDF...")
    output_pdf = output_dir / "sample_translated.pdf"

    render_pdf(
        translated_markdown,
        output_path=str(output_pdf),
        image_dir=str(image_dir),
        page_size="A4",
        font_size=11,
        margin=20.0,
    )

    print(f"  Saved: {output_pdf}")

    print("\n" + "=" * 60)
    print("✅ Test completed successfully!")
    print("=" * 60)
    print(f"\nGenerated files:")
    print(f"  Original Markdown: {original_md}")
    print(f"  Translated Markdown: {translated_md}")
    print(f"  Translated PDF: {output_pdf}")

if __name__ == "__main__":
    main()
