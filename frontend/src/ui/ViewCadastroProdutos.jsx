// ViewCadastroProdutos — the Curadoria (catalog) editor: what ENTERS and EXITS the
// dashboard. Each commodity is registered by its EXACT source code (código+banco; no
// prefixes), points at one AGRUPAMENTO (first-class registry — create/rename/delete +
// inline move) and carries a Ciclo de Vida of TWO INDEPENDENT AXES: Ingestão
// (ativa|pausada — keep fetching?) and Exibição (visivel|oculto — researcher sees it?).
// A read-only Status column derives the resulting state (Ativo / Oculto / Pausado /
// Pendente de ingestão) so the lifecycle is legible without decoding two dropdowns.
// The add form autocompletes the code from the source's product list and flags whether it already exists in Gold, but a code
// that is not (yet) listed is ACCEPTED as *pendente de ingestão* (the catalog now drives
// ingestion), not rejected. The catalog table also shows each commodity's current STATE
// in the dashboard (linhas na Gold, período coberto, se tem dados). Writes go through
// /api/catalog/* (append-only, IAP-attributed; removal is a non-destructive tombstone).
//
// Authorization is enforced server-side (403); a 400 = bad key / invalid banco or axis /
// missing PPM tag / duplicate or non-empty group. We surface both honestly rather than hiding the failure.

const { useState: useCcState, useEffect: useCcEffect, useMemo: useCcMemo, useRef: useCcRef } = React;

// Ciclo de vida = TWO INDEPENDENT AXES. The stored values are stable machine CODES; these
// pt-BR labels exist only here, in the UI — the retired design stored the display sentence
// itself, so a reword meant a data migration plus a coordinated change in dbt and Python.
const _CC_INGESTAO = [
  { v: 'ativa', label: 'Ativa', hint: 'Buscar dados novos a cada atualização' },
  { v: 'pausada', label: 'Pausada', hint: 'Parar de buscar dados novos; mantém o que já está no Gold' },
];
const _CC_VISIBILIDADE = [
  { v: 'visivel', label: 'Visível', hint: 'Aparece nos gráficos e filtros' },
  { v: 'oculto', label: 'Oculto', hint: 'Some de TODOS os gráficos e filtros' },
];
// Hiding pulls a produto from EVERY researcher-facing chart/filter, so setting it is
// confirmed. Pausing is NOT confirmed: it is reversible and destroys nothing.
const _CC_OCULTO = 'oculto';
// A fresh idempotency key (change_id). The backend dedupes a retried POST carrying the SAME
// change_id (a network timeout that actually landed, or a fast re-submit), so a write is
// never double-applied. Kept STABLE per logical operation until it commits, then rotated.
const _ccUuid = () =>
  (window.crypto && window.crypto.randomUUID)
    ? window.crypto.randomUUID()
    : 'cid-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
