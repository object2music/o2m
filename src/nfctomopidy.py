import datetime, sys, contextlib
import numpy as np
from mopidy_podcast import Extension, feeds
from urllib import parse

import src.util as util
from src.dbhandler import DatabaseHandler, Stats, Stats_Raw, Tag
from src.nfcreader import NfcReader
from src.spotifyhandler import SpotifyHandler

'''
option_type 
- normal
- favorites
- new
- incoming
- hidden
- trash
'''


class NfcToMopidy:
    activecards = {}
    activetags = []
    last_tag_uid = None

    suffle = False
    max_results = 50
    default_volume = 70  # 0-100
    option_discover_level = 5  # 0-10
    podcast_newest_first = False
    option_sort = "desc"

    def __init__(self, mopidyHandler, configO2m, configMopidy, logging):
        self.log = logging.getLogger(__name__)
        self.log.info("NFC TO MOPIDY INITIALIZATION")

        self.configO2M = configO2m["o2m"]
        self.configMopidy = configMopidy
        self.dbHandler = DatabaseHandler()  # Gère la base de données
        self.mopidyHandler = mopidyHandler  # Commandes mopidy via websockets
        self.spotifyHandler = SpotifyHandler()  # Api spotify pour recommandations
        # Contrôle les lecteurs nfc et renvoie les identifiants des cartes
        self.nfcHandler = NfcReader(self)

        if "api_result_limit" in self.configO2M:
            self.max_results = int(self.configO2M["api_result_limit"])

        if "default_volume" in self.configO2M:
            self.default_volume = int(self.configO2M["default_volume"])
        self.current_volume = self.default_volume

        if "discover_level" in self.configO2M:
            self.option_discover_level = int(self.configO2M["discover_level"])

        if "podcast_newest_first" in self.configO2M:
            self.podcast_newest_first = self.configO2M["podcast_newest_first"] == "true"

        if "option_sort" in self.configO2M:
            self.option_sort = self.configO2M["option_sort"] == "desc"

        if "option_autofill_playlists" in self.configO2M:
            self.option_autofill_playlists = self.configO2M["option_autofill_playlists"] == "True"
        else: self.option_autofill_playlists = False

        if "shuffle" in self.configO2M:
            self.shuffle = bool(self.configO2M["shuffle"])

        if "username" in self.configMopidy["spotify"]:
            self.username = self.configMopidy["spotify"]["username"]

        self.starting_mode(clear=True)

    def starting_mode(self,clear=False):
        # Default volume setting at beginning (or in main ?)
        if clear == True: 
            self.mopidyHandler.tracklist.clear()
            self.mopidyHandler.playback.stop()
        self.mopidyHandler.tracklist.set_random(False)
        self.mopidyHandler.mixer.set_mute(False)
        self.mopidyHandler.mixer.set_volume(self.default_volume)

    def tag_action(self,tag):
        if self.configO2M["discover"] == "true":
            try: 
                self.active_tags_changed()
            except Exception as val_e: 
                print(f"Erreur : {val_e}")
                self.spotifyhandler.init_token_sp() #pb of expired token to resolve...
                self.active_tags_changed()
        else:
            try: 
                self.one_tag_changed(tag)
            except Exception as val_e: 
                print(f"Erreur : {val_e}")
                self.spotifyhandler.init_token_sp() #pb of expired token to resolve...
                self.one_tag_changed(tag)

    def start_nfc(self):
        # Test mode provided in command line (NFC uids separated by space)
        if len(sys.argv) > 1:
            for i in range(1, len(sys.argv)):
                print(sys.argv[i])
                tag = self.dbHandler.get_tag_by_uid(sys.argv[i])
                self.activetags.append(tag)  # Ajoute le tag détecté dans la liste des tags actifs
                self.tag_action(tag)
        else:
            self.nfcHandler.loop()  # démarre la boucle infinie de détection nfc/rfid

    """
    Fonction appellée automatiquement dès qu'un changement est détecté au niveau des lecteurs rfid
    """

    def get_new_cards(self, addedCards, removedCards, activeCards):
        self.activecards = activeCards
        # Décommenter la ligne en dessous pour avoir de l'info sur les données récupérées dans le terminal
        # self.pretty_print_nfc_data(addedCards, removedCards)

        # Loop on added Cards
        for card in addedCards:
            tag = self.dbHandler.get_tag_by_uid(card.id)  # On récupère le tag en base de données via l'identifiant rfid
            if tag != None:
                tag.add_count()  # Incrémente le compteur de contacts pour ce tag
                self.activetags.append(tag)  # Ajoute le tag détecté dans la liste des tags actifs

                self.tag_action(tag)

            else:
                if card.id != "":
                    self.dbHandler.create_tag(card.id, "")  # le tag n'est pas présent en bdd donc on le rajoute
                else:
                    print("Reading card error ! : " + card)

        # Loop on removed Cards
        for card in removedCards:
            print("card removed")
            tag = self.dbHandler.get_tag_by_uid(card.id)  # On récupère le tag en base de données via l'identifiant rfid
            removedTag = next((x for x in self.activetags if x.uid == card.id), None)

            if tag != None and tag in self.activetags:
                self.activetags.remove(tag)

            if len(self.activetags) == 0:
                # print('Stopping music')
                self.update_stat_track(
                    self.mopidyHandler.playback.get_current_track(),
                    self.mopidyHandler.playback.get_time_position()
                )
                self.starting_mode(clear=True)
            elif removedTag.tlids != None:
                #Compute NewTlid (after track removing)
                current_tlid = self.mopidyHandler.playback.get_current_tlid()
                last_tlindex = self.mopidyHandler.tracklist.index()

                if current_tlid in removedTag.tlids:
                    self.update_stat_track(
                        self.mopidyHandler.playback.get_current_track(),
                        self.mopidyHandler.playback.get_time_position()
                    )
                    self.mopidyHandler.playback.stop()

                    current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()                
                    current_tlids = [ sub.tlid for sub in current_tracks ]

                    #Looping on active tracks
                    for i in current_tlids[last_tlindex:]:
                        if i not in removedTag.tlids:
                            next_tlid = i
                            break
                else:
                    next_tlid = current_tlid
                                
                #Removing tracks from playslist
                self.mopidyHandler.tracklist.remove({"tlid": removedTag.tlids})

                if current_tlid in removedTag.tlids:
                    self.mopidyHandler.playback.play(tlid=next_tlid)

            else:
                print("no uris with removed tag")

        print(f"Active tags count: {len(self.activetags)}")

    """
    Fonction alternative executée à chaque détecton de tag : 
    Ne coupe pas la lecture mais augmente et modifie la tracklist en fonction des paramètres de trois tags.
    """

    def active_tags_changed(self):
        seeds_genres = []
        seeds_artists = []
        seeds_tracks = []
        # local_uris = []
        for tag in self.activetags:
            if tag.tag_type == "genre":
                seeds_genres += self.parse_tag_data(tag.data)
            elif "spotify" in tag.tag_type and "artist" in tag.tag_type:
                seeds_artists += self.parse_tag_data(tag.data)
            elif "spotify" in tag.tag_type and "album" in tag.tag_type:
                print(
                    "spotify album not ready yet : need to get all tracks of album or playlist then feed the seed"
                )
            # else:
            # si le tag non compatible -> récupérer les utis et les ajouter à local_uris

        if len(seeds_artists) > 0 or len(seeds_genres) > 0 or len(seeds_tracks) > 0:
            tracks_uris = self.spotifyHandler.get_recommendations(
                seeds_genres, seeds_artists, limit=self.max_results
            )
            self.add_tracks_after(
                tracks_uris
            )  # ajouter les local_uris (merge des deux listes d'uris)
        else:
            # TODO : Aucune carte compatible pour la reco : Decider du comportement
            print("Carte non compatible avec la recommandation spotify!")

    def parse_tag_data(self, data):
        data_string = data.split(":")[-1]
        return data_string.split(",")

    """
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
    """

    def one_tag_changed(self, tag):
        if (tag.uid != self.last_tag_uid):  # Si différent du précédent tag détecté (Fonctionnel uniquement avec un lecteur)
            print(f"\nNouveau tag détecté: {tag}")

            # Variables
            max_results = self.max_results
            if tag.option_max_results: max_results = tag.option_max_results
            print (f"Max results : {max_results}")
            media_parts = tag.data.split(":")  #on découpe le champs média du tag en utilisant le séparateur :

            #DB Regulation (tmp)
            #self.reg_tag_db(tag)
            content = 0

            # Recommandation
            if "recommendation" in media_parts:
                if media_parts[3] == "genres":  # si les seeds sont des genres
                    genres = media_parts[4].split(
                        ","
                    )  # on sépare les genres et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(
                        seed_genres=genres, limit=max_results
                    )  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    self.add_tracks(
                        tag, tracks_uris, max_results
                    )  # Envoie les uris au mopidy Handler pour modifier la tracklist
                elif media_parts[3] == "artists":  # si les seeds sont des artistes
                    artists = media_parts[4].split(
                        ","
                    )  # on sépare les artistes et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(
                        seed_artists=artists, limit=max_results
                    )  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    self.add_tracks(
                        tag, tracks_uris, max_results
                    )  # Envoie les uris au mopidy Handler pour modifier la tracklist

            # Playlist hybride / mopidy / iris
            elif media_parts[0] == "m3u":
                playlist_uris = []
                playlist = self.mopidyHandler.playlists.lookup(tag.data)  # On retrouve le contenu avec son uri
                for track in playlist.tracks:  # Parcourt la liste de tracks
                    # Add
                    # Podcast channel
                    if "podcast" in track.uri and "#" not in track.uri:
                        print(f"Podcast : {track.uri}")
                        feedurl = track.uri.split("+")[1]
                        par = parse.parse_qs(parse.urlparse(feedurl).query)
                        if 'max_results' in par : max_results_pod = int(par['max_results'][0])
                        else : max_results_pod = max_results
                        #volume=parse.parse_qs(parse.urlparse(feedurl).query)['volume'][0]

                        shows = self.get_unread_podcasts(track.uri, 0)
                        # print(f'Shows : {shows}')
                        print(f'max_results_pod : {max_results_pod}')
                        self.add_tracks(tag, shows, max_results_pod)
                        # On doit rechercher un index de dernier épisode lu dans une bdd de statistiques puis lancer les épisodes non lus
                        # playlist_uris += self.get_unread_podcasts(shows)
                        content += 1

                    # Podcast episode
                    elif "podcast" in track.uri and "#" in track.uri:
                        feedurl = track.uri.split("+")[1]
                        self.get_podcast_from_url(feedurl)

                    # here&now:library
                    elif "herenow:library" in track.uri :
                        discover_level = self.get_option_for_tag(tag, "option_discover_level")
                        window = int(round(discover_level / 2))
                        #max_result1 = int(round((11-discover_level)*max_results/10))
                        #playlist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
                        #playlist_uris.append(self.get_spotify_library((max_results-max_result1)))
                        max_result1 = int(round(max_results/2))
                        playlist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
                        playlist_uris.append(self.get_spotify_library(max_result1))
                        #print(f"Adding herenow : {playlist_uris} tracks")

                    # auto:library
                    elif "auto:library" in track.uri :
                        discover_level = self.get_option_for_tag(tag, "option_discover_level")
                        window = int(round(discover_level / 2))
                        max_result1 = int(round(max_results/3))
                        playlist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
                        playlist_uris.append(self.get_spotify_library(max_result1))
                        self.add_playlistnew_tracks(max_result1)
                        content += 1

                    # spotify:library
                    elif "spotify:library" in track.uri :
                        print ("spotify:library")
                        playlist_uris.append(self.get_spotify_library(max_results))

                    # now:library
                    elif "now:library" in track.uri :
                        print ("now:library")
                        discover_level = self.get_option_for_tag(tag, "option_discover_level")
                        window = int(round(discover_level / 2))
                        playlist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_results))
                   
                    # Other contents in the playlist
                    else : playlist_uris.append(track.uri)  # Recupère l'uri de chaque track pour l'ajouter dans une liste

                if len(playlist_uris)>0:
                    #some contents are unique in lists, need to be flatten
                    playlist_uris1 = util.flatten_list(playlist_uris)
                    self.add_tracks(tag, playlist_uris1, max_results) # Envoie les uris en lecture
                    print(f"Adding : {playlist_uris1} tracks")
                    content += 1
                   

            # Spotify
            elif media_parts[0] == "spotify":
                if media_parts[1] == "artist":
                    print("find tracks of artist : " + tag.description)
                    tracks_uris = self.spotifyHandler.get_artist_top_tracks(media_parts[2])  # 10 tops tracks of artist
                    tracks_uris = (tracks_uris+ self.spotifyHandler.get_artist_all_tracks(media_parts[2], limit=max_results - 10))  # all tracks of artist with no specific order
                    self.add_tracks(tag, tracks_uris, max_results)
                    content += 1
                else:
                    self.add_tracks(tag, [tag.data], max_results)
                    content += 1


            # Podcast:channel
            elif tag.tag_type == "podcasts:channel":
                print("channel! get unread podcasts")
                uris = self.get_unread_podcasts(tag.data, tag.option_last_unread)
                self.add_tracks(tag, uris, max_results)
                content += 1


            # Every other contents
            else:
                self.add_tracks(tag, [tag.data], max_results)  # Ce n'est pas un cas particulier alors on envoie directement l'uri à mopidy
                content += 1


            #Shuffle if several entries in this action
            if (content > 1) and ((self.shuffle == "true" and tag.option_sort != "desc" and tag.option_sort != "asc") or tag.option_sort == "shuffle"):
                index = 0
                if self.mopidyHandler.tracklist.index() != None: index = int(self.mopidyHandler.tracklist.index())
                length = self.mopidyHandler.tracklist.get_length()
                self.shuffle_tracklist(index+1,length)

        # Next option
        else:
            print(f"Tag : {tag.uid} & last_tag_uid : {self.last_tag_uid}")
            self.launch_next()  # Le tag détecté est aussi le dernier détecté donc on passe à la chanson suivante
            return


        if self.mopidyHandler.tracklist.get_length() > 0:
            self.play_or_resume()

    def get_podcast_from_url(self, url):
        f = Extension.get_url_opener({"proxy": {}}).open(url, timeout=10)
        with contextlib.closing(f) as source:
            feed = feeds.parse(source)
        print(f"option_sort : {self.option_sort}")
        shows = list(feed.items(self.option_sort))
        """for item in shows:  
            if "app_rf_promotion" in item.uri:  max_results += 1"""
        # Conserve les max_results premiers épisodes
        del shows[self.max_results :]
        return shows

    def get_unread_podcasts(self, data, last_track_played):
        uris = []
        feedurl = data.split("+")[1]

        shows = self.get_podcast_from_url(feedurl)
        unread_shows = shows[last_track_played:]  # Remove n first shows already read (to be checked not used anymore)
        for item in unread_shows:
            #print (f"get_end_stat {self.dbHandler.get_end_stat(item.uri)} and item.uri {item.uri}")
            if (
                self.dbHandler.get_end_stat(item.uri) == 0
                and "app_rf_promotion" not in item.uri
            ):
                uris.append(item.uri)
        #print(f"Show {shows}")
        #print(f"Unread Show {unread_shows}")
        return uris

    # Lance la chanson suivante sur mopidy
    def launch_next(self):
        self.mopidyHandler.playback.next()
        self.mopidyHandler.playback.play()

    # Shuffling the tracklist
    def shuffle_tracklist(self, start_index, stop_index):
        try:
            if start_index != None:
                self.mopidyHandler.tracklist.shuffle(start_index, stop_index)
            else:
                self.mopidyHandler.tracklist.shuffle(0, stop_index)
        except:
            print(f"error")

    # New tag added : adding tracks to tracklist and associate them to tracks table
    def add_tracks(self, tag, uris, max_results=15):
        prev_length = self.mopidyHandler.tracklist.get_length()
        current_index = self.mopidyHandler.tracklist.index()

        tltracks_added = self.mopidyHandler.tracklist.add(uris=uris)

        if tltracks_added:
            uris_rem = []
            # Exclude tracks already read when option is new
            if tag.option_type == 'new':
                for t in tltracks_added:
                    if self.dbHandler.stat_exists(t.track.uri):
                        stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                        # When track skipped or too many counts
                        if (stat.skipped_count > 0
                            or self.threshold_playing_count_new(stat.read_count_end-1,self.option_discover_level) == True
                            or stat.in_library == 1
                            #or (stat.option_type != 'new' and stat.option_type != '' and stat.option_type != 'trash' and stat.option_type != 'hidden')
                            or (stat.option_type == 'trash' or stat.option_type == 'hidden')
                        ): 
                            uris_rem.append(t.track.uri)
                    #if t.track.uri in self.mopidyHandler.tracklist.get_tracks().uri:uris_rem.append(t.track.uri)

            else:
                #Removing trash and hidden
                '''for t in tltracks_added:
                    if self.dbHandler.stat_exists(t.track.uri):
                        stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                        if (stat.option_type == 'trash' or stat.option_type == 'hidden'):
                            uris_rem.append(t.track.uri)
                    #print (self.mopidyHandler.tracklist.get_tracks())
                    #if t.track.uri in self.mopidyHandler.tracklist.get_tracks().uri:uris_rem.append(t.track.uri)'''
            
            self.mopidyHandler.tracklist.remove({"uri": uris_rem})

            #Adding common and library tracks
            '''discover_level = self.get_option_for_tag(tag, "option_discover_level")
            limit = int(round(len(tltracks_added) * discover_level / 100))
            window = int(round(discover_level / 2))
            print(f"discover_level {discover_level} limit {limit} window {window}")
            if limit > 0: 
                uris2 = self.get_common_tracks(datetime.datetime.now().hour,window,limit)
                tltracks_added2 = self.mopidyHandler.tracklist.add(uris=uris2)
                tltracks_added.append(tltracks_added2)
                print (f"Adding common tracks : {uris2}")'''

            new_length = self.mopidyHandler.tracklist.get_length()
            print(f"Length {new_length}")

            # Shuffle new tracks if necessary : global shuffle or tag option : now in card 
            if (self.shuffle == "true" and tag.option_sort != "desc" and tag.option_sort != "asc") or tag.option_sort == "shuffle":
                self.shuffle_tracklist(prev_length, new_length)

            # Slice added tracks to max_results
            if (new_length - prev_length) > max_results:
                slice1 = self.mopidyHandler.tracklist.slice(prev_length + max_results, new_length)
                self.mopidyHandler.tracklist.remove(
                    {"tlid": [x.tlid for x in slice1]}
                )  # to be optimized ?

            # Update Tag Values : Tldis and Uris
            new_length = self.mopidyHandler.tracklist.get_length()
            slice2 = self.mopidyHandler.tracklist.slice(prev_length, new_length)
            print(f"Adding {new_length - prev_length} tracks")

            # TLIDs : Mopidy Tracks's IDs in tracklist associated to added Tag
            if hasattr(tag, "tlids"):
                tag.tlids += [x.tlid for x in slice2]
            else:
                tag.tlids = [x.tlid for x in slice2]
            #print("tag.tlids",tag.tlids)

            # Uris : Mopidy Uri's associated to added Tag
            if hasattr(tag, "uris"):
                tag.uris += [x.track.uri for x in slice2]
            else:
                tag.uris = [x.track.uri for x in slice2]
            #print("tag.uris",tag.uris)

            # Option types
            if hasattr(tag, "option_types"):
                tag.option_types += [tag.option_type for x in slice2]
            else:
                tag.option_types = [tag.option_type for x in slice2]
            #print("Option_types",tag.option_types)

            #library_link
            if hasattr(tag, "library_link"):
                tag.library_link += ['' for x in slice2]
            else:
                tag.library_link = ['' for x in slice2]
            #print("library_link",tag.library_link)

            # Shuffle complete computed tracklist if more than two tags
            if len(self.activetags) > 1:
                self.shuffle_tracklist(current_index + 1, new_length)
        print(f"\nTracks added to Tag {tag} with option_types {tag.option_types} and library_link {tag.library_link} \n")

 
    def play_or_resume(self):
        state = self.mopidyHandler.playback.get_state()
        if state == "stopped":
            if self.mopidyHandler.playback.get_current_tl_track() == None:
                #print("no current track : Playing first track")
                current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                if len(current_tracks) > 0:
                    self.mopidyHandler.playback.play(tlid=current_tracks[0].tlid)
            else:
                self.mopidyHandler.playback.play()
        elif state == "paused":
            self.mopidyHandler.playback.resume()
        """else:
            self.mopidyHandler.playback.next()"""

    # Vide la tracklist sauf la chanson en cours de lecture puis ajoute des uris à la suite
    @util.RateLimited(
        1
    )  # Limite l'execution de la fonction : une fois par seconde (à vérifier)
    def add_tracks_after(self, uris):
        print("ADDING SONGS SILENTLY IN TRACKLIST")
        self.clear_tracklist_except_current_song()
        self.mopidyHandler.tracklist.add(uris=uris)

    def clear_tracklist_except_current_song(self):
        all_tracklist_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
        current_tlid = self.mopidyHandler.playback.get_current_tlid()
        for (tlid, _) in all_tracklist_tracks:
            if tlid != current_tlid:
                self.mopidyHandler.tracklist.remove({"tlid": [tlid]})

