{{ config(materialized='table') }}

select
    h3,
    city,
    resolution,
    center_lat,
    center_lon,
    geom
from {{ ref('stg_h3_cells') }}
