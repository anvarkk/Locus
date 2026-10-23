{{ config(materialized='table') }}

select
    h3,
    city,
    business_type,
    rank() over (
        partition by city, business_type
        order by investment_index desc, h3
    ) as rank,
    round(investment_index, 2) as investment_index,
    case
        when investment_index >= 70 then 'A — открывать'
        when investment_index >= 55 then 'B — рассмотреть'
        when investment_index >= 40 then 'C — наблюдать'
        else 'D — не рекомендуется'
    end as recommendation,
    round(confidence, 3) as confidence,
    round(demand_score, 4) as demand_score,
    round(access_score, 4) as access_score,
    round(diversity_score, 4) as diversity_score,
    round(competition_score, 4) as competition_score,
    building_count,
    new_buildings,
    residential_units,
    new_residential_units,
    round(population, 1) as population,
    competitor_count,
    round(competitor_density_km2::numeric, 2) as competitor_density_km2,
    poi_count,
    poi_diversity,
    transport_stops,
    round(distance_to_center_m::numeric, 1) as distance_to_center_m,
    center_lat,
    center_lon
from {{ ref('fct_location_index') }}
