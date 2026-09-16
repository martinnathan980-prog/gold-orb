# Prototype « Suivi FWD »

`suivi-fwd.html` est la page autonome publiée comme artefact : un seul fichier,
aucune dépendance en dehors des polices Google, un jeu de données de démonstration
intégré. C'est la maquette de référence de l'interface — l'add-on Apps Script du
dossier parent en reprend les règles.

## Lancer la batterie de tests

```sh
npm install --no-save playwright
node tests/build-apercu.js      # écrit apercu.html à côté
node tests/batterie.js
```

`build-apercu.js` enveloppe la page dans le squelette de publication. S'il trouve
un dossier `fonts/` contenant `local.css`, il y bascule les polices pour que les
tests tournent hors ligne.

`CHROMIUM_PATH` force un binaire Chromium précis quand celui de Playwright n'est
pas installé.

La batterie ne se contente pas de vérifier que ça marche : elle essaie de casser
la page — recherches hostiles (balises, expressions régulières, 3 000 caractères,
émoji), jalons au texte injecté ou de 400 caractères, suppression de tous les
jalons, `localStorage` corrompu puis inaccessible, zoom et déplacement extrêmes
du graphique, sept largeurs d'écran, clavier seul, contraste dans les deux thèmes.
Toute erreur JavaScript remontée par la console fait échouer le lot.
