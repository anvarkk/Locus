"""Dagster orchestration for Locus.

Run locally:

    pip install -e ".[orchestration]"
    dagster dev -m orchestration.definitions

The demo job does not touch PostGIS; the warehouse job extracts, loads, runs dbt
and refreshes the dashboard.
"""

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    ConfigurableResource,
    Definitions,
    MaterializeResult,
    MetadataValue,
    ScheduleDefinition,
    asset,
    define_asset_job,
)

from locus.cleaning import clean_dataset
from locus.config import Settings, get_business_type, get_city
from locus.export import write_outputs
from locus.extract.osm import extract_city
from locus.models import CityDataset, PipelineResult
from locus.pipeline import PipelineOptions, run_pipeline
from locus.synthetic import generate_city


class LocusSettings(ConfigurableResource):
    """Dagster resource mirroring config/locus environment variables."""

    city: str = "kazan"
    source: str = "synthetic"
    business_type: str = "coffee"
    h3_resolution: int = 9
    radius_m: int = 500
    new_building_years: int = 5
    seed: int | None = None
    output_dir: str = "data/processed"
    database_url: str = "postgresql://locus:locus@localhost:5432/locus"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    user_agent: str = "locus-pet-project/0.1"
    with_synthetic_revenue: bool = True

    def to_settings(self) -> Settings:
        base = Settings.from_env()
        return replace(
            base,
            h3_resolution=self.h3_resolution,
            radius_m=self.radius_m,
            new_building_years=self.new_building_years,
            business_type=self.business_type,
            source=self.source,
            database_url=self.database_url,
            overpass_url=self.overpass_url,
            user_agent=self.user_agent,
            output_dir=Path(self.output_dir),
            dbt_project_dir=base.dbt_project_dir,
        )


@asset(group_name="extract", compute_kind="python")
def raw_city(context: AssetExecutionContext, settings: LocusSettings) -> CityDataset:
    """Extract a city from OSM or generate the deterministic demo dataset."""

    city = get_city(settings.city)
    if settings.source == "osm":
        dataset = extract_city(
            city,
            overpass_url=settings.overpass_url,
            user_agent=settings.user_agent,
            radius_m=settings.radius_m,
        )
    else:
        dataset = generate_city(city, seed=settings.seed)
    context.add_output_metadata(
        {
            "city": MetadataValue.text(city.name),
            "source": MetadataValue.text(dataset.source),
            "counts": MetadataValue.text(json.dumps(dataset.counts())),
            "generated_at": MetadataValue.text(dataset.generated_at),
        }
    )
    return dataset


@asset(group_name="transform", compute_kind="python")
def cleaned_city(raw_city: CityDataset) -> CityDataset:
    """Normalise categories, drop invalid coordinates, deduplicate POIs."""

    return clean_dataset(raw_city)


@asset(group_name="transform", compute_kind="python")
def location_scores(
    context: AssetExecutionContext,
    settings: LocusSettings,
    cleaned_city: CityDataset,
) -> PipelineResult:
    """Compute H3 features and the investment index."""

    cfg = settings.to_settings()
    result = run_pipeline(
        cleaned_city,
        cfg,
        business=get_business_type(cfg.business_type),
        options=PipelineOptions(with_synthetic_revenue=settings.with_synthetic_revenue),
    )
    top = result.scores[0] if result.scores else None
    context.add_output_metadata(
        {
            "cells": MetadataValue.int(len(result.scores)),
            "mean_index": MetadataValue.float(result.summary.get("mean_index", 0.0)),
            "top_h3": MetadataValue.text(top.h3 if top else ""),
            "top_index": MetadataValue.float(top.investment_index if top else 0.0),
            "summary": MetadataValue.text(
                json.dumps(result.summary, ensure_ascii=False)
            ),
        }
    )
    return result


@asset(group_name="load", compute_kind="sql", deps=[location_scores])
def postgis_load(
    context: AssetExecutionContext,
    settings: LocusSettings,
    location_scores: PipelineResult,
) -> MaterializeResult:
    """Upsert raw layers and the index into PostGIS."""

    from locus.load.db import load_result

    load_result(location_scores, settings.database_url)
    return MaterializeResult(
        metadata={
            "database": MetadataValue.text(settings.database_url.split("@")[-1]),
            "cells": MetadataValue.int(len(location_scores.scores)),
            "status": MetadataValue.text("loaded"),
        }
    )


@asset(group_name="transform", compute_kind="dbt", deps=[postgis_load])
def dbt_marts(
    context: AssetExecutionContext, settings: LocusSettings
) -> MaterializeResult:
    """Run dbt models that build staging/intermediate/marts in PostGIS."""

    dbt = shutil.which("dbt")
    if not dbt:
        raise RuntimeError(
            "dbt executable not found. Install with: pip install dbt-postgres"
        )
    env = os.environ.copy()
    env.setdefault("POSTGRES_HOST", "localhost")
    env.setdefault("POSTGRES_PORT", "5432")
    env.setdefault("POSTGRES_USER", "locus")
    env.setdefault("POSTGRES_PASSWORD", "locus")
    env.setdefault("POSTGRES_DB", "locus")
    project_dir = settings.to_settings().dbt_project_dir
    completed = subprocess.run(
        [dbt, "run", "--profiles-dir", "."],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    context.log.info(completed.stdout[-4000:])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-4000:] or "dbt run failed")
    return MaterializeResult(
        metadata={
            "project_dir": MetadataValue.text(str(project_dir)),
            "return_code": MetadataValue.int(completed.returncode),
            "models": MetadataValue.text(
                "stg_* → int_cell_features → fct_location_index → mart_investment_index"
            ),
        }
    )


@asset(group_name="serve", compute_kind="python")
def dashboard(
    context: AssetExecutionContext,
    settings: LocusSettings,
    location_scores: PipelineResult,
) -> MaterializeResult:
    """Write CSV/GeoJSON/report/standalone dashboard."""

    out_dir = settings.to_settings().output_dir
    paths = write_outputs(location_scores, out_dir)
    return MaterializeResult(
        metadata={
            "dashboard": MetadataValue.path(str(paths["dashboard"])),
            "csv": MetadataValue.path(str(paths["csv"])),
            "geojson": MetadataValue.path(str(paths["geojson"])),
            "cells": MetadataValue.int(len(location_scores.scores)),
        }
    )


demo_job = define_asset_job(
    "demo_refresh",
    selection=["raw_city", "cleaned_city", "location_scores", "dashboard"],
    description="Offline demo: synthetic/OSM data → index → dashboard.",
)

warehouse_job = define_asset_job(
    "warehouse_refresh",
    selection="*",
    description="Full refresh: extract → PostGIS → dbt → dashboard.",
)

daily_warehouse_refresh = ScheduleDefinition(
    job=warehouse_job,
    cron_schedule="0 3 * * *",
    execution_timezone="Europe/Moscow",
    name="daily_warehouse_refresh",
)


defs = Definitions(
    assets=[
        raw_city,
        cleaned_city,
        location_scores,
        postgis_load,
        dbt_marts,
        dashboard,
    ],
    jobs=[demo_job, warehouse_job],
    schedules=[daily_warehouse_refresh],
    resources={"settings": LocusSettings()},
)
