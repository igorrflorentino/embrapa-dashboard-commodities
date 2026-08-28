# COMTRADE — todos os fluxos, regime aduaneiro e tipo de mercado

> ⚠️ **Status: CONGELADO — não implementar a partir deste plano.** O que está congelado é o
> eixo **tipo de mercado** (natureza de mercado por regime × fluxo), não a Engenharia de
> Atributos inteira: o outro eixo dela, **nível de industrialização, está no ar e
> funcionando** (editor na barra lateral, view *Valor agregado* live, 303 classificações em
> 5 níveis em prod). A entrada de UI deste eixo é que está comentada, e
> `serving_comtrade_annual.market_nature` tem 0 valores distintos (PRs #168/#169).
> Dois dos três objetivos abaixo estão **bloqueados por dado**:
>
> - **Regime aduaneiro** e **tipo de mercado** dependem da dimensão de procedimento
>   aduaneiro, que a base **não tem**: desde o redesenho *totals-only* da v1.13.0 a
>   ingestão pede `customsCode=C00` (só os totais) para manter a base homogênea e evitar
>   duplas contagens, e o detalhe por regime é ausente na maioria dos países reportantes.
> - Só o objetivo (1) — **todos os tipos de fluxo** — é alcançável com o dado atual, e
>   mesmo assim a base hoje ingere apenas `X`/`M`.
>
> O texto abaixo é preservado como o **desenho**, não como uma fila de trabalho: ele
> continua correto sobre o que seria preciso, e é o ponto de partida se algum dia a fonte
> passar a reportar o detalhe. Antes de retomar, releia o `CLAUDE.md` (§ Engenharia de
> Atributos) e o cabeçalho de `docs/comtrade_world_backfill.md`.

**Objetivo.** Habilitar, no banco `un_comtrade`, os filtros de: (1) **todos os tipos de fluxo**
(os 10 regimes de comércio do UN Comtrade), (2) **regime aduaneiro** (`customsCode`), e (3) **tipo
de mercado** (natureza derivada pela Engenharia de Atributos). Ver o diagnóstico de origem em
`memory/audit_2026_07_01_filter_menu.md` (perguntas de fluxo/regime/mercado do usuário).

> **Regra de ouro deste plano:** um filtro só funciona quando **4 camadas concordam** — ingestão,
> Silver/Gold, backend serving e frontend. Cada fase abaixo alinha uma camada.

---

## 0. Realidade dos dados (medida em prod, 2026-07)

Números reais que **decidem o valor** de cada eixo (não o custo de nuvem, que é desprezível):

| Fato | Medida |
|---|---|
| Tamanho da linhagem Comtrade | Bronze 1,18 GB · Gold 0,84 GB · serving 0,79 GB (**< 3 GB total**) |
| Fluxos **ingeridos hoje** | 4 de 10 — `X,M,RX,RM` (config `COMTRADE_FLOWS`) |
| Fluxos no Gold | export 1,0M · import 1,2M · re-export 35,7k · re-import 5,2k linhas |
| **Regime aduaneiro** — % das linhas com detalhe (não-C00) | **13,9% global**; C00 = 86,1% |
| Regime p/ produtos agrícolas-alvo | madeira(44) 15,2% · castanha(08) 13,7% · cereais(10) 11,4% · oleaginosas(12) 11,0% · hortícolas(07) 10,3% · óleos(15) 8,7% |
| Regimes distintos observados | ~12 (`C00` total + `C01/C03/C20` dominam os breakdowns) |
| **Scoping do dashboard** | **fixado em Brasil como reporter** (`reporter_code='76'`) — por isso `re-export` fica VAZIO (o Brasil não reporta reexportação; global tem $29 bi, Brasil-reporter = NULL) |

**Conclusão de custo:** armazenamento/computação são desprezíveis (dentro da faixa gratuita do
BigQuery mesmo dobrando a linhagem). O limitante é **esforço** + **esparsidade** (regime/mercado
nascem ~85% no balde "C00/total"). O usuário decidiu prosseguir ciente disso → construir com
**empty-states honestos** e default "C00 = todos os regimes".

**Decisão de produto pendente (importante):** o scoping Brasil-reporter faz `re-export` (e vários
regimes de aperfeiçoamento) serem estruturalmente vazios. Se o pesquisador quiser ver reexportação
*mundial*, é preciso **des-fixar o reporter** — decisão maior, fora deste plano. Documentar no UI
que o recorte é "Brasil como declarante".

---

## Fases

### ✅ Fase 1 — Consertar os 4 fluxos já ingeridos (FEITO)

O bug: frontend enviava `re_export` (underscore), dado usa `re-export` (hífen), e o backend
`_ALLOWED_FLOWS` só aceitava export/import/all → selecionar Re-export/Re-import dava `400 fluxo
inválido`. Corrigido alinhando tudo ao token do dado (hífen):

- `webapi/routes.py` — `_ALLOWED_FLOWS` += `re-export`, `re-import`.
- `ui/filtersSchema.js` — `FLOW_OPTIONS.un_comtrade` valores → `re-export`/`re-import` (labels
  pt-BR Reexportação/Reimportação).
- Testes: `tests/test_webapi_routes.py::test_reexport_reimport_flows_are_accepted` +
  `filtersSchema.test.js` (hífen, não underscore).
- **Verificado live:** re-import renderiza dados reais do Brasil; re-export vazio corretamente.

### Fase 2 — Ingestão: baixar os 6 fluxos restantes  *(OPERATOR-GATED)*

Os regimes `DX, FM, MIP, MOP, XIP, XOP` **não estão no Bronze** — exigem re-download.

- `config.py` — `comtrade_flows` default `X,M,RX,RM` → `X,M,RX,RM,DX,FM,MIP,MOP,XIP,XOP`;
  atualizar o validador `comtrade_flows_list` (allowed set) e a mensagem de erro.
- `comtrade/client.py` — nada estrutural (já envia `flowCode=",".join(flows)`); confirmar que a
  API keyed aceita os 10 códigos numa chamada.
- **Runbook do operador** (precisa `COMTRADE_API_KEY` + cota de vários dias):
  `uv run embrapa ingest comtrade --full` (ou o Job Cloud Run de backfill) com o novo
  `COMTRADE_FLOWS`. ⚠️ **Verificar antes** com um download-teste de 1 reporter/ano se os 6 códigos
  retornam linhas — na base anual HS eles costumam ser raros/vazios (risco de "opção que não
  funciona" de novo). Se vazios, **não** expô-los no filtro (ver Fase 6, opções data-driven).

### ✅ Fase 3 — Silver: preservar o regime aduaneiro + mapear os 10 fluxos (FEITO — v1.9.0, PR #189)

`dbt/models/silver/silver_comtrade_flows.sql`. **Já shipado:** o modelo preserva os breakdowns de
regime (`where customsCode != 'C00' or _regime_breakdown_rows = 0`, com a janela anti-double-count
`_regime_breakdown_rows`), emite `customs_code` como coluna dimensional (`customsCode as
customs_code`) e junta o seed de natureza de mercado (`on p.customs_code = mn.customs_code`). A
regra de grão **anti-double-count** que ficou implementada:

- Manter as linhas de breakdown (`customsCode != 'C00'`) **onde existem**, E manter a linha `C00`
  **apenas** para as chaves `(reporter,partner,cmd,flow,year)` que **não têm** nenhum breakdown
  (senão o C00 dupla-conta os breakdowns). Padrão: `qualify` / anti-join por chave agregada.
- `customs_code` passa a ser coluna dimensional (com um rótulo pt-BR via seed de referência dos
  ~12 códigos C0x — criar `seeds/comtrade_customs_procedures.csv`).
- Estender o `case flowCode` para os 10 códigos (mapear DX/FM/MIP/MOP/XIP/XOP a tokens legíveis
  estáveis — **decisão de token**: sugiro manter `re-export`/`re-import` e usar
  `national-export`/`foreign-import`/`import-inward-processing`/… para os demais).
- Manter mos/mot/partner2 ainda somados (só o regime é o eixo novo pedido).

### ✅ Fase 4 — Gold: carregar o regime no grão (FEITO — v1.9.0, PR #189)

**Já shipado:** `gold_comtrade_flows.sql` carrega `customs_code` no grão/GROUP BY.
`dbt/models/gold/gold_comtrade_flows.sql`. Adicionar `customs_code` (+ `customs_label`) ao
`partition_by`/`cluster_by` conceitual e a TODOS os `group by` (with_dominant, base_flows). O grão
passa de `(flow, year, reporter, partner, cmd)` para `(flow, customs_code, year, reporter,
partner, cmd)`. Impacto de linhas medido: **+~16%** (breakdowns são esparsos). Revisar o
`data_quality_flag` e a deflação (inalterados — operam por linha).

### ✅ Fase 5 — Serving marts: propagar regime + fluxos (FEITO — v1.9.0, PR #189)

**Já shipado:** `serving_comtrade_annual.sql` inclui `customs_code` no grão/GROUP BY.
`dbt/models/serving/serving_comtrade_annual.sql` (+ quaisquer marts Comtrade). Incluir
`customs_code` no grão do mart; garantir que o snapshot flow-agregado ainda soma corretamente
quando o regime não é filtrado (default = todos os regimes, inclui C00+breakdowns SEM dupla
contagem — porque a Fase 3 já garante que C00 e breakdown são mutuamente exclusivos por chave).

### Fase 6 — Backend: opções data-driven + filtros de regime e mercado

- **Fluxos data-driven:** em vez do `FLOW_OPTIONS` hardcoded, expor os fluxos **que existem no
  dado** via `/api/source-meta` (ex.: `available_flows`), para o menu nunca oferecer uma opção
  vazia. Backend: `_ALLOWED_FLOWS` derivado da mesma fonte (ou expandido para os 10 tokens).
- **Regime aduaneiro:** novo parâmetro `customs` (multi-valor, client-side ou server-side)
  em `serving/sql.py` (`_customs(conditions, params, customs)`), validado como `_flow_or_400`.
- **Tipo de mercado:** ligar `seam.market_nature` (já existe, `seam_attribute_engineering.py`)
  ao gateway; expor `/api/market-nature` já roteado quando descongelado.

### Fase 7 — Frontend: filtros de regime e mercado + empty-states

- `filtersSchema.js` — `un_comtrade`: novo dim `regime` (`type:'multi'`, `backed:true`) e
  `mercado` (`type:'multi'`), com `hint` honesto ("~85% do comércio não tem detalhe de regime →
  aparece como C00/Total"). Fluxos: passar a ler `available_flows` do source-meta.
- `FilterMenu.jsx` — render dos novos multi-selects (reusar o padrão de `flags`/produtos).
- Empty-state claro quando o fluxo/regime selecionado não tem dado para o recorte Brasil (ex.:
  Reexportação) — "sem registros para este fluxo no recorte atual (Brasil declarante)".

### Fase 8 — Descongelar a Engenharia de Atributos (tipo de mercado)

`seam_attribute_engineering.py` está `FROZEN` (Versão Futura, PRs #168/#169). Reativar:
- Un-comentar os entry points de UI (views.js + AppShell.jsx) para "Engenharia de Atributos".
- `dbt build --vars 'enable_curation: true'` (o SCD2 gated) — **operator, prod**.
- O mapa `(customsCode × flowCode) → mercado` depende da Fase 3 (regime preservado) + curadoria
  do pesquisador (append-log `research_inputs`). Sem curadoria, o eixo fica vazio (honesto).

---

## Runbook do operador (fases 2, 4, 8 — prod)

1. **Re-ingestão** (Fase 2): setar `COMTRADE_FLOWS=X,M,RX,RM,DX,FM,MIP,MOP,XIP,XOP` no ambiente do
   Job → `uv run embrapa ingest comtrade --full` (ou disparar o Job de backfill). Custo: tempo de
   API/cota, não dinheiro. Confirmar linhas dos 6 novos códigos antes de expor no UI.
2. **Rebuild Gold** (Fases 3–5): `make dbt-build-prod-with-backup` (preservável). `silver_comtrade_flows`
   é `table` (full window), então rebuild completo. Validar grão e ausência de dupla contagem
   (SUM por flow com/sem regime deve bater).
3. **Descongelar** (Fase 8): `dbt build --vars 'enable_curation: true'` + deploy webapi (image-only)
   + re-habilitar entry points de UI.
4. **Deploy**: `gcloud builds submit --config deploy/webapi/cloudbuild.yaml` + `gcloud run deploy
   --image` (image-only, preserva env/IAP/SA).

## Custo em nuvem (resumo)

Desprezível em todas as fases. Linhagem < 3 GB; +regime ≈ +16% linhas (~+0,15 GB); +10 fluxos ≈
limitado (os 6 novos são raros na base anual). Consultas usam marts pré-agregados (< 1 GB) com
cache + `maximum_bytes_billed`. Estimativa: **centavos/mês ou $0 dentro da faixa gratuita**.

## Decisões em aberto

1. **Token dos 6 fluxos novos** — legível estável (`national-export`…) vs. o código bruto (`DX`).
2. **Reporter fixo em Brasil** — mantém re-export/regimes de aperfeiçoamento estruturalmente vazios.
   Des-fixar exige repensar o snapshot (grande; fora deste plano).
3. **Expor opções vazias?** — recomendação: **não** (opções data-driven via source-meta), para não
   recriar o problema de "filtro que não funciona".
