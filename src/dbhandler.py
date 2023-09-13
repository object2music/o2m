import logging, pprint, datetime, random, json

from peewee import IntegrityError, fn
from playhouse.migrate import SqliteDatabase, SqliteMigrator
from playhouse.reflection import generate_models, print_model
from playhouse.shortcuts import model_to_dict, dict_to_model


from src.o2mmodels import Box, Stats, Stats_Raw, db
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
        db.create_tables([Box])

class DatabaseHandler():

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.log.info('DATABASE HANDLER INITIALIZATION')
        self.boxs = self.get_all_boxs()
    
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
        results = list(Box.select().where(Box.favorite == 1).dicts()) 
        #results = json.dumps(model_to_dict(query))
        #results = self.transform_query_to_list(query)
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

    def get_stat_raw_by_hour(self, read_hour, window=0, limit=1, uri_pattern='track:'):
        if window > 0:
            query = Stats_Raw.select().where((Stats_Raw.read_hour.between(read_hour - window, read_hour + window))&(Stats_Raw.uri.contains(uri_pattern))).order_by(fn.Rand()).limit(limit)
        else:
            query = Stats_Raw.select().where((Stats_Raw.read_hour == read_hour)&(Stats_Raw.uri.contains(uri_pattern))).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
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

    def get_uris_new_notread(self, limit=1, date_now=0):
        #Track boxged new but only read once, probably because of ephemere availability like spotify. Request above two week
        date_now = datetime.datetime.utcnow().timestamp()
        query = Stats.select().where((Stats.uri % '%spotify:track%') & (Stats.read_count_end  >= 1) & (Stats.skipped_count == 0) & (Stats.option_type == 'new') & (Stats.last_read_date < (date_now-1209600))).order_by(fn.Rand()).limit(limit)
        #query = Stats.select().where((Stats.read_count_end  >= 1) | (Stats.skipped_count == 0) | (Stats.option_type == 'new') | (date - Stats.last_read_date > 1209600)).order_by(fn.Rand()).limit(limit)
        results = self.transform_query_to_list(query)
        if len(results) > 0:
            uris = [o.uri for o in results]
            print (f"Adding : news_notcompleted:library {len(uris)}")
            return uris

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