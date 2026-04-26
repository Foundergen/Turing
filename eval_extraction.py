"""
从自动产物与语料计算可复现的「质量/可靠度」指标。
数值表示系统自检与多源一致性，非真实 F1。
"""

import csv
import statistics
from pathlib import Path


def load_entity_rows(path="core_entities_auto.csv"):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def load_triple_audit(path="turing_triples_auto_audit.csv"):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def load_rows(path):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def corpus_hit_rate(names, corpus_path="turing_corpus_clean.txt"):
    text = Path(corpus_path).read_text(encoding="utf-8")
    hits = sum(1 for n in names if n and n in text)
    return hits / len(names) if names else 0.0


def eval_entities(rows):
    if not rows:
        return {}
    confs = []
    multi_src = 0
    model_src = 0
    high_certainty = 0  # 与旧「建议复核=否」同判据：置信≥0.68 且含 spaCy/CRF
    book_only_rule = 0
    by_type = {}
    by_subtype = {}
    for row in rows:
        src = row.get("来源", "")
        try:
            c = float(row.get("置信度", "0") or 0)
        except ValueError:
            c = 0.0
        confs.append(c)
        if "+" in src:
            multi_src += 1
        if "spacy" in src or "crf" in src:
            model_src += 1
        if c >= 0.68 and ("spacy" in src or "crf" in src):
            high_certainty += 1
        if src.strip() == "rule" and row.get("实体类型", "") == "Book":
            book_only_rule += 1
        typ = row.get("实体类型", "unknown")
        subtype = row.get("实体子类型", "")
        by_type[typ] = by_type.get(typ, 0) + 1
        if subtype:
            by_subtype[subtype] = by_subtype.get(subtype, 0) + 1

    n = len(rows)
    return {
        "条数": n,
        "平均置信度": round(statistics.mean(confs), 4) if confs else 0.0,
        "多来源占比": round(multi_src / n, 4),
        "含模型来源占比": round(model_src / n, 4),
        "高确定占比_置信且含模型": round(high_certainty / n, 4),
        "纯规则书名条数": book_only_rule,
        "按主类型计数": dict(sorted(by_type.items())),
        "按子类型计数": dict(sorted(by_subtype.items())),
        "语料字面命中率": None,
    }


def eval_triples(rows):
    if not rows:
        return {}
    by_src = {}
    confs_all = []
    specific_rel = 0
    no_review = 0
    for row in rows:
        src = row.get("来源", "unknown")
        try:
            c = float(row.get("置信度", "0") or 0)
        except ValueError:
            c = 0.0
        confs_all.append(c)
        by_src.setdefault(src, []).append(c)
        if row.get("关系", "").strip() != "相关":
            specific_rel += 1
        if row.get("建议人工复核", "").strip() == "否":
            no_review += 1

    n = len(rows)
    per_src_mean = {k: round(statistics.mean(v), 4) for k, v in by_src.items()}
    return {
        "条数": n,
        "平均置信度": round(statistics.mean(confs_all), 4) if confs_all else 0.0,
        "非相关关系占比": round(specific_rel / n, 4),
        "免检占比_建议复核为否": round(no_review / n, 4),
        "按来源平均置信度": per_src_mean,
    }


