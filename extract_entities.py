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
    name = re.sub(r"\s+", " ", name.strip())
    name = name.strip("()（）\"'“”‘’")
    return name

def normalize_alias_key(name: str) -> str:
    """归一化括号英文名、缩写等别名键。"""
    name = normalize_name(name)
    name = re.sub(r"\s+", " ", name)
    return name

def load_domain_aliases(path: str = "domain_aliases.csv") -> dict:
    """从外部词典读取别名归一规则，避免把语料专属简称写死在代码里。"""
    aliases = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("enabled", "1")).strip() in {"0", "false", "False", "否"}:
                    continue
                alias = normalize_alias_key(row.get("alias", ""))
                canonical = normalize_name(row.get("canonical", ""))
                if alias and canonical and alias != canonical:
                    aliases[alias] = canonical
    except FileNotFoundError:
        pass
    return aliases

def load_entity_type_overrides(path: str = "entity_type_overrides.csv") -> dict:
    """读取少量实体类型修正规则，用于处理模型难以稳定判断的边界名。"""
    overrides = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("enabled", "1")).strip() in {"0", "false", "False", "否"}:
                    continue
                name = normalize_name(row.get("name", ""))
                entity_type = row.get("entity_type", "").strip()
                if name and entity_type:
                    overrides[name] = entity_type
    except FileNotFoundError:
        pass
    return overrides

def load_entity_blocklist(path: str = "entity_blocklist.csv") -> dict:
    """读取按类型配置的噪声实体黑名单。"""
    blocklist = defaultdict(set)
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("enabled", "1")).strip() in {"0", "false", "False", "否"}:
                    continue
                entity_type = row.get("entity_type", "").strip()
                name = normalize_name(row.get("name", ""))
                if entity_type and name:
                    blocklist[entity_type].add(name)
    except FileNotFoundError:
        pass
    return dict(blocklist)

def build_alias_map():
    return load_domain_aliases()

ENTITY_TYPE_OVERRIDES = load_entity_type_overrides()
BOOK_TITLE_AS_ORGANIZATION = frozenset(
    name for name, typ in ENTITY_TYPE_OVERRIDES.items()
    if typ == "Organization" and name.startswith("《")
)
# 别名合并后仅 rule 的机构名，无 spaCy 时也要能保留
RULE_ONLY_ORGANIZATION_ALLOWLIST = frozenset(
    name for name, typ in ENTITY_TYPE_OVERRIDES.items()
    if typ == "Organization" and not name.startswith("《")
)
 
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
    if any(word in entity_name for word in ["理论", "测试", "生物学", "计算机科学"]):
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

# 高频误检实体从外部词典读取；只保留明显不是该类型的噪声。
ENTITY_BLOCKLIST_BY_TYPE = load_entity_blocklist()

def should_drop_by_blocklist(name: str, typ: str) -> bool:
    blocked = ENTITY_BLOCKLIST_BY_TYPE.get(typ)
    return bool(blocked and name in blocked)

def infer_entity_subtype(name: str, typ: str) -> str:
    """在不改变主类型的前提下，给实体补充轻量子类型。"""
    if typ == "Organization":
        if any(token in name for token in ("大学", "学院", "学校")):
            return "University"
        if any(token in name for token in ("实验室", "研究所", "研究院", "中央研究院")):
            return "ResearchInstitute"
        if any(token in name for token in ("政府", "司法部", "国会", "上议院", "警方")):
            return "GovernmentAgency"
        if any(token in name for token in ("海军", "军情", "密码学校", "密码破译", "GC&CS", "GCHQ")):
            return "MilitaryAgency"
        if any(token in name for token in ("报", "杂志", "出版社", "电视台")):
            return "MediaOrganization"
        if any(token in name for token in ("协会", "学会", "俱乐部", "委员会")):
            return "Association"
        if "公司" in name:
            return "Company"
        return "Organization"
    if typ == "Book":
        if any(token in name for token in ("论文", "基础", "可计算数", "机器和智能")):
            return "Paper"
        if any(token in name for token in ("法", "保密法", "法案")):
            return "Law"
        if any(token in name for token in ("选集", "著作")):
            return "Book"
        return "Work"
    if typ == "Concept":
        if any(token in name for token in ("理论", "定理", "公式", "算法")):
            return "Theory"
        if "测试" in name:
            return "Test"
        if "问题" in name:
            return "Problem"
        if any(token in name for token in ("智能", "科学", "数学", "密码学")):
            return "Discipline"
        return "Concept"
    if typ == "Machine":
        if "密码机" in name:
            return "CipherMachine"
        if any(token in name for token in ("计算机", "电脑")):
            return "Computer"
        if any(token in name for token in ("引擎", "乘法器", "装置", "机器", "机")):
            return "Device"
        return "Machine"
    if typ == "Event":
        if any(token in name for token in ("战争", "战役")):
            return "War"
        if "运动会" in name or "奥运" in name:
            return "SportsEvent"
        if any(token in name for token in ("审判", "赦免", "法案")):
            return "LegalEvent"
        return "Event"
    if typ == "Location":
        if name.endswith("国") or name in {"英国", "美国", "德国", "法国", "印度", "波兰"}:
            return "Country"
        if name.endswith(("州", "郡", "市", "镇")):
            return "AdministrativeRegion"
        if any(token in name for token in ("庄园", "学院", "实验室")):
            return "Place"
        return "Location"
    if typ == "Person":
        return "Person"
    return ""

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
    if len(name) < 2 or len(name) > 24:
        return False
    bad_tokens = ["，", "。", "：", "；", "？", "！", "（", "）", "==", "http", "页面存档", "……", "——"]
    if any(t in name for t in bad_tokens):
        return False
    if re.fullmatch(r"\d+", name):
        return False
    # 过长且无专名特征的英文碎片
    if len(name) > 20 and re.search(r"[A-Za-z]", name) and not re.search(r"[\u4e00-\u9fff]", name):
        return False
    return True

