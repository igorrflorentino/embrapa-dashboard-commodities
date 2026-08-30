{#-
  Os bancos que unem DUAS tabelas SIDRA sob um token só — pelo TOKEN CURTO, que é o
  vocabulário do gate de visibilidade e das dims (pevs | pam | ppm | comex | comtrade).

  PEVS: extração t289 × silvicultura t291. PPM: rebanho 3939 × produção animal 74.
  Nos demais a coluna `tabela` não existe no Gold, então nenhum predicado pode
  referenciá-la — é isto que esta lista decide.

  Espelha `serving.curation._BANCOS_MULTI_TABELA` do lado Python, e
  `test_bancos_multi_tabela_macro_matches_python` guarda os dois em sincronia. Uma lista
  que muda de um lado e não do outro é a forma exata do defeito que este projeto já teve
  (ver `chave_produto`, que documenta a mesma armadilha).
-#}
{% macro bancos_multi_tabela() %}
    {{ return(['pevs', 'ppm']) }}
{% endmacro %}
