# Auditoria Completa do Codebase — Embrapa Commodities Dashboard

> ⚠️ **HISTÓRICO — relatório pontual, não é uma lista de pendências.** Auditoria de 2026-06-23, sobre a v1.5.2, muito anterior ao estado atual do repositório. Seus achados foram tratados na época (veja o `CHANGELOG`); trate caminhos, contagens e estrutura aqui como o retrato daquela data, **não** como o código de hoje. Mantido por proveniência — em especial os achados refutados, que não existem em nenhum outro lugar.

**Data:** 2026-06-23 · **Versão auditada:** v1.5.2 · **Método:** workflow multi-agente
(13 dimensões em fan-out → verificação adversarial por achado → síntese + crítico de
completude). 88 agentes, ~6,1 M tokens. **59 achados brutos → 58 confirmados, 1 refutado.**
Os 2 achados ALTOS foram **re-verificados manualmente na fonte** (não só pelo voto dos agentes).

> Esta é a auditoria *full-codebase* automatizada. A varredura manual focada na feature geo
> do mesmo dia está em [`manual_scan_audit_2026-06-23.md`](manual_scan_audit_2026-06-23.md).

> **✅ REMEDIAÇÃO (mesma sessão):** todos os achados foram corrigidos no branch
> `claude/affectionate-ramanujan-0325c8` (worktree — **ainda não commitado/PR/deploy**).
> 48 arquivos, +857/−162. Validado: **897 pytest** (+13) / **250 vitest** (+9) verdes;
> ruff+format+eslint limpos; `vite build` OK; `dbt parse` limpo; deps com CVE atualizadas
> (`uv lock` + `uv sync`, flask 3.1.3 · werkzeug 3.1.8 · cryptography 49 · pydantic-settings
> 2.14.2 · msgpack 1.2.1). **Decisões conscientes de NÃO alterar código:** SEC-3 (dica IAP é
> aux. de operador, só p/ autenticado, sem segredo), NUM-3 (enquadramento "acervo"), IBGE-2
> (single-writer), INFRA-4 (chave dev gitignored), DBT-4 (linha área-only é genuinamente
> incompleta em qty+valor — documentado). **Diferidos p/ operador** (precisam de infra
> indisponível no sandbox): DEP-6 (pin por `@sha256` precisa de docker/registry).

---

## 0. Métricas objetivas (saúde estrutural)

| Métrica | Resultado |
|---|---|
| Maintainability Index (radon) | **Grau A em 100% dos arquivos** (pior: `serializers.py` 33,4) |
| Complexidade ciclomática (radon CC) | pior função `webapi/app.py:_json_safe` **C(14)**; ~40 funções grau B; resto A |
| Ruff C90 (McCabe ≤ 10) | **limpo** (`_json_safe` ≤ 10 no McCabe estrito; C(14) é contagem do radon) |
| Cobertura pytest | **95% global · 884 testes verdes** |
| Vitest (frontend) | 34 arquivos de teste |

Módulos com mais linhas descobertas (todos ≥ 88%): `gateway.py` 88%, `doctor.py` 88%,
`routes.py` 89%, `cli.py` 90%, `ibge/client.py` 90%, `curation.py` 91%, `serializers.py` 93%.

---

## 1. Veredito executivo

O repositório está **saudável e maduro**. A varredura de 13 dimensões **não encontrou nenhum
problema crítico** — sem brecha de segurança, sem corrupção de dados, sem crash no caminho de
produção. O risco real concentra-se em **2 achados ALTOS**, ambos no recorte de dados exibido:

- **NUM-1** — o banco UN COMTRADE soma o comércio do mundo inteiro em 2022-2023 por falta de
  fixação `reporter=Brasil` no snapshot próprio.
- **RVC-1** — filtros sub-UF/município (feature v1.5.2) são silenciosamente descartados em
  links de compartilhamento/citação.

Os 3 MÉDIOS são lacunas de integração/robustez na própria geografia recém-lançada. O resto é
cauda longa de baixo/info: drift de docs, hardening de supply-chain (7 CVEs já corrigidos
upstream, maioria não-alcançável) e polimentos. **Grade geral: A−.**

