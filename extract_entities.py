import csv
import re
from collections import Counter, defaultdict

try:
    import spacy
except ImportError:
    spacy = None

try:
    import sklearn_crfsuite
except ImportError:
    sklearn_crfsuite = None

TYPE_PRIORITY = [
    "Person",
    "Organization",
    "Location",
    "Event",
    "Machine",
    "Concept",
    "Book",
]

def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def build_alias_map():
    return {
        "图灵": "艾伦·图灵",
        "Turing": "艾伦·图灵",
        "阿兰·图灵": "艾伦·图灵",
        "二战": "第二次世界大战",
        "二次世界大战": "第二次世界大战",
        "剑桥": "剑桥大学",
        "普林斯顿": "普林斯顿大学",
        "恩尼格玛": "恩尼格玛密码机",
        "《每日电讯报》": "每日电讯报",
    }


BOOK_TITLE_AS_ORGANIZATION = frozenset({"《每日电讯报》"})
# 别名合并后仅 rule 的机构名，无 spaCy 时也要能保留
RULE_ONLY_ORGANIZATION_ALLOWLIST = frozenset({"每日电讯报"})
 
def map_spacy_label(label: str) -> str:
    if label == "PERSON":
        return "Person"
    if label == "ORG":
        return "Organization"
    if label in {"GPE", "LOC"}:
        return "Location"
    if label == "EVENT":
        return "Event"
    return ""

def guess_type_by_rule(entity_name: str) -> str:
    if "《" in entity_name and "》" in entity_name:
        return "Book"
    if any(word in entity_name for word in ["大学", "学院", "实验室", "学会", "协会", "政府", "研究所"]):
        return "Organization"
    if any(word in entity_name for word in ["战争", "审判", "赦免", "运动会"]):
        return "Event"
    if any(word in entity_name for word in ["机器", "密码机", "引擎", "破译机"]):
        return "Machine"
    if any(word in entity_name for word in ["理论", "图灵测试", "生物学", "计算机科学"]):
        return "Concept"
    if "科学" in entity_name and len(entity_name) <= 8:
        return "Concept"
    return ""

def looks_like_sentence_fragment(s: str) -> bool:
    """规则命中片段常为半句，过滤可降低 Concept 等误分。"""
    if re.search(r"[的了着过吗呢吧嘛呀噢欸]", s):
        return True
    if re.search(r"^[与及为在是以而但并]", s) or re.search(r"[与及为在是以而但并]$", s):
        return True
    # CRF 常见半句概念碎片
    if re.search(r"而不是|天生对|对科学|而不是科|人文学科而", s):
        return True
    if re.search(r"奖学金|基金会|宝洁", s):
        return True
    return False

# 传记语料里 spaCy/CRF 高频误检；按类型丢弃（无金标时的强先验）
ENTITY_BLOCKLIST_BY_TYPE = {
    "Person": {
        "档案馆",
        "氰化物",
        "叶序列",
        "波兰战",
        "英国电脑",
        "圣迈克尔",
        "God",
        "GC",
        "希尔顿",
        "林斯顿",
    },
    "Location": {"勋爵", "麦克纳利"},
    "Organization": {"通用", "英国皇家", "英国电脑"},
}


def should_drop_by_blocklist(name: str, typ: str) -> bool:
    blocked = ENTITY_BLOCKLIST_BY_TYPE.get(typ)
    return bool(blocked and name in blocked)

def calibrate_entity_type(name: str, typ: str) -> str:
    """用语形与后缀纠正常见类型漂移。"""
    if typ == "Person":
        if any(x in name for x in ["大学", "学院", "实验室", "学会", "协会", "政府", "研究所", "学校"]):
            return "Organization"
        # 郡/州名常被 zh 模型标成人名
        if "郡" in name or name.endswith("州"):
            return "Location"
    if typ == "Organization":
        if name.endswith("州") or name.endswith("省"):
            return "Location"
    if typ in {"Concept", "Event"} and len(name) <= 4:
        if name in {"英国", "美国", "德国", "法国", "印度", "波兰", "欧洲", "伦敦"}:
            return "Location"
    return typ

