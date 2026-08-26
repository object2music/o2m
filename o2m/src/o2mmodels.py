import sys, datetime, json
from peewee import (
    UUIDField,
    AutoField,
    CharField,
    IntegerField,
    TextField,
    TimestampField,
    FloatField,
    BooleanField,
    Model,
    OperationalError,
    MySQLDatabase,
)
from playhouse.migrate import migrate, MySQLMigrator, SqliteDatabase, SqliteMigrator
from playhouse.shortcuts import ReconnectMixin, model_to_dict, dict_to_model

sys.path.append(".")
import src.util as util


class ReconnectMySQLDatabase(ReconnectMixin, MySQLDatabase):
    pass


"""
DATABASE INIT
TODO 
    * Verifier la structure de la base et mettre à jour ou créer le schéma si nécessaire

"""
config_o2m = util.get_config_file("o2m.conf")["o2m"]

if "db_type" in config_o2m:
    db_type = config_o2m["db_type"]
    if db_type == "mysql":
        db_username = config_o2m["db_username"]
        db_password = config_o2m["db_password"]
        db_host = config_o2m["db_host"]
        db_port = int(config_o2m["db_port"])
        db_name = config_o2m["db_name"]
        db = ReconnectMySQLDatabase(
            db_name, host=db_host, user=db_username, password=db_password, port=db_port
        )
    elif db_type == "sqlite":
        database_path = config_o2m["db_sqlite_path"]
        db = SqliteDatabase(database_path)

# Si rien n'est spécifié -> base par défaut
if db == None:
    db = SqliteDatabase("data.db")


"""
    MODEL STRUCTURE
"""


class BaseModel(Model):
    class Meta:
        database = db

class Box(BaseModel):
    uid = CharField(
        unique=True,
        index=True,
        primary_key=True,
    )  # Unique nfc or box id
    user = TextField(null=True)  # user text
    data = TextField(null=True)  # media uri or option
    data_alt = TextField(null=True)  # media uri or option
    description = TextField(null=True)  # description text
    read_count = IntegerField(default=0)  # Increment each time a tag is used
    last_read_date = TimestampField(null=True, utc=True)  # timestamp of last used date
    option_type = CharField(default='library')  # option card type : library (default), new (discover card:only play new tracks), favorites (preferred tracks), hidden (not considered by stats)
    option_sort = CharField(null=True)  # shuffle, (asc, desc : date of tracks/podcasts)
    option_duration = IntegerField(null=True)  # max duration of a media : mostly useful for radios
    option_max_results = IntegerField(null=True)  # Max results associated to tag
    option_discover_level = IntegerField(default=5)  # Discover level (0-10) associated to tag
    option_energy = FloatField(null=True)   # Target energy 0.0-1.0 (NULL = inherit global mood context)
    option_valence = FloatField(null=True)  # Target valence/ambiance 0.0-1.0 (NULL = inherit global mood context)
    favorite= IntegerField(default=0) #Bool (is the box pinned or not)
    public= IntegerField(default=0) #Bool (is the content shared or not)
    image_url = TextField(null=True)  # optional cover/thumbnail URL for the box

    '''def __str__(self):
        #return "TAG UID : {} | MEDIA : {} | DESCRIPTION : {} | READ COUNT : {}| OPTION_TYPE : {}".format(self.uid, self.data, self.description, self.read_count, self.option_type)
        json_data = "{uid : "+self.uid+" , media : "+self.data+", description : "+self.description+" , read_count : "+self.read_count+" , option_type : "+self.option_type+" }"
        #json_data = json.dumps(model_to_dict(user_obj))
        json_data = json.dumps(json_data)
        return json_data'''
    
    def add_count(self):
        if self.read_count != None:
            self.read_count += 1
        else:
            self.read_count = 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()


