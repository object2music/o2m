"""Weighted track selection: the two samplers and the anti-repeat cooldown.

This is the ranking core of the AUTO mix and of every 'smart' box. It used to
live inside `O2mToMopidy` as four methods reading a dozen `self.*` tunables, a
`self._served_at` dict and the database, which made it impossible to exercise
without standing up the whole object — so the two cooldown windows were last
widened on the strength of an ad-hoc simulation rather than a test.

Nothing here touches the database or the clock. A caller reads the candidate
pool once (`Pool`), passes the tunables it is running with (`Tunables`), the
current time and the intra-session `served` map, and gets uris back. `rng` is a
seam for tests: seed it and the sampler is reproducible.

The algorithms themselves are documented in CLAUDE.md under "Auto-Selection
Algorithm"; the comments here explain the code, not the design.
"""

import bisect
import datetime
import math
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tunables:
    """The knobs the samplers read. Mirrors the class attributes on O2mToMopidy.

    `expand_pick_mode` is settable at runtime (A/B testing through
    /api/pick_mode), so build this per call rather than caching it.
    """

    cooldown_mult: float = 0.05       # weight at age 0 (just played), ramps back to 1
    cooldown_days: float = 3.0        # elapsed-time window, in days
    cooldown_rc_ref: int = 20         # read_count giving the maximum window stretch (~2x)
    cooldown_plays: int = 80          # rotation-depth window, in OTHER music plays
    exploit_sharpness: float = 1.3    # hybrid exploit exponent (affinity ** this)
    served_cooldown_min: float = 30.0 # minutes a just-served track stays demoted
    served_mult: float = 0.1          # multiplier applied inside that window
    expand_pick_mode: str = "hybrid"  # hybrid (P0) | temp (P1) | band (P2)

    @property
    def seq_window(self):
        """How far back the play sequence is read, in music plays.

        Derived rather than set: the depth window reaches cooldown_plays x2 for a
        heavy-rotation track, and a ruler shorter than that silently caps the rule —
        every track older than the tail looks infinitely far away and goes free. A
        margin on top so the boundary is never the answer.
        """
        return max(200, int(self.cooldown_plays * 2 * 1.25))


@dataclass
class Pool:
    """What the database says about a set of candidate uris.

    `uris` is the candidate list, already stripped of anything the caller chose
    to exclude. The maps are sparse on purpose — a uri absent from `pop` has no
    popularity yet, which is not the same as a popularity of zero, and each
    reader supplies its own neutral default.
    """

    uris: list
    feat: dict = field(default_factory=dict)        # uri -> (energy, valence)
    pop: dict = field(default_factory=dict)         # uri -> popularity in [0,1]
    last_read: dict = field(default_factory=dict)   # uri -> datetime of last play
    read_count: dict = field(default_factory=dict)  # uri -> lifetime play count
    seq: dict = field(default_factory=dict)         # uri -> stats_raw id of last play
    seq_tail: list = field(default_factory=list)    # recent music-play ids, ascending
    tag_sim: dict = field(default_factory=dict)     # uri -> tag similarity to a seed, [0,1]


def cooldown_factor(uri, pool, now, now_ts, served, tun):
    """Combined anti-repeat down-weight in (0,1].

    TWO clocks measure "recently", and the stricter one wins:

    - ELAPSED TIME, graduated over cooldown_days, stretched up to ~2x for
      heavy-rotation tracks (read_count -> cooldown_rc_ref).
    - ROTATION DEPTH: how much OTHER music has played since, over cooldown_plays,
      stretched the same way.

    Time alone was not enough. Measured on this install, 80% of the intervals
    between two plays of the same track exceed four days — past every time window,
    so the same popular track could be picked again and again as long as the
    calendar moved, however little music had actually gone by. Depth is what a
    listener perceives as repetition; time is only a proxy for it, and a poor one
    when listening is sporadic.

    min(), not a product: each is a full-strength constraint, and multiplying two
    of them would demote a track twice for one offence. The SERVED window is the
    exception and multiplies — it answers a different question.

    A track with no last_seq (never played since the column was added) falls back
    to time alone, so the rule fills in as tracks play rather than needing a
    backfill.
    """
    f = 1.0
    read_count = pool.read_count.get(uri, 0)
    stretch = 1.0 + min(read_count or 0, tun.cooldown_rc_ref) / float(tun.cooldown_rc_ref)

    last_read_at = pool.last_read.get(uri)
    if last_read_at is not None:
        try:
            lr = last_read_at
            if isinstance(lr, (int, float)):
                lr = datetime.datetime.utcfromtimestamp(lr)
            if getattr(lr, 'tzinfo', None) is not None:
                lr = lr.replace(tzinfo=None)
            age_days = (now - lr).total_seconds() / 86400.0
            cd_days = tun.cooldown_days * stretch
            if 0.0 <= age_days < cd_days:
                f = min(f, tun.cooldown_mult + (1.0 - tun.cooldown_mult) * (age_days / cd_days))
        except Exception:
            pass

    last_seq = pool.seq.get(uri)
    if last_seq and pool.seq_tail:
        try:
            # Music plays recorded after this track's own last play.
            since = len(pool.seq_tail) - bisect.bisect_right(pool.seq_tail, int(last_seq))
            cd_plays = tun.cooldown_plays * stretch
            if 0 <= since < cd_plays:
                f = min(f, tun.cooldown_mult + (1.0 - tun.cooldown_mult) * (since / cd_plays))
        except Exception:
            pass

    sa = served.get(uri)
    if sa is not None and (now_ts - sa) < tun.served_cooldown_min * 60.0:
        f *= tun.served_mult
    return f


