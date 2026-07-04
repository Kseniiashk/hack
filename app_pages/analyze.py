"""Анализ — рабочий инструмент: данные → диагностика → гипотезы → экспорт."""
import os
import tempfile

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

import ui_theme as ui
from core.ingest import parse_tailings_xlsx, TailingsReport
from core.diagnose import diagnose
from core.generate import generate, DEFAULT_WEIGHTS
from core.report import build_docx, hypotheses_to_csv, hypotheses_to_json
from core.economics import compute_kpi
from core.graph import build_graph, to_vis_html
from core import feedback as fb

_ROOT = next((p for p in __import__("sys").path if os.path.isdir(os.path.join(p, "core"))), ".")
BUNDLED = os.path.join(_ROOT, "data", "examples")
CASE_BASE = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
_YANDEX_READY = bool(os.environ.get("YANDEX_API_KEY") and os.environ.get("YANDEX_FOLDER_ID"))

EXAMPLES = {
    "Пример 1 — КГМК": ("КГМК.xlsx", "Пример 1/Хвосты КГМК.xlsx", "КГМК"),
    "Пример 2 — НОФ вкрапленные": ("НОФ-вкр.xlsx", "Пример 2/Хвосты НОФ Вкр.xlsx", "НОФ-вкр"),
    "Пример 3 — НОФ медистые": ("НОФ-мед.xlsx", "Пример 3/Хвосты НОФ мед.xlsx", "НОФ-мед"),
    "Пример 4 — ТОФ": ("ТОФ.xlsx", "Пример 4/Хвосты ТОФ_2.xlsx", "ТОФ"),
}


def _example_path(bundled_name, case_rel):
    p = os.path.join(BUNDLED, bundled_name)
    if os.path.exists(p):
        return p
    p2 = os.path.join(CASE_BASE, case_rel)
    return p2 if os.path.exists(p2) else None


@st.cache_resource(show_spinner=False)
def get_rag_cached():
    try:
        from core.rag import get_rag
        return get_rag()
    except Exception:
        return None


@st.cache_resource(show_spinner="Инициализация LLM…")
def get_llm_cached():
    try:
        from core.llm import get_reasoner
        return get_reasoner()
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def llm_refine_cached(facts: str, backend_name: str) -> str:
    llm = get_llm_cached()
    if not llm or not getattr(llm, "ok", False):
        return ""
    return llm.refine(facts)


# ----------------------------- Панель управления -----------------------------
st.sidebar.markdown(
    "<div style='font-family:var(--mono);font-size:11px;letter-spacing:.16em;"
    "text-transform:uppercase;color:#61788b;margin:6px 0 8px'>Данные</div>",
    unsafe_allow_html=True)
src_mode = st.sidebar.radio("Источник", ["Готовый пример", "Загрузить .xlsx"],
                            label_visibility="collapsed")

report: TailingsReport = None
if src_mode == "Готовый пример":
    choice = st.sidebar.selectbox("Пример", list(EXAMPLES.keys()))
    bundled_name, case_rel, plant = EXAMPLES[choice]
    path = _example_path(bundled_name, case_rel)
    if path:
        report = parse_tailings_xlsx(path, plant)
    else:
        st.sidebar.error("Файл примера не найден.")
else:
    up = st.sidebar.file_uploader("Файл 'Хвосты …xlsx'", type=["xlsx"])
    plant = st.sidebar.text_input("Название фабрики", "Моя фабрика")
    if up:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tf:
            tf.write(up.read())
            tmp = tf.name
        report = parse_tailings_xlsx(tmp, plant)

st.sidebar.markdown(
    "<div style='font-family:var(--mono);font-size:11px;letter-spacing:.16em;"
    "text-transform:uppercase;color:#61788b;margin:16px 0 4px'>Веса ранжирования</div>",
    unsafe_allow_html=True)
w_value = st.sidebar.slider("Ценность", 0.0, 1.0, DEFAULT_WEIGHTS["value"], 0.05)
w_feas = st.sidebar.slider("Реализуемость", 0.0, 1.0, DEFAULT_WEIGHTS["feasibility"], 0.05)
w_nov = st.sidebar.slider("Новизна", 0.0, 1.0, DEFAULT_WEIGHTS["novelty"], 0.05)
w_risk = st.sidebar.slider("Штраф за риск", 0.0, 1.0, DEFAULT_WEIGHTS["risk"], 0.05)
weights = {"value": w_value, "feasibility": w_feas, "novelty": w_nov, "risk": w_risk}

st.sidebar.markdown(
    "<div style='font-family:var(--mono);font-size:11px;letter-spacing:.16em;"
    "text-transform:uppercase;color:#61788b;margin:16px 0 4px'>Модель и цены</div>",
    unsafe_allow_html=True)
