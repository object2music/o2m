import logging, time, configparser, contextlib, sys
from pathlib import Path
from mopidyapi import MopidyAPI
from mopidy_podcast import feeds, Extension

from src.nfcreader import NfcReader
from src.dbhandler import DatabaseHandler, Tag
from src.spotifyhandler import SpotifyHandler
from src import util

logging.basicConfig(format='%(levelname)s CLASS : %(name)s FUNCTION : %(funcName)s LINE : %(lineno)d TIME : %(asctime)s MESSAGE : %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG,
                    filename='./logs/o2m.log', 
                    filemode='a')

START_BOLD = '\033[1m'
END_BOLD = '\033[0m'

'''
    TODO :
        * Logs : séparer les logs par ensemble de fonctionnalités (database, websockets, spotify etc...)
        * Timestamps sur les tags

    INSTALL : 
    pip3 install -r requirements.txt

    CONFIG : 
    Dans le fichier de conf de mopidy : 
        [o2m]
        database_path = src/o2mv1.db
        discover = true # utilise tous les tags pour de la recommandation / lance le contenu du dernier tag détecté

    Le script de recherche de fichier config est dans le fichier src/util.py

    chemin mac données mopidy : 
    /Users/antoine/.local/share/mopidy/
'''

class NfcToMopidy():
    activecards = {}
    activetags = []
    last_tag_uid = None

    suffle = False
    max_results = 50
    default_volume = 70 #0-100
    discover_level = 5 #0-10
    podcast_newest_first = False
    option_sort = 'desc'

    def __init__(self, mopidyHandler, config):
        self.log = logging.getLogger(__name__)
        self.log.info('NFC TO MOPIDY INITIALIZATION')
        
        self.config = config
        self.dbHandler = DatabaseHandler() # Gère la base de données
        self.mopidyHandler = mopidyHandler # Commandes mopidy via websockets
        self.spotifyHandler = SpotifyHandler() # Appel à l'api spotify pour recommandations
        self.nfcHandler = NfcReader(self) # Contrôle les lecteurs nfc et renvoie les identifiants des cartes

        if 'api_result_limit' in self.config['o2m']:
            self.max_results = int(self.config['o2m']['api_result_limit'])            
                
        if 'default_volume' in self.config['o2m']:
            self.default_volume = int(self.config['o2m']['default_volume'])  

        if 'discover_level' in self.config['o2m']:
            self.discover_level = int(self.config['o2m']['discover_level'])  

        if 'podcast_newest_first' in self.config['o2m']:
            self.podcast_newest_first = self.config['o2m']['podcast_newest_first'] == 'true' 

        if 'option_sort' in self.config['o2m']:
            self.option_sort = self.config['o2m']['option_sort'] == 'desc' 
        
        if 'shuffle' in self.config['o2m']:
            self.shuffle = bool(self.config['o2m']['shuffle'])

        #Default volume setting at beginning (or in main ?)
        self.mopidyHandler.mixer.set_volume(self.default_volume)


    def start_nfc(self):
        #Test mode provided in command line (NFC uids separated by space)
        if len(sys.argv) > 1:
            for i in range(1,len(sys.argv)):
                print(sys.argv[i])
                tag = self.dbHandler.get_tag_by_uid(sys.argv[i])
                self.activetags.append(tag) # Ajoute le tag détecté dans la liste des tags actifs
                if self.config['o2m']['discover'] == 'true':
                    self.active_tags_changed()
                else:
                    self.one_tag_changed(tag)
        else:
            self.nfcHandler.loop() # démarre la boucle infinie de détection nfc/rfid
    
    '''
    Fonction appellée automatiquement dès qu'un changement est détecté au niveau des lecteurs rfid
    '''
    def get_new_cards(self, addedCards, removedCards, activeCards):
        self.activecards = activeCards
        # Décommenter la ligne en dessous pour avoir de l'info sur les données récupérées dans le terminal
        # self.pretty_print_nfc_data(addedCards, removedCards)
        
        # Boucle sur les cartes ajoutées
        for card in addedCards:
            tag = self.dbHandler.get_tag_by_uid(card.id) # On récupère le tag en base de données via l'identifiant rfid
            if tag != None:
                tag.add_count() # Incrémente le compteur de contacts pour ce tag
                self.activetags.append(tag) # Ajoute le tag détecté dans la liste des tags actifs
                
                if self.config['o2m']['discover'] == 'true':
                    self.active_tags_changed()
                else:
                    self.one_tag_changed(tag)
            else:
                if card.id != '':
                    self.dbHandler.create_tag(card.id, '') # le tag n'est pas présent en bdd donc on le rajoute
                else:
                    print('Reading card error ! : ' + card)

        for card in removedCards:
            print('card removed')
            tag = self.dbHandler.get_tag_by_uid(card.id) # On récupère le tag en base de données via l'identifiant rfid
            removedTag = next((x for x in self.activetags if x.uid == card.id), None)
            
            if tag != None and tag in self.activetags:
                self.activetags.remove(tag)

            if len(self.activetags) == 0:
                # print('Stopping music')
                self.mopidyHandler.playback.stop() 
                self.mopidyHandler.tracklist.clear()
            elif removedTag.tlids != None:
                current_tlid = self.mopidyHandler.playback.get_current_tlid()
                # last_tlindex = 0
                # if current_tlid != None:
                    # if current_tlid in removedTag.tlids:
                    #     removedTag.tlids.remove(current_tlid)
                    # all_tracklist_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                    # current_track = next((x for x in all_tracklist_tracks if x.tlid == current_tlid))
                
                last_tlindex = self.mopidyHandler.tracklist.index()
                print(last_tlindex)

                if current_tlid in removedTag.tlids:
                    self.mopidyHandler.playback.stop()
                self.mopidyHandler.tracklist.remove({'tlid': removedTag.tlids})
                tl_length = self.mopidyHandler.tracklist.get_length()

                print(tl_length)
                all_new_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                if tl_length > last_tlindex:
                    if self.mopidyHandler.playback.get_state() != 'playing':
                        self.mopidyHandler.playback.play(all_new_tracks[last_tlindex-1])
                else:
                    self.play_or_resume()
            else:
                print('no uris with removed tag')
            
        print(f'Active tags count: {len(self.activetags)}')
    
    '''
    Fonction alternative executée à chaque détecton de tag : 
    Ne coupe pas la lecture mais augmente et modifie la tracklist en fonction des paramètres de trois tags.
    '''
    def active_tags_changed(self):
        seeds_genres = []
        seeds_artists = []
        seeds_tracks = []
        # local_uris = []
        for tag in self.activetags:
            if tag.tag_type == 'genre':
                seeds_genres += self.parse_tag_data(tag.data)
            elif 'spotify' in tag.tag_type and 'artist' in tag.tag_type:
                seeds_artists += self.parse_tag_data(tag.data)
            elif 'spotify' in tag.tag_type and 'album' in tag.tag_type:
                print('spotify album not ready yet : need to get all tracks of album or playlist then feed the seed')
            # else:
                # si le tag non compatible -> récupérer les utis et les ajouter à local_uris
            
        if (len(seeds_artists) > 0 or len(seeds_genres) > 0 or len(seeds_tracks) > 0):
            tracks_uris = self.spotifyHandler.get_recommendations(seeds_genres, seeds_artists, limit=self.max_results)
            self.add_tracks_after(tracks_uris) # ajouter les local_uris (merge des deux listes d'uris)
        else:
            # TODO : Aucune carte compatible pour la reco : Decider du comportement
            print('Carte non compatible avec la recommandation spotify!')

    def parse_tag_data(self, data):
        data_string = data.split(':')[-1]
        return data_string.split(',')
        
        
    '''
    Fonction appellée quand un nouveau tag est détecté et que l'on fonctionne en mode télécommande
    Un tag -> une action -> un contenu :
        Recommandations : 
            - Genres : Recommandation sur le ou les genres inclus dans le tag
            - Artists : Recommandation sur le ou les artistes ...
        m3u : Parsing de la playlist hybride 
        spotify : 
            - artist : Top tracks ou all tracks de l'artiste
            - album 
            - track
        local :
            - artist
            - album
            - track
        podcasts : 
            - show
            - channel / album
    '''
    def one_tag_changed(self, tag):
        if tag.uid != self.last_tag_uid: # Si différent du précédent tag détecté (Fonctionnel uniquement avec un lecteur)
            print(f'Tag : {tag}' )

            #Update max_results with DB specific tag option (duration is not good and definitive nomenclature)
            max_results = self.max_results
            if tag.option_duration != None:
            	max_results = tag.option_duration

            # self.last_tag_uid = tag.uid # On stocke en variable de classe le tag pour le comparer ultérieurement
            media_parts = tag.data.split(':') # on découpe le champs média du tag en utilisant le séparateur : 
            
            #Recommandation
            if 'recommendation' in media_parts:
                if media_parts[3] == 'genres': # si les seeds sont des genres
                    genres = media_parts[4].split(',') # on sépare les genres et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(seed_genres=genres, limit=max_results) # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    self.add_tracks(tag, tracks_uris) # Envoie les uris au mopidy Handler pour modifier la tracklist
                elif media_parts[3] == 'artists': # si les seeds sont des artistes
                    artists = media_parts[4].split(',') # on sépare les artistes et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(seed_artists=artists, limit=max_results) # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    self.add_tracks(tag, tracks_uris) # Envoie les uris au mopidy Handler pour modifier la tracklist
            
            # Playlist hybride / mopidy / iris
            elif media_parts[0] == 'm3u': 
                playlist_uris = []
                playlist = self.mopidyHandler.playlists.lookup(tag.data) # On retrouve le contenu avec son uri
                for track in playlist.tracks: # Parcourt la liste de tracks
                    #Podcast channel
                    if 'podcast' in track.uri and '#' not in track.uri: 
                        print(track.uri)
                        feedurl = track.uri.split('+')[1]
                        shows = self.get_unread_podcasts(track.uri, 0, max_results) 
                        self.add_tracks(tag, shows)
                        # On doit rechercher un index de dernier épisode lu dans une bdd de statistiques puis lancer les épisodes non lus
                        # playlist_uris += self.get_unread_podcasts(shows)
                    #Podcast episode
                    elif 'podcast' in track.uri and '#' in track.uri: 
                        feedurl = track.uri.split('+')[1]
                        self.get_podcast_from_url(feedurl)                     
                    #Other contents in the playlist
                    else:
                        playlist_uris.append(track.uri) # Recupère l'uri de chaque track pour l'ajouter dans une liste
                self.add_tracks(tag, playlist_uris) # Envoie les uris en lecture
            
            # Spotify
            elif media_parts[0] == 'spotify':
                if media_parts[1] == 'artist':
                    print('find tracks of artist : ' + tag.description)
                    tracks_uris = self.spotifyHandler.get_artist_top_tracks(media_parts[2]) # 10 tops tracks of artist
                    tracks_uris = tracks_uris + self.spotifyHandler.get_artist_all_tracks(media_parts[2], limit=max_results-10) # all tracks of artist with no specific order
                    self.add_tracks(tag, tracks_uris)
                else:
                    self.add_tracks(tag, [tag.data])
            
            #Podcast:channel
            elif tag.tag_type == 'podcasts:channel':
                print('channel! get unread podcasts')
                uris = self.get_unread_podcasts(tag.data, tag.option_items_length)
                self.add_tracks(tag, uris)
            
            #Every other contents
            else:
                self.add_tracks(tag, [tag.data]) # Ce n'est pas une reco alors on envoie directement l'uri à mopidy
        
        #Next option
        else:
            print(f'Tag : {tag.uid} & last_tag_uid : {self.last_tag_uid}' )
            self.launch_next() # Le tag détecté est aussi le dernier détecté donc on passe à la chanson suivante
            return

        if mopidy.tracklist.get_length() > 0: 
            self.play_or_resume()

    def get_podcast_from_url(self, url, max_results = 50):
        f = Extension.get_url_opener({"proxy":{}}).open(url, timeout=10)
        with contextlib.closing(f) as source:
            feed = feeds.parse(source)
        shows = list(feed.items(self.option_sort))
        for item in shows:
            if "app_rf_promotion" in item.uri:
                 max_results += 1
        # Conserve les max_results premiers épisodes
        del shows[max_results:]
        return shows

    def get_unread_podcasts(self, data, last_track_played, max_results = 50):
        uris = []
        feedurl = data.split('+')[1]
        
        shows = self.get_podcast_from_url(feedurl, max_results)
        unread_shows = shows[last_track_played:] # Supprime le n premiers éléments (déjà lus)
        for item in unread_shows:
            if "app_rf_promotion" not in item.uri: 
                uris.append(item.uri)
        print (shows)
        return uris

    # Lance la chanson suivante sur mopidy
    def launch_next(self):
        self.mopidyHandler.playback.next()
        self.mopidyHandler.playback.play()

    # Vide la tracklist, ajoute plusieurs uris puis lance la lecture
    def add_tracks(self, tag, uris):
        print(uris)
        tltracks_added = self.mopidyHandler.tracklist.add(uris=uris)

        if tltracks_added:
            #Slice added tracks to max_results
            tltracks_rem = tltracks_added[self.max_results:]
            for x in tltracks_rem:
                self.mopidyHandler.tracklist.remove({'tlid': [x.tlid]}) #to optimize ?
            tltracks_added = tltracks_added[0:self.max_results]
            #slice1 = self.mopidyHandler.tracklist.slice(start, end)
            print(f'Adding {len(tltracks_added)} tracks')
            
            #Update Tag Values
            #TLIDs : Mopidy Tracks's IDs in tracklist associated to added Tag
            if hasattr(tag, 'tlids'):
                tag.tlids += [x.tlid for x in tltracks_added]
            else:
                tag.tlids = [x.tlid for x in tltracks_added]
            print("tag.tlids",tag.tlids)

            #Uris : Mopidy Uri's associated to added Tag
            tag.uris = uris 
            print("tag.uris",tag.uris)


            #conditions pour mélanger les tracks : shuffle global, carte ou plus de 2 cartes
            if self.shuffle == 'true' or tag.option_sort == 'shuffle' or len(self.activetags) > 1:
                current_index = self.mopidyHandler.tracklist.index()
                tl_length = self.mopidyHandler.tracklist.get_length()
                if current_index != None:
                    self.mopidyHandler.tracklist.shuffle(current_index + 1, tl_length)
                else:
                    self.mopidyHandler.tracklist.shuffle(0, tl_length)                
            #self.play_or_resume()
    
    def play_or_resume(self):
        state = self.mopidyHandler.playback.get_state()
        if state == 'stopped':
            if self.mopidyHandler.playback.get_current_tl_track() == None:
                print('no current track : Playing first track')
                current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                if len(current_tracks) > 0:
                    self.mopidyHandler.playback.play(tlid=current_tracks[0].tlid)
            else:
                self.mopidyHandler.playback.play()
        elif state == 'paused':
            self.mopidyHandler.playback.resume()
        else:
            self.mopidyHandler.playback.next()
    
    # Vide la tracklist sauf la chanson en cours de lecture puis ajoute des uris à la suite
    @util.RateLimited(1) # Limite l'execution de la fonction : une fois par seconde (à vérifier)
    def add_tracks_after(self, uris):
        print('ADDING SONGS SILENTLY IN TRACKLIST')
        self.clear_tracklist_except_current_song()
        self.mopidyHandler.tracklist.add(uris=uris)

    def add_tracks_simple(self, uris):
        #Calculate index of insertion depending of discover_level
        current_index = self.mopidyHandler.tracklist.index()
        tl_length = self.mopidyHandler.tracklist.get_length()
        new_index = int(round(current_index + ((tl_length - current_index)*(10-self.discover_level)/10)))
        print("Adding new track at "+str(new_index)+" index")
        
        self.mopidyHandler.tracklist.add(uris=uris,at_position=new_index)

    def clear_tracklist_except_current_song(self):
        all_tracklist_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
        current_tlid = self.mopidyHandler.playback.get_current_tlid()
        for (tlid, _) in all_tracklist_tracks:
            if tlid != current_tlid:
                self.mopidyHandler.tracklist.remove({'tlid': [tlid]})
    
    # Appelle ou rappelle la fonction de recommandation pour allonger la tracklist et poursuivre la lecture de manière transparente
    def update_tracks(self):
        print('should update tracks')   

    # Pour le debug, print en console dans le détail les tags détectés et retirés
    # TODO : Déplacer dans la partie NFCreader, plus très utile ici ?
    def pretty_print_nfc_data(self, addedCards, removedCards):
        print('-------')
        print('NFC TAGS CHANGED!')
        print('COUNT : \n     ADDED : {}  \n     REMOVED : {} '.format(len(addedCards), len(removedCards)))
        print('ACTIONS : ')
        print('     ADDED : {} \n     REMOVED : {}'.format( 
            [x.reader + ' : ' + x.id for x in addedCards], 
            [x.reader + ' : ' + x.id for x in removedCards]))
        
        print('CURRENT CARDS ACTIVED : ')
        for key, card in self.activecards.items():
            print('     Reader : {} with card : {} '.format(key, card.id))
        print('-------')

