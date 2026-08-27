// AppShell.cov.test.jsx — coverage for the institutional chrome (AppShell.jsx, 0%
// before this file). AppShell is a side-effect module that registers window.AppShell;
// it reads a swarm of window.* registry helpers (VIEW_GROUPS / viewById / viewLabel /
// BANCOS / bancoById / visibleBancos / metricById / viewAppliesTo / crossViewApplies /
// bancosSupporting / missingCapsLabel / dataStore / urlEncodeState …) and composed
// widgets (Icon / MaturityTag / UsageDot / MaturityTag / FeedbackModal). We stub all of
// those as plain globals (matching the sibling MainScreen/ViewAbout patterns) and drive
// the interactive branches:
//   • chrome render (header band, sidebar items, topnav trigger, footer)
//   • the mobile off-canvas drawer (hamburger → .body.nav-open + .sidebar-backdrop;
//     close via backdrop / nav-item tap / Escape)  ← the PR #180 drawer, untested
//   • sidebar banco selection (setDatabase + setInfoPage(null)) + info-page selection
//   • topnav open + view pick (setView) + single-vs-multi visibleGroups filtering
//   • citation modal: open, render, close via backdrop / Fechar / Escape keydown effect
//   • the SidebarResizer pointer drag + double-click reset (--sidebar-w + localStorage)
//   • cross-fonte indicators: the picker (crossState.series → seriesCountByBanco) and
//     the analytical fixed-sources path
//   • share + cite copy + the window.openFeedback global + the Reportar trigger

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render } from '@testing-library/react';

const BANCOS = [
  { id: 'ibge_pevs', short: 'IBGE PEVS', label: 'Produção · Extração vegetal', maturity: 'estavel', status: 'live' },
  { id: 'comex', short: 'COMEX', label: 'Comércio · Exportações', maturity: 'beta', status: 'live' },
];

const VIEW_GROUPS = [
  {
    id: 'aggregate',
    label: 'Análise agregada',
    hint: 'cesta',
    views: [
      { id: 'overview', label: 'Visão geral', desc: 'Resumo consolidado.', status: 'live' },
      { id: 'soon_view', label: 'Em breve', desc: 'Futuro.', status: 'soon' },
    ],
  },
  {
    id: 'crosssource',
    label: 'Análise cruzada',
    hint: 'entre fontes',
    views: [
      { id: 'cross_source', label: 'Cruzamento entre fontes', desc: 'Monte as séries.', crossBanco: true },
      { id: 'chain_balance', label: 'Balanço da cadeia', desc: 'Cadeia.', crossBanco: true, sources: ['ibge_pevs', 'comex'] },
    ],
  },
];

const VIEW_BY_ID = Object.fromEntries(
  VIEW_GROUPS.flatMap((g) => g.views.map((v) => [v.id, { ...v, group: g }])),
);

function stubGlobals() {
  // Composed widgets — rendered as readable DOM so the chrome mounts in jsdom.
  window.Icon = ({ name }) => <i className="icon" data-icon={name} />;
  window.MaturityTag = ({ banco }) => <span className="mat-tag">{banco?.maturity || '…'}</span>;
  window.UsageDot = ({ active }) => <span className="usage-dot" data-active={!!active} />;
  window.FeedbackModal = ({ open, context }) =>
    open ? <div className="feedback-modal" data-view={context?.view || ''} data-banco={context?.banco || ''} /> : null;

  // Registry helpers.
  window.VIEW_GROUPS = VIEW_GROUPS;
  window.BANCOS = BANCOS;
  window.visibleBancos = () => BANCOS;
  window.viewById = (id) => VIEW_BY_ID[id] || null;
  window.viewLabel = (id) => VIEW_BY_ID[id]?.label || id;
  window.bancoById = (id) => BANCOS.find((b) => b.id === id) || null;
  window.metricById = (b, m) => ({ label: `métrica ${m}` });
  window.viewAppliesTo = () => ({ applies: true, missing: [] });
  window.crossViewApplies = () => ({ usable: true, state: 'ok', reason: '' });
  window.bancosSupporting = () => [BANCOS[1]];
  window.missingCapsLabel = (m) => (m || []).join(', ') || '—';
  window.dataStore = { get: () => null, meta: () => null };
  // urlState codec — present so buildPermalink returns a real URL (share + cite "Disponível em").
  window.urlEncodeArr = (a) => (a == null ? '' : a.length ? a.join(',') : '-');
  window.urlEncodeState = (state) =>
    Object.entries(state)
      .filter(([, v]) => v !== '' && v != null)
      .map(([k, v]) => `${k}=${v}`)
      .join('&');
  // The shared single encoder buildPermalink now delegates to (urlState.buildUrlState);
  // stub the fields it needs so the permalink resolves to a real URL in the test.
  window.MN_URL_CAP = 200;
  window.buildUrlState = ({ view, database, infoPage, summary }) => ({
    v: view, b: database, ip: infoPage,
    pb: window.urlEncodeArr(summary?.basket),
    st: window.urlEncodeArr(summary?.states),
    mn: window.urlEncodeArr(summary?.munis),
  });
}

