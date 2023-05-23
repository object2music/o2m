import logging

from mopidyapi import MopidyAPI
from src import util
from src.nfctomopidy import NfcToMopidy
from src.spotifyhandler import SpotifyHandler

from flask import Flask

"""
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


    On récupère le fichier de config de mopidy
        config = configparser.ConfigParser()
        config.read(str(Path.home()) + '/.config/mopidy/mopidy.conf')
    On cible la section spotify
        spotify_config = config['spotify']
    On passe les valeurs à spotipy
        client_credentials_manager = SpotifyClientCredentials(client_id=spotify_config['client_id'], client_secret=spotify_config['client_secret'])
        1sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
"""


"""
    Pas très clean de mettre les fonction de callback aux évènements dans le main 
    Mais on a besoin de l'instance de mopidyApi et la fonction callback à besoin de l'instance nfcHandler pour lancer les recos...

    Piste : Ajouter encore une classe mère pour remplacer le main?
"""


api = Flask(__name__)
@api.route('/api/auto')
def api_auto():
    #nfcHandler.clear_tracklist_except_current_song()
    nfcHandler.starting_mode(True)
    
    tag = nfcHandler.get_active_tag_by_uri("mopidy_tag")
    if tag.option_max_results: max_results = tag.option_max_results 
    else: max_results=20
    if tag.option_discover_level: discover_level = tag.option_discover_level 
    else: discover_level=5

    nfcHandler.quicklaunch_auto(max_results,discover_level)    
    nfcHandler.tracklistfill_auto(max_results,discover_level)
    #print (f"AUTO tracklist_uris : {tracklist_uris}")
    #nfcHandler.add_tracks(tag, tracklist_uris1, max_results)
    nfcHandler.play_or_resume()
    return ('auto!')

@api.route('/api/ol')
def api_ol():
    return "<p>Opening Level</p>"

logging.basicConfig(
    format="%(levelname)s CLASS : %(name)s FUNCTION : %(funcName)s LINE : %(lineno)d TIME : %(asctime)s MESSAGE : %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging.DEBUG,
    filename="./logs/o2m.log",
    filemode="a",
)

START_BOLD = "\033[1m"
END_BOLD = "\033[0m"