ORG_SUFFIXES = (
    "大学", "学院", "学校", "实验室", "研究所", "研究院", "学会",
    "协会", "政府", "海军", "司法部", "国会", "议院", "密码局", "军情六处",
    "密码学校", "俱乐部", "公司", "银行", "档案馆", "图书馆", "代表队",
)
LOC_SUFFIXES = ("国", "州", "郡", "市", "省", "县", "岛", "洋", "海", "城", "洲", "庄园", "公园")
EVENT_HINTS = ("战争", "运动会", "审判", "纪念", "大会")
MACHINE_HINTS = ("机器", "密码机", "引擎", "计算机", "设备")
CONCEPT_HINTS = ("理论", "测试", "智能", "科学", "主义", "方法", "模型", "算法", "公式", "问题", "概念")
PERSON_CONTEXT_HINTS = (
    "出生", "生于", "提出", "认为", "证明", "写道", "发明", "研究",
    "毕业", "就读", "父亲", "母亲", "同事", "导师", "数学家",
    "逻辑学家", "科学家", "教授",
)
LOCATION_CONTEXT_HINTS = ("位于", "来到", "前往", "抵达", "迁往", "来自", "出生于", "生于", "住在", "回到", "从", "在该处", "火车", "车站", "骑车", "跑到")
ORGANIZATION_CONTEXT_HINTS = ("任职于", "加入", "就读于", "毕业于", "工作于", "服务于", "属于", "攻读", "兼职工作", "招聘")
GENERIC_ORG_NAMES = {"实验室", "研究院", "研究所", "学院", "大学", "学校", "学会", "协会", "政府"}
GENERIC_MACHINE_NAMES = {"机器", "计算机器", "设备", "程序"}
GENERIC_CONCEPT_NAMES = {"问题", "方法", "模型", "概念", "理论", "公式", "算法", "程序"}
ENTITY_SUFFIX_TYPE_HINTS = {
    "Organization": (
        "大学", "学院", "学校", "研究所", "研究院", "实验室", "学会", "协会", "密码局",
        "海军", "司法部", "国会", "军情六处", "密码学校", "俱乐部", "公司", "银行",
        "档案馆", "图书馆", "代表队",
    ),
    "Location": ("庄园", "公园", "郡", "州", "省", "市", "洋"),
    "Concept": ("测试", "理论", "模型", "方法", "算法", "公式", "问题", "概念"),
    "Machine": ("密码机", "机器", "设备", "引擎", "计算机", "程序"),
}
STAGE_HEADING_HINTS = ("生平", "生涯", "时期", "研究", "文化", "作品", "参考资料", "外部链接", "参见", "注释", "奖项")

def infer_candidate_type(name: str) -> str:
    guessed = guess_type_by_rule(name)
    if guessed:
        return guessed
    for typ, suffixes in ENTITY_SUFFIX_TYPE_HINTS.items():
        if any(name.endswith(suffix) for suffix in suffixes):
            return typ
    return ""

def infer_parenthetical_type(long_name: str, short_name: str, context: str = "") -> str:
    inferred = infer_candidate_type(long_name)
    if inferred:
        return inferred
    context_text = f"{long_name}{short_name}{context}"
    if re.fullmatch(r"[A-Z][A-Z0-9&.\-]{1,10}", short_name):
        if any(hint in context_text for hint in MACHINE_HINTS):
            return "Machine"
        if any(hint in context_text for hint in ORG_SUFFIXES + ORGANIZATION_CONTEXT_HINTS):
            return "Organization"
        if any(hint in context_text for hint in CONCEPT_HINTS):
            return "Concept"
        return "Organization"
    if re.fullmatch(r"[A-Z][A-Za-z.\-]+(?:\s+[A-Z][A-Za-z.\-]+){1,4}", short_name):
        if any(hint in context_text for hint in ("父亲", "母亲", "同事", "导师", "饰演", "创办人", "数学家", "教授", "得主")):
            return "Person"
        if any(hint in context_text for hint in ORG_SUFFIXES + ORGANIZATION_CONTEXT_HINTS):
            return "Organization"
    return ""

