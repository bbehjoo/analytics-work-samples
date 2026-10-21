-- Pay bands by job level and region (USD).
-- depends_on: {{ ref('hris_comp_bands') }}
with source as (
    select * from {{ source('hris', 'comp_bands') }}
)

select
    cast(job_level as varchar)      as job_level,
    cast(region as varchar)         as region,
    cast(band_min_usd as integer)   as band_min,
    cast(band_mid_usd as integer)   as band_mid,
    cast(band_max_usd as integer)   as band_max
from source
