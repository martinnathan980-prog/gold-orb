# Mode d'emploi — le classeur, semaine après semaine

Ce document dit **ce que vous faites, physiquement, dans le classeur**, une
fois le tableau de bord installé (menu **Suivi FWD** visible dans le classeur).
Rien ne se saisit dans la page : le classeur est la mémoire, la page est la
lecture.

En une phrase : **un onglet par contrat, l'extract GATES dedans tel quel,
et une fois par semaine un seul geste — Suivi FWD → Importer les exports
GATES et SEE…, tous les exports choisis d'un coup, Importer** : chacun va
dans l'onglet de son contrat et le relevé de la semaine est archivé dans la
foulée. Le reste est automatique.

---

## 1. Ouvrir le tableau de bord

1. Ouvrir le classeur Google Sheets. Le menu **Suivi FWD** est à droite de
   « Aide » (s'il manque : **F5**, attendre dix secondes).
2. **Suivi FWD → Ouvrir le tableau de bord.** À la première ouverture, Google
   demande une autorisation : Autoriser, choisir votre compte, « Autoriser »
   encore.
3. La page s'ouvre dans une fenêtre. Tant que le classeur est vide, elle
   le dit — **« Le classeur n’a pas encore de plans »** — et rappelle les trois gestes
   ci-dessous. Elle ne montre jamais rien de fabriqué : seulement vos
   données.
4. **Plus rapide depuis le débrief 18** : le classeur n'est relu que s'il a
   changé depuis la dernière ouverture (le script garde ce qu'il a lu, et
   l'oublie dès qu'une cellule change, qu'on archive, qu'on ajoute, supprime
   ou renomme un onglet, des lignes ou des colonnes — et chaque jour) ; le
   tableau des plans se dessine par tranches d'une soixantaine de lignes, la
   suite en descendant. Si un chiffre paraît ne pas suivre le classeur (après
   avoir restauré une ancienne version du classeur, par exemple) : ajouter
   `?frais=1` au bout du lien `…/exec` — tout ce qui était gardé est oublié.
5. Les ouvertures de la page sont **comptées, sans nom ni adresse** (le pied
   de la page le dit) : **Suivi FWD → Diagnostic** donne, par semaine, le
   nombre d'ouvertures et de personnes distinctes.

### Recoller une livraison (quand je vous envoie les fichiers)

Le tableau de bord tient en **quatre fichiers**, et ils vont **ensemble** :
`Code`, `Index`, `Styles`, `Javascript`. À chaque livraison, **recollez les
quatre**, même si un seul semble avoir changé : un fichier laissé à la
livraison d'avant suffit à laisser la page blanche.

1. Extensions → Apps Script. Pour chacun des quatre fichiers : l'ouvrir à
   gauche, **Ctrl+A, Suppr**, puis coller le `.txt` du même nom **en entier**
   (dans le `.txt` : Ctrl+A, Ctrl+C), **Ctrl+S**.
2. **Si vous ouvrez la page par un lien `…/exec`** (application web) : ce lien
   sert la version *déployée*, pas celle que vous venez de coller. Déployer →
   Gérer les déploiements → ✏️ → Version : **Nouvelle version** → Déployer.
   Le menu Suivi FWD → Ouvrir le tableau de bord, lui, prend toujours le code
   enregistré. Dans ce même écran, vérifier **« Qui a accès »** : les
   utilisateurs de votre organisation (Airbus), **jamais « Tout le monde »**
   (n'importe qui sur internet, sans connexion).
3. Vérifier : **en bas de la page, « Livraison xxxxxxx »** — le numéro que je
   donne avec les fichiers. (Quand je ne corrige que `Code`, la livraison ne
   change pas : on ne recolle que `Code`.) Suivi FWD → **Diagnostic** le confirme :
   « ✓ Livraison xxxxxxx : Code, Index, Styles et Javascript concordent, et
   sont entiers. »
4. **Un nouvel article du menu Suivi FWD** n'apparaît qu'une fois le
   classeur rechargé : revenir à l'onglet du classeur, **F5**, attendre dix
   secondes.

Si un fichier ne concorde pas, **la page le dit elle-même**, en tête : « Les
fichiers du tableau de bord ne concordent pas. Index ne vient pas de la même
livraison… » ; et si elle ne peut pas s'afficher du tout, un cadre « La page
n'a pas pu s'afficher » (ou « n'a pas pu démarrer ») dit pourquoi et quoi
recoller — plus jamais un squelette vide sans un mot.

## 2. Mettre un contrat : l'extract GATES, dans un onglet

Un contrat = **un onglet** du classeur, qui porte **le nom du contrat** et
son export GATES tel quel. Tout le reste se déduit de là. Le plus simple :
la fenêtre d'import, qui crée l'onglet elle-même.

1. Dans GATES, exporter la liste du contrat en **Excel** (`.xlsx`, de
   préférence au CSV : l'export Excel garde les cellules fusionnées de la
   ligne des groupes, et c'est par le groupe « HDK AA 011 » que la page
   reconnaît la bonne colonne « Avancement Définition Electrique » parmi les
   vingt-sept). **Ne pas l'ouvrir** : le laisser tel que téléchargé.
2. Dans le classeur : **Suivi FWD → Importer les exports GATES et SEE…**
   (absent juste après avoir recollé `Code` : **F5** sur le classeur, dix
   secondes).
3. **Choisir les fichiers…** — l'export —, ou le glisser dans le cadre
   pointillé de la fenêtre. Elle le lit sur le poste (il ne part nulle part),
   le reconnaît — étiquette **GATES** — et dit ce qu'elle y trouve :
   « 186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules
   fusionnées ».
4. Pour un contrat que le classeur n'a pas encore, elle propose **« Nouveau
   contrat… »**, nommé d'après la ligne des groupes (« HDK AA 011 » →
   `HDK`) : garder ce nom ou en taper un autre — c'est le nom de l'onglet,
   celui que la page affichera. Un nom déjà pris ou réservé est refusé à
   mesure qu'on le tape. Sous la ligne : « Créera l'onglet « HDK » : un
   nouveau contrat, rangé après les autres ».
5. **Importer**, et **ne pas fermer la fenêtre avant la fin** (elle le
   rappelle). L'export est posé **tel quel** : chaque ligne à son numéro,
   chaque colonne à sa place, les cellules fusionnées de la ligne des groupes
   recréées — exactement ce qu'un Ctrl+A / Ctrl+V depuis Excel aurait posé.
   Puis la fenêtre dit ce que la page y lit : « ✓ « export.xlsx » → onglet
   « HDK » créé (nouveau contrat) : 186 plans, colonne suivie HDK AA 011 ›
   Avancement Définition Electrique, concept harnais lu ».
6. **Suivi FWD → Ouvrir le tableau de bord** (le fermer d'abord s'il était
   ouvert). La page est sur vos plans.

**À la main, par un collage** — si la fenêtre ne peut pas lire le fichier
(un export protégé, par exemple) : ouvrir l'export dans Excel, **Ctrl+A**,
**Ctrl+C** — tout l'extract, sans rien trier ni retirer : les lignes de titre
au-dessus, la ligne des groupes, la ligne des en-têtes, les colonnes vides.
Dans le classeur, l'onglet du contrat : pour le **premier**, l'onglet de
départ (« Feuille 1 ») renommé du nom du contrat (double-clic sur son nom) ;
pour les suivants, **+** en bas à gauche, puis renommer de même. Cellule
**A1**, **Ctrl+V**, attendre que Google finisse de coller (quelques secondes
pour 138 colonnes). Un onglet resté vide n'est pas pris pour un contrat.

Ce que la page a compris de l'extract se lit dans **Suivi FWD → Diagnostic**
(les colonnes reconnues, le nombre de plans, la ligne « ✓ Avancement FWD :
colonne « Avancement Définition Electrique », groupe « HDK AA 011 » — celle
de CONFIG.COLONNE_FWD »). Un onglet qui n'a que ses en-têtes y est marqué
« ⚠ L'onglet ne porte aucun plan (en-têtes seuls) : y importer l'export
GATES (menu Suivi FWD → Importer les exports GATES et SEE…) ou le coller en
A1. »
**Envoyez-moi ce texte** : c'est lui qui me dit si le modèle de colonnes
tombe juste. Le texte se copie à la souris dans la boîte ; s'il est trop
long, il est aussi dans **Extensions → Apps Script → Exécutions**, dernière
exécution de `diagnostic`.

À savoir :

- Le premier onglet (dans l'ordre des onglets, de gauche à droite) est le
  contrat sur lequel la page s'ouvre. On les réordonne en les faisant
  glisser.
- Un onglet **masqué** n'est pas un contrat, un onglet **vide** non plus. Les
  onglets `Historique_FWD_…` sont créés et masqués par l'outil : ne pas y
  toucher, ne pas les renommer.
- Un seul extract par onglet. Coller le même extract dans un second onglet
  donnerait deux « contrats » identiques.
- L'import **remplace l'onglet entier** (c'est ce qui le rend sûr : l'ancien
  ne s'en va qu'une fois le nouveau complet). Une mise en forme ajoutée à la
  main dans l'onglet du contrat — largeurs de colonnes, volets figés, filtre,
  couleurs — ne suit donc pas, et une formule d'un autre onglet qui pointait
  sur lui serait à refaire (`#REF!`). Le tableau de bord, lui, retrouve
  l'onglet par son nom, et l'historique ne bouge pas.
- Si un jour l'extract change de colonnes et que le Diagnostic ne trouve
  plus la colonne suivie après un collage : le réimporter par la fenêtre
  (l'onglet est remplacé en entier, cellules fusionnées comprises) ; à la
  main, supprimer l'onglet (clic droit → Supprimer), le recréer sous le
  **même nom**, puis coller. L'historique, nommé d'après l'onglet, est
  conservé.

## 3. Un deuxième contrat, un troisième

Même geste : son export dans la fenêtre d'import (on peut le mettre avec
ceux des autres contrats). Elle voit qu'il ne partage ses plans avec aucun
contrat du classeur, propose **« Nouveau contrat… »** nommé d'après ses
groupes (« THS AA … » → `THS`), et range le nouvel onglet après les autres.
À la main : un **nouvel onglet** nommé du contrat (`THS`), l'export collé en
A1. Dans la page, un sélecteur **Contrat** apparaît dans le bandeau du haut
dès qu'il y a deux onglets ; il passe de l'un à l'autre sans recharger.

Un classeur commencé avec un seul contrat garde parfois deux onglets sans
nom de contrat : son historique dans l'ancien onglet masqué
`Historique_FWD`, et sa base SEE dans un onglet `SEE` tout court. Avec deux
contrats, ni l'un ni l'autre ne serait plus lu. Quand **la fenêtre d'import
crée le deuxième contrat**, elle les renomme d'elle-même au nom du premier
— `Historique_FWD_HDK`, `SEE HDK` : ils ne pouvaient être qu'à lui — et le
dit sur la ligne du fichier (« l'onglet « SEE » devient « SEE HDK » »).

Si le deuxième contrat arrive **à la main** (un onglet collé), rien n'est
renommé : la page le dit au-dessus de la barre (« L'ancien onglet
d'historique « Historique_FWD » (12 relevés) n'est rattaché à aucun
contrat… »), le Diagnostic aussi, et l'archivage des contrats qui n'ont pas
encore d'historique est refusé tant qu'il n'est pas rattaché — pour ne pas
couper l'historique en deux. Le message de refus nomme le contrat qui a
produit ces relevés quand il le sait (ses plans recoupent ceux du dernier
relevé). Le geste : Affichage → Onglets masqués, renommer `Historique_FWD`
en `Historique_FWD_HDK` (le nom de ce contrat-là — jamais celui du nouveau),
et `SEE` en `SEE HDK`.

## 4. Chaque semaine : importer les exports, le relevé suit

C'est le geste qui construit l'historique — la courbe, la fin estimée et le
journal des changements n'existent que par lui.

1. Refaire l'export GATES de **chaque contrat** (et, quand il en faut un
   plus récent, l'export SEE de chaque contrat, § 5). Ils arrivent dans
   **Téléchargements** : **ne pas les ouvrir**.
2. Dans le classeur : **Suivi FWD → Importer les exports GATES et SEE…**
3. **Choisir les fichiers…**, puis, dans la fenêtre de Windows qui s'ouvre
   (dossier **Téléchargements**), les prendre **tous d'un coup** :
   - **Ctrl+clic** sur chacun : un clic sur le premier, puis la touche
     **Ctrl** maintenue pendant les clics sur les suivants ;
   - ou, s'ils se suivent dans la liste (triée par date, les derniers
     téléchargés ensemble), un clic sur le premier et **Maj+clic** sur le
     dernier ;
   - ou **Ctrl+A** pour tout le dossier — seulement pour un dossier qui ne
     contient que les exports de la semaine (dans Téléchargements, il
     prendrait tout le reste) ; un tableau qui n'est pas un export est
     marqué ✗ dans la liste, le lien **Retirer les fichiers en erreur** les
     enlève d'un coup, et ce qui n'est pas un tableau est laissé de côté ;
   - puis **Ouvrir**.

   Autre façon : sélectionner les fichiers dans l'Explorateur de Windows et
   les **glisser** dans le cadre pointillé de la fenêtre. Dix fichiers au
   plus à la fois (les suivants sont laissés de côté, et nommés : les
   importer ensuite) ; un fichier choisi deux fois n'est pris qu'une fois.
4. Chaque fichier est lu tout de suite, avec sa barre, puis rangé : une
   étiquette **GATES** ou **SEE**, le contrat retrouvé et pourquoi (« 186
   plans sur 186 déjà dans « HDK » »), l'onglet visé (« Remplacera l'onglet
   « HDK » — l'ancien ne s'en va qu'une fois tout reçu ; son historique est
   gardé »). Un contrat **à vérifier**, écrit en ambre, se choisit dans la
   liste de la ligne. Pour un export **GATES**, rien n'est choisi d'office :
   tant qu'un fichier attend quelque chose (un contrat à choisir, un nom à
   vérifier, deux fichiers pour le même onglet…), **Importer** reste éteint
   et la fenêtre dit quoi, juste sous la liste. Pour un export **SEE**, la
   fenêtre propose d'office un contrat — même quand il n'y en a qu'un —, et
   écrit « à vérifier » quand rien dans le fichier ne le confirme :
   **Importer reste allumé**, et le fichier partirait dans ce contrat.
   Regarder alors l'onglet nommé sous la ligne (« Remplacera l'onglet
   « SEE HDK » »), et changer le contrat si ce n'est pas le bon.
