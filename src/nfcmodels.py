import sys, datetime
from peewee import UUIDField, CharField, IntegerField, TextField, TimestampField, BooleanField, Model, OperationalError
from playhouse.migrate import migrate, MySQLMigrator, SqliteDatabase, SqliteMigrator
from playhouse.db_url import connect
from playhouse.pool import PooledMySQLDatabase

from playhouse.mysql_ext import MySQLConnectorDatabase

sys.path.append('.')
import src.util as util

'''
DATABASE INIT 
'''
config_o2m = util.get_config()['o2m']
if 'db_type' in config_o2m:
    db_type = config_o2m['db_type']
    db_username = config_o2m['db_username']
    db_password = config_o2m['db_password']
    db_host = config_o2m['db_host']
    db_port = config_o2m['db_port']
    db_name = config_o2m['db_name']
else:
    db_type = 'sqlite'
# database_path = config_o2m['db_sqlite_path']

# Connect to the database URL defined in the environment, falling
# back to a local Sqlite database if no database URL is specified.
# mysql route : mysql://user:passwd@ip:port/my_db
mysql_route = None
if db_type == 'mysql':
    mysql_route = db_type +'://' + db_username + ':' + db_password + '@' + db_host + ':' + db_port + '/' + db_name
    print('Connecting to mysql database : ' + db_name + ' on host : ' + db_host)
# db = connect(mysql_route or 'sqlite:///data.db')

# MySQL database implementation that utilizes mysql-connector driver.
# db = MySQLConnectorDatabase(db_name, host=db_host, user=db_username, password=db_password)

db = PooledMySQLDatabase(db_name, host=db_host, user=db_username,
                               passwd=db_password, max_connections=8, stale_timeout=110, 
                               thread_safe=False)


# Connection lost after some time.
'''
https://github.com/coleifer/peewee/issues/961
http://docs.peewee-orm.com/en/latest/peewee/api.html#Database

Changer de connector sql ?
Fermer et rouvrir la connexion à chaque fois ? (autour des actions sur les lecteurs nfc)

'''

'''
    MODEL STRUCTURE
'''
class BaseModel(Model):
    class Meta:
        database = db

class Tag(BaseModel):
    uid = CharField(unique=True, index=True, primary_key=True, ) # Unique tag/card/nfc id
    user = CharField(null=True)
    tag_type = CharField(null=True) # album_local, album_spotify etc...
    data = CharField(null=True) # media uri or option
    data_alt = CharField(null=True) # media uri or option
    description = TextField(null=True) # description text
    read_count = IntegerField(default=0) # Increment each time a tag is used
    last_read_date = TimestampField(null=True, utc=True) # timestamp of last used date
    option_new = BooleanField(default=False) # only play new tracks
    option_sort = CharField(null=True) # shuffle, (asc, desc : date of tracks/podcasts)
    option_duration = IntegerField(null=True) # max duration of a media : mostly useful for radios
    option_items_length = IntegerField(null=True) # Podcasts max count to read in podcast channel 

    def __str__(self):
        return 'TAG UID : {} | USER : {} | TYPE : {} | MEDIA : {} | READ COUNT : {} | DESCRIPTION : {}' .format(
            self.uid, 
            self.user, 
            self.tag_type, 
            self.data,
            self.read_count,
            self.description)

    def add_count(self):
        self.read_count += 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()
