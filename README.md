# Turing


从中文维基开放接口获取「艾伦·图灵」词条正文，经简繁清洗后，结合**词典弱标注**训练字级 **CRF** 命名实体模型，再与 **spaCy 中文 NER**、规则融合，输出自动实体表 `core_entities_auto.csv`。


| 文件 | 作用 |
|------|------|
| `spider_turing.py` | 拉取维基正文 → `turing_corpus.txt` |
| `clean_data.py` | 简繁转换 → `turing_corpus_clean.txt` |
| `core_entities.csv` | 核心实体词典（名称、类型），供 CRF 弱标注 |
| `train_ner_crf.py` | 训练 CRF → `ner_crf.model`（运行后生成，可不纳入 Git） |
| `extract_entities.py` | spaCy + 规则 + 可选 CRF，写出 `core_entities_auto.csv` |

## 环境依赖

```bash
pip install requests zhconv spacy sklearn-crfsuite joblib
python -m spacy download zh_core_web_sm
```

- **Python 3.10+** 推荐（与 spaCy 版本匹配即可）。

## 使用顺序

在项目根目录执行：

### 1. 抓取语料

```bash
python spider_turing.py
```

生成 `turing_corpus.txt`。


### 2. 清洗语料

```bash
python clean_data.py
```

读取 `turing_corpus.txt`，输出全简体 `turing_corpus_clean.txt`。

### 3. 训练 CRF（可选）

```bash
python train_ner_crf.py
```

依赖：`turing_corpus_clean.txt`、`core_entities.csv`。成功后得到 **`ner_crf.model`**，供 `extract_entities.py` 自动加载。

若跳过此步，抽取脚本仍可通过 spaCy 与规则运行，但 **CRF 分支不会贡献结果**。

### 4. 实体抽取

```bash
python extract_entities.py
```

读取 `turing_corpus_clean.txt`，写入 **`core_entities_auto.csv`**（UTF-8，列为：实体名称、实体类型、来源、投票数、置信度）。

## `core_entities.csv` 格式

- 第一行为表头，后续每行至少两列：**实体名称**、**实体类型**（与 `extract_entities.py` 中类型体系一致，如 Person、Location 等）。
- 用于在语料中匹配跨度并构造 CRF 的 BIO 标签；实体宜按**名称长度从长到短**维护（脚本内已对词典排序，但源文件仍建议长词在前以减少重叠歧义）。

## 类型与融合逻辑（摘要）

- **spaCy**：`zh_core_web_sm` 整篇标注。
- **规则**：书名号著作、机构/事件/机器/概念等形态启发式。
- **CRF**：存在 `ner_crf.model` 时按句预测，与上述结果**投票合并**并做简单类型校准与过滤。

详细规则见 `extract_entities.py` 内注释与常量。


## 后续扩展

关系抽取、三元组导出、RDF/图数据库导入等。
