/**
 * S12 City Dashboard: public, aggregate numbers only. A departures board on paper: ruled rows,
 * fixed columns, tabular numerals, a clock. Motion: counters on first load; when a refresh changes
 * the order, rows FLIP to their new place and changed numbers get a short live-blue wash.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { Flip } from 'gsap/Flip';
import { Badge, Icon, reducedMotion } from '../shared.jsx';

gsap.registerPlugin(Flip);

const POLL_MS = 30000;
const SORTS = [
  { key: 'wait', label: 'Shortest wait' },
  { key: 'beds', label: 'Most free beds' },
  { key: 'name', label: 'A–Z' },
];

function bedState(b) {
  if (!b.total) return { tone: '', icon: 'minus', label: 'No beds listed' };
  if (b.available === 0) return { tone: 'bad', icon: 'x', label: 'Full' };
  if (b.available / b.total < 0.2) return { tone: 'warn', icon: 'alert', label: 'Few beds' };
  return { tone: 'ok', icon: 'check', label: 'Beds free' };
}

function sortRows(rows, key) {
  const copy = [...rows];
  if (key === 'name') return copy.sort((a, b) => a.name.localeCompare(b.name));
  if (key === 'beds') return copy.sort((a, b) => b.beds.available - a.beds.available || a.name.localeCompare(b.name));
  const w = (h) => (h.opd.open_departments ? h.opd.shortest_wait_minutes ?? 9999 : 99999);
  return copy.sort((a, b) => w(a) - w(b) || a.name.localeCompare(b.name));
}

/** Key numbers per hospital, used to detect which cells changed between refreshes. */
const signature = (h) => ({
  wait: h.opd.shortest_wait_minutes, waiting: h.opd.waiting_tokens, free: h.beds.available,
  bedq: h.beds.waiting, low: h.pharmacy.low_stock_items,
});

function Counter({ value, first }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!first || reducedMotion() || value === 0) { el.textContent = String(value); return; }
    const o = { v: 0 };
    const tw = gsap.to(o, { v: value, duration: 1.2, ease: 'power3.out', onUpdate: () => { el.textContent = String(Math.round(o.v)); } });
    return () => tw.kill();
  }, [value, first]);
  return <span ref={ref} className="nums-display">{value}</span>;
}

function Num({ changed, children, className = '' }) {
  return <span className={`${className} ${changed ? 'wash' : ''}`}>{children}</span>;
}

function BedBar({ b }) {
  if (!b.total) return null;
  const pct = (n) => `${(n / b.total) * 100}%`;
  return (
    <div className="mt-2 flex h-2 w-full max-w-[200px] gap-0.5" aria-hidden="true">
      {b.available > 0 && <span style={{ width: pct(b.available) }} className="rounded bg-ok" />}
      {b.occupied > 0 && <span style={{ width: pct(b.occupied) }} className="rounded bg-ink/70" />}
      {b.cleaning > 0 && <span style={{ width: pct(b.cleaning) }} className="rounded bg-[repeating-linear-gradient(135deg,#b07d1a_0_2px,#fbeccb_2px_4px)]" />}
    </div>
  );
}

