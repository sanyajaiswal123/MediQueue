import './app.css';
import { initSidebar } from './sidebar.js';
import { initCarousels } from './carousel.js';
import { initTheme } from './theme.js';
import { initForms } from './forms.js';
import { getLenis } from './smooth.js';
import { initNav } from './nav.js';

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initSidebar();
  initCarousels();
  initForms();
  getLenis();
  initNav();
});
