"""Uma descrição de seed tem de fazer sentido SOZINHA.

As tabelas NCM/SH são hierárquicas: a linha de um SH6 herda o sentido do título-pai, e
sozinha lê como `"- Outras, de coníferas"` — que foi exatamente o que 36 linhas do capítulo
44 mostraram na tela de Cadastro de produtos (2026-08-29). O texto não estava truncado:
estava completo e mesmo assim ininteligível, porque veio de uma fonte hierárquica sem o
pai. O seed do COMEX nunca teve o problema (0 de 263); o do COMTRADE tinha 36 de 235,
todas do capítulo 44 — o mais recente a entrar, de procedência diferente das outras 199.

O segundo teste guarda contra a cura ser pior que a doença: a tabela do MDIC abrevia
algumas linhas para caber no campo (`Outs.painéis`, `n/trab.mecan.`, `recob.placas`), e
copiá-las cegamente teria degradado 9 rótulos. Onde o oficial vinha assim, o texto foi
COMPOSTO com o título-pai em vez de substituído.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

_SEEDS = Path(__file__).resolve().parents[1] / "dbt/seeds"
_ARQUIVOS = [("comtrade_hs.csv", "description"), ("comex_ncm.csv", "ncm_description")]


def _linhas(arquivo: str) -> list[dict]:
    with (_SEEDS / arquivo).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("arquivo,coluna", _ARQUIVOS)
def test_nenhuma_descricao_e_fragmento_hierarquico(arquivo: str, coluna: str) -> None:
    """`-` / `--` inicial é o marcador de nível da nomenclatura, não parte do nome."""
    frag = [r for r in _linhas(arquivo) if r[coluna].lstrip().startswith("-")]
    assert not frag, f"{arquivo}: {len(frag)} fragmento(s) — ex.: {frag[:3]}"


@pytest.mark.parametrize("arquivo,coluna", _ARQUIVOS)
def test_nenhuma_descricao_vem_abreviada_da_tabela_oficial(arquivo: str, coluna: str) -> None:
    """Um ponto colado numa letra minúscula (`Outs.painéis`, `n/trab.mecan.`) é a marca de
    um texto encurtado à força pelo MDIC — legível para máquina, não para o pesquisador."""
    maus = [r for r in _linhas(arquivo) if re.search(r"\.[a-zà-ú]", r[coluna])]
    assert not maus, f"{arquivo}: {len(maus)} descrição(ões) abreviada(s) — ex.: {maus[:3]}"


@pytest.mark.parametrize("arquivo,coluna", _ARQUIVOS)
def test_o_varredor_enxerga_as_descricoes(arquivo: str, coluna: str) -> None:
    """Guarda os testes acima: um CSV lido errado (coluna renomeada, separador trocado)
    devolveria zero linhas e faria os dois passarem para sempre."""
    linhas = _linhas(arquivo)
    assert len(linhas) > 200
    assert all(r[coluna].strip() for r in linhas), "há descrição vazia no seed"
