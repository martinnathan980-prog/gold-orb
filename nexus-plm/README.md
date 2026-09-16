# NEXUS PLM

Gestion de nomenclatures d'assemblages, sur Google Apps Script + Google Sheets.

- `ANALYSE.md` — analyse de la version d'origine (bugs, fragilités, décision d'architecture)
- `correctifs/` — lot 1 : correctifs ciblés des 6 bugs, à poser sur la version d'origine
- `src/` — **réécriture complète** (celle-ci)
- `test/` — 1 235 tests, exécutés sur les fichiers réellement livrés

```
npm test                 # 825 tests : logique, pondération, serveur, bundle
npm run demo             # construit build/demo.html et build/nexus-demo.html
npm run appsscript       # construit build/appsscript/ (version à coller)
npm run test:navigateur  # 410 tests dans un vrai Chromium
```

## Mise en service — deux chemins

**Montrer l'application, sans rien installer.** `build/nexus-demo.html` :
double-clic, ça s'ouvre dans le navigateur. Données en mémoire, rien n'est
enregistré. C'est le fichier à envoyer à un collègue.

**La mettre en service pour de vrai**, sur un Sheet : il faut copier le code
dans un projet Apps Script. Deux façons, au choix.

| | `clasp push` | Copier-coller |
|---|---|---|
| Ce qu'il faut | Node + `npm install -g @google/clasp` | un navigateur, rien d'autre |
| Ce qu'on colle | rien, `clasp` envoie `src/` | 2 fichiers, depuis `build/appsscript/` |
| Dans l'éditeur | les 20 fichiers, découpés | `Code.gs` + `Index.html` |
| Pour qui | mises à jour régulières | première mise en service, poste verrouillé |

Le copier-coller n'est pas une version dégradée : `npm run appsscript`
concatène les 4 fichiers serveur en un `Code.gs` et résout les
`<?!= include() ?>` dans un `Index.html`. C'est le même code, en deux
fichiers au lieu de vingt. `build/appsscript/catalogue.csv` accompagne le
tout : c'est le classeur catalogue, prêt à importer.

Un test (`test/test-bundle.js`) vérifie que cette version reste identique à
`src/` — aucun fichier perdu, aucun include oublié.

## Où est la base de données ?

**Dans un Google Sheet, et nulle part ailleurs.** L'application n'a pas de
base à elle : le classeur *est* la base, et chaque onglet est une table.

| Onglet | Rôle | Une ligne = |
|---|---|---|
| `1_BOITES` | les boîtes | une boîte : Fonction, PN Global, DS/VCI, Porteur, Statut, Niveau de qualification, **Composants** (boutons, voyants…), Image, Commentaires |
| `2_NOMENCLATURE` | les sous-ensembles | un sous-ensemble rattaché à sa boîte par `PN Global` : Type, PN du type, puis les colonnes de son type (référence, mots-clés, cotes, **Composants mécaniques**, **Composants routing**…) |
| `9_JOURNAL` | la trace | qui a modifié quoi, et quand |
| *catalogue* (classeur séparé) | les composants connus | Catégorie, Fonction, Norme, Référence, Désignation |

Concrètement : on ouvre le Sheet, on voit les données ; on les modifie dans
l'application, la cellule change dans le Sheet ; on peut aussi corriger une
cellule à la main, l'application la relira. `Config.gs` liste les en-têtes
attendus, et `Setup.gs` crée les onglets manquants (menu **NEXUS PLM** dans le
Sheet). Ajouter une colonne au Sheet suffit à la faire apparaître dans la
fiche, sauf pour les champs typés du registre.

Une cellule à valeurs multiples porte **une valeur par ligne** (Alt+Entrée
dans le Sheet) : c'est le cas des porteurs, des qualifications et des
composants.

