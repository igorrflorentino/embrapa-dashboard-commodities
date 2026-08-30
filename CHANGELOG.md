# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [1.46.8] - 2026-08-30

### Corrigido

- **`CLAUDE.md` e `ARCHITECTURE.md` descreviam o gate de visibilidade pela chave antiga.**
  A v1.46.5 acrescentou `sidra_tabela` à `dim_produto_visibility` e ao predicado que a
  consome, e atualizou o spec em `PLANS/` no mesmo PR — mas os dois arquivos que **semeiam
  o contexto de toda sessão futura** ficaram dizendo `(source, code)` por duas versões.
  Uma linha errada no `CLAUDE.md` não fica parada: ela se propaga para decisões.

  Duas afirmações, ambas falsas desde a v1.46.5:

  - a chave da view (`(source, code)` → `(source, code, sidra_tabela)`, nos dois arquivos);
  - **"NO-OP until something is hidden"** — o gate filtra 3 códigos comex, 6.688 linhas de
    Gold (medido 2026-08-30). Era no-op nas primeiras releases, e a documentação continuou
    dizendo isso muito depois de deixar de ser verdade.

  O verbete do `CLAUDE.md` passa a registrar também o que a v1.46.5 decidiu e não estava
  em lugar nenhum de topo: o casamento da tabela nos bancos multi-tabela, o **coringa** de
  uma linha sem tabela, e por que os dois lados renomeiam a coluna do gate para
  `_vis_sidra_tabela` (sem isso, um `sidra_tabela` sem qualificação resolve para o escopo
  interno do `NOT EXISTS` e a comparação vira tautologia).

### Adicionado

- `tests/test_docs_visibility_gate_key.py` — a chave que a documentação descreve tem de
  bater com a que o dbt impõe. A âncora é o `unique_combination_of_columns` do próprio
  modelo em `_core.yml`, mantido para impor o grão da view e não para este teste. Segue o
  padrão de `test_claude_md_ingest_batch.py`, que guarda outra afirmação do `CLAUDE.md`
  contra o registro que a decide.

  Vem com o irmão que guarda o varredor (`test_o_extrator_enxerga_a_chave`): um extrator
  que devolvesse lista vazia faria a asserção de substring passar para sempre — o modo de
  falha que este repositório já viu cinco vezes em varreduras minhas. Validado por três
  injeções: a doc voltar à chave antiga, o dbt mudar a chave sem a doc acompanhar, e o
  extrator ficar cego; cada uma reprova o teste certo.

---

## [1.46.7] - 2026-08-30

### Corrigido (documentação que mandava o operador atrás de ação impossível)

Contexto: a build completa de prod fecha em `PASS=369 WARN=4 ERROR=0` — e os relatórios
desta série vinham citando só `ERROR=0`. Os quatro avisos foram investigados contra prod.
Nenhum indica defeito, e as duas linhas do PAM (área plantada < colhida) conferem por
IDENTIDADE com as duas documentadas: 1990 Manaus/Mandioca e 1993 Goiás/Cana — a contagem
bater com 2 seria compatível com uma ter sumido e outra nova ter aparecido. Os outros dois
tinham texto errado:

- **`meso_code` / `micro_code` do mesh municipal** (`seeds/_seeds.yml`). O comentário dizia
  que o aviso existia "for a seed refresh". Nenhum refresh resolve: meso/micro são a
  divisão **congelada de 1990**, que o IBGE substituiu em 2017 pelas regiões
  intermediária/imediata, e um município criado depois disso nunca as recebe. Vale para
  exatamente UM município (medido 2026-08-30): `5101837 · Boa Esperança do Norte (MT)` —
  que tem `intermediaria_code=5103` e `imediata_code=510008`, ou seja, **é** plenamente
  filtrável nos níveis modernos. O comentário passa a separar os dois pares: meso/micro é
  permanente por natureza, intermediária/imediata é a divisão viva e um nulo lá seria
  acionável de verdade. Registra também a forma estrita (avisar sobre meso/micro só quando
  intermediária/imediata também forem nulas), NÃO aplicada — mudaria o comportamento do
  teste, não só o texto.

- **`assert_unconvertible_quantities_for_curation`**. O comentário listava duas causas,
  "ambas precisando de ação humana", e encaminhava o operador a `unit_family_conversions`.
  A causa que realmente dispara é uma **terceira**: `unit_native` **nula** — a fonte
  informou um número de quantidade e nenhuma unidade. Não é unidade não mapeada, é unidade
  ausente; nenhuma tabela de conversão resolve, e inventar uma seria inventar o dado. São
  871 linhas de `gold_comtrade_flows` (0,04% do banco), e o tratamento atual já é o certo
  (`qty_base` nulo, então nunca entram num agregado). O comentário agora traz as três
  causas e diz como separá-las na leitura do resultado.

Só comentários — nenhum teste, modelo ou seed muda de comportamento.

### Notas

- Uma varredura anterior desta sessão relatou "2 testes `severity: warn`, nenhum
  disparando". Ela olhou apenas `dbt/models` e passou ao largo de `dbt/seeds/` e do
  `{{ config(severity=\'warn\') }}` embutido nos `.sql` de `dbt/tests/`. **São 12
  configurados, 4 disparando.**
- Verificações que vieram limpas na mesma passagem: o Cloud Run serve a imagem `653a7e4`,
  idêntica ao HEAD de `main` (revisão criada 80 s após o merge), e `embrapa
  reconcile-check` conferiu **19.658 pontos com zero divergências** — nenhuma revisão a
  montante escapou da janela delta.

---

## [1.46.6] - 2026-08-30

### Modificado

- **O mapeamento banco↔fonte estava escrito à mão quatro vezes; agora é uma só, e as outras
  derivam.** Os 5 pares (`pevs`↔`ibge_pevs`, …) viviam em `curation._BANCO_TO_SOURCE`,
  `curation._SOURCE_PARA_BANCO`, `gateway._SHORT_SOURCE` e
  `seam_curation._BANCO_TO_SOURCE` — três módulos, as duas direções, e **duas delas com o
  mesmo nome em módulos diferentes**, o que faz de um import errado um valor plausível em
  vez de um `ImportError`. Nenhum teste guardava uma contra a outra; o que segurava a
  consistência era um comentário pedindo que se lembrasse das outras.

  Concordavam (medido em 2026-08-30), então era **latente, não vivo** — a mesma forma do
  achado da v1.46.5. O gatilho, porém, é datado: **SEFAZ NFe está `Planejado`**, e um sexto
  banco significa acertar quatro lugares. Errar um falha em silêncio, num caminho diferente
  daquele que a pessoa está testando.

  `serving/sql.BANCO_TO_SOURCE` passa a ser a fonte única, com `SOURCE_TO_BANCO` derivada
  por inversão — uma bijeção escrita duas vezes à mão é duas vezes a chance de errar, e o
  erro só apareceria no sentido que ninguém testa. As quatro referências antigas viraram
  aliases: são **o mesmo objeto**, então divergir deixou de ser possível em vez de apenas
  testado. Ambas são `MappingProxyType`, porque um dict compartilhado por três módulos que
  alguém mute num deles muda em todos.

  `sql.py` já hospedava esse tipo de vocabulário (`SEM_TABELA`, `CHAVE_*`) pela razão
  idêntica registrada no comentário de lá: *"eram 16 `partition by` espalhados por 5
  módulos, e uma chave que muda em 15 lugares e fica no 16º é a forma exata do defeito que
  este projeto já teve três vezes"*.

  Sem mudança de comportamento, medido: os quatro leitores diretos de Gold devolvem
  exatamente os mesmos números de antes (pevs 76/10/114/31 · ppm 89/14/142/27), e o
  predicado de visibilidade compõe igual.

### Adicionado

- `test_the_banco_vocabulary_is_written_by_hand_exactly_once` — varredura por AST de `src/`
  inteiro, afirmando **exatamente uma** cópia à mão. O número exato, e não um teto, é
  deliberado: um extrator quebrado que devolvesse zero faria uma asserção de teto passar
  para sempre. Ele cobrou isso duas vezes durante a própria escrita — o extrator não
  reconhecia o wrapper `MappingProxyType`, e depois não reconhecia a anotação de tipo
  (`AnnAssign`). A mensagem de falha distingue as duas causas possíveis de "zero cópias",
  que pedem correções opostas.
- `test_the_banco_vocabulary_is_a_bijection_and_covers_every_known_banco` — id longo
  repetido (o erro clássico de copiar-e-colar ao acrescentar o sexto banco) e cobertura
  contra âncoras mantidas por outros motivos: `_BANCOS_MULTI_TABELA`,
  `_tabelas_validas_por_banco` e as chaves de `gateway._GOLD_TABLE` (toda fonte roteável
  precisa de token curto, senão o gate levanta `KeyError` no meio de uma leitura de Gold).

  Validados por injeção: restaurar a cópia do gateway, duplicar um id longo e remover um
  banco reprovam os testes certos.

---

## [1.46.5] - 2026-08-30

### Corrigido

- **O gate de visibilidade escondia as DUAS metades de um produto multi-tabela.** A view
  `dim_produto_visibility` é única em `(source, code, sidra_tabela)`, mas o predicado que a
  consome casava só `source` e `code` — nos dois lados que precisam concordar, a macro
  `hidden_code_predicate` e o espelho `serving/sql.visibility_clause`. A identidade de um
  produto é `(banco, tabela, código)`: marcar a metade extração (289) como indisponível
  tinha de deixar a metade silvicultura (291) visível, e escondia as duas. Era **latente** —
  os códigos das duas tabelas são disjuntos hoje, então o caso nunca chegou a ocorrer — e
  foi registrado como achado na v1.46.4, com o check `Shared code across SIDRA tables`
  avisando no instante em que deixasse de ser.

  Uma linha do gate **sem tabela é coringa** (esconde as duas metades): `sidra_tabela` é
  opcional numa entrada de PEVS, e uma tag ausente tem de continuar escondendo tudo. Sem
  essa regra a correção seria *fail-open* — um produto escondido reapareceria.

  **A armadilha que quase entrou junto.** Dentro do `NOT EXISTS`, um `sidra_tabela` sem
  qualificação resolve para o escopo **interno**: `v.sidra_tabela = sidra_tabela` vira
  tautologia e volta a esconder as duas metades, com aparência de correto. Medido contra o
  BigQuery antes de escrever a correção — a forma ingênua fez a metade 291 desaparecer
  junto. Os dois lados expõem a coluna do gate como `_vis_sidra_tabela`, e o nome
  `sidra_tabela` deixa de existir no escopo interno.

  **Comportamento de hoje inalterado, medido linha a linha** nos cinco bancos contra o Gold
  de prod: pevs 1.351.477 · ppm 3.538.360 · pam 2.516.602 · comex 382.959 de 389.647 ·
  comtrade 2.053.708 — idêntico ao predicado anterior. O comex não é vácuo: os 3 códigos
  escondidos filtram 6.688 linhas, e o novo predicado filtra exatamente as mesmas.

### Adicionado

- **Dois testes unitários dbt** (`_gold.yml`, sobre `gold_source_metadata`) que executam o
  SQL de verdade no BigQuery — é lá que a armadilha tinha de ser guardada, porque quem
  decide a resolução de nome é o BigQuery, não a leitura que eu faço dela. Um prova que
  esconder a metade 289 deixa a 291 visível; o outro, que uma linha sem tabela esconde as
  duas. Validados por injeção: remover o rename reprova o primeiro, remover o coringa
  reprova o segundo.
- Macro `bancos_multi_tabela()` — a lista de bancos com duas tabelas SIDRA, do lado dbt,
  com `test_the_multi_table_banco_list_agrees_between_dbt_and_python` guardando a sincronia
  com `serving.curation._BANCOS_MULTI_TABELA`.
- `test_visibility_clause_renames_the_gate_column_to_avoid_the_shadowing_tautology` — a
  condição estrutural no espelho Python, que nenhum teste dbt alcança.

### Corrigido (documentação atrasada em relação aos dados)

- `dim_produto_visibility` **não declarava a coluna `sidra_tabela`** no `_core.yml`, embora
  a view a selecione e o teste de unicidade a referencie — o que bloqueava qualquer fixture
  de teste unitário sobre ela.
- Três afirmações de que o gate está vazio / é um "no-op steady state" (`_core.yml`, o
  cabeçalho da view, e `PLANS/quality_outliers_and_visibility_gate.md` em dois pontos).
  Prod tem 3 códigos comex escondidos, filtrando 6.688 linhas de Gold.

---

## [1.46.4] - 2026-08-30

### Corrigido

- **O guarda do invariante desta migração estava morto, e reportava verde.** O check
  `Shared code across SIDRA tables` do `embrapa doctor` — que pergunta se um código existe
  nas DUAS tabelas SIDRA de um banco — consultava a coluna `origem`, removida do Gold na
  v1.46.1. O BigQuery devolvia `400 Unrecognized name`, o `except Exception` engolia, e o
  doctor imprimia `✓ Shared code across SIDRA tables │ skipped: 400 Unrecognized name`.
  Ficou assim por três versões: o guarda do invariante da própria migração, cegado por ela.
  Num relatório de 27 ✓, um `skipped:` não se lê.

  Três defeitos empilhados, todos corrigidos:

  - **A consulta.** O discriminador deixou de ser um campo por banco (`origem` para o PEVS,
    `measure_kind` para o PPM — prosa nos dois casos) e passou a ser a constante
    `_COLUNA_DISCRIMINADORA = "sidra_tabela"`. A identidade de um produto é
    `(banco, tabela, código)`; um campo por banco tornava representável exatamente o erro
    que a v1.46.x foi corrigir. Como o `try` envolvia o laço inteiro e o PEVS vinha
    primeiro, **as duas metades do check estavam mortas**, não só a dele.
  - **A política de degradação, nos SEIS checks que a usavam.** `_skip_ou_quebra` separa o
    que o `except Exception` confundia: ausência de dado (`NotFound`, `Forbidden`, sem ADC,
    credencial expirada) continua verde com `skipped:`; qualquer outra exceção — consulta
    que não compila, `TypeError`, `KeyError` — vira **vermelho** com `CHECK QUEBRADO` e o
    nome do tipo. Vale também para os checks *advisory*: "advisory" governa o que o check
    faz quando *consegue* julgar.
  - **O teste que devia ter pego.** `test_shared_code_query_groups_by_the_discriminator`
    percorria `_BANCOS_MULTI_TABELA` e afirmava que o SQL continha o discriminador tirado
    *dessa mesma constante* — uma tautologia que passava verde com qualquer nome, inclusive
    um inexistente. A âncora agora é externa ao doctor: o próprio `.sql` do modelo Gold,
    mantido pelo pipeline e não pelo teste, com os comentários removidos antes da busca
    (a palavra `origem` sobrevive na prosa de vários modelos e um grep cru passaria).

- **`IBGE silvicultura variable codes`** nomeava `origem='silvicultura'` na mensagem de
  falha — texto que um operador lê justamente no momento de confusão. Agora diz
  `sidra_tabela='291' (silvicultura)`.

### Adicionado

