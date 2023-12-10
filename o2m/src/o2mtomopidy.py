import datetime, sys, contextlib, random
import numpy as np
from mopidy_podcast import Extension, feeds
from urllib import parse

import src.util as util
from src.dbhandler import DatabaseHandler, Stats, Stats_Raw, Box
from src.spotifyhandler import SpotifyHandler

'''
option_type 
- normal
- favorites
- new
- incoming
- hidden
- trash
- podcast
'''

class O2mToMopidy:
    activecards = {}
    activeboxs = []
    last_box_uid = None

    suffle = False
    max_results = 50
    default_volume = 70  # 0-100
    discover_level = 5  # 0-10
    podcast_newest_first = False
    option_sort = "desc"

    def __init__(self, mopidyHandler, configO2m, configMopidy, logging):
        self.configO2M = configO2m["o2m"]
        #self.configMopidy = configMopidy
        self.dbHandler = DatabaseHandler()  # Database management
        self.mopidyHandler = mopidyHandler  # Websocket mopidy for reading control
        self.spotifyHandler = SpotifyHandler() # Spotify API 

        if "api_result_limit" in self.configO2M:
            self.max_results = int(self.configO2M["api_result_limit"])

        if "default_volume" in self.configO2M:
            self.default_volume = int(self.configO2M["default_volume"])
        self.current_volume = self.default_volume

        if "discover_level" in self.configO2M:
            self.discover_level = int(self.configO2M["discover_level"])
        #Wether discover_level is on from the outside (api) or not
        self.discover_level_on = False

        if "podcast_newest_first" in self.configO2M:
            self.podcast_newest_first = self.configO2M["podcast_newest_first"] 

        if "option_sort" in self.configO2M:
            self.option_sort = self.configO2M["option_sort"] 

        if "option_autofill_playlists" in self.configO2M:
            self.option_autofill_playlists = bool(self.configO2M["option_autofill_playlists"])
        else: self.option_autofill_playlists = False

        if "option_add_reco_after_track" in self.configO2M:
            self.option_add_reco_after_track = bool(self.configO2M["option_add_reco_after_track"])
        else: self.option_add_reco_after_track = False

        if "shuffle" in self.configO2M:
            self.shuffle = bool(self.configO2M["shuffle"]) 

        if "username" in configO2m["spotify"]:
            self.username = configO2m["spotify"]["username"] 

        if "enabled" in configO2m["local"]:
            self.local = bool(configO2m["local"]["enabled"])

        if "default_box" in self.configO2M:
            self.default_box = self.configO2M["default_box"]

        if "fix_stats" in self.configO2M:
            self.fix_stats = self.configO2M["fix_stats"]

        self.starting_mode(clear=True)

#TAG MANAGEMENT

    def box_action(self,box):
        if self.configO2M["discover"] == "true":
            try: 
                self.active_boxs_changed()
            except Exception as val_e: 
                print(f"Erreur : {val_e}")
                self.spotifyHandler.init_token_sp() #pb of expired token to resolve...
                #self.active_boxs_changed()
        else:
            try: 
                self.one_box_changed(box)
            except Exception as val_e: 
                print(f"Erreur : {val_e}")
                self.spotifyHandler.init_token_sp() #pb of expired token to resolve...
                #self.one_box_changed(box)

    def box_action_remove(self,box,removedBox):
        if len(self.activeboxs) == 0:
                self.starting_mode(True)
                # print('Stopping music')
                '''self.update_stat_track(
                    self.mopidyHandler.playback.get_current_track(),
                    self.mopidyHandler.playback.get_time_position()
                )'''
        elif removedBox.tlids != None:
            #Compute NewTlid (after track removing)
            current_tlid = self.mopidyHandler.playback.get_current_tlid()
            last_tlindex = self.mopidyHandler.tracklist.index()

            if current_tlid in removedBox.tlids:
                self.update_stat_track(
                    self.mopidyHandler.playback.get_current_track(),
                    self.mopidyHandler.playback.get_time_position()
                )
                self.mopidyHandler.playback.stop()

                current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                current_tlids = [ sub.tlid for sub in current_tracks ]

                #Looping on active tracks
                for i in current_tlids[last_tlindex:]:
                    if i not in removedBox.tlids:
                        next_tlid = i
                        break
            else:
                next_tlid = current_tlid
                            
            #Removing tracks from playslist
            self.mopidyHandler.tracklist.remove({"tlid": removedBox.tlids})

            if current_tlid in removedBox.tlids and next_tlid!=None:
                self.mopidyHandler.playback.play(tlid=next_tlid)

        else:
            print("no uris with removed box")

    """
    Daemon function called when change in active boxes
    """

    def active_boxs_changed(self):
        seeds_genres = []
        seeds_artists = []
        seeds_tracks = []
        # local_uris = []
        for box in self.activeboxs:
            if "genre:" in box.data:
                seeds_genres += self.parse_box_data(box.data)
            elif "spotify:artist:" in box.data:
                seeds_artists += self.parse_box_data(box.data)
            elif "spotify:album:" in box.data:
                print(
                    "spotify album not ready yet : need to get all tracks of album or playlist then feed the seed"
                )
            # else:
            # si le box non compatible -> récupérer les utis et les ajouter à local_uris

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

    def parse_box_data(self, data):
        data_string = data.split(":")[-1]
        return data_string.split(",")

    """
    Function called when a new box is detected and operating in remote control mode
     A box -> an action -> a set of content:
         Recommendations:
             - Genres: Recommendation on the genre(s) included in the box
             - Artists: Recommendation on the artist(s) ...
         m3u: Hybrid playlist parsing
         spotify:
             - artist: Top tracks or all tracks of the artist
             - scrapbook
             - track
         local :
             - artist
             - scrapbook
             - track
         podcast:
             - show
             - channel / album
    """

