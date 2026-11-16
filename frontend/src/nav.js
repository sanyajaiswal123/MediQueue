/**
 * In-page tab switching without a reload (progressive enhancement; the links still work without JavaScript).
 *
 *  - `[data-slider="pill|line"]` on a group: a highlight element slides to whichever child is marked
 *    aria-current ("page" or "true") or aria-pressed="true". It moves through every tab in between.
 *  - `a[data-swap="#selector"]` inside such a group: clicking slides the highlight at once, fetches the
 *    target page in the background, swaps only the matching region, and updates the address bar.
 *    Any failure falls back to a normal page load.
 */
import { initForms } from './forms.js';

const CURRENT = '[aria-current="page"], [aria-current="true"], [aria-pressed="true"]';
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function place(group, animate) {
  const thumb = group._thumb;
  const cur = group.querySelector(CURRENT);
  if (!thumb) return;
  if (!cur) { thumb.style.opacity = '0'; return; }
  thumb.style.opacity = '1';
  let { offsetLeft: x, offsetTop: y, offsetWidth: w, offsetHeight: h } = cur;
  if (group.dataset.slider === 'line') { y = y + h - 2; h = 2; }
  const quick = !animate || reduced();
  if (quick) thumb.style.transition = 'none';
  thumb.style.transform = `translate(${x}px, ${y}px)`;
  thumb.style.width = `${w}px`;
  thumb.style.height = `${h}px`;
  if (quick) { void thumb.offsetWidth; thumb.style.transition = ''; }
}

function setup(group) {
  if (group._thumb) return;
  const thumb = document.createElement('span');
  thumb.className = `slider__thumb slider__thumb--${group.dataset.slider}`;
  thumb.setAttribute('aria-hidden', 'true');
  group.prepend(thumb);
  group._thumb = thumb;
  group.classList.add('has-thumb');
  place(group, false);
  new MutationObserver(() => place(group, true)).observe(group, {
    attributes: true, subtree: true, attributeFilter: ['aria-current', 'aria-pressed'],
  });
  new ResizeObserver(() => place(group, false)).observe(group);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => place(group, false));
}

function scan() {
  document.querySelectorAll('[data-slider]').forEach(setup);
}

/* ---------- swap a region of the page ---------- */

let controller = null;
let swappedOnce = false;
const wait = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

async function swapTo(link) {
  const group = link.closest('[data-slider]');
  const region = document.querySelector(link.dataset.swap);
  if (!group || !region) { window.location.assign(link.href); return; }

  // Slide the highlight right away, keeping the same attribute style the group already uses.
  const previous = group.querySelector('[aria-current]');
  const value = previous ? previous.getAttribute('aria-current') : 'true';
  group.querySelectorAll('[aria-current]').forEach((el) => el.removeAttribute('aria-current'));
  link.setAttribute('aria-current', value);

  if (controller) controller.abort();
  controller = new AbortController();
  const mine = controller;
  region.classList.add('is-swapping');
  region.setAttribute('aria-busy', 'true');

  try {
    const [res] = await Promise.all([
      fetch(link.href, { credentials: 'same-origin', headers: { Accept: 'text/html' }, signal: mine.signal }),
      wait(220), // let the fade-out and the slide start
    ]);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const finalUrl = new URL(res.url);
    if (finalUrl.origin !== window.location.origin) throw new Error('redirected away');
    const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
    const next = doc.querySelector(link.dataset.swap);
    if (!next) throw new Error('region missing');

    region.innerHTML = next.innerHTML;
    // Refresh counts in the tabs (for example waiting numbers) from the new page.
    group.querySelectorAll('a[href]').forEach((a) => {
      const fresh = [...doc.querySelectorAll('[data-slider] a[href]')].find((x) => x.getAttribute('href') === a.getAttribute('href'));
      const count = a.querySelector('.tab__count');
      const freshCount = fresh && fresh.querySelector('.tab__count');
      if (count && freshCount) count.textContent = freshCount.textContent;
    });
    window.history.pushState({ swapped: true }, '', link.href);
    swappedOnce = true;
    if (doc.title) document.title = doc.title;
    region.classList.remove('is-swapping');
    region.removeAttribute('aria-busy');
    document.dispatchEvent(new CustomEvent('mq:swapped', { detail: { region } }));
  } catch (err) {
    if (err.name === 'AbortError') return; // a newer click took over
    window.location.assign(link.href);
  }
}

function onClick(e) {
  const link = e.target.closest('a[data-swap]');
  if (!link || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  if (link.target && link.target !== '_self') return;
  if (new URL(link.href).origin !== window.location.origin) return;
  e.preventDefault();
  swapTo(link);
}

export function initNav() {
  scan();
  document.addEventListener('click', onClick);
  document.addEventListener('mq:swapped', () => { initForms(); scan(); });
  // React widgets (city dashboard) render their tabs a moment after load: watch briefly for new groups.
  const watcher = new MutationObserver(scan);
  watcher.observe(document.body, { childList: true, subtree: true });
  setTimeout(() => watcher.disconnect(), 6000);
  // Back and forward after an in-page swap: reload the real page for that address.
  window.addEventListener('popstate', () => { if (swappedOnce) window.location.reload(); });
}