class Track(BaseModel):
    uri = CharField(unique=True, index=True, primary_key=True)  # Unique uri
    last_read_date = TimestampField(null=True, utc=True)  # date
    read_position = IntegerField(default=0)  # description text
    read_end = FloatField(default=0.5)  # Rate average
    read_count = IntegerField(default=0)  # int
    read_count_end = IntegerField(default=0)  # int
    skipped_count = IntegerField(default=0)  # int
    in_library = TextField(default='')  # Uri track if exist
    day_time_average = IntegerField(default=0)  # int
    option_type = CharField(default='new')  # option card type : normal (default), new (discover card:only play new tracks), favorites (preferred tracks), hidden (not considered by stats)
    username = TextField(null=True)  # user text
    # Cache Spotify metadata
    name = TextField(null=True)          # track title
    duration_ms = IntegerField(null=True)
    track_number = IntegerField(null=True)
    album_id = CharField(null=True, index=True)  # → Album.id
    preview_url = TextField(null=True)
    cached_at = TimestampField(null=True, utc=True)
    storage = CharField(default='sp')    # 'sp' or 'local'
    liked = IntegerField(default=0)      # 1 = in liked tracks
    liked_at = TimestampField(null=True, utc=True)
    local_uri = TextField(null=True)     # file:// URI if downloaded via spotdl
    mood = TextField(null=True)          # Last.fm mood: calm/energetic/dark/happy
    energy = FloatField(null=True)       # 0.0 (calm/sleep) → 1.0 (intense/metal)
    valence = FloatField(null=True)      # 0.0 (dark/sad) → 1.0 (joyful/euphoric)
    popularity = FloatField(null=True)   # composite popularity score [0,1], recomputed in batch (stats_v2)
    mood_edited_at = TimestampField(null=True, utc=True)  # set on MANUAL mood/energy/valence edit → locks the track against warmup overwrite
    published_at = CharField(null=True)  # episode publication date 'YYYY-MM-DD' (spoken content; feed/API formats vary)
    channel_id = CharField(null=True, index=True)  # → PodcastChannel.id (spoken content; one episode has exactly one channel)

    def __str__(self):
        return "URI : {} | LAST READ : {} | READ COUNT END : {}| SKIP COUNT : {} | READ POSITION : {} | READ END : {}| OPTION_TYPE : {}".format(
            self.uri,
            self.last_read_date,
            self.read_count_end,
            self.skipped_count,
            self.read_position,
            self.read_end,
            self.option_type
        )

    """def add_count(self):
        if self.read_count != None:
            self.read_count += 1
        else:
            self.read_count = 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()"""


class Stats_Raw(BaseModel):
    # The physical primary key is the auto-increment `Id` column (see SHOW CREATE
    # TABLE); read_date is a plain indexed timestamp, NOT the PK. Declaring read_date
    # primary_key=True here misled the ORM (a second-resolution "PK" that isn't unique
    # in the DB). Map the real PK so .save()/get_by_id behave correctly.
    id = AutoField()
    read_date = TimestampField(
        index=True, null=True, utc=True
    )  # date
    uri = CharField(default=0)
    read_hour = IntegerField(default=0)  # int
    username = TextField(null=True)  # user text

    def __str__(self):
        return "URI : {} | LAST READ : {} | READ Hur : {}".format(
            self.uri, self.read_date, self.read_hour
        )


class PlaylistLog(BaseModel):
    """Audit log of playlist add/remove operations triggered by update_stat_track."""
    id = AutoField()
    event_date = TimestampField(utc=True)
    track_uri = CharField(index=True)
    track_name = TextField(null=True)
    playlist_uri = CharField()
    playlist_name = TextField(null=True)
    action = CharField()            # 'add' or 'remove'
    from_option_type = CharField(null=True)
    to_option_type = CharField(null=True)
    username = TextField(null=True)


# ─── Spotify local cache ───────────────────────────────────────────────────────

class Album(BaseModel):
    id = CharField(unique=True, index=True, primary_key=True)  # Spotify album ID
    uri = CharField(null=True)
    name = TextField(null=True)
    artist_name = TextField(null=True)  # denormalized main artist name
    album_type = CharField(null=True)   # album / single / compilation
    release_date = CharField(null=True) # kept as string (Spotify format varies)
    total_tracks = IntegerField(null=True)
    image_url = TextField(null=True)
    storage = CharField(default='sp')   # 'sp' or 'local'
    cached_at = TimestampField(null=True, utc=True)
    saved = IntegerField(default=0)     # 1 = in user's saved albums
    saved_at = TimestampField(null=True, utc=True)


