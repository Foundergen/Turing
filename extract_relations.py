import csv
import re
import itertools
from collections import defaultdict

try:
    import joblib
except ImportError:
    joblib = None

RELATION_CATALOG = {
    "出生于": "人物 -> 地点",
    "国籍": "人物 -> 地点",
    "就读于": "人物 -> 组织",
    "毕业于": "人物 -> 组织",
    "任职于": "人物 -> 组织",
    "师从": "人物 -> 人物",
    "合作": "人物 -> 人物",
    "父亲": "人物 -> 人物",
    "母亲": "人物 -> 人物",
    "参与": "人物/组织 -> 事件",
    "参与破解": "人物/组织 -> 机器",
    "提出": "人物 -> 概念/机器",
    "研究": "人物 -> 概念/机器",
    "撰写": "人物 -> 作品",
    "发表": "人物 -> 作品/概念",
    "证明": "人物 -> 概念",
    "获得": "人物 -> 概念/荣誉",
    "设计": "人物/组织 -> 机器/概念",
    "改进": "人物/组织 -> 机器",
    "开发": "人物/组织 -> 机器/概念",
    "聘请": "人物/组织 -> 人物",
    "迫害": "组织/地点 -> 人物",
    "誉为": "人物 -> 概念",
    "当选院士": "人物 -> 组织",
    "属于": "组织/机器 -> 地点",
    "设立": "组织 -> 概念",
    "相关": "兜底弱关系",
}

RELATION_TRIGGER_RULES = {
    "出生": "出生于",
    "出生于": "出生于",
    "生于": "出生于",
    "国籍": "国籍",
    "就读": "就读于",
    "就读于": "就读于",
    "毕业": "就读于",
    "毕业于": "就读于",
    "考入": "就读于",
    "毕业": "毕业于",
    "获博士学位": "毕业于",
    "任职": "任职于",
    "任职于": "任职于",
    "工作": "任职于",
    "工作于": "任职于",
    "加入": "任职于",
    "服务于": "任职于",
    "供职于": "任职于",
    "导师": "师从",
    "师从": "师从",
    "指导": "师从",
    "同事": "合作",
    "合作": "合作",
    "共事": "合作",
    "父亲": "父亲",
    "母亲": "母亲",
    "参与": "参与",
    "参加": "参与",
    "投身": "参与",
    "破解": "参与破解",
    "破译": "参与破解",
    "解密": "参与破解",
    "提出": "提出",
    "发明": "设计",
    "设计": "设计",
    "制作": "开发",
    "开发": "开发",
    "研制": "开发",
    "改进": "改进",
    "发表": "发表",
    "发布": "发表",
    "证明": "证明",
    "获得": "获得",
    "获": "获得",
    "聘请": "聘请",
    "招聘": "聘请",
    "迫害": "迫害",
    "被誉为": "誉为",
    "称赞": "誉为",
    "研究": "研究",
    "探讨": "研究",
    "撰写": "撰写",
    "写了": "撰写",
    "写成": "撰写",
    "著有": "撰写",
    "著作": "撰写",
    "院士": "当选院士",
    "当选": "当选院士",
    "属于": "属于",
    "隶属": "属于",
    "位于": "属于",
    "设立": "设立",
    "颁发": "设立",
    "授予": "设立",
}

RELATION_LABEL_ALIASES = {
    "博士导师": "师从",
    "同事": "合作",
    "获选院士": "当选院士",
    "毕业": "毕业于",
}

CANDIDATE_TYPE_PAIRS = {
    ("Person", "Location"),
    ("Person", "Organization"),
    ("Person", "Person"),
    ("Person", "Event"),
    ("Person", "Machine"),
    ("Person", "Concept"),
    ("Person", "Book"),
    ("Organization", "Person"),
    ("Organization", "Location"),
    ("Organization", "Event"),
    ("Organization", "Machine"),
    ("Organization", "Concept"),
    ("Machine", "Location"),
    ("Location", "Person"),
}

STRICT_BETWEEN_RELATIONS = {
    "出生于",
    "国籍",
    "就读于",
    "任职于",
    "参与破解",
    "提出",
    "撰写",
    "发表",
    "证明",
    "设计",
    "改进",
    "开发",
    "聘请",
    "迫害",
}

NEGATION_CUES = ("不", "没有", "未", "无", "并非", "不是", "谢绝")
PASSIVE_CUES = ("被", "遭到", "由")

OPEN_PREDICATE_RELATION_PATTERNS = [
    ("出生于", (r"(?:出生|生于|生下)",), {("Person", "Location")}),
    ("就读于", (r"(?:考入|就读|入读|攻读|求学)",), {("Person", "Organization")}),
    ("毕业于", (r"(?:毕业|获.{0,6}学位)",), {("Person", "Organization")}),
    ("任职于", (r"(?:任职|供职|服务|工作|兼职|加入|负责|成为.{0,10}(?:主任|研究员|成员))",), {("Person", "Organization")}),
    ("当选院士", (r"(?:被选为|当选|成为).{0,12}(?:院士|会士|FRS|成员)",), {("Person", "Organization")}),
    ("师从", (r"(?:导师|师从|指导)",), {("Person", "Person")}),
    ("合作", (r"(?:合作|共事|一起|与.{0,12}共同)",), {("Person", "Person")}),
    ("参与", (r"(?:参与|参加|投身|主要参与者|期间)",), {("Person", "Event"), ("Organization", "Event")}),
    ("参与破解", (r"(?:破解|破译|解密|密码分析)",), {("Person", "Machine"), ("Organization", "Machine")}),
    ("提出", (r"(?:提出|叫做|称为|定义为)",), {("Person", "Concept"), ("Person", "Machine")}),
    ("研究", (r"(?:研究|探讨|研究工作|兴趣是|应用)",), {("Person", "Concept"), ("Person", "Machine")}),
    ("撰写", (r"(?:撰写|写过|写了|著有|论文|名为)",), {("Person", "Book")}),
    ("发表", (r"(?:发表|发布|出版)",), {("Person", "Book"), ("Person", "Concept")}),
    ("证明", (r"(?:证明|展示)",), {("Person", "Concept")}),
    ("获得", (r"(?:获得|获)",), {("Person", "Concept")}),
    ("设计", (r"(?:设计|发明)",), {("Person", "Machine"), ("Person", "Concept"), ("Organization", "Machine")}),
    ("改进", (r"(?:改进|优化)",), {("Person", "Machine"), ("Organization", "Machine")}),
    ("开发", (r"(?:开发|研制|制作|建造)",), {("Person", "Machine"), ("Person", "Concept"), ("Organization", "Machine")}),
    ("聘请", (r"(?:聘请|招聘)",), {("Person", "Person"), ("Organization", "Person")}),
    ("迫害", (r"(?:迫害|处罚|起诉)",), {("Organization", "Person"), ("Location", "Person")}),
    ("誉为", (r"(?:被誉为|称赞|称为)",), {("Person", "Concept")}),
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def load_domain_aliases(path: str = "domain_aliases.csv") -> dict:
    """从外部词典读取别名归一规则，避免把语料专属简称写死在代码里。"""
    aliases = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("enabled", "1")).strip() in {"0", "false", "False", "否"}:
                    continue
                alias = normalize_text(row.get("alias", ""))
                canonical = normalize_text(row.get("canonical", ""))
                if alias and canonical and alias != canonical:
                    aliases[alias] = canonical
    except FileNotFoundError:
        pass
    return aliases


def build_alias_map():
    return load_domain_aliases()


MINED_ENTITY_PATTERNS = [
    ("Book", r"《[^》]{2,50}》"),
    ("Organization", r"[\u4e00-\u9fffA-Za-z0-9·（）()“”\"-]{2,32}(?:大学|学院|实验室|研究所|研究院|学会|协会|政府|海军|国会|司法部|密码学校|小组|委员会|档案馆|俱乐部|公司)"),
    ("Machine", r"[\u4e00-\u9fffA-Za-z0-9·（）()“”\"-]{2,32}(?:密码机|破译机|计算机|引擎|乘法器|程序|装置|机器|机)"),
    ("Machine", r"机器\s*([A-Za-z][A-Za-z0-9-]{1,24})"),
    ("Concept", r"[\u4e00-\u9fffA-Za-z0-9·（）()“”\"-]{2,36}(?:之父|密码分析|生物数学|图案形成|叶序列|理论|测试|问题|定理|概念|公式|系统|科学|智能|密码学|荣誉|勋章|会士)"),
    ("Event", r"[\u4e00-\u9fffA-Za-z0-9·（）()“”\"-]{2,24}(?:战争|战役|运动会|大罢工)"),
    ("Location", r"[\u4e00-\u9fffA-Za-z0-9·（）()“”\"-]{2,24}(?:州|郡|市|镇|庄园|附近|印度)"),
]

