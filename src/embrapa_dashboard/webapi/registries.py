"""Registries — Python reference data for bancos, perspectives, and filters.

A Python port of the design system's ``bancos.js`` / ``views.js`` /
``filtersSchema.js``. Only ``Banco`` / ``banco_by_id`` are consumed today (by the
seam, to resolve a banco's capabilities, value column, and dimensions). The UI's
sidebar, perspective mega-menu, routing and capability gating derive from the
FRONTEND copies (``frontend/src/ui/{bancos,views,filtersSchema}.js``), which are
the live source of truth — the ``View``/``FILTER_SCHEMAS``/maturity helpers below
are reference/parity data, NOT a control surface. Keep entries aligned with the
frontend so the next reader is not misled, but the frontend is authoritative for
anything the UI renders.

Status model (three axes, kept distinct):
  * ``maturity`` — dataset lifecycle (planejado · desenvolvimento · ingestao ·
    beta · estavel · manutencao · descontinuado). Build-time; ``has_data``
    decides whether a banco renders real perspectives or the "Em breve" placeholder.
  * ``visible`` — backend-controlled visibility (hides a banco everywhere).
  * usage (active/inactive) — derived at render time, never stored.

This repo has five live Gold sources: PEVS, COMEX, COMTRADE (estável/beta), IBGE PAM
(beta — ``gold_pam_production``, wired end-to-end incl. the produtividade view, #105)
and IBGE PPM (livestock — ``gold_ppm_production``; adds the herd axis, NO produtividade).
Only SEFAZ NFe has no Gold table here, so it stays a ``planejado``
placeholder (the design system's supported "launch without all bancos" path) — a
lead decision recorded with the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Maturity stages (reference vocabulary only) ──────────────────────────────
# The canonical list of VALID maturity values, ordered Planejado → … →
# Descontinuado. PER-BANCO maturity is NOT defined here — its single source of
# truth is BigQuery (``research_inputs.banco_metadata``), served via
# ``/api/source-meta``. The frontend (``frontend/src/ui/bancos.js``) owns how a
# stage renders (``has_data``/``caveat``/``color``). This dict is kept only as a
# spec/parity reference for the allowed maturity strings.
MATURITY: dict[str, dict] = {
    "planejado": {
        "id": "planejado",
        "label": "Planejado",
        "color": "var(--pres-gray-400)",
        "has_data": False,
        "future": True,
        "order": 1,
        "desc": "No roadmap, mas sem implementação iniciada nem prazo definido.",
    },
    "desenvolvimento": {
        "id": "desenvolvimento",
        "label": "Em desenvolvimento",
        "color": "var(--status-mat-dev)",
        "has_data": True,
        "order": 2,
        "desc": "Em produção e já consultável, mas ainda em construção, cálculos podem mudar.",
    },
    "ingestao": {
        "id": "ingestao",
        "label": "Ingestão",
        "color": "var(--status-mat-ingest)",
        "has_data": False,
        "order": 3,
        "desc": (
            "Pipeline construído, mas os dados ainda estão sendo baixados das "
            "fontes oficiais — a cobertura pode mudar."
        ),
    },
    "beta": {
        "id": "beta",
        "label": "Beta",
        "color": "var(--info)",
        "has_data": True,
        "caveat": True,
        "order": 4,
        "desc": "Disponível para testes e validações, resultados podem mudar.",
    },
    "estavel": {
        "id": "estavel",
        "label": "Estável",
        "color": "var(--ok)",
        "has_data": True,
        "order": 5,
        "desc": "Banco em produção, 100% pronto para consumo e análise.",
    },
    "manutencao": {
        "id": "manutencao",
        "label": "Em manutenção",
        "color": "var(--warn)",
        "has_data": True,
        "caveat": True,
        "order": 6,
        "desc": "Em produção, porém em correção de cálculo/tabela ou atualização programada.",
    },
    "descontinuado": {
        "id": "descontinuado",
        "label": "Descontinuado",
        "color": "var(--status-mat-sunset)",
        "has_data": True,
        "caveat": True,
        "sunset": True,
        "order": 7,
        "desc": "Banco obsoleto, não recebe mais manutenção e será removido em breve.",
    },
}

# ── Capability vocabulary ────────────────────────────────────────────────────
CAPABILITIES: dict[str, dict] = {
    "product": {"label": "dimensão de produto"},
    "geo": {"label": "dimensão geográfica (UF/município)"},
    "flow": {"label": "fluxo origem → destino"},
    "partner": {"label": "dimensão de parceiro comercial"},
    "monthly": {"label": "granularidade temporal mensal/diária"},
    "quality": {"label": "dimensão de qualidade"},
    "area": {"label": "área plantada / colhida"},
    "yield": {"label": "rendimento (produtividade kg/ha)"},
    "herd": {"label": "efetivo de rebanho (estoque em cabeças)"},
}


@dataclass(frozen=True)
class Banco:
    """A data source the dashboard can consume (one Gold table).

    A banco's *maturity* (and note/date) is NOT defined here. The single source of
    truth is the BigQuery table ``research_inputs.banco_metadata`` (served via
    ``/api/source-meta`` and rendered by the frontend). The registry only carries a
    banco's static capabilities (dimensions, metrics, value columns, coverage).
    """

    id: str
    short: str
    label: str
    sub: str  # short tagline (page headers)
    # Plain-language onboarding description (the "Sobre" banco card). Parity with the frontend
    # bancos.js `about` (the runtime source of truth for the UI) — kept aligned here so the
    # repo's banco descriptions don't drift between code surfaces.
    about: str
    domain: str
    scope: str
    source: str
    table: str
    provides: tuple[str, ...]
    base_currency: str = "BRL"
    geo_level: str | None = None
    visible: bool = True
    dimensions: dict = field(default_factory=dict)
    metrics: tuple[dict, ...] = ()
    cobertura: dict = field(default_factory=dict)


# Cross-source comparable-metric catalogs (per banco). ``years`` is native
# coverage; the cross view intersects coverages across selected series.
_PEVS_METRICS = (
    {
        "id": "prod_value",
        "label": "Valor da produção",
        "family": "currency",
        "unit": "R$",
        "agg": "Valor real (IPCA) da extração vegetal",
        "years": [1986, 2024],
    },
    {
        "id": "prod_mass",
        "label": "Quantidade produzida (massa)",
        "family": "mass",
        "unit": "t",
        "agg": "Massa colhida das espécies de família massa",
        "years": [1986, 2024],
    },
    {
        "id": "prod_volume",
        "label": "Quantidade produzida (volume)",
        "family": "volume",
        "unit": "m³",
        "agg": "Volume das espécies de família volume",
        "years": [1986, 2024],
    },
)
_COMEX_METRICS = (
    {
        "id": "exp_value",
        "label": "Valor exportado (FOB)",
        "family": "currency",
        "unit": "US$",
        "agg": "Soma do valor FOB das exportações",
        "years": [1997, 2024],
    },
    {
        "id": "imp_value",
        "label": "Valor importado (CIF)",
        "family": "currency",
        "unit": "US$",
        "agg": "Soma do valor das importações",
        "years": [1997, 2024],
    },
    {
        "id": "exp_weight",
        "label": "Peso exportado",
        "family": "mass",
        "unit": "kg",
        "agg": "Soma do peso líquido exportado",
        "years": [1997, 2024],
    },
    {
        "id": "exp_price",
        "label": "Preço médio (US$/kg)",
        "family": "ratio",
        "unit": "US$/kg",
        "agg": "Valor FOB ÷ peso líquido",
        "years": [1997, 2024],
    },
)
# COMTRADE coverage after the 2026-06 backfill: Brazil's OWN declarations span
# 1989→2024 (reporter=BRA, full history). The WORLD total (world_exp) needs every
# reporter's rows, which only exist for 2022–2023 (the earlier all-reporters dev
# window — the global/mirror backfill is deferred). So exp_value/imp_value (Brazil)
# advertise [1989, 2024], while world_exp stays [2022, 2023] — the honest window
# where all-reporters data actually exists. These drive the cross-source
# comparable-window math (SeriesResult.coverage); do NOT widen world_exp until the
# all-reporters/mirror ingestion lands, or it would sum Brazil-only as "world".
_COMTRADE_METRICS = (
    {
        "id": "exp_value",
        "label": "Valor exportado (BR)",
        "family": "currency",
        "unit": "US$",
        "agg": "Exportações brasileiras declaradas à ONU",
        "years": [1989, 2024],
    },
    {
        "id": "imp_value",
        "label": "Valor importado (BR)",
        "family": "currency",
        "unit": "US$",
        "agg": "Importações brasileiras declaradas à ONU",
        "years": [1989, 2024],
    },
    {
        "id": "world_exp",
        "label": "Exportação mundial",
        "family": "currency",
        "unit": "US$",
        "agg": "Total mundial do produto (todos reporters)",
        "years": [2022, 2023],
    },
)

_UF_DIMS = {
    "origin": {"label": "UF de origem", "kind": "uf"},
    "dest": {"label": "UF de destino", "kind": "uf"},
    "partner": {"label": "UF parceira", "kind": "uf"},
}

# ── Banco registry ───────────────────────────────────────────────────────────
# PEVS / COMEX / COMTRADE / PAM / PPM are live (Gold marts; PAM = beta over
# gold_pam_production, PPM = livestock over gold_ppm_production, PEVS-shaped). Only
# SEFAZ NFe has no Gold here → planejado placeholder (lead decision: keep all 6,
# render "Em breve").
BANCOS: list[Banco] = [
    Banco(
        id="ibge_pevs",
        short="IBGE PEVS",
        label="IBGE · Produção da Extração Vegetal e da Silvicultura",
        sub="Produção e exploração de produtos agrícolas no território brasileiro",
        about=(
            "Reúne, ano a ano, a quantidade e o valor da produção florestal brasileira nas "
            "DUAS metades da pesquisa do IBGE: a extração vegetal, de floresta nativa "
            "(castanha-do-pará, açaí, madeira em tora, lenha, carvão), e a silvicultura, de "
            "floresta plantada — de onde vem a maior parte da madeira do país. O filtro "
            "Origem da produção separa as duas; sem ele, os números somam ambas, que é o "
            "total da pesquisa. É por isso que estados de floresta plantada, como São "
            "Paulo, aparecem aqui: eles quase não têm extrativismo."
        ),
        domain="Produção interna",
        scope="Brasil · UF · município",
        source="IBGE",
        table="gold_pevs_production",
        provides=("product", "geo", "quality"),
        base_currency="BRL",
        geo_level="municipio",
        dimensions={**_UF_DIMS, "product": {"codeLabel": "Código PEVS"}},
        metrics=_PEVS_METRICS,
        cobertura={
            "years": "1986 → presente",
            "atualizacao": "anual",
            "granularidade": "produto × município × ano",
        },
    ),
    Banco(
        id="mdic_comex",
        short="MDIC COMEX",
        label="MDIC · Comércio Exterior",
        sub="Exportação e importação brasileiras por estado de origem, produto e parceiro",
        about=(
            "Consolida as estatísticas oficiais do comércio exterior brasileiro: exportações e "
            "importações por produto (NCM), estado de origem e país parceiro. Fundamental para "
            "análises de balança comercial e do fluxo de mercadorias entre o Brasil e o mundo."
        ),
        domain="Comércio exterior",
        scope="UF de origem ↔ países parceiros",
        source="MDIC · SECEX",
        table="gold_comex_flows",
        provides=("product", "geo", "flow", "partner", "monthly", "quality"),
        base_currency="USD",
        geo_level="uf",
        dimensions={
            "origin": {"label": "UF de origem", "kind": "uf"},
            "dest": {"label": "país parceiro", "kind": "country"},
            "partner": {"label": "país parceiro", "kind": "country"},
            "product": {"codeLabel": "Código NCM"},
        },
        metrics=_COMEX_METRICS,
        cobertura={
            "years": "1997 → presente",
            "atualizacao": "mensal (D+30)",
            "granularidade": "NCM × UF × país × via × ano-mês",
        },
    ),
    Banco(
        id="un_comtrade",
        short="UN COMTRADE",
        label="UN Comtrade · Estatísticas de Comércio Internacional",
        sub="Fluxos de comércio entre nações reportados à Divisão de Estatística da ONU",
        about=(
            "É o maior repositório global de dados oficiais de comércio internacional, compilado "
            "pelas Nações Unidas. Oferece estatísticas de importação e exportação reportadas por "
            "diversos países, permitindo situar a participação do Brasil no mercado mundial de "
            "cada produto."
        ),
        domain="Comércio internacional",
        scope="País → país (com ou sem filtro Brasil)",
        source="UN Statistics Division",
        table="gold_comtrade_flows",
        provides=("product", "flow", "partner", "quality"),
        base_currency="USD",
        geo_level=None,
        dimensions={
            "origin": {"label": "país reporter", "kind": "country"},
            "dest": {"label": "país parceiro", "kind": "country"},
            "partner": {"label": "país parceiro", "kind": "country"},
            "product": {"codeLabel": "Código HS6"},
        },
        metrics=_COMTRADE_METRICS,
        cobertura={
            # 2000, not 1989: the v1.13.0 totals-only redesign ingests from
            # COMTRADE_START_YEAR=2000 and silver_comtrade_flows floors reference_year
            # at var('comtrade_min_year', 2000). Measured: no COMTRADE row before 2000
            # exists in Bronze, Silver OR Gold. Keep in step with bancos.js.
            "years": "2000 → presente",
            "atualizacao": "anual + revisões",
            "granularidade": "HS6 × par de países × ano",
        },
    ),
    Banco(
        id="ibge_pam",
        short="IBGE PAM",
        label="IBGE · Produção Agrícola Municipal",
        sub="Área, produção e rendimento das lavouras temporárias e permanentes",
        about=(
            "Detalha a produção agrícola municipal — área plantada e colhida, quantidade "
            "produzida, rendimento médio e valor — das principais lavouras temporárias e "
            "permanentes do país. Ideal para analisar o desempenho de culturas como soja, "
            "milho, café, cana-de-açúcar e mandioca."
        ),
        domain="Produção agrícola",
        scope="Brasil · UF · município",
        source="IBGE",
        table="gold_pam_production",
        # 'yield' (área × rendimento) is wired end-to-end via /api/productivity over
        # gold_pam_production's area_*_ha + production columns — keep in sync with
        # the frontend bancos.js provides list.
        provides=("product", "geo", "quality", "yield"),
        base_currency="BRL",
        geo_level="municipio",
        dimensions={**_UF_DIMS, "product": {"codeLabel": "Código PAM"}},
        cobertura={
            "years": "1974 → presente",
            "atualizacao": "anual (atualização mensal automática)",
            "granularidade": "lavoura × município × ano",
        },
    ),
    Banco(
        id="ibge_ppm",
        short="IBGE PPM",
        label="IBGE · Pesquisa da Pecuária Municipal",
        sub="Efetivo dos rebanhos e produção de origem animal (leite, ovos, mel, lã)",
        about=(
            "Reúne informações anuais sobre os efetivos da pecuária — o tamanho dos rebanhos, em "
            "cabeças — e a produção de origem animal (leite, ovos, mel e lã) nos municípios "
            "brasileiros. Permite avaliar tanto o estoque de animais quanto o que eles produzem."
        ),
        domain="Produção pecuária",
        scope="Brasil · UF · município",
        source="IBGE",
        table="gold_ppm_production",
        # PPM is livestock → NO planted area → NO 'yield' capability (the Produtividade
        # view stays dark). It DOES add the 'herd' axis (efetivo, estoque em cabeças) that
        # gates the dedicated 'Rebanho' perspective, so it is NOT plain PEVS-shaped. Keep
        # in sync with the frontend bancos.js provides list.
        provides=("product", "geo", "quality", "herd"),
        base_currency="BRL",
        geo_level="municipio",
        dimensions={**_UF_DIMS, "product": {"codeLabel": "Código PPM"}},
        cobertura={
            "years": "1974 → presente",
            "atualizacao": "anual (atualização mensal)",
            "granularidade": "rebanho/produto × município × ano",
        },
    ),
    Banco(
        id="sefaz_nf",
        short="SEFAZ NFe",
        label="SEFAZ · Fluxos de Notas Fiscais Eletrônicas",
        sub="Comércio interno brasileiro reconstruído a partir de NFe inter-estaduais",
        about=(
            "Reconstrói o comércio interno brasileiro a partir das Notas Fiscais Eletrônicas, "
            "registrando operações de compra e venda entre estados e municípios. Trará uma visão "
            "de alta granularidade da movimentação econômica e fiscal — banco ainda em "
            "planejamento."
        ),
        domain="Comércio interno",
        scope="UF ↔ UF · município ↔ município",
        source="Receita · SEFAZ",
        table="gold_nfe_flows",
        provides=("product", "geo", "flow", "partner", "monthly", "quality"),
        base_currency="BRL",
        geo_level="municipio",
        dimensions={**_UF_DIMS, "product": {"codeLabel": "Código NCM"}},
        cobertura={
            "years": "2010 → presente",
            "atualizacao": "diária (defasagem 24h)",
            "granularidade": "NCM × CFOP × par UF/município × dia",
        },
    ),
]

_BANCO_BY_ID = {b.id: b for b in BANCOS}


def banco_by_id(banco_id: str) -> Banco:
    """Resolve a banco by id, falling back to the first (PEVS)."""
    return _BANCO_BY_ID.get(banco_id, BANCOS[0])


def visible_bancos() -> list[Banco]:
    return [b for b in BANCOS if b.visible]


def canon_currency_for(banco_id: str) -> str:
    return banco_by_id(banco_id).base_currency or "BRL"


# ── View registry (perspectives) ─────────────────────────────────────────────


@dataclass(frozen=True)
class View:
    """An analytical perspective. ``status`` 'live' = built this milestone."""

    id: str
    label: str
    status: str  # 'live' | 'soon'
    requires: tuple[str, ...] = ()
    desc: str = ""
    exportable: bool = False
    self_data: bool = False
    cross_banco: bool = False
    curated: bool = False
    data_blocked: bool = False  # component ships but renders an honest placeholder (no source)
    sources: tuple[str, ...] = ()
    align: str = ""
    # group is attached after construction (see VIEW_BY_ID)
    group_id: str = ""
    group_label: str = ""


@dataclass(frozen=True)
class ViewGroup:
    id: str
    label: str
    hint: str
    views: tuple[View, ...]


# Status mirrors the frontend views.js: 'live' = a component exists and renders
# (real data OR an honest data-blocked placeholder); 'soon' = not built. All the
# generic, trade, productivity (#105), cross-source and curated views are now live;
# only cross_chain / cross_lag render honest in-product placeholders because they
# need sources this repo lacks (SEFAZ inter-UF flows, monthly PEVS) — they are
# 'live' here to match the frontend (the component ships), not because the data is.
VIEW_GROUPS: list[ViewGroup] = [
    ViewGroup(
        "aggregate",
        "Análise agregada",
        "cesta de produtos",
        (
            View(
                "overview",
                "Visão geral",
                "live",
                exportable=True,
                desc="Resumo consolidado: KPIs, série de valor, composição e distribuição "
                "geográfica resumida.",
            ),
            View(
                "value",
                "Valor e volume",
                "live",
                exportable=True,
                desc="Séries históricas de valor e quantidade da cesta, segregadas por "
                "família de unidades.",
            ),
            View(
                "rebanho",
                "Rebanho",
                "live",
                requires=("herd",),
                desc="O efetivo dos rebanhos (estoque em cabeças, por espécie). Exclusivo "
                "da Pesquisa da Pecuária Municipal (IBGE PPM) — cabeças não têm valor "
                "monetário e não se somam entre espécies.",
            ),
        ),
    ),
    ViewGroup(
        "product",
        "Análise por produto",
        "produto individual",
        (
            View(
                "product_profile",
                "Perfil do produto",
                "live",
                requires=("product",),
                exportable=True,
                desc="Mergulho em um único produto: série de valor e quantidade, preço "
                "médio implícito, participação na cesta e ranking de UFs.",
            ),
            View(
                "product_compare",
                "Comparativo entre produtos",
                "live",
                requires=("product",),
                exportable=True,
                desc="Selecione 2 a 4 produtos e compare: séries base 100, variação "
                "acumulada, CAGR e correlação cruzada.",
            ),
            View(
                "productivity",
                "Produtividade",
                "live",
                requires=("yield",),
                exportable=True,
                self_data=True,
                desc="Rendimento (kg/ha) e área colhida por lavoura. Disponível para bancos "
                "de produção agrícola (IBGE PAM).",
            ),
        ),
    ),
    ViewGroup(
        "flows",
        "Análise de fluxos",
        "origem → destino",
        (
            View(
                "flows_territorial",
                "Fluxos territoriais",
                "live",
                requires=("flow",),
                self_data=True,
                desc="Diagrama Sankey origem → destino da cadeia comercial.",
            ),
            View(
                "flows_partners",
                "Parceiros comerciais",
                "live",
                requires=("partner",),
                self_data=True,
                desc="Rankings de UFs e países parceiros e fluxos bilaterais.",
            ),
        ),
    ),
    ViewGroup(
        "distribution",
        "Análise de distribuição",
        "espacial",
        (
            View(
                "geo",
                "Geografia",
                "live",
                requires=("geo",),
                exportable=True,
                desc="Distribuição territorial por valor, massa e volume, em região, UF ou "
                "município. Mapas, mapas de calor e rankings.",
            ),
            View(
                "concentration",
                "Concentração e desigualdade",
                "live",
                exportable=True,
                desc="Curva de Lorenz, índice de Gini e HHI por geografia e por produto.",
            ),
        ),
    ),
    ViewGroup(
        "temporal",
        "Análise temporal",
        "ciclos",
        (
            View(
                "seasonality",
                "Sazonalidade e tendências",
                "live",
                requires=("monthly",),
                self_data=True,
                desc="Mapa de calor mês × ano, decomposição e quebras "
                "estruturais. Requer dados mensais (MDIC, SEFAZ).",
            ),
        ),
    ),
    ViewGroup(
        "crosssource",
        "Análise cruzada",
        "entre bancos",
        (
            View(
                "cross_source",
                "Cruzamento entre fontes",
                "live",
                cross_banco=True,
                align="eixo temporal (ano)",
                desc="Compare séries anuais de bancos diferentes no mesmo eixo de tempo.",
            ),
            View(
                "cross_export_coef",
                "Coeficiente de exportação",
                "live",
                cross_banco=True,
                align="UF × ano",
                sources=("ibge_pevs", "mdic_comex"),
                desc="Quanto do que cada UF produz (IBGE) segue para exportação (MDIC).",
            ),
            View(
                "cross_market_share",
                "Brasil no mercado mundial",
                "live",
                cross_banco=True,
                align="eixo temporal (ano)",
                sources=("mdic_comex", "un_comtrade"),
                desc="Exportação brasileira como fração da exportação mundial (UN Comtrade).",
            ),
            View(
                "cross_price_spread",
                "Preço: porteira vs. FOB",
                "live",
                cross_banco=True,
                align="eixo temporal (ano)",
                sources=("ibge_pevs", "mdic_comex"),
                desc="Preço implícito na produção (IBGE) contra o preço FOB (MDIC).",
            ),
            View(
                "cross_mirror",
                "Espelho comercial",
                "live",
                cross_banco=True,
                align="eixo temporal (ano)",
                sources=("mdic_comex", "un_comtrade"),
                desc="A mesma exportação vista por MDIC, Comtrade e parceiros.",
            ),
            View(
                # Component ships but the data is blocked (needs SEFAZ inter-UF flows
                # + monthly PEVS this repo lacks) → renders an honest placeholder.
                "cross_chain",
                "Balanço da cadeia",
                "live",
                cross_banco=True,
                data_blocked=True,
                align="balanço físico (massa)",
                sources=("ibge_pevs", "sefaz_nf", "mdic_comex", "un_comtrade"),
                desc="Balanço de oferta reconciliado em massa, da produção ao mercado mundial.",
            ),
            View(
                # Data-blocked (needs monthly PEVS) → honest placeholder, like cross_chain.
                "cross_lag",
                "Defasagem safra → embarque",
                "live",
                cross_banco=True,
                data_blocked=True,
                align="mês (intra-anual)",
                sources=("ibge_pevs", "mdic_comex"),
                desc="Quantos meses os embarques (MDIC) seguem o pico da safra (IBGE).",
            ),
        ),
    ),
    # ─── "Análises curadas" (Engenharia de Atributos — UNFROZEN) ─────────────────
    # Live in the topnav (mirrors the frontend views.js). Fed by the researcher-editable
    # attribute-engineering classifications (per-code industrialization → Valor agregado;
    # regime×flow market-nature → Finalidade econômica), gated by the enable_curation dbt var.
    ViewGroup(
        "curated",
        "Análises curadas",
        "enriquecidas",
        (
            View(
                "curated_value_added",
                "Valor agregado",
                "live",
                cross_banco=True,
                curated=True,
                align="nível de industrialização",
                sources=("mdic_comex", "un_comtrade"),
                desc="Exportação separada entre bruta e processada, da classificação curada.",
            ),
            View(
                "curated_market_nature",
                "Finalidade econômica",
                "live",
                cross_banco=True,
                curated=True,
                align="finalidade (consumo/processamento)",
                sources=("mdic_comex", "un_comtrade"),
                desc="Valor comercializado por finalidade econômica (consumo × processamento).",
            ),
        ),
    ),
    ViewGroup(
        "documentation",
        "Documentação do banco",
        "metadados",
        (
            View(
                "quality",
                "Qualidade dos dados",
                "live",
                requires=("quality",),
                exportable=True,
                desc="Diagnóstico do data_quality_flag: distribuição de flags e qualidade "
                "por produto e UF.",
            ),
            View(
                "dados",
                "Estrutura de dados",
                "live",
                desc="A estrutura por trás do banco: percorra as tabelas de cada camada do "
                "pipeline (Bronze → Silver → Gold → Serving) e investigue qualquer uma linha a "
                "linha, com paginação, ordenação e filtros por coluna. Para conferir os dados ou "
                "rastrear de onde vem cada número.",
            ),
            View(
                "glossary",
                "Glossário",
                "live",
                desc="Termos, códigos e colunas do banco selecionado.",
            ),
        ),
    ),
]

# Flattened lookup, with group context attached.
VIEW_BY_ID: dict[str, View] = {}
for _g in VIEW_GROUPS:
    for _v in _g.views:
        # rebuild with group context (frozen dataclass → use replace-like dict)
        VIEW_BY_ID[_v.id] = View(**{**_v.__dict__, "group_id": _g.id, "group_label": _g.label})


def view_by_id(view_id: str) -> View | None:
    return VIEW_BY_ID.get(view_id)


def view_label(view_id: str) -> str:
    v = VIEW_BY_ID.get(view_id)
    return v.label if v else view_id


def is_view_live(view_id: str) -> bool:
    v = VIEW_BY_ID.get(view_id)
    return bool(v and v.status == "live")


def view_applies_to(view_id: str, banco_id: str) -> tuple[bool, list[str]]:
    """(applies, missing_caps) — does the view work for the banco?

    Cross-source perspectives operate across bancos → always apply.
    """
    v = VIEW_BY_ID.get(view_id)
    b = banco_by_id(banco_id)
    if not v:
        return (True, [])
    if v.cross_banco:
        return (True, [])
    missing = [c for c in v.requires if c not in b.provides]
    return (len(missing) == 0, missing)


def bancos_supporting(view_id: str) -> list[Banco]:
    """Which visible bancos satisfy a view's required capabilities."""
    v = VIEW_BY_ID.get(view_id)
    if not v:
        return []
    return [b for b in visible_bancos() if all(c in b.provides for c in v.requires)]


