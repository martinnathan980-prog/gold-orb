/**
 * Tests unitaires — exécution : `node tests/run-tests.js`
 *
 * Le code Apps Script n'est pas un module Node : on charge Code.gs et le bloc
 * <script> de Javascript.html dans un contexte isolé, avec des stubs minimaux.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

/** Les objets renvoyés par le contexte `vm` ont un autre prototype : on compare les structures. */
function memeStructure(reel, attendu, message) {
  assert.strictEqual(JSON.stringify(reel), JSON.stringify(attendu), message);
}

const racine = path.join(__dirname, '..');

// ---------- Chargement du serveur (Code.gs) ----------
const contexteServeur = { console, Date, Math, JSON, Object, Array, Number, String, parseFloat, parseInt, isNaN };
contexteServeur.Utilities = { getUuid: () => 'uuid-test' };
vm.createContext(contexteServeur);
vm.runInContext(fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8'), contexteServeur);
const serveur = contexteServeur;

// ---------- Chargement du client (Javascript.html) ----------
const scriptClient = fs.readFileSync(path.join(racine, 'Javascript.html'), 'utf8')
  .replace(/^<script>\s*/, '')
  .replace(/\s*<\/script>\s*$/, '');
const moduleClient = { exports: {} };
const contexteClient = {
  console, Date, Math, JSON, Object, Array, Number, String, parseFloat, parseInt, isNaN,
  setTimeout, clearTimeout, requestAnimationFrame: (fn) => fn(),
  module: moduleClient,
  window: {},
  document: { addEventListener() {}, querySelector: () => null, getElementById: () => null }
};
vm.createContext(contexteClient);
vm.runInContext(scriptClient, contexteClient);
const client = moduleClient.exports;

// ---------- Micro-harnais ----------
let reussis = 0;
const echecs = [];
function test(nom, fn) {
  try { fn(); reussis++; }
  catch (err) { echecs.push({ nom, message: err.message }); }
}

// =====================================================================
//  valeurNumerique
// =====================================================================
[serveur, client].forEach((impl, i) => {
  const cote = i === 0 ? 'serveur' : 'client';

  test(`[${cote}] valeurNumerique gère %, virgule et espaces insécables`, () => {
    assert.strictEqual(impl.valeurNumerique('75%'), 75);
    assert.strictEqual(impl.valeurNumerique('75 %'), 75);
    assert.strictEqual(impl.valeurNumerique('1 234,5'), 1234.5);
    assert.strictEqual(impl.valeurNumerique('-12'), -12);
    assert.ok(Number.isNaN(impl.valeurNumerique('')));
    assert.ok(Number.isNaN(impl.valeurNumerique('   ')));
    assert.ok(Number.isNaN(impl.valeurNumerique('en cours')));
    assert.ok(Number.isNaN(impl.valeurNumerique('12/03/2026')));
  });

  test(`[${cote}] classerFWD : règle numérique`, () => {
    assert.strictEqual(impl.classerFWD('100'), 'termine');
    assert.strictEqual(impl.classerFWD('100%'), 'termine');
    assert.strictEqual(impl.classerFWD('50'), 'encours');
    assert.strictEqual(impl.classerFWD('0'), 'vide');
    assert.strictEqual(impl.classerFWD('0%'), 'vide');
  });

  test(`[${cote}] classerFWD : "1000" n'est plus compté comme terminé par accident`, () => {
    // L'ancien code testait s.includes('100') : "1000" passait pour "100%".
    assert.strictEqual(impl.classerFWD('1000'), 'termine'); // >= 100 : terminé, mais via la règle numérique
    assert.strictEqual(impl.classerFWD('1001 pièces'), 'encours'); // texte : pas de faux positif
  });

  test(`[${cote}] classerFWD : mots-clés et accents`, () => {
    assert.strictEqual(impl.classerFWD('Terminé'), 'termine');
    assert.strictEqual(impl.classerFWD('ACHEVÉ'), 'termine');
    assert.strictEqual(impl.classerFWD('Clôturé'), 'termine');
    assert.strictEqual(impl.classerFWD('En cours'), 'encours');
    assert.strictEqual(impl.classerFWD('À faire'), 'vide');
    assert.strictEqual(impl.classerFWD('Non renseigné'), 'vide');
    assert.strictEqual(impl.classerFWD(''), 'vide');
    assert.strictEqual(impl.classerFWD('  '), 'vide');
    assert.strictEqual(impl.classerFWD('-'), 'vide');
    assert.strictEqual(impl.classerFWD(null), 'vide');
  });

  test(`[${cote}] classerFWD : serveur et client donnent le même résultat`, () => {
    const echantillons = ['100', '0', '', '50%', 'Terminé', 'en cours', 'à faire', 'N/A', '-', 'blabla', '1,5'];
    echantillons.forEach(v => {
      assert.strictEqual(serveur.classerFWD(v), client.classerFWD(v), `divergence sur "${v}"`);
    });
  });
});

// =====================================================================
//  Semaines ISO
// =====================================================================
test('numeroSemaineISO : cas de référence ISO-8601', () => {
  assert.strictEqual(serveur.numeroSemaineISO(new Date(2026, 0, 1)), '2026-S01');   // jeudi
  assert.strictEqual(serveur.numeroSemaineISO(new Date(2026, 8, 15)), '2026-S38');
  assert.strictEqual(serveur.numeroSemaineISO(new Date(2021, 0, 1)), '2020-S53');   // appartient à 2020
  assert.strictEqual(serveur.numeroSemaineISO(new Date(2024, 11, 30)), '2025-S01'); // appartient à 2025
});

test('numeroSemaineISO : zéro de tête pour garantir un tri lexicographique correct', () => {
  const semaines = [new Date(2026, 1, 2), new Date(2026, 4, 4), new Date(2026, 10, 2)]
    .map(serveur.numeroSemaineISO);
  assert.deepStrictEqual(semaines.slice().sort(), semaines);
  semaines.forEach(s => assert.match(s, /^\d{4}-S\d{2}$/));
});

test('normaliserSemaine : normalise et rejette les formats invalides', () => {
  assert.strictEqual(serveur.normaliserSemaine('2026-s8'), '2026-S08');
  assert.strictEqual(serveur.normaliserSemaine(' 2026 - S 38 '), '2026-S38');
  assert.strictEqual(serveur.normaliserSemaine('2026-S54'), null);
  assert.strictEqual(serveur.normaliserSemaine('2026-S00'), null);
  assert.strictEqual(serveur.normaliserSemaine('semaine 38'), null);
  assert.strictEqual(serveur.normaliserSemaine(''), null);
});

// =====================================================================
//  Détection des en-têtes et des colonnes
// =====================================================================
const FEUILLE = [
  ['', 'Informations principales', '', '', 'FWD', ''],
  ['Reference UD', 'Nom installation', 'ATA', 'ECP', 'Avancement', 'Commentaire'],
  ['UD-001', 'Cockpit', '24', 'ECP-1', '100%', 'RAS'],
  ['UD-002', 'Cabine', '25', 'ECP-2', '', ''],
  ['', '', '', '', '', ''],
  ['UD-003', 'Soute', '26', 'ECP-3', 'En cours', "Attente d'accès"]
];

test('detecterLigneEntete trouve la ligne « Reference UD »', () => {
  assert.strictEqual(serveur.detecterLigneEntete(FEUILLE), 1);
});

test('propagerGroupes remplit les cellules fusionnées', () => {
  const groupes = serveur.propagerGroupes(FEUILLE[0], 6);
  assert.deepStrictEqual(groupes, ['', 'Informations principales', 'Informations principales',
    'Informations principales', 'FWD', 'FWD']);
});

test('trouverIndexFWD croise le groupe et le nom de colonne', () => {
  const groupes = serveur.propagerGroupes(FEUILLE[0], 6);
  assert.strictEqual(serveur.trouverIndexFWD(FEUILLE[1], groupes), 4);
});

test('trouverIndexFWD : repli sur « Réalisation FWD » puis sur « fwd »', () => {
  assert.strictEqual(serveur.trouverIndexFWD(['Réf', 'Réalisation FWD'], ['', '']), 1);
  assert.strictEqual(serveur.trouverIndexFWD(['Réf', 'Statut FWD'], ['', '']), 1);
  assert.strictEqual(serveur.trouverIndexFWD(['Réf', 'ATA'], ['', '']), -1);
});

test('ligneNonVide écarte les lignes entièrement vides', () => {
  const lignes = FEUILLE.slice(2).filter(serveur.ligneNonVide);
  assert.strictEqual(lignes.length, 3);
});

// =====================================================================
//  Sécurité : échappement
// =====================================================================
test('echapper neutralise le HTML issu de la feuille', () => {
  assert.strictEqual(client.echapper('<img src=x onerror=alert(1)>'),
    '&lt;img src=x onerror=alert(1)&gt;');
  assert.strictEqual(client.echapper('Tom & Jerry'), 'Tom &amp; Jerry');
});

test("echapper protège les attributs contenant une apostrophe (cas fréquent en français)", () => {
  // Un groupe nommé « Définition d'ensemble » cassait l'attribut onclick de l'ancienne version.
  const attribut = client.echapper("Définition d'ensemble");
  assert.ok(!attribut.includes("'"), "l'apostrophe doit être encodée");
  assert.strictEqual(attribut, 'Définition d&#39;ensemble');
});

// =====================================================================
//  Tri
// =====================================================================
test('comparer : tri numérique sur des pourcentages affichés', () => {
  client.etat.tri = { index: 0, asc: true };
  const lignes = [['100%'], ['9%'], ['50%']].sort(client.comparer);
  assert.deepStrictEqual(lignes.map(l => l[0]), ['9%', '50%', '100%']);
});

test('comparer : tri alphabétique insensible aux accents', () => {
  client.etat.tri = { index: 0, asc: true };
  const lignes = [['Zèbre'], ['Élan'], ['Abeille']].sort(client.comparer);
  assert.deepStrictEqual(lignes.map(l => l[0]), ['Abeille', 'Élan', 'Zèbre']);
});

test('comparer : les cellules vides restent en bas dans les deux sens', () => {
  client.etat.tri = { index: 0, asc: true };
  assert.deepStrictEqual([['B'], [''], ['A']].sort(client.comparer).map(l => l[0]), ['A', 'B', '']);
  client.etat.tri = { index: 0, asc: false };
  assert.deepStrictEqual([['B'], [''], ['A']].sort(client.comparer).map(l => l[0]), ['B', 'A', '']);
});

// =====================================================================
//  Réordonnancement des colonnes
// =====================================================================
test('reordonner : déplacement vers la droite (bug corrigé)', () => {
  // 0 déposé sur 2 doit donner [1, 2, 0, 3] — l'ancien calcul donnait [1, 0, 2, 3].
  assert.deepStrictEqual(client.reordonner([0, 1, 2, 3], 0, 2), [1, 2, 0, 3]);
});

test('reordonner : déplacement vers la gauche', () => {
  assert.deepStrictEqual(client.reordonner([0, 1, 2, 3], 3, 1), [0, 3, 1, 2]);
});

test('reordonner : cas dégénérés', () => {
  const liste = [0, 1, 2];
  assert.strictEqual(client.reordonner(liste, 1, 1), liste);
  assert.strictEqual(client.reordonner(liste, 9, 1), liste);
  assert.deepStrictEqual(liste, [0, 1, 2], 'la liste source ne doit pas être mutée');
});

// =====================================================================
//  Agrégation pour les graphiques
// =====================================================================
test('agreger : les périodes datées sont triées chronologiquement, pas par fréquence', () => {
  // Régression : l'ancien code prenait le top-N par fréquence AVANT de trier.
  client.etat.entetes = ['Date création'];
  client.etat.lignesFiltrees = [
    ['2026-03-01'], ['2026-03-02'], ['2026-03-03'],
    ['2026-01-15'],
    ['2026-02-10'], ['2026-02-11']
  ];
  const { entrees, estDate } = client.agreger(0);
  assert.strictEqual(estDate, true);
  memeStructure(entrees, [['2026-01', 1], ['2026-02', 2], ['2026-03', 3]]);
});

test('agreger : dates au format jour/mois/année', () => {
  client.etat.entetes = ['Date de livraison'];
  client.etat.lignesFiltrees = [['12/03/2026'], ['28/03/2026'], ['05/04/2026']];
  const { entrees } = client.agreger(0);
  memeStructure(entrees, [['2026-03', 2], ['2026-04', 1]]);
});

test('agreger : regroupe la traîne dans « Autres »', () => {
  client.etat.entetes = ['ECP'];
  client.etat.lignesFiltrees = [];
  for (let i = 0; i < 20; i++) {
    for (let n = 0; n <= i; n++) client.etat.lignesFiltrees.push(['ECP-' + i]);
  }
  const { entrees } = client.agreger(0);
  assert.strictEqual(entrees.length, 16, '15 catégories + 1 ligne « Autres »');
  assert.match(entrees[15][0], /^Autres \(5 valeurs\)$/);
  const totalAutres = [0, 1, 2, 3, 4].reduce((s, i) => s + i + 1, 0);
  assert.strictEqual(entrees[15][1], totalAutres);
});

test('agreger : les cellules vides deviennent « Non renseigné »', () => {
  client.etat.entetes = ['Statut'];
  client.etat.lignesFiltrees = [['OK'], [''], ['   '], [null]];
  const { entrees } = client.agreger(0);
  const map = Object.fromEntries(entrees);
  assert.strictEqual(map['Non renseigné'], 3);
  assert.strictEqual(map['OK'], 1);
});

// =====================================================================
//  Rapport
// =====================================================================
console.log(`\n${reussis} test(s) réussi(s), ${echecs.length} échec(s).`);
if (echecs.length) {
  echecs.forEach(e => console.error(`  ✗ ${e.nom}\n      ${e.message}`));
  process.exit(1);
}
console.log('Tous les tests passent.\n');
