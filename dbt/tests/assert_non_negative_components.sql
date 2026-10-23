-- Singular test: demand components must be present and non-negative.
select *
from {{ ref('fct_location_index') }}
where demand_score < 0
   or access_score < 0
   or competition_score < 0
   or confidence < 0
   or confidence > 1
   or competitor_count < 0
