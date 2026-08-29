"""Every filter axis must reach every reader that honours it — not just the snapshot.

TWO axes shipped on 2026-08-29, one day apart, and BOTH were threaded through the snapshot
path and nowhere else:

* `origem` — the map returned identical totals for `extrativa`, `silvicultura` and no
  filter, where the correct split is 372,9 bi vs 690,6 bi (the halves differ ~6x).
* `niveis` — the same readers ignored the industrialization level completely: the snapshot
  showed 1,3 bi for commodity_pura beside a map showing the whole 1.063,5 bi.

Neither was a rounding error: each was a different dataset wearing the user's label, which
this project's "no invisible filtering" rule forbids outright. They reach the readers by
DIFFERENT mechanisms — `origem` is a column predicate passed as a kwarg, `niveis` resolves
to a code list because the level lives in an SCD2 dim and no fact carries it — so each gets
the assertion that fits its mechanism.

So these tests scan the WIRE, not the function. Each individual reader had a passing test
for its own parameter; what nobody checked was whether the call sites pass it.
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
    # _with_filter_axes folds every validated axis in; it must appear in the handler.
    corpo = antes[antes.rindex("\ndef ") :]
    assert "_with_filter_axes" in corpo, f"a rota que chama seam.{rota} nao dobra os eixos"


# Seam readers that honour a product basket — every one must narrow it by the selected
# nível, because the level is not a column any fact carries.
_BASKET_READERS = (
    "snapshot",
    "geo_yearly",
    "geo_municipio_yearly",
    "products_by_municipio",
    "flow_data",
    "partner_data",
    "products_by_uf",
    "monthly_data",
)


def _seam_function_bodies() -> dict[str, str]:
    src = _SEAM.read_text(encoding="utf-8")
    tree = ast.parse(src)
    linhas = src.split("\n")
    return {
        n.name: "\n".join(linhas[n.lineno - 1 : n.end_lineno])
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }


@pytest.mark.parametrize("fn", _BASKET_READERS)
def test_every_basket_reader_narrows_by_nivel(fn: str) -> None:
    """A reader that takes the basket raw serves the whole banco under a level's label."""
    corpo = _seam_function_bodies().get(fn)
    assert corpo, f"{fn} nao encontrada — o teste ficou obsoleto, nao o codigo"
    assert "_basket(summary)" in corpo, f"{fn} nao le mais a cesta — reveja a lista"
    assert "_apply_levels(" in corpo, f"{fn} usa a cesta CRUA, ignorando o nivel selecionado"


def test_the_level_narrowing_is_defined_once() -> None:
    """The narrowing lived inline in `snapshot` and nowhere else, which is how seven
    readers missed it. One definition, called everywhere — never a second copy."""
    src = _SEAM.read_text(encoding="utf-8")
    assert src.count("def _apply_levels(") == 1
    # The sentinel that keeps an empty resolution honest must not be re-spelled either.
    assert src.count('"__nenhum_codigo_neste_nivel__"') == 1
