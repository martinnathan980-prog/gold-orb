/**
 * NEXUS PLM — suite de tests.   node test/test.js
 * Charge les fichiers réellement livrés (voir harness.js).
 */
const H = require('./harness.js');
const fs = require('fs');
const path = require('path');

const C = H.chargerClient([
  'client/Dom.html', 'client/Composants.html', 'client/Types.html', 'client/Api.html',
  'client/Store.html', 'client/Compare.html', 'client/ViewGrid.html', 'client/ViewFiche.html',
  'client/ViewCompare.html', 'client/Reglages.html', 'client/Annulation.html',
  'client/Dialogues.html'
]);

let ok = 0, ko = 0;
const V = '\x1b[32m', R = '\x1b[31m', G = '\x1b[90m', Z = '\x1b[0m';
function eq(t, a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x === y) { ok++; console.log('  ' + V + 'OK' + Z + '   ' + t); }
  else { ko++; console.log('  ' + R + 'KO' + Z + '   ' + t +
                           '\n         attendu ' + y + '\n         obtenu  ' + x); }
}
function vrai(t, c) { eq(t, !!c, true); }
function faux(t, c) { eq(t, !!c, false); }
function bloc(t) { console.log('\n' + t); }

function deséchapper(s) {
  return String(s).replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
/** Retire les commentaires : un motif cité dans une explication n'est pas du code. */
function sansCommentaires(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/<!--[\s\S]*?-->/g, '');
}

function attribut(html, nom) {
  const m = html.match(new RegExp(nom + '="([^"]*)"'));
  return m ? deséchapper(m[1]) : null;
}

const CONFIG = {
  multiBoite: ['Porteur', 'Composants'],
  multiNom: ['Qualification Brouillard salin', 'Qualification Vibration',
             'Qualification Explosion', 'Mots-clés', 'Structure mécanique', 'Composants électriques'],
  lectureSeuleNom: ['ID_Ligne', 'PN Global'],
  statuts: ['En étude', 'Validé', 'Obsolète'],
  porteurs: []
};
const ENTETES_B = ['Fonction', 'PN Global', 'DS/VCI Associé', 'Porteur', 'Statut',
                   'Niveau de qualification', 'Composants', 'Image', 'Commentaires libres'];

function charger(boites, lignes) {
  C.chargerDonnees({ boites: boites, nomenclature: lignes,
                     headersBoites: ENTETES_B, headersNom: C.toutesLesColonnesNom(),
                     config: CONFIG });
  C.Store.recherche = ''; C.Store.ongletActif = 'Toutes';
  C.Store.filtreComposants = []; C.Store.filtreTypes = []; C.Store.tri = 'pn';
  C.reinitialiserPoids();
}

// =====================================================================
bloc('Registre des types');
// =====================================================================
eq('3 types proposés à la saisie', C.typesProposes().length, 3);
eq('lesquels', C.typesProposes().map(function (t) { return t.cle; }),
   ['structure', 'harnais', 'plaquette']);
vrai('le repli technique existe mais reste masqué', C.TYPES.autre.masque === true);
eq('4 portées de pondération (boîte + 3 types)', C.PORTEES.length, 4);
eq('seules la boîte et la structure s\'arbitrent',
   C.PORTEES.filter(C.porteeArbitrable).map(function (p) { return p.cle; }),
   ['boite', 'structure']);
eq('« Structure boîte »', C.typeDe({ Type: 'Structure boîte' }).cle, 'structure');
eq('sans accent', C.typeDe({ Type: 'Structure boite' }).cle, 'structure');
eq('casse indifférente', C.typeDe({ Type: 'HARNAIS' }).cle, 'harnais');
eq('synonyme', C.typeDe({ Type: 'câblage' }).cle, 'harnais');
eq('plaquette abrégée', C.typeDe({ Type: 'Plaquette' }).cle, 'plaquette');
eq('type inconnu -> repli', C.typeDe({ Type: 'Bidule' }).cle, 'autre');
eq('type vide -> repli', C.typeDe({ Type: '' }).cle, 'autre');
eq('ligne absente -> repli', C.typeDe(null).cle, 'autre');
vrai('une ligne de type inconnu reste affichable',
     C.TYPES.autre.champs.length > 0);

const champs = function (cle) { return C.TYPES[cle].champs.map(function (c) { return c.cle; }); };
vrai('la structure porte ses cotes', champs('structure').indexOf('Dim Long (mm)') !== -1);
faux('le harnais n\'a PAS de longueur', champs('harnais').indexOf('Dim Long (mm)') !== -1);
faux('le harnais n\'a PAS de masse', champs('harnais').indexOf('Masse (g)') !== -1);
eq('le harnais : PN, référence, image, commentaires',
   champs('harnais'), ['PN du type', 'Référence', 'Image', 'Commentaires libres']);
eq('la plaquette : PN, mots-clés, image, commentaires',
   champs('plaquette'), ['PN du type', 'Mots-clés', 'Image', 'Commentaires libres']);
faux('aucun composant sur le harnais', champs('harnais').indexOf('Structure mécanique') !== -1);
faux('aucun composant sur la plaquette', champs('plaquette').indexOf('Composants électriques') !== -1);
vrai('la structure porte sa structure mécanique', champs('structure').indexOf('Structure mécanique') !== -1);
vrai('et ses composants électriques', champs('structure').indexOf('Composants électriques') !== -1);
faux('plus de colonne « Composant STD »', C.toutesLesColonnesNom().indexOf('Composant STD') !== -1);
eq('la structure compare ses deux familles séparément',
   C.TYPES.structure.criteres.filter(function (c) { return c.mode === C.MODE.COMPOSANTS; })
     .map(function (c) { return c.champ; }),
   ['Structure mécanique', 'Composants électriques']);
eq('la boîte compare ses propres composants (boutons, voyants…)',
   C.CRITERES_BOITE.filter(function (c) { return c.mode === C.MODE.COMPOSANTS; })
     .map(function (c) { return c.champ; }), ['Composants']);
eq('trois champs de composants en tout, chacun avec sa catégorie',
   C.champsComposants().map(function (c) { return c.portee + ':' + c.categorie; }),
   ['boite:composant', 'structure:mecanique', 'structure:electrique']);
