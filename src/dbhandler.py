import logging, pprint

from peewee import IntegrityError
from playhouse.migrate import SqliteDatabase, SqliteMigrator
from playhouse.reflection import generate_models, print_model

from src.nfcmodels import Tag, Stats, Stats_Raw, db
'''
Database & Tables creation
Used only one time from the terminal
Usage : 
python3
>>> import dbhandler
>>> dbhandler.create_tables()
>>> quit()
'''
def create_tables():
    with db:
        db.create_tables([Tag])

class DatabaseHandler():

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.log.info('DATABASE HANDLER INITIALIZATION')
        self.tags = self.get_all_tags()

    def create_tag(self, uid, media_url):
        try:
            self.log.info('Creating Tag with uid : {} and media url {}'.format(uid, media_url))
            print('Creating Tag with uid : {} and media url {}'.format(uid, media_url))
            # tag = Tag(uid=uid)
            # response = tag.save()
            tag = Tag.create(uid=uid)
            print(tag)
            # if response == 1:
            #     self.log.info('Tag created : {}'.format(tag))
            #     return tag
            # else:
            #     print('error')
            #     print(response)
        except IntegrityError as err:
            self.log.error(err)
    
    def get_all_tags(self):
        query = Tag.select()
        return self.transform_query_to_list(query)
    
    def get_tag_by_uid(self, uid):
        self.log.info('searching for tag : {} '.format(uid))
        query = Tag.select().where(Tag.uid == uid)
        results = self.transform_query_to_list(query)
        print (results)
        if len(results) > 0:
            return results[0] 
    
    def get_tag_by_data(self, data):
        self.log.info(f'searching for tag with data: {data}')
        query = Tag.select().where(Tag.data == data)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            return results[0] 

    def get_tag_by_option_type(self, option_type):
        #self.log.info(f'searching for tag with option_type: {option_type}')
        query = Tag.select().where(Tag.option_type == option_type)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            return results[0] 

    def get_media_tag(self, uid):
        results = self.get_tag_by_uid(uid)
        if len(results > 0):
            tag = results[0]
            return tag.data
    
    def tag_exists(self, uid):
        if len(Tag.select().where(Tag.uid == uid)) > 0:
            return True
        else:
            return False

    def transform_query_to_list(self, query):
        tags = []
        for tag in query:
            tags.append(tag)
        return tags

    #STATS
    def create_stat(self, uri):
        try:
            stat = Stats.create(uri=uri)
            return stat
        except IntegrityError as err:
            self.log.error(err)
    
    def get_all_stats(self):
        query = Stats.select()
        return self.transform_query_to_list(query)
    
    def get_stat_by_uri(self, uri):
        query = Stats.select().where(Stats.uri == uri)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            #print (results[0])
            return results[0] 
    
    '''def get_stat_by_data(self, data):
        self.log.info(f'searching for stat with data: {data}')
        query = Stats.select().where(Stats.data == data)
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
        if len(Stats.select().where(Stats.uri == uri)) > 0:
            return True
        else:
            return False

    #STATS_RAW
    def create_stat_raw(self, uri, read_time, read_hour, username):
        stat_raw = Stats_Raw.create(uri=uri,read_time=read_time,read_hour=read_hour,username=username)
        return stat_raw    

if __name__ == "__main__":

    models = generate_models(db)
    print('MODEL TAG')
    print_model(models['tag'])

    mydb = DatabaseHandler()

    print('ALL TAGS')
    tags = mydb.get_all_tags()
    pprint.pprint(tags)

    print('creating')
    mydb.create_tag('super_uid2', 'super_media')

    print('searching')
    for tag in Tag.select().where(Tag.uid.contains('super')):
        print(tag)

        print('removing')
        tag.delete_instance() 
    
    print('searching')
    for tag in Tag.select().where(Tag.uid.contains('super')):
        print(tag)
    
    # create_tables()