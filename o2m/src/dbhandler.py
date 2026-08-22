import math
import logging, pprint, datetime, random, json, re as _re, unicodedata as _unicodedata

from peewee import IntegrityError, fn, JOIN
from playhouse.migrate import SqliteDatabase, SqliteMigrator
from playhouse.reflection import generate_models, print_model
from playhouse.shortcuts import model_to_dict, dict_to_model


from src.o2mmodels import (
    Box, Track, Stats_Raw, PlaylistLog, db,
    Album, Artist, Genre, TrackArtist, AlbumArtist, ArtistGenre,
    TrackGenre, AlbumGenre, TagFeature,
    Playlist, PlaylistTrack, AlbumTrack, CacheMeta,
    RfShow, RfTaxonomy,
    setup_database,
)

# ── Genre normalization ────────────────────────────────────────────────────────

_GENRE_NOISE = frozenset({
    'seen live', 'favorites', 'favourite', 'favourites', 'love', 'loved',
    'my favorite', 'favourite albums', 'favourite songs', 'my favourites',
    'wishlist', 'to buy', 'owned',
    'good', 'best', 'awesome', 'cool', 'great', 'amazing', 'beautiful',
    'perfect', 'classic', 'all', 'under 2000',
    'american', 'british', 'english', 'german', 'swedish', 'norwegian',
    'japanese', 'australian', 'canadian', 'irish', 'scottish', 'italian', 'spanish',
    'female vocalists', 'male vocalists',
    'various artists', 'unknown', 'albums i own', 'check', 'spotify',
})
_GENRE_NOISE_RE = _re.compile(r'^\d+s?$')


def _normalize_genre(name):
    """Lowercase, strip accents, replace hyphens with spaces, collapse whitespace."""
    n = name.lower().strip()
    n = _unicodedata.normalize('NFKD', n)
    n = ''.join(c for c in n if not _unicodedata.combining(c))
    n = n.replace('-', ' ')
    return ' '.join(n.split())


_RF_STATION_LABELS = {
    'FRANCECULTURE': 'France Culture', 'FRANCEINTER': 'France Inter',
    'FRANCEINFO': 'France Info', 'FRANCEMUSIQUE': 'France Musique',
    'MOUV': 'Mouv', 'FIP': 'FIP',
}


def _is_noise_genre(name):
    return name in _GENRE_NOISE or bool(_GENRE_NOISE_RE.match(name))
from peewee import IntegrityError as PeeweeIntegrityError

'''
Database & Tables creation
Used only one time from the terminal
Usage :
python3
>>> import dbhandler
>>> dbhandler.create_tables()
>>> quit()
'''

CACHE_TTL = {'track': 30, 'artist': 7, 'album': 30, 'playlist': 7, 'album_track': 100}  # days

def create_tables():
    with db:
        db.create_tables([Box, Track, Stats_Raw, Album, Artist, Genre,
                          TrackArtist, AlbumArtist, ArtistGenre,
                          Playlist, PlaylistTrack])

