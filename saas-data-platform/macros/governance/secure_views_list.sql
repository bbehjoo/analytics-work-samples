{% macro secure_employee_views() %}
    {#- [(role, model_name)] for every secure_<role>__employees model in the project. -#}
    {%- set views = [] -%}
    {%- if execute -%}
        {%- for n in graph.nodes.values() -%}
            {%- if n.resource_type == 'model' and n.name.startswith('secure_') and n.name.endswith('__employees') -%}
                {%- do views.append((n.name[7:-11], n.name)) -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(views | sort) }}
{% endmacro %}
