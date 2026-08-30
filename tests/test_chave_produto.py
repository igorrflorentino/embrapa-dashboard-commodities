"""A identidade de um produto é BANCO + TABELA + CÓDIGO, e em um lugar só.

PEVS e PPM unem duas tabelas SIDRA sob um token de banco só, então `banco + código` não
distingue as metades: seriam um agrupamento, uma visibilidade e um nível cobrindo as duas,
e a ingestão dirigida pelo catálogo perderia a metade não marcada em silêncio.

Eram **16** `partition by` espalhados por 5 módulos Python e mais 3 modelos dbt. Uma chave
que muda em 15 lugares e fica no 16º é a forma exata do defeito que este projeto já teve
três vezes em um único dia (o eixo `origem`, o `niveis`, a regra do `tabela`), e em
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
        assert "tabela" in frag, f"{nome} não inclui a tabela"
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
        " ".join(m.split()) for m in re.findall(r"insert into[^)]*\([^)]*\)", texto, re.I | re.S)
    ]


@pytest.mark.parametrize("arquivo", _ESCRITORES)
def test_todo_insert_em_log_de_produto_grava_a_tabela(arquivo: str) -> None:
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    alvo = [s for s in _inserts(texto) if _e_log_de_produto(s)]
    assert alvo, f"{arquivo}: o varredor não achou insert de log de produto"
    for stmt in alvo:
        assert "tabela" in stmt, f"{arquivo}: insert sem a tabela — {stmt[:90]!r}"


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
    assert "_current_tabela" in fonte, "o tombstone não preserva a tabela da entrada"


def test_o_ciclo_de_vida_grava_a_tabela_que_o_catalogo_resolveu(monkeypatch) -> None:
    """Comportamental de propósito: a versão anterior deste teste procurava o NOME
    `tabela_do_produto` no texto do módulo, e a linha de `import` sobrevivia — trocar a
    chamada por `None` passava verde. O que prende é o parâmetro que chega ao BigQuery.

    Nível e ciclo de vida não guardam a identidade; o catálogo guarda. Os dois têm de
    perguntar a ele, senão gravam na sentinela e o evento marca outro produto.
    """
    from unittest.mock import MagicMock

    from embrapa_dashboard.serving import catalog_lifecycle, curation

    monkeypatch.setattr(curation, "tabela_do_produto", lambda *a, **k: "291")
    bq = MagicMock()
    catalog_lifecycle._insert_lifecycle_event(
        bq,
        "proj.ds.log",
        element_kind="commodity",
        banco="pevs",
        code="3457",
        status="descontinuado",
        reason=None,
        purge_note=None,
        edited_by="a@x",
        change_id="c1",
    )
    params = {p.name: p.value for p in bq.query.call_args.kwargs["job_config"].query_parameters}
    assert params["tabela"] == "291", "o evento não levou a tabela resolvida"


# ── a documentação do grão ────────────────────────────────────────────────────
_DOCS_DE_GRAO = [
    "dbt/models/core/dim_produto_catalog.sql",
    "dbt/models/core/dim_produto_visibility.sql",
    "dbt/models/core/dim_code_industrialization_scd2.sql",
    "dbt/models/core/_core.yml",
    "PLANS/curadoria_catalogo.md",
]


@pytest.mark.parametrize("arquivo", _DOCS_DE_GRAO)
def test_nenhum_doc_descreve_a_chave_sem_a_tabela(arquivo: str) -> None:
    """Trocar a chave e deixar a prosa para trás faz o doc mentir sobre o modelo — e um
    leitor concluiria que dois produtos com o mesmo código colidem. Aconteceu: as três dims
    e a spec da Curadoria seguiram declarando `(codigo_produto, banco)` e `(source, code)`
    horas depois da mudança. Só o texto imediatamente ao redor da chave é verificável
    mecanicamente; é pouco, e é exatamente o que apodreceu."""
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    for padrao in (
        # Sem lookahead: a forma CORRETA é `(codigo_produto, banco, tabela)`, que não
        # contém `(codigo_produto, banco)` — o parêntese de fechar é o que separa as duas.
        # A versão anterior punha um `(?!,)` DEPOIS do parêntese e não pegava a injeção.
        r"per \(codigo_produto, banco\)",
        r"per \(source, code\)",
        r"key `\(codigo_produto, banco\)`",
        r"row per \(source, code, version\)",
    ):
        assert not re.search(padrao, texto), f"{arquivo}: descreve a chave sem a tabela — {padrao}"


# ── idempotência: o change_id só é replay do MESMO produto ────────────────────
# Um `change_id` reusado entre as DUAS metades de um código compartilhado passaria por
# replay e a segunda edição sumiria — sem erro, sem log, sem nada. As guardas comparam a
# chave INTEIRA, e as chaves do frontend a compõem inteira.
_GUARDAS = [
    "src/embrapa_dashboard/serving/curation.py",
    "src/embrapa_dashboard/serving/attribute_engineering.py",
]


@pytest.mark.parametrize("arquivo", _GUARDAS)
def test_as_guardas_de_idempotencia_comparam_a_chave_inteira(arquivo: str) -> None:
    texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
    tuplas = re.findall(r"ensure_no_change_id_conflict\(.*?\n\s*\(([^)]*)\)", texto, re.S)
    # Só as que identificam um PRODUTO. Fica de fora, corretamente, a do eixo
    # (aduana × fluxo): ela não fala de produto e não tem tabela SIDRA. O escopo é por
    # CONTEÚDO da tupla, não por arquivo, para que um guarda novo entre sozinho.
    de_produto = [t for t in tuplas if "codigo_produto" in t or '"code"' in t]
    assert de_produto, f"{arquivo}: o varredor não achou guarda de produto"
    for t in de_produto:
        assert "tabela" in t, f"{arquivo}: guarda sem a tabela — ({t.strip()})"


def test_as_chaves_de_idempotencia_do_frontend_incluem_a_tabela() -> None:
    """`_saveKey` e a chave `rm:` viram change_ids. Sem a tabela, editar as duas metades com
    os mesmos atributos gera a MESMA chave."""
    jsx = (_RAIZ / "frontend/src/ui/ViewCadastroProdutos.jsx").read_text(encoding="utf-8")
    for rotulo in ("save:", "rm:"):
        linha = next(x for x in jsx.split("\n") if f"`{rotulo}" in x)
        assert "tabela" in linha, f"chave {rotulo} sem a tabela — {linha.strip()[:80]}"


def test_o_delete_envia_a_tabela_da_entrada() -> None:
    """O backend resolve a tag quando omitida, mas resolver é escolher a ÚLTIMA escrita —
    ambíguo se houver duas metades. A linha da tela já tem a tag (ela desenha o selo)."""
    jsx = (_RAIZ / "frontend/src/ui/ViewCadastroProdutos.jsx").read_text(encoding="utf-8")
    linha = next(x for x in jsx.split("\n") if "catalog/entry/remove" in x)
    assert "tabela" in linha, "o delete não envia a tabela"


# ── a regra da tag vale para TODO banco multi-tabela ──────────────────────────
def test_a_regra_da_tag_nao_nomeia_um_banco() -> None:
    """`if banco == "ppm":` fechava as DUAS metades da regra no ppm, e o pevs escapava:
    entrada nova sem tag era aceita (uma sonda HTTP registrou `9999999` na sentinela para
    provar) e um update parcial DERRUBAVA a tag, movendo o produto para a sentinela.

    É o padrão "condicional que nomeia UM banco" — ela codifica um censo do mundo, e o
    mundo cresceu quando a silvicultura entrou. A âncora é a constante, não o literal.

    Varre o MÓDULO INTEIRO, não uma função. A primeira versão deste teste lia o fonte de
    `record_produto_catalog`, e reprovou quando a preservação foi extraída para
    `_preserve_omitted_fields` na v1.45.0 — comportamento idêntico, teste vermelho. Um teste
    que só sabe onde a regra mora hoje não guarda a regra, guarda o layout do arquivo."""
    from embrapa_dashboard.serving import curation

    assert 'banco == "ppm"' not in _so_o_codigo(inspect.getsource(curation)), (
        "a regra voltou a nomear um banco"
    )
    assert set(curation._BANCOS_MULTI_TABELA) == set(
        curation._tabelas_validas_por_banco(_cfg_falsa())
    ), "a constante e o vocabulário de tabelas divergiram"


def _so_o_codigo(fonte: str) -> str:
    """O fonte sem comentários NEM docstrings.

    Comentários e docstrings citam `banco == "ppm"` de propósito, para explicar o que
    quebrou; uma varredura cega a eles reprovaria a própria explicação. Filtrar por
    `startswith("#")` cobria só metade — a primeira versão deste teste passava despercebida
    por um docstring que continha o literal. `tokenize` separa código de texto de verdade,
    em vez de adivinhar pela indentação da linha."""
    import io as _io
    import tokenize as _tok

    pedacos = []
    for t in _tok.generate_tokens(_io.StringIO(fonte).readline):
        if t.type not in (_tok.COMMENT, _tok.STRING):
            pedacos.append(t.string)
    return " ".join(pedacos)


def _cfg_falsa():
    from embrapa_dashboard.config import Settings

    return Settings.model_construct(
        ppm_herd_table_id="3939",
        ppm_animal_table_id="74",
        ibge_table_id="289",
        silvicultura_table_id="291",
    )


@pytest.mark.parametrize("banco", ["ppm", "pevs"])
def test_entrada_nova_exige_a_tag_em_todo_banco_multi_tabela(banco: str) -> None:
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="obrigatória"):
        curation._validate_tabela(banco, None, _cfg_falsa(), require_for_ppm=True)


@pytest.mark.parametrize("banco", ["ppm", "pevs"])
def test_update_sem_a_tag_e_legitimo_porque_o_chamador_preserva(
    banco: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ausência num UPDATE é legítima só porque o chamador resolve a tag guardada antes de
    validar. As duas coisas andam juntas — se a preservação sumir, esta permissão vira o
    buraco: a escrita append-only grava a tag vazia e o produto vai para a sentinela
    `sql.SEM_TABELA`, sumindo das duas metades do banco.

    Verifica o COMPORTAMENTO, não o texto-fonte. A versão anterior procurava a chamada a
    `_current_tabela` dentro de `record_produto_catalog` e reprovou quando ela foi
    extraída na v1.45.0 — a preservação continuava lá, só tinha mudado de casa."""
    from embrapa_dashboard.serving import curation

    # A permissão: sem tag, num update, o validador não recusa.
    curation._validate_tabela(banco, None, _cfg_falsa(), require_for_ppm=False)

    # E a contrapartida que a torna segura: a tag guardada é recuperada quando omitida.
    guardada = "3939" if banco == "ppm" else "291"
    monkeypatch.setattr(curation, "_current_tabela", lambda *a, **k: guardada)
    monkeypatch.setattr(curation, "_current_descricao", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_current_lifecycle", lambda *a, **k: (None, None))
    tag, _desc, _ing, _vis = curation._preserve_omitted_fields(
        object(),
        "t",
        "4403",
        banco,
        is_active=True,  # UPDATE de uma entrada existente
        tabela=None,  # que NÃO reenvia a tag
        descricao_produto=None,
        ingestao=None,
        visibilidade=None,
    )
    assert tag == guardada, "o update deixou de preservar a tag guardada"

    # E numa entrada NOVA não há o que preservar — a tag continua ausente, e é o portão
    # (require_for_ppm=True) que recusa. Sem esta metade, "preservou" e "inventou" ficam
    # indistinguíveis.
    tag_nova, _d, _i, _v = curation._preserve_omitted_fields(
        object(),
        "t",
        "4403",
        banco,
        is_active=False,
        tabela=None,
        descricao_produto=None,
        ingestao=None,
        visibilidade=None,
    )
    assert tag_nova is None
