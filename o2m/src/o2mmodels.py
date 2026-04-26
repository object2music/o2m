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
    option_type = CharField(default='normal')  # option card type : normal (default), new (discover card:only play new tracks), favorites (preferred tracks), hidden (not considered by stats)
    option_sort = CharField(null=True)  # shuffle, (asc, desc : date of tracks/podcasts)
    option_duration = IntegerField(null=True)  # max duration of a media : mostly useful for radios
    option_max_results = IntegerField(null=True)  # Max results associated to tag
    option_discover_level = IntegerField(default=5)  # Discover level (0-10) associated to tag
    favorite= IntegerField(default=0) #Bool (is the box pinned or not)	
    public= IntegerField(default=0) #Bool (is the content shared or not)

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
    read_date = TimestampField(
        index=True, null=True, utc=True, primary_key=True
    )  # date # Unique uri
    uri = CharField(default=0)
    read_hour = IntegerField(default=0)  # int
    username = TextField(null=True)  # user text

    def __str__(self):
        return "URI : {} | LAST READ : {} | READ Hur : {}".format(
            self.uri, self.read_date, self.read_hour
        )


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

SCHEMA_VERSION = 1


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


_MIGRATIONS = [
    (1, "cache_tables_and_columns", _migration_v1),
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