MINED_ENTITY_PREFIX_STOPWORDS = (
    "在", "于", "从", "和", "与", "及", "对", "为", "由", "把", "被", "该", "这", "那", "一个", "一种", "他的", "她的", "其",
    "后来", "期间", "其中", "例如", "包括", "除了", "虽然", "但是", "因为", "所以",
)

MINED_ENTITY_CUES = (
    "考入", "任职于", "工作于", "负责", "成为", "遭到", "提供了", "使用的", "解密", "专注于", "基于",
    "建造了", "设计出", "提出了", "叫做", "所谓的", "真正的", "最早的", "即", "在", "于", "对",
    "被", "由", "向", "给", "当时的",
)

MINED_ENTITY_BAD_FRAGMENTS = (
    "提出", "研究", "证明", "设计", "负责", "成为", "考入", "破译", "招聘", "提供", "继续", "介绍",
    "应用", "称赞", "被誉为", "发挥", "帮助", "显示", "尝试", "允许", "无法", "没有", "不是",
)

WEAK_ORGANIZATION_NAMES = {"小组", "委员会", "研究组"}


def normalize_mined_entity(name: str, typ: str) -> str:
    name = normalize_text(name).strip(" ，,。；;：:（）()“”\"'、")
    for sep in ("。", "，", ",", "；", ";", "：", ":", "、", "（", "(", "“", "\""):
        if sep in name:
            parts = [part.strip(" ，,。；;：:（）()“”\"'、") for part in name.split(sep) if part.strip(" ，,。；;：:（）()“”\"'、")]
            if parts:
                name = parts[-1]
    for cue in MINED_ENTITY_CUES:
        if cue in name:
            tail = name.rsplit(cue, 1)[-1].strip(" ，,。；;：:（）()“”\"'、")
            if len(tail) >= 2:
                name = tail
    if typ != "Book" and "的" in name:
        tail = name.rsplit("的", 1)[-1].strip(" ，,。；;：:（）()“”\"'、")
        if len(tail) >= 2:
            name = tail
    for sep in ("为", "是", "将", "把", "用", "以"):
        if sep in name:
            tail = name.rsplit(sep, 1)[-1].strip(" ，,。；;：:（）()“”\"'、")
            if len(tail) >= 2:
                name = tail
    for prefix in ("密码系统", "机密军事密码", "德国机密军事密码"):
        if name.startswith(prefix) and len(name) > len(prefix) + 2:
            name = name[len(prefix):].strip(" ，,。；;：:（）()“”\"'、")
    for prefix in MINED_ENTITY_PREFIX_STOPWORDS:
        if name.startswith(prefix) and len(name) > len(prefix) + 2:
            name = name[len(prefix):].strip(" ，,。；;：:（）()“”\"'、")
    if typ == "Book" and not (name.startswith("《") and name.endswith("》")):
        name = f"《{name}》"
    return name


def is_valid_mined_entity(name: str, typ: str) -> bool:
    if not name or len(name) < 2 or len(name) > 50:
        return False
    if name.isdigit():
        return False
    if any(punc in name for punc in "\n。！？；;"):
        return False
    if any(fragment in name for fragment in MINED_ENTITY_BAD_FRAGMENTS):
        return False
    if len(name) > 2 and any(name.startswith(prefix) for prefix in MINED_ENTITY_PREFIX_STOPWORDS):
        return False
    weak_machine_terms = {"机器", "计算机", "程序", "装置", "机"}
    if typ == "Machine" and name in weak_machine_terms:
        return False
    if typ == "Machine" and re.fullmatch(r"[\u4e00-\u9fff]{2}机", name):
        return False
    weak_concepts = {"理论", "概念", "系统", "科学", "智能", "问题", "测试", "停机"}
    if typ == "Concept" and name in weak_concepts:
        return False
    if typ == "Organization" and name in WEAK_ORGANIZATION_NAMES:
        return False
    return True


def mine_relation_entities(text: str):
    mined = []
    seen = set()
    for typ, pattern in MINED_ENTITY_PATTERNS:
        for match in re.finditer(pattern, text):
            raw = match.group(1) if match.groups() else match.group(0)
            name = normalize_mined_entity(raw, typ)
            if not is_valid_mined_entity(name, typ):
                continue
            key = (name, typ)
            if key in seen:
                continue
            seen.add(key)
            mined.append((name, typ, match.group(0)))
    return mined


def register_mined_entities(text: str, entity_type_map: dict, alias_map: dict, entities: list):
    """
    用通用表面形式补充关系抽取所需的候选实体。
    这样可以避免把特定语料里的标准答案写进关系抽取器。
    """
    for name, typ, surface in mine_relation_entities(text):
        entity_type_map.setdefault(name, typ)
        alias_map.setdefault(name, name)
        entities.append(name)
        if surface != name:
            alias_map.setdefault(surface, name)
            entities.append(surface)


def build_dynamic_alias_map(entity_type_map: dict):
    alias_map = build_alias_map().copy()
    org_suffixes = ("大学", "学院", "实验室", "研究所", "研究院", "学会", "协会", "海军", "国会", "司法部")
    first_name_candidates = defaultdict(set)
    for canonical, typ in entity_type_map.items():
        name = normalize_text(canonical)
        if not name:
            continue
        alias_map.setdefault(name, canonical)
        if typ == "Book" and name.startswith("《") and name.endswith("》"):
            alias_map.setdefault(name[1:-1], canonical)
        if typ == "Person":
            for sep in ("·", "路", " "):
                if sep in name:
                    first = name.split(sep)[0].strip()
                    tail = name.split(sep)[-1].strip()
                    if 2 <= len(first) <= 4:
                        first_name_candidates[first].add(canonical)
                    if 2 <= len(tail) <= 8:
                        alias_map.setdefault(tail, canonical)
        if typ == "Organization":
            for suffix in org_suffixes:
                pattern = rf"([\u4e00-\u9fffA-Za-z]{{2,12}}{re.escape(suffix)})$"
                m = re.search(pattern, name)
                if m:
                    short = m.group(1)
                    if short != name:
                        alias_map.setdefault(short, canonical)
    for short, canonicals in first_name_candidates.items():
        if len(canonicals) == 1:
            alias_map.setdefault(short, next(iter(canonicals)))
    return alias_map


def apply_alias(name: str, alias_map: dict) -> str:
    return alias_map.get(name, name)


def resolve_entity_type(name: str, entity_type_map: dict, alias_map: dict) -> str:
    direct = entity_type_map.get(name, "")
    if direct:
        return direct
    canonical = alias_map.get(name, name)
    return entity_type_map.get(canonical, "")


def canonicalize_relation_label(relation: str) -> str:
    return RELATION_LABEL_ALIASES.get(relation, relation)


def entity_positions(sentence: str, e1: str, e2: str):
    i = sentence.find(e1)
    j = sentence.find(e2)
    if i == -1 or j == -1:
        return -1, -1
    return i, j


def extract_pair_context(sentence: str, e1: str, e2: str, window: int = 10):
    i, j = entity_positions(sentence, e1, e2)
    if i == -1 or j == -1:
        return sentence, sentence
    if i <= j:
        left_start = max(0, i - window)
        right_end = min(len(sentence), j + len(e2) + window)
        between = sentence[i + len(e1):j]
    else:
        left_start = max(0, j - window)
        right_end = min(len(sentence), i + len(e1) + window)
        between = sentence[j + len(e2):i]
    local = sentence[left_start:right_end]
    return local, between


def choose_relation_for_pair(sentence: str, e1: str, e2: str, relation_rules: dict):
    local_context, between = extract_pair_context(sentence, e1, e2)
    relation_scores = defaultdict(float)
    evidence = defaultdict(list)
    hit_between_map = defaultdict(bool)
    for trigger_word, rel_name in relation_rules.items():
        hit_in_between = trigger_word in between
        hit_in_local = trigger_word in local_context
        if not hit_in_between and not hit_in_local:
            continue
        relation_scores[rel_name] += 2.0 if hit_in_between else 0.75
        evidence[rel_name].append(trigger_word)
        hit_between_map[rel_name] = hit_between_map[rel_name] or hit_in_between
        if len(trigger_word) >= 2:
            relation_scores[rel_name] += 0.25
    if not relation_scores:
        return "", 0.0, [], False
    best_rel = sorted(relation_scores.items(), key=lambda x: (-x[1], x[0]))[0][0]
    return best_rel, relation_scores[best_rel], evidence.get(best_rel, []), hit_between_map.get(best_rel, False)


