/* The chart. It draws what the build told it and works nothing out for itself:
   every position, tier and note in the data was resolved offline in Python.

   No third-party tiles, no API, no network beyond this folder. The only
   dependency is vendor/maplibre-gl.js, which is here rather than on a CDN so
   that moving hosts stays a file copy. */
'use strict';

const PALETTE = {
  water: '#E7F1F5', shoal1: '#CDE3EE', shoal2: '#B2D3E6',
  land: '#F0E2C2', landEdge: '#8A7F6A', ink: '#2E3A42', inkSoft: '#5C6B75',
};

// Which band serves which zooms. The coarse band is 138 KB and the fine one
// 1.2 MB, so the fine one is only asked for once somebody zooms in far enough
// to see the difference.
const BANDS = [
  { name: 'coarse', maxzoom: 11 },
  { name: 'medium', minzoom: 11, maxzoom: 13 },
  { name: 'fine', minzoom: 13 },
];

const $ = (s) => document.querySelector(s);
const state = { days: new Set(), meta: null };

async function json(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function bounds(extent) {         // meta.extent is [lon0, lon1, lat0, lat1]
  return [[extent[0], extent[2]], [extent[1], extent[3]]];
}

const map = new maplibregl.Map({
  container: 'map',
  // No basemap: the style starts as bare water and the build's own GeoJSON is
  // the entire chart.
  style: {
    version: 8,
    sources: {},
    layers: [{ id: 'water', type: 'background', paint: { 'background-color': PALETTE.water } }],
  },
  attributionControl: false,
  maxZoom: 18,
  minZoom: 8,
  dragRotate: false,
  pitchWithRotate: false,
  touchZoomRotate: true,
  hash: false,
});
map.touchZoomRotate.disableRotation();
map.keyboard.enable();

// A deliberate handle. `const map` is a lexical binding, not a window property,
// and `window.map` resolves to the <div id="map"> instead — which is how a
// screenshot harness ends up silently measuring nothing.
window.chart = map;
// Handles the screenshot harness uses; harmless in a browser and the reason the
// viewer can be exercised without synthesising mouse events over a WebGL canvas.
window.__state = state;
window.__open = (id) => openViewer(id);

map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
map.addControl(new maplibregl.AttributionControl({
  compact: true,
  // Short enough not to wrap to two lines on a phone, where it would take a
  // tenth of the chart to say something nobody opened this to read.
  customAttribution: 'Coastline © OpenStreetMap · Track from a handheld GPS',
}), 'bottom-right');

map.on('load', start);

async function start() {
  const meta = await json('data/meta.json');
  state.meta = meta;
  map.fitBounds(bounds(meta.extent), { padding: 18, animate: false });

  // Don't let the chart be zoomed out past the whole trek, and don't let it be
  // panned into empty ocean — but note the order and the generosity, both of
  // which were wrong first time round. The extent is portrait (27 km by 46 km)
  // and screens are landscape, so fitting its height needs *more* width than the
  // extent has; a bounds box padded only by a fraction of each axis was
  // therefore tighter than the fit, and MapLibre resolved the conflict by
  // zooming in and cropping the trek at both ends. Padding by a share of the
  // larger span keeps the clamp clear of any sane viewport.
  map.setMinZoom(Math.max(7, map.getZoom() - 0.35));
  map.setMaxBounds(roomy(meta.extent, 0.6));

  addChart();
  await addTracks(meta);
  await addPhotos();
  await addPlaces();
  addInreach();
  buildPanel(meta);
  wirePanel();
  scaleBar();
  map.on('move', scaleBar);
  map.on('zoom', scaleBar);
}

// Pad both axes by a share of the *larger* span, so the box is never tighter
// than a full-extent fit on a landscape screen.
function roomy(e, f) {
  const pad = Math.max(e[1] - e[0], e[3] - e[2]) * f;
  return [[e[0] - pad, e[2] - pad], [e[1] + pad, e[3] + pad]];
}

/* ------------------------------------------------------------------ chart --- */
function addChart() {
  // Shoals under the land, so the halo reads as shallows running up to a beach.
  for (const b of BANDS) {
    map.addSource(`shoals-${b.name}`, { type: 'geojson', data: `data/shoals.${b.name}.geojson` });
    map.addLayer({
      id: `shoals-outer-${b.name}`, type: 'fill', source: `shoals-${b.name}`,
      filter: ['==', ['get', 'ring'], 'outer'],
      ...zoomRange(b), paint: { 'fill-color': PALETTE.shoal1 },
    });
    map.addLayer({
      id: `shoals-inner-${b.name}`, type: 'fill', source: `shoals-${b.name}`,
      filter: ['==', ['get', 'ring'], 'inner'],
      ...zoomRange(b), paint: { 'fill-color': PALETTE.shoal2 },
    });
  }
  for (const b of BANDS) {
    map.addSource(`coast-${b.name}`, { type: 'geojson', data: `data/coast.${b.name}.geojson` });
    map.addLayer({
      id: `land-${b.name}`, type: 'fill', source: `coast-${b.name}`,
      ...zoomRange(b), paint: { 'fill-color': PALETTE.land },
    });
    map.addLayer({
      id: `land-edge-${b.name}`, type: 'line', source: `coast-${b.name}`,
      ...zoomRange(b),
      paint: {
        'line-color': PALETTE.landEdge,
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.4, 13, 0.7, 17, 1.1],
      },
    });
  }
}

