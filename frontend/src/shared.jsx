/** Small helpers shared by the React widgets (TokenTracker, CityDashboard). */

const PATHS = {
  clock: <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>,
  megaphone: <><path d="m3 11 18-5v12L3 14v-3z" /><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" /></>,
  consult: <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M12 11h4" /><path d="M12 16h4" /></>,
  check: <><circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" /></>,
  minus: <><circle cx="12" cy="12" r="10" /><path d="M8 12h8" /></>,
  x: <><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6" /><path d="m9 9 6 6" /></>,
  alert: <><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" /><path d="M12 9v4" /><path d="M12 17h.01" /></>,
  back: <><path d="m12 19-7-7 7-7" /><path d="M19 12H5" /></>,
  chevron: <path d="m6 9 6 6 6-6" />,
  bed: <><path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8" /><path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4" /><path d="M2 18h20" /></>,
  door: <><path d="M13 4h3a2 2 0 0 1 2 2v14" /><path d="M2 20h3" /><path d="M13 20h9" /><path d="M13 4.56v16.157a.5.5 0 0 1-.596.49l-6-1.2A.5.5 0 0 1 6 19.517V5.283a1 1 0 0 1 .804-.98l5-1a1 1 0 0 1 1.196.98Z" /></>,
  refresh: <><path d="M21 12a9 9 0 1 1-3-6.7L21 8" /><path d="M21 3v5h-5" /></>,
};

export function Icon({ name, className = 'size-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}

export function Badge({ tone, icon, children }) {
  return (
    <span className={`badge${tone ? ` badge--${tone}` : ''}`}>
      <Icon name={icon} className="" />
      {children}
    </span>
  );
}

export function csrfToken() {
  const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** "8s ago" / "2 min ago" for a timestamp in ms. */
export function ago(ts, now) {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)} min ago`;
}