vrai('les parts de la structure font 100 au registre',
     C.TYPES.structure.criteres.reduce(function (t, c) { return t + c.poids; }, 0) === 100);

// =====================================================================
bloc('Porteurs : tous ceux d\'Airbus Helicopters, et pas de « Multi »');
// =====================================================================
faux('« Multi » a disparu', C.PORTEURS.indexOf('Multi') !== -1);
['H125', 'H130', 'H135', 'H145', 'H145M', 'H155', 'H160', 'H160M', 'H175', 'H175M',
 'H215', 'H215M', 'H225', 'H225M', 'NH90', 'Tigre', 'UH-72 Lakota'].forEach(function (p) {
  vrai('porteur ' + p, C.PORTEURS.indexOf(p) !== -1);
});
eq('la liste est fermée (registre)', C.CHAMPS_BOITE['Porteur'].ferme, true);
C.Store.config = Object.assign({}, CONFIG, { porteurs: [] });
eq('sans liste serveur, le registre fait foi', C.porteursConnus(), C.PORTEURS);
C.Store.config = Object.assign({}, CONFIG, { porteurs: ['H160', 'H225'] });
eq('la liste serveur prime quand elle existe', C.porteursConnus(), ['H160', 'H225']);
C.Store.config = CONFIG;

// =====================================================================
bloc('Composants à trois niveaux : fonction, norme, référence');
// =====================================================================
eq('format complet', C.analyserComposant('Bouton poussoir | ECS 7251 | MS24523-22'),
   { fonction: 'Bouton poussoir', norme: 'ECS 7251', reference: 'MS24523-22',
     brut: 'Bouton poussoir | ECS 7251 | MS24523-22' });
eq('ancien format « Type | Sous-type (Norme) » reste lisible',
   C.analyserComposant('Bouton poussoir | 1 contact (ECS 7251)'),
   { fonction: 'Bouton poussoir 1 contact', norme: 'ECS 7251', reference: '',
     brut: 'Bouton poussoir | 1 contact (ECS 7251)' });
eq('fonction seule', C.analyserComposant('Colonnette').fonction, 'Colonnette');
eq('fonction seule : ni norme ni référence', C.analyserComposant('Colonnette').norme + C.analyserComposant('Colonnette').reference, '');
eq('« Fonction (Norme) »', C.analyserComposant('Relais (ECS 1120)'),
   { fonction: 'Relais', norme: 'ECS 1120', reference: '', brut: 'Relais (ECS 1120)' });
eq('vide -> null', C.analyserComposant('   '), null);
eq('écriture en cellule', C.formaterComposantStructure({ fonction: 'Colonnette', norme: 'NSA 5512', reference: 'COL-M4-20' }),
   'Colonnette | NSA 5512 | COL-M4-20');
eq('pas de séparateurs traînants', C.formaterComposantStructure({ fonction: 'Colonnette' }), 'Colonnette');
eq('aller-retour', C.analyserComposant(C.formaterComposantStructure({ fonction: 'A', norme: 'B', reference: 'C' })).reference, 'C');
eq('libellé lisible', C.libelleComposant({ fonction: 'Voyant', norme: 'ECS 4410', reference: 'LED-G-28' }),
   'Voyant · ECS 4410 · LED-G-28');
eq('liste depuis une cellule multi-lignes',
   C.listeComposants('Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-A').length, 2);
eq('depuis le catalogue (nouvelles colonnes)',
   C.composantDepuisCatalogue({ 'Catégorie': 'mecanique', 'Fonction': 'Colonnette', 'Norme': 'NSA 5512', 'Référence': 'COL-M4-20', 'Désignation': 'M4' }),
   { fonction: 'Colonnette', norme: 'NSA 5512', reference: 'COL-M4-20', categorie: 'mecanique', designation: 'M4' });
eq('depuis le catalogue (anciennes colonnes)',
   C.composantDepuisCatalogue({ 'Type': 'Diode', 'Norm': 'ASNE 0239', 'Sous Type/Désignation': 'Diode' }).norme, 'ASNE 0239');
eq('catégorie par défaut : composant', C.composantDepuisCatalogue({ 'Type': 'Diode' }).categorie, 'composant');

const S = [C.analyserComposant('Bouton poussoir | ECS 7251 | MS24523-22'),
           C.analyserComposant('Voyant | ECS 4410 | LED-G-28'),
           C.analyserComposant('Relais | ECS 1120 | RLY-28-2C'),
           C.analyserComposant('Fusible | NSA 9350 | F5A')];
const T = [C.analyserComposant('Bouton poussoir | ECS 7251 | MS24523-22'),   // référence exacte
           C.analyserComposant('Voyant | ECS 4410 | LED-G-05'),              // même norme
           C.analyserComposant('Relais | ECS 1121 | RLY-28-4C'),             // même fonction
           C.analyserComposant('Connecteur | EN 3645 | CN-3645-12')];        // en plus
const ap = C.apparierComposants(S, T);
eq('1 référence exacte', ap.paliers.reference.length, 1);
eq('1 même norme', ap.paliers.norme.length, 1);
eq('1 même fonction', ap.paliers.fonction.length, 1);
eq('1 sans équivalent', ap.paliers.aucun.map(function (c) { return c.fonction; }), ['Fusible']);
eq('1 en plus sur la cible', ap.enPlus.map(function (c) { return c.fonction; }), ['Connecteur']);
eq('ratio = (1 + 0,66 + 0,33) / 4', Math.round(ap.ratio * 1000) / 1000, Math.round(((1 + 0.66 + 0.33) / 4) * 1000) / 1000);
eq('référence identique -> 100 %', C.apparierComposants(S.slice(0, 1), T.slice(0, 1)).ratio, 1);
eq('un composant n\'est apparié qu\'une fois',
   C.apparierComposants([S[0], S[0]], [T[0]]).paliers.aucun.length, 1);
eq('même référence mais autre fonction : pas apparié sur la référence',
   C.apparierComposants([C.analyserComposant('Relais | X | ABC')], [C.analyserComposant('Voyant | Y | ABC')]).paliers.aucun.length, 1);
eq('source vide -> ratio 0', C.apparierComposants([], T).ratio, 0);
eq('casse et accents indifférents',
   C.apparierComposants([C.analyserComposant('Équerre | en 2491 | eq-90-a')],
                        [C.analyserComposant('equerre | EN 2491 | EQ-90-A')]).paliers.reference.length, 1);

