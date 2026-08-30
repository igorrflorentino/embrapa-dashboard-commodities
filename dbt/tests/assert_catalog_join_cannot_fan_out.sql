-- Os marts que juntam o catálogo assumem UMA linha de dim por (source, código).
--
-- `serving_pam_annual` e `serving_ppm_annual` juntam `dim_produto_catalog` por
-- `(source, codigo_produto)` — sem a tabela SIDRA, porque o Gold desses bancos carrega um
-- discriminador SEMÂNTICO (`measure_kind` no PPM, `origem` no PEVS) e não o id da tabela.
-- Escrever o mapeamento `stock↔3939 / flow↔74` no join criaria uma QUARTA cópia de uma
-- decisão que já vive no `.env`, no validador da curadoria e no registro do doctor.
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
