/* The chart. It draws what the build told it and works nothing out for itself:
   every position, tier and note in the data was resolved offline in Python.

   No third-party tiles, no API, no network beyond this folder. The only
   dependency is vendor/maplibre-gl.js, which is here rather than on a CDN so
   that moving hosts stays a file copy. */
'use strict';

const PALETTE = {
  water: '#E7F1F5',
  land: '#F0E2C2', landEdge: '#8A7F6A', ink: '#2E3A42', inkSoft: '#5C6B75',
  // The deepest depth band, painted by the background rather than shipped as
  // 53,543 km2 of polygon. It is the poster's own water colour, and the depth ramp
  // steps down from it.
  deepWater: '#E7F1F5',
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
  // no-cache: always ask the server before trusting a stored copy. These
  // fetches run after the page has loaded, which puts them outside a hard
  // reload's cache bypass -- a browser once held a heuristically-"fresh"
  // places.geojson through four refreshes, drawing week-old label positions
  // under brand-new code.
  const r = await fetch(path, { cache: 'no-cache' });
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
    layers: [{ id: 'water', type: 'background',
               paint: { 'background-color': PALETTE.deepWater } }],
  },
  attributionControl: false,
  // This chart is one 27 x 46 km box and maxBounds forbids panning off it, so
  // the copies of the world either side are scenery nobody can reach. Kept
  // because it is the correct setting, not because it measured faster — on a
  // software renderer the frame times were too noisy to show either way.
  renderWorldCopies: false,
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
window.__drawCounts = () => drawClusterCounts();
window.__scaleBar = () => scaleBar();

map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
map.addControl(new maplibregl.AttributionControl({
  compact: true,
  // Short enough not to wrap to two lines on a phone, where it would take a
  // tenth of the chart to say something nobody opened this to read.
  customAttribution: 'Coastline © OpenStreetMap · Depths GMRT · '
                   + 'Track from a handheld GPS',
}), 'bottom-left');

map.on('load', start);

async function start() {
  const meta = await json('data/meta.json');
  state.meta = meta;

  // Don't let the chart be zoomed out past the whole trek, and don't let it be
  // panned into empty ocean. The clamp is built from what is actually *visible*
  // at the opening zoom rather than from the extent, because the extent is
  // portrait (27 km by 46 km) and screens are landscape: derived from the extent,
  // the box was tight in longitude and generous in latitude, so the chart panned
  // 21 km north but only 4 km east before sticking. Inflating the visible bounds
  // gives the same slack in every direction whatever shape the window is.
  applyViewLimits(meta);
  map.fitBounds(bounds(meta.extent), { padding: 18, animate: false });
  // A window can always be made wider than any amount of coastline, so the limits
  // come from the data and the container rather than from the opening view, and
  // are recomputed whenever the window changes shape.
  map.on('resize', () => applyViewLimits(meta));

  addChart(meta);
  await addTracks(meta);
  // Photographs, names and stories are each worth having and none is worth the
  // chart: one failed fetch used to stop here, before the panel was built, and
  // leave a chart with no Days list and a Layers button wired to nothing.
  const lost = [];
  for (const [what, load] of [['photographs', addPhotos], ['place names', addPlaces],
                              ['stories', addStories]]) {
    try { await load(); } catch (e) { console.error(e); lost.push(what); }
  }
  buildPanel(meta);
  wirePanel();
  if (lost.length) {
    const n = $('#notice');
    n.textContent = `Could not load the ${lost.join(' or the ')}. The rest of the chart is here.`;
    n.hidden = false;
  }
  scaleBar();
  map.on('move', scaleBar);
  map.on('zoom', scaleBar);
}

// The view may not leave the region the coastline actually covers. Zooming out is
// limited to the zoom at which that region still fills this container, so a wider
// window buys a wider view rather than a glimpse past the edge of the data — which
// is the only way this holds for a window of any shape.
function applyViewLimits(meta) {
  const v = meta.view_bounds;                    // lon0, lon1, lat0, lat1
  const box = [[v[0], v[2]], [v[1], v[3]]];
  // Order matters: the clamp has to exist before fitBounds, or MapLibre resolves
  // the conflict by zooming in and cropping the trek.
  map.setMaxBounds(null);
  const cam = map.cameraForBounds(box, { padding: 0 });
  map.setMinZoom(cam && cam.zoom ? cam.zoom : 8);
  map.setMaxBounds(box);
}