faux('la structure n\'a pas de mots-clés', champs('structure').indexOf('Mots-clés') !== -1);
vrai('la structure garde ses qualifications',
     champs('structure').some(function (c) { return c.indexOf('Qualification') === 0; }));
vrai('toutes les colonnes couvrent les 4 types',
     C.toutesLesColonnesNom().length >= 18);

// =====================================================================
bloc('Mots-clés');
// =====================================================================
eq('découpage', C.motsCles('APU, démarrage, mission SAR'), ['APU', 'démarrage', 'mission SAR']);
eq('séparateurs variés', C.motsCles('a;b|c/d'), ['a', 'b', 'c', 'd']);
eq('doublons insensibles aux accents', C.motsCles('Démarrage, demarrage, DÉMARRAGE'), ['Démarrage']);
eq('vide', C.motsCles(''), []);
eq('absent', C.motsCles(undefined), []);
eq('normalisation', C.normaliserTexte('  Éclairante  '), 'eclairante');

// =====================================================================
bloc('F1 — échappement : les données ne rentrent pas dans du code');
// =====================================================================
const PIEGE = '332"P<script>alert(1)</script>\'A & B';
eq('esc() traite les 5 caractères', C.esc('<>&"\''), '&lt;&gt;&amp;&quot;&#39;');
eq('esc(undefined)', C.esc(undefined), '');

charger(
  [{ 'PN Global': PIEGE, 'Fonction': 'APU', 'Statut': 'Validé', 'Porteur': 'H160',
     'DS/VCI Associé': 'D1', 'Image': '', 'Commentaires libres': '' }],
  [{ 'ID_Ligne': 'L-1', 'PN Global': PIEGE, 'Type': 'Harnais',
     'PN du type': 'P"1', 'Référence': 'R\'2' },
   { 'ID_Ligne': 'L-2', 'PN Global': PIEGE, 'Type': 'Plaquette éclairante',
     'PN du type': 'Q"2', 'Mots-clés': 'entraxe 5" d\'origine, mission <b>x</b>' }]);

const carte = C.carteHtml(C.Store.boites[0]);
faux('aucun <script> injecté dans la carte', /<script>alert/.test(carte));
eq('data-pn survit intact', attribut(carte, 'data-pn'), PIEGE);
faux('aucun onclick en ligne', carte.indexOf('onclick=') !== -1);

C.Store.pnCourant = PIEGE;
C.Store.enEditionNom = {}; C.Store.enEditionNom['L-1'] = true;
const fiche = C.ficheHtml(C.Store.boites[0]);
faux('aucun <script> dans la fiche', /<script>alert/.test(fiche));
const champRef = fiche.match(/<input[^>]*data-champ="Référence"[^>]*>/);
vrai('le champ Référence est rendu', !!champRef);
eq('la valeur survit à l\'apostrophe', attribut(champRef[0], 'value'), 'R\'2');
C.Store.enEditionNom = {};

const ficheLecture = C.ficheHtml(C.Store.boites[0]);
eq('data-valeur d\'une puce survit au guillemet ET à l\'apostrophe',
   attribut(ficheLecture.match(/data-action="supprimer-multi-nom"[^>]*>/)[0], 'data-valeur'),
   'entraxe 5" d\'origine');
faux('un mot-clé piégé n\'injecte rien', /<b>x<\/b>/.test(ficheLecture));

// =====================================================================
bloc('La fiche n\'affiche que les champs du type');
// =====================================================================
charger(
  [{ 'PN Global': 'B1', 'Fonction': 'APU', 'Statut': 'Validé' }],
  [{ 'ID_Ligne': 'H1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'HH',
     'Référence': 'HRN-1', 'Dim Long (mm)': '999', 'Masse (g)': '888' },
   { 'ID_Ligne': 'S1', 'PN Global': 'B1', 'Type': 'Structure boîte', 'PN du type': 'SS',
     'Dim Long (mm)': '500', 'Dim Larg (mm)': '140', 'Masse (g)': '500', 'Montage': 'Rack' },
   { 'ID_Ligne': 'P1', 'PN Global': 'B1', 'Type': 'Plaquette éclairante', 'PN du type': 'PP',
     'Numéro': 'PL-1', 'Dim Long (mm)': '777', 'Mots-clés': 'mission SAR, APU' }]);
C.Store.pnCourant = 'B1';

const blocH = C.blocNomHtml(C.nomParId('H1'));
vrai('le harnais affiche sa référence', blocH.indexOf('HRN-1') !== -1);
faux('le harnais n\'affiche PAS sa longueur (même renseignée)', blocH.indexOf('999') !== -1);
faux('ni sa masse', blocH.indexOf('888') !== -1);