price_ni = st.sidebar.number_input("Цена Ni, $/т", 1000, 50000, 15000, 500)
price_cu = st.sidebar.number_input("Цена Cu, $/т", 1000, 50000, 8500, 500)
prices = {"Ni": float(price_ni), "Cu": float(price_cu)}
use_rag = st.sidebar.checkbox("RAG-цитаты из учебников", value=True)
use_llm = st.sidebar.checkbox("LLM-обоснование (Yandex GPT)", value=False,
                              disabled=not _YANDEX_READY,
                              help="Переписывает обоснование топ-гипотез в связный "
                                   "экспертный текст строго по фактам (без новых чисел).")
apply_fb = st.sidebar.checkbox("Учитывать фидбэк экспертов", value=True)
if _YANDEX_READY:
    st.sidebar.caption("🟢 Yandex AI Studio подключён")

# ----------------------------- Заголовок и вывод -----------------------------
st.markdown(ui.hero_html(_YANDEX_READY), unsafe_allow_html=True)

if report is None:
    st.markdown(
        "<div class='welcome'>Выберите <b>готовый пример</b> или загрузите файл "
        "<b>Хвосты*.xlsx</b> в панели слева.</div>", unsafe_allow_html=True)
    st.stop()

for w in report.warnings:
    st.warning(w)

diag = diagnose(report, prices=prices)
rag = get_rag_cached() if use_rag else None
try:
    hyps = generate(diag, weights=weights, prices=prices, rag=rag, report=report)
except TypeError:
    # запасной путь, если закэширована старая версия generate() без report
    hyps = generate(diag, weights=weights, prices=prices, rag=rag)
if apply_fb:
    fb.apply_to_hypotheses(hyps)
kpi = compute_kpi(report, diag, hyps, prices, top_n=5)

if use_llm:
    llm = get_llm_cached()
    if llm and getattr(llm, "ok", False):
        from core.llm import facts_block
        with st.spinner("Генерация экспертных обоснований (Yandex GPT)…"):
            for h in hyps[:5]:
                setattr(h, "llm_rationale", llm_refine_cached(facts_block(h, diag), llm.name))

st.markdown(ui.kpi_row_html(report, diag.total_value_musd), unsafe_allow_html=True)

tab1, tab2, tabG, tabE, tab3 = st.tabs(
    ["Диагностика", "Гипотезы", "Граф знаний", "Экономика / KPI", "Экспорт"])