def template_relation_for_pair(head_type: str, tail_type: str, local_context: str, between: str):
    text = between if between.strip() else local_context
    if {head_type, tail_type} == {"Person", "Location"}:
        if any(w in text for w in ["出生于", "生于", "出生", "生下", "在那里生下"]):
            return "出生于", ["模板:出生"], True
        if "国籍" in text:
            return "国籍", ["模板:国籍"], True
    if {head_type, tail_type} == {"Person", "Organization"}:
        blocked_study_hints = ["客座教授", "奖学金", "Fellow", "成员"]
        if any(w in text for w in ["就读于", "考入", "毕业于", "毕业", "求学于", "入读", "攻读", "在校"]):
            if any(hint in text for hint in blocked_study_hints):
                return "", [], False
            return "就读于", ["模板:就读"], True
        if any(w in text for w in ["任职于", "任职", "工作于", "供职于", "服务于", "加入", "兼职工作", "负责", "副主任", "研究工作"]):
            return "任职于", ["模板:任职"], True
        if any(w in text for w in ["学会", "院士", "当选", "成员", "研究员", "被选为"]):
            return "当选院士", ["模板:院士"], False
    if head_type == tail_type == "Person":
        if any(w in text for w in ["导师", "师从", "指导"]):
            return "师从", ["模板:师从"], True
        if any(w in text for w in ["同事", "合作", "共事", "一起"]):
            return "合作", ["模板:合作"], False
    if {head_type, tail_type} == {"Person", "Event"}:
        if any(w in text for w in ["参与", "参加", "投身", "期间", "战时", "主要参与者"]):
            return "参与", ["模板:参与"], False
    if {"Person", "Machine"} == {head_type, tail_type}:
        if any(w in text for w in ["破解", "破译", "解密", "密码分析", "进行密码分析"]):
            return "参与破解", ["模板:破解"], True
        if any(w in text for w in ["设计", "发明", "制作", "规格"]):
            return "设计", ["模板:设计"], True
        if "改进" in text:
            return "改进", ["模板:改进"], True
        if any(w in text for w in ["开发", "研制", "建造"]):
            return "开发", ["模板:开发"], True
    if {"Person", "Concept"} == {head_type, tail_type}:
        if any(w in text for w in ["被誉为", "称赞"]):
            return "誉为", ["模板:誉为"], False
        if any(w in text for w in ["提出", "叫做"]):
            return "提出", ["模板:提出"], True
        if any(w in text for w in ["设计", "发明"]):
            return "设计", ["模板:设计"], True
        if "证明" in text:
            return "证明", ["模板:证明"], True
        if any(w in text for w in ["获得", "获"]):
            return "获得", ["模板:获得"], True
        if any(w in text for w in ["研究", "探讨", "模型", "测试", "理论"]):
            return "研究", ["模板:研究"], False
    if {"Person", "Book"} == {head_type, tail_type}:
        if any(w in text for w in ["撰写", "写了", "写成", "著有", "著作", "论文", "写过一篇", "名为", "写过"]):
            return "撰写", ["模板:撰写"], True
        if any(w in text for w in ["发表", "发布"]):
            return "发表", ["模板:发表"], True
    if {head_type, tail_type} == {"Organization", "Person"}:
        if any(w in text for w in ["聘请", "招聘"]):
            return "聘请", ["模板:聘请"], True
        if "迫害" in text:
            return "迫害", ["模板:迫害"], True
    if {head_type, tail_type} == {"Organization", "Location"}:
        if any(w in text for w in ["位于", "设于", "坐落于", "隶属"]):
            return "属于", ["模板:属于"], False
    if {head_type, tail_type} == {"Organization", "Machine"}:
        if any(w in text for w in ["使用", "提供", "破译", "破解"]):
            return "参与破解", ["模板:组织破解"], False
    return "", [], False


def predicate_context(sentence: str, e1: str, e2: str, window: int = 14):
    i, j = entity_positions(sentence, e1, e2)
    if i == -1 or j == -1:
        return sentence
    if i <= j:
        start = max(0, i + len(e1) - window)
        end = min(len(sentence), j + len(e2) + window)
    else:
        start = max(0, j + len(e2) - window)
        end = min(len(sentence), i + len(e1) + window)
    return sentence[start:end].strip()


def relation_type_pair_matches(allowed_pairs, head_type: str, tail_type: str) -> bool:
    if not head_type or not tail_type:
        return True
    return (head_type, tail_type) in allowed_pairs or (tail_type, head_type) in allowed_pairs


def extract_open_predicate_relation(sentence: str, e1: str, e2: str, head_type: str, tail_type: str):
    """
    轻量开放式关系抽取：先取实体对附近的局部谓词短语，
    再结合类型约束映射到固定关系模式。
    """
    local_context, between = extract_pair_context(sentence, e1, e2, window=18)
    predicate = between.strip(" ，,。；;：:、")
    search_text = predicate if predicate else local_context
    if len(search_text) > 80:
        return "", 0.0, []
    if any(cue in search_text for cue in NEGATION_CUES) and not any(cue in search_text for cue in ("没有答案", "不可能")):
        return "", 0.0, []

    best = ("", 0.0, [])
    for relation, patterns, allowed_pairs in OPEN_PREDICATE_RELATION_PATTERNS:
        if not relation_type_pair_matches(allowed_pairs, head_type, tail_type):
            continue
        hits = [p for p in patterns if re.search(p, search_text)]
        if not hits:
            continue
        score = 1.15
        if predicate and any(re.search(p, predicate) for p in patterns):
            score += 0.8
        if relation_type_allowed(relation, head_type, tail_type) or relation_type_allowed(relation, tail_type, head_type):
            score += 0.35
        if any(cue in search_text for cue in PASSIVE_CUES):
            score += 0.1
        if score > best[1]:
            best = (relation, score, [f"开放谓词:{hits[0]}"])
    return best


def feature_calibrated_confidence(row, entity_type_map: dict, alias_map: dict = None):
    """
    对每条候选边做类似特征向量分类的置信度校准。
    这里只使用结构和上下文特征，让规则候选与模型候选共用同一套过滤门槛。
    """
    alias_map = alias_map or {}
    head, relation, tail, source, confidence, evidence, sentence = row[:7]
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    head_type = resolve_entity_type(head, entity_type_map, alias_map)
    tail_type = resolve_entity_type(tail, entity_type_map, alias_map)
    if relation_context_contradicts(row, entity_type_map):
        return 0.0, ["特征:上下文反证"]
    if relation != "相关" and not relation_type_allowed(relation, head_type, tail_type):
        return 0.0, ["特征:类型不匹配"]

    local_context, between = extract_pair_context(sentence, head, tail, window=18)
    char_dist = min_char_distance(sentence, head, tail)
    trigger_hits = [w for w, rel in RELATION_TRIGGER_RULES.items() if rel == relation and w in local_context]
    between_hits = [w for w in trigger_hits if w in between]
    features = []
    score = confidence
    if between_hits:
        score += 0.055
        features.append("特征:触发词位于实体间")
    elif trigger_hits:
        score += 0.025
        features.append("特征:局部触发词")
    if char_dist <= 12:
        score += 0.035
        features.append("特征:近距离")
    elif char_dist > max_distance_for_pair(head_type, tail_type):
        score -= 0.12
        features.append("特征:距离偏远")
    if relation_type_allowed(relation, head_type, tail_type):
        score += 0.035
        features.append("特征:类型合法")
    if any(cue in local_context for cue in PASSIVE_CUES):
        features.append("特征:被动/受事提示")
    if any(cue in local_context for cue in NEGATION_CUES) and relation not in {"证明"}:
        score -= 0.12
        features.append("特征:否定提示")
    if str(source).startswith("auto_ml") and not trigger_hits:
        score -= 0.08
        features.append("特征:ML无触发词")
    return round(max(0.0, min(1.0, score)), 3), features


def pair_type_is_plausible(head_type: str, tail_type: str) -> bool:
    if not head_type or not tail_type:
        return True
    return (head_type, tail_type) in CANDIDATE_TYPE_PAIRS or (tail_type, head_type) in CANDIDATE_TYPE_PAIRS


def max_distance_for_pair(head_type: str, tail_type: str) -> int:
    pair = {head_type, tail_type}
    if pair == {"Person"}:
        return 26
    if "Concept" in pair or "Book" in pair:
        return 52
    if "Event" in pair or "Machine" in pair:
        return 60
    if "Organization" in pair:
        return 44
    return 32


def orient_by_relation(head: str, tail: str, relation: str, head_type: str, tail_type: str):
    person_head_relations = {
        "出生于", "国籍", "就读于", "毕业于", "任职于", "师从", "合作", "父亲", "母亲",
        "参与", "参与破解", "提出", "研究", "撰写", "发表", "证明", "获得", "设计",
        "改进", "开发", "当选院士", "誉为",
    }
    if relation in person_head_relations:
        if tail_type == "Person" and head_type != "Person":
            return tail, head, tail_type, head_type
    if relation in {"出生于", "国籍"}:
        if head_type == "Location" and tail_type == "Person":
            return tail, head, tail_type, head_type
    if relation in {"就读于", "毕业于", "任职于", "当选院士"}:
        if head_type == "Organization" and tail_type == "Person":
            return tail, head, tail_type, head_type
    if relation in {"提出", "研究", "证明", "获得", "设计", "改进", "开发", "誉为"}:
        if head_type in {"Concept", "Machine"} and tail_type == "Person":
            return tail, head, tail_type, head_type
    if relation in {"撰写", "发表"}:
        if head_type == "Book" and tail_type == "Person":
            return tail, head, tail_type, head_type
    if relation == "迫害":
        if head_type == "Person" and tail_type in {"Organization", "Location"}:
            return tail, head, tail_type, head_type
    if relation == "属于":
        if head_type == "Location" and tail_type in {"Organization", "Machine"}:
            return tail, head, tail_type, head_type
    return head, tail, head_type, tail_type