5. La case **« Archiver le relevé de la semaine S40 pour les contrats
   importés »** est cochée : la laisser (elle n'apparaît qu'avec un export
   GATES dans la liste).
6. **Importer**, et **ne pas fermer la fenêtre avant la fin** (elle le
   rappelle). Les exports GATES passent d'abord, puis ceux de SEE. À la fin,
   une ligne par fichier : « ✓ « export_HDK.xlsx » → onglet « HDK »
   remplacé : 186 plans, colonne suivie HDK AA 011 › Avancement Définition
   Electrique, concept harnais lu. Relevé S40 archivé (186 plans, 52
   validés). » Un fichier en échec (✗) n'arrête pas les autres, et son
   onglet reste tel qu'il était.
7. Rouvrir le tableau de bord : **Suivi FWD → Ouvrir le tableau de bord.**

**Comment la fenêtre retrouve le contrat** d'un export GATES : par ses plans
— le contrat dont l'onglet en a le plus en commun avec le fichier —, sinon
par le nom du contrat écrit au-dessus des en-têtes (« HDK AA 011 »), sinon
par le nom du fichier ; un export qui ne ressemble à aucun contrat propose
« Nouveau contrat… ». Deux fichiers pour le même onglet (l'export de la
semaine dernière resté dans Téléchargements, souvent — « Export GATES.xlsx »
et « Export GATES (1).xlsx ») : chaque ligne dit la date de son fichier
(« du 3 oct. 14:20 »), et la fenêtre attend qu'on en retire un — **garder le
plus récent**, celui qu'elle nomme (« Garder le plus récent, « Export GATES
(1).xlsx » (du 3 oct. 14:20) : retirer l'autre »), et **Retirer** l'autre
sur sa ligne.

