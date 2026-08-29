-- Singular test: the two PEVS Silvers must stay COLUMN-IDENTICAL.
--
-- gold_pevs_production unions them POSITIONALLY (`select 'x' as origem, * from …` twice).
-- Positional union is the right shape here — one model is a literal mirror of the other —
-- but it fails in the worst possible way if they ever drift: a column added to one and not
-- the other shifts every field after it, so values land in the WRONG COLUMNS and the build
-- still succeeds. No row count changes, no test on either model alone notices, and the
-- numbers are simply wrong from then on.
--
-- Compares name AND ordinal position AND type. A mismatch in any of the three is enough to
-- misalign the union, so all three are the invariant, not just the set of names.
--
-- Fails (returns a row) per column that exists in one and not the other, or that sits at a
-- different position / carries a different type.

with pevs as (
    select column_name, ordinal_position, data_type
    from {{ ref("silver_ibge_pevs").schema }}.INFORMATION_SCHEMA.COLUMNS
    where table_name = '{{ ref("silver_ibge_pevs").identifier }}'
),

silvicultura as (
    select column_name, ordinal_position, data_type
    from {{ ref("silver_ibge_silvicultura").schema }}.INFORMATION_SCHEMA.COLUMNS
    where table_name = '{{ ref("silver_ibge_silvicultura").identifier }}'
)

select
    coalesce(p.column_name, s.column_name)                  as column_name,
    p.ordinal_position                                      as pevs_position,
    s.ordinal_position                                      as silvicultura_position,
    p.data_type                                             as pevs_type,
    s.data_type                                             as silvicultura_type
from pevs p
full outer join silvicultura s
    on p.column_name = s.column_name
where p.column_name is null
   or s.column_name is null
   or p.ordinal_position != s.ordinal_position
   or p.data_type != s.data_type
