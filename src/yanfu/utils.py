"""YanFu - Utility functions for document processing and translation."""

from __future__ import annotations

import re
from pathlib import Path

# Language codes mapping (ISO 639-1 and variants)
LANGUAGE_MAP = {
    "auto": "auto",
    "en": "English",
    "zh": "Chinese (Simplified)",
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "zh-TW": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "it": "Italian",
    "pt": "Portuguese",
    "ar": "Arabic",
    "hi": "Hindi",
    "th": "Thai",
    "vi": "Vietnamese",
}

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".caj"}

# Default translation model
DEFAULT_TRANSLATION_MODEL = "gemma3:1b"

# ModelScope model IDs
MODELSCOPE_MODELS = {
    "gemma3:1b": "LLM-Research/gemma-3-1b-it",
    "qwen3:0.6b": "Qwen/Qwen3-0.6B",
    "qwen3:1.8b": "Qwen/Qwen3-1.8B",
}

# Translation prompt template
TRANSLATION_PROMPT_TEMPLATE = """You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator. Your goal is to accurately convey the meaning and nuances of the original {source_lang} text while adhering to {target_lang} grammar, vocabulary, and cultural sensitivities.

CRITICAL RULES:
1. Produce ONLY the {target_lang} translation
2. Do NOT include any explanations or commentary
3. Preserve all Markdown formatting, LaTeX formulas, and image references
4. Start directly with the translated text

Translate the following text:

{text}"""


def clean_markdown(text: str) -> str:
    """Clean and normalize Markdown text.

    Args:
        text: Raw Markdown text.

    Returns:
        Cleaned Markdown text.
    """
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize line endings
    text = text.replace("\r\n", "\n")

    # Remove trailing whitespace from lines
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # Clean up docling formula-not-decoded placeholders
    text = re.sub(r"<!--\s*formula-not-decoded\s*-->", "[Formula]", text)

    return text.strip()


def extract_images_from_pdf(pdf_path: str, output_dir: str) -> dict[str, bytes]:
    """Extract images from a PDF file.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save extracted images.

    Returns:
        Dictionary mapping image filenames to image data.
    """
    import fitz

    images = {}
    doc = fitz.open(pdf_path)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        image_list = page.get_images(full=True)

        for img_idx, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            if not base_image:
                continue

            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_name = f"page{page_idx + 1}_img{img_idx + 1}.{image_ext}"

            images[image_name] = image_bytes

    doc.close()
    return images


def detect_formulas(text: str) -> list[tuple[int, int, str]]:
    """Detect LaTeX formulas in text.

    Args:
        text: Text to search for formulas.

    Returns:
        List of (start, end, formula) tuples.
    """
    formulas = []

    # Inline formulas: $...$
    inline_pattern = re.compile(r"\$([^$\n]+)\$")
    for match in inline_pattern.finditer(text):
        formulas.append((match.start(), match.end(), match.group(0)))

    # Display formulas: $$...$$ or \[...\]
    display_pattern = re.compile(r"\$\$([^$]+)\$\$|\\\[(.+?)\\\]", re.DOTALL)
    for match in display_pattern.finditer(text):
        formulas.append((match.start(), match.end(), match.group(0)))

    return formulas


def is_pdf_file(path: str | Path) -> bool:
    """Check if a file is a PDF.

    Args:
        path: File path.

    Returns:
        True if PDF file.
    """
    return Path(path).suffix.lower() == ".pdf"


def is_caj_file(path: str | Path) -> bool:
    """Check if a file is a CAJ.

    Args:
        path: File path.

    Returns:
        True if CAJ file.
    """
    return Path(path).suffix.lower() == ".caj"


def get_output_path(input_path: str | Path, output_dir: str | Path | None = None, suffix: str = ".md") -> Path:
    """Generate output file path.

    Args:
        input_path: Input file path.
        output_dir: Output directory (optional).
        suffix: Output file suffix.

    Returns:
        Output file path.
    """
    input_path = Path(input_path)
    output_path = input_path.with_suffix(suffix)

    if output_dir:
        output_path = Path(output_dir) / output_path.name

    return output_path


def estimate_pdf_complexity(pdf_path: str) -> str:
    """Estimate PDF complexity for engine selection.

    Args:
        pdf_path: Path to PDF file.

    Returns:
        Complexity level: 'simple', 'moderate', or 'complex'.
    """
    import fitz

    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        has_images = False
        has_text = False

        for page_idx in range(min(page_count, 5)):  # Check first 5 pages
            page = doc[page_idx]
            text = page.get_text()
            if text.strip():
                has_text = True
            if page.get_images():
                has_images = True

        doc.close()

        if not has_images and has_text:
            return "simple"
        if has_images and page_count < 20:
            return "moderate"
        return "complex"
    except Exception:
        return "moderate"


def save_images_and_update_markdown(
    markdown: str,
    images: dict[str, bytes],
    output_dir: str | Path,
    image_subdir: str = "images",
) -> str:
    """Save images and update Markdown references.

    Args:
        markdown: Markdown text with image references.
        images: Dictionary of image data.
        output_dir: Output directory.
        image_subdir: Subdirectory for images.

    Returns:
        Updated Markdown text.
    """
    output_dir = Path(output_dir)
    image_dir = output_dir / image_subdir
    image_dir.mkdir(parents=True, exist_ok=True)

    for img_name, img_data in images.items():
        img_path = image_dir / img_name
        if isinstance(img_data, bytes):
            img_path.write_bytes(img_data)
        else:
            # Handle PIL Image objects
            img_data.save(str(img_path))

        # Update Markdown reference
        old_ref = f"]({img_name})"
        new_ref = f"]({image_subdir}/{img_name})"
        markdown = markdown.replace(old_ref, new_ref)

        old_ref = f"](./{img_name})"
        new_ref = f"](./{image_subdir}/{img_name})"
        markdown = markdown.replace(old_ref, new_ref)

    return markdown


def find_documents(input_dir: str | Path, recursive: bool = False) -> list[Path]:
    """Find all supported document files in a directory.

    Args:
        input_dir: Input directory.
        recursive: Whether to search recursively.

    Returns:
        List of document file paths.
    """
    input_dir = Path(input_dir)
    pattern = "**/*" if recursive else "*"

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(input_dir.glob(f"{pattern}{ext}"))

    return sorted(files)


def create_output_directories(files: list[Path], input_dir: Path, output_dir: Path, recursive: bool = False) -> None:
    """Create output directory structure matching input.

    Args:
        files: List of input files.
        input_dir: Input directory.
        output_dir: Output directory.
        recursive: Whether input was searched recursively.
    """
    for f in files:
        if recursive:
            rel_path = f.relative_to(input_dir)
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
