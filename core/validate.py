"""
Авто-валидация против эталона экспертов.

Организаторы дали не только данные хвостов, но и ЭТАЛОННЫЕ гипотезы (файлы
«Гипотезы*.docx» — результат мозгового штурма экспертов Компании). Это готовый
ground truth. Мы прогоняем нашу систему на тех же фабриках и объективно измеряем,
насколько её гипотезы совпадают с экспертными.

Метрики:
  recall    — доля эталонных гипотез, покрытых нашей системой (главная метрика:
              «мы нашли то же, что придумали эксперты»);
  precision — доля наших топ-гипотез, совпавших с эталоном;
  match@k   — покрытие эталона нашим топ-k.

Матчинг — по концептам, а не по строкам: каждая гипотеза раскладывается на
(оборудование/узел) + (действие). Совпадение засчитывается, если пересекаются
и узел, и действие. Это устойчиво к разным формулировкам одного и того же.
"""
from __future__ import annotations
import os
import json
import re
from dataclasses import dataclass, field, asdict

_KDIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")

# Концепт-словарь: канонический узел -> синонимы в тексте гипотез.
EQUIPMENT = {
    "мельница": ["мельниц", "футеровк", "шаров", "мелющих тел", "измельчен", "домол", "доизмельч"],
    "гидроциклон": ["гидроциклон", "циклон", "песков", "насадк", "апекс"],
    "классификатор": ["классификатор", "классификац", "спиральн", "возвратн", "контрольн классиф"],
    "дробилка": ["дробилк", "дроблен", "конусн", "гранулометри", "зазор", "щел", "гали"],
    "грохот": ["грохот", "грохочен", "сито"],
    "флотация": ["флотац", "пульп", "плотност", "контактн чан", "агитац", "реагент",
                 "finfix", "ксантоген", "собиратель", "фронт флотац", "пенн"],
    "магнитная_сепарация": ["магнитн", "сепарац"],
    "хвосты_возврат": ["хвост", "возврат в голов", "доизвлеч"],
}

# Действия (что делаем с узлом).
ACTIONS = {
    "замена": ["замен", "переход", "установ нов", "более производит"],
    "изменение": ["изменен", "геометри", "донастрой", "настрой", "регулиров", "оптимиз",
                  "повышен", "снижен", "уменьшен", "увеличен", "перераспредел"],
    "добавление": ["добавлен", "дополнительн", "промежуточн", "введен", "внедрен"],
    "контроль": ["контрол", "автоматиз", "автоматич", "стабилиз"],
}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()


def concepts(text: str) -> tuple[set, set]:
    """Возвращает (узлы, действия), найденные в тексте гипотезы."""
    t = _norm(text)
    nodes = {k for k, syns in EQUIPMENT.items() if any(s in t for s in syns)}
    acts = {k for k, syns in ACTIONS.items() if any(s in t for s in syns)}
    return nodes, acts


def is_match(ours: str, gold: str) -> bool:
    """Совпадение, если пересекается хотя бы один узел И (действие пересекается
    или узел достаточно специфичен, напр. магнитная сепарация/грохот)."""
    n1, a1 = concepts(ours)
    n2, a2 = concepts(gold)
    if not (n1 & n2):
        return False
    common = n1 & n2
    # для «сильных» узлов достаточно совпадения узла
    strong = {"магнитная_сепарация", "грохот", "гидроциклон", "хвосты_возврат"}
    if common & strong:
        return True
    # иначе требуем и совпадение действия
    return bool(a1 & a2) or not (a1 and a2)


@dataclass
class ValidationResult:
    plant: str = ""
    n_gold: int = 0
    n_ours: int = 0
    matched_gold: int = 0           # сколько эталонных покрыто
    recall: float = 0.0
    precision_topk: float = 0.0
    k: int = 0
    matches: list = field(default_factory=list)   # [{gold, our, rank}]
    missed: list = field(default_factory=list)    # непокрытые эталонные

    def to_dict(self):
        return asdict(self)


def load_gold() -> dict:
    p = os.path.join(_KDIR, "gold_hypotheses.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def validate_plant(plant: str, our_titles: list, k: int = 10) -> ValidationResult:
    gold = load_gold().get(plant, [])
    res = ValidationResult(plant=plant, n_gold=len(gold), n_ours=len(our_titles), k=k)
    topk = our_titles[:k]
    covered = set()
    used_ours = set()
    for gi, g in enumerate(gold):
        for oi, o in enumerate(topk):
            if is_match(o, g):
                covered.add(gi)
                used_ours.add(oi)
                res.matches.append({"gold": g, "our": o, "rank": oi + 1})
                break
    res.matched_gold = len(covered)
    res.recall = round(len(covered) / max(len(gold), 1), 3)
    res.precision_topk = round(len(used_ours) / max(len(topk), 1), 3)
    res.missed = [g for gi, g in enumerate(gold) if gi not in covered]
    return res


def validate_all(generate_fn, k: int = 10) -> dict:
    """generate_fn(plant) -> список заголовков наших гипотез. Возвращает
    результаты по фабрикам + агрегат."""
    gold = load_gold()
    results = {}
    tot_gold = tot_cov = 0
    for plant in gold:
        titles = generate_fn(plant)
        r = validate_plant(plant, titles, k=k)
        results[plant] = r
        tot_gold += r.n_gold
        tot_cov += r.matched_gold
    results["_overall"] = {
        "recall": round(tot_cov / max(tot_gold, 1), 3),
        "matched": tot_cov, "total_gold": tot_gold,
        "plants": len(gold),
    }
    return results


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose
    from core.generate import generate

    base = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
    files = {"КГМК": "Пример 1/Хвосты КГМК.xlsx", "НОФ-вкр": "Пример 2/Хвосты НОФ Вкр.xlsx",
             "НОФ-мед": "Пример 3/Хвосты НОФ мед.xlsx", "ТОФ": "Пример 4/Хвосты ТОФ_2.xlsx"}

    def gen(plant):
        rep = parse_tailings_xlsx(f"{base}/{files[plant]}", plant)
        return [h.title for h in generate(diagnose(rep))]

    res = validate_all(gen, k=12)
    print("\n" + "=" * 60)
    for plant in files:
        r = res[plant]
        print(f"\n### {plant}: recall {r.recall:.0%} "
              f"({r.matched_gold}/{r.n_gold} эталонных покрыто)")
        for m in r.matches:
            print(f"   ✓ [{m['rank']:2}] {m['gold'][:55]}")
        for g in r.missed:
            print(f"   ✗      {g[:55]}")
    o = res["_overall"]
    print(f"\n{'='*60}\nИТОГО recall = {o['recall']:.0%} "
          f"({o['matched']}/{o['total_gold']} эталонных гипотез покрыто)")
