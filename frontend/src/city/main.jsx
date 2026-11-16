import { createRoot } from 'react-dom/client';
import { getLenis } from '../smooth.js';
import CityDashboard from './CityDashboard.jsx';
import { reducedMotion } from '../shared.jsx';

const mount = document.getElementById('city');
if (mount) {
  createRoot(mount).render(<CityDashboard api={mount.dataset.api} detailBase={mount.dataset.detail} />);
}

if (!reducedMotion()) getLenis();