---

## 2. Achados por severidade

### 🔴 Crítico
Nenhum. Bucket vazio.

### 🟠 Alto (2) — re-verificados na fonte

- **NUM-1** · `serving/gateway.py:367-390, 745-774` (+ `serving/sql.py` trade_overview L561-597,
  product_timeseries L1037-1091).
  O snapshot próprio do banco **UN COMTRADE** (`overviewTS` + `productTS`) não fixa
  `reporter=Brasil`. O mart `serving_comtrade_annual` tem grão multi-reporter
  (`…, reporter_code, partner_code, family`); então para 2022-2023 (janela do backfill
  all-reporters) o KPI "Valor total" e as séries Valor/Volume somam o comércio do **mundo
  inteiro**, com salto espúrio em 2022. As leituras de parceiro/fluxo/cross **já fixam**
  `reporter_iso_a3=Brasil` (gateway.py:505-506, 600-601, 868-869) — estas duas escaparam.
  *Fix:* threadar `reporter_iso_a3=settings.comtrade_brazil_iso` por `trade_overview` /
  `product_timeseries` e atualizar o ramo `_TRADE` de `seam.snapshot()`; COMEX permanece sem
  fixação (é alfândega do próprio Brasil). Reverificar que o ponto 2022 não salta. **Esforço M.**

- **RVC-1** · `frontend/src/ui/urlState.js:13-17`.
  As 5 dimensões geo da v1.5.2 (`mesos/micros/inters/imediatas/munis`) não estão em
  `URL_STATE_KEYS` (que tem só `st`), nem em `buildPermalink` nem em `readStateFromURL`. Um
  recorte sub-UF/município é **perdido ao Compartilhar/Citar**, quebrando a reprodutibilidade da
  citação. *Fix:* adicionar as 5 chaves, codificar via `urlEncodeArr`/`urlDecodeArr`, teste de
  round-trip. (Correlato: `urlDecodeNum` linha 34 faz `Number(v)` sem guard de NaN.) **Esforço S.**

### 🟡 Médio (5)

- **GEO-1 / RVC-2** (mesmo problema) · `frontend/src/ui/ViewGeography.jsx:257-276`.
  A aba "Município" renderiza `filtered.topMunis`, que **não tem produtor backend**
  (`decorate.js:113` "no endpoint yet" → sempre `[]`). O cubo real da v1.5.2
  (`window.municipioYearly`) nunca foi ligado ao painel → aba "Município" sempre vazia.
  *Fix:* alimentar com `window.municipioYearly` quando `scope==='municipio'`, ou esconder o
  botão; remover o caminho morto `muniNames`. **Esforço M.**

- **DATA-1** · `frontend/src/ui/dataFilters.js:247-302`.
  Com basket de produtos **e** subset de UF ativos, durante o load do cubo produto×UF o
  `filtered.ts` soma **todos** os produtos (basket descartado de VALOR/YoY/acumulada).
  `ViewOverview` respeita `geoComboPending`, mas `ViewValueVolume` e `ViewConcentration`
  **não** → número errado transitório. *Fix:* essas views honrarem
  `geoComboPending`/`notFilteredByBasket`, ou neutralizar `ts` no data layer. **Esforço S.**

- **TEST-1** · `tests/test_webapi_routes.py` (ausente; fonte `routes.py:296-321`).
  A rota `POST /api/municipio-yearly` (entrada da feature de maior risco) **não tem teste HTTP**;
  o guard `cityCodes` vazio→400 (proteção de custo) não é asado no nível da rota. *Fix:* testes
  Flask-client para 400 (sem/vazio) e 200 (com basket+cidades). **Esforço S.**

### 🟢 Baixo (selecionados)