#   SONGS RECOMMANDATION MANAGEMENT

    def add_reco_after_track_read(self, track_uri, library_link='', data=''):
        self.mopidyHandler.playback.pause()

        if "spotify:track" in track_uri:
            # tag associated & update discover_level
            discover_level = self.get_option_for_tag_uri(track_uri,"option_discover_level")
            if discover_level < 10: new_type ='new' 
            else: new_type = 'new_mopidy' #If max discover level, infinite loop of recommandations

            # Get tracks recommandations
            track_data = track_uri.split(":")  # on découpe l'uri' :
            track_seed = [track_data[2]]  # track id
            limit = int(round(discover_level * 0.25)) #Fixing number of new tracks


            choices = ['album','artist','reco']
            uris = []
            #Ponderation Album / Artist / Reco
            if 'album' in data:
                p = [0, 0.8, 0.2]
            else:
                p = [0.5, 0.3, 0.2]

            #Randomly ponderated type of track added
            for i in range(0, limit): 
                c=np.random.choice(choices,1,replace=False,p=p)
                new_uri = track_uri

                #1 : Same Album
                if c[0]=='album':
                    while new_uri == track_uri:
                        new_uri = self.get_same_album_tracks(track_uri, 1)
                    uris += new_uri
                
                #2 : Same Artist
                if c[0]=='artist':
                    while new_uri == track_uri:
                        new_uri = self.get_same_artist_tracks(track_uri, 1)
                    uris += new_uri

                #3 : Spotify Reco
                if c[0]=='reco':
                    while new_uri == track_uri:
                        new_uri = self.get_spotify_reco(track_seed, 1)
                    uris += new_uri

            # Calculate insertion index depending of discover_level
            tl_length = self.mopidyHandler.tracklist.get_length()
            if self.mopidyHandler.tracklist.index():
                current_index = self.mopidyHandler.tracklist.index()
            else:
                current_index = tl_length

            if discover_level > 5:
                new_index = current_index #adding reco just after track
            else:
                if 'album' in data:
                    new_index = tl_length
                else:
                    new_index = int(round(current_index+ ((tl_length - current_index) * (10 - discover_level) / 10)))

            if uris:
                slice = self.mopidyHandler.tracklist.add(uris=uris, at_position=new_index)
                # Updating tag infos
                # if 'tag' in locals():
                if slice:
                    try:
                        tag = self.get_active_tag_by_uri(track_uri)
                        print (f"Tag : {tag}")
                        if hasattr(tag, "tlids"):
                            tag.tlids += [x.tlid for x in slice]
                        else:
                            tag.tlids = [x.tlid for x in slice]
                        #print("Tag.tlids : ",tag.tlids)

                        if hasattr(tag, "uris"):
                            tag.uris += uris
                        else:
                            tag.uris = uris
                        #print("Tag.uris : ",tag.uris)

                        print("Tag : ",tag)
                        if hasattr(tag, "option_types"):
                            tag.option_types += [new_type for x in slice]
                        else:
                            tag.option_types = [new_type for x in slice]
                        #print("Option_types : ",tag.option_types)

                        #library_link
                        if hasattr(tag, "library_link"):
                            tag.library_link += [library_link for x in slice]
                        else:
                            tag.library_link = [library_link for x in slice]
                        #print("library_link",tag.library_link)
                        print(f"\nAdding reco new tracks at index {str(new_index)} with uris {uris} discover_level {discover_level} tag.option_types {tag.option_types} tag.library_link {tag.library_link} and tlid {slice[0].tlid}\n")

                    except Exception as e:
                        print(f"Erreur : {e}")
                    
                    print(f"\nAdding reco new tracks at index {str(new_index)} with uris {uris} & tlid {slice[0].tlid}\n")
                    
                    if new_index == current_index:
                        #playing a track added just forward (jumping a step ahead)
                        self.mopidyHandler.playback.play(None,slice[0].tlid)
                    else:
                        self.mopidyHandler.playback.play(None)

        self.play_or_resume()

