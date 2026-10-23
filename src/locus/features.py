"""Feature engineering for H3 cells using a 500 m (configurable) radius."""

from __future__ import annotations

import math

from .config import BusinessType, City, Settings
from .geo import BucketIndex, cell_center, covering_cells, haversine_m
from .models import Building, CellFeatures, CityDataset, Poi, TransportStop


def _new_building(building: Building, current_year: int, years: int) -> bool:
    return building.completion_year is not None and (
        building.completion_year >= current_year - years
    )


def compute_features(
    dataset: CityDataset,
    business: BusinessType,
    settings: Settings,
) -> list[CellFeatures]:
    """Aggregate demand, competition and accessibility around every cell."""

    city: City = dataset.city
    radius = float(settings.radius_m)
    competitor_categories = set(business.competitor_categories)

    # Bucket size must be at least ~1.2x the radius so the 3x3 neighbourhood is
    # guaranteed to contain every entity within the search circle.
    bucket_size = max(0.01, radius / 111_320 * 1.2)
    poi_index = BucketIndex.build(
        dataset.pois, lambda p: (p.lat, p.lon), size_deg=bucket_size
    )
    building_index = BucketIndex.build(
        dataset.buildings, lambda b: (b.lat, b.lon), size_deg=bucket_size
    )
    stop_index = BucketIndex.build(
        dataset.transport_stops, lambda s: (s.lat, s.lon), size_deg=bucket_size
    )

    area_km2 = math.pi * (radius / 1000) ** 2
    rows: list[CellFeatures] = []

    for cell in covering_cells(city, settings.h3_resolution):
        lat, lon = cell_center(cell)
        nearby_pois: list[Poi] = list(poi_index.query(lat, lon, radius))
        nearby_buildings: list[Building] = list(building_index.query(lat, lon, radius))
        nearby_stops: list[TransportStop] = list(stop_index.query(lat, lon, radius))

        if not nearby_buildings:
            # No residential/commercial buildings => not a candidate location.
            continue

        new_buildings = [
            b
            for b in nearby_buildings
            if _new_building(b, settings.current_year, settings.new_building_years)
        ]
        residential_units = sum(b.estimated_flats for b in nearby_buildings)
        new_units = sum(b.estimated_flats for b in new_buildings)
        population = residential_units * 2.2
        competitors = sum(1 for p in nearby_pois if p.category in competitor_categories)
        diversity = len({p.category for p in nearby_pois})
        rows.append(
            CellFeatures(
                h3=cell,
                city=city.slug,
                center_lat=lat,
                center_lon=lon,
                building_count=len(nearby_buildings),
                new_buildings=len(new_buildings),
                residential_units=residential_units,
                new_residential_units=new_units,
                population=population,
                competitor_count=competitors,
                poi_count=len(nearby_pois),
                poi_diversity=diversity,
                transport_stops=len(nearby_stops),
                competitor_density_km2=competitors / area_km2,
                distance_to_center_m=haversine_m(city.lat, city.lon, lat, lon),
            )
        )
    return rows
