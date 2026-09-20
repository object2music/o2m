/* ══ The Boxes column's views — a list, three mosaics, and a dice ═════════════
   ══════════════════════════════════════════════════════════════════════════════

   The column lists the durable objects: a box is a row in the database and a
   physical thing you put down. An album is neither, but everything that happens
   after an activation — the fill, the mood and discover-level ladder, the
   anti-repeat cooldown, the ownership that lets a second tap remove exactly the
   tracks the first one added — is driven by a Box OBJECT, not by its row. So the
   server builds one that is never saved (o2m_core/virtualbox.py) and the whole
   box path runs unchanged; this file is only the way in.

   Four views share the column, switched at the left of its toolbar: the boxes
   list as it was, the same boxes as a mosaic, and the two library mosaics. A
   mosaic rather than more rows because these are chosen by their cover — 248
   album names in a third of a screen is a directory, 248 covers is a shelf.

   At the right of that toolbar, one die — the glyph alone, in the tabs' own box
   and without a frame of its own:
   **activate one at random, in whatever view is open**. It is the same gesture as
   reaching into the shelf without looking, and it is the only control here that
   does not need you to have decided anything.

   Loaded in <head>, like ds/o2m-marks.js and for the same reason: mood.html's
   init() runs synchronously at the end of its inline script and calls in here.
   Nothing in this file runs at load; the page's globals (API, objEsc, ICON,
   setFeedback…) are read at call time, by which point they exist. */

