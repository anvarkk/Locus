select
    h3,
    city,
    resolution,
    center_lat,
    center_lon,
    city_lat,
    city_lon,
    geom
from {{ source('analytics', 'h3_cells') }}
