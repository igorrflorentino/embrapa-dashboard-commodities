"""Remove as 4 entradas HS-4 (`4401`/`4402`) do catálogo de COMEX e COMTRADE.

Foram criadas em 2026-08-29 pela reorganização dos agrupamentos de madeira, que adicionou
o CABEÇALHO HS-4 aos grupos `lenha` e `carvao_vegetal` sem verificar que os códigos
específicos já estavam lá. O COMEX indexa por NCM-8 e o COMTRADE por HS-6, e o catálogo
casa pelo código EXATO — então um código de 4 dígitos nunca encontra dado nenhum.

Não se perde cobertura: os 29 códigos longos correspondentes já estão cadastrados e nos
mesmos agrupamentos (comex 12+4, comtrade 10+3). A remoção é um tombstone append-only
(`active=false`), reversível por outra escrita, e não gera órfão — não há dado em Gold
para essas entradas ficarem apontando.

Ensaio por padrão; `APPLY=1` para gravar.
"""

from __future__ import annotations

import os
import sys

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.gcp.clients import resolve_bq_client
from embrapa_dashboard.serving import curation
from embrapa_dashboard.serving import sql as sqlbuild

DRY = os.environ.get("APPLY") != "1"
ALVOS = [("comex", "4401"), ("comex", "4402"), ("comtrade", "4401"), ("comtrade", "4402")]

s = get_settings()
bq = resolve_bq_client(s)
LOG = sqlbuild.table_ref(s, "bq_research_inputs_dataset", s.bq_produto_catalog_log_table)

ativos = {
    (r.banco, r.codigo_produto)
    for r in bq.query(
        f"""
        select banco, codigo_produto from (
          select *, row_number() over (
            partition by codigo_produto, banco order by edited_at desc, change_id desc
          ) rn from `{LOG}`
        ) where rn = 1 and active
        """
    ).result()
}
plano = [a for a in ALVOS if a in ativos]

print(f"alvos: {len(ALVOS)} · ainda ativos (a remover): {len(plano)}")
for banco, cod in plano:
    print(f"  {banco:9} {cod}")
if not plano:
    print("\nnada a fazer (já removidos).")
    sys.exit(0)
if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

from embrapa_dashboard.webapi.app import app  # noqa: E402

HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:igorlopesc@gmail.com"}
ok = err = 0
with app.app_context():
    for banco, cod in plano:
        try:
            curation.remove_produto_catalog(cod, banco, HEADERS, settings=s, client=bq)
            ok += 1
        except Exception as exc:
            err += 1
            print(f"  ✗ {banco}/{cod}: {str(exc)[:120]}")
print(f"\nremovidos: {ok} · falhas: {err}")
