import datetime, time, sys, contextlib, random, subprocess, os, threading
#import numpy as np
import random
from mopidy_podcast import Extension, feeds
from urllib import parse, error as url_error

import src.util as util
from src.dbhandler import DatabaseHandler, Track, Stats_Raw, Box
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
    queue = 0 #queue empty

    suffle = False
    max_results = 50
    default_volume = 70  # 0-100
    discover_level = 5  # 0-10
    podcast_newest_first = False
    option_sort = "desc"

    avg_stats = {}

    def __init__(self, mopidyHandler, configO2m, configMopidy, logging):
        self.configO2M = configO2m["o2m"]
        #self.configMopidy = configMopidy
        self.dbHandler = DatabaseHandler()  # Database management
        self.mopidyHandler = mopidyHandler  # Websocket mopidy for reading control
        self.spotifyHandler = SpotifyHandler() # Spotify API
        self.spotifyHandler.set_db_handler(self.dbHandler)  # enable local cache
        self.library_name_cache = {}  # Cache to avoid repeated Spotify lookups for names
        self.library_link_from_track_cache = {}  # Cache: (track_uri, hint) -> full library uri
        # Central per-track registry keyed by Mopidy tlid (always unique).
        # Replaces the parallel box.tlids / box.uris / box.option_types / box.library_link lists.
        # {tlid: {'uri': str, 'option_type': str, 'library_link': str, 'box_id': str}}
        self._track_info = {}
        self._local_to_spotify = {}  # file:// URI → spotify:track: URI for stat routing

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
            self.option_autofill_playlists = self.clean_bool(self.configO2M["option_autofill_playlists"])
        else: self.option_autofill_playlists = False

        if "option_add_reco_after_track" in self.configO2M:
            self.option_add_reco_after_track = self.clean_bool(self.configO2M["option_add_reco_after_track"])
        else: self.option_add_reco_after_track = False

        self.default_box_uid = self.configO2M.get("default_box_uid", "").strip() or None

        if "shuffle" in self.configO2M:
            self.shuffle = self.clean_bool(self.configO2M["shuffle"])

        if "username" in configO2m["spotify"]:
            self.username = configO2m["spotify"]["username"] 

        if "enabled" in configO2m["local"]:
            self.local = self.clean_bool(configO2m["local"]["enabled"])

        if "default_box" in self.configO2M:
            self.default_box = self.configO2M["default_box"]
        else:
            self.default_box = None

        if "fix_stats" in self.configO2M:
            self.fix_stats = self.clean_bool(self.configO2M["fix_stats"])
        self.starting_mode(clear=True)

        self.avg_stats = self.stats_average()
        #Example : print (f"{self.avg_stats['new']['read_count_end']}")

#MISC
    def clean_bool(self,str1):
        try:
            return bool(eval(str(str1).lower().capitalize()))
        except Exception as val_e: 
            return False

    def stats_average(self):
        stats = {}
        for i in {'new','normal','incoming','favorites','hidden'}:
            stats2 = {}
            for j in {'read_end','read_count','read_count_end'}:
                stats2[j]=self.dbHandler.get_avg_stat(option_type=i,column=j)
                if stats2[j] == None: stats2[j]=0
            stats[i]=stats2
        print("\n\nSTATS")
        print("\n".join("{} {}".format(k, v) for k, v in stats.items()))
        return stats

#LOCAL CACHE RESOLUTION
    def _resolve_uri(self, uri):
        """Return the local file URI if this Spotify track was downloaded, else original."""
        if not uri or not uri.startswith('spotify:track:'):
            return uri
        try:
            local = self.dbHandler.get_local_uri(uri)
            if local:
                self._local_to_spotify[local] = uri
                return local
        except Exception:
            pass
        return uri

    def _resolve_uris(self, uris):
        """Resolve a list of URIs, substituting local files where available."""
        if not uris:
            return uris
        return [self._resolve_uri(u) for u in uris]

    def get_spotify_uri(self, uri):
        """Canonicalize a local file URI back to its Spotify URI for stat recording."""
        if not uri or uri.startswith('spotify:'):
            return uri
        return self._local_to_spotify.get(uri, uri)

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
        qi = 0
        while self.queue>0 and qi<120:
            print(f"\nRunning: {qi}")
            time.sleep(1)
            if (self.queue>0): qi+=1
        else:
            self.queue=1
            if len(self.activeboxs) == 0:
                    self.starting_mode(clear=True)
                    # print('Stopping music')
                    '''self.update_stat_track(
                        self.mopidyHandler.playback.get_current_track(),
                        self.mopidyHandler.playback.get_time_position()
                    )'''
            else:
                # Collect all tlids owned by this box from _track_info
                box_tlids = [t for t, info in self._track_info.items() if info.get('box_id') == removedBox.uid]
                if box_tlids:
                    current_tlid = self.mopidyHandler.playback.get_current_tlid()
                    last_tlindex = self.mopidyHandler.tracklist.index()
                    next_tlid = current_tlid

                    if current_tlid in box_tlids:
                        self.update_stat_track(
                            self.mopidyHandler.playback.get_current_track(),
                            self.mopidyHandler.playback.get_time_position()
                        )
                        self.mopidyHandler.playback.stop()

                        current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                        current_tlids = [sub.tlid for sub in current_tracks]
                        for i in current_tlids[last_tlindex:]:
                            if i not in box_tlids:
                                next_tlid = i
                                break

                    self.mopidyHandler.tracklist.remove({"tlid": box_tlids})
                    for t in box_tlids:
                        self._track_info.pop(t, None)

                    if current_tlid in box_tlids and next_tlid is not None:
                        self.mopidyHandler.playback.play(tlid=next_tlid)
                else:
                    print("no tracks registered for removed box")
            self.queue=0
                

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
                seeds_genres, seeds_artists, limit=self.max_results, discover_level=self.discover_level
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
        
        #print(f"\nNew box added: {box}")
        if (box.uid != self.last_box_uid):  # If different from last box added - for NFC mode only
            qi = 0
            while self.queue>0 and qi<120:
                print(f"\nRunning: {qi}")
                time.sleep(1)
                if (self.queue>0): qi+=1
            else:
                self.queue=1
                uri = "box:"+box.uid
                self.update_stat_raw(uri)

                # Variables
                if max_results==15:
                    max_results = self.max_results
                    if box.option_max_results: max_results = box.option_max_results
                    #print (f"Max results : {max_results}")
                
                prev_tl_length = self.mopidyHandler.tracklist.get_length()
                tracklist_uris = self.tracklistappend_box(box,max_results)
                #Flatten
                tracklist_uris = list(util.flatten_list(tracklist_uris))
                #Remove '' items
                tracklist_uris = list(filter(('').__ne__, tracklist_uris))
                #Shorten following lenght0
                lenght0 = len(tracklist_uris)
                tracklist_uris = tracklist_uris[:lenght0]
                #print(f"\nLenght {len(tracklist_uris)} & tracklist_uris: {tracklist_uris}")

                #Let's go to play — account for tracks already directly added in tracklistappend_box
                if len(tracklist_uris)>0:
                    directly_added = self.mopidyHandler.tracklist.get_length() - prev_tl_length
                    remaining = max(0, max_results - directly_added)
                    if remaining > 0:
                        self.add_tracks(box, tracklist_uris, remaining)

                #Shuffle if new tracks were added — regardless of direct vs. indirect add in tracklistappend_box
                current_tl_length = self.mopidyHandler.tracklist.get_length()
                if ((self.shuffle == "true" and box.option_sort != "desc" and box.option_sort != "asc") or box.option_sort == "shuffle") and (current_tl_length > prev_tl_length):
                    index = 0
                    if self.mopidyHandler.tracklist.index() != None: index = int(self.mopidyHandler.tracklist.index())
                    if current_tl_length > index + 1:
                        self.shuffle_tracklist(index+1, current_tl_length)
                self.queue = 0

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
        go = self.add_tracks(box, self.get_common_tracks(datetime.datetime.now().hour,window,max_results), max_results, "normal","o2m:history")
        #go += self.add_tracks(box, self.lastinfos(box,max_results), 1, "info","o2m:info")
        if go > 0:
            self.play_or_resume()

