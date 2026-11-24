// Fleet Architect's tape measure. Loads one page in headless Chrome at phone and desktop size,
// measures hard facts (overflow, text size, tap targets, first-screen buttons) and saves screenshots.
// Usage: node architect_measure.mjs <file-or-url> <out-dir> [chrome.exe]
// Prints one JSON object on stdout. Facts here are measured, not judged; the model does the judging.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [target, outDir, chromePath = 'C:/Program Files/Google/Chrome/Application/chrome.exe'] = process.argv.slice(2);
if (!target || !outDir) { console.error('usage: node architect_measure.mjs <file-or-url> <out-dir>'); process.exit(2); }
const url = /^https?:/i.test(target) ? target : pathToFileURL(resolve(target)).href;
const PORT = 9300 + Math.floor(Math.random() * 400);
const prof = mkdtempSync(join(tmpdir(), 'arch-'));
const chrome = spawn(chromePath, ['--headless=new', '--hide-scrollbars', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${prof}`, '--window-size=1440,900', 'about:blank']);
const sleep = ms => new Promise(r => setTimeout(r, ms));

let targets;
for (let i = 0; i < 60 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); } catch { await sleep(250); }
}
if (!targets) { chrome.kill(); console.error('chrome did not start'); process.exit(1); }
const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => (ws.onopen = r));
let id = 0; const pend = new Map(); const errors = []; let loaded = false;
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === 'Page.loadEventFired') loaded = true;
  if (m.method === 'Runtime.exceptionThrown') errors.push('JS error: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).slice(0, 200));
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(('Load error: ' + m.params.entry.text + ' ' + (m.params.entry.url || '')).slice(0, 200));
};
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');

const MEASURE = `(() => {
  const vw = innerWidth, vh = innerHeight;
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/)[0] : '');
  const shown = el => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0 && r.width > 0 && r.height > 0; };
  const docW = document.documentElement.scrollWidth;
  const overflow = docW > vw + 1;
  const wide = [];
  if (overflow) for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > vw + 1 && getComputedStyle(el).position !== 'fixed') { wide.push(name(el) + ' right edge ' + Math.round(r.right) + 'px'); if (wide.length >= 6) break; }
  }
  // smallest visible text
  const small = []; let minFont = 99;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode.textContent.trim(); const el = walker.currentNode.parentElement;
    if (!t || !el || !shown(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < minFont) minFont = fs;
    if (fs < 12 && small.length < 5) small.push(name(el) + ' ' + fs + 'px "' + t.slice(0, 30) + '"');
  }
  // tap targets and first-screen buttons
  const taps = [...document.querySelectorAll('a[href], button, input[type=submit], [role=button]')].filter(shown);
  const tiny = taps.filter(el => { const r = el.getBoundingClientRect(); return r.height < 40 || r.width < 40; });
  const firstScreen = taps.filter(el => { const r = el.getBoundingClientRect(); return r.top < vh && r.bottom > 0 && el.textContent.trim(); })
    .map(el => el.textContent.trim().replace(/\\s+/g, ' ').slice(0, 40));
  // is the headline / each first-screen button really on top, or covered (e.g. by a hero overlay)?
  // Lesson 2026-11-18: the Example Roofing draft's ::before overlay sat over its h1 and buttons.
  const covered = [];
  for (const el of [...document.querySelectorAll('h1'), ...taps]) {
    const r = el.getBoundingClientRect();
    if (!(r.top < vh && r.bottom > 0) || !shown(el)) continue;
    const cx = Math.min(Math.max(r.left + r.width / 2, 0), vw - 1), cy = Math.min(Math.max(r.top + r.height / 2, 0), vh - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (hit && hit !== el && !el.contains(hit)) covered.push(name(el) + ' "' + el.textContent.trim().slice(0, 25) + '" under ' + name(hit)
      + (hit.contains(el) ? " (its own container's ::before/::after overlay is painted on top: give the content position:relative and z-index:1)" : ''));
  }
  const imgs = [...document.images];
  return {
    viewport: vw + 'x' + vh, page_height: document.documentElement.scrollHeight,
    sideways_scroll: overflow, page_width: docW, too_wide: wide,
    smallest_text_px: minFont === 99 ? null : minFont, text_under_12px: small,
    tap_targets: taps.length, tap_targets_under_40px: tiny.length,
    tap_examples: tiny.slice(0, 5).map(el => name(el) + ' "' + el.textContent.trim().slice(0, 25) + '"'),
    first_screen_links: firstScreen.slice(0, 8),
    covered_on_first_screen: covered.slice(0, 6),
    h1_count: document.querySelectorAll('h1').length,
    images: imgs.length, images_no_alt: imgs.filter(i => !i.hasAttribute('alt')).length,
    images_broken: imgs.filter(i => i.complete && i.naturalWidth === 0).map(i => i.getAttribute('src')).slice(0, 5),
    has_viewport_meta: !!document.querySelector('meta[name=viewport]'),
    title: document.title,
  };
})()`;

const out = { url, sizes: {}, errors };
for (const [label, w, h, mobile] of [['phone', 390, 844, true], ['desktop', 1440, 900, false]]) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile });
  loaded = false;
  await send('Page.navigate', { url });
  for (let i = 0; i < 80 && !loaded; i++) await sleep(100);
  await sleep(1500); // fonts, entrance animations
  // scroll through once so lazy images and scroll-reveal effects show, then back to the top
  await ev(`(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) { scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } scrollTo(0, 0); })()`);
  await sleep(600);
  const m = await ev(MEASURE);
  const first = join(outDir, `${label}-first-screen.png`);
  writeFileSync(first, Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64'));
  // rest of the page, one screen per file, up to 4 more screens
  const rest = [];
  for (let s = 1; s <= 4 && s * h < m.page_height; s++) {
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: s * h, width: w, height: Math.min(h, m.page_height - s * h), scale: 1 } });
    const f = join(outDir, `${label}-screen-${s + 1}.png`);
    writeFileSync(f, Buffer.from(shot.result.data, 'base64'));
    rest.push(f);
  }
  out.sizes[label] = { ...m, shots: [first, ...rest] };
}
ws.close(); chrome.kill();
await sleep(300);
try { rmSync(prof, { recursive: true, force: true }); } catch {}
console.log(JSON.stringify(out));
