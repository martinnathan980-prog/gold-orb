# Suivi FWD — mise en place et usage hebdomadaire

## 1. Installer le script (une seule fois)

Dans le classeur Google Sheets :

1. **Extensions → Apps Script**.
2. Créer les fichiers suivants et y coller le contenu de ce dossier, à
   l'identique. Le nom compte : Apps Script retrouve les fichiers par leur nom.

   | Dans Apps Script | Type | Fichier à coller |
   |---|---|---|
   | `Code.gs` | Script | `Code.gs` |
   | `Index` | HTML | `Index.html` |
   | `Styles` | HTML | `Styles.html` |
   | `Javascript` | HTML | `Javascript.html` |

   Pour créer un fichier HTML : **+ → HTML**, puis saisir le nom **sans**
   l'extension (`Index`, et non `Index.html`).

3. Facultatif mais recommandé : **Projet → Paramètres → Afficher
   « appsscript.json »**, puis y coller `appsscript.json`.
4. **Enregistrer**, puis recharger le classeur.

Un menu **Suivi FWD** apparaît dans la barre du haut.

La première ouverture demande une autorisation Google : c'est normal, le script
lit le classeur et y écrit les onglets d'historique.

**Suivi FWD → Diagnostic** vérifie tout d'un coup : les fichiers, chaque
contrat (onglet, ligne d'en-têtes, colonne d'avancement, colonnes analysées,
relevés archivés), les jalons de configuration et le poids du paquet envoyé à
la page. C'est le premier réflexe quand quelque chose ne s'affiche pas.

## 2. Ouvrir le tableau de bord

**Suivi FWD → Ouvrir le tableau de bord.**

Pour le partager à quelqu'un qui n'ouvre pas le classeur :
**Déployer → Nouveau déploiement → Application Web**, exécuter en tant que
soi-même, accès selon la politique de l'entreprise. Le lien obtenu ouvre la
même page.

C'est un outil de **consultation** : la page ne modifie rien dans le classeur,
et rien de ce qu'on y clique n'est visible par les autres. Ce que voit la
collègue, sa chef le voit aussi.

## 3. Les contrats : un onglet visible par contrat

Chaque onglet **visible** du classeur est un contrat, et **le nom de l'onglet
est le nom du contrat** : un onglet `X1` donne le contrat « X1 » dans la page.
Rien à configurer : ajouter un onglet, y coller un export, c'est un contrat de
plus.

