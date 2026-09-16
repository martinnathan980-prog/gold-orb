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
lit le classeur et y écrit l'onglet d'historique.

## 2. Ouvrir le tableau de bord

**Suivi FWD → Ouvrir le tableau de bord.**

Pour le partager à quelqu'un qui n'ouvre pas le classeur :
**Déployer → Nouveau déploiement → Application Web**, exécuter en tant que
soi-même, accès selon la politique de l'entreprise. Le lien obtenu ouvre la
même page.

## 3. Le geste de chaque semaine

1. Dans GATES, exporter la liste en CSV.
2. Ouvrir l'onglet **Données** du classeur, `Ctrl+A`, `Suppr`, puis coller
   l'export en **A1**.
3. **Suivi FWD → Archiver le relevé de cette semaine.**

C'est tout. Ne jamais créer un nouvel onglet : le tableau de bord lit toujours
le premier onglet visible.

L'étape 3 peut se faire toute seule : **Suivi FWD → Activer l'archivage
automatique**, et un relevé est pris chaque vendredi vers 17 h.

## 4. Ce que devient l'historique

GATES ne donne qu'une photo du jour : l'export ne dit pas *quand* un plan est
passé à 100 %. L'historique ne peut donc pas être reconstitué après coup — il
s'accumule, un relevé par semaine, dans l'onglet masqué **Historique_FWD**.

- Un seul relevé par semaine ISO : réimporter le lundi puis le jeudi met la
  ligne à jour, elle ne se dédouble pas.
- **Rien n'est jamais supprimé.** Chaque relevé garde les comptes globaux, les
  comptes par colonne, et l'avancement plan par plan.
- Mauvais export collé par erreur ? **Suivi FWD → Supprimer le relevé de cette
  semaine**, recoller le bon, ré-archiver.

Pour consulter l'onglet : clic droit sur un onglet → *Afficher les feuilles
masquées* → `Historique_FWD`. Le remasquer ensuite n'est pas obligatoire.

## 5. Ce que le script devine tout seul

Aucun nom de colonne n'est écrit en dur.

- **La ligne d'en-têtes** est cherchée dans les huit premières lignes : les
  lignes de titre de l'export ne gênent pas.
- **La ligne au-dessus** est prise pour des groupes de colonnes fusionnés, et
  propagée vers la droite.
- **L'avancement FWD** est la colonne dont l'en-tête ou le groupe parle de FWD
  et d'avancement.
- **La référence** est la colonne qui identifie un plan ; elle reste figée à
  gauche du tableau.
- **Les dimensions** de « Avancement FWD par… » sont les colonnes qui se
  comportent comme des catégories : entre 2 et 40 valeurs distinctes. Une
  colonne de commentaires ou d'identifiants en est donc exclue d'office.
- **La date de création**, si elle existe, ajoute la dimension « ancienneté ».

Si les colonnes de l'export changent, il n'y a rien à modifier : recoller et
ré-archiver suffit.

## 6. Sur l'export GATES réel

Relevé sur `export_48.xlsx` : **138 colonnes**, en-tête en **ligne 2**, ligne de
groupes fusionnés en ligne 1, données à partir de la ligne 3.

| | |
|---|---|
| Colonnes | 138, dont **91** sont 13 répétitions du même bloc de 7 (une par variante HDK AA) |
| Groupes | 16 plages fusionnées + 2 cellules isolées (`Concept Harnais`, colonnes 40 et 41) |
| Sans intitulé | colonnes 1, 4 et 5 — nommées « Colonne 1 », « Colonne 4 », « Colonne 5 » |
| Référence figée | `Référence UD`, colonne **2** (pas la 1) |
| **Avancement FWD** | `Avancement`, colonne **42**, groupe `Réalisation FWD` |

**Vingt-sept colonnes ont un intitulé contenant « avancement ».** Une seule est
celle du FWD ; les autres sont `Avancement Définition Electrique` et
`Avancement Concept Harnais`, treize fois chacune. C'est le groupe fusionné
au-dessus qui départage, et le script lit les **vraies fusions** de la feuille.

Autres points tenus par le code :

- **Les lignes sans référence sont écartées.** L'export en intercale sous
  l'en-tête.
- **Les dates sont au format `2017-05-02T22:00:00.000Z`**, reconnues comme
  telles pour l'ancienneté.
- **Les booléens valent `true` / `false`.** Le tableau les montre tels quels —
  c'est l'extract. Dans le bloc d'analyse, où la valeur devient un nom de
  groupe lu par tout le monde, ils s'écrivent **Oui** / **Non**.
- **Les 91 colonnes des blocs HDK AA s'ouvrent repliées** : 47 colonnes à la
  première ouverture au lieu de 138. Rien n'est supprimé, « Colonnes → tout
  afficher » les ramène, et le choix de chacun est retenu.

### Les colonnes analysées

Dans « Avancement FWD par… », rangées par ordre alphabétique dans le sélecteur :

