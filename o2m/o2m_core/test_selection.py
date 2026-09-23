"""Tests for o2m_core.selection.

Run from o2m/:  python3 -m unittest o2m_core.test_selection

Two kinds of test, and the first is the reason this file exists.

DIFFERENTIAL — `_old_*` below is a verbatim transcription of the four methods as
they stood inside O2mToMopidy before the extraction (commit e92a90a), reading
plain dicts instead of `self`. Seeded with the same RNG on the same pool, the
old and the new must return the identical list. That is what says the move
changed nothing; the property tests then say the behaviour is the intended one.

PROPERTY — the claims CLAUDE.md makes about the selection engine, asserted:
the two cooldown clocks and which one wins, the DL temperature at both ends,
and the invariants of the sampler.
"""

import datetime
import math
import random
import unittest

from o2m_core import selection


# --------------------------------------------------------------------------
# The pre-extraction implementation, transcribed. Do not "clean up": its value
# is being an independent copy. If a behaviour change is ever intended, this
# is what has to be changed deliberately, and the diff will say so.
# --------------------------------------------------------------------------

def _old_cooldown_factor(uri, last_read_at, now, now_ts, served, read_count, last_seq, seq_tail, T):
    f = 1.0
    stretch = 1.0 + min(read_count or 0, T.cooldown_rc_ref) / float(T.cooldown_rc_ref)
    if last_read_at is not None:
        try:
            lr = last_read_at
            if isinstance(lr, (int, float)):
                lr = datetime.datetime.utcfromtimestamp(lr)
            if getattr(lr, 'tzinfo', None) is not None:
                lr = lr.replace(tzinfo=None)
            age_days = (now - lr).total_seconds() / 86400.0
            cd_days = T.cooldown_days * stretch
            if 0.0 <= age_days < cd_days:
                f = min(f, T.cooldown_mult + (1.0 - T.cooldown_mult) * (age_days / cd_days))
        except Exception:
            pass
    if last_seq and seq_tail:
        try:
            import bisect
            since = len(seq_tail) - bisect.bisect_right(seq_tail, int(last_seq))
            cd_plays = T.cooldown_plays * stretch
            if 0 <= since < cd_plays:
                f = min(f, T.cooldown_mult + (1.0 - T.cooldown_mult) * (since / cd_plays))
        except Exception:
            pass
    sa = served.get(uri)
    if sa is not None and (now_ts - sa) < T.served_cooldown_min * 60.0:
        f *= T.served_mult
    return f


def _old_sample_by_weight(uris, weights, n):
    n = min(n, len(uris))
    if n <= 0:
        return []
    keyed = []
    for u in uris:
        w = weights.get(u, 1e-9)
        if w <= 0:
            w = 1e-9
        keyed.append((random.random() ** (1.0 / w), u))
    keyed.sort(reverse=True)
    return [u for _, u in keyed[:n]]


def _old_mood_pick(uris, n, energy, valence, radius, discover_level,
                   feat, pop, last_read, rc, seq, seq_tail, served, now, now_ts, T):
    if not uris:
        return []
    n = min(n, len(uris))
    k = max(0.0, (10 - discover_level) / 5.0)
    mood_on = (energy is not None and valence is not None)
    sigma = max(radius, 1e-3)
    floor = 0.05 + 0.95 * (min(max(discover_level, 0), 10) / 10.0)

    def _mood_w(u):
        if not mood_on:
            return 1.0
        f = feat.get(u)
        if f is None:
            return floor
        d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
        return max(math.exp(-d2 / (2.0 * sigma * sigma)), floor)

    def _w(u):
        return (max(pop.get(u, 0.5), 1e-6) ** k) * _mood_w(u) \
               * _old_cooldown_factor(u, last_read.get(u), now, now_ts, served,
                                      rc.get(u, 0), seq.get(u), seq_tail, T)

    weights = {u: _w(u) for u in uris}
    result = _old_sample_by_weight(uris, weights, n)
    for u in result:
        served[u] = now_ts
    return result


