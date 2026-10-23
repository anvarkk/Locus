"""Cleaning and category normalisation of raw geospatial data."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

from .geo import fast_distance_m
from .models import Building, CityDataset, Poi, TransportStop

# Canonical categories used by the index. Keep in sync with dbt staging models.
AMENITY_CATEGORIES = {
    "cafe": "cafe",
    "restaurant": "restaurant",
    "fast_food": "fast_food",
    "bar": "bar",
    "pub": "bar",
    "bakery": "bakery",
    "ice_cream": "cafe",
    "bank": "bank",
    "atm": "bank",
    "post_office": "post_office",
    "parcel_locker": "parcel_locker",
    "pharmacy": "pharmacy",
    "hospital": "healthcare",
    "clinic": "healthcare",
    "dentist": "healthcare",
    "school": "school",
    "kindergarten": "kindergarten",
    "university": "education",
    "college": "education",
    "library": "education",
    "marketplace": "market",
    "community_centre": "community",
    "place_of_worship": "worship",
    "fuel": "fuel",
    "parking": "parking",
    "bus_station": "transport",
}

SHOP_CATEGORIES = {
    "coffee": "coffee",
    "bakery": "bakery",
    "outpost": "parcel_locker",
    "parcel_locker": "parcel_locker",
    "supermarket": "supermarket",
    "convenience": "convenience",
    "greengrocer": "grocery",
    "butcher": "grocery",
    "deli": "grocery",
    "kiosk": "kiosk",
    "chemist": "pharmacy",
    "beauty": "services",
    "hairdresser": "services",
    "clothes": "retail",
    "shoes": "retail",
    "electronics": "retail",
    "mobile_phone": "retail",
    "furniture": "retail",
    "stationery": "retail",
    "books": "retail",
    "sports": "retail",
    "toys": "retail",
    "pet": "retail",
    "alcohol": "retail",
    "tobacco": "retail",
    "car": "auto",
    "car_repair": "auto",
    "doityourself": "retail",
    "mall": "mall",
}

LEISURE_CATEGORIES = {
    "fitness_centre": "fitness",
    "sports_centre": "fitness",
    "park": "park",
    "playground": "park",
    "cinema": "entertainment",
    "theatre": "entertainment",
    "nightclub": "entertainment",
}

OFFICE_CATEGORIES = {
    "coworking": "office",
    "company": "office",
    "estate_agent": "services",
    "insurance": "services",
    "lawyer": "services",
    "accountant": "services",
    "it": "office",
    "educational_institution": "education",
}

CATEGORY_MAP: dict[str, dict[str, str]] = {
    "amenity": AMENITY_CATEGORIES,
    "shop": SHOP_CATEGORIES,
    "leisure": LEISURE_CATEGORIES,
    "office": OFFICE_CATEGORIES,
    "tourism": {
        "hotel": "hotel",
        "museum": "entertainment",
        "attraction": "attraction",
    },
    "building": {"commercial": "commercial", "retail": "commercial"},
}

BRAND_CATEGORY_HINTS = {
    "coffee": ("coffee", "coffee shop", "кофе", "surf coffee", "one price coffee"),
    "parcel_locker": ("ozon", "wildberries", "яндекс маркет", "сдэк", "boxberry"),
}


def normalize_category(tags: dict[str, Any]) -> str:
    """Map OSM tags to a small, stable category vocabulary."""

    for key in ("amenity", "shop", "leisure", "office", "tourism", "building"):
        raw = str(tags.get(key, "")).strip().lower()
        if raw and raw in CATEGORY_MAP.get(key, {}):
            return CATEGORY_MAP[key][raw]
    # Unknown values still get a useful family-level fallback.
    for key in ("amenity", "shop", "leisure", "office", "tourism"):
        if tags.get(key):
            return f"{key}:{str(tags[key]).lower()}"
    name = str(tags.get("name", "")).lower()
    for category, hints in BRAND_CATEGORY_HINTS.items():
        if any(hint in name for hint in hints):
            return category
    return "other"


def _valid_coords(lat: float | None, lon: float | None) -> bool:
    return (
        lat is not None
        and lon is not None
        and math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
        and not (lat == 0 and lon == 0)
    )


def _norm_name(name: str | None) -> str:
    if not name:
        return ""
    value = name.lower().strip()
    value = re.sub(r"[«»\"'`]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def clean_pois(pois: Iterable[Poi]) -> list[Poi]:
    """Drop invalid POIs and merge obvious duplicates within the same cell."""

    valid: list[Poi] = []
    for poi in pois:
        if not _valid_coords(poi.lat, poi.lon):
            continue
        category = poi.category or normalize_category(poi.tags)
        if category == "other":
            continue
        valid.append(
            Poi(
                id=poi.id,
                name=poi.name.strip() if poi.name else "",
                category=category,
                lat=poi.lat,
                lon=poi.lon,
                brand=poi.brand,
                amenity=poi.amenity,
                shop=poi.shop,
                source=poi.source,
                tags=poi.tags,
            )
        )

    # Dedupe by normalised name + category + ~50 m. OSM sometimes has a node
    # and a way for the same coffee shop.
    valid.sort(key=lambda p: (p.category, _norm_name(p.name), p.lat, p.lon))
    result: list[Poi] = []
    for poi in valid:
        duplicate = False
        for kept in reversed(result[-30:]):
            if kept.category != poi.category:
                continue
            if _norm_name(kept.name) != _norm_name(poi.name):
                continue
            if not _norm_name(poi.name):
                continue
            if fast_distance_m(kept.lat, kept.lon, poi.lat, poi.lon) <= 50:
                duplicate = True
                break
        if not duplicate:
            result.append(poi)
    return result


def clean_buildings(buildings: Iterable[Building]) -> list[Building]:
    result: list[Building] = []
    for building in buildings:
        if not _valid_coords(building.lat, building.lon):
            continue
        levels = max(1, min(120, int(building.levels or 1)))
        flats = building.flats
        if flats is not None and flats <= 0:
            flats = None
        year = building.completion_year
        if year is not None and not (1800 <= year <= 2100):
            year = None
        result.append(
            Building(
                id=building.id,
                lat=building.lat,
                lon=building.lon,
                address=building.address,
                building_type=building.building_type or "residential",
                levels=levels,
                flats=flats,
                completion_year=year,
                source=building.source,
            )
        )
    return result


def clean_transport_stops(stops: Iterable[TransportStop]) -> list[TransportStop]:
    result: list[TransportStop] = []
    seen: set[tuple[str, int, int]] = set()
    for stop in stops:
        if not _valid_coords(stop.lat, stop.lon):
            continue
        key = (stop.id, round(stop.lat * 1e4), round(stop.lon * 1e4))
        if key in seen:
            continue
        seen.add(key)
        result.append(stop)
    return result


def clean_dataset(dataset: CityDataset) -> CityDataset:
    return CityDataset(
        city=dataset.city,
        pois=clean_pois(dataset.pois),
        buildings=clean_buildings(dataset.buildings),
        transport_stops=clean_transport_stops(dataset.transport_stops),
        source=dataset.source,
        generated_at=dataset.generated_at,
    )
