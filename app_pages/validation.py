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
CASE_DIR = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"

FILES = {
    "КГМК": ("КГМК.xlsx", "Пример 1/Хвосты КГМК.xlsx"),
    "НОФ-вкр": ("НОФ-вкр.xlsx", "Пример 2/Хвосты НОФ Вкр.xlsx"),
    "НОФ-мед": ("НОФ-мед.xlsx", "Пример 3/Хвосты НОФ мед.xlsx"),
    "ТОФ": ("ТОФ.xlsx", "Пример 4/Хвосты ТОФ_2.xlsx"),
}


def path_of(plant):
    bundled, case_rel = FILES[plant]
    p = os.path.join(EXAMPLES_DIR, bundled)
    if os.path.exists(p):
        return p
    p = os.path.join(CASE_DIR, case_rel)
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
st.caption(
    "Метрика — покрытие (recall): какую долю экспертных гипотез система воспроизводит. "
    "Не «угадывание»: система выходит на те же инженерные решения из физики процесса, "
    "и вдобавок предлагает варианты, которых в экспертном списке не было.")

st.markdown("<div class='rule'>По фабрикам</div>", unsafe_allow_html=True)
for plant in FILES:
    st.markdown(t.validation_plant(res[plant]), unsafe_allow_html=True)

st.markdown("<div class='note'>Число рядом с гипотезой — её место в нашем ранжированном "
            "списке. Прочерк — экспертная гипотеза не попала в верхние k (показываем честно, "
            "без подгонки матчинга).</div>", unsafe_allow_html=True)