function Detail({ id, base }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let live = true;
    Promise.all([
      fetch(`${base}${id}/departments/`).then((r) => r.json()),
      fetch(`${base}${id}/beds/`).then((r) => r.json()),
    ]).then(([departments, beds]) => live && setData({ departments, beds }))
      .catch(() => live && setErr('Could not load details.'));
    return () => { live = false; };
  }, [id, base]);
  if (err) return <p className="py-4 text-sm text-bad">{err}</p>;
  if (!data) return <p className="py-4 text-sm text-ink-soft">Loading departments and wards…</p>;
  return (
    <div className="grid gap-8 pb-8 pt-2 lg:grid-cols-[3fr_2fr]">
      <div className="overflow-x-auto">
        <table className="table">
          <caption className="mb-2 text-left font-medium">OPD departments</caption>
          <thead><tr><th>Department</th><th>Status</th><th className="num">Waiting</th><th className="num">Est. wait</th><th className="num">Tokens left</th></tr></thead>
          <tbody>
            {data.departments.map((d) => (
              <tr key={d.id}>
                <td><span className="font-medium">{d.name}</span> <span className="text-ink-soft">{d.code}</span></td>
                <td>{d.is_open ? 'Open' : <span className="text-ink-soft">Closed</span>}</td>
                <td className="num">{d.waiting}</td>
                <td className="num">{d.is_open ? `${d.estimated_wait_minutes} min` : '–'}</td>
                <td className="num">{d.tokens_left || <span className="font-semibold text-warn">Full</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto">
        <table className="table">
          <caption className="mb-2 text-left font-medium">Wards</caption>
          <thead><tr><th>Ward</th><th className="num">Free</th><th className="num">Waiting</th></tr></thead>
          <tbody>
            {data.beds.wards.map((w) => (
              <tr key={w.id}>
                <td><span className="font-medium">{w.name}</span></td>
                <td className="num"><span className="font-semibold">{w.available}</span> <span className="text-ink-soft">/ {w.total}</span></td>
                <td className="num">{w.waiting || <span className="text-ink-soft">0</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function CityDashboard({ api, detailBase }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [sort, setSort] = useState('wait');
  const [open, setOpen] = useState(() => new Set());
  const [asOf, setAsOf] = useState(null);
  const [changed, setChanged] = useState({});
  const [first, setFirst] = useState(true);
  const listRef = useRef(null);
  const flipState = useRef(null);
  const prevSig = useRef({});
  const loadedOnce = useRef(false);

  const captureFlip = () => {
    if (listRef.current && !reducedMotion()) {
      flipState.current = Flip.getState(listRef.current.querySelectorAll('[data-flip]'));
    }
  };

  const load = useCallback(async () => {
    try {
      const res = await fetch(api, { headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const diff = {};
      data.forEach((h) => {
        const before = prevSig.current[h.id];
        const now = signature(h);
        if (before) Object.keys(now).forEach((k) => { if (before[k] !== now[k]) diff[`${h.id}:${k}`] = true; });
        prevSig.current[h.id] = now;
      });
      captureFlip();
      if (loadedOnce.current) setFirst(false);
      loadedOnce.current = true;
      setRows(data);
      setChanged(diff);
      setAsOf(new Date());
      setError('');
    } catch {
      setError('Could not refresh. Showing the last numbers.');
    }
  }, [api]);

  useEffect(() => {
    load();
    const id = setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  useLayoutEffect(() => {
    if (flipState.current) {
      Flip.from(flipState.current, { duration: 0.6, ease: 'expo.out', absolute: false });
      flipState.current = null;
    }
  });

  const changeSort = (key) => { captureFlip(); setSort(key); };
  const toggle = (id) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  if (!rows) {
    return (
      <>
        <h1 className="font-serif text-[clamp(2.6rem,5vw,4.4rem)] leading-[1.02]">Where to go right now</h1>
        <p className="mt-3 text-ink-soft" role="status">{error || 'Loading live numbers…'}</p>
      </>
    );
  }

  const totals = rows.reduce((t, h) => ({
    free: t.free + h.beds.available, beds: t.beds + h.beds.total, waiting: t.waiting + h.opd.waiting_tokens,
  }), { free: 0, beds: 0, waiting: 0 });
  const sorted = sortRows(rows, sort);
  const clock = asOf ? asOf.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-serif text-[clamp(2.6rem,5vw,4.4rem)] leading-[1.02]">Where to go right now</h1>
          <p className="mt-3 text-ink-soft">As of <span className="tabular font-medium text-ink">{clock}</span> · refreshes every 30 seconds{error && <span className="text-bad"> · {error}</span>}</p>
        </div>
        <button type="button" className="btn btn--ghost" onClick={load}><Icon name="refresh" />Refresh now</button>
      </div>

      <p className="mt-10 flex flex-wrap gap-x-10 gap-y-3 border-y border-line py-5 text-ink-soft" aria-live="polite">
        <span><span className="text-[44px] font-extralight leading-none text-ink"><Counter value={totals.free} first={first} /></span> of {totals.beds} beds free</span>
        <span><span className="text-[44px] font-extralight leading-none text-ink"><Counter value={totals.waiting} first={first} /></span> people in OPD queues</span>
        <span><span className="text-[44px] font-extralight leading-none text-ink"><Counter value={rows.length} first={first} /></span> hospitals reporting</span>
      </p>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-4">
        <div className="tabs" data-slider="line" role="group" aria-label="Sort hospitals">
          {SORTS.map((s) => (
            <button key={s.key} type="button" className="tab cursor-pointer" aria-pressed={sort === s.key}
              aria-current={sort === s.key ? 'page' : undefined} onClick={() => changeSort(s.key)}>{s.label}</button>
          ))}
        </div>
        <p className="flex flex-wrap items-center gap-4 text-xs text-ink-soft">
          <span className="inline-flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-ok" />free</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-ink/70" />occupied</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-[repeating-linear-gradient(135deg,#b07d1a_0_2px,transparent_2px_4px)]" />cleaning</span>
        </p>
      </div>

      <div className="board mt-6">
        <div className="board__head" aria-hidden="true">
          <span>Hospital</span><span>OPD wait</span><span>Beds</span><span>Pharmacy</span><span>Status</span><span />
        </div>
        <ul ref={listRef}>
          {sorted.map((h) => {
            const bs = bedState(h.beds);
            const closed = !h.opd.open_departments;
            const isOpen = open.has(h.id);
            const c = (k) => changed[`${h.id}:${k}`];
            return (
              <li key={h.id} data-flip data-flip-id={`h${h.id}`} className="board__item">
                <button type="button" className="board__row" aria-expanded={isOpen} aria-controls={`d${h.id}`} onClick={() => toggle(h.id)}>
                  <span>
                    <span className="block font-serif text-[26px] leading-tight text-ink">{h.name}</span>
                    <span className="text-sm text-ink-soft">{h.area}</span>
                  </span>
                  <span>
                    {closed ? <span className="text-ink-soft">OPD closed</span> : (
                      <>
                        <Num changed={c('wait')} className="text-[28px] font-light leading-none nums-display text-ink">{h.opd.shortest_wait_minutes}<span className="text-base text-ink-soft"> min</span></Num>
                        <span className="mt-1 block text-sm text-ink-soft">{h.opd.open_departments} depts open · <Num changed={c('waiting')}>{h.opd.waiting_tokens}</Num> waiting</span>
                      </>
                    )}
                  </span>
                  <span>
                    <Num changed={c('free')} className="text-[28px] font-light leading-none nums-display text-ink">{h.beds.available}</Num>
                    <span className="text-sm text-ink-soft"> free of {h.beds.total}</span>
                    <BedBar b={h.beds} />
                    {h.beds.waiting > 0 && <span className="mt-1 block text-sm text-ink-soft"><Num changed={c('bedq')}>{h.beds.waiting}</Num> waiting for a bed</span>}
                  </span>
                  <span className="text-sm">
                    {h.pharmacy.low_stock_items
                      ? <Num changed={c('low')} className="text-warn">{h.pharmacy.low_stock_items} item{h.pharmacy.low_stock_items > 1 ? 's' : ''} low</Num>
                      : <span className="text-ink-soft">Stocked</span>}
                  </span>
                  <span><Badge tone={bs.tone} icon={bs.icon}>{bs.label}</Badge></span>
                  <span className={`board__chev ${isOpen ? 'rotate-180' : ''}`}><Icon name="chevron" className="size-5" /><span className="sr-only">{isOpen ? 'Hide' : 'Show'} details for {h.name}</span></span>
                </button>
                <div id={`d${h.id}`} hidden={!isOpen}>{isOpen && <Detail id={h.id} base={detailBase} />}</div>
              </li>
            );
          })}
        </ul>
      </div>
      {rows.length === 0 && <p className="mt-8 text-ink-soft">No hospitals are reporting yet.</p>}
      <p className="mt-10 text-xs text-ink-soft">Totals only. No patient is named or identifiable on this page. Data: <a className="link" href={api}>public API</a>.</p>
    </>
  );
}