def looks_like_noisy_parenthetical_long_name(name: str, typ: str) -> bool:
    if typ != "Person":
        return False
    if re.search(r"^(?:他|她|它|其|该|这|那|一个|一种|同年|当时)", name):
        return True
    if any(token in name for token in ("成绩", "时间", "得主", "仅比", "他的", "她的", "当被问及")):
        return True
    return len(name) > 14 and not has_strong_person_shape(name)

def extract_parenthetical_aliases(text: str):
    alias_map = {}
    for m in re.finditer(r"([\u4e00-\u9fffA-Za-z·&\-]{2,30})[（(]([A-Za-z][A-Za-z0-9&.\-\s']{1,32})[）)]", text):
        long_name = normalize_name(m.group(1))
        short_name = normalize_alias_key(m.group(2))
        if not long_name or not short_name:
            continue
        alias_map[short_name] = long_name
    return alias_map

def mine_parenthetical_candidates(text: str):
    candidates = []
    pattern = r"([\u4e00-\u9fffA-Za-z·&\-]{2,30})[（(]([A-Za-z][A-Za-z0-9&.\-\s']{1,32})[）)]"
    for m in re.finditer(pattern, text):
        long_name = normalize_name(m.group(1))
        short_name = normalize_alias_key(m.group(2))
        context = text[max(0, m.start() - 24):min(len(text), m.end() + 24)]
        inferred = infer_parenthetical_type(long_name, short_name, context)
        if (
            inferred
            and is_valid_entity_name(long_name)
            and not looks_like_sentence_fragment(long_name)
            and not looks_like_noisy_parenthetical_long_name(long_name, inferred)
        ):
            candidates.append((long_name, inferred))
        if inferred and is_valid_entity_name(short_name):
            candidates.append((short_name, inferred))

    contextual_patterns = [
        (r"叫([\u4e00-\u9fffA-Za-z·&\-]{2,16})[（(][^)]+[）)]的(?:日间)?学校", "Organization"),
        (r"([\u4e00-\u9fffA-Za-z·&\-]{2,24}(?:学校|大学|学院|实验室|研究所|研究院|学会|协会|密码学校|俱乐部))[（(][^)]+[）)]", "Organization"),
        (r"([\u4e00-\u9fffA-Za-z·&\-]{2,24}(?:引擎|密码机|计算机|程序|机器|机))[（(][^)]+[）)]", "Machine"),
    ]
    for pattern, typ in contextual_patterns:
        for match in re.findall(pattern, text):
            name = normalize_name(match)
            if is_valid_entity_name(name) and not looks_like_sentence_fragment(name):
                candidates.extend(expand_nested_entity_candidates(name, typ))
    return candidates

def mine_heading_candidates(text: str):
    candidates = []
    for raw_line in text.splitlines():
        line = normalize_name(raw_line.strip("= "))
        if not line or len(line) > 20:
            continue
        if re.search(r"[，,。！？；;：:]", line):
            continue
        if any(hint in line for hint in STAGE_HEADING_HINTS):
            continue
        guessed = guess_type_by_rule(line)
        if guessed:
            candidates.append((line, guessed))
            continue
        if any(hint in line for hint in MACHINE_HINTS):
            candidates.append((line, "Machine"))
        elif any(hint in line for hint in CONCEPT_HINTS):
            candidates.append((line, "Concept"))
        elif any(line.endswith(suffix) for suffix in ORG_SUFFIXES):
            candidates.append((line, "Organization"))
    return candidates

PHRASE_SPLIT_CUES = (
    "叫做", "称为", "名为", "即", "作为", "用于", "用来", "负责", "研究", "提出",
    "考入", "就读", "毕业于", "加入", "进入", "任职于", "工作于", "位于", "在", "于",
    "从", "对", "为", "由", "把", "将", "使", "让", "通过", "进行", "继续", "成为",
    "开发", "制作", "改进", "使用", "尝试", "判定", "证明", "发表", "写过", "撰写",
    "找到", "模仿", "执行", "颁发给",
    "是", "被",
    "包括", "还是",
)
LEADING_NOISE_PATTERNS = (
    r"^(?:他|她|它|其|该|这|那|一种|一个|一些|许多|很多|所有|这个|那个)+",
    r"^(?:在|于|从|对|为|由|通过|对于|关于|作为)+",
    r"^(?:后来|随后|当时|期间|此后|战后|战争结束时)+",
    r"^(?:可以|能够|就|时|当时|没有|一台|真正的|现代)+",
    r"^\d{2,4}年",
)
INNER_NOISE_HINTS = (
    "能够", "可以", "继续", "需要", "帮助", "期间", "主要", "负责", "尝试", "用于",
    "用来", "工作", "研究", "提出", "写过", "撰写", "证明", "发表", "进行", "开发",
    "制作", "改进", "包括", "使", "让", "成为", "还是", "后来", "随后", "当时", "被", "还",
    "找到", "模仿", "执行", "颁发", "授予",
)
LEADING_NOISE_TOKENS = (
    "其中", "虽然", "后来", "随后", "当时", "期间", "此后", "所有在", "所有", "这种",
    "这个", "那个", "一种", "一个", "一些", "许多", "很多", "他", "她", "它", "其",
    "可以", "能够", "就", "时", "没有", "一台", "真正的", "现代",
)
RULE_PHRASE_TEMPLATE_HINTS = (
    "一个", "一种", "一些", "许多", "很多", "用于", "用来", "尝试", "提供", "介绍",
    "允许", "帮助", "完成", "继续", "研究", "分析", "判定", "决定", "作为",
)
LEADING_NOISE_CHARS = set("其虽然后随当中在于从对为由把将使让被又仍还可就时")

