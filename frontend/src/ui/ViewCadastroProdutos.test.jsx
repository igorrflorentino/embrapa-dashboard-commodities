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

/**
 * Espera o cadastro carregar e ABRE todos os agrupamentos.
 *
 * Desde v1.42.0 cada agrupamento nasce RECOLHIDO — com 31 cartões abertos a tela abria com
 * ~234 linhas. Quase todo teste aqui é sobre o conteúdo da tabela, então em vez de repetir o
 * clique em 20 lugares, este helper substitui o antigo `waitFor(.dt-table)`: ele espera o
 * cabeçalho do primeiro agrupamento (o sinal de que os dados chegaram), clica em "Expandir
 * todos" e só então espera a tabela. Um teste que queira verificar o estado RECOLHIDO não usa
 * o helper — chama `render` direto.
 */
async function abrirAgrupamentos(container) {
  await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
  const expandir = [...container.querySelectorAll('button')]
    .find((b) => /Expandir todos/.test(b.textContent));
  if (expandir) fireEvent.click(expandir);
  await waitFor(() => expect(container.querySelector('.dt-table')).toBeTruthy());
}

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

// ── Diagnóstico para um flake que NÃO conseguimos reproduzir ────────────────────
//
// "shows the existing manual descrição pre-filled…" falhou duas vezes (CI num PR só de
// documentação, 2026-08-28; e uma vez na suíte completa local) e passa em todo o resto.
// Foram descartados, cada um por medição: estouro de prazo do waitFor (todas as esperas
// deste arquivo passam com timeout de 1 ms — nada aqui precisa de relógio), chamadas de
// fetch atravessando a fronteira entre testes (instrumentado: nenhuma), dependência de
// ordem (--sequence.shuffle), o modo --coverage do CI, CPU saturada com 24 processos de
// carga, e uma closure obsoleta no onBlur (construída de propósito: o POST sai correto
// mesmo sem re-render entre o change e o blur).
//
// Sem mecanismo identificado, o que ainda tem valor é não gastar outra hora na próxima
// vez: estas asserções passam a dizer O QUE VIRAM. Um "Timed out in waitFor" não
// distingue "a linha não chegou" de "o campo estava desabilitado" de "o POST saiu para
// a URL errada" — e essa distinção é o diagnóstico inteiro.
const _diag = (container) => {
  const campo = container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]');
  const chamadas = (global.fetch && global.fetch.mock ? global.fetch.mock.calls : [])
    .map((c) => `${(c[1] && c[1].method) || 'GET'} ${String(c[0]).split('/api')[1] || c[0]}`);
  return JSON.stringify({
    linhasNaTabela: container.querySelectorAll('.dt-table tbody tr').length,
    campoExiste: !!campo,
    campoValor: campo ? campo.value : null,
    campoDesabilitado: campo ? campo.disabled : null,
    postUrl,
    postBody,
    fetches: chamadas,
  }, null, 2);
};
// waitFor que, ao estourar, conta o que estava na tela em vez de só dizer que estourou.
const esperar = (container, predicado, oQue) =>
  waitFor(() => expect(predicado()).toBe(true), {
    onTimeout: (err) => new Error(`${oQue}\n\nEstado no momento da falha:\n${_diag(container)}\n\n${err.message}`),
  });