function zoomRange(b) {
  const o = {};
  if (b.minzoom !== undefined) o.minzoom = b.minzoom;
  if (b.maxzoom !== undefined) o.maxzoom = b.maxzoom;
  return o;
}

/* ----------------------------------------------------------------- tracks --- */
async function addTracks(meta) {
  map.addSource('tracks', { type: 'geojson', data: 'data/tracks.geojson' });

  // A pale casing under every track so a dark day still reads where it crosses
  // land, and so two days sharing a channel stay legible.
  map.addLayer({
    id: 'track-casing', type: 'line', source: 'tracks',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': '#FBF6EA',
      'line-opacity': 0.85,
      'line-width': ['interpolate', ['linear'], ['zoom'], 8, 3.0, 12, 5.0, 17, 8.0],
    },
  });
  // Ashore is dotted, as on the poster: the walk to the marina and the van to
  // the airport are not sailing.
  map.addLayer({
    id: 'track-ashore', type: 'line', source: 'tracks',
    filter: ['!=', ['get', 'mode'], 'afloat'],
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      // Dotted for the walk and the van; finer dots for the arrival transfer,
      // which is a road reconstruction rather than anything the receiver saw.
      'line-dasharray': ['case', ['==', ['get', 'mode'], 'transfer'],
                         ['literal', [1, 2.2]], ['literal', [1.4, 1.6]]],
      'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.4, 12, 2.2, 17, 3.4],
    },
  });
  map.addLayer({
    id: 'track-afloat', type: 'line', source: 'tracks',
    filter: ['==', ['get', 'mode'], 'afloat'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.5, 12, 2.4, 17, 3.8],
    },
  });

  for (const d of meta.days) state.days.add(d.label);
  applyDays();

  // Tapping a track says which day it is — the chart-plotter equivalent of
  // reading the legend without leaving the chart.
  for (const id of ['track-afloat', 'track-ashore']) {
    map.on('click', id, (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup({ closeButton: false, offset: 8, maxWidth: '17rem' })
        .setLngLat(e.lngLat)
        .setHTML(`<strong>${esc(p.day)}</strong><br>${esc(p.title)}` +
                 `<br><span class="popup-route">${esc(p.route)}</span>` +
                 (p.nm ? `<br><span class="popup-route">${Number(p.nm).toFixed(1)} nm</span>` : ''))
        .addTo(map);
    });
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }
}

function applyDays() {
  const keep = [...state.days];
  const f = keep.length ? ['in', ['get', 'day'], ['literal', keep]] : ['==', ['get', 'day'], ' '];
  map.setFilter('track-casing', f);
  map.setFilter('track-afloat', ['all', f, ['==', ['get', 'mode'], 'afloat']]);
  map.setFilter('track-ashore', ['all', f, ['!=', ['get', 'mode'], 'afloat']]);
}