def _old_expand_pick(uris, n, energy, valence, discover_level,
                     feat, pop, last_read, rc, seq, seq_tail, served, now, now_ts, T):
    if not uris:
        return []
    m = min(n, len(uris))
    mode = T.expand_pick_mode
    sigma = max(discover_level / 20.0 + 0.05, 1e-3)
    MOOD_BONUS = 0.15

    def mood_g(u):
        if energy is None or valence is None:
            return 0.0
        f = feat.get(u)
        if f is None:
            return 0.0
        d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
        return math.exp(-d2 / (2.0 * sigma * sigma))

    def cd(u):
        return _old_cooldown_factor(u, last_read.get(u), now, now_ts, served,
                                    rc.get(u, 0), seq.get(u), seq_tail, T)

    def aff(u):
        return pop.get(u, 0.5) + MOOD_BONUS * mood_g(u)

    if mode == 'temp':
        k = (5 - discover_level) / 2.5
        weights = {u: (max(aff(u), 1e-6) ** k) * cd(u) for u in uris}
        sel = _old_sample_by_weight(uris, weights, m)
    elif mode == 'band':
        vals = sorted(pop.get(u, 0.5) for u in uris)
        p10 = vals[int(0.10 * (len(vals) - 1))]
        p90 = vals[int(0.90 * (len(vals) - 1))]
        target = p90 - (p90 - p10) * (discover_level / 10.0)
        sigma_pop = 0.15
        weights = {u: math.exp(-((pop.get(u, 0.5) - target) ** 2) / (2 * sigma_pop * sigma_pop))
                      * (1.0 + MOOD_BONUS * mood_g(u)) * cd(u) for u in uris}
        sel = _old_sample_by_weight(uris, weights, m)
    else:
        n_explore = int(round(m * discover_level / 10.0))
        ew = {u: (max(aff(u), 1e-6) ** T.exploit_sharpness) * cd(u) for u in uris}
        exploit = _old_sample_by_weight(uris, ew, m - n_explore)
        ex_set = set(exploit)
        rest = [u for u in uris if u not in ex_set]
        xw = {u: cd(u) for u in rest}
        sel = exploit + _old_sample_by_weight(rest, xw, n_explore)

    sel_set = set(sel)
    for u in sel_set:
        served[u] = now_ts
    return [u for u in uris if u in sel_set]


# --------------------------------------------------------------------------

NOW = datetime.datetime(2026, 9, 15, 12, 0, 0)
NOW_TS = 1789000000.0


def make_pool(seed, size=60, mode='hybrid'):
    """A random but reproducible candidate pool, deliberately sparse: most
    tracks carry no mood (~1.6% coverage in prod) and some have never played."""
    r = random.Random(seed)
    uris = [f"spotify:track:{seed}_{i}" for i in range(size)]
    feat, pop, last_read, rc, seq = {}, {}, {}, {}, {}
    for u in uris:
        if r.random() < 0.35:
            feat[u] = (r.random(), r.random())
        if r.random() < 0.8:
            pop[u] = r.random()
        if r.random() < 0.6:
            last_read[u] = NOW - datetime.timedelta(days=r.random() * 12)
        if r.random() < 0.7:
            rc[u] = r.randint(0, 40)
        if r.random() < 0.5:
            seq[u] = r.randint(1, 5000)
    seq_tail = sorted(r.sample(range(1, 5001), 200))
    pool = selection.Pool(uris=uris, feat=feat, pop=pop, last_read=last_read,
                          read_count=rc, seq=seq, seq_tail=seq_tail)
    tun = selection.Tunables(expand_pick_mode=mode)
    return pool, tun


