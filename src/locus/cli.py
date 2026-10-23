"""Command-line interface for Locus."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .app.server import serve as serve_app
from .config import Settings, get_business_type, get_city
from .export import write_outputs
from .extract.osm import OverpassError, extract_city
from .models import PipelineResult
from .pipeline import PipelineOptions, run_pipeline
from .serialization import read_dataset, write_dataset
from .synthetic import generate_city


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    if getattr(args, "resolution", None):
        settings = replace(settings, h3_resolution=args.resolution)
    if getattr(args, "radius", None):
        settings = replace(settings, radius_m=args.radius)
    if getattr(args, "business_type", None):
        settings = replace(settings, business_type=args.business_type)
    if getattr(args, "year", None):
        settings = replace(settings, current_year=args.year)
    return settings


def _city(args: argparse.Namespace):
    city = get_city(args.city)
    if getattr(args, "radius_km", None):
        city = replace(city, radius_km=args.radius_km)
    return city


def _build(
    dataset,
    settings: Settings,
    *,
    synthetic_revenue: bool,
    output_dir: Path,
    dashboard: Path | None = None,
) -> tuple[PipelineResult, dict[str, Path]]:
    business = get_business_type(settings.business_type)
    result = run_pipeline(
        dataset,
        settings,
        business=business,
        options=PipelineOptions(with_synthetic_revenue=synthetic_revenue),
    )
    paths = write_outputs(result, output_dir, dashboard)
    return result, paths


def _print_result(result: PipelineResult, paths: dict[str, Path]) -> None:
    summary = result.summary
    print()
    print(f"Город: {summary.get('city_name')} · {summary.get('business_title')}")
    print(
        f"Ячеек: {summary.get('cells')} · средний индекс: "
        f"{summary.get('mean_index')} · максимум: {summary.get('max_index')}"
    )
    if summary.get("hypothesis"):
        h = summary["hypothesis"]
        print(
            "Гипотеза (синтетика): uplift "
            f"{h.get('uplift_pp')} п.п., Spearman ρ = {h.get('spearman_rho')}"
        )
    print("\nТоп-5 локаций:")
    for score in result.scores[:5]:
        print(
            f"  #{score.rank:<3} {score.h3}  индекс {score.investment_index:>5.1f}  "
            f"{score.recommendation}  "
            f"новостр. {score.new_buildings}, конкурентов {score.competitor_count}"
        )
    print("\nФайлы:")
    for name, path in paths.items():
        print(f"  {name:<12} {path}")
    print(f"\nОткрыть дашборд: locus serve --dir {paths['dashboard'].parent} --open")


def cmd_demo(args: argparse.Namespace) -> int:
    settings = _settings(args)
    city = _city(args)
    if args.source == "osm":
        print(f"Загружаю OSM для {city.name} (radius {city.radius_km:.1f} км)...")
        try:
            dataset = extract_city(
                city,
                overpass_url=settings.overpass_url,
                user_agent=settings.user_agent,
                radius_m=int(city.radius_m),
            )
        except OverpassError as exc:
            print(f"Overpass недоступен: {exc}", file=sys.stderr)
            print(
                "Использую синтетические данные (--source synthetic).", file=sys.stderr
            )
            dataset = generate_city(city, seed=args.seed)
    else:
        dataset = generate_city(city, seed=args.seed)
    raw_path = write_dataset(dataset, Path(args.out) / f"{city.slug}_raw.json")
    print(f"Raw dataset: {raw_path} ({dataset.counts()})")
    result, paths = _build(
        dataset,
        settings,
        synthetic_revenue=not args.no_revenue,
        output_dir=Path(args.out),
        dashboard=Path(args.dashboard) if args.dashboard else None,
    )
    _print_result(result, paths)
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    settings = _settings(args)
    city = _city(args)
    coverage_m = int(city.radius_m)
    print(f"Overpass: {city.name}, покрытие {coverage_m} м")
    dataset = extract_city(
        city,
        overpass_url=settings.overpass_url,
        user_agent=settings.user_agent,
        radius_m=coverage_m,
    )
    out = Path(args.out)
    path = write_dataset(dataset, out / f"{city.slug}_raw.json")
    print(f"Сохранено: {path} ({dataset.counts()})")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    settings = _settings(args)
    dataset = read_dataset(Path(args.input))
    result, paths = _build(
        dataset,
        settings,
        synthetic_revenue=args.synthetic_revenue,
        output_dir=Path(args.out),
        dashboard=Path(args.dashboard) if args.dashboard else None,
    )
    _print_result(result, paths)
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    from .load.db import load_result

    settings = _settings(args)
    dataset = read_dataset(Path(args.input))
    result, paths = _build(
        dataset,
        settings,
        synthetic_revenue=args.synthetic_revenue,
        output_dir=Path(args.out),
        dashboard=Path(args.dashboard) if args.dashboard else None,
    )
    print(f"Загружаю в PostGIS: {settings.database_url}")
    load_result(result, settings.database_url)
    print("Готово. Теперь: cd dbt && dbt run --profiles-dir .")
    _print_result(result, paths)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    serve_app(
        Path(args.dir),
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="locus",
        description="Locus — индекс инвестиционной привлекательности локаций",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--city", help="slug города из config/cities.json")
        p.add_argument("--resolution", type=int, help="H3 resolution (4-12)")
        p.add_argument("--radius", type=int, help="радиус анализа, метры")
        p.add_argument(
            "--business-type",
            choices=["coffee", "parcel_locker"],
            help="тип бизнеса",
        )
        p.add_argument("--year", type=int, help="текущий год для расчёта новостроек")

    demo = sub.add_parser("demo", help="сгенерировать демо-город и построить индекс")
    common(demo)
    demo.add_argument("--source", choices=["synthetic", "osm"], default="synthetic")
    demo.add_argument("--radius-km", type=float, help="радиус города, км")
    demo.add_argument("--seed", type=int, help="seed синтетических данных")
    demo.add_argument("--out", default="data/processed")
    demo.add_argument("--dashboard", help="путь к dashboard.html")
    demo.add_argument(
        "--no-revenue", action="store_true", help="без синтетической выручки"
    )
    demo.set_defaults(func=cmd_demo)

    extract = sub.add_parser("extract", help="забрать данные из OpenStreetMap")
    common(extract)
    extract.add_argument("--radius-km", type=float)
    extract.add_argument("--out", default="data/raw")
    extract.set_defaults(func=cmd_extract)

    build = sub.add_parser("build", help="посчитать индекс по raw JSON")
    common(build)
    build.add_argument("--input", required=True, help="raw dataset JSON")
    build.add_argument("--out", default="data/processed")
    build.add_argument("--dashboard")
    build.add_argument("--synthetic-revenue", action="store_true")
    build.set_defaults(func=cmd_build)

    load = sub.add_parser("load", help="посчитать индекс и загрузить в PostGIS")
    common(load)
    load.add_argument("--input", required=True)
    load.add_argument("--out", default="data/processed")
    load.add_argument("--dashboard")
    load.add_argument("--synthetic-revenue", action="store_true")
    load.set_defaults(func=cmd_load)

    serve = sub.add_parser("serve", help="локальный дашборд + JSON API")
    serve.add_argument("--dir", default="data/processed")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--open", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to cp1251/cp866; keep Russian output stable.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
