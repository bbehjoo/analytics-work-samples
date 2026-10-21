{#
    Use custom schema names *literally* (staging, marts, raw_salesforce, ...)
    instead of dbt's default "<target_schema>_<custom>" concatenation. This keeps
    the local DuckDB database organized into readable schemas that match the
    layered architecture. In a production deployment you would typically keep the
    default behavior (which namespaces by target) — this override is for clarity
    in a self-contained sample.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
