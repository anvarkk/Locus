from __future__ import annotations

from locus.extract.osm import (
    _building_from_element,
    _poi_from_element,
    _stop_from_element,
    _year,
)


def test_parse_poi_node() -> None:
    element = {
        "type": "node",
        "id": 1,
        "lat": 55.79,
        "lon": 49.10,
        "tags": {"amenity": "cafe", "name": "Coffee", "brand": "Surf"},
    }
    poi = _poi_from_element(element)
    assert poi is not None
    assert poi.category == "cafe"
    assert poi.brand == "Surf"
    assert poi.id == "node/1"


def test_parse_poi_way_uses_center() -> None:
    element = {
        "type": "way",
        "id": 42,
        "center": {"lat": 55.8, "lon": 49.1},
        "tags": {"shop": "coffee", "name": "Coffee Point"},
    }
    poi = _poi_from_element(element)
    assert poi is not None
    assert poi.category == "coffee"
    assert (poi.lat, poi.lon) == (55.8, 49.1)


def test_unknown_poi_is_skipped() -> None:
    assert (
        _poi_from_element({"type": "node", "id": 1, "lat": 1, "lon": 1, "tags": {}})
        is None
    )


def test_parse_building() -> None:
    element = {
        "type": "way",
        "id": 10,
        "center": {"lat": 55.8, "lon": 49.1},
        "tags": {
            "building": "residential",
            "building:levels": "17",
            "building:flats": "320",
            "start_date": "2023-05-01",
            "addr:street": "Ленина",
            "addr:housenumber": "10",
        },
    }
    building = _building_from_element(element)
    assert building is not None
    assert building.levels == 17
    assert building.flats == 320
    assert building.completion_year == 2023
    assert building.address == "Ленина, 10"


def test_year_parser() -> None:
    assert _year("2022-04") == 2022
    assert _year("built in 1999") == 1999
    assert _year("n/a") is None


def test_parse_stop_type() -> None:
    metro = _stop_from_element(
        {
            "type": "node",
            "id": 5,
            "lat": 55.8,
            "lon": 49.1,
            "tags": {"station": "subway", "name": "Metro"},
        }
    )
    assert metro is not None and metro.stop_type == "metro"
