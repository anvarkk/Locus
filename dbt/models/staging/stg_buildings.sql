select
    city,
    id,
    address,
    building_type,
    greatest(1, coalesce(levels, 5)) as levels,
    case
        when flats is not null and flats > 0 then flats
        else greatest(1, coalesce(levels, 5) * 4)
    end as estimated_flats,
    completion_year,
    lat,
    lon,
    geom,
    source,
    loaded_at
from {{ source('raw', 'buildings') }}
where geom is not null
