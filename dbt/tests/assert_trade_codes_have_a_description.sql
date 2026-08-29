-- Every code that actually reaches Gold must be NAMEABLE.
--
-- `ncm_description` / `cmd_description` come from hand-curated seeds (comex_ncm,
-- comtrade_hs) via a LEFT JOIN, and both columns are documented as "NULL if outside the
-- seeded scope". That is true and, on its own, silent: a code ingested but absent from the
-- seed carries data through every chart while the Curadoria editor shows "—" for its name,
-- which only a human reading that screen would ever notice. It happened to 5 codes
-- (14011000, 15079010, 20059100, 140110, 200591 — measured 2026-08-29), two of which sit in
-- a chapter the seed's filter never listed (14, bambu).
--
-- The seed does NOT have to cover the whole NCM/HS universe — only what the pipeline
-- actually ingested. So the test compares the seed against the DATA, not against the
-- nomenclature: it fails exactly when a code arrives that nobody can name.
--
-- Fix a failure by adding the code to the seed with its OFFICIAL Portuguese description,
-- from MDIC's own table (https://balanca.economia.gov.br/balanca/bd/tabelas/NCM.csv,
-- column NO_NCM_POR) — never a description written from memory.

select 'comex' as banco, ncm_code as code
from {{ ref('gold_comex_flows') }}
group by 1, 2
having count(distinct ncm_description) = 0

union all

select 'comtrade' as banco, cmd_code as code
from {{ ref('gold_comtrade_flows') }}
group by 1, 2
having count(distinct cmd_description) = 0
