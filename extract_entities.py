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
        "艾伦": "艾伦·图灵",
        "艾伦·麦席森·图灵": "艾伦·图灵",
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

ORG_SUFFIXES = (
    "大学", "学院", "学校", "实验室", "研究所", "研究院", "学会",
    "协会", "政府", "海军", "司法部", "国会", "议院",
)
LOC_SUFFIXES = ("国", "州", "郡", "市", "省", "县", "岛", "洋", "海", "城", "洲")
EVENT_HINTS = ("战争", "运动会", "审判", "纪念", "大会")
MACHINE_HINTS = ("机器", "密码机", "引擎", "计算机", "设备")
CONCEPT_HINTS = ("理论", "测试", "智能", "科学", "主义", "方法")
PERSON_CONTEXT_HINTS = (
    "出生", "生于", "提出", "认为", "证明", "写道", "发明", "研究",
    "毕业", "就读", "父亲", "母亲", "同事", "导师", "数学家",
    "逻辑学家", "科学家", "教授",
)
LOCATION_CONTEXT_HINTS = ("位于", "来到", "前往", "抵达", "迁往", "来自", "出生于", "生于")
ORGANIZATION_CONTEXT_HINTS = ("任职于", "加入", "就读于", "毕业于", "工作于", "服务于", "属于")
GENERIC_ORG_NAMES = {"实验室", "研究院", "研究所", "学院", "大学", "学会", "协会", "政府"}


def collect_context_windows(text: str, name: str, window: int = 16, limit: int = 8):
    if not text or not name:
        return []
    windows = []
    start = 0
    while len(windows) < limit:
        idx = text.find(name, start)
        if idx == -1:
            break
        left = max(0, idx - window)
        right = min(len(text), idx + len(name) + window)
        windows.append(text[left:right])
        start = idx + len(name)
    return windows


def score_by_name_shape(name: str):
    scores = Counter()
    if name.startswith("《") and name.endswith("》"):
        scores["Book"] += 8
    if any(name.endswith(suffix) for suffix in ORG_SUFFIXES):
        scores["Organization"] += 5
    if any(name.endswith(suffix) for suffix in LOC_SUFFIXES):
        scores["Location"] += 4
    if any(hint in name for hint in EVENT_HINTS):
        scores["Event"] += 5
    if any(hint in name for hint in MACHINE_HINTS):
        scores["Machine"] += 5
    if any(hint in name for hint in CONCEPT_HINTS):
        scores["Concept"] += 4
    if "·" in name:
        scores["Person"] += 6
    if re.fullmatch(r"[A-Za-z][A-Za-z.\s-]{2,}", name):
        scores["Person"] += 4
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name):
        scores["Person"] += 1
    return scores


def score_by_context(name: str, windows):
    scores = Counter()
    for window in windows:
        if any(word in window for word in PERSON_CONTEXT_HINTS):
            scores["Person"] += 1
        if any(word in window for word in LOCATION_CONTEXT_HINTS):
            scores["Location"] += 1
        if any(word in window for word in ORGANIZATION_CONTEXT_HINTS):
            scores["Organization"] += 1
        if any(word in window for word in EVENT_HINTS):
            scores["Event"] += 1
        if any(word in window for word in MACHINE_HINTS):
            scores["Machine"] += 1
        if any(word in window for word in CONCEPT_HINTS):
            scores["Concept"] += 1
        if "《" in window and "》" in window:
            scores["Book"] += 1
        if re.search(r"(与|和|及|、)" + re.escape(name) + r"(、|和|及|一同)", window):
            scores["Person"] += 1
    return scores


def choose_final_type(name: str, vote_counter: Counter, text: str):
    combined = Counter()
    combined.update(vote_counter)
    combined.update(score_by_name_shape(name))
    windows = collect_context_windows(text, name)
    combined.update(score_by_context(name, windows))
    final_type = choose_type(combined)
    final_type = calibrate_entity_type(name, final_type) if final_type else ""
    return final_type, windows


def looks_like_person_fragment(name: str, sources: set, votes: int, windows):
    if "·" in name or " " in name or re.search(r"[A-Za-z]", name):
        return False
    if len(name) <= 1:
        return True
    if len(name) == 2 and votes <= 6:
        return True
    if len(name) == 3 and sources == {"spacy"} and votes <= 3:
        context = "".join(windows)
        if not any(word in context for word in PERSON_CONTEXT_HINTS):
            return True
    return False


def looks_like_generic_org(name: str, sources: set, votes: int):
    if sources != {"spacy"} or votes > 3:
        return False
    if name in GENERIC_ORG_NAMES:
        return True
    return name.startswith("国家") and name.endswith(("实验室", "研究院", "研究所")) and len(name) <= 5


def low_support_ambiguous_location(name: str, sources: set, votes: int, windows):
    if any(name.endswith(suffix) for suffix in LOC_SUFFIXES):
        return False
    if len(name) > 3 or votes > 3 or sources != {"spacy"}:
        return False
    context = "".join(windows)
    return not any(word in context for word in LOCATION_CONTEXT_HINTS)


def drop_prefix_fragments(entities):
    kept = []
    for entity in sorted(entities, key=lambda x: (-len(x[0]), -x[3], x[0])):
        name, typ, _, votes, _ = entity
        is_fragment = False
        for kept_entity in kept:
            kept_name, kept_type, _, kept_votes, _ = kept_entity
            if typ != kept_type:
                continue
            if len(name) < 3 or len(kept_name) - len(name) > 4:
                continue
            if kept_votes < votes:
                continue
            if kept_name.startswith(name):
                is_fragment = True
                break
        if not is_fragment:
            kept.append(entity)
    return kept

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
        final_type, windows = choose_final_type(name, c, text)
        if not final_type:
            continue
        total_votes = sum(c.values())
        confidence = round(c.get(final_type, max(c.values())) / total_votes, 3) if total_votes else 0.0
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
        if final_type == "Person" and looks_like_person_fragment(name, src_set, total_votes, windows):
            continue
        if final_type == "Organization" and looks_like_generic_org(name, src_set, total_votes):
            continue
        if final_type == "Location" and low_support_ambiguous_location(name, src_set, total_votes, windows):
            continue
        if final_type == "Person" and src_set == {"crf"} and "·" in name and len(name) <= 4:
            continue
        if final_type == "Location" and src_set == {"crf"} and len(name) == 3 and name.endswith("国"):
            if name[:-1] in merged_votes:
                continue
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

    final_entities = drop_prefix_fragments(final_entities)
    final_entities.sort(key=lambda x: (x[1], x[0]))

    # 自动结果：前两列供下游关系抽取；后列为自检/评估用
    with open("core_entities_auto.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["实体名称", "实体类型", "来源", "投票数", "置信度"])
        writer.writerows(final_entities)

    print(f"提取完成：core_entities_auto.csv 共 {len(final_entities)} 条实体")

if __name__ == "__main__":
    extract_and_save_entities()
