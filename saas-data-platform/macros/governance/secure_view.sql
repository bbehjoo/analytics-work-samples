{#
    Governance as code: one policy, applied the same way everywhere.

      * Each column that describes a person is tagged in YAML (config.meta):
          sensitivity  internal | confidential | pii | restricted
          category     a row of seeds/governance/access_policy.csv
      * access_policy.csv says, per category, what each role gets:
          full | mask | pseudonymize | band | flag | hide
      * seeds/governance/roles.csv adds a row filter per role.
      * secure_view(model, role) turns the two into one masked, filtered SELECT.

    Private by default: a column with no category, a category with no rule, or a
    treatment the column can't take (e.g. "band" on an email) is left out.
#}


{% macro governed_columns(model_name) %}
    {#- The model's documented columns, in YAML order, with their governance meta. -#}
    {%- set cols = [] -%}
    {%- if execute -%}
        {%- set node = graph.nodes.values()
              | selectattr('resource_type', 'equalto', 'model')
              | selectattr('name', 'equalto', model_name) | first -%}
        {%- for name, col in node.columns.items() -%}
            {%- set meta = col.config.meta if (col.config and col.config.meta) else col.meta -%}
            {%- do cols.append({
                  'name': name,
                  'sensitivity': meta.get('sensitivity'),
                  'category': meta.get('category'),
                  'mask': meta.get('mask', 'text'),
                  'band': meta.get('band'),
                  'pseudonym_prefix': meta.get('pseudonym_prefix', 'ID-'),
                  'pseudonym_source': meta.get('pseudonym_source', name),
                  'flag_label': meta.get('flag_label', 'Yes')
              }) -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(cols) }}
{% endmacro %}


{% macro access_policy() %}
    {#- {category: {sensitivity, <role>: treatment, ...}} read from the policy seed. -#}
    {%- set relation = ref('access_policy') -%}
    {%- set policy = {} -%}
    {%- if execute -%}
        {%- set rows = run_query('select * from ' ~ relation) -%}
        {%- for r in rows -%}
            {%- set entry = {} -%}
            {%- for c in rows.column_names -%}{%- do entry.update({c: r[c]}) -%}{%- endfor -%}
            {%- do policy.update({r['category']: entry}) -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(policy) }}
{% endmacro %}


{% macro role_config(role) %}
    {#- {label, row_filter, description} for one role, from the roles seed. -#}
    {%- set relation = ref('roles') -%}
    {%- set cfg = {} -%}
    {%- if execute -%}
        {%- set rows = run_query("select * from " ~ relation ~ " where role = '" ~ role ~ "'") -%}
        {%- if rows | length == 0 -%}
            {{ exceptions.raise_compiler_error("Role '" ~ role ~ "' is not in seeds/governance/roles.csv") }}
        {%- endif -%}
        {%- for c in rows.column_names -%}{%- do cfg.update({c: rows[0][c]}) -%}{%- endfor -%}
    {%- endif -%}
    {{ return(cfg) }}
{% endmacro %}


{% macro treatment_for(policy, col, role) %}
    {#- The treatment a role gets for a column; "hide" when anything is missing. -#}
    {%- set rule = policy.get(col.category) -%}
    {%- set t = (rule.get(role) if rule else none) or 'hide' -%}
    {%- if t == 'band' and not col.band -%}{%- set t = 'hide' -%}{%- endif -%}
    {%- if t == 'mask' and col.mask not in ('email', 'text') -%}{%- set t = 'hide' -%}{%- endif -%}
    {{ return(t) }}
{% endmacro %}


{% macro treated_column(col, treatment) %}
    {#- The SQL expression for one column under one treatment. -#}
    {%- set c = col.name -%}
    {%- if treatment == 'full' -%}
        {{ c }}
    {%- elif treatment == 'pseudonymize' -%}
        {#- salted hash: stable (same person, same pseudonym, so joins and counts
            still work) but not reversible without the salt -#}
        case when {{ col.pseudonym_source }} is not null then
            '{{ col.pseudonym_prefix }}' || upper(substr({{ dbt.hash("cast(" ~ col.pseudonym_source ~ " as varchar) || '" ~ var('pseudonym_salt') ~ "'") }}, 1, 6))
        end
    {%- elif treatment == 'mask' and col.mask == 'email' -%}
        left({{ c }}, 1) || '•••@' || {{ dbt.split_part(c, "'@'", 2) }}
    {%- elif treatment == 'mask' -%}
        left(cast({{ c }} as varchar), 1) || '•••'
    {%- elif treatment == 'band' and col.band == 'salary' -%}
        {{ salary_band(c) }}
    {%- elif treatment == 'band' and col.band == 'age' -%}
        cast(cast(floor({{ dbt.datediff(c, "cast('" ~ var('people_as_of') ~ "' as date)", 'year') }} / 10) * 10 as integer) as varchar) || 's'
    {%- elif treatment == 'flag' -%}
        case when {{ c }} is not null then '{{ col.flag_label }}' end
    {%- else -%}
        {{ exceptions.raise_compiler_error("No SQL for treatment '" ~ treatment ~ "' on column " ~ c) }}
    {%- endif -%}
{% endmacro %}


{% macro secure_view(model_name, role) %}
    {#- One role's view of a governed model: columns treated, rows filtered. -#}
    {%- set relation = ref(model_name) -%}
    {%- set policy = access_policy() -%}
    {%- set cfg = role_config(role) -%}
    {%- if not execute -%}
        select 1 as parsing
    {%- else -%}
        {%- set kept = [] -%}
        {%- for col in governed_columns(model_name) -%}
            {%- set t = treatment_for(policy, col, role) -%}
            {%- if t != 'hide' -%}{%- do kept.append((col, t)) -%}{%- endif -%}
        {%- endfor -%}
        {%- if kept | length == 0 -%}
            {{ exceptions.raise_compiler_error("Role '" ~ role ~ "' may see no column of " ~ model_name ~ "; serve it aggregates instead") }}
        {%- endif %}
-- {{ role }} view of {{ model_name }}, generated from seeds/governance/access_policy.csv
select
{%- for col, t in kept %}
    {{ treated_column(col, t) }} as {{ col.name }}{{ "," if not loop.last }}  -- {{ col.category }}: {{ t }}
{%- endfor %}
from {{ relation }}
{%- if cfg.get('row_filter') %}
where {{ cfg.get('row_filter') }}
{%- endif %}
    {%- endif -%}
{% endmacro %}
