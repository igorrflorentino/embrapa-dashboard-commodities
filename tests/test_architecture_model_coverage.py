"""Todo modelo dbt precisa aparecer no ARCHITECTURE.md.

`tests/test_doc_file_references.py` prende a direção PARA FRENTE: um caminho citado num
doc tem de existir. O que escapa é o INVERSO — um arquivo que existe e que nenhum doc
menciona. Foi assim que `silver_ibge_silvicultura.sql` ficou de fora: entrou em
2026-08-29 com um modelo Silver, uma tabela Bronze e uma coluna discriminadora no Gold, e
a árvore de pastas do ARCHITECTURE seguiu listando três modelos IBGE onde havia quatro.
Um leitor do doc concluiria que o PEVS tem uma metade só.

Renomear ou remover um teste falha alto (o import quebra); ACRESCENTAR um modelo não falha
em lugar nenhum — o doc só fica incompleto, em silêncio. Este teste é o alarme que faltava.

Não exige uma descrição boa, só a MENÇÃO: julgar prosa não é automatizável, mas a ausência
do nome é inequívoca e é o que de fato acontece.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[1]
_ARCH = (_RAIZ / "ARCHITECTURE.md").read_text(encoding="utf-8")
_CAMADAS = ("silver", "gold", "serving", "core")


def _modelos(camada: str) -> list[str]:
    return sorted(p.stem for p in (_RAIZ / f"dbt/models/{camada}").glob("*.sql"))


@pytest.mark.parametrize("camada", _CAMADAS)
def test_todo_modelo_dbt_aparece_no_architecture(camada: str) -> None:
    ausentes = [m for m in _modelos(camada) if m not in _ARCH]
    assert not ausentes, (
        f"modelo(s) de {camada}/ fora do ARCHITECTURE.md: {ausentes} — "
        "acrescente na árvore de pastas (a menção basta)"
    )


@pytest.mark.parametrize("camada", _CAMADAS)
def test_o_varredor_enxerga_os_modelos(camada: str) -> None:
    """Guarda o teste acima: um caminho errado devolveria zero modelos e o faria passar
    para sempre — cinco varreduras minhas estavam erradas antes do repositório estar."""
    assert len(_modelos(camada)) >= 5, f"nenhum modelo encontrado em dbt/models/{camada}/"
