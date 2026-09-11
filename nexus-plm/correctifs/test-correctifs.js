/**
 * Vérification du lot 1 : pour chaque bug, on exécute l'ANCIEN code et le
 * NOUVEAU sur la même entrée, et on vérifie que l'ancien échoue et que le
 * nouveau passe.  Lancement :  node test-correctifs.js
 */
const L = require('./lib-correctifs.js');

let ok = 0, ko = 0;
function verifie(titre, obtenu, attendu) {
  const a = JSON.stringify(obtenu), b = JSON.stringify(attendu);
  if (a === b) { ok++; console.log('  \x1b[32mOK\x1b[0m   ' + titre); }
  else { ko++; console.log('  \x1b[31mKO\x1b[0m   ' + titre + '\n         attendu ' + b + '\n         obtenu  ' + a); }
}
function section(t) { console.log('\n' + t); }

// ---------------------------------------------------------------- B1
section('B1 — catalogue : le clic ajoute le composant affiché');
const catalogue = [
  { Type: 'Bouton poussoir', 'Sous Type/Désignation': 'Push button', Norm: 'ECS 7251' },
  { Type: 'Switch',          'Sous Type/Désignation': 'Switch',      Norm: 'ASNE 0567' },
  { Type: 'Relais',          'Sous Type/Désignation': 'Relay',       Norm: 'ECS 0763' },
  { Type: 'Diode',           'Sous Type/Désignation': 'Diode',       Norm: 'ASNE 0239' }
];
// ancien : index dans la liste filtrée, relu dans la liste complète
const ancienFiltre = catalogue.filter(c => JSON.stringify(c).toLowerCase().includes('diode')).slice(0, 30);
verifie('ancien code : clic sur "Diode" ajoutait', catalogue[0].Type, 'Bouton poussoir');
// nouveau : index réel conservé
const nouveau = L.filtrerCatalogueData(catalogue, 'diode');
verifie('nouveau : 1 résultat affiché',           nouveau.affiches.length, 1);
verifie('nouveau : composant affiché',            nouveau.affiches[0].composant.Type, 'Diode');
verifie('nouveau : clic ajoute bien "Diode"',     catalogue[nouveau.affiches[0].indexReel].Type, 'Diode');
verifie('nouveau : total connu (pour "30 sur N")', nouveau.total, 1);
// le dernier élément du catalogue, cas le plus exposé au décalage
const n2 = L.filtrerCatalogueData(catalogue, 'relay');
verifie('nouveau : "Relais" (index 2) correct',   catalogue[n2.affiches[0].indexReel].Type, 'Relais');
verifie('formaterComposant',                      L.formaterComposant(catalogue[0]), 'Bouton poussoir | Push button (ECS 7251)');

// ---------------------------------------------------------------- B3
section('B3 — statut : "Invalidé" n\'est plus compté comme validé');
const cas = [
  ['Validé',      true,  'status-valide'],
  ['  validé  ',  true,  'status-valide'],
  ['Invalidé',    false, 'status-etude'],
  ['Non validé',  false, 'status-etude'],
  ['Obsolète',    false, 'status-obsolete'],
  ['En étude',    false, 'status-etude'],
  ['',            false, 'status-etude'],
  [undefined,     false, 'status-etude']
];
cas.forEach(([statut, attenduValide, attenduClasse]) => {
  verifie('estValide(' + JSON.stringify(statut) + ')',   L.estValide(statut),   attenduValide);
  verifie('classeStatut(' + JSON.stringify(statut) + ')', L.classeStatut(statut), attenduClasse);
});
verifie('ancien code comptait "Invalidé" comme validé',
        String('Invalidé').toLowerCase().includes('valid'), true);

