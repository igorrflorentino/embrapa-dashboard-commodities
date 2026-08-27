// MunicipioChoropleth — the intra-UF municipal choropleth: one state's municípios,
// shaded by the active metric. The finest geography the dashboard can draw, and the
// piece that makes a sub-UF filter finally VISIBLE — before this, narrowing to a
// mesorregião left BrazilChoropleth shading the whole state, unchanged
// (PLANS/geo_subregions.md, step 7).
//
//   <MunicipioChoropleth uf="PA" data valueKey label onSelect selectedCity/>
//   data = [{ cityCode, name, [valueKey] }]  (cityCode = the 7-digit IBGE code)
//
// Geometry is a vendored per-UF GeoJSON (frontend/public/geo/municipios/<UF>.json,
// ~7-69 KB gzipped) fetched on demand and cached per UF for the session. Deliberately
// NOT the whole-country municipal mesh: that is ~836 KB gzipped — heavier than
// maplibre itself — and 5570 polygons at country zoom are unreadable smudges.
//
// IBGE ships each feature with `codarea` = the 7-digit city code, which is already
// this project's join key end to end (dim_geo_municipio.city_code → /api/geo-mesh's
// cityCode → the /api/municipio-yearly cube), so no mapping table is involved.
//
// maplibre-gl is lazy-loaded, exactly as in BrazilChoropleth — the two share the
// scale/legend logic (choroplethScale.js) so the UF and município maps read alike.

import { useEffect, useMemo, useRef, useState } from 'react';

import { NODATA, fillColorExpression, ufColorScaleQuantile } from './choroplethScale';
import { sanitizeFeatureCollection } from './geoSanitize';

// uf -> Promise<FeatureCollection>. Module-level so switching away from a UF and back
// (or toggling metric) never refetches, and two mounts of this component share one
// in-flight request. A failed fetch is evicted so a later attempt can retry.
const MESH_CACHE = new Map();

export function loadMunicipioMesh(uf) {
  if (!uf) return Promise.resolve(null);
  if (MESH_CACHE.has(uf)) return MESH_CACHE.get(uf);
  const p = fetch(`/geo/municipios/${uf}.json`)
    .then((r) => {
      if (!r.ok) throw new Error(`malha municipal de ${uf}: HTTP ${r.status}`);
      return r.json();
    })
    // Same defensive pass the UF mesh gets: a malformed ring crashes maplibre's
    // geojson-vt worker and blanks the map rather than throwing where we can catch it.
    .then((fc) => sanitizeFeatureCollection(fc))
    .catch((err) => {
      MESH_CACHE.delete(uf);
      throw err;
    });
  MESH_CACHE.set(uf, p);
  return p;
}

function fmtCompact(v) {
  const mp = window.autoScaleNum && v ? window.autoScaleNum(v) : { factor: 1, suffix: '' };
  const s = v / mp.factor;
  const t = s.toLocaleString('pt-BR', { maximumFractionDigits: Math.abs(s) < 10 ? 1 : 0 });
  return mp.suffix ? `${t} ${mp.suffix}` : t;
}

