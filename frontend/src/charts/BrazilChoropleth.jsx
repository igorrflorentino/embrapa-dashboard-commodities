// BrazilChoropleth — an interactive geographic choropleth of Brazil's 27 UFs,
// shaded by the active metric. Real state shapes (vs the tile grid), with
// pan/zoom/hover via maplibre-gl over our own GeoJSON (no basemap tiles, so it
// works offline). Same call shape as BrazilTileMap: <BrazilChoropleth data
// valueKey label/>, data = [{ uf, name, [valueKey] }] (uf = 2-letter sigla).
//
// maplibre-gl (~250KB gz) is LAZY-loaded via dynamic import() on mount, so it's
// fetched only when a researcher actually opens this map — not on first paint of
// the app. Vite code-splits it into its own chunk.

import { useRef, useEffect, useState } from 'react';

import brazilUfGeo from './brazilUfGeo';
import { NODATA, fillColorExpression, ufColorScale } from './choroplethScale';
import { sanitizeFeatureCollection } from './geoSanitize';

// brazilUfGeo ships empty `[]` sub-polygons that crash maplibre's geojson-vt worker
// and blank the map (FINDING #5); sanitize once at module load into valid GeoJSON.
const UF_GEO = sanitizeFeatureCollection(brazilUfGeo);

const BRAZIL_BOUNDS = [
  [-74.5, -34.5],
  [-33.5, 6.5],
];

export function BrazilChoropleth({ data, valueKey, label, height = 360 }) {
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
        maplibregl = (await import('maplibre-gl')).default;
        await import('maplibre-gl/dist/maplibre-gl.css');
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
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

      popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

      map.on('load', () => {
        if (cancelled) return;
        map.addSource('uf', { type: 'geojson', data: UF_GEO });
        map.addLayer({ id: 'uf-fill', type: 'fill', source: 'uf', paint: { 'fill-color': NODATA, 'fill-opacity': 0.9 } });
        map.addLayer({ id: 'uf-line', type: 'line', source: 'uf', paint: { 'line-color': '#ffffff', 'line-width': 0.8 } });
        // Signal readiness rather than paint()ing here: this callback's `data` is frozen
        // at the first render (see layerReady).
        setLayerReady(true);
        map.on('mousemove', 'uf-fill', onMove);
        map.on('mouseleave', 'uf-fill', onLeave);
      });

      function onMove(e) {
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features && e.features[0];
        if (!f) return;
        const uf = f.properties.uf;
        const hit = lookupRef.current[uf];
        // Compact per-value magnitude (e.g. "2,9 bi") — matches the tile-map + legend, so
        // toggling Mapa/Blocos shows the same readable format instead of a long raw number.
        const fmtCompact = (v) => {
          const mp = window.autoScaleNum && v ? window.autoScaleNum(v) : { factor: 1, suffix: '' };
          const s = v / mp.factor;
          const t = s.toLocaleString('pt-BR', { maximumFractionDigits: Math.abs(s) < 10 ? 1 : 0 });
          return mp.suffix ? `${t} ${mp.suffix}` : t;
        };
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
      const { byUf } = ufColorScale(data, valueKey);
      map.setPaintProperty('uf-fill', 'fill-color', fillColorExpression(byUf));
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
  // it would repaint on every render); the values it actually reads — data, valueKey and
  // layerReady — are all here, which is what matters. layerReady is the one this effect
  // was missing: without it the effect never re-ran after the layer appeared.
  useEffect(() => {
    paint();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, valueKey, layerReady]);

  if (failed) {
    return (
      <div style={{ width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="caption" style={{ color: 'var(--fg-3)' }}>
          Mapa indisponível neste navegador.
        </span>
      </div>
    );
  }
  return (
    <div className="br-choropleth" style={{ position: 'relative', width: '100%', height }}>
      <div ref={ref} style={{ position: 'absolute', inset: 0, borderRadius: 8, overflow: 'hidden' }} />
    </div>
  );
}

window.BrazilChoropleth = BrazilChoropleth;
