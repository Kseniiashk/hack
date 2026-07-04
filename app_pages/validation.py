import os
import sys

import streamlit as st

import ui_theme as t
from core.ingest import parse_tailings_xlsx
from core.diagnose import diagnose
from core.generate import generate
from core.validate import validate_all, load_gold

ROOT = next((p for p in sys.path if os.path.isdir(os.path.join(p, "core"))), ".")
EXAMPLES_DIR = os.path.join(ROOT, "data", "examples")

FILES = {
    "КГМК": "КГМК.xlsx",
    "НОФ-вкр": "НОФ-вкр.xlsx",
    "НОФ-мед": "НОФ-мед.xlsx",
    "ТОФ": "ТОФ.xlsx",
}


def path_of(plant):
    p = os.path.join(EXAMPLES_DIR, FILES[plant])
    return p if os.path.exists(p) else None


@st.cache_data(show_spinner="Прогон по фабрикам…")
def run(k):
    def titles(plant):
        rep = parse_tailings_xlsx(path_of(plant), plant)
        return [h.title for h in generate(diagnose(rep))]
    res = validate_all(titles, k=k)
    return {p: res[p] for p in FILES} | {"_overall": res["_overall"]}


st.markdown(t.page_header(
    "Валидация",
    "К данным о хвостах организаторы приложили гипотезы, которые вручную составили "
    "эксперты Компании. Система прогоняется на тех же фабриках, и мы проверяем, покрывает "
    "ли она экспертные предложения. Совпадение считается по инженерному смыслу — "
    "по узлу схемы (мельница, гидроциклон, флотация…) и действию (замена, изменение, "
    "добавление), а не по совпадению слов. Один и тот же узел засчитывается один раз."),
    unsafe_allow_html=True)

if not load_gold():
    st.warning("Эталонные гипотезы не найдены.")
    st.stop()

k = st.slider("Учитывать верхние k гипотез", 5, 18, 12)
res = run(k)

st.markdown(t.validation_summary(res["_overall"]), unsafe_allow_html=True)

ov = res["_overall"]
# сводка метрик одной строкой: покрыто / лишнее / средняя точность
avg_prec = sum(res[p].precision_topk for p in FILES) / len(FILES)
m1, m2, m3 = st.columns(3)
m1.metric("Покрытие экспертов", f"{ov['recall']:.0%}", f"{ov['matched']}/{ov['total_gold']}")
m2.metric("Предложено сверх", f"{ov['extra']}", "инженерных вариантов")
m3.metric("Точность топ-k", f"{avg_prec:.0%}", "совпало с эталоном")

st.caption(
    "Метрика — покрытие (recall): какую долю экспертных гипотез система воспроизводит. "
    "Точность топ-k ниже намеренно: система выдаёт больше проверенных вариантов, чем "
    "было в коротком экспертном списке, поэтому «лишнее» — это плюс, а не ошибка. "
    "Матчинг мягкий (по инженерному смыслу), консервативный: одна наша гипотеза "
    "засчитывается только одному эталону, без повторного использования.")

st.markdown("<div class='rule'>По фабрикам</div>", unsafe_allow_html=True)
for plant in FILES:
    st.markdown(t.validation_plant(res[plant]), unsafe_allow_html=True)

# Главный дифференциатор: что система предложила сверх экспертов
extras = []
for plant in FILES:
    for x in res[plant].extra:
        if x not in extras:
            extras.append(x)
if extras:
    st.markdown("<div class='rule'>Предложено сверх экспертного списка</div>",
                unsafe_allow_html=True)
    st.caption("Инженерно обоснованные варианты, которых не было в коротком "
               "мозговом штурме экспертов — система находит их из физики процесса.")
    for x in extras[:5]:
        st.markdown(t.extra_row(x), unsafe_allow_html=True)

st.markdown("<div class='rule'>Границы применимости</div>", unsafe_allow_html=True)
st.markdown(
    "- Совпадение считается по инженерному смыслу (узел + действие), а не по словам — "
    "поэтому «мягкое» и устойчивое к формулировкам.\n"
    "- Эталон — короткий мозговой штурм экспертов; расхождение в отдельных пунктах "
    "нормально и показано честно.\n"
    "- Метрика подтверждает осмысленность выводов, но не заменяет пилотную проверку "
    "гипотез на фабрике.")
