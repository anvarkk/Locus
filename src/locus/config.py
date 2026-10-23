"""Configuration loading for Locus.

Settings can be overridden with environment variables (see ``.env.example``).
City and business-type definitions live in ``config/*.json`` so that analysts can
add a new market without touching the code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.getenv("LOCUS_CONFIG_DIR", REPO_ROOT / "config"))
PACKAGE_CONFIG_DIR = Path(__file__).resolve().parent / "defaults"

DEFAULT_WEIGHTS = {
    "demand": 0.45,
    "access": 0.20,
    "diversity": 0.10,
    "competition": 0.25,
}


@dataclass(frozen=True)
class City:
    """A city (or any circular area) we build an index for."""

    slug: str
    name: str
    lat: float
    lon: float
    radius_km: float = 5.0
    population: int | None = None

    @property
    def radius_m(self) -> float:
        return self.radius_km * 1000


@dataclass(frozen=True)
class BusinessType:
    """Target business and the competitive landscape it cares about."""

    slug: str
    title: str
    competitor_categories: tuple[str, ...]
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    description: str = ""

    def validate(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Business type {self.slug!r}: weights must sum to 1.0, got {total}"
            )
        unknown = set(self.weights) - {"demand", "access", "diversity", "competition"}
        if unknown:
            raise ValueError(f"Unknown weight keys: {sorted(unknown)}")


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the pipeline."""

    h3_resolution: int = 9
    radius_m: int = 500
    new_building_years: int = 5
    current_year: int = field(default_factory=lambda: date.today().year)
    business_type: str = "coffee"
    source: str = "synthetic"
    database_url: str = "postgresql://locus:locus@localhost:5432/locus"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    user_agent: str = "locus-pet-project/0.1"
    output_dir: Path = REPO_ROOT / "data" / "processed"
    dbt_project_dir: Path = REPO_ROOT / "dbt"

    def __post_init__(self) -> None:
        if not 4 <= self.h3_resolution <= 12:
            raise ValueError("h3_resolution must be between 4 and 12")
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.new_building_years <= 0:
            raise ValueError("new_building_years must be positive")

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            h3_resolution=int(os.getenv("LOCUS_H3_RESOLUTION", defaults.h3_resolution)),
            radius_m=int(os.getenv("LOCUS_RADIUS_M", defaults.radius_m)),
            new_building_years=int(
                os.getenv("LOCUS_NEW_BUILDING_YEARS", defaults.new_building_years)
            ),
            business_type=os.getenv("LOCUS_BUSINESS_TYPE", defaults.business_type),
            source=os.getenv("LOCUS_SOURCE", defaults.source),
            database_url=os.getenv("DATABASE_URL", defaults.database_url),
            overpass_url=os.getenv("OVERPASS_URL", defaults.overpass_url),
            user_agent=os.getenv("LOCUS_USER_AGENT", defaults.user_agent),
            output_dir=Path(os.getenv("LOCUS_OUTPUT_DIR", str(defaults.output_dir))),
            dbt_project_dir=Path(
                os.getenv("DBT_PROJECT_DIR", str(defaults.dbt_project_dir))
            ),
        )


def _config_path(name: str) -> Path:
    """Prefer the repo/user config, fall back to packaged defaults."""

    for base in (CONFIG_DIR, PACKAGE_CONFIG_DIR):
        candidate = base / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Config file {name!r} not found in {CONFIG_DIR} or {PACKAGE_CONFIG_DIR}."
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Set LOCUS_CONFIG_DIR or restore config/."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_cities() -> tuple[dict[str, City], str]:
    payload = _load_json(_config_path("cities.json"))
    cities = {
        slug: City(**{**raw, "slug": slug})
        for slug, raw in payload.get("cities", {}).items()
    }
    if not cities:
        raise ValueError("No cities found in config/cities.json")
    default = payload.get("default_city", next(iter(cities)))
    return cities, default


@lru_cache(maxsize=1)
def load_business_types() -> tuple[dict[str, BusinessType], str]:
    payload = _load_json(_config_path("business_types.json"))
    types: dict[str, BusinessType] = {}
    for slug, raw in payload.get("business_types", {}).items():
        business = BusinessType(
            slug=raw.get("slug", slug),
            title=raw["title"],
            description=raw.get("description", ""),
            competitor_categories=tuple(raw["competitor_categories"]),
            weights=dict(raw.get("weights", DEFAULT_WEIGHTS)),
        )
        business.validate()
        types[slug] = business
    if not types:
        raise ValueError("No business types found in config/business_types.json")
    return types, payload.get("default", next(iter(types)))


def get_city(slug: str | None = None) -> City:
    cities, default = load_cities()
    key = (slug or os.getenv("LOCUS_CITY") or default).lower()
    try:
        return cities[key]
    except KeyError as exc:
        raise KeyError(f"Unknown city {key!r}. Available: {sorted(cities)}") from exc


def get_business_type(slug: str | None = None) -> BusinessType:
    types, default = load_business_types()
    key = (slug or os.getenv("LOCUS_BUSINESS_TYPE") or default).lower()
    try:
        return types[key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown business type {key!r}. Available: {sorted(types)}"
        ) from exc
