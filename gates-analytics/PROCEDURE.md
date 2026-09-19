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
d'historique (`Historique_FWD…`), l'onglet de la seconde base s'il est nommé
(voir § 12) et les onglets de service (`Paramètres`, `Config`).

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

1. Dans GATES, exporter la liste de chaque contrat en CSV.
2. Ouvrir l'onglet du contrat, `Ctrl+A`, `Suppr`, puis coller l'export
   en **A1**. Même chose pour chaque contrat.
3. **Suivi FWD → Archiver le relevé de cette semaine.**

C'est tout. L'archivage passe sur **tous les contrats d'un coup**, une ligne
par contrat dans son propre onglet d'historique. Un onglet illisible n'empêche
pas les autres d'être relevés : l'erreur le nomme, et les autres sont
archivés.

L'étape 3 peut se faire toute seule : **Suivi FWD → Activer l'archivage
automatique**, et un relevé est pris chaque vendredi vers 17 h.

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
| Sans intitulé | colonnes 1, 4 et 5 — nommées « Colonne 1 », « Colonne 4 », « Colonne 5 » |
| Référence figée | `Référence UD`, colonne **2** (pas la 1) |
| **Avancement FWD** | `Avancement`, colonne **42**, groupe `Réalisation FWD` |
| Domaine | `Domaine` — le périmètre du haut de page |

**Vingt-sept colonnes ont un intitulé contenant « avancement ».** Une seule est
celle du FWD ; les autres sont `Avancement Définition Electrique` et
`Avancement Concept Harnais`, treize fois chacune. C'est le groupe fusionné
au-dessus qui départage, et le script lit les **vraies fusions** de la feuille.

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

Deux colonnes calculées : **fin estimée**, puis **effort demandé** quand un
jalon est à venir (**rythme actuel** sinon). Le bloc a une hauteur bornée :
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
DIMENSIONS: ['ATA', 'CC', 'ECP'],
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
  (voir plus haut), les mêmes intitulés, **l'ordre exact de la feuille**.
  C'est la vue de référence, celle sur laquelle tout le monde parle de la même
  chose.
- **Vue essentielle** : la poignée de colonnes qu'on regarde vraiment —
  référence, nom d'installation, ECP, ATA, séquence, validation définition
  électrique, date de création, avancement.

Il n'y a plus de bouton « Choisir » ni de panneau pour masquer une colonne à la
main : deux lectrices regardent toujours le même tableau. Le glisser-déposer
des colonnes et le tri restent.

Le bloc figé à gauche couvre tout ce qui précède la référence, elle comprise.
Sur l'export réel, la seule colonne qui la précédait est la « Colonne 1 »
retirée : la référence ouvre donc le tableau et reste seule figée.

### L'interrupteur exemple / réel

**Tout en haut de la page**, avant le titre : un seul interrupteur, qui porte
sur toute la page. Il n'y a pas un bouton par bloc, et on ne peut pas se
retrouver à moitié en exemple.

En mode **Exemple**, la page se borde de tirets et remplit **le graphique, le
journal et le comparatif** avec un historique fabriqué à partir des comptes du
jour. Les plans affichés, eux, restent ceux de la feuille — et la phrase le
dit : c'est l'historique qui est fabriqué, pas les plans. Tout ce qui marche
en données réelles marche à l'identique en exemple : périmètre, groupes,
changements d'indice, bulle du graphique.

Il est toujours proposé : au premier import il montre ce que la page dira plus
tard, et plus tard il sert encore à l'expliquer à quelqu'un.

## 8. Le périmètre : Tout / BASE/OPTION / PERSO

Dans le bandeau du titre, à droite de « Suivi FWD » (dessous, centré, sur un
petit écran) : **« Tout »**, puis une puce par valeur de la colonne de
domaine, chacune avec son compte de plans. Il est masqué quand l'export n'a
pas de colonne de domaine.

Le périmètre pilote **toute la page** : la barre et les états, la phrase, le
comparatif « depuis l'import », la courbe et sa bulle, le journal, le bloc par
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

Une référence UD s'écrit **racine + solution + indice** :

| `HEL0225A017` | `001` | `A` |
|---|---|---|
| **racine** : 3 lettres, 4 chiffres, `A`, 3 chiffres — fixe | **solution** : 3 chiffres — une autre solution, c'est un autre plan | **indice** : une lettre, change à chaque réémission du même plan |

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

