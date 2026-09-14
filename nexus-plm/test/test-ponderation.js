/**
 * NEXUS — pondération : la somme des parts doit TOUJOURS valoir 100 %.
 * C'est le point le plus facile à casser et le plus visible à l'écran,
 * il a sa propre batterie.   node test/test-ponderation.js
 */
const H = require('./harness.js');

const C = H.chargerClient([
  'client/Dom.html', 'client/Composants.html', 'client/Types.html', 'client/Api.html',
  'client/Store.html', 'client/Compare.html', 'client/ViewGrid.html', 'client/ViewFiche.html',
  'client/ViewCompare.html', 'client/Reglages.html', 'client/Annulation.html',
  'client/Dialogues.html'
]);

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

const somme = function (portee) {
  return C.criteresActifs(portee).reduce(function (t, c) {
    return t + Number(C.Store.poids[portee][c.cle]);
  }, 0);
};
const parts = function (portee) {
  const o = {};
  C.criteresActifs(portee).forEach(function (c) { o[c.cle] = C.Store.poids[portee][c.cle]; });
  return o;
};

C.chargerReglages();

// =====================================================================
bloc('Au départ, chaque portée totalise 100 %');
// =====================================================================
C.reinitialiserPoids();
C.PORTEES.forEach(function (p) {
  eq('somme ' + p.cle, somme(p.cle), 100);
  eq('tous les critères actifs ' + p.cle,
     C.criteresActifs(p.cle).length, p.criteres.length);
});
eq('un type à critère unique vaut 100', C.Store.poids.harnais.reference, 100);
eq('idem plaquette', C.Store.poids.plaquette.motsCles, 100);

// =====================================================================
bloc('Bouger un curseur redistribue les autres');
// =====================================================================
C.reinitialiserPoids();
const avant = parts('structure');
C.reglerPoids('structure', 'montage', 100);
eq('le critère poussé à 100 vaut 100', C.Store.poids.structure.montage, 100);
eq('la somme reste 100', somme('structure'), 100);
eq('tous les autres tombent à 0',
   C.criteresActifs('structure').filter(function (c) {
     return c.cle !== 'montage' && C.Store.poids.structure[c.cle] !== 0;
   }).length, 0);

C.reinitialiserPoids();
C.reglerPoids('structure', 'montage', 50);
eq('somme après passage à 50', somme('structure'), 100);
eq('le critère posé garde exactement sa valeur', C.Store.poids.structure.montage, 50);
vrai('les autres ont diminué',
     C.Store.poids.structure.mecanique < avant.mecanique);
vrai('mais restent proportionnels entre eux',
     Math.abs((C.Store.poids.structure.mecanique / C.Store.poids.structure.dimensions) -
              (avant.mecanique / avant.dimensions)) < 0.35);

C.reinitialiserPoids();
C.reglerPoids('structure', 'montage', 0);
eq('un critère à 0 laisse la somme à 100', somme('structure'), 100);
eq('et vaut bien 0', C.Store.poids.structure.montage, 0);

// Descendre un critère doit faire REMONTER les autres.
C.reinitialiserPoids();
const compAvant = C.Store.poids.structure.mecanique;
C.reglerPoids('structure', 'mecanique', 5);
vrai('baisser un critère remonte les autres', C.Store.poids.structure.montage > 10);
eq('somme toujours 100', somme('structure'), 100);
vrai('le critère baissé a bien baissé', C.Store.poids.structure.mecanique < compAvant);

// =====================================================================
bloc('Aucune dérive après des dizaines de mouvements');
// =====================================================================
C.reinitialiserPoids();
const cles = C.criteresActifs('structure').map(function (c) { return c.cle; });
let derive = 0;
for (let i = 0; i < 300; i++) {
  const cle = cles[i % cles.length];
  C.reglerPoids('structure', cle, (i * 7) % 101);
  if (somme('structure') !== 100) derive++;
}
eq('300 mouvements, aucune dérive', derive, 0);
faux('aucune part négative',
     C.criteresActifs('structure').some(function (c) { return C.Store.poids.structure[c.cle] < 0; }));
faux('aucune part au-dessus de 100',
     C.criteresActifs('structure').some(function (c) { return C.Store.poids.structure[c.cle] > 100; }));

// Valeurs aberrantes en entrée
C.reinitialiserPoids();
[-50, 1e9, NaN, undefined, null, '42', '  30  '].forEach(function (v) {
  C.reglerPoids('structure', 'masse', v);
  eq('entrée ' + JSON.stringify(v) + ' : somme reste 100', somme('structure'), 100);
  vrai('part bornée', C.Store.poids.structure.masse >= 0 && C.Store.poids.structure.masse <= 100);
});