| ID | Local | Problema · Fix |
|---|---|---|
| SEC-1 | `routes.py:312-321` | `cityCodes` sem cap de contagem (assimétrico com `_MAX_TABLE_FILTERS=5`) → limitar a ~5570 e 400 |
| SEC-2 | `routes.py:313` | `cityCodes` string é char-splitada (sem `isinstance(list)`) → validar e 400 |
| SEC-4 | `app.py:91-104` | sem `MAX_CONTENT_LENGTH` → setar ~1 MiB |
| GEO-2 | `dataFilters.js:189-198` | narrowing sub-UF mostra all-UF sem loading até mesh resolver (mitigado por warm-up) |
| DATA-2 | `dataFilters.js:189-190` | fetch desnecessário da mesh (~5570) para bancos de comércio → `_hasGeoKeys` só de arrays não-vazios |
| DATA-3 | `enrichment.js:166-177` | `stats()` reconstrói `cellMap` ~160×/chamada → construir 1× |
| RVC-3 | `MainScreen.jsx:394-396` | `ufsCovered` filtra só `value>0`, ignora `q_count` (rebanho PPM) |
| RVC-4 | `dataFilters.js:388-402` | caminho morto `muniNames`/`MUNI_PICKER_NAMES` |
| RVC-5 | `FilterMenu.jsx:270-281` | ~5570 checkboxes sem virtualização |
| OBS-1 | `monitor/state.py:349-350` | `rows=0` sempre no `pipeline_end` (produtor não emite `rows_total`; teste mascara) |
| OBS-2 | `monitor/state.py:325,334,350` | `TypeError` em scalar `null` → `ev.get('x') or 0` |
| IBGE-1 | `ibge/client.py:136-159` | deadline SIDRA não escala por densidade de municípios do estado (MG ~853 vs RR ~15) |
| COMEX-1 | `comex/client.py:253-275` | download 200 vazio vira chunk "failed" duro → `ComexTransientError` |
| DEP-1..6 | `uv.lock`, `deploy/*/Dockerfile` | 7 CVEs (todos com fix) → `uv lock --upgrade`; pinnar imagens base por `@sha256` |
| INFRA-1 | `release.yml:70-143` | builda imagem prod sem gate de teste, em tag arbitrária |
| INFRA-2 | `block-dangerous-commands.js:60-66` | hook não cobre `gcloud run jobs/scheduler/secrets/iam/monitoring delete` |
| INFRA-3 | `deploy/webapi/deploy.sh:45-46` | cai para `:latest` se `git rev-parse` falha → falhar alto |
| TEST-2/3/4 | tests | `geo-mesh` sem teste HTTP; seam município não asserta `value_column`/`city_codes`; serializers só single-row |
| DBT-1 | `assert_serving_conserved_gold.sql` | PPM fora do teste de conservação Gold→serving |
| DBT-4 | `gold_pam_production.sql:57-60` | linhas área-only do PAM marcadas INCOMPLETE |
| DOC-1 | `SECURITY.md:5-9` | tabela de versões obsoleta (lista 1.1.x; atual 1.5.2) |

### ℹ️ Info (agrupados)

- **NUM-2/NUM-3** — `overviewTS` omite `q_count` (footgun latente, hoje inócuo); quality COMTRADE
  conta sobre todos os reporters (framing "acervo do banco", coerente com a decisão de NUM-1).
- **JSON-1** `app.py:48-67` — `_json_safe` não trata `Decimal` (inalcançável hoje: nenhuma coluna
  NUMERIC) → adicionar branch como seguro.
- **DOC-2..DOC-9** — diagramas README/ARCHITECTURE omitem PPM / `gold_ppm_production` /
  `serving_ppm_annual` / seeds v1.5.2; `dbt_project.yml` e `_core.yml` não citam
  `dim_geo_municipio`; ROADMAP lista itens já entregues. Drift de docs, sem impacto funcional.
- **COMTRADE-1 / COMEX-2 / IBGE-2 / MON-1 / DOC(doctor) / DBT-2 / DBT-3** — invariantes latentes,
  leaks de hygiene, comentário órfão, staleness de backup com truncamento de fração de dia.

---

## 3. Três baldes do skill `code-audit`

