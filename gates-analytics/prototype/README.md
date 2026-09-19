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
émoji), jalons de configuration au texte injecté ou de 400 caractères, source
sans jalon, `localStorage` corrompu puis inaccessible, zoom et déplacement
extrêmes du graphique, sept largeurs d'écran, clavier seul, contraste dans les
deux thèmes. Elle vérifie aussi ce que le lot du débrief a apporté : la parité
entre « Données réelles » et « Exemple », les trois contrats de démonstration,
le périmètre (PERSO + BASE/OPTION = Tout, graphique compris), les changements
de solution et d'indice appariés par racine, le rapprochement avec SEE — une
seconde base aux écarts délibérés, sa jauge, ses tuiles et son tableau à
l'identique —, l'échelle du graphique, et un paquet vide du classeur qui
s'affiche vide en le disant. Le
compte de tests à jour est dans le README à la racine. Toute erreur JavaScript
remontée par la console fait échouer le lot.
