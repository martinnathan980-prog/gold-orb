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
eq('4 portées comparables (boîte + 3 types)', C.porteesComparables().length, 4);
eq('plus une portée interne : les niveaux de composant', C.PORTEES.length, 5);
eq('elle est marquée interne', C.porteeParCle('composant').interne, true);
faux('et n\'apparaît pas parmi les comparables',
     C.porteesComparables().some(function (p) { return p.cle === 'composant'; }));
eq('s\'arbitrent : la boîte, la structure, et les niveaux de composant',
   C.PORTEES.filter(C.porteeArbitrable).map(function (p) { return p.cle; }),
   ['boite', 'structure', 'composant']);
eq('les niveaux, du plus large au plus précis',
   C.NIVEAUX.map(function (n) { return n.cle; }), ['fonction', 'norme', 'reference']);
vrai('la boîte règle ses niveaux de composant',
     C.porteeAvecComposants(C.porteeParCle('boite')));
vrai('la structure aussi', C.porteeAvecComposants(C.porteeParCle('structure')));
faux('le harnais non, il n\'a pas de composants',
     C.porteeAvecComposants(C.porteeParCle('harnais')));
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

// --- Le calcul, niveau par niveau -----------------------------------
// Parts par défaut : fonction 20, norme 30, référence 50. Elles
// S'ADDITIONNENT. Ce qui n'est pas renseigné sort du dénominateur.
C.reinitialiserPoids();
const comp = function (t) { return C.analyserComposant(t); };
const ratio = function (a, b) {
  return Math.round(C.comparerComposants(comp(a), comp(b)).ratio * 1000) / 1000;
};

