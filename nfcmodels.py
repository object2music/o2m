from peewee import CharField, IntegerField, Model, OperationalError
from playhouse.migrate import migrate, MySQLMigrator, SqliteDatabase, SqliteMigrator

'''
DATABASE INIT 
'''
db = SqliteDatabase('./o2m.db')
migrator = SqliteMigrator(db)

'''
    MODEL STRUCTURE
'''
class BaseModel(Model):
    class Meta:
        database = db

class Tag(BaseModel):
    # owner = ForeignKeyField(Person, backref='pets')
    uid = CharField(unique=True)
    media = CharField(null=True)
    media_type = CharField(null=True)
    count = IntegerField(default=0)

    # add the new migrations on top of the list because the previous migrations throw an error
    try:
        migrate(
            migrator.add_column('tag', 'count', count),
            migrator.add_column('tag', 'media_type', media_type)
        )
    except OperationalError as err:
        print(err)

    def __str__(self):
        return 'TAG UID : {} | TYPE : {} | MEDIA : {} | COUNT : {}' .format(self.uid, self.media_type, self.media, self.count)

    def add_count(self):
        self.count += 1
        self.update()
        self.save()
