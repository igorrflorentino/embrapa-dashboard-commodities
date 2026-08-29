"""Every PEVS reader call in the seam must thread `origem`, and every route must parse it.

The axis was introduced on 2026-08-29 and threaded through the snapshot path only. The
unit tests were green and the feature was broken end-to-end: asking the map for
`silvicultura` returned BOTH halves summed. Measured on 2020–2023 before the fix —
identical totals for `extrativa`, `silvicultura` and no filter at all, where the correct
split is 372,9 bi vs 690,6 bi. The two halves differ ~6x in value, so this was not a
rounding error but a different dataset wearing the user's label, which this project's
"no invisible filtering" rule forbids outright.

So these tests scan the WIRE, not the function. Each individual reader had a passing test
for its `origem` parameter; what nobody checked was whether the call sites pass it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SEAM = Path(__file__).resolve().parents[1] / "src/embrapa_dashboard/webapi/seam.py"
_ROUTES = Path(__file__).resolve().parents[1] / "src/embrapa_dashboard/webapi/routes.py"

# Readers over gold_pevs_production / serving_pevs_annual — the only tables with `origem`.
# `fetch_products_by_uf` serves BOTH PEVS production and COMEX export, told apart only by
# `table_key` — so the sweep reads the table, not just the reader name.
_TRADE_TABLE = "serving_comex_annual"

_PEVS_READERS = {
    "fetch_production_overview",
    "fetch_production_by_uf",
    "fetch_production_by_uf_yearly",
    "fetch_production_by_municipio_yearly",
    "fetch_products_by_uf",
    "fetch_products_by_municipio",
}


def _gateway_calls(path: Path) -> list[tuple[str, int, set[str], str | None]]:
    """(reader, line, kwargs, table_key) for every `gateway.fetch_*` call in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "gateway"
        ):
            kwargs = {k.arg for k in node.keywords if k.arg}
            tabela = next(
                (
                    k.value.value
                    for k in node.keywords
                    if k.arg == "table_key" and isinstance(k.value, ast.Constant)
                ),
                None,
            )
            out.append((fn.attr, node.lineno, kwargs, tabela))
    return out


def test_every_pevs_reader_call_in_the_seam_threads_origem() -> None:
    """A PEVS reader called without `origem` silently answers for both halves."""
    faltando = [
        f"{nome} (seam.py:{linha})"
        for nome, linha, kwargs, tabela in _gateway_calls(_SEAM)
        if nome in _PEVS_READERS and "origem" not in kwargs and tabela != _TRADE_TABLE
    ]
    assert not faltando, "chamadas PEVS sem origem: " + ", ".join(faltando)


def test_a_trade_call_never_carries_origem() -> None:
    """The converse. `fetch_products_by_uf` is SHARED: PEVS production and COMEX export
    differ only by `table_key`. serving_comex_annual has no `origem` column, so passing it
    there would be a BigQuery error, not a silent one — but the sweep above must not push
    anyone into 'fixing' it that way."""
    indevidas = [
        f"{nome} (seam.py:{linha})"
        for nome, linha, kwargs, tabela in _gateway_calls(_SEAM)
        if tabela == _TRADE_TABLE and "origem" in kwargs
    ]
    assert not indevidas, "origem enviada a uma tabela de comercio: " + ", ".join(indevidas)


def test_the_sweep_actually_sees_the_calls() -> None:
    """Guards the scanner, not the code: an AST walk that matched nothing would make the
    test above pass forever. Five of my own sweeps were wrong before the repo was."""
    nomes = {nome for nome, _, _, _ in _gateway_calls(_SEAM)}
    assert nomes >= _PEVS_READERS, f"o varredor perdeu leitores: {_PEVS_READERS - nomes}"


@pytest.mark.parametrize(
    "rota",
    [
        "product_uf_ranking",
        "geo_yearly",
        "geo_municipio_yearly",
        "products_by_municipio",
        "products_by_uf",
    ],
)
def test_every_route_reaching_a_pevs_seam_parses_origem(rota: str) -> None:
    """The seam can only honour what the route parsed. Each of these five builds its own
    summary, and the axis reached exactly one of them."""
    src = _ROUTES.read_text(encoding="utf-8")
    m = re.search(rf"^\s*(?:summary, err = )?.*seam\.{rota}\(", src, re.M)
    assert m, f"rota {rota} nao encontrada — o teste ficou obsoleto, nao o codigo"
    antes = src[: m.start()]
    # _with_origem folds the validated param in; it must appear in the handler above.
    corpo = antes[antes.rindex("\ndef ") :]
    assert "_with_origem" in corpo, f"a rota que chama seam.{rota} nao passa origem"
