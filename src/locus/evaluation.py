"""Hypothesis validation.

The production hypothesis is:

    "Locations with a high density of new residential buildings but few
     competitors within 500 m show X% higher revenue growth."

Revenue data is not part of the public sources used by the pipeline. In offline
demo mode we generate a synthetic revenue signal from latent drivers plus noise
so that the plumbing (joining, quartiles, rank correlation) can be tested. The
report explicitly labels this as synthetic and never claims real-world proof.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

from .models import LocationScore


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based) for ties."""

    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def spearman_correlation(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation without numpy/scipy."""

    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    numerator = sum((x - mx) * (y - my) for x, y in zip(rx, ry))
    denom_x = math.sqrt(sum((x - mx) ** 2 for x in rx))
    denom_y = math.sqrt(sum((y - my) ** 2 for y in ry))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return numerator / (denom_x * denom_y)


def attach_synthetic_revenue(
    scores: list[LocationScore], seed: int = 42
) -> list[LocationScore]:
    """Add a reproducible pseudo-revenue growth column for demo validation."""

    rng = random.Random(seed)
    result: list[LocationScore] = []
    for row in scores:
        latent = (
            0.9 * math.log1p(row.new_residential_units)
            - 0.8 * math.log1p(row.competitor_count)
            + 0.2 * row.transport_stops
            + 0.1 * row.poi_diversity
        )
        growth = 2.0 + latent + rng.gauss(0, 1.2)
        growth = max(-15.0, min(35.0, growth))
        result.append(replace(row, observed_revenue_growth_pct=round(growth, 2)))
    return result


def evaluate_hypothesis(scores: list[LocationScore]) -> dict:
    """Compare revenue growth in top vs bottom index quartiles."""

    rows = [s for s in scores if s.observed_revenue_growth_pct is not None]
    if len(rows) < 8:
        return {"n": len(rows), "status": "not_enough_data"}

    ordered = sorted(rows, key=lambda s: s.investment_index)
    q = max(1, len(ordered) // 4)
    bottom = ordered[:q]
    top = ordered[-q:]

    bottom_mean = sum(s.observed_revenue_growth_pct for s in bottom) / len(bottom)
    top_mean = sum(s.observed_revenue_growth_pct for s in top) / len(top)
    xs = [s.investment_index for s in rows]
    ys = [s.observed_revenue_growth_pct for s in rows]
    rho = spearman_correlation(xs, ys)
    uplift = top_mean - bottom_mean

    if uplift > 0 and rho > 0.2:
        status = "supported_on_synthetic_data"
    elif uplift > 0:
        status = "weak_signal"
    else:
        status = "not_supported"

    return {
        "n": len(rows),
        "top_quartile_growth_pct": round(top_mean, 2),
        "bottom_quartile_growth_pct": round(bottom_mean, 2),
        "uplift_pp": round(uplift, 2),
        "spearman_rho": round(rho, 3),
        "status": status,
        "data_note": (
            "Revenue is synthetic (demo only). Replace "
            "observed_revenue_growth_pct with real observations to test the "
            "hypothesis on production data."
        ),
    }
