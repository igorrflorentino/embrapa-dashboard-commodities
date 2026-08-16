{# ────────────────────────────────────────────────────────────────────────────
   Catalog lifecycle — the SQL half of the two-axis vocabulary.

   The Curadoria catalog stores the lifecycle as two STABLE CODES:
     ingestao      ativa | pausada    — keep FETCHING new data?
     visibilidade  visivel | oculto   — researcher SEES it?

   Rows written before the split carry NULL in both and the retired prose enum in
   `ciclo_de_vida` ('Fazer Ingestão e deixar disponível' / '…mas deixar indisponível').
   The log is APPEND-ONLY, so history is never rewritten — these macros translate it on
   read instead, and are the ONE place that knows the legacy mapping.

   They are the twins of serving/curation.py's visibilidade_efetiva / ingestao_efetiva:
   one drives the researcher-facing gate (here), the other the admin editor (Python).
   A drift between them would desync what the editor shows from what the gate hides, so
   test_lifecycle_translation_matches_the_dbt_macro pins them together.
   ──────────────────────────────────────────────────────────────────────────── #}

{% macro catalog_visibilidade(visibilidade_col='visibilidade', ciclo_col='ciclo_de_vida') %}
coalesce(
    {{ visibilidade_col }},
    case {{ ciclo_col }}
        when 'Fazer Ingestão mas deixar indisponível' then 'oculto'
        when 'Fazer Ingestão e deixar disponível' then 'visivel'
    end,
    -- Unknown / unset never hides: the gate is a NOT EXISTS over hidden codes, so
    -- defaulting to 'visivel' keeps an unrecognized value from silently pulling a
    -- produto out of every chart. A wrong value is rejected at write time (400).
    'visivel'
)
{% endmacro %}


{% macro catalog_ingestao(ingestao_col='ingestao') %}
-- NULL predates the axis, and everything active was ingested back then (catalog_resolver
-- filtered on `active` alone) — so NULL MUST read as 'ativa'. Any other default would
-- silently stop ingesting every produto registered before the split.
coalesce({{ ingestao_col }}, 'ativa')
{% endmacro %}
