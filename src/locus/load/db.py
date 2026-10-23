"""PostGIS loader.

Creates the raw/analytics schemas and upserts the output of the Python pipeline.
The dbt project then builds staging + mart models on top of these tables.
"""

from __future__ import annotations

import json
from typing import Any

from ..geo import cell_boundary_lonlat
from ..models import PipelineResult

DDL = [
    "CREATE EXTENSION IF NOT EXISTS postgis",
    "CREATE SCHEMA IF NOT EXISTS raw",
    "CREATE SCHEMA IF NOT EXISTS analytics",
    """
    CREATE TABLE IF NOT EXISTS raw.pois (
        city            text        NOT NULL,
        id              text        NOT NULL,
        name            text,
        category        text        NOT NULL,
        brand           text,
        lat             double precision NOT NULL,
        lon             double precision NOT NULL,
        geom            geometry(Point, 4326) NOT NULL,
        tags            jsonb       NOT NULL DEFAULT '{}'::jsonb,
        source          text        NOT NULL,
        loaded_at       timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (city, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw.buildings (
        city            text        NOT NULL,
        id              text        NOT NULL,
        address         text,
        building_type   text,
        levels          integer,
        flats           integer,
        completion_year integer,
        lat             double precision NOT NULL,
        lon             double precision NOT NULL,
        geom            geometry(Point, 4326) NOT NULL,
        source          text        NOT NULL,
        loaded_at       timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (city, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw.transport_stops (
        city            text        NOT NULL,
        id              text        NOT NULL,
        name            text,
        stop_type       text,
        lat             double precision NOT NULL,
        lon             double precision NOT NULL,
        geom            geometry(Point, 4326) NOT NULL,
        source          text        NOT NULL,
        loaded_at       timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (city, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analytics.h3_cells (
        h3              text        PRIMARY KEY,
        city            text        NOT NULL,
        resolution      integer     NOT NULL,
        center_lat      double precision NOT NULL,
        center_lon      double precision NOT NULL,
        city_lat        double precision NOT NULL,
        city_lon        double precision NOT NULL,
        geom            geometry(Polygon, 4326) NOT NULL,
        loaded_at       timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analytics.location_index (
        h3                  text        NOT NULL,
        business_type       text        NOT NULL,
        city                text        NOT NULL,
        rank                integer     NOT NULL,
        investment_index    numeric     NOT NULL,
        recommendation      text        NOT NULL,
        confidence          numeric     NOT NULL,
        demand_score        numeric     NOT NULL,
        access_score        numeric     NOT NULL,
        diversity_score     numeric     NOT NULL,
        competition_score   numeric     NOT NULL,
        building_count      integer     NOT NULL,
        new_buildings       integer     NOT NULL,
        residential_units   integer     NOT NULL,
        new_residential_units integer   NOT NULL,
        population          numeric     NOT NULL,
        competitor_count    integer     NOT NULL,
        competitor_density_km2 numeric  NOT NULL,
        poi_count           integer     NOT NULL,
        poi_diversity       integer     NOT NULL,
        transport_stops     integer     NOT NULL,
        distance_to_center_m numeric    NOT NULL,
        explanation         text,
        center_lat          double precision NOT NULL,
        center_lon          double precision NOT NULL,
        geom                geometry(Polygon, 4326) NOT NULL,
        observed_revenue_growth_pct numeric,
        computed_at         timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (h3, business_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS pois_geom_idx ON raw.pois USING gist (geom)",
    "CREATE INDEX IF NOT EXISTS pois_category_idx ON raw.pois (category)",
    "CREATE INDEX IF NOT EXISTS buildings_geom_idx ON raw.buildings USING gist (geom)",
    "CREATE INDEX IF NOT EXISTS stops_geom_idx ON raw.transport_stops USING gist (geom)",
    "CREATE INDEX IF NOT EXISTS h3_cells_geom_idx ON analytics.h3_cells USING gist (geom)",
    "CREATE INDEX IF NOT EXISTS location_index_rank_idx ON analytics.location_index (city, business_type, rank)",
    # Lightweight forward migration for databases created before city centre was
    # stored alongside H3 cells.
    "ALTER TABLE analytics.h3_cells ADD COLUMN IF NOT EXISTS city_lat double precision NOT NULL DEFAULT 0",
    "ALTER TABLE analytics.h3_cells ADD COLUMN IF NOT EXISTS city_lon double precision NOT NULL DEFAULT 0",
]


def connect(database_url: str):
    """Import psycopg lazily so the demo works without database extras."""

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "PostGIS loading requires the 'db' extra: pip install -e '.[db]'"
        ) from exc
    return psycopg.connect(database_url)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        for statement in DDL:
            cur.execute(statement)
    conn.commit()


def _upsert_rows(conn, sql: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()


def load_dataset(conn, result: PipelineResult) -> None:
    dataset = result.dataset
    city = dataset.city.slug

    with conn.cursor() as cur:
        cur.execute("DELETE FROM raw.pois WHERE city = %s", (city,))
        cur.execute("DELETE FROM raw.buildings WHERE city = %s", (city,))
        cur.execute("DELETE FROM raw.transport_stops WHERE city = %s", (city,))
    conn.commit()

    _upsert_rows(
        conn,
        """
        INSERT INTO raw.pois
            (city, id, name, category, brand, lat, lon, geom, tags, source)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s,
             ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s::jsonb, %s)
        ON CONFLICT (city, id) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            brand = EXCLUDED.brand,
            geom = EXCLUDED.geom,
            tags = EXCLUDED.tags,
            loaded_at = now()
        """,
        [
            (
                city,
                poi.id,
                poi.name,
                poi.category,
                poi.brand,
                poi.lat,
                poi.lon,
                poi.lon,
                poi.lat,
                json.dumps(poi.tags, ensure_ascii=False),
                poi.source,
            )
            for poi in dataset.pois
        ],
    )

    _upsert_rows(
        conn,
        """
        INSERT INTO raw.buildings
            (city, id, address, building_type, levels, flats, completion_year,
             lat, lon, geom, source)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s,
             ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
        ON CONFLICT (city, id) DO UPDATE SET
            address = EXCLUDED.address,
            building_type = EXCLUDED.building_type,
            levels = EXCLUDED.levels,
            flats = EXCLUDED.flats,
            completion_year = EXCLUDED.completion_year,
            geom = EXCLUDED.geom,
            loaded_at = now()
        """,
        [
            (
                city,
                building.id,
                building.address,
                building.building_type,
                building.levels,
                building.flats,
                building.completion_year,
                building.lat,
                building.lon,
                building.lon,
                building.lat,
                building.source,
            )
            for building in dataset.buildings
        ],
    )

    _upsert_rows(
        conn,
        """
        INSERT INTO raw.transport_stops
            (city, id, name, stop_type, lat, lon, geom, source)
        VALUES
            (%s, %s, %s, %s, %s, %s,
             ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
        ON CONFLICT (city, id) DO UPDATE SET
            name = EXCLUDED.name,
            stop_type = EXCLUDED.stop_type,
            geom = EXCLUDED.geom,
            loaded_at = now()
        """,
        [
            (
                city,
                stop.id,
                stop.name,
                stop.stop_type,
                stop.lat,
                stop.lon,
                stop.lon,
                stop.lat,
                stop.source,
            )
            for stop in dataset.transport_stops
        ],
    )


def load_scores(conn, result: PipelineResult) -> None:
    city = result.dataset.city.slug
    business_type = result.business_type
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM analytics.location_index WHERE city = %s AND business_type = %s",
            (city, business_type),
        )
    conn.commit()

    _upsert_rows(
        conn,
        """
        INSERT INTO analytics.h3_cells
            (h3, city, resolution, center_lat, center_lon, city_lat, city_lon, geom)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
        ON CONFLICT (h3) DO UPDATE SET
            city = EXCLUDED.city,
            resolution = EXCLUDED.resolution,
            city_lat = EXCLUDED.city_lat,
            city_lon = EXCLUDED.city_lon,
            geom = EXCLUDED.geom,
            loaded_at = now()
        """,
        [
            (
                score.h3,
                city,
                result.settings.h3_resolution,
                score.center_lat,
                score.center_lon,
                city.lat,
                city.lon,
                json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [cell_boundary_lonlat(score.h3)],
                    }
                ),
            )
            for score in result.scores
        ],
    )

    _upsert_rows(
        conn,
        """
        INSERT INTO analytics.location_index (
            h3, business_type, city, rank, investment_index, recommendation,
            confidence, demand_score, access_score, diversity_score,
            competition_score, building_count, new_buildings,
            residential_units, new_residential_units, population,
            competitor_count, competitor_density_km2, poi_count, poi_diversity,
            transport_stops, distance_to_center_m, explanation,
            center_lat, center_lon, geom, observed_revenue_growth_pct
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s
        )
        ON CONFLICT (h3, business_type) DO UPDATE SET
            rank = EXCLUDED.rank,
            investment_index = EXCLUDED.investment_index,
            recommendation = EXCLUDED.recommendation,
            confidence = EXCLUDED.confidence,
            demand_score = EXCLUDED.demand_score,
            access_score = EXCLUDED.access_score,
            diversity_score = EXCLUDED.diversity_score,
            competition_score = EXCLUDED.competition_score,
            building_count = EXCLUDED.building_count,
            new_buildings = EXCLUDED.new_buildings,
            residential_units = EXCLUDED.residential_units,
            new_residential_units = EXCLUDED.new_residential_units,
            population = EXCLUDED.population,
            competitor_count = EXCLUDED.competitor_count,
            competitor_density_km2 = EXCLUDED.competitor_density_km2,
            poi_count = EXCLUDED.poi_count,
            poi_diversity = EXCLUDED.poi_diversity,
            transport_stops = EXCLUDED.transport_stops,
            distance_to_center_m = EXCLUDED.distance_to_center_m,
            explanation = EXCLUDED.explanation,
            geom = EXCLUDED.geom,
            observed_revenue_growth_pct = EXCLUDED.observed_revenue_growth_pct,
            computed_at = now()
        """,
        [
            (
                score.h3,
                business_type,
                city,
                score.rank,
                score.investment_index,
                score.recommendation,
                score.confidence,
                score.demand_score,
                score.access_score,
                score.diversity_score,
                score.competition_score,
                score.building_count,
                score.new_buildings,
                score.residential_units,
                score.new_residential_units,
                score.population,
                score.competitor_count,
                score.competitor_density_km2,
                score.poi_count,
                score.poi_diversity,
                score.transport_stops,
                score.distance_to_center_m,
                score.explanation,
                score.center_lat,
                score.center_lon,
                json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [cell_boundary_lonlat(score.h3)],
                    }
                ),
                score.observed_revenue_growth_pct,
            )
            for score in result.scores
        ],
    )


def load_result(result: PipelineResult, database_url: str | None = None) -> None:
    """Load a pipeline result into PostGIS in one transaction-safe flow."""

    url = database_url or result.settings.database_url
    with connect(url) as conn:
        ensure_schema(conn)
        load_dataset(conn, result)
        load_scores(conn, result)
