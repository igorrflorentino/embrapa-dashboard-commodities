// dataStore.test.js — the pushdown query boundary the views load through.
// Covers the fetch → decorate → cache path, the per-convention cache key
// (currency/correction pick the deflated column server-side, so a change must
// re-fetch), and that an HTTP failure becomes status='error' with a message.

import { describe, expect, it, vi } from 'vitest';

function jsonRes(body, { ok = true, status = 200 } = {}) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) });
}

// Flush pending microtasks (the fetch → decorate → cache chain resolves over a
// few .then ticks); macro-task tick covers any setTimeout-deferred work.
const settle = () => new Promise((r) => setTimeout(r, 0));

// load() also fires a /api/source-meta fetch (live provenance) alongside the
// snapshot; these tests assert on the SNAPSHOT query cadence, so count only those.
const snapCalls = (f) => f.mock.calls.filter((c) => String(c[0]).includes('/snapshot')).length;
const metaCalls = (f) => f.mock.calls.filter((c) => String(c[0]).includes('/source-meta')).length;

// A contract-complete BancoSnapshot (the shape assertSnapshotShape requires).
function validSnap(over = {}) {
  return { products: [], productTS: {}, overviewTS: [], ufData: [], quality: [], ...over };
}

async function loadStore(fetchImpl) {
  globalThis.fetch = fetchImpl;
  vi.resetModules();
  window.UF_DATA = [{ uf: 'PA', col: 7, row: 2, region: 'Norte', name: 'Pará' }];
  window.QUALITY_FLAGS = [{ id: 'OK', label: 'Sem ressalvas', color: 'var(--ok)' }];
  window.REGIONS = [{ id: 'N' }];
  // Gold table name is sourced from the banco registry (the single static source);
  // tableOf() reads window.bancoById(id).table.
  window.bancoById = (id) => ({ id, table: id === 'ibge_pevs' ? 'gold_pevs_production' : null });
  await import('./dataStore.js');
  return window.dataStore;
}

