import os
import sys
import tempfile

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

import ui_theme as t
from core.ingest import parse_tailings_xlsx
from core.diagnose import diagnose, check_data_sanity, rejected_directions
from core.generate import generate, DEFAULT_WEIGHTS
from core.report import build_docx, hypotheses_to_csv, hypotheses_to_json
from core.economics import compute_kpi
from core.graph import build_graph, to_vis_html
from core import feedback

ROOT = next((p for p in sys.path if os.path.isdir(os.path.join(p, "core"))), ".")
EXAMPLES_DIR = os.path.join(ROOT, "data", "examples")
HAS_YANDEX = bool(os.environ.get("YANDEX_API_KEY") and os.environ.get("YANDEX_FOLDER_ID"))

EXAMPLES = {
    "КГМК": "КГМК.xlsx",
    "НОФ вкрапленные": "НОФ-вкр.xlsx",
    "НОФ медистые": "НОФ-мед.xlsx",
    "ТОФ": "ТОФ.xlsx",
}


def example_path(name):
    p = os.path.join(EXAMPLES_DIR, EXAMPLES[name])
    return p if os.path.exists(p) else None


@st.cache_resource(show_spinner=False)
def load_rag():
    try:
        from core.rag import get_rag
        return get_rag()
    except Exception:
        return None


@st.cache_resource(show_spinner="Подключение к модели…")
def load_llm():
    try:
        from core.llm import get_reasoner
        return get_reasoner()
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def llm_text(facts, backend):
    r = load_llm()
    return r.refine(facts) if r and getattr(r, "ok", False) else ""


# Панель ввода
st.sidebar.subheader("Данные")
mode = st.sidebar.radio("Источник", ["Пример", "Загрузить файл"],
                        label_visibility="collapsed")

report = None
plant = ""
if mode == "Пример":
    name = st.sidebar.selectbox("Фабрика", list(EXAMPLES.keys()))
    path = example_path(name)
    if path:
        report, plant = parse_tailings_xlsx(path, name), name
    else:
        st.sidebar.error("Файл не найден.")
else:
    up = st.sidebar.file_uploader("Отчёт о хвостах (.xlsx)", type=["xlsx"])
    plant = st.sidebar.text_input("Название фабрики", "Фабрика")
    if up:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
            f.write(up.read())
            report = parse_tailings_xlsx(f.name, plant)

st.sidebar.subheader("Веса ранжирования")
weights = {
    "value": st.sidebar.slider("Ценность", 0.0, 1.0, DEFAULT_WEIGHTS["value"], 0.05),
    "feasibility": st.sidebar.slider("Реализуемость", 0.0, 1.0, DEFAULT_WEIGHTS["feasibility"], 0.05),
    "novelty": st.sidebar.slider("Новизна", 0.0, 1.0, DEFAULT_WEIGHTS["novelty"], 0.05),
    "risk": st.sidebar.slider("Штраф за риск", 0.0, 1.0, DEFAULT_WEIGHTS["risk"], 0.05),
}

st.sidebar.subheader("Параметры")
prices = {
    "Ni": float(st.sidebar.number_input("Цена Ni, $/т", 1000, 50000, 15000, 500)),
    "Cu": float(st.sidebar.number_input("Цена Cu, $/т", 1000, 50000, 8500, 500)),
}
use_rag = st.sidebar.checkbox("Ссылки на литературу", value=True)
use_llm = st.sidebar.checkbox("Текстовое обоснование (LLM)", value=HAS_YANDEX,
                              disabled=not HAS_YANDEX)
use_feedback = st.sidebar.checkbox("Учитывать оценки экспертов", value=True)

st.markdown(t.page_header("Анализ потерь и подбор гипотез"), unsafe_allow_html=True)

if report is None:
    st.info("Выберите фабрику или загрузите отчёт о хвостах.")
    st.stop()

for w in report.warnings:
    st.warning(w)

diag = diagnose(report, prices=prices)
rag = load_rag() if use_rag else None
try:
    hyps = generate(diag, weights=weights, prices=prices, rag=rag, report=report)
except TypeError:
    hyps = generate(diag, weights=weights, prices=prices, rag=rag)

if use_feedback:
    feedback.apply_to_hypotheses(hyps)
