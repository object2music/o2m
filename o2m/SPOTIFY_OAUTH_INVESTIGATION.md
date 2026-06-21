# Spotify OAuth dynamique — investigation (branche `spotify-oauth`)

## But final : UNE auth OAuth unifiée et robuste pour les 3 usages

L'objectif n'est pas juste de réparer mopidy-spotify, mais d'**unifier et fiabiliser les trois
auth Spotify** derrière **un seul login OAuth** (Authorization Code, app Spotify perso, redirect
`https://o2m.site/api/spotify_callback`), avec l'**union des scopes** :

| Usage | Aujourd'hui | Ce que l'OAuth unifié fournit |
|---|---|---|
| **mopidy-spotify** (streaming) | blob `credentials.json` copié à la main, fragile | token user `streaming` → mint du blob librespot (persisté `./data/spotify`) |
| **Spotipy** (Web API o2m : playlists/library/reco) | `.cache_spotipy` (token séparé) | le même token user (+ refresh) → `.cache_spotipy` |
| **Édition via l'UI mood** (identité) | proxy Iris public **cassé** | `/v1/me` du même token → cookie signé `require_edit_auth` |

Scopes à demander (union) : `streaming`, `user-read-private`, `user-read-email`,
`user-library-read/modify`, `playlist-read-private/collaborative`, `playlist-modify-public/private`,
`user-top-read`, `user-read-recently-played`, `user-follow-read/modify`.

Un seul clic « Connecter Spotify » dans l'UI mood → autorisation → o2m : (1) stocke token+refresh
(Spotipy), (2) mint le blob librespot (mopidy), (3) pose le cookie d'édition. Token rafraîchi
automatiquement (refresh_token). Par instance (chacune sa redirect/sous-domaine ou state).

---

But technique sous-jacent : remplacer le **blob `credentials.json` copié à la main** (mopidy-spotify)
par une **génération dynamique via la fenêtre OAuth** ci-dessus, stockée localement par instance
(volume `./data/spotify`).

## Ce qu'on a (mécanisme réel, mopidy-spotify 5.0.0a3 + gst-plugin-spotify/librespot)

Deux auth Spotify DISTINCTES :
1. **Web API métadonnées** (`mopidy_spotify/web.py`, `OAuthClient`) : `grant_type=client_credentials`
   avec `(client_id, client_secret)` → token **app** (sans user). Sert aux lookups/metadata.
2. **Streaming** (`backend.py:on_source_setup` → gst `libgstspotify.so` = librespot) :
   - `set_property("cache-credentials", <data_dir>/credentials-cache)`
   - `set_property("access-token", web_client.token())`  ← **token client_credentials (app)**
   - librespot lit/écrit `credentials-cache/credentials.json` = **stored credentials USER**
     (`{username, auth_type:1, auth_data}`).

Constats vérifiés dans le conteneur :
- **Pas de binaire `librespot`** (seulement `libgstspotify.so`).
- `get_config_schema()` : `client_id`, `client_secret`, `bitrate`, `allow_cache`… **aucune** option
  token/refresh/oauth. `username`/`password` = `Deprecated()` depuis 5.0.
- Donc **mopidy-spotify NE GÉNÈRE PAS** le `credentials.json` user : il ne fait que client_credentials,
  et s'appuie sur un blob user **fourni de l'extérieur**. Le streaming user marche tant que ce blob
  (auth_type 1) est présent et valide dans le cache ; sinon → `Failed to load Spotify user profile`.

→ C'est exactement le symptôme d'o2m_1 : blob périmé/absent ⇒ pas de musique (podcasts via mopidy-podcast OK).

## Cohabitation avec l'existant (.env + flow déjà présent)

Le `.env` contient **deux apps Spotify** + un compte ; ce sont des **credentials d'APP**, pas des
sessions user. La fenêtre du front produit, elle, un **token USER** (Authorization Code) — chose
**complémentaire**, pas concurrente : l'OAuth user **utilise** le client_id/secret d'une app pour
produire le token. On n'enlève rien, on **ajoute la couche user** par-dessus.

| Clé .env (o2m_1) | Rôle | Devenir dans l'unification |
|---|---|---|
| `SPOTIFY_CLIENT_ID` = `f650d733-…` (UUID) + `SPOTIFY_CLIENT_SECRET` | app **mopidy-spotify** (`mopidy.conf [spotify] client_id`) : client_credentials metadata + identité librespot | reste pour la metadata ; le **streaming** prend le blob minté via l'OAuth user |
| `SPOTIPY_CLIENT_ID` = `2c8b31fd…` (32 hex) + `SPOTIPY_CLIENT_SECRET` | app **Web API o2m (Spotipy)** | **= l'app de l'OAuth unifié** (on lui ajoute le scope `streaming` + redirect HTTPS) |
| `SPOTIPY_REDIRECT_URI` = `http://109.7.238.172:6691/api/spotipy_init` | redirect du flow Spotipy **existant** | → **`https://<sous-domaine>/api/spotipy_init`** (HTTPS, par instance) |
| `SPOTIFY_USERNAME` / `SPOTIFY_PASSWORD` | legacy (déprécié mopidy-spotify 5.x) | inutilisé pour l'auth |

