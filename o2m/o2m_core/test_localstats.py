"""The offline journals — o2m_core/localstats.py.

Most of these tests guard against ONE failure, inflation of `read_count`, which
matters because that column feeds popularity and the cooldown and cannot be
repaired after the fact. Each test names the door it closes.
"""

import json
import os
import shutil
import tempfile
import unittest

from o2m_core.localstats import (COMPLETE_FRACTION, MAX_PLAYS,
                                 MIN_PLAYED_FRACTION, LocalStats)


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='o2m-stats-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.now = 1_700_000_000
        self.st = LocalStats(self.root, clock=lambda: self.now)

    def tick(self, seconds=60):
        self.now += seconds


class TestPlaysAreEvents(_Base):

    def test_a_play_is_appended_not_replaced(self):
        """Two listens to one item are two reads. Keyed storage would make
        them one, which is the whole reason plays and positions are apart."""
        self.assertTrue(self.st.record_play('spotify:track:a', 200_000, 200_000))
        self.tick()
        self.assertTrue(self.st.record_play('spotify:track:a', 200_000, 200_000))
        self.assertEqual(len(self.st.plays()), 2)

    def test_a_play_carries_when_it_happened(self):
        """The hourly habits read read_hour, so crediting the flush would
        teach the selector you listen when the network came back."""
        self.st.record_play('spotify:track:a', 200_000, 200_000)
        at = self.st.plays()[0]['at']
        self.tick(3600 * 5)                      # five hours before any flush
        self.assertEqual(self.st.plays()[0]['at'], at)

    def test_an_explicit_timestamp_is_kept(self):
        self.st.record_play('spotify:track:a', 200_000, 200_000, at=1_600_000_000)
        self.assertEqual(self.st.plays()[0]['at'], 1_600_000_000)

    def test_an_artefact_is_not_recorded(self):
        """A tap that starts the wrong item and is corrected at once."""
        frac = MIN_PLAYED_FRACTION / 2
        self.assertFalse(self.st.record_play('spotify:track:a',
                                             int(200_000 * frac), 200_000))
        self.assertEqual(self.st.plays(), [])

    def test_a_play_with_no_length_is_refused(self):
        """A record the server cannot place would still count a read."""
        self.assertFalse(self.st.record_play('spotify:track:a', 120_000, 0))
        self.assertFalse(self.st.record_play('', 120_000, 200_000))
        self.assertEqual(self.st.plays(), [])

    def test_completion_is_flagged_at_the_servers_own_threshold(self):
        self.st.record_play('a', int(200_000 * COMPLETE_FRACTION), 200_000)
        self.st.record_play('b', int(200_000 * (COMPLETE_FRACTION - 0.1)), 200_000)
        self.assertTrue(self.st.plays()[0]['complete'])
        self.assertFalse(self.st.plays()[1]['complete'])

    def test_the_journal_is_bounded_and_keeps_the_newest(self):
        """A Pi offline for a month must not grow a journal it can never
        flush; the newest listening is what still describes the listener."""
        st = LocalStats(self.root, clock=lambda: self.now, max_plays=10)
        for i in range(14):
            st.record_play(f'spotify:track:{i}', 200_000, 200_000)
        plays = st.plays()
        self.assertEqual(len(plays), 10)
        self.assertEqual(plays[0]['uri'], 'spotify:track:4')
        self.assertEqual(plays[-1]['uri'], 'spotify:track:13')

    def test_the_default_bound_is_the_module_constant(self):
        self.assertEqual(LocalStats(self.root).max_plays, MAX_PLAYS)

    def test_recording_stays_cheap_as_the_journal_grows(self):
        """An append-only log appends. The first version read and rewrote the
        whole journal per listen, with an fsync, which measured 38s for 5000
        plays — this is the test that found it."""
        import time as _t
        start = _t.monotonic()
        for i in range(400):
            self.st.record_play(f'spotify:track:{i}', 200_000, 200_000)
        self.assertEqual(len(self.st.plays()), 400)
        self.assertLess(_t.monotonic() - start, 10.0)


class TestFlushingPlays(_Base):

    def test_only_what_was_sent_is_dropped(self):
        """A play recorded DURING the request sits after the prefix that was
        posted, and must survive the clear."""
        for i in range(3):
            self.st.record_play(f'uri{i}', 200_000, 200_000)
        sent = len(self.st.plays())
        self.st.record_play('during-the-request', 200_000, 200_000)
        self.st.clear_plays(sent)
        self.assertEqual([p['uri'] for p in self.st.plays()],
                         ['during-the-request'])

    def test_a_second_listen_in_flight_is_not_matched_away(self):
        """Clearing by uri would drop it; clearing by count does not."""
        self.st.record_play('same', 200_000, 200_000)
        sent = 1
        self.st.record_play('same', 200_000, 200_000)
        self.st.clear_plays(sent)
        self.assertEqual(len(self.st.plays()), 1)

    def test_clearing_nothing_changes_nothing(self):
        self.st.record_play('a', 200_000, 200_000)
        self.st.clear_plays(0)
        self.assertEqual(len(self.st.plays()), 1)


