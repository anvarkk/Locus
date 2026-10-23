from __future__ import annotations

from locus.cleaning import (
    clean_buildings,
    clean_pois,
    clean_transport_stops,
    normalize_category,
)
from locus.models import Building, Poi, TransportStop


def test_normalize_osm_categories() -> None:
    assert normalize_category({"shop": "coffee"}) == "coffee"
    assert normalize_category({"amenity": "cafe"}) == "cafe"
    assert normalize_category({"amenity": "parcel_locker"}) == "parcel_locker"
    assert normalize_category({"shop": "outpost"}) == "parcel_locker"
    assert normalize_category({"shop": "supermarket"}) == "supermarket"
    assert normalize_category({"office": "it"}) == "office"
    assert normalize_category({"amenity": "unknown_value"}) == "amenity:unknown_value"
    assert normalize_category({"name": "Surf Coffee"}) == "coffee"


def test_clean_pois_drops_invalid_and_duplicates() -> None:
    pois = [
        Poi("1", "Coffee Point", "coffee", 55.79, 49.10),
        # 20 m away — duplicate by name/category
        Poi("2", "Coffee Point", "coffee", 55.7901, 49.1001),
        Poi("3", "Broken", "coffee", 999, 49.10),
        Poi("4", "", "other", 55.79, 49.10),
        Poi("5", "Bakery", "bakery", 55.80, 49.11),
    ]
    cleaned = clean_pois(pois)
    assert {p.id for p in cleaned} == {"1", "5"}
    assert len(cleaned) == 2


def test_clean_buildings_clamps_and_estimates() -> None:
    buildings = [
        Building("1", 55.79, 49.10, levels=0),
        Building("2", 55.80, 49.11, levels=10, flats=0),
        Building("3", 95, 49.10, levels=5),
    ]
    cleaned = clean_buildings(buildings)
    assert len(cleaned) == 2
    assert cleaned[0].levels == 1
    assert cleaned[0].estimated_flats == 4
    assert cleaned[1].estimated_flats == 40


def test_clean_stops_deduplicates() -> None:
    stops = [
        TransportStop("1", "A", 55.79, 49.10),
        TransportStop("1", "A", 55.79, 49.10),
        TransportStop("2", "B", 0, 0),
    ]
    assert len(clean_transport_stops(stops)) == 1
