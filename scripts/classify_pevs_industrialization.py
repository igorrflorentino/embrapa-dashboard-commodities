"""One-off: classify the five unclassified PEVS codes on the industrialization axis.

Run from the repo root:

    uv run python scripts/classify_pevs_industrialization.py           # dry run (default)
    APPLY=1 uv run python scripts/classify_pevs_industrialization.py   # write

PEVS sat at 50% coverage (5 of 10 codes), which mattered the moment the axis became a
FILTER: a researcher slicing by level would find half the banco under "sem classificação".
Three of the five gaps were created by v1.34.0, which added the silviculture products
without classifying them.

Each level below is inherited from an analogue INSIDE PEVS, not from the trade codes:

  3455 Carvão vegetal    (silvicultura) → manufaturado_industrial   (twin 3433, extrativa)
  3456 Lenha             (silvicultura) → commodity_acondicionada   (twin 3434)
  3457 Madeira em tora   (silvicultura) → commodity_acondicionada   (twin 3435)

    The processing state of charcoal does not depend on whether the wood was native or
    planted — same product, and `origem` already records the provenance.

  3403 Açaí (fruto)      (extrativa)   → commodity_pura            (sibling 3405)
  3404 Castanha-de-caju  (extrativa)   → commodity_pura            (sibling 3405)

    Deliberately NOT inherited from trade: comex 20079921 (açaí) is HS 2007 — purées and
    pastes — and comtrade 080131/32 (caju) are shelled/packed nuts. Those are downstream
    of what PEVS measures. Inside PEVS the comparable product is castanha-do-pará, the raw
    extracted nut, classified `commodity_pura`.

Writes to the PRODUCTION attribute log, which is append-only with latest-wins: auditable
and reversible by re-recording, nothing is deleted. The researcher can override any of
these in Engenharia de Atributos → Nível de industrialização.
"""

import os
import sys

from google.cloud import bigquery

from embrapa_dashboard.config import Settings

DRY = os.environ.get("APPLY") != "1"

NIVEIS = {
    "3455": ("manufaturado_industrial", "herda do gêmeo extrativo 3433 (carvão vegetal)"),
    "3456": ("commodity_acondicionada", "herda do gêmeo extrativo 3434 (lenha)"),
    "3457": ("commodity_acondicionada", "herda do gêmeo extrativo 3435 (madeira em tora)"),
    "3403": ("commodity_pura", "fruto extraído sem modificação, como 3405 castanha-do-pará"),
    "3404": ("commodity_pura", "castanha extraída, ainda não descascada, como 3405"),
}

s = Settings()
bq = bigquery.Client(project=s.gcp_project_id, location=s.bq_location)

atual = {
    r.code: r.industrialization_level
    for r in bq.query(
        """
        select code, industrialization_level
        from `embrapa-dashboard-commodities.serving.dim_code_industrialization_scd2`
        where source = 'ibge_pevs' and is_current
        """
    ).result()
}

plano = [(c, n, por) for c, (n, por) in NIVEIS.items() if atual.get(c) != n]
print(f"códigos PEVS já classificados: {len(atual)}")
print(f"a classificar: {len(plano)}\n")
for code, nivel, por in plano:
    print(f"  {code} → {nivel:26s} {por}")

if DRY:
    print("\n(ensaio — nada escrito; APPLY=1 para executar)")
    sys.exit(0)

from embrapa_dashboard.serving import attribute_engineering  # noqa: E402
from embrapa_dashboard.webapi.app import app  # noqa: E402

HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:igorlopesc@gmail.com"}
ok = err = 0
# Inside the app context: the writer invalidates a flask-caching entry, which is bound to
# the app (see scripts/reorganize_madeira_agrupamento.py — the same trap cost 3 silent
# write failures there).
with app.app_context():
    for code, nivel, por in plano:
        try:
            attribute_engineering.record_code_industrialization(
                "ibge_pevs", code, nivel, HEADERS, note=por, settings=s, client=bq
            )
            ok += 1
        except Exception as exc:
            err += 1
            print(f"  ✗ {code}: {str(exc)[:110]}")
print(f"\ngravados: {ok} · falhas: {err}")
