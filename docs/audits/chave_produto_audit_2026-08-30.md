# Auditoria da chave do produto — `(banco, tabela, código)` — 2026-08-30 (v1.46.9)

> **STATUS — HISTORICAL: registro do estado em v1.46.9.** Os SETE achados abaixo foram
> corrigidos na v1.47.0, junto com a decisão de estender o trio aos cinco bancos (inclusive
> os de uma tabela só). Leia como a medição que motivou a mudança, não como fila de
> trabalho. Guardas novos: `tests/test_trio_identidade_produto.py`,
> `assert_ppm_measure_kind_matches_tabela` e o `not_null` sobre `tabela` nas dims.

Auditoria pedida para confirmar que **`(banco, tabela, código)` identifica um produto em
todo o projeto, em todas as camadas**, e para remover retrocompatibilidade da chave antiga.

## O fato que classifica todo o resto

Medido em prod (`gold.*`, 2026-08-30):

| banco | tabela → nº de códigos | códigos compartilhados entre as duas |
|---|---|---|
| `pevs` | 289 → 7 · 291 → 3 | **0** |
| `ppm` | 3939 → 8 · 74 → 6 | **0** |

**Os códigos são disjuntos entre as metades.** Logo, hoje `(banco, código)` já basta para
*unicidade*, e **todo achado deste relatório é latente, não vivo** — nenhum número errado
está sendo exibido.

Mas o mesmo `select` mostra por que a tabela é carga real:

| descrição | tabelas | códigos |
|---|---|---|
| Carvão vegetal | 2 | 3433, 3455 |
| Lenha | 2 | 3434, 3456 |
| Madeira em tora | 2 | 3435, 3457 |

**Três produtos existem nas duas metades com o mesmo nome e códigos diferentes.** A tabela
não é carga para *distinguir registros* — é carga para o **significado**. E foi exatamente
aí que os defeitos reais desta semana apareceram: gráficos fundindo as metades pelo nome
(v1.46.1/v1.46.3) e o gate escondendo as duas ao ocultar uma (v1.46.5). Nenhum deles era
um problema de unicidade.

Isso deve orientar a leitura das prioridades abaixo: o risco não é colisão de chave, é
**um número certo com um rótulo que nomeia o todo**.

---

## 🟢 Conforme — verificado, sem ação

| camada | ponto | chave |
|---|---|---|
| dbt core | `dim_produto_catalog` | `(codigo_produto, source, sidra_tabela)` |
| dbt core | `dim_produto_visibility` | `(source, code, sidra_tabela)` |
| dbt core | `dim_code_industrialization_scd2` | `(source, code, sidra_tabela)` |
| dbt macro | `chave_produto()` | trio, com `ifnull(tabela,'-')` para bancos de uma tabela |
| Python | `sql.CHAVE_CATALOGO` / `CHAVE_CLASSIFICACAO` / `CHAVE_CICLO_DE_VIDA` | trio |
| Python | `serving/attribute_engineering.py` (escritas) | trio explícito |
| Python + dbt | gate de visibilidade (`hidden_code_predicate` + `visibility_clause`) | trio desde v1.46.5 |
| Frontend | chave de linha do Cadastro (`ViewCadastroProdutos:705`) | `banco\|tabela\|código` |
| Frontend | chips de recorte + citação ABNT (`scopeChips.js` → `AppShell`) | inclui a tabela |
| Frontend | exportação CSV (`csvExport.js`) | inclui a tabela |
| dbt | `gold_comex_flows`, `gold_comtrade_flows`, `gold_pam_production` e suas marts | corretamente **sem** `sidra_tabela` — bancos de uma tabela só |

---

## 🟡 Achados — a chave declarada é mais estreita que a identidade

Ordenados por consequência, não por camada.

### 1. `serving_ppm_annual` colapsa as duas metades do PPM

`group by reference_year, state_acronym, product_code, family` — **sem `sidra_tabela`** —
e a tabela é levantada com `any_value(sidra_tabela)`, junto com `any_value(measure_kind)`.