Les composants s'écrivent **`Fonction | Norme | Référence`**, une ligne par
composant : `Bouton poussoir | ECS 7251 | MS24523-22`. L'ancienne écriture
`Type | Sous-type (Norme)` reste lue.

**La démonstration**, elle, n'a pas de Sheet : `demo/FauxServeur.html` garde
les mêmes tables en mémoire, dans l'onglet du navigateur. Rien n'y est
enregistré, tout repart à zéro au rechargement — c'est fait pour montrer, pas
pour travailler.

## Montrer l'application sans Google

`npm run demo` produit **`build/nexus-demo.html`** : un fichier unique, à
ouvrir d'un double-clic dans n'importe quel navigateur, sans serveur ni
réseau. Il contient l'application complète (le vrai code de `src/`), Bootstrap
inliné, des photos d'exemple et le faux serveur en mémoire. C'est le fichier à
envoyer à un collègue.

(`build/demo.html` est la même chose sous forme de fragment, pour l'aperçu
hébergé.)

## Démonstration navigable

`build/build-demo.js` assemble une version qui tourne hors de Google. Elle
résout les `<?!= include() ?>`, inline Bootstrap (la politique de sécurité des
Artifacts interdit les feuilles de style externes) et insère
`demo/FauxServeur.html`, qui fournit un `google.script.run` factice adossé à
des données en mémoire.

**Aucun fichier de `src/` n'est modifié pour la démo.** C'est la démonstration
concrète du découpage : `Api.html` appelle `google.script.run` exactement comme
en production, seul le transport change. C'est aussi ce qui permet de tester
l'interface dans un navigateur sans Google (`test/test-navigateur.js`).

La démo ajoute un interrupteur « simuler une panne serveur » : il sert à voir
le comportement d'échec, qui était totalement muet dans la version d'origine.
L'aperçu du CSV remplace le téléchargement, bloqué par le bac à sable.

## Structure

```
src/
  appsscript.json          manifeste (V8, portée du déploiement, scopes)
  Index.html               squelette — aucune logique

  server/
    Config.gs              feuilles, en-têtes, statuts, URL du catalogue
    Repository.gs          E/S Sheets : lecture, écriture par lot, clés, verrou, journal
    Api.gs                 SEULES fonctions exposées au client + validation
    Setup.gs               création de structure, jeu de démo, menu

  client/
    Styles.html            design system : fond blanc, une teinte de marque, la couleur signifie
    Composants.html        composants à trois niveaux : fonction > norme > référence
    Types.html             REGISTRE DES TYPES : champs + critères par type
    Dom.html               esc(), formats, délégation d'événements
    Api.html               google.script.run -> Promise   <-- frontière unique
    Store.html             état, recherche indexée, pondérations, journal
    Compare.html           scoring PUR, piloté par le registre, aucun HTML
    ViewGrid.html          cartes, onglets, filtres par type, indicateurs
    ViewFiche.html         panneau latéral, champs selon le type
    ViewCompare.html       rendu des équivalences
    Reglages.html          rail de pondération, à gauche du classement
    Annulation.html        rattrapage d'une suppression
    Dialogues.html         demander() / confirmer() — prompt() et confirm() sont bloqués chez Google
    Main.html              contrôleur : actions et démarrage
```

## Types de sous-ensembles

`client/Types.html` est la pièce maîtresse : un seul endroit décrit, pour chaque
type, **les champs qu'il porte** et **les critères qui servent à l'équivalence**.
L'affichage de la fiche, le moteur de scoring et l'écran de réglages en sont
tous générés. Ajouter un type ou un critère ne demande de toucher à aucun autre
fichier.

| Type | Champs propres | Critères d'équivalence |
|---|---|---|
| **Structure boîte** | montage, nombre de pas, longueur, largeur, masse, HL, DAL, **composants mécaniques**, **composants électriques** | montage, pas, dimensions, masse, DAL, HL, qualifications, composants mécaniques, composants électriques |
| **Harnais** | PN, référence | **référence, et rien d'autre** |
| **Plaquette éclairante** | PN, **mots-clés** | **mots-clés, et rien d'autre** |