**🔴 Arquitetura Crítica — VAZIO.** Nenhum problema arquitetural. Pushdown Computing, camada
serving, separação BFF/seam/serializers e parametrização de queries sólidas. O caminho geo novo é
seguro onde mais importa (`production_by_municipio_yearly` totalmente parametrizado, `value_column`
allowlistado via `_validate_column`, escala por família consistente — a classe de mis-scale de
quantidade física **não** reapareceu no serializer novo).

**🟡 Code Smells** — Concentrados no frontend recém-entregue (v1.5.2): integração incompleta do
cubo de município (GEO-1), guards de pending não consumidos por todas as views (DATA-1), caminhos
mortos (`muniNames`, `topMunis`), hot loop em `enrichment.stats()`. No backend: monitor frágil a
`null`/`rows_total` ausente, deadline SIDRA cego à densidade do estado.

**🟢 Convenções** — Boa aderência. Cauda longa de drift de docs e lacunas de teste em superfícies
de alto risco (rotas geo, codec de URL, views de geografia). Supply-chain bem configurado
(Dependabot ativo) mas com PRs pendentes não mesclados.

---

## 4. Plano de ação priorizado

1. **[ALTO]** NUM-1 — fixar `reporter=Brasil` no snapshot COMTRADE; reverificar 2022. **M**
2. **[ALTO]** RVC-1 — persistir dims geo na URL + teste round-trip. **S**
3. **[MÉDIO]** GEO-1/RVC-2 — ligar painel "Município" ao cubo real ou esconder o botão. **M**
4. **[MÉDIO]** DATA-1 — `ViewValueVolume`/`ViewConcentration` honrarem `geoComboPending`. **S**
5. **[MÉDIO]** TEST-1 — teste HTTP de `POST /api/municipio-yearly`. **S**
6. **[BAIXO]** DEP-1/DEP-2 — `uv lock --upgrade` (cryptography 48.0.1 tem alcance prod claro) + rebuild. **S**
7. **[BAIXO]** SEC-1/SEC-2/SEC-4 — capar/validar `cityCodes` + `MAX_CONTENT_LENGTH`. **S**
8. **[BAIXO]** INFRA-2 — estender hook destrutivo para jobs/scheduler/secrets/iam/monitoring. **S**
9. **[BAIXO]** Sweep de docs (DOC-1..DOC-9) de uma vez. **M**
10. **[BAIXO]** OBS-2 + robustez do monitor; IBGE-1 deadline por densidade. **S/M**

---

## 5. Falsos positivos e lacunas de cobertura

**Falsos positivos capturados: 1.** DBT-5 (índice de inflação iria a NULL permanente com
`monthly_pct_change=-100`) foi **refutado** — `SUM()` como agregado de janela no BigQuery ignora
NULLs, então um termo `safe.log(0)=NULL` é pulado, não envenena o cumulativo; e o gatilho
(−100% mês) é economicamente impossível.

**Lacunas de cobertura (gaps de probing, não bugs confirmados) — apontadas pelo crítico de completude:**

- **`scripts/`** inteiro fora de toda dimensão e sem cobertura — crucialmente
  `refresh_ibge_municipio_mesh.py`, o **gerador** do seed que sustenta toda a cascata geo v1.5.2.
  → smoke/unit test com fixture gravada.
- **`ibge_municipio_mesh.csv` (5572 linhas)** validado só por not_null/unique + 1 teste de UF;
  sem teste de **completude** (27 UFs, códigos de 7 dígitos, pares code/name) nem cruzamento com
  `gold.dim_geo_municipio` vivo.
- **Concorrência da camada serving** (gunicorn multi-worker + multi-instância) documentada como
  trade-off mas não probada (double-insert de curation, curador revogado dentro do TTL,
  invalidação pós-`delete_memoized`).
- **`urlState.js`** sem teste — `urlDecodeNum` sem guard de NaN.
- **Views de alto risco sem teste dedicado** — `ViewGeography`, `ViewValueVolume`, `csvExport.js`
  (onde viveu a classe "tonnes-mislabel"/medida não-aditiva).
