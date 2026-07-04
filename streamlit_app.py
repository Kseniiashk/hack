"""
Фабрика гипотез — многостраничный веб-сайт (Streamlit).

Точка входа с навигацией: Главная · Анализ · О проекте.
Общая инициализация (пути, ключ Yandex, тема) — здесь; страницы в app_pages/.
"""
import os
import sys

# Находим корень проекта (папку с core/) — работает и в корне репо, и локально.
_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = _HERE
for _cand in (_HERE, os.path.dirname(_HERE)):
    if os.path.isdir(os.path.join(_cand, "core")):
        PROJECT_ROOT = _cand
        break
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

try:
    from core import load_dotenv
    load_dotenv()
except Exception:
    pass

import streamlit as st

st.set_page_config(page_title="Фабрика гипотез", page_icon="⚗️", layout="wide")

# Ключ Yandex из st.secrets → окружение (для core/llm.py на Streamlit Cloud).
try:
    for _k in ("YANDEX_API_KEY", "YANDEX_FOLDER_ID", "YANDEX_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

import ui_theme
st.markdown(ui_theme.css(), unsafe_allow_html=True)

pages = [
    st.Page("app_pages/home.py", title="Главная", default=True),
    st.Page("app_pages/analyze.py", title="Анализ"),
    st.Page("app_pages/validation.py", title="Валидация"),
    st.Page("app_pages/about.py", title="О проекте"),
]
st.navigation(pages, position="sidebar").run()