Il n'y a que ces trois types. Un `Type` non reconnu dans la feuille reste
affichable (repli technique) mais n'est jamais proposé à la saisie.

Une pièce n'est comparée qu'aux pièces du **même type** : confronter une
plaquette et un harnais n'a pas de sens, ils n'ont pas les mêmes critères.

Les mots-clés sont comparés en recouvrement de vocabulaire, insensible aux
accents et à la casse, doublons écartés : « mission SAR » et « Mission Sar »
sont le même terme.

### Trois familles de composants

Les composants ne sont pas au même endroit selon ce qu'ils sont :

| Famille | Où | Exemples |
|---|---|---|
| **Composants** | sur la **boîte** | boutons poussoirs, voyants, interrupteurs, relais — ce qui se voit et se manipule |
| **Composants mécaniques** | sur la **structure boîte** | colonnettes, entretoises, équerres, inserts — ce qui est dur |
| **Composants routing** | sur la **structure boîte** | colliers, embases, passe-fils — ce qui tient les câbles |

Chaque famille a sa colonne, son catalogue (filtré par catégorie) et son
critère d'équivalence, pondéré séparément.

### Équivalence d'un composant : trois niveaux qui s'additionnent

Un composant se décrit en trois niveaux de précision croissante :

1. **Fonction** — ce que c'est : bouton poussoir, colonnette
2. **Norme** — ce qui le définit : ECS 7251, NSA 5512
3. **Référence** — le modèle exact

Les niveaux ne s'excluent pas, ils **s'additionnent**. Même fonction : on
prend la part de la fonction. Même norme en plus : on ajoute la part de la
norme. Même référence en plus : on ajoute la sienne, et le composant vaut
alors le maximum.

| Ce qui est partagé | Ce que le composant rapporte |
|---|---|
| Fonction seule | 20 % |
| Fonction et norme | 50 % |
| Les trois | 100 % |
| Fonctions différentes | rien |

Ces trois parts **se règlent**, dans le rail de pondération, dès que la portée
comparée manipule des composants : sur la boîte comme sur la structure boîte.
Le rail se lit de haut en bas, son en-tête reste fixe pendant qu'on descend,
et il annonce ce qui vient : « 9 critères retenus, plus les 3 niveaux de
composant ». Le bloc des niveaux ferme la liste, repérable à son aplat
marine. Une pondération dans la pondération : elle
dit ce que vaut une fonction partagée face à une référence exacte. Elle est
commune à la boîte et à la structure, puisque les trois niveaux veulent dire
la même chose des deux côtés.

**Ce qui n'est pas renseigné ne peut pas être exigé.** Un composant décrit par
sa seule fonction, s'il retrouve la même fonction, vaut 100 % de ce qu'on
savait de lui : la norme et la référence qu'on ne lui connaît pas sortent du
dénominateur. C'est la règle des critères non mesurables, appliquée à
l'intérieur d'un composant.

**La fonction est la porte d'entrée.** Deux composants de fonctions
différentes ne sont jamais appariés, même s'ils partagent une référence par
accident : un bouton poussoir n'est pas un voyant.

L'appariement classe **toutes** les paires possibles par score décroissant
avant de servir. Le résultat ne dépend donc pas de l'ordre de saisie, et le
meilleur candidat est pris plutôt que le premier rencontré. Chaque composant
de la cible ne sert qu'une fois. Le détail affiche, par composant, quels
niveaux sont partagés et ce que cela rapporte.

## Le rail de pondération

« Par défaut » ouvre la liste — c'est l'état de départ, pas un repli — puis
viennent les favoris. Les curseurs, eux, sont **repliés derrière un
engrenage** : ils servent une fois sur dix, un favori suffit le reste du
temps. Qui veut vraiment arbitrer les déplie ; les autres ne les voient pas.

