// BrazilChoropleth — an interactive geographic choropleth of Brazil's 27 UFs,
// shaded by the active metric. Real state shapes (vs the tile grid), with
// pan/zoom/hover via maplibre-gl over our own GeoJSON (no basemap tiles, so it
// works offline). Same call shape as BrazilTileMap: <BrazilChoropleth data
// valueKey label onSelect selectedUf/>, data = [{ uf, name, [valueKey] }] (uf =
// 2-letter sigla). `onSelect(uf)` fires on a state click (filter-by-click);
// `selectedUf` highlights the active selection and re-frames the view to it.
//
// maplibre-gl (~250KB gz) is LAZY-loaded via dynamic import() on mount, so it's
// fetched only when a researcher actually opens this map — not on first paint of
// the app. Vite code-splits it into its own chunk.

import { useEffect, useMemo, useRef, useState } from 'react';

import brazilUfGeo from './brazilUfGeo';
import { NODATA, fillColorExpression, ufColorScaleQuantile } from './choroplethScale';
import { sanitizeFeatureCollection } from './geoSanitize';

// brazilUfGeo ships empty `[]` sub-polygons that crash maplibre's geojson-vt worker
// and blank the map (FINDING #5); sanitize once at module load into valid GeoJSON.
const UF_GEO = sanitizeFeatureCollection(brazilUfGeo);

const BRAZIL_BOUNDS = [
  [-74.5, -34.5],
  [-33.5, 6.5],
];

// Per-UF bounding box (computed once from the SAME sanitized GeoJSON the map
// renders), so clicking a state can fit the view to it without a second data
// source. Handles both Polygon and MultiPolygon coordinate nesting.
function bboxOfFeature(feature) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const walk = (coords) => {
    if (typeof coords[0] === 'number') {
      const [x, y] = coords;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      return;
    }
    coords.forEach(walk);
  };
  walk(feature.geometry.coordinates);
  return [[minX, minY], [maxX, maxY]];
}
const UF_BOUNDS = {};
UF_GEO.features.forEach((f) => {
  if (f.properties && f.properties.uf) UF_BOUNDS[f.properties.uf] = bboxOfFeature(f);
});

// Per-value compact magnitude (e.g. 2_900_918_362 → "2,9 bi") — shared by the
// hover popup AND the legend, so both read the same format the tile map/legend
// use elsewhere in Geografia.
function fmtCompact(v) {
  const mp = window.autoScaleNum && v ? window.autoScaleNum(v) : { factor: 1, suffix: '' };
  const s = v / mp.factor;
  const t = s.toLocaleString('pt-BR', { maximumFractionDigits: Math.abs(s) < 10 ? 1 : 0 });
  return mp.suffix ? `${t} ${mp.suffix}` : t;
}

// A maplibre IControl (plain duck-typed interface — no maplibre import needed)
// that re-frames the map to all of Brazil. maplibre's own NavigationControl only
// offers +/-; without this, a researcher who scrolled or clicked into a single UF
// had no button-driven way back to the national view.
class ResetViewControl {
  constructor(onClick) {
    this._onClick = onClick;
  }
  onAdd() {
    const div = document.createElement('div');
    div.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'maplibregl-ctrl-icon';
    btn.title = 'Ajustar ao Brasil';
    btn.setAttribute('aria-label', 'Ajustar mapa ao Brasil');
    btn.style.fontSize = '15px';
    btn.style.lineHeight = '1';
    btn.textContent = '⤢';
    btn.addEventListener('click', () => this._onClick());
    div.appendChild(btn);
    this._container = div;
    return div;
  }
  onRemove() {
    if (this._container && this._container.parentNode) this._container.parentNode.removeChild(this._container);
  }
}