class TestDifferential(unittest.TestCase):
    """The extracted module must reproduce the pre-extraction result exactly."""

    def test_mood_pick_matches_old(self):
        for seed in range(25):
            for dl in (0, 3, 5, 8, 10):
                pool, tun = make_pool(seed)
                served_a, served_b = {}, {}
                random.seed(1000 + seed)
                old = _old_mood_pick(list(pool.uris), 20, 0.6, 0.4, dl / 20.0 + 0.05, dl,
                                     pool.feat, pool.pop, pool.last_read, pool.read_count,
                                     pool.seq, pool.seq_tail, served_a, NOW, NOW_TS, tun)
                random.seed(1000 + seed)
                new = selection.mood_pick(pool, 20, 0.6, 0.4, dl / 20.0 + 0.05, dl,
                                          served_b, NOW, NOW_TS, tun, rng=random)
                self.assertEqual(old, new, f"seed={seed} dl={dl}")
                self.assertEqual(served_a, served_b)

    def test_expand_pick_matches_old_in_all_three_modes(self):
        for mode in ('hybrid', 'temp', 'band'):
            for seed in range(15):
                for dl in (0, 5, 10):
                    pool, tun = make_pool(seed, mode=mode)
                    served_a, served_b = {}, {}
                    random.seed(2000 + seed)
                    old = _old_expand_pick(list(pool.uris), 20, 0.6, 0.4, dl,
                                           pool.feat, pool.pop, pool.last_read, pool.read_count,
                                           pool.seq, pool.seq_tail, served_a, NOW, NOW_TS, tun)
                    random.seed(2000 + seed)
                    new = selection.expand_pick(pool, 20, 0.6, 0.4, dl,
                                                served_b, NOW, NOW_TS, tun, rng=random)
                    self.assertEqual(old, new, f"mode={mode} seed={seed} dl={dl}")
                    self.assertEqual(served_a, served_b)

    def test_cooldown_factor_matches_old(self):
        pool, tun = make_pool(7)
        served = {u: NOW_TS - 60 for u in pool.uris[:10]}
        for u in pool.uris:
            new = selection.cooldown_factor(u, pool, NOW, NOW_TS, served, tun)
            old = _old_cooldown_factor(u, pool.last_read.get(u), NOW, NOW_TS, served,
                                       pool.read_count.get(u, 0), pool.seq.get(u),
                                       pool.seq_tail, tun)
            self.assertEqual(old, new, u)

    def test_no_mood_target_matches_old(self):
        """energy/valence None is the common case — a box with no mood forced."""
        pool, tun = make_pool(3)
        served_a, served_b = {}, {}
        random.seed(99)
        old = _old_mood_pick(list(pool.uris), 15, None, None, 0.3, 5,
                             pool.feat, pool.pop, pool.last_read, pool.read_count,
                             pool.seq, pool.seq_tail, served_a, NOW, NOW_TS, tun)
        random.seed(99)
        new = selection.mood_pick(pool, 15, None, None, 0.3, 5, served_b, NOW, NOW_TS,
                                  tun, rng=random)
        self.assertEqual(old, new)


class TestCooldown(unittest.TestCase):
    """The two clocks, and the rule that the stricter one wins."""

    def _pool(self, **kw):
        base = dict(uris=['u'], last_read={}, read_count={}, seq={}, seq_tail=[])
        base.update(kw)
        return selection.Pool(**base)

    def test_just_played_sits_at_the_floor(self):
        tun = selection.Tunables()
        pool = self._pool(last_read={'u': NOW})
        self.assertAlmostEqual(
            selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun), tun.cooldown_mult)

    def test_past_both_windows_is_free(self):
        tun = selection.Tunables()
        pool = self._pool(last_read={'u': NOW - datetime.timedelta(days=30)},
                          seq={'u': 1}, seq_tail=list(range(1, 400)))
        self.assertEqual(selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun), 1.0)

    def test_depth_brakes_a_track_time_would_have_freed(self):
        """The case that motivated the depth clock: played long ago by the
        calendar, but barely any other music has gone by since."""
        tun = selection.Tunables()
        old_play = NOW - datetime.timedelta(days=10)     # well past cooldown_days
        pool = self._pool(last_read={'u': old_play}, seq={'u': 4990},
                          seq_tail=list(range(4900, 5001)))  # only 10 plays since
        f = selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun)
        self.assertLess(f, 0.25, "depth must still brake it")

    def test_stricter_clock_wins_rather_than_multiplying(self):
        tun = selection.Tunables()
        pool = self._pool(last_read={'u': NOW - datetime.timedelta(days=1.5)},
                          seq={'u': 4990}, seq_tail=list(range(4900, 5001)))
        f_both = selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun)
        f_time = selection.cooldown_factor(
            'u', self._pool(last_read={'u': NOW - datetime.timedelta(days=1.5)}),
            NOW, NOW_TS, {}, tun)
        f_depth = selection.cooldown_factor(
            'u', self._pool(seq={'u': 4990}, seq_tail=list(range(4900, 5001))),
            NOW, NOW_TS, {}, tun)
        self.assertAlmostEqual(f_both, min(f_time, f_depth))
        self.assertGreater(f_both, f_time * f_depth, "must be min(), not a product")

    def test_heavy_rotation_rests_about_twice_as_long(self):
        tun = selection.Tunables()
        age = NOW - datetime.timedelta(days=tun.cooldown_days * 1.5)
        light = selection.cooldown_factor(
            'u', self._pool(last_read={'u': age}, read_count={'u': 0}), NOW, NOW_TS, {}, tun)
        heavy = selection.cooldown_factor(
            'u', self._pool(last_read={'u': age}, read_count={'u': 40}), NOW, NOW_TS, {}, tun)
        self.assertEqual(light, 1.0, "past the base window, a rarely-played track is free")
        self.assertLess(heavy, 1.0, "a heavy-rotation track is still resting")

    def test_served_multiplies_because_it_answers_another_question(self):
        tun = selection.Tunables()
        pool = self._pool()
        self.assertEqual(selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun), 1.0)
        served = {'u': NOW_TS - 60}
        self.assertAlmostEqual(
            selection.cooldown_factor('u', pool, NOW, NOW_TS, served, tun), tun.served_mult)

    def test_no_last_seq_falls_back_to_time_alone(self):
        tun = selection.Tunables()
        pool = self._pool(last_read={'u': NOW - datetime.timedelta(days=30)},
                          seq={}, seq_tail=list(range(1, 400)))
        self.assertEqual(selection.cooldown_factor('u', pool, NOW, NOW_TS, {}, tun), 1.0)


