/**
 * Tests des fonctions serveur PURES (sans SpreadsheetApp).
 * On les extrait du fichier livré et on les évalue isolément.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const RACINE = path.join(__dirname, '..', 'src');
let ok = 0, ko = 0;
const V = '\x1b[32m', R = '\x1b[31m', Z = '\x1b[0m';
function eq(t, a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x === y) { ok++; console.log('  ' + V + 'OK' + Z + '   ' + t); }
  else { ko++; console.log('  ' + R + 'KO' + Z + '   ' + t +
                           '\n         attendu ' + y + '\n         obtenu  ' + x); }
}
function vrai(t, c) { eq(t, !!c, true); }

/** Extrait une fonction nommée du source et l'évalue seule. */
function extraire(fichier, nom) {
  const source = fs.readFileSync(path.join(RACINE, fichier), 'utf8');
  const debut = source.indexOf('function ' + nom + '(');
  if (debut === -1) throw new Error(nom + ' introuvable dans ' + fichier);
  let profondeur = 0, i = source.indexOf('{', debut), fin = -1;
  for (; i < source.length; i++) {
    if (source[i] === '{') profondeur++;
    else if (source[i] === '}') { profondeur--; if (profondeur === 0) { fin = i + 1; break; } }
  }
  const contexte = vm.createContext({});
  vm.runInContext(source.slice(debut, fin) + '\nglobalThis.__f = ' + nom + ';', contexte);
  return contexte.__f;
}

console.log('\nRepository — découpage en plages contiguës');
const plages = extraire('server/Repository.gs', 'decouperEnPlages_');
eq('lignes contiguës -> une plage', plages([2, 3, 4]), [{ debut: 2, fin: 4 }]);
eq('deux groupes', plages([2, 3, 4, 9, 10]), [{ debut: 2, fin: 4 }, { debut: 9, fin: 10 }]);
eq('ligne isolée', plages([7]), [{ debut: 7, fin: 7 }]);
eq('désordonné', plages([10, 2, 9, 3]), [{ debut: 2, fin: 3 }, { debut: 9, fin: 10 }]);
eq('vide', plages([]), []);
eq('tout isolé', plages([2, 4, 6]),
   [{ debut: 2, fin: 2 }, { debut: 4, fin: 4 }, { debut: 6, fin: 6 }]);

console.log('\nApi — nettoyage du numéro de ligne');
const nettoyer = extraire('server/Api.gs', 'nettoyer_');
eq('_ligne retiré', nettoyer({ 'PN Global': 'A', _ligne: 12 }), { 'PN Global': 'A' });
eq('autres champs conservés', nettoyer({ a: 1, b: 2, _ligne: 3 }), { a: 1, b: 2 });

console.log('\nApi — validation');
const exigerTexte = extraire('server/Api.gs', 'exigerTexte_');
eq('texte nettoyé', exigerTexte('  A1  ', 'Le PN'), 'A1');
[undefined, null, '', '   '].forEach(function (v) {
  let leve = false;
  try { exigerTexte(v, 'Le PN'); } catch (e) { leve = /obligatoire/.test(e.message); }
  vrai('refuse ' + JSON.stringify(v), leve);
});

const src = fs.readFileSync(path.join(RACINE, 'server/Api.gs'), 'utf8');
const ctxStatut = vm.createContext({ CFG: { STATUTS: ['En étude', 'Validé', 'Obsolète'],
                                            STATUT_DEFAUT: 'En étude' } });
const d = src.indexOf('function validerStatut_(');
let p = 0, i = src.indexOf('{', d), f = -1;
for (; i < src.length; i++) {
  if (src[i] === '{') p++; else if (src[i] === '}') { p--; if (p === 0) { f = i + 1; break; } }
}
vm.runInContext(src.slice(d, f) + '\nglobalThis.__v = validerStatut_;', ctxStatut);
const validerStatut = ctxStatut.__v;
eq('casse normalisée', validerStatut('validé'), 'Validé');
eq('espaces ignorés', validerStatut('  Obsolète '), 'Obsolète');
eq('vide -> défaut', validerStatut(''), 'En étude');
let leve = false;
try { validerStatut('Invalidé'); } catch (e) { leve = /Statut invalide/.test(e.message); }
vrai('« Invalidé » est refusé à la saisie', leve);

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z);
process.exit(ko === 0 ? 0 : 1);