/* ------------------------------------------------------------------ chart --- */
// Measured bathymetry, drawn deepest band first so the shallowest sits on top.
// The deepest band is not in the data at all — it is the water background, which
// paints "everywhere else" for nothing.
function addDepth(meta) {
  // Vector bands, not a raster. A raster of a 61 m grid can only be a staircase or
  // a blur when magnified, and both were shipped and both looked it. Each feature
  // is everything shallower than its `hi`, so they nest, and drawing them in
  // descending order of `hi` leaves the shallowest on top.
  //
  // Fills only. Each band had a slightly darker line along its edge for a while, on
  // the theory that the poster's shoal halos read as crisp because each ring has an
  // edge — but on measured depths, where the bands are large and their boundaries
  // are a judgement about a 61 m survey rather than a drawn outline, it just looked
  // ruled.
  map.addSource('depth', { type: 'geojson', data: 'data/depth.geojson' });
  const bands = (meta.depth_bands || []).filter((b) => b.hi != null);
  for (const b of [...bands].sort((p, q) => q.hi - p.hi)) {
    map.addLayer({
      id: `depth-${b.hi}`, type: 'fill', source: 'depth',
      filter: ['==', ['get', 'hi'], b.hi],
      paint: { 'fill-color': b.colour, 'fill-antialias': true },
    });
  }
}

function addShoals() {
  // The drawn halo the printed sheet has always used: two buffers around the land,
  // coloured to suggest shallows and knowing nothing about the seabed. Hidden while
  // the measured depths are on, and shown in their place when Depth is unticked —
  // bare water was the wrong thing to fall back to, and seeing the two swap is the
  // only way to judge what the measurement changed.
  map.addSource('shoals', { type: 'geojson', data: 'data/shoals.geojson' });
  for (const order of [0, 1]) {          // outer ring first, inner over it
    map.addLayer({
      id: `shoal-${order}`, type: 'fill', source: 'shoals',
      filter: ['==', ['get', 'order'], order],
      layout: { visibility: 'none' },
      paint: { 'fill-color': ['get', 'colour'], 'fill-antialias': true },
    });
  }
}

function addChart(meta) {
  addShoals();
  addDepth(meta);
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
      // Dotted for the walk and the van; finer dots for the arrival transfer and
      // for the nights, which are reconstructions rather than anything the handheld
      // saw — the transfer from the road, the nights from the inReach's reports.
      'line-dasharray': ['case',
                         ['==', ['get', 'mode'], 'transfer'], ['literal', [1, 2.2]],
                         ['==', ['get', 'mode'], 'moored'], ['literal', [0.8, 1.8]],
                         ['literal', [1.4, 1.6]]],
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
      // A photograph placed from the track sits on the line, and a click on it
      // is for the photograph. Where two of these layers overlap, one popup.
      const photos = ['clusters', 'photo-points'].filter((l) => map.getLayer(l));
      if (photos.length && map.queryRenderedFeatures(e.point, { layers: photos }).length) return;
      if (e.originalEvent._trackPopup) return;
      e.originalEvent._trackPopup = true;
      const p = e.features[0].properties;
      const bits = [];
      if (p.nm) bits.push(`${Number(p.nm).toFixed(1)} nm`);
      if (p.shallowest_m) {
        bits.push(`shallowest water ${Number(p.shallowest_m).toFixed(1)} m`);
      }
      new maplibregl.Popup({ closeButton: false, offset: 8, maxWidth: '17rem' })
        .setLngLat(e.lngLat)
        .setHTML(`<strong>${esc(p.day)}</strong><br>${esc(p.title)}` +
                 `<br><span class="popup-route">${esc(p.route)}</span>` +
                 (bits.length ? `<br><span class="popup-route">${esc(bits.join(' · '))}</span>` : ''))
        .addTo(map);
    });
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }
}

function applyDays() {
  const keep = [...state.days];
  // No days ticked means show nothing. Say that with a filter that cannot
  // match, rather than comparing day against a sentinel: the sentinel here
  // used to be a literal NUL byte, which made this file read as binary --
  // grep over the whole site silently returned nothing, for every pattern.
  const f = keep.length ? ['in', ['get', 'day'], ['literal', keep]]
                        : ['==', ['literal', 0], ['literal', 1]];
  map.setFilter('track-casing', f);
  map.setFilter('track-afloat', ['all', f, ['==', ['get', 'mode'], 'afloat']]);
  map.setFilter('track-ashore', ['all', f, ['!=', ['get', 'mode'], 'afloat']]);
  refreshPhotos();
  refreshStories();
}

/* Hiding a day hides its photographs with it.
 *
 * This rebuilds the source's data rather than filtering the layers, because the
 * source clusters: a filter hides the dots a cluster is made of while the cluster
 * goes on reporting how many it had, so unticking a day would leave "37" floating
 * over water with nothing under it. Clustering is done by the source, so the
 * honest fix is to give the source less to cluster. The cluster counts follow by
 * themselves: setData fires sourcedata, and the listener there redraws them once
 * the new tiles exist -- redrawing here would only repaint the old ones.
 *
 * state.shown is the visible set, not the placeable one -- the viewer's next and
 * previous walk it, so they cannot wander into a day that has been switched off.
 */
