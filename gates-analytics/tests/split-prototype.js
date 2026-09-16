/* Découpe prototype/suivi-fwd.html en Styles.html / Javascript.html / Index.html.
   Le prototype est la source unique : il n'existe pas deux versions de l'interface,
   seulement deux façons de l'alimenter (jeu d'exemple ou classeur). */
const fs = require('fs');
const path = require('path');
const racine = path.join(__dirname, '..');

const src = fs.readFileSync(path.join(racine, 'prototype', 'suivi-fwd.html'), 'utf8').split('\n');
function borne(motif, depuis) {
  for (let i = depuis || 0; i < src.length; i++) if (src[i].trim() === motif) return i;
  throw new Error('balise introuvable : ' + motif);
}
const s0 = borne('<style>'), s1 = borne('</style>', s0);
const j0 = borne('<script>', s1), j1 = borne('</script>', j0);

fs.writeFileSync(path.join(racine, 'Styles.html'), src.slice(s0, s1 + 1).join('\n') + '\n');
fs.writeFileSync(path.join(racine, 'Javascript.html'), src.slice(j0, j1 + 1).join('\n') + '\n');

const markup = src.slice(s1 + 1, j0).join('\n').replace(/^\n+|\n+$/g, '');
const index = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
fs.writeFileSync(path.join(racine, 'Index.html'), index.replace('<!--MARKUP-->', markup));
console.log('Styles.html, Javascript.html et Index.html régénérés depuis le prototype');