## Favoris de pondération

Régler cinq curseurs avant chaque recherche, personne ne le fait. Un favori
pose d'un coup une **intention** : « je cherche d'abord la même fonction »,
« je cherche d'abord ce qui vole déjà sur cet appareil », « je cherche d'abord
le même contenu ». Un clic, le classement se recompose.

Un favori dit aussi ce qui **ne** compte pas : les critères qu'il ne nomme pas
sont écartés, et réapparaissent dans « Critères écartés ». Les parts sont
écrites en relatif dans le registre — c'est plus lisible — et ramenées à 100 %
à l'application.

Ce sont des points de départ, pas des verrous : les curseurs restent là, et
bouger l'un d'eux démarque le favori. On ne prétend pas y être resté.

| Portée | Favoris |
|---|---|
| Boîte | Même fonction · Même porteur · Même contenu · Même qualification |
| Structure boîte | Même encombrement · Même qualification · Même contenu · Même montage |
| Composant | Référence exacte · Même norme · Même fonction |

## Pondération

La pondération se règle **depuis la comparaison elle-même**, dans un rail à
gauche du classement : on bouge un curseur, le classement à droite se
recompose. Le rail s'ouvre sur la portée de ce qu'on regarde et nulle part
ailleurs.

- Les parts **totalisent toujours 100 %**. Monter un critère fait mécaniquement
  descendre les autres, proportionnellement : c'est un arbitrage, pas une série
  de curseurs indépendants. Un total à 250 % ne voudrait rien dire.
- On **choisit les critères** : `−` écarte un critère, il disparaît alors du
  résultat au lieu d'y figurer barré ; il se réintègre d'un clic. Le dernier
  critère ne peut pas être retiré.
- **Harnais et plaquette n'ont qu'un critère** : le panneau le dit et n'affiche
  aucun curseur — il n'y a rien à arbitrer.
- Le **classement se recalcule à chaque mouvement** : il n'y a pas d'aperçu à
  part, le résultat est l'aperçu.

Les réglages sont mémorisés sur le poste. « Rétablir les valeurs d'origine »
remet parts, critères et seuil à leur état initial.

## Ce qu'on ne dit plus

L'ancien « taux de couverture » en pourcentage était incompréhensible. À la
place, les critères qu'on n'a **pas pu** comparer sont **nommés** sous le
score : « Non comparé, faute de donnée : Masse. Le score porte sur le reste. »

## Ne rien perdre

- **Annulation** : une suppression reste rattrapable deux minutes. L'élément est
  recréé — avec un identifiant neuf, ce que l'interface annonce plutôt que de
  laisser croire à un retour en arrière exact.
- Côté serveur, la feuille `9_JOURNAL` enregistre qui a modifié quoi et quand.

## Deux espaces, deux bases

Le sélecteur du haut ne change pas de point de vue : il change de base. Elles
ne se filtrent pas pareil et ne répondent pas aux mêmes questions.

**Espace Boîtes** — trois lectures de la base des assemblages :

- **Boîtes** : la grille de cartes. « Que contient cette boîte ? »
- **Sous-ensembles** : une ligne par PN, son type, les boîtes qui le montent.
  « Où sert ce sous-ensemble ? » — le réemploi pris par l'autre bout.
- **Standardisation** : les familles de composants qui se dispersent. « Où la
  base coûte-t-elle plus qu'elle ne devrait ? »

**Espace Composants** — le référentiel des pièces, avec ses propres filtres,
sa propre recherche et sa propre bande d'indicateurs. Rien n'est partagé avec
l'espace Boîtes : revenir aux boîtes n'hérite pas du mot-clé tapé ici.

## L'espace Composants

Il réunit **deux sources qui ne se recouvrent pas** : le catalogue — ce qu'on
a le droit de monter — et les montages réels — ce qu'on monte effectivement.
Leur différence est l'information la plus utile de la page.