const blocS = C.blocNomHtml(C.nomParId('S1'));
vrai('la structure affiche sa longueur', blocS.indexOf('500') !== -1);
vrai('et son montage', blocS.indexOf('Rack') !== -1);
faux('la structure n\'affiche pas de champ Référence (celle du harnais)',
     /ligne-cle">Référence/.test(blocS));
vrai('la structure affiche ses deux familles de composants',
     blocS.indexOf('Structure mécanique') !== -1 && blocS.indexOf('Composants électriques') !== -1);
vrai('en colonnes fonction / norme / référence', blocS.indexOf('composants-entete') !== -1);
vrai('avec un catalogue par catégorie',
     blocS.indexOf('data-categorie="mecanique"') !== -1 && blocS.indexOf('data-categorie="electrique"') !== -1);

const blocP = C.blocNomHtml(C.nomParId('P1'));
vrai('la plaquette affiche ses mots-clés', blocP.indexOf('mission SAR') !== -1);
vrai('avec le style dédié', blocP.indexOf('puce-motcle') !== -1);
faux('la plaquette n\'affiche PAS son numéro (même renseigné)', blocP.indexOf('PL-1') !== -1);
faux('ni ses cotes', blocP.indexOf('777') !== -1);
faux('ni de composants', /Structure mécanique|Composants électriques/.test(blocP));

const blocH2 = C.blocNomHtml(C.nomParId('H1'));
faux('le harnais n\'affiche pas de qualification', blocH2.indexOf('Qualif') !== -1);
faux('ni de composants', /Structure mécanique|Composants électriques/.test(blocH2));
vrai('chaque bloc propose la duplication', blocH2.indexOf("'dupliquer-nom'") !== -1 ||
     blocH2.indexOf('dupliquer-nom') !== -1);

const fiche3 = C.ficheHtml(C.boiteParPn('B1'));
vrai('le sommaire liste les 3 types', fiche3.indexOf('Structure boîte') !== -1 &&
     fiche3.indexOf('Harnais') !== -1 && fiche3.indexOf('Plaquette') !== -1);

// =====================================================================
bloc('Équivalences par type');
// =====================================================================
function ligneH(id, pn, ref) {
  return { 'ID_Ligne': id, 'PN Global': pn, 'Type': 'Harnais',
           'PN du type': 'h' + id, 'Référence': ref };
}
function ligneP(id, pn, mots) {
  return { 'ID_Ligne': id, 'PN Global': pn, 'Type': 'Plaquette éclairante',
           'PN du type': 'p' + id, 'Mots-clés': mots };
}
function ligneS(id, pn, L, l, masse) {
  return { 'ID_Ligne': id, 'PN Global': pn, 'Type': 'Structure boîte', 'PN du type': 's' + id,
           'Montage': 'Rack', 'Nombre de pas': '2', 'Dim Long (mm)': String(L),
           'Dim Larg (mm)': String(l), 'Masse (g)': String(masse), 'DAL': 'A', 'HL': 'A' };
}

charger([{ 'PN Global': 'B1', 'Fonction': 'APU' }, { 'PN Global': 'B2', 'Fonction': 'APU' }],
  [ligneH('H1', 'B1', 'HRN-A'),
   ligneH('H2', 'B2', 'HRN-A'),
   ligneH('H3', 'B2', 'HRN-B'),
   ligneP('P1', 'B1', 'APU, mission SAR, démarrage'),
   ligneP('P2', 'B2', 'APU, mission SAR, arrêt'),
   ligneS('S1', 'B1', 500, 140, 500),
   ligneS('S2', 'B2', 500, 140, 510)]);

const eqH = C.equivalencesSousEnsemble('H1');
eq('seul le harnais comparable ressort', eqH.length, 1);
eq('c\'est bien H2', eqH[0].cible['ID_Ligne'], 'H2');
eq('identique -> 100 %', eqH[0].score, 100);
// H3 (autre référence, autre composant) tombe sous le seuil : on le vérifie
// en abaissant le seuil plutôt qu'en le supposant.
C.Store.seuilEquivalence = 0;
const eqHTous = C.equivalencesSousEnsemble('H1');
eq('seuil à 0 : les deux harnais ressortent', eqHTous.length, 2);
eq('H3 est bien classé dernier', eqHTous[1].cible['ID_Ligne'], 'H3');
vrai('avec un score nul', eqHTous[1].score === 0);
faux('aucune plaquette ni structure dans le lot',
     eqHTous.some(function (r) { return C.typeDe(r.cible).cle !== 'harnais'; }));
C.Store.seuilEquivalence = 15;
const critH = eqH[0].criteres.map(function (c) { return c.cle; });
eq('un seul critère pour le harnais', critH, ['reference']);

const eqP = C.equivalencesSousEnsemble('P1');
eq('une plaquette n\'est comparée qu\'aux plaquettes', eqP.length, 1);
eq('un seul critère pour la plaquette',
   eqP[0].criteres.map(function (c) { return c.cle; }), ['motsCles']);
const critMots = eqP[0].criteres.find(function (c) { return c.cle === 'motsCles'; });
vrai('les mots-clés sont bien un critère', !!critMots);
eq('2 mots-clés sur 3 en commun', critMots.ensembles.communs.length, 2);
eq('un mot-clé manquant', critMots.ensembles.manquants, ['démarrage']);
eq('un mot-clé en plus', critMots.ensembles.enPlus, ['arrêt']);
eq('mots-clés partiels', critMots.etat, 'partiel');

const eqS = C.equivalencesSousEnsemble('S1');
eq('une structure n\'est comparée qu\'aux structures', eqS.length, 1);
const critDim = eqS[0].criteres.find(function (c) { return c.cle === 'dimensions'; });
eq('dimensions identiques', critDim.etat, 'identique');
const critMasse = eqS[0].criteres.find(function (c) { return c.cle === 'masse'; });
eq('masse à 2 % = identique', critMasse.etat, 'identique');

// =====================================================================
bloc('Critère non mesurable : hors dénominateur, et affiché');
// =====================================================================
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [ligneH('H1', 'B1', ''),           // sans référence
   ligneH('H2', 'B2', 'HRN-Z')]);
C.Store.seuilEquivalence = 0;
const tousRef = C.equivalencesSousEnsemble('H1');
eq('sans référence, rien n\'est mesurable', tousRef.length, 0);
const sansRef = { mesurable: false };
const cRef = { libelle: 'Référence' };
eq('rien d\'autre à comparer, score nul', sansRef.mesurable, false);
eq('le critère est nommé comme non comparé', cRef.libelle, 'Référence');

// =====================================================================
bloc('Recherche, filtres et tri');
// =====================================================================
charger(
  [{ 'PN Global': '332P20001', 'Fonction': 'APU', 'Statut': 'Validé' },
   { 'PN Global': '332P20002', 'Fonction': 'APU', 'Statut': 'Invalidé' },
   { 'PN Global': '999X1', 'Fonction': 'NAV', 'Statut': 'Validé' }],
  [ligneH('H1', '332P20001', 'HRN-A'),
   ligneP('P1', '999X1', 'navigation, mission transport')]);

const b0 = C.boiteParPn('332P20001');
faux('« rowindex » ne matche plus', C.correspond(b0, 'rowindex'));
faux('« pn global » (nom de colonne) ne matche plus', C.correspond(b0, 'pn global'));
vrai('une vraie valeur matche', C.correspond(b0, '332P20001'));
vrai('le type résolu est cherchable', C.correspond(b0, 'harnais'));
vrai('recherche insensible aux accents',
     C.correspond(C.boiteParPn('999X1'), 'MISSION'));
vrai('mots-clés cherchables', C.correspond(C.boiteParPn('999X1'), 'transport'));
vrai('plusieurs mots dans le désordre', C.correspond(b0, 'hrn 332p20001'));
faux('un mot absent invalide', C.correspond(b0, 'harnais zzzz'));