/* ----------------------------------------------------------------- places --- */
async function addPlaces() {
  // No glyph server, so labels are drawn as HTML markers rather than symbol
  // layers. That keeps the site free of a font-stack dependency, and there are
  // only sixteen of them.
  const fc = await json('data/places.geojson');
  state.placeMarkers = [];
  for (const f of fc.features) {
    const p = f.properties;
    const el = document.createElement('div');
    el.className = `place place-${p.kind}`;
    el.textContent = p.label;      // CSS keeps the newline: see white-space
    const m = new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat(f.geometry.coordinates).addTo(map);
    state.placeMarkers.push({ marker: m, minzoom: p.minzoom || 11, el });
  }
  const tick = () => {
    const z = map.getZoom();
    const on = state.layers ? state.layers.places : true;
    for (const pm of state.placeMarkers) {
      pm.el.style.display = (on && z >= pm.minzoom) ? '' : 'none';
    }
  };
  state.refreshPlaces = tick;
  map.on('zoom', tick);
  tick();
}

function addInreach() {
  fetch('data/inreach.geojson').then((r) => (r.ok ? r.json() : null)).then((fc) => {
    if (!fc) return;
    map.addSource('inreach', { type: 'geojson', data: fc });
    map.addLayer({
      id: 'inreach', type: 'line', source: 'inreach',
      layout: { visibility: 'none', 'line-join': 'round' },
      paint: {
        'line-color': PALETTE.inkSoft,
        'line-dasharray': [2, 2],
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.0, 17, 2.0],
      },
    });
  });
}

/* ------------------------------------------------------------------ panel --- */
function buildPanel(meta) {
  const ul = $('#days');
  for (const d of meta.days) {
    const li = document.createElement('li');
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = true; cb.dataset.day = d.label;
    const sw = document.createElement('span');
    sw.className = 'swatch'; sw.style.borderTopColor = d.color;
    const name = document.createElement('span');
    name.className = 'daylabel';
    name.textContent = d.sail && d.n ? `${d.label} — ${d.title}` : `${d.label} — ${d.title}`;
    label.append(cb, sw, name);
    li.append(label);
    ul.append(li);
    cb.addEventListener('change', () => {
      if (cb.checked) state.days.add(d.label); else state.days.delete(d.label);
      applyDays();
    });
  }
}

function wirePanel() {
  state.layers = { photos: true, shoals: true, places: true, inreach: false };
  const panel = $('#panel'), toggle = $('#panel-toggle');
  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
  };
  setOpen(window.matchMedia('(min-width: 34rem)').matches);
  toggle.addEventListener('click', () => setOpen(panel.hidden));

  for (const cb of document.querySelectorAll('#chart-layers input[data-layer]')) {
    cb.addEventListener('change', () => {
      const key = cb.dataset.layer;
      state.layers[key] = cb.checked;
      if (key === 'shoals') {
        for (const b of BANDS) {
          for (const r of ['outer', 'inner']) {
            setVisible(`shoals-${r}-${b.name}`, cb.checked);
          }
        }
      } else if (key === 'places') {
        state.refreshPlaces && state.refreshPlaces();
      } else if (key === 'inreach') {
        setVisible('inreach', cb.checked);
      } else if (key === 'photos') {
        for (const id of ['clusters', 'photo-points', 'uncertainty',
                          'uncertainty-edge', 'selected']) {
          setVisible(id, cb.checked);
        }
        drawClusterCounts();
      }
    });
  }
  $('#days-all').addEventListener('click', () => setAllDays(true));
  $('#days-none').addEventListener('click', () => setAllDays(false));
}

function setAllDays(on) {
  for (const cb of document.querySelectorAll('#days input[data-day]')) {
    cb.checked = on;
    if (on) state.days.add(cb.dataset.day); else state.days.delete(cb.dataset.day);
  }
  applyDays();
}

function setVisible(id, on) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

