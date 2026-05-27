"""YanFu - Layout-preserving PDF translation using PyMuPDF.

Translates PDF documents while preserving original layout, images, and formatting.
Works by extracting text blocks, translating them, and overlaying on original pages.
"""

from __future__ import annotations

import fitz  # PyMuPDF

from .translator import OllamaTranslator, ConfigManager
from .utils import LANGUAGE_MAP, TRANSLATION_PROMPT_TEMPLATE


def translate_pdf_layout(
    input_pdf: str,
    output_pdf: str,
    source_lang: str = "auto",
    target_lang: str = "en",
    config: ConfigManager | None = None,
    temperature: float = 0.3,
    verbose: bool = False,
) -> dict:
    """Translate PDF while preserving original layout.
    
    Extracts text blocks from each page, translates them, and overlays
    the translated text on the original PDF pages. Images, fonts, and
    layout are preserved.
    
    Args:
        input_pdf: Path to input PDF.
        output_pdf: Path to output translated PDF.
        source_lang: Source language code.
        target_lang: Target language code.
        config: Configuration manager.
        temperature: Translation temperature.
        verbose: Enable verbose logging.
        
    Returns:
        Dictionary with page_count, translation_time, etc.
    """
    import time
    
    start_time = time.time()
    
    # Open PDF with error handling for malformed structure trees
    try:
        doc = fitz.open(input_pdf)
    except Exception as e:
        # Try opening as raw PDF if structure tree is broken
        doc = fitz.open(input_pdf, filetype="pdf")
        
    translator = OllamaTranslator(
        provider=config.get("provider", "ollama"),
        base_url=config.get("base_url", "http://localhost:11434"),
        model=config.get("model", ""),
        api_key=config.get("api_key", ""),
        temperature=config.get("temperature", temperature),
    )
    
    source_name = LANGUAGE_MAP.get(source_lang, source_lang)
    target_name = LANGUAGE_MAP.get(target_lang, target_lang)
    
    page_count = len(doc)
    
    for page_num in range(page_count):
        page = doc[page_num]
        
        if verbose:
            print(f"[YanFu] Translating page {page_num + 1}/{page_count}...")
            
        # Get text blocks with coordinates
        blocks = page.get_text("dict")["blocks"]
        
        for block in blocks:
            if "lines" not in block:
                continue
                
            # Extract text from block
            block_text = ""
            for line in block["lines"]:
                for span in line["spans"]:
                    block_text += span["text"]
            
            if not block_text.strip() or len(block_text.strip()) < 2:
                continue
                
            # Translate text block
            try:
                translated = translator.translate(block_text.strip(), source_lang, target_lang)
            except Exception as e:
                if verbose:
                    print(f"[YanFu] Translation failed for block: {e}")
                translated = block_text  # Fallback to original
                
            if not translated.strip():
                continue
                
            # Get bounding box of the block
            x0, y0, x1, y1 = block["bbox"]
            
            # Cover original text with white rectangle
            page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(1, 1, 1), fill=(1, 1, 1))
            
            # Calculate appropriate font size
            block_height = y1 - y0
            font_size = max(8, min(14, block_height * 0.75))
            
            # Insert translated text
            page.insert_text(
                fitz.Point(x0, y0 + font_size * 0.9),
                translated,
                fontsize=font_size,
                fontname="helv",
            )
            
    doc.save(output_pdf)
    doc.close()
    
    total_time = time.time() - start_time
    
    return {
        "page_count": page_count,
        "translation_time": total_time,
        "output_pdf": output_pdf,
    }