class DatabaseHandler():

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.log.info('DATABASE HANDLER INITIALIZATION')
        setup_database()
        self.boxs = self.get_all_boxs()

    #MISC Functions

    #Manage Podcasts url
    def podcast_uri_remove_max_results(self,uri):
        # Canonical podcast/episode URI: strip the feed-level ?max_results=N param so the
        # same episode (identified by its #guid) maps to ONE stat row, however it was played.
        # No-op for any URI without ?max_results= (radio/tunein http://, spotify, local…),
        # so non-podcast lookups are never altered.
        if not uri or "?max_results=" not in uri:
            return uri
        if "http://" in uri:
            uri = uri.replace("http://", "https://")
        uri1 = uri.split("?max_results=")
        if "#" in uri1[1]:
            uri2 = uri1[1].split("#")
            track_uri = str(uri1[0]) + "#" + str(uri2[1])
        else:
            track_uri = str(uri1[0])
        return track_uri

    #BOX
    def create_box(self, uid, media_url):
        try:
            self.log.info('Creating Box with uid : {} and media url {}'.format(uid, media_url))
            print('Creating Box with uid : {} and media url {}'.format(uid, media_url))
            # box = Box(uid=uid)
            # response = box.save()
            box = Box.create(uid=uid)
            print(box)
            return box
            # if response == 1:
            #     self.log.info('Box created : {}'.format(box))
            #     return box
            # else:
            #     print('error')
            #     print(response)
        except IntegrityError as err:
            self.log.error(err)
    
    def get_all_boxs(self):
        query = Box.select()
        return self.transform_query_to_list(query)

    def box_exists(self, uid):
        return Box.select().where(Box.uid == uid).exists()

    def new_box(self, uid):
        """Create an empty box with the given uid. Unlike create_box, lets
        IntegrityError propagate — callers must check box_exists first."""
        return Box.create(uid=uid)

    def delete_box(self, uid):
        """Delete one box. Returns the number of rows removed (0 = unknown uid)."""
        return Box.delete().where(Box.uid == uid).execute()

    def count_boxes_referencing(self, uid):
        """How many OTHER boxes cascade-include this one via a 'box:<uid>' line.
        Those lines keep working (the cascade skips unknown uids) but the user
        deserves to know the include will go dead."""
        return (Box.select()
                .where((Box.uid != uid) & (Box.data.contains('box:' + uid)))
                .count())

    def resolve_uris(self, uris):
        """Batch-resolve data-line uris to display names, cache-only (never hits
        Spotify). Returns {uri: {'name', 'kind', 'sub'}}; unresolved uris are absent."""
        out = {}
        for uri in uris:
            if not isinstance(uri, str):
                continue
            try:
                if uri.startswith('spotify:track:'):
                    t = Track.get_or_none(Track.uri == uri)
                    if t and t.name:
                        out[uri] = {'name': t.name, 'kind': 'track', 'sub': None}
                elif uri.startswith('spotify:album:'):
                    a = Album.get_or_none(Album.id == uri.rsplit(':', 1)[1])
                    if a and a.name:
                        out[uri] = {'name': a.name, 'kind': 'album', 'sub': a.artist_name}
                elif uri.startswith('spotify:artist:'):
                    a = Artist.get_or_none(Artist.id == uri.rsplit(':', 1)[1])
                    if a and a.name:
                        out[uri] = {'name': a.name, 'kind': 'artist', 'sub': None}
                elif uri.startswith('spotify:playlist:'):
                    p = Playlist.get_or_none(Playlist.id == uri.rsplit(':', 1)[1])
                    if p and p.name:
                        out[uri] = {'name': p.name, 'kind': 'playlist', 'sub': None}
                elif uri.startswith('box:'):
                    b = Box.get_or_none(Box.uid == uri[4:])
                    if b:
                        out[uri] = {'name': b.description or b.uid, 'kind': 'box',
                                    'sub': b.option_type}
            except Exception as err:
                self.log.error(f'resolve_uris: {uri}: {err}')
        return out

    def get_box_by_uid(self, uid):
        #self.log.info('searching for box : {} '.format(uid))
        query = Box.select().where(Box.uid == uid)
        results = self.transform_query_to_list(query)
        #print (results)
        if len(results) > 0:
            return results[0]
        else:
            mopidy_box = self.create_box('mopidy_box','')
            return mopidy_box

    def get_boxes_pinned(self):
        #results = Box.select().where(Box.favorite == 1).get()
        results = list(Box.select().where(Box.favorite == 1).order_by(Box.description).dicts())
        #results = list(Box.select().where(Box.favorite == 1).order_by(Box.description.desc()).dicts())
        if len(results) > 0:
            return results
        else:
            return []

    def get_box_by_data(self, data):
        self.log.info(f'searching for box with data: {data}')
        query = Box.select().where(Box.data == data)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            return results[0] 

    def get_box_by_option_type(self, option_type):
        #self.log.info(f'searching for box with option_type: {option_type}')
        query = Box.select().where(Box.option_type == option_type)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            r = random.randint(0, len(results)-1)
            return results[r]

    def get_boxes_by_option_type(self, option_type):
        """All boxes with this option_type (deterministic list — unlike
        get_box_by_option_type which returns a RANDOM one)."""
        return self.transform_query_to_list(
            Box.select().where(Box.option_type == option_type))

    def get_box_by_data_contains(self, needle):
        """Return the first box whose data field contains `needle` (e.g. 'auto:library')."""
        query = Box.select().where(Box.data.contains(needle))
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            return results[0]
        return None

    def get_media_box(self, uid):
        results = self.get_box_by_uid(uid)
        if len(results > 0):
            box = results[0]
            return box.data
    
    def box_exists(self, uid):
        if len(Box.select().where(Box.uid == uid)) > 0:
            return True
        else:
            return False

    def transform_query_to_list(self, query):
        boxs = []
        for box in query:
            boxs.append(box)
        return boxs

    #STATS
    def create_stat(self, uri):
        uri = self.podcast_uri_remove_max_results(uri)
        try:
            stat = Track.create(uri=uri)
            return stat
        except IntegrityError as err:
            # Course (stat_exists/create concurrents, ex. paused+ended du même
            # podcast) : la ligne vient d'être insérée ailleurs → on la récupère
            # au lieu de renvoyer None (ce None faisait crasher le thread WSListener)
            self.log.error(err)
            return self.get_stat_by_uri(uri)
    
    def get_all_stats(self):
        query = Track.select()
        return self.transform_query_to_list(query)
    
    def get_stat_by_uri(self, uri):
        # Match the canonical (no ?max_results) URI OR the raw one, so lookups work whether
        # or not the row has been migrated yet (safe rollout on un-migrated DBs).
        canon = self.podcast_uri_remove_max_results(uri)
        if canon != uri:
            query = Track.select().where((Track.uri == canon) | (Track.uri == uri))
        else:
            query = Track.select().where(Track.uri == uri)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            #print (results[0])
            return results[0] 
    
    '''def get_stat_by_data(self, data):
        self.log.info(f'searching for stat with data: {data}')
        query = Track.select().where(Track.data == data)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            return results[0] '''

    def get_end_stat(self, uri):
        end = 0
        results = self.get_stat_by_uri(uri)
        if results:
            end = results.read_end
        return end

    def get_pos_stat(self, uri):
        pos = 0
        results = self.get_stat_by_uri(uri)
        if results:
            pos = results.read_position
        return pos

    
    def stat_exists(self, uri):
        canon = self.podcast_uri_remove_max_results(uri)
        if canon != uri:
            q = Track.select().where((Track.uri == canon) | (Track.uri == uri))
        else:
            q = Track.select().where(Track.uri == uri)
        return len(q) > 0

    def get_avg_stat(self, option_type='', column='read_end'):
        if option_type != '':
            query = Track.select(fn.AVG(getattr(Track, column))).where(Track.option_type == option_type).scalar()
        else:
            query = Track.select(fn.AVG(getattr(Track, column))).scalar()
        #results = self.transform_query_to_list(query)
        return query

    # ── Popularity score (stats_v2) ──────────────────────────────────────────────
    def get_completion_prior(self):
        """Cohort completion mean over *played* tracks (read_count_end >= 1).

        Used as the Bayesian prior in the popularity score. Restricting to played
        tracks avoids the 0.5-default contamination from never-played tracks, which
        otherwise drags the global AVG(read_end) toward the median."""
        try:
            val = (Track.select(fn.AVG(Track.read_end))
                   .where(Track.read_count_end >= 1).scalar())
            return float(val) if val is not None else None
        except Exception as e:
            print(f"get_completion_prior error: {e}")
            return None

    def recompute_popularity(self, chunk_size=500):
        """Recompute Track.popularity for every track and persist it in batch.

        Pure scoring lives in src.popularity; this method only wires the cohort
        prior, iterates the table and bulk-updates rows whose score changed.
        Non-music content (podcasts/infos/radios) is left unscored (NULL).
        Returns the number of tracks updated. Cheap enough to run on demand or
        on a periodic TTL."""
        from src.popularity import compute_popularity, is_scorable, DEFAULT_PRIOR_COMPLETION
        prior = self.get_completion_prior() or DEFAULT_PRIOR_COMPLETION
        now = datetime.datetime.utcnow()
        updated = 0
        batch = []

        # Aux signals computed once (not per-row): first-play anchor (novelty) from
        # stats_raw, and playlist-membership count (endorsement).
        first_seen, pl_count = {}, {}
        try:
            for r in db.execute_sql("SELECT uri, MIN(read_date) FROM stats_raw "
                                    "WHERE uri LIKE %s GROUP BY uri", ('spotify:track:%',)):
                first_seen[r[0]] = r[1]
        except Exception as e:
            print(f"recompute_popularity first_seen error: {e}")
        try:
            # Only playlists still in the library endorse a track: one that left the
            # library is no longer drawn from, so it must not keep crediting either.
            # LEFT JOIN + IS NULL: a link whose playlist row is unknown, or never
            # assessed, still counts (see Playlist.in_library).
            for r in db.execute_sql(
                    "SELECT pt.track_uri, COUNT(DISTINCT pt.playlist_id) "
                    "FROM playlisttrack pt "
                    "LEFT JOIN playlist p ON p.id = pt.playlist_id "
                    "WHERE p.in_library IS NULL OR p.in_library <> 0 "
                    "GROUP BY pt.track_uri"):
                pl_count[r[0]] = r[1]
        except Exception as e:
            print(f"recompute_popularity playlist_count error: {e}")

        def _flush(rows):
            if not rows:
                return 0
            try:
                Track.bulk_update(rows, fields=[Track.popularity])
                return len(rows)
            except Exception as e:
                print(f"recompute_popularity flush error: {e}")
                return 0

        for t in Track.select():
            if is_scorable(t.uri, t.option_type):
                new = round(compute_popularity(
                    t.read_end, t.read_count, t.read_count_end, t.skipped_count,
                    last_read_date=t.last_read_date, liked=t.liked,
                    option_type=t.option_type, prior_completion=prior,
                    first_played_at=first_seen.get(t.uri),
                    playlist_count=pl_count.get(t.uri, 0), now=now), 4)
            else:
                new = None  # non-music: leave unscored
            # Only persist rows whose score actually changed (cheap re-runs).
            if new != t.popularity:
                t.popularity = new
                batch.append(t)
            if len(batch) >= chunk_size:
                updated += _flush(batch)
                batch = []
        updated += _flush(batch)

        try:
            self.set_cache_meta('popularity_at', updated or 1)
        except Exception:
            pass
        print(f"recompute_popularity: {updated} tracks scored (prior={round(prior, 3)})")
        return updated

    def recompute_popularity_if_stale(self, ttl_hours=24):
        """Recompute popularity only if the last run is older than ttl_hours (or never).
        A cheap ~daily refresh keeps the time-varying terms (recency, and later the
        add-novelty term) current without a per-selection cost. Returns True if it ran."""
        try:
            _, updated = self.get_cache_meta('popularity_at')
            if updated is not None:
                if isinstance(updated, (int, float)):
                    updated = datetime.datetime.utcfromtimestamp(updated)
                age_h = (datetime.datetime.utcnow() - updated).total_seconds() / 3600.0
                if age_h < ttl_hours:
                    return False  # still fresh
        except Exception as e:
            print(f"recompute_popularity_if_stale check error: {e}")
        self.recompute_popularity()
        return True

    #STATS_RAW
    def clear_today_stats_raw(self):
        """Delete raw listening rows recorded since the start of the current day
        (00:00). The server runs in UTC and read_date/read_hour are stored in UTC,
        so 'today' is the UTC calendar day — consistent with the rest of the app."""
        start_of_day = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0)
        deleted = Stats_Raw.delete().where(Stats_Raw.read_date >= start_of_day).execute()
        print(f"clear_today_stats_raw: {deleted} rows deleted (since {start_of_day.isoformat()})")
        return deleted

    def create_stat_raw(self, uri, read_time, read_hour, username):
        uri = self.podcast_uri_remove_max_results(uri)
        # read_time maps to the model's `read_date` TimestampField (there is no
        # `read_time` field — the old kwarg was silently dropped, so read_date fell
        # back to the field default). Passing it explicitly records the event time.
        stat_raw = Stats_Raw.create(uri=uri, read_date=read_time, read_hour=read_hour, username=username)
        return stat_raw

    def create_playlist_log(self, track_uri, playlist_uri, action, from_option_type=None, to_option_type=None, username=None, track_name=None, playlist_name=None):
        return PlaylistLog.create(
            event_date=datetime.datetime.now(datetime.timezone.utc),
            track_uri=track_uri,
            track_name=track_name,
            playlist_uri=playlist_uri,
            playlist_name=playlist_name,
            action=action,
            from_option_type=from_option_type,
            to_option_type=to_option_type,
            username=username,
        )

    def get_stat_raw_by_hour(self, read_hour, window=0, limit=1, uri_pattern='track:'):
        print (f"Get stat raw by hour {read_hour} {window} {limit} {uri_pattern}")
        # DISTINCT uri: Stats_Raw logs one row PER play, so a track played N times
        # in this hour-window otherwise gets N tickets in the random draw and
        # over-recurs (comfort-track bias). Dedup so each track counts once — the
        # popularity/cooldown weighting in _mood_pick then does the ranking.
        if window > 0:
            query = Stats_Raw.select(Stats_Raw.uri).where((Stats_Raw.read_hour.between(read_hour - window, read_hour + window))&(Stats_Raw.uri.contains(uri_pattern))).distinct().order_by(fn.Rand()).limit(limit)
        else:
            query = Stats_Raw.select(Stats_Raw.uri).where((Stats_Raw.read_hour == read_hour)&(Stats_Raw.uri.contains(uri_pattern))).distinct().order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        #print (results)
        if len(results) > 0:
            uris = [o.uri for o in results]
            return uris

    def get_stat_raw_by_hour1(self, read_hour, window=0, limit=1):
        if window > 0:
            query = Stats_Raw.select().where((Stats_Raw.read_hour.between(read_hour - window, read_hour + window))&(Stats_Raw.uri.contains("local"))).order_by(fn.Rand()).limit(limit)
        else:
            query = Stats_Raw.select().where((Stats_Raw.read_hour == read_hour)&(Stats_Raw.uri.contains("local"))).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            uris = [o.uri for o in results]
            return uris

    def get_uris_new_notread(self, limit=1):
        # Tracks tagged 'new', completed at least once, never skipped — no time constraint
        query = Track.select().where(
            (Track.uri % '%spotify:track%')
            & (Track.read_count_end >= 1)
            & (Track.skipped_count == 0)
            & (Track.option_type == 'new')
        ).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        if results:
            uris = [o.uri for o in results]
            print(f"newnotcompleted:library {len(uris)} tracks")
            return uris
        return []

    def get_uris_newrecent(self, limit=10, days=60):
        """Spotify tracks from the user's LIBRARY that have never been played — the
        'newrecent:library' novelty source (auto-launch / nouveauté).

        Library membership is the signal, not cache recency: a track counts as
        library if it's a liked track (Track.liked == 1) OR belongs to a saved album
        (Album.saved == 1). This deliberately EXCLUDES albums merely browsed/searched
        (lazy backfill sets neither flag), so casual exploration doesn't pollute the
        novelty pool. Podcasts are excluded implicitly by the spotify:track filter.

        `days` is kept for signature compatibility but no longer constrains the query
        (the old cached_at window starved the pool — warmup caches library albums once,
        so their cached_at quickly ages out even though they're still fresh, unplayed
        library content).
        """
        saved_albums = Album.select(Album.id).where(Album.saved == 1)
        query = Track.select().where(
            (Track.uri % '%spotify:track%')
            & (Track.read_count == 0)
            & (Track.skipped_count == 0)
            & ((Track.liked == 1) | (Track.album_id.in_(saved_albums)))
        ).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        if results:
            uris = [o.uri for o in results]
            print(f"newrecent:library {len(uris)} unplayed library tracks")
            return uris
        return []

    # Absolute position (ms) marking a "real engagement" with an episode. read_end is
    # unreliable for podcasts (duration unknown → it stays ~0), so progress is measured
    # by read_position, NOT by proportion.
    PODCAST_RESUME_POS_MS = 120000   # 2 minutes

    def get_uris_podcasts_notread(self, limit=15, discover_level=5):
        # Resume pool of UNFINISHED podcast/video episodes. Eligibility + ranking are
        # driven by the absolute read_position (ms), which is the only reliable progress
        # signal for podcasts. info-typed items go through the news/actuality window.
        skip_penalty = max(1, 8 - discover_level) * 86400  # seconds of recency lost per skip
        # Engagement (position ≥ 2 min) = a genuine resume → exempt from the skip penalty
        # so it ranks by recency (fixes Sismique/Védrine: the old read_end≥0.15 exemption
        # never fired because read_end stays ~0 for podcasts). Below 2 min, skips push it back.
        from peewee import Case
        RES = self.PODCAST_RESUME_POS_MS
        penalized_skips = Case(None, [(Track.read_position >= RES, 0)], Track.skipped_count)
        effective_recency = Track.last_read_date - (penalized_skips * skip_penalty)
        pool_size = min(max(limit, 1) * 4, 60)
        query = Track.select().where(
            ((Track.uri % '%podcast+%') | (Track.uri % '%youtube:video%') | (Track.uri % '%yt:%')
                # Radio France OpenAPI episodes are plain https mp3 URLs with no
                # 'podcast+' marker, so they need their hosts listed explicitly or
                # 'podcasts:unfinished' would silently ignore every one of them.
                | (Track.uri % '%proxycast.radiofrance.fr%')
                | (Track.uri % '%radiofrance-podcast.net%'))
            # read_count_end == 0 → finished at least once = DONE, never re-served.
            & (Track.read_count_end == 0)
            & (Track.read_end < 0.9)
            & (Track.read_position > 0)
            # REPEATED EARLY-SKIP = rejection: started ≥2 times, never got past 2 min →
            # the user keeps dropping it, don't resurface it (a single early skip is
            # tolerated — could be accidental).
            & ~((Track.skipped_count >= 2) & (Track.read_position < RES))
            & (Track.option_type != "library")
            & (Track.option_type != "info")
        ).order_by(effective_recency.desc()).limit(pool_size)
        pool = [o.uri for o in self.transform_query_to_list(query)]
        if not pool:
            return []
        # DL-scaled stochastic pick over the recency-ranked pool (Efraimidis-Spirakis):
        # weight = exp(-rank * alpha), alpha = (10-DL)/10 * 0.7 → DL0 sharp (resume the
        # newest unfinished, alpha=0.7), DL5 moderate, DL10 alpha=0 → uniform (pure
        # hasard among unfinished episodes). Randomness grows linearly with DL.
        alpha = (10 - discover_level) / 10.0 * 0.7
        keyed = []
        for i, uri in enumerate(pool):
            w = math.exp(-i * alpha)
            keyed.append((random.random() ** (1.0 / max(w, 1e-9)), uri))
        keyed.sort(reverse=True)
        return [u for _, u in keyed[:limit]]

    # ─── Cache helpers ─────────────────────────────────────────────────────────

    def is_cache_fresh(self, cached_at, entity_type='track'):
        """Return True if *cached_at* is within the TTL for *entity_type*."""
        if cached_at is None:
            return False
        ttl_days = CACHE_TTL.get(entity_type, 30)
        if isinstance(cached_at, (int, float)):
            cached_at = datetime.datetime.utcfromtimestamp(cached_at)
        return (datetime.datetime.utcnow() - cached_at).days < ttl_days

    # ─── Artist cache ──────────────────────────────────────────────────────────

    def get_artist(self, artist_id):
        """Return Artist from cache, or None if missing/stale."""
        try:
            a = Artist.get_by_id(artist_id)
            if self.is_cache_fresh(a.cached_at, 'artist'):
                return a
        except Artist.DoesNotExist:
            pass
        return None

    def save_artist(self, artist_data):
        """Upsert an artist from a Spotify API artist dict.
        Never overwrites followed/followed_at flags."""
        if not artist_data or not artist_data.get('id'):
            return None
        artist_id = artist_data['id']
        images = artist_data.get('images') or []
        followers = artist_data.get('followers') or {}
        row = {
            'id':         artist_id,
            'uri':        artist_data.get('uri', f'spotify:artist:{artist_id}'),
            'name':       artist_data.get('name'),
            'popularity': artist_data.get('popularity'),
            'followers':  followers.get('total'),
            'image_url':  images[0]['url'] if images else None,
            'storage':    'sp',
            'cached_at':  datetime.datetime.utcnow(),
        }
        update_fields = {k: v for k, v in row.items() if k != 'id'}
        Artist.insert(row).on_conflict(action='update', update=update_fields).execute()
        if artist_data.get('genres'):
            self.save_artist_genres(artist_id, artist_data['genres'])
        return artist_id

    def mark_artist_followed(self, artist_id, followed_at=None):
        """Set followed=1 on an artist row (create it if needed)."""
        updates = {
            'followed':    1,
            'followed_at': followed_at or datetime.datetime.utcnow(),
        }
        Artist.insert({**updates, 'id': artist_id}).on_conflict(
            action='update', update=updates,
        ).execute()

    def mark_artist_unfollowed(self, artist_id):
        """Clear followed=0 on an artist row (no-op if the row doesn't exist)."""
        Artist.update(followed=0, followed_at=None).where(Artist.id == artist_id).execute()

    def get_followed_artist_ids(self):
        """Return list of artist IDs where followed=1."""
        return [a.id for a in Artist.select(Artist.id).where(Artist.followed == 1)]

    def save_artist_genres(self, artist_id, genres):
        """Upsert normalized genre list and link them to *artist_id*."""
        for genre_name in genres:
            n = _normalize_genre(genre_name)
            if not n or _is_noise_genre(n):
                continue
            genre, _ = Genre.get_or_create(name=n)
            try:
                ArtistGenre.insert(
                    {'artist_id': artist_id, 'genre_id': genre.id}
                ).on_conflict_ignore().execute()
            except Exception:
                pass

    def get_artist_genres(self, artist_id):
        """Return list of genre name strings for *artist_id*."""
        rows = (Genre
                .select()
                .join(ArtistGenre, on=(Genre.id == ArtistGenre.genre_id))
                .where(ArtistGenre.artist_id == artist_id))
        return [g.name for g in rows]

    def save_track_genres(self, track_uri, tags_wc):
        """Persist [(tag_name, weight)] for a track (from track.getTopTags). Normalizes names."""
        for tag_name, weight in tags_wc:
            n = _normalize_genre(tag_name)
            if not n or _is_noise_genre(n):
                continue
            genre, _ = Genre.get_or_create(name=n)
            try:
                TrackGenre.insert({'track_uri': track_uri, 'genre_id': genre.id, 'weight': weight}
                                  ).on_conflict_replace().execute()
            except Exception:
                pass

    def save_album_genres(self, album_id, tags_wc):
        """Persist [(tag_name, weight)] for an album (from album.getTopTags). Normalizes names."""
        for tag_name, weight in tags_wc:
            n = _normalize_genre(tag_name)
            if not n or _is_noise_genre(n):
                continue
            genre, _ = Genre.get_or_create(name=n)
            try:
                AlbumGenre.insert({'album_id': album_id, 'genre_id': genre.id, 'weight': weight}
                                  ).on_conflict_replace().execute()
            except Exception:
                pass

    def get_track_genres(self, track_uri):
        """Return [(name, weight)] for a track, or [] if not cached."""
        try:
            rows = (Genre
                    .select(Genre.name, TrackGenre.weight)
                    .join(TrackGenre, on=(Genre.id == TrackGenre.genre_id))
                    .where(TrackGenre.track_uri == track_uri))
            return [(r.name, r.trackgenre.weight) for r in rows]
        except Exception:
            return []

    def get_album_genres(self, album_id):
        """Return [(name, weight)] for an album, or [] if not cached."""
        try:
            rows = (Genre
                    .select(Genre.name, AlbumGenre.weight)
                    .join(AlbumGenre, on=(Genre.id == AlbumGenre.genre_id))
                    .where(AlbumGenre.album_id == album_id))
            return [(r.name, r.albumgenre.weight) for r in rows]
        except Exception:
            return []

    def get_tracks_without_mood(self, limit=50):
        """Return [(uri, track_name, artist_name, album_name, album_id), ...] for tracks that
        have a name but no mood yet (mood IS NULL), ordered by most-listened first.
        Tracks marked mood='_' (no Last.fm data found) are excluded.
        Falls back to album.artist_name when the artist row is missing from the artist table."""
        try:
            rows = db.execute_sql("""
                SELECT t.uri, t.name,
                       COALESCE(a.name, al.artist_name) AS artist_name,
                       al.name AS album_name,
                       al.id   AS album_id
                FROM track t
                JOIN trackartist ta ON ta.track_uri = t.uri AND ta.position = 0
                LEFT JOIN artist a ON a.id = ta.artist_id
                LEFT JOIN album al ON al.id = t.album_id
                WHERE t.mood IS NULL
                  AND t.mood_edited_at IS NULL
                  AND t.name IS NOT NULL
                  AND COALESCE(a.name, al.artist_name) IS NOT NULL
                ORDER BY t.read_count_end DESC
                LIMIT %s
            """, (limit,))
            return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
        except Exception as e:
            print(f"get_tracks_without_mood error: {e}")
            return []

    def count_tracks_without_mood(self):
        """Return count of tracks with no mood data (NULL only, excludes '_' sentinel).
        Uses the same logic as get_tracks_without_mood (COALESCE artist fallback)."""
        try:
            row = db.execute_sql("""
                SELECT COUNT(DISTINCT t.uri)
                FROM track t
                JOIN trackartist ta ON ta.track_uri = t.uri AND ta.position = 0
                LEFT JOIN artist a ON a.id = ta.artist_id
                LEFT JOIN album al ON al.id = t.album_id
                WHERE t.mood IS NULL
                  AND t.mood_edited_at IS NULL
                  AND t.name IS NOT NULL
                  AND COALESCE(a.name, al.artist_name) IS NOT NULL
            """).fetchone()
            return row[0] if row else 0
        except Exception as e:
            print(f"count_tracks_without_mood error: {e}")
            return -1

    def get_sentinel_tracks_with_artist_genres(self, limit=50):
        """Return [(uri, track_name, artist_name, album_name, album_id)] for tracks with mood='_'
        whose primary artist now has genres in ArtistGenre — eligible for a retry."""
        try:
            rows = (
                Track.select(Track.uri, Track.name, Artist.name.alias('artist_name'),
                             Album.name.alias('album_name'), Album.id.alias('album_id'))
                .join(TrackArtist, on=(Track.uri == TrackArtist.track_uri))
                .join(Artist, on=(TrackArtist.artist_id == Artist.id))
                .join(ArtistGenre, on=(ArtistGenre.artist_id == Artist.id))
                .switch(Track)
                .join(Album, JOIN.LEFT_OUTER, on=(Track.album_id == Album.id))
                .where(
                    (Track.mood == '_') &
                    Track.mood_edited_at.is_null() &
                    Track.name.is_null(False) &
                    Artist.name.is_null(False) &
                    (TrackArtist.position == 0)
                )
                .order_by(Track.read_count_end.desc())
                .limit(limit)
                .namedtuples()
            )
            return [(r.uri, r.name, r.artist_name,
                     getattr(r, 'album_name', None),
                     getattr(r, 'album_id', None)) for r in rows]
        except Exception as e:
            print(f"get_sentinel_tracks_with_artist_genres error: {e}")
            return []

    def get_all_sentinel_tracks(self, limit=50):
        """Return [(uri, track_name, artist_name, album_name, album_id)] for ALL mood='_' tracks
        with a name and artist — no filter on ArtistGenre existence."""
        try:
            rows = db.execute_sql("""
                SELECT t.uri, t.name,
                       COALESCE(a.name, al.artist_name) AS artist_name,
                       al.name AS album_name,
                       al.id   AS album_id
                FROM track t
                JOIN trackartist ta ON ta.track_uri = t.uri AND ta.position = 0
                LEFT JOIN artist a ON a.id = ta.artist_id
                LEFT JOIN album al ON al.id = t.album_id
                WHERE t.mood = '_'
                  AND t.mood_edited_at IS NULL
                  AND t.name IS NOT NULL
                  AND COALESCE(a.name, al.artist_name) IS NOT NULL
                ORDER BY t.read_count_end DESC
                LIMIT %s
            """, (limit,))
            return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
        except Exception as e:
            print(f"get_all_sentinel_tracks error: {e}")
            return []

    def get_artist_genres_for_track(self, track_uri):
        """Return genre name strings for the primary artist of a track (ArtistGenre fallback)."""
        try:
            rows = db.execute_sql("""
                SELECT g.name FROM genre g
                JOIN artistgenre ag ON ag.genre_id = g.id
                JOIN trackartist ta ON ta.artist_id = ag.artist_id
                WHERE ta.track_uri = %s AND ta.position = 0
                ORDER BY g.name
            """, (track_uri,))
            return [r[0] for r in rows]
        except Exception as e:
            print(f"get_artist_genres_for_track error: {e}")
            return []

    def get_spotify_tracks_without_features(self, limit=100):
        """Return list of spotify:track: URIs where energy IS NULL or mood='_', ordered by play count."""
        try:
            rows = db.execute_sql("""
                SELECT t.uri FROM track t
                WHERE t.uri LIKE 'spotify:track:%%'
                  AND (t.energy IS NULL OR t.mood = '_')
                ORDER BY t.read_count_end DESC
                LIMIT %s
            """, (limit,))
            return [r[0] for r in rows]
        except Exception as e:
            print(f"get_spotify_tracks_without_features error: {e}")
            return []

    def count_spotify_tracks_without_features(self):
        try:
            row = db.execute_sql("""
                SELECT COUNT(*) FROM track
                WHERE uri LIKE 'spotify:track:%%'
                  AND (energy IS NULL OR mood = '_')
            """).fetchone()
            return row[0] if row else 0
        except Exception as e:
            print(f"count_spotify_tracks_without_features error: {e}")
            return -1

    def update_track_mood(self, uri, mood):
        Track.update(mood=mood).where(Track.uri == uri).execute()

    def update_track_features(self, uri, mood=None, energy=None, valence=None):
        updates = {}
        if mood is not None:
            updates[Track.mood] = mood
        if energy is not None:
            updates[Track.energy] = energy
        if valence is not None:
            updates[Track.valence] = valence
        if updates:
            # Never overwrite a manually-edited (locked) track.
            Track.update(updates).where(
                (Track.uri == uri) & (Track.mood_edited_at.is_null())
            ).execute()

    def upsert_track_features(self, uri, mood=None, energy=None, valence=None):
        """Comme update_track_features mais crée la ligne si absente (édition manuelle).
        Pose mood_edited_at = now → verrouille la track contre tout écrasement futur
        par le warmup (même si seuls energy/valence sont édités, mood restant NULL)."""
        updates = {}
        if mood is not None:
            updates['mood'] = mood
        if energy is not None:
            updates['energy'] = energy
        if valence is not None:
            updates['valence'] = valence
        if not updates:
            return
        updates['mood_edited_at'] = datetime.datetime.utcnow()
        Track.insert({**updates, 'uri': uri}).on_conflict(
            action='update', update=updates,
        ).execute()

    def set_track_liked(self, uri, liked):
        """Pose/retire le flag favori local (crée la ligne si absente)."""
        import datetime as _dt
        updates = {'liked': 1 if liked else 0,
                   'liked_at': _dt.datetime.utcnow() if liked else None}
        Track.insert({**updates, 'uri': uri}).on_conflict(
            action='update', update=updates,
        ).execute()

    def is_track_liked_local(self, uri):
        try:
            t = Track.get_or_none(Track.uri == uri)
            return bool(t and t.liked)
        except Exception:
            return False

    def get_tracks_by_mood_features(self, energy_target, valence_target, radius, genre_names=None, limit=25):
        """Return shuffled URIs of tracks within [energy_target±radius, valence_target±radius].

        Optionally restricts to tracks whose primary artist belongs to one of genre_names.
        Excludes tracks with NULL energy/valence.
        """
        try:
            q = (Track.select(Track.uri)
                 .where(
                     Track.energy.is_null(False) &
                     Track.valence.is_null(False) &
                     (fn.ABS(Track.energy - energy_target) <= radius) &
                     (fn.ABS(Track.valence - valence_target) <= radius)
                 ))

            if genre_names:
                genre_ids = [g.id for g in Genre.select().where(Genre.name << genre_names)]
                if genre_ids:
                    artist_ids = [ag.artist_id for ag in
                                  ArtistGenre.select(ArtistGenre.artist_id)
                                  .where(ArtistGenre.genre_id << genre_ids)]
                    if artist_ids:
                        track_uris_in_genre = [ta.track_uri for ta in
                                               TrackArtist.select(TrackArtist.track_uri)
                                               .where(TrackArtist.artist_id << artist_ids,
                                                      TrackArtist.position == 0)]
                        q = q.where(Track.uri << track_uris_in_genre)

            uris = [r.uri for r in q.namedtuples()]
            random.shuffle(uris)
            return uris[:limit]
        except Exception as e:
            print(f"get_tracks_by_mood_features error: {e}")
            return []

    def get_mood_distribution(self):
        """Return energy/valence stats for UI calibration: count, mean, std per axis."""
        try:
            rows = (Track.select(Track.energy, Track.valence)
                    .where(Track.energy.is_null(False) & Track.valence.is_null(False))
                    .namedtuples())
            energies = [r.energy for r in rows]
            valences = [r.valence for r in rows]
            if not energies:
                return {'count': 0}
            count = len(energies)
            e_mean = sum(energies) / count
            v_mean = sum(valences) / count
            return {
                'count': count,
                'energy': {'mean': round(e_mean, 3), 'min': round(min(energies), 3), 'max': round(max(energies), 3)},
                'valence': {'mean': round(v_mean, 3), 'min': round(min(valences), 3), 'max': round(max(valences), 3)},
            }
        except Exception as e:
            print(f"get_mood_distribution error: {e}")
            return {}

    def get_genres_with_counts(self, limit=100):
        """Return [{name, count}] genres sorted by number of associated tracks."""
        try:
            rows = (Genre.select(Genre.name, fn.COUNT(ArtistGenre.artist_id).alias('cnt'))
                    .join(ArtistGenre, on=(Genre.id == ArtistGenre.genre_id))
                    .group_by(Genre.id)
                    .order_by(fn.COUNT(ArtistGenre.artist_id).desc())
                    .limit(limit)
                    .namedtuples())
            return [{'name': r.name, 'count': r.cnt} for r in rows]
        except Exception as e:
            print(f"get_genres_with_counts error: {e}")
            return []

    def get_artist_ids_without_genres(self, max_count=500):
        """Return artist IDs that have a name in the Artist table but no genre entry yet.

        Only returns artists with a stored name so warmup_artist_genres can search
        by name. Artists from TrackArtist/AlbumArtist without an Artist row are
        ignored — they'd need a separate fetch step to get their name first.
        Randomizes and caps at max_count to stay within a single warmup run.
        """
        already = {ag.artist_id for ag in ArtistGenre.select(ArtistGenre.artist_id)}
        named_ids = {
            a.id
            for a in Artist.select(Artist.id, Artist.name).where(Artist.name.is_null(False))
            if a.id and a.name
        }
        without = list(named_ids - already)
        if max_count and len(without) > max_count:
            random.shuffle(without)
            without = without[:max_count]
        return without

    # ─── TagFeature — data-driven tag scoring ─────────────────────────────────

    def get_all_tag_features(self, filter_type=None):
        """Return all TagFeature rows as list of dicts.
        filter_type: None=all, 'noise'=is_noise=1, 'mood'=has mood, 'feature'=has energy+valence
        """
        try:
            q = TagFeature.select()
            if filter_type == 'noise':
                q = q.where(TagFeature.is_noise == 1)
            elif filter_type == 'mood':
                q = q.where(TagFeature.mood.is_null(False))
            elif filter_type == 'feature':
                q = q.where(TagFeature.energy.is_null(False))
            return [{'tag': t.tag, 'energy': t.energy, 'valence': t.valence,
                     'mood': t.mood, 'is_noise': t.is_noise} for t in q.order_by(TagFeature.tag)]
        except Exception as e:
            print(f"get_all_tag_features error: {e}")
            return []

    def upsert_tag_feature(self, tag, energy=None, valence=None, mood=None, is_noise=0):
        """Insert or replace a TagFeature entry. Tag is normalized before save."""
        n = _normalize_genre(tag)
        if not n:
            return False
        try:
            TagFeature.insert({'tag': n, 'energy': energy, 'valence': valence,
                               'mood': mood, 'is_noise': is_noise}
                              ).on_conflict_replace().execute()
            return True
        except Exception as e:
            print(f"upsert_tag_feature error: {e}")
            return False

    def delete_tag_feature(self, tag):
        n = _normalize_genre(tag)
        try:
            TagFeature.delete().where(TagFeature.tag == n).execute()
            return True
        except Exception as e:
            print(f"delete_tag_feature error: {e}")
            return False

    def get_unknown_tags(self, limit=100):
        """Return tag names that appear in TrackGenre/AlbumGenre/ArtistGenre
        but have no entry in TagFeature — candidates for manual classification."""
        try:
            known = {t.tag for t in TagFeature.select(TagFeature.tag)}
            rows = db.execute_sql("""
                SELECT DISTINCT g.name FROM genre g
                WHERE EXISTS (
                    SELECT 1 FROM trackgenre tg WHERE tg.genre_id = g.id
                    UNION ALL
                    SELECT 1 FROM albumgenre ag WHERE ag.genre_id = g.id
                    UNION ALL
                    SELECT 1 FROM artistgenre agi WHERE agi.genre_id = g.id
                )
                ORDER BY g.name
                LIMIT %s
            """, (limit * 3,))
            unknown = [r[0] for r in rows if r[0] not in known]
            return unknown[:limit]
        except Exception as e:
            print(f"get_unknown_tags error: {e}")
            return []

    # ─── Album cache ───────────────────────────────────────────────────────────

    def get_album(self, album_id):
        """Return Album from cache, or None if missing/stale."""
        try:
            a = Album.get_by_id(album_id)
            if self.is_cache_fresh(a.cached_at, 'album'):
                return a
        except Album.DoesNotExist:
            pass
        return None

    def save_album(self, album_data):
        """Upsert an album from a Spotify API album dict.
        Never overwrites saved/saved_at flags."""
        if not album_data or not album_data.get('id'):
            return None
        album_id = album_data['id']
        images = album_data.get('images') or []
        artists = album_data.get('artists') or []
        artist_name = artists[0].get('name') if artists else None
        row = {
            'id':           album_id,
            'uri':          album_data.get('uri', f'spotify:album:{album_id}'),
            'name':         album_data.get('name'),
            'artist_name':  artist_name,
            'album_type':   album_data.get('album_type'),
            'release_date': album_data.get('release_date'),
            'total_tracks': album_data.get('total_tracks'),
            'image_url':    images[0]['url'] if images else None,
            'storage':      'sp',
            'cached_at':    datetime.datetime.utcnow(),
        }
        # Skip None values on update: a partial source (e.g. a playlist read through
        # Mopidy, which carries no release date or artwork) must enrich the cached row,
        # never blank fields a richer fetch already filled.
        update_fields = {k: v for k, v in row.items() if k != 'id' and v is not None}
        Album.insert(row).on_conflict(action='update', update=update_fields).execute()
        # Link album → artists
        for pos, artist in enumerate(album_data.get('artists') or []):
            if artist.get('id'):
                try:
                    AlbumArtist.insert(
                        {'album_id': album_id, 'artist_id': artist['id'], 'position': pos}
                    ).on_conflict_ignore().execute()
                except Exception:
                    pass
        return album_id

    def mark_album_saved(self, album_id, saved_at=None):
        """Set saved=1 on an album row (create it if needed)."""
        updates = {
            'saved':    1,
            'saved_at': saved_at or datetime.datetime.utcnow(),
        }
        Album.insert({**updates, 'id': album_id}).on_conflict(
            action='update', update=updates,
        ).execute()

    def mark_album_unsaved(self, album_id):
        """Clear saved=0 on an album row (no-op if the row doesn't exist)."""
        Album.update(saved=0, saved_at=None).where(Album.id == album_id).execute()

    def is_album_saved_local(self, album_id):
        """True if the album row is marked saved (local cache)."""
        try:
            a = Album.get_or_none(Album.id == album_id)
            return bool(a and a.saved)
        except Exception:
            return False

    def get_saved_album_ids(self):
        """Return list of album IDs where saved=1."""
        return [a.id for a in Album.select(Album.id).where(Album.saved == 1)]

    def get_saved_albums(self, limit=200):
        """Saved albums as picker rows (uri/name/sub/image) for the box editor."""
        rows = (Album.select().where(Album.saved == 1)
                .order_by(Album.name).limit(limit))
        return [{'uri': a.uri or f'spotify:album:{a.id}',
                 'name': a.name or a.id,
                 'sub': a.artist_name or '',
                 'image': a.image_url or ''} for a in rows]

    def get_followed_artists(self, limit=200):
        """Followed artists as picker rows (uri/name/image) for the box editor."""
        rows = (Artist.select().where(Artist.followed == 1)
                .order_by(Artist.name).limit(limit))
        return [{'uri': a.uri or f'spotify:artist:{a.id}',
                 'name': a.name or a.id,
                 'sub': '',
                 'image': a.image_url or ''} for a in rows]

    def save_album_track(self, album_id, track_uri, position=0):
        """Link a track_uri to an album_id in AlbumTrack cache."""
        if not album_id or not track_uri:
            return
        try:
            AlbumTrack.insert(
                {'album_id': album_id, 'track_uri': track_uri, 'position': position}
            ).on_conflict_ignore().execute()
        except Exception:
            pass

    def get_album_tracks(self, album_id):
        """Return ordered list of track URIs for album_id from AlbumTrack cache, or None."""
        if not album_id:
            return None
        try:
            rows = list(
                AlbumTrack.select(AlbumTrack.track_uri)
                .where(AlbumTrack.album_id == album_id)
                .order_by(AlbumTrack.position)
            )
            if rows:
                return [r.track_uri for r in rows]
        except Exception:
            pass
        return None

    def get_artist_track_uris(self, artist_id):
        """Return cached track URIs linked to artist_id via TrackArtist (cache-only)."""
        if not artist_id:
            return None
        try:
            rows = list(TrackArtist.select(TrackArtist.track_uri)
                        .where(TrackArtist.artist_id == artist_id))
            if rows:
                return [r.track_uri for r in rows]
        except Exception as e:
            print(f"get_artist_track_uris error: {e}")
        return None

    def search_local(self, query, limit=15, offset=0):
        """Keyword search across cached content — the DB-first half of the
        content-search feature. Tracks/artists/albums by name; podcast/info
        episodes by name (Track.option_type). Radio isn't Track-backed (a live
        stream is never logged like a played track) — see
        O2mToMopidy.search_radio_stations for that one.

        Every query is explicitly ordered: `offset` powers the UI's "load more",
        and OFFSET without ORDER BY is undefined in MySQL, so pages would
        silently overlap or skip rows."""
        results = {'tracks': [], 'artists': [], 'albums': [], 'playlists': [], 'podcasts': [], 'info': [], 'boxes': []}
        for b in (Box.select().where(Box.description.contains(query))
                  .order_by(Box.description, Box.uid).limit(limit).offset(offset)):
            results['boxes'].append({
                'uid': b.uid, 'description': b.description,
                'option_type': b.option_type, 'image': b.image_url,
            })
        for t in (Track.select()
                  .where(Track.name.contains(query) & ~(Track.option_type.in_(['podcast', 'info'])))
                  .order_by(Track.last_read_date.desc(), Track.uri)
                  .limit(limit).offset(offset)):
            results['tracks'].append({
                'uri': t.uri, 'name': t.name, 'length': t.duration_ms,
                'artists': self._track_artist_names(t.uri),
            })
        for ot, bucket in (('podcast', 'podcasts'), ('info', 'info')):
            for t in (Track.select()
                      .where((Track.option_type == ot) & Track.name.contains(query))
                      .order_by(Track.last_read_date.desc(), Track.uri)
                      .limit(limit).offset(offset)):
                results[bucket].append({'uri': t.uri, 'name': t.name, 'length': t.duration_ms})
        for a in (Artist.select().where(Artist.name.contains(query))
                  .order_by(Artist.name, Artist.id).limit(limit).offset(offset)):
            results['artists'].append({
                'uri': a.uri or f'spotify:artist:{a.id}', 'name': a.name, 'image': a.image_url,
            })
        for al in (Album.select().where(Album.name.contains(query))
                   .order_by(Album.name, Album.id).limit(limit).offset(offset)):
            results['albums'].append({
                'uri': al.uri or f'spotify:album:{al.id}', 'name': al.name,
                'artist': al.artist_name, 'image': al.image_url,
            })
        for pl in (Playlist.select().where(Playlist.name.contains(query))
                   .order_by(Playlist.name, Playlist.id).limit(limit).offset(offset)):
            results['playlists'].append({
                'uri': pl.uri or f'spotify:playlist:{pl.id}', 'name': pl.name or pl.id,
                'image': pl.image_url,
            })
        return results

    def _track_artist_names(self, track_uri):
        """Artist name(s) for a track from the TrackArtist join (ordered), cache-only."""
        try:
            rows = (Artist.select(Artist.name)
                    .join(TrackArtist, on=(Artist.id == TrackArtist.artist_id))
                    .where(TrackArtist.track_uri == track_uri)
                    .order_by(TrackArtist.position))
            return [r.name for r in rows if r.name]
        except Exception:
            return []

    def get_album_detail(self, album_id):
        """DB-cached album detail (metadata + ordered tracks). None if nothing cached."""
        if not album_id:
            return None
        a = Album.get_or_none(Album.id == album_id)
        tracks = list(Track.select()
                      .where(Track.album_id == album_id)
                      .order_by(Track.track_number))
        if a is None and not tracks:
            return None
        total = a.total_tracks if (a and a.total_tracks) else len(tracks)
        return {
            'source':  'db',
            'name':    a.name if a else None,
            'artist':  a.artist_name if a else None,
            'image':   a.image_url if a else None,
            'total':   total,
            # Partial = the DB only has some of the album's tracks (not a full catalog);
            # the client falls back to a live lookup for a complete listing.
            'partial': bool(total and len(tracks) < total),
            'release': a.release_date if a else None,
            'tracks': [self._track_dict(t) for t in tracks],
        }

    def _track_dict(self, t):
        """Normalized track dict with the O2M per-track cache fields (status/mood/…)."""
        return {
            'uri': t.uri, 'name': t.name, 'length': t.duration_ms,
            'track_number': t.track_number,
            'artists': self._track_artist_names(t.uri),
            'local': bool(t.local_uri),
            'option_type': t.option_type,
            'mood': (t.mood if (t.mood and t.mood != '_') else None),
            'energy': t.energy, 'valence': t.valence,
            'liked': bool(t.liked),
        }

    def get_artist_detail(self, artist_id):
        """DB-cached artist detail (metadata + genres + known tracks + albums). None if empty."""
        if not artist_id:
            return None
        a = Artist.get_or_none(Artist.id == artist_id)
        track_uris = [r.track_uri for r in TrackArtist.select(TrackArtist.track_uri)
                      .where(TrackArtist.artist_id == artist_id)]
        tracks = []
        if track_uris:
            rows = list(Track.select().where(Track.uri.in_(track_uris[:300])))
            rows.sort(key=lambda t: ((t.popularity or 0), (t.read_count_end or 0)), reverse=True)
            tracks = rows[:50]
        album_ids = [r.album_id for r in AlbumArtist.select(AlbumArtist.album_id)
                     .where(AlbumArtist.artist_id == artist_id)]
        albums = []
        if album_ids:
            for al in Album.select().where(Album.id.in_(album_ids)):
                albums.append({'uri': al.uri or f'spotify:album:{al.id}', 'name': al.name})
        genres = self.get_artist_genres(artist_id) or []
        if a is None and not tracks and not albums:
            return None
        return {
            'source':     'db',
            'name':       a.name if a else None,
            'image':      a.image_url if a else None,
            'popularity': a.popularity if a else None,
            'followers':  a.followers if a else None,
            'genres':     genres,
            'tracks':     [self._track_dict(t) for t in tracks],
            'albums':     albums,
        }

    # ─── Track (stats) cache ───────────────────────────────────────────────────

    def get_track(self, uri):
        """Return Stats row with fresh cache metadata, or None."""
        try:
            t = Track.get_by_id(uri)
            if self.is_cache_fresh(t.cached_at, 'track'):
                return t
        except Track.DoesNotExist:
            pass
        return None

    def get_cached_album_id(self, track_uri):
        """Return album_id for track_uri from DB (any freshness), or None."""
        try:
            t = Track.get_by_id(track_uri)
            if t.album_id:
                return t.album_id
        except Exception:
            pass
        return None

    def get_cached_artist_id(self, track_uri):
        """Return a random artist_id for track_uri from TrackArtist table, or None."""
        try:
            rows = list(TrackArtist.select().where(TrackArtist.track_uri == track_uri))
            if rows:
                return random.choice(rows).artist_id
        except Exception:
            pass
        return None

    def save_track_metadata(self, track_data):
        """Update (or create) a Stats row with Spotify track metadata.

        *track_data* is the Spotify API track dict (full or simplified).
        Playback stats (read_count etc.) are never overwritten.
        """
        if not track_data or not track_data.get('uri'):
            return None
        uri = track_data['uri']
        album = track_data.get('album') or {}
        album_id = album.get('id')

        updates = {
            'name':         track_data.get('name'),
            'duration_ms':  track_data.get('duration_ms'),
            'track_number': track_data.get('track_number'),
            'album_id':     album_id,
            'preview_url':  track_data.get('preview_url'),
            'cached_at':    datetime.datetime.utcnow(),
            'storage':      'local' if uri.startswith('local:') else 'sp',
        }

        # Upsert: create stat row if not present, update metadata fields otherwise.
        # Same rule as save_album — a partial source must not blank fields already filled.
        Track.insert({**updates, 'uri': uri}).on_conflict(
            action='update',
            update={k: v for k, v in updates.items() if v is not None},
        ).execute()

        # Cache album when present
        if album and album_id:
            self.save_album(album)

        # Link track → album
        if album_id:
            self.save_album_track(album_id, uri, track_data.get('track_number') or 0)

        # Link track → artists
        for pos, artist in enumerate(track_data.get('artists') or []):
            if artist.get('id'):
                try:
                    TrackArtist.insert(
                        {'track_uri': uri, 'artist_id': artist['id'], 'position': pos}
                    ).on_conflict_ignore().execute()
                except Exception:
                    pass

        return uri

    # ─── Playlist cache ────────────────────────────────────────────────────────

    def save_playlist(self, playlist_data):
        """Upsert a playlist from a Spotify API playlist dict."""
        if not playlist_data or not playlist_data.get('id'):
            return None
        pl_id = playlist_data['id']
        images = playlist_data.get('images') or []
        owner = playlist_data.get('owner') or {}
        row = {
            'id':           pl_id,
            'uri':          playlist_data.get('uri', f'spotify:playlist:{pl_id}'),
            'name':         playlist_data.get('name'),
            'description':  playlist_data.get('description'),
            'owner_id':     owner.get('id'),
            'total_tracks': (playlist_data.get('tracks') or {}).get('total'),
            'snapshot_id':  playlist_data.get('snapshot_id'),
            'image_url':    images[0]['url'] if images else None,
            'storage':      'sp',
            'cached_at':    datetime.datetime.utcnow(),
        }
        Playlist.insert(row).on_conflict_replace().execute()
        return pl_id

    def save_playlist_track(self, playlist_id, track_uri, position=0, added_at=None):
        """Link a track to a playlist (upsert)."""
        import datetime
        if isinstance(added_at, str):
            try:
                added_at = datetime.datetime.strptime(added_at, '%Y-%m-%dT%H:%M:%SZ')
            except Exception:
                added_at = None
        try:
            PlaylistTrack.insert({
                'playlist_id': playlist_id,
                'track_uri':   track_uri,
                'position':    position,
                'added_at':    added_at,
            }).on_conflict_ignore().execute()
        except Exception as e:
            print(f"save_playlist_track error: {e}")

    def get_playlist(self, playlist_id):
        """Return Playlist from cache, or None if missing/stale (TTL 7 days)."""
        try:
            p = Playlist.get_by_id(playlist_id)
            if self.is_cache_fresh(p.cached_at, 'playlist'):
                return p
        except Playlist.DoesNotExist:
            pass
        return None

    def get_playlist_track_uris(self, playlist_id):
        """Return cached track URIs for a playlist, or empty list if none."""
        rows = list(PlaylistTrack.select(PlaylistTrack.track_uri)
                    .where(PlaylistTrack.playlist_id == playlist_id))
        return [r.track_uri for r in rows]

    def drop_playlist(self, playlist_id):
        """Forget a playlist entirely — its track links and its metadata row.
        For playlists that disappeared from the account (deleted or unfollowed);
        leaving them behind would let selection draw from a playlist that is gone."""
        try:
            links = PlaylistTrack.delete().where(PlaylistTrack.playlist_id == playlist_id).execute()
            Playlist.delete().where(Playlist.id == playlist_id).execute()
            return links
        except Exception as e:
            self.log.error(f"drop_playlist {playlist_id}: {e}")
            return 0

    def get_all_cached_playlist_ids(self, in_library_only=False):
        """Return IDs of all playlists that have at least one cached track.
        With *in_library_only*, skip the ones that left the account's library —
        their cache is kept, but nothing should be played from them any more."""
        rows = (PlaylistTrack.select(PlaylistTrack.playlist_id)
                .group_by(PlaylistTrack.playlist_id))
        ids = [r.playlist_id for r in rows]
        if not in_library_only:
            return ids
        gone = {p.id for p in Playlist.select(Playlist.id)
                .where(Playlist.id.in_(ids) & (Playlist.in_library == False))}  # noqa: E712
        return [i for i in ids if i not in gone]

    def set_playlists_in_library(self, library_ids):
        """Flag which cached playlists are still in the account's library.
        *library_ids* must come from a COMPLETE listing — a truncated one would
        mark half the library as gone."""
        if not library_ids:
            return 0
        try:
            Playlist.update(in_library=True).where(Playlist.id.in_(list(library_ids))).execute()
            return (Playlist.update(in_library=False)
                    .where(Playlist.id.not_in(list(library_ids)))
                    .where((Playlist.in_library.is_null()) | (Playlist.in_library == True))  # noqa: E712
                    .execute())
        except Exception as e:
            self.log.error(f"set_playlists_in_library: {e}")
            return 0

    def get_playlists_for_select(self, owner_id=None):
        """Cached playlists for the edition picker. owned=True if owner_id matches."""
        rows = list(Playlist.select(Playlist.id, Playlist.name, Playlist.uri, Playlist.owner_id)
                    .order_by(Playlist.name))
        out = []
        for p in rows:
            out.append({
                'id':   p.id,
                'name': p.name or p.id,
                'uri':  p.uri or f'spotify:playlist:{p.id}',
                'owned': bool(owner_id) and p.owner_id == owner_id,
            })
        return out

    def get_playlists_with_track(self, track_uri):
        """Names/ids of cached playlists currently containing the track."""
        rows = list(PlaylistTrack.select(PlaylistTrack.playlist_id)
                    .where(PlaylistTrack.track_uri == track_uri))
        ids = [r.playlist_id for r in rows]
        if not ids:
            return []
        names = {p.id: (p.name or p.id)
                 for p in Playlist.select(Playlist.id, Playlist.name).where(Playlist.id.in_(ids))}
        return [{'id': i, 'name': names.get(i, i)} for i in ids]

    def remove_playlist_track(self, playlist_id, track_uri):
        PlaylistTrack.delete().where(
            (PlaylistTrack.playlist_id == playlist_id) & (PlaylistTrack.track_uri == track_uri)
        ).execute()

    def reconcile_playlist_tracks(self, playlist_id, current_uris):
        """Drop playlist↔track links no longer present in the Spotify playlist
        (tracks removed directly on Spotify). `current_uris` = the FULL current
        set of the playlist — callers MUST pass it only after a complete fetch.
        An empty set legitimately means the playlist was emptied."""
        try:
            cond = (PlaylistTrack.playlist_id == playlist_id)
            if current_uris:
                cond = cond & (PlaylistTrack.track_uri.not_in(list(current_uris)))
            return PlaylistTrack.delete().where(cond).execute()
        except Exception as e:
            self.log.error(f"reconcile_playlist_tracks: {e}")
            return 0

    def get_random_played_track_uris(self, limit):
        """Last-resort fallback: random spotify tracks from play history."""
        rows = list(Track.select(Track.uri)
                    .where((Track.read_count > 0) & (Track.storage == 'sp')))
        uris = [r.uri for r in rows]
        if not uris:
            return []
        random.shuffle(uris)
        return uris[:limit]

    # ─── Liked tracks ──────────────────────────────────────────────────────────

    def get_local_uri(self, spotify_uri):
        """Return the local file URI for a spotify:track: URI, or None."""
        try:
            t = Track.get_by_id(spotify_uri)
            return t.local_uri or None
        except Track.DoesNotExist:
            return None

    def set_local_uri(self, spotify_uri, local_uri):
        """Store (or clear) the local file URI for a spotify:track: URI."""
        Track.insert({'uri': spotify_uri, 'local_uri': local_uri}).on_conflict(
            action='update', update={'local_uri': local_uri}
        ).execute()

    def clear_local_uri_by_file(self, local_uri):
        """Set local_uri=NULL for all tracks with this local file URI."""
        Track.update(local_uri=None).where(Track.local_uri == local_uri).execute()

    def mark_track_liked(self, uri, liked_at=None):
        """Set liked=1 on a track row (create it if needed)."""
        if isinstance(liked_at, str):
            try:
                liked_at = datetime.datetime.strptime(liked_at, '%Y-%m-%dT%H:%M:%SZ')
            except Exception:
                liked_at = None
        updates = {
            'liked':    1,
            'liked_at': liked_at or datetime.datetime.utcnow(),
        }
        Track.insert({**updates, 'uri': uri}).on_conflict(
            action='update',
            update=updates,
        ).execute()

    def reconcile_liked(self, liked_uris):
        """Clear liked=1 on tracks no longer in the Spotify liked set (un-likes
        done directly on Spotify). `liked_uris` = the COMPLETE set currently
        liked. Callers MUST pass it only after a complete fetch, and skip the
        call when the set is empty (guarded here too) so a transient empty API
        response can never wipe every like."""
        if not liked_uris:
            return 0
        try:
            return (Track.update(liked=0, liked_at=None)
                    .where((Track.liked == 1) & (Track.uri.not_in(list(liked_uris))))
                    .execute())
        except Exception as e:
            self.log.error(f"reconcile_liked: {e}")
            return 0

    def get_liked_track_uris(self):
        """Return list of URIs where liked=1."""
        return [t.uri for t in Track.select(Track.uri).where(Track.liked == 1)]

    # ─── CacheMeta ─────────────────────────────────────────────────────────────

    # Static fallback thresholds when no Spotify total reference is available
    _CACHE_STATIC_MIN = {
        'liked':           20,
        'artists':         10,
        'albums':           5,
        'playlist_tracks': 50,
    }

    def get_cache_meta(self, key):
        """Return (value_int, updated_at) for *key*, or (None, None) if absent."""
        try:
            row = CacheMeta.get_by_id(key)
            return row.value_int, row.updated_at
        except CacheMeta.DoesNotExist:
            return None, None
        except (ValueError, OverflowError):
            # Corrupt updated_at (e.g. MySQL DATETIME int stored in a BIGINT/TimestampField).
            # Reset the row so warmup re-runs cleanly.
            self.set_cache_meta(key, 0)
            return 0, None

    def set_cache_meta(self, key, value_int):
        """Upsert a CacheMeta entry with current timestamp."""
        CacheMeta.insert({
            'key':        key,
            'value_int':  value_int,
            'updated_at': datetime.datetime.utcnow(),
        }).on_conflict_replace().execute()

    # ── Radio France cache (shows + taxonomies) ────────────────────────────

    def upsert_rf_shows(self, rows):
        """Index RF shows for keyword search. Chunked upsert so a re-warmup
        refreshes titles instead of duplicating rows."""
        rows = [r for r in (rows or []) if r.get('rf_id') and r.get('name')]
        if not rows:
            return 0
        now = datetime.datetime.utcnow()
        payload = [{
            'id': r['rf_id'], 'station': r.get('station'), 'title': r['name'],
            'title_norm': _normalize_genre(r['name'])[:255],
            'url': r.get('url') or '', 'standfirst': r.get('standfirst') or '',
            'cached_at': now,
        } for r in rows]
        saved = 0
        for i in range(0, len(payload), 200):
            chunk = payload[i:i + 200]
            try:
                RfShow.insert_many(chunk).on_conflict(
                    action='update',
                    update={RfShow.title: RfShow.title, RfShow.station: RfShow.station},
                    preserve=[RfShow.title, RfShow.title_norm, RfShow.url,
                              RfShow.standfirst, RfShow.station, RfShow.cached_at],
                ).execute()
                saved += len(chunk)
            except Exception as e:
                print(f"upsert_rf_shows error: {e}")
        return saved

    def upsert_rf_taxonomies(self, rows):
        """Index RF themes/tags — the vocabulary behind 'rf:sujet:'."""
        rows = [r for r in (rows or []) if r.get('id') and r.get('title')]
        if not rows:
            return 0
        now = datetime.datetime.utcnow()
        payload = [{
            'id': r['id'], 'kind': (r.get('kind') or '').upper(), 'title': r['title'],
            'title_norm': _normalize_genre(r['title'])[:255], 'cached_at': now,
        } for r in rows]
        saved = 0
        for i in range(0, len(payload), 200):
            chunk = payload[i:i + 200]
            try:
                RfTaxonomy.insert_many(chunk).on_conflict(
                    action='update',
                    update={RfTaxonomy.title: RfTaxonomy.title},
                    preserve=[RfTaxonomy.title, RfTaxonomy.title_norm,
                              RfTaxonomy.kind, RfTaxonomy.cached_at],
                ).execute()
                saved += len(chunk)
            except Exception as e:
                print(f"upsert_rf_taxonomies error: {e}")
        return saved

    def count_rf_shows(self):
        try:
            return RfShow.select(RfShow.id).count()
        except Exception:
            return 0

    def count_rf_taxonomies(self):
        try:
            return RfTaxonomy.select(RfTaxonomy.id).count()
        except Exception:
            return 0

    def search_rf_shows(self, query, limit=15, offset=0):
        """Keyword search over the RF show catalogue, in directory row shape.
        Ordered so OFFSET paging is stable (MySQL OFFSET without ORDER BY is
        undefined and would overlap/skip rows between pages)."""
        q = _normalize_genre(query or '')
        if not q:
            return []
        try:
            rows = (RfShow.select()
                    .where(RfShow.title_norm.contains(q))
                    .order_by(RfShow.title_norm, RfShow.id)
                    .limit(limit).offset(offset))
            out = []
            for s in rows:
                if not s.url:
                    continue
                out.append({'name': s.title, 'uri': 'rf:show:' + s.url,
                            'image': '', 'sub': _RF_STATION_LABELS.get(s.station or '', 'Radio France'),
                            'source': 'radiofrance'})
            return out
        except Exception as e:
            print(f"search_rf_shows error: {e}")
            return []

    def find_rf_taxonomy(self, keyword):
        """Resolve a user keyword to RF taxonomy ids. Accepts a raw id. Exact
        title match first, then 'contains'; THEME wins over TAG (broader)."""
        kw = (keyword or '').strip()
        if not kw:
            return []
        if _re.match(r'^[0-9a-f-]{30,}_\d+$', kw, _re.I):
            return [{'id': kw, 'kind': 'THEME', 'title': kw}]
        n = _normalize_genre(kw)
        try:
            hits = list(RfTaxonomy.select().where(RfTaxonomy.title_norm == n))
            if not hits:
                hits = list(RfTaxonomy.select()
                            .where(RfTaxonomy.title_norm.contains(n))
                            .order_by(fn.CHAR_LENGTH(RfTaxonomy.title_norm))
                            .limit(5))
            hits.sort(key=lambda t: 0 if (t.kind or '').upper() == 'THEME' else 1)
            return [{'id': t.id, 'kind': (t.kind or '').upper(), 'title': t.title} for t in hits]
        except Exception as e:
            print(f"find_rf_taxonomy error: {e}")
            return []

    def list_rf_taxonomies(self, kind=None, query='', limit=200):
        """Subjects for the box-editor selector."""
        try:
            sel = RfTaxonomy.select()
            if kind:
                sel = sel.where(RfTaxonomy.kind == kind.upper())
            q = _normalize_genre(query or '')
            if q:
                sel = sel.where(RfTaxonomy.title_norm.contains(q))
            return [{'id': t.id, 'title': t.title, 'kind': (t.kind or '').upper()}
                    for t in sel.order_by(RfTaxonomy.title_norm).limit(limit)]
        except Exception as e:
            print(f"list_rf_taxonomies error: {e}")
            return []

    def count_cached(self, entity_type):
        """Count locally cached entries for *entity_type*."""
        try:
            if entity_type == 'liked':
                return Track.select().where(Track.liked == 1).count()
            if entity_type == 'artists':
                return Artist.select().where(Artist.followed == 1).count()
            if entity_type == 'albums':
                return Album.select().where(Album.saved == 1).count()
            if entity_type == 'playlist_tracks':
                return PlaylistTrack.select().count()
            if entity_type == 'genres':
                return ArtistGenre.select(ArtistGenre.artist_id).distinct().count()
        except Exception:
            pass
        return 0

    def is_cache_rich(self, entity_type, fill_rate=0.5):
        """True if cached count >= fill_rate * Spotify total (or static min fallback)."""
        count = self.count_cached(entity_type)
        total_ref, _ = self.get_cache_meta(f'total_{entity_type}')
        if total_ref and total_ref > 0:
            return count >= total_ref * fill_rate
        # Static fallback
        return count >= self._CACHE_STATIC_MIN.get(entity_type, 10)

    def is_album_track_cache_fresh(self, album_id):
        """True if AlbumTrack count matches album.total_tracks AND cache is within TTL."""
        try:
            album = Album.get_by_id(album_id)
            cached_count = AlbumTrack.select().where(AlbumTrack.album_id == album_id).count()
            if cached_count == 0:
                return False
            # If we know the total, require a full cache before considering it fresh
            if album.total_tracks and cached_count < album.total_tracks:
                return False
            return self.is_cache_fresh(album.cached_at, 'album_track')
        except Exception:
            return False

    # ─── Stats dashboard ───────────────────────────────────────────────────────

    def get_stats_mood(self):
        """Return mood tag distribution and scatter data for the stats dashboard."""
        try:
            mood_counts = {}
            for row in db.execute_sql(
                "SELECT COALESCE(mood, 'null') AS m, COUNT(*) AS cnt FROM track GROUP BY m"
            ):
                mood_counts[row[0]] = row[1]

            scatter = []
            rows = db.execute_sql(
                """
                SELECT t.energy, t.valence, COALESCE(t.mood, 'unknown') AS mood,
                       t.name, a.name AS artist_name
                FROM track t
                LEFT JOIN trackartist ta ON ta.track_uri = t.uri AND ta.position = 0
                LEFT JOIN artist a ON a.id = ta.artist_id
                WHERE t.energy IS NOT NULL AND t.valence IS NOT NULL
                ORDER BY t.read_count_end DESC
                LIMIT 2000
                """
            )
            for r in rows:
                scatter.append({
                    'energy': r[0],
                    'valence': r[1],
                    'mood': r[2],
                    'name': r[3] or '',
                    'artist': r[4] or '',
                })
            return {'mood_distribution': mood_counts, 'scatter': scatter}
        except Exception as e:
            print(f"get_stats_mood error: {e}")
            return {'mood_distribution': {}, 'scatter': []}

    def get_stats_tracks(self):
        """Return histogram data for read_end, read_count, read_count_end, last_read_date."""
        result = {
            'read_end_hist': [],
            'read_count_hist': [],
            'read_count_end_hist': [],
            'last_read_hist': [],
        }
        try:
            buckets_20 = [i / 20 for i in range(21)]
            read_end_counts = [0] * 20
            for row in db.execute_sql(
                "SELECT read_end FROM track WHERE read_end > 0 AND read_end IS NOT NULL"
            ):
                v = float(row[0])
                idx = min(int(v * 20), 19)
                read_end_counts[idx] += 1
            result['read_end_hist'] = [
                [round(buckets_20[i], 2), round(buckets_20[i + 1], 2), read_end_counts[i]]
                for i in range(20)
            ]
        except Exception as e:
            print(f"get_stats_tracks read_end error: {e}")

        count_buckets = [(0, 5), (5, 10), (10, 20), (20, 50), (50, None)]
        for col, key in [('read_count', 'read_count_hist'), ('read_count_end', 'read_count_end_hist')]:
            try:
                hist = []
                for lo, hi in count_buckets:
                    if hi is None:
                        row = db.execute_sql(
                            f"SELECT COUNT(*) FROM track WHERE {col} >= {lo}"
                        ).fetchone()
                        hist.append([lo, None, row[0]])
                    else:
                        row = db.execute_sql(
                            f"SELECT COUNT(*) FROM track WHERE {col} >= {lo} AND {col} < {hi}"
                        ).fetchone()
                        hist.append([lo, hi, row[0]])
                result[key] = hist
            except Exception as e:
                print(f"get_stats_tracks {col} error: {e}")

        try:
            months = []
            for row in db.execute_sql(
                """
                SELECT DATE_FORMAT(FROM_UNIXTIME(last_read_date), '%%Y-%%m') AS month,
                       COUNT(*) AS cnt
                FROM track
                WHERE last_read_date IS NOT NULL
                  AND last_read_date > UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 12 MONTH))
                GROUP BY month
                ORDER BY month ASC
                """
            ):
                months.append({'month': row[0], 'count': row[1]})
            result['last_read_hist'] = months
        except Exception:
            try:
                months = []
                for row in db.execute_sql(
                    """
                    SELECT strftime('%%Y-%%m', datetime(last_read_date, 'unixepoch')) AS month,
                           COUNT(*) AS cnt
                    FROM track
                    WHERE last_read_date IS NOT NULL
                      AND last_read_date > strftime('%%s', date('now', '-12 months'))
                    GROUP BY month
                    ORDER BY month ASC
                    """
                ):
                    months.append({'month': row[0], 'count': row[1]})
                result['last_read_hist'] = months
            except Exception as e:
                print(f"get_stats_tracks last_read error: {e}")

        return result

    # Map every raw Track.option_type onto a display category bucket.
    # Library-side (real tracks) vs adjacent/new vs sidelined vs media.
    _STATS_CATEGORY_MAP = {
        'library':     'library',
        'normal':      'library',
        'favorites':   'favorites',
        'incoming':    'incoming',
        'new':         'new',
        '':            'new',
        'new_mopidy':  'new',
        'hidden':      'hidden_trash',
        'trash':       'hidden_trash',
        'podcast':     'podcast_info',
        'info':        'podcast_info',
    }
    # Display order of categories in the comparative dashboard.
    _STATS_CATEGORY_ORDER = [
        'library', 'favorites', 'incoming', 'new', 'hidden_trash', 'podcast_info', 'other',
    ]

    def get_stats_breakdown(self):
        """Comparative track stats split by option_type category and by provenance.

        Library-side categories (library/favorites/incoming) hold the tracks really
        kept in the user's albums & playlists; `new` holds the adjacent tracks fed by
        history and album/artist warmups. For every category we expose popularity
        (read_end), play counts (read_count / read_count_end), skips, liked & mood
        fill rates, plus a provenance split (playlist > album > artist > unknown).
        """
        # One pass over `track`, grouped by (option_type, provenance). We aggregate
        # SUM + COUNT (not AVG) so several option_types can be merged into one display
        # bucket with correct weighted averages afterwards. Provenance priority:
        #   playlist (in a PlaylistTrack) > album (album_id set) > artist (TrackArtist) > unknown.
        # CASE / EXISTS are standard SQL → works on both MySQL and SQLite.
        sql = """
            SELECT t.option_type AS otype,
                   CASE
                     WHEN EXISTS (SELECT 1 FROM playlisttrack pt WHERE pt.track_uri = t.uri) THEN 'playlist'
                     WHEN t.album_id IS NOT NULL AND t.album_id <> '' THEN 'album'
                     WHEN EXISTS (SELECT 1 FROM trackartist ta WHERE ta.track_uri = t.uri) THEN 'artist'
                     ELSE 'unknown'
                   END AS prov,
                   COUNT(*)                                                     AS cnt,
                   SUM(t.read_end)                                              AS s_read_end,
                   SUM(t.read_count)                                            AS s_read_count,
                   SUM(t.read_count_end)                                        AS s_read_count_end,
                   SUM(t.skipped_count)                                         AS s_skipped,
                   SUM(CASE WHEN t.liked = 1 THEN 1 ELSE 0 END)                 AS n_liked,
                   SUM(CASE WHEN t.mood IS NOT NULL AND t.mood <> '_' THEN 1 ELSE 0 END) AS n_mood
            FROM track t
            GROUP BY t.option_type, prov
        """

        # Accumulator per category bucket.
        def _blank():
            return {
                'count': 0, 's_read_end': 0.0, 's_read_count': 0, 's_read_count_end': 0,
                's_skipped': 0, 'liked': 0, 'mood_filled': 0,
                'provenance': {'playlist': 0, 'album': 0, 'artist': 0, 'unknown': 0},
            }

        cats = {}
        try:
            for row in db.execute_sql(sql):
                otype, prov, cnt = (row[0] or ''), row[1], int(row[2] or 0)
                cat = self._STATS_CATEGORY_MAP.get(otype, 'other')
                acc = cats.setdefault(cat, _blank())
                acc['count']            += cnt
                acc['s_read_end']       += float(row[3] or 0)
                acc['s_read_count']     += int(row[4] or 0)
                acc['s_read_count_end'] += int(row[5] or 0)
                acc['s_skipped']        += int(row[6] or 0)
                acc['liked']            += int(row[7] or 0)
                acc['mood_filled']      += int(row[8] or 0)
                if prov not in acc['provenance']:
                    prov = 'unknown'
                acc['provenance'][prov] += cnt
        except Exception as e:
            print(f"get_stats_breakdown error: {e}")
            return {'categories': [], 'totals': {}}

        def _finalize(cat, acc):
            n = acc['count'] or 1
            return {
                'category':         cat,
                'count':            acc['count'],
                'avg_read_end':     round(acc['s_read_end'] / n, 3),
                'avg_read_count':   round(acc['s_read_count'] / n, 2),
                'avg_read_count_end': round(acc['s_read_count_end'] / n, 2),
                'avg_skipped':      round(acc['s_skipped'] / n, 2),
                'liked':            acc['liked'],
                'liked_pct':        round(100 * acc['liked'] / n, 1),
                'mood_filled':      acc['mood_filled'],
                'mood_pct':         round(100 * acc['mood_filled'] / n, 1),
                'provenance':       acc['provenance'],
            }

        categories = []
        for cat in self._STATS_CATEGORY_ORDER:
            if cat in cats:
                categories.append(_finalize(cat, cats[cat]))
        # Any unexpected bucket not in the predefined order.
        for cat in cats:
            if cat not in self._STATS_CATEGORY_ORDER:
                categories.append(_finalize(cat, cats[cat]))

        # Grand totals (all tracks combined).
        grand = _blank()
        for acc in cats.values():
            for k in ('count', 's_read_end', 's_read_count', 's_read_count_end',
                      's_skipped', 'liked', 'mood_filled'):
                grand[k] += acc[k]
            for p in grand['provenance']:
                grand['provenance'][p] += acc['provenance'][p]
        totals = _finalize('all', grand)

        return {'categories': categories, 'totals': totals}

    def get_playlist_log(self, limit=100):
        """Recent hard playlist mutations from the dedicated PlaylistLog table.

        Each row is a real add/remove of a track to/from a playlist (or saved
        tracks), recorded by `_log_playlist_change` whenever update_stat_track
        promotes/demotes a track between option_type buckets.
        """
        rows = []
        try:
            cur = db.execute_sql(
                "SELECT event_date, action, from_option_type, to_option_type, "
                "track_name, track_uri, playlist_name, playlist_uri, username "
                "FROM playlistlog ORDER BY event_date DESC LIMIT %d" % int(limit)
            )
            for r in cur:
                rows.append({
                    'event_date':       int(r[0]) if r[0] is not None else None,
                    'action':           r[1],
                    'from_option_type': r[2],
                    'to_option_type':   r[3],
                    'track_name':       r[4],
                    'track_uri':        r[5],
                    'playlist_name':    r[6],
                    'playlist_uri':     r[7],
                    'username':         r[8],
                })
        except Exception as e:
            print(f"get_playlist_log error: {e}")
        return {'log': rows}


if __name__ == "__main__":

    models = generate_models(db)
    print('MODEL TAG')
    print_model(models['box'])

    mydb = DatabaseHandler()

    print('ALL TAGS')
    boxs = mydb.get_all_boxs()
    pprint.pprint(boxs)

    print('creating')
    mydb.create_box('super_uid2', 'super_media')

    print('searching')
    for box in Box.select().where(Box.uid.contains('super')):
        print(box)

        print('removing')
        box.delete_instance() 
    
    print('searching')
    for box in Box.select().where(Box.uid.contains('super')):
        print(box)
    
    # create_tables()