Ne sont jamais pris pour des contrats : les onglets masqués, les onglets
**vides** (la « Feuille 1 » d'un classeur neuf, restée à côté), les onglets
d'historique (`Historique_FWD…`), l'onglet de la seconde base s'il est nommé
(voir § 12) et les onglets de service (`Paramètres`, `Config`). Sans aucun
contrat, le message nomme les onglets vides et dit le geste : coller l'export
GATES en A1 d'un onglet nommé du contrat.

Dans la page, un **sélecteur « Contrat »** dans le bandeau du haut passe de
l'un à l'autre sans recharger ; le titre ne le répète pas. Avec un seul
onglet, le sélecteur n'apparaît pas. La page
s'ouvre toujours sur le **premier** onglet, dans l'ordre du classeur ; les
autres se chargent à la demande. Un contrat qui ne peut pas être lu laisse la
page sur le contrat courant et affiche le message du classeur.

Pour imposer un contrat unique quel que soit le nombre d'onglets, en haut de
`Code.gs` :

```js
FEUILLE_DONNEES: 'Données',
```

## 4. Le geste de chaque semaine

1. Dans GATES, exporter la liste de chaque contrat — en Excel de préférence :
   les cellules fusionnées de la ligne des groupes voyagent avec, et c'est
   par le groupe « Réalisation FWD » que la bonne colonne « Avancement » se
   reconnaît (§ 7).
2. Ouvrir l'onglet du contrat, `Ctrl+A`, `Suppr`, puis coller l'export
   en **A1**. Même chose pour chaque contrat.
3. **Suivi FWD → Archiver le relevé de cette semaine.** Une boîte confirme :
   « Relevé S39 archivé : HDK (186 plans), THS (93 plans). Un second
   archivage dans la semaine remplace celui-ci. »

C'est tout. L'archivage passe sur **tous les contrats d'un coup**, une ligne
par contrat dans son propre onglet d'historique. Un onglet illisible n'empêche
pas les autres d'être relevés : l'erreur le nomme, et les autres sont
archivés.

L'étape 3 peut se faire toute seule : **Suivi FWD → Activer l'archivage
automatique (vendredi 17 h)**, et un relevé est pris chaque vendredi entre
17 h et 18 h (heure du fuseau du projet Apps Script).

Les étapes 1 et 2 aussi : voir **§ 15, l'automatisation** — un script récupère
les extracts dans Chrome et les dépose dans le classeur, qui archive la
semaine dans la foulée.

## 5. Ce que devient l'historique

GATES ne donne qu'une photo du jour : l'export ne dit pas *quand* un plan est
passé à 100 %. L'historique ne peut donc pas être reconstitué après coup — il
s'accumule, un relevé par semaine, **par contrat**, dans un onglet masqué
**`Historique_FWD_<nom du contrat>`** (`Historique_FWD_X1` pour l'onglet `X1`).

- Un seul relevé par semaine ISO : réimporter le lundi puis le jeudi met la
  ligne à jour, elle ne se dédouble pas.
- **Rien n'est jamais supprimé ni réécrit.** Chaque relevé garde les comptes
  globaux, les comptes par colonne, et l'avancement plan par plan. Tout ce que
  la page dérive de l'historique (périmètre, groupes, changements d'indice)
  se calcule à la lecture, à partir de ces cartes plan par plan ; l'onglet,
  lui, n'est jamais retouché.
- Mauvais export collé par erreur ? **Suivi FWD → Supprimer le relevé de cette
  semaine** retire la semaine courante de tous les contrats et récapitule ce
  qui a été retiré ; recoller le bon, ré-archiver.

Un classeur d'avant les contrats, qui porte encore l'ancien onglet
**`Historique_FWD`** tout court, continue de s'en servir tant qu'il n'a qu'un
seul contrat : rien n'est renommé, rien n'est reconstruit. Dès qu'un second
onglet de contrat apparaît, cet ancien onglet n'appartient plus à personne ;
le **Diagnostic** le signale, et il suffit de le renommer
`Historique_FWD_<nom>` pour rendre ses relevés au contrat qui les a produits.

Pour consulter un onglet d'historique : clic droit sur un onglet → *Afficher
les feuilles masquées*. Le remasquer ensuite n'est pas obligatoire : un onglet
dont le nom commence par `Historique_FWD` n'est jamais pris pour un contrat.

## 6. Ce que le script devine tout seul

Aucun nom de colonne n'est écrit en dur.

- **La ligne d'en-têtes** est cherchée dans les huit premières lignes : les
  lignes de titre de l'export ne gênent pas.
- **La ligne au-dessus** est prise pour des groupes de colonnes fusionnés, et
  propagée vers la droite.
- **L'avancement FWD** est la colonne dont l'en-tête ou le groupe parle de FWD
  et d'avancement.
- **La référence** est la colonne qui identifie un plan ; elle reste figée à
  gauche du tableau.
- **Le domaine** (`BASE/OPTION`, `PERSO`…) est la colonne dont l'intitulé
  parle de domaine ; il alimente le périmètre du bandeau du haut.
- **Les dimensions** de « Avancement FWD par… » sont les colonnes qui se
  comportent comme des catégories : entre 2 et 40 valeurs distinctes. Une
  colonne de commentaires ou d'identifiants en est donc exclue d'office.
- **La date de création**, si elle existe, ajoute la dimension « ancienneté ».

Si les colonnes de l'export changent, il n'y a rien à modifier : recoller et
ré-archiver suffit.

## 7. Sur l'export GATES réel

Relevé sur `export_48.xlsx` : **138 colonnes**, en-tête en **ligne 2**, ligne de
groupes fusionnés en ligne 1, données à partir de la ligne 3.

| | |
|---|---|
| Colonnes | 138, dont **91** sont 13 répétitions du même bloc de 7 (une par variante HDK AA) |
| Groupes | 16 plages fusionnées + 2 cellules isolées (`Concept Harnais`, colonnes 40 et 41) |
| Sans intitulé | colonnes 1, 4 et 5 — nommées « Colonne 1 », « Colonne 4 », « Colonne 5 ». Seule la **première** est retirée à l'affichage (c'est Excel qui l'ajoute) ; 4 et 5 restent, même vides : le tableau est la structure exacte de GATES |
| Référence figée | `Référence UD`, colonne **2** (pas la 1) |
| **Avancement FWD** | `Avancement Définition Electrique`, groupe `HDK AA 011` (`CONFIG.COLONNE_FWD`) |
| **Concept harnais** | `Avancement Concept Harnais`, groupe `HDK AA 011` (`CONFIG.COLONNE_CONCEPT`) |
| Domaine | `Domaine` — le périmètre du haut de page |

**Vingt-sept colonnes ont un intitulé contenant « avancement ».** Le FWD se
suit dans **`HDK AA 011 > Avancement Définition Electrique`** — et non plus
dans `Réalisation FWD > Avancement`, qui reste une colonne du tableau comme
les autres. C'est `CONFIG.COLONNE_FWD` qui le dit, groupe compris : les
treize blocs HDK AA portent tous les mêmes intitulés, et c'est le groupe
fusionné au-dessus qui départage — le script lit les **vraies fusions** de
la feuille. Un extract sans bloc `HDK AA 011` retombe sur la détection
(`Réalisation FWD > Avancement`), et le **Diagnostic** le dit en toutes
lettres : « ⚠ La colonne demandée … est introuvable ».

### Définition électrique ou concept harnais

`CONFIG.COLONNE_CONCEPT` nomme le second avancement suivi,
`HDK AA 011 > Avancement Concept Harnais`. Quand l'extract le porte, la page
affiche en haut l'interrupteur **Définition électrique | Concept harnais**,
et **toute la page suit** la colonne choisie : la barre, la courbe et son
historique, le journal, le bloc par groupe (« Concept harnais par ATA »), le
filtre des états, le tableau (c'est la colonne suivie qui porte la pastille
d'état). Le titre devient **« Suivi concept harnais »**. SEE ne connaît pas
le concept harnais : sous lui, la **comparaison avec SEE disparaît** — la
section comme l'interrupteur GATES | SEE du tableau — et revient avec la
définition électrique. Changer d'avancement retire les filtres posés — un
« terminé » n'a plus le même sens — et garde le cadre : périmètre, fenêtre du
graphique, regroupement.

L'archivage garde **les deux valeurs de chaque plan** : la carte d'un relevé
porte `[définition, concept]` par référence. Les relevés d'avant n'ont que
la définition ; ils se relisent tels quels, et **la courbe du concept
commence au premier archivage qui l'a gardé** — un historique ne se
reconstitue pas. Les deux colonnes se lisent avec les mêmes règles que
l'avancement FWD (§ 11) : `Terminé`, `En cours`, `À faire`, les
pourcentages ; une autre façon d'écrire se range en « en cours ».

Autres points tenus par le code :

- **Les lignes sans référence sont écartées.** L'export en intercale sous
  l'en-tête.
- **Une cellule de date arrive en objet `Date`**, pas en texte. Elle est ramenée
  au jour (`2017-05-02`) : sinon elle s'écrirait
  `Wed May 03 2017 00:00:00 GMT+0200 (…)`, déborderait de sa colonne, se
  trierait de travers et ne serait même pas reconnue comme une date.
- **Les booléens valent `true` / `false`.** Le tableau les montre tels quels —
  c'est l'extract. Dans le bloc d'analyse, où la valeur devient un nom de
  groupe lu par tout le monde, ils s'écrivent **Oui** / **Non**.
- **Les 138 colonnes sont lues et transmises à la page**, dans l'ordre de la
  feuille, y compris les 91 des blocs HDK AA répétés et les colonnes sans
  intitulé.
- **Le tableau en montre 137.** Une seule règle, décidée par l'utilisatrice :
  une colonne que le script a dû nommer lui-même faute d'intitulé
  (« Colonne N ») **et** qui ne porte aucune valeur sur aucune ligne est
  retirée de l'affichage. Sur l'export réel c'est « Colonne 1 », vide de bout
  en bout ; « Colonne 4 » et « Colonne 5 » restent tant qu'elles portent au
  moins une valeur — ce que la feuille de test suppose, et qui reste **à
  confirmer sur `export_48.xlsx`** : si elles étaient vides elles aussi, la
  règle les retirerait et le tableau en montrerait 135. Le modèle du serveur
  garde ses 138 colonnes : c'est la page qui trie, à l'ouverture.

### Les colonnes analysées

Dans « Avancement FWD par… », dans l'ordre de la configuration :

| Colonne | Ce qu'elle montre |
|---|---|
| **ATA** | le découpage attendu, ouvert par défaut |
| **CC** | code circuit |
| **ECP** | |
| **Date création (par mois)** | un groupe par mois, rangés dans l'ordre du temps ; s'ajoute d'elle-même |

Deux colonnes calculées : **fin estimée** (« S18 · mai 2027 »), puis
**rythme requis** quand un jalon est à venir — en plans par semaine, rouge
quand le rythme tenu, écrit dessous, ne suffit pas —, **rythme tenu** sinon.
Ces deux colonnes viennent de l'historique : elles portent sur tous les plans
du groupe, et une note le dit quand un autre filtre réduit les lignes. Le bloc a une hauteur bornée :
au-delà d'une dizaine de lignes, on descend dedans plutôt que d'allonger la
page.

**Un champ de filtre**, à côté du sélecteur de dimension, ne garde que les
lignes dont le nom de groupe contient ce qu'on tape (« Filtrer les ATA… ») :
il n'agit que sur ce bloc, un compte « n sur m » dit ce qu'il retient, `Échap`
le vide, changer de dimension le vide aussi. Rien n'en est retenu.

**Choisir une ligne déplie toutes ses références**, sans coupure, en deux
paquets : **Pas encore terminés (n)** — à faire, non renseignés, en cours —
puis **Terminés (n)**, chacun rangé par référence, une pastille par état. Un
clic sur une référence réduit le tableau du bas à ce plan. Le bloc défile :
640 références dans un seul groupe restent lisibles.

Chaque colonne calculée porte un **?** qui ouvre la même explication chiffrée.

Pour changer la liste, une ligne en haut de `Code.gs` :

```js
DIMENSIONS: ['ATA', 'Séquence', 'CC', 'ECP'],
```

La syntaxe `Groupe > Colonne` sert quand plusieurs colonnes portent le même
intitulé. Liste vidée, la détection automatique reprend la main.

Les autres réglages du même bloc :

```js
COLONNE_FWD: 'Réalisation FWD > Avancement',
COLONNE_DOMAINE: 'Domaine',
COLONNES_ESSENTIELLES: ['Nom Installation', 'ECP', 'ATA', 'Séquence',
                        'Validation Définition Electrique', 'Date création',
                        'Réalisation FWD > Avancement'],
```

### Revenir en arrière

Dès qu'un filtre est posé — un périmètre, un état, un groupe, une référence,
une recherche, un filtre de colonne, un lot du comparatif ou du rapprochement —
un **bandeau collé en haut de la page** nomme chacun d'eux et donne sa croix,
avec un **Tout effacer**. Où qu'on ait cliqué, la sortie est à portée.

### Les deux vues du tableau

Un interrupteur au-dessus du tableau, et rien entre les deux :

- **Toutes les colonnes** (au départ) : l'extract tel quel. Les 137 colonnes
  (voir plus haut), les mêmes intitulés, **l'ordre de la feuille** — à une
  exception près : la **colonne suivie** (l'avancement FWD, ou le concept
  harnais) vient juste après la référence et reste figée avec elle, pour
  lire l'état d'un plan sans faire défiler le tableau.
  C'est la vue de référence, celle sur laquelle tout le monde parle de la même
  chose.
- **Vue essentielle** : la poignée de colonnes qu'on regarde vraiment —
  référence, nom d'installation, ECP, ATA, séquence, validation définition
  électrique, date de création, avancement.

Il n'y a plus de bouton « Choisir » ni de panneau pour masquer une colonne à la
main : deux lectrices regardent toujours le même tableau. Le glisser-déposer
des colonnes et le tri restent.

Le bloc figé à gauche couvre tout ce qui précède la référence, elle comprise,
et la colonne suivie. Sur l'export réel, la seule colonne qui la précédait est
la « Colonne 1 » retirée : la référence ouvre donc le tableau, l'avancement
la suit. Ni l'une ni l'autre ne se déplace, et rien ne se dépose devant.

### Plus de mode « Exemple »

Il n'y a plus d'interrupteur **Données réelles / Exemple** : devant un
classeur, la page ne montre **que** ce que le classeur contient, rien de
fabriqué.

- **le classeur a des plans** : ce sont eux, et l'historique est celui des
  relevés archivés — un seul relevé donne un graphique à un point, et le
  journal attend le relevé suivant pour dire ce qui a bougé ;
- **le classeur n'a encore rien donné** — pas d'onglet de contrat, feuille
  vide — : à la place des sections, un panneau **« Le classeur est vide »**
  rappelle les trois gestes (un onglet au nom du contrat, l'extract collé
  en A1, Actualiser), et l'alerte dit ce qui manque.

Le jeu de trois contrats fictifs (HDK, THS, VRK) ne vit plus que dans la
**démonstration seule** (`prototype/`, l'artifact) : un mot « Démonstration »
le dit en tête de page. Le script de construction le retire des fichiers de
l'add-on, qui en sont d'autant plus légers.

## 7 bis. La semaine sous le titre

Sous « Suivi FWD », la page écrit la semaine **où l'on est**, avec ses dates :
« Semaine 39 · du 21 au 27 septembre 2026 ». Elle vient de la date du jour,
pas des données — il n'y a rien à tenir à la main.

Le titre ne dit **que** la semaine en cours : pas de mention du dernier
relevé à côté. Les chiffres de la page, eux, sont ceux du **dernier relevé
archivé** — c'est le graphique qui le dit : son trait vertical ne s'appelle
« aujourd'hui » que si ce relevé est de cette semaine, sinon il dit
« dernier relevé ».
Une page laissée ouverte reprend tout cela au retour sur l'onglet, et une
fois par heure.

La démonstration, elle, est **datée** : son historique s'arrête à la semaine
38 de 2026, en face des jalons du programme, qui sont des dates fixes. Son
trait dira donc « dernier relevé » — c'est exact, et c'est le signe qu'il
faudra rafraîchir le jeu de démonstration en même temps que les jalons.

## 8. Le périmètre : Tout / BASE/OPTION / PERSO

Le titre reste seul dans sa zone : le sélecteur est posé **à droite de la
phrase « N sur M plans terminés »**, juste au-dessus de la barre d'avancement
qu'il gouverne (à la ligne, à gauche, sur un petit écran) : **« Tout »**, puis
une puce par valeur de la colonne de domaine, chacune avec son compte de
plans. Il est masqué quand l'export n'a pas de colonne de domaine.

Le périmètre pilote **toute la page** : la barre et les états, la phrase, le
comparatif « depuis le relevé précédent », la courbe et sa bulle, le journal, le bloc par
groupe, le rapprochement, le tableau et son « sur N ». Choisir PERSO, c'est
regarder une page qui ne parle que des plans PERSO.

La courbe sous un périmètre n'est pas un filtre sur des comptes figés : elle
est **dérivée**, relevé par relevé, de la carte plan par plan archivée,
croisée avec le domaine **courant** de chaque plan (total = plans de la carte
dans le périmètre, terminés = ceux classés terminés). Les rythmes du bloc par
groupe passent par la même dérivation. L'onglet d'historique n'est jamais
réécrit pour cela.

La limite : un relevé archivé **sans carte plan par plan** ne peut pas être
dérivé. Il est écarté sous un périmètre et la note sous le graphique le dit
(« n relevés sans détail plan par plan, hors périmètre »). Sous « Tout », rien
ne change : ce sont les comptes archivés.

Le bandeau des filtres actifs nomme le périmètre en premier ; sa croix,
« Tout effacer » ou le bouton **Tout** y reviennent. Il n'est pas mémorisé : la
page ouvre toujours sur Tout, et un changement de contrat aussi.

## 9. Les références UD et les changements d'indice

Une référence UD se lit par morceaux. Sur `TFE2130A600001A` :

| `TF` | `E` | `2130` | `A` | `600` | `001` | `A` |
|---|---|---|---|---|---|---|
| code circuit | toujours `E` | ATA et sous-ATA | toujours `A` | séquence | solution | indice |

- la **séquence** dit où : `600` côté pilote, `700` côté copilote, `800` les
  boîtes ;
- la **solution** (3 chiffres) : une autre solution, c'est un autre plan ;
- l'**indice** (une lettre) change à chaque réémission du même plan.

La page appelle **racine** les six premiers morceaux jusqu'à la séquence
(`TFE2130A600`) et lit la référence sur ce gabarit : 3 caractères, 4 chiffres,
`A`, 3 chiffres, puis la solution et l'indice.

L'identité d'un plan, c'est **racine + solution**. Seul l'indice bouge sans
changer de plan.

La page lit cette forme en tolérant les séparateurs (`-`, `_`, espace, point,
`/`) et la casse : `hel0225a017-001-a` est le même plan. Une référence qui ne
suit pas ce format garde sa forme entière comme racine et n'est jamais
appariée à une autre.

Comparer deux relevés par racine + solution change ce qu'on voit : un plan
réémis sous un autre indice n'est plus « un disparu plus un nouveau », c'est
un **changement d'indice**. Une référence qui change de solution reste ce
qu'elle est : un plan disparu et un nouveau plan.

- **Dans le comparatif** « depuis le relevé précédent », un lot *changements d'indice*
  (pastille violette), cliquable comme les autres, filtre le tableau sur les
  nouvelles références ; son survol montre « ancienne → nouvelle ». Un plan
  réémis compte une fois, sous ce lot, même s'il change aussi d'état : la
  bulle et le journal montrent l'état avant et après.
- **Dans le journal**, la ligne se lit « ancienne → nouvelle », avec l'état
  avant et après ; chaque semaine compte ses changements d'indice, et le
  filtre du journal les propose.
- **Dans la bulle du graphique**, ils figurent parmi les comptes de la
  semaine.

Le tableau montre toujours la référence **courante** ; le journal garde
l'ancienne.

## 10. Le journal des changements

Chaque relevé archivé garde l'avancement **plan par plan**. Comparer deux
relevés successifs donne, semaine par semaine, qui a bougé et dans quel sens —
la seule chose que l'export du jour ne dira jamais.

Il est **sous le graphique**, dans la même section : la courbe dit combien, le
journal dit lesquels. Sa hauteur est bornée, on y descend.

Dans chaque semaine, les plans sont **rangés par état d'arrivée** : tous les
terminés, puis les passés en cours, puis les repassés à faire. Chaque ligne
ne dit que **quel plan est passé** : sa référence et son passage (« En cours
→ Validé »), sans le libellé de l'installation — il est dans le tableau.

- La semaine la plus récente est en haut, ouverte ; les autres se déplient
  d'un clic.
- `Tout / Terminés / En cours / À faire / Changement d'indice`, chacun avec sa
  pastille, ne garde que
  les passages voulus, et **chaque compte du résumé est cliquable** :
  « 6 terminés » n'affiche plus que ceux-là, sur toutes les semaines à la fois.
- Cliquer un plan réduit le tableau du bas à ce plan.
- Les nouveaux plans, ceux qui ont disparu de l'export et les changements
  d'indice sont signalés.
- **Survoler une semaine sur le graphique** en donne le résumé en chiffres :
  « Relevé de S38 · sept. 2026 », terminés sur total, le gain net sur le
  relevé précédent, puis **les lignes mêmes du journal** — « 20 passés à
  « Validé » », « 3 passés à « Non renseigné » », changements d'indice,
  nouveaux, disparus. Le comparatif du haut dit la dernière semaine avec ces
  mêmes lignes. La bulle ne liste pas de références : le journal, dessous,
  donne le détail.

Le journal se remplit au **deuxième** relevé : il faut deux relevés pour
savoir ce qui a changé entre les deux.

Le **changement d'indice** a sa couleur, un violet — ni un état ni une
alerte —, sur sa pastille (journal, filtre du journal, puce du comparatif) et
sur la nouvelle référence de la ligne ; la même couleur dit « autre indice »
dans la comparaison des bases.

## 11. Les valeurs de la colonne suivie

La page ne connaît pas d'avance les valeurs de la colonne : **elle les lit**.
Chaque valeur distincte — « Validé », « Check », « En cours », « A traiter »…
— devient un état affiché, **écrit comme dans l'extract**, avec son compte :
une part de la barre, un bouton de filtre, un bouton du journal. Un passage
d'une valeur à une autre compte comme un changement (« A traiter » → « Check »
aussi), et le journal le dit avec ces mots-là
(« passé à « Check » »). Une colonne qui change de vocabulaire change la page
avec elle, sans rien toucher.

Chaque valeur se range dans l'une de quatre **familles**, qui donnent sa
couleur et font la courbe :

| Famille | Ce qui l'y range |
|---|---|
| **Fini** | une valeur de `CONFIG.VALEURS_FINIES` (par défaut **`Validé`**), comparée entière — « Non validé » n'en est pas —, ou `100 %`, `terminé`, `achevé`, `clôturé`, `soldé`, `fini`, `ok` |
| **À faire** | `à faire`, `à traiter`, `non commencé`, `0 %` |
| **En cours** | tout pourcentage strictement entre 0 et 100, ou toute autre valeur (« Check », « En cours »…) |
| **Non renseigné** | cellule vide, `-`, ou `EMPTY` (tel que l'extract l'écrit) |

Plusieurs valeurs d'une même famille prennent la couleur de la famille, de
plus en plus claire. Seule la famille **fini** a un poids : c'est elle que
compte la courbe, le rythme requis par jalon, la comparaison avec SEE. Une
autre valeur qui voudrait dire « fini » s'ajoute à `VALEURS_FINIES`, en haut
de `Code.gs`. Le **Diagnostic** donne, pour chaque colonne suivie, les valeurs
lues avec leur compte et la mention « = fini » — de quoi vérifier d'un coup
d'œil (seulement des valeurs d'état : au-delà de vingt valeurs différentes,
ou de trente caractères, rien n'est recopié).

Une cellule vide reste un *défaut de saisie*, distinct de toute valeur : le
bouton « non renseigné » sous la barre sort la liste.

**Beaucoup de valeurs, ou de toutes petites.** Tant qu'elles tiennent, les
boutons des valeurs sont posés sous leur segment de la barre. Au-delà de
quatre valeurs, ou dès qu'un segment fait moins de quelques pixels (deux
plans sur six cents), ils passent en **légende** : une grille, une case par
valeur avec sa pastille, son nom, son nombre et sa part (« < 1 % » plutôt
que « 0 % »). Survoler une case — ou un segment — **éclaire** son segment et
estompe les autres : une valeur de deux plans se retrouve d'un coup d'œil.
Un clic filtre le tableau, comme avant.

## 12. Comparaison des bases de données : GATES et SEE

Une autre base suit les mêmes plans sous une autre structure. La seconde base
prévue est **SEE**, l'extract Excel de l'intranet (« Nommage WD BFLOW »).
**Chaque contrat a la sienne** : l'onglet `SEE HDK` sert au contrat `HDK`,
`SEE THS` à `THS` (`SEE - HDK`, `SEE_HDK`, `HDK SEE` valent aussi) ; un onglet
`SEE` tout court ne vaut que pour un classeur d'un seul contrat — devant
plusieurs, il n'est lu pour aucun, et le Diagnostic dit comment le renommer.
Un extract SEE : un
titre en ligne 1, les en-têtes en ligne 3, les données dessous, et la
référence UD répartie sur trois colonnes — **NAME** (la racine), **SOL.** (la
solution, trois chiffres) et **Cust.V** (l'indice, une lettre). Collé tel quel
dans un onglet de ce classeur et décrit dans la configuration, il donne deux
choses ; sans description, ni l'une ni l'autre n'existe.

**Ce que le rapprochement demande.** Dans SEE, un plan n'a pas d'état : soit
il y est, soit il n'y est pas. **S'il y est, c'est qu'il a été créé** — donc
terminé. La question posée est donc celle-là : *les plans que GATES dit
terminés, SEE les connaît-il, et réciproquement ?* La comparaison ne porte que
sur la **référence** ; les autres colonnes de l'extract s'affichent, elles ne
se comparent pas.

**La section « Comparaison des bases de données »**, sous le tableau des
plans, se lit comme on compare deux bases : deux cercles face à face, puis
plan par plan. Le titre suffit — plus de phrase ni de compte au-dessus, la
figure et les verdicts disent tout.

- la figure : le cercle **GATES** (plein, vert) à gauche avec son compte de
  plans et de terminés, le cercle **SEE** (pointillé) à droite avec ses
  lignes. Dans leur recouvrement, un **anneau** compte les plans que les deux
  bases connaissent, en trois parts à l'échelle — vert d'accord, violet autre
  indice, ambre connus de SEE mais pas terminés ici ; une part, même d'un seul
  plan, reste visible. À la première apparition d'une source, quand la section
  entre dans l'écran, les cercles s'installent et l'anneau se trace (rien de
  tout cela si le système demande moins de mouvement). À gauche du cercle
  GATES, en rouge, les **terminés que SEE ignore** — le nombre qui compte —,
  et dessous, dans le cercle, plus discret, ce qui n'est **pas encore** dans
  SEE (rien d'anormal : ces plans ne sont pas terminés). À droite, ce que SEE
  est seul à connaître (« tout le contrat » sous un périmètre, car ces lignes
  n'ont pas de domaine) ;
- à droite, six **verdicts**, un par ligne : la pastille, le grand nombre,
  puis une phrase de tous les jours qui se suffit à elle-même — plus de mot
  court en gras devant, il ne disait rien de plus. Un verdict à 0 se lit mais
  ne se clique pas :

| Ce que dit la page | Ce qu'il compte | Ce qu'il veut dire |
|---|---|---|
| terminés dans GATES et connus de SEE | terminé ici, présent là sous le même indice | tout va bien |
| dans SEE sous une autre lettre d'indice | terminé ici, présent là sous une autre lettre | une réémission d'un côté seulement |
| dans SEE, mais GATES ne les dit pas terminés | présent là, mais GATES ne le dit pas terminé | l'avancement GATES est peut-être en retard |
| terminés dans GATES, mais SEE ne les connaît pas | terminé ici, inconnu de SEE | à vérifier des deux côtés — c'est le lot qui compte |
| pas terminés, et pas encore dans SEE : rien d'anormal | pas terminé ici, pas encore créé là | rien d'anormal |
| lignes de SEE sans plan dans GATES | une ligne de là dont aucun plan du contrat n'a la racine et la solution | à regarder de près |

Le bandeau des filtres redit la même phrase (« Comparaison : terminés dans
GATES, mais SEE ne les connaît pas ») : ce qu'on vient de cliquer se relit
mot pour mot.

Cliquer un verdict filtre le tableau des plans ; les deux lots de plans que
SEE ne connaît pas l'emmènent sur GATES, celui des lignes que SEE est seule
à connaître sur SEE. Un seul lot à la fois ; le bandeau le nomme
(« Comparaison : … »), la croix le retire sans changer de côté. Un verdict se
**combine** avec les filtres du haut : « dans SEE, pas terminés ici » plus
l'état *En cours* ne garde que ceux-là.

Survoler un verdict — ou sa part de l'anneau, ou un nombre de côté —
l'éclaire dans la figure et ouvre une bulle : le compte, la part des terminés,
les paires « référence → solution et lettre », la répartition par état de
GATES, et où mène le clic.

**Plan par plan**, sous les cercles : un groupe par verdict, dans l'ordre
des priorités — d'abord ce qui est à vérifier (terminés absents de SEE, dans
SEE pas terminés ici, autre indice, seulement dans SEE), puis ce qui va (pas
encore dans SEE, terminés et dans SEE). À l'ouverture, **tous sont repliés** —
un clic sur la tête du groupe plie ou déplie. Cette tête porte la pastille, le nombre et
la même phrase que le verdict — rien d'autre. Dans un groupe, **une puce par
plan** : sa pastille d'état GATES, sa référence, et pour une réémission la
lettre sous laquelle SEE le connaît (« → B », en violet) ; douze plans
tiennent en deux lignes. La légende des pastilles (Terminé, En cours, À
faire, Non renseigné) est en tête de la liste, à droite du titre quand la
place le permet, dessous sinon. La bulle du survol dit le reste (« Terminé
dans GATES · absent dans SEE »). Pour « seulement dans SEE », la référence
recomposée, sans pastille. Les références sont triées, et un groupe déplié
montre **tous** ses plans — aucune coupure, aucun renvoi au tableau : quand
la liste dépasse la hauteur d'un écran, c'est la zone du groupe qui défile.
Un clic sur une référence d'ici
réduit le tableau GATES à ce plan (bandeau « Sélection : plan … ») ; sur une
référence seulement là, le tableau passe sur SEE, cherché sur elle (le
bandeau porte alors un jeton « Recherche dans SEE », qui se retire d'une
croix). Un clic sur un plan efface les filtres libres (état, groupe,
recherche, colonnes) — sans quoi un plan terminé sous le filtre « En cours »
donnerait un tableau vide — et garde le périmètre. Tout suit le périmètre,
sauf « seulement dans SEE », compté sur tout le contrat et étiqueté ainsi,
comme dans les cercles.

**Le tableau « SEE »**, derrière l'interrupteur **GATES | SEE** de la
section « Plans » (un seul tableau à la fois, les mêmes outils) : l'extract à
l'identique — toutes ses colonnes, dans son ordre, sous leurs intitulés. Pas
de *Vue essentielle* : l'extract n'a qu'une vingtaine de colonnes, en retirer
trois n'apporterait rien (elle reparaîtrait si `ESSENTIELLES` en désignait).
Le verdict se lit sur chaque ligne, en pastille dans la cellule NAME. Les
cases à cocher de l'extract (TRUE / FALSE) se lisent ✓ ou –. Une recherche et
un tri par intitulé (un clic, un second pour inverser, un troisième pour
l'ordre de l'extract) qui ne touchent qu'à lui ; cliquer une ligne appariée
réduit le tableau d'ici à ce plan.

Les lignes de SEE sont appariées aux plans **par racine + solution** (§ 9),
pour qu'un plan réémis d'un côté reste le même plan. La solution que l'extract
Excel aurait réduite à « 1 » est remise sur trois chiffres.

Le tout suit le périmètre (sous PERSO, les lignes des plans hors périmètre
s'effacent du tableau de SEE ; ce qui n'est que dans SEE, sans domaine, reste
compté à part, tout contrat) et le contrat. Rien n'est modifiable, rien n'est
mémorisé.

La démonstration seule en montre un exemple aux écarts délibérés.

**Brancher SEE, en trois gestes.** Dans le classeur, un onglet nommé
**`SEE`** (le nom configuré, `NOM`) ; l'extract « Nommage WD BFLOW » ouvert
dans Excel, **Ctrl+A, Ctrl+C** ; dans l'onglet, **A1, Ctrl+V**, tel quel —
titre en ligne 1, en-têtes en ligne 3, sans rien retoucher. Rouvrir le tableau
de bord : les deux cercles sont sous le tableau, et l'interrupteur **GATES |
SEE** apparaît. Rien à configurer : la configuration de `Code.gs` décrit déjà
SEE tel qu'il a été vu, et l'onglet est reconnu par son nom.

```js
RAPPROCHEMENT: {
  FEUILLE: '',                                 // pour un onglet nommé autrement que NOM (vide = NOM)
  NOM: 'SEE',                                  // nom affiché, et nom de l'onglet cherché
  CLE_REFERENCE: ['NAME', 'SOL.', 'Cust.V'],   // la référence, recomposée dans cet ordre
  ESSENTIELLES: []                             // pas de vue essentielle pour SEE
},
```

L'en-tête est la ligne qui porte tous les intitulés de la référence (la
ligne 3 dans SEE, sous le titre « Nommage WD BFLOW » et une ligne vide),
sinon la première ligne non vide. Le script la cherche dans les huit
premières lignes : l'extract se colle en A1 tel quel, titre compris.

**SEE n'écrit pas la référence comme GATES.** Son `NAME` place le A un cran
trop tôt — trois lettres, **trois** chiffres, A, le reste — là où GATES en
met quatre : `TFE311A0600` pour le plan que GATES appelle `TFE3110A600`. La
page garde la colonne telle qu'elle est dans l'extract — c'est l'extract —
et décale le A d'un cran pour recomposer la référence de GATES,
`NAME + SOL. + Cust.V` donnant `TFE3110A600003C`. Seul l'endroit du A fait
la règle : ce qui suit — solution, indice — n'y entre pas, si bien qu'une
solution ou un indice écrits autrement n'empêchent pas les deux bases de se
reconnaître. Une référence déjà écrite à la mode de GATES porte quatre
chiffres avant son A : elle est lue telle quelle.

Une référence introuvable dans l'onglet : pas de section, pas d'erreur — la
page s'ouvre. **Si les cercles manquent, Suivi FWD → Diagnostic** : sa ligne
« Seconde base » dit ce que le script voit — aucun onglet `SEE`, un onglet
vide, un onglet dont les en-têtes lus ne portent pas NAME, SOL. et Cust.V
(l'extract collé sans ses en-têtes, ou un autre extract — sans recopier ses
cellules), ou bien `✓ Seconde base « SEE » : onglet « SEE », 312 ligne(s),
référence NAME + SOL. + Cust.V (ligne d'en-têtes : 3)`. Un onglet là mais
illisible ne fait pas conclure « tout est en place » : le bilan final le redit.

Quand aucune ligne ne porte les trois intitulés, la ligne retenue est celle
qui en porte le **plus**, et non la première ligne non vide — celle-là, dans
SEE, est le titre « Nommage WD BFLOW », qui ne dit rien. Une colonne renommée
dans l'export donne donc `en-têtes lus (ligne 3)` puis `il manque Cust.V —
cette colonne a-t-elle un autre intitulé dans l'export ?`, au lieu d'envoyer
recoller un extract qui est déjà là, entier.

## 13. Les jalons

Les jalons sont **fixes** : ils viennent de la configuration, la page les
montre, personne ne les modifie à l'écran. Plus de clic sur une semaine pour en
poser, plus de poignée ni de croix — c'est un outil de consultation, et deux
lectrices ne peuvent plus se les déplacer l'une à l'autre.

Ils se règlent en haut de `Code.gs` : une semaine ISO, un texte de 60
caractères au plus et, au besoin :

- **`date`** — le jour exact (« AAAA-MM-JJ » ou « JJ/MM/AAAA ») : la page
  compte les jours jusqu'à lui, et il fixe la semaine ;
- **`perimetre`** — quand le jalon ne vaut que pour une partie des plans, la
  valeur de la colonne de domaine (§ 8), écrite comme dans l'extract ;
- **`suivi: 'concept'`** — quand le jalon appartient au **concept harnais**
  et non à la définition électrique (le FWD). Les diffusions **TO** (table
  outil) sont dans ce cas ; les diffusions **PH** et le solde suivent le FWD.

Ce sont les échéances du programme, transmises le 17/09/2026 :

```js
JALONS: [
  { semaine: '2026-S51', date: '2026-12-15', texte: 'Solde FWD' },
  { semaine: '2027-S02', date: '2027-01-15', texte: 'Diffusion PH Base',  perimetre: 'BASE/OPTION' },
  { semaine: '2027-S03', date: '2027-01-22', texte: 'Diffusion PH Perso', perimetre: 'PERSO' },
  { semaine: '2027-S05', date: '2027-02-05', texte: 'Diffusion TO Base',  perimetre: 'BASE/OPTION', suivi: 'concept' },
  { semaine: '2027-S08', date: '2027-02-26', texte: 'Diffusion TO Perso', perimetre: 'PERSO',       suivi: 'concept' }
],
```

Sous l'avancement « définition électrique », les deux jalons TO restent
dessinés, **en retrait**, et ne comptent pas (ni échéance, ni rythme
requis) ; sous « concept harnais », c'est l'inverse. Leur fiche le dit
(« suit le concept harnais ») et propose, d'un bouton, de passer à
l'avancement dont ils relèvent.

Sur le graphique, chaque jalon se marque d'un **numéro**, 1 à 5, en tête de
son trait — **tous sur une seule rangée**, jamais étagés, et sans texte
collé : deux jalons de semaines voisines se serrent côte à côte sur la
rangée, un court trait reliant le numéro à sa vraie semaine. La **légende
des jalons**, sous celle du graphique, les nomme — sur une ligne dès qu'il y
a la place — avec leur semaine telle qu'on la dit (« S2 · janv. 2027 »), leur
périmètre et, quand il n'est pas celui qu'on regarde, l'avancement qu'ils
suivent (« concept harnais »). La survoler (ou y passer au clavier) éclaire le trait et
fait paraître le nom sous la rangée. Un jalon
hors du périmètre choisi garde son numéro, dans un marqueur creux ; son
trait s'estompe. Un jalon sorti de la fenêtre affichée (zoom serré) reste
dans la légende, en retrait, avec « hors fenêtre ». L'échéance manquée est
rouge partout : marqueur, trait, et son entrée dans la légende. Cinq jalons
en dix semaines restent lisibles.

Le jalon dont le jour n'est pas passé le plus proche fait l'**échéance** : il
pilote la colonne **rythme requis** du bloc par groupe (ce qu'il faudrait
terminer chaque semaine pour le tenir, avec le rythme tenu dessous) et la
droite « requis pour … » du graphique. Sous un périmètre, seuls
comptent les jalons de ce périmètre et ceux qui n'en ont pas : sous PERSO,
une fois le solde passé, l'échéance est « Diffusion PH Perso », pas
« Diffusion PH Base » ; les jalons de l'autre périmètre restent dessinés, en
retrait, et leur bulle le dit. Sur « Tout », tous comptent. Sans jalon à
venir, la colonne laisse la place au **rythme tenu** et le graphique dit
« Aucun jalon à venir » (« … dans ce périmètre » quand il en reste ailleurs).

Une entrée illisible est simplement absente, elle ne fait pas tomber la page.
Le **Diagnostic** dit combien de jalons sont retenus, et si le périmètre de
chacun est bien l'une des valeurs de la colonne de domaine du premier contrat
— sinon il nomme le jalon et donne les valeurs vues, à recopier dans
`perimetre`.

## 13 bis. Chercher un plan dans une section

Pas de barre qui cherche partout : chaque section qui montre des plans a
**son propre petit champ**, à droite de son titre, qui ne cherche **que chez
elle** — on regarde son plan dans le carré qu'on veut, sans remonter en haut
de la page :

- **Ce qui a changé, semaine par semaine** : le journal ne garde que les
  passages du plan cherché ; ses semaines — et elles seules — restent,
  dépliées sur lui.
- **Avancement par ATA** (ou la dimension ouverte) : le champ « ATA ou
  plan… » filtre les groupes par leur nom, comme avant, et trouve aussi un
  plan : son groupe reste, et sous lui le plan trouvé, seul. Un clic le
  montre dans le tableau.
- **Comparaison des bases de données** : chaque lot ne garde que les plans
  cherchés, déplié sur eux, avec « sur N » pour le total du lot ; une ligne
  que SEE est seule à connaître se trouve aussi.
- **Plans** : la recherche du tableau, dans toutes les colonnes, comme avant.

Trois caractères d'une référence suffisent (`TFE3110…`) ; en minuscules, avec
des tirets ou des espaces, et même **écrite à la mode de SEE** (le A un cran
trop tôt), elle mène au même plan. En deçà de trois caractères, les champs du
journal et de la comparaison ne filtrent rien. Échap vide le champ. Ces
champs ne touchent qu'à leur section : ni le tableau, ni la barre, ni le
bandeau des filtres ne bougent.

## 13 ter. Ce qui est replié à l'ouverture

La page s'ouvre **tout replié** : les semaines du journal, les lots « plan par
plan » de la comparaison et les groupes (ATA, ECP…) ; le lecteur déplie ce
qu'il veut voir. Le graphique s'ouvre sur **six mois** — exactement le bouton
« 6 mois » —, ou sur **un an** quand la prochaine échéance tombe au-delà (le
concept harnais, dont la première échéance est en février) : la puce
« Prochaine échéance » ne parle jamais d'un jalon que le graphique ne montre
pas. Tant qu'on n'a ni zoomé ni déplacé, ce cadrage suit l'échéance quand on
change de périmètre ou d'avancement ; un cadrage choisi à la main est gardé.
Les boutons **3 mois · 6 mois · 1 an · Tout** sont à droite de l'en-tête du
graphique ; l'aide « glisser pour déplacer, molette pour zoomer » a disparu
(le geste, lui, marche toujours). Un jalon plus lointain reste dans la
légende, avec son décompte, marqué « hors fenêtre ».

## 13 quater. Les échéances en jours

Un jalon se donne à la semaine ; la page le dit **en jours**, jusqu'à **sa
date** (sans date, jusqu'au vendredi de sa semaine) :

- **en tête du graphique** (le titre, lui, ne dit que la semaine), la
  prochaine échéance du périmètre : « Prochaine
  échéance · Solde FWD · dans 80 jours », avec un point **vert** si le rythme
  tenu suffit, **rouge** sinon — le verdict de la fiche, mot pour mot ;
- **dans la légende des jalons**, sous chacun : « dans 111 jours », en ambre
  à moins de trois semaines, « il y a 5 jours » une fois passé.

Un clic — sur cette échéance, sur un jalon de la légende ou sur son
numéro dans le graphique — ouvre la **fiche de l'échéance** : sa date
(« mardi 15 décembre 2026 · S51 »), les **jours** et les **semaines**
restants, les **plans à terminer**, la jauge des terminés, le **rythme
requis** d'ici là contre le **rythme tenu**, et le verdict : échéance tenue,
ou combien de plans manqueraient le jour dit et quand tout serait terminé.
Les plans se comptent dans le périmètre regardé — sous PERSO, le solde FWD ne
compte que les plans PERSO — et un jalon d'un seul périmètre ne compte que
les siens : sur « Tout », « Diffusion PH Base » demande les plans
BASE/OPTION ; ouvert sous PERSO, sa fiche le dit (« hors du périmètre
choisi »). Un second clic, la croix ou
Échap — où que soit le focus — la referment ; au clavier, Entrée sur un
jalon l'ouvre.

Sur le graphique, quand le rythme tenu ne suffit pas, un trait rouge
marque à l'échéance « manque N » : les plans qui resteraient à faire ce
jour-là au rythme tenu — le même nombre que la fiche. La survoler donne la
phrase entière. La droite « requis » et ce trait ne se tracent que sur la
courbe des plans que l'échéance demande : sur « Tout », un jalon BASE/OPTION
se lit dans la légende (« requis … sur ses plans BASE/OPTION ») avec un lien
**voir BASE/OPTION** qui passe à ce périmètre.

## 13 quater bis. Une seule formule, une seule façon de dire une semaine

Chaque nombre qui se lit à deux endroits est **le même aux deux endroits** :
la fiche, la puce, la légende du graphique et le bloc par groupe tirent leurs
chiffres d'une seule fonction, avec une seule formule.

```
semaines restantes = semaine du jalon − semaine en cours
rythme requis      = plans à terminer ÷ semaines restantes (au moins une)
rythme tenu        = terminés gagnés du premier au dernier relevé ÷ semaines écoulées
fin estimée        = semaine en cours + arrondi supérieur(à terminer ÷ rythme tenu)
manque             = à terminer − rythme tenu × semaines restantes (au plan supérieur)
```

Tout se compte **à partir de la semaine en cours**, comme les jours : si le
relevé de la semaine n'est pas encore archivé, le temps qui reste ne
s'allonge pas pour autant. Le graphique le montre : un trait plat, fin, entre
le dernier relevé et la semaine en cours (marquée « aujourd'hui »), d'où
partent les projections ; survolée, cette semaine dit « pas encore de relevé
archivé », pas « à venir ».

Une semaine s'écrit partout de la même façon — journal, graphique, bulle,
jalons, fin estimée, pied de page : **« S38 · sept. 2026 »** (le mois et
l'année de son jeudi, qui fixe l'année ISO), ou « S38 » seul là où le mois se
lit déjà (axe du graphique, date complète de la fiche, boîte d'archivage).
L'étiquette technique 2026-S38 ne s'affiche plus que dans le Diagnostic.

Un seul mot pour une photo archivée de l'extract : **relevé**. « Depuis le
relevé précédent (S37 · sept. 2026) », « 13 relevés, de S26 · juin 2026 à S38
· sept. 2026 », « Dernier relevé : S38 · sept. 2026 ». Une même semaine du
journal se dit avec les **mêmes lignes** dans le comparatif du haut, dans le
journal et dans la bulle du graphique — « 20 passés à « Validé » », « 3
passés à « Non renseigné » » —, dans le même ordre ; « Non renseigné » compte
partout la même chose (cellule vide, tiret ou EMPTY), sous la barre comme
au-dessus du tableau.

## 13 quinquies. Vitesse d'ouverture et thème

- **Le paquet voyage compacté** : chaque nom de colonne, chaque référence
  d'un relevé n'y est écrit qu'une fois (compacterPaquet dans `Code`, rendu à
  l'identique par la page) — trois à quatre fois moins lourd.
- **Les gros tableaux se dessinent par tranches** : au-delà d'environ 40 000
  cellules, la suite vient en descendant dans le tableau, ou d'un clic sur
  « N lignes de plus ». Filtres, tris et comptes portent toujours sur toutes
  les lignes. Le tableau de SEE ne se dessine que quand on bascule dessus, et
  un tableau hors de l'écran ne se met pas en page tant qu'on ne s'en approche
  pas.
- **Les polices** se chargent sans retenir l'affichage : un réseau lent
  n'empêche plus la page de paraître.
- **Le Diagnostic dit le temps de chaque lecture** — GATES, historique,
  seconde base — et le poids envoyé : c'est lui qui dit où l'ouverture passe
  son temps sur ce classeur-là.
- **Le thème suit le navigateur** : clair ou sombre, menus déroulants, champs
  et barres de défilement compris — un Chrome en mode sombre n'ouvre plus de
  menu blanc écrit en clair.
- Un bouton **↑** en bas à droite ramène en haut de la page.

## 14. Ce qui reste local à chaque personne

La dimension ouverte, l'ordre des colonnes, les tris et le cadrage du graphique
sont retenus dans le navigateur de chacun. Personne n'impose sa mise en page à
personne — et rien de ce qui se partage (jalons, contrats, historique) n'y
passe. Le périmètre, les filtres et la vue du tableau repartent de zéro à
chaque ouverture.

## 15. L'automatisation : récupérer et déposer sans y penser

Tout ce qui précède se fait à la main en trois gestes par semaine. Le dossier
`import/` permet de s'en passer, **sans rien installer sur le poste** : pas
d'exécutable, pas de bibliothèque, seulement Python et le Chrome déjà là.
`import/README.md` donne le détail ; en résumé :

0. **S'entraîner d'abord, sans intranet.** `python import\essai.py --jouer`
   fabrique un faux GATES sur le PC et joue la chaîne entière — recherche,
   téléchargement, lecture d'un plan — sans rien préparer. La même commande
   sans `--jouer` affiche la marche à suivre pas à pas, et dit les trois
   lignes qui changeront au bureau.

1. **Préparer Chrome une fois.** Fermer Chrome, puis le relancer avec
   `chrome.exe --remote-debugging-port=9222` (un raccourci suffit). Il ouvre
   alors un canal local sur lequel un script peut lui dire « va à cette page,
   clique ce bouton, lis ce tableau ». La session reste la vôtre : vos
   cookies, votre authentification intranet. **Rien n'est simulé à l'aveugle**
   — on ne bouge pas la souris, on désigne l'élément et on lui demande de
   faire ce qu'il ferait sous le doigt. On peut travailler à côté pendant ce
   temps.

2. **Écrire la recette une fois.** Un fichier JSON qui dit les gestes dans
   l'ordre — ouvrir, remplir, cliquer, télécharger — avec une variable pour le
   contrat ou le plan. Trois modèles à compléter sont fournis dans
   `import/recettes/` : GATES par contrat, SEE par contrat, composants par
   plan. Le geste `cliquer_texte` ne demande que le texte écrit sur le bouton.

3. **Déposer dans le classeur.** `Code.gs` publie une adresse (Déployer →
   Application web), protégée par un secret :

   ```js
   DEPOT: { SECRET: 'une phrase longue et imprévisible', MAX_LIGNES: 20000 },
   ```

   `python import/deposer.py gates-HDK.csv --onglet HDK --archiver` envoie
   l'extract, le classeur vide l'onglet, colle les lignes et archive le relevé
   de la semaine. Sans secret, tout dépôt est refusé ; un onglet d'historique
   n'est jamais une cible ; redéposer la même semaine met la ligne à jour au
   lieu d'en empiler une seconde.

4. **Le lundi, un double-clic** sur un `.bat` — ou rien du tout, avec le
   Planificateur de tâches Windows et la case *Exécuter la tâche dès que
   possible si un démarrage planifié est manqué* : le PC éteint le lundi
   rattrape au premier allumage. Rien ne tourne quand la machine dort.

Les composants suivent la même voie, avec une recette qui ouvre chaque plan et
extrait son tableau. Et quand ils ne sortent d'aucun tableur, ils sont sur le
**plan**, sous toutes les formes qu'il prend : `import/lire_composants.py`
lit un PDF de dessin, un Visio, un DXF, ou un **scan** — image ou PDF scanné,
par reconnaissance de caractères hors ligne, sans exécutable — et rend les
équipements, chacun avec le repère électrique écrit dans sa boîte. Avec la
liste des repères que la base attend (`--connus`), il dit ce qui est
retrouvé, ce qui manque sur le plan et ce qui est en plus ; sur un scan,
cette liste tranche les lettres qu'une lecture confond. Il dit toujours
combien de boîtes il a vues, combien portent un repère unique, et lesquelles
sont douteuses : **aucun composant n'est inventé**. Une image de contrôle par
page permet la relecture d'un coup d'œil.

À valider avec l'informatique avant mise en place.