describe('dataStore', () => {
  it('loads, decorates, and caches a snapshot', async () => {
    const snap = validSnap({ ufData: [{ uf: 'PA', value: 1 }], quality: [{ id: 'OK', count: 3 }] });
    const f = vi.fn(() => jsonRes(snap));
    const ds = await loadStore(f);

    expect(ds.status('ibge_pevs')).toBe('idle');
    const res = await ds.load('ibge_pevs');
    expect(res.status).toBe('ready');
    expect(ds.status('ibge_pevs')).toBe('ready');

    const data = ds.get('ibge_pevs');
    expect(data.table).toBe('gold_pevs_production'); // stamped from the banco registry (tableOf)
    expect(data.ufData[0]).toMatchObject({ col: 7, region: 'Norte', name: 'Pará' }); // decorated
    expect(data.quality[0]).toMatchObject({ label: 'Sem ressalvas', color: 'var(--ok)' });

    await ds.load('ibge_pevs'); // same banco + convention → served from cache
    expect(snapCalls(f)).toBe(1);
  });

  it('surfaces an HTTP error as status=error with a message', async () => {
    const f = vi.fn(() => jsonRes({}, { ok: false, status: 500 }));
    const ds = await loadStore(f);

    const res = await ds.load('ibge_pevs');
    expect(res.status).toBe('error');
    expect(ds.error('ibge_pevs')).toMatch(/500/);
    expect(ds.get('ibge_pevs')).toBe(null);
  });

  it('re-fetches under a different convention (currency drives the cache key)', async () => {
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);

    await ds.load('ibge_pevs'); // BRL|IPCA
    ds.setConventions({ currency: 'USD', correction: 'IPCA' });
    await ds.load('ibge_pevs'); // USD|IPCA → new key → fetch again

    expect(snapCalls(f)).toBe(2);
    const lastUrl = f.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.includes('/snapshot'))
      .pop();
    expect(lastUrl).toContain('currency=USD');
  });

  it('re-fetches under a different flow, which drives the cache key + the URL param', async () => {
    // Flow (export/import) is server-side: the trade snapshot is pre-aggregated over
    // it, so a direction is part of the cache key + request. 'all' omits the param
    // (the historical default), a real direction adds flow=<dir>.
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);

    await ds.load('ibge_pevs'); // flow 'all'
    ds.setFlow('export');
    await ds.load('ibge_pevs'); // export → new key → fetch again

    expect(snapCalls(f)).toBe(2);
    const urls = f.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/snapshot'));
    expect(urls[0]).not.toContain('flow='); // 'all' omits the param
    expect(urls[1]).toContain('flow=export');
  });

  it('re-fetches under a different origem, which drives the cache key + the URL param', async () => {
    // The gap this closes, found only by driving the real UI (2026-08-29): `origem`
    // reached the chip, the citation and the CSV, and 1031 unit tests were green — while
    // the SNAPSHOT REQUEST never carried it. So picking "Extração vegetal" relabelled the
    // panel and left every number exactly as it was, which is the wrong-subject defect
    // this whole axis exists to prevent, produced by the axis itself.
    //
    // Two things have to be true and neither is visible from the FilterMenu's side: the
    // half must be part of the CACHE KEY (or the store serves the previous half's rows
    // under the new chip) and it must be in the URL (or the BFF sums both).
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);

    await ds.load('ibge_pevs'); // origem 'all'
    ds.setOrigem('extrativa');
    await ds.load('ibge_pevs'); // extrativa → new key → fetch again

    expect(snapCalls(f)).toBe(2);
    const urls = f.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/snapshot'));
    expect(urls[0]).not.toContain('origem='); // 'all' omits it — both halves, the survey total
    expect(urls[1]).toContain('origem=extrativa');
  });

  it("setOrigem('all') when already all is a no-op (no extra fetch)", async () => {
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);
    await ds.load('ibge_pevs');
    expect(snapCalls(f)).toBe(1);
    ds.setOrigem('all');
    await settle();
    expect(snapCalls(f)).toBe(1);
  });

  it("setFlow('all') when already all is a no-op (no extra fetch)", async () => {
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);
    await ds.load('ibge_pevs');
    expect(snapCalls(f)).toBe(1);
    ds.setFlow('all'); // unchanged → no re-fetch
    await settle();
    expect(snapCalls(f)).toBe(1);
  });

  it('setConventions ALONE re-triggers the load for an already-loaded banco', async () => {
    // F1.1 regression: a deep-linked ?cur/?corr applied AFTER the first load must
    // not wedge the view on the skeleton. setConventions switches to a new cache
    // key that nothing has loaded; useBancoData only issues load() on [bancoId],
    // so the store must proactively re-run the fetch itself — without any explicit
    // load() call from the view — and the banco must be 'ready' under the new conv.
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);

    await ds.load('ibge_pevs'); // BRL|IPCA → 1 snapshot fetch
    expect(snapCalls(f)).toBe(1);

    ds.setConventions({ currency: 'USD', correction: 'Nominal' }); // must re-fetch
    // setConventions kicks load() synchronously; let the fetch chain settle.
    await settle();

    expect(snapCalls(f)).toBe(2); // re-fetched WITHOUT a view-issued load()
    expect(ds.status('ibge_pevs')).toBe('ready'); // resolved under USD|Nominal
    const lastUrl = f.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.includes('/snapshot'))
      .pop();
    expect(lastUrl).toContain('currency=USD');
    expect(lastUrl).toContain('correction=Nominal');
  });

  it('setConventions with an unchanged convention is a no-op (no re-fetch)', async () => {
    const f = vi.fn(() => jsonRes(validSnap()));
    const ds = await loadStore(f);
    await ds.load('ibge_pevs');
    ds.setConventions({ currency: 'BRL', correction: 'IPCA' }); // same as active
    await settle();
    expect(snapCalls(f)).toBe(1);
  });

  it('rejects a drifted snapshot shape as status=error (no silent empty view)', async () => {
    // products is fine but productTS arrived as an array (a contract drift) —
    // every producer would read it and render blank; instead, fail loudly.
    const f = vi.fn(() => jsonRes(validSnap({ productTS: [] })));
    const ds = await loadStore(f);

    const res = await ds.load('ibge_pevs');
    expect(res.status).toBe('error');
    expect(ds.error('ibge_pevs')).toMatch(/contrato.*productTS/i);
    expect(ds.get('ibge_pevs')).toBe(null);
  });

  it('rejects NESTED-row drift (a renamed field), not just top-level keys', async () => {
    // overviewTS is a non-empty array (top-level check passes) but its row is
    // missing the load-bearing `v` — exactly the silent drift a backend field
    // rename would cause. The row-shape check must catch it.
    const f = vi.fn(() => jsonRes(validSnap({ overviewTS: [{ y: 2020, value: 1 }] })));
    const ds = await loadStore(f);

    const res = await ds.load('ibge_pevs');
    expect(res.status).toBe('error');
    expect(ds.error('ibge_pevs')).toMatch(/linhas fora do contrato.*overviewTS/i);
  });

  it('rejects a non-object snapshot payload (e.g. null / an error string)', async () => {
    const f = vi.fn(() => jsonRes(null));
    const ds = await loadStore(f);

    const res = await ds.load('ibge_pevs');
    expect(res.status).toBe('error');
    expect(ds.error('ibge_pevs')).toMatch(/inesperada/i);
  });

  it('loadMeta fetches /source-meta once and overlays it onto meta() (deduped)', async () => {
    // The freshness/about info-pages reach loadMeta directly (no snapshot load),
    // so it must fetch provenance on its own and never double-fetch a resolved one.
    const sm = {
      table: 'gold_pevs_production',
      yearStart: 1986,
      yearEnd: 2024,
      totalRows: 94771,
      lastRefreshLabel: '11 jun 2026 · 05:02 BRT',
    };
    const f = vi.fn((url) => jsonRes(String(url).includes('/source-meta') ? sm : validSnap()));
    const ds = await loadStore(f);
    window.bancoById = () => ({ prov: { refresh: 'fallback' } }); // registry fallback

    await ds.loadMeta('ibge_pevs');
    expect(metaCalls(f)).toBe(1);
    const m = ds.meta('ibge_pevs');
    expect(m.refresh).toBe('11 jun 2026 · 05:02 BRT'); // overlaid, not the fallback
    expect(m.coverage).toMatchObject({ yearEnd: 2024, totalRows: 94771 });

    await ds.loadMeta('ibge_pevs'); // already resolved → no second fetch
    expect(metaCalls(f)).toBe(1);
  });

  it('dedupes concurrent /source-meta fetches to a single request (FINDING #8)', async () => {
    // load() kicks fetchSourceMeta AND a view (ViewHealth/ViewAbout) can call
    // loadMeta() before it resolves; React StrictMode double-invokes effects too.
    // fetchSourceMeta only populates sourceMeta[id] AFTER the request lands, so
    // without an in-flight guard each caller would fire a DUPLICATE request. The
    // in-flight promise must collapse all concurrent callers to ONE network call.
    const sm = { table: 'gold_pevs_production', yearStart: 1986, yearEnd: 2024 };
    const f = vi.fn((url) => jsonRes(String(url).includes('/source-meta') ? sm : validSnap()));
    const ds = await loadStore(f);

    // Fire load() and loadMeta() in the SAME tick (both kick source-meta).
    const p1 = ds.load('ibge_pevs');
    const p2 = ds.loadMeta('ibge_pevs');
    await Promise.all([p1, p2]);
    await settle();

    expect(metaCalls(f)).toBe(1); // a single /source-meta request, not two
  });

  it('surfaces the latest-year completeness signal on meta() (FINDING #3)', async () => {
    // The serialized /source-meta now carries monthsInLatestYear / latestYearComplete
    // / latestCompleteYear so the Overview can anchor its YoY on the last COMPLETE
    // year for a partial-latest-year banco (COMEX). meta().latest exposes them.
    const sm = {
      table: 'gold_comex_flows',
      yearStart: 1997,
      yearEnd: 2026,
      monthsInLatestYear: 5,
      latestYearComplete: false,
      latestCompleteYear: 2025,
    };
    const f = vi.fn((url) => jsonRes(String(url).includes('/source-meta') ? sm : validSnap()));
    const ds = await loadStore(f);

    await ds.loadMeta('mdic_comex');
    const m = ds.meta('mdic_comex');
    expect(m.latest).toMatchObject({
      monthsInLatestYear: 5,
      yearComplete: false,
      completeYear: 2025,
    });
  });

  it('ignores a stale in-flight snapshot so it cannot overwrite a newer reload (M8)', async () => {
    // A same-key reload starts a NEWER fetch while the OLD one is still in flight.
    // The OLD response resolves LAST; without a generation token it would clobber
    // the newer one. We control resolution order with deferred promises.
    let resolveOld;
    const oldSnap = new Promise((res) => { resolveOld = res; });
    const newSnap = jsonRes(validSnap({ quality: [{ id: 'OK', count: 99 }] }));
    const f = vi
      .fn((url) => {
        if (String(url).includes('/source-meta')) return jsonRes({});
        // First snapshot call (gen 1) is deferred; the second (gen 2) resolves now.
        return f.__snap++ === 0 ? oldSnap : newSnap;
      });
    f.__snap = 0;
    const ds = await loadStore(f);

    const p1 = ds.load('ibge_pevs'); // gen 1 — pending (deferred)
    const p2 = ds.reload('ibge_pevs'); // deletes the entry + starts gen 2 (resolves now)
    await p2;
    await settle();
    expect(ds.status('ibge_pevs')).toBe('ready');
    expect(ds.get('ibge_pevs').quality[0].count).toBe(99); // gen 2 payload

    // The stale gen-1 fetch finally resolves — it must be dropped.
    resolveOld({ ok: true, status: 200, json: () => Promise.resolve(validSnap({ quality: [{ id: 'OK', count: 1 }] })) });
    await p1;
    await settle();
    expect(ds.get('ibge_pevs').quality[0].count).toBe(99); // still gen 2, not the stale 1
    expect(ds.status('ibge_pevs')).toBe('ready');
  });

  it('treats an absent completeness signal as complete (annual bancos)', async () => {
    // An annual banco (PEVS/PAM/COMTRADE) — or an older backend — omits the
    // completeness fields. meta().latest must default to yearComplete:true so the
    // Overview YoY is NEVER spuriously suppressed on an always-complete annual year.
    const sm = { table: 'gold_pevs_production', yearStart: 1986, yearEnd: 2024 };
    const f = vi.fn((url) => jsonRes(String(url).includes('/source-meta') ? sm : validSnap()));
    const ds = await loadStore(f);

    await ds.loadMeta('ibge_pevs');
    const m = ds.meta('ibge_pevs');
    expect(m.latest.yearComplete).toBe(true);
    expect(m.latest.completeYear).toBe(null);
  });
});