def choose_type(type_counter: Counter) -> str:
    if not type_counter:
        return ""
    max_count = max(type_counter.values())
    tied = [t for t, c in type_counter.items() if c == max_count]
    tied.sort(key=lambda t: TYPE_PRIORITY.index(t) if t in TYPE_PRIORITY else 999)
    return tied[0]

def is_valid_entity_name(name: str) -> bool:
    if len(name) < 2 or len(name) > 18:
        return False
    bad_tokens = ["，", "。", "：", "；", "？", "！", "（", "）", "==", "http", "页面存档", "……", "——"]
    if any(t in name for t in bad_tokens):
        return False
    if re.fullmatch(r"\d+", name):
        return False
    # 过长且无专名特征的英文碎片
    if len(name) > 12 and re.search(r"[A-Za-z]", name) and not re.search(r"[\u4e00-\u9fff]", name):
        return False
    return True

def char_features(chars, i):
    ch = chars[i]
    return {
        "bias": 1.0,
        "ch": ch,
        "is_digit": ch.isdigit(),
        "is_alpha": ch.isalpha(),
        "is_cjk": "\u4e00" <= ch <= "\u9fff",
        "prev": chars[i - 1] if i > 0 else "<BOS>",
        "next": chars[i + 1] if i < len(chars) - 1 else "<EOS>",
    }

def sentence_to_features(sentence):
    chars = list(sentence)
    return [char_features(chars, i) for i in range(len(chars))]

def bio_to_spans(text, tags):
    spans = []
    start = -1
    cur_type = ""
    for i, tag in enumerate(tags):
        if tag.startswith("B-"):
            if start != -1:
                spans.append((start, i, cur_type))
            start = i
            cur_type = tag[2:]
        elif tag.startswith("I-"):
            if start == -1:
                start = i
                cur_type = tag[2:]
        else:
            if start != -1:
                spans.append((start, i, cur_type))
                start = -1
                cur_type = ""
    if start != -1:
        spans.append((start, len(tags), cur_type))
    entities = []
    for s, e, t in spans:
        ent = normalize_name(text[s:e])
        if len(ent) > 1:
            entities.append((ent, t))
    return entities

def load_crf_model_or_none(model_path="ner_crf.model"):
    if sklearn_crfsuite is None:
        return None
    try:
        import joblib
    except ImportError:
        return None
    try:
        return joblib.load(model_path)
    except Exception:
        return None

def extract_by_crf(text):
    """
    可选 CRF 路径：仅在存在 ner_crf.model 且依赖可用时启用。
    """
    model = load_crf_model_or_none()
    if model is None:
        return []
    entities = []
    sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
    for sentence in sentences:
        feats = sentence_to_features(sentence)
        pred = model.predict_single(feats)
        for ent, typ in bio_to_spans(sentence, pred):
            mapped = typ if typ in TYPE_PRIORITY else ""
            if mapped:
                entities.append((ent, mapped))
    return entities

