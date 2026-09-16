# Suivi FWD

Tableau de bord de l'avancement FWD des plans d'intégration électrique, à
poser dans un classeur Google Sheets. La mise en place et le geste
hebdomadaire sont dans **[PROCEDURE.md](PROCEDURE.md)**.

## Ce qu'il y a dans ce dossier

| Fichier | Rôle |
|---|---|
| `Code.gs` | Serveur : lecture de la feuille, modèle de colonnes, historique, jalons |
| `Index.html` | Page ; elle injecte les données du classeur au rendu, sans aller-retour |
| `Styles.html` | Feuille de style |
| `Javascript.html` | Interface |
| `appsscript.json` | Manifeste (fuseau, portées OAuth) |
| `prototype/` | La même interface, autonome, avec un jeu d'exemple — c'est la source |
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
ferait perdre au découpage suivant. Tout passe par le prototype.

## Tests

```sh
npm install
npm test
```

- `npm run test:addon` — 67 tests. Le vrai `Code.gs` tourne dans Node contre un
  classeur en mémoire (`tests/faux-classeur.js`), sur un export volontairement
  pénible : lignes de titre, groupes fusionnés, en-têtes accentués ou
  dupliqués, ligne vide au milieu, avancements de toutes les formes. Puis la
  page qu'Apps Script rendrait est chargée dans un vrai navigateur et comparée
  aux comptes du serveur. Couvre aussi : feuille vide, feuille sans colonne
  d'avancement, historique corrompu, 4 000 plans, jalons hostiles.
- `npm run test:interface` — 175 tests sur l'interface elle-même. Elle
  n'essaie pas seulement de vérifier que ça marche : recherches avec balises,
  expressions régulières, 3 000 caractères ou émoji, jalon au texte injecté,
  `localStorage` corrompu puis inaccessible, zoom et déplacement extrêmes,
  sept largeurs d'écran, clavier seul, contraste dans les deux thèmes. Toute
  erreur JavaScript remontée par la console fait échouer le lot.

`CHROMIUM_PATH` force un binaire Chromium précis si celui de Playwright n'est
pas installé.

## Le parti pris

**L'historique s'accumule, il ne se reconstitue pas.** L'export GATES est une
photo du jour : il ne dit pas quand un plan est passé à 100 %. Un relevé est
donc archivé à chaque import, un par semaine ISO, et rien n'est jamais
supprimé.

**Quatre états, pas trois.** « À faire » est une valeur saisie ; une cellule
vide est un défaut de saisie. Les confondre masquerait le second.

**Le rythme est mesuré, pas lissé.** La saisie est irrégulière — une semaine un
lot entier, la suivante rien. Une moyenne glissante mesurerait surtout la date
du dernier lot. On prend donc la cadence moyenne depuis le premier relevé, et
le bouton « ? » de la colonne *fin estimée* refait le calcul avec les chiffres
de la ligne, pour que personne n'ait à faire confiance sur parole.

**Aucun nom de colonne en dur.** Tout se déduit de l'en-tête et du contenu. Si
l'export change de colonnes, il n'y a rien à modifier.