def sample_by_weight(uris, weights, n, rng=None):
    """Efraimidis-Spirakis weighted sampling without replacement from a
    precomputed {uri: weight} map (key = rand**(1/w), keep the largest).
    Returns up to n uris. Missing/<=0 weights fall back to a tiny epsilon."""
    rng = rng or random
    n = min(n, len(uris))
    if n <= 0:
        return []
    keyed = []
    for u in uris:
        w = weights.get(u, 1e-9)
        if w <= 0:
            w = 1e-9
        keyed.append((rng.random() ** (1.0 / w), u))
    keyed.sort(reverse=True)
    return [u for _, u in keyed[:n]]


def mood_pick(pool, n, energy, valence, radius, discover_level, served, now, now_ts,
              tun, rng=None):
    """Bias a candidate list towards (energy, valence) AND track popularity.

    Two orthogonal axes, both modulated by discover_level, without ever dropping
    tracks:
      - mood: a DL-scaled Gaussian around the target, sigma = radius (tight at DL0
        -> broad at DL10), so the closest tracks are favoured and farther ones fade
        smoothly instead of being cut off. `floor` rises with DL so mood stops
        mattering at DL10 (discovery); unknown-mood (NULL) tracks sit at the floor
        as low-weight fillers, so the pool is never empty even when few tracks
        carry energy/valence (the sparse-coverage case). Single weighted draw —
        no in-mood/rest split.
      - popularity: raised to a temperature k(DL). DL=0 -> k=2 (favour popular),
        DL=5 -> 1 (proportional), DL=10 -> 0 (uniform / pure discovery).

    Before the first popularity recompute (all scores NULL) the weights are
    uniform, so behaviour is identical to a random shuffle.

    Mutates `served`, stamping every uri it returns: that is the intra-session
    half of the cooldown, and the caller shares one map across a whole fill.
    """
    uris = pool.uris
    if not uris:
        return []
    n = min(n, len(uris))

    # Temperature: DL=0 -> k=2 (favor popular), DL=5 -> 1, DL=10 -> 0 (uniform)
    k = max(0.0, (10 - discover_level) / 5.0)

    mood_on = (energy is not None and valence is not None)
    sigma = max(radius, 1e-3)
    floor = 0.05 + 0.95 * (min(max(discover_level, 0), 10) / 10.0)

    def _mood_w(u):
        if not mood_on:
            return 1.0
        f = pool.feat.get(u)
        if f is None:
            return floor
        d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
        return max(math.exp(-d2 / (2.0 * sigma * sigma)), floor)

    # Weight = popularity**k x concentric-mood x anti-repeat cooldown (played + served).
    def _w(u):
        return (max(pool.pop.get(u, 0.5), 1e-6) ** k) * _mood_w(u) \
               * cooldown_factor(u, pool, now, now_ts, served, tun)

    weights = {u: _w(u) for u in uris}
    result = sample_by_weight(uris, weights, n, rng=rng)
    for u in result:
        served[u] = now_ts  # served-cooldown for subsequent selections
    return result


MOOD_BONUS = 0.15   # soft, features-only mood bonus in _expand_pick; unknown = neutral
# Tag proximity to the track a recommendation follows. Heavier than the mood on
# purpose: the tags come from Last.fm's human tagging of the artist and cover 97%
# of artists, while energy/valence are inferred from those same tags plus a
# fallback, and read as noisier in practice. Only set when there is a seed
# (end-of-track and replacement recommendations) — elsewhere tag_sim is empty.
TAG_BONUS = 0.25
BAND_SIGMA = 0.15   # popularity-band spread of the 'band' variant


def tag_similarity(seed_tags, cand_tags, idf):
    """Weighted Jaccard between two tag sets, each tag weighted by its rarity.

    Sharing 'shoegaze' says far more than sharing 'rock', so each tag counts for
    its idf (log of artists / artists carrying it). Jaccard rather than coverage
    of the seed: an artist tagged with forty things would otherwise match
    everything. Tags absent from `idf` (noise, single-artist junk) weigh nothing.
    Returns a value in [0,1]; 0 when either side has no weighted tag."""
    w = lambda ts: {t: idf[t] for t in ts if idf.get(t, 0) > 0}
    a, b = w(seed_tags or ()), w(cand_tags or ())
    if not a or not b:
        return 0.0
    inter = sum(a[t] for t in a.keys() & b.keys())
    union = sum(a.values()) + sum(v for t, v in b.items() if t not in a)
    return inter / union if union > 0 else 0.0