def collect_sentence_mentions(sentence: str, alias_map: dict, entity_type_map: dict):
    mentions = []
    seen = set()
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        canonical = alias_map[alias]
        ent_type = resolve_entity_type(alias, entity_type_map, alias_map)
        if not ent_type:
            continue
        start = sentence.find(alias)
        while start != -1:
            key = (start, start + len(alias), canonical, ent_type)
            if key not in seen:
                seen.add(key)
                mentions.append(
                    {
                        "start": start,
                        "end": start + len(alias),
                        "alias": alias,
                        "canonical": canonical,
                        "type": ent_type,
                    }
                )
            start = sentence.find(alias, start + 1)
    mentions.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    return mentions


def nearest_mention(mentions, anchor: int, required_types=None, direction="before", max_gap=36):
    best = None
    best_gap = 10**9
    for mention in mentions:
        if required_types and mention["type"] not in required_types:
            continue
        if direction == "before":
            if mention["end"] > anchor:
                continue
            gap = anchor - mention["end"]
        else:
            if mention["start"] < anchor:
                continue
            gap = mention["start"] - anchor
        if gap > max_gap:
            continue
        if gap < best_gap:
            best = mention
            best_gap = gap
    return best


def add_carry_mentions(mentions, text: str, carry_person: str = "", carry_org: str = "", entity_type_map=None):
    entity_type_map = entity_type_map or {}
    enriched = list(mentions)
    if carry_person:
        for token in ("他", "其", "该数学家"):
            start = text.find(token)
            while start != -1:
                next_char = text[start + len(token):start + len(token) + 1]
                if not (token == "他" and next_char == "们"):
                    enriched.append(
                        {
                            "start": start,
                            "end": start + len(token),
                            "alias": token,
                            "canonical": carry_person,
                            "type": entity_type_map.get(carry_person, "Person"),
                        }
                    )
                start = text.find(token, start + len(token))
    if carry_org and text.startswith(("该校", "该机构", "学院")):
        enriched.insert(
            0,
            {
                "start": 0,
                "end": 2,
                "alias": text[:2],
                "canonical": carry_org,
                "type": entity_type_map.get(carry_org, "Organization"),
            },
        )
    enriched.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    return enriched


def extract_template_relations_from_sentence(sentence: str, alias_map: dict, entity_type_map: dict, carry_person: str = "", carry_org: str = ""):
    mentions = collect_sentence_mentions(sentence, alias_map, entity_type_map)
    mentions = add_carry_mentions(mentions, sentence, carry_person, carry_org, entity_type_map)
    triples = []
    templates = [
        {"relation": "就读于", "triggers": ["考入", "就读于", "攻读", "入读"], "head_types": {"Person"}, "tail_types": {"Organization"}, "tail_after": True, "max_gap": 40},
        {"relation": "毕业于", "triggers": ["毕业于", "毕业", "获博士学位"], "head_types": {"Person"}, "tail_types": {"Organization"}, "tail_after": True, "max_gap": 40},
        {"relation": "任职于", "triggers": ["任职", "工作于", "供职于", "服务于", "兼职工作", "负责", "副主任", "加入"], "head_types": {"Person"}, "tail_types": {"Organization"}, "tail_after": False, "max_gap": 40},
        {"relation": "当选院士", "triggers": ["被选为", "当选", "成员"], "head_types": {"Person"}, "tail_types": {"Organization"}, "tail_after": True, "max_gap": 36},
        {"relation": "撰写", "triggers": ["写过", "撰写", "名为", "著有"], "head_types": {"Person"}, "tail_types": {"Book"}, "tail_after": True, "max_gap": 48},
        {"relation": "发表", "triggers": ["发表", "发布"], "head_types": {"Person"}, "tail_types": {"Book", "Concept"}, "tail_after": True, "max_gap": 52},
        {"relation": "提出", "triggers": ["提出", "叫做"], "head_types": {"Person"}, "tail_types": {"Concept", "Machine"}, "tail_after": True, "max_gap": 48},
        {"relation": "证明", "triggers": ["证明"], "head_types": {"Person"}, "tail_types": {"Concept"}, "tail_after": True, "max_gap": 48},
        {"relation": "获得", "triggers": ["获得", "获"], "head_types": {"Person"}, "tail_types": {"Concept"}, "tail_after": True, "max_gap": 44},
        {"relation": "设计", "triggers": ["设计", "发明"], "head_types": {"Person", "Organization"}, "tail_types": {"Machine", "Concept"}, "tail_after": True, "max_gap": 56},
        {"relation": "开发", "triggers": ["开发", "研制", "制作", "建造"], "head_types": {"Person", "Organization"}, "tail_types": {"Machine", "Concept"}, "tail_after": True, "max_gap": 56},
        {"relation": "改进", "triggers": ["改进"], "head_types": {"Person", "Organization"}, "tail_types": {"Machine"}, "tail_after": True, "max_gap": 56},
        {"relation": "研究", "triggers": ["研究", "研究工作"], "head_types": {"Person"}, "tail_types": {"Concept", "Machine"}, "tail_after": True, "max_gap": 48},
        {"relation": "参与破解", "triggers": ["破解", "破译", "解密", "密码分析"], "head_types": {"Person", "Organization"}, "tail_types": {"Machine"}, "tail_after": True, "max_gap": 48},
        {"relation": "聘请", "triggers": ["聘请", "招聘"], "head_types": {"Person", "Organization"}, "tail_types": {"Person"}, "tail_after": True, "max_gap": 42},
        {"relation": "迫害", "triggers": ["迫害"], "head_types": {"Organization", "Location"}, "tail_types": {"Person"}, "tail_after": False, "max_gap": 42},
        {"relation": "誉为", "triggers": ["被誉为", "称赞"], "head_types": {"Person"}, "tail_types": {"Concept"}, "tail_after": True, "max_gap": 140},
        {"relation": "父亲", "triggers": ["父亲"], "head_types": {"Person"}, "tail_types": {"Person"}, "tail_after": True, "max_gap": 32},
        {"relation": "母亲", "triggers": ["母亲"], "head_types": {"Person"}, "tail_types": {"Person"}, "tail_after": True, "max_gap": 32},
    ]

    for spec in templates:
        for trigger in spec["triggers"]:
            start = sentence.find(trigger)
            if start == -1:
                continue
            end = start + len(trigger)
            head = nearest_mention(mentions, start, spec["head_types"], "before", spec["max_gap"])
            tail_dir = "after" if spec["tail_after"] else "before"
            tail = nearest_mention(mentions, end if spec["tail_after"] else start, spec["tail_types"], tail_dir, spec["max_gap"])
            if not tail and spec["relation"] in {"就读于", "毕业于"} and carry_org:
                tail = {"canonical": carry_org, "type": entity_type_map.get(carry_org, "Organization")}
            if not head or not tail or head["canonical"] == tail["canonical"]:
                continue
            blocked_hints = ("客座教授", "奖学金", "Fellow")
            if spec["relation"] in {"就读于", "毕业于"} and any(hint in sentence for hint in blocked_hints):
                continue
            if spec["relation"] in {"就读于", "毕业于"} and not any(token in tail["canonical"] for token in ("大学", "学院", "学校")):
                continue
            row = [head["canonical"], spec["relation"], tail["canonical"], "auto_rule", 0.86, f"模板:{spec['relation']}", sentence, "否"]
            if relation_context_contradicts(row, entity_type_map):
                continue
            triples.append(row)

    birth_anchor = -1
    for token in ("在那里生下", "生下", "出生于", "生于", "出生"):
        birth_anchor = sentence.find(token)
        if birth_anchor != -1:
            person = nearest_mention(mentions, birth_anchor, {"Person"}, "after", 18) or nearest_mention(mentions, birth_anchor, {"Person"}, "before", 18)
            location = nearest_mention(mentions, birth_anchor, {"Location"}, "before", 36)
            if person and location:
                triples.append([person["canonical"], "出生于", location["canonical"], "auto_rule", 0.88, "模板:出生于", sentence, "否"])
            break

    if "招聘" in sentence:
        anchor = sentence.find("招聘")
        person = nearest_mention(mentions, anchor, {"Person"}, "before", 24)
        organization = nearest_mention(mentions, anchor, {"Organization"}, "before", 24)
        if person and organization:
            triples.append([organization["canonical"], "聘请", person["canonical"], "auto_rule", 0.84, "模板:聘请", sentence, "否"])

    if "学习" in sentence:
        anchor = sentence.find("学习")
        local_after = sentence[anchor:anchor + 24]
        if any(hint in local_after for hint in ("客座教授", "奖学金", "Fellow")):
            anchor = -1
        if anchor != -1:
            person = nearest_mention(mentions, anchor, {"Person"}, "before", 30)
            organization = nearest_mention(mentions, anchor, {"Organization"}, "before", 24)
            if person and organization and "大学" in organization["canonical"]:
                triples.append([person["canonical"], "就读于", organization["canonical"], "auto_rule", 0.82, "模板:学习", sentence, "否"])

    if "毕业" in sentence:
        anchor = sentence.find("毕业")
        person = nearest_mention(mentions, anchor, {"Person"}, "before", 24) or nearest_mention(mentions, anchor, {"Person"}, "after", 18)
        organization = nearest_mention(mentions, anchor, {"Organization"}, "before", 32) or nearest_mention(mentions, anchor, {"Organization"}, "after", 32)
        if not organization and carry_org:
            organization = {"canonical": carry_org, "type": entity_type_map.get(carry_org, "Organization")}
        if person and organization and not any(hint in sentence for hint in ("客座教授", "奖学金", "Fellow")):
            triples.append([person["canonical"], "毕业于", organization["canonical"], "auto_rule", 0.86, "模板:毕业于", sentence, "否"])

    if "父亲" in sentence:
        anchor = sentence.find("父亲")
        child = nearest_mention(mentions, anchor, {"Person"}, "before", 24)
        parent = nearest_mention(mentions, anchor + 2, {"Person"}, "after", 28)
        if child and parent and child["canonical"] != parent["canonical"]:
            triples.append([child["canonical"], "父亲", parent["canonical"], "auto_rule", 0.88, "模板:父亲", sentence, "否"])

    if "母亲" in sentence:
        anchor = sentence.find("母亲")
        child = nearest_mention(mentions, anchor, {"Person"}, "before", 24)
        parent = nearest_mention(mentions, anchor + 2, {"Person"}, "after", 28)
        if child and parent and child["canonical"] != parent["canonical"]:
            triples.append([child["canonical"], "母亲", parent["canonical"], "auto_rule", 0.88, "模板:母亲", sentence, "否"])

    if "与" in sentence and "一起" in sentence:
        if "说法" in sentence or "谈到" in sentence:
            return triples
        with_anchor = sentence.find("与")
        together_anchor = sentence.find("一起", with_anchor)
        left_person = nearest_mention(mentions, with_anchor, {"Person"}, "before", 24)
        partner = None
        for mention in mentions:
            if mention["type"] != "Person":
                continue
            if mention["start"] >= with_anchor and mention["end"] <= together_anchor:
                partner = mention
                break
        if left_person and partner and left_person["canonical"] != partner["canonical"]:
            triples.append([left_person["canonical"], "合作", partner["canonical"], "auto_rule", 0.82, "模板:合作", sentence, "否"])
    return triples


