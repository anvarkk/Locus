"""JSON (de)serialisation for datasets and pipeline outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import City
from .models import Building, CityDataset, Poi, TransportStop


def dataset_to_dict(dataset: CityDataset) -> dict:
    return {
        "city": asdict(dataset.city),
        "source": dataset.source,
        "generated_at": dataset.generated_at,
        "pois": [asdict(poi) for poi in dataset.pois],
        "buildings": [asdict(building) for building in dataset.buildings],
        "transport_stops": [asdict(stop) for stop in dataset.transport_stops],
    }


def dataset_from_dict(payload: dict) -> CityDataset:
    city = City(**payload["city"])
    return CityDataset(
        city=city,
        source=payload.get("source", "osm"),
        generated_at=payload.get("generated_at", ""),
        pois=[Poi(**row) for row in payload.get("pois", [])],
        buildings=[Building(**row) for row in payload.get("buildings", [])],
        transport_stops=[
            TransportStop(**row) for row in payload.get("transport_stops", [])
        ],
    )


def write_dataset(dataset: CityDataset, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dataset_to_dict(dataset)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_dataset(path: Path) -> CityDataset:
    return dataset_from_dict(json.loads(path.read_text(encoding="utf-8")))
