/**
 * Landing page motion (DESIGN.md: Lenis + GSAP on the landing page and City Dashboard only).
 *
 * Motion thesis
 * - Focal moment: one ticket's life (pinned, scrubbed): enters, people-ahead rolls 6 -> 0,
 *   the stub turns blue ("Go to Room 12"), a red SEEN stamp slams down. A rail tracks progress.
 * - Supporting: hero letters rise out of a mask and the live ticket drops in and counts up;
 *   the ticket tilts toward the pointer; serif headings reveal line by line with a brick-red
 *   block wipe; the city numbers' rule draws then counts; the module circles slide together
 *   into their overlap ("one system"); a live departures strip loops (faster as you scroll).
 * - Reduced motion: opacity-only fades, no pin, no loop, numbers shown as-is.
 * Content stays visible by default; hidden states are only ever set from JS.
 */
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';
import { getLenis } from './smooth.js';

gsap.registerPlugin(ScrollTrigger, SplitText);

const EASE = 'expo.out';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function smoothScroll() {
  const lenis = getLenis(); // shared instance (null under reduced motion)
  if (lenis) lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.lagSmoothing(0);
}

/* ---------- Hero ---------- */

function heroIn() {
  const ticketWrap = $('[data-hero-ticket] .ticket-wrap');
  const count = $('[data-hero-ticket] .font-display');
  const tl = gsap.timeline({ defaults: { ease: EASE } });

  $$('[data-hero-title] [aria-hidden="true"]').forEach((line) => {
    if (!line.offsetParent) return; // the hidden (other breakpoint) variant
    const split = SplitText.create(line, { type: 'chars', mask: 'chars' });
    tl.from(split.chars, { yPercent: 115, duration: 1.1, stagger: 0.045 }, 0);
  });

  if (ticketWrap) {
    tl.from(ticketWrap, { y: -220, rotation: -18, autoAlpha: 0, duration: 1.2, ease: 'power4.out' }, 0.55);
  }
  if (count) {
    const target = parseInt(count.textContent, 10) || 0;
    const o = { v: 0 };
    tl.to(o, {
      v: target, duration: 1.4, ease: 'power3.out',
      onUpdate: () => { count.textContent = String(Math.round(o.v)); },
    }, 0.9);
  }
  tl.from('[data-hero-copy] > *, [data-hero-aside]', { y: 24, autoAlpha: 0, duration: 0.9, stagger: 0.08 }, 0.8);
  // From-states are applied; let the hero paint (see the `motion` class in home.html).
  document.documentElement.classList.add('motion-ready');
}