def sanitize_candidate_name(name: str, typ: str) -> str:
    name = normalize_name(name)
    if not name:
        return ""
    suffixes = ENTITY_SUFFIX_TYPE_HINTS.get(typ, ())

    changed = True
    while changed and name:
        changed = False
        if len(name) >= 3 and name[0] in LEADING_NOISE_CHARS:
            trimmed = normalize_name(name[1:])
            if trimmed and any(trimmed.endswith(suffix) for suffix in suffixes):
                name = trimmed
                changed = True
        for token in LEADING_NOISE_TOKENS:
            if name.startswith(token):
                trimmed = normalize_name(name[len(token):])
                if trimmed and any(trimmed.endswith(suffix) for suffix in suffixes):
                    name = trimmed
                    changed = True
        for cue in PHRASE_SPLIT_CUES:
            if cue not in name:
                continue
            tail = normalize_name(name.split(cue)[-1])
            if tail and any(tail.endswith(suffix) for suffix in suffixes):
                if tail != name:
                    name = tail
                    changed = True
        for pattern in LEADING_NOISE_PATTERNS:
            trimmed = normalize_name(re.sub(pattern, "", name))
            if trimmed and trimmed != name and any(trimmed.endswith(suffix) for suffix in suffixes):
                name = trimmed
                changed = True

    fragments = set()
    for suffix in suffixes:
        pattern = rf"[A-Za-z\u4e00-\u9fff·&\-]{{1,24}}{re.escape(suffix)}"
        for match in re.finditer(pattern, name):
            fragments.add(normalize_name(match.group(0)))

    if fragments:
        def candidate_score(fragment: str):
            score = float(len(fragment))
            if any(fragment.endswith(suffix) for suffix in suffixes):
                score += 3.0
            score -= sum(2.0 for hint in INNER_NOISE_HINTS if hint in fragment)
            if "的" in fragment and typ != "Book":
                score -= 2.0
            if re.match(r"^(?:他|她|它|其|该|这|那|一种|一个|所有)", fragment):
                score -= 3.0
            return score

        name = max(
            fragments,
            key=lambda fragment: (
                candidate_score(fragment),
                -fragment.count("的"),
                len(fragment),
            ),
        )
    return normalize_name(name)

def expand_nested_entity_candidates(name: str, typ: str):
    expanded = {(name, typ)}
    if typ == "Organization":
        parts = re.findall(r"[A-Za-z\u4e00-\u9fff·&\-]{2,24}(?:大学|学院|学校|实验室|研究所|研究院|学会|协会|密码学校|俱乐部|公司|银行)", name)
        for part in parts:
            part = normalize_name(part)
            if 2 <= len(part) <= 18:
                expanded.add((part, "Organization"))
        # 从复合机构名里截出后层机构，如“某大学某学院” -> “某学院”
        for suffix in ("学院", "实验室", "研究所", "研究院", "学校", "密码学校", "俱乐部"):
            m = re.search(rf"([\u4e00-\u9fffA-Za-z·&\-]{{2,12}}{suffix})$", name)
            if m:
                short = normalize_name(m.group(1))
                if short != name and 2 <= len(short) <= 12:
                    expanded.add((short, "Organization"))
    if typ == "Machine":
        for suffix in ("密码机", "引擎", "计算机", "程序", "机"):
            if name.endswith(suffix):
                if len(name) > len(suffix) and 2 <= len(name) <= 24:
                    expanded.add((name, "Machine"))
                if suffix != "机" and 3 <= len(suffix) <= len(name) and len(name) - len(suffix) <= 2:
                    expanded.add((suffix, "Machine"))
    return expanded

