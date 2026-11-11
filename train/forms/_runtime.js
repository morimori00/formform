// formform training-form runtime. Inlined into every generated page by build.py.
// Widgets are declared in HTML with data-ff-* attributes; this file wires behaviour and exposes
//   window.__formState()  -> {family, variant, state, step, steps, submitted, values, errors, visible}
// Values are always read from live DOM (or the snapshot taken at successful submit).
(() => {
  const CFG = JSON.parse(document.getElementById('ff-config').textContent);
  const Q = new URLSearchParams(location.search);
  const STATE = Q.get('state') || 'default';            // default | prefilled | partial | wrong | loading | error
  const roots = [document];
  const all = sel => roots.flatMap(r => [...r.querySelectorAll(sel)]);
  const one = sel => all(sel)[0] || null;
  const fire = (el, ...types) => types.forEach(t => el.dispatchEvent(new Event(t, {bubbles: true, composed: true})));
  const pad = n => String(n).padStart(2, '0');
  let submitted = null, step = 0;

  // ---------- date helpers ----------
  const fmtDate = (iso, f) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ''); if (!m) return iso || '';
    const [, y, mo, d] = m;
    return {'YYYY-MM-DD': `${y}-${mo}-${d}`, 'MM/DD/YYYY': `${mo}/${d}/${y}`, 'DD/MM/YYYY': `${d}/${mo}/${y}`,
      'YYYY-DD-MM': `${y}-${d}-${mo}`, 'YYYY/MM/DD': `${y}/${mo}/${d}`, 'DD.MM.YYYY': `${d}.${mo}.${y}`}[f] || iso;
  };
  const parseDate = (s, f) => {
    s = (s || '').trim(); if (!s) return '';
    const p = s.split(/[-/.]/); if (p.length !== 3) return s;
    const order = f.split(/[-/.]/), o = {};
    order.forEach((k, i) => o[k[0]] = p[i]);
    const y = +o.Y, mo = +o.M, d = +o.D;
    if (!y || !mo || !d || mo > 12 || d > 31) return s;
    return `${y}-${pad(mo)}-${pad(d)}`;
  };

  // ---------- getters / setters per widget kind ----------
  const field = key => one(`[data-ff-key="${key}"]`);
  const kinds = {
    input: {get: e => e.value, set: (e, v) => { e.value = v ?? ''; fire(e, 'input', 'change'); }},
    select: {get: e => e.value, set: (e, v) => { e.value = v ?? ''; fire(e, 'change'); }},
    radio: {get: e => (e.querySelector('input:checked') || {}).value || '',
      set: (e, v) => e.querySelectorAll('input').forEach(i => { i.checked = i.value === v; if (i.checked) fire(i, 'change'); })},
    checkbox: {get: e => e.checked, set: (e, v) => { e.checked = v === true || v === 'true'; fire(e, 'change'); }},
    checks: {get: e => [...e.querySelectorAll('input:checked')].map(i => i.value).sort(),
      set: (e, v) => { e.querySelectorAll('input').forEach(i => i.checked = (v || []).includes(i.value)); fire(e, 'change'); }},
    switch: {get: e => e.getAttribute('aria-checked') === 'true', set: (e, v) => { e.setAttribute('aria-checked', String(!!v)); fire(e, 'change'); }},
    ariaradio: {get: e => (e.querySelector('[role=radio][aria-checked=true]') || {dataset: {}}).dataset.value || '',
      set: (e, v) => { e.querySelectorAll('[role=radio]').forEach(r => r.setAttribute('aria-checked', String(r.dataset.value === v))); fire(e, 'change'); }},
    dropdown: {get: e => e.dataset.value || '', set: (e, v) => pickDropdown(e, v)},
    combobox: {get: e => e.dataset.value || '', set: (e, v) => {
      const o = JSON.parse(e.dataset.ffOptions).find(o => o[0] === v);
      e.value = o ? o[1] : (v || ''); e.dataset.value = o ? o[0] : ''; fire(e, 'change'); }},
    datepicker: {get: e => parseDate(e.value, e.dataset.ffFormat), set: (e, v) => { e.value = fmtDate(v, e.dataset.ffFormat); fire(e, 'input', 'change'); }},
    rocdate: {get: e => {
      const [y, m, d] = [...e.querySelectorAll('select')].map(s => s.value);
      return y && m && d ? `${+y + 1911}-${pad(m)}-${pad(d)}` : '';
    }, set: (e, v) => {
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || ''); const s = [...e.querySelectorAll('select')];
      if (!m) { s.forEach(x => x.value = ''); } else { s[0].value = String(+m[1] - 1911); s[1].value = String(+m[2]); s[2].value = String(+m[3]); }
      s.forEach(x => fire(x, 'change'));
    }},
    editable: {get: e => e.innerText.trim(), set: (e, v) => { e.innerText = v ?? ''; fire(e, 'input'); }},
  };
  const kindOf = e => kinds[e.dataset.ffKind] || kinds.input;
  const getVal = key => { const e = field(key); return e ? kindOf(e).get(e) : null; };
  const setVal = (key, v) => { const e = field(key); if (e) kindOf(e).set(e, v); };
  const isEmpty = v => v === '' || v === null || v === false || (Array.isArray(v) && !v.length);

  // ---------- visibility (hidden steps / tabs still count as present; show-if hides) ----------
  const conditionalHidden = e => { for (let n = e; n; n = n.parentElement || (n.getRootNode() || {}).host) if (n.dataset && n.dataset.ffShowIf && n.hidden) return true; return false; };

  // ---------- validation ----------
  const UBN_W = [1, 2, 1, 2, 1, 2, 4, 1];
  const ubnOk = s => {
    if (!/^\d{8}$/.test(s)) return false;
    const sums = UBN_W.map((w, i) => { const p = w * +s[i]; return Math.floor(p / 10) + p % 10; });
    const t = sums.reduce((a, b) => a + b, 0);
    return t % 5 === 0 || (s[6] === '7' && (t + 1) % 5 === 0);
  };
  const MSG = CFG.messages;
  const check = e => {
    const key = e.dataset.ffKey, v = kindOf(e).get(e), rule = e.dataset.ffValidate || '';
    if (conditionalHidden(e)) return '';
    if (e.dataset.ffRequired === '1' && isEmpty(v)) return MSG.required;
    if (isEmpty(v) || !rule) return '';
    const s = String(v);
    if (rule === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s)) return MSG.email;
    if (rule === 'ubn' && !ubnOk(s)) return MSG.ubn;
    if (rule === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(s)) return MSG.date;
    if (rule.startsWith('re:') && !new RegExp(rule.slice(3)).test(s)) return e.dataset.ffMsg || MSG.format;
    if (rule.startsWith('match:') && s !== String(getVal(rule.slice(6)))) return MSG.match;
    return '';
  };
  const showError = (e, msg) => {
    const box = e.closest('[data-ff-row]') || e.parentElement;
    let err = box.querySelector(':scope > .ff-error');
    if (!err) { err = document.createElement('div'); err.className = 'ff-error'; err.setAttribute('role', 'alert'); box.appendChild(err); }
    err.textContent = msg; err.hidden = !msg;
    e.setAttribute('aria-invalid', msg ? 'true' : 'false');
  };
  const validate = scope => {
    let bad = 0;
    for (const e of all('[data-ff-key]')) {
      if (scope && !scope.contains(e) && !scope.contains(e.getRootNode().host)) continue;
      const m = check(e); showError(e, m); if (m) bad++;
    }
    return bad;
  };
  const errors = () => all('[data-ff-key][aria-invalid=true]').map(e => ({key: e.dataset.ffKey,
    message: ((e.closest('[data-ff-row]') || e.parentElement).querySelector('.ff-error') || {}).textContent || ''}));

  // ---------- widgets ----------
  function pickDropdown(host, v) {
    const o = host.parentElement.querySelector(`[role=option][data-value="${CSS.escape(v || '')}"]`);
    host.dataset.value = o ? v : '';
    host.querySelector('.ff-dd-label').textContent = o ? o.textContent : host.dataset.ffPlaceholder;
    host.parentElement.querySelectorAll('[role=option]').forEach(x => x.setAttribute('aria-selected', String(x === o)));
    fire(host, 'change');
  }
  const initDropdown = host => {
    const list = host.parentElement.querySelector('[role=listbox]');
    const close = () => { list.hidden = true; host.setAttribute('aria-expanded', 'false'); };
    host.addEventListener('click', ev => { ev.preventDefault(); list.hidden = !list.hidden; host.setAttribute('aria-expanded', String(!list.hidden)); });
    list.addEventListener('click', ev => { const o = ev.target.closest('[role=option]'); if (o) { pickDropdown(host, o.dataset.value); close(); showError(host, check(host)); } });
    document.addEventListener('click', ev => { if (!host.parentElement.contains(ev.composedPath()[0])) close(); }, true);
  };
  const initCombobox = inp => {
    const opts = JSON.parse(inp.dataset.ffOptions), list = inp.parentElement.querySelector('[role=listbox]');
    const delay = +(inp.dataset.ffDelay || 0);
    let timer;
    const render = () => {
      const q = inp.value.trim().toLowerCase();
      list.innerHTML = '';
      if (q.length < (+inp.dataset.ffMinChars || 1)) { list.hidden = true; inp.setAttribute('aria-expanded', 'false'); return; }
      const hits = opts.filter(o => o[1].toLowerCase().includes(q) || (o[2] || '').toLowerCase().includes(q)).slice(0, 8);
      for (const [v, label, sub] of hits) {
        const li = document.createElement('li'); li.setAttribute('role', 'option'); li.dataset.value = v; li.id = inp.id + '-o-' + v.replace(/\W/g, '_');
        li.innerHTML = `<span></span>${sub ? '<small></small>' : ''}`; li.firstChild.textContent = label; if (sub) li.lastChild.textContent = sub;
        list.appendChild(li);
      }
      if (!hits.length) list.innerHTML = `<li class="ff-empty">${CFG.messages.noMatch}</li>`;
      list.hidden = false; inp.setAttribute('aria-expanded', 'true');
    };
    inp.addEventListener('input', () => {
      inp.dataset.value = '';                               // typing invalidates the committed choice
      clearTimeout(timer);
      if (delay) { list.hidden = false; list.innerHTML = `<li class="ff-empty">${CFG.messages.searching}</li>`; timer = setTimeout(render, delay); } else render();
    });
    list.addEventListener('mousedown', ev => ev.preventDefault());
    list.addEventListener('click', ev => {
      const li = ev.target.closest('[role=option]'); if (!li) return;
      const o = opts.find(o => o[0] === li.dataset.value);
      inp.value = o[1]; inp.dataset.value = o[0]; list.hidden = true; inp.setAttribute('aria-expanded', 'false');
      fire(inp, 'change'); showError(inp, check(inp));
    });
    inp.addEventListener('blur', () => setTimeout(() => { list.hidden = true; inp.setAttribute('aria-expanded', 'false'); }, 150));
  };
  const initDatepicker = inp => {
    const btn = inp.parentElement.querySelector('.ff-cal-btn'), pop = inp.parentElement.querySelector('.ff-cal');
    const ysel = pop.querySelector('.ff-cal-y'), msel = pop.querySelector('.ff-cal-m'), grid = pop.querySelector('.ff-cal-grid');
    const draw = () => {
      const y = +ysel.value, m = +msel.value, first = new Date(y, m - 1, 1).getDay(), n = new Date(y, m, 0).getDate();
      grid.innerHTML = '';
      for (let i = 0; i < first; i++) grid.appendChild(document.createElement('span'));
      for (let d = 1; d <= n; d++) {
        const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'gridcell'); b.textContent = d;
        b.setAttribute('aria-label', `${y}-${pad(m)}-${pad(d)}`);
        b.onclick = () => { inp.value = fmtDate(`${y}-${pad(m)}-${pad(d)}`, inp.dataset.ffFormat); pop.hidden = true; fire(inp, 'input', 'change'); showError(inp, check(inp)); };
        grid.appendChild(b);
      }
    };
    btn.addEventListener('click', () => {
      const cur = parseDate(inp.value, inp.dataset.ffFormat), m = /^(\d{4})-(\d{2})/.exec(cur);
      const now = new Date(CFG.today); ysel.value = m ? +m[1] : now.getFullYear(); msel.value = m ? +m[2] : now.getMonth() + 1;
      draw(); pop.hidden = !pop.hidden;
    });
    ysel.onchange = msel.onchange = draw;
    pop.querySelector('.ff-cal-prev').onclick = () => { if (+msel.value === 1) { msel.value = 12; ysel.value = +ysel.value - 1; } else msel.value = +msel.value - 1; draw(); };
    pop.querySelector('.ff-cal-next').onclick = () => { if (+msel.value === 12) { msel.value = 1; ysel.value = +ysel.value + 1; } else msel.value = +msel.value + 1; draw(); };
    if (inp.dataset.ffTyping === '0') inp.readOnly = true;
  };
  const initCascade = child => {
    const parent = field(child.dataset.ffParent), map = JSON.parse(child.dataset.ffMap), ph = child.dataset.ffPlaceholder;
    const fill = () => {
      const keep = child.value;
      child.innerHTML = `<option value="">${ph}</option>` + (map[parent.value] || []).map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
      child.disabled = !parent.value; child.value = (map[parent.value] || []).some(o => o[0] === keep) ? keep : '';
    };
    parent.addEventListener('change', fill); fill();
  };
  const initTabs = list => {
    const tabs = [...list.querySelectorAll('[role=tab]')];
    tabs.forEach(t => t.addEventListener('click', () => tabs.forEach(x => {
      const on = x === t; x.setAttribute('aria-selected', String(on)); x.classList.toggle('active', on);
      document.getElementById(x.getAttribute('aria-controls')).hidden = !on;
    })));
  };
  const refreshShowIf = () => {
    for (const e of all('[data-ff-show-if]')) {
      const [k, v] = e.dataset.ffShowIf.split('=');
      e.hidden = String(getVal(k)) !== v;
    }
  };

  // ---------- steps & submit ----------
  const steps = () => all('.ff-step');
  const showStep = i => {
    step = i; steps().forEach((s, j) => s.hidden = j !== i);
    const ind = one('.ff-progress'); if (ind) ind.querySelectorAll('li').forEach((li, j) => li.classList.toggle('current', j === i));
    window.scrollTo(0, 0);
  };
  const snapshot = () => Object.fromEntries(CFG.keys.map(k => [k, getVal(k)]));
  const submit = () => {
    if (validate()) { banner(MSG.fix, true); return; }
    if (STATE === 'error' && !window.__ffRejected) {          // server-side rejection on first submit
      window.__ffRejected = true; const e = field(CFG.rejectKey);
      if (e) { showError(e, CFG.rejectMessage); banner(MSG.fix, true); return; }
    }
    submitted = snapshot(); window.__submitted = submitted;
    one('#ff-root').innerHTML = `<div class="ff-done" role="status"><h2>${MSG.doneTitle}</h2><p>${MSG.doneBody}</p><p class="ff-ref">${CFG.refPrefix}-${String(Date.now()).slice(-6)}</p></div>`;
  };
  const banner = (msg, bad) => {
    let b = one('.ff-banner'); if (!b) return;
    b.textContent = msg; b.hidden = !msg; b.classList.toggle('bad', !!bad);
  };

  // ---------- boot ----------
  const boot = () => {
    const root = document.getElementById('ff-root');
    root.replaceChildren(document.getElementById('ff-form').content.cloneNode(true));
    for (const host of root.querySelectorAll('[data-ff-shadow]')) {
      const sr = host.attachShadow({mode: host.dataset.ffShadow});
      sr.appendChild(document.getElementById('ff-style').cloneNode(true));
      sr.appendChild(host.querySelector('template').content.cloneNode(true));
      host.querySelector('template').remove(); roots.push(sr);
    }
    all('[data-ff-kind=dropdown]').forEach(initDropdown);
    all('[data-ff-kind=combobox]').forEach(initCombobox);
    all('[data-ff-kind=datepicker]').forEach(initDatepicker);
    all('[data-ff-parent]').forEach(initCascade);
    all('[role=tablist]').forEach(initTabs);
    all('[data-ff-kind=switch]').forEach(s => s.addEventListener('click', () => { s.setAttribute('aria-checked', String(s.getAttribute('aria-checked') !== 'true')); fire(s, 'change'); }));
    all('[data-ff-kind=ariaradio] [role=radio]').forEach(r => r.addEventListener('click', () => kinds.ariaradio.set(r.closest('[data-ff-kind]'), r.dataset.value)));
    for (const e of all('[data-ff-key]')) {
      e.addEventListener('change', refreshShowIf);
      e.addEventListener(e.dataset.ffKind === 'combobox' ? 'change' : 'blur', () => showError(e, check(e)), true);
      if (e.dataset.ffKind === 'radio' || e.dataset.ffKind === 'checks') e.addEventListener('change', () => showError(e, check(e)));
    }
    all('[data-ff-next]').forEach(b => b.addEventListener('click', ev => {
      ev.preventDefault(); const cur = steps()[step];
      if (validate(cur)) { banner(MSG.fix, true); return; } banner(''); showStep(step + 1);
    }));
    all('[data-ff-back]').forEach(b => b.addEventListener('click', ev => { ev.preventDefault(); banner(''); showStep(step - 1); }));
    all('[data-ff-submit]').forEach(b => b.addEventListener('click', ev => { ev.preventDefault(); submit(); }));
    all('form').forEach(f => f.addEventListener('submit', ev => ev.preventDefault()));
    if (steps().length) showStep(0);
    // hard states (a recorder can also call window.__ffPrefill(right, wrong) itself with a persona's values)
    const P = CFG.prefill, R = Object.entries(P.right);
    if (STATE === 'prefilled') window.__ffPrefill(P.right);
    if (STATE === 'partial') window.__ffPrefill(Object.fromEntries(R.slice(0, Math.ceil(R.length / 2))));
    if (STATE === 'wrong') window.__ffPrefill(P.right, P.wrong);
    refreshShowIf();
    window.__ffReady = true;
  };
  // Put values into fields as if entered earlier: `right` twice (so dependent selects get their options), then `wrong`
  // values with their validation message shown. Keys/values use the same canonical form as __formState().values.
  window.__ffPrefill = (right, wrong) => {
    for (let i = 0; i < 2; i++) Object.entries(right || {}).forEach(([k, v]) => setVal(k, v));
    Object.entries(wrong || {}).forEach(([k, v]) => { setVal(k, v); const e = field(k); if (e) showError(e, check(e)); });
    refreshShowIf();
  };
  window.__formState = () => ({
    family: CFG.family, variant: CFG.variant, state: STATE, ready: !!window.__ffReady,
    step, steps: steps().length || 1, submitted: !!submitted,
    values: submitted || (window.__ffReady ? snapshot() : {}),
    errors: submitted ? [] : errors(),
    visible: window.__ffReady && !submitted ? CFG.keys.filter(k => { const e = field(k); return e && !conditionalHidden(e); }) : [],
  });
  const wait = STATE === 'loading' ? +(Q.get('delay') || 1500) : CFG.delay;
  const go = () => wait ? setTimeout(boot, wait) : boot();
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', go) : go();
})();
