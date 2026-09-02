# O2M (Object 2 Music) — État fonctionnel et d'usage

> Document de référence destiné à alimenter une analyse stratégique / d'opportunité
> marketing et un plan de communication. Il décrit **ce que le produit fait
> réellement aujourd'hui**, comment il est utilisé, son niveau de maturité et ses
> contraintes — sans embellissement.
> Dernière mise à jour : **2 septembre 2026** (chiffres mesurés sur la base de
> production ce jour-là).

---

## 1. Le pitch

**O2M transforme des objets physiques en télécommandes musicales intelligentes.**
On pose un objet (porteur d'une puce NFC) sur un lecteur : la musique, le podcast,
la radio ou le bulletin d'infos associé se lance — et le système construit et
entretient la playlist tout seul, en apprenant des écoutes du foyer.

C'est un « Spotify tangible et familial » : moins d'écrans, des rituels physiques
(l'objet du matin, la figurine des enfants, la carte jazz), et un moteur de
recommandation local qui mixe habitude et découverte selon un dosage réglable.

## 2. Le concept

- **Dé-écranisation** : l'interaction primaire est physique (objet posé/retiré),
  pas une app. Les enfants, invités, grands-parents lancent leur musique sans
  téléphone ni compte.
- **Objets = contenus + comportements** : chaque objet (« box ») porte un contenu
  (playlists, albums, artistes, feeds podcast, flux radio, mots-clés dynamiques)
  ET des réglages (niveau de découverte, tri, quantité, cibles d'ambiance).
- **Scénarios composables** : une box peut inclure d'autres box (« cascades ») —
  ex. l'objet « Auto morning » = infos fraîches + radio FIP + mix musical adaptatif.
- **Data-driven** : chaque écoute nourrit une base locale (position de lecture,
  complétion, skips, moment de la journée, mood) qui pilote les choix suivants.

## 3. L'expérience utilisateur (parcours réels)

1. **Le matin** : on pose l'objet « matin » → bulletin d'infos du jour, puis un mix
   musical calé sur l'heure et les habitudes. Le tout enchaîne sans interaction.
2. **Les enfants** : chaque enfant a son objet (figurine, carte) → sa playlist,
   sans écran, sans risque de dérive algorithmique.
3. **Sur mobile** : une interface web (PWA installable) en deux modes —
   - **Basic** (défaut téléphone) : 4 gros interrupteurs *Music / Podcast / Info /
     Radio* + un bouton central *ALL* + 2 potentiomètres (*niveau d'ouverture* et
     *mood* à 5 crans : intense · calm · normy · happy · energetic).
   - **Full** : matrice d'humeur 2D (énergie × ambiance), potards fins, genres,
     tracklist annotée, fiches détail album/artiste/box, édition.
4. **En voiture** : le téléphone lit le flux du foyer en 5G (indicateur de qualité
   réseau vert/orange/rouge intégré).
5. **Multiroom** : diffusion synchronisée dans plusieurs pièces (Snapcast) ; le
   téléphone peut lui-même devenir une enceinte.
6. **Podcasts intelligents** : reprise exactement où on s'était arrêté, priorisation
   des épisodes entamés récents, mélange automatique de plusieurs sources jusqu'à
   une quantité cible, saut de la pré-pub, et sélection d'épisodes **par sujet**
   (thèmes et mots-clés Radio France) plutôt que par abonnement.

## 4. Fonctionnalités (état réel)

### Objets / boxes
- Types : bibliothèque, favoris, nouveautés, à trier, podcast, info, cachée, corbeille.
- Contenus : playlists/albums/artistes Spotify, feeds RSS podcast, playlists
  YouTube, flux radio (Radio France…), fichiers locaux, mots-clés dynamiques
  (`auto:library`, `meta_podcasts`, `meta_infos`, `meta_radios`,
  `podcasts:unfinished`, `podcasts:channel`, `infos:library`, `now:library` et
  `herenow:library` pour les habitudes horaires, `newrecent:library`,
  `albums:spotify`… — une vingtaine de motifs, choisis dans l'éditeur).
- **Sujets Radio France** : `rf:show:<émission>` et surtout `rf:sujet:<mot-clé>`, qui
  remplit une box avec les épisodes correspondant à un thème (343 thèmes hiérarchisés,
  1 146 mots-clés) — un abonnement *par sujet* et non par émission.
- Cascades : une box peut inclure d'autres box → scénarios (réveil, famille).
- Édition en ligne (protégée par authentification Spotify OAuth) : nom, type,
  niveau de découverte, tri, quantité, cibles énergie/ambiance, contenu brut.

### Moteur musical
- **Mood** : chaque piste est enrichie (énergie 0-1, valence 0-1, catégorie
  calm/energetic/dark/happy) via Last.fm + édition manuelle ; la matrice ou le
  potard mood composent le mix en temps réel.
  **Changement d'échelle depuis la version précédente de ce document** : la
  couverture mood est passée de ~1 % à **53 % des pistes nommées** (40 941 pistes),
  et les genres d'artistes de 24 % à **97 %**. Le mood n'est plus une promesse
  d'architecture, c'est une donnée exploitable — ce qui change la crédibilité de
  tout le discours « moteur d'ambiance ».
- **Niveau de découverte (0-10)** : dose familier vs nouveau — de « mes classiques »
  à « surprends-moi », appliqué partout (mix auto, recommandations, sélections).
- **Recommandations continues** : en fin de morceau, le système peut insérer des
  titres proches (bibliothèque locale d'abord, Spotify/Last.fm sinon).
- **Anti-répétition, popularité composite, habitudes horaires** (quel contenu à
  quelle heure), sélection pondérée récence × hasard pour la rotation des sources.

### Données & bibliothèque
- Base locale complète, mesurée le 2 septembre 2026 : **76 815 pistes** (52 187
  nommées), 7 880 albums, 1 285 artistes, 694 genres, 53 playlists (10 406
  appartenances), **150 objets**, **102 542 écoutes** horodatées, liens N:N.
- **Catalogue de contenu parlé** : 3 744 chaînes (podcasts + émissions Radio France),
  9 219 épisodes, 1 489 sujets Radio France indexés — mis en cache localement pour
  qu'une box se remplisse sans appel réseau.
- Mise en cache progressive : un album consulté incomplet est automatiquement
  complété depuis Spotify et servi ensuite 100 % en local.
- Cache audio local optionnel (téléchargement des titres Spotify les plus écoutés
  → lecture sans réseau, substitution transparente).

### Diffusion & intégrations
- Serveur : Mopidy (standard open source) + couche O2M (API Flask).
- Sources : Spotify (compte foyer + surcouche perso OAuth pour l'édition),
  podcasts RSS, YouTube, radios en flux direct, fichiers locaux.
- Sortie : multiroom Snapcast, navigateur-enceinte, Bluetooth.
- Accès distant HTTPS (reverse proxy + auth), PWA installable, thèmes d'interface
  (dark/light/mono/overprint/invert).

## 5. Publics et usages observés

Le produit tourne **quotidiennement depuis plusieurs années dans un foyer réel**
(familial, multi-générations) :
- adultes : rituels matin/soir, mood mixes, podcasts culture/actu, radio ;
- enfants : objets personnels, playlists dédiées, autonomie sans écran ;
- contextes : cuisine/salon (multiroom), voiture (5G), mobilité (PWA).

Six instances serveur tournent en parallèle (production familiale sur Raspberry
Pi + serveur, dev, démos), preuve d'une reproductibilité déjà éprouvée.

## 6. Maturité — forces et limites (honnête)

**Forces**
- Produit réel, utilisé tous les jours, robuste (verrous, reconnexions auto,
  auto-guérison des connexions, tests bout-en-bout).
- Périmètre fonctionnel riche et différenciant (mood + tangible + podcasts
  intelligents + multiroom, le tout data-driven local).
- **Les données d'ambiance existent vraiment** (53 % des pistes nommées, 97 % des
  artistes) : le différenciateur « moteur d'ambiance » est démontrable, plus seulement
  architectural. C'était la principale faiblesse de la version précédente de ce document.
- **Algorithmes documentés et testés** : le score de popularité est un module pur
  (aucune dépendance hors `math`/`datetime`) couvert par 15 tests unitaires.
- Open source (GPL-3.0), déployable par un bricoleur averti (Docker, doc
  d'installation, ou natif Raspberry Pi).
- UI soignée (design system, mobile-first, deux niveaux de complexité).

**Limites / contraintes stratégiques majeures**
- **Dépendance Spotify** : compte Premium requis ; l'API se restreint
  (recommandations et playlists éditoriales déjà dépréciées) ; le partage d'un
  compte foyer sur plusieurs instances est une zone grise des CGU. Toute
  trajectoire de diffusion doit traiter ce risque (alternatives : bibliothèque
  locale, Tidal/Deezer via Mopidy, contenus libres).
- **Installation technicienne** : Docker/RPi/NFC — pas grand public en l'état ;
  pas d'app store, pas d'onboarding guidé.
- **Matériel** : lecteur NFC + serveur à assembler soi-même (pas de hardware
  produit) ; les coupures audio en mobilité (streaming temps-réel Snapcast)
  restent un point dur identifié.
- **Mono-foyer testé** : pas de multi-tenant, sécurité de niveau « maison »
  (basic-auth). Nuance mesurée : le schéma **porte déjà une colonne propriétaire**
  (`username` sur pistes, objets et écoutes), effectivement renseignée et contenant
  deux identités distinctes. Mais **aucune requête ne filtre dessus** : c'est de
  l'attribution, pas une frontière d'isolation. Le travail multi-tenant est donc
  côté lectures et authentification, pas côté modèle de données — c'est plutôt une
  bonne nouvelle pour le chiffrage.
- Documentation publique datée (slides, Notion) par rapport à l'état actuel.

## 7. Différenciation (paysage rapide)

| Face à | O2M se distingue par |
|---|---|
| Spotify/app streaming | tangible, sans écran, multiroom local, données chez soi, mood matrix, dosage découverte |
| Toniebox / Yoto (enfants) | contenus illimités (streaming + podcasts + radio), pas de figurines propriétaires, familial ET adulte |
| Sonos / multiroom | couche d'intelligence d'usage (habitudes, mood, podcasts repris), objets physiques, open source |
| Assistants vocaux | pas de cloud à l'écoute, rituels physiques, contrôle parental de fait |

## 8. Vecteurs de productisation (que peut-on détacher, et à quel coût ?)

Section ajoutée pour l'analyse d'offre. Elle évalue **ce qui est réellement
extractable** du code actuel, avec le couplage constaté — pas ce qui serait
souhaitable. Classée du plus immédiat au plus lourd.

### A. Le score de popularité — extractible tel quel ⭐ le plus mûr
`popularity.py` ne dépend que de `math` et `datetime`, ne touche ni base ni réseau,
et est couvert par 15 tests unitaires qui passent. Il transforme un historique
d'écoute (complétion, volume, skips, ancienneté, likes, appartenance playlist) en un
score [0,1], avec un lissage bayésien qui traite correctement le cas « jamais
terminé » — le piège classique des scores maison.

**Publiable en librairie (pip) quasi en l'état.** Utile à tout lecteur audio qui
possède un historique et veut classer sans réentraîner un modèle. Faible valeur
commerciale directe, forte valeur de **preuve technique et de visibilité**.

### B. Le moteur de sélection — extractible avec un travail identifié
Les échantillonneurs (`_mood_pick`, `_expand_pick`, `_cooldown_factor`,
`_sample_by_weight`) portent la vraie originalité : pondération gaussienne autour
d'une cible d'ambiance, température pilotée par le niveau de découverte
(popularité-dominant → aléatoire pur), anti-répétition progressive sur plusieurs
jours étirée pour les titres de forte rotation.

Couplage : ce sont des méthodes de `O2mToMopidy` qui lisent `self.dbHandler`. La
frontière est nette (elles ont besoin d'un dictionnaire `uri → caractéristiques`),
mais l'extraction est un vrai chantier, pas un copier-coller.

### C. Extension Mopidy — attention au contresens
O2M n'est **pas** une extension Mopidy : c'est un **client** de Mopidy via JSON-RPC.
Un « plugin Mopidy » serait donc une réécriture de l'intégration, pas un
repackaging. Ce qui intéresserait cette communauté (petite mais qualifiée) : le
mix auto ambiance/découverte et la gestion podcast (reprise, catalogue, sujets).
Bon vecteur de **notoriété technique**, marché quasi nul.

### D. Application mobile / plugin Spotify — **structurellement fermé**, pas seulement faible

Vérifié sur la politique développeur et la documentation officielles (septembre 2026),
plus une contrainte mesurée sur ce projet. Quatre verrous, chacun suffisant à lui seul.

**1. Le plafond de distribution est un cercle vicieux.** Une application reste en
*development mode* — **5 utilisateurs authentifiés maximum**, sur liste blanche. Pour
passer en *extended quota mode* (utilisateurs illimités), Spotify exige depuis mai 2025
une **entité juridique** (les particuliers sont explicitement exclus) et
**au moins 250 000 utilisateurs actifs mensuels**. Il faut donc déjà avoir 250 000
utilisateurs pour être autorisé à en avoir plus de 5. Aucune trajectoire indépendante ne
franchit cette porte.

**2. Le mécanisme central d'O2M est explicitement interdit.** La politique interdit de
« segue, mix, re-mix, or overlap any Spotify Content with any other audio content
(**including other Spotify Content**) ». Or O2M *est* une machine à composer une file
unique mêlant musique, podcast, info et radio. La formulation vise le mixage DJ
(fondus enchaînés) et l'on peut plaider qu'une lecture séquentielle n'est pas un
« segue » — mais c'est une plaidoirie, pas une autorisation.

**3. Le scénario emblématique est interdit sans accord écrit.** « Do not create ringtone
or alert tone functionality or **alarm functionality** […] unless you receive Spotify's
written approval. » L'objet du matin — le rituel le plus mis en avant dans ce document —
tombe dedans.

**4. Toute monétisation est fermée.** « Commercial uses are not permitted for SDAs » :
une application qui diffuse ne peut pas générer de revenu, ni par vente, ni par achat
intégré, ni par publicité. Le modèle payant est donc exclu **par construction**, pas par
prudence.

**Contrainte technique mesurée en plus du cadre légal** : depuis le 10 août 2026,
`login5` refuse les jetons émis par tout `client_id` tiers — un jeton de notre propre
application ne peut plus rien lire (mopidy-spotify#437). La lecture n'a été rétablie ici
qu'en passant par une identité *keymaster* (celle du client de bureau). Ça marche, mais
**c'est un contournement d'identité** : acceptable comme risque personnel sur un outil
privé, **disqualifiant** dans un produit distribué. À énoncer clairement dans toute
discussion d'offre.

**Ce qui reste néanmoins possible, et suffit à l'usage réel**
Le *development mode* autorise 5 utilisateurs : c'est précisément la taille d'un foyer.
O2M peut donc rester légitimement ce qu'il est — un outil privé, familial. Le mur
n'apparaît qu'au moment de la distribution.

**La bifurcation « interne / externe » et ce qu'elle apprend**
- **Interne** (l'app lit elle-même) : bloqué côté natif par le point technique ci-dessus.
  Le *Web Playback SDK* reste une voie officielle mais impose Premium, les DRM du
  navigateur (support WebView iOS médiocre) — et bute de toute façon sur les 5 utilisateurs.
- **Externe** (*App Remote*, on télécommande l'app Spotify officielle) : techniquement
  propre, et **cela réglerait le point dur de la mobilité** listé au §6 (plus de flux
  Snapcast en 5G, donc plus de coupures en voiture). Mais le téléphone devient un
  *lecteur séparé* — fin du mix unique du foyer — et **seul le contenu Spotify** peut
  passer par ce canal : ni podcast, ni radio, ni fichier local.

Contrainte technique et contrainte juridique pointent donc dans la **même** direction :
le contenu Spotify ne peut pas être mêlé au reste, et la voie *App Remote* ne saurait de
toute façon transporter que lui.

**Le design hybride qui en découle** (au sens « deux voies », pas « deux sources mêlées »)
Une application mobile qui lirait **nativement tout le non-Spotify** — podcasts, radio,
cache local : aucune licence à négocier, et surtout des **fichiers HTTP téléchargeables
donc écoutables hors ligne** — et **déléguerait la musique à l'app Spotify officielle**
via App Remote. Deux voies jamais mélangées : exactement ce que la politique impose, et
exactement ce qui résout la mobilité. Les épisodes sont déjà stockés sous une forme
directement compatible (`podcast+<flux>#<guid>` → fichier HTTP).

### E. Le sous-système contenu parlé — l'actif sous-estimé
La partie podcasts est plus différenciante que la partie musicale, et beaucoup moins
concurrencée :
- abonnement **par sujet** plutôt que par émission (thèmes/mots-clés Radio France) ;
- catalogue local des chaînes et épisodes → remplissage sans latence réseau ;
- reprise fine, priorisation des épisodes entamés, saut de pré-pub, partage de budget
  entre sources, dédoublonnage inter-sources par identifiant d'épisode.

Il contient aussi un **savoir non trivial et non documenté publiquement** sur l'API
Radio France (contraintes de pagination, filtres taxonomiques intersectés, champ RSS
cassé côté serveur, appariement des épisodes entre flux et API). C'est une barrière
à l'entrée réelle pour un concurrent.

### F. SaaS — le plus lourd, mais le modèle de données n'est pas le blocage
Le schéma porte déjà l'appartenance (`username` sur pistes, objets, écoutes) et deux
identités y coexistent. **Rien ne filtre dessus** : tout accès est global. Le chantier
est donc l'isolation des lectures, l'authentification et le cycle de vie des comptes
— plus une refonte de la dépendance Spotify (un compte par foyer ne se transpose pas
en SaaS). À cadrer comme un produit distinct, pas comme une évolution.

### Synthèse
| Vecteur | Effort | Valeur | Risque |
|---|---|---|---|
| A. Librairie popularité | très faible | visibilité | nul |
| B. Moteur de sélection | moyen | forte (cœur) | interne |
| C. Extension Mopidy | moyen | notoriété | marché nul |
| D. App mobile Spotify | — | **nulle : fermé** | plafond 5 users, mix et monétisation interdits |
| E. Brique contenu parlé | moyen | **forte, différenciante** | dépendance éditeurs |
| F. SaaS | élevé | forte | plateforme + produit |

## 9. Actifs mobilisables pour la communication

- Nom et concept clairs (« Object 2 Music »), naming des vues (Basic/Full).
- Dépôt GitHub public (GPL-3.0), historique de développement actif.
- Slide deck de présentation (Google Slides) et espace Notion (doc + install) —
  à rafraîchir.
- Interface démontrable en ligne (instances de démo derrière HTTPS).
- Histoires d'usage authentiques (famille, enfants, voiture, matinales) — matière
  à storytelling non fabriqué.

## 10. Questions ouvertes pour l'analyse stratégique

Révisées au 2 septembre 2026. Deux points ont bougé depuis la version précédente.

**Ce qui n'est plus une question ouverte**
- *« Le moteur d'ambiance tient-il ses promesses ? »* — oui, désormais mesurable
  (53 % des pistes, 97 % des artistes). L'argument peut être avancé sans réserve.
- *« Le multi-tenant impose-t-il une refonte du modèle de données ? »* — non. Le
  schéma porte déjà l'appartenance ; le chantier est l'isolation des lectures et
  l'authentification (voir §8-F).

**Ce qui reste ouvert**
1. **Cible** : makers/open source ? familles dé-écranisation ? enfants (marché
   Toniebox) ? hôtellerie/lieux (ambiance data-driven) ? mix ?
2. **Modèle** : pur open source communautaire ; kit matériel (lecteur NFC +
   image serveur prête) ; service installé ; SaaS ?
3. **Rapport à Spotify** : la question la plus structurante, et **elle est
   partiellement tranchée depuis septembre 2026** (voir §8-D). Toute *diffusion* d'un
   produit intégrant la lecture Spotify est fermée : plafond de 5 utilisateurs sans
   250 000 MAU préalables, mixage de sources et monétisation explicitement interdits.
   La question n'est donc plus « rester dépendant ou non » pour un produit — c'est
   « **quelle offre construire sans lecture Spotify** », Spotify restant l'usage
   privé du foyer. Reste ouvert : bibliothèque locale, autres backends Mopidy
   (Tidal, Deezer, Jellyfin, Bandcamp…), ou centrage sur le contenu parlé.
4. **Positionnement dé-écranisation** : opportunité forte (parentalité, santé
   numérique) — quel angle sans être moralisateur ?
5. **Effort produit avant diffusion** : onboarding, sécurité, packaging hardware,
   documentation — quel minimum viable selon la cible retenue ?
6. **Le contenu parlé doit-il devenir le fer de lance ?** La question gagne en force
   depuis l'analyse §8-D : c'est la partie la plus différenciante, la moins
   concurrencée, celle qui porte le savoir le plus difficile à répliquer (§8-E) —
   et **la seule sans dépendance de plateforme** (RSS ouvert, API Radio France
   publique, fichiers téléchargeables donc utilisables hors ligne). Les trois
   contraintes majeures du dossier — licence, distribution, mobilité — s'évanouissent
   toutes sur ce périmètre. C'est probablement la conclusion la plus actionnable de
   ce document.
