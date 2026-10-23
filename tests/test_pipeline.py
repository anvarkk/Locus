from __future__ import annotations

import json

from locus.config import Settings, get_city
from locus.export import write_outputs
from locus.pipeline import PipelineOptions, run_pipeline
from locus.serialization import (
    dataset_from_dict,
    dataset_to_dict,
    read_dataset,
    write_dataset,
)
from locus.synthetic import generate_city


def _small_dataset():
    city = get_city("kazan")
    return generate_city(city, buildings=220, pois=180, stops=45, seed=123)


def test_pipeline_end_to_end() -> None:
    settings = Settings(h3_resolution=9, radius_m=500, current_year=2026)
    dataset = _small_dataset()
    assert dataset.counts()["buildings"] == 220
    result = run_pipeline(
        dataset,
        settings,
        options=PipelineOptions(with_synthetic_revenue=True),
    )
    assert len(result.scores) > 20
    assert result.summary["cells"] == len(result.scores)
    assert result.summary["source"] == "synthetic"
    assert "hypothesis" in result.summary
    indexes = [s.investment_index for s in result.scores]
    assert indexes == sorted(indexes, reverse=True)
    assert result.scores[0].rank == 1
    assert all(0 <= value <= 100 for value in indexes)


def test_outputs_are_written(tmp_path) -> None:
    settings = Settings(h3_resolution=9, radius_m=500, current_year=2026)
    result = run_pipeline(
        _small_dataset(),
        settings,
        options=PipelineOptions(with_synthetic_revenue=True),
    )
    paths = write_outputs(result, tmp_path, tmp_path / "dashboard.html")
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 0

    rows = (tmp_path / "location_index.csv").read_text(encoding="utf-8-sig")
    assert "investment_index" in rows
    assert "recommendation" in rows

    geojson = json.loads(
        (tmp_path / "location_index.geojson").read_text(encoding="utf-8")
    )
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(result.scores)
    assert geojson["features"][0]["geometry"]["type"] == "Polygon"

    dashboard = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
    assert "__PAYLOAD__" not in dashboard
    assert "const DATA =" in dashboard
    assert "Locus" in dashboard
    assert "Проверка гипотезы" in dashboard

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Топ локаций" in report
    assert "Проверка гипотезы" in report


def test_dataset_roundtrip(tmp_path) -> None:
    dataset = _small_dataset()
    path = write_dataset(dataset, tmp_path / "raw.json")
    restored = read_dataset(path)
    assert restored.city == dataset.city
    assert restored.counts() == dataset.counts()
    assert restored.pois[0] == dataset.pois[0]
    assert restored.generated_at == dataset.generated_at


def test_dataset_dict_roundtrip() -> None:
    dataset = _small_dataset()
    payload = dataset_to_dict(dataset)
    restored = dataset_from_dict(json.loads(json.dumps(payload)))
    assert restored.counts() == dataset.counts()
