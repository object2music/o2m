// node --test o2m/static/test_offsubs.js
const test = require('node:test');
const assert = require('node:assert');
const S = require('./offsubs.js');
const NOW = 1e12, DAY = 86400000, Q = 1000;
const opts = o => ({ requester: 'a', uids: ['a', 'b'], quota: Q, exhausted: {}, now: NOW,
                     pass: new Set(), queued: new Set(), ...o });

test('only what a device can hold can be subscribed to', () => {
  assert.ok(S.eligible('spotify:playlist:x'));
  assert.ok(S.eligible('#label\n08:00-10:00 > podcast+https://f/rss\ndl:3'));
  assert.ok(S.eligible('auto:library'));
  assert.ok(!S.eligible('meta_all'));
  assert.ok(!S.eligible('tv:https://y\n#x\nmood:calm'));
  assert.ok(!S.eligible('https://stream/a.aac'));
  assert.ok(!S.eligible('spotify:album:x', 'radio'));
  assert.ok(!S.eligible(''));
});

test('the quota is shared, and a box with no more to offer leaves its part', () => {
  assert.deepStrictEqual(S.allowances(Q, ['a', 'b', 'c'], {}, {}), { a: 250, b: 250, c: 250 });
  const got = S.allowances(Q, ['a', 'b', 'c'], { a: 50 }, { a: true });
  assert.deepStrictEqual(got, { a: 50, b: 350, c: 350 });
});

test('an item two boxes hold costs each half, and what is done with costs nothing', () => {
  const inv = { x: { bytes: 100, subs: ['a', 'b'] }, y: { bytes: 100, subs: ['a'], heardOff: 1 },
                z: { bytes: 40 } };
  assert.deepStrictEqual(S.usage(inv, ['a', 'b'], NOW), { box: { a: 50, b: 50 }, tl: 40 });
});

test('finished voice leaves first, then the unsubscribed, the borrowing tracklist, heard music', () => {
  const inv = {
    heard: { bytes: 10, subs: ['a'], heardOff: 1, at: 1 },
    tl:    { bytes: 400, at: 2 },
    gone:  { bytes: 10, subs: ['old'], tl: false, at: 3 },
    done:  { bytes: 10, subs: ['a'], done: true, at: 4 },
    fresh: { bytes: 10, subs: ['a'], at: 5 },
  };
  assert.deepStrictEqual(S.victims(inv, opts()), ['done', 'gone', 'tl', 'heard']);
});

test('unheard subscribed content is never pushed out', () => {
  const inv = { a: { bytes: 10, subs: ['a'], at: 1 }, b: { bytes: 10, subs: ['b'], at: 2 } };
  assert.deepStrictEqual(S.victims(inv, opts({ requester: 'tl' })), []);
  assert.deepStrictEqual(S.victims(inv, opts()), []);
});

test('a box over its part gives back its oldest, and no more than the excess', () => {
  const inv = { o: { bytes: 300, subs: ['a'], at: 1 }, n: { bytes: 300, subs: ['a'], at: 2 } };
  assert.deepStrictEqual(S.victims(inv, opts({ uids: ['a', 'b'] })), ['o']);
});

test('the tracklist within its part is left alone by a box, not by itself', () => {
  const inv = { t: { bytes: 100, at: 1 } };
  assert.deepStrictEqual(S.victims(inv, opts()), []);
  assert.deepStrictEqual(S.victims(inv, opts({ requester: 'tl' })), ['t']);
});

test('what plays, is queued or was just fetched stays; a finished queued episode goes', () => {
  const inv = { c: { bytes: 1, done: true }, q: { bytes: 1, heardOff: 1, subs: ['a'] },
                p: { bytes: 1, done: true }, d: { bytes: 1, done: true } };
  const got = S.victims(inv, opts({ cur: 'c', pass: new Set(['p']), queued: new Set(['q', 'd']) }));
  assert.deepStrictEqual(got, ['d']);
});

test('an unheard bulletin expires after two days, an episode does not', () => {
  const inv = { i: { bytes: 1, cat: 'info', subs: ['a'], at: NOW - 3 * DAY },
                p: { bytes: 1, cat: 'podcast', subs: ['a'], at: NOW - 30 * DAY } };
  assert.deepStrictEqual(S.victims(inv, opts()), ['i']);
});

test('a file that broke off is tried again soon, then less and less', () => {
  const MIN = 60000;
  assert.strictEqual(S.due({ last: NOW - 14 * MIN, failed: 1 }, NOW), null);
  assert.strictEqual(S.due({ last: NOW - 15 * MIN, failed: 1 }, NOW), 'failed');
  assert.strictEqual(S.due({ last: NOW - 15 * MIN, failed: 2 }, NOW), null);
  assert.strictEqual(S.due({ last: NOW - 30 * MIN, failed: 2 }, NOW), 'failed');
  assert.strictEqual(S.due({ last: NOW - DAY, failed: 20 }, NOW), 'failed');
});

test('with no offline listening nothing is due for a week', () => {
  assert.strictEqual(S.due({ last: NOW - 6 * DAY }, NOW), null);
  assert.strictEqual(S.due({ last: NOW - 7 * DAY }, NOW), 'idle');
});

test('what was heard offline, a gesture and an unfinished fill each bring it forward', () => {
  assert.strictEqual(S.due({ last: NOW - DAY, dirty: true }, NOW), 'listened');
  assert.strictEqual(S.due({ last: NOW - 60000, dirty: true }, NOW), null);
  assert.strictEqual(S.due({ last: NOW - 60000, force: true }, NOW), 'asked');
  assert.strictEqual(S.due({ last: NOW - DAY, incomplete: true }, NOW), 'incomplete');
  assert.strictEqual(S.due({ last: NOW - 3600000, incomplete: true }, NOW), null);
  assert.strictEqual(S.due({}, NOW), 'first');
});

test('mobile data, a data saver, a bad link and a low battery wait', () => {
  assert.ok(S.blocked({ connection: { type: 'cellular' } }));
  assert.ok(S.blocked({ connection: { saveData: true } }));
  assert.ok(S.blocked({ net: 'red' }));
  assert.ok(S.blocked({ battery: { charging: false, level: 0.1 } }));
  assert.strictEqual(S.blocked({ connection: { type: 'wifi' }, battery: { charging: true, level: 0.1 } }), '');
  assert.strictEqual(S.blocked({}), '');
});

test('music heard here lately does not come straight back', () => {
  const items = [{ uri: 'held' }, { uri: 'heard' }, { uri: 'old' }, { uri: 'new' }];
  const got = S.todo(items, u => u === 'held', { heard: NOW - DAY, old: NOW - 40 * DAY }, NOW);
  assert.deepStrictEqual(got.map(t => t.uri), ['old', 'new']);
});