def mine_entity_candidates(text: str):
    candidates = []
    sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
    for sentence in sentences:
        for typ, suffixes in ENTITY_SUFFIX_TYPE_HINTS.items():
            for suffix in suffixes:
                pattern = rf"[A-Za-z\u4e00-\u9fff·&\-]{{2,24}}{re.escape(suffix)}"
                for match in re.findall(pattern, sentence):
                    name = sanitize_candidate_name(match, typ)
                    if not is_valid_entity_name(name):
                        continue
                    if looks_like_sentence_fragment(name):
                        continue
                    if any(hint in name for hint in INNER_NOISE_HINTS):
                        continue
                    candidates.extend(expand_nested_entity_candidates(name, typ))
        for match in re.findall(r"[A-Z][A-Z0-9&.\-]{1,10}", sentence):
            name = normalize_name(match)
            if 2 <= len(name) <= 12:
                candidates.append((name, "Organization"))
    return candidates

def mine_contextual_candidates(text: str):
    candidates = []
    patterns = [
        (r"(?:考入|就读于|毕业于|攻读|入读)([\u4e00-\u9fffA-Za-z·&\-]{2,28}(?:大学|学院|学校|实验室|研究所|研究院))", "Organization"),
        (r"(?:在|于|加入|进入)([\u4e00-\u9fffA-Za-z·&\-]{2,28}(?:大学|学院|学校|实验室|研究所|研究院|军情六处|密码学校|俱乐部|公司|银行))(?:负责|工作|任职|服务|兼职|学习|攻读)?", "Organization"),
        (r"成为([\u4e00-\u9fffA-Za-z·&\-]{2,28}(?:大学|学院|学校|实验室|研究所|研究院))的副主任", "Organization"),
        (r"(?:由|被|向)([\u4e00-\u9fffA-Za-z·&\-]{2,24}(?:大学|学院|学校|实验室|研究所|研究院|学会|协会|政府|海军|国会|司法部|密码局))(?:提供|任命|招聘|颁发|授予)", "Organization"),
        (r"(?:负责|设计|开发|制作|改进|建造|使用|运行|执行)([\u4e00-\u9fffA-Za-z·&\-]{2,24}(?:引擎|密码机|计算机|机器|设备|程序|机))", "Machine"),
        (r"([\u4e00-\u9fffA-Za-z·&\-]{2,24}(?:引擎|密码机|计算机|机器|设备|程序|机))(?:的研究工作|的软件工作|设置|信息|模型)", "Machine"),
        (r"最早的真正的计算机[——-]([\u4e00-\u9fffA-Za-z·&\-]{2,16})", "Machine"),
        (r"(?:提出|介绍|证明|研究|应用)(?:了|的)?(?:一个|一种|所谓的)?([\u4e00-\u9fffA-Za-z·&\-]{2,20}(?:测试|理论|模型|方法|算法|公式|问题|概念))", "Concept"),
        (r"(?:父亲|母亲|同事|导师|创办人|设计师|得主|饰演|历史学家|数学家)[\u4e00-\u9fffA-Za-z·&\-“”\"'，,、\s]{0,8}([A-Z][A-Za-z.\-]+(?:\s+[A-Z][A-Za-z.\-]+){1,4})", "Person"),
        (r"([A-Z][A-Za-z.\-]+(?:\s+[A-Z][A-Za-z.\-]+){1,4})[\u4e00-\u9fffA-Za-z·&\-“”\"'，,、\s]{0,8}(?:说|认为|谈到|饰演|创办|设计)", "Person"),
    ]
    for pattern, typ in patterns:
        for match in re.findall(pattern, text):
            name = sanitize_candidate_name(match, typ)
            if not name or not is_valid_entity_name(name):
                continue
            if looks_like_sentence_fragment(name):
                continue
            if any(hint in name for hint in INNER_NOISE_HINTS):
                continue
            candidates.extend(expand_nested_entity_candidates(name, typ))
    return candidates

def looks_like_stage_heading(name: str, src_set) -> bool:
    if "rule_heading" not in src_set:
        return False
    if len(name) > 10:
        return True
    return any(hint in name for hint in STAGE_HEADING_HINTS)

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
            scores["Location"] += 2
        if any(word in window for word in ORGANIZATION_CONTEXT_HINTS):
            scores["Organization"] += 2
        if any(word in window for word in EVENT_HINTS):
            scores["Event"] += 1
        if any(word in window for word in MACHINE_HINTS):
            scores["Machine"] += 2
        if any(word in window for word in CONCEPT_HINTS):
            scores["Concept"] += 2
        if "《" in window and "》" in window:
            scores["Book"] += 1
        if re.search(r"(与|和|及|、)" + re.escape(name) + r"(、|和|及|一同)", window):
            scores["Person"] += 1
    return scores

def refine_type_with_context(name: str, final_type: str, windows, vote_counter: Counter):
    context = "".join(windows)
    if final_type == "Person":
        if any(word in context for word in ("住在", "回到", "位于", "在该处", "骑", "途中")):
            if not any(word in context for word in PERSON_CONTEXT_HINTS):
                return "Location"
    if final_type in {"Machine", "Concept"}:
        if name.endswith("测试") or "测试" in name:
            return "Concept"
        if name.endswith("机") or "密码机" in name:
            return "Machine"
    if final_type == "Organization" and name.endswith("庄园"):
        return "Location"
    if final_type == "Location" and any(name.endswith(s) for s in ORG_SUFFIXES):
        return "Organization"
    if not final_type:
        return choose_type(vote_counter)
    return final_type

