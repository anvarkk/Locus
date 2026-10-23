"""Geospatial helpers: distance, bounding boxes and H3 cell utilities."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from typing import TypeVar

import h3

from .config import City

EARTH_RADIUS_M = 6_371_008.8
T = TypeVar("T")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def fast_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular approximation — accurate to <0.5% for 500 m radii."""

    dlat = (lat2 - lat1) * 111_320.0
    dlon = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def bbox(city: City, padding_km: float = 0.2) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for a circular area."""

    dlat = (city.radius_km + padding_km) / 111.32
    dlon = (city.radius_km + padding_km) / (
        111.32 * max(0.05, math.cos(math.radians(city.lat)))
    )
    return city.lat - dlat, city.lon - dlon, city.lat + dlat, city.lon + dlon


def covering_cells(city: City, resolution: int) -> list[str]:
    """H3 cells whose centres fall inside the city's analysis radius."""

    center = h3.latlng_to_cell(city.lat, city.lon, resolution)
    # Average edge length at res 9 is ~174 m; k rings cover k*edge metres.
    edge_m = max(50.0, h3.average_hexagon_edge_length(resolution, unit="m"))
    k = math.ceil(city.radius_m / edge_m) + 1
    cells: list[str] = []
    for cell in h3.grid_disk(center, k):
        lat, lon = h3.cell_to_latlng(cell)
        if haversine_m(city.lat, city.lon, lat, lon) <= city.radius_m:
            cells.append(cell)
    cells.sort()
    return cells


def cell_center(cell: str) -> tuple[float, float]:
    return h3.cell_to_latlng(cell)


def cell_boundary_lonlat(cell: str) -> list[list[float]]:
    """Closed GeoJSON ring for an H3 cell."""

    ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell)]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def cell_polygon_geojson(cell: str) -> dict:
    return {"type": "Polygon", "coordinates": [cell_boundary_lonlat(cell)]}


class BucketIndex:
    """Coarse lat/lon bucket index for fast nearby lookups without PostGIS.

    The production path uses a GiST index in PostGIS. This structure keeps the
    local/demo pipeline in pure Python and is ~50-100x faster than scanning all
    entities for every cell.
    """

    def __init__(self, size_deg: float = 0.01) -> None:
        self.size_deg = size_deg
        self._buckets: dict[tuple[int, int], list[tuple[float, float, T]]] = {}

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return math.floor(lat / self.size_deg), math.floor(lon / self.size_deg)

    def add(self, lat: float, lon: float, item: T) -> None:
        self._buckets.setdefault(self._key(lat, lon), []).append((lat, lon, item))

    def query(self, lat: float, lon: float, radius_m: float) -> Iterator[T]:
        key_lat, key_lon = self._key(lat, lon)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for item_lat, item_lon, item in self._buckets.get(
                    (key_lat + dy, key_lon + dx), ()
                ):
                    if fast_distance_m(lat, lon, item_lat, item_lon) <= radius_m:
                        yield item

    @classmethod
    def build(
        cls, items: Iterable[T], get_coords, size_deg: float = 0.01
    ) -> BucketIndex:
        index = cls(size_deg=size_deg)
        for item in items:
            lat, lon = get_coords(item)
            index.add(lat, lon, item)
        return index