function refreshPhotos() {
  if (!state.onChart) return;                 // called once before photos load
  // Read the open photograph before rebuilding: state.at indexes state.shown, so
  // the moment that array changes the index means something else. A photograph
  // opened from the tray leaves state.at null, and the rebuild leaves it alone.
  const openId = ($('#viewer').hidden || state.at == null || !state.shown)
    ? null : (state.shown[state.at] || {}).id;
  // As in the tray: a photograph with no day has no checkbox to answer to, and
  // one that knows where it was but not when would otherwise be in neither.
  state.shown = state.onChart.filter((p) => !p.day || state.days.has(p.day));
  state.indexById = new Map(state.shown.map((p, i) => [p.id, i]));
  // Guarded: a tab holding last week's page with this script has no button.
  const browse = $('#photos-browse');
  if (browse) {
    browse.disabled = !state.shown.length;
    // The count is part of the button's name, so it is read out with it.
    browse.textContent = `Browse the photographs on the chart (${state.shown.length})`;
  }
  const src = map.getSource('photos');
  if (src) src.setData(photoFC(state.shown));
  // A photograph whose day just went away should not stay open over a chart that
  // no longer shows where it was. One that survives is re-shown at its new index
  // rather than just reassigned: "Photograph 571 of 2180" has to stop saying 2180
  // the moment 610 of them are hidden. Re-shown where it stands, though --
  // renumbering the caption is no reason to move the camera.
  if (openId != null) {
    if (state.indexById.has(openId)) showAt(state.indexById.get(openId), { pan: false });
    else closeViewer();
  }
  // The tray answers to the same checkboxes as the chart.
  buildTray();
}

function photoFC(list) {
  return {
    type: 'FeatureCollection',
    features: list.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, tier: p.tier },
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
    })),
  };
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
    // A name that ends at its point rather than straddling it stays the same few
    // pixels off its island at every zoom, where a centred one set off to the
    // side drifts away as the map grows.
    el.className = `place place-${p.kind}${p.anchor ? ` place-${p.anchor}` : ''}`;
    el.textContent = p.label;      // CSS keeps the newline: see white-space
    const m = new maplibregl.Marker({ element: el, anchor: p.anchor || 'center' })
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

/* ---------------------------------------------------------------- stories --- */
// What happened where, in the journal's own words. HTML markers for the same
// reason the place names are: no glyph server, and a marker that carries a number
// needs text. There are a couple of dozen, so the cost is nothing.
const STORY_NEAR_PX = 16;

async function addStories() {
  const fc = await json('data/stories.geojson');
  state.stories = fc.features.map((f) => {
    const p = f.properties;
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'story';
    el.textContent = p.n;
    el.style.background = p.color;
    el.setAttribute('aria-label', `Story ${p.n}: ${p.title}`);
    const s = { p, lngLat: f.geometry.coordinates, el };
    // A marker swallows the click, so the map never hears it: open from here.
    el.addEventListener('click', (e) => { e.stopPropagation(); openStory(s); });
    s.marker = new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat(s.lngLat).addTo(map);
    return s;
  });
  refreshStories();
}

// A story shows when its box is ticked and its day is. The first call comes from
// applyDays before the stories have loaded, hence the guard.
function refreshStories() {
  if (!state.stories) return;
  const on = state.layers ? state.layers.stories : true;
  for (const s of state.stories) {
    s.el.style.display = (on && state.days.has(s.p.day)) ? '' : 'none';
  }
  // An open popup goes with its stories: one left over a chart that no longer
  // shows its day is the filter not having filtered. A popup can hold stories
  // from two days at one anchorage, and unticking one day costs it that story
  // and not the other.
  if (state.storyPopup) {
    const were = state.storyPopupOf || [];
    const left = were.filter((o) => o.el.style.display !== 'none');
    if (!left.length) state.storyPopup.remove();
    else if (left.length < were.length) showStories(left, state.storyPopup.getLngLat());
  }
  drawClusterCounts();      // a dot that has just appeared may be under a bubble
}

/* Several things happened at the same anchorage, and their markers sit on top of
 * one another until the chart is zoomed well in. So a tap opens every visible
 * story under it, in the order they happened, rather than whichever marker the
 * browser happened to stack last. */
function openStory(s) {
  const at = map.project(s.lngLat);
  const here = state.stories.filter((o) => {
    if (o.el.style.display === 'none') return false;
    const q = map.project(o.lngLat);
    return Math.hypot(q.x - at.x, q.y - at.y) <= STORY_NEAR_PX;
  }).sort((a, b) => a.p.n - b.p.n);
  showStories(here, s.lngLat);
}

