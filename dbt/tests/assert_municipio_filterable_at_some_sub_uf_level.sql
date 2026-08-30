-- Todo município tem de ser filtrável em ALGUM nível sub-UF. Este é o invariante que o
-- produto realmente usa (a cascata de geografia), e substitui os `not_null` que ficavam
-- em `meso_code`/`micro_code` no seed.
--
-- Por que a troca (v1.46.9). O IBGE mantém DUAS divisões sub-UF que não se aninham: a
-- clássica de 1990 (mesorregião → microrregião), CONGELADA, e a de 2017 (região
-- intermediária → imediata), VIVA. Um município criado depois de 2017 nunca recebe a
-- clássica. Os `not_null` antigos avisavam para sempre sobre 5101837 · Boa Esperança do
-- Norte (MT), que tem a divisão moderna completa e é plenamente filtrável — um aviso que
-- nenhuma ação resolve. Ruído permanente tratado como pendência treina a ignorar avisos,
-- que é o defeito que a v1.46.4 corrigiu no `doctor`.
--
-- A pergunta certa não é "tem meso?" e sim "dá para filtrar este município?". Um município
-- que perdesse AS DUAS divisões sumiria da cascata sub-UF sem que nada quebrasse — é
-- exatamente esse silêncio que este teste fecha, e nenhum `not_null` por coluna o
-- alcançava: cada um olhava a sua coluna, e a condição é sobre a combinação.
--
-- WARN (não error): um município fora da cascata degrada a navegação daquele lugar, mas
-- não corrompe número nenhum — o mesmo critério dos irmãos em `intermediaria_code` /
-- `imediata_code`, que seguem com `not_null` porque a divisão viva deve cobrir todos.
--
-- Falha (devolve linhas) se um município não tem NENHUM par completo.

{{ config(severity='warn') }}

select
    city_code,
    city_name,
    state_acronym,
    meso_code,
    micro_code,
    intermediaria_code,
    imediata_code
from {{ ref('ibge_municipio_mesh') }}
where (meso_code is null or micro_code is null)
  and (intermediaria_code is null or imediata_code is null)