def extract_and_save_entities():
    print("正在读取图灵语料...")
    with open("turing_corpus_clean.txt", "r", encoding="utf-8") as f:
        text = f.read()

    votes = defaultdict(Counter)
    source_counter = defaultdict(Counter)

    # A. spaCy NER（可选）
    if spacy is not None:
        try:
            print("执行实体抽取：spaCy NER + 规则 + CRF(可选)...")
            nlp = spacy.load("zh_core_web_sm")
            doc = nlp(text)
            for ent in doc.ents:
                clean_text = normalize_name(ent.text)
                if len(clean_text) <= 1:
                    continue
                label = map_spacy_label(ent.label_)
                if label:
                    votes[clean_text][label] += 3
                    source_counter[clean_text]["spacy"] += 1
        except Exception:
            print("spaCy 模型不可用，已跳过 NER 路径。")
    else:
        print("未安装 spaCy，已跳过 NER 路径。")

    # B. 基于文本形态的规则补充
    for m in re.findall(r"《[^《》]{2,40}》", text):
        name = normalize_name(m)
        if name in BOOK_TITLE_AS_ORGANIZATION:
            votes[name]["Organization"] += 2
        else:
            votes[name]["Book"] += 2
        source_counter[name]["rule"] += 1

    sentences = re.split(r"[。！？\n]", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        for token in re.findall(r"[A-Za-z0-9·\u4e00-\u9fa5《》]{2,40}", sentence):
            token = normalize_name(token)
            if len(token) > 14:
                continue
            if looks_like_sentence_fragment(token):
                continue
            guessed = guess_type_by_rule(token)
            if not guessed:
                continue
            if guessed == "Concept" and len(token) > 10:
                continue
            votes[token][guessed] += 1
            source_counter[token]["rule"] += 1

    # C. CRF 路径（可选）
    crf_entities = extract_by_crf(text)
    for name, typ in crf_entities:
        votes[name][typ] += 2
        source_counter[name]["crf"] += 1

    # D. 别名统一
    alias_map = build_alias_map()
    merged_votes = defaultdict(Counter)
    merged_source = defaultdict(Counter)
    for raw_name, c in votes.items():
        std_name = alias_map.get(raw_name, raw_name)
        if not is_valid_entity_name(std_name):
            continue
        for t, v in c.items():
            merged_votes[std_name][t] += v
        for src, v in source_counter[raw_name].items():
            merged_source[std_name][src] += v

    # 组装结果
    final_entities = []
    for name, c in merged_votes.items():
        final_type = choose_type(c)
        if not final_type:
            continue
        total_votes = sum(c.values())
        calibrated = calibrate_entity_type(name, final_type)
        if calibrated != final_type:
            rel_votes = max(c.get(calibrated, 0), c.get(final_type, 0))
            final_type = calibrated
            confidence = round(rel_votes / total_votes, 3) if total_votes else 0.0
        else:
            confidence = round(c[final_type] / total_votes, 3) if total_votes else 0.0
        if should_drop_by_blocklist(name, final_type):
            continue
        if final_type == "Concept" and looks_like_sentence_fragment(name):
            continue
        # 纪念活动/年份类碎片，不宜作人物节点
        if final_type == "Person" and name.endswith("年") and "图灵" in name:
            continue
        # 奖学金/基金全称常被 NER 标成人名
        if final_type == "Person" and ("奖学金" in name or "基金会" in name):
            continue
        # 极短纯西文人名碎片，传记中多为噪声指代
        if final_type == "Person" and len(name) <= 6 and re.fullmatch(r"[A-Za-z·.\s]+", name):
            if name.count(" ") < 1 and len(name.replace("·", "")) < 6:
                continue
        src_set = set(merged_source[name].keys())
        model_sources = {"spacy", "crf"}
        has_model = bool(src_set & model_sources)
        rule_only = src_set == {"rule"}
        # 仅 CRF 的长串 Concept 误分多，略收紧
        if final_type == "Concept" and src_set == {"crf"} and len(name) > 6:
            if confidence < 0.95:
                continue
        if rule_only and final_type == "Concept":
            if confidence < 0.85 or len(name) > 8:
                continue
        if rule_only and final_type in {"Event", "Machine"}:
            if confidence < 0.75:
                continue
        keep = (confidence >= 0.72) or (len(src_set & model_sources) >= 2 and confidence >= 0.55)
        keep = keep and (
            has_model
            or (final_type == "Book" and "rule" in src_set)
            or (
                final_type == "Organization"
                and name in RULE_ONLY_ORGANIZATION_ALLOWLIST
                and "rule" in src_set
            )
        )
        keep = keep and len(name) <= 16
        if not keep:
            continue
        final_entities.append(
            (
                name,
                final_type,
                "+".join(sorted(merged_source[name].keys())),
                total_votes,
                confidence,
            )
        )

    final_entities.sort(key=lambda x: (x[1], x[0]))

    # 自动结果：前两列供下游关系抽取；后列为自检/评估用
    with open("core_entities_auto.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["实体名称", "实体类型", "来源", "投票数", "置信度"])
        writer.writerows(final_entities)

    print(f"提取完成：core_entities_auto.csv 共 {len(final_entities)} 条实体")

if __name__ == "__main__":
    extract_and_save_entities()