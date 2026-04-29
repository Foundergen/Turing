import csv
import html
import json
import re
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENTITY_PATH = BASE_DIR / "core_entities_auto.csv"
TRIPLE_PATH = BASE_DIR / "turing_triples_core.csv"
EVENT_PATH = BASE_DIR / "turing_events_core.csv"
OUTPUT_PATH = BASE_DIR / "kg_dashboard.html"


TYPE_COLORS = {
    "Person": "#3b82f6",
    "Organization": "#14b8a6",
    "Location": "#22c55e",
    "Book": "#f97316",
    "Concept": "#8b5cf6",
    "Machine": "#ef4444",
    "Event": "#64748b",
    "Unknown": "#6b7280",
}

EVENT_COLORS = {
    "出生事件": "#3b82f6",
    "教育事件": "#14b8a6",
    "发表事件": "#f97316",
    "密码破译事件": "#ef4444",
    "法律迫害事件": "#8b5cf6",
    "任职事件": "#0ea5e9",
    "获奖荣誉事件": "#eab308",
    "设计开发事件": "#10b981",
    "研究事件": "#6366f1",
    "死亡事件": "#64748b",
}


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def year_from_text(value):
    match = re.search(r"(\d{4})", value or "")
    return int(match.group(1)) if match else 9999


def pct(value, total):
    if not total:
        return 0
    return round(value * 100 / total, 1)


def build_dashboard_data():
    entities = read_csv(ENTITY_PATH)
    triples = read_csv(TRIPLE_PATH)
    events = read_csv(EVENT_PATH)

    entity_info = {}
    for row in entities:
        name = row.get("实体名称", "").strip()
        if not name:
            continue
        entity_info[name] = {
            "name": name,
            "type": row.get("实体类型", "Unknown").strip() or "Unknown",
            "subtype": row.get("实体子类型", "").strip(),
            "confidence": row.get("置信度", "").strip(),
            "source": row.get("来源", "").strip(),
        }

    degree = Counter()
    for row in triples:
        head = row.get("头实体", "").strip()
        tail = row.get("尾实体", "").strip()
        if head and tail:
            degree[head] += 1
            degree[tail] += 1

    nodes = []
    edge_names = set()
    for row in triples:
        for key in ("头实体", "尾实体"):
            name = row.get(key, "").strip()
            if name and name not in edge_names:
                edge_names.add(name)
                info = entity_info.get(name, {"type": "Unknown", "subtype": ""})
                nodes.append({
                    "id": name,
                    "label": name,
                    "type": info.get("type", "Unknown"),
                    "subtype": info.get("subtype", ""),
                    "degree": degree.get(name, 1),
                    "color": TYPE_COLORS.get(info.get("type", "Unknown"), TYPE_COLORS["Unknown"]),
                })

    links = []
    for row in triples:
        head = row.get("头实体", "").strip()
        tail = row.get("尾实体", "").strip()
        relation = row.get("关系", "").strip()
        if head and tail and relation:
            links.append({
                "source": head,
                "target": tail,
                "relation": relation,
                "confidence": row.get("置信度", ""),
                "evidence": row.get("证据句", ""),
            })

    event_rows = []
    for row in events:
        event_rows.append({
            "event_id": row.get("event_id", ""),
            "event_type": row.get("event_type", ""),
            "trigger": row.get("trigger", ""),
            "subject": row.get("subject", ""),
            "time": row.get("time", ""),
            "year": year_from_text(row.get("time", "")),
            "location": row.get("location", ""),
            "object": row.get("object", ""),
            "participants": row.get("participants", ""),
            "cause": row.get("cause", ""),
            "result": row.get("result", ""),
            "confidence": row.get("confidence", ""),
            "evidence_sentence": row.get("evidence_sentence", ""),
            "color": EVENT_COLORS.get(row.get("event_type", ""), "#64748b"),
        })
    event_rows.sort(key=lambda x: (x["year"], x["event_id"]))

    entity_type_counts = Counter(row.get("实体类型", "Unknown") or "Unknown" for row in entities)
    entity_subtype_counts = Counter(row.get("实体子类型", "") for row in entities if row.get("实体子类型", ""))
    relation_counts = Counter(row.get("关系", "") for row in triples if row.get("关系", ""))
    event_type_counts = Counter(row.get("event_type", "") for row in events if row.get("event_type", ""))

    return {
        "summary": {
            "entity_count": len(entities),
            "triple_count": len(triples),
            "event_count": len(events),
            "event_time_pct": pct(sum(1 for e in events if e.get("time")), len(events)),
        },
        "entities": entities,
        "triples": triples,
        "events": event_rows,
        "nodes": nodes,
        "links": links,
        "stats": {
            "entity_types": entity_type_counts.most_common(),
            "entity_subtypes": entity_subtype_counts.most_common(),
            "relations": relation_counts.most_common(),
            "event_types": event_type_counts.most_common(),
        },
    }


