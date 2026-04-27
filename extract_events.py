import csv
import re
from collections import defaultdict


EVENT_FIELDS = [
    "event_id",
    "event_type",
    "trigger",
    "subject",
    "time",
    "location",
    "object",
    "participants",
    "cause",
    "result",
    "previous_event",
    "next_event",
    "source",
    "confidence",
    "evidence_sentence",
    "review_flag",
]

EVENT_SPECS = [
    {
        "event_type": "出生事件",
        "triggers": ("出生", "生下"),
        "subject_types": {"Person"},
        "object_types": set(),
        "location_types": {"Location"},
        "confidence": 0.88,
    },
    {
        "event_type": "教育事件",
        "triggers": ("考入", "就读", "攻读", "毕业", "获博士学位", "学习"),
        "subject_types": {"Person"},
        "object_types": {"Organization"},
        "location_types": {"Organization", "Location"},
        "confidence": 0.84,
    },
    {
        "event_type": "任职事件",
        "triggers": ("任职", "供职", "服务", "兼职工作", "负责", "副主任", "加入"),
        "subject_types": {"Person"},
        "object_types": {"Organization"},
        "location_types": {"Organization", "Location"},
        "confidence": 0.82,
    },
    {
        "event_type": "研究事件",
        "triggers": ("研究", "提出", "证明", "应用", "介绍"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Concept", "Machine", "Book"},
        "location_types": set(),
        "confidence": 0.8,
    },
    {
        "event_type": "发表事件",
        "triggers": ("发表", "发布", "写过", "撰写"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Book", "Concept"},
        "location_types": set(),
        "confidence": 0.83,
    },
    {
        "event_type": "密码破译事件",
        "triggers": ("破解", "破译", "解密", "密码分析"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Machine", "Concept"},
        "location_types": {"Organization", "Location"},
        "confidence": 0.84,
    },
    {
        "event_type": "设计开发事件",
        "triggers": ("设计", "改进", "开发", "建造", "制作", "研制"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Machine", "Concept"},
        "location_types": set(),
        "confidence": 0.82,
    },
    {
        "event_type": "获奖荣誉事件",
        "triggers": ("被选为", "当选", "授予", "颁发"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Organization", "Concept", "Book"},
        "location_types": {"Organization", "Location"},
        "confidence": 0.82,
    },
    {
        "event_type": "法律迫害事件",
        "triggers": ("迫害", "起诉", "定罪", "公审", "赦免", "道歉", "拒绝"),
        "subject_types": {"Person", "Organization"},
        "object_types": {"Person", "Concept"},
        "location_types": {"Organization", "Location"},
        "confidence": 0.8,
    },
    {
        "event_type": "死亡事件",
        "triggers": ("死亡", "去世", "自杀", "吃这苹果"),
        "subject_types": {"Person"},
        "object_types": {"Concept"},
        "location_types": {"Location"},
        "confidence": 0.86,
    },
]

REVIEW_EVENT_TYPES = {"研究事件"}
GENERIC_OBJECTS = {"问题", "理论", "模型", "方法", "概念", "机器", "程序", "科学"}
NEGATION_CUES = ("不", "没有", "未", "无", "并非", "不是", "并不是", "尚未", "未能", "谢绝")

TRIGGER_PRIORITY = {
    "考入": 5,
    "毕业": 5,
    "被选为": 5,
    "授予": 5,
    "发表": 5,
    "死亡": 5,
    "兼职工作": 5,
    "副主任": 5,
    "负责": 4,
    "破解": 4,
    "破译": 4,
    "密码分析": 4,
    "改进": 4,
    "设计": 4,
    "生下": 4,
    "出生": 3,
    "攻读": 3,
    "学习": 3,
    "制作": 2,
}

RELATION_EVENT_HINTS = {
    "出生于": "出生事件",
    "就读于": "教育事件",
    "毕业于": "教育事件",
    "任职于": "任职事件",
    "发表": "发表事件",
    "撰写": "发表事件",
    "参与破解": "密码破译事件",
    "提出": "研究事件",
    "研究": "研究事件",
    "证明": "研究事件",
    "设计": "设计开发事件",
    "改进": "设计开发事件",
    "开发": "设计开发事件",
    "当选院士": "获奖荣誉事件",
    "迫害": "法律迫害事件",
    "聘请": "任职事件",
}

EVENT_RELATION_OBJECTS = {
    "出生事件": {"出生于"},
    "教育事件": {"就读于", "毕业于"},
    "任职事件": {"任职于", "聘请"},
    "研究事件": {"提出", "研究", "证明"},
    "发表事件": {"发表", "撰写"},
    "密码破译事件": {"参与破解"},
    "设计开发事件": {"设计", "改进", "开发"},
    "获奖荣誉事件": {"当选院士"},
    "法律迫害事件": {"迫害"},
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def load_domain_aliases(path="domain_aliases.csv"):
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


def load_entity_type_map(path="core_entities_auto.csv"):
    entity_type_map = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = normalize_text(row.get("实体名称", ""))
            typ = normalize_text(row.get("实体类型", ""))
            if name and typ:
                entity_type_map[name] = typ
    return entity_type_map


def load_relation_index(path="turing_triples_core.csv"):
    by_sentence = defaultdict(list)
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sentence = normalize_text(row.get("证据句", ""))
                relation = normalize_text(row.get("关系", ""))
                if not sentence or relation not in RELATION_EVENT_HINTS:
                    continue
                by_sentence[sentence].append(
                    {
                        "head": normalize_text(row.get("头实体", "")),
                        "relation": relation,
                        "tail": normalize_text(row.get("尾实体", "")),
                        "confidence": float(row.get("置信度", 0) or 0),
                    }
                )
    except FileNotFoundError:
        pass
    return by_sentence


def build_alias_map(entity_type_map):
    alias_map = load_domain_aliases()
    for name in entity_type_map:
        alias_map.setdefault(name, name)
    return alias_map


def apply_alias(name: str, alias_map: dict) -> str:
    return alias_map.get(name, name)


def split_line_into_segments(line: str):
    parts = re.split(r"[。！？；;]", line)
    return [part.strip(" ，,；;:：") for part in parts if part.strip(" ，,；;:：")]


def collect_mentions(sentence: str, alias_map: dict, entity_type_map: dict):
    mentions = []
    seen = set()
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        canonical = apply_alias(alias, alias_map)
        typ = entity_type_map.get(canonical, "")
        if not typ:
            continue
        start = sentence.find(alias)
        while start != -1:
            end = start + len(alias)
            key = (start, end, canonical, typ)
            if key not in seen:
                seen.add(key)
                mentions.append(
                    {
                        "start": start,
                        "end": end,
                        "alias": alias,
                        "canonical": canonical,
                        "type": typ,
                    }
                )
            start = sentence.find(alias, start + 1)
    mentions.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    return mentions


def add_pronoun_mentions(mentions, sentence, carry_person, entity_type_map):
    if not carry_person:
        return mentions
    enriched = list(mentions)
    for token in ("他", "其"):
        start = sentence.find(token)
        while start != -1:
            if token == "他" and sentence[start:start + 2] == "他们":
                start = sentence.find(token, start + 1)
                continue
            enriched.append(
                {
                    "start": start,
                    "end": start + len(token),
                    "alias": token,
                    "canonical": carry_person,
                    "type": entity_type_map.get(carry_person, "Person"),
                }
            )
            start = sentence.find(token, start + 1)
    enriched.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    return enriched


def nearest_mention(mentions, anchor: int, required_types=None, direction="both", max_gap=48):
    required_types = required_types or set()
    candidates = []
    for mention in mentions:
        if required_types and mention["type"] not in required_types:
            continue
        if direction == "before":
            gap = anchor - mention["end"]
            if gap < 0 or gap > max_gap:
                continue
        elif direction == "after":
            gap = mention["start"] - anchor
            if gap < 0 or gap > max_gap:
                continue
        else:
            gap = min(abs(anchor - mention["start"]), abs(anchor - mention["end"]))
            if gap > max_gap:
                continue
        candidates.append((gap, -(mention["end"] - mention["start"]), mention))
    if not candidates:
        return None
    return sorted(candidates)[0][2]


def mentions_by_type(mentions, types):
    return [m for m in mentions if m["type"] in types]


def extract_times(sentence: str):
    patterns = [
        r"\d{4}\s*年\d{1,2}\s*月\d{1,2}\s*日",
        r"\d{4}\s*年\d{1,2}\s*月",
        r"\d{4}\s*年\d{1,2}\s*月到\d{4}\s*年\d{1,2}\s*月",
        r"\d{4}\s*年到\d{4}\s*年",
        r"\d{4}\s*年",
        r"二次世界大战期间",
        r"第二次世界大战期间",
        r"战争结束时",
        r"每年六月的第一周",
    ]
    spans = []
    for pattern in patterns:
        for match in re.finditer(pattern, sentence):
            spans.append((match.start(), re.sub(r"\s+", "", match.group(0))))
    seen = set()
    times = []
    for _, text in sorted(spans):
        if text not in seen:
            seen.add(text)
            times.append(text)
    return times


def choose_time(sentence: str, trigger_pos: int, event_type: str = "", trigger: str = ""):
    times = extract_times(sentence)
    if not times:
        return ""
    if event_type == "法律迫害事件" and trigger in {"赦免", "拒绝", "道歉"}:
        return times[0]
    positioned = []
    for time in times:
        pos = sentence.find(time)
        positioned.append((abs(pos - trigger_pos), time))
    return sorted(positioned)[0][1]


def choose_subject(sentence, mentions, trigger_pos, spec, carry_person):
    if spec["event_type"] == "法律迫害事件":
        legal_orgs = [
            m for m in mentions
            if m["type"] == "Organization"
            and any(hint in m["canonical"] for hint in ("政府", "司法", "警方", "法院", "上议院"))
        ]
        if legal_orgs:
            return sorted(legal_orgs, key=lambda m: abs(m["start"] - trigger_pos))[0]["canonical"]
        org = nearest_mention(mentions, trigger_pos, {"Organization"}, "before", 88)
        if not org:
            org = nearest_mention(mentions, trigger_pos, {"Organization"}, "after", 48)
        if org:
            return org["canonical"]
    subject = nearest_mention(mentions, trigger_pos, spec["subject_types"], "before", 56)
    if not subject:
        subject = nearest_mention(mentions, trigger_pos, spec["subject_types"], "after", 32)
    if not subject and carry_person and "Person" in spec["subject_types"]:
        return carry_person
    return subject["canonical"] if subject else ""


def choose_object(mentions, trigger_pos, spec):
    if not spec["object_types"]:
        return ""
    obj = nearest_mention(mentions, trigger_pos, spec["object_types"], "after", 72)
    if not obj:
        obj = nearest_mention(mentions, trigger_pos, spec["object_types"], "before", 48)
    if obj and obj["canonical"] not in GENERIC_OBJECTS:
        return obj["canonical"]
    return ""


def choose_location(mentions, trigger_pos, spec):
    if not spec["location_types"]:
        return ""
    location = nearest_mention(mentions, trigger_pos, spec["location_types"], "before", 64)
    if not location:
        location = nearest_mention(mentions, trigger_pos, spec["location_types"], "after", 48)
    return location["canonical"] if location else ""


def collect_participants(mentions, subject, obj, location):
    participants = []
    for mention in mentions:
        name = mention["canonical"]
        if name in {subject, obj, location}:
            continue
        if mention["type"] in {"Person", "Organization"} and name not in participants:
            participants.append(name)
    return "；".join(participants[:5])


def infer_cause_result(sentence: str, trigger: str):
    trigger_pos = sentence.find(trigger)
    cause = ""
    result = ""
    if trigger_pos < 0:
        return cause, result

    before = sentence[:trigger_pos]
    after = sentence[trigger_pos + len(trigger):]
    cause_markers = ("因为", "由于", "因", "凭借")
    result_markers = ("因此", "从而", "使得", "导致", "以至于", "于是")

    for marker in cause_markers:
        pos = before.rfind(marker)
        if pos >= 0:
            cause = before[pos + len(marker):].strip(" ，,；;:：")
            break
    for marker in result_markers:
        pos = after.find(marker)
        if pos >= 0:
            result = after[pos + len(marker):].strip(" ，,；;:：")
            break
    return cause[:80], result[:100]


def has_negated_trigger(sentence: str, trigger: str):
    trigger_pos = sentence.find(trigger)
    if trigger_pos < 0:
        return False
    local_before = sentence[max(0, trigger_pos - 10):trigger_pos]
    local_after = sentence[trigger_pos:trigger_pos + len(trigger) + 8]
    if "没有答案" in local_after:
        return False
    if any(cue in local_before for cue in NEGATION_CUES):
        return True
    negated_patterns = (
        rf"(?:并非|并不是|不是|没有|未|尚未|未能).{{0,8}}{re.escape(trigger)}",
        rf"不是由.{{0,12}}{re.escape(trigger)}",
        rf"并非由.{{0,12}}{re.escape(trigger)}",
    )
    return any(re.search(pattern, sentence) for pattern in negated_patterns)


def relation_support_for_event(event, relations):
    wanted = EVENT_RELATION_OBJECTS.get(event["event_type"], set())
    supported = []
    for rel in relations:
        if rel["relation"] in wanted:
            supported.append(rel)
    return supported


def enhance_event_with_relations(event, relations, entity_type_map):
    supported = relation_support_for_event(event, relations)
    if not supported:
        return event

    event = dict(event)
    for rel in supported:
        head = rel["head"]
        tail = rel["tail"]
        relation = rel["relation"]
        head_type = entity_type_map.get(head, "")
        tail_type = entity_type_map.get(tail, "")

        if relation == "聘请":
            if not event["subject"] or event["subject"] == head:
                event["subject"] = tail
            if not event["location"] and head_type == "Organization":
                event["location"] = head
            if not event["object"] and head_type == "Organization":
                event["object"] = head
        elif relation == "迫害":
            if not event["subject"] or entity_type_map.get(event["subject"], "") != "Organization":
                event["subject"] = head
            if not event["object"]:
                event["object"] = tail
        else:
            if not event["subject"] and head_type in {"Person", "Organization"}:
                event["subject"] = head
            if relation in {"出生于"}:
                event["location"] = tail
                event["object"] = ""
            elif relation in {"就读于", "毕业于", "任职于", "当选院士"}:
                if not event["location"] and tail_type in {"Organization", "Location"}:
                    event["location"] = tail
                if not event["object"]:
                    event["object"] = tail
            elif not event["object"]:
                event["object"] = tail

    event["source"] = "auto_event_rule+relation"
    event["confidence"] = round(min(1.0, float(event["confidence"]) + 0.04), 3)
    if event["confidence"] >= 0.8:
        event["review_flag"] = "否"
    return event


def trigger_inside_entity_name(mentions, trigger_start, trigger_end):
    for mention in mentions:
        if mention["start"] < trigger_start and trigger_end <= mention["end"]:
            return True
    return False


def event_context_contradicts(event):
    sentence = event["evidence_sentence"]
    event_type = event["event_type"]
    trigger = event["trigger"]
    subject = event["subject"]
    obj = event["object"]
    location = event["location"]
    trigger_pos = sentence.find(trigger)
    subject_pos = sentence.find(subject) if subject else -1
    obj_pos = sentence.find(obj) if obj else -1
    location_pos = sentence.find(location) if location else -1

    if any(noise in sentence for noise in ("页面存档", "参考资料", "外部链接")):
        return True
    if has_negated_trigger(sentence, trigger):
        return True
    if not subject and event_type not in {"获奖荣誉事件"}:
        return True
    if event_type in {"教育事件", "任职事件"} and not (obj or location):
        return True
    if event_type == "任职事件" and any(noise in sentence for noise in ("纯数学工作", "工作压力", "软件工作")) and not location:
        return True
    if event_type == "任职事件" and location and location_pos >= 0:
        context = sentence[location_pos:location_pos + len(location) + 12]
        if any(hint in context for hint in ("监督下", "监管下", "指导下", "管理下", "主持下")):
            return True
    if event_type == "研究事件" and obj in GENERIC_OBJECTS:
        return True
    if event_type == "发表事件" and any(hint in sentence for hint in ("没有发表", "未发表", "都没有发表")):
        return True
    if event_type == "发表事件" and not obj:
        return True
    if event_type == "密码破译事件" and "加速破译" in sentence and obj_pos > trigger_pos >= 0:
        return True
    if event_type == "密码破译事件" and any(hint in sentence for hint in ("密码分析家", "历史学家", "谈到他的同事")):
        return True
    if event_type == "密码破译事件" and not obj and "密码分析" not in sentence:
        return True
    if event_type == "设计开发事件" and not obj and not event["time"]:
        return True
    if event_type == "法律迫害事件" and subject and subject == obj:
        return True
    if event_type == "法律迫害事件" and subject and any(media in subject for media in ("报", "杂志", "期刊")):
        return True
    if event_type == "法律迫害事件" and trigger == "定罪" and "宣布" in sentence and "赦免" in sentence:
        return True
    if event_type == "法律迫害事件" and trigger in {"拒绝"} and subject == "艾伦·图灵":
        return True
    if event_type == "死亡事件" and "直到去世" in sentence:
        return True
    if event_type == "死亡事件" and event["time"] and not event["time"].startswith("1954"):
        return True
    if event_type == "死亡事件" and "去世" in sentence and subject_pos > trigger_pos >= 0:
        return True
    return False


def confidence_for_event(spec, event):
    confidence = spec["confidence"]
    if event["time"]:
        confidence += 0.04
    if event["object"]:
        confidence += 0.03
    if event["location"]:
        confidence += 0.03
    if event["event_type"] in REVIEW_EVENT_TYPES:
        confidence -= 0.08
    if not event["subject"]:
        confidence -= 0.18
    return round(max(0.0, min(1.0, confidence)), 3)


def make_event_id(index: int):
    return f"E{index:04d}"


def extract_events_from_sentence(sentence, alias_map, entity_type_map, relation_index, carry_person):
    mentions = collect_mentions(sentence, alias_map, entity_type_map)
    mentions = add_pronoun_mentions(mentions, sentence, carry_person, entity_type_map)
    sentence_relations = relation_index.get(normalize_text(sentence), [])
    events = []
    for spec in EVENT_SPECS:
        for trigger in spec["triggers"]:
            start = sentence.find(trigger)
            while start != -1:
                if trigger_inside_entity_name(mentions, start, start + len(trigger)):
                    start = sentence.find(trigger, start + len(trigger))
                    continue
                subject = choose_subject(sentence, mentions, start, spec, carry_person)
                obj = choose_object(mentions, start + len(trigger), spec)
                location = choose_location(mentions, start, spec)
                event = {
                    "event_type": spec["event_type"],
                    "trigger": trigger,
                    "subject": subject,
                    "time": choose_time(sentence, start, spec["event_type"], trigger),
                    "location": location,
                    "object": obj,
                    "participants": collect_participants(mentions, subject, obj, location),
                    "cause": "",
                    "result": "",
                    "previous_event": "",
                    "next_event": "",
                    "source": "auto_event_rule",
                    "confidence": 0.0,
                    "evidence_sentence": sentence,
                    "review_flag": "否",
                }
                event["cause"], event["result"] = infer_cause_result(sentence, trigger)
                event["confidence"] = confidence_for_event(spec, event)
                if event["confidence"] < 0.72 or event["event_type"] in REVIEW_EVENT_TYPES:
                    event["review_flag"] = "是"
                event = enhance_event_with_relations(event, sentence_relations, entity_type_map)
                if not event_context_contradicts(event):
                    events.append(event)
                start = sentence.find(trigger, start + len(trigger))
    return events, mentions


def aggregate_events(events):
    grouped = {}
    for event in events:
        key = (
            event["event_type"],
            event["trigger"],
            event["subject"],
            event["time"],
            event["location"],
            event["object"],
            event["evidence_sentence"],
        )
        previous = grouped.get(key)
        if previous is None or event["confidence"] > previous["confidence"]:
            grouped[key] = event
    return sorted(
        grouped.values(),
        key=lambda e: (
            e["time"] or "9999年",
            e["evidence_sentence"],
            -float(e["confidence"]),
            e["event_type"],
        ),
    )


def select_core_events(events):
    best_by_sentence_type = {}
    for event in events:
        if event["confidence"] < 0.8:
            continue
        if event["review_flag"] == "是":
            continue
        if event["event_type"] in {"法律迫害事件", "死亡事件", "获奖荣誉事件"} and not event["time"]:
            continue
        if event["event_type"] in {"设计开发事件", "密码破译事件"} and not event["object"]:
            continue
        type_sentence_key = (event["event_type"], event["evidence_sentence"])
        previous = best_by_sentence_type.get(type_sentence_key)
        event_rank = (
            float(event["confidence"]),
            TRIGGER_PRIORITY.get(event["trigger"], 0),
            1 if event["source"].endswith("+relation") else 0,
            1 if event["time"] else 0,
            1 if event["object"] else 0,
            1 if event["location"] else 0,
        )
        if previous is None:
            best_by_sentence_type[type_sentence_key] = (event_rank, event)
            continue
        if event_rank > previous[0]:
            best_by_sentence_type[type_sentence_key] = (event_rank, event)

    return sorted(
        [event for _, event in best_by_sentence_type.values()],
        key=lambda e: (e["time"] or "9999年", e["evidence_sentence"], e["event_type"]),
    )


def write_events(path, events):
    rows = []
    for index, event in enumerate(events, 1):
        row = dict(event)
        row["event_id"] = make_event_id(index)
        row.setdefault("cause", "")
        row.setdefault("result", "")
        row.setdefault("previous_event", "")
        row.setdefault("next_event", "")
        rows.append(row)

    dated = [
        row for row in rows
        if row.get("time") and first_year_from_event(row) != 9999
    ]
    dated.sort(key=lambda e: (first_year_from_event(e), e.get("event_id", "")))
    for prev, curr in zip(dated, dated[1:]):
        prev["next_event"] = curr["event_id"]
        curr["previous_event"] = prev["event_id"]

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def first_year_from_event(event):
    text = event.get("time") or event.get("evidence_sentence", "")
    match = re.search(r"(\d{4})年", text)
    return int(match.group(1)) if match else 9999


def extract_events():
    print("正在加载实体与别名字典...")
    entity_type_map = load_entity_type_map("core_entities_auto.csv")
    alias_map = build_alias_map(entity_type_map)
    relation_index = load_relation_index("turing_triples_core.csv")
    relation_count = sum(len(items) for items in relation_index.values())
    print(f"已加载 {relation_count} 条核心关系用于事件元素补强。")

    print("正在加载语料并抽取事件...")
    with open("turing_corpus_clean.txt", "r", encoding="utf-8") as f:
        text = f.read()

    all_events = []
    carry_person = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("==="):
            continue
        for sentence in split_line_into_segments(line):
            events, mentions = extract_events_from_sentence(sentence, alias_map, entity_type_map, relation_index, carry_person)
            all_events.extend(events)
            persons = [m["canonical"] for m in mentions if m["type"] == "Person"]
            if persons:
                carry_person = persons[0]

    all_events = aggregate_events(all_events)
    core_events = select_core_events(all_events)
    write_events("turing_events_auto_audit.csv", all_events)
    write_events("turing_events_core.csv", core_events)

    stats = defaultdict(int)
    for event in all_events:
        stats[event["event_type"]] += 1
    print(f"共抽取 {len(all_events)} 个候选事件。")
    print(f"其中核心事件 {len(core_events)} 个。")
    print("事件类型统计：")
    for event_type, count in sorted(stats.items()):
        print(f"  - {event_type}: {count}")
    print("已生成 turing_events_auto_audit.csv、turing_events_core.csv。")


if __name__ == "__main__":
    extract_events()