const baseProps = () => ({
  view: 'overview',
  setView: vi.fn(),
  database: 'ibge_pevs',
  setDatabase: vi.fn(),
  infoPage: null,
  setInfoPage: vi.fn(),
  summary: { startDate: '2010', endDate: '2024', products: 'Açaí', geo: 'PA' },
  conventions: { currency: 'BRL', correction: 'IPCA', units: { mass: 't', volume: 'm³' }, autoScale: true },
  crossState: { series: [], mode: '', y0: '', y1: '' },
  mode: 'single',
  setMode: vi.fn(),
});

let AppShell;

beforeEach(async () => {
  await import('./AppShell.jsx'); // registers window.AppShell
  AppShell = window.AppShell;
  stubGlobals();
  // Clipboard stub so onShare / onCopyCite don't throw in jsdom.
  if (!navigator.clipboard) {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  } else {
    navigator.clipboard.writeText = vi.fn().mockResolvedValue(undefined);
  }
});

afterEach(() => {
  cleanup();
  localStorage.removeItem('embrapa:sidebarW');
  delete window.openFeedback;
});

describe('AppShell — chrome render', () => {
  it('renders header band, sidebar bancos, topnav trigger and the footer tríade', () => {
    const { container } = render(
      <AppShell {...baseProps()}>
        <div className="child-content">conteúdo</div>
      </AppShell>,
    );
    // Header band.
    expect(container.querySelector('.topbar')).toBeTruthy();
    expect(container.querySelector('.topbar-hamburger')).toBeTruthy();
    expect(container.querySelector('.product-name')).toBeTruthy();
    // Sidebar single-mode banco items.
    const items = [...container.querySelectorAll('.side-item-l')].map((e) => e.textContent);
    expect(items).toContain('IBGE PEVS');
    expect(items).toContain('COMEX');
    // The active banco gets the 'active' class.
    expect(container.querySelector('.side-item.active')).toBeTruthy();
    // Topnav trigger shows the active group + view labels.
    expect(container.textContent).toContain('Análise agregada');
    expect(container.textContent).toContain('Visão geral');
    // The children render in the content slot.
    expect(container.querySelector('.child-content')).toBeTruthy();
    // Footer.
    expect(container.querySelector('.footer')).toBeTruthy();
    // The resizer handle is present.
    expect(container.querySelector('.sidebar-resizer')).toBeTruthy();
    // The feedback modal is mounted but closed (stub renders nothing).
    expect(container.querySelector('.feedback-modal')).toBeNull();
  });

  it('registers window.openFeedback on mount and removes it on unmount', () => {
    const { unmount } = render(<AppShell {...baseProps()} />);
    expect(typeof window.openFeedback).toBe('function');
    unmount();
    expect(window.openFeedback).toBeUndefined();
  });
});

