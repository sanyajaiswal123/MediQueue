/**
 * One shared Lenis smooth-scroll instance for every page.
 * Other modules (landing animation, city dashboard) call getLenis() instead of creating their own.
 * Returns null under prefers-reduced-motion, so callers must handle that.
 *
 * Nested scrollers (the styled dropdown list) carry `data-lenis-prevent` so the wheel scrolls them, not the page.
 */
import Lenis from 'lenis';

let instance;

export function getLenis() {
  if (instance !== undefined) return instance;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    instance = null;
    return instance;
  }
  instance = new Lenis({ lerp: 0.11, autoRaf: true });
  return instance;
}
