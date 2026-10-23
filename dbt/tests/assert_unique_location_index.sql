-- Singular test: (h3, business_type) must be unique in the final mart.
select
    h3,
    business_type,
    count(*) as rows
from {{ ref('mart_investment_index') }}
group by h3, business_type
having count(*) > 1