class Artist(BaseModel):
    id = CharField(unique=True, index=True, primary_key=True)  # Spotify artist ID
    uri = CharField(null=True)
    name = TextField(null=True)
    popularity = IntegerField(null=True)
    followers = IntegerField(null=True)
    image_url = TextField(null=True)
    storage = CharField(default='sp')   # 'sp' or 'local'
    cached_at = TimestampField(null=True, utc=True)
    followed = IntegerField(default=0)  # 1 = user follows this artist
    followed_at = TimestampField(null=True, utc=True)


class Genre(BaseModel):
    id = AutoField()
    name = CharField(unique=True, index=True)


# ─── Join tables ───────────────────────────────────────────────────────────────

class TrackArtist(BaseModel):
    """N:N  track.uri ↔ artist.id"""
    track_uri = CharField(index=True)   # → Track.uri
    artist_id = CharField(index=True)   # → Artist.id
    position = IntegerField(default=0)  # 0 = main artist

    class Meta:
        indexes = ((('track_uri', 'artist_id'), True),)


class AlbumArtist(BaseModel):
    """N:N  album.id ↔ artist.id"""
    album_id = CharField(index=True)    # → Album.id
    artist_id = CharField(index=True)   # → Artist.id
    position = IntegerField(default=0)

    class Meta:
        indexes = ((('album_id', 'artist_id'), True),)


class ArtistGenre(BaseModel):
    """N:N  artist.id ↔ genre.id"""
    artist_id = CharField(index=True)   # → Artist.id
    genre_id = IntegerField(index=True) # → Genre.id

    class Meta:
        indexes = ((('artist_id', 'genre_id'), True),)


class TrackGenre(BaseModel):
    """N:N  track.uri ↔ genre.id — persists Last.fm track.getTopTags with weight."""
    track_uri = CharField(index=True)   # → Track.uri
    genre_id  = IntegerField(index=True) # → Genre.id
    weight    = IntegerField(default=0)  # Last.fm count

    class Meta:
        indexes = ((('track_uri', 'genre_id'), True),)


class AlbumGenre(BaseModel):
    """N:N  album.id ↔ genre.id — persists Last.fm album.getTopTags with weight."""
    album_id = CharField(index=True)    # → Album.id
    genre_id = IntegerField(index=True) # → Genre.id
    weight   = IntegerField(default=0)  # Last.fm count

    class Meta:
        indexes = ((('album_id', 'genre_id'), True),)


class TagFeature(BaseModel):
    """Data-driven tag → (energy, valence, mood) mapping. Replaces hardcoded dicts.
    Seeded at startup from SpotifyHandler class constants, then editable via UI."""
    tag      = CharField(primary_key=True, max_length=100)  # normalized tag name
    energy   = FloatField(null=True)    # 0.0–1.0
    valence  = FloatField(null=True)    # 0.0–1.0
    mood     = CharField(null=True, max_length=20)   # calm / energetic / dark / happy
    is_noise = IntegerField(default=0)  # 1 = filter this tag from scoring


class Playlist(BaseModel):
    id = CharField(unique=True, index=True, primary_key=True)  # Spotify playlist ID
    uri = CharField(null=True)
    name = TextField(null=True)
    description = TextField(null=True)
    owner_id = CharField(null=True)
    total_tracks = IntegerField(null=True)
    snapshot_id = CharField(null=True)  # used to detect playlist changes
    image_url = TextField(null=True)
    storage = CharField(default='sp')   # 'sp' or 'local'
    cached_at = TimestampField(null=True, utc=True)
    # False once the playlist has left the account's library. Spotify keeps a removed
    # playlist alive (and fetchable by id) for ~90 days, so its absence from the listing
    # is not a deletion: we stop drawing from it instead of erasing what we know of it.
    # NULL = never assessed, treated as in-library.
    in_library = BooleanField(null=True, default=True)


