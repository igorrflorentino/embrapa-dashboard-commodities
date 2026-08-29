"""One-off: register the agrupamentos that catalog entries point at but that never existed.

Run from the repo root:

    uv run python scripts/register_missing_agrupamentos.py           # dry run (default)
    APPLY=1 uv run python scripts/register_missing_agrupamentos.py   # write

An agrupamento is TWO things: a row in the groups registry, and the `agrupamento_id` the
catalog entries carry. v1.34.4 reorganized the wood products by writing the second WITHOUT
the first, so 37 products ended up pointing at `lenha` and `carvao_vegetal`, which no
group row backed. The cadastro screen listed them, correctly, under "Sem agrupamento
REGISTRADO" — the word `registrado` is the whole distinction, and it was doing its job.

`abacaxi` (1 entry) has the same shape and predates that change.

The group id is the SLUG OF ITS NAME (`curation._slug`), so the name chosen here is not
cosmetic — it is what decides whether the new row matches the id the entries already
carry. "Lenha e resíduos lenhosos" slugs to `lenha_e_residuos_lenhosos` and would NOT
match; "Lenha" does. The 26 lenha entries are therefore also re-recorded so their stored
NAME agrees with the registry, which is the invariant a rename normally maintains.
"""

import os
import sys

from google.cloud import bigquery

from embrapa_dashboard.config import Settings

DRY = os.environ.get("APPLY") != "1"

# nome do grupo → o id que ele gera (e que as entradas já apontam)
GRUPOS = ["Lenha", "Carvão vegetal", "Abacaxi"]
# entradas cujo NOME guardado diverge do nome do grupo registrado
RENOMEAR_ENTRADAS = {"lenha": "Lenha"}

s = Settings()
bq = bigquery.Client(project=s.gcp_project_id, location=s.bq_location)

from embrapa_dashboard.serving import curation  # noqa: E402

alvo_ids = {curation._slug(n): n for n in GRUPOS}
print("grupos a registrar:")
for gid, nome in alvo_ids.items():
    print(f"  {gid:22s} nome={nome!r}")

if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

from embrapa_dashboard.serving import agrupamentos  # noqa: E402
from embrapa_dashboard.webapi.app import app  # noqa: E402

HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:igorlopesc@gmail.com"}
ok = err = 0
# No contexto do app: os escritores invalidam caches ligados a ele (a mesma armadilha que
# custou 3 escritas silenciosas em scripts/reorganize_madeira_agrupamento.py).
with app.app_context():
    for gid, nome in alvo_ids.items():
        try:
            agrupamentos.record_group(nome, HEADERS, settings=s, client=bq)
            ok += 1
            print(f"  ✓ grupo {gid}")
        except Exception as exc:
            err += 1
            print(f"  ✗ grupo {gid}: {str(exc)[:110]}")

    # Alinhar o NOME guardado nas entradas ao nome do grupo recém-registrado.
    for gid, nome in RENOMEAR_ENTRADAS.items():
        linhas = list(
            bq.query(
                f"""
                select codigo_produto, banco from (
                    select codigo_produto, banco, agrupamento_id,
                           row_number() over (
                               partition by codigo_produto, banco order by edited_at desc
                           ) rn
                    from `{s.gcp_project_id}.research_inputs.produto_catalog_log`
                )
                where rn = 1 and agrupamento_id = '{gid}'
                """
            ).result()
        )
        for r in linhas:
            try:
                curation.record_produto_catalog(
                    r.codigo_produto,
                    r.banco,
                    HEADERS,
                    agrupamento=nome,
                    agrupamento_id=gid,
                    settings=s,
                    client=bq,
                    invalidate_cache=False,
                )
                ok += 1
            except Exception as exc:
                err += 1
                print(f"  ✗ {r.banco}/{r.codigo_produto}: {str(exc)[:110]}")
print(f"\ngravados: {ok} · falhas: {err}")
