"""Migração única: completar `sidra_tabela` no histórico do catálogo de curadoria.

A chave de um produto passa a ser **(banco, tabela, código)**. O log é append-only, e as
linhas escritas ANTES de a coluna `sidra_tabela` existir a têm NULL. Promover a coluna para
dentro da chave sem tratar isso transformaria **supersessão em coexistência**: a versão
antiga (NULL) deixaria de ser "estado anterior da mesma entrada" e viraria um produto
próprio. Medido antes: a chave de 3 colunas dava 258 entradas ativas onde a de 2 dá 234 —
24 fantasmas, todos de `pevs` (10) e `ppm` (14), os dois bancos multi-tabela.

Por que UPDATE e não uma linha nova: preencher uma coluna que era NULL **porque não existia
quando a linha foi escrita** completa o histórico, não reescreve decisão nenhuma. Nenhum
valor decidido por um pesquisador muda — o destino de cada linha é o valor que a PRÓPRIA
entrada já carrega hoje. Um tombstone sintético, a alternativa, deixaria no log uma remoção
que ninguém fez.

Bancos de uma tabela só (comex, comtrade, pam) não são tocados: para eles o componente de
tabela não carrega informação e a chave nova é equivalente à antiga.

Faça o snapshot antes (`make backup-gold`) — este script escreve no único dataset que não
se recalcula. Ensaio por padrão; `APPLY=1` para executar.
"""

from __future__ import annotations

import os
import sys

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.gcp.clients import resolve_bq_client
from embrapa_dashboard.serving import sql as sqlbuild

DRY = os.environ.get("APPLY") != "1"
s = get_settings()
bq = resolve_bq_client(s)
LOG = sqlbuild.table_ref(s, "bq_research_inputs_dataset", s.bq_produto_catalog_log_table)

# O alvo de cada entrada: a linha mais recente que TEM tag (o `is null` primeiro no order
# by empurra as sem tag para o fim, então rn=1 é sempre uma linha com valor, se houver).
ALVOS = f"""
    select codigo_produto, banco, sidra_tabela
    from (
      select codigo_produto, banco, sidra_tabela,
             row_number() over (partition by codigo_produto, banco
                                order by (sidra_tabela is null), edited_at desc, change_id desc) rn
      from `{LOG}`
    )
    where rn = 1 and sidra_tabela is not null
"""


def _conta(sql: str) -> int:
    return next(iter(bq.query(sql).result())).n


antes_2 = _conta(f"""
    select count(*) n from (
      select row_number() over (partition by codigo_produto, banco
                                order by edited_at desc, change_id desc) rn, active
      from `{LOG}`) where rn = 1 and active
""")
antes_3 = _conta(f"""
    select count(*) n from (
      select row_number() over (partition by codigo_produto, banco, ifnull(sidra_tabela,'@')
                                order by edited_at desc, change_id desc) rn, active
      from `{LOG}`) where rn = 1 and active
""")
pendentes = _conta(f"""
    select count(*) n from `{LOG}` l join ({ALVOS}) a
      using (codigo_produto, banco)
    where l.sidra_tabela is null
""")

print(f"  ativos com chave (banco, codigo)          : {antes_2}")
print(f"  ativos com chave (banco, tabela, codigo)  : {antes_3}")
print(f"  linhas historicas a completar             : {pendentes}")

if antes_2 == antes_3 and pendentes == 0:
    print("\n  nada a fazer — a migracao ja e neutra.")
    sys.exit(0)
if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

bq.query(f"""
    update `{LOG}` l
    set sidra_tabela = a.sidra_tabela
    from ({ALVOS}) a
    where l.codigo_produto = a.codigo_produto
      and l.banco = a.banco
      and l.sidra_tabela is null
""").result()

depois_3 = _conta(f"""
    select count(*) n from (
      select row_number() over (partition by codigo_produto, banco, ifnull(sidra_tabela,'@')
                                order by edited_at desc, change_id desc) rn, active
      from `{LOG}`) where rn = 1 and active
""")
print(f"\n  ativos com a chave de 3 colunas DEPOIS    : {depois_3}")
print("  ->", "MIGRACAO NEUTRA" if depois_3 == antes_2 else f"DIVERGE de {antes_2} — investigue")
