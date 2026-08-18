// ViewCadastroProdutos.test.jsx — render + write coverage for the Curadoria editor.
// Each commodity is registered by its EXACT source code (código+banco; no prefixes). The
// add form fetches the source's REAL codes (/api/catalog/source-codes) for autocomplete +
// an advisory "já existe na Gold?" hint; a not-yet-listed code is ACCEPTED as pendente de
// ingestão (Salvar needs only a non-empty code + a chosen agrupamento, plus the PPM tag when
// applicable — it does NOT gate on the code existing). The catalog table shows each commodity's
// Gold STATE (/api/catalog/status → linhas, período, tem-dados). Agrupamentos are a FIRST-CLASS
// registry: entries via /api/catalog/entry, groups via /api/catalog/group — all mocked.
// Uses the GLOBAL React (main.jsx sets window.React).

import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';

let ViewCadastroProdutos;
let postBody;
let postUrl;

const ENTRIES = {
  entries: [
    {
      // The seam always returns the EFFECTIVE coded axes (a legacy row is translated
      // server-side), so the fixture carries them like the real API does.
      codigo_produto: '4403', banco: 'comex', agrupamento: 'Madeira',
      ingestao: 'ativa', visibilidade: 'visivel', agrupamento_id: 'madeira',
      descricao_fonte: 'Madeira em toras (NCM)', descricao_produto: 'Nota antiga',
    },
    {
      codigo_produto: '4407', banco: 'comtrade', agrupamento: 'Madeira',
      ingestao: 'ativa', visibilidade: 'visivel', agrupamento_id: 'madeira',
      descricao_fonte: null,
    },
  ],
  total: 2,
};
const GROUPS = {
  groups: [
    { group_id: 'madeira', group_name: 'Madeira', n_members: 2 },
    { group_id: 'castanha', group_name: 'Castanha', n_members: 0 }, // an EMPTY group
  ],
  total: 2,
};
// Per-commodity Gold state (linhas na Gold + período + tem-dados), keyed "banco:code".
const STATUS = {
  status: {
    'comex:4403': { n_rows: 1234, year_start: 1997, year_end: 2023, has_data: true },
    'comtrade:4407': { n_rows: 0, year_start: null, year_end: null, has_data: false },
  },
};
// The source's REAL codes for the add form (comex): includes 0801, so a valid add can fire.
const SOURCE_CODES = {
  banco: 'comex',
  codes: [
    { code: '0801', name: 'Castanhas (NCM)' },
    { code: '4403', name: 'Madeira em toras (NCM)' },
  ],
};

function mockFetch(opts = {}) {
  const {
    entries = ENTRIES, groups = GROUPS, orphans = { orphans: [], total: 0 },
    status = STATUS, sourceCodes = SOURCE_CODES,
    failStatus = false, failSourceCodes = false, failOrphans = false,
  } = opts;
  const notOk = { ok: false, status: 500, json: () => Promise.resolve({}), text: () => Promise.resolve('') };
  global.fetch = vi.fn((url, init) => {
    if (init && init.method === 'POST') {
      postBody = JSON.parse(init.body);
      postUrl = String(url);
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    }
    const u = String(url);
    // Force a specific read to fail (ok:false) so the error-state branches are exercised.
    if (failStatus && u.includes('/api/catalog/status')) return Promise.resolve(notOk);
    if (failSourceCodes && u.includes('/api/catalog/source-codes')) return Promise.resolve(notOk);
    if (failOrphans && u.includes('/api/catalog/orphans')) return Promise.resolve(notOk);
    const body = u.includes('/api/catalog/orphans')
      ? orphans
      : u.includes('/api/catalog/groups')
        ? groups
        : u.includes('/api/catalog/status')
          ? status
          : u.includes('/api/catalog/source-codes')
            ? sourceCodes
            : entries;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve('') });
  });
}

