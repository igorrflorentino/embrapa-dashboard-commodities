{#-
  A TABELA de uma linha do log de curadoria, com o padrão do banco quando ela é nula.

  Os logs em `research_inputs` são APPEND-ONLY e guardam linhas escritas antes de a tabela
  existir como conceito para aquele banco. Medido em 2026-08-30: comex (303), comtrade (519)
  e pam (29) têm a coluna nula em TODAS as linhas — nunca houve outro valor possível para
  elas, porque cada um desses bancos tem uma tabela só.

  Esta macro NÃO reescreve o log; ela completa a leitura na fronteira. É o único ponto do
  projeto onde a ausência é tratada, e depois dela o trio `(banco, tabela, código)` é
  não-nulo em todas as camadas — que é o ponto: sem isto, o Gold do comex (que carrega
  `tabela = 'comex_ncm'`) não casaria com um catálogo nulo e TODO produto comex perderia
  o seu agrupamento.

  Bancos multi-tabela (pevs, ppm) NÃO têm padrão, de propósito: adivinhar a metade seria
  inventar dado. Medido em 2026-08-30: nenhuma linha viva deles tem a tabela nula (as duas
  únicas são do código de teste 9999999, e a vigente é um tombstone). O `not_null` sobre a
  coluna nas dims transforma isso num erro de build, caso deixe de ser verdade.

  Args:
    tabela_col — a coluna de tabela no log (`sidra_tabela` até a migração, `tabela` depois).
    banco_col  — a coluna de banco/source do log.
-#}
{% macro tabela_com_padrao(tabela_col='tabela', banco_col='banco') -%}
    coalesce(
        {{ tabela_col }},
        case {{ banco_col }}
            when 'pam'         then '{{ var("pam_table_id") }}'
            when 'ibge_pam'    then '{{ var("pam_table_id") }}'
            when 'comex'       then '{{ var("comex_table_id") }}'
            when 'mdic_comex'  then '{{ var("comex_table_id") }}'
            when 'comtrade'    then '{{ var("comtrade_table_id") }}'
            when 'un_comtrade' then '{{ var("comtrade_table_id") }}'
        end
    )
{%- endmacro %}
