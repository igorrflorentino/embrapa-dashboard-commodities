{{ config(materialized='table') }}

-- ────────────────────────────────────────────────────────────────────────────
-- gold_produto_agrupamento — cross-source product bridge (RESOLVED to exact codes).
--
-- The same physical commodity wears a different code in each source: PEVS uses
-- an extractive-product code, COMEX an 8-digit NCM, COMTRADE a 6-digit HS. Every
-- cross-source analysis (export coefficient, world market share, price spread,
-- trade mirror, harvest→shipment lag) must join the SAME commodity across them —
-- and that link is domain knowledge, not a SELECT DISTINCT.
--
-- The editable Curadoria catalog registers each commodity by its EXACT source code
-- (`codigo_produto`; no prefixes). This model joins those codes to the codes that
-- actually appear in each Gold fact table, emitting exact (source, code) → commodity
-- rows so a consumer joins on equality. A Gold code not in the catalog is simply
-- absent here → "unlinked" (graceful degradation), never an error.
--
-- Grain: one row per (source, code, tabela) — o TRIO, como em todo o projeto.
--
-- ⚠ INVARIANT (load-bearing): `(codigo_produto, source, tabela)` é único no catálogo, e o
-- join abaixo casa o TRIO INTEIRO, então um código do Gold resolve para NO MÁXIMO um
-- agrupamento_id — o LEFT JOIN cross-source das marts não pode FANAR OUT e dobrar somas de
-- qty_base/val_*. Até v1.46.9 este texto afirmava que `(codigo_produto, source)` era único
-- no catálogo: não era (o teste do catálogo sempre foi sobre o trio), e o join casava só o
-- par — um código nas duas tabelas de um banco, com agrupamentos diferentes, teria dobrado
-- as somas. O `unique_combination_of_columns` sobre (source, code, tabela) em _gold.yml é a
-- guarda de build, e `assert_serving_conserved_gold` é a guarda de valor.
-- ────────────────────────────────────────────────────────────────────────────

with xwalk as (

    -- The editable Curadoria catalog (dim_produto_catalog), the SOT that replaced
    -- the commodity_crosswalk seed. Each row is one exact (source, codigo_produto).
    -- A produto registered WITHOUT an agrupamento (agrupamento_id null) can't be
    -- cross-linked, so it is excluded from the crosswalk — matching the serving
    -- layer's produto_catalog() skip. Keeps agrupamento_id/_nome NOT NULL here (and
    -- those produtos still appear in single-banco views via gold_<source>_production).
    select agrupamento_id, agrupamento_nome, source, codigo_produto, tabela
    from {{ ref('dim_produto_catalog') }}
    where agrupamento_id is not null

),

source_codes as (

    -- PAM and PPM joined the bridge in 2026-08 (the coordinated change this note
    -- used to reserve: union below + accepted_values in _gold.yml + the buckets in
    -- webapi/seam_base.produto_catalog, which would KeyError on an unknown source).
    --
    -- It changes NO existing computation: every cross-source view asks for its
    -- sources BY NAME (seam_base._codes(agrupamento_id, 'pevs') for the export
    -- coefficient, 'comex'/'comtrade' for market share), so nothing sums across
    -- production sources behind the researcher's back. What it adds is CHOICE —
    -- the multi-fonte picker is series-oriented, so PAM/PPM simply become series a
    -- researcher can place on the axis next to PEVS, and decide for themselves
    -- whether extractive and cultivated output belong side by side or added up.
    -- An aggregate "extractive + cultivated" metric, if ever wanted, must be its
    -- own NAMED metric — never a silent change to an existing denominator.
    select distinct 'pevs' as source, product_code as code, tabela
    from {{ ref('gold_pevs_production') }}
    union all
    select distinct 'pam' as source, product_code as code, tabela
    from {{ ref('gold_pam_production') }}
    union all
    select distinct 'ppm' as source, product_code as code, tabela
    from {{ ref('gold_ppm_production') }}
    union all
    select distinct 'comex' as source, ncm_code as code, tabela
    from {{ ref('gold_comex_flows') }}
    union all
    select distinct 'comtrade' as source, cmd_code as code, tabela
    from {{ ref('gold_comtrade_flows') }}

)

select distinct
    x.agrupamento_id,
    x.agrupamento_nome,
    c.source,
    c.code,
    c.tabela
from source_codes c
join xwalk x
    on c.source = x.source
    and c.code = x.codigo_produto
    -- A TABELA entra no join (v1.47.0). Sem ela o join casava `(source, code)` contra um
    -- catálogo que é único no TRIO: um código nas duas tabelas de um banco, com
    -- agrupamentos diferentes, FANARIA OUT e dobraria as somas de qty_base/val_*. O
    -- cabeçalho deste modelo declarava como invariante que `(codigo_produto, source)` era
    -- único no catálogo — não era, e é essa a correção.
    and c.tabela = x.tabela
