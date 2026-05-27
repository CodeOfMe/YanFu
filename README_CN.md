# YanFu (言附)

**使用 Ollama 或 OpenAI 兼容 API 的 PDF/CAJ 文档翻译工具，保留排版生成 PDF。**

---

## 功能

- **14 种 PDF 解析引擎**：docling（默认）、marker、mineru、easyocr、doctr、nougat、pymupdf、pdfplumber、llamaparse、mathpix、mineru-cloud、doc2x，以及自动选择模式
- **灵活的翻译后端**：本地 Ollama、OpenAI 云端，或任何 OpenAI 兼容接口
- **动态模型发现**：自动从配置的提供商获取可用模型
- **三栏 GUI**：原文 PDF | 解析后 Markdown | 翻译结果，均可拖拽调整大小
- **渲染/纯文本切换**：Markdown 可切换为渲染视图（表格、标题、代码格式化）或纯文本
- **同步滚动**：PDF 与翻译同步滚动（可开关）
- **后台线程**：解析和翻译不阻塞界面
- **CLI + Python API**：`yanfu paper.pdf -l zh` 或 `from yanfu import yanfu_translate_file`
- **配置向导**：`yanfu --config` 引导完成首次设置

---

## 安装

```bash
pip install yanfu
```

14 种引擎和 GUI 依赖全部包含，无需额外安装。

```bash
yanfu --version   # 验证安装
```

---

## 快速开始

### 1. 配置翻译提供商

```bash
yanfu --config
```

按提示选择提供商 → 模型 → 引擎。默认：**Ollama + gemma3:1b + docling**。

或手动拉取模型：

```bash
ollama pull gemma3:1b        # 默认模型
ollama pull qwen2.5:1.5b     # 中文翻译更好
ollama pull qwen2.5:7b       # 最佳质量
```

### 2. 启动 GUI

```bash
yanfu --gui
```

### 3. 翻译

| 步骤 | 按钮 | 作用 |
|------|------|------|
| 打开 PDF | 📂 Open PDF | 加载 PDF 到左栏 |
| 解析 | 📄 Parse PDF | 提取文字（中间栏显示 Markdown） |
| 翻译 | ▶ Translate | 翻译已解析文本（右栏显示结果） |
| 保存 | 💾 Save MD / 💾 Save PDF | 导出翻译 |

**一键操作**：打开 PDF → 点 ▶ Translate（自动先解析再翻译）。

### 4. 命令行

```bash
# 翻译为中文
yanfu paper.pdf -l zh

# 翻译为日文
yanfu paper.pdf -l ja

# 指定引擎
yanfu paper.pdf --engine marker -l zh

# 批量处理目录
yanfu ./papers --batch -l es -v

# JSON 输出
yanfu paper.pdf --json
```

---

## GUI 布局

```
┌────────────────┬─────────────────────┬─────────────────────┐
│  📄 原文        │  📝 解析后 Markdown  │  🌐 翻译结果         │
│  ┌──────────┐  │  🔄Plain ✕Clear    │  🔗同步 🔄Plain ✕   │
│  │          │  │  📄解析  ▶翻译      │  ▶翻译 💾保存       │
│  │   PDF    │  │  ┌──────────────┐   │  ┌──────────────┐   │
│  │  查看器   │  │  │ 渲染或纯文本  │   │  │ 渲染或纯文本  │   │
│  │          │  │  │              │   │  │              │   │
│  └──────────┘  │  └──────────────┘   │  └──────────────┘   │
│  ◀ 1/11页 ▶   │  ### 方法          │  ### 方法           │
│                │  |列1|列2|          │  |列1|列2|          │
│                │  [Formula]          │  [公式]             │
└────────────────┴─────────────────────┴─────────────────────┘
│  状态: 正在翻译...     进度: [████████░░] 80%              │
└──────────────────────────────────────────────────────────┘
```

### 三栏说明

| 栏位 | 内容 | 操作 |
|------|------|------|
| 左 | PDF 查看器，支持翻页 | Open PDF，上一页/下一页 |
| 中 | 解析后 Markdown | 解析、清除、渲染切换 |
| 右 | 翻译结果 | 翻译、清除、保存、渲染切换 |

### 工具栏

- 📂 打开 PDF
- ▶ 翻译
- 💾 保存（Markdown 或 PDF）
- 🔗 同步滚动（开关）

### 设置（Ctrl+,）

| 分类 | 选项 |
|------|------|
| 翻译提供商 | 提供商（Ollama/OpenAI/自定义）、Base URL、API Key、模型 |
| 模型列表 | 刷新模型、测试连接 |
| PDF 解析引擎 | 14 种引擎，可用状态（绿色 ✓ / 红色 ✗） |
| 设备 | Auto / CPU / CUDA / Apple MPS / DirectML(Vulkan) |
| 下载/重下载 | 下载所选引擎模型（Force 清空缓存重下） |
| 翻译设置 | 源语言/目标语言、Temperature |
| 输出设置 | 页面大小、字号、边距 |