def split_line_into_segments(line: str):
    return [seg.strip(" ，,；;:：") for seg in re.split(r"[。！？；;]", line) if seg.strip(" ，,；;:：")]


def extract_bound_relations(segment: str, alias_map: dict, entity_type_map: dict, carry_person: str = "", carry_org: str = ""):
    mentions = collect_sentence_mentions(segment, alias_map, entity_type_map)
    mentions = add_carry_mentions(mentions, segment, carry_person, carry_org, entity_type_map)

    triples = []
    trigger_specs = [
        ("考入", "就读于", {"Person"}, {"Organization"}, "before", "after", 28, 28, 0.9),
        ("攻读", "就读于", {"Person"}, {"Organization"}, "before", "before", 28, 18, 0.86),
        ("毕业于", "就读于", {"Person"}, {"Organization"}, "before", "after", 28, 28, 0.88),
        ("毕业", "毕业于", {"Person"}, {"Organization"}, "before", "after", 28, 28, 0.88),
        ("获博士学位", "毕业于", {"Person"}, {"Organization"}, "before", "before", 28, 36, 0.9),
        ("负责", "任职于", {"Person"}, {"Organization"}, "before", "before", 24, 18, 0.84),
        ("被选为", "当选院士", {"Person"}, {"Organization"}, "before", "after", 24, 28, 0.9),
        ("当选", "当选院士", {"Person"}, {"Organization"}, "before", "after", 24, 28, 0.86),
        ("写过", "撰写", {"Person"}, {"Book"}, "before", "after", 28, 48, 0.9),
        ("撰写", "撰写", {"Person"}, {"Book"}, "before", "after", 28, 48, 0.9),
        ("发表", "发表", {"Person"}, {"Book", "Concept"}, "before", "after", 28, 52, 0.88),
        ("发布", "发表", {"Person", "Organization"}, {"Book", "Concept"}, "before", "after", 28, 52, 0.82),
        ("提出", "提出", {"Person"}, {"Concept", "Machine"}, "before", "after", 24, 48, 0.9),
        ("证明", "证明", {"Person"}, {"Concept"}, "before", "after", 24, 48, 0.86),
        ("获得", "获得", {"Person"}, {"Concept"}, "before", "after", 24, 44, 0.84),
        ("获", "获得", {"Person"}, {"Concept"}, "before", "after", 24, 44, 0.82),
        ("设计", "设计", {"Person", "Organization"}, {"Machine", "Concept"}, "before", "after", 32, 56, 0.88),
        ("发明", "设计", {"Person", "Organization"}, {"Machine", "Concept"}, "before", "after", 32, 56, 0.84),
        ("改进", "改进", {"Person", "Organization"}, {"Machine"}, "before", "after", 36, 56, 0.86),
        ("开发", "开发", {"Person", "Organization"}, {"Machine", "Concept"}, "before", "after", 36, 56, 0.84),
        ("研制", "开发", {"Person", "Organization"}, {"Machine", "Concept"}, "before", "after", 36, 56, 0.84),
        ("制作", "开发", {"Person", "Organization"}, {"Machine", "Concept"}, "before", "after", 36, 56, 0.84),
        ("研究", "研究", {"Person"}, {"Concept", "Machine"}, "before", "after", 24, 48, 0.84),
        ("研究工作", "研究", {"Person"}, {"Concept", "Machine"}, "before", "before", 24, 24, 0.84),
        ("破解", "参与破解", {"Person", "Organization"}, {"Machine"}, "before", "after", 32, 48, 0.84),
        ("破译", "参与破解", {"Person", "Organization"}, {"Machine"}, "before", "after", 32, 48, 0.84),
        ("解密", "参与破解", {"Person", "Organization"}, {"Machine"}, "before", "after", 32, 48, 0.84),
        ("聘请", "聘请", {"Person", "Organization"}, {"Person"}, "before", "after", 32, 42, 0.84),
        ("招聘", "聘请", {"Organization"}, {"Person"}, "before", "before", 24, 24, 0.8),
        ("迫害", "迫害", {"Organization", "Location"}, {"Person"}, "before", "before", 36, 24, 0.84),
        ("被誉为", "誉为", {"Person"}, {"Concept"}, "before", "after", 18, 54, 0.86),
        ("称赞", "誉为", {"Person", "Organization"}, {"Person", "Concept"}, "before", "after", 36, 54, 0.78),
        ("父亲", "父亲", {"Person"}, {"Person"}, "before", "after", 20, 28, 0.88),
        ("母亲", "母亲", {"Person"}, {"Person"}, "before", "after", 20, 28, 0.88),
    ]

    for trigger, relation, head_types, tail_types, head_dir, tail_dir, head_gap, tail_gap, confidence in trigger_specs:
        start = segment.find(trigger)
        while start != -1:
            head_anchor = start if head_dir == "before" else start + len(trigger)
            tail_anchor = start if tail_dir == "before" else start + len(trigger)
            head = nearest_mention(mentions, head_anchor, head_types, head_dir, head_gap)
            tail = nearest_mention(mentions, tail_anchor, tail_types, tail_dir, tail_gap)
            if not tail and relation in {"就读于", "毕业于"} and carry_org:
                tail = {"canonical": carry_org, "type": entity_type_map.get(carry_org, "Organization")}
            if relation in {"就读于", "毕业于"} and tail and not any(token in tail["canonical"] for token in ("大学", "学院", "学校")):
                start = segment.find(trigger, start + len(trigger))
                continue
            if head and tail and head["canonical"] != tail["canonical"]:
                row = [head["canonical"], relation, tail["canonical"], "auto_rule", confidence, f"绑定:{relation}", segment, "否"]
                if not relation_context_contradicts(row, entity_type_map):
                    triples.append(row)
            start = segment.find(trigger, start + len(trigger))
    return triples