// ---------------------------------------------------------------- B4
section('B4 — export CSV');
verifie('guillemets doublés',  L.champCsv('Entraxe 5" nominal'), '"Entraxe 5"" nominal"');
verifie('retours ligne aplatis', L.champCsv('a\nb'),             '"a / b"');
verifie('valeur vide',          L.champCsv(undefined),           '""');
const csv = L.construireCsv([['Type', 'PN'], ['Repère #3', 'A"B']]);
verifie('BOM UTF-8 présent',    csv.charCodeAt(0),               0xFEFF);
verifie('le # est conservé',    csv.includes('Repère #3'),       true);
verifie('contenu complet',      csv.slice(1), '"Type";"PN"\r\n"Repère #3";"A""B"');
const boite = { 'PN Global': 'X', nomenclature: [{ Type: 'Harnais', 'PN du type': 'P1', 'Composant STD': 'c1\nc2', 'Masse (g)': '126.5', DAL: 'A', HL: 'A' }] };
verifie('ligne BOM complète',   L.lignesBomPourBoite(boite)[1], ['Harnais', 'P1', 'c1\nc2', '126.5', 'A', 'A']);
// preuve que l'ancien code perdait les données après un '#'
const ancienHref = encodeURI('data:text/csv;charset=utf-8,"Repère #3","suite"');
verifie('ancien code : tout est perdu après le #',
        ancienHref.split('#')[1], '3%22,%22suite%22');

// ---------------------------------------------------------------- B5
section('B5 — compteurs d\'onglets cohérents');
const boites = [
  { Fonction: 'APU', 'PN Global': '332P20001', nomenclature: [] },
  { Fonction: 'APU', 'PN Global': '332P20002', nomenclature: [] },
  { Fonction: 'NAV', 'PN Global': '999X1',     nomenclature: [] }
];
const r = L.calculerAffichage(boites, '332p2', 'Toutes', null);
verifie('compteur "Toutes" = nb réellement visible', r.visibles.length, 2);
verifie('somme des onglets = compteur "Toutes"',
        [...r.parFonction.values()].reduce((s, v) => s + v.length, 0), r.visibles.length);
verifie('cartes affichées',                         r.aAfficher.length, 2);
// ancien code : "Toutes" affichait la liste NON filtrée
verifie('ancien code : "Toutes" annonçait', boites.length, 3);
// onglet orphelin
const r2 = L.calculerAffichage(boites, '999', 'APU', null);
verifie('onglet orphelin -> retombe sur Toutes',    r2.ongletEffectif, 'Toutes');
verifie('et les résultats restent visibles',        r2.aAfficher.length, 1);
// onglet toujours valide
const r3 = L.calculerAffichage(boites, '', 'APU', null);
verifie('onglet valide conservé',                   r3.ongletEffectif, 'APU');
verifie('contenu de l\'onglet',                     r3.aAfficher.length, 2);
// recherche par composants (boitesForcees) : pas de refiltrage
const r4 = L.calculerAffichage(boites, 'zzz', 'Toutes', [boites[0]]);
verifie('boitesForcees non refiltrées',             r4.aAfficher.length, 1);

// ---------------------------------------------------------------- B6
section('B6 — plus de "undefined" affiché');
verifie('ancien code affichait', String(undefined).replace(/\n/g, ', ') || '-', 'undefined');
verifie('txt(undefined)', L.txt(undefined), '-');
verifie('txt(null)',      L.txt(null),      '-');
verifie('txt("")',        L.txt(''),        '-');
verifie('txt("   ")',     L.txt('   '),     '-');
verifie('txt("H160")',    L.txt('H160'),    'H160');
verifie('txt(0) conservé', L.txt(0),        '0');
verifie('valeursMulti("H160\\nH225")', L.valeursMulti('H160\nH225'), ['H160', 'H225']);
verifie('valeursMulti(undefined)',     L.valeursMulti(undefined),    []);

// ---------------------------------------------------------------- KPI
section('KPI (dépend de B3)');
const bs = [
  { 'PN Global': 'A', Statut: 'Validé',   nomenclature: [{ 'PN du type': 'A.1' }] },
  { 'PN Global': 'B', Statut: 'Invalidé', nomenclature: [{ 'PN du type': 'A.1' }] },
  { 'PN Global': 'C', Statut: 'En étude', nomenclature: [] }
];
const kpi = L.calculerKpi(bs);
verifie('1 seule boîte validée sur 3', kpi.nbValides,   1);
verifie('pourcentage',                 kpi.pctValides,  33);
verifie('références dédupliquées',     kpi.refsUniques, 4);

console.log('\n' + (ko === 0 ? '\x1b[32m' : '\x1b[31m') + ok + ' OK, ' + ko + ' KO\x1b[0m');
process.exit(ko === 0 ? 0 : 1);
