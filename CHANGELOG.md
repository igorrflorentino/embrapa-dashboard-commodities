# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [1.24.29] - 2026-08-20

### Fixed
- **Varredura de documentação, fechando o que a sessão de hoje deixou desatualizado.** Seis
  versões (v1.24.23→28) mudaram deploy, CI e a CLI; a documentação não acompanhou.

  - **`CONTRIBUTING.md` — o checklist de PR não citava `make coverage-diff`.** Era a lacuna
    mais cara: quem seguisse o checklist à risca abriria PR e seria reprovado por um check
    que o checklist nunca mencionou. E "todos os **três** status checks" virou **cinco**
    (faltavam `dbt unit tests` e `gitleaks`).
  - **A história do deploy estava obsoleta em 5 lugares** (`CLAUDE.md`, `README.md`,
    `ARCHITECTURE.md` ×3): todos apresentavam `make webapi-deploy` como o caminho, sem dizer
    que mudança de **código** agora sobe sozinha no merge. Perigoso e não só desatualizado —
    a partir de uma máquina sem `.env.prod`, rodar `deploy.sh` para publicar código
    **derruba o `IAP_AUDIENCE`** e desarma a verificação de IAP no app. Agora está explícito
    que `deploy.sh` é o caminho de **mudança de env**, e só.
  - **`docs/operations_runbook.md`** ganhou a mesma distinção, para que a seção de
    `IAP_AUDIENCE` não seja lida como "todo deploy precisa de `.env.prod`".
  - **`ARCHITECTURE.md`** — a árvore de módulos não listava `reconcile_check.py` nem
    `release.py`, ambos criados nesta sessão.

### Added
- **`docs/iam_setup.md` ganhou a seção das service accounts de CI.** As cinco identidades
  keyless (WIF) existiam **apenas** nos cabeçalhos dos workflows — uma lacuna pré-existente
  que hoje ficou maior, quando adicionei a quinta. A tabela é índice; o cabeçalho do
  workflow segue sendo a fonte de verdade dos comandos, de propósito, para que concessão e
  uso não se separem.

### Nota — uma service account órfã, encontrada na varredura
`sa-dashboard-smoke-ci` **existe**, tem a variável `GCP_SMOKE_SERVICE_ACCOUNT` configurada
e binding WIF ativo — mas **nenhum workflow a referencia** (verificado 2026-08-20). É
remanescente do smoke test removido junto com a UI Dash. Acesso keyless permanente que nada
usa é acesso que vale remover. **Não removi** — apagar identidade em produção é decisão do
operador; está registrado no `docs/iam_setup.md` com o aviso.

---

## [1.24.28] - 2026-08-20

### Changed
- **Duas camadas de cobertura, em vez de um número só.** O portão rearmado em v1.24.27
  ficou a 99% com **7 linhas de folga** — apertado a ponto de um único `except` defensivo
  bloquear merge. E um portão que atrapalha toda hora acaba baixado às pressas, que foi
  exatamente como ele virou decorativo antes.

  **Camada 1 — piso absoluto, 99% → 98%** (`make test`). A função dele é impedir
  **decaimento silencioso**, não policiar PR individual. O piso é **proporcional ao tamanho
  do repo**: com ~6,8k statements, 98% ainda pega uma feature sem teste (~77 statements) e
  deixa de tropeçar em ruído de uma linha. `precision = 2` continua sendo o que faz 98
  significar 98.

  **Camada 2 — cobertura do diff** (`make coverage-diff`, via `diff-cover`): **≥90% das
  linhas que o branch mudou**. Esta é a que de fato exige *"escreveu código, escreveu
  teste"*.

  O piso pergunta "o repositório inteiro segue bem coberto?" — pergunta que **enfraquece
  conforme o repo cresce**, já que a mesma feature sem teste mexe menos no total a cada mês.
  A cobertura do diff pergunta "você testou o que acabou de escrever?", que não decai, e
  **nunca cobra do PR um buraco que ele não criou** — como as ~20 linhas descobertas da
  `serving/attribute_engineering.py`, que está **congelada**.

  A lacuna entre as duas foi demonstrada, não suposta: **6 linhas novas sem teste levam o
  total de 99,12% para 99,04% — o piso PASSA, e a cobertura do diff REPROVA com 16%.**

  No CI a camada 2 roda **só em pull request** (num push para `main` o diff é o que acabou
  de ser mergeado e já foi checado no PR). O checkout ganhou `fetch-depth: 0`, sem o qual
  não há base para comparar. Sem Codecov, sem conta, sem token — `diff-cover` é dependência
  de dev e roda dentro do próprio job.

---

## [1.24.27] - 2026-08-20

### Fixed
- **O portão de cobertura não gateava — agora gateia.** `--cov-fail-under=99` comparava a
  cobertura **arredondada**:

  ```python
  round(total, precision) < fail_under     # precision default = 0
  round(98.79, 0) == 99  →  99 < 99  →  False  →  passa
  ```

  Na prática o portão de "99%" exigia **≥98,5%**, e a linha
  `FAIL Required test coverage of 99% not reached` que aparecia no log do CI era
  **cosmética** — o job seguia verde. Comprovado pelo extremo: **0,38% de cobertura ainda
  saía com exit 0**. Sem ninguém perceber, a cobertura total já tinha escorregado para
  **98,79%**.

  Correção: `precision = 2` em `[tool.coverage.report]`, com a explicação ao lado. Agora
  99 quer dizer 99. Verificado nos dois sentidos: 0,38% → exit **1**; 99,12% → exit **0**;
  limiar inatingível de 99,5 → exit **1**.

### Added
- **17 testes cobrindo guardas que nunca tinham sido exercitadas**, subindo a cobertura de
  98,79% para **99,12%** (60 linhas descobertas, margem de 7 até o teto). Escolhidos por
  serem **rejeições e caminhos fail-closed** — onde um defeito silencioso é mais caro —
  e não por serem fáceis de cobrir:

  - **`webapi/routes.py`** — o 503 quando a allowlist de editores não pôde ser confirmada
    (allowlist vazia significa "aberto a qualquer chamador IAP" **por design**, então uma
    leitura vazia que na verdade é "indisponível" jamais pode ser confundida com ela);
    `can_edit` virando `false` quando a consulta falha; e as três rotas de agrupamento
    exigindo editor.
  - **`serving/curation.py`** — a rejeição de eixo com erro de digitação (a docstring cita
    `'ocluto'` pelo nome: armazenado em silêncio, deixaria em exibição um produto que o
    pesquisador quis ocultar); banco desconhecido, que é a **única** camada que valida isso;
    e as quedas `NotFound`/`BadRequest` que significam "nada armazenado ainda" — deliberadamente
    estreitas, para que uma falha transitória do BigQuery nunca apague a anotação de um
    pesquisador.
  - **`doctor.py`** — as saídas consultivas: uma sonda que não consegue responder degrada
    para uma linha informativa, nunca derruba o relatório inteiro nem reporta verde falso.

  **Não** cobri `serving/attribute_engineering.py` (20 linhas, a maior fatia restante):
  é a Engenharia de Atributos, congelada e oculta da UI. Testar código congelado só para
  subir número é enchimento.

---

## [1.24.26] - 2026-08-20

### Added
- **`embrapa reconcile-check`** — responde com medição a pergunta que o lembrete mensal
  fazia por palpite: *"algum ano antigo mudou na fonte?"*.

  A ingestão de IBGE/BCB é **delta**: o nightly só re-consulta uma janela recente, então
  uma correção publicada num ano **antigo** nunca é vista. O `reconcile` existe para isso,
  mas é caro, e até agora a decisão de rodá-lo era um chute mensal.

  O comando é **somente leitura** — não ingere, não corrige, não escreve. Compara o que as
  fontes servem HOJE contra o que está no Bronze, restrito a dado velho o bastante para a
  janela delta nunca tocar. Sai com **1** se algo divergiu (dá para um workflow gatilhar
  em cima), **0** se não, e informa quantos pontos conferiu.

  **IBGE PEVS: célula a célula, no grão que armazenamos** (município × produto × variável,
  nível `n6`). Deliberadamente **não** compara totais nacionais: o IBGE suprime células
  municipais pequenas por confidencialidade, e um agregado divergiria por motivo que não é
  revisão. **BCB: exaustivo** — uma requisição ao SGS devolve a série inteira, então todo
  ponto anterior à janela de rewind é conferido, não amostrado.

  **COMEX fica fora de propósito:** o check de ETag por arquivo já re-detecta revisão de
  qualquer ano toda noite, então `reconcile` não acrescenta nada para ele.

  Primeira execução real: **19.658 pontos conferidos, zero divergências**.

### Changed
- **O lembrete mensal (`reconcile-reminder.yml`) agora lidera com o check.** Em vez de
  descrever quando um `reconcile` *seria* justificado e pedir que o operador julgue, a
  issue manda rodar `embrapa reconcile-check` e colar os números. A premissa original —
  registrada no workflow e no `CLAUDE.md` — era que nenhum pré-check barato seria viável
  para IBGE/BCB. Isso vale para o histórico **inteiro**, mas não para uma amostra bem
  escolhida (~20k pontos em ~2 min), e para o BCB não vale de forma alguma. Texto corrigido
  nos dois lugares.

---

## [1.24.25] - 2026-08-20

### Changed
- **`eslint-plugin-react-hooks` 5 → 7 e `globals` 15 → 17** (PRs #261 e #266 do Dependabot,
  incorporados aqui porque o bump do plugin **não passa sozinho**: as regras novas reprovam
  código existente, e mergear o bump sem as correções deixaria o CI vermelho).

  O react-hooks 7 traz o conjunto de regras da era React Compiler e apontou **9 erros reais**
  em 4 regras. Nenhum foi silenciado por conveniência — cada um foi julgado individualmente.

### Fixed
- **`react-hooks/static-components` — componentes criados durante o render (2 casos reais).**
  `Group` (em `MetricConventions.jsx`) e `Legend` (em `ViewCuratedAnalyses.jsx`) eram definidos
  dentro do corpo do componente pai. Como o tipo do componente é **novo a cada render**, o React
  não atualizava: descartava e remontava a subárvore inteira toda vez. Os dois não capturam nada
  do escopo pai (recebem tudo por props), então foram içados para o escopo de módulo — correção
  real, comportamento preservado.
- **`react-hooks/immutability` — `Donut.jsx`.** A geometria das fatias usava um acumulador
  mutável (`acc += …`) dentro do render. Extraída para `donutSlices()`, função pura de escopo de
  módulo — some a mutação em render e a geometria fica testável isoladamente. No caminho, uma
  regressão que eu mesmo introduzi e que o **lint não pegou**: a legenda usava `val(d)`, que
  passou a existir só dentro do helper (`no-undef` está desligado no projeto por causa dos
  globais `window.*`). Virou `sliceValue(d, valueKey)`, compartilhado pelos dois — sem isso a
  legenda mostraria `NaN%`.
- **`react-hooks/refs` — `_base.jsx`.** `onClickRef.current = onClick` era escrito **durante o
  render**. Movido para um efeito sem array de dependências (roda depois de todo render). Nada
  se perde: o ref só é lido a partir de um clique do usuário, que nunca acontece antes do React
  ter aplicado o efeito. Coberto pelo teste de regressão que já existia em `_base.test.jsx`.

### Nota — 3 dos 9 NÃO eram defeitos, e foram anotados em vez de "corrigidos"
- **`static-components` × 2 em `MainScreen.jsx`:** `Comp` e `ViewComponent` são **buscados no
  registry de visões** (`window.viewComponent(id)`), não criados no render — a regra não
  distingue as duas coisas. A identidade só muda quando o pesquisador troca de visão, e remontar
  nessa troca é o comportamento pretendido: cada visão tem seus próprios fetches e estado local,
  e não deve herdar os da anterior.
- **`set-state-in-effect` × 1 em `_base.jsx`:** o `if (failed) setFailed(false)` é guardado, então
  dispara no máximo uma vez por recuperação e o passe seguinte já não faz nada — não é a cascata
  que a regra combate. Também não é estado derivado: registra o resultado de uma chamada
  imperativa a um sistema externo (Plotly), que é exatamente o papel de um efeito.

  Os três levaram `eslint-disable-next-line` **com a justificativa escrita ao lado**. Reescrever
  o código para agradar a regra deixaria os dois piores.

### Verificação
Lint 0 erros com o plugin novo, 792/792, build limpo — e conferido **no build servido**, porque
esta versão mexe em ciclo de vida do Plotly e em dois componentes de UI: strip de convenções com
os 4 grupos e 14 botões, troca de moeda propagando até os gráficos (`US$ 1.210.169.184`), e o
donut com 8 formas e legenda `54% / 18% / 15% / 10% / 3% / 0%` — sem `NaN`.

`ViewCuratedAnalyses.jsx` não tem teste dedicado (é a Engenharia de Atributos, congelada e
oculta da UI); ali o hoist é mecânico e a verificação é lint + build.

---

## [1.24.24] - 2026-08-20

### Changed
- **maplibre-gl 4.7.1 → 6.4.1** — o bump reprovado em v1.24.22 agora entra, com a causa raiz
  entendida. Eram **duas** falhas independentes, e a nota do v1.24.22 acertou o sintoma e
  **errou o diagnóstico** (ver a correção abaixo).

  **(1) O `TypeError`.** O maplibre 5+ é ESM puro com ~85 exports **nomeados** e **sem
  `default`**. O componente fazia `(await import('maplibre-gl')).default` → `undefined` →
  `undefined.Map`, exatamente o `Cannot read properties of undefined (reading 'Map')`
  observado. E como a única coisa referenciada era um export inexistente, o Rollup removia a
  biblioteca inteira por tree-shaking — daí o chunk cair de 786 kB para 514 bytes. Corrigido
  usando o **namespace** do módulo.

  **(2) O worker, que só apareceu depois.** Resolvido o import, o mapa **continuava cinza**:
  `isStyleLoaded()` e `loaded()` ficavam `false` para sempre e **nenhum evento `idle`**
  chegava. O maplibre 5+ roda o geojson-vt num **module worker** publicado como arquivo
  separado, e resolve a URL dele em runtime como irmão do próprio `import.meta.url` — uma URL
  que o bundler não enxerga, então o Vite nunca emitia o arquivo. A requisição caía no
  fallback de SPA (index.html), morria no MIME check, e o worker nunca subia. Corrigido com
  `?worker&url` + `maplibregl.setWorkerUrl()`, mais `worker: { format: 'es' }` no
  `vite.config.js`.

  Precisa ser `?worker&url` e **não** `?url`: o worker importa um irmão
  (`./maplibre-gl-shared.mjs`, 482 kB). O `?url` copia um arquivo só, verbatim, e o import
  relativo aponta para um asset inexistente.

  Verificado no **build servido** e no **dev server**: worker sem erro, `isStyleLoaded()`
  true, **31 UFs renderizadas**, `fill-color` como `match` de 57 entradas no primeiro
  carregamento, popup de hover ("PA · Pará · 2,9 bi R$") e controles de zoom intactos.
  Bundle: chunk maplibre 786 → 980 kB, mais um worker de 470 kB (no 4.x esse código vinha
  inline como blob dentro do bundle único).

### Fixed
- **Correção da nota do v1.24.22.** Aquela entrada atribuiu a falha ao `manualChunks` do
  `vite.config.js` "não acompanhar" o maplibre 5+. Está **errado**: o `manualChunks` só trata
  `plotly` e `react` e nunca menciona maplibre — o chunk vem do code-splitting automático do
  `import()` dinâmico. As causas reais são as duas acima. A nota original ficou preservada
  como registro histórico, mas mandaria o próximo leitor para o caminho errado.

### Added
- Terceiro teste em `BrazilChoropleth.test.jsx`: trava a **ordem** `setWorkerUrl` → `new Map()`.
  O maplibre sobe o pool de workers no primeiro `new Map()`, então um `setWorkerUrl` que chegue
  depois é ignorado e a biblioteca volta a adivinhar a URL — de novo com o mapa em branco. O
  mock também deixou de expor `default`, espelhando o ESM real: um mock com `default` deixaria
  passar um componente que quebra contra a biblioteca de verdade. 792/792.

---

## [1.24.23] - 2026-08-20

### Fixed
- **Coroplético "Distribuição por UF" nascia cinza.** Ao abrir a Geografia o mapa vinha todo
  na cor de "sem dado"; trocar a métrica (Valor → Quantidade) fazia as cores aparecerem, e
  voltar para Valor as mantinha. Não era a métrica: era a **ordem de carregamento**.

  O `paint()` desistia em silêncio em duas condições **transitórias** — o estilo do maplibre
  ainda assentando, e a camada `uf-fill` ainda não criada (ela nasce no `map.on('load')`,
  assíncrono). Na prática a API responde ANTES do mapa terminar de carregar, então o efeito
  de dados rodava exatamente nesse intervalo e saía sem pintar. Como só uma mudança de
  `data`/`valueKey` re-disparava o efeito, aquele instante virava **permanente** — e mexer no
  seletor de métrica era a única coisa que refazia a pintura com tudo já pronto.

  O `map.on('load')` também pintava a partir do próprio closure, congelado no PRIMEIRO render,
  quando `data` ainda estava vazio: pintava o cinza de "sem dado" e nada o corrigia depois.

  Agora `paint()` **adia em vez de desistir** (`map.once('idle', paint)`, que se remove
  sozinho — nunca empilha handlers), o `load` apenas sinaliza prontidão via `layerReady`, e
  esse estado entra nas dependências do efeito, que repinta com o dado ATUAL. Verificado no
  build de produção: `fill-color` deixa de ser o cinza plano `"#eef0ef"` e passa a ser uma
  expressão `match` com as 27 UFs, no primeiro carregamento, sem tocar em nada.

### Added
- `frontend/src/charts/BrazilChoropleth.test.jsx` — dois testes de regressão que reproduzem a
  ordem real (dado antes do `load`; estilo ainda assentando) com um mapa falso. Ambos **falham
  no código antigo** e passam no corrigido. 791/791 no total.

---

## [1.24.22] - 2026-08-20

### Changed
- **Plotly 2 → 3.** Sem mudança de código: 789/789, lint e build limpos. Verificado **no build
  de produção**, não só no dev server — série histórica 1986-2024, rosca de composição, mapa de
  calor e os três gráficos da Geografia, com dado real e zero erros no console.

### Nota — maplibre 4 → 6 REPROVADO, e por quê
O bump **quebra o coroplético em produção**, e passa despercebido por tudo que normalmente
usamos para aprovar:

    [choropleth] maplibre init failed:
      TypeError: Cannot read properties of undefined (reading 'Map')

Testes (789/789), lint e `vite build` passam. **No dev server o mapa renderiza normalmente** —
o Vite serve os módulos direto. Só o `dist` servido de verdade expõe a falha: a biblioteca não
entra no pacote. O sinal estava no tamanho — o chunk do maplibre cai de **786 kB para 514
bytes** e o `index` não cresce; os 786 kB simplesmente desaparecem. O maplibre 5+ mudou de
arquitetura e o `manualChunks` do `vite.config.js` não acompanha.

Revertido para 4.7.1. Reabrir exige ajustar o bundling primeiro, e **validar no build**, nunca
no dev server.

Registro de método: cheguei a suspeitar que o maplibre 6 apagava as cores do coroplético.
Comparei com o 4 antes de acusar — a aparência é idêntica, então **não era regressão**. O
coroplético renderiza sem preenchimento por cor nas DUAS versões, o que confirma em navegador
o item que a auditoria de 2026-06 deixou em aberto. É um defeito pré-existente, separado deste
PR.

## [1.24.21] - 2026-08-20

### Changed
- **React 18 → 19** (`react`, `react-dom`, `@testing-library/react` 16.1 → 16.3). **Nenhuma
  linha de código da aplicação precisou mudar** — a suíte passou 789/789 e o `vite build`
  saiu limpo já na primeira tentativa.

  Verificado **no navegador**, não só nos testes, porque teste unitário não vê renderização:
  a Visão geral do PEVS carregou com dado real (KPIs, sparklines, série histórica 1986-2024 no
  Plotly, rosca de composição, mapa de UF, painel de qualidade), sem um único erro no console.
  É o primeiro dos quatro majors que a política do #256 passou a entregar individualmente.

### Nota — o major que NÃO foi feito
**eslint 9 → 10 está bloqueado a montante.** O `eslint-plugin-react@latest` continua em 7.37.5,
com peer `^3 || … || ^9.7` — sem suporte a eslint 10. Fazer o bump exigiria `--legacy-peer-deps`,
que mascara uma incompatibilidade real em vez de resolvê-la. Fica esperando o upstream; foi
exatamente este conflito que quebrava o `npm ci` no PR agrupado que motivou a mudança de política.

## [1.24.20] - 2026-08-20

### Changed
- **Node 22 → 24 (LTS)** em `.nvmrc`, `deploy/webapi/Dockerfile` e `docs/testing.md`, juntos —
  que é a única forma segura de mover essa versão. Como o `.nvmrc` virou fonte única na
  v1.24.7, o CI (`ci.yml` e `release.yml`, via `node-version-file`) acompanha sozinho.

  **Verificado antes de mudar, não depois:** suíte do frontend **789/789** e `vite build`
  limpo no node 24, com o `npm ci` refeito do zero. Manutenção deliberada, não resgate — o
  node 22 tem suporte até abril/2027; a motivação é não repetir a defasagem em que o
  Dockerfile constrói o bundle de produção num runtime que nenhum teste exercita.

## [1.24.19] - 2026-08-20

**O Service ficou defasado do Gold que ele lê, e derrubou as views de cruzamento.**

### Fixed
- **Incidente (resolvido no mesmo dia):** o `dbt build` da v1.24.18 publicou as linhas
  `pam`/`ppm` no `gold_produto_agrupamento` de produção, mas o Service seguia na v1.24.14 —
  cuja `produto_catalog()` indexava um dicionário fixo `pevs/comex/comtrade` por
  `c[r.source]`. A primeira linha `pam` levantava `KeyError` e **todas as views multi-fonte
  respondiam 500**. Reproduzido contra o crosswalk real antes de corrigir; Service atualizado
  para v1.24.18 e verificado.

  A causa não foi o código: **a correção do `KeyError` estava no próprio PR que quebrou**. Foi
  a assimetria de entrega — mudanças de dbt chegam à produção no instante do build, mudanças de
  Service só no deploy manual —, que abre uma janela em que o Gold já mudou e o código que o lê
  ainda não.

### Added
- **Workflow `Deploy webapi service`**: a cada merge no `main` que toque
  `src/embrapa_dashboard/**`, `frontend/**`, `pyproject.toml`, `uv.lock` ou `deploy/webapi/**`,
  reconstrói a imagem e aponta o Service com `gcloud run services update --image` cirúrgico —
  env, secret, SA de runtime, escalonamento e anotações do IAP persistem. Depois **lê o Service
  de volta** e falha se a imagem, qualquer env var crítica ou o `iap-enabled` não tiverem
  sobrevivido.

  Fecha a mesma classe que o `ingestion-job-deploy.yml` fechou para o Job — que existia porque
  aquela imagem tinha ficado um mês atrás do `main`. Os dois artefatos agora se mantêm no HEAD
  sozinhos.

  Requer configuração GCP one-time (identidade `sa-webapi-deploy-ci` + variável
  `GCP_WEBAPI_DEPLOY_SERVICE_ACCOUNT`), documentada no cabeçalho. **Enquanto a variável não
  existir o job pula** (verde), então o merge não muda nada.

## [1.24.18] - 2026-08-20

**PAM e PPM entram na ponte entre fontes.** A castanha-de-caju passa a cruzar quatro fontes,
com produção **extrativa (PEVS)** e **cultivada (PAM)** disponíveis no mesmo eixo.

### Added
- **`gold_pam_production` e `gold_ppm_production` unidos ao `gold_produto_agrupamento`** — a
  "coordinated change" que o próprio modelo reservava: união no crosswalk, `pam`/`ppm` no
  `accepted_values`, e os buckets no `seam_base.produto_catalog`.

  **Não altera cálculo nenhum existente.** Toda view multi-fonte pede suas fontes **pelo nome**
  (`_codes(agrupamento_id, 'pevs')` no coeficiente de exportação; `'comex'`/`'comtrade'` no
  market share), então nada soma entre fontes de produção pelas costas do pesquisador. O que
  muda é a **escolha**: a camada multi-fonte é orientada a séries, então PAM e PPM viram séries
  que o pesquisador coloca no eixo ao lado do PEVS e decide, olhando as curvas, se extrativo e
  cultivado se comparam lado a lado ou se somam.

  Uma métrica agregada "extrativo + cultivado", se algum dia for desejada, terá de ser uma
  métrica **nomeada e opcional** — nunca uma mudança silenciosa num denominador existente.

### Fixed
- **Adicionar um banco à ponte não pode mais derrubar as views multi-fonte.** Os buckets do
  `produto_catalog` eram um literal `pevs/comex/comtrade` indexado por `c[r.source]`, então a
  primeira linha de uma fonte nova levantaria `KeyError` e derrubaria **todas** as views de
  cruzamento. Agora derivam de `sqlbuild.GOLD_CODE_SOURCES` (a mesma fonte única que o gate de
  visibilidade e o check de órfãos já usam), e cada agrupamento carrega uma lista — vazia
  quando for o caso — para toda fonte conhecida. O `_codes` também passou a usar `.get`: uma
  fonte desconhecida devolve "sem códigos" em vez de 500.

## [1.24.17] - 2026-08-19

**A cota do COMTRADE é cobrada por CHAMADA, e cada chunk era exatamente uma.** Medido antes
de otimizar — e a medição descartou a otimização que eu vinha recomendando.

### Changed
- **`REPORTER_BATCH_SIZE` 8 → 16** (`comtrade/pipeline.py`): uma re-busca completa cai de
  **864 para 432 chamadas**, passando a caber numa única janela diária (~500) em vez de exigir
  duas.

  A medição que orientou isso: sobre uma corrida mundial completa de 2026-08, as respostas
  reais tiveram média de **9,5 mil linhas** e pico de **35,8 mil**, contra um cap de **100 mil**
  por chamada. O splitter adaptativo, portanto, **nunca dispara** — cada chunk é uma chamada, e
  é o tamanho do lote de reporters, não o splitter, que determina o custo de cota.

  16 mantém margem larga (pico projetado ~72 mil, 72% do cap) e um lote que eventualmente
  estourar continua protegido pelo splitter. **24 projetaria 107 mil, acima do cap**, passando
  a pagar splits e devolvendo o ganho — por isso 16, não mais.

  ⚠ Trocar esta constante **invalida todos os raws arquivados**: o basename é hash do conjunto
  de reporters, então o agrupamento novo não casa com nada e a história inteira é re-buscada.
  Feito agora justamente porque a ampliação de escopo de coco/caju **já obrigava** uma
  re-busca completa — a migração sai junto, e pela metade do custo.

### Nota — a otimização que NÃO foi feita
Vinha recomendando um *re-fetch dirigido*: buscar só os códigos adicionados, em vez do chunk
inteiro. A medição mostrou que ela **não reduziria a cota em nada** — 864 chunks continuariam
sendo 864 chamadas, só com respostas menores. O gargalo era o número de chamadas, não o volume
por chamada. Registrado para não ser reproposta sem novo dado.

Os três testes que fixavam o lote em 8 passam a derivá-lo da constante: testam a lógica de
particionar, não o valor, e não quebram na próxima calibragem.

## [1.24.16] - 2026-08-19

### Fixed
- **A série do coco dessecado terminava em 2014** (`config.py`, `comex_ncm_succession.csv`).
  A v1.24.15 ingeriu `08011110` e `08011190` supondo que `08011100` fosse o código
  pré-revisão sendo desdobrado — **é o contrário**. Os dados provam: os dois rodam de 1997 a
  2014 e param; o `08011100` assume de 2014 em diante. Foi uma **consolidação**, não um
  desdobramento.

  Isso importava porque a incerteza que me fez excluí-lo não existia: um desdobramento exige
  escolher um alvo entre vários (daí a hesitação), mas uma consolidação tem alvo **inequívoco**.
  Os três agora são ingeridos e a seed mapeia o par aposentado em `08011100`, deixando a série
  contínua **1997–2026** em vez de sumir em 2014.

  O catálogo acompanha: `08011100` (atual) entra, `08011110`/`08011190` saem — seu dado é
  normalizado para o atual, então nunca teriam linha própria na Gold e ficariam como lacuna
  permanente no check `Catalog → Gold arrival`.

### Nota
`gold_produto_agrupamento` continua sem `pam`/`ppm` — é **deliberado e documentado** no próprio
modelo ("RESERVED for when PAM cross-source linkage is wired in, not a bug"). Os produtos de PAM
cadastrados aqui (castanha de caju, coco-da-baía) já têm dado na Gold e aparecem nas visões de
banco único; entram no cruzamento quando essa fiação for feita.

## [1.24.15] - 2026-08-19

