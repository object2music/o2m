"""Unit tests for the pure popularity scoring formula (stats_v2).

Run from o2m/src:   python3 -m unittest test_popularity
The module under test has no DB dependency, so this runs in isolation.
"""

import unittest
import datetime

try:
    from src.popularity import (
        compute_popularity, is_scorable, DEFAULT_PRIOR_COMPLETION,
        FORCED_LOW_SCORE, LIKE_BONUS, REC_FLOOR,
    )
except ImportError:  # when run from o2m/src directly
    from popularity import (
        compute_popularity, is_scorable, DEFAULT_PRIOR_COMPLETION,
        FORCED_LOW_SCORE, LIKE_BONUS, REC_FLOOR,
    )


class TestPopularity(unittest.TestCase):

    def test_bounds(self):
        """Score is always within [0, 1] across extreme inputs."""
        for args in [
            (1.0, 100, 100, 0),
            (0.0, 100, 0, 100),
            (None, 0, 0, 0),
            (2.0, 1, 5, -3),  # garbage values must still clamp
        ]:
            s = compute_popularity(*args)
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_trash_forced_low(self):
        s = compute_popularity(1.0, 100, 100, 0, liked=1, option_type='trash')
        self.assertEqual(s, FORCED_LOW_SCORE)

    def test_never_played_sits_near_prior(self):
        """A never-finished track collapses to the shrinkage prior, not 0 or 0.5."""
        prior = 0.55
        s = compute_popularity(0.5, 0, 0, 0, prior_completion=prior)
        # quality == prior, volume == 0 → base == QUALITY_W * prior
        self.assertAlmostEqual(s, 0.65 * prior, places=3)

    def test_more_completions_scores_higher(self):
        """Volume + sustained quality should beat a single completion."""
        low = compute_popularity(0.9, 1, 1, 0)
        high = compute_popularity(0.9, 30, 30, 0)
        self.assertGreater(high, low)

    def test_skip_penalty(self):
        """Heavy skipping lowers the score vs a clean history."""
        clean = compute_popularity(0.8, 10, 8, 0)
        skipped = compute_popularity(0.8, 10, 8, 10)
        self.assertGreater(clean, skipped)

    def test_shrinkage_dampens_low_sample(self):
        """One perfect play is pulled toward the prior, below a well-sampled track."""
        prior = 0.5
        one_perfect = compute_popularity(1.0, 1, 1, 0, prior_completion=prior)
        many_good = compute_popularity(0.85, 40, 40, 0, prior_completion=prior)
        self.assertGreater(many_good, one_perfect)

    def test_recency_decay(self):
        """Recent play scores higher than the same stats played long ago."""
        now = datetime.datetime(2026, 6, 17)
        recent = compute_popularity(0.8, 10, 8, 0,
                                    last_read_date=now - datetime.timedelta(days=1),
                                    now=now)
        old = compute_popularity(0.8, 10, 8, 0,
                                 last_read_date=now - datetime.timedelta(days=720),
                                 now=now)
        self.assertGreater(recent, old)
        self.assertGreater(old, 0.0)  # never zeroed out

    def test_recency_floor(self):
        """Recency multiplier never drops below REC_FLOOR even for ancient plays."""
        now = datetime.datetime(2026, 6, 17)
        ancient = compute_popularity(0.8, 10, 8, 0,
                                     last_read_date=now - datetime.timedelta(days=100000),
                                     now=now)
        no_date = compute_popularity(0.8, 10, 8, 0)
        self.assertGreaterEqual(ancient, no_date * REC_FLOOR - 1e-9)

    def test_aware_datetime_does_not_crash(self):
        """tz-aware last_read_date must be handled gracefully."""
        now = datetime.datetime.now(datetime.timezone.utc)
        s = compute_popularity(0.8, 10, 8, 0,
                               last_read_date=now - datetime.timedelta(days=10),
                               now=now)
        self.assertTrue(0.0 <= s <= 1.0)

    def test_like_bonus(self):
        base = compute_popularity(0.7, 10, 8, 0, liked=0)
        liked = compute_popularity(0.7, 10, 8, 0, liked=1)
        self.assertAlmostEqual(liked - base, min(LIKE_BONUS, 1.0 - base), places=3)

    def test_novelty_recent_first_play_boosts(self):
        """A recently first-played track scores above the same track discovered long ago."""
        now = datetime.datetime(2026, 6, 20)
        fresh = compute_popularity(0.6, 3, 2, 0,
                                   first_played_at=now - datetime.timedelta(days=2), now=now)
        old = compute_popularity(0.6, 3, 2, 0,
                                  first_played_at=now - datetime.timedelta(days=2000), now=now)
        self.assertGreater(fresh, old)

    def test_novelty_saturates_with_completions(self):
        """Novelty boost shrinks as the track gets completed more (plateau)."""
        now = datetime.datetime(2026, 6, 20)
        fp = now - datetime.timedelta(days=1)
        few = compute_popularity(0.6, 1, 0, 0, first_played_at=fp, now=now)
        many = compute_popularity(0.6, 30, 30, 0, first_played_at=fp, now=now)
        # isolate novelty by comparing to the no-novelty baseline
        few_base = compute_popularity(0.6, 1, 0, 0, now=now)
        many_base = compute_popularity(0.6, 30, 30, 0, now=now)
        self.assertGreater(few - few_base, many - many_base)

    def test_novelty_unix_timestamp_accepted(self):
        now = datetime.datetime(2026, 6, 20)
        ts = (now - datetime.timedelta(days=3) - datetime.datetime(1970, 1, 1)).total_seconds()
        s = compute_popularity(0.6, 3, 2, 0, first_played_at=ts, now=now)
        self.assertTrue(0.0 <= s <= 1.0)

    def test_playlist_endorsement(self):
        """More playlist memberships raise the score, saturating at PLAYLIST_REF."""
        base = compute_popularity(0.6, 5, 4, 0, playlist_count=0)
        one = compute_popularity(0.6, 5, 4, 0, playlist_count=1)
        many = compute_popularity(0.6, 5, 4, 0, playlist_count=7)
        self.assertGreater(one, base)
        self.assertGreater(many, one)

    def test_is_scorable(self):
        """Only replayable music is scorable; podcasts/infos/radios are excluded."""
        self.assertTrue(is_scorable('spotify:track:abc', 'library'))
        self.assertTrue(is_scorable('local:track:xyz', 'favorites'))
        self.assertFalse(is_scorable('spotify:track:abc', 'podcast'))
        self.assertFalse(is_scorable('spotify:track:abc', 'info'))
        self.assertFalse(is_scorable('https://feed/ep.mp3', 'library'))
        self.assertFalse(is_scorable('podcast:rss:feed', 'library'))
        self.assertTrue(is_scorable('spotify:track:abc', None))


if __name__ == '__main__':
    unittest.main()