describe('AppShell — mobile off-canvas drawer (PR #180)', () => {
  it('opens the drawer on the hamburger and adds the nav-open class + backdrop', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    expect(container.querySelector('.body.nav-open')).toBeNull();
    expect(container.querySelector('.sidebar-backdrop')).toBeNull();

    fireEvent.click(container.querySelector('.topbar-hamburger'));
    expect(container.querySelector('.body.nav-open')).toBeTruthy();
    expect(container.querySelector('.sidebar-backdrop')).toBeTruthy();
    expect(container.querySelector('.topbar-hamburger').getAttribute('aria-expanded')).toBe('true');
  });

  it('closes the drawer when the backdrop is clicked', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.topbar-hamburger'));
    fireEvent.click(container.querySelector('.sidebar-backdrop'));
    expect(container.querySelector('.body.nav-open')).toBeNull();
  });

  it('closes the drawer when a sidebar item is tapped (.side-item delegate)', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.topbar-hamburger'));
    expect(container.querySelector('.body.nav-open')).toBeTruthy();
    // Click inside a .side-item — the aside's onClick closest('.side-item') closes it.
    fireEvent.click(container.querySelector('.side-item'));
    expect(container.querySelector('.body.nav-open')).toBeNull();
  });

  it('closes the drawer on the Escape key (sideNavOpen effect)', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.topbar-hamburger'));
    expect(container.querySelector('.body.nav-open')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(container.querySelector('.body.nav-open')).toBeNull();
  });

  it('clicking a non-side-item region of the aside does NOT close the drawer', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.topbar-hamburger'));
    // .side-section is not a .side-item → closest returns null → stays open.
    fireEvent.click(container.querySelector('.side-section'));
    expect(container.querySelector('.body.nav-open')).toBeTruthy();
  });
});

describe('AppShell — sidebar + topnav selection', () => {
  it('selecting a banco calls setDatabase and clears the info page', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    const comex = [...container.querySelectorAll('.side-item')].find((el) =>
      el.textContent.includes('COMEX'),
    );
    fireEvent.click(comex);
    expect(props.setDatabase).toHaveBeenCalledWith('comex');
    expect(props.setInfoPage).toHaveBeenCalledWith(null);
  });

  it('Enter on a banco item activates it via the clickable() keyboard handler', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    const comex = [...container.querySelectorAll('.side-item')].find((el) =>
      el.textContent.includes('COMEX'),
    );
    fireEvent.keyDown(comex, { key: 'Enter' });
    expect(props.setDatabase).toHaveBeenCalledWith('comex');
    // Space also activates.
    props.setDatabase.mockClear();
    fireEvent.keyDown(comex, { key: ' ' });
    expect(props.setDatabase).toHaveBeenCalledWith('comex');
    // A non-activating key is ignored.
    props.setDatabase.mockClear();
    fireEvent.keyDown(comex, { key: 'a' });
    expect(props.setDatabase).not.toHaveBeenCalled();
  });

  it('selecting an info page (Sobre / Glossário / Cadastro) calls setInfoPage', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    const cadastro = [...container.querySelectorAll('.side-item')].find((el) =>
      el.textContent.includes('Cadastro de produtos'),
    );
    fireEvent.click(cadastro);
    expect(props.setInfoPage).toHaveBeenCalledWith('cadastro_produtos');

    const glossary = [...container.querySelectorAll('.side-item')].find((el) =>
      el.textContent.includes('Glossário global'),
    );
    fireEvent.click(glossary);
    expect(props.setInfoPage).toHaveBeenCalledWith('glossary');
  });

  it('clicking the brand logo routes to the "about" info page', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click(container.querySelector('.brand-btn'));
    expect(props.setInfoPage).toHaveBeenCalledWith('about');
  });

  it('opens the topnav and picks a view → setView + setInfoPage(null) + closes the menu', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click(container.querySelector('.topnav-trigger'));
    expect(container.querySelector('.topnav-menu')).toBeTruthy();
    // The single-mode menu lists the aggregate group's views (overview + soon).
    const overviewOpt = [...container.querySelectorAll('.topnav-opt')].find((b) =>
      b.textContent.includes('Visão geral'),
    );
    fireEvent.click(overviewOpt);
    expect(props.setView).toHaveBeenCalledWith('overview');
    expect(props.setInfoPage).toHaveBeenCalledWith(null);
    // Menu closed after pick.
    expect(container.querySelector('.topnav-menu')).toBeNull();
  });

  it('clicking the topnav scrim closes the menu', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.topnav-trigger'));
    fireEvent.click(container.querySelector('.topnav-scrim'));
    expect(container.querySelector('.topnav-menu')).toBeNull();
  });

  it('a disabled cross-source option does not fire pickView', () => {
    // Make the cross picker non-usable so it renders disabled in multi mode.
    window.crossViewApplies = () => ({ usable: false, state: 'na', reason: 'precisa de ≥2 séries' });
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'cross_source';
    const { container } = render(<AppShell {...props} />);
    fireEvent.click(container.querySelector('.topnav-trigger'));
    const disabledOpt = container.querySelector('.topnav-opt[disabled]');
    expect(disabledOpt).toBeTruthy();
    fireEvent.click(disabledOpt);
    expect(props.setView).not.toHaveBeenCalled();
  });

  it('a single-mode "não se aplica" view stays clickable and lists supporting bancos', () => {
    window.viewAppliesTo = () => ({ applies: false, missing: ['flow'] });
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click(container.querySelector('.topnav-trigger'));
    // The supporters line ("disponível em …") renders for an N/A single-mode view.
    expect(container.textContent).toContain('disponível em');
    const naOpt = [...container.querySelectorAll('.topnav-opt')].find((b) =>
      b.textContent.includes('Visão geral'),
    );
    fireEvent.click(naOpt);
    expect(props.setView).toHaveBeenCalledWith('overview');
  });
});

