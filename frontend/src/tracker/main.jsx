import { createRoot } from 'react-dom/client';
import TokenTracker from './TokenTracker.jsx';

const mount = document.getElementById('tracker');
if (mount) {
  const { api, cancel, book } = mount.dataset;
  createRoot(mount).render(<TokenTracker api={api} cancelUrl={cancel} bookUrl={book} />);
}
