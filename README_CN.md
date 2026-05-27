# YanFu (言富)

使用 Ollama 或 OpenAI 兼容 API 的 PDF/CAJ 文档翻译工具，支持保留排版的 PDF 生成。

**简单配置**：安装一次，配置翻译提供商即可使用。支持本地 Ollama、OpenAI 云端以及任何 OpenAI 兼容接口。

## 功能特性

- **灵活的翻译提供商**：使用本地 Ollama、OpenAI 云端，或任何 OpenAI 兼容 API（vLLM、LM Studio 等）
- **动态模型发现**：自动从配置的提供商获取可用模型——无硬编码模型列表
- **多格式支持**：解析 PDF 和 CAJ（中国学术期刊）文件
- **排版保留**：使用 marker-pdf 生成保留排版、图片和公式的 PDF 输出
- **OCR 支持**：处理扫描文档
- **批量处理**：处理多个文件或整个目录
- **图形界面与命令行**：精美的 PySide6 图形界面和命令行界面
- **Python API**：干净的 API 接口，支持 ToolResult 模式
- **配置向导**：首次用户的交互式设置引导

## 系统要求

- Python 3.10+
- macOS / Linux / Windows
- Ollama（本地翻译）或 OpenAI API 密钥（云端翻译）
- CPU 友好：所有文档解析均可在 CPU 上高效运行

## 安装

YanFu 默认使用 **ModelScope / 国内 HF 镜像** 下载模型，无需科学上网。

```bash
# 安装所有依赖（推荐）
pip install yanfu

# 开发工具
pip install yanfu[dev]
```

就这么简单！所有核心依赖（包括 PySide6 GUI、marker-pdf OCR 和文档解析器）都已包含。

## 快速开始

### 第一步：配置翻译提供商

运行交互式配置向导：

```bash
yanfu --config
```

或通过 GUI 设置对话框配置。支持的提供商：

| 提供商 | 配置方式 | 费用 |
|--------|----------|------|
| **Ollama**（本地） | `ollama pull qwen3:0.6b` | 免费 |
| **OpenAI**（云端） | 需要 API 密钥 | 按量付费 |
| **自定义** | 任何 OpenAI 兼容接口 | 视情况而定 |

### 第二步：翻译

#### 图形界面

```bash
yanfu --gui
```

GUI 功能：
- **左右分栏**：左侧原文 PDF，右侧译文
- **同步滚动**：开启同步可同时浏览两侧内容
- **独立线程**：PDF 解析和翻译在后台线程运行——界面始终保持响应
- **导出选项**：另存为 Markdown 或翻译后的 PDF

#### 命令行

```bash
# 翻译 PDF 为中文
yanfu paper.pdf -l zh

# 翻译为日文
yanfu paper.pdf -l ja

# 翻译多个文件
yanfu paper1.pdf paper2.pdf -l fr

# 批量处理目录
yanfu ./papers --batch -l es

# 详细日志输出
yanfu paper.pdf -v

# JSON 格式输出
yanfu paper.pdf --json

# 列出当前提供商的可用模型
yanfu --list-models

# 测试与提供商的连接
yanfu --test-connection
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--gui` | 启动图形界面 |
| `--config` | 运行配置向导 |
| `--test-connection` | 测试提供商连接 |
| `--list-models` | 列出提供商可用模型 |
| `--reset-config` | 重置配置为默认值 |
| `-V`, `--version` | 显示版本 |
| `-v`, `--verbose` | 启用详细输出 |
| `-o`, `--output` | 输出目录 |
| `--json` | JSON 格式输出 |
| `-q`, `--quiet` | 抑制非必要输出 |
| `-l`, `--lang` | 目标语言（默认：en） |
| `--source-lang` | 源语言（默认：auto） |
| `--use-ocr` | 启用扫描文档 OCR |
| `--engine` | PDF 解析引擎（auto/marker/pymupdf/docling/pdfplumber/mineru/easyocr 等） |
| `--temperature` | 翻译温度（0.0-1.0） |
| `--batch` | 批量处理目录 |
| `--list-langs` | 列出支持的语言 |

### 国内镜像 / ModelScope

YanFu 默认使用 **国内 HF 镜像** (`https://hf-mirror.com`) 下载引擎模型，无需科学上网。只需要正常安装即可：

```bash
pip install yanfu
```

首次运行时，marker-pdf 等引擎的模型会自动从国内镜像下载到 `~/.cache/datalab/models/`。

### PDF 解析引擎

YanFu 支持 **14 种解析引擎**，可通过 `--engine` 参数或 GUI 设置选择：

| 引擎 | 模型大小 | OCR | 特长 |
|------|---------|-----|------|
| **marker** | ~3GB | ✓ | 最佳综合质量，布局+OCR+图片 |
| **docling** | ~1.5GB | ✓ | IBM，质量速度均衡 |
| **mineru** | ~1.5GB | ✓ | 中文文档最佳 |
| **easyocr** | ~300MB | ✓ | 80+ 语言，轻量 |
| **doctr** | ~500MB | ✓ | 轻量 OCR |
| **nougat** | ~1.5GB | ✓ | 学术论文 |
| **surya-lite** | ~2GB | ✓ | Surya 纯 OCR |
| **pymupdf** | 无 | ✗ | 最快，数字 PDF |
| **pdfplumber** | 无 | ✗ | 表格提取，轻量 |
| **llamaparse** | 云端 | ✓ | API Key 需配置 |
| **mathpix** | 云端 | ✓ | 数学/STEM 公式 |
| **mineru-cloud** | 云端 | ✓ | 中文云端 API |
| **doc2x** | 云端 | ✓ | LaTeX 公式输出 |
| **auto** | - | - | 自动选择最佳引擎 |

在 GUI 中点击 **Settings** → 选择引擎 → 点击下载按钮即可预下载模型。

## 支持的语言

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

# 翻译单个文件
result = yanfu_translate_file(
    input_path="paper.pdf",
    target_lang="zh",
)

print(result.success)    # True / False
print(result.data)       # 输出路径和元数据
print(result.metadata)   # 版本和时间信息
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

### 配置管理

```python
from yanfu.translator import ConfigManager

config = ConfigManager()

# 检查是否已配置
if not config.is_configured():
    print("运行 'yanfu --config' 进行设置")

# 修改设置
config.set("provider", "ollama")
config.set("model", "qwen3:0.6b")
config.set("base_url", "http://localhost:11434")
config.save_config()

# 重置为默认值
config.reset()
```

## 架构设计

YanFu 采用清晰的多线程架构：

```
┌─────────────────────────────────────────────────────┐
│                    GUI（主线程）                       │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  PDF 查看器    │    │      译文编辑器            │   │
│  │  (PyMuPDF)    │    │    (QTextEdit)            │   │
│  └──────────────┘    └──────────────────────────┘   │
└─────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│  ParseWorker     │          │  TranslateWorker      │
│  （后台线程）      │          │  （后台线程）          │
│  - PDF 解析      │          │  - API 调用           │
│  - 图片提取      │          │  - 分块翻译           │
│  - Markdown 生成 │          │  - PDF 渲染           │
└─────────────────┘          └──────────────────────┘
```

- **ParseWorker**：使用 marker-pdf 或 PyMuPDF 从 PDF 提取文本、图片和公式
- **TranslateWorker**：将文本块发送至 Ollama/OpenAI API，组装结果，渲染 PDF
- **UI 线程**：始终保持响应——解析和翻译期间不会卡顿

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
- [TransPaste](https://github.com/CodeOfMe/TransPaste) - 本地大模型剪贴板翻译工具
