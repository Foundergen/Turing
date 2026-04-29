# 图灵知识图谱构建项目

本项目以艾伦·图灵相关中文文本为语料，完成从文本清洗、实体抽取、关系抽取、事件抽取，到 RDF 存储、质量评估和网页可视化检索的知识图谱构建流程。

项目当前重点不是只生成简单的“实体-关系-实体”三元组，而是同时抽取图灵生平中的核心事件，例如教育经历、论文发表、密码破译、法律迫害、任职和荣誉事件，并把事件作为知识图谱中的重要节点进行组织。

## 项目流程

当前推荐执行顺序如下：

```text
turing_corpus_clean.txt
 -> extract_entities.py
 -> extract_relations.py
 -> extract_events.py
 -> csv_to_rdf.py
 -> eval_extraction.py
 -> visualize_kg.py
```

对应命令：

```powershell
python .\extract_entities.py
python .\extract_relations.py
python .\extract_events.py
python .\csv_to_rdf.py
python .\eval_extraction.py
python .\visualize_kg.py
```

运行完成后，主要结果包括：

- `core_entities_auto.csv`：实体抽取结果
- `turing_triples_auto_audit.csv`：关系抽取审核版
- `turing_triples_core.csv`：关系抽取核心版
- `turing_events_auto_audit.csv`：事件抽取审核版
- `turing_events_core.csv`：事件抽取核心版
- `turing_instances.ttl`：RDF/Turtle 实例数据
- `kg_dashboard.html`：知识图谱可视化与搜索网页

## 核心功能

### 1. 实体抽取

入口文件：

```text
extract_entities.py
```

输入：

```text
turing_corpus_clean.txt
domain_aliases.csv
entity_type_overrides.csv
entity_blocklist.csv
ner_crf.model（可选）
```

输出：

```text
core_entities_auto.csv
```

实体抽取综合使用：

- spaCy 中文 NER
- 规则抽取
- CRF 模型结果，可选加载 `ner_crf.model`
- 别名归一
- 类型覆盖表
- 实体黑名单过滤
- 投票融合与置信度计算

当前实体结果包含主类型和子类型：

```text
实体名称, 实体类型, 实体子类型, 来源, 投票数, 置信度
```

主类型包括：

```text
Person, Organization, Location, Book, Concept, Machine, Event
```

子类型包括：

```text
University, ResearchInstitute, GovernmentAgency, MilitaryAgency,
Paper, Book, Work, Theory, Test, CipherMachine, Country 等
```

### 2. 关系抽取

入口文件：

```text
extract_relations.py
```

输入：

```text
turing_corpus_clean.txt
core_entities_auto.csv
domain_aliases.csv
relation_bin_clf.model（可选）
relation_multi_clf.model（可选）
```

输出：

```text
turing_triples_auto_audit.csv
turing_triples_core.csv
```

关系抽取综合使用：

- 规则触发词
- 开放式关系抽取模式
- 特征向量分类模型
- 实体主类型约束
- 实体子类型约束
- 否定语境过滤
- 置信度评分
- 核心版筛选

关系核心版用于展示和入库，审核版保留更多候选结果，便于人工复核。

三元组字段包括：

```text
头实体, 关系, 尾实体, 来源, 置信度, 触发词, 证据句, 建议人工复核
```

### 3. 事件抽取

入口文件：

```text
extract_events.py
```

输入：

```text
turing_corpus_clean.txt
core_entities_auto.csv
turing_triples_core.csv
domain_aliases.csv
```

输出：

```text
turing_events_auto_audit.csv
turing_events_core.csv
```

事件抽取依赖实体和核心关系结果，在句子级事件识别的基础上补充事件元素。当前支持的事件类型包括：

```text
出生事件
教育事件
发表事件
密码破译事件
法律迫害事件
任职事件
获奖荣誉事件
研究事件
设计开发事件
死亡事件
```

事件字段包括：

```text
event_id, event_type, trigger, subject, time, location, object,
participants, cause, result, previous_event, next_event,
source, confidence, evidence_sentence, review_flag
```

其中：

- `event_id`：事件编号
- `event_type`：事件类型
- `trigger`：触发词
- `subject`：事件主体
- `time`：时间信息
- `location`：地点或机构
- `object`：事件客体
- `participants`：其他参与者
- `cause` / `result`：轻量原因、结果信息
- `previous_event` / `next_event`：按时间串联的前后事件
- `evidence_sentence`：原文证据句
- `review_flag`：是否建议人工复核

### 4. RDF 存储

入口文件：

```text
csv_to_rdf.py
```

输入：

```text
core_entities_auto.csv
turing_triples_core.csv
turing_events_core.csv
```

输出：

```text
turing_instances.ttl
```

`csv_to_rdf.py` 的作用是把 CSV 抽取结果转换为 RDF 图数据，并以 Turtle 格式保存。它与可视化页面是并行关系：

```text
CSV 抽取结果
├─ csv_to_rdf.py -> turing_instances.ttl
└─ visualize_kg.py -> kg_dashboard.html
```