export function BrazilChoropleth({ data, valueKey, label, height = 360, onSelect, selectedUf }) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  const [failed, setFailed] = useState(false);
  // TRUE once map.on('load') has added the 'uf-fill' layer. It is a dependency of the
  // paint effect, not just a flag: the load callback is created on the FIRST render and
  // closes over that render's (empty) `data`, so calling paint() from inside it painted
  // the no-data grey and nothing re-ran it — the choropleth stayed colourless until the
  // researcher happened to change a metric, which re-fired the effect with the layer now
  // present. Flipping state instead lets the effect below repaint with CURRENT data.
  // (The hover path already dodged the same stale closure via lookupRef.)
  const [layerReady, setLayerReady] = useState(false);

  // MAPA-3: quantile bins instead of a linear share of the max — a linear scale
  // collapses whenever a couple of UFs dominate the total (measured: 23 of 27
  // states landing in the SAME lightest bucket for PEVS 2024). Computed once here
  // so BOTH paint() and the legend render from the identical bucket assignment.
  const scale = useMemo(() => ufColorScaleQuantile(data, valueKey), [data, valueKey]);

  // uf -> { name, value, label } for the hover popup, kept in a ref so the map's
  // event handlers always read the latest data without re-binding listeners.
  const lookupRef = useRef({});
  useEffect(() => {
    const idx = {};
    (data || []).forEach((d) => {
      idx[d.uf] = { name: d.name, value: Number(d[valueKey]) || 0, label };
    });
    lookupRef.current = idx;
  }, [data, valueKey, label]);

  // onSelect is a fresh closure every render (it captures the current filter
  // state in ViewGeography); kept in a ref so the click handler registered ONCE
  // on the map always calls the CURRENT one, never the one from first mount.
  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  // Create the map once (lazy-loading maplibre). Guarded so an unmount mid-load
  // doesn't init a detached map or setState after teardown.
  useEffect(() => {
    if (!ref.current) return undefined;
    let cancelled = false;
    let map = null;
    let popup = null;

    (async () => {
      let maplibregl;
      try {
        // NAMESPACE import, never `.default`. maplibre 5+ ships pure ESM with ~85 NAMED
        // exports and NO default, so `(await import(…)).default` is undefined and
        // `maplibregl.Map` throws "Cannot read properties of undefined (reading 'Map')".
        // What makes that trap nasty is that it fails ONLY in the build: with nothing but a
        // non-existent export referenced, Rollup tree-shakes the whole library away (the
        // chunk collapsed 786 kB → 514 bytes) while the dev server, which serves modules
        // directly, kept rendering fine. That is exactly how the first 4→6 attempt passed
        // tests, lint and `vite build` and still broke production (see v1.24.22).
        maplibregl = await import('maplibre-gl');
        await import('maplibre-gl/dist/maplibre-gl.css');
        // maplibre 5+ runs geojson-vt in a MODULE WORKER shipped as a separate file, and
        // resolves it at runtime as a sibling of its own `import.meta.url`. That URL is
        // invisible to the bundler, so Vite never emitted the file: the request fell through
        // to the SPA's index.html fallback and died on strict MIME checking. The worker then
        // never started, so no source ever finished loading — `isStyleLoaded()` and
        // `loaded()` stayed false forever and NO 'idle' event ever fired.
        // `?worker&url` makes Vite BUNDLE the worker and hand back its URL. It has to be
        // `?worker&url`, not a plain `?url`: the published worker is an ES module that
        // imports a sibling, `./maplibre-gl-shared.mjs`. A plain `?url` copies that one file
        // verbatim, so the relative import resolves to an asset Vite never emitted and the
        // module worker dies on load. `?worker&url` follows the import graph and emits one
        // self-contained worker instead.
        // `setWorkerUrl` is maplibre's supported override (it takes priority over the
        // import.meta.url guess) and must run BEFORE the first `new Map()`, which is what
        // spins up the worker pool.
        maplibregl.setWorkerUrl(
          (await import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url')).default,
        );
      } catch (err) {
        console.error('[choropleth] maplibre failed to load:', err);
        if (!cancelled) setFailed(true);
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
          bounds: BRAZIL_BOUNDS,
          fitBoundsOptions: { padding: 12 },
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
        });
      } catch (err) {
        // No WebGL (headless / unsupported) — degrade instead of crashing the view.
        console.error('[choropleth] maplibre init failed:', err);
        if (!cancelled) setFailed(true);
        return;
      }
      mapRef.current = map;
      // Surface any maplibre-internal error under our own prefix (maplibre's default
      // handler logs a stackless console.error) — diagnostic only, never blanks the map.
      map.on('error', (e) => {
        console.warn('[choropleth] maplibre error:', (e && e.error && e.error.message) || e);
      });
      map.touchZoomRotate.disableRotation();
      // MAPA-1: scroll-zoom was ON by default, so scrolling the PAGE past the map
      // zoomed the MAP instead — confirmed in the production build (three scrolls
      // shrank Brazil to a third of the frame with no way back except the +/-
      // buttons). Pinch-zoom (touch) and the +/- buttons still work; the
      // ResetViewControl below is the way back to the national view.
      map.scrollZoom.disable();
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(new ResetViewControl(() => map.fitBounds(BRAZIL_BOUNDS, { padding: 24, duration: 400 })), 'top-right');

      popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

      map.on('load', () => {
        if (cancelled) return;
        map.addSource('uf', { type: 'geojson', data: UF_GEO });
        map.addLayer({ id: 'uf-fill', type: 'fill', source: 'uf', paint: { 'fill-color': NODATA, 'fill-opacity': 0.9 } });
        map.addLayer({ id: 'uf-line', type: 'line', source: 'uf', paint: { 'line-color': '#ffffff', 'line-width': 0.8 } });
        // A dedicated highlight layer for the active click-to-filter selection —
        // starts filtered to nothing; the paint effect below sets its filter to the
        // selected UF (or back to nothing) whenever `selectedUf` changes.
        map.addLayer({
          id: 'uf-selected', type: 'line', source: 'uf',
          filter: ['==', ['get', 'uf'], '__none__'],
          paint: { 'line-color': 'var(--embrapa-green-darker, #003c1d)', 'line-width': 2.5 },
        });
        // Signal readiness rather than paint()ing here: this callback's `data` is frozen
        // at the first render (see layerReady).
        setLayerReady(true);
        map.on('mousemove', 'uf-fill', onMove);
        map.on('mouseleave', 'uf-fill', onLeave);
        map.on('click', 'uf-fill', onClick);
      });

      function onMove(e) {
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features && e.features[0];
        if (!f) return;
        const uf = f.properties.uf;
        const hit = lookupRef.current[uf];
        const val = hit ? fmtCompact(hit.value) : '—';
        const name = (hit && hit.name) || f.properties.name || uf;
        const unit = (hit && hit.label) || '';
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            // max-width + word-wrap so a long UF name ("Rio Grande do Sul") can't
            // stretch the popup past a narrow/mobile map edge (audit POPUP-1, defensive).
            `<div style="max-width:180px;overflow-wrap:anywhere">` +
              `<div style="font:600 12px var(--font-body,sans-serif)">${uf} · ${name}</div>` +
              `<div style="font:11px var(--font-body,sans-serif);color:#555">${val} ${unit}</div>` +
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
        const uf = f && f.properties && f.properties.uf;
        if (uf && onSelectRef.current) onSelectRef.current(uf);
      }
    })();

    return () => {
      cancelled = true;
      if (popup) popup.remove();
      if (map) map.remove();
      mapRef.current = null;
    };
    // No suppression needed any more: this effect used to call paint() — a value it did
    // not declare — and the disable comment hid that. It now only flips layerReady, whose
    // setter React guarantees stable, so the empty dependency list is genuinely correct.
  }, []);

  // Re-paint when the data / metric changes (no map rebuild). Guarded so it is a
  // no-op until the map AND its style/layer exist (the data-effect can fire on the
  // first render, before the async map.on('load') has added 'uf-fill'), and so a
  // malformed paint expression degrades to the no-data fill instead of throwing
  // "Cannot read properties of undefined (reading 'length')" up to the view and
  // blanking the choropleth without the WebGL fallback (FINDING #5).
  function paint() {
    const map = mapRef.current;
    if (!map || typeof map.getLayer !== 'function') return;
    // DEFER, don't give up. These two conditions are transient — the style is still
    // settling right after addSource/addLayer, and 'uf-fill' does not exist until the
    // async load handler runs. Returning silently (what this used to do) made every such
    // moment PERMANENT: nothing re-ran paint, so the map kept the no-data grey until the
    // researcher happened to change a metric, which re-fired the effect once everything
    // had settled. That workaround was the only reason the map ever showed colour.
    // 'idle' fires when the map has finished loading and rendering, and `once` removes
    // itself, so this retries exactly as often as needed and never stacks handlers.
    const notReady =
      (typeof map.isStyleLoaded === 'function' && !map.isStyleLoaded()) ||
      !map.getLayer('uf-fill');
    if (notReady) {
      if (typeof map.once === 'function') map.once('idle', paint);
      return;
    }
    try {
      map.setPaintProperty('uf-fill', 'fill-color', fillColorExpression(scale.byUf));
      if (typeof map.setFilter === 'function' && map.getLayer('uf-selected')) {
        map.setFilter('uf-selected', ['==', ['get', 'uf'], selectedUf || '__none__']);
      }
    } catch (err) {
      console.error('[choropleth] paint failed; falling back to no-data fill:', err);
      try {
        map.setPaintProperty('uf-fill', 'fill-color', NODATA);
      } catch {
        /* best effort — the style may be unusable; leave the existing fill */
      }
    }
  }
  // `paint` is re-created every render, so it stays OUT of the dependency list (listing
  // it would repaint on every render); the values it actually reads — scale, selectedUf
  // and layerReady — are all here, which is what matters. layerReady is the one this
  // effect was missing: without it the effect never re-ran after the layer appeared.
  useEffect(() => {
    paint();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scale, selectedUf, layerReady]);

  // Re-frame the viewport to the active selection (or back to all of Brazil once
  // cleared). A no-op until the map has actually loaded; harmless to also fire once
  // on mount with no selection — it re-asserts the SAME bounds the map already
  // opened with, so there's nothing to visibly animate.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !layerReady || typeof map.fitBounds !== 'function') return;
    const bounds = (selectedUf && UF_BOUNDS[selectedUf]) || BRAZIL_BOUNDS;
    map.fitBounds(bounds, { padding: 32, duration: 500 });
  }, [selectedUf, layerReady]);

  if (failed) {
    return (
      <div style={{ width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="caption" style={{ color: 'var(--fg-3)' }}>
          Mapa indisponível neste navegador.
        </span>
      </div>
    );
  }
  const legend = scale.thresholds;
  const hasLegend = legend.some(Boolean);
  return (
    <div className="bmap-wrap">
      <div className="br-choropleth" style={{ position: 'relative', width: '100%', height }}>
        <div ref={ref} style={{ position: 'absolute', inset: 0, borderRadius: 8, overflow: 'hidden' }} />
      </div>
      {/* MAPA-2: "Mapa" (this component) had no legend at all — "Blocos" (the tile
          map) did. Reusing .bmap-legend/.bmap-scale gives both visualizations the
          SAME legend chrome, so toggling between them doesn't lose the scale. */}
      {hasLegend && (
        <div className="bmap-legend">
          <span className="caption">{label}</span>
          <div className="bmap-scale">
            {legend.map((t, i) => (
              <span
                key={i}
                style={{ background: t ? t.color : NODATA }}
                title={t ? `${fmtCompact(t.min)} – ${fmtCompact(t.max)}` : 'sem UF nesta faixa'}
              />
            ))}
          </div>
          <span className="caption tnum">
            {fmtCompact(legend.find(Boolean)?.min ?? 0)} – {fmtCompact([...legend].reverse().find(Boolean)?.max ?? 0)}
          </span>
        </div>
      )}
    </div>
  );
}

window.BrazilChoropleth = BrazilChoropleth;
