#!/usr/bin/env node
/* The chart, driven in a real browser: the things only a click can show.
 *
 *     node map/browser_check.js http://127.0.0.1:8123/
 *
 * Run by `python -m map.tests`, which serves site_build for it and skips this
 * when the driver is not installed. It is not a dependency of the build:
 *
 *     npm install --no-save playwright-core      # node_modules is ignored
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
  await page.goto(process.argv[2], { waitUntil: 'load' });
  await page.waitForFunction(
    () => typeof state !== 'undefined' && state.stories && state.onChart, null, { timeout: 60000 });

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
  const laid = await page.evaluate(() => {
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
    return { names, dots, labels: state.placeMarkers.length, top: map.getMaxZoom() };
  });
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

  // The dots open on a click; a keyboard gets in by the panel.
  await page.click('#days-all');
  await page.focus('#photos-browse');
  await page.keyboard.press('Enter');
  const first = await page.evaluate(() => ({
    open: !document.querySelector('#viewer').hidden, at: state.at,
    count: document.querySelector('#photos-browse').textContent }));
  await page.keyboard.press('ArrowRight');
  say('a keyboard can open the chart\'s photographs and step through them',
      first.open && first.at === 0 && await page.evaluate(() => state.at === 1)
      && /\(\d+\)/.test(first.count), JSON.stringify(first));
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
  await browser.close();
})().catch((e) => { say('the browser check ran to the end', false, String(e)); process.exit(1); });
