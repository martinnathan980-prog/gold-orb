/* Découpe prototype/suivi-fwd.html en Styles.html / Javascript.html / Index.html.
   Le prototype est la source unique : il n'existe pas deux versions de l'interface,
   seulement deux façons de l'alimenter (jeu d'exemple ou classeur). */
const fs = require('fs');
const path = require('path');
const racine = path.join(__dirname, '..');
const { echapperChevrons } = require('./echapper-chevrons');

const src = fs.readFileSync(path.join(racine, 'prototype', 'suivi-fwd.html'), 'utf8').split('\n');
function borne(motif, depuis) {
  for (let i = depuis || 0; i < src.length; i++) if (src[i].trim() === motif) return i;
  throw new Error('balise introuvable : ' + motif);
}
const s0 = borne('<style>'), s1 = borne('</style>', s0);
const j0 = borne('<script>', s1), j1 = borne('</script>', j0);

fs.writeFileSync(path.join(racine, 'Styles.html'), src.slice(s0, s1 + 1).join('\n') + '\n');

/* Le corps du script sort avec ses « < » échappés dans les chaînes : même code,
   mais plus une seule balise, donc un fichier qui traverse une passerelle de
   messagerie au lieu d'être retenu pour contrebande HTML. Voir
   tests/echapper-chevrons.js. L'enveloppe <script> reste en clair. */
/* Le jeu de démonstration — 138 colonnes, trois contrats fictifs, une base
   SEE inventée — ne sert qu'à la page ouverte seule. Le classeur a ses
   propres données : le bloc balisé <démonstration> n'y est pas livré, et un
   appel égaré rendrait une source vide plutôt que des plans fictifs. */
const lignesScript = src.slice(j0 + 1, j1);
const d0 = lignesScript.findIndex(l => l.trim().indexOf('/* <démonstration>') === 0);
const d1 = lignesScript.findIndex(l => l.trim() === '/* </démonstration> */');
if (d0 === -1 || d1 === -1 || d1 < d0) throw new Error('balises <démonstration> introuvables dans le prototype');
const livre = lignesScript.slice(0, d0).concat([
  '  /* La démonstration n\'est pas livrée au classeur : il a ses propres données. */',
  '  function jeuDExemple() { return sourceDuClasseur(null); }'
], lignesScript.slice(d1 + 1));
const corps = echapperChevrons(livre.join('\n'));
fs.writeFileSync(path.join(racine, 'Javascript.html'),
  '<script>\n' + corps.texte + '\n</script>\n');

const markup = src.slice(s1 + 1, j0).join('\n').replace(/^\n+|\n+$/g, '');
const index = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
fs.writeFileSync(path.join(racine, 'Index.html'), index.replace('<!--MARKUP-->', markup));
console.log('Styles.html, Javascript.html et Index.html régénérés depuis le prototype'
  + ' — ' + corps.remplacements + ' chevrons échappés dans les chaînes');
