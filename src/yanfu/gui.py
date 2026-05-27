"""YanFu - PySide6 GUI with PDF viewer, translation, and synchronized scrolling.

Provides a complete graphical interface for document translation
with side-by-side PDF viewing, synchronized scrolling, and model management.
Uses separate threads for parsing and translation to avoid UI blocking.
"""

from __future__ import annotations

import sys
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .core import DocumentProcessor
from .parser import parse_document
from .renderer import render_pdf
from .translator import ConfigManager, ModelFetcher, OllamaTranslator, translate_markdown
from .utils import LANGUAGE_MAP, clean_markdown, find_documents

logger = logging.getLogger("yanfu")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """Result of PDF parsing."""
    success: bool
    markdown: str = ""
    images: dict = None
    page_count: int = 0
    engine: str = ""
    error: str = ""

    def __post_init__(self):
        if self.images is None:
            self.images = {}


@dataclass
class TranslationTask:
    """A single translation task."""
    file_path: str
    target_lang: str = "en"
    source_lang: str = "auto"
    use_ocr: bool = False
    parse_engine: str = "auto"
    temperature: float = 0.3
    page_size: str = "A4"
    font_name: str | None = None
    font_size: int = 11
    margin: float = 20.0
    config: ConfigManager | None = None


@dataclass
class TaskResult:
    """Result of a translation task."""
    task: TranslationTask
    success: bool
    output_pdf: str = ""
    output_md: str = ""
    error: str = ""
    page_count: int = 0
    image_count: int = 0
    translation_time: float = 0.0
    total_time: float = 0.0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class ParseWorkerSignals(QObject):
    """Signals for parse worker."""
    started = Signal(str)
    progress = Signal(str, int, int)  # message, current, total
    finished = Signal(object)  # ParseResult
    error = Signal(str)


class ParseWorker(QThread):
    """Background thread for PDF parsing."""

    def __init__(
        self,
        file_path: str,
        output_dir: str,
        use_ocr: bool = False,
        parse_engine: str = "auto",
    ):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.use_ocr = use_ocr
        self.parse_engine = parse_engine
        self.signals = ParseWorkerSignals()
        self._cancel_requested = False
        self._mutex = QMutex()

    def cancel(self):
        with QMutexLocker(self._mutex):
            self._cancel_requested = True

    def is_cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancel_requested

    def run(self):
        try:
            self.signals.started.emit(self.file_path)
            logger.debug(f"[ParseWorker] Starting parse: {self.file_path}")

            image_dir = Path(self.output_dir) / f"{Path(self.file_path).stem}_images"
            image_dir.mkdir(parents=True, exist_ok=True)

            self.signals.progress.emit("Extracting text and images...", 0, 100)

            result = parse_document(
                self.file_path,
                engine=self.parse_engine,
                use_ocr=self.use_ocr,
                output_dir=str(image_dir),
            )

            if self.is_cancelled():
                self.signals.progress.emit("Cancelled", 100, 100)
                return

            self.signals.progress.emit("Parsing complete", 100, 100)

            parse_result = ParseResult(
                success=True,
                markdown=result["markdown"],
                images=result.get("images", {}),
                page_count=result.get("page_count", 0),
                engine=result.get("engine", "unknown"),
            )

            logger.debug(f"[ParseWorker] Parse complete: {parse_result.page_count} pages, {len(parse_result.images)} images")
            self.signals.finished.emit(parse_result)

        except Exception as e:
            logger.error(f"[ParseWorker] Error: {e}")
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


class TranslateWorkerSignals(QObject):
    """Signals for translate worker."""
    started = Signal(str)
    progress = Signal(str, int, int)  # message, current_chunk, total_chunks
    finished = Signal(str, str, str)  # translated_md, output_md, output_pdf
    error = Signal(str)


