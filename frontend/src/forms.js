/**
 * Form upgrades (progressive enhancement; forms still work without this file):
 *  - every single-choice <select> inside .field becomes a styled listbox (keyboard: arrows, Home/End, Enter, Escape, type-ahead)
 *  - every password input inside .field gets a Show / Hide toggle
 * The native <select> stays in the DOM and keeps the value, so Django reads the form exactly as before.
 */

let uid = 0;

function enhanceSelect(select) {
  if (select.dataset.enhanced || select.multiple) return;
  select.dataset.enhanced = '1';
  uid += 1;

  const wrap = document.createElement('div');
  wrap.className = 'sel';
  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);
  select.classList.add('sel__native');
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');

  const label = select.id ? document.querySelector(`label[for="${select.id}"]`) : null;
  if (label && !label.id) label.id = `sel-label-${uid}`;

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'sel__btn';
  btn.id = `sel-btn-${uid}`;
  btn.setAttribute('role', 'combobox');
  btn.setAttribute('aria-haspopup', 'listbox');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-labelledby', label ? `${label.id} ${btn.id}` : btn.id);
  btn.disabled = select.disabled;
  btn.innerHTML = '<span class="sel__value"></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
  const valueEl = btn.querySelector('.sel__value');

  const list = document.createElement('ul');
  list.className = 'sel__list';
  list.id = `sel-list-${uid}`;
  list.setAttribute('role', 'listbox');
  list.setAttribute('data-lenis-prevent', '');
  if (label) list.setAttribute('aria-labelledby', label.id);
  list.hidden = true;
  btn.setAttribute('aria-controls', list.id);

  const items = Array.from(select.options).map((opt, i) => {
    const li = document.createElement('li');
    li.className = 'sel__opt';
    li.id = `${list.id}-${i}`;
    li.setAttribute('role', 'option');
    li.setAttribute('aria-selected', 'false');
    if (opt.disabled) li.setAttribute('aria-disabled', 'true');
    li.innerHTML = '<span class="sel__tick" aria-hidden="true"></span>';
    const text = document.createElement('span');
    text.textContent = opt.textContent;
    li.appendChild(text);
    list.appendChild(li);
    return li;
  });

  wrap.append(btn, list);

  let active = Math.max(0, select.selectedIndex);
  let typed = '';
  let typedTimer = null;

  function sync() {
    const idx = select.selectedIndex;
    const opt = select.options[idx];
    valueEl.textContent = opt ? opt.textContent : '';
    valueEl.classList.toggle('sel__value--empty', !opt || opt.value === '');
    items.forEach((li, i) => li.setAttribute('aria-selected', String(i === idx)));
  }

  function mark(i) {
    active = Math.max(0, Math.min(items.length - 1, i));
    items.forEach((li, n) => { li.dataset.active = String(n === active); });
    btn.setAttribute('aria-activedescendant', items[active].id);
    items[active].scrollIntoView({ block: 'nearest' });
  }

  function isOpen() { return !list.hidden; }

  function open() {
    if (btn.disabled) return;
    document.dispatchEvent(new CustomEvent('sel:open', { detail: wrap }));
    list.hidden = false;
    wrap.dataset.open = 'true';
    btn.setAttribute('aria-expanded', 'true');
    // Open upward when there is not enough room below.
    const rect = btn.getBoundingClientRect();
    wrap.dataset.up = String(window.innerHeight - rect.bottom < 260 && rect.top > 260);
    mark(Math.max(0, select.selectedIndex));
  }

  function close() {
    list.hidden = true;
    wrap.dataset.open = 'false';
    btn.setAttribute('aria-expanded', 'false');
    btn.removeAttribute('aria-activedescendant');
  }

  function choose(i) {
    if (select.options[i].disabled) return;
    select.selectedIndex = i;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    sync();
    close();
    btn.focus();
  }

  btn.addEventListener('click', () => (isOpen() ? close() : open()));
  items.forEach((li, i) => {
    li.addEventListener('click', () => choose(i));
    li.addEventListener('mousemove', () => { if (active !== i) mark(i); });
  });

  btn.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen()) open(); else mark(active + (e.key === 'ArrowDown' ? 1 : -1));
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (typed && e.key === ' ') return; // a space inside type-ahead
      e.preventDefault();
      if (isOpen()) choose(active); else open();
    } else if (e.key === 'Escape' && isOpen()) {
      e.preventDefault();
      close();
    } else if (e.key === 'Home' && isOpen()) {
      e.preventDefault(); mark(0);
    } else if (e.key === 'End' && isOpen()) {
      e.preventDefault(); mark(items.length - 1);
    } else if (e.key === 'Tab' && isOpen()) {
      close();
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      typed += e.key.toLowerCase();
      clearTimeout(typedTimer);
      typedTimer = setTimeout(() => { typed = ''; }, 600);
      const hit = Array.from(select.options).findIndex((o) => o.textContent.trim().toLowerCase().startsWith(typed));
      if (hit > -1) { if (!isOpen()) open(); mark(hit); }
    }
  });

  document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) close(); });
  document.addEventListener('sel:open', (e) => { if (e.detail !== wrap) close(); });
  select.addEventListener('change', sync);
  sync();
}

function enhancePassword(input) {
  if (input.dataset.enhanced) return;
  input.dataset.enhanced = '1';
  const wrap = document.createElement('div');
  wrap.className = 'pw';
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'pw__toggle';
  toggle.textContent = 'Show';
  toggle.setAttribute('aria-label', 'Show password');
  toggle.setAttribute('aria-pressed', 'false');
  toggle.addEventListener('click', () => {
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    toggle.textContent = showing ? 'Show' : 'Hide';
    toggle.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    toggle.setAttribute('aria-pressed', String(!showing));
  });
  wrap.appendChild(toggle);
}

/** Booking button reads "Book token · <department>" once a department is picked. */
export function syncBookLabel() {
  const form = document.querySelector('[data-book-form]');
  const label = form && form.querySelector('[data-book-label]');
  if (!label) return;
  const on = form.querySelector('input[name="department"]:checked');
  label.textContent = on ? `Book token \u00b7 ${on.dataset.name}` : 'Book my token';
}

document.addEventListener('change', (e) => { if (e.target.closest && e.target.closest('[data-book-form]')) syncBookLabel(); });

export function initForms() {
  document.querySelectorAll('.field select').forEach(enhanceSelect);
  document.querySelectorAll('.field input[type="password"]').forEach(enhancePassword);
  syncBookLabel();
}