**Coco e Castanha-de-caju eram agrupamentos vazios; a madeira manufaturada era escopo
excluído de propósito.** O check `Catalog → Gold arrival` apontou 95 produtos cadastrados sem
dado — investigados um a um, deram dois diagnósticos opostos.

### Added
- **Coco e Castanha-de-caju agora existem de verdade.** Os dois apareciam na lista de
  agrupamentos do dashboard com **zero dado de qualquer fonte** — um pesquisador que
  escolhesse qualquer um via nada, sem explicação. Nada no `config.py` documentava exclusão,
  diferente da madeira: era lacuna, não decisão.

  Escopo ampliado nas quatro fontes: **PEVS** `3404` (castanha-de-caju extrativa), **PAM**
  `40143` (castanha de caju) + `40145` (coco-da-baía), **COMEX** 6 NCMs e **COMTRADE** 5 HS6.
  A castanha-de-caju passa a ter as duas óticas — extrativa e cultivada — que é exatamente o
  cruzamento que o painel existe para permitir. Custo medido: ~1,7× no Gold do COMTRADE,
  contra os 15,8× que a madeira manufaturada custaria.

  Duas decisões de granularidade registradas no próprio `config.py`: **`40330` ("Caju", o
  pseudofruto) fica de fora** — é produto diferente da castanha, e juntá-los no mesmo
  agrupamento confundiria fruta com noz; e **`08011100` (NCM pré-revisão) não é ingerido** —
  seu desdobramento em "sem casca/ralados" vs "outros secos" não tem lado dominante óbvio, e
  uma linha de sucessão precisa afirmar um. Chutar seria fabricar história, então o coco começa
  na revisão até um pesquisador decidir o mapeamento.

### Changed
- **90 códigos de madeira manufaturada removidos do catálogo do COMTRADE.** São exatamente os
  que o `config.py` documenta como excluídos — *"manufactured-wood articles (móveis/marcenaria)
  that polluted the whole-chapter scope and are not comparable to PEVS extractive output"*.
  Mantê-los cadastrados fazia o dashboard prometer dado que o desenho decidiu não ter, e o
  check os apontaria como lacuna para sempre.

  Eles apareciam com dado até ontem por **resíduo**: o backfill de 2026-06 tinha escopo mais
  largo, e os anos nunca re-buscados desde então ainda carregavam aquelas linhas. A retomada
  do COMTRADE re-buscou todos os anos assentados e o dedupe por *latest batch* as substituiu —
  terminando de aplicar a migração para totals-only que estava pela metade.

  O catálogo do COMEX já estava alinhado (zero produtos sem dado), tendo passado pela migração
  de granularidade em 02/07. O do COMTRADE era o pendente.

## [1.24.14] - 2026-08-18

### Fixed
- **A tela prometia que uma edição valia "em alguns minutos" — erra por até um dia**
  (`ViewCadastroProdutos.jsx`). Os marts de serving aplicam o gate de visibilidade no **build**
  (`hidden_code_predicate`), e a prod se reconstrói no agendamento **diário** do
  `dbt-build-prod` (`cron: '30 11 * * *'` = 08:30 BRT). Um pesquisador que ocultasse um produto,
  esperasse cinco minutos e continuasse vendo-o nos gráficos concluiria — com razão — que o
  controle está quebrado.

  As cinco ocorrências passam a nomear a cadência real: confirmação de ocultar (individual e em
  lote), o aviso anexado aos toasts de salvar/renomear, e a legenda de ajuda. Teste novo trava a
  promessa, para "alguns minutos" não voltar.

- **A ajuda de "Adicionar produto" prometia ingestão para qualquer fonte**, mesmo agora que a
  tela já distingue por banco (v1.24.9). O texto passa a dizer que o produto entra como
  *pendente de ingestão* nas fontes dirigidas pelo cadastro e como *sem dados* nas demais, cujo
  escopo vem da configuração do pipeline.

## [1.24.13] - 2026-08-18

**Limpar uma anotação pela tela tinha parado de funcionar** — regressão introduzida hoje,
encontrada testando as ações do Cadastro à mão.

### Fixed
- **`''` no campo ✎ voltou a apagar a anotação** (`webapi/routes.py`). Duas mudanças se
  anularam: o writer passou a **preservar** um `descricao_produto` omitido (v1.24.8, para que
  uma edição não relacionada não apague a nota do pesquisador), enquanto a rota já colapsava
  `''` → `None` para **todos** os campos. Juntas: `None` virou "mantenha" e `''` virou `None`,
  então a nota limpa **reaparecia** na recarga — sem erro, sem aviso e sem caminho para
  removê-la.

  `_coerce_str_fields` ganhou `keep_blank`, e `descricao_produto` entra nele: para os demais
  campos em branco continua significando ausente (é o que faz o 400 de campo obrigatório
  funcionar), mas para a anotação **ausente = manter, `''` = apagar**, e os dois sentidos
  agora atravessam a pilha inteira sem se perder.

  Vale o registro de como apareceu: os testes de unidade da preservação passavam (cobriam o
  writer) e os da rota também (cobriam a coerção). O defeito só existia na **junção** dos
  dois — e só apareceu ao limpar uma nota pela interface de verdade.

## [1.24.12] - 2026-08-18

**A cota diária do UN Comtrade responde 403, não 429 — e por isso paginava um humano.**
Descoberto na primeira execução real do backfill de escopo.