- **Dans le comparatif** « depuis l'import », un lot *changements d'indice*
  (pastille en anneau), cliquable comme les autres, filtre le tableau sur les
  nouvelles références ; son survol montre « ancienne → nouvelle ». Un plan
  réémis qui change aussi d'état compte en plus dans le lot de son état
  d'arrivée.
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
terminés, puis les passés en cours, puis les repassés à faire.

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
  « Relevé du … », terminés sur total, la différence depuis le relevé
  précédent, puis les comptes non nuls de la semaine — passés en terminé, en
  cours, repassés à faire, effacés, nouveaux, disparus, changements d'indice.
  La bulle ne liste pas de références : le journal, dessous, donne le détail.

Le journal se remplit au **deuxième** archivage : il faut deux relevés pour
savoir ce qui a changé entre les deux.

## 11. Les quatre états

| État | Ce qui le déclenche |
|---|---|
| **Terminé** | `100 %`, `terminé`, `achevé`, `clôturé`, `soldé`, `fini`, `ok` |
| **En cours** | tout pourcentage strictement entre 0 et 100, `en cours`, ou tout autre texte |
| **À faire** | `à faire`, `non commencé`, `0 %` |
| **Non renseigné** | cellule vide, ou `-` |

« À faire » est une valeur *saisie*. Une cellule vide est un *défaut de
saisie*. Les confondre masquerait le second, qui est précisément ce qu'on
cherche à voir : le bouton « non renseignés » sous la barre sort la liste.

## 12. Rapprochement avec une seconde base : SEE

