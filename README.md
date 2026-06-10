# 合同条款快速检索与比对工具

一个功能强大的命令行工具，用于快速检索和比对PDF和Word格式合同文件中的条款内容。

## 功能特性

### 1. 文件扫描与内容提取
- 支持递归扫描指定目录中的PDF和Word格式合同文件
- 准确提取文件中的全文内容，包括文本和表格
- 保留原始文档的页码信息，确保检索结果可精确定位

### 2. 索引构建
- 建立支持中英文双语的全文检索索引（基于Whoosh）
- 实现高效的文本分词处理（基于Jieba），针对合同专业术语进行优化
- 索引包含文件路径、条款内容、页码及相关元数据

### 3. 关键字检索功能
- 支持多关键词组合搜索（AND/OR逻辑）
- 返回结果包含：匹配的合同文件名、相关条款摘要、精确页码
- 搜索结果按相关度排序（BM25F算法）

### 4. 条款比对功能（核心功能）
- 接收用户输入的标准条款文本作为比对基准
- 在所有已索引合同中查找语义相似的条款内容
- 计算并返回相似度评分（0-100分）
- 定位并返回相似条款的原文内容及在文档中的具体位置（页码+段落）

### 5. 统计信息输出
- 扫描文件总数及各类型文件数量统计
- 成功提取内容的文件比例
- 提取的条款总数及平均条款长度
- 检索/比对操作的响应时间统计

### 6. 输出格式支持
- 终端彩色表格：使用不同颜色区分不同类型信息，优化可读性
- JSON格式：完整输出所有结构化数据，便于后续自动化处理

## 性能指标

- **索引构建时间**：对于100个标准合同文件，应在5分钟内完成
- **检索响应时间**：单次关键词搜索应在2秒内返回结果
- **条款比对时间**：标准条款比对应在10秒内完成（针对100个合同文件）

## 安装

### 方式一：使用pip安装

```bash
pip install -e .
```

### 方式二：使用requirements.txt

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 查看帮助信息

```bash
contract-retriever --help
contract-retriever build-index --help
contract-retriever search --help
contract-retriever compare --help
```

### 2. 构建索引

```bash
contract-retriever build-index /path/to/contracts
```

### 3. 关键字检索

```bash
# AND模式（所有关键词必须出现）
contract-retriever search 违约责任 违约金

# OR模式（任一关键词出现即可）
contract-retriever search -m OR 违约责任 争议解决

# 限制返回结果数量
contract-retriever search -l 20 保密条款
```

### 4. 条款比对

```bash
# 直接输入标准条款
contract-retriever compare -c "任何一方违反本合同约定，应承担违约责任"

# 从文件读取标准条款
contract-retriever compare --clause-file standard_clause.txt

# 设置相似度阈值
contract-retriever compare -c "条款内容" -t 0.5

# 显示完整内容
contract-retriever compare -c "条款内容" --show-content
```

### 5. 查看统计信息

```bash
# 查看所有统计
contract-retriever stats

# 查看文件统计
contract-retriever stats -t file

# 查看比对统计
contract-retriever stats -t compare
```

### 6. 列出已索引文档

```bash
contract-retriever list-docs
```

### 7. 清除索引

```bash
contract-retriever clear-index -f
```

## 输出格式选项

### JSON输出

```bash
# 所有命令都支持--json-output选项
contract-retriever --json-output search 违约责任

# 保存到文件
contract-retriever search 违约责任 --output-json results.json
```

### 禁用彩色输出

```bash
contract-retriever --no-color search 违约责任
```

## 项目结构

```
contract-retriever/
├── src/
│   └── contract_retriever/
│       ├── __init__.py
│       ├── cli.py           # 命令行入口
│       ├── extractor.py     # 文件扫描与内容提取
│       ├── indexer.py       # 索引构建与检索
│       ├── comparator.py    # 条款比对功能
│       ├── formatter.py     # 输出格式化
│       └── stats.py         # 统计信息管理
├── tests/                   # 测试用例
├── sample_data/             # 示例数据
├── pyproject.toml
├── requirements.txt
└── setup.py
```

## 核心模块说明

### extractor.py
- `PDFExtractor`: 基于pdfplumber的PDF内容提取
- `WordExtractor`: 基于python-docx的Word文档内容提取
- `DocumentScanner`: 目录扫描器，支持递归扫描
- `extract_contract_clauses`: 合同条款智能识别

### indexer.py
- `ChineseAnalyzer`: 自定义中文分词分析器
- `ContractIndex`: 全文索引管理器，支持构建、检索、更新

### comparator.py
- `ClauseComparator`: 条款比对器，使用TF-IDF + 余弦相似度计算
- 结合Jaccard相似度和关键词匹配，提升比对准确性

### formatter.py
- `OutputFormatter`: 输出格式化器，支持彩色表格和JSON输出

## 测试

运行所有测试：

```bash
python -m pytest tests/ -v
```

运行单个测试文件：

```bash
python -m pytest tests/test_extractor.py -v
python -m pytest tests/test_indexer.py -v
python -m pytest tests/test_comparator.py -v
```

## 技术栈

- **CLI框架**: Click
- **内容提取**: pdfplumber, python-docx
- **全文检索**: Whoosh
- **中文分词**: Jieba
- **相似度计算**: scikit-learn (TF-IDF + 余弦相似度)
- **终端输出**: Rich, Colorama
- **进度显示**: tqdm

## 优化的合同专业术语

工具内置了超过80个合同专业术语的优化，包括但不限于：
- 甲方、乙方、丙方
- 违约责任、不可抗力、保密条款、知识产权
- 服务期限、付款方式、违约金、赔偿金
- 争议解决、管辖法院、仲裁
- 担保、抵押、质押、保证
- 各类合同类型等

## License

MIT License