---

## PDF 解析引擎（14 种）

| 引擎 | 类型 | 模型 | OCR | 适用场景 |
|------|------|------|:---:|----------|
| **docling**（默认）| 本地 | ~1.5GB | ✓ | 质量速度均衡，表格处理好 |
| **marker** | 本地 | ~3GB | ✓ | 最佳综合：排版+OCR+图片+公式 |
| **mineru** | 本地 | ~1.5GB | ✓ | 中文文档 |
| **easyocr** | 本地 | ~300MB | ✓ | 80+ 语言，轻量 |
| **doctr** | 本地 | ~500MB | ✓ | 旋转文字处理，轻量 |
| **nougat** | 本地 | ~1.5GB | ✓ | 学术论文 |
| **pymupdf** | 本地 | 无 | ✗ | 最快，数字 PDF |
| **pdfplumber** | 本地 | 无 | ✗ | 表格提取 |
| **llamaparse** | 云端 | 云端 | ✓ | 优秀质量（需 LlamaCloud Key） |
| **mathpix** | 云端 | 云端 | ✓ | 数学/STEM 公式 |
| **mineru-cloud** | 云端 | 云端 | ✓ | 中文文档（需 API Key） |
| **doc2x** | 云端 | 云端 | ✓ | 最佳公式 LaTeX 输出 |
| **auto** | 自动 | — | — | 自动选择最佳可用引擎 |

**公式提示**：论文有大量数学公式，请用 **Marker** 或 **Doc2X**。

---

## 命令行参考

```
yanfu [OPTIONS] [input ...]

参数:
  --gui              启动图形界面
  --config           运行配置向导
  --test-connection  测试提供商连接
  --list-models      列出提供商模型
  --reset-config     重置配置
  -V, --version      显示版本
  -v, --verbose      详细输出
  -o, --output DIR   输出目录
  --json             JSON 输出
  -l, --lang CODE    目标语言（默认: en）
  --source-lang CODE 源语言（默认: auto）
  --engine ENGINE    解析引擎
  --temperature F    翻译温度 (0.0-1.0)
  --batch            批量处理
  --list-langs       列出支持语言
```

### 支持的语言

| 代码 | 语言 | 代码 | 语言 |
|------|------|------|------|
| en | 英语 | zh | 简体中文 |
| zh-Hant | 繁体中文 | ja | 日语 |
| ko | 韩语 | fr | 法语 |
| de | 德语 | es | 西班牙语 |
| ru | 俄语 | ar | 阿拉伯语 |
| hi | 印地语 | th | 泰语 |
| vi | 越南语 | it | 意大利语 |
| pt | 葡萄牙语 | | |

---

## Python API

```python
from yanfu import yanfu_translate_file
from yanfu.translator import ConfigManager

# 配置
config = ConfigManager()
config.set("provider", "ollama")
config.set("model", "gemma3:1b")
config.save_config()

# 翻译
result = yanfu_translate_file("paper.pdf", target_lang="zh", config=config)
print(result.data["output_pdf"])  # 翻译后 PDF 路径
```

### 批量

```python
from yanfu import yanfu_translate_files

result = yanfu_translate_files(
    ["paper1.pdf", "paper2.pdf"],
    target_lang="ja",
    config=config,
)
for r in result.data["results"]:
    print(r["file"], "成功" if r["success"] else "失败")
```

---

## 模型下载

### 自动下载

引擎首次使用时自动下载模型（终端显示 tqdm 进度条）。可在设置中预下载：

1. 设置 → 选择引擎 → 点击 **⬇ Download Selected Engine Models**
2. 终端显示下载进度和缓存路径
3. 点击 **🔄 Re-download (Force)** 清空缓存重下

### 缓存路径

| 引擎 | 缓存位置 |
|------|----------|
| marker | `~/.cache/datalab/models/` 或 `%LOCALAPPDATA%\datalab\models\` |
| docling / doctr | `~/.cache/huggingface/hub/` |
| easyocr | `<easyocr 安装目录>/model/` |
| pymupdf / pdfplumber | 无需缓存 |

---

## 常见问题

| 问题 | 解决方法 |
|------|----------|
| `ModuleNotFoundError: PySide6` | `pip install yanfu`（包含全部依赖） |
| 翻译输出为空 | `ollama list` 检查模型 → 换大模型 |
| "No extractable text" | PDF 是图片版 → 用 EasyOCR 或 Marker |
| Docling 公式缺失 | 换 Marker 引擎（支持公式），或 Doc2X 云端 |
| QThread 崩溃 | 更新到最新版（`git pull`） |
| 下载卡住 | 设置 → Re-download (Force) 清缓存 |
| 不知道模型路径 | 终端会打印缓存路径 |

---

## 开发

```bash
git clone https://github.com/CodeOfMe/YanFu.git
cd YanFu
pip install -e ".[dev]"
pytest tests/ -v
ruff check .
```

---

## 许可证

GPL-3.0-or-later