/* --------------------------------------------------------------- scale bar --- */
// A scale bar earns its place on a zoomable chart where a compass rose would
// only need redrawing at every scale. Nautical miles, because that is what the
// week was measured in.
function scaleBar() {
  const NM = 1852;
  const y = map.getCanvas().clientHeight / 2;
  const a = map.unproject([0, y]), b = map.unproject([100, y]);
  const mPerPx = a.distanceTo(b) / 100;
  const targetPx = Math.min(150, Math.max(80, map.getCanvas().clientWidth * 0.22));
  const rawNm = (targetPx * mPerPx) / NM;
  const nice = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50];
  let nm = nice[0];
  for (const n of nice) if (n <= rawNm) nm = n;
  const px = (nm * NM) / mPerPx;
  $('#scalebar-line').style.width = `${Math.round(px)}px`;
  $('#scalebar-label').textContent = `${nm} nm`;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

map.on('error', (e) => {
  // Loud in the console, quiet on the chart: a missing optional layer should not
  // blank the map the crew opened.
  console.error('map error', e && e.error ? e.error : e);
});

/* ----------------------------------------------------------- photographs --- */
// Tier colours. `gps` and `bracket` are the camera's own word for where it was;
// `calibrated` and `inferred` are the boat's, which is a different claim, and the
// chart says so quietly rather than pretending they are the same thing.
const TIER = {
  gps: '#0B6E4F',
  calibrated: '#1D4E89',
  inferred: '#8A7F6A',
};
const ON_CHART = ['gps', 'calibrated', 'inferred'];

async function addPhotos() {
  const all = await json('data/photos.json');
  state.photos = all;
  // Time order is already how the build wrote it, so previous/next in the viewer
  // follows the day as it happened rather than wandering by proximity.
  state.shown = all.filter((p) => ON_CHART.includes(p.tier) && p.lat != null);
  state.offChart = all.filter((p) => !ON_CHART.includes(p.tier));
  state.indexById = new Map(state.shown.map((p, i) => [p.id, i]));

  map.addSource('photos', {
    type: 'geojson',
    cluster: true,
    // 13, not 15. Clustering applies per integer tile zoom, so a ceiling of 15
    // meant nothing became an individual pin until z16 — and with maxZoom 17
    // that left one zoom level in which to actually look at a photograph. The
    // design's promise is cluster → zoom splits it → pin opens the viewer, and
    // the split has to happen somewhere a person would still be exploring.
    clusterMaxZoom: 13,
    clusterRadius: 42,
    data: {
      type: 'FeatureCollection',
      features: state.shown.map((p) => ({
        type: 'Feature',
        properties: { id: p.id, tier: p.tier },
        geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      })),
    },
  });

  // The ring that says how far out a position could be. Drawn in metres, so it
  // grows as you zoom in — a 1.8 km GoPro estimate stays honestly enormous and a
  // 15 m camera fix stays invisibly small.
  map.addSource('uncertainty', { type: 'geojson', data: emptyFC() });
  map.addLayer({
    id: 'uncertainty', type: 'fill', source: 'uncertainty',
    paint: { 'fill-color': '#8A7F6A', 'fill-opacity': 0.17 },
  });
  map.addLayer({
    id: 'uncertainty-edge', type: 'line', source: 'uncertainty',
    paint: { 'line-color': '#8A7F6A', 'line-width': 1, 'line-dasharray': [2, 2] },
  });

  map.addSource('selected', { type: 'geojson', data: emptyFC() });

  map.addLayer({
    id: 'clusters', type: 'circle', source: 'photos',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': '#FBF6EA',
      'circle-opacity': 0.94,
      'circle-stroke-color': '#2E3A42',
      'circle-stroke-width': 1.2,
      'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'],
                        2, 11, 20, 15, 100, 20, 500, 26],
    },
  });
  map.addLayer({
    id: 'photo-points', type: 'circle', source: 'photos',
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': ['match', ['get', 'tier'],
                       'gps', TIER.gps,
                       'calibrated', TIER.calibrated, TIER.inferred],
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3.4, 14, 5, 18, 8],
      'circle-stroke-color': '#FBF6EA',
      'circle-stroke-width': 1.4,
    },
  });

  // Clustering runs to z15, so the photograph you have open is usually still
  // inside a cluster and would otherwise have nothing marking it.
  map.addLayer({
    id: 'selected', type: 'circle', source: 'selected',
    paint: {
      'circle-color': '#C1272D',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 17, 9],
      'circle-stroke-color': '#FBF6EA',
      'circle-stroke-width': 2,
    },
  });

  // A cluster is a promise that zooming will split it.
  map.on('click', 'clusters', (e) => {
    const f = map.queryRenderedFeatures(e.point, { layers: ['clusters'] })[0];
    map.getSource('photos').getClusterExpansionZoom(f.properties.cluster_id)
      .then((z) => map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.15 }))
      .catch(() => {});
  });
  map.on('click', 'photo-points', (e) => {
    openViewer(e.features[0].properties.id);
  });
  for (const id of ['clusters', 'photo-points']) {
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }

  // Cluster counts are HTML, because a symbol layer would need a glyph server
  // and this site has no font stack to host. There are rarely more than forty
  // on screen, and queryRenderedFeatures only returns what is in the viewport.
  const redraw = () => drawClusterCounts();
  map.on('move', redraw);
  map.on('moveend', redraw);
  map.on('sourcedata', (e) => { if (e.sourceId === 'photos') redraw(); });
  redraw();

  buildTray();
  wireViewer();
}

