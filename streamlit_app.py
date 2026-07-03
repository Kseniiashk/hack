"""
Фабрика гипотез — интерактивное демо (Streamlit).

Запуск:
  cd hypothesis_factory
  /Users/kseniashk/anaconda3/bin/python3 -m streamlit run app/streamlit_app.py

Поток: загрузка xlsx хвостов -> диагностика с графиками -> ранжированные
гипотезы с обоснованием и цитатами -> настройка весов -> экспорт docx/csv/json.
"""
import os
import sys
import tempfile

# Находим корень проекта (папку, где лежит core/) — работает и в корне репо
# (Streamlit Cloud), и в подпапке app/ (локально).
_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = _HERE
for _cand in (_HERE, os.path.dirname(_HERE)):
    if os.path.isdir(os.path.join(_cand, "core")):
        PROJECT_ROOT = _cand
        break
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

from core import load_dotenv  # noqa: E402
load_dotenv()  # подхватываем ключ Yandex из .env, если есть

import streamlit as st

# На Streamlit Cloud ключ приходит через st.secrets — прокидываем его в окружение,
# чтобы LLM-слой (core/llm.py) его увидел.
try:
    for _k in ("YANDEX_API_KEY", "YANDEX_FOLDER_ID", "YANDEX_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

# LLM включаем по умолчанию только если доступен быстрый Yandex-бэкенд (есть ключ).
_YANDEX_READY = bool(os.environ.get("YANDEX_API_KEY") and os.environ.get("YANDEX_FOLDER_ID"))

import streamlit.components.v1 as components
import pandas as pd

from core.ingest import parse_tailings_xlsx, TailingsReport, SIZE_CLASSES
from core.diagnose import diagnose
from core.generate import generate, DEFAULT_WEIGHTS
from core.report import build_docx, hypotheses_to_csv, hypotheses_to_json
from core.economics import compute_kpi
from core.graph import build_graph, to_vis_html

st.set_page_config(page_title="Фабрика гипотез", page_icon="⚗️", layout="wide")

# Примеры лежат в проекте (data/examples), чтобы демо работало где угодно
# (в т.ч. на Hugging Face Spaces). Если рядом есть оригинальные данные кейса —
# они тоже подхватятся.
_ROOT = PROJECT_ROOT
BUNDLED = os.path.join(_ROOT, "data", "examples")
CASE_BASE = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"

# (подпись в UI) -> (basename в data/examples, путь в оригинальном кейсе, plant)
EXAMPLES = {
    "Пример 1 — КГМК": ("КГМК.xlsx", "Пример 1/Хвосты КГМК.xlsx", "КГМК"),
    "Пример 2 — НОФ вкрапленные": ("НОФ-вкр.xlsx", "Пример 2/Хвосты НОФ Вкр.xlsx", "НОФ-вкр"),
    "Пример 3 — НОФ медистые": ("НОФ-мед.xlsx", "Пример 3/Хвосты НОФ мед.xlsx", "НОФ-мед"),
    "Пример 4 — ТОФ": ("ТОФ.xlsx", "Пример 4/Хвосты ТОФ_2.xlsx", "ТОФ"),
}


def _example_path(bundled_name, case_rel):
    """Сначала пробуем встроенный пример, затем оригинальные данные кейса."""
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
    """Кэш LLM-обоснований по тексту фактов — повторные ререндеры (движение
    слайдеров) не бьют по API заново и экономят бюджет токенов."""
    llm = get_llm_cached()
    if not llm or not getattr(llm, "ok", False):
        return ""
    return llm.refine(facts)


# ----------------------------- Sidebar ---------------------------------------
st.sidebar.title("⚗️ Фабрика гипотез")
st.sidebar.caption("Генерация и приоритизация гипотез по снижению потерь металла с хвостами обогащения")

src_mode = st.sidebar.radio("Источник данных", ["Готовый пример", "Загрузить .xlsx"])

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

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Экспертная настройка весов")
w_value = st.sidebar.slider("Ценность (эффект на KPI)", 0.0, 1.0, DEFAULT_WEIGHTS["value"], 0.05)
w_feas = st.sidebar.slider("Реализуемость", 0.0, 1.0, DEFAULT_WEIGHTS["feasibility"], 0.05)
w_nov = st.sidebar.slider("Новизна", 0.0, 1.0, DEFAULT_WEIGHTS["novelty"], 0.05)
w_risk = st.sidebar.slider("Штраф за риск", 0.0, 1.0, DEFAULT_WEIGHTS["risk"], 0.05)
weights = {"value": w_value, "feasibility": w_feas, "novelty": w_nov, "risk": w_risk}

st.sidebar.markdown("---")
price_ni = st.sidebar.number_input("Цена Ni, $/т", 1000, 50000, 15000, 500)
price_cu = st.sidebar.number_input("Цена Cu, $/т", 1000, 50000, 8500, 500)
prices = {"Ni": float(price_ni), "Cu": float(price_cu)}
use_rag = st.sidebar.checkbox("RAG-обоснование (цитаты из учебников)", value=True)
use_llm = st.sidebar.checkbox("LLM-обоснование", value=False,
                              help="Переписывает обоснование топ-гипотез в связный "
                                   "экспертный текст строго по фактам из данных (без "
                                   "новых чисел). Бэкенд: Yandex AI Studio при заданном "
                                   "YANDEX_API_KEY (≈0.5 с/гипотеза), иначе локальная "
                                   "модель Qwen3 (офлайн). Включите для «живых» обоснований.")
if _YANDEX_READY:
    st.sidebar.caption("🟢 Yandex AI Studio подключён — включите галочку выше")


# ----------------------------- Main ------------------------------------------
st.title("Фабрика гипотез")
st.caption("Обогащение сульфидных руд цветных металлов · Элемент 28 = Ni · Элемент 29 = Cu")

if report is None:
    st.info("Выберите пример или загрузите файл хвостов в панели слева.")
    st.stop()

if report.warnings:
    for w in report.warnings:
        st.warning(w)

diag = diagnose(report, prices=prices)
rag = get_rag_cached() if use_rag else None
hyps = generate(diag, weights=weights, prices=prices, rag=rag)

# Обучение на фидбэке: корректируем ранжирование по накопленным оценкам экспертов.
from core import feedback as fb
apply_fb = st.sidebar.checkbox("Учитывать фидбэк экспертов", value=True,
                               help="Подтверждённые гипотезы поднимаются, "
                                    "опровергнутые/отклонённые опускаются.")
if apply_fb:
    fb.apply_to_hypotheses(hyps)
kpi = compute_kpi(report, diag, hyps, prices, top_n=5)

if use_llm:
    llm = get_llm_cached()
    if llm and getattr(llm, "ok", False):
        from core.llm import facts_block
        with st.spinner("Генерация экспертных обоснований (LLM)…"):
            for h in hyps[:6]:
                txt = llm_refine_cached(facts_block(h, diag), llm.name)
                setattr(h, "llm_rationale", txt)
        st.sidebar.success(f"LLM: {llm.name} ({llm.device})")
    else:
        reason = getattr(llm, "_err", "модель не найдена") if llm else "недоступно"
        st.sidebar.info(f"LLM выключена ({reason}) — используется детерминированное "
                        "обоснование.")

# --- KPI-строка ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Хвосты, т/год", f"{report.tail_mass_t:,.0f}")
c2.metric("Потери Ni в хвостах", f"{report.tail_el28_t:,.0f} т",
          f"{report.tail_el28_pct:.3f}%")
c3.metric("Потери Cu в хвостах", f"{report.tail_el29_t:,.0f} т",
          f"{report.tail_el29_pct:.3f}%")
c4.metric("Потолок эффекта", f"{diag.total_value_musd:.0f} M$/год",
          help="Стоимость всего извлекаемого металла, теряемого с хвостами")

tab1, tab2, tabG, tabE, tab3 = st.tabs(
    ["📊 Диагностика", "💡 Гипотезы", "🕸️ Граф знаний", "💰 Экономика / KPI", "📤 Экспорт"])

# ===== Диагностика =====
with tab1:
    st.subheader("Распределение потерь металла по классам крупности")
    rows = []
    for c in report.classes:
        rows.append({
            "Класс, мкм": c.size,
            "Доля класса, %": round(c.mass_share_pct, 1),
            "Ni всего, т": round(c.el28_t, 1),
            "Ni раскрытый, т": round(c.min28.liberated_t(), 1),
            "Ni закрытый (сростки), т": round(c.min28.locked_t(), 1),
            "Cu всего, т": round(c.el29_t, 1),
            "Cu раскрытый, т": round(c.min29.liberated_t(), 1),
            "Cu закрытый (сростки), т": round(c.min29.locked_t(), 1),
        })
    df = pd.DataFrame(rows).set_index("Класс, мкм")
    st.dataframe(df, use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Закрытый металл (недоизмельчение) по классам, т**")
        locked = pd.DataFrame({
            "Ni закрытый": [c.min28.locked_t() for c in report.classes],
            "Cu закрытый": [c.min29.locked_t() for c in report.classes],
        }, index=[c.size for c in report.classes])
        st.bar_chart(locked)
    with colB:
        st.markdown("**Раскрытый металл (потеря шламов) по классам, т**")
        lib = pd.DataFrame({
            "Ni раскрытый": [c.min28.liberated_t() for c in report.classes],
            "Cu раскрытый": [c.min29.liberated_t() for c in report.classes],
        }, index=[c.size for c in report.classes])
        st.bar_chart(lib)

    st.subheader("Ключевые находки диагностики")
    for f in diag.findings:
        if f.code == "RECOVERABLE_CEILING":
            st.success(f"🎯 **{f.headline}**\n\n{f.detail}")
        else:
            icon = {"UNDERGRIND": "🔨", "SLIMES": "🌫️", "MIDGRIND": "⚙️"}.get(f.code, "•")
            with st.expander(f"{icon} {f.headline}  ·  ≈{f.value_musd:.1f} M$/год"):
                st.write(f.detail)
                st.json(f.evidence)

# ===== Гипотезы =====
with tab2:
    st.subheader(f"Ранжированные гипотезы ({len(hyps)})")
    st.caption("Score = w·Ценность + w·Реализуемость + w·Новизна − w·Риск. "
               "Веса и цены настраиваются слева.")
    for i, h in enumerate(hyps, 1):
        with st.expander(f"**{i}. {h.title}**  ·  Score {h.score:.2f}  ·  "
                         f"≈{h.value_musd:.1f} M$/год  ·  класс {h.size_class}", expanded=(i <= 3)):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Эффект", f"{h.value_musd:.1f} M$")
            m2.metric("Реализуемость", f"{h.feasibility:.2f}")
            m3.metric("Новизна", f"{h.novelty:.2f}")
            m4.metric("Риск", f"{h.risk:.2f}")
            llm_txt = getattr(h, "llm_rationale", "")
            if llm_txt:
                st.markdown(f"**Обоснование (LLM).** {llm_txt}")
                with st.popover("детерминированное обоснование"):
                    st.write(h.rationale)
            else:
                st.markdown(f"**Обоснование.** {h.rationale}")
            st.markdown(f"**Механизм влияния.** {h.mechanism}")
            if h.equipment:
                st.markdown(f"**Оборудование:** {', '.join(h.equipment)} · "
                            f"**Передел:** {h.stage}")
            if h.success_criterion:
                st.markdown(f"**Критерий успеха.** {h.success_criterion}")
            if h.roadmap:
                st.markdown("**Дорожная карта проверки:**")
                for step in h.roadmap:
                    st.markdown(f"- {step}")
            if h.citations:
                st.markdown("**Источники (литература):**")
                for c in h.citations:
                    pg = f", с.{c['page']}" if c.get("page") else ""
                    st.markdown(f"> «{c['snippet']}»  \n— *{c['source']}{pg}*")

            # --- Обучение на фидбэке ---
            st.markdown("---")
            fb_stats = getattr(h, "fb_stats", None)
            fb_mult = getattr(h, "fb_multiplier", 1.0)
            cap = "**Оценка эксперта.**"
            if fb_stats:
                cap += (f" История: ✅{fb_stats.get('confirmed',0)} "
                        f"❌{fb_stats.get('refuted',0)} 🚫{fb_stats.get('rejected',0)} "
                        f"· множитель ранга ×{fb_mult}")
            st.caption(cap)
            fc1, fc2, fc3 = st.columns(3)
            if fc1.button("✅ Подтверждена", key=f"c_{h.id}_{i}"):
                fb.record(h.id, fb.CONFIRMED, plant=diag.plant); st.rerun()
            if fc2.button("❌ Опровергнута", key=f"r_{h.id}_{i}"):
                fb.record(h.id, fb.REFUTED, plant=diag.plant); st.rerun()
            if fc3.button("🚫 Отклонить", key=f"x_{h.id}_{i}"):
                fb.record(h.id, fb.REJECTED, plant=diag.plant); st.rerun()

# ===== Граф знаний =====
with tabG:
    st.subheader("Граф знаний: от наблюдения в данных к вмешательству")
    st.caption("Класс крупности → форма потерь → причина → гипотеза → оборудование. "
               "Наведите на узел для подробностей; граф отражает картину именно этой фабрики.")
    top_g = st.slider("Гипотез на графе", 3, min(12, len(hyps)), min(8, len(hyps)))
    # Граф (~0.5 МБ интерактивного HTML) строим по кнопке, чтобы не утяжелять
    # первый рендер и стабильно работать за прокси хостинга.
    if st.button("🕸️ Построить граф", key="build_graph"):
        st.session_state["show_graph"] = True
    if st.session_state.get("show_graph"):
        G = build_graph(diag, hyps, top_n=int(top_g))
        html = to_vis_html(G, height="640px")
        if "vis.Network" in html and "new vis.DataSet" in html and len(html) > 5000:
            components.html("<!doctype html><meta charset='utf-8'>" + html, height=660,
                            scrolling=False)
        else:
            st.warning("Библиотека визуализации не найдена. Показываю связи текстом.")
            for u, v, d in G.edges(data=True):
                st.text(f"{G.nodes[u].get('label','')}  —{d.get('label','')}→  "
                        f"{G.nodes[v].get('label','')}")
    else:
        st.info("Нажмите «Построить граф», чтобы отрисовать интерактивную схему связей.")

# ===== Экономика / KPI =====
with tabE:
    st.subheader("Экономика и KPI")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Извлечение Ni сейчас", f"{kpi.recovery_ni_pct:.2f}%")
    e2.metric("Извлечение Ni после (топ-5)", f"{kpi.new_recovery_ni_pct:.2f}%",
              f"+{kpi.new_recovery_ni_pct - kpi.recovery_ni_pct:.2f} п.п.")
    e3.metric("Содержание Ni в хвостах", f"{kpi.tail_ni_pct:.3f}%",
              f"→ {kpi.new_tail_ni_pct:.3f}% прогноз", delta_color="inverse")
    e4.metric("Эффект портфеля топ-5", f"{kpi.portfolio_musd:.1f} M$/год")

    st.markdown(
        f"**Потолок эффекта:** {kpi.ceiling_musd:.1f} млн $/год — стоимость всего "
        f"извлекаемого металла в хвостах ({kpi.recoverable_ni_t:,.0f} т Ni + "
        f"{kpi.recoverable_cu_t:,.0f} т Cu). "
        f"**Портфель топ-5 гипотез** отыгрывает ≈ {kpi.portfolio_musd:.1f} млн $/год "
        f"(Ni +{kpi.portfolio_ni_t:,.0f} т, Cu +{kpi.portfolio_cu_t:,.0f} т).")

    colS, colD = st.columns(2)
    with colS:
        st.markdown("**Чувствительность к ценам металлов**")
        sdf = pd.DataFrame(kpi.sensitivity).set_index("scenario")
        st.bar_chart(sdf)
    with colD:
        st.markdown("**Вклад причин в потери (стоимость), M$/год**")
        cdf = pd.DataFrame([
            {"Причина": f.code, "M$": round(f.value_musd, 1)}
            for f in diag.findings if f.code != "RECOVERABLE_CEILING"
        ])
        if not cdf.empty:
            st.bar_chart(cdf.groupby("Причина")["M$"].sum())
    st.caption("Оценки ориентировочные (цены Ni/Cu настраиваются слева); "
               "содержание шихты — по типовому балансу отчёта.")

# ===== Экспорт =====
with tab3:
    st.subheader("Экспорт результатов")
    top_n = st.number_input("Сколько гипотез включить в отчёт", 1, len(hyps),
                            min(8, len(hyps)))
    colx, coly, colz = st.columns(3)
    with colx:
        if st.button("📄 Сформировать DOCX-отчёт"):
            out = os.path.join(tempfile.gettempdir(), f"{diag.plant}_гипотезы.docx")
            build_docx(diag, hyps, out, top_n=int(top_n))
            with open(out, "rb") as f:
                st.download_button("Скачать DOCX", f.read(),
                                   file_name=f"{diag.plant}_гипотезы.docx")
    with coly:
        st.download_button("📊 Скачать CSV (Jira/YouTrack)",
                           hypotheses_to_csv(hyps),
                           file_name=f"{diag.plant}_гипотезы.csv")
    with colz:
        st.download_button("🔗 Скачать JSON (API)",
                           hypotheses_to_json(hyps),
                           file_name=f"{diag.plant}_гипотезы.json")

    st.markdown("---")
    st.markdown("**Предпросмотр таблицы задач:**")
    prev = pd.DataFrame([{
        "Ранг": i + 1, "Гипотеза": h.title, "Score": round(h.score, 2),
        "Эффект,M$": round(h.value_musd, 1), "Класс": h.size_class,
        "Передел": h.stage,
    } for i, h in enumerate(hyps)])
    st.dataframe(prev, use_container_width=True)