// Catalog `banco` is the cross-source SOURCE TOKEN; show the friendly banco name.
const _CC_BANCOS = [
  { v: 'pevs', label: 'IBGE PEVS' },
  { v: 'pam', label: 'IBGE PAM' },
  { v: 'ppm', label: 'IBGE PPM' },
  { v: 'comex', label: 'MDIC COMEX' },
  { v: 'comtrade', label: 'UN COMTRADE' },
];
const _CC_BANCO_LABEL = Object.fromEntries(_CC_BANCOS.map((b) => [b.v, b.label]));
// Dois bancos guardam DUAS tabelas SIDRA sob um mesmo token, e a entrada marca qual —
// é por essa marca que a ingestão dirigida pelo catálogo roteia. Vazio/NA nos demais.
// A marca é OBRIGATÓRIA nos dois desde que a identidade de um produto passou a ser
// (banco, tabela, código): sem ela a entrada não cai em nenhuma das duas metades, cai numa
// TERCEIRA identidade que não corresponde a dado nenhum. Era opcional no PEVS enquanto a
// chave a ignorava.
const _CC_SIDRA_TABELAS = {
  ppm: {
    campo: 'Tabela PPM', obrigatorio: true, vazio: 'Escolha rebanho ou produção…',
    opcoes: [{ v: '3939', label: 'Rebanho (efetivo)' }, { v: '74', label: 'Produção animal' }],
  },
  pevs: {
    campo: 'Metade do PEVS', obrigatorio: true, vazio: 'Escolha extração ou silvicultura…',
    opcoes: [{ v: '289', label: 'Extração vegetal' }, { v: '291', label: 'Silvicultura' }],
  },
};
const _CC_SIDRA_LABEL = Object.fromEntries(
  Object.entries(_CC_SIDRA_TABELAS).map(([banco, cfg]) => [
    banco, Object.fromEntries(cfg.opcoes.map((t) => [t.v, t.label])),
  ]),
);
// Busca do cadastro. Sem dobrar acento, "acai" não acha "Açaí" e "castanha do para" não acha
// "castanha-do-pará" — e é exatamente assim que o pesquisador digita quando só quer saber se o
// produto JÁ está cadastrado. Hífen e pontuação viram espaço pelo mesmo motivo.
function _ccNorm(txt) {
  return String(txt ?? '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}
// Todos os termos têm de aparecer (E, não OU): "arroz 1006" acha o arroz de código 1006xxxx,
// que é a pergunta real. Cada termo pode cair em qualquer campo.
function _ccCombina(termos, campos) {
  const alvo = campos.map(_ccNorm).join(' | ');
  return termos.every((t) => alvo.includes(t));
}

const _CC_EMPTY_DRAFT = {
  codigo_produto: '', banco: 'comex', agrupamento_id: '',
  descricao_produto: '', ingestao: 'ativa', visibilidade: 'visivel', sidra_tabela: '',
};
// Reference legend content (pt-BR — the researcher reads it). Kept as DATA next to the
// vocabulary it documents, so a new column/action is added in one place and the counts in the
// summary stay honest automatically. Order matches the table, left to right.
const _CC_HELP_COLUNAS = [
  { k: 'Banco', d: 'A fonte oficial do dado (IBGE PEVS/PAM/PPM, MDIC COMEX, UN Comtrade).' },
  { k: 'Tabela', d: 'O código da tabela SIDRA dentro do banco (passe o mouse para ver o nome). Só o PEVS (extração vegetal · silvicultura) e o PPM (rebanho · produção animal) reúnem duas tabelas sob um mesmo banco; nos demais aparece um travessão. Junto com o banco e o código, ela forma a identidade do produto — o mesmo código pode estar cadastrado nas duas tabelas e são produtos diferentes.' },
  { k: 'Código', d: 'O código real da fonte (NCM, HS, código SIDRA). É ele, junto com o banco e a tabela, que identifica o produto no cadastro — não o nome.' },
  { k: 'Descrição (fonte)', d: 'O nome que a própria fonte dá a esse código; é somente leitura. Logo abaixo fica a sua anotação (✎), um texto livre seu que não altera nenhum dado.' },
  { k: 'Linhas', d: 'Quantas linhas esse produto tem hoje na camada Gold. Zero significa que ainda não foi ingerido.' },
  { k: 'Período', d: 'O intervalo de anos que os dados já ingeridos cobrem.' },
  { k: 'Status', d: 'O estado do produto, derivado das duas colunas seguintes e da presença de dados: Ativo, Oculto, Pausado ou Pendente de ingestão. É um resumo, não um controle — para mudá-lo, use Ingestão ou Exibição.' },
  { k: 'Agrupamento', d: 'O conceito que unifica o mesmo produto entre fontes diferentes (ex.: "Soja" reunindo os códigos do COMEX e do Comtrade). É o que permite comparar fontes no mesmo gráfico.' },
  { k: 'Ingestão', d: 'Se o pipeline continua buscando dados novos desse produto a cada atualização.' },
  { k: 'Exibição', d: 'Se o pesquisador vê esse produto nos gráficos e filtros do dashboard.' },
  { k: 'Ações', d: 'Remover o produto do cadastro.' },
];

const _CC_HELP_ACOES = [
  { k: 'Editar a anotação (✎)', tag: 'reversível', tone: 'ok',
    d: 'Texto livre seu, para registrar o que quiser sobre o produto. Não altera nenhum número nem a descrição oficial da fonte.' },
  { k: 'Trocar o Agrupamento', tag: 'reversível', tone: 'ok',
    d: 'Move o produto para outro conceito. Muda como ele é somado nas visões que cruzam fontes — o dado em si continua o mesmo.' },
  { k: 'Ingestão → Pausada', tag: 'reversível', tone: 'ok',
    d: 'Para de buscar dados novos, mas mantém no Gold tudo que já foi baixado — e o produto continua aparecendo no dashboard. Use para congelar uma série sem perder o histórico.' },
  { k: 'Exibição → Oculto', tag: 'pede confirmação', tone: 'warn',
    d: 'Tira o produto de TODOS os gráficos e filtros para os pesquisadores. Os dados continuam no Gold e a ingestão segue normalmente; é só uma decisão de exibição.' },
  { k: 'Remover (🗑)', tag: 'pede confirmação', tone: 'warn',
    d: 'Marca o produto como descontinuado e o tira do cadastro. Os dados já baixados NÃO são apagados: ficam órfãos no Gold e aparecem na seção "Descontinuados". Só um operador os apaga, com backup antes.' },
  { k: 'Aplicar a todos', tag: 'em lote', tone: 'warn',
    d: 'Aplica Ingestão ou Exibição a todos os produtos do agrupamento de uma vez. Ocultar em lote também pede confirmação.' },
  { k: 'Criar / renomear / excluir agrupamento', tag: null, tone: null,
    d: 'Renomear mantém os produtos; só o rótulo muda. Excluir exige que o agrupamento esteja vazio — reatribua ou remova os produtos antes.' },
  { k: 'Adicionar produto', tag: null, tone: null,
    d: 'Cadastra um código da fonte. Um código ainda não ingerido é aceito. Nas fontes cuja ' +
       'ingestão é dirigida por este cadastro ele entra como "pendente de ingestão" e é buscado ' +
       'na próxima ingestão; nas demais (o escopo vem da configuração do pipeline) ele fica como ' +
       '"sem dados" até que a equipe técnica inclua o código.' },
];

// A catalog write reaches the researcher-facing charts/filters only on the NEXT dbt build (+ the
// serving marts' cache TTL) — never instantly. Appended to save/rename toasts so the researcher
// isn't surprised the change doesn't show up in the dashboard right away (mirrors the hide notice).
//
// It used to say "alguns minutos", which is wrong by up to a DAY: the serving marts apply the
// visibility gate at BUILD time (hidden_code_predicate), and prod rebuilds on the daily
// dbt-build-prod schedule — `cron: '30 11 * * *'` = 08:30 BRT. A researcher who hid a produto,
// waited five minutes and still saw it in the charts would reasonably conclude the control was
// broken. Name the real cadence instead.
const _CC_LATENCIA =
  'A mudança vale na próxima reconstrução diária dos dados (por volta das 08:30, horário de Brasília).';

// The produto's LIFECYCLE STATE, derived from the two axes + whether its data actually
// landed in Gold. Read-only: it is a consequence of the controls, never a control itself —
// which is the point, since the retired "Ciclo de vida" dropdown was named for the whole
// lifecycle while only steering visibility. The remaining states (descontinuado, purgado)
// belong to removed produtos and live in the Descontinuados section, not in this table.
// PRECEDENCE matters: pausada wins over "sem dados" because a frozen produto that never
// arrived is paused, not "waiting for the next run" — saying "pendente" would promise an
// ingestion that will never come.
//
// The SAME reasoning applies per banco, and used not to: a produto with no data was called
// "Pendente de ingestão · será buscado na próxima ingestão" for EVERY source. For COMEX and
// COMTRADE that is false — their scope comes from config, not from this catalog — so a
// registration there sits "pendente" forever while the label keeps promising a fetch.
// `driven` (from /api/catalog/entries → catalog_driven_bancos) is the list of bancos a
// registration actually steers; outside it we say what is true instead.
function _ccStatus(entry, st, driven) {
  if ((entry.ingestao || 'ativa') === 'pausada') {
    return { key: 'pausado', label: 'Pausado', title: 'Não busca dados novos; o histórico no Gold é mantido' };
  }
  if (st && !st.has_data) {
    return (driven || []).includes(entry.banco)
      ? { key: 'pendente', label: 'Pendente de ingestão', title: 'Cadastrado; será buscado na próxima ingestão' }
      : { key: 'sem-dados', label: 'Sem dados',
          title: 'Cadastrado, mas a ingestão desta fonte não é dirigida pelo cadastro — '
               + 'o escopo dela é definido na configuração do pipeline. Registrar aqui não '
               + 'agenda uma busca; fale com a equipe técnica para incluir o código.' };
  }
  if ((entry.visibilidade || 'visivel') === _CC_OCULTO) {
    return { key: 'oculto', label: 'Oculto', title: 'Ingerido, mas fora de todos os gráficos e filtros' };
  }
  return { key: 'ativo', label: 'Ativo', title: 'Ingerindo e visível no dashboard' };
}
const _ccInt = (n) => (n == null ? '—' : Number(n).toLocaleString('pt-BR'));

// Agrupamento <select>. MODULE-level (stable identity) so React reconciles it across the
// parent's frequent re-renders (every keystroke in "Novo agrupamento", every busy toggle)
// instead of unmounting/remounting the whole subtree. When `value` matches no known group
// (a stray / unassigned entry, or the empty add-form draft) it shows an explicit empty
// option instead of silently defaulting to whatever group sorts first.
function CcGroupSelect({ value, onChange, placeholder, groups, busy, ariaLabel }) {
  const known = groups.some((g) => g.group_id === value);
  const empty = placeholder || (known ? null : 'Sem agrupamento — reatribua…');
  return (
    <select value={known ? value : ''} disabled={busy} aria-label={ariaLabel}
            onChange={(ev) => onChange(ev.target.value)} className="cc-group-select">
      {empty != null && <option value="">{empty}</option>}
      {groups.map((g) => <option key={g.group_id} value={g.group_id}>{g.group_name}</option>)}
    </select>
  );
}

// Inline-editable "Descrição" (the researcher's own free-text annotation — NOT the read-only
// descrição da fonte) for one catalog entry, editable both at creation AND afterward. MODULE-level
// (stable identity, like CcGroupSelect) so React doesn't remount it — and so doesn't blow away
// in-progress typing — across the parent's frequent re-renders (any save anywhere reloads `data`).
// Keeps its own local draft so typing doesn't round-trip a save on every keystroke; commits on
// blur/Enter only when the trimmed value actually differs from the saved one (skips a no-op
// write). Esc reverts the draft without saving.
function CcDescricaoField({ value, onSave, busy, ariaLabel }) {
  const [draft, setDraft] = useCcState(value || '');
  // Re-seed the local draft whenever the SAVED value changes under us (e.g. after this field's
  // own commit reloads `data`, or a group rename re-stamps every member). A same-content string
  // is reference-equal for React's dependency check, so this never clobbers an unrelated row's
  // in-progress typing.
  useCcEffect(() => { setDraft(value || ''); }, [value]);
  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed !== (value || '')) onSave(trimmed);
    else if (trimmed !== draft) setDraft(trimmed); // normalize stray whitespace locally, no write
  };
  // The ✎ marks the line as YOUR note (vs the source description directly above it). Always
  // in the DOM — never conditional on content — so the input's left edge doesn't shift sideways
  // the moment you type the first character; CSS fades the whole wrapper instead.
  return (
    <span className="cc-descricao-wrap">
      <span className="cc-descricao-mark" aria-hidden="true">✎</span>
      <input type="text" className="cc-descricao-input" value={draft} disabled={busy}
             aria-label={ariaLabel} title="Sua anotação (opcional) — não é a descrição da fonte"
             placeholder="+ anotação"
             onChange={(ev) => setDraft(ev.target.value)}
             onBlur={commit}
             onKeyDown={(ev) => {
               if (ev.key === 'Enter') ev.currentTarget.blur(); // blur triggers commit
               else if (ev.key === 'Escape') { setDraft(value || ''); ev.currentTarget.blur(); }
             }} />
    </span>
  );
}

