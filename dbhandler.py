from peewee import IntegrityError
from playhouse.migrate import SqliteDatabase, SqliteMigrator
from playhouse.reflection import generate_models, print_model
import logging, pprint
from nfcmodels import Tag, db

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

    def update_tag_count(self, uid):
        if self.tag_exists(uid):
            response = self.get_tag_by_uid(uid)
            tag = response[0]
            tag.count += 1
            tag.update()
            tag.save()
            print(tag)
            self.log.info('Adding count {} to tag {} '.format(tag.count, tag.uid))
        else:
            self.create_tag(uid, None)

    def create_tag(self, uid, media_url):
        try:
            self.log.info('Creating Tag with uid : {} and media url {}'.format(uid, media_url))
            tag = Tag(uid=uid, media=media_url)
            response = tag.save()
            if response == 1:
                self.log.info('Tag created : {}'.format(tag))
        except IntegrityError as err:
            self.log.error(err)
    
    def get_all_tags(self):
        query = Tag.select()
        return self.transform_query_to_list(query)
    
    def get_tag_by_uid(self, uid):
        self.log.info('searching for tag : {} '.format(uid))
        query = Tag.select().where(Tag.uid == uid)
        return self.transform_query_to_list(query)
    
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