"""A identidade de um produto é BANCO + TABELA + CÓDIGO, e em um lugar só.

PEVS e PPM unem duas tabelas SIDRA sob um token de banco só, então `banco + código` não
distingue as metades: seriam um agrupamento, uma visibilidade e um nível cobrindo as duas,
e a ingestão dirigida pelo catálogo perderia a metade não marcada em silêncio.

Eram **16** `partition by` espalhados por 5 módulos Python e mais 3 modelos dbt. Uma chave
que muda em 15 lugares e fica no 16º é a forma exata do defeito que este projeto já teve
três vezes em um único dia (o eixo `origem`, o `niveis`, a regra do `sidra_tabela`), e em
todas a suíte ficou verde. Por isso a chave vive em constantes/macro e estes testes varrem
os CALL SITES — não a função.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from embrapa_dashboard.serving import sql as sqlbuild

_RAIZ = Path(__file__).resolve().parents[1]
_PY = [
    "src/embrapa_dashboard/serving/curation.py",
    "src/embrapa_dashboard/serving/gateway.py",
    "src/embrapa_dashboard/serving/agrupamentos.py",
    "src/embrapa_dashboard/ibge/catalog_resolver.py",
    "src/embrapa_dashboard/doctor.py",
]
_DBT = [
    "dbt/models/core/dim_produto_catalog.sql",
    "dbt/models/core/dim_produto_visibility.sql",
    "dbt/models/core/dim_code_industrialization_scd2.sql",
]
# As chaves ANTIGAS, que ignoravam a tabela. Nenhuma pode sobreviver fora do sql.py.
_ANTIGAS = (
    r"partition by codigo_produto, banco\b(?!,)",
    r"partition by source, code\b(?!,)",
    r"partition by element_kind, banco, code\b(?!,)",
)


@pytest.mark.parametrize("arquivo", _PY + _DBT)
def test_nenhum_call_site_usa_a_chave_antiga(arquivo: str) -> None:
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    for padrao in _ANTIGAS:
        assert not re.search(padrao, texto), f"{arquivo}: chave antiga (sem a tabela) sobreviveu"


@pytest.mark.parametrize("arquivo", _PY)
def test_call_sites_python_derivam_da_constante(arquivo: str) -> None:
    """Cada `partition by` sobre um log de curadoria tem de vir de `sql.CHAVE_*`."""
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    partitions = re.findall(r"partition by ([^\n]*)", texto)
    # Só os logs de PRODUTO. O log de agrupamentos particiona por `group_id`: um grupo não
    # é um produto e não tem tabela SIDRA — exigir a chave lá seria exigir uma coluna que
    # não existe. Excluir por nome (e não por arquivo) mantém a varredura honesta se um
    # log novo aparecer no mesmo módulo.
    dos_logs = [
        p for p in partitions if ("edited_at" in p or "change_id" in p) and "group_id" not in p
    ]
    assert dos_logs, f"{arquivo}: o varredor não achou nenhum partition by de log de produto"
    for p in dos_logs:
        assert "sqlbuild.CHAVE_" in p, f"{arquivo}: chave redigitada em vez de derivada — {p!r}"


@pytest.mark.parametrize("arquivo", _DBT)
def test_call_sites_dbt_derivam_do_macro(arquivo: str) -> None:
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    for p in re.findall(r"partition by ([^\n]*)", texto):
        assert "chave_produto(" in p, f"{arquivo}: chave redigitada em vez do macro — {p!r}"


def test_as_tres_chaves_carregam_a_tabela_e_a_sentinela() -> None:
    """A sentinela é o que torna a chave uniforme: nos bancos de uma tabela só a coluna não
    carrega informação, e sem o `ifnull` um NULL viraria uma identidade à parte."""
    for nome in ("CHAVE_CATALOGO", "CHAVE_CLASSIFICACAO", "CHAVE_CICLO_DE_VIDA"):
        frag = getattr(sqlbuild, nome)
        assert "sidra_tabela" in frag, f"{nome} não inclui a tabela"
        assert f"'{sqlbuild.SEM_TABELA}'" in frag, f"{nome} não colapsa NULL na sentinela"


def test_python_e_dbt_concordam_na_sentinela() -> None:
    """Os dois lados materializam a MESMA identidade: o Python escreve e lê os logs, o dbt
    materializa as dims que a UI e o Gold consomem. Divergir é criar dois produtos onde há
    um — e nada mais no sistema notaria."""
    macro = (_RAIZ / "dbt/macros/chave_produto.sql").read_text(encoding="utf-8")
    assert f"'{sqlbuild.SEM_TABELA}'" in macro, "macro do dbt usa outra sentinela"


# ── o lado da ESCRITA ─────────────────────────────────────────────────────────
# A varredura acima cobre só os `partition by` — as LEITURAS. Trocar a chave e varrer
# apenas um dos lados foi o defeito real: cinco caminhos de escrita ficaram gravando sem a
# tabela, e cada um deles cairia na sentinela — o delete não deletaria, a classificação
# abriria uma linhagem SCD2 paralela, o evento de ciclo de vida marcaria outro produto.
# Nenhum daria erro. Estes testes varrem o outro lado.
_ESCRITORES = [
    "src/embrapa_dashboard/serving/curation.py",
    "src/embrapa_dashboard/serving/attribute_engineering.py",
    "src/embrapa_dashboard/serving/catalog_lifecycle.py",
]


def _e_log_de_produto(stmt: str) -> bool:
    """Só os inserts que gravam a IDENTIDADE de um produto. Ficam de fora, corretamente: a
    allowlist de editores (resource/email), o log de agrupamentos (um grupo não é produto e
    não tem tabela SIDRA) e o de (aduana × fluxo). O critério é o identificador do produto
    aparecer na lista de colunas — e não o arquivo, para que um log novo no mesmo módulo
    entre na varredura sozinho."""
    return ("codigo_produto" in stmt or re.search(r"\bcode\b", stmt)) and "group_id" not in stmt


def _inserts(texto: str) -> list[str]:
    """Cada `insert into ... (colunas)` do arquivo, achatado."""
    return [
        " ".join(m.split())
        for m in re.findall(r"insert into[^)]*\([^)]*\)", texto, re.I | re.S)
    ]


@pytest.mark.parametrize("arquivo", _ESCRITORES)
def test_todo_insert_em_log_de_produto_grava_a_tabela(arquivo: str) -> None:
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    alvo = [s for s in _inserts(texto) if _e_log_de_produto(s)]
    assert alvo, f"{arquivo}: o varredor não achou insert de log de produto"
    for stmt in alvo:
        assert "sidra_tabela" in stmt, f"{arquivo}: insert sem a tabela — {stmt[:90]!r}"


def test_o_varredor_de_escrita_enxerga_os_inserts() -> None:
    """Guarda o teste acima: um regex que não casa nada o faria passar para sempre."""
    total = sum(len(_inserts((_RAIZ / a).read_text(encoding="utf-8"))) for a in _ESCRITORES)
    assert total >= 2, f"o varredor achou {total} insert(s) — regex quebrado?"


def test_o_tombstone_preserva_a_tabela_da_entrada() -> None:
    """O caso mais traiçoeiro: um delete sem a tag marca a SENTINELA, a entrada real segue
    ativa, e a remoção reporta sucesso. `remove_produto_catalog` tem de resolver a tag
    guardada antes de gravar."""
    fonte = inspect.getsource(
        __import__("embrapa_dashboard.serving.curation", fromlist=["x"]).remove_produto_catalog
    )
    assert "_current_sidra_tabela" in fonte, "o tombstone não preserva a tabela da entrada"


def test_os_registros_por_codigo_resolvem_a_tabela_pelo_catalogo() -> None:
    """Nível e ciclo de vida não guardam a identidade — o catálogo guarda. Os dois têm de
    perguntar a ele, senão gravam na sentinela."""
    from embrapa_dashboard.serving import attribute_engineering, catalog_lifecycle

    for mod in (attribute_engineering, catalog_lifecycle):
        fonte = inspect.getsource(mod)
        assert "tabela_do_produto" in fonte, f"{mod.__name__} não resolve a tabela pelo catálogo"
