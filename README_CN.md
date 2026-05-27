# 言福 (YanFu)

使用本地大模型进行 PDF/CAJ 文档翻译并生成保留排版的 PDF 文件。

**零配置**：安装后即可运行，模型首次运行时自动下载。

## 功能特性

- **零配置**：`pip install yanfu` 后即可运行。无需 Ollama、无需 API 密钥、无需外部服务。
- **自动下载模型**：GGUF 模型在首次运行时自动从 ModelScope/HuggingFace 下载。
- **多格式支持**：解析 PDF 和 CAJ（中国学术期刊）文件。
- **本地大模型翻译**：使用 GGUF 模型（gemma3:1b、qwen3:0.6b）通过 llama-cpp-python 翻译。
- **排版保留**：生成保留排版、图片和公式的 PDF 输出。
- **OCR 支持**：处理扫描文档。
- **批量处理**：处理多个文件或整个目录。
- **CLI 和 API**：命令行界面和带有 ToolResult 模式的 Python API。
- **智能体集成**：用于 LLM 智能体的 OpenAI 函数调用工具。

## 系统要求

- Python 3.10+
- macOS / Linux / Windows
- 仅需 CPU（GGUF 模型在 CPU 上运行，无需 GPU）
- 约 1GB 磁盘空间用于模型

## 安装

```bash
# 基础安装（包含所有依赖）
pip install yanfu

# 带 OCR 支持
pip install yanfu[ocr]

# 完整安装
pip install yanfu[all]
```

就这样！无需额外配置。模型将在首次运行时自动下载。

## 快速开始

```bash
# 将 PDF 翻译为英文（首次运行时模型自动下载）
yanfu paper.pdf

# 翻译为中文
yanfu paper.pdf -l zh

# 使用更快的模型翻译为日文
yanfu paper.pdf -l ja --model qwen3:0.6b

# 翻译多个文件
yanfu paper1.pdf paper2.pdf -l fr

# 批量处理目录
yanfu ./papers --batch -l es

# 详细输出
yanfu paper.pdf -v

# JSON 格式输出
yanfu paper.pdf --json
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-V`, `--version` | 显示版本 |
| `-v`, `--verbose` | 启用详细输出 |
| `-o`, `--output` | 输出目录 |
| `--json` | JSON 输出格式 |
| `-q`, `--quiet` | 抑制非必要输出 |
| `-l`, `--lang` | 目标语言（默认：en） |
| `--source-lang` | 源语言（默认：auto） |
| `--model` | 翻译模型（默认：gemma3:1b） |
| `--model-path` | GGUF 文件直接路径 |
| `--cache-dir` | 模型缓存目录 |
| `--use-ocr` | 为扫描文档启用 OCR |
| `--engine` | PDF 解析器（auto/pymupdf/marker/pdfplumber） |
| `--temperature` | 翻译温度（0.0-1.0） |
| `--batch` | 批量处理目录 |
| `--list-langs` | 列出支持的语言 |
| `--list-models` | 列出可用模型 |
| `--download-model` | 下载模型而不翻译 |
| `--list-downloaded` | 列出已下载的模型 |
| `--cleanup-models` | 删除所有已下载的模型 |

### 翻译模型

| 模型 | 大小 | 质量 | 速度 |
|------|------|------|------|
| gemma3:1b | ~780MB | 良好 | 中等 |
| qwen3:0.6b | ~420MB | 基础 | 快速 |
| qwen3:1.8b | ~1.1GB | 最佳 | 较慢 |

模型下载后存储在 `~/.cache/yanfu/models/` 目录。

### 支持的语言

| 代码 | 语言 | 代码 | 语言 |
|------|------|------|------|
| en | 英语 | zh | 简体中文 |
| zh-Hant | 繁体中文 | ja | 日语 |
| ko | 韩语 | fr | 法语 |
| de | 德语 | es | 西班牙语 |
| ru | 俄语 | it | 意大利语 |
| pt | 葡萄牙语 | ar | 阿拉伯语 |
| hi | 印地语 | th | 泰语 |
| vi | 越南语 | | |

## Python API

```python
from yanfu import yanfu_translate_file, ToolResult

# 翻译单个文件（首次运行时模型自动下载）
result = yanfu_translate_file(
    input_path="paper.pdf",
    target_lang="zh",
    model_name="gemma3:1b",
)

print(result.success)    # True / False
print(result.data)       # 输出路径和元数据
print(result.metadata)   # 版本和计时信息
```

### 批量处理

```python
from yanfu import yanfu_translate_files

result = yanfu_translate_files(
    input_paths=["paper1.pdf", "paper2.caj"],
    target_lang="ja",
    use_ocr=True,
)

for r in result.data["results"]:
    print(f"{r['file']}: {'成功' if r['success'] else '失败'}")
```

### 模型管理

```python
from yanfu.translator import ModelManager

mm = ModelManager()

# 列出已下载的模型
print(mm.list_downloaded_models())

# 下载特定模型
mm.download_model("qwen3:0.6b")

# 检查模型是否存在
print(mm.is_model_downloaded("gemma3:1b"))

# 清理以释放磁盘空间
mm.cleanup()  # 删除所有模型
mm.cleanup("qwen3:0.6b")  # 删除特定模型
```

## 智能体集成

YanFu 提供 OpenAI 函数调用工具用于 LLM 智能体集成：

```python
from yanfu.tools import TOOLS, dispatch

# TOOLS 包含 OpenAI API 的函数模式
# dispatch() 将工具调用路由到相应的函数

# 与 OpenAI API 配合使用
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "将此 PDF 翻译为中文"}],
    tools=TOOLS,
)

# 分派工具调用
tool_call = response.choices[0].message.tool_calls[0]
result = dispatch(tool_call.function.name, tool_call.function.arguments)
```

## 命令行帮助

```
$ yanfu --help
usage: yanfu [-h] [-V] [-v] [-o OUTPUT] [--json] [-q] [-l LANG]
             [--source-lang SOURCE_LANG] [--model MODEL] [--model-path MODEL_PATH]
             [--cache-dir CACHE_DIR] [--use-ocr] [--engine ENGINE]
             [--temperature TEMPERATURE] [--page-size PAGE_SIZE]
             [--font FONT] [--font-size FONT_SIZE] [--margin MARGIN] [--batch]
             [--list-langs] [--list-models] [--download-model MODEL]
             [--list-downloaded] [--cleanup-models]
             [input ...]

言福 - 使用本地大模型翻译 PDF/CAJ 文档（零配置）
```

## 开发

```bash
# 克隆并安装开发版本
git clone https://github.com/CodeOfMe/YanFu.git
cd YanFu
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查和格式化
ruff check .
ruff format .
```

## 许可证

GPL-3.0-or-later

## 参见

- [NuoYi](https://github.com/cycleuser/NuoYi) - PDF/DOCX 转 Markdown 转换器
- [TransPaste](https://github.com/CodeOfMe/TransPaste) - 本地大模型剪贴板翻译器
