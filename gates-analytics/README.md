# Suivi FWD

Tableau de bord de l'avancement FWD des plans d'intégration électrique, à
poser dans un classeur Google Sheets. La mise en place et le geste
hebdomadaire sont dans **[PROCEDURE.md](PROCEDURE.md)**.

C'est un outil de **consultation** : la page montre, elle ne modifie rien.

## Ce qu'il y a dans ce dossier

| Fichier | Rôle |
|---|---|
| `Code.gs` | Serveur : contrats (un onglet visible chacun), modèle de colonnes, historique par contrat, jalons de configuration, lecture de la seconde base |
| `Index.html` | Page ; elle injecte le premier contrat au rendu, sans aller-retour, et tend le pont `SUIVI_FWD_API.chargerContrat` pour les autres |
| `Styles.html` | Feuille de style |
| `Javascript.html` | Interface |
| `appsscript.json` | Manifeste (fuseau, portées OAuth) |
| `prototype/` | La même interface, autonome, avec un jeu d'exemple à trois contrats — c'est la source |
| `import/releve.py` | Variante hors Google : archive les relevés depuis un CSV |
| `tests/` | Batterie de l'add-on (serveur + page rendue) |

## Une seule interface, deux sources

`prototype/suivi-fwd.html` est **la** version de l'interface. Elle tourne seule
avec un jeu d'exemple, ce qui permet de la montrer et de la tester sans
classeur. Quand elle trouve `window.SUIVI_FWD_DONNEES` posé dans la page, elle
s'alimente à la place sur le classeur.

`Styles.html`, `Javascript.html` et `Index.html` en sont **dérivés** :

```sh
npm run build        # redécoupe le prototype en fichiers Apps Script
```

Ne jamais modifier les trois fichiers dérivés à la main : la modification se
ferait perdre au découpage suivant. Tout passe par le prototype (et par
`tests/Index.modele.html` pour l'enveloppe d'`Index.html`).

## Ce que la page montre

- **Un bandeau tout en haut** : l'interrupteur exemple / réel, le
  **périmètre** (Tout, puis une puce par domaine — `BASE/OPTION`, `PERSO`…)
  qui pilote toute la page, et le sélecteur de **contrat** quand le classeur
  en a plusieurs.
- **L'avancement du jour** : barre, quatre états, et le comparatif « depuis
  l'import » — passés en terminé, en cours, repassés à faire, nouveaux,
  disparus et **changements d'indice** (le même plan réémis sous un autre
  indice, retrouvé par la racine de sa référence UD).
- **La courbe dans le temps**, avec les jalons de configuration, une bulle
  qui résume chaque semaine en chiffres, et dessous le **journal** de ce qui a
  changé, semaine par semaine, plan par plan.
- **Avancement FWD par…** : par ATA, CC, ECP ou mois de création, avec la fin
  estimée et l'effort demandé par le prochain jalon ; un filtre sur la colonne
  de gauche, et sous chaque ligne toutes ses références, à faire puis
  terminées.
- **Le rapprochement avec une seconde base**, quand la configuration en
  nomme une : absents d'un côté ou de l'autre, indices différents, champs
  différents.
- **Le tableau** : l'extract GATES à l'identique — toutes les colonnes, les
  mêmes intitulés, l'ordre exact de la feuille — en deux vues seulement,
  *Toutes les colonnes* et *Vue essentielle*. Seule exception : une colonne
  sans intitulé et entièrement vide (« Colonne 1 » sur l'export réel) n'est
  pas affichée.

## Tests

```sh
npm install
npm test
```

- `npm run test:addon` — 294 tests. Le vrai `Code.gs` tourne dans Node contre
  un classeur en mémoire (`tests/faux-classeur.js`), sur un export
  volontairement pénible : lignes de titre, groupes fusionnés, en-têtes
  accentués ou dupliqués, ligne vide au milieu, avancements de toutes les
  formes — puis sur la vraie structure à 138 colonnes de l'export GATES
  (`tests/feuille-gates.js`). La page qu'Apps Script rendrait est ensuite
  chargée dans un vrai navigateur et comparée aux comptes du serveur. Couvre
  aussi : feuille vide, feuille sans colonne d'avancement, historique
  corrompu, 4 000 plans, jalons de configuration hostiles, deux contrats
  (archivage, suppression, diagnostic, ancien onglet d'historique orphelin,
  changement de contrat dans la page, panne du classeur), périmètre dérivé
  des cartes plan par plan, seconde base à rapprocher.
- `npm run test:interface` — 369 tests sur l'interface elle-même.
  Elle n'essaie pas seulement de vérifier que ça marche : recherches avec
  balises, expressions régulières, 3 000 caractères ou émoji, jalon de
  configuration au texte injecté, `localStorage` corrompu puis inaccessible,
  zoom et déplacement extrêmes, sept largeurs d'écran, clavier seul, contraste
  dans les deux thèmes ; parité entre données réelles et exemple, le parseur
  de références UD sur quinze formes, les changements d'indice, le périmètre
  (PERSO + BASE/OPTION = Tout, point par point), les trois contrats de la
  démonstration, le rapprochement aux écarts délibérés. Toute erreur
  JavaScript remontée par la console fait échouer le lot.

Les deux lots se lancent séparément ; chacun affiche à la fin
« N test(s) réussi(s), M échec(s) ». `CHROMIUM_PATH` force un binaire Chromium
précis si celui de Playwright n'est pas installé.

## Le parti pris

**L'historique s'accumule, il ne se reconstitue pas.** L'export GATES est une
photo du jour : il ne dit pas quand un plan est passé à 100 %. Un relevé est
donc archivé à chaque import, un par semaine ISO et par contrat, et rien n'est
jamais supprimé ni réécrit. Ce que la page montre sous un périmètre est
**dérivé** à la lecture des cartes plan par plan archivées, jamais recalculé
dans l'onglet.

**Quatre états, pas trois.** « À faire » est une valeur saisie ; une cellule
vide est un défaut de saisie. Les confondre masquerait le second.

**Un plan garde son identité quand il est réémis.** Une référence UD, c'est une
racine fixe, puis un indice et une révision qui bougent. Comparer par la racine
évite qu'une réémission passe pour un disparu plus un nouveau.

**Le rythme est mesuré, pas lissé.** La saisie est irrégulière — une semaine un
lot entier, la suivante rien. Une moyenne glissante mesurerait surtout la date
du dernier lot. On prend donc la cadence moyenne depuis le premier relevé, et
le bouton « ? » de la colonne *fin estimée* refait le calcul avec les chiffres
de la ligne, pour que personne n'ait à faire confiance sur parole.

**Tout le monde regarde la même chose.** Pas de colonnes à choisir, pas de
jalons à déplacer : ce qui se partage (jalons, contrats, seconde base) est dans
la configuration et le classeur, et seule la mise en page reste locale.

**Aucun nom de colonne en dur.** Tout se déduit de l'en-tête et du contenu. Si
l'export change de colonnes, il n'y a rien à modifier.
