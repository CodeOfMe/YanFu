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
        device: str = "auto",
    ):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.use_ocr = use_ocr
        self.parse_engine = parse_engine
        self.device = device
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

            # Build engine list: selected engine first, then pymupdf as last-resort fallback
            engines_to_try = [self.parse_engine]
            if self.parse_engine not in ("pymupdf",):
                engines_to_try.append("pymupdf")

            last_error = None
            for engine in engines_to_try:
                try:
                    result = parse_document(
                        self.file_path,
                        engine=engine,
                        use_ocr=self.use_ocr,
                        output_dir=str(image_dir),
                        device=self.device,
                    )

                    markdown = result.get("markdown", "")
                    # If user explicitly chose an engine, use its result even if text is short
                    if engine == self.parse_engine:
                        pass  # Always accept user's choice
                    elif len(markdown.strip()) < 10 and engine != engines_to_try[-1]:
                        logger.warning(f"[ParseWorker] Fallback engine '{engine}' gave too little text ({len(markdown)} chars), trying next...")
                        continue

                    if self.is_cancelled():
                        self.signals.progress.emit("Cancelled", 100, 100)
                        return

                    self.signals.progress.emit("Parsing complete", 100, 100)
                    parse_result = ParseResult(
                        success=True,
                        markdown=markdown,
                        images=result.get("images", {}),
                        page_count=result.get("page_count", 0),
                        engine=engine,
                    )
                    logger.debug(f"[ParseWorker] Done: engine={engine}, pages={parse_result.page_count}, images={len(parse_result.images)}, text={len(markdown)} chars")
                    self.signals.finished.emit(parse_result)
                    return

                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[ParseWorker] Engine '{engine}' failed: {e}")
                    continue

            raise RuntimeError(f"All engines failed. Last: {last_error}")

        except Exception as e:
            logger.error(f"[ParseWorker] Fatal: {e}")
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
            print(f"\n[TranslateWorker] ========================================")
            print(f"[TranslateWorker] Provider: {self.config.get('provider')}")
            print(f"[TranslateWorker] Model:    {self.config.get('model')}")
            print(f"[TranslateWorker] Base URL: {self.config.get('base_url')}")
            print(f"[TranslateWorker] Source:   {self.source_lang} → {self.target_lang}")
            
            from .translator import _split_markdown
            chunks = _split_markdown(self.markdown)
            total_chunks = len(chunks)
            print(f"[TranslateWorker] Markdown: {len(self.markdown)} chars → {total_chunks} chunks")
            print(f"[TranslateWorker] ========================================")

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
                    return

                if chunk.strip():
                    print(f"[TranslateWorker] Chunk {i+1}/{total_chunks} ({len(chunk)} chars)...", end=" ", flush=True)
                    self.signals.progress.emit(f"Translating chunk {i+1}/{total_chunks}...", i, total_chunks)
                    translated = translator.translate(chunk, self.source_lang, self.target_lang)
                    translated_chunks.append(translated)
                    print(f"→ {len(translated)} chars")
                else:
                    translated_chunks.append(chunk)

            if self.is_cancelled():
                return

            print(f"\n[TranslateWorker] Rendering PDF...")
            self.signals.progress.emit("Rendering PDF...", total_chunks, total_chunks)

            translated_markdown = "\n\n".join(translated_chunks)
            translated_markdown = clean_markdown(translated_markdown)
            print(f"[TranslateWorker] Translated: {len(translated_markdown)} chars")

            stem = Path(self.file_path).stem
            output_md = str(Path(self.output_dir) / f"{stem}_{self.target_lang}.md")
            Path(output_md).write_text(translated_markdown, encoding="utf-8")
            print(f"[TranslateWorker] Saved MD: {output_md}")

            image_dir = Path(self.output_dir) / f"{stem}_images"
            output_pdf = str(Path(self.output_dir) / f"{stem}_{self.target_lang}.pdf")
            render_pdf(translated_markdown, output_path=output_pdf,
                       image_dir=str(image_dir) if image_dir.exists() else None,
                       page_size=self.page_size, font_size=self.font_size, margin=self.margin)
            print(f"[TranslateWorker] Saved PDF: {output_pdf}")

            self.signals.progress.emit("Translation complete", total_chunks, total_chunks)
            self.signals.finished.emit(translated_markdown, output_md, output_pdf)

        except Exception as e:
            print(f"\n[TranslateWorker] ❌ FATAL: {e}")
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


