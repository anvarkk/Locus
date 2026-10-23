"""Domain models shared by extract / transform / load layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import City


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class Poi:
    """A point of interest (competitor or demand driver)."""

    id: str
    name: str
    category: str
    lat: float
    lon: float
    brand: str | None = None
    amenity: str | None = None
    shop: str | None = None
    source: str = "osm"
    tags: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def display_name(self) -> str:
        return self.name or self.brand or self.category


@dataclass(frozen=True, slots=True)
class Building:
    """A residential building used as a demand proxy."""

    id: str
    lat: float
    lon: float
    address: str | None = None
    building_type: str = "residential"
    levels: int = 5
    flats: int | None = None
    completion_year: int | None = None
    source: str = "osm"

    @property
    def estimated_flats(self) -> int:
        """Estimate dwellings when the source does not expose a flat count.

        The heuristic (4 flats per floor) is intentionally conservative and is
        replaced by ``building:flats`` whenever OSM/open-data provides it.
        """

        if self.flats and self.flats > 0:
            return int(self.flats)
        return max(1, int(self.levels) * 4)

    @property
    def is_new(self) -> bool:
        return self.completion_year is not None


@dataclass(frozen=True, slots=True)
class TransportStop:
    """Public transport stop — a proxy for foot traffic."""

    id: str
    name: str
    lat: float
    lon: float
    stop_type: str = "bus"
    source: str = "osm"


@dataclass
class CityDataset:
    """Everything extracted for one city before cleaning."""

    city: City
    pois: list[Poi] = field(default_factory=list)
    buildings: list[Building] = field(default_factory=list)
    transport_stops: list[TransportStop] = field(default_factory=list)
    source: str = "osm"
    generated_at: str = field(default_factory=utc_now_iso)

    def counts(self) -> dict[str, int]:
        return {
            "pois": len(self.pois),
            "buildings": len(self.buildings),
            "transport_stops": len(self.transport_stops),
        }


@dataclass(frozen=True, slots=True)
class CellFeatures:
    """Aggregated features for one H3 cell (radius-based)."""

    h3: str
    city: str
    center_lat: float
    center_lon: float
    building_count: int
    new_buildings: int
    residential_units: int
    new_residential_units: int
    population: float
    competitor_count: int
    poi_count: int
    poi_diversity: int
    transport_stops: int
    competitor_density_km2: float
    distance_to_center_m: float


@dataclass(frozen=True, slots=True)
class LocationScore:
    """Index components plus the final score for one cell."""

    h3: str
    city: str
    business_type: str
    center_lat: float
    center_lon: float
    rank: int
    investment_index: float
    recommendation: str
    confidence: float
    demand_score: float
    access_score: float
    diversity_score: float
    competition_score: float
    building_count: int
    new_buildings: int
    residential_units: int
    new_residential_units: int
    population: float
    competitor_count: int
    competitor_density_km2: float
    poi_count: int
    poi_diversity: int
    transport_stops: int
    distance_to_center_m: float
    explanation: str
    observed_revenue_growth_pct: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "h3": self.h3,
            "city": self.city,
            "business_type": self.business_type,
            "center_lat": round(self.center_lat, 6),
            "center_lon": round(self.center_lon, 6),
            "rank": self.rank,
            "investment_index": round(self.investment_index, 1),
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 3),
            "demand_score": round(self.demand_score, 3),
            "access_score": round(self.access_score, 3),
            "diversity_score": round(self.diversity_score, 3),
            "competition_score": round(self.competition_score, 3),
            "building_count": self.building_count,
            "new_buildings": self.new_buildings,
            "residential_units": self.residential_units,
            "new_residential_units": self.new_residential_units,
            "population": round(self.population, 1),
            "competitor_count": self.competitor_count,
            "competitor_density_km2": round(self.competitor_density_km2, 2),
            "poi_count": self.poi_count,
            "poi_diversity": self.poi_diversity,
            "transport_stops": self.transport_stops,
            "distance_to_center_m": round(self.distance_to_center_m, 1),
            "explanation": self.explanation,
            "observed_revenue_growth_pct": (
                round(self.observed_revenue_growth_pct, 2)
                if self.observed_revenue_growth_pct is not None
                else None
            ),
        }


@dataclass
class PipelineResult:
    """Cleaned dataset + scored cells + summary metadata."""

    dataset: CityDataset
    scores: list[LocationScore]
    business_type: str
    settings: Any
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=utc_now_iso)