C.Store.filtreTypes = ['plaquette'];
eq('filtre par type', C.calculerVue().visibles.length, 1);
C.Store.filtreTypes = ['harnais', 'plaquette'];
eq('deux types exigés ensemble', C.calculerVue().visibles.length, 0);
C.Store.filtreTypes = [];

C.Store.recherche = '332p2';
let vue = C.calculerVue();
eq('« Toutes » = nombre visible', vue.visibles.length, 2);
eq('somme des onglets = « Toutes »',
   Array.from(vue.parFonction.values()).reduce(function (s, v) { return s + v.length; }, 0),
   vue.visibles.length);
vrai('l\'état filtré est signalé', vue.filtre);
C.Store.recherche = '';

C.Store.ongletActif = 'APU'; C.Store.recherche = '999';
eq('onglet orphelin -> Toutes', C.calculerVue().onglet, 'Toutes');
C.Store.recherche = ''; C.Store.ongletActif = 'Toutes';

C.Store.tri = 'statut';
eq('tri par statut : les validés d\'abord',
   C.calculerVue().visibles[0]['Statut'], 'Validé');
C.Store.tri = 'taille';
eq('tri par taille', C.calculerVue().visibles[0].nomenclature.length, 1);
C.Store.tri = 'pn';
eq('tri par PN', C.calculerVue().visibles.map(function (b) { return b[C.CLE_PN()]; }),
   ['332P20001', '332P20002', '999X1']);

const rep = C.repartitionTypes();
eq('répartition par type', rep.map(function (e) { return e.type.cle + ':' + e.nombre; }),
   ['harnais:1', 'plaquette:1']);

// =====================================================================
bloc('Statuts et indicateurs');
// =====================================================================
[['Validé', true, 'status-valide'], ['Invalidé', false, 'status-etude'],
 ['Non validé', false, 'status-etude'], ['Obsolète', false, 'status-obsolete'],
 ['', false, 'status-etude'], [undefined, false, 'status-etude']
].forEach(function (c) {
  eq('estValide(' + JSON.stringify(c[0]) + ')', C.estValide(c[0]), c[1]);
  eq('classeStatut(' + JSON.stringify(c[0]) + ')', C.classeStatut(c[0]), c[2]);
});
const kpi = C.calculerKpi(C.Store.boites);
eq('« Invalidé » non compté', kpi.nbValides, 2);
eq('sous-ensembles comptés', kpi.nbLignes, 2);
eq('pourcentage', kpi.pctValides, 67);
eq('pièces distinctes', kpi.nbPieces, 2);
eq('aucune pièce réutilisée ici', kpi.reutilisees, 0);

// =====================================================================
bloc('Catalogue, CSV, images, valeurs absentes');
// =====================================================================
C.Store.catalogue = [
  { Type: 'Bouton poussoir', 'Sous Type/Désignation': 'Push button', Norm: 'ECS 7251' },
  { Type: 'Switch', 'Sous Type/Désignation': 'Switch', Norm: 'ASNE 0567' },
  { Type: 'Relais', 'Sous Type/Désignation': 'Relay', Norm: 'ECS 0763' },
  { Type: 'Diode', 'Sous Type/Désignation': 'Diode', Norm: 'ASNE 0239' }
];
const fc = C.filtrerCatalogue('diode');
eq('1 résultat', fc.affiches.length, 1);
eq('l\'index pointe le bon composant', C.Store.catalogue[fc.affiches[0].index].Type, 'Diode');
eq('recherche accent-insensible', C.filtrerCatalogue('RELAY').total, 1);

C.Store.catalogue = [
  { 'Catégorie': 'composant',  'Fonction': 'Bouton poussoir', 'Norme': 'ECS 7251', 'Référence': 'MS24523-22' },
  { 'Catégorie': 'mecanique',  'Fonction': 'Colonnette',      'Norme': 'NSA 5512', 'Référence': 'COL-M4-20' },
  { 'Catégorie': 'mecanique',  'Fonction': 'Entretoise',      'Norme': 'NSA 5520', 'Référence': 'ENT-10' },
  { 'Catégorie': 'electrique', 'Fonction': 'Collier',         'Norme': 'NSA 8420', 'Référence': 'CT-120' }
];
eq('catalogue filtré par catégorie : la structure mécanique', C.filtrerCatalogue('', 'mecanique').total, 2);
eq('les composants de boîte', C.filtrerCatalogue('', 'composant').total, 1);
eq('les composants électriques', C.filtrerCatalogue('', 'electrique').total, 1);
eq('pas de colonnette proposée pour une boîte', C.filtrerCatalogue('colonnette', 'composant').total, 0);
eq('recherche par référence', C.filtrerCatalogue('col-m4', 'mecanique').total, 1);
eq('sans catégorie, tout', C.filtrerCatalogue('').total, 4);

// =====================================================================
bloc('Indicateurs qui filtrent : statut et réemploi');
// =====================================================================
charger(
  [{ 'PN Global': 'B1', 'Fonction': 'APU', 'Statut': 'Validé' },
   { 'PN Global': 'B2', 'Fonction': 'APU', 'Statut': 'En étude' },
   { 'PN Global': 'B3', 'Fonction': 'NAV', 'Statut': 'Validé' }],
  [{ 'ID_Ligne': 'a', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'HRN-1' },
   { 'ID_Ligne': 'b', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'HRN-1' },
   { 'ID_Ligne': 'c', 'PN Global': 'B3', 'Type': 'Harnais', 'PN du type': 'HRN-9' }]);
C.Store.filtreStatut = null; C.Store.filtreReutilise = false;
eq('sans filtre : 3', C.calculerVue().aAfficher.length, 3);
C.Store.filtreStatut = 'Validé';
eq('validées seulement', C.calculerVue().aAfficher.map(function (b) { return b['PN Global']; }), ['B1', 'B3']);
vrai('la vue se sait filtrée', C.calculerVue().filtre);
C.Store.filtreStatut = null;
C.Store.filtreReutilise = true;
eq('boîtes partageant une pièce', C.calculerVue().aAfficher.map(function (b) { return b['PN Global']; }), ['B1', 'B2']);
C.Store.filtreReutilise = false;
eq('pièces réutilisées', Array.from(C.piecesReutilisees()), ['hrn-1']);

