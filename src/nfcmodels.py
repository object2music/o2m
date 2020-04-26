import sys, datetime
from peewee import UUIDField, CharField, IntegerField, TextField, TimestampField, BooleanField, Model, OperationalError, MySQLDatabase
from playhouse.migrate import migrate, MySQLMigrator, SqliteDatabase, SqliteMigrator
from playhouse.shortcuts import ReconnectMixin

sys.path.append('.')
import src.util as util

class ReconnectMySQLDatabase(ReconnectMixin, MySQLDatabase):
    pass

'''
DATABASE INIT 

TODO 
    * Verifier la structure de la base et mettre à jour ou créer le schéma si nécessaire

'''
config_o2m = util.get_config()['o2m']

if 'db_type' in config_o2m:
    db_type = config_o2m['db_type']
    if db_type == 'mysql':
        db_username = config_o2m['db_username']
        db_password = config_o2m['db_password']
        db_host = config_o2m['db_host']
        db_port = config_o2m['db_port']
        db_name = config_o2m['db_name']
        db = ReconnectMySQLDatabase(db_name, host=db_host, user=db_username, password=db_password)
    elif db_type == 'sqlite':
        database_path = config_o2m['db_sqlite_path']
        db = SqliteDatabase(database_path)
    
# Si rien n'est spécifié -> base par défaut 
if db == None:  
    db = SqliteDatabase('data.db')


'''
    MODEL STRUCTURE
'''
class BaseModel(Model):
    class Meta:
        database = db

class Tag(BaseModel):
    uid = CharField(unique=True, index=True, primary_key=True, ) # Unique tag/card/nfc id
    tag_type = CharField(null=True) # album_local, album_spotify etc...
    data = CharField(null=True) # media uri or option
    description = TextField(null=True) # description text
    read_count = IntegerField(default=0) # Increment each time a tag is used
    last_read_date = TimestampField(null=True, utc=True) # timestamp of last used date
    option_new = BooleanField(default=False) # only play new tracks
    option_sort = CharField(null=True) # shuffle, (asc, desc : date of tracks/podcasts)
    option_duration = IntegerField(null=True) # max duration of a media : mostly useful for radios
    option_items_length = IntegerField(null=True) # Podcasts max count to read in podcast channel 

    def __str__(self):
        return 'TAG UID : {} | TYPE : {} | MEDIA : {} | DESCRIPTION : {} | READ COUNT : {}' .format(self.uid, self.tag_type, self.data, self.description, self.read_count)

    def add_count(self):
        if self.read_count != None:
            self.read_count += 1
        else:
            self.read_count = 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()
