/* ══ Object mosaic — activating an album or an artist the way a box is activated
   ══════════════════════════════════════════════════════════════════════════════

   The Boxes column lists the durable objects: a box is a row in the database and
   a physical thing you put down. An album is neither, but everything that happens
   after an activation — the fill, the mood and discover-level ladder, the
   anti-repeat cooldown, the ownership that lets a second tap remove exactly the
   tracks the first one added — is driven by a Box OBJECT, not by its row. So the
   server builds one that is never saved (o2m_core/virtualbox.py) and the whole
   box path runs unchanged; this file is only the way in.

   Three views share the column, switched on the Auto row: the boxes list as it
   was, and two mosaics. A mosaic rather than more rows because these are chosen
   by their cover — 248 album names in a third of a screen is a directory, 248
   covers is a shelf.

   Loaded in <head>, like ds/o2m-marks.js and for the same reason: mood.html's
   init() runs synchronously at the end of its inline script and calls in here.
   Nothing in this file runs at load; the page's globals (API, objEsc, ICON,
   setFeedback…) are read at call time, by which point they exist. */

const OBJGRID = (() => {
  const MODES = ['boxes', 'albums', 'artists'];
  const STORE_KEY = 'o2m-panel-mode';
  /* One request for the whole library rather than a page at a time: the filter
     field below has to search what is NOT on screen to be worth anything, and
     248 rows of json is ~40 KB. Covers are the weight, and they are lazy. */
  const PAGE = 500;

  const state = {
    mode: 'boxes',
    rows: { albums: null, artists: null },   // null = not fetched yet
    more: { albums: false, artists: false },
    filter: '',
    active: new Map(),                        // uri → kind
    busy: new Set(),
  };

  const KIND_OF = { albums: 'album', artists: 'artist' };

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
      ['boxes',   ICON.box,  'Boxes'],
      ['albums',  ICON.disc, 'Albums'],
      ['artists', ICON.user, 'Artists'],
    ].map(([m, icon, label]) =>
      `<button type="button" class="pm-tab" role="tab" data-panel-mode="${m}"`
      + ` title="${label}" aria-label="${label}">${icon}</button>`).join('');
    bar.appendChild(seg);

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
    if (boxes) boxes.hidden = mode !== 'boxes';
    if (grid) grid.hidden = mode === 'boxes';
    if (mode === 'boxes') return;

    if (state.rows[mode] === null) load(mode);
    else render();
  }

  async function load(mode) {
    const grid = document.getElementById('obj-grid');
    if (grid) grid.innerHTML = '<div class="og-empty">Loading…</div>';
    try {
      const d = await fetch(`${API}/library_browse?kind=${mode}&limit=${PAGE}`).then(r => r.json());
      state.rows[mode] = (d && d.items) || [];
      state.more[mode] = !!(d && d.has_more);
    } catch (e) {
      state.rows[mode] = [];
      state.more[mode] = false;
    }
    // No refreshActive() here: tileHTML reads state.active, which init() fills
    // once and every toggle keeps up to date. Re-asking on each mode switch
    // would be a second request for an answer already on hand.
    if (state.mode === mode) render();
  }

  /* ── Render ────────────────────────────────────────────────────────────── */

  function tileHTML(row, kind) {
    const active = state.active.has(row.uri);
    /* The artwork, or a generated cover from the uri when the library has none
       (2 followed artists here). Injected inline rather than through <img src>:
       the generated svg uses the theme's var(--…) and would lose them. */
    const art = row.image
      ? `<img class="og-art" src="${objEsc(row.image)}" alt="" loading="lazy" decoding="async">`
      : `<div class="og-art og-art--gen">${window.O2M ? O2M.coverFor(row.uri) : ''}</div>`;
    return `<button type="button" class="og-tile${active ? ' active' : ''}"`
      + ` data-uri="${objEsc(row.uri)}" data-kind="${objEsc(kind)}"`
      + ` data-name="${objEsc(row.name || '')}" data-sub="${objEsc(row.sub || '')}"`
      + ` aria-pressed="${active}">`
      + `<span class="og-thumb">${art}<span class="og-mark">${ICON.check}</span>`
      + `<span class="og-open" role="button" tabindex="0" data-og-open`
      + ` title="Details" aria-label="Details">${ICON.eye}</span></span>`
      + `<span class="og-name">${objEsc(row.name || '?')}</span>`
      + (row.sub ? `<span class="og-sub">${objEsc(row.sub)}</span>` : '')
      + `</button>`;
  }

  function render() {
    const grid = document.getElementById('obj-grid');
    if (!grid || state.mode === 'boxes') return;
    const kind = KIND_OF[state.mode];
    const all = state.rows[state.mode] || [];
    const q = state.filter;
    const rows = q ? all.filter(r => ((r.name || '') + ' ' + (r.sub || '')).toLowerCase().includes(q)) : all;

    if (!rows.length) {
      grid.innerHTML = `<div class="og-empty">${objEsc(
        all.length ? 'Nothing matches that filter.'
          : (state.mode === 'albums'
             ? 'No saved albums cached yet.'
             : 'No followed artists cached yet.'))}</div>`;
      return;
    }
    let html = rows.map(r => tileHTML(r, kind)).join('');
    // Said, not hidden: the mosaic claims to show the library, so a truncation
    // that goes unmentioned would be a lie about what is not there.
    if (state.more[state.mode] && !q)
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
      const { uri, kind, name, sub } = tile.dataset;
      if (kind === 'album') openAlbum(uri, { name, artist: sub });
      else openArtist(uri, name);
      return;
    }
    toggle(tile);
  }

  async function toggle(tile) {
    const { uri, name } = tile.dataset;
    if (!uri || state.busy.has(uri)) return;
    state.busy.add(uri);
    tile.disabled = true;
    try {
      const r = await fetch(`${API}/object_toggle?uri=${encodeURIComponent(uri)}`
                            + `&name=${encodeURIComponent(name || '')}`).then(x => x.json());
      if (!r.ok) { setFeedback(r.error || 'Could not activate'); return; }
      markActive(uri, r.active ? r.kind : null, name);
      // Starting a box ends the implicit mood session; an object is no different.
      moodSessionActive = false;
      setFeedback((r.active ? '▶ ' : '⏹ ') + (name || uri));
      // Same two beats as toggleBox: the badge first, the filled tracklist after
      // O2M's asynchronous refill.
      setTimeout(refreshNowPlaying, 800);
      setTimeout(refreshNowPlaying, 3000);
      setTimeout(syncMoodDials, 900);
    } catch (e) {
      setFeedback('Activation error');
    } finally {
      state.busy.delete(uri);
      tile.disabled = false;
    }
  }

  function markActive(uri, kind, name) {
    if (kind) state.active.set(uri, { kind, name: name || uri });
    else state.active.delete(uri);
    paint();
  }

  function paint() {
    document.querySelectorAll('#obj-grid .og-tile').forEach(t => {
      const on = state.active.has(t.dataset.uri);
      t.classList.toggle('active', on);
      t.setAttribute('aria-pressed', String(on));
    });
    if (typeof updateBoxesCount === 'function') updateBoxesCount();
  }

  /* One call for the whole grid. The boxes list asks per box, which is fine for
     a dozen rows and would be hundreds of requests here. */
  async function refreshActive() {
    try {
      const d = await fetch(API + '/active_objects').then(r => r.json());
      state.active = new Map(((d && d.items) || []).map(o => [o.uri, o]));
    } catch (e) { return; }
    paint();
  }

  /* What the column header counts, per kind — an activated album is not a box
     and saying "4 boxes" when three of them are records would be wrong. */
  function activeCounts() {
    const out = {};
    state.active.forEach(o => { out[o.kind] = (out[o.kind] || 0) + 1; });
    return out;
  }

  function init() {
    if (!mount()) return;
    let saved = 'boxes';
    try { saved = localStorage.getItem(STORE_KEY) || 'boxes'; } catch (e) {}
    setMode(saved);
    refreshActive();
  }

  return { init, setMode, refreshActive, activeCounts };
})();