// =====================================================================
bloc('Choisir les critères');
// =====================================================================
C.reinitialiserPoids();
eq('9 critères pour la structure', C.criteresActifs('structure').length, 9);
C.desactiverCritere('structure', 'masse');
eq('8 après retrait', C.criteresActifs('structure').length, 8);
eq('la somme reste 100', somme('structure'), 100);
faux('le critère retiré n\'est plus actif', C.critereEstActif('structure', 'masse'));

C.activerCritere('structure', 'masse');
eq('9 après réajout', C.criteresActifs('structure').length, 9);
eq('somme toujours 100', somme('structure'), 100);
vrai('le critère réajouté a une part non nulle', C.Store.poids.structure.masse > 0);

// On ne retire pas le dernier.
C.reinitialiserPoids();
cles.forEach(function (c) { if (c !== 'montage') C.desactiverCritere('structure', c); });
eq('il reste un critère', C.criteresActifs('structure').length, 1);
eq('il vaut 100', C.Store.poids.structure.montage, 100);
faux('retirer le dernier est refusé', C.desactiverCritere('structure', 'montage'));
eq('il est toujours là', C.criteresActifs('structure').length, 1);

// Un critère écarté sort du résultat, il n'y figure pas « ignoré ».
C.reinitialiserPoids();
C.chargerDonnees({
  boites: [{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  nomenclature: [
    { 'ID_Ligne': 'S1', 'PN Global': 'B1', 'Type': 'Structure boîte', 'PN du type': 's1',
      'Montage': 'Rack', 'Masse (g)': '500', 'Dim Long (mm)': '100', 'Dim Larg (mm)': '50',
      'Nombre de pas': '2', 'DAL': 'A', 'HL': 'A' },
    { 'ID_Ligne': 'S2', 'PN Global': 'B2', 'Type': 'Structure boîte', 'PN du type': 's2',
      'Montage': 'Nez', 'Masse (g)': '500', 'Dim Long (mm)': '100', 'Dim Larg (mm)': '50',
      'Nombre de pas': '2', 'DAL': 'A', 'HL': 'A' }
  ],
  headersBoites: ['PN Global'], headersNom: C.toutesLesColonnesNom(),
  config: { multiBoite: [], multiNom: [], lectureSeuleNom: ['ID_Ligne', 'PN Global'],
            statuts: [], porteurs: [] }
});
C.Store.seuilEquivalence = 0;
const avecMontage = C.equivalencesSousEnsemble('S1')[0];
vrai('le montage figure au résultat',
     avecMontage.criteres.some(function (c) { return c.cle === 'montage'; }));
const scoreAvecMontage = avecMontage.score;

C.desactiverCritere('structure', 'montage');
const sansMontage = C.equivalencesSousEnsemble('S1')[0];
faux('le critère écarté ne figure plus du tout',
     sansMontage.criteres.some(function (c) { return c.cle === 'montage'; }));
vrai('le score remonte puisque le critère qui fâchait est parti',
     sansMontage.score > scoreAvecMontage);
C.reinitialiserPoids();

// =====================================================================
bloc('Les parts pilotent réellement le score');
// =====================================================================
C.reinitialiserPoids();
C.Store.seuilEquivalence = 0;   // après la réinitialisation, qui rétablit le seuil
C.criteresActifs('structure').forEach(function (c) {
  if (c.cle !== 'montage' && c.cle !== 'masse') C.desactiverCritere('structure', c.cle);
});
eq('deux critères retenus', C.criteresActifs('structure').length, 2);

C.reglerPoids('structure', 'montage', 100);   // montage diffère, masse identique
eq('tout sur le critère qui diffère -> 0 %', C.equivalencesSousEnsemble('S1')[0].score, 0);
C.reglerPoids('structure', 'montage', 0);     // tout sur la masse, identique
eq('tout sur le critère identique -> 100 %', C.equivalencesSousEnsemble('S1')[0].score, 100);
C.reglerPoids('structure', 'montage', 50);
eq('moitié-moitié -> 50 %', C.equivalencesSousEnsemble('S1')[0].score, 50);
C.reglerPoids('structure', 'montage', 25);
eq('un quart / trois quarts -> 75 %', C.equivalencesSousEnsemble('S1')[0].score, 75);
C.reinitialiserPoids();

// =====================================================================
bloc('Persistance des réglages');
// =====================================================================
C.reinitialiserPoids();
C.reglerPoids('structure', 'montage', 40);
C.desactiverCritere('structure', 'hl');
const attendu = parts('structure');
C.Store.poids = {}; C.Store.criteresActifs = {};
C.chargerReglages();
eq('les parts sont relues', parts('structure'), attendu);
faux('le critère écarté le reste', C.critereEstActif('structure', 'hl'));
eq('somme intacte après relecture', somme('structure'), 100);

C.reinitialiserPoids();
faux('après réinitialisation, plus rien de personnalisé', C.poidsModifies());
C.desactiverCritere('structure', 'hl');
vrai('un critère écarté compte comme personnalisation', C.poidsModifies());
C.reinitialiserPoids();

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z);
process.exit(ko === 0 ? 0 : 1);
