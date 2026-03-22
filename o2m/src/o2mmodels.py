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


class Artist(BaseModel):
    id = CharField(unique=True, index=True, primary_key=True)  # Spotify artist ID
    uri = CharField(null=True)
    name = TextField(null=True)
    popularity = IntegerField(null=True)
    followers = IntegerField(null=True)
    image_url = TextField(null=True)
    storage = CharField(default='sp')   # 'sp' or 'local'
    cached_at = TimestampField(null=True, utc=True)


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


# ─── Database setup / migration ────────────────────────────────────────────────

NEW_TABLES = [Album, Artist, Genre, TrackArtist, AlbumArtist, ArtistGenre,
              Playlist, PlaylistTrack]

# New columns added to the existing track table
_STATS_NEW_COLUMNS = [
    ('name',         TextField(null=True)),
    ('duration_ms',  IntegerField(null=True)),
    ('track_number', IntegerField(null=True)),
    ('album_id',     CharField(null=True, index=True)),
    ('preview_url',  TextField(null=True)),
    ('cached_at',    TimestampField(null=True, utc=True)),
    ('storage',      CharField(default='sp')),
    ('liked',        IntegerField(default=0)),   # 1 = in liked tracks
    ('liked_at',     TimestampField(null=True, utc=True)),
]


def _add_column_safe(migrator, table, column, field):
    """Add a column to *table* only if it does not already exist."""
    try:
        migrate(migrator.add_column(table, column, field))
    except Exception:
        pass  # column already exists


def setup_database():
    """Create new tables and migrate existing ones.  Safe to call at every startup."""
    # Create new tables (IF NOT EXISTS)
    db.create_tables(NEW_TABLES, safe=True)

    # Migrate track: add new columns when missing
    if isinstance(db, SqliteDatabase):
        migrator = SqliteMigrator(db)
    else:
        migrator = MySQLMigrator(db)

    for col_name, field in _STATS_NEW_COLUMNS:
        _add_column_safe(migrator, 'track', col_name, field)
