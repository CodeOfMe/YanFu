"""YanFu - PySide6 GUI with PDF viewer, translation, and synchronized scrolling.

Provides a complete graphical interface for document translation
with side-by-side PDF viewing, synchronized scrolling, and model management.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QImage, QPixmap, QTextCursor
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
from .translator import ConfigManager, ModelFetcher, OllamaTranslator
from .utils import LANGUAGE_MAP, find_documents

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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
# Worker signals and thread
# ---------------------------------------------------------------------------

class WorkerSignals(QObject):
    """Signals for translation worker."""
    progress = Signal(str, str)
    task_started = Signal(str, int, int)
    task_finished = Signal(object)
    all_finished = Signal(list)
    error = Signal(str)


class TranslationWorker(QThread):
    """Independent thread for running translation tasks."""

    def __init__(
        self,
        tasks: list[TranslationTask],
        output_dir: str,
    ):
        super().__init__()
        self.tasks = tasks
        self.output_dir = output_dir
        self._cancel_requested = False
        self._mutex = QMutex()
        self.signals = WorkerSignals()

    def cancel(self):
        """Request cancellation."""
        with QMutexLocker(self._mutex):
            self._cancel_requested = True

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        with QMutexLocker(self._mutex):
            return self._cancel_requested

    def run(self):
        """Execute translation tasks in background thread."""
        results = []

        for i, task in enumerate(self.tasks):
            if self.is_cancelled():
                self.signals.progress.emit("Cancelled by user", "warn")
                break

            filename = Path(task.file_path).name
            self.signals.task_started.emit(filename, i + 1, len(self.tasks))
            self.signals.progress.emit(f"Processing: {filename}", "info")

            try:
                processor = DocumentProcessor(
                    output_dir=self.output_dir,
                    target_lang=task.target_lang,
                    source_lang=task.source_lang,
                    use_ocr=task.use_ocr,
                    parse_engine=task.parse_engine,
                    temperature=task.temperature,
                    page_size=task.page_size,
                    font_name=task.font_name,
                    font_size=task.font_size,
                    margin=task.margin,
                    config=task.config,
                    verbose=False,
                )

                result = processor.process(task.file_path)

                task_result = TaskResult(
                    task=task,
                    success=result.success,
                    output_pdf=result.output_pdf,
                    output_md=result.output_md,
                    error=result.error,
                    page_count=result.page_count,
                    image_count=len(result.images),
                    translation_time=result.translation_time,
                    total_time=result.total_time,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )

                results.append(task_result)
                self.signals.task_finished.emit(task_result)

                if result.success:
                    self.signals.progress.emit(f"Completed: {filename}", "success")
                else:
                    self.signals.progress.emit(f"Failed: {filename}: {result.error}", "error")

            except Exception as e:
                task_result = TaskResult(
                    task=task,
                    success=False,
                    error=str(e),
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                results.append(task_result)
                self.signals.task_finished.emit(task_result)
                self.signals.progress.emit(f"Error: {filename}: {str(e)}", "error")

        self.signals.all_finished.emit(results)


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
        self.doc = fitz.open(file_path)
        self.total_pages = len(self.doc)
        self.current_page = 0
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
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """Settings dialog for translation configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(450)
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

        self.ocr_check = QCheckBox("Use OCR for scanned documents")
        trans_layout.addRow("", self.ocr_check)

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
        self.ocr_check.setChecked(self.config.get("use_ocr", False))
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
        self.config.set("use_ocr", self.ocr_check.isChecked())
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

        self._worker: TranslationWorker | None = None
        self._task_results: list[TaskResult] = []
        self._current_pdf_path: str | None = None
        self._current_md_path: str | None = None
        self._current_md_content: str = ""
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
            self.pdf_viewer.load_pdf(file_path)
            self._current_pdf_path = file_path
            self.translate_btn.setEnabled(True)
            self.status.showMessage(f"Loaded: {Path(file_path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{str(e)}")

    def _translate_current(self):
        """Translate the currently loaded PDF."""
        if not self._current_pdf_path:
            QMessageBox.warning(self, "No PDF", "Please open a PDF first.")
            return

        if not self.config.is_configured():
            QMessageBox.warning(self, "Not Configured", "Please configure your translation provider in Settings.")
            return

        output_dir = str(Path(self._current_pdf_path).parent)
        task = TranslationTask(
            file_path=self._current_pdf_path,
            target_lang=self.config.get("target_lang", "en"),
            source_lang=self.config.get("source_lang", "auto"),
            use_ocr=self.config.get("use_ocr", False),
            temperature=self.config.get("temperature", 0.3),
            page_size=self.config.get("page_size", "A4"),
            font_size=self.config.get("font_size", 11),
            margin=self.config.get("margin", 20.0),
            config=self.config,
        )

        self.status.showMessage("Translating...")
        self.translate_btn.setEnabled(False)

        try:
            processor = DocumentProcessor(
                output_dir=output_dir,
                target_lang=task.target_lang,
                source_lang=task.source_lang,
                use_ocr=task.use_ocr,
                parse_engine=task.parse_engine,
                temperature=task.temperature,
                page_size=task.page_size,
                font_size=task.font_size,
                margin=task.margin,
                config=task.config,
                verbose=False,
            )

            result = processor.process(self._current_pdf_path)

            if result.success:
                self._current_md_path = result.output_md
                self._current_md_content = result.markdown
                self.md_editor.setPlainText(result.markdown)
                self.save_md_btn.setEnabled(True)
                self.save_pdf_btn.setEnabled(True)
                self.status.showMessage(f"Translation completed: {result.output_pdf}")
            else:
                QMessageBox.critical(self, "Translation Error", result.error)
                self.status.showMessage("Translation failed")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Translation failed:\n{str(e)}")
            self.status.showMessage("Translation failed")
        finally:
            self.translate_btn.setEnabled(True)

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
                # Re-render PDF with current markdown
                content = self.md_editor.toPlainText()
                from .renderer import render_pdf
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
    app = QApplication(sys.argv)
    app.setApplicationName("YanFu")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CodeOfMe")
    app.setStyle("Fusion")

    window = YanFuMainWindow()
    window.show()

    sys.exit(app.exec())