class PlaylistTrack(BaseModel):
    """N:N  playlist.id ↔ track.uri"""
    playlist_id = CharField(index=True)  # → Playlist.id
    track_uri = CharField(index=True)    # → Track.uri
    position = IntegerField(default=0)
    added_at = TimestampField(null=True, utc=True)

    class Meta:
        indexes = ((('playlist_id', 'track_uri'), True),)


class AlbumTrack(BaseModel):
    """N:N  album.id ↔ track.uri — ordered tracklist cache"""
    album_id = CharField(index=True)   # → Album.id
    track_uri = CharField(index=True)  # → Track.uri
    position = IntegerField(default=0)

    class Meta:
        indexes = ((('album_id', 'track_uri'), True),)


class CacheMeta(BaseModel):
    """Key/value store for cache health metrics and schema versioning.
    Reserved key: 'schema_version' (value_int = current schema version).
    Cache keys: total_liked, total_artists, total_albums, total_playlists
                warmup_liked_at, warmup_artists_at, warmup_albums_at, warmup_playlist_tracks_at
    """
    key = CharField(unique=True, index=True, primary_key=True)
    value_int = IntegerField(null=True)
    updated_at = TimestampField(null=True, utc=True)


class RfShow(BaseModel):
    """Radio France show catalogue (OpenAPI `shows`) — the keyword index that
    makes an RF podcast findable BEFORE it has ever been played. The keyless
    directories o2m searches (fyyd) index almost no Radio France, so without
    this a show like "L'Invite(e) des Matins" simply never came up.

    RF's `Show.podcast { rss }` is broken server-side, so a show is referenced
    by its page URL ('rf:show:<url>') and expanded through the API, not as a
    'podcast+<feed>' line.
    """
    id         = CharField(primary_key=True)        # RF show uuid ("<uuid>_<n>")
    station    = CharField(null=True, index=True)   # StationsEnum value
    title      = TextField(null=True)
    # CharField, not TextField: MySQL refuses an index on TEXT without a prefix
    # length, and this column exists only to be searched.
    title_norm = CharField(null=True, index=True)   # accent/case folded
    url        = TextField(null=True)               # page url -> episodes
    standfirst = TextField(null=True)
    cached_at  = TimestampField(null=True, utc=True)


class RfTaxonomy(BaseModel):
    """Radio France themes/tags (OpenAPI `taxonomies`) — the vocabulary behind
    the dynamic 'rf:sujet:<keyword>' box. `diffusions` filters take taxonomy
    IDs, never paths, so the id is the payload — but the path's DEPTH decides
    WHICH argument the id belongs to (themes / subthemes / subsubthemes), so it
    is stored too. Only themes carry one: for some tags it is null and the API
    raises on the field, so it is requested for THEME queries only.
    """
    id         = CharField(primary_key=True)        # "<uuid>_0"
    kind       = CharField(null=True, index=True)   # THEME | TAG
    title      = TextField(null=True)
    title_norm = CharField(null=True, index=True)
    path       = TextField(null=True)               # 'arts-divertissements/cinema'
    cached_at  = TimestampField(null=True, utc=True)


class PodcastChannel(BaseModel):
    """A podcast source: an RSS feed or a Radio France show.

    Episodes themselves stay in `Track` — that table is already a catalogue +
    stats hybrid (most of its rows have never been played) and it is what the
    lifecycle, the resume pool and the search buckets already read. What was
    missing is the SOURCE they belong to: an RSS episode carries its feed in its
    own uri, but a Radio France episode is a bare mp3 link that says nothing
    about its show — hence Track.channel_id.
    """
    id         = CharField(primary_key=True)        # feed url (rss) or RF show id
    kind       = CharField(null=True, index=True)   # 'rss' | 'rf'
    title      = TextField(null=True)
    title_norm = CharField(null=True, index=True)
    url        = TextField(null=True)               # feed url, or the RF show page
    station    = CharField(null=True)
    image_url  = TextField(null=True)
    cached_at  = TimestampField(null=True, utc=True)


class EpisodeTaxonomy(BaseModel):
    """Episode ↔ Radio France subject. Many-to-many on purpose: one episode
    routinely carries several themes AND tags, so a column on Track could not
    express it — this is what lets 'rf:sujet:<subject>' be answered from the DB
    instead of re-querying the API on every box activation."""
    track_uri   = CharField(index=True)
    taxonomy_id = CharField(index=True)

    class Meta:
        primary_key = False
        indexes = ((('track_uri', 'taxonomy_id'), True),)


