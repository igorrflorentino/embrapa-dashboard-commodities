// ViewAbout — institutional "Sobre o dashboard" page. This is the landing screen,
// so it doubles as the onboarding guide: what the dashboard is, which bancos feed
// it, how to navigate, how the data is processed, and how to read it. No insights
// or live analysis — just orientation. All per-banco facts (maturity, coverage,
// refresh, table) come from the backend (/api/source-meta), never hardcoded here.

// App version — the live value comes from the BACKEND (pyproject → importlib.metadata →
// /api/source-meta.appVersion → window.APP_VERSION, hydrated by dataStore), the single source
// of truth the release tag bumps. package.json is only the pre-load fallback (shown for the
// first paint, before source-meta resolves). Keeping it in sync used to be a convention the
// manifest quietly broke — it sat at 1.11.0 against a 1.24.7 project — so a test now asserts
// package.json + package-lock.json match pyproject.toml (tests/test_release.py).
import pkg from '../../package.json';

const { useState: useAbState, useEffect: useAbEffect } = React;

// Per-category descriptions for the grouped "Perspectivas analíticas" section.
// Keyed by VIEW_GROUPS[].id (views.js). Onboarding tone — says what each family of
// perspectives is FOR, so a new researcher knows where to look.
const GROUP_DESCS = {
  aggregate: 'Olhe a cesta de produtos como um todo: indicadores consolidados e séries históricas de valor e quantidade. É o ponto de partida antes de descer ao produto individual.',
  product: 'Aprofunde-se em um produto específico ou compare alguns lado a lado: preço, participação na cesta, ranking de estados e — na produção agrícola — produtividade.',
  flows: 'Acompanhe o caminho do produto da origem ao destino: a cadeia da extração à exportação e os parceiros (estados e países) que compram e vendem.',
  distribution: 'Veja onde a produção acontece e quão concentrada ela é: mapas e rankings por região, estado ou município, com índices de concentração e desigualdade (Gini, HHI, Lorenz).',
  temporal: 'Investigue os padrões no tempo além da tendência: sazonalidade, decomposição da série e quebras estruturais. Mais reveladora com dados mensais.',
  crosssource: 'Cruze séries de bancos diferentes no mesmo eixo — produção (IBGE) × exportação (MDIC) × mercado mundial (Comtrade) — para medir coeficiente de exportação, participação global, spread de preço e o balanço da cadeia.',
  curated: 'Análises que dependem da classificação feita pelo pesquisador (Engenharia de atributos): produto bruto × processado e a finalidade econômica (consumo × processamento) do que é comercializado.',
  documentation: 'Conheça a procedência e a confiabilidade do banco selecionado: o diagnóstico de qualidade dos dados (e, no menu lateral, o glossário de termos e códigos).',
};

