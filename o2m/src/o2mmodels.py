import sys, datetime, json
from peewee import (
    UUIDField,
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


#POCKETBASE
from pocketbase import PocketBase  # Client also works the same
from pocketbase.client import FileUpload
client = PocketBase('http://back:8090')
# or as admin
admin_data = client.admins.auth_with_password("pvincent4@gmail.com", "o2m_pvincent!")


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
    id = str
    name = str
    image = str
    favorite = bool
    public = bool
    contents = [str]
    read_count = int
    last_read_date = str
    flow = [str]

    #Content parsing : Box.contents[i].name


    '''def __str__(self):
        #return "TAG UID : {} | MEDIA : {} | DESCRIPTION : {} | READ COUNT : {}| OPTION_TYPE : {}".format(self.uid, self.data, self.description, self.read_count, self.option_type)
        json_data = "{uid : "+self.uid+" , media : "+self.data+", description : "+self.description+" , read_count : "+self.read_count+" , option_type : "+self.option_type+" }"
        #json_data = json.dumps(model_to_dict(user_obj))
        json_data = json.dumps(json_data)
        return json_data'''
    
    def create(self):
        print("CREATE")
        print(self)
        PocketBase.collection("boxes").create()


    def add_count(self):
        if self.read_count != None:
            self.read_count += 1
        else:
            self.read_count = 1
        self.last_read_date = datetime.datetime.utcnow()
        self.update()
        self.save()


class Stats(BaseModel):
    uri = CharField(unique=True, index=True, primary_key=True)  # Unique uri
    last_read_date = TimestampField(null=True, utc=True)  # date
    read_position = IntegerField(default=0)  # description text
    read_end = FloatField(default=0)  # Rate average
    read_count = IntegerField(default=0)  # int
    read_count_end = IntegerField(default=0)  # int
    skipped_count = IntegerField(default=0)  # int
    in_library = TextField(default='')  # Uri track if exist
    day_time_average = IntegerField(default=0)  # int
    option_type = CharField(null=True)  # option card type : normal (default), new (discover card:only play new tracks), favorites (preferred tracks), hidden (not considered by stats)
    username = TextField(null=True)  # user text

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
