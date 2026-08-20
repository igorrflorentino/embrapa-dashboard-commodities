// Donut — share-of-total ring + HTML legend. Kept as SVG (a categorical share
// display gains nothing from zoom/pan; this is pixel-perfect to the design
// system). Faithful port of the prototype's Donut. Same name + props.
//   data: [{ name, color, [valueKey] }]  (valueKey is a fraction 0-1)

// Slice geometry, pure and OUTSIDE any component. The running total it needs is a
// mutable accumulator, which react-hooks/immutability rightly refuses inside a render
// body; a module-scope helper is both allowed and independently testable.
// Returns [{ full, d, fill }] in input order.
// Coerce each datum's value (Number(…) || 0) so a missing/non-numeric valueKey can't
// produce NaN% slices, a blank ring, or a "NaN%" legend row.
const sliceValue = (d, valueKey) => Number(d[valueKey]) || 0;

export function donutSlices(data, valueKey, r, ir) {
  const val = (d) => sliceValue(d, valueKey);
  const total = data.reduce((s, d) => s + val(d), 0) || 1;
  let acc = 0;
  return data.map((d) => {
    const start = acc / total;
    acc += val(d);
    const end = acc / total;
    const a0 = start * Math.PI * 2 - Math.PI / 2;
    const a1 = end * Math.PI * 2 - Math.PI / 2;
    const large = end - start > 0.5 ? 1 : 0;
    const x0 = r + r * Math.cos(a0);
    const y0 = r + r * Math.sin(a0);
    const x1 = r + r * Math.cos(a1);
    const y1 = r + r * Math.sin(a1);
    const xi0 = r + ir * Math.cos(a0);
    const yi0 = r + ir * Math.sin(a0);
    const xi1 = r + ir * Math.cos(a1);
    const yi1 = r + ir * Math.sin(a1);
    return {
      // A slice spanning the whole circle (e.g. a single 100% product) has coincident
      // arc endpoints, so the SVG <path> is zero-length and renders nothing (a blank
      // ring). Flag it and draw a full <circle> instead; the inner white circle below
      // still punches the donut hole. Covers the common single-product selection.
      full: end - start >= 0.9999,
      d: `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} L ${xi1} ${yi1} A ${ir} ${ir} 0 ${large} 0 ${xi0} ${yi0} Z`,
      fill: d.color || 'var(--viz-1)',
    };
  });
}

function Donut({ data = [], size = 160, valueKey = 'share' }) {
  const r = size / 2;
  const ir = r * 0.62;
  const slices = donutSlices(data, valueKey, r, ir);

  return (
    <div className="donut-wrap">
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        {slices.map((s, i) => (
          s.full
            ? <circle key={i} cx={r} cy={r} r={r} fill={s.fill} />
            : <path key={i} d={s.d} fill={s.fill} />
        ))}
        <circle cx={r} cy={r} r={ir - 2} fill="#fff" />
      </svg>
      <ul className="donut-legend">
        {data.map((d, i) => (
          <li key={i}>
            <span className="ldot" style={{ background: d.color }}></span>
            <span className="lname">{d.name}</span>
            <span className="lval tnum">{(sliceValue(d, valueKey) * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

window.Donut = Donut;
export default Donut;
