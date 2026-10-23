{{ config(materialized='table') }}

-- Same scoring formula as src/locus/scoring.py. Normalisation is min-max over
-- the city; production analytics normally uses percent_rank for robustness
-- against outliers.

with features as (

    select * from {{ ref('int_cell_features') }}

),

normalized as (

    select
        *,
        case
            when max(new_residential_units) over () > min(new_residential_units) over ()
            then (new_residential_units - min(new_residential_units) over ())::numeric
                 / (max(new_residential_units) over () - min(new_residential_units) over ())
            else 0
        end as new_units_norm,
        case
            when max(new_buildings) over () > min(new_buildings) over ()
            then (new_buildings - min(new_buildings) over ())::numeric
                 / (max(new_buildings) over () - min(new_buildings) over ())
            else 0
        end as new_buildings_norm,
        case
            when max(population) over () > min(population) over ()
            then (population - min(population) over ())::numeric
                 / (max(population) over () - min(population) over ())
            else 0
        end as population_norm,
        case
            when max(transport_stops) over () > min(transport_stops) over ()
            then (transport_stops - min(transport_stops) over ())::numeric
                 / (max(transport_stops) over () - min(transport_stops) over ())
            else 0
        end as transport_norm,
        case
            when max(poi_diversity) over () > min(poi_diversity) over ()
            then (poi_diversity - min(poi_diversity) over ())::numeric
                 / (max(poi_diversity) over () - min(poi_diversity) over ())
            else 0
        end as diversity_norm,
        case
            when max(coffee_competitors) over () > min(coffee_competitors) over ()
            then (coffee_competitors - min(coffee_competitors) over ())::numeric
                 / (max(coffee_competitors) over () - min(coffee_competitors) over ())
            else 0
        end as coffee_competition_norm,
        case
            when max(pvz_competitors) over () > min(pvz_competitors) over ()
            then (pvz_competitors - min(pvz_competitors) over ())::numeric
                 / (max(pvz_competitors) over () - min(pvz_competitors) over ())
            else 0
        end as pvz_competition_norm
    from features

),

components as (

    select
        *,
        0.50 * new_units_norm
        + 0.30 * new_buildings_norm
        + 0.20 * population_norm as demand_score
    from normalized

),

unioned as (

    -- Coffee: weights from config/business_types.json
    select
        h3,
        city,
        'coffee'::text as business_type,
        resolution,
        center_lat,
        center_lon,
        demand_score,
        transport_norm as access_score,
        diversity_norm as diversity_score,
        coffee_competition_norm as competition_score,
        100.0 * (
            0.45 * demand_score
            + 0.20 * transport_norm
            + 0.10 * diversity_norm
            + 0.25 * (1.0 - coffee_competition_norm)
        ) as investment_index,
        least(
            1.0,
            0.35 + 0.65 * least(
                1.0,
                (building_count * 2 + poi_count + transport_stops * 3) / 80.0
            )
        ) as confidence,
        building_count,
        new_buildings,
        residential_units,
        new_residential_units,
        population,
        coffee_competitors as competitor_count,
        coffee_competitors
            / (pi() * power({{ var('radius_m', 500) }} / 1000.0, 2)) as competitor_density_km2,
        poi_count,
        poi_diversity,
        transport_stops,
        distance_to_center_m
    from components

    union all

    -- Parcel locker / PVZ: weights from config/business_types.json
    select
        h3,
        city,
        'parcel_locker'::text as business_type,
        resolution,
        center_lat,
        center_lon,
        demand_score,
        transport_norm as access_score,
        diversity_norm as diversity_score,
        pvz_competition_norm as competition_score,
        100.0 * (
            0.50 * demand_score
            + 0.15 * transport_norm
            + 0.10 * diversity_norm
            + 0.25 * (1.0 - pvz_competition_norm)
        ) as investment_index,
        least(
            1.0,
            0.35 + 0.65 * least(
                1.0,
                (building_count * 2 + poi_count + transport_stops * 3) / 80.0
            )
        ) as confidence,
        building_count,
        new_buildings,
        residential_units,
        new_residential_units,
        population,
        pvz_competitors as competitor_count,
        pvz_competitors
            / (pi() * power({{ var('radius_m', 500) }} / 1000.0, 2)) as competitor_density_km2,
        poi_count,
        poi_diversity,
        transport_stops,
        distance_to_center_m
    from components

)

select * from unioned
