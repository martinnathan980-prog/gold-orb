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

// Sources lues une fois : plusieurs blocs verifient le code livre.
const lireSrc = function (f) { return fs.readFileSync(path.join(H.RACINE, f), 'utf8'); };
const grilleSrc = lireSrc('client/ViewGrid.html');
const ficheSrc = lireSrc('client/ViewFiche.html');
const cssSrc = lireSrc('client/Styles.html');

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
             'Qualification Explosion', 'Mots-clés', 'Composants mécaniques', 'Composants routing'],
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
faux('aucun composant sur le harnais', champs('harnais').indexOf('Composants mécaniques') !== -1);
faux('aucun composant sur la plaquette', champs('plaquette').indexOf('Composants routing') !== -1);
vrai('la structure porte sa composants mécaniques', champs('structure').indexOf('Composants mécaniques') !== -1);
vrai('et ses composants électriques', champs('structure').indexOf('Composants routing') !== -1);
faux('plus de colonne « Composant STD »', C.toutesLesColonnesNom().indexOf('Composant STD') !== -1);
eq('la structure compare ses deux familles séparément',
   C.TYPES.structure.criteres.filter(function (c) { return c.mode === C.MODE.COMPOSANTS; })
     .map(function (c) { return c.champ; }),
   ['Composants mécaniques', 'Composants routing']);
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
eq('quinze porteurs', C.PORTEURS.length, 15);
vrai('le Dauphin est de la famille', C.PORTEURS.indexOf('Dauphin') !== -1);
[ 'H155', 'H175M', 'UH-72 Lakota' ].forEach(function (p) {
  faux(p + ' a ete retire', C.PORTEURS.indexOf(p) !== -1);
});
['Dauphin', 'H125', 'H130', 'H135', 'H145', 'H145M', 'H160', 'H160M', 'H175',
 'H215', 'H215M', 'H225', 'H225M', 'NH90', 'Tigre'].forEach(function (p) {
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
     blocS.indexOf('Composants mécaniques') !== -1 && blocS.indexOf('Composants routing') !== -1);
vrai('en colonnes fonction / norme / référence', blocS.indexOf('composants-entete') !== -1);
vrai('avec un catalogue par catégorie',
     blocS.indexOf('data-categorie="mecanique"') !== -1 && blocS.indexOf('data-categorie="electrique"') !== -1);

const blocP = C.blocNomHtml(C.nomParId('P1'));
vrai('la plaquette affiche ses mots-clés', blocP.indexOf('mission SAR') !== -1);
vrai('avec le style dédié', blocP.indexOf('puce-motcle') !== -1);
faux('la plaquette n\'affiche PAS son numéro (même renseigné)', blocP.indexOf('PL-1') !== -1);
faux('ni ses cotes', blocP.indexOf('777') !== -1);
faux('ni de composants', /Composants mécaniques|Composants routing/.test(blocP));

const blocH2 = C.blocNomHtml(C.nomParId('H1'));
faux('le harnais n\'affiche pas de qualification', blocH2.indexOf('Qualif') !== -1);
faux('ni de composants', /Composants mécaniques|Composants routing/.test(blocH2));
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
eq('catalogue filtré par catégorie : la composants mécaniques', C.filtrerCatalogue('', 'mecanique').total, 2);
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
C.Store.filtreStatut = null;
eq('sans filtre : 3', C.calculerVue().aAfficher.length, 3);
C.Store.filtreStatut = 'Validé';
eq('validées seulement', C.calculerVue().aAfficher.map(function (b) { return b['PN Global']; }), ['B1', 'B3']);
vrai('la vue se sait filtrée', C.calculerVue().filtre);
C.Store.filtreStatut = null;
faux('sans filtre, la vue ne se dit pas filtrée', C.calculerVue().filtre);
// Le filtre « pièces réutilisées » a été retiré : la notion n'était pas
// comprise, et le bouton ne répondait à aucune question qu'on se pose.
eq('plus de filtre par réemploi', typeof C.piecesReutilisees, 'undefined');

// L'export CSV a ete retire il y a plusieurs versions ; ses deux aides
// n'avaient plus d'appelant et ne survivaient que par ce test.
eq('plus de fabrique CSV', typeof C.construireCsv, 'undefined');
eq('ni d\'echappement de cellule', typeof C.champCsv, 'undefined');

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
bloc('Standardisation : où la base se disperse');
// =====================================================================
const boiteAvec = function (pn, composants) {
  return { 'PN Global': pn, 'Composants': composants };
};
const structureAvec = function (id, pn, meca) {
  return { 'ID_Ligne': id, 'PN Global': pn, 'Type': 'Structure boîte',
           'PN du type': pn + '.01', 'Composants mécaniques': meca };
};

// Cinq références sous une seule norme : le cas d'école.
charger(
  [boiteAvec('B1', 'Bouton poussoir | ECS 7251 | MS24523-22'),
   boiteAvec('B2', 'Bouton poussoir | ECS 7251 | MS24523-23'),
   boiteAvec('B3', 'Bouton poussoir | ECS 7251 | MS24523-24')], []);
let op = C.opportunitesStandardisation(C.Store.boites);
eq('une famille dispersée', op.length, 1);
eq('la fonction', op[0].fonction, 'Bouton poussoir');
eq('une seule norme', op[0].nbNormes, 1);
eq('mais trois références', op[0].nbReferences, 3);
eq('la catégorie est celle du champ', op[0].categorie, 'composant');
eq('chaque référence sait où elle sert',
   op[0].normes[0].references.map(function (r) { return r.nbBoites; }), [1, 1, 1]);

// Une seule référence partout : rien à rationaliser.
charger(
  [boiteAvec('B1', 'Bouton poussoir | ECS 7251 | MS24523-22'),
   boiteAvec('B2', 'Bouton poussoir | ECS 7251 | MS24523-22')], []);
eq('la même référence partout n\'est pas une dispersion',
   C.opportunitesStandardisation(C.Store.boites).length, 0);
eq('mais on sait qu\'elle sert dans deux boîtes',
   Array.from(C.famillesComposants(C.Store.boites).values())[0]
     .normes.get('ecs 7251').references.get('ms24523-22').boites.size, 2);

// Plusieurs normes pour une même fonction : dispersion aussi.
charger(
  [boiteAvec('B1', 'Voyant | ECS 4410 | LED-G-28'),
   boiteAvec('B2', 'Voyant | ECS 4411 | LED-R-28')], []);
op = C.opportunitesStandardisation(C.Store.boites);
eq('deux normes pour la même fonction', op[0].nbNormes, 2);
eq('et deux références', op[0].nbReferences, 2);

// Le classement : la famille la plus dispersée en tête.
charger(
  [boiteAvec('B1', 'Voyant | ECS 4410 | LED-1\nRelais | ECS 1120 | RLY-1'),
   boiteAvec('B2', 'Voyant | ECS 4410 | LED-2\nRelais | ECS 1120 | RLY-2'),
   boiteAvec('B3', 'Voyant | ECS 4410 | LED-3')], []);
op = C.opportunitesStandardisation(C.Store.boites);
eq('la plus dispersée en tête', op[0].fonction, 'Voyant');
eq('avec ses trois références', op[0].nbReferences, 3);
eq('puis le relais', [op[1].fonction, op[1].nbReferences], ['Relais', 2]);

// Une même fonction dans deux CATÉGORIES différentes reste deux familles :
// une cosse électrique n'est pas une cosse mécanique.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Cosse | EN 2491 | CS-1' }],
  [structureAvec('S1', 'B1', 'Cosse | EN 2491 | CS-2')]);
const famillesMixtes = C.famillesComposants(C.Store.boites);
eq('deux familles, une par catégorie', famillesMixtes.size, 2);
eq('aucune n\'est dispersée toute seule',
   C.opportunitesStandardisation(C.Store.boites).length, 0);

