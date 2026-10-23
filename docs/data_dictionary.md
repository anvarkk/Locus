# Data dictionary

## Raw layer

### `raw.pois`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `city` | text | slug города |
| `id` | text | OSM id (`node/123`) или synthetic id |
| `name` | text | название |
| `category` | text | каноническая категория (`coffee`, `cafe`, `parcel_locker`, …) |
| `brand` | text | бренд/оператор, если есть |
| `lat`, `lon` | double precision | координаты |
| `geom` | geometry(Point,4326) | точка для PostGIS |
| `tags` | jsonb | исходные OSM-теги |
| `source` | text | `osm` / `synthetic` |
| `loaded_at` | timestamptz | время загрузки |

### `raw.buildings`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `city`, `id` | text | ключ |
| `address` | text | адрес из `addr:*` |
| `building_type` | text | OSM `building=*` |
| `levels` | integer | этажность (≥ 1) |
| `flats` | integer | число квартир, если известно |
| `completion_year` | integer | год постройки, если известен |
| `lat`, `lon`, `geom` | — | координаты |
| `source`, `loaded_at` | — | метаданные |

### `raw.transport_stops`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `city`, `id` | text | ключ |
| `name` | text | название остановки |
| `stop_type` | text | `bus` / `tram` / `metro` / `rail` |
| `lat`, `lon`, `geom` | — | координаты |
| `source`, `loaded_at` | — | метаданные |

## Analytics layer

### `analytics.h3_cells`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `h3` | text | H3-индекс (PK) |
| `city` | text | slug города |
| `resolution` | integer | разрешение H3 |
| `center_lat`, `center_lon` | double precision | центр ячейки |
| `city_lat`, `city_lon` | double precision | центр города (для distance) |
| `geom` | geometry(Polygon,4326) | полигон ячейки |
| `loaded_at` | timestamptz | время загрузки |

### `analytics.location_index`

Ключ `(h3, business_type)`. Содержит все компоненты (`demand_score`,
`access_score`, `diversity_score`, `competition_score`), `investment_index`,
`confidence`, `rank`, `recommendation`, метрики спроса/конкуренции, геометрию и
`computed_at`.

## Marts (dbt)

### `locus_marts.mart_investment_index`

| Колонка | Описание |
|---------|----------|
| `h3` | H3-ячейка |
| `city` | город |
| `business_type` | `coffee` / `parcel_locker` |
| `rank` | место внутри города и бизнеса (1 = лучший) |
| `investment_index` | индекс 0–100 |
| `recommendation` | A/B/C/D |
| `confidence` | 0–1 |
| `demand_score`, `access_score`, `diversity_score`, `competition_score` | компоненты 0–1 |
| `building_count`, `new_buildings` | здания / новостройки |
| `residential_units`, `new_residential_units` | квартиры / квартиры в новостройках |
| `population` | оценка населения |
| `competitor_count`, `competitor_density_km2` | конкуренция |
| `poi_count`, `poi_diversity` | POI |
| `transport_stops` | остановки |
| `distance_to_center_m` | расстояние до центра |
| `center_lat`, `center_lon` | центр ячейки |

### `locus_marts.dim_h3_cells`

Справочник H3-ячеек с геометрией для BI/QGIS.

## CSV / GeoJSON

`location_index.csv` — плоская выгрузка `LocationScore` (все поля, включая
`explanation` и `observed_revenue_growth_pct`). `location_index.geojson` —
FeatureCollection с H3-полигонами и теми же атрибутами. `pois.geojson` —
точки POI с флагом `is_competitor`.