**Le scaffolding existe déjà** : `main.py:/api/spotipy_init` fait le flow Authorization Code complet
(`SpotifyOAuth.get_authorize_url()` → callback `get_access_token(code)` → `.cache_spotipy` via
`CacheFileHandler`), avec `spotifyhandler.scope` (Web API). **Il manque juste** : redirect **HTTPS** +
scope **`streaming`** + **fan-out** du token vers les 3 consommateurs.

**Unifier = upgrader CE flow** (pas en créer un nouveau) :
1. `spotifyhandler.scope` += `streaming user-read-private user-read-email`.
2. `SPOTIPY_REDIRECT_URI` → `https://<sous-domaine instance>/api/spotipy_init` (enregistrer chaque
   sous-domaine dans le dashboard de l'app SPOTIPY ; Spotify accepte plusieurs redirect URIs).
3. À la fin de `/api/spotipy_init` (token obtenu) → **fan-out** :
   - **Spotipy** : déjà (`.cache_spotipy`). ✓
   - **Édition mood** : `/v1/me` → cookie signé `require_edit_auth` (remplace le proxy Iris cassé).
   - **mopidy-spotify** : mint du `credentials.json` librespot depuis ce token (spike #1).
4. Par instance : chacune garde son `.cache_spotipy`, son blob librespot (volume `./data/spotify`),
   son sous-domaine de redirect.

⚠️ À valider au spike : un token issu de l'app **SPOTIPY** (avec `streaming`) suffit-il à librespot
même si `mopidy.conf client_id` = app **mopidy** (f650d733) ? Sinon → pointer `mopidy.conf client_id`
sur l'app SPOTIPY (full consolidation 1 app).

## Le vrai problème à résoudre

Produire dynamiquement un **`credentials.json` librespot (auth_type 1)** à partir d'un **login user OAuth**,
par instance, et le déposer dans `./data/spotify/credentials-cache/` (persisté).

La partie « fenêtre OAuth » (Authorization Code) est simple maintenant qu'on a HTTPS. La partie **dure** =
convertir le **token user OAuth → stored-credentials librespot** (format `auth_data`), car c'est
spécifique à librespot.

## Pistes d'implémentation (à départager par un spike)

### Piste A — patch `on_source_setup` : injecter un token USER dans le gst-plugin (= librespot)
Le plugin gst EST librespot et écrit déjà dans `cache-credentials`. Hypothèse : si on lui passe un
**access-token USER** (au lieu du token client_credentials), librespot s'authentifie comme l'utilisateur
et **stocke** `credentials.json` (auth_type 1) tout seul.
- o2m fait l'OAuth (Authorization Code, redirect `https://o2m.site/api/spotify_callback`) → user access_token (+ refresh).
- Patch `mopidy_spotify/backend.py:on_source_setup` : `access-token = <token user fourni par o2m>`
  (lu via un fichier partagé / petit endpoint), fallback sur `web_client.token()`.
- 1ère lecture → librespot mint `credentials.json` → persiste sur volume → runs suivants OK.
- ⚠️ Patch = modif d'un fichier **dans l'image mopidy** (même souci que `o2m.js` : pas de volume sur le
  package) → déploiement par `docker cp` ou mount du fichier patché. **À VALIDER** : librespot mint-il
  vraiment le blob à partir d'un access-token user via la property gst ? (spike #1, le risque principal).

### Piste B — librespot CLI `--oauth` (one-shot par instance)
Installer le binaire `librespot` et lancer son flow OAuth (`--oauth`) qui produit `credentials.json`.
- Propre/isolé, mais le flow librespot utilise un **redirect loopback `127.0.0.1:PORT`** (dans le conteneur)
  → à proxifier/relayer pour une vraie fenêtre distante (Caddy ou capture du code). Ajoute une dépendance binaire.

### Piste C — helper Python token→stored-credentials
Utiliser une lib (librespot-python/-auth communautaire) pour échanger un token user contre des stored
credentials et écrire `credentials.json`. À évaluer (maintenance/compat).

## ✅ SPIKE #1 — RÉSULTAT : Piste A CONFIRMÉE (o2m_6, 21/06/2026)

Protocole : OAuth unifié sur o2m_6 → token user (scope `streaming`) dans `.cache_spotipy` ;
on vide `credentials-cache/` ; on patche `backend.py:on_source_setup` pour passer **le token user**
(au lieu de `web_client.token()` = client_credentials) ; lecture d'un `spotify:track`.

Résultat : **lecture `playing` + `credentials.json` minté** (`auth_type:1`, `username:1181464119`).
→ **Un token user `streaming` fourni au gst-plugin (librespot) authentifie, streame ET génère le
blob réutilisable durable.** C'est la voie retenue.

Les 3 auth validées d'un seul login : Spotipy (`.cache_spotipy`) ✓, cookie d'édition (fan-out) ✓,
streaming+mint librespot ✓ (« Refreshed 43 Spotify playlists » côté Web API en bonus).

## Intégration propre (à faire — le spike utilisait un hack /tmp + patch en conteneur)

1. **Feed du token user à librespot** : `backend.py:on_source_setup` doit utiliser le token user d'o2m
   (au lieu de client_credentials) **pour le mint initial**. Le blob étant réutilisable, le token n'est
   nécessaire qu'au 1er mint (ou re-mint si invalidé). Source du token : `.cache_spotipy` partagé
   (volume) ou poussé par o2m après l'OAuth.
2. **Déploiement du patch** : `mopidy_spotify/backend.py` est dans l'**image** (comme o2m.js) → le
   déployer par **mount de fichier** (volume sur ce seul fichier, survit aux recreate) plutôt que par
   `docker cp` éphémère. [[project_deploy_o2mjs]]
3. **Persistance du blob** : monter `./data/spotify` (déjà prouvé sur o2m_1) → le blob minté survit aux recreate.
4. **UI** : bouton « Connecter Spotify » dans l'UI mood → `/api/spotipy_init` (déjà fan-out Spotipy+édition).
5. **Refresh** : `.cache_spotipy` se rafraîchit (refresh_token) ; prévoir un re-mint si Spotify invalide le blob.

## Reco de départ
1. **Spike #1 (décisif)** : valider la **Piste A** — fournir un access-token **user** au gst-plugin et voir
   si `credentials.json` (auth_type 1) est minté dans `cache-credentials`. Si oui, c'est la voie la plus
   intégrée (réutilise librespot déjà présent).
2. Construire l'**OAuth Authorization Code** côté o2m (endpoints `/api/spotify_login` → `/api/spotify_callback`,
   app Spotify perso, scopes streaming) — utile aussi pour le **point 3** (Web API/édition) et le `.cache_spotipy`.
3. Stockage : token user (+ refresh) par instance ; `credentials.json` minté → volume `./data/spotify` (déjà en place sur o2m_1).

## Modèle de comptes retenu (séparation par plan)

| Plan | Compte | Fichier |
|---|---|---|
| **Streaming** (librespot/blob) | **compte d'instance fixe** (« maison »), épinglé | `.cache_spotify_instance` (baseline) → `/api/spotify_stream_token` |
| **Web API / contenu** (boxes, favoris, library, **écriture**) | overlay **perso** si auth manuelle, **sinon** baseline | `.cache_spotipy` (overlay) sinon baseline |
| **Édition** (cookie signé) | identité perso | cookie `require_edit_auth` |

- **Sans auth manuelle** : lecture + requêtes sur le compte d'instance fixe (la baseline est *seedée une fois* depuis le cache actif et **jamais écrasée** → un invité ne peut pas hijacker streaming/fallback).
- **Auth manuelle** : overlay Web API (le user injecte ses favoris + droits d'écriture) + cookie d'édition. Le **streaming reste sur le compte fixe** → marche même si le user est en **gratuit**.
- **Désauth** (`/api/spotipy_out`) : supprime l'overlay → Web API retombe sur la baseline ; streaming intact ; cookie effacé.

### Suivi différé — prise en charge du streaming par le compte perso (Premium)
Idée : si l'utilisateur signé est **Premium**, faire streamer **son** compte (jusqu'à désauth) pour répartir la charge (Spotify = 1 flux actif/compte). **Différé** : non bloquant aujourd'hui (le même compte streame OK sur plusieurs instances en parallèle ; la limite réelle est inconnue). Implémentation prête à l'emploi quand utile : `/api/spotify_stream_token` renvoie `{access_token, account}` (overlay si Premium, sinon baseline) + `backend.py` efface le blob `credentials.json` quand le compte voulu change (re-mint). Aucun changement structurel requis (tout reste dans mopidy).

## État / contexte
- Branche `spotify-oauth` (worktree `/home/o2m/oauth-spotify`, base `stats_v2`). N'impacte pas o2m_1 qui tourne.
- Correctif d'urgence déjà appliqué hors-branche : blob copié + volume `./data/spotify` (o2m_1 durable). Voir mémoire `project_spotify_multi_instance`.