Après un import, on peut en lancer un autre **dans la même fenêtre** : elle
relit d'abord la liste des contrats, donc un contrat créé au tour d'avant
est proposé, et son export SEE retrouvé par ses plans.

**Le relevé est archivé contrat par contrat**, pour les seuls contrats
importés : une ligne datée de la semaine dans l'onglet d'historique du
contrat (`Historique_FWD_HDK`, créé et masqué tout seul au premier
archivage). Importer de nouveau dans la même semaine **remplace** la ligne
de la semaine, il n'en ajoute pas une seconde. Si l'archivage refuse
(l'export importé est celui d'une semaine déjà archivée, la colonne suivie
est introuvable…), la ligne du fichier le dit en ⚠ — l'import, lui, est fait.

**Un export identique à un relevé plus ancien** est refusé par prudence :
c'est presque toujours l'export de la semaine dernière, pris par erreur.
Mais il peut être juste — GATES est vraiment revenu à cet état (une
validation retirée), ou le relevé déjà pris cette semaine venait d'un
mauvais export. Dans ce cas seulement : **Suivi FWD → Archiver le relevé de
cette semaine** pose la question, contrat par contrat (« L'export de « HDK »
est identique au relevé S39… L'archiver quand même comme relevé S41 ? ») ;
**Oui** l'archive, **Non** ne touche à rien. Sinon, c'est que le fichier
n'était pas l'export du jour : importer le bon. L'archivage du vendredi,
lui, ne pose pas de question : il refuse, et le mail d'échec de Google le
dit.
Seule exception : un export où la page **ne trouverait plus** la colonne
suivie que l'onglet actuel a (un export d'un autre contrat, un `.csv` sans
sa ligne de groupes) ne remplace rien — l'ancien onglet reste, la ligne le
dit en ✗.

**À la main** (sans la fenêtre) : dans l'onglet de chaque contrat, **Ctrl+A**,
**Suppr**, cliquer **A1**, **Ctrl+V** de l'export ouvert dans Excel, puis
**Suivi FWD → Archiver le relevé de cette semaine.** Une boîte confirme :
« Relevé S39 archivé : HDK (186 plans), THS (93 plans). » Ce menu-là archive
**tous les contrats d'un coup**.

Une erreur de manipulation (mauvais extract importé ou collé) : **Suivi FWD →
Supprimer le relevé de cette semaine** — une boîte demande d'abord
« Supprimer le relevé S39 de « HDK », « THS » ? » (seuls les contrats qui ont
un relevé cette semaine sont nommés) ; **Non** ne touche à rien —, puis
importer le bon (case
« Archiver » cochée), ou le recoller et archiver de nouveau. Pour vérifier
après coup : le pied du tableau de bord (« 3 relevés archivés ») ou le
Diagnostic (« Relevés archivés : 3 »).

**Importer (ou coller) écrase-t-il l'historique ?** Non. L'import remplace
**l'extract** de l'onglet du contrat, comme un collage — c'est voulu,
l'onglet ne garde que l'état du jour. L'historique, lui, est dans l'onglet
masqué `Historique_FWD_HDK` : **une ligne par semaine archivée**, que rien
n'écrase, sauf un second archivage dans la même semaine (il remplace la ligne
de cette semaine-là). Le seul piège : remplacer l'extract **avant** d'avoir
archivé le précédent — la semaine du précédent est alors perdue. La case
« Archiver » de la fenêtre l'évite ; après un collage, archiver dans la
foulée (ou laisser l'archivage du vendredi le faire) suffit. En attendant
l'archivage, la page compte déjà l'extract du jour pour la semaine en cours,
et le pied le dit (« l'extract du jour, pas encore archivé, compte pour
S39 »).

**L'archivage refuse** si la colonne suivie est introuvable dans un onglet
(« Colonne « HDK AA 011 > Avancement Définition Electrique » introuvable ») :
une semaine où tout serait « non renseigné » fausserait la courbe pour de bon.
Le Diagnostic dit alors où se trouve l'intitulé (voir § 7).

Filet de sécurité : **Suivi FWD → Activer l'archivage automatique
(vendredi 17 h)**, et Google prend le relevé chaque vendredi **entre 17 h et
18 h**, à partir de ce qui est dans les onglets à ce moment-là. Il faut donc
avoir importé (ou recollé) l'extract avant ; à ce rendez-vous-là, personne
n'est devant l'écran, aucune boîte ne s'affiche. Après un import, case
« Archiver » cochée, il n'a plus rien à rattraper : il réécrit la ligne de
la semaine avec ce que portent les onglets, sans en ajouter une. Vérifier une fois, dans **Extensions →
Apps Script → ⚙ Paramètres du projet**, que le fuseau horaire est
Europe/Paris. « Désactiver l'archivage automatique » l'arrête.

### Rattraper une semaine passée (l'export gardé de côté)

Quand un relevé porte le mauvais export — par exemple S39 archivé avec
l'export de S40, les deux relevés identiques, donc aucun rythme — et que
l'export de cette semaine-là est encore sous la main :

1. Mettre l'export **de la semaine passée** dans l'onglet du contrat
   (`HDK`) : par la fenêtre d'import, **case « Archiver » décochée** — sinon
   il serait archivé pour la semaine en cours —, ou par un collage
   (**Ctrl+A**, **Suppr**, **A1**, **Ctrl+V**). Afficher cet onglet.
2. **Suivi FWD → Archiver l'onglet affiché pour une semaine passée…**,
   taper la semaine où l'export a été tiré de GATES : `S39` (ou `39`).
3. La boîte redit tout avant d'écrire : « Archiver l'export affiché dans
   « HDK » comme relevé S39 ? Il remplace le relevé S39 déjà archivé… » →
   **Oui**. Seul ce contrat est touché.
4. **Tout de suite, sans faute** : remettre l'export **du jour** dans
   `HDK` — par la fenêtre d'import, case « Archiver » cochée (elle archive
   dans la foulée), ou par un collage suivi de **Suivi FWD → Archiver le
   relevé de cette semaine**. Sinon l'archivage du vendredi prendrait
   l'export de S39 pour celui de la semaine en cours — et, dans le cas le
   plus courant, **sans rien dire** (voir ci-dessous).

