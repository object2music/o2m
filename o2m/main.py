import logging, subprocess, os, spotipy, json, threading, requests

from mopidyapi import MopidyAPI
from src import util
from src.o2mtomopidy import O2mToMopidy
from src.spotifyhandler import SpotifyHandler
from time import sleep

from flask import Flask, request, session, redirect
from flask_session import Session
from flask_cors import CORS

"""
    TODO :
        * Logs : séparer les logs par ensemble de fonctionnalités (database, websockets, spotify etc...)
        * Timestamps sur les boxs
    Pas très clean de mettre les fonction de callback aux évènements dans le main 
    Mais on a besoin de l'instance de mopidyApi et la fonction callback à besoin de l'instance o2mHandler pour lancer les recos...

    Piste : Ajouter encore une classe mère pour remplacer le main?
"""

START_BOLD = "\033[1m"
END_BOLD = "\033[0m"


def _install_resilient_ws_listener():
    """Harden mopidyapi's WSListener against fatal exceptions.

    The stock ``MopidyWSClient._websocket_runner`` only catches
    ``(ConnectionError, ConnectionClosed, OSError)``. A handshake ``EOFError``
    ("connection closed while reading HTTP status line") — seen when mopidy is
    briefly overloaded / restarting after a keepalive ping timeout — escapes the
    ``while True`` loop and kills the listener thread with no recovery. Once dead,
    no more ``track_playback_ended`` / ``track_playback_paused`` events arrive:
    podcasts stop resuming where they left off and stats stop being written,
    while HTTP/RPC (a separate path) keeps working — exactly the observed failure.

    Replace the runner with one that catches *any* exception and reconnects with a
    capped backoff. Event callbacks live on the client (``_event_callbacks``), so
    they survive reconnects untouched.
    """
    import asyncio, time as _time
    import websockets
    from mopidyapi.wsclient import MopidyWSClient

    def _resilient_websocket_runner(self, loop):
        async def packethandler(state):
            async with websockets.connect(self.ws_url) as ws:
                state['ok'] = True  # connected → reset backoff after this session
                while True:
                    msg = await ws.recv()
                    self._on_message(msg)

        base = getattr(self, 'reconnect_time', 0.5) or 0.5
        backoff = base
        while True:
            state = {'ok': False}
            try:
                loop.run_until_complete(packethandler(state))
            except Exception as e:
                try:
                    self.logger.warning(
                        f"Mopidy WS listener error, reconnecting in {backoff:.0f}s: {e}")
                except Exception:
                    pass
            _time.sleep(backoff)
            backoff = base if state['ok'] else min(backoff * 2, 30)

    MopidyWSClient._websocket_runner = _resilient_websocket_runner


_install_resilient_ws_listener()

if __name__ == "__main__":

#CONFS AND CONSTS

    #Launch Connectors and modules
    o2mConf = util.get_config_file("o2m.conf")  # o2m
    #mopidyConf = util.get_config_file("mopidy.conf")  # mopidy
    mopidyConf = ""
    def create_api():
        #FLASK INIT
        api = Flask(__name__)
        CORS(api)
        api.config['SECRET_KEY'] = os.urandom(64)
        api.config['SESSION_TYPE'] = 'filesystem'
        api.config['SESSION_FILE_DIR'] = './.flask_session/'
        Session(api)
        return api

    api=create_api()
    api.app_context().push()

    # Silence noisy Werkzeug access logs for high-frequency polling/health-check
    # endpoints (status badges, track features, Docker healthcheck) so the logs stay
    # readable. Doesn't affect the print()s in o2mtomopidy.py (track end, stats
    # updates, recos, ...) — those go straight to stdout, untouched by this filter.
    # Extend the list as needed.
    _SILENCED_LOG_PATHS = ('/api/track_features', '/api/track_status', '/health')
    class _SilencePollingFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return not any(p in msg for p in _SILENCED_LOG_PATHS)
    logging.getLogger('werkzeug').addFilter(_SilencePollingFilter())

    while True:
        strer = 1
        try:
            #mopidy = MopidyAPI(host='mopidy', port=6680)
            mopidy = MopidyAPI(host=o2mConf["o2m"]["host_mopidy"], port=o2mConf["o2m"]["port_mopidy"])
            #mopidy = MopidyAPI(host='51.15.205.150', port='6680')
            #mopidy = MopidyAPI()
            o2mHandler = O2mToMopidy(mopidy, o2mConf, mopidyConf, logging)
            strer = 0
        except Exception as err_value:
            strer = 1
            print (err_value)

        if strer != 0:
            sleep(10)  # wait for 10 seconds before trying to fetch the data again
        else:
            break

    # Background cache warmup — runs after o2mHandler is ready, non-blocking
    def _background_warmup():
        sleep(5)  # let Flask start first
        try:
            dl = o2mHandler.discover_level if o2mHandler.discover_level is not None else 5
            o2mHandler.spotifyHandler.warmup_cache(discover_level=dl)
        except Exception as e:
            print(f"background warmup error: {e}")

    threading.Thread(target=_background_warmup, daemon=True).start()

    # Periodic popularity recompute — keeps the time-varying terms (recency, and the
    # upcoming add-novelty term) fresh. Recomputes at most ~once a day (cheap), so a
    # long-running process doesn't drift; skips if a recent run already exists.
    def _popularity_scheduler():
        sleep(20)  # let startup settle
        while True:
            try:
                o2mHandler.dbHandler.recompute_popularity_if_stale(ttl_hours=24)
            except Exception as e:
                print(f"popularity scheduler error: {e}")
            sleep(3600)  # re-check hourly

    threading.Thread(target=_popularity_scheduler, daemon=True).start()

