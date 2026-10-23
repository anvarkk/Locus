{{ config(materialized='view') }}

-- Features for every H3 cell. PostGIS does the 500 m radius aggregation; H3
-- binning itself happens in Python because PostGIS has no native H3 functions.

with cells as (

    select * from {{ ref('stg_h3_cells') }}

),

buildings as (

    select * from {{ ref('stg_buildings') }}

),

pois as (

    select * from {{ ref('stg_pois') }}

),

stops as (

    select * from {{ ref('stg_transport_stops') }}

),

thresholds as (

    select
        extract(year from current_date)::int
        - {{ var('new_building_years', 5) }} as new_building_year

),

building_features as (

    select
        c.h3,
        count(b.id) as building_count,
        count(b.id) filter (
            where b.completion_year >= (select new_building_year from thresholds)
        ) as new_buildings,
        coalesce(sum(b.estimated_flats), 0) as residential_units,
        coalesce(sum(b.estimated_flats) filter (
            where b.completion_year >= (select new_building_year from thresholds)
        ), 0) as new_residential_units
    from cells c
    left join buildings b
        on st_dwithin(
            c.geom::geography,
            b.geom::geography,
            {{ var('radius_m', 500) }}
        )
    group by c.h3

),

competition_features as (

    select
        c.h3,
        count(p.id) filter (
            where p.category in ('coffee', 'cafe', 'bakery')
        ) as coffee_competitors,
        count(p.id) filter (
            where p.category in ('parcel_locker', 'post_office')
        ) as pvz_competitors,
        count(p.id) as poi_count,
        count(distinct p.category) as poi_diversity
    from cells c
    left join pois p
        on st_dwithin(
            c.geom::geography,
            p.geom::geography,
            {{ var('radius_m', 500) }}
        )
    group by c.h3

),

transport_features as (

    select
        c.h3,
        count(t.id) as transport_stops
    from cells c
    left join stops t
        on st_dwithin(
            c.geom::geography,
            t.geom::geography,
            {{ var('radius_m', 500) }}
        )
    group by c.h3

)

select
    c.h3,
    c.city,
    c.resolution,
    c.center_lat,
    c.center_lon,
    b.building_count,
    b.new_buildings,
    b.residential_units,
    b.new_residential_units,
    b.residential_units * {{ var('population_per_unit', 2.2) }} as population,
    coalesce(cf.coffee_competitors, 0) as coffee_competitors,
    coalesce(cf.pvz_competitors, 0) as pvz_competitors,
    coalesce(cf.poi_count, 0) as poi_count,
    coalesce(cf.poi_diversity, 0) as poi_diversity,
    coalesce(tf.transport_stops, 0) as transport_stops,
    st_distance(
        c.geom::geography,
        st_setsrid(st_makepoint(c.city_lon, c.city_lat), 4326)::geography
    ) as distance_to_center_m
from cells c
join building_features b on b.h3 = c.h3
left join competition_features cf on cf.h3 = c.h3
left join transport_features tf on tf.h3 = c.h3
where b.building_count > 0
