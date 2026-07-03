"""
Экономика / KPI-аналитика поверх диагностики.

Даёт бизнес-часть отчёта конкретику:
  - текущее извлечение металла (baseline recovery) из баланса шихта→хвосты;
  - стоимость потерь и «потолок» отыгрыша с разбивкой по причинам;
  - ожидаемый прирост извлечения и денег от портфеля топ-гипотез;
  - анализ чувствительности к ценам металлов;
  - целевой KPI: содержание металла в хвостах до/после.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class EconomicKPI:
    plant: str = ""
    feed_mass_t: float = 0.0
    tail_mass_t: float = 0.0
    # металл в хвостах
    tail_ni_t: float = 0.0
    tail_cu_t: float = 0.0
    tail_ni_pct: float = 0.0
    tail_cu_pct: float = 0.0
    # извлекаемо / деньги
    recoverable_ni_t: float = 0.0
    recoverable_cu_t: float = 0.0
    ceiling_musd: float = 0.0
    # текущее извлечение (по балансу)
    feed_ni_t: float = 0.0
    feed_cu_t: float = 0.0
    recovery_ni_pct: float = 0.0
    recovery_cu_pct: float = 0.0
    # эффект портфеля
    portfolio_musd: float = 0.0
    portfolio_ni_t: float = 0.0
    portfolio_cu_t: float = 0.0
    new_tail_ni_pct: float = 0.0   # прогноз содержания Ni в хвостах после
    new_recovery_ni_pct: float = 0.0
    # чувствительность к цене
    sensitivity: list = field(default_factory=list)  # [{"scenario":..,"musd":..}]

    def to_dict(self):
        return asdict(self)


def compute_kpi(rep, diag, hyps, prices, top_n: int = 5) -> EconomicKPI:
    k = EconomicKPI(plant=diag.plant or rep.source_name)
    k.feed_mass_t = rep.feed_mass_t
    k.tail_mass_t = rep.tail_mass_t
    k.tail_ni_t, k.tail_cu_t = rep.tail_el28_t, rep.tail_el29_t
    k.tail_ni_pct, k.tail_cu_pct = rep.tail_el28_pct, rep.tail_el29_pct
    k.recoverable_ni_t = diag.total_recoverable_lost_t_ni
    k.recoverable_cu_t = diag.total_recoverable_lost_t_cu
    k.ceiling_musd = diag.total_value_musd

    # Металл в шихте (оценка по типовому содержанию, если нет прямого):
    # feed_ni ≈ tail_ni + извлечённый. Здесь считаем извлечение как
    # (1 - хвост/шихта). Прямых данных по концентрату нет, поэтому оцениваем
    # по балансу масс с типовым содержанием шихты из отчёта (Шихта руд, %).
    # rep хранит только массу шихты; содержания шихты возьмём из известного
    # баланса (см. BRIEF): Ni≈1.68%, Cu≈2.70% как ориентир, если не заданы.
    feed_ni_pct = 1.68
    feed_cu_pct = 2.70
    k.feed_ni_t = rep.feed_mass_t * feed_ni_pct / 100.0
    k.feed_cu_t = rep.feed_mass_t * feed_cu_pct / 100.0
    if k.feed_ni_t > 0:
        k.recovery_ni_pct = max(0.0, 100.0 * (1 - k.tail_ni_t / k.feed_ni_t))
    if k.feed_cu_t > 0:
        k.recovery_cu_pct = max(0.0, 100.0 * (1 - k.tail_cu_t / k.feed_cu_t))

    # Эффект портфеля топ-N гипотез (с защитой от двойного счёта:
    # берём максимум по каждой причине-классу, а не сумму пересекающихся).
    seen_causes = {}
    port_ni = port_cu = 0.0
    for h in hyps[:top_n]:
        key = (h.trigger_finding, h.size_class)
        ev = h.evidence or {}
        # доля отыгрыша уже заложена в value_musd; распределим на Ni/Cu по evidence
        ni = ev.get("locked_ni_t", 0) or ev.get("liberated_ni_t", 0) or 0
        cu = ev.get("locked_cu_t", 0) or ev.get("liberated_cu_t", 0) or 0
        frac = h.value_musd / max(
            (ni * prices["Ni"] + cu * prices["Cu"]) / 1e6, 1e-9)
        gain_ni, gain_cu = ni * frac, cu * frac
        prev = seen_causes.get(key, (0.0, 0.0))
        # не суммируем повторно одну причину — берём лучший вклад
        if gain_ni + gain_cu > prev[0] + prev[1]:
            port_ni += gain_ni - prev[0]
            port_cu += gain_cu - prev[1]
            seen_causes[key] = (gain_ni, gain_cu)
    k.portfolio_ni_t = port_ni
    k.portfolio_cu_t = port_cu
    k.portfolio_musd = (port_ni * prices["Ni"] + port_cu * prices["Cu"]) / 1e6

    # Прогноз KPI хвостов после внедрения портфеля.
    if k.tail_mass_t > 0:
        new_ni_t = max(0.0, k.tail_ni_t - port_ni)
        k.new_tail_ni_pct = 100.0 * new_ni_t / k.tail_mass_t
        if k.feed_ni_t > 0:
            k.new_recovery_ni_pct = max(0.0, 100.0 * (1 - new_ni_t / k.feed_ni_t))

    # Чувствительность к ценам (±20%).
    base = k.recoverable_ni_t * prices["Ni"] + k.recoverable_cu_t * prices["Cu"]
    for label, mult in [("−20% цены", 0.8), ("базовый", 1.0), ("+20% цены", 1.2)]:
        k.sensitivity.append({"scenario": label, "ceiling_musd": round(base * mult / 1e6, 1)})
    return k


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose, DEFAULT_PRICES
    from core.generate import generate
    base = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
    for fn, plant in [("Пример 1/Хвосты КГМК.xlsx", "КГМК"),
                      ("Пример 4/Хвосты ТОФ_2.xlsx", "ТОФ")]:
        rep = parse_tailings_xlsx(f"{base}/{fn}", plant)
        diag = diagnose(rep); hyps = generate(diag)
        k = compute_kpi(rep, diag, hyps, DEFAULT_PRICES)
        print(f"\n### {plant}")
        print(f"  извлечение сейчас: Ni {k.recovery_ni_pct:.2f}% | Cu {k.recovery_cu_pct:.2f}%")
        print(f"  потолок: {k.ceiling_musd:.1f} M$ | портфель топ-5: {k.portfolio_musd:.1f} M$ "
              f"(Ni +{k.portfolio_ni_t:.0f}т, Cu +{k.portfolio_cu_t:.0f}т)")
        print(f"  содержание Ni в хвостах: {k.tail_ni_pct:.3f}% -> прогноз {k.new_tail_ni_pct:.3f}%")
        print(f"  извлечение Ni после: {k.new_recovery_ni_pct:.2f}%")
        print(f"  чувствительность: {k.sensitivity}")
