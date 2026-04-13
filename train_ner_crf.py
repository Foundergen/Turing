import csv
import re
import sys

try:
    import joblib
except ImportError:  # 兼容无 joblib 环境
    import pickle

    class _JoblibCompat:
        @staticmethod
        def dump(obj, path):
            with open(path, "wb") as f:
                pickle.dump(obj, f)

    joblib = _JoblibCompat()

try:
    import sklearn_crfsuite
except ImportError:
    sklearn_crfsuite = None

try:
    from sklearn.metrics import classification_report, precision_recall_fscore_support
    from sklearn.model_selection import train_test_split
except ImportError:
    classification_report = None
    precision_recall_fscore_support = None
    train_test_split = None


def read_entity_dict(path="core_entities_auto.csv", min_confidence=0.9):
    type_thresholds = {
        "Person": max(min_confidence, 0.90),
        "Organization": max(min_confidence, 0.88),
        "Location": max(min_confidence, 0.85),
        "Event": max(min_confidence, 0.80),
        "Machine": max(min_confidence, 0.80),
        "Concept": max(min_confidence, 0.90),
        "Book": max(min_confidence, 0.85),
    }
    entities = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        confidence_enabled = "置信度" in (reader.fieldnames or [])
        filtered_out = 0
        filtered_by_type = {}
        for row in reader:
            name = (row.get("实体名称") or "").strip()
            typ = (row.get("实体类型") or "").strip()
            if not (name and typ):
                continue
            if confidence_enabled:
                try:
                    conf = float((row.get("置信度") or "0").strip())
                except ValueError:
                    conf = 0.0
                threshold = type_thresholds.get(typ, min_confidence)
                if conf < threshold:
                    filtered_out += 1
                    filtered_by_type[typ] = filtered_by_type.get(typ, 0) + 1
                    continue
            entities.append((name, typ))
    entities.sort(key=lambda x: len(x[0]), reverse=True)
    if not entities:
        raise RuntimeError(f"实体词典为空或全部低于置信度阈值: {path}")
    if confidence_enabled:
        dropped_detail = ", ".join(f"{k}:{v}" for k, v in sorted(filtered_by_type.items()))
        print(
            f"已加载实体词典: {path}，置信度阈值={min_confidence:.2f}，"
            f"保留 {len(entities)} 条，过滤 {filtered_out} 条"
        )
        if dropped_detail:
            print(f"按类型过滤明细: {dropped_detail}")
    else:
        print(f"已加载实体词典: {path}（无置信度列），共 {len(entities)} 条")
    return entities


def split_sentences(text):
    return [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]


def get_char(chars, idx, default):
    return chars[idx] if 0 <= idx < len(chars) else default


def char_features(chars, i):
    ch = chars[i]
    prev = get_char(chars, i - 1, "<BOS>")
    prev2 = get_char(chars, i - 2, "<BOS2>")
    next_ = get_char(chars, i + 1, "<EOS>")
    next2 = get_char(chars, i + 2, "<EOS2>")
    return {
        "bias": 1.0,
        "ch": ch,
        "is_digit": ch.isdigit(),
        "is_alpha": ch.isalpha(),
        "is_cjk": "\u4e00" <= ch <= "\u9fff",
        "prev": prev,
        "prev2": prev2,
        "next": next_,
        "next2": next2,
        "prev_ch": f"{prev}|{ch}",
        "ch_next": f"{ch}|{next_}",
        "prev2_prev": f"{prev2}|{prev}",
        "next_next2": f"{next_}|{next2}",
    }


def sentence_to_features(sentence):
    chars = list(sentence)
    return [char_features(chars, i) for i in range(len(chars))]


def annotate_sentence(sentence, entities):
    tags = ["O"] * len(sentence)
    for name, typ in entities:
        # 用 finditer 命中同一实体在句中的所有出现位置
        for match in re.finditer(re.escape(name), sentence):
            start = match.start()
            end = match.end()
            # 如果这一段已被标注，跳过，避免覆盖长实体
            if not any(t != "O" for t in tags[start:end]):
                tags[start] = f"B-{typ}"
                for i in range(start + 1, end):
                    tags[i] = f"I-{typ}"
    return tags