class TranslateWorker(QThread):
    """Background thread for translation."""

    def __init__(
        self,
        markdown: str,
        source_lang: str,
        target_lang: str,
        config: ConfigManager,
        output_dir: str,
        file_path: str,
        page_size: str = "A4",
        font_size: int = 11,
        margin: float = 20.0,
        temperature: float = 0.3,
    ):
        super().__init__()
        self.markdown = markdown
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.config = config
        self.output_dir = output_dir
        self.file_path = file_path
        self.page_size = page_size
        self.font_size = font_size
        self.margin = margin
        self.temperature = temperature
        self.signals = TranslateWorkerSignals()
        self._cancel_requested = False
        self._mutex = QMutex()

    def cancel(self):
        with QMutexLocker(self._mutex):
            self._cancel_requested = True

    def is_cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancel_requested

    def run(self):
        try:
            self.signals.started.emit(self.file_path)
            logger.debug(f"[TranslateWorker] Starting translation: {self.file_path}")

            # Split markdown into chunks for progress tracking
            from .translator import _split_markdown
            chunks = _split_markdown(self.markdown)
            total_chunks = len(chunks)
            logger.debug(f"[TranslateWorker] Split into {total_chunks} chunks")

            translated_chunks = []
            translator = OllamaTranslator(
                provider=self.config.get("provider", "ollama"),
                base_url=self.config.get("base_url", "http://localhost:11434"),
                model=self.config.get("model", ""),
                api_key=self.config.get("api_key", ""),
                temperature=self.config.get("temperature", self.temperature),
                max_tokens=self.config.get("max_tokens", 4096),
            )

            for i, chunk in enumerate(chunks):
                if self.is_cancelled():
                    self.signals.progress.emit("Cancelled", i, total_chunks)
                    return

                if chunk.strip():
                    self.signals.progress.emit(f"Translating chunk {i+1}/{total_chunks}...", i, total_chunks)
                    translated = translator.translate(chunk, self.source_lang, self.target_lang)
                    translated_chunks.append(translated)
                else:
                    translated_chunks.append(chunk)

            if self.is_cancelled():
                return

            self.signals.progress.emit("Rendering PDF...", total_chunks, total_chunks)

            translated_markdown = "\n\n".join(translated_chunks)
            translated_markdown = clean_markdown(translated_markdown)

            # Save Markdown
            stem = Path(self.file_path).stem
            output_md = str(Path(self.output_dir) / f"{stem}_{self.target_lang}.md")
            Path(output_md).write_text(translated_markdown, encoding="utf-8")
            logger.debug(f"[TranslateWorker] Saved Markdown: {output_md}")

            # Render PDF
            image_dir = Path(self.output_dir) / f"{stem}_images"
            output_pdf = str(Path(self.output_dir) / f"{stem}_{self.target_lang}.pdf")

            render_pdf(
                translated_markdown,
                output_path=output_pdf,
                image_dir=str(image_dir) if image_dir.exists() else None,
                page_size=self.page_size,
                font_size=self.font_size,
                margin=self.margin,
            )
            logger.debug(f"[TranslateWorker] Saved PDF: {output_pdf}")

            self.signals.progress.emit("Translation complete", total_chunks, total_chunks)
            self.signals.finished.emit(translated_markdown, output_md, output_pdf)

        except Exception as e:
            logger.error(f"[TranslateWorker] Error: {e}")
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


# ---------------------------------------------------------------------------
# PDF Viewer Widget
# ---------------------------------------------------------------------------

class PDFViewerWidget(QWidget):
    """Widget to display PDF pages with scroll synchronization."""

    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.current_page = 0
        self.total_pages = 0
        self.sync_enabled = True
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(40)
        self.prev_btn.clicked.connect(self._prev_page)
        toolbar.addWidget(self.prev_btn)

        self.page_label = QLabel("0 / 0")
        self.page_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.page_label)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(40)
        self.next_btn.clicked.connect(self._next_page)
        toolbar.addWidget(self.next_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # PDF display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.image_label)

        layout.addWidget(self.scroll_area)

        self._update_page_label()

    def load_pdf(self, file_path: str):
        """Load a PDF file for display."""
        import os
        old_stderr = sys.stderr
        try:
            sys.stderr = open(os.devnull, 'w')
            self.doc = fitz.open(file_path)
        finally:
            sys.stderr.close()
            sys.stderr = old_stderr
            
        self.total_pages = len(self.doc)
        self.current_page = 0
        logger.debug(f"[PDFViewer] Loaded: {self.total_pages} pages")
        self._render_page()
        self._update_page_label()

    def _render_page(self):
        """Render current page."""
        if not self.doc or self.current_page >= self.total_pages:
            return

        page = self.doc[self.current_page]
        pix = page.get_pixmap(dpi=150)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(img))

    def _on_scroll(self, value):
        """Handle scroll events for synchronization."""
        if not self.sync_enabled or not self.doc:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        max_scroll = scrollbar.maximum()
        if max_scroll > 0:
            page_ratio = value / max_scroll
            estimated_page = int(page_ratio * (self.total_pages - 1))
            if estimated_page != self.current_page:
                self.current_page = estimated_page
                self._render_page()
                self._update_page_label()
                self.page_changed.emit(self.current_page)

    def set_page(self, page_num: int):
        """Set current page number."""
        if self.doc and 0 <= page_num < self.total_pages:
            self.current_page = page_num
            self._render_page()
            self._update_page_label()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_page()
            self._update_page_label()
            self.page_changed.emit(self.current_page)

    def _next_page(self):
        if self.doc and self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._render_page()
            self._update_page_label()
            self.page_changed.emit(self.current_page)

    def _update_page_label(self):
        self.page_label.setText(f"{self.current_page + 1} / {self.total_pages}")

    def set_sync_enabled(self, enabled: bool):
        self.sync_enabled = enabled


# ---------------------------------------------------------------------------
# Model download worker
# ---------------------------------------------------------------------------

class ModelDownloadSignals(QObject):
    """Signals for model download worker."""
    progress = Signal(str, int, int)  # message, current, total
    finished = Signal(str)
    error = Signal(str)


class _TqdmSignal(tqdm):  # type: ignore
    """Custom tqdm that emits progress to Qt signals."""
    def __init__(self, signals, *args, **kwargs):
        self._signals = signals
        self._last_pct = -1
        kwargs.setdefault("file", sys.stdout)
        kwargs.setdefault("unit", "B")
        kwargs.setdefault("unit_scale", True)
        kwargs.setdefault("unit_divisor", 1024)
        super().__init__(*args, **kwargs)
    
    def update(self, n=1):
        super().update(n)
        if self.total and self.total > 0:
            pct = int(self.n * 100 / self.total)
            if pct != self._last_pct:
                self._last_pct = pct
                desc = self.desc or "Downloading"
                size_mb = self.total / 1024 / 1024 if self.total else 0
                self._signals.progress.emit(f"{desc} ({size_mb:.0f}MB)...", pct, 100)