'''
    Pas très clean de mettre les fonction de callback aux évènements dans le main 
    Mais on a besoin de l'instance de mopidyApi et la fonction callback à besoin de l'instance nfcHandler pour lancer les recos...

    Piste : Ajouter encore une classe mère pour remplacer le main?
'''
if __name__ == "__main__":

    mopidy = MopidyAPI()
    config = util.get_config()
    nfcHandler = NfcToMopidy(mopidy, config)
    spotifyHandler = SpotifyHandler() # Appel à l'api spotify pour recommandations

    # A chaque lancement on vide la tracklist (plus simple pour les tests)
    mopidy.tracklist.clear()

    # Fonction appellée à chaque changement de chanson
    @mopidy.on_event('track_playback_ended')
    def print_ended_events(event):
        track = event.tl_track.track
        print(f"Ended song : {START_BOLD}{track.name}{END_BOLD} at : {START_BOLD}{event.time_position}{END_BOLD} ms")
        if 'podcast' in track.uri:
            if event.time_position / track.length > 0.5: # Si la lecture de l'épisode est au delà de la moitié
                tag = nfcHandler.dbHandler.get_tag_by_data(track.album.uri) # Récupère le tag correspondant à la chaine
                if tag != None:
                    if tag.tag_type == 'podcasts:channel':
                        tag.option_items_length = track.track_no # actualise le numéro du dernier podcast écouté
                        tag.update()
                        tag.save()

        #on ajoute une nouvelle recommandation à chaque track terminée
        if 'spotify:track' in track.uri and event.time_position / track.length > 0.9:
            track_data = track.uri.split(':') # on découpe l'uri' :
            tracks = [track_data[2]]
            #print (tracks)
            uris = spotifyHandler.get_recommendations(seed_genres=None, seed_artists=None, seed_tracks=tracks, limit=1)
            nfcHandler.add_tracks_simple(uris)

        tracklist_length = mopidy.tracklist.get_length()
        tracklist_index = mopidy.tracklist.index()
        if tracklist_index != None and tracklist_length != 0:
            index = tracklist_index + 1
            tracks_left_count = tracklist_length - index # Nombre de chansons restante dans la tracklist            
            if tracks_left_count < 1: 
                nfcHandler.update_tracks() # si besoin on ajoute des chansons à la tracklist avec de la reco 

    #Infinite loop for NFC detection
    nfcHandler.start_nfc()


# Code pour créer manuellement des tags en bdd
# if __name__ == "__main__":
#     mydb = DatabaseHandler()
#     tag = mydb.get_tag_by_uid('AB34A324')
#     tag.description = 'Spotify Artist : Creedence'
#     tag.save()
#     # tag = Tag.create('AB34A324')
#     #     uid='AB34A324', 
#     #     tag_type = 'spotify:artist', 
#     #     data = 'spotify:artist:3IYUhFvPQItj6xySrBmZkd',
#     #     descrition = 'Spotify Artist : Creedence')
#     print(tag)