export function MunicipioChoropleth({
  uf, data, valueKey, label, height = 420, onSelect, selectedCity, narrowed = false,
}) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  // One state object TAGGED with the UF it belongs to, rather than a mesh + an
  // effect that nulls it on every UF change: clearing state synchronously in an
  // effect body is a cascading render (and what react-hooks/set-state-in-effect
  // flags). Tagging lets the current UF's mesh be *derived* during render — a stale
  // UF's payload simply doesn't match and reads as "still loading".
  const [loaded, setLoaded] = useState({ uf: null, fc: null, error: null });
  const [layerReady, setLayerReady] = useState(false);
  const current = loaded.uf === uf ? loaded : { fc: null, error: null };
  const mesh = current.fc;
  const failed = current.error;

  // The SAME quantile classes + legend the UF choropleth uses. Municipal values are
  // even more concentrated than per-UF ones (measured 2024: the top 100 of 5570
  // municípios carry 71% of national value), so a linear ramp would be worse here
  // than it already was at UF grain.
  const scale = useMemo(() => {
    const rows = (data || []).map((d) => ({ uf: d.cityCode, [valueKey]: d[valueKey] }));
    return ufColorScaleQuantile(rows, valueKey);
  }, [data, valueKey]);

  // cityCode -> { name, value } for the hover popup, in a ref so the handlers
  // registered once always read current data.
  const lookupRef = useRef({});
  useEffect(() => {
    const idx = {};
    (data || []).forEach((d) => {
      // `city` is what the município rows carry (dataFilters/rankMunisFromCube);
      // `name` is accepted too so the component isn't bound to one row shape.
      idx[d.cityCode] = { name: d.name || d.city, value: Number(d[valueKey]) || 0, label };
    });
    lookupRef.current = idx;
  }, [data, valueKey, label]);

  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  // Fetch (or reuse) the UF's mesh. Guarded so a UF switch mid-flight doesn't paint
  // the previous state's polygons.
  useEffect(() => {
    let cancelled = false;
    if (!uf) return undefined;
    loadMunicipioMesh(uf)
      .then((fc) => { if (!cancelled) setLoaded({ uf, fc, error: null }); })
      .catch((err) => {
        console.error('[municipio-choropleth]', err);
        if (!cancelled) setLoaded({ uf, fc: null, error: 'Malha municipal indisponível para esta UF.' });
      });
    return () => { cancelled = true; };
  }, [uf]);

  // Create the map once the mesh is in hand (its bounds frame the view, so there is
  // nothing useful to show before that).
  useEffect(() => {
    if (!ref.current || !mesh) return undefined;
    let cancelled = false;
    let map = null;
    let popup = null;

    (async () => {
      let maplibregl;
      try {
        // Namespace import + bundled worker URL — same contract as BrazilChoropleth;
        // see the long note there for why `.default` and a plain `?url` both break.
        maplibregl = await import('maplibre-gl');
        await import('maplibre-gl/dist/maplibre-gl.css');
        maplibregl.setWorkerUrl(
          (await import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url')).default,
        );
      } catch (err) {
        console.error('[municipio-choropleth] maplibre failed to load:', err);
        if (!cancelled) setFailed('Mapa indisponível neste navegador.');
        return;
      }
      if (cancelled || !ref.current) return;

      try {
        map = new maplibregl.Map({
          container: ref.current,
          style: {
            version: 8,
            sources: {},
            layers: [{ id: 'bg', type: 'background', paint: { 'background-color': 'transparent' } }],
          },
          bounds: meshBounds(mesh),
          fitBoundsOptions: { padding: 16 },
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
        });
      } catch (err) {
        console.error('[municipio-choropleth] maplibre init failed:', err);
        if (!cancelled) setFailed('Mapa indisponível neste navegador.');
        return;
      }
      mapRef.current = map;
      map.on('error', (e) => {
        console.warn('[municipio-choropleth] maplibre error:', (e && e.error && e.error.message) || e);
      });
      map.touchZoomRotate.disableRotation();
      // Page scroll wins over map zoom, same as the UF map (MAPA-1).
      map.scrollZoom.disable();
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

      popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

      map.on('load', () => {
        if (cancelled) return;
        map.addSource('mun', { type: 'geojson', data: mesh });
        map.addLayer({ id: 'mun-fill', type: 'fill', source: 'mun', paint: { 'fill-color': NODATA, 'fill-opacity': 0.92 } });
        // Hairlines: at state zoom a 0.8px border (the UF map's) turns a dense UF like
        // MG into a grey mesh where the fill barely shows.
        map.addLayer({ id: 'mun-line', type: 'line', source: 'mun', paint: { 'line-color': '#ffffff', 'line-width': 0.35 } });
        map.addLayer({
          id: 'mun-selected', type: 'line', source: 'mun',
          filter: ['==', ['get', 'codarea'], '__none__'],
          paint: { 'line-color': 'var(--embrapa-green-darker, #003c1d)', 'line-width': 2 },
        });
        setLayerReady(true);
        map.on('mousemove', 'mun-fill', onMove);
        map.on('mouseleave', 'mun-fill', onLeave);
        map.on('click', 'mun-fill', onClick);
      });

      function onMove(e) {
        map.getCanvas().style.cursor = onSelectRef.current ? 'pointer' : 'default';
        const f = e.features && e.features[0];
        if (!f) return;
        const code = f.properties.codarea;
        const hit = lookupRef.current[code];
        // A município with no row is genuinely "sem produção registrada" — say so,
        // rather than showing a bare dash the reader has to interpret.
        const name = (hit && hit.name) || code;
        const body = hit
          ? `${fmtCompact(hit.value)} ${(hit.label || '')}`
          : 'sem produção registrada';
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="max-width:200px;overflow-wrap:anywhere">` +
              `<div style="font:600 12px var(--font-body,sans-serif)">${name}</div>` +
              `<div style="font:11px var(--font-body,sans-serif);color:#555">${body}</div>` +
            `</div>`,
          )
          .addTo(map);
      }
      function onLeave() {
        map.getCanvas().style.cursor = '';
        popup.remove();
      }
      function onClick(e) {
        const f = e.features && e.features[0];
        const code = f && f.properties && f.properties.codarea;
        if (code && onSelectRef.current) onSelectRef.current(code);
      }
    })();

    return () => {
      cancelled = true;
      setLayerReady(false);
      if (popup) popup.remove();
      if (map) map.remove();
      mapRef.current = null;
    };
  }, [mesh]);

  // Repaint on data/metric/selection change (no map rebuild).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || typeof map.getLayer !== 'function') return;
    const paint = () => {
      const notReady =
        (typeof map.isStyleLoaded === 'function' && !map.isStyleLoaded()) || !map.getLayer('mun-fill');
      if (notReady) {
        if (typeof map.once === 'function') map.once('idle', paint);
        return;
      }
      try {
        // 'codarea' — IBGE's property name for the 7-digit city code on these meshes
        // (the UF mesh keys on 'uf', which is fillColorExpression's default).
        map.setPaintProperty('mun-fill', 'fill-color', fillColorExpression(scale.byUf, NODATA, 'codarea'));
        if (typeof map.setFilter === 'function' && map.getLayer('mun-selected')) {
          map.setFilter('mun-selected', ['==', ['get', 'codarea'], selectedCity || '__none__']);
        }
      } catch (err) {
        console.error('[municipio-choropleth] paint failed:', err);
        try { map.setPaintProperty('mun-fill', 'fill-color', NODATA); } catch { /* best effort */ }
      }
    };
    paint();
  }, [scale, selectedCity, layerReady]);

  if (failed) {
    return (
      <div style={{ width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="caption" style={{ color: 'var(--fg-3)' }}>{failed}</span>
      </div>
    );
  }
  if (!mesh) {
    return (
      <div style={{ width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="caption" style={{ color: 'var(--fg-3)' }}>Carregando a malha municipal…</span>
      </div>
    );
  }

  const legend = scale.thresholds;
  const hasLegend = legend.some(Boolean);
  const semDado = (data || []).length
    ? (mesh.features || []).length - (data || []).filter((d) => (d[valueKey] || 0) > 0).length
    : (mesh.features || []).length;
  return (
    <div className="bmap-wrap">
      <div className="br-choropleth" style={{ position: 'relative', width: '100%', height }}>
        <div ref={ref} style={{ position: 'absolute', inset: 0, borderRadius: 8, overflow: 'hidden' }} />
      </div>
      {hasLegend && (
        <div className="bmap-legend">
          <span className="caption">{label}</span>
          <div className="bmap-scale">
            {legend.map((t, i) => (
              <span
                key={i}
                style={{ background: t ? t.color : NODATA }}
                title={t ? `${fmtCompact(t.min)} – ${fmtCompact(t.max)}` : 'sem município nesta faixa'}
              />
            ))}
          </div>
          <span className="caption tnum">
            {fmtCompact(legend.find(Boolean)?.min ?? 0)} – {fmtCompact([...legend].reverse().find(Boolean)?.max ?? 0)}
          </span>
        </div>
      )}
      {/* Roughly half the municípios of a producing UF have no row in a given year
          (measured 2024, Brasil: 2.983 de 5.570). Saying how many are grey keeps an
          honest map from reading as a broken one — but the REASON differs: with a
          sub-UF/município facet active the greys are simply outside the selection,
          and calling those "sem produção" would assert something the data never said. */}
      {semDado > 0 && (
        <p className="caption" style={{ padding: '0 4px', color: 'var(--fg-3)' }}>
          {narrowed
            ? `${semDado} ${semDado === 1 ? 'município fora do recorte' : 'municípios fora do recorte'} — em cinza.`
            : `${semDado} ${semDado === 1 ? 'município sem produção registrada' : 'municípios sem produção registrada'} no período — em cinza.`}
        </p>
      )}
    </div>
  );
}

/** [[minLng, minLat], [maxLng, maxLat]] over a FeatureCollection, for the initial fit. */
export function meshBounds(fc) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const walk = (c) => {
    if (typeof c[0] === 'number') {
      if (c[0] < minX) minX = c[0];
      if (c[0] > maxX) maxX = c[0];
      if (c[1] < minY) minY = c[1];
      if (c[1] > maxY) maxY = c[1];
      return;
    }
    c.forEach(walk);
  };
  (fc.features || []).forEach((f) => f.geometry && walk(f.geometry.coordinates));
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : [[-74, -34], [-33, 6]];
}

window.MunicipioChoropleth = MunicipioChoropleth;
export default MunicipioChoropleth;
