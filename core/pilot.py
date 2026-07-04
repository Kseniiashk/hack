"""
Протокол пилотной проверки гипотезы (pilot card).

Переводит гипотезу из «идеи» в готовый к цеху план A/B-опробования:
что делаем → зачем → ожидаемый эффект → риски → план пилота (длительность,
контрольный KPI, критерий stop/go) → что измерять ежедневно.

Всё выводится из уже посчитанных полей гипотезы (эффект, риск, критерий успеха,
дорожная карта) — новых чисел не выдумываем.
"""
from __future__ import annotations

# Ориентировочная длительность пилота по типу передела (недели).
STAGE_WEEKS = {
    "измельчение": (3, 4),
    "классификация": (2, 4),
    "дробление": (2, 3),
    "флотация": (2, 3),
    "классификация+измельчение": (4, 6),
    "дробление+измельчение": (4, 6),
}

# Что измерять ежедневно — по причине потерь.
DAILY_KPI = {
    "UNDERGRIND": "доля закрытого Pnt/Cp в целевом классе; крупность слива; циркулирующая нагрузка",
    "MIDGRIND": "доля сростков в среднем классе; гранулометрия слива",
    "SLIMES": "содержание раскрытого металла в классе −10 мкм в хвостах; плотность пульпы; извлечение тонких классов",
}


def pilot_card(h) -> dict:
    """Возвращает структурированный протокол пилота для гипотезы."""
    stage = getattr(h, "stage", "") or "флотация"
    wk = STAGE_WEEKS.get(stage, (2, 4))
    daily = DAILY_KPI.get(getattr(h, "trigger_finding", ""),
                          "целевой KPI по содержанию металла в хвостах")

    # Критерий stop/go: успех, если целевой KPI улучшился и нет роста шламов/потерь.
    lo = getattr(h, "value_low", 0.0)
    go = (f"KPI улучшился в сторону цели (см. критерий успеха), нижняя граница эффекта "
          f"≥ {lo:.1f} млн долл./год подтверждена, без роста потерь в смежных классах")
    stop = ("целевой KPI не сдвинулся за контрольный период или выросли потери в "
            "других классах крупности")

    # CAPEX и простой срок окупаемости.
    try:
        from core.capex import payback as _payback
        pb = _payback(h.id, h.value_musd)
        if pb["payback_years"] is not None:
            yrs = pb["payback_years"]
            pb_str = (f"{yrs*12:.0f} мес." if yrs < 1 else f"{yrs:.1f} года")
            capex_str = f"CAPEX ~{pb['capex_musd']:.1f} млн долл. ({pb['tier']}), окупаемость {pb_str}"
        else:
            capex_str = f"CAPEX ~{pb['capex_musd']:.1f} млн долл. ({pb['tier']})"
    except Exception:
        capex_str = ""

    return {
        "what": h.title,
        "why": h.mechanism,
        "effect": (f"{getattr(h,'value_low',0):.1f} … {h.value_musd:.1f} … "
                   f"{getattr(h,'value_high',0):.1f} млн долл./год"),
        "capex": capex_str,
        "risk": (f"технический {getattr(h,'risk_tech',0):.2f} / "
                 f"экономический {getattr(h,'risk_econ',0):.2f}"),
        "design": "A/B: контрольная секция (без изменений) против опытной (с вмешательством), "
                  "сопоставимая руда и режим",
        "duration": f"{wk[0]}–{wk[1]} недель",
        "success": h.success_criterion or "снижение потерь металла в целевом классе",
        "go": go,
        "stop": stop,
        "daily": daily,
        "steps": h.roadmap or [],
        "equipment": h.equipment or [],
    }


def pilot_card_text(h) -> str:
    """Человекочитаемый протокол пилота (для docx/экспорта)."""
    c = pilot_card(h)
    lines = [
        f"ПРОТОКОЛ ПИЛОТА: {c['what']}",
        f"Что делаем: {c['what']}",
        f"Зачем (механизм): {c['why']}",
        f"Ожидаемый эффект: {c['effect']}",
        f"Риски: {c['risk']}",
        f"Дизайн: {c['design']}",
        f"Длительность: {c['duration']}",
        f"Критерий успеха: {c['success']}",
        f"GO (продолжаем/масштабируем): {c['go']}",
        f"STOP (сворачиваем): {c['stop']}",
        f"Мерить ежедневно: {c['daily']}",
    ]
    if c["equipment"]:
        lines.append(f"Оборудование: {', '.join(c['equipment'])}")
    if c["steps"]:
        lines.append("Шаги: " + "; ".join(c["steps"]))
    return "\n".join(lines)


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose
    from core.generate import generate
    base = os.environ.get("CASE_DIR", "data/examples")
    rep = parse_tailings_xlsx(f"{base}/КГМК.xlsx", "КГМК")
    hyps = generate(diagnose(rep), report=rep)
    print(pilot_card_text(hyps[0]))
