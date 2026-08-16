// ViewAbout.cov.test.jsx — coverage smoke + branch tests for the institutional
// "Sobre o dashboard" onboarding page (ViewAbout.jsx). The page is purely
// registry-driven: it reads the banco list (visibleBancos/BANCOS), the perspective
// groups (VIEW_GROUPS), per-banco provenance (bancoMeta/maturityMeta/bancoTable) and
// the live Gold refresh stamp (dataStore.meta). We stub all of those as plain globals
// + the composed widgets (SectionHeader/MaturityTag/MaturityLegend), then drive the
// main branches: the banco grid with a Gold table (hasData) vs a planned banco
// (no table, "ainda não publicada"), the grouped perspectives section, the pipeline /
// tips / credits cards, and the version + refresh footer.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

const BANCOS = [
  { id: 'ibge_pevs', short: 'IBGE PEVS', sub: 'Produção extrativa', about: 'Reúne dados anuais da extração vegetal e da silvicultura no Brasil.', maturity: 'estavel', status: 'live' },
  { id: 'sefaz_nf', short: 'SEFAZ NFe', sub: 'Comércio interno', about: 'Reconstrói o comércio interno a partir das Notas Fiscais Eletrônicas.', maturity: 'planejado', status: 'soon' },
];

const VIEW_GROUPS = [
  {
    id: 'aggregate',
    label: 'Análise agregada',
    hint: 'cesta',
    views: [
      { id: 'overview', label: 'Visão geral', desc: 'Resumo consolidado da cesta.' },
      { id: 'glossary', label: 'Glossário', desc: 'Termos e códigos.' }, // filtered out (id === glossary)
    ],
  },
  {
    id: 'product',
    label: 'Análise por produto',
    hint: 'commodity',
    views: [
      { id: 'product_profile', label: 'Perfil do produto', desc: 'Mergulho numa commodity.' },
      { id: 'no_desc', label: 'Sem descrição' }, // filtered out (no desc)
    ],
  },
  {
    id: 'empty',
    label: 'Grupo vazio',
    hint: '—',
    views: [{ id: 'glossary', label: 'Glossário', desc: 'x' }], // group drops (only glossary)
  },
];

function makeStore(metas = {}) {
  return {
    subscribe: () => () => {},
    loadMeta: vi.fn(),
    meta: (id) => metas[id] || null,
  };
}

function stubGlobals(store) {
  window.dataStore = store;
  window.BANCOS = BANCOS;
  window.visibleBancos = () => BANCOS;
  window.VIEW_GROUPS = VIEW_GROUPS;
  window.maturityMeta = (b) => ({ hasData: b && b.maturity === 'estavel' });
  window.bancoTable = (id) => `gold_${id}`;
  window.bancoMeta = (id) => {
    const b = BANCOS.find((x) => x.id === id) || {};
    const hasData = b.maturity === 'estavel';
    return {
      domain: hasData ? 'Produção interna' : 'Comércio interno',
      scope: 'Brasil · UF · município',
      source: 'IBGE',
      table: `gold_${id}`,
      cobertura: { granularidade: 'produto × município × ano' },
      maturityDate: hasData ? null : '2026-Q4',
    };
  };
  // Composed widgets rendered as readable DOM.
  window.SectionHeader = ({ overline, title, action }) => (
    <div className="sh">
      <span className="sh-overline">{overline}</span>
      <span className="sh-title">{title}</span>
      <span className="sh-action">{action}</span>
    </div>
  );
  window.MaturityTag = ({ banco }) => <span className="mat-tag">{banco?.maturity || '…'}</span>;
  window.MaturityLegend = () => <div className="mat-legend" />;
}

let ViewAbout;

beforeEach(async () => {
  await import('./ViewAbout.jsx'); // registers window.ViewAbout
  ViewAbout = window.ViewAbout;
});

afterEach(() => cleanup());