def print_relation_catalog():
    print("关系类型清单：")
    for rel, desc in RELATION_CATALOG.items():
        print(f"  - {rel}: {desc}")
    print("关系触发词表：")
    grouped = defaultdict(list)
    for trigger, rel in RELATION_TRIGGER_RULES.items():
        grouped[rel].append(trigger)
    for rel in RELATION_CATALOG:
        triggers = grouped.get(rel)
        if triggers:
            print(f"  - {rel}: {'、'.join(triggers)}")


def load_relation_models(bin_model_path="relation_bin_clf.model", multi_model_path="relation_multi_clf.model"):
    if joblib is None:
        return None, None
    try:
        bin_model = joblib.load(bin_model_path)
        multi_model = joblib.load(multi_model_path)
        return bin_model, multi_model
    except Exception:
        return None, None


def build_relation_feature_text(sentence, e1, e2, entity_type_map, alias_map=None):
    alias_map = alias_map or {}
    ht = resolve_entity_type(e1, entity_type_map, alias_map) or "UNK"
    tt = resolve_entity_type(e2, entity_type_map, alias_map) or "UNK"
    dist = abs(sentence.find(e1) - sentence.find(e2)) if (e1 in sentence and e2 in sentence) else 999
    local_context, between = extract_pair_context(sentence, e1, e2)
    trigger_words = sorted({w for w in RELATION_TRIGGER_RULES if w in local_context})
    trigger = int(bool(trigger_words))
    trigger_text = "|".join(trigger_words[:6]) if trigger_words else "NONE"
    between_flag = int(bool(between.strip()))
    between_trigger_words = sorted({w for w in RELATION_TRIGGER_RULES if w in between})
    pair_ok = int(pair_type_is_plausible(ht, tt))
    neg = int(any(cue in local_context for cue in NEGATION_CUES))
    passive = int(any(cue in local_context for cue in PASSIVE_CUES))
    order = "e1_before_e2" if sentence.find(e1) <= sentence.find(e2) else "e2_before_e1"
    predicate = re.sub(r"\s+", "", between.strip(" ，,。；;：:、"))[:24] or "NONE"
    return (
        f"{e1} [SEP] {sentence} [SEP] {e2} [SEP] {ht}>{tt} "
        f"[SEP] dist={dist} [SEP] trig={trigger} [SEP] between={between_flag} "
        f"[SEP] trigwords={trigger_text} [SEP] between_trig={'|'.join(between_trigger_words[:6]) or 'NONE'} "
        f"[SEP] pair_ok={pair_ok} [SEP] neg={neg} [SEP] passive={passive} [SEP] order={order} "
        f"[SEP] predicate={predicate}"
    )


def relation_ml_predict_with_model(bin_model, multi_model, sentence, e1, e2, entity_type_map, alias_map=None):
    if bin_model is None or multi_model is None:
        return "", 0.0
    feature_text = build_relation_feature_text(sentence, e1, e2, entity_type_map, alias_map)
    try:
        # 第一阶段：判断是否有关系
        bin_probs = bin_model.predict_proba([feature_text])[0]
        rel_prob = float(bin_probs[1])  # 1 表示“有关系”
        if rel_prob < 0.45:
            return "", rel_prob

        # 第二阶段：判断关系类型
        multi_probs = multi_model.predict_proba([feature_text])[0]
        multi_classes = list(multi_model.classes_)
        best_idx = max(range(len(multi_probs)), key=lambda i: multi_probs[i])
        best_rel = multi_classes[best_idx]
        best_prob = float(multi_probs[best_idx])

        # 综合置信度：关系存在与类型概率加权平均（比乘法更稳）
        final_prob = round(0.6 * rel_prob + 0.4 * best_prob, 4)
        return best_rel, final_prob
    except Exception:
        return "", 0.0


def load_entity_type_map(path="core_entities.csv"):
    entity_types = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                entity_types[row[0].strip()] = row[1].strip()
    return entity_types


def relation_type_allowed(relation, head_type, tail_type):
    """
    轻量类型约束，减少明显错误边。
    """
    if not head_type or not tail_type:
        return True
    allowed = {
        "出生于": {("Person", "Location")},
        "国籍": {("Person", "Location")},
        "就读于": {("Person", "Organization")},
        "毕业于": {("Person", "Organization")},
        "师从": {("Person", "Person")},
        "任职于": {("Person", "Organization")},
        "合作": {("Person", "Person")},
        "父亲": {("Person", "Person")},
        "母亲": {("Person", "Person")},
        "参与": {("Person", "Event"), ("Organization", "Event")},
        "参与破解": {("Person", "Machine"), ("Organization", "Machine")},
        "提出": {("Person", "Concept"), ("Person", "Machine")},
        "发表": {("Person", "Book"), ("Person", "Concept"), ("Organization", "Book"), ("Organization", "Concept")},
        "证明": {("Person", "Concept")},
        "获得": {("Person", "Concept")},
        "设计": {("Person", "Machine"), ("Person", "Concept"), ("Organization", "Machine"), ("Organization", "Concept")},
        "改进": {("Person", "Machine"), ("Organization", "Machine")},
        "开发": {("Person", "Machine"), ("Person", "Concept"), ("Organization", "Machine"), ("Organization", "Concept")},
        "聘请": {("Person", "Person"), ("Organization", "Person")},
        "迫害": {("Organization", "Person"), ("Location", "Person")},
        "誉为": {("Person", "Concept"), ("Organization", "Person"), ("Book", "Person")},
        "当选院士": {("Person", "Organization")},
        "属于": {("Organization", "Location"), ("Machine", "Location"), ("Organization", "Organization")},
        "设立": {("Organization", "Concept")},
        "研究": {("Person", "Concept"), ("Person", "Machine")},
        "撰写": {("Person", "Book")},
    }
    if relation not in allowed:
        return True
    return (head_type, tail_type) in allowed[relation]


def min_char_distance(sentence, e1, e2):
    i = sentence.find(e1)
    j = sentence.find(e2)
    if i == -1 or j == -1:
        return 10**9
    if i <= j:
        return max(0, j - (i + len(e1)))
    return max(0, i - (j + len(e2)))


