-- Os marts que juntam o catálogo assumem UMA linha de dim por (source, código).
--
-- `serving_pam_annual` junta `dim_produto_catalog` por `(source, codigo_produto)` — sem a
-- tabela SIDRA, e ali isso NÃO é suposição: o PAM é banco de tabela única (5457), então um
-- código não pode aparecer duas vezes na dim.
--
-- O `serving_ppm_annual` juntava do mesmo jeito, e ali ERA suposição — o Gold carregava um
-- discriminador semântico (`measure_kind`) e não o id da tabela, então escrever o
-- mapeamento `stock↔3939 / flow↔74` no join teria sido uma quarta cópia de uma decisão que
-- já vive no `.env`, no validador da curadoria e no registro do doctor. Desde v1.46.0 o id
-- viaja no fato e aquele join usa a chave inteira.
--
-- Desde v1.39.0 a dim tem grão (codigo_produto, source, sidra_tabela), então um código
-- presente nas DUAS tabelas de um banco multi-tabela devolveria DUAS linhas — e o join
-- faria fan-out, DUPLICANDO os valores do fato. Silenciosamente: nenhum erro, só números
-- dobrados num mart.
--
-- Este teste transforma esse silêncio em falha alta. Se ele acender, o conserto NÃO é
-- afrouxá-lo: é dar ao join a tabela (via um macro que centralize o mapeamento) ou decidir
-- que aquele código não deve existir nas duas metades. `embrapa doctor` → `shared-code`
-- avisa antes, no Gold, sem depender de um build.

select source, codigo_produto, count(*) as linhas
from {{ ref('dim_produto_catalog') }}
where source in ('pam', 'ppm')
group by source, codigo_produto
having linhas > 1