class TestPositionsAreState(_Base):

    def test_a_position_replaces_rather_than_appends(self):
        """Written on pause, on seek, on pagehide and on a 10s tick — appended,
        one listen would become a read per checkpoint."""
        for pos in (10_000, 20_000, 30_000):
            self.st.set_position('podcast+f#g', pos, 600_000)
            self.tick(10)
        rows = self.st.positions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows['podcast+f#g']['position'], 30_000)

    def test_only_a_moved_bookmark_is_unsent(self):
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        self.assertIn('podcast+f#g', self.st.unsent_positions())
        self.st.mark_positions_sent(['podcast+f#g'])
        self.assertEqual(self.st.unsent_positions(), {})

    def test_an_unchanged_bookmark_is_never_re_sent(self):
        """Re-sending it on every reconnection counts a read for a track
        nobody played — the same inflation by another door."""
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        self.st.mark_positions_sent(['podcast+f#g'])
        for _ in range(5):
            self.tick(600)
            self.assertEqual(self.st.unsent_positions(), {})

    def test_it_becomes_unsent_again_when_it_moves(self):
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        self.st.mark_positions_sent(['podcast+f#g'])
        self.tick()
        self.st.set_position('podcast+f#g', 90_000, 600_000)
        self.assertIn('podcast+f#g', self.st.unsent_positions())

    def test_a_bookmark_that_moved_in_flight_is_not_stamped_away(self):
        """mark_positions_sent compares `at`, it does not overwrite it."""
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        self.tick()
        self.st.set_position('podcast+f#g', 90_000, 600_000)   # during the POST
        self.st.mark_positions_sent(['podcast+f#g'])
        # Stamped to the position actually held now, so nothing is lost and
        # nothing is sent twice.
        self.assertEqual(self.st.unsent_positions(), {})
        self.assertEqual(self.st.positions()['podcast+f#g']['position'], 90_000)

    def test_a_bookmark_seeded_from_the_server_is_not_echoed_back(self):
        """It came FROM the server at download time: sending it straight back
        would count a read for something nobody played here."""
        self.st.set_position('podcast+f#g', 120_000, 600_000, synced=True)
        self.assertEqual(self.st.unsent_positions(), {})

    def test_finishing_retires_the_bookmark(self):
        """Kept, the item resumes ten seconds before its own end for ever."""
        self.st.set_position('podcast+f#g', 599_000, 600_000)
        self.assertTrue(self.st.retire_position('podcast+f#g'))
        self.assertEqual(self.st.positions(), {})
        self.assertFalse(self.st.retire_position('podcast+f#g'))


class TestDurability(_Base):

    def test_records_survive_a_new_reader(self):
        """These exist because something is already unreachable: a process
        that dies holding them loses what it was asked to keep."""
        self.st.record_play('a', 200_000, 200_000)
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        fresh = LocalStats(self.root)
        self.assertEqual(len(fresh.plays()), 1)
        self.assertEqual(len(fresh.positions()), 1)

    def test_no_temporary_file_is_left_behind(self):
        self.st.record_play('a', 200_000, 200_000)
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        leftovers = [n for n in os.listdir(self.root) if n.startswith('.journal-')]
        self.assertEqual(leftovers, [])

    def test_a_truncated_last_line_costs_only_itself(self):
        """The whole reason plays are JSON Lines: a power cut in the middle of
        a write used to take the entire journal with it."""
        self.st.record_play('a', 200_000, 200_000)
        self.st.record_play('b', 200_000, 200_000)
        with open(self.st.plays_path, 'a') as f:
            f.write('{"uri": "c", "posi')          # the cut
        kept = [p['uri'] for p in self.st.plays()]
        self.assertEqual(kept, ['a', 'b'])
        # ...and recording again carries on rather than failing.
        self.assertTrue(self.st.record_play('d', 200_000, 200_000))
        self.assertEqual([p['uri'] for p in self.st.plays()], ['a', 'b', 'd'])

    def test_a_journal_of_the_wrong_shape_reads_as_empty(self):
        with open(self.st.positions_path, 'w') as f:
            json.dump(['not', 'a dict'], f)
        self.assertEqual(self.st.positions(), {})

    def test_rows_without_a_uri_are_ignored(self):
        with open(self.st.plays_path, 'w') as f:
            f.write('{"position": 1}\n"junk"\n{"uri": "a", "at": 1}\n')
        self.assertEqual([p['uri'] for p in self.st.plays()], ['a'])


class TestPending(_Base):

    def test_it_counts_without_handing_over_the_records(self):
        self.st.record_play('a', 200_000, 200_000, at=1_000)
        self.st.record_play('b', 200_000, 200_000, at=2_000)
        self.st.set_position('podcast+f#g', 10_000, 600_000)
        self.st.set_position('podcast+f#h', 10_000, 600_000, synced=True)
        self.assertEqual(self.st.pending(), {
            'plays': 2, 'positions': 2, 'positions_unsent': 1,
            'oldest_play_at': 1_000,
        })

    def test_an_empty_root_is_all_zeros(self):
        self.assertEqual(self.st.pending(), {
            'plays': 0, 'positions': 0, 'positions_unsent': 0,
            'oldest_play_at': 0,
        })


if __name__ == '__main__':
    unittest.main()