# ─── Database versioning ───────────────────────────────────────────────────────
#
# SCHEMA_VERSION is the target version.  setup_database() applies every
# migration whose version number is above the stored 'schema_version' key.
# Each migration function must be fully idempotent (IF NOT EXISTS / try-except).
#
# To add a new migration:
#   1. Write  _migration_vN(migrator)
#   2. Append (N, "short_description", _migration_vN)  to  _MIGRATIONS
#   3. Bump   SCHEMA_VERSION = N

def _get_schema_version():
    try:
        row = CacheMeta.get_by_id('schema_version')
        return row.value_int or 0
    except Exception:
        return 0


def _set_schema_version(version):
    CacheMeta.insert({
        'key':        'schema_version',
        'value_int':  version,
        'updated_at': datetime.datetime.utcnow(),
    }).on_conflict_replace().execute()


def _add_column_safe(migrator, table, column, field):
    """Add a column to *table* only if it does not already exist."""
    try:
        migrate(migrator.add_column(table, column, field))
    except Exception:
        pass  # column already exists


# ── Migration v1 ───────────────────────────────────────────────────────────────
# Adds all Spotify cache tables and new columns on track / artist / album.
# Corresponds to the state documented in dump.sql as of 2026-04-26.

def _migration_v1(migrator):
    db.create_tables([
        Album, Artist, Genre, TrackArtist, AlbumArtist, ArtistGenre,
        Playlist, PlaylistTrack, AlbumTrack,
    ], safe=True)

    for col, field in [
        ('name',         TextField(null=True)),
        ('duration_ms',  IntegerField(null=True)),
        ('track_number', IntegerField(null=True)),
        ('album_id',     CharField(null=True, index=True)),
        ('preview_url',  TextField(null=True)),
        ('cached_at',    TimestampField(null=True, utc=True)),
        ('storage',      CharField(default='sp')),
        ('liked',        IntegerField(default=0)),
        ('liked_at',     TimestampField(null=True, utc=True)),
    ]:
        _add_column_safe(migrator, 'track', col, field)

    for col, field in [
        ('followed',    IntegerField(default=0)),
        ('followed_at', TimestampField(null=True, utc=True)),
    ]:
        _add_column_safe(migrator, 'artist', col, field)

    for col, field in [
        ('saved',    IntegerField(default=0)),
        ('saved_at', TimestampField(null=True, utc=True)),
    ]:
        _add_column_safe(migrator, 'album', col, field)


def _migration_v2(migrator):
    _add_column_safe(migrator, 'track', 'local_uri', TextField(null=True))


def _migration_v3(migrator):
    # Remove duplicate (album_id, track_uri) rows keeping the earliest inserted row
    try:
        db.execute_sql("""
            DELETE FROM albumtrack
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT MIN(id) AS id
                    FROM albumtrack
                    GROUP BY album_id, track_uri
                ) AS tmp
            )
        """)
    except Exception as e:
        print(f"migration_v3 AlbumTrack dedup: {e}")
    # Ensure unique index exists (no-op if already present)
    try:
        migrate(migrator.add_index('albumtrack', ('album_id', 'track_uri'), unique=True))
    except Exception:
        pass  # index already exists


def _migration_v4(migrator):
    db.create_tables([PlaylistLog], safe=True)


def _migration_v5(migrator):
    _add_column_safe(migrator, 'track', 'mood', TextField(null=True))


def _migration_v6(migrator):
    _add_column_safe(migrator, 'track', 'energy', FloatField(null=True))
    _add_column_safe(migrator, 'track', 'valence', FloatField(null=True))
    # Backfill approximate energy/valence from existing categorical mood
    try:
        db.execute_sql("""
            UPDATE track SET
                energy = CASE mood
                    WHEN 'calm'      THEN 0.2
                    WHEN 'energetic' THEN 0.8
                    WHEN 'dark'      THEN 0.3
                    WHEN 'happy'     THEN 0.6
                    ELSE NULL
                END,
                valence = CASE mood
                    WHEN 'calm'      THEN 0.6
                    WHEN 'energetic' THEN 0.7
                    WHEN 'dark'      THEN 0.2
                    WHEN 'happy'     THEN 0.9
                    ELSE NULL
                END
            WHERE mood IS NOT NULL
        """)
    except Exception as e:
        print(f"migration_v6 backfill: {e}")


