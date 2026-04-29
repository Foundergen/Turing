import csv
import re
import urllib.parse

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD


BASE_URI = "http://www.semanticweb.org/turing-kg#"

RELATION_MAPPING = {
    "出生于": "bornIn",
    "国籍": "hasNationality",
    "就读于": "studiedAt",
    "毕业于": "graduatedFrom",
    "任职于": "workedAt",
    "师从": "studiedUnder",
    "合作": "collaboratedWith",
    "父亲": "hasFather",
    "母亲": "hasMother",
    "参与": "participatedIn",
    "参与破解": "participatedInCryptanalysis",
    "提出": "proposed",
    "研究": "researched",
    "撰写": "wrote",
    "发表": "published",
    "证明": "proved",
    "获得": "received",
    "设计": "designed",
    "改进": "improved",
    "开发": "developed",
    "聘请": "hired",
    "迫害": "persecuted",
    "誉为": "praisedAs",
    "当选院士": "electedFellowOf",
    "属于": "belongsTo",
    "设立": "established",
    "相关": "relatedTo",
}

TYPE_MAPPING = {
    "Person": "Person",
    "Organization": "Organization",
    "Location": "Location",
    "Event": "NamedEvent",
    "Machine": "Machine",
    "Concept": "Concept",
    "Book": "Book",
}


def uri_name(name: str) -> str:
    clean = re.sub(r"\s+", "_", name.strip())
    return urllib.parse.quote(clean, safe="")


def add_literal_if_present(graph, subject, predicate, value, datatype=None):
    value = str(value or "").strip()
    if not value:
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def add_entity(graph, ns, name, entity_type="", entity_subtype=""):
    if not name:
        return None
    entity_uri = URIRef(ns[uri_name(name)])
    graph.add((entity_uri, RDFS.label, Literal(name, lang="zh")))
    if entity_type:
        class_name = TYPE_MAPPING.get(entity_type, "Entity")
        graph.add((entity_uri, RDF.type, URIRef(ns[class_name])))
    else:
        graph.add((entity_uri, RDF.type, URIRef(ns["Entity"])))
    add_literal_if_present(graph, entity_uri, URIRef(ns["entitySubtype"]), entity_subtype)
    return entity_uri


def build_rdf_graph():
    print("正在构建实体、关系、事件 RDF 图谱...")

    graph = Graph()
    ns = Namespace(BASE_URI)
    graph.bind("turing", ns)

    entity_types = {}
    entity_subtypes = {}
    with open("core_entities_auto.csv", "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("实体名称", "").strip()
            entity_type = row.get("实体类型", "").strip()
            entity_subtype = row.get("实体子类型", "").strip()
            if name:
                entity_types[name] = entity_type
                entity_subtypes[name] = entity_subtype
                add_entity(graph, ns, name, entity_type, entity_subtype)

    triple_count = 0
    with open("turing_triples_core.csv", "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            head = row.get("头实体", "").strip()
            relation = row.get("关系", "").strip()
            tail = row.get("尾实体", "").strip()
            if not head or not relation or not tail:
                continue
            predicate_name = RELATION_MAPPING.get(relation, uri_name(relation))
            head_uri = add_entity(graph, ns, head, entity_types.get(head, ""), entity_subtypes.get(head, ""))
            tail_uri = add_entity(graph, ns, tail, entity_types.get(tail, ""), entity_subtypes.get(tail, ""))
            graph.add((head_uri, URIRef(ns[predicate_name]), tail_uri))
            triple_count += 1

    event_count = 0
    with open("turing_events_core.csv", "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            event_id = row.get("event_id", "").strip()
            if not event_id:
                continue
            event_uri = URIRef(ns[uri_name(event_id)])
            graph.add((event_uri, RDF.type, URIRef(ns["Event"])))
            graph.add((event_uri, RDFS.label, Literal(f"{row.get('event_type', '')}:{event_id}", lang="zh")))
            add_literal_if_present(graph, event_uri, URIRef(ns["eventType"]), row.get("event_type"))
            add_literal_if_present(graph, event_uri, URIRef(ns["trigger"]), row.get("trigger"))
            add_literal_if_present(graph, event_uri, URIRef(ns["time"]), row.get("time"))
            add_literal_if_present(graph, event_uri, URIRef(ns["cause"]), row.get("cause"))
            add_literal_if_present(graph, event_uri, URIRef(ns["result"]), row.get("result"))
            add_literal_if_present(graph, event_uri, URIRef(ns["confidence"]), row.get("confidence"), XSD.decimal)
            add_literal_if_present(graph, event_uri, URIRef(ns["evidenceSentence"]), row.get("evidence_sentence"))

            subject = row.get("subject", "").strip()
            location = row.get("location", "").strip()
            obj = row.get("object", "").strip()
            participants = [p.strip() for p in row.get("participants", "").split("；") if p.strip()]

            for predicate, value in (
                ("hasSubject", subject),
                ("hasLocation", location),
                ("hasObject", obj),
            ):
                value_uri = add_entity(graph, ns, value, entity_types.get(value, ""), entity_subtypes.get(value, ""))
                if value_uri:
                    graph.add((event_uri, URIRef(ns[predicate]), value_uri))
            for participant in participants:
                participant_uri = add_entity(graph, ns, participant, entity_types.get(participant, ""), entity_subtypes.get(participant, ""))
                if participant_uri:
                    graph.add((event_uri, URIRef(ns["hasParticipant"]), participant_uri))
            previous_event = row.get("previous_event", "").strip()
            next_event = row.get("next_event", "").strip()
            if previous_event:
                graph.add((event_uri, URIRef(ns["afterEvent"]), URIRef(ns[uri_name(previous_event)])))
            if next_event:
                graph.add((event_uri, URIRef(ns["beforeEvent"]), URIRef(ns[uri_name(next_event)])))
            event_count += 1

    output_file = "turing_instances.ttl"
    graph.serialize(destination=output_file, format="turtle")

    print(f"已写入实体 {len(entity_types)} 个、核心关系 {triple_count} 条、核心事件 {event_count} 个。")
    print(f"已生成 RDF 文件：{output_file}")


if __name__ == "__main__":
    build_rdf_graph()
