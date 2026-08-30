-- Curation surface (WARN, not error): quantity readings that carry a value but
-- could NOT be normalised to a family base unit (qty_base IS NULL while a
-- qty_native exists). We never invent a conversion, so these rows ship with
-- qty_base NULL; este teste as mantém visíveis em vez de deixá-las sumir.
--
-- TRÊS causas, e só as duas primeiras são acionáveis:
--   1. family = 'desconhecida' COM `unit_native` preenchida — a unidade da fonte não
--      está nas 5 famílias; acrescente uma linha em unit_family_conversions (ou decida
--      que está genuinamente fora de escopo).
--   2. uma unidade de commodity (saca/@/bushel/barril) sem linha em
--      product_unit_factors — forneça o to_base por produto.
--   3. ⚠ `unit_native` NULA — a fonte informou um número de quantidade e NENHUMA
--      unidade. Não é unidade não mapeada, é unidade AUSENTE: nenhuma tabela de
--      conversão resolve, e inventar uma seria inventar o dado. O tratamento correto é
--      o que já acontece (qty_base nulo, então a linha nunca entra num agregado).
--      É o ÚNICO caso que dispara hoje: 871 linhas de gold_comtrade_flows com
--      family='desconhecida' e unit_native nula (medido 2026-08-30, 0,04% do banco).
--      Uma versão anterior deste comentário listava só as duas primeiras causas e
--      mandava o operador atrás de uma linha de conversão que não existiria.
--
-- Ao ler o resultado: separe pelas colunas. `unit_native` preenchida = trabalho de
-- curadoria; `unit_native` nula = limitação da fonte, nada a fazer.
{{ config(severity='warn') }}

select 'gold_pevs_production' as model, family, unit_native, count(*) as n
from {{ ref('gold_pevs_production') }}
where qty_native is not null and qty_base is null
group by 1, 2, 3

union all

select 'gold_comex_flows' as model, family, unit_native, count(*) as n
from {{ ref('gold_comex_flows') }}
where qty_native is not null and qty_base is null
group by 1, 2, 3

union all

-- PPM spans contagem/volume/massa via the generic seed (arguably the most exposed to
-- an unmapped unit); COMTRADE degrades an unknown qty_unit_code to 'desconhecida' with
-- a NULL base. Both carry qty_native/qty_base, so surface their unconvertible rows on
-- the same curation worklist (DBT-2).
select 'gold_ppm_production' as model, family, unit_native, count(*) as n
from {{ ref('gold_ppm_production') }}
where qty_native is not null and qty_base is null
group by 1, 2, 3

union all

select 'gold_comtrade_flows' as model, family, unit_native, count(*) as n
from {{ ref('gold_comtrade_flows') }}
where qty_native is not null and qty_base is null
group by 1, 2, 3

union all

-- PAM shares the same unit-family seed path (the monetary + family-coherence tests
-- already cover it), so include it on the curation worklist too. Vacuous today (PAM's
-- only quantity unit is Toneladas, always convertible) but a future SIDRA 5457 revision
-- reporting an unmapped unit would otherwise produce a qty_native-not-null/qty_base-NULL
-- row that no curation surface catches (DBT-5).
select 'gold_pam_production' as model, family, unit_native, count(*) as n
from {{ ref('gold_pam_production') }}
where qty_native is not null and qty_base is null
group by 1, 2, 3