// Accessible in-app confirmation — replaces the browser's inaccessible window.confirm/prompt
// with the same modal chrome as the citation/feedback dialogs (cite-backdrop/cite-modal/…),
// so it's announced (role=dialog + aria-modal), Esc-dismissable and design-system-consistent.
// `spec` = null (closed) or { title, body?, confirmLabel?, danger?, input?, onConfirm }. When
// `input` is present the modal shows a text field (rename) whose trimmed value flows to onConfirm.
function CcConfirmModal({ spec, onClose }) {
  const [value, setValue] = useCcState('');
  // Seed the input (rename) whenever a new spec opens.
  useCcEffect(() => { setValue(spec && spec.input ? (spec.input.value || '') : ''); }, [spec]);
  // Esc closes (mirrors the citation/feedback modals).
  useCcEffect(() => {
    if (!spec) return undefined;
    const onKey = (ev) => { if (ev.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [spec, onClose]);
  if (!spec) return null;
  const submit = () => {
    if (spec.input) {
      const v = value.trim();
      if (!v) return; // require a non-empty value (mirrors the old window.prompt guard)
      spec.onConfirm(v);
    } else {
      spec.onConfirm();
    }
    onClose();
  };
  return (
    <div className="cite-backdrop" onClick={onClose}>
      <div className="cite-modal" onClick={(ev) => ev.stopPropagation()}
           role="dialog" aria-modal="true" aria-labelledby="cc-confirm-title">
        <header className="cite-head">
          <div>
            <div className="overline">Cadastro de produtos</div>
            <h2 id="cc-confirm-title">{spec.title}</h2>
            {spec.body && <p className="caption">{spec.body}</p>}
          </div>
          <button className="fm-close" onClick={onClose} aria-label="Fechar">
            <window.Icon name="close" size={18}/>
          </button>
        </header>
        <div className="cite-body">
          {spec.input && (
            <label className="fb-label">
              {spec.input.label}
              <input id="cc-confirm-input" type="text" value={value} autoFocus
                     style={{ display: 'block', width: '100%', marginTop: 4 }}
                     onChange={(ev) => setValue(ev.target.value)}
                     onKeyDown={(ev) => { if (ev.key === 'Enter') submit(); }} />
            </label>
          )}
          <div className="cite-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
            <button type="button" className="btn-primary" onClick={submit}
                    style={spec.danger ? { background: 'var(--err, #b71c1c)', borderColor: 'var(--err, #b71c1c)' } : undefined}>
              {spec.confirmLabel || 'Confirmar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Rola TODOS os cartões de agrupamento juntos na horizontal.
//
// As larguras fixas da `.cc-table` existem para uma coisa só: a mesma coluna no mesmo x em
// todos os cartões, para o olho não ziguezaguear entre caixas. Quando a tela fica estreita
// demais a tabela passa a rolar (v1.46.9) — e uma barra POR cartão desfaz justamente essa
// grade, porque cada tabela mostraria uma janela diferente. Era o motivo declarado para a
// versão anterior preferir apertar as colunas a rolar.
//
// Sincronizar resolve os dois lados: rola, e continua alinhado. Consulta o DOM em vez de
// manter um registro de refs porque `.cc-dt-wrap` só existe nesta tela e os cartões
// montam/desmontam ao abrir e fechar o toggle — um registro teria de acertar esse ciclo de
// vida, e acertar errado deixa nós desmontados no conjunto.
function useSyncedTableScroll() {
    const sincronizando = useCcRef(false);

    return (ev) => {
        // Atribuir `scrollLeft` dispara `scroll` nos outros; sem o guarda, cada um
        // reagiria ao vizinho num laço.
        if (sincronizando.current) return;
        sincronizando.current = true;
        const alvo = ev.currentTarget;
        const x = alvo.scrollLeft;
        for (const el of document.querySelectorAll('.cc-dt-wrap')) {
            if (el !== alvo && el.scrollLeft !== x) el.scrollLeft = x;
        }
        requestAnimationFrame(() => {
            sincronizando.current = false;
        });
    };
}

function ViewCadastroProdutos() {
  const [data, setData] = useCcState({ entries: [], groups: [], loading: true, error: null, canEdit: true,
    // Bancos cuja INGESTÃO um cadastro realmente dirige (/api/catalog/entries →
    // catalog_driven_bancos). Vazio até resolver: preferimos NÃO prometer ingestão a
    // prometer uma que talvez não venha.
    catalogDriven: [] });
  // Uma barra horizontal por cartão, todas movendo juntas — ver useSyncedTableScroll.
  const sincronizarRolagem = useSyncedTableScroll();
  const [statusMap, setStatusMap] = useCcState({}); // "banco:code" -> {n_rows, year_start, year_end, has_data}
  const [statusErr, setStatusErr] = useCcState(false); // the (cheap, lazy) Gold-state read FAILED — distinct from "sem dados"
  const [status, setStatus] = useCcState(null); // { kind: 'ok' | 'err', msg }
  const [busy, setBusy] = useCcState(false);
  const [draft, setDraft] = useCcState({ ..._CC_EMPTY_DRAFT });
  const [showAdd, setShowAdd] = useCcState(false);
  const [orphans, setOrphans] = useCcState([]);
  const [orphansErr, setOrphansErr] = useCcState(false); // the orphans (Descontinuados) read FAILED — distinct from "no orphans"
  // In-app confirmation dialog (replaces window.confirm/prompt with accessible modal chrome).
  // null = closed; otherwise { title, body?, confirmLabel?, danger?, input?, onConfirm } — see
  // CcConfirmModal. `input` present ⇒ a rename-style text field whose value flows to onConfirm.
  const [pendingConfirm, setPendingConfirm] = useCcState(null);
  const [newGroup, setNewGroup] = useCcState('');
  // The source's REAL codes for the add form's banco (autocomplete + advisory "já existe" hint).
  const [srcCodes, setSrcCodes] = useCcState({ banco: null, codes: [], loading: false, error: false });
  // Cada agrupamento começa RECOLHIDO: com 31 cartões abertos a tela abre com ~234 linhas e
  // ninguém lê 234 linhas — quem chega aqui quer UM produto. Guardamos os abertos (e não os
  // fechados) para que um agrupamento novo nasça fechado como todos os outros.
  const [abertos, setAbertos] = useCcState(() => new Set());
  const [busca, setBusca] = useCcState('');

  // Idempotency keys, one STABLE change_id per in-flight logical operation. The key is scoped
  // to the entity AND the payload (see _saveKey): a retry of the SAME edit reuses its key so a
  // double-click / timeout-then-retry dedupes server-side, but a DIFFERENT later edit of the
  // same entity gets a FRESH key. A key is rotated only on success (run's opKeys), so a FAILED
  // op keeps its key for the resume. Scoping the key to the entity ALONE was a bug: after a
  // partial-batch failure retained the key of an already-committed write, the researcher's next
  // DIFFERENT edit of that entity reused the change_id and the server swallowed it as a benign
  // duplicate (attribute-only divergence), silently discarding the edit under a success toast.
  const cidRef = useCcRef(new Map());
  const cidFor = (key) => {
    if (!cidRef.current.has(key)) cidRef.current.set(key, _ccUuid());
    return cidRef.current.get(key);
  };
  const cidDone = (key) => cidRef.current.delete(key);
  // Idempotency key for a catalog-entry write: entity + a fingerprint of the MEANINGFUL fields
  // the server records (agrupamento, ciclo de vida, descrição). Two edits that change different
  // attributes of the same product therefore get distinct change_ids and both apply; re-issuing
  // the identical edit reuses one and dedupes.
  // A TABELA entra na chave junto com banco+código: um produto é (banco, tabela, código)
  // desde v1.39.0. Sem ela, editar as duas metades de um código compartilhado com os mesmos
  // atributos geraria o MESMO change_id, e a segunda edição seria descartada como replay.
  const _saveKey = (e) =>
    `save:${e.banco}:${e.sidra_tabela ?? '-'}:${e.codigo_produto}:` +
    JSON.stringify([e.agrupamento_id ?? null, e.ingestao ?? null, e.visibilidade ?? null, e.descricao_produto ?? null]);

  // Server-authoritative edit permission (from /api/catalog/entries' can_edit). The UI
  // merely REFLECTS it — the POST handlers still 403 on a stale true, so this only ever
  // hides controls, never widens access. `locked` = a write is in flight, editing isn't
  // allowed, OR permission isn't known yet (still loading) — controls stay disabled until
  // can_edit resolves, so a non-editor never sees briefly-enabled controls.
  const canEdit = data.canEdit !== false;
  const locked = busy || !canEdit || data.loading;

  const load = () => {
    setData((d) => ({ ...d, loading: true, error: null }));
    Promise.all([
      fetch('/api/catalog/entries').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))),
      // Reject (don't fall back to {groups:[]}) on a groups failure: an empty registry would
      // make EVERY product render under "Sem agrupamento registrado", inviting the researcher
      // to needlessly reassign them all. Surface the real error instead.
      fetch('/api/catalog/groups').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status} (agrupamentos)`)))),
    ])
      // NOTE: /api/catalog/entries also returns `by_agrupamento` (a server-side per-Agrupamento
      // rollup). The UI intentionally IGNORES it and derives grouping client-side from the
      // first-class /api/catalog/groups registry (groupsSorted/membersOf below). Kept server-side
      // (harmless, tested — serializers.serialize_catalog_worklist) rather than removed.
      .then(([e, g]) => setData({ entries: e.entries || [], groups: g.groups || [], loading: false, error: null, canEdit: e.can_edit !== false, catalogDriven: e.catalog_driven_bancos || [] }))
      .catch((err) => setData({ entries: [], groups: [], loading: false, error: String(err.message || err), canEdit: true, catalogDriven: [] }));
    // Orphans (removed from the catalog, Gold data lingering) — shown as Descontinuados. A
    // failure is surfaced (orphansErr) rather than rendered as an empty list, which would
    // silently HIDE the whole Descontinuados section (gated on orphans.length > 0).
    fetch('/api/catalog/orphans')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { setOrphans(d.orphans || []); setOrphansErr(false); })
      .catch(() => { setOrphans([]); setOrphansErr(true); });
    // Per-commodity Gold state (linhas + período) — a separate, cheap lazy read. A failure is
    // surfaced (statusErr) rather than rendered as an empty map, which reads like perpetual "…".
    fetch('/api/catalog/status')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { setStatusMap(d.status || {}); setStatusErr(false); })
      .catch(() => { setStatusMap({}); setStatusErr(true); });
  };
  useCcEffect(load, []);

  // Fetch the source's real codes whenever the add form is open on a banco (backs the
  // <datalist> autocomplete + the advisory "código já existe na Gold?" hint). Skip if already loaded.
  useCcEffect(() => {
    if (!showAdd || !draft.banco) return;
    if (srcCodes.banco === draft.banco) return;
    const target = draft.banco;
    // Race guard: if the user switches banco again before this fetch resolves, ignore the
    // stale response — otherwise an out-of-order reply could overwrite the newer banco's codes,
    // stranding the hint at "verificando…" with an empty autocomplete.
    let cancelled = false;
    setSrcCodes({ banco: target, codes: [], loading: true, error: false });
    fetch('/api/catalog/source-codes?banco=' + encodeURIComponent(target))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (!cancelled) setSrcCodes({ banco: target, codes: d.codes || [], loading: false, error: false }); })
      // A load failure is surfaced (error: true) rather than masquerading as "0 códigos" — the
      // add-form hint then says the codes couldn't be verified instead of "ainda não ingerido".
      .catch(() => { if (!cancelled) setSrcCodes({ banco: target, codes: [], loading: false, error: true }); });
    return () => { cancelled = true; };
  }, [showAdd, draft.banco]);

  // POST a write; throw the server's pt-BR error on a non-2xx so callers can surface it.
  const post = async (path, body) => {
    const r = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!r.ok) {
      const b = await r.json().catch(() => null);
      throw new Error((b && b.error) || `HTTP ${r.status}`);
    }
    return r.json();
  };

  const run = async (fn, okMsg, opKeys) => {
    setBusy(true); setStatus(null);
    let ok = false;
    try {
      await fn();
      ok = true;
      setStatus({ kind: 'ok', msg: okMsg });
    } catch (e) {
      setStatus({ kind: 'err', msg: String(e.message || e) });
    } finally {
      // Always re-sync to the PERSISTED state — a multi-write op that fails midway has
      // already committed some rows; reloading only on success would show stale values.
      load();
      setBusy(false);
    }
    // Rotate the idempotency key(s) ONLY after a committed op — a FAILED op keeps its key so a
    // retry reuses it and dedupes server-side (a partial batch resumes without re-applying).
    if (ok && opKeys) [].concat(opKeys).forEach(cidDone);
    return ok; // callers (e.g. the add form) reset/close only on success
  };

  const saveEntry = (entry) => {
    const key = _saveKey(entry);
    return run(
      () => post('/api/catalog/entry', { ...entry, change_id: cidFor(key) }),
      `Produto ${entry.codigo_produto} salvo. ${_CC_LATENCIA}`,
      key,
    );
  };

  // Visibilidade. HIDING pulls the produto from EVERY researcher chart/filter, so confirm +
  // explain the consequence + the update latency first. Un-hiding needs no confirmation.
  const changeVisibilidade = (e, visibilidade) => {
    if (visibilidade === _CC_OCULTO) {
      setPendingConfirm({
        title: `Ocultar ${e.codigo_produto}?`,
        body: `Ele deixará de aparecer em TODOS os gráficos e filtros do dashboard para os ` +
          `pesquisadores. Os dados continuam no Gold e a ingestão segue normalmente. ` +
          `A mudança vale na próxima reconstrução diária dos dados (por volta das 08:30, ` +
          `horário de Brasília) — não na hora.`,
        confirmLabel: 'Ocultar', danger: true,
        onConfirm: () => saveEntry({ ...e, visibilidade }),
      });
      return;
    }
    saveEntry({ ...e, visibilidade });
  };

  // Ingestão. Pausing is REVERSIBLE and destroys nothing (the Gold history stays, and the
  // produto keeps showing) — so unlike hiding and removing, it needs no confirmation.
  const changeIngestao = (e, ingestao) => saveEntry({ ...e, ingestao });

  const removeEntry = (e) => {
    setPendingConfirm({
      title: `Remover ${e.codigo_produto} (${_CC_BANCO_LABEL[e.banco] || e.banco}) do cadastro?`,
      body: 'Os dados já baixados ficam órfãos (não são apagados automaticamente).',
      confirmLabel: 'Remover', danger: true,
      onConfirm: () => {
        const key = `rm:${e.banco}:${e.sidra_tabela ?? '-'}:${e.codigo_produto}`;
        run(() => post('/api/catalog/entry/remove', { codigo_produto: e.codigo_produto, banco: e.banco, sidra_tabela: e.sidra_tabela ?? null, change_id: cidFor(key) }),
          `Produto ${e.codigo_produto} marcado como descontinuado.`, key);
      },
    });
  };

  // Move a commodity to a DIFFERENT agrupamento (membership change) — re-upserts with the
  // target group's id + name, so it re-groups on reload.
  const moveEntry = (e, groupId) => {
    const g = data.groups.find((x) => x.group_id === groupId);
    if (!g || g.group_id === e.agrupamento_id) return;
    saveEntry({ ...e, agrupamento_id: g.group_id, agrupamento: g.group_name });
  };

  // ── Agrupamento (group) management — the first-class registry ──────────────────
  const createGroup = () => {
    const name = newGroup.trim();
    if (!name) { setStatus({ kind: 'err', msg: 'Informe o nome do novo agrupamento.' }); return; }
    const key = `grp-new:${name}`;
    // Clear the input ONLY on a committed create — clearing eagerly discarded the typed name
    // even when the save failed, so the researcher had to retype it.
    run(() => post('/api/catalog/group', { group_name: name, change_id: cidFor(key) }),
      `Agrupamento "${name}" criado.`, key).then((ok) => { if (ok) setNewGroup(''); });
  };
  const renameGroup = (g) => {
    setPendingConfirm({
      title: `Renomear o agrupamento "${g.group_name}"`,
      input: { label: 'Novo nome do agrupamento', value: g.group_name },
      confirmLabel: 'Renomear',
      onConfirm: (name) => {
        const trimmed = name.trim();
        if (!trimmed || trimmed === g.group_name) return;
        // Key on the target NAME, not just the group id: after a rename that committed but was
        // reported as failed (so its key was retained), a SECOND rename to a DIFFERENT name must
        // get a fresh change_id — else the server dedupes it and re-stamps the OLD name while the
        // toast announces the new one.
        const key = `grp:${g.group_id}:${trimmed}`;
        run(() => post('/api/catalog/group', { group_id: g.group_id, group_name: trimmed, change_id: cidFor(key) }),
          `Agrupamento renomeado para "${trimmed}". ${_CC_LATENCIA}`, key);
      },
    });
  };
  const deleteGroup = (g) => {
    if (g.n_members > 0) return; // the button is disabled; guard anyway
    setPendingConfirm({
      title: `Excluir o agrupamento vazio "${g.group_name}"?`,
      confirmLabel: 'Excluir', danger: true,
      onConfirm: () => {
        const key = `grp-del:${g.group_id}`;
        run(() => post('/api/catalog/group/remove', { group_id: g.group_id, change_id: cidFor(key) }),
          `Agrupamento "${g.group_name}" excluído.`, key);
      },
    });
  };

  // Per-Agrupamento lifecycle (the lead's edit grain): set ONE axis for every member.
  // `axis` is the field name ('ingestao' | 'visibilidade') so the bulk path can't drift from
  // the per-row one — both write the same coded field through the same saveEntry contract.
  const setAxisForGroup = (g, axis, value) => {
    const members = data.entries.filter((e) => e.agrupamento_id === g.group_id);
    const apply = () => {
      const writes = members.map((m) => ({ ...m, [axis]: value }));
      const keys = writes.map(_saveKey);
      run(async () => {
        let done = 0;
        try {
          for (const w of writes) {
            await post('/api/catalog/entry', { ...w, change_id: cidFor(_saveKey(w)) });
            done += 1;
          }
        } catch (e) {
          throw new Error(`${String(e.message || e)} — aplicado a ${done}/${writes.length} antes da falha.`);
        }
      }, `Ciclo de vida de "${g.group_name}" atualizado (${writes.length}).`, keys);
    };
    if (axis === 'visibilidade' && value === _CC_OCULTO) {
      setPendingConfirm({
        title: `Ocultar TODOS os ${members.length} produto(s) de "${g.group_name}"?`,
        body: 'Eles deixarão de aparecer em qualquer gráfico ou filtro do dashboard para os ' +
          'pesquisadores. Vale na próxima reconstrução diária dos dados (por volta das 08:30).',
        confirmLabel: 'Ocultar', danger: true,
        onConfirm: apply,
      });
      return;
    }
    apply();
  };

  // ── Add form: derived validation state ────────────────────────────────────────
  const codeIndex = useCcMemo(() => {
    const m = new Map();
    (srcCodes.codes || []).forEach((c) => m.set(c.code, c.name));
    return m;
  }, [srcCodes]);
  const codeLoadedForBanco = srcCodes.banco === draft.banco && !srcCodes.loading;
  // The source-codes fetch for the current banco FAILED — distinct from "0 códigos" (empty but
  // loaded); the hint says the code couldn't be verified instead of falsely "não ingerido".
  const srcCodesErr = srcCodes.error && srcCodes.banco === draft.banco;
  // Only judge the code against the CURRENTLY-loaded banco's codes — otherwise, in the
  // paint right after a banco switch (before the codes reload), a code from the previous
  // banco could flash a false ✓ / enable Salvar.
  const codeMatch = (draft.codigo_produto && codeLoadedForBanco)
    ? codeIndex.has(draft.codigo_produto) : null;
  const groupChosen = !!data.groups.find((x) => x.group_id === draft.agrupamento_id);
  // Só um banco EXIGE a marca de tabela (ppm); o pevs a aceita e tem padrão, os demais
  // não a têm. Derivado do registro — um `draft.banco !== 'ppm'` aqui voltaria a bloquear
  // o dia em que outro banco passar a exigi-la.
  const sidraTagged = !_CC_SIDRA_TABELAS[draft.banco]?.obrigatorio || !!draft.sidra_tabela;
  // A code the source doesn't (yet) list is no longer blocked — it registers as *pendente
  // de ingestão* (the catalog now drives ingestion). We only need a code, a group, the PPM
  // tag when applicable, and edit permission.
  const canSubmit = !!draft.codigo_produto && groupChosen && sidraTagged && !locked;

  const submitAdd = async () => {
    if (!draft.codigo_produto || !draft.banco) {
      setStatus({ kind: 'err', msg: 'Código do produto e banco são obrigatórios (formam a chave).' });
      return;
    }
    const g = data.groups.find((x) => x.group_id === draft.agrupamento_id);
    if (!g) {
      setStatus({ kind: 'err', msg: 'Escolha um agrupamento (ou crie um novo acima).' });
      return;
    }
    const cfgSidra = _CC_SIDRA_TABELAS[draft.banco];
    if (cfgSidra?.obrigatorio && !draft.sidra_tabela) {
      setStatus({ kind: 'err', msg: `Escolha a ${cfgSidra.campo.toLowerCase()}.` });
      return;
    }
    // Reset + close ONLY on a successful write; a 400/403 keeps the form open with the
    // user's input intact so they can correct it.
    const ok = await saveEntry({ ...draft, agrupamento: g.group_name });
    if (ok) {
      setDraft({ ..._CC_EMPTY_DRAFT });
      setShowAdd(false);
    }
  };

  // Cancel the add form: close it AND discard the draft. Shared by the toolbar toggle and the
  // card's "Cancelar" so the two behave identically (the toggle previously left the draft intact).
  const cancelAdd = () => { setShowAdd(false); setDraft({ ..._CC_EMPTY_DRAFT }); };

  // Registry groups, sorted; each rendered as a card with its members.
  const groupsSorted = [...data.groups].sort((a, b) => a.group_name.localeCompare(b.group_name, 'pt-BR'));
  const membersOf = (gid) => data.entries.filter((e) => e.agrupamento_id === gid);
  // Entries pointing at a group not in the registry (legacy / pre-migration) → a fallback
  // bucket so nothing is hidden. After the seed migration this is empty.
  const knownIds = new Set(data.groups.map((g) => g.group_id));
  const strayEntries = data.entries.filter((e) => !knownIds.has(e.agrupamento_id));

  // ── Busca ────────────────────────────────────────────────────────────────────────────
  // Procura no CÓDIGO e nas duas descrições — a da fonte e a anotação do pesquisador —, mais
  // o banco e o agrupamento. A pergunta que ela responde é "esse produto já está cadastrado?",
  // e quem pergunta lembra do nome OU do código, raramente de qual banco. Filtra a LINHA, não
  // só o cartão: mostrar um agrupamento inteiro porque um item bateu esconderia qual bateu.
  const termos = _ccNorm(busca).split(' ').filter(Boolean);
  const buscando = termos.length > 0;
  const nomeDoGrupo = new Map(data.groups.map((g) => [g.group_id, g.group_name]));
  const casa = (e) => !buscando || _ccCombina(termos, [
    e.codigo_produto, e.descricao_fonte, e.descricao_produto,
    _CC_BANCO_LABEL[e.banco] || e.banco, nomeDoGrupo.get(e.agrupamento_id) || '',
  ]);
  const filtrar = (lista) => (buscando ? lista.filter(casa) : lista);
  const achados = buscando ? data.entries.filter(casa).length : 0;

  // Buscando, o resultado tem de estar VISÍVEL: um acerto escondido atrás de um toggle é o
  // mesmo que nenhum acerto. Fora da busca vale o que o usuário abriu — e um cartão vazio
  // continua listado (recolhido), senão o agrupamento sem produtos some sem explicação.
  const estaAberto = (gid) => (buscando ? true : abertos.has(gid));
  const alternar = (gid) => setAbertos((prev) => {
    const p = new Set(prev);
    if (p.has(gid)) p.delete(gid); else p.add(gid);
    return p;
  });
  const gruposVisiveis = buscando
    ? groupsSorted.filter((g) => membersOf(g.group_id).some(casa))
    : groupsSorted;
  const todosAbertos = groupsSorted.length > 0 && groupsSorted.every((g) => abertos.has(g.group_id));

  const memberRows = (members) => (
    <div className="dt-wrap cc-dt-wrap" onScroll={sincronizarRolagem}>
      <table className="dt-table cc-table">
        <thead>
          <tr>
            <th>Banco</th><th>Tabela</th><th>Código</th><th>Descrição (fonte)</th>
            <th className="num">Linhas</th><th>Período</th><th>Status</th>
            <th>Agrupamento</th><th>Ingestão</th><th>Exibição</th><th aria-label="ações"></th>
          </tr>
        </thead>
        <tbody>
          {members.map((e) => {
            // O status vem do Gold por (banco, código): o FATO não carrega a tabela, então
            // duas metades de um código compartilhado mostrariam a mesma contagem. É limite
            // do dado, não chave errada — `doctor → shared-code` avisa se o caso aparecer.
            const st = statusMap[e.banco + ':' + e.codigo_produto];
            return (
              // A key precisa da chave INTEIRA: com banco+código só, as duas metades de um
              // código compartilhado colidiriam e o React reusaria a linha errada.
              <tr key={e.banco + '|' + (e.sidra_tabela ?? '-') + '|' + e.codigo_produto}>
                <td className="cc-cell-title">{_CC_BANCO_LABEL[e.banco] || e.banco}</td>
                {/* A identidade de um produto é BANCO + TABELA + CÓDIGO, então o trio lê da
                    esquerda para a direita em colunas próprias. Era um selo dentro da célula do
                    banco, o que escondia um terço da chave dentro de outro terço. Bancos de uma
                    tabela só mostram o travessão: a coluna não some, senão o leitor não sabe se
                    aquele banco não tem tabela ou se a tela deixou de mostrar. */}
                {/* O CÓDIGO da tabela SIDRA, não o nome por extenso: é o identificador que a
                    fonte usa e que aparece na URL do SIDRA, e a coluna vizinha já mostra o
                    código do produto — os dois lidos juntos formam a chave. Mesma fonte,
                    cor e tamanho do resto da tabela (a classe `tnum` das colunas numéricas),
                    em vez do selo colorido: um selo dizia "isto é outra coisa", quando é
                    apenas mais um pedaço da identidade. O nome por extenso vira `title`, de
                    modo que ninguém precise decorar que 289 é extração vegetal. */}
                <td className="tnum" data-label="Tabela"
                    title={_CC_SIDRA_LABEL[e.banco]?.[e.sidra_tabela] || undefined}>
                  {_CC_SIDRA_TABELAS[e.banco]
                    ? (e.sidra_tabela || <span className="dt-null">—</span>)
                    : <span className="dt-null">—</span>}
                </td>
                <td className="tnum" data-label="Código">{e.codigo_produto}</td>
                <td data-label="Descrição">
                  {e.descricao_fonte || <span className="dt-null">—</span>}
                  {/* The researcher's own free-text annotation — editable here, not just at
                      creation (commits on blur/Enter; see CcDescricaoField). Distinct from the
                      read-only descrição da fonte above; when empty it fades out (CSS) so an
                      un-annotated row reads as a single clean line. */}
                  <CcDescricaoField value={e.descricao_produto} busy={locked}
                                    ariaLabel={`Sua descrição de ${e.codigo_produto}`}
                                    onSave={(text) => saveEntry({ ...e, descricao_produto: text })} />
                </td>
                <td className="num tnum" data-label="Linhas">{st ? _ccInt(st.n_rows) : (statusErr ? '—' : '…')}</td>
                <td className="tnum" data-label="Período">{st && st.year_start != null ? `${st.year_start}–${st.year_end}` : '—'}</td>
                <td data-label="Status">
                  {/* DERIVED, read-only: the produto's lifecycle state as a consequence of the
                      two axes + whether its data reached Gold. Absorbs the old "Dados" column —
                      "sem dados na Gold" and "pendente de ingestão" were the same fact stated
                      twice. Until the Gold-state read resolves we show the loading/unknown mark
                      rather than guessing a state from the axes alone. */}
                  {!st ? <span className="dt-null">{statusErr ? '—' : '…'}</span> : (() => {
                    const s = _ccStatus(e, st, data.catalogDriven);
                    return <span className={'cc-status cc-status-' + s.key} title={s.title}>{s.label}</span>;
                  })()}
                </td>
                <td data-label="Agrupamento">
                  <CcGroupSelect value={e.agrupamento_id} onChange={(gid) => moveEntry(e, gid)}
                                 groups={groupsSorted} busy={locked}
                                 ariaLabel={`Agrupamento de ${e.codigo_produto}`} />
                </td>
                {/* One column per axis: the two are independent decisions, so they read as
                    siblings of Agrupamento rather than as two halves of a compound field. The
                    <th> labels them, which is why the cells carry no inner label. */}
                <td data-label="Ingestão">
                  <select disabled={locked} value={e.ingestao || 'ativa'}
                          aria-label={`Ingestão de ${e.codigo_produto}`}
                          title={(_CC_INGESTAO.find((o) => o.v === (e.ingestao || 'ativa')) || {}).hint}
                          onChange={(ev) => changeIngestao(e, ev.target.value)}>
                    {_CC_INGESTAO.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
                  </select>
                </td>
                <td data-label="Exibição">
                  <select disabled={locked} value={e.visibilidade || 'visivel'}
                          aria-label={`Visibilidade de ${e.codigo_produto}`}
                          title={(_CC_VISIBILIDADE.find((o) => o.v === (e.visibilidade || 'visivel')) || {}).hint}
                          onChange={(ev) => changeVisibilidade(e, ev.target.value)}>
                    {_CC_VISIBILIDADE.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
                  </select>
                </td>
                <td className="cc-cell-actions" data-label="Ações">
                  <button type="button" className="cc-remove" disabled={locked}
                          title="Remover (marca como descontinuado)" aria-label={`Remover ${e.codigo_produto}`}
                          onClick={() => removeEntry(e)}
                          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--err, #b71c1c)' }}>
                    🗑
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <>
      <CcConfirmModal spec={pendingConfirm} onClose={() => setPendingConfirm(null)} />
      <div className="card subtle" style={{ marginBottom: 12 }}>
        <p className="caption" style={{ margin: 0 }}>
          Este é o <strong>cadastro de produtos</strong> — a fonte única de verdade do que entra
          e sai do dashboard. Cada produto é identificado por <code>(banco, tabela, código)</code> —
          o <strong>código real da fonte</strong>, e a tabela porque PEVS e PPM reúnem duas sob um
          mesmo banco — e pertence a um <strong>agrupamento</strong> (o
          conceito que a unifica entre fontes). Agrupamentos são criados, renomeados e excluídos aqui;
          <strong>Ingestão</strong> e <strong>Exibição</strong> controlam, separadamente, se o pipeline
          busca dados novos e se o pesquisador vê o produto; <strong>remover</strong> um produto o marca
          como descontinuado (os dados já baixados ficam órfãos, apagados só por um humano). Edições
          exigem autorização e ficam registradas com seu e-mail.
        </p>
      </div>

      {/* Reference legend: what each column means and what each edit actually does. Collapsed
          by default (same <details> card pattern as the Qualidade flag legend) so it never
          pushes the table down — the page just spent two rounds getting more compact. */}
      <details className="cc-help card">
        <summary className="cc-help-summary">
          <span>Como ler esta tabela e o que cada edição faz</span>
          <span className="caption">{_CC_HELP_COLUNAS.length} colunas · {_CC_HELP_ACOES.length} ações</span>
        </summary>
        <div className="cc-help-body">
          {/* Two clearly separate panels: reference (what you READ) vs actions (what you DO).
              The left accent colour carries that distinction — blue for the informational
              half, green for the one that writes — mirroring .mc-bar's accent convention. */}
          <div className="cc-help-block cc-help-block-ler">
            <h3 className="cc-help-h">
              O que cada coluna mostra
              <span className="cc-help-h-n">{_CC_HELP_COLUNAS.length} colunas</span>
            </h3>
            <dl className="cc-help-list">
              {_CC_HELP_COLUNAS.map((c) => (
                <div key={c.k} className="cc-help-item">
                  <dt>{c.k}</dt>
                  <dd className="caption">{c.d}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="cc-help-block cc-help-block-editar">
            <h3 className="cc-help-h">
              O que cada edição faz
              <span className="cc-help-h-n">{_CC_HELP_ACOES.length} ações</span>
            </h3>
            <dl className="cc-help-list">
              {_CC_HELP_ACOES.map((a) => (
                <div key={a.k} className="cc-help-item">
                  <dt>
                    {a.k}
                    {a.tag && <span className={'cc-help-tag cc-help-tag-' + a.tone}>{a.tag}</span>}
                  </dt>
                  <dd className="caption">{a.d}</dd>
                </div>
              ))}
            </dl>
          </div>
          <p className="caption cc-help-foot">
            Nada aqui é destrutivo: o registro é <strong>somente-adição</strong> — cada edição vira
            uma nova linha com seu e-mail e a data, e nenhuma anterior é apagada. As mudanças valem
            na <strong>próxima reconstrução diária dos dados</strong> (por volta das 08:30, horário
            de Brasília), não na hora.
          </p>
        </div>
      </details>

      {!canEdit && (
        <p className="caption" role="status"
           style={{ padding: '8px 10px', borderRadius: 6, marginBottom: 10,
                    background: 'var(--warn-bg, #fff8e1)', color: 'var(--warn, #8a6d00)',
                    border: '1px solid var(--warn, #b8860b)' }}>
          <strong>Modo somente leitura</strong> — você não está autorizado a editar este
          cadastro. Peça a um editor autorizado (ou a um operador) para incluir seu e-mail
          na lista de editores.
        </p>
      )}

      {status && (
        <p className="caption" role={status.kind === 'err' ? 'alert' : 'status'}
           style={{ padding: '8px 10px', borderRadius: 6, marginBottom: 10,
                    background: status.kind === 'ok' ? 'var(--ok-bg, #e8f5e9)' : 'var(--err-bg, #fdecea)',
                    color: status.kind === 'ok' ? 'var(--ok, #1b7f3b)' : 'var(--err, #b71c1c)' }}>
          {status.msg}
        </p>
      )}

      {statusErr && !data.error && !data.loading && (
        // ONLY the partial-failure case: the catalog itself loaded but the (separate, lazy)
        // Gold-state read failed. Suppressed when the catalog itself failed/loading, so we never
        // claim "o cadastro continua válido" next to the catalog's own "Erro ao carregar".
        <p className="caption" role="status"
           style={{ padding: '8px 10px', borderRadius: 6, marginBottom: 10,
                    background: 'var(--warn-bg, #fff8e1)', color: 'var(--warn, #8a6d00)',
                    border: '1px solid var(--warn, #b8860b)' }}>
          Não foi possível carregar o estado dos produtos no Gold (linhas, período e “tem dados”).
          O cadastro continua válido; recarregue a página para tentar de novo.
        </p>
      )}

      {orphansErr && !data.loading && (
        // The Descontinuados section is gated on orphans.length > 0, so a failed orphans read
        // would silently hide it — surface the failure instead (there MAY be discontinued produtos).
        <p className="caption" role="alert"
           style={{ padding: '8px 10px', borderRadius: 6, marginBottom: 10,
                    background: 'var(--warn-bg, #fff8e1)', color: 'var(--warn, #8a6d00)',
                    border: '1px solid var(--warn, #b8860b)' }}>
          Não foi possível carregar os produtos descontinuados (órfãos). Pode haver itens
          aguardando remoção que não estão sendo exibidos; recarregue a página para tentar de novo.
        </p>
      )}

      {orphans.length > 0 && (
        <div className="card" style={{ marginBottom: 12, borderLeft: '4px solid var(--err, #b71c1c)' }}>
          <window.SectionHeader
            overline="Descontinuados"
            title={`${orphans.length.toLocaleString('pt-BR')} descontinuado(s)`}
          />
          <p className="caption" style={{ margin: '0 2px 8px' }}>
            Removidos do cadastro, mas os dados já baixados continuam no Gold. Serão removidos
            por um operador (com backup), <strong>nunca automaticamente</strong>.
          </p>
          <div className="dt-wrap">
            <table className="dt-table">
              <thead>
                <tr><th>Agrupamento</th><th>Banco</th><th>Código</th><th>Situação</th><th>Marcado em</th></tr>
              </thead>
              <tbody>
                {orphans.map((o) => {
                  // Honor the server's per-row status: a re-orphaned code already PURGED reads
                  // 'purged' (its Gold data returned via a rebuild), not a blanket "aguardando".
                  const purged = o.status === 'purged';
                  return (
                    <tr key={o.banco + '|' + o.codigo_produto} title={o.warning || ''}>
                      <td>{o.agrupamento || '—'}</td>
                      <td>{_CC_BANCO_LABEL[o.banco] || o.banco}</td>
                      <td className="tnum">{o.codigo_produto}</td>
                      <td className="caption">{purged ? 'Purgado — dados retornaram ao Gold' : 'Aguardando remoção'}</td>
                      <td className="caption">{o.flagged_at ? String(o.flagged_at).slice(0, 10) : 'detectado agora'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* A busca vem ANTES do resto da barra e ocupa a primeira linha inteira: com os cartões
          recolhidos por padrão, ela passa a ser o caminho principal para chegar a um produto,
          não um filtro acessório. */}
      <div className="pp-selector cc-busca-barra" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <label className="cc-busca">
          <span className="cc-busca-icone" aria-hidden="true">⌕</span>
          <input type="search" value={busca} className="cc-busca-input"
                 placeholder="Pesquisar produto por código ou descrição…"
                 aria-label="Pesquisar no cadastro por código ou descrição"
                 onChange={(e) => setBusca(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Escape') setBusca(''); }} />
          {busca && (
            <button type="button" className="cc-busca-limpar" onClick={() => setBusca('')}
                    aria-label="Limpar busca" title="Limpar (Esc)">×</button>
          )}
        </label>
        {/* O resultado é dito em número: "0 produtos" responde "não, não está cadastrado" —
            que é justamente a pergunta — de um jeito que uma lista vazia não responde. */}
        <span className="caption cc-busca-saldo" role="status">
          {buscando
            ? `${achados.toLocaleString('pt-BR')} produto(s) em ${gruposVisiveis.length} agrupamento(s)`
            : `${data.entries.length.toLocaleString('pt-BR')} produtos · ${data.groups.length} agrupamentos`}
        </span>
        <button type="button" className="seg-opt" disabled={buscando || !groupsSorted.length}
                title={buscando ? 'Durante a busca os resultados ficam sempre abertos' : undefined}
                onClick={() => setAbertos(todosAbertos ? new Set()
                  : new Set(groupsSorted.map((g) => g.group_id)))}>
          {todosAbertos ? '▾ Recolher todos' : '▸ Expandir todos'}
        </button>
      </div>

      <div className="pp-selector" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <label className="caption" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Novo agrupamento:
          <input type="text" value={newGroup} placeholder="Ex.: Castanha" disabled={locked}
                 onChange={(e) => setNewGroup(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') createGroup(); }} />
          <button type="button" className="seg-opt" onClick={createGroup} disabled={locked || !newGroup.trim()}>
            + Criar
          </button>
        </label>
        <button type="button" className="seg-opt" disabled={locked}
                onClick={() => (showAdd ? cancelAdd() : setShowAdd(true))}>
          {showAdd ? 'Cancelar' : '+ Adicionar produto'}
        </button>
      </div>

      {showAdd && (
        <div className="card cc-add-card" style={{ marginBottom: 12 }}>
          <window.SectionHeader overline="Cadastro" title="Adicionar produto"
            action={<span className="caption">informe o código real da fonte</span>} />
          <div className="cc-add-grid">
            <label className="cc-field">
              <span className="cc-field-label">Banco (fonte)</span>
              <select value={draft.banco} disabled={locked}
                      onChange={(e) => setDraft((d) => ({ ...d, banco: e.target.value, codigo_produto: '', sidra_tabela: '' }))}>
                {_CC_BANCOS.map((b) => <option key={b.v} value={b.v}>{b.label}</option>)}
              </select>
            </label>

            {_CC_SIDRA_TABELAS[draft.banco] && (
              <label className="cc-field">
                <span className="cc-field-label">{_CC_SIDRA_TABELAS[draft.banco].campo}</span>
                <select value={draft.sidra_tabela} disabled={locked}
                        onChange={(e) => setDraft((d) => ({ ...d, sidra_tabela: e.target.value }))}>
                  <option value="">{_CC_SIDRA_TABELAS[draft.banco].vazio}</option>
                  {_CC_SIDRA_TABELAS[draft.banco].opcoes.map(
                    (t) => <option key={t.v} value={t.v}>{t.v} — {t.label}</option>)}
                </select>
              </label>
            )}

            <label className="cc-field">
              <span className="cc-field-label">Código do produto</span>
              <input type="text" list="cc-code-options" value={draft.codigo_produto} disabled={locked}
                     placeholder={srcCodes.loading && srcCodes.banco === draft.banco ? 'carregando códigos…' : 'digite ou escolha um código real'}
                     autoComplete="off"
                     onChange={(e) => setDraft((d) => ({ ...d, codigo_produto: e.target.value.trim() }))} />
              <datalist id="cc-code-options">
                {(srcCodes.banco === draft.banco ? srcCodes.codes : []).slice(0, 3000).map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </datalist>
              {srcCodesErr ? (
                // The source's code list failed to load — we can't verify the code, so say so
                // instead of claiming "0 códigos" / "ainda não ingerido" (both misleading here).
                <small className="cc-hint" style={{ color: 'var(--err, #b71c1c)' }}>
                  Não foi possível carregar os códigos de {_CC_BANCO_LABEL[draft.banco]} para conferência.
                </small>
              ) : draft.codigo_produto ? (
                codeMatch === true ? (
                  <small className="cc-hint cc-hint-ok">✓ {codeIndex.get(draft.codigo_produto) || 'código válido'}</small>
                ) : codeLoadedForBanco ? (
                  // Not (yet) in the source list → accepted either way; a soft warning, not a
                  // block. What the warning PROMISES depends on the banco: the catalog steers
                  // ingestion only for the sources in `catalogDriven` (the IBGE pipelines, and
                  // only while catalog_authoritative_ingestion is on). Saying "será buscado na
                  // próxima ingestão" for COMEX/COMTRADE was simply untrue — their scope lives
                  // in the pipeline config, so the entry would sit pendente forever.
                  <small className="cc-hint" style={{ color: 'var(--warn, #b8860b)' }}>
                    {(data.catalogDriven || []).includes(draft.banco)
                      ? `⚠ ainda não ingerido em ${_CC_BANCO_LABEL[draft.banco]} — será buscado na próxima ingestão`
                      : `⚠ ainda não ingerido em ${_CC_BANCO_LABEL[draft.banco]} — o cadastro não agenda a busca `
                        + `nesta fonte (o escopo dela vem da configuração do pipeline); o produto entra como “sem dados”`}
                  </small>
                ) : (
                  <small className="cc-hint">verificando…</small>
                )
              ) : (
                <small className="cc-hint">
                  {srcCodes.banco === draft.banco && !srcCodes.loading
                    ? `${srcCodes.codes.length.toLocaleString('pt-BR')} códigos reais nesta fonte`
                    : ' '}
                </small>
              )}
            </label>

            <label className="cc-field">
              <span className="cc-field-label">Agrupamento</span>
              <CcGroupSelect value={draft.agrupamento_id} groups={groupsSorted} busy={locked}
                           onChange={(gid) => setDraft((d) => ({ ...d, agrupamento_id: gid }))}
                           placeholder={data.groups.length ? 'Escolha um agrupamento…' : 'Crie um agrupamento primeiro'} />
            </label>

            <label className="cc-field">
              <span className="cc-field-label">Ingestão</span>
              <select value={draft.ingestao} disabled={locked}
                      onChange={(e) => setDraft((d) => ({ ...d, ingestao: e.target.value }))}>
                {_CC_INGESTAO.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
              </select>
            </label>

            <label className="cc-field">
              <span className="cc-field-label">Exibição</span>
              <select value={draft.visibilidade} disabled={locked}
                      onChange={(e) => setDraft((d) => ({ ...d, visibilidade: e.target.value }))}>
                {_CC_VISIBILIDADE.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
              </select>
            </label>

            <label className="cc-field cc-field-wide">
              <span className="cc-field-label">Descrição <small className="pc-cap">(opcional — anotação sua)</small></span>
              <input type="text" value={draft.descricao_produto} disabled={locked} placeholder="ex.: Castanha-do-pará com casca"
                     onChange={(e) => setDraft((d) => ({ ...d, descricao_produto: e.target.value }))} />
            </label>
          </div>
          <div className="cc-add-actions">
            <button type="button" className="btn-primary" onClick={submitAdd} disabled={!canSubmit}>
              {busy ? 'Salvando…' : 'Salvar produto'}
            </button>
            <button type="button" className="btn-secondary" onClick={cancelAdd} disabled={busy}>
              Cancelar
            </button>
            {draft.banco === 'ppm' && !draft.sidra_tabela && draft.codigo_produto && (
              <span className="caption" style={{ color: 'var(--err, #b71c1c)' }}>escolha a tabela PPM</span>
            )}
          </div>
        </div>
      )}

      {data.error ? (
        <p className="caption" style={{ padding: '20px 4px', color: 'var(--err)' }}>Erro ao carregar: {data.error}</p>
      ) : data.loading ? (
        <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>Carregando cadastro…</p>
      ) : !data.groups.length && !data.entries.length ? (
        <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>
          Nenhum agrupamento ainda. Crie um em “Novo agrupamento”, depois use “+ Adicionar produto”.
        </p>
      ) : (
        <>
          {gruposVisiveis.map((g) => {
            const members = filtrar(membersOf(g.group_id));
            const aberto = estaAberto(g.group_id);
            return (
              <div className="card cc-group-card" key={g.group_id} style={{ marginBottom: 10 }}>
                <div className="cc-group-head" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: aberto ? 8 : 0, flexWrap: 'wrap' }}>
                  {/* O nome INTEIRO é o botão, não só a setinha: é o alvo óbvio de clique e dá
                      uma área de toque decente. Os outros controles do cabeçalho ficam FORA
                      dele — aninhar botão em botão é HTML inválido e faz renomear/excluir
                      recolherem o cartão junto. Por isso não usamos <details>/<summary>. */}
                  <button type="button" className="cc-group-toggle" aria-expanded={aberto}
                          onClick={() => alternar(g.group_id)} disabled={buscando}
                          title={buscando ? 'Durante a busca os resultados ficam abertos'
                                          : (aberto ? 'Recolher' : 'Expandir')}>
                    <span className="cc-group-chevron" aria-hidden="true">{aberto ? '▾' : '▸'}</span>
                    <strong>{g.group_name}</strong>
                    <small className="pc-cap">
                      ({buscando ? `${members.length} de ${g.n_members}` : g.n_members})
                    </small>
                  </button>
                  <button type="button" className="seg-opt" disabled={locked}
                          onClick={() => renameGroup(g)} title="Renomear agrupamento">✎ Renomear</button>
                  <button type="button" className="seg-opt" disabled={locked || g.n_members > 0}
                          onClick={() => deleteGroup(g)}
                          title={g.n_members > 0 ? 'Reatribua ou remova os produtos antes de excluir' : 'Excluir agrupamento vazio'}>
                    🗑 Excluir
                  </button>
                  {/* Bulk per-agrupamento, one option group per axis. The option VALUE carries
                      the axis ('ingestao:pausada'), so the two can never be confused. */}
                  {g.n_members > 0 && (
                    <label className="caption" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      Aplicar a todos:
                      <select disabled={locked} defaultValue=""
                              aria-label={`Aplicar ciclo de vida a todos de ${g.group_name}`}
                              onChange={(ev) => {
                                const v = ev.target.value;
                                ev.target.value = '';
                                if (!v) return;
                                const [axis, value] = v.split(':');
                                setAxisForGroup(g, axis, value);
                              }}>
                        <option value="">escolha…</option>
                        <optgroup label="Ingestão">
                          {_CC_INGESTAO.map((o) => (
                            <option key={o.v} value={`ingestao:${o.v}`}>{o.label}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Exibição">
                          {_CC_VISIBILIDADE.map((o) => (
                            <option key={o.v} value={`visibilidade:${o.v}`}>{o.label}</option>
                          ))}
                        </optgroup>
                      </select>
                    </label>
                  )}
                </div>
                {/* Recolhido não renderiza a tabela — o custo de 234 linhas de <select> some
                    junto com a poluição visual, em vez de só ficar escondido por CSS. */}
                {aberto && (members.length ? memberRows(members) : (
                  <p className="caption" style={{ margin: '0 2px' }}>Agrupamento vazio — adicione produtos ou exclua-o.</p>
                ))}
              </div>
            );
          })}

          {buscando && !gruposVisiveis.length && !filtrar(strayEntries).length && (
            <p className="caption" style={{ padding: '28px 4px', textAlign: 'center' }}>
              Nenhum produto cadastrado combina com <strong>“{busca.trim()}”</strong>. Se ele
              deveria estar aqui, use “+ Adicionar produto”.
            </p>
          )}

          {filtrar(strayEntries).length > 0 && (
            <div className="card" style={{ marginBottom: 10, borderLeft: '4px solid var(--warn, #b8860b)' }}>
              <div className="cc-group-head" style={{ marginBottom: 8 }}>
                <strong>Sem agrupamento registrado <small className="pc-cap">({filtrar(strayEntries).length})</small></strong>
                <p className="caption" style={{ margin: '4px 0 0' }}>
                  Reatribua cada um a um agrupamento existente na coluna “Agrupamento”.
                </p>
              </div>
              {memberRows(filtrar(strayEntries))}
            </div>
          )}
        </>
      )}
    </>
  );
}

window.ViewCadastroProdutos = ViewCadastroProdutos;
