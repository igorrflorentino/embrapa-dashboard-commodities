"""One-off: reorganize the generic `madeira` agrupamento into four with real affinity.

Run from the repo root:

    uv run python scripts/reorganize_madeira_agrupamento.py           # dry run (default)
    APPLY=1 uv run python scripts/reorganize_madeira_agrupamento.py   # write

Writes to the PRODUCTION curation log (`research_inputs.produto_catalog_log`), which is
append-only: every edit is a new row and latest-wins, so this is auditable and reversible
by re-recording the previous values. Nothing is deleted. Afterwards run a dbt build so
`gold_produto_agrupamento` picks the new mapping up.

`madeira` held 136 codes across comex/comtrade/pevs — measured, they fall into FOUR HS4
headings that the customs nomenclature itself keeps apart (verified against
gold_comex_flows descriptions, not from memory):

  4401  lenha, estilhas, partículas, resíduos     → `lenha`
  4402  carvão vegetal                            → `carvao_vegetal`
  4403  madeira em bruto / em tora                → `madeira_em_tora`
  4407  madeira serrada (processada)              → `madeira_serrada`

Extraction and planted halves share each agrupamento by design (project lead, 2026-08-29):
`origem` separates them in the filter menu, so the catalog does not have to.

This also lands the three silviculture codes (3455/3456/3457), which shipped in v1.34.0
with no agrupamento at all, and dissolves the degenerate one-member groups `3433`/`3434`.
"""

import os
import sys

from google.cloud import bigquery

from embrapa_dashboard.config import Settings

DRY = os.environ.get("APPLY") != "1"

DESTINO = {
    "4401": ("lenha", "Lenha e resíduos lenhosos"),
    "4402": ("carvao_vegetal", "Carvão vegetal"),
    "4403": ("madeira_em_tora", "Madeira em tora"),
    "4407": ("madeira_serrada", "Madeira serrada"),
}
# PEVS codes: the extraction/silviculture pairs, placed by what they ARE.
PEVS = {
    "3433": ("carvao_vegetal", "Carvão vegetal"),  # extrativa
    "3455": ("carvao_vegetal", "Carvão vegetal"),  # silvicultura
    "3434": ("lenha", "Lenha e resíduos lenhosos"),  # extrativa
    "3456": ("lenha", "Lenha e resíduos lenhosos"),  # silvicultura
    "3435": ("madeira_em_tora", "Madeira em tora"),  # extrativa
    "3457": ("madeira_em_tora", "Madeira em tora"),  # silvicultura
    "3450": ("madeira_em_tora", "Madeira em tora"),  # pinheiro brasileiro, em tora
}

s = Settings()
bq = bigquery.Client(project=s.gcp_project_id, location=s.bq_location)

atual = list(
    bq.query(
        """
        select source, code, agrupamento_id
        from `embrapa-dashboard-commodities.gold.gold_produto_agrupamento`
        where agrupamento_id in ('madeira', '3433', '3434')
        order by source, code
        """
    ).result()
)

plano = []
for r in atual:
    # PEVS codes are placed one by one (they are few and each names a product); the
    # trade codes are placed by their HS4 heading, which is the nomenclature's own split.
    alvo = PEVS.get(r.code) if r.source == "pevs" else DESTINO.get(r.code[:4])
    if alvo is None:
        plano.append((r.source, r.code, r.agrupamento_id, None, "SEM DESTINO"))
        continue
    if alvo[0] != r.agrupamento_id:
        plano.append((r.source, r.code, r.agrupamento_id, alvo, "realocar"))

# os tres da silvicultura ainda nao estao no catalogo
for cod in ("3455", "3456", "3457"):
    plano.append(("pevs", cod, None, PEVS[cod], "registrar"))

from collections import Counter  # noqa: E402

print(f"linhas hoje em madeira/3433/3434: {len(atual)}")
print(f"acoes: {len(plano)}\n")
for acao, n in Counter(p[4] for p in plano).items():
    print(f"  {acao}: {n}")
print()
destino_cnt = Counter(p[3][0] for p in plano if p[3])
for ag, n in sorted(destino_cnt.items(), key=lambda x: -x[1]):
    print(f"  → {ag}: {n} códigos")
orfaos = [p for p in plano if p[4] == "SEM DESTINO"]
if orfaos:
    print(f"\n⚠ SEM DESTINO ({len(orfaos)}):")
    for o in orfaos[:10]:
        print("   ", o[0], o[1], o[2])

if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

from embrapa_dashboard.serving import curation  # noqa: E402

HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:igorlopesc@gmail.com"}
ok = err = 0
for source, code, _antes, alvo, _acao in plano:
    try:
        curation.record_produto_catalog(
            code,
            source,
            HEADERS,
            agrupamento=alvo[1],
            agrupamento_id=alvo[0],
            settings=s,
            client=bq,
            invalidate_cache=False,
        )
        ok += 1
    except Exception as exc:
        err += 1
        print(f"  ✗ {source}/{code}: {str(exc)[:110]}")
print(f"\ngravados: {ok} · falhas: {err}")
