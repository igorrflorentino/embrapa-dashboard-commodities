"""What the PEVS banco SAYS it covers must match the SIDRA table it actually reads.

The IBGE survey is named "Produção da Extração Vegetal e da Silvicultura" and has two
halves. This project ingests one: table 289, the EXTRACTION from native forest. The
silviculture half — planted forest, table 291 — is not ingested.

The registries described both. A researcher read "extrativismo vegetal e da silvicultura
… recursos florestais, nativos e plantados", looked for São Paulo, and found it empty —
and reasonably concluded the data was broken. It was not: SIDRA t289 itself reports "-"
for SP's charcoal, firewood and roundwood. What was wrong was the promise. The gap is not
marginal — in 2023 the half we hold is R$ 6,2 bi and the half we don't is R$ 31,7 bi.

The survey's NAME legitimately contains "Silvicultura" (it is a proper noun, and the ABNT
citation must keep it). What may not stand is a description of COVERAGE that includes the
half we never ingested. The mechanism that decides is `IBGE_TABLE_ID`, so pin the claim
to it — and pin both registry copies, since two copies agreeing proved nothing before.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BANCOS_JS = REPO / "frontend" / "src" / "ui" / "bancos.js"
SCHEMA_JS = REPO / "frontend" / "src" / "ui" / "filtersSchema.js"

# Phrases that assert the silviculture half is INCLUDED. Bare "silvicultura" is not one:
# it appears in the survey's own name, which stays.
CLAIMS_BOTH = (
    "vegetal e da silvicultura",
    "vegetal e silvicultura",
    "nativos e plantados",
    "nativas e plantadas",
)
# The description must not merely avoid the false claim — it must SAY the half is out, so
# a future rewrite that quietly drops the caveat fails here instead of on a researcher.
NAMES_THE_GAP = ("fica de fora", "289")


def _js_about() -> str:
    m = re.search(r"id:\s*'ibge_pevs'.*?about:\s*'(.*?)',\n", BANCOS_JS.read_text("utf-8"), re.S)
    assert m, "bancos.js: PEVS `about` not found"
    return m.group(1)


def _py_banco():
    from embrapa_dashboard.webapi.registries import BANCOS

    return next(b for b in BANCOS if b.id == "ibge_pevs")


def test_the_ingested_sidra_table_is_still_the_extraction_half() -> None:
    """The premise of every assertion below. If this ever changes, they must be revisited.

    Read from the DECLARED default and the documented `.env.example`, not from an
    instantiated `Settings` — building one needs GCP credentials the CI job has no reason
    to hold, and a test that only runs where a developer happens to have a `.env` is a
    test that passes for the wrong reason (this one did, until CI said otherwise).

    An operator who overrides IBGE_TABLE_ID in their own `.env` changes the premise —
    which is precisely why the claim is pinned here rather than trusted.
    """
    from embrapa_dashboard.config import Settings

    assert Settings.model_fields["ibge_table_id"].default == "289"
    assert "IBGE_TABLE_ID=289" in (REPO / ".env.example").read_text("utf-8")


@pytest.mark.parametrize("origem", ["spa", "backend"])
def test_pevs_description_does_not_promise_the_silviculture_half(origem: str) -> None:
    texto = (_js_about() if origem == "spa" else _py_banco().about).lower()
    encontrados = [c for c in CLAIMS_BOTH if c in texto]
    assert encontrados == [], f"{origem}: descrição promete a metade não ingerida: {encontrados}"


@pytest.mark.parametrize("origem", ["spa", "backend"])
def test_pevs_description_says_which_half_is_missing(origem: str) -> None:
    texto = (_js_about() if origem == "spa" else _py_banco().about).lower()
    assert any(m in texto for m in NAMES_THE_GAP), (
        f"{origem}: a descrição não diz que a silvicultura está fora — sem isso, o nome da "
        "pesquisa ('… e da Silvicultura') volta a ser lido como cobertura"
    )


def test_the_product_filter_hint_does_not_promise_it_either() -> None:
    """The same claim rode along in the products filter hint, in both copies."""
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
