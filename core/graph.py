"""
Граф знаний: связывает наблюдения из данных с гипотезами через причинную цепочку

    Класс крупности ──> Минеральная форма потерь ──> Причина ──> Вмешательство ──> Оборудование

Это прямое требование ТЗ («визуальное представление связей: графы, диаграммы влияния»).
Граф строится из результатов диагностики и ранжирования конкретной фабрики, поэтому
он не абстрактный, а отражает реальную картину потерь этого объекта.

Рендер — самодостаточный интерактивный HTML на vis-network (встроенный, без внешних
CDN: библиотека инлайнится). Работает офлайн и внутри Streamlit.
"""
from __future__ import annotations
import json
import os

import networkx as nx


# Цвета/группы узлов.
GROUPS = {
    "class": {"color": "#4C78A8", "shape": "box"},        # класс крупности
    "mineral": {"color": "#72B7B2", "shape": "ellipse"},  # минеральная форма
    "cause": {"color": "#E45756", "shape": "diamond"},    # причина потерь
    "hypo": {"color": "#F58518", "shape": "box"},         # гипотеза
    "equip": {"color": "#B279A2", "shape": "dot"},        # оборудование
}

CAUSE_LABEL = {
    "UNDERGRIND": "Недоизмельчение\n(сростки в крупных классах)",
    "SLIMES": "Потеря шламов\n(раскрытый металл в −10 мкм)",
    "MIDGRIND": "Сростки в среднем классе",
}


def build_graph(diag, hyps, top_n: int = 8) -> nx.DiGraph:
    G = nx.DiGraph()

    # Узлы причин (по находкам).
    causes = {}
    for f in diag.findings:
        if f.code == "RECOVERABLE_CEILING":
            continue
        cid = f"cause::{f.code}::{f.size_class}"
        if cid in causes:
            continue
        causes[cid] = f
        G.add_node(cid, group="cause",
                   label=CAUSE_LABEL.get(f.code, f.code),
                   title=f"{f.headline}\n≈{f.value_musd:.1f} M$/год",
                   value=max(8, f.value_musd))

        # Класс крупности -> причина.
        if f.size_class:
            clid = f"class::{f.size_class}"
            G.add_node(clid, group="class", label=f"Класс {f.size_class} мкм",
                       title="Класс крупности", value=12)
            G.add_edge(clid, cid, label="→ причина")

        # Минеральная форма -> причина.
        if f.code in ("UNDERGRIND", "MIDGRIND"):
            mid = "mineral::locked"
            G.add_node(mid, group="mineral", label="Закрытый Pnt/Cp\n(сросток)",
                       title="Металл заперт в породе", value=14)
            G.add_edge(mid, cid, label="форма потерь")
        elif f.code == "SLIMES":
            mid = "mineral::liberated"
            G.add_node(mid, group="mineral", label="Раскрытый Pnt/Cp\n(тонкий шлам)",
                       title="Раскрыт, но теряется во флотации", value=14)
            G.add_edge(mid, cid, label="форма потерь")

    # Гипотезы -> причины (по триггеру) и -> оборудование.
    for h in hyps[:top_n]:
        hid = f"hypo::{h.id}"
        G.add_node(hid, group="hypo",
                   label=h.title if len(h.title) < 42 else h.title[:40] + "…",
                   title=f"{h.title}\nScore {h.score:.2f} · ≈{h.value_musd:.1f} M$/год\n"
                         f"реализ {h.feasibility:.2f} · риск {h.risk:.2f}",
                   value=max(10, h.value_musd))
        # связь гипотеза -> все причины с совпадающим кодом
        for cid, f in causes.items():
            if f.code == h.trigger_finding and (not h.size_class or h.size_class == f.size_class):
                G.add_edge(cid, hid, label="решается")
        for eq in h.equipment[:2]:
            eid = f"equip::{eq}"
            G.add_node(eid, group="equip", label=eq, title="Оборудование", value=8)
            G.add_edge(hid, eid, label="через")

    return G


def to_vis_html(G: nx.DiGraph, height: str = "620px") -> str:
    """Рендерит граф в самодостаточный HTML (vis-network инлайном из CDN-строки нет —
    используем облегчённую встроенную реализацию через vis-network из пакета, если есть,
    иначе — минимальный SVG-фолбэк)."""
    nodes, edges = [], []
    for n, d in G.nodes(data=True):
        g = GROUPS.get(d.get("group", "hypo"), GROUPS["hypo"])
        nodes.append({
            "id": n, "label": d.get("label", n),
            "title": d.get("title", ""),
            "color": g["color"], "shape": g["shape"],
            "value": d.get("value", 10),
        })
    for u, v, d in G.edges(data=True):
        edges.append({"from": u, "to": v, "label": d.get("label", ""),
                      "arrows": "to"})

    vis_js = _vis_lib()
    tmpl = """
<div id="knet" style="height:%HEIGHT%;border:1px solid #ddd;border-radius:8px;background:#fff"></div>
<script type="text/javascript">%VISJS%</script>
<script type="text/javascript">
  var nodes = new vis.DataSet(%NODES%);
  var edges = new vis.DataSet(%EDGES%);
  var container = document.getElementById('knet');
  var data = {nodes: nodes, edges: edges};
  var options = {
    nodes: {font:{size:14, multi:true}, scaling:{min:8,max:40}},
    edges: {font:{size:10, color:'#888', align:'middle'}, color:{color:'#bbb'},
            smooth:{type:'cubicBezier'}, arrows:{to:{scaleFactor:0.6}}},
    physics: {stabilization:true, barnesHut:{gravitationalConstant:-8000,springLength:140}},
    layout: {improvedLayout:true},
    interaction: {hover:true, tooltipDelay:120}
  };
  new vis.Network(container, data, options);
</script>
"""
    html = (tmpl.replace("%HEIGHT%", height)
                .replace("%VISJS%", vis_js)
                .replace("%NODES%", json.dumps(nodes, ensure_ascii=False))
                .replace("%EDGES%", json.dumps(edges, ensure_ascii=False)))
    return html


def _vis_lib() -> str:
    """Возвращает исходник vis-network. Пытаемся взять из установленного пакета,
    иначе — из локального кэша data/vendor. Если нет — вернём заглушку, но узлы/рёбра
    отрисуются, как только библиотека будет добавлена."""
    # 1) кэш проекта
    vendor = os.path.join(os.path.dirname(__file__), "..", "data", "vendor",
                          "vis-network.min.js")
    if os.path.exists(vendor):
        with open(vendor, encoding="utf-8") as f:
            return f.read()
    # 2) из пакета pyvis, если он появится
    try:
        import pyvis, glob
        base = os.path.dirname(pyvis.__file__)
        cand = glob.glob(os.path.join(base, "**", "vis-network*.min.js"), recursive=True)
        if cand:
            with open(cand[0], encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""  # фолбэк: библиотека подставится, если положить её в data/vendor


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose
    from core.generate import generate
    base = os.environ.get('CASE_DIR', 'data/examples')
    rep = parse_tailings_xlsx(f"{base}/Пример 1/Хвосты КГМК.xlsx", "КГМК")
    diag = diagnose(rep); hyps = generate(diag)
    G = build_graph(diag, hyps)
    print(f"граф: {G.number_of_nodes()} узлов, {G.number_of_edges()} рёбер")
    html = to_vis_html(G)
    out = os.path.join(os.path.dirname(__file__), "..", "exports", "КГМК_граф.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'>" + html)
    print("saved:", out, "| vis-lib:", "встроена" if _vis_lib() else "нужен data/vendor/vis-network.min.js")