# ---------------------------------------------------------------------------
# PDF Viewer Widget
# ---------------------------------------------------------------------------

class MarkdownViewer(QWidget):
    """Widget to display markdown with toggle between rendered HTML and plain text."""
    
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._raw_md = ""
        self._rendered = True
        self._build_ui(title)

    def _build_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._editor = QTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 10))
        layout.addWidget(self._editor)

    def clear(self):
        self._raw_md = ""
        self._editor.clear()

    def setReadOnly(self, ro: bool):
        self._editor.setReadOnly(ro)

    def setPlainText(self, text: str):
        self._raw_md = text
        self._editor.setPlainText(text)

    def setPlaceholderText(self, text: str):
        self._editor.setPlaceholderText(text)

    def set_markdown(self, md: str):
        self._raw_md = md
        if self._rendered:
            self._show_rendered()
        else:
            self._show_plain()

    def toggle_view(self):
        self._rendered = not self._rendered
        if self._raw_md:
            self.set_markdown(self._raw_md)

    def _show_rendered(self):
        """Convert markdown to HTML and display."""
        try:
            from markdown import markdown
            html = markdown(self._raw_md, extensions=['tables', 'fenced_code', 'codehilite'])
            css = "<style>body{font-family: -apple-system, sans-serif; font-size: 13px; line-height: 1.6;} table{border-collapse: collapse; width: 100%;} td,th{border: 1px solid #ddd; padding: 6px;} code{background: #f5f5f5; padding: 2px 4px; border-radius: 3px;} pre{background: #f5f5f5; padding: 8px; border-radius: 4px;} blockquote{border-left: 3px solid #ddd; margin-left: 0; padding-left: 12px; color: #666;} h1,h2,h3{border-bottom: 1px solid #eee; padding-bottom: 4px;}</style>"
            self._editor.setHtml(css + html)
        except Exception:
            self._show_plain()

    def _show_plain(self):
        self._editor.setPlainText(self._raw_md)

    def editor(self):
        return self._editor


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

class _ModelFetchWorker(QThread):
    """Background thread for fetching Ollama/OpenAI models."""

    class _Signals(QObject):
        finished = Signal(list, str)  # models, current_model

    def __init__(self, provider: str, base_url: str, api_key: str, current_model: str):
        super().__init__()
        self._provider = provider
        self._base_url = base_url
        self._api_key = api_key
        self._current_model = current_model
        self.signals = self._Signals()

    def run(self):
        try:
            models = ModelFetcher.get_models(self._provider, self._base_url, self._api_key)
        except Exception:
            models = []
        self.signals.finished.emit(models, self._current_model)