function showStories(here, lngLat) {
  const html = here.map((o) =>
    `<article class="story-text"><h3><span class="story-n" style="background:${esc(o.p.color)}">` +
    `${esc(o.p.n)}</span>${esc(o.p.title)}</h3>` +
    `<p class="popup-route">${esc(storyWhen(o.p))}</p><p>${esc(o.p.text)}</p></article>`).join('') +
    `<p class="story-more"><a href="journal.html#${esc(daySlug(here[0].p.day))}">` +
    `Read ${esc(here[0].p.day)} in the journal</a></p>`;
  if (state.storyPopup) state.storyPopup.remove();
  const popup = new maplibregl.Popup({ offset: 14, maxWidth: '21rem', className: 'story-popup' })
    .setLngLat(lngLat).setHTML(html).addTo(map);
  // Closed by hand or replaced, it no longer answers for any story.
  popup.on('close', () => {
    if (state.storyPopup === popup) { state.storyPopup = null; state.storyPopupOf = null; }
  });
  state.storyPopup = popup;
  state.storyPopupOf = here;
}

// The journal page's anchor for a day: 'Sun 24 Mar' -> 'sun-24-mar'. The same
// rule as map/journal.py's slug(), which makes the anchors.
function daySlug(label) {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function storyWhen(p) {
  if (!p.time) return p.day;
  const [h, m] = p.time.split(':').map(Number);
  const h12 = ((h + 11) % 12) + 1;
  return `${p.day} · about ${h12}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
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
  // What the chart opens with is whatever index.html ticks: the chart, its depths
  // and its names. Photographs and stories are there for whoever asks -- 2,180
  // pins and 21 dots over a chart this size bury the chart.
  state.layers = {};
  const panel = $('#panel'), toggle = $('#panel-toggle');
  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
  };
  setOpen(window.matchMedia('(min-width: 34rem)').matches);
  toggle.addEventListener('click', () => setOpen(panel.hidden));

  for (const cb of document.querySelectorAll('#chart-layers input[data-layer]')) {
    cb.addEventListener('change', () => applyLayer(cb.dataset.layer, cb.checked));
    // Once now, so a box that starts unticked starts with its layer hidden: the
    // layers are all added visible, before the panel exists to say otherwise.
    applyLayer(cb.dataset.layer, cb.checked);
  }
  $('#days-all').addEventListener('click', () => setAllDays(true));
  $('#days-none').addEventListener('click', () => setAllDays(false));
  posterLinks();
  applyDayParam();
}

function applyLayer(key, on) {
  state.layers[key] = on;
  if (key === 'depth') {
    for (const b of ((state.meta && state.meta.depth_bands) || []))
      if (b.hi != null) setVisible(`depth-${b.hi}`, on);
    for (const o of [0, 1]) setVisible(`shoal-${o}`, !on);
  } else if (key === 'places') {
    state.refreshPlaces && state.refreshPlaces();
  } else if (key === 'stories') {
    refreshStories();
  } else if (key === 'photos') {
    for (const id of ['clusters', 'photo-points', 'uncertainty',
                      'uncertainty-edge', 'selected']) {
      setVisible(id, on);
    }
    drawClusterCounts();
    // The key explains the photograph dots, so it comes and goes with them.
    $('#photo-key').hidden = !on;
  }
}

// The printed sheet, for anyone who wants it on a wall. The build says which
// files it copied in and how big they are; with none, the group stays hidden.
function posterLinks() {
  const files = (state.meta && state.meta.poster) || [];
  if (!files.length) return;
  const host = $('#poster-links');
  host.textContent = 'Download the 18 × 24 in chart: ';
  files.forEach((f, i) => {
    const a = document.createElement('a');
    a.href = f.href;
    a.download = '';
    a.textContent = `${f.label} (${(f.bytes / 2 ** 20).toFixed(f.bytes < 10 * 2 ** 20 ? 1 : 0)} MB)`;
    host.append(a);
    if (i < files.length - 1) host.append(' · ');
  });
  $('#poster-group').hidden = false;
}

// journal.html links here as index.html?day=Sun 24 Mar: show that day alone,
// frame its track, and turn the stories on, since that is what the reader was
// just reading.
async function applyDayParam() {
  const want = new URLSearchParams(location.search).get('day');
  if (!want || !state.meta.days.some((d) => d.label === want)) return;
  for (const cb of document.querySelectorAll('#days input[data-day]')) {
    cb.checked = cb.dataset.day === want;
  }
  state.days = new Set([want]);
  applyDays();
  const stories = document.querySelector('#chart-layers input[data-layer="stories"]');
  if (stories && !stories.checked) { stories.checked = true; applyLayer('stories', true); }
  try {
    const fc = await json('data/tracks.geojson');
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    const eat = (c) => {
      if (typeof c[0] === 'number') {
        w = Math.min(w, c[0]); e = Math.max(e, c[0]);
        s = Math.min(s, c[1]); n = Math.max(n, c[1]);
      } else c.forEach(eat);
    };
    for (const f of fc.features) if (f.properties.day === want) eat(f.geometry.coordinates);
    if (w < e || s < n) {
      map.fitBounds([[w, s], [e, n]], { padding: 70, maxZoom: 13.5, animate: false });
    }
  } catch (err) { console.error(err); }
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
  // onChart is everything that has a position; shown is the subset whose day is
  // ticked. refreshPhotos owns that subset -- the first paint and every toggle
  // after it run the same computation, so they cannot drift apart.
  state.onChart = all.filter((p) => ON_CHART.includes(p.tier) && p.lat != null);
  state.offChart = all.filter((p) => !ON_CHART.includes(p.tier));

  map.addSource('photos', {
    type: 'geojson',
    cluster: true,
    // Clustered at every zoom the chart reaches. It once stopped at 13, on the
    // promise that zooming always splits a cluster into pins; but a boat at
    // anchor for an afternoon puts sixty photographs within a few metres, and
    // past 13 those drew as a heap of dots with one on top to click. A heap
    // that cannot be split now stays a count, and a click on it opens it.
    maxzoom: 20,
    clusterMaxZoom: 19,
    clusterRadius: 42,
    data: emptyFC(),        // refreshPhotos hands it the visible set below
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

  // Invisible, but still the click target and the hit test. The visible bubble
  // is the HTML .cluster-count, which stacks above the place names -- drawn
  // here on the canvas it sat *under* them, and HOPE TOWN painted straight
  // through the 390 photographs moored on top of it.
  map.addLayer({
    id: 'clusters', type: 'circle', source: 'photos',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': '#FBF6EA',
      'circle-opacity': 0,
      'circle-stroke-width': 0,
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

  // Clustering runs at every zoom, so the photograph you have open is usually
  // still inside a cluster and would otherwise have nothing marking it.
  map.addLayer({
    id: 'selected', type: 'circle', source: 'selected',
    paint: {
      'circle-color': '#C1272D',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 17, 9],
      'circle-stroke-color': '#FBF6EA',
      'circle-stroke-width': 2,
    },
  });

  // A cluster splits when zooming can split it, and opens when it cannot:
  // one that would hold together past z16 is a single anchorage, where another
  // zoom level only spreads the dots a few pixels.
  map.on('click', 'clusters', (e) => {
    const f = map.queryRenderedFeatures(e.point, { layers: ['clusters'] })[0];
    const src = map.getSource('photos');
    const id = f.properties.cluster_id;
    src.getClusterExpansionZoom(id).then((z) => {
      if (z > OPEN_ZOOM || map.getZoom() >= map.getMaxZoom() - 0.01) {
        return src.getClusterLeaves(id, f.properties.point_count, 0).then(openStack);
      }
      map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.15 });
    }).catch(() => {});
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
  // One redraw per animation frame however many events arrive.
  let pending = 0;
  const redraw = () => {
    if (pending) return;
    pending = requestAnimationFrame(() => { pending = 0; drawClusterCounts(); });
  };
  map.on('move', redraw);
  map.on('moveend', redraw);
  map.on('sourcedata', (e) => { if (e.sourceId === 'photos') redraw(); });
  redraw();

  refreshPhotos();          // computes state.shown, fills the source, builds the tray
  wireViewer();
}

// Past this zoom a cluster is opened rather than zoomed into.
const OPEN_ZOOM = 16;

// Open a heap of photographs at its earliest. state.shown is in time order and
// a heap was taken in one sitting, so next and previous walk through it.
function openStack(leaves) {
  const at = leaves.map((l) => state.indexById.get(l.properties.id))
    .filter((i) => i != null).sort((a, b) => a - b);
  if (at.length) openViewer(state.shown[at[0]].id);
}

function emptyFC() { return { type: 'FeatureCollection', features: [] }; }

let countEls = [];
function drawClusterCounts() {
  const host = $('#clusters');
  if (!host) return;
  if (!state.layers || state.layers.photos === false) {
    host.innerHTML = '';
    countEls = [];            // those nodes are gone; forgetting that kept the
                              // counts invisible after the layer came back on
    seatStories([]);
    return;
  }
  if (!map.getLayer('clusters')) return;
  const feats = map.queryRenderedFeatures({ layers: ['clusters'] });
  // Reuse the DOM nodes: this runs on every frame of a pan.
  while (countEls.length < feats.length) {
    const el = document.createElement('div');
    el.className = 'cluster-count';
    host.appendChild(el);
    countEls.push(el);
  }
  const w = map.getCanvas().clientWidth, h = map.getCanvas().clientHeight;
  const bubbles = [];
  let used = 0;
  for (const f of feats) {
    const pt = map.project(f.geometry.coordinates);
    // Bubbles straddling the edge still draw (the host clips them); only one
    // whose whole circle is off screen is skipped. 26 is the largest radius.
    if (pt.x < -26 || pt.y < -26 || pt.x > w + 26 || pt.y > h + 26) continue;
    const el = countEls[used++];
    const r = clusterPx(f.properties.point_count);
    el.textContent = f.properties.point_count_abbreviated;
    el.style.width = `${2 * r}px`;
    el.style.height = `${2 * r}px`;
    el.style.transform = `translate(-50%, -50%) translate3d(${pt.x}px, ${pt.y}px, 0)`;
    el.style.display = '';
    bubbles.push({ x: pt.x, y: pt.y, r });
  }
  for (let i = used; i < countEls.length; i++) countEls[i].style.display = 'none';
  seatStories(bubbles);
}

/* A story and the photographs taken there are at the same spot, so the count
 * bubble landed on the story's dot: the dot was hidden and still took the click,
 * and the bubble showed and could not be opened. A dot under a bubble moves out
 * to the bubble's rim, on the side it was already on, like a badge. */
const STORY_R = 11;
function seatStories(bubbles) {
  if (!state.stories) return;
  for (const s of state.stories) {
    let dx = 0, dy = 0;
    if (s.el.style.display !== 'none') {
      const at = map.project(s.lngLat);
      let x = at.x, y = at.y;
      // Clearing one bubble can land the dot on its neighbour, so go round a
      // few times; in a real pile-up the last pass simply stands.
      for (let pass = 0; pass < 4; pass++) {
        let hit = false;
        for (const b of bubbles) {
          const ox = x - b.x, oy = y - b.y;
          const d = Math.hypot(ox, oy), clear = b.r + STORY_R;
          if (d >= clear - 0.5) continue;
          // Dead centre has no side to keep to, so it goes up and to the right.
          const ux = d > 0.5 ? ox / d : Math.SQRT1_2, uy = d > 0.5 ? oy / d : -Math.SQRT1_2;
          x = b.x + ux * clear;
          y = b.y + uy * clear;
          hit = true;
        }
        if (!hit) break;
      }
      dx = Math.round(x - at.x); dy = Math.round(y - at.y);
    }
    if (s.dx !== dx || s.dy !== dy) {
      s.dx = dx; s.dy = dy;
      s.marker.setOffset([dx, dy]);
    }
  }
}

// The transparent canvas layer's circle-radius stops, so the drawn bubble and
// the click target agree about how big a cluster is.
function clusterPx(n) {
  const stops = [[2, 11], [20, 15], [100, 20], [500, 26]];
  if (n <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    if (n <= stops[i][0]) {
      const [n0, r0] = stops[i - 1], [n1, r1] = stops[i];
      return r0 + (r1 - r0) * (n - n0) / (n1 - n0);
    }
  }
  return stops[stops.length - 1][1];
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

function showAt(i, { pan = true } = {}) {
  const p = state.shown[i];
  if (!p) return;
  // Where the viewer was, if it was open on a neighbour: only a step with the
  // arrows can be said to have moved on.
  const open = !$('#viewer').hidden;
  const from = (open && state.at != null && Math.abs(state.at - i) === 1)
    ? state.shown[state.at] : null;
  // The same photograph shown again -- a day toggle renumbering the sequence --
  // is not a step, and must not take down a notice that has only just gone up.
  const same = open && state.at === i;
  state.at = i;
  const img = $('#viewer-img');
  // Same photograph, new index: renumbering the caption must not reload the image.
  if (img.getAttribute('src') !== p.view) img.src = p.view;
  img.alt = `Photograph ${i + 1} of ${state.shown.length}`;
  // Previous and next walk state.shown, which a tray photograph is not in.
  $('#viewer-prev').hidden = false;
  $('#viewer-next').hidden = false;
  $('#viewer-when').textContent = whenText(p);
  $('#viewer-note').textContent = p.note || '';
  $('#viewer-meta').textContent =
    [p.camera, p.uncertainty_m != null ? `± ${fmtDistance(p.uncertainty_m)}` : null]
      .filter(Boolean).join('  ·  ');
  const [a, b] = spotAround(i);
  $('#viewer-spot').textContent = b > a
    ? `${i - a + 1} of ${b - a + 1} ${/under way/.test(p.note || '') ? 'along this stretch' : 'at this spot'}`
    : '';
  if (!same) announceMove(from, i);
  revealViewer();

  map.getSource('uncertainty').setData(
    p.uncertainty_m ? ringAround(p.lon, p.lat, p.uncertainty_m) : emptyFC());
  map.getSource('selected').setData({
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {},
                 geometry: { type: 'Point', coordinates: [p.lon, p.lat] } }],
  });
  // Bring it into view without yanking the chart around if it is already there.
  // Not at all when a day toggle is only renumbering the sequence: unticking
  // Monday must not drag the camera back to the Thursday photograph that is open.
  if (pan && !map.getBounds().contains([p.lon, p.lat])) {
    map.easeTo({ center: [p.lon, p.lat], duration: 400 });
  }
}

/* The arrows walk every photograph in the order it was taken, not the stack that
 * was opened, so the one after the last at an anchorage is somewhere else. A spot
 * is a run of photographs each within SPOT_M of the one before -- a stack at an
 * anchorage, or an unbroken stretch under way. */
const SPOT_M = 250;

function metresApart(p, q) {
  const k = Math.cos((p.lat + q.lat) * Math.PI / 360);
  return Math.hypot((p.lon - q.lon) * 111320 * k, (p.lat - q.lat) * 110540);
}

function spotAround(i) {
  const s = state.shown;
  let a = i, b = i;
  while (a > 0 && metresApart(s[a - 1], s[a]) <= SPOT_M) a--;
  while (b < s.length - 1 && metresApart(s[b], s[b + 1]) <= SPOT_M) b++;
  return [a, b];
}

// How long the notice stays. Timed here rather than by a CSS animation: the
// stylesheet cuts every animation to nothing for a reader who has asked for
// reduced motion, and the notice went with it in a blink.
const MOVED_MS = 3500;
let movedTimer = 0;

function announceMove(from, i) {
  const el = $('#viewer-moved');
  const p = state.shown[i];
  const d = from ? metresApart(from, p) : 0;
  clearTimeout(movedTimer);
  if (d <= SPOT_M) { el.hidden = true; return; }
  const [a, b] = spotAround(i);
  const n = b - a + 1;
  el.textContent = `A different spot · ${fmtDistance(Math.round(d))} away` +
    (n > 1 ? ` · ${n} photographs here` : '');
  el.hidden = false;
  movedTimer = setTimeout(() => { el.hidden = true; }, MOVED_MS);
}

function whenText(p) {
  // A day off a WhatsApp filename is a date somebody's phone wrote, not a
  // measurement. export.py ships the flag; this is the only place a human
  // sees it, so this is where the hedge has to be said.
  const day = p.day && p.day_provisional ? `${p.day}, at a guess` : p.day;
  if (!p.utc) return day ? `${day} — time unknown` : 'time unknown';
  const d = new Date(p.utc);
  const edt = new Date(d.getTime() - 4 * 3600 * 1000);
  const hh = String(edt.getUTCHours()).padStart(2, '0');
  const mm = String(edt.getUTCMinutes()).padStart(2, '0');
  // Away from Abaco the clock shown is still the trip's, and says so: 04:00 on
  // a photograph taken at Dallas was three in the morning there.
  if (day) return `${day} · ${hh}:${mm}${p.tier === 'travel' ? ' Bahamas time' : ''}`;
  // Off the trip's days -- Portland, an airport -- there is no day to name, and
  // a bare clock time says neither which date nor whose clock.
  const date = edt.toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).replace(',', '');
  return `${date} · ${hh}:${mm} Bahamas time`;
}

function fmtDistance(m) {
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  if (m >= 100) return `${Math.round(m / 10) * 10} m`;
  return `${m} m`;
}

/* The viewer says it is a modal dialog, so it has to behave like one for someone
 * not using a pointer: focus goes into it when it opens, cannot wander off to the
 * controls behind it while it is open, and goes back to whatever opened it when
 * it closes. `inert` does the middle part -- everything behind is unfocusable and
 * unclickable -- which is sturdier than catching Tab by hand. */
const BEHIND_VIEWER = ['#map', '#masthead', '#panel-toggle', '#panel', '#scalebar',
                       '#clusters', '#tray', '#notice'];

function revealViewer() {
  const v = $('#viewer');
  if (!v.hidden) return;            // already open: previous/next, or a renumbering
  state.viewerReturn = document.activeElement;
  v.hidden = false;
  document.body.classList.add('viewing');
  for (const sel of BEHIND_VIEWER) { const el = $(sel); if (el) el.inert = true; }
  $('#viewer-close').focus();
}

function closeViewer() {
  const wasOpen = !$('#viewer').hidden;
  $('#viewer').hidden = true;
  $('#viewer-moved').hidden = true;
  document.body.classList.remove('viewing');
  for (const sel of BEHIND_VIEWER) { const el = $(sel); if (el) el.inert = false; }
  if (wasOpen) {
    const back = state.viewerReturn;
    state.viewerReturn = null;
    if (back && document.contains(back) && back.focus) back.focus();
  }
  // state.at is only meaningful while the viewer is open on a chart photograph.
  // Left behind, it would tell refreshPhotos a closed viewer was still showing it.
  state.at = null;
  map.getSource('uncertainty').setData(emptyFC());
  map.getSource('selected').setData(emptyFC());
}

function wireViewer() {
  $('#viewer-close').addEventListener('click', closeViewer);
  // The null checks cover a photograph opened from the tray: it is not in
  // state.shown, so there is nowhere for previous or next to go from it.
  $('#viewer-prev').addEventListener('click',
    () => { if (state.at != null) showAt(Math.max(0, state.at - 1)); });
  $('#viewer-next').addEventListener('click',
    () => { if (state.at != null) showAt(Math.min(state.shown.length - 1, state.at + 1)); });
  document.addEventListener('keydown', (e) => {
    if ($('#viewer').hidden && $('#tray').hidden) return;
    // One layer at a time: Escape on a tray photograph goes back to the tray,
    // with focus on the thumbnail it came from, and a second closes the tray.
    if (e.key === 'Escape') {
      if (!$('#viewer').hidden) closeViewer(); else closeTray();
      return;
    }
    if ($('#viewer').hidden || state.at == null) return;
    if (e.key === 'ArrowLeft') showAt(Math.max(0, state.at - 1));
    if (e.key === 'ArrowRight') showAt(Math.min(state.shown.length - 1, state.at + 1));
  });
  // The dots and counts are drawn on a canvas and open on a click, which leaves
  // a keyboard nowhere to start. This is the start; the arrows do the rest.
  if ($('#photos-browse')) {
    $('#photos-browse').addEventListener('click', () => {
      if (state.shown.length) openViewer(state.shown[0].id);
    });
  }
  $('#tray-open').addEventListener('click', () => {
    $('#tray').hidden = false;
    $('#tray-close').focus();
  });
  $('#tray-close').addEventListener('click', closeTray);
}

function closeTray() {
  if ($('#tray').hidden) return;
  $('#tray').hidden = true;
  $('#tray-open').focus();
}

/* ------------------------------------------------------------------- tray --- */
// Rebuilt by refreshPhotos on every day toggle: "unticked" has to mean the same
// thing in the tray as on the chart. A photograph with no day has no checkbox
// to answer to, so it is always listed.
function buildTray() {
  const off = state.offChart.filter((p) => !p.day || state.days.has(p.day));
  $('#tray-count').textContent = `(${off.length})`;
  const heading = {
    unplaced: 'Ashore, or between receivers',
    travel: 'Travel',
    screenshot: 'Screenshots',
  };
  const why = {
    travel: 'Taken away from Abaco — the flights, and home either side. '
          + 'Plotting Portland on a chart of the Sea of Abaco would be nonsense.',
    unplaced: 'No position, for one of three reasons: the moment falls outside '
            + 'both receivers, which is most of the arrival and departure days; '
            + 'the boat was moving between satellite reports; or the file reached '
            + 'us with its timestamp stripped. The evenings on a mooring used to '
            + 'be here and are on the chart now. Open one to see which it is.',
    screenshot: 'Phone screenshots — flight trackers, a lock screen. Nothing to '
              + 'place: these are the shape of a screen, not of a camera.',
  };
  const byTier = {};
  for (const p of off) (byTier[p.tier] = byTier[p.tier] || []).push(p);
  const body = $('#tray-body');
  body.innerHTML = '';
  for (const tier of ['unplaced', 'travel', 'screenshot']) {
    const list = byTier[tier];
    if (!list) continue;
    const h = document.createElement('h3');
    h.textContent = `${heading[tier] || tier} — ${list.length}`;
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
        // A button, not a bare image: an <img> with a click handler cannot be
        // reached with Tab or opened with Enter, so the tray could be opened
        // from the keyboard and nothing in it could.
        const what = `${p.camera}${p.utc ? ' · ' + whenText(p) : ''}`;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'thumb';
        btn.title = what;
        btn.setAttribute('aria-label', `Open photograph: ${what}`);
        const img = document.createElement('img');
        // Before src: Safari and Firefox start the fetch when src is set, and
        // a flag that arrives afterwards is too late to make it lazy.
        img.loading = 'lazy';            // only what is on screen is fetched
        img.decoding = 'async';
        img.src = p.thumb;
        img.alt = '';                    // the button carries the name
        btn.append(img);
        btn.addEventListener('click', () => openOffChart(p));
        grid.append(btn);
      }
      body.append(dh, grid);
    }
  }
}

function openOffChart(p) {
  // Same viewer, but there is no position to show or ring to draw -- and no
  // index either: state.at must not go on pointing at whatever chart photograph
  // it last held, or a day toggle would swap this one for that one.
  state.at = null;
  $('#viewer-img').src = p.view;
  $('#viewer-img').alt = '';
  $('#viewer-when').textContent = whenText(p);
  $('#viewer-note').textContent = p.note || '';
  $('#viewer-meta').textContent = p.camera || '';
  $('#viewer-spot').textContent = '';
  $('#viewer-moved').hidden = true;
  $('#viewer-prev').hidden = true;
  $('#viewer-next').hidden = true;
  revealViewer();
  map.getSource('uncertainty').setData(emptyFC());
  map.getSource('selected').setData(emptyFC());
}
