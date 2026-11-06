/* Box subscriptions on a device: the decisions, with no DOM, storage or network,
   so `test_offsubs.js` can run them (node --test). mood.html does the rest.

   An inventory row (`o2m-offline-inv`) says where it came from: `subs`, the boxes
   that hold it, and `tl: false` when the tracklist did not ask for it (a row from
   before subscriptions has no `tl` and counts as the tracklist's). */
const OFFSUBS = (() => {
  const DAY = 86400000;
  const SUBS_SHARE = 0.75;          // of the quota; the tracklist has the rest
  const INFO_TTL = 2 * DAY;         // yesterday's bulletin, unheard, is worth nothing
  const RETRY_LISTENED = DAY / 48;  // a second offline session does not ask again at once
  const RETRY_INCOMPLETE = DAY;     // spotdl needs its time
  const RETRY_IDLE = 7 * DAY;       // nothing was heard here: new episodes, once a week
  const RETRY_FAILED = DAY / 96;    // a file that broke off: soon, then less and less
  const HEARD_TTL = 30 * DAY;

  /* A radio, a TV box, the ALL trigger, a page: nothing a device can hold. */
  function eligible(data, optionType) {
    if (optionType === 'radio') return false;
    const lines = String(data || '').split(/\r?\n/)
      .map(l => l.trim().replace(/^\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*>\s*/, '').trim())
      .filter(l => l && !l.startsWith('#') && l !== '{' && l !== '}' && !/^(dl|mood)\s*:/i.test(l));
    return lines.some(l => !/^(tv:|meta_all$|meta_radios$|https?:\/\/|tunein:|web:|xp:)/.test(l));
  }

  const liveSubs = (m, uids) => (m.subs || []).filter(u => uids.includes(u));
  const isExpired = (m, now) => m.cat === 'info' && (m.subs || []).length > 0
                                && now - (m.at || 0) > INFO_TTL;

  /* Done with: its place may go to something new. */
  function replaceable(m, now) {
    return !!(m.done || m.heardOff || isExpired(m, now));
  }

  /* Who uses what. An item two boxes hold is stored once, so it costs each half. */
  function usage(inv, uids, now) {
    const box = Object.fromEntries(uids.map(u => [u, 0]));
    let tl = 0;
    for (const m of Object.values(inv)) {
      if (replaceable(m, now)) continue;
      const live = liveSubs(m, uids);
      if (live.length) live.forEach(u => { box[u] += (m.bytes || 0) / live.length; });
      else if (m.tl !== false) tl += m.bytes || 0;
    }
    return { box, tl };
  }

  /* An equal part each; what a box with nothing more to offer leaves goes to the
     others, as a shortfall rolls forward between the lines of a box. */
  function allowances(quota, uids, used, exhausted) {
    const out = {};
    let left = quota * SUBS_SHARE, open = uids.slice();
    for (;;) {
      const fair = open.length ? left / open.length : 0;
      const short = open.filter(u => exhausted[u] && (used[u] || 0) < fair);
      if (!short.length) { open.forEach(u => { out[u] = fair; }); return out; }
      short.forEach(u => { out[u] = used[u] || 0; left -= out[u]; });
      open = open.filter(u => !short.includes(u));
    }
  }

  /* Who leaves when `requester` ('tl' or a box uid) needs room, in order. What was
     not heard stays: a subscription is only ever pushed out by being over its part,
     the tracklist only by itself or when it borrowed. */
  function victims(inv, { requester, uids, quota, exhausted, now, cur, pass, queued }) {
    const { box, tl } = usage(inv, uids, now);
    const allow = allowances(quota, uids, box, exhausted || {});
    const over = Object.fromEntries(uids.map(u => [u, box[u] - allow[u]]));
    let tlOver = requester === 'tl' ? Infinity : tl - quota * (1 - SUBS_SHARE);
    const ranked = [];
    const oldest = Object.keys(inv).sort((a, b) => (inv[a].at || 0) - (inv[b].at || 0));
    for (const u of oldest) {
      const m = inv[u], live = liveSubs(m, uids);
      if (u === cur || (pass && pass.has(u))) continue;
      if (m.done) { ranked.push([0, u]); continue; }
      if (queued && queued.has(u)) continue;
      if (isExpired(m, now) || (!live.length && m.tl === false)) ranked.push([1, u]);
      else if (!live.length) {
        if (tlOver > 0) { ranked.push([2, u]); tlOver -= m.bytes || 0; }
      } else if (m.heardOff) ranked.push([3, u]);
      else {
        const b = live.find(x => over[x] > 0);
        if (b) { ranked.push([4, u]); over[b] -= m.bytes || 0; }
      }
    }
    return ranked.sort((a, b) => a[0] - b[0]).map(r => r[1]);
  }

  /* Is a pass due? Nothing else asks the server: with no offline listening this
     answers null for a week. `force` is a gesture (a subscription, the quota). */
  function due(state, now) {
    const since = now - (state.last || 0);
    if (state.force) return 'asked';
    if (!state.last) return 'first';
    if (state.dirty && since >= RETRY_LISTENED) return 'listened';
    if (state.failed && since >= Math.min(RETRY_FAILED * 2 ** (state.failed - 1), DAY)) return 'failed';
    if (state.incomplete && since >= RETRY_INCOMPLETE) return 'incomplete';
    return since >= RETRY_IDLE ? 'idle' : null;
  }

  /* Why not now, from what the browser is willing to say. iOS and desktops say
     nothing about the link, so there the rest of the checks have to do. */
  function blocked({ connection, battery, net }) {
    const c = connection || {};
    if (c.type === 'cellular') return 'not on Wi-Fi';
    if (c.saveData) return 'data saver';
    if (net === 'red') return 'poor network';
    if (battery && !battery.charging && battery.level < 0.2) return 'low battery';
    return '';
  }

  /* What is left to fetch: not held, and not music heard here lately (a fixed
     playlist would hand it straight back). */
  function todo(items, isHeld, heard, now) {
    return items.filter(t => !isHeld(t.uri)
                             && !(heard[t.uri] && now - heard[t.uri] < HEARD_TTL));
  }

  return { eligible, replaceable, usage, allowances, victims, due, blocked, todo, HEARD_TTL };
})();
if (typeof module !== 'undefined') module.exports = OFFSUBS;