class TestSampler(unittest.TestCase):

    def test_returns_at_most_n_without_duplicates(self):
        uris = [f"u{i}" for i in range(10)]
        w = {u: 1.0 for u in uris}
        for n in (0, 1, 5, 10, 25):
            out = selection.sample_by_weight(uris, w, n, rng=random.Random(4))
            self.assertEqual(len(out), min(max(n, 0), len(uris)))
            self.assertEqual(len(set(out)), len(out))
            self.assertTrue(set(out) <= set(uris))

    def test_weight_dominates_over_many_draws(self):
        uris = [f"u{i}" for i in range(20)]
        w = {u: 1.0 for u in uris}
        w['u0'] = 500.0
        r = random.Random(11)
        hits = sum('u0' in selection.sample_by_weight(uris, w, 3, rng=r) for _ in range(200))
        self.assertGreater(hits, 180)

    def test_zero_and_missing_weights_do_not_raise(self):
        uris = ['a', 'b', 'c']
        out = selection.sample_by_weight(uris, {'a': 0.0, 'b': -1.0}, 3, rng=random.Random(1))
        self.assertEqual(sorted(out), ['a', 'b', 'c'])


class TestTemperature(unittest.TestCase):
    """DL0 -> popularity-dominant, DL10 -> pure random. The core claim."""

    def _pool_with_clear_favourites(self):
        uris = [f"u{i}" for i in range(40)]
        pop = {u: (0.95 if i < 8 else 0.05) for i, u in enumerate(uris)}
        return selection.Pool(uris=uris, pop=pop)

    def test_dl0_favours_popular_and_dl10_does_not(self):
        pool = self._pool_with_clear_favourites()
        tun = selection.Tunables()
        top = set(list(pool.uris)[:8])

        def share(dl, seed):
            r = random.Random(seed)
            got = 0
            for _ in range(60):
                sel = selection.mood_pick(pool, 8, None, None, 0.3, dl, {}, NOW, NOW_TS,
                                          tun, rng=r)
                got += len(top & set(sel))
            return got / (60 * 8)

        low, high = share(0, 5), share(10, 5)
        self.assertGreater(low, 0.75, "DL0 must lean hard on popularity")
        self.assertLess(high, 0.40, "DL10 must be close to uniform")
        self.assertGreater(low, high + 0.3)

    def test_unknown_mood_tracks_stay_selectable(self):
        """~1.6% of tracks carry energy/valence: the pool must never empty."""
        uris = [f"u{i}" for i in range(30)]
        pool = selection.Pool(uris=uris, feat={'u0': (0.9, 0.9)})
        out = selection.mood_pick(pool, 10, 0.1, 0.1, 0.05, 5, {}, NOW, NOW_TS,
                                  selection.Tunables(), rng=random.Random(2))
        self.assertEqual(len(out), 10)


