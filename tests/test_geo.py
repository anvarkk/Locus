from __future__ import annotations

import math

from locus.config import get_city
from locus.geo import (
    BucketIndex,
    cell_boundary_lonlat,
    covering_cells,
    fast_distance_m,
    haversine_m,
)


def test_haversine_one_degree_latitude() -> None:
    distance = haversine_m(55.0, 49.0, 56.0, 49.0)
    assert math.isclose(distance, 111_195, rel_tol=0.01)


def test_fast_distance_close_to_haversine() -> None:
    exact = haversine_m(55.79, 49.10, 55.80, 49.12)
    approx = fast_distance_m(55.79, 49.10, 55.80, 49.12)
    assert math.isclose(exact, approx, rel_tol=0.01)


def test_covering_cells_inside_radius() -> None:
    city = get_city("kazan")
    cells = covering_cells(city, 9)
    assert len(cells) > 100
    for cell in cells[:25]:
        from locus.geo import cell_center

        lat, lon = cell_center(cell)
        assert haversine_m(city.lat, city.lon, lat, lon) <= city.radius_m + 1


def test_cell_boundary_is_closed_ring() -> None:
    city = get_city("kazan")
    cell = covering_cells(city, 9)[0]
    ring = cell_boundary_lonlat(cell)
    assert len(ring) >= 7
    assert ring[0] == ring[-1]
    assert all(len(point) == 2 for point in ring)


def test_bucket_index_finds_nearby_only() -> None:
    index = BucketIndex()
    index.add(55.79, 49.10, "near")
    index.add(55.90, 49.30, "far")
    found = list(index.query(55.79, 49.10, 500))
    assert found == ["near"]
