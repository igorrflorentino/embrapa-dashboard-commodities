{#-
    hidden_code_predicate — the Ciclo de Vida visibility gate (F7), as a SQL predicate.

    Returns a NOT EXISTS clause that EXCLUDES any Gold row whose code equals a hidden
    commodity's code (dim_produto_visibility). Drop it into the WHERE of any model
    that enumerates commodities for a RESEARCHER (the serving marts, the quality union).
    A code with no hidden-code row passes (visible). The Python gateway's direct-Gold
    readers use the equivalent serving/sql.visibility_clause() against the SAME view
    (one source of truth).

    A identidade de um produto é (banco, TABELA, código), então nos bancos multi-tabela o
    predicado casa também a tabela: esconder a metade extração (289) de um código deixa a
    metade silvicultura (291) visível. Até a v1.46.4 ele casava só (source, code) e as duas
    metades sumiam juntas — invisível, porque hoje os códigos das duas tabelas são
    disjuntos e o caso nunca chegou a acontecer.

    Uma linha do gate SEM tabela é CORINGA (esconde as duas metades). É o comportamento
    anterior preservado: `sidra_tabela` é opcional numa entrada de PEVS, e uma tag ausente
    tem de continuar escondendo tudo — jamais nada.

    ⚠ Por que o subselect renomeia a coluna. Dentro do NOT EXISTS, um `sidra_tabela` sem
    qualificação resolve para o escopo INTERNO: `v.sidra_tabela = sidra_tabela` vira uma
    tautologia que esconde as duas metades de novo, com aparência de correto. Medido contra
    o BigQuery em 2026-08-30 — a forma ingênua fez a metade 291 desaparecer junto. Ao expor
    a coluna do gate como `_vis_sidra_tabela`, o nome `sidra_tabela` deixa de existir no
    escopo interno e só pode resolver para o Gold, que é o que se quer comparar. Não troque
    isto por uma comparação "mais simples".

    Args:
      source_literal — the short source token of THIS model's Gold table
                       (pevs | pam | ppm | comex | comtrade), matched against
                       dim_produto_visibility.source.
      code_column    — the product/NCM/HS code column in this model.
-#}
{% macro hidden_code_predicate(source_literal, code_column) -%}
    not exists (
        select 1 from (
            select source, code, sidra_tabela as _vis_sidra_tabela
            from {{ ref('dim_produto_visibility') }}
        ) v
        where v.source = '{{ source_literal }}'
          and {{ code_column }} = v.code
{%- if source_literal in bancos_multi_tabela() %}
          and (
              v._vis_sidra_tabela is null
              or v._vis_sidra_tabela = ''
              or v._vis_sidra_tabela = sidra_tabela
          )
{%- endif %}
    )
{%- endmacro %}