if __name__ == "__main__":

    mopidy = MopidyAPI()
    o2mConf = util.get_config_file("o2m.conf")  # o2m
    mopidyConf = util.get_config_file("mopidy.conf")  # mopidy
    #mopidyConf = util.get_config_file("snapcast.conf")  # mopidy
    nfcHandler = NfcToMopidy(mopidy, o2mConf, mopidyConf, logging)
    #o2m_api = MyRequestHandler()

    # Fonction called when track started
    @mopidy.on_event("track_playback_started")
    def track_started_event(event):
        track = event.tl_track.track

        #Quick and dirty volume Management
        if "radiofrance-podcast.net" in track.uri :
            nfcHandler.current_volume = nfcHandler.mopidyHandler.mixer.get_volume()
            nfcHandler.mopidyHandler.mixer.set_volume(int(nfcHandler.current_volume*1.5))
            print (f"Get Volume : {nfcHandler.current_volume}")

        # Podcast : seek previous position
        if "podcast" in track.uri and "#" in track.uri:
            if nfcHandler.dbHandler.get_pos_stat(track.uri):
                print(
                    f"seeking prev position : {nfcHandler.dbHandler.get_pos_stat(track.uri)}"
                )
                nfcHandler.mopidyHandler.playback.seek(
                    max(nfcHandler.dbHandler.get_pos_stat(track.uri) - 10, 0)
                )

    # Fonction called when tracked skipped OR completly finished
    @mopidy.on_event("track_playback_ended")
    def track_ended_event(event):
        #Datas
        track = event.tl_track.track
        tag = nfcHandler.get_active_tag_by_uri(track.uri)
        option_type = 'new_mopidy'
        library_link = ''
        data = ''
        position = event.time_position

        #Quick and dirty volume Management
        if "radiofrance-podcast.net" in track.uri :
            print (f"Set Volume : {nfcHandler.current_volume}")
            #nfcHandler.mopidyHandler.mixer.set_volume(nfcHandler.current_volume)
            nfcHandler.mopidyHandler.mixer.set_volume(int(nfcHandler.mopidyHandler.mixer.get_volume()*0.67))
        
        #Update Dynamic datas linked to Tag object and stats
        if tag:
            if tag.data != '': data = tag.data
            if tag.option_type != 'new':
                if hasattr(tag, "option_types") and hasattr(tag, "tlids"):
                    try: option_type = tag.option_types[tag.tlids.index(event.tl_track.tlid)]
                    except Exception as val_e: print(f"Erreur : {val_e}")
                if hasattr(tag, "library_link") and hasattr(tag, "tlids"):
                    try: library_link = tag.library_link[tag.tlids.index(event.tl_track.tlid)]
                    except Exception as val_e: print(f"Erreur : {val_e}")
                #Try / except here to check if dynamic playlist computing is not in competition with first playback finishing...
                if library_link == '': 
                    library_link = tag.data
                    if "m3u" in tag.data:
                        playlist = nfcHandler.mopidyHandler.playlists.lookup(tag.data)
                        for trackp in playlist.tracks:
                            #need to be updated : in which playlist is track if manies ?
                            if 'spotify:playlist' in trackp.uri: 
                                library_link = trackp.uri
                                break
        #print (f"Track :{track}")
        #print (f"Tag :{tag}")
        # print (f"Event {event}")
        print(f"\nEnded song : {track} with option_type {option_type} and library_link {library_link}")

        # Recommandations added at each ended and nottrack an (pour l'instant seulement spotify:track)
        if "track" in track.uri and event.time_position / track.length > 0.9:
            if option_type != 'new': 
                #int(round(discover_level * 0.25))
                try: nfcHandler.add_reco_after_track_read(track.uri,library_link,data)
                except Exception as val_e: 
                    #except nfcHandler.spotifyHandler.sp.client.SpotifyException: nfcHandler.spotifyHandler.init_token_sp() #pb of expired token to resolve...
                    print(f"Erreur : {val_e}")
                    nfcHandler.spotifyHandler.init_token_sp()
                    nfcHandler.add_reco_after_track_read(track.uri,library_link,data)
            if option_type != 'hidden': 
                print ("Adding raw stats")
                nfcHandler.update_stat_raw(track)

        # Podcast
        if "podcast+" in track.uri:
            if nfcHandler.dbHandler.stat_exists(track.uri):
                stat = nfcHandler.dbHandler.get_stat_by_uri(track.uri)
                #If last stat read position is greater than actual: do not update
                if position < stat.read_position: position = stat.read_position
                #print(f"Event : {position} / stat : {stat.read_position}")                
            # If directly in tag data (not m3u) : behaviour to ckeck
            if (position / track.length > 0.7): 
                tag = nfcHandler.dbHandler.get_tag_by_data(track.uri)  # To check !!! Récupère le tag correspondant à la chaine
                if tag != None:
                    if tag.tag_type == "podcasts:channel":
                        tag.option_last_unread = (track.track_no)  # actualise le numéro du dernier podcast écouté
                        tag.update()
                        tag.save()

        # Update stats
        try: 
            nfcHandler.update_stat_track(track,position,option_type,library_link)
        except Exception as val_e: 
            #except nfcHandler.spotifyhandler.sp.client.SpotifyException: 
            print(f"Erreur : {val_e}")
            nfcHandler.spotifyHandler.init_token_sp() #pb of expired token to resolve...
            nfcHandler.update_stat_track(track,position,option_type,library_link)

            
        if "tunein" in track.uri:
            if option_type != 'hidden': nfcHandler.update_stat_raw(track)

        # Tracklist filling when empty
        tracklist_length = mopidy.tracklist.get_length()
        tracklist_index = mopidy.tracklist.index()
        if tracklist_index != None and tracklist_length != 0:
            index = tracklist_index + 1
            tracks_left_count = (
                tracklist_length - index
            )  # Nombre de chansons restante dans la tracklist
            if tracks_left_count < 1:
                nfcHandler.update_tracks()  # si besoin on ajoute des chansons à la tracklist avec de la reco

    # Fonction called when status change ie : stop but impossible to catch track before
    """@mopidy.on_event('playback_state_changed')
    def event_print(event):
        #possibility of track catching ?
        if event.new_state == 'stopped': print (f"Stop : {nfcHandler.mopidyHandler.playback.get_current_track()}")"""

    # Infinite loop for NFC detection and API Launcher
    try:
        #api.run()
        api.run(debug=True, host='0.0.0.0', port=6681)
        nfcHandler.start_nfc()
    except Exception as ex:
        print(f"Erreur : {ex}")
        nfcHandler.spotifyHandler.init_token_sp()
        nfcHandler.start_nfc()
        api.run(debug=True, host='0.0.0.0', port=6681)


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