#TRACKLIST FILL / ADD
    # Adding tracks to tracklist and associate them to active_box infos
    def add_tracks(self, active_box, uris, max_results=15, force_option_type=None, library_link='', bypass_remove_filter=False):
        #Set variables
        option_type = active_box.option_type
        if force_option_type != None: 
            option_type=force_option_type
        length = 0

        # Compute a default library_link when not provided to ensure robust tracking
        try:
            if (not library_link or library_link == '') and active_box is not None:
                # If favorites box and user has Spotify, mark favorites
                if getattr(active_box, 'option_type', '') == 'favorites' and getattr(self, 'username', None) is not None:
                    library_link = 'o2m:favorites'
                else:
                    # Try to extract a playlist URI from the box data (first spotify:playlist found)
                    lib_box = self.get_spotify_playlist_from_box(active_box)
                    if lib_box:
                        library_link = lib_box

                # If still empty, try to derive a meaningful link from box data
                if (not library_link or library_link == '') and getattr(active_box, 'data', None):
                    try:
                        for line in str(active_box.data).split("\n"):
                            line = line.replace("\r", "").strip()
                            if not line or line.startswith('#'):
                                continue
                            # Prefer concrete spotify:* identifiers when present
                            if line.startswith('spotify:playlist:') or line.startswith('spotify:album:') or line.startswith('spotify:artist:'):
                                library_link = line
                                break
                            # Fallback to any spotify:/o2m: link-like value
                            if line.startswith('spotify:') or line.startswith('o2m:'):
                                library_link = line
                                break
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error computing default library_link: {e}")

        if isinstance(uris, list) and max_results > 0:
            if len(uris) > 0:
                #Inits
                uris = util.flatten_list(uris)
                #uris = self.flatten(uris)
                if None in uris: uris.remove(None)
                if "None" in uris: uris.remove("None")
                # Ensure URIs is a list of non-empty strings; filter out blanks
                if isinstance(uris, str):
                    uris = [uris]
                try:
                    uris = [u for u in uris if isinstance(u, str) and u.strip() != ""]
                except Exception:
                    pass
                if not isinstance(uris, list):
                    print("Warning: URIs is not a list after normalization; skipping add_tracks")
                    return 0
                if len(uris) == 0:
                    print("Warning: No valid URIs to add (after filtering); skipping add_tracks")
                    return 0

                prev_length = self.mopidyHandler.tracklist.get_length()
                if self.mopidyHandler.tracklist.index():
                    current_index = self.mopidyHandler.tracklist.index()
                else: 
                    current_index = 0 
                
                #Adding tracks trought mopidy handler
                tltracks_added = self.mopidyHandler.tracklist.add(uris=self._resolve_uris(uris))
                length = len(tltracks_added)
                print (f"Lenght added {len(tltracks_added)}")

                if len(tltracks_added)>0:
                    uris_rem = []
                    
                    #****REMOVE***
                    # Exclude tracks already read when option is new
                    # bypass_remove_filter=True skips this for pre-filtered sources (newrecent, newnotcompleted)
                    if option_type == 'new' and not bypass_remove_filter:
                        for t in tltracks_added:
                            if self.dbHandler.stat_exists(t.track.uri):
                                stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                                # When track skipped or too many counts we remove them
                                if (stat.skipped_count > 0
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
                            if self.fix_stats==True: 
                                self.update_stat_track(t.track,0,option_type,'',True)
                            
                            '''if self.dbHandler.stat_exists(t.track.uri):
                                stat = self.dbHandler.get_stat_by_uri(t.track.uri)
                                if (stat.option_type == 'trash' or stat.option_type == 'hidden'):
                                    uris_rem.append(t.track.uri)'''

                            #print (self.mopidyHandler.tracklist.get_tracks())
                            #Removing double tracks in trackslit
                            #if t.track.uri in self.mopidyHandler.tracklist.get_tracks().uri:uris_rem.append(t.track.uri)

                    if len(uris_rem)>0:
                        print ("Removing old new tracks")
                        self.mopidyHandler.tracklist.remove({"uri": uris_rem})

                    #***SLICE***
                    new_length = self.mopidyHandler.tracklist.get_length()
                    #print(f"Length {new_length}")

                    # Shuffle new tracks if necessary : global shuffle or box option : now in card 
                    if (self.shuffle == "true" and active_box.option_sort != "desc" and active_box.option_sort != "asc") or active_box.option_sort == "shuffle":
                        if new_length > prev_length:
                            print(f"Shuffling")
                            self.shuffle_tracklist(prev_length, new_length)
                    
                    #if (active_box.option_sort == "asc") :
                    #    self.mopidyHandler.tracklist.slice

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

                    #***REPLACE AND DISCOVER IF OPTION ON***
                    #Calculate init values
                    discover_level = self.calculate_discover_level(track_uri='',push_discover_level=None)
                    #if discover_level < 10: new_type ='new' else: new_type = 'new_mopidy' #If max discover level, infinite loop of recommandations
                    window_replace = (10 - discover_level)+1
                    replaced_tlids = set()  # Track which tlids were replaced

                    #Exclude if DL is on extreme values which has special behaviours and other cases
                    # 'new' excluded: the new context must play unheard tracks, not recommendations
                    if discover_level > 0 and discover_level < 10 and self.option_add_reco_after_track and window_replace < len(slice2) and option_type not in ['hidden','trash','new']:
                        try:
                            #TODO check library_link
                            for i in range(1, len(slice2), window_replace):
                                #print (f"i : {i}")
                                tlid = slice2[i].tlid
                                uri = slice2[i].track.uri
                                if "spotify:track" in uri:
                                    uris = self.get_track_recommandation(uri,discover_level,1,library_link)

                                    if len(uris) > 0 :
                                        index = self.mopidyHandler.tracklist.index(tlid=tlid)
                                        slice3 = self.mopidyHandler.tracklist.add(uris=self._resolve_uris(uris), at_position=index)
                                        if slice3:
                                            slice4 = self.mopidyHandler.tracklist.remove({'tlid': [tlid]})
                                            if slice4: 
                                                print (f"Replacing at index {index} uri {uri} by uri {uris[0]}")
                                                replaced_tlids.add(slice3[0].tlid)  # Track the new tlid
                                            else: 
                                                print (f"Error when Replacing at index {index} uri {uri} by uri {uris[0]}")

                            #update values if replacements
                            new_length = self.mopidyHandler.tracklist.get_length()
                            slice2 = self.mopidyHandler.tracklist.slice(prev_length, new_length)
                        except Exception as val_e: 
                            print(f"Erreur : {val_e}")

                    #***UPDATE VALUES***
                    # Register each added track in the central _track_info dict
                    option_types_list = ['new' if x.tlid in replaced_tlids else option_type for x in slice2]
                    for tl_track, track_option_type in zip(slice2, option_types_list):
                        track_uri = tl_track.track.uri
                        if tl_track.tlid in replaced_tlids:
                            library_display = 'Reco'
                        else:
                            try:
                                effective_link = self.get_library_link_for_track(track_uri, library_link)
                                library_display = self.get_library_display(effective_link) if effective_link else ''
                            except Exception:
                                library_display = ''
                        self._track_info[tl_track.tlid] = {
                            'uri':             track_uri,
                            'option_type':     track_option_type,
                            'library_link':    library_link,
                            'library_display': library_display,
                            'box_id':          active_box.uid,
                        }
                        try:
                            if self.dbHandler.stat_exists(track_uri):
                                stat = self.dbHandler.get_stat_by_uri(track_uri)
                            else:
                                stat = self.dbHandler.create_stat(track_uri)

                            if (not getattr(stat, 'option_type', None)) and track_option_type:
                                stat.option_type = track_option_type

                            if library_display:
                                stat.in_library = library_display

                            stat.save()
                        except Exception as e:
                            print(f"Error saving stats for {track_uri}: {e}")
                    
                    # Shuffle complete computed tracklist if more than two boxs
                    #self.shuffle_tracklist(current_index + 1, new_length)
                    if (len(self.activeboxs) > 1 or active_box.option_sort=="shuffle") and not((option_type == "info") and (new_length - prev_length==1) and (current_index <= 1)):
                        if new_length > current_index + 1:
                            print ("shuffling")
                            self.shuffle_tracklist(current_index + 1, new_length)
                   
                    #Move at next place the lastinfo content
                    if ((option_type == "info") and (new_length - prev_length==1)):
                        index = self.mopidyHandler.tracklist.index(tl_track=tltracks_added[0])
                        self.mopidyHandler.tracklist.move(index, index, current_index+1)
                    
                    #print(f"\nTracks added to Box {box} with option_types {box.option_types} and library_link {box.library_link} \n")
        return (length)

    def tracklistfill_auto(self,active_box,max_results=20,discover_level=5,mode='normal'):
        #box is the active box in memory and box1,2.. the database contents of boxes
        try:
            print (f"DL AUTO : {discover_level}")
            #GO QUICKLY
            self.quicklaunch_auto(1,discover_level,active_box)

            #Variables
            window = int(round(discover_level / 2))
            tracklist_uris= []

            # Calculate track counts based on linear formulas that respect the limits
            # Base values for discover_level 0 and 10, with linear interpolation
            # favorites: 10 → 2 (linear: -0.8*dl + 10)
            # common: 8 → 5 (linear: -0.3*dl + 8)  
            # playlists: 8 → 5 (linear: -0.3*dl + 8)
            # albums: 4 → 5 (linear: 0.1*dl + 4)
            # incoming: 0 → 3 (linear: 0.3*dl + 0)
            # news: 0 → 10 (linear: 1.0*dl + 0)
            # Total: 30 → 30 (always 30)
            
            base_proportions = {
                'favorites': -0.8 * discover_level + 10,
                'common': -0.3 * discover_level + 8,
                'playlists': -0.3 * discover_level + 8,
                'albums_artists': 0.1 * discover_level + 4,
                'incoming': 0.3 * discover_level,
                'news': 1.0 * discover_level
            }
            
            # Add podcast proportion if in podcast mode
            if mode == 'podcast':
                base_proportions['podcasts'] = 0.9 * discover_level
            
            # Normalize proportions to sum to 1
            total_proportion = sum(base_proportions.values())
            if total_proportion > 0:
                for key in base_proportions:
                    base_proportions[key] /= total_proportion
            
            # Distribute max_results among categories, ensuring the sum is correct
            base_counts = {}
            remaining = max_results
            for key, proportion in list(base_proportions.items())[:-1]:
                count = int(round(proportion * max_results))
                base_counts[key] = count
                remaining -= count
            
            base_counts[list(base_proportions.keys())[-1]] = remaining
            
            print(f"Track distribution: {base_counts} (total: {sum(base_counts.values())})")

            #ADD_TRACKS        
            #Common tracks
            if base_counts.get('common', 0) > 0:
                print(f"\nAUTO : Common {base_counts['common']} tracks\n")
                self.add_tracks(active_box, self.get_common_tracks(datetime.datetime.now().hour,window,base_counts['common']), base_counts['common'], "normal","o2m:history")

            #Incoming
            if base_counts.get('incoming', 0) > 0:
                print(f"\nAUTO : Incoming {base_counts['incoming']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('incoming')
                library_link = self.get_spotify_playlist_from_box(box1)
                self.add_tracks(active_box, self.tracklistappend_box(box1,base_counts['incoming']), base_counts['incoming'], "incoming",library_link)

            #Favorites
            if base_counts.get('favorites', 0) > 0:
                print(f"\nAUTO : Fav {base_counts['favorites']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('favorites')
                #Using spotify favs
                if self.username !=None:
                    fav = self.spotifyHandler.get_library_favorite_tracks(base_counts['favorites'])
                    library_link = 'o2m:favorites'
                    self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)
                #Using specific playlist (normaly elif)
                if box1 != None:
                    fav= self.tracklistappend_box(box1,base_counts['favorites'])
                    library_link = self.get_spotify_playlist_from_box(box1)
                    self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)
                #if fav != None: self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)

            #Podcasts (only in podcast mode)
            if mode=='podcast' and base_counts.get('podcasts', 0) > 0:
                box1 = self.dbHandler.get_box_by_option_type('podcast')
                if box1:
                    print(f"\nAUTO : Podcasts {base_counts['podcasts']} tracks\n")                
                    self.add_tracks(active_box, self.tracklistappend_box(box1,base_counts['podcasts']), base_counts['podcasts'], "podcast","o2m:podcast")
            
            #Albums/Artists
            if base_counts.get('albums_artists', 0) > 0:
                if (random.choice([1,2])) == 1:
                    print(f"\nAUTO : Albums {base_counts['albums_artists']} tracks\n")
                    self.add_tracks(active_box, self.spotifyHandler.get_my_albums_tracks(base_counts['albums_artists'],discover_level), base_counts['albums_artists'], "normal","spotify:album")
                else:
                    print(f"\nAUTO : Artists {base_counts['albums_artists']} tracks\n")
                    self.add_tracks(active_box, self.spotifyHandler.get_my_artists_tracks(base_counts['albums_artists'],discover_level), base_counts['albums_artists'], "normal","spotify:artist")

            #Playlists
            if base_counts.get('playlists', 0) > 0:
                pl_tracks,lib_link = self.spotifyHandler.get_playlists_tracks(base_counts['playlists'],discover_level)
                print(f"\nAUTO : Playlist {base_counts['playlists']} tracks and {len(pl_tracks)} size \n")
                for i in range(len(pl_tracks)):
                    print(f"\nAUTO : Playlist {base_counts['playlists']} tracks and {len(pl_tracks[i])} size \n")
                    uris = [pl_tracks[i]]
                    self.add_tracks(active_box, uris=uris, max_results=1, force_option_type="normal", library_link=lib_link[i])

            #News
            if base_counts.get('news', 0) > 0:
                print(f"\nAUTO : News {base_counts['news']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('new')
                self.add_tracks(active_box, self.tracklistappend_box(box1,base_counts['news']), base_counts['news'], "new","o2m:new")
    
        except Exception as val_e: 
            print(f"Erreur : {val_e}")

#TRACKLIST APPEND / MANAGEMENT 
    
    #Tracklist filling from box
    def tracklistappend_box(self,box,max_results):
        #Variables
        tracklist_uris = []
        tl_length_at_start = self.mopidyHandler.tracklist.get_length()
        if max_results>0:
            
            #If discover level has been pushed by api since the begining of session, we priorise it
            discover_level = self.discover_level
            if not(self.discover_level_on) and (self.get_option_for_box(box, "option_discover_level")!=None) :
                discover_level = self.get_option_for_box(box, "option_discover_level")

            #DB Regulation (tmp)
            #self.reg_box_db(box)
            content = 0

            # Looping on hybrid playlist (delimited by \n)
            data = box.data.split("\n")
            data = [x for x in data if not x.startswith('#')]
            data = [x for x in data if not x.startswith('\r')]
            data = [x.replace('\r', '') for x in data]

            for content in data:
                #Other box called
                if "box:" in content :
                    box_uid = content.split(":")[1]
                    self.queue = 0
                    box = self.dbHandler.get_box_by_uid(box_uid)
                    self.activeboxs.append(box)  #adding box to list
                    print(f"added box {box}") 
                    self.box_action(box)
                
                # Recommandation
                elif "recommendation" in content:
                    media_parts = content.split(":")
                    if media_parts[3] == "genres":  # si les seeds sont des genres
                        genres = media_parts[4].split(",")  # on sépare les genres et on les ajoute un par un dans une liste
                        tracks_uris = self.spotifyHandler.get_recommendations(seed_genres=genres, limit=max_results, discover_level=self.discover_level)  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                        #self.add_tracks(box, tracks_uris, max_results)  # Envoie les uris au mopidy Handler pour modifier la tracklist
                        tracklist_uris.append(tracks_uris)
                    elif media_parts[3] == "artists":  # si les seeds sont des artistes
                        artists = media_parts[4].split(",")  # on sépare les artistes et on les ajoute un par un dans une liste
                        tracks_uris = self.spotifyHandler.get_recommendations(seed_artists=artists, limit=max_results, discover_level=self.discover_level)  # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                        #self.add_tracks(box, tracks_uris, max_results)  # Envoie les uris au mopidy Handler pour modifier la tracklist
                        tracklist_uris.append(tracks_uris)

                # here&now:library (daily habits + library auto extract)
                elif "herenow:library" in content :
                    window = int(round(discover_level / 2))
                    max_result1 = int(round(max_results/2))
                    tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_result1))
                    tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(max_result1,1))

                # auto:library testing (daily habits + library auto extract)
                elif "auto:library" in content :
                    tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level))

                # auto:library testing (daily habits + library auto extract)
                elif "auto_podcast:library" in content :
                    tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level,'podcast'))

                # spotify:library (library random extract)
                elif "spotify:library" in content:
                    print("spotify:library")
                    max_result1 = int(round(max_results / 2))
                    album_pairs = self.spotifyHandler.get_my_albums_tracks(max_result1, 1, return_pairs=True)
                    artist_pairs = self.spotifyHandler.get_my_artists_tracks(max_result1, 1, return_pairs=True)
                    for uri, source in album_pairs + artist_pairs:
                        remaining = max(0, max_results - (self.mopidyHandler.tracklist.get_length() - tl_length_at_start))
                        if remaining <= 0:
                            break
                        self.add_tracks(box, [uri], remaining, library_link=source or '')

                # spotify:library (library random extract)
                elif "spotify:library2" in content :
                    print ("spotify:library2")
                    max_result1 = int(round(max_results/3))
                    tracklist_uris.append(self.spotifyHandler.get_my_albums_tracks(max_result1,1))
                    tracklist_uris.append(self.spotifyHandler.get_my_artists_tracks(max_result1,1))
                    tracklist_uris.append(self.spotifyHandler.get_library_favorite_tracks(max_result1))

                # o2m:favorites (favorites only)
                elif "o2m:favorites" in content :
                    print ("o2m:favorites")
                    tracklist_uris.append(self.spotifyHandler.get_library_favorite_tracks(max_results))

                # Backward compatibility: legacy spotify:favorites
                elif "spotify:favorites" in content:
                    print ("spotify:favorites (legacy) -> o2m:favorites")
                    tracklist_uris.append(self.spotifyHandler.get_library_favorite_tracks(max_results))

                # now:library (daily habits)
                elif "now:library" in content :
                    print ("now:library")
                    window = int(round(discover_level / 2))
                    tracklist_uris.append(self.get_common_tracks(datetime.datetime.now().hour,window,max_results))

                # infos:library (more recent news podcasts (to be updated))
                elif "infos:library" in content :
                    tracklist_uris.append(self.lastinfos(box,max_results))

                # newnotcompleted:library — pre-filtered in DB, bypass REMOVE in add_tracks
                elif "newnotcompleted:library" in content:
                    remaining = max(0, max_results - (self.mopidyHandler.tracklist.get_length() - tl_length_at_start))
                    if remaining > 0:
                        uri_new = self.get_new_tracks_notread(remaining)
                        if uri_new:
                            self.add_tracks(box, uri_new, remaining, library_link='o2m:newnotcompleted', bypass_remove_filter=True)

                # newrecent:library — pre-filtered in DB, bypass REMOVE in add_tracks
                elif "newrecent:library" in content:
                    remaining = max(0, max_results - (self.mopidyHandler.tracklist.get_length() - tl_length_at_start))
                    if remaining > 0:
                        days = 60
                        uri_new = self.get_newrecent_tracks(remaining, days)
                        if uri_new:
                            self.add_tracks(box, uri_new, remaining, library_link='o2m:newrecent', bypass_remove_filter=True)

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

                # albums:spotify — direct call to carry the selected album/artist as library_link
                elif "albums:spotify" in content :
                    remaining = max(0, max_results - (self.mopidyHandler.tracklist.get_length() - tl_length_at_start))
                    if remaining > 0:
                        if (random.choice([1,2])) == 1:
                            uris, source = self.spotifyHandler.get_my_albums_tracks(1, 0, return_source=True)
                        else:
                            uris, source = self.spotifyHandler.get_my_artists_tracks(1, 0, return_source=True)
                        if uris:
                            self.add_tracks(box, uris, remaining, library_link=source or '')

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
                    if uris:
                        tracklist_uris.append(uris)

                # Podcast channel
                elif "podcast+" in content and "#" not in content:
                    print(f"Podcast channel : {content}")
                    self.update_stat_raw(content)
                    #self.add_podcast_from_channel(box,content,max_results)
                    tracklist_uris.append(self.add_podcast_from_channel(box,content,max_results))
                    # On doit rechercher un index de dernier épisode lu dans une bdd de statistiques puis lancer les épisodes non lus
                    # tracklist_uris += self.get_unread_podcasts(shows)

                # Podcast episode
                elif "podcast+" in content and "#" in content:
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
                    elif media_parts[1] == "playlist":
                        tracklist_uris.append(content)
                        # Cache playlist content if not already fresh (cache-first, 1 API call max)
                        self.spotifyHandler.cache_playlist_by_id(media_parts[2])
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
        info_url = ""
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
            if (hour >= 8 and hour < 10) : info_url = "rss_18835.xml" #FI Week end 7h
            if (hour >= 10 and hour < 14) or (hour == 9 and minute >= 25): info_url= "rss_12735.xml" #FI 9h
            if hour >= 14 and hour <= 19: info_url = "rss_18909.xml" #FI Week end 13h
            #if hour >= 14 and hour <= 19: info_url = "rss_12735.xml" #FI Week end 13h
            if ((hour == 18 and minute > 20) and hour < 20) or (hour <= 9 and day == 6) : info_url = "rss_18910.xml" #FI Week end 18h
            if (hour == 19 and minute > 20)  or (hour <= 9 and minute < 25) or hour > 19: info_url = "rss_18911.xml" #FI Week end 19h
            if  day == 5 and ((hour < 9) or (hour == 9 and minute < 25)) : info_url = "rss_11736.xml" #FI 19h
        
        try:
            if info_url != "":
                info_url = "podcast+https://radiofrance-podcast.net/podcast09/" + info_url + "?max_results=1"
                print (info_url)
                tracklist_uris = self.add_podcast_from_channel(box,info_url, max_results)
                return tracklist_uris
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            #return []

    def add_podcast_from_channel(self,box,uri, max_results):
        feedurl = uri.split("+")[1]
        #parsing url ?
        par = parse.parse_qs(parse.urlparse(feedurl).query)
        print(f"par : {par} and uri : {uri}")
        if 'max_results' in par : max_results_pod = int(par['max_results'][0])
        else : max_results_pod = max_results
        #volume=parse.parse_qs(parse.urlparse(feedurl).query)['volume'][0]

        shows = self.get_unread_podcasts(uri, 0, max_results_pod)
        #print(f'Shows : {shows}')
        #print(f'max_results_pod : {max_results_pod}')
        #self.add_tracks(box, shows, max_results_pod)
        return shows

    def get_podcast_from_url(self, url):
        try:
            f = Extension.get_url_opener({"proxy": {}}).open(url, timeout=10)
        except (url_error.HTTPError, url_error.URLError) as e:
            print(f"Podcast feed unavailable ({url}): {e}")
            return []
        with contextlib.closing(f) as source:
            feed = feeds.parse(source)
        print(f"option_sort : {self.option_sort}")
        shows = list(feed.items(self.option_sort))
        # Conserve les max_results premiers épisodes
        del shows[self.max_results :]
        return shows

    def get_unread_podcasts(self, data, last_track_played, max_results=15):
        uris = []
        feedurl = data.split("+")[1]

        shows = self.get_podcast_from_url(feedurl)
        #unread_shows = shows[last_track_played:]  # Remove n first shows already read (to be checked not used anymore)
        unread_shows = shows[:max_results]  # Cut to max results (to be suppressed if grabbing later than first tracks)
        for item in unread_shows:
            stat_pod = self.dbHandler.get_stat_by_uri(item.uri)
            if (stat_pod):
                #Keep podcasts when 
                #This is a podcast and read_end proportion < 0.9 and not a promotion podcast
                if (stat_pod.option_type == "podcast" and stat_pod.read_end < 0.9 and "app_rf_promotion" not in item.uri): uris.append(item.uri)
                #This is an info and podcast and read_end proportion < 0.9 and not a promotion podcast
                elif (not stat_pod.read_count_end > 0 and "app_rf_promotion" not in item.uri): uris.append(item.uri)
            elif ("app_rf_promotion" not in item.uri): uris.append(item.uri)
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
            print("Clearing tracklist and active boxs")
            self.mopidyHandler.playback.stop()
            self.mopidyHandler.tracklist.clear()
            self._track_info.clear()

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
        print(f"play_or_resume: state={state}")
        if state == "stopped":
            current_tl_track = self.mopidyHandler.playback.get_current_tl_track()
            if current_tl_track is None:
                current_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
                print(f"play_or_resume: no current track, tracklist size={len(current_tracks)}")
                if len(current_tracks) > 0:
                    self.mopidyHandler.playback.play(tlid=current_tracks[0].tlid)
                    print(f"play_or_resume: playing tlid={current_tracks[0].tlid}")
            else:
                self.mopidyHandler.playback.play()
                print(f"play_or_resume: resuming current track")
        elif state == "paused":
            self.mopidyHandler.playback.resume()
            print(f"play_or_resume: resuming from pause")
        else:
            print(f"play_or_resume: already playing or unknown state, no action")

    def initialize_playback(self, window=1):
        """
        Initialize playback according to rules:
        1) If there is a track in the tracklist and playback is paused, resume playback.
        2) If there is no track in the tracklist, look into the `stats_raw` table for a
           'box:' URI usually played at this hour and launch that box.
        In all cases, ensure audio is not muted and unmute the mixer.

        Parameters:
            window (int): hour window around the current hour used when querying stats_raw
        """
        # Only allow initialize_playback to run if option_add_reco_after_track is enabled
        if not getattr(self, 'option_add_reco_after_track', False):
            return False

        try:
            # 1) Always unmute first
            try:
                self.mopidyHandler.mixer.set_mute(False)
            except Exception as e:
                print(f"Error while unmuting mixer: {e}")

            # Check if there are tracks in the tracklist
            try:
                tl_length = self.mopidyHandler.tracklist.get_length()
            except Exception as e:
                print(f"Error getting tracklist length: {e}")
                tl_length = 0

            # If there are tracks and state is paused -> resume/play
            try:
                state = self.mopidyHandler.playback.get_state()
            except Exception as e:
                print(f"Error getting playback state: {e}")
                state = None

            if tl_length and tl_length > 0 and state == 'paused':
                try:
                    self.mopidyHandler.playback.play()
                    return True
                except Exception as e:
                    print(f"Error starting existing playback: {e}")

            # 2) If no tracks in the tracklist -> use default box if configured, else fall back to stats_raw history
            if not tl_length or tl_length == 0:
                box = None

                if self.default_box_uid:
                    try:
                        box = self.dbHandler.get_box_by_uid(self.default_box_uid)
                        if box is None:
                            print(f"initialize_playback: default_box_uid '{self.default_box_uid}' not found in DB")
                    except Exception as e:
                        print(f"initialize_playback: error fetching default box: {e}")

                if box is None:
                    # Fallback: pick a box from stats_raw history matching current hour
                    hour = datetime.datetime.now().hour
                    try:
                        uris = self.dbHandler.get_stat_raw_by_hour(hour, window, 1, 'box:')
                    except Exception as e:
                        print(f"Error querying stats_raw: {e}")
                        uris = None

                    if uris and len(uris) > 0:
                        uri = uris[0]
                        try:
                            if uri.startswith('box:'):
                                uid = uri.split(':', 1)[1]
                                box = self.dbHandler.get_box_by_uid(uid)
                        except Exception as e:
                            print(f"Error parsing box uri from stats_raw: {e}")

                if box is not None:
                    try:
                        self.box_action(box)
                        self.activeboxs.append(box)
                    except Exception as e:
                        print(f"Error launching box in initialize_playback: {e}")

            # Nothing to do
            return False
        except Exception as e:
            print(f"Error in initialize_playback: {e}")
            return False

    # Vide la tracklist sauf la chanson en cours de lecture puis ajoute des uris à la suite
    @util.RateLimited(
        1
    )  # Limite l'execution de la fonction : une fois par seconde (à vérifier)
    def add_tracks_after(self, uris):
        print("ADDING SONGS SILENTLY IN TRACKLIST")
        self.clear_tracklist_except_current_song()
        self.mopidyHandler.tracklist.add(uris=self._resolve_uris(uris))

    def clear_tracklist_except_current_song(self):
        all_tracklist_tracks = self.mopidyHandler.tracklist.get_tl_tracks()
        current_tlid = self.mopidyHandler.playback.get_current_tlid()
        for (tlid, _) in all_tracklist_tracks:
            if tlid != current_tlid:
                self.mopidyHandler.tracklist.remove({"tlid": [tlid]})

