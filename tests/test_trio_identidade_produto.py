"""O trio `(banco, tabela, código)` identifica um produto em TODAS as camadas.

Decisão de projeto (2026-08-30): o trio vale nos CINCO bancos, inclusive nos que têm uma
tabela só — PAM usa o id SIDRA real (5457), COMEX e COMTRADE usam um nome do próprio
projeto. A simetria é o objetivo: com o trio valendo em todos, cada função de identidade
tem UMA forma, sem o ramo "este banco tem tabela / aquele não". Era esse ramo que fazia a
regra deixar de se propagar — v1.46.1 (gráficos), v1.46.5 (gate de visibilidade) e os sete
achados de `docs/audits/chave_produto_audit_2026-08-30.md`.

As âncoras são externas a este arquivo: os `.sql` dos modelos, mantidos pelo pipeline, e as
chaves de unicidade declaradas nos `.yml`, mantidas para impor o grão.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

_RAIZ = pathlib.Path(__file__).resolve().parents[1]
_DBT = _RAIZ / "dbt" / "models"

# Os modelos de FATO por banco. Um sexto banco entra aqui e nos ids de `config.py`.
_GOLD_PRODUTO = [
    "gold_pevs_production",
    "gold_pam_production",
    "gold_ppm_production",
    "gold_comex_flows",
    "gold_comtrade_flows",
]
_MARTS = [
    "serving_pevs_annual",
    "serving_pam_annual",
    "serving_ppm_annual",
    "serving_comex_annual",
    "serving_comex_seasonality",
    "serving_comtrade_annual",
]
_COD = {"codigo_produto", "product_code", "code", "ncm_code", "cmd_code"}


def _sem_comentarios(sql: str) -> str:
    """O SQL sem comentários de linha — a palavra `tabela` sobrevive na prosa de quase todo
    modelo, e um grep cru passaria verde por causa dela (foi o que aconteceu na v1.46.4)."""
    return re.sub(r"--.*", "", sql)


def _modelo(nome: str) -> str:
    achados = list(_DBT.rglob(f"{nome}.sql"))
    assert len(achados) == 1, f"{nome}: {len(achados)} arquivos"
    return _sem_comentarios(achados[0].read_text(encoding="utf-8"))


def _chaves_de_unicidade() -> list[tuple[str, list[str]]]:
    saida = []
    for p in _DBT.rglob("_*.yml"):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for m in doc.get("models") or []:
            for t in m.get("tests") or []:
                if not isinstance(t, dict):
                    continue
                for nome, cfg in t.items():
                    if "unique_combination" not in nome:
                        continue
                    cols = (cfg or {}).get("arguments", {}).get("combination_of_columns", [])
                    saida.append((m["name"], list(cols)))
    return saida


def test_o_varredor_enxerga_os_modelos_e_as_chaves() -> None:
    """Guarda os testes abaixo: um caminho errado ou um parser quebrado devolveria vazio e
    os faria passar para sempre — o modo de falha que este repositório já viu seis vezes."""
    assert all(_modelo(m) for m in _GOLD_PRODUTO + _MARTS)
    chaves = _chaves_de_unicidade()
    assert len(chaves) >= 15, f"só {len(chaves)} chaves — o parser quebrou?"
    assert any(set(c) & _COD for _, c in chaves)


@pytest.mark.parametrize("modelo", _GOLD_PRODUTO + _MARTS)
def test_todo_modelo_de_produto_carrega_a_tabela(modelo: str) -> None:
    """Todo Gold de produto e toda mart PROJETAM `tabela` — inclusive os bancos de UMA
    tabela. É o que permite ao consumidor tratar os cinco igual.

    Procura a PROJEÇÃO (uma linha que é só `tabela,` ou `<alias>.tabela,`), não a palavra:
    a primeira versão deste teste aceitava qualquer menção, e uma injeção que apagou a
    projeção de `gold_comex_flows` passou verde — a palavra sobrevivia no `group by`."""
    projecao = re.compile(r"^\s*(?:[a-z_]{1,4}\.)?tabela,\s*$", re.M)
    assert projecao.search(_modelo(modelo)), (
        f"{modelo} não projeta `tabela` — o trio deixa de valer neste banco e todo "
        f"consumidor volta a precisar de um ramo por banco"
    )


def test_toda_chave_de_unicidade_com_codigo_inclui_a_tabela() -> None:
    """A chave declarada é o contrato do grão. Uma que traga um CÓDIGO de produto sem a
    tabela declara um grão mais estreito que a identidade — e, nos modelos multi-tabela,
    só passava porque os códigos das duas metades são disjuntos hoje."""
    faltando = [(m, c) for m, c in _chaves_de_unicidade() if (set(c) & _COD) and "tabela" not in c]
    assert not faltando, "chave(s) de unicidade sobre código SEM a tabela:\n  " + "\n  ".join(
        f"{m}: {c}" for m, c in faltando
    )


def test_o_join_do_agrupamento_casa_o_trio() -> None:
    """`gold_produto_agrupamento` resolve o agrupamento de cada código do Gold. Com o join
    sobre `(source, code)` contra um catálogo único no TRIO, um código nas duas tabelas de
    um banco casaria DUAS linhas e o LEFT JOIN das marts dobraria as somas de qty_base/val_*
    — a consequência que o cabeçalho do próprio modelo declara como load-bearing."""
    sql = _modelo("gold_produto_agrupamento")
    assert "c.tabela = x.tabela" in sql, "o join não casa a tabela"


def test_o_gate_de_visibilidade_casa_o_trio_nos_dois_lados() -> None:
    """A macro dbt e o espelho Python compõem o MESMO predicado. Um lado casar a tabela e o
    outro não deixaria metade do dashboard aplicando a regra nova e metade a velha."""
    from embrapa_dashboard.config import Settings
    from embrapa_dashboard.serving import sql as sqlbuild

    macro = _sem_comentarios(
        (_RAIZ / "dbt" / "macros" / "hidden_code_predicate.sql").read_text(encoding="utf-8")
    )
    assert "_vis_tabela" in macro
    # `_env_file=None`: o CI não tem `.env`, e `get_settings()` levantaria ValidationError —
    # o teste mediria a ausência do arquivo, não o predicado. Mesmo padrão do
    # `_isolated_settings` em test_serving.py.
    cfg = Settings(_env_file=None, gcp_project_id="p")  # type: ignore[call-arg]
    clause = sqlbuild.visibility_clause(cfg, "pevs", "product_code")
    assert "_vis_tabela" in clause


def test_o_padrao_por_banco_concorda_entre_dbt_e_python() -> None:
    """A macro `tabela_com_padrao` e o espelho `sql.tabela_com_padrao` completam a MESMA
    ausência, em arquivos e linguagens diferentes: a macro para as dims, o Python para os
    leitores que reimplementam o latest-wins sobre o log cru.

    Divergirem é sempre defeito — foi assim que a v1.47.0 nasceu com a tabela chegando NULA
    ao editor do Cadastro (chave `comtrade:nan:440724`): a dim aplicava o padrão e o
    `fetch_produto_catalog` não. Nenhum dos dois DERIVA do outro; ambos derivam dos ids de
    tabela, e por isso o teste compara o conjunto de pares que cada lado produz."""
    from embrapa_dashboard.config import Settings
    from embrapa_dashboard.serving import sql as sqlbuild

    cfg = Settings(_env_file=None, gcp_project_id="p")  # type: ignore[call-arg]
    # Compara o CONJUNTO DE BANCOS que recebe padrão. A macro escreve `{{ var(...) }}` e o
    # Python escreve o valor já resolvido, então comparar os valores exigiria resolver as
    # vars aqui — e a paridade var↔config já é guardada por `embrapa doctor`. O que ESTE
    # teste protege é o que aquele não vê: um banco ganhar padrão de um lado só.
    ramo = re.compile(r"when\s+'([a-z_]+)'\s+then")

    macro = (_RAIZ / "dbt" / "macros" / "tabela_com_padrao.sql").read_text(encoding="utf-8")
    do_dbt = set(ramo.findall(_sem_comentarios(macro).split("{% macro")[1]))
    do_python = set(ramo.findall(sqlbuild.tabela_com_padrao(cfg)))

    assert do_dbt, "o extrator não achou os ramos da macro — conserte o extrator"
    assert do_dbt == do_python, (
        f"bancos com padrão divergem.\n  dbt:    {sorted(do_dbt)}\n  python: {sorted(do_python)}"
    )

    # E nenhum banco MULTI-tabela pode ter padrão: adivinhar a metade seria inventar dado.
    from embrapa_dashboard.serving.curation import _BANCOS_MULTI_TABELA

    com_padrao = do_python
    assert not (com_padrao & set(_BANCOS_MULTI_TABELA)), (
        f"banco multi-tabela com padrão: {sorted(com_padrao & set(_BANCOS_MULTI_TABELA))}"
    )
