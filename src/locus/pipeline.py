"""Pipeline orchestration in plain Python (used by CLI, Dagster and tests)."""

from __future__ import annotations

from dataclasses import dataclass

from .cleaning import clean_dataset
from .config import BusinessType, Settings, get_business_type
from .evaluation import attach_synthetic_revenue, evaluate_hypothesis
from .features import compute_features
from .models import CityDataset, PipelineResult, utc_now_iso
from .scoring import score_features, score_summary


@dataclass
class PipelineOptions:
    with_synthetic_revenue: bool = False
    synthetic_revenue_seed: int = 42


def run_pipeline(
    dataset: CityDataset,
    settings: Settings,
    *,
    business: BusinessType | None = None,
    options: PipelineOptions | None = None,
) -> PipelineResult:
    """Clean -> H3 features -> score -> (optional) validation."""

    options = options or PipelineOptions()
    business = business or get_business_type(settings.business_type)

    cleaned = clean_dataset(dataset)
    features = compute_features(cleaned, business, settings)
    scores = score_features(features, business)
    if options.with_synthetic_revenue:
        scores = attach_synthetic_revenue(scores, seed=options.synthetic_revenue_seed)

    summary = {
        "city": cleaned.city.slug,
        "city_name": cleaned.city.name,
        "business_type": business.slug,
        "business_title": business.title,
        "source": cleaned.source,
        "generated_at": utc_now_iso(),
        "h3_resolution": settings.h3_resolution,
        "radius_m": settings.radius_m,
        "new_building_years": settings.new_building_years,
        "input_counts": cleaned.counts(),
        **score_summary(scores),
    }
    if options.with_synthetic_revenue:
        summary["hypothesis"] = evaluate_hypothesis(scores)

    return PipelineResult(
        dataset=cleaned,
        scores=scores,
        business_type=business.slug,
        settings=settings,
        summary=summary,
    )
