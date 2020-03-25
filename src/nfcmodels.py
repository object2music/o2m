import sys, datetime
from peewee import UUIDField, CharField, IntegerField, TextField, TimestampField, BooleanField, Model, OperationalError
from playhouse.migrate import migrate, MySQLMigrator, SqliteDatabase, SqliteMigrator

sys.path.append('.')
import src.util as util
'''
DATABASE INIT 
'''
database_path = util.get_config()['o2m']['database_path']
db = SqliteDatabase(database_path)
migrator = SqliteMigrator(db)

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
        return 'TAG UID : {} | TYPE : {} | MEDIA : {} | READ COUNT : {}' .format(self.uid, self.tag_type, self.description, self.read_count)

    def add_count(self):
        self.read_count += 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()

# class Tag(BaseModel):
#     # owner = ForeignKeyField(Person, backref='pets')
#     uid = CharField(unique=True)
#     media = CharField(null=True)
#     media_type = CharField(null=True)
#     count = IntegerField(default=0)

#     # add the new migrations on top of the list because the previous migrations throw an error
#     try:
#         migrate(
#             migrator.add_column('tag', 'count', count),
#             migrator.add_column('tag', 'media_type', media_type)
#         )
#     except OperationalError as err:
#         print(err)

#     def __str__(self):
#         return 'TAG UID : {} | TYPE : {} | MEDIA : {} | COUNT : {}' .format(self.uid, self.media_type, self.media, self.count)

#     def add_count(self):
#         self.count += 1
#         self.update()
#         self.save()

if __name__ == "__main__":
    print(database_path)