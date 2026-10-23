"""Export scored cells to CSV / GeoJSON / Markdown / standalone dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import get_business_type
from .dashboard import render_dashboard
from .geo import cell_polygon_geojson
from .models import LocationScore, PipelineResult

CSV_FIELDS = list(LocationScore.__dataclass_fields__)  # type: ignore[attr-defined]


def _score_payload(score: LocationScore) -> dict:
    payload = score.as_dict()
    payload["h3"] = score.h3
    return payload


def write_csv(scores: list[LocationScore], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for score in scores:
            row = score.as_dict()
            row["h3"] = score.h3
            writer.writerow(row)
    return path


def scores_geojson(scores: list[LocationScore]) -> dict:
    features = []
    for score in scores:
        properties = _score_payload(score)
        properties.pop("h3", None)
        properties["h3"] = score.h3
        features.append(
            {
                "type": "Feature",
                "id": score.h3,
                "geometry": cell_polygon_geojson(score.h3),
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def pois_geojson(result: PipelineResult) -> dict:
    business = get_business_type(result.business_type)
    competitors = set(business.competitor_categories)
    features = []
    for poi in result.dataset.pois:
        features.append(
            {
                "type": "Feature",
                "id": poi.id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [poi.lon, poi.lat],
                },
                "properties": {
                    "name": poi.display_name,
                    "category": poi.category,
                    "brand": poi.brand,
                    "is_competitor": poi.category in competitors,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_geojson(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_summary(summary: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_report(result: PipelineResult, path: Path, top_n: int = 15) -> Path:
    summary = result.summary
    hypothesis = summary.get("hypothesis")
    lines = [
        f"# Индекс инвестиционной привлекательности — {summary.get('city_name', '')}",
        "",
        f"**Бизнес:** {summary.get('business_title', result.business_type)}  ",
        f"**Сетка:** H3 res {summary.get('h3_resolution')}  ",
        f"**Радиус:** {summary.get('radius_m')} м  ",
        f"**Источник данных:** {summary.get('source')}  ",
        f"**Ячеек:** {summary.get('cells', 0)}",
        "",
        "## Как читать индекс",
        "",
        (
            "Индекс 0–100 объединяет спрос (новостройки, население), транспортную "
            "доступность, разнообразие POI и штраф за конкуренцию. "
            "A — открывать, B — рассмотреть, C — наблюдать, D — не рекомендуется. "
            "Подробная формула — в `docs/methodology.md`."
        ),
        "",
    ]
    if hypothesis:
        lines += [
            "## Проверка гипотезы (синтетическая выручка)",
            "",
            (
                f"- Верхний квартиль индекса: **{hypothesis.get('top_quartile_growth_pct')}%** "
                f"роста выручки"
            ),
            f"- Нижний квартиль: **{hypothesis.get('bottom_quartile_growth_pct')}%**",
            f"- Uplift: **{hypothesis.get('uplift_pp')} п.п.**",
            f"- Spearman ρ: **{hypothesis.get('spearman_rho')}**",
            f"- Статус: `{hypothesis.get('status')}`",
            "",
            (
                "> Выручка здесь синтетическая и служит только проверкой пайплайна. "
                "Для реального вывода замените колонку `observed_revenue_growth_pct` "
                "на фактические данные."
            ),
            "",
        ]
    lines += [
        "## Топ локаций",
        "",
        "| # | H3 | Индекс | Рекомендация | Новостройки | Конкуренты | Транспорт |",
        "|---|----|-------:|--------------|------------:|-----------:|----------:|",
    ]
    for score in result.scores[:top_n]:
        lines.append(
            f"| {score.rank} | `{score.h3}` | {score.investment_index:.1f} | "
            f"{score.recommendation} | {score.new_buildings} "
            f"({score.new_residential_units} кв.) | {score.competitor_count} | "
            f"{score.transport_stops} |"
        )
    lines += [
        "",
        "## Ограничения",
        "",
        (
            "- OSM не содержит выручку, реальную проходимость и часть атрибутов "
            "новостроек; год постройки и число квартир часто отсутствуют."
        ),
        "- Демо-режим использует детерминированные синтетические данные.",
        (
            "- Индекс — эвристика для приоритизации локаций, а не замена "
            "финансовой модели."
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_outputs(
    result: PipelineResult,
    out_dir: Path,
    dashboard_path: Path | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = dashboard_path or out_dir / "dashboard.html"
    paths = {
        "csv": write_csv(result.scores, out_dir / "location_index.csv"),
        "geojson": write_geojson(
            scores_geojson(result.scores), out_dir / "location_index.geojson"
        ),
        "pois_geojson": write_geojson(pois_geojson(result), out_dir / "pois.geojson"),
        "summary": write_summary(result.summary, out_dir / "summary.json"),
        "report": write_report(result, out_dir / "report.md"),
        "dashboard": Path(render_dashboard(result, dashboard_path)),
    }
    return paths