def missing_caps_label(missing: list[str]) -> str:
    return " · ".join(CAPABILITIES.get(c, {}).get("label", c) for c in missing)


# ── Filter schema (per-banco filterable dimensions) ──────────────────────────
# Value-range quick presets — single source for the FilterMenu shortcuts and the
# row-counter heuristic. ``row_share`` only scales the "Linhas" provenance count.
VALUE_PRESETS: list[dict] = [
    {"id": "none", "min": None, "max": None, "suffix": None, "row_share": 1.00},
    {"id": "1k", "min": 1_000, "max": None, "suffix": "1 mil", "row_share": 0.81},
    {"id": "10k", "min": 10_000, "max": None, "suffix": "10 mil", "row_share": 0.52},
    {"id": "100k", "min": 100_000, "max": None, "suffix": "100 mil", "row_share": 0.18},
    {"id": "1M", "min": 1_000_000, "max": None, "suffix": "1 mi", "row_share": 0.04},
]

TIER_LABEL = {
    "universal": "Universal",
    "shared": "Compartilhada",
    "specific": "Específica do banco",
}

FILTER_SCHEMAS: dict[str, dict] = {
    "ibge_pevs": {
        "table": "gold_pevs_production",
        "dims": [
            {
                "id": "produtos",
                "num": "01",
                "tier": "shared",
                "type": "products",
                "label": "Produtos · PEVS",
                "column": "product_code",
                "hint": "Commodities da extração vegetal (floresta nativa).",
            },
            {
                "id": "nivel",
                "num": "02",
                "tier": "shared",
                "type": "multi",
                "label": "Nível de industrialização",
                "column": "industrialization_level",
                "hint": "Do bruto ao manufaturado, pela classificação curada de cada código.",
            },
            {
                "id": "origem",
                "num": "02",
                "tier": "specific",
                "type": "segment",
                "label": "Origem da produção",
                "column": "origem",
                "hint": (
                    "Metade da pesquisa: extração de floresta nativa ou silvicultura (plantada)."
                ),
            },
            {
                "id": "periodo",
                "num": "03",
                "tier": "universal",
                "type": "period-value",
                "label": "Período & faixa de valor",
                "column": "reference_year · val_real_ipca_brl",
                "hint": "Janela temporal e corte por valor monetário da linha.",
            },
            {
                "id": "geografia",
                "num": "03",
                "tier": "shared",
                "type": "geo-cascade",
                "label": "Geografia",
                "column": "state_acronym",
                "hint": "Cascata nação ▸ região ▸ estado.",
            },
            {
                "id": "qualidade",
                "num": "04",
                "tier": "specific",
                "type": "flags",
                "label": "Qualidade dos dados",
                "column": "data_quality_flag",
                "hint": "Bandeira de qualidade por linha.",
            },
        ],
    },
    "mdic_comex": {
        "table": "gold_comex_flows",
        "dims": [
            {
                "id": "periodo",
                "tier": "universal",
                "type": "date-range",
                "label": "Período",
                "column": "reference_year",
                "hint": "Mensal, de 1997 ao presente.",
            },
            {
                "id": "ncm",
                "tier": "shared",
                "type": "multi-tree",
                "label": "Produto · NCM / SH",
                "column": "ncm_code",
                "hint": "Hierarquia SH2 ▸ SH4 ▸ SH6 ▸ NCM 8 dígitos.",
            },
            {
                "id": "uf_origem",
                "tier": "shared",
                "type": "multi",
                "label": "UF de origem",
                "column": "state_acronym",
                "hint": "Unidade da federação do exportador.",
            },
            {
                "id": "fluxo",
                "tier": "specific",
                "type": "segment",
                "label": "Fluxo",
                "column": "flow",
                "options": ["Exportação", "Importação"],
                "hint": "Direção da operação.",
            },
            {
                "id": "valor",
                "tier": "universal",
                "type": "value-range",
                "label": "Faixa de valor (FOB)",
                "column": "val_yearfx_usd",
                "hint": "Corte por valor FOB em dólares.",
            },
        ],
    },
    "un_comtrade": {
        "table": "gold_comtrade_flows",
        "dims": [
            {
                "id": "periodo",
                "tier": "universal",
                "type": "date-range",
                "label": "Período",
                "column": "reference_year",
                "hint": "Anual, de 1989 ao presente.",
            },
            {
                "id": "hs6",
                "tier": "shared",
                "type": "multi-tree",
                "label": "Produto · HS6",
                "column": "cmd_code",
                "hint": "Sistema Harmonizado a 6 dígitos.",
            },
            {
                "id": "flow",
                "tier": "specific",
                "type": "segment",
                "label": "Fluxo",
                "column": "flow",
                "options": ["Export", "Import", "Re-export", "Re-import"],
                "hint": "Direção do fluxo internacional.",
            },
            {
                "id": "valor",
                "tier": "universal",
                "type": "value-range",
                "label": "Faixa de valor (US$)",
                "column": "val_yearfx_usd",
                "hint": "Corte por valor declarado.",
            },
        ],
    },
}


def filter_schema_for(banco_id: str) -> dict:
    return FILTER_SCHEMAS.get(banco_id, FILTER_SCHEMAS["ibge_pevs"])