| Colonne | Ce qu'elle montre |
|---|---|
| **ATA** | le découpage attendu, ouvert par défaut |
| **CC** | code circuit |
| **Date création (par mois)** | un groupe par mois, rangés dans l'ordre du temps |
| **ECP** | |

Deux colonnes calculées : **fin estimée**, puis **effort demandé**. « À solder
par semaine » a été retiré — personne ne suit un nombre par semaine. Le bloc a
une hauteur bornée : au-delà d'une dizaine de lignes, on descend dedans plutôt
que d'allonger la page.

**Choisir une ligne déplie ses références** : les plans non terminés d'abord,
une pastille par état, et un clic sur une référence réduit le tableau du bas à
ce plan. Au-delà de quinze groupes, le bloc en montre quinze et propose le
reste.

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
GROUPES_MASQUES_AU_DEPART: ['HDK AA'],
```

### Revenir en arrière

Dès qu'un filtre est posé — un état, un domaine, un groupe, une référence, une
recherche, un filtre de colonne — un **bandeau collé en haut de la page** nomme
chacun d'eux et donne sa croix, avec un **Tout effacer**. Où qu'on ait cliqué,
la sortie est à portée.

### Le journal des changements

Chaque relevé archivé garde l'avancement **plan par plan**. Comparer deux
relevés successifs donne, semaine par semaine, qui a bougé et dans quel sens —
la seule chose que l'export du jour ne dira jamais.

Il est **sous le graphique**, dans la même section : la courbe dit combien, le
journal dit lesquels. Sa hauteur est bornée, on y descend.

Dans chaque semaine, les plans sont **rangés par état d'arrivée** : tous les
terminés, puis les passés en cours, puis les repassés à faire.

- La semaine la plus récente est en haut, ouverte ; les autres se déplient
  d'un clic.
- `Tout / Terminés / En cours / À faire` ne garde que les passages voulus, et
  **chaque compte du résumé est cliquable** : « 6 terminés » n'affiche plus que
  ceux-là, sur toutes les semaines à la fois.
- Cliquer un plan réduit le tableau du bas à ce plan.
- Les nouveaux plans et ceux qui ont disparu de l'export sont signalés.
- **Survoler une semaine sur le graphique** donne le même contenu en raccourci :
  le nombre de passages en terminé et les références.

Le journal se remplit au **deuxième** archivage : il faut deux relevés pour
savoir ce qui a changé entre les deux.

### Les filtres rapides, au-dessus du tableau

- **Domaine** — une puce par valeur (`BASE/OPTION`, `PERSO`…), avec le compte.
- **Terminés reconduits** — les plans déjà terminés dont la date de création
  remonte à plus de douze mois. Ils viennent d'avant : ils gonflent le
  pourcentage d'avancement sans rien dire de l'effort de cette campagne. Le
  seuil se règle par `MOIS_RECONDUIT` dans `Javascript.html`.

### Vue essentielle

Le bouton **Vue essentielle**, à côté de « Colonnes », ne laisse que la
référence, l'avancement, la date de création et les colonnes analysées. Un
second clic remet **exactement** la disposition d'avant, y compris les colonnes
qu'on avait masquées soi-même.

### Voir un exemple

Le lien **voir un exemple**, à côté du titre « Avancement dans le temps »,
remplit d'un coup **le graphique et le journal** avec un historique fabriqué à
partir des comptes du jour, sous un bandeau qui dit que c'en est un. Le tableau
et les compteurs du haut restent sur les vraies données.

Il est toujours proposé : au premier import il montre ce que la page dira plus
tard, et plus tard il sert encore à l'expliquer à quelqu'un.

## 7. Les quatre états

| État | Ce qui le déclenche |
|---|---|
| **Terminé** | `100 %`, `terminé`, `achevé`, `clôturé`, `soldé`, `fini`, `ok` |
| **En cours** | tout pourcentage strictement entre 0 et 100, `en cours`, ou tout autre texte |
| **À faire** | `à faire`, `non commencé`, `0 %` |
| **Non renseigné** | cellule vide, ou `-` |

« À faire » est une valeur *saisie*. Une cellule vide est un *défaut de
saisie*. Les confondre masquerait le second, qui est précisément ce qu'on
cherche à voir : le bouton « non renseignés » sous la barre sort la liste.

## 8. Les jalons

Se posent en cliquant une semaine sur le graphique, se déplacent à la souris ou
aux flèches du clavier, se retirent par la croix. Ils sont **partagés** : ils
vivent dans le classeur, pas dans le navigateur. Ce que pose la collègue, sa
chef le voit.

Le jalon à venir le plus proche pilote les colonnes « à solder/sem. » et
« effort demandé » du bloc par ATA. Sans jalon, ces colonnes laissent la place
au rythme actuel.

## 9. Ce qui reste local à chaque personne

L'ordre des colonnes, celles qui sont masquées, le tri et le cadrage du
graphique sont retenus dans le navigateur de chacun. Personne n'impose sa mise
en page à personne.
