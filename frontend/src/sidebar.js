/**
 * Floating sidebar. Opening on hover and keyboard focus is pure CSS (see app.css).
 * JS adds: tap-to-toggle for touch screens, and Escape to close however it was opened.
 */
export function initSidebar() {
  const sidebar = document.querySelector('[data-sidebar]');
  if (!sidebar) return;

  const toggle = sidebar.querySelector('[data-sidebar-toggle]');
  const setOpen = (open) => {
    sidebar.classList.toggle('is-open', open);
    if (toggle) toggle.setAttribute('aria-expanded', String(open));
  };

  if (toggle) {
    toggle.addEventListener('click', () => {
      sidebar.classList.remove('is-dismissed');
      setOpen(!sidebar.classList.contains('is-open'));
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    setOpen(false);
    sidebar.classList.add('is-dismissed');
  });

  // Re-arm hover/focus opening once the pointer or focus has left.
  const rearm = () => sidebar.classList.remove('is-dismissed');
  sidebar.addEventListener('pointerleave', rearm);
  sidebar.addEventListener('focusout', (e) => {
    if (!sidebar.contains(e.relatedTarget)) rearm();
  });

  // Tap outside closes the panel on touch devices.
  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'touch' && !sidebar.contains(e.target)) setOpen(false);
  });
}
