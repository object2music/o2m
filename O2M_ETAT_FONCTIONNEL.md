# O2M (Object 2 Music) — État fonctionnel et d'usage

> Document de référence destiné à alimenter une analyse stratégique / d'opportunité
> marketing et un plan de communication. Il décrit **ce que le produit fait
> réellement aujourd'hui**, comment il est utilisé, son niveau de maturité et ses
> contraintes — sans embellissement.
> Dernière mise à jour : **2 septembre 2026** (chiffres mesurés sur la base de
> production ce jour-là).

---

## 1. Le pitch et la proposition de valeur

**O2M — Media Shaker.** *Remix knowledge and music, finally.*

**O2M est votre station média personnelle. Musique, podcasts, radios, livres audio :
tout dans une seule file, composée par un moteur dont vous lisez les règles et que vous
réglez du bout du doigt.** En trois verbes, repris de la présentation du projet :
**Explore & choose · Share · Be your own trend.**

### Le problème

L'offre de contenus est infinie, et pourtant trouver *le bon* contenu, *maintenant*,
sans y passer du temps et sans médiation, reste difficile. Pris entre explorer et
choisir, on bute sur ses limites de temps et d'attention tout en voulant la meilleure
expérience : puissante, apprenante, singulière, reliée à son histoire. Les plateformes
répondent par des algorithmes opaques et des applications cloisonnées par type de
contenu ; l'expérience est individuelle, jetable, et une expérience média mémorable
perd de sa valeur si elle n'est pas partagée.

O2M propose l'inverse : un **média régénératif** (*the regenerative media*) — qui
capitalise dans le temps long, transmet et fait évoluer ce qu'on écoute au lieu de le
consommer et l'oublier ; où les objets et les boîtes portent une histoire qui mérite
autant d'être transmise que, parfois, oubliée.

### Trois convergences

Un objet unique en son genre, né dans un foyer réel et rodé pendant des années d'usage
quotidien, qui se tient à la convergence de trois tensions très contemporaines :

- **Information × musique.** Les plateformes les rangent dans des apps séparées ; la vie
  les mêle. O2M compose une seule file où le bulletin du matin glisse vers le mix, où
  l'épisode entamé hier revient à sa place entre deux titres, où la radio prend le
  relais quand la bibliothèque s'épuise.
- **Ouverture × fermeture.** Face aux algorithmes opaques et aux jardins clos, O2M
  expose son score de popularité, ses strates de bibliothèque et ses règles de
  sélection, et tourne sur un pipeline open source avec les données chez soi. Il puise
  autant dans les contenus libres (RSS, radios, Radio France, fichiers) que dans les
  catalogues fermés.
- **Individuel × collectif.** Une boîte par personne, un dosage pour la pièce : la file
  du foyer est le point de rencontre. Deux membres activent chacun leurs boîtes, le
  moteur les mêle ; seul en voiture, la même station vous suit. Dans un monde polarisé,
  peu de choses méritent plus d'être partagées qu'une musique ou un contenu qui compte :
  en famille, en soirée, entre cultures — chacun a son mot à dire.

D'autres paires traversent le projet et peuvent nourrir la communication : hasard ×
histoire, local × global, ici et maintenant × temps long, tangible × configurable.

Formules courtes : **« Toute votre audio. Une seule file. Vos règles. »** ·
*« Mix your media in a single place, with open rules. Share distinguished experiences
widely. »* (deck) · « Vos contenus, vos boîtes, votre dosage. »

Il s'utilise de **deux manières qui déclenchent exactement les mêmes comportements** :
- une **interface classique** (webapp mobile et desktop) : activation de plusieurs
  boîtes, bouton *auto*, vue Basic à quatre interrupteurs, réglages de découverte et
  d'ambiance — c'est l'usage principal ;
- des **objets NFC**, secondaires, qui appellent la même API : poser un objet revient à
  activer sa boîte depuis l'écran, sans l'écran.

Le nom « Object 2 Music » désigne l'origine du projet, pas son périmètre : la valeur est
dans le moteur et l'organisation des contenus, l'objet n'est qu'un déclencheur parmi
d'autres. La version précédente de ce pitch (« Spotify tangible et familial ») réduisait
O2M à la matérialisation de la musique — c'est réducteur, et c'est la face du produit la
plus exposée à la dépendance Spotify (§8-D). La proposition de valeur tient sur sept
axes ; la matérialisation n'y apparaît que comme une variante du cinquième.

### Les sept axes

Ils prolongent les six valeurs de la présentation — *Accessible… even tangible ·
Organised, as you are · Fully configurable · Contents live blend · Balanced
recommendations · Open-source and possibly local* — en y ajoutant la transparence de la
bibliothèque (axe 3) et la mobilité (axe 6), et en rétrogradant le tangible au rang
d'option.

**1. Des boîtes, pas des playlists.**
Une box agrège des playlists, des albums, des artistes, des flux podcast, des radios,
des livres audio et des *motifs dynamiques* (dernières infos, podcasts en
cours, un album au hasard, une émission par sujet). Le contenu est réorganisé **par
usage** — « le matin », « les enfants », « jazz du soir » — et non par source ni par
application. Une box peut en contenir d'autres (cascades). 150 objets en production.

**2. Un seul mix, un seul dosage.**
Plusieurs box actives en même temps alimentent **une seule file de lecture**. Le niveau
de découverte (0-10) et la cible d'ambiance (énergie × valence) s'appliquent au mélange
entier, pas à chaque source. Boîtes mixées + dosage unique = des expériences médias
augmentées :
- *collectives* — deux membres du foyer activent chacun leur box, la file les mêle ;
- *individuelles* — « mon trajet » = un bulletin d'infos frais, puis un mix musical
  calé sur l'heure, sans une interaction de plus.

**3. Une bibliothèque qui se range toute seule, et qui dit pourquoi.**
Chaque piste vit dans une **strate** de cycle de vie visible : `new` → `incoming` →
`library` → `favorites`, plus `hidden` et `trash`. La **popularité** est une formule
ouverte et documentée (complétion lissée, volume, skips, récence, like, appartenance
playlist), recalculée en lot, lisible dans le dépôt et couverte par des tests — pas une
boîte noire de plateforme. En production : 54 100 pistes `new`, 8 841 `library`,
765 `favorites`.

**4. Un moteur de flow dont on lit les règles.**
Le moteur de service compose un *flow* et une dynamique de renouvellement équilibrée,
pilotées par le niveau de découverte : les proportions des sources varient avec lui
(DL0 = presque tout favoris/habitudes, DL10 = presque tout nouveautés), la pondération
d'ambiance est une gaussienne dont la largeur suit le même curseur, et un
anti-répétition gradué sur plusieurs jours empêche les titres de confort de revenir à
chaque session. Tout est documenté dans le dépôt (`CLAUDE.md`, section
*Auto-Selection Algorithm*). S'y ajoutent des **motifs intelligents** utilisables dans
n'importe quelle box : podcasts en cours de lecture (`podcasts:unfinished`), mix auto
(`auto:`), dernières infos (`infos:library`), un album au hasard (`albums:spotify`,
`albums:local`), habitudes horaires (`now:`, `herenow:`), nouveautés récentes
(`newrecent:`), et recherche d'émissions par mot-clé Radio France (`rf:sujet:`).

**5. Un geste, ou tous les réglages.**
La vue **Basic** lance tout en un geste : quatre interrupteurs *Music / Podcast / Info /
Radio*, un bouton *ALL*, deux potentiomètres (découverte, ambiance). La vue **Full**
ouvre tout : matrice d'ambiance 2D, choix des box, genres, tracklist annotée, fiches
détail, édition. **Même moteur, deux niveaux de lecture.** L'objet NFC est une
troisième commande, optionnelle et sans écran, pour les enfants, les invités et les
rituels : il ne fait rien de plus qu'un appui dans l'interface, il le fait sans
téléphone.

**6. Partout : multicontrôle, multilecture.**
PWA installable, desktop et mobile. Plusieurs téléphones contrôlent la même file ; un
téléphone peut aussi *lire* le flux du foyer en mobilité (voiture, 5G, indicateur de
qualité réseau) ou devenir une enceinte de plus dans le multiroom.

