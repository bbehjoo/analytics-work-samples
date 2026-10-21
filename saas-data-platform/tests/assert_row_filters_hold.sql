{{ config(group='people') }}  {# owned by People Analytics, so it may read the private dim_employee #}
-- Proof test: a role with a row filter sees exactly the rows the policy allows.
-- For each role in seeds/governance/roles.csv that has a row_filter:
--   * no row outside the filter, and
--   * the same number of rows as dim_employee filtered the same way (nothing missing).
-- Returns one row per breach (expected: 0).
-- depends_on: {{ ref('dim_employee') }}
-- depends_on: {{ ref('roles') }}
-- depends_on: {{ ref('secure_sales_manager_emea__employees') }}
{%- set checks = [] -%}

{%- for role, model_name in secure_employee_views() -%}
    {%- set f = role_config(role).get('row_filter') -%}
    {%- if f -%}
        {%- set view = ref(model_name) -%}
        {%- do checks.append("select '" ~ role ~ "' as role, 'row outside the filter' as problem, count(*) as n "
            ~ "from " ~ view ~ " where not (" ~ f ~ ") having count(*) > 0") -%}
        {%- do checks.append("select '" ~ role ~ "', 'row count differs from policy', "
            ~ "(select count(*) from " ~ view ~ ") - (select count(*) from " ~ ref('dim_employee') ~ " where " ~ f ~ ") "
            ~ "where (select count(*) from " ~ view ~ ") <> (select count(*) from " ~ ref('dim_employee') ~ " where " ~ f ~ ")") -%}
    {%- endif -%}
{%- endfor %}

{% if checks -%}
{{ checks | join('\nunion all\n') }}
{%- else -%}
select null as role, null as problem, null as n where 1 = 0
{%- endif %}