beforeEach(async () => {
  globalThis.React = React;
  window.React = React;
  window.SectionHeader = ({ overline, title, action }) => (
    <div className="sh"><span>{overline}</span><span>{title}</span>{action}</div>
  );
  window.Icon = ({ name }) => <span data-icon={name} />; // used by the CcConfirmModal close button
  postBody = null;
  postUrl = null;
  mockFetch();
  await import('./ViewCadastroProdutos.jsx');
  ViewCadastroProdutos = window.ViewCadastroProdutos;
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// Open the add form, wait for the source-codes to load (so the advisory "já existe" hint is armed).
async function openAddForm(container, getByText) {
  fireEvent.click(getByText('+ Adicionar produto'));
  const codeInput = () => container.querySelector('input[list="cc-code-options"]');
  await waitFor(() => expect(codeInput()).toBeTruthy());
  return codeInput();
}

describe('ViewCadastroProdutos — the Curadoria catalog editor', () => {
  it('renders each agrupamento with members, source description, and Gold-state columns', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // Wait for the async status fetch to populate the linhas/período columns.
    await waitFor(() => expect(container.textContent).toContain('1.234'));
    // The Madeira group header + member count, and the EMPTY Castanha group card too.
    expect(container.textContent).toContain('Madeira');
    expect(container.textContent).toContain('(2)');
    expect(container.textContent).toContain('Castanha');
    expect(container.textContent).toContain('Agrupamento vazio');
    // Friendly banco labels + the source's original description.
    expect(container.textContent).toContain('MDIC COMEX');
    expect(container.textContent).toContain('UN COMTRADE');
    expect(container.textContent).toContain('Madeira em toras (NCM)');
    // Gold-state columns: linhas (pt-BR grouped), período span, and the tem-dados markers.
    expect(container.textContent).toContain('1997–2023');
    // The old "Dados" ✓/sem-dados column was absorbed into the derived Status badge:
    // 4403 has data + is visible → Ativo. 4407 (comtrade) is registered-but-empty and the
    // fixture declares NO catalog_driven_bancos, so it is "Sem dados" — NOT "Pendente de
    // ingestão", which would promise a fetch the trade pipelines never make from the catalog.
    expect(container.querySelector('.cc-status-ativo')).toBeTruthy();
    expect(container.querySelector('.cc-status-sem-dados')).toBeTruthy();
    expect(container.querySelector('.cc-status-pendente')).toBeFalsy();
    const codes = [...container.querySelectorAll('.dt-table tbody td')].map((e) => e.textContent);
    expect(codes).toContain('4403');
    expect(codes).toContain('4407');
    // The code_prefix column is GONE — no "Prefixo" header anywhere.
    expect(container.textContent).not.toContain('Prefixo');
  });

  it('creates a new agrupamento via /api/catalog/group', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const newGroupInput = [...container.querySelectorAll('input[type="text"]')].find(
      (i) => i.getAttribute('placeholder') === 'Ex.: Castanha',
    );
    fireEvent.change(newGroupInput, { target: { value: 'Açaí' } });
    fireEvent.click(getByText('+ Criar'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/group');
    expect(postBody.group_name).toBe('Açaí');
  });

  it('adds a commodity by an EXISTING source code into a chosen agrupamento', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const codeInput = await openAddForm(container, getByText);
    // Type a code the source really has (0801 ∈ SOURCE_CODES) — the "já existe" hint shows ✓.
    fireEvent.change(codeInput, { target: { value: '0801' } });
    fireEvent.change(container.querySelector('.cc-add-card .cc-group-select'), { target: { value: 'castanha' } });
    // The Salvar button un-disables once a code is present + a group is chosen.
    const saveBtn = getByText('Salvar produto');
    await waitFor(() => expect(saveBtn.disabled).toBe(false));
    fireEvent.click(saveBtn);
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.codigo_produto).toBe('0801');
    expect(postBody.agrupamento_id).toBe('castanha');
    expect(postBody.agrupamento).toBe('Castanha');
    expect(postBody.banco).toBe('comex');
  });

  it('accepts a NOT-YET-INGESTED code as pendente de ingestão: soft warning, Salvar enabled, POST fires', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const codeInput = await openAddForm(container, getByText);
    // 9999 is NOT in the source's real codes — no longer blocked: the catalog drives
    // ingestion, so it registers as pending and the next run will fetch it.
    fireEvent.change(codeInput, { target: { value: '9999' } });
    fireEvent.change(container.querySelector('.cc-add-card .cc-group-select'), { target: { value: 'castanha' } });
    // A soft warning appears (not a hard block) and Salvar un-disables.
    await waitFor(() => expect(container.textContent).toContain('ainda não ingerido'));
    const saveBtn = getByText('Salvar produto');
    expect(saveBtn.disabled).toBe(false);
    fireEvent.click(saveBtn);
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.codigo_produto).toBe('9999');
  });

  it('PPM requires the sidra_tabela sub-select and sends it in the POST', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const codeInput = await openAddForm(container, getByText);
    // Switch banco to IBGE PPM → the "Tabela PPM" sub-select appears.
    fireEvent.change(container.querySelectorAll('.cc-add-card select')[0], { target: { value: 'ppm' } });
    await waitFor(() => expect(container.textContent).toContain('Tabela PPM'));
    fireEvent.change(codeInput, { target: { value: '2670' } });
    fireEvent.change(container.querySelector('.cc-add-card .cc-group-select'), { target: { value: 'castanha' } });
    // Without the table chosen, Salvar stays disabled (the tag is mandatory for PPM).
    expect(getByText('Salvar produto').disabled).toBe(true);
    // Pick "Rebanho" (SIDRA 3939) → Salvar enables and the POST carries sidra_tabela.
    const tabelaSelect = [...container.querySelectorAll('.cc-add-card select')].find(
      (s) => [...s.options].some((o) => o.value === '3939'),
    );
    fireEvent.change(tabelaSelect, { target: { value: '3939' } });
    await waitFor(() => expect(getByText('Salvar produto').disabled).toBe(false));
    fireEvent.click(getByText('Salvar produto'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postBody.banco).toBe('ppm');
    expect(postBody.sidra_tabela).toBe('3939');
  });

  it('says "Pendente de ingestão" ONLY for a banco the catalog actually steers', async () => {
    // Same empty produto, two worlds. The catalog drives ingestion only for the IBGE
    // pipelines, and only while catalog_authoritative_ingestion is on; the backend reports
    // that as catalog_driven_bancos. Registering a COMEX/COMTRADE code never schedules a
    // fetch, so promising one there is a lie the researcher cannot check.
    const entries = {
      entries: [{
        codigo_produto: '3405', banco: 'pevs', agrupamento: 'Bambu',
        ingestao: 'ativa', visibilidade: 'visivel', agrupamento_id: 'bambu',
      }],
      total: 1,
      catalog_driven_bancos: ['pevs', 'pam', 'ppm'],
    };
    const status = { status: { 'pevs:3405': { n_rows: 0, year_start: null, year_end: null, has_data: false } } };
    mockFetch({ entries, status, groups: { groups: [{ group_id: 'bambu', group_name: 'Bambu', n_members: 1 }] } });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-status')).toBeTruthy());
    expect(container.querySelector('.cc-status-pendente')).toBeTruthy();
    expect(container.querySelector('.cc-status-sem-dados')).toBeFalsy();
  });

  it('never promises the hide takes effect in "minutos"', async () => {
    // The serving marts apply the visibility gate at BUILD time, and prod rebuilds on the
    // DAILY dbt-build-prod schedule (cron 30 11 * * * = 08:30 BRT). The copy used to say
    // "pode levar alguns minutos", wrong by up to a day: a researcher who hid a produto,
    // waited five minutes and still saw it charted would conclude the control was broken.
    mockFetch();
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-status')).toBeTruthy());
    const texto = container.textContent;
    expect(texto).not.toMatch(/alguns minutos/i);
    expect(texto).toMatch(/reconstrução diária/i);
  });

  it('read-only when can_edit is false: banner shown, edit controls disabled', async () => {
    mockFetch({ entries: { ...ENTRIES, can_edit: false } });
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    expect(container.textContent).toContain('Modo somente leitura');
    expect(getByText('+ Adicionar produto').disabled).toBe(true);
    // The inline row controls (remove) are disabled too.
    expect(container.querySelector('.cc-remove').disabled).toBe(true);
  });

  it('requires an agrupamento: with a valid code but no group, Salvar stays disabled', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const codeInput = await openAddForm(container, getByText);
    fireEvent.change(codeInput, { target: { value: '0801' } }); // valid code…
    // …but no agrupamento chosen → the button stays disabled and nothing is posted.
    await waitFor(() => expect(container.querySelector('.cc-hint-ok')).toBeTruthy());
    expect(getByText('Salvar produto').disabled).toBe(true);
    expect(postBody).toBeNull();
  });

  it('documents EVERY table column in the collapsible legend', async () => {
    // The legend is the in-product reference for the table. If a column is added and not
    // documented, the researcher meets an unexplained header — so pin the two lists together
    // rather than trusting they stay in sync by hand.
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
    const headers = [...container.querySelectorAll('.cc-table thead th')]
      .map((th) => th.textContent.trim())
      .filter(Boolean); // the ações column header is intentionally empty (icon-only)
    const documented = [...container.querySelectorAll('.cc-help-item dt')].map((dt) => dt.textContent.trim());
    for (const h of headers) {
      expect(documented.some((d) => d.startsWith(h))).toBe(true);
    }
  });

  it('keeps the legend collapsed by default so it never pushes the table down', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
    const details = container.querySelector('details.cc-help');
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    // The summary states what's inside, and the counts come from the data (not hardcoded).
    expect(details.querySelector('summary').textContent).toContain('Como ler esta tabela');
  });

  it('explains that removal is non-destructive and that hiding keeps ingesting', async () => {
    // These two are the actions most easily misread as data loss / as stopping the pipeline.
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
    const legend = container.querySelector('.cc-help').textContent;
    expect(legend).toContain('NÃO são apagados');
    expect(legend).toContain('a ingestão segue normalmente');
    expect(legend).toContain('somente-adição');
  });

  it('pauses ingestion without a confirmation and without touching visibility', async () => {
    // Pausing is reversible and destroys nothing (history stays, produto stays visible), so
    // unlike hiding it must NOT gate behind the modal.
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const sel = container.querySelector('select[aria-label="Ingestão de 4403"]');
    fireEvent.change(sel, { target: { value: 'pausada' } });
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(container.querySelector('.cite-modal')).toBeNull(); // no confirmation
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.ingestao).toBe('pausada');
    expect(postBody.visibilidade).toBe('visivel'); // the OTHER axis is untouched
  });

  it('confirms before hiding, and hiding does not pause ingestion', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const sel = container.querySelector('select[aria-label="Visibilidade de 4403"]');
    fireEvent.change(sel, { target: { value: 'oculto' } });
    // Hiding pulls it from every chart → gated behind the accessible modal.
    await waitFor(() => expect(container.querySelector('.cite-modal[role="dialog"]')).toBeTruthy());
    expect(postBody).toBeNull();
    fireEvent.click(container.querySelector('.cite-modal .btn-primary'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postBody.visibilidade).toBe('oculto');
    expect(postBody.ingestao).toBe('ativa'); // still fetching — the axes are independent
  });

  it('derives the Status badge from the axes, with pausada outranking "sem dados"', async () => {
    // A frozen produto that never arrived is Pausado, not Pendente: calling it pending would
    // promise an ingestion that will never come.
    mockFetch({
      entries: {
        entries: [
          { codigo_produto: '1', banco: 'comex', agrupamento: 'Madeira', agrupamento_id: 'madeira',
            ingestao: 'ativa', visibilidade: 'visivel' },
          { codigo_produto: '2', banco: 'comex', agrupamento: 'Madeira', agrupamento_id: 'madeira',
            ingestao: 'ativa', visibilidade: 'oculto' },
          { codigo_produto: '3', banco: 'comex', agrupamento: 'Madeira', agrupamento_id: 'madeira',
            ingestao: 'pausada', visibilidade: 'visivel' },
          { codigo_produto: '4', banco: 'comex', agrupamento: 'Madeira', agrupamento_id: 'madeira',
            ingestao: 'pausada', visibilidade: 'visivel' },
        ],
        total: 4,
      },
      status: {
        status: {
          'comex:1': { n_rows: 10, year_start: 2000, year_end: 2020, has_data: true },
          'comex:2': { n_rows: 10, year_start: 2000, year_end: 2020, has_data: true },
          'comex:3': { n_rows: 10, year_start: 2000, year_end: 2020, has_data: true },
          'comex:4': { n_rows: 0, year_start: null, year_end: null, has_data: false },
        },
      },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-status')).toBeTruthy());
    await waitFor(() => expect(container.querySelectorAll('.cc-status').length).toBe(4));
    const badges = [...container.querySelectorAll('.cc-status')].map((b) => b.textContent);
    expect(badges).toEqual(['Ativo', 'Oculto', 'Pausado', 'Pausado']);
  });

  it('reads a LEGACY row (no coded axes) as ativa/visivel rather than blank', async () => {
    // Rows written before the two-axis split arrive without the coded fields; the UI must
    // fall back to the safe defaults instead of rendering an empty dropdown.
    mockFetch({
      entries: {
        entries: [{
          codigo_produto: '4403', banco: 'comex', agrupamento: 'Madeira', agrupamento_id: 'madeira',
          ciclo_de_vida: 'Fazer Ingestão e deixar disponível',
        }],
        total: 1,
      },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    expect(container.querySelector('select[aria-label="Ingestão de 4403"]').value).toBe('ativa');
    expect(container.querySelector('select[aria-label="Visibilidade de 4403"]').value).toBe('visivel');
  });

  it('moves a commodity to another agrupamento via the row group dropdown', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // The first member row's Agrupamento <select> (a .cc-group-select inside the table).
    fireEvent.change(container.querySelector('.dt-table .cc-group-select'), { target: { value: 'castanha' } });
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.agrupamento_id).toBe('castanha');
    expect(postBody.agrupamento).toBe('Castanha');
  });

  it('tags a PPM row with its SIDRA table next to the BANCO (not inside the Descrição cell)', async () => {
    // PPM is the one banco storing two SIDRA tables (3939 rebanho / 74 produção animal) under
    // one banco token, so the tag qualifies the SOURCE. It must sit in the banco cell — putting
    // it under the researcher's annotation (where it used to be) read like part of that note.
    mockFetch({
      entries: {
        entries: [{
          codigo_produto: '2670', banco: 'ppm', agrupamento: 'Madeira', agrupamento_id: 'madeira',
          ciclo_de_vida: 'Fazer Ingestão e deixar disponível',
          descricao_fonte: 'Bovino', sidra_tabela: '3939',
        }],
        total: 1,
      },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const tag = container.querySelector('.cc-sidra-tag');
    expect(tag.textContent).toBe('Rebanho (efetivo)');
    // It lives in the banco (title) cell, and NOT in the Descrição cell.
    expect(tag.closest('td').classList.contains('cc-cell-title')).toBe(true);
    expect(container.querySelector('td[data-label="Descrição"] .cc-sidra-tag')).toBeNull();
  });

  it('omits the SIDRA tag for non-PPM bancos', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    expect(container.querySelector('.cc-sidra-tag')).toBeNull(); // comex + comtrade rows
  });

  it('shows the existing manual descrição pre-filled, and edits it after creation via blur-commit', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // 4403 already has a saved descricao_produto — the field round-trips it, not just at creation.
    const input = container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]');
    expect(input.value).toBe('Nota antiga');
    // Typing alone must NOT fire a save (no round-trip on every keystroke) — only blur commits.
    fireEvent.change(input, { target: { value: 'Nota atualizada' } });
    expect(postBody).toBeNull();
    fireEvent.blur(input);
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.codigo_produto).toBe('4403');
    expect(postBody.descricao_produto).toBe('Nota atualizada');
    // Every other field round-trips unchanged (this is an edit of ONE attribute, not a re-add).
    expect(postBody.agrupamento_id).toBe('madeira');
  });

  it('does not re-save the manual descrição on blur when the (trimmed) value is unchanged', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    const input = container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]');
    fireEvent.change(input, { target: { value: '  Nota antiga  ' } }); // same content, stray whitespace
    fireEvent.blur(input);
    expect(postBody).toBeNull();
  });

  it('removes a commodity via the tombstone endpoint (after confirming in the accessible modal)', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-remove')).toBeTruthy());
    fireEvent.click(container.querySelector('.cc-remove'));
    // The native window.confirm is gone — an accessible in-app modal (role=dialog) opens; the
    // POST fires only once the user clicks the modal's confirm button, not on the row click.
    await waitFor(() => expect(container.querySelector('.cite-modal[role="dialog"]')).toBeTruthy());
    expect(postBody).toBeNull(); // nothing sent until confirmed
    fireEvent.click(container.querySelector('.cite-modal .btn-primary'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry/remove');
    expect(postBody.codigo_produto).toBe('4403');
  });

  it('renames an agrupamento via the modal text input (no native prompt)', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // Groups sort alphabetically (Castanha before Madeira); target the Madeira card's Renomear.
    const madeiraCard = [...container.querySelectorAll('.card')].find((c) => {
      const h = c.querySelector('.cc-group-head strong');
      return h && h.textContent.includes('Madeira');
    });
    const renameBtn = [...madeiraCard.querySelectorAll('button')].find((b) => b.textContent.includes('Renomear'));
    fireEvent.click(renameBtn);
    await waitFor(() => expect(container.querySelector('#cc-confirm-input')).toBeTruthy());
    fireEvent.change(container.querySelector('#cc-confirm-input'), { target: { value: 'Madeira Nova' } });
    fireEvent.click(container.querySelector('.cite-modal .btn-primary'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/group');
    expect(postBody.group_name).toBe('Madeira Nova');
    expect(postBody.group_id).toBe('madeira');
  });

  it('deletes an empty agrupamento via the modal confirm (no native confirm)', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // Castanha is the empty group (n_members:0) → its "🗑 Excluir" is enabled.
    const castanhaCard = [...container.querySelectorAll('.card')].find((c) => {
      const h = c.querySelector('.cc-group-head strong');
      return h && h.textContent.includes('Castanha');
    });
    const delBtn = [...castanhaCard.querySelectorAll('button')].find((b) => b.textContent.includes('Excluir'));
    fireEvent.click(delBtn);
    await waitFor(() => expect(container.querySelector('.cite-modal[role="dialog"]')).toBeTruthy());
    expect(postBody).toBeNull(); // nothing sent until confirmed
    fireEvent.click(container.querySelector('.cite-modal .btn-primary'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/group/remove');
    expect(postBody.group_id).toBe('castanha');
  });

  it('surfaces a Gold-state (status) fetch failure as a distinct banner + "—" cells (not silent "…")', async () => {
    mockFetch({ failStatus: true });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    // The catalog itself loaded (entries ok); only the lazy status read failed → the warn banner shows.
    await waitFor(() => expect(container.textContent).toContain('Não foi possível carregar o estado dos produtos no Gold'));
    // The Linhas cell shows '—' (unknown, explained by the banner), not the perpetual-loading '…'.
    const linhasCell = container.querySelector('.dt-table td[data-label="Linhas"]');
    expect(linhasCell.textContent).toBe('—');
  });

  it('surfaces a source-codes fetch failure in the add form (not a false "0 códigos")', async () => {
    mockFetch({ failSourceCodes: true });
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    fireEvent.click(getByText('+ Adicionar produto'));
    await waitFor(() => expect(container.textContent).toContain('Não foi possível carregar os códigos'));
  });

  it('does NOT show the Gold-state banner when the catalog itself failed to load', async () => {
    // A total outage: entries + status both fail. The banner must stay hidden so we never claim
    // "o cadastro continua válido" next to the catalog's own "Erro ao carregar".
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}), text: () => Promise.resolve('') }));
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.textContent).toContain('Erro ao carregar'));
    expect(container.textContent).not.toContain('O cadastro continua válido');
  });

  it('surfaces an orphans (Descontinuados) fetch failure instead of silently hiding the section', async () => {
    // The Descontinuados section is gated on orphans.length > 0, so a failed orphans read would
    // otherwise vanish silently — there may be discontinued produtos not shown.
    mockFetch({ failOrphans: true });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
    await waitFor(() => expect(container.textContent).toContain('Não foi possível carregar os produtos descontinuados'));
  });

  it('surfaces orphans as Descontinuados with the human-only deletion warning', async () => {
    mockFetch({
      orphans: {
        orphans: [{
          codigo_produto: '20079926', banco: 'comex', agrupamento: 'Cupuaçu',
          status: 'descontinuado', flagged_at: null,
          warning: 'será removida por um operador',
        }],
        total: 1,
      },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.textContent).toContain('Descontinuados'));
    expect(container.textContent).toContain('Cupuaçu');
    expect(container.textContent).toContain('20079926');
    expect(container.textContent).toContain('nunca automaticamente');
  });
});
