#!/usr/bin/env python3
"""Comprehensive test: tables, images, formulas, translation, PDF rendering."""

import os, sys, time
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
sys.path.insert(0, str(Path(__file__).parent / "src"))

from yanfu.parser import parse_document
from yanfu.translator import ConfigManager, translate_markdown
from yanfu.renderer import render_pdf
from yanfu.utils import clean_markdown

OUTPUT = Path(__file__).parent / "test_output"
OUTPUT.mkdir(exist_ok=True)


def analyze_content(md: str) -> dict:
    """Analyze markdown for tables, images, formulas."""
    import re
    tables = len(re.findall(r'\|.*\|.*\n\|[-| ]+\|', md))  # markdown tables
    images = len(re.findall(r'!\[.*?\]\(.*?\)', md))        # ![alt](url)
    formulas = len(re.findall(r'\$\$.*?\$\$|\$[^$]+\$', md, re.DOTALL))  # $$...$$ or $...$
    code_blocks = len(re.findall(r'```', md)) // 2
    headings = len(re.findall(r'^#{1,6}\s', md, re.MULTILINE))
    return {
        "tables": tables, "images": images, "formulas": formulas,
        "code_blocks": code_blocks, "headings": headings, "chars": len(md),
    }


def test_parse(engine: str) -> tuple:
    """Parse and return markdown + stats."""
    print(f"\n  [{engine.upper()}]", end=" ", flush=True)
    t0 = time.time()
    try:
        r = parse_document("sample.pdf", engine=engine, output_dir=str(OUTPUT / engine))
        md = r.get("markdown", "")
        elapsed = time.time() - t0
        stats = analyze_content(md)
        used = r.get("engine", "?")
        print(f"✅ {used} engine, {stats['chars']} chars, {elapsed:.1f}s")
        for k, v in stats.items():
            if v and k != "chars":
                print(f"      {k}: {v}")
        return md, stats
    except Exception as e:
        print(f"❌ {time.time()-t0:.1f}s: {e}")
        return "", {}


def main():
    print("=" * 70)
    print("  YanFu — Tables / Images / Formulas / Translation Test")
    print("=" * 70)

    # Config
    config = ConfigManager()
    config.set("provider", "ollama")
    config.set("base_url", "http://localhost:11434")
    config.set("model", "qwen3:0.6b")
    config.set("target_lang", "zh")
    config.set("source_lang", "en")
    config.set("temperature", 0.3)
    config.save_config()

    # ── Step 1: Parse with all engines ──
    print("\n── 1. Parse with each engine ──")
    best_md, best_stats = "", {}
    for eng in ["pymupdf", "easyocr"]:
        md, stats = test_parse(eng)
        if md and len(md) > len(best_md):
            best_md, best_stats = md, stats
        OUTPUT.mkdir(exist_ok=True)
        (OUTPUT / f"sample_{eng}.md").write_text(md, encoding="utf-8")

    if not best_md:
        print("\n❌ No engine succeeded.")
        return

    print(f"\n  🏆 Best: {len(best_md)} chars — {'✓ '.join(f'{k}={v}' for k,v in best_stats.items() if v)}")

    # ── Step 2: Translation ──
    print("\n── 2. Translation ──")
    print(f"  Sending {len(best_md)} chars to {config.get('model')}...")
    t0 = time.time()
    try:
        translated = translate_markdown(best_md, source_lang="en", target_lang="zh", config=config)
        translated = clean_markdown(translated)
        elapsed = time.time() - t0
        print(f"  ✅ {len(translated)} chars in {elapsed:.1f}s")
        print(f"  First 300 chars: {translated[:300]}")
    except Exception as e:
        print(f"  ❌ {e}")
        return

    # ── Step 3: Render PDF ──
    print("\n── 3. PDF rendering ──")
    pdf_path = str(OUTPUT / "sample_translated.pdf")
    t0 = time.time()
    render_pdf(translated, output_path=pdf_path)
    size = Path(pdf_path).stat().st_size / 1024
    print(f"  ✅ {size:.0f}KB in {time.time()-t0:.1f}s")

    # ── Summary ──
    print(f"\n{'='*70}")
    print(f"  📊 Summary")
    print(f"{'='*70}")
    print(f"  Parse:  {best_stats['chars']} chars, {best_stats['tables']} tables, "
          f"{best_stats['images']} images, {best_stats['formulas']} formulas")
    print(f"  Translate: {len(translated)} chars → sample_translated.md")
    print(f"  PDF:    {pdf_path} ({size:.0f}KB)")
    print(f"  Files:  {OUTPUT}/")
    for f in sorted(OUTPUT.iterdir()):
        if f.is_file():
            print(f"    {f.name} ({f.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
