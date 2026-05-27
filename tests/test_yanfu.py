"""YanFu - Comprehensive test suite."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestToolResult:
    """Test ToolResult dataclass."""

    def test_success_result(self):
        from yanfu.api import ToolResult

        r = ToolResult(success=True, data={"key": "value"})
        assert r.success is True
        assert r.error is None

    def test_failure_result(self):
        from yanfu.api import ToolResult

        r = ToolResult(success=False, error="failed")
        assert r.success is False
        assert r.error == "failed"

    def test_to_dict(self):
        from yanfu.api import ToolResult

        r = ToolResult(success=True, data=[1, 2])
        d = r.to_dict()
        assert set(d.keys()) == {"success", "data", "error", "metadata"}

    def test_default_metadata_isolation(self):
        from yanfu.api import ToolResult

        r1 = ToolResult(success=True)
        r2 = ToolResult(success=True)
        r1.metadata["a"] = 1
        assert "a" not in r2.metadata


class TestYanfuAPI:
    """Test API functions."""

    def test_translate_file_not_found(self):
        from yanfu.api import yanfu_translate_file

        result = yanfu_translate_file("/nonexistent/file.pdf")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_translate_unsupported_format(self, tmp_path):
        from yanfu.api import yanfu_translate_file

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        result = yanfu_translate_file(str(txt_file))
        assert result.success is False
        assert "unsupported" in result.error.lower()

    def test_translate_files_empty_list(self):
        from yanfu.api import yanfu_translate_files

        result = yanfu_translate_files([])
        assert result.success is False
        assert "no input" in result.error.lower()


class TestToolsSchema:
    """Test TOOLS schema."""

    def test_tool_structure(self):
        from yanfu.tools import TOOLS

        for tool in TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_required_fields_in_properties(self):
        from yanfu.tools import TOOLS

        for tool in TOOLS:
            func = tool["function"]
            props = func["parameters"]["properties"]
            for req in func["parameters"]["required"]:
                assert req in props

    def test_translate_file_tool(self):
        from yanfu.tools import TOOLS

        translate_tool = next(t for t in TOOLS if t["function"]["name"] == "yanfu_translate_file")
        assert translate_tool is not None
        assert "input_path" in translate_tool["function"]["parameters"]["required"]

    def test_translate_files_tool(self):
        from yanfu.tools import TOOLS

        translate_tool = next(t for t in TOOLS if t["function"]["name"] == "yanfu_translate_files")
        assert translate_tool is not None
        assert "input_paths" in translate_tool["function"]["parameters"]["required"]


class TestToolsDispatch:
    """Test dispatch function."""

    def test_dispatch_translate_file(self):
        from yanfu.tools import dispatch

        result = dispatch("yanfu_translate_file", {"input_path": "/nonexistent.pdf"})
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_dispatch_unknown_tool(self):
        from yanfu.tools import dispatch

        with pytest.raises(ValueError, match="Unknown tool"):
            dispatch("unknown_tool", {})

    def test_dispatch_with_string_arguments(self):
        from yanfu.tools import dispatch

        result = dispatch("yanfu_translate_file", '{"input_path": "/nonexistent.pdf"}')
        assert result["success"] is False


class TestCLIFlags:
    """Test CLI integration."""

    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "yanfu"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_version_flag(self):
        r = self._run_cli("-V")
        assert r.returncode == 0
        assert "YanFu" in r.stdout

    def test_help_has_unified_flags(self):
        r = self._run_cli("--help")
        assert "--json" in r.stdout
        assert "--quiet" in r.stdout or "-q" in r.stdout
        assert "--verbose" in r.stdout or "-v" in r.stdout
        assert "--output" in r.stdout or "-o" in r.stdout

    def test_list_langs(self):
        r = self._run_cli("--list-langs")
        assert r.returncode == 0
        assert "en" in r.stdout
        assert "zh" in r.stdout

    def test_list_models(self):
        r = self._run_cli("--list-models")
        assert r.returncode == 0
        assert "gemma3:1b" in r.stdout
        assert "qwen3:0.6b" in r.stdout

    def test_no_input_error(self):
        r = self._run_cli()
        assert r.returncode == 1
        assert "required" in r.stderr.lower() or "required" in r.stdout.lower()

    def test_json_output(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        r = self._run_cli(str(txt_file), "--json")
        assert r.returncode == 1
        output = json.loads(r.stdout)
        assert output["success"] is False


class TestPackageExports:
    """Test package exports."""

    def test_version_import(self):
        from yanfu import __version__
        assert __version__ == "0.1.0"

    def test_tool_result_import(self):
        from yanfu import ToolResult
        assert ToolResult is not None

    def test_translate_file_import(self):
        from yanfu import yanfu_translate_file
        assert yanfu_translate_file is not None

    def test_translate_files_import(self):
        from yanfu import yanfu_translate_files
        assert yanfu_translate_files is not None

    def test_all_exports(self):
        import yanfu
        assert "__version__" in yanfu.__all__
        assert "ToolResult" in yanfu.__all__
        assert "yanfu_translate_file" in yanfu.__all__
        assert "yanfu_translate_files" in yanfu.__all__


class TestUtils:
    """Test utility functions."""

    def test_clean_markdown(self):
        from yanfu.utils import clean_markdown

        text = "Hello\n\n\n\nWorld\n\n\n"
        cleaned = clean_markdown(text)
        assert "\n\n\n" not in cleaned
        assert cleaned == "Hello\n\nWorld"

    def test_language_map(self):
        from yanfu.utils import LANGUAGE_MAP

        assert "en" in LANGUAGE_MAP
        assert "zh" in LANGUAGE_MAP
        assert "auto" in LANGUAGE_MAP

    def test_supported_extensions(self):
        from yanfu.utils import SUPPORTED_EXTENSIONS

        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".caj" in SUPPORTED_EXTENSIONS

    def test_is_pdf_file(self):
        from yanfu.utils import is_pdf_file

        assert is_pdf_file("test.pdf") is True
        assert is_pdf_file("test.PDF") is True
        assert is_pdf_file("test.txt") is False

    def test_is_caj_file(self):
        from yanfu.utils import is_caj_file

        assert is_caj_file("test.caj") is True
        assert is_caj_file("test.CAJ") is True
        assert is_caj_file("test.pdf") is False

    def test_get_output_path(self):
        from yanfu.utils import get_output_path

        path = get_output_path("/path/to/file.pdf")
        assert str(path).endswith(".md")

    def test_get_output_path_with_dir(self, tmp_path):
        from yanfu.utils import get_output_path

        path = get_output_path("/path/to/file.pdf", output_dir=str(tmp_path))
        assert path.parent == tmp_path


class TestTranslator:
    """Test translator and model manager."""

    def test_model_definitions(self):
        from yanfu.translator import MODEL_DEFINITIONS

        assert "gemma3:1b" in MODEL_DEFINITIONS
        assert "qwen3:0.6b" in MODEL_DEFINITIONS
        assert "qwen3:1.8b" in MODEL_DEFINITIONS

        for model_id, info in MODEL_DEFINITIONS.items():
            assert "name" in info
            assert "gguf_repo" in info
            assert "gguf_file" in info
            assert "size_mb" in info

    def test_model_manager_init(self, tmp_path):
        from yanfu.translator import ModelManager

        mm = ModelManager(cache_dir=str(tmp_path))
        assert mm.cache_dir == tmp_path

    def test_model_manager_no_models(self, tmp_path):
        from yanfu.translator import ModelManager

        mm = ModelManager(cache_dir=str(tmp_path))
        assert mm.list_downloaded_models() == []

    def test_model_manager_unknown_model(self, tmp_path):
        from yanfu.translator import ModelManager

        mm = ModelManager(cache_dir=str(tmp_path))
        assert mm.get_model_path("unknown_model") is None
        assert mm.is_model_downloaded("unknown_model") is False

    def test_gguf_translator_init(self, tmp_path):
        from yanfu.translator import GGUFTranslator

        translator = GGUFTranslator(cache_dir=str(tmp_path))
        assert translator.model_name == "gemma3:1b"
        assert translator._model is None

    def test_split_markdown(self):
        from yanfu.translator import _split_markdown

        text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        chunks = _split_markdown(text, max_chunk_size=100)
        assert len(chunks) >= 1

    def test_translate_empty_text(self):
        from yanfu.translator import _split_markdown

        chunks = _split_markdown("")
        assert len(chunks) == 0 or chunks == [""]


class TestParser:
    """Test document parser."""

    def test_pdf_parser_init(self):
        from yanfu.parser import PDFParser

        parser = PDFParser()
        assert parser.engine == "auto"
        assert parser.use_ocr is False

    def test_caj_parser_init(self):
        from yanfu.parser import CAJParser

        parser = CAJParser()
        assert parser.pdf_parser is not None

    def test_parse_unsupported_format(self):
        from yanfu.parser import parse_document

        with pytest.raises(ValueError, match="Unsupported"):
            parse_document("test.txt")


class TestRenderer:
    """Test PDF renderer."""

    def test_pdf_renderer_init(self, tmp_path):
        from yanfu.renderer import PDFRenderer

        output_path = tmp_path / "output.pdf"
        renderer = PDFRenderer(str(output_path))
        assert renderer.output_path == output_path

    def test_render_pdf_function(self, tmp_path):
        from yanfu.renderer import render_pdf

        output_path = tmp_path / "output.pdf"
        assert callable(render_pdf)


class TestCore:
    """Test core processing."""

    def test_processing_result(self):
        from yanfu.core import ProcessingResult

        result = ProcessingResult(success=True)
        assert result.success is True
        assert result.error == ""

    def test_document_processor_init(self):
        from yanfu.core import DocumentProcessor

        processor = DocumentProcessor()
        assert processor.target_lang == "en"
        assert processor.model_name == "gemma3:1b"

    def test_process_nonexistent_file(self):
        from yanfu.core import DocumentProcessor

        processor = DocumentProcessor()
        result = processor.process("/nonexistent/file.pdf")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_process_unsupported_format(self, tmp_path):
        from yanfu.core import DocumentProcessor

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        processor = DocumentProcessor()
        result = processor.process(str(txt_file))
        assert result.success is False
        assert "unsupported" in result.error.lower()