#O2M CORE / TRACKLIST INIT 
    def one_box_changed(self, box, max_results=15):
        #print(f"\nNouveau box détecté: {box}")
        if (box.uid != self.last_box_uid):  # Si différent du précédent box détecté (Fonctionnel uniquement avec un lecteur)
            uri = "box:"+box.uid
            self.update_stat_raw(uri)

            # Variables
            if max_results==15:
                max_results = self.max_results
                if box.option_max_results: max_results = box.option_max_results
                #print (f"Max results : {max_results}")
            
            tracklist_uris = self.tracklistappend_box(box,max_results)
            print (tracklist_uris)

            #Let's go to play
            if len(tracklist_uris)>0:
                #max_results to be recalculated function of subadding already done (content var)
                length = self.add_tracks(box, tracklist_uris, max_results) # Envoie les uris en lecture

                #Shuffle if several entries in this action
                if ((self.shuffle == "true" and box.option_sort != "desc" and box.option_sort != "asc") or box.option_sort == "shuffle") and (length>0):
                    index = 0
                    if self.mopidyHandler.tracklist.index() != None: index = int(self.mopidyHandler.tracklist.index())
                    length = self.mopidyHandler.tracklist.get_length()
                    self.shuffle_tracklist(index+1,length)

        # Next option
        else:
            print(f"Box : {box.uid} & last_box_uid : {self.last_box_uid}")
            self.launch_next()  # Le box détecté est aussi le dernier détecté donc on passe à la chanson suivante
            return

        if self.mopidyHandler.tracklist.get_length() > 0:
            self.play_or_resume()

    def quicklaunch_auto(self,max_results=1,discover_level=5,box=None):
        window = int(round(discover_level / 2))
        if box == None:
            box = self.dbHandler.get_box_by_option_type('new_mopidy')
        #Common tracks :launch quickly auto with one track
        self.add_tracks(box, self.get_common_tracks(datetime.datetime.now().hour,window,max_results), max_results)
        self.play_or_resume()


