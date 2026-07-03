"""
Визуальный слой «control-room»: единая дизайн-система для Streamlit-приложения.
Тёмный сланцевый фон, приборная типографика, акценты никель/медь (Ni/Cu),
тонкие линии, никаких дефолтных стримлитовских «карточек с эмодзи».

Экспортирует inject_css() и набор HTML-рендереров.
"""
import html as _html

# --- Палитра -----------------------------------------------------------------
GROUND = "#0b1620"      # почти чёрный сланец
GROUND2 = "#0e1a24"
PANEL = "#122232"
PANEL2 = "#0f1d29"
LINE = "#1f3547"
LINE_SOFT = "#18293700"
INK = "#eaf1f7"
DIM = "#93a9ba"
FAINT = "#61788b"
COPPER = "#e0954f"      # медь — главный акцент
COPPER_D = "#c2793a"
NICKEL = "#9cc0d8"      # никель — структурный акцент
TEAL = "#4fc2a3"        # good
STEEL = "#6fa0c8"       # undergrind
AMBER = "#e6b055"       # slimes
SLATE = "#9488bd"       # midgrind


def esc(s):
    return _html.escape(str(s))


def inject_css():
    return f"""
<style>
/* ---- шрифты: системные, без CDN (не «иишный» дефолт, приборный вид) ---- */
:root {{
  --ground:{GROUND}; --panel:{PANEL}; --panel2:{PANEL2}; --line:{LINE};
  --ink:{INK}; --dim:{DIM}; --faint:{FAINT};
  --copper:{COPPER}; --nickel:{NICKEL}; --teal:{TEAL};
  --steel:{STEEL}; --amber:{AMBER}; --slate:{SLATE};
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
}}

/* фон приложения */
.stApp {{
  background:
    radial-gradient(1100px 480px at 82% -10%, #16303f55 0%, transparent 62%),
    linear-gradient(180deg, {GROUND2} 0%, {GROUND} 100%);
  color: var(--ink);
}}
/* прячем стандартный хедер/меню/футер Streamlit — чище, менее «шаблонно» */
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
.block-container {{ padding-top: 1.4rem; max-width: 1220px; }}

/* ---- сайдбар как приборная панель ---- */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, {PANEL} 0%, {PANEL2} 100%);
  border-right: 1px solid var(--line);
}}
section[data-testid="stSidebar"] * {{ color: var(--ink); }}
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] label {{ color: var(--dim) !important; font-size: 13px; }}

/* заголовки */
h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.01em; }}

/* ---- хиро ---- */
.hero {{ border-bottom: 1px solid var(--line); padding: 4px 0 20px; margin-bottom: 8px; }}
.hero .eyebrow {{
  font-family: var(--mono); font-size: 11.5px; letter-spacing: .22em;
  text-transform: uppercase; color: var(--copper); margin-bottom: 10px;
}}
.hero h1 {{ font-size: 34px; font-weight: 680; margin: 0 0 8px; line-height: 1.05; }}
.hero .sub {{ color: var(--dim); font-size: 15px; max-width: 76ch; line-height: 1.55; }}
.hero .sub b.ni {{ color: var(--nickel); }} .hero .sub b.cu {{ color: var(--copper); }}
.hero .tags {{ margin-top: 14px; display:flex; flex-wrap:wrap; gap:8px; }}
.hero .tags span {{
  font-family: var(--mono); font-size: 11px; color: var(--nickel);
  border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px;
  background: var(--panel2);
}}
.hero .tags b {{ color: var(--copper); }}

/* ---- KPI-полоса ---- */
.kpirow {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background: var(--line); border:1px solid var(--line); border-radius:14px;
  overflow:hidden; margin: 6px 0 4px; }}
.kpi {{ background: linear-gradient(180deg,{PANEL} 0%,{PANEL2} 100%); padding:16px 18px 14px; }}
.kpi .l {{ font-size:11.5px; color:var(--faint); text-transform:uppercase; letter-spacing:.07em; }}
.kpi .v {{ font-family:var(--mono); font-size:25px; font-weight:600; margin-top:5px;
  font-variant-numeric: tabular-nums; letter-spacing:-.01em; }}
.kpi .v small {{ font-size:14px; font-weight:500; opacity:.8; }}
.kpi .n {{ font-size:12px; color:var(--dim); margin-top:3px; }}

/* ---- секции ---- */
.sec-label {{ font-family:var(--mono); font-size:12px; letter-spacing:.16em;
  text-transform:uppercase; color:var(--faint); margin:26px 0 12px;
  padding-bottom:9px; border-bottom:1px solid var(--line); }}

/* ---- находки диагностики ---- */
.find {{ background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--nickel);
  border-radius:11px; padding:13px 16px; margin-bottom:10px; }}
.find.ceiling {{ border-left-color:var(--teal); background:#0e2620; }}
.find .h {{ font-weight:600; color:var(--ink); font-size:14.5px; display:flex; justify-content:space-between; gap:12px; }}
.find .cost {{ font-family:var(--mono); color:var(--copper); font-size:13px; white-space:nowrap; }}
.find .d {{ color:var(--dim); font-size:13px; margin-top:6px; line-height:1.55; }}

/* ---- карточки гипотез ---- */
.hyp {{ background:linear-gradient(180deg,{PANEL} 0%,{PANEL2} 100%);
  border:1px solid var(--line); border-top:3px solid var(--nickel);
  border-radius:13px; padding:16px 18px; margin-bottom:14px; }}
.hyp .top {{ display:flex; align-items:baseline; gap:13px; }}
.hyp .rank {{ font-family:var(--mono); font-size:19px; font-weight:700; color:var(--copper); min-width:26px; }}
.hyp .title {{ flex:1; font-size:16.5px; font-weight:600; color:var(--ink); line-height:1.25; }}
.hyp .score {{ font-family:var(--mono); color:var(--nickel); font-size:13px; white-space:nowrap; }}
.hyp .llm {{ font-size:10px; padding:2px 7px; border-radius:5px; background:#0e2620;
  color:var(--teal); border:1px solid #1c4a3d; margin-left:6px; vertical-align:middle; }}
.hyp .metrics {{ display:flex; flex-wrap:wrap; gap:14px; margin:11px 0; font-size:12.5px; color:var(--dim);
  font-variant-numeric: tabular-nums; }}
.hyp .metrics b {{ color:var(--ink); font-family:var(--mono); }}
.hyp .chip {{ font-family:var(--mono); font-size:10.5px; padding:2px 9px; border-radius:6px; }}
.hyp .rat {{ color:var(--ink); font-size:14px; line-height:1.58; margin:6px 0 9px; }}
.hyp .mech, .hyp .succ, .hyp .equip {{ color:var(--dim); font-size:13px; margin:5px 0; line-height:1.5; }}
.hyp .mech b, .hyp .succ b {{ color:var(--nickel); font-weight:600; }}
.hyp .road {{ font-size:12.5px; color:var(--dim); margin:7px 0; }}
.hyp .road b {{ color:var(--nickel); }} .hyp .road ol {{ margin:5px 0 0 18px; padding:0; }}
.hyp .cites {{ font-size:12px; color:var(--faint); margin-top:9px; border-top:1px dashed var(--line); padding-top:8px; }}
.hyp .cites i {{ color:var(--dim); }}
.hyp .fb {{ font-family:var(--mono); font-size:11.5px; color:var(--dim); margin-top:8px; }}

/* ---- экономика ---- */
.ecard {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:15px 17px; }}
.ecard .l {{ font-size:11.5px; color:var(--faint); text-transform:uppercase; letter-spacing:.06em; }}
.ecard .v {{ font-family:var(--mono); font-size:22px; font-weight:600; margin-top:5px; color:var(--ink);
  font-variant-numeric: tabular-nums; }}
.ecard .n {{ font-size:12px; color:var(--dim); margin-top:3px; }}

/* ---- вкладки ---- */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ color: var(--dim); font-weight: 500; }}
.stTabs [aria-selected="true"] {{ color: var(--copper) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--copper) !important; }}

/* ---- кнопки ---- */
.stButton > button {{ border:1px solid var(--line); background:var(--panel2); color:var(--ink);
  border-radius:9px; font-weight:500; transition: all .15s; }}
.stButton > button:hover {{ border-color:var(--copper); color:var(--copper); }}

/* уменьшаем визуальный шум дефолтных виджетов */
[data-testid="stMetric"] {{ background:var(--panel); border:1px solid var(--line);
  border-radius:11px; padding:12px 14px; }}
[data-testid="stMetricLabel"] {{ color: var(--faint) !important; }}

.welcome {{ background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--copper);
  border-radius:12px; padding:22px 24px; color:var(--dim); font-size:15px; line-height:1.6; }}
.welcome b {{ color: var(--copper); }}
</style>
"""


