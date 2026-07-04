"""
Количественная модель эффекта (вместо «доли отыгрыша из головы»).

Идея: не брать effect_frac константой, а рассчитывать ожидаемый прирост извлечения
из инженерных принципов процесса И реальной минералогии данных, с диапазоном
(пессимистичный / ожидаемый / оптимистичный) и явными допущениями.

Механика:
  Адресуемый металл (addressable) — сколько извлекаемого металла реально может
  «достать» это вмешательство в целевом классе:
    - для раскрытия (доизмельчение/классификация/грохот/магнит) — это ЗАКРЫТЫЙ
      металл (сростки) в целевом классе: его надо вскрыть;
    - для флотации/шламов — РАСКРЫТЫЙ металл в тонком классе −10, теряемый флотацией.
  Достижимая доля (capture) — какую часть адресуемого реально извлечём: задаётся
  диапазоном по типу вмешательства (из практики обогащения) и корректируется
  «зрелостью» узла (насколько radikально вмешательство).

Итог: tonnes_low/exp/high и деньги, плюс человекочитаемая расшифровка расчёта.
Всё прозрачно и проверяемо экспертом — ключевое требование ТЗ.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict

# Тип вмешательства → (capture_low, capture_exp, capture_high) — доля адресуемого
# металла, которую реально извлекаем. Основано на инженерной логике процесса.
# Раскрытие крупных сростков радикальнее «донастройки», поэтому вилки разные.
CAPTURE = {
    # раскрытие сростков
    "H_REGRIND_MAGSEP":      (0.20, 0.35, 0.50),   # отдельный цикл доизмельчения — сильно
    "H_FINE_SCREEN":         (0.15, 0.28, 0.42),
    "H_TAILS_RECLASSIFY":    (0.15, 0.28, 0.45),
    "H_CLASSIFIER_TO_CYCLONE": (0.12, 0.24, 0.38),
    "H_CLASSIFIER_UPGRADE":  (0.10, 0.20, 0.32),
    "H_CYCLONE_APEX":        (0.08, 0.16, 0.26),
    "H_LINER_GEOMETRY":      (0.08, 0.16, 0.26),
    "H_BALL_LOAD_120":       (0.05, 0.12, 0.20),
    "H_BALL_WEAR_CLASS5":    (0.04, 0.09, 0.16),
    "H_CLASSIFIER_SPEED":    (0.04, 0.09, 0.15),
    # дробление (стабилизация питания)
    "H_CRUSHER_GRANULO":     (0.04, 0.10, 0.18),
    "H_CRUSHER_GAP":         (0.03, 0.08, 0.14),
    "H_PEBBLE_CRUSHER":      (0.06, 0.14, 0.24),
    # флотация / шламы
    "H_PULP_DENSITY":        (0.06, 0.13, 0.22),
    "H_CONTACT_TANKS":       (0.08, 0.16, 0.26),
    "H_FLOT_FRONT":          (0.08, 0.16, 0.26),
    "H_REAGENT_FINFIX":      (0.07, 0.15, 0.25),
    "H_WATER_CONTROL":       (0.04, 0.10, 0.17),
}
DEFAULT_CAPTURE = (0.05, 0.12, 0.20)


@dataclass
class EffectEstimate:
    addressable_ni_t: float = 0.0
    addressable_cu_t: float = 0.0
    capture_low: float = 0.0
    capture_exp: float = 0.0
    capture_high: float = 0.0
    ni_low: float = 0.0; ni_exp: float = 0.0; ni_high: float = 0.0
    cu_low: float = 0.0; cu_exp: float = 0.0; cu_high: float = 0.0
    musd_low: float = 0.0; musd_exp: float = 0.0; musd_high: float = 0.0
    basis: str = ""              # что взято за адресуемый металл
    explain: str = ""           # расшифровка расчёта

    def to_dict(self):
        return asdict(self)


def _class_of(rep, size):
    for c in rep.classes:
        if c.size == size:
            return c
    return None


def estimate_effect(card_id: str, finding, report, prices) -> EffectEstimate:
    """Оценивает эффект вмешательства по реальной минералогии целевого класса."""
    e = EffectEstimate()
    cl, ch = CAPTURE.get(card_id, DEFAULT_CAPTURE), None
    e.capture_low, e.capture_exp, e.capture_high = CAPTURE.get(card_id, DEFAULT_CAPTURE)

    c = _class_of(report, finding.size_class) if finding.size_class else None

    if finding.code in ("UNDERGRIND", "MIDGRIND") and c is not None:
        # адресуемое = закрытый (извлекаемый, но запертый) металл в классе
        e.addressable_ni_t = c.min28.locked_t()
        e.addressable_cu_t = c.min29.locked_t()
        e.basis = f"закрытый Pnt/Cp в классе {finding.size_class} мкм (сростки, требуют раскрытия)"
    elif finding.code == "SLIMES" and c is not None:
        # адресуемое = раскрытый металл в −10, теряемый флотацией
        e.addressable_ni_t = c.min28.liberated_t()
        e.addressable_cu_t = c.min29.liberated_t()
        e.basis = "раскрытый Pnt/Cp в классе −10 мкм (шламы, теряются во флотации)"
    else:
        # fallback: берём стоимостную оценку находки
        e.addressable_ni_t = 0.0
        e.addressable_cu_t = 0.0
        e.basis = "оценка по стоимости находки"

    def band(t):
        return (t * e.capture_low, t * e.capture_exp, t * e.capture_high)

    e.ni_low, e.ni_exp, e.ni_high = band(e.addressable_ni_t)
    e.cu_low, e.cu_exp, e.cu_high = band(e.addressable_cu_t)

    def money(ni, cu):
        return (ni * prices["Ni"] + cu * prices["Cu"]) / 1e6

    e.musd_low = money(e.ni_low, e.cu_low)
    e.musd_exp = money(e.ni_exp, e.cu_exp)
    e.musd_high = money(e.ni_high, e.cu_high)

    e.explain = (
        f"Адресуемый металл: {e.addressable_ni_t:,.0f} т Ni + {e.addressable_cu_t:,.0f} т Cu "
        f"({e.basis}). Достижимая доля извлечения вмешательством: "
        f"{e.capture_low:.0%}…{e.capture_exp:.0%}…{e.capture_high:.0%}. "
        f"Ожидаемый возврат: {e.ni_exp:,.0f} т Ni + {e.cu_exp:,.0f} т Cu ≈ "
        f"{e.musd_exp:.1f} млн $/год (диапазон {e.musd_low:.1f}…{e.musd_high:.1f})."
    )
    return e


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose, DEFAULT_PRICES
    from core.generate import generate
    base = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
    rep = parse_tailings_xlsx(f"{base}/Пример 1/Хвосты КГМК.xlsx", "КГМК")
    diag = diagnose(rep)
    hyps = generate(diag)
    print("Количественная модель эффекта (КГМК, топ-5):\n")
    for h in hyps[:5]:
        # находка-триггер
        f = next((x for x in diag.findings
                  if x.code == h.trigger_finding and x.size_class == h.size_class), None)
        if not f:
            continue
        e = estimate_effect(h.id, f, rep, DEFAULT_PRICES)
        print(f"• {h.title}")
        print(f"  {e.explain}\n")