| État | Ce que ça veut dire |
|---|---|
| courant | au catalogue, et monté |
| **hors catalogue** | monté, mais absent du catalogue : une pièce non maîtrisée |
| jamais montée | au catalogue, montée nulle part : un référencement qui dort |

L'arbre suit l'ordre dans lequel on cherche une pièce : **famille → fonction →
norme → référence**. On sait ce qu'on veut faire avant de savoir sous quelle
norme le chercher. Chaque niveau porte ses comptes, et une norme servie par
plusieurs références montées est marquée « dispersée ».

Le rail de gauche filtre par famille ; la bande de tête filtre par état — les
tuiles « montée une fois », « hors catalogue » et « jamais montées » sont des
boutons. Les premières fonctions, les plus montées, sont ouvertes ; la traîne
est repliée, et un bouton fait basculer l'ensemble. Ni mur, ni page vide.

## Pas de duplication

Ni pour une boîte, ni pour un sous-ensemble. Recopier un élément pour en
changer le PN derrière n'était un raccourci pour personne : on crée, on
remplit. Les boutons ont été retirés, ainsi que l'action client, la liaison
et la fonction serveur, qui n'avaient plus d'appelant.

Les **suppressions**, elles, passent par un **dialogue intégré**
(`Dialogues.html`). Les fenêtres natives `prompt()` et `confirm()` sont
bloquées dans l'iframe sandboxée d'Apps Script : c'est pour cela que
« Supprimer » ne faisait rien, sans le moindre message. Plus aucun appel
natif ne subsiste.

## Saisie guidée : les trois niveaux se resserrent

Un composant s'écrit `Fonction | Norme | Référence`. Les trois champs étaient
indépendants : sous « Bouton poussoir », la liste Norme proposait `NSA 5512`,
qui est une norme de colonnette. On suggérait donc des combinaisons qui
n'existent pas.

Un index `fonction → normes → références` est construit à chaque
rafraîchissement, à partir du catalogue **et** de tout ce qui est déjà saisi.
Écrire « Bouton poussoir » restreint la liste Norme à ses trois normes ;
choisir l'une d'elles restreint la liste Référence aux siennes. Chaque bloc de
saisie porte ses propres listes : le bloc de la boîte et celui de la structure
ne se gênent pas.

Une fonction **encore inconnue** ne restreint rien. On guide la saisie, on ne
l'enferme pas : un composant qui n'existe pas encore dans la base doit pouvoir
s'écrire.

## Une double espace ne fait pas deux composants

`normaliserTexte()` ramène les espaces internes à un seul. Sans cela,
« Bouton  poussoir » et « Bouton poussoir » étaient deux fonctions distinctes :
deux familles dans la vue Standardisation, un score de 0 à la comparaison, et
deux entrées dans les suggestions. Une frappe de trop ne doit pas scinder une
famille.

## Doublons : ce qui les sépare

Un PN, un autre PN, un score : cela disait qu'il fallait regarder, pas quoi
regarder. Chaque paire montre désormais **ce qui les sépare** et **ce qui
concorde**, critère par critère, avec les deux valeurs en regard — et nomme ce
qui n'a pas pu être comparé faute de donnée. Un bouton ouvre la comparaison
complète, pondération comprise.

L'intérêt est rappelé en tête : deux PN pour la même chose, c'est deux pièces à
approvisionner, qualifier et stocker au lieu d'une.

## Le balayage des doublons, et ce qu'il coûte

Comparer chaque paire de sous-ensembles du même type est quadratique. Il faut
donc un plafond, mais l'ancien — 400 paires — correspondait à **29
sous-ensembles du même type** : toute base réelle passait dessous et
l'indicateur restait à « — », sans rien dire. Mesuré : 21 000 paires
(≈ 120 boîtes) tiennent en 0,6 s, ce qui convient pour une action déclenchée au
clic. Le plafond est là.

