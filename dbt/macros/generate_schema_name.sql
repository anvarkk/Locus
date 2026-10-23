{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Keep explicitly configured schema names as-is instead of prefixing them
        with the target schema (which would produce analytics_locus_marts). -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
