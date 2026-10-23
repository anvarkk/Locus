"""Deterministic synthetic city generator for offline demos and tests.

The generator is deliberately transparent: new residential clusters on the
outskirts get many flats but few competitors, while the old centre has high
POI density and saturated competition. Revenue is generated from the same
latent drivers plus noise, so the validation block demonstrates the pipeline —
it is **not** evidence about the real world.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from .config import BusinessType, City
from .geo import haversine_m
from .models import Building, CityDataset, Poi, TransportStop


@dataclass(frozen=True)
class Cluster:
    lat: float
    lon: float
    sigma_km: float
    kind: str  # old | new | mixed
    weight: float


def _seed_for(city: City) -> int:
    digest = hashlib.sha256(f"locus:{city.slug}".encode()).hexdigest()
    return int(digest[:12], 16)


def _offset(
    lat: float, lon: float, distance_m: float, bearing_deg: float
) -> tuple[float, float]:
    dlat = distance_m * math.cos(math.radians(bearing_deg)) / 111_320
    dlon = (
        distance_m
        * math.sin(math.radians(bearing_deg))
        / (111_320 * max(0.1, math.cos(math.radians(lat))))
    )
    return lat + dlat, lon + dlon


def _gaussian_point(
    rng: random.Random, cluster: Cluster, max_sigma: float = 2.2
) -> tuple[float, float]:
    # Box-Muller, capped to avoid points far outside the cluster.
    r = min(max_sigma, abs(rng.gauss(0, cluster.sigma_km)))
    theta = rng.uniform(0, 2 * math.pi)
    return _offset(cluster.lat, cluster.lon, r * 1000, math.degrees(theta))


def generate_city(
    city: City,
    *,
    buildings: int | None = None,
    pois: int | None = None,
    stops: int | None = None,
    seed: int | None = None,
) -> CityDataset:
    """Build a reproducible dataset for a city."""

    rng = random.Random(seed if seed is not None else _seed_for(city))
    radius_m = city.radius_m
    n_buildings = buildings or max(500, int(radius_m / 6))
    n_pois = pois or max(260, int(radius_m / 12))
    n_stops = stops or max(55, int(radius_m / 75))

    old_town = Cluster(city.lat, city.lon, 1.1, "old", 1.0)
    clusters: list[Cluster] = [old_town]
    # 5-8 residential districts: half new, half mixed.
    for i in range(6):
        distance = rng.uniform(1.1, max(1.3, city.radius_km * 0.92))
        bearing = rng.uniform(0, 360)
        lat, lon = _offset(city.lat, city.lon, distance * 1000, bearing)
        kind = "new" if i % 2 == 0 else "mixed"
        clusters.append(Cluster(lat, lon, rng.uniform(0.35, 0.85), kind, 0.55))

    def pick_cluster(prefer_new: bool = False) -> Cluster:
        if prefer_new:
            new = [c for c in clusters if c.kind in {"new", "mixed"}]
            weights = [c.weight for c in new]
            return rng.choices(new, weights=weights, k=1)[0]
        return rng.choices(clusters, weights=[c.weight for c in clusters], k=1)[0]

    now_year = 2026
    building_rows: list[Building] = []
    for i in range(n_buildings):
        if i < int(n_buildings * 0.62):
            cluster = pick_cluster(prefer_new=True)
            is_new = cluster.kind == "new" or rng.random() < 0.55
        else:
            cluster = rng.choice(clusters)
            is_new = rng.random() < 0.12
        lat, lon = _gaussian_point(rng, cluster)
        if haversine_m(city.lat, city.lon, lat, lon) > radius_m:
            lat, lon = _gaussian_point(rng, cluster, max_sigma=1.2)
        levels = rng.randint(9, 26) if is_new else rng.randint(2, 9)
        year = (
            rng.randint(now_year - 4, now_year) if is_new else rng.randint(1955, 2016)
        )
        flats = levels * rng.randint(4, 8) if is_new else levels * rng.randint(3, 6)
        building_type = "residential"
        if rng.random() < 0.08:
            building_type = "commercial"
        building_rows.append(
            Building(
                id=f"way/{100_000 + i}",
                lat=round(lat, 7),
                lon=round(lon, 7),
                address=f"ул. {cluster.kind.title()}, {rng.randint(1, 180)}",
                building_type=building_type,
                levels=levels,
                flats=flats,
                completion_year=year,
                source="synthetic",
            )
        )

    # --- POIs -------------------------------------------------------------
    # competitor pressure is heavily concentrated in the old centre;
    # new districts receive a small fraction.
    poi_specs: list[tuple[str, int, float, float]] = [
        # category, count, share_near_old_town, share_in_new_districts
        ("coffee", int(n_pois * 0.13), 0.70, 0.12),
        ("cafe", int(n_pois * 0.11), 0.65, 0.12),
        ("bakery", int(n_pois * 0.05), 0.65, 0.10),
        ("parcel_locker", int(n_pois * 0.05), 0.30, 0.40),
        ("post_office", int(n_pois * 0.02), 0.55, 0.10),
        ("supermarket", int(n_pois * 0.07), 0.35, 0.30),
        ("convenience", int(n_pois * 0.10), 0.30, 0.40),
        ("pharmacy", int(n_pois * 0.07), 0.35, 0.30),
        ("bank", int(n_pois * 0.05), 0.70, 0.08),
        ("restaurant", int(n_pois * 0.06), 0.75, 0.05),
        ("fast_food", int(n_pois * 0.07), 0.70, 0.08),
        ("fitness", int(n_pois * 0.03), 0.45, 0.20),
        ("school", int(n_pois * 0.04), 0.30, 0.35),
        ("kindergarten", int(n_pois * 0.04), 0.25, 0.40),
        ("park", int(n_pois * 0.03), 0.25, 0.35),
        ("retail", int(n_pois * 0.08), 0.45, 0.20),
        ("services", int(n_pois * 0.05), 0.50, 0.20),
    ]
    poi_rows: list[Poi] = []
    idx = 0
    for category, count, old_share, new_share in poi_specs:
        for _ in range(count):
            roll = rng.random()
            if roll < old_share:
                lat, lon = _gaussian_point(rng, old_town, max_sigma=1.8)
            elif roll < old_share + new_share:
                lat, lon = _gaussian_point(rng, pick_cluster(prefer_new=True))
            else:
                cluster = rng.choice(clusters)
                lat, lon = _gaussian_point(rng, cluster)
            if haversine_m(city.lat, city.lon, lat, lon) > radius_m:
                lat, lon = _gaussian_point(rng, old_town, max_sigma=1.5)
            brand = _brand_for(category, rng)
            poi_rows.append(
                Poi(
                    id=f"node/{500_000 + idx}",
                    name=_poi_name(category, rng),
                    category=category,
                    lat=round(lat, 7),
                    lon=round(lon, 7),
                    brand=brand,
                    source="synthetic",
                )
            )
            idx += 1

    # --- Transport stops --------------------------------------------------
    stop_rows: list[TransportStop] = []
    for i in range(n_stops):
        if i < n_stops * 0.55:
            lat, lon = _gaussian_point(rng, old_town, max_sigma=2.2)
        else:
            lat, lon = _gaussian_point(rng, pick_cluster(prefer_new=True))
        if haversine_m(city.lat, city.lon, lat, lon) > radius_m:
            lat, lon = _gaussian_point(rng, old_town, max_sigma=2.0)
        stop_type = rng.choices(
            ["bus", "tram", "metro", "rail"], weights=[0.62, 0.18, 0.14, 0.06], k=1
        )[0]
        stop_rows.append(
            TransportStop(
                id=f"node/{900_000 + i}",
                name=f"Остановка {i + 1}",
                lat=round(lat, 7),
                lon=round(lon, 7),
                stop_type=stop_type,
                source="synthetic",
            )
        )

    return CityDataset(
        city=city,
        pois=poi_rows,
        buildings=building_rows,
        transport_stops=stop_rows,
        source="synthetic",
    )


_BRANDS = {
    "coffee": ["Surf Coffee", "Coffee Bean", "One Price Coffee", "Кофе Хауз"],
    "cafe": ["Шоколадница", "Costa Coffee", "Local Cafe"],
    "bakery": ["Хлебный дом", "Булочная"],
    "parcel_locker": ["Ozon", "Wildberries", "Яндекс Маркет", "СДЭК"],
    "post_office": ["Почта России"],
    "supermarket": ["Магнит", "Пятёрочка", "Перекрёсток"],
    "convenience": ["Магнит", "Пятёрочка"],
    "pharmacy": ["Аптека №1", "Ригла"],
    "bank": ["Сбер", "Тинькофф", "ВТБ"],
    "restaurant": ["Вкусно и точка", "Ресторан"],
    "fast_food": ["Вкусно и точка", "KFC", "Burger King"],
    "fitness": ["Планета Фитнес", "Спортзал"],
    "retail": ["Магазин", "М.Видео", "DNS"],
    "services": ["Салон", "Сервис"],
}

_NAMES = {
    "coffee": ["Кофейня", "Coffee to go", "Кофе с собой"],
    "cafe": ["Кафе", "Кофейня-кондитерская"],
    "bakery": ["Пекарня", "Булочная"],
    "parcel_locker": ["ПВЗ", "Постамат"],
    "post_office": ["Отделение почты"],
    "supermarket": ["Супермаркет"],
    "convenience": ["Продукты"],
    "pharmacy": ["Аптека"],
    "bank": ["Банк", "Банкомат"],
    "restaurant": ["Ресторан"],
    "fast_food": ["Фастфуд"],
    "fitness": ["Фитнес-клуб"],
    "school": ["Школа"],
    "kindergarten": ["Детский сад"],
    "park": ["Парк"],
    "retail": ["Магазин"],
    "services": ["Салон услуг"],
}


def _poi_name(category: str, rng: random.Random) -> str:
    base = rng.choice(_NAMES.get(category, ["Точка"]))
    return f"{base} №{rng.randint(1, 99)}"


def _brand_for(category: str, rng: random.Random) -> str | None:
    options = _BRANDS.get(category)
    return rng.choice(options) if options else None


def competitor_categories(types: list[BusinessType]) -> set[str]:
    result: set[str] = set()
    for business in types:
        result.update(business.competitor_categories)
    return result