Au-delà, l'indicateur ne se tait plus : il affiche « trop de pièces : filtrez
d'abord », et la liste explique que **le balayage suit la sélection affichée** —
une recherche, un statut, un porteur, et il repart.

## L'état initial ne doit pas produire un zéro silencieux

`Store.poids` et `Store.criteresActifs` partent vides et ne sont remplis que par
`chargerReglages()`. Tout ce qui y touchait avant : soit plantait
(`reglerPoids`), soit rendait un score de 0 sur tout, sans message. Un classement
entièrement à zéro se lit « rien ne se ressemble », alors que cela voulait dire
« rien n'a été comparé ». Les deux tables s'initialisent désormais à la demande,
sur les valeurs du registre.

## Un geste de moins, partout

Une liste fermée s'ajoute **au choix** : choisir un porteur, c'est le vouloir,
il n'y a rien à confirmer derrière. Le bouton « Ajouter » ne subsiste que sur
les champs libres, où taper **Entrée** fait la même chose — et où choisir une
suggestion de la liste ajoute directement.

La recherche par composants n'a plus de bouton du tout : on choisit ou on
tape Entrée, la puce se pose, **le filtre s'applique derrière la fenêtre
restée ouverte**. Empiler trois critères ne demande plus d'ouvrir et fermer
trois fois.

Le catalogue ne se referme plus après un ajout : poser trois colonnettes,
c'est trois clics, pas neuf. Et après chaque écriture, la fiche étant
recomposée, **le focus revient dans le champ qu'on utilisait** : saisir cinq
composants d'affilée ne demande plus cinq clics de replacement.

« Supprimer » a quitté le mode édition, pour la boîte comme pour le
sous-ensemble : c'est une action **sur la fiche**, pas un champ de
formulaire. On ne passe plus en édition pour effacer.

## Porteurs

La liste des porteurs est **fermée** : tous les porteurs Airbus Helicopters,
définis une fois dans `Config.gs` (serveur) et `Types.html` (repli client), et
rien d'autre — plus de « Multi ». Une boîte porte autant de porteurs qu'il en
faut, cochés à la création ou ajoutés depuis la fiche.


## Parti pris visuel

**La couleur porte une information, ou elle structure la page.** Trois teintes
de type (structure, harnais, plaquette), trois teintes de statut, trois niveaux
d'équivalence : c'est la couleur qui signifie. À côté, une seule teinte de
marque, un marine, réservée aux actions principales et aux états actifs.

**Le sol est blanc.** C'est lui qui donne l'impression de propreté, et il le
reste sous le titre comme dans le corps de page. La couleur est portée par les
**objets** posés dessus : les cartes prennent un voile bleu-gris, celui des
panneaux d'aéronef et des plans, et la barre d'action une teinte plus
soutenue. Rien ne colore le fond.

**Les indicateurs sont une ligne, pas une rangée de cartes.** Cadrée de deux
filets, chaque mesure séparée de la suivante par un trait fin : les chiffres
se lisent d'une traite, comme une plaque de relevés. Chacun reste un filtre.

**Une barre d'action coupe la page en deux.** Pleine largeur, teintée, filet
marine au-dessus, elle sépare l'en-tête du catalogue et réunit les deux façons
d'entrer dans les données : chercher, ou créer. Le bouton de création vit là,
et non à côté du titre, où il n'avait rien à faire.

Typographie ancrée dans le sujet : **Archivo** très tracké pour le titre, à la
manière d'une plaque d'aéronef ; **IBM Plex Mono** pour les PN, qui sont de la
donnée et s'alignent en colonne ; **Instrument Sans** pour le reste.

Les commandes secondaires ne sont plus des boutons posés à côté : la recherche
par composant vit **dans** le champ de recherche, le tri est un menu discret
aligné avec le nombre de résultats, les filtres de type sont des jetons colorés
par le type qu'ils désignent.

