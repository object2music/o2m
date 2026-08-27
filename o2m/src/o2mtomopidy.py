import datetime, time, sys, contextlib, random, subprocess, os, threading, math, re
#import numpy as np
import random
from mopidy_podcast import Extension, feeds
from urllib import parse, error as url_error

import src.util as util
from src.dbhandler import DatabaseHandler, Track, Stats_Raw, Box
from src.spotifyhandler import SpotifyHandler
from src import radiofrance as rf

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
    expand_pick_mode = "hybrid"  # smart-selection variant: hybrid (P0) | temp (P1) | band (P2)
    cooldown_hours = 8.0         # (legacy) kept for reference; the played cooldown is now multi-day (cooldown_days)
    cooldown_mult = 0.05         # weight floor: multiplier at age 0 (just played), ramps back to 1 over the window
    cooldown_days = 2.0          # base played-cooldown window (days); a just-played track eases back to full over this
    cooldown_rc_ref = 20         # read_count giving the max window stretch (heavy-rotation tracks rest ~2× longer)
    exploit_sharpness = 1.3      # P0 exploit weight exponent (affinity**this); 2 was too repetitive
    served_cooldown_min = 30.0   # minutes; tracks just SERVED (selected) are down-weighted
    served_mult = 0.1            # weight multiplier applied within the served-cooldown window
    rest_pop_factor = 0.7        # _mood_pick: gentler popularity exponent on the off-mood fallback (1=full)

    avg_stats = {}

    def __init__(self, mopidyHandler, configO2m, configMopidy, logging):
        # `activeboxs` is declared as a CLASS attribute above (line 24) — a mutable
        # default shared by every instance unless shadowed here. Without this,
        # self.activeboxs.append(...)/.remove(...) mutate that one shared list, so
        # state can leak across O2mToMopidy re-instantiations within the same
        # process (main.py's connect-retry loop) — observed as boxes appearing
        # "already active" with no user action (stuck-boxes-like symptom).
        self.activeboxs = []
        self.configO2M = configO2m["o2m"]
        #self.configMopidy = configMopidy
        self.dbHandler = DatabaseHandler()  # Database management
        self.mopidyHandler = mopidyHandler  # Websocket mopidy for reading control
        self.spotifyHandler = SpotifyHandler() # Spotify API
        self.spotifyHandler.set_db_handler(self.dbHandler)  # enable local cache
        self.spotifyHandler.set_mopidy_handler(mopidyHandler)  # fallback source for playlists
        self.library_name_cache = {}  # Cache to avoid repeated Spotify lookups for names
        self.library_link_from_track_cache = {}  # Cache: (track_uri, hint) -> full library uri
        # Central per-track registry keyed by Mopidy tlid (always unique).
        # Replaces the parallel box.tlids / box.uris / box.option_types / box.library_link lists.
        # {tlid: {'uri': str, 'option_type': str, 'library_link': str, 'box_id': str}}
        self._track_info = {}
        # Serialize box add/remove/reload ops (Flask HTTP threads + mopidy-event thread). RLock
        # is reentrant so a cascade (box: include) re-enters on the same thread without deadlock,
        # and the `with` release is exception-safe (a failed load no longer wedges the mutex).
        self._box_lock = threading.RLock()
        self._box_lock_timeout = 30  # seconds; on timeout we proceed rather than hang forever
        self._local_to_spotify = {}  # file:// URI → spotify:track: URI for stat routing
        self._rf_published = {}      # RF episode uri → 'YYYY-MM-DD' (rows may not exist yet at fetch time)

        if "api_result_limit" in self.configO2M:
            self.max_results = int(self.configO2M["api_result_limit"])

        if "default_volume" in self.configO2M:
            self.default_volume = int(self.configO2M["default_volume"])
        self.current_volume = self.default_volume

        if "discover_level" in self.configO2M:
            self.discover_level = int(self.configO2M["discover_level"])
        #Wether discover_level is on from the outside (api) or not
        self.discover_level_on = False

        # Mood interface settings — global context defaults (0.5 = neutral/mean "5/5")
        self.mood_energy = 0.5     # float 0.0-1.0 target energy
        self.mood_valence = 0.5    # float 0.0-1.0 target valence (ambiance)
        self.mood_genres = []      # list of genre name strings

        # ── Radio now-playing + auto-save to library ─────────────────────────
        self._radio_np = None          # last known {title,artist,album,key,is_music,source} for the UI
        self._radio_last_key = None     # step/title id of the track currently on air (change = prev finished)
        self._radio_last_meta = None    # meta of the track currently on air
        self.radio_poll_sec = 15        # how often the watcher polls the active radio
        self.radio_save_min_dl = 5      # discover_level threshold to auto-save a finished radio track
        # Radio France stations keyed by EXACT stream slug → (livemeta id | None,
        # is_music, full name). Exact-slug matching (not substring) so e.g.
        # 'monpetitfranceinter' is NOT swallowed by 'franceinter'. id=None → known
        # station with no livemeta feed (show the name only, no live track).
        self._RF_STATIONS = {
            'fip':                 (7,    True,  'FIP'),
            'fiprock':             (64,   True,  'FIP Rock'),
            'fipjazz':             (65,   True,  'FIP Jazz'),
            'fipgroove':           (66,   True,  'FIP Groove'),
            'fipworld':            (69,   True,  'FIP Monde'),
            'fipnouveautes':       (70,   True,  'FIP Nouveautés'),
            'fipreggae':           (71,   True,  'FIP Reggae'),
            'fipelectro':          (74,   True,  'FIP Electro'),
            'francemusique':       (5,    True,  'France Musique'),
            'franceinter':         (1,    False, 'France Inter'),
            'franceinfo':          (2,    False, 'France Info'),
            'franceculture':       (4,    False, 'France Culture'),
            'monpetitfranceinter': (None, False, 'Mon Petit France Inter'),
        }
        # Station brand logos — the "repli 1" fallback shown as the cover when the
        # live feed carries no usable artwork (shows, station-only, streams). Keyed by
        # the same exact slug; FIP webradios share the FIP logo, PFI reuses France
        # Inter's. Public Wikimedia Commons PNG rasterisations (stable content URLs).
        # Superseded per-item by the real OpenAPI visual once the key resolves it.
        _L_FIP = 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/FIP_logo_2021.svg/250px-FIP_logo_2021.svg.png'
        _L_INTER = 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a0/France_Inter_logo_2021.svg/250px-France_Inter_logo_2021.svg.png'
        self._RF_LOGOS = {
            'fip': _L_FIP, 'fiprock': _L_FIP, 'fipjazz': _L_FIP, 'fipgroove': _L_FIP,
            'fipworld': _L_FIP, 'fipnouveautes': _L_FIP, 'fipreggae': _L_FIP, 'fipelectro': _L_FIP,
            'francemusique': 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/6c/France_Musique_logo_2021.svg/250px-France_Musique_logo_2021.svg.png',
            'franceinter': _L_INTER,
            'franceinfo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/0/03/Franceinfo.svg/250px-Franceinfo.svg.png',
            'franceculture': 'https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/France_Culture_logo_2021.svg/250px-France_Culture_logo_2021.svg.png',
            'monpetitfranceinter': _L_INTER,
        }
        # Radio France OpenAPI key (developers.radiofrance.fr) — optional. When set,
        # it will be used to resolve real show/station visuals (UUID → image URL);
        # until then the station logos above are the fallback cover.
        self._rf_api_key = (self.configO2M.get('radiofrance_api_key', '') or '').strip() or None

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
        self._health_check_last = 0  # cooldown gate for check_active_boxes_health

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
        for i in {'new','library','incoming','favorites','hidden'}:
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
        """Resolve a list of URIs, substituting local files where available.
        Defensive: coerce a bare string to a list and drop non-URI tokens (no ':'
        scheme) so a stray value (e.g. a box id) never reaches mopidy.tracklist.add,
        which would raise 'Expected a list of URIs'."""
        if not uris:
            return uris
        if isinstance(uris, str):
            uris = [uris]
        uris = [u for u in uris if isinstance(u, str) and ':' in u]
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

    @contextlib.contextmanager
    def _box_ops_lock(self):
        """Reentrant, exception-safe mutex around box add/remove/reload. Bounded acquire so a
        stuck/slow op can't wedge everything — the old self.queue polling waited up to 120s and,
        worse, never released on exception (a failed load left it stuck, so the next remove hung
        the full 120s). On timeout we proceed without the lock rather than hang forever, matching
        the old 'eventually run it' behaviour."""
        acquired = self._box_lock.acquire(timeout=self._box_lock_timeout)
        if not acquired:
            print(f"box lock: not acquired within {self._box_lock_timeout}s — proceeding anyway")
        try:
            yield
        finally:
            if acquired:
                self._box_lock.release()

    def box_action_remove(self,box,removedBox):
        with self._box_ops_lock():
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
    def one_box_changed(self, box, max_results=None):

        #print(f"\nNew box added: {box}")
        if (box.uid != self.last_box_uid):  # If different from last box added - for NFC mode only
            with self._box_ops_lock():
                uri = "box:"+box.uid
                self.update_stat_raw(uri)

                # Variables
                if max_results is None:
                    max_results = self.max_results
                    if box.option_max_results: max_results = box.option_max_results
                elif box.option_max_results:
                    # A caller-supplied budget (meta_fill's per-box share) used to bypass
                    # the box's own Max results entirely, so the editor field had no
                    # effect in auto mode. Honour it as a ceiling on the share.
                    max_results = min(max_results, box.option_max_results)
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
                if ((self.shuffle == "true" and box.option_sort != "desc" and box.option_sort != "asc") or box.option_sort == "shuffle" or box.option_sort == "smart") and (current_tl_length > prev_tl_length):
                    index = 0
                    if self.mopidyHandler.tracklist.index() != None: index = int(self.mopidyHandler.tracklist.index())
                    if current_tl_length > index + 1:
                        self.smart_shuffle_tracklist(index+1, current_tl_length)

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
        go = self.add_tracks(box, self.get_common_tracks(datetime.datetime.now().hour,window,max_results), max_results, "library","o2m:history")
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

                # Enforce the budget. max_results was only ever used as a `> 0` guard
                # here, so the whole list was added whatever the caller asked for:
                # every caller passes a computed budget (meta_fill's per-box share,
                # `remaining` in one_box_changed, the auto mix's base_counts) and a
                # source that returns more than its share — a long YouTube playlist,
                # a full podcast feed — silently blew past it. That is how a 30-track
                # podcast actuator ended up queueing 142.
                if len(uris) > max_results:
                    print(f"add_tracks: capping {len(uris)} uris to max_results={max_results}")
                    uris = uris[:max_results]

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
                                    or (stat.option_type == 'trash' or stat.option_type == 'hidden' or stat.option_type == 'library' or stat.option_type == 'incoming')
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
                    if (self.shuffle == "true" and active_box.option_sort != "desc" and active_box.option_sort != "asc") or active_box.option_sort == "shuffle" or active_box.option_sort == "smart":
                        if new_length > prev_length:
                            print(f"Shuffling")
                            self.smart_shuffle_tracklist(prev_length, new_length)
                    
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
                    # 'new' excluded: the new context must play unheard tracks, not recommendations.
                    # podcast/info excluded: they are spoken content — never inject music recos there.
                    if discover_level > 0 and discover_level < 10 and self.option_add_reco_after_track and window_replace < len(slice2) and option_type not in ['hidden','trash','new','podcast','info']:
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
                    _enrich_items = []  # feature-less tracks to enrich preemptively (async)
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

                            # Queue feature-less, unlocked tracks for preemptive enrichment.
                            if (stat is not None and getattr(stat, 'mood_edited_at', None) is None
                                    and (stat.mood is None or stat.mood == '_' or stat.energy is None)):
                                _enrich_items.append((tl_track.track, track_uri))

                            # Spoken content: fill what makes an episode readable in the
                            # panel — title, publication date and the channel it belongs
                            # to. Done HERE because this is where the row is created; the
                            # earlier attempt ran before that and updated nothing. Episodes
                            # reaching the tracklist outside the catalogue warmup (a news
                            # flash from 'infos:library', a resumed item) had no metadata
                            # at all as a result.
                            if self._is_spoken_uri(track_uri):
                                try:
                                    self._fill_spoken_meta(stat, tl_track.track, track_uri)
                                except Exception as e:
                                    print(f"spoken meta ({track_uri}): {e}")

                            if (not getattr(stat, 'option_type', None)) and track_option_type:
                                stat.option_type = track_option_type

                            if library_display:
                                stat.in_library = library_display

                            stat.save()
                        except Exception as e:
                            print(f"Error saving stats for {track_uri}: {e}")

                    # Preemptive mood enrichment for the just-added feature-less tracks
                    # (one background worker, sequential in play order, rate-limit aware).
                    self._enrich_tracks_preemptive(_enrich_items)

                    # Shuffle complete computed tracklist if more than two boxs
                    #self.shuffle_tracklist(current_index + 1, new_length)
                    if (len(self.activeboxs) > 1 or active_box.option_sort=="shuffle" or active_box.option_sort=="smart") and not((option_type == "info") and (new_length - prev_length==1) and (current_index <= 1)):
                        if new_length > current_index + 1:
                            print ("shuffling")
                            self.smart_shuffle_tracklist(current_index + 1, new_length)
                   
                    #Move at next place the lastinfo content
                    if ((option_type == "info") and (new_length - prev_length==1)):
                        index = self.mopidyHandler.tracklist.index(tl_track=tltracks_added[0])
                        self.mopidyHandler.tracklist.move(index, index, current_index+1)
                    
                    #print(f"\nTracks added to Box {box} with option_types {box.option_types} and library_link {box.library_link} \n")
        return (length)

    def _enrich_track_features_sync(self, track, uri, stat=None):
        """Enrich (mood/energy/valence) one track via Last.fm if it lacks them.
        Blocking — call from a background thread. Skips already-enriched, non-music,
        and manually-locked tracks (update_track_features also refuses locked ones)."""
        try:
            if stat is None and self.dbHandler.stat_exists(uri):
                stat = self.dbHandler.get_stat_by_uri(uri)
        except Exception:
            stat = None
        if stat is not None and getattr(stat, 'mood_edited_at', None) is not None:
            return  # manually locked
        needs = (stat is None or stat.mood is None or stat.mood == '_'
                 or (stat.energy is None and stat.mood not in (None, '_')))
        if not needs:
            return
        name = getattr(track, 'name', None)
        artists = getattr(track, 'artists', None) or []
        artist = next((a.name for a in artists if getattr(a, 'name', None)), None)
        album = getattr(track, 'album', None)
        album_name = getattr(album, 'name', None)
        album_uri = getattr(album, 'uri', None) or ''
        album_id = album_uri.split(':')[-1] if ':' in album_uri else None
        if not (name and artist) or any(s in uri for s in ('podcast', 'rss', 'http://', 'https://')):
            return
        try:
            mood, energy, valence = self.spotifyHandler._lastfm_get_track_mood(
                artist, name, album_name, track_uri=uri, album_id=album_id)
            if mood or energy is not None:
                self.dbHandler.update_track_features(uri, mood=mood, energy=energy, valence=valence)
                print(f"deferred mood: {artist} – {name} → mood={mood} e={energy} v={valence}")
            else:
                self.dbHandler.update_track_features(uri, mood='_')
        except Exception as e:
            print(f"deferred mood error ({name}): {e}")

    def _enrich_track_features_async(self, track, uri, stat=None):
        """Background single-track enrichment (deferred, on playback end)."""
        threading.Thread(target=self._enrich_track_features_sync,
                         args=(track, uri, stat), daemon=True).start()

    def _enrich_tracks_preemptive(self, items):
        """Enrich a batch of just-added feature-less tracks in ONE background worker,
        sequentially in play order and rate-limit aware — so queued tracks get their
        mood/energy/valence before playback, without a burst of concurrent Last.fm
        calls. items = [(track, uri), ...]. Non-blocking."""
        if not items:
            return
        def _worker():
            for track, uri in items:
                try:
                    if self.spotifyHandler._is_rate_limited():
                        break
                    self._enrich_track_features_sync(track, uri)
                    time.sleep(0.25)
                except Exception as e:
                    print(f"preemptive enrich error: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def tracklistfill_auto(self,active_box,max_results=20,discover_level=5,mode='normal'):
        #box is the active box in memory and box1,2.. the database contents of boxes
        try:
            print (f"DL AUTO : {discover_level}")
            #GO QUICKLY
            self.quicklaunch_auto(1,discover_level,active_box)

            #Variables
            window = int(round(discover_level / 2))
            tracklist_uris= []

            # Effective mood criteria: box option overrides else global context (default 0.5/0.5).
            # Applied to every entry below to bias selection towards energy/ambiance.
            energy = getattr(active_box, 'option_energy', None)
            if energy is None: energy = self.mood_energy
            valence = getattr(active_box, 'option_valence', None)
            if valence is None: valence = self.mood_valence
            radius = discover_level / 20.0 + 0.05   # DL=0 → 0.05, DL=10 → 0.55 (same as apply_mood_settings)
            OVERSAMPLE, POOL_CAP = 3, 60
            def _pool(c): return min(c * OVERSAMPLE, POOL_CAP)   # oversampled fetch size for an entry
            print(f"AUTO mood criteria: energy={energy} valence={valence} radius={round(radius,2)}")

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
                common = self.get_common_tracks(datetime.datetime.now().hour,window,_pool(base_counts['common']))
                common = self._mood_pick(common, base_counts['common'], energy, valence, radius, discover_level)
                self.add_tracks(active_box, common, base_counts['common'], "library","o2m:history")

            #Incoming
            if base_counts.get('incoming', 0) > 0:
                print(f"\nAUTO : Incoming {base_counts['incoming']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('incoming')
                library_link = self.get_spotify_playlist_from_box(box1)
                incoming = self.tracklistappend_box(box1,_pool(base_counts['incoming']),attribute_to=active_box)
                incoming = self._mood_pick(incoming, base_counts['incoming'], energy, valence, radius, discover_level)
                self.add_tracks(active_box, incoming, base_counts['incoming'], "incoming",library_link)

            #Favorites
            if base_counts.get('favorites', 0) > 0:
                print(f"\nAUTO : Fav {base_counts['favorites']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('favorites')
                #Using spotify favs
                if self.username !=None:
                    fav = self.spotifyHandler.get_library_favorite_tracks(_pool(base_counts['favorites']))
                    fav = self._mood_pick(fav, base_counts['favorites'], energy, valence, radius, discover_level)
                    library_link = 'o2m:favorites'
                    self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)
                #Using specific playlist (normaly elif)
                if box1 != None:
                    fav= self.tracklistappend_box(box1,_pool(base_counts['favorites']),attribute_to=active_box)
                    fav = self._mood_pick(fav, base_counts['favorites'], energy, valence, radius, discover_level)
                    library_link = self.get_spotify_playlist_from_box(box1)
                    self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)
                #if fav != None: self.add_tracks(active_box, fav, base_counts['favorites'], "favorites",library_link)

            #Podcasts (only in podcast mode)
            if mode=='podcast' and base_counts.get('podcasts', 0) > 0:
                box1 = self.dbHandler.get_box_by_option_type('podcast')
                if box1:
                    print(f"\nAUTO : Podcasts {base_counts['podcasts']} tracks\n")                
                    self.add_tracks(active_box, self.tracklistappend_box(box1,base_counts['podcasts'],attribute_to=active_box), base_counts['podcasts'], "podcast","o2m:podcast")
            
            #Albums/Artists
            if base_counts.get('albums_artists', 0) > 0:
                if (random.choice([1,2])) == 1:
                    print(f"\nAUTO : Albums {base_counts['albums_artists']} tracks\n")
                    aa = self.spotifyHandler.get_my_albums_tracks(_pool(base_counts['albums_artists']),discover_level)
                    aa = self._mood_pick(aa, base_counts['albums_artists'], energy, valence, radius, discover_level)
                    self.add_tracks(active_box, aa, base_counts['albums_artists'], "library","spotify:album")
                else:
                    print(f"\nAUTO : Artists {base_counts['albums_artists']} tracks\n")
                    aa = self.spotifyHandler.get_my_artists_tracks(_pool(base_counts['albums_artists']),discover_level)
                    aa = self._mood_pick(aa, base_counts['albums_artists'], energy, valence, radius, discover_level)
                    self.add_tracks(active_box, aa, base_counts['albums_artists'], "library","spotify:artist")

            #Playlists
            if base_counts.get('playlists', 0) > 0:
                pl_tracks,lib_link = self.spotifyHandler.get_playlists_tracks(_pool(base_counts['playlists']),discover_level)
                # Mood-bias the playlist pool while keeping each uri paired with its library link
                link_by_uri = dict(zip(pl_tracks, lib_link))
                pl_tracks = self._mood_pick(pl_tracks, base_counts['playlists'], energy, valence, radius, discover_level)
                print(f"\nAUTO : Playlist {base_counts['playlists']} tracks and {len(pl_tracks)} size \n")
                for u in pl_tracks:
                    self.add_tracks(active_box, uris=[u], max_results=1, force_option_type="library", library_link=link_by_uri.get(u, ''))

            #News
            if base_counts.get('news', 0) > 0:
                print(f"\nAUTO : News {base_counts['news']} tracks\n")
                box1 = self.dbHandler.get_box_by_option_type('new')
                news = self.tracklistappend_box(box1,_pool(base_counts['news']),attribute_to=active_box)
                news = self._mood_pick(news, base_counts['news'], energy, valence, radius, discover_level)
                self.add_tracks(active_box, news, base_counts['news'], "new","o2m:new")
    
        except Exception as val_e: 
            print(f"Erreur : {val_e}")

#TRACKLIST APPEND / MANAGEMENT 
    
    #Tracklist filling from box
#BASIC CATEGORIES (shared by /api/basic_boxes, /api/basic_toggle and the meta_* box patterns)
    _META_PATTERNS = {'meta_podcasts': 'podcast', 'meta_infos': 'info', 'meta_radios': 'radio'}

    _STREAM_RE = re.compile(r'https?://\S+\.(aac|mp3|m3u8)\b|icecast', re.I)

    def _box_category(self, data, option_type):
        """Classify any box (pinned or not) into a basic-view category, given its
        data/option_type. None = cascade/meta scenario box (not a direct source
        of any kind — leave it alone). 'other' = a direct, non-cascade box that
        isn't podcast/info/radio (e.g. a plain library/new box) — not one of the
        4 actuators' fill sources, but still swept up by Music OFF's catch-all
        (see meta_remove) so it doesn't get orphaned once activated some other
        way (Full view, NFC, cascade)."""
        data = data or ''
        if re.search(r'^\s*box:', data, re.M) or re.search(r'^\s*meta_', data, re.M):
            return None
        if re.search(r'^\s*auto:', data, re.M):
            return 'music'
        if option_type == 'podcast':
            return 'podcast'
        if option_type == 'info':
            return 'info'
        if self._STREAM_RE.search(data):
            return 'radio'
        return 'other'

    def get_basic_categories(self):
        """Pinned boxes grouped into the basic-view categories (direct sources only).
        music: data has an 'auto:' line · podcast/info: by option_type · radio: data
        carries direct audio-stream URLs. Cascade boxes ('box:' lines), meta boxes
        ('meta_*' lines) and anything else uncategorized ('other') are excluded —
        they are scenarios or not a fill source, not one of the 4 direct sources."""
        cats = {'music': [], 'podcast': [], 'info': [], 'radio': []}
        for b in self.dbHandler.get_boxes_pinned():
            cat = self._box_category(b.get('data'), b.get('option_type'))
            if cat in cats:
                cats[cat].append(b)
        return cats

    def search_radio_stations(self, query):
        """Keyword search over radio station names — the content-search feature's
        radio source. Stations aren't Track-backed (a live stream is never logged
        the way a played track is); their only record is the '#Label' comment
        line immediately preceding each stream URL inside a radio-category box's
        data (the established convention — see e.g. the 'Radios' box). Reuses
        get_basic_categories()['radio'] so this stays in sync with whatever
        counts as a direct radio source elsewhere (basic-view actuator, etc)."""
        q = (query or '').lower()
        if not q:
            return []
        results = []
        for meta in self.get_basic_categories().get('radio') or []:
            box = self.dbHandler.get_box_by_uid(meta['uid'])
            if box is None:
                continue
            label = None
            for raw in (box.data or '').splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    label = line.lstrip('#').strip()
                    continue
                if line.startswith('http') and label:
                    if q in label.lower():
                        results.append({'uri': line, 'name': label, 'box_uid': box.uid})
                    label = None
        return results

    def list_podcast_channels(self):
        """All referenced podcast *channels*. Like radios, a channel has no Track
        record: it's a '#Label' comment line immediately preceding an active
        'podcast+<feed_url>' line inside a box's data (podcast/info/hidden boxes).
        Returns the mopidy-podcast URI (O2M's '?max_results=' hint stripped) so a
        result can be browsed into episodes and played directly. Disabled
        ('#podcast+…') lines are skipped. Deduped by feed."""
        results, seen = [], set()
        for box in Box.select():
            label = None
            for raw in (box.data or '').splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('podcast+'):
                    feed = re.sub(r'[?&]max_results=\d+', '', line)
                    if label and feed not in seen:
                        seen.add(feed)
                        results.append({'uri': feed, 'name': label, 'box_uid': box.uid})
                    label = None
                elif line.startswith('#') and 'podcast+' not in line and 'yt' not in line.lower():
                    label = line.lstrip('#').strip()
                else:
                    label = None
        results.sort(key=lambda c: c['name'].lower())
        return results[:200]

    def search_podcast_channels(self, query):
        """Keyword search over podcast channel labels — the podcast half of the
        content-search feature (see list_podcast_channels)."""
        q = (query or '').lower()
        if not q:
            return []
        return [c for c in self.list_podcast_channels() if q in c['name'].lower()][:20]

    def _pick_box_by_recency(self, boxes):
        """Recency × chance: rank by last_read_date, halving weights per rank."""
        def ts(b):
            lr = b.get('last_read_date')
            try:
                return lr.timestamp() if hasattr(lr, 'timestamp') else float(lr or 0)
            except Exception:
                return 0
        ranked = sorted(boxes, key=ts, reverse=True)
        weights = [2 ** -i for i in range(len(ranked))]
        return random.choices(ranked, weights=weights, k=1)[0]

    def meta_fill(self, cat, max_results=None):
        """Activate a category's sources within a max_results budget. music/radio
        are single-source (the mood engine sizes itself / a stream is endless) —
        one pick by recency×chance, unchanged. podcast/info activate ALL their
        (not-yet-active) sources at once, each asked for an equal share of the
        budget (limit // N); a source that can't fill its share (e.g. a 1-track
        news box) has its shortfall carried forward and redistributed equally
        across the sources processed after it, so a thin source doesn't leave the
        category under-filled when richer sources could have covered it. Runs
        server-side so an actuator tap is atomic — no client loop to interrupt.
        Locked (reentrant) around the whole read-modify-write of activeboxs: without
        it, tapping two actuators quickly (or racing the check_active_boxes_health
        watchdog) let two threads mutate the shared activeboxs list concurrently —
        a remove() on one thread's stale snapshot could raise/skip while another
        thread's box_action_remove never ran, leaving that box's tracks stuck in
        the tracklist even though the box looked deactivated."""
        with self._box_ops_lock():
            limit = max_results or self.max_results
            boxes = self.get_basic_categories().get(cat) or []
            if not boxes:
                return 0
            try:
                start = self.mopidyHandler.tracklist.get_length()
            except Exception:
                start = 0

            if cat in ('music', 'radio'):
                # Single-source: one pick by recency×chance, as before.
                pool = [b for b in boxes if not any(a.uid == b['uid'] for a in self.activeboxs)]
                if not pool:
                    return 0
                meta = self._pick_box_by_recency(pool)
                sub = self.dbHandler.get_box_by_uid(meta['uid'])
                if sub is None:
                    return 0
                self.activeboxs.append(sub)
                try:
                    self.box_action(sub)
                except Exception as e:
                    print(f"meta_fill({cat}) on {sub.uid}: {e}")
                try:
                    return self.mopidyHandler.tracklist.get_length() - start
                except Exception:
                    return limit

            # Multi-source: equal split across every not-yet-active source, with
            # a running budget so an underfilled source's shortfall rolls forward.
            pool = [b for b in boxes if not any(a.uid == b['uid'] for a in self.activeboxs)]
            if not pool:
                return 0
            gained_total = 0
            budget = limit
            for i, meta in enumerate(pool):
                sub = self.dbHandler.get_box_by_uid(meta['uid'])
                if sub is None:
                    continue
                share = max(1, round(budget / (len(pool) - i)))
                self.activeboxs.append(sub)
                try:
                    before = self.mopidyHandler.tracklist.get_length()
                except Exception:
                    before = None
                try:
                    self.one_box_changed(sub, max_results=share)
                except Exception as e:
                    print(f"meta_fill({cat}) on {sub.uid}: {e}")
                try:
                    got = self.mopidyHandler.tracklist.get_length() - before if before is not None else share
                except Exception:
                    got = share
                gained_total += got
                budget -= got   # a shortfall (got < share) rolls forward; a surplus tightens the rest
                if budget <= 0:
                    break
            return gained_total

    def meta_remove(self, cat):
        """Deactivate every active box of a category (mirror of meta_fill). See
        meta_fill's docstring for why this needs the same lock.

        Music is the catch-all bucket: it ALSO sweeps up any currently-active box
        that isn't podcast/info/radio/cascade/meta either (checked directly on the
        live box, not just the pinned list, so an unpinned one — Full view, NFC,
        cascade — isn't missed). Without this, a plain library/new-style box
        activated some other way than the Music actuator (e.g. a pinned
        'newnotcompleted:library' box tapped in the Full view's Boxes panel) has
        no category claiming it, so no actuator — including Music OFF — could
        ever remove its tracks; they'd sit in the tracklist forever."""
        with self._box_ops_lock():
            uids = {b['uid'] for b in (self.get_basic_categories().get(cat) or [])}
            if cat == 'music':
                for b in self.activeboxs:
                    if self._box_category(b.data, b.option_type) in ('music', 'other'):
                        uids.add(b.uid)
            removed = 0
            for b in [x for x in self.activeboxs if x.uid in uids]:
                try:
                    if b not in self.activeboxs:
                        continue   # already removed by a concurrent call in this same lock window
                    self.activeboxs.remove(b)
                    self.box_action_remove(b, b)
                    removed += 1
                except Exception as e:
                    print(f"meta_remove({cat}) on {b.uid}: {e}")
            return removed

    def tracklistappend_box(self,box,max_results,attribute_to=None):
        # attribute_to: the box that dynamically-added tracks (skip badge, box_id
        # in _track_info, and hence deactivation cleanup) get tagged under.
        # Defaults to `box` itself (the normal case: a box's own data is being
        # read to fill ITS OWN tracklist entry). Some content patterns below
        # (spotify:library / newnotcompleted:library / newrecent:library /
        # albums:spotify) call add_tracks internally rather than returning URIs
        # to the caller — when tracklistappend_box is instead called to borrow
        # ANOTHER box's content on behalf of a currently-active box (e.g.
        # tracklistfill_auto's "News" component reads the option_type='new' box
        # to mix a few of its tracks into Music/Auto's own mix), those internal
        # calls used to tag tracks under `box` (the box being READ) instead of
        # the box actually being activated — so turning that active box off
        # could never find/remove them (observed: Music off left "Newnotcompleted"
        # tracks stuck when other actuators were still active and the box-count
        # never dropped to 0, which is when a separate blanket-clear fallback
        # would otherwise have masked the issue). Pass attribute_to to fix that.
        tag_box = attribute_to or box
        #Variables
        tracklist_uris = []
        tl_length_at_start = self.mopidyHandler.tracklist.get_length()
        if max_results>0:
            
            #If discover level has been pushed by api since the begining of session, we priorise it
            discover_level = self.discover_level
            if not(self.discover_level_on) and (self.get_option_for_box(box, "option_discover_level")!=None) :
                discover_level = self.get_option_for_box(box, "option_discover_level")

            # Effective mood criteria for cache-expansion filtering (box option else global context)
            energy = getattr(box, 'option_energy', None)
            if energy is None: energy = self.mood_energy
            valence = getattr(box, 'option_valence', None)
            if valence is None: valence = self.mood_valence

            # Smart selection (popularity/mood/cooldown via _expand_pick) is the DEFAULT:
            # it applies when option_sort is 'smart' OR unspecified (NULL/empty).
            # Only an explicit basic mode (shuffle/asc/desc) opts out to the legacy path.
            smart = ((getattr(box, 'option_sort', None) or 'smart') == 'smart')

            #DB Regulation (tmp)
            #self.reg_box_db(box)
            content = 0

            # Looping on hybrid playlist (delimited by \n)
            data = box.data.split("\n")
            data = [x for x in data if not x.startswith('#')]
            data = [x for x in data if not x.startswith('\r')]
            data = [x.replace('\r', '') for x in data]

            # Podcast feeds share the box's budget instead of each taking all of it.
            # Without this, every 'podcast+' line was handed the SAME max_results, so
            # a long feed (Banzaii, 24 episodes) flooded the tracklist while a short
            # one (Very good trip, 6 published) contributed a fraction — the mix was
            # driven by feed length, not by any intent. Same rolling-budget rule as
            # meta_fill uses across boxes: an equal share each, and the shortfall of a
            # thin feed rolls forward to the ones processed after it.
            _pod_feeds = [x for x in data if 'podcast+' in x and '#' not in x]
            _pod_left = len(_pod_feeds)
            _pod_budget = max_results

            # Warm the Radio France episode cache for every 'rf:sujet:' line at once.
            # Each line costs one API call per station, and the loop below is
            # sequential, so a box holding a dozen subjects took ~55s to activate —
            # long enough that the UI looks like it did nothing. The lookups are
            # independent and IO-bound, so run them concurrently here; the loop then
            # hits radiofrance's short-lived cache and returns immediately.
            _rf_lines = [x.strip() for x in data
                         if x.strip().startswith(('rf:sujet:', 'rf:subject:'))]
            _rf_done = {}
            if len(_rf_lines) > 1 and self.rf_enabled():
                import concurrent.futures as _cf
                def _warm(line):
                    try:
                        value, _sep, st = line.split(':', 2)[2].partition('@')
                        picked = [rf.STATIONS.get(x.strip().lower(), x.strip().upper())
                                  for x in st.split(',') if x.strip()]
                        return line, self.rf_subject_episodes(value.strip(), max_results,
                                                              picked or None)
                    except Exception as e:
                        print(f"rf:sujet prefetch ({line}): {e}")
                        return line, []
                try:
                    with _cf.ThreadPoolExecutor(max_workers=min(8, len(_rf_lines))) as _ex:
                        for _line, _uris in _ex.map(_warm, _rf_lines):
                            _rf_done[_line] = _uris
                except Exception as e:
                    print(f"rf:sujet prefetch pool: {e}")

            for content in data:
                #Other box called (cascade include)
                if "box:" in content :
                    box_uid = content.split(":", 1)[1].strip()
                    sub_box = self.dbHandler.get_box_by_uid(box_uid)
                    if sub_box is None:
                        print(f"box include: unknown box uid '{box_uid}' — skipped")
                        continue
                    # Dedup: don't register the same included box twice (it made activeboxs
                    # grow and double-loaded on the next reload).
                    if not any(b.uid == sub_box.uid for b in self.activeboxs):
                        self.activeboxs.append(sub_box)  #adding box to list
                    # During a full reload, load each box at most once per cycle so a cascade
                    # include + a direct reload don't double it.
                    seen = getattr(self, '_reload_seen', None)
                    if seen is not None:
                        if sub_box.uid in seen:
                            continue
                        seen.add(sub_box.uid)
                    print(f"added box {sub_box}")
                    self.box_action(sub_box)
                
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

                # meta_podcasts / meta_infos / meta_radios — category fills (the basic-view
                # actuators as box patterns): sources drawn recency × chance until the
                # limit is reached. Music's equivalent is auto:library above.
                elif content.strip() in self._META_PATTERNS:
                    self.meta_fill(self._META_PATTERNS[content.strip()], max_results)

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
                        self.add_tracks(tag_box, [uri], remaining, library_link=source or '')

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
                            self.add_tracks(tag_box, uri_new, remaining, library_link='o2m:newnotcompleted', bypass_remove_filter=True)

                # newrecent:library — pre-filtered in DB, bypass REMOVE in add_tracks
                elif "newrecent:library" in content:
                    remaining = max(0, max_results - (self.mopidyHandler.tracklist.get_length() - tl_length_at_start))
                    if remaining > 0:
                        days = 60
                        uri_new = self.get_newrecent_tracks(remaining, days)
                        if uri_new:
                            self.add_tracks(tag_box, uri_new, remaining, library_link='o2m:newrecent', bypass_remove_filter=True)

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
                            self.add_tracks(tag_box, uris, remaining, library_link=source or '')

                # Autos mode (to be optimized with the above code)
                elif "auto:library" in content:
                    tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level))

                elif "auto_simple:library" in content:
                    tracklist_uris.append(self.tracklistfill_auto(box,max_results,discover_level,'simple'))

                elif "infos:library" in content:
                    tracklist_uris.append(self.lastinfos(box,max_results))

                # Unfinished podcasts
                elif "podcasts:unfinished" in content:
                    uris = self.dbHandler.get_uris_podcasts_notread(max_results, discover_level)
                    if uris:
                        tracklist_uris.append(uris)

                # Radio France (OpenAPI). 'rf:show:<page url>' = one show, latest
                # unheard episodes; 'rf:sujet:<theme|tag>' (alias 'rf:subject:')
                # = a DYNAMIC box, whatever the stations published on that
                # subject over the API's 7-day window. RF's RSS is broken
                # server-side, so both expand through the API into plain https
                # mp3 URIs, which mopidy plays directly.
                elif content.strip().startswith('rf:'):
                    rf_line = content.strip()
                    if rf_line.startswith('rf:show:'):
                        tracklist_uris.append(
                            self.rf_show_episodes(rf_line[len('rf:show:'):], max_results))
                    elif rf_line.startswith(('rf:sujet:', 'rf:subject:')):
                        if rf_line in _rf_done:
                            tracklist_uris.append(_rf_done[rf_line])
                        else:
                            value, _sep, stations = rf_line.split(':', 2)[2].partition('@')
                            picked = [rf.STATIONS.get(x.strip().lower(), x.strip().upper())
                                      for x in stations.split(',') if x.strip()]
                            tracklist_uris.append(
                                self.rf_subject_episodes(value.strip(), max_results, picked or None))

                # Podcast channel
                elif "podcast+" in content and "#" not in content:
                    print(f"Podcast channel : {content}")
                    self.update_stat_raw(content)
                    _share = max(1, round(_pod_budget / _pod_left)) if _pod_left > 0 else max_results
                    _got = self.add_podcast_from_channel(box, content, _share)
                    _pod_left = max(0, _pod_left - 1)
                    _pod_budget = max(0, _pod_budget - len(_got or []))
                    tracklist_uris.append(_got)
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
                        # Smart only: expand the artist's cached tracks and stochastically pick.
                        cached = self.dbHandler.get_artist_track_uris(media_parts[2]) if smart else None
                        if cached:
                            tracklist_uris.append(self._expand_pick(cached, max_results, energy, valence, discover_level, exclude_hidden=(getattr(box, 'option_type', '') not in ('hidden', 'trash'))))
                        else:
                            # Basic / cache-miss: legacy top + all tracks (may hit the API)
                            tracks_uris = self.spotifyHandler.get_artist_top_tracks(media_parts[2])  # 10 tops tracks of artist
                            tracklist_uris.append(self.spotifyHandler.get_artist_all_tracks(media_parts[2], limit=max_results - 10))  # all tracks of artist with no specific order
                    elif media_parts[1] == "album":
                        # Smart only: expand album sub-tracks from AlbumTrack and stochastically pick.
                        cached = self.dbHandler.get_album_tracks(media_parts[2]) if smart else None
                        if cached:
                            tracklist_uris.append(self._expand_pick(cached, max_results, energy, valence, discover_level, exclude_hidden=(getattr(box, 'option_type', '') not in ('hidden', 'trash'))))
                        else:
                            tracklist_uris.append(content)  # basic: raw URI, Mopidy resolves the whole album
                    elif media_parts[1] == "playlist":
                        if smart:
                            # Cache playlist content if not already fresh (cache-first, 1 API call max)
                            self.spotifyHandler.cache_playlist_by_id(media_parts[2])
                            cached = self.dbHandler.get_playlist_track_uris(media_parts[2])
                        else:
                            cached = None
                        if cached:
                            tracklist_uris.append(self._expand_pick(cached, max_results, energy, valence, discover_level, exclude_hidden=(getattr(box, 'option_type', '') not in ('hidden', 'trash'))))
                        else:
                            tracklist_uris.append(content)  # basic: raw URI, Mopidy resolves the whole playlist
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
        # '?max_results=N' on the feed is a CEILING combined with the share the box
        # allocated — it used to REPLACE it, which let one feed ignore the budget
        # entirely (and silently defeated meta_fill's equal split in auto mode).
        if 'max_results' in par : max_results_pod = min(int(par['max_results'][0]), max_results)
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
            with contextlib.closing(f) as source:
                feed = feeds.parse(source)
            print(f"option_sort : {self.option_sort}")
            shows = list(feed.items(self.option_sort))
            # Conserve les max_results premiers épisodes
            del shows[self.max_results :]
            return shows
        except (url_error.HTTPError, url_error.URLError) as e:
            print(f"Podcast feed unavailable ({url}): {e}")
            return []
        except Exception as e:
            # Read timeout ('The read operation timed out'), malformed feed, etc. Skip THIS
            # feed instead of letting it bubble up to box_action, which would swallow it and
            # drop the whole podcast/info half of a cascade (intermittent 'no podcasts').
            print(f"Podcast feed skipped ({url}): {e}")
            return []

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
                #This is a podcast, never finished (read_count_end == 0), last listen < 0.9, not a promo
                if (stat_pod.option_type == "podcast" and not stat_pod.read_count_end > 0 and stat_pod.read_end < 0.9 and "app_rf_promotion" not in item.uri): uris.append(item.uri)
                #This is an info and podcast and read_end proportion < 0.9 and not a promotion podcast
                elif (not stat_pod.read_count_end > 0 and "app_rf_promotion" not in item.uri): uris.append(item.uri)
            elif ("app_rf_promotion" not in item.uri): uris.append(item.uri)
        #print(f"Show {shows}")
        #print(f"Unread Show {unread_shows}")
        return uris

    def _unread_spoken_uris(self, uris):
        """Keep only episodes not already finished/abandoned, and never promos.
        Extracted from get_unread_podcasts so RSS podcasts and Radio France
        OpenAPI episodes (plain https mp3, no 'podcast+' marker) share one rule."""
        out = []
        for uri in uris or []:
            if not uri or "app_rf_promotion" in uri:
                continue
            stat = self.dbHandler.get_stat_by_uri(uri)
            if stat is None:
                out.append(uri)
            elif not stat.read_count_end > 0 and (stat.read_end or 0) < 0.9:
                out.append(uri)
        return out

    # ── Radio France (OpenAPI) ────────────────────────────────────────────────

    def rf_enabled(self):
        return bool(self._rf_api_key)

    def rf_stations(self):
        """Stations scanned by 'rf:sujet:' when the line names none. Spoken
        content lives on Culture/Inter; overridable in o2m.conf."""
        raw = (self.configO2M.get('radiofrance_stations', '') or '').strip()
        if raw:
            picked = [rf.STATIONS.get(x.strip().lower().replace(' ', ''), x.strip().upper())
                      for x in raw.split(',') if x.strip()]
            if picked:
                return picked
        return list(rf.DEFAULT_STATIONS)

    def search_rf_shows(self, query, limit=15, offset=0):
        """RF show catalogue keyword search. DB-only: the OpenAPI has no keyword
        search over shows, the catalogue is indexed by warmup_rf_shows."""
        return self.dbHandler.search_rf_shows(query, limit=limit, offset=offset)

    def rf_resolve_url(self, url):
        """A pasted radiofrance.fr URL -> {'show': <channel row>, 'episodes': [...]}.
        Show pages resolve directly; an EPISODE page resolves its parent show
        (showByUrl answers 'Not a show' for one) and pins that episode first."""
        if not self.rf_enabled():
            return None
        info = rf.parse_rf_url(url)
        if not info:
            return None
        show = rf.show_by_url(self._rf_api_key, info['show_url'])
        episodes = rf.episodes_of_show(self._rf_api_key, info['show_url'], first=20)
        if info.get('kind') == 'episode' and (info.get('episode_slug') or info.get('episode_id')):
            slug, eid = info.get('episode_slug') or '', info.get('episode_id') or ''
            def _is_target(e):
                page = e.get('page_url') or ''
                return (slug and slug in page) or (eid and eid in page)
            episodes.sort(key=lambda e: 0 if _is_target(e) else 1)
        if not show and not episodes:
            return None
        return {'show': show, 'episodes': episodes}

    def rf_show_episodes(self, show_url, max_results=15):
        """Latest unheard episodes of an RF show — the RSS-less equivalent of
        add_podcast_from_channel (RF's Show.podcast{rss} faults server-side)."""
        if not show_url:
            return []
        cached = self.dbHandler.get_episodes_by_channel(show_url, limit=max(max_results * 3, 30))
        ready = self._unread_spoken_uris(cached)[:max_results]
        if ready or self._podcast_cache_fresh():
            return ready
        if not self.rf_enabled():
            return []
        eps = self._rf_convert(
            rf.episodes_of_show(self._rf_api_key, show_url, first=max(max_results * 2, 20)))
        for e in eps:
            self._remember_rf_published(e)
        return self._unread_spoken_uris([e['uri'] for e in eps])[:max_results]

    def _remember_rf_published(self, episode):
        """Stash an RF episode's publication date. Their URIs are plain mp3 links,
        so mopidy resolves no metadata for them — the API is the only source.
        published_date is a unix timestamp; normalise it to the 'YYYY-MM-DD' the
        feed-based path already stores."""
        try:
            raw = episode.get('published')
            if not raw:
                return
            day = datetime.datetime.utcfromtimestamp(int(raw)).strftime('%Y-%m-%d')
            self._rf_published[episode['uri']] = day
            self.dbHandler.set_track_published(episode['uri'], day)
        except Exception:
            pass

    def rf_taxonomy_ids(self, value):
        """Keyword or raw taxonomy id -> filters for diffusions(), bucketed by the
        theme's DEPTH in its path: diffusions takes themes / subthemes /
        subsubthemes as separate arguments, and a depth-2 theme such as
        'arts-divertissements/cinema' matches nothing when passed as `themes`.
        Tags have no hierarchy and always go to `tags`."""
        hits = self.dbHandler.find_rf_taxonomy(value)
        buckets = {'themes': [], 'subthemes': [], 'subsubthemes': [], 'tags': []}
        # ONE id only. diffusions() INTERSECTS the ids it is given (verified:
        # Climat alone 7 episodes, Géopolitique alone 4, both together 0), so
        # passing every fuzzy match for a keyword would reliably return nothing.
        # find_rf_taxonomy already ranks exact before partial and THEME before TAG,
        # so the first hit is the best match.
        for h in hits[:1]:
            if (h.get('kind') or '') == 'TAG':
                buckets['tags'].append(h['id'])
                continue
            depth = (h.get('path') or '').count('/') + 1 if h.get('path') else 1
            key = 'themes' if depth <= 1 else ('subthemes' if depth == 2 else 'subsubthemes')
            buckets[key].append(h['id'])
        return buckets

    def rf_subject_episodes(self, keyword, max_results=15, stations=None):
        """Dynamic subject box: what the stations published on a theme/tag over
        the API's 7-day window, merged and de-duplicated."""
        if not self.rf_enabled() or not keyword:
            return []
        f = self.rf_taxonomy_ids(keyword)
        if not any(f.values()):
            print(f"rf:sujet: no Radio France subject matches {keyword!r}")
            return []
        # Cache first: the warmup keeps these episodes fresh, and reading them
        # locally is what makes activation instant AND repeatable — querying live
        # meant losing a few subjects to timeouts on every cold fill.
        cached = self.dbHandler.get_episodes_by_taxonomy(
            [i for v in f.values() for i in v], limit=max(max_results * 3, 30))
        ready = self._unread_spoken_uris(cached)[:max_results]
        if ready or self._podcast_cache_fresh():
            return ready
        import concurrent.futures as _cf
        targets = list(stations or self.rf_stations())
        def _one(station):
            try:
                return rf.diffusions(self._rf_api_key, station,
                                     themes=f['themes'], tags=f['tags'],
                                     subthemes=f['subthemes'], subsubthemes=f['subsubthemes'],
                                     days=rf.MAX_WINDOW_DAYS, first=50)
            except Exception as e:
                print(f"rf:sujet {keyword!r} on {station}: {e}")
                return []
        # One request per station, run together: they are independent and IO-bound.
        if len(targets) > 1:
            with _cf.ThreadPoolExecutor(max_workers=len(targets)) as ex:
                results = list(ex.map(_one, targets))
        else:
            results = [_one(t) for t in targets]
        seen, uris = set(), []
        for batch in results:
            for ep in self._rf_convert(batch):
                if ep['uri'] not in seen:
                    seen.add(ep['uri'])
                    uris.append(ep['uri'])
                    self._remember_rf_published(ep)
        return self._unread_spoken_uris(uris)[:max_results]

    # ── Podcast catalogue warmup ──────────────────────────────────────────
    # Box activation used to query Radio France live, once per subject per
    # station. That made it slow AND unstable: on a cold cache a burst of ~28
    # requests routinely lost several to timeouts, so the same box yielded
    # anywhere from 7 to 30 episodes. The catalogue is refreshed in the
    # background instead, and filling reads the DB.

    def _boxes_podcast_sources(self):
        """What the boxes actually reference: RSS feeds, RF shows, RF subjects.
        Scoped to referenced sources on purpose — the point is to preload what
        this install listens to, not to mirror Radio France."""
        feeds, shows, subjects = set(), set(), set()
        for b in Box.select():
            for raw in (b.data or '').splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('podcast+'):
                    feeds.add(re.sub(r'[?&]max_results=\d+', '', line.split('+', 1)[1]).strip())
                elif line.startswith('rf:show:'):
                    shows.add(line[len('rf:show:'):].strip())
                elif line.startswith(('rf:sujet:', 'rf:subject:')):
                    subjects.add(line.split(':', 2)[2].partition('@')[0].strip())
        return feeds, shows, subjects

    def warmup_podcast_catalogue(self, purge_days=365):
        """Refresh the episodes of every referenced source. Never raises."""
        self._rf_feed_keys = {}   # re-read each feed once per run, not stale ones
        feeds, shows, subjects = self._boxes_podcast_sources()
        total = 0
        for feed in feeds:
            try:
                items = self.get_podcast_from_url(feed)
                self.dbHandler.upsert_podcast_channel(
                    feed, 'rss', title=self._feed_title(feed), url=feed)
                # mopidy's Refs give a uri and a title but no date, and the date is
                # both what the Details panel shows and what makes an episode
                # identifiable across sources — so read it from the feed itself.
                dates = self._feed_pubdates(feed)
                eps = []
                for it in items:
                    guid = (it.uri or '').split('#', 1)[-1]
                    day, ekey = dates.get(guid, ('', ''))
                    eps.append({'uri': it.uri, 'name': getattr(it, 'name', ''),
                                'day': day, 'key': ekey})
                total += self.dbHandler.upsert_episodes(eps, channel_id=feed,
                                                        option_type=self._spoken_type_for_uri(feed))
            except Exception as e:
                print(f"warmup_podcast_catalogue(feed {feed}): {e}")
        if self.rf_enabled():
            for url in shows:
                try:
                    eps = self._rf_convert(rf.episodes_of_show(self._rf_api_key, url, first=40))
                    if eps:
                        self.dbHandler.upsert_podcast_channel(
                            url, 'rf', title=eps[0].get('show_title', ''), url=url,
                            feed_url=self._rf_feed_for_show(url))
                        self.dbHandler.upsert_episodes(eps, channel_id=url, dedup=True)
                        total += len(eps)
                except Exception as e:
                    print(f"warmup_podcast_catalogue(show {url}): {e}")
            for subject in subjects:
                try:
                    total += self._warm_subject(subject)
                except Exception as e:
                    print(f"warmup_podcast_catalogue(subject {subject}): {e}")
        try:
            self.dbHandler.set_cache_meta('warmup_podcasts_at', 1)
        except Exception:
            pass
        try:
            self.dbHandler.purge_old_episodes(purge_days)
        except Exception as e:
            print(f"warmup_podcast_catalogue(purge): {e}")
        print(f"warmup_podcast_catalogue: {total} episodes refreshed "
              f"({len(feeds)} feeds, {len(shows)} shows, {len(subjects)} subjects)")
        return total

    def _podcast_cache_fresh(self, hours=6):
        """True while the catalogue warmup is recent enough to be believed —
        INCLUDING when it holds nothing for a subject. Without this the fill
        cannot tell 'not cached yet' from 'cached, and there is genuinely
        nothing this week', and re-queries the API for every empty subject —
        which is most of them, and exactly what made activation slow."""
        try:
            _v, at = self.dbHandler.get_cache_meta('warmup_podcasts_at')
            if not at:
                return False
            if isinstance(at, (int, float)):
                at = datetime.datetime.utcfromtimestamp(at)
            return (datetime.datetime.utcnow() - at).total_seconds() < hours * 3600
        except Exception:
            return False

    def _feed_title(self, feed_url):
        """The feed's own <title> — what the Details panel shows as the channel."""
        try:
            import urllib.request as _u
            raw = _u.urlopen(_u.Request(feed_url, headers={'User-Agent': 'o2m/1.0'}),
                             timeout=15).read(200000).decode('utf-8', 'ignore')
            m = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.S)
            return (m.group(1).strip() if m else '')[:255]
        except Exception:
            return ''

    def _feed_index(self, feed_url):
        """Parse a feed once into what the catalogue needs:
          guid -> (day, page_key)   and   page_key -> guid
        mopidy exposes neither the date nor the <link> from a browse Ref, and the
        <link> carries Radio France's episode id — the only exact join between a
        feed item and the same episode served by the API."""
        by_guid, by_key = {}, {}
        try:
            import email.utils, urllib.request as _u
            raw = _u.urlopen(_u.Request(feed_url, headers={'User-Agent': 'o2m/1.0'}),
                             timeout=15).read().decode('utf-8', 'ignore')
            for item in re.findall(r'<item>(.*?)</item>', raw, re.S):
                g = re.search(r'<guid[^>]*>([^<]+)</guid>', item)
                d = re.search(r'<pubDate>([^<]+)</pubDate>', item)
                lk = re.search(r'<link>([^<]+)</link>', item)
                if not g:
                    continue
                guid = g.group(1).strip()
                day = ''
                if d:
                    try:
                        day = email.utils.parsedate_to_datetime(
                            d.group(1).strip()).strftime('%Y-%m-%d')
                    except Exception:
                        day = ''
                pkey = rf.episode_key(lk.group(1) if lk else '')
                by_guid[guid] = (day, pkey)
                if pkey:
                    by_key[pkey] = guid
        except Exception as e:
            print(f"_feed_index({feed_url}): {e}")
        return by_guid, by_key

    def _feed_pubdates(self, feed_url):
        return self._feed_index(feed_url)[0]

    def _rf_feed_for_show(self, show_url):
        """Cached feed of a show; discovered from its page the first time."""
        if not show_url:
            return ''
        feed = self.dbHandler.get_channel_feed(show_url)
        if feed:
            return feed
        feed = rf.discover_feed(show_url)
        if feed:
            self.dbHandler.upsert_podcast_channel(show_url, 'rf', url=show_url, feed_url=feed)
        return feed

    def _rf_as_podcast_uri(self, ep):
        """A Radio France episode expressed the way every other podcast is:
        'podcast+<feed>#<guid>'.

        Both sources describe the same broadcast but ship different audio files
        (their ITEMA ids differ), so they used to produce two unrelated Track
        rows for one episode — split history, and a pile of special cases for the
        bare mp3 form. They do agree on the episode PAGE, whose id joins them
        exactly. Returns '' when the show has no discoverable feed or the episode
        is not in it yet (just published): the mp3 url is then kept as a fallback.
        """
        try:
            key = ep.get('key')
            show = ep.get('show_url')
            if not key or not show:
                return ''
            feed = self._rf_feed_for_show(show)
            if not feed:
                return ''
            cache = getattr(self, '_rf_feed_keys', None)
            if cache is None:
                cache = self._rf_feed_keys = {}
            if feed not in cache:
                cache[feed] = self._feed_index(feed)[1]
            guid = cache[feed].get(str(key))
            return f"podcast+{feed}#{guid}" if guid else ''
        except Exception as e:
            print(f"_rf_as_podcast_uri: {e}")
            return ''

    def _rf_convert(self, episodes):
        """Swap in the podcast+ form wherever it exists. Idempotent."""
        for ep in episodes or []:
            if not ep or not (ep.get('uri') or '').startswith('http'):
                continue
            alt = self._rf_as_podcast_uri(ep)
            if alt:
                ep['uri'] = alt
        return episodes

    def _warm_subject(self, subject):
        """Cache one subject's recent episodes, with their show and their subjects
        — the pivot is what lets the fill answer 'rf:sujet:' from the DB."""
        f = self.rf_taxonomy_ids(subject)
        if not any(f.values()):
            return 0
        n = 0
        for station in self.rf_stations():
            for ep in self._rf_convert(rf.diffusions(
                    self._rf_api_key, station,
                    themes=f['themes'], tags=f['tags'],
                    subthemes=f['subthemes'], subsubthemes=f['subsubthemes'],
                    days=rf.MAX_WINDOW_DAYS, first=50)):
                cid = ep.get('show_url') or ''
                if cid:
                    self.dbHandler.upsert_podcast_channel(
                        cid, 'rf', title=ep.get('show_title', ''), url=cid, station=station)
                self.dbHandler.upsert_episodes([ep], channel_id=cid or None, dedup=True)
                n += 1
        return n

    _RF_WARMUP_TTL = {'rf_shows': 7, 'rf_taxonomies': 30}   # days

    def _rf_should_warmup(self, entity_type):
        """TTL gate on CacheMeta. Deliberately simpler than
        SpotifyHandler.should_warmup: there is no reference total to compare a
        third-party catalogue against."""
        try:
            _v, updated_at = self.dbHandler.get_cache_meta(f'warmup_{entity_type}_at')
            if not updated_at:
                return True
            if isinstance(updated_at, (int, float)):
                updated_at = datetime.datetime.utcfromtimestamp(updated_at)
            return (datetime.datetime.utcnow() - updated_at).days >= self._RF_WARMUP_TTL.get(entity_type, 7)
        except Exception:
            return True

    def warmup_rf_shows(self, stations=None, max_pages=30):
        """Index the RF show catalogue station by station, 100/page (server cap),
        following the edge cursor — `shows` exposes no pageInfo, so a short page
        means the end."""
        total = 0
        for station in (stations or self.rf_stations()):
            after, pages = None, 0
            while pages < max_pages:
                rows, cursor = rf.list_shows(self._rf_api_key, station, first=rf.MAX_PAGE, after=after)
                if not rows:
                    break
                total += self.dbHandler.upsert_rf_shows(rows)
                pages += 1
                if not cursor:
                    break
                after = cursor
                time.sleep(0.25)
        print(f"warmup_rf_shows: {total} shows indexed")
        return total

    def warmup_rf_taxonomies(self, max_pages=12):
        """Index themes then tags — the vocabulary behind 'rf:sujet:'."""
        total = 0
        for kind in ('THEME', 'TAG'):
            after, pages = None, 0
            while pages < max_pages:
                rows, cursor = rf.list_taxonomies(self._rf_api_key, kinds=(kind,),
                                                  first=rf.MAX_PAGE, after=after)
                if not rows:
                    break
                total += self.dbHandler.upsert_rf_taxonomies(rows)
                pages += 1
                if not cursor:
                    break
                after = cursor
                time.sleep(0.25)
        print(f"warmup_rf_taxonomies: {total} subjects indexed")
        return total

    def warmup_radiofrance(self, force=False):
        """Refresh the RF catalogue caches. Never raises: Radio France being
        down must not take the rest of the warmup with it."""
        if not self.rf_enabled():
            print("warmup_radiofrance: no radiofrance_api_key, skipping")
            return
        for entity_type, method in (('rf_taxonomies', self.warmup_rf_taxonomies),
                                    ('rf_shows', self.warmup_rf_shows)):
            try:
                if force or self._rf_should_warmup(entity_type):
                    method()
                    self.dbHandler.set_cache_meta(f'warmup_{entity_type}_at', 1)
            except Exception as e:
                print(f"warmup_radiofrance({entity_type}) error: {e}")

    def get_unfinished_podcasts(self, max_results=15):
        uris = []
        self.dbHandler.get_unfinished_pattern("")
        #shows = self.get_podcast_from_url(self.uri)
        '''for item in shows:
            if self.dbHandler.get_end_stat(item.uri) == 0:
                uris.append(item.uri)'''
        return uris