describe('AppShell — mode filtering (single vs multi)', () => {
  it('single mode shows the non-cross group; the mode switch toggles to multi', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click(container.querySelector('.topnav-trigger'));
    // Single mode → aggregate group visible, cross group filtered out.
    expect(container.textContent).toContain('Análise agregada');
    expect(container.textContent).not.toContain('Cruzamento entre fontes');

    // Click the "Multi-fonte" mode tab.
    const multiTab = [...container.querySelectorAll('.mode-opt')].find((b) =>
      b.textContent.includes('Multi-fonte'),
    );
    fireEvent.click(multiTab);
    expect(props.setMode).toHaveBeenCalledWith('multi');
  });

  it('multi mode renders the cross group + the "Fontes no cruzamento" sidebar header', () => {
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'cross_source';
    const { container } = render(<AppShell {...props} />);
    expect(container.textContent).toContain('Fontes no cruzamento');
    fireEvent.click(container.querySelector('.topnav-trigger'));
    expect(container.textContent).toContain('Análise cruzada');
  });
});

describe('AppShell — cross-fonte sidebar indicators', () => {
  it('the picker (cross_source) reflects the assembled series counts', () => {
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'cross_source';
    props.crossState = {
      series: [
        { b: 'ibge_pevs', m: 'prod_value' },
        { b: 'ibge_pevs', m: 'prod_qty' },
      ],
      mode: 'overlay',
      y0: '2010',
      y1: '2024',
    };
    const { container } = render(<AppShell {...props} />);
    // ibge_pevs is included with a count of 2; comex is excluded.
    const counts = [...container.querySelectorAll('.side-src-count')].map((e) => e.textContent);
    expect(counts).toContain('2');
    expect(container.querySelector('.side-src.incl')).toBeTruthy();
    expect(container.querySelector('.side-src.excl')).toBeTruthy();
  });

  it('an analytical fixed-sources cross view marks its declared sources as included', () => {
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'chain_balance'; // sources: ibge_pevs + comex
    props.crossState = { series: [] };
    const { container } = render(<AppShell {...props} />);
    // Both declared sources are included → no .excl row.
    const incl = container.querySelectorAll('.side-src.incl');
    expect(incl.length).toBe(2);
    expect(container.querySelector('.side-src.excl')).toBeNull();
    // "incluída" label shows when included but with no per-banco count.
    expect(container.textContent).toContain('incluída');
  });
});