#  TRACKS AND STATS MANAGEMENT

    def get_spotify_reco(self, track_seed, limit):
        uris = self.spotifyHandler.get_recommendations(
            seed_genres=None, seed_artists=None, seed_tracks=track_seed, limit=limit)
        return uris

    def get_same_artist_tracks(self, track_uri, limit):
        artist_id = self.spotifyHandler.get_track_artist(track_uri)
        uris = self.spotifyHandler.get_artist_all_tracks(artist_id, limit)
        return uris

    def get_same_album_tracks(self, track_uri, limit):
        album_uri = self.spotifyHandler.get_track_album(track_uri)
        uris = self.spotifyHandler.get_album_all_tracks(album_uri, limit)
        return uris

    def get_spotify_library(self,limit):
        return self.spotifyHandler.get_library_tracks(limit)

    def get_common_tracks(self,read_hour,window,limit):
        return self.dbHandler.get_stat_raw_by_hour(read_hour,window,limit)

    def add_playlistnew_tracks(self,limit):
        tag_new = self.dbHandler.get_tag_by_option_type('new')
        self.add_tracks(tag_new, limit)
        return True

    def get_active_tag_by_uri(self, uri):
        for tag in self.activetags:
            print (tag)
            if hasattr(tag, "uris"):
                if uri in tag.uris:
                    return tag
        
        mopidy_tag = self.dbHandler.get_tag_by_uid('mopidy_tag')
        mopidy_tag.uris = [uri]
        self.activetags.append(mopidy_tag)
        return mopidy_tag

    def get_option_for_tag_uri(self, uri, optionName):
        tag = self.get_active_tag_by_uri(uri)
        if tag is not None:
            attr = getattr(tag, optionName)
            if attr is not None:
                if attr != '':
                    return getattr(tag, optionName, None)
        return getattr(self, optionName, None)

    def get_option_for_tag(self, tag, optionName):
        if tag is not None:
            attr = getattr(tag, optionName)
            if attr is not None:
                if attr != '':
                    return getattr(tag, optionName, None)
        return getattr(self, optionName, None)

    def get_option_discover_level_for_tag(self, uri):
        tag = self.get_active_tag_by_uri(uri)
        if tag is not None:
            if tag.option_discover_level is not None:
                if tag.option_discover_level != '':
                    return tag.option_discover_level
        return self.option_discover_level


    # Track DB Regulation (tmp)
    def reg_stat_track(self, stat):
        if (stat.read_count - stat.read_count_end) > stat.skipped_count:
            stat.skipped_count = stat.read_count - stat.read_count_end
        if stat.read_count_end > 0 and (
            stat.day_time_average == None or stat.day_time_average == 0
        ):
            stat.day_time_average = stat.last_read_date.hour
        stat.update()
        stat.save()

    # Tag DB Regulation (tmp)
    def reg_tag_db(self, tag):
        if tag.option_type == '': tag.option_type='normal'
        tag.update()
        tag.save()

    # Update raw stat when finished, skipped or system stopped (if possible)
    def update_stat_raw(self, track):
        self.dbHandler.create_stat_raw(
            track.uri,
            datetime.datetime.utcnow(),
            datetime.datetime.now().hour,
            self.username
        )

    # Update tracks stat when finished, skipped or system stopped (if possible)
    def update_stat_track(self, track, pos=0, option_type='', library_link=''):
        #Harmonize option_type if new 
        if 'new' in option_type: option_type='new'

        #Get stats
        if self.dbHandler.stat_exists(track.uri):
            stat = self.dbHandler.get_stat_by_uri(track.uri)
        else:
            stat = self.dbHandler.create_stat(track.uri)

        stat.last_read_date = datetime.datetime.utcnow()
        stat.read_position = pos
        stat.read_count += 1
        stat.username = self.username

        #Avoid downgrade of option types in DB
        if not(option_type == 'new' and (stat.option_type == 'normal' or stat.option_type == 'favorites' or stat.option_type == 'incoming')):
            if not(option_type == 'normal' and (stat.option_type == 'favorites' or stat.option_type == 'incoming')):
                stat.option_type = option_type

        #Variable
        track_finished = False
        if hasattr(track, "length"):
            if pos / track.length > 0.9: track_finished = True
            if "podcast+" in track.uri and pos / track.length > 0.7: track_finished = True

        print(f"Track Finished : {track_finished}")

        #Update stats
        if track_finished:
            stat.read_end = True
            stat.read_count_end += 1
            if stat.read_count_end > 0 and stat.day_time_average != None:
                stat.day_time_average = (
                    datetime.datetime.now().hour
                    + stat.day_time_average * (stat.read_count_end - 1)
                ) / (stat.read_count_end)
            else:
                stat.day_time_average = datetime.datetime.now().hour
        else:
            if stat.read_end != True:
                stat.read_end = False
            stat.skipped_count += 1

        #Add / remove the track to playlist(s) if played above/below discover level
        if self.option_autofill_playlists == True:
            uri = []
            uri.append(track.uri)
            print("Autofill activated")

            if track_finished == True :
                #Adding if "new track" played many times
                if stat.option_type == 'new' and self.threshold_playing_count_new(stat.read_count_end,self.option_discover_level)==True :
                    if library_link !='':
                        print(f"Autofilling LL : {library_link}")
                        result = self.autofill_spotify_playlist(library_link,uri)
                        if result: stat.option_type = 'normal'

                    if stat.option_type != 'normal' :
                        tag_incoming = self.dbHandler.get_tag_by_option_type('incoming')
                        print(f"Autofilling TI : {tag_incoming}")
                        if tag_incoming:
                            if 'spotify:playlist' in tag_incoming.data: 
                                result = self.autofill_spotify_playlist(tag_incoming.data,uri)
                                if result: stat.option_type = 'incoming'
                            if 'm3u' in tag_incoming.data :
                                playlist = self.mopidyHandler.playlists.lookup(tag_incoming.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result: stat.option_type = 'incoming'

                        '''for tag in self.activetags:
                            #Need to loop on the playlists IN the tag/card
                            discover_level_tag = self.get_option_for_tag(tag, "option_discover_level")
                            if tag.option_type == 'normal' and self.threshold_playing_count_new(stat.read_count_end,discover_level_tag)==True :
                                if 'spotify:playlist' in tag.data :
                                    result = self.autofill_spotify_playlist(tag.data,uri)
                                    if result: stat.option_type = 'normal'
                                if 'm3u' in tag.data :
                                    playlist = self.mopidyHandler.playlists.lookup(tag.data)
                                    #for track in playlist.tracks:
                                    #    if 'spotify:playlist' in track.uri :
                                    #        result = self.autofill_spotify_playlist(track.uri,uri)
                                    #        if result: stat.option_type = 'normal'
                                    if 'spotify:playlist' in playlist.tracks[0].uri :
                                        result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                        if result: stat.option_type = 'normal'
                        '''

                #Adding any track to incoming if played many times
                if self.threshold_adding_favorites(stat.read_count_end,self.option_discover_level)==True :
                    tag_favorites = self.dbHandler.get_tag_by_option_type('favorites')
                    print(f"Autofilling TF : {tag_favorites}")
                    if tag_favorites:
                        if 'spotify:playlist' in tag_favorites.data: 
                            result = self.autofill_spotify_playlist(tag_favorites.data,uri)
                            if result: stat.option_type = 'favorites'
                        if 'm3u' in tag_favorites.data :
                            playlist = self.mopidyHandler.playlists.lookup(tag_favorites.data)
                            #for track in playlist.tracks:
                            #    if 'spotify:playlist' in track.uri :
                            #        result = self.autofill_spotify_playlist(track.uri,uri)
                            #        if result: stat.option_type = 'favorites'
                            if 'spotify:playlist' in playlist.tracks[0].uri :
                                result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                if result: stat.option_type = 'favorites'

            else:
                #Remove track from playlist if skipped many times
                if self.threshold_count_deletion(stat,self.option_discover_level)==True :
                    '''and library_link !='''
                    print (f"Trashing track {stat.skipped_count} {self.option_discover_level}")
                    tag_trash = self.dbHandler.get_tag_by_option_type('trash')
                    if tag_trash:
                        if 'spotify:playlist' in tag_trash.data: 
                            result = self.autofill_spotify_playlist(tag_trash.data,uri)
                            if result: 
                                #self.spotifyHandler.remove_tracks_playlist(library_link, uri)
                                stat.option_type = 'hidden'
                        if 'm3u' in tag_trash.data :
                            playlist = self.mopidyHandler.playlists.lookup(tag_trash.data)
                            for track in playlist.tracks:
                                if 'spotify:playlist' in track.uri :
                                    result = self.autofill_spotify_playlist(tag_trash,uri)
                                    if result:  
                                        #self.spotifyHandler.remove_tracks_playlist(track.uri, uri)
                                        stat.option_type = 'hidden'


        print(f"\nUpdate stat track {stat}\n")
        stat.update()
        stat.save()

    

    # Auto Filling playlist 
    def autofill_spotify_playlist(self, playlist_uri,uri):
        try: 
            self.autofill_spotify_playlist_action(playlist_uri,uri)
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            self.spotifyHandler.init_token_sp() #pb of expired token to resolve...
            self.autofill_spotify_playlist_action(playlist_uri,uri)

    def autofill_spotify_playlist_action(self, playlist_uri,uri):
        #Toadd : test if writable
        if 'spotify:playlist' in playlist_uri and 'spotify:track' in uri:
            playlist_id = playlist_uri.split(":")[2]
            track_id = uri[0].split(":")[2]
            if self.spotifyHandler.is_track_in_playlist(self.username,track_id,playlist_id) == False:
                print (f"Auto Filling playlist with self.username: {self.username}, playlist: {playlist_uri}, track.uri: {uri}")
                result = self.spotifyHandler.add_tracks_playlist(self.username, playlist_uri, uri)
            else: result = 'already in'
            return (result)
        else: print(f"Erreur : autofill, playlist_uri : {playlist_uri}")
            
#   THRESHOLDs MANAGEMENT

    #Threshold for stopping playing and autofilling new tracks (add_tracks or autofill)
    #discover_level = 5 : read_count_end>=3
    def threshold_playing_count_new(self,read_count_end,option_discover_level):
        #print (f"read_count_end : {read_count_end} option_discover_level : {option_discover_level}")
        if float(read_count_end) >= ((11-option_discover_level)/2): return True
        else: return False

    #Threshold for adding tracks to favorites (autofill)
    #Need to integrate global ratio, not pertinent now
    #discover_level = 5 : read_count_end>=12
    def threshold_adding_favorites(self,read_count_end,option_discover_level):
        '''if float(read_count_end) >= ((11-option_discover_level)*2): return True
        else: return False'''
        return False


    #Threshold for deleting tracks from playlist if too many skipped
    #discover_level = 5 et read_count_end=0 : skipped_count_end >=5
    def threshold_count_deletion(self,stat,option_discover_level):
        if float(stat.skipped_count) > ((11-option_discover_level)*(stat.read_count_end+1)*0.7): 
            return True 
        else: 
            return False

#   WIP

    # Appelle ou rappelle la fonction de recommandation pour allonger la tracklist et poursuivre la lecture de manière transparente
    def update_tracks(self):
        print("should update tracks")

    # Pour le debug, print en console dans le détail les tags détectés et retirés
    # TODO : Déplacer dans la partie NFCreader, plus très utile ici ?
    def pretty_print_nfc_data(self, addedCards, removedCards):
        print("-------")
        print("NFC TAGS CHANGED!")
        print(
            "COUNT : \n     ADDED : {}  \n     REMOVED : {} ".format(
                len(addedCards), len(removedCards)
            )
        )
        print("ACTIONS : ")
        print(
            "     ADDED : {} \n     REMOVED : {}".format(
                [x.reader + " : " + x.id for x in addedCards],
                [x.reader + " : " + x.id for x in removedCards],
            )
        )

        print("CURRENT CARDS ACTIVED : ")
        for key, card in self.activecards.items():
            print("     Reader : {} with card : {} ".format(key, card.id))
        print("-------")