`any_value` sobre um discriminador é a assinatura do defeito: declara "sei que isto varia e
estou colapsando". Se um código existisse nas duas tabelas do PPM, as linhas seriam
**somadas** e a metade exibida seria arbitrária.

O irmão `serving_pevs_annual` **agrupa** por `sidra_tabela`. É o mesmo conserto aplicado a
um e não ao outro — o padrão recorrente deste projeto: *uma regra que existe e não se
propaga*.

### 2. `gold_produto_agrupamento` declara um invariante que o catálogo não garante

O cabeçalho diz, como invariante **load-bearing**:

> `(codigo_produto, source)` is unique in the catalog … so a Gold code resolves to AT MOST
> one agrupamento_id — the cross-source LEFT JOIN in the serving marts cannot FAN OUT and
> double any qty_base/val_* sum.

Mas `dim_produto_catalog` é único em **`(codigo_produto, source, sidra_tabela)`**. O join é
`code = codigo_produto` sobre `(source, code)`. Com um código nas duas tabelas e
agrupamentos diferentes, o join **fanaria out e dobraria as somas monetárias**.

O teste `unique_combination_of_columns(source, code)` interrompe o build antes disso, então
o número errado não chega à tela — mas o texto afirma uma garantia que não existe.

### 3. Contratos de unicidade que subdeclaram o grão

Modelos que unem DUAS tabelas SIDRA e cuja chave declarada omite o discriminador:

| modelo | chave declarada | une duas tabelas? |
|---|---|---|
| `gold_pevs_production` | `(reference_year, state_acronym, city_code, product_code)` | sim (289 ∪ 291) |
| `gold_ppm_production` | idem | sim (3939 ∪ 74) |
| `silver_ibge_ppm` | `(reference_year, city_code, product_code, variable_code, unit_of_measure)` | sim |
| `serving_pevs_annual` | `(reference_year, state_acronym, product_code, family)` | sim — **e o modelo agrupa por `sidra_tabela`** |

⚠ **Há uma leitura em que isto é deliberado.** A docstring do check
`Shared code across SIDRA tables` (`doctor.py`) registra a chave estreita como *tripwire*:
se um código compartilhado aparecer, o teste de unicidade falha com severidade `error`, o
`dbt build` pula os modelos downstream e o número errado não chega ao dashboard.

Essa defesa fazia sentido quando não havia outro alarme. **Deixou de fazer em v1.46.4**,
quando o check do `doctor` voltou a funcionar: ele vigia exatamente essa condição e a
*explica*, em vez de produzir uma falha de unicidade confusa. Corrigir as chaves troca um
alarme obscuro por um alarme nomeado — mas é uma decisão de projeto, não uma correção
mecânica.

### 4. O estado Gold de um produto é indexado sem a tabela — três camadas

O caminho completo perde a tabela em três pontos independentes:

1. `gateway.fetch_source_code_stats` → `group by code` sobre o Gold. Para PEVS/PPM isso
   **soma as duas metades**.
2. `seam_curation.catalog_status` → `by_banco[r.banco].add(r.codigo_produto)` descarta
   `sidra_tabela` das linhas do catálogo, e a saída é chaveada `f"{banco}:{code}"`.
3. `ViewCadastroProdutos:701` → `statusMap[e.banco + ':' + e.codigo_produto]`.

Consequência com um código compartilhado: haveria **duas** linhas no Cadastro (o catálogo é
único no trio) e **uma** entrada de estado — as duas linhas mostrariam as mesmas "Linhas" e
o mesmo "Período", somados.

A linha 705 do mesmo arquivo já usa o trio como chave de renderização. A discrepância está
dentro de um arquivo só.

### 5. `curation.tabela_do_produto(source, code)` deriva a tabela a partir do código

Assume a disjunção que o trio deveria tornar desnecessária. É a única forma disponível hoje
para quem só tem `(source, code)` — mas é uma dependência circular: a identidade completa é
reconstruída a partir de uma chave parcial.

Usada por `attribute_engineering` ao gravar uma classificação. As escritas ficam corretas
enquanto os códigos forem disjuntos.

### 6. `gateway.fetch_source_codes` — `any_value(name)` por código