# --- Рендереры ---------------------------------------------------------------
def hero_html(yandex_ready: bool):
    dot = ("<span>🟢 Yandex GPT</span>" if yandex_ready
           else "<span>офлайн-режим</span>")
    return f"""
<div class='hero'>
  <div class='eyebrow'>Норникель AI Science Hack · Фабрика гипотез</div>
  <h1>Снижение потерь металла с хвостами обогащения</h1>
  <div class='sub'>Система превращает отчёт по хвостам обогатительной фабрики в
    ранжированные проверяемые инженерные гипотезы — с диагностикой причин потерь,
    обоснованием, ссылками на источники и оценкой эффекта.
    <b class='ni'>Элемент 28 = никель</b>, <b class='cu'>Элемент 29 = медь</b>.</div>
  <div class='tags'>
    <span>диагностика на <b>физике процесса</b></span>
    <span>обоснование · <b>Yandex GPT</b></span>
    <span>цитаты из <b>учебников</b></span>
    <span>ноль выдуманных чисел</span>
    {dot}
  </div>
</div>"""


def kpi_row_html(report, ceiling_musd):
    def cell(l, v, n, color=INK):
        return (f"<div class='kpi'><div class='l'>{esc(l)}</div>"
                f"<div class='v' style='color:{color}'>{v}</div>"
                f"<div class='n'>{esc(n)}</div></div>")
    return ("<div class='kpirow'>"
            + cell("Хвосты, т/год", f"{report.tail_mass_t:,.0f}", "образование хвостов", NICKEL)
            + cell("Потери Ni", f"{report.tail_el28_t:,.0f} <small>т</small>",
                   f"{report.tail_el28_pct:.3f}% в хвостах", STEEL)
            + cell("Потери Cu", f"{report.tail_el29_t:,.0f} <small>т</small>",
                   f"{report.tail_el29_pct:.3f}% в хвостах", COPPER)
            + cell("Потолок эффекта", f"{ceiling_musd:.0f} <small>M$/год</small>",
                   "весь извлекаемый металл", TEAL)
            + "</div>")


