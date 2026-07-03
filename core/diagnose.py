"""
Diagnostic Engine — превращает TailingsReport в список интерпретируемых находок (findings).

Каждая находка — числовой факт о том, ГДЕ и ПОЧЕМУ теряется извлекаемый металл.
Находки — это триггеры для генератора гипотез. Никаких «чёрных ящиков»:
вся логика — явные правила на физике процесса обогащения.

Две фундаментальные причины потерь извлекаемого металла:
  1) UNDERGRIND (недоизмельчение): металл заперт в сростках ('Закрытый Pnt/Cp')
     в крупных классах (+125, +71, -71+45). Раскрытие -> доизмельчение/классификация.
  2) SLIMES (переизмельчение/шламы): раскрытый металл в тонком классе -10 мкм,
     который физически теряется во флотации. Лечение -> флотация шламов, реагенты,
     время флотации, плотность пульпы.

Плюс агрегаты: KPI-потолок (сколько извлекаемого металла теряется всего), деньги.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import json

from core.ingest import TailingsReport, SizeClassRow, ELEMENTS

# Классы, считающиеся «крупными» (недоизмельчение) и «тонким шламом».
COARSE = {"+125", "+71", "-71 + 45"}
MID = {"-45 + 20", "-20 + 10"}
SLIME = "-10"


@dataclass
class Finding:
    code: str                 # UNDERGRIND | SLIMES | MIDGRIND | RECOVERABLE_CEILING
    element: str              # Ni | Cu | Ni+Cu
    size_class: str = ""      # класс крупности, если применимо
    severity: float = 0.0     # 0..1, для сортировки/визуализации
    lost_recoverable_t: float = 0.0   # извлекаемый, но потерянный металл, т/год
    value_musd: float = 0.0   # оценочная стоимость этих потерь, млн $/год
    headline: str = ""        # человекочитаемый заголовок
    detail: str = ""          # подробное объяснение с числами
    evidence: dict = field(default_factory=dict)  # опорные числа


@dataclass
class Diagnosis:
    report_name: str = ""
    plant: str = ""
    total_recoverable_lost_t_ni: float = 0.0
    total_recoverable_lost_t_cu: float = 0.0
    total_value_musd: float = 0.0
    findings: list = field(default_factory=list)  # list[Finding], отсортированы по severity

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# Цены металлов по умолчанию, $/т (допущение; настраивается).
DEFAULT_PRICES = {"Ni": 15000.0, "Cu": 8500.0}


def _class_by_size(rep: TailingsReport, size: str) -> Optional[SizeClassRow]:
    for c in rep.classes:
        if c.size == size:
            return c
    return None


def diagnose(rep: TailingsReport, prices: dict = None) -> Diagnosis:
    prices = prices or DEFAULT_PRICES
    d = Diagnosis(report_name=rep.source_name, plant=rep.plant)

    # Агрегаты по извлекаемому потерянному металлу.
    rec_ni = sum(c.min28.recoverable_t for c in rep.classes)
    rec_cu = sum(c.min29.recoverable_t for c in rep.classes)
    d.total_recoverable_lost_t_ni = rec_ni
    d.total_recoverable_lost_t_cu = rec_cu

    def money(t_ni, t_cu):
        return (t_ni * prices["Ni"] + t_cu * prices["Cu"]) / 1e6  # млн $

    d.total_value_musd = money(rec_ni, rec_cu)

    findings: list[Finding] = []

    # --- 1) Недоизмельчение: закрытый металл в крупных классах ---------------
    for size in ["+125", "+71", "-71 + 45"]:
        c = _class_by_size(rep, size)
        if not c:
            continue
        locked_ni = c.min28.locked_t()
        locked_cu = c.min29.locked_t()
        locked_total = locked_ni + locked_cu
        if locked_total < 1.0:
            continue
        val = money(locked_ni, locked_cu)
        # тяжесть: доля закрытого металла в общих извлекаемых потерях
        sev = min(1.0, locked_total / max(rec_ni + rec_cu, 1.0))
        findings.append(Finding(
            code="UNDERGRIND",
            element="Ni+Cu",
            size_class=size,
            severity=sev,
            lost_recoverable_t=locked_total,
            value_musd=val,
            headline=f"Недоизмельчение в классе {size} мкм: "
                     f"{locked_total:,.0f} т металла заперто в сростках",
            detail=(f"В классе крупности {size} мкм теряется {locked_ni:,.0f} т Ni и "
                    f"{locked_cu:,.0f} т Cu в форме ЗАКРЫТОГО Pnt/Cp (сростки с породой). "
                    f"Этот металл извлекаем, но требует вскрытия зёрен доизмельчением: "
                    f"текущая крупность недостаточна для раскрытия. "
                    f"Оценочная стоимость потерь ≈ {val:.1f} млн $/год."),
            evidence={"locked_ni_t": round(locked_ni, 1),
                      "locked_cu_t": round(locked_cu, 1),
                      "class_share_pct": round(c.mass_share_pct, 1)},
        ))

    # --- 2) Шламы: раскрытый металл в тонком классе -10 -----------------------
    cs = _class_by_size(rep, SLIME)
    if cs:
        lib_ni = cs.min28.liberated_t()
        lib_cu = cs.min29.liberated_t()
        lib_total = lib_ni + lib_cu
        if lib_total >= 1.0:
            val = money(lib_ni, lib_cu)
            sev = min(1.0, lib_total / max(rec_ni + rec_cu, 1.0))
            findings.append(Finding(
                code="SLIMES",
                element="Ni+Cu",
                size_class=SLIME,
                severity=sev,
                lost_recoverable_t=lib_total,
                value_musd=val,
                headline=f"Потеря шламов (-10 мкм): {lib_total:,.0f} т РАСКРЫТОГО "
                         f"металла уходит в хвосты",
                detail=(f"В тончайшем классе -10 мкм теряется {lib_ni:,.0f} т Ni и "
                        f"{lib_cu:,.0f} т Cu в РАСКРЫТОЙ форме — зёрна вскрыты, но частицы "
                        f"слишком мелкие для эффективной флотации (потеря со шламами). "
                        f"Это признак переизмельчения и/или недостаточной флотации тонких классов. "
                        f"Оценочная стоимость ≈ {val:.1f} млн $/год."),
                evidence={"liberated_ni_t": round(lib_ni, 1),
                          "liberated_cu_t": round(lib_cu, 1),
                          "class_share_pct": round(cs.mass_share_pct, 1)},
            ))

    # --- 3) Средние классы: смешанные потери (доизмельчение отдельным циклом) --
    for size in ["-45 + 20", "-20 + 10"]:
        c = _class_by_size(rep, size)
        if not c:
            continue
        locked = c.min28.locked_t() + c.min29.locked_t()
        if locked < 1.0:
            continue
        val = money(c.min28.locked_t(), c.min29.locked_t())
        sev = min(0.8, locked / max(rec_ni + rec_cu, 1.0))
        findings.append(Finding(
            code="MIDGRIND",
            element="Ni+Cu",
            size_class=size,
            severity=sev,
            lost_recoverable_t=locked,
            value_musd=val,
            headline=f"Сростки в среднем классе {size} мкм: {locked:,.0f} т металла",
            detail=(f"В классе {size} мкм заперто {locked:,.0f} т извлекаемого металла в сростках. "
                    f"Целесообразно селективное доизмельчение этого класса в отдельном цикле, "
                    f"чтобы не переизмельчать уже раскрытый металл. ≈ {val:.1f} млн $/год."),
            evidence={"locked_t": round(locked, 1),
                      "class_share_pct": round(c.mass_share_pct, 1)},
        ))

    # --- 4) KPI-потолок ------------------------------------------------------
    findings.append(Finding(
        code="RECOVERABLE_CEILING",
        element="Ni+Cu",
        severity=0.0,
        lost_recoverable_t=rec_ni + rec_cu,
        value_musd=d.total_value_musd,
        headline=f"Потолок выигрыша: до {rec_ni:,.0f} т Ni и {rec_cu:,.0f} т Cu "
                 f"извлекаемо из хвостов",
        detail=(f"Из {rep.tail_el28_t:,.0f} т Ni и {rep.tail_el29_t:,.0f} т Cu в хвостах "
                f"потенциально извлекаемо {rec_ni:,.0f} т Ni и {rec_cu:,.0f} т Cu "
                f"(остальное — силикаты/валлериит/примесь в пирротине, "
                f"не извлекается текущей технологией). "
                f"Это верхняя граница экономического эффекта ≈ {d.total_value_musd:.1f} млн $/год "
                f"при полном отыгрыше."),
        evidence={"tail_ni_t": round(rep.tail_el28_t, 1),
                  "tail_cu_t": round(rep.tail_el29_t, 1),
                  "recoverable_ni_t": round(rec_ni, 1),
                  "recoverable_cu_t": round(rec_cu, 1)},
    ))

    # Сортировка находок по стоимости (кроме потолка — он всегда справочный).
    core = [f for f in findings if f.code != "RECOVERABLE_CEILING"]
    core.sort(key=lambda f: f.value_musd, reverse=True)
    ceiling = [f for f in findings if f.code == "RECOVERABLE_CEILING"]
    d.findings = core + ceiling
    return d


if __name__ == "__main__":
    from core.ingest import parse_tailings_xlsx
    base = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
    for fn, plant in [("Пример 1/Хвосты КГМК.xlsx", "КГМК"),
                      ("Пример 4/Хвосты ТОФ_2.xlsx", "ТОФ")]:
        rep = parse_tailings_xlsx(f"{base}/{fn}", plant)
        d = diagnose(rep)
        print(f"\n######## {plant} — потолок {d.total_value_musd:.1f} млн $/год ########")
        for f in d.findings:
            print(f"[{f.code:20}] {f.value_musd:6.1f} M$  {f.headline}")