## Images

Le champ Image attend une **URL de photo** (lien direct ou lien Drive, converti
en miniature). Rien n'est dessiné : sans URL, la carte affiche « Pas de photo ».
L'aperçu Artifact bloque les images externes ; elles s'affichent dans
l'application.

## Indicateurs

Ils appartiennent à l'espace affiché. Garder ceux des boîtes en consultant les
composants faisait lire les mauvais chiffres : on croit que « 13 boîtes »
qualifie ce qu'on a sous les yeux. Quatre de chaque côté, jamais sept.

| Espace Boîtes | Espace Composants |
|---|---|
| Boîtes — *tout réafficher* | Références — *relâcher les filtres* |
| Validées — *ne montrer qu'elles* | À ranger — *les fonctions dispersées* |
| À standardiser — *la vue correspondante* | Hors catalogue — *les pièces non référencées* |
| Doublons probables — *la liste, au-dessus de 95 %* | Montées une fois — *l'appro isolé* |

Les filtres par **état** et par **emploi** vivent au rail de gauche, avec les
familles : ce sont des filtres, pas des alertes, et les compter en gros
chiffres noyait le reste.

## Déploiement

```bash
npm install -g @google/clasp
clasp login
clasp clone <ID_DU_SCRIPT>     # ou clasp create --type sheets
clasp push
```

Apps Script accepte le `/` dans les noms de fichiers : `client/Dom.html` apparaît
comme un dossier dans l'éditeur, et `include('client/Dom')` le résout.

### Sans clasp, depuis le navigateur

1. Nouveau Google Sheet → **Extensions › Apps Script**.
2. Renommer `Code.gs` si besoin, et y coller `build/appsscript/Code.gs`
   (tout remplacer).
3. **+ › HTML**, nommer le fichier `Index` (sans `.html`, l'éditeur l'ajoute),
   y coller `build/appsscript/Index.html`.
4. Enregistrer. Il ne doit y avoir que ces deux fichiers.

### Ensuite, **une fois**, quelle que soit la méthode

1. Importer `build/appsscript/catalogue.csv` dans un **nouveau** classeur
   (Fichier › Importer › Importer les données), et copier son URL.
2. Éditeur Apps Script → ⚙ Paramètres du projet → Propriétés du script →
   ajouter `URL_CATALOGUE` = l'URL de ce classeur. Elle n'est plus en dur
   dans le source.
3. Recharger le Sheet → menu **NEXUS PLM** → *Créer / compléter la structure*.
   (Puis *Réinitialiser avec le jeu de démo…* pour avoir de quoi regarder.)
4. Déployer › Nouveau déploiement › **Application web**. Autoriser les accès
   à la première exécution.

Si l'application se charge mais qu'aucune fenêtre ne s'ouvre, c'est que le
réseau bloque `cdn.jsdelivr.net` : Bootstrap n'est pas chargé. Dans ce cas,
inliner Bootstrap dans `Index.html` comme le fait `build/build-demo.js`.

Le manifeste fixe `access: "DOMAIN"` : l'application n'est accessible qu'aux
comptes du domaine. À adapter si besoin, mais pas à élargir sans raison.

## Ce qui a changé

### Les 6 bugs confirmés

| | Correction |
|---|---|
| Catalogue ajoutant le mauvais composant | l'index réel est conservé, plus celui de la liste filtrée |
| Aucun `withFailureHandler` | un seul passe-plat `appelerServeur`, bandeau d'erreur, arrêt des indicateurs |
| « Invalidé » compté comme validé | liste fermée + égalité stricte, et validation à la saisie |
| Export CSV cassé | `Blob` au lieu de `data:`+`encodeURI`, guillemets doublés, BOM UTF-8, séparateur `;` |
| Compteur d'onglet incohérent | un seul filtrage dont tout dérive |
| « undefined » affiché | helper `txt()` |

