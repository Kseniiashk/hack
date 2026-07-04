"""
Оценка капзатрат и простой окупаемости (для бизнес-части).

CAPEX-уровень выводится из типа вмешательства (не выдумываем точных сумм):
  - настройка режима / реагенты / АСУ — низкий CAPEX (донастройка без замены);
  - замена насадок / футеровки / шаров — средний;
  - новое оборудование (сепаратор, доп. дробилка, замена классификаторов) — высокий.

Payback = ориентировочный CAPEX / годовой эффект. Это оценка «порядка величины»,
не финансовая модель — так и помечаем. Диапазоны CAPEX условные (млн $).
"""
from __future__ import annotations

# Ориентировочный CAPEX по id вмешательства, млн $ (порядок величины, допущение).
CAPEX_MUSD = {
    # настройка/режим — почти без капзатрат
    "H_CLASSIFIER_SPEED": 0.05,
    "H_PULP_DENSITY": 0.05,
    "H_WATER_CONTROL": 0.3,
    "H_CRUSHER_GAP": 0.3,
    "H_REAGENT_FINFIX": 0.2,
    "H_CRUSHER_GRANULO": 0.4,
    # замена расходников/узлов — средний
    "H_CYCLONE_APEX": 0.5,
    "H_BALL_LOAD_120": 0.4,
    "H_BALL_WEAR_CLASS5": 0.5,
    "H_LINER_GEOMETRY": 0.8,
    "H_CONTACT_TANKS": 1.5,
    "H_FLOT_FRONT": 1.0,
    # новое оборудование / переустройство — высокий
    "H_CLASSIFIER_UPGRADE": 3.0,
    "H_CLASSIFIER_TO_CYCLONE": 4.0,
    "H_FINE_SCREEN": 3.5,
    "H_TAILS_RECLASSIFY": 3.0,
    "H_PEBBLE_CRUSHER": 5.0,
    "H_REGRIND_MAGSEP": 6.0,
}
DEFAULT_CAPEX = 1.0


def capex_tier(card_id: str) -> str:
    c = CAPEX_MUSD.get(card_id, DEFAULT_CAPEX)
    if c <= 0.5:
        return "низкий"
    if c <= 1.5:
        return "средний"
    return "высокий"


def payback(card_id: str, value_musd: float) -> dict:
    """Простой срок окупаемости (годы) = CAPEX / годовой эффект."""
    capex = CAPEX_MUSD.get(card_id, DEFAULT_CAPEX)
    years = capex / value_musd if value_musd > 0 else None
    return {
        "capex_musd": capex,
        "tier": capex_tier(card_id),
        "payback_years": years,
        "payback_months": (years * 12) if years is not None else None,
    }


def feasibility_penalty(card_id: str) -> float:
    """Штраф к ранжированию за капиталоёмкость/невыполнимость «здесь и сейчас»:
    высокий CAPEX = ниже приоритет для быстрого внедрения. 0 (нет штрафа) .. 0.15."""
    capex = CAPEX_MUSD.get(card_id, DEFAULT_CAPEX)
    if capex <= 0.5:
        return 0.0
    if capex <= 1.5:
        return 0.05
    if capex <= 4.0:
        return 0.10
    return 0.15