/** The hero ticket leans toward the pointer (desktop pointers only). */
function heroTilt() {
  const hero = $('.hero');
  const ticket = $('[data-hero-ticket] .ticket');
  if (!hero || !ticket || !matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  gsap.set(ticket, { transformPerspective: 900 });
  const rx = gsap.quickTo(ticket, 'rotationX', { duration: 0.6, ease: 'power3.out' });
  const ry = gsap.quickTo(ticket, 'rotationY', { duration: 0.6, ease: 'power3.out' });
  hero.addEventListener('pointermove', (e) => {
    const r = hero.getBoundingClientRect();
    ry(((e.clientX - r.left) / r.width - 0.5) * 16);
    rx(-((e.clientY - r.top) / r.height - 0.5) * 12);
  });
  hero.addEventListener('pointerleave', () => { rx(0); ry(0); });
}

/** Sticky nav slides away while scrolling down and returns on the way up. */
function navAutoHide() {
  const nav = $('.topnav');
  if (!nav) return;
  let hidden = false;
  ScrollTrigger.create({
    start: 'top -160',
    end: 'max',
    onUpdate: (self) => {
      const hide = self.direction === 1;
      if (hide !== hidden) {
        hidden = hide;
        gsap.to(nav, { yPercent: hide ? -170 : 0, duration: 0.45, ease: hide ? 'power2.in' : EASE });
      }
    },
    onLeaveBack: () => { hidden = false; gsap.to(nav, { yPercent: 0, duration: 0.45, ease: EASE }); },
  });
}

/* ---------- Live departures strip ---------- */

function ticker() {
  const track = $('[data-ticker]');
  if (!track) return;
  const loop = gsap.to(track, { xPercent: -50, duration: 60, ease: 'none', repeat: -1 });
  // Pause when offscreen; speed up briefly with scroll velocity.
  ScrollTrigger.create({
    trigger: track, start: 'top bottom', end: 'bottom top',
    onToggle: (self) => (self.isActive ? loop.play() : loop.pause()),
    onUpdate: (self) => {
      const boost = 1 + Math.min(Math.abs(self.getVelocity()) / 600, 5);
      gsap.to(loop, { timeScale: boost, duration: 0.2, overwrite: true });
      gsap.to(loop, { timeScale: 1, duration: 1.2, delay: 0.2, ease: 'power2.out' });
    },
  });
  track.addEventListener('pointerenter', () => gsap.to(loop, { timeScale: 0, duration: 0.5, overwrite: true }));
  track.addEventListener('pointerleave', () => gsap.to(loop, { timeScale: 1, duration: 0.5, overwrite: true }));
}

/* ---------- Editorial reveals ---------- */

/** Serif headings: each line is wiped by a brick-red block, the text lands behind it. */
function headingWipes() {
  $$('[data-split]').forEach((el) => {
    const light = el.dataset.split === 'light';
    SplitText.create(el, {
      type: 'lines',
      mask: 'lines',
      autoSplit: true,
      onSplit(self) {
        const blocks = self.masks.map((m) => {
          m.style.position = 'relative';
          const b = document.createElement('span');
          b.className = `wipe-block${light ? ' wipe-block--light' : ''}`;
          b.setAttribute('aria-hidden', 'true');
          m.appendChild(b);
          return b;
        });
        gsap.set(self.lines, { autoAlpha: 0 });
        const tl = gsap.timeline({ scrollTrigger: { trigger: el, start: 'top 82%', once: true } });
        self.lines.forEach((line, i) => {
          const at = i * 0.12;
          tl.fromTo(blocks[i], { scaleX: 0, transformOrigin: 'left' }, { scaleX: 1, duration: 0.45, ease: 'power3.inOut' }, at)
            .set(line, { autoAlpha: 1 }, at + 0.45)
            .set(blocks[i], { transformOrigin: 'right' }, at + 0.45)
            .to(blocks[i], { scaleX: 0, duration: 0.5, ease: 'power3.inOut' }, at + 0.45);
        });
        return tl;
      },
    });
  });

  $$('[data-wipe]').forEach((tag) => {
    gsap.fromTo(tag, { clipPath: 'inset(0 100% 0 0)' }, {
      clipPath: 'inset(0 0% 0 0)', duration: 0.7, ease: 'power3.inOut',
      scrollTrigger: { trigger: tag, start: 'top 88%', once: true },
    });
  });
}

/** City numbers: the rule draws across, then each number counts up from zero. */
function cityNumbers() {
  const rule = $('[data-rule]');
  const nums = $$('[data-count]');
  if (!rule) return;
  const tl = gsap.timeline({ scrollTrigger: { trigger: rule, start: 'top 85%', once: true } });
  tl.from(rule, { scaleX: 0, duration: 1.0, ease: 'power3.inOut' });
  nums.forEach((el, i) => {
    const text = el.firstChild;
    const target = Number(el.dataset.count) || 0;
    if (!text || text.nodeType !== Node.TEXT_NODE) return;
    const o = { v: 0 };
    tl.from(el.parentElement, { y: 30, autoAlpha: 0, duration: 0.8, ease: EASE }, 0.5 + i * 0.12)
      .to(o, {
        v: target, duration: 1.4, ease: 'power3.out',
        onStart: () => { text.nodeValue = '0'; },
        onUpdate: () => { text.nodeValue = String(Math.round(o.v)); },
      }, 0.5 + i * 0.12);
  });
}

/* ---------- Focal moment: one ticket through its life ---------- */

function journey() {
  const section = $('[data-journey]');
  if (!section) return;
  const steps = $$('[data-step]', section);
  const now = $('[data-step-now]', section);
  const ticketWrap = $('[data-journey-ticket]', section);
  const ticket = $('.journey-ticket', section);
  const ahead = $('[data-ahead]', section);
  const aheadLabel = $('[data-ahead-label]', section);
  const turn = $('.journey-ticket__turn', section);
  const stubText = $('[data-stub-text]', section);
  const fill = $('[data-stub-fill]', section);
  const done = $('[data-stub-done]', section);
  const stamp = $('[data-stamp]', section);
  const rail = $('[data-rail-fill]', section);

  /** One coherent ticket per step: waiting (1-2), called (3), seen (4). */
  const setState = (n) => {
    const state = n >= 4 ? 'seen' : n >= 3 ? 'called' : 'waiting';
    ticket.dataset.state = state;
    turn.textContent = state === 'seen' ? 'Visit complete' : "It's your turn";
  };

  let current = 0;
  const setStep = (n) => {
    if (n === current) return;
    current = n;
    if (now) {
      now.textContent = String(n);
      gsap.fromTo(now, { yPercent: 60, autoAlpha: 0 }, { yPercent: 0, autoAlpha: 1, duration: 0.35, ease: EASE, overwrite: true });
    }
    steps.forEach((li, i) => li.classList.toggle('is-current', i + 1 === n));
    setState(n);
  };
  setStep(1);

  let shown = 6;
  const showAhead = (n) => {
    if (n === shown) return;
    const down = n < shown;
    shown = n;
    ahead.textContent = String(n);
    gsap.fromTo(ahead, { yPercent: down ? 70 : -70, autoAlpha: 0 }, { yPercent: 0, autoAlpha: 1, duration: 0.3, ease: EASE, overwrite: true });
    aheadLabel.textContent = n === 0 ? "you're next" : n === 1 ? 'person ahead' : 'people ahead';
    stubText.textContent = n === 0 ? 'Any minute now' : `About ${n * 8} min`;
  };

  const mm = gsap.matchMedia();
  mm.add('(min-width: 1024px)', () => {
    gsap.from(ticketWrap, {
      xPercent: 40, rotation: 16, autoAlpha: 0, duration: 1.1, ease: EASE,
      scrollTrigger: { trigger: section, start: 'top 70%', once: true },
    });

    const counter = { n: 6 };
    const tl = gsap.timeline({
      defaults: { ease: 'none' },
      scrollTrigger: {
        trigger: section, start: 'top top', end: '+=1700', pin: true, scrub: 0.6,
        onUpdate: (self) => setStep(Math.min(4, Math.floor(self.progress * 3.999) + 1)),
      },
    });
    // Four equal segments so progress maps straight to the step counter.
    tl.to(rail, { scaleY: 1, duration: 4 }, 0)
      .to(ticketWrap, { y: -10, duration: 1 }, 0)
      // 2: the line moves (6 -> 0)
      .to(counter, { n: 0, duration: 0.9, onUpdate: () => showAhead(Math.round(counter.n)) }, 1)
      // 3: called: stub wipes blue ("Go to Room 12"), ticket lifts toward you
      .to(fill, { clipPath: 'inset(0 0% 0 0)', duration: 0.45, ease: 'power2.inOut' }, 2.05)
      .to(ticket, { scale: 1.04, duration: 0.35, ease: 'power2.out' }, 2.05)
      .to(ticket, { scale: 1, duration: 0.35, ease: 'power2.in' }, 2.4)
      // 4: seen: stub turns back to paper ("sent to the pharmacy"), the stamp lands clear of the token
      .to(done, { clipPath: 'inset(0 0% 0 0)', duration: 0.4, ease: 'power2.inOut' }, 3.05)
      .fromTo(stamp, { autoAlpha: 0, scale: 2.4, rotation: 8 },
        { autoAlpha: 1, scale: 1, rotation: -10, duration: 0.3, ease: 'power4.in' }, 3.2)
      .to(ticketWrap, { keyframes: { rotation: [0, -2.5, 1.5, -0.6, 0], y: [-10, -4, -10] }, duration: 0.35 }, 3.5)
      .to({}, { duration: 0.15 }, 3.85);
    return () => { showAhead(6); shown = 6; };
  });
  // Phones / tablets: no pin. Show one coherent static state: called.
  mm.add('(max-width: 1023px)', () => {
    steps.forEach((li) => li.classList.add('is-current'));
    ticket.dataset.state = 'called';
    gsap.set(fill, { clipPath: 'inset(0 0% 0 0)' });
    gsap.from(ticketWrap, {
      y: 60, rotation: 10, autoAlpha: 0, duration: 1, ease: EASE,
      scrollTrigger: { trigger: ticketWrap, start: 'top 85%', once: true },
    });
  });
}

/* ---------- Modules: four circles slide into one system ---------- */

function circles() {
  const list = $('[data-circles]');
  if (!list) return;
  const items = [...list.children];
  const activate = (el) => items.forEach((c) => c.classList.toggle('is-active', c === el));
  items.forEach((c) => {
    c.addEventListener('mouseenter', () => activate(c));
    c.addEventListener('focusin', () => activate(c));
    c.addEventListener('click', () => activate(c));
  });

  gsap.matchMedia().add('(min-width: 901px)', () => {
    gsap.fromTo(items, {
      x: (i) => (i - 1.5) * 120, scale: 0.9,
    }, {
      x: 0, scale: 1, ease: 'power2.out', stagger: 0.04,
      scrollTrigger: { trigger: list, start: 'top 90%', end: 'top 45%', scrub: 0.8 },
    });
  });
}

/* ---------- Close and footer ---------- */

function footerWordmark() {
  const mark = $('[data-wordmark]');
  if (!mark) return;
  const split = SplitText.create(mark, { type: 'chars', mask: 'chars' });
  gsap.from(split.chars, {
    yPercent: 110, duration: 0.9, ease: EASE, stagger: 0.04,
    scrollTrigger: { trigger: mark, start: 'top 95%', once: true },
  });
}

/* ---------- Reduced motion: fades only ---------- */

function gentle() {
  $$('[data-split], [data-wipe], [data-rule], [data-journey-ticket], [data-circles] > li, [data-wordmark]').forEach((el) => {
    gsap.from(el, { autoAlpha: 0, duration: 0.6, ease: 'power1.out', scrollTrigger: { trigger: el, start: 'top 90%', once: true } });
  });
  $$('[data-step]').forEach((li) => li.classList.add('is-current'));
  const fill = $('[data-stub-fill]');
  if (fill) gsap.set(fill, { clipPath: 'inset(0 0% 0 0)' });
  const jt = $('.journey-ticket');
  if (jt) jt.dataset.state = 'called';
  $$('[data-circles] > li').forEach((c, _, all) => c.addEventListener('mouseenter', () => all.forEach((x) => x.classList.toggle('is-active', x === c))));
}

function init() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    gentle();
    return;
  }
  smoothScroll();
  heroIn();
  heroTilt();
  navAutoHide();
  ticker();
  headingWipes();
  cityNumbers();
  journey();
  circles();
  footerWordmark();
}

// Wait for the self-hosted fonts so SplitText measures the real line breaks.
document.fonts.ready.then(init);
