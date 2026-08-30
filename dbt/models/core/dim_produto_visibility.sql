{{ config(materialized='view') }}

-- ────────────────────────────────────────────────────────────────────────────
-- dim_produto_visibility — the HIDDEN-prefix registry for the Ciclo de Vida
-- visibility gate (F7).
--
-- A researcher can set a commodity's VISIBILIDADE to 'oculto': keep its data in Gold but
-- HIDE the commodity from the dashboard. (Visibility is now its own axis, independent of
-- INGESTAO — a paused produto stays visible unless it is also hidden. Rows written before
-- the split carry the retired `ciclo_de_vida` prose and are translated by the
-- catalog_visibilidade macro, the single place that knows that mapping.)
-- This view emits ONLY the (source, code) of such hidden commodities
-- (the exact codigo_produto; latest-wins, active). The gate is a NOT EXISTS predicate
-- over this view (see macros/hidden_code_predicate.sql + serving/sql.visibility_clause):
-- a Gold code with NO row here stays visible — so PPM (no catalog rows) and any
-- code outside the catalog are unaffected.
--
-- Kept SEPARATE from dim_produto_catalog ON PURPOSE: the Curadoria admin editor,
-- the orphan/lifecycle readers and gold_produto_agrupamento must still see a
-- hidden-but-active row (you have to be able to edit/un-hide it). The gate only
-- touches the RESEARCHER-facing Gold reads (marts, direct-Gold readers, cross-source
-- picker). `banco` is already the short source token (pevs/pam/ppm/comex/comtrade),
-- matching the Gold tables' source — verified on prod data.
--
-- Grain: one row per hidden (source, code). Empty when nothing is hidden
-- (the no-op steady state today: all active catalog rows are "deixar disponível").
-- ────────────────────────────────────────────────────────────────────────────

with current_catalog as (

    select
        banco           as source,
        codigo_produto,
        -- Parte da identidade do produto. O `partition by` abaixo funciona sem ela porque
        -- avalia sobre a tabela de origem; o SELECT final, não — ele lê desta CTE.
        -- Padrão do banco quando o log histórico não traz tabela (comex/comtrade/pam
        -- nasceram sem ela). ÚNICO ponto do projeto que trata a ausência; daqui para
        -- baixo o trio é NÃO-NULO em todas as camadas.
        {{ tabela_com_padrao('tabela', 'banco') }} as tabela,
        {{ catalog_visibilidade() }} as visibilidade_efetiva,
        active,
        -- Latest-wins per key; same tie-breaker note as dim_produto_catalog: a
        -- same-microsecond change_id tie is deterministic but not true write-order —
        -- unreachable for human edits, and the unique_combination(source, code, tabela) test on this
        -- model is the backstop. This ORDER BY is replicated across the serving readers.
        row_number() over (
            partition by {{ chave_produto() }}
            order by edited_at desc, change_id desc
        ) as _rn
    from {{ source('research_inputs', 'produto_catalog_log') }}

)

select
    source,
    codigo_produto as code,
    -- Ver dim_produto_catalog: parte da identidade do produto.
    tabela
from current_catalog
where _rn = 1
  and active
  and visibilidade_efetiva = 'oculto'
