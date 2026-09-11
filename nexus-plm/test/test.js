/**
 * NEXUS PLM — suite de tests.   Lancement :  node test/test.js
 * Charge les fichiers réellement livrés (voir harness.js).
 */
const H = require('./harness.js');
const fs = require('fs');
const path = require('path');

const C = H.chargerClient([
  'client/Dom.html', 'client/Store.html', 'client/Compare.html',
  'client/ViewGrid.html', 'client/ViewFiche.html', 'client/ViewCompare.html'
]);

let ok = 0, ko = 0;
const V = '\x1b[32m', R = '\x1b[31m', G = '\x1b[90m', Z = '\x1b[0m';

function eq(titre, obtenu, attendu) {
  const a = JSON.stringify(obtenu), b = JSON.stringify(attendu);
  if (a === b) { ok++; console.log('  ' + V + 'OK' + Z + '   ' + titre); }
  else { ko++; console.log('  ' + R + 'KO' + Z + '   ' + titre +
                           '\n         attendu ' + b + '\n         obtenu  ' + a); }
}
function vrai(titre, condition) { eq(titre, !!condition, true); }
function faux(titre, condition) { eq(titre, !!condition, false); }
function titre(t) { console.log('\n' + t); }

function deséchapper(s) {
  return String(s).replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
function attribut(html, nom) {
  const m = html.match(new RegExp(nom + '="([^"]*)"'));
  return m ? deséchapper(m[1]) : null;
}

// =====================================================================
titre('F1 — échappement : les données ne rentrent plus dans du code');
// =====================================================================
const PIEGE = '332"P<script>alert(1)</script>\'A & B';

eq('esc() traite les 5 caractères', C.esc('<>&"\''),
   '&lt;&gt;&amp;&quot;&#39;');
eq('esc(undefined)', C.esc(undefined), '');
eq('esc() est idempotent sur du texte sain', C.esc('Harnais 332'), 'Harnais 332');

C.chargerDonnees({
  boites: [{ 'PN Global': PIEGE, 'Fonction': 'APU', 'Statut': 'Validé',
             'Porteur': 'H160', 'DS/VCI Associé': 'D1', 'Image': '', 'Commentaires libres': '' }],
  nomenclature: [{ 'ID_Ligne': 'L-1', 'PN Global': PIEGE, 'Type': 'Harnais',
                   'PN du type': 'P"1', 'Composant STD': 'Vis 5" | ISO' }],
  headersBoites: ['Fonction', 'PN Global', 'DS/VCI Associé', 'Porteur', 'Statut', 'Image', 'Commentaires libres'],
  headersNom: ['ID_Ligne', 'PN Global', 'Type', 'PN du type', 'Composant STD'],
  config: { multiBoite: ['Porteur'], multiNom: [], lectureSeuleNom: ['ID_Ligne', 'PN Global'],
            statuts: ['En étude', 'Validé', 'Obsolète'], colonneStd: 'Composant STD' }
});

const carte = C.carteHtml(C.Store.boites[0]);
faux('la carte ne contient aucun <script> injecté', /<script>alert/.test(carte));
vrai('le < est échappé', carte.indexOf('&lt;script&gt;') !== -1);
eq('data-pn survit intact au passage HTML', attribut(carte, 'data-pn'), PIEGE);
vrai('aucun onclick en ligne dans la carte', carte.indexOf('onclick=') === -1);

C.Store.pnCourant = PIEGE;
C.Store.enEditionBoite = true;
const fiche = C.ficheHtml(C.Store.boites[0]);
faux('la fiche ne contient aucun <script> injecté', /<script>alert/.test(fiche));
// Le cas qui cassait tout : un guillemet dans un value="" tronquait la saisie.
const champPn = fiche.match(/<input[^>]*data-champ="PN Global"[^>]*>/);
vrai('le champ PN Global est rendu', !!champPn);
eq('la valeur du champ survit au guillemet', attribut(champPn[0], 'value'), PIEGE);
eq('data-champ correct', attribut(champPn[0], 'data-champ'), 'PN Global');
C.Store.enEditionBoite = false;

const ficheLecture = C.ficheHtml(C.Store.boites[0]);
vrai('la puce STD avec guillemet est échappée', ficheLecture.indexOf('Vis 5&quot; | ISO') !== -1);
eq('data-valeur de la puce survit',
   attribut(ficheLecture.match(/data-action="supprimer-std"[^>]*>/)[0], 'data-valeur'),
   'Vis 5" | ISO');
faux('aucun onclick en ligne dans la fiche', ficheLecture.indexOf('onclick=') !== -1);

// =====================================================================
titre('B1 — catalogue : le clic ajoute le composant affiché');
// =====================================================================
C.Store.catalogue = [
  { Type: 'Bouton poussoir', 'Sous Type/Désignation': 'Push button', Norm: 'ECS 7251' },
  { Type: 'Switch', 'Sous Type/Désignation': 'Switch', Norm: 'ASNE 0567' },
  { Type: 'Relais', 'Sous Type/Désignation': 'Relay', Norm: 'ECS 0763' },
  { Type: 'Diode', 'Sous Type/Désignation': 'Diode', Norm: 'ASNE 0239' }
];
const fc = C.filtrerCatalogue('diode');
eq('1 résultat', fc.affiches.length, 1);
eq('composant affiché', fc.affiches[0].composant.Type, 'Diode');
eq("l'index pointe sur le bon composant", C.Store.catalogue[fc.affiches[0].index].Type, 'Diode');
eq('total connu pour le compteur', fc.total, 1);
const fc2 = C.filtrerCatalogue('relay');
eq('dernier cas exposé au décalage', C.Store.catalogue[fc2.affiches[0].index].Type, 'Relais');
eq('formaterComposant', C.formaterComposant(C.Store.catalogue[0]),
   'Bouton poussoir | Push button (ECS 7251)');
eq('recherche vide = tout', C.filtrerCatalogue('').total, 4);

// =====================================================================
titre('B3 — statut : « Invalidé » n\'est plus validé');
// =====================================================================
[['Validé', true, 'status-valide'], ['  validé ', true, 'status-valide'],
 ['Invalidé', false, 'status-etude'], ['Non validé', false, 'status-etude'],
 ['Obsolète', false, 'status-obsolete'], ['En étude', false, 'status-etude'],
 ['', false, 'status-etude'], [undefined, false, 'status-etude']
].forEach(function (c) {
  eq('estValide(' + JSON.stringify(c[0]) + ')', C.estValide(c[0]), c[1]);
  eq('classeStatut(' + JSON.stringify(c[0]) + ')', C.classeStatut(c[0]), c[2]);
});
eq('badge vide si statut vide', C.badgeStatutHtml(''), '');

// =====================================================================
titre('B4 — export CSV');
// =====================================================================
eq('guillemets doublés', C.champCsv('Entraxe 5" nominal'), '"Entraxe 5"" nominal"');
eq('retours ligne aplatis', C.champCsv('a\nb'), '"a / b"');
eq('valeur absente', C.champCsv(undefined), '""');
const csv = C.construireCsv([['Type', 'PN'], ['Repère #3', 'A"B']]);
eq('BOM UTF-8', csv.charCodeAt(0), 0xFEFF);
vrai('le # est conservé', csv.indexOf('Repère #3') !== -1);
eq('contenu', csv.slice(1), '"Type";"PN"\r\n"Repère #3";"A""B"');

// =====================================================================
titre('B5 — compteurs d\'onglets cohérents');
// =====================================================================
function jeu() {
  C.chargerDonnees({
    boites: [
      { 'PN Global': '332P20001', 'Fonction': 'APU', 'Statut': 'Validé' },
      { 'PN Global': '332P20002', 'Fonction': 'APU', 'Statut': 'Invalidé' },
      { 'PN Global': '999X1', 'Fonction': 'NAV', 'Statut': 'Validé' }
    ],
    nomenclature: [
      { 'ID_Ligne': 'L-1', 'PN Global': '332P20001', 'Type': 'Harnais',
        'PN du type': 'A.1', 'Composant STD': 'Vis (ISO 1)' },
      { 'ID_Ligne': 'L-2', 'PN Global': '999X1', 'Type': 'Harnais',
        'PN du type': 'A.1', 'Composant STD': 'Écrou (ISO 2)' }
    ],
    headersBoites: ['PN Global', 'Fonction', 'Statut'],
    headersNom: ['ID_Ligne', 'PN Global', 'Type', 'PN du type', 'Composant STD'],
    config: { multiBoite: [], multiNom: [], lectureSeuleNom: ['ID_Ligne', 'PN Global'],
              statuts: [], colonneStd: 'Composant STD' }
  });
  C.Store.recherche = ''; C.Store.ongletActif = 'Toutes'; C.Store.filtreComposants = [];
}
jeu();
C.Store.recherche = '332p2';
let vue = C.calculerVue();
eq('« Toutes » = nombre réellement visible', vue.visibles.length, 2);
eq('somme des onglets = « Toutes »',
   Array.from(vue.parFonction.values()).reduce(function (s, v) { return s + v.length; }, 0),
   vue.visibles.length);
eq('cartes affichées', vue.aAfficher.length, 2);
vrai('le compteur rendu affiche bien 2',
     C.ongletsHtml(vue).indexOf('Toutes <span class="tab-count">2</span>') !== -1);

jeu();
C.Store.recherche = '999'; C.Store.ongletActif = 'APU';
vue = C.calculerVue();
eq('onglet orphelin -> Toutes', vue.onglet, 'Toutes');
eq('les résultats restent visibles', vue.aAfficher.length, 1);

jeu();
C.Store.ongletActif = 'APU';
vue = C.calculerVue();
eq('onglet valide conservé', vue.onglet, 'APU');
eq('contenu de l\'onglet', vue.aAfficher.length, 2);

// =====================================================================
titre('B6 — plus de « undefined »');
// =====================================================================
eq('ancien code produisait', String(undefined).replace(/\n/g, ', ') || '-', 'undefined');
[[undefined, '-'], [null, '-'], ['', '-'], ['   ', '-'], ['H160', 'H160'], [0, '0']]
  .forEach(function (c) { eq('txt(' + JSON.stringify(c[0]) + ')', C.txt(c[0]), c[1]); });
eq('valeursMulti multi-lignes', C.valeursMulti('H160\nH225'), ['H160', 'H225']);
eq('valeursMulti(undefined)', C.valeursMulti(undefined), []);
jeu();
vrai('carte sans Porteur affiche « - »',
     C.carteHtml(C.Store.boites[0]).indexOf('undefined') === -1);

// =====================================================================
titre('F5 — recherche : plus de faux positifs sur les noms de colonnes');
// =====================================================================
jeu();
const b0 = C.Store.boites[0];
faux('« rowindex » ne matche plus', C.correspond(b0, 'rowindex'));
faux('« commentaires » ne matche plus', C.correspond(b0, 'commentaires'));
faux('« pn global » (nom de colonne) ne matche plus', C.correspond(b0, 'pn global'));
vrai('une vraie valeur matche', C.correspond(b0, '332P20001'));
vrai('la recherche descend dans la nomenclature', C.correspond(b0, 'harnais'));
vrai('plusieurs mots dans le désordre', C.correspond(b0, 'harnais 332p20001'));
faux('un mot absent invalide', C.correspond(b0, 'harnais zzzz'));
vrai('requête vide = tout', C.correspond(b0, ''));

// =====================================================================
titre('F4 — comparateur : les deux bugs de pondération');
// =====================================================================
function boite(pn, fonction, qualif, lignes) {
  return { 'PN Global': pn, 'Fonction': fonction, 'Niveau de qualification': qualif,
           nomenclature: lignes || [] };
}
function ligne(type, std) {
  return { 'ID_Ligne': 'x', 'Type': type, 'Composant STD': (std || []).join('\n') };
}
C.Store.config.colonneStd = 'Composant STD';
C.Store.config.multiNom = ['Qualification Vibration'];

// Bug 1 : source sans composant STD, cible qui en a.
const sansStd = boite('A', 'APU', 'Q1', [ligne('Harnais', [])]);
const avecStd = boite('B', 'APU', 'Q1', [ligne('Harnais', ['Vis', 'Écrou'])]);
const r1 = C.comparerBoites(sansStd, avecStd);
const critStd = r1.criteres.find(function (c) { return c.cle === 'composants'; });
eq('le critère composants est hors calcul', critStd.etat, 'indisponible');
eq('deux boîtes par ailleurs identiques -> 100 %', r1.score, 100);
vrai('mais la couverture le signale', r1.couverture < 100);
eq('les composants en trop sont tout de même restitués', critStd.ensembles.enPlus, ['Vis', 'Écrou']);

// Bug 2 : pénalité silencieuse sur une masse absente côté cible.
const nomA = { 'ID_Ligne': '1', 'Type': 'Harnais', 'Montage': 'Rack', 'Masse (g)': '500',
               'DAL': 'A', 'HL': 'A', 'Composant STD': '' };
const nomB = { 'ID_Ligne': '2', 'Type': 'Harnais', 'Montage': 'Rack', 'Masse (g)': '',
               'DAL': 'A', 'HL': 'A', 'Composant STD': '' };
const r2 = C.comparerSousEnsembles(nomA, nomB);
const critMasse = r2.criteres.find(function (c) { return c.cle === 'masse'; });
eq('masse absente = hors calcul', critMasse.etat, 'indisponible');
vrai('et la raison est restituée', /non renseigné/.test(critMasse.message));
eq('le reste étant identique, score 100 %', r2.score, 100);
vrai('la ligne apparaît bien dans le rendu',
     C.critereHtml(critMasse).indexOf('hors calcul') !== -1);

// Comportements nominaux
const r3 = C.comparerBoites(
  boite('A', 'APU', 'Q1', [ligne('Harnais', ['Vis', 'Écrou'])]),
  boite('B', 'NAV', 'Q2', [ligne('Structure', ['Rivet'])]));
vrai('tout diffère -> score bas', r3.score < 20);
eq('couverture complète', r3.couverture, 100);

const r4 = C.comparerBoites(
  boite('A', 'APU', 'Q1', [ligne('Harnais', ['Vis', 'Écrou'])]),
  boite('B', 'APU', 'Q1', [ligne('Harnais', ['Vis', 'Écrou'])]));
eq('identiques -> 100 %', r4.score, 100);

const r5 = C.comparerBoites(
  boite('A', 'APU', 'Q1', [ligne('Harnais', ['Vis', 'Écrou'])]),
  boite('B', 'APU', 'Q1', [ligne('Harnais', ['Vis'])]));
const c5 = r5.criteres.find(function (c) { return c.cle === 'composants'; });
eq('50 % des composants en commun', c5.obtenu, 25);
eq('manquant identifié', c5.ensembles.manquants, ['Écrou']);
vrai('score intermédiaire', r5.score > 40 && r5.score < 100);

// Masse à ±5 %
eq('masse à 3 % = identique',
   C.comparerSousEnsembles(Object.assign({}, nomA, { 'Masse (g)': '500' }),
                           Object.assign({}, nomA, { 'Masse (g)': '515' }))
    .criteres.find(function (c) { return c.cle === 'masse'; }).etat, 'identique');
eq('masse à 20 % = différente',
   C.comparerSousEnsembles(Object.assign({}, nomA, { 'Masse (g)': '500' }),
                           Object.assign({}, nomA, { 'Masse (g)': '600' }))
    .criteres.find(function (c) { return c.cle === 'masse'; }).etat, 'different');

// =====================================================================
titre('Store — mises à jour ciblées');
// =====================================================================
jeu();
eq('rattachement parent/enfant', C.Store.boites[0].nomenclature.length, 1);
eq('boite sans nomenclature', C.Store.boites[1].nomenclature.length, 0);

C.appliquerNom({ 'ID_Ligne': 'L-1', 'PN Global': '332P20001', 'Type': 'Harnais MODIFIÉ',
                 'PN du type': 'A.1', 'Composant STD': '' });
eq('ligne mise à jour en place', C.nomParId('L-1')['Type'], 'Harnais MODIFIÉ');
eq('pas de doublon créé', C.Store.nomenclature.length, 2);

C.retirerNom('L-1');
eq('ligne retirée', C.nomParId('L-1'), null);
eq('lien parent recalculé', C.Store.boites[0].nomenclature.length, 0);

jeu();
C.Store.pnCourant = '332P20001';
C.appliquerBoite({ 'PN Global': 'NOUVEAU-PN', 'Fonction': 'APU', 'Statut': 'Validé' }, '332P20001');
eq('renommage appliqué', C.boiteParPn('NOUVEAU-PN')['Fonction'], 'APU');
eq('ancienne clé absente', C.boiteParPn('332P20001'), null);
eq('clé étrangère suivie', C.nomParId('L-1')['PN Global'], 'NOUVEAU-PN');
eq('rattachement reconstruit', C.boiteParPn('NOUVEAU-PN').nomenclature.length, 1);
eq('sélection courante suivie', C.Store.pnCourant, 'NOUVEAU-PN');

jeu();
C.retirerBoite('332P20001');
eq('boîte retirée', C.Store.boites.length, 2);
eq('nomenclature en cascade', C.Store.nomenclature.length, 1);

// =====================================================================
titre('Filtre par composants embarqués');
// =====================================================================
jeu();
C.Store.filtreComposants = ['Vis'];
eq('une seule boîte contient « Vis »', C.calculerVue().visibles.length, 1);
C.Store.filtreComposants = ['Vis', 'Écrou'];
eq('aucune boîte ne contient les deux', C.calculerVue().visibles.length, 0);
C.Store.filtreComposants = [];
eq('filtre vide = tout', C.calculerVue().visibles.length, 3);

// =====================================================================
titre('Indicateurs');
// =====================================================================
jeu();
const kpi = C.calculerKpi(C.Store.boites);
eq('« Invalidé » n\'est pas compté', kpi.nbValides, 2);
eq('pourcentage', kpi.pctValides, 67);
eq('références dédupliquées (3 PN + A.1)', kpi.refsUniques, 4);
eq('KPI sur liste vide', C.calculerKpi([]).pctValides, 0);

// =====================================================================
titre('Miniatures Drive');
// =====================================================================
eq('lien /d/<id>',
   C.urlMiniature('https://drive.google.com/file/d/1A2B3C4D5E6F7G8H9I0J1K2L/view'),
   'https://drive.google.com/thumbnail?id=1A2B3C4D5E6F7G8H9I0J1K2L&sz=w1000');
eq('lien ?id=<id>',
   C.urlMiniature('https://drive.google.com/open?id=1A2B3C4D5E6F7G8H9I0J1K2L'),
   'https://drive.google.com/thumbnail?id=1A2B3C4D5E6F7G8H9I0J1K2L&sz=w1000');
eq('URL non-Drive inchangée', C.urlMiniature('https://exemple.fr/a.png'), 'https://exemple.fr/a.png');
eq('valeur vide', C.urlMiniature(''), '');
eq('texte quelconque', C.urlMiniature('pas une url'), '');
eq('imageHtml ne rend rien sans URL', C.imageHtml('', 'x'), '');

// =====================================================================
titre('Serveur — syntaxe et cohérence');
// =====================================================================
['server/Config.gs', 'server/Repository.gs', 'server/Api.gs', 'server/Setup.gs']
  .forEach(function (f) {
    try { H.verifierSyntaxeServeur(f); ok++; console.log('  ' + V + 'OK' + Z + '   syntaxe ' + f); }
    catch (e) { ko++; console.log('  ' + R + 'KO' + Z + '   syntaxe ' + f + ' : ' + e.message); }
  });

const srcSetup = fs.readFileSync(path.join(H.RACINE, 'server/Setup.gs'), 'utf8');
const srcApi = fs.readFileSync(path.join(H.RACINE, 'server/Api.gs'), 'utf8');
const srcConfig = fs.readFileSync(path.join(H.RACINE, 'server/Config.gs'), 'utf8');
const srcIndex = fs.readFileSync(path.join(H.RACINE, 'Index.html'), 'utf8');

// Les lignes de démo doivent avoir autant de colonnes que d'en-têtes.
const nbEnTetesNom = (srcConfig.match(/NOMENCLATURE: \[([\s\S]*?)\]/)[1].match(/'/g).length) / 2;
const lignesDemo = srcSetup.match(/\n    \['332P20001',[\s\S]*?\n  \]\.map/);
const premiere = lignesDemo[0].split('\n')[1];
const nbColDemo = (premiere.match(/'/g).length) / 2 + 1;   // +1 : ID_Ligne ajouté par .map
eq('jeu de démo : colonnes = en-têtes', nbColDemo, nbEnTetesNom);

vrai('ALLOWALL remplacé par DEFAULT', srcApi.indexOf('XFrameOptionsMode.DEFAULT') !== -1);
faux('plus aucun ALLOWALL appelé', /XFrameOptionsMode\.ALLOWALL/.test(srcApi));
faux("l'URL du catalogue n'est plus en dur", /docs\.google\.com\/spreadsheets/.test(srcConfig));
vrai('URL du catalogue en Script Property', srcConfig.indexOf('URL_CATALOGUE') !== -1);
vrai('verrou sur les mutations', srcApi.indexOf('avecVerrou_') !== -1);
vrai('journalisation', srcApi.indexOf('journaliser_') !== -1);
eq('écriture par lot : aucun setValue() en boucle',
   (fs.readFileSync(path.join(H.RACINE, 'server/Repository.gs'), 'utf8')
      .match(/forEach[\s\S]{0,200}?\.setValue\(/g) || []).length, 0);

// Le client ne doit plus appeler google.script.run hors de Api.html.
['Dom', 'Store', 'Compare', 'ViewGrid', 'ViewFiche', 'ViewCompare', 'Main'].forEach(function (f) {
  const s = fs.readFileSync(path.join(H.RACINE, 'client/' + f + '.html'), 'utf8');
  faux('google.script.run absent de ' + f + '.html', s.indexOf('google.script.run') !== -1);
});
const srcApiClient = fs.readFileSync(path.join(H.RACINE, 'client/Api.html'), 'utf8');
vrai('withFailureHandler présent', srcApiClient.indexOf('withFailureHandler') !== -1);
eq('autant de withFailureHandler que de withSuccessHandler (appels réels)',
   (srcApiClient.match(/\.withFailureHandler\(/g) || []).length,
   (srcApiClient.match(/\.withSuccessHandler\(/g) || []).length);

// Plus aucun gestionnaire en ligne dans le HTML livré.
faux('aucun onclick= dans Index.html', /onclick=/.test(srcIndex));
['ViewGrid', 'ViewFiche', 'ViewCompare', 'Main'].forEach(function (f) {
  const s = fs.readFileSync(path.join(H.RACINE, 'client/' + f + '.html'), 'utf8');
  faux('aucun onclick= généré par ' + f + '.html', /onclick=/.test(s));
});
vrai('.max-width-xl est définie',
     fs.readFileSync(path.join(H.RACINE, 'client/Styles.html'), 'utf8')
       .indexOf('.max-width-xl') !== -1);

// Toute action référencée dans les vues doit exister dans Main.html
const srcMain = fs.readFileSync(path.join(H.RACINE, 'client/Main.html'), 'utf8');
const declarees = new Set();
(srcMain.match(/^\s*'([a-z-]+)':\s*function/gm) || []).forEach(function (l) {
  declarees.add(l.match(/'([a-z-]+)'/)[1]);
});
const utilisees = new Set();
['ViewGrid', 'ViewFiche', 'ViewCompare'].forEach(function (f) {
  const s = fs.readFileSync(path.join(H.RACINE, 'client/' + f + '.html'), 'utf8');
  (s.match(/action:\s*'([a-z-]+)'/g) || []).forEach(function (m) {
    utilisees.add(m.match(/'([a-z-]+)'/)[1]);
  });
});
(srcIndex.match(/data-action="([a-z-]+)"/g) || []).forEach(function (m) {
  utilisees.add(m.match(/"([a-z-]+)"/)[1]);
});
const orphelines = Array.from(utilisees).filter(function (a) { return !declarees.has(a); });
eq('aucune action référencée sans implémentation', orphelines, []);
vrai('au moins 20 actions déclarées', declarees.size >= 20);

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z +
            G + '  (' + declarees.size + ' actions, ' + utilisees.size + ' référencées)' + Z);
process.exit(ko === 0 ? 0 : 1);
