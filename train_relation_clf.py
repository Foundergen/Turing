import csv
import random
import re
import sys
from collections import Counter, defaultdict

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


ENTITY_PATH = "core_entities_auto.csv"
TRIPLE_PATH = "turing_triples_clean.csv"
CORPUS_PATH = "turing_corpus_clean.txt"
NEGATIVE_LABEL = "无关系"

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
    "参与": "参与",
    "参加": "参与",
    "投身": "参与",
    "二战": "参与",
    "破解": "参与破解",
    "破译": "参与破解",
    "解密": "参与破解",
    "提出": "提出",
    "发明": "提出",
    "设计": "提出",
    "发表": "提出",
    "研究": "研究",
    "探讨": "研究",
    "撰写": "撰写",
    "写了": "撰写",
    "写成": "撰写",
    "著有": "撰写",
    "著作": "撰写",
    "院士": "当选院士",
    "当选": "当选院士",
    "皇家学会": "当选院士",
    "属于": "属于",
    "隶属": "属于",
    "位于": "属于",
    "设立": "设立",
    "颁发": "设立",
    "授予": "设立",
}


def build_alias_map():
    return {
        "图灵": "艾伦·图灵",
        "Turing": "艾伦·图灵",
        "二战": "第二次世界大战",
        "剑桥": "剑桥大学",
        "普林斯顿": "普林斯顿大学",
        "恩尼格玛": "恩尼格玛密码机",
    }


def split_sentences(text):
    return [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]


def read_entity_names(path=ENTITY_PATH):
    names = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row:
                names.append(row[0].strip())
    return sorted(set(names), key=len, reverse=True)


def read_entity_types(path=ENTITY_PATH):
    entity_types = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                entity_types[row[0].strip()] = row[1].strip()
    return entity_types


def read_positive_triples(path=TRIPLE_PATH):
    triples = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3:
                triples.append((row[0].strip(), row[1].strip(), row[2].strip()))
    return triples


def build_sentence_index(sentences, triples):
    mapping = defaultdict(list)
    alias_map = build_alias_map()
    alias_rev = defaultdict(set)
    for short, canonical in alias_map.items():
        alias_rev[canonical].add(short)
        alias_rev[canonical].add(canonical)

    def mentions(ent):
        return alias_rev.get(ent, {ent})

    for head, relation, tail in triples:
        for sent in sentences:
            if any(x in sent for x in mentions(head)) and any(y in sent for y in mentions(tail)):
                mapping[(head, tail)].append((sent, relation))
                break
    return mapping


def feature_text(head, sentence, tail, entity_types):
    head_type = entity_types.get(head, "UNK")
    tail_type = entity_types.get(tail, "UNK")
    head_pos = sentence.find(head)
    tail_pos = sentence.find(tail)
    if head_pos == -1 or tail_pos == -1:
        dist = 999
        order = "UNK"
    else:
        dist = abs(head_pos - tail_pos)
        order = "H<T" if head_pos <= tail_pos else "T<H"
    trigger_words = sorted({w for w in RELATION_TRIGGER_RULES if w in sentence})
    trigger_flag = int(bool(trigger_words))
    trigger_text = "|".join(trigger_words[:6]) if trigger_words else "NONE"
    return (
        f"{head} [SEP] {sentence} [SEP] {tail} [SEP] "
        f"{head_type}>{tail_type} [SEP] dist={dist} [SEP] order={order} "
        f"[SEP] trig={trigger_flag} [SEP] trigwords={trigger_text}"
    )