# ===== Диагностика =====
with tab1:
    st.markdown("<div class='sec-label'>Распределение потерь по классам крупности</div>",
                unsafe_allow_html=True)
    df = pd.DataFrame([{
        "Класс, мкм": c.size, "Доля класса, %": round(c.mass_share_pct, 1),
        "Ni всего, т": round(c.el28_t, 1),
        "Ni раскрытый, т": round(c.min28.liberated_t(), 1),
        "Ni закрытый, т": round(c.min28.locked_t(), 1),
        "Cu всего, т": round(c.el29_t, 1),
        "Cu раскрытый, т": round(c.min29.liberated_t(), 1),
        "Cu закрытый, т": round(c.min29.locked_t(), 1),
    } for c in report.classes]).set_index("Класс, мкм")
    st.dataframe(df, use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Закрытый металл (недоизмельчение), т**")
        st.bar_chart(pd.DataFrame({
            "Ni закрытый": [c.min28.locked_t() for c in report.classes],
            "Cu закрытый": [c.min29.locked_t() for c in report.classes],
        }, index=[c.size for c in report.classes]))
    with colB:
        st.markdown("**Раскрытый металл (шламы), т**")
        st.bar_chart(pd.DataFrame({
            "Ni раскрытый": [c.min28.liberated_t() for c in report.classes],
            "Cu раскрытый": [c.min29.liberated_t() for c in report.classes],
        }, index=[c.size for c in report.classes]))

    st.markdown("<div class='sec-label'>Ключевые находки</div>", unsafe_allow_html=True)
    for f in diag.findings:
        if f.code != "RECOVERABLE_CEILING":
            st.markdown(ui.finding_html(f), unsafe_allow_html=True)
    for f in diag.findings:
        if f.code == "RECOVERABLE_CEILING":
            st.markdown(ui.finding_html(f), unsafe_allow_html=True)

# ===== Гипотезы =====
with tab2:
    st.markdown(
        f"<div class='sec-label'>Ранжированные гипотезы · {len(hyps)} шт · "
        f"Score = ценность + реализуемость + новизна − риск</div>",
        unsafe_allow_html=True)
    for i, h in enumerate(hyps, 1):
        st.markdown(ui.hypothesis_html(i, h), unsafe_allow_html=True)
        fc1, fc2, fc3, _sp = st.columns([1.1, 1.1, 1.0, 3.8])
        if fc1.button("Подтвердить", key=f"c_{h.id}_{i}"):
            fb.record(h.id, fb.CONFIRMED, plant=diag.plant); st.rerun()
        if fc2.button("Опровергнуть", key=f"r_{h.id}_{i}"):
            fb.record(h.id, fb.REFUTED, plant=diag.plant); st.rerun()
        if fc3.button("Отклонить", key=f"x_{h.id}_{i}"):
            fb.record(h.id, fb.REJECTED, plant=diag.plant); st.rerun()

# ===== Граф =====
with tabG:
    st.markdown(
        "<div class='sec-label'>Граф знаний · наблюдение → причина → гипотеза → оборудование</div>",
        unsafe_allow_html=True)
    top_g = st.slider("Гипотез на графе", 3, min(12, len(hyps)), min(8, len(hyps)))
    if st.button("Построить граф", key="build_graph"):
        st.session_state["show_graph"] = True
    if st.session_state.get("show_graph"):
        G = build_graph(diag, hyps, top_n=int(top_g))
        html = to_vis_html(G, height="640px")
        if "vis.Network" in html and len(html) > 5000:
            components.html("<!doctype html><meta charset='utf-8'>" + html, height=660)
        else:
            for u, v, d in G.edges(data=True):
                st.text(f"{G.nodes[u].get('label','')} —{d.get('label','')}→ {G.nodes[v].get('label','')}")
    else:
        st.markdown("<div class='welcome'>Нажмите <b>«Построить граф»</b> для интерактивной схемы.</div>",
                    unsafe_allow_html=True)

# ===== Экономика =====
with tabE:
    st.markdown("<div class='sec-label'>Экономика и целевые KPI</div>", unsafe_allow_html=True)
    ec = ui.eco_cards_html(kpi)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(ec["recov"], unsafe_allow_html=True)
    c2.markdown(ec["after"], unsafe_allow_html=True)
    c3.markdown(ec["tail"], unsafe_allow_html=True)
    c4.markdown(ec["port"], unsafe_allow_html=True)
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"**Потолок эффекта:** {kpi.ceiling_musd:.1f} млн $/год — стоимость всего "
        f"извлекаемого металла ({kpi.recoverable_ni_t:,.0f} т Ni + {kpi.recoverable_cu_t:,.0f} т Cu). "
        f"**Портфель топ-5** отыгрывает ≈ {kpi.portfolio_musd:.1f} млн $/год.")
    colS, colD = st.columns(2)
    with colS:
        st.markdown("**Чувствительность к ценам металлов**")
        st.bar_chart(pd.DataFrame(kpi.sensitivity).set_index("scenario"))
    with colD:
        st.markdown("**Вклад причин в потери, M$/год**")
        cdf = pd.DataFrame([{"Причина": f.code, "M$": round(f.value_musd, 1)}
                            for f in diag.findings if f.code != "RECOVERABLE_CEILING"])
        if not cdf.empty:
            st.bar_chart(cdf.groupby("Причина")["M$"].sum())

# ===== Экспорт =====
with tab3:
    st.markdown("<div class='sec-label'>Экспорт результатов</div>", unsafe_allow_html=True)
    top_n = st.number_input("Гипотез в отчёт", 1, len(hyps), min(8, len(hyps)))
    cx, cy, cz = st.columns(3)
    with cx:
        if st.button("Сформировать DOCX"):
            out = os.path.join(tempfile.gettempdir(), f"{diag.plant}_гипотезы.docx")
            build_docx(diag, hyps, out, top_n=int(top_n))
            with open(out, "rb") as f:
                st.download_button("Скачать DOCX", f.read(), file_name=f"{diag.plant}_гипотезы.docx")
    with cy:
        st.download_button("Скачать CSV", hypotheses_to_csv(hyps),
                           file_name=f"{diag.plant}_гипотезы.csv")
    with cz:
        st.download_button("Скачать JSON", hypotheses_to_json(hyps),
                           file_name=f"{diag.plant}_гипотезы.json")
    st.markdown("<div class='sec-label'>Предпросмотр таблицы задач</div>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{
        "Ранг": i + 1, "Гипотеза": h.title, "Score": round(h.score, 2),
        "Эффект,M$": round(h.value_musd, 1), "Класс": h.size_class, "Передел": h.stage,
    } for i, h in enumerate(hyps)]), use_container_width=True)