#   SONGS RECOMMANDATION MANAGEMENT
    def add_reco_after_track_read(self, track_uri, library_link='', data='', mode='add'):
        if self.option_add_reco_after_track: 
            #self.mopidyHandler.playback.pause()
            if "spotify:track" in track_uri:
                
                #Calculate init values
                discover_level = self.calculate_discover_level(track_uri)
                if discover_level < 10: 
                    new_type ='new'
                    limit = int(round(discover_level * 0.25)) #Fixing number of new tracks
                else: 
                    new_type = 'new_mopidy' #If max discover level, infinite loop of recommandations
                    limit = 1 #Extreme mode : continusly autofill until next song is launched

                # Identify the box tied to the currently playing track using tlid first, then uri
                current_tlid = None
                try:
                    current_tlid = self.mopidyHandler.playback.get_current_tlid()
                except Exception as e:
                    print(f"Error getting current tlid: {e}")

                target_box = self.get_active_box_for_playback(track_uri, current_tlid)

                uris = self.get_track_recommandation(track_uri,discover_level,limit,data)

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
                    slice = self.mopidyHandler.tracklist.add(uris=self._resolve_uris(uris), at_position=new_index)
                    # Updating box infos
                    # if 'box' in locals():
                    if slice:
                        try:
                            box = target_box or self.get_active_box_by_uri(track_uri)
                            box_id = box.uid if box is not None else 'mopidy_box'
                            if box is None:
                                print(f"Warning: Could not identify box for reco from {track_uri} — registering under mopidy_box")

                            # Register each reco track in _track_info (keyed by unique tlid)
                            reco_display = 'Reco'
                            for x in slice:
                                try:
                                    reco_uri = x.track.uri if (hasattr(x, "track") and x.track) else (uris[0] if uris else '')
                                    self._track_info[x.tlid] = {
                                        'uri':             reco_uri,
                                        'option_type':     new_type,
                                        'library_link':    library_link,
                                        'library_display': reco_display,
                                        'box_id':          box_id,
                                    }
                                except Exception as e:
                                    print(f"Error registering reco track in _track_info: {e}")

                        except Exception as e:
                            print(f"Erreur : {e}")
                        
                        print(f"\nAdding reco new tracks at index {str(new_index)} with uris {uris} & tlid {slice[0].tlid}\n")
                        
                        if new_index == current_index:
                            #playing a track added just forward (jumping a step ahead)
                            self.mopidyHandler.playback.play(None,slice[0].tlid)
                        else:
                            self.mopidyHandler.playback.play(None)

            #self.play_or_resume()

    def calculate_discover_level(self,track_uri='',push_discover_level=None):
        # Calculate the discover_level : box associated or updated discover_level via api
        discover_level = self.discover_level
        if not self.discover_level_on :
            if push_discover_level != None and push_discover_level:
                discover_level = push_discover_level
            if track_uri != '':
                dl = self.get_option_for_box_uri(track_uri,"option_discover_level")
                if dl and dl != None: discover_level = dl
        print (int(discover_level))
        return int(discover_level)

    def get_track_recommandation(self,track_uri, discover_level=5, limit=1, data=''):
        # Get tracks recommandations
        if "spotify:track" not in track_uri:
            return []

        track_data = track_uri.split(":")
        track_seed = [track_data[2]]

        choices = ['album','artist','reco']
        uris = []

        #Ponderation Album / Artist / Reco depending the context data
        if 'album' in data:
            p = [0, 0.8, 0.2]
        else:
            p = [0.5, 0.3, 0.2]

        # Tracks to exclude: seed + already chosen in this call
        excluded = {track_uri}

        for i in range(0, limit):
            c = random.choices(choices, weights=p, k=3)
            print(c)
            new_uri = None

            for _attempt in range(len(c)):
                strategy = c[_attempt]
                if strategy == 'album':
                    candidates = self.get_same_album_tracks(track_uri, 3)
                elif strategy == 'artist':
                    candidates = self.get_same_artist_tracks(track_uri, 3)
                else:  # reco
                    candidates = self.get_spotify_reco(track_seed, 3)

                if not candidates:
                    continue

                # Pick first candidate that isn't the seed or already selected
                valid = [u for u in candidates if u and u not in excluded]
                if valid:
                    new_uri = valid[0]
                    break

            if new_uri:
                uris.append(new_uri)
                excluded.add(new_uri)

        return uris


