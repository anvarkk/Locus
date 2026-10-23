select
    city,
    id,
    name,
    stop_type,
    lat,
    lon,
    geom,
    source,
    loaded_at
from {{ source('raw', 'transport_stops') }}
where geom is not null