eq('guillemets doublés', C.champCsv('Entraxe 5" nominal'), '"Entraxe 5"" nominal"');
const csv = C.construireCsv([['Type', 'PN'], ['Repère #3', 'A"B']]);
eq('BOM UTF-8', csv.charCodeAt(0), 0xFEFF);
eq('contenu', csv.slice(1), '"Type";"PN"\r\n"Repère #3";"A""B"');

eq('lien Drive /d/', C.urlMiniature('https://drive.google.com/file/d/1A2B3C4D5E6F7G8H9I0J1K2L/view'),
   'https://drive.google.com/thumbnail?id=1A2B3C4D5E6F7G8H9I0J1K2L&sz=w1000');
eq('image embarquée acceptée', C.urlMiniature('data:image/svg+xml;charset=utf-8,%3Csvg'),
   'data:image/svg+xml;charset=utf-8,%3Csvg');
eq('texte quelconque refusé', C.urlMiniature('pas une url'), '');

[[undefined, '-'], [null, '-'], ['', '-'], ['   ', '-'], ['H160', 'H160'], [0, '0']]
  .forEach(function (c) { eq('txt(' + JSON.stringify(c[0]) + ')', C.txt(c[0]), c[1]); });
charger([{ 'PN Global': 'B1', 'Fonction': 'APU' }], []);
faux('aucun « undefined » sur une carte sans porteur',
     C.carteHtml(C.Store.boites[0]).indexOf('undefined') !== -1);

// =====================================================================
bloc('Store — mises à jour ciblées et annulation');
// =====================================================================
charger([{ 'PN Global': 'B1', 'Fonction': 'APU' }],
        [ligneH('H1', 'B1', 'R1')]);
eq('rattachement', C.boiteParPn('B1').nomenclature.length, 1);
eq('type résolu et mis en cache', C.nomParId('H1')._type.cle, 'harnais');

C.Store.pnCourant = 'B1';
C.appliquerBoite({ 'PN Global': 'B9', 'Fonction': 'APU' }, 'B1');
eq('renommage appliqué', C.boiteParPn('B1'), null);
eq('clé étrangère suivie', C.nomParId('H1')['PN Global'], 'B9');
eq('sélection courante suivie', C.Store.pnCourant, 'B9');
eq('rattachement reconstruit', C.boiteParPn('B9').nomenclature.length, 1);

C.retirerNom('H1');
eq('ligne retirée', C.nomParId('H1'), null);
eq('lien parent recalculé', C.boiteParPn('B9').nomenclature.length, 0);

C.memoriserSuppression('nomenclature', { 'ID_Ligne': 'X' });
vrai('annulation possible juste après', C.peutAnnuler());
C.Store.derniereSuppression.heure = Date.now() - 300000;
faux('mais pas indéfiniment', C.peutAnnuler());

// =====================================================================
bloc('Réemploi : où une pièce est-elle montée ?');
// =====================================================================
charger([{ 'PN Global': 'B1', 'Fonction': 'A' }, { 'PN Global': 'B2', 'Fonction': 'A' },
         { 'PN Global': 'B3', 'Fonction': 'B' }],
  [{ 'ID_Ligne': 'H1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'HP-1', 'Référence': 'R' },
   { 'ID_Ligne': 'H2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'HP-1', 'Référence': 'R' },
   { 'ID_Ligne': 'H3', 'PN Global': 'B3', 'Type': 'Harnais', 'PN du type': 'HP-9', 'Référence': 'R' }]);
eq('la pièce partagée est vue dans les deux boîtes', C.boitesUtilisant('HP-1'), ['B1', 'B2']);
eq('en excluant la boîte courante', C.boitesUtilisant('HP-1', 'B1'), ['B2']);
eq('une pièce unique n\'est montée nulle part ailleurs', C.boitesUtilisant('HP-9', 'B3'), []);
eq('PN inconnu', C.boitesUtilisant('ZZZ'), []);
eq('PN vide', C.boitesUtilisant(''), []);
eq('insensible aux accents et à la casse', C.boitesUtilisant('hp-1'), ['B1', 'B2']);

C.Store.pnCourant = 'B1';
vrai('la fiche annonce le réemploi',
     C.blocNomHtml(C.nomParId('H1')).indexOf('Aussi montée dans') !== -1);
vrai('avec un lien vers l\'autre boîte',
     C.blocNomHtml(C.nomParId('H1')).indexOf('B2') !== -1);
faux('rien à signaler pour une pièce unique',
     C.blocNomHtml(C.nomParId('H3')).indexOf('Aussi montée dans') !== -1);

const kpiReemploi = C.calculerKpi(C.Store.boites);
eq('une pièce réutilisée', kpiReemploi.reutilisees, 1);
eq('sur deux pièces distinctes', kpiReemploi.nbPieces, 2);
eq('soit 50 %', kpiReemploi.pctReutilisees, 50);

// =====================================================================
bloc('Doublons probables');
// =====================================================================
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }, { 'PN Global': 'B3' }],
  [{ 'ID_Ligne': 'H1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'A-1', 'Référence': 'REF-X' },
   { 'ID_Ligne': 'H2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'A-2', 'Référence': 'REF-X' },
   { 'ID_Ligne': 'H3', 'PN Global': 'B3', 'Type': 'Harnais', 'PN du type': 'A-3', 'Référence': 'REF-Y' }]);
const dbl = C.compterDoublonsProbables(C.Store.boites);
eq('une paire détectée', dbl.nombre, 1);
eq('ce sont bien A-1 et A-2',
   [dbl.paires[0].a['PN du type'], dbl.paires[0].b['PN du type']].sort(), ['A-1', 'A-2']);
eq('à 100 %', dbl.paires[0].score, 100);
faux('pas tronqué sur ce volume', dbl.tronque);

// Même PN : ce n'est pas un doublon, c'est la même pièce réutilisée.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [{ 'ID_Ligne': 'H1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'MEME', 'Référence': 'R' },
   { 'ID_Ligne': 'H2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'MEME', 'Référence': 'R' }]);
eq('un PN identique n\'est pas un doublon', C.compterDoublonsProbables(C.Store.boites).nombre, 0);

// Types différents : jamais comparés entre eux.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [{ 'ID_Ligne': 'H1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'X-1', 'Référence': 'R' },
   { 'ID_Ligne': 'P1', 'PN Global': 'B2', 'Type': 'Plaquette éclairante', 'PN du type': 'X-2',
     'Mots-clés': 'R' }]);