function emptyFC() { return { type: 'FeatureCollection', features: [] }; }

let countEls = [];
function drawClusterCounts() {
  const host = $('#clusters');
  if (!host) return;
  if (!state.layers || state.layers.photos === false) { host.innerHTML = ''; return; }
  const feats = map.queryRenderedFeatures({ layers: ['clusters'] });
  // Reuse the DOM nodes: this runs on every frame of a pan.
  while (countEls.length < feats.length) {
    const el = document.createElement('div');
    el.className = 'cluster-count';
    host.appendChild(el);
    countEls.push(el);
  }
  feats.forEach((f, i) => {
    const el = countEls[i];
    const pt = map.project(f.geometry.coordinates);
    el.textContent = f.properties.point_count_abbreviated;
    el.style.transform = `translate(-50%, -50%) translate(${pt.x}px, ${pt.y}px)`;
    el.style.display = '';
  });
  for (let i = feats.length; i < countEls.length; i++) countEls[i].style.display = 'none';
}

/* ---------------------------------------------------------------- viewer --- */
function ringAround(lon, lat, metres) {
  // A circle in metres, as a polygon, because that is what a fill layer can draw
  // at any zoom without the radius quietly meaning pixels instead.
  const pts = [];
  const dLat = metres / 111320;
  const dLon = metres / (111320 * Math.cos(lat * Math.PI / 180));
  for (let i = 0; i <= 48; i++) {
    const a = (i / 48) * Math.PI * 2;
    pts.push([lon + Math.cos(a) * dLon, lat + Math.sin(a) * dLat]);
  }
  return { type: 'FeatureCollection', features: [{
    type: 'Feature', properties: {},
    geometry: { type: 'Polygon', coordinates: [pts] } }] };
}

function openViewer(id) {
  const i = state.indexById.get(id);
  if (i === undefined) return;
  state.at = i;
  showAt(i);
}

function showAt(i) {
  const p = state.shown[i];
  if (!p) return;
  state.at = i;
  $('#viewer-img').src = p.view;
  $('#viewer-img').alt = `Photograph ${i + 1} of ${state.shown.length}`;
  $('#viewer-when').textContent = whenText(p);
  $('#viewer-note').textContent = p.note || '';
  $('#viewer-meta').textContent =
    [p.camera, p.uncertainty_m != null ? `± ${fmtDistance(p.uncertainty_m)}` : null]
      .filter(Boolean).join('  ·  ');
  $('#viewer').hidden = false;
  document.body.classList.add('viewing');

  map.getSource('uncertainty').setData(
    p.uncertainty_m ? ringAround(p.lon, p.lat, p.uncertainty_m) : emptyFC());
  map.getSource('selected').setData({
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {},
                 geometry: { type: 'Point', coordinates: [p.lon, p.lat] } }],
  });
  // Bring it into view without yanking the chart around if it is already there.
  if (!map.getBounds().contains([p.lon, p.lat])) {
    map.easeTo({ center: [p.lon, p.lat], duration: 400 });
  }
}

