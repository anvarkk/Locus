from __future__ import annotations

import pytest

from locus.config import get_business_type
from locus.evaluation import (
    attach_synthetic_revenue,
    evaluate_hypothesis,
    spearman_correlation,
)
from locus.models import CellFeatures
from locus.scoring import robust_normalize, score_features


def _feature(
    h3: str, new_units: int, competitors: int, stops: int = 5, diversity: int = 5
) -> CellFeatures:
    return CellFeatures(
        h3=h3,
        city="test",
        center_lat=55.79,
        center_lon=49.10,
        building_count=20,
        new_buildings=10 if new_units else 0,
        residential_units=1000,
        new_residential_units=new_units,
        population=2200,
        competitor_count=competitors,
        poi_count=40,
        poi_diversity=diversity,
        transport_stops=stops,
        competitor_density_km2=competitors / 0.785,
        distance_to_center_m=1000,
    )


def test_robust_normalize_clips_outlier() -> None:
    values = [0, 1, 2, 3, 1000]
    normalized = robust_normalize(values)
    assert normalized[0] == 0
    assert normalized[-1] == 1
    assert all(0 <= value <= 1 for value in normalized)


def test_high_demand_low_competition_wins() -> None:
    business = get_business_type("coffee")
    features = [
        _feature("winner", new_units=2000, competitors=1, stops=12, diversity=12),
        _feature("middle", new_units=900, competitors=7, stops=6, diversity=8),
        _feature("loser", new_units=100, competitors=30, stops=1, diversity=2),
    ]
    scores = score_features(features, business)
    assert [s.h3 for s in scores] == ["winner", "middle", "loser"]
    assert scores[0].investment_index > scores[-1].investment_index
    assert all(0 <= s.investment_index <= 100 for s in scores)
    assert scores[0].rank == 1
    assert scores[0].recommendation.startswith("A")


def test_revenue_signal_and_hypothesis() -> None:
    business = get_business_type("coffee")
    features = [
        _feature(f"h{i}", new_units=i * 100, competitors=20 - i) for i in range(1, 12)
    ]
    scores = attach_synthetic_revenue(score_features(features, business), seed=7)
    assert all(s.observed_revenue_growth_pct is not None for s in scores)
    report = evaluate_hypothesis(scores)
    assert report["n"] == len(scores)
    assert report["uplift_pp"] > 0
    assert report["spearman_rho"] > 0


def test_spearman_perfect_rank() -> None:
    assert spearman_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