def finding_html(f):
    icons = {"UNDERGRIND": "недоизмельчение", "SLIMES": "потеря шламов",
             "MIDGRIND": "средний класс"}
    colors = {"UNDERGRIND": STEEL, "SLIMES": AMBER, "MIDGRIND": SLATE}
    if f.code == "RECOVERABLE_CEILING":
        return (f"<div class='find ceiling'><div class='h'>{esc(f.headline)}</div>"
                f"<div class='d'>{esc(f.detail)}</div></div>")
    col = colors.get(f.code, NICKEL)
    tag = icons.get(f.code, f.code)
    return (f"<div class='find' style='border-left-color:{col}'>"
            f"<div class='h'><span>{esc(f.headline)}</span>"
            f"<span class='cost'>≈{f.value_musd:.1f} M$/год</span></div>"
            f"<div class='d'><span style='color:{col};font-family:var(--mono);"
            f"font-size:11px;text-transform:uppercase;letter-spacing:.08em'>{esc(tag)}</span> — "
            f"{esc(f.detail)}</div></div>")


def hypothesis_html(i, h):
    colors = {"UNDERGRIND": STEEL, "SLIMES": AMBER, "MIDGRIND": SLATE}
    col = colors.get(h.trigger_finding, NICKEL)
    llm = getattr(h, "llm_rationale", "")
    rat = llm if llm else h.rationale
    llm_badge = "<span class='llm'>LLM</span>" if llm else ""
    fb_stats = getattr(h, "fb_stats", None)
    fb_line = ""
    if fb_stats:
        fb_line = (f"<div class='fb'>фидбэк · ✅{fb_stats.get('confirmed',0)} "
                   f"❌{fb_stats.get('refuted',0)} 🚫{fb_stats.get('rejected',0)} "
                   f"· ×{getattr(h,'fb_multiplier',1.0)}</div>")
    cites = ""
    if h.citations:
        cc = "".join(
            f"<div>«{esc(c['snippet'])}» — <i>{esc(c['source'])}"
            + (f", с.{c['page']}" if c.get('page') else "") + "</i></div>"
            for c in h.citations)
        cites = f"<div class='cites'>{cc}</div>"
    road = ""
    if h.roadmap:
        road = ("<div class='road'><b>Дорожная карта:</b><ol>"
                + "".join(f"<li>{esc(s)}</li>" for s in h.roadmap) + "</ol></div>")
    equip = (f"<div class='equip'>Оборудование: {esc(', '.join(h.equipment))} · передел: {esc(h.stage)}</div>"
             if h.equipment else "")
    return f"""
<div class='hyp' style='border-top-color:{col}'>
  <div class='top'>
    <div class='rank'>{i:02d}</div>
    <div class='title'>{esc(h.title)}{llm_badge}</div>
    <div class='score'>Score {h.score:.2f}</div>
  </div>
  <div class='metrics'>
    <span><b style='color:{COPPER}'>{h.value_musd:.1f}</b> M$/год</span>
    <span>реализуемость <b>{h.feasibility:.2f}</b></span>
    <span>новизна <b>{h.novelty:.2f}</b></span>
    <span>риск <b>{h.risk:.2f}</b></span>
    <span class='chip' style='background:{col}22;color:{col}'>{esc(h.trigger_finding)} · {esc(h.size_class)} мкм</span>
  </div>
  <div class='rat'>{esc(rat)}</div>
  <div class='mech'><b>Механизм.</b> {esc(h.mechanism)}</div>
  {equip}
  <div class='succ'><b>Критерий успеха.</b> {esc(h.success_criterion)}</div>
  {road}{cites}{fb_line}
</div>"""


def eco_cards_html(kpi):
    def c(l, v, n, color=INK):
        return (f"<div class='ecard'><div class='l'>{esc(l)}</div>"
                f"<div class='v' style='color:{color}'>{v}</div>"
                f"<div class='n'>{esc(n)}</div></div>")
    return {
        "recov": c("Извлечение Ni сейчас", f"{kpi.recovery_ni_pct:.2f}%", "по балансу шихта→хвосты", TEAL),
        "after": c("Извлечение Ni после (топ-5)", f"{kpi.new_recovery_ni_pct:.2f}%",
                   f"+{kpi.new_recovery_ni_pct-kpi.recovery_ni_pct:.2f} п.п. прогноз", TEAL),
        "tail": c("Ni в хвостах", f"{kpi.tail_ni_pct:.3f}% → {kpi.new_tail_ni_pct:.3f}%",
                  "снижение содержания", INK),
        "port": c("Эффект портфеля топ-5", f"{kpi.portfolio_musd:.1f} M$/год",
                  f"Ni +{kpi.portfolio_ni_t:,.0f}т · Cu +{kpi.portfolio_cu_t:,.0f}т", COPPER),
    }