Une autre base suit les mêmes plans sous une autre structure. La seconde base
prévue est **SEE**, l'extract Excel de l'intranet (« Nommage WD BFLOW ») : un
titre en ligne 1, les en-têtes en ligne 3, les données dessous, et la
référence UD répartie sur trois colonnes — **NAME** (la racine), **SOL.** (la
solution, trois chiffres) et **Cust.V** (l'indice, une lettre). Collé tel quel
dans un onglet de ce classeur et décrit dans la configuration, il donne deux
choses ; sans description, ni l'une ni l'autre n'existe.

**La section « Rapprochement avec SEE »**, entre le bloc par groupe et le
tableau, reprend exactement le dessin de la barre d'avancement du haut, pour
se lire du même geste :

- une phrase : « **623** sur 640 plans identiques dans SEE », et dessous ce
  qu'il reste à regarder : « Il reste 17 plans à vérifier · 5 références que
  SEE est seul à connaître. » ;
- la barre : chaque plan d'ici dans une seule case — identique (vert), même
  plan sous un autre indice (anneau), champs différents (ambre), absent de SEE
  (rouge) — et, à part, après un blanc, en pointillé, ce qui n'existe que
  dans SEE ;
- cinq boutons sous la barre, comme les états sous celle du haut, avec leur
  grand nombre ; un bouton à 0 se lit mais ne se clique pas :

| Bouton | Ce qu'il compte | Le clic |
|---|---|---|
| **identiques** | même indice, mêmes champs | filtre le tableau, GATES ou SEE |
| **autre indice** | le même plan (même racine et même solution), connu là sous une autre lettre | idem |
| **champs différents** | un champ comparé qui ne dit pas la même chose des deux côtés | idem |
| **absents de SEE** | des plans d'ici que SEE ne connaît pas | filtre et passe sur GATES |
| **seulement dans SEE** | des lignes de là dont aucun plan du contrat n'a la racine et la solution | filtre et passe sur SEE |

Un seul lot à la fois ; le bandeau le nomme (« Rapprochement : … »), la croix
le retire sans changer de côté. Survoler un bouton éclaire son segment et
ouvre une bulle : les champs comparés, la ventilation des écarts par champ,
les paires « référence → solution et lettre », et où mène le clic. Quand le
tableau est du mauvais côté pour le lot posé, il le dit et propose « Les voir
dans GATES / SEE ». Un bouton **détail des écarts (n)** déplie une grille :
référence, champ, valeur GATES, valeur SEE.

**Le tableau « SEE »**, derrière l'interrupteur **GATES | SEE** de la
section « Plans » (un seul tableau à la fois, les mêmes outils) : l'extract à
l'identique —
toutes ses colonnes, dans son ordre, sous leurs intitulés — et une *Vue
essentielle* si la configuration en désigne une (les colonnes de la référence
en font toujours partie). Le verdict se lit sur chaque ligne : la pastille
dans la cellule NAME, et les cellules qui diffèrent d'ici sous un voile ambre,
la valeur d'ici en info-bulle. Les cases à cocher de l'extract (TRUE / FALSE)
se lisent ✓ ou –. Une recherche et un tri par intitulé (un clic, un second
pour inverser, un troisième pour l'ordre de l'extract) qui ne touchent qu'à
lui ; cliquer une ligne appariée réduit le tableau d'ici à ce plan.

Les lignes de SEE sont appariées aux plans **par racine + solution** (§ 9),
pour qu'un plan réémis d'un côté reste le même plan. La solution que l'extract
Excel aurait réduite à « 1 » est remise sur trois chiffres. Un champ se compare à la
lettre près, sans tenir compte de la casse ni des accents ; deux cases à cocher
se comparent cochée à cochée ; l'avancement FWD, lui, se compare **par état**,
et face à une case à cocher, un plan terminé ici doit être coché là.

Le tout suit le périmètre (sous PERSO, les lignes des plans hors périmètre
s'effacent du tableau de SEE ; ce qui n'est que dans SEE, sans domaine, reste
compté à part, tout contrat) et le contrat. Rien n'est modifiable, rien n'est
mémorisé.

La démonstration en montre un exemple aux écarts délibérés. Dans le classeur,
la configuration de `Code.gs` décrit déjà SEE tel qu'il a été vu ; il reste à
**nommer l'onglet** — et à confirmer les champs comparés :

```js
RAPPROCHEMENT: {
  FEUILLE: '',                                  // nom de l'onglet où SEE est collé (vide = rien)
  NOM: 'SEE',                                   // nom affiché ; vide = le nom de l'onglet
  CLE_REFERENCE: ['NAME', 'SOL.', 'Cust.V'],   // la référence, recomposée dans cet ordre
  ESSENTIELLES: ['NAME', 'SOL.', 'Cust.V', 'VALIDITY PSN FULL', 'DIAGRAM TYPE',
                 'PRODUCT FAMILY', 'Validated', 'Released Date', 'REDRAW'],
  CHAMPS: [                                     // hypothèse à confirmer
    { ici: 'Réalisation FWD > Avancement', la: 'Validated',          titre: 'Avancement / Validated' },
    { ici: 'Réalisation FWD > Redraw',     la: 'REDRAW',             titre: 'Redraw' },
    { ici: 'Nom Installation',             la: 'FG1 TAGDESCRIPTION', titre: 'Installation' }
  ]
},
```

`ici` se désigne comme partout dans la configuration (intitulé, ou
« Groupe > Colonne » en cas de doublon) ; `la` est l'intitulé dans l'onglet,
retrouvé sans tenir compte de la casse ni des accents. L'en-tête est la ligne
qui porte tous les intitulés de la référence (la ligne 3 dans SEE), sinon la
première ligne non vide. Un champ dont l'un des deux côtés est introuvable est
écarté, pas la section.

## 13. Les jalons

Les jalons sont **fixes** : ils viennent de la configuration, la page les
montre, personne ne les modifie à l'écran. Plus de clic sur une semaine pour en
poser, plus de poignée ni de croix — c'est un outil de consultation, et deux
lectrices ne peuvent plus se les déplacer l'une à l'autre.

Ils se règlent en haut de `Code.gs`, une semaine ISO et un texte de 60
caractères au plus :

```js
JALONS: [
  { semaine: '2026-S44', texte: 'Gel de la définition' },
  { semaine: '2026-S52', texte: 'Revue critique' },
  { semaine: '2027-S12', texte: 'Livraison plateau' },
  { semaine: '2027-S26', texte: 'Premier vol' }
],
```

**Ces quatre entrées sont provisoires** : à remplacer par les vraies échéances
du programme. Une entrée illisible est simplement absente, elle ne fait pas
tomber la page ; le **Diagnostic** dit combien de jalons sont retenus.

Le jalon à venir le plus proche pilote la colonne **effort demandé** du bloc par
groupe (ce qu'il faudrait solder chaque semaine pour le tenir, comparé au
rythme réellement tenu). Sans jalon à venir, la colonne laisse la place au
**rythme actuel** et le graphique dit « Aucun jalon à venir ».

## 14. Ce qui reste local à chaque personne

La dimension ouverte, l'ordre des colonnes, les tris et le cadrage du graphique
sont retenus dans le navigateur de chacun. Personne n'impose sa mise en page à
personne — et rien de ce qui se partage (jalons, contrats, historique) n'y
passe. Le périmètre, les filtres et la vue du tableau repartent de zéro à
chaque ouverture.