class ModelDownloadWorker(QThread):
    """Background thread for downloading parsing engine models."""

    def __init__(self, engine: str = "marker"):
        super().__init__()
        self.engine = engine
        self.signals = ModelDownloadSignals()
        self._cancel_requested = False
        self._mutex = QMutex()

    def cancel(self):
        with QMutexLocker(self._mutex):
            self._cancel_requested = True

    def is_cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancel_requested

    def run(self):
        try:
            if self.engine == "marker":
                self._download_marker_models()
            elif self.engine == "docling":
                self._download_docling_models()
            elif self.engine == "easyocr":
                self._download_easyocr_models()
            elif self.engine == "mineru":
                self._download_mineru_models()
            else:
                self.signals.error.emit(f"Unknown engine: {self.engine}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Download error: {str(e)}")

    def _patch_tqdm(self):
        """Enable huggingface_hub progress bars and patch tqdm to emit signals."""
        import huggingface_hub.file_download
        import huggingface_hub._snapshot_download
        import tqdm as tqdm_module

        signals = self.signals

        # Patch huggingface_hub's tqdm to use our custom class
        class SignalTqdm(tqdm_module.tqdm):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("file", sys.stdout)
                kwargs.setdefault("unit", "B")
                kwargs.setdefault("unit_scale", True)
                kwargs.setdefault("unit_divisor", 1024)
                super().__init__(*args, **kwargs)
                self._last_pct = -1

            def update(self, n=1):
                super().update(n)
                if self.total and self.total > 0:
                    pct = int(self.n * 100 / self.total)
                    if pct != self._last_pct and pct > self._last_pct:
                        self._last_pct = pct
                        desc = self.desc or "Downloading"
                        signals.progress.emit(f"{desc}", pct, 100)

        # Replace tqdm in huggingface_hub modules
        huggingface_hub.file_download.tqdm = SignalTqdm
        huggingface_hub._snapshot_download.tqdm = SignalTqdm

        # Also enable progress bars
        from huggingface_hub.utils import enable_progress_bars
        enable_progress_bars()

    def _download_marker_models(self):
        """Download marker-pdf models with progress tracking."""
        print("\n" + "=" * 60)
        print("[YanFu] Downloading marker-pdf models (~3GB)...")
        print("=" * 60)

        self.signals.progress.emit("Initializing marker-pdf...", 0, 100)
        self._patch_tqdm()

        try:
            from marker.models import create_model_dict

            print("[YanFu] Loading models (downloads show below)...")
            print("-" * 60)

            artifact_dict = create_model_dict()

            print("-" * 60)
            print("[YanFu] ✅ All marker models loaded!")
            print("=" * 60)

            self.signals.progress.emit("Models loaded", 100, 100)
            self.signals.finished.emit("Marker models loaded successfully")
        except Exception as e:
            print(f"\n[YanFu] ❌ Marker download failed: {e}")
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Marker download failed: {str(e)}")

    def _download_docling_models(self):
        """Download Docling models."""
        print("\n" + "=" * 60)
        print("[YanFu] Downloading Docling models (~1.5GB)...")
        print("=" * 60)

        self.signals.progress.emit("Loading Docling...", 10, 100)

        try:
            from docling.document_converter import DocumentConverter

            self.signals.progress.emit("Loading converter...", 30, 100)
            converter = DocumentConverter()

            print("[YanFu] ✅ Docling models loaded!")
            print("=" * 60)

            self.signals.progress.emit("Docling models loaded", 100, 100)
            self.signals.finished.emit("Docling models loaded successfully")
        except Exception as e:
            print(f"\n[YanFu] ❌ Docling download failed: {e}")
            self.signals.error.emit(f"Docling download failed: {str(e)}")

    def _download_easyocr_models(self):
        """Download EasyOCR models."""
        print("\n" + "=" * 60)
        print("[YanFu] Downloading EasyOCR models (~300MB)...")
        print("=" * 60)

        self.signals.progress.emit("Loading EasyOCR...", 10, 100)

        try:
            import easyocr

            self.signals.progress.emit("Loading reader...", 30, 100)
            reader = easyocr.Reader(['en', 'ch_sim'])

            print("[YanFu] ✅ EasyOCR models loaded!")
            print("=" * 60)

            self.signals.progress.emit("EasyOCR models loaded", 100, 100)
            self.signals.finished.emit("EasyOCR models loaded successfully")
        except Exception as e:
            print(f"\n[YanFu] ❌ EasyOCR download failed: {e}")
            self.signals.error.emit(f"EasyOCR download failed: {str(e)}")

    def _download_mineru_models(self):
        """Download MinerU models."""
        print("\n" + "=" * 60)
        print("[YanFu] Downloading MinerU models (~1.5GB)...")
        print("=" * 60)

        self.signals.progress.emit("Loading MinerU...", 10, 100)

        try:
            from magic_pdf.data.dataset import PymuDocDataset
            from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

            self.signals.progress.emit("Loading models...", 30, 100)

            print("[YanFu] ✅ MinerU models loaded!")
            print("=" * 60)

            self.signals.progress.emit("MinerU models loaded", 100, 100)
            self.signals.finished.emit("MinerU models loaded successfully")
        except Exception as e:
            print(f"\n[YanFu] ❌ MinerU download failed: {e}")
            self.signals.error.emit(f"MinerU download failed: {str(e)}")


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """Settings dialog for translation configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(700)
        self.config = ConfigManager()
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Provider settings
        provider_group = QGroupBox("Translation Provider")
        provider_layout = QFormLayout()

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Ollama (Local)", "ollama")
        self.provider_combo.addItem("OpenAI (Cloud)", "openai")
        self.provider_combo.addItem("Custom OpenAI-Compatible", "custom")
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_layout.addRow("Provider:", self.provider_combo)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://localhost:11434")
        provider_layout.addRow("Base URL:", self.base_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        provider_layout.addRow("API Key:", self.api_key_edit)

        self.model_combo = QComboBox()
        provider_layout.addRow("Model:", self.model_combo)

        btn_layout = QHBoxLayout()
        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        btn_layout.addWidget(self.refresh_models_btn)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_btn)
        provider_layout.addRow("", btn_layout)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # PDF Parsing Engine settings
        engine_group = QGroupBox("PDF Parsing Engine")
        engine_layout = QVBoxLayout()

        # Engine list with status
        self.engine_list = QListWidget()
        self.engine_list.setMaximumHeight(200)
        self._update_engine_list()
        engine_layout.addWidget(self.engine_list)

        # Engine combo for selection
        engine_select_layout = QFormLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Auto (Best Available)", "auto")
        self.engine_combo.addItem("Marker (Layout + OCR + Images)", "marker")
        self.engine_combo.addItem("Docling (IBM, Balanced)", "docling")
        self.engine_combo.addItem("MinerU (Chinese)", "mineru")
        self.engine_combo.addItem("EasyOCR (80+ languages)", "easyocr")
        self.engine_combo.addItem("DocTR (Lightweight OCR)", "doctr")
        self.engine_combo.addItem("Nougat (Academic)", "nougat")
        self.engine_combo.addItem("Surya Lite OCR", "surya-lite")
        self.engine_combo.addItem("PyMuPDF (Fast, No OCR)", "pymupdf")
        self.engine_combo.addItem("PDFPlumber (Tables)", "pdfplumber")
        self.engine_combo.addItem("LlamaParse (Cloud)", "llamaparse")
        self.engine_combo.addItem("Mathpix (Cloud, STEM)", "mathpix")
        self.engine_combo.addItem("MinerU Cloud", "mineru-cloud")
        self.engine_combo.addItem("Doc2X (Cloud, LaTeX)", "doc2x")
        engine_select_layout.addRow("Selected Engine:", self.engine_combo)
        engine_layout.addLayout(engine_select_layout)

        # Download buttons for engines that need models
        download_layout = QHBoxLayout()
        self.download_marker_btn = QPushButton("Download Marker (~3GB)")
        self.download_marker_btn.clicked.connect(lambda: self._download_engine_models("marker"))
        download_layout.addWidget(self.download_marker_btn)

        self.download_docling_btn = QPushButton("Download Docling (~1.5GB)")
        self.download_docling_btn.clicked.connect(lambda: self._download_engine_models("docling"))
        download_layout.addWidget(self.download_docling_btn)

        self.download_easyocr_btn = QPushButton("Download EasyOCR (~300MB)")
        self.download_easyocr_btn.clicked.connect(lambda: self._download_engine_models("easyocr"))
        download_layout.addWidget(self.download_easyocr_btn)

        engine_layout.addLayout(download_layout)

        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)

        # Translation settings
        trans_group = QGroupBox("Translation Settings")
        trans_layout = QFormLayout()

        self.source_lang_combo = QComboBox()
        self.source_lang_combo.addItem("Auto Detect", "auto")
        for code, name in LANGUAGE_MAP.items():
            if code != "auto":
                self.source_lang_combo.addItem(f"{name} ({code})", code)
        trans_layout.addRow("Source Language:", self.source_lang_combo)

        self.target_lang_combo = QComboBox()
        for code, name in LANGUAGE_MAP.items():
            if code != "auto":
                self.target_lang_combo.addItem(f"{name} ({code})", code)
        self.target_lang_combo.setCurrentText("English (en)")
        trans_layout.addRow("Target Language:", self.target_lang_combo)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 1.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(0.3)
        trans_layout.addRow("Temperature:", self.temperature_spin)

        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # Output settings
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout()

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["A4", "letter"])
        output_layout.addRow("Page Size:", self.page_size_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(11)
        output_layout.addRow("Font Size:", self.font_size_spin)

        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(10.0, 50.0)
        self.margin_spin.setSingleStep(1.0)
        self.margin_spin.setValue(20.0)
        output_layout.addRow("Margin (mm):", self.margin_spin)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Model download progress
        self.model_progress_bar = QProgressBar()
        self.model_progress_bar.setVisible(False)
        layout.addWidget(self.model_progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._on_provider_changed()
        self._update_engine_status()

    def _on_provider_changed(self):
        """Update UI based on selected provider."""
        provider = self.provider_combo.currentData()
        if provider == "ollama":
            self.base_url_edit.setEnabled(True)
            self.api_key_edit.setEnabled(False)
            self._refresh_models()
        elif provider == "openai":
            self.base_url_edit.setEnabled(False)
            self.base_url_edit.setText("https://api.openai.com")
            self.api_key_edit.setEnabled(True)
            self._refresh_models()
        else:
            self.base_url_edit.setEnabled(True)
            self.base_url_edit.clear()
            self.api_key_edit.setEnabled(True)
            self.model_combo.clear()
            self.model_combo.setEditable(True)
            self.model_combo.setEditText("")

    def _refresh_models(self):
        """Fetch and populate available models."""
        provider = self.provider_combo.currentData()
        base_url = self.base_url_edit.text()
        api_key = self.api_key_edit.text()

        self.model_combo.clear()
        self.model_combo.addItem("Fetching models...", "")
        self.model_combo.setEnabled(False)
        QApplication.processEvents()

        models = ModelFetcher.get_models(provider, base_url, api_key)

        self.model_combo.clear()
        if models:
            for m in models:
                self.model_combo.addItem(m, m)
            self.model_combo.setEnabled(True)
        else:
            self.model_combo.addItem("No models found (enter manually)", "")
            self.model_combo.setEditable(True)
            self.model_combo.setEnabled(True)

    def _load_settings(self):
        provider = self.config.get("provider", "ollama")
        idx = self.provider_combo.findData(provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        self.base_url_edit.setText(self.config.get("base_url", "http://localhost:11434"))
        self.api_key_edit.setText(self.config.get("api_key", ""))

        model = self.config.get("model", "")
        idx = self.model_combo.findData(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif model:
            self.model_combo.setEditText(model)

        source_lang = self.config.get("source_lang", "auto")
        idx = self.source_lang_combo.findData(source_lang)
        if idx >= 0:
            self.source_lang_combo.setCurrentIndex(idx)

        target_lang = self.config.get("target_lang", "en")
        idx = self.target_lang_combo.findData(target_lang)
        if idx >= 0:
            self.target_lang_combo.setCurrentIndex(idx)

        self.temperature_spin.setValue(self.config.get("temperature", 0.3))
        self.page_size_combo.setCurrentText(self.config.get("page_size", "A4"))
        self.font_size_spin.setValue(self.config.get("font_size", 11))
        self.margin_spin.setValue(self.config.get("margin", 20.0))

    def save_settings(self):
        self.config.set("provider", self.provider_combo.currentData())
        self.config.set("base_url", self.base_url_edit.text())
        self.config.set("api_key", self.api_key_edit.text())

        model_data = self.model_combo.currentData()
        self.config.set("model", model_data if model_data else self.model_combo.currentText())

        self.config.set("source_lang", self.source_lang_combo.currentData())
        self.config.set("target_lang", self.target_lang_combo.currentData())
        self.config.set("temperature", self.temperature_spin.value())
        self.config.set("parse_engine", self.engine_combo.currentData())
        self.config.set("page_size", self.page_size_combo.currentText())
        self.config.set("font_size", self.font_size_spin.value())
        self.config.set("margin", self.margin_spin.value())

        self.config.save_config()

    def _test_connection(self):
        """Test connection to the configured provider."""
        translator = OllamaTranslator(
            provider=self.provider_combo.currentData(),
            base_url=self.base_url_edit.text(),
            model=self.model_combo.currentData() or self.model_combo.currentText(),
            api_key=self.api_key_edit.text(),
        )
        success, message = translator.test_connection()
        if success:
            QMessageBox.information(self, "Connection Test", f"✓ {message}")
        else:
            QMessageBox.warning(self, "Connection Test", f"✗ {message}")

    def _update_engine_list(self):
        """Update engine list with availability status."""
        from .parser import PDFParser
        
        self.engine_list.clear()
        engines = PDFParser.list_available_engines()
        
        for eng in engines:
            if eng["name"] == "auto":
                continue
            
            status = "✓" if eng["available"] else "✗"
            gpu_tag = " [GPU]" if eng["needs_gpu"] else ""
            item_text = f"{status} {eng['display_name']}{gpu_tag} - {eng['model_size']}"
            
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(item_text)
            if eng["available"]:
                item.setForeground(Qt.green)
            else:
                item.setForeground(Qt.red)
            
            self.engine_list.addItem(item)

    def _update_engine_status(self):
        """Update engine availability status."""
        self._update_engine_list()

    def _download_engine_models(self, engine: str):
        """Download models for the specified engine."""
        engine_names = {
            "marker": "Marker (~3GB)",
            "docling": "Docling (~1.5GB)",
            "easyocr": "EasyOCR (~300MB)",
            "mineru": "MinerU (~1.5GB)",
        }
        name = engine_names.get(engine, engine)
        
        reply = QMessageBox.question(
            self,
            "Download Models",
            f"Download {name} models?\nThis enables the {engine} parsing engine.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Disable all download buttons
        self.download_marker_btn.setEnabled(False)
        self.download_docling_btn.setEnabled(False)
        self.download_easyocr_btn.setEnabled(False)
        self.model_progress_bar.setVisible(True)
        self.model_progress_bar.setValue(0)

        self._model_download_worker = ModelDownloadWorker(engine=engine)
        self._model_download_worker.signals.progress.connect(self._on_model_download_progress)
        self._model_download_worker.signals.finished.connect(self._on_model_download_finished)
        self._model_download_worker.signals.error.connect(self._on_model_download_error)
        self._model_download_worker.finished.connect(self._on_model_download_worker_finished)
        self._model_download_worker.start()

    def _on_model_download_progress(self, message: str, current: int, total: int):
        self.model_progress_bar.setValue(current)
        self.model_progress_bar.setFormat(f"{message} %p%")

    def _on_model_download_finished(self, message: str):
        self.model_progress_bar.setValue(100)
        self.model_progress_bar.setFormat("✓ Download complete")
        self._update_engine_list()
        QMessageBox.information(self, "Download Complete", f"✓ {message}")

    def _on_model_download_error(self, error: str):
        self.model_progress_bar.setVisible(False)
        QMessageBox.critical(self, "Download Error", error)

    def _on_model_download_worker_finished(self):
        """Re-enable buttons when worker finishes."""
        self.download_marker_btn.setEnabled(True)
        self.download_docling_btn.setEnabled(True)
        self.download_easyocr_btn.setEnabled(True)
        self.model_progress_bar.setVisible(False)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class YanFuMainWindow(QMainWindow):
    """Main application window for YanFu GUI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"YanFu - Document Translator v{__version__}")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self._parse_worker: ParseWorker | None = None
        self._translate_worker: TranslateWorker | None = None
        self._current_pdf_path: str | None = None
        self._current_md_path: str | None = None
        self._current_md_content: str = ""
        self._parsed_markdown: str = ""
        self.config = ConfigManager()

        self._build_ui()
        self._build_menu()
        self._build_toolbar()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Main splitter: Source (left) | Translation (right)
        main_splitter = QSplitter(Qt.Horizontal)

        # Left panel: PDF Viewer
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("📄 Original Document"))
        left_header.addStretch()
        self.open_pdf_btn = QPushButton("Open PDF")
        self.open_pdf_btn.clicked.connect(self._open_pdf)
        left_header.addWidget(self.open_pdf_btn)
        left_layout.addLayout(left_header)

        self.pdf_viewer = PDFViewerWidget()
        left_layout.addWidget(self.pdf_viewer)

        main_splitter.addWidget(left_widget)

        # Right panel: Translation
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("🌐 Translation"))
        right_header.addStretch()

        self.sync_scroll_check = QCheckBox("Sync Scroll")
        self.sync_scroll_check.setChecked(True)
        self.sync_scroll_check.toggled.connect(self._on_sync_scroll_toggled)
        right_header.addWidget(self.sync_scroll_check)

        self.parse_btn = QPushButton("📄 Parse PDF")
        self.parse_btn.clicked.connect(self._parse_current)
        self.parse_btn.setEnabled(False)
        right_header.addWidget(self.parse_btn)

        self.translate_btn = QPushButton("▶ Translate")
        self.translate_btn.clicked.connect(self._translate_current)
        self.translate_btn.setEnabled(False)
        right_header.addWidget(self.translate_btn)

        self.save_md_btn = QPushButton("💾 Save MD")
        self.save_md_btn.clicked.connect(self._save_markdown)
        self.save_md_btn.setEnabled(False)
        right_header.addWidget(self.save_md_btn)

        self.save_pdf_btn = QPushButton("💾 Save PDF")
        self.save_pdf_btn.clicked.connect(self._save_translated_pdf)
        self.save_pdf_btn.setEnabled(False)
        right_header.addWidget(self.save_pdf_btn)

        right_layout.addLayout(right_header)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.md_editor = QTextEdit()
        self.md_editor.setReadOnly(False)
        self.md_editor.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.md_editor.setPlaceholderText("Translation will appear here...")
        right_layout.addWidget(self.md_editor)

        main_splitter.addWidget(right_widget)

        # Set initial splitter sizes (50/50)
        main_splitter.setSizes([600, 600])

        main_layout.addWidget(main_splitter)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready - Open a PDF to start")

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        open_action = file_menu.addAction("Open PDF...")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_pdf)

        file_menu.addSeparator()
        save_md_action = file_menu.addAction("Save Markdown...")
        save_md_action.setShortcut("Ctrl+S")
        save_md_action.triggered.connect(self._save_markdown)

        save_pdf_action = file_menu.addAction("Save Translated PDF...")
        save_pdf_action.triggered.connect(self._save_translated_pdf)

        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        tools_menu = menubar.addMenu("&Tools")
        settings_action = tools_menu.addAction("Settings...")
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)

        config_action = tools_menu.addAction("Configuration Wizard...")
        config_action.triggered.connect(self._run_config_wizard)

        help_menu = menubar.addMenu("&Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._show_about)

    def _build_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("📂 Open PDF", self)
        open_action.triggered.connect(self._open_pdf)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        parse_action = QAction("📄 Parse", self)
        parse_action.triggered.connect(self._parse_current)
        toolbar.addAction(parse_action)

        translate_action = QAction("▶ Translate", self)
        translate_action.triggered.connect(self._translate_current)
        toolbar.addAction(translate_action)

        toolbar.addSeparator()

        save_action = QAction("💾 Save", self)
        save_menu = QMenu(self)
        save_menu.addAction("Save Markdown", self._save_markdown)
        save_menu.addAction("Save Translated PDF", self._save_translated_pdf)
        save_action.setMenu(save_menu)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        self.sync_action = QAction("🔗 Sync Scroll", self)
        self.sync_action.setCheckable(True)
        self.sync_action.setChecked(True)
        self.sync_action.toggled.connect(self._on_sync_scroll_toggled)
        toolbar.addAction(self.sync_action)

    def _open_pdf(self):
        """Open a PDF file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if file_path:
            self._load_pdf(file_path)

    def _load_pdf(self, file_path: str):
        """Load and display PDF."""
        try:
            print(f"\n[YanFu] Loading PDF: {file_path}")
            self.pdf_viewer.load_pdf(file_path)
            self._current_pdf_path = file_path
            self._parsed_markdown = ""
            self._current_md_content = ""
            self.md_editor.clear()
            self.parse_btn.setEnabled(True)
            self.translate_btn.setEnabled(False)
            self.save_md_btn.setEnabled(False)
            self.save_pdf_btn.setEnabled(False)
            pages = self.pdf_viewer.total_pages
            print(f"[YanFu] PDF loaded successfully: {pages} pages")
            self.status.showMessage(f"Loaded: {Path(file_path).name} ({pages} pages)")
        except Exception as e:
            print(f"[YanFu] ERROR loading PDF: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{str(e)}")

    def _parse_current(self):
        """Parse the currently loaded PDF in background thread."""
        if not self._current_pdf_path:
            QMessageBox.warning(self, "No PDF", "Please open a PDF first.")
            return

        print("\n" + "=" * 60)
        print("[YanFu] Starting PDF parsing...")
        print(f"[YanFu] Input: {self._current_pdf_path}")
        print("=" * 60)

        output_dir = str(Path(self._current_pdf_path).parent)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.parse_btn.setEnabled(False)
        self.translate_btn.setEnabled(False)
        self.status.showMessage("Parsing PDF...")

        self._parse_worker = ParseWorker(
            file_path=self._current_pdf_path,
            output_dir=output_dir,
            use_ocr=self.config.get("use_ocr", False),
            parse_engine=self.config.get("parse_engine", "auto"),
        )
        self._parse_worker.signals.started.connect(self._on_parse_started)
        self._parse_worker.signals.progress.connect(self._on_parse_progress)
        self._parse_worker.signals.finished.connect(self._on_parse_finished)
        self._parse_worker.signals.error.connect(self._on_parse_error)
        self._parse_worker.start()

    def _on_parse_started(self, file_path: str):
        print(f"[YanFu] Parse worker started: {Path(file_path).name}")

    def _on_parse_progress(self, message: str, current: int, total: int):
        self.progress_bar.setValue(current)
        self.status.showMessage(message)

    def _on_parse_finished(self, result: ParseResult):
        print(f"\n[YanFu] ✅ Parsing completed!")
        print(f"[YanFu] Pages: {result.page_count}")
        print(f"[YanFu] Images: {len(result.images)}")
        print(f"[YanFu] Engine: {result.engine}")
        print(f"[YanFu] Markdown: {len(result.markdown)} chars")

        self._parsed_markdown = result.markdown
        self.md_editor.setPlainText(result.markdown)
        self.translate_btn.setEnabled(True)
        self.parse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status.showMessage(f"Parsed: {result.page_count} pages, {len(result.images)} images")

    def _on_parse_error(self, error: str):
        print(f"\n[YanFu] ❌ Parse error: {error}")
        QMessageBox.critical(self, "Parse Error", error)
        self.parse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status.showMessage("Parse failed")

    def _translate_current(self):
        """Translate the parsed markdown in background thread."""
        if not self._parsed_markdown:
            QMessageBox.warning(self, "Not Parsed", "Please parse the PDF first.")
            return

        if not self.config.is_configured():
            QMessageBox.warning(self, "Not Configured", "Please configure your translation provider in Settings.")
            return

        print("\n" + "=" * 60)
        print("[YanFu] Starting translation...")
        print(f"[YanFu] Input: {self._current_pdf_path}")
        print(f"[YanFu] Provider: {self.config.get('provider')}")
        print(f"[YanFu] Model: {self.config.get('model')}")
        print(f"[YanFu] Source: {self.config.get('source_lang', 'auto')} → Target: {self.config.get('target_lang', 'en')}")
        print("=" * 60)

        output_dir = str(Path(self._current_pdf_path).parent)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.parse_btn.setEnabled(False)
        self.status.showMessage("Translating...")

        self._translate_worker = TranslateWorker(
            markdown=self._parsed_markdown,
            source_lang=self.config.get("source_lang", "auto"),
            target_lang=self.config.get("target_lang", "en"),
            config=self.config,
            output_dir=output_dir,
            file_path=self._current_pdf_path,
            page_size=self.config.get("page_size", "A4"),
            font_size=self.config.get("font_size", 11),
            margin=self.config.get("margin", 20.0),
            temperature=self.config.get("temperature", 0.3),
        )
        self._translate_worker.signals.started.connect(self._on_translate_started)
        self._translate_worker.signals.progress.connect(self._on_translate_progress)
        self._translate_worker.signals.finished.connect(self._on_translate_finished)
        self._translate_worker.signals.error.connect(self._on_translate_error)
        self._translate_worker.start()

    def _on_translate_started(self, file_path: str):
        print(f"[YanFu] Translate worker started: {Path(file_path).name}")

    def _on_translate_progress(self, message: str, current: int, total: int):
        if total > 0:
            self.progress_bar.setValue(int((current / total) * 100))
        self.status.showMessage(message)

    def _on_translate_finished(self, translated_md: str, output_md: str, output_pdf: str):
        print(f"\n[YanFu] ✅ Translation completed successfully!")
        print(f"[YanFu] Markdown: {output_md}")
        print(f"[YanFu] PDF: {output_pdf}")

        self._current_md_path = output_md
        self._current_md_content = translated_md
        self.md_editor.setPlainText(translated_md)
        self.save_md_btn.setEnabled(True)
        self.save_pdf_btn.setEnabled(True)
        self.translate_btn.setEnabled(True)
        self.parse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status.showMessage(f"Translation completed: {output_pdf}")
        print("=" * 60)

    def _on_translate_error(self, error: str):
        print(f"\n[YanFu] ❌ Translation error: {error}")
        QMessageBox.critical(self, "Translation Error", error)
        self.translate_btn.setEnabled(True)
        self.parse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status.showMessage("Translation failed")
        print("=" * 60)

    def _save_markdown(self):
        """Save markdown content to file."""
        if not self._current_md_content:
            QMessageBox.warning(self, "No Content", "No translation to save.")
            return

        if self._current_md_path:
            default_path = self._current_md_path
        else:
            default_path = str(Path(self._current_pdf_path).parent / "translation.md") if self._current_pdf_path else "translation.md"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown",
            default_path,
            "Markdown Files (*.md);;All Files (*)",
        )
        if file_path:
            try:
                content = self.md_editor.toPlainText()
                Path(file_path).write_text(content, encoding="utf-8")
                self._current_md_path = file_path
                self.status.showMessage(f"Saved: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def _save_translated_pdf(self):
        """Save translated PDF."""
        if not self._current_pdf_path:
            return

        default_path = str(Path(self._current_pdf_path).parent / f"{Path(self._current_pdf_path).stem}_translated.pdf")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Translated PDF",
            default_path,
            "PDF Files (*.pdf);;All Files (*)",
        )
        if file_path:
            try:
                content = self.md_editor.toPlainText()
                render_pdf(
                    content,
                    output_path=file_path,
                    page_size=self.config.get("page_size", "A4"),
                    font_size=self.config.get("font_size", 11),
                    margin=self.config.get("margin", 20.0),
                )
                self.status.showMessage(f"Saved: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save PDF:\n{str(e)}")

    def _on_sync_scroll_toggled(self, checked: bool):
        """Handle sync scroll toggle."""
        self.pdf_viewer.set_sync_enabled(checked)
        self.sync_action.setChecked(checked)
        self.sync_scroll_check.setChecked(checked)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            dialog.save_settings()
            self.config = dialog.config
            self.status.showMessage("Settings saved")

    def _run_config_wizard(self):
        from .config_wizard import run_config_wizard
        run_config_wizard()
        self.config = ConfigManager()
        self.status.showMessage("Configuration wizard completed")

    def _show_about(self):
        QMessageBox.about(
            self,
            "About YanFu",
            f"<h2>YanFu v{__version__}</h2>"
            "<p>PDF/CAJ Document Translator</p>"
            "<p>Translate documents using Ollama or OpenAI-compatible APIs with layout-preserving PDF generation.</p>"
            "<p>Licensed under GPL-3.0-or-later</p>"
            "<p><a href='https://github.com/CodeOfMe/YanFu'>https://github.com/CodeOfMe/YanFu</a></p>",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_gui():
    """Launch the YanFu GUI application."""
    import os

    # Set up detailed logging to terminal
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger.setLevel(logging.DEBUG)

    # Suppress MuPDF stderr errors
    try:
        devnull = open(os.devnull, 'w')
        sys.stderr = devnull
    except Exception:
        pass

    print("=" * 60)
    print("  YanFu - Document Translator v" + __version__)
    print("=" * 60)
    print()
    print("[YanFu] Starting GUI...")
    print(f"[YanFu] Python: {sys.version}")
    print(f"[YanFu] Platform: {sys.platform}")
    print()

    app = QApplication(sys.argv)
    app.setApplicationName("YanFu")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CodeOfMe")
    app.setStyle("Fusion")

    print("[YanFu] QApplication initialized")

    window = YanFuMainWindow()
    window.show()

    print("[YanFu] Main window shown")
    print("[YanFu] GUI ready. Open a PDF to start translation.")
    print()

    sys.exit(app.exec())