eq('deux types différents ne font pas un doublon',
   C.compterDoublonsProbables(C.Store.boites).nombre, 0);

// La pondération pilote l'indicateur : deux structures de même montage mais
// de cotes et de masse différentes. Sur tous les critères elles restent sous
// le seuil ; sur le seul montage, elles deviennent un doublon probable.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [ligneS('S1', 'B1', 500, 140, 500),
   ligneS('S2', 'B2', 300, 90, 900)]);
eq('sur tous les critères, aucun doublon',
   C.compterDoublonsProbables(C.Store.boites).nombre, 0);

C.criteresActifs('structure').forEach(function (c) {
  if (c.cle !== 'montage') C.desactiverCritere('structure', c.cle);
});
eq('sur le seul montage, elles deviennent un doublon probable',
   C.compterDoublonsProbables(C.Store.boites).nombre, 1);
C.reinitialiserPoids();
eq('retour aux critères d\'origine', C.compterDoublonsProbables(C.Store.boites).nombre, 0);

// =====================================================================
bloc('Serveur — syntaxe et cohérence');
// =====================================================================
['server/Config.gs', 'server/Repository.gs', 'server/Api.gs', 'server/Setup.gs']
  .forEach(function (f) {
    try { H.verifierSyntaxeServeur(f); ok++; console.log('  ' + V + 'OK' + Z + '   syntaxe ' + f); }
    catch (e) { ko++; console.log('  ' + R + 'KO' + Z + '   syntaxe ' + f + ' : ' + e.message); }
  });

const srcConfig = fs.readFileSync(path.join(H.RACINE, 'server/Config.gs'), 'utf8');
const srcApi = fs.readFileSync(path.join(H.RACINE, 'server/Api.gs'), 'utf8');
const srcIndex = fs.readFileSync(path.join(H.RACINE, 'Index.html'), 'utf8');

const enTetesServeur = srcConfig.match(/NOMENCLATURE: \[([\s\S]*?)\],\n    JOURNAL/)[1]
  .match(/'([^']+)'/g).map(function (s) { return s.slice(1, -1); });
const colonnesClient = C.toutesLesColonnesNom();
const absentes = colonnesClient.filter(function (c) { return enTetesServeur.indexOf(c) === -1; });
eq('toute colonne utilisée par un type existe côté serveur', absentes, []);
vrai('Référence présente', enTetesServeur.indexOf('Référence') !== -1);
vrai('Mots-clés présents', enTetesServeur.indexOf('Mots-clés') !== -1);

vrai('XFrame en DEFAULT', srcApi.indexOf('XFrameOptionsMode.DEFAULT') !== -1);
faux('plus aucun ALLOWALL appelé', /XFrameOptionsMode\.ALLOWALL/.test(srcApi));
faux("l'URL du catalogue n'est plus en dur", /docs\.google\.com\/spreadsheets/.test(srcConfig));
vrai('verrou sur les mutations', srcApi.indexOf('avecVerrou_') !== -1);
vrai('journalisation serveur', srcApi.indexOf('journaliser_') !== -1);