#TRACKLIST FILL / ADD
    # Adding tracks to tracklist and associate them to tracks table
    def add_tracks(self, box, uris, max_results=15):
        length = 0
        if len(uris) > 0:
            uris = util.flatten_list(uris)
            if None in uris:
                uris.remove(None)
            if "None" in uris:
                uris.remove("None")
            print (uris)
            prev_length = self.mopidyHandler.tracklist.get_length()
            if self.mopidyHandler.tracklist.index():
                current_index = self.mopidyHandler.tracklist.index()
            else: 
                current_index = 0 
            tltracks_added = self.mopidyHandler.tracklist.add(uris=uris)
            length = len(tltracks_added)
            print (f"Lenght added {len(tltracks_added)}")
            if len(tltracks_added)>0:
                uris_rem = []
                # Exclude tracks already read when option is new
                #Too long > to be replaced by a trashing action along playing
                if box.option_type == 'new':
                    for t in tltracks_added:
                        if self.dbHandler.stat_exists(t.track.uri):
                            stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                            # When track skipped or too many counts we remove them
                            if (stat.skipped_count > 0
                                or stat.in_library == 1
                                or (stat.option_type == 'trash' or stat.option_type == 'hidden' or stat.option_type == 'normal' or stat.option_type == 'incoming')
                                or self.threshold_playing_count_new(stat.read_count_end-1,self.discover_level) == True
                                #or (stat.option_type != 'new' and stat.option_type != '' and stat.option_type != 'trash' and stat.option_type != 'hidden')
                            ): 
                                uris_rem.append(t.track.uri)
                        #Removing double tracks in trackslit
                        #if t.track.uri in self.mopidyHandler.tracklist.get_tracks().uri:uris_rem.append(t.track.uri)

                else:
                    #Removing trash and hidden : too long
                    for t in tltracks_added:
                        #Option_type fixing (to be improved)
                        if self.fix_stats==True: self.update_stat_track(t.track,0,box.option_type,'',True)
                        
                        '''if self.dbHandler.stat_exists(t.track.uri):
                            stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                            if (stat.option_type == 'trash' or stat.option_type == 'hidden'):
                                uris_rem.append(t.track.uri)'''

                        #print (self.mopidyHandler.tracklist.get_tracks())
                        #Removing double tracks in trackslit
                        #if t.track.uri in self.mopidyHandler.tracklist.get_tracks().uri:uris_rem.append(t.track.uri)

                self.mopidyHandler.tracklist.remove({"uri": uris_rem})

                #Adding common and library tracks
                '''discover_level = self.get_option_for_box(box, "option_discover_level")
                limit = int(round(len(tltracks_added) * discover_level / 100))
                window = int(round(discover_level / 2))
                print(f"discover_level {discover_level} limit {limit} window {window}")
                if limit > 0: 
                    uris2 = self.get_common_tracks(datetime.datetime.now().hour,window,limit)
                    tltracks_added2 = self.mopidyHandler.tracklist.add(uris=uris2)
                    tltracks_added.append(tltracks_added2)
                    print (f"Adding common tracks : {uris2}")'''

                new_length = self.mopidyHandler.tracklist.get_length()
                #print(f"Length {new_length}")

                # Shuffle new tracks if necessary : global shuffle or box option : now in card 
                if (self.shuffle == "true" and box.option_sort != "desc" and box.option_sort != "asc") or box.option_sort == "shuffle":
                    self.shuffle_tracklist(prev_length, new_length)

                # Slice added tracks to max_results
                if (new_length - prev_length) > max_results:
                    slice1 = self.mopidyHandler.tracklist.slice(prev_length + max_results, new_length)
                    self.mopidyHandler.tracklist.remove(
                        {"tlid": [x.tlid for x in slice1]}
                    )  # to be optimized ?

                # Update Box Values : Tldis and Uris
                new_length = self.mopidyHandler.tracklist.get_length()
                slice2 = self.mopidyHandler.tracklist.slice(prev_length, new_length)
                #print(f"Adding {new_length - prev_length} tracks")

                # TLIDs : Mopidy Tracks's IDs in tracklist associated to added Box
                if hasattr(box, "tlids"):
                    box.tlids += [x.tlid for x in slice2]
                else:
                    box.tlids = [x.tlid for x in slice2]
                #print("box.tlids",box.tlids)

                # Uris : Mopidy Uri's associated to added Box
                if hasattr(box, "uris"):
                    box.uris += [x.track.uri for x in slice2]
                else:
                    box.uris = [x.track.uri for x in slice2]
                #print("box.uris",box.uris)

                # Option types
                if hasattr(box, "option_types"):
                    box.option_types += [box.option_type for x in slice2]
                else:
                    box.option_types = [box.option_type for x in slice2]
                #print("Option_types",box.option_types)

                #library_link
                if hasattr(box, "library_link"):
                    box.library_link += ['' for x in slice2]
                else:
                    box.library_link = ['' for x in slice2]
                #print("library_link",box.library_link)

                # Shuffle complete computed tracklist if more than two boxs
                self.shuffle_tracklist(current_index + 1, new_length)
                '''if len(self.activeboxs) > 1:
                    self.shuffle_tracklist(current_index + 1, new_length)'''
            #print(f"\nTracks added to Box {box} with option_types {box.option_types} and library_link {box.library_link} \n")
        return (length)

    def tracklistfill_auto0(self,box,max_results=20,discover_level=5,mode='full'):
        print (f"DL AUTO : {discover_level}")
        #GO QUICKLY
        self.quicklaunch_auto(1,discover_level)    

        #Variables
        window = int(round(discover_level / 2))
        #box = self.dbHandler.get_box_by_option_type('new_mopidy')
        #box.option_type == 'normal'
        tracklist_uris= []

        #Common tracks n=(-0.3*d+8)/30
        max_result1 = int(round((-0.3*discover_level+8)/30*max_results))
        print(f"\nAUTO : Common {max_result1} tracks\n")
        #tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
        box.option_type == 'new'
        uris = self.get_common_tracks(datetime.datetime.now().hour,window,max_result1)
        self.add_tracks(box, uris, max_result1)

        #self.add_tracks(box, tracklist_uris, max_results)

        #return tracklist_uris

    def tracklistfill_auto(self,box,max_results=20,discover_level=5,mode='normal'):
        try:
            print (f"DL AUTO : {discover_level}")
            #GO QUICKLY
            self.quicklaunch_auto(1,discover_level,box)

            #Variables
            window = int(round(discover_level / 2))
            #box = self.dbHandler.get_box_by_option_type('new_mopidy')
            #box.option_type == 'normal'
            tracklist_uris= []

            #ADD_TRACKS
            #News n=(0.5*d)/30
            max_result1 = int(round((0.7*discover_level)/30*max_results))
            print(f"\nAUTO : News {max_result1} tracks\n")
            box1 = self.dbHandler.get_box_by_option_type('new')
            #self.one_box_changed(box, max_result1)
            self.add_tracks(box, self.tracklistappend_box(box1,max_result1), max_result1)
            #tracklist_uris.append(self.tracklistappend_box(box,max_result1))        
            
            #Incoming n=(0.5*d)/30
            max_result1 = int(round((0.7*discover_level)/30*max_results))
            print(f"\nAUTO : Incoming {max_result1} tracks\n")
            box1 = self.dbHandler.get_box_by_option_type('incoming')
            #self.one_box_changed(box, max_result1)
            self.add_tracks(box, self.tracklistappend_box(box1,max_result1), max_result1)
            #tracklist_uris.append(self.tracklistappend_box(box,max_result1))  

            #Favorites n=5/30
            max_result1 = int(round((-0.3*discover_level+8)/30*max_results))
            print(f"\nAUTO : Fav {max_result1} tracks\n")
            box1 = self.dbHandler.get_box_by_option_type('favorites')
            if box1 != None:
                #box=box1
                fav= self.tracklistappend_box(box1,max_result1)
            else:
                fav = self.spotifyHandler.get_library_favorite_tracks(max_result1)
            self.add_tracks(box, fav, max_result1)
            #tracklist_uris.append(self.tracklistappend_box(box,max_result1))

            if mode=='podcast':
                #Podcasts ??? n=(0.5*d)/30
                max_result1 = int(round((0.9*discover_level)/30*max_results))
                print(f"\nAUTO : Podcasts {max_result1} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('podcast')
                #self.one_box_changed(box, max_result1)
                if box1:
                    self.add_tracks(box, self.tracklistappend_box(box1,max_result1), max_result1)
                #tracklist_uris.append(self.tracklistappend_box(box,max_result1))

            #INFOS
            box.option_type == 'podcast'
            box.option_sort == 'desc'
            self.add_tracks(box, self.lastinfos(box,max_results), 1)

            #APPEND
            #Common tracks n=(-0.3*d+8)/30
            max_result1 = int(round((-0.3*discover_level+8)/30*max_results))
            print(f"\nAUTO : Common {max_result1} tracks\n")
            #tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
            box.option_type == 'new'
            self.add_tracks(box, self.get_common_tracks(datetime.datetime.now().hour,window,max_result1), max_result1)
            #self.add_tracks(box, tracklist_uris, max_results)

            #Albums n=5/30
            max_result1 = int(round(discover_level*2/30*max_results))
            print(f"\nAUTO : Albums {max_result1} tracks\n")
            #tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(max_result1,discover_level))
            self.add_tracks(box, self.spotifyHandler.get_my_albums_tracks(max_result1,discover_level), max_result1)

            #Playlists n=(-0.2*d+7)/30
            max_result1 = int(round((-0.2*discover_level+7)/30*max_results))
            print(f"\nAUTO : Playlist {max_result1} tracks\n")
            #tracklist_uris.append(self.spotifyHandler.get_playlists_tracks(max_result1,discover_level))
            self.add_tracks(box, self.spotifyHandler.get_playlists_tracks(max_result1,discover_level), max_result1)


            #return tracklist_uris
        except Exception as val_e: 
            print(f"Erreur : {val_e}")

#TRACKLIST APPEND / MANAGEMENT 
    
    #Tracklist filling from box
    def tracklistappend_box(self,box,max_results):
        #Variables
        tracklist_uris = []
        
        #If discover level has been pushed by api since the begining of session, we priorise it
        if self.discover_level_on:
            discover_level = self.discover_level
        else:
            discover_level = self.get_option_for_box(box, "option_discover_level")
        
        '''
        #Temporary hack because of spotify pb
        if "spotify" in box.data:
            media_parts = box.data.split(":")  #on découpe le champs média du box en utilisant le séparateur :
            data = box.data
        else:
            media_parts = box.data.split(":")  #on découpe le champs média du box en utilisant le séparateur :
            data = box.data
        #print (media_parts)
        '''

        #DB Regulation (tmp)
        #self.reg_box_db(box)
        content = 0

        # Looping on hybrid playlist (delimited by \n)
        data = box.data.split("\n")
        data = data.split("\r")
        data = [x for x in data if not x.startswith('#')]
        data = [x for x in data if not x.startswith('\r')]

        for content in data:
            # Recommandation
            if "recommendation" in content:
                media_parts = content.split(":")
                if media_parts[3] == "genres":  # si les seeds sont des genres
                    genres = media_parts[4].split(",")  # on sépare les genres et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(seed_genres=genres, limit=max_results)  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    #self.add_tracks(box, tracks_uris, max_results)  # Envoie les uris au mopidy Handler pour modifier la tracklist
                    tracklist_uris.append(tracks_uris)
                elif media_parts[3] == "artists":  # si les seeds sont des artistes
                    artists = media_parts[4].split(",")  # on sépare les artistes et on les ajoute un par un dans une liste
                    tracks_uris = self.spotifyHandler.get_recommendations(seed_artists=artists, limit=max_results)  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                    #self.add_tracks(box, tracks_uris, max_results)  # Envoie les uris au mopidy Handler pour modifier la tracklist
                    tracklist_uris.append(tracks_uris)

            # here&now:library (daily habits + library auto extract)
            elif "herenow:library" in content :
                window = int(round(discover_level / 2))
                max_result1 = int(round(max_results/2))
                tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
                tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(max_result1,1))
                #tracklist_uris.append(self.get_spotify_library(max_result1))
                #print(f"Adding herenow : {tracklist_uris} tracks")

            # auto:library testing (daily habits + library auto extract)
            elif "auto:library" in content :
                tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level))

            # auto:library testing (daily habits + library auto extract)
            elif "auto_podcast:library" in content :
                tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level,'podcast'))

            # spotify:library (library random extract)
            elif "spotify:library" in content :
                print ("spotify:library")
                max_result1 = int(round(max_results/3))
                tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(2*max_result1,1))
                #tracklist_uris.append(self.get_spotify_library(2*max_results1))
                tracklist_uris.append(self.spotifyHandler.get_library_favorite_tracks(max_result1))
                #tracklist_uris.append(self.spotifyHandler.get_library_recent_tracks(max_results))

            # now:library (daily habits)
            elif "now:library" in content :
                print ("now:library")
                window = int(round(discover_level / 2))
                tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_results))

            # infos:library (more recent news podcasts (to be updated))
            elif "infos:library" in content :
                tracklist_uris.append(self.lastinfos(box,max_results))

            # newnotcompleted:library (adding new tracks only played once)
            elif "newnotcompleted:library" in content :
                uri_new = self.get_new_tracks_notread(max_results)
                if len(uri_new)>0:
                    #tracklist_uris.append(uri_new)
                    tracklist_uris.append(uri_new)
                    #print(f"Adding : {uri_new} tracks")
            
            # album:local 
            elif "albums:local" in content :
                #list_album = self.mopidyHandler.library.search({'album': ['a']})
                list_album = self.mopidyHandler.library.get_distinct("albumartist")
                print(f"List albums{list_album}")
                random.shuffle(list_album)
                list_album = list_album[0]['id']
                print(f"List albums{list_album}")
                #list_album = list_album[0]['id']
                if len(list_album)>0:
                    tracklist_uris.append(uri_new)
                    #self.add_tracks(box, uri_new, max_results) # Envoie les uris en lecture
                    print(f"Adding : {uri_new} tracks")
                    content += 1

            # album:spotify 
            elif "albums:spotify" in content :
                if (random.choice([1,2])) == 1:
                    tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(1,0))
                else:
                    tracklist_uris.append(self.spotifyHandler.get_my_artists_tracks(1,0))

            # Autos mode (to be optimized with the above code)
            elif "auto:library" in content:
                tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level))

            elif "auto_simple:library" in content:
                tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level,'simple'))

            elif "infos:library" in content:
                tracklist_uris.append(self.lastinfos(box,max_results))

            # Unfinished podcasts
            elif "podcasts:unfinished" in content:
                uris = self.dbHandler.get_uris_podcasts_notread(max_results)
                if uris is not None:
                    tracklist_uris.append(uris)

            # Podcast channel
            elif "podcast" in content and "#" not in content:
                print(f"Podcast : {content}")
                self.update_stat_raw(content)
                #self.add_podcast_from_channel(box,content,max_results)
                tracklist_uris.append(self.add_podcast_from_channel(box,content,max_results))
                # On doit rechercher un index de dernier épisode lu dans une bdd de statistiques puis lancer les épisodes non lus
                # tracklist_uris += self.get_unread_podcasts(shows)

            # Podcast episode
            elif "podcast" in content and "#" in content:
                feedurl = content.split("+")[1]
                tracklist_uris.append(self.get_podcast_from_url(feedurl))

            # Podcast:channel
            elif "podcasts:channel" in box.data:
                self.update_stat_raw(box.data)
                #self.add_podcast_from_channel(box,content,max_results)
                tracklist_uris.append(self.add_podcast_from_channel(box,box.data,max_results))    

            # Spotify
            elif "spotify" in content:
                #print ([data])
                #self.update_stat_raw([data])
                media_parts = content.split(":")
                if media_parts[1] == "artist":
                    tracks_uris = self.spotifyHandler.get_artist_top_tracks(media_parts[2])  # 10 tops tracks of artist
                    #self.add_tracks(box, tracks_uris, max_results)
                    tracklist_uris.append(self.spotifyHandler.get_artist_all_tracks(media_parts[2], limit=max_results - 10))  # all tracks of artist with no specific order
                else:
                    tracklist_uris.append(content)        

            # Other contents in the playlist
            else : 
                if "playlist" in content: self.update_stat_raw(content)
                tracklist_uris.append(content)  # Recupère l'uri de chaque track pour l'ajouter dans une liste

        #print (f"AUTO : Box : {tracklist_uris}")
        #tracklist_uris = util.flatten_list(tracklist_uris)

        return tracklist_uris  

    def lastinfos(self,box,max_results):
        hour = datetime.datetime.now().hour
        minute = datetime.datetime.now().minute
        day = datetime.datetime.today().weekday() #0 : Monday - 6 : Sunday
        print (f"infos:library {day} {hour} {minute}")
        #Week
        if day < 5:
            if hour <= 7 : info_url = "rss_10055.xml" #FC 7h
            if hour ==8 and minute <= 20 : info_url = "rss_10055.xml" #FC 7h30
            if (hour == 8 and minute > 20) or (hour >=9 and hour < 14) : info_url = "rss_12495.xml" #FI 8h
            #if hour >= 10 and hour < 14: info_url= "rss_12735.xml" #FI 9h
            if hour >= 14 and hour < 19: info_url = "rss_11673.xml" #FI 13h
            if (hour == 18 and minute > 20): info_url = "rss_11731.xml" #FI 18h
            if (hour == 19 and minute > 20) or hour >= 20 : info_url = "rss_11736.xml" #FI 19h
            if hour < 8 and day == 0: info_url = "rss_18911.xml" #FI Week end 19h
        #Week-end
        else:
            if (hour >= 10 and hour < 14) or (hour == 9 and minute >= 25): info_url= "rss_12735.xml" #FI 9h
            if hour >= 14 and hour < 19: info_url = "rss_18909.xml" #FI Week end 13h
            if ((hour == 18 and minute > 20) and hour < 20) or (hour <= 9 and day == 6): info_url = "rss_18910.xml" #FI Week end 18h
            if (hour == 19 and minute > 20)  or (hour <= 9 and minute < 25) or hour > 19: info_url = "rss_18911.xml" #FI Week end 19h
            if (hour <= 9 and minute < 25 and day == 5): info_url = "rss_11736.xml" #FI 19h

        try:
            info_url = "podcast+https://radiofrance-podcast.net/podcast09/" + info_url + "?max_results=1"
            tracklist_uris = self.add_podcast_from_channel(box,info_url, max_results)
            return tracklist_uris
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            #return []

    def add_podcast_from_channel(self,box,uri, max_results):
        feedurl = uri.split("+")[1]
        par = parse.parse_qs(parse.urlparse(feedurl).query)
        if 'max_results' in par : max_results_pod = int(par['max_results'][0])
        else : max_results_pod = max_results
        #volume=parse.parse_qs(parse.urlparse(feedurl).query)['volume'][0]

        shows = self.get_unread_podcasts(uri, 0, max_results_pod)
        #print(f'Shows : {shows}')
        #print(f'max_results_pod : {max_results_pod}')
        #self.add_tracks(box, shows, max_results_pod)
        return shows

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

    def get_unread_podcasts(self, data, last_track_played, max_results=15):
        uris = []
        feedurl = data.split("+")[1]

        shows = self.get_podcast_from_url(feedurl)
        unread_shows = shows[last_track_played:]  # Remove n first shows already read (to be checked not used anymore)
        unread_shows = shows[:max_results]  # Cut to max results (to be suppressed if grabbing later than first tracks)
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

    def get_unfinished_podcasts(self, max_results=15):
        uris = []
        self.dbHandler.get_unfinished_pattern("")
        #shows = self.get_podcast_from_url(self.uri)
        '''for item in shows:
            if self.dbHandler.get_end_stat(item.uri) == 0:
                uris.append(item.uri)'''
        return uris