def choose_final_type(name: str, vote_counter: Counter, text: str):
    combined = Counter()
    combined.update(vote_counter)
    combined.update(score_by_name_shape(name))
    windows = collect_context_windows(text, name)
    combined.update(score_by_context(name, windows))
    final_type = choose_type(combined)
    final_type = calibrate_entity_type(name, final_type) if final_type else ""
    final_type = refine_type_with_context(name, final_type, windows, combined)
    return final_type, windows, combined

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

def has_strong_person_shape(name: str) -> bool:
    if "路" in name or "·" in name or " " in name:
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z.\s-]{2,}", name))

def context_signal_counts(windows):
    context = "".join(windows)
    person_score = sum(1 for word in PERSON_CONTEXT_HINTS if word in context)
    location_score = sum(1 for word in LOCATION_CONTEXT_HINTS if word in context)
    location_score += sum(
        1
        for cue in ("车站", "街", "路牌", "附近", "在那里", "住在", "回到", "火车", "骑车", "跑到", "经过")
        if cue in context
    )
    return person_score, location_score

def lacks_person_evidence(name: str, sources: set, votes: int, windows) -> bool:
    if sources != {"spacy"} or votes > 3:
        return False
    if has_strong_person_shape(name):
        return False
    if len(name) < 2 or len(name) > 5:
        return False
    person_score, location_score = context_signal_counts(windows)
    if person_score >= 2:
        return False
    return location_score > person_score or person_score == 0

def low_support_short_spacy_person(name: str, sources: set, votes: int) -> bool:
    if sources != {"spacy"} or votes > 4:
        return False
    if has_strong_person_shape(name):
        return False
    if re.search(r"[A-Za-z]", name):
        return False
    return 2 <= len(name) <= 8

def looks_like_generic_org(name: str, sources: set, votes: int):
    if name in GENERIC_ORG_NAMES:
        return votes <= 3 and not (sources & {"crf", "spacy"})
    if sources != {"spacy"} or votes > 3:
        return False
    return name.startswith("国家") and name.endswith(("实验室", "研究院", "研究所")) and len(name) <= 5

def looks_like_reference_org(name: str, sources: set, windows) -> bool:
    if sources & {"spacy", "crf"}:
        return False
    if "rule_phrase" not in sources:
        return False
    context = "".join(windows)
    return any(token in context for token in ("页面存档", "外部链接", "参考资料", "存于互联网档案馆"))

def looks_like_generic_machine(name: str, sources: set, votes: int):
    if name in GENERIC_MACHINE_NAMES:
        return votes <= 3 and not (sources & {"crf", "spacy"})
    if sources <= {"rule_phrase", "rule_context"} and not (sources & {"crf", "spacy"}):
        if name.endswith("计算机") and len(name) <= 6:
            return True
        if name.endswith("程序") and len(name) <= 4:
            return True
        if any(token in name for token in ("大学", "协会", "颁发", "找到", "模仿", "执行")):
            return True
    return False

def looks_like_generic_concept(name: str, sources: set, votes: int):
    if name in GENERIC_CONCEPT_NAMES and votes <= 6 and not (sources & {"crf", "spacy"}):
        return True
    return False

def looks_like_low_support_generic(name: str, final_type: str, sources: set, votes: int) -> bool:
    if sources != {"rule_phrase"} or votes > 2:
        return False
    if final_type == "Organization" and name in GENERIC_ORG_NAMES:
        return True
    if final_type == "Machine" and name in GENERIC_MACHINE_NAMES:
        return True
    if final_type == "Organization" and len(name) <= 2 and any(name.endswith(suffix) for suffix in ORG_SUFFIXES):
        return True
    if final_type == "Machine" and len(name) <= 4 and any(name.endswith(suffix) for suffix in ("机器", "设备", "机")):
        return True
    if final_type == "Concept" and len(name) <= 4 and any(name.endswith(suffix) for suffix in ("理论", "方法", "模型")):
        return True
    return False

def low_support_ambiguous_location(name: str, sources: set, votes: int, windows):
    if any(name.endswith(suffix) for suffix in LOC_SUFFIXES):
        return False
    if len(name) > 3 or votes > 3 or sources != {"spacy"}:
        return False
    context = "".join(windows)
    return not any(word in context for word in LOCATION_CONTEXT_HINTS)

def looks_like_prefixed_phrase(name: str, final_type: str, sources: set) -> bool:
    if "rule_phrase" not in sources:
        return False
    if final_type not in {"Organization", "Location", "Concept", "Machine"}:
        return False
    patterns = (
        r"^(?:后来|随后|虽然|其中|期间|当时|此后|所有在)",
        r"^\d{2,4}年",
        r"^[\u4e00-\u9fff]{1,4}(?:在|是|被|考入|进入|加入|成为|负责|提出)",
    )
    return any(re.match(pattern, name) for pattern in patterns)