def relation_context_contradicts(row, entity_type_map: dict) -> bool:
    head, relation, tail = row[:3]
    sentence = row[6] if len(row) > 6 else ""
    trigger_text = str(row[5]) if len(row) > 5 else ""
    directional_tail_after = {"提出", "设计", "开发", "发表", "证明", "获得"}

    if relation in {"发表", "发布"} and any(hint in sentence for hint in ("没有发表", "未发表", "尚未发表")):
        return True
    if relation == "证明" and any(hint in sentence for hint in ("事实证明", "这证明", "表明")):
        return True

    trigger_positions = [sentence.find(token) for token in RELATION_TRIGGER_RULES if RELATION_TRIGGER_RULES[token] == relation and token in sentence]
    trigger_positions.extend(sentence.find(token) for token in re.split(r"[|:：]", trigger_text) if token and token in sentence)
    trigger_positions = [pos for pos in trigger_positions if pos >= 0]
    trigger_pos = min(trigger_positions) if trigger_positions else -1
    tail_pos = sentence.find(tail)
    head_pos = sentence.find(head)
    try:
        confidence = float(row[4])
    except (TypeError, ValueError):
        confidence = 0.0

    if tail_pos < 0 and relation != "相关" and confidence < 0.75:
        return True

    if relation in directional_tail_after and trigger_pos >= 0 and tail_pos >= 0 and tail_pos < trigger_pos:
        return True

    if relation == "任职于" and tail_pos >= 0:
        tail_context = sentence[tail_pos:tail_pos + len(tail) + 12]
        before_tail = sentence[max(0, tail_pos - 4):tail_pos]
        if any(hint in tail_context for hint in ("监督下", "监管下", "指导下", "管理下", "主持下")):
            return True
        if any(marker in before_tail for marker in ("被", "由")) and re.search(rf"{re.escape(tail)}.{{0,8}}(?:招聘|聘请|招募)", sentence[tail_pos:]):
            return True

    if relation == "聘请" and head_pos >= 0:
        hire_positions = [sentence.find(token) for token in ("聘请", "招聘", "招募") if token in sentence]
        hire_pos = min(hire_positions) if hire_positions else -1
        head_context = sentence[head_pos:head_pos + len(head) + 12]
        if hire_pos >= 0 and head_pos > hire_pos:
            return True
        if any(hint in head_context for hint in ("监督下", "监管下", "指导下", "管理下", "主持下")):
            return True

    if relation in {"提出", "设计", "开发"} and trigger_pos >= 0 and tail_pos >= 0:
        between = sentence[trigger_pos:tail_pos] if trigger_pos <= tail_pos else sentence[tail_pos:trigger_pos]
        if any(marker in between for marker in ("为", "使", "根据", "通过", "因为")) and not any(marker in between for marker in ("叫做", "称为", "名为")):
            return True
        if relation in {"设计", "开发"} and any(marker in between for marker in ("包括改进", "对", "的改进")):
            return True
        if relation == "开发" and "研制的" in between:
            return True
        if relation == "开发" and re.search(r"研制的.{0,6}" + re.escape(tail), sentence):
            return True

    if relation in {"设计", "开发", "提出", "研究"} and trigger_pos >= 0:
        left_context = sentence[max(0, trigger_pos - 24):trigger_pos]
        if "根据" in left_context and any(hint in left_context for hint in ("理论", "方法", "论文", "著作")):
            return True

    if relation in {"设计", "开发"} and tail_pos >= 0:
        tail_context = sentence[max(0, tail_pos - 6):tail_pos + len(tail) + 8]
        if re.search(rf"对.{{0,8}}{re.escape(tail)}.{{0,4}}的改进", tail_context):
            return True

    if relation == "参与破解" and tail_pos >= 0:
        local = sentence[max(0, tail_pos - 12):tail_pos + len(tail) + 12]
        tail_type = entity_type_map.get(tail, "")
        span = sentence[min(trigger_pos, tail_pos):max(trigger_pos, tail_pos) + len(tail)] if trigger_pos >= 0 else local
        lead_span = sentence[max(0, trigger_pos - 4):tail_pos + len(tail)] if trigger_pos >= 0 and tail_pos >= 0 else local
        if tail_type == "Machine" and ("加速破译" in local or "加速破译" in span or "加速破译" in lead_span or ("加速破译" in sentence and sentence.find("加速破译") < tail_pos)):
            return True

    if relation == "当选院士" and not any(hint in sentence for hint in ("院士", "学会", "FRS", "会士", "成员")):
        return True
    if relation == "研究" and "研究组根据" in sentence:
        return True
    if relation == "迫害":
        action_positions = [sentence.find(token) for token in ("迫害", "起诉", "处罚", "定罪") if token in sentence]
        action_pos = min(action_positions) if action_positions else -1
        if action_pos >= 0 and head_pos >= 0:
            if head_pos > action_pos or action_pos - (head_pos + len(head)) > 24:
                return True
        if any(media_word in head for media_word in ("报", "杂志", "期刊", "电视台", "出版社")):
            return True

    if head_pos >= 0 and tail_pos >= 0 and abs(head_pos - tail_pos) > 140 and relation not in {"相关"}:
        return True

    return False


def organization_parent_child(child: str, parent: str, entity_type_map: dict) -> bool:
    if child == parent:
        return False
    if entity_type_map.get(child) != "Organization" or entity_type_map.get(parent) != "Organization":
        return False
    if len(child) <= len(parent):
        return False
    return child.startswith(parent) or (parent.endswith("大学") and child.startswith(parent))


def normalize_organization_hierarchy(triples, entity_type_map):
    """
    对人物-组织事实优先保留更具体的组织，
    同时补充“子组织 -> 属于 -> 父组织”的层级关系。
    """
    grouped = defaultdict(list)
    for row in triples:
        head, relation, tail = row[:3]
        if relation in {"就读于", "毕业于", "任职于", "当选院士"} and entity_type_map.get(tail) == "Organization":
            grouped[(head, relation)].append(row)

    drop_keys = set()
    hierarchy_rows = {}
    for rows in grouped.values():
        for short_row in rows:
            short_org = short_row[2]
            for long_row in rows:
                long_org = long_row[2]
                if short_org == long_org:
                    continue
                if len(long_org) > len(short_org) and short_org in long_org:
                    drop_keys.add((short_row[0], short_row[1], short_row[2]))
        for child_row in rows:
            child_org = child_row[2]
            for parent_row in rows:
                parent_org = parent_row[2]
                if not organization_parent_child(child_org, parent_org, entity_type_map):
                    continue
                drop_keys.add((parent_row[0], parent_row[1], parent_row[2]))
                evidence_sentence = child_row[6] if len(child_row) > 6 else ""
                hierarchy_key = (child_org, "属于", parent_org)
                hierarchy_rows[hierarchy_key] = [
                    child_org,
                    "属于",
                    parent_org,
                    "auto_rule",
                    0.86,
                    "层级归一",
                    evidence_sentence,
                    "否",
                ]

    normalized = [row for row in triples if (row[0], row[1], row[2]) not in drop_keys]
    existing_keys = {(row[0], row[1], row[2]) for row in normalized}
    for key, row in hierarchy_rows.items():
        if key not in existing_keys:
            normalized.append(row)
            existing_keys.add(key)
    return normalized


def aggregate_relation_evidence(triples, entity_type_map, alias_map=None):
    """
    多示例证据聚合：当同一三元组被多个句子或多个抽取器支持时，
    保留最强证据，并适度提高置信度。
    """
    alias_map = alias_map or {}
    grouped = defaultdict(list)
    source_rank = {"auto_rule": 4, "auto_open_ie": 3, "auto_feature_ml": 2, "auto_ml": 2, "auto_cooccur": 0}
    for row in triples:
        calibrated, feature_notes = feature_calibrated_confidence(row, entity_type_map, alias_map)
        if calibrated <= 0:
            continue
        new_row = list(row)
        new_row[4] = calibrated
        if feature_notes:
            new_row[5] = f"{new_row[5]}|{'|'.join(feature_notes)}"
        grouped[(new_row[0], new_row[1], new_row[2])].append(new_row)

    aggregated = []
    for key, rows in grouped.items():
        best = max(rows, key=lambda r: (float(r[4]), source_rank.get(r[3], 0), len(str(r[5]))))
        evidence_count = len({r[6] for r in rows})
        source_count = len({r[3] for r in rows})
        support_bonus = min(0.10, 0.035 * max(0, evidence_count - 1) + 0.02 * max(0, source_count - 1))
        best = list(best)
        best[4] = round(min(1.0, float(best[4]) + support_bonus), 3)
        evidence_parts = []
        for part in str(best[5]).split("|"):
            part = part.strip()
            if part and part not in evidence_parts:
                evidence_parts.append(part)
        best[5] = "|".join(evidence_parts)
        if evidence_count > 1:
            best[5] = f"{best[5]}|多证据:{evidence_count}"
        if best[4] >= 0.74 and best[7] == "是":
            best[7] = "否"
        aggregated.append(best)
    return aggregated