def eval_events(rows):
    if not rows:
        return {}
    confs = []
    no_review = 0
    with_time = 0
    with_object = 0
    with_location = 0
    with_cause_or_result = 0
    by_type = {}
    by_source = {}
    for row in rows:
        try:
            c = float(row.get("confidence", "0") or 0)
        except ValueError:
            c = 0.0
        confs.append(c)
        if row.get("review_flag", "").strip() == "否":
            no_review += 1
        if row.get("time", "").strip():
            with_time += 1
        if row.get("object", "").strip():
            with_object += 1
        if row.get("location", "").strip():
            with_location += 1
        if row.get("cause", "").strip() or row.get("result", "").strip():
            with_cause_or_result += 1
        by_type[row.get("event_type", "unknown")] = by_type.get(row.get("event_type", "unknown"), 0) + 1
        by_source[row.get("source", "unknown")] = by_source.get(row.get("source", "unknown"), 0) + 1
    n = len(rows)
    return {
        "条数": n,
        "平均置信度": round(statistics.mean(confs), 4) if confs else 0.0,
        "免检占比_建议复核为否": round(no_review / n, 4),
        "含时间占比": round(with_time / n, 4),
        "含客体占比": round(with_object / n, 4),
        "含地点机构占比": round(with_location / n, 4),
        "含原因或结果占比": round(with_cause_or_result / n, 4),
        "按事件类型计数": dict(sorted(by_type.items())),
        "按来源计数": dict(sorted(by_source.items())),
    }


def composite_entity_score(m):
    if not m or m.get("条数", 0) == 0:
        return 0.0
    return round(
        100
        * (
            0.35 * m["平均置信度"]
            + 0.25 * m["多来源占比"]
            + 0.25 * m["含模型来源占比"]
            + 0.15 * m["高确定占比_置信且含模型"]
        ),
        2,
    )


def composite_triple_score(m):
    if not m or m.get("条数", 0) == 0:
        return 0.0
    spec = m["非相关关系占比"]
    rev = m["免检占比_建议复核为否"]
    conf = m["平均置信度"]
    return round(100 * (0.4 * conf + 0.35 * spec + 0.25 * rev), 2)


def composite_event_score(m):
    if not m or m.get("条数", 0) == 0:
        return 0.0
    return round(
        100
        * (
            0.35 * m["平均置信度"]
            + 0.25 * m["免检占比_建议复核为否"]
            + 0.15 * m["含时间占比"]
            + 0.15 * m["含客体占比"]
            + 0.10 * m["含地点机构占比"]
        ),
        2,
    )


def main():
    ent_rows = load_entity_rows()
    tri_rows = load_triple_audit()
    tri_core_rows = load_rows("turing_triples_core.csv")
    event_rows = load_rows("turing_events_auto_audit.csv")
    event_core_rows = load_rows("turing_events_core.csv")

    em = eval_entities(ent_rows)
    if ent_rows:
        names = [r.get("实体名称", "").strip() for r in ent_rows]
        em["语料字面命中率"] = round(corpus_hit_rate(names), 4)

    tm = eval_triples(tri_rows)
    evm = eval_events(event_rows)
    evcm = eval_events(event_core_rows)

    print("=== 实体（core_entities_auto.csv）===")
    for k, v in em.items():
        print(f"  {k}: {v}")
    print(f"  综合可靠度指数(0-100): {composite_entity_score(em)}")
    print("  （说明：由置信度、多来源、模型参与、高确定比例加权，非人工准确率）")

    print()
    print("=== 关系（turing_triples_auto_audit.csv）===")
    for k, v in tm.items():
        print(f"  {k}: {v}")
    print(f"  综合可靠度指数(0-100): {composite_triple_score(tm)}")
    print("  （说明：由置信度、具体关系占比、免检比例加权）")
    if tri_rows:
        print(f"  核心版占审核版比例: {round(len(tri_core_rows) / len(tri_rows), 4)}")

    print()
    print("=== 事件审核版（turing_events_auto_audit.csv）===")
    for k, v in evm.items():
        print(f"  {k}: {v}")
    print(f"  综合可靠度指数(0-100): {composite_event_score(evm)}")
    print("  （说明：由置信度、免检比例、时间/客体/地点完整度加权）")

    print()
    print("=== 事件核心版（turing_events_core.csv）===")
    for k, v in evcm.items():
        print(f"  {k}: {v}")
    print(f"  综合可靠度指数(0-100): {composite_event_score(evcm)}")
    if event_rows:
        print(f"  核心版占审核版比例: {round(len(event_core_rows) / len(event_rows), 4)}")


if __name__ == "__main__":
    main()
