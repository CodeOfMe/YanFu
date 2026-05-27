"""YanFu - PDF renderer with layout preservation.

Generates PDF files from Markdown while preserving layout, images, and formulas.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class PDFRenderer:
    """Render Markdown to PDF with layout preservation.

    Handles text formatting, images, tables, and formulas.
    Supports CJK fonts for Chinese/Japanese/Korean text.
    """

    def __init__(
        self,
        output_path: str,
        page_size: str = "A4",
        font_name: str | None = None,
        font_size: int = 11,
        margin: float = 20.0,
    ):
        """Initialize PDF renderer.

        Args:
            output_path: Output PDF file path.
            page_size: Page size (A4, letter).
            font_name: Font name (auto-detects CJK fonts).
            font_size: Base font size.
            margin: Page margin in mm.
        """
        self.output_path = Path(output_path)
        self.page_size = A4 if page_size == "A4" else letter
        self.font_size = font_size
        self.margin = margin * mm
        self._styles = None
        self._font_name = font_name or self._find_cjk_font()

    def render(self, markdown: str, image_dir: str | None = None) -> str:
        """Render Markdown to PDF.

        Args:
            markdown: Markdown text.
            image_dir: Directory containing images.

        Returns:
            Output PDF path.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(self.output_path),
            pagesize=self.page_size,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin,
            bottomMargin=self.margin,
        )

        story = self._markdown_to_story(markdown, image_dir)
        doc.build(story)

        return str(self.output_path)

    def _markdown_to_story(self, markdown: str, image_dir: str | None) -> list:
        """Convert Markdown to ReportLab story elements.

        Args:
            markdown: Markdown text.
            image_dir: Image directory.

        Returns:
            List of story elements.
        """
        story = []
        styles = self._get_styles()

        # Split by paragraphs
        paragraphs = markdown.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Handle headings
            if para.startswith("#"):
                story.append(self._parse_heading(para, styles))
                continue

            # Handle images
            img_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", para)
            if img_match:
                alt_text = img_match.group(1)
                img_path = img_match.group(2)

                if image_dir:
                    full_path = Path(image_dir) / img_path
                else:
                    full_path = Path(img_path)

                if full_path.exists():
                    img = Image(str(full_path))
                    # Scale image to fit page width
                    max_width = self.page_size[0] - 2 * self.margin
                    if img.imageWidth > max_width:
                        scale = max_width / img.imageWidth
                        img.drawWidth = max_width
                        img.drawHeight = img.imageHeight * scale
                    story.append(img)

                    if alt_text:
                        story.append(Spacer(1, 6))
                        story.append(Paragraph(f"<i>{alt_text}</i>", styles["Caption"]))
                continue

            # Handle tables
            if "|" in para and "\n" in para:
                table_element = self._parse_table(para, styles)
                if table_element:
                    story.append(table_element)
                    continue

            # Handle lists
            if para.startswith(("- ", "* ", "+ ")):
                story.append(self._parse_list(para, styles))
                continue

            # Handle code blocks
            if para.startswith("```"):
                story.append(self._parse_code_block(para, styles))
                continue

            # Handle formulas (LaTeX)
            if "$" in para or "\\[" in para:
                story.append(self._parse_formula(para, styles))
                continue

            # Regular paragraph
            formatted_text = self._format_inline(para)
            story.append(Paragraph(formatted_text, styles["Normal"]))

        return story

    def _get_styles(self) -> dict[str, ParagraphStyle]:
        """Get paragraph styles.

        Returns:
            Dictionary of paragraph styles.
        """
        if self._styles is not None:
            return self._styles

        base_style = getSampleStyleSheet()

        font_name = self._font_name

        styles = {
            "Normal": ParagraphStyle(
                "Normal",
                fontName=font_name,
                fontSize=self.font_size,
                leading=self.font_size * 1.5,
                spaceAfter=6,
            ),
            "Heading1": ParagraphStyle(
                "Heading1",
                fontName=font_name,
                fontSize=self.font_size + 8,
                leading=(self.font_size + 8) * 1.3,
                spaceBefore=18,
                spaceAfter=12,
                textColor=colors.HexColor("#1a1a1a"),
            ),
            "Heading2": ParagraphStyle(
                "Heading2",
                fontName=font_name,
                fontSize=self.font_size + 4,
                leading=(self.font_size + 4) * 1.3,
                spaceBefore=14,
                spaceAfter=8,
                textColor=colors.HexColor("#333333"),
            ),
            "Heading3": ParagraphStyle(
                "Heading3",
                fontName=font_name,
                fontSize=self.font_size + 2,
                leading=(self.font_size + 2) * 1.3,
                spaceBefore=10,
                spaceAfter=6,
                textColor=colors.HexColor("#444444"),
            ),
            "Code": ParagraphStyle(
                "Code",
                fontName="Courier",
                fontSize=self.font_size - 1,
                leading=(self.font_size - 1) * 1.3,
                backColor=colors.HexColor("#f5f5f5"),
                borderColor=colors.HexColor("#dddddd"),
                borderWidth=1,
                borderPadding=5,
                spaceBefore=6,
                spaceAfter=6,
            ),
            "Caption": ParagraphStyle(
                "Caption",
                fontName=font_name,
                fontSize=self.font_size - 2,
                leading=(self.font_size - 2) * 1.3,
                textColor=colors.HexColor("#666666"),
                alignment=1,  # Center
            ),
        }

        self._styles = styles
        return styles

    def _find_cjk_font(self) -> str:
        """Find available CJK font.

        Returns:
            Font name.
        """
        # Common CJK font paths on macOS
        mac_fonts = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]

        for font_path in mac_fonts:
            if os.path.exists(font_path):
                font_name = Path(font_path).stem
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    return font_name
                except Exception:
                    continue

        # Try Linux fonts
        linux_fonts = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        ]

        for font_path in linux_fonts:
            if os.path.exists(font_path):
                font_name = Path(font_path).stem
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    return font_name
                except Exception:
                    continue

        # Fallback to Helvetica (no CJK support)
        return "Helvetica"

    def _parse_heading(self, text: str, styles: dict) -> Paragraph:
        """Parse Markdown heading.

        Args:
            text: Heading text.
            styles: Paragraph styles.

        Returns:
            Paragraph element.
        """
        if text.startswith("###"):
            return Paragraph(self._format_inline(text[3:].strip()), styles["Heading3"])
        elif text.startswith("##"):
            return Paragraph(self._format_inline(text[2:].strip()), styles["Heading2"])
        else:
            return Paragraph(self._format_inline(text[1:].strip()), styles["Heading1"])

    def _parse_table(self, text: str, styles: dict) -> Table | None:
        """Parse Markdown table.

        Args:
            text: Table text.
            styles: Paragraph styles.

        Returns:
            Table element.
        """
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return None

        data = []
        for line in lines:
            if line.strip().startswith("|---"):
                continue
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if cells:
                data.append([self._format_inline(cell) for cell in cells])

        if not data:
            return None

        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), self._font_name),
            ("FONTSIZE", (0, 0), (-1, 0), self.font_size),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        return table

    def _parse_list(self, text: str, styles: dict) -> Paragraph:
        """Parse Markdown list.

        Args:
            text: List text.
            styles: Paragraph styles.

        Returns:
            Paragraph element.
        """
        items = text.split("\n")
        formatted_items = []

        for item in items:
            item = re.sub(r"^[-*+]\s*", "• ", item)
            formatted_items.append(self._format_inline(item))

        return Paragraph("<br/>".join(formatted_items), styles["Normal"])

    def _parse_code_block(self, text: str, styles: dict) -> Paragraph:
        """Parse Markdown code block.

        Args:
            text: Code block text.
            styles: Paragraph styles.

        Returns:
            Paragraph element.
        """
        # Remove code fences
        code = re.sub(r"^```.*\n?", "", text)
        code = re.sub(r"\n?```$", "", code)

        return Paragraph(code, styles["Code"])

    def _parse_formula(self, text: str, styles: dict) -> Paragraph:
        """Parse text with LaTeX formulas.

        Args:
            text: Text with formulas.
            styles: Paragraph styles.

        Returns:
            Paragraph element.
        """
        # Keep formulas as-is for now (ReportLab doesn't support LaTeX)
        # In a full implementation, we would convert LaTeX to images
        return Paragraph(self._format_inline(text), styles["Normal"])

    def _format_inline(self, text: str) -> str:
        """Format inline Markdown elements.

        Args:
            text: Text with inline formatting.

        Returns:
            Formatted text for ReportLab.
        """
        # Escape HTML special characters
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")

        # Bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

        # Italic: *text* or _text_
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text)

        # Inline code: `text`
        text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)

        return text


def render_pdf(
    markdown: str,
    output_path: str,
    image_dir: str | None = None,
    page_size: str = "A4",
    font_name: str | None = None,
    font_size: int = 11,
    margin: float = 20.0,
) -> str:
    """Render Markdown to PDF.

    Args:
        markdown: Markdown text.
        output_path: Output PDF path.
        image_dir: Image directory.
        page_size: Page size.
        font_name: Font name.
        font_size: Font size.
        margin: Page margin.

    Returns:
        Output PDF path.
    """
    renderer = PDFRenderer(
        output_path=output_path,
        page_size=page_size,
        font_name=font_name,
        font_size=font_size,
        margin=margin,
    )

    return renderer.render(markdown, image_dir)