def extract_triples():
    print("正在加载核心实体字典...")
    print_relation_catalog()
    # 1. 读取实体词典
    entities = []
    with open('core_entities_auto.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader) # 跳过表头
        for row in reader:
            if row:
                entities.append(row[0]) # 只取第一列的实体名称
                
    print(f"成功加载 {len(entities)} 个核心实体。")
    entity_type_map = load_entity_type_map("core_entities_auto.csv")
    alias_map = build_dynamic_alias_map(entity_type_map)
    # 外部别名词典里的简称不在实体表里时也要能命中，否则共现会偏少。
    for short in alias_map:
        if short not in entities:
            entities.append(short)
    # 长实体优先，减少短串误配顺序问题
    entities = sorted(set([normalize_text(e) for e in entities if e.strip()]), key=len, reverse=True)

    # 2. 读取纯文本语料
    print("正在加载语料...")
    with open('turing_corpus_clean.txt', 'r', encoding='utf-8') as f:
        text = f.read()
    register_mined_entities(text, entity_type_map, alias_map, entities)
    # 注册通用候选实体后再次归一排序，保证新增长词优先命中。
    entities = sorted(set([normalize_text(e) for e in entities if e.strip()]), key=len, reverse=True)

    # 3. 将整篇文章按句号、感叹号、问号切分成单句
    sentences = [line.strip() for line in text.splitlines() if line.strip()]
    
    # 4. 定义关系触发词典
    relation_rules = RELATION_TRIGGER_RULES

    triples = []
    relation_stats = defaultdict(int)
    print("正在逐句扫描并抽取实体关系...")
    bin_model, multi_model = load_relation_models("relation_bin_clf.model", "relation_multi_clf.model")
    carry_person = ""
    carry_org = ""
    
    # 5. 遍历每一行，并按分句处理
    for line in sentences:
        line = line.strip()
        if not line:
            continue
        if line.startswith("===") and line.endswith("==="):
            continue

        for sentence in split_line_into_segments(line):
            if not sentence:
                continue

            triples.extend(extract_template_relations_from_sentence(sentence, alias_map, entity_type_map, carry_person, carry_org))
            triples.extend(extract_bound_relations(sentence, alias_map, entity_type_map, carry_person, carry_org))

            # 句中出现的核心实体
            found_entities = [ent for ent in entities if ent in sentence]
            sentence_mentions = collect_sentence_mentions(sentence, alias_map, entity_type_map)
            sentence_persons = [m["canonical"] for m in sentence_mentions if m["type"] == "Person"]
            sentence_orgs = [m["canonical"] for m in sentence_mentions if m["type"] == "Organization"]
            if sentence_persons:
                carry_person = sentence_persons[0]
            if sentence_orgs and any(trigger in sentence for trigger in ("考入", "攻读", "就读", "学习", "毕业", "负责", "副主任", "任职", "工作")):
                carry_org = sentence_orgs[0]

            # 如果一句话里至少有两个实体，就有可能存在关系
            if len(found_entities) < 2:
                continue
            # 将句子里的实体两两配对组合
            pairs = list(itertools.combinations(found_entities, 2))
            
            for entity1, entity2 in pairs:
                # 候选对过滤：字符距离过大通常不是直接关系
                char_dist = min_char_distance(sentence, entity1, entity2)
                entity1_type = resolve_entity_type(entity1, entity_type_map, alias_map)
                entity2_type = resolve_entity_type(entity2, entity_type_map, alias_map)
                if not pair_type_is_plausible(entity1_type, entity2_type):
                    continue
                if char_dist > max_distance_for_pair(entity1_type, entity2_type):
                    continue

                local_context, between = extract_pair_context(sentence, entity1, entity2)
                # 阶段1 规则判定
                relation, score, trigger_words, trigger_between = choose_relation_for_pair(sentence, entity1, entity2, relation_rules)
                tpl_relation, tpl_triggers, tpl_between = template_relation_for_pair(entity1_type, entity2_type, local_context, between)
                if tpl_relation:
                    if not relation or score < 2.5:
                        relation = tpl_relation
                        score = max(score, 3.2 if tpl_between else 2.2)
                        trigger_words = tpl_triggers
                        trigger_between = tpl_between
                open_relation, open_score, open_triggers = extract_open_predicate_relation(sentence, entity1, entity2, entity1_type, entity2_type)
                if open_relation and (not relation or open_score > score):
                    relation = open_relation
                    score = open_score
                    trigger_words = open_triggers
                    trigger_between = True
                # 阶段2 传统分类器补充（可选）
                ml_relation_12, ml_prob_12 = relation_ml_predict_with_model(bin_model, multi_model, sentence, entity1, entity2, entity_type_map, alias_map)
                ml_relation_21, ml_prob_21 = relation_ml_predict_with_model(bin_model, multi_model, sentence, entity2, entity1, entity_type_map, alias_map)
                if ml_prob_21 > ml_prob_12:
                    ml_relation, ml_prob = canonicalize_relation_label(ml_relation_21), ml_prob_21
                    ml_swapped = True
                else:
                    ml_relation, ml_prob = canonicalize_relation_label(ml_relation_12), ml_prob_12
                    ml_swapped = False

                if relation:
                    relation = canonicalize_relation_label(relation)
                    if relation in {"父亲", "母亲"}:
                        continue
                    if relation in STRICT_BETWEEN_RELATIONS and not trigger_between and char_dist > 14:
                        relation = ""
                    elif relation in {"出生于", "国籍"} and {entity1_type, entity2_type} != {"Person", "Location"}:
                        relation = ""
                    elif relation in {"就读于", "毕业于", "任职于", "当选院士"} and {entity1_type, entity2_type} != {"Person", "Organization"}:
                        relation = ""
                    elif relation in {"就读于", "毕业于"} and entity1_type == "Organization" and entity2_type == "Person":
                        if any(hint in sentence for hint in ("客座教授", "奖学金", "Fellow")):
                            relation = ""
                if relation:
                    source = "auto_rule"
                    confidence = round(min(1.0, 0.42 + 0.16 * score), 3)
                    review_flag = "是" if confidence < 0.7 else "否"
                    evidence_triggers = "|".join(trigger_words)
                elif ml_relation and ml_prob >= 0.18:
                    relation = ml_relation
                    source = "auto_feature_ml"
                    confidence = round(ml_prob, 3)
                    review_flag = "是" if confidence < 0.52 else "否"
                    evidence_triggers = "(ML预测)"
                else:
                    continue

                # 统一实体别名
                e1_clean = apply_alias(entity1, alias_map)
                e2_clean = apply_alias(entity2, alias_map)
                if e1_clean == e2_clean:
                    continue

                head, tail = e1_clean, e2_clean

                # 机器学习模型若判断反向更好，调整方向
                if source == "auto_ml" and ml_swapped:
                    head, tail = tail, head

                # 类型约束校验，不满足则降级为“相关”
                head_type = entity_type_map.get(head, "")
                tail_type = entity_type_map.get(tail, "")
                head, tail, head_type, tail_type = orient_by_relation(head, tail, relation, head_type, tail_type)
                if head == tail:
                    continue
                if relation == "合作":
                    coop_dist = min_char_distance(sentence, entity1, entity2)
                    if coop_dist > 18 and "一起" not in sentence:
                        continue
                if relation in {"就读于", "毕业于"} and any(hint in sentence for hint in ("客座教授", "奖学金", "Fellow")):
                    continue
                if relation != "相关" and not relation_type_allowed(relation, head_type, tail_type):
                    # 若反向类型合法，则交换方向保留关系
                    if relation_type_allowed(relation, tail_type, head_type):
                        head, tail = tail, head
                        head_type, tail_type = tail_type, head_type
                    else:
                        if source == "auto_ml" and confidence >= 0.45:
                            pass
                        else:
                            continue

                if source == "auto_rule" and any(str(t).startswith("开放谓词:") for t in trigger_words):
                    source = "auto_open_ie"
                    confidence = round(min(1.0, confidence + 0.02), 3)
                row = [head, relation, tail, source, confidence, evidence_triggers, sentence, review_flag]
                calibrated_confidence, feature_notes = feature_calibrated_confidence(row, entity_type_map, alias_map)
                if calibrated_confidence <= 0:
                    continue
                row[4] = calibrated_confidence
                if feature_notes:
                    row[5] = f"{row[5]}|{'|'.join(feature_notes)}"
                if calibrated_confidence >= 0.74:
                    row[7] = "否"
                triples.append(row)
                relation_stats[source] += 1

    # 6. 去重并保存三元组
    triples = aggregate_relation_evidence(triples, entity_type_map, alias_map)
    best_triples = {}
    source_rank = {"auto_rule": 5, "auto_open_ie": 4, "auto_feature_ml": 3, "auto_ml": 3, "auto_cooccur": 1}
    for t in triples:
        key = (t[0], t[1], t[2])
        if t[1] in {"就读于", "毕业于"} and not any(token in t[2] for token in ("大学", "学院", "学校")):
            continue
        if t[1] == "合作" and any(hint in t[6] for hint in ("说法", "谈到")):
            continue
        if relation_context_contradicts(t, entity_type_map):
            continue
        if t[1] in {"父亲", "母亲"} and (t[4] < 0.8 or not str(t[5]).startswith("模板:")):
            continue
        if t[3] == "auto_cooccur" and t[4] < 0.29:
            continue
        if t[3] in {"auto_ml", "auto_feature_ml"} and t[4] < 0.50:
            continue
        prev = best_triples.get(key)
        if prev is None:
            best_triples[key] = t
            continue
        prev_rank = (prev[4], source_rank.get(prev[3], 0), len(str(prev[5])))
        new_rank = (t[4], source_rank.get(t[3], 0), len(str(t[5])))
        if new_rank > prev_rank:
            best_triples[key] = t
    unique_triples = normalize_organization_hierarchy(list(best_triples.values()), entity_type_map)
    core_triples = [
        row for row in unique_triples
        if row[3] in {"auto_rule", "auto_open_ie"} and row[4] >= 0.84 and row[1] != "相关"
    ]

    print("正在保存三元组数据...")
    # 完整审计文件：保留来源、置信度、证据句和复核标记，便于人工校验。
    with open('turing_triples_auto_audit.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['头实体', '关系', '尾实体', '来源', '置信度', '触发词', '证据句', '建议人工复核'])
        writer.writerows(unique_triples)

    # 核心文件：只保留高置信规则关系，供展示或语义网导入优先使用。
    with open('turing_triples_core.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['头实体', '关系', '尾实体', '来源', '置信度', '触发词', '证据句', '建议人工复核'])
        writer.writerows(core_triples)
        
    print(f"共抽取了 {len(unique_triples)} 条知识三元组。")
    print(f"其中核心展示三元组 {len(core_triples)} 条。")
    print(
        f"来源统计：rule={relation_stats['auto_rule']} open_ie={relation_stats['auto_open_ie']} "
        f"feature_ml={relation_stats['auto_feature_ml']} cooccur={relation_stats['auto_cooccur']}"
    )
    print("已生成 turing_triples_auto_audit.csv、turing_triples_core.csv。")

if __name__ == "__main__":
    extract_triples()