Une semaine à venir est refusée (« S41 » tapé en S40 aussi) ; « S52 »
tapé début janvier est celle de l'année d'avant (la boîte écrit alors
« S52 2025 », forme qu'on peut aussi taper). Mettre l'export de la semaine
passée dans un **nouvel** onglet (« HDK S39 ») est refusé : ce serait un
nouveau contrat — c'est dans l'onglet `HDK` lui-même qu'il va.
Si l'étape 4 est oubliée, le filet ne joue que dans deux cas : la semaine
en cours a **déjà** son relevé (l'archivage refuse de l'écraser avec
l'export rattrapé, et le dit) ; ou l'export rattrapé est **plus ancien que
le dernier relevé** (« … porte le même export que le relevé S38, alors que
le relevé S39, plus récent, est différent… » : archivé pour la semaine en
cours, il ferait reculer les plans qui ont bougé depuis). Mais quand on
rattrape **la semaine juste avant** (S39, en S40, S40 pas encore archivée),
l'export rattrapé est le dernier relevé : rien ne le distingue d'une semaine
où rien n'a bougé, et le vendredi l'archive **sans un mot** pour S40 — une
semaine plate. D'où l'étape 4, obligatoire. (Rattrapable ensuite : importer
l'export du jour, case « Archiver » cochée, remplace la ligne de S40.)

## 5. La seconde base, SEE : un onglet par contrat

Chaque contrat a sa propre base SEE, donc son propre onglet : **`SEE HDK`**
pour le contrat de l'onglet `HDK`, **`SEE THS`** pour `THS`. Le plus simple —
et le seul chemin quand l'Excel de SEE est **trop lourd pour s'ouvrir** :

1. Dans le classeur, menu **Suivi FWD → Importer les exports GATES et
   SEE…** — la fenêtre du § 4 : les exports SEE peuvent y aller avec ceux
   de GATES, d'un coup (absente juste après avoir recollé `Code` : **F5**
   sur le classeur).
2. **Choisir les fichiers…** — l'export « Nommage WD BFLOW » de chaque
   contrat, tel qu'il a été téléchargé, **sans l'ouvrir dans Excel** (ou les
   glisser dans la fenêtre). Chacun prend l'étiquette **SEE**, et son
   contrat est retrouvé **par ses plans** : la fenêtre envoie au classeur un
   échantillon de quelques centaines de lignes — les seules colonnes NAME,
   SOL., Cust.V —, que le classeur rapproche des plans de chaque contrat
   comme la page le fait — même avec un seul contrat : c'est ce qui
   confirme qu'il est le bon ; sinon par le nom du fichier ; sinon elle
   propose le seul contrat, ou celui de l'onglet affiché, **à vérifier**
   (en ambre, la liste visible). Sous la ligne, l'onglet qu'elle va remplir :
   « Remplacera l'onglet « SEE HDK » » ou « Créera l'onglet « SEE HDK » ».
3. **Importer**, puis **ne pas fermer la fenêtre avant la fin** (elle le
   rappelle). Elle lit le fichier sur le poste — il ne part nulle part — et
   n'envoie au classeur que la ligne d'en-tête et les trois colonnes de la
   comparaison, **NAME**, **SOL.** et **Cust.V**. L'onglet `SEE HDK` est
   créé, ou remplacé : l'ancien ne s'en va qu'une fois tout reçu et vérifié,
   un import interrompu le laisse intact (si le classeur ne répond pas, la
   fenêtre réessaie deux fois d'elle-même). Quelques secondes pour la lecture
   (une dizaine pour 120 000 lignes), puis l'envoi par paquets ; la fenêtre
   dit où elle en est, puis « ✓ « export.xlsx » → N lignes dans l'onglet
   « SEE HDK » ». Un export SEE n'archive rien : la case « Archiver » ne
   concerne que les exports GATES.
4. Rouvrir le tableau de bord : chaque contrat se compare à sa base.

L'export SEE d'un contrat **tout neuf** peut partir avec son export GATES,
dans le même import : la fenêtre propose le nouveau contrat (« NEO
(nouveau) ») dans la liste de la ligne SEE, et pose l'export GATES d'abord.

Même avec **un seul contrat**, l'import crée `SEE HDK` (le nom du
contrat) : un `SEE` tout court déjà là, lui, est remplacé sous son nom — et
renommé `SEE HDK` le jour où la fenêtre crée un deuxième contrat (§ 3) : la
ligne SEE l'annonce alors (« Remplacera l'onglet « SEE HDK » (aujourd'hui
« SEE », renommé à la création du nouveau contrat) »).

L'onglet importé n'a que ces trois colonnes : c'est normal, la comparaison
n'en lit pas d'autre. Et comme l'ancien onglet est remplacé, une formule d'un
autre onglet qui pointait dessus serait à refaire (le tableau de bord, lui,
retrouve l'onglet par son nom).

La case **« Garder aussi les autres colonnes »** ne sert qu'à regarder tout
l'extract dans le tableau SEE de la page : la comparaison n'en a pas besoin,
et c'est bien plus lourd (au-delà de quatre millions de cellules, la
fenêtre refuse et dit de la décocher).

**Ce que la fenêtre lit** : les `.xlsx` et `.xlsm`, les `.csv` et `.txt`
(séparateur, accents et zéros de tête compris), et les faux « `.xls` » que
sortent certains outils (une page web ou du XML Excel 2003 renommés). Elle
ne lit pas un **vrai ancien `.xls`** (même renommé `.xlsx`), un `.xlsb`, ni un fichier **protégé**
(mot de passe, étiquette de confidentialité) : elle le dit. Pour un vrai
`.xls`, dans le classeur : **Fichier → Importer → le fichier → « Insérer de
nouvelles feuilles »** — ⚠️ surtout pas « Remplacer la feuille de calcul »,
qui remplace **tout le classeur** —, puis supprimer l'ancien onglet
`SEE HDK` et donner ce nom au nouveau. Pour un fichier protégé : demander
l'export sans protection, ou en `.csv`.

Si la fenêtre a été fermée en plein envoi, il reste un onglet
`SEE HDK (import …)` (ou `HDK (import …)` pour un export GATES) : il n'est
jamais lu — ni comme contrat, ni comme base —, le **Diagnostic** le signale,
et le prochain import du même onglet le retire tout seul (on peut aussi le
supprimer à la main).

**À la main, pour un petit extract** : **+** pour un nouvel onglet nommé
`SEE HDK` (`SEE - HDK` ou `SEE_HDK` marchent aussi), ouvrir l'extract dans
Excel, **Ctrl+A**, **Ctrl+C**, puis dans l'onglet **A1**, **Ctrl+V** — tel
quel, titre en ligne 1 et en-têtes en ligne 3 compris.

Avec **un seul contrat** dans le classeur, un onglet nommé `SEE` tout court
suffit. Avec plusieurs, un `SEE` tout court n'est lu pour aucun — il ne dit
pas à quel contrat il appartient : le **Diagnostic** le signale et donne le
nom à lui donner.

Sous le tableau des plans apparaît la section **Comparaison des bases de
données** : les deux cercles et, à leur droite, les verdicts — un clic sur
l'un d'eux déplie ses plans sous sa ligne. Au-dessus du tableau, l'interrupteur **GATES | SEE**
montre l'un ou l'autre extract. Rien à configurer : l'onglet est reconnu par
son nom (les en-têtes sont trouvés seuls, ligne 3 dans l'extract), et la
référence est recomposée à partir des colonnes NAME, SOL. et Cust.V — le A
du NAME, que SEE écrit un cran trop tôt (`TFE311A0600` pour le plan que
GATES appelle `TFE3110A600`), est décalé pour retrouver le plan dans GATES.

SEE n'a pas d'historique : la comparaison porte toujours sur l'extract qui
est dans l'onglet. On le réimporte quand on en a un plus récent (le même
menu, seul ou avec les exports GATES de la semaine), sans rien archiver.

### Si le collage rame

Le menu **Importer les exports GATES et SEE…** évite le collage : c'est le
premier remède.
S'il faut coller quand même, c'est Sheets qui peine sous le volume, pas le
tableau de bord : aucun calcul n'est déclenché par une saisie dans le
classeur. Dans l'ordre d'efficacité :

1. **Coller les valeurs seules** — **Ctrl+Maj+V** au lieu de Ctrl+V. C'est le
   plus gros gain : sans la mise en forme qui vient d'Excel (polices, bordures,
   couleurs, largeurs), Sheets a bien moins à écrire.