#API DEF AND LISTENER (to be move in a dedicated part)
    #API BOX ACTION (mode : toogle, add, remove) AND SHOW
    def api_box_action(uid='',option_type='',mode='toogle'):
        box = None
        if uid!='':
            box = o2mHandler.dbHandler.get_box_by_uid(uid)
        if option_type!='':
            box = o2mHandler.dbHandler.get_box_by_option_type(option_type)
        #print (f"ACTIVE TAGS : {o2mHandler.activeboxs}")
        
        #Active Toogle  Add     Remove
        #yes     Remove  Not     Remove  
        #no      Add     Add     Not
        
        if box != None:
            action = 'No'
            #PRESENT
            if box in o2mHandler.activeboxs: 
                if mode == 'toogle' or mode == 'remove': action = 'remove'
            #ABSENT
            else:
                if mode == 'toogle' or mode == 'add': action = 'add'

            if action == 'remove':
                try: 
                    removedBox = next((x for x in o2mHandler.activeboxs if x.uid == box.uid), None)
                    print(f"removed box {removedBox}")
                    o2mHandler.activeboxs.remove(box)
                    o2mHandler.box_action_remove(box,removedBox)
                    return "TAG removed"
                except Exception as val_e: 
                    print(f"Erreur : {val_e}")
                    return(val_e)

            if action == 'add':
                try:
                    o2mHandler.activeboxs.append(box)  #adding box to list
                    print(f"added box {box}") 
                    o2mHandler.box_action(box)
                    #box.add_count()  # Incrémente le compteur de contacts pour ce box
                    return "TAG added"
                except Exception as val_e: 
                    print(f"Erreur : {val_e}")
                    return(val_e)
            
            if action == 'No':
                return ("No action")
                
        else: return "no TAG"

    # ─── Édition : auth par identité Spotify (proxy Iris public, TEMPORAIRE — migrer en HTTPS) ───
    import functools
    from itsdangerous import URLSafeTimedSerializer

    _EDIT_COOKIE = 'o2m_edit'
    _EDIT_MAX_AGE = 30 * 24 * 3600  # 30 jours

    def _edit_secret():
        """Secret de signature du cookie, auto-généré et persisté (pas de .env requis)."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.edit_cookie_secret')
        try:
            with open(path) as f:
                s = f.read().strip()
            if s:
                return s
        except Exception:
            pass
        import secrets
        s = secrets.token_hex(32)
        try:
            with open(path, 'w') as f:
                f.write(s)
            os.chmod(path, 0o600)
        except Exception:
            pass
        return s

    _edit_serializer = URLSafeTimedSerializer(_edit_secret(), salt='o2m-edit')

    def _edit_allowlist():
        """IDs Spotify autorisés : O2M_EDIT_SPOTIFY_IDS (csv) + défaut SPOTIFY_USERNAME.
        Hors Docker les variables d'env n'existent pas → fallback sur o2m.conf [spotify] username."""
        sources = [os.environ.get('O2M_EDIT_SPOTIFY_IDS', ''),
                   os.environ.get('SPOTIFY_USERNAME', '')]
        try:
            sources.append(o2mConf.get('spotify', 'username', fallback=''))
        except Exception:
            pass
        ids = set()
        for src in sources:
            for part in src.replace(';', ',').split(','):
                p = part.strip().lower()
                if p:
                    ids.add(p)
        return ids

    def _edit_current_user():
        tok = request.cookies.get(_EDIT_COOKIE)
        if not tok:
            return None
        try:
            return _edit_serializer.loads(tok, max_age=_EDIT_MAX_AGE).get('id')
        except Exception:
            return None

    def require_edit_auth(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import jsonify
            if _edit_current_user() is None:
                return jsonify({'error': 'edit_auth_required'}), 401
            return fn(*args, **kwargs)
        return wrapper

    @api.route('/api/edit_auth', methods=['POST'])
    def api_edit_auth():
        """Reçoit un access_token Spotify (obtenu via le proxy Iris), revérifie l'identité
        côté serveur via /v1/me, et pose un cookie signé si l'id est dans l'allowlist."""
        from flask import jsonify, make_response
        data = request.get_json(silent=True) or {}
        token = (data.get('access_token') or '').strip()
        if not token:
            return jsonify({'ok': False, 'error': 'access_token required'}), 400
        try:
            r = requests.get('https://api.spotify.com/v1/me',
                             headers={'Authorization': f'Bearer {token}'}, timeout=8)
        except Exception as e:
            return jsonify({'ok': False, 'error': f'spotify unreachable: {e}'}), 502
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'invalid spotify token'}), 401
        me = r.json()
        uid = (me.get('id') or '').strip()
        name = me.get('display_name') or uid
        if uid.lower() not in _edit_allowlist():
            return jsonify({'ok': False, 'id': uid, 'display_name': name,
                            'reason': 'not_in_allowlist'}), 403
        resp = make_response(jsonify({'ok': True, 'id': uid, 'display_name': name}))
        resp.set_cookie(_EDIT_COOKIE, _edit_serializer.dumps({'id': uid}),
                        max_age=_EDIT_MAX_AGE, httponly=True, samesite='Lax')
        return resp

    @api.route('/api/edit_status')
    def api_edit_status():
        from flask import jsonify
        uid = _edit_current_user()
        return jsonify({'unlocked': uid is not None, 'id': uid})

    @api.route('/api/onboarding')
    def api_onboarding():
        """First-launch state for the welcome flow. `first_launch` is derived from the
        DB itself (no Spotify library ever synced) rather than a stored flag — this is
        per-DB, so an already-populated instance (incl. the o2m_0/o2m_1 shared prod DB)
        is never treated as fresh, and there's nothing to keep in sync."""
        from flask import jsonify, request
        from src.o2mmodels import Playlist
        try:
            liked = o2mHandler.dbHandler.count_cached('liked')
            albums = o2mHandler.dbHandler.count_cached('albums')
            playlists = Playlist.select().count()
        except Exception:
            liked = albums = playlists = 0
        # Spotify OAuth redirect sanity: the configured SPOTIPY_REDIRECT_URI must point at the
        # host the user is actually on, or the login round-trip lands on another instance and
        # the "connect" step can never complete. We only DETECT + report (never edit secrets).
        host = (request.headers.get('X-Forwarded-Host') or request.host).split(':')[0]
        proto = 'https' if request.headers.get('X-Forwarded-Proto', '') == 'https' else request.scheme
        cfg_redirect = (os.getenv('SPOTIPY_REDIRECT_URI') or '').strip()
        cfg_host = cfg_redirect.split('://', 1)[-1].split('/', 1)[0].lower() if cfg_redirect else ''
        expected_redirect = f'{proto}://{host}/api/spotipy_init'
        # host-only comparison; a local 127.0.0.1 access is treated as unknown (not a mismatch)
        redirect_ok = bool(cfg_host) and (host.lower() in ('127.0.0.1', 'localhost') or cfg_host == host.lower())
        return jsonify({
            'first_launch': (liked == 0 and albums == 0 and playlists == 0),
            'onboarding_done': o2mHandler.dbHandler.box_exists('o2m_onboarding'),
            'spotify_connected': _edit_current_user() is not None,
            'counts': {'liked': liked, 'albums': albums, 'playlists': playlists},
            'redirect_ok': redirect_ok,
            'redirect_configured': cfg_redirect,
            'redirect_expected': expected_redirect,
        })

    # Seed boxes pointing to the ORIGINAL owner's playlists (foreign to a new user) +
    # the deprecated Spotify-recommendation seed box.
    _ONBOARDING_FOREIGN = (
        'spotify:playlist:4CAjrciXNfqiDdr757UwBx', 'spotify:playlist:0zM5DUb7FYRVvVjBg3ULp3',
        'spotify:playlist:4oXELBuV9B6QtxYwMdzsoE', 'spotify:playlist:2YndOajMlJlkj7x6WyevW6',
    )
    # Generic starter boxes that work for any authenticated user (no foreign content).
    _ONBOARDING_EXAMPLES = [
        {'description': 'Auto',        'data': 'auto:library\ninfos:library', 'option_type': 'library', 'option_sort': 'smart'},
        {'description': 'Auto albums', 'data': 'albums:spotify',              'option_type': 'library', 'option_sort': 'asc'},
        {'description': 'New',         'data': 'newrecent:library\nnewnotcompleted:library', 'option_type': 'new_mopidy'},
        {'description': 'Podcasts',    'data': 'podcasts:unfinished',          'option_type': 'podcast'},
        {'description': 'Radio France Inter', 'data': 'tunein:station:s24875', 'option_type': 'library'},
    ]

    @api.route('/api/onboarding/setup', methods=['POST'])
    @require_edit_auth
    def api_onboarding_setup():
        """First-launch box setup (idempotent). Sanitizes the foreign-playlist seed
        boxes, creates the user's own writable playlists (Incoming/Trash) + wires the
        system boxes to them, and creates the generic starter boxes. Pass dry_run=1 to
        get the plan without side effects. A marker box makes it a no-op once done."""
        from flask import jsonify
        from src.o2mmodels import Box, Playlist
        data = request.get_json(silent=True) or {}
        dry = bool(data.get('dry_run'))
        db = o2mHandler.dbHandler

        if db.box_exists('o2m_onboarding') and not dry:
            return jsonify({'ok': True, 'skipped': 'already_done'})

        # 1. Sanitize: seed boxes pointing to foreign playlists / deprecated reco seeds.
        to_delete = [{'uid': b.uid, 'description': b.description} for b in Box.select()
                     if any(f in (b.data or '') for f in _ONBOARDING_FOREIGN)
                     or 'spotify:recommendation:seeds' in (b.data or '')]
        # 2. Writable playlists to create for the system boxes (skip if a same-name one exists).
        existing_pl = {(p.name or '').strip() for p in Playlist.select(Playlist.name)}
        want_pl = [('O2M Incoming', 'incoming'), ('O2M Trash', 'trash')]
        to_create_pl = [{'name': n, 'option_type': ot} for n, ot in want_pl if n not in existing_pl]
        # 3. Starter boxes to create (skip existing by description).
        have_boxes = {(b.description or '').strip() for b in Box.select(Box.description)}
        to_create_boxes = [ex for ex in _ONBOARDING_EXAMPLES if ex['description'] not in have_boxes]

        if dry:
            return jsonify({'dry_run': True, 'plan': {
                'delete': to_delete,
                'create_playlists': to_create_pl,
                'create_boxes': [b['description'] for b in to_create_boxes],
            }})

        result = {'deleted': [], 'playlists': [], 'boxes': [], 'errors': []}
        # --- execute: sanitize ---
        for b in to_delete:
            try:
                api_box_action(uid=b['uid'], mode='remove')
                db.delete_box(b['uid'])
                result['deleted'].append(b['uid'])
            except Exception as e:
                result['errors'].append(f"delete {b['uid']}: {e}")
        # --- create writable playlists + wire the system box of that option_type ---
        sp = getattr(o2mHandler.spotifyHandler, 'sp', None)
        username = getattr(o2mHandler, 'username', None)
        for pl in to_create_pl:
            try:
                uri = None
                if sp and username:
                    created = sp.user_playlist_create(username, pl['name'], public=False,
                                                       description='O2M — auto-managed')
                    uri = created.get('uri')
                if uri:
                    box = db.get_box_by_option_type(pl['option_type'])
                    if box is None:
                        box = db.new_box('o2m_' + pl['option_type'])
                        box.option_type = pl['option_type']; box.description = pl['name']; box.favorite = 0
                    box.data = uri
                    box.save()
                    result['playlists'].append({'name': pl['name'], 'uri': uri, 'box': box.uid})
            except Exception as e:
                result['errors'].append(f"playlist {pl['name']}: {e}")
        # --- create starter boxes ---
        import secrets
        for ex in to_create_boxes:
            try:
                uid = secrets.token_hex(8)
                while db.box_exists(uid):
                    uid = secrets.token_hex(8)
                box = db.new_box(uid)
                _apply_box_fields(box, ex)
                box.favorite = 1
                box.save()
                result['boxes'].append(ex['description'])
            except Exception as e:
                result['errors'].append(f"box {ex['description']}: {e}")
        # --- mark done (marker box, ignored by selection) ---
        try:
            m = db.new_box('o2m_onboarding')
            m.description = 'onboarding'; m.option_type = 'hidden'; m.data = 'done'; m.favorite = 0; m.public = 0
            m.save()
        except Exception as e:
            result['errors'].append(f"marker: {e}")
        return jsonify({'ok': True, **result})

    @api.route('/api/edit_logout', methods=['POST'])
    def api_edit_logout():
        from flask import jsonify, make_response
        resp = make_response(jsonify({'ok': True}))
        resp.delete_cookie(_EDIT_COOKIE)
        return resp

    @api.route('/api/box')
    def api_box():
        uid = request.args.get('uid')
        mode = request.args.get('mode')
        option_type = request.args.get('option_type')
        if uid==None: uid=''
        if option_type==None: option_type=''
        if mode==None: mode='toogle'
        return api_box_action(uid,option_type,mode)

    #Return list of favorite boxes
    @api.route('/api/box_favorites')
    def api_box_favorites():
        boxes = o2mHandler.dbHandler.get_boxes_pinned()
        #boxes = json.dumps(boxes)
        return (boxes)

    #Return a single box's data without triggering playback (used by spotdl cache service)
    @api.route('/api/newrecent')
    def api_newrecent():
        """Return unplayed recently-cached tracks for inspection/testing."""
        limit = int(request.args.get('limit', 20))
        days = int(request.args.get('days', 60))
        uris = o2mHandler.dbHandler.get_uris_newrecent(limit=limit, days=days)
        return json.dumps({'count': len(uris), 'days': days, 'uris': uris})

    @api.route('/api/search')
    def api_search():
        """Content search — the DB cache first (tracks/artists/albums/podcast
        episodes/info episodes/radio stations), plus a live Spotify search for
        music (tagged separately so the UI can show cache vs live results)."""
        from flask import jsonify
        q = (request.args.get('q') or '').strip()
        if len(q) < 2:
            return jsonify({'error': 'query too short'}), 400
        try:
            results = o2mHandler.dbHandler.search_local(q)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        try:
            results['radios'] = o2mHandler.search_radio_stations(q)
        except Exception as e:
            results['radios'] = []
        try:
            results['podcast_channels'] = o2mHandler.search_podcast_channels(q)
        except Exception as e:
            results['podcast_channels'] = []
        try:
            results['spotify'] = o2mHandler.spotifyHandler.search_music(q)
        except Exception as e:
            results['spotify'] = {'tracks': [], 'artists': [], 'albums': []}
        return jsonify(results)

    @api.route('/api/podcast_channels')
    def api_podcast_channels():
        """All referenced podcast channels (browse list for the content picker)."""
        from flask import jsonify
        try:
            return jsonify(o2mHandler.list_podcast_channels())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/directory')
    def api_directory():
        """External content directories for the box wizard — the local cache is
        empty on a fresh install, so podcast/radio content has to be discovered
        outside the DB. kind=podcast|radio; with q= it searches, without it
        browses (podcast: top charts of ?genre=, radio: top stations of the
        country). Items are ready-to-use box data lines."""
        from flask import jsonify
        from src import directory
        kind = (request.args.get('kind') or '').strip()
        q = (request.args.get('q') or '').strip()
        country = (request.args.get('country') or '').strip() or None
        try:
            if kind == 'podcast':
                if q:
                    return jsonify({'items': directory.search_podcasts(q), 'mode': 'search'})
                genre = (request.args.get('genre') or '').strip() or None
                return jsonify({'items': directory.top_podcasts(genre, country), 'mode': 'top'})
            if kind == 'radio':
                if q:
                    return jsonify({'items': directory.search_radios(q), 'mode': 'search'})
                return jsonify({'items': directory.top_radios(country), 'mode': 'top'})
            return jsonify({'error': 'unknown kind'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/library_browse')
    def api_library_browse():
        """Cached library listings for the box-content browser:
        kind=playlists|albums|artists. Rows are ready-to-pick (uri/name/sub/image).
        Empty when the Spotify cache hasn't been warmed up yet."""
        from flask import jsonify
        kind = (request.args.get('kind') or '').strip()
        db = o2mHandler.dbHandler
        try:
            if kind == 'playlists':
                rows = [{'uri': p['uri'], 'name': p['name'], 'sub': '', 'image': ''}
                        for p in db.get_playlists_for_select(owner_id=getattr(o2mHandler, 'username', None))]
            elif kind == 'albums':
                rows = db.get_saved_albums()
            elif kind == 'artists':
                rows = db.get_followed_artists()
            else:
                return jsonify({'error': 'unknown kind'}), 400
            return jsonify({'items': rows})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/directory_genres')
    def api_directory_genres():
        """Localized podcast genre list (iTunes), for browsing the directory."""
        from flask import jsonify
        from src import directory
        try:
            country = (request.args.get('country') or '').strip() or None
            return jsonify({'genres': directory.podcast_genres(country)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/resolve_uris', methods=['POST'])
    def api_resolve_uris():
        """Batch-resolve data-line uris to display names, DB cache only (used by
        the structured box-data editor). Never hits Spotify."""
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uris = data.get('uris')
        if not isinstance(uris, list):
            return jsonify({'error': 'uris must be a list'}), 400
        try:
            return jsonify({'results': o2mHandler.dbHandler.resolve_uris(uris[:200])})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/debug/tracklist_ownership')
    def api_debug_tracklist_ownership():
        """Diagnostic (read-only): current tracklist cross-referenced with
        o2mHandler._track_info's box_id, so a 'why is this still here after
        deactivating box X' question can be answered directly instead of guessed
        at. Not linked from the UI; call it manually when investigating."""
        from flask import jsonify
        try:
            tl = o2mHandler.mopidyHandler.tracklist.get_tl_tracks()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        active_uids = {b.uid for b in o2mHandler.activeboxs}
        rows = []
        for tlt in tl:
            info = o2mHandler._track_info.get(tlt.tlid, {})
            box_id = info.get('box_id')
            rows.append({
                'tlid': tlt.tlid, 'uri': tlt.track.uri, 'name': tlt.track.name,
                'option_type': info.get('option_type'), 'box_id': box_id,
                'box_active': box_id in active_uids if box_id else None,
            })
        return jsonify({'active_boxes': sorted(active_uids), 'tracks': rows})

    @api.route('/api/box_info')
    def api_box_info():
        uid = request.args.get('uid')
        if not uid:
            return json.dumps({'error': 'uid required'}), 400
        box = o2mHandler.dbHandler.get_box_by_uid(uid)
        if box is None:
            return json.dumps({'error': 'box not found'}), 404
        return json.dumps({
            'uid': box.uid,
            'data': box.data,
            'description': box.description,
            'option_type': box.option_type,
            'option_sort': box.option_sort,
            'option_discover_level': box.option_discover_level,
            'option_max_results': box.option_max_results,
            'option_duration': box.option_duration,
            'option_energy': box.option_energy,
            'option_valence': box.option_valence,
            'favorite': box.favorite,
            'public': box.public,
            'image_url': box.image_url,
        })

    BOX_OPTION_TYPES = ['library', 'favorites', 'new', 'incoming', 'hidden', 'trash', 'podcast', 'info']
    # 'smart' is an explicit variant of the smart path (NULL/'' also select it,
    # but 'smart' additionally forces a reshuffle) — whitelisted so the ~34 boxes
    # already using it aren't silently reset to NULL when saved from the UI.
    BOX_SORTS = ['shuffle', 'asc', 'desc', 'smart']

    def _apply_box_fields(box, data):
        """Apply whitelisted box fields from a request payload, each
        validated/clamped. Returns the dict of changed fields (not saved)."""
        def _clamp(v, lo, hi):
            try: v = float(v)
            except (TypeError, ValueError): return None
            return max(lo, min(hi, v))
        def _int_or_none(v):
            if v in (None, ''): return None
            try: return int(v)
            except (TypeError, ValueError): return None

        changed = {}
        if 'description' in data:
            box.description = (data['description'] or '').strip() or None; changed['description'] = box.description
        if 'data' in data:
            box.data = data['data'] if data['data'] is not None else ''; changed['data'] = box.data
        if 'option_type' in data and data['option_type'] in BOX_OPTION_TYPES:
            box.option_type = data['option_type']; changed['option_type'] = box.option_type
        if 'option_sort' in data:
            box.option_sort = data['option_sort'] if data['option_sort'] in BOX_SORTS else None; changed['option_sort'] = box.option_sort
        if 'option_discover_level' in data:
            v = _clamp(data['option_discover_level'], 0, 10)
            if v is not None: box.option_discover_level = int(round(v)); changed['option_discover_level'] = box.option_discover_level
        if 'option_max_results' in data:
            box.option_max_results = _int_or_none(data['option_max_results']); changed['option_max_results'] = box.option_max_results
        if 'favorite' in data:
            box.favorite = 1 if data['favorite'] else 0; changed['favorite'] = box.favorite
        if 'public' in data:
            box.public = 1 if data['public'] else 0; changed['public'] = box.public
        if 'option_energy' in data:
            box.option_energy = _clamp(data['option_energy'], 0, 1); changed['option_energy'] = box.option_energy
        if 'option_valence' in data:
            box.option_valence = _clamp(data['option_valence'], 0, 1); changed['option_valence'] = box.option_valence
        if 'image_url' in data:
            box.image_url = (data['image_url'] or '').strip() or None; changed['image_url'] = box.image_url
        return changed

    @api.route('/api/box_edit', methods=['POST'])
    @require_edit_auth
    def api_box_edit():
        """Update editable box fields. Gated on edit rights (same as track edits)."""
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uid = (data.get('uid') or '').strip()
        if not uid:
            return jsonify({'error': 'uid required'}), 400
        box = o2mHandler.dbHandler.get_box_by_uid(uid)
        if box is None:
            return jsonify({'error': 'box not found'}), 404
        changed = _apply_box_fields(box, data)
        try:
            box.save()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        return jsonify({'ok': True, 'uid': uid, 'changed': changed})

    @api.route('/api/box_new', methods=['POST'])
    @require_edit_auth
    def api_box_new():
        """Create a box from the UI. uid is a generated random hex id (same family
        as NFC tag uids, no prefix); a physical tag can be associated later.
        Defaults: favorite=1 so the new box shows up in the boxes panel."""
        from flask import jsonify
        import secrets
        data = request.get_json(silent=True) or {}
        if not (data.get('description') or '').strip():
            return jsonify({'error': 'description required'}), 400
        # Never test existence via get_box_by_uid — it silently auto-creates.
        uid = secrets.token_hex(8)
        while o2mHandler.dbHandler.box_exists(uid):
            uid = secrets.token_hex(8)
        try:
            box = o2mHandler.dbHandler.new_box(uid)
            _apply_box_fields(box, data)
            if 'favorite' not in data:
                box.favorite = 1
            box.save()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        return jsonify({'ok': True, 'uid': uid})

    @api.route('/api/box_delete', methods=['POST'])
    @require_edit_auth
    def api_box_delete():
        """Delete a box. It is deactivated first (same path as a manual toggle
        off, so its tracks leave the tracklist), then the row is dropped."""
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uid = (data.get('uid') or '').strip()
        if not uid:
            return jsonify({'error': 'uid required'}), 400
        if not o2mHandler.dbHandler.box_exists(uid):
            return jsonify({'error': 'box not found'}), 404
        try:
            referenced = o2mHandler.dbHandler.count_boxes_referencing(uid)
            api_box_action(uid=uid, mode='remove')     # deactivate + drop its tracks
            o2mHandler.dbHandler.delete_box(uid)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        return jsonify({'ok': True, 'uid': uid, 'referenced_by': referenced})

    #Register a local file download for a Spotify track (called by spotdl cache service)
    @api.route('/api/register_local_track', methods=['POST'])
    def api_register_local_track():
        data = request.get_json(silent=True) or {}
        spotify_uri = (data.get('spotify_uri') or '').strip()
        local_uri = (data.get('local_uri') or '').strip()
        if not spotify_uri or not local_uri:
            return json.dumps({'error': 'spotify_uri and local_uri required'}), 400
        if not spotify_uri.startswith('spotify:track:'):
            return json.dumps({'error': 'spotify_uri must be spotify:track:'}), 400
        try:
            o2mHandler.dbHandler.set_local_uri(spotify_uri, local_uri)
            return json.dumps({'ok': True, 'spotify_uri': spotify_uri, 'local_uri': local_uri})
        except Exception as e:
            return json.dumps({'error': str(e)}), 500

    #Clear a local file mapping when the file is deleted (called by spotdl cache service)
    @api.route('/api/clear_local_track', methods=['POST'])
    def api_clear_local_track():
        data = request.get_json(silent=True) or {}
        local_uri = (data.get('local_uri') or '').strip()
        if not local_uri:
            return json.dumps({'error': 'local_uri required'}), 400
        try:
            o2mHandler.dbHandler.clear_local_uri_by_file(local_uri)
            return json.dumps({'ok': True})
        except Exception as e:
            return json.dumps({'error': str(e)}), 500

    #API box checking if activated or not
    @api.route('/api/box_activated')
    def api_box_activated():
        o2mHandler.check_active_boxes_health()  # transitional watchdog, see docstring
        uid = request.args.get('uid')
        box = o2mHandler.dbHandler.get_box_by_uid(uid)
        if box != None:
            if box in o2mHandler.activeboxs: return("1")
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
                for box in o2mHandler.activeboxs:
                    if "auto" in box.data: relaunch = True
                    elif "m3u" in box.data:
                        contents = o2mHandler.mopidyHandler.playlists.lookup(box.data) 
                        for track in contents.tracks:
                            if "auto" in track.uri: relaunch = True
            if relaunch == True:
                #relaunching with the actual boxes
                if len(o2mHandler.activeboxs)>0:
                    o2mHandler.starting_mode(True,True)
                #relaunching with default_box if exists
                elif o2mHandler.default_box != None:
                    o2mHandler.starting_mode(True,True,o2mHandler.default_box)
            return "New dl"
        else:
            return "No new dl"
    
    #API TRACK STATUS
    #Get the value from tlid or uri in list
    @api.route('/api/track_status')
    def api_track_status():
        uri = request.args.get('uri')
        try:
            # _track_info is authoritative for current session: checked first so reco/replaced
            # tracks return the right option_type even before (or without) a DB stat entry.
            info = next((v for v in o2mHandler._track_info.values() if v.get('uri') == uri), None)

            # read_end always comes from DB; default 0 if track not yet recorded
            stat = o2mHandler.dbHandler.get_stat_by_uri(uri)
            read_end = float(stat.read_end) if stat else 0.0

            # Inline metric shown in the badge: read_end·popularity (both /10).
            # Popularity is appended only when scored (music tracks).
            _re10 = int(round(read_end, 1) * 10)
            _pop10 = round(float(stat.popularity) * 10) if (stat and stat.popularity is not None) else None
            metric = f"{_re10}·{_pop10}" if _pop10 is not None else str(_re10)

            def mood_suffix(s):
                if not s:
                    return ''
                parts = []
                if s.mood and s.mood != '_':
                    parts.append(s.mood)
                ev = []
                if s.energy is not None:
                    ev.append(str(round(s.energy * 10)))
                if s.valence is not None:
                    ev.append(str(round(s.valence * 10)))
                if ev:
                    parts.append('|'.join(ev))
                return ' (' + ' '.join(parts) + ')' if parts else ''

            # Fast path: library_display from _track_info, option_type from DB
            if info and info.get('library_display'):
                option_type = str(stat.option_type) if stat else 'new'
                status = option_type + " - " + metric + " - " + info['library_display'] + mood_suffix(stat)
                return status

            # Slow path: stat must exist for full DB-based resolution
            if stat is None:
                return 'Manual'

            option_type = str(stat.option_type)
            stored = str(stat.in_library) if stat.in_library else ''

            # Make in_library intelligible:
            # - If stored is already 'type:Name' keep it.
            # - If stored is 'type:<spotifyId>' resolve to 'type:<Name>' at request time.
            # - If stored is a raw spotify URI, resolve it.
            library_name = ''
            if stored:
                try:
                    resolved = stored

                    def _looks_like_spotify_id(s):
                        try:
                            s = str(s)
                            return len(s) == 22 and s.isalnum()
                        except Exception:
                            return False

                    # Handle prefixed format type:value
                    if ':' in stored:
                        prefix, value = stored.split(':', 1)
                        if prefix in {'playlist', 'album', 'artist'}:
                            # sanitize legacy/control-char artifacts like '#015'
                            try:
                                value = str(value).replace('#015', '').replace('\r', '').replace('\n', '').strip()
                            except Exception:
                                pass

                            # If we already stored a display name like "playlist:Calm",
                            # do not hit Spotify again (would try /v1/playlists/Calm).
                            if not value.startswith('spotify:'):
                                normalized_id = o2mHandler.spotifyHandler.normalize_spotify_id(value)
                                if not _looks_like_spotify_id(normalized_id):
                                    resolved = f"{prefix}:{value}"
                                    library_name = resolved
                                    status = option_type + " - " + metric + " - " + library_name + mood_suffix(stat)
                                    return status
                                value = normalized_id

                            if value.startswith('spotify:'):
                                resolved_uri = o2mHandler.spotifyHandler.normalize_spotify_uri(value)
                            else:
                                resolved_uri = o2mHandler.spotifyHandler.normalize_spotify_uri(f"spotify:{prefix}:{value}")

                            # Resolve via Spotify (retry token once on failure)
                            try:
                                name_only = o2mHandler.spotifyHandler.get_resource_name(resolved_uri)
                            except Exception:
                                o2mHandler.spotifyHandler.init_token_sp()
                                name_only = o2mHandler.spotifyHandler.get_resource_name(resolved_uri)

                            # get_resource_name can fallback to returning the URI; keep it stable
                            if isinstance(name_only, str) and name_only.startswith('spotify:'):
                                # last resort: keep original value (id or name)
                                name_only = value

                            resolved = f"{prefix}:{name_only}"
                        else:
                            # Unknown prefix, leave as-is
                            resolved = stored
                    elif stored.startswith('spotify:'):
                        # Raw spotify URI
                        try:
                            resolved = o2mHandler.spotifyHandler.get_resource_name(stored)
                        except Exception:
                            o2mHandler.spotifyHandler.init_token_sp()
                            resolved = o2mHandler.spotifyHandler.get_resource_name(stored)

                    library_name = resolved

                    # Persist resolved name so subsequent calls skip the API entirely
                    if resolved and resolved != stored and not resolved.startswith('spotify:'):
                        try:
                            stat.in_library = resolved
                            stat.save()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Error getting library name: {e}")
                    library_name = stored

            status = option_type + " - " + metric + " - " + library_name + mood_suffix(stat)
        except Exception as val_e:
            status = 'new'
        return status

        #tlid = int(request.args.get('tlid'))
        #tracks = o2mHandler.mopidyHandler.tracklist.filter({'tlid':[tlid]})
        #tracks = o2mHandler.mopidyHandler.tracklist.slice(tlid,tlid+1)
        '''if tracks != None:
            print (tracks)
            uri = tracks[0].track['uri']
            stat = o2mHandler.dbHandler.get_stat_by_uri(uri)
            return stat['option_type']
        else:
            return "no track"'''

    @api.route('/api/cache_playlists')
    def api_cache_playlists():
        """Trigger bulk cache of all user playlists and their tracks."""
        count = o2mHandler.spotifyHandler.cache_all_playlists()
        return f"cached {count} tracks"

    @api.route('/api/warmup_genres')
    def api_warmup_genres():
        """Force an immediate genre warmup run (bypasses TTL)."""
        import threading
        o2mHandler.dbHandler.set_cache_meta('warmup_genres_at', 0)
        def _run():
            try:
                o2mHandler.spotifyHandler.warmup_artist_genres()
            except Exception as e:
                print(f"api_warmup_genres error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        return "genre warmup started"

    @api.route('/api/diag/genres')
    def api_diag_genres():
        """Synchronous genre diagnostic — runs warmup and returns JSON results."""
        from flask import jsonify
        try:
            o2mHandler.dbHandler.set_cache_meta('warmup_genres_at', 0)
            result = o2mHandler.spotifyHandler.warmup_artist_genres()
            return jsonify(result or {'error': 'no result'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/warmup_moods')
    def api_warmup_moods():
        """Trigger mood/energy/valence warmup for tracks missing features (background, up to 1000 tracks)."""
        import threading
        o2mHandler.dbHandler.set_cache_meta('warmup_moods_at', 0)
        def _run():
            try:
                o2mHandler.spotifyHandler.warmup_track_moods(batch_size=50, max_batches=20)
            except Exception as e:
                print(f"api_warmup_moods error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        pending = o2mHandler.dbHandler.count_tracks_without_mood()
        from flask import jsonify
        return jsonify({'status': 'started', 'tracks_pending': pending})

    @api.route('/api/recompute_popularity')
    def api_recompute_popularity():
        """Recompute the composite popularity score for all tracks (background, stats_v2)."""
        import threading
        from flask import jsonify
        def _run():
            try:
                o2mHandler.dbHandler.recompute_popularity()
            except Exception as e:
                print(f"api_recompute_popularity error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'status': 'started'})

    @api.route('/api/expand_pick_mode')
    def api_expand_pick_mode():
        """Get or set the _expand_pick selection variant (A/B testing, in-memory).
        ?mode=hybrid|weighted|topm sets it; no arg returns the current value."""
        from flask import jsonify
        valid = ('hybrid', 'temp', 'band')
        mode = request.args.get('mode')
        if mode:
            if mode not in valid:
                return jsonify({'error': 'invalid mode', 'valid': list(valid)}), 400
            o2mHandler.expand_pick_mode = mode
        return jsonify({'mode': getattr(o2mHandler, 'expand_pick_mode', 'hybrid'),
                        'valid': list(valid)})

    @api.route('/api/track_tags')
    def api_track_tags():
        from flask import jsonify
        uri = request.args.get('uri', '')
        if not uri:
            return jsonify([])
        tags = o2mHandler.dbHandler.get_track_genres(uri)  # [(name, weight)]
        if not tags:
            # Fallback: artist-level genres (weight=1, no specific track data)
            genres = o2mHandler.dbHandler.get_artist_genres_for_track(uri)
            tags = [(name, 1) for name in genres]
        return jsonify([{'name': name, 'weight': weight}
                        for name, weight in sorted(tags, key=lambda x: -x[1])])

    @api.route('/api/warmup_retry_sentinels')
    def api_warmup_retry_sentinels():
        """Trigger full retry of all sentinel tracks via the complete Last.fm chain (background)."""
        import threading
        def _run():
            try:
                o2mHandler.spotifyHandler.warmup_retry_all_sentinels(batch_size=50, max_batches=200)
            except Exception as e:
                print(f"api_warmup_retry_sentinels error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        from flask import jsonify
        return jsonify({'status': 'started'})

    @api.route('/api/warmup_spotify_features')
    def api_warmup_spotify_features():
        """Trigger Spotify audio_features warmup (background, up to 10k tracks per call)."""
        import threading
        o2mHandler.dbHandler.set_cache_meta('warmup_spotify_features_at', 0)
        def _run():
            try:
                o2mHandler.spotifyHandler.warmup_spotify_features(batch_size=100, max_batches=100)
            except Exception as e:
                print(f"api_warmup_spotify_features error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        pending = o2mHandler.dbHandler.count_spotify_tracks_without_features()
        from flask import jsonify
        return jsonify({'status': 'started', 'tracks_pending': pending})

    # ── Mood interface ────────────────────────────────────────────────────────────

    @api.route('/api/mood', methods=['GET'])
    def api_mood_get():
        from flask import jsonify
        dist = o2mHandler.dbHandler.get_mood_distribution()
        pending = o2mHandler.dbHandler.count_tracks_without_mood()
        return jsonify({
            'energy':          o2mHandler.mood_energy,
            'valence':         o2mHandler.mood_valence,
            'genres':          o2mHandler.mood_genres,
            'discover_level':  o2mHandler.discover_level,
            'distribution':    dist,
            'tracks_pending':  pending,
        })

    @api.route('/api/mood', methods=['POST'])
    def api_mood_post():
        from flask import jsonify, request as req
        data = req.get_json(silent=True) or {}
        if 'energy' in data:
            o2mHandler.mood_energy = float(data['energy'])
        if 'valence' in data:
            o2mHandler.mood_valence = float(data['valence'])
        if 'genres' in data:
            o2mHandler.mood_genres = data['genres'] if isinstance(data['genres'], list) else []
        if 'discover_level' in data:
            o2mHandler.discover_level = int(data['discover_level'])
        # apply=false → store the settings only (no rebuild, no auto-box launch).
        # Used by the /basic view when no actuator is on: the dials set the values
        # that the next Music launch will use.
        if data.get('apply') is False:
            return jsonify({'status': 'settings_saved', 'tracks_added': 0})
        added = o2mHandler.apply_mood_settings()
        if added is not None and added < 0:
            # Skipped: user boxes are active → mood affects their future recommendations.
            return jsonify({'status': 'boxes_active', 'tracks_added': 0})
        return jsonify({'status': 'ok', 'tracks_added': added})

    @api.route('/api/track_features')
    def api_track_features():
        from flask import jsonify
        from src.o2mmodels import Track
        uris = request.args.getlist('uri')[:40]
        if not uris:
            return jsonify({})
        try:
            result = {}
            for t in Track.select(Track.uri, Track.energy, Track.valence, Track.popularity).where(
                Track.uri.in_(uris) & Track.energy.is_null(False)
            ):
                result[t.uri] = {'energy': float(t.energy), 'valence': float(t.valence)}
                if t.popularity is not None:
                    result[t.uri]['popularity'] = float(t.popularity)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ─── Édition des features d'un morceau (énergie/valence/mood) ───
    @api.route('/api/track_features', methods=['POST'])
    @require_edit_auth
    def api_track_features_set():
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uri = (data.get('uri') or '').strip()
        if not uri:
            return jsonify({'error': 'uri required'}), 400
        def _f01(x):
            try:
                return min(1.0, max(0.0, float(x)))
            except (TypeError, ValueError):
                return None
        energy  = _f01(data['energy'])  if 'energy'  in data else None
        valence = _f01(data['valence']) if 'valence' in data else None
        mood    = (data.get('mood') or None) if 'mood' in data else None
        # Auto-derive the categorical mood from a manual energy/valence edit (matrix drag),
        # unless the caller set the mood explicitly (dropdown). One-way: e/v → mood.
        if mood is None and energy is not None:
            v = valence
            if v is None:
                try:
                    t = o2mHandler.dbHandler.get_stat_by_uri(uri)
                    v = float(t.valence) if (t and t.valence is not None) else None
                except Exception:
                    v = None
            mood = util.mood_from_energy_valence(energy, v)
        try:
            o2mHandler.dbHandler.upsert_track_features(uri, mood=mood, energy=energy, valence=valence)
            return jsonify({'ok': True, 'uri': uri, 'energy': energy, 'valence': valence, 'mood': mood})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ─── Statut favori Spotify (compte serveur) pour affichage combiné ───
    @api.route('/api/track_saved')
    def api_track_saved():
        from flask import jsonify
        uri = (request.args.get('uri') or '').strip()
        if not uri or not uri.startswith('spotify:track:'):
            return jsonify({'saved': None})
        try:
            return jsonify({'saved': o2mHandler.spotifyHandler.is_track_saved(uri)})
        except Exception as e:
            return jsonify({'saved': None, 'error': str(e)})

    # ─── Toggle favori : DB locale + Spotify (si morceau Spotify) ───
    @api.route('/api/track_favorite', methods=['POST'])
    @require_edit_auth
    def api_track_favorite():
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uri = (data.get('uri') or '').strip()
        favorite = bool(data.get('favorite'))
        if not uri:
            return jsonify({'error': 'uri required'}), 400
        result = {'ok': True, 'uri': uri, 'favorite': favorite}
        # Local DB
        try:
            o2mHandler.dbHandler.set_track_liked(uri, favorite)
            result['liked_local'] = favorite
        except Exception as e:
            result['liked_local_error'] = str(e)
        # Spotify (compte serveur), seulement pour les morceaux Spotify
        if uri.startswith('spotify:track:'):
            try:
                o2mHandler.spotifyHandler.set_track_saved(uri, favorite)
                result['liked_spotify'] = favorite
            except Exception as e:
                result['liked_spotify_error'] = str(e)
        return jsonify(result)

    # ─── Playlists : liste éditable + appartenance + add/remove ───
    @api.route('/api/playlists')
    def api_playlists():
        from flask import jsonify
        owner = getattr(o2mHandler, 'username', None)
        try:
            return jsonify(o2mHandler.dbHandler.get_playlists_for_select(owner_id=owner))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/track_playlists')
    def api_track_playlists():
        from flask import jsonify
        uri = (request.args.get('uri') or '').strip()
        if not uri:
            return jsonify([])
        try:
            return jsonify(o2mHandler.dbHandler.get_playlists_with_track(uri))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/track_playlist', methods=['POST'])
    @require_edit_auth
    def api_track_playlist():
        from flask import jsonify
        data = request.get_json(silent=True) or {}
        uri = (data.get('uri') or '').strip()
        pid = (data.get('playlist_id') or '').strip()
        action = (data.get('action') or '').strip()
        if not uri or not pid or action not in ('add', 'remove'):
            return jsonify({'error': 'uri, playlist_id, action(add|remove) required'}), 400
        playlist_uri = f'spotify:playlist:{pid}'
        try:
            if action == 'add':
                o2mHandler.spotifyHandler.add_tracks_playlist(
                    getattr(o2mHandler, 'username', None), playlist_uri, [uri])
                o2mHandler.dbHandler.save_playlist_track(pid, uri)
            else:
                o2mHandler.spotifyHandler.remove_tracks_playlist(playlist_uri, [uri])
                o2mHandler.dbHandler.remove_playlist_track(pid, uri)
            try:
                o2mHandler.dbHandler.create_playlist_log(
                    uri, playlist_uri, action, username=getattr(o2mHandler, 'username', None))
            except Exception:
                pass
            return jsonify({'ok': True, 'uri': uri, 'playlist_id': pid, 'action': action})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/genres')
    def api_genres():
        from flask import jsonify
        return jsonify(o2mHandler.dbHandler.get_genres_with_counts())

    @api.route('/api/track_info')
    def api_track_info():
        from flask import jsonify
        uri = request.args.get('uri')
        if not uri:
            return jsonify({})
        try:
            stat = o2mHandler.dbHandler.get_stat_by_uri(uri)
            info = next((v for v in o2mHandler._track_info.values() if v.get('uri') == uri), None)
            library = (info.get('library_display') if info else None) or (str(stat.in_library) if stat and stat.in_library else '')
            # Classification for display: the LIVE box context (_track_info) wins over
            # the stored stat — a stat can lag/mis-tag (e.g. a podcast served from an
            # info box that got written 'new'). Fall back to the stat, then to a
            # uri-derived type so a podcast/info stream never shows the music 'new'.
            opt = (str(info.get('option_type')) if (info and info.get('option_type')) else
                   (str(stat.option_type) if stat else None))
            # Spoken content never shows a music tag: a podcast/video URI carrying a
            # music type (new/library/favorites/incoming/…) is displayed as 'podcast'
            # ('info' is kept — it's a legitimate spoken classification).
            if (('podcast+' in uri) or ('youtube:video' in uri) or ('yt:' in uri)) and \
               opt not in ('info', 'podcast'):
                opt = 'podcast'
            if not opt:
                opt = 'new'
            return jsonify({
                'option_type':    opt,
                'read_end':       round(float(stat.read_end), 2) if stat else 0.0,
                'read_count_end': int(stat.read_count_end) if stat else 0,
                'mood':           str(stat.mood) if stat and stat.mood and stat.mood != '_' else None,
                'energy':         round(float(stat.energy), 3) if stat and stat.energy is not None else None,
                'valence':        round(float(stat.valence), 3) if stat and stat.valence is not None else None,
                'popularity':     round(float(stat.popularity), 3) if stat and stat.popularity is not None else None,
                'liked':          bool(stat.liked) if stat else False,
                'library':        library,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/play_next')
    def api_play_next():
        """Queue a track right after the current one, with O2M's live URI
        adaptation (swap a Spotify track for its cached local file when present,
        recording the local→spotify mapping for stats) — same path O2M uses when
        it fills the tracklist, so externally-cached content is used live."""
        from flask import jsonify
        uris_in = request.args.getlist('uri')  # one or many uri= params (album/artist queue)
        if not uris_in:
            return jsonify({'error': 'uri required'}), 400
        try:
            m = o2mHandler.mopidyHandler
            tl_length = m.tracklist.get_length()
            # Insert right after the currently playing track. Prefer the current
            # tl_track (reliable while playing); fall back to tracklist.index(),
            # then to the end of the tracklist if nothing is playing.
            at = None
            try:
                cur_tl = m.playback.get_current_tl_track()
                if cur_tl is not None:
                    ci = m.tracklist.index(cur_tl)
                    if isinstance(ci, int):
                        at = ci + 1
            except Exception:
                at = None
            if at is None:
                idx = m.tracklist.index()
                at = (idx + 1) if isinstance(idx, int) else tl_length
            resolved = o2mHandler._resolve_uris(uris_in)
            if not resolved:
                return jsonify({'error': 'unresolved uri'}), 400
            added = m.tracklist.add(uris=resolved, at_position=at)
            tlid = None
            try: tlid = added[0].tlid
            except Exception: pass
            return jsonify({'ok': True, 'at_position': at, 'count': len(resolved), 'tlid': tlid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def _spotify_id(uri):
        return uri.split(':')[-1] if uri and ':' in uri else (uri or '')

    @api.route('/api/album_info')
    def api_album_info():
        """Album detail served from the O2M DB cache (Album + Track.album_id +
        TrackArtist). Returns {cached: False} when the album isn't in the DB so the
        client can fall back to a live Spotify lookup."""
        from flask import jsonify
        aid = _spotify_id(request.args.get('uri'))
        try:
            d = o2mHandler.dbHandler.get_album_detail(aid)
            if d and not d.get('partial'):
                d['cached'] = True
                return jsonify(d)
            # Incomplete or missing in cache → lazy backfill from Spotify into the DB,
            # then re-read so this album is fully cache-served from now on.
            try:
                o2mHandler.spotifyHandler.backfill_album(aid)
            except Exception as e:
                print(f"album backfill error: {e}")
            d2 = o2mHandler.dbHandler.get_album_detail(aid)
            if d2:
                d2['cached'] = True
                d2['backfilled'] = True
                return jsonify(d2)
            return jsonify({'cached': False})
        except Exception as e:
            return jsonify({'cached': False, 'error': str(e)})

    @api.route('/api/artist_info')
    def api_artist_info():
        """Artist detail served from the O2M DB cache (Artist + TrackArtist +
        AlbumArtist + ArtistGenre). {cached: False} → client falls back to Spotify."""
        from flask import jsonify
        aid = _spotify_id(request.args.get('uri'))
        try:
            d = o2mHandler.dbHandler.get_artist_detail(aid)
            if not d:
                return jsonify({'cached': False})
            d['cached'] = True
            return jsonify(d)
        except Exception as e:
            return jsonify({'cached': False, 'error': str(e)})

    @api.route('/mood')
    def mood_ui():
        # Primary mood UI (design-system version, formerly mood2.html).
        from flask import send_from_directory
        return send_from_directory('static', 'mood.html')

    @api.route('/basic')
    def basic_ui():
        # Basic view (default on mobile): same page, the client switches to
        # basic mode based on the /basic path — no separate file to maintain.
        from flask import send_from_directory
        return send_from_directory('static', 'mood.html')

    @api.route('/api/basic_boxes')
    def api_basic_boxes():
        """Pinned boxes grouped for the /basic view actuators. Read-only —
        categories: music (the auto box: data has an 'auto:' line), podcast/info
        (by option_type), radio (data carries direct audio-stream URLs).
        Cascade boxes (data has uncommented 'box:' include lines — composite
        scenarios like auto_morning) are excluded: an actuator only drives
        direct sources, and a cascade would light other actuators as a side
        effect (e.g. Info pulling in the auto box)."""
        from flask import jsonify
        o2mHandler.check_active_boxes_health()  # transitional watchdog, see docstring
        try:
            active_uids = {b.uid for b in o2mHandler.activeboxs}
            out = {}
            for cat, boxes in o2mHandler.get_basic_categories().items():
                rows = []
                for box in boxes:
                    lr = box.get('last_read_date')
                    try:
                        lr = lr.timestamp() if hasattr(lr, 'timestamp') else (float(lr) if lr else 0)
                    except Exception:
                        lr = 0
                    rows.append({'uid': box['uid'], 'description': box.get('description'),
                                 'active': box['uid'] in active_uids, 'last_read': lr})
                out[cat] = rows
            out['limit'] = o2mHandler.max_results   # fill target for multi-source categories
            return jsonify(out)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/basic_toggle')
    def api_basic_toggle():
        """Atomic actuator action for the /basic view: one request activates
        (meta_fill: sources drawn recency × chance up to the limit) or deactivates
        (meta_remove) a whole category server-side — the client no longer loops box
        by box, so a page reload or phone lock can't leave a partial state."""
        from flask import jsonify
        cat = request.args.get('cat')
        mode = request.args.get('mode', 'add')
        if cat not in ('music', 'podcast', 'info', 'radio'):
            return jsonify({'error': 'cat must be music|podcast|info|radio'}), 400
        try:
            if mode == 'remove':
                return jsonify({'ok': True, 'removed': o2mHandler.meta_remove(cat)})
            return jsonify({'ok': True, 'gained': o2mHandler.meta_fill(cat)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/mood2')
    def mood2_ui():
        # Transitional alias → same as /mood (kept so existing test links don't 404).
        from flask import send_from_directory
        return send_from_directory('static', 'mood.html')

    @api.route('/mood_legacy')
    def mood_legacy_ui():
        # Archived pre-design-system UI, unplugged from the default route but kept
        # reachable here if ever needed.
        from flask import send_from_directory
        return send_from_directory('static', 'mood_legacy.html')

    @api.route('/sw.js')
    def service_worker():
        # Servi depuis la racine pour que le scope du service worker couvre tout
        # le site (/mood inclus). Ne s'enregistrera qu'en HTTPS (cf. sw.js).
        from flask import send_from_directory
        resp = send_from_directory('static', 'sw.js')
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp

    @api.route('/api/client_config')
    def api_client_config():
        from flask import jsonify, request as req
        # Behind Caddy (HTTPS): route the WebSockets through the domain as wss
        # (Mopidy under /mopidy/ws, Snapcast under /snapcast) to avoid mixed-content.
        # On direct LAN access (HTTP): keep the direct ports.
        host = (req.headers.get('X-Forwarded-Host') or req.host).split(':')[0]
        # Snapcast is only relevant when Mopidy's audio output is routed to the
        # snap fifo (AUDIO_OUTPUT contains 'snapfifo'/'snapcast'). Otherwise we omit
        # the snap_* URLs so the client hides the Snapcast button.
        audio_output = os.environ.get('AUDIO_OUTPUT', '').lower()
        snap_enabled = ('snapfifo' in audio_output) or ('snapcast' in audio_output)
        # Same env var the Iris sidebar uses (mopidy/entrypoint.sh O2M_BACKOFFICE_URI),
        # so the mood UI's footer link stays in sync with whatever this instance points to.
        backoffice_url = os.environ.get('O2M_BACKOFFICE_URI') or None
        if req.headers.get('X-Forwarded-Proto', '') == 'https':
            cfg = {'mopidy_ws_url': f'wss://{host}/mopidy/ws', 'backoffice_url': backoffice_url}
            if snap_enabled:
                cfg['snap_url']    = f'https://{host}/snapcast'
                cfg['snap_ws_url'] = f'wss://{host}/snapcast'
            return jsonify(cfg)
        snap_port = os.environ.get('PORT_SNAPSERVER_HTTP', '6693')
        mopidy_port = os.environ.get('PORT_MOPIDY', '6680')
        cfg = {'mopidy_ws_url': f'ws://{host}:{mopidy_port}/mopidy/ws', 'backoffice_url': backoffice_url}
        if snap_enabled:
            cfg['snap_url']    = f'http://{host}:{snap_port}'
            cfg['snap_ws_url'] = f'ws://{host}:{snap_port}'
        return jsonify(cfg)

    @api.route('/tag_features')
    def tag_features_ui():
        from flask import send_from_directory
        return send_from_directory('static', 'tag_features.html')

    @api.route('/api/tag_features', methods=['GET'])
    def api_tag_features_get():
        from flask import jsonify
        filter_type = request.args.get('filter')  # all / noise / mood / feature / unknown
        if filter_type == 'unknown':
            tags = o2mHandler.dbHandler.get_unknown_tags(limit=200)
            return jsonify([{'tag': t} for t in tags])
        return jsonify(o2mHandler.dbHandler.get_all_tag_features(filter_type=filter_type))

    @api.route('/api/tag_features', methods=['POST'])
    def api_tag_features_post():
        from flask import jsonify
        data = request.get_json(force=True) or {}
        tag = data.get('tag', '').strip()
        if not tag:
            return jsonify({'error': 'tag required'}), 400
        ok = o2mHandler.dbHandler.upsert_tag_feature(
            tag,
            energy=data.get('energy'),
            valence=data.get('valence'),
            mood=data.get('mood') or None,
            is_noise=int(data.get('is_noise', 0)),
        )
        if ok:
            o2mHandler.spotifyHandler._reload_tag_features()
        return jsonify({'ok': ok})

    @api.route('/api/tag_features/<path:tag>', methods=['DELETE'])
    def api_tag_features_delete(tag):
        from flask import jsonify
        ok = o2mHandler.dbHandler.delete_tag_feature(tag)
        if ok:
            o2mHandler.spotifyHandler._reload_tag_features()
        return jsonify({'ok': ok})

    @api.route('/api/stats/mood')
    def api_stats_mood():
        from flask import jsonify
        try:
            return jsonify(o2mHandler.dbHandler.get_stats_mood())
        except Exception as e:
            return jsonify({'error': str(e), 'mood_distribution': {}, 'scatter': []}), 500

    @api.route('/api/stats/tracks')
    def api_stats_tracks():
        from flask import jsonify
        try:
            return jsonify(o2mHandler.dbHandler.get_stats_tracks())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.route('/api/stats/breakdown')
    def api_stats_breakdown():
        from flask import jsonify
        try:
            return jsonify(o2mHandler.dbHandler.get_stats_breakdown())
        except Exception as e:
            return jsonify({'error': str(e), 'categories': [], 'totals': {}}), 500

    @api.route('/api/stats/playlist_log')
    def api_stats_playlist_log():
        from flask import jsonify, request as req
        try:
            limit = int(req.args.get('limit', 100))
        except Exception:
            limit = 100
        limit = max(1, min(limit, 1000))
        try:
            return jsonify(o2mHandler.dbHandler.get_playlist_log(limit))
        except Exception as e:
            return jsonify({'error': str(e), 'log': []}), 500

    @api.route('/stats')
    def stats_ui():
        from flask import send_from_directory
        return send_from_directory('static', 'stats.html')

    @api.route('/api/mopidy_rpc', methods=['POST'])
    def api_mopidy_rpc():
        from flask import jsonify, request as req
        import urllib.request, urllib.error
        body = req.get_data()
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(mopidy.http_url, data=body,
                    headers={'Content-Type': 'application/json'}), timeout=5)
            return r.read(), 200, {'Content-Type': 'application/json'}
        except urllib.error.URLError as e:
            return jsonify({'error': str(e)}), 502

    @api.route('/api/mopidy_image')
    def api_mopidy_image():
        from flask import request as req, redirect as redir
        import urllib.request
        uri = req.args.get('uri', '')
        if not uri:
            return '', 404
        if uri.startswith('http'):
            return redir(uri)
        base = mopidy.http_url.replace('/mopidy/rpc', '')
        try:
            r = urllib.request.urlopen(base + uri, timeout=5)
            ct = r.headers.get('Content-Type', 'image/jpeg')
            return r.read(), 200, {'Content-Type': ct}
        except Exception:
            return '', 404

    #RESTART
    @api.route('/health')
    def health_check():
        return "OK", 200

    @api.route('/api/toogle_play')
    def api_toogle_play():
        o2mHandler.play_or_resume()
        return ("play !")

    @api.route('/api/initialize_playback')
    def api_initialize_playback():
        """Trigger initialize_playback on the o2m handler.

        The server determines the current time; the client should not supply the time.
        An optional `window` query param is ignored for time-of-day — server-side clock is used.
        `nobox=1` keeps unmute + resume-if-paused but never auto-launches a box
        (used by the /basic view).
        """
        try:
            nobox = request.args.get('nobox') in ('1', 'true')
            result = o2mHandler.initialize_playback(allow_box=not nobox)
            if result:
                return ("initialized")
            else:
                return ("no_action")
        except Exception as e:
            return (str(e)), 500
    
    @api.route('/api/reset_o2m')
    def api_reset_o2m():
        o2mHandler.starting_mode(True,True)
        return ("reset")

    @api.route('/api/clear_boxes')
    def api_clear_boxes():
        """Authoritatively deactivate EVERY active box server-side and clear the
        tracklist — a clean slate so the mood matrix rebuilds the auto mix.
        (starting_mode clears the tracklist but not activeboxs, and the UI only
        deactivates boxes it renders; this is the reliable empty-everything.)"""
        from flask import jsonify
        o2mHandler.activeboxs = []
        try:
            o2mHandler.starting_mode(clear=True)
        except Exception as e:
            print(f"clear_boxes error: {e}")
        return jsonify({'status': 'cleared'})

    @api.route('/api/restart_o2m')
    def api_restart_o2m():
        p = subprocess.run("start_o2m.sh", shell=True, check=True)
        return ("reset")

    @api.route('/api/restart_mopidy')
    def api_restart_mopidy():
        def do_restart():
            sleep(1)
            subprocess.run(['docker', 'compose', '--profile', 'prod', 'restart', 'mopidy', 'o2m'],
                           capture_output=True)
        threading.Thread(target=do_restart, daemon=True).start()
        return ("restarting")

    @api.route('/api/clear_today_history')
    def api_clear_today_history():
        o2mHandler.dbHandler.clear_lasthour_stats_raw()
        return ("cleared")

    #SPOTIPY
    if o2mHandler.spotifyHandler.spotipy_config:
        @api.route('/api/spotipy_check')
        def api_spotipy_check():
            cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=o2mHandler.spotifyHandler.cache_path)        
            auth_manager = spotipy.oauth2.SpotifyOAuth(scope=o2mHandler.spotifyHandler.scope,cache_handler=cache_handler,show_dialog=True)
            if not auth_manager.validate_token(cache_handler.get_cached_token()):
                return ("spotipy_init")
            else:
                return ("spotipy_out")

        @api.route('/api/spotipy_init')
        def api_spotipy_init():
            cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=o2mHandler.spotifyHandler.cache_path)        
            auth_manager = spotipy.oauth2.SpotifyOAuth(scope=o2mHandler.spotifyHandler.scope,cache_handler=cache_handler,show_dialog=True)

            if request.args.get("code"):
                # Step 2. Being redirected from Spotify auth page.
                # The token lands in .cache_spotipy = the per-user OVERLAY (Web API: favorites,
                # library, write). Seed the instance baseline once (fixed house account for
                # streaming + fallback), then (re)build sp preferring the overlay.
                auth_manager.get_access_token(request.args.get("code"))
                o2mHandler.spotifyHandler.seed_instance_cache_if_absent()
                o2mHandler.spotifyHandler.reload_sp()
                return redirect('/api/spotipy_init')

            if not auth_manager.validate_token(cache_handler.get_cached_token()):
                # Step 1. Display sign in link when no token
                auth_url = auth_manager.get_authorize_url()
                return f'<h2><a href="{auth_url}">Sign in</a></h2>'

            # Step 3. Signed in, display data
            o2mHandler.spotifyHandler.seed_instance_cache_if_absent()
            o2mHandler.spotifyHandler.reload_sp()
            # Fan-out #1 (edit-auth): the same Spotify login also unlocks the mood-edit
            # space — set the signed cookie if the identity is in the allowlist (replaces
            # the broken Iris proxy). Secure when served over HTTPS (behind Caddy).
            from flask import make_response
            me = o2mHandler.spotifyHandler.sp.me()
            uid = (me.get("id") or "").strip()
            resp = make_response(
                f'<h2>Hi {me.get("display_name") or uid}, '
                f'<small><a href="/api/spotipy_out">[sign out]</a></small></h2>'
            )
            if uid.lower() in _edit_allowlist():
                resp.set_cookie(
                    _EDIT_COOKIE, _edit_serializer.dumps({"id": uid}),
                    max_age=_EDIT_MAX_AGE, httponly=True, samesite="Lax",
                    secure=(request.headers.get("X-Forwarded-Proto", "") == "https"),
                )
            return resp

        @api.route('/api/spotipy_out')
        def api_spotipy_out():
            from flask import make_response
            # De-auth = drop the per-user OVERLAY only. The Web API then falls back to the
            # instance baseline (fixed house account); streaming is untouched (pinned to it).
            # Also clear the edit cookie.
            if os.path.exists(o2mHandler.spotifyHandler.cache_path):
                os.remove(o2mHandler.spotifyHandler.cache_path)
                print("Per-user Spotify overlay removed — falling back to instance baseline.")
            o2mHandler.spotifyHandler.reload_sp()
            resp = make_response(redirect('/api/spotipy_init'))
            resp.delete_cookie(_EDIT_COOKIE)
            return resp

        # Fan-out #2 (streaming): fresh USER access-token for mopidy-spotify/librespot.
        # Called internally by the patched mopidy backend (on_source_setup) to mint/refresh
        # the durable librespot credentials blob. Returns the cached token, refreshed if expired.
        @api.route('/api/spotify_stream_token')
        def api_spotify_stream_token():
            try:
                sh = o2mHandler.spotifyHandler
                # Streaming is pinned to the fixed INSTANCE baseline (never the per-user
                # overlay), so playback keeps running on the house Premium account even when a
                # free-tier user is signed in only for Web-API/edit. Fall back to the overlay
                # cache only if the baseline file does not exist yet.
                path = sh.instance_cache_path if os.path.exists(sh.instance_cache_path) else sh.cache_path
                ch = spotipy.cache_handler.CacheFileHandler(cache_path=path)
                am = spotipy.oauth2.SpotifyOAuth(scope=sh.scope, cache_handler=ch)
                tok = ch.get_cached_token()
                if not tok:
                    return ("", 404)
                if am.is_token_expired(tok) and tok.get("refresh_token"):
                    tok = am.refresh_access_token(tok["refresh_token"])
                return (tok.get("access_token", ""), 200)
            except Exception as e:
                print(f"spotify_stream_token error: {e}")
                return ("", 503)
    
    #MOPIDY LISTENERS
        # Fonction called when track started
        @mopidy.on_event("track_playback_started")
        #@mopidy.audio.AudioListener.state_changed("PAUSED","PLAYING",None)
        def track_started_event(event):
            track = event.tl_track.track
            print (event)

            #Quick and dirty volume Management
            # Podcast : seek previous position
            if ("podcast+" in track.uri and ("#" in track.uri or "episode" in track.uri) ) or ("youtube:video:" in track.uri) or ("yt:" in track.uri):
                stat_uri = o2mHandler.dbHandler.get_stat_by_uri(track.uri)
                if (stat_uri):
                    #if (o2mHandler.dbHandler.get_pos_stat(track.uri) > 0) and (o2mHandler.dbHandler.get_pos_stat(track.uri)/track.length < 0.9) :
                    if (stat_uri.read_position > 10) and (stat_uri.read_position <= track.length):
                        o2mHandler.mopidyHandler.playback.seek(max(stat_uri.read_position - 10, 0))
                    if stat_uri.read_position > track.length :
                        o2mHandler.mopidyHandler.playback.seek(track.length - 10)
                    #skip advertising 
                    #elif "radiofrance-podcast.net" in track.uri: o2mHandler.mopidyHandler.playback.seek(15000)
                #elif "radiofrance-podcast.net" in track.uri:  o2mHandler.mopidyHandler.playback.seek(15000)
            if "radiofrance-podcast.net" in track.uri or "podcasts.nova.fr" in track.uri or "9851446c-d9b9-47a2-99a9-26d0a4968cc3" in track.uri :
                volume = o2mHandler.mopidyHandler.mixer.get_volume()*1.5
                if volume > 100: volume = 100
                o2mHandler.mopidyHandler.mixer.set_volume(int(volume))

        # Fonction called when tracked skipped OR completly finished
        #@mopidy.audio.AudioListener.state_changed("PLAYING","PAUSED",None)
        #@mopidy.audio.AudioListener.reached_end_of_stream()   
        def track_ended_event(event):
            #Datas
            track = event.tl_track.track
            # Resolve local file URI back to its Spotify URI for all stat/reco logic
            effective_uri = o2mHandler.get_spotify_uri(track.uri)
            discover_level = o2mHandler.calculate_discover_level(effective_uri)
            
            #No action if discover_level set to 0
            if discover_level > 0:
            
                # Direct lookup from _track_info — no index arithmetic, no parallel lists
                tlid = event.tl_track.tlid
                info = o2mHandler._track_info.get(tlid, {})
                option_type = info.get('option_type', 'new_mopidy')
                library_link = info.get('library_link', '')
                data = ''
                position = event.time_position

                active_box = o2mHandler.get_active_box_by_tlid(tlid)
                if not active_box:
                    active_box = o2mHandler.get_active_box_by_uri(track.uri)

                if active_box:
                    if active_box.data != '': data = active_box.data
                    # library_link fallback when not stored in _track_info (e.g. Iris-added track)
                    if not library_link:
                        if active_box.data == 'spotify:favorites':
                            library_link = 'o2m:favorites'
                        else:
                            data_lines = [x for x in active_box.data.split("\n")
                                          if not x.startswith('#') and not x.startswith('\r')]
                            for content in data_lines:
                                if 'spotify:playlist' in content:
                                    library_link = content
                                    break
                print(f"Library Link : {library_link}")

                if event.event == "track_playback_ended":
                    #Quick and dirty volume Management
                    if "radiofrance-podcast.net" in track.uri or "podcasts.nova.fr" in track.uri or "9851446c-d9b9-47a2-99a9-26d0a4968cc3" in track.uri :
                        print (f"Set Volume : {o2mHandler.current_volume}")
                        #o2mHandler.mopidyHandler.mixer.set_volume(o2mHandler.current_volume)
                        o2mHandler.mopidyHandler.mixer.set_volume(int(o2mHandler.mopidyHandler.mixer.get_volume()*0.67))

                    # Recommandations added at each ended and nottrack (only spotify:track now)
                    if "track" in effective_uri and position / track.length > 0.9:
                        print (f"Ending with option_type {option_type}")
                        if option_type != 'new':
                            #int(round(discover_level * 0.25))
                            #Pb with this library_link calc
                            library_link="o2m:reco_after_track"
                            try: o2mHandler.add_reco_after_track_read(effective_uri,library_link,data)
                            except Exception as val_e:
                                print(f"Erreur : {val_e}")
                                o2mHandler.spotifyHandler.init_token_sp()
                                o2mHandler.add_reco_after_track_read(effective_uri,library_link,data)
                        if option_type != 'hidden' and option_type != 'trash' :
                            print ("Adding raw stats")
                            o2mHandler.update_stat_raw(effective_uri)

                # Podcast
                '''if ("podcast+" in track.uri and ("#" in track.uri or "episode" in track.uri) ) or ("youtube:video:" in track.uri) or ("yt:" in track.uri):

                    #URI harmonization if max_results used : pb to update track.uri
                    if "?max_results=" in track.uri: 
                        uri1 = track.uri.split("?max_results=")
                        if "#" in uri1[1]: 
                            uri2 = uri1[1].split("#")
                            track_uri = str(uri1[0]) + "#" + str(uri2[1])
                        else : track_uri = str(uri1[0])
                    if o2mHandler.dbHandler.stat_exists(track.uri):
                        stat = o2mHandler.dbHandler.get_stat_by_uri(track.uri)
                        #If last stat read position is greater than actual: do not update
                        #if position < stat.read_position: position = stat.read_position
                        print(f"Event : {position} / stat : {stat.read_position}")
                    # If directly in box data (not m3u) : behaviour to ckeck
                    if (position / track.length > 0.7): 
                        active_box = o2mHandler.dbHandler.get_box_by_data(track.uri)  # To check !!! Récupère le active_box correspondant à la chaine
                        if active_box != None:
                            if active_box.box_type == "podcasts:channel":
                                active_box.option_last_unread = (track.track_no)  # actualise le numéro du dernier podcast écouté
                                active_box.update()
                                active_box.save()
                '''
                                
                print(f"\n{event.event} song : {track.name} with option_type {option_type} and library_link {library_link}")

                # Update stats 
                if (event.event == "track_playback_ended") or ("podcast+" in track.uri and ("#" or "episode") in track.uri) or ("youtube:video:" in track.uri) or ("yt:" in track.uri):
                    
                    try:
                        o2mHandler.update_stat_track(track,position,option_type,library_link,uri_override=effective_uri)
                    except Exception as val_e:
                        print(f"Erreur : {val_e}")
                        o2mHandler.spotifyHandler.init_token_sp() #pb of expired token to resolve
                        o2mHandler.update_stat_track(track,position,option_type,library_link,uri_override=effective_uri)

                if "tunein" in effective_uri:
                    if option_type != 'hidden': o2mHandler.update_stat_raw(effective_uri)

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

        @mopidy.on_event("track_playback_ended")
        def event_track_playback_ended(event):
            track_ended_event(event)

        @mopidy.on_event("track_playback_paused")
        def event_track_playback_paused(event):
            track_ended_event(event)

    # Fonction called when status change ie : stop but impossible to catch track before
    """@mopidy.on_event('playback_state_changed')
    def event_print(event):
        #possibility of track catching ?
        if event.new_state == 'stopped': print (f"Stop : {o2mHandler.mopidyHandler.playback.get_current_track()}")"""


#MAIN LOOP
    # Infinite loop for API listener
    try:
        api.run(host='0.0.0.0', port=6681)
    except Exception as ex:
        print(f"Erreur : {ex}")
        o2mHandler.spotifyHandler.init_token_sp()
        api.run(host='0.0.0.0', port=6681)

# Code pour créer manuellement des boxs en bdd
# if __name__ == "__main__":
#     mydb = DatabaseHandler()
#     box = mydb.get_box_by_uid('AB34A324')
#     box.description = 'Spotify Artist : Creedence'
#     box.save()
#     # box = Box.create('AB34A324')
#     #     uid='AB34A324',
#     #     box_type = 'spotify:artist',
#     #     data = 'spotify:artist:3IYUhFvPQItj6xySrBmZkd',
#     #     descrition = 'Spotify Artist : Creedence')
#     print(box)