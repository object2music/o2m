# Spotify OAuth dynamique — investigation (branche `spotify-oauth`)

But : remplacer le **blob `credentials.json` copié à la main** (mopidy-spotify) par une
**génération dynamique via une fenêtre OAuth** (HTTPS dispo : `https://o2m.site`), stockée
localement par instance (volume `./data/spotify`).

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

## Reco de départ
1. **Spike #1 (décisif)** : valider la **Piste A** — fournir un access-token **user** au gst-plugin et voir
   si `credentials.json` (auth_type 1) est minté dans `cache-credentials`. Si oui, c'est la voie la plus
   intégrée (réutilise librespot déjà présent).
2. Construire l'**OAuth Authorization Code** côté o2m (endpoints `/api/spotify_login` → `/api/spotify_callback`,
   app Spotify perso, scopes streaming) — utile aussi pour le **point 3** (Web API/édition) et le `.cache_spotipy`.
3. Stockage : token user (+ refresh) par instance ; `credentials.json` minté → volume `./data/spotify` (déjà en place sur o2m_1).

## État / contexte
- Branche `spotify-oauth` (worktree `/home/o2m/oauth-spotify`, base `stats_v2`). N'impacte pas o2m_1 qui tourne.
- Correctif d'urgence déjà appliqué hors-branche : blob copié + volume `./data/spotify` (o2m_1 durable). Voir mémoire `project_spotify_multi_instance`.