function whenText(p) {
  if (!p.utc) return p.day ? `${p.day} — time unknown` : 'time unknown';
  const d = new Date(p.utc);
  const edt = new Date(d.getTime() - 4 * 3600 * 1000);
  const hh = String(edt.getUTCHours()).padStart(2, '0');
  const mm = String(edt.getUTCMinutes()).padStart(2, '0');
  return `${p.day || ''} · ${hh}:${mm}`.trim();
}

function fmtDistance(m) {
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  if (m >= 100) return `${Math.round(m / 10) * 10} m`;
  return `${m} m`;
}

function closeViewer() {
  $('#viewer').hidden = true;
  document.body.classList.remove('viewing');
  map.getSource('uncertainty').setData(emptyFC());
  map.getSource('selected').setData(emptyFC());
}

function wireViewer() {
  $('#viewer-close').addEventListener('click', closeViewer);
  $('#viewer-prev').addEventListener('click', () => showAt(Math.max(0, state.at - 1)));
  $('#viewer-next').addEventListener('click',
    () => showAt(Math.min(state.shown.length - 1, state.at + 1)));
  document.addEventListener('keydown', (e) => {
    if ($('#viewer').hidden && $('#tray').hidden) return;
    if (e.key === 'Escape') { closeViewer(); $('#tray').hidden = true; }
    if ($('#viewer').hidden) return;
    if (e.key === 'ArrowLeft') showAt(Math.max(0, state.at - 1));
    if (e.key === 'ArrowRight') showAt(Math.min(state.shown.length - 1, state.at + 1));
  });
  $('#tray-open').addEventListener('click', () => { $('#tray').hidden = false; });
  $('#tray-close').addEventListener('click', () => { $('#tray').hidden = true; });
}

/* ------------------------------------------------------------------- tray --- */
function buildTray() {
  const off = state.offChart;
  $('#tray-count').textContent = `(${off.length})`;
  const why = {
    travel: 'Taken away from Abaco — the flights, and home either side. '
          + 'Plotting Portland on a chart of the Sea of Abaco would be nonsense.',
    unplaced: 'The camera knew when, but the receiver was on its charger — '
            + 'these are mostly the evenings ashore.',
  };
  const byTier = {};
  for (const p of off) (byTier[p.tier] = byTier[p.tier] || []).push(p);
  const body = $('#tray-body');
  body.innerHTML = '';
  for (const tier of ['unplaced', 'travel']) {
    const list = byTier[tier];
    if (!list) continue;
    const h = document.createElement('h3');
    h.textContent = `${tier === 'travel' ? 'Travel' : 'Ashore, after the receiver stopped'} — ${list.length}`;
    const note = document.createElement('p');
    note.className = 'tray-why';
    note.textContent = why[tier] || '';
    body.append(h, note);
    // Grouped by day, then camera: the tray is for browsing, not for hunting.
    const byDay = {};
    for (const p of list) (byDay[p.day || 'Undated'] = byDay[p.day || 'Undated'] || []).push(p);
    for (const [day, ps] of Object.entries(byDay)) {
      const dh = document.createElement('h4');
      dh.textContent = `${day} · ${ps.length}`;
      const grid = document.createElement('div');
      grid.className = 'grid';
      for (const p of ps) {
        const img = document.createElement('img');
        img.src = p.thumb;
        img.loading = 'lazy';            // only what is on screen is fetched
        img.decoding = 'async';
        img.alt = '';
        img.title = `${p.camera}${p.utc ? ' · ' + whenText(p) : ''}`;
        img.addEventListener('click', () => openOffChart(p));
        grid.append(img);
      }
      body.append(dh, grid);
    }
  }
}

function openOffChart(p) {
  // Same viewer, but there is no position to show or ring to draw.
  $('#viewer-img').src = p.view;
  $('#viewer-img').alt = '';
  $('#viewer-when').textContent = whenText(p);
  $('#viewer-note').textContent = p.note || '';
  $('#viewer-meta').textContent = p.camera || '';
  $('#viewer').hidden = false;
  document.body.classList.add('viewing');
  map.getSource('uncertainty').setData(emptyFC());
}