describe('AppShell — citation modal', () => {
  it('opens the modal, renders the in-text + reference blocks, and copies', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    expect(container.querySelector('.cite-modal')).toBeTruthy();
    // In-text ABNT 10520 call + full reference both present. The entity is ALL CAPS
    // by project decision: this asserted "(Embrapa," until v1.31.0, on 10520:2023's
    // initial-capital rule for authors, and was changed for consistency with the
    // reference head and Embrapa's house style.
    expect(container.textContent).toContain('(EMBRAPA,');
    expect(container.textContent).toContain('EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA');
    // Disponível em: present because urlEncodeState is stubbed.
    expect(container.textContent).toContain('Disponível em:');
    // Copy buttons invoke the clipboard.
    fireEvent.click(container.querySelector('.cite-copy-mini'));
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
  });

  it('closes via the Fechar secondary button', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    const fechar = [...container.querySelectorAll('.btn-secondary')].find((b) => b.textContent.includes('Fechar'));
    fireEvent.click(fechar);
    expect(container.querySelector('.cite-modal')).toBeNull();
  });

  it('closes via a backdrop click (and stays open on a modal-body click)', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    // Body click is stopPropagation → stays open.
    fireEvent.click(container.querySelector('.cite-modal'));
    expect(container.querySelector('.cite-modal')).toBeTruthy();
    // Backdrop click → closes.
    fireEvent.click(container.querySelector('.cite-backdrop'));
    expect(container.querySelector('.cite-modal')).toBeNull();
  });

  it('closes on the Escape keydown effect', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    expect(container.querySelector('.cite-modal')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(container.querySelector('.cite-modal')).toBeNull();
  });

  it('builds the cross-source picker citation when on the cross_source view', () => {
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'cross_source';
    props.crossState = { series: [{ b: 'ibge_pevs', m: 'prod_value' }], mode: 'overlay', y0: '2010', y1: '2024' };
    const { container } = render(<AppShell {...props} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    expect(container.textContent).toContain('Cruzamento entre fontes');
  });

  it('builds the fixed cross-analysis citation for a fixed-sources cross view', () => {
    const props = baseProps();
    props.mode = 'multi';
    props.view = 'chain_balance';
    props.crossState = { series: [] };
    const { container } = render(<AppShell {...props} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Citar painel')));
    expect(container.textContent).toContain('Análise cruzada');
  });
});

describe('AppShell — share + feedback', () => {
  it('Share copies the permalink and flips the label to "URL copiada"', async () => {
    const { container } = render(<AppShell {...baseProps()} />);
    const share = [...container.querySelectorAll('.util-action')].find((b) =>
      b.textContent.includes('Compartilhar'),
    );
    await act(async () => {
      fireEvent.click(share);
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
    expect(container.textContent).toContain('URL copiada');
  });

  it('Enviar feedback opens the FeedbackModal with the current view/banco context', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    fireEvent.click([...container.querySelectorAll('.util-action')].find((b) => b.textContent.includes('Enviar feedback')));
    const modal = container.querySelector('.feedback-modal');
    expect(modal).toBeTruthy();
    expect(modal.dataset.view).toBe('overview');
    expect(modal.dataset.banco).toBe('ibge_pevs');
  });

  it('window.openFeedback(prefill) opens the modal with the prefilled context', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    act(() => {
      window.openFeedback({ view: 'Referências', category: 'sugestao' });
    });
    const modal = container.querySelector('.feedback-modal');
    expect(modal).toBeTruthy();
    expect(modal.dataset.view).toBe('Referências');
  });
});