describe('ViewCadastroProdutos — the Curadoria catalog editor', () => {
  it('renders each agrupamento with members, source description, and Gold-state columns', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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

  it('PEVS offers the two SIDRA halves, and the tag is REQUIRED there', async () => {
    // PEVS spans t289 (extração vegetal) + t291 (silvicultura), so it gets the same
    // sub-select PPM has — e com a mesma exigência. A marca virou obrigatória quando a
    // identidade de um produto passou a ser (banco, tabela, código): sem ela a entrada não
    // cai em nenhuma das duas metades, cai numa TERCEIRA identidade que não corresponde a
    // dado nenhum. Era opcional enquanto a chave a ignorava.
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    const codeInput = await openAddForm(container, getByText);
    fireEvent.change(container.querySelectorAll('.cc-add-card select')[0], { target: { value: 'pevs' } });
    await waitFor(() => expect(container.textContent).toContain('Metade do PEVS'));
    const meia = [...container.querySelectorAll('.cc-add-card select')].find(
      (s) => [...s.options].some((o) => o.value === '291'),
    );
    expect([...meia.options].map((o) => o.value)).toEqual(['', '289', '291']);
    fireEvent.change(codeInput, { target: { value: '3457' } });
    fireEvent.change(container.querySelector('.cc-add-card .cc-group-select'), { target: { value: 'castanha' } });
    // Sem metade escolhida, Salvar fica BLOQUEADO — igual ao PPM.
    expect(getByText('Salvar produto').disabled).toBe(true);
    fireEvent.change(meia, { target: { value: '291' } });
    await waitFor(() => expect(getByText('Salvar produto').disabled).toBe(false));
    fireEvent.click(getByText('Salvar produto'));
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postBody.banco).toBe('pevs');
    expect(postBody.sidra_tabela).toBe('291');
  });

  it('shows the SIDRA-half tag on a pevs row, not only on ppm', async () => {
    // The chip was gated on `banco === 'ppm'`, so a silvicultura produto looked identical
    // to an extraction one in the listing — the two halves differ ~4× in size and share
    // agrupamentos (madeira/lenha/carvão), so the row alone could not tell them apart.
    mockFetch({
      entries: {
        entries: [{
          codigo_produto: '3457', banco: 'pevs', agrupamento: 'Madeira', agrupamento_id: 'madeira',
          descricao_fonte: 'Madeira em tora', sidra_tabela: '291',
        }],
        total: 1,
      },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    const celula = container.querySelector('td[data-label="Tabela"]');
    // O CÓDIGO da tabela SIDRA, não o nome por extenso; o nome fica no title.
    expect(celula.textContent.trim()).toBe('291');
    expect(celula.getAttribute('title')).toBe('Silvicultura');
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
    await waitFor(() => expect(container.querySelector('.cc-status')).toBeTruthy());
    const texto = container.textContent;
    expect(texto).not.toMatch(/alguns minutos/i);
    expect(texto).toMatch(/reconstrução diária/i);
  });

  it('read-only when can_edit is false: banner shown, edit controls disabled', async () => {
    mockFetch({ entries: { ...ENTRIES, can_edit: false } });
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    expect(container.textContent).toContain('Modo somente leitura');
    expect(getByText('+ Adicionar produto').disabled).toBe(true);
    // The inline row controls (remove) are disabled too.
    expect(container.querySelector('.cc-remove').disabled).toBe(true);
  });

  it('requires an agrupamento: with a valid code but no group, Salvar stays disabled', async () => {
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
    const details = container.querySelector('details.cc-help');
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    // The summary states what's inside, and the counts come from the data (not hardcoded).
    expect(details.querySelector('summary').textContent).toContain('Como ler esta tabela');
  });

  it('explains that removal is non-destructive and that hiding keeps ingesting', async () => {
    // These two are the actions most easily misread as data loss / as stopping the pipeline.
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    const legend = container.querySelector('.cc-help').textContent;
    expect(legend).toContain('NÃO são apagados');
    expect(legend).toContain('a ingestão segue normalmente');
    expect(legend).toContain('somente-adição');
  });

  it('pauses ingestion without a confirmation and without touching visibility', async () => {
    // Pausing is reversible and destroys nothing (history stays, produto stays visible), so
    // unlike hiding it must NOT gate behind the modal.
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
    expect(container.querySelector('select[aria-label="Ingestão de 4403"]').value).toBe('ativa');
    expect(container.querySelector('select[aria-label="Visibilidade de 4403"]').value).toBe('visivel');
  });

  it('moves a commodity to another agrupamento via the row group dropdown', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    // The first member row's Agrupamento <select> (a .cc-group-select inside the table).
    fireEvent.change(container.querySelector('.dt-table .cc-group-select'), { target: { value: 'castanha' } });
    await waitFor(() => expect(postBody).toBeTruthy());
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.agrupamento_id).toBe('castanha');
    expect(postBody.agrupamento).toBe('Castanha');
  });

  it('mostra a tabela SIDRA em COLUNA própria, não escondida na célula do banco', async () => {
    // A identidade de um produto é banco + tabela + código, então o trio lê da esquerda para
    // a direita em colunas próprias. O selo já esteve embaixo da anotação do pesquisador (onde
    // lia como parte dela) e depois dentro da célula do banco — o que escondia um terço da
    // chave dentro de outro terço.
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
    await abrirAgrupamentos(container);
    const celula = container.querySelector('td[data-label="Tabela"]');
    expect(celula.textContent.trim()).toBe('3939');
    expect(celula.getAttribute('title')).toBe('Rebanho (efetivo)');
    // Coluna própria — o código não voltou para dentro da célula do banco nem da Descrição.
    expect(container.querySelector('td.cc-cell-title').textContent).not.toContain('3939');
    expect(container.querySelector('td[data-label="Descrição"]').textContent).not.toContain('3939');
    // A coluna usa a mesma classe numérica do resto da tabela, não um selo próprio.
    expect(celula.className).toContain('tnum');
  });

  it('omits the SIDRA tag for SINGLE-TABLE bancos', async () => {
    // "non-PPM" until 2026-08-29; pevs joined ppm as multi-table, so what earns a tag is
    // spanning two SIDRA tables, not being ppm.
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
    // comex + comtrade: a coluna existe (senão o leitor não sabe se sumiu) mas vem vazia.
    const celulas = [...container.querySelectorAll('td[data-label="Tabela"]')];
    expect(celulas.length).toBeGreaterThan(0);
    for (const c of celulas) expect(c.textContent.trim()).toBe('—');
  });

  it('shows the existing manual descrição pre-filled, and edits it after creation via blur-commit', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    // Wait for the INPUT the test is about, not just for the table around it: the rows are
    // populated a tick after `.dt-table` mounts, so gating on the table let this read a
    // not-yet-filled field. Passed locally and failed under CI load (2026-08-28).
    await abrirAgrupamentos(container);
    await esperar(container,
      () => container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]')?.value === 'Nota antiga',
      'O campo de descrição de 4403 nunca chegou com a nota salva.');
    // 4403 already has a saved descricao_produto — the field round-trips it, not just at creation.
    const input = container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]');
    // Typing alone must NOT fire a save (no round-trip on every keystroke) — only blur commits.
    fireEvent.change(input, { target: { value: 'Nota atualizada' } });
    expect(postBody, `Digitar não pode salvar. Estado:\n${_diag(container)}`).toBeNull();
    fireEvent.blur(input);
    await esperar(container, () => postBody !== null,
      'O blur não disparou o salvamento da descrição.');
    expect(postUrl).toContain('/api/catalog/entry');
    expect(postBody.codigo_produto).toBe('4403');
    expect(postBody.descricao_produto).toBe('Nota atualizada');
    // Every other field round-trips unchanged (this is an edit of ONE attribute, not a re-add).
    expect(postBody.agrupamento_id).toBe('madeira');
  });

  it('does not re-save the manual descrição on blur when the (trimmed) value is unchanged', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    // Same reason as above: gate on the field's own value, not on the table's presence.
    await abrirAgrupamentos(container);
    await esperar(container,
      () => container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]')?.value === 'Nota antiga',
      'O campo de descrição de 4403 nunca chegou com a nota salva.');
    const input = container.querySelector('.cc-descricao-input[aria-label="Sua descrição de 4403"]');
    fireEvent.change(input, { target: { value: '  Nota antiga  ' } }); // same content, stray whitespace
    fireEvent.blur(input);
    expect(postBody).toBeNull();
  });

  it('removes a commodity via the tombstone endpoint (after confirming in the accessible modal)', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
    // The catalog itself loaded (entries ok); only the lazy status read failed → the warn banner shows.
    await waitFor(() => expect(container.textContent).toContain('Não foi possível carregar o estado dos produtos no Gold'));
    // The Linhas cell shows '—' (unknown, explained by the banner), not the perpetual-loading '…'.
    const linhasCell = container.querySelector('.dt-table td[data-label="Linhas"]');
    expect(linhasCell.textContent).toBe('—');
  });

  it('surfaces a source-codes fetch failure in the add form (not a false "0 códigos")', async () => {
    mockFetch({ failSourceCodes: true });
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);
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
    await abrirAgrupamentos(container);
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

  it('a coluna Tabela existe, é documentada e as larguras somam 100%', async () => {
    // Três coisas que só quebram juntas. As larguras da tabela são POSICIONAIS
    // (`nth-child`), então inserir uma coluna desloca todas as seguintes: ao acrescentar
    // "Tabela", "Código" herdou os 16% de "Descrição" e "Exibição" caiu para 42px, com o
    // cabeçalho quebrando em "Ex/ib/iç/ão". O CSS não é exercitado pelo jsdom, então o que
    // dá para prender aqui é a soma — que é justamente o que denuncia o deslocamento.
    const { container, getByText } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);

    const cabecalhos = [...container.querySelectorAll('.cc-table thead th')]
      .map((th) => th.textContent.trim()).filter(Boolean);
    expect(cabecalhos.slice(0, 3)).toEqual(['Banco', 'Tabela', 'Código']);

    // A legenda é a referência em produto: coluna sem verbete vira cabeçalho inexplicado.
    expect(getByText('Tabela', { selector: '.cc-help-k, dt, strong, b' })).toBeTruthy();
  });

  // ── Agrupamentos recolhíveis + busca ──────────────────────────────────────────────────

  it('abre com TODOS os agrupamentos recolhidos — nenhuma tabela na tela', async () => {
    // A tela abria com ~234 linhas de uma vez. O que se prende aqui não é "existe um botão",
    // é que a TABELA não está montada: um cartão que só esconde por CSS não resolve nada.
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
    expect(container.querySelector('.cc-table')).toBeNull();
    for (const b of container.querySelectorAll('.cc-group-toggle')) {
      expect(b.getAttribute('aria-expanded')).toBe('false');
    }
  });

  it('o toggle abre só o agrupamento clicado, e fecha de novo', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
    const madeira = [...container.querySelectorAll('.cc-group-toggle')]
      .find((b) => b.textContent.includes('Madeira'));

    fireEvent.click(madeira);
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
    // Só UM cartão abriu: o outro agrupamento continua sem tabela.
    expect(container.querySelectorAll('.cc-table').length).toBe(1);
    expect(madeira.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(madeira);
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeNull());
  });

  it('a busca acha pelo CÓDIGO e some com os agrupamentos que não têm o produto', async () => {
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
    fireEvent.change(container.querySelector('.cc-busca-input'), { target: { value: '4403' } });

    // O resultado aparece SEM precisar expandir: um acerto escondido é o mesmo que nenhum.
    await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
    const codigos = [...container.querySelectorAll('.cc-table td[data-label="Código"]')]
      .map((td) => td.textContent.trim());
    expect(codigos).toEqual(['4403']);              // o 4407 do mesmo agrupamento saiu
    // Restou UM cartão. (Olhar `textContent` não serve: "Castanha" também aparece nas
    // <option> do seletor de agrupamento e no placeholder do campo de criar.)
    const cartoes = [...container.querySelectorAll('.cc-group-toggle')];
    expect(cartoes.length).toBe(1);
    expect(cartoes[0].textContent).toContain('Madeira');
    expect(cartoes[0].textContent).toContain('1 de 2');   // quantos bateram, de quantos há
  });

  it('a busca acha pela DESCRIÇÃO ignorando acento, caixa e hífen', async () => {
    // É assim que o pesquisador digita quando só quer saber se o produto já está cadastrado:
    // sem acento, sem hífen, na caixa que der. A fixture PRECISA ter acento e hífen, senão o
    // teste passa mesmo com a normalização removida — foi o que aconteceu na primeira versão
    // deste teste, que buscava "MADEIRA em TORAS" contra "Madeira em toras" e só exercitava a
    // caixa. Cada termo abaixo isola uma das três dobras.
    mockFetch({
      entries: {
        entries: [{
          codigo_produto: '0801', banco: 'comex', agrupamento: 'Castanha',
          agrupamento_id: 'castanha', ingestao: 'ativa', visibilidade: 'visivel',
          // SEM hífen de propósito: o caso que exige dobrar pontuação é o usuário digitar
          // "castanha-do-pará" quando a fonte escreveu com espaços. No sentido contrário a
          // busca acharia sozinha, porque os termos são casados por substring — foi por isso
          // que a primeira versão deste teste passava com a normalização de hífen removida.
          descricao_fonte: 'Castanha do Pará com casca',
        }],
        total: 1,
      },
      groups: { groups: [{ group_id: 'castanha', group_name: 'Castanha', n_members: 1 }], total: 1 },
    });
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
    const campo = container.querySelector('.cc-busca-input');

    for (const termo of ['castanha do para', 'CASTANHA-DO-PARÁ', 'pará com casca']) {
      fireEvent.change(campo, { target: { value: termo } });
      await waitFor(() => expect(container.querySelector('.cc-table')).toBeTruthy());
      expect([...container.querySelectorAll('.cc-table td[data-label="Código"]')]
        .map((td) => td.textContent.trim()), `não achou com "${termo}"`).toEqual(['0801']);
    }
  });

  it('busca sem resultado DIZ que não achou — é a resposta à pergunta', async () => {
    // "0 produtos" responde "não, não está cadastrado". Uma área em branco não responde nada,
    // e é indistinguível de uma falha de carregamento.
    const { container } = render(<ViewCadastroProdutos />);
    await waitFor(() => expect(container.querySelector('.cc-group-toggle')).toBeTruthy());
    fireEvent.change(container.querySelector('.cc-busca-input'), { target: { value: 'zzz-nao-existe' } });
    await waitFor(() => expect(container.textContent).toMatch(/Nenhum produto cadastrado combina/));
    expect(container.querySelector('.cc-busca-saldo').textContent).toContain('0 produto');
  });
});

