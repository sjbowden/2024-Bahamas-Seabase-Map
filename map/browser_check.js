#!/usr/bin/env node
/* The chart, driven in a real browser: the things only a click can show.
 *
 *     node map/browser_check.js http://127.0.0.1:8123/
 *
 * Run by `python -m map.tests`, which serves site_build for it and skips this
 * when the driver is not installed. It is not a dependency of the build:
 *
 *     npm install --no-save playwright-core@1.64.0      # node_modules is ignored
 *
 * Uses the Chrome already on the machine; CHROME=/path/to/chrome names another.
 * Prints one JSON object per check: {"name": ..., "ok": ..., "detail": ...}.
 */
const { chromium } = require('playwright-core');

const say = (name, ok, detail = '') => console.log(JSON.stringify({ name, ok: !!ok, detail }));

(async () => {
  let browser;
  try {
    browser = await chromium.launch({
      ...(process.env.CHROME ? { executablePath: process.env.CHROME } : { channel: 'chrome' }),
      // MapLibre wants WebGL, and a headless machine has no GPU to give it.
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
             '--ignore-gpu-blocklist'],
    });
  } catch (e) {
    // The driver without a browser to drive is a machine that cannot run this,
    // not a chart that failed it.
    console.log(JSON.stringify({ skip: String(e.message || e).split('\n')[0] }));
    return;
  }
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  // No photograph in the archive has a position and no date, so one is invented
  // here, on the way to the page: a camera-placed record with its day taken off.
  await page.route('**/data/photos.json', async (route) => {
    const r = await route.fetch();
    const all = await r.json();
    const src = all.find((p) => p.tier === 'gps');
    all.push({ ...src, id: 'pTEST', day: null, utc: null, time: null });
    await route.fulfill({ response: r, json: all });
  });
  const asked = [];
  page.on('request', (r) => asked.push(r.url()));
  const fetched = (name) => asked.some((u) => u.includes(`coast.${name}.geojson`));
  await page.goto(process.argv[2], { waitUntil: 'load' });
  await page.waitForFunction(
    () => typeof state !== 'undefined' && state.stories && state.onChart, null, { timeout: 60000 });

  // The fine coastline is 1.2 MB and is for someone who has zoomed in.
  await page.waitForFunction(() => map.isSourceLoaded('coast-coarse'));
  const early = { coarse: fetched('coarse'), fine: fetched('fine'),
                  zoom: await page.evaluate(() => map.getZoom()) };
  await page.evaluate(() => map.jumpTo({ zoom: 14 }));
  await page.waitForFunction(() => map.querySourceFeatures('coast-fine').length > 0,
                             null, { timeout: 30000 });
  say('the fine coastline is fetched on zooming in, and not before',
      early.coarse && !early.fine && fetched('fine'), JSON.stringify(early));
  await page.evaluate((z) => map.jumpTo({ zoom: z }), early.zoom);

  const popups = () => page.locator('.story-popup').count();
  const openFirstStory = () => page.evaluate(() => {
    const s = state.stories.find((o) => o.el.style.display !== 'none');
    s.el.click();
    return s.p.day;
  });

  await page.check('#chart-layers input[data-layer="stories"]');

  // Every name against every other, and every story dot against every name, at
  // each tenth of a zoom the chart allows. The lines of text are what is
  // compared, not the padded box around them. Names are HTML, the same size at
  // every zoom, so this is a question about positions and the zoom each name
  // first shows at -- which is what changes when a name is added.
  const sweep = (pg) => pg.evaluate(() => {
    const name = (el) => el.textContent.replace(/\s+/g, ' ').trim();
    const lines = (el) => {
      const r = document.createRange();
      r.selectNodeContents(el);
      const rows = [];
      for (const c of r.getClientRects()) {
        if (c.width < 1) continue;
        const row = rows.find((q) => Math.abs(q.top - c.top) < 3);
        if (!row) rows.push({ left: c.left, right: c.right, top: c.top, bottom: c.bottom });
        else {
          row.left = Math.min(row.left, c.left);
          row.right = Math.max(row.right, c.right);
          row.bottom = Math.max(row.bottom, c.bottom);
        }
      }
      return rows;
    };
    const hit = (a, b) => Math.min(a.right, b.right) > Math.max(a.left, b.left)
      && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top);
    const shown = (el) => getComputedStyle(el).display !== 'none';
    const was = { center: map.getCenter(), zoom: map.getZoom() };
    const names = {}, dots = {};
    const note = (into, k, z) => { (into[k] = into[k] || [z, z])[1] = z; };
    for (let i = Math.round(map.getMinZoom() * 10); i <= Math.round(map.getMaxZoom() * 10); i++) {
      map.jumpTo({ zoom: i / 10 });
      const labs = state.placeMarkers.filter((pm) => shown(pm.el))
        .map((pm) => ({ name: name(pm.el), rows: lines(pm.el) }));
      for (let a = 0; a < labs.length; a++) {
        for (let b = a + 1; b < labs.length; b++) {
          if (labs[a].rows.some((r) => labs[b].rows.some((q) => hit(r, q)))) {
            note(names, `${labs[a].name} × ${labs[b].name}`, i / 10);
          }
        }
      }
      for (const s of state.stories.filter((o) => shown(o.el))) {
        const d = s.el.getBoundingClientRect();
        for (const l of labs) {
          if (l.rows.some((r) => hit(r, d))) note(dots, `${s.p.title} × ${l.name}`, i / 10);
        }
      }
    }
    map.jumpTo(was);
    return { names, dots, labels: state.placeMarkers.length, top: map.getMaxZoom(),
             shown: state.placeMarkers.filter((pm) => shown(pm.el)).length };
  });
  const laid = await sweep(page);
  const span = ([k, [a, b]]) => `${k} z${a}-${b}`;
  const crossed = Object.entries(laid.names);
  say('no two names overlap at any zoom', crossed.length === 0,
      crossed.map(span).join('; ') || `${laid.labels} names`);
  // A dot is drawn where its story happened and a name where its place is, so
  // zoomed well out some dots are on names: the chart opens at z9.9 on a phone
  // and z10.4 on a desktop, and the last of them is clear by z11.3. A name with
  // a story set at its own point starts beside the dot instead (place-left).
  const CLEAR_BY = 11.5;
  const late = Object.entries(laid.dots).filter(([, z]) => z[1] >= CLEAR_BY);
  say(`no story dot is on a name from z${CLEAR_BY} in`, late.length === 0,
      late.map(span).join('; ')
      || `${Object.keys(laid.dots).length} cross further out, the last `
      + `to z${Math.max(0, ...Object.values(laid.dots).map((z) => z[1]))}`);

  // A story's popup goes when its day does, and not when another day does.
  const day = await openFirstStory();
  say('a story opens in a popup', await popups() === 1, day);
  await page.uncheck(`#days input[data-day="${day}"]`);
  // Closed, or left holding another day's story from the same spot.
  say('unticking its day takes its stories out of the popup', await page.evaluate(
    (d) => !(state.storyPopupOf || []).some((o) => o.p.day === d)
      && ![...document.querySelectorAll('.story-popup .popup-route')]
        .some((e) => e.textContent.includes(d)), day));
  await page.check(`#days input[data-day="${day}"]`);
  await openFirstStory();
  await page.click('#days-none');
  say('and so does "none"', await popups() === 0);
  await page.click('#days-all');
  await openFirstStory();
  const other = await page.evaluate(() => {
    const mine = new Set(state.storyPopupOf.map((o) => o.p.day));
    return [...document.querySelectorAll('#days input[data-day]')]
      .map((c) => c.dataset.day).find((d) => !mine.has(d));
  });
  await page.uncheck(`#days input[data-day="${other}"]`);
  say('unticking some other day leaves it open', await popups() === 1, other);

  // Two days' stories at one anchorage share a popup, and each leaves with its
  // own day. Zoomed out until the nearest such pair is one tap.
  await page.click('#days-all');
  const pair = await page.evaluate(() => {
    map.jumpTo({ zoom: 10 });
    for (const s of state.stories) {
      openStory(s);
      const days = [...new Set(state.storyPopupOf.map((o) => o.p.day))];
      if (days.length > 1) return { days, n: state.storyPopupOf.length };
    }
    return null;
  });
  if (pair) {
    await page.uncheck(`#days input[data-day="${pair.days[0]}"]`);
    const left = await page.evaluate(() => ({
      of: state.storyPopupOf.map((o) => o.p.day),
      drawn: document.querySelectorAll('.story-popup .story-text').length }));
    say('a popup of two days keeps the story whose day is still ticked',
        await popups() === 1 && left.of.length && left.drawn === left.of.length
        && !left.of.includes(pair.days[0]), JSON.stringify(left));
    await page.click('.story-popup .maplibregl-popup-close-button');
    say('and a popup closed by hand answers for no story',
        await page.evaluate(() => !state.storyPopup && !state.storyPopupOf));
  } else {
    say('a popup of two days keeps the story whose day is still ticked', false,
        'no two stories of different days share a tap at z10');
  }

  // A photograph that knows where and not when answers to no day's checkbox.
  await page.click('#days-all');
  await page.check('#chart-layers input[data-layer="photos"]');
  const shown = () => page.evaluate(() => state.shown.some((p) => p.id === 'pTEST'));
  say('a located photograph with no day is on the chart', await shown());
  await page.click('#days-none');
  say('and stays there with every day unticked', await shown());
  await page.evaluate(() => openViewer('pTEST'));
  say('and opens in the viewer',
      await page.evaluate(() => !document.querySelector('#viewer').hidden));
  await page.click('#viewer-close');

  // Off the trip's days a caption has no day to lead with, and says the date.
  const when = await page.evaluate(() => whenText({ utc: '2024-03-20T05:38:26Z', day: null }));
  say('a photograph off the trip\'s days is captioned with its date',
      when === 'Wed 20 Mar · 01:38 Bahamas time', when);
  const away = await page.evaluate(() => [
    whenText({ utc: '2024-03-22T08:00:00Z', day: 'Fri 22 Mar', tier: 'travel' }),
    whenText({ utc: '2024-03-22T08:00:00Z', day: 'Fri 22 Mar', tier: 'gps' })]);
  const loose = await page.evaluate(() => whenText(
    { utc: null, day: 'Mon 25 Mar', day_provisional: true, clock: '17:46' }));
  say('a photograph with only its camera\'s clock says that is whose time it is',
      loose === 'Mon 25 Mar, at a guess · 17:46 by the camera\'s own clock', loose);
  say('and one taken away from Abaco on a trip day says whose clock it is',
      away[0] === 'Fri 22 Mar · 04:00 Bahamas time' && away[1] === 'Fri 22 Mar · 04:00',
      away.join(' | '));
  const idle = await page.evaluate(() => {
    const b = document.querySelector('#photos-browse');
    const was = b.disabled;
    b.disabled = true;
    const line = getComputedStyle(b).textDecorationLine;
    b.disabled = was;
    return line;
  });
  say('with nothing to browse, the browse button does not look like a link',
      idle === 'none', idle);

  // The dots open on a click; a keyboard gets in by the panel, which opens a
  // sheet of thumbnails for the photographs on the chart, as the other link
  // does for the ones that are not.
  await page.click('#days-all');
  await page.focus('#photos-browse');
  await page.keyboard.press('Enter');
  const tray = await page.evaluate(() => ({
    open: !document.querySelector('#tray').hidden,
    title: document.querySelector('#tray h2').textContent,
    thumbs: document.querySelectorAll('#tray-body .thumb').length,
    shown: state.shown.length,
    days: [...document.querySelectorAll('#tray-body h4')].map((h) => h.textContent.split(' · ')[0]),
    viewer: !document.querySelector('#viewer').hidden,
    label: document.querySelector('#photos-browse').textContent }));
  say('the browse link opens thumbnails of the chart\'s photographs, day by day',
      tray.open && !tray.viewer && tray.title === 'On the chart'
      && tray.thumbs === tray.shown && tray.thumbs > 2000 && tray.days.length >= 7
      && /\(\d+\)/.test(tray.label), JSON.stringify({ ...tray, days: tray.days.length }));
  await page.focus('#tray-body .thumb');
  await page.keyboard.press('Enter');
  const first = await page.evaluate(() => ({
    open: !document.querySelector('#viewer').hidden, at: state.at }));
  await page.keyboard.press('ArrowRight');
  say('a keyboard can open one of them and step on through the rest',
      first.open && first.at === 0 && await page.evaluate(() => state.at === 1),
      JSON.stringify(first));
  await page.keyboard.press('Escape');
  const backAt = await page.evaluate(() => ({
    viewer: !document.querySelector('#viewer').hidden,
    tray: !document.querySelector('#tray').hidden,
    focus: document.activeElement.className }));
  await page.keyboard.press('Escape');
  say('closing the photograph returns to the thumbnails, and again to the chart',
      !backAt.viewer && backAt.tray && backAt.focus === 'thumb'
      && await page.evaluate(() => document.querySelector('#tray').hidden
        && document.activeElement.id === 'photos-browse'), JSON.stringify(backAt));
  // With the sheet open: a day toggle hides that day's block and keeps the
  // reader's place; closing a photograph comes back to the one being looked
  // at; and unticking Photographs takes the sheet away with them.
  // At this window's size the open sheet lies over most of the panel, so the
  // boxes under it are clicked as a taller window, or a keyboard, would.
  const press = (sel) => page.evaluate((q) => document.querySelector(q).click(), sel);
  await page.click('#photos-browse');
  const made = await page.evaluate(() => {
    const t = document.querySelector('#tray');
    t.scrollTop = 4000;
    return { thumbs: document.querySelectorAll('#tray-body .thumb').length, top: t.scrollTop };
  });
  await press('#days input[data-day="Thu 28 Mar"]');
  const kept = await page.evaluate(() => ({
    thumbs: document.querySelectorAll('#tray-body .thumb').length,
    top: document.querySelector('#tray').scrollTop,
    thu: document.querySelector('#tray-body .tray-day[data-day="Thu 28 Mar"]').hidden,
    others: [...document.querySelectorAll('#tray-body .tray-day')].filter((b) => !b.hidden).length,
    why: document.querySelector('#tray > .tray-why').textContent,
    shown: state.shown.length }));
  say('a day toggle hides that day in the open sheet and keeps the reader\'s place',
      kept.thumbs === made.thumbs && made.top > 1000 && kept.top === made.top && kept.thu
      && kept.others >= 6 && kept.why.startsWith(`${kept.shown} photographs`),
      JSON.stringify({ made, kept }));
  await press('#days input[data-day="Thu 28 Mar"]');
  await page.evaluate(() => document.querySelector('#tray-body .thumb').click());
  for (let k = 0; k < 40; k++) await page.keyboard.press('ArrowRight');
  const stepped = await page.evaluate(() => state.shown[state.at].id);
  await page.keyboard.press('Escape');
  const landed = await page.evaluate(() => {
    const a = document.activeElement, r = a.getBoundingClientRect();
    return { id: a.dataset.id, cls: a.className, inView: r.top >= 0 && r.bottom <= innerHeight };
  });
  say('closing a photograph stepped to from the sheet lands on its own thumbnail',
      landed.cls === 'thumb' && landed.id === stepped && landed.inView,
      JSON.stringify({ stepped, landed }));
  await page.focus('#tray-close');
  await press('#chart-layers input[data-layer="photos"]');
  const gone = await page.evaluate(() => ({
    tray: document.querySelector('#tray').hidden,
    left: document.querySelectorAll('#tray-body .thumb').length,
    focus: document.activeElement.dataset.layer || document.activeElement.id }));
  say('unticking Photographs closes the sheet and leaves focus somewhere real',
      gone.tray && gone.left === 0 && gone.focus === 'photos', JSON.stringify(gone));
  await page.check('#chart-layers input[data-layer="photos"]');

  await page.click('#tray-open');
  const offTray = await page.evaluate(() => ({
    title: document.querySelector('#tray h2').textContent,
    thumbs: document.querySelectorAll('#tray-body .thumb').length,
    off: state.offChart.filter((p) => !p.day || state.days.has(p.day)).length }));
  say('and the other link still opens the ones not on the chart',
      offTray.title === 'Not on the chart' && offTray.thumbs === offTray.off && offTray.off > 0,
      JSON.stringify(offTray));
  await page.keyboard.press('Escape');

  // A photograph placed from the track sits on the line. A click on it opens
  // the photograph and does not leave the day's popup underneath.
  await page.click('#days-all');
  const spot = await page.evaluate(async () => {
    const idle = () => new Promise((r) => map.once('idle', r));
    for (const p of state.shown.filter((q) => q.tier === 'calibrated').slice(0, 200)) {
      map.jumpTo({ center: [p.lon, p.lat], zoom: 17 });
      await idle();
      const at = map.project([p.lon, p.lat]);
      const on = (layers) => map.queryRenderedFeatures([at.x, at.y], { layers }).length;
      if (on(['clusters', 'photo-points']) && on(['track-afloat'])) {
        const box = map.getCanvas().getBoundingClientRect();
        return { x: box.left + at.x, y: box.top + at.y, id: p.id };
      }
    }
    return null;
  });
  if (spot) {
    await page.mouse.click(spot.x, spot.y);
    await page.waitForTimeout(600);
    const after = await page.evaluate(() => ({
      viewer: !document.querySelector('#viewer').hidden,
      popups: document.querySelectorAll('.maplibregl-popup:not(.story-popup)').length }));
    say('a click on a photograph on the track opens no day popup',
        after.viewer && after.popups === 0, JSON.stringify({ ...after, id: spot.id }));
  } else {
    say('a click on a photograph on the track opens no day popup', false,
        'no calibrated photograph was found drawn on the track');
  }

  say('the page raised no errors', errors.length === 0, errors.join('; '));

  // The same again at the size of a phone, which is how most of the crew will
  // open it: its own stylesheet rules, its own opening zoom, the panel as a
  // sheet at the foot of the screen, and a finger and not a pointer.
  const PHONE = { width: 390, height: 844 };
  const phone = await browser.newPage({
    viewport: PHONE, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const phoneErrors = [];
  phone.on('pageerror', (e) => phoneErrors.push(String(e)));
  await phone.goto(process.argv[2], { waitUntil: 'load' });
  await phone.waitForFunction(
    () => typeof state !== 'undefined' && state.stories && state.onChart, null, { timeout: 60000 });
  const shut = await phone.evaluate(() => document.querySelector('#panel').hidden);
  await phone.tap('#panel-toggle');
  const sheet = await phone.evaluate(() => {
    const p = document.querySelector('#panel'), r = p.getBoundingClientRect();
    return { hidden: p.hidden, left: r.left, right: r.right, top: r.top, bottom: r.bottom,
             expanded: document.querySelector('#panel-toggle').getAttribute('aria-expanded') };
  });
  say('on a phone the panel starts shut and opens as a sheet inside the screen',
      shut && !sheet.hidden && sheet.expanded === 'true' && sheet.left >= 0
      && sheet.right <= PHONE.width && sheet.top >= PHONE.height * 0.4
      && sheet.bottom <= PHONE.height, JSON.stringify(sheet));
  await phone.check('#chart-layers input[data-layer="stories"]');
  const small = await sweep(phone);
  const smallCrossed = Object.entries(small.names);
  say('on a phone no two names overlap at any zoom', smallCrossed.length === 0,
      smallCrossed.map(span).join('; ') || `${small.shown} of ${small.labels} names shown`);
  const smallLate = Object.entries(small.dots).filter(([, z]) => z[1] >= CLEAR_BY);
  say(`on a phone no story dot is on a name from z${CLEAR_BY} in`, smallLate.length === 0,
      smallLate.map(span).join('; '));
  await phone.check('#chart-layers input[data-layer="photos"]');
  await phone.tap('#photos-browse');
  const strip = await phone.evaluate(() => {
    const t = document.querySelector('#tray'), r = t.getBoundingClientRect();
    return { open: !t.hidden, left: r.left, right: r.right, bottom: r.bottom,
             wide: document.documentElement.scrollWidth };
  });
  say('on a phone the thumbnails open as a sheet inside the screen',
      strip.open && strip.left >= 0 && strip.right <= PHONE.width
      && strip.bottom <= PHONE.height + 1 && strip.wide <= PHONE.width, JSON.stringify(strip));
  await phone.tap('#tray-body .thumb');
  await phone.waitForFunction(() => {
    const i = document.querySelector('#viewer-img');
    return i.complete && i.naturalWidth > 0;
  }, null, { timeout: 30000 });
  const seen = await phone.evaluate(() => {
    const box = (s) => document.querySelector(s).getBoundingClientRect();
    const img = box('#viewer-img'), x = box('#viewer-close'), cap = box('#viewer figcaption');
    return { open: !document.querySelector('#viewer').hidden,
             img: [Math.round(img.left), Math.round(img.right)],
             close: [Math.round(x.left), Math.round(x.top), Math.round(x.right)],
             caption: [Math.round(cap.left), Math.round(cap.right)],
             wide: document.documentElement.scrollWidth };
  });
  say('on a phone a photograph opens with its picture, caption and close button on screen',
      seen.open && seen.img[0] >= 0 && seen.img[1] <= PHONE.width
      && seen.img[1] - seen.img[0] > PHONE.width / 2
      && seen.close[0] >= 0 && seen.close[1] >= 0 && seen.close[2] <= PHONE.width
      && seen.caption[0] >= 0 && seen.caption[1] <= PHONE.width && seen.wide <= PHONE.width,
      JSON.stringify(seen));
  // The scale is a ruler: all of it has to be on the screen, and it has to be
  // as long as its label says. Zoomed all the way in, a tenth of a mile is
  // wider than a phone.
  const rulers = [];
  for (const zoom of [18, 16, 13, 8]) {
    await phone.evaluate((z) => map.jumpTo({ center: [-77, 26.5], zoom: z }), zoom);
    rulers.push(await phone.evaluate(() => {
      const r = document.querySelector('#scalebar-line').getBoundingClientRect();
      // Not the page's own measurement: the earth's girth at this latitude,
      // over the 512 px a tile is at zoom 0, doubled at each zoom after.
      const m = 40075016.686 * Math.cos(map.getCenter().lat * Math.PI / 180)
                / (512 * 2 ** map.getZoom());
      const said = document.querySelector('#scalebar-label').textContent;
      return { zoom: map.getZoom(), left: Math.round(r.left), right: Math.round(r.right),
               said, drawn: Math.round(r.width), true: Math.round(parseFloat(said) * 1852 / m) };
    }));
  }
  say('on a phone the scale is on the screen and as long as it says at every zoom',
      rulers.every((r) => r.left >= 0 && r.right <= PHONE.width && r.drawn >= 30
                   && r.drawn <= 160 && /^[\d.]+ nm$/.test(r.said)
                   && Math.abs(r.drawn - r.true) <= 3),
      JSON.stringify(rulers));
  // A chart with no size yet has no scale to draw; the ruler it had stands.
  const unsized = await phone.evaluate(() => {
    const real = map.unproject, was = document.querySelector('#scalebar-label').textContent;
    map.unproject = () => real.call(map, [0, 0]);
    try { window.__scaleBar(); } finally { map.unproject = real; }
    return { was, said: document.querySelector('#scalebar-label').textContent,
             width: document.querySelector('#scalebar-line').style.width };
  });
  say('a chart that cannot be measured keeps the scale it had',
      unsized.said === unsized.was && /^\d+px$/.test(unsized.width), JSON.stringify(unsized));
  say('the page raised no errors on a phone', phoneErrors.length === 0, phoneErrors.join('; '));
  await phone.close();

  // The chart's own data failing has to be said on the page, not in a console.
  const broken = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await broken.route('**/data/meta.json', (route) => route.fulfill({ status: 500, body: 'no' }));
  await broken.goto(process.argv[2], { waitUntil: 'load' });
  await broken.waitForFunction(() => !document.querySelector('#notice').hidden,
                               null, { timeout: 30000 }).catch(() => {});
  const told = await broken.evaluate(() => {
    const n = document.querySelector('#notice');
    return { shown: !n.hidden, text: n.textContent, link: !!n.querySelector('a[href="journal.html"]') };
  });
  say('a chart that cannot load its data says so, and offers the journal',
      told.shown && /could not load/i.test(told.text) && told.link, JSON.stringify(told));
  await broken.close();

  // The photographs failing to load takes their two links with it, and a click
  // that reaches one anyway does nothing rather than throwing.
  const blind = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const blindErrors = [];
  blind.on('pageerror', (e) => blindErrors.push(String(e)));
  await blind.route('**/data/photos.json', (route) => route.fulfill({ status: 500, body: 'no' }));
  await blind.goto(process.argv[2], { waitUntil: 'load' });
  await blind.waitForFunction(() => typeof state !== 'undefined' && state.stories && state.layers,
                              null, { timeout: 60000 });
  await blind.check('#chart-layers input[data-layer="photos"]');
  const dark = await blind.evaluate(() => {
    document.querySelector('#tray-open').click();
    document.querySelector('#photos-browse').click();
    return { links: document.querySelector('#photo-links').hidden,
             tray: document.querySelector('#tray').hidden };
  });
  say('with no photographs loaded their links are not offered and cannot throw',
      dark.links && dark.tray && blindErrors.length === 0,
      JSON.stringify({ ...dark, errors: blindErrors }));
  await blind.close();

  const holed = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await holed.route('**/data/tracks.geojson', (route) => route.fulfill({ status: 500, body: 'no' }));
  await holed.goto(process.argv[2], { waitUntil: 'load' });
  await holed.waitForFunction(() => !document.querySelector('#notice').hidden,
                              null, { timeout: 30000 }).catch(() => {});
  const gap = await holed.evaluate(() => document.querySelector('#notice').textContent);
  say('a chart missing its track says the track is missing', /the track/.test(gap), gap);
  await holed.close();
  await browser.close();
})().catch((e) => { say('the browser check ran to the end', false, String(e)); process.exit(1); });
