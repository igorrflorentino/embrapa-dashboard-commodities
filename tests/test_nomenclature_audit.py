"""O classificador do registro de divergências das nomenclaturas de comércio.

COMEX e COMTRADE não trazem descrição nos dados — o arquivo do MDIC tem código e números,
o Bronze do COMTRADE também. O nome que o pesquisador lê é um artefato editorial deste
repositório, então a política (2026-08-29) é: usar o texto pleno da nomenclatura e
REGISTRAR toda divergência contra o campo de exibição do MDIC.

O que se testa aqui são as funções puras (a rede fica no script, operado à mão): o
detector de texto degradado e o classificador. Errar o detector é o risco real — ele é o
que impede que `Outs.painéis` entre no lugar de um rótulo bom.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parents[1] / "scripts/audit_nomenclature_seeds.py"
_spec = importlib.util.spec_from_file_location("audit_nomenclature_seeds", _CAMINHO)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


@pytest.mark.parametrize(
    "texto",
    [
        'Painéis de particul."waferboard", etc.em bruto',  # aspas + ponto colado
        "Outs.painéis de fibras de madeira",  # abreviação clássica do MDIC
        "n/trab.mecan.d>0.8g/cm3",
        "Lenha",  # curto demais para identificar um produto
    ],
)
def test_detecta_texto_degradado(texto: str) -> None:
    assert _mod._degradado(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Madeira de coníferas, em bruto",
        "Purês e pastas, cozidos, de açaí (Euterpe oleracea)",
        "Dormentes de madeira, para vias férreas ou semelhantes, não impregnados",
        "Óleo de soja, refinado",  # ponto ausente; curto mas plausível
    ],
)
def test_nao_acusa_texto_bom(texto: str) -> None:
    assert not _mod._degradado(texto)


def test_ponto_seguido_de_MAIUSCULA_ou_espaco_nao_e_abreviacao() -> None:
    """O detector procura ponto colado em MINÚSCULA. `Espécie. Outra` e `Fagus spp.` são
    prosa normal e não podem ser acusados — um falso positivo aqui reclassificaria um
    rótulo bom como degradado e o mandaria ser reescrito."""
    assert not _mod._degradado("Madeira de faia (Fagus spp.), em bruto, mesmo descascada")
    assert not _mod._degradado("Uma frase. Outra frase completa aqui")


def test_classifica_cada_caso_no_seu_balde() -> None:
    assert _mod._classe("qualquer coisa", "") == "ausente no MDIC"
    assert _mod._classe("Madeira em bruto, tratada", "Outs.madeira") == "oficial abreviado"
    assert _mod._classe("Purês e pastas, cozidos, de açaí", "Purês de açaí") == "nosso mais pleno"
    assert _mod._classe("Bananas frescas", "Bananas-da-terra, secas") == "procedência distinta"


def test_registro_committado_tem_as_quatro_classes_e_os_dois_seeds() -> None:
    """Guarda o artefato, não só o gerador: um registro vazio ou truncado passaria
    despercebido, e ele é a resposta a 'de onde veio esse texto?'."""
    doc = (Path(__file__).resolve().parents[1] / "docs/nomenclatura_divergencias.md").read_text(
        encoding="utf-8"
    )
    assert "comex_ncm" in doc and "comtrade_hs" in doc
    assert "oficial abreviado" in doc and "nosso mais pleno" in doc
    # O caso que motivou a política: o MDIC dá ao código "outros" a descrição do irmão.
    assert "15079019" in doc


# ── a garantia do prefixo da SIDRA ────────────────────────────────────────────
# O teste dbt assert_sidra_prefix_strip_is_lossless verifica a propriedade nos DADOS, e por
# isso passa com qualquer padrão enquanto todo valor da SIDRA for um ordinal numérico —
# uma injeção provou isso. Ele acusa a SIDRA mudar de forma; não acusa AFROUXAREM o padrão.
# Esta é a outra metade: prende o padrão em si.
_SILVERS = [
    "dbt/models/silver/silver_ibge_pevs.sql",
    "dbt/models/silver/silver_ibge_silvicultura.sql",
]


@pytest.mark.parametrize("modelo", _SILVERS)
def test_o_prefixo_removido_e_ancorado_a_digitos(modelo: str) -> None:
    """`^[0-9]+(?:\\.[0-9]+)*\\s-\\s` só casa com um ordinal. O padrão anterior,
    `^([^-]+)\\s-\\s`, removia QUALQUER prefixo sem hífen: "Açaí - fruto" virava "fruto".
    Texto informativo não pode casar com [0-9.]+, então a perda fica impossível por
    construção — desde que ninguém troque o padrão de volta."""
    sql = (Path(__file__).resolve().parents[1] / modelo).read_text(encoding="utf-8")
    assert r"r'^[0-9]+(?:\.[0-9]+)*\s-\s'" in sql, f"{modelo}: padrão do prefixo afrouxou"
    assert r"r'^([^-]+)\s-\s'" not in sql, f"{modelo}: voltou o padrão que comia texto"


@pytest.mark.parametrize("modelo", _SILVERS)
def test_so_o_prefixo_e_removido_da_descricao(modelo: str) -> None:
    """Uma segunda remoção qualquer sobre a mesma coluna passaria despercebida pelo teste
    acima, que só confere o padrão do ordinal."""
    sql = (Path(__file__).resolve().parents[1] / modelo).read_text(encoding="utf-8")
    linha = next(x for x in sql.split("\n") if "as product_description" in x)
    assert linha.count("regexp_replace") == 1, f"{modelo}: mais de uma remoção na descrição"
    assert "substr" not in linha and "left(" not in linha.lower(), f"{modelo}: corte de string"
