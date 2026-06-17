"""Composite track popularity score (stats_v2).

Pure, DB-free scoring used to rank tracks for selection. The score is a single
float in [0, 1] combining completion quality, listening volume, skip penalty,
recency and explicit signals. It is recomputed in batch
(see DatabaseHandler.recompute_popularity) and persisted on Track.popularity.

Design notes (discussion 2026-06-17):
- Completion quality uses Bayesian shrinkage toward the cohort completion mean,
  so low-sample tracks aren't trusted blindly and never-finished tracks sit at a
  neutral, explorable prior instead of the arbitrary 0.5 default of read_end.
- Volume is a saturating log so heavy-rotation tracks don't dominate linearly.
- Recency is a soft multiplier in [REC_FLOOR, 1]: it boosts recent plays without
  ever zeroing out an old favourite.
- option_type stays OUT of the intrinsic score (favourites already correlate
  with high quality/volume — double counting), except 'trash' which is forced low.

Keep the tunables below grouped so the curve is easy to adjust during tuning.
"""

import math
import datetime

# ── Tunable weights ─────────────────────────────────────────────────────────────
QUALITY_W = 0.65          # weight of completion quality in the earned base
VOLUME_W = 0.35           # weight of listening volume in the earned base
PRIOR_M = 3.0             # shrinkage strength: nb of "virtual" plays at the prior mean
VOLUME_REF = 20           # read_count_end giving ~full volume score (log saturation)
SKIP_W = 0.5              # max fraction of base removed by a 100%-skip history
REC_HALFLIFE_DAYS = 120.0 # recency half-life (days)
REC_FLOOR = 0.6           # recency multiplier floor (old tracks keep 60% of score)
LIKE_BONUS = 0.10         # additive bonus for liked tracks
DEFAULT_PRIOR_COMPLETION = 0.55  # fallback cohort completion mean if none supplied

# option_type values forced to a fixed low score (should not resurface).
_FORCED_LOW = frozenset({'trash'})
FORCED_LOW_SCORE = 0.0

# Content whose lifecycle isn't "replayable music": podcasts/infos are consumed
# once, radios are continuous streams — completion-based popularity is meaningless
# for them, so they are left unscored (popularity = NULL) and ignored by selection.
# Mirrors the exclusion guard used for mood enrichment in o2mtomopidy.
NON_MUSIC_OPTION_TYPES = frozenset({'podcast', 'info'})
_NON_MUSIC_URI_HINTS = ('podcast', 'rss', 'http://', 'https://')


def is_scorable(uri, option_type=None):
    """True if the track is replayable music eligible for a popularity score.

    Podcasts/infos (consume-once) and radios/streams (no completion semantics)
    are excluded so the score stays a pure music replay signal."""
    if option_type in NON_MUSIC_OPTION_TYPES:
        return False
    if uri:
        u = uri.lower()
        if any(h in u for h in _NON_MUSIC_URI_HINTS):
            return False
    return True


def compute_popularity(read_end, read_count, read_count_end, skipped_count,
                       last_read_date=None, liked=0, option_type='library',
                       prior_completion=DEFAULT_PRIOR_COMPLETION, now=None):
    """Return a popularity score in [0, 1] for a single track.

    All raw arguments come straight from the Track row; None values are tolerated.
    prior_completion is the cohort completion mean (read_end averaged over played
    tracks) — see DatabaseHandler.get_completion_prior.
    """
    if option_type in _FORCED_LOW:
        return FORCED_LOW_SCORE

    read_count = read_count or 0
    read_count_end = read_count_end or 0
    skipped_count = skipped_count or 0
    prior = prior_completion if prior_completion is not None else DEFAULT_PRIOR_COMPLETION

    # 1. Completion quality — Bayesian shrinkage toward the cohort prior.
    #    Never-finished tracks (n=0) collapse to the prior (neutral, explorable).
    n = read_count_end
    R = read_end if (read_end is not None and n > 0) else prior
    quality = (n * R + PRIOR_M * prior) / (n + PRIOR_M)

    # 2. Volume — saturating log of completions.
    volume = math.log1p(read_count_end) / math.log1p(VOLUME_REF)
    if volume > 1.0:
        volume = 1.0

    base = QUALITY_W * quality + VOLUME_W * volume

    # 3. Skip penalty — proportional to lifetime skip rate.
    if read_count > 0:
        skip_rate = min(skipped_count / read_count, 1.0)
        base *= (1.0 - SKIP_W * skip_rate)

    # 4. Recency — soft multiplier, never below REC_FLOOR.
    if last_read_date is not None:
        now = now or datetime.datetime.utcnow()
        try:
            # Normalize both ends to naive datetimes to avoid aware/naive mismatch.
            lrd = last_read_date
            if getattr(lrd, 'tzinfo', None) is not None:
                lrd = lrd.replace(tzinfo=None)
            if getattr(now, 'tzinfo', None) is not None:
                now = now.replace(tzinfo=None)
            age_days = max((now - lrd).total_seconds() / 86400.0, 0.0)
            decay = 0.5 ** (age_days / REC_HALFLIFE_DAYS)
            base *= REC_FLOOR + (1.0 - REC_FLOOR) * decay
        except Exception:
            pass  # unparseable date → skip recency rather than fail the score

    # 5. Explicit signal.
    if liked:
        base += LIKE_BONUS

    return max(0.0, min(1.0, base))