kpi = compute_kpi(report, diag, hyps, prices, top_n=5)

if use_llm:
    llm = load_llm()
    if llm and getattr(llm, "ok", False):
        from core.llm import facts_block
        with st.spinner("Формулирую обоснования…"):
            for h in hyps[:5]:
                h.llm_rationale = llm_text(facts_block(h, diag), llm.name)

st.markdown(t.summary(report, diag.total_value_musd), unsafe_allow_html=True)

tab_diag, tab_hyp, tab_graph, tab_eco, tab_export = st.tabs(
    ["Диагностика", "Гипотезы", "Граф", "Экономика", "Экспорт"])

with tab_diag:
    st.markdown("<div class='rule'>Проверка исходных данных</div>", unsafe_allow_html=True)
    for chk in check_data_sanity(report):
        icon = "🟢" if chk["status"] == "ok" else "🟡"
        st.markdown(t.check_row(chk["status"], chk["msg"]), unsafe_allow_html=True)

    st.markdown("<div class='rule'>Распределение по классам крупности</div>",
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{
        "Класс, мкм": c.size,
        "Доля, %": round(c.mass_share_pct, 1),
        "Ni всего, т": round(c.el28_t, 1),
        "Ni раскрытый": round(c.min28.liberated_t(), 1),
        "Ni в сростках": round(c.min28.locked_t(), 1),
        "Cu всего, т": round(c.el29_t, 1),
        "Cu раскрытый": round(c.min29.liberated_t(), 1),
        "Cu в сростках": round(c.min29.locked_t(), 1),
    } for c in report.classes]).set_index("Класс, мкм"), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.caption("Металл в сростках (недоизмельчение), т")
        st.bar_chart(pd.DataFrame({
            "Ni": [c.min28.locked_t() for c in report.classes],
            "Cu": [c.min29.locked_t() for c in report.classes],
        }, index=[c.size for c in report.classes]))
    with right:
        st.caption("Раскрытый металл (шламы), т")
        st.bar_chart(pd.DataFrame({
            "Ni": [c.min28.liberated_t() for c in report.classes],
            "Cu": [c.min29.liberated_t() for c in report.classes],
        }, index=[c.size for c in report.classes]))

    st.markdown("<div class='rule'>Что и где теряется</div>", unsafe_allow_html=True)
    ordered = [f for f in diag.findings if f.code != "RECOVERABLE_CEILING"]
    ordered += [f for f in diag.findings if f.code == "RECOVERABLE_CEILING"]
    for f in ordered:
        st.markdown(t.finding(f), unsafe_allow_html=True)

    rejected = rejected_directions(report, diag)
    if rejected:
        with st.expander("Почему НЕ предлагаем некоторые стандартные меры"):
            for r in rejected:
                st.markdown(t.rejected(r), unsafe_allow_html=True)

with tab_hyp:
    st.markdown(f"<div class='rule'>Гипотезы — {len(hyps)}</div>",
                unsafe_allow_html=True)
    st.caption(
        "Оценка эксперта корректирует место гипотезы в списке при следующих запусках: "
        "подтверждённые поднимаются (множитель ранга до 1.3×), опровергнутые опускаются "
        "(до 0.7×), отклонённые уходят вниз. Множитель показан в строке гипотезы.")
    for i, h in enumerate(hyps, 1):
        st.markdown(t.hypothesis(i, h), unsafe_allow_html=True)
        b1, b2, b3, _ = st.columns([1, 1, 1, 4])
        if b1.button("Подтвердить", key=f"c{h.id}{i}"):
            feedback.record(h.id, feedback.CONFIRMED, plant=plant)
            st.toast(f"«{h.title[:40]}…» подтверждена — множитель "
                     f"×{feedback.multiplier(h.id)}")
            st.rerun()
        if b2.button("Опровергнуть", key=f"r{h.id}{i}"):
            feedback.record(h.id, feedback.REFUTED, plant=plant)
            st.toast(f"«{h.title[:40]}…» опровергнута — множитель "
                     f"×{feedback.multiplier(h.id)}")
            st.rerun()
        if b3.button("Отклонить", key=f"x{h.id}{i}"):
            feedback.record(h.id, feedback.REJECTED, plant=plant)
            st.toast(f"«{h.title[:40]}…» отклонена — множитель "
                     f"×{feedback.multiplier(h.id)}")
            st.rerun()