#MOPIDY LIVE CONTROL 
    def starting_mode(self,clear=False,start=False,uid=None):
        #Cleaning 
        if clear == True: 
            self.mopidyHandler.tracklist.clear()
            self.mopidyHandler.playback.stop()
            for box in self.activeboxs:
                box.tlids.clear()
                box.uris.clear()
                box.option_types.clear()
                box.library_link.clear()

        # Default volume setting at beginning (or in main ?)
        self.mopidyHandler.tracklist.set_random(False)
        self.mopidyHandler.mixer.set_mute(False)
        self.mopidyHandler.mixer.set_volume(self.default_volume)

        #Restart with active boxs if actived
        if start == True: 
            for box in self.activeboxs:
                self.box_action(box)
            if uid != None:
                box = self.dbHandler.get_box_by_uid(uid)
                if box != None:
                    self.activeboxs.append(box)
                    self.box_action(box)

    # Launch next song
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
        if self.option_add_reco_after_track: 
            #self.mopidyHandler.playback.pause()

            if "spotify:track" in track_uri:
                # Calculate the discover_level : box associated or updated discover_level via api
                if self.discover_level_on:
                    discover_level = self.discover_level
                else:
                    discover_level = self.get_option_for_box_uri(track_uri,"option_discover_level")
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
                
                new_index = current_index 
                if discover_level ==10:
                    new_index = current_index #adding reco just after track
                else:
                    if 'album' in data:
                        new_index = tl_length #at the end
                    else:
                        new_index = int(round(current_index+ ((tl_length - current_index) * (10 - discover_level) / 10))) #somewhere in the middle of the tracklist

                if uris:
                    slice = self.mopidyHandler.tracklist.add(uris=uris, at_position=new_index)
                    # Updating box infos
                    # if 'box' in locals():
                    if slice:
                        try:
                            box = self.get_active_box_by_uri(track_uri)
                            #print (f"Box : {box}")
                            if hasattr(box, "tlids"):
                                box.tlids += [x.tlid for x in slice]
                            else:
                                box.tlids = [x.tlid for x in slice]
                            #print("Box.tlids : ",box.tlids)

                            if hasattr(box, "uris"):
                                box.uris += uris
                            else:
                                box.uris = uris
                            #print("Box.uris : ",box.uris)

                            #print("Box : ",box)
                            if hasattr(box, "option_types"):
                                box.option_types += [new_type for x in slice]
                            else:
                                box.option_types = [new_type for x in slice]
                            #print("Option_types : ",box.option_types)

                            #library_link
                            if hasattr(box, "library_link"):
                                box.library_link += [library_link for x in slice]
                            else:
                                box.library_link = [library_link for x in slice]
                            #print("library_link",box.library_link)
                            #print(f"\nAdding reco new tracks at index {str(new_index)} with uris {uris} discover_level {discover_level} box.option_types {box.option_types} box.library_link {box.library_link} and tlid {slice[0].tlid}\n")

                        except Exception as e:
                            print(f"Erreur : {e}")
                        
                        print(f"\nAdding reco new tracks at index {str(new_index)} with uris {uris} & tlid {slice[0].tlid}\n")
                        
                        if new_index == current_index:
                            #playing a track added just forward (jumping a step ahead)
                            self.mopidyHandler.playback.play(None,slice[0].tlid)
                        else:
                            self.mopidyHandler.playback.play(None)

            #self.play_or_resume()

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
        pattern = "track:"
        print (self.local)
        if not self.local and self.username != None: pattern = "track:spotify"
        if self.local and self.username == None : pattern = "track:local"
        return self.dbHandler.get_stat_raw_by_hour(read_hour,window,limit,pattern)

    def get_new_tracks_notread(self,limit):
        return self.dbHandler.get_uris_new_notread(limit)

    def get_active_box_by_uri(self, uri):
        for box in self.activeboxs:
            #print (box
            if hasattr(box, "uris"):
                if uri in box.uris:
                    return box
        #No box so we attribute the default one : mopidy        
        mopidy_box = self.dbHandler.get_box_by_uid('mopidy_box')
        mopidy_box.uris = [uri]
        self.activeboxs.append(mopidy_box)
        return mopidy_box

    def get_option_for_box_uri(self, uri, optionName):
        box = self.get_active_box_by_uri(uri)
        if box is not None:
            attr = getattr(box, optionName)
            if attr is not None:
                if attr != '':
                    return getattr(box, optionName, None)
        return getattr(self, optionName, None)

    def get_option_for_box(self, box, optionName):
        if box is not None:
            attr = getattr(box, optionName)
            if attr is not None:
                if attr != '':
                    return getattr(box, optionName, None)
        return getattr(self, optionName, None)

    def get_option_discover_level_for_box(self, uri):
        box = self.get_active_box_by_uri(uri)
        if box is not None:
            if box.option_discover_level is not None:
                if box.option_discover_level != '':
                    return box.option_discover_level
        return self.discover_level


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

    # Box DB Regulation (tmp)
    def reg_box_db(self, box):
        if box.option_type == '': box.option_type='normal'
        box.update()
        box.save()

    # Update raw stat when finished, skipped or system stopped (if possible)
    def update_stat_raw(self, uri):
        self.dbHandler.create_stat_raw(
            uri,
            datetime.datetime.utcnow(),
            datetime.datetime.now().hour,
            self.username
        )

    # Update tracks stat when finished, skipped or system stopped (if possible)
    def update_stat_track(self, track, pos=0, option_type='', library_link='', fix=False):
        #Harmonize option_type if new 
        if 'new' in option_type: option_type='new'

        #Get stats
        if self.dbHandler.stat_exists(track.uri):
            stat = self.dbHandler.get_stat_by_uri(track.uri)
        else:
            stat = self.dbHandler.create_stat(track.uri)

        if fix==False:
            stat.last_read_date = datetime.datetime.utcnow()
            stat.read_count += 1
            stat.read_position = pos
            stat.username = self.username
        else:
            stat.skipped_count = stat.read_count - stat.read_count_end

        #Avoid downgrade of option types in DB
        if not(option_type == 'new' and (stat.option_type == 'normal' or stat.option_type == 'favorites' or stat.option_type == 'incoming' or stat.option_type == 'hidden' or stat.option_type == 'trash')):
            #if not(option_type == 'normal' and (stat.option_type == 'favorites' or stat.option_type == 'incoming')):
            if not(option_type == 'normal' and stat.option_type == 'favorites'):
                stat.option_type = option_type

        #Using rate reading average instead of bool
        track_finished = False
        rate = 0.5
        if hasattr(track, "length"):
            rate = pos / track.length
            if pos / track.length > 0.9: track_finished = True
            #if "podcast+" in track.uri and pos / track.length > 0.7: track_finished = True

        stat.read_end = ((stat.read_end * stat.read_count_end) + rate) / (stat.read_count_end + 1)

        #Update stats
        if track_finished:
            #stat.read_end = True
            stat.read_count_end += 1
            if stat.read_count_end > 0 and stat.day_time_average != None:
                stat.day_time_average = (
                    datetime.datetime.now().hour
                    + stat.day_time_average * (stat.read_count_end - 1)
                ) / (stat.read_count_end)
            else:
                stat.day_time_average = datetime.datetime.now().hour
        elif not fix:
            #if stat.read_end != True: stat.read_end = False
            stat.skipped_count += 1

        #Add / remove the track to playlist(s) if played above/below discover level
        if self.option_autofill_playlists and not fix:
            uri = []
            uri.append(track.uri)

            if track_finished == True :
                print("Finished : autofill activated")
                #Adding to incoming if "new track" played many times
                if stat.option_type == 'new' and self.threshold_playing_count_new(stat.read_count_end,self.discover_level)==True :
                    if library_link !='':
                        print(f"Autofilling Library : {library_link}")
                        result = self.autofill_spotify_playlist(library_link,uri)
                        if result: stat.option_type = 'normal'

                    if stat.option_type != 'normal' :
                        box_incoming = self.dbHandler.get_box_by_option_type('incoming')
                        print(f"Autofilling Incoming : {box_incoming}")
                        if box_incoming:
                            if 'spotify:playlist' in box_incoming.data: 
                                result = self.autofill_spotify_playlist(box_incoming.data,uri)
                                if result: stat.option_type = 'incoming'
                            if 'm3u' in box_incoming.data :
                                playlist = self.mopidyHandler.playlists.lookup(box_incoming.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result: stat.option_type = 'incoming'

                        '''for box in self.activeboxs:
                            #Need to loop on the playlists IN the box/card
                            discover_level_box = self.get_option_for_box(box, "option_discover_level")
                            if box.option_type == 'normal' and self.threshold_playing_count_new(stat.read_count_end,discover_level_box)==True :
                                if 'spotify:playlist' in box.data :
                                    result = self.autofill_spotify_playlist(box.data,uri)
                                    if result: stat.option_type = 'normal'
                                if 'm3u' in box.data :
                                    playlist = self.mopidyHandler.playlists.lookup(box.data)
                                    #for track in playlist.tracks:
                                    #    if 'spotify:playlist' in track.uri :
                                    #        result = self.autofill_spotify_playlist(track.uri,uri)
                                    #        if result: stat.option_type = 'normal'
                                    if 'spotify:playlist' in playlist.tracks[0].uri :
                                        result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                        if result: stat.option_type = 'normal'
                        '''

                #Adding any track to favorites if played many times
                if self.threshold_adding_favorites(stat.read_count_end,self.discover_level)==True :
                    box_favorites = self.dbHandler.get_box_by_option_type('favorites')
                    print(f"Autofilling Favorites : {box_favorites}")
                    if box_favorites:
                        if 'spotify:playlist' in box_favorites.data: 
                            result = self.autofill_spotify_playlist(box_favorites.data,uri)
                            if result: stat.option_type = 'favorites'
                        if 'm3u' in box_favorites.data :
                            playlist = self.mopidyHandler.playlists.lookup(box_favorites.data)
                            #for track in playlist.tracks:
                            #    if 'spotify:playlist' in track.uri :
                            #        result = self.autofill_spotify_playlist(track.uri,uri)
                            #        if result: stat.option_type = 'favorites'
                            if 'spotify:playlist' in playlist.tracks[0].uri :
                                result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                if result: stat.option_type = 'favorites'

            else:
                #Remove track from playlist if skipped many times
                if self.threshold_count_deletion(stat,self.discover_level)==True :
                    '''and library_link !='''
                    print (f"Trashing track {stat.skipped_count} {self.discover_level}")
                    box_trash = self.dbHandler.get_box_by_option_type('trash')
                    if box_trash:
                        if 'spotify:playlist' in box_trash.data: 
                            result = self.autofill_spotify_playlist(box_trash.data,uri)

                            if result and stat.option_type == "incoming": 
                                try:
                                    self.spotifyHandler.remove_tracks_playlist(library_link, uri)
                                except Exception as val_e: 
                                    print(f"Erreur : {val_e}")
                            #stat.option_type = 'trash'

                        '''
                        if 'm3u' in box_trash.data :
                            playlist = self.mopidyHandler.playlists.lookup(box_trash.data)
                            for track in playlist.tracks:
                                if 'spotify:playlist' in track.uri :
                                    result = self.autofill_spotify_playlist(box_trash,uri)
                                    if result:  
                                        if (stat.option_type == "incoming"): 
                                            #self.spotifyHandler.remove_tracks_playlist(track.uri, uri)
                                        stat.option_type = 'trash'
                        '''

        print(f"\n\nUpdate stat track {stat}\n\n")
        stat.update()
        stat.save()

    # Auto Filling playlist 
    def autofill_spotify_playlist(self, playlist_uri,uri):
        try: 
            result = self.autofill_spotify_playlist_action(playlist_uri,uri)
            return (result)
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            self.spotifyHandler.init_token_sp() #pb of expired token to resolve...
            result = self.autofill_spotify_playlist_action(playlist_uri,uri)
            return (result)

    def autofill_spotify_playlist_action(self, playlist_uri,uri):
        #Toadd : test if writable
        print(f"Autofill, playlist_uri : {playlist_uri} uri : {uri}")
        if 'spotify:playlist' in playlist_uri and ('spotify:track' in uri[0]) :
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
    def threshold_playing_count_new(self,read_count_end,discover_level):
        #print (f"read_count_end : {read_count_end} discover_level : {discover_level}")
        if float(read_count_end) >= ((11-discover_level)/2): return True
        else: return False

    #Threshold for adding tracks to favorites (autofill)
    #Need to integrate global ratio, not pertinent now
    #discover_level = 5 : read_count_end>=12
    def threshold_adding_favorites(self,read_count_end,discover_level):
        '''if float(read_count_end) >= ((11-discover_level)*2): return True
        else: return False'''
        return False


    #Threshold for deleting tracks from playlist if too many skip
    #discover_level = 5 et read_count_end=0 : skipped_count_end >=5 // and (stat.read_count_end == 0)
    def threshold_count_deletion(self,stat,discover_level):
        #if (float(stat.skipped_count) > ((11-discover_level)*(stat.read_count_end+1)*0.7)) : 
        if (float(stat.skipped_count) > ((5)*(stat.read_count_end + 1)*0.7)) : 
            return True 
        else: 
            return False

#   WIP

    # Appelle ou rappelle la fonction de recommandation pour allonger la tracklist et poursuivre la lecture de manière transparente
    def update_tracks(self):
        print("should update tracks")

    # Pour le debug, print en console dans le détail les boxs détectés et retirés
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
