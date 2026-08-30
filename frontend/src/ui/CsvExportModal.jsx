// CsvExportModal — confirmação antes do download do CSV.
//
// O objetivo é o pesquisador saber, ANTES de escolher onde salvar, se o arquivo é mesmo o
// que ele espera. Por isso a janela não descreve o export em termos genéricos: ela mostra
// o que foi de fato montado — o nome do arquivo, o assunto, as colunas exatas, a contagem
// de linhas e o tamanho — a partir do MESMO objeto que o "Baixar" vai escrever. Nada aqui
// é recalculado: `preview.baixar()` grava a string já pronta.
//
// O recorte e as convenções vêm dos mesmos resolvedores que desenham as duas faixas na
// tela (`window.activeFilterChips`), e não de uma segunda leitura do estado: uma janela que
// dissesse o recorte com uma regra própria poderia contradizer a faixa logo acima dela.

function CsvExportModal({ preview, chips, conventions, onClose }) {
  const fecharComEsc = React.useCallback((e) => { if (e.key === 'Escape') onClose(); }, [onClose]);
  React.useEffect(() => {
    document.addEventListener('keydown', fecharComEsc);
    return () => document.removeEventListener('keydown', fecharComEsc);
  }, [fecharComEsc]);

  if (!preview) return null;

  // Um erro aqui não é exceção: é o caso normal de "não há o que baixar neste recorte".
  // Dizer isso é mais útil que um botão que não faz nada (o comportamento anterior era
  // apenas um console.warn, invisível para quem usa).
  if (preview.erro) {
    const msg = preview.motivo === 'sem-linhas'
      ? 'O recorte atual não deixou nenhuma linha. Amplie o período, os produtos ou a geografia e tente de novo.'
      : `O banco ${preview.banco} ainda não está liberado, então não há dados para baixar.`;
    return (
      <div className="cite-backdrop" onClick={onClose}>
        <div className="cite-modal csv-modal" onClick={(e) => e.stopPropagation()}
             role="alertdialog" aria-modal="true" aria-labelledby="csv-title">
          <header className="cite-head">
            <div>
              <div className="overline">Exportação</div>
              <h2 id="csv-title">Nada para baixar</h2>
              <p className="caption">{msg}</p>
            </div>
            <button className="fm-close" onClick={onClose} aria-label="Fechar">
              <window.Icon name="close" size={18}/>
            </button>
          </header>
          <div className="csv-foot">
            <button type="button" className="btn-secondary" onClick={onClose}>Entendi</button>
          </div>
        </div>
      </div>
    );
  }

  const conv = conventions || {};
  const unidades = Object.values(conv.units || {}).filter(Boolean).join(' · ');
  const convChips = [
    conv.currency && { k: 'Moeda', v: conv.currency },
    conv.correction && { k: 'Correção', v: conv.correction === 'Nominal' ? 'Sem correção' : conv.correction },
    unidades && { k: 'Unidades', v: unidades },
  ].filter(Boolean);

  return (
    <div className="cite-backdrop" onClick={onClose}>
      <div className="cite-modal csv-modal" onClick={(e) => e.stopPropagation()}
           role="dialog" aria-modal="true" aria-labelledby="csv-title">
        <header className="cite-head">
          <div>
            <div className="overline">Exportação</div>
            <h2 id="csv-title">Confira antes de baixar</h2>
            <p className="caption">
              Isto é <strong>exatamente</strong> o que o arquivo vai conter — o recorte e as
              convenções ativos já estão aplicados. Nada é recalculado no download.
            </p>
          </div>
          <button className="fm-close" onClick={onClose} aria-label="Fechar">
            <window.Icon name="close" size={18}/>
          </button>
        </header>

        <div className="cite-body csv-body">
          {/* O que salta aos olhos primeiro é o que o pesquisador confere primeiro: o
              tamanho do que vem. Um "3 linhas" onde ele esperava milhares responde a
              pergunta antes de qualquer outra leitura. */}
          <div className="csv-numeros">
            <div className="csv-num">
              <span className="csv-num-v">{preview.linhas.toLocaleString('pt-BR')}</span>
              <span className="csv-num-k">linha{preview.linhas === 1 ? '' : 's'}</span>
            </div>
            <div className="csv-num">
              <span className="csv-num-v">{preview.colunas.length}</span>
              <span className="csv-num-k">coluna{preview.colunas.length === 1 ? '' : 's'}</span>
            </div>
            <div className="csv-num">
              <span className="csv-num-v">{_csvTamanho(preview.bytes)}</span>
              <span className="csv-num-k">tamanho</span>
            </div>
          </div>

          <dl className="csv-lista">
            <div><dt>Conteúdo</dt><dd>{preview.assunto}</dd></div>
            <div><dt>Banco</dt><dd>{preview.banco}</dd></div>
            <div>
              <dt>Arquivo</dt>
              <dd><code className="csv-arquivo">{preview.arquivo}</code></dd>
            </div>
          </dl>

          {/* As colunas são a resposta mais concreta a "é isto que eu espero?" — quem baixa
              para planilha quer saber se `valor_BRL` ou `valor_USD` vem no arquivo. */}
          <section className="csv-secao">
            <h3 className="csv-h">Colunas do arquivo</h3>
            <div className="csv-colunas">
              {preview.colunas.map((c) => <code key={c} className="csv-col">{c}</code>)}
            </div>
          </section>

          {chips && chips.length > 0 && (
            <section className="csv-secao">
              <h3 className="csv-h">Recorte aplicado</h3>
              <div className="csv-chips">
                {chips.map((c, i) => (
                  <span key={i} className="fm-chip-filter">
                    <span className="fm-chip-k">{c.k}</span>{c.v}
                  </span>
                ))}
              </div>
            </section>
          )}

          {convChips.length > 0 && (
            <section className="csv-secao">
              <h3 className="csv-h">Convenções métricas</h3>
              <div className="csv-chips">
                {convChips.map((c, i) => (
                  <span key={i} className="fm-chip-filter">
                    <span className="fm-chip-k">{c.k}</span>{c.v}
                  </span>
                ))}
              </div>
            </section>
          )}

          <p className="caption csv-nota">
            Separador <strong>;</strong> e codificação <strong>UTF-8 com BOM</strong> — abre
            direto no Excel em português. O navegador perguntará onde salvar.
          </p>
        </div>

        <div className="csv-foot">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn-primary csv-baixar"
                  onClick={() => { preview.baixar(); onClose(); }}>
            <window.Icon name="download" size={16}/>
            Baixar {preview.arquivo.endsWith('.csv') ? 'CSV' : 'arquivo'}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Tamanho legível. Bytes reais da string montada, não estimativa. */
function _csvTamanho(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}

window.CsvExportModal = CsvExportModal;
window._csvTamanho = _csvTamanho;
