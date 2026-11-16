/** Notices carousel on the staff overview: scroll-snap track + dots kept in sync. */
export function initCarousels() {
  document.querySelectorAll('[data-carousel]').forEach((track) => {
    const dots = track.parentElement.querySelector('[data-carousel-dots]');
    if (!dots) return;
    const buttons = [...dots.children];
    const go = (i) => track.scrollTo({ left: i * track.clientWidth, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    buttons.forEach((b, i) => b.addEventListener('click', () => go(i)));
    track.addEventListener('scroll', () => {
      const i = Math.round(track.scrollLeft / track.clientWidth);
      buttons.forEach((b, j) => b.setAttribute('aria-current', String(i === j)));
    }, { passive: true });
  });
}
