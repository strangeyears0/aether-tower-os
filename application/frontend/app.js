/* ==========================================================================
   AETHER TOWER OS — frontend (vanilla JS)
   ========================================================================== */
(() => {
  'use strict';

  // ------------------------------------------------------------------ config
  const CONFIG = { apiBase: '/api', ...(window.AETHER_CONFIG || {}) };
  // Tryb deweloperski bez NGINX:  index.html?api=http://localhost:8000/api
  const apiOverride = new URLSearchParams(location.search).get('api');
  if (apiOverride) CONFIG.apiBase = apiOverride.replace(/\/$/, '');

  const TOTAL_FLOORS = 100;
  const DEFAULT_FLOOR = 42;
  const DEFAULT_USER = 'U-0300';
  const POLL_FLOOR_MS = 20000;
  const POLL_HEALTH_MS = 15000;

  const ZONES = [
    { key: 'Alpha', sub: 'Focus & Deep Work' },
    { key: 'Beta', sub: 'Collaboration & Project' },
    { key: 'Gamma', sub: 'Agile Teams' },
    { key: 'Delta', sub: 'Hot Desks & Dual 4K' },
  ];

  const SPEC_ROWS = [
    ['monitors', 'Monitory', 'monitor'],
    ['chair', 'Fotel', 'chair'],
    ['desk', 'Biurko', 'desk'],
    ['computer', 'Stacja robocza', 'cpu'],
    ['network', 'Sieć', 'network'],
  ];

  const ICONS = {
    monitor: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    chair: '<svg viewBox="0 0 24 24"><path d="M8 3h8l1 8H7l1-8ZM6 11h12v3H6zM12 14v5M8 21l4-2 4 2"/></svg>',
    desk: '<svg viewBox="0 0 24 24"><path d="M3 8h18M5 8v12M19 8v12M9 8v5h6V8"/><path d="M12 3v3M10 4.5l2-1.5 2 1.5"/></svg>',
    cpu: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>',
    network: '<svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v5M12 12l-6 5M12 12l6 5"/></svg>',
    map: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="#D9461F" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/></svg>',
  };

  // ------------------------------------------------------------------- state
  const state = {
    meta: null,
    date: null,
    floors: [],
    floorId: null,
    selectedId: null,
    pendingId: null,
    busy: false,
    userId: null,
    users: [],
    myReservations: [],
    filter: '',
    floorCache: new Map(), // `${floor}|${date}` -> FloorMap
    floorReq: 0,
    loadingFloor: false,
    floorError: null,
    animateNext: false,
  };

  // ----------------------------------------------------------------- helpers
  const $ = (sel) => document.querySelector(sel);
  const pad = (n, len = 2) => String(n).padStart(len, '0');
  const cacheKey = (floor = state.floorId, date = state.date) => `${floor}|${date}`;

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value == null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'vars') for (const [name, v] of Object.entries(value)) node.style.setProperty(name, v);
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function icon(name, cls) {
    const span = el('span', { class: cls });
    span.innerHTML = ICONS[name]; // statyczne, zaufane stałe
    return span;
  }

  const coordinate = (floor, zone, desk) => `FL-${pad(floor)}.ZONE-${String(zone).toUpperCase()}.DESK-${pad(desk, 3)}`;

  function fmtDate(iso, opts = { weekday: 'short', day: '2-digit', month: '2-digit' }) {
    return new Date(`${iso}T00:00:00`).toLocaleDateString('pl-PL', opts);
  }

  const level = (pct) => (pct >= 80 ? 'high' : pct >= 50 ? 'mid' : 'low');

  const storage = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  };

  // --------------------------------------------------------------------- API
  async function api(path, { method = 'GET', body } = {}) {
    const res = await fetch(CONFIG.apiBase + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch { /* brak treści */ }
    if (!res.ok) {
      const detail = data && data.detail;
      const message = typeof detail === 'string'
        ? detail
        : detail && detail.message
          ? detail.message
          : Array.isArray(detail)
            ? detail.map((d) => d.msg).join('; ')
            : `Błąd serwera (HTTP ${res.status})`;
      const err = new Error(message);
      err.status = res.status;
      err.code = detail && detail.code;
      throw err;
    }
    return data;
  }

  // ------------------------------------------------------------------ toasts
  function toast(kind, title, message = '', ttl = 4800) {
    const node = el('div', { class: `toast toast--${kind}`, role: kind === 'error' ? 'alert' : 'status' },
      el('div', {}, el('div', { class: 'toast__title mono' }, title), message && el('div', { class: 'toast__msg' }, message)));
    $('#toasts').append(node);
    setTimeout(() => {
      node.classList.add('is-leaving');
      node.addEventListener('animationend', () => node.remove(), { once: true });
    }, ttl);
  }

  // ------------------------------------------------------------------- clock
  function tickClock() {
    const now = new Date();
    $('#clock-time').textContent = now.toLocaleTimeString('pl-PL', { hour12: false });
    $('#clock-date').textContent = now.toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' });
  }

  function setLink(up) {
    const link = $('#link');
    link.dataset.state = up ? 'up' : 'down';
    $('#link-label').textContent = up ? 'Połączono' : 'Brak połączenia';
  }

  async function checkHealth() {
    try { await api('/health'); setLink(true); } catch { setLink(false); }
  }

  // ----------------------------------------------------------- derived state
  const currentFloorData = () => state.floorCache.get(cacheKey()) || null;
  const findResource = (id) => (currentFloorData()?.resources || []).find((r) => r.id === id) || null;
  const myReservationOn = (date) => state.myReservations.find((r) => r.reservation_date === date) || null;
  const currentUser = () => state.users.find((u) => u.id === state.userId) || null;

  // ------------------------------------------------------ left panel: floors
  function renderTowerStat() {
    const total = state.floors.reduce((s, f) => s + f.total, 0);
    const reserved = state.floors.reduce((s, f) => s + f.reserved, 0);
    const pct = total ? (reserved / total) * 100 : 0;
    $('#tower-stat').textContent = `Wieża · ${reserved.toLocaleString('pl-PL')} / ${total.toLocaleString('pl-PL')} · ${pct.toFixed(1)}%`;
    $('#tower-bar-fill').style.width = `${Math.min(100, pct * 4)}%`; // skala x4 – czytelność przy niskiej zajętości
  }

  function renderFloorList() {
    const list = $('#floor-list');
    if (!state.floors.length) {
      list.replaceChildren(...Array.from({ length: 9 }, () => el('li', { class: 'floor--skeleton' })));
      return;
    }
    const q = state.filter.trim();
    const items = [...state.floors]
      .sort((a, b) => b.floor_id - a.floor_id)
      .filter((f) => !q || String(f.floor_id).includes(q));

    $('#floor-count').textContent = items.length;
    if (!items.length) {
      list.replaceChildren(el('li', { class: 'empty-note mono' }, 'Brak pięter dla podanego filtra'));
      return;
    }

    list.replaceChildren(...items.map((f) => {
      const pct = Math.round(f.occupancy_pct);
      return el('li', { role: 'presentation' },
        el('button', {
          type: 'button',
          class: 'floor',
          role: 'option',
          id: `floor-${f.floor_id}`,
          'aria-selected': String(f.floor_id === state.floorId),
          'data-level': level(f.occupancy_pct),
          vars: { '--pct': Math.max(pct, f.reserved ? 2 : 0) },
          title: `Piętro ${f.floor_id}: ${f.reserved}/${f.total} zajętych, ${f.maintenance} w konserwacji`,
          onclick: () => selectFloor(f.floor_id),
        },
        el('span', { class: 'floor__tag mono' }, `FL-${pad(f.floor_id)}`),
        el('span', { class: 'floor__label' },
          el('span', { class: 'floor__name' }, `Piętro ${f.floor_id}`),
          el('span', { class: 'floor__sep' }, '•'),
          el('span', { class: 'floor__occ mono' }, `${pct}% zajęte`)),
        el('span', { class: 'floor__bar' }, el('span'))));
    }));
  }

  function scrollFloorIntoView() {
    $(`#floor-${state.floorId}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function renderMine() {
    const list = $('#mine-list');
    $('#mine-count').textContent = state.myReservations.length;
    if (!state.myReservations.length) {
      list.replaceChildren(el('li', { class: 'mine__empty' }, 'Brak nadchodzących rezerwacji.'));
      return;
    }
    list.replaceChildren(...state.myReservations.map((r) => el('li', {},
      el('button', { type: 'button', class: 'mine__item mono', onclick: () => goToReservation(r) },
        el('b', {}, r.resource_id), el('span', {}, fmtDate(r.reservation_date))))));
  }

  async function goToReservation(r) {
    if (r.reservation_date !== state.date) await setDate(r.reservation_date);
    selectFloor(r.floor_id, { deskId: r.resource_id });
  }

  // ----------------------------------------------------- center panel: map
  function renderMapHeader() {
    const data = currentFloorData();
    const eyebrow = $('#map-eyebrow');
    const title = $('#map-title');
    const stats = $('#map-stats');
    if (!state.floorId) {
      eyebrow.textContent = 'Plan piętra';
      title.textContent = 'Wybierz piętro';
      stats.replaceChildren();
      return;
    }
    eyebrow.textContent = `FL-${pad(state.floorId)} · ${fmtDate(state.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}`;
    title.replaceChildren(`Piętro ${state.floorId}`, el('span', { class: 'mono' }, '150 stanowisk'));
    if (!data) { stats.replaceChildren(); return; }
    const s = data.summary;
    const stat = (cls, label, value) => el('div', { class: `stat ${cls}` },
      el('span', { class: 'stat__label mono' }, label), el('span', { class: 'stat__value mono' }, value));
    stats.replaceChildren(
      stat('stat--free', 'Wolne', s.available),
      stat('stat--occupied', 'Zajęte', s.reserved),
      stat('stat--maintenance', 'Konserwacja', s.maintenance),
      stat('stat--pct', 'Zajętość', `${Math.round(s.occupancy_pct)}%`));
  }

  function mapState(kind, title, text, action) {
    const art = kind === 'loading' ? el('div', { class: 'spinner', role: 'progressbar', 'aria-label': 'Ładowanie' })
      : icon(kind === 'error' ? 'alert' : 'map', 'map-state__art');
    return el('div', { class: 'map-state' }, art, el('h3', {}, title), text && el('p', {}, text), action);
  }

  function renderMap() {
    const body = $('#map-body');
    if (!state.floorId) {
      body.replaceChildren(mapState('idle', 'Wybierz piętro z listy', 'Dane 150 stanowisk zostaną pobrane dopiero po wyborze piętra (lazy loading).'));
      return;
    }
    const data = currentFloorData();
    if (!data) {
      if (state.floorError) {
        body.replaceChildren(mapState('error', 'Nie udało się pobrać mapy piętra', state.floorError,
          el('button', { type: 'button', class: 'btn-link mono', onclick: () => loadFloor() }, 'Ponów')));
      } else {
        body.replaceChildren(el('div', { class: 'skeleton-zones' }, ...ZONES.map(() => el('div', { class: 'skeleton-zone' }))));
      }
      return;
    }

    const me = state.userId;
    let index = 0;
    const zones = ZONES.map((z) => {
      const desks = data.resources.filter((r) => r.zone === z.key);
      const free = desks.filter((d) => d.status === 'free').length;
      return el('section', { class: 'zone', 'aria-label': `Strefa ${z.key}` },
        el('div', { class: 'zone__head' },
          el('div', { class: 'zone__name' }, el('b', {}, z.key), el('span', {}, z.sub)),
          el('div', { class: 'zone__free' }, el('b', {}, free), ` / ${desks.length} wolnych`)),
        el('div', { class: 'zone__grid' }, ...desks.map((d) => deskButton(d, me, index++))));
    });

    const wrapper = el('div', { class: `zones${state.animateNext ? ' is-entering' : ''}` }, ...zones);
    state.animateNext = false;
    const scrollTop = body.scrollTop;
    body.replaceChildren(wrapper);
    body.scrollTop = scrollTop;
  }

  function deskButton(d, me, i) {
    const pending = state.pendingId === d.id;
    const cls = ['desk', `desk--${d.status}`];
    if (pending) cls.push('desk--pending');
    if (state.selectedId === d.id) cls.push('desk--selected');
    if (d.status === 'occupied' && d.reserved_by_id === me) cls.push('desk--mine');
    const label = { free: 'wolne', occupied: 'zajęte', maintenance: 'konserwacja' }[d.status];
    return el('button', {
      type: 'button',
      class: cls.join(' '),
      id: d.svg_element_id,
      'data-desk': d.id,
      'aria-pressed': String(state.selectedId === d.id),
      'aria-label': `Biurko ${d.desk_number}, strefa ${d.zone}, ${label}`,
      title: `${d.coordinate} · ${label}`,
      vars: { '--i': i },
      onclick: () => selectDesk(d.id),
    }, pad(d.desk_number, 3));
  }

  // ---------------------------------------------------- right panel: drawer
  function setDrawerOpen(open) {
    $('#layout').classList.toggle('has-drawer', open);
    $('#drawer').setAttribute('aria-hidden', String(!open));
  }

  function kv(label, value, wide = false) {
    return el('div', { class: `kv__item${wide ? ' kv__item--wide' : ''}` },
      el('span', { class: 'kv__label' }, label), el('span', { class: 'kv__value' }, value));
  }

  function renderDrawer() {
    const body = $('#drawer-body');
    const d = state.selectedId ? findResource(state.selectedId) : null;
    if (!d) {
      setDrawerOpen(false);
      return;
    }
    setDrawerOpen(true);
    updateCrumb();

    const eq = d.equipment || {};
    const mine = d.status === 'occupied' && d.reserved_by_id === state.userId;
    const myOnDate = myReservationOn(state.date);
    const pending = state.pendingId === d.id;
    const badgeKind = pending ? 'pending' : d.status;
    const badgeText = pending ? 'Rezerwacja w toku'
      : { free: 'Wolne', occupied: mine ? 'Zajęte · Twoja rezerwacja' : 'Zajęte', maintenance: 'Konserwacja' }[d.status];

    const specs = SPEC_ROWS.filter(([key]) => eq[key]).map(([key, label, ic]) =>
      el('div', { class: 'spec' }, icon(ic, 'spec__icon'),
        el('div', {}, el('span', { class: 'spec__label' }, label), el('span', { class: 'spec__value' }, eq[key]))));

    const zoneMeta = ZONES.find((z) => z.key === d.zone);
    const typeLabel = d.type.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());

    // przycisk akcji
    let action;
    let hint = null;
    if (pending) {
      action = el('button', { type: 'button', class: 'btn btn--primary btn--busy', disabled: true }, 'Przetwarzanie…');
    } else if (d.status === 'free') {
      if (myOnDate) {
        action = el('button', { type: 'button', class: 'btn btn--primary', disabled: true }, 'Masz już rezerwację');
        hint = `Twoja rezerwacja na ${fmtDate(state.date)}: ${myOnDate.resource_id}. Anuluj ją, aby wybrać inne biurko.`;
      } else {
        action = el('button', { type: 'button', class: 'btn btn--primary', id: 'reserve-btn', onclick: () => reserve(d) }, 'Zarezerwuj to biurko');
        hint = `Rezerwacja na dzień ${fmtDate(state.date, { day: '2-digit', month: 'long', year: 'numeric' })} jako ${currentUser()?.full_name ?? state.userId}.`;
      }
    } else if (mine) {
      action = el('button', { type: 'button', class: 'btn btn--danger', id: 'cancel-btn', onclick: () => cancel(d) }, 'Anuluj moją rezerwację');
    } else if (d.status === 'occupied') {
      action = el('button', { type: 'button', class: 'btn btn--primary', disabled: true }, 'Stanowisko zajęte');
      hint = d.reserved_by ? `Zarezerwowane przez: ${d.reserved_by}` : null;
    } else {
      action = el('button', { type: 'button', class: 'btn btn--primary', disabled: true }, 'Konserwacja — niedostępne');
      hint = 'Stanowisko jest chwilowo wyłączone z użytku przez zespół Facility.';
    }

    body.replaceChildren(
      el('div', { class: 'coord' },
        el('span', { class: 'eyebrow' }, 'Koordynaty'),
        el('span', { class: 'coord__value' }, d.coordinate),
        el('span', { class: 'coord__id mono' }, `ID zasobu · ${d.id}`)),
      el('span', { class: `badge badge--${badgeKind}` }, el('i'), badgeText),
      el('div', { class: 'kv' },
        kv('Piętro', `FL-${pad(d.floor_id)}`),
        kv('Strefa', d.zone),
        kv('Profil', zoneMeta ? zoneMeta.sub : '—', true),
        kv('Typ', typeLabel),
        kv('Data', fmtDate(state.date, { day: '2-digit', month: '2-digit', year: 'numeric' }))),
      el('div', {},
        el('span', { class: 'eyebrow section-title' }, 'Specyfikacja sprzętowa'),
        el('div', { class: 'specs' }, ...specs)),
      Array.isArray(eq.extras) && eq.extras.length
        ? el('div', {}, el('span', { class: 'eyebrow section-title' }, 'Wyposażenie dodatkowe'),
          el('div', { class: 'tags' }, ...eq.extras.map((x) => el('span', { class: 'tag' }, x))))
        : null,
      el('div', { class: 'drawer__actions' }, action, hint && el('p', { class: 'hint' }, hint)));
  }

  function updateCrumb() {
    const d = state.selectedId ? findResource(state.selectedId) : null;
    $('#crumb').textContent = d
      ? d.coordinate
      : state.floorId ? `FL-${pad(state.floorId)}.ZONE-ALL` : 'FL-—';
  }

  // -------------------------------------------------------------- selection
  async function selectFloor(id, { deskId = null } = {}) {
    const changed = id !== state.floorId;
    state.floorId = id;
    if (changed) {
      state.selectedId = deskId;
      state.animateNext = true;
    } else if (deskId) {
      state.selectedId = deskId;
    }
    renderFloorList();
    renderMapHeader();
    updateCrumb();
    renderDrawer();
    scrollFloorIntoView();
    await loadFloor();
  }

  function selectDesk(id) {
    state.selectedId = state.selectedId === id ? null : id;
    renderMap();
    renderDrawer();
    updateCrumb();
  }

  function closeDrawer() {
    state.selectedId = null;
    renderMap();
    renderDrawer();
    updateCrumb();
  }

  // ----------------------------------------------------------------- loading
  async function loadFloors() {
    state.floors = await api(`/floors?date=${state.date}`);
    renderFloorList();
    renderTowerStat();
  }

  function syncFloorSummary(data) {
    const idx = state.floors.findIndex((f) => f.floor_id === data.floor_id);
    if (idx >= 0) state.floors[idx] = data.summary;
    renderTowerStat();
  }

  /** Lazy loading: dane piętra pobierane są dopiero po jego wyborze (+ stale-while-revalidate). */
  async function loadFloor({ silent = false } = {}) {
    const floorId = state.floorId;
    const key = cacheKey();
    const token = ++state.floorReq;
    const cached = state.floorCache.get(key);

    state.floorError = null;
    if (cached) {
      renderMap(); renderMapHeader(); renderDrawer();
    } else if (!silent) {
      state.loadingFloor = true;
      renderMapHeader();
      renderMap();
    }

    try {
      const data = await api(`/floors/${floorId}/resources?date=${state.date}`);
      if (token !== state.floorReq) return; // przestarzała odpowiedź
      state.floorCache.set(key, data);
      state.loadingFloor = false;
      syncFloorSummary(data);
      renderFloorList();
      renderMapHeader();
      renderMap();
      renderDrawer();
      updateCrumb();
    } catch (err) {
      if (token !== state.floorReq) return;
      state.loadingFloor = false;
      setLink(false);
      if (!cached) {
        state.floorError = err.message;
        renderMap();
      } else if (!silent) {
        toast('warn', 'Odświeżanie nieudane', err.message);
      }
    }
  }

  async function loadUsers() {
    state.users = await api('/users?limit=500');
    const saved = storage.get('aether.user');
    state.userId = state.users.some((u) => u.id === saved) ? saved
      : state.users.some((u) => u.id === DEFAULT_USER) ? DEFAULT_USER
        : state.users[state.users.length - 1]?.id ?? null;
    const select = $('#user-select');
    select.replaceChildren(...state.users.map((u) => el('option', { value: u.id }, `${u.full_name} (${u.id})`)));
    select.value = state.userId;
  }

  async function loadMyReservations() {
    if (!state.userId) { state.myReservations = []; renderMine(); return; }
    state.myReservations = await api(`/users/${encodeURIComponent(state.userId)}/reservations`);
    renderMine();
  }

  // ----------------------------------------------------------------- actions
  async function refreshAfterMutation() {
    state.floorCache.delete(cacheKey());
    await Promise.allSettled([loadMyReservations(), loadFloor({ silent: true })]);
    renderMap();
    renderDrawer();
  }

  async function reserve(desk) {
    if (state.busy) return;
    state.busy = true;
    state.pendingId = desk.id;
    renderMap();
    renderDrawer();
    try {
      await api('/reservations', {
        method: 'POST',
        body: { user_id: state.userId, resource_id: desk.id, reservation_date: state.date },
      });
      toast('success', 'Rezerwacja potwierdzona', `${desk.coordinate} · ${fmtDate(state.date)}`);
    } catch (err) {
      toast(err.status === 409 ? 'warn' : 'error', err.status === 409 ? 'Konflikt rezerwacji' : 'Błąd rezerwacji', err.message);
    } finally {
      state.pendingId = null;
      state.busy = false;
      await refreshAfterMutation();
    }
  }

  async function cancel(desk) {
    if (state.busy || !desk.reservation_id) return;
    state.busy = true;
    state.pendingId = desk.id;
    renderMap();
    renderDrawer();
    try {
      await api(`/reservations/${desk.reservation_id}?user_id=${encodeURIComponent(state.userId)}`, { method: 'DELETE' });
      toast('success', 'Rezerwacja anulowana', `${desk.coordinate} · ${fmtDate(state.date)}`);
    } catch (err) {
      toast('error', 'Nie udało się anulować', err.message);
    } finally {
      state.pendingId = null;
      state.busy = false;
      await refreshAfterMutation();
    }
  }

  async function setDate(date) {
    if (!date || date === state.date) return;
    state.date = date;
    $('#date-input').value = date;
    state.floorCache.clear();
    await loadFloors().catch((e) => toast('error', 'Błąd danych', e.message));
    if (state.floorId) await loadFloor();
  }

  // ------------------------------------------------------------------ events
  function bindEvents() {
    $('#date-input').addEventListener('change', (e) => setDate(e.target.value));

    $('#user-select').addEventListener('change', async (e) => {
      state.userId = e.target.value;
      storage.set('aether.user', state.userId);
      await loadMyReservations().catch((err) => toast('error', 'Błąd danych', err.message));
      renderMap();
      renderDrawer();
    });

    $('#floor-search').addEventListener('input', (e) => {
      state.filter = e.target.value;
      renderFloorList();
    });
    $('#floor-search').addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const n = parseInt(state.filter, 10);
      if (n >= 1 && n <= TOTAL_FLOORS) selectFloor(n);
    });

    $('#drawer-close').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.selectedId) closeDrawer();
    });
  }

  // -------------------------------------------------------------------- init
  async function init() {
    renderFloorList();
    renderMap();
    renderMine();
    try {
      state.meta = await api('/meta');
      state.date = state.meta.today;
      const dateInput = $('#date-input');
      dateInput.min = state.meta.today;
      dateInput.max = state.meta.max_date;
      dateInput.value = state.date;

      await Promise.all([loadUsers(), loadFloors()]);
      setLink(true);
      await loadMyReservations();
      await selectFloor(DEFAULT_FLOOR);
    } catch (err) {
      setLink(false);
      $('#map-body').replaceChildren(mapState('error', 'Brak połączenia z reservation-service', err.message,
        el('button', { type: 'button', class: 'btn-link mono', onclick: init }, 'Ponów')));
      $('#tower-stat').textContent = 'Wieża · brak danych';
    }
  }

  bindEvents();
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(checkHealth, POLL_HEALTH_MS);
  setInterval(() => {
    if (document.visibilityState === 'visible' && state.floorId && !state.busy) {
      loadFloor({ silent: true });
      api(`/floors?date=${state.date}`).then((f) => { state.floors = f; renderFloorList(); renderTowerStat(); }).catch(() => {});
    }
  }, POLL_FLOOR_MS);
  init();
})();