def expand_pick(pool, n, energy, valence, discover_level, served, now, now_ts,
                tun, rng=None, on_debug=None):
    """STOCHASTIC filter of a tapped object's cached tracks, weighted toward a
    DL-controlled popularity target. Always SAMPLES n at random from the pool (no
    deterministic block) so a large playlist ROTATES around the target each tap
    instead of replaying the same top tracks. Returns a source-ordered subset
    (sequencing stays option_sort's job); the count drops below n only when the
    source has fewer tracks.

    Variant = tun.expand_pick_mode:
      - 'hybrid' (P0): n*(1-DL/10) exploit (sampled proportional to affinity
                   ** exploit_sharpness) + n*DL/10 explore (uniform from the
                   rest) — both stochastic.
      - 'temp'   (P1): one sample weighted by affinity**k, k=(5-DL)/2.5
                   (+2 favours the top -> 0 uniform -> -2 favours the obscure).
      - 'band'   (P2): one sample weighted by a Gaussian around a target
                   popularity P*(DL) (~p90 at DL0 -> ~p10 at DL10).

    Tag proximity to a seed (pool.tag_sim, recommendations only) adds a bonus
    heavier than the mood's; both only in the exploit share of 'hybrid'.
    Mood adds a small bonus only when features exist (unknown = neutral), and
    recently-played tracks are down-weighted by the cooldown. Excluding
    hidden/trash is the caller's job, when building the pool: a directly-tapped
    box whose OWN tracks are hidden or trash must still play its own content.
    """
    uris = pool.uris
    if not uris:
        return []
    m = min(n, len(uris))
    mode = tun.expand_pick_mode or 'hybrid'
    sigma = max(discover_level / 20.0 + 0.05, 1e-3)

    def mood_g(u):  # concentric Gaussian proximity to the target in (0,1]; 0 if unknown
        if energy is None or valence is None:
            return 0.0
        f = pool.feat.get(u)
        if f is None:
            return 0.0
        d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
        return math.exp(-d2 / (2.0 * sigma * sigma))

    def cd(u):
        return cooldown_factor(u, pool, now, now_ts, served, tun)

    def tag_g(u):  # tag proximity to the seed in [0,1]; 0 when unknown or no seed
        return pool.tag_sim.get(u, 0.0)

    def aff(u):  # affinity = popularity + soft mood bonus + tag-proximity bonus
        return pool.pop.get(u, 0.5) + MOOD_BONUS * mood_g(u) + TAG_BONUS * tag_g(u)

    if mode == 'temp':
        k = (5 - discover_level) / 2.5  # +2 (favour top) .. 0 (uniform) .. -2 (favour obscure)
        weights = {u: (max(aff(u), 1e-6) ** k) * cd(u) for u in uris}
        sel = sample_by_weight(uris, weights, m, rng=rng)
    elif mode == 'band':
        vals = sorted(pool.pop.get(u, 0.5) for u in uris)
        p10 = vals[int(0.10 * (len(vals) - 1))]
        p90 = vals[int(0.90 * (len(vals) - 1))]
        target = p90 - (p90 - p10) * (discover_level / 10.0)  # DL0->top, DL10->bottom
        weights = {u: math.exp(-((pool.pop.get(u, 0.5) - target) ** 2) / (2 * BAND_SIGMA * BAND_SIGMA))
                      * (1.0 + MOOD_BONUS * mood_g(u) + TAG_BONUS * tag_g(u)) * cd(u) for u in uris}
        sel = sample_by_weight(uris, weights, m, rng=rng)
    else:  # 'hybrid' (P0): stochastic exploit + uniform explore
        n_explore = int(round(m * discover_level / 10.0))
        ew = {u: (max(aff(u), 1e-6) ** tun.exploit_sharpness) * cd(u) for u in uris}
        exploit = sample_by_weight(uris, ew, m - n_explore, rng=rng)
        ex_set = set(exploit)
        rest = [u for u in uris if u not in ex_set]
        xw = {u: cd(u) for u in rest}
        sel = exploit + sample_by_weight(rest, xw, n_explore, rng=rng)

    sel_set = set(sel)
    for u in sel_set:
        served[u] = now_ts  # remember what we just served (served-cooldown)
    if on_debug is not None:
        try:
            ps = [pool.pop.get(u, 0.5) for u in sel_set]
            on_debug(f"expand_pick[{mode}] DL={discover_level} pool={len(uris)} "
                     f"-> {len(sel_set)} tracks, avg_pop={round(sum(ps)/len(ps), 3) if ps else 0}")
        except Exception:
            pass
    return [u for u in uris if u in sel_set]  # source order preserved
