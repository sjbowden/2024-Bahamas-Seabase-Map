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
  const browser = await chromium.launch({
    ...(process.env.CHROME ? { executablePath: process.env.CHROME } : { channel: 'chrome' }),
    // MapLibre wants WebGL, and a headless machine has no GPU to give it.
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
           '--ignore-gpu-blocklist'],
  });
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
  say('unticking its day closes the popup', await popups() === 0);
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

  say('the page raised no errors', errors.length === 0, errors.join('; '));
  await browser.close();
})().catch((e) => { say('the browser check ran to the end', false, String(e)); process.exit(1); });
