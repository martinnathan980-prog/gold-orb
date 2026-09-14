/**
 * La version « à coller » dans l'éditeur Apps Script doit rester le MÊME code
 * que src/. C'est une concaténation, donc le risque n'est pas la logique :
 * c'est qu'un fichier manque, qu'un include ne soit pas résolu, ou qu'un
 * ajout dans src/ ne parte jamais dans le bundle.
 *   node test/test-bundle.js
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const RACINE = path.join(__dirname, '..');
const SORTIE = path.join(RACINE, 'build', 'appsscript');

let ok = 0, ko = 0;
const V = '\x1b[32m', R = '\x1b[31m', Z = '\x1b[0m';
function eq(t, a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x === y) { ok++; console.log('  ' + V + 'OK' + Z + '   ' + t); }
  else { ko++; console.log('  ' + R + 'KO' + Z + '   ' + t +
                           '\n         attendu ' + y + '\n         obtenu  ' + x); }
}
function vrai(t, c) { eq(t, !!c, true); }
function faux(t, c) { eq(t, !!c, false); }
function bloc(t) { console.log('\n' + t); }

// On reconstruit : le test porte sur ce que produit le script, pas sur un
// fichier qui traînerait d'une exécution précédente.
execFileSync(process.execPath, [path.join(RACINE, 'build', 'build-appsscript.js')]);

const lireSortie = function (f) { return fs.readFileSync(path.join(SORTIE, f), 'utf8'); };
const lireSrc = function (f) { return fs.readFileSync(path.join(RACINE, 'src', f), 'utf8'); };

bloc('Code.gs — les 4 fichiers serveur, intacts');
const code = lireSortie('Code.gs');
try { new vm.Script(code, { filename: 'Code.gs' }); ok++; console.log('  ' + V + 'OK' + Z + '   syntaxe'); }
catch (e) { ko++; console.log('  ' + R + 'KO' + Z + '   syntaxe : ' + e.message); }

['Config.gs', 'Repository.gs', 'Api.gs', 'Setup.gs'].forEach(function (f) {
  vrai(f + ' repris en entier', code.indexOf(lireSrc('server/' + f).trim()) !== -1);
});
vrai('CFG est défini avant tout le reste',
     code.indexOf('const CFG') < code.indexOf('function doGet'));
vrai('les fonctions exposées au client sont là',
     ['getToutLeContenu', 'saveBoite', 'addBoite', 'deleteBoiteEntiere', 'dupliquerBoite',
      'saveNomenclature', 'addSousEnsemble', 'deleteNomenclature', 'getCatalogueComposants']
       .every(function (f) { return code.indexOf('function ' + f) !== -1; }));
vrai('le menu du Sheet aussi', code.indexOf('function onOpen') !== -1);

bloc('Index.html — les 14 fichiers client, includes résolus');
const idx = lireSortie('Index.html');
faux('plus aucun <?!= include() ?>', /<\?!=/.test(idx));
const attendus = (lireSrc('Index.html').match(/include\('([^']+)'\)/g) || [])
  .map(function (m) { return m.match(/'([^']+)'/)[1]; });
eq('14 includes dans la source', attendus.length, 14);
attendus.forEach(function (nom) {
  const source = lireSrc(nom + '.html');
  vrai(nom + ' repris en entier', idx.indexOf(source) !== -1);
});
vrai('l\'ordre de src/ est conservé (Composants avant Types)',
     idx.indexOf('CATEGORIES_COMPOSANT') < idx.indexOf('const CHAMPS_BOITE'));
vrai('Dialogues est chargé après Dom (enregistrerActions doit exister)',
     idx.indexOf('function enregistrerActions') < idx.indexOf('function ouvrirDialogue'));

const blocsScript = idx.match(/<script>[\s\S]*?<\/script>/g) || [];
blocsScript.forEach(function (b, i) {
  const corps = b.replace(/^<script>/, '').replace(/<\/script>$/, '');
  try { new Function(corps); ok++; console.log('  ' + V + 'OK' + Z + '   bloc <script> ' + (i + 1)); }
  catch (e) { ko++; console.log('  ' + R + 'KO' + Z + '   bloc <script> ' + (i + 1) + ' : ' + e.message); }
});
vrai('Bootstrap reste en CDN (Apps Script l\'autorise)',
     /cdn\.jsdelivr\.net\/npm\/bootstrap/.test(idx));

bloc('catalogue.csv — de quoi remplir le classeur catalogue');
const csv = lireSortie('catalogue.csv');
eq('BOM UTF-8 (sinon Sheets casse les accents)', csv.charCodeAt(0), 0xFEFF);
const lignes = csv.slice(1).trim().split('\r\n');
eq('en-têtes attendus par Api.gs',
   lignes[0], 'Catégorie;Fonction;Norme;Référence;Désignation');
vrai('au moins 30 composants', lignes.length - 1 >= 30);
eq('les 3 catégories sont couvertes',
   Array.from(new Set(lignes.slice(1).map(function (l) { return l.split(';')[0]; }))).sort(),
   ['composant', 'electrique', 'mecanique']);
faux('aucune cellule vide en fonction ou référence',
     lignes.slice(1).some(function (l) {
       const c = l.split(';');
       return !c[1] || !c[3];
     }));
// Les en-têtes du CSV doivent être ceux que le client sait relire.
const composants = fs.readFileSync(path.join(RACINE, 'src/client/Composants.html'), 'utf8');
['Catégorie', 'Fonction', 'Norme', 'Référence', 'Désignation'].forEach(function (c) {
  vrai('« ' + c +' » est lu par composantDepuisCatalogue', composants.indexOf("'" + c + "'") !== -1);
});

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z);
process.exit(ko === 0 ? 0 : 1);
