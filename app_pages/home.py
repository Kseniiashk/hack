"""Главная — посадочная страница (лендинг)."""
import os
import streamlit as st
import ui_theme as ui

st.markdown(ui.landing_hero_html(), unsafe_allow_html=True)

# CTA
c1, c2, c3 = st.columns([2, 1.2, 2])
with c2:
    if st.button("Открыть анализ  →", type="primary", use_container_width=True):
        st.switch_page("app_pages/analyze.py")

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown("<div class='sec-label'>Что делает система</div>", unsafe_allow_html=True)
st.markdown(ui.landing_features_html(), unsafe_allow_html=True)

st.markdown("<div class='sec-label'>Как это работает</div>", unsafe_allow_html=True)
st.markdown(ui.landing_flow_html(), unsafe_allow_html=True)

st.markdown("<div class='sec-label'>Проверено на данных кейса</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='kpirow'>"
    "<div class='kpi'><div class='l'>КГМК</div><div class='v' style='color:#e0954f'>149 "
    "<small>M$/год</small></div><div class='n'>потолок эффекта</div></div>"
    "<div class='kpi'><div class='l'>ТОФ</div><div class='v' style='color:#e0954f'>137 "
    "<small>M$/год</small></div><div class='n'>потолок эффекта</div></div>"
    "<div class='kpi'><div class='l'>НОФ медистые</div><div class='v' style='color:#e0954f'>68 "
    "<small>M$/год</small></div><div class='n'>потолок эффекта</div></div>"
    "<div class='kpi'><div class='l'>НОФ вкрапленные</div><div class='v' style='color:#e0954f'>43 "
    "<small>M$/год</small></div><div class='n'>потолок эффекта</div></div>"
    "</div>", unsafe_allow_html=True)

_yready = bool(os.environ.get("YANDEX_API_KEY") and os.environ.get("YANDEX_FOLDER_ID"))
st.markdown(
    f"<div style='text-align:center;margin-top:22px;color:#61788b;font-size:13px'>"
    f"Элемент 28 = никель · Элемент 29 = медь · "
    f"{'LLM-обоснование через Yandex GPT подключено' if _yready else 'офлайн-режим'}"
    f"</div>", unsafe_allow_html=True)
