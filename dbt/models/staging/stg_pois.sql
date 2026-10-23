select
    city,
    id,
    name,
    category,
    brand,
    lat,
    lon,
    geom,
    tags,
    source,
    loaded_at
from {{ source('raw', 'pois') }}
where geom is not null