#  TRACKS AND STATS MANAGEMENT

    def get_spotify_playlist_from_box(self,box):
        library_link = ''

        # Playlist extraction: do NOT lookup arbitrary box.data in Mopidy.
        # Some legacy values (e.g. 'spotify:favorites') are not valid Spotify URIs for Mopidy.
        data = box.data.split("\n")
        data = [x for x in data if not x.startswith('#')]
        data = [x for x in data if not x.startswith('\r')]
        #Loop on lines containing the playlist uris
        for content in data:
            #Taking the first one. Pb if manies ?
            if 'spotify:playlist' in content: 
                library_link = content
                break
        return library_link

    def get_library_link_for_track(self, track_uri, library_link_hint):
        """Derive a full library URI for a specific track when the hint is generic.

        Examples:
        - hint 'spotify:album'  -> 'spotify:album:<id>' based on the track
        - hint 'spotify:artist' -> 'spotify:artist:<id>' based on the track
        Otherwise returns the hint as-is.
        """
        try:
            if not library_link_hint:
                return ''
            if not track_uri or not isinstance(track_uri, str):
                return library_link_hint

            cache_key = (track_uri, library_link_hint)
            if cache_key in self.library_link_from_track_cache:
                return self.library_link_from_track_cache[cache_key]

            # Only possible for Spotify tracks
            if not track_uri.startswith('spotify:track:'):
                self.library_link_from_track_cache[cache_key] = library_link_hint
                return library_link_hint

            track_id = track_uri.split(':', 2)[2]

            resolved = library_link_hint
            if library_link_hint == 'spotify:album':
                resolved = self.spotifyHandler.get_track_album(track_id)
            elif library_link_hint == 'spotify:artist':
                artist_id = self.spotifyHandler.get_track_artist(track_id)
                if artist_id:
                    resolved = f'spotify:artist:{artist_id}'

            self.library_link_from_track_cache[cache_key] = resolved
            return resolved
        except Exception as e:
            print(f"Error deriving library_link from track {track_uri} hint {library_link_hint}: {e}")
            return library_link_hint

    def get_library_display(self, library_link):
        """Return human-readable name for a library link with simple caching."""
        try:
            if not library_link:
                return ''
            if library_link in self.library_name_cache:
                return self.library_name_cache[library_link]

            display = library_link
            prefix = ''

            # If this is a Spotify URI, prefix with its type for readability
            if isinstance(library_link, str) and library_link.startswith('spotify:'):
                parts = library_link.split(':')
                if len(parts) >= 2:
                    resource_type = parts[1]
                    if resource_type in {'playlist', 'album', 'artist'}:
                        prefix = f"{resource_type}:"

            try:
                display = self.spotifyHandler.get_resource_name(library_link)
            except Exception as e:
                print(f"Error resolving library display for {library_link}: {e}")

            # If resolution failed and we still have a Spotify URI, shorten it to the ID
            # so we store 'playlist:<id>' instead of 'playlist:spotify:playlist:<id>'.
            if isinstance(display, str) and display.startswith('spotify:'):
                try:
                    dparts = display.split(':')
                    if len(dparts) >= 3:
                        display = dparts[2]
                except Exception:
                    pass

            # Avoid double-prefixing if the resolved name already contains a prefix
            if prefix and isinstance(display, str):
                if not (display.startswith('playlist:') or display.startswith('album:') or display.startswith('artist:')):
                    display = prefix + display

            self.library_name_cache[library_link] = display
            return display
        except Exception as e:
            print(f"Error in get_library_display: {e}")
            return library_link

    def get_spotify_reco(self, track_seed, limit):
        uris = self.spotifyHandler.get_recommendations(
            seed_genres=None, seed_artists=None, seed_tracks=track_seed, limit=limit, discover_level=self.discover_level)
        return uris

    def get_same_artist_tracks(self, track_uri, limit):
        artist_id = self.spotifyHandler.get_track_artist(track_uri)
        if not artist_id:
            return []
        uris = self.spotifyHandler.get_artist_all_tracks(artist_id, limit)
        return uris

    def get_same_album_tracks(self, track_uri, limit):
        album_uri = self.spotifyHandler.get_track_album(track_uri)
        if not album_uri:
            return []
        uris = self.spotifyHandler.get_album_all_tracks(album_uri, limit)
        return uris

    def get_spotify_library(self,limit):
        return self.spotifyHandler.get_library_tracks(limit)

    def get_common_tracks(self,read_hour,window,limit):
        pattern = "track:"
        if not self.local and self.username != None: pattern = "spotify:track"
        if self.local and self.username == None : pattern = "local:local"
        return self.dbHandler.get_stat_raw_by_hour(read_hour,window,limit,pattern)

    def get_new_tracks_notread(self, limit):
        return self.dbHandler.get_uris_new_notread(limit)

    def get_newrecent_tracks(self, limit, days=60):
        return self.dbHandler.get_uris_newrecent(limit, days)

    def get_active_box_by_uri(self, uri):
        """Return the active box that owns a track with the given URI."""
        for info in self._track_info.values():
            if info.get('uri') == uri:
                box_id = info.get('box_id')
                for box in self.activeboxs:
                    if box.uid == box_id:
                        return box
        # Track not registered (added externally via Iris) — fall back to mopidy_box
        return self._get_or_create_mopidy_box()

    def get_active_box_by_tlid(self, tlid):
        """Return the active box that owns the given tlid."""
        if tlid is None:
            return None
        info = self._track_info.get(tlid)
        if info:
            box_id = info.get('box_id')
            for box in self.activeboxs:
                if box.uid == box_id:
                    return box
        return None

    def _get_or_create_mopidy_box(self):
        """Return the persistent in-memory mopidy_box, fetching from DB once if needed."""
        try:
            for box in self.activeboxs:
                if box.uid == 'mopidy_box':
                    return box
            mopidy_box = self.dbHandler.get_box_by_uid('mopidy_box')
            if mopidy_box:
                self.activeboxs.append(mopidy_box)
                return mopidy_box
        except Exception as e:
            print(f"Error getting/creating mopidy_box: {e}")
        return None

    def get_active_box_for_playback(self, track_uri=None, tlid=None):
        box = self.get_active_box_by_tlid(tlid)
        if box:
            return box
        if track_uri:
            return self.get_active_box_by_uri(track_uri)
        return None

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
            datetime.datetime.now(datetime.timezone.utc),
            datetime.datetime.now().hour,
            self.username
        )

    def _log_playlist_change(self, track_uri, playlist_uri, action, from_type, to_type, track_name=None):
        try:
            playlist_name = self.get_library_display(playlist_uri) if playlist_uri else None
            self.dbHandler.create_playlist_log(
                track_uri=track_uri,
                playlist_uri=playlist_uri,
                action=action,
                from_option_type=from_type,
                to_option_type=to_type,
                username=self.username,
                track_name=track_name,
                playlist_name=playlist_name,
            )
        except Exception as e:
            print(f"playlist log error: {e}")

    # Update tracks stat when finished, skipped or system stopped (if possible)
    def update_stat_track(self, track, pos=0, option_type='', library_link='', fix=False, uri_override=None):
        # Populate metadata cache from Mopidy track object (no API call)
        self.spotifyHandler.cache_track_from_mopidy(track)

        # uri_override allows callers to record stats under the canonical Spotify URI
        # even when the track was played from a local file (file:// URI)
        uri = uri_override or track.uri

        #Harmonize option_type if new
        if 'new' in option_type: option_type='new'
        new_stat = False

        #Get stats
        if self.dbHandler.stat_exists(uri):
            stat = self.dbHandler.get_stat_by_uri(uri)
        else:
            new_stat = True
            stat = self.dbHandler.create_stat(uri)

        #Using rate reading average instead of bool
        track_finished = False
        rate = 0.5
        stat.username = self.username

        if hasattr(track, "length"):
            rate = pos / track.length
            if rate > 0.9: track_finished = True
            #Probably an artefact of auto adding track : so no adding stat needed and exit function
            #if (rate < 0.05) and (new_stat==False): 
            if (rate < 0.05) : 
                print (f"No Stat : skip artefact {rate}")
                return None

        if fix==False:
            stat.last_read_date = datetime.datetime.now(datetime.timezone.utc)
            stat.read_count += 1
            stat.read_position = pos
        else:
            stat.skipped_count = stat.read_count - stat.read_count_end #Fix

        #Avoid downgrade of option types in DB
        #Due to many possibilities of change, we remove it and follow the flow !
        if not(option_type == 'new' and (stat.option_type == 'normal' or stat.option_type == 'favorites' or stat.option_type == 'incoming' or stat.option_type == 'hidden' or stat.option_type == 'trash')):
            #if not(option_type == 'normal' and (stat.option_type == 'favorites' or stat.option_type == 'incoming')):
            if not(option_type == 'incoming' and (stat.option_type == 'normal' or stat.option_type == 'favorites')):
                stat.option_type = option_type
        #stat.option_type = option_type
        
        # Store library_link in the in_library field (repurposed from obsolete boolean)
        if library_link and library_link != '':
            try:
                effective_link = self.get_library_link_for_track(uri, library_link)
            except Exception:
                effective_link = library_link
            stat.in_library = self.get_library_display(effective_link)
        
        #Check if there is a stat pb to fix 
        if (stat.read_end == 0): stat.read_end = 0.01
        if (stat.read_count == 0): stat.read_count = 0.01
        gap = stat.read_count_end / stat.read_count / stat.read_end #Gap evaluates integrity of data to check if fix is needed

        #If meta fix activated do not include actual rate
        if stat.read_count <=1:
            stat.read_end = rate
        else:            
            if (fix == False):
                '''if (gap > 1.5 ) or (gap < 0.6): 
                    print ("Fix forced due to high gap")
                    stat.read_end = ((stat.read_end * (stat.read_count - stat.read_count_end))+ stat.read_count_end + rate) / (stat.read_count + 1)
                else:'''
                #old_stat_read_end = stat.read_end
                stat.read_end = ((stat.read_end * stat.read_count) + rate) / (stat.read_count + 1)
                #print (f"Rate {rate}, Read_count {stat.read_count}, , Read_end {old_stat_read_end}  New stat Read_end : {stat.read_end}")
            else:
                if (gap > 1.5 ) or (gap < 0.6): 
                    stat.read_end = ((stat.read_end * (stat.read_count - stat.read_count_end))+ stat.read_count_end) / (stat.read_count)
            #stat.read_end = ((stat.read_end * stat.read_count_end) + rate) / (stat.read_count_end + 1)

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
        elif (fix == False):
            #if stat.read_end != True: stat.read_end = False
            stat.skipped_count += 1

        #Add / remove the track to playlist(s) if played above/below discover level
        if self.option_autofill_playlists and (fix == False):
            uri = []
            uri.append(track.uri)
            _from_option_type = stat.option_type
            _track_name = getattr(track, 'name', None)

            #TRACK FINISHED
            if track_finished == True :
                print("Finished : autofill and remove activated")
                #NEW > INCOMING : Adding to incoming if "new track" played many times
                if stat.option_type == 'new' and self.threshold_playing_count_new(stat.read_count_end,self.discover_level)==True :
                    if library_link !='':
                        print(f"Autofilling Library : {library_link}")
                        result = self.autofill_spotify_playlist(library_link,uri)
                        if result: stat.option_type = 'normal'
                        if result and result != 'already in': self._log_playlist_change(uri[0], library_link, 'add', _from_option_type, 'normal', _track_name)

                    if stat.option_type != 'normal' :
                        box_incoming = self.dbHandler.get_box_by_option_type('incoming')
                        print(f"Autofilling Incoming : {box_incoming}")
                        if box_incoming:
                            if 'spotify:playlist' in box_incoming.data:
                                result3 = self.autofill_spotify_playlist(box_incoming.data,uri)
                                if result3: stat.option_type = 'incoming'
                                if result3 and result3 != 'already in': self._log_playlist_change(uri[0], box_incoming.data, 'add', _from_option_type, 'incoming', _track_name)
                            if 'm3u' in box_incoming.data :
                                playlist = self.mopidyHandler.playlists.lookup(box_incoming.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result4 = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result4: stat.option_type = 'incoming'
                                    if result4 and result4 != 'already in': self._log_playlist_change(uri[0], playlist.tracks[0].uri, 'add', _from_option_type, 'incoming', _track_name)

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

                #NORMAL > FAVORITES : Adding any track to favorites if played many times
                if self.threshold_adding_favorites(stat,self.discover_level)==True :
                    print(f"Autofilling Favorites")
                    if self.username !=None:
                        result5 = self.spotifyHandler.sp.current_user_saved_tracks_add(tracks=uri)
                        if result5: stat.option_type = 'favorites'
                        if result5: self._log_playlist_change(uri[0], 'spotify:saved', 'add', _from_option_type, 'favorites', _track_name)
                    else:
                        box_favorites = self.dbHandler.get_box_by_option_type('favorites')
                        if box_favorites:
                            if 'spotify:playlist' in box_favorites.data:
                                result6 = self.autofill_spotify_playlist(box_favorites.data,uri)
                                if result6: stat.option_type = 'favorites'
                                if result6 and result6 != 'already in': self._log_playlist_change(uri[0], box_favorites.data, 'add', _from_option_type, 'favorites', _track_name)
                            if 'm3u' in box_favorites.data :
                                playlist = self.mopidyHandler.playlists.lookup(box_favorites.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result7 = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result7: stat.option_type = 'favorites'
                                    if result7 and result7 != 'already in': self._log_playlist_change(uri[0], playlist.tracks[0].uri, 'add', _from_option_type, 'favorites', _track_name)

            #TRACK SKIPPED
            else:
                #Remove track from playlist if skipped many times
                if self.threshold_remove_track_playlist(stat,self.discover_level)==True and library_link !='':
                    print (f"0. Trying to Trash track {stat.uri} from {library_link}")
                    #Adding to trash
                    box_trash = self.dbHandler.get_box_by_option_type('trash')
                    if box_trash:
                        if 'spotify:playlist' in box_trash.data:
                            print (f"1. Putting in Trash track {stat.uri}")
                            result = self.autofill_spotify_playlist(box_trash.data,uri)
                            if result and result != 'already in': self._log_playlist_change(uri[0], box_trash.data, 'add', _from_option_type, 'trash', _track_name)

                            #If trashed, let's trash it really
                            if result:
                                print (f"2. Putting in Trash track {stat.uri}")
                                #self.spotifyHandler.remove_tracks_playlist(library_link, uri)
                                result2 = self.remove_spotify_playlist(library_link,uri)
                                if result2:
                                    stat.option_type = 'new'
                                    self._log_playlist_change(uri[0], library_link, 'remove', _from_option_type, 'new', _track_name)
                                    print (f"3. Track trashed {stat.uri} from {library_link}")
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

                #Remove track from favorites if skipped many times
                if self.threshold_removing_favorites(stat,self.discover_level)==True:
                    print(f"Removing Favorites")
                    if self.username !=None:
                        result3 = self.spotifyHandler.sp.current_user_saved_tracks_delete(tracks=uri)
                        if result3: stat.option_type = 'normal'
                        if result3: self._log_playlist_change(uri[0], 'spotify:saved', 'remove', _from_option_type, 'normal', _track_name)
                    else:
                        box_favorites = self.dbHandler.get_box_by_option_type('favorites')
                        if box_favorites:
                            if 'spotify:playlist' in box_favorites.data:
                                result4 = self.remove_spotify_playlist(box_favorites.data,uri)
                                if result4: stat.option_type = 'normal'
                                if result4: self._log_playlist_change(uri[0], box_favorites.data, 'remove', _from_option_type, 'normal', _track_name)
                            if 'm3u' in box_favorites.data :
                                playlist = self.mopidyHandler.playlists.lookup(box_favorites.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result5 = self.remove_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result5: stat.option_type = 'normal'
                                    if result5: self._log_playlist_change(uri[0], playlist.tracks[0].uri, 'remove', _from_option_type, 'normal', _track_name)

        # Deferred mood enrichment: if energy/valence still missing and not yet attempted,
        # fetch from Last.fm in a background thread so the playback event is not blocked.
        if stat.energy is None and stat.mood is None:
            _track_name   = getattr(track, 'name', None)
            _artists      = getattr(track, 'artists', None) or []
            _artist_name  = next((a.name for a in _artists if getattr(a, 'name', None)), None)
            _uri_mood     = uri
            _db           = self.dbHandler
            _sp           = self.spotifyHandler
            if _track_name and _artist_name and not any(
                s in _uri_mood for s in ('podcast', 'rss', 'http://', 'https://')
            ):
                def _enrich():
                    try:
                        mood, energy, valence = _sp._lastfm_get_track_mood(_artist_name, _track_name)
                        if mood or energy is not None:
                            _db.update_track_features(_uri_mood, mood=mood, energy=energy, valence=valence)
                            print(f"deferred mood: {_artist_name} – {_track_name} → mood={mood} e={energy} v={valence}")
                        else:
                            _db.update_track_features(_uri_mood, mood='_')
                    except Exception as e:
                        print(f"deferred mood error ({_track_name}): {e}")
                threading.Thread(target=_enrich, daemon=True).start()

        print(f"\n\nUpdate and Fix {fix} stat track {stat}\n\n")
        stat.update()
        stat.save()

    # Auto Filling playlist 
    def remove_spotify_playlist(self, playlist_uri,uri):
        # Defensive: strip control chars and whitespace, then delegate to SpotifyHandler normalizer
        try:
            if isinstance(playlist_uri, str):
                playlist_uri = playlist_uri.replace("\r", "").replace("\n", "").strip()
                # remove stray '#015' artifacts if present
                playlist_uri = playlist_uri.replace("#015", "").strip()

            # delegate to SpotifyHandler which already normalizes playlist id and tracks
            print(f"Trying remove from playlist uri {playlist_uri} - tracks {uri}")
            return self.spotifyHandler.remove_tracks_playlist(playlist_uri, uri)
        except Exception as val_e:
            print(f"Erreur removing from playlist: {val_e}")        



    # Auto Filling playlist 
    def autofill_spotify_playlist0(self, playlist_uri,uri):
        try: 
            #Toadd : test if writable
            print(f"Autofill, playlist_uri : {playlist_uri} uri : {uri}")
            if 'spotify:playlist' in playlist_uri and ('spotify:track' in uri[0]) :
                playlist_id = playlist_uri.split(":")[2]
                track_id = uri[0].split(":")[2]
                if self.spotifyHandler.is_track_in_playlist(self.username,track_id,playlist_id) == False:
                    print (f"Auto Filling playlist with self.username: {self.username}, playlist: {playlist_uri}, track.uri: {uri}")
                    result = self.spotifyHandler.sp.user_playlist_add_tracks(self.username, playlist_id, uri)
                else: result = 'already in'
                return (result)
        except Exception as val_e: 
            print(f"Erreur : {val_e}")

    # Auto Filling playlist 
    def autofill_spotify_playlist(self, playlist_uri,uri):
        try: 
            #Toadd : test if writable
            print(f"Autofill, playlist_uri : {playlist_uri} uri : {uri}")
            if 'spotify:playlist' in playlist_uri and ('spotify:track' in uri[0]) :
                playlist_id = playlist_uri.split(":")[2]
                track_id = uri[0].split(":")[2]
                if self.spotifyHandler.is_track_in_playlist(self.username,track_id,playlist_id) == False:
                    print (f"Auto Filling playlist with self.username: {self.username}, playlist: {playlist_uri}, track.uri: {uri}")
                    result = self.spotifyHandler.sp.user_playlist_add_tracks(self.username, playlist_id, uri)
                else: result = 'already in'
                return (result)
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            
#   THRESHOLDS MANAGEMENT

    #Threshold NEW : stopping playing and autofilling new tracks (add_tracks or autofill)
    #discover_level = 5 : read_count_end>=3
    def threshold_playing_count_new(self,read_count_end,discover_level):
        #print (f"read_count_end : {read_count_end} discover_level : {discover_level}")
        threshold = ((11-discover_level)/2) + (1 if discover_level == 10 else 0)
        if float(read_count_end) >= threshold: return True
        else: return False

    #Threshold FAVORITES : for adding or removing tracks to favorites (autofill)
    #discover_level = 5 : read_count_end>=12 // if float(read_count_end) >= ((11-discover_level)*2):
    def threshold_adding_favorites(self,stat,discover_level):
        result = False
        ratio = 1+(1-discover_level/20)
        print (f"Favorite test Ratio:{ratio}")
        #if stat.option_type=="normal" and (stat.read_end > self.avg_stats['favorites']['read_end']) and (stat.read_count >= self.avg_stats['favorites']['read_count']): 
        if (stat.option_type=="normal" 
            and (stat.read_end*stat.read_count > ratio*float(self.avg_stats['favorites']['read_end'])*float(self.avg_stats['favorites']['read_count'])) 
            and (stat.read_end > ratio*float(self.avg_stats['favorites']['read_end'])) 
            and (stat.read_count > ratio*float(self.avg_stats['favorites']['read_count'])) 
            and (stat.read_count >= self.avg_stats['favorites']['read_count'])) : 
            result=True
        return result
    
    def threshold_removing_favorites(self,stat,discover_level):
        result = False
        if stat.option_type=="favorites" and (stat.read_end < self.avg_stats['favorites']['read_end']) and (stat.read_count >= self.avg_stats['favorites']['read_count']): 
            result=True
        return result

    #Threshold TRACK PLAYLIST : removing a track from a playlist if too many skip
    #discover_level = 5 et read_count_end=0 : skipped_count_end >=5 // and (stat.read_count_end == 0)
    #if (float(stat.skipped_count) > ((11-discover_level)*(stat.read_count_end+1)*0.7)) : 
    #if (float(stat.skipped_count) > ((5)*(stat.read_count_end + 1)*0.7)) : 
    def threshold_remove_track_playlist(self,stat,discover_level):
        result = False
        if stat.option_type=="normal":
            if (stat.read_end < self.avg_stats['normal']['read_end']) and (stat.read_count >= self.avg_stats['normal']['read_count']): result=True
        elif stat.option_type=="incoming":
            if (stat.read_end < self.avg_stats['incoming']['read_end']) and (stat.read_count >= self.avg_stats['incoming']['read_count']): result=True
        elif stat.option_type=="hidden":
            if (stat.read_end < self.avg_stats['hidden']['read_end']) and (stat.read_count >= self.avg_stats['hidden']['read_count']): result=True
        return result

#   MISC FUNCTIONS
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
