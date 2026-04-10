import csv
import re

import joblib
import sklearn_crfsuite


def read_entity_dict(path="core_entities.csv"):
    entities = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                entities.append((row[0].strip(), row[1].strip()))
    entities.sort(key=lambda x: len(x[0]), reverse=True)
    return entities


def split_sentences(text):
    return [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]


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


def annotate_sentence(sentence, entities):
    tags = ["O"] * len(sentence)
    for name, typ in entities:
        start = sentence.find(name)
        if start == -1:
            continue
        end = start + len(name)
        if end > len(sentence):
            continue
        # 如果这一段已被标注，跳过，避免覆盖长实体
        if any(t != "O" for t in tags[start:end]):
            continue
        tags[start] = f"B-{typ}"
        for i in range(start + 1, end):
            tags[i] = f"I-{typ}"
    return tags


def build_training_data(text, entities):
    X, y = [], []
    for sent in split_sentences(text):
        feats = sentence_to_features(sent)
        tags = annotate_sentence(sent, entities)
        if any(t != "O" for t in tags):
            X.append(feats)
            y.append(tags)
    return X, y


def main():
    with open("turing_corpus_clean.txt", "r", encoding="utf-8") as f:
        text = f.read()
    entities = read_entity_dict("core_entities.csv")

    X_train, y_train = build_training_data(text, entities)
    if not X_train:
        raise RuntimeError("未构造出 CRF 训练样本，请检查语料和实体词典。")

    model = sklearn_crfsuite.CRF(
        algorithm="lbfgs",
        c1=0.1,
        c2=0.1,
        max_iterations=100,
        all_possible_transitions=True,
    )
    model.fit(X_train, y_train)
    joblib.dump(model, "ner_crf.model")

    print(f"CRF 训练完成，样本句数: {len(X_train)}")
    print("已生成: ner_crf.model")


if __name__ == "__main__":
    main()