`turing-ontology.owl` 是本体结构文件，可用于说明图谱 schema 或导入 Protégé 等工具；`turing_instances.ttl` 是抽取出的实例数据。

### 5. 质量评估

入口文件：

```text
eval_extraction.py
```

输入：

```text
core_entities_auto.csv
turing_triples_auto_audit.csv
turing_triples_core.csv
turing_events_auto_audit.csv
turing_events_core.csv
```

评估内容包括：

- 实体数量、平均置信度、多来源占比
- 实体主类型和子类型分布
- 关系数量、平均置信度、核心版占比
- 事件数量、事件类型分布、时间/客体/地点完整度
- 综合可靠度指数

该评估不是人工标注准确率，而是基于置信度、来源、结构完整度和复核标记得到的自动质量统计。

### 6. 可视化与搜索

入口文件：

```text
visualize_kg.py
```

输入：

```text
core_entities_auto.csv
turing_triples_core.csv
turing_events_core.csv
```

输出：

```text
kg_dashboard.html
```

网页中包含：

- 实体关系网络图，带方向箭头
- 核心事件时间线
- 未明确时间事件分区
- 实体类型、实体子类型、关系类型、事件类型统计
- 核心三元组明细表
- 知识搜索框，可同时检索实体、关系和事件

打开 `kg_dashboard.html` 即可查看结果。重新抽取后，只需再次运行：

```powershell
python .\visualize_kg.py
```

即可刷新网页数据。

## 文件说明

### 主流程代码

| 文件 | 作用 |
|------|------|
| `extract_entities.py` | 实体抽取 |
| `extract_relations.py` | 关系抽取 |
| `extract_events.py` | 事件抽取 |
| `csv_to_rdf.py` | CSV 转 RDF/Turtle |
| `eval_extraction.py` | 抽取质量统计 |
| `visualize_kg.py` | 生成可视化网页 |

### 数据与配置

| 文件 | 作用 |
|------|------|
| `turing_corpus.txt` | 原始语料 |
| `turing_corpus_clean.txt` | 清洗后的简体语料，当前抽取主输入 |
| `domain_aliases.csv` | 别名表 |
| `entity_type_overrides.csv` | 实体类型覆盖表 |
| `entity_blocklist.csv` | 实体黑名单 |
| `turing-ontology.owl` | 本体结构文件 |

### 模型与训练脚本

| 文件 | 作用 |
|------|------|
| `ner_crf.model` | 实体识别 CRF 模型 |
| `relation_bin_clf.model` | 关系二分类模型 |
| `relation_multi_clf.model` | 关系多分类模型 |
| `train_ner_crf.py` | 训练实体 CRF 模型 |
| `train_relation_clf.py` | 训练关系分类模型 |

训练脚本不是每次运行主流程都必须执行。当前抽取脚本会直接读取已有模型；如果模型文件不存在，则对应模型分支会降级或跳过。

### 数据准备脚本

| 文件 | 作用 |
|------|------|
| `spider_turing.py` | 抓取图灵相关原始文本 |
| `clean_data.py` | 清洗语料并转换为简体 |

这两个脚本主要用于语料准备。当前已有 `turing_corpus_clean.txt`，因此日常抽取不必重复运行。

## 环境依赖

推荐 Python 3.10+。

常用依赖：

```powershell
pip install requests zhconv spacy sklearn-crfsuite joblib scikit-learn rdflib
python -m spacy download zh_core_web_sm
```

如果只查看已有 CSV 和 HTML，不需要安装全部依赖；如果要完整重跑抽取流程，则建议安装上述依赖。

## 当前结果概览

最近一次运行结果为：

```text
实体：74 条
关系审核版：34 条
关系核心版：15 条
事件审核版：62 条
事件核心版：22 条
```

评估脚本输出的核心指标包括：

```text
实体综合可靠度指数：74.69
关系综合可靠度指数：90.64
事件核心版综合可靠度指数：86.23
```

这些指标用于项目内部质量观察，不等同于人工标注准确率。

## 推荐提交文件

如果用于课程作业或项目展示，建议至少保留：

```text
extract_entities.py
extract_relations.py
extract_events.py
csv_to_rdf.py
eval_extraction.py
visualize_kg.py

turing_corpus_clean.txt
domain_aliases.csv
entity_type_overrides.csv
entity_blocklist.csv

core_entities_auto.csv
turing_triples_auto_audit.csv
turing_triples_core.csv
turing_events_auto_audit.csv
turing_events_core.csv
turing_instances.ttl
turing-ontology.owl
kg_dashboard.html

ner_crf.model
relation_bin_clf.model
relation_multi_clf.model
```

可选保留：

```text
spider_turing.py
clean_data.py
train_ner_crf.py
train_relation_clf.py
turing_corpus.txt
turing_triples_clean.csv
```

这些文件用于说明数据准备和模型训练来源，但不是每次运行当前知识图谱构建主流程都必须使用。
