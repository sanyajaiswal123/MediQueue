/**
 * S4 Live token tracker. The token is a boarding pass (department -> room), a blister strip shows the
 * people ahead as capsules, and a journey rail shows where the visit is. Polls the patient's own token every 15s.
 * One live animation: when the number of people ahead drops, a capsule pops out of its well.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon, ago, csrfToken } from '../shared.jsx';

const POLL_MS = 15000;
const ACTIVE = ['WAITING', 'CALLED', 'IN_CONSULT'];
const MAX_CALLS = 3;
const MAX_WELLS = 11;

const STATUS_LABEL = {
  WAITING: 'Waiting', CALLED: 'Called', IN_CONSULT: 'With the doctor',
  COMPLETED: 'Completed', NO_SHOW: 'Missed', CANCELLED: 'Cancelled',
};

function time(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) : '—';
}

function day(iso) {
  return iso ? new Date(`${iso}T00:00`).toLocaleDateString([], { day: 'numeric', month: 'short' }) : '';
}

/** Capsule glyph that rides the dashed route line, like the plane on a boarding pass. */
function CapsuleGlyph() {
  return (
    <svg viewBox="0 0 30 14" aria-hidden="true">
      <rect x="1" y="1" width="28" height="12" rx="6" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M15 1v12" stroke="currentColor" strokeWidth="2" />
      <rect x="2.5" y="2.5" width="12" height="9" rx="4.5" fill="currentColor" opacity="0.35" />
    </svg>
  );
}

/** The status headline, food-tracker style: one clear sentence about what is happening now. */
function headline(t) {
  switch (t.status) {
    case 'WAITING':
      return t.people_ahead === 0
        ? { title: "You're next.", sub: t.room ? `Stay near Room ${t.room}.` : 'Stay nearby. We will tell you when to go in.' }
        : {
          title: `${t.people_ahead} ${t.people_ahead === 1 ? 'person' : 'people'} ahead of you.`,
          sub: t.estimated_wait_minutes > 0 ? `About ${t.estimated_wait_minutes} min. Stay nearby.` : 'Any minute now. Stay nearby.',
        };
    case 'CALLED':
      return {
        title: "It's your turn.",
        sub: t.call_count >= 2 ? `Called ${t.call_count} of ${MAX_CALLS} times. After the third, the token is marked missed.` : `Go to Room ${t.room || '—'}.`,
      };
    case 'IN_CONSULT':
      return { title: "You're with the doctor.", sub: t.room ? `Room ${t.room}.` : '' };
    case 'COMPLETED':
      return {
        title: 'Visit complete.',
        sub: t.prescription === 'PENDING' ? 'Your prescription is waiting at the pharmacy counter.'
          : t.prescription === 'DISPENSED' ? 'Your medicines were handed over at the pharmacy.'
            : 'No medicines were prescribed on this visit.',
      };
    case 'NO_SHOW':
      return { title: 'Token missed.', sub: `You were called ${MAX_CALLS} times and did not come in. Ask reception for a new token.` };
    default:
      return { title: 'Token cancelled.', sub: 'You can book another token whenever you are ready.' };
  }
}

