/**
 * Light / dark theme. The inline script in base.html sets <html data-theme> before first paint
 * (saved choice, else the OS setting). This module wires the toggle buttons, saves the choice,
 * follows OS changes until the user picks one, and plays one motion: a circular reveal from the
 * button (View Transitions), skipped under reduced motion or where unsupported.
 */
const KEY = 'mq-theme';
const META = { light: '#f3f1ee', dark: '#121110' };

const saved = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const current = () => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', META[theme]);
  document.querySelectorAll('[data-theme-toggle]').forEach((b) => {
    b.setAttribute('aria-pressed', String(theme === 'dark'));
    b.setAttribute('title', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  });
}

function switchTo(theme, origin) {
  try { localStorage.setItem(KEY, theme); } catch { /* private mode: still switch for this page */ }
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!document.startViewTransition || reduce || !origin) { apply(theme); return; }
  const r = origin.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const t = document.startViewTransition(() => apply(theme));
  t.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: 520, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' },
    );
  });
}

export function initTheme() {
  apply(current());
  document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
    btn.addEventListener('click', () => switchTo(current() === 'dark' ? 'light' : 'dark', btn));
  });
  // Follow the OS until the user makes a choice.
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!saved()) apply(e.matches ? 'dark' : 'light');
  });
}