2. **Vider pour de vrai avant de recoller** — sélectionner les lignes par leurs
   numéros à gauche, clic droit, **Supprimer les lignes**. Un simple **Suppr**
   efface le texte mais laisse les lignes et leur mise en forme, qui
   s'accumulent d'une semaine sur l'autre. Même chose pour les colonnes vides à
   droite de l'extract.
3. **Coller par paquets** de deux ou trois mille lignes plutôt que tout d'un
   coup : la fenêtre reste utilisable pendant ce temps.
4. **Ne garder que les colonnes utiles.** La comparaison n'en lit que trois :
   **NAME**, **SOL.** et **Cust.V**. Les autres ne servent qu'à regarder
   l'extract dans le tableau SEE. Si c'est trop lourd, ne coller que ces trois
   colonnes : la page dit exactement la même chose, en beaucoup plus léger.
5. **Onglet `SEE HDK` nu** — pas de mise en forme conditionnelle, pas de filtre, pas
   de volet figé, et surtout aucune formule d'un autre onglet qui pointe dessus :
   elle se recalculerait à chaque collage.
6. **Si l'export existe en `.csv`** — onglet `SEE HDK` sélectionné (`SEE`
   tout court s'il n'y a qu'un contrat), Fichier →
   Importer → le fichier, puis **« Remplacer la feuille active »**. Sheets
   lit un fichier bien plus vite qu'il n'avale un collage. ⚠️ Surtout pas
   « Remplacer la feuille de calcul » : celle-là remplace **tout le
   classeur**, contrats et historique compris.
7. Fermer les autres onglets Chrome lourds, et le tableau de bord pendant
   l'opération : il ne recalcule rien, mais il occupe la mémoire.

## 6. Lire la page, de haut en bas

- **Le bandeau**, à droite : dès deux contrats le lien **Vue d'ensemble**
  (une ligne par contrat : validés, reculs, rythme, plans à l'arrêt,
  prochaine échéance) et le sélecteur **Contrat**, et
  dessous l'interrupteur **Avancement : Définition électrique | Concept
  harnais** — les deux
  avancements du bloc HDK AA 011 ; toute la page suit celui qui est choisi,
  le titre aussi (« Suivi FWD » ou « Suivi concept harnais »). Le concept
  harnais a trois valeurs : rien, « À traiter », « Traité » — « Traité »
  compte comme validé. Sous le
  titre, la semaine où l'on est, et rien d'autre.
- **Le périmètre** : Tout / BASE/OPTION / PERSO — les valeurs de la colonne
  « Domaine » de l'extract, telles quelles. Il restreint toute la page.
- **En haut, sans titre** : la phrase « N sur M plans validés », la barre
  des valeurs de la colonne telles qu'elles sont écrites (Validé, Check, En
  cours, A traiter, non renseigné…) avec leur nombre, et **À surveiller** :
  les plans en cours qui n'ont pas bougé depuis 6 semaines ou plus, un clic
  les montre. Au début, il n'y en a aucun : il faut six semaines de relevés
  pour qu'un plan puisse être « à l'arrêt ». Au-delà de quatre valeurs, ou
  quand l'une est trop petite pour se voir (deux plans sur six cents), les
  valeurs passent en **légende** sous la barre, toutes sur une ligne (les
  sept de GATES comprises) ; survoler une case éclaire son segment. VALIDATED (« Validé ») compte comme validé — partout, la
  page dit « validés » ; une autre valeur qui voudrait dire validé se
  déclare dans `Code` (`VALEURS_FINIES`).