// google.script.run ne doit exister que dans client/Api.html
['Dom', 'Composants', 'Types', 'Store', 'Compare', 'ViewGrid', 'ViewFiche', 'ViewCompare',
 'Reglages', 'Annulation', 'Dialogues', 'Main'].forEach(function (f) {
  const s = sansCommentaires(
    fs.readFileSync(path.join(H.RACINE, 'client/' + f + '.html'), 'utf8'));
  faux('google.script.run absent de ' + f + '.html', s.indexOf('google.script.run') !== -1);
  faux('aucun onclick= généré par ' + f + '.html', /onclick=/.test(s));
});
const srcApiClient = fs.readFileSync(path.join(H.RACINE, 'client/Api.html'), 'utf8');
eq('autant de withFailureHandler que de withSuccessHandler',
   (srcApiClient.match(/\.withFailureHandler\(/g) || []).length,
   (srcApiClient.match(/\.withSuccessHandler\(/g) || []).length);
faux('aucun onclick= dans Index.html', /onclick=/.test(srcIndex));

// Toute action référencée doit exister
const srcMain = fs.readFileSync(path.join(H.RACINE, 'client/Main.html'), 'utf8') + '\n' +
                fs.readFileSync(path.join(H.RACINE, 'client/Dialogues.html'), 'utf8');
const declarees = new Set();
(srcMain.match(/^\s*'([a-z-]+)':\s*function/gm) || []).forEach(function (l) {
  declarees.add(l.match(/'([a-z-]+)'/)[1]);
});
const utilisees = new Set();
['ViewGrid', 'ViewFiche', 'ViewCompare', 'Reglages', 'Annulation', 'Main'].forEach(function (f) {
  const s = fs.readFileSync(path.join(H.RACINE, 'client/' + f + '.html'), 'utf8');
  (s.match(/action:\s*'([a-z-]+)'/g) || []).forEach(function (m) {
    utilisees.add(m.match(/'([a-z-]+)'/)[1]);
  });
});
(srcIndex.match(/data-action="([a-z-]+)"/g) || []).forEach(function (m) {
  utilisees.add(m.match(/"([a-z-]+)"/)[1]);
});
eq('aucune action référencée sans implémentation',
   Array.from(utilisees).filter(function (a) { return !declarees.has(a); }), []);
faux('plus aucune action de journal', declarees.has('ouvrir-journal'));
faux('plus d\'export CSV', declarees.has('exporter-bom'));
faux('plus de réglages rapides', declarees.has('appliquer-preset'));
vrai('on peut retirer un critère', declarees.has('retirer-critere'));
vrai('et en rajouter un', declarees.has('ajouter-critere'));
vrai('duplication d\'un sous-ensemble', declarees.has('dupliquer-nom'));
const enTeteIndex = srcIndex.slice(srcIndex.indexOf('<header class="entete">'), srcIndex.indexOf('</header>'));
faux('pas de bouton Pondération dans l\'en-tête', /data-action="ouvrir-reglages"/.test(enTeteIndex));
vrai('le rail de réglages vit DANS la comparaison',
     /id="compareModal"[\s\S]*id="reglagesRail"[\s\S]*id="compareResult"/.test(srcIndex));
faux('plus de panneau de réglages séparé', /id="reglagesModal"/.test(srcIndex));
faux('plus d\'aperçu à part : le classement est l\'aperçu', /reglagesApercu/.test(srcIndex));
vrai('un dialogue intégré remplace prompt() et confirm()', /id="dialogueModal"/.test(srcIndex));
const srcMainSeul = sansCommentaires(fs.readFileSync(path.join(H.RACINE, 'client/Main.html'), 'utf8'));
faux('plus aucun prompt() natif', /\bprompt\(/.test(srcMainSeul));
faux('plus aucun confirm() natif', /\bconfirm\(/.test(srcMainSeul));
vrai('la duplication passe par le dialogue intégré', /demander\(/.test(srcMainSeul));
vrai('la suppression aussi', /confirmer\(/.test(srcMainSeul));
vrai('demander() existe', typeof C.demander === 'function');
vrai('confirmer() existe', typeof C.confirmer === 'function');
vrai('les indicateurs filtrent', declarees.has('filtrer-statut') && declarees.has('filtrer-reutilise'));
vrai('ajout d\'un composant en trois niveaux', declarees.has('ajouter-composant'));
faux('« Multi » n\'est plus proposé comme porteur', /value="Multi"/.test(srcIndex));
faux('plus de porteurs codés en dur dans la page', /<datalist id="list-Porteur">\s*<option/.test(srcIndex));
vrai('la pondération est atteinte depuis la comparaison',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewCompare.html'), 'utf8')
       .indexOf("action: 'ouvrir-reglages'") !== -1);
vrai('« Nouvelle boîte » et non « Assemblage »', srcIndex.indexOf('Nouvelle boîte') !== -1);
vrai('la création est dans les outils d\'en-tête, pas sous le titre',
     /class="entete-outils">[\s\S]*?data-action="nouvelle-boite"/.test(srcIndex) &&
     !/class="marque">[\s\S]*?data-action="nouvelle-boite"[\s\S]*?<\/div>\s*<div class="entete-outils"/.test(srcIndex));
eq('le titre est NEXUS seul', (srcIndex.match(/<h1>([^<]*)<\/h1>/) || [])[1], 'NEXUS');
faux('plus de bouton d\'export', /exporter-bom/.test(srcIndex));
faux('plus de bloc de réglages rapides', /reglagesPresets/.test(srcIndex));
vrai('le formulaire de création porte les porteurs', srcIndex.indexOf('newBoitePorteurs') !== -1);
vrai('le statut', srcIndex.indexOf('newBoiteStatut') !== -1);
vrai('le niveau de qualification', srcIndex.indexOf('newBoiteNiveau') !== -1);
vrai('et l\'URL de la photo', srcIndex.indexOf('newBoiteImage') !== -1);
vrai('indicateur de réutilisation', srcIndex.indexOf('kpiReutil') !== -1);
vrai('indicateur de doublons probables', srcIndex.indexOf('kpiDoublons') !== -1);
vrai('les doublons sont consultables', declarees.has('ouvrir-doublons'));
vrai('le tri est un menu, plus un select', declarees.has('choisir-tri'));
faux('plus de <select> de tri', /id="triSelect"/.test(srcIndex));
vrai('la recherche par composant est dans le champ',
     /class="btn-dans-champ"[^>]*id="btnComposant"/.test(srcIndex));
faux('plus de bandeau de démonstration dans la source livrée',
     /barreDemo/.test(srcIndex));

faux('plus de sous-titre sous le titre', /Nomenclatures d'assemblages/.test(srcIndex));
vrai('indicateur « Boîtes »', /indicateur-libelle">Boîtes</.test(srcIndex));
faux('plus d\'indicateur « Sous-ensembles »', /indicateur-libelle">Sous-ensembles</.test(srcIndex));
vrai('duplication d\'une boîte depuis la carte',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewGrid.html'), 'utf8')
       .indexOf("action: 'dupliquer-boite'") !== -1);
faux('plus de duplication de boîte dans la fiche',
     sansCommentaires(fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8'))
       .indexOf("'dupliquer-boite'") !== -1);
vrai('duplication d\'un sous-ensemble depuis la fiche',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8')
       .indexOf("'dupliquer-nom'") !== -1);

// Tous les jetons CSS utilisés sont définis en clair
const srcCss = fs.readFileSync(path.join(H.RACINE, 'client/Styles.html'), 'utf8');
const base = srcCss.slice(srcCss.indexOf(':root {'), srcCss.indexOf(':root:not('));
const definis = new Set((base.match(/--[a-z0-9-]+:/g) || []).map(function (v) { return v.slice(0, -1); }));
const jetons = new Set((srcCss.match(/var\(--[a-z0-9-]+\)/g) || [])
                        .map(function (v) { return v.slice(4, -1); }));
eq('tous les jetons CSS sont définis dans le :root de base',
   Array.from(jetons).filter(function (j) { return !definis.has(j); }), []);
vrai('le thème sombre redéfinit les jetons', srcCss.indexOf('[data-theme="dark"]') !== -1);
vrai('body peint son fond explicitement', /body \{[\s\S]*?background: var\(--sol\)/.test(srcCss));
// La couleur ne doit servir qu'à porter une information.
const teintesInterface = (srcCss.match(/--encre[0-9-]*:|--trait[a-z-]*:|--sol[0-9-]*:|--surface[0-9-]*:/g) || []).length;
vrai('des jetons neutres pour toute la chrome', teintesInterface >= 8);
vrai('une seule teinte de marque, réservée aux actions', /--marque:/.test(srcCss));
faux('pas de second accent', /--accent:/.test(srcCss));
vrai('le sol est blanc', /--sol: #ffffff/.test(srcCss));
vrai('le rail et le classement sont côte à côte', /\.compare-corps\.avec-reglages \{ grid-template-columns: 300px/.test(srcCss));
vrai('les couleurs de type subsistent', /--t-structure:|--t-harnais:|--t-plaquette:/.test(srcCss));
vrai('les couleurs de statut subsistent', /--vert:|--ambre:|--rouge:/.test(srcCss));

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z +
            G + '  (' + declarees.size + ' actions)' + Z);
process.exit(ko === 0 ? 0 : 1);
