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

  // A story's popup goes when its day does, and not when another day does.
  await page.check('#chart-layers input[data-layer="stories"]');
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