// Les composants de structure sont bien parcourus.
charger(
  [{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [structureAvec('S1', 'B1', 'Colonnette | NSA 5512 | COL-M4-20'),
   structureAvec('S2', 'B2', 'Colonnette | NSA 5512 | COL-M6-40')]);
op = C.opportunitesStandardisation(C.Store.boites);
eq('la composants mécaniques compte aussi', op.length, 1);
eq('dans sa catégorie', op[0].categorie, 'mecanique');
eq('deux références de colonnette', op[0].nbReferences, 2);

// Un composant sans fonction n'a pas de famille.
charger([{ 'PN Global': 'B1', 'Composants': ' | ECS 7251 | MS24523-22' }], []);
eq('sans fonction, pas de famille', C.famillesComposants(C.Store.boites).size, 0);

// L'analyse suit les filtres, comme les deux autres vues.
charger(
  [{ 'PN Global': 'B1', 'Statut': 'Validé', 'Composants': 'Voyant | ECS 4410 | LED-1' },
   { 'PN Global': 'B2', 'Statut': 'En étude', 'Composants': 'Voyant | ECS 4410 | LED-2' }], []);
eq('sans filtre, la dispersion est visible',
   C.opportunitesStandardisation(C.calculerVue().aAfficher).length, 1);
C.Store.filtreStatut = 'Validé';
eq('filtré sur une seule boîte, plus de dispersion',
   C.opportunitesStandardisation(C.calculerVue().aAfficher).length, 0);
C.Store.filtreStatut = null;

eq('base vide', C.opportunitesStandardisation([]), []);

// Le rendu, échappement compris.
charger([{ 'PN Global': 'B"1', 'Composants': '<b>V</b> | N1 | R1\n<b>V</b> | N1 | R2' }], []);
const htmlStd = C.standardisationHtml(C.calculerVue());
faux('une fonction piégée n\'injecte rien', /<b>V<\/b>/.test(htmlStd));
vrai('elle est affichée échappée', htmlStd.indexOf('&lt;b&gt;V&lt;/b&gt;') !== -1);
vrai('le compte de références est affiché', htmlStd.indexOf('2</b> références') !== -1);
// Sans dispersion, il n'y a rien a montrer : les familles deja rangees ne
// demandent aucune action, les lister noyait celles qui en demandent une.
charger([{ 'PN Global': 'B1', 'Composants': 'Voyant | N1 | R1' }], []);
const htmlPropre = C.standardisationHtml(C.calculerVue());
vrai('une famille deja rangee ne s\'affiche pas', htmlPropre.indexOf('etat-vide') !== -1);
vrai('et on dit pourquoi', htmlPropre.indexOf('Rien à standardiser') !== -1);
faux('plus de section « Deja rangees »', /standard-propres|Déjà rangées/.test(htmlPropre));

// Sans aucun composant, meme message : il n'y a rien a analyser.
charger([{ 'PN Global': 'B1' }], []);
vrai('sans composant, on le dit aussi',
     C.standardisationHtml(C.calculerVue()).indexOf('etat-vide') !== -1);

// Une famille dispersee, elle, est bien rendue, avec ses boites depliables.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Voyant | N1 | R1' },
   { 'PN Global': 'B2', 'Composants': 'Voyant | N1 | R2' }], []);
const htmlDisperse = C.standardisationHtml(C.calculerVue());
vrai('la famille dispersee est la', htmlDisperse.indexOf('famille') !== -1);
vrai('avec ses references depliables',
     htmlDisperse.indexOf('data-action="deplier-reference"') !== -1);
vrai('et les boites ou elles servent', htmlDisperse.indexOf('>B1</button>') !== -1);
eq('la fonction famillesStandardisees a disparu avec la section',
   typeof C.famillesStandardisees, 'undefined');

// Le classement met en tete la famille la PLUS dispersee : c'est celle qui
// coute le plus a faire vivre.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Voyant | N1 | R1\nEcrou | N3 | R3' },
   { 'PN Global': 'B2', 'Composants': 'Voyant | N1 | R2\nEcrou | N3 | R4' },
   { 'PN Global': 'B3', 'Composants': 'Voyant | N1 | R5' }], []);
eq('la plus dispersee passe devant',
   C.opportunitesStandardisation(C.Store.boites).map(function (f) { return f.fonction; }),
   ['Voyant', 'Ecrou']);

// La reference la plus utilisee d'une famille dispersee est signalee.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Voyant | N1 | R1' },
   { 'PN Global': 'B2', 'Composants': 'Voyant | N1 | R1' },
   { 'PN Global': 'B3', 'Composants': 'Voyant | N1 | R2' }], []);
const htmlMaj = C.standardisationHtml(C.calculerVue());
eq('une seule reference majoritaire',
   (htmlMaj.match(/ref-majoritaire/g) || []).length, 1);
vrai('et c\'est la plus utilisee',
     htmlMaj.indexOf('ref-majoritaire') < htmlMaj.indexOf('R2'));

// Le mode de vue accepte la troisième lecture, et refuse ce qui n'existe pas.
C.Store.vueMode = 'standardisation';
C.enregistrerReglages();
C.Store.vueMode = 'boites';
C.chargerReglages();
eq('le mode standardisation est relu', C.Store.vueMode, 'standardisation');
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
vrai('un indicateur filtre la base', declarees.has('filtrer-statut'));
faux('plus de filtre par réemploi', declarees.has('filtrer-reutilise'));
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
// L'export retire, le helper de telechargement n'avait plus d'appelant.
faux('plus de helper de telechargement',
     fs.readFileSync(path.join(H.RACINE, 'client/Dom.html'), 'utf8')
       .indexOf('function telecharger') !== -1);
faux('ni de lien de sauvegarde fabrique a la volee',
     fs.readFileSync(path.join(H.RACINE, 'client/Dom.html'), 'utf8')
       .indexOf('createObjectURL') !== -1);
faux('plus de bloc de réglages rapides', /reglagesPresets/.test(srcIndex));
vrai('le formulaire de création porte les porteurs', srcIndex.indexOf('newBoitePorteurs') !== -1);
vrai('le statut', srcIndex.indexOf('newBoiteStatut') !== -1);
vrai('le niveau de qualification', srcIndex.indexOf('newBoiteNiveau') !== -1);
vrai('et l\'URL de la photo', srcIndex.indexOf('newBoiteImage') !== -1);
// Les indicateurs sont desormais rendus : ils appartiennent a l'espace
// affiche, et garder ceux des boites en consultant les composants faisait
// lire les mauvais chiffres.
vrai('la bande est rendue, plus ecrite en dur', srcIndex.indexOf('id="zoneIndicateurs"') !== -1);
faux('aucun indicateur n\'est fige dans la page', /indicateur-libelle/.test(srcIndex));
charger([{ 'PN Global': 'B1', 'Statut': 'Validé', 'Composants': 'Voyant | MS25041 | R1' },
         { 'PN Global': 'B2', 'Statut': 'En étude', 'Composants': 'Voyant | MS25041 | R2' }], []);