def build_dataset(text, entities, triples, entity_path=ENTITY_PATH):
    random.seed(42)
    sentences = split_sentences(text)
    pos_map = build_sentence_index(sentences, triples)
    entity_types = read_entity_types(entity_path)

    samples = []
    positive_pairs = set()
    for (head, tail), items in pos_map.items():
        for sent, relation in items:
            samples.append((feature_text(head, sent, tail, entity_types), relation))
            positive_pairs.add((head, tail))

    neg_candidates = []
    for sent in sentences:
        found = [e for e in entities if e in sent]
        if len(found) < 2:
            continue
        for i in range(len(found)):
            for j in range(i + 1, len(found)):
                head, tail = found[i], found[j]
                if (head, tail) in positive_pairs or (tail, head) in positive_pairs:
                    continue
                neg_candidates.append((head, sent, tail))

    random.shuffle(neg_candidates)
    target_neg = min(len(neg_candidates), max(30, len(samples)))
    for head, sent, tail in neg_candidates[:target_neg]:
        samples.append((feature_text(head, sent, tail, entity_types), NEGATIVE_LABEL))

    random.shuffle(samples)
    X = [x for x, _ in samples]
    y = [label for _, label in samples]
    return X, y


def build_classifier(max_iter):
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1)),
            ("lr", LogisticRegression(max_iter=max_iter, class_weight="balanced")),
        ]
    )


def main():
    entity_path = sys.argv[1] if len(sys.argv) > 1 else ENTITY_PATH
    triple_path = sys.argv[2] if len(sys.argv) > 2 else TRIPLE_PATH

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    entities = read_entity_names(entity_path)
    triples = read_positive_triples(triple_path)
    X_all, y_all = build_dataset(text, entities, triples, entity_path=entity_path)
    if len(set(y_all)) < 2:
        raise RuntimeError("关系分类训练数据不足，至少需要两类标签。")

    print(f"训练样本总数: {len(X_all)}")
    print(f"标签分布: {dict(Counter(y_all))}")

    stratify_labels = y_all if min(Counter(y_all).values()) >= 2 else None
    test_size = 0.25 if len(X_all) >= 12 else 0.33
    X_train, X_valid, y_train, y_valid = train_test_split(
        X_all,
        y_all,
        test_size=test_size,
        random_state=42,
        shuffle=True,
        stratify=stratify_labels,
    )

    y_train_bin = [0 if y == NEGATIVE_LABEL else 1 for y in y_train]
    y_valid_bin = [0 if y == NEGATIVE_LABEL else 1 for y in y_valid]
    bin_clf = build_classifier(max_iter=1200)
    bin_clf.fit(X_train, y_train_bin)
    y_pred_bin = bin_clf.predict(X_valid)
    print("=== 二分类验证（有关系/无关系）===")
    print(classification_report(y_valid_bin, y_pred_bin, digits=4, zero_division=0))

    X_train_multi = [x for x, y in zip(X_train, y_train) if y != NEGATIVE_LABEL]
    y_train_multi = [y for y in y_train if y != NEGATIVE_LABEL]
    X_valid_multi = [x for x, y in zip(X_valid, y_valid) if y != NEGATIVE_LABEL]
    y_valid_multi = [y for y in y_valid if y != NEGATIVE_LABEL]
    if len(set(y_train_multi)) < 2:
        raise RuntimeError("关系类型样本过少，无法训练多分类器。")

    multi_clf = build_classifier(max_iter=1400)
    multi_clf.fit(X_train_multi, y_train_multi)
    if X_valid_multi:
        y_pred_multi = multi_clf.predict(X_valid_multi)
        print("=== 多分类验证（具体关系类型）===")
        print(classification_report(y_valid_multi, y_pred_multi, digits=4, zero_division=0))
    else:
        print("=== 多分类验证 ===")
        print("验证集里没有正关系样本，跳过关系类型报告。")

    y_all_bin = [0 if y == NEGATIVE_LABEL else 1 for y in y_all]
    X_all_multi = [x for x, y in zip(X_all, y_all) if y != NEGATIVE_LABEL]
    y_all_multi = [y for y in y_all if y != NEGATIVE_LABEL]
    bin_clf.fit(X_all, y_all_bin)
    multi_clf.fit(X_all_multi, y_all_multi)

    joblib.dump(bin_clf, "relation_bin_clf.model")
    joblib.dump(multi_clf, "relation_multi_clf.model")

    print(f"关系模型训练完成，样本数: {len(X_all)}，关系标签数: {len(set(y_all_multi))}")
    print("已生成: relation_bin_clf.model, relation_multi_clf.model")


if __name__ == "__main__":
    main()
