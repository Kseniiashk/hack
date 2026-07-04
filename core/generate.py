"""
Hypothesis Generator + Ranking.

Матчит находки Diagnostic Engine с карточками каталога, инстанцирует гипотезы
с конкретными числами из данных, считает Value/Novelty/Feasibility/Risk и
прозрачный итоговый Score. Опционально прикрепляет RAG-цитаты для обоснования.

Формула ранжирования (полностью интерпретируема, веса настраиваются):
    Score = w_value*Value_norm + w_feas*Feasibility + w_nov*Novelty − w_risk*Risk
где Value_norm — нормированная стоимость отыгрываемых потерь по всем гипотезам.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import os
import json
import yaml

from core.diagnose import Diagnosis, Finding, DEFAULT_PRICES

_KNOW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")


def load_catalog() -> list:
    with open(os.path.join(_KNOW_DIR, "hypotheses.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["hypotheses"]


def load_economics() -> dict:
    with open(os.path.join(_KNOW_DIR, "economics.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


DEFAULT_WEIGHTS = {"value": 0.45, "feasibility": 0.25, "novelty": 0.15, "risk": 0.15}


@dataclass
class Hypothesis:
    id: str
    title: str
    trigger_finding: str          # какая находка породила
    size_class: str
    rationale: str                # обоснование с числами из данных
    mechanism: str
    equipment: list = field(default_factory=list)
    stage: str = ""
    # метрики
    value_musd: float = 0.0       # ожидаемый эффект, млн $/год
    value_low: float = 0.0        # пессимистичная оценка (модель эффекта)
    value_high: float = 0.0       # оптимистичная оценка
    value_norm: float = 0.0       # 0..1
    feasibility: float = 0.0
    novelty: float = 0.0
    risk: float = 0.0
    risk_tech: float = 0.0
    risk_econ: float = 0.0
    score: float = 0.0
    # обоснование
    citations: list = field(default_factory=list)   # [{source, snippet}]
    success_criterion: str = ""
    roadmap: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def _value_for(card: dict, finding: Finding, prices: dict) -> float:
    """Ожидаемый эффект = доля отыгрыша * стоимость извлекаемых потерь находки."""
    return card.get("effect_frac", 0.15) * finding.value_musd


def generate(diag: Diagnosis, weights: dict = None, prices: dict = None,
             rag=None, exclude_ids: set = None, report=None) -> list:
    """Возвращает ранжированный список Hypothesis.
    Если передан report — эффект считается количественной моделью по реальной
    минералогии (диапазон low/exp/high), иначе — через effect_frac."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    prices = prices or DEFAULT_PRICES
    exclude_ids = exclude_ids or set()
    catalog = load_catalog()
    by_id = {c["id"]: c for c in catalog}
    if report is not None:
        from core.effect_model import estimate_effect

    raw: list[Hypothesis] = []
    seen = set()  # (card_id, size_class) — избегаем дублей
    for finding in diag.findings:
        if finding.code == "RECOVERABLE_CEILING":
            continue
        for card in catalog:
            if card["id"] in exclude_ids:
                continue
            if finding.code not in card.get("triggers", []):
                continue
            scope = card.get("size_scope") or []
            if scope and finding.size_class and finding.size_class not in scope:
                continue
            key = (card["id"], finding.size_class)
            if key in seen:
                continue
            seen.add(key)

            risk = 0.5 * card.get("risk_tech", 0.4) + 0.5 * card.get("risk_econ", 0.4)

            # Эффект: количественная модель по минералогии, если есть report.
            eff = None
            if report is not None:
                eff = estimate_effect(card["id"], finding, report, prices)
                val = eff.musd_exp
                rationale = (
                    f"Диагноз: {finding.headline}. {finding.detail} "
                    f"Механизм: {card['mechanism'].strip()} {eff.explain}"
                )
            else:
                val = _value_for(card, finding, prices)
                rationale = (
                    f"Диагноз: {finding.headline}. {finding.detail} "
                    f"Механизм вмешательства: {card['mechanism'].strip()} "
                    f"При отыгрыше ~{int(card.get('effect_frac',0.15)*100)}% этих потерь "
                    f"ожидаемый эффект ≈ {val:.1f} млн $/год."
                )

            h = Hypothesis(
                id=card["id"],
                title=card["title"],
                trigger_finding=finding.code,
                size_class=finding.size_class,
                rationale=rationale,
                mechanism=card["mechanism"].strip(),
                equipment=card.get("equipment", []),
                stage=card.get("stage", ""),
                value_musd=val,
                value_low=(eff.musd_low if eff else val * 0.6),
                value_high=(eff.musd_high if eff else val * 1.5),
                feasibility=card.get("feasibility", 0.5),
                novelty=card.get("novelty", 0.5),
                risk=risk,
                risk_tech=card.get("risk_tech", 0.4),
                risk_econ=card.get("risk_econ", 0.4),
                success_criterion=card.get("success", "").strip(),
                roadmap=card.get("roadmap", []),
                evidence=finding.evidence,
            )
            raw.append(h)

    # Дедуп по id: оставляем инстанс с максимальным value (лучший класс-триггер).
    best: dict = {}
    for h in raw:
        if h.id not in best or h.value_musd > best[h.id].value_musd:
            best[h.id] = h
    hyps = list(best.values())

    # Нормировка value.
    vmax = max((h.value_musd for h in hyps), default=1.0) or 1.0
    for h in hyps:
        h.value_norm = h.value_musd / vmax
        h.score = (weights["value"] * h.value_norm
                   + weights["feasibility"] * h.feasibility
                   + weights["novelty"] * h.novelty
                   - weights["risk"] * h.risk)

    # RAG-обоснование (цитаты из учебников).
    if rag is not None:
        for h in hyps:
            card = by_id.get(h.id, {})
            queries = card.get("refs", []) or [h.title]
            cites = []
            for q in queries[:2]:
                cites.extend(rag.search(q, k=1))
            # уникализируем по источнику
            uniq, srcs = [], set()
            for c in cites:
                if c["source"] not in srcs:
                    uniq.append(c); srcs.add(c["source"])
            h.citations = uniq[:2]

    hyps.sort(key=lambda h: h.score, reverse=True)
    return hyps


def hypotheses_to_dicts(hyps: list) -> list:
    return [asdict(h) for h in hyps]


if __name__ == "__main__":
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose
    base = "/Users/kseniashk/fabric/Задача 1. Фабрика гипотез/Задача 1"
    for fn, plant in [("Пример 1/Хвосты КГМК.xlsx", "КГМК"),
                      ("Пример 4/Хвосты ТОФ_2.xlsx", "ТОФ")]:
        rep = parse_tailings_xlsx(f"{base}/{fn}", plant)
        diag = diagnose(rep)
        hyps = generate(diag)
        print(f"\n######## {plant}: {len(hyps)} гипотез ########")
        for i, h in enumerate(hyps, 1):
            print(f"{i:2}. [{h.score:.2f}] {h.title}")
            print(f"     эффект≈{h.value_musd:5.1f}M$ | реализ={h.feasibility:.2f} "
                  f"нов={h.novelty:.2f} риск={h.risk:.2f} | класс {h.size_class} | {h.stage}")