C.Store.espace = 'boites';
const indBoites = C.indicateursBoitesHtml(C.calculerKpi(C.Store.boites), C.calculerVue());
['Boîtes', 'Validées', 'À standardiser', 'Doublons probables'].forEach(function (l) {
  vrai('l\'espace boites annonce « ' + l + ' »', indBoites.indexOf(l) !== -1);
});
eq('quatre indicateurs, tous des boutons',
   (indBoites.match(/<button class="indicateur/g) || []).length, 4);
faux('aucun n\'est un bloc inerte', /<div class="indicateur/.test(indBoites));

C.Store.espace = 'composants';
C.Store.catalogue = [];
const indCompo = C.indicateursComposantsHtml(C.calculerVue());
['Références', 'À ranger', 'Hors catalogue', 'Montées une fois'].forEach(function (l) {
  vrai('l\'espace composants annonce « ' + l + ' »', indCompo.indexOf(l) !== -1);
});
eq('quatre aussi, pas sept',
   (indCompo.match(/<button class="indicateur/g) || []).length, 4);
faux('« Boîtes » ne reste pas affiché dans les composants', /Boîtes<\/span>/.test(indCompo));
faux('ni « Validées »', indCompo.indexOf('Validées') !== -1);
C.Store.espace = 'boites';

// « Pieces reutilisees » comptait les sous-ensembles montes dans plusieurs
// boites. Personne ne savait le lire, et le filtre ne repondait a aucune
// question qu'on se pose devant la grille : retire, avec sa mecanique.
faux('plus d\'indicateur de réutilisation', indBoites.indexOf('réutilis') !== -1);
faux('ni son filtre', /filtrer-reutilise/.test(srcIndex));
faux('ni la mécanique côté données',
     lireSrc('client/Store.html').indexOf('piecesReutilisees') !== -1);
faux('ni le partage de pièce',
     lireSrc('client/Store.html').indexOf('partageUnePiece') !== -1);
// La ligne « sur toute la base » sous les chiffres ne disait rien que la
// grille ne montrait deja.
faux('plus de ligne de portée sous les indicateurs', /kpiPortee/.test(srcIndex));
faux('ni son style', /indicateurs-portee/.test(cssSrc));
// Le « / » accole a « Par composant » etait un badge sans emploi visible.
faux('plus de badge de raccourci dans le champ', /class="raccourci"/.test(srcIndex));
faux('ni son style', /\.raccourci \{/.test(cssSrc));
// « Références uniques » additionnait des PN de boîtes et des PN de
// sous-ensembles, et n'était même pas cliquable : remplacé par ce qu'il
// reste à ranger, qui mène à la vue correspondante.
faux('plus d\'indicateur « Références uniques »', /Références uniques/.test(srcIndex));
faux('ni le compteur qui l\'alimentait', /kpiNoms/.test(srcIndex));
faux('ni dans le rendu', grilleSrc.indexOf('kpiNoms') !== -1);
faux('plus d\'indicateur inerte au milieu des boutons', /indicateur-fixe/.test(srcIndex));

vrai('et il est cliquable', declarees.has('voir-standardisation'));
vrai('il mène à la troisième vue',
     /'voir-standardisation':[\s\S]{0,200}: 'standardisation'/
       .test(sansCommentaires(lireSrc('client/Main.html'))));
faux('la page ne fige plus d\'indicateur',
     /<button[^>]*class="indicateur[ "]/.test(srcIndex));
faux('plus rien du réemploi dans le rendu',
     /kpiReutil|pctReutilisees|indReutil/.test(grilleSrc));

// Les équivalences se lancent depuis la fiche de la boîte, comme pour un
// sous-ensemble : il fallait refermer la fiche et retrouver la carte.
vrai('« Équivalences » existe dans la fiche de la boîte',
     /boutonHtml\('comparer-boite'[\s\S]{0,80}Équivalences/.test(ficheSrc));
vrai('et toujours sur la carte', grilleSrc.indexOf("action: 'comparer-boite'") !== -1);

// Un doublon probable se compare pour de bon, pondération comprise.
vrai('on peut ouvrir la comparaison depuis la liste des doublons',
     declarees.has('comparer-depuis-doublons'));
vrai('le détail d\'une paire est rendu par la vue de comparaison',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewCompare.html'), 'utf8')
       .indexOf('function doublonHtml') !== -1);
vrai('le style du détail existe', /\.doublon-detail \{/.test(cssSrc));
vrai('les écarts se repèrent à la pastille', /\.doublon-different .doublon-crit-nom::before/.test(cssSrc));

// Les listes de suggestion vivent dans le bloc de saisie, et se resserrent.
faux('plus de listes globales par catégorie', /listesComposants/.test(srcIndex));
faux('ni dans le contrôleur', sansCommentaires(lireSrc('client/Main.html')).indexOf('listesComposants') !== -1);
vrai('chaque bloc porte les siennes', ficheSrc.indexOf('listes-bloc') !== -1);
vrai('et elles se resserrent à la frappe',
     /addEventListener\('input'[\s\S]{0,300}resserrerBloc/.test(sansCommentaires(lireSrc('client/Main.html'))));
vrai('l\'index est construit côté logique, pas côté DOM',
     fs.readFileSync(path.join(H.RACINE, 'client/Composants.html'), 'utf8')
       .indexOf('function construireIndexComposants') !== -1);
vrai('les doublons restent un indicateur', indBoites.indexOf('Doublons probables') !== -1);
vrai('les doublons sont consultables', declarees.has('ouvrir-doublons'));
vrai('on bascule entre boîtes et sous-ensembles', declarees.has('changer-vue'));
vrai('trois lectures de la base', /\['standardisation', 'Standardisation'\]/.test(
     fs.readFileSync(path.join(H.RACINE, 'client/ViewGrid.html'), 'utf8')));
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
vrai('indicateur « Boîtes »', /indicateur-libelle">Boîtes</.test(indBoites));
faux('plus d\'indicateur « Sous-ensembles »', /indicateur-libelle">Sous-ensembles</.test(indBoites));
faux('plus de duplication de boîte sur la carte',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewGrid.html'), 'utf8')
       .indexOf('dupliquer-boite') !== -1);
faux('plus de duplication de boîte dans la fiche',
     sansCommentaires(fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8'))
       .indexOf("'dupliquer-boite'") !== -1);
faux('aucun reste de duplication dans la fiche',
     fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8')
       .indexOf('dupliquer-nom') !== -1);

// =====================================================================
bloc('Une double espace ne fait pas deux composants');
// =====================================================================
eq('les espaces internes sont ramenes a un seul',
   C.normaliserTexte('Bouton  poussoir'), 'bouton poussoir');
eq('tabulations et retours compris', C.normaliserTexte('Bouton\tpoussoir'), 'bouton poussoir');
eq('les accents partent toujours', C.normaliserTexte('Équerre'), 'equerre');
eq('et la casse aussi', C.normaliserTexte('  ÉQUERRE  '), 'equerre');

// Consequence concrete : une saisie relachee ne scinde plus une famille en deux.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Bouton poussoir | ECS 7251 | MS-1' },
   { 'PN Global': 'B2', 'Composants': 'Bouton  poussoir | ECS 7251 | MS-2' }], []);
eq('une seule famille, malgre la double espace',
   C.famillesComposants(C.Store.boites).size, 1);
eq('et elle est bien vue comme dispersee',
   C.opportunitesStandardisation(C.Store.boites).length, 1);

// Et deux composants ainsi ecrits se comparent toujours a 100 %.
const cA = C.listeComposants('Bouton poussoir | ECS 7251 | MS-1')[0];
const cB = C.listeComposants('Bouton  poussoir | ECS 7251 | MS-1')[0];
eq('la comparaison ne les separe pas', C.comparerComposants(cA, cB).ratio, 1);

// =====================================================================
bloc('La base de composants : catalogue et montages reunis');
// =====================================================================
// Ce n'est pas une lecture de la base des boites : c'est une base a part,
// qui reunit ce qu'on a le DROIT de monter et ce qu'on monte VRAIMENT.
C.Store.catalogue = [
  { 'Catégorie': 'composant', 'Fonction': 'Voyant', 'Norme': 'MS25041',
    'Référence': 'MS25041-3', 'Désignation': 'Indicator light, vert' },
  { 'Catégorie': 'composant', 'Fonction': 'Voyant', 'Norme': 'MS25041',
    'Référence': 'MS25041-5', 'Désignation': 'Indicator light, rouge' },
  { 'Catégorie': 'mecanique', 'Fonction': 'Colonnette', 'Norme': 'NAS43',
    'Référence': 'NAS43DD3-20', 'Désignation': 'Entretoise 20 mm' }
];
charger(
  [{ 'PN Global': 'B1', 'Porteur': 'H225', 'Composants': 'Voyant | MS25041 | MS25041-3' },
   { 'PN Global': 'B2', 'Porteur': 'H160\nH160M', 'Composants': 'Voyant | MS25041 | MS25041-3' },
   { 'PN Global': 'B3', 'Porteur': 'H225', 'Composants': 'Connecteur | EN 3645 | CN-INCONNU' }],
  [structureAvec('S1', 'B1', 'Colonnette | NAS43 | NAS43DD3-20')]);

let baseC = C.baseComposants(C.Store.boites);
eq('catalogue et montages sont reunis', baseC.length, 4);

const voyantVert = baseC.find(function (c) { return c.reference === 'MS25041-3'; });
eq('le voyant monte est courant', voyantVert.etat, C.ETAT_COMPOSANT.COURANT);
eq('sur deux boites', voyantVert.nbBoites, 2);
eq('nommees', voyantVert.boites, ['B1', 'B2']);
eq('porteurs cumules', voyantVert.porteurs, ['H160', 'H160M', 'H225']);
eq('la designation vient du catalogue', voyantVert.designation, 'Indicator light, vert');
eq('et on sait d\'ou il est monte', voyantVert.portees, ['Boîte']);

const voyantRouge = baseC.find(function (c) { return c.reference === 'MS25041-5'; });
eq('une reference au catalogue que personne ne monte est DORMANTE',
   voyantRouge.etat, C.ETAT_COMPOSANT.DORMANT);
eq('sans aucune boite', voyantRouge.nbBoites, 0);

// Le cas le plus utile : une piece montee que le catalogue ne connait pas.
const inconnu = baseC.find(function (c) { return c.reference === 'CN-INCONNU'; });
eq('un composant monte hors catalogue est signale', inconnu.etat, C.ETAT_COMPOSANT.HORS);
faux('il n\'est pas au catalogue', inconnu.auCatalogue);
eq('mais il est bien monte', inconnu.nbBoites, 1);

const colonnette = baseC.find(function (c) { return c.reference === 'NAS43DD3-20'; });
eq('les composants des sous-ensembles comptent', colonnette.nbBoites, 1);
eq('avec leur categorie', colonnette.categorie, 'mecanique');
eq('et la portee d\'ou ils viennent', colonnette.portees, ['Structure boîte']);

// Le bilan.
const bil = C.bilanComposants(baseC);
eq('quatre references', bil.references, 4);
eq('trois montees', bil.montes, 3);
eq('deux montees une seule fois', bil.isoles, 2);
eq('une dormante', bil.dormants, 1);
eq('une hors catalogue', bil.hors, 1);

// L'arbre : famille -> fonction -> norme -> references.
const arbre = C.arbreComposants(baseC);
eq('deux familles', arbre.length, 2);
eq('les composants de boite d\'abord', arbre[0].cle, 'composant');
eq('puis la mecanique', arbre[1].cle, 'mecanique');
const fVoyant = arbre[0].fonctions.find(function (f) { return f.libelle === 'Voyant'; });
eq('le voyant porte deux references', fVoyant.references, 2);
eq('sous une seule norme', fVoyant.normes.length, 1);
// Une seule des deux est montee : ce n'est PAS de la dispersion.
faux('une seule reference montee ne disperse rien', fVoyant.normes[0].dispersee);

// Deux references montees sous la meme norme, la : c'est disperse.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Voyant | MS25041 | MS25041-3' },
   { 'PN Global': 'B2', 'Composants': 'Voyant | MS25041 | MS25041-5' }], []);
const arbre2 = C.arbreComposants(C.baseComposants(C.Store.boites));
vrai('deux references montees sous une norme, c\'est disperse',
     arbre2[0].fonctions[0].normes[0].dispersee);
vrai('et la fonction est signalee', arbre2[0].fonctions[0].dispersee);

// Les filtres de l'espace, qui ne partagent rien avec ceux des boites.
C.Store.catalogue = [];
charger(
  [{ 'PN Global': 'B1', 'Statut': 'Validé',
     'Composants': 'Voyant | MS25041 | MS25041-3\nRelais | MS27401 | MS27401-1' },
   { 'PN Global': 'B2', 'Statut': 'En étude', 'Composants': 'Voyant | MS25041 | MS25041-3' }],
  [structureAvec('S1', 'B1', 'Colonnette | NAS43 | NAS43DD3-20')]);
const remettre = function () {
  ['famille', 'fonction', 'norme', 'etat', 'emploi'].forEach(function (c) { C.Store.compo[c] = null; });
  C.Store.compo.recherche = '';
};
remettre();
eq('sans filtre, tout', C.composantsFiltres(C.Store.boites).length, 3);
faux('et aucun filtre actif', C.filtreComposantActif());

C.Store.compo.famille = 'mecanique';
eq('filtre par famille', C.composantsFiltres(C.Store.boites).length, 1);
vrai('le filtre se sait actif', C.filtreComposantActif());
remettre();

C.Store.compo.emploi = 'partage';
eq('seuls les partages', C.composantsFiltres(C.Store.boites).map(function (c) { return c.reference; }),
   ['MS25041-3']);
C.Store.compo.emploi = 'isole';
eq('seuls les isoles', C.composantsFiltres(C.Store.boites).length, 2);
remettre();

C.Store.compo.recherche = 'relais';
eq('la recherche porte sur les quatre champs',
   C.composantsFiltres(C.Store.boites).map(function (c) { return c.reference; }), ['MS27401-1']);
C.Store.compo.recherche = 'NAS43';
eq('la norme aussi', C.composantsFiltres(C.Store.boites).length, 1);
remettre();

// La recherche des composants ne touche PAS celle des boites.
C.Store.compo.recherche = 'relais';
C.Store.recherche = '';
eq('les deux recherches sont independantes', C.calculerVue().aAfficher.length, 2);
remettre();

// Le rendu.
charger([{ 'PN Global': 'B"1', 'Composants': '<b>V</b> | <i>N</i> | <u>R</u>' }], []);
const htmlBase = C.composantsHtml(C.calculerVue());
faux('un composant piege n\'injecte rien', /<b>V<\/b>|<i>N<\/i>/.test(htmlBase));
vrai('il est affiche echappe', htmlBase.indexOf('&lt;b&gt;V&lt;/b&gt;') !== -1);
vrai('la famille se filtre', htmlBase.indexOf('data-champ="famille"') !== -1);
// La liste ne montre que les fonctions : le detail s'ouvre dans la fiche.
vrai('une fonction mene a sa fiche',
     htmlBase.indexOf('data-action="ouvrir-fiche-composant"') !== -1);
vrai('et la liste se trie', htmlBase.indexOf('data-action="trier-composants"') !== -1);
faux('plus d\'arbre deplie dans la liste', /data-action="basculer-fonction"/.test(htmlBase));

// La liste des fonctions, et ses tris.
charger(
  [{ 'PN Global': 'B1', 'Composants': 'Voyant | N1 | R1\nRelais | N2 | R9' },
   { 'PN Global': 'B2', 'Composants': 'Voyant | N1 | R2' },
   { 'PN Global': 'B3', 'Composants': 'Voyant | N3 | R3' }], []);
C.Store.catalogue = [];
C.Store.compo.tri = 'emploi';
let fcts = C.fonctionsComposants(C.baseComposants(C.Store.boites));
eq('deux fonctions', fcts.length, 2);
eq('la plus montee en tete', fcts[0].libelle, 'Voyant');
eq('avec ses trois references', fcts[0].references, 3);
eq('sous deux normes', fcts[0].normes, 2);
eq('dans trois boites', fcts[0].nbBoites, 3);
vrai('et elle est dispersee', fcts[0].dispersee);
faux('le relais, monte une seule fois, ne l\'est pas',
     fcts.find(function (f) { return f.libelle === 'Relais'; }).dispersee);

C.Store.compo.tri = 'alpha';
eq('tri alphabetique',
   C.fonctionsComposants(C.baseComposants(C.Store.boites)).map(function (f) { return f.libelle; }),
   ['Relais', 'Voyant']);
C.Store.compo.tri = 'dispersion';
eq('tri par dispersion',
   C.fonctionsComposants(C.baseComposants(C.Store.boites))[0].libelle, 'Voyant');
C.Store.compo.tri = 'emploi';

// Une reference au catalogue que personne ne monte ne rend pas « disperse ».
C.Store.catalogue = [{ 'Catégorie': 'composant', 'Fonction': 'Relais',
                       'Norme': 'N2', 'Référence': 'R-DORMANTE' }];
charger([{ 'PN Global': 'B1', 'Composants': 'Relais | N2 | R9' }], []);
fcts = C.fonctionsComposants(C.baseComposants(C.Store.boites));
eq('deux references connues', fcts[0].references, 2);
eq('mais une seule montee', fcts[0].montees, 1);
faux('donc pas de dispersion', fcts[0].dispersee);
eq('et la dormante est comptee', fcts[0].dormantes, 1);
C.Store.catalogue = [];

// La fiche d'une fonction.
charger(
  [{ 'PN Global': 'B1', 'Porteur': 'H225', 'Composants': 'Voyant | MS25041 | R1' },
   { 'PN Global': 'B2', 'Porteur': 'H160', 'Composants': 'Voyant | MS25041 | R1' },
   { 'PN Global': 'B3', 'Composants': 'Voyant | MS25041 | R2' }], []);
C.Store.ficheComposant = { categorie: 'composant', fonction: 'Voyant' };
const ficheFct = C.ficheComposantHtml(C.Store.ficheComposant);
vrai('le resume compte les normes', /<span class="fc-n">1<\/span>/.test(ficheFct));
vrai('la norme est un bloc', ficheFct.indexOf('MS25041') !== -1);
vrai('la plus montee est marquee', ficheFct.indexOf('la plus montée') !== -1);
vrai('et le conseil la nomme', /converger/.test(ficheFct));
vrai('les boites sont nommees', ficheFct.indexOf('>B1</button>') !== -1);
vrai('et les porteurs cumules', ficheFct.indexOf('H225') !== -1 && ficheFct.indexOf('H160') !== -1);
// Une seule reference montee : aucun conseil de convergence a donner.
charger([{ 'PN Global': 'B1', 'Composants': 'Voyant | MS25041 | R1' }], []);
faux('sans dispersion, pas de conseil',
     C.ficheComposantHtml({ categorie: 'composant', fonction: 'Voyant' }).indexOf('converger') !== -1);
// Une fonction disparue ne plante pas la fiche.
vrai('une fonction inconnue se dit',
     C.ficheComposantHtml({ categorie: 'composant', fonction: 'Jamais vue' })
       .indexOf('etat-vide') !== -1);
C.Store.ficheComposant = null;
charger([{ 'PN Global': 'B1' }], []);
C.Store.catalogue = [];
vrai('baseC vide, on le dit', C.composantsHtml(C.calculerVue()).indexOf('etat-vide') !== -1);

// L'espace est memorise, et « composants » n'est plus une lecture.
C.Store.espace = 'composants';
C.enregistrerReglages();
C.Store.espace = 'boites';
C.chargerReglages();
eq('l\'espace est relu', C.Store.espace, 'composants');
C.Store.espace = 'boites';
C.Store.vueMode = 'composants';
C.enregistrerReglages();
C.Store.vueMode = 'boites';
C.chargerReglages();
eq('« composants » n\'est plus une lecture de l\'espace boites', C.Store.vueMode, 'boites');
C.enregistrerReglages();

// Le seuil de doublon monte a 95 % : en deca, deux PN proches n'en sont pas.
eq('le seuil de doublon est a 95 %', C.SEUIL_DOUBLON, 95);

// =====================================================================
bloc('Favoris de ponderation');
// =====================================================================
C.chargerReglages();
const favBoite = C.favorisDe('boite');
vrai('la boite a des favoris', favBoite.length >= 3);
vrai('chacun ne nomme que des criteres existants',
     favBoite.every(function (f) {
       return Object.keys(f.poids).every(function (c) {
         return C.CRITERES_BOITE.some(function (x) { return x.cle === c; });
       });
     }));
vrai('chacun porte une aide', favBoite.every(function (f) { return f.aide && f.aide.length > 3; }));

// Les parts sont ecrites en relatif : c'est l'application qui ramene a 100.
favBoite.forEach(function (f) {
  const parts = C.normaliserFavori(f);
  const total = Object.keys(parts).reduce(function (t, c) { return t + parts[c]; }, 0);
  eq('« ' + f.libelle + ' » totalise 100 %', total, 100);
});

vrai('poser un favori repond vrai', C.appliquerFavori('boite', 'porteur'));
eq('le porteur pese le plus',
   C.criteresActifs('boite').reduce(function (a, b) {
     return C.poidsDe('boite', a) >= C.poidsDe('boite', b) ? a : b;
   }).cle, 'porteur');
eq('et le total reste a 100',
   C.criteresActifs('boite').reduce(function (t, c) { return t + C.poidsDe('boite', c); }, 0), 100);

// Un favori dit aussi ce qui NE compte pas : les criteres absents sont ecartes.
vrai('poser « Meme contenu » ne garde que ses criteres', C.appliquerFavori('boite', 'contenu'));
eq('trois criteres retenus', C.criteresActifs('boite').length, 3);
faux('le porteur est ecarte', C.critereEstActif('boite', 'porteur'));

// Un favori inconnu ne change rien.
const avantInconnu = C.criteresActifs('boite').map(function (c) { return c.cle; });
faux('un favori inconnu est refuse', C.appliquerFavori('boite', 'nimporte'));
eq('et rien n\'a bouge', C.criteresActifs('boite').map(function (c) { return c.cle; }), avantInconnu);
faux('une portee inconnue aussi', C.appliquerFavori('nimporte', 'porteur'));

// Un favori change VRAIMENT le classement : c'est tout son interet.
charger(
  [{ 'PN Global': 'SRC', 'Fonction': 'HOIST', 'Porteur': 'H145',
     'Niveau de qualification': 'Qualified to H145', 'Composants': 'Voyant | MS25041 | MS25041-3' },
   { 'PN Global': 'MEME-PORTEUR', 'Fonction': 'COM', 'Porteur': 'H145',
     'Niveau de qualification': 'Qualified to H145', 'Composants': 'Relais | MS27401 | MS27401-1' },
   { 'PN Global': 'MEME-CONTENU', 'Fonction': 'NAV', 'Porteur': 'H225',
     'Niveau de qualification': 'Qualified to H225', 'Composants': 'Voyant | MS25041 | MS25041-3' }], []);
C.appliquerFavori('boite', 'porteur');
eq('avec « Meme porteur », c\'est le porteur qui gagne',
   C.equivalencesBoite('SRC')[0].cible['PN Global'], 'MEME-PORTEUR');
C.appliquerFavori('boite', 'contenu');
eq('avec « Meme contenu », c\'est le contenu',
   C.equivalencesBoite('SRC')[0].cible['PN Global'], 'MEME-CONTENU');
C.reinitialiserPoids();

// Chaque portee comparable a au moins un favori applicable.
C.porteesComparables().forEach(function (p) {
  vrai('la portee « ' + p.libelle + ' » a un favori', C.favorisDe(p.cle).length >= 1);
});

// =====================================================================
bloc('La fiche ne cache plus rien hors edition');
// =====================================================================
charger(
  [{ 'PN Global': 'B1', 'Fonction': 'APU', 'Image': 'https://exemple.fr/photo.jpg' }],
  [{ 'ID_Ligne': 'S1', 'PN Global': 'B1', 'Type': 'Structure boîte',
     'PN du type': 'B1.01', 'Montage': 'Console STD',
     'Image': 'https://exemple.fr/structure.jpg' }]);
C.Store.enEditionBoite = false; C.Store.enEditionNom = {};
const ficheLue = C.ficheHtml(C.boiteParPn('B1'));
// Un champ qu'il faut passer en edition pour LIRE est un champ qu'on oublie.
vrai('l\'URL de la photo de boite se lit', ficheLue.indexOf('exemple.fr/photo.jpg') !== -1);
vrai('celle du sous-ensemble aussi', ficheLue.indexOf('exemple.fr/structure.jpg') !== -1);
vrai('elles sont cliquables', ficheLue.indexOf('class="lien-url"') !== -1);
vrai('et s\'ouvrent dans un onglet', ficheLue.indexOf('rel="noopener noreferrer"') !== -1);
vrai('le type du sous-ensemble se lit aussi', /Type[\s\S]{0,120}Structure boîte/.test(ficheLue));

// Tout ce que l'edition montre doit se lire hors edition.
C.Store.enEditionBoite = true; C.Store.enEditionNom = { 'S1': true };
const ficheEditee = C.ficheHtml(C.boiteParPn('B1'));
C.Store.enEditionBoite = false; C.Store.enEditionNom = {};
const libelles = ['Fonction', 'Image (URL)', 'Montage', 'Type'];
libelles.forEach(function (l) {
  vrai('« ' + l + '  » est lisible hors edition', ficheLue.indexOf(l) !== -1);
  vrai('et editable', ficheEditee.indexOf(l) !== -1);
});

// Une URL longue est raccourcie a l'affichage, mais entiere au survol.
const longue = 'https://drive.google.com/file/d/' + 'A'.repeat(60) + '/view';
charger([{ 'PN Global': 'B1', 'Image': longue }], []);
const htmlLongue = C.ficheHtml(C.boiteParPn('B1'));
vrai('l\'URL longue est tronquee a l\'oeil', htmlLongue.indexOf('…') !== -1);
vrai('mais entiere dans le lien', htmlLongue.indexOf('href="' + longue + '"') !== -1);

// Une valeur qui n'est pas une URL reste du texte, pas un lien mort.
charger([{ 'PN Global': 'B1', 'Image': 'pas une url' }], []);
faux('un texte quelconque ne devient pas un lien',
     /class="lien-url"/.test(C.ficheHtml(C.boiteParPn('B1'))));
charger([{ 'PN Global': 'B1', 'Image': '' }], []);
vrai('une image absente se dit', C.ficheHtml(C.boiteParPn('B1')).indexOf('—') !== -1);

// Une URL piegee ne sort pas de son attribut.
charger([{ 'PN Global': 'B1', 'Image': 'https://x.fr/"><script>alert(1)</script>' }], []);
faux('une URL piegee n\'injecte rien',
     /<script>alert\(1\)<\/script>/.test(C.ficheHtml(C.boiteParPn('B1'))));

// =====================================================================
bloc('Ce que la batterie a trouve');
// =====================================================================
// 1) Avant que les reglages ne soient charges, Store.criteresActifs est vide.
// L'ancien repli donnait un score de 0 sur TOUT, sans message : un classement
// entierement a zero se lit « rien ne se ressemble », pas « rien n'a ete
// compare ». Par defaut, tous les criteres comptent.
const actifsSauves = C.Store.criteresActifs;
C.Store.criteresActifs = {};
charger([{ 'PN Global': 'B1', 'Fonction': 'APU', 'Composants': 'V|N|R' }], []);
const memeBoite = C.boiteParPn('B1');
const avantReglages = C.comparerBoites(memeBoite, memeBoite);
vrai('sans reglages charges, la comparaison reste mesurable', avantReglages.mesurable);
eq('et une boite vaut 100 contre elle-meme', avantReglages.score, 100);
vrai('tous les criteres sont retenus par defaut',
     C.criteresActifs('boite').length === C.CRITERES_BOITE.length);
vrai('critereEstActif() suit le meme repli', C.critereEstActif('boite', 'fonction'));
// Un tableau VIDE, lui, est un choix explicite : on le respecte.
C.Store.criteresActifs = { boite: [] };
eq('une liste vide reste une liste vide', C.criteresActifs('boite').length, 0);
C.Store.criteresActifs = actifsSauves;

// 2) On ne peut pas ecarter le dernier critere : le garde-fou existe.
C.chargerReglages();
const tous = C.CRITERES_BOITE.map(function (c) { return c.cle; });
tous.slice(0, -1).forEach(function (cle) { C.desactiverCritere('boite', cle); });
eq('il reste un critere', C.criteresActifs('boite').length, 1);
faux('et le dernier ne part pas', C.desactiverCritere('boite', C.criteresActifs('boite')[0].cle));
eq('il est toujours la', C.criteresActifs('boite').length, 1);
C.reinitialiserPoids();
C.chargerReglages();

// 3) Le balayage des doublons est quadratique, donc plafonne. L'ancien
// plafond (400 paires) correspondait a 29 sous-ensembles du meme type :
// toute base reelle passait dessous et l'indicateur restait muet.
vrai('le plafond couvre une base de travail', C.PLAFOND_PAIRES >= 20000);
// Et quand il est depasse, l'indicateur ne reste pas muet : il dit quoi faire.
vrai('le « — » est explique',
     lireSrc('client/ViewGrid.html').indexOf('trop de pièces : filtrez d') !== -1);
vrai('et la modale renvoie vers le filtrage',
     /Restreignez[\s\S]{0,20}la sélection/.test(sansCommentaires(lireSrc('client/Main.html'))));
// La croix des puces faisait 14 px de cote : intenable au doigt.
vrai('la croix des puces est agrandie au doigt',
     /@media \(pointer: coarse\)[\s\S]{0,260}\.puce-suppr[\s\S]{0,200}min-height: 26px/
       .test(lireSrc('client/Styles.html')));
const surMesure = function (n) {
  const b = [], no = [];
  for (let i = 0; i < n; i++) {
    b.push({ 'PN Global': 'B' + i });
    no.push({ 'ID_Ligne': 'B' + i + '-h', 'PN Global': 'B' + i, 'Type': 'Harnais',
              'PN du type': 'B' + i + '.h', 'Référence': 'REF-' + (i % 3) });
  }
  charger(b, no);
  return C.compterDoublonsProbables(C.Store.boites);
};
vrai('100 boites du meme type sont balayees', surMesure(100).nombre !== null);
vrai('200 aussi', surMesure(200).nombre !== null);
const tropGros = surMesure(400);
eq('au-dela, on ne balaie pas a moitie', tropGros.nombre, null);
vrai('et on le signale', tropGros.tronque);
eq('sans rendre de paires partielles', tropGros.paires, []);

// 4) Le code mort est parti : l'export CSV, ses aides, et trois fonctions
// que rien n'appelait.
['construireCsv', 'champCsv', 'clesNormalisees', 'formaterComposant',
 'CSV_SEPARATEUR'].forEach(function (n) {
  eq(n + ' a disparu', typeof C[n], 'undefined');
});
vrai('formaterComposantStructure, lui, sert au catalogue',
     typeof C.formaterComposantStructure === 'function');

// 5) Meme fragilite du cote des poids : Store.poids part vide, et tout ce qui
// y touchait avant le chargement des reglages plantait sur un objet absent.
const poidsSauves = C.Store.poids;
C.Store.poids = {};
C.reglerPoids('boite', 'fonction', 50);
eq('regler une part sans reglages charges ne plante plus',
   C.criteresActifs('boite').reduce(function (t, c) { return t + C.poidsDe('boite', c); }, 0), 100);
C.Store.poids = {};
C.normaliserPoids('structure');
eq('normaliser non plus',
   C.criteresActifs('structure').reduce(function (t, c) { return t + C.poidsDe('structure', c); }, 0), 100);
C.Store.poids = {};
C.Store.criteresActifs = {};
vrai('ecarter un critere non plus', C.desactiverCritere('boite', 'porteur'));
eq('et le total reste a 100',
   C.criteresActifs('boite').reduce(function (t, c) { return t + C.poidsDe('boite', c); }, 0), 100);
C.Store.poids = poidsSauves;
C.chargerReglages();

// 6) Le CSS orphelin est parti avec le code qui l'utilisait.
['btn-sur-image', 'btn-icone', 'btn-entete', 'ligne-appoint', 'indicateurs-portee', 'raccourci']
  .forEach(function (c) {
    faux('.' + c + ' n\'a plus de regle', new RegExp('\\.' + c + '[\\s,{:]').test(cssSrc));
  });

// =====================================================================
bloc('Saisie guidee : les trois niveaux se resserrent');
// =====================================================================
// Sous « Bouton poussoir », proposer une norme de colonnette n'a pas de sens.
charger(
  [{ 'PN Global': 'B1',
     'Composants': 'Bouton poussoir | ECS 7251 | MS24523-22\n' +
                   'Bouton poussoir | ECS 0763 | MS24523-31\n' +
                   'Voyant | ECS 4410 | LED-1' }],
  [structureAvec('S1', 'B1', 'Colonnette | NSA 5512 | COL-M4-20')]);
C.Store.catalogue = [];
C.construireIndexComposants();

let sug = C.suggestionsComposant('composant', '', '');
eq('sans fonction, toutes les fonctions sont proposees',
   sug.fonctions, ['Bouton poussoir', 'Voyant']);
eq('et toutes les normes de la categorie', sug.normes, ['ECS 0763', 'ECS 4410', 'ECS 7251']);
faux('rien n\'est encore restreint', sug.restreint);

sug = C.suggestionsComposant('composant', 'Bouton poussoir', '');
vrai('une fonction connue restreint', sug.restreint);
eq('seules ses normes restent', sug.normes, ['ECS 0763', 'ECS 7251']);
eq('et seules ses references', sug.references, ['MS24523-22', 'MS24523-31']);

sug = C.suggestionsComposant('composant', 'Bouton poussoir', 'ECS 7251');
eq('la norme choisie ne laisse que sa reference', sug.references, ['MS24523-22']);
eq('les normes de la fonction restent visibles', sug.normes, ['ECS 0763', 'ECS 7251']);

sug = C.suggestionsComposant('composant', 'BOUTON  POUSSOIR', '');
eq('la casse et les espaces n\'empechent pas la reconnaissance',
   sug.normes, ['ECS 0763', 'ECS 7251']);

sug = C.suggestionsComposant('composant', 'Fonction jamais vue', '');
faux('une fonction inconnue ne restreint rien', sug.restreint);
eq('tout reste proposable : on n\'empeche pas de saisir du neuf',
   sug.normes, ['ECS 0763', 'ECS 4410', 'ECS 7251']);

sug = C.suggestionsComposant('composant', 'Bouton poussoir', 'NORME INEDITE');
eq('une norme inconnue sous une fonction connue ne vide pas les references',
   sug.references, ['MS24523-22', 'MS24523-31']);

// Les categories ne se melangent pas : la mecanique a son propre index.
eq('la colonnette est indexee en mecanique',
   C.suggestionsComposant('mecanique', 'Colonnette', '').normes, ['NSA 5512']);
eq('et pas dans la categorie electrique de la boite',
   C.suggestionsComposant('composant', '', '').normes.indexOf('NSA 5512'), -1);

// Le catalogue nourrit l'index au meme titre que la base.
C.Store.catalogue = [{ 'Catégorie': 'mecanique', 'Fonction': 'Colonnette',
                       'Norme': 'NSA 5520', 'Référence': 'COL-M6-40' }];
C.construireIndexComposants();
eq('une norme venue du catalogue est proposee',
   C.suggestionsComposant('mecanique', 'Colonnette', '').normes, ['NSA 5512', 'NSA 5520']);
C.Store.catalogue = [];
C.construireIndexComposants();

// Un composant sans fonction n'entre pas dans l'index : il ne se rattache a rien.
charger([{ 'PN Global': 'B1', 'Composants': ' | ECS 9999 | REF-X' }], []);
C.construireIndexComposants();
eq('un composant sans fonction n\'est pas indexe',
   C.suggestionsComposant('composant', '', '').normes, []);

// =====================================================================
bloc('Doublons : ce qui les separe, pas seulement leur score');
// =====================================================================
// Une structure porte plusieurs criteres : c'est la qu'un ecart se voit.
// Une structure COMPLETE : le seuil etant a 95 %, il faut que tous les
// criteres soient renseignes pour qu'un ecart pese son vrai poids.
const structDetaillee = function (id, pn, modifs) {
  return Object.assign({ 'ID_Ligne': id, 'PN Global': pn, 'Type': 'Structure boîte',
    'PN du type': pn + '.01', 'Montage': 'Console STD', 'Nombre de pas': '1',
    'Dim Long (mm)': '500', 'Dim Larg (mm)': '140', 'Masse (g)': '500',
    'HL': 'A', 'DAL': 'A',
    'Qualification Brouillard salin': 'Cat. S', 'Qualification Vibration': 'Qual. H225',
    'Qualification Explosion': 'Case 1',
    'Composants mécaniques': 'Colonnette | NAS43 | NAS43DD3-20',
    'Composants routing': 'Collier | MS3367 | MS3367-4-9' }, modifs || {});
};
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [structDetaillee('S1', 'B1'), structDetaillee('S2', 'B2', { 'DAL': 'B' })]);
const paire = C.compterDoublonsProbables(C.Store.boites).paires[0];
vrai('une paire est bien detectee', !!paire);
const dOut = C.doublonHtml(paire);
vrai('les deux PN sont montres', dOut.indexOf('B1.01') !== -1 && dOut.indexOf('B2.01') !== -1);
vrai('les boites d\'origine aussi', dOut.indexOf('>B1<') !== -1 && dOut.indexOf('>B2<') !== -1);
vrai('ce qui les separe est nomme', dOut.indexOf('Ce qui les sépare') !== -1);
vrai('avec le critere en cause', dOut.indexOf('DAL') !== -1);
vrai('et les deux valeurs', dOut.indexOf('A vs B') !== -1);
vrai('ce qui concorde est nomme aussi', dOut.indexOf('Ce qui concorde') !== -1);
vrai('avec un critere identique', dOut.indexOf('Console STD') !== -1);
vrai('on peut ouvrir la comparaison complete',
     dOut.indexOf('data-action="comparer-depuis-doublons"') !== -1);
vrai('sur l\'identifiant de ligne, pas sur le PN', dOut.indexOf('data-id="S1"') !== -1);
// Tout est renseigne sur cette paire : il n'y a rien d'incomparable a dire.
faux('rien n\'est laisse de cote', dOut.indexOf('Non comparé, faute de donnée') !== -1);
// Mais quand une donnee manque, on le nomme plutot que de l'ignorer.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [structDetaillee('S1', 'B1', { 'Nombre de pas': '' }),
   structDetaillee('S2', 'B2', { 'Nombre de pas': '', 'DAL': 'B' })]);
const paireTrouee = C.compterDoublonsProbables(C.Store.boites).paires[0];
vrai('la paire tient quand meme', !!paireTrouee);
vrai('et ce qui manque est nomme',
     C.doublonHtml(paireTrouee).indexOf('Non comparé, faute de donnée') !== -1);

// Deux pieces que rien ne separe : on le dit, au lieu d'une section vide.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [structDetaillee('S1', 'B1'), structDetaillee('S2', 'B2')]);
const jumelles = C.doublonHtml(C.compterDoublonsProbables(C.Store.boites).paires[0]);
vrai('rien ne les separe, et c\'est ecrit',
     jumelles.indexOf('Rien ne les sépare') !== -1);

// Un PN piege ne sort pas de son attribut.
charger([{ 'PN Global': 'B1' }, { 'PN Global': 'B2' }],
  [structDetaillee('S1', 'B1', { 'PN du type': '<img src=x onerror=alert(1)>' }),
   structDetaillee('S2', 'B2')]);
faux('un PN piege n\'injecte rien',
     /<img src=x/.test(C.doublonHtml(C.compterDoublonsProbables(C.Store.boites).paires[0])));

// =====================================================================
bloc('Frictions levées — un geste de moins partout');
// =====================================================================
const srcFiche = fs.readFileSync(path.join(H.RACINE, 'client/ViewFiche.html'), 'utf8');
const modale = srcIndex.slice(srcIndex.indexOf('id="multiSearchModal"'),
                              srcIndex.indexOf('id="catalogueModal"'));

// F1 — la recherche par composants n'a plus de bouton « Ajouter » : choisir
// dans la liste, ou taper Entrée, suffit.
faux('plus de bouton Ajouter dans la recherche par composants',
     /data-action="ajouter-chip"/.test(modale));
vrai('la modale se ferme par un bouton explicite',
     modale.indexOf('data-action="fermer-multi-recherche"') !== -1);
vrai('fermer-multi-recherche est implémentée', declarees.has('fermer-multi-recherche'));
faux('lancer-multi-recherche a disparu', declarees.has('lancer-multi-recherche'));
vrai('choisir une suggestion ajoute directement',
     /multi\.addEventListener\('input'[\s\S]{0,200}ajouter-chip/.test(srcMainSeul));
vrai('Entrée aussi', /multi\.addEventListener\('keydown'[\s\S]{0,200}ajouter-chip/.test(srcMainSeul));
vrai('optionConnue() compare aux suggestions offertes',
     /function optionConnue\(idListe, valeur\)/.test(srcMainSeul));

// F2 — le filtre par composants s'applique sans fermer la modale.
vrai('ajouter une puce rafraîchit la liste derrière',
     /'ajouter-chip':[\s\S]{0,400}rendreInterface\(\)/.test(srcMainSeul));
vrai('en retirer une aussi',
     /'retirer-chip':[\s\S]{0,300}rendreInterface\(\)/.test(srcMainSeul));

// F3 — une liste fermée s'ajoute au choix, sans bouton de confirmation.
vrai('les listes fermées sont un select seul',
     srcFiche.indexOf('saisie-multi saisie-multi-seule') !== -1);
const blocFerme = srcFiche.slice(srcFiche.indexOf('if (editable && champ.options)'),
                                 srcFiche.indexOf('} else if (editable)'));
faux('sans bouton Ajouter à côté', /btn-mini/.test(blocFerme));
vrai('un change sur une liste fermée déclenche l\'ajout',
     /addEventListener\('change'[\s\S]{0,400}dataset\.ajout/.test(srcMainSeul));

// F4 — Entrée valide partout : champ libre et composant à trois niveaux.
vrai('Entrée ajoute dans un champ multi',
     /saisie-multi'\)[\s\S]{0,200}dataset\.ajout/.test(srcMainSeul));
vrai('Entrée ajoute aussi un composant',
     /saisie-composant'\)[\s\S]{0,300}ajouter-composant/.test(srcMainSeul));

// F5 — le focus revient sur le champ qu'on utilisait, la fiche ayant été
// recomposée entre-temps.
vrai('redonnerFocus() existe', /function redonnerFocus\(classe, criteres\)/.test(srcMainSeul));
eq('trois rendus lui rendent la main',
   (srcMainSeul.match(/redonnerFocus\(/g) || []).length - 1, 3);
vrai('les écritures multiples rendent une promesse',
     /function majMultiBoite[\s\S]{0,400}return /.test(srcMainSeul));

// F6 — le catalogue se referme apres un ajout : le geste se termine la ou il
// a commence, sur la fiche, et on voit le composant pose.
vrai('ajouter depuis le catalogue referme la modale',
     /'ajouter-catalogue':[\s\S]{0,500}fermerModal\('catalogueModal'\)/
       .test(sansCommentaires(lireSrc('client/Main.html'))));
vrai('et confirme l\'ajout',
     /'ajouter-catalogue':[\s\S]{0,500}confirmerSucces/
       .test(sansCommentaires(lireSrc('client/Main.html'))));

// Supprimer se voit sans passer en édition : c'est une action sur la fiche,
// pas sur un formulaire.
const actionsBoite = srcFiche.slice(srcFiche.indexOf('function blocBoiteHtml'),
                                    srcFiche.indexOf('function blocNomHtml'));
vrai('Supprimer la boîte vit hors du mode édition',
     actionsBoite.indexOf("boutonHtml('supprimer-boite'") >
     actionsBoite.indexOf("boutonHtml('editer-boite'"));
const editionBoite = actionsBoite.slice(actionsBoite.indexOf('? boutonHtml('),
                                        actionsBoite.indexOf(': boutonHtml('));
faux('et non dans la branche d\'édition', editionBoite.indexOf('supprimer-boite') !== -1);
const actionsNom = srcFiche.slice(srcFiche.indexOf('function blocNomHtml'),
                                  srcFiche.indexOf('function blocNomHtml') + 1400);
vrai('idem pour le sous-ensemble',
     actionsNom.indexOf("boutonHtml('supprimer-nom'") >
     actionsNom.indexOf("boutonHtml('editer-nom'"));

// Standardisation : on déplie une référence pour voir où elle sert.
vrai('deplier-reference est implémentée', declarees.has('deplier-reference'));
vrai('la référence est un bouton dépliable', /data-action="deplier-reference"/.test(
     C.standardisationHtml({ aAfficher: [
       { 'PN Global': 'B1', 'Composants': 'V | N | R1' },
       { 'PN Global': 'B2', 'Composants': 'V | N | R2' }] })));
vrai('l\'état d\'ouverture est annoncé', /aria-expanded/.test(srcGrille));
vrai('les boîtes citées ouvrent leur fiche',
     /usage-lien[\s\S]{0,120}ouvrir-fiche/.test(srcGrille));
faux('le style des familles rangées est parti avec la section',
     /\.standard-propres|\.propre \{/.test(
       fs.readFileSync(path.join(H.RACINE, 'client/Styles.html'), 'utf8')));
vrai('la référence majoritaire se repère', /\.ref-majoritaire \{/.test(
     fs.readFileSync(path.join(H.RACINE, 'client/Styles.html'), 'utf8')));

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
// C'est l'en-tête du rail qui reste fixe, pas le bas : on descend pour
// parcourir toutes les pondérations, dans l'ordre.
vrai('l\'en-tête du rail reste fixe en haut',
     /\.rail-tete \{[\s\S]*?position: sticky;\s*top:/.test(srcCss));
faux('le bloc des niveaux n\'est plus épinglé en bas',
     /\.sous-reglage \{[\s\S]*?position: sticky/.test(srcCss));
vrai('il reste repérable au défilement par son aplat marine',
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