describe('rolagem horizontal sincronizada entre cartões', () => {
  /**
   * jsdom não faz layout: `scrollLeft` é sempre 0 e o setter não guarda nada. Sem esta
   * prótese o teste passaria verde com o handler vazio — mediria a limitação do jsdom, não
   * o código. Cada elemento ganha um `scrollLeft` de verdade.
   */
  function comScrollLeftReal(elementos) {
    for (const el of elementos) {
      let v = 0;
      Object.defineProperty(el, 'scrollLeft', {
        get: () => v,
        set: (x) => { v = x; },
        configurable: true,
      });
    }
  }

  /**
   * O fixture padrão tem DOIS agrupamentos, mas o segundo é vazio — e grupo vazio não
   * renderiza tabela, então sobra um `.cc-dt-wrap` só e não há o que sincronizar. Aqui os
   * dois precisam ter membro.
   */
  function doisCartoesPovoados() {
    return {
      entries: {
        entries: [
          ...ENTRIES.entries,
          {
            codigo_produto: '0801', banco: 'comex', agrupamento: 'Castanha',
            ingestao: 'ativa', visibilidade: 'visivel', agrupamento_id: 'castanha',
            descricao_fonte: 'Castanha-do-pará',
          },
        ],
        total: 3,
      },
      groups: {
        groups: [
          { group_id: 'madeira', group_name: 'Madeira', n_members: 2 },
          { group_id: 'castanha', group_name: 'Castanha', n_members: 1 },
        ],
        total: 2,
      },
    };
  }

  it('rolar um cartão move os outros para o mesmo x', async () => {
    mockFetch(doisCartoesPovoados());
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);

    const wraps = [...document.querySelectorAll('.cc-dt-wrap')];
    expect(wraps.length).toBeGreaterThan(1); // sem dois cartões não há o que sincronizar
    comScrollLeftReal(wraps);

    wraps[0].scrollLeft = 137;
    fireEvent.scroll(wraps[0]);

    // Todos os outros seguem — é isso que preserva a grade de colunas compartilhada, o
    // motivo pelo qual as larguras são fixas em primeiro lugar.
    for (const el of wraps.slice(1)) expect(el.scrollLeft).toBe(137);
  });

  /**
   * ⚠ O que este teste NÃO prende, dito na cara: o guarda `sincronizando` do handler. Ele
   * existe porque num navegador de verdade atribuir `scrollLeft` DISPARA `scroll` nos
   * outros cartões, e sem o flag cada um reagiria ao vizinho. O jsdom não emite `scroll`
   * em atribuição programática, então esse laço não é reproduzível aqui — removi o flag
   * numa injeção e a suíte ficou verde. Registrar isso vale mais que um teste que parece
   * cobrir e não cobre.
   *
   * O que ele prende de verdade: a origem não é reescrita. Hoje quem garante isso é a
   * comparação `el.scrollLeft !== x` (o alvo já está em `x`), não o flag — e essa é
   * justamente a propriedade que sobreviveria a alguém "simplificar" a condição.
   */
  it('a origem da rolagem não é reescrita', async () => {
    mockFetch(doisCartoesPovoados());
    const { container } = render(<ViewCadastroProdutos />);
    await abrirAgrupamentos(container);

    const wraps = [...document.querySelectorAll('.cc-dt-wrap')];
    comScrollLeftReal(wraps);
    let escritas = 0;
    const original = Object.getOwnPropertyDescriptor(wraps[0], 'scrollLeft');
    Object.defineProperty(wraps[0], 'scrollLeft', {
      get: original.get,
      set: (x) => { escritas += 1; original.set(x); },
      configurable: true,
    });

    wraps[0].scrollLeft = 90;   // a rolagem do usuário
    fireEvent.scroll(wraps[0]);

    // Só a escrita do próprio usuário. Propagar de volta para a origem realimentaria o
    // laço que o guarda `sincronizando` existe para cortar.
    expect(escritas).toBe(1);
  });
});