- **Avancement dans le temps** : la courbe des validés relevé après relevé,
  les jalons du programme (numérotés 1 à 5 sur une rangée, en clair dans la
  légende dessous), la fin estimée au rythme tenu et le rythme requis pour
  tenir le prochain jalon (« manque N » quand le rythme ne suffit pas). La
  légende dit seulement **réalisé**, **au rythme tenu (2/sem.)** et
  **requis pour « Solde FWD »** : la fin estimée et le nombre du requis sont
  au survol, dans la fiche de l'échéance et dans le bloc par groupe. Il
  s'ouvre **toujours** sur **Échéances** — jusqu'à la semaine qui suit la
  dernière échéance : les cinq jalons à l'écran ; six mois pour un contrat
  sans jalon — ; **Échéances · 3 mois ·
  6 mois · 1 an · Tout** à droite (un autre choix vaut pour la visite, pas
  pour la prochaine ouverture). Les jalons sont ceux de **HDK** ; **THS** n'en a
  pas (un autre contrat, d'autres dates, à venir) : sa page montre le rythme
  tenu, sans échéance — la fin estimée au survol de « au rythme tenu », dans
  la vue d'ensemble et par groupe. Sous chaque jalon de la légende, son nom et sa
  semaine ; le reste (périmètre, jours) au survol et dans la fiche. En
  tête, la prochaine échéance en jours : un clic ouvre sa fiche (Échap la
  ferme). Les jalons **TO** (table outil) suivent le concept harnais : sous
  la définition électrique, ils restent dessinés, en retrait.
  **Au-dessus de la courbe, des pastilles** (une par valeur que les relevés
  ont portée, sur une ligne) : par défaut celle de VALIDATED, la courbe des
  validés. Un clic sur une autre
  — PWD_IN_PROGRESS, TO_CONFIRM… — montre combien de plans la portent,
  relevé après relevé, et dessous sa variation par semaine (les baisses
  sous le trait). Le rythme, la fin estimée et l'échéance restent ceux des
  validés. Au concept harnais sans aucun « Traité », pas de pastille pour
  lui : la courbe des validés est celle qu'on voit quand aucune n'est
  pressée, et un second clic sur la pastille pressée y revient.
- **Ce qui a changé, semaine par semaine** : le journal — quels plans sont
  passés à VALIDATED, lesquels ont changé d'indice, lesquels sont apparus ou ont
  disparu de l'extract, et les **reculs**, en rouge. Les semaines forment un
  tableau : une colonne par sorte de passage, nommée dans l'en-tête, de la
  plus fréquente à la plus rare, la pastille et le nombre dans la case —
  tout tombe droit d'une semaine à l'autre. Dépliée, une ligne = une
  référence et son passage, sans libellé. Les semaines s'ouvrent repliées.
  **Au-dessus, une seule ligne** : les pastilles à gauche, le petit champ
  « Chercher un plan… » au bout à droite (il ne cherche que dans le
  journal). Les pastilles : **seulement les valeurs vers lesquelles des
  plans sont passés** (dans l'ordre de la barre du haut), puis Reculs et
  Changement d'indice s'il y en a, chacune avec son nombre — combien de
  plans y sont arrivés, toutes semaines confondues. S'il n'y a eu que des
  validations, il n'y a que « Tout » et VALIDATED. Un clic n'affiche
  qu'eux : « VALIDATED » montre tous les plans devenus validés, **y compris
  ceux validés sous un nouvel indice**. Une ligne trop longue défile (un
  fondu à droite le dit).
- **Avancement FWD par…** (ou **Concept harnais par…**) : le même avancement découpé par ATA, séquence,
  CC, ECP, ou par mois de création, avec la fin estimée et le rythme requis
  (en plans par semaine, le rythme tenu dessous) par groupe, rangés par ATA
  dans l'ordre, chacun avec son chevron et, en ambre, ses plans **à
  l'arrêt** — en cours, sans changement depuis 6 semaines ou plus (le bloc
  le rappelle en tête).
  Un clic sur un groupe déplie ses plans **sur place**, sous sa ligne —
  les autres groupes restent là, comme les semaines du journal ; le reste
  de la page (phrase, courbe, tableau) suit ce groupe, un second clic le
  referme. Une sous-liste par valeur (VALIDATED, PWD_IN_PROGRESS…), chacune
  avec son compte. **Sous le titre, la même ligne que le journal** : ses
  pastilles à gauche — seulement les valeurs que portent ses plans, ceux
  que le champ laisse voir quand il filtre —, et au bout à droite le champ
  « ATA ou plan… » (un groupe ou un plan), précédé de « n sur m » groupes
  quand il filtre. Un clic sur VALIDATED compte, dans
  chaque groupe, ses plans VALIDATED « sur » son total, et « +n » ceux
  arrivés au dernier relevé ; la barre n'éclaire que cette valeur. Le choix
  ne touche que ce bloc et tient quand on passe d'ATA à ECP ; la fin estimée
  et les rythmes restent ceux de tout le groupe.
- **Plans** : l'extract, à l'identique, avec ses colonnes ; recherche, tri,
  filtres. « Vue essentielle » n'en garde qu'une poignée — référence, nom
  d'installation, ECP, ATA, séquence, validation définition électrique, date
  de création, avancement — celles de cette liste qui se retrouvent dans
  l'extract. Les cases à cocher se lisent Oui / Non. **Un clic sur une
  référence** — ici ou n'importe où dans la page — ne montre que ce plan, et
  ouvre au-dessus du tableau **sa vie** : une case par relevé, depuis quand
  il est dans son état, ses changements (reculs en rouge, changements
  d'indice en violet).
- **Comparaison des bases de données** (si l'onglet `SEE` est là) : ce que
  GATES dit validé et que SEE connaît, et les écarts — en cercles, et à
  droite six verdicts, une seule liste : un clic sur un verdict filtre le
  tableau et déplie tous ses plans sous sa ligne, en puces. Un clic sur une
  référence la montre dans le tableau ; le petit champ à droite du titre ne
  cherche que dans la comparaison. Elle n'existe que pour la définition
  électrique : SEE ne connaît pas le concept harnais.

## 7. Si quelque chose ne va pas

D'abord **Suivi FWD → Diagnostic** : il dit ce que le script voit, onglet par
onglet, et ce qui manque. Puis :

| Ce que vous voyez | Ce que ça veut dire | Quoi faire |
|---|---|---|
| Pas de menu « Suivi FWD » | Le script n'est pas chargé | F5 ; sinon Extensions → Apps Script, fonction `onOpen`, ▶ Exécuter (le menu ne dépend que du fichier `Code`) |
| « Ouvrir le tableau de bord » donne une erreur | Un fichier HTML manque ou est mal nommé | Diagnostic : il nomme le fichier (`Index`, `Styles`, `Javascript`) introuvable |
| La page reste **blanche** : le titre, des cadres vides, des tirets « — » | Le code de la page ne s'est pas lancé — le plus souvent un fichier resté à la livraison d'avant, ou coupé au collage (débrief 17) | Recoller **les quatre** fichiers de la dernière livraison (§ 1, « Recoller une livraison ») ; par un lien `…/exec`, publier une **nouvelle version** du déploiement. Les pages livrées depuis le 29 septembre le disent elles-mêmes en tête |
| En tête : « Les fichiers du tableau de bord ne concordent pas. **Index** ne vient pas de la même livraison… » | Ce fichier-là est resté à une autre livraison | Le recoller depuis la dernière livraison, Ctrl+S (et nouvelle version du déploiement pour un lien `…/exec`) |
| En tête : « La page n'a pas pu démarrer. Le fichier Javascript semble incomplet » | `Javascript` a été collé en partie (le fichier est long) | Dans `Javascript.html.txt` : Ctrl+A, Ctrl+C ; dans Apps Script : `Javascript`, Ctrl+A, Ctrl+V, Ctrl+S. Le Diagnostic dit « ✗ « Javascript » est incomplet » tant que ce n'est pas fait |
| En tête : « La page n'a pas pu s'afficher. Une erreur l'a arrêtée » | Une panne de la page elle-même | M'envoyer une capture du cadre (il ne cite aucune valeur du classeur) : le « Détail » me dit où chercher |
| En bas de la page, la livraison n'est pas celle que je vous ai donnée | Le lien `…/exec` sert encore l'ancienne version déployée | Déployer → Gérer les déploiements → ✏️ → Nouvelle version → Déployer |
| Une page « Le tableau de bord ne peut pas s'ouvrir : les fichiers collés ne tiennent pas ensemble » | Un fichier manque au projet (`Index`, `Styles` ou `Javascript`) | Elle nomme le fichier : + → HTML, le nommer exactement, y coller le `.txt` |
| Le Diagnostic dit « ✓ Fichier « Javascript » : 213307 caractères » alors que le `.txt` en fait 300 000 | Normal : Apps Script compte les fichiers sans leurs commentaires | Rien à faire, tant qu'il dit « ✓ … concordent, et sont entiers » |
| « Le fichier Javascript contient deux copies » | Collé sans tout effacer (le neuf au-dessus de l'ancien) | `Javascript` : Ctrl+A, Suppr, coller, Ctrl+S |
| Au-dessus de la barre : « L'onglet d'historique « Historique_FWD_… » n'est rattaché à aucun contrat » | Un onglet de contrat renommé : ses relevés sont restés sous l'ancien nom. L'archivage est refusé d'ici là | Afficher les onglets masqués, renommer l'historique comme la page l'indique |
| Au-dessus de la barre : « L'ancien onglet d'historique « Historique_FWD » … n'est rattaché à aucun contrat » | Un deuxième contrat a été ajouté **à la main** à un classeur qui n'en avait qu'un (la fenêtre d'import, elle, le renomme d'elle-même) : l'ancien historique, sans nom de contrat, n'est plus celui de personne. L'archivage du contrat sans historique est refusé d'ici là | Afficher les onglets masqués, renommer `Historique_FWD` en `Historique_FWD_HDK` (le contrat qui a produit ces relevés, que le message nomme quand il le sait — jamais le contrat qu'on vient de créer). Ne pas retirer le préfixe : les relevés de HDK sortiraient de la page |
| « La colonne … est vide sur les N plans » | L'export importé ou collé n'a pas cette colonne remplie | Réimporter (ou recoller) un export complet ; l'archivage est refusé si la semaine d'avant en avait des valeurs |
| « L'onglet « THS » ne porte aucun plan (en-têtes seuls) » (dans le Diagnostic : « ⚠ L'onglet ne porte aucun plan (en-têtes seuls) : y importer l'export GATES… ») | Un onglet préparé d'avance | Y importer (ou coller) l'export du contrat ; en attendant, il n'est pas archivé |
| En bas : « Chiffres lus dans le classeur le vendredi… » | La page est ouverte depuis longtemps | Recharger la page avant de présenter |
| « Le classeur n’a pas encore de plans », avec une alerte | Aucun onglet de données lisible : l'alerte dit pourquoi | « Aucune colonne d'avancement FWD n'a été reconnue » : l'extract est collé sans sa ligne d'en-têtes ou sa ligne de groupes → le réimporter (Suivi FWD → Importer les exports GATES et SEE…), ou le recoller entier en A1 ; « Aucun onglet de données exploitable : « Feuille 1 » est vide » : aucun onglet ne contient encore d'extract → l'importer (§ 2) |
| En haut : « Colonne « HDK AA 011 > Avancement Définition Electrique » introuvable » | L'extract n'a pas cette colonne sous ce groupe (groupe renommé, bloc absent) : la page n'en lit **aucune autre** à la place, rien n'est dit validé, l'archivage refuse | Diagnostic : il liste les groupes où l'intitulé existe ; corriger le nom du groupe dans `COLONNE_FWD` (partie avant « > ») s'il a changé dans l'export |
| Pour vérifier la colonne lue | — | Le **pied de la page** la nomme : « Colonne suivie : HDK AA 011 › Avancement Définition Electrique » |
| « 0 sur 600 plans validés », et au-dessus de la barre « Aucun plan n'est compté « validé » » | Le mot qui veut dire « fini » dans la colonne n'est pas connu de la page (seul « Validé » l'est, avec « Validée », « Terminé », « OK », « 100 % »…). Jamais au concept harnais : « 0 Traité » y est un vrai zéro, sans message | La page liste les valeurs lues : m'envoyer celle(s) qui veulent dire « fini » (et « pas commencé »), je les ajoute à `VALEURS_FINIES` (et `VALEURS_A_FAIRE`) dans `Code` |
| « Ce qui a changé semaine par semaine » reste vide | Le journal dit pourquoi : un seul relevé (deux archivages la même semaine n'en font qu'un), ou deux relevés identiques — le même export archivé deux fois | Importer le **dernier** export de GATES (case « Archiver » cochée), ou le recoller puis archiver ; le Diagnostic dit combien de plans ont changé entre les deux derniers relevés |
| Pas de courbe, pas de fin estimée | Aucun relevé archivé | Suivi FWD → Archiver le relevé de cette semaine (ou importer l'export, case « Archiver » cochée) |
| Pas de section « Comparaison » | Pas d'onglet `SEE <contrat>` (ou `SEE` pour un seul contrat), ou illisible | Diagnostic, ligne « Seconde base » : elle dit s'il manque l'onglet, s'il est vide, ou si les en-têtes NAME / SOL. / Cust.V ne s'y trouvent pas |
| La fenêtre d'import dit « Ni un export GATES ni un export SEE » | Le fichier n'est ni l'un ni l'autre — ou SEE a renommé une de ses colonnes NAME / SOL. / Cust.V (la fenêtre cite la ligne la plus proche et ce qui lui manque) | Retirer ce fichier ; si c'est bien un export et que ses intitulés ont changé, me les envoyer (les intitulés seulement, pas les données) |
| Sur une ligne de la fenêtre, en ambre : « … choisir le contrat » ou « à vérifier » | La fenêtre n'a pas pu rattacher l'export à un contrat avec certitude : aucun plan en commun, plusieurs contrats nommés dans le fichier, ou un contrat nommé dont l'onglet n'a presque aucun plan en commun avec lui. Pour un export SEE, même avec un seul contrat (« « HDK » est le seul contrat, mais l'échantillon n'y retrouve que 0 référence sur 400 : à vérifier ») — et **Importer reste allumé** | Choisir le contrat dans la liste de la ligne — ou « Nouveau contrat… » pour l'export GATES d'un contrat que le classeur n'a pas encore. Pour un SEE, vérifier l'onglet nommé sous la ligne avant d'importer |
| La fenêtre dit « Deux fichiers vont dans l'onglet « HDK » » | Deux exports du même contrat dans la liste (celui de la semaine dernière, resté dans Téléchargements, souvent) ; la date de chaque fichier est sur sa ligne | **Garder le plus récent** — celui que la fenêtre nomme (« Garder le plus récent, « … » (du 3 oct. 14:20) ») — et **Retirer** l'autre ; ou changer son contrat si c'est l'export d'un autre contrat |
| La fenêtre dit « La ligne d'en-têtes de cet export GATES est en ligne 14 » | Le fichier a été retouché (des lignes ajoutées en haut) : la page ne trouverait pas ses en-têtes | Le retélécharger de GATES tel quel |
| Sur une ligne de la fenêtre, ✗ « Colonne suivie absente de cet export… L'ancien onglet « HDK » est intact » | La page ne trouverait pas la colonne suivie dans cet export, alors qu'elle la trouve dans l'onglet actuel : un export d'un autre contrat ou d'un autre programme, ou un `.csv` sans sa ligne de groupes. Rien n'est remplacé, rien n'est archivé | Vérifier le contrat choisi sur la ligne ; importer l'export **Excel** (`.xlsx`) de GATES de ce contrat |
| Après l'import d'un export GATES, ⚠ « … mais la colonne suivie est introuvable » | L'export n'a pas la colonne suivie sous son groupe — le plus souvent un `.csv`, qui perd les cellules fusionnées de la ligne des groupes ; rien n'est archivé | Importer l'export **Excel** (`.xlsx`) de GATES ; sinon, Diagnostic (ligne « Colonne … introuvable » ci-dessous) |
| Après l'import, ⚠ « Relevé S40 non archivé : … » | L'import est fait, mais l'archivage a refusé, pour la raison qui suit (l'export est identique à un relevé plus ancien, un historique attend d'être rattaché…) | Faire ce que dit le message. Pour un historique à rattacher : le geste du § 3 (renommer `Historique_FWD` au nom du contrat qui a produit ces relevés), puis Suivi FWD → Archiver le relevé de cette semaine |
| La fenêtre d'import dit « ancien fichier Excel (.xls) » ou « navigateur trop ancien » | Un format qu'elle ne lit pas, ou un Chrome / Edge d'avant 2022 | Demander l'export en `.xlsx` ou `.csv` ; ou Fichier → Importer → « Insérer de nouvelles feuilles » (§ 5) ; ou mettre le navigateur à jour |
| La fenêtre d'import dit « Ce fichier Excel est protégé » | Mot de passe ou étiquette de confidentialité sur l'export : ni la fenêtre ni Sheets ne peuvent le lire | Demander l'export sans protection, ou en `.csv` ; pour un export GATES qu'Excel ouvre, le collage à la main (§ 2) reste possible |
| La fenêtre d'import dit « Google refuse l'appel : plusieurs comptes Google… » | Plusieurs comptes Google connectés dans le même Chrome : Apps Script se trompe de compte | Ouvrir le classeur dans une fenêtre où seul le compte du classeur est connecté (ou une fenêtre de navigation privée), puis relancer |
| La fenêtre d'import dit « Le classeur dépasserait la limite de Google Sheets : 10 millions de cellules » | Un classeur Google ne dépasse pas dix millions de cellules, **vides comprises** — et le temps de l'import, l'ancien onglet et le nouveau coexistent ; la fenêtre compte avant d'envoyer, rien n'est créé | Décocher « Garder aussi les autres colonnes » ; sinon supprimer les onglets qui ne servent plus (vieux essais, copies), ou les lignes et colonnes vides en bas et à droite des gros onglets |
| La fenêtre d'import dit « Le fichier est abîmé » | Téléchargement coupé, ou fichier enregistré à moitié | Le retélécharger depuis GATES ou SEE |
| Un onglet `HDK (import …)`, `SEE HDK (import …)` ou `… (ancien …)` en plus | La fenêtre d'import a été fermée (ou la connexion coupée) en plein envoi — l'onglet visé est intact —, ou l'échange des onglets a été coupé à mi-course (« ancien » : l'onglet d'avant, mis de côté). Ce reste n'est jamais lu, ni comme contrat ni comme base | Le supprimer, ou relancer l'import du même onglet : il le retire. Le Diagnostic le signale |
| Un contrat en trop ou en moins | Un onglet visible en trop, ou masqué | Chaque onglet visible qui porte un export (Référence UD, ATA…) est un contrat ; un onglet « Notes » à côté est écarté tout seul (le Diagnostic le dit) |
| « N lignes répètent une référence déjà vue » au-dessus de la barre | L'export a été collé par-dessus l'ancien sans le vider : des lignes de l'ancien restent en dessous | Le réimporter (l'onglet est remplacé en entier), ou Ctrl+A, Suppr, puis le recoller en A1 |
| Après avoir renommé un onglet de contrat, la courbe repart d'un seul relevé | L'historique porte encore l'ancien nom (`Historique_FWD_Feuille 1`) | Le Diagnostic le signale : renommer cet onglet d'historique `Historique_FWD_<nom du contrat>` |
| Sous le graphique : « S41 : aucun changement depuis le relevé d'avant, plan par plan » | L'archivage (celui du vendredi, souvent) a repris l'export de la semaine d'avant — ou rien n'a vraiment bougé | Si un export plus récent existe : l'importer (case « Archiver » cochée), ou le recoller puis archiver : le relevé de la semaine est remplacé |
| Deux relevés identiques alors que j'ai bien les deux exports | La semaine passée a été archivée avec l'export d'aujourd'hui | § 4, « Rattraper une semaine passée » : remettre l'export de la semaine passée (import, case « Archiver » décochée, ou collage), **Archiver l'onglet affiché pour une semaine passée…**, puis remettre l'export du jour et archiver |
| « Geste refusé : il ne se lance que dans le classeur, menu Suivi FWD » | Quelqu'un a essayé d'archiver, supprimer ou couper l'archivage depuis la page (la console du navigateur) | Rien à faire : la page est en consultation, elle ne modifie rien. Ces gestes se font dans le classeur, menu Suivi FWD |
| « l'onglet « HDK » porte le même export que le relevé S39 : le relevé S40 déjà archivé, différent, n'est pas écrasé » — ou « … que le relevé S38, alors que le relevé S39, plus récent, est différent » (ou un mail d'échec de Google le vendredi) | Le plus souvent, l'export d'une semaine passée (rattrapé, ou pris par erreur dans Téléchargements) est dans l'onglet : l'archiver pour la semaine en cours écraserait le bon relevé, ou ferait reculer les plans qui ont bougé depuis. Plus rarement, c'est voulu : GATES est vraiment revenu à cet état, ou le relevé de la semaine venait d'un mauvais export | Si l'onglet n'a pas l'export du jour : importer le bon (case « Archiver » cochée). Si c'est voulu : **Suivi FWD → Archiver le relevé de cette semaine**, qui demande « L'archiver quand même ? » → **Oui** |
| Sur une ligne de la fenêtre, ✗ « Le classeur est occupé par un autre geste (archivage…) : l'onglet « HDK » n'a pas été remplacé » | L'archivage du vendredi (ou un autre import) tenait le classeur au moment d'échanger les onglets : l'import a renoncé plutôt que de retirer l'onglet sous ses yeux. L'ancien onglet est intact | Relancer l'import dans une minute |
| La fenêtre dit « La liste des contrats n'a pas pu être relue après l'import » | Le classeur n'a pas répondu à la fin d'un import : la fenêtre ne rattache pas de nouveaux fichiers avec une liste périmée | Fermer la fenêtre et la rouvrir (menu Suivi FWD → Importer les exports GATES et SEE…) |
| « … un autre geste écrit en ce moment dans l'historique de ce classeur … : l'historique n'est pas touché » | Deux archivages en même temps (celui du vendredi et un import, ou le menu) : le second attend trente secondes, puis renonce plutôt que d'écrire deux relevés pour la même semaine | Relancer dans une minute (menu Suivi FWD → Archiver le relevé de cette semaine) |
| THS n'a pas d'échéance | Voulu : les jalons livrés sont ceux de HDK | Me donner les dates de THS quand elles existent : je les ajoute dans `CONFIG.JALONS` avec `contrat: 'THS'` |

Et dans tous les cas : **le texte du Diagnostic** (copié à la souris dans la
boîte, ou pris dans Extensions → Apps Script → Exécutions) suffit pour que je
voie ce qui se passe.

## 8. Passer la main (congés longs, changement de poste)

La page tourne au nom de celui qui l'a déployée, et l'archivage du vendredi
aussi. Pour qu'un collègue reprenne :

1. Partager le classeur avec lui en **modification**, puis Fichier →
   Partager → le nommer **propriétaire** (les onglets d'historique suivent :
   ils sont dans le classeur).
2. Lui, dans le classeur : **Suivi FWD → Activer l'archivage automatique**
   (le déclencheur est personnel : celui de l'ancien propriétaire s'arrête
   avec son compte), puis **Déployer → Nouveau déploiement → Application web**
   et diffuser le **nouveau** lien `…/exec`.
3. Pour une absence courte, rien à transférer : il suffit que quelqu'un fasse
   l'export GATES chaque semaine et le garde, nommé par semaine ; au retour,
   **Archiver l'onglet affiché pour une semaine passée…** (§ 4) remet chaque
   export à sa semaine.

## 9. Ce qu'il ne faut pas faire

- Renommer ou modifier les onglets `Historique_FWD_…` : c'est la mémoire.
- Retoucher l'extract collé (trier, supprimer des colonnes, renommer des
  en-têtes) : le tableau de la page doit être l'extract, et le modèle de
  colonnes se repère sur les en-têtes de GATES.
- Coller deux extracts dans le même onglet.

---

*Le reste — l'installation pas à pas, et plus tard l'automatisation des
extracts — est dans `AU-BUREAU.md`. Le détail de chaque règle est dans
`PROCEDURE.md`.*