class TestExpandPick(unittest.TestCase):

    def test_source_order_is_preserved(self):
        pool, tun = make_pool(12)
        out = selection.expand_pick(pool, 15, 0.5, 0.5, 5, {}, NOW, NOW_TS, tun,
                                    rng=random.Random(3))
        self.assertEqual(out, [u for u in pool.uris if u in set(out)])

    def test_count_is_capped_by_the_pool(self):
        pool = selection.Pool(uris=['a', 'b', 'c'])
        out = selection.expand_pick(pool, 10, None, None, 5, {}, NOW, NOW_TS,
                                    selection.Tunables(), rng=random.Random(3))
        self.assertEqual(len(out), 3)

    def test_unknown_mode_falls_back_to_hybrid(self):
        pool, _ = make_pool(6)
        a = selection.expand_pick(pool, 10, 0.5, 0.5, 5, {}, NOW, NOW_TS,
                                  selection.Tunables(expand_pick_mode='hybrid'),
                                  rng=random.Random(8))
        b = selection.expand_pick(pool, 10, 0.5, 0.5, 5, {}, NOW, NOW_TS,
                                  selection.Tunables(expand_pick_mode='nonsense'),
                                  rng=random.Random(8))
        self.assertEqual(a, b)

    def test_empty_pool_returns_empty(self):
        for fn, args in ((selection.expand_pick, (0.5, 0.5, 5)),
                         (selection.mood_pick, (0.5, 0.5, 0.3, 5))):
            self.assertEqual(
                fn(selection.Pool(uris=[]), 10, *args, {}, NOW, NOW_TS,
                   selection.Tunables()), [])


class TestTunables(unittest.TestCase):

    def test_sequence_window_covers_the_widest_depth_window(self):
        """A ruler shorter than the stretched depth window silently caps the
        rule — every track older than the tail would look infinitely far away."""
        for plays in (10, 40, 80, 200, 500):
            tun = selection.Tunables(cooldown_plays=plays)
            self.assertGreaterEqual(tun.seq_window, plays * 2)
        self.assertGreaterEqual(selection.Tunables(cooldown_plays=1).seq_window, 200)

    def test_defaults_match_the_engine(self):
        """These are the values the running engine uses; CLAUDE.md documents
        them and the doubling of both windows was a deliberate change."""
        tun = selection.Tunables()
        self.assertEqual(tun.cooldown_days, 3.0)
        self.assertEqual(tun.cooldown_plays, 80)
        self.assertEqual(tun.seq_window, 200)


if __name__ == '__main__':
    unittest.main()


class TestTagProximity(unittest.TestCase):
    """Tags as a weight: selection.tag_similarity and the TAG_BONUS it feeds."""

    IDF = {'rock': 0.2, 'shoegaze': 3.0, 'dream pop': 2.5, 'jazz': 1.0}

    def test_a_rare_shared_tag_outweighs_a_common_one(self):
        seed = {'rock', 'shoegaze'}
        self.assertGreater(selection.tag_similarity(seed, {'shoegaze', 'jazz'}, self.IDF),
                           selection.tag_similarity(seed, {'rock', 'jazz'}, self.IDF))

    def test_bounds_and_unknowns(self):
        seed = {'shoegaze', 'dream pop'}
        self.assertEqual(selection.tag_similarity(seed, seed, self.IDF), 1.0)
        self.assertEqual(selection.tag_similarity(seed, {'jazz'}, self.IDF), 0.0)
        self.assertEqual(selection.tag_similarity(seed, None, self.IDF), 0.0)
        # A tag outside the idf table (noise, single-artist junk) weighs nothing.
        self.assertEqual(selection.tag_similarity({'myartistname'}, {'myartistname'}, self.IDF), 0.0)

    def test_many_tags_do_not_match_everything(self):
        seed = {'shoegaze'}
        broad = set(self.IDF)
        self.assertLess(selection.tag_similarity(seed, broad, self.IDF),
                        selection.tag_similarity(seed, {'shoegaze'}, self.IDF))

    def _counts(self, dl, runs=400):
        uris = [f'u{i}' for i in range(20)]
        pool = selection.Pool(uris=uris, pop={u: 0.5 for u in uris},
                              tag_sim={'u0': 1.0, 'u1': 1.0})
        rng = random.Random(11)
        hits = 0
        for _ in range(runs):
            out = selection.expand_pick(pool, 2, None, None, dl, {}, NOW, NOW_TS,
                                        selection.Tunables(), rng=rng)
            hits += sum(1 for u in out if u in ('u0', 'u1'))
        return hits / (runs * 2)

    def test_close_tags_are_favoured_where_the_pick_exploits(self):
        # Equal popularity, no mood: at DL0 the two tag-close tracks must come up
        # clearly more often than their 2/20 fair share.
        self.assertGreater(self._counts(0), 0.14)

    def test_pure_exploration_ignores_the_bonus(self):
        # DL10 is all explore — uniform by design, the bonus must not leak in.
        self.assertAlmostEqual(self._counts(10), 0.10, delta=0.03)