describe('ViewAbout — render smoke + main sections', () => {
  it('renders the purpose, banco grid, perspectives, pipeline, tips and credits', () => {
    const store = makeStore({ ibge_pevs: { refresh: '2026-06-20 · 03:00' } });
    stubGlobals(store);

    const { container } = render(<ViewAbout />);

    // Section overlines for the six cards.
    const overlines = [...container.querySelectorAll('.sh-overline')].map((e) => e.textContent);
    expect(overlines).toContain('Propósito');
    expect(overlines).toContain('Bancos de dados');
    expect(overlines).toContain('Perspectivas analíticas');
    expect(overlines).toContain('Como os dados são processados');
    expect(overlines).toContain('Como usar');
    expect(overlines).toContain('Créditos e proveniência');

    // Banco grid: both bancos render their short label + the maturity legend.
    expect(container.querySelector('.ab-banco-grid')).toBeTruthy();
    expect(container.textContent).toContain('IBGE PEVS');
    expect(container.textContent).toContain('SEFAZ NFe');
    expect(container.querySelector('.ab-mat-legend')).toBeTruthy();
    expect(container.querySelector('.mat-legend')).toBeTruthy();

    // The mount effects fire loadMeta for every banco.
    expect(store.loadMeta).toHaveBeenCalledTimes(BANCOS.length);
  });

  it('shows the friendly onboarding description (not the technical Gold table name)', () => {
    stubGlobals(makeStore());
    const { container } = render(<ViewAbout />);
    // The card now shows the plain-language `about` description…
    expect(container.textContent).toContain('Reúne dados anuais da extração vegetal');
    // …and NO LONGER the technical Gold table name (that moved to "Estrutura de dados").
    expect(container.querySelectorAll('.ab-banco code').length).toBe(0);
    expect(container.textContent).not.toContain('gold_ibge_pevs');
    expect(container.textContent).not.toContain('camada Serving');
    // The planejado banco still surfaces its expected-completion date.
    expect(container.textContent).toContain('Conclusão prevista');
    expect(container.textContent).toContain('2026-Q4');
    // Geographic reach is labelled "Abrangência geográfica" (no longer the misleading
    // "Granularidade"); the real grain is shown separately as "Granularidade".
    expect(container.textContent).toContain('Abrangência geográfica');
    expect(container.textContent).toContain('Brasil · UF · município');
    expect(container.textContent).toContain('Granularidade');
    expect(container.textContent).toContain('produto × município × ano');
  });

  it('groups the perspectives, dropping glossary + desc-less views and empty groups', () => {
    stubGlobals(makeStore());
    const { container } = render(<ViewAbout />);
    // 2 surviving views (overview + product_profile) across 2 groups.
    const title = [...container.querySelectorAll('.sh-title')].map((e) => e.textContent);
    expect(title).toContain('2 perspectivas em 2 categorias');
    // glossary view is filtered out; product_profile + overview shown.
    const viewTitles = [...container.querySelectorAll('.ab-view-title')].map((e) => e.textContent);
    expect(viewTitles).toContain('Visão geral');
    expect(viewTitles).toContain('Perfil do produto');
    expect(viewTitles).not.toContain('Glossário');
    expect(viewTitles).not.toContain('Sem descrição'); // desc-less view dropped
  });

  it("shows the app version + that VERSION's release date in the footer", () => {
    // The date beside the version is the release date (CHANGELOG → backend →
    // window.APP_RELEASE_DATE), NOT a Gold refresh stamp. Give the store a PEVS
    // refresh that differs from it: the footer must show the release date, since
    // pairing a build with an unrelated data date read as "this version is old".
    stubGlobals(makeStore({ ibge_pevs: { refresh: '2026-06-20 · 03:00' } }));
    window.APP_RELEASE_DATE = '16 ago 2026';
    const { container } = render(<ViewAbout />);
    const ver = container.querySelector('.ab-version .tnum')?.textContent || '';
    expect(ver).toMatch(/^v\d/); // "v1.x.y …" from the backend (package.json pre-load)
    expect(ver).toContain('16 ago 2026');
    expect(ver).not.toContain('2026-06-20'); // the Gold refresh must NOT leak in here
  });

  it('renders the version ALONE when no release date is known (never a stand-in)', () => {
    stubGlobals(makeStore({ ibge_pevs: { refresh: '2026-06-20 · 03:00' } }));
    delete window.APP_RELEASE_DATE; // unreleased dev build / CHANGELOG section absent
    const { container } = render(<ViewAbout />);
    const ver = container.querySelector('.ab-version .tnum')?.textContent || '';
    expect(ver).toMatch(/^v\d[\d.]*$/); // version only — no separator, no date
  });

  it('falls back to BANCOS when visibleBancos is absent', () => {
    stubGlobals(makeStore());
    window.visibleBancos = undefined; // exercise the (window.BANCOS || []) fallback path
    const { container } = render(<ViewAbout />);
    expect(container.textContent).toContain('IBGE PEVS');
  });
});
