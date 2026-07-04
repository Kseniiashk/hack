"""Оформление интерфейса: тёмная сдержанная тема и рендер блоков.

Здесь только внешний вид — вся логика в core/. Стиль минималистичный:
плоские поверхности, тонкие разделители, один спокойный акцент, без градиентов
и декоративных плашек. Числа — моноширинным, текст — обычным.
"""
import html


# Спокойная тёмная палитра. Один акцент (охра) на важные числа.
BG = "#14171a"
SURFACE = "#1b1f23"
BORDER = "#2b3137"
TEXT = "#dfe3e6"
MUTED = "#9aa4ac"
FAINT = "#697079"
ACCENT = "#c98a4b"
GOOD = "#6fae8e"
WARN = "#c9a24b"


def e(x):
    return html.escape(str(x))


def css():
    return f"""
<style>
:root {{ --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}

.stApp {{ background: {BG}; color: {TEXT}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ max-width: 1080px; padding-top: 2rem; }}

section[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}

h1, h2, h3, h4 {{ color: {TEXT}; font-weight: 600; }}
a {{ color: {ACCENT}; }}

/* заголовок раздела: просто подпись сверху с чертой */
.page-title {{ font-size: 26px; font-weight: 600; margin: 0 0 4px; }}
.page-note {{ color: {MUTED}; font-size: 14px; max-width: 70ch; line-height: 1.5;
  margin: 0 0 20px; }}
.rule {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: {FAINT}; margin: 24px 0 10px; padding-bottom: 6px;
  border-bottom: 1px solid {BORDER}; }}

/* сводка: ряд чисел без плашек, разделённых линиями */
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr);
  border: 1px solid {BORDER}; border-radius: 6px; }}
.summary .cell {{ padding: 12px 16px; border-right: 1px solid {BORDER}; }}
.summary .cell:last-child {{ border-right: none; }}
.summary .k {{ font-size: 12px; color: {FAINT}; }}
.summary .v {{ font-family: var(--mono); font-size: 20px; margin-top: 4px;
  font-variant-numeric: tabular-nums; }}
.summary .u {{ font-size: 12px; color: {MUTED}; margin-top: 2px; }}

/* находки — строки списка, слева тонкая метка причины */
.finding {{ padding: 12px 0; border-bottom: 1px solid {BORDER}; }}
.finding:last-child {{ border-bottom: none; }}
.finding .head {{ display: flex; justify-content: space-between; gap: 16px; }}
.finding .name {{ color: {TEXT}; font-size: 14px; }}
.finding .cost {{ font-family: var(--mono); color: {MUTED}; white-space: nowrap; }}
.finding .cause {{ font-family: var(--mono); font-size: 11px; color: {FAINT};
  text-transform: uppercase; letter-spacing: .05em; }}
.finding .desc {{ color: {MUTED}; font-size: 13px; margin-top: 5px; line-height: 1.5; }}

/* гипотеза — заголовок с номером, метрики строкой, текст ниже. без карточки */
.hyp {{ padding: 16px 0; border-bottom: 1px solid {BORDER}; }}
.hyp .head {{ display: flex; gap: 12px; align-items: baseline; }}
.hyp .num {{ font-family: var(--mono); color: {FAINT}; }}
.hyp .name {{ flex: 1; font-size: 16px; font-weight: 600; color: {TEXT}; }}
.hyp .val {{ font-family: var(--mono); color: {ACCENT}; white-space: nowrap; }}
.hyp .range {{ color: {FAINT}; font-size: 12px; }}
.hyp .meta {{ font-family: var(--mono); font-size: 12px; color: {MUTED};
  margin: 8px 0; }}
.hyp .body {{ color: {TEXT}; font-size: 14px; line-height: 1.6; margin: 6px 0; }}
.hyp .line {{ color: {MUTED}; font-size: 13px; margin: 4px 0; line-height: 1.5; }}
.hyp .line b {{ color: {TEXT}; font-weight: 600; }}
.hyp .cite {{ color: {FAINT}; font-size: 12px; margin-top: 8px; padding-left: 12px;
  border-left: 2px solid {BORDER}; line-height: 1.5; }}

/* вкладки — простые, без подсветки-плашки */
.stTabs [data-baseweb="tab-list"] {{ display: flex; flex-direction: row;
  flex-wrap: wrap; gap: 4px; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{ color: {MUTED}; padding: 8px 14px; }}
.stTabs [aria-selected="true"] {{ color: {TEXT}; }}

.stButton > button {{ background: {SURFACE}; color: {TEXT};
  border: 1px solid {BORDER}; border-radius: 5px; }}
.stButton > button:hover {{ border-color: {ACCENT}; }}

.note {{ color: {FAINT}; font-size: 12px; margin-top: 8px; }}
</style>
"""


def page_header(title, note=""):
    out = f"<div class='page-title'>{e(title)}</div>"
    if note:
        out += f"<div class='page-note'>{e(note)}</div>"
    return out


def summary(report, ceiling_musd):
    def cell(k, v, u):
        return (f"<div class='cell'><div class='k'>{e(k)}</div>"
                f"<div class='v'>{v}</div><div class='u'>{e(u)}</div></div>")
    return ("<div class='summary'>"
            + cell("Хвосты, т/год", f"{report.tail_mass_t:,.0f}", "образование")
            + cell("Ni в хвостах", f"{report.tail_el28_t:,.0f}",
                   f"{report.tail_el28_pct:.3f}%")
            + cell("Cu в хвостах", f"{report.tail_el29_t:,.0f}",
                   f"{report.tail_el29_pct:.3f}%")
            + cell("Потолок эффекта", f"{ceiling_musd:.0f}", "млн $/год")
            + "</div>")


