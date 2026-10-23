"""Investment attractiveness scoring.

Formula (all components normalised to 0..1 across the city):

    demand      = 0.50 * new_units_norm + 0.30 * new_buildings_norm
                + 0.20 * population_norm
    access      = transport_stops_norm
    diversity   = poi_diversity_norm
    competition = competitor_count_norm

    index = 100 * (
        w_demand * demand + w_access * access +
        w_diversity * diversity + w_competition * (1 - competition)
    )

The same formula is implemented in dbt (`fct_location_index.sql`). Python is
used for the local/demo path, SQL — for the production warehouse path.
"""

from __future__ import annotations

from dataclasses import replace

from .config import BusinessType
from .models import CellFeatures, LocationScore

COMPONENT_LABELS = {
    "demand": "спрос",
    "access": "транспорт",
    "diversity": "разнообразие POI",
    "competition": "конкуренция",
}


def _percentile(values: list[float], q: float = 0.95) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def robust_normalize(values: list[float], upper_quantile: float = 0.95) -> list[float]:
    """Min-max scaling with the top 5% clipped to reduce outlier influence."""

    if not values:
        return []
    low = min(values)
    high = _percentile(values, upper_quantile)
    if high <= low:
        high = max(values)
    if high <= low:
        return [0.0 for _ in values]
    return [max(0.0, min(1.0, (value - low) / (high - low))) for value in values]


def recommendation_for(index: float) -> str:
    if index >= 70:
        return "A — открывать"
    if index >= 55:
        return "B — рассмотреть"
    if index >= 40:
        return "C — наблюдать"
    return "D — не рекомендуется"


def _confidence(features: CellFeatures) -> float:
    data_points = (
        features.building_count * 2 + features.poi_count + features.transport_stops * 3
    )
    return round(min(1.0, 0.35 + 0.65 * min(1.0, data_points / 80)), 3)


def _explanation(
    features: CellFeatures,
    demand: float,
    access: float,
    competition: float,
    index: float,
) -> str:
    bits = [
        (
            f"новостройки: {features.new_buildings} домов / "
            f"{features.new_residential_units} кв."
        ),
        (
            f"конкуренты: {features.competitor_count} "
            f"({features.competitor_density_km2:.2f}/км²)"
        ),
        f"транспорт: {features.transport_stops} остановок",
    ]
    if demand >= 0.6 and competition <= 0.35:
        driver = "высокий спрос при низкой конкуренции"
    elif demand >= 0.6 and competition > 0.65:
        driver = "сильный спрос, но рынок насыщен"
    elif demand < 0.35 and competition <= 0.35:
        driver = "свободная ниша, но мало жителей"
    elif access >= 0.7:
        driver = "хорошая транспортная доступность"
    elif index >= 55:
        driver = "сбалансированные факторы"
    else:
        driver = "слабый спрос и/или высокая конкуренция"
    return f"{driver.capitalize()}. " + "; ".join(bits) + "."


def score_features(
    features: list[CellFeatures],
    business: BusinessType,
) -> list[LocationScore]:
    """Score all cells and assign deterministic ranks."""

    if not features:
        return []

    business.validate()
    weights = business.weights

    new_units = [f.new_residential_units for f in features]
    new_buildings = [f.new_buildings for f in features]
    population = [f.population for f in features]
    transport = [f.transport_stops for f in features]
    diversity = [f.poi_diversity for f in features]
    competitors = [f.competitor_count for f in features]

    new_units_norm = robust_normalize(new_units)
    new_buildings_norm = robust_normalize(new_buildings)
    population_norm = robust_normalize(population)
    transport_norm = robust_normalize(transport)
    diversity_norm = robust_normalize(diversity)
    competition_norm = robust_normalize(competitors)

    scored: list[LocationScore] = []
    for i, feature in enumerate(features):
        demand = (
            0.50 * new_units_norm[i]
            + 0.30 * new_buildings_norm[i]
            + 0.20 * population_norm[i]
        )
        access = transport_norm[i]
        diversity_score = diversity_norm[i]
        competition = competition_norm[i]
        index = 100.0 * (
            weights["demand"] * demand
            + weights["access"] * access
            + weights["diversity"] * diversity_score
            + weights["competition"] * (1.0 - competition)
        )
        index = round(max(0.0, min(100.0, index)), 2)
        scored.append(
            LocationScore(
                h3=feature.h3,
                city=feature.city,
                business_type=business.slug,
                center_lat=feature.center_lat,
                center_lon=feature.center_lon,
                rank=0,
                investment_index=index,
                recommendation=recommendation_for(index),
                confidence=_confidence(feature),
                demand_score=round(demand, 4),
                access_score=round(access, 4),
                diversity_score=round(diversity_score, 4),
                competition_score=round(competition, 4),
                building_count=feature.building_count,
                new_buildings=feature.new_buildings,
                residential_units=feature.residential_units,
                new_residential_units=feature.new_residential_units,
                population=feature.population,
                competitor_count=feature.competitor_count,
                competitor_density_km2=feature.competitor_density_km2,
                poi_count=feature.poi_count,
                poi_diversity=feature.poi_diversity,
                transport_stops=feature.transport_stops,
                distance_to_center_m=feature.distance_to_center_m,
                explanation=_explanation(feature, demand, access, competition, index),
            )
        )

    scored.sort(key=lambda row: (-row.investment_index, row.h3))
    return [replace(row, rank=position + 1) for position, row in enumerate(scored)]


def score_summary(scores: list[LocationScore]) -> dict[str, float]:
    if not scores:
        return {"cells": 0}
    indices = [s.investment_index for s in scores]
    ordered = sorted(indices)
    return {
        "cells": len(scores),
        "mean_index": round(sum(indices) / len(indices), 2),
        "median_index": round(ordered[len(ordered) // 2], 2),
        "p90_index": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))], 2),
        "max_index": round(max(indices), 2),
        "min_index": round(min(indices), 2),
    }
