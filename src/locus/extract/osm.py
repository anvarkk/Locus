"""Extract POIs, buildings and public transport stops from OpenStreetMap.

Uses the Overpass API. The parser is intentionally tolerant: OSM tags are
heterogeneous and many buildings have no completion year or flat count. Missing
attributes are handled by cleaning heuristics / explicit confidence scores.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from ..cleaning import normalize_category
from ..config import City
from ..models import Building, CityDataset, Poi, TransportStop, utc_now_iso

POI_QUERY = """
[out:json][timeout:180];
(
  nwr["amenity"~"^(cafe|restaurant|fast_food|bar|pub|bakery|ice_cream|bank|atm|post_office|parcel_locker|pharmacy|hospital|clinic|dentist|school|kindergarten|university|college|library|community_centre|place_of_worship|fuel|parking|bus_station)$"](around:{radius},{lat},{lon});
  nwr["shop"~"^(coffee|bakery|outpost|parcel_locker|supermarket|convenience|greengrocer|butcher|deli|kiosk|chemist|beauty|hairdresser|clothes|shoes|electronics|mobile_phone|furniture|stationery|books|sports|toys|pet|alcohol|tobacco|car|car_repair|doityourself|mall)$"](around:{radius},{lat},{lon});
  nwr["leisure"~"^(fitness_centre|sports_centre|park|playground|cinema|theatre|nightclub)$"](around:{radius},{lat},{lon});
  nwr["office"](around:{radius},{lat},{lon});
);
out center tags;
"""

TRANSPORT_QUERY = """
[out:json][timeout:120];
(
  node["highway"="bus_stop"](around:{radius},{lat},{lon});
  node["public_transport"="stop_position"](around:{radius},{lat},{lon});
  node["railway"~"^(station|tram_stop|halt)$"](around:{radius},{lat},{lon});
  node["tram"="yes"](around:{radius},{lat},{lon});
  node["station"="subway"](around:{radius},{lat},{lon});
);
out center tags;
"""

BUILDING_QUERY = """
[out:json][timeout:240];
(
  way["building"](around:{radius},{lat},{lon});
  relation["building"](around:{radius},{lat},{lon});
);
out center tags;
"""


class OverpassError(RuntimeError):
    pass


def fetch_overpass(
    query: str,
    url: str,
    user_agent: str,
    *,
    retries: int = 3,
    timeout_s: int = 240,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": user_agent},
                timeout=timeout_s,
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                raise OverpassError(
                    f"Overpass HTTP {response.status_code}: {response.text[:200]}"
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, OverpassError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(2**attempt)
    raise OverpassError(
        f"Overpass request failed after {retries} attempts: {last_error}"
    )


def _center(element: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _year(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value)
    for token in text.replace("-", " ").replace(".", " ").split():
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1800 <= year <= 2100:
                return year
    return None


def _address(tags: dict[str, Any]) -> str | None:
    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    if street and house:
        return f"{street}, {house}"
    return tags.get("addr:full")


def _poi_from_element(element: dict[str, Any]) -> Poi | None:
    coords = _center(element)
    if coords is None:
        return None
    tags = element.get("tags", {}) or {}
    category = normalize_category(tags)
    if category == "other":
        return None
    return Poi(
        id=f"{element.get('type', 'node')}/{element['id']}",
        name=tags.get("name", ""),
        category=category,
        lat=coords[0],
        lon=coords[1],
        brand=tags.get("brand") or tags.get("operator"),
        amenity=tags.get("amenity"),
        shop=tags.get("shop"),
        source="osm",
        tags=tags,
    )


def _building_from_element(element: dict[str, Any]) -> Building | None:
    coords = _center(element)
    if coords is None:
        return None
    tags = element.get("tags", {}) or {}
    if tags.get("building") in {None, "no"}:
        return None
    levels = _int_or_none(tags.get("building:levels")) or 5
    flats = _int_or_none(tags.get("building:flats"))
    year = _year(tags.get("start_date")) or _year(tags.get("building:year"))
    return Building(
        id=f"{element.get('type', 'way')}/{element['id']}",
        lat=coords[0],
        lon=coords[1],
        address=_address(tags),
        building_type=tags.get("building", "residential"),
        levels=levels,
        flats=flats,
        completion_year=year,
        source="osm",
    )


def _stop_from_element(element: dict[str, Any]) -> TransportStop | None:
    coords = _center(element)
    if coords is None:
        return None
    tags = element.get("tags", {}) or {}
    if tags.get("railway") in {"station", "halt"} or tags.get("station") == "subway":
        stop_type = "metro" if tags.get("station") == "subway" else "rail"
    elif tags.get("railway") == "tram_stop" or tags.get("tram") == "yes":
        stop_type = "tram"
    else:
        stop_type = "bus"
    return TransportStop(
        id=f"{element.get('type', 'node')}/{element['id']}",
        name=tags.get("name", ""),
        lat=coords[0],
        lon=coords[1],
        stop_type=stop_type,
        source="osm",
    )


def extract_city(
    city: City,
    *,
    overpass_url: str,
    user_agent: str,
    radius_m: int | None = None,
) -> CityDataset:
    radius = radius_m or int(city.radius_m)
    fmt = {"radius": radius, "lat": city.lat, "lon": city.lon}

    poi_payload = fetch_overpass(POI_QUERY.format(**fmt), overpass_url, user_agent)
    stop_payload = fetch_overpass(
        TRANSPORT_QUERY.format(**fmt), overpass_url, user_agent
    )
    building_payload = fetch_overpass(
        BUILDING_QUERY.format(**fmt), overpass_url, user_agent
    )

    pois = [
        poi
        for element in poi_payload.get("elements", [])
        if (poi := _poi_from_element(element)) is not None
    ]
    buildings = [
        building
        for element in building_payload.get("elements", [])
        if (building := _building_from_element(element)) is not None
    ]
    stops = [
        stop
        for element in stop_payload.get("elements", [])
        if (stop := _stop_from_element(element)) is not None
    ]
    return CityDataset(
        city=city,
        pois=pois,
        buildings=buildings,
        transport_stops=stops,
        source="osm",
        generated_at=utc_now_iso(),
    )