def finding(f):
    labels = {"UNDERGRIND": "недоизмельчение", "SLIMES": "потеря шламов",
              "MIDGRIND": "средний класс", "RECOVERABLE_CEILING": "итог"}
    lbl = labels.get(f.code, f.code.lower())
    if f.code == "RECOVERABLE_CEILING":
        return (f"<div class='finding'><div class='head'><span class='name'>"
                f"{e(f.headline)}</span></div>"
                f"<div class='desc'>{e(f.detail)}</div></div>")
    return (f"<div class='finding'>"
            f"<div class='cause'>{e(lbl)}</div>"
            f"<div class='head'><span class='name'>{e(f.headline)}</span>"
            f"<span class='cost'>{f.value_musd:.1f} млн $/год</span></div>"
            f"<div class='desc'>{e(f.detail)}</div></div>")


def hypothesis(i, h):
    body = getattr(h, "llm_rationale", "") or h.rationale
    lo, hi = getattr(h, "value_low", 0), getattr(h, "value_high", 0)
    rng = f" <span class='range'>({lo:.1f}–{hi:.1f})</span>" if hi else ""
    equip = ""
    if h.equipment:
        equip = (f"<div class='line'><b>Оборудование:</b> {e(', '.join(h.equipment))} · "
                 f"передел: {e(h.stage)}</div>")
    road = ""
    if h.roadmap:
        steps = "; ".join(h.roadmap)
        road = f"<div class='line'><b>Проверка:</b> {e(steps)}</div>"
    cite = ""
    if h.citations:
        cc = " · ".join(f"{e(c['source'])}"
                        + (f", с.{c['page']}" if c.get('page') else "")
                        for c in h.citations)
        cite = f"<div class='cite'>{e(h.citations[0]['snippet'])} — {cc}</div>"
    return (f"<div class='hyp'>"
            f"<div class='head'><span class='num'>{i:02d}</span>"
            f"<span class='name'>{e(h.title)}</span>"
            f"<span class='val'>{h.value_musd:.1f} млн $/год{rng}</span></div>"
            f"<div class='meta'>score {h.score:.2f} · реализуемость {h.feasibility:.2f} · "
            f"новизна {h.novelty:.2f} · риск {h.risk:.2f} · {e(h.trigger_finding.lower())} "
            f"· класс {e(h.size_class)} мкм</div>"
            f"<div class='body'>{e(body)}</div>"
            f"<div class='line'><b>Механизм:</b> {e(h.mechanism)}</div>"
            f"{equip}"
            f"<div class='line'><b>Критерий успеха:</b> {e(h.success_criterion)}</div>"
            f"{road}{cite}</div>")


def eco_summary(kpi):
    def cell(k, v, u):
        return (f"<div class='cell'><div class='k'>{e(k)}</div>"
                f"<div class='v'>{v}</div><div class='u'>{e(u)}</div></div>")
    return ("<div class='summary'>"
            + cell("Извлечение Ni", f"{kpi.recovery_ni_pct:.2f}%", "сейчас")
            + cell("После портфеля", f"{kpi.new_recovery_ni_pct:.2f}%",
                   f"+{kpi.new_recovery_ni_pct - kpi.recovery_ni_pct:.2f} п.п.")
            + cell("Ni в хвостах", f"{kpi.tail_ni_pct:.3f}%",
                   f"прогноз {kpi.new_tail_ni_pct:.3f}%")
            + cell("Эффект топ-5", f"{kpi.portfolio_musd:.1f}", "млн $/год")
            + "</div>")


# --- Валидация ---------------------------------------------------------------
def validation_summary(overall):
    r = overall["recall"]
    return (f"<div style='padding:20px 0 4px'>"
            f"<span style='font-family:var(--mono);font-size:52px;font-weight:600;"
            f"color:{GOOD if r>=0.9 else WARN}'>{r:.0%}</span>"
            f"<div style='color:{MUTED};font-size:14px;margin-top:4px'>"
            f"совпадение с гипотезами экспертов — {overall['matched']} из "
            f"{overall['total_gold']} на {overall['plants']} фабриках</div></div>")


def validation_plant(r):
    rows = ""
    for m in r.matches:
        rows += (f"<div style='padding:5px 0;font-size:13px;color:{TEXT};"
                 f"border-top:1px solid {BORDER}'>"
                 f"<span style='font-family:var(--mono);color:{ACCENT};"
                 f"margin-right:10px'>#{m['rank']}</span>{e(m['gold'])}</div>")
    for g in r.missed:
        rows += (f"<div style='padding:5px 0;font-size:13px;color:{FAINT};"
                 f"border-top:1px solid {BORDER}'>"
                 f"<span style='font-family:var(--mono);margin-right:10px'>—</span>"
                 f"{e(g)}</div>")
    return (f"<div style='margin-bottom:18px'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:15px;color:{TEXT};margin-bottom:4px'>"
            f"<b>{e(r.plant)}</b>"
            f"<span style='font-family:var(--mono);color:{GOOD if r.recall>=0.9 else WARN}'>"
            f"{r.recall:.0%} ({r.matched_gold}/{r.n_gold})</span></div>"
            f"{rows}</div>")
