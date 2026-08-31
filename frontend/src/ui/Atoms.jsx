// SectionHeader + small shared components

function SectionHeader({ overline, title, action }) {
  return (
    <div className="section-head">
      <div>
        <div className="overline">{overline}</div>
        <h3 className="section-title">{title}</h3>
      </div>
      {action && <div className="section-action">{action}</div>}
    </div>
  );
}

// NotApplicableNote — an inline, honest "este filtro não se aplica" notice that a
// view renders ABOVE its (still-real) charts when the active filter summary carries
// a dimension this view's grain cannot honour. The data producers surface that as
// a `notApplicable` object keyed by dimension (e.g. { states: '…', basket: '…' }):
// the param is withheld at the data layer (no silent drop), and this atom makes the
// refusal visible to the researcher instead of leaving an unchanged chart unexplained.
// Renders nothing when there is no applicable note (the common case), so a view can
// place it unconditionally above its charts.
function NotApplicableNote({ note }) {
  const messages = note ? Object.values(note).filter(Boolean) : [];
  if (!messages.length) return null;
  return (
    <div className="card subtle na-note">
      {messages.map((msg, i) => (
        <p key={i} className="cs-note" style={{ margin: 0 }}>
          <window.Icon name="info" size={14} />
          <span>{msg}</span>
        </p>
      ))}
    </div>
  );
}

// UfScopePicker — a compact single-UF selector for the cross-banco views (which
// have no global filter bar). value = UF acronym or '' (Brasil/national). The view
// converts it to a `states` array for the producers. Single-UF keeps the cross
// comparison unambiguous (a researcher looks at one state at a time).
function UfScopePicker({ value, onChange, label = 'Recorte por UF' }) {
  const ufs = (window.UF_DATA || []).slice().sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
  return (
    <label className="uf-scope">
      <span className="caption">{label}</span>
      {/* `.scope-select`, não `.seg-opt`: aquela é `border: none; background: transparent`
          porque foi feita para viver DENTRO da caixa do `.seg`, que fornece a borda. Solta,
          o controle media 24px sem borda nem fundo — lia como legenda, não como campo. Este
          átomo é renderizado em CINCO pontos (ViewCrossSource, ViewsMultiSource ×3,
          ViewCuratedAnalyses), então o defeito aparecia nos cinco. */}
      <select
        className="scope-select"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Brasil (todas as UFs)</option>
        {ufs.map((u) => (
          <option key={u.uf} value={u.uf}>{u.uf} · {u.name}</option>
        ))}
      </select>
    </label>
  );
}

// EmptyCard — the canonical full-card "no data here" early-return state: a subtle card
// wrapping a centered caption. Was hand-written identically across several views'
// empty states (DEDUP-10). `children` is the pt-BR message.
function EmptyCard({ children }) {
  return (
    <div className="card subtle">
      <p className="caption" style={{ padding: '20px 4px', textAlign: 'center' }}>
        {children}
      </p>
    </div>
  );
}

// LoadErrorNote — an inline, HONEST "não foi possível carregar" notice a view renders
// ABOVE its charts when a data FETCH FAILED (distinct from "genuinely no data"). The
// resource-backed producers surface a failed /api read as `loadError` on their shell
// (data/producers.js + resource.errorOf), so a network/BigQuery error is NOT silently
// rendered as an empty "0 / Sem dados" state — the project's no-invisible-filtering /
// in-product-honesty rule. role="alert" announces it; renders nothing when there is no
// error, so a view can place it unconditionally above its charts.
function LoadErrorNote({ error }) {
  if (!error) return null;
  return (
    <div className="card subtle na-note" role="alert"
         style={{ borderLeft: '4px solid var(--err, #b71c1c)' }}>
      <p className="cs-note" style={{ margin: 0 }}>
        <window.Icon name="warning" size={14} />
        <span>Não foi possível carregar estes dados (falha de rede ou do servidor). Os
          valores exibidos podem estar incompletos — recarregue a página para tentar de novo.</span>
      </p>
    </div>
  );
}

Object.assign(window, { SectionHeader, NotApplicableNote, UfScopePicker, EmptyCard, LoadErrorNote });
