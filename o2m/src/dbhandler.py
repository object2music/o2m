import logging, pprint, datetime, random, json

from peewee import IntegrityError, fn, JOIN
from playhouse.migrate import SqliteDatabase, SqliteMigrator
from playhouse.reflection import generate_models, print_model
from playhouse.shortcuts import model_to_dict, dict_to_model


from src.o2mmodels import (
    Box, Track, Stats_Raw, PlaylistLog, db,
    Album, Artist, Genre, TrackArtist, AlbumArtist, ArtistGenre,
    Playlist, PlaylistTrack, AlbumTrack, CacheMeta,
    setup_database,
)
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
        if "http://" in uri:
            uri = uri.replace("http://", "https://")
        if "?max_results=" in uri : 
            uri1 = uri.split("?max_results=")
            if "#" in uri1[1]: 
                uri2 = uri1[1].split("#")
                track_uri = str(uri1[0]) + "#" + str(uri2[1])
            else : track_uri = str(uri1[0])
            return track_uri
        else: return uri

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
        try:
            stat = Track.create(uri=uri)
            return stat
        except IntegrityError as err:
            self.log.error(err)
    
    def get_all_stats(self):
        query = Track.select()
        return self.transform_query_to_list(query)
    
    def get_stat_by_uri(self, uri):
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
        if len(Track.select().where(Track.uri == uri)) > 0:
            return True
        else:
            return False

    def get_avg_stat(self, option_type='', column='read_end'):
        if option_type != '':
            query = Track.select(fn.AVG(getattr(Track, column))).where(Track.option_type == option_type).scalar()
        else:
            query = Track.select(fn.AVG(getattr(Track, column))).scalar()
        #results = self.transform_query_to_list(query)
        return query

    #STATS_RAW
    def clear_lasthour_stats_raw(self):
        one_hour_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        deleted = Stats_Raw.delete().where(Stats_Raw.read_date >= one_hour_ago).execute()
        print(f"clear_lasthour_stats_raw: {deleted} rows deleted")
        return deleted

    def create_stat_raw(self, uri, read_time, read_hour, username):
        stat_raw = Stats_Raw.create(uri=uri,read_time=read_time,read_hour=read_hour,username=username)
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
        if window > 0:
            query = Stats_Raw.select().where((Stats_Raw.read_hour.between(read_hour - window, read_hour + window))&(Stats_Raw.uri.contains(uri_pattern))).order_by(fn.Rand()).limit(limit)
        else:
            query = Stats_Raw.select().where((Stats_Raw.read_hour == read_hour)&(Stats_Raw.uri.contains(uri_pattern))).order_by(fn.Rand()).limit(limit)
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
        """Spotify tracks cached recently (last N days) that have never been played.

        Source: tracks populated by warmup (albums, playlists, artists) that haven't
        been played yet, or queued but play never counted (read_count still 0).
        Podcasts are excluded implicitly by the spotify:track URI filter.
        """
        date_now = datetime.datetime.utcnow().timestamp()
        cutoff = date_now - (days * 86400)
        query = Track.select().where(
            (Track.uri % '%spotify:track%')
            & (Track.cached_at >= cutoff)
            & (Track.read_count == 0)
            & (Track.skipped_count == 0)
        ).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        if results:
            uris = [o.uri for o in results]
            print(f"newrecent:library {len(uris)} unplayed tracks cached in last {days}d")
            return uris
        return []

    def get_uris_podcasts_notread(self, limit=15, discover_level=5):
        #Track unfinished
        #pattern="%podcast+%"
        date_now = datetime.datetime.utcnow().timestamp()
        #query = Track.select().where( ((Track.uri % '%podcast+%') | (Track.uri % '%youtube:video%')| (Track.uri % '%yt:%'))& (Track.read_end <= 0.9)& (Track.read_position > 30000)& (Track.option_type != "info")& (Track.option_type != "normal")).order_by(Track.last_read_date.desc()).limit(limit)
        #query = Track.select().where( ((Track.uri % '%podcast+%') | (Track.uri % '%youtube:video%')| (Track.uri % '%yt:%'))
        query = Track.select().where( ((Track.uri % '%podcast+%')| (Track.uri % '%youtube:video%')| (Track.uri % '%yt:%'))& (Track.read_end < 0.9)& (Track.read_position > 0)& (Track.read_count_end == 0)
            & (
            #((Track.option_type != "info")& (Track.option_type != "normal")& (Track.read_count_end <= discover_level/2) & (Track.skipped_count <= discover_level))
            ((Track.option_type != "normal")& (Track.read_count_end <= discover_level/2) & (Track.skipped_count <= discover_level))
            |((Track.option_type == "podcast")& (Track.read_count_end <= discover_level/2) & (Track.skipped_count <= discover_level*2)) 
            )).order_by(Track.last_read_date.desc()).limit(limit)
        results = self.transform_query_to_list(query)
        print (results)
        if len(results) > 0:
            #uris = [o.uri for o in results]
            uris = []
            for o in results:
                #uris.append(self.podcast_uri_remove_max_results(o.uri))
                uris.append(o.uri)
            return uris

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

    def get_followed_artist_ids(self):
        """Return list of artist IDs where followed=1."""
        return [a.id for a in Artist.select(Artist.id).where(Artist.followed == 1)]

    def save_artist_genres(self, artist_id, genres):
        """Upsert genre list and link them to *artist_id*."""
        for genre_name in genres:
            genre, _ = Genre.get_or_create(name=genre_name)
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

    def get_tracks_without_mood(self, limit=50):
        """Return [(uri, track_name, artist_name, album_name), ...] for tracks that have a name
        but no mood yet (mood IS NULL), ordered by most-listened first.
        Tracks marked mood='_' (no Last.fm data found) are excluded."""
        try:
            rows = (
                Track.select(Track.uri, Track.name, Artist.name.alias('artist_name'),
                             Album.name.alias('album_name'))
                .join(TrackArtist, on=(Track.uri == TrackArtist.track_uri))
                .join(Artist, on=(TrackArtist.artist_id == Artist.id))
                .switch(Track)
                .join(Album, JOIN.LEFT_OUTER, on=(Track.album_id == Album.id))
                .where(
                    Track.mood.is_null() &
                    Track.name.is_null(False) &
                    Artist.name.is_null(False) &
                    (TrackArtist.position == 0)
                )
                .order_by(Track.read_count_end.desc())
                .limit(limit)
                .namedtuples()
            )
            return [(r.uri, r.name, r.artist_name, getattr(r, 'album_name', None)) for r in rows]
        except Exception as e:
            print(f"get_tracks_without_mood error: {e}")
            return []

    def count_tracks_without_mood(self):
        """Return count of tracks with no mood data (NULL only, excludes '_' sentinel).
        Uses the same joins/filters as get_tracks_without_mood for consistency."""
        try:
            return (
                Track.select()
                .join(TrackArtist, on=(Track.uri == TrackArtist.track_uri))
                .join(Artist, on=(TrackArtist.artist_id == Artist.id))
                .where(
                    Track.mood.is_null() &
                    Track.name.is_null(False) &
                    Artist.name.is_null(False) &
                    (TrackArtist.position == 0)
                )
                .count()
            )
        except Exception as e:
            print(f"count_tracks_without_mood error: {e}")
            return -1

    def get_sentinel_tracks_with_artist_genres(self, limit=50):
        """Return [(uri, track_name, artist_name, album_name)] for tracks with mood='_' (sentinel)
        whose primary artist now has genres in ArtistGenre — eligible for a retry."""
        try:
            rows = (
                Track.select(Track.uri, Track.name, Artist.name.alias('artist_name'),
                             Album.name.alias('album_name'))
                .join(TrackArtist, on=(Track.uri == TrackArtist.track_uri))
                .join(Artist, on=(TrackArtist.artist_id == Artist.id))
                .join(ArtistGenre, on=(ArtistGenre.artist_id == Artist.id))
                .switch(Track)
                .join(Album, JOIN.LEFT_OUTER, on=(Track.album_id == Album.id))
                .where(
                    (Track.mood == '_') &
                    Track.name.is_null(False) &
                    Artist.name.is_null(False) &
                    (TrackArtist.position == 0)
                )
                .order_by(Track.read_count_end.desc())
                .limit(limit)
                .namedtuples()
            )
            return [(r.uri, r.name, r.artist_name, getattr(r, 'album_name', None)) for r in rows]
        except Exception as e:
            print(f"get_sentinel_tracks_with_artist_genres error: {e}")
            return []

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
            Track.update(updates).where(Track.uri == uri).execute()

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
        update_fields = {k: v for k, v in row.items() if k != 'id'}
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

    def get_saved_album_ids(self):
        """Return list of album IDs where saved=1."""
        return [a.id for a in Album.select(Album.id).where(Album.saved == 1)]

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

        # Upsert: create stat row if not present, update metadata fields otherwise
        Track.insert({**updates, 'uri': uri}).on_conflict(
            action='update',
            update=updates,
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

    def get_all_cached_playlist_ids(self):
        """Return IDs of all playlists that have at least one cached track."""
        rows = (PlaylistTrack.select(PlaylistTrack.playlist_id)
                .group_by(PlaylistTrack.playlist_id))
        return [r.playlist_id for r in rows]

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