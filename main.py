import logging, subprocess

from mopidyapi import MopidyAPI
from src import util
from src.o2mtomopidy import O2mToMopidy
from src.spotifyhandler import SpotifyHandler

from flask import Flask, request
from flask_cors import CORS

"""
    TODO :
        * Logs : séparer les logs par ensemble de fonctionnalités (database, websockets, spotify etc...)
        * Timestamps sur les tags
    Pas très clean de mettre les fonction de callback aux évènements dans le main 
    Mais on a besoin de l'instance de mopidyApi et la fonction callback à besoin de l'instance o2mHandler pour lancer les recos...

    Piste : Ajouter encore une classe mère pour remplacer le main?
"""

START_BOLD = "\033[1m"
END_BOLD = "\033[0m"

if __name__ == "__main__":

#CONFS AND CONSTS
    mopidy = MopidyAPI()
    o2mConf = util.get_config_file("o2m.conf")  # o2m
    mopidyConf = util.get_config_file("mopidy.conf")  # mopidy
    o2mHandler = O2mToMopidy(mopidy, o2mConf, mopidyConf, logging)
    api = Flask(__name__)
    CORS(api)


#API DEF AND LISTENER (to be move in a dedicated part)

    def api_box_action(uid='',option_type='',mode='toogle'):
        if uid!='':
            tag = o2mHandler.dbHandler.get_tag_by_uid(uid)
        if option_type!='':
            tag = o2mHandler.dbHandler.get_tag_by_option_type(option_type)
        #print (f"ACTIVE TAGS : {o2mHandler.activetags}")
        
        #Active Toogle  Add     Remove
        #yes     Remove  Not     Remove  
        #no      Add     Add     Not
        
        if tag != None:
            action = 'No'
            #PRESENT
            if tag in o2mHandler.activetags: 
                if mode == 'toogle' or mode == 'remove': action = 'remove'
            #ABSENT
            else:
                if mode == 'toogle' or mode == 'add': action = 'add'

            if action == 'remove':
                removedTag = next((x for x in o2mHandler.activetags if x.uid == tag.uid), None)
                print(f"removed tag {removedTag}")
                o2mHandler.activetags.remove(tag)
                o2mHandler.tag_action_remove(tag,removedTag)
                return "TAG removed"
            if action == 'add':
                o2mHandler.activetags.append(tag)  #adding tag to list
                print(f"added tag {tag}") 
                o2mHandler.tag_action(tag)
                #tag.add_count()  # Incrémente le compteur de contacts pour ce tag
                return "TAG added"
        else: return "no TAG"

    #API BOX (mode : toogle, add, remove)
    @api.route('/api/box')
    def api_box():
        uid = request.args.get('uid')
        mode = request.args.get('mode')
        option_type = request.args.get('option_type')
        if uid==None: uid=''
        if option_type==None: option_type=''
        if mode==None: mode='toogle'
        return api_box_action(uid,option_type,mode)

    #API box checking (activated or not)
    @api.route('/api/box_activated')
    def api_box_activated():
        uid = request.args.get('uid')
        tag = o2mHandler.dbHandler.get_tag_by_uid(uid)
        if tag != None:
            if tag in o2mHandler.activetags: return("1")
            else: return("0")

    #API Opening Level
    #Get the value
    @api.route('/api/dl')
    def api_dl():
        if o2mHandler.discover_level != None:
            return str(o2mHandler.discover_level)
        else:
            return "No Opening Level"

    #Activate and apply a new value
    @api.route('/api/dl_on')
    def api_dl_on():
        dl = request.args.get('dl')
        if dl != None:
            o2mHandler.discover_level = int(dl)
            o2mHandler.discover_level_on = True

            #Should we relaunch when dl is changed?
            state = o2mHandler.mopidyHandler.playback.get_state()
            relaunch = False
            if state == "stopped": relaunch = True
            else:
                for tag in o2mHandler.activetags:
                    if "auto" in tag.data: relaunch = True
                    elif "m3u" in tag.data:
                        contents = o2mHandler.mopidyHandler.playlists.lookup(tag.data) 
                        for track in contents.tracks:
                            if "auto" in track.uri: relaunch = True
            if relaunch == True:
                #relaunching with the actual boxes
                if len(o2mHandler.activetags)>0:
                    o2mHandler.starting_mode(True,True)
                #relaunching with default_box if exists
                elif o2mHandler.default_box != None:
                    o2mHandler.starting_mode(True,True,o2mHandler.default_box)
            return "New dl"
        else:
            return "No new dl"

    @api.route('/api/reset')
    def api_reset():
        p = subprocess.run("/home/pi/o2m/start_o2m.sh", shell=True, check=True)
        #o2mHandler.starting_mode(True,True)
        return ("reset")

    @api.route('/api/relaunch')
    def api_relaunch():
        p = subprocess.run("/home/pi/o2m/start_mopidy.sh", shell=True, check=True)
        return ("reset")

