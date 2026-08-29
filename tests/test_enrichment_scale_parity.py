"""The industrialization scale is declared twice — once per language — and nothing tied
the two together.

``webapi.seam_attribute_engineering.CUR_LEVELS`` orders the value-added analysis; the
frontend's ``window.ENRICH_LEVELS`` populates the editor and the filter menu. They are
one vocabulary written in two files, which is precisely how the pair drifts: add a level
in the UI and the API rejects it (400 from ``_ALLOWED_NIVEIS``); add one in Python and no
researcher can ever select it. Neither failure is loud — the first looks like a broken
save, the second like a level nobody uses.

Ordering is compared too, not just membership: ``CUR_LEVELS`` is ordered least→most
processed and that position IS the ordinal the gradient and the "prêmio de processamento"
read. A reordered frontend list would keep every id and still redraw the analysis wrong.

The third copy, ``routes._ALLOWED_NIVEIS``, needs no test: it is *derived* from
``CUR_LEVELS`` rather than restated, which is the stronger form of this guarantee.
"""

from __future__ import annotations

import re
from pathlib import Path

from embrapa_dashboard.webapi.seam_attribute_engineering import CUR_LEVELS

_ENRICHMENT_JS = Path(__file__).resolve().parents[1] / "frontend/src/data/enrichment.js"


def _frontend_level_ids() -> list[str]:
    """The ids inside the ENRICH_LEVELS literal, in declaration order.

    Scoped to that one array: the file also declares MARKETS, whose entries carry `id:`
    too, and a naive file-wide scan silently absorbs them (it reported a phantom ninth
    level, `consumo`, on 2026-08-29)."""
    src = _ENRICHMENT_JS.read_text(encoding="utf-8")
    start = src.index("window.ENRICH_LEVELS = [")
    end = src.index("];", start)
    return re.findall(r"\bid:\s*'([^']+)'", src[start:end])


def test_frontend_and_backend_declare_the_same_scale_in_the_same_order() -> None:
    assert _frontend_level_ids() == list(CUR_LEVELS)


def test_the_scope_guard_actually_excludes_the_neighbouring_registry() -> None:
    """Guards the extraction above, not the product: if the ENRICH_LEVELS literal were
    read file-wide, MARKETS ids would leak in and the parity test would fail for a reason
    that has nothing to do with the scale."""
    src = _ENRICHMENT_JS.read_text(encoding="utf-8")
    todos = re.findall(r"\bid:\s*'([^']+)'", src)
    assert len(todos) > len(CUR_LEVELS), "outras listas com `id:` sumiram — reveja o escopo"
    assert set(_frontend_level_ids()) < set(todos)