def _migration_v7(migrator):
    db.create_tables([TrackGenre, AlbumGenre], safe=True)


def _migration_v8(migrator):
    db.create_tables([TagFeature], safe=True)


def _migration_v9(migrator):
    _add_column_safe(migrator, 'box', 'option_energy', FloatField(null=True))
    _add_column_safe(migrator, 'box', 'option_valence', FloatField(null=True))


def _migration_v10(migrator):
    # Rename the 'normal' option_type value to 'library' (clearer) on existing rows
    for table in ('box', 'track'):
        try:
            db.execute_sql(f"UPDATE {table} SET option_type='library' WHERE option_type='normal'")
        except Exception as e:
            print(f"migration_v10 {table}: {e}")


def _migration_v11(migrator):
    _add_column_safe(migrator, 'track', 'popularity', FloatField(null=True))


def _migration_v12(migrator):
    _add_column_safe(migrator, 'track', 'mood_edited_at', TimestampField(null=True, utc=True))


def _migration_v13(migrator):
    _add_column_safe(migrator, 'box', 'image_url', TextField(null=True))


def _migration_v18(migrator):
    db.create_tables([PodcastChannel, EpisodeTaxonomy], safe=True)
    _add_column_safe(migrator, 'track', 'channel_id', CharField(null=True))


def _migration_v17(migrator):
    _add_column_safe(migrator, 'track', 'published_at', CharField(null=True))


def _migration_v16(migrator):
    _add_column_safe(migrator, 'rftaxonomy', 'path', TextField(null=True))


def _migration_v15(migrator):
    db.create_tables([RfShow, RfTaxonomy], safe=True)


def _migration_v14(migrator):
    _add_column_safe(migrator, 'playlist', 'in_library', BooleanField(null=True, default=True))


SCHEMA_VERSION = 18

_MIGRATIONS = [
    (1, "cache_tables_and_columns", _migration_v1),
    (2, "track_local_uri", _migration_v2),
    (3, "albumtrack_dedup_unique_index", _migration_v3),
    (4, "playlist_log_table", _migration_v4),
    (5, "track_mood_column", _migration_v5),
    (6, "track_energy_valence_columns", _migration_v6),
    (7, "track_album_genre_tables", _migration_v7),
    (8, "tagfeature_table", _migration_v8),
    (9, "box_energy_valence_options", _migration_v9),
    (10, "option_type_normal_to_library", _migration_v10),
    (11, "track_popularity_column", _migration_v11),
    (12, "track_mood_edited_at_column", _migration_v12),
    (13, "box_image_url_column", _migration_v13),
    (14, "playlist_in_library_column", _migration_v14),
    (15, "radiofrance_show_taxonomy_tables", _migration_v15),
    (16, "rftaxonomy_path_column", _migration_v16),
    (17, "track_published_at_column", _migration_v17),
    (18, "podcast_channel_episode_taxonomy", _migration_v18),
]


def setup_database():
    """Create base tables, then apply all pending schema migrations.
    Safe to call at every startup — all operations are idempotent."""

    # Bootstrap: base tables + CacheMeta must exist before we can read the version
    db.create_tables([Box, Track, Stats_Raw, CacheMeta], safe=True)

    migrator = SqliteMigrator(db) if isinstance(db, SqliteDatabase) else MySQLMigrator(db)
    current = _get_schema_version()

    for version, name, fn in _MIGRATIONS:
        if version > current:
            print(f"[DB] applying migration v{version}: {name}")
            fn(migrator)
            _set_schema_version(version)
            print(f"[DB] schema version is now v{version}")

    if current >= SCHEMA_VERSION:
        print(f"[DB] schema up to date (v{SCHEMA_VERSION})")