#MOPIDY LISTENERS
    # Fonction called when track started
    @mopidy.on_event("track_playback_started")
    def track_started_event(event):
        track = event.tl_track.track

        #Quick and dirty volume Management
        if "radiofrance-podcast.net" in track.uri :
            o2mHandler.current_volume = o2mHandler.mopidyHandler.mixer.get_volume()
            o2mHandler.mopidyHandler.mixer.set_volume(int(o2mHandler.current_volume*1.5))
            print (f"Get Volume : {o2mHandler.current_volume}")

        # Podcast : seek previous position
        if "podcast" in track.uri and ("#" or "episode") in track.uri:
            if o2mHandler.dbHandler.get_pos_stat(track.uri) > 0:
                o2mHandler.mopidyHandler.playback.seek(max(o2mHandler.dbHandler.get_pos_stat(track.uri) - 10, 0))
            #skip advertising on sismique
            elif "9851446c-d9b9-47a2-99a9-26d0a4968cc3" in track.uri :
                o2mHandler.mopidyHandler.playback.seek(63000)

    # Fonction called when tracked skipped OR completly finished
    @mopidy.on_event("track_playback_ended")
    def track_ended_event(event):
        #Datas
        track = event.tl_track.track
        tag = o2mHandler.get_active_tag_by_uri(track.uri)
        option_type = 'new_mopidy'
        library_link = ''
        data = ''
        position = event.time_position
        print (position) 

        #Quick and dirty volume Management
        if "radiofrance-podcast.net" in track.uri or "9851446c-d9b9-47a2-99a9-26d0a4968cc3" in track.uri :
            print (f"Set Volume : {o2mHandler.current_volume}")
            #o2mHandler.mopidyHandler.mixer.set_volume(o2mHandler.current_volume)
            o2mHandler.mopidyHandler.mixer.set_volume(int(o2mHandler.mopidyHandler.mixer.get_volume()*0.67))
        
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
                        playlist = o2mHandler.mopidyHandler.playlists.lookup(tag.data)
                        for trackp in playlist.tracks:
                            #need to be updated : in which playlist is track if manies ?
                            if 'spotify:playlist' in trackp.uri: 
                                library_link = trackp.uri
                                break
        print(f"\nEnded song : {track} with option_type {option_type} and library_link {library_link}")

        # Recommandations added at each ended and nottrack an (pour l'instant seulement spotify:track)
        if "track" in track.uri and event.time_position / track.length > 0.9:
            if option_type != 'new': 
                #int(round(discover_level * 0.25))
                try: o2mHandler.add_reco_after_track_read(track.uri,library_link,data)
                except Exception as val_e: 
                    print(f"Erreur : {val_e}")
                    o2mHandler.spotifyHandler.init_token_sp()
                    o2mHandler.add_reco_after_track_read(track.uri,library_link,data)
            if option_type != 'hidden' and option_type != 'trash' : 
                print ("Adding raw stats")
                o2mHandler.update_stat_raw(track.uri)

        # Podcast
        if "podcast+" in track.uri:
            #URI harmonization if max_results used : pb to update track.uri
            '''if "?max_results=" in track.uri: 
                uri1 = track.uri.split("?max_results=")
                if "#" in uri1[1]: 
                    uri2 = uri1[1].split("#")
                    track_uri = str(uri1[0]) + "#" + str(uri2[1])
                else : track_uri = str(uri1[0])'''

            if o2mHandler.dbHandler.stat_exists(track.uri):
                stat = o2mHandler.dbHandler.get_stat_by_uri(track.uri)
                #If last stat read position is greater than actual: do not update
                if position < stat.read_position: position = stat.read_position
                print(f"Event : {position} / stat : {stat.read_position}")
            # If directly in tag data (not m3u) : behaviour to ckeck
            if (position / track.length > 0.7): 
                tag = o2mHandler.dbHandler.get_tag_by_data(track.uri)  # To check !!! Récupère le tag correspondant à la chaine
                if tag != None:
                    if tag.tag_type == "podcasts:channel":
                        tag.option_last_unread = (track.track_no)  # actualise le numéro du dernier podcast écouté
                        tag.update()
                        tag.save()

        # Update stats 
        try: 
            o2mHandler.update_stat_track(track,position,option_type,library_link)
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            o2mHandler.spotifyHandler.init_token_sp() #pb of expired token to resolve
            o2mHandler.update_stat_track(track,position,option_type,library_link)

            
        if "tunein" in track.uri:
            if option_type != 'hidden': o2mHandler.update_stat_raw(track.uri)

        # Tracklist filling when empty
        tracklist_length = mopidy.tracklist.get_length()
        tracklist_index = mopidy.tracklist.index()
        if tracklist_index != None and tracklist_length != 0:
            index = tracklist_index + 1
            tracks_left_count = (
                tracklist_length - index
            )  # Nombre de chansons restante dans la tracklist
            if tracks_left_count < 1:
                o2mHandler.update_tracks()  # si besoin on ajoute des chansons à la tracklist avec de la reco

    # Fonction called when status change ie : stop but impossible to catch track before
    """@mopidy.on_event('playback_state_changed')
    def event_print(event):
        #possibility of track catching ?
        if event.new_state == 'stopped': print (f"Stop : {o2mHandler.mopidyHandler.playback.get_current_track()}")"""



#MAIN LOOP
    # Infinite loop for NFC detection and API Launcher
    try:
        #api.run()
        api.run(debug=True, host='0.0.0.0', port=6681)
    except Exception as ex:
        print(f"Erreur : {ex}")
        o2mHandler.spotifyHandler.init_token_sp()
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