function Pass({ t, isNew }) {
  const called = t.status === 'CALLED';
  const ended = ['COMPLETED', 'NO_SHOW', 'CANCELLED'].includes(t.status);
  const stamp = { COMPLETED: 'Completed', NO_SHOW: 'Missed', CANCELLED: 'Void' }[t.status];
  const stub = t.status === 'WAITING'
    ? [['Ahead', t.people_ahead], ['Wait', t.estimated_wait_minutes > 0 ? <>~{t.estimated_wait_minutes}<small> min</small></> : <small>soon</small>], ['Booked', time(t.created_at)]]
    : called || t.status === 'IN_CONSULT'
      ? [['Room', t.room || '—'], ['Calls', `${t.call_count}/${MAX_CALLS}`], ['Booked', time(t.created_at)]]
      : [['Status', <small>{STATUS_LABEL[t.status]}</small>], ['Booked', time(t.created_at)], ['Room', t.room || '—']];

  return (
    <div className={`pass-wrap ${isNew ? 'pass-wrap--print' : ''}`}>
      <section className={`ticket pass ${called ? 'pass--called' : ''} ${ended ? 'pass--done' : ''}`} aria-label={`Token ${t.label}`} role={called ? 'alert' : undefined}>
        <div className="pass__caps"><span>MediQueue · OPD token</span><span>{day(t.date)}</span></div>
        <div className="pass__route">
          <span className="pass__code">{t.department_code}</span>
          <span className="pass__line"><CapsuleGlyph /></span>
          <span className="pass__code">{t.room ? `R-${String(t.room).replace(/^R-?/i, '')}` : 'TBA'}</span>
        </div>
        <div className="pass__names"><span>{t.department_name}</span><span className="text-right">{t.hospital_name}</span></div>
        <p className="pass__label tabular">{t.label}</p>
        {called && <p className="pass__go">Go to Room {t.room || '—'}</p>}
        {stamp && <span className="stamp stamp--ink" aria-hidden="true">{stamp}</span>}
        {t.is_priority && !stamp && <span className="stamp stamp--brand">Priority</span>}
        <div className="ticket__perf" aria-hidden="true" />
        <dl className="pass__stub">
          {stub.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </section>
    </div>
  );
}

/** One capsule well per person ahead (up to 11), served wells empty, and a two-tone "you" capsule at the end. */
function Blister({ ahead, start }) {
  const wells = Math.min(Math.max(start, ahead), MAX_WELLS);
  const filled = Math.min(ahead, wells);
  const prev = useRef(ahead);
  const dropped = ahead < prev.current;
  useEffect(() => { prev.current = ahead; }, [ahead]);
  const empty = wells - filled;
  return (
    <div className="blister" aria-hidden="true">
      {Array.from({ length: wells }, (_, i) => {
        const out = i < empty;
        const pop = out && dropped && i === empty - 1;
        return <span key={i} className={`blister__well ${out ? 'blister__well--out' : ''} ${pop ? 'blister__well--pop' : ''}`}><i /></span>;
      })}
      {ahead > MAX_WELLS && <span className="blister__more">+{ahead - MAX_WELLS}</span>}
      <span className="blister__well blister__well--you"><i /></span>
      <span className="blister__you">you</span>
    </div>
  );
}

function Countdown({ minutes, since, now }) {
  const left = Math.max(0, minutes * 60 - Math.floor((now - since) / 1000));
  const m = Math.floor(left / 60);
  const s = left % 60;
  if (minutes === 0) return <span>any minute now</span>;
  return <span className="tabular">in about {m} min {String(s).padStart(2, '0')} s</span>;
}

function Rail({ t, since, now }) {
  const order = ['BOOKED', 'WAITING', 'CALLED', 'IN_CONSULT', 'COMPLETED'];
  const ended = t.status === 'NO_SHOW' || t.status === 'CANCELLED';
  const reached = ended ? (t.status === 'NO_SHOW' ? 2 : 1) : order.indexOf(t.status);
  const nodes = [
    { title: 'Booked', sub: time(t.created_at) },
    { title: 'In the queue', sub: t.status === 'WAITING' ? <>{t.people_ahead} ahead · <Countdown minutes={t.estimated_wait_minutes} since={since} now={now} /></> : '' },
    { title: 'Called', sub: t.room ? `Room ${t.room}` : '' },
    { title: 'With the doctor', sub: '' },
    { title: 'Done', sub: '' },
  ];
  return (
    <ol className="rail" aria-label="Your visit">
      {nodes.map((n, i) => {
        const state = i < reached ? 'done' : i === reached ? 'now' : 'next';
        return (
          <li key={n.title} className={state === 'done' ? 'is-done' : ''}>
            <span className={`rail__node ${state === 'done' ? 'rail__node--done' : state === 'now' ? 'rail__node--now' : ''}`} aria-hidden="true" />
            <div>
              <p className={state === 'now' ? 'font-semibold text-ink' : state === 'done' ? 'text-ink' : 'text-ink-soft'}>
                {n.title}{state === 'now' && <span className="sr-only"> (now)</span>}
              </p>
              {n.sub && <p className="text-sm text-ink-soft">{n.sub}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function TokenTracker({ api, cancelUrl, bookUrl }) {
  const [token, setToken] = useState(null);
  const [error, setError] = useState('');
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [start, setStart] = useState(0);
  const [isNew] = useState(() => new URLSearchParams(window.location.search).get('new') === '1');
  const lastStatus = useRef(null);
  const baseTitle = useRef(document.title);

  const load = useCallback(async () => {
    try {
      const res = await fetch(api, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (!res.ok) throw new Error(res.status === 404 ? 'This token was not found.' : 'Could not refresh.');
      const data = await res.json();
      setToken(data);
      setFetchedAt(Date.now());
      setError('');
    } catch (e) {
      setError(e.message || 'Could not refresh.');
    }
  }, [api]);

  useEffect(() => {
    load();
    const poll = setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(poll); clearInterval(tick); document.removeEventListener('visibilitychange', onVisible); };
  }, [load]);

  // The print animation plays once: drop ?new=1 so a refresh does not replay it.
  useEffect(() => {
    if (isNew) window.history.replaceState(null, '', window.location.pathname);
  }, [isNew]);

  // Remember the longest line seen, so served capsules show as empty wells.
  useEffect(() => {
    if (token && token.status === 'WAITING') setStart((s) => Math.max(s, token.people_ahead));
  }, [token]);

  // Being called: update the tab title and buzz once.
  useEffect(() => {
    if (!token) return;
    if (token.status === 'CALLED' && lastStatus.current && lastStatus.current !== 'CALLED') {
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    }
    document.title = token.status === 'CALLED' ? `Your turn: Room ${token.room || ''} · ${token.label}` : baseTitle.current;
    lastStatus.current = token.status;
  }, [token]);

  const cancel = async () => {
    setBusy(true);
    try {
      const res = await fetch(cancelUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not cancel.');
      setToken(data);
      setConfirming(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return <div className="pcard text-ink-soft" role="status">{error || 'Loading your token…'}</div>;
  }

  const active = ACTIVE.includes(token.status);
  const head = headline(token);

  return (
    <div>
      <div className="flex items-center justify-between text-sm text-ink-soft">
        <a href="/" className="-ml-2 inline-flex items-center gap-1 rounded-full px-2 py-1 hover:text-ink"><Icon name="back" />Home</a>
        <span className="inline-flex items-center gap-1.5">
          {active && <span className="size-1.5 rounded-full bg-live" aria-hidden="true" />}
          Updated {ago(fetchedAt, now)}
        </span>
      </div>

      <div className="mt-6" aria-live="polite">
        <h1 className="font-serif text-[clamp(2rem,6vw,2.6rem)] leading-[1.05] text-ink">{head.title}</h1>
        {head.sub && <p className="mt-2 max-w-[44ch] text-ink-soft">{head.sub}</p>}
      </div>

      <div className="mt-8 md:grid md:grid-cols-[minmax(0,440px)_1fr] md:items-start md:gap-14">
        <div>
          <Pass t={token} isNew={isNew} />
          {token.status === 'WAITING' && <Blister ahead={token.people_ahead} start={start} />}
          {token.status === 'WAITING' && (
            <p className="mt-3 px-1 text-xs leading-relaxed text-ink-soft">
              Estimate = people ahead × average consultation time. Priority patients are seen first, so it can change.
            </p>
          )}
        </div>

        <div className="mt-10 md:mt-2">
          <h2 className="mb-5 text-sm font-medium text-ink-soft">Your visit</h2>
          <Rail t={token} since={fetchedAt} now={now} />
        </div>
      </div>

      {error && <p className="mt-4 flex items-center gap-2 text-sm text-bad" role="alert"><Icon name="alert" />{error}</p>}

      {token.status === 'WAITING' && (
        <div className="mt-10">
          {!confirming ? (
            <button type="button" className="btn btn--danger-ghost" onClick={() => setConfirming(true)}>Cancel my token</button>
          ) : (
            <div className="pcard !p-5 max-w-[440px]">
              <p className="font-medium">Cancel {token.label}? You'll lose your place in the line.</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className="btn btn--dark" onClick={() => setConfirming(false)} autoFocus>Keep my place</button>
                <button type="button" className="btn btn--danger-ghost" onClick={cancel} disabled={busy}>{busy ? 'Cancelling…' : 'Cancel token'}</button>
              </div>
            </div>
          )}
        </div>
      )}

      {!active && (
        <a href={bookUrl} className="btn btn--dark mt-8">Book another token</a>
      )}
    </div>
  );
}
