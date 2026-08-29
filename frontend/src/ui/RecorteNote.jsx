// RecorteNote — states the active sub-UF recorte directly above the territorial cards.
//
// A meso/micro/intermediária/imediata narrowing restricts the data to a FRACTION of one
// state WITHOUT removing that state from the selection, so every UF row still carries
// the state's name while carrying only part of its production: "Pará · R$ 655 mi" for
// what is really the Marajó. The filter chip and the ABNT citation now name the recorte
// for the panel (v1.33.28), but those sit in the chrome — a reader looking at the map
// reads the map. This puts the same sentence where the numbers are.
//
// One component, three views, so the three cannot describe one recorte three ways.
// Renders nothing when nothing narrows.

function RecorteNote({ recorte }) {
  if (!recorte) return null;
  return (
    <div className="card subtle" style={{ marginBottom: 12 }}>
      <p className="caption" style={{ padding: '10px 12px' }}>
        Recorte territorial ativo: <strong>{recorte}</strong>. Os valores por UF abaixo
        somam <strong>apenas</strong> os municípios desse recorte — não a produção
        completa do estado.
      </p>
    </div>
  );
}

window.RecorteNote = RecorteNote;
export default RecorteNote;
