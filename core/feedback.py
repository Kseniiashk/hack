"""
Механизм обучения на фидбэке (требование ТЗ, доп. пожелание).

Эксперт отмечает гипотезу как подтверждённую / опровергнутую / отклонённую.
Система копит эти оценки и корректирует ранжирование будущих рекомендаций:
у карточек гипотез появляется множитель приоритета на основе истории.

Хранилище — простой JSON (локально / на диске Space), без внешней БД.
Прозрачно и интерпретируемо: видно, сколько раз и как оценивали каждую гипотезу.

Логика корректировки (мягкая, ограниченная):
    prior = (подтверждено + 1) / (подтверждено + опровергнуто + 2)   # сглаживание Лапласа
    boost = 0.7 + 0.6 * prior            # диапазон ~0.7..1.3
    отклонённые (rejected) сильнее гасятся штрафом.
Итоговый множитель применяется к Score в rank-слое, оставаясь в разумных пределах.
"""
from __future__ import annotations
import os
import json
import threading
from datetime import datetime, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(_DIR, "..", "data", "feedback.json")
_LOCK = threading.Lock()

# Разрешённые вердикты.
CONFIRMED = "confirmed"
REFUTED = "refuted"
REJECTED = "rejected"   # эксперт исключил направление


def _load() -> dict:
    if not os.path.exists(STORE):
        return {}
    try:
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE) or ".", exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE)


def record(hypo_id: str, verdict: str, note: str = "", plant: str = "") -> None:
    """Фиксирует оценку эксперта по гипотезе."""
    if verdict not in (CONFIRMED, REFUTED, REJECTED):
        raise ValueError(f"неизвестный вердикт: {verdict}")
    with _LOCK:
        data = _load()
        rec = data.setdefault(hypo_id, {
            "confirmed": 0, "refuted": 0, "rejected": 0, "history": []})
        rec[verdict] += 1
        rec["history"].append({
            "verdict": verdict, "note": note, "plant": plant,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _save(data)


def stats(hypo_id: str) -> dict:
    return _load().get(hypo_id, {"confirmed": 0, "refuted": 0, "rejected": 0, "history": []})


def all_stats() -> dict:
    return _load()


def multiplier(hypo_id: str) -> float:
    """Множитель приоритета гипотезы по накопленному фидбэку (0.5..1.3)."""
    rec = _load().get(hypo_id)
    if not rec:
        return 1.0
    c, r, x = rec.get("confirmed", 0), rec.get("refuted", 0), rec.get("rejected", 0)
    # Байесово сглаживание доли подтверждений.
    prior = (c + 1) / (c + r + 2)
    boost = 0.7 + 0.6 * prior            # ~0.7..1.3
    if x > 0:                            # отклонённые направления гасим сильнее
        boost *= max(0.5, 1.0 - 0.2 * x)
    return round(max(0.5, min(1.3, boost)), 3)


def apply_to_hypotheses(hyps: list) -> list:
    """Корректирует score гипотез по фидбэку и пере-сортирует.
    Добавляет поля fb_multiplier и fb_stats для прозрачности в UI."""
    data = _load()
    if not data:
        for h in hyps:
            setattr(h, "fb_multiplier", 1.0)
            setattr(h, "fb_stats", None)
        return hyps
    for h in hyps:
        m = multiplier(h.id)
        setattr(h, "fb_multiplier", m)
        setattr(h, "fb_stats", data.get(h.id))
        h.score = round(h.score * m, 4)
    hyps.sort(key=lambda h: h.score, reverse=True)
    return hyps


if __name__ == "__main__":
    # демонстрация: подтверждаем одну гипотезу, опровергаем другую
    record("H_LINER_GEOMETRY", CONFIRMED, "лаб. подтвердила рост раскрытия", "КГМК")
    record("H_LINER_GEOMETRY", CONFIRMED, "повтор на второй секции", "КГМК")
    record("H_PEBBLE_CRUSHER", REFUTED, "прирост в пределах погрешности", "ТОФ")
    print("H_LINER_GEOMETRY множитель:", multiplier("H_LINER_GEOMETRY"))
    print("H_PEBBLE_CRUSHER множитель:", multiplier("H_PEBBLE_CRUSHER"))
    print("stats:", json.dumps(all_stats(), ensure_ascii=False)[:200])
