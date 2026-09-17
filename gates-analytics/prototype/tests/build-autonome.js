/* Assemble une page de demonstration ENTIEREMENT autonome : un seul fichier
   .html, aucune ressource externe, ouvrable d'un double-clic sur n'importe
   quelle machine, sans reseau.

   Pourquoi : `apercu.html` reste lie au dossier `fonts/`, et la version
   Apps Script va chercher ses polices sur fonts.googleapis.com — que la
   passerelle d'entreprise peut retenir. Ici tout est dans le fichier.

   Deux economies, sinon le fichier pese 1,4 Mo :
   - seul le latin de base est embarque (le francais n'a besoin ni du
     cyrillique, ni du grec, ni du vietnamien, ni du latin etendu) ;
   - Newsreader et IBM Plex Sans sont des polices VARIABLES : un meme fichier
     sert plusieurs graisses. On l'ecrit une fois, avec une plage
     (font-weight: 300 500), au lieu d'une copie par graisse.

   Resultat : 4 polices, ~445 Ko. Pour l'envoyer par mail, l'emballer ensuite
   avec import/empaqueter.py.

       node prototype/tests/build-autonome.js
*/
const fs = require('fs');
const path = require('path');

const racine = path.join(__dirname, '..');
const sortie = process.argv[2] || path.join(racine, 'suivi-fwd-demo.html');

let corps = fs.readFileSync(path.join(racine, 'suivi-fwd.html'), 'utf8');
const css = fs.readFileSync(path.join(racine, 'fonts', 'local.css'), 'utf8');

/* local.css range ses @font-face par alphabet, precedes d'un commentaire.
   On ne garde que « latin », puis on regroupe par FICHIER : c'est lui qui
   decide, pas la graisse declaree. */
const blocs = [...css.matchAll(/\/\* (latin) \*\/\s*(@font-face \{[\s\S]*?\})/g)];
if (!blocs.length) throw new Error('aucun bloc @font-face « latin » dans fonts/local.css');

const parFichier = new Map();
for (const [, , bloc] of blocs) {
  const nom = /url\(fonts\/([^)]+)\)/.exec(bloc)[1];
  const famille = /font-family: '([^']+)'/.exec(bloc)[1];
  const style = /font-style: ([^;]+);/.exec(bloc)[1];
  const poids = Number(/font-weight: ([^;]+);/.exec(bloc)[1]);
  const cle = nom + '|' + famille + '|' + style;
  const f = parFichier.get(cle);
  if (!f) parFichier.set(cle, { nom, bloc, min: poids, max: poids });
  else { f.min = Math.min(f.min, poids); f.max = Math.max(f.max, poids); }
}

const stylePolices = [...parFichier.values()].map(function (f) {
  const chemin = path.join(racine, 'fonts', f.nom);
  const b64 = fs.readFileSync(chemin).toString('base64');
  return f.bloc
    .replace(/url\(fonts\/[^)]+\)/, 'url(data:font/woff2;base64,' + b64 + ')')
    .replace(/font-weight: [^;]+;/,
             'font-weight: ' + (f.min === f.max ? f.min : f.min + ' ' + f.max) + ';')
    /* plus de sous-ensemble : cette police sert desormais tous les caracteres */
    .replace(/\n\s*unicode-range: [^;]+;/, '');
}).join('\n');

const avant = corps.length;
corps = corps.replace(/<link rel="stylesheet" href="https:\/\/fonts\.googleapis\.com[^"]*">/,
                      '<style>\n' + stylePolices + '\n</style>');
if (corps.length === avant) throw new Error('lien Google Fonts introuvable dans suivi-fwd.html');

const tete = '<!doctype html><html lang="fr"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
  '<title>Suivi FWD</title>' +
  '<style>:root{color-scheme:light dark}body{margin:0;font:14px system-ui;background:#f4f2ed}' +
  'img{max-width:100%}[hidden]{display:none!important}</style></head><body>';

fs.writeFileSync(sortie, tete + corps + '\n</body></html>');

const reste = (tete + corps).match(/https?:\/\/(?!www\.w3\.org)/g);
if (reste) throw new Error('ressource externe restante : ' + reste.length);

let brut = 0;
parFichier.forEach(f => { brut += fs.statSync(path.join(racine, 'fonts', f.nom)).size; });
console.log('suivi-fwd-demo.html reconstruit');
console.log('  %d polices embarquees (%d octets bruts)', parFichier.size, brut);
console.log('  %d octets, aucune ressource externe', fs.statSync(sortie).size);
