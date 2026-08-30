"""The idempotency read-back: the query that makes a RETRIED write echo instead of duplicate.

Every writer in `serving/` accepts an optional ``change_id``. When the same one arrives
twice — a client retry, a flaky network — the writer must return the row it ALREADY stored,
not insert a second one. The function that fetches that row is the whole mechanism.

The 2026-08-30 audit found those functions executing in **zero** tests: every test that
reaches them replaces them with a `monkeypatch` stub, which is the right call for the tests
*about the dedup flow* but leaves the bodies — the SQL — unexercised. A wrong column name
in one of them would pass the entire suite and fail in production, on the retry path, which
is exactly where nobody is watching.

These tests drive the real bodies against a fake BigQuery client. The anchor is external to
the code under test: what the function RETURNS, and the query it actually emitted — never
its source text.
"""

from __future__ import annotations

from unittest import mock

import pytest


class _LinhaEspia:
    """Uma linha de resultado que ANOTA quais colunas o código leu dela.

    Sem isto o teste não consegue ver o defeito que ele existe para pegar: uma linha falsa
    com as chaves certas responde bem mesmo que o SELECT peça outro nome de coluna, e um
    `select industrializacao_level` (typo) passa verde. Anotando as leituras, dá para
    confrontá-las com a lista de colunas do SELECT que a própria função emitiu — o
    acoplamento real entre a consulta e o mapeamento logo abaixo dela."""

    def __init__(self, valores: dict):
        self._valores = valores
        self.lidas: set[str] = set()

    def __getitem__(self, chave):
        self.lidas.add(chave)
        return self._valores[chave]


def _bq(rows):
    """A fake BigQuery client whose `.query(...).result()` yields ``rows``."""
    client = mock.MagicMock()
    client.query.return_value.result.return_value = rows
    return client


def _colunas_do_select(sql: str) -> set[str]:
    """Os nomes de coluna entre `select` e `from`."""
    corpo = sql.lower().split("select", 1)[1].split("from", 1)[0]
    return {c.strip() for c in corpo.split(",") if c.strip()}


def _sql_emitido(client) -> str:
    return client.query.call_args.args[0]


def _params_emitidos(client):
    cfg = client.query.call_args.kwargs["job_config"]
    return {p.name: p.value for p in cfg.query_parameters}


# (módulo, função, linha guardada, o que a função deve devolver dela)
def _casos():
    from embrapa_dashboard.serving import agrupamentos, attribute_engineering, curation

    return [
        pytest.param(
            curation._row_for_change_id,
            {
                "codigo_produto": "4403",
                "banco": "comex",
                "agrupamento": "Madeira",
                "descricao_produto": None,
                "ciclo_de_vida": None,
                "agrupamento_id": "madeira",
                "active": True,
                "edited_by": "a@b.c",
                "tabela": None,
                "ingestao": "ativa",
                "visibilidade": "visivel",
            },
            {"codigo_produto": "4403", "banco": "comex"},
            id="curation",
        ),
        pytest.param(
            agrupamentos._group_row_for_change_id,
            {"group_id": "madeira", "group_name": "Madeira", "active": True, "edited_by": "a@b.c"},
            {"group_id": "madeira", "group_name": "Madeira"},
            id="agrupamentos",
        ),
        pytest.param(
            attribute_engineering._code_row_for_change_id,
            {
                "source": "comex",
                "code": "4403",
                "industrialization_level": "bruto",
                "note": None,
                "edited_by": "a@b.c",
            },
            {"source": "comex", "code": "4403", "industrialization_level": "bruto"},
            id="attr_code",
        ),
        pytest.param(
            attribute_engineering._flow_market_row_for_change_id,
            {"customs_code": "C00", "flow_code": "X", "market": "externo", "edited_by": "a@b.c"},
            {"customs_code": "C00", "flow_code": "X", "market": "externo"},
            id="attr_flow_market",
        ),
    ]


@pytest.mark.parametrize("fn, guardada, esperado", _casos())
def test_echoes_the_stored_row_marked_deduped(fn, guardada, esperado) -> None:
    """Achou a linha → devolve os valores GUARDADOS, marcados como dedup.

    "Marcados" importa: sem `deduped=True` o chamador não distingue uma escrita nova de um
    replay, e a resposta HTTP mentiria sobre ter gravado."""
    linha = _LinhaEspia(guardada)
    client = _bq([linha])
    row = fn(client, "proj.ds.tbl", "chg-1")
    assert row is not None
    for chave, valor in esperado.items():
        assert row[chave] == valor, f"{chave} não veio da linha guardada"
    assert row["change_id"] == "chg-1"
    assert row["deduped"] is True

    # E o acoplamento que dá sentido ao resto: toda coluna que o código LEU da linha tem de
    # estar no SELECT que ele mesmo emitiu. É isto que pega um nome de coluna errado — o
    # defeito que só apareceria em produção, no caminho de retry, onde ninguém está olhando.
    selecionadas = _colunas_do_select(_sql_emitido(client))
    faltando = linha.lidas - selecionadas
    assert not faltando, (
        f"lê {sorted(faltando)} da linha, mas o SELECT não pede: {sorted(selecionadas)}"
    )


@pytest.mark.parametrize("fn, guardada, esperado", _casos())
def test_returns_none_when_the_stored_row_is_gone(fn, guardada, esperado) -> None:
    """Nenhuma linha → None, e não um KeyError num `rows[0]` que não existe.

    Este é o ramo que nenhum teste cobria nas quatro funções. Ele não é hipotético: os
    chamadores tratam o None (`if stored is not None: return stored`, com um fallback logo
    abaixo), o que só faz sentido porque ele pode acontecer."""
    assert fn(_bq([]), "proj.ds.tbl", "chg-1") is None


@pytest.mark.parametrize("fn, guardada, esperado", _casos())
def test_reads_the_latest_row_for_that_change_id_by_parameter(fn, guardada, esperado) -> None:
    """A forma da consulta, que é o que faz o eco estar certo:

    * o ``change_id`` viaja como PARÂMETRO, não interpolado — é entrada de cliente;
    * a tabela consultada é a que o chamador passou, não uma fixa no módulo;
    * ``order by edited_at desc limit 1`` — o registro é somente-adição, então "a linha
      daquele change_id" é a ÚLTIMA; sem a ordenação o eco poderia devolver uma versão
      anterior da mesma linha.
    """
    client = _bq([guardada])
    fn(client, "proj.ds.minha_tabela", "chg-xyz")
    sql = " ".join(_sql_emitido(client).lower().split())
    assert "@change_id" in sql, "o change_id foi interpolado no SQL em vez de parametrizado"
    assert "chg-xyz" not in sql
    assert _params_emitidos(client) == {"change_id": "chg-xyz"}
    assert "proj.ds.minha_tabela" in sql, "consultou uma tabela diferente da pedida"
    assert "order by edited_at desc" in sql, "sem ordenação, o eco pode devolver uma versão velha"
    assert "limit 1" in sql