def is_low_information_sentence(sentence):
    if len(sentence) > 120:
        return True
    # 低信息句（标点/数字比例过高）作为弱监督噪声过滤
    punct_or_digit = sum(1 for ch in sentence if not ("\u4e00" <= ch <= "\u9fff" or ch.isalpha()))
    return (punct_or_digit / max(len(sentence), 1)) > 0.45


def build_training_data(text, entities):
    X, y = [], []
    neg_X, neg_y = [], []
    for sent in split_sentences(text):
        if is_low_information_sentence(sent):
            continue
        feats = sentence_to_features(sent)
        tags = annotate_sentence(sent, entities)
        if any(t != "O" for t in tags):
            X.append(feats)
            y.append(tags)
        elif 8 <= len(sent) <= 60:
            # 采样难负样本，缓解模型“见词即实体”的偏置
            neg_X.append(feats)
            neg_y.append(tags)

    if not X:
        return X, y

    max_neg = max(10, len(X) // 2)
    X.extend(neg_X[:max_neg])
    y.extend(neg_y[:max_neg])
    return X, y


def flatten_tags(tag_sequences):
    return [tag for seq in tag_sequences for tag in seq]


def main():
    if sklearn_crfsuite is None or train_test_split is None or precision_recall_fscore_support is None:
        raise RuntimeError(
            "缺少依赖 sklearn-crfsuite/scikit-learn，请在当前解释器中安装: "
            "python -m pip install sklearn-crfsuite scikit-learn joblib"
        )

    with open("turing_corpus_clean.txt", "r", encoding="utf-8") as f:
        text = f.read()
    entity_dict_path = sys.argv[1] if len(sys.argv) > 1 else "core_entities_auto.csv"
    min_confidence = float(sys.argv[2]) if len(sys.argv) > 2 else 0.9
    try:
        entities = read_entity_dict(entity_dict_path, min_confidence=min_confidence)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"{e}\n未找到训练词典。默认读取 core_entities_auto.csv，"
            "也可运行: python train_ner_crf.py <你的词典路径> [置信度阈值]"
        ) from e

    X_data, y_data = build_training_data(text, entities)
    if not X_data:
        raise RuntimeError("未构造出 CRF 训练样本，请检查语料和实体词典。")

    if len(X_data) < 2:
        raise RuntimeError("训练样本不足 2 句，无法切分验证集；请扩充语料或实体词典。")

    test_size = 0.2 if len(X_data) >= 10 else 0.3
    if len(X_data) <= 3:
        test_size = 1 / len(X_data)
    X_train, X_valid, y_train, y_valid = train_test_split(X_data, y_data, test_size=test_size, random_state=42, shuffle=True)

    model = sklearn_crfsuite.CRF(
        algorithm="lbfgs",
        c1=0.1,
        c2=0.1,
        max_iterations=100,
        all_possible_transitions=True,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_valid)

    y_true_flat = flatten_tags(y_valid)
    y_pred_flat = flatten_tags(y_pred)

    p, r, f1, _ = precision_recall_fscore_support(
        y_true_flat, y_pred_flat, average="micro", zero_division=0
    )
    labels = sorted(set(tag for tag in y_true_flat if tag != "O"))
    print(
        f"验证集 token-level: Precision={p:.4f} Recall={r:.4f} F1={f1:.4f} "
        f"(train={len(X_train)}, valid={len(X_valid)})"
    )
    if labels:
        print("验证集标签报告（排除 O）：")
        print(classification_report(y_true_flat, y_pred_flat, labels=labels, zero_division=0, digits=4))
    else:
        print("验证集中未出现实体标签，已跳过标签级报告。")

    # 评估后使用全量数据再训练一次，保证导出的模型可用于下游流程
    model.fit(X_data, y_data)
    joblib.dump(model, "ner_crf.model")

    print(f"CRF 训练完成，样本句数: {len(X_data)}")
    print("已生成: ner_crf.model")


if __name__ == "__main__":
    main()