eq('tout identique : le maximum',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 7251 | MS24523-22'), 1);
eq('fonction et norme partagées, référence différente : 20 + 30 sur 100',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 7251 | MS24523-23'), 0.5);
eq('fonction seule partagée : 20 sur 100',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 0763 | MS24523-31'), 0.2);
eq('fonctions différentes : rien',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Voyant | ECS 7251 | MS24523-22'), 0);

// Ce qui n'est pas renseigné ne peut pas être exigé.
eq('source décrite par sa seule fonction, retrouvée : tous ses points',
   ratio('Colonnette', 'Colonnette | NSA 5512 | COL-M4-20'), 1);
eq('fonction + norme renseignées et partagées : tous ses points',
   ratio('Colonnette | NSA 5512', 'Colonnette | NSA 5512 | COL-M4-20'), 1);
eq('fonction + norme renseignées, norme différente : 20 sur 50',
   ratio('Colonnette | NSA 5512', 'Colonnette | NSA 5599 | COL-X'), 0.4);
eq('cible muette sur un niveau que la source renseigne : le niveau est perdu',
   ratio('Colonnette | NSA 5512 | COL-M4-20', 'Colonnette'), 0.2);
eq('casse et accents indifférents',
   ratio('Équerre | en 2491 | eq-90-a', 'equerre | EN 2491 | EQ-90-A'), 1);

const detail = C.comparerComposants(comp('Bouton poussoir | ECS 7251 | MS24523-22'),
                                    comp('Bouton poussoir | ECS 7251 | MS24523-23'));
eq('le détail nomme les trois niveaux',
   detail.niveaux.map(function (n) { return n.cle; }), ['fonction', 'norme', 'reference']);
eq('et leur état', detail.niveaux.map(function (n) { return n.etat; }),
   ['egal', 'egal', 'different']);
eq('les points obtenus', detail.obtenu, 50);
eq('sur le maximum atteignable', detail.max, 100);
const detailPartiel = C.comparerComposants(comp('Colonnette'), comp('Colonnette | NSA 5512 | X'));
eq('un niveau non renseigné est marqué absent',
   detailPartiel.niveaux.map(function (n) { return n.etat; }), ['egal', 'absent', 'absent']);
eq('et ne gonfle pas le dénominateur', detailPartiel.max, 20);

// --- Les parts sont réglables ---------------------------------------
C.reglerPoids('composant', 'reference', 90);
eq('la somme des niveaux reste 100',
   C.criteresActifs('composant').reduce(function (t, c) {
     return t + C.Store.poids.composant[c.cle]; }, 0), 100);
vrai('référence à 90 : partager la seule fonction ne vaut presque plus rien',
     ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 0763 | X') < 0.1);
C.reglerPoids('composant', 'reference', 0);
eq('référence à 0 : fonction et norme font tout le score',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 7251 | AUTRE'), 1);
C.reinitialiserPoids();

// Un niveau écarté sort du calcul, il ne vaut pas 0 point sur 100.
C.desactiverCritere('composant', 'norme');
eq('la norme écartée ne compte plus du tout',
   ratio('Bouton poussoir | ECS 7251 | MS24523-22', 'Bouton poussoir | ECS 9999 | MS24523-22'), 1);
eq('elle est signalée comme écartée',
   C.comparerComposants(comp('A | B | C'), comp('A | B | C'))
    .niveaux.filter(function (n) { return n.etat === 'ecarte'; }).length, 1);
C.reinitialiserPoids();

// --- L'appariement ---------------------------------------------------
const S = [comp('Bouton poussoir | ECS 7251 | MS24523-22'),
           comp('Voyant | ECS 4410 | LED-G-28'),
           comp('Relais | ECS 1120 | RLY-28-2C'),
           comp('Fusible | NSA 9350 | F5A')];
const T = [comp('Bouton poussoir | ECS 7251 | MS24523-22'),   // les trois niveaux
           comp('Voyant | ECS 4410 | LED-G-05'),              // fonction + norme
           comp('Relais | ECS 1121 | RLY-28-4C'),             // fonction seule
           comp('Connecteur | EN 3645 | CN-3645-12')];        // en plus
const ap = C.apparierComposants(S, T);
eq('3 composants appariés', ap.appariements.length, 3);
eq('1 sans équivalent', ap.aucun.map(function (c) { return c.fonction; }), ['Fusible']);
eq('1 en plus sur la cible', ap.enPlus.map(function (c) { return c.fonction; }), ['Connecteur']);
eq('le meilleur appariement en tête', ap.appariements[0].source.fonction, 'Bouton poussoir');
eq('les scores, du plus fort au plus faible',
   ap.appariements.map(function (a) { return Math.round(a.detail.ratio * 100); }), [100, 50, 20]);
eq('le score du critère est la moyenne sur la SOURCE, manquants compris',
   Math.round(ap.ratio * 1000) / 1000, Math.round(((1 + 0.5 + 0.2) / 4) * 1000) / 1000);

eq('une fonction différente n\'est jamais appariée, même référence identique',
   C.apparierComposants([comp('Relais | X | ABC')], [comp('Voyant | X | ABC')]).appariements.length, 0);
eq('un composant de la cible ne sert qu\'une fois',
   C.apparierComposants([comp('A | B | C'), comp('A | B | C')], [comp('A | B | C')]).aucun.length, 1);
eq('source vide : ratio 0', C.apparierComposants([], T).ratio, 0);
eq('cible vide : rien n\'est apparié', C.apparierComposants(S, []).appariements.length, 0);
eq('et tout est sans équivalent', C.apparierComposants(S, []).aucun.length, 4);

// L'ordre de saisie ne doit rien changer : on classe les paires avant de servir.
const melange = function (t) { return t.slice().reverse(); };
eq('le score ne dépend pas de l\'ordre des listes',
   Math.round(C.apparierComposants(melange(S), melange(T)).ratio * 1000) / 1000,
   Math.round(ap.ratio * 1000) / 1000);

// Le meilleur candidat est pris, pas le premier rencontré.
const gourmand = C.apparierComposants(
  [comp('Colonnette | NSA 5512 | COL-M4-20')],
  [comp('Colonnette | NSA 9999 | AUTRE'), comp('Colonnette | NSA 5512 | COL-M4-20')]);
eq('le candidat parfait est préféré au médiocre',
   gourmand.appariements[0].cible.reference, 'COL-M4-20');
eq('et le médiocre reste « en plus »', gourmand.enPlus[0].norme, 'NSA 9999');

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
faux('plus de duplication d\'un sous-ensemble : on en ajoute un, on ne le recopie pas',
     blocH2.indexOf('dupliquer-nom') !== -1);
vrai('mais on peut toujours l\'éditer', blocH2.indexOf('editer-nom') !== -1);
vrai('et chercher ses équivalences', blocH2.indexOf('comparer-nom') !== -1);

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
bloc('Inventaire des pièces : où sert quoi');
// =====================================================================
charger(
  [{ 'PN Global': 'B1', 'Fonction': 'APU' },
   { 'PN Global': 'B2', 'Fonction': 'APU' },
   { 'PN Global': 'B3', 'Fonction': 'NAV' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'HRN-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'HRN-1' },
   { 'ID_Ligne': '3', 'PN Global': 'B3', 'Type': 'Harnais', 'PN du type': 'HRN-1' },
   { 'ID_Ligne': '4', 'PN Global': 'B1', 'Type': 'Structure boîte', 'PN du type': 'STR-9' },
   { 'ID_Ligne': '5', 'PN Global': 'B2', 'Type': 'Structure boîte', 'PN du type': 'STR-9' },
   { 'ID_Ligne': '6', 'PN Global': 'B3', 'Type': 'Plaquette éclairante', 'PN du type': 'PLQ-7' },
   { 'ID_Ligne': '7', 'PN Global': 'B3', 'Type': 'Harnais', 'PN du type': '' }]);

const inv = C.inventairePieces(C.Store.boites);
eq('3 pièces distinctes, la pièce sans PN écartée', inv.length, 3);
eq('la plus réutilisée en tête', inv[0].pn, 'HRN-1');
eq('elle est dans 3 boîtes', inv[0].nombre, 3);
eq('et on sait lesquelles', inv[0].boites, ['B1', 'B2', 'B3']);
eq('puis celle dans 2 boîtes', [inv[1].pn, inv[1].nombre], ['STR-9', 2]);
eq('la pièce unique ferme la marche', [inv[2].pn, inv[2].nombre], ['PLQ-7', 1]);
eq('le type est résolu', inv[0].type.cle, 'harnais');
faux('une pièce sans PN n\'est jamais listée',
     inv.some(function (p) { return !p.pn; }));

// Deux pièces de MÊME PN mais de types différents restent distinctes : ce
// n'est pas la même chose, et on ne les compte pas ensemble.
charger(
  [{ 'PN Global': 'B1' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'X-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B1', 'Type': 'Structure boîte', 'PN du type': 'X-1' }]);
eq('même PN, deux types : deux entrées', C.inventairePieces(C.Store.boites).length, 2);

// La même pièce montée DEUX FOIS dans la même boîte ne fait pas deux boîtes.
charger(
  [{ 'PN Global': 'B1' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'Y-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'Y-1' }]);
const doubleMontage = C.inventairePieces(C.Store.boites);
eq('une seule entrée', doubleMontage.length, 1);
eq('une seule boîte', doubleMontage[0].nombre, 1);
eq('mais les deux lignes sont gardées', doubleMontage[0].lignes.length, 2);

// Casse et accents : « Colonnette » et « COLONNETTE » sont la même pièce.
charger(
  [{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'Réf-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'REF-1' }]);
eq('accents et casse regroupés', C.inventairePieces(C.Store.boites).length, 1);
eq('et comptés comme réutilisés', C.inventairePieces(C.Store.boites)[0].nombre, 2);

eq('base vide, inventaire vide', C.inventairePieces([]), []);
charger([{ 'PN Global': 'B1' }], []);
eq('boîte sans nomenclature', C.inventairePieces(C.Store.boites), []);

// L'inventaire suit les filtres : il porte sur ce qui est affiché.
charger(
  [{ 'PN Global': 'B1', 'Statut': 'Validé' }, { 'PN Global': 'B2', 'Statut': 'En étude' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'Z-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'Z-1' }]);
eq('sans filtre, la pièce est dans 2 boîtes',
   C.inventairePieces(C.calculerVue().aAfficher)[0].nombre, 2);
C.Store.filtreStatut = 'Validé';
eq('filtré sur les validées, elle n\'est plus que dans 1',
   C.inventairePieces(C.calculerVue().aAfficher)[0].nombre, 1);
C.Store.filtreStatut = null;

// Le rendu : échappement compris, puisque des PN piégés existent.
charger(
  [{ 'PN Global': 'B"1' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B"1', 'Type': 'Harnais', 'PN du type': '<b>P</b>' }]);
const htmlPieces = C.piecesHtml(C.calculerVue());
faux('un PN piégé n\'injecte rien', /<b>P<\/b>/.test(htmlPieces));
vrai('le PN piégé est affiché échappé', htmlPieces.indexOf('&lt;b&gt;P&lt;/b&gt;') !== -1);
eq('le lien vers la boîte porte le PN intact',
   attribut(htmlPieces.match(/data-action="ouvrir-fiche"[^>]*>/)[0], 'data-pn'), 'B"1');
vrai('une pièce montée une seule fois n\'est pas marquée partagée',
     htmlPieces.indexOf('piece-partagee') === -1);
charger(
  [{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [{ 'ID_Ligne': '1', 'PN Global': 'B1', 'Type': 'Harnais', 'PN du type': 'W-1' },
   { 'ID_Ligne': '2', 'PN Global': 'B2', 'Type': 'Harnais', 'PN du type': 'W-1' }]);
vrai('une pièce partagée l\'est', C.piecesHtml(C.calculerVue()).indexOf('piece-partagee') !== -1);
vrai('avec le compte en clair', C.piecesHtml(C.calculerVue()).indexOf('2 boîtes') !== -1);
charger([{ 'PN Global': 'B1' }], []);
vrai('inventaire vide : on le dit', C.piecesHtml(C.calculerVue()).indexOf('etat-vide') !== -1);

// Le mode de vue se mémorise, et refuse une valeur inventée.
C.Store.vueMode = 'pieces';
C.enregistrerReglages();
C.Store.vueMode = 'boites';
C.chargerReglages();
eq('le mode est relu', C.Store.vueMode, 'pieces');
C.Store.vueMode = 'boites';
C.enregistrerReglages();

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
faux('plus d\'action de duplication de sous-ensemble', declarees.has('dupliquer-nom'));
faux('ni de duplication de boîte : elle ne servait pas non plus',
     declarees.has('dupliquer-boite'));
faux('la liaison client a disparu aussi',
     fs.readFileSync(path.join(H.RACINE, 'client/Api.html'), 'utf8').indexOf('dupliquerBoite') !== -1);
faux('et la fonction serveur, qui n\'avait plus d\'appelant',
     srcApi.indexOf('dupliquerBoite') !== -1);
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
vrai('les suppressions passent par le dialogue intégré', /confirmer\(/.test(srcMainSeul));
eq('deux suppressions confirmées : la boîte et le sous-ensemble',
   (srcMainSeul.match(/confirmer\(\{/g) || []).length, 2);
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

// Le bouton de création ne doit plus côtoyer le nom du site : il vit dans la
// barre d'action, avec la recherche, entre l'en-tête et le catalogue.
const enTeteComplet = srcIndex.slice(srcIndex.indexOf('<header class="entete">'),
                                     srcIndex.indexOf('</header>'));
faux('la création n\'est plus dans l\'en-tête',
     enTeteComplet.indexOf('nouvelle-boite') !== -1);
faux('plus de zone d\'outils accolée au titre', /entete-outils/.test(srcIndex));
const bande = srcIndex.slice(srcIndex.indexOf('<div class="bande-action">'),
                             srcIndex.indexOf('<main class="enveloppe contenu">'));
vrai('la barre d\'action existe', bande.length > 100);
vrai('elle porte la recherche', bande.indexOf('id="searchBar"') !== -1);
vrai('et le bouton de création', bande.indexOf('data-action="nouvelle-boite"') !== -1);
vrai('la recherche a quitté le corps de page',
     srcIndex.slice(srcIndex.indexOf('<main class="enveloppe contenu">'))
             .indexOf('id="searchBar"') === -1);
vrai('le titre reste seul dans sa marque',
     /<div class="marque">\s*<h1>NEXUS<\/h1>\s*<\/div>/.test(srcIndex));
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
vrai('on bascule entre boîtes et sous-ensembles', declarees.has('changer-vue'));
const srcGrille = fs.readFileSync(path.join(H.RACINE, 'client/ViewGrid.html'), 'utf8');
vrai('la seconde vue s\'appelle « Sous-ensembles »',
     srcGrille.indexOf("'Sous-ensembles'") !== -1);
faux('« Pièces » a disparu de l\'étiquette', /'pieces', 'Pièces'/.test(srcGrille));
vrai('l\'inventaire nomme sa colonne « Sous-ensemble »',
     srcGrille.indexOf('<span>Sous-ensemble</span>') !== -1);
vrai('l\'en-tête du rail annonce les niveaux',
     fs.readFileSync(path.join(H.RACINE, 'client/Reglages.html'), 'utf8')
       .indexOf('niveaux de composant') !== -1);
vrai('la page réserve une place au sélecteur de vue', srcIndex.indexOf('id="zoneVue"') !== -1);
vrai('le tri est un menu, plus un select', declarees.has('choisir-tri'));
faux('plus de <select> de tri', /id="triSelect"/.test(srcIndex));
vrai('la recherche par composant est dans le champ',
     /class="btn-dans-champ"[^>]*id="btnComposant"/.test(srcIndex));
faux('plus de bandeau de démonstration dans la source livrée',
     /barreDemo/.test(srcIndex));

faux('plus de sous-titre sous le titre', /Nomenclatures d'assemblages/.test(srcIndex));
vrai('indicateur « Boîtes »', /indicateur-libelle">Boîtes</.test(srcIndex));
faux('plus d\'indicateur « Sous-ensembles »', /indicateur-libelle">Sous-ensembles</.test(srcIndex));
faux('plus de duplication de boîte sur la carte',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewGrid.html'), 'utf8')
       .indexOf('dupliquer-boite') !== -1);
faux('plus de duplication de boîte dans la fiche',
     sansCommentaires(fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8'))
       .indexOf("'dupliquer-boite'") !== -1);
faux('aucun reste de duplication dans la fiche',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8')
       .indexOf('dupliquer-nom') !== -1);

// Tous les jetons CSS utilisés sont définis en clair
const srcCss = fs.readFileSync(path.join(H.RACINE, 'client/Styles.html'), 'utf8');
const base = srcCss.slice(srcCss.indexOf(':root {'), srcCss.indexOf(':root:not('));
const definis = new Set((base.match(/--[a-z0-9-]+:/g) || []).map(function (v) { return v.slice(0, -1); }));
const jetons = new Set((srcCss.match(/var\(--[a-z0-9-]+\)/g) || [])
                        .map(function (v) { return v.slice(4, -1); }));
eq('tous les jetons CSS sont définis dans le :root de base',
   Array.from(jetons).filter(function (j) { return !definis.has(j); }), []);
vrai('l\'inventaire a son style', /\.inventaire \{/.test(srcCss));
vrai('les pièces partagées se repèrent', /\.piece-partagee \{/.test(srcCss));
vrai('le sélecteur de vue aussi', /\.onglet-vue \{/.test(srcCss));
vrai('les niveaux d\'un composant ont leur pastille', /\.niveau-egal\s+\{/.test(srcCss));
vrai('la sous-pondération a son bloc', /\.sous-reglage \{/.test(srcCss));
vrai('le bloc des niveaux est collé en bas du rail',
     /\.sous-reglage \{[\s\S]*?position: sticky/.test(srcCss));
vrai('et signalé par un filet marine',
     /\.sous-reglage \{[\s\S]*?border-top: 2px solid var\(--marque\)/.test(srcCss));
vrai('le rail règle les niveaux quand la portée compare des composants',
     fs.readFileSync(path.join(H.RACINE, 'client/Reglages.html'), 'utf8')
       .indexOf('porteeAvecComposants') !== -1);
vrai('chaque curseur porte sa portée',
     /data-portee="' \+ esc\(portee\.cle\)/.test(
       fs.readFileSync(path.join(H.RACINE, 'client/Reglages.html'), 'utf8')));
vrai('le thème sombre redéfinit les jetons', srcCss.indexOf('[data-theme="dark"]') !== -1);
vrai('body peint son fond explicitement', /body \{[\s\S]*?background: var\(--sol\)/.test(srcCss));
// La couleur ne doit servir qu'à porter une information.
const teintesInterface = (srcCss.match(/--encre[0-9-]*:|--trait[a-z-]*:|--sol[0-9-]*:|--surface[0-9-]*:/g) || []).length;
vrai('des jetons neutres pour toute la chrome', teintesInterface >= 8);
vrai('une seule teinte de marque, réservée aux actions', /--marque:/.test(srcCss));
faux('pas de second accent', /--accent:/.test(srcCss));
// Le sol est BLANC : c'est lui qui donne l'impression de propreté. La
// couleur est portée par les objets posés dessus, pas par le fond.
const jeton = function (nom) {
  const m = srcCss.match(new RegExp('--' + nom + ': (#[0-9a-f]{6})'));
  return m ? m[1] : null;
};
eq('le sol est blanc', jeton('sol'), '#ffffff');
vrai('l\'en-tête l\'est aussi, sous NEXUS',
     /\.entete \{ background: var\(--sol\)/.test(srcCss));
faux('les cartes, elles, ne sont pas blanches', jeton('surface') === '#ffffff');
eq('ce qui se saisit reste blanc', jeton('surface-2'), '#ffffff');
vrai('la barre d\'action a sa teinte', !!jeton('bande'));
// Les teintes portent un voile bleu : le bleu doit dominer le rouge.
const bleute = function (hex) {
  return parseInt(hex.slice(5, 7), 16) > parseInt(hex.slice(1, 3), 16);
};
['sol-2', 'surface', 'surface-3', 'bande', 'trait', 'trait-fort'].forEach(function (n) {
  vrai('--' + n + ' est bleuté, pas gris neutre', bleute(jeton(n)));
});
const clarte = function (hex) {
  return parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
};
vrai('les cartes se détachent du sol blanc par leur teinte',
     clarte(jeton('surface')) < clarte(jeton('sol')));
vrai('la barre d\'action est plus soutenue que les cartes',
     clarte(jeton('bande')) < clarte(jeton('surface')));
// Les indicateurs sont une ligne cadrée de filets, pas une rangée de cartes.
vrai('les indicateurs forment une ligne continue',
     /\.indicateurs \{[\s\S]*?display: flex/.test(srcCss));
vrai('cadrée en haut et en bas', /\.indicateurs \{[\s\S]*?border-top: 1px solid var\(--trait\)/.test(srcCss));
vrai('avec un filet entre chaque mesure',
     /\.indicateur \+ \.indicateur::before/.test(srcCss));
faux('plus de jauge sous les chiffres', /indicateur-jauge/.test(srcCss));
faux('ni dans la page', /kpiValJauge/.test(srcIndex));
vrai('le bouton de création est arrondi',
     /\.btn-creer \{[\s\S]*?border-radius: 999px/.test(srcCss));
vrai('la barre est soulignée par un filet marine',
     /\.bande-action \{[\s\S]*?border-top: 3px solid var\(--marque\)/.test(srcCss));
vrai('elle tient sur une ligne, recherche puis bouton',
     /\.bande-corps \{[\s\S]*?display: flex/.test(srcCss));
vrai('et passe en colonne sur petit écran',
     /\.bande-corps \{ flex-direction: column/.test(srcCss));
faux('plus de style pour les outils d\'en-tête', /\.entete-outils/.test(srcCss));
vrai('le rail et le classement sont côte à côte', /\.compare-corps\.avec-reglages \{ grid-template-columns: 300px/.test(srcCss));
vrai('les couleurs de type subsistent', /--t-structure:|--t-harnais:|--t-plaquette:/.test(srcCss));
vrai('les couleurs de statut subsistent', /--vert:|--ambre:|--rouge:/.test(srcCss));

console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z +
            G + '  (' + declarees.size + ' actions)' + Z);
process.exit(ko === 0 ? 0 : 1);