describe('AppShell — SidebarResizer', () => {
  it('drags the handle to widen the sidebar and persists --sidebar-w to localStorage', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    const handle = container.querySelector('.sidebar-resizer');
    // pointerdown begins the resize (startX captured); body gets sb-resizing.
    fireEvent.pointerDown(handle, { clientX: 260 });
    expect(document.body.classList.contains('sb-resizing')).toBe(true);
    // pointermove on window widens by +40px → 300px (within [200, 460]).
    fireEvent.pointerMove(window, { clientX: 300 });
    expect(document.documentElement.style.getPropertyValue('--sidebar-w')).toBe('300px');
    // pointerup ends the drag, clears the class and persists.
    fireEvent.pointerUp(window);
    expect(document.body.classList.contains('sb-resizing')).toBe(false);
    expect(localStorage.getItem('embrapa:sidebarW')).toBe('300px');
  });

  it('clamps the width to the max bound', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    const handle = container.querySelector('.sidebar-resizer');
    fireEvent.pointerDown(handle, { clientX: 0 });
    fireEvent.pointerMove(window, { clientX: 9999 }); // way past max
    expect(document.documentElement.style.getPropertyValue('--sidebar-w')).toBe('460px');
    fireEvent.pointerUp(window);
  });

  it('double-click resets the width to the 260px default', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    const handle = container.querySelector('.sidebar-resizer');
    // Pre-set a non-default width.
    document.documentElement.style.setProperty('--sidebar-w', '400px');
    fireEvent.doubleClick(handle);
    expect(document.documentElement.style.getPropertyValue('--sidebar-w')).toBe('260px');
    expect(localStorage.getItem('embrapa:sidebarW')).toBe('260px');
  });
});

describe('AppShell — mobile topbar: util overflow menu (⋯)', () => {
  it('opens the overflow menu with the three actions on the "⋯" button', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    expect(container.querySelector('.util-menu')).toBeNull();
    fireEvent.click(container.querySelector('.util-more'));
    const menu = container.querySelector('.util-menu');
    expect(menu).toBeTruthy();
    const labels = [...menu.querySelectorAll('.util-menu-item')].map((b) => b.textContent.trim());
    expect(labels).toEqual(['Citar painel', 'Compartilhar', 'Enviar feedback']);
    expect(container.querySelector('.util-more').getAttribute('aria-expanded')).toBe('true');
  });

  it('a menu item fires its action and closes the menu (Enviar feedback → feedback modal)', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.util-more'));
    const reportItem = [...container.querySelectorAll('.util-menu-item')].find((b) =>
      b.textContent.includes('Enviar feedback'),
    );
    fireEvent.click(reportItem);
    expect(container.querySelector('.util-menu')).toBeNull(); // menu closed
    expect(container.querySelector('.feedback-modal')).toBeTruthy(); // Enviar feedback opened the modal
  });

  it('closes the overflow menu via the scrim and via Escape', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    fireEvent.click(container.querySelector('.util-more'));
    fireEvent.click(container.querySelector('.util-scrim'));
    expect(container.querySelector('.util-menu')).toBeNull();
    // reopen, then close with Escape (the utilOpen keydown effect)
    fireEvent.click(container.querySelector('.util-more'));
    expect(container.querySelector('.util-menu')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(container.querySelector('.util-menu')).toBeNull();
  });
});

describe('AppShell — mobile topbar: mode toggle relocated to the drawer', () => {
  it('renders the single/multi toggle inside the sidebar with both labels', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    const sw = container.querySelector('.side-mode-switch');
    expect(sw).toBeTruthy();
    const labels = [...sw.querySelectorAll('.mode-opt')].map((b) => b.textContent.trim());
    expect(labels).toContain('Banco único');
    expect(labels).toContain('Multi-fonte');
  });

  it('the drawer mode toggle calls setMode for both options', () => {
    const props = baseProps();
    const { container } = render(<AppShell {...props} />);
    const opts = container.querySelectorAll('.side-mode-switch .mode-opt');
    fireEvent.click(opts[1]); // Multi-fonte
    expect(props.setMode).toHaveBeenCalledWith('multi');
    fireEvent.click(opts[0]); // Banco único
    expect(props.setMode).toHaveBeenCalledWith('single');
  });
});