def render_html(data):
    data_json = json.dumps(data, ensure_ascii=False)
    escaped_json = html.escape(data_json, quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>图灵知识图谱可视化</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #dbe3ef;
      --accent: #2563eb;
      --shadow: 0 12px 30px rgba(15, 23, 42, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    header {{
      padding: 28px 40px 18px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0 0 12px; font-size: 28px; font-weight: 700; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 12px;
      max-width: 1180px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: #fbfdff;
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .metric strong {{ display: block; font-size: 24px; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 22px 22px 40px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
      padding: 18px;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    select, input {{
      height: 34px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 0 10px;
      background: #ffffff;
      color: var(--text);
    }}
    button {{
      height: 34px;
      border: 1px solid #bfdbfe;
      border-radius: 6px;
      background: #eff6ff;
      color: #1d4ed8;
      cursor: pointer;
    }}
    #graph {{
      width: 100%;
      height: 620px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
      overflow: hidden;
    }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 13px; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }}
    .timeline {{
      position: relative;
      padding-left: 18px;
      border-left: 3px solid #dbeafe;
    }}
    .search-box {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .search-box input {{
      width: 100%;
      height: 38px;
    }}
    .search-results {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .result-group {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
      overflow: hidden;
    }}
    .result-group h3 {{
      margin: 0;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      background: #f8fafc;
      font-size: 15px;
    }}
    .result-list {{
      max-height: 280px;
      overflow: auto;
    }}
    .result-item {{
      padding: 10px 12px;
      border-bottom: 1px solid #e2e8f0;
      line-height: 1.55;
      font-size: 13px;
    }}
    .result-item:last-child {{ border-bottom: 0; }}
    .result-title {{ font-weight: 700; }}
    .result-meta {{ color: var(--muted); margin-top: 3px; }}
    .event {{
      position: relative;
      padding: 0 0 16px 18px;
    }}
    .event::before {{
      content: "";
      position: absolute;
      left: -28px;
      top: 4px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--event-color);
      border: 3px solid #ffffff;
      box-shadow: 0 0 0 1px var(--line);
    }}
    .event-title {{ font-weight: 700; }}
    .event-meta {{ color: var(--muted); font-size: 13px; margin: 4px 0; }}
    .event-sentence {{ line-height: 1.7; }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px 1fr 42px;
      gap: 10px;
      align-items: center;
      margin: 8px 0;
      font-size: 13px;
    }}
    .bar-name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ height: 10px; background: #e2e8f0; border-radius: 99px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--accent); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #e2e8f0;
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #f8fafc; position: sticky; top: 0; }}
    .table-wrap {{ max-height: 420px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }}
    .muted {{ color: var(--muted); }}
    .tip {{
      position: fixed;
      display: none;
      max-width: 360px;
      padding: 10px 12px;
      background: rgba(15, 23, 42, .94);
      color: #ffffff;
      border-radius: 6px;
      font-size: 13px;
      pointer-events: none;
      z-index: 10;
      line-height: 1.5;
    }}
    @media (max-width: 820px) {{
      header {{ padding: 22px 18px; }}
      .summary, .stats-grid, .search-results {{ grid-template-columns: 1fr; }}
      .search-box {{ grid-template-columns: 1fr; }}
      main {{ padding: 16px; }}
      #graph {{ height: 520px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>图灵知识图谱可视化</h1>
    <div class="summary" id="summary"></div>
  </header>
  <main>
    <section>
      <h2>知识搜索</h2>
      <div class="search-box">
        <input id="kgSearchInput" type="search" placeholder="输入实体、关系、事件类型、年份或证据句关键词，例如：图灵测试、迫害、1939">
        <button id="kgSearchButton">搜索</button>
      </div>
      <div class="search-results" id="kgSearchResults"></div>
    </section>

    <section>
      <h2>实体关系网络图</h2>
      <div class="toolbar">
        <label>实体类型 <select id="typeFilter"><option value="">全部</option></select></label>
        <label>关系类型 <select id="relationFilter"><option value="">全部</option></select></label>
        <button id="resetGraph">重置视图</button>
      </div>
      <div class="legend" id="legend"></div>
      <svg id="graph" role="img" aria-label="实体关系网络图"></svg>
    </section>

    <section>
      <h2>核心事件时间线</h2>
      <div class="toolbar">
        <label>事件类型 <select id="eventFilter"><option value="">全部</option></select></label>
      </div>
      <div class="timeline" id="timeline"></div>
    </section>

    <section>
      <h2>抽取结果统计</h2>
      <div class="stats-grid" id="stats"></div>
    </section>

    <section>
      <h2>核心三元组明细</h2>
      <div class="table-wrap">
        <table id="tripleTable"></table>
      </div>
    </section>
  </main>
  <div class="tip" id="tip"></div>
  <script id="kgData" type="application/json">{escaped_json}</script>
  <script>
    const data = JSON.parse(document.getElementById('kgData').textContent);
    const typeColors = {json.dumps(TYPE_COLORS, ensure_ascii=False)};
    const eventColors = {json.dumps(EVENT_COLORS, ensure_ascii=False)};
    const summary = document.getElementById('summary');
    const tip = document.getElementById('tip');

    function escapeText(value) {{
      return String(value ?? '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
    }}

    function fillSummary() {{
      const items = [
        ['实体数量', data.summary.entity_count],
        ['核心关系', data.summary.triple_count],
        ['核心事件', data.summary.event_count],
        ['事件含时间占比', data.summary.event_time_pct + '%'],
      ];
      summary.innerHTML = items.map(([label, value]) => `<div class="metric"><strong>${{value}}</strong><span>${{label}}</span></div>`).join('');
    }}

    function unique(values) {{
      return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
    }}

    function rowText(row) {{
      return Object.values(row).join(' ').toLowerCase();
    }}

    function resultGroup(title, rows, renderer) {{
      const body = rows.length
        ? rows.slice(0, 10).map(renderer).join('')
        : '<div class="result-item muted">没有匹配结果</div>';
      return `<div class="result-group"><h3>${{title}}（${{rows.length}}）</h3><div class="result-list">${{body}}</div></div>`;
    }}

    function renderSearch() {{
      const keyword = document.getElementById('kgSearchInput').value.trim().toLowerCase();
      const target = document.getElementById('kgSearchResults');
      if (!keyword) {{
        target.innerHTML = '<div class="result-group"><h3>提示</h3><div class="result-list"><div class="result-item muted">输入关键词后，可以同时检索实体、核心三元组和核心事件。</div></div></div>';
        return;
      }}
      const entityRows = data.entities.filter(row => rowText(row).toLowerCase().includes(keyword));
      const tripleRows = data.triples.filter(row => rowText(row).toLowerCase().includes(keyword));
      const eventRows = data.events.filter(row => rowText(row).toLowerCase().includes(keyword));
      target.innerHTML =
        resultGroup('实体', entityRows, row => `
          <div class="result-item">
            <div class="result-title">${{escapeText(row['实体名称'])}}</div>
            <div class="result-meta">类型：${{escapeText(row['实体类型'] || '未知')}} ｜ 子类型：${{escapeText(row['实体子类型'] || '无')}} ｜ 置信度：${{escapeText(row['置信度'] || '')}}</div>
          </div>`) +
        resultGroup('关系', tripleRows, row => `
          <div class="result-item">
            <div class="result-title">${{escapeText(row['头实体'])}} → ${{escapeText(row['关系'])}} → ${{escapeText(row['尾实体'])}}</div>
            <div class="result-meta">置信度：${{escapeText(row['置信度'])}}</div>
            <div>${{escapeText(row['证据句'])}}</div>
          </div>`) +
        resultGroup('事件', eventRows, row => `
          <div class="result-item">
            <div class="result-title">${{escapeText(row.time || '时间未知')}} · ${{escapeText(row.event_type)}} · ${{escapeText(row.trigger)}}</div>
            <div class="result-meta">主体：${{escapeText(row.subject || '无')}} ｜ 客体：${{escapeText(row.object || '无')}} ｜ 地点/机构：${{escapeText(row.location || '无')}}</div>
            <div>${{escapeText(row.evidence_sentence)}}</div>
          </div>`);
    }}

    function fillFilters() {{
      const typeFilter = document.getElementById('typeFilter');
      unique(data.nodes.map(n => n.type)).forEach(v => typeFilter.add(new Option(v, v)));
      const relationFilter = document.getElementById('relationFilter');
      unique(data.links.map(e => e.relation)).forEach(v => relationFilter.add(new Option(v, v)));
      const eventFilter = document.getElementById('eventFilter');
      unique(data.events.map(e => e.event_type)).forEach(v => eventFilter.add(new Option(v, v)));
      document.getElementById('legend').innerHTML = Object.entries(typeColors)
        .filter(([k]) => data.nodes.some(n => n.type === k))
        .map(([k, c]) => `<span><i class="dot" style="background:${{c}}"></i>${{k}}</span>`).join('');
    }}

    function renderGraph() {{
      const svg = document.getElementById('graph');
      const width = svg.clientWidth || 1000;
      const height = svg.clientHeight || 620;
      const typeValue = document.getElementById('typeFilter').value;
      const relationValue = document.getElementById('relationFilter').value;
      let links = data.links.filter(e => !relationValue || e.relation === relationValue);
      let nodeIds = new Set(links.flatMap(e => [e.source, e.target]));
      let nodes = data.nodes.filter(n => nodeIds.has(n.id) && (!typeValue || n.type === typeValue));
      nodeIds = new Set(nodes.map(n => n.id));
      links = links.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

      const nodeMap = new Map(nodes.map((n, i) => [n.id, {{
        ...n,
        x: width / 2 + Math.cos(i * 2.399) * Math.min(width, height) * .28,
        y: height / 2 + Math.sin(i * 2.399) * Math.min(width, height) * .28,
        vx: 0,
        vy: 0,
      }}]));
      const simLinks = links.map(e => ({{...e, sourceNode: nodeMap.get(e.source), targetNode: nodeMap.get(e.target)}}));

      for (let tick = 0; tick < 260; tick++) {{
        for (const a of nodeMap.values()) {{
          for (const b of nodeMap.values()) {{
            if (a === b) continue;
            const dx = a.x - b.x;
            const dy = a.y - b.y;
            const dist2 = Math.max(dx * dx + dy * dy, 80);
            const force = 900 / dist2;
            a.vx += dx * force * .01;
            a.vy += dy * force * .01;
          }}
        }}
        for (const e of simLinks) {{
          const a = e.sourceNode, b = e.targetNode;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const wanted = 130;
          const force = (dist - wanted) * .012;
          const fx = dx / dist * force;
          const fy = dy / dist * force;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }}
        for (const n of nodeMap.values()) {{
          n.vx += (width / 2 - n.x) * .002;
          n.vy += (height / 2 - n.y) * .002;
          n.vx *= .82;
          n.vy *= .82;
          n.x = Math.max(36, Math.min(width - 36, n.x + n.vx));
          n.y = Math.max(36, Math.min(height - 36, n.y + n.vy));
        }}
      }}

      const drawableLinks = simLinks.map(e => {{
        const a = e.sourceNode, b = e.targetNode;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const sourceRadius = Math.min(24, 10 + a.degree * 2);
        const targetRadius = Math.min(24, 10 + b.degree * 2);
        return {{
          ...e,
          sx: a.x + dx / dist * (sourceRadius + 2),
          sy: a.y + dy / dist * (sourceRadius + 2),
          tx: b.x - dx / dist * (targetRadius + 8),
          ty: b.y - dy / dist * (targetRadius + 8),
        }};
      }});

      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `
        <defs>
          <marker id="arrow" markerWidth="14" markerHeight="14" refX="12" refY="4" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,8 L12,4 z" fill="#475569"></path>
          </marker>
        </defs>
        ${{drawableLinks.map(e => `<line x1="${{e.sx}}" y1="${{e.sy}}" x2="${{e.tx}}" y2="${{e.ty}}" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"></line>
          <text x="${{(e.sourceNode.x + e.targetNode.x) / 2}}" y="${{(e.sourceNode.y + e.targetNode.y) / 2 - 4}}" fill="#475569" font-size="12" text-anchor="middle">${{escapeText(e.relation)}}</text>`).join('')}}
        ${{[...nodeMap.values()].map(n => `<g class="node" data-name="${{escapeText(n.id)}}" data-type="${{escapeText(n.type)}}" data-subtype="${{escapeText(n.subtype)}}" transform="translate(${{n.x}},${{n.y}})">
          <circle r="${{Math.min(24, 10 + n.degree * 2)}}" fill="${{n.color}}" stroke="#fff" stroke-width="2"></circle>
          <text y="${{Math.min(36, 22 + n.degree * 2)}}" text-anchor="middle" font-size="12" fill="#0f172a">${{escapeText(n.label)}}</text>
        </g>`).join('')}}
      `;
      svg.querySelectorAll('.node').forEach(el => {{
        el.addEventListener('mousemove', ev => showTip(ev, `<b>${{el.dataset.name}}</b><br>类型：${{el.dataset.type}}<br>子类型：${{el.dataset.subtype || '无'}}`));
        el.addEventListener('mouseleave', hideTip);
      }});
    }}

    function showTip(ev, content) {{
      tip.innerHTML = content;
      tip.style.display = 'block';
      tip.style.left = Math.min(window.innerWidth - 380, ev.clientX + 14) + 'px';
      tip.style.top = (ev.clientY + 14) + 'px';
    }}

    function hideTip() {{
      tip.style.display = 'none';
    }}

    function renderTimeline() {{
      const filter = document.getElementById('eventFilter').value;
      const rows = data.events.filter(e => !filter || e.event_type === filter);
      const datedRows = rows.filter(e => e.year !== 9999);
      const undatedRows = rows.filter(e => e.year === 9999);
      const renderRows = items => items.map(e => `
        <div class="event" style="--event-color:${{e.color}}">
          <div class="event-title">${{escapeText(e.time || '时间未知')}} · ${{escapeText(e.event_type)}} · ${{escapeText(e.trigger)}}</div>
          <div class="event-meta">主体：${{escapeText(e.subject || '无')}} ｜ 地点/机构：${{escapeText(e.location || '无')}} ｜ 客体：${{escapeText(e.object || '无')}} ｜ 置信度：${{escapeText(e.confidence)}}</div>
          <div class="event-sentence">${{escapeText(e.evidence_sentence)}}</div>
        </div>`).join('');
      document.getElementById('timeline').innerHTML =
        renderRows(datedRows) +
        (undatedRows.length ? `<h3 class="muted">未明确时间事件</h3>${{renderRows(undatedRows)}}` : '');
    }}

    function renderStatsBlock(title, rows, color) {{
      const max = Math.max(1, ...rows.map(r => r[1]));
      return `<div><h3>${{title}}</h3>${{rows.map(([name, count]) => `
        <div class="bar-row">
          <div class="bar-name" title="${{escapeText(name)}}">${{escapeText(name)}}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${{count * 100 / max}}%;background:${{color}}"></div></div>
          <div>${{count}}</div>
        </div>`).join('')}}</div>`;
    }}

    function renderStats() {{
      document.getElementById('stats').innerHTML =
        renderStatsBlock('实体主类型', data.stats.entity_types, '#2563eb') +
        renderStatsBlock('实体子类型', data.stats.entity_subtypes.slice(0, 12), '#14b8a6') +
        renderStatsBlock('关系类型', data.stats.relations, '#f97316') +
        renderStatsBlock('事件类型', data.stats.event_types, '#8b5cf6');
    }}

    function renderTripleTable() {{
      const rows = data.triples;
      document.getElementById('tripleTable').innerHTML = `
        <thead><tr><th>头实体</th><th>关系</th><th>尾实体</th><th>置信度</th><th>证据句</th></tr></thead>
        <tbody>${{rows.map(r => `<tr>
          <td>${{escapeText(r['头实体'])}}</td>
          <td>${{escapeText(r['关系'])}}</td>
          <td>${{escapeText(r['尾实体'])}}</td>
          <td>${{escapeText(r['置信度'])}}</td>
          <td>${{escapeText(r['证据句'])}}</td>
        </tr>`).join('')}}</tbody>`;
    }}

    fillSummary();
    fillFilters();
    renderSearch();
    renderGraph();
    renderTimeline();
    renderStats();
    renderTripleTable();
    document.getElementById('kgSearchButton').addEventListener('click', renderSearch);
    document.getElementById('kgSearchInput').addEventListener('keydown', event => {{
      if (event.key === 'Enter') {{
        renderSearch();
      }}
    }});
    document.getElementById('kgSearchInput').addEventListener('input', event => {{
      if (!event.target.value.trim()) {{
        renderSearch();
      }}
    }});
    document.getElementById('typeFilter').addEventListener('change', renderGraph);
    document.getElementById('relationFilter').addEventListener('change', renderGraph);
    document.getElementById('eventFilter').addEventListener('change', renderTimeline);
    document.getElementById('resetGraph').addEventListener('click', () => {{
      document.getElementById('typeFilter').value = '';
      document.getElementById('relationFilter').value = '';
      renderGraph();
    }});
    window.addEventListener('resize', renderGraph);
  </script>
</body>
</html>"""


def main():
    data = build_dashboard_data()
    OUTPUT_PATH.write_text(render_html(data), encoding="utf-8")
    print(f"已生成可视化页面：{OUTPUT_PATH}")
    print(
        f"实体 {data['summary']['entity_count']} 条，"
        f"核心关系 {data['summary']['triple_count']} 条，"
        f"核心事件 {data['summary']['event_count']} 条。"
    )


if __name__ == "__main__":
    main()
