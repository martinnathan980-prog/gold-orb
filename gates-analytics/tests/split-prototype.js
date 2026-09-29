/* Découpe prototype/suivi-fwd.html en Styles.html / Javascript.html / Index.html.
   Le prototype est la source unique : il n'existe pas deux versions de l'interface,
   seulement deux façons de l'alimenter (jeu d'exemple ou classeur). */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const racine = path.join(__dirname, '..');
const { echapperChevrons } = require('./echapper-chevrons');

const texteSource = fs.readFileSync(path.join(racine, 'prototype', 'suivi-fwd.html'), 'utf8');
const src = texteSource.split('\n');

/* La livraison. Les quatre fichiers que Nathan recolle à la main — Code,
   Index, Styles, Javascript — portent la même, pour que la page et le
   Diagnostic nomment celui qui serait resté à une livraison d'avant (débrief
   17 : un Index d'avant avec le Javascript du jour, et une page blanche).
   C'est l'empreinte de ce qui les produit : le prototype, le modèle d'Index
   et Code.gs sans sa propre ligne d'édition — la même source redonne la même
   livraison, et une modification de l'un des trois en fait une nouvelle. */
const cheminCode = path.join(racine, 'Code.gs');
const code = fs.readFileSync(cheminCode, 'utf8');
const LIGNE_EDITION = /^const EDITION = '[0-9a-f]*';$/m;
if (!LIGNE_EDITION.test(code)) throw new Error("Code.gs : ligne « const EDITION = '…'; » introuvable");
const modeleIndex = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
const EDITION = crypto.createHash('sha1')
  .update(texteSource).update('\0').update(modeleIndex).update('\0').update(code.replace(LIGNE_EDITION, ''))
  .digest('hex').slice(0, 7);
function poser(texte, marque, par, fichier) {
  if (texte.split(marque).length !== 2) throw new Error(fichier + ' : marque de livraison introuvable ou répétée — ' + marque);
  return texte.replace(marque, par);
}
function borne(motif, depuis) {
  for (let i = depuis || 0; i < src.length; i++) if (src[i].trim() === motif) return i;
  throw new Error('balise introuvable : ' + motif);
}
const s0 = borne('<style>'), s1 = borne('</style>', s0);
const j0 = borne('<script>', s1), j1 = borne('</script>', j0);

fs.writeFileSync(path.join(racine, 'Styles.html'),
  poser(src.slice(s0, s1 + 1).join('\n') + '\n', '--suivi-fwd-edition: "source";',
        '--suivi-fwd-edition: "' + EDITION + '";', 'Styles'));

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
const corps = echapperChevrons(poser(livre.join('\n'), "var EDITION = 'source';",
  "var EDITION = '" + EDITION + "';", 'Javascript'));
/* La dernière ligne dit le fichier entier : le Diagnostic la cherche, pour
   reconnaître un Javascript collé en partie (FIN_DU_JAVASCRIPT dans Code.gs). */
fs.writeFileSync(path.join(racine, 'Javascript.html'),
  '<script>\n' + corps.texte + '\n/* suivi-fwd : fin du fichier Javascript, livraison ' + EDITION + ' */\n</script>\n');

const markup = src.slice(s1 + 1, j0).join('\n').replace(/^\n+|\n+$/g, '');
const index = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
fs.writeFileSync(path.join(racine, 'Index.html'),
  poser(index, "window.SUIVI_FWD_LIVRAISON_INDEX = 'source';",
        "window.SUIVI_FWD_LIVRAISON_INDEX = '" + EDITION + "';", 'Index').replace('<!--MARKUP-->', markup));
/* Et Code.gs, réécrit seulement si sa livraison change. */
const codeLivre = code.replace(LIGNE_EDITION, "const EDITION = '" + EDITION + "';");
if (codeLivre !== code) fs.writeFileSync(cheminCode, codeLivre);
console.log('Styles.html, Javascript.html et Index.html régénérés depuis le prototype'
  + ' — ' + corps.remplacements + ' chevrons échappés dans les chaînes — livraison ' + EDITION);