class _EngineModelDownloader(QThread):
    """Background thread for downloading selected engine's models."""

    class _Signals(QObject):
        progress = Signal(str)
        finished = Signal(str)
        error = Signal(str)

    def __init__(self, engine: str, force: bool = False):
        super().__init__()
        self._engine = engine
        self._force = force
        self.signals = self._Signals()

    def run(self):
        import os, shutil
        from pathlib import Path
        from platformdirs import user_cache_dir
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        try:
            if self._engine == "marker":
                if self._force:
                    from platformdirs import user_cache_dir
                    cache = Path(user_cache_dir("datalab")) / "models"
                    if cache.exists():
                        shutil.rmtree(cache)
                        print(f"[YanFu] Cleared cache: {cache}")
                
                from platformdirs import user_cache_dir
                cache_dir = Path(user_cache_dir("datalab")) / "models"
                print(f"\n[YanFu] Loading marker-pdf models...")
                print(f"[YanFu] 📁 Cache: {cache_dir}")
                print(f"[YanFu] (First run downloads ~3 GB)")
                self.signals.progress.emit("Downloading marker models (check terminal)...")
                
                # Exactly like NuoYi: just call create_model_dict()
                from huggingface_hub.utils import enable_progress_bars
                enable_progress_bars()
                from marker.models import create_model_dict
                create_model_dict()
                
                # Verify
                total = sum(f.stat().st_size for f in cache_dir.rglob("*.safetensors") if f.is_file()) if cache_dir.exists() else 0
                if total > 0:
                    print(f"[YanFu] ✅ Models ready: {total/1024/1024:.0f}MB at {cache_dir}")
                    self.signals.finished.emit(f"Ready ({total/1024/1024:.0f}MB)")
                else:
                    self.signals.error.emit(f"No models at {cache_dir}. Check terminal output.")

            elif self._engine == "docling":
                if self._force:
                    hf_cache = Path.home() / ".cache" / "huggingface"
                    if hf_cache.exists():
                        shutil.rmtree(hf_cache)
                hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
                print(f"\n[YanFu] 📁 HF cache: {hf_cache}")
                self.signals.progress.emit(f"Cache: {hf_cache}")
                self.signals.progress.emit("Downloading Docling models (~1.5GB)...")
                from docling.document_converter import DocumentConverter
                DocumentConverter()
                print(f"[YanFu] ✅ Docling ready at: {hf_cache}")
                self.signals.finished.emit(f"Docling ready\n📁 {hf_cache}")

            elif self._engine == "easyocr":
                if self._force:
                    import easyocr
                    easyocr_dir = Path(easyocr.__file__).parent / "model"
                    if easyocr_dir.exists():
                        shutil.rmtree(easyocr_dir)
                import easyocr
                easyocr_dir = Path(easyocr.__file__).parent / "model"
                print(f"\n[YanFu] 📁 EasyOCR cache: {easyocr_dir}")
                self.signals.progress.emit(f"Cache: {easyocr_dir}")
                self.signals.progress.emit("Downloading EasyOCR models (~300MB)...")
                easyocr.Reader(['en', 'ch_sim'])
                print(f"[YanFu] ✅ EasyOCR ready at: {easyocr_dir}")
                self.signals.finished.emit(f"EasyOCR ready\n📁 {easyocr_dir}")

            elif self._engine == "doctr":
                self.signals.progress.emit("Downloading DocTR models (~500MB)...")
                from doctr.models import ocr_predictor
                ocr_predictor(pretrained=True)
                self.signals.finished.emit("DocTR models ready")

            elif self._engine == "nougat":
                self.signals.progress.emit("Downloading Nougat models (~1.5GB)...")
                from nougat import NougatModel
                from nougat.utils.checkpoint import get_checkpoint
                get_checkpoint()
                self.signals.finished.emit("Nougat models ready")

            elif self._engine == "surya-lite":
                self.signals.progress.emit("Downloading Surya Lite models (~2GB)...")
                from surya.recognition import RecognitionPredictor
                from surya.foundation import FoundationPredictor
                FoundationPredictor()
                self.signals.finished.emit("Surya Lite models ready")

            elif self._engine == "mineru":
                self.signals.progress.emit("MinerU: run magic-pdf-model-download -d")
                self.signals.finished.emit("MinerU ready (if pre-downloaded)")

            elif self._engine in ("pymupdf", "pdfplumber"):
                self.signals.finished.emit(f"'{self._engine}' needs no download — ready.")

            elif self._engine in ("llamaparse", "mathpix", "mineru-cloud", "doc2x"):
                self.signals.error.emit(f"'{self._engine}' is cloud. Set API key env var first.")

            else:
                self.signals.finished.emit(f"'{self._engine}' ready.")
        except Exception as e:
            self.signals.error.emit(str(e))