Alimenta o autocompletar do Cadastro. Colapsa o nome das metades. Menor consequência: o
formulário tem campo próprio para a tabela, obrigatório no PPM.

### 7. Seleção de produtos no frontend é `Set<código>`

`FilterMenu` guarda a cesta por código puro (`products.has(p.code)`, `toggleIn(s, p.code)`)
e usa `key={p.code}`. `ViewProductCompare` idem (`key={it.code}`); a lista de órfãos do
Cadastro usa `banco|código` (linha 924).

**Classificado como decisão de projeto, não defeito.** Existe um eixo separado de tabela
("Origem da produção"), então cesta-de-códigos × filtro-de-tabela cobre o espaço. Registrado
para que a escolha seja consciente, não acidental.

---

## ⚖️ Uma decisão que é sua: `measure_kind`

`measure_kind` (`'stock'` | `'flow'`) é o **gêmeo sobrevivente do `origem`**. Como `origem`
era, ele mapeia 1-para-1 com a tabela (3939 → stock, 74 → flow) e vive em 6 arquivos dbt, 6
módulos Python e 8 arquivos do frontend.

Pela regra do `CLAUDE.md` — *"todo rótulo humano de uma metade é DERIVADO da tabela, nunca
armazenado ao lado dela"* — ele seria candidato à mesma remoção que o `origem`.

**Recomendo mantê-lo**, por uma diferença real: `origem` era só outro nome para a tabela,
enquanto stock/flow é uma **regra de agregação** (um estoque não se soma ao longo de anos).
Trocá-lo por `sidra_tabela === '3939'` vazaria o id de uma tabela SIDRA para dentro de cada
ramo de UI, e quebraria no dia em que outro banco tiver estoques.

O que o torna seguro é que ele já é **derivado**, não independente: `silver_ibge_ppm` o
calcula com `case when p.sidra_tabela = ppm_herd_table_id then 'stock' else 'flow' end`. O
que falta é um teste que impeça que ele volte a ser um fato autônomo.

---

## 🧹 Retrocompatibilidade

Sua instrução foi remover compat da chave antiga. Duas coisas parecem iguais e não são.

### Sai — compat de código puro

| ponto | o que é |
|---|---|
| `main.jsx:115` `_tabelaDoParamAntigo()` + `q.get('or')` na linha 164 | decodifica o parâmetro de URL `or=extrativa\|silvicultura`, aposentado em v1.46.0. Puro código, nada depende dele além de permalinks compartilhados antes daquela versão (mesmo dia). |

### Fica — não é compat, é leitura de dado imutável

| ponto | por que não sai |
|---|---|
| macro `catalog_visibilidade()` e o campo `ciclo_de_vida` em `curation.py` | traduzem linhas que **existem fisicamente** em `research_inputs.produto_catalog_log`, que é **append-only** e nunca é reescrito. Remover a tradução não limparia código: quebraria a leitura de dado real. |
| seeds de sucessão de códigos NCM/HS/SIDRA aposentados (`config.py`, `attribute_engineering.py`) | "aposentado" ali se refere a **códigos de produto que a fonte externa aposentou**, não à nossa chave. Assunto diferente; removê-los perderia histórico. |

---

## Recomendação

Ordem sugerida, por relação consequência/custo:

1. **#1 `serving_ppm_annual`** — agrupar por `sidra_tabela`, simetria com o irmão PEVS.
2. **#4 estado Gold por trio** — as três camadas juntas, senão vira meia-propagação.
3. **#2 `gold_produto_agrupamento`** — no mínimo corrigir o texto do invariante; idealmente
   levar a tabela ao join.
4. **#3 chaves de unicidade** — decisão sua sobre o tripwire (ver a ressalva acima).
5. **🧹 remover `_tabelaDoParamAntigo`**.
6. **⚖️ `measure_kind`** — manter, com um guarda de consistência contra `sidra_tabela`.

Cada item deve vir com validação por injeção: restaurar o defeito tem de reprovar um teste
nomeado. Onde a condição só é observável com um código compartilhado — inexistente hoje —,
o teste precisa **construir** esse caso (fixture dbt ou stub), não esperar por ele.