#MOPIDY LIVE CONTROL
    def reload_active_boxes(self):
        """Rebuild the tracklist by re-running box_action on EVERY active box.
        In discover mode a single call rebuilds from all active boxes at once;
        otherwise each box is refilled in turn. Shared by starting_mode(start=True)
        and apply_mood_settings (live mood change).
        Locked (reentrant): `self._reload_seen` is shared instance state reset to
        None in a finally at the end of the method — two overlapping calls (e.g.
        two /api/mood POSTs firing close together, both reaching
        apply_mood_settings) raced on it: one call's finally could null it out
        while the other was still mid-loop, crashing with 'argument of type
        NoneType is not iterable'. The lock serializes the whole method, matching
        the pattern already used for box_action/meta_fill/meta_remove."""
        with self._box_ops_lock():
            if not self.activeboxs:
                return
            if ("discover" in self.configO2M and self.configO2M["discover"] == "true"):
                self.box_action(self.activeboxs[0])
            else:
                # Dedup active boxes by uid (cascade `box:` includes can append duplicates).
                seen_uids = set()
                unique = []
                for b in list(self.activeboxs):
                    if b.uid not in seen_uids:
                        seen_uids.add(b.uid)
                        unique.append(b)
                self.activeboxs = unique
                # Boxes included by a cascade (box:<uid>) are loaded by their parent — don't also
                # reload them directly (that double-loaded them → 120 instead of 60).
                included = set()
                for b in unique:
                    for line in (b.data or '').split('\n'):
                        line = line.strip()
                        if line.startswith('box:'):
                            included.add(line.split(':', 1)[1].strip())
                # Reset the NFC "same tag = next song" guard so every box actually reloads, and
                # track boxes loaded this cycle so a cascade child isn't loaded twice.
                self.last_box_uid = None
                self._reload_seen = set()
                try:
                    for b in unique:
                        if b.uid in included or b.uid in self._reload_seen:
                            continue  # loaded via its parent's cascade
                        self._reload_seen.add(b.uid)
                        try:
                            self.box_action(b)
                        except Exception as e:
                            print(f"reload_active_boxes error: {e}")
                finally:
                    self._reload_seen = None

    def check_active_boxes_health(self):
        """Transitional watchdog (2026-07-20 incident): o2m's `activeboxs` lives in
        process memory and survives a mopidy restart, but mopidy's tracklist does
        not (no persisted state) — so an independent mopidy restart leaves boxes
        marked active in the UI with an empty tracklist and no playback, looking
        stuck. If active boxes exist but the tracklist is empty, auto-refill by
        replaying reload_active_boxes(). The cooldown only gates the REFILL
        attempt (15s) — the cheap emptiness check itself always runs, so a
        healthy poll never suppresses the next, actually-empty one."""
        if not self.activeboxs:
            return
        try:
            length = self.mopidyHandler.tracklist.get_length()
        except Exception:
            return
        if length:
            return
        now = time.time()
        if now - self._health_check_last < 15:
            return   # a refill was already attempted recently; don't hammer mopidy
        self._health_check_last = now
        print(f"check_active_boxes_health: {len(self.activeboxs)} active box(es) but empty "
              f"tracklist (mopidy restarted independently?) — auto-refilling")
        try:
            self.reload_active_boxes()
        except Exception as e:
            print(f"check_active_boxes_health: reload error: {e}")

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
            self.reload_active_boxes()
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

    def smart_shuffle_tracklist(self, start_index, stop_index):
        """Default ordering: popularity-weighted reorder of the tracklist slice
        [start,stop). Temperature follows discover_level — low DL surfaces popular
        tracks first, DL=10 → uniform (identical to a plain random shuffle). Before
        the first popularity recompute (all scores NULL) weights are uniform, so
        behaviour matches the previous shuffle. Any failure falls back to it."""
        try:
            s = start_index if start_index is not None else 0
            tl = self.mopidyHandler.tracklist.get_tl_tracks()
            slice_tl = tl[s:stop_index]
            if len(slice_tl) <= 1:
                return
            uris = [t.track.uri for t in slice_tl]
            pop = {}
            try:
                for r in (Track.select(Track.uri, Track.popularity)
                              .where(Track.uri << uris).namedtuples()):
                    if r.popularity is not None:
                        pop[r.uri] = r.popularity
            except Exception as e:
                print(f"smart_shuffle lookup error: {e}")
            # Temperature: DL=0 → k=2 (favor popular), DL=5 → 1, DL=10 → 0 (uniform)
            k = max(0.0, (10 - self.discover_level) / 5.0)
            # Efraimidis-Spirakis weighted order over tl_tracks (NULL → neutral 0.5)
            keyed = []
            for t in slice_tl:
                w = pop.get(t.track.uri, 0.5) ** k
                if w <= 0:
                    w = 1e-9
                keyed.append((random.random() ** (1.0 / w), t.tlid))
            keyed.sort(reverse=True)
            ordered = [tlid for _, tlid in keyed]
            # Apply the permutation with selection-style moves, mirroring locally
            cur = [t.tlid for t in slice_tl]
            for p, desired in enumerate(ordered):
                c = cur.index(desired, p)
                if c != p:
                    self.mopidyHandler.tracklist.move(s + c, s + c + 1, s + p)
                    cur.insert(p, cur.pop(c))
        except Exception as e:
            print(f"smart_shuffle error: {e}; falling back to plain shuffle")
            self.shuffle_tracklist(start_index, stop_index)
 
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

    def apply_mood_settings(self):
        """Apply a mood change coming from the interface.

        Two cases:
        - Auto/mood mode (auto box active, or nothing active): full clean reload —
          clear the whole tracklist + per-track box state, then RELOAD EVERY active
          box with the new mood/discover_level (not just the auto box). If nothing is
          active, self-activate the auto box (DB 'auto:library' or a simulated fill).
        - A user box active WITHOUT the auto session (e.g. a single playlist): no
          rebuild (returns -1); the new mood biases its future live recommendations.

        Returns tracks added, or -1 when skipped (user box active, no auto).
        """
        auto_active = any('auto:library' in (getattr(b, 'data', '') or '') for b in self.activeboxs)
        user_boxes = [b for b in self.activeboxs
                      if 'auto:library' not in (getattr(b, 'data', '') or '')]

        # Case 2: user box(es) active without the auto/mood session → don't disrupt.
        if user_boxes and not auto_active:
            print("apply_mood_settings: user box(es) active (no auto) → no rebuild")
            return -1

        # Case 1: clean clear of the whole tracklist + per-track box state (no volume
        # reset), then rebuild from scratch with the new mood.
        try:
            self.mopidyHandler.playback.stop()
            self.mopidyHandler.tracklist.clear()
            self._track_info.clear()
        except Exception as e:
            print(f"apply_mood_settings: clear error: {e}")

        if self.activeboxs:
            # Reload EVERY active box (auto + any user boxes) with the new mood/DL.
            self.reload_active_boxes()
        else:
            # Nothing active → start the auto/mood mix.
            box = self.dbHandler.get_box_by_data_contains('auto:library')
            if box is not None:
                self.activeboxs.append(box)
                self.box_action(box)
            else:
                fallback = self.dbHandler.get_box_by_option_type('new_mopidy') or Box(
                    uid='auto_sim', option_type='new_mopidy', data='auto:library', option_sort=None)
                self.tracklistfill_auto(fallback, self.max_results, self.discover_level)

        added = self.mopidyHandler.tracklist.get_length()

        # Start playback from the top of the fresh mix.
        try:
            if self.mopidyHandler.playback.get_state() == "stopped":
                tl = self.mopidyHandler.tracklist.get_tl_tracks()
                if tl:
                    self.mopidyHandler.playback.play(tlid=tl[0].tlid)
        except Exception as e:
            print(f"apply_mood_settings: play error: {e}")

        print(f"apply_mood_settings: reloaded {len(self.activeboxs)} box(es), added {added} "
              f"(e={self.mood_energy} v={self.mood_valence} dl={self.discover_level})")
        return max(0, added)

    def initialize_playback(self, window=1, allow_box=True):
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

                # Two ways to skip the box auto-launch (unmute + resume-if-paused
                # still apply): the caller passes allow_box=False (e.g. the /basic
                # view), or default_box_uid is the sentinel 'none'. An EMPTY
                # default_box_uid falls back to the stats_raw history box instead.
                if not allow_box:
                    return False
                if self.default_box_uid and self.default_box_uid.lower() == 'none':
                    return False

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

        # Build a candidate pool (wider than `limit`) from same-album / same-artist /
        # Spotify reco, then mood+popularity-select it via _expand_pick so live recos
        # follow the current mood matrix + discover_level (and the cooldown avoids
        # re-recommending what was just played/served). Context: an album box leans on
        # the artist + reco rather than re-serving the same album.
        n_fetch = max(6, limit * 4)
        pool = []
        if 'album' in data:
            pool += self.get_same_artist_tracks(track_uri, n_fetch) or []
            pool += self.get_spotify_reco(track_seed, n_fetch) or []
        else:
            pool += self.get_same_album_tracks(track_uri, n_fetch) or []
            pool += self.get_same_artist_tracks(track_uri, n_fetch) or []
            pool += self.get_spotify_reco(track_seed, n_fetch) or []

        # Dedup (keep order), drop the seed.
        seen, candidates = {track_uri}, []
        for u in pool:
            if u and u not in seen:
                seen.add(u)
                candidates.append(u)
        if not candidates:
            return []

        uris = self._expand_pick(candidates, limit, self.mood_energy, self.mood_valence, discover_level)

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
                # strip() is essential: box data uses \r\n line endings and we split on
                # \n, so each line keeps a trailing \r. An unstripped 'spotify:playlist:ID\r'
                # is rejected by the Spotify API ("Unsupported URL / URI.", 400) — this
                # silently broke the radio auto-save add (the manual editor builds the URI
                # from a clean id, which is why only the auto path failed).
                library_link = content.strip()
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

    def _mood_pick(self, uris, n, energy, valence, radius, discover_level=5):
        """Bias a candidate list towards (energy, valence) AND track popularity.

        Two orthogonal axes, both modulated by discover_level, without ever
        dropping tracks:
          - mood: tracks whose energy/valence are known AND within `radius` of the
            target come first; the rest (NULL or out-of-radius) are fallback.
          - popularity: within each group, tracks are drawn weighted by their
            popularity score raised to a temperature k(DL). Low DL sharpens toward
            popular/comfort tracks; high DL flattens toward uniform discovery.

        Before the first popularity recompute (all scores NULL) the weights are
        uniform, so behaviour is identical to the previous random shuffle.
        """
        if not uris:
            return []
        # Some auto-fill sources hand in nested lists (e.g. News) — flatten to flat
        # scalar URIs, else the `uri IN (...)` lookup raises "Operand should contain
        # 1 column(s)" and the whole mood/popularity selection silently falls back.
        uris = [u for u in util.flatten_list(list(uris)) if isinstance(u, str) and u]
        if not uris:
            return []
        # Temperature: DL=0 → k=2 (favor popular), DL=5 → 1 (proportional), DL=10 → 0 (uniform)
        k = max(0.0, (10 - discover_level) / 5.0)

        # Single query for energy/valence + popularity; drop hidden/trash from the pool
        # so explicitly rejected tracks never resurface.
        feat, pop, last_read, rc, excluded = {}, {}, {}, {}, set()
        try:
            for t in (Track.select(Track.uri, Track.energy, Track.valence, Track.popularity,
                                   Track.option_type, Track.last_read_date, Track.read_count)
                          .where(Track.uri << list(uris)).namedtuples()):
                if t.option_type in ('hidden', 'trash'):
                    excluded.add(t.uri)
                    continue
                if t.energy is not None and t.valence is not None:
                    feat[t.uri] = (t.energy, t.valence)
                if t.popularity is not None:
                    pop[t.uri] = t.popularity
                if t.last_read_date is not None:
                    last_read[t.uri] = t.last_read_date
                if t.read_count is not None:
                    rc[t.uri] = t.read_count
        except Exception as e:
            print(f"_mood_pick lookup error: {e}")
            return uris[:min(n, len(uris))]

        if excluded:
            uris = [u for u in uris if u not in excluded]
        if not uris:
            return []
        n = min(n, len(uris))

        now = datetime.datetime.utcnow()
        now_ts = time.time()
        served = getattr(self, '_served_at', None)
        if served is None:
            self._served_at = served = {}

        # Concentric mood weighting (replaces the old hard ±radius band): a DL-scaled
        # Gaussian around the (energy, valence) target. σ = radius (tight at DL0 →
        # broad at DL10), so the closest tracks are favoured and farther ones fade
        # smoothly instead of being cut off. `floor` rises with DL so mood stops
        # mattering at DL10 (discovery); unknown-mood (NULL) tracks sit at the floor
        # as low-weight fillers, so the pool is never empty even when few tracks carry
        # energy/valence (the sparse-coverage case). Single weighted draw — no split.
        mood_on = (energy is not None and valence is not None)
        sigma = max(radius, 1e-3)
        floor = 0.05 + 0.95 * (min(max(discover_level, 0), 10) / 10.0)

        def _mood_w(u):
            if not mood_on:
                return 1.0
            f = feat.get(u)
            if f is None:
                return floor
            d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
            return max(math.exp(-d2 / (2.0 * sigma * sigma)), floor)

        # Weight = popularity**k × concentric-mood × anti-repeat cooldown (played + served).
        def _w(u):
            return (max(pop.get(u, 0.5), 1e-6) ** k) * _mood_w(u) \
                   * self._cooldown_factor(u, last_read.get(u), now, now_ts, served, rc.get(u, 0))
        weights = {u: _w(u) for u in uris}
        result = self._sample_by_weight(uris, weights, n)
        for u in result:
            served[u] = now_ts  # served-cooldown for subsequent selections
        return result

    def _expand_pick(self, uris, n, energy, valence, discover_level, exclude_hidden=True):
        """STOCHASTIC filter of a tapped object's cached tracks, weighted toward a
        DL-controlled popularity target. Always SAMPLES max_results at random from
        the pool (no deterministic block) so a large playlist ROTATES around the
        target each tap instead of replaying the same top tracks. Returns a
        source-ordered subset (sequencing stays option_sort's job); count drops
        below n only when the source has fewer tracks. Only invoked when the box's
        option_sort is 'smart' (shuffle/asc/desc keep the basic legacy path).

        Variant = self.expand_pick_mode:
          - 'hybrid' (P0): n*(1-DL/10) exploit (sampled ∝ affinity²) + n*DL/10
                       explore (uniform from the rest) — both stochastic.
          - 'temp'   (P1): one sample weighted by affinity^k, k=(5-DL)/2.5
                       (+2 favours the top → 0 uniform → -2 favours the obscure).
          - 'band'   (P2): one sample weighted by a Gaussian around a target
                       popularity P*(DL) (≈p90 at DL0 → ≈p10 at DL10).
        Mood adds a small bonus only when features exist (unknown = neutral).
        recently-played tracks are down-weighted (cooldown). hidden/trash are
        excluded ONLY when exclude_hidden=True (recos/discovery): a directly-tapped
        box whose OWN tracks are hidden/trash (e.g. a box with option_type='hidden')
        passes exclude_hidden=False so it can still play its own content — otherwise
        the exclusion would gut it (bug: 60/66 hidden → only 6 playable).
        """
        if not uris:
            return []
        feat, pop, last_read, rc, excluded = {}, {}, {}, {}, set()
        try:
            for t in (Track.select(Track.uri, Track.energy, Track.valence, Track.popularity,
                                   Track.option_type, Track.last_read_date, Track.read_count)
                          .where(Track.uri << list(uris)).namedtuples()):
                if exclude_hidden and t.option_type in ('hidden', 'trash'):
                    excluded.add(t.uri)
                    continue
                if t.energy is not None and t.valence is not None:
                    feat[t.uri] = (t.energy, t.valence)
                if t.popularity is not None:
                    pop[t.uri] = t.popularity
                if t.last_read_date is not None:
                    last_read[t.uri] = t.last_read_date
                if t.read_count is not None:
                    rc[t.uri] = t.read_count
        except Exception as e:
            print(f"_expand_pick lookup error: {e}")
            return list(uris[:min(n, len(uris))])

        if excluded:
            uris = [u for u in uris if u not in excluded]
        if not uris:
            return []
        m = min(n, len(uris))
        mode = getattr(self, 'expand_pick_mode', 'hybrid')
        now = datetime.datetime.utcnow()
        now_ts = time.time()
        served = getattr(self, '_served_at', None)
        if served is None:
            self._served_at = served = {}
        sigma = max(discover_level / 20.0 + 0.05, 1e-3)
        MOOD_BONUS = 0.15  # soft, features-only; unknown mood = neutral

        def mood_g(u):  # concentric Gaussian proximity to the target in (0,1]; 0 if unknown
            if energy is None or valence is None:
                return 0.0
            f = feat.get(u)
            if f is None:
                return 0.0
            d2 = (f[0] - energy) ** 2 + (f[1] - valence) ** 2
            return math.exp(-d2 / (2.0 * sigma * sigma))

        def cd(u):
            return self._cooldown_factor(u, last_read.get(u), now, now_ts, served, rc.get(u, 0))

        def aff(u):  # affinity = popularity + soft, distance-graded mood bonus
            return pop.get(u, 0.5) + MOOD_BONUS * mood_g(u)

        if mode == 'temp':
            k = (5 - discover_level) / 2.5  # +2 (favour top) .. 0 (uniform) .. -2 (favour obscure)
            weights = {u: (max(aff(u), 1e-6) ** k) * cd(u) for u in uris}
            sel = self._sample_by_weight(uris, weights, m)
        elif mode == 'band':
            vals = sorted(pop.get(u, 0.5) for u in uris)
            p10 = vals[int(0.10 * (len(vals) - 1))]
            p90 = vals[int(0.90 * (len(vals) - 1))]
            target = p90 - (p90 - p10) * (discover_level / 10.0)  # DL0→top, DL10→bottom
            sigma_pop = 0.15  # popularity-band spread (distinct from the mood sigma above)
            weights = {u: math.exp(-((pop.get(u, 0.5) - target) ** 2) / (2 * sigma_pop * sigma_pop))
                          * (1.0 + MOOD_BONUS * mood_g(u)) * cd(u) for u in uris}
            sel = self._sample_by_weight(uris, weights, m)
        else:  # 'hybrid' (P0): stochastic exploit + uniform explore
            n_explore = int(round(m * discover_level / 10.0))
            ew = {u: (max(aff(u), 1e-6) ** self.exploit_sharpness) * cd(u) for u in uris}
            exploit = self._sample_by_weight(uris, ew, m - n_explore)
            ex_set = set(exploit)
            rest = [u for u in uris if u not in ex_set]
            xw = {u: cd(u) for u in rest}
            sel = exploit + self._sample_by_weight(rest, xw, n_explore)

        sel_set = set(sel)
        for u in sel_set:
            served[u] = now_ts  # remember what we just served (served-cooldown)
        try:
            ps = [pop.get(u, 0.5) for u in sel_set]
            print(f"_expand_pick[{mode}] DL={discover_level} pool={len(uris)} "
                  f"-> {len(sel_set)} tracks, avg_pop={round(sum(ps)/len(ps), 3) if ps else 0}")
        except Exception:
            pass
        return [u for u in uris if u in sel_set]  # source order preserved

    def _sample_by_weight(self, uris, weights, n):
        """Efraimidis-Spirakis weighted sampling without replacement from a
        precomputed {uri: weight} map (key = rand**(1/w), keep the largest).
        Returns up to n uris. Missing/≤0 weights fall back to a tiny epsilon."""
        n = min(n, len(uris))
        if n <= 0:
            return []
        keyed = []
        for u in uris:
            w = weights.get(u, 1e-9)
            if w <= 0:
                w = 1e-9
            keyed.append((random.random() ** (1.0 / w), u))
        keyed.sort(reverse=True)
        return [u for _, u in keyed[:n]]

    def _cooldown_factor(self, uri, last_read_at, now, now_ts, served, read_count=0):
        """Combined anti-repeat down-weight in (0,1]: a track recently PLAYED and/or
        recently SERVED is demoted, so successive selections rotate. Shared by
        _expand_pick and _mood_pick.

        Played cooldown is MULTI-DAY and graduated (not a hard step): a track played
        just now sits at cooldown_mult and eases linearly back to 1.0 over the window.
        The window is cooldown_days, stretched up to ~2× for heavy-rotation tracks
        (read_count → cooldown_rc_ref) so comfort favourites don't recur every session.
        Served cooldown (intra-session, minutes) is unchanged."""
        f = 1.0
        if last_read_at is not None:
            try:
                lr = last_read_at
                if isinstance(lr, (int, float)):
                    lr = datetime.datetime.utcfromtimestamp(lr)
                if getattr(lr, 'tzinfo', None) is not None:
                    lr = lr.replace(tzinfo=None)
                age_days = (now - lr).total_seconds() / 86400.0
                cd_days = self.cooldown_days * (1.0 + min(read_count or 0, self.cooldown_rc_ref) / float(self.cooldown_rc_ref))
                if 0.0 <= age_days < cd_days:
                    f *= self.cooldown_mult + (1.0 - self.cooldown_mult) * (age_days / cd_days)
            except Exception:
                pass
        sa = served.get(uri)
        if sa is not None and (now_ts - sa) < self.served_cooldown_min * 60.0:
            f *= self.served_mult
        return f


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
        if box.option_type == '': box.option_type='library'
        box.update()
        box.save()

    # Update raw stat when finished, skipped or system stopped (if possible)
    def update_stat_raw(self, uri):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        self.dbHandler.create_stat_raw(
            uri,
            now_utc,
            now_utc.hour,   # UTC hour, consistent with the UTC read_date (was local .now().hour)
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
        # Spoken content (podcast/video URI) must NEVER carry a music tag, whatever box
        # or bucket it was drawn from (auto→'library', news→'new', Iris search→'new'…):
        # force it to a non-music type so it stays resumable and out of the music
        # removal/reco/promotion flow. The sticky rule below keeps an existing 'info'
        # classification (info-box episodes) when we pass the generic 'podcast'.
        if self._is_spoken_uri(uri) \
                and option_type in ('new', 'new_mopidy', 'library', 'favorites', 'incoming', 'normal', ''):
            option_type = self._spoken_type_for_uri(uri, getattr(track, 'length', None))
        new_stat = False

        #Get stats
        if self.dbHandler.stat_exists(uri):
            stat = self.dbHandler.get_stat_by_uri(uri)
        else:
            new_stat = True
            stat = self.dbHandler.create_stat(uri)

        # Garde-fou : si la stat n'a pu être ni récupérée ni créée, on sort
        # proprement plutôt que de crasher le thread d'événements Mopidy
        if stat is None:
            print(f"update_stat_track: no stat for {uri}, skipping")
            return None

        #Using rate reading average instead of bool
        track_finished = False
        rate = 0.5
        stat.username = self.username

        if hasattr(track, "length") and track.length:
            rate = pos / track.length
            if rate > 0.9: track_finished = True
            # Persist duration from the Mopidy track (podcasts carry .length here even
            # though the metadata cache skips non-spotify URIs) → fills duration_ms
            # incrementally on each playback, enabling proportion-based logic later.
            try:
                if not stat.duration_ms:
                    stat.duration_ms = int(track.length)
            except Exception:
                pass
            # Same reason for the title: cache_track_from_mopidy is spotify-only, so
            # Track.name stayed NULL for every episode and search_local's
            # 'podcasts'/'info' buckets (which match on name) could never return
            # anything. Set it once, never overwrite, and only for spoken content so
            # the richer Spotify path stays the source of truth for music.
            try:
                if not stat.name and self._is_spoken_uri(uri):
                    _nm = (getattr(track, 'name', '') or '').strip()
                    if _nm and not _nm.startswith(('http://', 'https://')):
                        stat.name = _nm[:512]
            except Exception:
                pass
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
        # Keep an 'info' classification sticky: an info-box item (handled by the news/actuality
        # window) must not be silently downgraded to 'podcast'/'new' by a later casual replay.
        if not(stat.option_type == 'info' and option_type in ('new', 'podcast')):
            if not(option_type == 'new' and (stat.option_type == 'library' or stat.option_type == 'favorites' or stat.option_type == 'incoming' or stat.option_type == 'hidden' or stat.option_type == 'trash')):
                #if not(option_type == 'library' and (stat.option_type == 'favorites' or stat.option_type == 'incoming')):
                if not(option_type == 'incoming' and (stat.option_type == 'library' or stat.option_type == 'favorites')):
                    _was_option_type = stat.option_type
                    stat.option_type = option_type
                    # A track can also reach 'favorites' through the BOX context (a box
                    # tagged favorites stamps its type on what it serves), not only
                    # through threshold_adding_favorites — and that path never touched
                    # Spotify, which is why statuses and the ♥ could disagree. Mirror
                    # the like so the two stay in sync, exactly like the threshold path.
                    if (option_type == 'favorites' and _was_option_type != 'favorites'
                            and str(uri).startswith('spotify:track:') and not stat.liked):
                        try:
                            self.spotifyHandler.set_track_saved(uri, True)
                            stat.liked = 1
                            stat.liked_at = datetime.datetime.now(datetime.timezone.utc)
                            print(f"favorites sync: liked {uri} on Spotify")
                        except Exception as e:
                            # Never let a refused Spotify write break stat recording;
                            # the status still stands, the ♥ simply stays off.
                            print(f"favorites sync: Spotify like failed for {uri}: {e}")
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
                        if result: stat.option_type = 'library'
                        if result and result != 'already in': self._log_playlist_change(uri[0], library_link, 'add', _from_option_type, 'library', _track_name)

                    if stat.option_type != 'library' :
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
                            if box.option_type == 'library' and self.threshold_playing_count_new(stat.read_count_end,discover_level_box)==True :
                                if 'spotify:playlist' in box.data :
                                    result = self.autofill_spotify_playlist(box.data,uri)
                                    if result: stat.option_type = 'library'
                                if 'm3u' in box.data :
                                    playlist = self.mopidyHandler.playlists.lookup(box.data)
                                    #for track in playlist.tracks:
                                    #    if 'spotify:playlist' in track.uri :
                                    #        result = self.autofill_spotify_playlist(track.uri,uri)
                                    #        if result: stat.option_type = 'library'
                                    if 'spotify:playlist' in playlist.tracks[0].uri :
                                        result = self.autofill_spotify_playlist(playlist.tracks[0].uri,uri)
                                        if result: stat.option_type = 'library'
                        '''

                    # Transfer, not duplicate: a track promoted out of 'new' →
                    # incoming/library is removed from the 'new' box's editable
                    # playlist(s) (skip the one just added to in the library case;
                    # non-editable/Spotify-owned playlists fail silently and are ignored).
                    if _from_option_type == 'new' and stat.option_type in ('incoming', 'library'):
                        self._remove_from_new_playlists(uri, library_link if stat.option_type == 'library' else None, _from_option_type, _track_name)

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
                        if result3: stat.option_type = 'library'
                        if result3: self._log_playlist_change(uri[0], 'spotify:saved', 'remove', _from_option_type, 'library', _track_name)
                    else:
                        box_favorites = self.dbHandler.get_box_by_option_type('favorites')
                        if box_favorites:
                            if 'spotify:playlist' in box_favorites.data:
                                result4 = self.remove_spotify_playlist(box_favorites.data,uri)
                                if result4: stat.option_type = 'library'
                                if result4: self._log_playlist_change(uri[0], box_favorites.data, 'remove', _from_option_type, 'library', _track_name)
                            if 'm3u' in box_favorites.data :
                                playlist = self.mopidyHandler.playlists.lookup(box_favorites.data)
                                #for track in playlist.tracks:
                                #    if 'spotify:playlist' in track.uri :
                                #        result = self.autofill_spotify_playlist(track.uri,uri)
                                #        if result: stat.option_type = 'favorites'
                                if 'spotify:playlist' in playlist.tracks[0].uri :
                                    result5 = self.remove_spotify_playlist(playlist.tracks[0].uri,uri)
                                    if result5: stat.option_type = 'library'
                                    if result5: self._log_playlist_change(uri[0], playlist.tracks[0].uri, 'remove', _from_option_type, 'library', _track_name)

        # Deferred mood enrichment on playback end (mood=NULL / '_' / energy=NULL).
        self._enrich_track_features_async(track, uri, stat)

        print(f"\n\nUpdate and Fix {fix} stat track {stat}\n\n")
        stat.update()
        stat.save()

    # Any non-music spoken item: RSS podcast, YouTube, or a Radio France OpenAPI
    # episode. RF episodes are plain https mp3 URLs with no 'podcast+' marker to
    # key on, so every spoken-content test has to know these hosts too.
    _SPOKEN_URI_RE = re.compile(
        r'podcast\+|youtube:video|(?:^|:)yt:'
        r'|proxycast\.radiofrance\.fr|radiofrance-podcast\.net', re.I)

    def _fill_spoken_meta(self, stat, mopidy_track, uri):
        """Title, date and channel for a spoken item, written once.

        The channel needs no lookup: a podcast uri already carries its feed
        ('podcast+<feed>#<guid>'). Registering it here means every episode gets a
        Channel row in the panel, not only those the catalogue warmup happened to
        index."""
        if not stat:
            return
        if not getattr(stat, 'name', None):
            nm = (getattr(mopidy_track, 'name', '') or '').strip()
            if nm and not nm.startswith(('http://', 'https://')):
                stat.name = nm[:512]
        if not getattr(stat, 'published_at', None):
            day = getattr(mopidy_track, 'date', None) or self._rf_published.get(uri)
            if day:
                stat.published_at = str(day)[:32]
        if not getattr(stat, 'channel_id', None) and uri.startswith('podcast+'):
            feed = re.sub(r'[?&]max_results=\d+', '', uri.split('+', 1)[1].split('#')[0]).strip()
            if feed:
                stat.channel_id = feed
                # Register the channel so the panel can name it rather than show a url.
                try:
                    if not self.dbHandler.get_channel_feed(feed):
                        self.dbHandler.upsert_podcast_channel(
                            feed, 'rss', title=self._feed_title(feed), url=feed, feed_url=feed)
                except Exception:
                    pass

    def _is_spoken_uri(self, uri):
        return bool(uri and self._SPOKEN_URI_RE.search(str(uri)))

    def _spoken_type_for_uri(self, uri, length_ms=None):
        """Classify spoken content (podcast+/youtube URI) as 'info' or 'podcast' when
        the box context is lost. Resolution order:
          1. HERITAGE — the type of the box whose data references this feed ('info'
             wins over 'podcast': actuality is the stronger claim).
          2. DURATION — short (< 20 min) → 'info', long → 'podcast' (live only; old
             stats have no duration).
          3. Fallback → 'podcast' (generic spoken; at least out of the music flow)."""
        try:
            if 'podcast+' in uri:
                feed = re.sub(r'[?&]max_results=\d+', '', uri.split('podcast+', 1)[1].split('#')[0]).strip().rstrip('/')
                if feed:
                    found = None
                    for b in Box.select().where(Box.data.contains(feed)):
                        if b.option_type == 'info':
                            return 'info'
                        if b.option_type == 'podcast':
                            found = 'podcast'
                    if found:
                        return found
        except Exception:
            pass
        try:
            if length_ms and int(length_ms) < 20 * 60 * 1000:
                return 'info'
        except Exception:
            pass
        return 'podcast'

    # Auto Filling playlist
    def _new_discovery_boxes(self):
        """The DISCOVERY 'new' boxes — those carrying the newrecent/newnotcompleted
        directives (e.g. 'Nouveautés'), i.e. the real "new inbox". Excludes ad-hoc
        'new'-tagged mood boxes ('0 Party'/'0 Chill') whose Spotify playlists must
        never be edited. get_box_by_option_type('new') can't be used — it returns a
        RANDOM 'new' box."""
        out = []
        for b in (self.dbHandler.get_boxes_by_option_type('new') or []):
            d = getattr(b, 'data', '') or ''
            if 'newrecent' in d or 'newnotcompleted' in d:
                out.append(b)
        return out

    def _new_discovery_playlists(self):
        """All spotify:playlist uris across the discovery 'new' boxes (ToListen,
        Shazam, …) — the editable inboxes a 'new' track can come from."""
        seen, out = set(), []
        for b in self._new_discovery_boxes():
            for line in (getattr(b, 'data', '') or '').split('\n'):
                line = line.strip()
                if line.startswith('spotify:playlist:') and line not in seen:
                    seen.add(line)
                    out.append(line)
        return out

    def _new_target_box(self):
        """Canonical discovery box (first), or any 'new' box as a fallback."""
        boxes = self._new_discovery_boxes()
        if boxes:
            return boxes[0]
        allnew = self.dbHandler.get_boxes_by_option_type('new') or []
        return allnew[0] if allnew else None

    def _new_target_playlist(self):
        """The canonical 'new' editable playlist uri for the ADD (ToListen perso)."""
        box = self._new_target_box()
        return self.get_spotify_playlist_from_box(box) if box else ''

    def _remove_from_new_playlists(self, uri, exclude_uri, from_type, track_name):
        """Transfer, not duplicate: remove a promoted track from EVERY discovery-'new'
        playlist that actually CONTAINS it (ToListen, Shazam, …) — tied to where the
        'new' track really lives, robust to several editable inboxes. Only removes
        where present (is_track_in_playlist), skips the playlist just added to
        (exclude_uri, library case); non-editable playlists fail silently."""
        try:
            if not uri or 'spotify:track' not in uri[0]:
                return
            track_id = uri[0].split(':')[2]
            for pl in self._new_discovery_playlists():
                if exclude_uri and pl == exclude_uri:
                    continue
                pid = pl.split(':')[2]
                try:
                    inside = self.spotifyHandler.is_track_in_playlist(self.username, track_id, pid)
                except Exception:
                    inside = False
                if not inside:
                    continue
                res = self.remove_spotify_playlist(pl, uri)
                if res:
                    self._log_playlist_change(uri[0], pl, 'remove', from_type, 'new', track_name)
        except Exception as e:
            print(f"_remove_from_new_playlists error: {e}")

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
    # ── Radio now-playing + auto-save ────────────────────────────────────────
    def start_radio_watcher(self):
        """Spawn the background radio watcher (once)."""
        if getattr(self, '_radio_watcher_started', False):
            return
        self._radio_watcher_started = True
        import threading
        threading.Thread(target=self._radio_watch_loop, daemon=True).start()

    def _radio_watch_loop(self):
        """While a radio stream is playing, poll its now-playing metadata. When the
        current track changes, the PREVIOUS one just finished on air ("terminé en
        lecture") → if it's a music radio and discover_level ≥ radio_save_min_dl,
        auto-save it to the library."""
        import time as _t
        _t.sleep(20)  # let startup settle
        while True:
            try:
                playing = False
                try:
                    playing = (self.mopidyHandler.playback.get_state() == 'playing')
                except Exception:
                    playing = False
                if not playing:
                    # Genuinely stopped → clear pending state (no finish to save).
                    self._radio_np = None
                    self._radio_last_key = None
                    self._radio_last_meta = None
                else:
                    np = self.radio_now_playing()
                    if np and np.get('key'):
                        self._radio_np = np
                        if np['key'] != self._radio_last_key:
                            # Track changed → the previous track played through to its end.
                            prev = self._radio_last_meta
                            if prev and prev.get('is_music'):
                                try:
                                    self._on_radio_track_finished(prev)
                                except Exception as e:
                                    print(f"radio auto-save error: {e}", flush=True)
                            self._radio_last_key = np['key']
                            self._radio_last_meta = np
                    # else: still playing but a transient metadata fetch failed
                    # (network blip / rate limit) → KEEP the pending key/meta so the
                    # in-progress track's finish isn't lost on the next real change.
            except Exception as e:
                print(f"_radio_watch_loop error: {e}")
            _t.sleep(self.radio_poll_sec)

    def _rf_station_for_uri(self, uri):
        """(station_id|None, is_music, full_name, logo_url) for a Radio France stream
        URI, else None. Matches the EXACT stream slug (…/<slug>-hifi.aac) — not a
        substring — so 'monpetitfranceinter' ≠ 'franceinter'."""
        if not uri or 'radiofrance' not in uri.lower():
            return None
        tail = uri.lower().split('?')[0].rsplit('/', 1)[-1]
        for suf in ('.aac', '.mp3', '.ogg'):
            if tail.endswith(suf):
                tail = tail[:-len(suf)]
        for suf in ('-hifi', '-midfi', '-lofi', '-hbr', '-lbr'):
            if tail.endswith(suf):
                tail = tail[:-len(suf)]
        st = self._RF_STATIONS.get(tail)
        if not st:
            return None
        return (st[0], st[1], st[2], self._RF_LOGOS.get(tail, ''))

    def _rf_livemeta(self, sid):
        """Current on-air track for a Radio France station via the livemeta API."""
        import urllib.request, json, time
        try:
            req = urllib.request.Request(f'https://api.radiofrance.fr/livemeta/pull/{sid}',
                                         headers={'User-Agent': 'Mozilla/5.0'})
            d = json.load(urllib.request.urlopen(req, timeout=6))
        except Exception as e:
            print(f"_rf_livemeta({sid}) error: {e}")
            return None
        steps = d.get('steps') or {}
        now = int(time.time())
        cur = None
        for s in steps.values():
            if s.get('title') and s.get('start', 0) <= now <= s.get('end', 10 ** 12):
                cur = s
                break
        if not cur:  # no exact window match → most recent titled step
            titled = [s for s in steps.values() if s.get('title')]
            cur = max(titled, key=lambda s: s.get('start', 0)) if titled else None
        if not cur:
            return None
        # embedType 'song' = a real music track; anything else (expression, …) is a
        # show/segment. Artist/album only make sense for songs.
        kind = 'song' if (cur.get('embedType') or '').lower() == 'song' else 'show'
        if kind == 'song':
            artist = (cur.get('authors') or (cur.get('highlightedArtists') or [''])[0]
                      or cur.get('performers') or '').strip()
            album = (cur.get('titreAlbum') or '').strip()
        else:
            artist, album = '', ''
        # Radio France 'visual' is sometimes a full URL (songs) and sometimes a bare
        # UUID (shows) that we can't turn into an image URL — keep only usable URLs.
        vis = str(cur.get('visual') or '')
        if not vis.startswith('http'):
            vis = ''
        return {'title': (cur.get('title') or '').strip(), 'artist': artist, 'album': album,
                'kind': kind,
                'key': cur.get('stepId') or cur.get('uuid') or f"{artist}-{cur.get('title')}",
                'visual': vis, 'source': 'radiofrance'}

    def radio_now_playing(self):
        """Current track on the active radio. Radio France stations → livemeta API;
        any other radio → ICY stream title (get_stream_title, 'Artist - Title')."""
        try:
            cur = self.mopidyHandler.playback.get_current_track()
        except Exception:
            cur = None
        uri = getattr(cur, 'uri', '') if cur else ''
        if not uri or not (uri.startswith('http') or uri.startswith('tunein:')):
            return None
        # Friendly station name (kept visible in the UI even when a song plays).
        station = (getattr(cur, 'name', '') or '')
        if station.startswith('http') or station.startswith('tunein:'):
            station = ''
        st = self._rf_station_for_uri(uri)
        if st:
            sid, is_music, name, logo = st
            meta = self._rf_livemeta(sid) if sid else None
            if not (meta and meta.get('title')):
                # Known station but no usable live item → still surface the station name.
                meta = {'title': '', 'artist': '', 'album': '', 'kind': 'radio', 'visual': '',
                        'key': 'station:' + name, 'source': 'radiofrance'}
            meta['is_music'] = is_music
            meta['station'] = name   # full sub-station name (e.g. 'FIP Groove')
            meta['station_logo'] = logo   # brand-logo fallback cover (repli 1)
            return meta
        # Fallback: ICY stream title (other Icecast/Shoutcast radios).
        try:
            title = self.mopidyHandler.playback.get_stream_title()
        except Exception:
            title = None
        if title:
            artist, sep, track = title.partition(' - ')
            if sep:
                return {'title': track.strip(), 'artist': artist.strip(), 'album': '', 'kind': 'song',
                        'key': title, 'is_music': True, 'source': 'icy', 'station': station,
                        'station_logo': ''}
            return {'title': title.strip(), 'artist': '', 'album': '', 'kind': 'song',
                    'key': title, 'is_music': True, 'source': 'icy', 'station': station,
                    'station_logo': ''}
        # Non-RF stream with no ICY → at least show the stream/station name.
        if station:
            return {'title': '', 'artist': '', 'album': '', 'kind': 'radio', 'visual': '',
                    'key': 'station:' + station, 'source': 'stream', 'station': station,
                    'station_logo': ''}
        return None

    def _on_radio_track_finished(self, meta):
        """A music-radio track just played through. Three discover_level tiers:
          - lower third (DL < 10/3 ≈ 3.3): no tracking at all;
          - middle third (10/3 ≤ DL < 20/3 ≈ 6.7): DB only (record the stat);
          - upper third (DL ≥ 20/3): DB + add to the 'new' playlist."""
        frac = (self.discover_level or 0) / 10.0
        if frac < 1.0 / 3.0:
            return  # tier 1 — no tracking
        title = (meta.get('title') or '').strip()
        if not title:
            return
        to_playlist = frac >= 2.0 / 3.0  # tier 3 → playlist too; tier 2 → DB only
        self._save_radio_track((meta.get('artist') or '').strip(), title, to_playlist=to_playlist)

    def _save_radio_track(self, artist, title, to_playlist=True):
        """Resolve a radio track to Spotify and record it in the DB as a 'new' track
        played once through (always). When `to_playlist` (upper DL tier), also add it
        to the canonical 'new' playlist (ToListen). Returns the resolved uri or None."""
        query = (artist + ' ' + title).strip()
        try:
            res = self.spotifyHandler.search_music(query, limit=5)
        except Exception as e:
            print(f"radio save: search error for {query!r}: {e}")
            return None
        tracks = (res or {}).get('tracks') or []
        if not tracks:
            print(f"radio save: no Spotify match for {query!r}")
            return None
        top = tracks[0]
        uri = top['uri']
        # DB tracking (tiers 2 & 3): record as a 'new' track completed once.
        self._record_new_once(uri, top)
        if not to_playlist:
            print(f"radio save: {query!r} → {uri} recorded in DB (tier 2, no playlist)", flush=True)
            return uri
        # Upper tier (DL ≥ 2/3, to_playlist=True): also log the listen in stats_raw as a
        # track play, so radio plays feed the raw stats like a normal completed track
        # (Radio France HTTP streams never reach the track_playback_ended stats path).
        # Restricted to this tier per the 3-tier design (lower/middle tiers don't log raw).
        try:
            self.update_stat_raw(uri)
        except Exception as e:
            print(f"radio save: stats_raw log error: {e!r}", flush=True)
        # Playlist (tier 3): add to the canonical 'new' playlist (ToListen) via the
        # EXACT same path as the manual editor (POST /api/track_playlist) —
        # add_tracks_playlist → sp.playlist_add_items — which is proven to work, plus
        # the local DB mirror (save_playlist_track) so the track shows as in-playlist
        # immediately. The old autofill_spotify_playlist used sp.user_playlist_add_tracks
        # with self.username (the streaming account, not the playlist owner) → 403/refused.
        playlist, added = '', None
        try:
            playlist = (self._new_target_playlist() or '').strip()  # defensive: never a trailing \r
            print(f"radio save: target 'new' playlist = {playlist!r}", flush=True)
            if playlist:
                pid = playlist.split(':')[-1]
                # Dedup against the LOCAL mirror (reliable) rather than a Spotify
                # is_track_in_playlist READ, which 403s/429s under the shared-token
                # rate limits and — in the old autofill path — raised and aborted the
                # whole add. The mirror is populated by save_playlist_track below and
                # by the manual editor, so it reflects what we've added.
                already = False
                try:
                    already = uri in set(self.dbHandler.get_playlist_track_uris(pid))
                except Exception:
                    already = False
                if already:
                    added = 'already in (mirror)'
                else:
                    added = self.spotifyHandler.add_tracks_playlist(self.username, playlist, [uri])
                    try:
                        self.dbHandler.save_playlist_track(pid, uri)
                    except Exception as e:
                        print(f"radio save: local playlist mirror error: {e!r}", flush=True)
        except Exception as e:
            print(f"radio save: playlist add error: {e!r}", flush=True)
        if playlist and added:
            print(f"radio save: {query!r} → {uri} recorded in DB + added to {playlist} ({added})", flush=True)
        elif playlist:
            print(f"radio save: {query!r} → {uri} recorded in DB but NOT added to "
                  f"{playlist} (Spotify write failed/refused)", flush=True)
        else:
            print(f"radio save: {query!r} → {uri} recorded in DB (no 'new' playlist configured)", flush=True)
        return uri

    def _record_new_once(self, uri, tinfo):
        """Persist a stat identical to a first complete play: option_type 'new'
        (never downgrading a stronger existing type), one completed read."""
        stat = self.dbHandler.get_stat_by_uri(uri)
        if stat is None:
            stat = self.dbHandler.create_stat(uri)
        if stat is None:
            return
        try:
            if not getattr(stat, 'name', None):
                stat.name = tinfo.get('name')
            if not getattr(stat, 'duration_ms', None) and tinfo.get('length'):
                stat.duration_ms = int(tinfo['length'])
        except Exception:
            pass
        rate = 1.0  # heard through to the end on the radio
        prev_count = stat.read_count or 0
        if prev_count <= 1:
            stat.read_end = rate
        else:
            stat.read_end = ((stat.read_end * prev_count) + rate) / (prev_count + 1)
        stat.read_count = prev_count + 1
        stat.read_count_end = (stat.read_count_end or 0) + 1
        stat.last_read_date = datetime.datetime.now(datetime.timezone.utc)
        stat.username = self.username
        # Only set 'new' when unset — never downgrade a promoted/rejected status.
        if not stat.option_type or stat.option_type in ('', 'normal'):
            stat.option_type = 'new'
        try:
            stat.save()
        except Exception as e:
            print(f"radio save: stat save error: {e}")

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
        # Complete plays before a 'new' track is promoted (→ incoming / library).
        # Gentler slope (/4) so the "3 plays" plateau spans DL 5–8 instead of DL7
        # dropping to 2 — loosens the incoming inflow at high discover levels.
        # Effective (ceil): DL0-4→4-5, DL5-8→3, DL9-10→2.
        threshold = (17 - discover_level) / 4.0
        return float(read_count_end) >= threshold

    #Threshold FAVORITES : for adding or removing tracks to favorites (autofill)
    #discover_level = 5 : read_count_end>=12 // if float(read_count_end) >= ((11-discover_level)*2):
    def threshold_adding_favorites(self,stat,discover_level):
        result = False
        ratio = 1+(1-discover_level/20)
        print (f"Favorite test Ratio:{ratio}")
        #if stat.option_type=="library" and (stat.read_end > self.avg_stats['favorites']['read_end']) and (stat.read_count >= self.avg_stats['favorites']['read_count']): 
        if (stat.option_type=="library" 
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
        if stat.option_type=="library":
            if (stat.read_end < self.avg_stats['library']['read_end']) and (stat.read_count >= self.avg_stats['library']['read_count']): result=True
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
