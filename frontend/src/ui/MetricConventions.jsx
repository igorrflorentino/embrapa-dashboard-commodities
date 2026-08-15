// MetricConventions — display-time metric configuration strip.
// Sits BELOW the active-filter chips, ABOVE the dashboard views.
//
// Filters reduce *which rows* enter the visualization.
// Conventions decide *how those rows are displayed*: which currency,
// whether values are nominal or inflation-adjusted, and which units
// are used for mass / volume readouts.
//
// Controlled component:
//   <MetricConventions value={...} onChange={fn(next)} expanded={bool} onToggleExpanded={fn} />
// where value is:
//   { currency: 'BRL'|'USD'|'EUR',
//     correction: 'Nominal'|'IPCA'|'IGP-M'|'IGP-DI',
//     units: { mass: 't', volume: 'm³', … }  // display unit per family }
//
// `expanded`/`onToggleExpanded` are lifted to the root (main.jsx), NOT local useState —
// unlike a typical collapsible, every onChange here re-triggers a snapshot load
// (contract map §0.2), and DataGate swaps ALL of its children (this component included)
// for a loading placeholder while that fetch is in flight. Local state would be wiped by
// that unmount on every single toggle, slamming the panel shut after each click. Lifting
// it above DataGate (same reasoning as filterOpen) survives the remount.

import { magnitudeParts } from '../charts/magnitude.js';

