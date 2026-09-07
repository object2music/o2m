# Identité de streaming Spotify (keymaster) — installation et appairage

Depuis le **10/08/2026**, `login5` refuse tout access-token frappé par un `client_id` tiers :
la lecture Spotify casse (`INVALID_CREDENTIALS`, puis côté gst `track is not available`).
Upstream : [mopidy-spotify#437](https://github.com/mopidy/mopidy-spotify/issues/437),
[go-librespot#364](https://github.com/devgianlu/go-librespot/issues/364) — la réponse annoncée
(« two login paths ») n'est pas livrée.

O2M contourne en donnant à librespot un token frappé par le **client desktop Spotify
(« keymaster »)**, obtenu en PKCE, et servi par `/api/spotify_stream_token`. La Web API garde le
`client_id` o2m : un token desktop se fait 429 immédiatement sur `api.spotify.com`.
Contexte détaillé : [SPOTIFY_OAUTH_INVESTIGATION.md](SPOTIFY_OAUTH_INVESTIGATION.md).

Deux faits mesurés qui expliquent la procédure ci-dessous :

- même piste, même binaire, cache vide : token `client_id` tiers → `track is not available`,
  token keymaster → `PLAYING` ;
- un blob `credentials-cache/credentials.json` antérieur à la panne **casse la lecture même avec
  un bon token** (librespot rejoue des stored credentials que login5 refuse) → il doit être purgé.
  Le backend patché s'en charge au changement d'identité.

---

## Nouvelle instance : l'ordre des opérations

Les étapes 1 à 4 relèvent de l'exploitant (hors application), les suivantes sont dans l'UI.

1. **`.env`** depuis `env.example` : ports décalés de 10 par instance, `O2M_PUBLIC_URL=https://o2mN.o2m.site`
   (qui alimente `SPOTIPY_REDIRECT_URI`), base de données, `SPOTIFY_USERNAME` (allowlist d'édition
   par défaut), `LASTFM_API_KEY` si l'enrichissement est voulu.
2. **Redirect URI** de l'instance enregistrée dans le dashboard Spotify de l'app. Sans ça, la
   connexion tourne en rond — le wizard le détecte et l'affiche, mais ne peut pas le corriger.
3. **Vhost Caddy** et fichier compose de l'instance.
4. **Démarrage** : les migrations de schéma s'appliquent seules.
5. **Connexion Spotify** (wizard étape 1, ou `/api/spotipy_init`) → `.cache_spotipy`, amorçage du
   baseline `.cache_spotify_instance`, et cookie d'édition si le compte est dans l'allowlist.
6. **Appairage de la lecture** (wizard étape 2, ou `/api/spotify_stream_auth`) → voir la procédure
   d'appairage plus bas. **Sans cette étape, aucune piste Spotify ne se lit.**
7. Sync de la bibliothèque, boxes de démarrage, première box (wizard étapes 3 à 5).

### Quel compte Spotify ?

**Compte standard partagé entre instances.** Chaque instance doit être appairée **séparément** :
ne jamais copier `.cache_spotify_stream` d'une machine à l'autre, Spotify fait tourner le
`refresh_token` à chaque rafraîchissement et la copie serait invalidée au premier tour. Limite à
connaître : un compte Premium n'autorise **qu'un seul flux à la fois** — deux instances qui lisent
simultanément se disputent la session et se coupent mutuellement.

**Compte Premium dédié à l'instance.** C'est le bon choix dès que deux instances doivent lire en
même temps. La connexion Web API (étape 5) et l'appairage (étape 6) se font alors avec ce compte,
qui hébergera aussi les playlists « O2M Incoming / Trash » créées par le wizard. Pense à ajouter
ton identifiant Spotify personnel à `O2M_EDIT_SPOTIFY_IDS` pour garder la main sur l'édition, sinon
seul le compte dédié peut administrer l'instance.

Dans les deux cas, l'identité de lecture reste strictement séparée de l'identité Web API : elles
n'ont ni le même `client_id`, ni le même cycle de vie, et une seule des deux peut lire l'audio.

---

## Installation sans Docker (Raspberry Pi)

Sous Docker, `mopidy/mopidy_spotify_backend.py` est bind-monté par-dessus le `backend.py` du
paquet installé. Sans Docker, il faut faire ce montage à la main — c'est la seule vraie
différence.

### 0. Prérequis à vérifier

```sh
mopidy deps | grep -i -A1 "Mopidy-Spotify"   # doit être 5.0.0aX
gst-inspect-1.0 spotifyaudiosrc | grep -E "Version|access-token"
```

Il faut **mopidy-spotify 5.x + gst-plugin-spotify** (l'élément `spotifyaudiosrc` et sa propriété
`access-token`). Sans ça, le patch ne s'applique pas : c'est une autre stack de lecture.

### 1. Mettre le dépôt à jour

```sh
cd /chemin/vers/o2m && git pull
```

### 2. Installer le backend patché

Repérer le paquet installé. `mopidy deps` donne déjà le chemin (`Mopidy-Spotify: 5.0.0a3 from
/usr/…/dist-packages`), ce qui est le plus fiable en venv/pipx ; sinon, avec **le même
interpréteur que mopidy** :

```sh
PKG=$(python3 -c "import mopidy_spotify, os; print(os.path.dirname(mopidy_spotify.__file__))")
echo "$PKG"
sudo cp -n "$PKG/backend.py" "$PKG/backend.py.orig"      # sauvegarde de l'original
sudo ln -sfn /chemin/vers/o2m/mopidy/mopidy_spotify_backend.py "$PKG/backend.py"
```

Le **lien symbolique** reproduit le bind-mount : les `git pull` suivants sont pris en compte au
prochain restart de mopidy, sans rien réinstaller. Une simple `cp` marche aussi, mais il faut
alors la refaire après chaque pull.

⚠️ Un `pip install --upgrade mopidy-spotify` remplacera le lien : refaire cette étape après toute
mise à jour du paquet, et vérifier que la version d'upstream n'a pas rendu le patch caduc.

### 3. URL de l'API o2m

Le backend essaie `http://o2m:6681` (nom de service Docker) puis `http://127.0.0.1:6681`, et
retient celui qui répond : sur le Pi, **rien à configurer** si o2m écoute bien sur le port 6681 de
la machine (`api.run(host='0.0.0.0', port=6681)` dans `main.py`).

Si o2m tourne sur un autre hôte ou un autre port, pinner l'URL par variable d'environnement :

```sh
sudo systemctl edit mopidy      # crée un override
```
```ini
[Service]
Environment=O2M_API_URL=http://127.0.0.1:6681
```

### 4. Redémarrer

```sh
sudo systemctl restart o2m      # ou la façon dont o2m est lancé ici
sudo systemctl restart mopidy
```

### 5. Appairer l'identité de streaming

L'appairage est **par instance** : chaque install (Pi, chaque instance Docker) fait le sien.
Ne pas copier `.cache_spotify_stream` d'une machine à l'autre — Spotify renvoie un nouveau
`refresh_token` à chaque refresh, donc la copie partagée serait invalidée dès le premier refresh.

1. Se connecter d'abord à Spotify sur l'instance : `http://<pi>:6681/api/spotipy_init`, avec un
   compte présent dans l'allowlist d'édition (`O2M_EDIT_SPOTIFY_IDS` / `SPOTIFY_USERNAME`).
   C'est ce qui pose le cookie d'admin qui protège la page suivante.
2. Ouvrir `http://<pi>:6681/api/spotify_stream_auth`.
3. Cliquer le lien de connexion Spotify, **avec le compte Premium maison** (celui qui lit).
4. Le navigateur va échouer à joindre `127.0.0.1:8898` : **c'est normal**, rien n'écoute là.
5. Copier l'URL complète de la barre d'adresse (celle qui contient `code=…`) et la coller dans le
   formulaire, puis valider.

La page doit alors afficher « Paired — identity `km-…` ».

### 6. Vérifier

```sh
curl -s localhost:6681/api/spotify_stream_identity ; echo     # doit renvoyer km-...
```

Lancer une piste Spotify, puis :

```sh
journalctl -u mopidy -n 50 | grep -iE "streaming identity|login5|INVALID_CREDENTIALS"
```

Attendu : **une seule** ligne `Spotify streaming identity changed — cleared cached credentials.`
(la purge du vieux blob, au premier passage), et **aucune** erreur `login5` / `INVALID_CREDENTIALS`.
La purge ne doit pas réapparaître aux lectures suivantes.

Fichiers créés (chemins bare-metal usuels ; `mopidy` doit pouvoir écrire dans son data dir) :

| Fichier | Rôle |
|---|---|
| `<dir o2m>/.cache_spotify_stream` | token + refresh keymaster + `pair_id` (secret, non versionné) |
| `/var/lib/mopidy/spotify/credentials-cache/credentials.json` | blob librespot, regénéré après purge |
| `/var/lib/mopidy/spotify/stream-identity` | identité vue au dernier passage, sert de témoin de purge |

Si mopidy ne tourne pas en service système, le data dir est `~/.local/share/mopidy/spotify`.

---

## Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `track is not available`, lecture qui skippe | identité non appairée → repli sur l'ancien token | refaire l'étape 5 ; vérifier `/api/spotify_stream_identity` |
| `/api/spotify_stream_auth` renvoie 401 | pas de cookie d'édition | passer par `/api/spotipy_init` avec un compte de l'allowlist |
| Identité appairée mais lecture toujours KO | blob non purgé (backend non patché) | vérifier que `backend.py` du paquet pointe bien sur le fichier du dépôt |
| `State mismatch` à l'appairage | URL collée issue d'une session précédente | recharger la page pour un nouveau lien, refaire la danse |
| La purge se répète à chaque lecture | data dir non inscriptible par mopidy | vérifier les droits sur `<data_dir>/stream-identity` |
| Lecture OK puis coupures | plusieurs instances lisent sur le même compte Spotify | un seul flux actif par compte Premium |

## À retirer un jour

Ce contournement disparaîtra quand mopidy-spotify livrera son propre chemin de lecture
(PR [#436](https://github.com/mopidy/mopidy-spotify/pull/436) en cours). À ce moment-là : rendre
`backend.py.orig`, retirer le lien symbolique, et supprimer l'appairage via le bouton *Unpair*
de `/api/spotify_stream_auth`.