with tab_graph:
    st.markdown("<div class='rule'>Связи: класс → причина → гипотеза → оборудование</div>",
                unsafe_allow_html=True)
    n = st.slider("Гипотез на графе", 3, min(12, len(hyps)), min(8, len(hyps)))
    if st.button("Построить граф"):
        st.session_state["graph"] = True
    if st.session_state.get("graph"):
        g = build_graph(diag, hyps, top_n=int(n))
        html = to_vis_html(g, height="600px")
        if "vis.Network" in html and len(html) > 5000:
            components.html("<!doctype html><meta charset='utf-8'>" + html, height=620)
        else:
            for u, v, d in g.edges(data=True):
                st.text(f"{g.nodes[u].get('label','')} → {g.nodes[v].get('label','')}")

with tab_eco:
    st.markdown("<div class='rule'>Извлечение и эффект</div>", unsafe_allow_html=True)
    st.markdown(t.eco_summary(kpi), unsafe_allow_html=True)
    st.markdown(
        f"Потолок эффекта — {kpi.ceiling_musd:.1f} млн долларов в год: столько стоит "
        f"весь извлекаемый металл в хвостах ({kpi.recoverable_ni_t:,.0f} т Ni и "
        f"{kpi.recoverable_cu_t:,.0f} т Cu). Портфель из пяти верхних гипотез "
        f"возвращает около {kpi.portfolio_musd:.1f} млн долларов в год.")
    st.caption(
        "Эффект портфеля не суммируется вслепую: если несколько мер бьют в один и тот же "
        "класс потерь, система берёт лучший вклад, а не складывает их — чтобы не завышать оценку.")

    st.markdown("<div class='rule'>Матрица приоритетов</div>", unsafe_allow_html=True)
    st.caption("Быстрые победы — легко внедрить и высокий эффект; стратегические — "
               "высокий эффект, но капитальные затраты. Размер точки — новизна. "
               "Номер точки = ранг гипотезы.")
    try:
        st.plotly_chart(t.priority_matrix(hyps), use_container_width=True)
    except Exception:
        st.info("Матрица недоступна (нужен plotly).")
    labels = {"UNDERGRIND": "Недоизмельчение", "SLIMES": "Потеря шламов",
              "MIDGRIND": "Средний класс"}
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Чувствительность к ценам металлов, млн долл./год")
        sens = pd.DataFrame(kpi.sensitivity).set_index("scenario")
        st.bar_chart(sens, horizontal=True)
    with c2:
        st.caption("Вклад причин в потери, млн долл./год")
        rows = [{"Причина": labels.get(f.code, f.code), "M$": round(f.value_musd, 1)}
                for f in diag.findings if f.code != "RECOVERABLE_CEILING"]
        df = pd.DataFrame(rows).groupby("Причина")["M$"].sum()
        if not df.empty:
            st.bar_chart(df, horizontal=True)
    st.markdown("<div class='note'>Оценки ориентировочные: цены задаются слева, "
                "содержание шихты — по типовому балансу отчёта.</div>",
                unsafe_allow_html=True)

with tab_export:
    st.markdown("<div class='rule'>Выгрузка результатов</div>", unsafe_allow_html=True)
    top_n = st.number_input("Гипотез в отчёте", 1, len(hyps), min(8, len(hyps)))
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Собрать DOCX"):
            out = os.path.join(tempfile.gettempdir(), f"{plant}_гипотезы.docx")
            build_docx(diag, hyps, out, top_n=int(top_n))
            with open(out, "rb") as f:
                st.download_button("Скачать DOCX", f.read(),
                                   file_name=f"{plant}_гипотезы.docx")
    with c2:
        st.download_button("CSV", hypotheses_to_csv(hyps),
                           file_name=f"{plant}_гипотезы.csv")
    with c3:
        st.download_button("JSON", hypotheses_to_json(hyps),
                           file_name=f"{plant}_гипотезы.json")
    st.dataframe(pd.DataFrame([{
        "№": i + 1, "Гипотеза": h.title, "Score": round(h.score, 2),
        "Эффект, M$": round(h.value_musd, 1), "Класс": h.size_class,
    } for i, h in enumerate(hyps)]), use_container_width=True)