def looks_like_rule_phrase_template(name: str, final_type: str, sources: set, windows) -> bool:
    if "rule_phrase" not in sources:
        return False
    if sources & {"spacy", "crf"}:
        return False
    if final_type not in {"Organization", "Location", "Concept", "Machine"}:
        return False
    if any(token in name for token in RULE_PHRASE_TEMPLATE_HINTS):
        return True
    if final_type == "Machine" and len(name) > 4 and any(name.endswith(suffix) for suffix in ("机器", "设备")):
        return True
    if final_type == "Concept" and ("或" in name or "与" in name):
        return True
    context = "".join(windows)
    if final_type == "Person":
        return False
    return name in context and any(hint in name for hint in INNER_NOISE_HINTS)

def looks_like_single_char_prefixed_entity(name: str, final_type: str, sources: set, votes: int) -> bool:
    if sources != {"rule_phrase"} or votes > 2:
        return False
    if len(name) < 4:
        return False
    if not re.match(r"^[\u4e00-\u9fff]", name):
        return False
    trimmed = name[1:]
    if final_type == "Machine" and any(trimmed.endswith(suffix) for suffix in ("密码机", "机器", "设备", "机")):
        return True
    if final_type == "Organization" and any(trimmed.endswith(suffix) for suffix in ORG_SUFFIXES):
        return True
    if final_type == "Location" and any(trimmed.endswith(suffix) for suffix in LOC_SUFFIXES):
        return True
    if final_type == "Concept" and any(trimmed.endswith(suffix) for suffix in ("测试", "理论", "方法", "模型")):
        return True
    return False

def looks_like_place_named_person(name: str, sources: set, votes: int, windows) -> bool:
    if sources != {"spacy"} or votes > 3:
        return False
    if len(name) < 2 or len(name) > 5:
        return False
    context = "".join(windows)
    location_cues = ("位于", "车站", "街", "路", "火车", "乘", "骑车", "跑到", "经过", "前往", "到达", "在")
    return any(cue in context for cue in location_cues) and not any(word in context for word in PERSON_CONTEXT_HINTS)

def looks_like_non_person_phrase(name: str, final_type: str, windows) -> bool:
    if final_type != "Person":
        return False
    if any(token in name for token in ("他的", "她的", "得主", "成绩", "时间", "仅比", "选拔")):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z.\s-]{2,}", name):
        words = name.split()
        lower_function_words = {"of", "the", "and", "with", "in", "on", "for", "to"}
        if any(word.lower() in lower_function_words for word in words):
            return True
        if len(words) == 1 and len(name) > 10:
            context = "".join(windows)
            return not any(hint in context for hint in ("说", "认为", "饰演", "创办", "设计", "历史学家", "数学家", "同事"))
    return False

def drop_prefix_fragments(entities):
    kept = []
    country_prefixes = ("英国", "美国", "德国", "法国", "波兰", "印度")
    for entity in sorted(entities, key=lambda x: (-len(x[0]), -x[4], x[0])):
        name, typ, _, _, votes, _ = entity
        is_fragment = False
        for kept_entity in kept:
            kept_name, kept_type, _, _, kept_votes, _ = kept_entity
            if typ != kept_type:
                continue
            if len(name) < 3 or len(kept_name) - len(name) > 4:
                continue
            if kept_votes < votes:
                continue
            if kept_name.startswith(name):
                is_fragment = True
                break
            if typ == "Organization" and kept_name.endswith(name) and kept_name[:-len(name)] in country_prefixes:
                is_fragment = True
                break
            if (
                typ == "Person"
                and re.fullmatch(r"[A-Za-z][A-Za-z.\s-]{2,}", name)
                and re.fullmatch(r"[A-Za-z][A-Za-z.\s-]{2,}", kept_name)
                and kept_name.endswith(name)
                and kept_name != name
                and kept_votes >= votes
            ):
                is_fragment = True
                break
        if not is_fragment:
            kept.append(entity)
    return kept

