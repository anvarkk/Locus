-- Singular test: index must stay within 0..100.
select *
from {{ ref('mart_investment_index') }}
where investment_index < 0
   or investment_index > 100
