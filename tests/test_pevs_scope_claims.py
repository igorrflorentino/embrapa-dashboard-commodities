"""What the PEVS banco SAYS it covers must match the SIDRA tables it actually reads.

INVERTED 2026-08-29. This file was written when the project ingested ONE half of the
survey (table 289, extraction from native forest) while the registries described both —
a researcher read "recursos florestais, nativos e plantados", found São Paulo empty, and
reasonably concluded the data was broken. Back then the test REQUIRED the description to
say the silviculture half was out.

Table 291 is now ingested too (PLANS/silvicultura_source.md), so the same requirement
would now be the lie. The test flips: the description must name BOTH halves and the
`origem` axis that separates them. It failing on that change was the point — a stale
claim outliving the mechanism that decided it is precisely what this file exists to
catch, and it caught it in the direction nobody plans for.

The mechanism is still the configured SIDRA tables, and both registry copies are still
pinned, since two copies agreeing proved nothing before.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BANCOS_JS = REPO / "frontend" / "src" / "ui" / "bancos.js"
SCHEMA_JS = REPO / "frontend" / "src" / "ui" / "filtersSchema.js"

# The description must name BOTH halves — the word "silvicultura" alone is not enough,
# since it also appears in the survey's NAME and did so throughout the period when the
# half was missing. What proves coverage is naming the planted forest as content.
NAMES_BOTH = ("silvicultura",)
NAMES_THE_PLANTED_HALF = ("plantada", "plantado")
# And it must point at the axis that separates them, or a reader has no way to know a
# total mixes native with planted.
NAMES_THE_AXIS = ("origem",)


def _js_about() -> str:
    m = re.search(r"id:\s*'ibge_pevs'.*?about:\s*'(.*?)',\n", BANCOS_JS.read_text("utf-8"), re.S)
    assert m, "bancos.js: PEVS `about` not found"
    return m.group(1)


def _py_banco():
    from embrapa_dashboard.webapi.registries import BANCOS

    return next(b for b in BANCOS if b.id == "ibge_pevs")


def test_both_sidra_halves_are_configured() -> None:
    """The premise of every assertion below. If either changes, they must be revisited.

    Read from the DECLARED defaults, not from an instantiated `Settings` — building one
    needs GCP credentials the CI job has no reason to hold, and a test that only runs
    where a developer happens to have a `.env` is a test that passes for the wrong reason
    (this one did, until CI said otherwise).
    """
    from embrapa_dashboard.config import Settings

    assert Settings.model_fields["ibge_table_id"].default == "289"
    assert Settings.model_fields["silvicultura_table_id"].default == "291"


@pytest.mark.parametrize("copia", ["spa", "backend"])
def test_pevs_description_names_both_halves(copia: str) -> None:
    texto = (_js_about() if copia == "spa" else _py_banco().about).lower()
    assert any(m in texto for m in NAMES_BOTH), f"{copia}: não nomeia a silvicultura"
    assert any(m in texto for m in NAMES_THE_PLANTED_HALF), (
        f"{copia}: não diz que a floresta PLANTADA está incluída — e o nome da pesquisa "
        "sozinho não prova cobertura: ele dizia 'e da Silvicultura' durante todo o período "
        "em que essa metade faltava"
    )


@pytest.mark.parametrize("copia", ["spa", "backend"])
def test_pevs_description_points_at_the_axis_that_separates_them(copia: str) -> None:
    texto = (_js_about() if copia == "spa" else _py_banco().about).lower()
    assert any(m in texto for m in NAMES_THE_AXIS), (
        f"{copia}: a descrição não menciona o eixo Origem. Sem ele o leitor não tem como "
        "saber que um total soma nativa + plantada — e a soma é 5:1 a favor da plantada"
    )


def test_the_origem_axis_is_declared_in_both_filter_schemas() -> None:
    """The axis has to EXIST as a filter, not just be named in prose."""
    from embrapa_dashboard.webapi.registries import FILTER_SCHEMAS

    dims = FILTER_SCHEMAS["ibge_pevs"]["dims"]
    assert any(d.get("id") == "origem" for d in dims), "backend: sem a dimensão origem"
    assert "id: 'origem'" in SCHEMA_JS.read_text("utf-8"), "SPA: sem a dimensão origem"


def test_the_product_filter_hint_does_not_promise_what_the_codes_do_not_cover() -> None:
    """The products hint describes the PRODUCT list, which is still extraction-only in
    its wording — the silviculture products are reached through the origem axis."""
    from embrapa_dashboard.webapi.registries import FILTER_SCHEMAS

    hints = [SCHEMA_JS.read_text("utf-8")]
    hints += [
        d["hint"]
        for d in FILTER_SCHEMAS["ibge_pevs"]["dims"]
        if d.get("type") == "products" and d.get("hint")
    ]
    # Guard the guard: an empty list would make the loop below vacuously true.
    assert len(hints) > 1, "nenhum hint de produtos encontrado no registro do backend"
    for hint in hints:
        assert "vegetal e silvicultura" not in hint.lower()