### Fixed
- **403 "Out of call volume quota" agora vira `ComtradeQuotaError`**
  (`comtrade/client.py`). O backfill rodou 1h39, arquivou **508 chunks** e então bateu a cota
  diária. A API sinaliza isso com **403**:

      {"statusCode":403,"message":"Out of call volume quota.
       Quota will be replenished in 19:07:31."}

  O cliente só mapeava **429** para cota, então o 403 caía em `ComtradeRequestError` — "not
  transient" — e a execução saía **1**, disparando o alerta vermelho de "unexpected —
  investigate" para a condição mais esperada e autocurável que existe nesse pipeline. Toda a
  infraestrutura para tratá-la bem já existia (a classe, o "pare e re-execute" do CLI, o
  código de saída limpo, o raw resumível); faltava só reconhecer o status certo.

  **Casado pela mensagem, não pelo status:** um 403 de chave revogada ou inválida continua
  sendo falha real e segue paginando — lavá-lo como "cota, tente depois" travaria a ingestão
  em silêncio para sempre.

  Nada se perdeu: os 508 chunks estão arquivados e a re-execução retoma exatamente os
  restantes. E como os já processados foram regravados com o `cmd_scope` atual, eles pulam —
  a retomada custa só o que falta.

## [1.24.11] - 2026-08-17

### Fixed
- **Um re-fetch por escopo ampliado logava DUAS razões, e uma era falsa**
  (`comtrade/pipeline.py`). A checagem de escopo da v1.24.10 entrou como *fall-through*, então
  um ano assentado re-buscado por escopo também imprimia *"recent year — re-fetching"* —
  visivelmente errado para, digamos, o ano 2000. Pego observando a primeira execução real de
  ponta a ponta. Agora é `else`: cada caminho imprime **uma** razão, e a correta. O
  comportamento sempre esteve certo; o log é que desorientava quem fosse diagnosticar o gasto
  de cota.

## [1.24.10] - 2026-08-17

**A última fonte sem defesa contra ampliação de escopo, e uma rede que cobre as futuras.**

### Fixed
- **COMTRADE agora retroage a história quando um produto é adicionado**
  (`comtrade/pipeline.py`). Um ano "assentado" cujo raw já existia era pulado para sempre —
  correto enquanto o escopo é estável, e **errado** no instante em que um produto entra: o
  objeto arquivado só contém os códigos pedidos na época, então o produto novo apareceria
  apenas a partir da janela de re-fetch recente. Truncamento silencioso de história, do tipo
  que o pesquisador não tem como perceber.

  O `cmd_scope` **já era gravado** na proveniência do raw (confirmado: 400/400 objetos
  amostrados o carregam) — faltava consultá-lo. Agora um ano assentado é re-buscado quando o
  escopo gravado não cobre os códigos configurados.

  **Deliberadamente unidirecional:** só códigos *adicionados* disparam trabalho. Remover ou
  reordenar deixa o superconjunto arquivado perfeitamente utilizável (o Silver filtra), e
  re-buscar por isso queimaria a cota diária à toa. Objeto sem `cmd_scope` gravado não dispara
  nada — não dá para saber o que ele cobria, e chutar "re-buscar" re-cobraria o acervo inteiro
  por um palpite.

  Com isso as três famílias de pipeline finalmente cumprem a mesma promessa, cada uma pela
  economia da sua fonte: IBGE re-consulta o SIDRA em janela completa quando um produto está
  ausente do Bronze; COMEX re-filtra o raw arquivado quando o fingerprint do filtro muda (sem
  tocar na fonte); COMTRADE re-busca o ano assentado quando o `cmd_scope` ficou defasado.

### Added
- **Check `Catalog → Gold arrival` no `embrapa doctor`**: produtos cadastrados sem dado
  nenhum na Gold, agrupados por banco. É a rede **agnóstica de fonte** para a classe inteira
  — não importa *como* um banco ingere, só se o que o pesquisador cadastrou de fato apareceu.

  É o que faltava para que a falha do COMTRADE fosse visível: ela existia desde sempre e
  **nenhum** sinal a reportava. Um banco futuro, com mecanismo ausente ou quebrado, ganha a
  mesma proteção de graça — que é justamente o caso que nenhum teste por pipeline cobre.

  Consultivo (`ok=True`): um produto cadastrado há minutos está legitimamente vazio. Medido
  antes de construir para não repetir o erro do check de órfãos: **2 de 308** hoje, e os dois
  são exatamente os códigos de bambu do COMTRADE. Zero ruído.

## [1.24.9] - 2026-08-16

**Bambu entra no dashboard — e o teste prático do cadastro revelou uma promessa falsa na
tela.** Percorrido o fluxo real de ponta a ponta (criar agrupamento → cadastrar produtos
pelo formulário → conferir status), como um pesquisador faria.

### Added
- **Bambu no escopo de ingestão** (`config.py`): `14011000` (bambus para cestaria) e
  `20059100` (brotos de bambu) no COMEX; os SH6 equivalentes `140110` / `200591` no
  COMTRADE. Códigos confirmados na **referência HS oficial do UN Comtrade** e na
  **nomenclatura NCM do MDIC** — não deduzidos.

  Ingerido por **NCM explícita, não por heading**: cada SH6 de bambu tem um único NCM (sem
  desdobramento brasileiro), e as headings seriam largas demais — `1401` arrasta
  ratan/vime/junco, `2005` traria todo o capítulo de conservas vegetais. Escopo =
  matéria-prima agrícola; manufaturados de bambu (móveis, pisos, utensílios, celulose) ficam
  **fora**, pela mesma razão que a madeira largou o capítulo inteiro.

  Registro no catálogo de Curadoria feito **pela própria tela**, sob o agrupamento "Bambu".
  Nota de campo: **bambu não existe em nenhuma fonte do IBGE** (confirmado nas tabelas SIDRA
  289, 5457, 3939 e 74) — só vem do comércio exterior.

### Fixed
- **A tela de Cadastro prometia uma ingestão que nunca viria** (`ViewCadastroProdutos.jsx`,
  `webapi/seam_curation.py`, `ibge/catalog_resolver.py`). Ao cadastrar um código ainda não
  ingerido, o aviso dizia *"será buscado na próxima ingestão"* — e o status repetia
  *"Pendente de ingestão"* — para **qualquer** banco.

  É falso para COMEX e COMTRADE: o `catalog_resolver` é usado só pelos três pipelines do
  IBGE, e o escopo do comércio exterior vem da configuração. Um produto cadastrado ali fica
  "pendente" para sempre. E é falso para **todos** os bancos quando
  `catalog_authoritative_ingestion` está desligado — flag que o frontend sequer conhecia.

  Novo `catalog_driven_bancos()` reporta quais bancos um cadastro **de fato** dirige (o
  conjunto do IBGE ∩ flag ligado), exposto em `/api/catalog/entries`. Fora dessa lista a tela
  agora diz o que é verdade: status **"Sem dados"** e um aviso explicando que o escopo da
  fonte vem da configuração do pipeline, com o tom de alerta em vez do neutro que sugeria
  "aguarde". O código já raciocinava sobre isso no caso vizinho — havia um comentário
  dizendo que chamar um produto pausado de "pendente" *"would promise an ingestion that will
  never come"* —, mas o caso por banco tinha passado.

## [1.24.8] - 2026-08-16

**Dois diagnósticos que mentiam em silêncio**, achados na verificação final da sessão.

### Fixed
- **O check de órfãos do `doctor` contava tombstones, não órfãos** (`doctor.py`). Um órfão é
  uma remoção que **deixou dado para trás** — tombstone (`active=false`) **e** o código exato
  ainda presente no Gold do banco. Só esses são marcados pelo `mark-orphans`. Contando
  tombstones puros, uma remoção **limpa** (sem dado remanescente) nunca é marcada — e
  corretamente, não há o que expurgar —, então `removed > marked` virava o estado permanente
  após qualquer faxina.

  O resultado: o check avisava para sempre, culpava um passo de build que na verdade tinha
  rodado com sucesso (`detected=0`), e prescrevia um `mark-orphans` que era no-op garantido.
  Neste repositório, a migração dos catálogos de comércio de HS-4 para NCM-8/HS-6 em
  **02/07** deixou 20 tombstones limpos, e o alerta era 100% falso positivo desde então. O
  custo real não é o texto — é treinar o operador a ignorar a saída do `doctor`.

  A constante `GOLD_CODE_SOURCES` (banco → tabela Gold + coluna do código) saiu do `gateway`
  para o `serving/sql.py`, que é flask-free: os dois consumidores — a worklist de
  Descontinuados na UI e o check do `doctor`, que roda num `embrapa doctor` puro e por isso
  não pode importar o gateway — precisam concordar sobre o que é um órfão.

- **`frontend/package.json` estava em 1.11.0** contra um projeto em 1.24.7 — treze minors
  atrás, enquanto um comentário no `ViewAbout.jsx` afirmava que era "kept in sync". Ele é o
  fallback de pré-carga do número de versão, então a **primeira pintura** da página *Sobre*
  mostrava uma versão errada até `/api/source-meta` resolver. Sincronizado (manifest + os dois
  campos do `package-lock.json`) e agora **coberto por teste**, que falha se divergirem do
  `pyproject.toml` — a afirmação do comentário deixa de ser aspiracional.

## [1.24.7] - 2026-08-16

**A versão do node não estava declarada em lugar nenhum** — CI, Dockerfile e dev local
podiam divergir sem nada avisar, e divergiam.

### Added
- **`.nvmrc` (node 22) como fonte única**, lido agora pelo `ci.yml` e pelo `release.yml` via
  `node-version-file` em vez de `"22"` escrito à mão nos dois. O `deploy/webapi/Dockerfile`
  ganhou comentário amarrando o `node:22-slim` a ele. Antes, a versão aparecia hardcoded em
  três lugares independentes e em nenhum que uma máquina de desenvolvimento fosse ler.

  O sintoma que revelou isso: com node 25 local, os **36 testes do `AppShell` falham** com
  `localStorage.removeItem is not a function` — uma interação do jsdom, sem relação com o
  código — enquanto o CI, em node 22, fica verde. Um desenvolvedor perseguiria um bug que não
  existe, ou pior, ignoraria a suíte por considerá-la quebrada. Sob node 22 passam 787/787.

- **Nota em `docs/testing.md`** com o caminho para alinhar, inclusive sem gerenciador de versão
  (`brew install node@22`, keg-only, sem tocar no node global).

Fecha o outro lado da regra de node do #256: lá, impedir que a base do Dockerfile suba de major
sozinha; aqui, garantir que os três pontos concordem e que o dev local saiba qual é.

## [1.24.6] - 2026-08-16

**A data ao lado da versão, na página *Sobre*, não era a data da versão.**

### Fixed
- **A data exibida ao lado da versão passa a ser a data da release**
  (`ViewAbout.jsx`, `webapi/serializers.py`, novo `embrapa_dashboard/release.py`). Sob um único
  rótulo "Versão", a linha juntava a versão do app com a **data de refresh do Gold do PEVS** —
  então lia-se `v1.24.3 · 01 ago 2026` para um build publicado naquele mesmo dia. Dois problemas
  num campo só: a versão parecia velha, e a data falava por *um* banco entre cinco, escolhido
  silenciosamente (o PEVS é o mais parado; o PAM atualizou hoje).

  A data agora vem do `CHANGELOG.md` — a mesma fonte única que o `release.yml` já usa para
  compor o corpo da GitHub Release, então ela não tem como divergir do registro de release.
  Nada é gerado no build nem hardcoded: **versão sem seção no CHANGELOG simplesmente não tem
  data, e a UI mostra a versão sozinha** em vez de inventar uma. Substituir por "hoje"
  apresentaria um build antigo como recém-publicado — exatamente a desonestidade que este
  campo existe para remover.

  Frescor por banco continua sendo trabalho do hero, da *Saúde do sistema* e de *Dados*, que
  dizem a qual banco cada data pertence.

  O `CHANGELOG.md` passa a ser copiado para a imagem do webapi (fica em `/app`, ao lado do
  `pyproject.toml`; o pacote instala sob `/app/.venv/…`, então uma busca relativa ao `__file__`
  não o encontraria). Um teste roda contra o CHANGELOG **real** e falha se a versão publicada
  não tiver seção — guarda de que o checklist de release foi seguido.

## [1.24.5] - 2026-08-16

**Dependabot agrupava majors com patches, e o resultado é que nada entrava.** Três PRs
abertos (o mais antigo de 23/06) travados pelo mesmo motivo estrutural.

### Changed
- **Grupos do Dependabot restritos a `minor`/`patch`** (`.github/dependabot.yml`, os três
  grupos: github-actions, python, npm). Um bump breaking em qualquer ponto do grupo bloqueava
  **todos** os bumps seguros junto — o PR apodrecia e, um mês depois, ninguém distinguia mais o
  rotineiro do arriscado. Majors continuam chegando, agora como PRs **individuais**, um por
  dependência, cada um revisável e revertível sozinho.

  O caso concreto: o PR #242 empacotou `react` 18→19, `plotly.js` 2→3, `maplibre-gl` 4→6 e
  `eslint` 9→10 com uma dúzia de patches de rotina. Os três primeiros são breaking changes na UI
  **viva** (gráficos, coroplético, renderização); o `eslint` 10 ainda quebrava o `npm ci` de
  saída, por conflito com o peer range do `eslint-plugin-react`. Nada ali podia entrar, nem o
  que era seguro.

- **Base `node` do Dockerfile do webapi fixada no major** (mesmo arquivo), espelhando a regra
  que já existia para o `python`. `ci.yml` e `release.yml` rodam build e testes da SPA em
  **node 22**; um bump de major só no Dockerfile publicaria um bundle de produção compilado por
  um runtime que nenhum job de CI exercita. **A divergência é o risco — não o build falhar.** Um
  PR de node 26 ficou ~2 meses aberto exatamente por isso. Bumps de patch do major fixado seguem
  fluindo; mover de major é migração deliberada, mudando Dockerfile **e** os dois workflows
  juntos, de preferência para uma linha LTS.

## [1.24.4] - 2026-08-16

**A imagem do Job de ingestão ficou um mês atrás do `main` — e ninguém tinha como perceber.**
Descoberto ao disparar o Job manualmente para validar a v1.24.3.

### Added
- **Workflow `Deploy ingestion job`** (`.github/workflows/ingestion-job-deploy.yml`): a cada
  merge no `main` que toque `src/embrapa_dashboard/**`, `pyproject.toml`, `uv.lock` ou
  `deploy/ingestion/**`, reconstrói a imagem e aponta o Job para ela com um
  `gcloud run jobs update --image` cirúrgico — só a imagem muda, então env, o secret
  `COMTRADE_API_KEY`, a SA de runtime, `maxRetries` e o timeout persistem. **Nunca executa**
  o Job (a identidade de CI não recebe `run.jobs.run`); a próxima execução agendada pega a
  imagem. A tag é o SHA curto do commit, para que "qual commit o Job está rodando?" seja
  respondível pelo console — a defasagem passou despercebida justamente por não ser.

  Não entrou no `release.yml` de propósito: aquele workflow **desacopla build de deploy** por
  design, e não foi uma tag `v*` que defasou — foi o `main` andando à frente do Job. O
  precedente correto é o `dbt-build-prod.yml`, que já auto-roda contra prod no merge. Auto-deploy
  é seguro para *este* artefato: é batch, sem UI e sem sessão de usuário viva — a imagem nova só
  afeta a próxima execução, e o rollback é um `--image <anterior>`. O Service do webapi segue
  manual.

  Requer configuração GCP one-time (identidade dedicada `sa-ingest-deploy-ci` + variável
  `GCP_INGEST_DEPLOY_SERVICE_ACCOUNT`), documentada no cabeçalho do workflow. **Enquanto a
  variável não existir o job pula** (verde), então o merge não muda nada e o workflow se ativa
  sozinho depois.

### Contexto — o que a defasagem custou
O Job rodava a imagem `v1.17.0`, de 14/07, até 16/08. A correção de alertas transientes da
v1.19.0 nunca chegou à produção, então a execução mensal do UN Comtrade saía 1 e disparava
alerta vermelho nos dias 15/07 e 15/08 — em ambos os casos por 2 chunks com `HTTP 429`
rate-limited (`Retry-After` de 6s e 13s, ou seja `ComtradeTransientError`) contra 862 chunks
bem-sucedidos. O log de 15/08 prova a versão: a linha de resumo não traz o qualificador
`(all transient — expected)` que o código atual sempre imprime.

## [1.24.3] - 2026-08-16

**Segunda rodada da auditoria — verificação mais profunda e busca por bugs relacionados.**
Um achado ativo em produção e uma assimetria latente; três suspeitas foram investigadas e
descartadas (ver *Verificado*).

### Fixed
- **PAM e PPM ainda alertavam em falha transiente** (`cli.py`): a correção da v1.24.2 cobriu os
  comandos em chunks (`ibge-batch`/`comex`/`comtrade`) e os multi-fonte (`all`/`reconcile`), mas
  os de **disparo único** continuaram sem tratamento — a exceção subia crua e o typer saía 1.
  Dois deles têm gatilho próprio do Cloud Scheduler **habilitado em produção**
  (`embrapa-ingest-all-pam-monthly`, dia 2; `embrapa-ingest-all-ppm-monthly`, dia 3), usam o
  mesmo cliente SIDRA que levanta `SidraTransientError`, e a política de alerta observa o
  `result="failed"` do **job** — não os argumentos do comando. Ou seja: uma instabilidade do
  SIDRA nos dias 2 ou 3 disparava o mesmo e-mail vermelho de "falha inesperada" que um bug real.
  Novo `_transient_aware_exit` (gêmeo de disparo único do `_summarize_and_exit`) aplicado a
  `ibge`, `ibge-pam`, `ibge-ppm`, `bcb-inflation` e `bcb-currency`. Entra **por fora** do
  `pipeline_run`, então o log de eventos ainda registra a falha antes do código de saída ser
  rebaixado; qualquer exceção não marcada continua propagando intacta (saída 1, com traceback).

### Changed
- **`descricao_produto` agora é preserve-on-omit** (`serving/curation.py`): a escrita é um
  overwrite de linha inteira, e os dois eixos de ciclo de vida e o `sidra_tabela` já preservavam
  o valor armazenado quando omitidos — a anotação livre do pesquisador, não. Nenhum cliente vivo
  disparava isso (a UI reenvia a entrada inteira em todos os caminhos, e o
  `seed_catalog_from_env` é protegido pela deduplicação do `change_id` determinístico), mas a
  assimetria deixava um PATCH parcial de script/curl apagar anotações em silêncio — e uma nota
  digitada à mão, diferente de um eixo, não se recupera de um dropdown. `None` = omitido
  (preserva); `''` = limpeza explícita (grava), que é como o campo ✎ esvazia uma nota.

### Verificado (investigado, sem defeito)
- **Reescrita `EXISTS`→`JOIN` da detecção de órfãos** (v1.19.0): preserva a semântica —
  `tombstoned` tem exatamente uma linha por `(codigo_produto, banco)` (`_rn = 1`), então as
  quatro colunas do fan-out do join são idênticas e o `distinct` colapsa de volta a uma linha.
- **Leitura do Gold na detecção de órfãos não passa pelo gate de visibilidade** — correto e
  proposital: ocultar um produto não pode escondê-lo da detecção, senão "ocultar + remover"
  deixaria dado órfão invisível para sempre.
- **`auto_mark_orphans` escreve em log separado** (`catalog_lifecycle_log`, não
  `produto_catalog_log`): o detector automático não tem como sobrescrever linha de catálogo nem
  apagar anotação.

## [1.24.2] - 2026-08-16

**Correção dos 3 achados da auditoria da própria sessão (v1.19.0 → v1.24.1).** Nenhum causava
perda de dado nem expunha produto oculto; o segundo era silencioso.

### Fixed
- **Chunks do IBGE em lote nunca eram marcados como transientes** (`cli.py`): o `ChunkOutcome`
  do caminho de falha era criado sem `transient=`, então `ingest ibge-batch` e a fase IBGE do
  `reconcile` sempre saíam com código 1 e disparavam o alerta — mesmo numa queda de conexão do
  SIDRA, que se autocorrige na próxima execução. É justamente a falha que esse comando existe
  para sobreviver (janelas grandes), e COMEX/COMTRADE já marcavam. A direção do erro era segura
  (alerta a mais), mas a feature não funcionava na fonte transiente mais provável.
- **Coluna ausente fazia a ingestão abandonar o catálogo em silêncio**
  (`ibge/catalog_resolver.py`): a consulta passou a referenciar `ingestao`; numa tabela que
  ainda não tem essa coluna o `BadRequest` era engolido pelo `except` amplo do chamador e a
  ingestão caía para os códigos do `.env` — deixando de buscar o que o pesquisador cadastrou e
  buscando o que ele **pausou**, tudo com o job saindo 0 (nada alertava). Agora o resolver
  refaz a consulta **sem o filtro de pausa**, o que é exatamente equivalente: se a coluna não
  existe, nenhuma linha pode estar pausada. O caminho de leitura já tinha proteção análoga.
- **Renomear agrupamento fazia uma consulta extra por membro** (`serving/agrupamentos.py`):
  `_restamp_members` não repassava os dois eixos, então cada membro caía no ramo de preservação
  do writer e disparava um `_current_lifecycle` — apesar de a linha já ter sido lida. Num
  agrupamento grande (Madeira tem 226 entradas) isso somava ~20-25% a uma operação já lenta.
  Os eixos agora são repassados; a leitura tolera uma tabela pré-split (senão o rename passaria
  a quebrar nela, que seria a mesma classe de bug do achado anterior).

### Changed
- 6 testes novos fixam as três correções: falha transiente do IBGE sai 0 **e** uma não-transiente
  junto ainda sai 1; o resolver continua usando o catálogo quando a coluna falta (e o filtro de
  pausa está mesmo na consulta); o rename repassa `ingestao`/`visibilidade` e sobrevive à tabela
  antiga.

## [1.24.1] - 2026-08-16

### Changed
- **A legenda do Cadastro separa visualmente "o que se lê" de "o que se faz".** Antes as duas
  seções eram divididas só por um espaçamento e um título pequeno, e como a grade de duas
  colunas seguia igual dos dois lados, tudo lia como uma lista contínua. Agora cada metade é
  um painel delimitado (borda, fundo próprio e título com régua e contagem), com uma faixa
  lateral que carrega o tipo: **azul** para a referência (colunas) e **verde** para o que
  escreve (edições) — a mesma convenção de acento do bloco de convenções métricas.
- Títulos mais diretos: "O que cada coluna mostra" e "O que cada edição faz", no lugar de
  "As colunas" / "As edições".

## [1.24.0] - 2026-08-16

### Added
- **Legenda in-product no Cadastro de produtos**: "Como ler esta tabela e o que cada edição
  faz" — o que cada uma das 10 colunas representa e o que cada uma das 8 edições realmente
  provoca. Recolhida por padrão (mesmo padrão `<details>` da legenda de flags da Qualidade),
  então não empurra a tabela para baixo.
- As edições ganharam **etiquetas de consequência** — *reversível*, *pede confirmação*,
  *em lote* — porque o risco real varia muito entre elas e não dava para inferir da tela.
  A legenda é explícita justamente nos dois pontos mais fáceis de ler errado: **remover não
  apaga dado** (os dados ficam órfãos no Gold, só um operador apaga, com backup) e **ocultar
  não para a ingestão** (é só decisão de exibição). Fecha lembrando que o registro é
  somente-adição e que as mudanças valem na próxima atualização.

### Changed
- O card de introdução dizia que "o **Ciclo de Vida** controla a exibição" — desatualizado
  desde a divisão em dois eixos (v1.23.0). Agora explica que **Ingestão** e **Exibição**
  controlam, separadamente, se o pipeline busca dados novos e se o pesquisador vê o produto.
- Um teste passa a exigir que **toda coluna da tabela esteja documentada** na legenda: se
  alguém adicionar uma coluna e esquecer de explicá-la, o teste quebra em vez de o
  pesquisador encontrar um cabeçalho sem explicação. Os contadores do resumo ("10 colunas ·
  8 ações") saem dos dados, não são digitados à mão.

## [1.23.1] - 2026-08-16

### Changed
- **"Ingestão" e "Exibição" viraram colunas próprias no Cadastro de produtos**, no lugar
  dos dois seletores empilhados dentro de uma coluna "Ciclo de vida". Os dois eixos são
  decisões independentes, então lêem melhor como irmãos de "Agrupamento" do que como duas
  metades de um campo composto — e o `<th>` passa a rotular cada seletor, dispensando os
  rótulos internos que a célula fundida exigia. No mobile o ganho é maior: cada eixo vira
  uma linha rotulada do card, sem a duplicação de rótulo que havia antes.
- Larguras rebalanceadas para 10 colunas, sem scroll horizontal e sem select cortado
  (verificado em 1400px, 1280px e 375px). A ~1280px os 10 cabeçalhos não cabem todos em
  uma linha; a folga foi deixada com **"Descrição (fonte)"**, que quebra no espaço
  ("Descrição / (fonte)") — dar esse ponto percentual a ela faria "Agrupamento", uma
  palavra só, quebrar no meio ("Agrupame/nto"), o que lê como defeito. Uma linha de
  cabeçalho um pouco mais alta, não.

## [1.23.0] - 2026-08-16

**Ciclo de vida do produto virou DOIS EIXOS independentes, com códigos estáveis.** O enum
único de duas frases era um antipadrão em três frentes: prometia uma escolha sobre ingestão
que não existia, chamava-se "ciclo de vida" controlando só visibilidade, e a frase pt-BR de
exibição *era* a chave no banco.

### Added
- **Eixo `ingestao` (ativa | pausada).** "Pausada" congela a série: para de buscar dados
  novos e mantém todo o histórico no Gold — e o produto **continua visível**. Antes esse
  estado era inexprimível: as duas opções começavam com "Fazer Ingestão" e o
  `catalog_resolver` **nunca lia a coluna**, então a única forma de parar a ingestão era
  *remover* o produto, virando órfão à espera de purga. Agora o resolver filtra de verdade.
- **Coluna `Status` derivada (somente leitura)** — Ativo / Oculto / Pausado / Pendente de
  ingestão. É consequência dos eixos, nunca um controle: era exatamente o que faltava, já
  que o dropdown antigo se chamava "ciclo de vida" mas governava um eixo só. Absorveu a
  coluna "Dados" (produto sem linhas na Gold = pendente de ingestão era o mesmo fato dito
  duas vezes), então a tabela **manteve 9 colunas** e o alinhamento conquistado na v1.20.1.

### Changed
- **Eixo `visibilidade` (visivel | oculto) com código estável.** A frase
  `'Fazer Ingestão mas deixar indisponível'` estava hardcoded em `dim_produto_visibility.sql`,
  no Python e no dropdown — renomear o rótulo exigia migração de dados coordenada em três
  lugares, e uma divergência silenciosa faria o gate **fail open**. Agora o banco guarda
  `oculto` e o rótulo pt-BR existe só na UI.
- **Migração sem reescrever histórico.** O log é append-only: as linhas antigas continuam
  com a prosa e são **traduzidas na leitura** pelo macro `catalog_lifecycle` (SQL) e por
  `visibilidade_efetiva`/`ingestao_efetiva` (Python) — gêmeos, com um teste fixando a tabela
  verdade dos dois. Valor desconhecido **nunca** oculta: o gate falha para o lado seguro.
- **Preservação de eixo no servidor.** Omitir um eixo num update preserva o valor guardado.
  O writer sobrescreve a linha inteira, então antes uma edição não relacionada (renomear o
  agrupamento) apagava o `ciclo_de_vida` — só não quebrava porque a UI reenviava tudo. Agora
  qualquer cliente ou script está seguro por padrão.
- Verificado contra a **produção**: a lógica antiga e a nova escondem exatamente os **mesmos
  3 produtos** entre os 308 ativos; o teste unitário do gate cobre linha legada, linha nova,
  a transição entre elas, independência dos eixos e o caso tudo-NULL. Colunas adicionadas à
  tabela real antes do deploy (aditivas, nullable) — expandir o schema antes de subir o
  código evita que o `dbt build` quebre ao selecionar coluna inexistente.

---

## [1.22.0] - 2026-08-16

**As séries do BCB — câmbio PTAX e índices de inflação — agora aparecem em "Tabelas de
referência".** São a calibração por trás de todo valor monetário exibido, mas só eram
consultáveis dentro de "Estrutura de dados", na camada Silver de cada banco.

### Added
- **"Câmbio PTAX (BCB)"** (17.386 linhas, USD e EUR, desde 1984) e **"Índices de inflação
  (BCB)"** (1.564 linhas, IPCA/IGP-M/IGP-DI desde 1980, com variação mensal e índice
  encadeado) na perspectiva **Referências**, com a mesma grade read-only das demais
  (paginação e ordenação no servidor, filtro por coluna, exportação, e o botão de reportar
  valor suspeito). Elas respondem exatamente às perguntas "de onde veio essa cotação?" e
  "qual índice foi aplicado nessa correção?" — o mesmo ato de consultar
  `historical_currency_factors`, que já estava listado. A inconsistência era ter a metade
  "moedas antigas → Real" visível e a metade "BRL ↔ USD/EUR" não.

### Changed
- **Novo catálogo `_REFERENCE_TABLE_CATALOG`, separado de `_SEED_CATALOG`.** As tabelas do
  BCB são modelos dbt alimentados por ingestão, não seeds CSV — e um teste existente exige
  uma **bijeção estrita** entre `_SEED_CATALOG` e `dbt/seeds/*.csv` (para que um seed novo
  nunca passe despercebido sem ser exposto). Em vez de afrouxar essa invariante, os dois
  catálogos ficam separados e se juntam só no ponto de leitura (`_CONSULTABLE_BY_ID`), que
  é o allowlist de segurança do endpoint. Ambas as tabelas vivem no mesmo dataset `silver`,
  então o caminho de leitura é idêntico.
- **Novo teste espelhando o rigor do existente**: cada id de `_REFERENCE_TABLE_CATALOG`
  precisa ter um modelo dbt `<id>.sql` correspondente, os dois catálogos precisam ser
  disjuntos, e tudo que é listado precisa ser resolvível. Sem isso, um id renomeado só
  falharia na leitura, como um 404 do BigQuery — a mesma classe de bug que o teste dos
  seeds previne.
- **Ordem do seletor por TEMA, não por catálogo de origem** (`_REFERENCE_DISPLAY_AFTER`):
  as duas tabelas do BCB aparecem logo após "Fatores de reforma monetária", de modo que
  reforma monetária → câmbio → inflação se leiam como uma história só, em vez de as do BCB
  ficarem no fim, depois das dimensões de fonte. Um teste garante que o reordenamento é
  *loss-free* (nada sumido nem duplicado) antes de checar a adjacência — reordenar lista é
  justamente o tipo de código que perde um item silenciosamente.
- Verificado ao vivo contra o BigQuery de produção: as duas tabelas carregam com dados
  reais, ordenação e paginação funcionam até o fim das 17 mil linhas, e um id fora do
  allowlist continua recebendo 400.

---

## [1.21.0] - 2026-08-16

**O título da página voltou a ser a primeira coisa da página.** Nas perspectivas, os blocos de
filtro e de convenções métricas eram renderizados ACIMA do `MainScreen` — ou seja, dois blocos
de controles vinham antes do `<h1>` da própria página.

### Changed
- **`page-hero` agora precede as barras de filtro e de convenções métricas.** O `<h1>` da view
  é o **único** cabeçalho da página (o AppShell não tem nenhum), e vinha em terceiro lugar
  dentro do `<main>`. Isso penalizava justamente quem depende de estrutura: navegar por
  cabeçalhos é um dos modos principais de leitores de tela, e a ordem de tabulação chegava a
  "Editar filtros" / "Exportar CSV" / "Editar métricas" antes de qualquer indicação de em que
  página se está. Também era a causa de o hero ficar empurrado para baixo — o problema que
  motivou recolher o bloco de convenções na v1.20.0. Nova ordem: hero → filtros → convenções →
  conteúdo.
- **Implementado como *slot*, não como prop drilling.** As duas barras continuam sendo
  construídas e conectadas no `main.jsx` (estado, handlers e condições de renderização
  inalterados) e são passadas ao `MainScreen` por um único prop `controls`, que decide apenas
  ONDE colocá-las. Isso evitou passar ~7 props (`onOpen`/`onExport`/`setConventions`/
  `metricsExpanded`/…) e manteve o `MainScreen` sem conhecer o encanamento de filtros.
- **Deliberadamente NÃO usamos `order` do flexbox**, que seria o atalho óbvio: ele reordena só
  o visual e deixa o DOM intacto, então leitor de tela e tabulação continuariam na ordem
  antiga — trocaria um problema de acessibilidade por outro (descasamento entre ordem visual e
  ordem de leitura, WCAG 1.3.2), consertando apenas o sintoma estético.
- Visibilidade preservada: `{controls}` foi inserido nos **6** branches do `MainScreen` que já
  mostravam as barras (view normal, glossário do banco com e sem verbete, banco *planejado* —
  onde a barra aparece no modo *preview* e as convenções seguem ausentes por não ser banco
  live —, view incompatível e view *em breve*). Páginas informativas continuam sem as barras.
  Espaçamento idêntico: `.screen` tem o mesmo `flex column; gap: 24px` do `.content`.
  Verificado ao vivo em cada branch pela ordem real do DOM (não só pelo visual), incluindo que
  trocar a moeda continua aplicando e mantendo o painel de convenções aberto.

---

## [1.20.1] - 2026-08-15

**Cadastro de produtos: a célula "Descrição" carregava três linhas sem rótulo — duas delas
nem pertenciam ali.** Reorganização, sem coluna nova e sem truncar nada.

### Changed
- **A tag da tabela SIDRA saiu da Descrição e foi para junto do Banco.** "Rebanho (efetivo)" /
  "Produção animal" identifica de QUAL das duas tabelas SIDRA a linha veio — o PPM é o único
  banco que guarda duas tabelas (3939 rebanho / 74 produção animal) sob o mesmo token, então o
  mesmo produto pode estar cadastrado duas vezes e a tag é o que as distingue. É metadado da
  FONTE, irmão do banco e do código; renderizada logo abaixo da anotação do pesquisador, lia-se
  como parte da anotação. Agora fica sob o nome do banco (`.cc-sidra-tag`), tingida como
  metadado de fonte e quebrando linha em vez de truncar.
- **A anotação vazia deixou de ocupar todas as ~300 linhas.** O placeholder aparecia em toda
  linha do cadastro, mesmo sem anotação — a maior fonte de ruído visual da tela. Agora uma
  anotação vazia fica transparente e só aparece ao passar o mouse na linha (como um "+ anotação"),
  ou ao receber foco pelo teclado (`:focus-within`). Usa `opacity`, não `display`/`visibility`:
  a caixa permanece, então a altura da linha não "pula" quando o ponteiro cruza a tabela, e o
  campo continua na árvore de acessibilidade e alcançável por Tab. Uma anotação PREENCHIDA nunca
  é afetada (segue sempre visível) e recuperou o marcador **✎** que a distingue da descrição da
  fonte logo acima. Em telas de toque (≤768px), onde não há hover, a anotação vazia permanece
  visível — senão ficaria invisível e sem como ser descoberta. Para quem está em **modo somente
  leitura**, o "+ anotação" nem aparece no hover: não faz sentido oferecer uma ação indisponível.
  Verificado ao vivo com os 308 produtos reais: 95 anotações vazias invisíveis, 213 preenchidas
  visíveis, a linha sob o cursor revelada e as outras 94 intactas, sem overflow horizontal.

---

## [1.20.0] - 2026-08-15

**Curadoria: a descrição manual do produto (a anotação livre do pesquisador — não a
descrição oficial da fonte) agora é editável a qualquer momento, não só na criação.**

### Added
- **Campo "Descrição" editável inline** no Cadastro de produtos (`ViewCadastroProdutos.jsx`):
  cada linha da tabela ganhou um input compacto (componente `CcDescricaoField`, no mesmo
  padrão module-level de `CcGroupSelect`) para a anotação `descricao_produto`, que estava
  sujeita a edição SOMENTE no formulário de "+ Adicionar produto" — depois de cadastrado o
  produto, não havia como corrigir ou atualizar a anotação. Commita no blur/Enter, só quando
  o valor (trimado) realmente muda (evita escrita no-op a cada clique); Esc reverte sem
  salvar. Nenhuma mudança de backend/BigQuery/dbt foi necessária: `descricao_produto` já era
  uma coluna mutável comum em `research_inputs.produto_catalog_log` (mesmo mecanismo
  append-only + "latest-wins" já usado por `agrupamento`/`ciclo_de_vida`), e o endpoint
  `POST /api/catalog/entry` já a aceitava sem lógica de write-once — só faltava o controle na
  UI. Verificado ponta a ponta contra o BigQuery real (dev local): editar, recarregar a
  página e confirmar que o valor persistiu.

### Changed
- **Colunas da tabela de produtos alinhadas entre agrupamentos, sem scroll horizontal**
  (`dashboard.css`, ≥769px): cada agrupamento renderiza sua PRÓPRIA `<table>` (uma por card);
  com o layout automático do navegador, cada tabela calculava a largura das colunas a partir
  do seu próprio conteúdo, então a mesma coluna caía numa posição x diferente em cada card —
  forçando o olho a "zigzaguear" entre caixas — e textos longos empurravam a tabela além da
  largura do card, exigindo scroll lateral em cada uma. Fix: `table-layout: fixed` +
  larguras percentuais fixas por `nth-child`, IDÊNTICAS em toda `.cc-table` (compartilhadas
  via CSS, sem tocar o componente React), alinhando as colunas entre todos os cards; texto
  agora QUEBRA (`white-space: normal` + `overflow-wrap: anywhere`) em vez de forçar
  overflow — nada é truncado. As duas colunas `<select>` (Agrupamento/Ciclo de vida) — que
  nunca quebram seu próprio valor exibido, apenas cortam nativamente quando estreitas —
  cederam proporção às colunas de texto/número que realmente precisam evitar quebras feias
  no meio de um número. Escopado a `min-width:769px` para não colidir com o layout de cards
  empilhados do mobile (≤768px, inalterado). Verificado sem overflow horizontal em 1280px,
  1400px e 820px (medição via `scrollWidth`/`clientWidth`), com o layout mobile intacto.
- **"Convenções métricas" recolhida por padrão, no mesmo padrão do bloco de filtros**
  (`MetricConventions.jsx`): a tira sempre vinha 100% aberta (moeda, correção monetária,
  grupos de unidade por família + checkbox de auto-escala), ocupando bastante altura e
  empurrando o page hero de cada perspectiva para bem mais abaixo — diferente do bloco de
  filtros, que já ficava atrás de um botão "Editar filtros". Agora mostra só um resumo
  compacto (chips somente-leitura reaproveitando `.fm-chip-filter`/`.fm-chip-k`/`.fm-edit-btn`
  do próprio bloco de filtros, para leitura visual consistente) + um botão "Editar métricas";
  os grupos completos só entram no DOM quando expandido, com "Recolher" para fechar de volta.
  **Achado durante a implementação:** o estado de expandido/recolhido não podia ficar local
  ao componente — `DataGate` (main.jsx) desmonta TODOS os seus filhos (incluindo este) e
  mostra um placeholder de carregamento a cada troca de convenção (toda mudança de
  moeda/correção/unidade recarrega o snapshot), o que resetaria um `useState` interno e
  fecharia o painel sozinho a cada clique — inviabilizando editar várias convenções em
  sequência. Corrigido subindo o estado (`metricsExpanded`) para `main.jsx`, acima do
  `DataGate`, no mesmo padrão já usado por `filterOpen`. Verificado ao vivo: 3 mudanças de
  convenção em sequência (moeda → correção → unidade) mantêm o painel aberto; "Recolher"
  fecha e o resumo reflete corretamente o estado final.

---

## [1.19.0] - 2026-08-15

**Correção do erro 500 em "Cadastro de produtos" (órfãos) + classificação transiente vs. real
nos alertas de ingestão.** Disparado pela investigação de dois alertas simultâneos (Cloud
Monitoring `embrapa-ingest-all` + o aviso amarelo na tela de curadoria), que se mostraram
independentes — mas ambos valiam correção.

### Fixed
- **`GET /api/catalog/orphans` 500 quando 2+ bancos têm produtos removidos simultaneamente**
  (`gateway.fetch_orphan_produtos`): o `EXISTS` correlacionado contra um `UNION ALL` de 2+
  tabelas Gold não é algo que o BigQuery consegue decorrelacionar
  ("Correlated subqueries that reference other tables are not supported..."). Reescrito como
  `JOIN` simples, semanticamente idêntico. Bug latente desde a v1.10.8 (#206) — só se manifestou
  agora que a primeira remoção cross-banco (comex + comtrade) aconteceu em produção. Confirmado
  reproduzindo a query real no BigQuery antes e depois da correção.

### Changed
- **Classificação transiente vs. inesperado no CLI de ingestão** (`embrapa ingest all` /
  `comtrade` / `comex` / `reconcile`): cada falha por chunk/fonte agora carrega se foi um
  `SourceTransientError` marcado (upstream já esgotou o orçamento de retry do `tenacity` —
  esperado, autocurável na próxima janela delta) ou algo inesperado (bug de código, erro de
  permissão/schema). Se **todas** as falhas de uma execução forem transientes, o comando sai com
  código 0 (mesma lógica já usada para a exaustão de cota diária do COMTRADE, agora generalizada
  a qualquer rate-limit/timeout esgotado); se **qualquer** falha não for transiente, sai com
  código 1 como antes. O log de cada execução marca cada falha com `(transient)` ou
  `(unexpected — investigate)`. Objetivo: o alerta `embrapa-ingest-job-failed` do Cloud
  Monitoring deixa de disparar para condições que se autocorrigem na próxima execução agendada,
  reservando a página para bugs reais. O texto do alerta (`deploy/ingestion/alert_policy.json`)
  também deixou de afirmar erroneamente que o job é só "nightly" (é compartilhado pelos gatilhos
  mensais de comtrade/pam/ppm/reconcile) e agora aponta para essa nova marcação nos logs.

---

## [1.18.0] - 2026-07-14

**Anomalia agronômica do PAM promovida a flag de qualidade in-product + correção de docs.**
Seguindo a auditoria de fluxos de dados (v1.17.0), a inconsistência "área plantada < área
colhida" — antes visível só no log do build (`assert_pam_area_planted_ge_harvested`, WARN) —
agora aparece como uma flag própria na janela de Qualidade, para o pesquisador ver que o dado
é um erro da fonte (SIDRA), não um erro do pipeline.

### Added
- **Flag `AREA_INCONSISTENT`** (só PAM): um registro cujo `area_planted_ha < area_harvested_ha`
  (agronomicamente impossível) recebe essa flag no `gold_pam_production`, com **precedência**
  sobre a flag de completude (todas as linhas afetadas eram `OK`, então nada é mascarado). Fiada
  ponta a ponta: `data_quality_flag` (Gold) → `serving_quality_by_source` (contagem genérica) →
  serializer (`_FLAG_KEY` + label pt-BR `_FLAG_LABEL_PT`) → registro `QUALITY_FLAGS` + `QTS_KEY`
  do frontend (donut, série temporal e legenda "O que significa cada flag?"). Erros de fonte
  continuam **carregados fielmente** (regra do projeto: marcar anomalias, nunca substituir).

### Fixed
- **Docs desatualizadas sobre a semântica do SIDRA `-`** (após a mudança `dash_is_zero` da
  v1.17.0): README, ARCHITECTURE e `docs/adding_a_data_source.md` diziam que `-` → NULL; agora
  esclarecem que os placeholders de "sem dado" (`...`, `..`, `*`, `X`) → NULL, mas o `-` do SIDRA
  é um **zero exato medido** → `0` para o IBGE (mantido distinto de ausente).

---

## [1.17.1] - 2026-07-14

**Hardenings defensivos opcionais dos 2 achados latentes restantes da auditoria de fluxos de
dados (L7/L8), após verificação adversarial.** Ambos os achados foram avaliados como não-ativos
(precondição jamais observada em toda a história ingerida; L7 ainda protegido pelos testes de
conservação Silver→Gold; L8 lido pelo gráfico via `qty_base`, unit-safe). Estas são blindagens
preventivas — nenhuma corrige um bug atual. Mudança **somente dbt**, sem alteração de runtime;
entra em vigor no próximo build de prod agendado (sem redeploy da webapi).

### Changed
- **Chave de dedup do IBGE Silver normalizada** (`silver_ibge_{pevs,pam,ppm}.sql`): o `partition
  by` do `qualify` passa a usar `lower(trim(unidade_de_medida))` — a MESMA normalização que os
  joins de seed já aplicam. Sem isso, um re-rótulo cosmético (caixa/espaço) da unidade de uma
  célula já ingerida colocaria a linha revisada numa partição diferente da obsoleta, ambas
  sobrevivendo ao latest-wins, e o pivô `max()` do Gold as colapsaria por magnitude, não recência.
  No-op nos dados atuais (uma unidade por célula).

### Added
- **Teste defensivo `assert_comex_single_stat_unit_per_ncm`** (WARN): alerta se um NCM do COMEX
  algum dia reportar sob mais de uma unidade estatística nativa (uma reclassificação do MDIC entre
  unidades da MESMA família — ex. QUILOGRAMA↔TONELADA — que a `serving_comex_annual` misturaria sob
  um único rótulo). Converte o ponto-cego silencioso num aviso de build no primeiro sinal.

---

## [1.17.0] - 2026-07-14

**Auditoria enxuta de fluxos de dados e ciclo de vida — 12 achados confirmados corrigidos**
(6 críticos de perda/deturpação de dado + 6 antipadrões latentes de config-drift; verificação
adversarial por 2 lentes de refutação). Foco exclusivo em perda de dados / dado errado exibido
ao pesquisador como correto, e desenhos que viram isso quando dado/config derivam.

> ⚠️ **Requer rebuild do dbt Gold em prod** (a mudança de `safe_numeric` propaga Silver→Gold) —
> não basta deploy de imagem. A retenção dos zeros publicados do IBGE **aumenta** a contagem de
> linhas do Gold (linhas de zero exato antes descartadas passam a ser retidas). A correção de
> ingestão do COMTRADE re-busca os 2 anos mais recentes a cada rodada.

### Fixed
- **COMTRADE congelava anos parcialmente publicados** — reporters entram com atraso de ~1-2 anos,
  então um ano buscado cedo ficava com poucos reporters e o `sync_raw` fazia resume-skip para
  sempre. Agora a janela recente é re-buscada integralmente (não só sentinelas vazias), absorvendo
  reporters atrasados e revisões.
- **`safe_numeric` apagava os zeros exatos do SIDRA** — `'-'` (zero medido, "não resultante de
  arredondamento") era mapeado para NULL igual a `'...'` (indisponível), confundindo "produção
  cessou/zero" com "não pesquisado" e descartando/marcando como ausente. Novo parâmetro
  `dash_is_zero`: PEVS/PAM/PPM mapeiam `'-'`→0; BCB/COMEX/COMTRADE inalterados.
- **Renomear agrupamento revertia movimentações e ressuscitava produtos removidos** —
  `_active_member_rows` filtrava por `agrupamento_id` (atributo mutável) **antes** do dedup
  latest-wins; agora deduplica o log completo e só então filtra pelo estado atual.
- **Chave de idempotência engolia a próxima edição diferente** — a chave era por-entidade e
  retida entre falhas, então uma segunda edição *diferente* do mesmo produto reusava o `change_id`
  e era descartada em silêncio com toast de sucesso. Agora a chave inclui uma impressão do payload.
- **Adaptadores de comércio ignoravam os filtros server-side** — sazonalidade, Sankey (COMTRADE)
  e ranking de parceiros não recebiam flow/regime/tipo-de-mercado que o `/snapshot` já honra,
  exibindo totais de todos os fluxos sob um filtro ativo. Fiados agora ponta a ponta.
- **"Brasil no mercado mundial" dividia por denominador mundial parcial** — o último ano comum
  podia ter uma fração dos reporters, inflando a "participação atual". Série e KPI capados no
  último ano com cobertura de reporters assentada (≥90% do máximo).
- **Backfill de produto novo (IBGE/PAM/PPM)** — a janela delta era por-tabela; um produto novo
  recebia só a sobreposição recente. Agora um código sem linhas no Bronze força janela completa.
- **Marcador de carga do COMEX ganhou impressão do filtro** — uma mudança no conjunto de produtos
  re-roda a Fase 2 sobre os arquivos históricos (antes um NCM novo nunca fazia backfill).
- **Série BCB fria vazia agora falha alto no delta** (código com typo/descontinuado deixava de
  entrar em silêncio, com colunas Gold NULL).
- **PAM/PPM `family`** passou a consultar o override de unidade por-produto (`ufp.family`),
  alinhado a PEVS/COMEX.
- **Guard anti-dupla-contagem do COMTRADE (`sum_flows`)** aplicado a `product_timeseries` e ao
  ranking de parceiros (soma X+M, não X+M+RX+RM).
- **`backup-gold` registra e verifica o dataset de origem** — um snapshot de dev não satisfaz
  mais o gate de frescor do doctor nem o gate de backup do `purge-orphan` para prod.

---

## [1.16.0] - 2026-07-12

**Remediação da rodada seguinte da auditoria da Curadoria + varredura sistêmica dos mesmos
padrões de defeito no projeto inteiro.** Duas frentes: (1) correção dos 27 achados menores
confirmados que restavam da auditoria da Curadoria/Cadastro; (2) varredura de 12 classes de
defeito por todo o projeto (backend, frontend, dbt) com verificação adversarial, corrigindo
27 recorrências confirmadas + itens de menor confiança. Sem mudança de contrato de API que
quebre clientes; a mudança de `dbt` é aditiva (testes + descrições) e num `view`.

### Fixed
- **Honestidade de dados — falha de fetch exibida como "sem dados" em ~10 telas** (regra dura
  do projeto: nunca afirmar um valor sobre dado que não carregou). Raiz sistêmica na camada de
  dados: `data/resource.js` ganhou `errorOf()` e `data/producers.js` propaga `loadError` nos
  shells (flow/partner/monthly/productivity/cross-source/cross-analytics/products-by-uf); novo
  `LoadErrorNote` (acessível, `role="alert"`, pt-BR) ligado em Fluxos, Parceiros, Sazonalidade,
  Produtividade, Cruzamento de fontes, Multi-fonte (4 sub-análises), Análises curadas (2) e
  Geografia — além do read de órfãos do Cadastro. Uma falha de `/api/*` agora mostra erro
  honesto em vez de "US$ 0 / 0 rotas / sem dados".
- **Idioma (regra pt-BR ↔ inglês)**: mensagens de erro que o pesquisador vê passaram a pt-BR
  (validação de campo obrigatório e autorização nas rotas do catálogo/atributos; erros de
  filtro em `serving/sql.py`; `seam.seed_page`); strings só-operador/CLI passaram a inglês.
- **Trilha de auditoria anônima**: `embrapa editors add` / `attribute-editors add` (concessões
  de permissão) e `purge-orphan --mark-purged` agora registram o operador real do SO
  (`operator:<usuário>`) em vez do default anônimo.
- **Idempotência (`change_id`)**: os writers de atributo (FROZEN) passaram a devolver a linha
  ARMAZENADA no dedup e a sinalizar conflito (HTTP 409) quando um `change_id` é reusado com
  chave diferente (espelha `curation`/`agrupamentos`); `change_id` agora tem limite de tamanho.
- **Limites de tamanho ausentes** em campos graváveis pelo usuário (`agrupamento_id`,
  `change_id` do feedback e dos writers, `source`/`code`/`customs_code`/`flow_code`).
- **Leitura resiliente do catálogo**: `gateway.fetch_produto_catalog` faz self-heal do schema
  (coluna `sidra_tabela`) e retry ao ler uma tabela antiga, em vez de dar 500 no Cadastro.
- **Acessibilidade**: `aria-label` em selects de filtro/ano sem nome acessível (Cruzamento,
  Base de dados, Referências, Cadeia, Curadoria, FilterMenu) e `role="alert"` em banners de erro.
- **Vocabulário/nomenclatura**: "commodity(s)" como sinônimo do assunto → "produto(s)" (×6 em
  `registries.py`); jargão "marts"/"Refresh" removido do hero (`MainScreen`); "seeds" →
  "valores de referência" (Referências).
- **Validação de parâmetros de URL** (`main.jsx`): `flow`/`customs`/`market` deep-linked são
  validados contra as opções do banco (espelha `?cur`/`?v`/`?b`).
- **`dbt`**: `accepted_values` no vocabulário `ciclo_de_vida` (gate F7) e em
  `serving_comtrade_annual.market_nature`; teste `unit_test` de latest-wins em
  `dim_produto_catalog`; `sidra_tabela` documentada em `_sources.yml`.

## [1.15.0] - 2026-07-11

**Auditoria da Curadoria/Cadastro de produtos + varredura dos mesmos padrões no resto do
projeto.** Duas rodadas: (1) remediação dos achados confirmados da feature de curadoria;
(2) correção de 11 recorrências dos mesmos padrões de defeito em outras telas/rotas. Sem
mudança de contrato de API que quebre clientes; a mudança de `dbt` é em `view` (propaga no
próximo `dbt build`).

### Fixed
- **Purga de órfãos — pontos cegos do único fluxo destrutivo** (`serving/catalog_lifecycle.py`,
  `cli.py`): o gate agora recusa purgar um produto **re-adicionado** ao catálogo (o log
  append-only continuava lendo `descontinuado`); o backup deixou de ser aviso e virou **gate
  rígido** (sem snapshot fresco os DELETEs não são impressos, salvo `--force`); `--mark-purged`
  trata erro com mensagem limpa em vez de traceback; a nota do plano explicita que a purga só é
  permanente apagando Bronze **e** reconstruindo os Silver incrementais com `--full-refresh`.
- **`_current_sidra_tabela` engolia erro transitório** (`serving/curation.py`): `except`
  estreitado para `(NotFound, BadRequest)`, evitando gravar `sidra_tabela` NULL numa edição PPM
  e excluir o código da ingestão dirigida por catálogo. Mesmo ajuste em
  `serving/attribute_engineering.py` (`seed_flow_market`, estreitado para `NotFound`).
- **Renomear agrupamento permitia nome duplicado** (`serving/agrupamentos.py`): validação de
  colisão de nome no rename (a criação já bloqueava); re-stamp dos membros converge num retry
  idempotente.
- **Editor do Cadastro lia marts com gate de visibilidade F7** (`serving/gateway.py`,
  `webapi/seam_curation.py`): novo leitor **ungated** `fetch_source_products_gold` para o editor
  admin, que por design deve ver produtos ocultos (antes um produto oculto virava falso "ainda
  não ingerido").
- **Falhas de fetch exibidas como "vazio legítimo"** — agora distinguem erro de ausência:
  ranking/mapa por UF (`ViewProductProfile.jsx`, `ViewRebanho.jsx`), catálogo de referências
  (`ViewReferencias.jsx`, catálogo estático nunca vazio) e exportação de CSV
  (`ViewReferencias.jsx`, `ViewDados.jsx`, antes falhava sem aviso).
- **Falha ao carregar agrupamentos** (`ViewCadastroProdutos.jsx`) deixou de ser engolida (todos
  os produtos apareciam como "Sem agrupamento registrado").
- **Parâmetros de deep-link sem validação**: `?v` (view), `?b` (banco) e `?ip` (info page)
  agora são validados contra o menu/registro; um valor desconhecido cai no padrão em vez de
  renderizar tela quebrada / banco errado (`frontend/src/main.jsx`, `frontend/src/ui/views.js`).
- **Strings em inglês visíveis ao pesquisador → pt-BR**: autorização do catálogo, validação de
  filtro em Dados/Referências (`serving/sql.py`), 500 genérico (`webapi/routes.py`) e mensagens
  de validação do feedback (`serving/feedback.py`).

### Added
- **Idempotência nos writes do cliente** (`change_id`): o Cadastro de produtos e o canal de
  **feedback** agora enviam uma chave estável por operação; o backend deduplica um reenvio
  (timeout que aterrissou / duplo-clique), evitando linha duplicada no BigQuery **e** issue
  duplicada no GitHub. Confirmação + aviso de latência ao **ocultar** um produto; a lista de
  Descontinuados exibe `status`/`warning` (um código já purgado que retornou não aparece mais
  como "aguardando remoção").
- **Check de órfãos no `embrapa doctor`** (`Catalog orphan lifecycle`) — soft-warn quando há
  remoções ainda não marcadas pelo `mark-orphans` (previsto na spec da curadoria).

### Changed
- **Gate de visibilidade F7 nos contadores de `gold_source_metadata`** (dbt): `total_rows`/
  `products_total` que o pesquisador vê (Saúde do sistema, chips) passam a excluir produtos
  ocultos, alinhando ao restante dos marts. NO-OP até algo ser ocultado.

## [1.14.1] - 2026-07-11

**Correção de UI · legendas duplicadas** nos gráficos de várias janelas. Nenhuma mudança de
schema/dbt/API — puramente frontend (renderização Plotly).

### Fixed
- **Legenda duplicada em gráficos com legenda customizada** — vários gráficos Plotly
  desenhavam a legenda **nativa do Plotly** *e* uma legenda HTML customizada (`qa-legend`,
  `pc-legend`, `xs-legend`) para a **mesma** série, aparecendo duas vezes. Reportado na
  janela **Qualidade dos dados** ("Por produto" e "Share por flag") e, na varredura do
  projeto, encontrado também em **Comparar produtos**, **Sazonalidade e tendências**,
  **Multi-fonte** (Porteira vs. porto · Markup, MDIC × Comtrade) e **Fonte cruzada**
  (modos base-100 e eixo-duplo). Os componentes de gráfico (`FlagBars`, `StackedArea`,
  `MultiLineChart`, `DualAxisLineChart`) ganharam uma prop `showLegend` (padrão `true`,
  preservando o comportamento onde a legenda nativa é a única); as views que já desenham a
  própria legenda passam `showLegend={false}`. Gráficos sem legenda customizada (ex.:
  `Rebanho`, a razão em `Fonte cruzada`) seguem com a legenda nativa. Cobertura de testes
  adicionada para a prop em cada componente.

## [1.14.0] - 2026-07-06

**UN COMTRADE país filter** + uma **auditoria focada no glossário** (33 correções aplicadas) +
crédito de autoria/manutenção no rodapé. Nenhuma mudança de schema/dbt — os filtros de país
consomem colunas (`reporter_iso_a3`, `partner_iso_a3`) que já existiam na
`serving_comtrade_annual` (backfill mundial já concluído); só a leitura server-side + a UI
são novas.

### Added
- **País reporter · País parceiro (UN COMTRADE)** — dois multi-seletores de país no menu
  "Editar filtros", espelhando o filtro de Fluxo já existente ponta a ponta (schema, seam,
  gateway, SQL, dataStore, URL, chips). `reporter` é um codificador de 3 estados — ausente
  = Brasil (idêntico ao comportamento atual), `__all__` = mundo (sem pin, soma todos os
  reporters), lista = `IN (...)`; `partner` segue a regra padrão null-quando-cheio. Novo
  endpoint `GET /api/countries` (203 reporters × 246 parceiros, cacheado). Verificado
  byte-a-byte contra o BigQuery (Brasil 2024 = 73,42 · mundo = 615,37 · Brasil↔China = 36,18,
  em bi US$ IPCA).
- **Autoria/manutenção no rodapé** — nova coluna no `<footer>` global (`AppShell.jsx`), ao
  lado do crédito institucional da Embrapa, com contato técnico e o link do repositório
  GitHub, para quem quiser reportar um problema ou contribuir encontrar isso facilmente em
  qualquer tela.

### Fixed
- **Espaçamento do hint de produtos no menu de filtros** (`.fm-cascade-hint`): o texto
  descritivo do dimensionamento de produtos ficava colado na borda esquerda e no cabeçalho
  da seção (sem margem) em todos os bancos com hint. Corrigido com inset alinhado ao
  cabeçalho (22px desktop / 14px mobile) + respiro vertical.
- **Auditoria do glossário (33 achados verificados, todos corrigidos)** — a pior classe:
  **códigos de produto fabricados** que nunca bateram com o SIDRA real (PEVS `49xxx`/PAM
  `54xxx` → códigos reais `34xx`/`40xxx`), um **produto-fantasma** ("Erva-mate", nunca
  esteve na base) removido, e dois produtos reais que faltavam (Carvão vegetal, Pinheiro
  brasileiro) adicionados. Também corrigidas descrições desatualizadas (COMTRADE Flow
  agora é totals-only; `BEC` era um termo órfão; Reporter/Partner descritos como colunas
  passivas, agora são filtros; o eixo "tipo de mercado" da Engenharia de atributos está
  congelado e agora é rotulado como tal) e reescritas ~12 definições genéricas demais para
  o pesquisador leigo (HHI, FOB/CIF, SH4·SH6, entre outras). Adicionado o vocabulário-base
  do app (produto · agrupamento · cesta) que nunca havia sido glossado.

---

## [1.13.5] - 2026-07-06

Remediação de uma **auditoria de segurança da feature Curadoria** (catálogo editável). Nenhum
achado crítico — sem acesso não-autenticado, sem destruição de dados, sem injeção; o purge
humano-gated e o log append-only se sustentam. Prod está **travado** (2 editores em
`catalog_editors`). Os achados são das costuras + bugs funcionais reais. *(Assume #224/1.13.1
… #229/1.13.4 antes; reconciliação trivial. O ajuste de tie-breaker SCD2 (#10) foi ADIADO — é
uma mudança de 13 pontos para um empate inalcançável; ver PR.)*

### Fixed
- **Autorização fail-OPEN em erro transitório vira fail-CLOSED.** `routes._authorize_*_editor`:
  se criar a tabela de allowlist FALHA (BQ/perms) E a allowlist está vazia, agora nega (503) em
  vez de cair silenciosamente em "modo aberto" — um allowlist vazio só é confiável quando o
  estado da tabela pôde ser confirmado.
- **`sidra_tabela` era descartado na seam do catálogo** (`seam_curation.record_catalog_entry`):
  entradas PPM (SIDRA 3939/74) criadas via web API falhavam a validação (400). Repassado.
- **Códigos só-espaço passavam pelo resolver** (`catalog_resolver`): `strip` antes do filtro →
  `' '` virava `''` na URL SIDRA (`c289/3405,,3450`). Filtra depois de aparar.
- **Revogação de editor não invalidava o cache** (catálogo + atributo): um editor removido
  mantinha acesso de escrita por ~30s. `add`/`remove` agora invalidam a allowlist memoizada.
- **Dedup de idempotência devolvia o corpo da requisição, não a linha ARMAZENADA**
  (`curation._row_for_change_id`): um retry com o mesmo change_id e valores diferentes agora
  devolve o que foi persistido (consistência read-after-write).
- **Regex do purge afrouxado** (`catalog_lifecycle.purge_plan`): `[A-Za-z0-9.\-]+` →
  `[0-9]+`, em lockstep com a validação de escrita do catálogo (só dígitos).

### Added
- **Teste de acoplamento cross-layer do Ciclo de Vida** — o literal "oculto" acopla 3 camadas
  (validador Python, gate dbt `dim_produto_visibility`, dropdown do frontend); um reword numa
  só falha o gate em silêncio. Pinado por teste.
- **Teste de unicidade em `dim_produto_visibility`** (`(source, code)`), espelhando o de
  `dim_produto_catalog` — pina o grão SCD2 "latest-wins" contra uma regressão.

## [1.13.4] - 2026-07-06

Remediação de uma **auditoria profunda do banco IBGE PEVS** (extração vegetal) — a fonte
FUNDACIONAL e a mais sólida das cinco auditadas: os núcleos difíceis (reforma monetária
pré-1994, Silver incremental, unidades multi-família) estão **corretos por design**. Os
achados são lacunas de GUARDA — paradoxalmente, PEVS (a fonte mais antiga) tinha MENOS
guardas que o PAM, feito depois. *(Assume que #224/1.13.1 + #225/1.13.2 + #226/1.13.3 entram
antes; reconciliação trivial da versão caso a ordem mude.)*

### Added
- **Guarda de paridade das variáveis PEVS (144 quantidade / 145 valor).** Expostas em
  `config.py` (`ibge_variable_*_code`) + ponte `env_var()` no `dbt_project.yml` + novo
  `doctor._check_ibge_variable_codes` — espelha o guard do PAM. Um código mistypado
  (144→143) em `.env`/`dbt_project.yml` agora **falha no doctor** em vez de silenciosamente
  esvaziar a coluna de quantidade no Gold. Inclui `.env.example` + testes.
- **Teste dbt `assert_product_single_family`** (`warn`) — cada `(produto, gold)` deve ter
  uma única família física; se um produto passasse a ter 2 famílias (erro de seed/ingestão),
  as somas de quantidade misturariam t + m³ num total sem sentido. Verificado limpo em prod
  (0 violações) sobre pevs/pam/ppm.

### Changed (docs)
- **Runbook**: nova seção "Editando um seed dbt → `--full-refresh`" — um edit em
  `historical_currency_factors` (reforma pré-1994), `unit_family_conversions` ou
  `product_unit_factors` NÃO propaga num build incremental; exige `--full-refresh` do
  `silver_ibge_pevs+`.
- **Frontend**: nota de escala (`mil t` / `mi m³`) em `bancos.js` + entradas de glossário —
  a unidade-base é t/m³, mas os gráficos exibem em escala (×1e3 / ×1e6); não é divergência.

## [1.13.3] - 2026-07-05

Remediação de uma **auditoria profunda do banco IBGE PAM** (produção agrícola). O maior risco
— o rendimento ser uma RAZÃO somada indevidamente — está **correto por design** (o serving
descarta o rendimento reportado e o front-end recalcula Σqty ÷ Σárea). Os achados são portões
de qualidade de dados + 1 bug de UI. *(Assume que #224/1.13.1 e #225/1.13.2 entram antes;
reconciliação trivial da versão caso a ordem mude.)*

### Fixed
- **Botão "Exportar" da perspectiva Produtividade (falha silenciosa).** `views.js`:
  `exportable:false` — não havia case `'productivity'` em `csvExport.buildRows` (a view é
  `selfData` e recalcula rendimento = qty/área fora do contexto de export), então o botão
  renderizava e o clique caía no caminho `default → null` sem baixar nada.

### Added
- **Teste dbt `assert_pam_area_planted_ge_harvested`** (`warn`) — sinaliza linhas SIDRA
  agronomicamente impossíveis (área plantada < colhida; ex. 1990 Manaus Mandioca 50<650 ha,
  1993 Cana 790<890 ha) sem bloquear o build; os dados são carregados fielmente (regra do
  projeto: marcar anomalias, nunca substituir em silêncio).
- **Validação de FORMA da resposta SIDRA** (`ibge/client.py`) — rejeita um corpo JSON que
  não seja lista antes da conversão para DataFrame; documenta que a COMPLETUDE depende do
  contrato do SIDRA (HTTP 400 em overflow, não truncamento silencioso em 200).
- **Teste de completude das 5 variáveis PAM** (`test_pam_pipeline`) — pin do conjunto
  {8331, 216, 214, 112, 215}; largar o 215 (valor) zeraria `gold_pam_production.val_raw`.

### Changed (docs)
- `gold_pam_production`: documentado que `yield_kg_ha` é o rendimento REPORTADO pelo SIDRA,
  cru e NÃO-autoritativo (diverge de qty/área em algumas linhas; é uma razão, nunca somável;
  o serving não o expõe — recalcula).
- Glossário: nota de que o **IGP-M começa em 1989** — `val_real_igpm_*` fica NULL antes disso
  (não é defeito do pipeline), enquanto IPCA/IGP-DI (desde 1980) preenchem.

## [1.13.2] - 2026-07-05

Remediação de uma **auditoria profunda do banco IBGE PPM** (pecuária) — a base mais
saudável auditada até agora. Os 2 achados são defensivos: NÃO há bug ativo (verificado em
produção — o front-end já segrega corretamente estoque/fluxo por toda parte). *(Assume que a
PR #224 — COMEX, 1.13.1 — entra antes; reconciliação trivial da versão caso a ordem mude.)*

### Changed (defesa em profundidade)
- **Agregação de valor "flow-only" para fontes com `measure_kind` (PPM).** Os builders de
  produção (`production_overview` / `_by_uf` / `_by_uf_yearly`, `product_timeseries`) agora
  envolvem a soma de valor num `CASE WHEN measure_kind = 'flow'` quando a fonte carrega o
  discriminador estoque/fluxo (via `has_measure_kind`, derivado de `source ∈
  _MEASURE_KIND_SOURCES`). Torna EXPLÍCITO o contrato "efetivo de rebanho (estoque, cabeças)
  não tem valor" e defende contra uma futura linha de estoque que vaze valor não-nulo.
  Semanticamente um **no-op hoje** — verificado em prod: valor de estoque é 100% NULL, e a
  soma de fluxo é idêntica (US$/R$ 2.418,88 bi). A QUANTIDADE fica sem guarda de propósito
  (cabeças é uma quantidade válida — alimenta a perspectiva Rebanho).
- **Nota de cache (forward-compat).** O tratamento `measure_kind` é derivado da fonte, e
  `source` já está na chave do `@cache.memoize` de cada reader → sem colisão possível.
  Documentado que, se `measure_kind` virar um filtro do usuário, deve entrar na assinatura do
  reader para compor a chave de cache (precedente `flow`/`customs`/`market`).

## [1.13.1] - 2026-07-05

Remediação de uma **auditoria profunda do banco MDIC COMEX** (7 achados verificados
adversarialmente — a base é fundamentalmente sólida, sem nenhum bug de corrupção de dados
ativo em produção; os achados são lacunas defensivas, rótulos e documentação).

### Fixed
- **Validação de largura dos códigos COMEX.** `comex_ncm/heading/chapter_map` agora exigem
  8/4/2 dígitos — um código mal-configurado (ex. NCM de 7 dígitos) falha no carregamento em
  vez de silenciosamente não casar nenhuma linha no filtro do ingest (violava "no invisible
  filtering").
- **Guarda EUR-pré-1999 em `gold_comex_flows`.** O CTE `fx_month` (mensal) ganhou
  `and reference_year >= 1999` no ramo EUR, espelhando `annual_deflation_ctes` — impede que um
  eventual backfill de PTAX EUR pré-euro vaze taxas em `val_yearfx_eur`.

### Added
- **Tripwire dbt `assert_comex_no_gross_kg_unit`** (severity `warn`) — alerta se `co_unid=24`
  (QUILOGRAMA BRUTO / kg bruto) aparecer nos dados, antes que sua conversão (idêntica a kg
  líquido) misture peso bruto e líquido no agregado.

### Changed (docs / rótulos)
- **"UF de origem"** (glossário + hint): é sempre o lado **brasileiro** da operação (origem na
  exportação, destino na importação), não o país estrangeiro.
- **"Via"** (glossário): documentada como agregada / não filtrável; comentário do
  `filtersSchema` corrigido ("summed away in Silver" → camada de **serving**; Silver/Gold
  mantêm `transport_route_code`).
- Comentário falso de "Gold guard" em `serving_comex_annual` corrigido (o NULL pré-1994 vem do
  LEFT JOIN sem linhas correspondentes, não de uma guarda de ano explícita).
- `config.py`: documentado o acoplamento de **nome** das env-vars `BCB_INFLATION_SERIES_*_CODE`
  entre `config.py` e `dbt_project.yml` (renomear em só um lado faz o dbt cair no default).

## [1.13.0] - 2026-07-05

**COMTRADE totais-só (homogeneidade + sem dupla contagem) + "Tipo de Mercado" congelado.**
Decisão de produto após a auditoria (1.12.1): a base COMTRADE passa a carregar **apenas os
totais de cada dimensão**, para todos os países como reportador *e* parceiro, a partir de
2000. Isso torna a base **homogênea** (todo país reporta os totais, mesmo os que nunca
detalham) e **estruturalmente livre de dupla contagem** (regime C00-vs-detalhe, hierarquia de
fluxo X⊇RX, modais). Como o detalhe de regime aduaneiro deixa de existir na base, a
subfuncionalidade **"Tipo de Mercado"** (natureza econômica) fica **congelada**.

### Changed — ingestão totais-só
- **`COMTRADE_FLOWS` = `X,M`** (só os dois totais de direção — exportação/importação). Os
  sub-fluxos RX/RM/DX/FM/… são subconjuntos de X/M e passariam a duplicar; não são mais
  ingeridos.
- **Novo `COMTRADE_CUSTOMS_CODE` = `C00`** — o request agora manda `customsCode=C00`, baixando
  só o agregado "todos os regimes / total". Onde um reportador também detalha, `C00 =
  Σ(detalhes)`, então C00 sozinho é *lossless* para o total. Vazio ⇒ baixa todos os regimes
  (comportamento pré-2026-07).
- **`COMTRADE_REPORTERS` = `all`** — todos os reportadores × todos os parceiros (a matriz
  bilateral completa: comércio do Brasil + o espelho + market-share mundial). A duplicação é
  contida a jusante (readers do serving fixam o reportador; o Silver derruba o parceiro World
  e mantém só os totais; dedup por lote mais recente).
- **`COMTRADE_START_YEAR` = `2000`** — a base all-reporters é ancorada no marco de 2000.
- **`silver_comtrade_flows`**: mantém só `customsCode=C00` + fluxo em `X/M` +
  `reference_year >= var('comtrade_min_year', 2000)`; removida a lógica de exclusão-mútua
  C00-vs-detalhe (não há mais detalhe). Requer **um `--full-refresh`** no cutover para expurgar
  as linhas de detalhe/pré-2000 do incremental.

### Frozen — "Tipo de Mercado" (congelado, NÃO removido)
- Escondidos da UI (andaime mantido, dormível): o item de sidebar **"Tipo de Mercado"**, a rota
  `enrich_market` (editor da matriz), a análise curada **"Finalidade econômica"**, o filtro
  **"Tipo de mercado"** e — como consequência do totais-só (customs_code vira constante C00) —
  o filtro **"Regime aduaneiro"**. O picker de **Fluxo** passa a oferecer só exportação/importação.
- Motivo (gravado na memória do projeto): a natureza econômica se infere do regime aduaneiro,
  que a maioria dos países (Brasil: 100%) só reporta como C00. Reviver só faria sentido para o
  subconjunto de países que detalham — uma feature de cobertura parcial, adiada.

### Migration / operação de dados (operador)
- Requer **re-ingest total** com o novo escopo (all-reporters, 2000+, totais-só) — ver
  `docs/comtrade_world_backfill.md`. O re-ingest APENDA no Bronze; a dedup por lote-mais-recente
  + o floor de ano do Silver fazem a base virar totais-só sem DELETE obrigatório. As linhas de
  detalhe/pré-2000 antigas no Bronze ficam órfãs (nunca selecionadas); podem ser deletadas para
  economizar armazenamento (DELETE rodado por humano — hook de segurança). Depois, um
  `dbt build --full-refresh` no `silver_comtrade_flows` propaga para Silver/Gold/serving.

## [1.12.1] - 2026-07-05

Remediação dos achados de uma **auditoria profunda do banco UN COMTRADE** (ingestão →
Silver → Gold → mart de serving → "Tipo de Mercado" → frontend), verificados
adversarialmente. NÃO inclui o achado crítico de produto (o C00 — ~94% do valor — é
inclassificável por regime, e o Brasil reporta só C00, então "Tipo de Mercado" cobre ~5% do
valor e 0% do Brasil; decisão de produto pendente).

### Fixed
- **`market=''` (limpar par) agora lê como NULL, não como classificação vazia.**
  `dim_flow_market_scd2` filtra `market != ''`, então um par limpo não tem linha is_current →
  o LEFT JOIN do mart devolve `market_nature` NULL (contrato "não classificado → NULL") e a
  leitura ao vivo concorda — uma fonte de verdade simétrica.
- **Todas as classificações de tipo de mercado renderizam na matriz.** `flow_market_worklist`
  emite uma célula (valor 0) para todo par CLASSIFICADO mesmo sem dado COMTRADE — antes, uma
  classificação salva para um par sem dado sumia silenciosamente da UI e do KPI.
- **Anos COMTRADE recém-publicados são recuperados.** Um ano recente cujo Bronze é um
  sentinela vazio (buscado antes de o UN publicar) é RE-buscado dentro de uma janela
  (`COMTRADE_RECENT_REFETCH_YEARS`, default 2) — antes o sentinela fazia o chunk pular para
  sempre e o `reconcile` exclui o COMTRADE, então o ano nunca era ingerido.
- **`val_yearfx_eur` é NULL antes de 1999** (o euro não existia): a média-ano de EUR é
  guardada em `annual_deflation_ctes` para `reference_year >= 1999`, eliminando um valor 1998
  espúrio (afeta todos os golds — correto em todos).

### Changed
- **`COMTRADE_FLOWS` aceita os 10 regimes** (os 6 de aperfeiçoamento além de X/M/RX/RM) — o
  default ainda ingere 4, mas a allowlist não rejeita mais os outros, que o Silver já
  normaliza; alinha o comentário do Silver com o comportamento real.
- Correções de doc/rótulo: `24 → 25` pares em todo lugar; comentários "seed-driven" →
  "edit-driven" pós-v1.12.0; hints de valor-vs-registro (C00 é ~86% dos registros / 94% do
  valor); grão do Gold com `customs_code`; contagem do gap de qualidade (~830 → ~56,5k).

## [1.12.0] - 2026-07-05

**Engenharia de Atributos 100% descongelada.** As "Análises curadas" voltam ao topnav
(Parte A) e a **"Tipo de Mercado"** volta a ser uma **matriz editável na UI** — revertida
do seed estático `comtrade_market_nature` (v1.9.0) de volta para o log editável por
pesquisador. O **filtro "Tipo de mercado" e a análise "Finalidade econômica" continuam
funcionando** (a coluna `market_nature` do mart segue existindo — só muda a fonte: seed →
matriz editável). Ambos os atributos derivados (industrialização + tipo de mercado) ficam
atrás do mesmo `enable_curation` (default `true`; prod via `DBT_ENABLE_CURATION`).

### Added
- **`dim_flow_market_scd2`** (`dbt/models/core/`): view SCD2 Type-2 sobre o log
  `research_inputs.flow_market_log` — grão `(customs_code, flow_code)`, `valid_from` /
  `valid_to` / `is_current` via `LEAD()`, gated por `enable_curation` (espelha
  `dim_code_industrialization_scd2`). `flow_code` carrega o **token normalizado** de fluxo
  (`export`/`import`/…), casando `serving_comtrade_annual.flow`.
- **Editor "Tipo de Mercado"** (`?ip=enrich_market`, item na sidebar): a matriz 16×10
  (regime aduaneiro × fluxo) com um `<select>` consumo/processamento por célula e o valor
  US$ realmente transacionado por par (materialidade). Escrita append-only autenticada por
  IAP (`POST /api/attributes/flow-market`), guardada pela mesma allowlist de editores de
  atributos; leitura ao vivo (`GET /api/attributes/flow-worklist`, view SCD2, TTL curto).
- **`embrapa flow-market-seed`** (+ `make ensure-flow-market`): backfill idempotente dos 25
  pares do seed retirado para o log editável — o cutover (nada regride).

### Changed
- **`serving_comtrade_annual.market_nature`** passa a derivar de `dim_flow_market_scd2`
  (LEFT JOIN, `is_current`) em vez do seed. **`silver_comtrade_flows` / `gold_comtrade_flows`
  não carregam mais `market_nature`** (uma classificação editável fica fora do fato do
  medalhão; requer **um** `--full-refresh` no `silver_comtrade_flows` incremental para
  purgar a coluna fantasma). O editor reflete a edição na hora (view ao vivo); o filtro +
  a análise refletem após o próximo `dbt build` (latência documentada).
- **Parte A — descongelamento:** o grupo `curated` ("Análises curadas") volta ao topnav
  (`webapi/registries.py`) e `enable_curation` passa a `true` por padrão em `dbt_project.yml`.

### Removed
- Seed `comtrade_market_nature.csv` + seu registro em "Referências" (substituído pela matriz
  editável). O caminho editável antigo (`record_flow_market`, `dim_flow_market_scd2`) volta
  re-home no pacote `embrapa_dashboard` e adaptado às convenções atuais (`dev_author`,
  `/api/attributes/*`, escala de 8 níveis, guard `_authorize_attribute_editor`).

## [1.11.0] - 2026-07-05

A **Curadoria** vira a fonte única de verdade que **dirige a ingestão** dos bancos
IBGE (PEVS/PAM/PPM): a lista de códigos baixados do SIDRA passa a sair do catálogo
editável em "Cadastro de produtos", não mais do `.env`. Tudo atrás de uma flag
reversível (`CATALOG_AUTHORITATIVE_INGESTION`, default `false`) — o resolver sempre
cai no `.env` se o catálogo estiver ausente/vazio/inacessível, então nada quebra.

### Added
- **Ingestão dirigida pelo catálogo** (`ibge/catalog_resolver.py`): quando a flag está
  ligada, os pipelines IBGE resolvem os códigos de produto a partir de
  `research_inputs.produto_catalog_log` (lido cru, antes do dbt), com **fallback para o
  `.env`** e um **cap de segurança** (`CATALOG_RESOLVER_MAX_CODES`, default 500) contra
  um cadastro acidental gigante. Metadados de engenharia (tabela/classificação/variáveis/
  janelas) permanecem no `.env`.
- **Coluna `sidra_tabela`** no log do catálogo: o PPM (rebanho SIDRA 3939 / produção
  animal 74) é roteado por ela na ingestão; auto-migrada via `ALTER TABLE ADD COLUMN IF
  NOT EXISTS`. Sub-select "Tabela PPM" no formulário de cadastro.
- **Autorização**: env override `CATALOG_EDITORS_ALLOWED_EMAILS` (paridade com
  `CURATION_ALLOWED_EMAILS`), flag `can_edit` em `GET /api/catalog/entries` (a UI esconde/
  desabilita os controles para não-autorizados; o servidor continua autoritativo com 403),
  e comandos CLI `embrapa editors|curators add|remove` para gerenciar as duas listas.
- **`embrapa catalog-seed-from-env`**: semeia os códigos atuais do `.env` no catálogo
  (idempotente; marca o `sidra_tabela` do PPM) — o backfill de cutover.
- **`embrapa doctor`**: checagem "Catalog↔env product codes" que mostra o drift entre o
  catálogo e o `.env` por banco (informativa — nunca falha).

### Changed
- **Cadastro de produtos aceita produto "pendente de ingestão"**: um código ainda não
  presente no Gold não é mais bloqueado (o catálogo agora dirige a ingestão; a próxima
  execução o busca) — vira um aviso suave em vez de erro. Um typo grosseiro (código não
  numérico) continua rejeitado.
- `deploy/ingestion/deploy.sh`: a allowlist de env do Job passa a encaminhar `CATALOG_*` +
  o dataset/tabela do log do catálogo, para a flag chegar ao Job de ingestão.

## [1.10.11] - 2026-07-04

Correções de uma auditoria manual profunda de todo o repositório (75 achados
verificados). Nenhuma mudança de schema; comportamento preservado exceto os
defeitos abaixo.

### Fixed
- **Filtros "Regime aduaneiro" e "Tipo de mercado" (COMTRADE) agora afetam de
  fato os gráficos.** Antes chegavam só à série de visão geral, que nenhuma view
  renderiza — o usuário via totais sem filtro achando que estavam filtrados. O
  filtro passou a ser aplicado no servidor à série de produtos (`productTS`) que
  as views realmente desenham, e as quantidades da visão geral usam o mesmo
  escopo filtrado.
- **Segurança dos hooks de proteção (`scripts/claude-hooks`).** As guardas de
  deleção deixavam passar `gcloud storage buckets delete`, `bq --flag rm`,
  `gcloud alpha storage rm` e `bq query … DELETE/TRUNCATE`; chaves de conta de
  serviço no padrão do repositório (`sa-*-key.json`) não eram protegidas.
  Fechadas, com testes positivos e negativos para cada regra (antes 30 de 33
  regras não tinham teste).
- **IDs de projeto GCP corrompidos na documentação de IAM/auth/custos/Looker** —
  o find/replace da renomeação v1.10.8 trocara o ID imutável
  `embrapa-dashboard-commodities` por um nome inválido (com espaço e acento);
  todo comando `gcloud`/`bq` copiado dessas páginas falhava. Restaurado.
- **Robustez da API:** endpoints POST com corpo JSON não-objeto agora respondem
  400 (antes 500); a grade de Dados rejeita mais de 5 filtros em vez de descartá-los
  em silêncio (afetava o CSV exportado); paginação de tabela filtrada recebeu
  ordenação determinística; injeção de Markdown no issue de feedback do GitHub via
  `url`/`view`/`banco` foi neutralizada.
- **Curadoria:** idempotência de criar/excluir agrupamento corrigida (retry deixou
  de dar 400); `mark_purged` passou a exigir status *Descontinuado*; caches de
  catálogo/agrupamentos invalidam juntos.
- **Configuração e docs:** `COMEX_END_YEAR` deixou de vir fixado no `.env.example`
  (evita parar a ingestão do ano corrente); `doctor` valida as variáveis do PPM;
  diversos comentários/documentos desatualizados alinhados ao código
  (vocabulário de industrialização, taxonomia de flags, CHANGELOG, SECURITY,
  índices de PLANS).

## [1.10.10] - 2026-07-03

Melhoria de UI: o alternador de modo foi para a barra lateral.

### Changed
- **O alternador "Banco único · Multi-fonte" saiu do menu superior e passou para o
  topo da barra lateral**, junto da seleção de dados — é ele que decide se a lista
  abaixo é de um único banco ou do conjunto multi-fonte —, deixando a barra superior
  mais limpa. No celular ele já ficava no topo do menu lateral; agora o desktop segue
  o mesmo lugar. Em larguras de barra lateral bem estreitas, os dois segmentos
  empilham em duas linhas de largura total, sem cortar os rótulos.

## [1.10.9] - 2026-07-03

Conclusão da renomeação de terminologia na interface — o v1.10.8 renomeou os
identificadores e o schema do BigQuery, mas deixou várias strings visíveis ainda
como "commodity".

### Fixed
- **Rótulos da interface acertados para "produto" (item individual) ou
  "agrupamento" (cesta cruzada de fontes):** o seletor das perspectivas cruzadas
  agora mostra de fato **"Todos os agrupamentos"** (era "Cesta completa" —
  anunciado no v1.10.8, mas não aplicado no código); os seletores de "Valor
  agregado", "Finalidade econômica" e "Nível de industrialização" passaram a
  exibir **"Agrupamento"**; e as telas "Perfil do produto", "Comparativo entre
  produtos", "Cadastro de produtos", "Sobre o dashboard" e os textos do topo
  deixaram de chamar o item de "commodity". O termo "commodity" segue reservado
  ao eixo de industrialização ("Commodity Pura").

### Changed
- **Documentação e scripts alinhados ao novo nome:** `docs/setup.md`, os
  cabeçalhos dos skills, comentários de `ci.yml`/`dbt-build-prod.yml` e a prosa de
  `ARCHITECTURE.md` / `docs/frontend_data_contract.md` / `docs/gold_data_model.md`
  / `docs/operations_runbook.md` deixaram de descrever o sistema atual com o nome
  antigo; os scripts de exportação passaram a rotular o CSV com "Produto"/
  "Agrupamento".
- **`docs/migration_history.md`** recebeu o registro (que faltava) do cutover de
  schema do v1.10.8: renomes de tabela/coluna, remoção de `code_prefix` e o drop
  das 5 tabelas antigas.

## [1.10.8] - 2026-07-03

Terminologia precisa + renomeação do projeto para **"produtos agrícolas"**.

### Changed
- **Terminologia de 5 termos, consistente na UI:** **produto** = 1 item de um
  banco; **agrupamento** = produtos de *vários* bancos (perspectivas multi-fonte);
  **cesta** = produtos de *um único* banco (seleção por filtros); **commodity** =
  produto *sem* diferenciação (eixo "nível de industrialização"); **manufaturado**
  = produto *com* diferenciação. As perspectivas cruzadas passam a chamar a
  seleção de "Agrupamento" (era "Commodity"), com "Todos os agrupamentos" no lugar
  de "Cesta completa". "commodity" fica reservado ao eixo de industrialização;
  os itens individuais seguem como "produto".
- **Projeto renomeado de "commodities" para "produtos agrícolas"** — o dashboard
  cobre produtos agrícolas como um todo, não só commodities. Renomeados: o título
  da aba e do topo ("Análise histórica de produtos agrícolas"), a tela "Sobre o
  dashboard", a descrição do pacote e o título nos docs (README, ARCHITECTURE,
  CONTRIBUTING, CLAUDE.md). O **repositório GitHub** virou
  `embrapa-dashboard-produtos-agricolas` (com o Workload Identity Federation do CI
  repontado) e o **nome de exibição do projeto GCP** virou "Produtos Agricolas
  Dashboard". O **ID do projeto GCP permanece `embrapa-dashboard-commodities`**
  (imutável; embutido em BigQuery/Cloud Run/IAM) — só o nome de exibição mudou.

## [1.10.7] - 2026-07-02

Correção de um bug de servidor que derrubava as perspectivas multi-fonte com
seletor de commodity (Coeficiente de exportação, entre outras).

### Fixed
- **`/api/catalog` retornava 500 em produção, quebrando as análises cruzadas.**
  Duas commodities no `gold_produto_agrupamento` — PEVS **3433 (Carvão vegetal)** e
  **3434 (Lenha)** — estavam com `agrupamento_id` NULL (uma entrada do catálogo salva
  sem agrupamento). No `produto_catalog()` isso virava uma **chave de dicionário
  `float` NaN** misturada com as chaves texto; o provedor JSON do Flask serializa
  com `sort_keys=True`, tentava ordenar `NaN` contra `str` e estourava
  (`'<' not supported between float and str`), **derrubando o endpoint inteiro**.
  Com o `agrupamentoCatalog()` vazio, a perspectiva "Coeficiente de exportação" (e os
  seletores de commodity das demais cruzadas) exibia "Indicador indisponível".
  Agora uma linha com `agrupamento_id` nulo é **ignorada** (com log de aviso) em vez
  de derrubar a resposta — uma única linha malformada nunca mais quebra todas as
  views. As duas commodities ficam fora das análises cruzadas até receberem um
  agrupamento (continuam normais nas views de banco único). Teste de regressão
  adicionado. Diagnosticado reproduzindo no preview contra os dados reais de prod.

## [1.10.6] - 2026-07-02

Correção **real** do menu de filtros no celular e no desktop — a v1.10.5 não
resolveu (e piorou no iPhone). O diagnóstico desta vez foi feito reproduzindo o
bug num navegador real na largura de iPhone, não às cegas.

### Fixed
- **Seções do menu de filtros "achatadas" e modal sem rolagem (celular E desktop).**
  A causa real não era a rolagem aninhada do iOS (hipótese da v1.10.5), e sim um
  colapso de layout: o corpo do modal (`.fm-body`) é uma coluna flex e suas seções
  ficavam com o `flex-shrink` padrão (1) — então, quando a seção Geografia ficava
  alta, o flexbox **encolhia** Produtos/Período/Qualidade até virarem tiras de ~5px
  e o corpo nunca transbordava, logo **não rolava** e não dava para ver nem editar
  as opções. Afetava todo celular e janelas de desktop com menos de ~950px de
  altura. Corrigido com `.fm-body > .fm-section { flex-shrink: 0 }`: as seções
  mantêm a altura natural e o corpo rola como uma única região (como o próprio
  design já pretendia). A v1.10.5 havia "achatado" as listas internas no celular,
  o que inflava a Geografia para ~48000px e agravava o colapso — isso foi
  **revertido**; as listas voltam a ser roladores internos compactos (a coluna de
  municípios pode ter até 300 linhas).
- **"Círculo" cinza atrás do resumo da Geografia no celular.** Era o *pill* de dica
  em cascata (`.fm-cascade-hint`, `border-radius:999px`): com o texto longo
  quebrando em várias linhas num telefone estreito, ele inchava num borrão quase
  circular. Agora usa cantos normais e alinha o ícone ao topo.

### Changed (internal)
- `index.html` passa a ser servido com `Cache-Control: no-cache`, para que o
  `?v=<versão>` dos CSS estáticos (nomes sem hash) sempre chegue ao navegador em
  vez de uma casca antiga em cache prender a versão velha do CSS/JS. Teste
  adicionado (`test_webapi_app`). `?v=` dos CSS → 1.10.6.
- Removido `-webkit-overflow-scrolling: touch` (obsoleto no iOS moderno) e mantido
  `overscroll-behavior: contain` para conter a rolagem interna. Sem mudança visual
  no desktop além da correção do colapso.

## [1.10.5] - 2026-07-02

Correção do menu de filtros travado no iPhone/iOS Safari — funcionava no emulador do
Chrome, mas não no aparelho real.

### Fixed
- **Menu de filtros ("Editar filtros") inutilizável no iPhone (iOS Safari).** O modal tinha
  listas com rolagem *aninhada* (`.fm-grid-scroll` dos produtos/flags de qualidade e cada
  coluna `.fm-geo-list` da geografia) dentro do corpo rolável. O iOS Safari **não encadeia**
  a rolagem restante de um scroller interno para o pai (o Chrome encadeia — por isso o
  emulador passava): um toque que começasse sobre uma dessas listas prendia o gesto e o
  modal parecia **congelado**, sem alcançar o rodapé (Redefinir/Cancelar/Aplicar). No
  celular (≤600px) as listas internas agora são só layout (`max-height: none; overflow:
  visible`), deixando **uma única região de rolagem** (o corpo do modal); adicionados
  `overscroll-behavior: contain` + `-webkit-overflow-scrolling: touch`. O DOM de municípios
  continua limitado por `GEO_RENDER_CAP=300`.
- **Rodapé do modal fora da tela no iOS.** O teto de altura usava `100vh`, que no iOS mede a
  viewport *grande* (barra de URL recolhida), empurrando o rodapé fixo para baixo da dobra.
  Adicionado par de *fallback* com `100dvh` (viewport visível/dinâmica) — o `vh` fica como
  reserva para navegadores sem `dvh`.
- Toques nas caixas de seleção da geografia ganharam área maior (padding 5px → 9px), acima
  do conforto mínimo do iOS. Trilho decorativo do cabeçalho de seção agora tem
  `pointer-events: none` (nunca intercepta um toque).

### Changed (internal)
- Os CSS estáticos (`colors_and_type.css`, `dashboard.css`, `filter-menu.css`) têm nomes
  fixos (sem hash), então navegadores os mantêm em cache. Adicionado `?v=<versão>` aos
  `<link>` em `frontend/index.html` para forçar o download da versão nova — **incremente
  junto com a versão do app** a cada mudança de CSS. Sem alteração no desktop.

## [1.10.4] - 2026-07-02

Mobile/tablet responsiveness pass for four admin/utility surfaces that still assumed
desktop width.

### Fixed
- **"Cadastro de commodities" e "Nível de industrialização" no celular/tablet.** As
  tabelas largas (9 e 4 colunas) transbordavam ~800–960px no celular e ~400–580px no
  tablet — viravam um scroll horizontal inútil. Agora **reflow em cartões empilhados**
  (mesma convenção da tela "Saúde do sistema", via `data-label`): o cadastro vira cartões
  ≤768px (celular + tablet retrato) e o classificador de industrialização ≤560px (celular;
  cabe no tablet). A barra "Aplicar à base" e o seletor "Agrupar por" passam a quebrar
  linha. Nada muda no desktop.
- **Menu de filtros:** o rodapé da seção de geografia ("Malha IBGE: 5571 municípios ·
  mesorregião/microrregião…") era um único filho flex com `flex-shrink: 0` e vazava ~230px
  do painel no celular — agora encolhe e quebra em duas linhas.
- **Janela "Citar painel":** tinha `overflow: hidden` sem `max-height`, então em telas
  baixas (ou citações longas) o modal era **cortado sem rolagem**. Agora é limitado à
  altura da viewport com o **corpo rolável** (o cabeçalho e o ✕ ficam fixos e visíveis).

## [1.10.3] - 2026-07-02

Post-migration audit follow-ups (v1.10.0→v1.10.2): a multi-agent audit found no
high-severity bugs; this fixes the confirmed medium/low findings plus stale-doc and
dead-code cleanup.

### Fixed
- **Cadastro rejects an invalid `banco` token.** A banco outside the 5 valid catalog
  tokens (pevs/pam/ppm/comex/comtrade) silently bypassed the code-existence guard and
  wrote a junk catalog row that never joined in `gold_produto_agrupamento`. The writer
  now rejects it loudly (400).
- **Add form no longer loses your input on a failed write.** A 400 (duplicate/inexistent
  code) or 403 (not on the editor allowlist) kept the red banner but wiped the form; it
  now resets + closes **only on success**, preserving your input to correct.
- **"Cadastro de commodities" no longer remounts every dropdown on each keystroke.** The
  agrupamento `<select>` was defined inside the render (new identity per render); hoisted
  to a stable module-level component — also fixes an unassigned "stray" entry showing the
  first group instead of a blank placeholder.
- **Descontinuados now shows the orphan's agrupamento.** It was sourced from the
  removal tombstone (always NULL); now taken from the commodity's last *active* row.
- Add form: the ✓/✗ code hint is now banco-aware (no brief false "✓" right after switching
  banco); `catalog_status` uses a NaN-safe year guard.

### Changed (docs / internal)
- Corrected stale `code_prefix`/prefix wording to exact-code across the gateway/lifecycle
  docstrings, the `hidden_code_predicate` macro, and the `gold_produto_agrupamento`
  BigQuery description; documented the quality taxonomy as **11-value** (9 emitted + 2
  reserved) in README / CLAUDE.md / the quality PLAN.
- Removed dead `code_prefix` test fixtures; retired the misleading `commodity_crosswalk`
  mock in the Referências test; added the reverse (catalog→CSV) seed-bijection guard.

## [1.10.2] - 2026-07-02

Make the data-quality tags self-explanatory in the dashboard, and reserve the
structure for future auto-filled ("inferido") values.

### Added
- **Legenda de qualidade na perspectiva "Qualidade dos dados"** — um painel
  *"O que significa cada flag?"* (recolhível) documenta **todas** as marcas de
  qualidade com uma descrição em pt-BR clara (redação da aba "Qualidades" do Contrato
  de Dados), independente das flags selecionadas. Além disso, cada card e legenda de
  gráfico agora mostra a descrição como *tooltip* ao passar o mouse. O catálogo
  (Glossário) aponta para essa legenda como referência canônica.
- **Dois níveis reservados `inferido`** (`Quantidade inferida` / `Valor financeiro
  inferido`) — marcados como *reservada* na legenda e plumbados por toda a stack
  (registro de flags, mapas do backend, contrato `qualityTs`, filtro, `accepted_values`
  do dbt) exatamente como os níveis outlier/problemático: **aceitos-mas-ausentes**
  (sempre 0 hoje), prontos para quando um pipeline de preenchimento automático existir.
  Nenhum modelo do Gold os emite ainda — a taxonomia apenas reserva os ids.

### Notes
- Deploy é image-only (a única mudança de dbt é `accepted_values`, um teste — sem
  rebuild). Também leva a correção do seed "Tipos de mercado" (v1.10.1) ao prod.

## [1.10.1] - 2026-07-02

### Fixed
- **"Tipos de mercado" agora aparece em "Tabelas de referência".** A seed
  `comtrade_market_nature` (a natureza de mercado — consumo / processamento — por par
  regime aduaneiro × fluxo do COMTRADE) materializava no `silver` e já alimentava o
  pipeline, mas nunca havia sido registrada no catálogo de Referências (`_SEED_CATALOG`),
  então não era consultável. Registrada como somente-leitura (calibração). Verificada
  fiel à aba "Tipos de Mercado" da planilha Contrato de Dados (25 pares de natureza
  definida; os pares ausentes = "Não se aplica").

### Added
- Teste de regressão (`test_every_seed_csv_is_a_consultable_reference_table`) que garante
  a bijeção seed CSV ↔ `_SEED_CATALOG`: uma nova seed que materialize no `silver` mas não
  for registrada no catálogo de Referências passa a quebrar o CI (com uma lista de exclusão
  explícita e documentada para casos intencionais, como a `commodity_crosswalk` aposentada).

## [1.10.0] - 2026-07-02

Simplify the commodity catalog: each commodity is registered by its **exact source
code**, one at a time — no more prefixes. A redesigned, guided add screen that **won't
let you register a code that doesn't exist**, and status columns showing each
commodity's current state in the dashboard.

### Added
- **Catalog status columns** — the "Cadastro de commodities" table now shows, per
  commodity, its current Gold state: **linhas na Gold**, **período coberto**
  (ano mais antigo–recente) and a **tem-dados** indicator (a registered code with no
  Gold rows reads "sem dados"). Backed by one cheap cached aggregate per source
  (`GET /api/catalog/status` → `gateway.fetch_source_code_stats`).
- **Code autocomplete + hard existence check on the add form** — the code field
  autocompletes from the source's REAL product list (`GET /api/catalog/source-codes`),
  shows a live ✓/✗ hint, and both the client AND the server (`serving/curation.
  _assert_code_exists`) **reject a code that doesn't exist in the source** (HTTP 400,
  pt-BR reason). You can no longer register a phantom commodity.

### Changed
- **`code_prefix` eliminated end-to-end** (DB, backend, dbt, UI). Every commodity is
  keyed by its exact `(codigo_produto, banco)`; the cross-source bridge, the F7
  visibility gate (`dim_produto_visibility` + `hidden_code_predicate`), the PAM/PPM
  serving joins, the orphan diff and the purge plan all switched from
  `LIKE code_prefix||'%'` to exact `= code`. Behavior-preserving — after the v1.9.5
  import every entry's prefix already equalled its exact leaf code.
- **The "Adicionar commodity" screen was redesigned** — a clear labelled grid (banco ·
  código · agrupamento · ciclo · descrição) with inline validation feedback, replacing
  the cramped free-form row. Registration is one code at a time.

### Removed
- The prefix-disjointness write guard and the coarse-prefix purge resolution (both
  moot once codes are exact).

### Operator follow-up (zero-downtime column removal — two steps around the deploy)
- **Before deploy** (makes prod ready for the new writer; the old revision is unaffected —
  it still writes a non-null value into a now-nullable column):
  `ALTER TABLE research_inputs.produto_catalog_log ALTER COLUMN code_prefix DROP NOT NULL;`
- **After the new revision is live and verified** (fully removes the column — the new code
  never references it):
  `ALTER TABLE research_inputs.produto_catalog_log DROP COLUMN code_prefix;`

## [1.9.5] - 2026-07-02

Connect Curadoria (Cadastro de commodities) and Engenharia de Atributos (Nível de
industrialização) — one catalog, in sync.

### Changed
- **The industrialization worklist now reads the SAME live commodity catalog the
  "Cadastro de commodities" editor uses** (`seam_curation.catalog_worklist` → the
  append-only `produto_catalog_log`). So both features share identical
  banco+código+descrição+agrupamento, any catalog edit (new/renamed/moved/removed
  commodity or group) propagates to both automatically, and **PAM/PPM now group by
  commodity** (they live in the catalog with their agrupamentos, unlike the crosswalk).
  Replaces the old worklist that read the Gold code universe + the crosswalk (which
  lacked PAM/PPM). The value-added analysis is unchanged (it reads the classification
  log directly).
- **"Código" column** in the classifier no longer cramped — codes stay on one line with
  room to breathe.
- Page subtitle for "Nível de industrialização" updated for the 8-level scale (was
  "(bruta/processada)").

### Fixed
- `catalog_worklist` no longer 500s when a catalog entry has a NULL agrupamento/
  descrição/ciclo — BigQuery returns those as `NaN` (float), which broke the group sort;
  now normalized to None.

## [1.9.4] - 2026-07-02

Engenharia de Atributos — the per-code industrialization scale is now an **8-level ordinal
taxonomy** (Commodity Pura → Manufaturado Especializado), replacing the old 3-value
bruta/processada/misturado. Backend storage is open-vocabulary, so no schema change.

### Changed
- **Industrialization is now an 8-level ordinal scale** (`Commodity Pura`, `Higienizada`,
  `Acondicionada`, `Consumível`, `Subproduto`; `Manufaturado Artesanal`, `Industrial`,
  `Especializado`), each with a researcher-facing definition. The classifier editor offers the
  8 options + a reference legend ("O que significa cada nível") and per-option tooltips.
- **The "Valor agregado" analysis is redesigned as a per-level gradient** instead of a binary
  Bruto×Processado split: stacked-area of export value (US$ bi) and volume (mil t) by level, a
  per-level unit-price chart (US$/kg), and a "prêmio de processamento" = price of the most-
  processed present level ÷ the least-processed. New KPIs (níveis presentes, nível predominante).
  The seam/serializer now emit per-level series (`byLevel`/`byLevelWeight`/`byLevelPrice`).
- **PAM and PPM are now classifiable.** The industrialization worklist covers every live source
  (`CLASSIFIABLE_SOURCES`) — IBGE PEVS/PAM/PPM + MDIC COMEX + UN Comtrade — so their commodities
  can be classified too (the value-added analysis itself stays COMEX-only).

### Added
- Glossary + view descriptions updated for the 8-level scale and the two families
  (Commodity × Manufaturado).

## [1.9.3] - 2026-07-01

A mobile-responsiveness fix for the "Saúde do sistema" page — the per-banco operational
table now reflows to readable cards on phones. Frontend-only (no dbt/Gold change).

### Changed
- **"Saúde do sistema" is now properly adapted to phones.** On tablet the page was already
  fine, but on a phone the 6-column per-banco operational table ("Estado atual de cada fonte")
  had no mobile treatment: squeezed into ~290px it collapsed every cell to unreadable
  vertical letter-columns (bank names wrapping "I-B-G-E-P-P-M") behind a horizontal scroll.
  It now **reflows to one stacked label:value card per banco on phones (≤560px)** — the
  app's established "two-column sheet → list" convention (`.pp-spec` / `.ab-banco-meta`) — via
  `data-label` attributes read only by a phone-scoped `@media` block, so tablet (≥561px) and
  desktop render byte-identical. Also stacked, on the narrowest phones (≤480px): the
  "Arquitetura operacional" key/value rows, the shared `SectionHeader` title + caption
  (was crushing into two columns), and a wrapped alert timestamp (no longer flung to the
  right edge, orphaned from its title). Frontend-only; no dbt/Gold change.

## [1.9.2] - 2026-07-01

Curadoria "Cadastro de commodities" editor overhaul — agrupamentos become a first-class,
fully editable entity, each code now shows its original source description, and the vestigial
"Industrialização" field is removed. `dim_produto_catalog` drops one column (rebuilt on the
next prod build); no other Gold change.

### Added
- **First-class AGRUPAMENTOS (groups) in the "Cadastro de commodities" editor.** Groups were
  previously *derived* (the distinct set of `agrupamento` names on catalog entries) — no empty
  groups, no rename, no delete. They are now a real registry (`research_inputs.agrupamento_log`,
  append-only, IAP-attributed, keyed by `group_id` == a catalog entry's `agrupamento_id`) with a full
  lifecycle: **create** (incl. empty groups), **rename** (re-tags the group's member entries), and
  **delete** (blocked while the group still has members — reassign first). A researcher can also
  **move a commodity between groups** inline. Backend `serving/agrupamentos.py` +
  `/api/catalog/groups` (GET) + `/api/catalog/group` / `/api/catalog/group/remove` (POST).
- **The source's ORIGINAL description per code** in the editor — a read-only "Descrição (fonte)"
  column showing the name the source (IBGE / NCM / HS6) gives each code, via `fetch_products`.

### Removed
- **The catalog's free-text "Industrialização" field, everywhere** (writer, `gateway` read,
  `dim_produto_catalog`, `_sources.yml`, the editor column + Add form). It was vestigial —
  nothing downstream consumed it — and duplicated the concept owned by the separate **Engenharia de
  Atributos · Nível de industrialização** feature (the versioned `dim_code_industrialization_scd2`),
  which is now the single home for industrialization.

## [1.9.1] - 2026-07-01

UI polish across the shell — a bank-operability system-health page, a clearer feedback entry
point, and a roomier filter-menu product picker. Frontend-only (no dbt/Gold changes).

### Changed
- **The filter menu's product list is no longer cramped, for every banco.** The products
  section was capped at a tight 132px scroll box while the whole modal grew unbounded and the
  backdrop scrolled — a nested double-scroll that made picking from long product sets awkward
  (worst on PPM's 23 flat products and the COMEX/Comtrade NCM/HS trees). The modal is now a
  fixed-height flex column — a pinned header, a single scrolling body, and a **pinned footer**
  so "Aplicar filtros" always stays in view — and the product list gets a roomy,
  viewport-responsive height (`clamp(240px, 46vh, 460px)`, up from 132px). Short lists (e.g.
  PEVS/PAM) still size to their content with no wasted space; long lists and expanded trees get
  ~3× the visible rows. Verified across all five live bancos and on a short (640px) viewport.
- **The topbar "Reportar problema" action is now "Enviar feedback".** The button opened a
  dialog that already accepted a problem, a question (dúvida) OR a suggestion, but its label
  implied problems only — and, unlike "Citar painel" / "Compartilhar", it rendered with no
  icon (the `feedback` icon was missing from the registry, so `Icon` returned null). Relabeled
  to the encompassing "Enviar feedback" (+ a matching message-bubble icon), and the dialog
  title is now "Fale com a equipe".
- **"Saúde do sistema" is now focused on bank OPERABILITY, not data quality.** The page
  previously leaked single-bank data-quality content (a PEVS-only "% de linhas íntegras"
  chart + a PEVS quality-spike alert + a PEVS-scoped refresh KPI), which both duplicated the
  dedicated **Qualidade dos dados** perspective and ignored the other five banks. It now
  reports multi-bank operability only, from real backend signals:
  - KPIs: **Status geral**, **Bancos operando** (X/Y), **Volume total na Gold** (rows summed
    across sources), **Alertas operacionais** (real failed Gold queries).
  - The per-bank matrix gained **Fonte** + **Período coberto** columns (live `year_start–year_end`)
    alongside the real per-bank Gold-query status.
  - The architecture card surfaces the **running app version**, the system-wide temporal
    amplitude, an honest "telemetria de execuções não monitorada" note, and a pointer to the
    Qualidade dos dados perspective (where data-quality diagnostics live).
  - Removed the PEVS-only quality chart/alert/KPI + the retired run-history card, and swept the
    orphaned CSS (`hs-runs*`, `hs-dur/hs-delta`, `hs-status-ok`, `hs-alert-warn/info`). The
    page hero subtitle no longer promises "qualidade das tabelas Gold".

### Fixed
- **Missing icons that rendered blank.** Added the icons the app referenced but the registry
  lacked: `feedback` (topbar button), `bug_report` / `lightbulb` (the Problema / Sugestão
  category chips in the feedback dialog — only Dúvida had one before), `check_circle` (the
  feedback "enviado" confirmation), and `inventory_2` (the "Cadastro de commodities" sidebar
  item). All were silently rendering nothing.

## [1.9.0] - 2026-07-01

Unfroze **Engenharia de Atributos** and converted the market-nature (tipo de mercado) axis
from a researcher-editable-in-UI table to a **seed-driven** classification transcribed from
the "Contrato de Dados" sheet. Full UN Comtrade flow/regime/market filter surface, wired
reporter-agnostically so it lights up as more reporters are ingested.

### Added
- **Seed `comtrade_market_nature`** — the (customs_code × normalized flow) → {consumo, processamento}
  economic-purpose classification, transcribed from the "Tipos de Mercado" tab of the Contrato de
  Dados sheet. Joined in `silver_comtrade_flows` and propagated (`any_value`) through
  `gold_comtrade_flows` → `serving_comtrade_annual`. Uniqueness-tested on `(customs_code, flow)`;
  `market_nature` accepted-values-tested `[consumo, processamento]`.
- **"Finalidade econômica" analysis** (`curated_market_nature` → `ViewMarketNature`) — COMTRADE
  value by seed-classified purpose (consumo × processamento), read from the serving mart
  (`/api/cross/market-nature`). Replaces the frozen researcher-editable market-nature editor.
- **UN Comtrade filter dimensions** — "Tipo de mercado" (server param `market`) and "Regime
  aduaneiro" (`customs`) join "Fluxo" in the filter menu, trigger bar, and URL state (`mk`/`cx`).
  The predicates are reporter-agnostic; they currently return data only where a reporter declares
  per-customs-procedure detail.

### Changed
- **Engenharia de Atributos is live again.** The per-code industrialization editor ("Nível de
  industrialização" / "Valor agregado") is unfrozen and researcher-editable; `DBT_ENABLE_CURATION`
  is now `true` so the gated SCD2 view keeps rebuilding on every prod build. The `enable_curation`
  dbt var now gates **only** the industrialization SCD2 — market-nature is never gated.
- **Market-nature is no longer editable in the UI.** It is sourced entirely from the seed; there is
  no "Tipo de Mercado" editor entry and no write endpoint.

### Removed
- All flow-market editor machinery (no backward compatibility): the `flow_market_log` table +
  writer, `record_flow_market` / `flow_worklist` endpoints, the `_flow_market_map` /
  `_market_nature_accumulate` seam helpers, the frontend flow-market draft store, and
  `BQ_FLOW_MARKET_LOG_TABLE`. Market-nature now reads the serving mart directly (no Bronze scan).

### Also in this release
- **Filter-menu hardening** — a single URL-state encoder (`window.buildUrlState`) shared by every
  writer, fixing município loss on reload, the geo-mesh load race, over-100% "Linhas" shares, a
  focus-trap, and a handful of chip/value edge cases surfaced by the filter-menu audit.
- **NCM/HS6 product tree** — the COMEX/Comtrade product picker gained an expandable SH2 ▸ SH4 ▸ SH6
  tree with tri-state parents (a pure view over the leaf-code selection — no backend change).
- **SH-chapter labels** — human-readable SH2 chapter names for the product groups (`shChapters.js`).

### Notes
- **Reporter scope.** The `un_comtrade` banco is pinned to Brazil's own declaration, and Brazil
  reports only the aggregate customs procedure (C00), so the regime/market filters are empty for
  Brazil today. The classification is applied to every reporter in the mart, so the filters need
  **no code change** to light up as other reporters' data is used — the world view is already
  surfaced by the "Finalidade econômica" analysis. Spec: `PLANS/comtrade_flows_regimes_market.md`.

## [1.8.1] - 2026-06-30

Post-v1.8.0 adversarial audit of the change set (6-lens fan-out; 3 confirmed / 6 refuted,
0 critical). Three follow-up fixes.

### Fixed
- **Yield ranking no longer mislabels kg/ha with a magnitude word (audit CORR-1).** BarChart
  gained a `compact` flag and ViewProductivity passes `compact={false}`, so a 3.500 kg/ha yield
  reads "3.500" — matching the per-UF tile map — instead of "3,5 mil". The v1.8.0 compact-label
  change had applied magnitude scaling to unit metrics too.
- **Raw-table browse offset is now bounded (audit COST-1).** The "Estrutura de dados" explorer
  exposed Bronze/Silver tables to the free `tabledata.list` browse path, which passes the request
  `offset` straight to `start_index`. `RAW_TABLE_MAX_OFFSET` (5M) clamps it in `fetch_table_rows`
  and `fetch_seed_rows`, so an absurd `?offset=…` can't trigger a needless deep storage skip.
- **Backend "Estrutura de dados" view description matches the frontend (audit CONS-1).** The
  parity registry entry regained its trailing "Para conferir os dados ou rastrear de onde vem
  cada número." clause.

## [1.8.0] - 2026-06-30

Mobile-responsive pass, a 4-layer data-structure explorer, a per-(banco × perspectiva)
page hero, width-adaptive charts, and a 17-dimension audit remediation. Backend 1200
pytest / 99.91% coverage, frontend 730 vitest; all live-verified on prod BigQuery.

### Added
- **"Estrutura de dados" perspective** — browse every table across all four medallion layers
  (Bronze → Silver → Gold → Serving), grouped by layer, with row-level inspection (server-side
  pagination, sort, per-column filters, CSV export) (#185).
- **Mobile-responsive layout** — off-canvas sidebar drawer (hamburger, ≤768px), a
  pinned-to-viewport perspective sheet, and a decluttered phone topbar (mode toggle → drawer,
  utility actions → "⋯" menu) (#180, #183, #184).
- **Per-(banco × perspectiva) page hero** — the intro text now reflects the active banco *and*
  perspective; selfData perspectives (Produtividade/PAM, Fluxos, Sazonalidade) on a live banco
  now render the full hero with the maturity banner + provenance/selection box (#185).
- **PR-level dbt unit-test gate** in CI (#179).

### Changed
- **Dynamic app version** — the dashboard reads its version from the package metadata instead of
  a hardcoded `v0.1.0` (#185).
- **Charts adapt to tight space** — annual axes thin their year labels to the rendered width
  (`yearAxis()`), bar value labels use compact magnitude ("2,9 bi"), and the year × UF heatmap
  moved to a linear axis so its labels never crush (#185).
- **About / status indicators** — friendlier per-banco onboarding copy, a dedicated colour for
  the "ingestão" maturity tag, harmonized hero status pills (maturity + usage), and a beta caveat
  banner that reads the same registry description as the "Sobre" legend (#185).
- **~99% test coverage** with CI coverage gates (backend → 100%, frontend src/ui → ~88%) (#181).

### Fixed
- **Solid chart hover tooltips** — the shared layout pins an opaque background (was transparent),
  and the year-over-year chart drops a d3 sign flag that made Plotly dump the raw unrounded
  percentage (#185).
- **Card text never overflows** — a global overflow-wrap guard, and the geographic auto-scale uses
  per-tile magnitude so small UFs aren't rounded to zero nor large ones clipped (#185).
- **17-dimension audit remediation** — purge `code_prefix` resolution, REST `flow` validation,
  curation orphan-cache invalidation, and assorted backend / dbt / frontend hardening (#185).
- **dbt** — PPM unit test mocks `product_unit_factors` (un-breaks the prod build) and the 1985
  PAM/PPM currency-reform correction (#178, #179).

## [1.7.0] - 2026-06-27

### Added — Curadoria: researcher-editable commodity catalog

Replaces the rejected Google-Sheets "contrato de dados" proposal with an **in-dashboard**
admin surface writing to BigQuery `research_inputs`. Researchers now control what enters and
exits the dashboard without a deploy, with the destructive path kept human-gated. Spec:
`PLANS/curadoria_catalogo.md`. 941 pytest / 273 vitest green; the Gold cutover was proven
row-identical on real data and the whole feature was live-verified end-to-end on prod BigQuery.

- **3-way nomenclature split.** The frozen feature historically called "Curadoria" is really
  *feature engineering* → renamed `serving/attribute_engineering.py`; the shared
  append-log / IAP-author / idempotency infra is `serving/research_inputs.py`; the name
  **Curadoria** now means the catalog (what enters/exits).
- **Referências** — a read-only viewer for the calibration seeds (currency-reform factors, unit
  conversions, code/country dimensions, …) with a per-row "reportar valor incorreto" →
  feedback loop. No edit rights; engineers fix the version-controlled CSVs.
- **Editable commodity catalog.** `research_inputs.produto_catalog_log` →
  `core/dim_produto_catalog` → `gold_produto_agrupamento`; the `commodity_crosswalk` **seed is
  RETIRED**. Append-only writer (IAP author + `change_id` idempotency), a per-catalog editor
  allowlist (`research_inputs.catalog_editors`), an on-write prefix-disjointness guard, and the
  **"Cadastro de commodities"** admin UI (add / remove / edit; the in/out *Ciclo de Vida* per
  Agrupamento).
- **Orphan → Descontinuado lifecycle.** A commodity removed from the catalog whose Gold data
  still lingers is auto-detected (on the dbt-build boundary) and marked Descontinuado with a
  deletion warning — **never auto-deleted** (the orphan definition is the *removal transition*,
  grounded on real data to avoid false-flagging legitimately-uncataloged products).
- **Human-gated purge.** `embrapa purge-orphan` is a backup-gated *planner* that prints the
  scoped `DELETE`s for an operator to run (the agent never runs them); `embrapa mark-orphans`
  drives the auto-mark on the build cadence.

### Added — Q1 quality outlier/problemático detection

`data_quality_flag` is now a **9-value taxonomy** (was 4–5), surfacing implied-price anomalies on
top of the missing/incomplete flags. Spec: `PLANS/quality_outliers_and_visibility_gate.md`.
Activated in prod via a Gold rebuild (it rewrites `data_quality_flag` row-by-row).

- **The 9 values** (id → pt-BR label): `OK` → *Normais*; `MISSING_VALUE` → *Valor financeiro
  ausente*; `MISSING_QUANTITY` → *Quantidade ausente*; `MISSING_WEIGHT` → *Peso ausente*
  (COMEX/COMTRADE only); `INCOMPLETE` → *Incompleto*; `OUTLIER_QUANTITY` → *Quantidade atípica
  (válida)*; `PROBLEMATIC_QUANTITY` → *Quantidade problemática (provável erro)*; `OUTLIER_VALUE` →
  *Valor atípico (válido)*; `PROBLEMATIC_VALUE` → *Valor problemático (provável erro)*.
- **Outlier vs problemático.** An **outlier** is a high-magnitude but price-consistent row (a real
  big number). A **problemático** row has an implied unit price (value ÷ quantity) more than
  `quality_price_k` (=100×) above or below the product's median — i.e. a likely typo (e.g. the
  COMTRADE `weight = 1` placeholders).
- **Magnitude floor.** `quality_value_floor` (=100 000) skips rows below this deflated-BRL / USD
  value, stripping tiny-municipality rounding noise so a single global threshold works across all 5
  sources. IBGE is scored on the **deflated** `val_real_ipca_brl` (nominal would manufacture a fake
  pre-1995 hyperinflation tail); trade on nominal USD value / `net_weight_kg`. PPM stock (herd) rows
  have no value, so they are scored qty-only.
- **dbt vars** (`dbt/dbt_project.yml`): `enable_quality_outliers` (now **TRUE** in prod; `false`
  falls back to the legacy 4-value flag, compiled byte-identical), `quality_price_k` = 100,
  `quality_outlier_k` = 4.0, `quality_min_obs` = 100, `quality_value_floor` = 100 000.
- **Materialized rates** (share of **all rows**, from `serving.serving_quality_by_source`) —
  *problemático*: PEVS 0.0009 %, COMEX 0.0057 %, PAM 0.020 %, PPM 0.0003 %, COMTRADE 0.15 %;
  *outlier* (the valid-but-large tail): PEVS 0.42 %, PAM 0.29 %, PPM 0.46 %, COMEX 0.61 %,
  COMTRADE 0.24 %.

### Added — F7 Ciclo de Vida visibility gate

A commodity a researcher marks **"Fazer Ingestão mas deixar indisponível"** (ingest, but keep
unavailable) is now hidden from every researcher-facing Gold read, while still visible to the admin
editor and the crosswalk. **No-op today** (0 hidden rows). Spec:
`PLANS/quality_outliers_and_visibility_gate.md`.

- New dbt model `core/dim_produto_visibility` (a view of `(source, code_prefix)` for the hidden
  commodities), the `hidden_code_predicate` macro, and `serving/sql.visibility_clause` (the Python
  builder used by the gateway's direct-Gold readers).
- The gate is applied at every researcher-facing Gold read: the 6 serving marts,
  `serving_quality_by_source`, the cross-source picker (`seam_base`), and the gateway direct readers
  (município cube, quality timeseries, quality-by-product).
- Kept **separate** from `dim_produto_catalog` so the admin editor and `gold_produto_agrupamento`
  still see the hidden rows.

### Fixed — Contrato de Dados integration

- **7th maturity stage "Ingestão".** Bank maturity gained an `ingestao` level (label *Ingestão*,
  order 3, `has_data = false` — "pipeline built, data still loading") in both `frontend/.../bancos.js`
  (`window.MATURITY`) and `webapi/registries.py` (`MATURITY`), kept at parity.
- **Quality healthy label renamed `OK` → `Normais`**, including the **"(flag = OK)" → "(Normais)"**
  KPI relabel.
- **"Tabelas de referência" sidebar entry** regained its `table_chart` icon.

Remediation of the 2026-06-24 post-v1.6.0 deep audit (report:
`docs/audits/deep_audit_2026-06-24_v1.6.0.md`; grade A−, 0 critical). All confirmed findings
(1 high, 4 medium, 3 low) fixed; 915 pytest / 267 vitest green.

### Fixed
- **`deploy.sh` no longer disables the feedback GitHub loop on redeploy (audit INFRA-1).**
  `FEEDBACK_GITHUB_REPO` is now in the env allowlist and the `FEEDBACK_GITHUB_TOKEN` secret is
  mounted via `--set-secrets` when it exists, so a routine `make webapi-deploy` keeps the loop
  active (it was silently dropping both before).
- **Feedback is written to BigQuery BEFORE the GitHub forward (audit FB-1).** The durable row
  lands first (`issue_url` NULL) and is stamped after a successful forward, so a GitHub failure
  can never orphan an issue without a log row; the docstring is corrected.
- **Curadoria freeze completed (audit FREEZE-1).** Stale `?ip=curation` / `enrich_*` deep links
  now render a neutral "Versão Futura" notice instead of the frozen editor, and the curation
  glossary section is hidden — the app is fully decoupled from curation, even via direct URL.
- **No dev-vs-prod JSX-runtime divergence (audit DEV-1).** The classic JSX runtime is now used
  in dev, build AND Vitest (`vitest.setup.js` supplies the global `React`), so all three
  exercise the same compilation path instead of dev-only-classic vs build/test-automatic.
- **Feedback message is fenced in the GitHub issue (audit SEC-1)** — no Markdown / @-mention
  injection — and a **per-author cooldown** debounces double-clicks/abuse (audit SEC-2,
  `FEEDBACK_COOLDOWN_SECONDS`, default 5s, returns 429).

### Added (tests)
- Coverage for the GitHub-forward success path, the FB-1 write-then-stamp ordering, the SEC-1
  fence, and the SEC-2 cooldown (audit TEST-1).

### Docs
- Operations runbook + `.env.example`: the feedback `FEEDBACK_GITHUB_*` Secret Manager wiring +
  the fine-grained `issues:write` token guidance (audit DOC-1).
- Completed the 2026-06-24 deep audit (`docs/audits/deep_audit_2026-06-24_v1.6.0_complete.md`):
  confirms every fix above holds, corrects a stale `CLAUDE.md` line that called the **frozen**
  Curadoria "activatable" (audit DOC-2), and records the **live prod grain + conservation
  re-check** (audit DATA-1) — all 7 Gold tables grain-unique, `gold_source_metadata` ties exactly
  to the facts (e.g. comtrade 2,294,874 rows), and the COMTRADE World-partner double-count guard
  holds (0 rows).

### Changed
- **`deploy.sh` preserves prod-only env across routine deploys.** A new git-ignored
  `deploy/webapi/.env.prod` (template: `deploy/webapi/.env.prod.example`) is layered on top of
  the repo-root `.env` (same allowlist; prod values win), so `IAP_AUDIENCE` and
  `FEEDBACK_GITHUB_REPO` — which don't belong in a dev/worktree `.env` — are applied on every
  `make webapi-deploy` instead of being silently dropped. This removes the image-only-deploy
  workaround and keeps the in-app IAP JWT verification + the feedback cooldown armed. With
  Curadoria frozen, the feedback channel (`submitted_by`) is now the live consumer of
  `IAP_AUDIENCE`.

## [1.6.0] — 2026-06-24

Headline release of the 2026-06-24 work: the **in-app feedback channel** ("Reportar problema" →
append-only BigQuery log + IAP author + optional best-effort GitHub-issue loop), **roadmap management
moved to Google Drive** (`ROADMAP.md` / `TODO.md` retired), the **Curadoria feature frozen** (deferred
to the "Versão Futura" roadmap phase, hidden from the UI), and the **rolldown-vite dev server repaired**
(`npm run dev` was blank-screening on a CJS `require` the dev server didn't rewrite to ESM). Plus the
second-pass remediation of the 2026-06-23 **post-release audit** of v1.5.3 (15-dimension,
adversarially-verified; 37 confirmed findings) and a focused deduplication sweep. Validated:
910 pytest / 267 vitest green; ruff+format+eslint clean; `vite build`, `dbt parse`, `dbt compile`
and `sqlfluff` clean.

### Fixed
- **CAGR ("CAGR a.a.") no longer inflated for series with internal year gaps.** Both
  ViewProductCompare AND ViewCrossSource annualized over the array length instead of the
  calendar-year span; per-product series are ragged (the backend emits only existing
  `(code, year)` rows), so a gapped window overstated the rate. Both now derive the period from
  the year span via a shared `window.spanYears` helper.
- **The "Valor e volume" view no longer blanks on auto-scaled stacked composition.** Its
  per-year stack total was computed by array index across ragged product layers, throwing a
  `TypeError` (or silently dropping tail years). Now aggregates by year via `window.stackYearMax`.
- **The composition Donut renders a visible ring for a single 100% slice** (a full-circle SVG
  arc collapsed to a blank ring — the common single-product selection).
- **Sub-UF/município IBGE ingestion robustness:** the IBGE-1 deadline fix had saturated every
  per-state retry budget to the 600s drain ceiling; the retry budget is now decoupled (geo-scaled
  drain CAP, request-volume retry budget), so one slow state can't eat the nightly task timeout.
- **dbt:** the `commodity_crosswalk` seed now pre-accepts `'ppm'` (the documented PPM-linkage step
  no longer hard-fails `dbt build`); `comtrade_cpc_value` pins the `mot/mos/partner2` breakdown
  axes like Silver (no double-count); the flow-market "current" read breaks `edited_at` ties on
  `change_id` deterministically.
- **Local safety hook:** the `mkfs` guard now blocks `mkfs.ext4`/`mkfs.xfs` (a `\\w` regex typo let
  the only form anyone types through), and the dbt-prod guard no longer false-positives on
  `--full-refresh --target prod` flag order.

### Changed (security / hardening / internal)
- **Cost guard:** the product-basket `codes` IN-list is now capped symmetrically with `cityCodes`
  (`_MAX_BASKET_CODES`), via `_csv_param` (SEC-1).
- **Promoted the COMTRADE single-year invariant from `assert` to an unconditional raise** (survives
  `python -O`).
- **Deduplication** (each behaviour-preserving + verified): a shared `annual_deflation_ctes()` dbt
  macro replaces the FX+inflation CTE block copied across the four Gold models (−243 lines; compiled
  SQL proven byte-identical via offline `dbt compile` + normalized diff); `resolve_clients` /
  `resolve_bq_client` now own client construction (was inlined in 5+ sites); a `magnitude.js`
  kernel + `window.scaleLabel` end the bi/mi/mil ladder + currency-label grammar duplication; an
  `EmptyCard` atom replaces three copied empty-states. PAM/PPM now wire the `product_unit_factors`
  override like PEVS (inert today — uniform behaviour).
- **Docs/parity sweep:** COMTRADE coverage start year reconciled to 1989 in both filter hints;
  `webapi/registries.py` gains the PPM `herd` capability + `rebanho` view; `contracts.js`,
  `cache.py` and `.env.example` (`BQ_BANCO_METADATA_TABLE`) brought current.

### Removed
- **`ROADMAP.md` and `TODO.md` retired from the repo.** Project vision and evolution tracking now
  live in a Google Drive document maintained for business leadership (a simpler, render-friendly
  view for non-technical stakeholders). The doc map in `README.md` / `CLAUDE.md` points there;
  `PLANS/` (engineering specs) stays in-repo and `CHANGELOG.md` remains the canonical per-version
  record of what shipped.

### Changed (product / scope)
- **Curation/enrichment ("Curadoria") frozen — deferred to the "Versão Futura" roadmap phase.**
  Per leadership decision, the partially-built, not-yet-validated data-curation feature (the per-code
  industrialization + market-nature editor and its two curated analyses) is now HIDDEN from the
  dashboard UI: the "Análises curadas" perspectives (`frontend/src/ui/views.js`) and the "Engenharia
  de atributos" sidebar editor (`AppShell.jsx`) are commented out behind FROZEN banners. The app runs
  100% decoupled from it; the backend routes, serving writers, and the SCD2 dbt view (already gated by
  `enable_curation`, default false) are kept in place + tested as the scaffold for the real future
  implementation, each marked with FROZEN comments. The operations runbook now warns against prod
  activation while frozen. No data or behaviour change for any active view.

### Added
- **In-app feedback channel ("Reportar problema").** A new dashboard button opens a modal
  (bug / dúvida / sugestão) that POSTs to `/api/feedback`; the report is written to an
  append-only `feedback_log` BigQuery table, with the author captured from the IAP identity
  and reproduction context auto-attached (the permalink to the current view/filters, app
  version, optional user-agent). When `FEEDBACK_GITHUB_REPO` + `FEEDBACK_GITHUB_TOKEN` are
  set, each report ALSO opens a GitHub issue (best-effort — a failure never blocks or loses
  the BigQuery write); unset = BigQuery-only. Reuses the curation append-log + IAP-author
  pattern. (`serving/feedback.py`, `webapi/routes.py`, `frontend/src/ui/FeedbackModal.jsx`,
  `frontend/src/data/feedback.js`.)

### Added (tests)
- Regression tests for the ragged-series fixes (`cagrPct`/`spanYears`/`stackYearMax`, single-slice
  Donut), the `_MAX_MUNICIPIO_CODES`/`_MAX_BASKET_CODES` caps, the n6 retry-budget decoupling, the
  dbt `change_id` tiebreaker + breakdown pins, and `scaleLabel`.
- **First automated coverage for `scripts/`:** Node `--test` cases for the safety-hook regexes (wired
  into CI) and a fixture test for the IBGE municipal mesh-seed generator (`_row()`).

---

## [1.5.3] — 2026-06-23

Remediation of the 2026-06-23 **full-codebase audit** (13-dimension, adversarially-verified;
report at `docs/audits/full_codebase_audit_2026-06-23.md`). Baseline health was already A− with
0 critical issues; the changes below close 2 displayed-number HIGHs, a cluster of geography-feature
gaps, and routine hardening.

### Fixed
- **The UN Comtrade banco no longer sums the whole world's trade for 2022-2023.** Its own
  overviewTS + productTS read the multi-reporter `serving_comtrade_annual` mart WITHOUT pinning a
  reporter, so for the all-reporters backfill years the "Valor total" KPI and the value/volume
  series conflated every country's trade (a large spurious jump at 2022). Both readers now pin
  `reporter = Brazil`, matching the already-correct partner/flow/cross-source readers. (audit NUM-1)
- **Sub-UF / município geography filters now survive Compartilhar / Citar.** The five v1.5.2 geo
  dimensions were missing from the share-link codec, so a cited panel silently dropped the
  territorial narrowing; they now round-trip through the URL (and `urlDecodeNum` rejects a malformed
  numeric param instead of propagating `NaN`). (audit RVC-1)
- **The Geography "Município" granularity panel shows real data.** It rendered an always-empty
  legacy list (no backend producer); it now ranks municípios from the live município cube, with an
  honest empty-state, and the button is hidden for UF-only trade bancos. (audit GEO-1)
- **Value/Volume and Concentration views no longer flash a basket-dropped figure** during the
  product × UF cube load — they honour the same `geoComboPending` guard the Overview already used.
  (audit DATA-1)
- **Ingestion robustness:** an empty/truncated COMEX download is retried as a transient instead of a
  hard chunk failure (COMEX-1); the SIDRA drain deadline scales with a state's município count so a
  dense state can't time out on a slow night (IBGE-1); the run monitor no longer crashes on a null
  scalar and stops printing a bogus `rows=0` (OBS-1/2).
- **`embrapa doctor`** backup-freshness compares fractional days, so a snapshot just past the
  threshold is correctly flagged stale.

### Changed
- **API hardening:** `POST /api/municipio-yearly` caps + type-checks `cityCodes` (a pathological or
  non-list payload is a clean 400), the app sets `MAX_CONTENT_LENGTH`, and `_json_safe` serializes
  `decimal.Decimal`. (audit SEC-1/2/4, JSON-1)
- **dbt tests:** the Gold→serving value-conservation test and the unconvertible-quantity
  curation-surface test now cover PPM and COMTRADE; `dim_geo_municipio`'s sub-UF columns are
  documented for `persist_docs`. (audit DBT-1/2/3)
- **CI / infra:** the release workflow runs a lint+test gate before publishing the prod image; the
  deploy scripts fail loudly instead of silently defaulting to `:latest`; the destructive-command
  hook now covers `gcloud run jobs` / `scheduler` / `secrets` / `iam` / `monitoring` delete.
  (audit INFRA-1/2/3)
- Documentation sweep (README / ARCHITECTURE / ROADMAP / SECURITY / dbt) to reflect IBGE PPM, the
  v1.5.2 geography feature, and the current supported version. (audit DOC-1..9)

### Security
- **Dependency CVE bumps** (`uv lock --upgrade`): cryptography 48 → 49 (the one with unambiguous prod
  reach — the TLS path to GCP), Flask 3.0.3 → 3.1.3, Werkzeug 3.0.6 → 3.1.8, pydantic-settings
  2.14.1 → 2.14.2, msgpack 1.1.2 → 1.2.1. The remaining advisories in the set were present in the
  lockfile but not reachable in this codebase.

---

## [1.5.2] — 2026-06-23

The **IBGE sub-UF geography** feature (shipped in #157 but previously undocumented) plus
two rounds of audit remediation: the 2026-06-22 quality audit (11 findings — see
`docs/audits/quality_audit_2026-06-22.md`) and a 2026-06-23 manual-scan follow-up on the
freshly-shipped geo code (3 edge-case robustness bugs). Security core re-confirmed clean.

### Added
- **Sub-UF geography + live município filter (IBGE municipal mesh).** The geography filter
  now offers the IBGE territorial levels BETWEEN UF and município — BOTH parallel divisions:
  classic **mesorregião → microrregião** and 2017 **região intermediária → imediata** — plus
  **município** as a live filter. Backed by a new `ibge_municipio_mesh` seed (~5570 municípios
  → both divisions; refreshed by `scripts/refresh_ibge_municipio_mesh.py`), the conformed
  `dim_geo_municipio` dim, a município-grained serving cube read straight from Gold
  (city-scoped + `maximum_bytes_billed`-guarded), and two BFF routes: `GET /api/geo-mesh`
  (the cascade universe) + `POST /api/municipio-yearly` (the basket + city-scoped cube). The
  cascade engine reconciles two parallel sub-UF branches with a "following" refill (re-selecting
  a parent restores its children). Applies to the municipality-grained IBGE bancos
  (`ibge_pevs`/`ibge_pam`/`ibge_ppm`); COMEX (UF-origin) / COMTRADE (international) are unaffected.

### Fixed
- **The Geography view now honours the flow filter for a COMEX product basket.** The
  basket-scoped `/api/geo-yearly` cube dropped the active export/import direction (while
  the snapshot applied it), so VALOR TOTAL + the choropleth showed all-flows figures,
  internally inconsistent with the flow-filtered rest of the app. `flow` now threads the
  frontend cache key + request → `/geo-yearly` → `seam.geo_yearly` → the gateway reader
  (which already applied it). (audit M2)
- **`ingest reconcile` now covers the PAM and PPM SIDRA sources.** The old-year
  upstream-revision escape hatch skipped every `in_all=False` source, so a correction to
  an old PPM (live) or PAM year was never re-queried; reconcile now re-fetches them
  `--full` alongside BCB/COMEX (COMTRADE stays excluded, key-gated). (audit M1)
- **UN Comtrade daily-quota exhaustion exits 0, not 1.** Quota is expected and
  self-healing (the next scheduled run resumes), so it no longer trips the Cloud Run
  job-failure alert; a genuine non-quota chunk failure still exits 1. (audit L6)
- **`fetch_banco_metadata` now honours `CACHE_CLASSIFICATION_TIMEOUT`.** It was the one
  curation-class read left pinned at the decoration-time default, contradicting its own
  "a Console maturity flip reflects within the window" contract. (audit L8c)
- **The município cube is requested via POST, so a broad sub-UF selection no longer 414s.**
  A wide narrowing (e.g. most mesorregiões of a large UF) resolves to thousands of city codes;
  sent in a GET query string they overflowed gunicorn's request-line limit (~4 KB → HTTP 414).
  They now travel in the POST body, and a non-empty city set is required — so the backend never
  scans the full ~146k-row município grid. (audit 2026-06-23 A/D)
- **An empty sub-UF selection reads as honest "no data", not an eternal spinner.** A
  legitimately-empty município cube (`[]`) was conflated with not-yet-loaded (`null`), pinning
  the view at a permanent loading state; an empty result also no longer silently falls back to
  the all-UF grid (which showed data the selection excludes). (audit 2026-06-23 B)
- **A not-yet-built `dim_geo_municipio` degrades to an empty payload, not a 500.** The geo
  readers now catch `NotFound` (mirroring `banco_metadata_overrides`), so a fresh/dev/PEVS-only
  environment returns `{municipios: []}` instead of 500-ing the whole geography menu — matching
  the documented contract. (audit 2026-06-23 C)

### Changed
- **pre-commit ruff pinned to v0.15.13** (was v0.6.9), matching the ruff CI runs, so the
  local hook can't format/lint differently than CI. (audit L1)
- **Dependabot now watches the Docker base images** (`deploy/webapi`, `deploy/ingestion`)
  so a `python:3.12-slim` / `node:22-slim` CVE surfaces as a PR. (audit L2)
- **`__version__` reads from package metadata** and `pyproject` version bumped to `1.5.1`
  (was a stale `1.0.0`; `__init__` was `0.1.0`). Nothing user-facing read either —
  cosmetic. (audit L3)
- **A warn-severity `not_null` test on the curation `edited_by` author** closes the one
  untested column on the SCD2 audit trail. (audit L8b)
- **`sa-secret-reader-prod` dev-workflow grant doc corrected** to `roles/bigquery.user`
  (matching the permission matrix + the ps1 grant script; the walkthrough said
  `jobUser`). (audit L7)

### Docs
- Added IBGE PPM to the ARCHITECTURE folder/model/scheduler trees, the `doctor` sample in
  `docs/testing.md`, and the dataset list in `docs/ownership_transfer.md` (PPM has been
  live since v1.3.0 but was missing from these). (audit L4)
- Documented the one accepted long-lived SA key (`sa-claude-code-web-dev`) + a 90-day
  rotation reminder in `SECURITY.md` / `docs/auth_architecture.md` (both previously
  claimed "no long-lived keyfiles"). (audit L7)
- Noted that editing a seed an incremental model consumes needs `--full-refresh`
  (silver_ibge_pevs header + the dbt-workflow skill). (audit L8a)
- **Documented the sub-UF geography feature across the living docs** (ARCHITECTURE,
  `docs/gold_data_model.md`, `docs/frontend_data_contract.md`, CLAUDE.md, `scripts/README.md`) —
  it had shipped in #157 with only a `PLANS/` entry. Added a cross-source `dim_geo_municipio`
  vs `dim_geo_br` UF→região consistency test. (audit 2026-06-23 docs)

---

## [1.5.1] — 2026-06-21

Hardening pass on the new **"Dados (tabela)"** raw-table endpoint, from a security-weighted
adversarial audit (40-agent sweep). The audit **confirmed the security core holds** — no SQL
injection, no arbitrary-table read past the `(banco, table)` allowlist, no cache exhaustion —
so this release is robustness + correctness on the same surface, not a vulnerability fix.

### Fixed
- **Malformed filter input now returns a clean `400`, never an opaque `500`.** A missing/`null`,
  non-numeric, non-finite (`inf`/`nan`), or non-scalar (list/dict) filter value used to raise a
  bare `TypeError`/BigQuery error that fell through to the 500 handler (with a spurious
  "Unhandled error" log). `serving/sql._coerce_filter_value` + `webapi/routes._parse_table_filters`
  now reject these as `ValueError → 400`.
- **Filtering a `DATE`/`TIMESTAMP` column works.** Such a column bound its value as `STRING`,
  so `last_refresh = <string>` was a BigQuery type mismatch → 500. The comparison now runs
  against `CAST(col AS STRING)` (verified on prod: `reference_date`/`last_refresh` filters
  on `gold_pevs_production`).
- **NULL in an `INTEGER`/`BOOLEAN`/`DATE` column no longer 500s the page.** BigQuery surfaces
  these as pandas `pd.NA`/`pd.NaT` (not float `NaN`); the JSON encoder rejected `pd.NA` and
  `pd.NaT.isoformat()` leaked the literal string `"NaT"`. `webapi/app._json_safe` now maps both
  to JSON `null`.
- **`contains` filter matches literally.** It used `LIKE '%val%'` with no wildcard escaping
  (BigQuery `LIKE` has no `ESCAPE` clause), so a value with `%`/`_` over-matched. Now uses
  `CONTAINS_SUBSTR` (bound literal needle; verified on prod: `'%'` matches 0 rows, not all).
- **Transient `400` flash on banco switch removed.** `ViewDados` now gates the rows fetch on
  `tableBanco === database`, so it won't request the previous banco's table mid-switch.

### Security / cost
- **Tighter per-request byte cap for raw-table queries** (`RAW_TABLE_MAX_BYTES` = 10 GiB, vs
  the 100 GiB global guard) — defense-in-depth for a raw-data endpoint, while still allowing a
  full sort of the largest Gold table.
- **No internal attr on the wire** — the `/api/tables` payload dropped the dead `dataset`
  field (it leaked an internal config-attr name and the frontend never used it).

### Tests / docs
- End-to-end allowlist-rejection route test (out-of-allowlist `(banco, table)` → `400` through
  the real route→seam→gateway, no BigQuery), filter-coercion `400` tests, `_json_safe` NA/NaT
  test, `CAST`-comparison + `CONTAINS_SUBSTR` SQL tests, non-scalar-value `400` test, and a
  banco-switch render test. **868 pytest / 231 vitest green.**
- `/api/tables` + `/api/table` added to the canonical endpoint table in
  `PLANS/react_migration_contract_map.md`.

---

## [1.5.0] — 2026-06-21

New **"Dados (tabela)"** perspective on every banco — a faithful, unsummarized window onto
the actual rows so researchers can verify data line-by-line or hunt a value they suspect is
wrong. Preview-verified on real production data (2,4 mi linhas de `gold_ppm_production`).

### Added
- **Tabular data-inspection view** (`frontend/src/ui/ViewDados.jsx`, in the "Documentação
  do banco" group, universal). Per banco it lists the **principal (Gold) table + the serving
  marts that feed its charts** (so the derived tables are inspectable too), and for the
  selected table browses the RAW rows with **server-side pagination, ordenação (clique no
  cabeçalho) e filtros por coluna** (=, ≠, >, ≥, <, ≤, contém, é nulo) + **exportação do
  recorte em CSV** (até 500 linhas).
- **`/api/tables` + `/api/table` endpoints** (`webapi/routes.py` → `seam` → `gateway` →
  `serving/sql.py`). Security + cost by construction:
  - **(banco, table) allowlist** (`gateway._INSPECT_TABLES`) — only a banco's own Gold +
    serving marts; any other table → HTTP 400 (no arbitrary-table reads, no Silver/Bronze).
  - **The table's live schema IS the column allowlist** — ORDER BY / filter columns are
    validated against `client.get_table().schema`; filter VALUES stay bound `@params`.
  - **Hybrid read**: a plain browse uses the FREE `tabledata.list` (no bytes billed); only
    an actual sort/filter spends a query, capped by `BQ_MAX_BYTES_BILLED`. Page size capped
    at 500 rows.

### Tests
- `ViewDados.test.jsx` (picker + grid + empty state); `serving/sql.raw_table_*` (column
  allowlist, bound filters, limit cap, bad-op/value rejection); `gateway` allowlist boundary;
  `serialize_table_page`; the `/api/tables` + `/api/table` routes (arg + filter-JSON parsing,
  400 on malformed). **863 pytest / 230 vitest green; eslint + ruff clean; build OK.**

---

## [1.4.2] — 2026-06-21

Audit remediation. A post-feature adversarial sweep (45 agents) found that making the
herd value-aware in 6 views still left the **same value-assumption bug class** in code
paths not touched by `1.4.0`/`1.4.1`: a herd basket (a value-less stock) silently
rendered R$ 0, empty maps, or wrong exports. Preview-verified on real production PPM data.

### Fixed
- **`dataFilters` cube path dropped `q_count`** — once a product-subset loaded the geo
  cube, the herd's geographic Gini/HHI/Lorenz collapsed to all-zero (the snapshot path
  kept it; the cube path didn't). `regionData` likewise now carries `q_count`.
- **Overview "Quantidade · Contagem" KPI blended incompatible quantities** — it summed
  ~68 bi eggs (a flow) + ~1.9 bi heads (a stock) across 8 non-additive species into one
  meaningless headline on PPM's default view. It is now **suppressed when the basket
  contains a stock**, with a note pointing to the per-species **Rebanho** view; the geo
  digest map + "UFs cobertas" counter read headcount for a value-less basket.
- **`ViewGeography` was herd-blind** — it now offers a **"Quantidade (cabeças)"**
  dimension (with a não-somar-entre-espécies caveat) instead of an all-zero Valor map;
  `value` is gated on having value so a herd defaults to cabeças.
- **`ViewValueVolume` showed R$ 0** for a herd — the monetary cards are gated on having
  value, with an honest note redirecting a herd basket to Rebanho.
- **CSV export** — added a `qtd_contagem_un` column to the aggregate/geo/concentration
  exports, and fixed the per-product export that **mislabelled a headcount as tonnes**
  (`fam==='volume'?…:t`) and scaled it 1000× wrong; now a family→unit map.
- **`ViewProductProfile` "Participação no efetivo"** denominator no longer blends the
  herd stock with egg/milk count-flows (a stock's share is among other stocks).
- **`serialize_products_by_uf`** now emits the `q_count` its SQL already computed (was a
  dead column), so 'Produtos do estado' can rank a herd by headcount.

### Changed / docs / tests
- `ViewProductCompare` titles the normalized chart "do efetivo (cabeças)" for an all-herd
  basket (was hardcoded "do valor"); `overviewTS` contract + `serialize_geo_yearly`
  docstring corrected; `frontend_data_contract.md` documents `measure_kind`/`q_count`;
  added the missing `.qa-facet` CSS.
- New lock-in tests: `serialize_product_uf` + `serialize_products_by_uf` q_count,
  ViewConcentration cabeças fallback, ViewOverview count-KPI suppression, `pearsonByYear`
  `key='q'`. **854 pytest / 228 vitest green; eslint + ruff clean; build OK.**
- **Baseline health stayed excellent** (96% backend coverage, sql.py 100%, max CC C(12)
  pre-existing, MI all A); security review confirmed **no new injection/SSRF/auth-bypass**.

---

## [1.4.1] — 2026-06-20

Refinement to the livestock herd feature (`1.4.0`), preview-verified end-to-end against
the local webapi on real production PPM data (composição Galináceos 82% / Bovino 12%, UF
líder PR; Perfil stock=Bovino mostra efetivo 238 mi cab sem Valor/Preço).

### Added
- **Stock/flow facet on the Qualidade view** — for a banco carrying `measure_kind`
  (livestock), the per-product data-quality breakdown splits into **Estoque** (the herd —
  value-less, so its flags are OK vs quantidade-ausente) and **Fluxo** (animal products —
  value + quantity). The two have structurally different flag profiles, so one merged list
  blurred the diagnosis.

### Changed
- **Overview count KPI relabelled** `Efetivo/contagem` → **`Quantidade · Contagem`** — the
  KPI sums the herd (a stock) AND eggs (a flow), so "Efetivo" overclaimed; the neutral
  label is consistent with the Massa/Volume quantity KPIs.
- **`vite.config.js`** — a `preview` proxy now mirrors the dev `/api` proxy, so a production
  build can be smoke-tested against the local webapi (`npm run preview`). Used to
  preview-verify this change: the experimental rolldown-vite **dev** server mishandles the
  injected JSX runtime ("require is not defined"), so the **build** preview is the reliable
  local-verification path.

---

## [1.4.0] — 2026-06-20

Makes the **IBGE PPM herd visible**. The livestock headcount — ~⅔ of
`gold_ppm_production`, the largest single body of rows the new banco added — was
structurally invisible as a quantity (every chart showed `q: null` for it). This
release gives `contagem` its own quantity track end-to-end and adds a dedicated
**Rebanho** perspective; no Gold rebuild (the headcount was already in `qty_base`).

### Added
- **New perspective: "Rebanho"** (`frontend/src/ui/ViewRebanho.jsx`) — the herd
  (efetivo dos rebanhos) view, gated on a new `herd` capability that only IBGE PPM
  provides. Cabeças-only (no monetary axis): latest-year composition by species
  (donut), 50-year per-species evolution (multi-line — never stacked, since heads of
  different species are not additive) and a per-UF headcount tile map of the focused
  species, with honest "estoque, não somar entre espécies" caveats.
- **`q_count` quantity track (the keystone)** — `contagem` (livestock head + eggs) gets
  its own per-family `qty_base` column across the serving readers (`serving/sql.py`) and
  the serializer (`webapi/serializers.py`), so the herd now renders a real quantity where
  it previously emitted `q: null`. `serialize_product_uf` also carries `q_count`, so a
  value-less stock ranks UFs by headcount instead of an all-zero value.
- **`measure_kind` (stock|flow) on the products list** — exposed PPM-only via a gateway
  flag (`with_measure_kind`), letting the UI separate the value-less herd (stock) from
  the animal-product flows (eggs/milk) that share the `contagem` family.

### Changed
- **Analytical views are now value-less-aware** — each perspective implicitly treated
  monetary `value` as the universal measure, which a stock (the herd) breaks. **Perfil
  do produto** swaps Valor/Preço for Efetivo/Pico and ranks UFs by headcount for a stock;
  **Visão geral** adds an efetivo KPI; **Comparativo** indexes (base 100) and correlates
  a herd on headcount instead of a flat-zero value line; **Concentração** falls back to
  cabeças (Gini/HHI/Lorenz) for a value-less basket.
- **Count formatters + unit registry** — new `formatCountQty`/`countQtyMul`/
  `countAxisLabel` (mirroring mass/volume); `UNIT_FAMILIES` re-keyed `contagem`→`count`
  to match the token the serializer emits — a latent mismatch that was dormant until the
  first count-family product rendered a quantity.

### Tests
- New `ViewRebanho.test.jsx` (herd built from stock species only; cabeças-only
  composition/evolution; honest empty state) + a count-KPI lock-in in
  `ViewOverview.test.jsx`; serializer + `sql.products`/`product_timeseries` gain
  `q_count`/`measure_kind` coverage. **853 pytest / 223 vitest green; eslint + ruff
  clean; vite build OK.**

---

## [1.3.0] — 2026-06-20

New dashboard banco **IBGE PPM** (livestock), now **LIVE in production**, plus a SIDRA
ingestion-robustness fix that unblocked its historical backfill.

### Added
- **New data source: IBGE PPM** (Pesquisa da Pecuária Municipal) — a new dashboard
  banco `ibge_ppm` for livestock: herd headcount (SIDRA 3939, Cabeças) + animal
  production (SIDRA 74 — leite/ovos/mel/lã, with value). PPM is **multi-table**
  (a first for the SIDRA sources): one `ingest ibge-ppm` ingests both tables into
  two Bronze tables, unioned in `silver_ibge_ppm` with a `measure_kind` (stock|flow)
  discriminator. New `gold_ppm_production` (no área/yield — livestock) + serving mart
  `serving_ppm_annual` ride the full deflation/FX matrix and the PEVS-shaped gateway
  readers with no new query SQL. Capability-wise PEVS-shaped (`provides` product/geo/
  quality, **no** produtividade). New `PPM_*` knobs + `BQ_BRONZE_PPM_{HERD,ANIMAL}_TABLE`;
  excluded from nightly `ingest all` (annual) — on-demand via `ingest ibge-ppm` + the
  monthly `schedule_ppm.sh` (cron `0 4 3 * *`). New unit_family_conversions seed rows
  fold the SIDRA ×1000 "Mil litros"/"Mil dúzias" scale. **Activated 2026-06-20**:
  Bronze backfilled 1974→2024 (2.27M herd + 3.41M animal rows) via the Cloud Run Job,
  Gold/serving built (2.4M-row `gold_ppm_production`, all dbt tests green on prod data),
  and the `banco_metadata` maturity set to `beta`.

### Changed
- **Volume-based dynamic SIDRA timeout + jittered exponential backoff** (#148) — the
  flat 75s per-request drain budget was too tight to stream a wide-window / many-product
  IBGE response when SIDRA is slow (it killed the PPM backfill: a cell-halved 13y ×
  8-product query for a big state couldn't drain in 75s, and a slow-byte timeout — unlike
  a cell-limit error — never triggered further halving). The drain + retry budgets now
  scale with the request's period×product×variable volume (above the lean floor, clamped
  to a ceiling), and `http_retry_policy` uses full-jitter exponential backoff to
  de-synchronise the parallel state-fetch workers. Shared by IBGE/BCB/COMEX.

---

## [1.2.0] — 2026-06-19

Capability-aware UI: the dashboard now surfaces **only what each data source can
actually do** — across the single-banco filter menu, the multi-fonte perspectives,
and the cross-source pickers — so the screen is never cluttered with options that
lead nowhere. Plus a leaner analytical bundle and a dead-code/doc sweep. No data or
mart-grain change — the new code runs against the existing prod Gold/serving tables.

### Added
- **Dynamic, capability-gated filter menu** (#143) — every filter option now loads
  from a per-banco schema (`FILTER_SCHEMAS`): a dimension appears only when the active
  banco provides it, instead of always-on filters that silently no-op. The **Fluxo**
  segment (exportação/importação) became a real **server-side** filter — it re-fetches
  the snapshot scoped to the chosen flow (the marts already carry `flow`; no dbt change).
- **Capability-gated multi-fonte perspectives** (#144) — the cross-source perspective
  picker now **disables** (with a "Demonstração" badge + reason) the perspectives whose
  source does not exist yet (`cross_chain`/`cross_lag` — they need SEFAZ inter-UF flows /
  monthly PEVS), via a new `crossViewApplies` gate (data-blocked / source-availability /
  ≥2 comparable series). The cross-source **series picker** hides banco cards with no
  comparable metric (PAM) and disables the chips of metric-but-no-data bancos (SEFAZ).
- **Family-gated commodity pickers** (#145) — the **Coeficiente de exportação** and
  **Preço: porteira vs. FOB** views (which compare PEVS mass to COMEX weight) now offer
  ONLY pure-mass commodities and open on a real indicator, instead of defaulting to the
  always-incompatible "Cesta completa". `/api/catalog` now carries each commodity's PEVS
  `family` (derived from the existing `_pevs_family_by_agrupamento` index).

### Changed
- **Leaner analytical bundle** (#141) — the audit-polish pass trimmed the Plotly
  payload, raised `webapi` test coverage, and documented `PYTHONUTF8=1` for local dbt
  on Windows (cp1252 crash fix).
- **Dead-code & doc-staleness sweep** (#142) — removed backend + frontend orphans,
  wired the dormant `contracts.js` runtime contract-lint, and fixed 5 stale docs;
  0 synthetic-data leftovers remain.

---

## [1.1.0] — 2026-06-19

Full remediation of the 2026-06-18 repository audit (#138) — **0 critical / 0 high**;
the focus was displayed-number correctness, plus security/robustness hardening and
test coverage. Verified live in production (dashboard reads + curation writes).

### Added
- **Security hardening** — `current_author()` fails CLOSED on Cloud Run without
  `IAP_AUDIENCE` (refuses to stamp a forgeable curation author); `deploy/webapi/deploy.sh`
  hard-fails post-deploy if `invoker-iam-disabled=true` or `iap-enabled≠true`; the
  `release.yml` `version` input is env-indirected + validated. New `embrapa doctor`
  **`currency-codes`** probe guards `BCB_CURRENCY_SERIES` against a stale-`.env` FX
  regression.
- **dbt numeric + grain tests** — a deflation/FX `unit_test` on `gold_pevs_production`
  (the scientific core, previously untested numerically; validated on BigQuery),
  uniqueness tests on the `silver_bcb_inflation`/`silver_bcb_currency` grain, and an
  `if: failure()` stale-marts alert on the nightly prod build.
- **Test coverage** — `serving/gateway.py` 80% → 99% (parametrized reader-wiring
  tests), frontend View render tests (ViewQuality/Overview/Concentration), and
  nested snapshot-contract drift detection.
- **Dependabot** now also covers the `pip` (Python) and `npm` (frontend) trees.

### Changed
- **ESLint now lints `frontend/src/ui/`** (the live production UI), fixing the
  previously-hidden dead code, stale `eslint-disable` directives, and hook deps.
- **Sidebar + modal accessibility** — sidebar items are keyboard/screen-reader
  operable (role/tabindex/Enter), and the filter + citation modals close on Escape
  with `aria-modal`.
- **`v1.1.0` deployed** — `IAP_AUDIENCE` is now set on the prod Cloud Run service, so
  curation uses the cryptographic IAP-JWT verification (no longer the spoofable
  plaintext header).

### Fixed
- **Quality-flag taxonomy** — the frontend registry now matches the real Gold flags
  (`OK/MISSING_VALUE/MISSING_QUANTITY/MISSING_WEIGHT/INCOMPLETE`). The stale prototype
  taxonomy was silently dropping `INCOMPLETE`/`MISSING_WEIGHT` from the Quality view +
  filter and leaking raw English ids in place of the pt-BR labels.
- **Physical-quantity scaling** — `product_timeseries` emits per-family base sums
  (`q_mass`/`q_vol`) so mass and volume are never blended and count/energy/area
  quantities are no longer mis-scaled (no more `count ÷ 1e6`).
- **COMTRADE partner ranking + flow Sankey** pin the reporter to Brazil, fixing the
  2022–2023 all-reporters multi-count.
- **COMEX freshness** — only the ETag confirms "current" (Last-Modified is too weak
  for a same-second republish); **COMTRADE** permanent truncations are logged
  distinctly (operator action required) instead of buried as a generic failure.
- **Docs** — a stale `src/proto` reference, 5 repo-escaping `../` links in
  `ARCHITECTURE.md`, the renamed curation SCD2 view/log-table names, the CONTRIBUTING
  CI-checks list, and the BCB delta-overlap granularity wording.

---

## [1.0.0] — 2026-06-18

### Added
- **Dedicated dashboard rebuilt as a React SPA + Flask REST `webapi`** (Plotly.js
  charts), replacing the Dash UI entirely — served from one origin behind Cloud Run
  direct IAP (`src/embrapa_dashboard/webapi/`, `frontend/`). The Dash package was
  removed at cutover.
- **Decoupled release CI** — `.github/workflows/release.yml` (#132) builds a
  versioned, immutable `webapi` image to Artifact Registry on a `v*` tag; deploy
  without rebuild via `WEBAPI_SKIP_BUILD=1 WEBAPI_TAG=vX deploy/webapi/deploy.sh`.
  Pinned action SHAs bumped to Node-24 majors (#133). `v1.0.0` released + deployed.
- **Per-UF chart scoping + new chart metrics (P1–P6, #131)** — partner metric
  toggle (value|weight|price), OLS trendlines, value-added volume+price, and a
  dual-metric seasonality; `serving_comex_seasonality` grain now includes
  `state_acronym` (×UF).
- **UN Comtrade world/all-reporters full-history backfill runbook** —
  `docs/comtrade_world_backfill.md` (#128), with a daily Cloud Run Job scheduler.

### Changed
- **IAP-only ingress + scale-to-zero, no load balancer (#122).** The dashboard runs
  Cloud Run direct IAP (`ingress=all` + IAP, `min-instances=0`) — the zero-fixed-cost
  posture; an external HTTPS LB stays future-only / out of scope.
- **`silver_comtrade_flows` is now incremental** (`insert_overwrite` by
  `reference_year`, #127) — caps the cost of the all-reporters backfill.
- **`reconcile` is operator-triggered + a monthly reminder issue**
  (`.github/workflows/reconcile-reminder.yml`, #130) — no longer an unconditional
  scheduled run.
- **Enrichment is now a sidebar SECTION with one screen per tool** (was a single
  "Curadoria" item opening one window with internal tabs). The "Enriquecimento"
  section holds **Nível de industrialização** (`?ip=enrich_industrial`) and **Tipo
  de Mercado** (`?ip=enrich_market`), each its own screen over the same shared
  institutional store — so each enrichment can be done separately. `ViewCuration`
  split into `ViewEnrichmentIndustrialization` + `ViewEnrichmentMarketNature` with a
  shared apply bar; the old `?ip=curation` deep link still resolves (→ industrialization).
- **9-commodity scope across every source** — castanha-do-brasil, madeira, açaí,
  cupuaçu, banana, mandioca, soja, milho, arroz, each on the sources that carry it.
  Codes verified (live SIDRA, official NCM table, WCO/HS); COMEX gained a 4-digit SH
  *heading* tier in the product matcher.
- **Full historical backfill**: IBGE PAM back to **1974** (monetary reform absorbed
  via `historical_currency_factors`, was 1994+); UN COMTRADE Brazil-reporter to **1989**.
- **IBGE PAM and UN COMTRADE graduated `beta → estável`** (complete data, no caveat),
  flipped through the new editable `research_inputs.banco_metadata` override table
  (maturity/coverage edits are a BigQuery `MERGE`, merged over the registry by
  `/api/source-meta` — no rebuild/redeploy).
- **Geo filter nação restricted to Brasil** for domestic bancos: the cascade no
  longer offers foreign "export destinations" (China/EUA/…) — a prototype fabrication
  that mapped to no column in any geo-cascade banco (dead options). International
  partners stay a real dimension only for COMEX/COMTRADE, via their own país/partner
  filters.

### Fixed
- **The VALOR TOTAL hero ignored the state filter and the choropleth ignored the
  product basket** (Overview/Geografia). Both stemmed from the per-banco snapshot
  lacking a product × UF × year grain (the honest "a cesta não recorta a distribuição
  por UF" note). A new basket-scoped cube — `/api/geo-yearly`, reusing the existing
  `serving_*_annual` `*_by_uf_yearly` readers with `product_codes` (**no new dbt
  model**) — now lets the hero, choropleth, ranking and series respect **state +
  product + período together** (the note clears once the cube loads). `applyFilters`
  pulls it on demand and sums it over the selected states client-side; the value
  column matches the snapshot's via the active currency×correction.
- **Transparent retired→current code translation** — the dashboard now exposes only
  current codes, with retired-code history folded into them: `comtrade_hs_succession`
  + `comex_ncm_succession` seeds applied in the silver models (`coalesce(succ.current
  _code, code)`; raw kept in `*_code_reported`, the true natural key for the uniqueness
  tests). Verified: 0 retired codes leak to Gold.
- **Full codebase audit + live visual inspection: 117 confirmed defects resolved.**
  A two-phase audit (automated metrics + an adversarially-verified manual sweep)
  found **106 issues, all fixed** — including the three once-deferred items: the
  commodity-level curation dead-code removal, the UF/state filter wired into the
  trade flow/partner readers, and **real year-FX BRL/EUR for trade bancos**
  (retiring the frontend mock-FX rates; trade values now come from the Gold
  columns). A subsequent **live dashboard inspection** found and fixed **11 more
  UI/data issues**, most notably: the Overview/Geografia **per-UF map showed an
  all-years cumulative mislabeled as the latest year** (the per-UF readers now
  scope to the latest year, matching the national KPI and the `ano × UF` heatmap);
  a **misleading year-over-year on an incomplete latest year** (now anchored on
  the last complete year, with the partial year marked "(parcial)" on the series,
  composition donut and map — the backend exposes `monthsInLatestYear` /
  `latestYearComplete` / `latestCompleteYear` on `/source-meta`); **"UFs cobertas"
  counted COMEX pseudo-origin codes** (ND/EX/ZN…) against the 27 real states
  (ufData rows now carry a `real` flag); stale filter-summary chips; a duplicate
  `/source-meta` fetch; and the Saúde "saudáveis" denominators. Also corrected:
  the dbt 1994 `val_yearfx_*` CR$/R$ changeover, the append-only Comtrade
  `cpc_value` dedup, the quality-flag taxonomy (real Gold flags), the implicit
  price for volume-family products (1000× overstatement), and COMEX/COMTRADE mass
  quantities (kg summed and scaled as tonnes). Decomposed all radon grade-C
  functions and added ~210 tests (Python 497→701, frontend 47→103); full suite
  green. Detailed report: `docs/audits/codebase_audit_2026-06-12.md`.
- **Geografia choropleth ("Mapa" mode) rendered blank.** Confirmed in production
  (not a headless artifact): `brazilUfGeo` shipped **143 empty `[]` sub-polygons**
  inside its MultiPolygons (a shape-simplification artifact), and maplibre-gl 4.x's
  geojson-vt worker throws "Cannot read properties of undefined (reading 'length')"
  on an empty sub-polygon, dropping the ENTIRE feature → 0 features → blank map. The
  GeoJSON is now sanitized once at load (`charts/geoSanitize.js`, unit-tested) into
  valid GeoJSON, and a `map.on('error')` handler surfaces any future maplibre error
  under our own prefix. The Geografia per-UF map/bars also gained the "(parcial)"
  marker on an incomplete latest year, matching the Overview.

### Removed
- **Chinese Yuan (CNY) dropped entirely.** The dashboard now offers only BRL, USD and EUR. Removed the external-FX path that sourced BRL/CNY (the `extfx_cny_brl` seed, `silver_extfx_currency`, and `scripts/refresh_cny_seed.py`) and dropped the `val_yearfx_cny` / `val_real_ipca_cny` / `val_real_igpm_cny` / `val_real_igpdi_cny` columns from every Gold fact (`gold_pevs_production`, `gold_pam_production`, `gold_comex_flows`, `gold_comtrade_flows`). Requires a `dbt build --full-refresh` to physically drop the columns; Looker Studio reports bound to the CNY metrics must unbind them (see `docs/looker_studio_setup.md`). China-the-country trade flows (COMEX/COMTRADE partner geography) are unaffected.

### Added
- **New data source: IBGE PAM (Produção Agrícola Municipal, SIDRA table 5457)** —
  annual crop production (área, quantidade, rendimento, valor) by municipality,
  the second IBGE/SIDRA source alongside PEVS. Lean first cut: 5 highest-value
  crops (soja, milho, café, cana, arroz) from 2010, surfacing **quantidade** and
  **valor da produção** in the dashboard (área/rendimento are carried in Gold for
  a follow-up). Reuses the generic SIDRA client; new `ibge/pam_pipeline.py`
  (two-phase Bronze, own `bronze_pam` dataset + `raw/ibge/pam/` segment),
  `ingest ibge-pam` CLI (**excluded from nightly `ingest all`** — annual,
  slow-changing — runnable on demand), `doctor` PAM probe + Bronze/serving
  targets. dbt: `silver_ibge_pam` → `gold_pam_production` → `serving_pam_annual`
  (column-identical to the PEVS mart, so PAM rides the source-parameterized
  gateway readers, the currency/correction toggles, and the quality views), plus
  a Silver→Gold conservation test. Banco `ibge_pam` graduates `planejado → beta`.
  Lean assumption: the monetary value is nominal R$ via ×1000 from "Mil Reais",
  valid for the post-1994 window (`PAM_START_YEAR` ≥ 1994). New knobs:
  `PAM_TABLE_ID`/`PAM_CLASSIFICATION_ID`/`PAM_PRODUCT_CODES`/`PAM_START_YEAR`/
  `PAM_END_YEAR`/`PAM_DELTA_OVERLAP_YEARS`, `BQ_BRONZE_PAM_{DATASET,TABLE}`.
- **IBGE PEVS is now delta by default** (like the BCB). `ingest ibge` / `ingest all`
  re-fetch only from `latest_bronze_year - IBGE_DELTA_OVERLAP_YEARS` (default 1)
  forward — absorbing PEVS revisions and a newly published year — instead of
  re-pulling 1986→today on every run (a huge request that blows SIDRA's slow-byte
  deadline on an unattended Cloud Run Job). `--full` forces the full window;
  `ingest ibge-batch` remains for the initial chunked historical backfill; a cold
  Bronze falls back to the full window. New helper `latest_reference_year`
  (`gcp/bigquery.py`) + `IBGE_DELTA_OVERLAP_YEARS` knob. Motivated by a Cloud Run
  Job smoke-run that failed on exactly this IBGE full-history fetch.
- **Architectural pivot — Pushdown Computing in the dashboard (replaces the
  in-memory/Pandas design, with its OOM/concurrency risk).** The dashboard (now the
  React SPA + Flask `webapi`) is **stateless**: UI filters turn into **parameterized SQL** (`@param`) on
  BigQuery, cached by **flask-caching**, instead of loading Gold tables into memory.
  - **dbt `serving/`**: marts pre-aggregated at the chart grains
    (`serving_pevs_annual`, `serving_comex_annual`, `serving_comex_seasonality`,
    `serving_comtrade_annual`, `serving_quality_by_source`) in the `serving` dataset
    (`BQ_SERVING_DATASET`), materialized as **tables** (cutting scan from GB→MB).
  - **dbt `core/`**: conformed dimensions `dim_date`, `dim_geo_br`; and the SCD
    Type 2 view `dim_code_industrialization_scd2` (gated by `--vars 'enable_curation: true'`).
  - **Dynamic curation (SCD2)**: append-only log
    `research_inputs.code_industrialization_log` (author captured from the IAP
    header `X-Goog-Authenticated-User-Email`); the UI does a live LEFT JOIN of the
    static mart to the classification dimension.
  - **Python BFF** (`src/embrapa_dashboard/serving/`, optional `serving` extra):
    `sql` (@param + anti-injection allowlist), `gateway` (`@cache.memoize`), `cache`
    (flask-caching — `SimpleCache` scales multi-instance for free; `RedisCache`
    optional), `iap`, `curation` (append-only INSERT + cache invalidation).
  - **Multi-instance scaling without Redis (for free).** The dashboard scales to
    3–5+ Cloud Run instances without Memorystore: marts converge on
    `CACHE_DEFAULT_TIMEOUT` (overnight data) and the curation classification read
    uses a **short TTL** (`CACHE_CLASSIFICATION_TIMEOUT`, default 30s) that bounds
    the staleness between instances (eventual consistency ≤30s) — the instance that
    edits invalidates immediately. `RedisCache` becomes **optional** (only for
    instant cross-instance consistency under high traffic).
  - **Automated ingestion**: `embrapa ingest all` packaged as a **Cloud Run
    Job** (`deploy/ingestion/`: Dockerfile, cloudbuild.yaml, deploy.sh, schedule.sh)
    + **Cloud Scheduler** overnight (off-peak). Shortcuts `make ingest-job-deploy` /
    `make ingest-job-schedule`.
  - **Reverts the previous "never pre-aggregate" stance**: Gold remains the
    comprehensive per-source table (ad-hoc aggregation at query time), but `serving/`
    materializes pre-aggregated marts for Pushdown — they derive from Gold, they do
    not replace it.
- **New source: UN Comtrade (global bilateral trade) — `gold_comtrade_flows`.**
  A global complement to COMEX (Brazil): worldwide `reporter→partner` flows for
  HS **0801** (nuts) + **chapter 44** (wood/charcoal), ingested at the
  **HS6** level (scope expanded to the 156 six-digit leaves), across the **four
  primary regimes** X/M/RX/RM, all reporters × all partners, annual grain.
  - **Ingestion** (`embrapa ingest comtrade [--full] [--from-raw]`): a *keyed*
    JSON API (`COMTRADE_API_KEY`, free), with the key **only** in the
    `Ocp-Apim-Subscription-Key` header (never in the URL/log). Two-phase raw zone,
    *chunked* by `(year, batch of 8 reporters)` and **resumable**. **Adaptive
    split** against truncation (`fetch_chunk_adaptive`): when a call hits the
    100k-row cap (a single dense reporter already overflows it), it recursively
    splits reporters→flows→cmd and concatenates. It stays **outside
    `embrapa ingest all`** (key/quota-gated).
  - **dbt**: `silver_comtrade_flows` (keeps only the fully aggregated record —
    `motCode=0`/`customsCode=C00`/`partner2Code=0`/`mosCode=0` — and HS6 only; drops
    the World partner `0`; normalizes `flowCode` X/M/RX/RM →
    `export`/`import`/`re-export`/`re-import`) and `gold_comtrade_flows` (the 4
    monetary conventions over `primaryValue` US$, **annual** deflation; bilateral
    reporter+partner geography via M49). Reuses `silver_currency` (USD/EUR/CNY) and
    `unit_family_conversions` (families).
  - **Seeds** of authoritative reference: `comtrade_country` (M49 → ISO3/name,
    `partnerAreas.json`), `comtrade_unit` (qtyUnitCode → family — 5=items, 8=kg,
    12=m³) and `comtrade_hs` (0801 + ch. 44, `HS.json`). Script
    `scripts/refresh_comtrade_country_seed.py`.
  - Initial historical window limited to **2022-2023** (config `COMTRADE_START_YEAR`/
    `COMTRADE_END_YEAR`) for development; extend later to older history.
- **Transport-modal dimension in COMEX (`via`).** `gold_comex_flows` gains
  `transport_route_code` (in the grain) + `via_name` via the new `comex_via` seed
  (MDIC CO_VIA codes → PT labels: Marítima, Aérea, Rodoviária…).
- **Cross-source product crosswalk** — seed `commodity_crosswalk` (links by
  *prefix*, at the commodity-concept level) + model `gold_produto_agrupamento`
  (resolves to an exact `(source, code) → commodity`). Links the same commodity
  across PEVS (extractive code) / COMEX (NCM8) / COMTRADE (HS6) — the basis for the
  cross analyses (export coefficient, market share, trade mirror).
- **Data contract document** `docs/frontend_data_contract.md` — a Gold →
  frontend-snapshot map (field, magnitude, unit) for the BFF handoff.
- **Per-source provenance metadata** — view `gold_source_metadata` (one row per
  source: table, cadence, year coverage, counters `total_rows`/
  `products_total`/`ufs_total`, `last_refresh`), derived from the Gold tables. It
  feeds the frontend `dataStore.meta(id)` seam (provenance comes from the backend,
  not from literals); `implStatus`/`visible` stay as runtime config, documented in
  the contract.

### Changed
- **Quantities by physical unit family (schema break, no backward
  compatibility).** The fixed `[kg, t, m³, L]` format was removed. Every quantity
  row in Gold now exposes `family` (`massa`|`volume`|`energia`|
  `contagem`|`area`|`desconhecida`), `unit_native` (source label), `qty_native`
  (native value), `qty_base` (converted to the family's base unit) and
  `base_unit` (`t`/`m³`/`MWh`/`un`/`ha`). The conversion happens in **Silver**
  (Gold already delivers the final format). **`gold_pevs_production`** swaps
  `quantity_tons`/`quantity_m3` for these columns; **`gold_comex_flows`** swaps
  `stat_unit`/`stat_unit_symbol`/`statistical_quantity` for
  `unit_native`/`unit_native_symbol`/`qty_native`+`qty_base`+`family`+`base_unit`
  (statistical-unit resolution moved from Gold to Silver;
  `net_weight_kg` remains as a parallel mass-kg). **Rule:** never sum
  `qty_base` across families — every aggregation requires `GROUP BY family` (build
  `q_by_family = {massa:Σt, volume:Σm³, …}` at query time). Monetary value
  remains family-agnostic and summable.
  - New versioned seeds: **`unit_family_conversions`** (unit →
    family + `to_base`, single source — no factor hardcoded in queries) and
    **`product_unit_factors`** (a product→factor crosswalk for commodity units
    like saca/@/bushel/barril, which overrides the generic seed; no row → null
    `qty_base`, flagged for curation — never an invented conversion).
  - `data_quality_flag` reassigned to `(qty, val_brl)`. New curation (warn) test
    `assert_unconvertible_quantities_for_curation` and a
    **dbt unit test** with one case per family + a crosswalk override.
  - ⚠️ **Operational:** `silver_ibge_pevs` is incremental — run
    `dbt build --select silver_ibge_pevs+ --full-refresh` (dev **and** prod) when
    applying this change, otherwise the old partitions are left with the new
    columns null.

### Fixed
- **COMTRADE: resume now identifies the reporter batch by content, not by
  positional index.** The raw object was named `<ano>_r<índice>`, where the index
  came from slicing `list_reporters()` in the order of the UN reference JSON — if
  the UN reordered/changed the reporter set between runs, the same index would map
  to different reporters and resume silently skipped a batch whose composition had
  changed, leaving data never ingested. Now the reporters are **sorted** before
  batching and the basename is a **stable hash** of the batch's codes
  (`<ano>_r<hash>`), with `reporter_codes` recorded in the provenance.
  **Operation:** the first run after this change re-fetches the past years once
  (old basenames become orphaned; Silver dedupes).
- **COMEX/COMTRADE: the delta skip could leave a `(flow,year)`/batch
  permanently missing from Bronze.** When the raw was current, Phase 2 was skipped
  assuming "raw present ⇒ Bronze loaded" — false if a previous run archived the raw
  and aborted before the load. Now a `bronze_loaded_at` marker in the raw object's
  metadata (written after Phase 2; cleared automatically on a re-extract) is the
  source of truth: the skip happens only when the raw is current **and** has
  already been loaded.
- **BCB: the raw basename/provenance reflect the window actually archived.**
  In delta mode each series fetches only its recent overlap window, but the raw
  object was labeled with the configured `bcb_start_year` (e.g. "1980-2026") — a
  window the object does not contain. Now the label derives from the actual range
  of years in the data (`min`/`max` of `reference_date_str`).
- **`pyproject.toml`: license corrected from `MIT` to `Apache-2.0`** (the
  `LICENSE` file and all the other docs were already Apache 2.0); description
  updated to include COMEX/COMTRADE.
- **COMTRADE: ~2.5× double-counting in the Gold values/quantities.** The keyed API
  returns, per `(reporter, partner, cmd, flow)`, a **fully aggregated** record
  (`motCode=0`/`customsCode=C00`/`partner2Code=0`/`mosCode=0`) **plus** breakdown
  rows by transport mode / customs / 2nd partner — whose value **sums into the
  aggregate**. Silver kept everything and Gold summed it all together. Fixed by
  keeping only the aggregated record in `silver_comtrade_flows` (lossless: 546,812
  groups = 546,812 rows; Bronze untouched, no re-ingest). Total COMTRADE
  US$1,779bn → US$692bn; the COMEX↔COMTRADE mirror now matches.
- **COMTRADE: wrong physical unit families.** The `comtrade_unit` seed used a
  legacy qtyUnitCode table that does not match the API's codes. Validated against
  the HS6 `standardUnitAbbr`: **5=number of items (count)**, **8=kg
  (mass)**, **12=m³ (volume)** — previously ~24% of rows fell into the wrong family.
- **BCB FX series corrected (affected PEVS and COMEX).** The configured series
  were wrong: `3694` (USD) is **annual** — insufficient for COMEX's monthly
  deflation (it only filled Januaries); `4393` (EUR) returned ~127 and `20542`
  (CNY) ~4 million — **these are not BRL/unit quotes**. Swapped for PTAX **daily
  sell**: `1`=USD, `21619`=EUR (Gold averages by year/month). **CNY was removed** —
  the BCB does not publish BRL/CNY (nor USD/CNY) in the SGS or PTAX; a yuan column
  would require an external source (follow-up). This fixes
  `val_yearfx_{brl,usd,eur}` and `val_real_*_{brl,usd,eur}` in
  `gold_pevs_production` **and** `gold_comex_flows`.
- **`bcb/client`: SGS HTTP 404 treated as a window with no data**, not an error —
  series have different start dates (USD 1984, EUR 1999), so the `--full`
  year-chunking queries windows that predate some series. Previously, a `--full`
  from `BCB_START_YEAR` broke with a 404 on the first empty window.

### Added
- **COMEX reference dimensions — readable labels on `gold_comex_flows`.**
  Three seeds from the MDIC auxiliary tables (`bd/tabelas/`): `comex_unit`
  (`NCM_UNIDADE.csv` → statistical unit, e.g. `16`=METRO CUBICO, `10`=
  QUILOGRAMA LIQUIDO), `comex_country` (`PAIS.csv` → ISO-3 + PT name) and
  `comex_ncm` (`NCM.csv`, filtered for nuts `0801*` + ch. 44 → PT description).
  `gold_comex_flows` gains readable columns via `ref()`: `ncm_description`,
  `country_name`/`country_iso_a3`, `stat_unit`/`stat_unit_symbol` — 100%
  coverage of the current data. Clarifies the quantity semantics: `net_weight_kg`
  is always kg (comparable across products); `statistical_quantity` is in the NCM
  unit (m³ for most wood, kg for nuts) — do not sum across different units.

### Changed
- **Two-phase ingestion with a `raw/` zone — standardized across ALL sources.**
  Every source now follows **extract→raw→bronze**: Phase 1 archives the extract
  *verbatim* in GCS (`raw/<source>/<dataset>/<basename>.parquet`, with provenance
  metadata — URL, ETag/Last-Modified, `fetched_at`, `rows`); Phase 2 reads the
  raw back, filters/shapes it and loads Bronze. Re-filtering, changing
  products/rules or re-deriving Bronze **does not hit the source again** — only a
  real data revision triggers a re-fetch. New primitive `core/raw.py`
  (`land_raw`/`land_raw_file`/`read_raw`/`download_raw`/`list_raw`/`raw_provenance`)
  + `GCS_RAW_PREFIX`.
  - **COMEX:** Phase 1 downloads the full CSV→Parquet (all NCMs) and re-downloads
    **only when the ETag changed** (catching revisions to any year, not just the
    current one); Phase 2 filters the raw via `iter_batches`. `--from-raw`
    re-filters with no internet.
  - **IBGE:** Phase 1 archives the SIDRA response; Phase 2 loads Bronze.
  - **BCB:** each delta window becomes a raw object stamped per run (an
    append-only trail); `--from-raw` rebuilds Bronze by re-reading the trail.
  - Every `embrapa ingest <source>` gains `--from-raw`. The dead primitive
    `core/bronze.land_and_load` was removed (all sources use the new flow).
    Plan: `PLANS/raw_zone_architecture.md`. dbt/Silver/Gold unchanged.

### Added
- **COMEX source (MDIC Comex Stat) — complete Bronze→Silver→Gold pipeline.**
  A new *foreign trade* source (the first of the `flows` form —
  origin→destination), cross-referencing production × trade × FX × inflation of the
  same product. Scope: export **and** import, Brazil nut (NCM `08012100`/
  `08012200`) + the entire chapter 44 (wood/charcoal), at the month×NCM×country×UF
  grain.
  - **Bronze (`src/embrapa_dashboard/comex/`):** `client.py` bulk-downloads the
    annual CSVs from Comex Stat (`EXP_<ano>.csv`/`IMP_<ano>.csv`; `;`/latin-1)
    — *stream to disk* (100+ MB files), pandas parse in chunks, column-precise
    filter on `CO_NCM`/`CO_NCM[:2]`. EXP (11 cols) and IMP (13 cols: +
    `VL_FRETE`/`VL_SEGURO`) unified into a schema-union (export writes NULL in the
    two). It does **NOT** use the JSON API (which returned the aggregated Brazil
    total under a malformed filter, HTTP 200). `pipeline.py` has its own `run()`
    with delta by `(flow, year)` (re-fetches the current year, skips years already
    in Bronze). The command `embrapa ingest comex` is multi-chunk (events per
    `(flow, year)` in the monitor); registered in `cli.INGESTS`,
    `doctor.SOURCE_CHECKS` (`_check_comex`) and `doctor.BRONZE_TARGETS`. Config
    `COMEX_*` in `config.py`/`.env.example`.
  - **TLS:** the host `balanca.economia.gov.br` omits the intermediate CA from the
    handshake (`requests`/certifi fails; curl passes via AIA). The public
    intermediate (Sectigo R36) is vendored in `comex/_ca.py` and appended to the
    certifi bundle at runtime — **without disabling verification**.
  - **Silver/Gold (dbt):** `silver_comex_flows` (dedup at the full source grain);
    `gold_comex_flows` (ONE comprehensive `flows` table, grain
    flow×month×NCM×country×UF, aggregation via `GROUP BY` in queries). Applies the
    4 monetary conventions over `VL_FOB` (US$): `val_yearfx_*` at the month FX and
    `val_real_{ipca,igpm,igpdi}_*` (US$→BRL at the month FX → BCB index → today).
  - Coverage: `tests/test_comex_client.py` + `tests/test_comex_pipeline.py`;
    schema tests in `_silver.yml`/`_gold.yml`. Plan in
    `PLANS/comex_flows.md`.
- **Shared Bronze landing primitive (D4).** The identical tail of the Bronze
  pipelines (`ensure_bucket` → Parquet upload → `load_dataframe` with
  partition/cluster keys) was extracted into a source-agnostic primitive,
  analogous to D1 (`core/http.py`): each `run()` keeps only what is specific to the
  source. `ensure_dataset` is left out because the BCB needs the dataset *before*
  the extract (delta lookup). **Note:** this step evolved, still within this
  cycle, into the two-phase ingestion with a `raw/` zone — the final primitive is
  `core/raw.py` (see "Changed" above), not an intermediate
  `core/bronze.land_and_load` (introduced and removed within this same cycle).
  Observable behavior preserved; coverage in `tests/test_core_raw.py`.
- **`core/http.py` — shared HTTP primitives (D1).** A new factory
  `http_retry_policy(transient_exc, deadline_s, max_attempts=5, before_sleep=None)`
  and helper `get_drained(url, *, total_deadline_s, transient_exc, context, ...)`
  encapsulate the tenacity retry policy and the manual body drain under a
  wall-clock deadline (slow-byte defense) that were previously duplicated in the
  IBGE and BCB clients. Shared constants: `DEFAULT_TIMEOUT`, `DEFAULT_HEADERS`,
  `RETRYABLE_STATUS_CODES`. Observable behavior preserved byte for byte —
  source-specific deadlines (75s/180s in IBGE, 60s/120s in BCB) remain in the
  clients; unique defensive logic (IBGE period-halving, BCB year-chunking) also
  did not migrate. Coverage: 11 new tests in
  `tests/test_core_http.py` (including the slow-byte deadline test migrated from
  `test_ibge_client.py`) + 2 "delegate" tests asserting the kwargs passed to
  `get_drained` in each client.
- **Retry observability in the BCB client (D1.1).** `_fetch_window` now wires a
  `before_sleep=_emit_retry` hook into the tenacity policy, symmetric to IBGE —
  SGS series retries now emit a `retry` event
  (`series`, `window`, `attempt`, `reason`) that shows up in `embrapa monitor`.
  Unlike IBGE (which uses a contextvar because the UF lives one frame up), the
  `(code, window)` context comes directly from `retry_state.args`, since
  `_fetch_window` is itself the retried function. Coverage: a test of the hook's
  logic + a regression guard on the wiring (`before_sleep`).

### Changed
- **BCB inflation/currency pipelines collapsed into `bcb/series.py`.** The two
  pipelines were ~90% identical (`_extract`, `_effective_start_year`, `run`);
  they now share a generic SGS series pipeline parameterized by a
  `BcbSeriesSpec` (`kind`, `label_column`, `series_map`, `table`, `schema`, and the
  only genuinely source-specific line — `overlap_start_year(last) -> int`).
  `bcb/inflation.py` and `bcb/currency.py` became thin shims defining their spec
  and delegating. Public entry points (`inflation.run`/`currency.run`),
  constants (`DELTA_OVERLAP_MONTHS`, `BRONZE_SCHEMA`) and observable behavior
  preserved. **Deliberately reverts** the old note in
  `docs/adding_a_data_source.md` ("do not extract `_effective_start_year`"):
  on closer inspection, the difference was one line, today a `Callable` knob. The
  doc was updated to steer SGS series toward the spec, and differently-shaped
  sources toward writing their own `run()`. Tests consolidated: the duplication
  of the two test files became a single `tests/test_bcb_series.py` parameterized
  over the two specs + two thin per-variant files (the spec contract).
- **Gold renamed `gold_commodity_matrix` → `gold_pevs_production`**, adopting the
  `gold_<source>_<form>` convention (`production` for output measurement like PEVS;
  `flows` for origin→destination flow in future trade databases). Reinforces the
  rule of **one comprehensive Gold table per source** (ad-hoc aggregation at
  query time; pre-aggregated marts live in the `serving/` layer — see the
  Pushdown Computing item above).
  **External action required:** repoint the Looker Studio source to
  `gold.gold_pevs_production` and drop the orphaned `gold.gold_commodity_matrix`
  table in prod after the next `make dbt-build-prod` (see `docs/migration_history.md`).

### Fixed
<!-- Bug fixes -->

### Removed
- **Dash + Plotly UI layer removed (2026-05-29).** The frontend is being
  rebuilt with the Claude Design System in a separate flow. The following were
  deleted: the `src/embrapa_dashboard/dashboard/` package, the
  `tests/test_dashboard_*` tests, the scripts `scripts/dashboard_*` /
  `scripts/check_dashboard_size.py` / `scripts/dashboard-*.ps1`, the
  `Dockerfile`, the workflow `.github/workflows/dashboard-smoke.yml`, the
  `docs/auth.md` and the Claude Code skills `run-dashboard`,
  `dash-page-scaffold`, `new-chart-component`, `deploy-cloud-run`. The `dashboard`
  and `visual` extras in `pyproject.toml`, the `check-dashboard-size` hook
  in `.pre-commit-config.yaml`, the `--extra dashboard` in `ci.yml` and the
  `dashboard-*` / `test-smoke` targets in the `Makefile` were also removed.
  The backend (Medallion pipeline + dbt + `embrapa` CLI) remains 100%
  functional. The next handoff will join the new design system with
  this backend.

---

## [0.1.0] — 2026-05-26

> Initial release — functional end-to-end Medallion pipeline.

### Added

- **IBGE PEVS ingestion pipeline** via the SIDRA API with support for multiple products and periods.
- **BCB ingestion pipeline** (IPCA/IGP-M/IGP-DI inflation + USD/EUR/CNY FX) via the SGS API.
- **Delta ingestion** for the BCB — only new data is fetched by default.
- **Chunked ingestion** (`ibge-batch --chunk-years`) for large historical windows.
- **Silver layer (dbt)**: typing, dedup, IPCA chain index.
- **Seed `historical_currency_factors`**: absorbs Brazilian currency reforms (1942–1994).
- **Gold layer (dbt)**: `gold_commodity_matrix` table with 22 denormalized columns.
- **Aggregated Gold tables**: `gold_commodity_state_year`, `gold_commodity_year_product`.
- **Unified CLI** with Typer: `embrapa ingest|discover|dbt|doctor|backup-gold`.
- **Web dashboard** with Dash + Plotly (multi-page), deployed via Cloud Run.
- **Multi-stage Dockerfile** with a slim, non-root image, Gunicorn.
- **Service Account Impersonation** (OAuth 2.0) — no distributed keyfiles.
- **Four Service Accounts** with separation of responsibilities (reader, pipeline, dashboard, AI).
- **Gold backup → GCS** (`embrapa backup-gold`, `make dbt-build-prod-with-backup`).
- **`embrapa doctor`**: environment health diagnostics.
- **dev/prod separation** in the dbt schemas with auto-expiration of dev tables (7 days).
- **CI/CD**: GitHub Actions with lint (Ruff), test (pytest), dbt parse.
- **Pre-commit hooks**: gitleaks, ruff, file-hygiene, dashboard size ceiling (500 LOC).
- **Smoke test** of the dashboard with real BQ.
- **Visual check** with Playwright (headless screenshots → `artifacts/`).
- **Cross-platform automated setup**: `setup.sh`, `setup.bat`, `setup.ps1`.
- **Complete documentation**: setup, IAM, auth, cost safety, ownership transfer, testing.

---

<!-- Template for new versions:

## [X.Y.Z] — YYYY-MM-DD

### Added
### Changed
### Fixed
### Removed
### Security
### Deprecated

-->
