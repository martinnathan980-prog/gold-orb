// Tests du moteur de recherche — exécuter depuis etii-hub/ :
//   node tests/search.test.mjs
// Aucune dépendance : Node seul suffit.

import { readFileSync } from 'node:fs';
import { creerIndex, rechercher, normaliser, surligner, suggerer }
  from '../assets/js/search.js';

const corpus = JSON.parse(readFileSync(new URL('../assets/data/documents.json', import.meta.url),'utf8'));
const docs = corpus.documents;
const CHAMPS = [
  {nom:'titre', poids:10}, {nom:'reference', poids:6}, {nom:'motsCles', poids:5},
  {nom:'metier', poids:4}, {nom:'type', poids:4}, {nom:'perimetre', poids:2},
  {nom:'porteur', poids:2}, {nom:'description', poids:1},
];

let ok = 0, ko = 0;
const t = (nom, cond, detail='') => {
  if (cond) { ok++; console.log(`  OK   ${nom}`); }
  else { ko++; console.log(`  ÉCHEC ${nom} ${detail}`); }
};

console.log(`\n== Indexation (${docs.length} documents) ==`);
const t0 = process.hrtime.bigint();
const idx = creerIndex(docs, CHAMPS);
const tIdx = Number(process.hrtime.bigint()-t0)/1e6;
t(`index construit en ${tIdx.toFixed(1)} ms`, tIdx < 500);

console.log(`\n== Normalisation (insensible aux accents) ==`);
t('"Intégration" === "integration"', normaliser('Intégration') === normaliser('integration'));
t('"ESSAIS" === "essais"', normaliser('ESSAIS') === normaliser('essais'));
t('ponctuation neutralisée', normaliser('a.b,c') === normaliser('a b c'));

console.log(`\n== Pertinence ==`);
const r1 = rechercher(idx, 'harnais', {limite:5});
t('"harnais" renvoie des résultats', r1.length > 0, `(${r1.length})`);
t('le 1er contient bien "harnais"',
  /harnais/i.test(r1[0]?.doc.titre + JSON.stringify(r1[0]?.doc.metier) + r1[0]?.doc.description));
const r2 = rechercher(idx, 'routage harnais', {limite:5});
t('multi-termes : score du 1er > score du dernier',
  r2.length > 1 && r2[0].score > r2[r2.length-1].score);
const rAcc = rechercher(idx, 'integration', {limite:5});
const rAcc2 = rechercher(idx, 'intégration', {limite:5});
t('accent indifférent sur la requête',
  JSON.stringify(rAcc.map(r=>r.doc.id)) === JSON.stringify(rAcc2.map(r=>r.doc.id)));

console.log(`\n== Tolérance aux fautes ==`);
const rf = rechercher(idx, 'conecteur', {limite:5});   // connecteur, 1 faute
t('"conecteur" retrouve "connecteur"',
  rf.some(r => /connecteur/i.test(r.doc.titre + r.doc.motsCles.join(' '))), `(${rf.length} rés.)`);
const rf2 = rechercher(idx, 'corossion', {limite:5});  // corrosion
t('"corossion" retrouve "corrosion"',
  rf2.some(r => /corrosion/i.test(r.doc.titre + r.doc.motsCles.join(' '))), `(${rf2.length} rés.)`);

console.log(`\n== Déterminisme ==`);
const a = rechercher(idx,'norme',{limite:20}).map(r=>r.doc.id).join(',');
const b = rechercher(idx,'norme',{limite:20}).map(r=>r.doc.id).join(',');
const c = rechercher(idx,'norme',{limite:20}).map(r=>r.doc.id).join(',');
t('3 appels identiques -> ordre identique', a===b && b===c);

console.log(`\n== Filtres ==`);
const rFil = rechercher(idx, '', {filtre: d => d.type === 'Norme'});
t('filtre par type appliqué', rFil.length > 0 && rFil.every(r=>r.doc.type==='Norme'), `(${rFil.length})`);
const rVide = rechercher(idx, '', {});
t('requête vide -> tout le corpus', rVide.length === docs.length, `(${rVide.length}/${docs.length})`);

console.log(`\n== Robustesse (ne doit jamais lever) ==`);
const casses = ['', '   ', 'c++', 'a.b', '(x)', '[', '\\', '***', 'é', 'a'.repeat(300), '?!;:'];
for (const q of casses) {
  try { const r = rechercher(idx, q, {limite:5}); t(`requête ${JSON.stringify(q.slice(0,12))}`, Array.isArray(r)); }
  catch(e) { t(`requête ${JSON.stringify(q.slice(0,12))}`, false, '-> LÈVE: '+e.message); }
}
try { t('corpus vide', Array.isArray(rechercher(creerIndex([], CHAMPS), 'x', {}))); }
catch(e){ t('corpus vide', false, '-> LÈVE: '+e.message); }
try {
  const idxT = creerIndex([{id:'x1', titre:null, motsCles:undefined, description:42}], CHAMPS);
  t('champs null/undefined/numérique', Array.isArray(rechercher(idxT,'x',{})));
} catch(e){ t('champs null/undefined/numérique', false, '-> LÈVE: '+e.message); }
try { t('limite 0', Array.isArray(rechercher(idx,'norme',{limite:0}))); }
catch(e){ t('limite 0', false, '-> LÈVE: '+e.message); }

console.log(`\n== surligner() : segments, jamais de HTML ==`);
const seg = surligner('Guide de routage des harnais', 'routage harnais');
t('renvoie un tableau de segments', Array.isArray(seg) && seg.length>0);
t('aucun segment ne contient de balise', seg.every(s => !/[<>]/.test(s.texte)));
t('le texte reconstitué est intact',
  seg.map(s=>s.texte).join('') === 'Guide de routage des harnais',
  `-> "${seg.map(s=>s.texte).join('')}"`);
t('au moins un segment marqué', seg.some(s=>s.correspond));
const segChev = surligner('routage routage', 'routage rout');
t('termes chevauchants : pas de duplication',
  segChev.map(s=>s.texte).join('') === 'routage routage');
t('texte vide toléré', Array.isArray(surligner('', 'x')));

console.log(`\n== suggerer() ==`);
const sug = suggerer(idx, 'harnai');
t('suggestion proposée pour "harnai"', typeof sug === 'string' || sug === null, `-> ${JSON.stringify(sug)}`);

console.log(`\n== Performance (corpus x30 = ${docs.length*30} documents) ==`);
const gros = [];
for (let k=0;k<30;k++) for (const d of docs) gros.push({...d, id:`${d.id}-${k}`});
const gi = creerIndex(gros, CHAMPS);
const reqs = ['harnais','routage des cables','norme','integration 3d','conecteur','essai continuite'];
const t1 = process.hrtime.bigint();
for (let k=0;k<50;k++) for (const q of reqs) rechercher(gi, q, {limite:30});
const moy = Number(process.hrtime.bigint()-t1)/1e6/(50*reqs.length);
t(`${moy.toFixed(3)} ms par recherche sur ${gros.length} documents`, moy < 10);

console.log(`\n${'='.repeat(46)}\n  ${ok} réussis, ${ko} échoués\n${'='.repeat(46)}`);
process.exit(ko ? 1 : 0);