### Les fragilités structurelles

- **Échappement** — `esc()` partout, délégation d'événements, plus un seul
  `onclick` en ligne. Un test vérifie qu'un PN piégé (`332"P<script>…'A`)
  traverse l'affichage et revient intact.
- **Identité** — le numéro de ligne ne quitte plus le serveur. Le client envoie
  `PN Global` ou `ID_Ligne`, le serveur résout au moment de l'écriture. Deux
  suppressions rapprochées ne peuvent plus viser la mauvaise ligne.
- **Concurrence** — `LockService` sur toutes les mutations.
- **Comparateurs** — calcul séparé du rendu, pondérations dans `POIDS`. Les deux
  bugs de scoring sont corrigés : un critère non mesurable sort du dénominateur
  **et** est affiché comme tel. Un taux de **couverture** dit sur quelle part des
  critères le score a été calculé.
- **Recherche** — index sur les valeurs seules. `image`, `commentaires`,
  `rowindex` ne ramènent plus tout. Recherche multi-mots, avec anti-rebond.
- **Performances** — écriture par lot (1 appel par ligne au lieu d'un par
  colonne), retours différentiels au lieu de relire les deux feuilles à chaque
  frappe, catalogue en `CacheService`.
- **Sécurité** — `XFrameOptionsMode.DEFAULT`, URL du catalogue en Script
  Property, validation serveur, journal `9_JOURNAL` (qui, quoi, quand).
- **Divers** — `.max-width-xl` enfin définie, panneau latéral responsive,
  `initialiserBaseDeDonnees` scindée en une version sûre et une version
  destructive à confirmation écrite, conversion Drive dédupliquée (elle était
  copiée 3 fois), annulation d'édition possible.

### Fonctions

Les 10 fonctions serveur et les ~34 fonctions client d'origine sont toutes
conservées. Renommages principaux :

| Origine | Devient |
|---|---|
| `getToutLeContenu` | inchangé |
| `saveLigne(feuille, rowIndex, modifs)` | `saveBoite(pn, modifs)` / `saveNomenclature(id, modifs)` |
| `deleteLigne(feuille, rowIndex)` | `deleteNomenclature(id)` |
| `deleteBoiteEntiere(pn, rowIndex)` | `deleteBoiteEntiere(pn)` |
| `addBoiteLibre` / `addSousEnsembleLibre` | `addBoite` / `addSousEnsemble` |
| `initialiserBaseDeDonnees` | `creerStructureSiAbsente` + `reinitialiserAvecDemo` |
| `filtrerInterface` | `calculerVue` + `rendreInterface` |
| `comparerBoite` / `comparerSousEnsemble` | `equivalencesBoite` / `equivalencesSousEnsemble` |
| les `toggleEdit*` | actions `editer-*` / `annuler-*` / `sauver-*` |

Ajouts : annulation d'édition, filtre par composants affiché et retirable,
taux de couverture des scores, journal des modifications.

## Réserve

Le code d'origine m'est parvenu via un PDF : l'extraction a perdu les emojis
(icônes ✅/❌ des comparateurs) et introduit des retours à la ligne. Les icônes
sont remplacées par `✓ ≈ ✗ –`. **Avant de pousser, comparer avec les fichiers
authentiques** — notamment si des colonnes ont été ajoutées au Sheet depuis.

Deux points à valider en conditions réelles, non testables hors navigateur :

1. **Téléchargement CSV** — l'interface tourne dans une iframe sandboxée ;
   selon le navigateur un téléchargement déclenché par script peut être bloqué.
   C'était déjà le cas avant. Repli : `window.open(url)` ou génération du fichier
   dans Drive côté serveur.
2. **Séparateur `;`** — adapté à Excel FR. À passer à `,` dans `Dom.html`
   (`CSV_SEPARATEUR`) si les fichiers alimentent un outil attendant la virgule.