function ViewAbout() {
  const bancos = window.visibleBancos ? window.visibleBancos() : (window.BANCOS || []);

  // Sobre is an info-page (?ip=about): reached directly it renders outside the data
  // boundary. Eager-load every banco's provenance so the cards + footer date reflect
  // the real Gold metadata (and re-render as each /api/source-meta resolves).
  const [, forceAb] = useAbState(0);
  useAbEffect(() => window.dataStore.subscribe(() => forceAb(n => n + 1)), []);
  useAbEffect(() => {
    bancos.forEach(b => window.dataStore && window.dataStore.loadMeta && window.dataStore.loadMeta(b.id));
  }, []);

  // Perspectives grouped by the 8 categories (views.js · VIEW_GROUPS) — registry
  // driven, so it never goes stale. Glossary is a reference tool, not a perspective,
  // so it is filtered out; empty groups are dropped.
  const groups = (window.VIEW_GROUPS || [])
    .map(g => ({
      id: g.id,
      label: g.label,
      hint: g.hint,
      views: g.views.filter(v => v.id !== 'glossary' && v.desc).map(v => ({ id: v.id, title: v.label, desc: v.desc })),
    }))
    .filter(g => g.views.length);
  const totalViews = groups.reduce((n, g) => n + g.views.length, 0);

  const APP_VERSION = 'v' + (window.APP_VERSION || pkg.version);
  // The date beside the version is the VERSION's release date (CHANGELOG.md → the backend),
  // NOT a data-refresh stamp. It used to be the PEVS Gold refresh date, which under the lone
  // "Versão" label read as "this build is from 01 ago" while the release had shipped that same
  // day — and silently spoke for one banco out of five. Per-banco freshness is the job of the
  // hero, Saúde and Dados views, which state which banco each date belongs to. No fallback:
  // an unknown date renders the version alone rather than a stand-in.
  const releaseDate = window.APP_RELEASE_DATE || null;

  const TIPS = [
    {
      title: 'Como navegar',
      desc: 'Escolha um banco de dados na barra à esquerda e uma perspectiva no menu “Selecionar perspectiva”, no topo. Alterne entre “Banco único” (uma fonte por vez) e “Multi-fonte” (cruza séries de bancos diferentes no mesmo eixo). A barra lateral pode ser redimensionada arrastando sua borda direita.',
    },
    {
      title: 'Filtros não são iguais a convenções métricas',
      desc: 'Os filtros escolhem QUAIS dados aparecem (produtos, período, estados e municípios, faixa de valor, sinalizações de qualidade). As convenções métricas escolhem COMO esses dados são mostrados (moeda, correção pela inflação, unidade de massa ou volume). São controles independentes — mudar um não mexe no outro.',
    },
    {
      title: 'Valor nominal × valor real',
      desc: 'Para comparar anos diferentes de forma justa, prefira o valor corrigido pela inflação (real). O valor nominal está em moeda da época e só deve ser usado para conferência pontual — somar ou comparar valores nominais de anos distintos induz a erro. A correção (IPCA, IGP-M ou IGP-DI) é escolhida nas convenções métricas.',
    },
    {
      title: 'Famílias de unidades nunca se misturam',
      desc: 'Quantidades em massa (t/kg) e em volume (m³/L) jamais são somadas. Quando a cesta selecionada contém produtos de famílias diferentes, o dashboard mostra uma métrica de quantidade por família. O valor monetário permanece sempre agregável.',
    },
    {
      title: 'Citação e compartilhamento',
      desc: 'Use “Citar painel” (canto superior direito) para gerar, do painel exatamente como exibido — banco, perspectiva, recorte, produtos, UFs, filtros e convenções —, a citação no texto (ABNT NBR 10520:2023) e a referência completa (ABNT NBR 6023:2025), já com o link permanente. “Compartilhar” copia uma URL que reproduz toda a seleção atual, ideal para colaborar com outro pesquisador.',
    },
    {
      title: 'Exportação de dados',
      desc: 'O botão “Exportar CSV” (canto superior direito, ao lado de “Compartilhar”) baixa a fatia de dados em tela — já com todos os filtros e convenções aplicados, na resolução máxima disponível — para você seguir a análise em planilha ou em outra ferramenta. Fica junto de “Citar painel” e “Compartilhar” porque os três levam o mesmo estado embora: como citação, como link e como arquivo.',
    },
  ];

  const CREDITS = [
    { role: 'Coordenação científica', who: 'Embrapa — Empresa Brasileira de Pesquisa Agropecuária' },
    { role: 'Vinculação institucional', who: 'Ministério da Agricultura e Pecuária · Governo Federal' },
    { role: 'Fontes de dados', who: 'IBGE · MDIC SECEX · UN Statistics Division · SEFAZ estaduais' },
    { role: 'Engenharia de dados', who: 'Coleta, padronização e cálculo de indicadores a partir das fontes oficiais, em nuvem' },
    { role: 'Apresentação', who: 'Aplicação web interativa (React) com gráficos Plotly' },
  ];

  return (
    <div className="ab-stack">
      {/* Purpose + first steps (onboarding) */}
      <div className="card ab-purpose">
        <window.SectionHeader
          overline="Propósito"
          title="Análise histórica dos produtos agrícolas brasileiros"
        />
        <p className="ab-lead">
          O <strong>Dashboard de Análise Histórica de Produtos Agrícolas</strong> reúne, num só lugar,
          as principais bases públicas sobre os produtos agrícolas brasileiros — produção extrativa e
          agrícola, comércio interno e comércio exterior — para que pesquisadores explorem como
          esses mercados evoluíram ao longo de décadas. Cada fonte oficial entra com o mesmo
          peso: você escolhe o banco de dados e a perspectiva, aplica filtros e compara séries.
          O foco é exclusivamente analítico e científico — todos os números vêm de dados oficiais
          processados pelo pipeline, sem projeções, recomendações ou opiniões automatizadas.
        </p>
        <p className="ab-lead">
          <strong>Primeiros passos:</strong> escolha um banco de dados na barra à esquerda,
          selecione uma perspectiva no menu superior e ajuste os filtros e as convenções métricas
          conforme a sua pergunta de pesquisa. Para comparar fontes diferentes, ative o modo
          <strong> Multi-fonte</strong>. Cada banco tem cobertura temporal e maturidade próprias,
          indicadas nos cartões abaixo. As seções seguintes detalham os bancos, as perspectivas
          disponíveis, como os dados são processados e as convenções importantes para interpretar
          os resultados com segurança.
        </p>
      </div>

      {/* Datasets */}
      <div className="card">
        <window.SectionHeader
          overline="Bancos de dados"
          title="O que você encontra aqui"
          action={<span className="caption">{bancos.length} bancos · {bancos.filter(b => b.status === 'live').length} disponível(is)</span>}
        />
        <div className="ab-banco-grid">
          {bancos.map(b => {
            const bm = window.bancoMeta(b.id);
            return (
              <div key={b.id} className={'ab-banco mat-' + b.maturity}>
                <div className="ab-banco-head">
                  <span className="ab-banco-short">{b.short}</span>
                  <window.MaturityTag banco={b} />
                </div>
                <div className="ab-banco-domain">{bm.domain}</div>
                <p className="ab-banco-sub">{b.about || b.sub}</p>
                <dl className="ab-banco-meta">
                  {/* "Abrangência geográfica" = the geographic levels/reach (Brasil·UF·
                      município, or origin↔partner for trade) — NOT the row grain. */}
                  <dt>Abrangência geográfica</dt><dd>{bm.scope}</dd>
                  {/* "Granularidade" = the finest detail, i.e. the unique key of a row
                      (dim × dim × … × tempo) — the consistent answer to "até que nível vai
                      o detalhamento". Sourced from cobertura.granularidade. */}
                  {bm.cobertura && bm.cobertura.granularidade && (
                    <>
                      <dt>Granularidade</dt><dd>{bm.cobertura.granularidade}</dd>
                    </>
                  )}
                  <dt>Fonte</dt><dd>{bm.source}</dd>
                  {bm.maturityDate && (
                    <>
                      <dt>Conclusão prevista</dt><dd className="tnum">{bm.maturityDate}</dd>
                    </>
                  )}
                </dl>
              </div>
            );
          })}
        </div>
        <div className="ab-mat-legend">
          <div className="ab-mat-legend-head">Maturidade dos bancos</div>
          <window.MaturityLegend />
        </div>
      </div>

      {/* Perspectives — grouped by category */}
      <div className="card">
        <window.SectionHeader
          overline="Perspectivas analíticas"
          title={`${totalViews} perspectivas em ${groups.length} categorias`}
        />
        <div className="ab-pgroups">
          {groups.map(g => (
            <div key={g.id} className="ab-pgroup">
              <div className="ab-pgroup-head">
                <h3 className="ab-pgroup-title">{g.label}</h3>
                {GROUP_DESCS[g.id] && <p className="ab-pgroup-desc">{GROUP_DESCS[g.id]}</p>}
              </div>
              <div className="ab-view-grid">
                {g.views.map(v => (
                  <div key={v.id} className="ab-view">
                    <h4 className="ab-view-title">{v.title}</h4>
                    <p className="ab-view-desc">{v.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Data processing — concept + pointer to the per-layer table explorer */}
      <div className="card">
        <window.SectionHeader
          overline="Como os dados são processados"
          title="Das fontes oficiais aos números do painel"
        />
        <p className="ab-lead">
          Cada número exibido percorre um pipeline de quatro camadas — das cópias fiéis das
          fontes oficiais (<strong>Bronze</strong>), passando pela padronização
          (<strong>Silver</strong>) e pela tabela analítica completa de cada fonte
          (<strong>Gold</strong>), até os recortes prontos para o painel
          (<strong>Serving</strong>). Para conhecer cada camada em detalhe e investigar as
          tabelas linha a linha, abra a perspectiva <strong>Estrutura de dados</strong> (no
          menu “Selecionar perspectiva”, em “Documentação do banco”).
        </p>
      </div>

      {/* Usage tips */}
      <div className="card">
        <window.SectionHeader
          overline="Como usar"
          title="Guia rápido para interpretar e navegar"
        />
        <div className="ab-tips">
          {TIPS.map((t, i) => (
            <div key={i} className="ab-tip">
              <h3 className="ab-tip-title">{t.title}</h3>
              <p className="ab-tip-desc">{t.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Credits */}
      <div className="card">
        <window.SectionHeader
          overline="Créditos e proveniência"
          title="Quem mantém o dashboard"
        />
        <dl className="ab-credits">
          {CREDITS.map((c, i) => (
            <React.Fragment key={i}>
              <dt>{c.role}</dt>
              <dd>{c.who}</dd>
            </React.Fragment>
          ))}
        </dl>
        <div className="ab-version">
          <div>
            <span className="meta-label">Versão</span>
            <span className="meta-val tnum">{APP_VERSION}{releaseDate ? ` · ${releaseDate}` : ''}</span>
          </div>
          <div>
            <span className="meta-label">Contato técnico</span>
            <span className="meta-val">igor.lopes@embrapa.br</span>
          </div>
          <div>
            <span className="meta-label">Licença dos dados</span>
            <span className="meta-val">Atribuição obrigatória (Embrapa + fonte original)</span>
          </div>
        </div>
      </div>
    </div>
  );
}

window.ViewAbout = ViewAbout;