function MetricConventions({ value, onChange, families, banco, expanded, onToggleExpanded }) {
  const set = (patch) => onChange({ ...value, ...patch });

  // Currency + monetary-correction only apply to a banco that carries a monetary
  // value (window.isMonetaryBanco — derived from its metrics/baseCurrency). All
  // current bancos are monetary, so this is forward-looking: a future physical-only
  // source (e.g. a pure energy-volume series) would show the unit groups only,
  // never an inapplicable moeda/correção the user can't meaningfully change.
  const monetary = window.isMonetaryBanco ? window.isMonetaryBanco(banco) : true;

  // Physical-unit groups are REGISTRY-DRIVEN: one group per family present
  // in the data (familiesInBasket). Mass/volume keep their dedicated conv
  // fields for back-compat; any other family stores its unit in value.units.
  const physFams = ((families && families.length ? families : ['mass', 'volume']))
    .filter(f => window.UNIT_FAMILIES[f]);
  const unitFor = (fid) => (value.units && value.units[fid]) || window.defaultUnitOf(fid);
  const setUnitFor = (fid, id) => set({ units: { ...(value.units || {}), [fid]: id } });

  const Group = ({ label, options, active, onPick, mono }) => (
    <div className="mc-group">
      <span className="mc-label">{label}</span>
      {/* A 4-option group lays out as a balanced 2×2 grid (e.g. Massa kg/t/@/sc) instead of
          wrapping 3+1 with a lopsided lone item; ≤3 options stay on one row. */}
      <div className={'seg' + (options.length === 4 ? ' seg-2x2' : '')}>
        {options.map(o => (
          <button key={o.id}
                  type="button"
                  disabled={o.disabled}
                  title={o.disabled ? o.disabledReason : undefined}
                  className={'seg-opt ' + (active === o.id ? 'on' : '') + (o.disabled ? ' disabled' : '')}
                  onClick={() => !o.disabled && onPick(o.id)}>
            <span className={mono ? 'tnum' : ''}>{o.id}</span>
            {o.sub && <small>{o.sub}</small>}
          </button>
        ))}
      </div>
    </div>
  );

  // The Gold/serving marts carry the full currency × correction matrix EXCEPT the
  // IGP-M/IGP-DI × USD combos (no val_real_{igpm,igpdi}_usd is reachable through the
  // serving allowlist — only BRL and EUR). Disable exactly those so the strip can
  // never request a US$ figure the BFF would silently serve as a real R$ value under
  // a US$ symbol (wrong-symbol display). EUR keeps both — its deflated columns exist.
  const isUnservedCombo = (currency, corr) =>
    currency === 'USD' && (corr === 'IGP-M' || corr === 'IGP-DI');
  const UNSERVED_REASON =
    'Indisponível para US$ — não há coluna deflacionada por este índice em dólar (use R$/€ ou IPCA).';
  // Picking a currency must not leave an unservable correction active: switching to
  // US$ while IGP-M/IGP-DI is selected snaps the correction back to IPCA in the SAME
  // update, so the request never carries the wrong-symbol combo (no render-time set).
  // Reuses window.clampConvention so the strip and the deep-link decoder share one rule.
  const setCurrency = (id) => onChange(window.clampConvention({ ...value, currency: id }));

  // Collapsed-state summary chips — read-only, mirror FilterTriggerBar's
  // .fm-chip-filter/.fm-chip-k pattern so the compact row reads consistently with the
  // filter chips above it. Every current convention gets a chip (unlike filter chips,
  // which are capability-gated per banco) since there's no "default/inactive" state to
  // omit here — moeda/correção/unit/escala always have a value.
  const chips = [
    monetary && { k: 'Moeda', v: (window.CURRENCY_FX[value.currency] || {}).symbol || value.currency },
    monetary && { k: 'Correção', v: value.correction === 'Nominal' ? 'Sem correção' : value.correction },
    ...physFams.map((fid) => ({ k: window.UNIT_FAMILIES[fid].label, v: unitFor(fid) })),
    { k: 'Escala', v: value.autoScale ? 'Automática' : 'Fixa' },
  ].filter(Boolean);

  return (
    <div className="mc-bar">
      {!expanded ? (
        <div className="mc-head mc-head-compact">
          <span className="mc-overline">Convenções métricas</span>
          {chips.map((c, i) => (
            <span key={i} className="fm-chip-filter">
              <span className="fm-chip-k">{c.k}</span>{c.v}
            </span>
          ))}
          <span className="fm-spacer"></span>
          <button type="button" className="fm-edit-btn" aria-expanded="false" onClick={onToggleExpanded}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 20h4l10-10-4-4L4 16zM14 6l4 4"/>
            </svg>
            Editar métricas
          </button>
        </div>
      ) : (
        <>
          <div className="mc-head">
            <span className="mc-overline">Convenções métricas</span>
            <span className="mc-caption">
              Como os valores e quantidades são exibidos — não altera quais linhas entram na visualização.
            </span>
            <label className="mc-check" title="Reescala automaticamente entre mil/mi/bi para evitar números longos">
              <input type="checkbox"
                     checked={!!value.autoScale}
                     onChange={(e) => set({ autoScale: e.target.checked })} />
              <span>Auto-escala (mil/mi/bi)</span>
            </label>
            <span className="fm-spacer"></span>
            <button type="button" className="fm-edit-btn" aria-expanded="true" onClick={onToggleExpanded}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="18 15 12 9 6 15"/>
              </svg>
              Recolher
            </button>
          </div>

          <div className="mc-groups">
            {monetary && (
              <Group
                label="Moeda"
                mono
                options={[
                  // BRL/USD/EUR are real Gold columns (BCB PTAX series).
                  { id: 'BRL', sub: 'R$'  },
                  { id: 'USD', sub: 'US$' },
                  { id: 'EUR', sub: '€'   },
                ]}
                active={value.currency}
                onPick={setCurrency}
              />
            )}

            {monetary && (
              <Group
                label="Correção monetária"
                options={[
                  { id: 'Nominal', sub: 'sem corr.' },
                  { id: 'IPCA',    sub: 'IBGE' },
                  { id: 'IGP-M',   sub: 'FGV', disabled: isUnservedCombo(value.currency, 'IGP-M'), disabledReason: UNSERVED_REASON },
                  { id: 'IGP-DI',  sub: 'FGV', disabled: isUnservedCombo(value.currency, 'IGP-DI'), disabledReason: UNSERVED_REASON },
                ]}
                active={value.correction}
                onPick={(id) => set({ correction: id })}
              />
            )}

            {physFams.map(fid => {
              const fam = window.UNIT_FAMILIES[fid];
              return (
                <Group key={fid}
                  label={fam.label}
                  mono
                  options={(fam.units || []).map(u => ({ id: u.id, sub: u.long }))}
                  active={unitFor(fid)}
                  onPick={(id) => setUnitFor(fid, id)}
                />
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// Helpers — exported on window for use by views ----------------------

window.DEFAULT_CONVENTIONS = {
  currency:   'BRL',
  correction: 'IPCA',
  units:      { mass: 't', volume: 'm³' },
  autoScale:  false,
};

// The single source of truth for the unservable currency × correction combos:
// IGP-M / IGP-DI deflation has no US$ column in the serving marts (only BRL/EUR), so
// requesting it would surface a real R$ figure under a US$ symbol. The strip disables
// these, and the deep-link decoder (main.jsx) clamps them — a bookmarked
// ?cur=USD&corr=IGP-M must not slip past the UI gate. Returns a SERVABLE convention.
window.clampConvention = (conv) => {
  if (conv && conv.currency === 'USD' && (conv.correction === 'IGP-M' || conv.correction === 'IGP-DI')) {
    return { ...conv, correction: 'IPCA' };
  }
  return conv;
};
// Display unit chosen for a family (falls back to the registry default).
window.unitOf = (conv, fam) => (conv && conv.units && conv.units[fam]) || window.defaultUnitOf(fam);

// Auto-scale helper — picks a (factor, suffix) so the number sits in a readable
// magnitude. Used only when conv.autoScale === true. The bi/mi/mil ladder is the SHARED
// kernel (magnitude.js), identical to the chart axis's ptBrMagnitude so the two can't
// drift (DEDUP-7).
window.autoScaleNum = magnitudeParts;

function _fmtRescaled(v, conv, unitSuffix) {
  if (conv.autoScale) {
    const { factor, suffix } = window.autoScaleNum(v);
    const scaled = v / factor;
    const txt = scaled.toLocaleString('pt-BR', {
      maximumFractionDigits: scaled < 10 ? 2 : scaled < 100 ? 1 : 0,
    });
    return suffix
      ? `${txt} ${suffix} ${unitSuffix}`.trim()
      : `${txt} ${unitSuffix}`.trim();
  }
  return v.toLocaleString('pt-BR', { maximumFractionDigits: 0 }) + ' ' + unitSuffix;
}

// Currency display SYMBOLS (R$ / US$ / €). This is a label table ONLY — there is
// deliberately NO numeric FX rate here. Every live banco (PEVS/PAM production AND
// COMEX/Comtrade trade) now serves its snapshot value IN the requested currency
// SERVER-side, at the REAL year-FX / deflated Gold columns (val_*_brl / val_*_usd /
// val_*_eur, real BCB PTAX). So no client-side conversion of real data exists — the
// old frozen mock rates (USD 0.205 / EUR 0.187) used to cross-convert a USD-native
// trade banco were a wrong-number path on explicit BRL/EUR selection and are gone.
window.CURRENCY_FX = {
  BRL: { symbol: 'R$', long: 'Real'  },
  USD: { symbol: 'US$', long: 'Dólar' },
  EUR: { symbol: '€',   long: 'Euro'  },
};

// Multiplicative display factor for a server-backed *value*. ALWAYS 1: currency ×
// correction now select the REAL deflated value column SERVER-side
// (val_real_{ipca,igpm,igpdi}_{brl,usd,eur}, val_yearfx_{brl,usd,eur} for Nominal —
// the scientific core, real BCB PTAX), so the snapshot value already ARRIVES in the
// requested currency for EVERY live banco (production AND trade). There is no client
// multiplier left; this helper exists so the manual value-scaling sites (views
// building chart series by hand) read a single factor that agrees with applyConv /
// formatValue. (Edge: USD + IGP-M/IGP-DI has no _usd column → the BFF falls back to
// the real BRL column and the value_label flags "moeda indisponível → R$"; the
// figure is still real, never a mock conversion.)
window.convFactor = (_conv) => 1;

// Base-aware value multiplier — kept for the views that call it (ViewGeography /
// ViewOverview UF map) so their call sites need no change. It is now ALWAYS 1: a
// trade banco's snapshot (ufData/overview) no longer arrives in a fixed US$ that the
// client must cross-convert — the BFF serves it IN the requested display currency
// (the real BRL/USD/EUR Gold column). Cross-converting again via a frozen mock rate
// was the wrong-number bug on explicit BRL/EUR selection; that path is removed. The
// `base` arg is ignored on purpose — server-native values need no base→display rate.
window.convFactorFor = (_base, conv) => window.convFactor(conv);

// Convert a BRL-canonical value through the active currency + correction.
window.applyConv = (val, conv) => {
  if (val == null) return null;
  return val * window.convFactor(conv);
};

// Format a BRL-canonical value through the active convention.
// Auto-scale (mil/mi/bi) only when conv.autoScale === true.
window.formatValue = (brl, conv) => {
  if (brl == null) return '—';
  const sym = window.CURRENCY_FX[conv.currency].symbol;
  const v = window.applyConv(brl, conv);
  if (conv.autoScale) {
    const { factor, suffix } = window.autoScaleNum(v);
    const scaled = v / factor;
    const txt = scaled.toLocaleString('pt-BR', {
      maximumFractionDigits: scaled < 10 ? 2 : scaled < 100 ? 1 : 0,
    });
    return suffix ? `${sym} ${txt} ${suffix}` : `${sym} ${txt}`;
  }
  return sym + ' ' + v.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
};

// Axis label — when auto-scale is ON, append the picked suffix for the
// passed reference magnitude; otherwise just the currency symbol.
window.valueAxisLabel = (conv, refMagnitude) => {
  const sym = window.CURRENCY_FX[conv.currency].symbol;
  if (conv.autoScale && refMagnitude != null) {
    const { suffix } = window.autoScaleNum(refMagnitude);
    return suffix ? `${sym} ${suffix}` : sym;
  }
  return sym;
};

// Convert a series {y, v: value in banco base currency} to displayed currency.
window.convertSeries = (series, conv, key = 'v') => {
  const factor = window.convFactor(conv);
  return series.map(d => ({ ...d, [key]: d[key] * factor }));
};

// Mass / volume: native data is in t (mass) and m³ (volume) at internal scale.
// OVERVIEW_TS.q_mass holds *thousands of tonnes*; PRODUCT_TS.q (mass) same.
// OVERVIEW_TS.q_vol holds *millions of m³*; PRODUCT_TS.q (volume) same.
//
// Display rule (per user request): never auto-rescale to abbreviated units.
// The user picks t or kg → we render in t or kg. Same for m³ vs L.

window.formatMassQty = (milT, conv) => {
  if (milT == null) return '—';
  const v = milT * window.massQtyMul(conv);
  return _fmtRescaled(v, conv, window.unitOf(conv, 'mass'));
};
window.formatVolumeQty = (miM3, conv) => {
  if (miM3 == null) return '—';
  const v = miM3 * window.volumeQtyMul(conv);
  return _fmtRescaled(v, conv, window.unitOf(conv, 'volume'));
};
// Contagem (head / eggs — PPM livestock): internal q_count holds *millions of units*
// (mi un), the same ÷1e6 scaling the serializer applies. Mirrors mass/volume so the
// herd reads in the user-picked count unit (un / dz / milheiro / cabeça).
window.formatCountQty = (miUn, conv) => {
  if (miUn == null) return '—';
  const v = miUn * window.countQtyMul(conv);
  return _fmtRescaled(v, conv, window.unitOf(conv, 'count'));
};

// Multipliers: internal dataset units (mil t / mi m³) → selected display
// unit, via the registry factors so any member unit (kg/t/@/sc, L/m³/hL…)
// converts correctly. internal mass = mil t (×1000 t); internal vol = mi m³.
window.massQtyMul    = (conv) => 1000 / window.unitToBase('mass', window.unitOf(conv, 'mass'));
window.volumeQtyMul  = (conv) => 1e6  / window.unitToBase('volume', window.unitOf(conv, 'volume'));
// internal count = mi un (×1e6 un); convert to the picked count unit via the registry.
window.countQtyMul   = (conv) => 1e6  / window.unitToBase('count', window.unitOf(conv, 'count'));
window.massAxisLabel   = (conv) => window.unitOf(conv, 'mass');
window.volumeAxisLabel = (conv) => window.unitOf(conv, 'volume');
window.countAxisLabel  = (conv) => window.unitOf(conv, 'count');

// Human label for the active monetary convention (e.g. "USD · IPCA").
window.conventionMonetaryLabel = (conv) =>
  conv.currency + (conv.correction === 'Nominal' ? ' · nominal' : ' · ' + conv.correction);

// scaleLabel — axis/series label grammar for a magnitude-scaled unit: a currency symbol
// sits BEFORE the magnitude suffix ("R$ bi"), a physical unit AFTER ("bi t"). Single
// source for the symbol list + ordering so the three scalers (scaleSeries, ValueVolume
// _scaleStack, Geography heatScaled) can't drift when a symbol changes — the CNY removal
// showed the list does churn (DEDUP-9). Pure string / label-only — never touches a value.
window.SCALE_CURRENCY_SYMS = ['R$', 'US$', '€'];
window.scaleLabel = (unit, suffix) =>
  window.SCALE_CURRENCY_SYMS.includes(unit) ? `${unit} ${suffix}` : `${suffix} ${unit}`.trim();

// scaleSeries — rescales a series + returns the matching axis label.
// When conv.autoScale is OFF, returns the data as-is and unitSuffix only.
// When ON, divides every value by autoScale(refMagnitude).factor and
// builds the label respecting unit grammar (see scaleLabel).
window.scaleSeries = (series, refMag, conv, valueKey, unitSuffix) => {
  if (!conv.autoScale) {
    return { data: series, label: unitSuffix };
  }
  const { factor, suffix } = window.autoScaleNum(refMag);
  if (!suffix) return { data: series, label: unitSuffix };
  const data = series.map(d => ({ ...d, [valueKey]: d[valueKey] / factor }));
  return { data, label: window.scaleLabel(unitSuffix, suffix) };
};

window.MetricConventions = MetricConventions;
