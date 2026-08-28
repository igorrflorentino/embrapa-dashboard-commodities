// Glossário data — per-banco terms used across the dashboard.
// Each banco gets a list of terms. Terms have:
//   term  — short name (case as authored)
//   short — one-line definition (institutional voice)
//   tag   — small chip label (column/source/etc.); optional
//   cat   — category for grouping inside the banco; optional
//
// IDs match window.BANCOS in bancos.js.

const GLOSSARY = {
  ibge_pevs: {
    label: 'IBGE PEVS',
    sub:   'Produção da Extração Vegetal e da Silvicultura',
    terms: [
      { term: 'PEVS',     cat: 'Fonte',    tag: 'IBGE',  short: 'Produção da Extração Vegetal e da Silvicultura — apuração anual do IBGE com a quantidade produzida e o valor da produção de produtos não-madeireiros e madeireiros nativos.' },
      { term: 'SIDRA',    cat: 'Fonte',    tag: 'IBGE',  short: 'Sistema IBGE de Recuperação Automática — o portal público onde o IBGE disponibiliza suas tabelas oficiais. É a fonte de onde este painel extrai os dados originais das pesquisas do IBGE (PEVS, PAM, PPM).' },
      { term: 'Açaí (fruto)',     cat: 'Produto', tag: '3403', short: 'Fruto da palmeira Euterpe oleracea colhido em áreas nativas ou manejadas como extrativas. É o açaí EXTRATIVO da PEVS — distinto do açaí de lavoura (cultivado), que aparece na PAM sob o código 45982. Unidade: toneladas.' },
      { term: 'Castanha-do-pará', cat: 'Produto', tag: '3405', short: 'Semente de Bertholletia excelsa, principal produto extrativista não-madeireiro da Amazônia. Unidade: toneladas (t).' },
      { term: 'Carvão vegetal',   cat: 'Produto', tag: '3433', short: 'Carvão obtido da carbonização de madeira nativa. Diferentemente da lenha e das toras (medidas em volume), o carvão é medido em MASSA. Unidade: toneladas (t).' },
      { term: 'Lenha',            cat: 'Produto', tag: '3434', short: 'Madeira nativa destinada à combustão direta. Principal item em VOLUME da PEVS. Unidade: metros cúbicos (m³).' },
      { term: 'Madeira em tora',  cat: 'Produto', tag: '3435', short: 'Toras de espécies nativas, sujeitas a controle de licenciamento ambiental. Unidade: metros cúbicos (m³).' },
      { term: 'Pinheiro brasileiro', cat: 'Produto', tag: '3450', short: 'Madeira em tora de araucária (Araucaria angustifolia), espécie nativa do Sul/Sudeste em risco de extinção. Unidade: metros cúbicos (m³).' },
      { term: 'mil t',            cat: 'Unidade', short: 'Escala de exibição da massa nos gráficos: milhares de toneladas (1 mil t = 1.000 t). O eixo mostra "mil t" enquanto a unidade-base do produto é a tonelada (t).' },
      { term: 'mi m³',            cat: 'Unidade', short: 'Escala de exibição do volume nos gráficos: milhões de metros cúbicos (1 mi m³ = 1.000.000 m³). O eixo mostra "mi m³" enquanto a unidade-base do produto é o metro cúbico (m³).' },
      { term: 'gold_pevs_production', cat: 'Tabela', tag: 'Base final', short: 'Tabela final do painel. Cada linha é uma combinação de ano, UF, município e produto. É a origem de todos os números das telas.' },
      { term: 'val_yearfx_*',          cat: 'Coluna', tag: 'gold',     short: 'Valor nominal em moeda corrente convertido pelo câmbio médio do ano. Auditoria histórica — não comparar entre anos.' },
      { term: 'val_real_ipca_*',       cat: 'Coluna', tag: 'gold',     short: 'Valor projetado para hoje pela cadeia IPCA. Padrão deste dashboard para comparações inter-anuais.' },
      { term: 'val_real_igpm_*',       cat: 'Coluna', tag: 'gold',     short: 'Idem usando o IGP-M (FGV). Alternativa ao IPCA, comum em séries de preços no atacado e de commodities. O IGP-M começa em 1989 — por isso val_real_igpm_* fica NULL para anos anteriores (não é um defeito do pipeline), enquanto IPCA e IGP-DI (desde 1980) preenchem.' },
      { term: 'data_quality_flag',     cat: 'Coluna', tag: 'qualidade', short: 'Marca de confiabilidade de cada linha: Normais (com quantidade e valor), valor financeiro ausente, quantidade ausente, incompleta (sem quantidade nem valor), e — com a detecção de outliers ativa — atípico/atípica (válido: bem acima do esperado, mas com preço implícito coerente) e problemático/problemática (provável erro de digitação: preço implícito — valor÷quantidade — muito fora da mediana do produto). Reserva ainda dois níveis para preenchimento automático futuro (quantidade / valor inferido), hoje sempre vazios; a legenda completa fica na perspectiva Qualidade dos dados.' },
    ],
  },

  ibge_pam: {
    label: 'IBGE PAM',
    sub:   'Produção Agrícola Municipal — área, produção e rendimento das lavouras',
    terms: [
      { term: 'PAM',       cat: 'Fonte',    tag: 'IBGE',  short: 'Produção Agrícola Municipal — apuração anual do IBGE com área plantada/colhida, produção e rendimento médio das lavouras temporárias e permanentes.' },
      { term: 'Lavoura temporária', cat: 'Conceito', short: 'Cultura de ciclo curto, replantada a cada safra (soja, milho, algodão, arroz, feijão).' },
      { term: 'Lavoura permanente', cat: 'Conceito', short: 'Cultura de ciclo longo, sem replantio anual (café, cana-de-açúcar, laranja, cacau).' },
      { term: 'Soja (em grão)',   cat: 'Produto', tag: '40124', short: 'Principal lavoura brasileira em área e valor. Concentrada no Centro-Oeste e Sul. Unidade: toneladas.' },
      { term: 'Milho (em grão)',  cat: 'Produto', tag: '40122', short: 'Primeira e segunda safra (milho safrinha). Forte em MT, PR e GO. Unidade: toneladas.' },
      { term: 'Café (em grão)',   cat: 'Produto', tag: '40139', short: 'Lavoura permanente; arábica e conilon. A PAM traz o TOTAL (soma de arábica e conilon). Concentrado em MG, ES e SP.' },
      { term: 'Cana-de-açúcar',   cat: 'Produto', tag: '40106', short: 'Lavoura permanente, base do etanol e do açúcar. Colhida em massa; forte em SP, GO e MG. Unidade: toneladas.' },
      { term: 'Arroz (em casca)', cat: 'Produto', tag: '40102', short: 'Lavoura temporária de grão; produção medida em casca (antes do beneficiamento). Concentrada no RS. Unidade: toneladas.' },
      { term: 'Banana (cacho)',   cat: 'Produto', tag: '40136', short: 'Lavoura permanente; produção medida pelo peso do cacho. Unidade: toneladas.' },
      { term: 'Mandioca',         cat: 'Produto', tag: '40119', short: 'Raiz de lavoura temporária, base de farinha e fécula, com ampla distribuição no país. Unidade: toneladas.' },
      { term: 'Açaí (cultivado)', cat: 'Produto', tag: '45982', short: 'Açaí de lavoura permanente (PAM) — distinto do açaí EXTRATIVO da PEVS (código 3403). Unidade: toneladas.' },
      { term: 'Área colhida',  cat: 'Coluna', short: 'Área de onde a lavoura foi de fato colhida, em hectares (ha) — pode ser menor que a área plantada quando parte da safra se perde (seca, praga, etc.). É ela que entra na conta do rendimento (produção ÷ área colhida).' },
      { term: 'Rendimento médio', cat: 'Coluna', short: 'Produtividade da lavoura = produção ÷ área colhida, em kg/ha. Média área-ponderada (nunca somada).' },
      { term: 'gold_pam_production', cat: 'Tabela', tag: 'Base final', short: 'Tabela final do painel. Cada linha é uma combinação de ano, UF, município e lavoura, com área, produção, rendimento e valor.' },
      { term: 'data_quality_flag',     cat: 'Coluna', tag: 'qualidade', short: 'Marca de confiabilidade de cada linha: Normais (com quantidade e valor), valor financeiro ausente, quantidade ausente, incompleta (sem quantidade nem valor), e — com a detecção de outliers ativa — atípico/atípica (válido: bem acima do esperado, mas com preço implícito coerente) e problemático/problemática (provável erro de digitação: preço implícito — valor÷quantidade — muito fora da mediana do produto). Reserva ainda dois níveis para preenchimento automático futuro (quantidade / valor inferido), hoje sempre vazios; a legenda completa fica na perspectiva Qualidade dos dados.' },
    ],
  },

  ibge_ppm: {
    label: 'IBGE PPM',
    sub:   'Pesquisa da Pecuária Municipal — rebanhos, produção animal e valor',
    terms: [
      { term: 'PPM',       cat: 'Fonte',    tag: 'IBGE',  short: 'Pesquisa da Pecuária Municipal — apuração anual do IBGE com o efetivo dos rebanhos e a produção de origem animal por município.' },
      { term: 'Efetivo dos rebanhos', cat: 'Conceito', short: 'Número de cabeças do rebanho (bovino, suíno, galináceos, etc.) num dado ano — um estoque, não uma produção, e sem valor monetário.' },
      { term: 'Produção de origem animal', cat: 'Conceito', short: 'Leite, ovos de galinha e codorna, mel, lã e casulo do bicho-da-seda — um fluxo anual, com quantidade e valor.' },
      { term: 'Bovino',    cat: 'Rebanho', tag: '2670', short: 'Maior rebanho do país, medido em cabeças (o efetivo, isto é, o estoque de animais num dado ano). Por ser um estoque e não uma produção, o efetivo bovino não tem valor monetário associado no PPM — diferentemente do leite ou dos ovos.' },
      { term: 'Leite',     cat: 'Produto', tag: '2682', short: 'Produção em mil litros (família volume). Concentrada em MG, RS e PR.' },
      { term: 'Ovos de galinha', cat: 'Produto', tag: '2685', short: 'Ovos para consumo produzidos pela avicultura de postura, medidos em mil dúzias — uma unidade de CONTAGEM, não de peso, por isso não se somam com litros de leite ou quilos de mel. É um dos principais produtos de origem animal em valor, concentrado em SP, PR e MG.' },
      { term: 'Cabeças',   cat: 'Unidade', short: 'Unidade de contagem do efetivo dos rebanhos — não é somável com litros de leite ou kg de mel (famílias diferentes).' },
      { term: 'valor_producao', cat: 'Coluna', short: 'Valor da produção animal (R$), deflacionável por IPCA/IGP-M/IGP-DI. O efetivo dos rebanhos NÃO tem valor.' },
      { term: 'gold_ppm_production', cat: 'Tabela', tag: 'Base final', short: 'Tabela final do painel. Cada linha é uma combinação de ano, UF, município e rebanho/produto, com quantidade (na unidade do produto) e — para a produção animal — valor.' },
      { term: 'data_quality_flag',     cat: 'Coluna', tag: 'qualidade', short: 'Marca de confiabilidade de cada linha: Normais, valor financeiro ausente, quantidade ausente, incompleta, e — com a detecção de outliers ativa — atípica (válida) e problemática (provável erro). O rebanho (estoque) fica Normais só com a quantidade — não tem valor por definição. Reserva ainda quantidade / valor inferido para preenchimento automático futuro, hoje sempre vazios; veja a legenda completa na perspectiva Qualidade dos dados.' },
    ],
  },

  mdic_comex: {
    label: 'MDIC COMEX',
    sub:   'Comércio Exterior brasileiro — exportações e importações por UF e parceiro',
    terms: [
      { term: 'SECEX',     cat: 'Fonte',    tag: 'MDIC',  short: 'Secretaria de Comércio Exterior do MDIC — divulga as estatísticas mensais de comércio exterior brasileiro.' },
      { term: 'NCM',       cat: 'Classificação', tag: 'Mercosul', short: 'Nomenclatura Comum do Mercosul — código de 8 dígitos derivado do Sistema Harmonizado (SH) para classificar mercadorias em comércio exterior.' },
      { term: 'SH4 · SH6', cat: 'Classificação', tag: 'OMA', short: 'Níveis do Sistema Harmonizado, o catálogo mundial de mercadorias: mais dígitos significam mais detalhe (SH4 é o capítulo do produto, SH6 desce ao tipo específico). Como o SH6 é idêntico no mundo todo, é o nível que permite comparar o comércio brasileiro (NCM, 8 dígitos) com o de outros países no UN Comtrade.' },
      { term: 'FOB',       cat: 'Termo',    tag: 'Incoterm', short: 'Free On Board — valor da mercadoria até ser colocada no navio no porto de embarque, SEM incluir frete internacional nem seguro. É a base padrão das exportações brasileiras; por isso os valores de exportação (FOB) e de importação (que costumam vir em CIF, com frete e seguro) não são diretamente comparáveis.' },
      { term: 'CIF',       cat: 'Termo',    tag: 'Incoterm', short: 'Cost, Insurance and Freight — valor da mercadoria somado ao frete e ao seguro até o porto de destino. Como inclui esses custos, um valor CIF é sempre maior que o FOB da mesma carga; por isso comparar importação (CIF) com exportação (FOB) infla artificialmente as importações.' },
      { term: 'UF de origem', cat: 'Coluna', short: 'Unidade da Federação brasileira da operação — o lado nacional: origem (produtor/exportador) na exportação, destino na importação. Não é o país estrangeiro.' },
      { term: 'Via',          cat: 'Coluna', short: 'Modalidade de transporte (marítima, aérea, rodoviária, ferroviária, fluvial, dutos). Existe na base bruta, mas é agregada (somada) na camada de serving — não é um filtro disponível no painel.' },
      { term: 'Peso líquido', cat: 'Coluna', short: 'Peso da mercadoria sem a embalagem, em quilogramas. Serve de denominador do preço médio (valor ÷ peso = US$/kg); por isso um peso errado — ex.: 1 kg registrado numa carga cara — distorce o preço e é justamente o que aciona a marca "problemático" na qualidade dos dados.' },
      { term: 'val_yearfx_* · val_real_*', cat: 'Coluna', tag: 'gold', short: 'A base do comércio é o valor FOB em US$: val_yearfx_usd é o próprio valor da fonte (nominal, sem conversão) e as versões em R$/€ usam o câmbio médio do ano; val_real_* traz tudo a preços de hoje pela inflação (IPCA/IGP-M/IGP-DI), para comparar anos diferentes.' },
      { term: 'gold_comex_flows', cat: 'Tabela', tag: 'Base final', short: 'Tabela final do painel. Cada linha é uma combinação de ano-mês, UF, NCM, país, via e fluxo.' },
      { term: 'data_quality_flag', cat: 'Coluna', tag: 'qualidade', short: 'Marca de confiabilidade de cada linha: Normais, valor financeiro ausente, peso ausente (sem peso líquido), incompleta, e — com a detecção de outliers ativa — atípico/atípica (válido: bem acima do esperado, preço coerente) e problemático/problemática (provável erro: preço implícito US$/kg muito fora da mediana do produto, ex.: peso = 1 kg). Reserva ainda peso / valor inferido para preenchimento automático futuro, hoje sempre vazios; a legenda completa fica na perspectiva Qualidade dos dados.' },
    ],
  },

  un_comtrade: {
    label: 'UN COMTRADE',
    sub:   'Estatísticas de Comércio Internacional — UN Statistics Division',
    terms: [
      { term: 'UNSD',     cat: 'Fonte',         tag: 'ONU', short: 'United Nations Statistics Division — mantém a base UN Comtrade com dados de comércio reportados pelas autoridades aduaneiras dos países.' },
      { term: 'País reporter', cat: 'Filtro', short: 'O país cujas alfândegas declararam a operação à ONU — o lado que "conta" o comércio. No painel é um FILTRO: vem como Brasil por padrão, mas você pode trocá-lo pelo mundo inteiro (todos os reporters) ou por outro país, para ver o comércio a partir de outra perspectiva.' },
      { term: 'País parceiro', cat: 'Filtro', short: 'O país do outro lado da operação — o destino de uma exportação ou a origem de uma importação vista pelo reporter. No painel é um FILTRO que restringe a análise a um parceiro específico; o padrão é considerar todos os parceiros.' },
      { term: 'Flow',     cat: 'Coluna',        short: 'Direção da operação sob a ótica do reporter: exportação (venda ao exterior) ou importação (compra do exterior). A base do painel usa apenas esses dois totais de direção; as reexportações e reimportações já estão incluídas neles e não aparecem como categorias à parte.' },
      { term: 'HS6',      cat: 'Classificação', tag: 'OMA', short: 'Sistema Harmonizado a 6 dígitos — padrão internacional comum a Brasil (NCM) e ao mundo. É o nível que torna o comércio de países diferentes diretamente comparável.' },
      { term: 'Mirror data', cat: 'Método',     short: 'Toda exportação de um país deveria aparecer como importação do parceiro pelo mesmo valor; na prática os números divergem por diferenças de registro, contrabando ou subfaturamento. Comparar os dois lados (o "espelho") revela essas lacunas. É o mesmo princípio da perspectiva "Espelho comercial" no modo multi-fonte.' },
      { term: 'val_yearfx_* · val_real_*', cat: 'Coluna', tag: 'gold', short: 'A base é o valor FOB em US$ (nominal); val_yearfx_usd é o próprio valor da fonte, sem conversão, e as versões em R$/€ usam o câmbio médio do ano; val_real_* traz tudo a preços de hoje pela inflação, para comparar anos diferentes.' },
      { term: 'Reexportação · Reimportação', cat: 'Conceito', short: 'Mercadoria que entrou no país e depois saiu (reexportação), ou que havia saído e retornou (reimportação), sem ter sido transformada. No painel, o filtro de fluxo mostra apenas os totais de exportação e importação, que já as incluem.' },
      { term: 'gold_comtrade_flows', cat: 'Tabela', tag: 'Base final', short: 'Tabela final do painel. Cada linha é uma combinação de ano, país reporter, país parceiro, regime aduaneiro, HS6 e fluxo. (O Brasil declara hoje apenas no regime de totais C00, mas a coluna faz parte do grão.)' },
      { term: 'data_quality_flag', cat: 'Coluna', tag: 'qualidade', short: 'Marca de confiabilidade de cada linha: Normais, valor financeiro ausente, quantidade ausente, incompleta, e — com a detecção de outliers ativa — atípico/atípica (válido) e problemático/problemática (provável erro: preço implícito US$/kg muito fora da mediana, ex.: peso = 1 kg em chapas de madeira de alto valor). Reserva ainda quantidade / valor inferido para preenchimento automático futuro, hoje sempre vazios; veja a legenda completa na perspectiva Qualidade dos dados.' },
    ],
  },

  sefaz_nf: {
    label: 'SEFAZ NFe',
    sub:   'Fluxos de comércio interno brasileiro reconstruídos a partir de NFe',
    pending: true,
    terms: [
      { term: 'NFe',     cat: 'Documento', tag: 'SEFAZ', short: 'Nota Fiscal Eletrônica — documento fiscal autorizado pela SEFAZ que registra cada operação de circulação de mercadoria no Brasil.' },
      { term: 'CFOP',    cat: 'Classificação', tag: 'CONFAZ', short: 'Código Fiscal de Operações e Prestações — identifica a natureza da operação (venda, transferência, devolução etc).' },
      { term: 'CNAE',    cat: 'Classificação', tag: 'IBGE',   short: 'Classificação Nacional de Atividades Econômicas — identifica o setor de atividade do estabelecimento.' },
      { term: 'ICMS',    cat: 'Tributo',   tag: 'CONFAZ', short: 'Imposto sobre Circulação de Mercadorias e Serviços — base e alíquota constam na NFe.' },
      { term: 'UF origem · destino', cat: 'Coluna', short: 'Localização do remetente e do destinatário da NFe. Permite reconstruir fluxos inter-estaduais.' },
      { term: 'Município', cat: 'Coluna', short: 'IBGE 7 dígitos. Identifica origem e destino com granularidade fina.' },
      { term: 'Agregação privada', cat: 'Método', short: 'Linhas que representariam fluxos com menos de N=5 estabelecimentos são agregadas ou suprimidas para preservar sigilo fiscal.' },
      { term: 'gold_nfe_flows', cat: 'Tabela', tag: 'Planejada', short: 'Tabela final planejada. Cada linha será uma combinação de ano-mês, par UF/município, CFOP e NCM.' },
    ],
  },

  // ── Thematic groups (cross-cutting — not tied to a single banco) ────────
  cross_analysis: {
    label: 'Análise cruzada',
    sub:   'Perspectivas multi-fonte — comparam séries de bancos diferentes',
    kind:  'tema',
    terms: [
      { term: 'Produto', cat: 'Conceito', short: 'Um item de um único banco (uma linha do catálogo): uma castanha na PEVS, uma NCM no COMEX. É a unidade mínima de análise do painel.' },
      { term: 'Agrupamento', cat: 'Conceito', short: 'Um mesmo produto econômico reunido ATRAVÉS de bancos diferentes (ex.: "Madeira" juntando a madeira da PEVS, do COMEX e do Comtrade). É o que torna possíveis as análises multi-fonte.' },
      { term: 'Cesta', cat: 'Conceito', short: 'O conjunto de produtos de UM banco que você selecionou nos filtros. A análise agregada (visão geral, valor e volume) soma essa cesta.' },
      { term: 'Banco único · Multi-fonte', cat: 'Modo', short: 'Os dois modos de análise, no topo da barra lateral. Banco único olha uma fonte de cada vez; Multi-fonte cruza séries de bancos diferentes no mesmo eixo (produção × exportação, participação no mercado mundial, etc.) — é onde vivem as perspectivas de análise cruzada.' },
      { term: 'Cruzamento entre fontes', cat: 'Perspectiva', short: 'Compara de 2 a 4 séries anuais de bancos diferentes no mesmo eixo de tempo, alternando entre base 100, eixo duplo e painéis.' },
      { term: 'Base 100',  cat: 'Método', short: 'Coloca todas as séries no valor 100 no ano inicial e mostra a variação a partir daí, para comparar o crescimento de coisas medidas em unidades diferentes (toneladas, reais, cabeças). Uma linha em 150 cresceu 50% desde o começo — o foco passa a ser o ritmo, não o tamanho.' },
      { term: 'Eixo duplo', cat: 'Método', short: 'Duas unidades em eixos verticais distintos (esquerda/direita) — compara o formato das curvas, não o nível absoluto.' },
      { term: 'Coeficiente de exportação', cat: 'Perspectiva', tag: 'IBGE × MDIC', short: 'Parcela da produção de cada UF (IBGE) que segue para exportação (MDIC). Mede a orientação exportadora por estado.' },
      { term: 'Participação no mercado mundial', cat: 'Perspectiva', tag: 'MDIC × Comtrade', short: 'Exportação brasileira como fração da exportação mundial do agrupamento (UN Comtrade).' },
      { term: 'Espelho comercial', cat: 'Perspectiva', tag: 'MDIC × Comtrade', short: 'Mostra a mesma exportação brasileira sob três olhares — o registro do MDIC, o do UN Comtrade e o que os países parceiros declararam ter importado do Brasil. Em tese os três deveriam bater; quando divergem, a diferença ao longo do tempo indica problemas de registro ou cobertura e ajuda a decidir em qual fonte confiar.' },
      { term: 'Balanço da cadeia', cat: 'Perspectiva', tag: 'massa', short: 'Reconstitui o destino da produção — comércio interno (SEFAZ), exportação (MDIC) e consumo/estoque — com massa conservada, mais a fatia no mercado mundial. (Perspectiva PLANEJADA — depende do banco SEFAZ NFe, ainda não disponível.)' },
      { term: 'Defasagem safra → embarque', cat: 'Perspectiva', tag: 'lead-lag', short: 'Quantos meses os embarques (MDIC, mensal) seguem o pico da safra (IBGE). (Perspectiva PLANEJADA — depende de perfis MENSAIS de safra que a PEVS, anual, ainda não fornece.)' },
    ],
  },

  // Engenharia de atributos — o nível de industrialização é editável pelo pesquisador; o
  // tipo de mercado (finalidade econômica) vem de um seed (Contrato de Dados).
  curadoria: {
    label: 'Engenharia de atributos',
    sub:   'Atributos derivados: conhecimento do pesquisador (industrialização) + seed (tipo de mercado)',
    kind:  'tema',
    terms: [
      { term: 'Engenharia de atributos', cat: 'Conceito', short: 'Camada de colunas derivadas construídas sobre os dados: o nível de industrialização (editável pelo pesquisador) e o tipo de mercado (definido por seed). Alimenta as análises curadas no modo multi-fonte.' },
      { term: 'Nível de industrialização', cat: 'Dimensão', short: 'Escala ordinal de 8 níveis atribuída a cada código de produto pelo pesquisador, do bruto ao manufaturado: Commodity Pura, Higienizada, Acondicionada, Consumível e Subproduto; Manufaturado Artesanal, Industrial e Especializado. Base da análise de valor agregado.' },
      { term: 'Commodity · Manufaturado', cat: 'Dimensão', short: 'As duas famílias da escala: Commodity (matéria-prima em graus crescentes de limpeza e acondicionamento, até virar insumo ou subproduto) e Manufaturado (produto diferenciado — artesanal, industrial ou especializado).' },
      { term: 'Finalidade econômica (tipo de mercado)', cat: 'Dimensão', short: 'Classificação do par regime aduaneiro × fluxo em Consumo ou Processamento. RECURSO SUSPENSO: depende do detalhe de regime aduaneiro que a base atual da UN COMTRADE (apenas o total C00) não carrega, portanto não está disponível no painel.' },
      { term: 'Consumo · Processamento', cat: 'Dimensão', short: 'Os dois destinos do bem: consumo final, ou transformação/beneficiamento industrial. É a finalidade que o seed atribuiria a cada par regime × fluxo. RECURSO SUSPENSO (ver "Finalidade econômica").' },
      { term: 'Par regime × fluxo', cat: 'Conceito', short: 'Cruzamento entre o regime aduaneiro (a modalidade legal sob a qual a mercadoria entra ou sai — consumo definitivo, admissão temporária, drawback etc.) e a direção do fluxo (importação ou exportação). É esse par, e não o regime ou o fluxo isolados, que revelaria a finalidade econômica. RECURSO SUSPENSO — depende de um detalhe de regime que a base atual (C00) não carrega.' },
      { term: 'Valor agregado', cat: 'Análise', short: 'Exportação distribuída pelos 8 níveis de industrialização ao longo do tempo (valor, volume e preço por nível), com o prêmio de processamento — preço do nível mais processado sobre o menos processado.' },
      { term: 'Rascunho → aplicado', cat: 'Operação', short: 'As classificações de industrialização ficam em rascunho até você clicar em "Aplicar à base"; a partir daí ficam salvas e as análises se atualizam ao vivo para todos os pesquisadores. O histórico de alterações é preservado.' },
      { term: 'Regime aduaneiro', cat: 'Conceito', short: 'A modalidade legal sob a qual uma mercadoria cruza a fronteira, definida pela alfândega: consumo/exportação definitiva, admissão temporária, drawback (importar para reexportar já processado), entre outras. No UN Comtrade, "C00" é o total, somando todos os regimes — é o único nível que a base carrega hoje.' },
      { term: 'Catálogo (Cadastro de produtos)', cat: 'Operação', short: 'A lista, curada pelo pesquisador, de quais produtos entram e saem do dashboard, com seu agrupamento e ciclo de vida (exibir ou ocultar). Editada na tela "Cadastro de produtos"; toda alteração fica registrada com o e-mail do autor.' },
      { term: 'Descontinuado · órfão', cat: 'Operação', short: 'Um produto que saiu do catálogo mas cujos dados já baixados continuam na base. Fica marcado como Descontinuado (órfão) e só é apagado por decisão humana, nunca automaticamente.' },
    ],
  },

  // Statistical methods that surface in the perspective names/descriptions
  // (views.js) but a low-IT researcher would not know — glossed in plain pt-BR.
  metodos: {
    label: 'Métodos estatísticos',
    sub:   'Conceitos de cálculo usados nas perspectivas analíticas',
    kind:  'tema',
    terms: [
      { term: 'Índice de Gini', cat: 'Método', short: 'Mede a desigualdade de uma distribuição (ex.: a concentração da produção entre as UFs) numa escala de 0 a 1: 0 = tudo igualmente distribuído, 1 = tudo concentrado em um só.' },
      { term: 'Curva de Lorenz', cat: 'Método', short: 'Gráfico que acumula, do menor para o maior, a fatia da produção ou do valor detida por cada UF ou produtor. A linha diagonal representa a igualdade perfeita (cada parte com fatia idêntica); quanto mais a curva real afunda abaixo dessa diagonal, maior a concentração nas mãos de poucos. É a base visual do Índice de Gini.' },
      { term: 'HHI (Herfindahl-Hirschman)', cat: 'Método', short: 'Mede o quanto uma produção ou mercado está concentrado em poucos participantes: soma dos quadrados das participações percentuais de cada parte, numa escala de 0 a 10.000 (convenção do US DoJ). Abaixo de 1.500 = baixa concentração; 1.500 a 2.500 = moderada; acima de 2.500 = alta (poucos atores dominam).' },
      { term: 'CAGR', cat: 'Método', short: 'Taxa de crescimento média anual composta — o crescimento percentual equivalente, por ano, entre o início e o fim do período.' },
      { term: 'Correlação cruzada (defasagem)', cat: 'Método', short: 'Mede se duas séries se movem juntas. A correlação disponível hoje compara o movimento no MESMO ano (crescimento ano a ano, sem defasagem); a versão com atraso — embarques que seguem o pico da safra alguns meses depois — exige perfis mensais que ainda não estão disponíveis.' },
      { term: 'Preço médio implícito', cat: 'Método', short: 'Preço estimado dividindo o valor pela quantidade (ex.: US$ por kg). Não é um preço cotado, e sim a média que resulta dos dados agregados.' },
      { term: 'Valor nominal × valor real', cat: 'Método', short: 'Nominal = o valor em moeda da época. Real = o mesmo valor trazido a preços de hoje pela inflação (IPCA, IGP-M ou IGP-DI), para comparar anos diferentes de forma justa.' },
      { term: 'Deflacionar', cat: 'Método', short: 'Retirar o efeito da inflação de uma série de valores, trazendo reais de anos diferentes para o poder de compra de um mesmo ano de referência. Sem deflacionar, um valor de 1990 parece muito maior que o de hoje só por causa da inflação. É o que fazem as colunas val_real_ipca / igpm / igpdi.' },
      { term: 'IPCA · IGP-M · IGP-DI', cat: 'Método', short: 'Os três índices de inflação usados para trazer valores antigos a preços de hoje. O IPCA (IBGE) mede a inflação ao consumidor e é o padrão do dashboard; o IGP-M e o IGP-DI (FGV) pesam mais o atacado — o IGP-M começa em 1989, enquanto IGP-DI e IPCA vêm de antes.' },
      { term: 'Moeda (R$ · US$ · €)', cat: 'Método', short: 'Você escolhe em qual moeda ver os valores: a produção (IBGE) é nativa em reais, o comércio (COMEX/Comtrade) em dólares, e a conversão usa o câmbio real do BCB. As correções IGP-M e IGP-DI só existem em R$ e €; se você estiver em US$ e escolher um desses índices, a correção volta automaticamente para o IPCA (a moeda permanece em US$).' },
      { term: 'Auto-escala (mil/mi/bi)', cat: 'Método', short: 'Opção que ajusta automaticamente a grandeza dos números exibidos (mil, milhão, bilhão) para deixá-los legíveis, sem mudar o valor real. É diferente das escalas fixas de eixo "mil t" e "mi m³", que valem só para a PEVS.' },
    ],
  },
};

window.GLOSSARY = GLOSSARY;

// Coverage lint: every visible banco should have a glossary section.
if (window.auditBancoCoverage) {
  window.auditBancoCoverage('glossário (glossary.js)', (b) => !!window.GLOSSARY[b.id]);
}
