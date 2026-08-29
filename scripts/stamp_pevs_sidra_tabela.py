"""Carimba `sidra_tabela` nas entradas PEVS do catálogo de curadoria.

O PEVS virou um banco de DUAS tabelas SIDRA em 2026-08-29 (extração vegetal t289 +
silvicultura t291), mas toda entrada do catálogo é anterior à distinção e está sem tag.
Enquanto ficarem sem tag, o resolver de ingestão dirigida pelo catálogo não consegue
separar as metades: pedir à t289 os códigos de silvicultura devolve uma fatia vazia que o
pipeline reporta como no-op limpo — o pior tipo de errado (ver o docstring de
`ibge/silvicultura_pipeline._product_codes`).

Ensaio por padrão; `APPLY=1` para gravar. A tabela de cada código é DERIVADA de
`SILVICULTURA_PRODUCT_CODES`, nunca redigitada aqui — uma segunda lista dos mesmos
códigos é exatamente como as duas divergem.
"""

from __future__ import annotations

import os
import sys

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.gcp.clients import resolve_bq_client
from embrapa_dashboard.serving import curation

DRY = os.environ.get("APPLY") != "1"
s = get_settings()
bq = resolve_bq_client(s)

SILVICULTURA = set(s.silvicultura_product_codes_list)
LOG = f"{s.gcp_project_id}.{s.bq_research_inputs_dataset}.{s.bq_produto_catalog_log_table}"

linhas = list(
    bq.query(
        f"""
        select codigo_produto, agrupamento, agrupamento_id, sidra_tabela from (
          select *, row_number() over (
            partition by codigo_produto, banco order by edited_at desc, change_id desc
          ) rn from `{LOG}` where banco = 'pevs'
        ) where rn = 1 and active
        order by codigo_produto
        """
    ).result()
)

plano = []
for r in linhas:
    alvo = s.silvicultura_table_id if r.codigo_produto in SILVICULTURA else s.ibge_table_id
    if r.sidra_tabela == alvo:
        continue  # já carimbado — idempotente
    plano.append((r.codigo_produto, r.agrupamento, r.agrupamento_id, alvo))

print(f"entradas pevs ativas: {len(linhas)} · a carimbar: {len(plano)}")
for cod, _nome, gid, alvo in plano:
    metade = "silvicultura" if alvo == s.silvicultura_table_id else "extração"
    print(f"  {cod} → t{alvo} ({metade:12}) · {gid}")

if not plano:
    print("\nnada a fazer.")
    sys.exit(0)
if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

from embrapa_dashboard.webapi.app import app  # noqa: E402

HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:igorlopesc@gmail.com"}
ok = err = 0
# No contexto do app: os escritores invalidam caches ligados a ele.
with app.app_context():
    for cod, nome, gid, alvo in plano:
        try:
            # agrupamento é OBRIGATÓRIO em toda escrita (não é preserve-on-omit); reenviar
            # o nome guardado. Os demais campos do pesquisador preservam-se por omissão.
            curation.record_produto_catalog(
                cod,
                "pevs",
                HEADERS,
                agrupamento=nome,
                agrupamento_id=gid,
                sidra_tabela=alvo,
                settings=s,
                client=bq,
                invalidate_cache=False,
            )
            ok += 1
        except Exception as exc:
            err += 1
            print(f"  ✗ {cod}: {str(exc)[:120]}")
print(f"\ngravados: {ok} · falhas: {err}")