**7. Open source, chez vous.**
Mopidy + Snapcast (mobilité et multiroom) ou Mopidy + enceinte (maison). Code GPL-3.0,
données d'écoute chez soi, déployable en Docker ou nativement sur Raspberry Pi.

### Ce que le pitch ne doit pas prétendre

Le document reste honnête (§6, §8) : O2M n'est pas installable par le grand public en
l'état, la lecture Spotify ne peut pas être distribuée (§8-D), et le flux temps réel en
mobilité coupe encore. Les **livres audio** sont lus comme fichiers locaux ou flux et
bénéficient de la reprise de position des contenus parlés, mais il n'existe pas encore
de type ni de motif dédié. Les sept axes ci-dessus sont tous **démontrables
aujourd'hui** sur l'instance de production ; ils ne préjugent pas d'une offre.

## 2. Le concept en une image

La **box** est le contenu réorganisé, le **dosage** est le réglage, la **commande** est
au choix : l'interface (mobile, desktop) ou un objet NFC. Tout le reste découle de ces
trois termes :

- **Box = contenus + comportements** : chaque box porte un contenu (playlists,
  albums, artistes, feeds podcast, flux radio, motifs dynamiques) ET des réglages
  (niveau de découverte, tri, quantité, cibles d'ambiance).
- **Une seule API, deux déclencheurs** : un appui dans l'interface et un objet posé
  sur le lecteur appellent le même point d'entrée (`box_action`). Tout ce que fait un
  objet, l'interface le fait ; l'inverse n'est pas vrai (réglages, édition, choix fin).
- **Scénarios composables** : une box peut inclure d'autres box (« cascades ») —
  ex. l'objet « Auto morning » = infos fraîches + radio FIP + mix musical adaptatif.
- **Data-driven local** : chaque écoute nourrit une base chez soi (position de
  lecture, complétion, skips, moment de la journée, mood) qui pilote les choix
  suivants selon des règles lisibles.
- **Dé-écranisation comme option, pas comme dogme** : parce que le contenu est déjà
  organisé et dosé, le geste suffisant *peut* être un objet posé. Les enfants, invités,
  grands-parents lancent leur média sans téléphone ni compte ; les autres utilisent
  l'écran.

## 3. L'expérience utilisateur (parcours réels)

1. **Le matin** : on active la box « matin » (depuis le téléphone ou en posant
   l'objet) → bulletin d'infos du jour, puis un mix musical calé sur l'heure et les
   habitudes. Le tout enchaîne sans interaction.
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
  YouTube, flux radio (Radio France…), fichiers locaux (dont livres audio), mots-clés
  dynamiques
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

**Publics visés (hypothèses, issues de la présentation du projet — non validées par
des entretiens)** — quatre personas et leurs mots :
- **Le collectionneur de CD / vinyles, la quarantaine** : « J'ai beaucoup de disques
  auxquels je tiens pour l'objet. Je ne découvre plus rien depuis le cloud, je n'y
  comprends rien, et on me dit que ça pollue. »
- **L'utilisateur Spotify des générations X-Y-Z** : « Je reçois plein de
  recommandations mais je n'arrive pas à les attraper, ma musique est un chaos. Je
  voudrais une expérience plus contextuelle, des marque-pages. Et je sais qu'il y a
  d'autres mondes que je n'utilise pas, l'énorme offre podcast en tête. »
- **Les parents qui veulent encadrer les écrans** : « Les écrans captent l'attention
  au quotidien. Je voudrais éviter l'usage autonome de l'ordinateur pour mes enfants
  et les accompagner vers des contenus éducatifs. »
- **Le groupe d'amis dans un lieu public** : « Je voudrais reprendre la main sur la
  musique simplement, proposer mes recommandations et découvrir celles des autres. »

Les trois premiers correspondent aux usages observés dans le foyer ; le quatrième
(lieu, groupe, chacun a son mot à dire) est le seul qui n'a jamais été mis en situation.

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
repackaging — mais une réécriture **bornée** (environ 130 appels et trois événements,
voir l'étude détaillée au §13). Ce qui intéresserait cette communauté (petite mais
qualifiée) : le mix auto ambiance/découverte et la gestion podcast (reprise, catalogue,
sujets). Bon vecteur de **notoriété technique**, marché quasi nul — mais, et c'est le
point important du §13, c'est aussi ce qui rendrait le kit S2 installable en une ligne.

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
- **Une proposition de valeur en sept axes** (§1), chacun démontrable sur
  l'instance de production et rattaché à des chiffres mesurés.
- Dépôt GitHub public (GPL-3.0), historique de développement actif.
- Slide deck de présentation (Google Slides) et espace Notion (doc + install).
  Le deck fournit une signature réutilisable (*Media Shaker*, *the regenerative
  media*, *Explore & choose / Share / Be your own trend*), une page « enjeux médias »,
  quatre personas avec verbatims (§5), six valeurs et une bibliothèque de motifs
  illustrée. Il est daté sur trois points : il annonce une application Android
  native (fermée depuis, §8-D), décrit une boîte « RECOs » remplie par les
  recommandations Spotify (API dépréciée) et ne mentionne ni le mood, ni Radio France,
  ni le contenu parlé par sujet — les trois différenciateurs les plus récents.
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


## 11. Étapes d'analyse proposées — diffusion et valorisation

Plan de travail pour passer de « ce que le produit est » (ce document) à « ce qu'on
pourrait en faire ». Chaque étape a un livrable court ; les étapes 1 à 3 sont
indépendantes et peuvent être menées en parallèle.

### Étape 0 — Poser l'hypothèse de périmètre
Décider explicitement si l'analyse se fait **avec ou sans lecture Spotify dans l'offre**.
§8-D et §10-3 plaident pour « sans » : Spotify reste l'usage privé du foyer, l'offre se
construit sur le contenu parlé, la bibliothèque locale et les autres backends Mopidy.
Livrable : une phrase de cadrage, datée, en tête de la suite du dossier.

### Étape 1 — Matrice « axes de valeur × périmètre de contenu »
Pour chacun des sept axes du §1, mesurer quelle part de la valeur **subsiste** selon la
source : Spotify / fichiers locaux / podcasts RSS / Radio France / radios / autres
backends (Tidal, Deezer, Jellyfin, Bandcamp). Les axes 1 à 4 (boîtes, mixage, strates,
algorithme) sont a priori indépendants de la source ; l'axe 2 perd la musique streaming.
Livrable : une grille 7 × 6 avec trois niveaux (intact / dégradé / perdu).

### Étape 2 — Benchmark par axe, pas par produit
Le paysage du §7 compare des produits entiers. Comparer plutôt **axe par axe** :
- méta-playlists et strates de bibliothèque : Plexamp, Roon, Navidrome, Volumio, moOde ;
- mixage multi-source et flow parlé/musical : Pocket Casts, AntennaPod, Snipd, l'app
  Radio France, les « morning briefings » des assistants ;
- transparence algorithmique et popularité ouverte : Last.fm, ListenBrainz (Troi) ;
- tangible / sans écran : Yoto, Toniebox, Phoniebox, Tonuino, projets DIY Mopidy.
Livrable : pour chaque axe, un verdict *unique / rare / commun*, et la liste des axes
que personne d'autre ne tient ensemble.

### Étape 3 — Cibles et entretiens
Partir des quatre personas de la présentation (§5 : collectionneur de disques,
utilisateur Spotify noyé dans ses recommandations, parents encadrant les écrans, groupe
d'amis dans un lieu) et y ajouter les cibles apparues depuis : makers / auto-hébergeurs,
gros consommateurs de podcasts et d'actualité, lieux (hôtellerie, commerces,
tiers-lieux) cherchant une ambiance pilotée par les données. Cinq à huit entretiens par
cible, en faisant réagir aux sept axes et à une démo, pour repérer **quels axes
déclenchent** et lesquels laissent indifférent. Les verbatims du deck servent de point
de départ ; ce sont des hypothèses à confirmer ou à réfuter, pas des résultats.
Livrable : les sept axes classés par cible ; la ou les deux cibles retenues.

### Étape 4 — Formes de diffusion, chiffrées
Évaluer chaque forme sur quatre critères : effort, dépendance de plateforme, revenu
possible, cohérence avec les axes retenus à l'étape 3.
- a. image Raspberry Pi prête à flasher + documentation (voie communautaire) ;
- b. briques extractibles : librairie popularité (§8-A), moteur de sélection (§8-B),
  brique contenu parlé / Radio France (§8-E) ;
- c. kit matériel (lecteur NFC + serveur préinstallé) ;
- d. service installé chez le client ou dans un lieu ;
- e. SaaS centré sur le contenu parlé (§8-F, sans Spotify) ;
- f. application mobile hybride non-Spotify (§8-D, dernier paragraphe).
Livrable : un tableau forme × critère, et deux ou trois formes candidates.
Une première passe de cette étape est faite au §12.

### Étape 5 — Vérification juridique et licences
Ce que chaque forme retenue implique : obligations GPL-3.0 pour un kit ou un service ;
conditions d'usage commercial de l'API Radio France ; règles des flux podcast
(publicité, mesure d'audience) ; Spotify déjà instruit (§8-D).
Livrable : liste des feux rouges et des points à négocier, par forme.

### Étape 6 — Test de traction à faible coût
Avant tout investissement produit, mesurer l'intérêt réel avec ce qui existe déjà :
publier la librairie popularité, ouvrir une instance de démo, écrire un article
« un moteur de recommandation dont on lit les règles » pour les communautés Mopidy,
auto-hébergement et podcast. Six à huit semaines d'observation.
Livrable : signaux chiffrés (visites, stars, issues, demandes d'installation) et
verbatims, mis en regard des cibles de l'étape 3.

### Étape 7 — Minimum viable de diffusion
Pour les formes retenues : onboarding, sécurité (au-delà de basic-auth), packaging,
documentation à jour, désensibilisation à Spotify. Chiffrage en semaines.
Livrable : périmètre minimal et coût, par forme.

### Étape 8 — Décision
Go / no-go par forme, et feuille de route à six mois. Les questions du §10 doivent
toutes avoir une réponse, ou un propriétaire et une date.


## 12. Analyse d'opportunité croisée — valeurs modulaires × faisabilité technique

Cette section croise **ce que le dispositif contient de réutilisable** (les modules) avec
**sept scénarios d'évolution**, et évalue chacun sur quatre critères demandés :
proportion du projet conservée, charge de travail *utile* (celle qui garde sa valeur même
si le scénario échoue), risques et verrous, revenus ou bénéfices symboliques. Les faits
techniques ont été vérifiés dans le code le 2 septembre 2026 ; les faits externes
(politiques de plateformes, licences) sont datés et signalés « à vérifier » quand ils
n'ont pas pu l'être.

### 12.1 Les modules — ce qui est réellement détachable

| # | Module | Où | Dépendance Spotify | Détachabilité |
|---|---|---|---|---|
| M1 | **Boîtes / méta-playlists, cascades, motifs dynamiques** | `Box`, `box_action`, `_META_PATTERNS`, motifs `auto:`, `now:`, `albums:`, `podcasts:`, `rf:` | Faible dans le modèle, forte dans les **données** (la majorité des contenus de box sont des URIs Spotify) | Bonne : le concept est agnostique, les box existantes ne le sont pas |
| M2 | **Moteur de mix et de dosage** (proportions par DL, gaussienne mood, température, anti-répétition) | `tracklistfill_auto`, `_mood_pick`, `_expand_pick`, `_cooldown_factor` | Nulle sur le principe ; les recos live Spotify sont déjà dépréciées | Moyenne : méthodes de `O2mToMopidy`, extraction = chantier identifié (§8-B) |
| M3 | **Strates et popularité ouverte** | `popularity.py` (143 lignes, 15 tests), transitions de strates dans `dbhandler` | Nulle | Excellente pour le score ; moyenne pour les transitions |
| M4 | **Enrichissement mood / genres** (Last.fm) | `spotifyhandler.py` (malgré son nom) | Nulle : ne demande que des noms d'artiste et de titre | Bonne, à extraire d'un fichier mal nommé |
| M5 | **Contenu parlé** (RSS, Radio France, sujets, reprise, pré-pub, budget partagé) | `radiofrance.py` (422 l.), partie podcast de `o2mtomopidy`, `PodcastChannel`, `RfTaxonomy` | Nulle | Bonne ; c'est l'actif le plus autonome (§8-E) |
| M6 | **Résilience locale** : cache audio et substitution | service `spotdl/cache.py`, `Track.local_uri`, résolution dans `o2mtomopidy` | Le service part d'URIs Spotify mais télécharge **depuis YouTube** | Bonne techniquement, **problématique juridiquement** (voir S2) |
| M7 | **UI Basic / Full, PWA, multicontrôle** | `o2m/static/mood.html` (7 482 l.), `o2m.js` injecté dans Iris, frontend SvelteKit (dev) | Nulle : parle à l'API O2M | Bonne, mais monolithique |
| M8 | **Pipeline de diffusion** : Mopidy + Snapcast, multiroom, navigateur-enceinte, 5G | compose, `snapstream.ts` | Nulle (Mopidy embarque déjà Local, Podcast, TuneIn, YouTube) | Standard open source, rien à extraire, tout à packager |
| M9 | **Tangible NFC** | `nfcreader.py` (pyscard) → même `box_action` que l'UI | Nulle | Petit module, remplaçable (lecteur USB, téléphone NFC) |
| M10 | **Historique d'écoute et habitudes** | `Stats_Raw` (102 542 écoutes), `now:` / `herenow:` | Nulle | Le jeu de données lui-même est un actif (longitudinal, un foyer, plusieurs années) |
| M11 | **Savoir-faire non codé** : API Radio France, pièges Spotify 2026, ecosystème Mopidy | `CLAUDE.md`, mémoire du projet | — | Transférable en conseil, en documentation, en conférence |

Ordres de grandeur pour lire la « proportion conservée » : le cœur Python fait environ
12 000 lignes (`o2mtomopidy` 3 800, `spotifyhandler` 2 800, `main` 2 400, `dbhandler`
2 400) ; l'UI 7 500. Le mot « spotify » apparaît 181 fois dans `o2mtomopidy`, 166 dans
`main`, 47 dans `dbhandler` : la dépendance est **répandue mais concentrée**, elle se
retire en semaines, pas en mois.

### 12.2 Les scénarios

Grille commune : **Conservé** (part des modules qui restent en service) · **Charge utile**
(ordre de grandeur en personne-mois, et ce qui reste acquis en cas d'échec) · **Risques et
verrous** · **Revenus / symbolique** · **Verdict**.

---

#### S1. Application dans la sphère Spotify, monétisable (plugin, app compagnon)

Spotify n'a **pas de système de plugins** : la seule voie est une application tierce sur
l'API Web, le Web Playback SDK ou App Remote — toutes régies par la même politique
développeur, instruite au §8-D. Trois variantes ont été examinées :
- *app qui lit* : plafond 5 utilisateurs, mixage de sources interdit, alarme interdite ;
- *app qui n'organise que les playlists* (boîtes et strates appliquées au compte Spotify de
  l'utilisateur, export en playlists) : même politique, même plafond de 5 utilisateurs
  tant que l'*extended quota* n'est pas accordé, et **« Commercial uses are not permitted
  for SDAs »** ;
- *contournement d'identité* (client de bureau) : disqualifiant dans un produit distribué.

| Critère | Évaluation |
|---|---|
| Conservé | M1 et M3 en idées (~15 %) ; tout le reste est à réécrire dans un client mobile |
| Charge utile | 6-9 p·m de réécriture, **quasi nulle en valeur résiduelle** : le code produit ne servirait à rien d'autre |
| Risques et verrous | Fermé par construction : distribution (5 users / 250 000 MAU), monétisation (interdite), mixage (interdit), plus l'instabilité technique constatée (login5, août 2026) |
| Revenus / symbolique | 0 / faible |
| **Verdict** | **Abandonner**. Spotify reste l'usage privé du foyer. La seule survivance utile est le design hybride du §8-D (App Remote pour la musique, natif pour le reste) — et il n'est pas monétisable non plus. |

---

#### S2. Dispositif personnel sur serveur local : kit documenté pour la communauté libriste, avec résilience locale

C'est la continuité directe du projet. Tout tourne déjà ; le travail est du **packaging**
et de la **désensibilisation à Spotify** (rendre optionnel, pas retirer).

**Sur la résilience par téléchargement.** Le service `spotdl` existe et fonctionne :
chaque nuit il télécharge les titres des box épinglées et O2M substitue le fichier local
à l'URI Spotify. Mais `spotdl` obtient l'audio **depuis YouTube**, ce qui contrevient aux
conditions de YouTube et, en droit français, ne relève pas de la copie privée (source
non licite). Pour un outil privé c'est un risque personnel ; **dans un kit distribué,
c'est un motif de retrait** et une entrave à tout partenariat ultérieur (S3, S4). Le kit
doit donc fonder sa résilience sur des sources dont le téléchargement est légitime :
- **podcasts et radios** : fichiers HTTP ouverts, déjà stockés sous une forme
  téléchargeable (`podcast+<flux>#<guid>`) — c'est le vrai gisement de résilience ;
- **fichiers possédés** : CD et vinyles numérisés (le persona « collectionneur » du §5 est
  exactement ce public), achats Bandcamp / Qobuz sans DRM ;
- **musique libre** : Jamendo, Free Music Archive, Bandcamp en écoute ; catalogues de
  médiathèques via leurs abonnements (voir S7b) ;
- **serveurs personnels** : Jellyfin, Navidrome, Funkwhale comme backends Mopidy.
`yt-dlp` reste légitime pour *lire* YouTube (c'est ce que fait Mopidy-YouTube), pas pour
*constituer* une bibliothèque.

| Critère | Évaluation |
|---|---|
| Conservé | **~85 %** : M1 à M10 tels quels ; Spotify passe en option « apportez votre compte », le service spotdl devient un module désactivé par défaut ou retiré |
| Charge utile | 3-6 p·m : image Raspberry Pi prête à flasher, installateur, onboarding (première box, première source), SQLite par défaut, authentification correcte, documentation à jour, retrait des chemins Spotify obligatoires. **Tout ce travail reste acquis** pour S4, S5, S7 : c'est le socle commun |
| Risques et verrous | Charge de support d'une communauté ; vieillissement de l'écosystème Mopidy (Iris peu maintenu, Mopidy-Spotify en alpha) ; sécurité « maison » à durcir avant exposition ; matériel à assembler (lecteur NFC) |
| Revenus / symbolique | Revenus faibles (dons, vente d'un kit matériel RPi + lecteur + boîtier à faible marge, prestations d'installation) ; **symbolique élevé** : visibilité, contributeurs, crédibilité pour tous les autres scénarios |
| **Verdict** | **Faire, en premier.** C'est le seul scénario sans verrou externe, et il produit le socle dont dépendent S4, S5 et S7. Condition : régler la question spotdl avant publication. La forme « extension Mopidy » (§13) en est la meilleure incarnation : le kit devient `pip install Mopidy-O2M` sur n'importe quelle installation Mopidy existante. |

---

#### S3. Conseil commercial fondé sur les usages, auprès des plateformes de streaming (Deezer…)

Ce qu'on vend n'est pas du code mais **des résultats d'usage et des mécanismes
démontrés** : le curseur de découverte comme contrat explicite avec l'auditeur, la matrice
d'ambiance à partir de tags ouverts, la popularité bayésienne lisible, les boîtes comme
méta-playlists par usage, le mixage info + musique, l'abonnement à un *sujet* plutôt qu'à
une émission. Le prototype et le jeu de données (M10) servent de preuve.

Deezer est l'interlocuteur naturel (français, a communiqué sur la transparence de *Flow*,
équipe de recherche active) ; Qobuz (curation, public collectionneur) ensuite. Note : les
API publiques de Deezer et Qobuz n'offrent pas de lecture intégrale aux tiers — le sujet
n'est pas l'intégration mais le conseil (à vérifier pour Tidal, qui a rouvert une API
développeur en 2024).

| Critère | Évaluation |
|---|---|
| Conservé | ~10 % en code (démo), **100 % en savoir** (M2, M3, M11 et la documentation déjà écrite) |
| Charge utile | 1-2 p·m pour un dossier : benchmark axe par axe (§11-2), résultats mesurés sur le foyer, deux ou trois publications (billet technique, conférence type ISMIR / RecSys, Mopidy Discourse). Utile en soi : cette matière sert aussi S2, S4, S5 |
| Risques et verrous | Faible crédibilité d'une personne seule face à des équipes de recherche ; **aucune protection** (GPL-3.0 : les idées sont publiques, le code réutilisable) ; syndrome « pas inventé ici » ; accès aux décideurs. Le jeu de données d'un seul foyer est anecdotique statistiquement, mais rare par sa durée |
| Revenus / symbolique | Jours de conseil possibles mais improbables sans notoriété préalable ; **symbolique moyen à fort** si une publication ou une intervention est acceptée |
| **Verdict** | **Opportuniste, après publication.** Ne pas démarcher à froid : publier d'abord (S7a, S7e), laisser venir. |

---

#### S4. Partenariat avec les plateformes publiques : Radio France, FIP

L'actif le plus solide du dossier est ici. O2M possède déjà : un client de l'OpenAPI Radio
France avec ses contraintes documentées, la conversion des épisodes en flux podcast, la
jointure flux/API par identifiant de page, la taxonomie (343 thèmes, 1 146 mots-clés) et
la **sélection par sujet** — une fonction que l'application Radio France elle-même ne
propose pas sous cette forme. Côté FIP : les métadonnées *livemeta* permettent déjà de
capter ce qui passe à l'antenne dans la strate `new`, faisant de FIP une **source de
découverte** pour la bibliothèque personnelle.

Le mélange info + musique est de plus le concept éditorial de France Inter : proposer
« vos contenus par sujet, mêlés à votre musique, avec un dosage visible » parle leur
langue. Formes possibles : prototype présenté à la direction du numérique ou à
l'innovation, participation à un appel à projets, résidence, hackathon, ou simple
convention d'usage de l'API à des fins de démonstration publique.

| Critère | Évaluation |
|---|---|
| Conservé | ~40 % du code (M5, M1, M10, M7 en démonstrateur) ; **100 % du savoir M11** |
| Charge utile | 1-2 p·m : prototype ciblé (box « sujet » + FIP → découverte), dossier, prise de contact. Utile en soi : consolide M5, qui est le fer de lance de S5 |
| Risques et verrous | Conditions d'usage de l'OpenAPI (usage commercial probablement exclu sans accord — à vérifier) ; lenteur institutionnelle et règles de commande publique ; dépendance à une seule institution ; les épisodes sans `podcastEpisode` restent non lisibles via l'API |
| Revenus / symbolique | Revenus faibles ou indirects (prestation R&D, subvention innovation, résidence) ; **symbolique très élevé** : légitimité, presse, accès à un public national. Bénéfice mutuel réel : Radio France gagne un cas d'usage de son API |
| **Verdict** | **Chercher, en parallèle de S2.** Le meilleur rapport effort / crédibilité du dossier. Prérequis : un démonstrateur propre (donc sans spotdl, donc S2 avancé) et le point juridique sur l'API. |

---

#### S5. Nouveau service : application robuste et résiliente, éducation aux algorithmes ouverts (Tournesol, Pol.is), tout téléchargeable, dimension collective

C'est le **produit** vers lequel tout le reste converge, et le seul scénario qui exploite
les trois convergences du pitch à la fois. Ce qu'il apporte de nouveau :
- **éducation aux algorithmes** : les règles sont déjà ouvertes (M2, M3) ; l'étape suivante
  est de les rendre **co-réglables** — à la manière de Tournesol, des comparaisons par
  paires (« lequel de ces deux titres convient mieux à cette ambiance ? ») pour affiner le
  mood et la popularité ; à la manière de Pol.is, une **négociation collective du dosage**
  quand plusieurs personnes alimentent la même file (le curseur de découverte devient un
  consensus, pas un réglage individuel) ;
- **résilience** : tout le non-Spotify est téléchargeable légitimement (podcasts, radios en
  différé, fichiers possédés, musique libre, livres audio sans DRM) → une application
  mobile qui lit hors ligne, la musique de plateforme restant en option via App Remote
  (design hybride §8-D) ;
- **collectif** : comptes, foyers ou groupes, file partagée, historique par personne
  (`username` existe déjà, rien ne filtre dessus — §8-F).

Le point faible est structurel : **la musique de plateforme n'y est pas**. Le service sera
fort sur le parlé, le local et le libre, faible sur « toute la musique du monde ». C'est
acceptable si la cible est explicitement l'éducation, les familles, les médiathèques, les
collectifs — pas le grand public Spotify.

| Critère | Évaluation |
|---|---|
| Conservé | ~60 % : M1-M5, M10 comme cœur de service ; M7 refondue (application mobile hors ligne) ; M8 réduit ; Spotify sort du périmètre de lecture |
| Charge utile | **12-24 p·m et une équipe** (backend multi-tenant, application mobile avec cache hors ligne, comptes, mécanismes de comparaison et de consensus, hébergement, RGPD). Utile partiellement : le backend multi-tenant et l'application hors ligne ne servent que ce scénario |
| Risques et verrous | Financement et portage (structure associative ou coopérative plutôt que start-up) ; concurrence sur le parlé (Pocket Casts, AntennaPod, Snipd) et sur l'éducation aux médias ; adoption d'un catalogue musical amputé ; charge d'exploitation d'un service |
| Revenus / symbolique | Abonnement freemium modeste ; **financements publics crédibles** : éducation aux médias et à l'information (CLEMI, ministère de la Culture), fonds européens NGI, fondations numériques ; **symbolique maximal** — un objet unique en son genre, cohérent avec Tournesol et Pol.is |
| **Verdict** | **Objectif à moyen terme, conditionné à un financement.** Ne pas démarrer avant S2 (socle) et S4 (légitimité). Le sous-ensemble « application parlé hors ligne » (§8-D) est un premier jalon autonome. |

---

#### S6. Dispositif tangible premium pour espaces publics (bars, hôtels, coworkings, boutiques) : remplacer le juke-box

L'idée exploite le persona 4 du §5 (« chacun a son mot à dire ») : des cartes NFC ou le
téléphone des clients alimentent la file du lieu, le gérant fixe le dosage et l'ambiance,
le moteur arbitre. C'est un **juke-box collaboratif à règles ouvertes** — un positionnement
que ni TouchTunes ni Rockbot n'occupent.

Le verrou est la **licence musicale**. Diffuser de la musique dans un lieu commercial exige
en France la SACEM et la SPRE quels que soient les moyens, et les abonnements grand public
(Spotify, Deezer) interdisent l'usage professionnel. Il faut un catalogue **B2B licencié** :
Soundtrack Your Brand (API partenaires — à vérifier pour le contrôle de lecture), offres
professionnelles des plateformes, ou musique libre de droits (Jamendo Licensing, Epidemic
Sound). O2M deviendrait la couche d'interaction et d'intelligence au-dessus de ce
catalogue — ce qui suppose que le catalogue l'autorise.

| Critère | Évaluation |
|---|---|
| Conservé | ~70 % : M1, M2, M7, M8, M9 sont le cœur ; M5 et M10 secondaires ; Spotify exclu |
| Charge utile | 6-12 p·m : matériel durci (lecteur, boîtier, réseau du lieu), comptes gérant / clients, intégration d'un catalogue licencié, facturation, support. Peu réutilisable hors de ce scénario, sauf le multi-comptes |
| Risques et verrous | Licence (bloquant tant qu'un catalogue B2B n'est pas ouvert à un tiers), cycle de vente B2B, support matériel sur site, concurrence installée (TouchTunes, Rockbot, Soundtrack) |
| Revenus / symbolique | **Le seul scénario à revenu récurrent clair** (abonnement par lieu, installation, éventuellement participation des clients) ; symbolique moyen |
| **Verdict** | **Conditionnel.** Ne s'ouvre que si un fournisseur B2B accepte l'intégration. À sonder tôt (un courriel suffit), à ne pas construire avant. Variante à préférer : les **lieux publics non commerciaux** (S7b), où la licence est déjà réglée. |

---

#### S7. Autres pistes

**S7a. Paquets open source : librairie popularité + moteur de sélection (+ extension Mopidy).**
Conservé : M2, M3 (100 % de leur code). Charge : 0,5 p·m pour la librairie, 2-3 p·m pour le
moteur et une extension Mopidy réelle (§8-C). Risque nul. Revenus nuls, symbolique fort
auprès des communautés techniques ; c'est la porte d'entrée de S3. **Faire immédiatement.**

**S7b. Médiathèques et tiers-lieux culturels.** Les médiathèques françaises disposent de
catalogues musicaux **déjà licenciés** pour leurs usagers (offres type diMusic / 1D touch,
Philharmonie à la demande) et cherchent des dispositifs de médiation : bornes tangibles
pour les enfants (M9), écoute par sujet (M5), ateliers « comprendre un algorithme de
recommandation » (M2, M3 rendus visibles). Le persona 3 (parents) et le persona 4 (lieu,
collectif) se rejoignent ici sans le verrou SACEM de S6. Conservé ~75 %. Charge 3-6 p·m
au-dessus de S2 (borne, mode kiosque, intégration d'un catalogue de médiathèque — à
vérifier avec les fournisseurs). Revenus : marchés publics modestes, subventions DRAC /
lecture publique, ateliers ; symbolique élevé. **La meilleure déclinaison « espace public ».**

**S7c. Kit pédagogique « éducation aux algorithmes ».** Sans matériel : une version
d'O2M où l'on manipule le curseur de découverte, la matrice d'ambiance et les poids de la
popularité en voyant la file changer. Conservé ~50 % (M2, M3, M7). Charge 2-3 p·m.
Débouchés : CLEMI, enseignants, médiathèques (S7b), programmes d'éducation aux médias.
Revenus faibles (ateliers, licences d'établissement), symbolique élevé, et **c'est la
version minimale de S5** — un bon test de la thèse avant d'y investir.

**S7d. Extension pour les distributions audio libres (Volumio, moOde, Jellyfin, Navidrome).**
Le moteur de mix (M2, M3, M4) comme greffon sur des lecteurs qui ont déjà la communauté
et le matériel. Conservé ~40 %. Charge 3-4 p·m par cible. Risque : API des hôtes,
maintenance. Revenus nuls, notoriété technique. À envisager après S7a si la communauté
répond.

**S7e. Recherche et jeu de données.** Publier, anonymisé, l'historique du foyer (102 542
écoutes, plusieurs années, avec strates, mood, complétion) et les résultats du curseur de
découverte. Conservé : M10 et M3. Charge 1 p·m. Intérêt : rare par sa durée et sa
granularité (position d'arrêt, reprise), même s'il ne couvre qu'un foyer. Débouché :
collaboration avec un laboratoire (IRCAM, équipes MIR), crédibilité pour S3 et S4.

**S7f. Livres audio.** Un type et un motif dédiés (reprise par chapitre, strate « en
cours »), sur des sources sans DRM (LibriVox, achats). Petit chantier (0,5 p·m), qui rend
la promesse du pitch tenable et renforce S2 et S5.

**S7g. Intégration domotique (Home Assistant, Music Assistant et consorts).** Exposer les
boîtes, le curseur de découverte et l'ambiance comme entités pilotables par une
domotique, et recevoir d'elle le contexte (présence, pièce, tags NFC du téléphone) qui
manque au `herenow:`. Étude détaillée au §14 : 0,5 à 1 p·m pour un pont MQTT + intégration
Home Assistant, canal de diffusion majeur vers le public libriste.

### 12.3 Matrice de synthèse

| Scénario | Conservé | Charge utile | Verrou principal | Revenus | Symbolique | Verdict |
|---|---|---|---|---|---|---|
| S1 App Spotify | ~15 % | 6-9 p·m, non réutilisable | politique Spotify, par construction | 0 | faible | **Abandonner** |
| S2 Kit libriste | ~85 % | 3-6 p·m, socle commun | spotdl à retirer ; support | faible | élevé | **Faire en premier** |
| S3 Conseil plateformes | ~10 % code / 100 % savoir | 1-2 p·m | crédibilité, pas de protection | possible, improbable | moyen-fort | Après publication |
| S4 Radio France / FIP | ~40 % / 100 % savoir | 1-2 p·m | CGU API, institution | indirect | **très élevé** | **Chercher en parallèle** |
| S5 Service app + éducation | ~60 % | 12-24 p·m, équipe | financement, catalogue musical | freemium + public | **maximal** | Moyen terme, conditionné |
| S6 Juke-box premium | ~70 % | 6-12 p·m | licence B2B | **récurrent** | moyen | Conditionnel, sonder d'abord |
| S7a Paquets open source | M2-M3 | 0,5-3 p·m | aucun | 0 | fort (technique) | **Immédiat** |
| S7b Médiathèques | ~75 % | 3-6 p·m sur S2 | intégration catalogue | modeste, public | élevé | **Meilleur « espace public »** |
| S7c Kit pédagogique | ~50 % | 2-3 p·m | aucun | faible | élevé | Test de la thèse S5 |
| S7d Greffon Volumio etc. | ~40 % | 3-4 p·m / cible | API hôtes | 0 | notoriété | Après S7a |
| S7e Recherche / données | M10, M3 | 1 p·m | anonymisation | 0 | crédibilité | Avec S7a |
| S7f Livres audio | +M5 | 0,5 p·m | aucun | — | tient la promesse | Avec S2 |
| S7g Domotique (HA / MQTT) | ~100 % + contexte | 0,5-1 p·m | aucun | 0 | fort (canal HA) | **Avec S2, tôt** (§14) |

### 12.4 Lecture croisée et séquence proposée

Trois constats se dégagent du croisement :

1. **Les modules indépendants de Spotify sont les plus mûrs** (M3, M5, M10) et ils
   portent les scénarios au meilleur rapport effort / bénéfice (S4, S7a, S7e). Les
   modules dépendants de Spotify (données de M1, M6) portent les scénarios fermés (S1) ou
   fragiles (S2 avec spotdl). La désensibilisation n'est pas une perte, c'est un tri.
2. **Le revenu et le symbolique sont anticorrélés.** Le seul scénario à revenu récurrent
   clair (S6) est verrouillé par la licence et peu différenciant symboliquement ; les
   scénarios à fort capital symbolique (S4, S5, S7b) vivent de financements publics ou
   indirects. Le projet a un profil **d'intérêt général**, et son portage (association,
   coopérative, adossement à une institution) devrait l'assumer plutôt que le contredire.
3. **Un socle commun sert tout le reste** : S2 sans spotdl, avec un onboarding et une
   sécurité correcte, est le prérequis technique de S4, S5, S6 et S7b. Chaque mois passé
   dessus est utile quel que soit le scénario retenu ensuite.

Séquence sur douze mois, sans financement externe préalable :
- **Mois 1-2** — S7a (librairie popularité, article « un moteur dont on lit les règles »),
  S7f (livres audio), retrait de spotdl du périmètre distribuable. Premier test de traction
  (§11-6).
- **Mois 2-6** — S2 : image, installateur, onboarding, documentation. En parallèle S4 :
  démonstrateur « sujet + FIP » et prise de contact Radio France ; point juridique sur
  l'API. Un courriel de sondage à un fournisseur B2B pour S6.
- **Mois 6-9** — S7c (kit pédagogique) et premier contact médiathèques (S7b) : tester la
  thèse « éducation aux algorithmes » à petite échelle. S7e si un laboratoire répond.
- **Mois 9-12** — Décision sur S5 à la lumière des retours de S4, S7b, S7c, et recherche
  de financement si la thèse tient. S3 en opportunité si les publications ont porté.

Ce qui reste à vérifier avant d'engager quoi que ce soit : les conditions d'usage de
l'OpenAPI Radio France pour une démonstration publique (S4), l'ouverture d'un catalogue B2B
à un tiers (S6), les modalités d'intégration des catalogues de médiathèques (S7b), et la
politique développeur Tidal (S3).


## 13. Étude : O2M peut-il être une extension Mopidy ?

**Réponse courte : oui, techniquement, et c'est même l'architecture naturelle du projet.
O2M est aujourd'hui un client externe de Mopidy pour des raisons historiques, pas pour
des raisons de fond.** Le chantier est réel mais borné (2 à 3 personne-mois), et il peut
se faire en deux phases dont la première apporte déjà l'essentiel. Ce qui suit détaille
le pourquoi, le comment, les pertes et les gains — à partir du code mesuré le 2 septembre
2026.

### 13.1 Ce qu'est une extension Mopidy

Mopidy est un serveur Python organisé en acteurs (Pykka). Une extension est un paquet pip
qui déclare une classe `Extension` (point d'entrée `mopidy.ext`), un schéma de
configuration lu dans `mopidy.conf` (section `[o2m]`), et enregistre dans le *registry*
une ou plusieurs briques :
- un **frontend** : un acteur qui reçoit le proxy `core` et implémente `CoreListener` —
  il est notifié **en processus** de `track_playback_started/ended/paused`, etc., et
  appelle `core.tracklist.add(...)`, `core.playback.play()`… directement ;
- une **application HTTP** (`http:app`) : des handlers Tornado servis par le serveur web
  de Mopidy sous `/<nom>/`, donc sur le **même port** que l'interface (6680) ;
- des **fichiers statiques** (`http:static`) ;
- un **backend** : un fournisseur de schéma d'URI (`o2m:…`) — bibliothèque, playlists,
  lecture.

Mopidy-Iris est exactement cela : un frontend (`IrisFrontend`), une app HTTP avec sa
propre API et un websocket, des fichiers statiques. Le modèle existe, il est éprouvé, et
c'est celui qu'O2M imite déjà de l'extérieur.

### 13.2 Ce qu'O2M fait aujourd'hui, mesuré

| Aspect | État actuel | Ce que ça devient en extension |
|---|---|---|
| Liaison à Mopidy | `mopidyapi` (websocket JSON-RPC), avec un correctif maison pour rendre le *listener* résilient aux déconnexions (`_install_resilient_ws_listener`) et une construction unique pour ne pas fuir des threads | Le proxy `core` en processus. **Tout le code de résilience websocket disparaît** : plus de reconnexion, plus de thread d'écoute, plus de perte d'événements au redémarrage |
| Appels au cœur | ~130 sites, 30 méthodes distinctes, dominés par `tracklist.get_length` (23), `tracklist.index` (12), `playback.play` (8), `tracklist.get_tl_tracks` (6), `playlists.lookup` (6), `playback.seek` (6) | Mêmes noms, mêmes signatures : `core.tracklist.add(uris=…).get()`. Les objets renvoyés sont des `mopidy.models` (attributs `tl_track.track.uri`) là où `mopidyapi` renvoie des tuples nommés à l'accès identique. Portage **mécanique** |
| Événements écoutés | Trois : `track_playback_started`, `track_playback_ended`, `track_playback_paused` | Trois méthodes de `CoreListener`. `time_position` arrive nativement |
| API HTTP | **91 routes Flask** (2 400 lignes dans `main.py`), CORS, `flask_session` pour la session d'édition OAuth, port 6681 | Handlers Tornado sous `/o2m/api/…`, même origine que l'UI → plus de CORS, plus de second port à exposer via Caddy, plus de détection de `base_url` dans `o2m.js`. La session signée est à réécrire (cookie sécurisé Tornado) |
| UI | `mood.html` (Basic/Full), `stats.html`, `tag_features.html`, service worker, manifest — servis par Flask | `http:static` : servis par Mopidy sous `/o2m/`. Inchangés |
| Injection dans Iris | `o2m.js` et `o2m.css` **copiés dans `dist-packages/mopidy_iris/static/`** par le Dockerfile | Inchangé : Iris n'a pas de système de greffons, l'injection reste un contournement. Mais le besoin diminue : O2M a déjà sa propre UI, Iris ne sert plus qu'à parcourir la bibliothèque et à relayer l'auth Spotify |
| Threads de fond | ~13 (`warmup`, planificateur de popularité, enrichissement, catalogue podcast, redémarrages) | Identiques, lancés depuis `on_start()` de l'acteur. Un acteur Pykka ne doit pas bloquer : les traitements longs restent en threads, comme aujourd'hui |
| NFC | `pyscard` en thread, déclenche `box_action` | Un thread du frontend. Rien ne change |
| Base de données | Peewee, MySQL ou SQLite, initialisée à l'import | Inchangée. `create_conf_files.sh` devient inutile : la configuration passe par `mopidy.conf` |
| Redémarrages | `/api/restart_mopidy` et `/api/restart_o2m` appellent `docker compose restart` | **Impossibles depuis l'intérieur du processus.** À remplacer par une réinitialisation d'état (`reset_o2m` existe déjà) et par la supervision externe (systemd, Docker) |
| Services voisins | `spotdl/cache.py` appelle l'API O2M par HTTP | Inchangé, l'URL change |
| Versions | Mopidy 3.4.2, Python 3.10, Pykka 2.0.3, Tornado 6.1 | Compatibles. Mopidy 4 est en préparation (Python ≥ 3.11, Pykka 4 ; changements d'API d'extension à vérifier) |

### 13.3 Ce qu'on gagne

1. **Installation en une ligne sur tout Mopidy existant.** `pip install Mopidy-O2M`, une
   section `[o2m]` dans `mopidy.conf`, et O2M tourne sur l'image Raspberry Pi officielle
   de Mopidy, sur un Volumio, sur un serveur maison. C'est **le raccourci du kit S2** : la
   documentation d'installation, les paquets Debian, la communauté et le catalogue
   d'extensions de mopidy.com existent déjà — O2M s'y insère au lieu de tout refaire.
2. **Fin de la fragilité websocket.** La couche la plus rustinée du code actuel
   (reconnexion, fuite de threads, événements perdus au redémarrage, `reload_active_boxes`
   à la reconnexion) devient sans objet.
3. **Une seule origine, un seul port.** L'UI et l'API sortent de Mopidy sur 6680 : Caddy
   ne proxifie plus qu'un service, `o2m.js` n'a plus à deviner où est l'API, et le
   problème d'auth temporaire en HTTP (mémoire du projet) se simplifie.
4. **Une configuration unique.** Plus de `o2m.conf` généré depuis les variables
   d'environnement ; le schéma de configuration de Mopidy valide les valeurs et documente
   les clés.
5. **Visibilité.** Une extension listée sur mopidy.com est la forme la plus lisible du
   « vecteur notoriété » du §8-C, et la seule qui apporte des installations réelles.
6. **Une porte vers les clients tiers.** Un **backend** `o2m:` optionnel exposerait les
   boîtes comme playlists ou dossiers parcourables : n'importe quel client MPD ou Iris
   verrait « Auto morning » et pourrait le lancer. C'est le module M1 rendu visible dans
   tout l'écosystème sans écrire d'interface. (Attention : une boîte est un comportement
   dynamique, pas une liste statique ; la lecture d'un `o2m:box:<uid>` devrait déclencher
   `box_action`, ce qu'un backend peut faire mais que le modèle Mopidy ne prévoit pas
   nativement — prototype à faire avant de promettre.)

### 13.4 Ce qu'on perd, ou ce qu'il faut accepter

1. **L'isolation des pannes.** Aujourd'hui O2M peut planter et redémarrer sans couper la
   musique, et inversement. En extension, une exception non rattrapée dans l'acteur O2M
   arrête cet acteur **en silence** (comportement Pykka) pendant que Mopidy continue : il
   faut un garde-fou de supervision interne (rattraper au niveau du dispatch d'événement,
   relancer les threads morts, exposer `/o2m/health`). Une erreur dans les threads de fond
   ne tue pas Mopidy, mais une erreur à l'import ou dans `setup()` empêche Mopidy de
   démarrer. Le coût en discipline de code est réel.
2. **Le redémarrage ciblé.** Plus de `restart_o2m` : on redémarre Mopidy, donc la
   lecture. À compenser par une réinitialisation d'état complète en processus.
3. **La liberté de pile web.** Flask et son écosystème sortent ; Tornado impose ses
   handlers et sa gestion de session. C'est le gros du portage.
4. **Le couplage aux versions de Mopidy.** Une extension vit au rythme de Mopidy (la
   transition vers Mopidy 4 imposera des adaptations) et de Python. Le client externe
   n'avait qu'à parler JSON-RPC.
5. **Le déploiement Docker actuel se simplifie mais change** : un conteneur au lieu de
   deux, image `mopidy` à reconstruire à chaque évolution d'O2M (aujourd'hui seul
   `o2m.js` impose une reconstruction ; Python et `mood.html` sont *live*). En
   développement, monter le paquet en volume rétablit le rechargement.

### 13.5 Chiffrage en deux phases

**Phase 1 — « même code, dans le processus »** (3 à 5 semaines).
- Écrire `Extension`, le schéma de configuration, un frontend `O2mFrontend(CoreListener)`.
- Remplacer `MopidyAPI` par un **adaptateur** qui expose la même interface
  (`mopidy.tracklist.add(...)` → `core.tracklist.add(...).get()`) : le reste du code ne
  change pas, les ~130 appels restent tels quels.
- Les trois événements deviennent des méthodes de l'acteur qui appellent le code existant.
- Flask continue de tourner **dans un thread de l'extension**, sur son port : ce n'est pas
  élégant mais c'est légal, et cela isole la phase 2.
- Supprimer `_install_resilient_ws_listener`, `create_conf_files.sh`, les routes de
  redémarrage Docker.
- Résultat : un paquet installable, la fragilité websocket éliminée, zéro régression
  fonctionnelle, et la possibilité de **vérifier** le comportement Pykka sur la vraie
  charge (Raspberry Pi) avant d'aller plus loin.

**Phase 2 — « intégration complète »** (5 à 8 semaines).
- Porter les 91 routes en handlers Tornado sous `/o2m/api/`, réécrire la session d'édition
  OAuth, servir les statiques via `http:static`, retirer Flask, CORS et le port 6681.
- Adapter `o2m.js`, `sw.js`, `manifest.json` à la nouvelle origine ; simplifier Caddy.
- Optionnel : backend `o2m:` exposant les boîtes (prototype d'une semaine d'abord).
- Publier sur PyPI, référencer sur mopidy.com, documenter l'installation sur l'image Pi
  officielle.

Total : **2 à 3 personne-mois**, la phase 1 seule valant déjà l'effort. Le travail est
**réutilisable** dans tous les scénarios qui gardent le socle Mopidy (S2, S4, S6, S7b,
S7d) ; il ne sert pas S5 si celui-ci abandonne Mopidy pour une application autonome — mais
S5 n'est pas à l'ordre du jour avant douze mois.

### 13.6 Ce que cela change dans l'analyse du §12

- **S2 (kit)** : l'extension est la meilleure forme du kit. Au lieu d'une image O2M à
  maintenir (Docker, compose, deux services, fichiers de conf générés), on livre un paquet
  pip et une page d'installation qui s'appuie sur la documentation Mopidy. La charge de S2
  baisse d'autant que celle du §13 monte : l'un remplace en partie l'autre.
- **S7d (greffon Volumio, moOde)** : ces distributions embarquent ou acceptent Mopidy ;
  une extension Mopidy y est installable sans travail spécifique. S7d devient un
  sous-produit du §13 plutôt qu'un chantier par cible.
- **§8-C** : le « contresens » est levé. Ce n'est pas un repackaging, mais ce n'est pas
  non plus une réécriture : c'est un **déplacement de frontière**, mécanique dans sa
  première phase.
- **Le mot de vigilance** : Mopidy est un écosystème qui vieillit (Iris peu maintenu,
  Mopidy-Spotify en alpha depuis longtemps, Mopidy 4 attendu). S'y ancrer davantage est
  le bon choix pour les douze prochains mois et pour le public libriste ; ce n'est pas un
  engagement de long terme, et le cœur d'O2M (M1-M5, M10) doit rester indépendant de
  Mopidy dans son code — ce qu'il est déjà, l'adaptateur de la phase 1 étant la seule
  couture.

**Recommandation** : engager la phase 1 dès le début du kit S2 (mois 2 de la séquence du
§12.4), décider la phase 2 au vu du comportement réel sur Raspberry Pi.


## 14. Home Assistant, Music Assistant et consorts : rassembler ou partager les briques ?

La question se pose dans les deux sens. **Rassembler** : la domotique du foyer devient le
tableau de bord d'O2M (boîtes, curseurs, scènes, voix, présence). **Partager** : certaines
briques d'O2M existent déjà chez elle, et certaines briques qui manquent à O2M y sont
natives. Le tableau ci-dessous croise les modules du §12.1 avec ce que Home Assistant (HA)
et Music Assistant (MA, le gestionnaire musical de l'écosystème HA) proposent, à ma
connaissance en septembre 2026 — à vérifier sur les versions courantes.

### 14.1 Croisement module par module

| Module O2M | Home Assistant | Music Assistant | Lecture |
|---|---|---|---|
| M1 Boîtes, cascades, motifs | Scènes et scripts (statiques) | Playlists, favoris ; pas de « boîte » comportementale | **O2M apporte** ce qui manque : le contenu comme comportement dosé |
| M2 Moteur de mix / dosage | — | File d'attente, lecture aléatoire, « don't stop the music » (enchaînement par similarité de fournisseur) | **O2M apporte** ; MA n'a ni curseur de découverte ni ambiance |
| M3 Strates, popularité ouverte | — | — | **O2M apporte** |
| M4 Mood / genres | — | Métadonnées des fournisseurs | **O2M apporte** |
| M5 Contenu parlé (RSS, RF, sujets, reprise) | — | Podcasts (fournisseurs RSS), livres audio via **Audiobookshelf**, radios via Radio Browser | MA a la **largeur** (livres audio !), O2M la **profondeur** (sujets, reprise fine, pré-pub, budget) |
| M6 Résilience locale | — | Fichiers locaux, Jellyfin, Plex, Subsonic/Navidrome comme fournisseurs | MA couvre légitimement ce qu'O2M faisait via spotdl |
| M7 UI Basic / Full | Tableaux de bord Lovelace, app compagnon, **Assist** (voix locale) | Interface web et carte HA | HA apporte les surfaces de contrôle que la PWA d'O2M ne peut pas offrir (voix, écrans muraux, présence) |
| M8 Diffusion | Intégrations **Snapcast**, MPD (donc Mopidy-MPD), Chromecast, Sonos, AirPlay, DLNA | Lecteurs : Snapcast, Chromecast, Sonos, AirPlay, Squeezelite, lecteurs HA | Même pile Snapcast : **O2M et HA se branchent déjà sur le même serveur** |
| M9 Tangible NFC | **Natif** : tags NFC scannés par l'app compagnon (téléphone) ou lecteurs ESPHome (PN532), événement `tag_scanned` → automatisation | — | HA fait mieux et moins cher : n'importe quel téléphone est un lecteur, n'importe quelle ESP32 à 5 € en fait une borne |
| M10 Historique, habitudes | Historique d'états (pas d'écoute par piste) | — | **O2M apporte**. En retour, HA connaît la **présence** et la **pièce** : le « ici » que `herenow:` n'a pas (il ne lit que l'heure) |
| Fournisseurs de contenu | — | Spotify (via librespot), Tidal, Qobuz, YouTube Music, Apple Music, Deezer (à vérifier), locaux, Plex, Jellyfin, radios, podcasts, livres audio | **MA a résolu la largeur de catalogue que Mopidy ne suit plus** (Mopidy-Spotify en alpha, pas de Deezer, Tidal communautaire) |

Deux constats nets. **Ce qu'O2M possède et qu'eux n'ont pas** : le cœur (M1-M5, M10), c'est-
à-dire exactement ce que le §12 identifie comme les modules mûrs et indépendants. **Ce
qu'ils possèdent et qu'O2M a bricolé** : le tangible (M9), la largeur de fournisseurs, les
surfaces de contrôle, la présence. La complémentarité est presque parfaite — et elle
confirme le tri du §12 : garder le cœur, déléguer la périphérie.

### 14.2 Trois montages possibles

**A. HA pilote O2M (rassembler, sens domotique → O2M).** O2M expose ses commandes comme
entités : un interrupteur par boîte, un `number` pour le curseur de découverte, deux
`number` pour énergie et ambiance, un `select` pour le mood à cinq crans, un capteur
« piste en cours / strate / popularité ». Techniquement : un **pont MQTT avec découverte
automatique** (HA crée les entités seul) — ce qui rend le pont aussi compatible avec
openHAB, Jeedom, Domoticz, Node-RED — puis, si la demande existe, une **intégration HACS**
avec `config flow`. Ce qui devient possible sans une ligne de code côté O2M :
- scanner un tag NFC avec le téléphone → activer une boîte (le tangible **sans lecteur
  dédié**, y compris hors du foyer via l'app) ;
- « tout le monde est parti » → pause et fermeture des boîtes ; « première personne rentre
  après 18 h » → boîte du soir ;
- Assist : « lance la boîte du matin », « plus de découverte » en voix **locale** ;
- un écran mural avec les quatre interrupteurs de la vue Basic ;
- le curseur de découverte piloté par une scène (dîner = DL 2, ménage = DL 8).
Effort : **1 à 2 semaines** pour le pont MQTT, 2 à 4 semaines pour l'intégration HACS.
Conservé : 100 % d'O2M, plus du contexte. Risque nul. Revenus nuls. **Symbolique fort** :
HA est la plus grande communauté d'auto-hébergement domestique ; un dépôt HACS est un canal
de diffusion sans équivalent pour S2.

**B. HA nourrit O2M (partager, sens domotique → moteur).** Le contexte remonte dans le
moteur : la **pièce** où l'on est et **qui** est présent deviennent des dimensions de
`Stats_Raw` (aujourd'hui : heure seulement). `herenow:` devient vraiment « ici et
maintenant » : ce qu'on écoute dans la cuisine le samedi matin quand les enfants sont là.
C'est une extension légère du modèle (colonnes additives, migration compatible) et une
entrée MQTT dans O2M. Effort : 2 à 3 semaines après A. Ce montage est aussi le seul
chemin réaliste vers la **dimension collective** du pitch (« une boîte par personne, un
dosage pour la pièce ») sans construire de comptes : la présence est l'identité.

**C. Music Assistant remplace Mopidy comme couche de lecture (partager, sens
fournisseurs).** O2M garde son cœur et parle à MA au lieu de Mopidy : file d'attente,
événements de lecture, recherche et résolution d'URIs passent par l'API websocket de MA
(client Python officiel). Ce qu'on y gagne : Tidal, Qobuz, YouTube Music, Jellyfin,
Navidrome, **livres audio via Audiobookshelf** (S7f offert), radios, podcasts — soit la
réponse au « catalogue amputé » qui affaiblit S2 et S5 — et une couche de lecture
activement maintenue. Ce qu'on y perd : le travail du §13 (extension Mopidy) ne s'y
transpose pas ; l'écosystème MA est jeune, HA-centrique et change vite ; Spotify y passe
par librespot avec les mêmes fragilités et la même zone grise d'usage que chez nous. Effort :
**2 à 3 personne-mois** (nouvel adaptateur, modèle d'événements différent, tests), plus une
veille permanente. Conservé : le cœur (~60 %), M7 ; M8 et M9 délégués.

### 14.3 Ce que cela change dans le dossier

- **A est à faire tôt et sans hésiter**, en même temps que le kit S2 : coût dérisoire,
  canal de diffusion majeur, et il donne au tangible une version gratuite (le téléphone)
  qui lève le frein matériel listé au §6.
- **B est la voie la plus courte vers le collectif** du pitch, et elle donne enfin un
  sens au « ici » du `herenow:`.
- **C est l'alternative stratégique au §13.** Les deux répondent à la même faiblesse
  (Mopidy vieillit), par des chemins opposés : s'ancrer plus profondément dans Mopidy, ou
  s'en détacher pour MA. Ils ne sont pas cumulables à court terme. Le choix dépend d'une
  question que l'étape 3 du §11 doit poser aux libristes rencontrés : *« votre serveur
  audio, c'est Mopidy, Music Assistant, ou autre chose ? »* Tant que la réponse n'est pas
  connue, la bonne décision technique est la même que celle du §13.6 : garder le cœur
  d'O2M **indépendant de la couche de lecture**, avec un adaptateur — Mopidy aujourd'hui,
  MA demain si la communauté y est.
- **La place d'O2M se précise** : ni un lecteur, ni une domotique, mais le **cerveau
  éditorial** entre les deux — celui qui décide *quoi* jouer, dans quel ordre, avec quel
  dosage, et qui explique pourquoi. C'est une position que personne n'occupe dans
  l'écosystème HA/MA, et c'est exactement le périmètre des modules mûrs (M1-M5, M10).