const OBJGRID = (() => {
  /* 'boxes' is the pre-existing list, rendered by mood.html's loadBoxes(); the
     other three are mosaics owned by this file. */
  const MODES = ['boxes', 'boxgrid', 'albums', 'artists'];
  const MOSAICS = ['boxgrid', 'albums', 'artists'];
  const STORE_KEY = 'o2m-panel-mode';
  /* One request for a whole listing rather than a page at a time: the filter
     field below has to search what is NOT on screen to be worth anything, and
     248 rows of json is ~40 KB. Covers are the weight, and they are lazy. */
  const PAGE = 500;

  const KIND_OF = { boxgrid: 'box', albums: 'album', artists: 'artist' };
  const ICONS = {
    /* Two box glyphs, as asked: the solid box opens the list, the same box drawn
       as a grid of four opens the mosaic. */
    boxes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
    boxgrid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    dice: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/></svg>',
  };

  const state = {
    mode: 'boxes',
    rows: { boxgrid: null, albums: null, artists: null },   // null = not fetched
    more: { boxgrid: false, albums: false, artists: false },
    filter: '',
    active: new Map(),      // object uri → {kind, name}
    activeBoxes: new Set(), // box uid
    busy: new Set(),
  };

  /* ── DOM ───────────────────────────────────────────────────────────────── */

  function mount() {
    const bar = document.getElementById('auto-bar');
    const body = document.querySelector('#boxes-panel .panel-body');
    if (!bar || !body || document.getElementById('panel-mode')) return false;

    const seg = document.createElement('div');
    seg.id = 'panel-mode';
    seg.className = 'pm-seg';
    seg.setAttribute('role', 'tablist');
    seg.innerHTML = [
      ['boxes',   ICONS.boxes,   'Boxes'],
      ['boxgrid', ICONS.boxgrid, 'Boxes as a mosaic'],
      ['albums',  ICON.disc,     'Albums'],
      ['artists', ICON.user,     'Artists'],
    ].map(([m, icon, label]) =>
      `<button type="button" class="pm-tab" role="tab" data-panel-mode="${m}"`
      + ` title="${label}" aria-label="${label}">${icon}</button>`).join('');
    bar.appendChild(seg);

    const rnd = document.createElement('button');
    rnd.id = 'panel-random';
    rnd.type = 'button';
    rnd.className = 'pm-random';
    rnd.title = 'Activate one at random';
    rnd.setAttribute('aria-label', 'Activate one at random');
    rnd.innerHTML = ICONS.dice;
    rnd.addEventListener('click', pickRandom);
    bar.appendChild(rnd);

    const grid = document.createElement('div');
    grid.id = 'obj-grid-wrap';
    grid.hidden = true;
    grid.innerHTML =
      '<div class="og-tools">'
      + '<input class="og-filter" type="search" placeholder="Filter…" autocomplete="off" spellcheck="false">'
      + '</div><div class="og-grid" id="obj-grid"></div>';
    body.appendChild(grid);

    seg.addEventListener('click', (e) => {
      const b = e.target.closest('[data-panel-mode]');
      if (b) setMode(b.dataset.panelMode);
    });
    grid.querySelector('.og-filter').addEventListener('input', (e) => {
      state.filter = e.target.value.trim().toLowerCase();
      render();
    });
    document.getElementById('obj-grid').addEventListener('click', onGridClick);
    return true;
  }

  /* ── Sticky geometry ───────────────────────────────────────────────────── */

  /* The toolbar and the filter stay at the top while the mosaic scrolls, and on
     desktop they must start below the column's own header — which is sticky in
     the SAME scroller. Its height is measured rather than assumed: it changes
     with the theme's type, and a wrong guess shows either a strip of scrolled
     content or an overlap that eats the header. objgrid.css does the rest. */
  function measureSticky() {
    const panel = document.getElementById('boxes-panel');
    if (!panel) return;
    const set = (name, el) => {
      if (el) panel.style.setProperty(name, Math.round(el.getBoundingClientRect().height) + 'px');
    };
    set('--og-label-h', document.getElementById('boxes-panel-label'));
    set('--og-bar-h', document.getElementById('auto-bar'));
  }

  function watchSticky() {
    measureSticky();
    window.addEventListener('resize', measureSticky);
    if (typeof ResizeObserver === 'undefined') return;
    // The toolbar wraps to two rows in a narrow column, and the header grows with
    // the count it shows — both change the offsets under them.
    const ro = new ResizeObserver(measureSticky);
    ['boxes-panel-label', 'auto-bar'].forEach(id => {
      const el = document.getElementById(id);
      if (el) ro.observe(el);
    });
  }

  /* ── Mode ──────────────────────────────────────────────────────────────── */

  function setMode(mode) {
    if (!MODES.includes(mode)) mode = 'boxes';
    state.mode = mode;
    try { localStorage.setItem(STORE_KEY, mode); } catch (e) {}

    document.querySelectorAll('#panel-mode .pm-tab').forEach(b => {
      const on = b.dataset.panelMode === mode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const boxes = document.getElementById('boxes-wrap');
    const grid = document.getElementById('obj-grid-wrap');
    const mosaic = MOSAICS.includes(mode);
    if (boxes) boxes.hidden = mosaic;
    if (grid) grid.hidden = !mosaic;
    // What is active may have moved since this view was last looked at — an NFC
    // tap, the Basic view, the server itself. One request for the whole column,
    // asked at the moment someone turns to it.
    refreshActive();
    if (!mosaic) return;

    if (state.rows[mode] === null) load(mode);
    else render();
  }

  async function load(mode) {
    const grid = document.getElementById('obj-grid');
    if (grid) grid.innerHTML = '<div class="og-empty">Loading…</div>';
    try {
      if (mode === 'boxgrid') {
        // The pinned boxes, in the shape the tiles read. None of them carries an
        // image today, so every box tile falls to its generated cover — which is
        // deterministic on the uid, so a box keeps the same face.
        const d = await fetch(API + '/box_favorites').then(r => r.json());
        // No `sub`: a box's option_type is an internal lifecycle word, and with
        // the name now set inside the square it would be the tile's only caption
        // — "library" under twenty-six of twenty-eight tiles, reading as their
        // subtitle. The list still carries it, as the swatch colour.
        state.rows[mode] = (d || []).map(b => ({
          uri: 'box:' + b.uid, uid: b.uid,
          name: b.description || b.uid, sub: '',
          image: b.image_url || '',
        }));
        state.more[mode] = false;
      } else {
        const d = await fetch(`${API}/library_browse?kind=${mode}&limit=${PAGE}`).then(r => r.json());
        state.rows[mode] = (d && d.items) || [];
        state.more[mode] = !!(d && d.has_more);
      }
    } catch (e) {
      state.rows[mode] = [];
      state.more[mode] = false;
    }
    // No refreshActive() here: tileHTML reads the active state, which init()
    // fills once and every toggle keeps up to date. Re-asking on each mode
    // switch would be a second request for an answer already on hand.
    if (state.mode === mode) render();
  }

  /* ── Render ────────────────────────────────────────────────────────────── */

  function isActive(row, kind) {
    return kind === 'box' ? state.activeBoxes.has(row.uid) : state.active.has(row.uri);
  }

  function tileHTML(row, kind) {
    const active = isActive(row, kind);
    const name = row.name || '?';
    /* Where the name goes. An album is recognised by its SLEEVE, so its name is a
       caption under the tile. A box is only its name — never a picture one knows
       — so the name belongs IN the square: set large when there is no artwork
       (which is every box today), laid over the artwork when there is. Either
       way the caption below is dropped rather than printed twice, and the full
       name lives on the tile's `title` for the ones the square has to clip. */
    const named = !row.image || kind === 'box';
    const art = row.image
      ? `<img class="og-art" src="${objEsc(row.image)}" alt="" loading="lazy" decoding="async">`
        + (kind === 'box' ? `<span class="og-cap">${objEsc(name)}</span>` : '')
      : `<span class="og-art og-art--text">${objEsc(name)}</span>`;
    return `<button type="button" class="og-tile${active ? ' active' : ''}`
      + `${named ? ' og-tile--named' : ''}"`
      + ` data-uri="${objEsc(row.uri)}" data-kind="${objEsc(kind)}"`
      + (row.uid ? ` data-uid="${objEsc(row.uid)}"` : '')
      + ` data-name="${objEsc(name)}" data-sub="${objEsc(row.sub || '')}"`
      + ` title="${objEsc(name)}" aria-pressed="${active}">`
      + `<span class="og-thumb">${art}<span class="og-mark">${ICON.check}</span>`
      + `<span class="og-open" role="button" tabindex="0" data-og-open`
      + ` title="Details" aria-label="Details">${ICON.eye}</span></span>`
      + `<span class="og-name">${objEsc(name)}</span>`
      + (row.sub ? `<span class="og-sub">${objEsc(row.sub)}</span>` : '')
      + `</button>`;
  }

  function visibleRows() {
    const all = state.rows[state.mode] || [];
    const q = state.filter;
    return q ? all.filter(r => ((r.name || '') + ' ' + (r.sub || '')).toLowerCase().includes(q))
             : all;
  }

  function render() {
    const grid = document.getElementById('obj-grid');
    if (!grid || !MOSAICS.includes(state.mode)) return;
    const kind = KIND_OF[state.mode];
    const rows = visibleRows();

    if (!rows.length) {
      const empty = (state.rows[state.mode] || []).length
        ? 'Nothing matches that filter.'
        : state.mode === 'boxgrid' ? 'No pinned boxes.'
        : state.mode === 'albums'  ? 'No saved albums cached yet.'
                                   : 'No followed artists cached yet.';
      grid.innerHTML = `<div class="og-empty">${objEsc(empty)}</div>`;
      return;
    }
    let html = rows.map(r => tileHTML(r, kind)).join('');
    // Said, not hidden: the mosaic claims to show the library, so a truncation
    // that goes unmentioned would be a lie about what is not there.
    if (state.more[state.mode] && !state.filter)
      html += `<div class="og-empty og-more">Showing the first ${rows.length}.</div>`;
    grid.innerHTML = html;
  }

  /* ── Activation ────────────────────────────────────────────────────────── */

  function onGridClick(e) {
    const tile = e.target.closest('.og-tile');
    if (!tile) return;
    // The eye opens the object's detail view; the rest of the tile toggles it —
    // the same division as the boxes list's ⓘ glyph.
    if (e.target.closest('[data-og-open]')) {
      e.stopPropagation();
      const { uri, kind, name, sub, uid } = tile.dataset;
      if (kind === 'album') openAlbum(uri, { name, artist: sub });
      else if (kind === 'artist') openArtist(uri, name);
      else openBox(uid);
      return;
    }
    toggle(tile.dataset, tile);
  }

  /* `data` is a tile's dataset, or the same four fields built by pickRandom for a
     row that may not be on screen. `el` is only there to grey out while it runs. */
  async function toggle(data, el) {
    const { uri, kind, name, uid } = data;
    const key = uid || uri;
    if (!key || state.busy.has(key)) return;
    state.busy.add(key);
    if (el) el.disabled = true;
    try {
      if (kind === 'box') await toggleBoxTile(uid, name);
      else await toggleObject(uri, name);
      // Starting a box ends the implicit mood session; an object is no different.
      moodSessionActive = false;
      // Same two beats as toggleBox: the badge first, the filled tracklist after
      // O2M's asynchronous refill.
      setTimeout(refreshNowPlaying, 800);
      setTimeout(refreshNowPlaying, 3000);
      setTimeout(syncMoodDials, 900);
    } catch (e) {
      setFeedback('Activation error');
    } finally {
      state.busy.delete(key);
      if (el) el.disabled = false;
    }
  }

  async function toggleObject(uri, name) {
    const r = await fetch(`${API}/object_toggle?uri=${encodeURIComponent(uri)}`
                          + `&name=${encodeURIComponent(name || '')}`).then(x => x.json());
    if (!r.ok) { setFeedback(r.error || 'Could not activate'); return; }
    if (r.active) state.active.set(uri, { kind: r.kind, name: name || uri });
    else state.active.delete(uri);
    paint();
    setFeedback((r.active ? '▶ ' : '⏹ ') + (name || uri));
  }

  async function toggleBoxTile(uid, name) {
    /* `/api/box` fills the tracklist before it answers, so its reply describes a
       settled state — and it can honestly say `No action`, when the box was
       already in that state because something else activated it. Flipping the
       tile locally instead of reading that is how one could end up showing the
       reverse of the truth until the next poll. */
    const answer = ((await fetch(API + '/box?uid=' + encodeURIComponent(uid)
                                 + '&mode=toogle').then(r => r.text())) || '').trim();
    if (answer === 'TAG added')        setFeedback('▶ ' + (name || uid));
    else if (answer === 'TAG removed') setFeedback('⏹ ' + (name || uid));
    else                               setFeedback(name || uid);
    // Authoritative, and it paints the list row behind this tile at the same time.
    await refreshActive();
  }

  /* Paints EVERY view of the column from one answer — the mosaic tiles and the
     boxes LIST. The list used to ask `/api/box_activated` once per box on a ten
     minute timer, which is where the drift came from: a box activated by an NFC
     tag, by the Basic view's actuators or by the server itself (the auto box a
     mood apply lights, the watchdog's reload) sat wrong on screen for minutes,
     and the two views could disagree with each other because toggling from one
     never told the other. One request, one painter, one clock. */
  function paint() {
    document.querySelectorAll('#obj-grid .og-tile').forEach(t => {
      const on = t.dataset.kind === 'box'
        ? state.activeBoxes.has(t.dataset.uid)
        : state.active.has(t.dataset.uri);
      t.classList.toggle('active', on);
      t.setAttribute('aria-pressed', String(on));
    });
    document.querySelectorAll('#boxes-wrap .box-btn[data-uid]').forEach(b => {
      b.classList.toggle('active', state.activeBoxes.has(b.dataset.uid));
    });
    // recomputeAutoBox reads those classes back for the live-mode flag, and ends
    // in updateBoxesCount; falling back to the count alone keeps this module
    // usable on a page that has no boxes list.
    if (typeof recomputeAutoBox === 'function') recomputeAutoBox();
    else if (typeof updateBoxesCount === 'function') updateBoxesCount();
  }

  /* One call for the whole column — objects AND boxes — and the only place the
     active state is read. Everything that changes it ends here. */
  async function refreshActive() {
    try {
      const d = await fetch(API + '/active_objects').then(r => r.json());
      state.active = new Map(((d && d.items) || []).map(o => [o.uri, o]));
      state.activeBoxes = new Set((d && d.boxes) || []);
    } catch (e) { return; }
    paint();
  }

  /* ── One at random ─────────────────────────────────────────────────────── */

  /* Draws from what the CURRENT view holds, and only from what is not already
     on: activating something that is already playing is a no-op the user cannot
     tell from a broken button, and toggling it OFF would be the opposite of what
     a die is for. In the list view the DOM is the list, since loadBoxes owns it. */
  function candidates() {
    if (state.mode === 'boxes') {
      return [...document.querySelectorAll('#boxes-wrap .box-btn[data-uid]')]
        .filter(b => !b.classList.contains('active'))
        .map(b => ({ kind: 'box', uid: b.dataset.uid,
                     name: b.querySelector('.box-name')?.textContent || b.dataset.uid, el: b }));
    }
    const kind = KIND_OF[state.mode];
    return visibleRows()
      .filter(r => !isActive(r, kind))
      .map(r => ({ kind, uri: r.uri, uid: r.uid, name: r.name }));
  }

  async function pickRandom() {
    const btn = document.getElementById('panel-random');
    const pool = candidates();
    if (!pool.length) {
      setFeedback(state.rows[state.mode] === null && state.mode !== 'boxes'
        ? 'Still loading…' : 'Everything here is already on');
      return;
    }
    const pick = pool[Math.floor(Math.random() * pool.length)];
    // Resolved before the toggle, not after: it is what pulses while the fill
    // runs, so a random pick looks exactly like a tap on the same tile.
    const el = tileEl(pick);
    scrollTo(el);
    if (btn) btn.disabled = true;
    try {
      // The list view's rows are the existing buttons, with their own handler and
      // their own feedback — click rather than re-implement them here.
      if (pick.el) pick.el.click();
      else await toggle(pick, el);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function tileEl(pick) {
    if (pick.el) return pick.el;
    const key = pick.uid || pick.uri;
    return document.querySelector(
      `#obj-grid .og-tile[data-${pick.uid ? 'uid' : 'uri'}="${CSS.escape(key)}"]`);
  }

  /* Say WHICH one came up, by showing it: a die that only prints a name leaves
     you looking for it. */
  function scrollTo(el) {
    try { el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) {}
  }

  /* ── Counts ────────────────────────────────────────────────────────────── */

  /* What the column header counts, per kind — an activated album is not a box
     and saying "4 boxes" when three of them are records would be wrong. Boxes
     are counted from the list's DOM by updateBoxesCount itself. */
  function activeCounts() {
    const out = {};
    state.active.forEach(o => { out[o.kind] = (out[o.kind] || 0) + 1; });
    return out;
  }

  function init() {
    if (!mount()) return;
    let saved = 'boxes';
    try { saved = localStorage.getItem(STORE_KEY) || 'boxes'; } catch (e) {}
    setMode(saved);   // asks for the active state on its way through
    watchSticky();
  }

  return { init, setMode, refreshActive, activeCounts, pickRandom };
})();
