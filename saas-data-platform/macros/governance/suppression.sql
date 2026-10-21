{#
    Helpers for reporting on people without exposing a person.
#}

{% macro salary_band(expr) -%}
    {#- 137,500 -> '$120-140k'. Used by the analyst view and the aggregates alike. -#}
    case when {{ expr }} is not null then
        '$' || cast(cast(floor({{ expr }} / 20000) * 20 as integer) as varchar)
            || '-' || cast(cast(floor({{ expr }} / 20000) * 20 + 20 as integer) as varchar) || 'k'
    end
{%- endmacro %}


{% macro suppress(group_size, expr) -%}
    {#- The metric, or null when the group is too small to report safely. -#}
    case when {{ group_size }} >= {{ var('min_group_size') }} then {{ expr }} end
{%- endmacro %}
