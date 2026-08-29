{#-
  A identidade de um produto na curadoria: BANCO + TABELA + CÓDIGO.

  PEVS e PPM unem DUAS tabelas SIDRA sob um token de banco só (extração t289 ×
  silvicultura t291; rebanho 3939 × produção animal 74), então banco+código não distingue
  as metades. Nos bancos de uma tabela (comex, comtrade, pam) a coluna não carrega
  informação e o `ifnull` a colapsa na sentinela — para eles a chave nova é equivalente à
  antiga, o que manteve a migração neutra.

  Espelha `serving.sql.CHAVE_*` do lado Python. Os dois lados precisam concordar: o Python
  escreve e lê os logs, o dbt materializa as dims que a UI e o Gold consomem. Uma chave que
  muda de um lado e não do outro é a forma exata do defeito que este projeto já teve.
-#}
{% macro chave_produto(codigo='codigo_produto', banco='banco', tabela='sidra_tabela') %}
{{ codigo }}, {{ banco }}, ifnull({{ tabela }}, '-')
{%- endmacro %}
