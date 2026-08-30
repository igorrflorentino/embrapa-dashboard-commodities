"""A chave do gate de visibilidade, como a documentação a descreve, tem de bater com a
chave que o dbt realmente impõe.

Esta deriva aconteceu de verdade: a v1.46.5 acrescentou `sidra_tabela` à
`dim_produto_visibility` e ao predicado que a consome, o spec em `PLANS/` foi atualizado
no mesmo PR — e `CLAUDE.md` e `ARCHITECTURE.md` ficaram dizendo `(source, code)` por mais
duas versões. `CLAUDE.md` é o arquivo carregado no contexto de toda sessão futura, então
uma linha errada ali não fica parada: ela se propaga para decisões.

A âncora é o teste `unique_combination_of_columns` do próprio modelo, em `_core.yml` —
mantido para impor o grão da view, não para este teste. Segue o padrão de
`test_claude_md_ingest_batch.py`, que guarda outra afirmação do CLAUDE.md contra o
registro que a decide.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

_RAIZ = pathlib.Path(__file__).resolve().parents[1]
_DOCS = ("CLAUDE.md", "ARCHITECTURE.md")


def _chave_imposta_pelo_dbt() -> list[str]:
    """As colunas do `unique_combination_of_columns` de `dim_produto_visibility`."""
    modelos = yaml.safe_load(
        (_RAIZ / "dbt" / "models" / "core" / "_core.yml").read_text(encoding="utf-8")
    )
    for modelo in modelos["models"]:
        if modelo["name"] != "dim_produto_visibility":
            continue
        for teste in modelo.get("tests", []):
            if "dbt_utils.unique_combination_of_columns" in teste:
                return list(
                    teste["dbt_utils.unique_combination_of_columns"]["arguments"][
                        "combination_of_columns"
                    ]
                )
    return []


def test_o_extrator_enxerga_a_chave() -> None:
    """Guarda o teste abaixo. Um extrator que devolvesse lista vazia faria a asserção de
    substring passar para sempre — o modo de falha que este repositório já viu cinco
    vezes em varreduras minhas."""
    chave = _chave_imposta_pelo_dbt()

    assert chave, (
        "não achei o unique_combination_of_columns de dim_produto_visibility em "
        "_core.yml — conserte o extrator, NÃO relaxe o teste abaixo"
    )
    assert len(chave) >= 2, f"chave suspeita de tão curta: {chave}"


@pytest.mark.parametrize("doc", _DOCS)
def test_a_documentacao_descreve_a_chave_que_o_dbt_impoe(doc: str) -> None:
    """`CLAUDE.md` e `ARCHITECTURE.md` descrevem a view por uma tupla de colunas; ela tem
    de ser a que o dbt impõe. Não confere prosa — confere que a tupla escrita nos docs
    contém exatamente os mesmos nomes, na mesma ordem."""
    chave = _chave_imposta_pelo_dbt()
    esperado = f"({', '.join(chave)})"
    texto = (_RAIZ / doc).read_text(encoding="utf-8")

    trechos = [ln for ln in texto.splitlines() if "dim_produto_visibility" in ln]
    assert trechos, f"{doc} não menciona dim_produto_visibility — o teste ficou sem alvo"

    assert any(esperado in ln for ln in trechos), (
        f"{doc} descreve dim_produto_visibility sem a chave que o dbt impõe "
        f"({esperado}). Linhas encontradas:\n  " + "\n  ".join(t.strip()[:150] for t in trechos)
    )
