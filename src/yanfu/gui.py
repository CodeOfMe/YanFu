"""YanFu - PySide6 GUI with multi-threaded translation support.

Provides a complete graphical interface for document translation
with independent worker threads, progress tracking, and settings.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
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

        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        provider_layout.addRow("", self.refresh_models_btn)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        provider_layout.addRow("", self.test_btn)

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
            self.model_combo.clear()
            self.model_combo.addItem("Loading models...", "")
            self.model_combo.setEnabled(False)
            self._refresh_models()
        elif provider == "openai":
            self.base_url_edit.setEnabled(False)
            self.base_url_edit.setText("https://api.openai.com")
            self.api_key_edit.setEnabled(True)
            self.model_combo.clear()
            self.model_combo.addItem("Loading models...", "")
            self.model_combo.setEnabled(False)
            self._refresh_models()
        else:
            self.base_url_edit.setEnabled(True)
            self.base_url_edit.clear()
            self.api_key_edit.setEnabled(True)
            self.model_combo.clear()
            self.model_combo.setEditable(True)
            self.model_combo.setEditText("")
            self.model_combo.setEnabled(True)

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
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)

        self._worker: TranslationWorker | None = None
        self._task_results: list[TaskResult] = []
        self._selected_files: list[str] = []
        self.config = ConfigManager()

        self._build_ui()
        self._build_menu()
        self._update_ui_state()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Top splitter: File list + Log
        top_splitter = QSplitter(Qt.Vertical)

        # File selection
        file_group = QGroupBox("Files")
        file_layout = QVBoxLayout(file_group)

        file_btn_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files")
        self.add_files_btn.clicked.connect(self._add_files)
        file_btn_layout.addWidget(self.add_files_btn)

        self.add_dir_btn = QPushButton("Add Directory")
        self.add_dir_btn.clicked.connect(self._add_directory)
        file_btn_layout.addWidget(self.add_dir_btn)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        file_btn_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_files)
        file_btn_layout.addWidget(self.clear_btn)
        file_btn_layout.addStretch()
        file_layout.addLayout(file_btn_layout)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        file_layout.addWidget(self.file_list)

        # Output directory
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output:"))
        self.output_edit = QLineEdit()
        output_layout.addWidget(self.output_edit, 1)
        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(self.browse_output_btn)
        file_layout.addLayout(output_layout)

        top_splitter.addWidget(file_group)

        # Log area
        log_group = QGroupBox("Progress & Log")
        log_layout = QVBoxLayout(log_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        log_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont("Menlo" if sys.platform == "darwin" else "Consolas", 10)
        self.log_text.setFont(font)
        log_layout.addWidget(self.log_text)

        top_splitter.addWidget(log_group)

        main_layout.addWidget(top_splitter)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        bottom_layout.addWidget(self.settings_btn)
        bottom_layout.addStretch()

        self.start_btn = QPushButton("Start Translation")
        self.start_btn.clicked.connect(self._start_translation)
        bottom_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_translation)
        bottom_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(bottom_layout)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        add_files_action = file_menu.addAction("Add Files...")
        add_files_action.setShortcut("Ctrl+O")
        add_files_action.triggered.connect(self._add_files)

        add_dir_action = file_menu.addAction("Add Directory...")
        add_dir_action.triggered.connect(self._add_directory)

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

    def _update_ui_state(self):
        has_files = len(self._selected_files) > 0
        is_running = self._worker is not None and self._worker.isRunning()

        self.start_btn.setEnabled(has_files and not is_running)
        self.cancel_btn.setVisible(is_running)
        self.add_files_btn.setEnabled(not is_running)
        self.add_dir_btn.setEnabled(not is_running)
        self.remove_btn.setEnabled(has_files and not is_running)
        self.clear_btn.setEnabled(has_files and not is_running)
        self.settings_btn.setEnabled(not is_running)

        if is_running:
            self.status.showMessage("Translating...")
        else:
            self.status.showMessage(f"Ready - {len(self._selected_files)} file(s)")

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF/CAJ Files",
            "",
            "Documents (*.pdf *.caj);;PDF Files (*.pdf);;CAJ Files (*.caj);;All Files (*)",
        )
        if files:
            for f in files:
                if f not in self._selected_files:
                    self._selected_files.append(f)
                    self.file_list.addItem(f)
            self._update_ui_state()

    def _add_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            files = find_documents(dir_path, recursive=True)
            added = 0
            for f in files:
                f_str = str(f)
                if f_str not in self._selected_files:
                    self._selected_files.append(f_str)
                    self.file_list.addItem(f_str)
                    added += 1
            self._log(f"Added {added} files from directory")
            self._update_ui_state()

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            if 0 <= row < len(self._selected_files):
                self._selected_files.pop(row)
            self.file_list.takeItem(self.file_list.row(item))
        self._update_ui_state()

    def _clear_files(self):
        self._selected_files.clear()
        self.file_list.clear()
        self._update_ui_state()

    def _browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_edit.setText(dir_path)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            dialog.save_settings()
            self.config = dialog.config
            self._log("Settings saved")

    def _start_translation(self):
        if not self._selected_files:
            QMessageBox.warning(self, "No Files", "Please add files to translate.")
            return

        if not self.config.is_configured():
            QMessageBox.warning(self, "Not Configured", "Please configure your translation provider in Settings.")
            return

        output_dir = self.output_edit.text()
        if not output_dir:
            output_dir = str(Path(self._selected_files[0]).parent)
            self.output_edit.setText(output_dir)

        tasks = []
        for f in self._selected_files:
            task = TranslationTask(
                file_path=f,
                target_lang=self.config.get("target_lang", "en"),
                source_lang=self.config.get("source_lang", "auto"),
                use_ocr=self.config.get("use_ocr", False),
                temperature=self.config.get("temperature", 0.3),
                page_size=self.config.get("page_size", "A4"),
                font_size=self.config.get("font_size", 11),
                margin=self.config.get("margin", 20.0),
                config=self.config,
            )
            tasks.append(task)

        self._task_results.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(tasks))
        self.progress_bar.setValue(0)

        self._worker = TranslationWorker(tasks, output_dir)
        self._worker.signals.task_started.connect(self._on_task_started)
        self._worker.signals.task_finished.connect(self._on_task_finished)
        self._worker.signals.all_finished.connect(self._on_all_finished)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._update_ui_state()
        self._log(f"Starting translation of {len(tasks)} file(s)...")

    def _cancel_translation(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._log("Cancellation requested...")

    def _on_task_started(self, filename: str, current: int, total: int):
        self.progress_bar.setValue(current - 1)
        self._log(f"[{current}/{total}] Processing: {filename}")

    def _on_task_finished(self, result: TaskResult):
        self._task_results.append(result)
        idx = len(self._task_results)
        self.progress_bar.setValue(idx)

    def _on_all_finished(self, results: list[TaskResult]):
        success = sum(1 for r in results if r.success)
        failed = len(results) - success
        self._log(f"Translation complete: {success} succeeded, {failed} failed")
        self.status.showMessage(f"Completed: {success}/{len(results)} succeeded")

    def _on_progress(self, message: str, level: str):
        self._log(message)

    def _on_error(self, error: str):
        self._log(f"Error: {error}")

    def _on_worker_finished(self):
        self._worker = None
        self.progress_bar.setVisible(False)
        self._update_ui_state()

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _run_config_wizard(self):
        from .config_wizard import run_config_wizard
        run_config_wizard()
        self.config = ConfigManager()
        self._log("Configuration wizard completed.")

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