def structural_support_score(name: str, final_type: str, combined: Counter, src_set: set) -> float:
    score = 0.0
    score += combined.get(final_type, 0)
    if "rule_phrase" in src_set:
        score += 2.0
    if "rule_parenthetical" in src_set:
        score += 2.0
    if "rule_context" in src_set:
        score += 2.0
    if "rule_heading" in src_set:
        score += 2.5
    if any(name.endswith(suffix) for suffix in ENTITY_SUFFIX_TYPE_HINTS.get(final_type, ())):
        score += 2.0
    if final_type in {"Organization", "Concept", "Machine"} and re.fullmatch(r"[A-Z][A-Z0-9&.\-]{1,10}", name):
        score += 1.5
    if final_type == "Person" and has_strong_person_shape(name):
        score += 2.0
    return score

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
    print("正在读取语料...")
    with open("turing_corpus_clean.txt", "r", encoding="utf-8") as f:
        text = f.read()

    votes = defaultdict(Counter)
    source_counter = defaultdict(Counter)
    dynamic_alias_map = extract_parenthetical_aliases(text)

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

    # D. 结构化短语候选挖掘（后缀、缩写、上下文）
    for name, typ in mine_entity_candidates(text):
        votes[name][typ] += 2
        source_counter[name]["rule_phrase"] += 1
    for name, typ in mine_parenthetical_candidates(text):
        votes[name][typ] += 2
        source_counter[name]["rule_parenthetical"] += 1
    for name, typ in mine_contextual_candidates(text):
        votes[name][typ] += 2
        source_counter[name]["rule_context"] += 1
    for name, typ in mine_heading_candidates(text):
        votes[name][typ] += 3
        source_counter[name]["rule_heading"] += 1

    # E. 别名统一
    alias_map = build_alias_map()
    for short_name, long_name in dynamic_alias_map.items():
        alias_map.setdefault(short_name, long_name)
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
        final_type, windows, combined = choose_final_type(name, c, text)
        if not final_type:
            continue
        total_votes = sum(c.values())
        confidence = round(c.get(final_type, max(c.values())) / total_votes, 3) if total_votes else 0.0
        if should_drop_by_blocklist(name, final_type):
            continue
        if final_type == "Concept" and looks_like_sentence_fragment(name):
            continue
        # 纪念活动/年份类碎片，不宜作人物节点
        if final_type == "Person" and re.search(r"\d{2,4}年$", name):
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
        support_score = structural_support_score(name, final_type, combined, src_set)
        if looks_like_stage_heading(name, src_set):
            continue
        if looks_like_prefixed_phrase(name, final_type, src_set):
            continue
        if looks_like_rule_phrase_template(name, final_type, src_set, windows):
            continue
        if looks_like_low_support_generic(name, final_type, src_set, total_votes):
            continue
        if looks_like_single_char_prefixed_entity(name, final_type, src_set, total_votes):
            continue
        if final_type == "Person" and looks_like_place_named_person(name, src_set, total_votes, windows):
            continue
        if looks_like_non_person_phrase(name, final_type, windows):
            continue
        if final_type == "Person" and low_support_short_spacy_person(name, src_set, total_votes):
            continue
        if final_type == "Person" and lacks_person_evidence(name, src_set, total_votes, windows):
            continue
        if final_type == "Person" and looks_like_person_fragment(name, src_set, total_votes, windows):
            continue
        if final_type == "Organization" and looks_like_generic_org(name, src_set, total_votes):
            continue
        if final_type == "Organization" and looks_like_reference_org(name, src_set, windows):
            continue
        if final_type == "Machine" and looks_like_generic_machine(name, src_set, total_votes):
            continue
        if final_type == "Concept" and looks_like_generic_concept(name, src_set, total_votes):
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
        keep = keep or (
            src_set & {"rule_phrase", "rule_parenthetical", "rule_context"}
            and final_type in {"Organization", "Concept", "Machine", "Location"}
            and support_score >= 7
            and confidence >= 0.4
        )
        keep = keep or (
            "rule_heading" in src_set
            and final_type in {"Organization", "Concept", "Machine"}
            and support_score >= 6
        )
        keep = keep or (
            "rule_context" in src_set
            and final_type == "Person"
            and has_strong_person_shape(name)
            and support_score >= 7
            and confidence >= 0.45
        )
        keep = keep or (
            "rule_parenthetical" in src_set
            and final_type in {"Person", "Organization", "Machine", "Concept"}
            and support_score >= 6
            and confidence >= 0.45
        )
        keep = keep and (
            has_model
            or (final_type == "Book" and "rule" in src_set)
            or (
                final_type == "Organization"
                and name in RULE_ONLY_ORGANIZATION_ALLOWLIST
                and "rule" in src_set
            )
            or (
                src_set & {"rule_phrase", "rule_parenthetical", "rule_context"}
                and final_type in {"Organization", "Concept", "Machine", "Location"}
                and support_score >= 7
            )
            or (
                src_set & {"rule_parenthetical", "rule_context"}
                and final_type == "Person"
                and has_strong_person_shape(name)
                and support_score >= 7
            )
            or (
                "rule_heading" in src_set
                and final_type in {"Organization", "Concept", "Machine"}
                and support_score >= 6
            )
        )
        keep = keep and len(name) <= 24
        if not keep:
            continue
        final_entities.append(
            (
                name,
                final_type,
                infer_entity_subtype(name, final_type),
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
        writer.writerow(["实体名称", "实体类型", "实体子类型", "来源", "投票数", "置信度"])
        writer.writerows(final_entities)

    print(f"提取完成：core_entities_auto.csv 共 {len(final_entities)} 条实体")

if __name__ == "__main__":
    extract_and_save_entities()