// ── Reference detail levels (ABNT NBR 6023:2025) ─────────────────────────────
//
// The reference was one fixed string concatenating the banco AND every active filter.
// That is right for "I analysed exactly this slice" and wrong for "I used this tool":
// a methods section citing the dashboard should not send the reader through a UF list.

describe('AppShell — reference detail levels', () => {
  const openCite = (container) => {
    fireEvent.click([...container.querySelectorAll('.util-action')]
      .find((b) => b.textContent.includes('Citar painel')));
  };
  const pick = (container, label) => {
    const lv = [...container.querySelectorAll('.cite-level')].find((l) => l.textContent.includes(label));
    fireEvent.click(lv.querySelector('input'));
    return lv;
  };
  const refText = (container) =>
    [...container.querySelectorAll('.cite-text')].find((n) => !n.classList.contains('cite-text-inline')).textContent;

  it('offers exactly three levels, in a radiogroup', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    const group = container.querySelector('[role="radiogroup"]');
    expect(group).toBeTruthy();
    expect([...group.querySelectorAll('input[type="radio"]')]).toHaveLength(3);
  });

  it('defaults to the detailed level — the behaviour that shipped before the choice', () => {
    // Anyone who opens the modal and copies must get what they got yesterday; the two
    // shorter levels are opt-in, not a silent change to everyone's reference.
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    const on = container.querySelector('.cite-level.on');
    expect(on.textContent).toContain('Consulta detalhada');
    expect(refText(container)).toContain('Recorte:');
  });

  it('"Ferramenta geral" drops the banco AND every filter', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    pick(container, 'Ferramenta geral');
    const txt = refText(container);
    expect(txt).toContain('EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA (EMBRAPA).');
    expect(txt).toContain('Dashboard de análise histórica de produtos agrícolas.');
    // The whole point of this level: no source, no scope.
    expect(txt).not.toContain('IBGE PEVS');
    expect(txt).not.toContain('Recorte:');
    expect(txt).not.toContain('Convenções métricas:');
    // The publication tail survives — it is what makes it a reference at all.
    expect(txt).toContain('Brasília, DF: Embrapa,');
    expect(txt).toContain('Acesso em:');
  });

  it('"Por banco de dados" names the source and nothing else', () => {
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    pick(container, 'Por banco de dados');
    const txt = refText(container);
    // Subtitle after a colon, per the requested format.
    expect(txt).toContain('Dashboard de análise histórica de produtos agrícolas: IBGE PEVS.');
    expect(txt).not.toContain('Recorte:');
    expect(txt).not.toContain('Convenções métricas:');
  });

  it('copies the SELECTED level, not the detailed one', () => {
    // The requirement that ties the feature together: the button under a chosen radio
    // has to copy what the box above it shows.
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    pick(container, 'Ferramenta geral');
    navigator.clipboard.writeText.mockClear();
    fireEvent.click([...container.querySelectorAll('.btn-primary')]
      .find((b) => b.textContent.includes('Copiar referência')));
    const copied = navigator.clipboard.writeText.mock.calls.at(-1)[0];
    expect(copied).toBe(refText(container));
    expect(copied).not.toContain('Recorte:');
  });

  it('keeps the three levels on one author and one publication tail', () => {
    // They may differ ONLY in how much of the panel they describe; a divergent author
    // or access date between levels would be three different references.
    const { container } = render(<AppShell {...baseProps()} />);
    openCite(container);
    const seen = ['Ferramenta geral', 'Por banco de dados', 'Consulta detalhada'].map((l) => {
      pick(container, l);
      return refText(container);
    });
    for (const txt of seen) {
      expect(txt.startsWith('EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA (EMBRAPA).')).toBe(true);
      expect(txt).toContain('Brasília, DF: Embrapa,');
      expect(txt).toContain('Acesso em:');
    }
    expect(new Set(seen).size).toBe(3);   // and they really are three different texts
  });
});