- **Varredura por AST contra o atalho voltar.** `test_no_check_returns_a_literal_green_from_a_broad_except`
  percorre o módulo inteiro e reprova qualquer `CheckResult(..., True, ...)` devolvido de
  dentro de um `except Exception`. Um check NOVO com o mesmo atalho falha no CI em vez de
  morrer em silêncio. Verde vindo de um `except` **estreito** continua permitido — o check
  `GCS bucket` responde `except NotFound` com um veredito real ("será criado na primeira
  ingestão"), que é julgar, não engolir.
- Seção **"Um ✓ verde do `doctor` que diz `skipped:`"** no runbook de operações,
  explicando as duas cores e por que a distinção existe.

### Notas

- **Achado latente, não corrigido aqui** (registrado na docstring do check e apontado pela
  sua mensagem de falha): a view `dim_produto_visibility` é única em
  `(source, code, sidra_tabela)`, mas o predicado que a consome casa só `source` e `code` —
  nos dois lados, a macro `hidden_code_predicate` e o espelho Python
  `serving/sql.visibility_clause`. Se um dia um código existir nas duas tabelas de um banco,
  esconder uma metade esconderá as duas, sem aviso. Hoje é inofensivo (os códigos são
  disjuntos, medido em 2026-08-30) e o check agora avisa no instante em que deixar de ser.
  Fechar isso exige tratamento por banco — `comex`/`comtrade`/`pam` não têm `sidra_tabela` —
  e é decisão de escopo próprio.

---

## [1.46.3] - 2026-08-30

### Corrigido

- **Os dois últimos gráficos que confundiam as duas metades do PEVS.** A varredura que
  encontrou o defeito nos rankings por UF e por município (v1.46.1) apontou mais dois
  pontos, que ficaram abertos:

  - **Donut "Participação por produto"** (Visão geral, a tela mais visitada) — a legenda
    mostrava `Madeira em tora 57%` e `Madeira em tora 7%`, `Lenha 11%` e `Lenha 2%`. O
    Donut usa índice como chave, então não *fundia* as fatias como o gráfico de barras —
    mas o leitor não tinha como saber qual metade era qual, e "Carvão vegetal" aparecia
    uma vez só porque sua segunda metade caía em "Outros".
  - **Comparativo entre produtos** — a legenda, a tabela de métricas e o nome das séries.
    Alcançável sempre que se escolhem as duas metades do mesmo produto, o que o seletor de
    cesta permite. (A matriz de correlação da mesma tela já mostrava o **código** e por
    isso nunca teve o problema.)

  Faltava a `sidra_tabela` na lista de produtos do *snapshot*. Ela passa a viajar por lá
  seguindo o precedente que já existia no mesmo arquivo — `measure_kind` é selecionada só
  para o PPM —, e as duas telas usam o `labelProductRows` que já existia. O rótulo só
  ganha o sufixo quando o nome se repete no conjunto exibido.

---

## [1.46.2] - 2026-08-30

### Documentação

- **`CLAUDE.md` e `PLANS/silvicultura_source.md` descreviam a `origem` como o eixo que
  separa as duas metades do PEVS** — aposentada em v1.46.1. O CLAUDE.md passa a descrever
  `sidra_tabela` e a regra que a sustenta: a identidade de um produto é
  `(banco, tabela, código)`, então a tabela é uma COLUNA e todo nome humano de uma metade
  é DERIVADO dela, nunca guardado ao lado. O plano da silvicultura ganhou uma nota de
  superação no topo, mantendo o registro histórico intacto — o escopo da ingestão, o modelo
  de linhas e os critérios de aceite continuam valendo.

---

## [1.46.1] - 2026-08-30

Passo 2 de 2. Os consumidores passam a ler a **tabela SIDRA**, e a `origem` sai da Gold.
O passo anterior (v1.46.0) já pôs a coluna no dado, então este deploy não tem janela de
quebra: o que o código novo precisa já está em produção.

### Corrigido

- **Rótulos sobrepostos no gráfico "O que ‹lugar› produz"** (*Perfil do território*, e o
  mesmo gráfico em *Geografia*). Madeira em tora, lenha e carvão vegetal existem nas duas
  tabelas do PEVS com o **mesmo nome** e códigos diferentes (3457/3435, 3456/3434,
  3455/3433). O gráfico usa o nome como categoria do eixo e o Plotly funde categorias
  homônimas numa posição só: aparecia **uma** barra (a maior) com os **dois** rótulos
  impressos por cima um do outro. Em Minas Gerais, "Carvão vegetal" desenhava 115 bi e
  imprimia junto "14 bi" — daí o eixo ir a 121 bi com o rótulo dizendo 14.

  A desambiguação usa a **tabela**, que é o terceiro componente da identidade do produto,
  e só entra quando o nome se repete no conjunto exibido:

  | filtro | rótulos |
  |---|---|
  | Ambas | `Carvão vegetal · silvicultura`, `Carvão vegetal · extração`, `Açaí (fruto)` |
  | Silvicultura | `Carvão vegetal`, `Madeira em tora`, `Lenha` |

  O nome humano de cada tabela vem de **um registro só** (`SIDRA_TABELA_OPTIONS`), para
  não nascer um segundo vocabulário em outro arquivo.

### Alterado

- **`origem` foi aposentada.** O eixo agora é a tabela de ponta a ponta: coluna
  `sidra_tabela` na Gold, predicado `sidra_tabela = @sidra_tabela` no SQL, parâmetro de API
  `sidraTabela` (com allowlist **derivada** do `config.py`, não uma lista fixa), parâmetro
  de URL `tb`, e coluna `tabela_sidra` no CSV. O nome humano ("Extração vegetal (nativa)",
  "Silvicultura (plantada)") continua idêntico na tela — ele passou a ser derivado do id
  em vez de guardado ao lado dele.

- **Links antigos continuam funcionando.** O decodificador aceita o `or=extrativa|silvicultura`
  dos permalinks já compartilhados e o traduz para a tabela, lendo o mesmo registro que
  desenha o filtro — então renomear uma metade lá continua valendo aqui.

---

## [1.46.0] - 2026-08-30

Primeiro de dois passos: a **tabela SIDRA passa a viajar no dado**. Este PR só mexe em
dbt e não muda nenhum consumidor — a `origem` continua existindo e sendo lida como sempre.
A migração dos consumidores vem no passo seguinte.

### Adicionado

- **`sidra_tabela` na Gold e nas marts do PEVS e do PPM.** A identidade de um produto é
  `(banco, tabela, código)` — a mesma chave que o catálogo da curadoria usa desde v1.39.0
  —, mas o id da tabela nunca foi uma coluna: existia como **nome de tabela no Bronze**
  (`sidra_t289_raw`) e, na Gold, virava prosa carimbada na união
  (`select 'extrativa' as origem, …`). Quem exibia não alcançava a identidade.

  O carimbo agora é o **id**, lido das vars do dbt em paridade com o `config.py` (o mesmo
  padrão dos códigos de variável, que o `doctor` valida). No PPM ele entra no Silver, de
  onde `measure_kind` passa a ser **derivada** — ela continua existindo porque responde
  "esta linha tem preço?", que é o que cinco telas perguntam, e não "de onde veio".

### Alterado

- **`origem` virou coluna DERIVADA da tabela**, em vez de um segundo fato guardado ao
  lado. Nada muda para quem a lê: o filtro, o chip, a citação ABNT e o CSV seguem
  idênticos. Ela sai no PR seguinte, junto com a migração dos consumidores.

- **O join do catálogo em `serving_ppm_annual` passou a usar a chave inteira**
  `(source, código, tabela)`. Ele omitia a tabela e o próprio modelo documentava isso com
  um ⚠ como uma **suposição**, presa por `assert_catalog_join_cannot_fan_out.sql` — porque
  o Gold carregava um discriminador semântico e não o id. O teste dizia: *"se ele acender,
  o conserto é dar ao join a tabela"*. Foi o que se fez. No `serving_pam_annual` o
  comentário foi corrigido: ali nunca foi suposição — o PAM é banco de tabela única.

### Notas de operação

⚠ **Este build exige `--full-refresh`.** `silver_ibge_ppm` é incremental com
`on_schema_change='append_new_columns'`: um build normal acrescentaria a coluna mas só
preencheria as linhas NOVAS, deixando o histórico com NULL — e o join novo as descartaria
em silêncio.

---

## [1.45.0] - 2026-08-30

Auditoria completa do projeto (`docs/audits/full_audit_2026-08-30.md`) e a correção dos
quatro achados que ela levantou. Nenhum era **crítico** — os 64 módulos Python são grau A
de manutenibilidade e não há importação circular —, mas os dois primeiros ficam no caminho
de escrita do catálogo, onde uma regra duplicada já se escondeu uma vez.

### Alterado

- **`record_produto_catalog` saiu de complexidade E(38) para C(18).** Era a pior função do
  projeto, e o número não era acadêmico: ela guardava uma cópia literal da regra do
  `sidra_tabela`, e generalizar o validador compartilhado deixou toda escrita PEVS recusada
  com mensagem velha. Foram extraídos `_validate_agrupamento`,
  `_validate_group_registered` e `_preserve_omitted_fields` — este último nomeia a política
  de "preservar o que foi omitido" que a docstring já descrevia como uma regra só. O portão
  que **recusa** ficou de propósito no fluxo principal: uma recusa tem de ser legível onde
  a escrita acontece.

- **`record_group` saiu de D(24) para C(15)**, com `_validate_group_name` e
  `_validate_group_uniqueness`. O plano falava em reusar os predicados do item anterior; na
  inspeção isso estaria errado — um guarda os campos de uma **entrada** do catálogo, o
  outro a identidade do **registro** de grupos. Compartilham só o teto de caracteres, que
  já era a mesma constante.

### Adicionado

- **`tests/test_change_id_readback.py`** — 12 testes sobre as quatro funções que releem uma
  linha pelo `change_id`. São elas que fazem uma escrita repetida **ecoar** em vez de
  duplicar, e a auditoria mostrou que executavam em **zero** testes: todo teste que as
  alcança as substitui por um stub. Um nome de coluna errado no `SELECT` passaria a suíte
  inteira e falharia em produção, no caminho de retry, onde ninguém está olhando.
  `serving/attribute_engineering` foi de **86,93% para 96,08%**; o total do repositório, de
  99,06% para **99,31%**.

### Removido

- **A dimensão "Faixa de valor", de ponta a ponta.** `valueMin`/`valueMax` nunca eram
  escritos — nenhum controle de UI, nenhum deep link —, `VALUE_PRESETS` alimentava só
  `valueShareForRange`, que alimentava só um contador que sempre lia 1,00 dela, e
  `chipFmt.valueRange` formatava um campo que ninguém preenchia. Um laço fechado de código
  morto, do qual só a citação ABNT ainda declararia algo. Saíram junto quatro testes que
  afirmavam que uma constante valia 1,00 — guardavam código morto, não comportamento.

  A dimensão continua **documentada** em `filtersSchema` com `backed: false`, que é onde
  dizer "a fonte tem a coluna, o dashboard não filtra por ela" é honesto em vez de enganoso.

### Corrigido

- **Dois testes que guardavam o layout do arquivo, não a regra.** `test_chave_produto.py`
  procurava trechos do fonte **dentro de `record_produto_catalog`**; a extração acima moveu
  a lógica de casa e eles reprovaram com o comportamento intacto. Passaram a verificar
  comportamento (`_preserve_omitted_fields` devolvendo a tag guardada) e a varrer o módulo
  inteiro em vez de uma função. A varredura de texto também ganhou um instrumento melhor:
  filtrava só linhas iniciadas por `#` e deixava passar um literal dentro de um docstring —
  agora usa `tokenize`, que separa código de prosa de verdade.

---

## [1.44.1] - 2026-08-30

### Corrigido

- **O nome do arquivo CSV passa a trazer o período dos dados.** Saía
  `..._completo.csv` sempre que ninguém tinha mexido no filtro de período, ao lado de um
  chip dizendo "1986–2024". Era coerente ("completo" = sem recorte), mas a janela de
  confirmação passou a mostrar as duas coisas juntas, e juntas elas leem como contradição.
  Agora sai `ibge_pevs_serie_agregada_1986-2024.csv`.

  A fonte do período é a **coluna `ano` do próprio arquivo**, não o filtro: é a única que
  não pode discordar do conteúdo. A diferença aparece quando as duas divergem — filtro
  2005–2021 sobre dados que só cobrem 2020–2021 nomeia o arquivo `2020-2021`, porque
  nomeá-lo `2005-2021` prometeria uma cobertura que o arquivo não entrega. O filtro
  descreve a intenção; o arquivo é o que o pesquisador vai abrir seis meses depois.

  Um ano só não vira `2024-2024`. Um assunto sem coluna `ano` (qualidade) cai no período
  do filtro e, na falta dele, no chip da tela — com o travessão normalizado, que não é
  caractere para nome de arquivo. `completo` fica só para quando não existe fonte nenhuma.

- Removida a classe `util-action-export`, aplicada ao botão e sem regra de CSS
  correspondente — achada na varredura final de classes declaradas × usadas.

---

## [1.44.0] - 2026-08-30

### Adicionado

- **Confirmação antes de baixar o CSV.** O clique em "Exportar CSV" passa a abrir uma
  janela que mostra **o que vai ser baixado** antes de o navegador perguntar onde salvar:
  quantas linhas, quantas colunas e o tamanho do arquivo; o conteúdo em uma frase
  ("Série anual agregada", "Distribuição por município", …); o nome do arquivo; a lista
  exata das colunas — é ela que responde se vem `valor_BRL` ou `valor_USD` —; e o recorte
  e as convenções aplicados.

  A garantia que faz isso valer alguma coisa é estrutural: a janela é montada a partir do
  **mesmo objeto** que o "Baixar" grava. O exportador foi partido em `prepareTableCSV`
  (monta e devolve um descritor, com um `baixar()` que escreve a string **já pronta**) e
  `exportActiveTableCSV` (o caminho direto, sem confirmação, mantido). Se o download
  remontasse o arquivo, a tela poderia descrever uma coisa e gravar outra — exatamente o
  que a confirmação existe para impedir.

  Como efeito colateral, **"não há o que baixar" virou uma resposta em tela**. Antes um
  banco não liberado ou um recorte sem linhas produzia um `console.warn` e um botão que
  não fazia nada — invisível para quem usa. Agora a janela diz o motivo e o que fazer.

### Alterado

- **"Exportar CSV" saiu do meio do trio fixo e foi para o lado dele**, separado por um
  risquinho. O botão é condicional — some nas páginas de informação e nas views sem tabela
  —, então no meio do grupo ele empurrava "Enviar feedback" de lugar a cada troca de tela.
  Como `.util` é alinhado à direita, um item no **início** cresce para a esquerda: medido
  no navegador, "Citar painel", "Compartilhar" e "Enviar feedback" ficam em 1003, 1127 e
  1261 com ou sem o export — **zero deslocamento**. Mesma ordem no menu "⋯" do celular.

- **A lista de chips do recorte mudou-se para `scopeChips.js`** (`activeFilterChips`).
  Ela morava dentro do `FilterTriggerBar`, o que fazia da faixa o único lugar capaz de
  dizer qual é o recorte; a janela do CSV precisa dizer a mesma coisa, e duas cópias da
  regra é como duas superfícies passam a descrever uma seleção só de dois jeitos — a mesma
  razão pela qual `axisScopeChips` já vivia ali.

---

## [1.43.1] - 2026-08-30

### Corrigido

- **"Editar filtros" e "Editar métricas" passam a ter as mesmas dimensões.** A altura já
  era igual — a classe é compartilhada —, mas a largura vinha do texto: 122px contra 138px,
  medidos no navegador. Como os dois ficam no mesmo canto de dois blocos empilhados,
  larguras diferentes os faziam ler como dois controles distintos, quando são o mesmo
  controle de dois blocos. Um `min-width` na classe compartilhada iguala pelo maior, e
  agora eles alinham nos **dois** lados, formando uma coluna. "Recolher" (o mesmo botão no
  estado expandido das convenções) entra junto de propósito: sem isso o botão encolheria ao
  abrir o bloco. "Ver dimensões previstas" é naturalmente maior e não é afetado — vive
  sozinho na barra de preview, nunca lado a lado com os outros.

  O guarda possível em teste não é a medida (o jsdom não aplica CSS), e sim as duas coisas
  de que ela depende: que a regra seja **uma só** — se cada botão ganhar a sua, elas
  divergem em silêncio — e que o **conjunto de rótulos** seja o que foi medido, já que um
  valor em px não sabe o que o texto mede e um rótulo mais longo estouraria o `min-width`
  sem erro nenhum.

---

## [1.43.0] - 2026-08-30

### Alterado

- **As ações de "Filtros ativos" e "Convenções métricas" ficam fixas no canto superior
  direito do bloco.** Antes os chips e o botão eram irmãos numa mesma linha que quebrava,
  então o "Editar filtros" descia junto com o último chip: a posição dele dependia de
  **quantos chips o banco expõe** — dez no IBGE PEVS, quatro no UN COMTRADE — e mudava de
  perspectiva para perspectiva. Agora cada bloco tem duas áreas: informação à esquerda,
  que quebra, e ação à direita, que não. Medido no navegador: com 2, 3 e 6 linhas de
  chips e a faixa indo de 98px a 266px de altura, o botão fica a **17px da borda direita
  e 12px do topo** nos dois blocos. O "Recolher" do estado expandido das convenções ocupa
  o lugar exato do "Editar métricas", então abrir e fechar não move o botão.

- **"Exportar CSV" foi para o topbar, ao lado de "Compartilhar".** Ele era o único botão
  sólido de uma faixa cujo trabalho é *descrever* estado, não agir; e o escopo não batia —
  "Editar filtros" edita o bloco onde vive, enquanto o export é montado de
  `{view, banco, filtros, convenções}`, das quais o recorte é só uma parte. No topbar ele
  fica com "Citar painel" e "Compartilhar", que são a mesma família: os três levam o mesmo
  estado embora — como citação, como link e como arquivo —, e o "Compartilhar" codifica na
  URL exatamente as mesmas quatro entradas. Ganha posição fixa em todo o dashboard e entra
  no menu "⋮" do celular. O texto do "Sobre o dashboard" foi atualizado para dizer onde
  ele está.

### Corrigido

- **O "Exportar CSV" não aparece mais em páginas de informação.** Regressão introduzida
  ao movê-lo: a faixa de filtros só existia em views de dados, o que escondia o botão em
  "Sobre o dashboard", "Glossário" ou "Cadastro de produtos" sem ninguém precisar pensar
  nisso. No topbar, que é sempre visível, o gate passou a ser explícito — e **derivado**
  do `isDataView` já calculado uma vez em `main.jsx`, em vez de uma segunda cópia da regra
  que sairia de sincronia na primeira vez que a primeira mudasse.

---

## [1.42.0] - 2026-08-30

### Adicionado

- **Cada agrupamento agora abre e fecha.** A tela mostrava as 31 tabelas de uma vez —
  234 linhas, 702 `<select>` e 8.190 `<option>` montados no carregamento — quando quem
  chega aqui quer **um** produto. Os cartões nascem recolhidos: o cartão fechado não
  renderiza a tabela, então o custo some junto com a poluição visual, em vez de ficar
  apenas escondido por CSS. Um botão **Expandir/Recolher todos** cobre o caso de quem
  quer a lista inteira. O nome do agrupamento inteiro é o alvo de clique (não só a
  setinha); Renomear e Excluir ficam fora dele, senão recolheriam o cartão junto — é
  por isso que não é um `<details>/<summary>`.

- **Busca por código ou descrição**, no topo da lista. Responde a pergunta "esse produto
  já está cadastrado?" sem obrigar a percorrer 31 agrupamentos. Procura no código, nas
  duas descrições (a da fonte e a anotação do pesquisador), no banco e no agrupamento;
  todos os termos precisam bater, então `arroz 1006` funciona. Dobra acento, caixa e
  pontuação — `castanha do para` acha *Castanha do Pará*, e `castanha-do-pará` também.
  Durante a busca os resultados ficam sempre visíveis (um acerto escondido atrás de um
  toggle é o mesmo que nenhum acerto), e o cabeçalho diz quantos bateram de quantos há
  (`Arroz (5 de 15)`). Uma busca sem resultado **diz** que não achou: "0 produtos"
  responde "não está cadastrado", coisa que uma área em branco não responde.

### Alterado

- **A coluna `Tabela` mostra o código da tabela SIDRA (`289`, `291`, `3939`, `74`), não
  o nome por extenso.** É o identificador que a fonte usa e que aparece na URL do SIDRA,
  e lido junto com a coluna vizinha forma a chave do produto. Passa a usar a mesma fonte,
  cor e tamanho do resto da tabela em vez de um selo colorido: o selo dizia "isto é outra
  coisa", quando é apenas mais um pedaço da identidade. O nome por extenso vira `title`,
  e o seletor do formulário passa a mostrar `289 — Extração vegetal`, para ninguém
  precisar decorar a correspondência.

- **Larguras das colunas refeitas** sobre a medição nova. `Tabela` caiu de 105px para
  62px ao trocar o nome pelo código, e essa folga foi para *Descrição (fonte)*, que subiu
  de 160px para 201px — a única coluna de prosa. As necessidades somam 1024px contra
  1089px disponíveis.

---

## [1.41.1] - 2026-08-30

### Corrigido

- **As 11 colunas do Cadastro cabem, e todos os cartões usam a mesma grade.** Com a
  coluna `Tabela` a mais, faltava largura: o cabeçalho quebrava no meio das palavras
  (`Ingestã/o`), o pill de status virava `OCULT/O` e números partiam em `251.7/77`.
  Cada largura agora é uma necessidade **medida** — a maior string que a coluna precisa
  renderizar numa linha, mais o padding — e não um palpite. O conteúdo real pede 884px;
  o resto era padding, então 20px por coluna viraram 16px (devolve 44px) e a tela do
  Cadastro recupera 40px de recuo lateral do `.content` e do `.card`. Sobra vai toda
  para *Descrição (fonte)*, a única coluna de prosa.

- **A barra de rolagem vertical desalinhava os cartões maiores.** O `max-height: 640px`
  do `.dt-wrap` só disparava nos grupos com muitas linhas, e a barra roubava 15px **deles**:
  7 dos 31 cartões mediam 1074px contra 1089px dos outros. Isso anulava justamente o que o
  `table-layout: fixed` existe para garantir — a mesma grade em todos os cartões — e era a
  razão de `Ingestã/o` e `OCULT/O` quebrarem só ali. Sem o scroll interno, os 31 cartões
  medem 1089px. A página inteira já rolava.

- **Quebra no meio da palavra onde não havia palavra longa.** `overflow-wrap: anywhere`
  estava em todas as células, para a Descrição poder quebrar; era ele que partia número,
  sigla e rótulo. Agora vale só na coluna de prosa. Em 1280px — onde a tabela ainda
  comprime, comportamento que já existia — a quebra no meio da palavra passou de dezenas
  de células a **zero**: o que não tem espaço nem hífen vaza alguns pixels em vez de virar
  duas sílabas.

### Notas de medição

Três instrumentos deram resultado errado antes do repositório estar errado, e a correção
de cada um mudou a conta: `measureText` do canvas **ignora `letter-spacing`** (subestimava
todo piso); um `<select>` foi medido pela opção mais longa do **menu**, que abre em popup
com largura própria, quando só o valor **selecionado** precisa caber; e `scrollWidth` não
enxerga déficit **já absorvido por uma quebra** — devolvia exatamente a largura alocada,
isto é, lia de volta a própria conta. A medição que vale usa uma cópia da tabela sem
larguras impostas. `ccTableWidths.test.js` ganhou a âncora que faltava: uma largura por
`<th>` do cabeçalho, contado no **JSX** — o arquivo que muda quando alguém acrescenta uma
coluna e esquece o CSS.

---

## [1.41.0] - 2026-08-30

### Adicionado

- **Coluna `Tabela` no Cadastro de produtos.** A identidade de um produto é
  `banco + tabela + código`, e um terço dela estava escondido dentro de outro terço — um
  selo dentro da célula do banco. Agora o trio lê da esquerda para a direita em colunas
  próprias. Bancos de uma tabela só mostram travessão: a coluna não some, senão o leitor
  não sabe se aquele banco não tem tabela ou se a tela deixou de mostrar.

  Verificado no navegador: os quatro rótulos renderizam (*Extração vegetal*, *Silvicultura*,
  *Rebanho (efetivo)*, *Produção animal*), **24 linhas com selo e 210 com travessão** —
  soma 234, que é o total do catálogo. No empilhado do celular a coluna vira linha rotulada
  entre o banco e o código.

### Corrigido

- **A coluna nova desalinhou todas as larguras.** Elas são posicionais (`nth-child`), então
  inserir uma desloca as seguintes: "Código" herdou os 16% de "Descrição" e "Exibição" caiu
  para **42px**, com o cabeçalho quebrando em "Ex/ib/iç/ão" e a tabela transbordando 35px
  dentro de um wrapper que **corta** em vez de rolar. Redistribuídas para onze colunas;
  transbordo agora é 4px de arredondamento.
- **A `key` do React era `banco + código`** — sem a tabela, duas metades de um código
  compartilhado colidiriam e o React reusaria a linha errada.
- Duas frases que descreviam a chave com dois campos: a introdução da tela e o verbete
  "Banco" da legenda.

### Verificação

`frontend/src/ui/ccTableWidths.test.js`: os índices `nth-child` têm de ser contíguos de 1 a
N, sem repetir nem furo, e as larguras têm de somar 100%. O jsdom não aplica CSS, então o
que quebrou de fato — o deslocamento — só era visível a olho; o arquivo, porém, é texto, e
as três propriedades pegam qualquer inserção mal feita.

---

## [1.40.2] - 2026-08-30

### Corrigido

- **O `uv.lock` estava em 1.40.0 no `main` com o `pyproject.toml` em 1.40.1.** Os três
  arquivos que já tinham teste de sincronia (`pyproject`, `package.json`,
  `package-lock.json`) foram bumpados; o lock não. Não é cosmético: o lock é o que uma
  instalação reproduzível lê para saber que versão está construindo.

### Adicionado

- **`uv lock --check` como PRIMEIRA linha do `make lint`.** A posição é a regra, não um
  detalhe: qualquer `uv run` abaixo **re-sincroniza** o lock, e aí a divergência some antes
  de ser vista. Foi assim que ela chegou ao `main` sem o CI notar.

  Um teste em pytest **não serve** de guarda aqui, e eu escrevi um antes de descobrir isso:
  o `uv run pytest` cura o arquivo antes de o teste lê-lo, então a asserção nunca falha.
  Foi removido — um teste que não pode falhar é pior que teste nenhum, porque parece
  cobertura.

---

## [1.40.1] - 2026-08-30

### Corrigido

- **A regra da tag SIDRA estava fechada em `if banco == "ppm":`** — as duas metades dela, e
  o `pevs` escapava das duas:
  - **entrada nova sem tag era ACEITA**, caindo na sentinela. Uma sonda HTTP registrou o
    produto `9999999` em produção para provar (removido em seguida);
  - **um update parcial DERRUBAVA a tag.** Este é o pior: os edits inline de agrupamento e
    ciclo na tabela do admin não reenviam a tag, então salvar um deles moveria o produto
    para a sentinela — sumindo das duas metades, sem erro.

  É o padrão *"condicional que nomeia UM banco"*: ela codifica um censo do mundo, e o mundo
  cresceu quando a silvicultura entrou. Passou a derivar de `_BANCOS_MULTI_TABELA`, com o
  vocabulário de tabelas numa função própria (`_tabelas_validas_por_banco`).

### Verificação

Encontrado ao rodar o caminho de ESCRITA do catálogo por **HTTP real** — a camada que eu
mais mexi e menos tinha verificado nesse nível. Depois do conserto:

| sonda | antes | agora |
|---|---|---|
| entrada nova em `pevs` sem tag | **200** (criava na sentinela) | **400** |
| update parcial sem reenviar a tag | derrubaria | **preservada** (`291`) |
| tag de outro banco (`3939` no `pevs`) | 400 | 400 |

O teste do `doctor` que ancora o registro multi-tabela **acusou a mudança de lugar** do
vocabulário — comportamento correto: a âncora foi reapontada para a função nova, que é
âncora melhor por ser dedicada.

---

## [1.40.0] - 2026-08-30

Varredura dos **consumidores** da chave — as camadas que leem as dims e as que apagam dado.

### Adicionado

- **`assert_catalog_join_cannot_fan_out`** (teste dbt). `serving_pam_annual` e
  `serving_ppm_annual` juntam `dim_produto_catalog` por `(source, código)`, **sem a
  tabela** — e desde v1.39.0 a dim pode devolver DUAS linhas para um código presente nas
  duas metades de um banco multi-tabela. O join faria **fan-out e duplicaria os valores do
  fato**, em silêncio.

  O conserto "óbvio" seria escrever o mapeamento `stock↔3939 / flow↔74` no join — uma
  **quarta cópia** de uma decisão que já vive no `.env`, no validador da curadoria e no
  registro do `doctor`. Em vez disso, a suposição que os marts fazem ficou **presa onde é
  usada**: o teste falha alto no dia em que ela deixar de valer, e o comentário no join diz
  o que fazer então.

### Corrigido

- **O plano de purga afirmava "never over-purging" e isso virou condicionalmente falso.**
  O `DELETE` casa por CÓDIGO, não pela chave inteira: um código nas duas metades seria
  purgado por inteiro, levando a metade que NÃO foi marcada como órfã. Não há caso hoje e o
  plano é impresso para revisão humana — então o aviso passou a sair **no próprio plano**,
  onde quem executa lê, e não só no docstring.

### Verificado sem achado

`serving.sql.visibility_clause` e o macro `hidden_code_predicate` casam por `(source,
code)` — consistentes entre si e corretos hoje, já que cada código vive numa metade só. A
imprecisão só apareceria no cenário compartilhado, que `embrapa doctor` → `shared-code`
vigia. `gold_produto_agrupamento` LÊ a dim sem juntar fato, então duas linhas ali seriam o
comportamento correto sob o modelo novo.

---

## [1.39.3] - 2026-08-30

Varredura das camadas restantes da troca de chave — **6 sítios em 3 camadas**, todos
latentes (não há código compartilhado hoje) e todos da mesma forma: identificar um produto
sem a tabela.

### Corrigido

- **Três guardas de idempotência comparavam a chave pela metade** (`(codigo_produto,
  banco, active)` ×2 e `(source, code)`). Um `change_id` reusado entre as DUAS metades de
  um código compartilhado passaria por **replay**, e a segunda edição sumiria — sem erro,
  sem log. Passaram a comparar a chave inteira. No escritor de nível, a resolução da tabela
  subiu para **antes** do guarda, já que ela faz parte do que decide se é replay.
- **As duas chaves de idempotência do frontend** (`_saveKey` e `rm:`) não incluíam a
  tabela: editar as duas metades com os mesmos atributos geraria o **mesmo** change_id.
- **O delete não enviava a tabela.** O backend a resolve quando omitida, mas resolver é
  escolher a última escrita — ambíguo com duas metades. A linha da tela já a tem (é dela
  que sai o selo azul).
- **A mensagem de erro das rotas** ainda chamava `(codigo_produto, banco)` de "a chave do
  catálogo".

### Adicionado

- Guardas em `tests/test_chave_produto.py` para a camada de idempotência, com escopo por
  **conteúdo da tupla** e não por arquivo — o guarda do eixo (aduana × fluxo) fica de fora
  sozinho, porque não fala de produto, e um guarda novo entra na varredura sem ninguém
  lembrar.

---

## [1.39.2] - 2026-08-30

### Corrigido

- **A troca de chave estava incompleta num ponto que a anulava**: os testes de unicidade
  das três dims continuavam em `(codigo_produto, source)` / `(source, code)`, **sem a
  tabela**. Se um código aparecesse nas duas metades de um banco multi-tabela, a curadoria
  agora conseguiria representá-lo — e o build quebraria assim mesmo, que era exatamente a
  situação que a mudança existia para resolver. As três dims passaram a **expor**
  `sidra_tabela` e os três testes a incluí-la.
- **A prosa ficou para trás do modelo** em 4 arquivos: as três dims e a spec
  `PLANS/curadoria_catalogo.md` seguiam declarando o grão antigo horas depois da mudança.

### Verificação

Ao expor a coluna eu **quebrei um alias** e quase publiquei: `codigo_produto as code` virou
`sidra_tabela as code` no `dim_produto_visibility`, o que faria a coluna `code` conter id de
tabela e o gate de visibilidade parar de ocultar. O `dbt build` pegou, e a inspeção depois
confirmou os 3 produtos ocultos com NCM de 8 dígitos em `code`.

### Adicionado

- Guarda de prosa em `tests/test_chave_produto.py`: nenhum doc de grão pode descrever a
  chave sem a tabela. A primeira versão do regex **não pegava a injeção** — o lookahead
  estava depois do parêntese; sem ele o padrão já basta, porque a forma correta tem
  `, sidra_tabela` antes de fechar.

---

## [1.39.1] - 2026-08-29

### Corrigido

- **A troca de chave da v1.39.0 varreu as LEITURAS e deixou CINCO caminhos de escrita para
  trás.** Todos gravavam sem a tabela, então cairiam na sentinela — uma identidade à parte
  que não corresponde a dado nenhum, e nenhum deles daria erro:
  - `remove_produto_catalog` — o tombstone marcaria a sentinela e **a entrada real seguiria
    ativa**, com o delete reportando sucesso;
  - `record_code_industrialization` — a classificação abriria uma **linhagem SCD2 paralela**,
    órfã das versões anteriores do mesmo produto;
  - os três escritores de ciclo de vida (via o funil `_insert_lifecycle_event`) — o evento
    marcaria outro produto.

  Nada corrompeu: as leituras estavam certas e a falha só apareceria na próxima edição de
  curadoria. Os três agora resolvem a tabela pelo catálogo, que é a fonte de verdade da
  identidade (`curation.tabela_do_produto`, aceitando token de banco ou de fonte).

### Adicionado

- **Varredura do lado da ESCRITA** em `tests/test_chave_produto.py`: todo `insert` num log
  de produto tem de nomear `sidra_tabela`, o tombstone tem de preservar a tag guardada, e o
  evento de ciclo de vida tem de levar a tabela que o catálogo resolveu. Ficam de fora, por
  critério de coluna e não de arquivo: a allowlist de editores, o log de agrupamentos (um
  grupo não é produto) e o de aduana × fluxo.

### Verificação

Prova de ponta a ponta em produção: regravar a classificação do `3457` com o **mesmo** nível
(latest-wins, nenhuma decisão muda) gravou `sidra_tabela='291'` — antes teria ido para a
sentinela.

Uma injeção passou verde e o defeito era o teste — **quinta vez no mesmo dia**: ele
procurava o nome `tabela_do_produto` no TEXTO do módulo, e a linha de `import` sobrevivia a
trocar a chamada por `None`. Virou teste de comportamento, sobre o parâmetro que chega ao
BigQuery.

---

## [1.39.0] - 2026-08-29

### Alterado

- **A identidade de um produto na curadoria passou a ser `(banco, tabela, código)`**, nos
  três registros que a assumiam: catálogo, gate de visibilidade e nível de
  industrialização. PEVS e PPM unem duas tabelas SIDRA sob um token de banco só, e com a
  chave antiga um código presente nas duas metades seria um produto só — um agrupamento,
  uma visibilidade e um nível cobrindo ambas, a tag da tela mostrando uma delas
  arbitrariamente, e a ingestão dirigida pelo catálogo perdendo a metade não marcada em
  silêncio.
- **A chave vive em UM lugar por linguagem**: `serving.sql.CHAVE_{CATALOGO,CLASSIFICACAO,
  CICLO_DE_VIDA}` no Python e o macro `chave_produto` no dbt. Eram **16** `partition by`
  redigitados em 5 módulos mais 3 modelos — e uma chave que muda em 15 lugares e fica no
  16º é a forma exata do defeito que este projeto teve três vezes em um único dia.
- **A tag da tabela virou obrigatória** em entrada nova nos dois bancos multi-tabela. Sem
  ela a entrada não cai em nenhuma das metades: cai na sentinela, uma terceira identidade
  que não corresponde a dado nenhum. Bancos de uma tabela (comex, comtrade, pam) não foram
  tocados — para eles a coluna não carrega informação e o `ifnull` a colapsa.

### Migração

`scripts/migrate_catalog_key_add_table.py` (ensaio por padrão). A armadilha, medida antes:
o log é append-only e as linhas anteriores à coluna a têm NULL, então promover a coluna
para dentro da chave transformaria **supersessão em coexistência** — **258** entradas ativas
onde havia **234**, 24 fantasmas.

1. `UPDATE` em **51** linhas históricas, preenchendo com o valor que a própria entrada já
   carrega — completa uma coluna que era NULL *porque não existia quando a linha foi
   escrita*; nenhuma decisão de pesquisador mudou.
2. Coluna adicionada aos logs de nível e ciclo de vida **e às constantes de esquema** —
   senão uma instalação nova criaria a tabela sem ela. Furo que um teste existente pegou.
3. Depois: **234 com qualquer das duas chaves**. Verificado em produção após o build:
   catálogo 234 · `dim_produto_catalog` 234 · `gold_produto_agrupamento` 234 ·
   classificações 308 · `embrapa doctor` verde.

Registrado em `docs/migration_history.md`.

### Adicionado

- `tests/test_chave_produto.py`: varre os **call sites** — nenhum pode redigitar a chave
  antiga, todo `partition by` de log de produto deriva da constante (Python) ou do macro
  (dbt), e os dois lados usam a **mesma** sentinela. Divergir criaria dois produtos onde há
  um, e nada mais no sistema notaria. O log de agrupamentos é excluído por nome: um grupo
  não é um produto e não tem tabela SIDRA.

---

## [1.38.0] - 2026-08-29

### Adicionado

- **`embrapa doctor` → `shared-code`**: avisa se um código passar a existir nas **duas**
  tabelas SIDRA de um banco multi-tabela (PEVS: extração t289 × silvicultura t291; PPM:
  rebanho 3939 × produção animal 74). Hoje não há nenhum — 7 contra 3 no PEVS, 8 contra 6
  no PPM, sem interseção.

  Se aparecer, três coisas acontecem e **só a primeira faz barulho**:

  1. O teste de unicidade do Gold (chave sem o discriminador, severidade `error`) falha, e
     como o prod roda `dbt build` os modelos downstream são pulados — o número errado não
     chega ao dashboard.
  2. A curadoria **não consegue representar** o caso: catálogo, gate de visibilidade e nível
     de industrialização identificam um produto por `(banco, código)` e nenhum dos três
     conhece a tabela. Seriam um agrupamento, uma visibilidade e um nível cobrindo as duas
     metades, e a tag da tela mostraria uma delas, arbitrária.
  3. Com `catalog_authoritative_ingestion` ligado, o resolver filtra por `sidra_tabela` e a
     metade não marcada deixaria de ser buscada **em silêncio**.

  **Por que só o check, e não a correção definitiva.** Corrigir (2) de verdade exige trocar
  a identidade do produto em ~25 pontos de código, 3 dims e 3 logs — sobre o único dado do
  projeto que não se recalcula — para fechar um buraco hoje **inalcançável**, já que (1)
  barra o dado e (3) depende de uma flag desligada. O check transforma "inalcançável" em
  "detectado", com tempo para decidir diante de um caso concreto. Gatilho para reabrir: o
  IBGE publicar um código compartilhado, ou a decisão de ligar a ingestão dirigida.

### Verificação

Quatro injeções. A segunda passou verde e **o defeito era o teste**: ele contava
`len(_BANCOS_MULTI_TABELA)`, derivado da própria constante, então remover um banco mudava
os dois lados da asserção. A âncora passou a ser independente —
`curation._validate_sidra_tabela` mantém a mesma lista por outro motivo, e as duas
divergirem é sempre defeito. Agora acusa nas duas direções.

---

## [1.37.2] - 2026-08-29

### Corrigido

- **A documentação ficou para trás do trabalho de hoje**, em três pontos:
  - `ARCHITECTURE.md` listava **três** modelos Silver do IBGE onde havia quatro — o
    `silver_ibge_silvicultura.sql` entrou hoje e a árvore de pastas não o registrou. Um
    leitor concluiria que o PEVS tem uma metade só. A descrição do
    `gold_pevs_production` passou a dizer que ele é fonte **multi-tabela** (t289 + t291,
    discriminadas por `origem`) e a explicar por que o teste de unicidade **não** inclui
    `origem`: os códigos das duas metades são disjuntos hoje, e se o IBGE reusar um o
    teste falha alto no build seguinte — que é exatamente o sinal desejado.
  - `CLAUDE.md` e `README.md` descreviam o backup como sendo **só do Gold**, desatualizado
    desde v1.36.0.
  - `ARCHITECTURE.md` também não citava `dim_produto_visibility` nem
    `dim_flow_market_scd2`, ambos anteriores a hoje.

### Adicionado

- **`tests/test_architecture_model_coverage.py`**: todo modelo dbt precisa aparecer no
  `ARCHITECTURE.md`. O teste existente (`test_doc_file_references`) prende a direção **para
  frente** — caminho citado tem de existir. O inverso é que escapava: renomear ou remover
  um teste falha alto porque o import quebra, mas **acrescentar** um modelo não falha em
  lugar nenhum; o doc só fica incompleto, em silêncio. As quatro camadas
  (silver/gold/serving/core) estão agora em 100%.

---

## [1.37.1] - 2026-08-29

### Alterado

- **O registro de divergências passou a explicar a classe `ausente no MDIC`.** Ela parece
  lacuna a preencher e não é: a tabela do MDIC cobre o SH da nomenclatura **brasileira**, e
  o COMTRADE é comércio **mundial** numa janela de 25 anos. Medido, os 14 casos se dividem
  em três situações sem conserto do lado do MDIC:

  1. **Aposentado** numa revisão do SH — `440331`/`440335` (madeiras tropicais) só aparecem
     no Gold em **2000–2005**.
  2. **Vigente que o Brasil não usa** — `440714` (Hem-fir, conífera norte-americana) tem
     **703 linhas em 2022–2025** e nenhuma entrada no MDIC.
  3. **Linha de seed sem dado**, que custa uma linha de CSV.

  Sem essa nota, um mantenedor futuro caçaria entradas que não existem. O seed pode ser
  mais largo que os dados; o contrário é que quebra, e disso cuida
  `assert_trade_codes_have_a_description`.

---

## [1.37.0] - 2026-08-29

Auditoria da captura da descrição da fonte, com duas decisões do pesquisador.

### Corrigido

- **A remoção do ordinal da SIDRA podia comer texto informativo.** O padrão era
  `^([^-]+)\\s-\\s` — remove QUALQUER prefixo sem hífen, então um produto chamado
  `"Açaí - fruto"` teria perdido o "Açaí" e aparecido como `"fruto"`. Nenhum valor da SIDRA
  jamais acionou isso (10 distintos, todos ordinais), mas *"ainda não aconteceu"* não é
  garantia. O padrão passou a exigir **dígitos e pontos** (`^[0-9]+(?:\\.[0-9]+)*\\s-\\s`),
  o que torna a perda **impossível por construção**: texto informativo não casa com
  `[0-9.]+`. Demonstrado lado a lado no BigQuery — o padrão antigo transformava
  `"Açaí - fruto"` em `"fruto"`; o novo preserva, e nos ordinais reais os dois coincidem.

  A remoção em si foi **mantida** por decisão do pesquisador: o ordinal é posição no menu
  da SIDRA, não atributo do produto — carvão vegetal é `7.1` na t289 e `1.1` na t291.

### Adicionado

- **Registro de divergências de nomenclatura** (`docs/nomenclatura_divergencias.md`,
  gerado por `make nomenclature-audit`). COMEX e COMTRADE **não trazem descrição nos
  dados**: o arquivo do MDIC tem `CO_NCM` e números, o Bronze do COMTRADE idem. O nome que
  o pesquisador lê é artefato editorial deste repositório. Política decidida: **usar o
  texto pleno da nomenclatura e registrar a divergência**. São **218** divergências
  classificadas em quatro classes — `oficial abreviado` (11), `nosso mais pleno` (140),
  `procedência distinta` (53), `ausente no MDIC` (14).

  Por que não copiar o oficial: `NO_NCM_POR` é campo de **exibição** com limite de
  tamanho, que produz `Outs.painéis` e `n/trab.mecan.d>0.8g/cm3` — e às vezes está
  **factualmente errado**: em `15079019` (o código "outros", acima de 5 litros) a tabela dá
  a descrição do irmão, "menor que 5 litros".
- **Três guardas**: `assert_sidra_prefix_strip_is_lossless` (dbt, prende a propriedade nos
  DADOS — acusa a SIDRA mudar de forma) e dois testes de código que prendem o **padrão** e
  proíbem uma segunda remoção na coluna. A separação veio de uma injeção: o teste dbt
  sozinho passava com o padrão permissivo, porque os 10 valores reais são todos ordinais.

### Auditoria — o que se confirmou intacto

`SIDRA → Bronze` verbatim · `Silver → Gold` sem transformação · `Gold → API` sem
transformação · `API → tela` sem truncamento (todo `.slice` no frontend é de array) ·
exportação CSV verbatim (só escape RFC-4180). Riscos estruturais sem caso hoje:
`any_value(name)` escolheria arbitrariamente se um código tivesse dois nomes (0 em 234).

---

## [1.36.2] - 2026-08-29

### Corrigido

- **36 descrições do COMTRADE liam como fragmento** (`"- Outras, de coníferas"`,
  `"-- De faia (Fagus spp.)"`). Não estavam truncadas: o texto estava íntegro, mas veio da
  nomenclatura **hierárquica** da NCM/SH, onde a linha herda o sentido do título-pai — e os
  `-` / `--` são o marcador de nível, não parte do nome. Todas as 36 eram do **capítulo 44**
  (madeira), o mais recente a entrar no seed; as outras 199 vieram de fonte autocontida, e o
  seed do COMEX nunca teve o problema (0 de 263).

  Substituídas pelo nome oficial autocontido do MDIC (`NCM_SH.csv`, `NO_SH6_POR`), no grão
  exato que o COMTRADE usa. Ex.: `440320` passou de `"- Outras, de coníferas"` para
  **"Madeira de coníferas, em bruto"**.

### Alterado

- **9 das 36 foram COMPOSTAS em vez de substituídas.** A tabela do MDIC abrevia algumas
  linhas para caber no campo (`Outs.painéis`, `n/trab.mecan.d>0.8g/cm3`,
  `recob.placas plástico`), e copiá-las teria **degradado** o rótulo em vez de melhorá-lo.
  Nesses casos o texto foi composto com o título-pai limpo (`SH4 — fragmento`), ficando
  completo sem herdar a abreviação. Os 36 substitutos são todos distintos entre si, e a
  distinção que o fragmento carregava se preserva — `440610` "não impregnados" contra
  `440690` "impregnados", que o seed antes chamava só de `"- Outros"`.
- Nenhum rótulo novo estourou a norma do arquivo: o comprimento máximo segue **366**
  caracteres, o mesmo de antes (mediana 104, p90 206).
- As outras 199 linhas foram deixadas em paz de propósito: 214 diferem do texto oficial,
  mas quase todas por variação cosmética, e reescrevê-las trocaria rótulos que já estão bons.

### Adicionado

- `tests/test_seed_descriptions.py`: **nenhuma** descrição de seed pode começar com `-`
  (fragmento hierárquico) nem conter a marca de abreviação do MDIC (ponto colado em letra
  minúscula). Vale para os dois seeds, com um terceiro teste que guarda o próprio varredor.

---

## [1.36.1] - 2026-08-29

### Corrigido

- **Cinco produtos apareciam sem descrição da fonte ("—") mesmo tendo dados.** O nome vem
  de um seed curado à mão (`comex_ncm` / `comtrade_hs`) por `left join`; os códigos
  `14011000`, `15079010`, `20059100` (NCM-8) e `140110`, `200591` (HS-6) **não estavam
  lá**, então o join devolvia NULL. Dois deles são do capítulo **14** (bambu), que o filtro
  documentado do seed nunca listou — o produto foi ingerido e cadastrado, e a lacuna só
  aparecia para quem lesse a tela de cadastro.

  As descrições novas vieram da **tabela oficial do MDIC** (`NCM.csv`, coluna
  `NO_NCM_POR`), nunca escritas de memória. A fonte foi validada por controle: o código
  `44011000`, já presente no seed, devolve exatamente o texto que lá estava. Para os dois
  HS-6, cada um tem **um único** filho NCM, então o texto oficial do NCM é o do SH6; a
  unidade `kg` vem de `CO_UNID=10` = QUILOGRAMA LÍQUIDO (`NCM_UNIDADE.csv`).
- **Removidas as 4 entradas HS-4 (`4401`/`4402`) do catálogo de COMEX e COMTRADE.** Foram
  criadas em v1.35.x pela reorganização dos agrupamentos de madeira, que adicionou o
  cabeçalho de 4 dígitos sem verificar que os 29 códigos específicos já estavam
  cadastrados **e nos mesmos agrupamentos**. O COMEX indexa por NCM-8 e o COMTRADE por
  HS-6, e o catálogo casa pelo código exato — um código de 4 dígitos nunca encontra dado.
  O check `Catalog → Gold arrival` do `doctor` passou de 4 pendências para zero.

### Adicionado

- **`assert_trade_codes_have_a_description`** (teste dbt): falha quando um código chega ao
  Gold que o seed não sabe nomear. Compara o seed com os **dados**, não com a nomenclatura
  inteira — o seed não precisa cobrir todo o universo NCM/HS, só o que a ingestão de fato
  trouxe. Validado contra produção: acusa exatamente os 5 códigos acima.

**Nota operacional:** o efeito na tela depende de um `dbt build` de produção, que recarrega
os seeds. O build agendado (seg/qui) aplica sem custo extra.

---

## [1.36.0] - 2026-08-29

### Adicionado

- **O backup passou a cobrir `research_inputs` — a única coisa insubstituível do projeto.**
  O Gold é **derivável**: perdê-lo custa um `dbt build`, porque cada linha remonta ao
  Bronze. O `research_inputs` é **autoral** — catálogo de produtos, registro de
  agrupamentos, classificações de industrialização, log de ciclo de vida e as allowlists
  de quem pode editar. Nada disso se recalcula de fonte nenhuma, e era **o único dataset
  sem backup**, enquanto a metade reproduzível tinha um quase diário. São 12 tabelas,
  1310 linhas, ~220 KiB: o custo de cobrir arredonda para zero.
- **`embrapa doctor` → `curation-backup`**, que lê o manifesto do snapshot mais recente e
  **falha** se ele for anterior à cobertura. A chave `curation_table_count` **ausente**
  significa "snapshot anterior à cobertura"; **`0`** significa "coberto, dataset vazio" —
  estados diferentes, e confundi-los é o que chamaria de protegido um snapshot que não
  protege nada.

### Alterado

- O layout do Gold no snapshot segue **byte a byte** o de antes (`run=<id>/<tabela>/`); a
  curadoria entra sob `run=<id>/_curation/`, então qualquer ferramenta de restauração
  escrita contra o formato antigo continua valendo.
- A introspecção da curadoria **não filtra por prefixo** (o Gold filtra): toda tabela desse
  dataset é autoral, e um filtro seria mais uma coisa a manter em sincronia — a lista fixa
  de tabelas Gold, que já escondeu um bug real quando 3 dos 4 modelos sumiram, é o
  precedente.

**Verificado em produção:** snapshot `20260829T182244Z` gravado com 6 tabelas Gold + 12 de
curadoria; o check saiu de FALHA para `12 curation table(s)`.

---

## [1.35.7] - 2026-08-29

### Corrigido

- **As três rotas de comércio (`/flow`, `/partners`, `/monthly`) não parseavam eixo
  nenhum.** Em v1.35.6 os leitores ganharam o recorte por nível e as rotas continuaram
  chamando `_filter_summary()` cru — o seam pronto e nada o alimentando. O sinal foi um
  nível **inválido respondendo 200** em vez de 400: uma rota que não valida é uma rota que
  não parseia. Também não chegavam `flow`, `customs` nem `market`, apesar de o comentário
  no `flow_data` dizer explicitamente que eles *"must narrow the Sankey too"*.
- **`flow` agora recorta o Sankey do COMTRADE** (`export` e `import` devolvem respostas
  distintas) e um valor inválido devolve 400. No COMEX o Sankey **continua fixo em export**
  — isso é por desenho no seam, não um eixo perdido.

### Alterado

- **Os cinco eixos de valor passaram a ser dobrados num lugar só.** A rota `/snapshot` os
  dobrava inline, e *só* ela — que é exatamente como as outras oito ficaram sem. Agora ela
  também deriva de `_with_filter_axes`. No frontend, `activeAxisParams` passou a devolver
  os cinco, `axisKey` **deriva** o fragmento das chaves do próprio objeto (nunca uma lista
  escrita à mão), e o `geoYearly` deixou de tratar `flow` por conta própria.

### Varredura completa dos sete eixos

| eixo | estado |
|---|---|
| `flow` | chega e valida · COMEX fixa `export` por desenho |
| `customs` | chega · a base só tem `C00` (2.053.708 linhas), então não há o que recortar |
| `market` | chega · coluna 100% NULL — o eixo congelado, documentado |
| `reporters` | já chegava · 3 estados (ausente = Brasil, `__all__`, lista) |
| `partners` | já chegava |
| `origem` | corrigido em v1.35.5 |
| `niveis` | v1.35.6 + estas três rotas |

**Duas injeções reprovaram testes MEUS**, não código: nada assertava o *conteúdo* do helper
de rotas (remover `customs` deixava tudo verde), e a varredura do frontend olhava o sítio de
chamada `axisKey(ax)` em vez do que `axisKey` faz (trocar o corpo por `return ax.origem`
passava). Ambos fechados, e a injeção repetida agora acusa.

---

## [1.35.6] - 2026-08-29

### Corrigido

- **O filtro de nível de industrialização tinha o mesmo defeito do `origem`, um eixo ao
  lado.** Também nasceu passado só pelo caminho do snapshot, então o mapa, o cubo
  municipal, os dois rankings de produto e os três leitores de comércio o **ignoravam por
  completo**: o snapshot mostrava 1,3 bi para `commodity_pura` ao lado de um mapa que
  mostrava os 1.063,5 bi inteiros.

  O eixo alcança os leitores por um mecanismo **diferente** do `origem` — o nível mora numa
  dim SCD2 própria e nenhum fato o carrega, então ele se resolve para uma lista de códigos
  em vez de virar predicado SQL. O bloco que fazia isso vivia inline no `snapshot`; virou
  `_apply_levels`, chamado pelos **oito** leitores que honram cesta.

### Alterado

- **Um helper por eixo virou um helper para todos.** `_with_origem` (v1.35.5) virou
  `_with_filter_axes`, que dobra `origem` **e** `niveis` na summary de toda rota; no
  frontend, `activeOrigemParam` virou `activeAxisParams` + `axisKey`, espalhados com
  `...ax`. O próximo eixo entra em **um** lugar em vez de precisar ser lembrado em oito
  sítios de chamada — que é exatamente como estes dois falharam, com um dia de intervalo.

### Verificação

Os dois eixos **compõem** (um recorta coluna, o outro recorta a lista de códigos):

| recorte | valor |
|---|---|
| `origem=silvicultura` | 690.562 |
| `+ niveis=commodity_acondicionada` | 548.906 |
| `+ niveis=manufaturado_industrial` | 141.655 |

548.906 + 141.655 = 690.561 — os dois níveis particionam a metade exatamente. Um nível
inválido devolve **400**. E `origem=silvicultura&niveis=commodity_pura` devolve **zero**,
que é a resposta certa: nenhum dos três produtos de silvicultura é `commodity_pura`
(carvão é `manufaturado_industrial`; lenha e tora são `commodity_acondicionada`).

As duas varreduras de fio passaram a cobrir os dois eixos, cada uma com a asserção que cabe
ao mecanismo do eixo. Uma injeção reprovou um **teste meu** que era fraco demais (checava o
nome do eixo no corpo do helper, não no que ele devolve) — corrigido.

---

## [1.35.5] - 2026-08-29

### Corrigido

- **O filtro `origem` não chegava ao mapa, ao cubo municipal nem aos dois rankings de
  produto.** O eixo nasceu em v1.34.0 e foi passado só pelo caminho do snapshot. Medido
  sobre 2020–2023 antes da correção — totais **idênticos** para `extrativa`, `silvicultura`
  e sem filtro nenhum, onde a separação correta é **372,9 bi × 690,6 bi**. As duas metades
  diferem ~6× em valor, então não era imprecisão: era **um recorte diferente do que o
  usuário pediu, sob o rótulo dele** — o que a regra dura do projeto proíbe.

  Corrigido no fio inteiro: dois builders SQL (`products_by_uf`, `products_by_municipio`)
  e dois leitores do gateway passaram a aceitar `origem`; cinco sítios do seam passaram a
  passá-la; cinco rotas passaram a lê-la por um helper único (`_with_origem`); e os quatro
  produtores do frontend passaram a **enviá-la e a chavear o cache por ela** — enviar sem
  chavear serve a resposta da metade anterior a partir da memória, o que parece idêntico a
  não enviar.

  Verificado pelo HTTP real: `/api/geo-yearly` devolve 1051 linhas sem filtro, 1017 em
  extrativa, 836 em silvicultura, e `origem=plantada` → **400**.

### Adicionado

- **Testes de FIO para o eixo** (`tests/test_origem_wiring.py`,
  `frontend/src/data/producers.origem.wiring.test.js`). Cada leitor já tinha teste do seu
  parâmetro `origem`; ninguém verificava se as **chamadas** o passavam. A varredura lê o
  AST do seam e exige `origem` em toda chamada a leitor PEVS — distinguindo PEVS de COMEX
  pelo `table_key`, porque `fetch_products_by_uf` serve os dois e `serving_comex_annual`
  não tem essa coluna (há teste para o converso também). No frontend, um teste por modo de
  falha: não enviar, e enviar sem chavear.

**Fora de escopo, medido:** o cruzamento entre fontes também não recebe o eixo, mas suas
views declaram `requires: []` — não anunciam filtro nenhum (nem a cesta de produtos), então
ali não há promessa quebrada.

---

## [1.35.4] - 2026-08-29

### Corrigido

- **O PEVS virou um banco de duas tabelas SIDRA e a curadoria continuava assumindo que só o
  PPM era.** Quando a silvicultura (t291) entrou hoje, toda a pilha de catálogo seguiu
  tratando `sidra_tabela` como campo exclusivo do PPM — a validação recusava carimbar uma
  entrada PEVS, o resolver não sabia separar as metades, o `doctor` acusava DRIFT
  permanente e a tela não mostrava nem oferecia a marca.
- **A regra estava escrita duas vezes.** `record_produto_catalog` tinha uma cópia literal
  inline (como otimização "rejeitar cedo, sem BQ") além do validador dedicado. Ao
  generalizar só o validador, **toda escrita PEVS continuou sendo recusada** com a mensagem
  antiga. Agora o portão delega ao mesmo validador em vez de repetir a regra.
- **O `doctor` acusava DRIFT permanente e correto-por-desenho.** Comparava o token `pevs`
  inteiro contra `IBGE_PRODUCT_CODES` (só t289), então os três códigos de silvicultura
  apareciam como divergência para sempre. Agora compara **por tabela**, como o PPM sempre
  fez: `pevs:289 OK(7) · pevs:291 OK(3)`. Um operador que aprende a ignorar o doctor é o
  custo real de um alarme falso fixo.

### Alterado

- **As 10 entradas PEVS do catálogo foram carimbadas** (`scripts/stamp_pevs_sidra_tabela.py`,
  idempotente, ensaio por padrão): t289 nos 7 códigos de extração, t291 nos 3 de
  silvicultura. A tabela de cada código é derivada de `SILVICULTURA_PRODUCT_CODES`, nunca
  redigitada.
- **A silvicultura passou a resolver pelo catálogo**, com escopo `sidra_tabela=291` — o que
  o docstring do pipeline já previa ("até o catálogo aprender a marcar a tabela SIDRA de um
  código"). Um produto que o pesquisador adicionar à metade plantada passa a ser ingerido
  sem edição de `.env`.
- **Uma entrada PEVS sem marca resolve como extração**, em vez de deixar de ser ingerida:
  toda entrada é anterior à coluna, extração é o que "um produto PEVS" significou por toda
  a história e é ~4× a outra metade. O PPM mantém o `=` estrito — lá as duas tabelas não
  compartilham código e adivinhar buscaria a tabela errada.
- **A tela de cadastro** oferece "Metade do PEVS" (Extração vegetal / Silvicultura) e mostra
  o selo na listagem. A marca é **opcional** no PEVS e obrigatória no PPM, derivado de um
  registro por banco em vez de `banco === 'ppm'` espalhado por quatro lugares.

**Por que isso importa.** Com `catalog_authoritative_ingestion` ligado, o pipeline de
**extração** — a metade maior — pediria à t289 os três códigos de silvicultura. A SIDRA
responde com fatia vazia e o pipeline reporta um no-op limpo: a ingestão pararia e nada
diria. O risco estava latente só porque a flag está `off`.

---

## [1.35.3] - 2026-08-29

### Adicionado

- **`embrapa doctor` agora verifica a integridade referencial da curadoria.** As duas
  escritas que um pesquisador faz todo dia apontam para um vocabulário definido em outro
  lugar, e nenhuma das duas conferia o alvo: uma entrada de catálogo nomeia um
  `agrupamento_id`, e uma classificação nomeia um nível de industrialização. O check
  `curation-integrity` cruza cada uma com o seu registro e **falha** (não é advisory:
  nenhuma das duas condições é legítima). Lê só os dois logs pequenos — sem varredura de
  Gold, custo zero. Instalação fria degrada para `skipped`.
- **Paridade da escala de industrialização entre frontend e backend**
  (`tests/test_enrichment_scale_parity.py`). `CUR_LEVELS` e `window.ENRICH_LEVELS` são um
  vocabulário escrito em dois arquivos; nada ligava os dois. Compara **ordem**, não só
  composição — a posição é o ordinal que desenha o gradiente do valor agregado, então uma
  lista reordenada mantém todos os ids e ainda redesenha a análise errada.

### Corrigido

- **A escala de níveis estava declarada três vezes.** `routes._ALLOWED_NIVEIS` era cópia
  literal de `seam_attribute_engineering.CUR_LEVELS`, criada junto com o filtro de nível
  em v1.35.1. Agora é **derivada** (`(*CUR_LEVELS, UNCLASSIFIED_NIVEL)`) — a divergência
  deixa de ser possível em vez de ser vigiada. Sem mudança de comportamento: os mesmos 9
  valores, a sentinela ao fim.

**Por que isso importa.** O defeito de 2026-08-29 — 37 produtos apontando para
agrupamentos que nunca foram criados — não falhou em lugar nenhum: a escrita deu certo, o
log ficou consistente consigo mesmo, e os produtos apenas sumiram de toda visão agrupada,
aparecendo só no título "Sem agrupamento registrado (38)" que um humano leu por acaso. O
escritor passou a recusar isso em v1.35.2; este check fecha o caminho de quem **não passa
pelo escritor** (insert direto, backup restaurado, grupo removido depois). O nível de
industrialização tinha o mesmo buraco uma dimensão ao lado: vocabulário aberto na escrita,
então um nível com typo fica invisível a todo filtro **e** ausente de "sem classificação".
Medido hoje: 308 classificações em 5 níveis, todas válidas — o invariante valia e nada o
sustentava.

---

## [1.35.2] - 2026-08-29

### Corrigido

- **37 produtos apareciam em "Sem agrupamento registrado", e a culpa era da v1.34.4.** Um
  agrupamento é **duas** coisas: uma linha no registro de grupos, e o `agrupamento_id` que
  as entradas do catálogo carregam. A reorganização da madeira escreveu a segunda **sem a
  primeira**, então 37 produtos passaram a apontar para `lenha` e `carvao_vegetal` —
  grupos que nenhuma linha respaldava. Mais um caso pré-existente (`abacaxi`) fecha os 38
  que a tela mostrava.

  A tela estava certa o tempo todo: a palavra **"registrado"** era a distinção inteira, e
  eu a li como sinônimo de "sem agrupamento". Procurei o número em quatro consultas
  diferentes antes de olhar o que ela de fato dizia.

  Os três grupos foram registrados (`scripts/register_missing_agrupamentos.py`). O nome
  importa e não é cosmético: o id é o **slug do nome**, e "Lenha e resíduos lenhosos"
  geraria `lenha_e_residuos_lenhosos`, que não casaria com o id que as entradas já
  carregavam. Os grupos ficaram "Lenha" e "Carvão vegetal", e as 26 entradas foram
  regravadas para o nome bater com o registro.

- **O escritor do catálogo passa a recusar um agrupamento inexistente.** Era o buraco que
  permitiu tudo isso: `record_produto_catalog` validava o código e o ciclo de vida, e
  nada sobre o grupo existir. Uma escrita apontando para o vazio era aceita, a Gold
  materializava o id, e o produto caía fora de toda análise cruzada **sem erro nenhum** —
  visível só para quem estivesse olhando aquela seção da tela.

  Um registro **ausente** continua não bloqueando nada: numa instalação fria não há contra
  o que validar, e recusar tudo impediria cadastrar o primeiro produto. Vazio significa
  "nada a checar", não "tudo inválido".

### Testes

3 casos novos, validados por injeção: remover a guarda derruba um; fazer o registro vazio
recusar tudo derruba nove — o que mostra quanta coisa depende de a instalação fria
continuar funcionando.

---

## [1.35.1] - 2026-08-29

### Corrigido

- **O IBGE PAM ficou sem o filtro de nível de industrialização.** A v1.35.0 gateava o
  filtro por uma **lista de bancos escrita à mão**, e a PAM não estava nela. Não era
  decisão: eu montei a lista a partir de uma consulta cujo resultado **truncei com `tail`**
  — e `ibge_pam` ordena logo antes de `ibge_pevs`, então a linha que o incluiria foi
  exatamente a cortada. A PAM tem 4 dos seus 11 códigos classificados.

  O portão passa a derivar da **capacidade** do banco (`provides` inclui `product`), que
  não tem como ficar desatualizada. Todos os cinco bancos com produtos oferecem o filtro.

- **A busca do banco era indireta e podia responder sobre outro.** `bancoById` cai no
  primeiro banco quando o id é desconhecido — conveniente em quase todo lugar, errado num
  portão, que passaria a responder "sim, tem o filtro" sobre um banco diferente do
  perguntado. Trocada por busca direta no registro.

### Testes

3 casos novos, validados por injeção: voltar à lista fixa sem a PAM, copiar a escala em
vez de lê-la do registro do editor, e remover a opção "sem classificação" — cada um
derruba o seu.

O segundo importa por um motivo próprio: a escala vem de `ENRICH_LEVELS`, que é o
registro **do editor**. Uma cópia aqui poderia divergir do que o editor grava, e o filtro
ofereceria níveis que ninguém consegue atribuir — ou omitiria os que existem.

---

## [1.35.0] - 2026-08-29

O menu de filtros ganhou **Nível de industrialização** — o eixo existia no editor, na
dimensão SCD2 e na view "Valor agregado", mas em lugar nenhum onde se pudesse recortar
um painel por ele.

Isso importava mais do que parecia: foi o argumento que sustentou juntar madeira bruta e
serrada num agrupamento só (v1.34.3). Sem o filtro, a separação que eu prometi não
existia.

### Adicionado

- **Filtro por nível de industrialização** — multi-seleção sobre a escala curada de 8
  níveis, disponível nos quatro bancos que têm códigos classificados. Resolvido no
  servidor: o nível mora numa dimensão própria e não no fato, então o seam traduz níveis →
  códigos e **intersecta com a cesta** — as duas restrições se compõem em vez de uma
  sobrescrever a outra.

  O eixo viaja: chip, referência ABNT (só quando reduz o escopo), coluna no CSV e
  parâmetro `ni` no permalink.

- **"Sem classificação" é opção explícita.** O eixo é curado à mão e por construção nunca
  está completo, então o que ainda não tem nível precisa poder ser **visto**, não sumir de
  todo recorte. Ele não é lido da dimensão — é definido por **ausência** dela, e é por
  isso que o resolvedor recebe o universo de códigos do banco.

  E há uma guarda para o caso de todos os níveis escolhidos não resolverem código nenhum:
  uma cesta vazia seria lida adiante como "sem filtro de produto" e serviria o banco
  inteiro — o oposto do que foi pedido. Um sentinela que não casa com nada mantém a
  resposta honesta.

- **A PEVS foi a 100% de cobertura** (`scripts/classify_pevs_industrialization.py`). Ela
  estava em 50%, e três das cinco lacunas foram criadas pela v1.34.0, que cadastrou os
  produtos da silvicultura sem classificá-los. Cada nível foi herdado de um análogo
  **dentro da PEVS**, não do comércio: o NCM de açaí classificado é purê (SH 2007) e os de
  castanha são descascadas — ambos a jusante do que a PEVS mede.

### Verificação

Contra a Gold de produção, os níveis **particionam** o dado sem vazamento:
`commodity_acondicionada` R$ 30,81 bi + `manufaturado_industrial` R$ 8,93 bi +
`commodity_pura` R$ 1,17 bi = **R$ 40,91 bi**, exatamente o total sem filtro. E
`sem_classificacao` dá zero, como tem de dar agora que a PEVS está inteira.

9 testes novos, validados por injeção — quebrar o sentinela de "sem classificação",
aceitar um nível inválido na rota, tirar o parâmetro da requisição, e ignorar a fonte ao
resolver os códigos, cada um derruba o seu.

Dois deles cobrem o **fio**, não o resolvedor: que um nível escolhido chega aos leitores
como códigos, e que ele **compõe** com a cesta em vez de sobrescrevê-la. Era a lacuna que
o portão de cobertura acusou — o resolvedor estava testado isolado e a integração não,
exatamente o padrão que deixou o eixo `origem` subir quebrado.

**Um dos testes não guardava o que dizia guardar.** Ele afirmava impedir que um código de
outra fonte com os mesmos dígitos vazasse para o resultado — e a injeção que remove a
separação por banco passou. O caso pedia um nível que a outra fonte não tinha, então a
contaminação não tinha como aparecer. Reescrito para pedir exatamente o nível que só
existe na outra fonte: agora a injeção derruba.

---

## [1.34.4] - 2026-08-29

Reorganização dos agrupamentos de madeira **aplicada em produção**, com duas correções
que a própria execução revelou.

### Resultado

| agrupamento | códigos | fontes |
|---|---|---|
| `madeira` | 108 (era 136) | comex · comtrade · pevs |
| `lenha` | 24 | comex · comtrade · pevs |
| `carvao_vegetal` | 9 | comex · comtrade · pevs |

Os agrupamentos degenerados `3433` e `3434` — um membro só, id igual ao código — deixaram
de existir, e os três códigos da silvicultura entraram nos seus grupos. Cada agrupamento
reúne agora extração e plantio das três fontes, e a comparação que nada disso permitia
antes fica disponível:

| | extrativa 2023 | silvicultura 2023 |
|---|---|---|
| madeira | R$ 2,88 bi | R$ 19,4 bi |
| carvão vegetal | R$ 0,41 bi | R$ 7,49 bi |
| lenha | R$ 0,71 bi | R$ 4,26 bi |

### Corrigido no script, durante a execução

- **A fonte da verdade era a Gold, e devia ser o catálogo.** `gold_produto_agrupamento`
  só expõe códigos que **têm dado**, então um produto registrado mas ainda não ingerido é
  invisível ali — e são justamente esses que uma reorganização não pode pular, porque
  nada mais volta a visitá-los. A primeira passada deixou **4 códigos para trás** (dois de
  4401 e dois de 4402, presentes no catálogo e ausentes da Gold). O script passa a ler o
  log de curadoria.

- **As escritas precisam do contexto Flask.** Registrar uma entrada **nova** alcança o
  flask-caching, que é ligado ao app; sem o contexto a escrita morre com
  `'Cache' object has no attribute 'app'`. E o modo de falha é traiçoeiro: só o caminho de
  entrada nova quebra, então uma execução que apenas **atualiza** linhas existentes parece
  ter dado certo enquanto todo produto genuinamente novo falha em silêncio. Foi exatamente
  o que aconteceu na primeira passada — 31 atualizações gravadas, 3 registros perdidos.

---

## [1.34.3] - 2026-08-29

### Corrigido

- **A reorganização da v1.34.2 separava madeira bruta de serrada, e não devia.** Elas são
  o mesmo produto em dois estágios de processamento, e o dashboard **já tem um eixo para
  isso**: Engenharia de Atributos → Nível de industrialização, onde o pesquisador
  classifica cada código e depois filtra. Criar `madeira_em_tora` e `madeira_serrada`
  duplicaria no catálogo um eixo vivo — exatamente o motivo pelo qual extração e
  silvicultura compartilham agrupamento (lá é o eixo `origem` que separa).

  O script passa a produzir **três** agrupamentos, não quatro: `madeira` (bruta + serrada),
  `lenha` e `carvao_vegetal`. E fica muito mais cirúrgico — **34 ações em vez de 141**,
  porque os 105 códigos que já estavam em `madeira` simplesmente ficam onde estão.

  Lenha e carvão continuam separados, e por um motivo diferente: não são estágios de
  processamento da madeira, são produtos distintos que o IBGE conta em separado e que a
  nomenclatura mantém em posições próprias. Carvão nem sequer é medido na mesma unidade
  (toneladas contra m³) — o que torna somá-lo com madeira em tora sem sentido, e não
  apenas grosseiro.

### Uma medição minha estava errada

Ao avaliar se o eixo de industrialização daria conta da separação, respondi que **nenhum**
dos 136 códigos estava classificado. Estava errado: **todos os 136 estão**. A consulta
juntava as duas tabelas por `source`, sem eu notar que elas usam convenções diferentes
(`comex` contra `mdic_comex`) — o join não casava nada e eu li o vazio como ausência de
dado.

Refeita, ela mostra que a classificação já faz precisamente a separação que eu ia
duplicar: 4403 (madeira em bruto) inteiramente como `commodity_acondicionada`, 4407
(serrada) como `commodity_consumivel`/`commodity_pura`.

Nada foi escrito em produção sob o desenho errado — a aplicação do script depende de um
humano, e isso é o que deu tempo de corrigir antes.

---

## [1.34.2] - 2026-08-29

### Adicionado

- **`scripts/reorganize_madeira_agrupamento.py`** — o agrupamento `madeira` acumulava
  **136 códigos** de três bancos, e produtos descorrelacionados dentro dele. Medido, eles
  caem em quatro posições SH4 que a própria nomenclatura aduaneira mantém separadas
  (conferido contra as descrições em `gold_comex_flows`, não de memória):

  | destino | membros | o que é |
  |---|---|---|
  | `madeira_serrada` | 60 | madeira processada (SH 4407) |
  | `madeira_em_tora` | 48 | madeira em bruto (4403) + PEVS tora e pinheiro |
  | `lenha` | 24 | lenha, estilhas, partículas, resíduos (4401) + PEVS lenha |
  | `carvao_vegetal` | 9 | carvão vegetal (4402) + PEVS carvão |

  A reorganização também resolve duas coisas de uma vez: dissolve os agrupamentos
  **degenerados** `3433` e `3434` (um membro só, id igual ao código — carvão e lenha nunca
  tiveram grupo de verdade, nem na extração) e **registra os três códigos da silvicultura**
  (3455/3456/3457), que subiram na v1.34.0 sem agrupamento nenhum e por isso ficavam
  invisíveis às perspectivas multi-fonte.

  Extração e plantio compartilham cada agrupamento por decisão do projeto: o eixo `origem`
  já os separa no menu de filtros, então o catálogo não precisa duplicá-los.

  O script roda em **ensaio por padrão** e escreve no log append-only da Curadoria, onde
  cada edição é uma linha nova com latest-wins — auditável e reversível, nada é apagado.

### Testes

- **Os quatro eixos server-side sem teste de fio ganharam um.** `flow` e `origem` tinham;
  `customs`, `market`, `reporters` e `partners` não. **Não presumi que funcionavam** —
  dirigi a API de produção e os quatro estavam corretos (flow: 5.319 + 139 = 5.458 exato;
  reporters sem parâmetro = `BRA` explícito = 4.982, `__all__` = 56.440). Então isto não
  conserta bug: fecha o buraco que deixou o `origem` subir quebrado com 1031 testes verdes.

  Cada caso prende as duas metades do contrato que nenhuma tela revela — o parâmetro tem
  de ir na **requisição** e entrar na **chave de cache** —, e há um caso extra para o
  sentinela `__all__` do reporter, que é tri-estado: tratá-lo como "sem filtro" devolveria
  o Brasil sob o rótulo "Mundo".

  Escritos como tabela, para o próximo eixo custar uma linha e não uma cópia. Validados por
  injeção nos quatro.

---

## [1.34.1] - 2026-08-29

O eixo `origem` chegava ao rótulo e não ao dado.

### Corrigido

- **Escolher uma metade da PEVS reetiquetava o painel sem mudar um número.** O chip dizia
  "Extração vegetal (nativa)", a citação ABNT declarava a metade, o CSV trazia a coluna —
  e a requisição do snapshot **nunca carregava o parâmetro**. São Paulo continuava com os
  mesmos R$ 5,79 bi sob os três rótulos, quando em extração ele é **R$ 0**.

  É o defeito de sujeito-errado que o eixo existe para impedir, produzido pelo próprio
  eixo. Faltavam três elos: o `dataStore` não tinha `activeOrigem` (nem na **chave de
  cache** — sem isso a store serviria as linhas da metade anterior sob o rótulo novo — nem
  no query string), não havia ponte `setOrigem` vinda do `summary`, e a rota
  `/api/snapshot` não lia o parâmetro. O backend abaixo dela já estava correto: consultado
  direto, `origem=extrativa` sempre devolveu SP = 0.

- A rota ganhou `_origem_or_400`: uma metade inválida agora dá 400 em vez de casar zero
  linhas e desenhar um dashboard vazio que parece "sem dados para esta seleção".

### O que isso ensina

**Os 1031 testes de frontend passavam com a feature quebrada de ponta a ponta.** Cada
unidade estava certa — o resolvedor do chip, o fragmento da citação, a coluna do CSV, o
seam, o SQL — e o fio entre elas não existia. É a mesma lição da v1.33.28, quando apagar a
ligação no `main.jsx` deixou 1012 testes verdes: **testar a unidade não testa o fio.**

O novo caso em `dataStore.test.js` fecha exatamente isso, e prende as duas metades do
contrato que nenhuma tela revela: o parâmetro tem de ir na requisição **e** entrar na chave
de cache. Validado por injeção nas duas. Do lado do servidor, dois casos em
`test_webapi_routes.py` prendem o elo que faltava — o eixo chega ao seam, e `all` fica de
fora do summary para que uma requisição sem recorte siga byte-idêntica à de antes.

Encontrado dirigindo a interface real contra a Gold de produção — não por leitura.

---

## [1.34.0] - 2026-08-29

A PEVS passa a ter as **duas metades**. A pesquisa do IBGE se chama "Produção da Extração
Vegetal **e da** Silvicultura" e o projeto ingeria uma: a extração de floresta nativa
(SIDRA t289). A silvicultura — floresta plantada, t291 — chegou.

Isso começou com um pesquisador perguntando por que São Paulo e Rio de Janeiro não têm
dados. Não tinham porque quase não há extrativismo lá: a produção florestal desses
estados é plantada. A v1.33.32 corrigiu a **descrição** encolhendo a promessa; esta
versão a cumpre.

### Adicionado

- **Ingestão da SIDRA t291** (`embrapa ingest ibge-silvicultura`) — pipeline irmão do da
  PAM, mesmo cliente SIDRA, delta por padrão, raw zone própria (`raw/ibge/silvicultura/`),
  Bronze própria (`sidra_t291_raw`). Entra no lote semanal junto com a extração, porque as
  duas metades são publicadas juntas: uma atrasada em relação à outra deixaria o eixo
  `origem` fora de passo consigo mesmo.

- **A coluna `origem`** em `gold_pevs_production` — `extrativa` | `silvicultura`, nunca
  nula. Dois modelos Silver convergindo numa Gold; sem filtro, os números somam as duas,
  que é o total da própria pesquisa.

- **`origem` como eixo de filtro de primeira classe** — seletor no menu, chip na barra,
  fragmento na referência ABNT, coluna no CSV e parâmetro `or` no permalink. Essa parte
  não é ornamento: a metade plantada vale ~5× a nativa, então um total que as mistura
  **sem dizer** seria o defeito das v1.33.25–32 construído de propósito.

### O que NÃO mudou

Filtrar `origem = extrativa` reproduz a Gold anterior **linha por linha** — 1.075.438
linhas, o mesmo número de antes. O teste de conservação Silver→Gold passou a rodar por
metade, o que o torna duas verificações independentes em vez de uma, e é ele que prende
essa promessa.

### Números

Medidos, não estimados. O modelo do plano previa ≈ 870.000 linhas e a carga trouxe
**869.778**. Gold vai de 1,08 M para 1,35 M linhas.

| | Brasil 2023 | São Paulo 2023 |
|---|---|---|
| extrativa | R$ 5,03 bi | **R$ 0** |
| silvicultura | R$ 31,16 bi | **R$ 4,15 bi** |

São Paulo era o caso que motivou a pergunta e é o que a prova: zero na extração,
R$ 4,15 bi na silvicultura. Conferido contra o SIDRA célula a célula (madeira em tora
R$ 3.651,5 mi · lenha R$ 369,1 mi · carvão R$ 127,9 mi).

Custo: ~R$ 0,20/mês — armazenamento ~R$ 0,11, Cloud Run ~R$ 0,07, e consulta R$ 0 porque
os +10 GB/mês cabem na franquia de 1 TiB.

### Corrigido no caminho

- **Dois critérios de aceite do plano estavam errados** e foram corrigidos com o medido:
  SP 2023 é R$ 4,15 bi (não 4,45) e Brasil R$ 31,16 bi (não 31,7). Ambos os originais
  eram os totais da tabela inteira, incluindo os "outros produtos" (acácia-negra, resina)
  que o escopo exclui. Foi a ingestão que revelou — o critério funcionou justamente por
  apontar para a fonte, e não para a nossa própria saída.

- **O teste da v1.33.32 foi invertido, não remendado.** Ele exigia que a descrição
  dissesse que a silvicultura estava fora; agora exige que ela nomeie as duas metades e o
  eixo. Ele falhou no momento exato em que devia falhar.

- **`assert_pevs_conserved_silver_to_gold`** passou a reconciliar por `origem`;
  **`_check_bronze_tables`** deixou de contar alvos na mão e passou a derivá-los do
  registro; e o doctor ganhou dois probes novos (alcance da t291 e paridade das vars
  142/143 entre `config.py` e `dbt_project.yml`).

### Testes

- **`assert_pevs_silvers_column_identical`** — a união na Gold é **posicional**
  (`select 'x' as origem, * from …` duas vezes). É a forma certa aqui, já que um modelo é
  espelho literal do outro, mas ela falha do pior jeito possível se os dois divergirem:
  uma coluna a mais em um deles desloca todos os campos seguintes, os valores caem na
  coluna errada, **o build continua verde** e os números ficam errados dali em diante.
  O teste compara nome, posição e tipo — os três, porque qualquer um deles basta para
  desalinhar.

1607 Python + 1031 frontend, cobertura do patch 97%. Validados por injeção: trocar os rótulos de `origem` na
união da Gold; retirar o eixo da citação, do CSV e do schema de filtros; deixar a coluna
do CSV vazia; acrescentar uma coluna a uma das Silvers. Um teste novo prende o eixo em **todos** os leitores de produção — um
recorte que chega ao KPI e não ao mapa faria as duas metades da tela discordarem sobre o
que descrevem.

---

## [1.33.32] - 2026-08-28

Um pesquisador reparou que São Paulo e Rio de Janeiro não têm dados no IBGE PEVS e
perguntou se estava certo. **O dado está certo; a descrição do banco é que estava
errada** — e era ela que fazia o vazio parecer defeito.

### O que foi medido

- SP e RJ **têm** linhas na Gold (SP: 39.634, R$ 132,1 mi; RJ: 4.011, R$ 10,5 mi), com os
  7 produtos e 1986–2024. O que zerou foi o **valor recente**: SP tinha 119 municípios
  com produção em 2007 e nenhum desde 2015.
- Confrontado com a fonte: o **próprio SIDRA t289 devolve `-`** para SP em carvão
  vegetal, lenha, madeira em tora e pinheiro brasileiro em 2023. Nosso zero é fiel.
- SP não está ausente da PEVS: tem R$ 5,85 mi em 2023, todos em **palmito e pinhão** —
  produtos fora do recorte de 9 commodities deste projeto.

### Corrigido

- **A descrição do banco prometia a metade que não ingerimos.** A PEVS do IBGE tem duas
  metades: extração vegetal (floresta nativa, tabela SIDRA **289**) e silvicultura
  (floresta plantada, tabela 291). Ingerimos só a primeira. As duas cópias do registro —
  SPA e backend — diziam *"do extrativismo vegetal **e da silvicultura**"* e
  *"recursos florestais, **nativos e plantados**"*, e o hint do filtro de produtos
  repetia. Nada disso é verdade sobre o que o banco contém.

  A diferença não é marginal. Em 2023, no Brasil: a metade que temos vale **R$ 6,2 bi**;
  a que não temos, **R$ 31,7 bi**. Só São Paulo produz **R$ 4,45 bi/ano** de madeira em
  tora, lenha e carvão — exatamente os produtos que rastreamos — mas de floresta
  plantada. O Gold inteiro de SP, 39 anos, é R$ 132 mi.

  O **nome** da pesquisa continua como é ("Produção da Extração Vegetal e da
  Silvicultura" é nome próprio, e a citação ABNT precisa dele). O que mudou foi a
  descrição de cobertura, que agora diz qual metade está aqui, qual ficou de fora, e
  usa São Paulo como o exemplo que explica o vazio — porque é exatamente onde o leitor
  tropeça.

### Testes

Um arquivo novo prende a afirmação ao mecanismo que a decide, `IBGE_TABLE_ID`: enquanto
ele for 289, nenhuma das duas cópias pode descrever a silvicultura como incluída — e
ambas **precisam** dizer que ela está fora, para que uma reescrita futura que largue a
ressalva falhe aqui em vez de falhar num pesquisador. O bare "silvicultura" não é
proibido: ele está no nome da pesquisa, que fica.

4 casos, validados por injeção — reintroduzir a promessa em cada cópia derruba a sua;
apagar a ressalva derruba outra; devolver o hint antigo derruba a quarta.

---

## [1.33.31] - 2026-08-28

O check de heartbeat — construído na v1.31.0 para responder *"o gatilho disparou?"* —
tinha o mesmo defeito que passei a semana varrendo, e não podia ver o caso mais provável
hoje.

### Corrigido

- **`Ingest heartbeat` dizia `every scheduled ingest ran` listando UMA fonte.** A linha
  nomeava o todo sobre o subconjunto que reportou: sete fontes têm gatilho, uma tinha
  registro, e as outras seis eram silenciosamente descartadas do cálculo *e* da frase.
  É exatamente o padrão das v1.33.25/27/28 — um rótulo que nomeia mais do que o número
  mede — desta vez no código que existe para detectar silêncio.

- **A isenção de "nunca reportou" nunca expirava.** O docstring dizia, de propósito, que
  uma fonte ausente da tabela não é acusada, "porque a tabela só começa a encher depois
  que isto entrar no ar". Razoável no dia 1 — mas sem prazo, o que ela cria é um ponto
  cego permanente: **"o gatilho nasceu quebrado e jamais disparou uma vez" ficou
  indistinguível de "ainda não chegou a hora", para sempre.**

  E esse é precisamente o estado de hoje: `embrapa-ingest-all-weekly`, que substituiu o
  disparo noturno em 2026-08-28, tem `LAST_ATTEMPT` **vazio** — nunca executou, e só
  dispara às segundas. Se tiver nascido malconfigurado, a ingestão para em silêncio e o
  guarda-chuva que escrevi para exatamente isso responderia "todas rodaram".

  A isenção passa a valer só enquanto significa alguma coisa: até a **própria tabela de
  heartbeat** ter existido mais tempo que a janela daquela fonte. Antes disso, silêncio
  não diz nada (a tabela nasce vazia, e gritar no dia 1 é como um check vira ignorado);
  depois, silêncio é o sinal mais alto que existe. A referência é a data de criação da
  tabela — o mecanismo, não um palpite.

- **"Parou de rodar" e "nunca rodou" deixam de virar uma palavra só.** São diagnósticos
  diferentes e consertos diferentes: um manda olhar as execuções do Job, o outro manda
  olhar como o scheduler foi criado.

A frase de sucesso passa a prestar contas de todas as fontes — as que rodaram, com a
idade, e as que ainda não têm primeiro registro mas seguem dentro da janela.

### Testes

Três casos novos (1578 no total), validados por injeção: voltar a isentar quem nunca
reportou derruba os dois casos novos; voltar a dizer "every" sobre o subconjunto, 1;
fundir "parou" e "nunca" numa palavra só, 1.

Um teste existente mudou de premissa e foi reescrito em vez de remendado: ele afirmava
que uma fonte nunca observada é **ignorada**. Ela não é mais — é nomeada. Ignorá-la era
metade do defeito.

---

## [1.33.30] - 2026-08-28

### Testes

- **O flake do `ViewCadastroProdutos` passa a dizer o que viu.** O teste
  "shows the existing manual descrição pre-filled…" falhou duas vezes — no CI, num PR
  só de documentação, e uma vez na suíte completa local — e passa em todo o resto.

  **Não foi possível reproduzi-lo.** Cada hipótese foi descartada por medição, não por
  opinião: estouro de prazo do `waitFor` (todas as esperas do arquivo passam com
  `timeout: 1` — nada ali precisa de relógio, então o modo de falha não é "tarde");
  chamadas de `fetch` atravessando a fronteira entre testes (instrumentado no
  `afterEach`: nenhuma); dependência de ordem (`--sequence.shuffle`, 3×); o modo
  `--coverage` que o CI usa e que eu não estava usando (3×); CPU saturada com 24
  processos de carga, com o arquivo sozinho e com a suíte inteira; e uma closure
  obsoleta no `onBlur` — construída de propósito, disparando `change` e `blur` dentro
  do mesmo `act` sem re-render entre eles, e o POST sai correto assim mesmo.

  Sem mecanismo identificado, inventar um conserto seria fingir diagnóstico. O que
  sobra com valor real é a próxima falha não custar outra hora: `Timed out in waitFor`
  não distingue "a linha não chegou" de "o campo veio vazio" de "o POST saiu para a
  URL errada", e essa distinção **é** o diagnóstico. As duas esperas do campo passam a
  reportar, no erro, o estado da tela: quantas linhas a tabela tinha, se o campo
  existia, seu valor, se estava desabilitado, e a lista de chamadas de API feitas até
  ali.

  Validado por injeção — remover a nota salva do fixture acusa
  `"O campo … nunca chegou com a nota salva" · campoValor: ""`; fazer o blur não salvar
  acusa `"O blur não disparou o salvamento" · campoValor: "Nota atualizada"`, que já
  separa "a digitação falhou" de "o salvamento falhou". Uma terceira injeção (campo
  desabilitado) **não** derrubou o teste — o `fireEvent.change` do jsdom ignora o
  `disabled` —, então a asserção que eu havia escrito para guardá-la foi removida em vez
  de ficar no arquivo sem provar nada.

---

## [1.33.29] - 2026-08-28

Dois fechamentos da varredura da v1.33.28 — a mesma classe no **eixo comércio**, e a
parte que ficou faltando pela régua que eu mesmo escrevi.

### Corrigido

- **A citação ABNT ignorava o eixo comércio.** A lista de escopo da referência tinha
  quatro itens: produtos, território, qualidade, faixa de valor. Para um banco de
  comércio o recorte é definido por **fluxo, regime, mercado, reporter e parceiro**, e
  nenhum dos cinco entrava. Um painel COMTRADE **Brasil → China** saía citado como
  `Produtos: Todos (89). Território: Não se aplica.` — ao lado de um permalink com
  `rp=BRA&pt=CHN`. A prosa contradizia o próprio link, agora por omissão.

  Agora sai `Reporter: Brasil. Parceiro: China.` Segue a regra que a lista já aplicava
  a qualidade e faixa de valor: declara o que **define ou restringe**, cala sobre o que
  está em "todos".

  Os cinco resolvedores viviam inline no `FilterTriggerBar`, então só o chip conseguia
  nomeá-los. Foram extraídos para `scopeChips.js` — o chip e a citação leem o **mesmo**
  resolvedor, pelo mesmo motivo que o `filterSummary.js` existe.

- **"Território: Não se aplica" era uma afirmação, e ela errava nos dois sentidos.**
  Num banco sem geografia virava ruído ao lado de um par de países; num banco ainda
  carregando transformava um estado transitório em fato sobre o banco (o COMEX, que
  tem geografia, era citado assim durante o carregamento). O chip passa a publicar a
  própria bandeira de aplicabilidade junto com o texto, e a referência cala quando a
  dimensão não se aplica — ou ainda não se sabe.

- **O recorte sub-UF agora aparece onde o número está.** A v1.33.28 o levou ao chip, à
  citação e ao CSV — todos fora do corpo da página. Pela régua registrada ali, isso não
  bastava: um leitor olhando o mapa lê o mapa. O seam passa a expor o recorte nomeado, e
  ele aparece em duas superfícies novas — uma nota acima dos cartões territoriais
  (Visão geral, Geografia, Concentração, num único componente para as três não
  divergirem) e uma terceira linha no popup do mapa de UF, que é onde o número de **um**
  estado é lido sozinho.

### Testes

12 casos novos (1025 no total). Validados por injeção: citação voltar a ignorar o
comércio derruba 3; declarar também o que não restringe, 2; voltar a afirmar território
sempre, 1; parceiro completo contando como recorte, 1; seam parar de expor o recorte, 1;
popup parar de exibi-lo, 1.

Três harnesses passaram a importar o módulo real em vez de stub — o resolvedor de
comércio, o `chipFmt` e o `RecorteNote` —, porque um stub ali deixaria o teste e o
produto concordando por acidente.

Conferido no navegador contra o BigQuery de produção: COMTRADE Brasil→China cita
`Reporter: Brasil. Parceiro: China.` sem território fantasma; COMEX com fluxo restrito
cita `Fluxo: Exportação. Território: Brasil · 27 UFs.`; PEVS com o Marajó ativo mostra a
nota nas três views e nenhuma sem recorte.

---

## [1.33.28] - 2026-08-28

Varredura atrás da classe de defeito da v1.33.27 — **um agregado que leva o nome do
todo mas é calculado sobre um subconjunto filtrado**. Encontrado um caso, mais grave
que o original porque sai do produto.

### Corrigido

- **Um recorte sub-UF ficava invisível fora da Geografia.** As quatro facetas agregadas
  (mesorregião, microrregião, região intermediária, região imediata) estreitam os dados
  **sem tirar nenhuma UF da seleção** — então toda contagem que os resumos de filtro
  recebem continua no total, e eles respondiam com o país inteiro. Filtrando a
  mesorregião do **Marajó** (16 municípios do Pará), o chip do cabeçalho anunciava
  `Brasil · 27 UFs` enquanto o mapa pintava `PA = 655 mi` — sendo que o Pará inteiro
  naquele ano é R$ 2,91 bi. A palavra "Marajó" não aparecia em lugar nenhum da tela.

- **A citação ABNT repetia isso.** A referência de "consulta detalhada" — a que se
  propõe a descrever o recorte exato, e cujo comentário no código diz explicitamente que
  ela deve *"never over-claim a filtered panel as if it were the full dataset"* — saía
  como `UFs: Brasil · 27 UFs`, **ao lado de um permalink que carregava `me=1502`**. A
  referência contradizia o próprio link. Um pesquisador publicaria um método falso.

  Agora sai `Território: Marajó (PA)`. O prefixo mudou de "UFs" para "Território"
  porque uma mesorregião não é uma UF — consertar o valor e deixar o rótulo errado
  seria só mudar o defeito de lugar.

- **O CSV não levava o recorte.** Um arquivo baixado sai do produto para sempre: não
  tem chip, nem permalink, nem trilha ao lado. A tabela de distribuição geográfica
  trazia `PA` com o valor do Marajó e nada mais. Passa a carregar a coluna
  `recorte_geografico`, irmã da `escopo_produto` que já viajava junto — e ela diz
  `sem recorte sub-UF` por extenso quando não há, porque célula vazia é ambígua.

### Sobre a causa

A regra já existia e estava certa: `geoDrill.subUfLabel` (v1.33.1) descreve o recorte
*"never wider than it is"*, e o FilterMenu já tinha um `subUfNarrowing` alimentando um
selo "recorte ativo" para que recolher o painel *"never hides an active narrowing
silently"*. A regra foi aplicada à trilha territorial e ao selo, e **nunca propagada às
duas superfícies que saem da tela** — o chip e a citação. As três chamadas de
`geoChipText`/`geoHeaderText` simplesmente nunca mencionavam as facetas.

### Testes

15 casos novos. Validados por injeção: tirar a guarda do chip derruba 2; a da linha do
menu, 2; omitir a UF no recorte, 2; inventar uma UF para código órfão, 1; tirar a coluna
do CSV, 7; deixá-la vazia, 3.

Um deles precisou de instrumento novo. Apagar a ligação no `main.jsx` — exatamente onde
o defeito morava — deixava **os 1012 testes verdes**: as funções puras estavam travadas,
o fio que as alimenta não. `filterSummary.wiring.test.js` varre o código e exige que
toda chamada passe o recorte; ele pega tanto a remoção no `main.jsx` quanto em uma das
duas do FilterMenu.

Conferido no navegador contra o BigQuery de produção: sem filtro → `Brasil · 27 UFs`;
duas UFs → `1 nação · 2 UFs`; mesorregião → `Marajó (PA)`, com a citação concordando
com o próprio permalink.

---

## [1.33.27] - 2026-08-28

O cartão "Soma por região" nomeava uma região inteira sobre um número que era de um
estado só — e entregava esse número como uma barra sozinha, que não informa nada.

### Corrigido

- **"Norte" sobre o valor do Pará.** `regionData` soma o `ufData` **já filtrado** mas
  mantinha o rótulo da região inteira. Filtrando um estado, o cartão escrevia "Norte"
  sobre um número que era do Pará — enquanto "Maiores estados produtores", **na mesma
  tela**, chamava aquele mesmo número de "Pará". Dois nomes, um número, e nada dizendo
  ao pesquisador qual era o sujeito. É o defeito da v1.33.25 (nome de UF sobre valor de
  região) um grão acima.

  Somar só o que está filtrado continua certo — é a regra de nunca exibir dado fora do
  filtro. O que faltava era **declarar a parcialidade**: cada linha de região passa a
  carregar quantas UFs somou, quantas somaria sem o filtro de estado, e quais são. O
  denominador sai do **mesmo caminho de dados** (mesmo ano, mesma cesta, mesmo recorte
  sub-UF) com só o filtro de UF suspenso, então "1 de 7" significa exatamente "o que
  apareceria se você limpasse o filtro" — nunca uma constante geográfica, que marcaria
  como parcial uma região cujas UFs faltantes simplesmente não existem no banco.

- **Uma barra sozinha não é um gráfico.** Comprimento de barra só significa algo contra
  outras barras; com uma só ela preenche a área por definição e o único dado real fica
  no eixo. Com uma região o cartão passa a mostrar o valor por extenso
  (`R$ 2,91 bi`, moeda como prefixo; `30 mil t`, unidade física como sufixo) com a
  composição embaixo. Com duas ou mais, as barras voltam — aí elas comparam de verdade —
  e cada região parcial leva a marca no próprio rótulo.

### Testes

10 casos novos, todos validados por injeção: desenhar a barra sozinha de novo derruba 4;
nunca marcar parcialidade, 1; tirar a marca das barras, 2; trocar o denominador do banco
por uma constante geográfica, 3; embaralhar a ordem das UFs (que faria a lista truncada
mentir), 1. O stub de `RegionBars` descartava as props — a mesma cegueira dos popups de
ontem — e agora as captura.

Conferido no navegador contra o BigQuery de produção: um estado → `R$ 2,91 bi` ·
`parcial · 1 de 7 UFs com dados em 2024 · Pará`; três estados em duas regiões → barras
com "Norte (parcial)" e "Sudeste (parcial)"; sem filtro → nada marcado.

---

## [1.33.26] - 2026-08-28

Varredura atrás de defeitos equivalentes ao da v1.33.25 — rótulo nomeando um sujeito
diferente do que o número mede. **Nenhum outro encontrado**; a mesma cegueira de teste que
o permitiu, sim.

### Verificado, sem achados

- **`regionUfRows` tem um único consumidor**, o mapa já corrigido. Os demais
  `{ ...x, [valueKey]: ... }` do projeto são escala de unidade — mesmo sujeito, não
  mistura de grão.
- **Mapa de calor**: o ramo de região agrega UFs *em* regiões e rotula pela região; o ramo
  de UF usa a série da própria UF. O comentário do ramo municipal já nomeava este perigo
  ("never the plain UF grid — the exact 'same vector at the wrong grain' problem").
- **Exportação CSV**: no modo região troca a **fonte** (`regionData`), não só o rótulo —
  exatamente o que o mapa deveria ter feito.
- **Mapa municipal** e **BrazilTileMap**: identidade e valor do mesmo sujeito.

### Testes

- **O popup do mapa municipal não tinha nenhuma asserção sobre o que escreve** — o stub
  descartava o HTML, igual ao do mapa do Brasil antes da v1.33.25. Era a mesma ausência que
  deixou o outro defeito viver semanas. O fixture passa a capturar o texto, e três casos o
  prendem: o popup nomeia o município do próprio polígono e mostra o valor **dele**; a
  invariante varrida garante que nenhum município exibe o nome de outro; e um município sem
  linha diz "sem produção registrada" em vez de um traço mudo com número atribuído.

  Validados por injeção: fazer o popup ler a linha errada acusa
  `Abel Figueiredo: mostra Abaetetuba`; trocar a mensagem por "—" derruba o terceiro.

---

## [1.33.25] - 2026-08-28

### Corrigido

- **No mapa em território Brasil, o hover nomeava o ESTADO ao lado do valor da REGIÃO.**
  Reportado com captura: sobre o Amazonas lia-se `AM · Amazonas · 3,8 bi R$`, quando
  3,8 bi é o Norte inteiro. O Amazonas sozinho são **354 mi** — o rótulo atribuía ao
  estado **10×** o que ele produz.

  A causa está no desenho, e ele é deliberado: macrorregião não tem geometria vendorizada,
  então cada UF é pintada com o total da **sua região** e os cinco blocos aparecem sobre a
  malha que já existe. Só que a linha continuava carregando a identidade da **UF** —
  `{ ...u, [valueKey]: reg[valueKey] }` — e o popup lia `name` da UF com `value` da região.

  Agora quem monta a linha declara **o que ela representa** (`displayCode`/`displayName`),
  e o popup obedece; sem essa declaração o polígono é o próprio sujeito e a identidade da
  UF continua correta. Verificado no navegador nos dois modos: Brasil mostra
  `N · Norte · 3,8 bi`, e dentro do Norte mostra `AM · Amazonas · 354 mi`.

### Testes

- **O popup não era testável**: o `FakeMap` do teste descartava os handlers de camada, então
  nada guardava o texto do hover — que é justamente onde a identidade aparece. O fixture
  passa a registrar handlers por `evento:camada` e a capturar o HTML do popup.
- Invariante: **nenhuma linha com identidade declarada pode exibir o nome do polígono**,
  varrida sobre as cinco regiões com uma UF de cada. Mais os dois casos diretos (região
  nomeia a região; UF sem declaração nomeia a UF). Validada por injeção — repor a leitura
  antiga faz a varredura acusar `AM · Amazonas`.

---

## [1.33.24] - 2026-08-28

### Documentação

Varredura dos arquivos que descreviam a infraestrutura mudada hoje. **Nove arquivos** ainda
diziam "nightly" ou citavam configurações que deixaram de existir.

- **`.env.example` não tinha três configurações novas** — `BQ_HEARTBEAT_TABLE`,
  `HEARTBEAT_SLACK_DAYS` e `SOURCE_FRESHNESS_ANNUAL_SLACK_YEARS`. Quem copiasse o exemplo
  para montar um `.env` não saberia que existem. Acrescentadas com o porquê de cada padrão.
- **`docs/adding_a_data_source.md`** mostrava o molde do `IngestSpec` **sem** `cadence_days`.
  Uma fonte nova herdaria 7 em silêncio e o check de batimento usaria a janela errada. O
  molde agora inclui o campo, com a nota de que ele e o cron do script de agendamento são
  presos por teste — então se alteram juntos.
- **`deploy/ingestion/README.md`** chamava o gatilho de nightly em quatro pontos, não listava
  o `schedule_currency.sh` e descrevia o `schedule_pam.sh` como "manual scheduler" (é
  mensal). Ganhou também o parágrafo que faltava: o alerta vê rodada que **falha**, e quem
  cobre a rodada verde-sem-dado são os dois checks do `doctor`.
- **`ARCHITECTURE.md`**, **`CLAUDE.md`**, **`README.md`**, **`docs/comtrade_world_backfill.md`**
  e a **skill `ingest-data`** descreviam o lote como noturno. Corrigidos — a menção que
  sobrou no `ARCHITECTURE.md` é histórica e explícita ("nightly until 2026-08-28").
### Corrigido

- **Teste instável no `ViewCadastroProdutos`.** Dois casos esperavam a **tabela** aparecer
  (`.dt-table`) e em seguida liam o `value` de um **input** — que é populado um tick depois.
  Passa sempre localmente e falhou sob carga no CI. As esperas passam a ser gatilhadas no
  próprio campo que o teste afirma, que é estritamente mais preciso do que esperar o
  contêiner. **Não provado por injeção**: a corrida não reproduz fora da carga do CI, então
  a correção vem do mecanismo, não de uma falha reproduzida.

### Documentação (continuação)

- **`docs/operations_runbook.md` descrevia duas configurações que eu mesmo removi**
  (`HEARTBEAT_DAILY_SLACK_DAYS` / `HEARTBEAT_MONTHLY_SLACK_DAYS`), substituídas na v1.33.20
  por `cadence_days` + `HEARTBEAT_SLACK_DAYS`. Eu escrevi aquele trecho na v1.33.19 e o
  deixei vencer quatro PRs depois, no mesmo dia — exatamente o modo de falha que passei o
  dia documentando.

---

## [1.33.23] - 2026-08-28

### Documentação

- **Medido: 70–83% do Bronze é peso morto**, e é isso que os modelos incrementais varrem.
  Com a chave natural de cada modelo: `bronze_ibge.sidra_t289_raw` tem **82,8%** de linhas
  superadas (21,1M contra 4,4M vivas) e `bronze_pam.sidra_t5457_raw`, **69,9%** (39,1M
  contra 16,9M). O Bronze é append-only por desenho e o `reconcile` mensal re-ingere a
  história inteira, então as cópias se acumulam — e o `qualify` do Silver descarta ~5 de
  cada 6 linhas que leu.

  Podar as superadas cortaria a varredura desses modelos ~5× **sem tocar no contrato do
  `>=`** documentado na v1.33.22 — alavanca maior e mais segura que apertar o limite.
  Registrado, não feito: é operação com backup antes e aval humano (o Bronze é o pouso
  consultável; a raw zone no GCS guarda a cópia de proveniência), e rende ~US$ 0,16/mês.

### Levantamento de custos — nada a fazer

Medido hoje, o projeto inteiro custa da ordem de **US$ 1/mês**:

| item | medido | custo/mês |
|---|---|---|
| BigQuery consulta | ~157 GB | **zero** — 15% da cota grátis de 1 TiB |
| BigQuery armazenamento | 22,45 GB | ~US$ 0,25 (10 GB grátis) |
| GCS | 7 GB, ciclo de vida completo até Delete em 365d | centavos |
| Artifact Registry | 40 MB, 8 versões — não acumula | ~zero |
| Cloud Run Service | `min-instances=0`, escala a zero | por uso |
| Cloud Run Job | execuções curtas (câmbio: 10,6s) | por uso |
| Cloud Scheduler | 7 gatilhos (3 grátis) | ~US$ 0,40 |

A maior linha identificável é o **Cloud Scheduler**, com US$ 0,40. A regra de
escala-a-zero do projeto já tinha feito o trabalho: não há infraestrutura de custo fixo, e
o resto é proporcional ao uso e minúsculo.

---

## [1.33.22] - 2026-08-28

### Documentação

- **Os dois modelos incrementais mais caros não são incrementais na prática — e o
  comentário deles afirmava o contrário.** `silver_ibge_pevs` dizia que o re-scan do limite
  é *"bounded: only the year(s) tied at the max timestamp re-run, **not the full
  history**"*. Medido em 2026-08-28: `affected_years` devolve **os 39 anos (1986–2024) em
  todo build**, e os bytes faturados são **planos** — 3,22 GB/build por 13 dias seguidos,
  depois 3,88 GB/build por mais 9. Isso é a assinatura de reconstrução completa, não de
  build incremental. `silver_ibge_pam` tem o mesmo padrão (~3,1 GB/build).

  A causa: o limite é `ingestion_timestamp >= max(Silver)`, e o lote que está **em cima**
  do limite continua qualificando até chegar algo mais novo. Duas coisas tornam esse lote
  grande e duradouro aqui — o `reconcile` mensal re-ingere a história inteira por desenho,
  e o próprio PEVS só escreve em Bronze ~2 dias por mês. Um lote de história inteira fica
  semanas no limite, e todo build no intervalo o refaz.

  **Não corrigido, de propósito.** O `>=` é o que impede um append de mesmo segundo de ser
  pulado para sempre; apertá-lo exige um argumento de corretude diferente, não um operador
  diferente — uma comparação por ano entre Bronze e Silver (máximo de `ingestion_timestamp`
  **e** contagem de linhas, para o caso de mesmo segundo seguir coberto) resolveria. Não
  vale o risco hoje: o projeto está em ~15% da cota grátis de 1 TiB/mês do BigQuery, então
  isso custa **zero**. Os dois modelos são ~36% dos bytes do build e cairiam para perto de
  nada — é o primeiro alvo se a conta um dia sair do gratuito.

  Nenhuma linha de SQL executável mudou: só os cabeçalhos, agora com a medição.

### Nota sobre a análise que gerou isto

A pergunta era "e se o build for a cada 15 dias?". A resposta medida foi **não**: os três
cenários (diário 52%, 2×/semana 15%, quinzenal 4%) cabem na cota grátis, então a economia é
**zero em dinheiro** — e o custo seria real, porque PAM e PPM pousam nos dias 2 e 3 e
esperariam 14 e 13 dias para aparecer, justamente as fontes que carregam a publicação anual
do IBGE.

Ao investigar a alternativa, minha primeira hipótese (falta de poda de partição na consulta
de descoberta) estava **errada**: medida, ela custa 380 MB e cairia para 61 MB — ~2% do
build, não 36%. O tamanho do prêmio que eu estimara estava certo; o mecanismo, não.

---

## [1.33.21] - 2026-08-28

### Corrigido

- **A mudança de cadência da v1.33.20 teria feito o `dbt source freshness` avisar todo
  dia.** `bronze_ibge.sidra_raw` (PEVS) e `bronze_bcb.inflation_raw` carregavam
  `warn_after: 2d / error_after: 7d` com o comentário "Nightly delta ingest" — correto até
  o lote virar semanal. A partir daí 2 dias tripariam em quase todo dia saudável, e 7 dias
  errariam pouco antes de cada rodada normal. Passam a **10d / 17d** (uma rodada perdida
  avisa, duas erram).

  `bronze_bcb.currency_raw` **fica em 2d/7d**: é a única fonte que segue diária, e 2 dias
  cobrem um fim de semana. `bronze_comex` já estava em 30/60 por desenho próprio (o ETag
  faz o `ingestion_timestamp` rastrear **dado**, não pipeline) e não foi tocado.

  Pego antes de disparar: o workflow roda às 08:00 BRT e a mudança foi à noite.

- **Comentários diziam que PAM, PPM e COMTRADE são atualizados "MANUALMENTE".** Não são —
  têm gatilho mensal próprio, ativo e disparando (verificado hoje). Os comentários
  precederam esses gatilhos. Corrigidos, e agora apontam que **saúde de gatilho é o check
  de batimento do `doctor`**, não a janela de frescor — que por isso pode seguir warn-only.

### Testes

- **`tests/test_source_freshness_matches_cadence.py`**: a janela de frescor de cada fonte
  tem de caber na cadência com que o agendador realmente dispara — `warn_after` maior que a
  cadência, e `error_after`, **quando existe**, maior que um ciclo inteiro perdido.

  O `error_after` é opcional **de propósito**, e minha primeira versão do teste exigia-o,
  reprovando PAM/PPM/COMTRADE. Fui ler: o warn-only ali é decisão registrada. Ajustei a
  regra ao desenho, não o desenho à regra. COMEX e COMTRADE ficam isentos da comparação com
  cadência, com o motivo escrito. Validado por injeção (repor 2d/7d no PEVS acusa).

---

## [1.33.20] - 2026-08-28

Reorganização das cadências, guiada por medição — e não pela intuição de que "diário é
caro". A intuição estava certa no diagnóstico e errada no alvo.

### Alterado

- **O build do dbt passa de diário para 2×/semana (seg e qui).** É aqui que está o
  dinheiro: medido em 7 dias parados, `sa-dbt-build-ci` faturou **121,3 GB** contra
  **1,3 GB** de toda a ingestão — **98,9% do custo**. E a maior parte disso reconstruía
  entradas idênticas, porque as fontes não-câmbio avançam mensal ou anualmente e o câmbio
  entra no Gold como **média anual** (`val_yearfx_* = val_raw / brl_per_usd_avg`), de modo
  que um dia a mais de PTAX mal move o número exibido. Duas vezes por semana e não uma
  porque os gatilhos mensais caem em **dias fixos do mês** (PAM 2, PPM 3, COMTRADE 15),
  que caem em qualquer dia da semana: com seg+qui, dado fora do ciclo espera no máximo
  3–4 dias; com segunda apenas, esperaria 6.
- **O lote de ingestão passa de diário para semanal** (`embrapa-ingest-all-weekly`,
  segunda 05:00 BRT), e **o câmbio ganha gatilho diário próprio**
  (`embrapa-ingest-all-currency-daily`, `make ingest-job-currency-schedule`). Medido em 30
  dias de sondagem diária, o avanço real da referência: câmbio **22×** (dias úteis),
  inflação **2×**, COMEX escreveu em 3 dias, PEVS em 2. Ou seja: três das quatro fontes do
  lote eram sondadas ~15× mais do que publicam.

  A economia dessa parte é ~1% — ingestão nunca foi o custo. O motivo é parar de pedir a
  quatro APIs dado que três delas só publicam mensal ou anualmente.

  O agendador `-nightly` foi **pausado**, não removido: apagar agendador é bloqueado para
  o agente por hook do projeto. Removê-lo de vez é um passo humano.

- **`IngestSpec` ganha `cadence_days`.** A janela do check de batimento era derivada de
  `in_all` — "no lote ⇒ diário" — o que deixou de ser verdade no instante em que o lote
  virou semanal, e teria feito o check acusar PEVS, inflação e COMEX toda semana. Agora
  cada fonte declara a sua cadência (câmbio 1, lote 7, mensais 31) e o `doctor` soma
  `HEARTBEAT_SLACK_DAYS` (padrão 3), substituindo as duas folgas anteriores por uma.

### Testes

- **`tests/test_ingest_cadence_matches_schedulers.py`**: a `cadence_days` declarada tem de
  bater com o cron do script que cria o gatilho — parseando `deploy/ingestion/schedule*.sh`.
  Uma fonte pode ter **mais de um** gatilho (o câmbio tem o próprio diário **e** anda no
  lote semanal), então o esperado é o **menor** intervalo: tomar o do lote deixaria o
  câmbio ficar 7 dias no escuro antes de alguém reclamar. Validado por injeção. Mais uma
  invariante de que toda fonte é coberta por algum agendador.

### Verificado em produção

O gatilho novo de câmbio foi disparado e conferido: **330 linhas** em `bcb_cambio` e
**zero** em inflação e COMEX — escopo correto. E ele produziu o **primeiro batimento real**
(`bcb-currency · ok · 10,6s`), provando a feature da v1.33.19 ponta a ponta em prod.

---

## [1.33.19] - 2026-08-28

### Adicionado

- **Batimento de ingestão — o ponto cego fecha.** Toda rodada de ingestão passa a gravar
  uma linha em `research_inputs.ingestion_heartbeat` (fonte, timestamp, desfecho, duração)
  **tenha ou não tido o que ingerir**. Com isso os três estados finalmente se separam:

  | o que se vê | o que significa |
  |---|---|
  | nenhuma linha na janela da fonte | o **gatilho** não disparou |
  | linha `ok`, dado inalterado | rodou e a fonte não tinha nada — o silêncio saudável |
  | linha `failed` | rodou e quebrou (o alerta também dispara) |

  Nem o alerta nem o Bronze respondiam isso: o alerta vê execução que **falha**, e o delta
  **não escreve nada** quando não há dado novo — então "sem linhas novas" é tão comum no
  caso saudável quanto no quebrado.

  O check **Ingest heartbeat** do `embrapa doctor` lê essa trilha, com janela vinda de
  `cli.INGESTS`: fonte do lote noturno tem `HEARTBEAT_DAILY_SLACK_DAYS` (padrão 2), as
  mensais têm `HEARTBEAT_MONTHLY_SLACK_DAYS` (padrão 35). Fonte que **nunca** reportou não
  é acusada — a tabela só enche daqui para frente.

  A gravação **nunca** pode derrotar uma ingestão: `record()` engole todo erro com aviso.
  Um monitor capaz de derrubar o que monitora é pior que monitor nenhum — e há teste
  fixando exatamente isso.

### Corrigido

- **A suíte de testes escrevia batimentos em PRODUÇÃO.** `test_cli.py` exercita os comandos
  de ingestão, que agora passam pelo envelope novo e chegavam a `record()` — que, com a
  credencial de quem desenvolve presente, inseria de verdade em `research_inputs`. Uma
  rodada completa deixou **121 linhas** lá, e o `doctor` passou a reportar "every scheduled
  ingest ran" com base na própria suíte.

  Fechado com uma fixture `autouse` no `conftest.py` que neutraliza o cliente BigQuery do
  módulo. Ela troca `_bq_client`, **não** `record` — assim a lógica de `record` continua
  rodando e testável (os testes dele injetam o próprio cliente). Verificado: 121 linhas
  antes, 121 depois de uma suíte completa. A suíte também caiu de **163s para 27s**, o que
  confirma que o custo eram idas reais ao BigQuery.

  As 121 linhas de artefato precisam ser removidas por um humano — `DELETE` em BigQuery é
  deliberadamente bloqueado para o agente (ver `docs/operations_runbook.md`).

### Documentação

- O runbook § "Is a source still arriving?" ganha a tabela dos três estados, as janelas, a
  garantia de não-derrubar-a-ingestão e a consulta para ver a trilha crua.

---

## [1.33.18] - 2026-08-28

### Adicionado

- **`embrapa doctor` passa a checar o frescor de cada fonte.** O alerta de ingestão dispara
  em execução **falha**; uma rodada mensal que roda verde e não ingere nada é
  indistinguível de "a fonte ainda não publicou" — e para as fontes anuais esse estado
  quieto é normal ~11 meses por ano, então um travamento real podia ficar sem ser notado.

  O check lê `gold_source_metadata` (uma consulta pequena, e estende sozinho quando uma
  fonte é acrescentada lá) e compara `year_end` com o que a `cadence` daquela linha implica:
  `annual` precisa de ≥ `ano_atual − SOURCE_FRESHNESS_ANNUAL_SLACK_YEARS` (padrão **2** — um
  ano inteiro de folga além da defasagem de ~1 ano que essas fontes já têm, de modo a só
  acusar depois que uma janela de publicação passou **sem** o ano novo chegar); `monthly`
  precisa de ≥ `ano_atual − 1` (janeiro ainda carrega dezembro). **Avisa, nunca falha.**

  **O que ele deliberadamente NÃO faz**, registrado no código e no runbook: distinguir fonte
  quieta saudável de fonte travada **entre** janelas de publicação — o dado é idêntico nos
  dois casos. Ele pega o travamento na janela, não antes. Para saber se o gatilho disparou,
  o sinal é a execução do Job, não o BigQuery.

  Contra prod hoje: `ibge_pam=2024 · ibge_pevs=2024 · ibge_ppm=2024 · mdic_comex=2026 ·
  un_comtrade=2025`, todas correntes.

### Testes

- 6 casos cobrindo o piso dependente de cadência (uma anual atrasada acusa e a saudável ao
  lado não é nomeada; uma mensal um ano atrás acusa onde a anual passa), `year_end` nulo,
  tabela vazia e falha de consulta. Validados por injeção: remover a dependência de cadência
  quebra 1 teste; suprimir o aviso quebra 2. `test_run_all_executes_every_probe` — que fixa
  a lista ordenada de checks — foi atualizado em vez de afrouxado.

---

## [1.33.17] - 2026-08-28

### Corrigido

- **Comentário em `cli.py` dizia que o PAM deveria ganhar cadência mensal "later … once
  validated". Ele já tem, há meses.** `embrapa-ingest-all-pam-monthly` (cron `0 4 2 * *`) e
  `embrapa-ingest-all-ppm-monthly` (`0 4 3 * *`) estão **ENABLED** no Cloud Scheduler e
  disparam — verificado em 2026-08-28 pelas execuções extras do Job nos dias 2 e 3 de
  agosto às 07:06 e 07:04 UTC, além da diária das 08:0x, e pela ingestão de PPM em Bronze
  datada de 2026-08-03.

  O comentário, somado à nota de exclusão do lote noturno (corrigida na v1.33.16), fazia
  parecer que estar fora do `ingest all` era estar **sem** cadência — duas coisas
  diferentes. Reescrito com o nome do agendamento, o cron e o alvo de `make` que o cria.

### Verificado, sem achados

A cadência mensal é funcional, não só agendada: `pam_delta_overlap_years` /
`ppm_delta_overlap_years` são 1 (cada rodada refaz de `último_ano_bronze − 1`, absorvendo
revisões) e `pam_end_year` / `ppm_end_year` usam `default_factory=_current_year` — flutuam
à frente do último ano publicado e não estão pinados no `.env`. Logo, quando o IBGE
publicar 2025, a próxima rodada mensal o captura. O `pam_pipeline` inclusive documenta o
caso confusível (SIDRA vazio ⇒ pular, não acumular vazios).

---

## [1.33.16] - 2026-08-28

Auditoria do `CLAUDE.md` — a doc carregada em toda sessão, e a que acabou de se provar
errada em três pontos numa frase (v1.33.15). Um achado novo.

### Corrigido

- **`make ingest-all` não atualiza PAM nem PPM, e o `CLAUDE.md` nomeava só o COMTRADE como
  exclusão.** O lote roda **quatro** fontes (IBGE PEVS + BCB inflação + BCB câmbio + COMEX)
  e exclui **três**: `cli.INGESTS` marca `in_all=False` para `ibge-pam` e `ibge-ppm`
  (anuais, ~1 ano de defasagem de publicação, cadência mensal própria) além do `comtrade`
  (key-gated + quota-gated). Quem rodasse o alvo para "atualizar tudo" deixaria **dois dos
  seis bancos** parados sem perceber. A enumeração `ingest {ibge|bcb-*|all}` também
  omitia metade dos comandos; agora lista todos.

### Testes

- **`tests/test_claude_md_ingest_batch.py`**: toda fonte com `in_all=False` em
  `cli.INGESTS` tem de estar nomeada na nota de exclusão do `CLAUDE.md`.

  A primeira versão do teste **passou com o defeito reintroduzido** — o regex pegava um
  bloco largo, e a linha logo abaixo enumera todos os nomes de ingest, satisfazendo a
  checagem mesmo sem a nota. Estreitado para ler apenas as linhas de comentário que seguem
  `make ingest-all`, e revalidado: agora acusa `['comtrade', 'ibge-pam', 'ibge-ppm']`.

### Verificado, sem achados

Tudo o mais do `CLAUDE.md` que é checável confere: os 4 vars de qualidade
(`quality_price_k`=100, `quality_outlier_k`=4.0, `quality_min_obs`=100,
`quality_value_floor`=100000) e `enable_quality_outliers: true`; a taxonomia de flags (os
2 níveis reservados `INFERRED_*` de fato com zero linhas em prod); `silver_ibge_pevs`
incremental `insert_overwrite` por `reference_year` e `silver_bcb_*` como `table`; os três
registries (`cli.INGESTS`, `doctor.SOURCE_CHECKS`, `doctor.BRONZE_TARGETS`); o entrypoint
gunicorn e o extra `webapi` sem dash/plotly; e todos os caminhos citados.

---

## [1.33.15] - 2026-08-28

### Corrigido

- **`CLAUDE.md` e `ARCHITECTURE.md` diziam que a Engenharia de Atributos inteira está
  congelada e escondida da UI. Só um dos seus dois eixos está.** Correção apontada pelo
  usuário e confirmada no código e em prod:

  | eixo | estado real |
  |---|---|
  | **Nível de industrialização** (por código) | **NO AR** — editor na barra lateral, view *Valor agregado* `status: 'live'`, `serving.dim_code_industrialization_scd2` com **303 classificações em 5 níveis** em prod |
  | **Tipo de mercado** (regime × fluxo) | **CONGELADO** — entrada de UI comentada, `curated_market_nature` deliberadamente não mapeada, `serving_comtrade_annual.market_nature` com **0 valores distintos** |

  Três afirmações erradas na mesma frase: o escopo ("hidden from the UI" — o editor de
  industrialização está visível), o gate (`enable_curation` "default false" — é **`true`**
  em `dbt_project.yml:122`) e a receita de revival (`--vars 'enable_curation: true'` — já
  ligado; o que falta para o tipo de mercado é **dado**, não configuração: a base
  totals-only `customsCode=C00` não traz o detalhe de procedimento aduaneiro).

  O comentário do `AppShell.jsx` sempre escopou certo ("the **'Tipo de Mercado'** matrix is
  hidden"), e a memória do projeto também. Quem generalizava era a documentação de topo —
  e na v1.33.13 **eu propaguei essa generalização** para o banner que acrescentei em
  `PLANS/comtrade_flows_regimes_market.md`, citando o `CLAUDE.md` como autoridade. Banner
  reescrito junto.

---

## [1.33.14] - 2026-08-28

### Corrigido

- **A "Exportação mundial" declarava dois anos de cobertura; tem vinte e seis — e isso
  encolhia a janela do compositor de cruzamento.** `world_exp` estava fixada em
  `years: [2022, 2023]`, um literal do tempo em que o backfill all-reporters estava
  adiado. Ele foi concluído, e o literal sobreviveu.

  Não era só rótulo: `crossCommonWindow` (producers.js) calcula a janela comparável como a
  **interseção** dos `years` das métricas selecionadas — `Math.max` dos inícios,
  `Math.min` dos fins. Escolher "Exportação mundial" no compositor colapsava a comparação
  para **2022–2023**, com qualquer outra série, sobre 26 anos de dado real.

  Medido no mart que a métrica lê (`serving_comtrade_annual`, `flow='export'`): total
  mundial presente em **todos os 26 anos**, de US$ 71,7 bi (2000) a US$ 339,3 bi (2022),
  sobre 89–166 reporters por ano. Passa a `[2000, 2025]`, alinhada às métricas irmãs.

  A invariante de v1.33.9 **não pegaria isto**: ela proíbe métrica reivindicando dado mais
  ANTIGO que a cobertura do banco. Aqui o erro foi reivindicar **menos** — e para "menos"
  não existe piso configurado contra o qual comparar, porque uma métrica pode
  legitimamente cobrir só parte do período do banco. Fica registrado como limite conhecido
  em vez de virar uma regra frágil.

  Encontrado ao conferir uma anotação interna minha que dizia "world_exp só 2022–2023, NÃO
  alargue até o backfill all-reporters" — a mesma afirmação vencida que estava no
  `CLAUDE.md`, no runbook e no `bancos.js`, corrigida nas v1.33.7 / v1.33.11 e agora aqui.

---

## [1.33.13] - 2026-08-28

Auditoria de conteúdo dos 42 arquivos de documentação (a varredura anterior, v1.33.12,
foi de *referências*; esta é do que os textos **afirmam**). Cinco achados.

### Corrigido

- **`frontend/src/ui/README.md` dizia que o diretório está "intentionally out of ESLint
  scope" — e mandava conferir no `eslint.config.js`, que diz o contrário.** O config lista
  `src/ui/**/*.{js,jsx}` explicitamente, `npm run lint` é
  `eslint src/data src/charts src/ui`, e o ESLint analisa **106 arquivos** ali. O próprio
  config registra que a isenção "lapsed once it became maintained prod code, and the gap
  was hiding real dead-code + hook-deps findings" — o README preservou justamente o
  racional que caducou, junto com o "avoid restyling it" que vinha colado nele.
- **`PLANS/comtrade_flows_regimes_market.md` não declarava estado.** Abre com "**Objetivo.**
  Habilitar…" e nada indica que a feature está **congelada** — o `CLAUDE.md` é explícito
  ("do NOT treat it as activatable") e dois dos três objetivos estão bloqueados por dado
  (o detalhe de procedimento aduaneiro não existe na base desde o redesenho totals-only).
  Ganhou banner de estado com o motivo.
- **6 das 8 auditorias em `docs/audits/` não tinham marcador de histórico.** São relatórios
  datados sobre versões muito anteriores (v1.5.2, v1.6.0, PRs específicos); sem marcador,
  os achados listados leem como pendências abertas. Foi o risco que corri ao começar esta
  auditoria. Padronizadas com o banner que uma delas já usava.
- **`PLANS/geo_subregions.md`, marcado DONE, ainda dizia que o município está "currently
  gated (`topMunis` [])".** Ele é populado a partir do cubo, ranqueado e nomeado pela malha
  (teste `GEO-1`); o `[]` que sobrou no código é o fallback de snapshot vazio.
- **`scripts/README.md` se declara "the index" e não listava `refresh_ibge_municipio_geojson.py`**
  — o script que vendoriza as malhas municipais sem as quais o mapa não desce abaixo da UF.
  Indexado. Na mesma passada: a célula "quando usar" do `test_setup.py` mandava rodar o
  setup "via `setup.sh`/`setup.ps1`", scripts que a coluna ao lado, na mesma linha, lista
  como **substituídos** e que não existem.

### Testes

- **`tests/test_doc_status_markers.py`**: toda auditoria em `docs/audits/` e todo plano em
  `PLANS/` têm de declarar seu estado nas 10 primeiras linhas. A regra aceita o vocabulário
  que o repositório já usa (HISTÓRICO · SUPERSEDED · STATUS · CONGELADO · DONE · COMPLETE ·
  IMPLEMENTED) em vez de exigir uma palavra: dois planos lideram com um banner SUPERSEDED e
  põem o Status logo abaixo, o que lê **melhor**, não pior. Validado por injeção nos dois
  casos.

### Verificado, sem achados

- **Piso de cobertura**: `CONTRIBUTING.md` (98%) bate com o `Makefile` (`--cov-fail-under=98`);
  o "99%" citado em `docs/testing.md` é a explicação de por que **não** é 99. Real hoje:
  99,10% sobre 6.877 statements — o "~6.8k" da doc confere.
- **`docs/frontend_data_contract.md` §3.6** cobre os três endpoints sub-UF, incluindo o
  `products-by-municipio` de v1.29.0.
- **`scripts/README.md`** agora fecha nos dois sentidos: nenhum script sem entrada, nenhuma
  entrada sem arquivo.

---

## [1.33.12] - 2026-08-28

Varredura mecânica das docs: todo caminho de arquivo, alvo de `make` e comando da CLI
citado em `*.md`, `docs/`, `PLANS/` e `.claude/skills/` conferido contra o que existe.

### Corrigido

- **A skill `lint-and-test` mandava rodar cinco testes que não existem.** Os arquivos
  ganharam o prefixo `test_webapi_` em algum momento e a lista ficou para trás:
  `test_seam.py`, `test_serializers.py`, `test_format.py`, `test_registries.py` e
  `test_cache_resilience.py`. Quem seguisse a skill — pessoa ou agente — recebia
  "file not found" cinco vezes. Corrigidos para os nomes reais, mais os dois
  `test_cov_*` que não constavam.
- **A mesma skill afirmava "the suite has ~31 files"; são 63.** Trocado por `make test` e
  `ls tests/test_*.py`, que é a única contagem que não apodrece.

### Testes

- **`tests/test_doc_file_references.py`**: todo caminho `tests/test_*.py` citado numa doc
  ou skill tem de existir, e todo glob citado (`tests/test_comex_*.py`) tem de casar com
  algo. Validado por injeção nos dois casos. `CHANGELOG.md` fica de fora de propósito:
  ele registra o que era verdade em cada versão, então um caminho depois renomeado está
  **correto** ali.

  Caminhos de teste são o subconjunto que vale prender automaticamente — são inequívocos,
  ao contrário de um termo de glossário ou do `column:` de um filtro, onde tentar adivinhar
  pelo formato da string gera falso-positivo (foi o que quase me fez "corrigir"
  `valor_producao` na v1.33.9).

### Verificado, sem achados

- **312 caminhos de arquivo** citados nas docs: os demais sem correspondência são
  referências históricas ou exemplos deliberados — o `ARCHITECTURE.md` cita `docs/auth.md`
  e `scripts/check_dashboard_size.py` numa lista do que foi **deletado**, o `PLANS/README.md`
  dá exemplos de nomenclatura, o `README.md` diz que o Roadmap no Drive **substitui**
  `ROADMAP.md`/`TODO.md`, e `profiles.yml` é criado pelo usuário em `~/.dbt/`.
- **Todo `embrapa <comando>`** citado em qualquer doc resolve num comando real (13 comandos).
- **Todo `make <alvo>`** citado em bloco de código resolve num alvo real (40 alvos).

---

## [1.33.11] - 2026-08-28

### Documentação

- **O backfill mundial do COMTRADE está concluído, mas a documentação ainda o descrevia
  como a lacuna pendente do projeto.** Medido no Gold: os **26 anos** (2000–2025) estão em
  todos os reporters, entre **90 e 174 por ano**; **nenhum** ano é só-Brasil. A seção
  "Current state" do runbook, medida em 2026-06-17, listava `1989–2021, 2024–2025` como
  só-Brasil e dizia que faltavam "35 missing years"; o `CLAUDE.md` chamava o arquivo de
  "the last gap to max granularity".

  O custo de acreditar nisso era concreto: seguir o runbook gastaria dias da cota da API
  da ONU — que o próprio documento chama de "the only real constraint" — rebaixando dado
  que já está lá.

  Corrigidos: o subtítulo e a seção de estado (agora com a medição e a distribuição por
  ano), a linha do `CLAUDE.md`, a verificação #1 (era `1989–2025` e a faixa de linhas
  pré-redesenho `337–1.628`; hoje `2000–2025` e **641–1.956**, verificada), a linha de
  risco que ainda falava em "current gap", e a verificação #6 — que mandava editar a
  maturidade em `bancos.js`, quando a fonte única é `research_inputs.banco_metadata` desde
  que o override entrou.

  Acrescentado o que o backfill **de fato** custou, contra a previsão que o documento
  trazia: Bronze **21.110.724** linhas (previsão ~29,7M), Silver **2.053.708** (~4,25M),
  26 anos em vez de 35. O cabeçalho já avisava que a previsão era "a safe upper bound";
  agora há o número real ao lado.

  Nota: **eu editei este mesmo arquivo mais cedo hoje** (v1.33.7, corrigindo a instrução
  `COMTRADE_START_YEAR=1989`) sem notar que a premissa dele estava vencida — corrigi a
  receita e deixei o motivo errado. O documento registra por que a seção sobreviveu:
  nada recalcula um estado escrito à mão.

### Pendência deixada para o operador (não feita aqui)

- A verificação #6 do runbook condiciona promover o `un_comtrade` de `beta` a `estavel` às
  verificações (1) e (2) — **ambas satisfeitas** na medição de hoje. Se isso basta para
  chamá-lo estável é julgamento de quem responde pelo dado: é uma afirmação ao pesquisador
  sobre quanto os números ainda podem mudar. Deliberadamente não alterado.

---

## [1.33.10] - 2026-08-28

### Corrigido

- **O CI ficava vermelho no main a cada merge que tocasse `dbt/**`.** O job "dbt unit
  tests" rodava também no push, e o `dbt-build-prod` dispara no mesmo push — os dois
  executam **os mesmos** unit tests, materializando cada modelo testado na **mesma**
  tabela temporária (`<nome_do_teste>__dbt_tmp`) do **mesmo** dataset `gold`. O build
  derrubava a temporária debaixo do teste em execução, que falhava com "Destination
  deleted/expired during operation".

  Medido: o build inicia `test_dim_produto_catalog_latest_wins_active` às 17:52:03, o CI
  falha nesse mesmo teste às 17:52:13, e um re-run idêntico passou depois que o build
  terminou (runs 33196613456 / 33196613442). Não era instabilidade: era determinístico
  para todo merge que mexesse em dbt — justamente as mudanças que mais precisam da
  verificação.

  O job passa a rodar **só em pull request**, que é seu propósito declarado (pegar antes
  do merge). No main ele era redundante: `dbt build` roda unit tests desde o dbt 1.8, então
  o `dbt-build-prod` já executa todos — sobre o DAG inteiro (nós 20, 21, 128, 129 e 190 de
  357), não só os 6 selecionados no CI. Um push direto no main sem PR continua coberto,
  pelo próprio build.

  A primeira hipótese — apontar o job para um dataset sandbox — **foi testada e não
  funciona**, e o motivo corrige uma afirmação que estava no próprio comentário do CI
  ("read NO real tables and write nothing"): unit tests não leem LINHAS reais, mas o dbt
  os materializa e resolve os tipos de coluna de cada relação referenciada contra o
  warehouse vivo. Em `dbt_dev_silver` a seed `historical_currency_factors` não existe e a
  compilação falha. O comentário agora registra as duas coisas.

  O job `sqlfluff` ficou como estava: só compila os modelos, não materializa nada, e
  portanto não colide.

---

## [1.33.9] - 2026-08-28

A recomendação da v1.33.8: completar a documentação de colunas do Gold, que além de valer
por si destrava a classe de guarda que faltava — "todo nome afirmado na UI existe no schema".

### Documentação

- **`dbt/models/gold/_gold.yml` passa a documentar TODAS as colunas do Gold.** Eram 87 sem
  descrição em 5 modelos (a família `val_yearfx_*`/`val_real_*` inteira, mais unidades,
  pesos e colunas específicas de comércio). Agora os 7 modelos batem exatamente com o
  schema real: **181 colunas**, nenhuma faltando, nenhuma documentada-porém-inexistente,
  nenhuma duplicada.

  Duas semânticas que só existiam no SQL e agora estão escritas onde se procura por elas:
  `qty_native`/`qty_base` em COMEX e COMTRADE somam **apenas** as linhas da unidade
  dominante do grupo (somar unidades mistas juntaria números incomparáveis), e
  `source_rows` conta quantas linhas da fonte foram colapsadas em cada linha do Gold.

### Corrigido

- **O glossário marcava `gold_nfe_flows` com o mesmo tag "Base final" das cinco tabelas
  que existem.** O texto dizia "planejada … será", mas o tag é o chip que se lê num
  relance, e ele afirmava uma tabela que o SEFAZ NFe ainda não tem. Passa a "Planejada".

### Testes

- **`tests/test_glossary_schema_claims.py`**: todo termo do glossário com `tag: 'gold'`
  tem de resolver numa coluna do Gold (exata ou família com `*`); toda tabela com
  `tag: 'Base final'` tem de existir; toda tabela "Planejada" **não** pode já existir; e
  nenhuma coluna pode aparecer duas vezes no YAML. Validado por injeção nos três casos.

  O teste NÃO adivinha o que é identificador físico pelo formato da string — foi
  justamente esse palpite que quase me fez "corrigir" `valor_producao`, que é vocabulário
  da fonte, como `ncm` e `codigo_pevs` em outros bancos. O `tag` da própria entrada é o
  sinal explícito.

- `pyyaml` passa a ser dependência declarada do grupo `dev`. Já chegava transitivamente
  pelo dbt-core; declarada para o teste não depender do grafo de dependências de terceiro.

---

## [1.33.8] - 2026-08-28

### Alterado

- **Removidos os overrides de cobertura que apenas duplicavam o registry.** `ibge_pam`
  (`cobertura_years`) e `ibge_ppm` (`cobertura_years`, `cobertura_atualizacao`,
  `cobertura_granularidade`) carregavam em `research_inputs.banco_metadata` valores
  **byte-idênticos** aos de `registries.py` e `bancos.js` — conferido campo a campo antes
  de apagar. Não era defeito hoje; era a condição que produziu o defeito do COMTRADE na
  v1.33.7, onde as duas cópias diziam "1989" e portanto nada parecia inconsistente até
  que ambas ficassem erradas.

  Limpeza de **coluna, não de linha**: `maturity` não tem fallback no registry, então uma
  linha apagada deixaria o banco exibindo a etiqueta neutra "…" para sempre. As seis
  linhas seguem com sua `maturity`, e só o `sefaz_nf` mantém `maturity_note` — a única
  ressalva legítima da tabela. Nenhum override de cobertura resta: o registry é a cópia
  única.

  Verificado depois: os cinco bancos com dados devolvem exatamente os mesmos três campos
  de cobertura de antes da limpeza. No-op para quem lê, por construção.

### Documentação

- **O runbook mandava dobrar a mudança de volta no registry "para que o default e o
  override concordem" — e parava aí.** Esse é o passo que faltava: uma vez dobrada, o
  override vira cópia redundante, e cópia que concorda hoje é a que envelhece amanhã.
  `docs/operations_runbook.md` agora manda **apagar o override** depois de dobrar,
  cita o caso do COMTRADE como o que acontece quando não se apaga, e avisa para nunca
  anular `maturity` (sem fallback ⇒ banco preso em "…").

---

## [1.33.7] - 2026-08-28

Varredura atrás de erros da mesma família do PPM — dado estático afirmando o que os dados
não sustentam. Dois achados, ambos no UN COMTRADE.

### Corrigido

- **O painel anunciava cobertura do COMTRADE desde 1989; não existe nada antes de 2000.**
  O redesenho *totals-only* da v1.13.0 moveu a ingestão para `COMTRADE_START_YEAR=2000` e
  `silver_comtrade_flows` passou a pisar `reference_year` em `var('comtrade_min_year', 2000)`.
  Medido nas três camadas: Bronze 2000–2025 (21.110.724 linhas), Silver 2000–2025, Gold
  2000–2025 (26 anos, 2.053.708 linhas). **Nenhuma linha antes de 2000, em lugar nenhum.**
  O rótulo ficou para trás em quatro cópias — `bancos.js` (cobertura + os anos das métricas
  `exp_value`/`imp_value`, que também terminavam em 2024 com Gold em 2025), `registries.py`,
  e a linha de override em `research_inputs.banco_metadata`. O override não estava sequer
  sobrepondo: duplicava o mesmo valor errado do registry, o que é a condição exata que faz
  uma cópia envelhecer sem ninguém notar. Limpo (o registry volta a ser a fonte única, como
  o runbook pede). Conferido nos cinco bancos com dados: todos declaram agora um início
  igual ao do Gold.
- **O runbook do backfill mandava rodar com `COMTRADE_START_YEAR=1989`** em dois pontos
  executáveis, contradizendo o próprio cabeçalho ("from **2000** … now the default ingest
  scope"), o default da config e o piso do Silver. Seguir a instrução gastaria a cota diária
  da API da ONU — que o documento chama de "the only real constraint" — buscando anos que o
  build descarta em seguida.

### Testes

- **`tests/test_banco_coverage_claims.py`**: o início declarado na cobertura tem de ser igual
  ao piso de ingestão configurado, nos dois registries (PAM, PPM, COMEX, COMTRADE — PEVS
  descobre o seu e SEFAZ NFe não tem pipeline, então ficam fora de propósito); os dois
  registries têm de declarar a mesma cobertura; e nenhuma métrica pode reivindicar dado mais
  antigo que a cobertura do seu banco. Validado por injeção nos três pontos (2, 2 e 1 falha).

  A invariante existe porque nem o rótulo se recalcula, nem a concordância entre os dois
  registries provava algo — **os dois estavam errados juntos**. O que decide o início de
  verdade é o piso configurado, e é a ele que o rótulo passa a responder.

---

## [1.33.6] - 2026-08-28

### Corrigido

- **O aviso de beta do IBGE PPM não era o dos outros bancos.** Em vez de "Beta. Disponível
  para testes e validações, resultados podem mudar." o PPM exibia "Beta. Pecuária
  municipal — rebanho + produção de origem animal".

  A causa é **dado**, não código: a linha do PPM em `research_inputs.banco_metadata` tinha
  `maturity_note` preenchido com uma descrição de escopo, escrita em 2026-06-20 por
  `updated_by='ppm-activation'`. E `maturity_note` **substitui** o texto padrão do estágio
  (`MaturityBanner`: `banco.maturityNote || m.desc`), então a descrição tomou o lugar da
  ressalva. Corrigido em produção com um `UPDATE` de um campo — os outros cinco bancos já
  tinham `NULL`, exceto `sefaz_nf`, cuja note é uma ressalva legítima e ficou intacta.
  Conferido nos cinco bancos com dados: todos exibem agora a mesma mensagem.

  O texto removido não tinha lugar nessa tabela — o schema só tem maturidade e cobertura —
  e já vivia em `bancos.js` como `sub`, `about` e `domain`.

### Documentação

- **O lado da ESCRITA não dizia que `maturity_note` substitui a mensagem padrão** — o
  runbook a chamava apenas de "the caveat note", e foi essa a lacuna que permitiu o erro.
  `docs/operations_runbook.md` § "Changing a banco's maturity / note / coverage" e a
  docstring de `ensure_banco_metadata_table` agora dizem que a note **substitui** (não
  acrescenta), que ela serve só para uma ressalva verdadeira daquele banco (como a do
  `sefaz_nf`), que descrição de escopo pertence a `bancos.js`, e como limpar uma.

---

## [1.33.5] - 2026-08-28

### Alterado

- **"Convenções métricas" passa a ser simétrica a "Filtros ativos".** As duas tiras ficam
  uma sobre a outra e têm o mesmo peso — uma diz quais linhas entram, a outra como os
  números daquelas linhas são exibidos — mas destoavam em quatro pontos, e a diferença
  lia como hierarquia onde não há: padding `14px 18px 16px` contra `12px 16px`, gap 14
  contra 12, rótulo em azul peso 600 contra cinza `--fg-3` peso 500, e um filete azul de
  3px à esquerda que a tira de filtros não tem. Tudo alinhado pelo desenho de "Filtros
  ativos".

  O filete saiu por não codificar nada: neste código uma `border-left: 3px` marca
  **categoria** (níveis de maturidade, live/soon, painel de leitura vs. de escrita), e uma
  cor fixa única na única tira do seu tipo não distinguia coisa alguma. As duas regras
  ficam com um comentário pedindo que andem juntas.

  Medido no app: padding, borda, raio, fundo, largura e **altura** idênticos, e o rótulo
  resolvendo para o mesmo `rgb(102, 102, 102)` / peso 500 / `letter-spacing` 1,2px nas
  duas tiras. Estado expandido conferido junto.

---

## [1.33.4] - 2026-08-28

Duas varreduras nas transições do mapa e na referência ABNT — quatro defeitos, todos
do tipo que não gera erro nenhum, só uma tela ou um texto que afirma o que não é.

### Corrigido

- **Clicar fora do mapa, logo depois de entrar numa região, não fazia nada visível.**
  `enterRegion` grava `regions` **e** `states` (a região só alcança os dados através das
  UFs), e `stepOut` lia essas UFs como um degrau próprio: o primeiro clique limpava
  `states` sem mudar o nível nem a trilha, e só o segundo voltava ao Brasil. Era o
  caminho mais comum de todos. Agora a expansão da própria região é reconhecida como
  não-degrau e o gesto sai dela de uma vez.
- **A trilha nomeava a região inteira enquanto o mapa plotava parte dela.** Com uma
  região selecionada, um estreitamento de várias UFs dentro dela era suprimido:
  "Norte com apenas PA e AM" renderizava idêntico às sete UFs do Norte. É a
  sub-notificação da v1.33.2 um degrau acima, e o recorte é alcançável pelo uso normal
  do menu (o seletor de UF exige uma região antes). O estreitamento passa a ter crumb
  próprio; a expansão da região continua suprimida, por ser ruído e não informação.
  A regra mora numa única função (`isRegionExpansion`) porque trilha e `stepOut`
  precisam responder a mesma pergunta — derivações separadas foi como as duas
  discordaram da primeira vez.
- **`undefined` vazava para dentro da referência ABNT.** O rótulo de convenções
  guardava contra `conventions` ausente mas confiava na FORMA do objeto: um
  `conventions` sem `units` publicava "Convenções métricas: BRL · IPCA · undefined ·
  undefined" num texto que o pesquisador cola no trabalho. Passa a ter default por
  campo.
- **A referência anunciava um cruzamento e não nomeava nada.** Sem séries escolhidas no
  compositor, o nível detalhado saía "— Cruzamento entre fontes — . Recorte: ...".
  O segmento agora só aparece quando há séries.

### Testes

- **Invariantes das transições do drill** (`geoDrill.test.js`), varridas sobre todo estado
  alcançável por sequências de até três gestos: nenhum `stepOut` é silencioso (muda
  nível ou trilha), `stepOut` sempre termina em Brasil sem ciclo, a trilha nunca nomeia
  um recorte maior que o filtrado, e um banco sem grão municipal nunca oferece o degrau
  de município. Validadas por injeção: restaurar o primeiro defeito acusa 146 estados,
  o segundo acusa 24 + 36.
- **A referência contra a norma** (`AppShell.cov.test.jsx`), varrida sobre 9 estados do
  app × 3 níveis de detalhe: nenhum valor ausente vaza, pontuação bem formada, entrada
  sempre em caixa alta (6023:2025), negrito cobrindo exatamente o título e o mesmo
  título nos três níveis, fecho com data de acesso, e a citação no texto com inicial
  maiúscula (10520:2023) — a norma que já foi "unificada" para caixa alta uma vez e
  revertida.

---

## [1.33.3] - 2026-08-28

Três rótulos idênticos na barra de cores afirmavam que a escala era plana quando não era.

### Corrigido

- **Barra de cores dos mapas de calor: faixa estreita colapsava as três âncoras no mesmo
  rótulo.** As âncoras (mínimo / centro / máximo) existem para o leitor situar qualquer cor
  na escala; formatadas todas pela escada `bi/mi/mil` com no máximo uma casa decimal, uma
  faixa curta as reduzia a três números iguais — Centro-Oeste 2018–2019 no PEVS exibia
  `1 mil | 1 mil | 1 mil` sobre um gradiente que variava de fato. Medido sobre o acervo
  real (`/api/geo-yearly`, ibge_pevs): **45 combinações de (região × janela de anos)**
  colapsavam, todas em seleções corriqueiras. `colorbarAnchors` agora escalona a precisão
  até os rótulos se separarem e, se nem 3 casas bastarem, devolve o eixo ao Plotly em vez
  de imprimir um rótulo preciso porém ilegível. O caminho de faixa larga é byte-idêntico
  ao anterior, e `ptBrMagnitude` sem o novo argumento opcional não mudou para nenhum outro
  consumidor. Afeta o mapa de calor Ano × Região e o de sazonalidade Mês × Ano.

### Testes

- Varredura de invariante sobre 10 magnitudes × 9 larguras relativas × sinal (`_base.colorbar.test.js`):
  o resultado é `null` **ou** três rótulos distintos — nunca um repetido. Validada por
  injeção de regressão (restaurar a formatação antiga faz a varredura acusar 97 casos), com
  dois casos reais do PEVS ancorados explicitamente.

---

## [1.33.2] - 2026-08-28

A correção da v1.33.1 tinha a **mesma lacuna que corrigia**, um nível abaixo — e agora
há uma invariante no lugar de mais um caso.

### Fixed
- **A trilha nomeava só a primeira faceta sub-UF.** As duas divisões do IBGE são
  **paralelas e não se aninham** (clássica meso→micro, 2017 intermediária→imediata), e um
  município precisa passar por **todas** as facetas ativas — o recorte efetivo é a
  **interseção**. Com mesorregião *Nordeste Paraense* **e** intermediária *Belém* ativas,
  a trilha dizia apenas `Brasil › Nordeste Paraense`.

  Quem lesse aquilo concluiria que o recorte era a mesorregião inteira, quando era um
  conjunto estritamente menor. Mesma falha de honestidade da v1.33.1 — o dispositivo de
  orientação descrevendo mais território do que os dados —, agora no rótulo em vez do
  nível.

  A regra passa a nunca sub-reportar: uma narrowing é nomeada, duas são nomeadas juntas
  (`Nordeste Paraense · Belém`), e além disso entra a contagem. Uma contagem é mais vaga
  que um nome, mas não pode afirmar que o recorte é mais largo do que é.

### Added
- **Invariante varrida sobre as 16 combinações das quatro facetas:** nenhum rótulo pode
  nomear um único lugar enquanto duas ou mais narrowings estão ativas, e nenhuma
  combinação ativa pode produzir rótulo vazio.

  Existe porque "adicionar mais um caso" foi o que produziu dois bugs seguidos. A trilha
  deixou de ser decoração quando o seletor de granularidade saiu (v1.32.0): virou o
  **único** lugar onde o pesquisador lê onde está, então a correção dela é carga
  estrutural. Validada por injeção de regressão — reintroduzido o "nomeia só a primeira",
  a varredura acusa `3/n=2: UNDER-REPORTS`.

- `subUfLabel` e `subUfCount` mudaram da view para o `geoDrill`, junto de
  `drillLevel`/`drillTrail`, para que a regra viva onde é varrida.

---

## [1.33.1] - 2026-08-28

Achado de auditoria da própria sessão: o drill-down (v1.32.0) **ignorava as facetas
sub-UF**, e o mapa passou a afirmar o oposto dos dados.

### Fixed
- **Um recorte por mesorregião produzia um mapa dizendo "Brasil".** Com a mesorregião
  *Nordeste Paraense* aplicada e nenhuma UF selecionada:

      trilha:  "Brasil"                     <- o dado era uma meso do Pará
      título:  "Distribuição por região"
      heatmap: "ano × região (1 região)"

  `drillLevel` inspecionava apenas `munis`, `states` e `regions`. As quatro facetas entre
  a UF e o município — mesorregião, microrregião, intermediária, imediata — não entravam
  na conta, então um recorte **abaixo** da UF caía no nível mais **grosso** que existe.
  Regressão do propósito declarado do `PLANS/geo_subregions.md`: *"a sub-UF selection
  must finally reach the MAP"*.

  Pior que o rótulo errado: `scope` também dirige o **grão da exportação CSV**
  (`window.geoExportScope`), então o download saía por região — casando com a legenda,
  não com as linhas.

  `drillLevel` passa a receber `subUfActive` de quem sabe: um facet key pode estar
  presente cobrindo o **universo inteiro**, o que não estreita nada, e só o `dataFilters`
  conhece o universo. Verificado no navegador: a mesma seleção agora dá
  `Brasil › Nordeste Paraense`, "Distribuição por município" e "ano × município".

- **A trilha ganhou a migalha do recorte**, nomeada pela malha, no degrau entre a UF e o
  município — sem ela a trilha parava em "Brasil", com o dispositivo de orientação
  afirmando o contrário do que estava embaixo.

- **`stepOut` ganhou o mesmo degrau:** clicar fora com uma meso ativa pulava direto para
  limpar a UF, descartando um estreitamento que o pesquisador não pediu para deixar.

### Nota de auditoria
- O "Perfil do território" foi conferido no mesmo passo e **não** tem o defeito — lê
  `scopedCityCodes` e `subUfActive` diretamente.
- **Método de bump corrigido:** eu vinha reescrevendo `"version"` no `package-lock.json`
  por substituição de texto. Nesta versão havia **14** ocorrências de `"version":
  "1.33.0"` — 2 do projeto e 12 de dependências que por acaso estão nessa versão. A
  asserção de contagem barrou a torto e a direito antes que 12 pinos fossem reescritos.
  Passa a usar `npm version`, que altera só as duas entradas do projeto. Auditados os 25
  commits anteriores: nenhum bump meu tocou em dependência (os dois que alteram muitas
  versões são PRs do dependabot, que é o trabalho deles).

---

## [1.33.0] - 2026-08-28

**Abacaxi disponível no dashboard** (IBGE PAM, SIDRA 40092) — e o registro dessa
entrega, que saiu na v1.32.3 sem versão nem changelog.

### Added
- **Abacaxi no IBGE PAM.** É lavoura, então o banco é o PAM (produção agrícola), não o
  PEVS (extração vegetal). Ingerido 1974–2024: **251.777 linhas** no Gold, 5.563
  municípios, **1.376** no mart de consumo.

  **Conferência de valor ponta a ponta:** 2023 fecha em **1.587.545 t** no Gold —
  idêntico ao que a API do SIDRA devolve na fonte, sondada *antes* de ingerir.

  Registrado na Curadoria como agrupamento `abacaxi` / **Abacaxi**, `ativa/visivel`.
  Snapshot do Gold para rollback: `run=20260828T042743Z`.

- **A unidade, que era a armadilha.** O SIDRA rotula o produto **"Abacaxi\*"**, e a
  unidade clássica do PAM para abacaxi é **mil frutos** — que o seed
  `unit_family_conversions` NÃO cobre (tem `un`, `dúzia`, `milheiro`, `cabeça`; nenhuma
  linha para frutos). Se chegasse assim, a quantidade cairia em `desconhecida` e
  sumiria em silêncio.

  A tabela 5457 harmoniza em toneladas — verificado em dois caminhos independentes: no
  dado já em produção (Coco-da-baía\*, igualmente asteriscado, gravado como
  `Toneladas`/`massa`) e na própria API. O asterisco é nota de rodapé, não aviso de
  unidade. Fixado em teste **com o raciocínio junto**, porque a leitura errada é a
  plausível: alguém poderia "corrigir" adicionando uma linha `contagem` e dividir a
  série por um fator de mil frutos que não se aplica.

### Impacto analítico
- **A cesta "Todos" do IBGE PAM foi de 10 para 11 produtos**, então qualquer agregado
  de todos-os-produtos daquele banco mudou de valor. Num painel com citação ABNT que
  carrega data de acesso e estado dos filtros, quem citou antes e quem cita agora
  citaram universos diferentes — e este registro é o único lugar onde isso consta.

### Fixed
- **`.env.example` estava defasado**: listava 8 códigos PAM enquanto o default do
  `config.py` listava 10, então quem partisse do exemplo ingeria um conjunto menor que o
  do job publicado. Teste novo compara os dois.

### Documentation
- **`docs/frontend_data_contract.md` §3.6** dizia "via **two** dedicated endpoints"; são
  três desde a v1.29.0, com a adição do `POST /api/products-by-municipio`.
- **`CLAUDE.md`** descrevia a cascata sub-UF lendo o Gold direto apenas via
  `municipio-yearly`. São dois leitores Gold-direto, ambos exigindo `cityCodes`
  não-vazio — a escopagem por cidade É o controle de custo. Importa por ser o arquivo de
  contexto: sem isso, uma sessão futura não saberia que o segundo existe.

---

## [1.32.3] - 2026-08-27

### Fixed
- **Uma seleção municipal sobrevivia à troca de banco e levava um banco só-UF para um
  grão que ele não tem.** O filtro geográfico é compartilhado: entrar num município no
  IBGE PEVS e mudar para o MDIC COMEX (só origem-UF) deixava o COMEX no nível de
  município.

  O controle segmentado tinha um efeito explícito para isso; derivar o nível (v1.32.0)
  o descartou, e o ramo de `munis` do `drillLevel` era onde ele deveria estar. Agora
  degrada para UF, como o ramo de `states` sempre fez.

- **A trilha não acompanhava a degradação.** Com o nível já corrigido para UF, a migalha
  de município continuava lá — exibindo o **código cru de 7 dígitos** como nível atual e
  oferecendo um caminho de volta a um lugar onde o mapa nunca esteve. `drillTrail` passa
  a receber a capacidade do banco e a parar onde ele para.

  Fixado como invariante: **a trilha nunca corre mais fundo que o nível**, varrido sobre
  as formas de filtro nos dois tipos de banco. Uma migalha além do nível atual é uma
  promessa que o mapa não pode cumprir.

### Nota
Encontrado ao andar um **percurso** que eu não tinha andado — trocar de banco estando
fundo no drill —, e não um destino. Os dois bugs da v1.32.2 tinham a mesma natureza:
dependem de estado acumulado pela navegação, que testes que montam cada nível
diretamente nunca produzem.

---

## [1.32.2] - 2026-08-27

Dois defeitos do drill-down da v1.32.0, ambos reportados por uso.

### Fixed
- **A migalha da região não levava a lugar nenhum.** De `Brasil › Norte › Pará`, clicar
  em "Norte" não mudava nada.

  `ufsOfRegion` resolvia a composição da região contra as UFs **já filtradas**. Dentro
  do Pará, o Norte "continha" exatamente um estado, então reentrar na região aplicava
  `states: ['PA']` — que continua sendo nível de município. A trilha não se movia e o
  clique lia como morto. A composição passa a vir do **universo** de UFs
  (`ufDataFull`), não da seleção corrente: agora volta com as sete.

- **Clicar num município carregava em silêncio.** O aviso "Carregando…" era guardado por
  `wantMuniFallback`, que exige `!subUfActive` — e clicar num município **ativa** a
  faceta sub-UF. Ou seja, o aviso existia para todos os caminhos menos o que o
  drill-down tornou mais comum.

  Passa a cobrir os dois caminhos municipais (o fallback local da view e o cubo
  compartilhado do `dataFilters`), e a **nomear o lugar certo**: o município quando há
  um, senão a UF — anunciar o estado enquanto o pesquisador acabou de clicar numa
  cidade reportaria a espera errada.

### Verificação
No navegador: de `Brasil › Norte › Pará`, a migalha "Norte" volta para `Brasil › Norte`
com `st=AC,AM,AP,PA,RO,RR,TO` (a região inteira); e clicar num município exibe
"Carregando municípios de Acará…" enquanto o histórico chega.

---

## [1.32.1] - 2026-08-27

### Changed
- **Entrar num território agora ESCONDE o resto do mapa, não o deixa cinza.** Faltava
  fechar o ciclo do drill-down da v1.32.0: entrar numa UF já enquadrava o estado, mas
  entrar numa **região** deixava o país inteiro desenhado, e focar um **município**
  deixava os outros do estado à volta.

  Em cada nível o mapa responde "o que há aqui dentro". Deixar os vizinhos desenhados
  convida a lê-los como parte da resposta — e no nível de região eles carregam a cor de
  **outra** região, então um vizinho acinzentado seria ativamente enganoso.

  Novas props `focusUfs` (BrazilChoropleth) e `focusCity` (MunicipioChoropleth):
  filtram **preenchimento e contorno** — filtrar só o preenchimento deixaria as bordas
  dos vizinhos flutuando sobre um mapa vazio — e enquadram a seleção. Para uma região, o
  enquadramento é a **união** das caixas das UFs dela; para um município, a geometria
  dele.

### Fixed
- **A contagem em cinza calava-se sobre um mapa que deixou de existir.** Com um
  município focado, os demais ficam ocultos e não cinzentos, mas a legenda seguia
  dizendo *"143 municípios fora do recorte — em cinza"*. A contagem é uma afirmação
  contábil sobre o que está na tela, então ela se cala no nível de foco — onde,
  aliás, não há o que explicar: exatamente um lugar está desenhado, de propósito.

  Encontrado na verificação em navegador da própria mudança acima; a supressão é
  guardada pelo **foco**, não por silêncio geral, e há teste dos dois lados.

---

## [1.32.0] - 2026-08-27

O mapa da Geografia vira **uma superfície só, navegável por zoom**, no lugar de três
modos escolhidos num seletor.

### Changed
- **A granularidade deixou de ser um controle: ela é onde você está.**

      Brasil              → as cinco macrorregiões
      dentro de uma região → as UFs dela
      dentro de uma UF     → os municípios dela
      dentro de um município → aquele município

  Clicar entra; clicar no espaço vazio sai um nível. Os botões `+`/`-` seguem sendo
  ampliação pura — movem a câmera, nunca o grão.

  **Isso elimina o beco sem saída por construção.** Escolher "Município" com nada
  selecionado abria um card explicando que era preciso ir configurar um filtro antes: o
  mapa sabia para onde você queria ir e pedia que você dissesse de novo em outro lugar.
  Com o nível derivado da seleção, "município sem UF" deixa de ser um estado alcançável
  — só se entra em município **entrando numa UF** —, então não há o que explicar.

- **Drill É filtro, de propósito.** O clique no mapa já estreitava o dashboard inteiro
  (v1.27.0) e todos os outros cards seguem o filtro geográfico. Manter uma segunda noção
  paralela de "onde estou" deixaria o mapa e os cards ao lado discordando sobre o que
  está sendo olhado.

### Added
- **Trilha de navegação** (`Brasil › Norte › Pará › Abaetetuba`) no lugar do seletor.
  "Clique fora para voltar" é invisível até ser descoberto, e um mapa sem noção visível
  de profundidade deixa o pesquisador sem saber se olha um país ou um estado. Cada
  migalha também é o caminho de volta àquele nível — um único patch, então o dashboard
  relê uma vez em vez de N.

- **`geoDrill.js`** — a derivação do nível e a escada de saída, puras e testadas à
  parte: um banco só-UF (COMEX) para na UF; várias UFs selecionadas ficam no nível de
  UF (a malha municipal é por UF, e escolher uma delas em silêncio seria mentir sobre a
  seleção); sair sempre termina em Brasil em passos finitos.

- **`onBackground`** nos dois choropleths: um handler ligado ao mapa inteiro que
  pergunta se o ponto acertou o preenchimento — a única forma, no maplibre, de
  distinguir "cliquei em nada" de "cliquei em algo".

### Verificação
Escada completa medida no navegador, nos dois sentidos: `Brasil` → `Brasil › Norte`
(Distribuição por UF) → `Brasil › Norte › Pará` (**Distribuição por município**, direto,
sem passar por filtro) → `Brasil › Norte › Pará › Abaetetuba`; e o clique fora
devolvendo `{munis: null}` de volta para `Brasil › Norte › Pará`.

---

## [1.31.6] - 2026-08-27

### Added
- **Invariantes de contagem do mapa municipal, varridos sobre o espaço malha × dados.**
  Mesmo tratamento dado ao mapa de calor na v1.31.5, agora no `MunicipioChoropleth`.

  A contagem em cinza é uma afirmação **contábil** feita ao pesquisador — "N municípios
  sem produção registrada" — calculada subtraindo o que os dados cobrem do que a malha
  desenha. Os dois conjuntos nem sempre coincidem: o IBGE lista ao menos um município
  (Boa Esperança do Norte/MT, criado em 2023) cuja geometria a API de malhas não
  publica, então um município pode ter dado e não ter polígono. Subtrair comprimentos
  cegamente o dobrava no cinza, superestimando "sem produção" e, com vários, indo a
  negativo.

  As propriedades varridas:

  - o cinza nunca excede o número de polígonos da malha, nem fica negativo;
  - **cinza + desenhados-com-dado = malha**, sempre (a identidade contábil por trás da
    frase; se falhar, o número na tela descreve um conjunto que não existe);
  - município com dado e **sem** polígono é reportado à parte, nunca dobrado no cinza;
  - valor zero conta como cinza, não como dado;
  - `narrowed` muda a **redação** e nunca o número — "fora do recorte" e "sem produção"
    são afirmações diferentes sobre os mesmos municípios;
  - concordância de número (1 município / N municípios);
  - nada é dito quando todo município desenhado tem dado (um "0 municípios sem produção"
    seria ruído vestido de achado).

  Validados por injeção de regressão, não presumidos: a subtração cega de comprimentos
  (o bug original), aceitar zero como dado, e inverter a lógica de `narrowed` — as três
  fazem a varredura falhar.

### Nota
- A varredura precisou de **uma UF distinta por caso**: `MESH_CACHE` é de nível de
  módulo e chaveado por UF, então iterar com a mesma UF serve a primeira malha a todas
  as iterações seguintes — o laço passaria a afirmar contra dados que não está
  renderizando, e **passaria por acidente**. Encontrado ao escrever o teste; registrado
  no próprio arquivo para não se repetir.

---

## [1.31.5] - 2026-08-27

### Added
- **Invariantes geométricos do mapa de calor, varridos sobre 1..15 linhas.** A barra de
  cor recebeu **cinco correções num único dia** (v1.29.3, v1.29.5, v1.30.0, v1.30.1,
  v1.31.3). Todas corretas, todas incompletas — cada uma verificada contra as duas ou
  três contagens de linhas que por acaso estavam na tela. Pior: os testes escritos ao
  lado delas fixavam o comportamento **suposto**, e um deles ("não remonta numa mudança
  de linhas do mesmo lado do limiar") afirmava exatamente a regra que produziu o bug da
  v1.31.3.

  Estes não são mais casos: são as propriedades que precisam valer para **toda**
  contagem de linhas, verificadas varrendo o espaço em vez de amostrá-lo.

  - orientação segue o limiar, sem exceções;
  - o mesmo conjunto de chaves da barra é declarado em qualquer contagem (uma chave
    presente num ramo e ausente no outro sobrevive à virada, porque `Plotly.react` deixa
    atributo aninhado omitido no valor anterior);
  - âncoras sempre em exatamente `zmin`, ponto médio e `zmax`;
  - `len: 1` sempre;
  - **toda** mudança na contagem de linhas chega a um elemento novo — o invariante que
    a v1.31.3 violava;
  - mudança apenas de dados **nunca** remonta, em nenhuma contagem;
  - uma altura explícita mantém a barra vertical.

  Validados por injeção de regressão: reintroduzir a chave só-de-orientação faz a
  varredura falhar apontando a transição exata (`1->2: REUSED`), e trocar o limiar de 5
  para 3 falha em `4:v` esperando `4:h`. Um teste que não falha com o código quebrado
  não vale nada, então isso foi verificado e não presumido.

### Fixed
- `uv.lock` ficou em 1.31.3 enquanto o `pyproject.toml` foi para 1.31.4 (o merge do
  #313 não regenerou o lockfile). Realinhado.

---

## [1.31.4] - 2026-08-27

### Fixed
- **Um resize recusado pelo Plotly escapava como rejeição não tratada.** O
  `ResizeObserver` de `_base.jsx` chamava `Plotly.Plots.resize(el)` dentro de um
  `try/catch` — **síncrono**, e portanto incapaz de ver o que a função devolve.
  Confirmado lendo `plotly.js/src/plots/plots.js`:

  ```js
  plots.resize = function(gd) {
      var p = new Promise(function(resolve, reject) {
          if(!gd || Lib.isHidden(gd)) {
              reject(new Error('Resize must be passed a displayed plot div element.'));
  ```

  Um `ResizeObserver` dispara exatamente quando o elemento colapsa, então o caminho de
  rejeição é alcançável e sobe ao console como `Uncaught (in promise)`.

  Duas guardas: a chamada é pulada quando o elemento está desconectado ou oculto
  (espelhando o próprio `Lib.isHidden`, que é `getComputedStyle(gd).display` vazio ou
  `'none'`), e um `.catch` fecha a corrida em que o elemento é escondido **entre** essa
  checagem e a do Plotly.

### Nota de método
- **A premissa que motivou esta correção não se confirmou.** Ela dizia que "toda view
  com gráfico registra erros no console ao carregar" — texto escrito a partir de uma
  sessão de horas com HMR e trocas de branch acumulados. Num servidor limpo o erro não
  reproduz: nem em carga inicial, nem em trocas de perspectiva, nem sob HMR, nem com a
  aba em segundo plano, nem sob redimensionamento do viewport.

  A correção fica porque o defeito é verificável **lendo o fonte da biblioteca** — um
  `try/catch` síncrono não captura uma promessa rejeitada. Mas não deve ser creditada
  por consertar um sintoma reproduzível: o gatilho exato permanece desconhecido, e
  provavelmente não afeta produção.

---

## [1.31.3] - 2026-08-27

### Fixed
- **O mapa de calor mantinha a geometria antiga ao reduzir o número de linhas.**
  Selecionar uma única região na Geografia deixava o gráfico com o layout de cinco:
  faixa de **105px para uma linha** dentro de um gráfico de 132px, e a barra de cor
  **encalhada em y=-76**, acima do card e fora de vista — só o rótulo "R$" aparecia,
  solto sobre a faixa.

  `Plotly.react` **não refaz o layout quando a altura do contêiner muda**. A `key` de
  remontagem introduzida na v1.29.5 cobria apenas a virada de orientação, e 5 regiões →
  1 região permanece horizontal (o limiar é ≤ 5): a orientação não mudava, então não
  havia remontagem, e o gráfico ficava com a geometria de cinco linhas.

  A `key` passou a incluir a **altura resolvida**. Qualquer mudança na contagem de
  linhas move a altura, então cobre o caso que a chave de orientação não enxerga. Os
  dois gatilhos continuam sendo mudanças deliberadas de seleção, nunca um laço de
  render — a garantia está fixada em teste: mesma geometria, mesmo elemento.

  Verificado nas duas direções: 5 → 1 região (faixa 105px → 16px, barra y=-76 → y=92
  com largura total) e 1 → 5 → 12 UFs, terminando na barra vertical à direita.

### Nota
- **O teste que deveria ter pego isso afirmava o contrário.** Ele dizia "não remonta
  numa mudança de linhas do mesmo lado do limiar" — exatamente o comportamento que
  produziu o bug. Foi reescrito para afirmar o oposto, com o motivo registrado, e a
  garantia de "não remontar à toa" migrou para o caso que de fato importa: geometria
  inalterada.

---

## [1.31.2] - 2026-08-27

### Fixed
- **"Por banco de dados" nomeava as MÉTRICAS no seletor de séries cruzadas.** Na
  perspectiva "Cruzamento entre fontes" o nível do meio saía como
  `…produtos agrícolas: Valor da produção (IBGE PEVS) × Valor exportado (FOB) (MDIC
  COMEX)` — indicadores sob um rótulo que promete bancos, e um detalhe que já pertence
  ao nível "Consulta detalhada".

  Essa perspectiva não tem `sources` fixas (o pesquisador monta as séries), então o
  fallback lia o rótulo das séries. Agora os bancos são derivados das séries escolhidas
  e **deduplicados** — duas métricas do mesmo banco não o listam duas vezes. Resultado:
  `: IBGE PEVS · MDIC COMEX.`, igual às perspectivas cruzadas de fontes fixas.

  Encontrado abrindo o modo Multi-fonte, o único caminho da citação que fora projetado
  sem especificação e nunca visto na tela.

---

## [1.31.1] - 2026-08-27

### Changed
- **O título da obra vai em negrito na referência**, conforme a ABNT NBR 6023:2025 — e
  **o subtítulo não**. Na opção "Por banco de dados" isso significa que
  `Dashboard de análise histórica de produtos agrícolas` fica em negrito e
  `: IBGE PEVS` não: é justamente a distinção entre título e subtítulo que a norma faz.

  Cada nível passou a ser montado em **três partes** (`head` / `title` / `rest`) em vez
  de uma string única. Uma string só poderia ser re-dividida por adivinhação sobre onde
  o título termina; com a fronteira explícita, o negrito cai sempre no lugar certo.

- **"Copiar referência" leva o negrito junto.** `writeText` entrega texto puro, e o
  destino real deste botão é um editor de texto — onde o título destacado é exatamente o
  que a norma exige. Sem isso o pesquisador reaplicaria o negrito à mão toda vez.

  Agora escreve `text/html` **e** `text/plain` via `ClipboardItem`: o Word/Docs pega o
  trecho formatado, e um destino de texto puro (um `.bib`, um terminal) recebe os mesmos
  caracteres. Onde `ClipboardItem` não existe, cai no `writeText` de antes — uma
  referência sem negrito é melhor que nenhuma.

  Os `&` do permalink são escapados no HTML: sem isso o destino da colagem os interpreta
  como entidades e corrompe em silêncio o link que o leitor deveria seguir.

---

## [1.31.0] - 2026-08-27

O modal "Citar painel" passa a oferecer **três níveis de detalhe** para a referência.

### Added
- **Seletor de nível de detalhe** (radiogroup) acima do bloco da referência ABNT NBR
  6023:2025, com o texto atualizando reativamente:

  - **Ferramenta geral** *(padrão)* — cita o dashboard como ferramenta, sem banco e sem
    filtros. É o caso comum numa seção de métodos, e o único que o leitor consegue usar
    sem ter um permalink filtrado à frente.
  - **Por banco de dados** — acrescenta a fonte consultada após dois-pontos
    (`…produtos agrícolas: IBGE PEVS.`).
  - **Consulta detalhada** — banco, perspectiva, recorte, produtos, UFs, qualidade,
    faixa de valor e convenções métricas.

  A referência era uma string única que concatenava o banco **e** todos os filtros
  ativos. Essa é a citação certa para "analisei exatamente este recorte" e a errada para
  "usei esta ferramenta" — uma seção de métodos não deveria mandar o leitor percorrer
  uma lista de UFs.

  Os três compartilham autoria, título e rodapé de publicação, de modo que só possam
  diferir onde devem: em quanto do painel descrevem.

- Numa perspectiva **cruzada** não há banco único, então o nível "Por banco de dados"
  nomeia as fontes que ela cruza. Omiti-las tornaria o nível do meio idêntico ao geral.

### Changed
- **Título único, em caixa de sentença, nos três níveis.** A consulta detalhada trazia
  uma variante em caixa de título (`Dashboard de Análise Histórica…`), então as
  referências discordavam sobre o nome da obra que citam. Caixa de sentença é também a
  forma da NBR 6023:2025. Autoria e título passaram a sair de constantes únicas, e não
  de literais repetidos em três ramos.
- **O botão "Copiar referência" copia o nível selecionado**, não mais a versão detalhada.
- **A abertura do modal descreve a escolha**, em vez de prometer "o painel exatamente
  como exibido" — o que passou a valer apenas para um dos três níveis.

### Unchanged
- **A citação no texto continua `(Embrapa, [ANO])`.** A NBR 10520:2023 grafa o autor na
  chamada com inicial maiúscula, enquanto a NBR 6023:2025 mantém a entidade em caixa alta
  no corpo da referência — as duas normas são complementares, e a diferença de caixa
  **não** é inconsistência. Registrado no código e em teste porque parece um erro à
  primeira vista: foi "unificado" para caixa alta durante o desenvolvimento desta versão
  e revertido em seguida.
- **O `Disponível em:` segue sendo o permalink completo** nos três níveis.

---

## [1.30.1] - 2026-08-27

### Fixed
- **O limiar que decide a orientação da barra de cor era baixo demais.** Estava em 3
  linhas, um número que eu havia estimado, não medido. Com **4 linhas** a barra vertical
  saía com **44px de altura** para três rótulos de ~12px cada — legível, mas encostando
  um no outro.

  Medido e ajustado para **5**: aos 6 o gradiente tem ~92px, onde os rótulos respiram.
  Abaixo disso a barra vai para a horizontal, onde um mapa de calor de poucas linhas tem
  largura de sobra. Verificadas as duas fronteiras: 5 linhas → horizontal com gradiente
  de 781px e nenhuma colisão; 6 linhas → vertical com 92px.

  Encontrado ao fechar a mesma lacuna que deixou o bug da v1.29.5 passar: eu havia
  verificado os estados extremos (1 linha e 12), nunca a vizinhança do limiar.

---

## [1.30.0] - 2026-08-27

A barra de cor dos mapas de calor reconstruída como **legenda**, não como eixo.

### Changed
- **Âncoras fixas em vez de números redondos soltos.** Os ticks vinham do gerador de
  eixo (`ptBrValueTicks`), que escolhe passos redondos e deixa o eixo passar do dado —
  correto para um eixo, errado para uma legenda. Sobre uma escala terminando em ~134 mi
  ele emitia `0 / 50 mi / 100 mi`, que caíam em 0%, 37% e 75% da barra, **sem nada
  marcando o topo**. A primeira pergunta de quem olha um degradê é "o que significa a
  cor mais escura?", e era exatamente o valor que a legenda nunca mostrava.

  Novo helper `colorbarAnchors(min, max)` em `_base.jsx`: sempre três âncoras — limite
  inferior, centro e limite superior — em 0%, 50% e 100%. Os rótulos continuam passando
  por `ptBrMagnitude`, então leem "134 mi" na mesma escada de todo o resto.

- **A barra ocupa a extensão inteira na direção que tem espaço** (`len: 1`): a altura do
  gráfico quando vertical, a **largura** quando horizontal. Uma barra atarracada boiando
  num card largo lê como sobra, não como chave das cores.

- **A unidade sai do meio do gradiente.** Ao lado de uma barra vertical o Plotly rotaciona
  o título 90°, e "R$" ficava deitado entre dois ticks, parecendo mais um deles. Agora
  vai acima na vertical e, na horizontal, logo acima da barra.

- **A barra horizontal é ancorada ao CONTÊINER**, não à área de plotagem. Num mapa de
  calor de uma linha essa área tem ~16px de altura, então um deslocamento relativo a ela
  movia a barra 7px — direto para cima dos rótulos de ano, com a unidade caindo sobre
  "2005". Medido: título em `t:72-85`, barra em `t:92-104`, rótulos de ano em `t:33-46`,
  sem colisão.

- **`zmin`/`zmax` fixados explicitamente** na trace. Deixados para o Plotly inferir, as
  pontas da barra e os rótulos que as descrevem eram derivados por caminhos diferentes;
  agora são provadamente os mesmos números.

- **`MonthYearHeatmap` (Sazonalidade) recebeu o mesmo tratamento** — tinha os dois
  defeitos reportados para o outro: unidade rotacionada no meio do gradiente e nenhuma
  âncora, então as pontas da escala nunca eram rotuladas e os ticks caíam nas letras SI
  inglesas do Plotly ("14B" ao lado do "14 bi" do próprio app).

---

## [1.29.5] - 2026-08-27

### Fixed
- **A barra de cor do mapa de calor ficava atravessada no meio do gráfico ao voltar da
  visão de uma UF para a nacional.** Regressão introduzida na v1.29.3, junto com a
  própria barra adaptativa.

  `Plotly.react` **reaproveita o grupo SVG `.colorbar`** quando a orientação muda.
  Tanto `gd.data` quanto `gd._fullData` terminavam corretos (`orientation: 'v'`,
  `x: 1.02`, `len: 1`) — medido — enquanto o grupo **desenhado** mantinha a geometria
  horizontal: `x=309 w=297` dentro de um gráfico de 937px, ou seja, uma barra encalhada
  no meio do mapa de calor. Selecionar uma UF e depois desmarcá-la caía exatamente
  nisso.

  A hipótese óbvia — de que o `react` não reseta atributos aninhados omitidos — estava
  **errada**, e a medição foi o que mostrou: o estado resolvido estava certo o tempo
  todo; quem não se redesenhava era o SVG. A correção é uma `key` de React no `<Plot>`,
  de modo que cruzar o limiar entrega ao Plotly um elemento limpo. A remontagem só
  acontece na virada de orientação, não em qualquer mudança de dado — um re-plot por
  seleção deliberada, não por render.

  Verificado ao vivo em três ciclos UF↔nacional: barra vertical em `x=869 w=60` (borda
  direita) e horizontal em `x=120 w=442` (abaixo), estável em todas as idas e voltas.

---

## [1.29.4] - 2026-08-27

### Changed
- **O mapa de região não desenha mais as divisas estaduais dentro de cada bloco.**
  A unidade de análise ali é a macrorregião; mostrar os estados que a compõem
  contradiz isso e faz o mapa parecer um mapa de UF mal pintado.

  Nova prop `seamless` do `BrazilChoropleth`: o contorno passa a ser pintado com a
  **cor de preenchimento de cada estado** em vez de branco. A divisa entre dois
  estados da mesma região fica da mesma cor dos dois lados — some — enquanto o degrau
  entre regiões continua exatamente onde as cores já mudam.

  **Não é um dissolve de verdade**, e é de propósito: unir os polígonos exigiria uma
  operação de topologia em tempo de execução e não compraria nada aqui. Também não se
  desenha nada falso — nenhuma fronteira é inventada, apenas se esconde uma onde os
  dois lados já têm a mesma cor. O grão de UF segue com a divisa branca, que ali é a
  informação.

---

## [1.29.3] - 2026-08-27

Três ajustes de interface na Geografia, todos reportados por uso real.

### Fixed
- **O "Ver raio-x" não parecia clicável.** Foi entregue com a classe `seg-opt`, que só
  tem aparência dentro de um grupo segmentado — solto num cabeçalho de card, era texto
  sem chrome nenhum. Agora é `btn-secondary` (borda, superfície, hover, `cursor:
  pointer`) com um ícone, que diz "isto abre uma leitura detalhada" onde o rótulo
  sozinho não dizia.

- **A barra de cor do mapa de calor colapsava com poucas linhas.** Ela ocupa a altura do
  *gráfico*, e com uma única UF selecionada o gráfico tem ~68 px: o título da unidade e
  os ticks se sobrepunham num borrão ilegível — justamente no recorte mais comum que
  existe. Com até 3 linhas a barra vira **horizontal, abaixo do gráfico**, onde largura
  é o que um mapa de calor de uma linha tem de sobra. Acima disso segue vertical. A
  escada de ticks pt-BR é a mesma nas duas orientações, e uma altura passada
  explicitamente pelo chamador continua sendo respeitada.

### Added
- **Mapa para a granularidade "Região"** — era a única das três sem mapa, ou seja, o
  grão mais grosso era o único que não dava para ver. Não há geometria de macrorregião
  para vendorizar e não é preciso: uma macrorregião é exatamente uma união de UFs, então
  o mapa pinta **cada UF com o total da SUA região**, desenhando os cinco blocos sobre a
  malha que já existe. Os valores vêm do mesmo `regScaled` das barras, então mapa e
  barras compartilham base e escala.

  Vem com o mesmo alternador **Mapa | Barras** que a UF tem — cinco blocos leem um
  ranking pior do que cinco barras, então nenhuma das duas visões é a resposta sozinha.

  Clicar numa região estreita para **as UFs dela**: `regions` sozinho é pai de cascata
  (dirige as opções do menu de filtro), enquanto `states` é o que chega ao dado — os
  dois são definidos, senão o chip se moveria e mais nada.

---

## [1.29.2] - 2026-08-27

Varredura em busca de outros casos do bug "4361,4%" — testes cujo *stub* diverge da
implementação real e por isso abençoam o bug. **Não havia outros.** Mas a causa raiz
apareceu, e é a API, não os stubs.

### Resultado da varredura
- **Todos os call sites estão corretos.** Auditados um a um os 15 usos de `fmtPct`, os
  9 de `pctBR`/aliases e os 20 de `fmtSigned` em `src/`: cada um passa o tipo certo de
  número. O `fmtPct` da v1.29.0 era o único errado e já estava corrigido.
- **Comparação estática de stubs é ruidosa demais** para essa classe (falsos positivos
  em `crossViewApplies`, `viewAppliesTo`). O método que funcionou foi executar a suíte
  **com os formatadores reais no lugar dos stubs**: as 15 falhas resultantes eram todas
  cosméticas (`60,0%` vs `60.0%`, `'2 mil'` vs `'1500'`) ou artefato do próprio
  experimento — nenhuma divergência de escala.

### Added
- **`formatterContracts.test.js`** — o único lugar que declara, de forma executável, o
  que cada formatador numérico espera receber. Existe porque o projeto tem **três**
  formatadores de porcentagem com **duas convenções opostas** e nomes que não dizem
  qual é qual:

      fmtPct(0.6)   → '60,0%'   recebe FRAÇÃO      (multiplica por 100)
      pctBR(60)     → '60,0%'   recebe PERCENTUAL  (só concatena '%')
      fmtSigned(60) → '+60,0%'  recebe PERCENTUAL

  Um stub pode sempre divergir da função real; o que não pode divergir em silêncio é o
  **contrato**. Inclui o caso errado (`fmtPct(43.614) === '4361,4%'`) fixado de
  propósito, para que o sintoma seja reconhecível na próxima vez.

### Fixed
- **`pctBR(null)` renderizava `"—%"`** — traço com unidade colada, que se lê como valor
  em vez de ausência. O irmão `fmtSigned(null)` já devolvia `'—'`, e o teste existente
  afirmava as duas coisas a três linhas de distância sem notar a inconsistência: era um
  teste de caracterização que travou a verruga em vez de questioná-la.

### Documented
- **Nota de convenção em `data.js`**, onde o autor de um call site realmente lê. Os
  nomes dos campos do payload são a proteção que já existia (`*Frac` é fração,
  `*Share`/`*Pct` é percentual) e agora está escrita.
- **`fmtPct` e `pctBR` arredondam diferente** para a mesma quantidade — `toFixed`
  (binário: `3.55` é `3.5499…` → baixo) contra `toLocaleString` (→ cima). O mesmo número
  pode sair `3,5%` numa tela e `3,6%` noutra. Inofensivo em si, mas parece discrepância
  de dado para quem compara duas views, então está fixado em teste.

---

## [1.29.1] - 2026-08-27

O seletor de território do "Perfil do território" **ignorava o filtro geográfico**.
Uma sessão filtrada em AM+SP exibia alegremente o Pará — um valor calculado sobre um
conjunto que o pesquisador havia excluído explicitamente.

### Fixed
- **O filtro define o universo; o seletor escolhe o foco dentro dele.** Os dois não
  eram redundantes, eram **conflitantes**: o seletor listava as 27 UFs
  independentemente do filtro. Agora oferece apenas territórios que o filtro admite —
  a mesma regra que o "Perfil do produto" já seguia ao limitar seus chips à cesta.
  Vale para o filtro de UF **e** para as facetas sub-UF (meso/micro/intermediária/
  imediata/município), que resolvem para um conjunto de municípios; `applyFilters`
  passou a exportar esse conjunto como `scopedCityCodes`.

- **A participação deixa de ser inventada sob recorte sub-UF.** Nesse caso a série por
  UF é um *rollup só das cidades selecionadas*, então somá-la dá o total da própria
  seleção — dividir por ele imprimiria ~100% e chamaria isso de "participação no
  país". Não há denominador nacional honesto nessa base (a grade não estreitada é
  all-products, o que misturaria bases), então o KPI diz que não dá para calcular.

- **A posição passa a ser no país, não dentro do subconjunto filtrado.** "1º de 1 UF
  na seleção" é honesto e inútil. O ranking nacional continua computável sob filtro de
  UF, porque a série por UF só é estreitada por facetas **sub**-UF.

### Added
- **Combinar territórios agora é uma pergunta que a perspectiva responde.** Quando o
  filtro nomeia mais de um lugar, o seletor oferece **"Seleção atual (N somadas)"** e
  passa a ser o padrão — o pesquisador pediu aquele conjunto, então o conjunto é a
  primeira resposta honesta; entrar num membro é um clique. A trajetória é a soma
  (legítima: mesma unidade, mesma base de deflação) e a composição é **uma** consulta
  sobre o conjunto, porque os dois leitores já aceitam listas.

  **Só quando o filtro estreita.** Sem filtro, "Seleção atual" seria o Brasil inteiro
  — que é o trabalho da Visão geral; um perfil territorial do país não perfila nada.
  Uma soma de territórios não tem posição em ranking, e o KPI diz isso.

- **Atalho "Ver raio-x" no card do mapa da Geografia**, nomeando o território que
  abriria ("Ver raio-x de PA"). As duas perspectivas são metades de uma pergunta:
  Geografia mostra como a atividade se distribui **entre** lugares, o Perfil mostra o
  que acontece **dentro** de um. O atalho não carrega lugar próprio — o perfil lê o
  mesmo filtro que a Geografia escreve. Nova ponte `window.goToView`, registrada junto
  de `patchFilter`/`openFilterMenu` e pelo mesmo motivo. **O clique no mapa segue
  intocado**: filtro barato e reversível.

---

## [1.29.0] - 2026-08-27

Nova perspectiva **"Perfil do território"**: o raio-x de um lugar. Até agora o
dashboard sabia responder "onde este produto é produzido"; passa a responder também
"o que este lugar produz".

### Added
- **Perspectiva "Perfil do território"** (`territory_profile`, em *Análise de
  distribuição*, exigindo a capacidade `geo`). É a **transposta** do "Perfil do
  produto": aquele fixa um produto e olha através dos lugares; este fixa um **lugar**
  e olha através dos produtos.

  Deliberadamente **não** foi embutida na Geografia. Geografia responde "como a
  atividade se distribui **entre** territórios" — a unidade de análise é a
  distribuição. Esta responde "o que acontece **neste** território" — a unidade é o
  lugar. Uma só perspectiva servindo as duas passaria a significar duas coisas.

  Traz, para uma UF ou um município: a trajetória histórica do lugar, sua composição
  por produto, o peso e a posição dele no país, e o pico histórico.

- **`POST /api/products-by-municipio`** — o que os cubos existentes não conseguiam
  dizer. Tanto `production_by_municipio_yearly` quanto o cubo por UF **agrupam pelo
  lugar e somam os produtos**, então desenham a trajetória de um território mas nunca
  nomeiam o que está por trás dela. Novo builder `sql.products_by_municipio` +
  `gateway.fetch_products_by_municipio` + `seam.products_by_municipio`.

  Lê o Gold direto e herda **exatamente** o contrato de custo do cubo: `cityCodes`
  não-vazio obrigatório, mesmo teto, mesmos 400s — a validação virou o helper
  compartilhado `_city_codes_or_400`, para que as duas rotas não possam divergir.
  Aplica o mesmo gate F7 de visibilidade: um produto marcado indisponível não
  reaparece só porque a pergunta mudou de "quanto aqui" para "o que aqui".

### Changed
- **A entrada é explícita, não o clique.** O clique no mapa continua sendo o que já
  era em toda parte — um filtro barato e reversível, com toggle. Navegar até um
  raio-x não é nenhuma das duas coisas, e empilhar o segundo significado no mesmo
  gesto quebraria o toggle no controle mais usado da interface. A perspectiva tem
  seus próprios seletores e **se posiciona** a partir do filtro global quando ele já
  nomeia um único lugar — então clicar numa UF e trocar de perspectiva cai no lugar
  certo.

### Honestidade
- **Participação e posição são calculadas sobre a janela selecionada**, não sobre o
  último ano. O gráfico ao lado cobre a janela inteira; duas perguntas diferentes sob
  um mesmo rótulo seria o bug.
- **O denominador nacional ignora o filtro de UF de propósito** — caso contrário a
  participação de uma sessão filtrada num único estado seria sempre 100%. O KPI diz
  qual é o denominador e qual é a janela.
- **Um município nunca toma emprestado o número da UF em silêncio:** participação e
  posição só existem por UF, e a página afirma isso quando o nível é municipal.
- **Um banco só com grão de UF declara isso** (`NotApplicableNote`) em vez de oferecer
  um nível municipal que voltaria vazio — o que se leria como "este estado não tem
  municípios produzindo", uma afirmação diferente e falsa.

---

## [1.28.3] - 2026-08-27

Os 36 testes que falhavam localmente e passavam no CI não eram flaky nem culpa do
código — era o Node 26 quebrando o `localStorage` do ambiente de teste. Agora o
ambiente se conserta sozinho.

### Fixed
- **`localStorage` volta a funcionar sob Node ≥26.** O Node 26 passou a expor um
  `localStorage` próprio, atrás de `--localstorage-file`. Sem a flag o global
  continua **definido** — como um getter que devolve `undefined` — e, como o
  ambiente jsdom do Vitest funde `window` em `globalThis`, esse getter **sobrepõe**
  o Storage que o jsdom tinha instalado. Toda chamada virava
  `Cannot read properties of undefined`, o que aparecia como **36 falhas em
  `AppShell.cov.test.jsx`** com cara de bug nosso.

  O CI roda o major do `/.nvmrc` (24), onde nada disso existe — então o sintoma só
  atingia máquina local, e custava uma hora até alguém pensar em conferir `node -v`.
  O descriptor é `configurable: true`, então o `vitest.setup.js` simplesmente
  recoloca um Storage funcional. **Escopo deliberado:** só age quando o
  `localStorage` está ausente ou inutilizável; no Node 24 a implementação do jsdom
  fica intocada.

  Medido: suíte completa no Node 26.7.0 sem nenhuma flag — **832/832**, contra 36
  falhas antes.

### Added
- `frontend/src/ui/localStorageEnv.test.js` — 4 testes fixando o invariante "todo
  teste recebe um `localStorage` funcional, em qualquer major do Node", inclusive
  que uma chave ausente devolve `null` e não `undefined` (a UI ramifica em
  `=== null`).
- Campo `engines` (`node: ^24`) em `frontend/package.json`, alinhado ao `/.nvmrc` e
  ao estágio de build do Dockerfile, com nota explicando por que os três andam
  juntos.

---

## [1.28.2] - 2026-08-27

O `geo mesh check` nunca tinha rodado. Disparei manualmente pela primeira vez e ele
falhou — expondo três defeitos que só apareceriam em outubro, e o pior deles em
silêncio.

### Fixed
- **Falha de rede não é mais lida como "a malha divergiu".** O `--check` saía `1`
  em qualquer erro e o workflow fazia `stale=$([ $code -ne 0 ])`, então um timeout
  do IBGE abriria uma issue anunciando que o IBGE mudou o conjunto de municípios.
  Isso contradiz o desenho declarado no cabeçalho do próprio workflow ("MEDE, e só
  abre issue quando algo divergiu de fato") e um alarme falso trimestral é a forma
  mais rápida de ensinar todo mundo a ignorar o alerta que importa.

  Agora há três desfechos distintos: `0` em dia, `1` divergiu, `2` **não deu para
  medir**. O passo que abre issue roda só no `1`; o `2` falha com `::warning` e diz
  explicitamente que não afirma nada sobre a malha.

- **A API de localidades do IBGE dá timeout a partir dos runners do GitHub** (a
  primeira execução morreu com `ConnectTimeout` após 120 s; da estação de trabalho
  responde normalmente). `_fetch_roster` agora tenta 4 vezes com backoff
  exponencial e timeout de 30 s por tentativa, e devolve `None` em vez de levantar
  — para que o chamador consiga separar "não medi" de "divergiu".

- **O passo que abre a issue estava quebrado.** `--repo "\$REPO"`, `--assignee
  "\$OWNER"` e `--body-file "\$body_file"` escapavam o `$`, então o bash passava
  as strings literais `$REPO`/`$OWNER`/`$body_file`. Confirmado na execução real:
  `open $body_file: no such file or directory`. O `--title` logo acima usava
  `$(date ...)` sem escape e expandia certo — a inconsistência denunciava o
  acidente. Esse caminho só roda no momento exato em que a malha diverge, ou seja,
  falharia justamente quando fosse necessário.

### Added
- Seis testes em `tests/test_refresh_municipio_geojson.py` fixando a separação
  entre `EXIT_UNREACHABLE` e `EXIT_DRIFTED`, o retry com backoff, e o fato de que
  o caminho "não deu para medir" **não** manda ninguém rodar `make refresh-geo`.

---

## [1.28.1] - 2026-08-27

Higiene de dependências: o PR semanal do eslint 10 **não era instável, era impossível**.
Ele reabria toda semana e queimava a matriz de CI inteira para morrer no `npm ci`.

### Changed
- **`.github/dependabot.yml`** passa a ignorar majors do **`eslint`** no updater do
  frontend. O motivo não é risco de migração, é impossibilidade: o peer range do
  `eslint-plugin-react` termina em `^9.7` e a **7.37.5 ainda é a última release**
  publicada, então o `npm ci` aborta com `ERESOLVE` antes de rodar um único teste —
  e nenhuma mudança de código ou config **deste** repositório levanta um limite de
  peer dependency de terceiro. O agrupamento minor/patch (v1.24.x) já tinha tirado o
  eslint 10 do PR agrupado, mas majors excluídos continuam chegando como PR
  individual **por desenho**, então o #291 renascia sozinho: três execuções falhas
  só em 2026-08-27.

  O bloco de `ignore` segue o padrão que o arquivo já usa para `python`/`node`:
  registra o **porquê** e a **condição de saída**. Quando o `eslint-plugin-react`
  publicar uma release que aceite eslint 10, remover o bloco e subir os dois juntos
  — o `eslint-plugin-react-hooks@7.1.1` já aceita `^10.0.0`. Bumps minor/patch do
  eslint 9.x continuam fluindo normalmente.

---

## [1.28.0] - 2026-08-27

Os três leitores que **ignoravam o filtro de UF** passam a honrá-lo. Ficou registrado
como achado na v1.27.0: `/api/product-uf`, `/api/productivity` e
`/api/cross/export-coef` não aceitavam recorte por estado, então seus mapas mostravam
as 27 UFs enquanto o resto da sessão estava filtrado.

### Fixed
- **`/api/product-uf`** (Perfil do produto · "Onde X é produzido", e o mapa por UF do
  Rebanho) e **`/api/productivity`** (Produtividade) passam a aceitar `states`;
  `production_by_uf`, `comex_by_uf` e `productivity` ganharam `uf_codes`.

  O recorte é aplicado **antes** do pin de ano mais recente, de propósito: com filtro
  de UF ativo o ano de referência deve ser o último que **aqueles** estados têm, não o
  do país. Um estado cuja série termina antes fixaria num ano sem linhas e leria como
  tendo parado de produzir.

- **`/api/cross/export-coef`** narra **os dois lados da razão** — produção (PEVS) e
  exportação (COMEX) — mais o agregado. Estreitar só a produção dividiria a saída do
  estado pela exportação do país inteiro e desinflaria o coeficiente em silêncio: um
  número errado, não um número menor. Verificado: Castanha-do-pará dá **35,5%**
  nacional e **52,0%** recortado no PA — exatamente o que o quadrinho do PA já
  mostrava no mapa nacional.

- **Efeitos de busca que não refariam a consulta.** Os dois consumidores de
  `/api/product-uf` montam o fetch num `useEffect` cujo array de dependências não
  tinha o recorte de UF — a requisição sairia com o filtro novo só por acidente de
  re-render. Passam a depender de uma chave primitiva derivada (`ufScopeKey`), que
  preserva a distinção entre "sem filtro" (`null`) e "nenhum selecionado" (`''`);
  depender do array cru refaria a busca a cada render.

### Changed — rótulos que precisavam acompanhar
Encanamento sozinho teria criado uma desonestidade **nova**, pior que a de antes:
rendimento e coeficiente são **razões**, então recortar não devolve "menos" do mesmo
número — devolve **outro** número.

- **Produtividade**: "Rendimento nacional" vira "Rendimento no PA" quando há recorte.
  Medido: arroz dá **6.728 kg/ha** nacional e **3.276 kg/ha** no PA — menos da metade.
  Sem o rótulo, a tela mostraria 3.276 kg/ha sob a palavra "nacional".
- **Coeficiente de exportação**: "Coeficiente nacional" vira "Coeficiente · PA".
- `ui/geoSelect.js` ganhou `geoScopeLabel(states)`, a fonte única dessa palavra.

### Changed — de onde vem o recorte no cruzamento
O **Coeficiente de exportação** ganhou seletor **próprio** de UF (`UfScopePicker`),
não o filtro global — igual à view irmã Preço porteira×FOB, que já fazia assim.

As perspectivas cruzadas **escondem a barra de filtros** de propósito (`isDataView`
as exclui: "no single-banco filter surface"). Fazê-la honrar silenciosamente um
filtro que o pesquisador não vê nem controla naquela tela estreitaria o mapa por um
motivo invisível na página — o oposto do que esta série de versões vem corrigindo. O
recorte server-side é o mesmo; só a origem do valor muda.

---

## [1.27.0] - 2026-08-27

Leva à **app inteira** o que a v1.25.0 tinha entregue só à Geografia, e fecha a
inconsistência que aquela versão criou: o coroplético passou a classificar por
quantil e a grade de blocos ficou na escala linear — **os dois lados de um mesmo
toggle Mapa/Blocos, sobre os mesmos números, com classificações diferentes**.

### Fixed
- **A escala linear seguia viva em 6 das 7 renderizações de mapa.** `BrazilTileMap`
  é usado por Geografia, **Visão geral, Rebanho, Produtividade, Qualidade e as
  análises cruzadas** — todas continuavam com o `(v-min)/(max-min)` que colapsa em
  série concentrada. Medido no valor real por UF do PEVS 2024: **21 das 25 UFs com
  produção caíam na faixa mais clara** e 4 das 7 faixas nunca eram usadas. Agora usa
  o mesmo quantil dos dois mapas maplibre, e a legenda mostra a faixa que cada cor
  cobre (faixa sem ninguém fica esmaecida em vez de ganhar um intervalo inventado).
- **A tarja cinza do mapa municipal podia contar errado.** Contava por diferença de
  tamanhos (`malha.length - dados.length`), o que soma indevidamente um município
  que tenha dado mas nenhum polígono — e, com alguns deles, chegaria a número
  negativo. Passa a comparar os códigos de fato.

### Added
- **Clique-para-filtrar na Visão geral e na Qualidade.** Clicar numa UF filtra o
  painel inteiro; clicar de novo limpa — o mesmo gesto da Geografia. A regra saiu de
  dentro da view para `ui/geoSelect.js`, compartilhada pelas três, incluindo a parte
  fácil de errar: selecionar uma UF **zera** os recortes sub-UF/região/nação, para
  que um recorte antigo (ou de um link compartilhado) não se cruze silenciosamente
  com o clique e mostre menos do que o estado pedido.

  **Deliberadamente NÃO ligado** em Rebanho, Produtividade e Coeficiente de
  exportação: os leitores dessas três (`/api/product-uf`, `/api/productivity`,
  `/api/cross/export-coef`) **não aceitam filtro de UF**, então o clique mudaria o
  filtro global e o mapa não reagiria — o controle-que-parece-agir-e-não-age que
  esta mesma auditoria condenou. Fica registrado como achado: os mapas dessas três
  views ignoram o filtro de UF ativo.

- **`make refresh-geo`** — re-busca os DOIS artefatos territoriais versionados de
  uma vez (o seed código→ancestralidade e as 27 malhas municipais). Nenhum dos dois
  scripts tinha alvo no Makefile.

- **Verificação automática de malha vencida** (`geo-mesh-check.yml`, trimestral).
  A malha é versionada, então envelhece em silêncio: o IBGE cria municípios a cada
  ciclo e nada no app notaria — o município novo simplesmente nunca seria desenhado
  nem apareceria no filtro, enquanto a produção dele seguiria contando nos totais.
  Diferente do lembrete de `reconcile` ao lado, este **não cutuca: mede**, e só abre
  issue quando algo divergiu de fato. `refresh_ibge_municipio_geojson.py --check` é
  uma requisição pequena ao roster do Localidades, não os 27 downloads pesados.

### Notes — o que a verificação encontrou
- **As duas APIs do IBGE discordam entre si.** O roster (Localidades) lista **5571**
  municípios; a API de malhas desenha **5570**. O ausente é **Boa Esperança do
  Norte/MT (5101837)**, criado em 2023 — o mesmo município que o script irmão já
  registrava como tendo só o ramo sub-UF de 2017. Não é defasagem nossa e re-baixar
  a malha não o traz, então ele está em `ROSTER_ONLY`, documentado, e o `--check`
  passa verde (um check permanentemente vermelho é um check que se aprende a ignorar).

  Consequência no produto: ele é **selecionável no filtro** (a cascata vem do roster)
  e **não pode ser desenhado**. O `MunicipioChoropleth` agora avisa explicitamente
  quando um município com dado não tem malha, em vez de somá-lo ao cinza. Hoje a nota
  não aparece porque ele ainda não tem nenhuma linha no Gold.

- **O mapa municipal já valia para PAM e PPM** — nenhuma linha de código foi
  necessária. `ViewGeography` é o mesmo componente para todo banco, os três IBGE já
  declaram `geoLevel: 'municipio'` e já estavam em `_MUNICIPIO_SOURCES`. Verificado:
  PAM desenha os 399 municípios do PR, PPM os 141 de MT.

- `ufColorScale` (a versão linear) foi **removida** — ninguém mais a importava.

---

## [1.26.0] - 2026-08-27

Fecha o passo 7 do `PLANS/geo_subregions.md`, aberto desde 2026-06: **o recorte sub-UF
finalmente aparece no mapa**. Os cinco níveis de filtro abaixo da UF narravam os DADOS
corretamente desde a v1.5.2, mas o coroplético continuava pintando o estado inteiro —
o filtro mais fino do produto não tinha efeito visível nenhum.

### Added
- **Mapa municipal com polígonos reais.** Ao escolher a granularidade *Município* com a
  seleção resolvida a uma única UF, o mapa passa a desenhar os municípios daquele estado,
  coloridos pela métrica ativa. É a leitura que o grão UF escondia: a produção é
  concentradíssima — medido em 2024, **os 100 maiores municípios de 5.570 respondem por
  71% do valor nacional**, e o mapa por UF pintava o Pará inteiro de escuro por causa de
  Portel e Prainha.

  - Geometria vendorizada por `scripts/refresh_ibge_municipio_geojson.py`, a partir da API
    de malhas v3 do IBGE (`intrarregiao=municipio&qualidade=minima`), em
    `frontend/public/geo/municipios/<UF>.json` — 27 arquivos, ~2,9 MB, de 7 a 69 KB
    gzipados por UF. O Vite copia `public/**` para `dist` e o Flask serve como estático,
    então não há rota nova.
  - **A chave de junção já existia dos dois lados**: o `codarea` do IBGE É o `city_code` de
    7 dígitos que o projeto usa em `dim_geo_municipio`, no `/api/geo-mesh` e no cubo
    `/api/municipio-yearly`. Nenhuma tabela de-para foi necessária.
  - **Uma malha por UF, não uma do Brasil** — e isso é um limite deliberado, não um
    primeiro incremento: a malha municipal do país inteiro tem ~836 KB gzipados (mais
    pesada que o próprio maplibre) e 5.570 polígonos no zoom nacional são manchas de 2-3
    px. Quando a seleção abrange mais de um estado, o ranking continua — ele é correto em
    qualquer amplitude.
  - Clicar num município filtra por ele; clicar de novo limpa. Alternador **Mapa/Ranking**
    na granularidade Município.
  - Vendorizada em vez de buscada do IBGE em runtime: o mapa é deliberadamente sem
    basemap para funcionar offline, e depender de um host externo em tempo de leitura
    abriria mão disso (mais uma entrada de CSP e um risco de disponibilidade) por um dado
    que muda duas vezes por década.

- **Recorte de ano no cubo municipal.** `/api/municipio-yearly` passa a aceitar `y0`/`y1`.
  O `sqlbuild` sempre aceitou os limites — só a rota e o seam nunca os repassavam, então
  toda requisição trazia os ~39 anos. Medido sobre os 5.570 municípios: **153.634 linhas /
  16,9 MB / 28 s** sem limite. A view agora pede apenas a janela do filtro do pesquisador.

### Fixed
- **`fillColorExpression` fixava a propriedade `uf`.** O mapa municipal compilava uma
  expressão `match` perfeitamente válida que **não casava com nada** — todo município caía
  no fallback e o estado inteiro pintava cinza de "sem dado", sem erro nenhum para
  explicar. A propriedade agora é parâmetro (`codarea` no caso municipal); o padrão segue
  `uf`, então o mapa por UF não muda.
- **A escala por quantil degenerava com poucas unidades.** Com uma única UF selecionada
  (o caso que o próprio clique-no-mapa da v1.25.0 cria), `rank/n` colocava o único valor
  na posição 0 — a faixa **mais clara** — para um número que é simultaneamente o menor e o
  maior. Abaixo do número de faixas, os valores passam a ocupar as faixas mais **escuras**.
- **O corte de top-100 dos municípios era um limite de exibição vivendo no motor de
  dados.** Assim que o mapa passou a desenhar a partir dessas linhas, virou erro de dado:
  todo município da posição 101 em diante não tinha linha para casar, então o mapa o
  pintava como "sem produção registrada" e o contava na tarja cinza — no Pará, um falso
  "44 municípios sem produção" para uma UF de 144. O `dataFilters` devolve o conjunto
  completo; quem corta é a view, e só o ranking.
- **A tarja cinza afirmava o que o dado não dizia.** Com um recorte sub-UF ativo, os
  municípios sem cor estão **fora do recorte**, não sem produção. As duas situações agora
  têm textos distintos.
- **Rótulos por código em vez de nome.** A malha do IBGE (`/api/geo-mesh`) só era buscada
  no caminho de fallback de UF única, então o caminho do recorte sub-UF ficava sem nomes —
  o popup do mapa e as linhas do mapa de calor mostravam `1503606 · PA` em vez de
  `Itaituba · PA`.

### Notes
- `MunicipioChoropleth` compartilha `choroplethScale.js` com o mapa por UF, então as duas
  leituras usam a mesma classificação e a mesma legenda.
- O bundle principal cresceu **7 KB** (523 → 530 KB) — a geometria não entra nele.

---

## [1.25.0] - 2026-08-26

Auditoria completa da perspectiva **Geografia** (23 achados verificados no build de
produção contra o BigQuery real) e correção de todos eles. O denominador comum era o
mesmo: **a perspectiva mostrava mais do que declarava** — um ano em três cartões e trinta
e nove em um quarto, a cesta em três e todos os produtos no mapa de calor, cinco níveis de
recorte no filtro e um só desenhado no mapa.

### Fixed — confiabilidade do número

- **O mapa de calor ano × UF ignorava a cesta de produtos.** O mapa, o Top 10 e as barras
  por região passam a ler o cubo cesta×UF assim que ele carrega; `heatRows` nunca trocava
  de fonte — lia `dataStore.get(banco).ufYearly`, que é **sempre todos os produtos**. Pior:
  a nota honesta `notFilteredByBasket` era acionada por `basketActive && !useCube`, ou
  seja, aparecia *antes* do cubo chegar e sumia exatamente quando mapa e heatmap passavam a
  discordar. Medido com a cesta = Açaí (fruto), PA 2024: mapa **R$ 865 mi** (correto)
  contra célula do heatmap **R$ 2.908 mi** (os 7 produtos) — razão de 3,4×, sem aviso
  nenhum na tela. `applyFilters` já calculava a grade correta (`geoSource`) mas não a
  devolvia; agora exporta `ufYearlySeries`/`muniYearlySeries` e o heatmap lê a MESMA fonte
  que o mapa. Passa a existir uma só grade (UF × ano) nesta perspectiva.

- **"Produtos do estado" somava 39 anos numa página onde todo o resto mostrava um ano.**
  O cartão consome `/api/products-by-uf`, que faz `sum(value)` sobre a janela inteira, e
  não carregava rótulo de período — enquanto os outros três cartões carregavam
  `mapYearTag`. Na mesma tela: "Maiores estados produtores · **2024**" → PA R$ 2,9 bi, e
  "Produtos do estado (PA)" → Madeira em tora **R$ 136 bi**. Agora o cartão pede o mesmo
  `mapYear` do resto da perspectiva e o declara no overline.

- **Pseudo-origens entravam nos cartões por UF e ficavam de fora do cartão por região.**
  `ViewOverview` e `ViewConcentration` filtram por `isRealUf`; a Geografia não. A linha
  `ND` (não declarado) do COMEX entrava em `top10ufs`, no `sharedMax` e no heatmap, e sumia
  do `regionData` (não tem região) e do coroplético (não casa com polígono). Medido sem
  filtro: soma das UFs **237.622** contra soma por região **234.888** — diferença de
  **2.734**, exatamente a linha ND, sem nota nenhuma. Aplicado o mesmo guarda-corpo das
  perspectivas irmãs.

- **"Exportar CSV" exportava sempre a tabela por UF**, mesmo com a lista de municípios na
  tela: `csvExport` decidia pelo id da perspectiva (`'geo'`), nunca pelo `scope`. Quem
  recortava 14 municípios e clicava em exportar recebia a linha única do PA. Agora ramifica
  por escopo (região / UF / município), mantendo as colunas `ano` e `escopo_produto` que já
  carregavam os avisos da tela.

### Fixed — motor da cascata geográfica

- **Impureza de updater no `useGeoCascade`.** `reconcile` escrevia
  `prevEligible.current[level] = ok` **dentro da função passada ao `setState`**. Updaters
  precisam ser puros: o StrictMode do React os invoca duas vezes, e a segunda invocação
  lia o ref já sobrescrito pela primeira, concluía que o nível "não estava seguindo" os
  pais e desfazia o refill. Percurso "Estados → Limpar → marcar Pará": build de dev deixava
  Mesorregiões **0/6** e Municípios **0/0**; o de produção acertava (**6/6**, **144/144**).
  Não afetava o usuário final, mas quebrava a cascata para quem desenvolve e é exatamente
  o tipo de coisa que reaparece sob renderização concorrente.

- **Limpar uma coluna zerava as colunas abaixo dela — discordando do motor de dados.**
  Um clique em "Limpar" nas Mesorregiões levava Microrregiões e Municípios a
  `0/0 · Nenhum resultado`, porque `passes()` lia "0 selecionados" como "nada passa".
  Mas o `dataFilters.js` **já** trata um facet vazio como "sem restrição" — a cascata e o
  motor que aplica o filtro discordavam sobre a mesma seleção. Alinhados. (A assimetria
  de *código em branco* entre os dois segue deliberada e documentada — é outro eixo.)

### Fixed — leitura do mapa

- **Rolar a página sobre o mapa dava zoom no mapa.** `scrollZoom` do maplibre ficava
  ligado e não havia como voltar ao enquadramento: três rolagens reduziam o Brasil a um
  terço do quadro e a página não se movia. Desligado (o zoom segue nos botões +/− e no
  pinch), e adicionado um controle de **reenquadrar**.

- **A escala do coroplético colapsava.** Linear sobre o máximo: com a distribuição real do
  PEVS 2024, **23 das 25 UFs com produção caíam no nível mais claro** e 3 dos 6 níveis da
  rampa nunca eram usados — Maranhão (386) e Sergipe (1) recebiam exatamente a mesma cor.
  Trocada por classificação **por quantil** (`ufColorScaleQuantile`), que usa os 6 níveis.

- **A visualização padrão não tinha legenda; a alternativa tinha.** "Blocos" trazia rampa
  e faixa mín–máx, "Mapa" (o padrão) não trazia nada. Legenda adicionada ao coroplético,
  reusando o mesmo markup, com os cortes de cada faixa no `title`.

- **A barra de cor do mapa de calor falava inglês** (`14B · 12B · 8B`) enquanto o eixo do
  gráfico ao lado lia `3 bi · 2 bi · 1 bi`. O projeto já tinha a função para isso
  (`ptBrValueTicks`, escrita justamente para matar o "15G vs 15 bi") — ela só nunca havia
  chegado a este colorbar.

- **A lista de municípios usava um formato numérico que não existe em nenhum outro lugar
  do painel**: `113.008.308,7 R$` (símbolo depois do número, uma casa decimal irrelevante
  na casa dos milhões, sem magnitude compacta) enquanto as barras do mesmo cartão mostravam
  "2,9 bi". Passa a usar o mesmo `autoScaleNum`.

- **Cada linha de município reservava uma coluna que nunca tem conteúdo.** O cubo é
  agregado por cesta, então `dataFilters` preenche `product: ''` — e o CSS mantinha a faixa
  de `1.6fr` reservada, a segunda mais larga da linha. Era por isso que as barras começavam
  tão à direita. Faixa removida, espaço devolvido à barra.

- **Rótulos que não acompanhavam o escopo.** "Mapa de calor" encimava um gráfico de barras
  em *Região* e uma lista em *Município*; "Top 10 · Maiores estados produtores" aparecia
  sobre **uma** barra; "(1 maiores)" e "1 macrorregiões" quebravam a concordância. Todos
  derivados do escopo/cardinalidade ativos agora.

### Added — Geografia

- **Clique no mapa filtra por UF.** Clicar num estado (no coroplético ou nos blocos) aplica
  o filtro àquele estado e reenquadra o mapa nele; clicar de novo limpa. Elimina a ida ao
  modal para o recorte mais comum de todos. `BrazilTileMap` já aceitava `onSelect` e
  ninguém ligava essa entrada. A UF ativa ganha contorno destacado nas duas visualizações.

- **"Granularidade" passa a reger a página inteira.** Antes trocava só o primeiro cartão —
  o mapa de calor continuava em UF, o Top 10 continuava em UF. Agora o mapa de calor agrupa
  por região/UF/município conforme a escolha, e os cartões redundantes com o grão ativo
  somem (em *Região*, "Distribuição por região" e "Soma por região" eram o **mesmo gráfico,
  os mesmos dados, duas vezes na mesma tela**).

- **Município fica útil com uma UF selecionada.** Antes, a lista por município exigia
  primeiro entrar numa mesorregião pelo filtro; com uma única UF selecionada, agora lista
  direto os municípios daquele estado. Implementado **local à view** — uma primeira versão
  estendeu a cascata compartilhada em `dataFilters.js` e isso colocou *todas* as outras
  perspectivas em estado de carregamento sempre que uma UF única estivesse selecionada e a
  malha do IBGE ainda não tivesse aquecido (regressão pega por `dataFilters.cov.test.js`).

- **Estado vazio com ação.** "A lista por município aparece ao recortar a geografia…" era
  um parágrafo instrucional sem nada para clicar; ganhou o botão **"Abrir filtro de
  geografia"**, via o mesmo bridge (`window.patchFilter` / `window.openFilterMenu`) que o
  clique no mapa usa — em vez de uma prop nova no contrato que ~20 outras views compartilham.

### Changed — painel de filtros

- **Os quatro níveis sub-UF + Município recolhidos atrás de "Refinar dentro da UF".** Eram
  8 colunas paralelas sempre abertas (duas fileiras no desktop, oito roladores empilhados
  no celular) mesmo antes de escolher qualquer UF. A seção abre em três colunas
  (Nações · Regiões · Estados); o disclosure **expande sozinho** quando o filtro aplicado
  já recorta um dos níveis, e mostra o selo "recorte ativo" quando colapsado — colapsar
  nunca esconde um recorte vivo.

- **As duas divisões do IBGE agora são apresentadas como divisões.** Agrupadas e rotuladas
  ("Divisão clássica (1990)" / "Divisão atual (2017)") com uma frase explicando que
  recortam o mesmo estado de formas **independentes** — antes toda essa semântica estava
  codificada nos separadores da dica (`estado ▸ meso/microrregião · inter/imediata ▸
  município`), e o resultado prático era "Municípios 14/14" convivendo com
  "Reg. imediatas 21/21", que lido literalmente é impossível.

- **O cabeçalho do modal contradizia o resumo da própria seção**: "1 nação(ões), **0 UF**,
  **todos os municípios**" contra "… 0 UFs · **0 municípios**" logo abaixo — ambos saindo
  de `filterSummary.js`, arquivo criado justamente para impedir que as duas versões
  divergissem. Unificado o ramo de zero e reusada a pluralização correta que `geoChipText`
  já tinha dez linhas abaixo.

### Accessibility
- Os três controles segmentados da Geografia (Métrica, Granularidade, Mapa/Blocos) ganharam
  `role="group"` + `aria-pressed`, que o `FilterMenu` já usava em outro ponto.

### Nota — deliberadamente NÃO feito
- **Não dividir a Geografia em várias perspectivas.** O painel já tem **oito superfícies**
  com mapa do Brasil ou ranking de UF (Visão geral, Geografia, Concentração, Perfil do
  produto, Produtividade, Rebanho, Coeficiente de exportação, Fluxos/Parceiros). Mais
  entradas de menu multiplicariam a navegação sem responder nada novo; o que a perspectiva
  pedia era separação **interna** por pergunta, feita acima.
- **Não fabricar o grão produto × UF × ano** para "consertar" o heatmap — é exatamente a
  fabricação que a F1.5 removeu deste código. Ler o cubo quando existir e rotular
  honestamente quando não existir.
- **Não embutir a malha municipal completa no bundle** nem adicionar provedor de tiles
  (custo fixo recorrente, contra a regra de scale-to-zero do projeto).
- **Mapa municipal com polígonos reais** segue como a única lacuna de *capacidade* da
  perspectiva (o recorte sub-UF ainda não estreita o mapa, que pinta a UF inteira —
  ver `PLANS/geo_subregions.md`, passo 7). Exige uma fonte de geometria que o repositório
  não tem; fica para avaliação própria.

---

## [1.24.30] - 2026-08-20

### Removed
- **Identidade órfã de CI aposentada.** `sa-dashboard-smoke-ci` sobrou do smoke test
  removido junto com a UI Dash e **nenhum workflow a referenciava** — confirmado por grep
  em todos os `.github/workflows/*.yml`: só aparecia em comentário, citada como exemplo da
  convenção de nomes.

  Não era inofensiva: carregava **`bigquery.dataViewer` + `jobUser` + `readSessionUser` no
  projeto inteiro**, assumível por qualquer workflow deste repo via seu binding
  `workloadIdentityUser`. Leitura permanente de todos os datasets, para nada.

  A variável de repo `GCP_SMOKE_SERVICE_ACCOUNT` foi **removida**. A exclusão da service
  account em si **fica para o operador** — os hooks de segurança do projeto bloqueiam
  remoção de SA por automação, de propósito. Passos e valor de restauro em
  `docs/iam_setup.md`.

- **1,1 GB de worktrees abandonados** em `.claude/worktrees/` (dois diretórios de 15/jun,
  ~550 MB cada). Não eram worktrees registrados — `git worktree list` não os conhecia e o
  link `.git` deles estava quebrado. Antes de apagar, verifiquei que **todo arquivo único
  ali é recuperável do histórico**: eram da era pré-rename (pacote `embrapa_commodities`,
  `frontend/src/proto/`, `TODO.md`/`ROADMAP.md` aposentados) mais artefatos `dbt/target/`.
  Eram locais e fora do versionamento, então o repositório não muda.

### Nota — o que a varredura confirmou que NÃO está morto
Vale registrar o que foi investigado e **descartado**, para ninguém refazer o trabalho:

- **Frontend: zero órfãos.** Montei o grafo real de imports a partir do entry point (não
  um grep de nome de arquivo, que dá falso positivo em comentário): **86 módulos, 86
  alcançáveis**.
- **Python: zero código morto** a 80% de confiança (`vulture`). A 60% só aparecem os
  comandos Typer, registrados por decorator — falso positivo conhecido.
- **`python-dotenv`** parecia sem uso porque nada o importa direto: é exigência do
  `pydantic-settings`, que o usa para o `env_file=".env"` do `config.py`. Fica.
- **`radon`** parecia sem uso porque meu grep não varria `.claude/skills/`: a skill
  `code-audit` o invoca. Fica.
- **Nenhuma dependência npm sem import**, nenhum branch remoto além do `main`, nenhum
  resto de diretório da era Dash.

### Nota — encontrado, deliberadamente NÃO removido
A service account padrão do Compute Engine (`1085662235842-compute`) tem **`roles/editor`
no projeto** e nenhuma referência no repositório. É identidade gerenciada pelo GCP e usada
implicitamente por alguns serviços; removê-la sem mapear quem depende dela é o tipo de
limpeza que derruba produção. Fica registrada aqui como dívida de privilégio, não como
lixo.

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