class SettingsDialog(QDialog):
    """Settings dialog for translation configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(700)
        self.config = ConfigManager()
        self._model_fetch_worker = None
        self._dl_worker: _EngineModelDownloader | None = None
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
        self.engine_list.setMaximumHeight(140)
        engine_layout.addWidget(self.engine_list)

        # Engine + device selection
        engine_select_layout = QFormLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Auto (Best Available)", "auto")
        self.engine_combo.addItem("Marker (Layout+OCR+Images, ~3GB)", "marker")
        self.engine_combo.addItem("MinerU (Chinese, ~1.5GB)", "mineru")
        self.engine_combo.addItem("Docling (IBM, ~1.5GB)", "docling")
        self.engine_combo.addItem("EasyOCR (80 languages, ~300MB)", "easyocr")
        self.engine_combo.addItem("DocTR (Light OCR, ~500MB)", "doctr")
        self.engine_combo.addItem("Nougat (Academic, ~1.5GB)", "nougat")
        self.engine_combo.addItem("PyMuPDF (Fast, No Models)", "pymupdf")
        self.engine_combo.addItem("PDFPlumber (Tables, No Models)", "pdfplumber")
        self.engine_combo.addItem("LlamaParse (Cloud, API Key)", "llamaparse")
        self.engine_combo.addItem("Mathpix (Cloud STEM, API Key)", "mathpix")
        self.engine_combo.addItem("MinerU Cloud (API Key)", "mineru-cloud")
        self.engine_combo.addItem("Doc2X (Cloud LaTeX, API Key)", "doc2x")
        engine_select_layout.addRow("Engine:", self.engine_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItem("Auto Detect", "auto")
        self.device_combo.addItem("CPU Only", "cpu")
        # Check available GPU backends
        try:
            import torch
            if torch.cuda.is_available():
                self.device_combo.addItem("NVIDIA CUDA", "cuda")
            if hasattr(torch, 'mps') and torch.backends.mps.is_available():
                self.device_combo.addItem("Apple MPS", "mps")
        except ImportError:
            pass
        # DirectML for Windows (Vulkan-compatible)
        try:
            import torch_directml
            self.device_combo.addItem("DirectML (Vulkan)", "dml")
        except ImportError:
            pass
        engine_select_layout.addRow("Device:", self.device_combo)
        engine_layout.addLayout(engine_select_layout)

        # Download + hint
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("⬇ Download Selected Engine Models")
        self.download_btn.clicked.connect(self._download_selected_engine)
        btn_row.addWidget(self.download_btn)

        self.redownload_btn = QPushButton("🔄 Re-download (Force)")
        self.redownload_btn.clicked.connect(self._force_redownload)
        self.redownload_btn.setToolTip("Force re-download models even if already cached")
        btn_row.addWidget(self.redownload_btn)
        btn_row.addStretch()
        engine_layout.addLayout(btn_row)

        self.engine_hint = QLabel("Models auto-download on first Parse. Click download to pre-fetch.")
        self.engine_hint.setStyleSheet("color: #888; font-size: 11px;")
        engine_layout.addWidget(self.engine_hint)

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
        # Trigger async model loading after UI is shown
        self._refresh_models()

    def _on_provider_changed(self):
        """Update UI based on selected provider (non-blocking)."""
        provider = self.provider_combo.currentData()
        if provider == "ollama":
            self.base_url_edit.setEnabled(True)
            self.api_key_edit.setEnabled(False)
        elif provider == "openai":
            self.base_url_edit.setEnabled(False)
            self.base_url_edit.setText("https://api.openai.com")
            self.api_key_edit.setEnabled(True)
        else:
            self.base_url_edit.setEnabled(True)
            self.base_url_edit.clear()
            self.api_key_edit.setEnabled(True)
            self.model_combo.clear()
            self.model_combo.setEditable(True)
            self.model_combo.setEditText("")
            return  # Don't fetch for custom provider

    def _refresh_models(self):
        """Fetch and populate available models in background thread."""
        provider = self.provider_combo.currentData()
        base_url = self.base_url_edit.text()
        api_key = self.api_key_edit.text()
        current_model = self.model_combo.currentData() or self.model_combo.currentText()

        self.model_combo.clear()
        self.model_combo.addItem("Fetching models...", "")
        self.model_combo.setEnabled(False)

        # Run fetch in background thread to avoid UI freeze
        self._model_fetch_worker = _ModelFetchWorker(provider, base_url, api_key, current_model)
        self._model_fetch_worker.signals.finished.connect(self._on_models_fetched)
        self._model_fetch_worker.start()

    def _on_models_fetched(self, models: list[str], current_model: str):
        """Handle fetched models."""
        self.model_combo.clear()
        if models:
            for m in models:
                self.model_combo.addItem(m, m)
            if current_model:
                idx = self.model_combo.findData(current_model)
                if idx >= 0:
                    self.model_combo.setCurrentIndex(idx)
            self.model_combo.setEnabled(True)
        else:
            self.model_combo.addItem("No models found (enter manually)", "")
            self.model_combo.setEditable(True)
            self.model_combo.setEnabled(True)
            if current_model:
                self.model_combo.setEditText(current_model)

    def _download_selected_engine(self):
        """Pre-download models for the currently selected engine."""
        self._run_download(force=False)

    def _force_redownload(self):
        """Force re-download models, clearing cache first."""
        engine = self.engine_combo.currentData()
        if engine in ("pymupdf", "pdfplumber", "auto"):
            QMessageBox.information(self, "Not Needed", f"Engine '{engine}' has no models to download.")
            return

        reply = QMessageBox.warning(
            self, "Force Re-download",
            f"This will DELETE cached models for '{engine}' and re-download them.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._run_download(force=True)

    def _run_download(self, force: bool = False):
        engine = self.engine_combo.currentData()
        if engine in ("pymupdf", "pdfplumber", "auto"):
            QMessageBox.information(self, "Not Needed", f"Engine '{engine}' has no models to download.")
            return

        self.download_btn.setEnabled(False)
        self.redownload_btn.setEnabled(False)
        self.download_btn.setText("Downloading...")

        self._dl_worker = _EngineModelDownloader(engine, force=force)
        self._dl_worker.signals.progress.connect(lambda msg: self.download_btn.setText(msg))
        self._dl_worker.signals.finished.connect(self._on_engine_dl_done)
        self._dl_worker.signals.error.connect(self._on_engine_dl_error)
        self._dl_worker.start()

    def _on_engine_dl_done(self, msg: str):
        self.download_btn.setEnabled(True)
        self.redownload_btn.setEnabled(True)
        self.download_btn.setText("⬇ Download Selected Engine Models")
        self._update_engine_list()
        QMessageBox.information(self, "Done", msg)

    def _on_engine_dl_error(self, err: str):
        self.download_btn.setEnabled(True)
        self.redownload_btn.setEnabled(True)
        self.download_btn.setText("⬇ Download Selected Engine Models")
        QMessageBox.critical(self, "Download Failed", err)

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

        # Engine
        eng = self.config.get("parse_engine", "pymupdf")
        idx = self.engine_combo.findData(eng)
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)

        # Device
        dev = self.config.get("device", "auto")
        idx = self.device_combo.findData(dev)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)

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
        self.config.set("device", self.device_combo.currentData())
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

        # Keep strong references to ALL threads to prevent GC
        self._workers: list = []
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

        # Main splitter: PDF (left) | Markdown Preview (middle) | Translation (right)
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

        # Middle panel: Parsed Markdown preview
        mid_widget = QWidget()
        mid_layout = QVBoxLayout(mid_widget)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_header = QHBoxLayout()
        mid_header.addWidget(QLabel("📝 Parsed Markdown"))
        mid_header.addStretch()
        self.md_toggle_btn = QPushButton("🔄 Plain")
        self.md_toggle_btn.setFixedWidth(80)
        self.md_toggle_btn.clicked.connect(lambda: self._toggle_view("md"))
        mid_header.addWidget(self.md_toggle_btn)
        mid_layout.addLayout(mid_header)
        self.md_preview = MarkdownViewer()
        mid_layout.addWidget(self.md_preview)
        main_splitter.addWidget(mid_widget)

        # Right panel: Translation output
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
        self.tl_toggle_btn = QPushButton("🔄 Plain")
        self.tl_toggle_btn.setFixedWidth(80)
        self.tl_toggle_btn.clicked.connect(lambda: self._toggle_view("tl"))
        right_header.addWidget(self.tl_toggle_btn)
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

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.md_editor = MarkdownViewer()
        self.md_editor.setReadOnly(False)
        self.md_editor.setPlaceholderText("Translation will appear here...")
        right_layout.addWidget(self.md_editor)
        main_splitter.addWidget(right_widget)

        main_splitter.setSizes([400, 400, 400])
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

    def _toggle_view(self, which: str):
        """Toggle between rendered HTML and plain text."""
        if which == "md":
            self.md_preview.toggle_view()
            self.md_toggle_btn.setText("🔄 Rendered" if self.md_preview._rendered else "🔄 Plain")
        else:
            self.md_editor.toggle_view()
            self.tl_toggle_btn.setText("🔄 Rendered" if self.md_editor._rendered else "🔄 Plain")

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
        self.translate_btn.setEnabled(False)
        self.status.showMessage("Parsing PDF...")

        self._parse_worker = ParseWorker(
            file_path=self._current_pdf_path,
            output_dir=output_dir,
            use_ocr=self.config.get("use_ocr", False),
            parse_engine=self.config.get("parse_engine", "auto"),
            device=self.config.get("device", "auto"),
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
        self.progress_bar.setVisible(False)
        self.status.showMessage(f"Parsed: {result.page_count} pages, {len(result.images)} images")

    def _on_parse_error(self, error: str):
        print(f"\n[YanFu] ❌ Parse error: {error}")
        QMessageBox.critical(self, "Parse Error", error)
        self.progress_bar.setVisible(False)
        self.status.showMessage("Parse failed")

    def _translate_current(self):
        """Translate - parses PDF first if needed, then translates."""
        if not self._current_pdf_path:
            QMessageBox.warning(self, "No PDF", "Please open a PDF first.")
            return

        if not self.config.is_configured():
            QMessageBox.warning(self, "Not Configured", "Please configure your translation provider in Settings.")
            return

        if not self._parsed_markdown:
            # Need to parse first, then translate
            self._parse_then_translate()
        else:
            self._do_translate()

    def _parse_then_translate(self):
        """Parse PDF first, then automatically translate."""
        print("\n" + "=" * 60)
        print("[YanFu] Parsing + Translating...")
        print(f"[YanFu] Input: {self._current_pdf_path}")
        print(f"[YanFu] Provider: {self.config.get('provider')}")
        print(f"[YanFu] Model: {self.config.get('model')}")
        print(f"[YanFu] Source: {self.config.get('source_lang', 'auto')} → Target: {self.config.get('target_lang', 'en')}")
        print("=" * 60)

        output_dir = str(Path(self._current_pdf_path).parent)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.status.showMessage("Parsing PDF...")

        # Wait for any previous worker
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.quit()
            self._parse_worker.wait(1000)

        self._parse_worker = ParseWorker(
            file_path=self._current_pdf_path,
            output_dir=output_dir,
            use_ocr=self.config.get("use_ocr", False),
            parse_engine=self.config.get("parse_engine", "pymupdf"),
            device=self.config.get("device", "auto"),
        )
        self._workers.append(self._parse_worker)
        self._parse_worker.signals.finished.connect(self._on_parse_then_translate)
        self._parse_worker.signals.error.connect(self._on_parse_error)
        self._parse_worker.finished.connect(lambda: self._workers.remove(self._parse_worker) if self._parse_worker in self._workers else None)
        self._parse_worker.start()

    def _on_parse_then_translate(self, result: ParseResult):
        """After parsing, start translation."""
        print(f"\n[YanFu] ✅ Parsed: {result.engine}, {result.page_count}p, {len(result.images)}img, {len(result.markdown)} chars")
        self._parsed_markdown = result.markdown
        self.md_preview.set_markdown(result.markdown)  # Show in preview
        self.md_editor.set_markdown("")  # Clear translation
        
        if not self._parsed_markdown.strip():
            QMessageBox.warning(self, "No Text", "PDF has no extractable text. It may be fully image-based.")
            self.translate_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            return
        self._do_translate()

    def _do_translate(self):
        """Translate already-parsed markdown."""
        print("\n" + "=" * 60)
        print("[YanFu] Starting translation...")
        print("=" * 60)

        output_dir = str(Path(self._current_pdf_path).parent)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.status.showMessage("Translating...")

        # Wait for any previous worker to finish
        if self._translate_worker and self._translate_worker.isRunning():
            self._translate_worker.quit()
            self._translate_worker.wait(1000)

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
        self._workers.append(self._translate_worker)
        self._translate_worker.signals.progress.connect(self._on_translate_progress)
        self._translate_worker.signals.finished.connect(self._on_translate_finished)
        self._translate_worker.signals.error.connect(self._on_translate_error)
        self._translate_worker.finished.connect(lambda: self._workers.remove(self._translate_worker) if self._translate_worker in self._workers else None)
        self._translate_worker.start()

        output_dir = str(Path(self._current_pdf_path).parent)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
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
        self.md_editor.set_markdown(translated_md)
        self.save_md_btn.setEnabled(True)
        self.save_pdf_btn.setEnabled(True)
        self.translate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status.showMessage(f"Translation completed: {output_pdf}")
        print("=" * 60)

    def _on_translate_error(self, error: str):
        print(f"\n[YanFu] ❌ Translation error: {error}")
        QMessageBox.critical(self, "Translation Error", error)
        self.translate_btn.setEnabled(True)
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
                content = self.md_editor.editor().toPlainText()
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
                content = self.md_editor.editor().toPlainText()
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

    # Use HF mirror for mainland China
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

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
