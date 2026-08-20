"""Shared primitives for the seam layer.

Low-level helpers used by BOTH the cross-source analytics (``seam_cross``) and the
attribute-engineering readers (``seam_attribute_engineering``): the live-source set
and the commodity crosswalk toolkit (catalog, per-source code lookup, per-metric
yearly points). Kept in their own module so the two analytic modules depend only on
this base — never on each other or on ``seam`` — which keeps the import graph a clean
DAG (base ← {cross, attributes} ← seam) with no cycles. ``seam`` re-exports these so
``seam.produto_catalog`` / ``seam._xyear`` etc. stay available to callers + tests.

The crosswalk/catalog reads are memoized with the SAME flask-caching TTL the
gateway mart reads use (CACHE_DEFAULT_TIMEOUT) — NOT functools.lru_cache: the
crosswalk and the Gold families it joins are rebuilt by the nightly dbt run, so a
long-lived Cloud Run instance must converge to the fresh catalog within the TTL
instead of serving a stale one for its whole process lifetime.
"""

from __future__ import annotations

import logging

import pandas as pd

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache

logger = logging.getLogger(__name__)

# Banco id → the BFF source key (they already align by construction).
_LIVE_SOURCES = {"ibge_pevs", "ibge_pam", "ibge_ppm", "mdic_comex", "un_comtrade"}


@cache.memoize()
def _crosswalk_df() -> pd.DataFrame:
    # F7 visibility gate: exclude commodities a researcher marked "indisponível" so the
    # cross-source picker AGREES with the (gated) per-banco pickers. Same single source of
    # truth as the dbt marts + gateway readers — dim_produto_visibility — never re-derived
    # in Python. gold_produto_agrupamento.source is already the short token (pevs/comex/
    # comtrade), matching the view. A no-op today (nothing hidden); the admin/orphan readers
    # are intentionally NOT gated (they must still see hidden-but-active rows).
    s = get_settings()
    fqn = sqlbuild.table_ref(s, "bq_gold_dataset", "gold_produto_agrupamento")
    vis = sqlbuild.table_ref(s, "bq_gold_dataset", "dim_produto_visibility")
    sql = (
        f"select x.agrupamento_id, x.agrupamento_nome, x.source, x.code from `{fqn}` x "
        f"where not exists (select 1 from `{vis}` v "
        f"where v.source = x.source and x.code = v.code)"
    )
    return gateway.run_query(sql, [])


@cache.memoize()
def produto_catalog() -> dict:
    """agrupamento_id -> {id, name, pevs[], comex[], comtrade[]} from the crosswalk.

    A crosswalk row whose agrupamento_id is NULL (a catalog entry saved without an
    agrupamento) is SKIPPED: it has no cross-source identity to key on, and a NaN
    id would become a float dict key that 500s the WHOLE /api/catalog response —
    the JSON provider's sort_keys can't order float against str keys, so one
    malformed row would take down every cross-source view. Skipping keeps the
    endpoint resilient; the row is logged so the bad catalog entry stays visible.
    """
    cat: dict = {}
    skipped: list[str] = []
    for r in _crosswalk_df().itertuples():
        if pd.isna(r.agrupamento_id):
            skipped.append(f"{r.source}:{r.code}")
            continue
        # Buckets are derived from sqlbuild.GOLD_CODE_SOURCES, never hand-listed: this
        # line used to be `c[r.source].append(...)` over a literal pevs/comex/comtrade
        # dict, so the day a new source entered the crosswalk it would KeyError and take
        # down every cross-source view. Deriving them means adding a banco to the bridge
        # can no longer break this, and every agrupamento carries an (empty) list for
        # every source, so callers can index without guarding.
        c = cat.setdefault(
            r.agrupamento_id,
            {"id": r.agrupamento_id, "name": r.agrupamento_nome}
            | {src: [] for src in sqlbuild.GOLD_CODE_SOURCES},
        )
        c.setdefault(r.source, []).append(str(r.code))
    if skipped:
        logger.warning(
            "produto_catalog: skipped %d crosswalk row(s) with NULL agrupamento_id "
            "(catalog entry saved without an agrupamento): %s",
            len(skipped),
            ", ".join(sorted(skipped)),
        )
    return cat


def _codes(agrupamento_id: str | None, source: str) -> tuple:
    """The agrupamento's codes for ONE source — the reason adding a banco to the bridge
    is safe: every cross-source view names the source it wants (the export coefficient
    asks 'pevs', market share asks 'comex'/'comtrade'), so nothing ever sums across
    production sources implicitly. ``.get`` rather than ``[]``: an unknown source
    returns "no codes" instead of 500-ing the view."""
    c = produto_catalog().get(agrupamento_id) if agrupamento_id else None
    return tuple(c.get(source, ())) if c else ()


def _xyear(metric: str, codes: tuple, uf_codes: tuple = ()) -> dict:
    """{year: raw value} from the gateway cross reader for a metric, scoped to codes.

    ``uf_codes`` optionally narrows to origin UFs (cross-source per-UF scoping); it
    only affects COMEX metrics — the gateway drops it for COMTRADE (no UF column)."""
    df = gateway.fetch_cross_series(metric, codes=codes, uf_codes=uf_codes)
    return {int(r.reference_year): float(r.value or 0) for r in df.itertuples()}
