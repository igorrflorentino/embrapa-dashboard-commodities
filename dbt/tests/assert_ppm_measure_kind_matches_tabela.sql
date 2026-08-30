-- `measure_kind` é DERIVADO da tabela, nunca um fato independente.
--
-- Ele é o gêmeo sobrevivente do `origem` que a v1.46.1 removeu: como aquele, mapeia 1-para-1
-- com a tabela (3939 → stock, 74 → flow). A auditoria de 2026-08-30 decidiu MANTÊ-LO, por
-- uma diferença real — `origem` era só outro nome para a tabela, enquanto stock/flow é uma
-- REGRA DE AGREGAÇÃO (um estoque não se soma ao longo de anos). Trocá-lo por
-- `tabela = '3939'` vazaria um id de tabela SIDRA para dentro de cada ramo de UI, e
-- quebraria no dia em que outro banco tiver estoques.
--
-- O que torna a decisão segura é ele ser derivado (`silver_ibge_ppm` o calcula com um
-- `case` sobre a tabela) e não autônomo. Este teste é o que impede que volte a ser
-- autônomo: se alguém passar a gravá-lo à mão, ou trocar o `case`, os dois divergem e o
-- build para. Sem ele, a decisão de manter dependeria de ninguém mexer.
--
-- Falha (devolve linhas) se algum par (tabela, measure_kind) do Gold contradiz o mapa.

select
    tabela,
    measure_kind,
    count(*) as n
from {{ ref('gold_ppm_production') }}
where measure_kind != case
        when tabela = '{{ var("ppm_herd_table_id") }}' then 'stock'
        else 'flow'
    end
group by tabela, measure_kind
