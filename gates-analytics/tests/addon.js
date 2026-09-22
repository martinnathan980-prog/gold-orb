/* Batterie de l'add-on : on fait tourner le VRAI Code.gs contre un classeur en
   mémoire, puis on charge la page qu'Apps Script rendrait, dans un vrai
   navigateur. Ce qui est testé ici, c'est la chaîne feuille → serveur → écran. */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const vm = require('vm');
const { construire, chargerServeur, brancherClasseur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleExemple } = require('./feuille-exemple');
const { feuilleGates, entetes: entetesGates, colonne: colonneGates } = require('./feuille-gates');

let reussis = 0;
const echecs = [];
const erreursJS = [];
let sectionCourante = '';
function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail ? ' — ' + detail : ''));
  }
}
function section(t) { sectionCourante = t; console.log('\n— ' + t + ' —'); }

/* L'interrupteur exemple / réel est visible devant un classeur ;
   mais son mécanisme reste : la batterie le manœuvre comme un clic. */
const basculerMode = (pg, mode) => pg.evaluate(m => document.querySelector('#mode-donnees button[data-mode="' + m + '"]').click(), mode);

function serveurSur(valeurs, proprietes, fichiers) {
  const classeur = new Classeur([new Feuille('Données', valeurs)]);
  return { contexte: chargerServeur(classeur, proprietes || {}, fichiers), classeur: classeur };
}

(async () => {
  // =================================================================
  section('Détection des colonnes');
  const { paquet, contexte: ctxPaquet } = construire();
  verifier('le paquet est valide', paquet.ok === true, paquet.message);
  /* Le contrat : ce classeur n'a qu'un onglet visible, « Données », donc un
     seul contrat, nommé comme l'onglet — la page en déduit qu'il n'y a rien à
     choisir. */
  verifier('le paquet porte la liste des contrats et le contrat servi',
    Array.isArray(paquet.contrats) && paquet.contrats.length === 1 &&
    paquet.contrats[0].id === 'Données' && paquet.contrats[0].nom === 'Données' &&
    paquet.contrat === 'Données', JSON.stringify(paquet.contrats) + ' / ' + paquet.contrat);
  verifier('le contrat demandé par son identifiant est servi',
    ctxPaquet.getDonneesPourClient('Données').plans.length === paquet.plans.length &&
    ctxPaquet.getDonneesPourClient('Données').contrat === 'Données');
  /* Un identifiant qui ne désigne aucun onglet : une erreur qui le nomme, pas
     un repli silencieux sur un autre contrat — la page la montre et garde le
     contrat courant. */
  const inconnu = ctxPaquet.getDonneesPourClient('autre');
  verifier('un contrat inconnu donne un paquet d\'erreur qui le nomme, jamais un autre contrat',
    inconnu.ok === false && /« autre » est introuvable/.test(inconnu.message) &&
    inconnu.plans.length === 0 && inconnu.contrat === '', inconnu.message);
  verifier('les onze colonnes sont vues', paquet.colonnes.length === 11, String(paquet.colonnes.length));
  verifier('les lignes de titre ne sont pas prises pour des données',
    paquet.plans.length === 186, paquet.plans.length + ' plans');
  verifier('la ligne vide du milieu est écartée',
    paquet.plans.every(p => Object.keys(p).some(k => p[k])));
  verifier('la référence est figée et porte la clé « reference »',
    paquet.colonnes[0].cle === 'reference' && paquet.colonnes[0].fige === true);
  verifier('l\'avancement FWD est reconnu',
    paquet.colonnes.some(c => c.cle === 'avancement' && /Avancement FWD/.test(c.titre)));
  verifier('les groupes fusionnés sont propagés',
    paquet.colonnes[1].groupe === 'Informations principales' &&
    paquet.colonnes[5].groupe === 'Définition du plan', JSON.stringify(paquet.colonnes.map(c => c.groupe)));
  verifier('la colonne de date est repérée', paquet.cleDate === 'date_creation', String(paquet.cleDate));
  verifier('l\'ATA est la dimension proposée par défaut',
    paquet.dimParDefaut === 'ata', String(paquet.dimParDefaut));
  verifier('le commentaire libre n\'est pas une dimension',
    !paquet.colonnes.find(c => c.cle === 'commentaire').dim);
  verifier('la référence n\'est pas une dimension',
    !paquet.colonnes.find(c => c.cle === 'reference').dim);
  verifier('les libellés accentués sont conservés',
    paquet.colonnes.some(c => c.titre === 'Validation définition électrique'));

  // =================================================================
  section('Structure réelle de l\'export GATES');
  /* 137 colonnes, dont 91 sont treize répétitions du même bloc de sept ;
     une ligne de groupes fusionnés ; une ligne de service sous l\'en-tête ;
     et vingt-sept colonnes dont l\'intitulé contient « avancement », alors
     qu\'une seule est celle du FWD. */
  function serveurGates(nbLignes, config) {
    const g = feuilleGates(nbLignes || 186);
    const feuille = new Feuille('Données', g.valeurs, false, g.fusions);
    const classeur = new Classeur([feuille], 'Suivi FWD H225');
    const ctx = chargerServeur(classeur, {});
    // CONFIG est déclaré en const : il n'apparaît pas sur l'objet de contexte.
    if (config) {
      const cfg = vm.runInContext('CONFIG', ctx);
      Object.keys(config).forEach(k => { cfg[k] = config[k]; });
    }
    return { contexte: ctx, classeur: classeur };
  }

  const gates = serveurGates();
  const mGates = gates.contexte.construireModele();
  const hGates = entetesGates();
  verifier('les 138 colonnes de l\'export sont lues', mGates.colonnes.length === 138, String(mGates.colonnes.length));
  verifier('vingt-sept colonnes contiennent « avancement »',
    hGates.filter(t => /avancement/i.test(t)).length === 27,
    String(hGates.filter(t => /avancement/i.test(t)).length));

  /* Par défaut, le FWD se suit dans HDK AA 011 > Avancement Définition
     Electrique, et le concept harnais dans le même bloc. */
  const colFwd = mGates.colonnes.find(c => c.cle === 'avancement');
  verifier('par défaut, le FWD se lit dans HDK AA 011 > Avancement Définition Electrique',
    colFwd && colFwd.titre === 'Avancement Définition Electrique' && colFwd.groupe === 'HDK AA 011',
    colFwd && (colFwd.groupe + ' > ' + colFwd.titre));
  const colConcept = mGates.colonnes.find(c => c.cle === mGates.cleConcept);
  verifier('et le concept harnais dans HDK AA 011 > Avancement Concept Harnais — une autre colonne',
    !!colConcept && colConcept.titre === 'Avancement Concept Harnais' && colConcept.groupe === 'HDK AA 011' && mGates.cleConcept !== 'avancement',
    colConcept && (colConcept.groupe + ' > ' + colConcept.titre));
  /* Sans forçage, la détection d'avant reste juste : « Réalisation FWD >
     Avancement », jamais une colonne d'un bloc de variante. */
  const detecte = serveurGates(40, { COLONNE_FWD: '', COLONNE_CONCEPT: '' }).contexte.construireModele();
  const colDetectee = detecte.colonnes.find(c => c.cle === 'avancement');
  verifier('sans forçage, la détection retient « Avancement » du groupe « Réalisation FWD », et pas de concept',
    colDetectee && colDetectee.titre === 'Avancement' && colDetectee.groupe === 'Réalisation FWD' && detecte.cleConcept === null,
    colDetectee && (colDetectee.groupe + ' > ' + colDetectee.titre));

  verifier('les groupes fusionnés couvrent leur vraie largeur',
    mGates.colonnes[1].groupe === 'Informations principales' &&   // col 2
    mGates.colonnes[25].groupe === 'Définition du plan' &&        // col 26, ATA
    mGates.colonnes[41].groupe === 'Réalisation FWD' &&           // col 42, Avancement
    mGates.colonnes[47].groupe === 'HDK AA' &&                    // col 48
    mGates.colonnes[137].groupe === 'HDK AA 009',                 // col 138
    JSON.stringify([mGates.colonnes[1].groupe, mGates.colonnes[25].groupe,
                    mGates.colonnes[41].groupe, mGates.colonnes[47].groupe,
                    mGates.colonnes[137].groupe]));
  verifier('les deux « Concept Harnais » isolés ne sont pas étalés',
    mGates.colonnes[39].groupe === 'Concept Harnais' &&
    mGates.colonnes[40].groupe === 'Concept Harnais' &&
    mGates.colonnes[41].groupe === 'Réalisation FWD',
    JSON.stringify([mGates.colonnes[39].groupe, mGates.colonnes[40].groupe, mGates.colonnes[41].groupe]));
  verifier('un groupe ne déborde ni avant ni après sa plage',
    mGates.colonnes[0].groupe === '' &&      // col 1, hors groupe
    mGates.colonnes[45].groupe === '' &&     // col 46, Classif. SAP
    mGates.colonnes[46].groupe === '',       // col 47, Classif. calculée
    JSON.stringify([mGates.colonnes[0].groupe, mGates.colonnes[45].groupe, mGates.colonnes[46].groupe]));
  verifier('les colonnes sans intitulé reçoivent un nom lisible',
    mGates.colonnes[0].titre === 'Colonne 1' && mGates.colonnes[3].titre === 'Colonne 4',
    JSON.stringify([mGates.colonnes[0].titre, mGates.colonnes[3].titre]));

  verifier('la ligne de service sous l\'en-tête est écartée',
    mGates.plans.length === 186 && mGates.lignesIgnorees === 1,
    mGates.plans.length + ' plans, ' + mGates.lignesIgnorees + ' ignorée(s)');
  verifier('la référence figée est « Référence UD »',
    mGates.colonnes.find(c => c.fige).titre === 'Référence UD');
  verifier('la date de création est trouvée malgré les autres dates',
    mGates.cleDate === 'date_creation', String(mGates.cleDate));

  const titresDim = mGates.clesDim.map(c => mGates.colonnes.find(x => x.cle === c).titre);
  verifier('les colonnes d\'analyse sont celles demandées, dans l\'ordre',
    JSON.stringify(titresDim) === JSON.stringify(['ATA', 'Séquence', 'CC', 'ECP']), JSON.stringify(titresDim));
  verifier('l\'ATA est ouvert par défaut', mGates.dimParDefaut === 'ata', mGates.dimParDefaut);
  verifier('le mois de création s\'y ajoute côté page, pas côté serveur',
    mGates.cleDate === 'date_creation' && mGates.clesDim.indexOf('_mois') === -1);
  verifier('la vue essentielle tient en moins de dix colonnes',
    mGates.clesEssentielles.length <= 10 && mGates.clesEssentielles.length >= 5,
    String(mGates.clesEssentielles.length));
  verifier('elle contient la référence, l\'avancement suivi, le concept harnais et la date',
    ['reference', 'avancement', mGates.cleConcept, mGates.cleDate].every(c => c && mGates.clesEssentielles.indexOf(c) !== -1),
    JSON.stringify(mGates.clesEssentielles));
  verifier('la colonne de domaine est repérée',
    mGates.cleDomaine && mGates.colonnes.find(c => c.cle === mGates.cleDomaine).titre === 'Domaine',
    String(mGates.cleDomaine));
  verifier('l\'ancienneté s\'ajoute grâce à la date de création',
    mGates.cleDate && mGates.colonnes.find(c => c.cle === mGates.cleDate).titre === 'Date création',
    String(mGates.cleDate));
  verifier('aucune colonne de texte libre n\'est une dimension',
    !titresDim.some(t => /Commentaire|Libellé|Raison|Désignation/i.test(t)), JSON.stringify(titresDim));
  verifier('aucun intitulé répété n\'est une dimension',
    !titresDim.some(t => ['Validité', 'Quantité', 'A traiter par', 'Configuration officielle',
                          'Avancement Définition Electrique', 'Avancement Concept Harnais',
                          'Type'].indexOf(t) !== -1), JSON.stringify(titresDim));
  verifier('ni la référence ni la date brute ne sont des dimensions',
    !titresDim.some(t => ['Référence UD', 'Date création'].indexOf(t) !== -1), JSON.stringify(titresDim));
  verifier('ni l\'avancement ni le chapitre n\'y sont, comme demandé',
    titresDim.indexOf('Avancement') === -1 && titresDim.indexOf('Chapitre') === -1,
    JSON.stringify(titresDim));
  verifier('le nombre de dimensions reste tenable', titresDim.length <= 8, String(titresDim.length));

  /* Liste vidée : la détection automatique doit retomber sur des colonnes
     sensées, l'ATA compris, alors qu'il est en vingt-sixième position. */
  const auto = serveurGates(186, { DIMENSIONS: [] });
  const mAuto = auto.contexte.construireModele();
  const titresAuto = mAuto.colonnes.filter(c => c.dim).map(c => c.titre);
  verifier('sans liste, la détection trouve quand même l\'ATA',
    titresAuto.indexOf('ATA') !== -1 && mAuto.dimParDefaut === 'ata', JSON.stringify(titresAuto));
  verifier('et n\'y met ni texte libre ni intitulé répété',
    !titresAuto.some(t => /Commentaire|Libellé|Désignation|Raison/i.test(t)) &&
    !titresAuto.some(t => ['Validité', 'Quantité', 'A traiter par', 'Type'].indexOf(t) !== -1),
    JSON.stringify(titresAuto));

  verifier('aucune colonne n\'est écartée du modèle : l\'extract passe entier',
    mGates.colonnes.length === 138, String(mGates.colonnes.length));
  verifier('la ligne sans référence est bien celle du parasite',
    mGates.plans.every(p => /^UD-/.test(p.reference)),
    JSON.stringify(mGates.plans.filter(p => !/^UD-/.test(p.reference)).map(p => p.reference).slice(0, 3)));
  /* La feuille est lue en `getDisplayValues()` : la date arrive telle qu'elle
     s'affiche. Sur une feuille française, c'est le jour d'abord — et la
     colonne doit quand même être reconnue comme une date. */
  verifier('une date à la française traverse le modèle telle quelle',
    mGates.plans.every(p => /^\d{2}\/\d{2}\/\d{4}$/.test(p[mGates.cleDate])),
    JSON.stringify(mGates.plans.slice(0, 2).map(p => p[mGates.cleDate])));
  verifier('et la colonne de date est repérée malgré l\'ordre jour-mois',
    mGates.cleDate === 'date_creation', String(mGates.cleDate));

  // Les forçages doivent l'emporter sur la détection.
  const force = serveurGates(40, {
    COLONNE_FWD: 'HDK AA > Avancement Concept Harnais',
    DIMENSIONS: ['Groupage', 'ATA']
  });
  const mForce = force.contexte.construireModele();
  verifier('CONFIG.COLONNE_FWD impose la colonne, groupe compris',
    mForce.colonnes.find(c => c.cle === 'avancement').titre === 'Avancement Concept Harnais' &&
    mForce.colonnes.find(c => c.cle === 'avancement').groupe === 'HDK AA',
    mForce.colonnes.find(c => c.cle === 'avancement').groupe);
  verifier('CONFIG.DIMENSIONS impose la liste et son ordre',
    JSON.stringify(mForce.clesDim) === JSON.stringify(['groupage', 'ata']),
    JSON.stringify(mForce.clesDim));

  verifier('aucune autre colonne ne s\'empare des clés réservées',
    mForce.colonnes.filter(c => c.cle === 'avancement').length === 1 &&
    mForce.colonnes.filter(c => c.cle === 'reference').length === 1,
    JSON.stringify(mForce.colonnes.filter(c => /^(avancement|reference)/.test(c.cle)).map(c => c.cle + ':' + c.titre)));

  const forceInconnu = serveurGates(20, { COLONNE_FWD: 'Colonne qui n\'existe pas' });
  const mInconnu = forceInconnu.contexte.construireModele();
  verifier('un forçage qui ne tombe sur rien retombe sur la détection — et le modèle le sait',
    mInconnu.colonnes.find(c => c.cle === 'avancement').titre === 'Avancement' && mInconnu.fwdDemandeeAbsente === true);
  verifier('le diagnostic le dit : la colonne demandée est introuvable, la page suit celle trouvée d’elle-même',
    /⚠ La colonne demandée \(CONFIG\.COLONNE_FWD « Colonne qui n'existe pas »\) est introuvable/.test(forceInconnu.contexte.diagnostic()));

  // L'archivage doit tenir sur 137 colonnes et treize blocs répétés.
  gates.contexte.enregistrerInstantaneHebdo();
  const hg = gates.contexte.getHistorique(gates.classeur);
  verifier('le relevé s\'archive sur la structure réelle',
    hg.length === 1 && hg[0].total === 186 &&
    hg[0].termine + hg[0].encours + hg[0].afaire + hg[0].vide === 186);
  verifier('les comptes par ATA sont archivés',
    hg[0].groupes.ata && Object.keys(hg[0].groupes.ata).length >= 5,
    JSON.stringify(Object.keys(hg[0].groupes.ata || {})));
  /* Le concept harnais s'archive avec la définition : deux cartes relues,
     chacune sur les 186 plans, aux valeurs de leur colonne. */
  const valeursConcept = {}, valeursDef = {};
  mGates.plans.forEach(p => { valeursConcept[p.reference] = String(p[mGates.cleConcept] || ''); valeursDef[p.reference] = String(p.avancement || ''); });
  verifier('le relevé garde les deux avancements, relus en deux cartes : définition (plans) et concept (plansConcept)',
    !!hg[0].plans && !!hg[0].plansConcept &&
    Object.keys(hg[0].plansConcept).length === 186 && Object.keys(hg[0].plans).length === 186 &&
    Object.keys(hg[0].plans).every(r => typeof hg[0].plans[r] === 'string' && hg[0].plans[r] === valeursDef[r]) &&
    Object.keys(hg[0].plansConcept).every(r => hg[0].plansConcept[r] === valeursConcept[r]),
    JSON.stringify(Object.keys(hg[0].plansConcept || {}).slice(0, 2)));

  const rapportGates = gates.contexte.diagnostic();
  verifier('le diagnostic nomme la colonne FWD et son groupe',
    /Avancement FWD : colonne « Avancement Définition Electrique », groupe « HDK AA 011 »/.test(rapportGates) &&
    !/⚠ La colonne demandée/.test(rapportGates),
    rapportGates.split('\n').find(l => /Avancement FWD/.test(l)));
  verifier('pour chaque colonne suivie, le diagnostic donne les valeurs lues et leur compte',
    (rapportGates.match(/^  valeurs lues : /gm) || []).length === 2, rapportGates.split('\n').filter(l => /valeurs lues/.test(l)).join(' / '));
  const rapportValide = serveurSur(feuilleExemple(10).map((l, i) => i === 4 ? l.map((c, j) => j === 8 ? 'Validé' : c) : l)).contexte.diagnostic();
  verifier('« Validé » y est marqué « = fini »', /« Validé » 1 = fini/.test(rapportValide),
    rapportValide.split('\n').filter(l => /valeurs lues/.test(l)).join(' / '));
  verifier('et celle du concept harnais, avec ses comptes',
    /✓ Concept harnais : colonne « Avancement Concept Harnais », groupe « HDK AA 011 »/.test(rapportGates) &&
    /✓ Concept harnais[^\n]*\n  \d+ terminés, \d+ en cours, \d+ à faire, \d+ non renseignés/.test(rapportGates),
    rapportGates.split('\n').filter(l => /Concept harnais/.test(l)).join(' / '));
  verifier('il liste les colonnes d\'analyse en clair',
    /Analyse par : .*ATA/.test(rapportGates), rapportGates.split('\n').find(l => /Analyse par/.test(l)));
  verifier('il signale les lignes ignorées et annonce l\'extract entier',
    /1 ligne\(s\) sans référence ignorée/.test(rapportGates) &&
    /Tableau ouvert sur les 138 colonnes de la feuille, dans son ordre/.test(rapportGates),
    rapportGates.split('\n').find(l => /Tableau ouvert/.test(l)));

  // =================================================================
  section('Classement des quatre états, côté serveur');
  const { contexte } = serveurSur(feuilleExemple(10));
  const cas = [
    ['100%', 'termine'], ['100 %', 'termine'], ['Terminé', 'termine'], ['TERMINE', 'termine'],
    ['achevé', 'termine'], ['soldé', 'termine'],
    ['50%', 'encours'], ['75 %', 'encours'], ['En cours', 'encours'], ['0,5', 'encours'],
    ['À faire', 'afaire'], ['à faire', 'afaire'], ['A FAIRE', 'afaire'], ['0%', 'afaire'],
    ['Non commencé', 'afaire'],
    ['', 'vide'], ['   ', 'vide'], ['-', 'vide'], [null, 'vide'], [undefined, 'vide'],
    // « EMPTY », tel que l'extract l'écrit dans une case vide, est une case vide.
    ['EMPTY', 'vide'], ['empty', 'vide'],
    /* Le vocabulaire de l'extract : « Validé » est fini (CONFIG.VALEURS_FINIES),
       comparé entier ; « à traiter » est à faire ; le reste est en cours. */
    ['Validé', 'termine'], ['VALIDE', 'termine'], ['  validé ', 'termine'],
    ['Non validé', 'encours'], ['Invalidé', 'encours'],
    ['A traiter', 'afaire'], ['à traiter', 'afaire'], ['Check', 'encours']
  ];
  let tousBons = true, mauvais = '';
  cas.forEach(([valeur, attendu]) => {
    const obtenu = contexte.classerFWD(valeur);
    if (obtenu !== attendu) { tousBons = false; mauvais += ' ' + JSON.stringify(valeur) + '→' + obtenu; }
  });
  verifier('les trente cas de classement tombent juste, « Validé » compris', tousBons, mauvais);
  /* La page classe exactement comme le serveur : la même table, côté client. */
  const pageClasse = await (async () => {
    const nav0 = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
    const p0 = await (await nav0.newContext()).newPage();
    await p0.goto('file://' + path.join(__dirname, '..', 'prototype', 'apercu.html'));
    await p0.waitForTimeout(900);
    const r = await p0.evaluate(c => c.map(([v]) => window.__classer(v)), cas);
    await nav0.close();
    return r;
  })();
  verifier('la page classe chaque cas comme le serveur',
    cas.every(([v, att], i) => pageClasse[i] === att), JSON.stringify(cas.filter(([v, att], i) => pageClasse[i] !== att)));
  verifier('« à faire » n\'est pas confondu avec une cellule vide',
    contexte.classerFWD('À faire') !== contexte.classerFWD(''));

  // =================================================================
  section('Semaines ISO');
  verifier('début janvier retombe sur l\'année précédente',
    contexte.numeroSemaineISO(new Date(2027, 0, 1)) === '2026-S53',
    contexte.numeroSemaineISO(new Date(2027, 0, 1)));
  verifier('le 4 janvier est toujours en semaine 1',
    contexte.numeroSemaineISO(new Date(2026, 0, 4)) === '2026-S01');
  verifier('une semaine se normalise', contexte.normaliserSemaine('2026-s8') === '2026-S08');
  verifier('une semaine absurde est rejetée',
    contexte.normaliserSemaine('2026-S99') === null && contexte.normaliserSemaine('n\'importe quoi') === null);

  // =================================================================
  section('Historique : archivage et relecture');
  /* Un contrat par onglet, un onglet d'historique par contrat : celui du
     contrat « Données » s'appelle « Historique_FWD_Données ». */
  const h = serveurSur(feuilleExemple(50));
  const r1 = h.contexte.enregistrerInstantaneHebdo();
  verifier('un relevé est écrit, et le détail nomme le contrat et son onglet d\'historique',
    r1.ok && r1.contrats.length === 1 && r1.contrats[0].id === 'Données' &&
    r1.contrats[0].historique === 'Historique_FWD_Données' && r1.contrats[0].compte.total === 50,
    JSON.stringify(r1.semaine) + ' ' + JSON.stringify(r1.contrats && r1.contrats.map(c => [c.id, c.historique])));
  verifier('l\'onglet d\'historique du contrat est créé et masqué',
    h.classeur.getSheetByName('Historique_FWD_Données') !== null &&
    h.classeur.getSheetByName('Historique_FWD_Données').isSheetHidden() &&
    h.classeur.getSheetByName('Historique_FWD') === null,
    h.classeur.getSheets().map(f => f.getName()).join(', '));
  const avant = h.classeur.getSheetByName('Historique_FWD_Données').valeurs.length;
  h.contexte.enregistrerInstantaneHebdo();
  h.contexte.enregistrerInstantaneHebdo();
  verifier('réimporter la même semaine ne crée pas de doublon',
    h.classeur.getSheetByName('Historique_FWD_Données').valeurs.length === avant,
    avant + ' → ' + h.classeur.getSheetByName('Historique_FWD_Données').valeurs.length);
  const histo = h.contexte.getHistorique(h.classeur);
  verifier('le relevé se relit', histo.length === 1 && histo[0].total === 50);
  verifier('les quatre états sont archivés séparément',
    histo[0].termine + histo[0].encours + histo[0].afaire + histo[0].vide === 50,
    JSON.stringify(histo[0]).slice(0, 120));
  verifier('les comptes par dimension sont archivés',
    histo[0].groupes && histo[0].groupes.ata && Object.keys(histo[0].groupes.ata).length > 0);
  verifier('l\'ancienneté est archivée comme dimension',
    histo[0].groupes && !!histo[0].groupes._anciennete);
  verifier('chaque plan est archivé nommément',
    histo[0].plans && Object.keys(histo[0].plans).length === 50,
    String(histo[0].plans && Object.keys(histo[0].plans).length));
  const parAta = histo[0].groupes.ata;
  const sommeAta = Object.keys(parAta).reduce((s, k) => s + parAta[k].total, 0);
  verifier('la somme par ATA retombe sur le total', sommeAta === 50, String(sommeAta));

  /* Une feuille énorme : la carte plan par plan ne tient plus dans une
     cellule (Sheets : 50 000 caractères). Elle est répartie sur plusieurs
     cellules à partir de la colonne « Plans », aucune ne dépasse 45 000
     caractères, et elle se relit entière — la jeter, comme avant, privait
     ces relevés de périmètre, de journal et de comparatif. Les références
     font 15 caractères, comme les vraies. */
  const valeurs4000 = feuilleExemple(4000).map((l, i) => {
    if (i < 4 || !l[0]) return l;
    const c = l.slice(); c[0] = 'H225-' + c[0]; return c;
  });
  const gros = serveurSur(valeurs4000);
  gros.contexte.enregistrerInstantaneHebdo();
  const feuilleGrosse = gros.classeur.getSheetByName('Historique_FWD_Données');
  const ligneGrosse = feuilleGrosse.valeurs[1];
  const cellulesPlans = ligneGrosse.slice(8).filter(v => v !== '' && v !== undefined);
  verifier('4 000 plans : la carte est répartie sur plusieurs cellules, aucune ne dépasse 45 000 caractères',
    valeurs4000[4][0].length === 15 && cellulesPlans.length >= 2 &&
    ligneGrosse.every(v => String(v).length <= 45000) && cellulesPlans.join('').length > 45000,
    cellulesPlans.length + ' cellule(s) : ' + cellulesPlans.map(v => String(v).length).join(' + ') + ' car.');
  verifier('les comptes restent justes sur 4 000 plans', Number(ligneGrosse[2]) === 4000);
  const reluGros = gros.contexte.getHistorique(gros.classeur);
  verifier('la carte se relit entière, plan par plan',
    reluGros.length === 1 && reluGros[0].plans !== null && Object.keys(reluGros[0].plans).length === 4000 &&
    Object.prototype.hasOwnProperty.call(reluGros[0].plans, valeurs4000[4][0]),
    String(reluGros[0] && reluGros[0].plans && Object.keys(reluGros[0].plans).length));
  verifier('le diagnostic dit sur combien de cellules la carte s\'étale',
    new RegExp('carte plan par plan sur ' + cellulesPlans.length + ' cellules par relevé').test(gros.contexte.diagnostic()));

  /* Réarchiver la même semaine avec une carte plus courte : la ligne est
     mise à jour, et les cellules que l'ancienne carte occupait en plus sont
     vidées — aucun résidu à recoller à la lecture. Puis plus longue à
     nouveau : elle reprend ses cellules. */
  const largeurAvant = ligneGrosse.length;
  gros.classeur.getSheetByName('Données').valeurs = feuilleExemple(50);
  gros.contexte.enregistrerInstantaneHebdo();
  const ligneCourte = feuilleGrosse.valeurs[1];
  const reluCourt = gros.contexte.getHistorique(gros.classeur);
  verifier('réarchiver la même semaine avec moins de plans vide les cellules en trop',
    feuilleGrosse.valeurs.length === 2 && largeurAvant >= 11 && ligneCourte.length === largeurAvant &&
    ligneCourte.slice(9).every(v => v === '') && Number(ligneCourte[2]) === 50 &&
    reluCourt.length === 1 && reluCourt[0].plans !== null && Object.keys(reluCourt[0].plans).length === 50,
    largeurAvant + ' → ' + ligneCourte.length + ' colonnes, résidu ' +
      JSON.stringify(ligneCourte.slice(9).map(v => String(v).length)));
  gros.classeur.getSheetByName('Données').valeurs = valeurs4000;
  gros.contexte.enregistrerInstantaneHebdo();
  verifier('et réarchiver plus de plans la rétale sur plusieurs cellules',
    feuilleGrosse.valeurs.length === 2 &&
    feuilleGrosse.valeurs[1].slice(8).filter(v => v !== '').length === cellulesPlans.length &&
    Object.keys(gros.contexte.getHistorique(gros.classeur)[0].plans).length === 4000);

  /* Une ligne d'un ancien relevé — la carte dans une seule cellule, neuf
     colonnes — se relit comme avant à côté des lignes étalées ; une cellule
     « Plans » vide donne toujours « pas de carte ». */
  feuilleGrosse.valeurs.push(['2026-S02', new Date(2026, 0, 9), 3, 1, 1, 1, 0, '{}', '{"A":"100%","B":"50%","C":""}']);
  feuilleGrosse.valeurs.push(['2026-S03', new Date(2026, 0, 16), 3, 1, 1, 1, 0, '{}', '']);
  const reluMixte = gros.contexte.getHistorique(gros.classeur);
  verifier('une ligne ancienne à neuf colonnes se relit comme avant, une cellule « Plans » vide donne null',
    reluMixte.length === 3 && reluMixte[0].semaine === '2026-S02' &&
    JSON.stringify(reluMixte[0].plans) === '{"A":"100%","B":"50%","C":""}' &&
    reluMixte[1].semaine === '2026-S03' && reluMixte[1].plans === null &&
    Object.keys(reluMixte[2].plans).length === 4000,
    JSON.stringify(reluMixte.map(r => [r.semaine, r.plans && Object.keys(r.plans).length])));

  /* La grille de l'onglet n'a plus que neuf colonnes (quelqu'un a supprimé
     les colonnes vides) : Sheets refuse d'écrire au-delà, donc l'archivage
     l'élargit d'abord — à l'ajout d'une ligne comme à la mise à jour. */
  const etroit = serveurSur(valeurs4000);
  const histoEtroit = etroit.contexte.getFeuilleHistorique(etroit.classeur, undefined, true);
  histoEtroit.colonnesGrille = 9;
  let refusGrille = false;
  try { histoEtroit.getRange(1, 1, 1, 10); } catch (e) { refusGrille = true; }
  let erreurGrille = '';
  try { etroit.contexte.enregistrerInstantaneHebdo(); } catch (e) { erreurGrille = e.message; }
  const largeurAjout = histoEtroit.getMaxColumns();
  histoEtroit.valeurs[1].length = 9;           // un relevé écrit à l'ancienne, dans une grille étroite
  histoEtroit.colonnesGrille = 9;
  try { etroit.contexte.enregistrerInstantaneHebdo(); } catch (e) { erreurGrille += ' ; ' + e.message; }
  verifier('une grille trop étroite est élargie avant d\'écrire, à l\'ajout comme à la mise à jour',
    refusGrille && erreurGrille === '' && largeurAjout >= 11 && histoEtroit.getMaxColumns() >= 11 &&
    histoEtroit.valeurs.length === 2 &&
    Object.keys(etroit.contexte.getHistorique(etroit.classeur)[0].plans).length === 4000,
    erreurGrille || (largeurAjout + ' / ' + histoEtroit.getMaxColumns() + ' colonnes'));

  // =================================================================
  section('Historique : relecture tolérante');
  const abime = serveurSur(feuilleExemple(20));
  abime.contexte.enregistrerInstantaneHebdo();
  const f = abime.classeur.getSheetByName('Historique_FWD_Données');
  f.valeurs.push(['pas une semaine', new Date(), 1, 1, 0, 0, 0, '{', '{']);
  f.valeurs.push(['', '', '', '', '', '', '', '', '']);
  f.valeurs.push(['2026-S02', new Date(), 5, 1, 1, 1, 2, 'JSON cassé {[', 'idem']);
  const relu = abime.contexte.getHistorique(abime.classeur);
  verifier('les lignes illisibles sont ignorées', relu.length === 2, relu.length + ' relevés');
  verifier('un JSON cassé ne fait pas tomber la lecture',
    relu[0].semaine === '2026-S02' && relu[0].plans === null && JSON.stringify(relu[0].groupes) === '{}');

  // =================================================================
  /* L'ancien classeur : un seul onglet de données et l'onglet « Historique_FWD »
     tout court, avec des relevés dedans. Il continue de servir tel quel — rien
     n'est renommé, rien n'est reconstruit, et aucun onglet nouveau n'apparaît. */
  section('Historique : rétro-compatibilité de l\'ancien onglet « Historique_FWD »');
  const ENTETES_H = ['Semaine', 'Date', 'Total', 'Terminés', 'En cours', 'À faire', 'Non renseignés', 'Par dimension', 'Plans'];
  const ancienHisto = new Feuille('Historique_FWD', [
    ENTETES_H.slice(),
    ['2026-S30', new Date(2026, 6, 24), 30, 5, 5, 10, 10, '{"ata":{"24":{"total":30,"termine":5}}}', '{}']
  ], true);
  const ancien = new Classeur([new Feuille('Données', feuilleExemple(30)), ancienHisto], 'Ancien classeur');
  const cAncien = chargerServeur(ancien, {});
  verifier('un seul onglet visible : un seul contrat, et « Historique_FWD » n\'en est pas un',
    JSON.stringify(cAncien.listerContrats(ancien)) === JSON.stringify([{ id: 'Données', nom: 'Données' }]));
  verifier('l\'ancien onglet est l\'historique de ce contrat',
    cAncien.getFeuilleHistorique(ancien, 'Données', false) === ancienHisto &&
    cAncien.getHistorique(ancien, 'Données').length === 1 &&
    cAncien.getHistorique(ancien, 'Données')[0].semaine === '2026-S30');
  /* Un relevé d'avant le concept harnais ne porte que des chaînes : il se
     relit tel quel, sans carte du concept — rien ne s'invente. */
  const ancienAvecCarte = new Feuille('Historique_FWD', [
    ENTETES_H.slice(),
    ['2026-S29', new Date(2026, 6, 17), 2, 1, 1, 0, 0, '{}', '{"TFE3110A600003C":"Terminé","MBE3411A800001A":"En cours"}']
  ], true);
  const classeurCarte = new Classeur([new Feuille('Données', feuilleExemple(10)), ancienAvecCarte], 'Carte ancienne');
  const cCarte = chargerServeur(classeurCarte, {});
  const hCarte = cCarte.getHistorique(classeurCarte, 'Données');
  verifier('un relevé d’avant le concept se relit tel quel : sa carte, et pas de carte du concept',
    hCarte.length === 1 && hCarte[0].plans && hCarte[0].plans.TFE3110A600003C === 'Terminé' && !('plansConcept' in hCarte[0]),
    JSON.stringify(hCarte[0]));
  const rAncien = cAncien.enregistrerInstantaneHebdo();
  verifier('l\'archivage écrit dedans, sans créer « Historique_FWD_Données »',
    rAncien.contrats[0].historique === 'Historique_FWD' && ancienHisto.valeurs.length === 3 &&
    ancien.getSheetByName('Historique_FWD_Données') === null &&
    cAncien.getHistorique(ancien).length === 2,
    ancien.getSheets().map(x => x.getName()).join(', '));
  verifier('le paquet de la page lit ces relevés', cAncien.getDonneesPourClient().releves.length === 2);
  ancienHisto.showSheet();
  verifier('démasqué, l\'ancien onglet n\'est toujours pas un contrat',
    cAncien.listerContrats(ancien).length === 1 && cAncien.getDonneesPourClient().contrats.length === 1);
  ancienHisto.hideSheet();
  /* Le diagnostic le nomme comme onglet d'historique, sans rien signaler. */
  const rapAncien = cAncien.diagnostic();
  verifier('le diagnostic le donne comme onglet d\'historique du contrat',
    /Relevés archivés : 2 \(onglet « Historique_FWD »\)/.test(rapAncien) && !/rattaché à aucun contrat/.test(rapAncien),
    rapAncien.split('\n').find(l => /Relevés archivés/.test(l)));

  // =================================================================
  /* Plusieurs contrats : chaque onglet visible qui n'est pas de service en
     est un, nommé comme l'onglet, dans l'ordre des onglets ; chacun a son
     historique masqué « Historique_FWD_<nom> » ; l'archivage et la
     suppression passent sur tous ; la page reçoit le premier et demande les
     autres. */
  section('Plusieurs contrats : un onglet visible chacun');
  const multi = construire({ contrats: ['X1', 'X2'], sortie: 'apercu-contrats.html' });
  const cM = multi.contexte, clM = multi.classeur, pM = multi.paquet;
  verifier('deux onglets, deux contrats, dans l\'ordre des onglets',
    JSON.stringify(cM.listerContrats(clM)) === JSON.stringify([{ id: 'X1', nom: 'X1' }, { id: 'X2', nom: 'X2' }]),
    JSON.stringify(cM.listerContrats(clM)));
  verifier('le paquet d\'ouverture est celui du premier, et porte les deux',
    pM.ok === true && pM.contrat === 'X1' && pM.feuille === 'X1' && pM.plans.length === 186 &&
    JSON.stringify(pM.contrats) === JSON.stringify([{ id: 'X1', nom: 'X1' }, { id: 'X2', nom: 'X2' }]),
    pM.contrat + ' / ' + pM.plans.length);
  const pX2 = cM.getDonneesPourClient('X2');
  verifier('le paquet de X2 est un autre paquet : son onglet, ses plans, ses relevés',
    pX2.ok === true && pX2.contrat === 'X2' && pX2.plans.length === 93 && pX2.plans.length !== pM.plans.length &&
    pX2.contrats.length === 2 && pX2.releves.length === 5 && pX2.releves[4].total === 93 && pM.releves[4].total === 186,
    pX2.contrat + ' / ' + pX2.plans.length + ' plans, ' + pX2.releves.length + ' relevés');
  verifier('le paquet posé dans la page est celui du premier contrat',
    /"contrat":"X1"/.test(cM.donneesJSONPourPage()) && /"contrats":\[\{"id":"X1","nom":"X1"\},\{"id":"X2","nom":"X2"\}\]/.test(cM.donneesJSONPourPage()));
  verifier('un identifiant se retrouve sans tenir compte de la casse ni des accents',
    cM.getDonneesPourClient('x2').contrat === 'X2' && cM.getDonneesPourClient(' X1 ').contrat === 'X1');
  /* L'historique suit la même résolution : « x1 » est bien l'historique de
     « X1 », pas un onglet fantôme vide ; et un contrat inconnu est une erreur
     franche, comme pour les données. */
  verifier('l\'historique d\'un contrat se retrouve aussi sans tenir compte de la casse',
    cM.getHistorique(clM, 'x1').length === cM.getHistorique(clM, 'X1').length &&
    cM.getHistorique(clM, 'X1').length === 5 &&
    cM.getFeuilleHistorique(clM, ' x1 ', false).getName() === 'Historique_FWD_X1',
    cM.getHistorique(clM, 'x1').length + ' / ' + cM.getHistorique(clM, 'X1').length);
  let erreurInconnu = '';
  try { cM.getHistorique(clM, 'X9'); } catch (e) { erreurInconnu = e.message; }
  verifier('l\'historique d\'un contrat inconnu est une erreur franche, pas un onglet fantôme',
    /« X9 » est introuvable/.test(erreurInconnu) && clM.getSheetByName('Historique_FWD_X9') === null, erreurInconnu);
  verifier('deux onglets d\'historique masqués, un par contrat, et pas d\'ancien onglet',
    ['Historique_FWD_X1', 'Historique_FWD_X2'].every(n => clM.getSheetByName(n) !== null && clM.getSheetByName(n).isSheetHidden()) &&
    clM.getSheetByName('Historique_FWD') === null, clM.getSheets().map(x => x.getName()).join(', '));

  const histoX1 = clM.getSheetByName('Historique_FWD_X1'), histoX2 = clM.getSheetByName('Historique_FWD_X2');
  const avantM = [histoX1.valeurs.length, histoX2.valeurs.length];
  const rM = cM.enregistrerInstantaneHebdo();
  verifier('l\'archivage passe sur les deux contrats et renvoie le détail, contrat par contrat',
    rM.ok === true && rM.contrats.map(c => c.id + ':' + c.historique + ':' + c.compte.total).join(' ') ===
      'X1:Historique_FWD_X1:186 X2:Historique_FWD_X2:93',
    JSON.stringify(rM.contrats && rM.contrats.map(c => [c.id, c.historique, c.compte.total])));
  verifier('la semaine courante est mise à jour dans chaque onglet, sans doublon',
    histoX1.valeurs.length === avantM[0] && histoX2.valeurs.length === avantM[1] &&
    cM.normaliserSemaine(histoX1.valeurs[histoX1.valeurs.length - 1][0]) === rM.semaine &&
    cM.normaliserSemaine(histoX2.valeurs[histoX2.valeurs.length - 1][0]) === rM.semaine);
  verifier('les comptes archivés sont ceux de chaque contrat, pas ceux de l\'autre',
    Number(histoX1.valeurs[histoX1.valeurs.length - 1][2]) === 186 &&
    Number(histoX2.valeurs[histoX2.valeurs.length - 1][2]) === 93);

  const sM = cM.supprimerDernierReleve();
  verifier('la suppression retire la semaine courante des deux contrats',
    sM.supprimes.join() === 'X1,X2' && sM.sans.length === 0 &&
    histoX1.valeurs.length === avantM[0] - 1 && histoX2.valeurs.length === avantM[1] - 1 &&
    cM.getHistorique(clM, 'X1').length === 4 && cM.getHistorique(clM, 'X2').length === 4,
    JSON.stringify(sM));
  verifier('et l\'alerte récapitule contrat par contrat',
    /^Relevé \d{4}-S\d{2} supprimé pour « X1 », « X2 »\. Recollez/.test(cM.__alertes[cM.__alertes.length - 1]),
    cM.__alertes[cM.__alertes.length - 1]);
  const sM2 = cM.supprimerDernierReleve();
  verifier('une seconde suppression n\'a plus rien à retirer, et le dit',
    sM2.supprimes.length === 0 && sM2.sans.join() === 'X1,X2' &&
    /^Aucun relevé pour la semaine \d{4}-S\d{2}\.$/.test(cM.__alertes[cM.__alertes.length - 1]),
    cM.__alertes[cM.__alertes.length - 1]);
  /* Un seul contrat archivé cette semaine : le récapitulatif distingue. */
  histoX1.appendRow([rM.semaine, new Date(), 186, 1, 1, 1, 183, '{}', '{}']);
  const sM3 = cM.supprimerDernierReleve();
  verifier('un contrat avec relevé, l\'autre sans : le récapitulatif distingue les deux',
    sM3.supprimes.join() === 'X1' && sM3.sans.join() === 'X2' &&
    /supprimé pour « X1 » ; aucun relevé pour « X2 »/.test(cM.__alertes[cM.__alertes.length - 1]),
    cM.__alertes[cM.__alertes.length - 1]);

  histoX2.showSheet();
  verifier('un onglet d\'historique démasqué n\'est pas un contrat pour autant',
    cM.listerContrats(clM).length === 2 && cM.getDonneesPourClient().contrats.length === 2);
  histoX2.hideSheet();
  const rapM = cM.diagnostic();
  verifier('le diagnostic nomme les deux contrats et leurs onglets d\'historique',
    /2 contrat\(s\), un onglet visible chacun : « X1 », « X2 »/.test(rapM) &&
    /— Contrat « X1 » —/.test(rapM) && /— Contrat « X2 » —/.test(rapM) &&
    /Relevés archivés : 4 \(onglet « Historique_FWD_X1 »\)/.test(rapM) &&
    /Relevés archivés : 4 \(onglet « Historique_FWD_X2 »\)/.test(rapM),
    rapM.split('\n').filter(l => /contrat|Contrat|Relevés/.test(l)).join(' / '));
  verifier('il dit que la page part sur le premier contrat, et conclut',
    /contrat « X1 », le premier ; les autres se chargent à la demande/.test(rapM) && /Tout est en place/.test(rapM));

  /* L'ancien onglet « Historique_FWD » à côté de deux contrats : il n'est
     l'historique de personne, et le diagnostic dit comment le rattacher. */
  clM.insertSheet('Historique_FWD').appendRow(ENTETES_H.slice());
  verifier('à côté de plusieurs contrats, l\'ancien onglet n\'est ni un contrat ni l\'historique de l\'un d\'eux',
    cM.listerContrats(clM).length === 2 &&
    cM.getFeuilleHistorique(clM, 'X1', false).getName() === 'Historique_FWD_X1' &&
    cM.getFeuilleHistorique(clM, 'X2', false).getName() === 'Historique_FWD_X2');
  const rapOrphelin = cM.diagnostic();
  verifier('et le diagnostic dit comment le rattacher',
    /« Historique_FWD » n'est rattaché à aucun contrat/.test(rapOrphelin) &&
    /renommer « Historique_FWD_<nom du contrat> »/.test(rapOrphelin),
    rapOrphelin.split('\n').find(l => /rattaché/.test(l)));

  /* Un onglet visible mais VIDE n'est pas un contrat : c'est la « Feuille 1 »
     d'un classeur neuf, restée en tête à côté de l'onglet du premier
     contrat. Il ne compte pas, n'est pas archivé, ne fait pas d'erreur, et
     la page s'ouvre sur le contrat rempli — même quand le vide est premier. */
  const clV = new Classeur([new Feuille('Feuille 1', []), new Feuille('X1', feuilleExemple(20))], 'Avec un onglet vide en tête');
  const cV = chargerServeur(clV, {});
  let erreurV = '';
  try { cV.enregistrerInstantaneHebdo(); } catch (e) { erreurV = e.message; }
  const boite = cV.__alertes[cV.__alertes.length - 1];
  verifier('un onglet vide en tête n\'est pas un contrat : l\'archivage passe sur l\'autre seul, sans erreur',
    erreurV === '' && cV.getHistorique(clV, 'X1').length === 1 && cV.listerContrats(clV).length === 1 &&
    cV.listerContrats(clV)[0].id === 'X1', erreurV || JSON.stringify(cV.listerContrats(clV)));
  verifier('la page s\'ouvre sur le contrat rempli ; l\'onglet vide, demandé par son nom, est introuvable',
    cV.getDonneesPourClient().ok === true && cV.getDonneesPourClient().contrat === 'X1' &&
    cV.getDonneesPourClient().contrats.length === 1 && cV.getDonneesPourClient('Feuille 1').ok === false);
  verifier('le diagnostic ne le mentionne pas et conclut que tout est en place',
    !/Feuille 1/.test(cV.diagnostic()) && /Tout est en place/.test(cV.diagnostic()), cV.diagnostic());
  /* Lancé du menu, l'archivage se confirme dans une boîte : la semaine, les
     contrats et leurs comptes, et le fait qu'un second archivage remplace. */
  verifier('l\'archivage se confirme dans une boîte : « Relevé <semaine> archivé : X1 (20 plans). »',
    /^Relevé \d{4}-S\d{2} archivé : X1 \(20 plans\)\. Un second archivage dans la semaine remplace celui-ci\.$/.test(boite), boite);

  /* Ce qui n'est pas un contrat : un onglet masqué, un onglet de service, la
     seconde base. CONFIG.FEUILLE_DONNEES, lui, impose un contrat unique. */
  const clS = new Classeur([
    new Feuille('Paramètres', [['clé', 'valeur']]),
    new Feuille('X1', feuilleExemple(20)),
    new Feuille('Brouillon', feuilleExemple(10), true),
    new Feuille('Base2', [['REF_UD']]),
    new Feuille('X2', feuilleExemple(15)),
    new Feuille('Historique_FWD', [ENTETES_H.slice(), ['2026-S20', new Date(2026, 4, 15), 20, 2, 2, 8, 8, '{}', '{}']], true)
  ], 'Service');
  const cS = chargerServeur(clS, {});
  vm.runInContext('CONFIG.RAPPROCHEMENT.FEUILLE = "Base2"', cS);
  verifier('ni un onglet de service, ni un onglet masqué, ni la seconde base ne sont des contrats',
    cS.listerContrats(clS).map(c => c.id).join() === 'X1,X2', JSON.stringify(cS.listerContrats(clS)));
  vm.runInContext('CONFIG.FEUILLE_DONNEES = "X2"', cS);
  verifier('CONFIG.FEUILLE_DONNEES impose un contrat unique, cet onglet-là',
    cS.listerContrats(clS).map(c => c.id).join() === 'X2' && cS.getDonneesPourClient().contrat === 'X2' &&
    cS.getDonneesPourClient().plans.length === 15 && cS.getDonneesPourClient().contrats.length === 1);
  verifier('et ce contrat unique retrouve l\'ancien onglet d\'historique',
    cS.getHistorique(clS, 'X2').length === 1 && cS.getHistorique(clS, 'X2')[0].semaine === '2026-S20');
  verifier('un autre onglet demandé est alors introuvable',
    cS.getDonneesPourClient('X1').ok === false && /« X1 » est introuvable/.test(cS.getDonneesPourClient('X1').message));
  vm.runInContext('CONFIG.FEUILLE_DONNEES = "Nulle part"', cS);
  verifier('un onglet imposé qui n\'existe pas est une erreur lisible',
    cS.getDonneesPourClient().ok === false && /« Nulle part » est introuvable/.test(cS.getDonneesPourClient().message) &&
    /Onglet de données : L'onglet « Nulle part » est introuvable/.test(cS.diagnostic()));

  // =================================================================
  section('Jalons de configuration');
  /* Les jalons vivent dans CONFIG.JALONS, et nulle part ailleurs : pas de
     propriété de document, pas d'écriture. getJalons() valide ce que la
     configuration contient. On modifie CONFIG dans le contexte du serveur,
     comme le ferait quelqu'un qui édite Code.gs. */
  const j = serveurSur(feuilleExemple(10));
  const configurer = (liste) => vm.runInContext('CONFIG.JALONS = ' + JSON.stringify(liste), j.contexte);
  const parDefaut = j.contexte.getJalons();
  verifier('la configuration livrée porte les cinq jalons du programme, triés et normalisés',
    parDefaut.length === 5 && parDefaut.every(x => /^\d{4}-S\d{2}$/.test(x.semaine) && x.texte) &&
    parDefaut.every((x, i) => i === 0 || parDefaut[i - 1].semaine <= x.semaine), JSON.stringify(parDefaut));
  verifier('le solde FWD en tête (2026-S51, pour tous), puis les diffusions PH et TO, Base et Perso, chacune à son périmètre',
    parDefaut[0].texte === 'Solde FWD' && parDefaut[0].semaine === '2026-S51' && !('perimetre' in parDefaut[0]) &&
    parDefaut.slice(1).map(x => x.texte + '@' + x.semaine + '/' + x.perimetre).join() ===
      'Diffusion PH Base@2027-S02/BASE/OPTION,Diffusion PH Perso@2027-S03/PERSO,Diffusion TO Base@2027-S05/BASE/OPTION,Diffusion TO Perso@2027-S08/PERSO',
    JSON.stringify(parDefaut));
  verifier('aucune fonction de sauvegarde ni de propriété de document ne subsiste',
    typeof j.contexte.sauverJalons === 'undefined' && !/PropertiesService|CLE_JALONS/.test(fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8')));
  configurer([
    { semaine: '2026-s8', texte: '  Revue de définition  ' },
    { semaine: '2026-S02', texte: '' },
    { semaine: 'nawak', texte: 'ignoré' },
    null,
    { semaine: '2026-S40', texte: 'X'.repeat(200) }
  ]);
  const lus = j.contexte.getJalons();
  verifier('les entrées invalides sont écartées', lus.length === 3, String(lus.length));
  verifier('les jalons sont triés par semaine',
    lus.map(x => x.semaine).join(',') === '2026-S02,2026-S08,2026-S40', lus.map(x => x.semaine).join(','));
  verifier('un texte vide reçoit un libellé', lus[0].texte === 'Jalon');
  verifier('un texte est épuré de ses espaces', lus[1].texte === 'Revue de définition');
  verifier('un texte à rallonge est coupé à 60 caractères', lus[2].texte.length === 60);
  verifier('les jalons n\'ont plus d\'identifiant : rien à sauvegarder',
    lus.every(x => Object.keys(x).sort().join(',') === 'semaine,texte'));
  verifier('le paquet envoyé à la page reprend ces jalons',
    JSON.stringify(j.contexte.getDonneesPourClient().jalons) === JSON.stringify(lus));
  configurer([
    { semaine: '2026-S50', texte: 'Base', perimetre: '  BASE/OPTION ' },
    { semaine: '2026-S52', texte: 'Tous', perimetre: '' },
    { semaine: '2027-S01', texte: 'Nul', perimetre: null },
    { semaine: '2027-S02', texte: 'Long', perimetre: 'P'.repeat(80) }
  ]);
  const avecPer = j.contexte.getJalons();
  verifier('le périmètre d\'un jalon voyage, épuré ; vide ou absent, la clé n\'existe pas ; à rallonge, coupé à 40',
    avecPer[0].perimetre === 'BASE/OPTION' && !('perimetre' in avecPer[1]) && !('perimetre' in avecPer[2]) && avecPer[3].perimetre.length === 40,
    JSON.stringify(avecPer));
  verifier('et le paquet envoyé à la page porte ce périmètre tel quel',
    JSON.stringify(j.contexte.getDonneesPourClient().jalons) === JSON.stringify(avecPer));
  /* Le diagnostic confronte les périmètres des jalons à la colonne de domaine
     du premier contrat. La feuille d'exemple n'en a pas : il le dit. La vraie
     structure d'export en a une, « Domaine », à BASE/OPTION et PERSO. */
  configurer([{ semaine: '2026-S50', texte: 'Base', perimetre: 'BASE/OPTION' }]);
  verifier('sans colonne de domaine, le diagnostic prévient que les jalons à périmètre ne feront l\'échéance que sur « Tout »',
    /⚠ 1 jalon\(s\) à périmètre, mais l'onglet « Données » n'a pas de colonne de domaine/.test(j.contexte.diagnostic()), j.contexte.diagnostic());
  configurer(parDefaut);
  const gJal = construire({ gates: true, lignes: 40, historique: false, sortie: 'apercu-gates-jalons.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-gates-jalons.html'));
  const diagConnu = gJal.contexte.diagnostic();
  verifier('sur la vraie structure, les périmètres livrés (BASE/OPTION, PERSO) sont connus de la colonne « Domaine »',
    /périmètres des jalons : BASE\/OPTION, PERSO — tous connus de la colonne « Domaine »/.test(diagConnu), diagConnu);
  vm.runInContext('CONFIG.JALONS = ' + JSON.stringify([
    { semaine: '2026-S50', texte: 'Ailleurs', perimetre: 'MARS' },
    { semaine: '2026-S51', texte: 'Perso', perimetre: 'perso' },
    { semaine: '2026-S52', texte: 'Tous' }
  ]), gJal.contexte);
  const diagPer = gJal.contexte.diagnostic();
  verifier('un périmètre inconnu de la colonne : le diagnostic le dit, jalon par jalon, et donne les valeurs vues ; la casse est indifférente',
    /⚠ Jalon « Ailleurs » : périmètre « MARS » inconnu de la colonne « Domaine »/.test(diagPer) &&
    /→ valeurs vues dans « Domaine » : (BASE\/OPTION, PERSO|PERSO, BASE\/OPTION) — à recopier dans perimetre/.test(diagPer) &&
    !/Jalon « Perso »/.test(diagPer) && !/Jalon « Tous »/.test(diagPer), diagPer);
  const trop = [];
  for (let i = 1; i <= 60; i++) trop.push({ semaine: '2026-S' + String((i % 52) + 1).padStart(2, '0'), texte: 'j' + i });
  configurer(trop);
  verifier('le nombre de jalons est plafonné', j.contexte.getJalons().length === 40);
  vm.runInContext('CONFIG.JALONS = "pas une liste"', j.contexte);
  verifier('une configuration qui n\'est pas une liste donne une liste vide',
    Array.isArray(j.contexte.getJalons()) && j.contexte.getJalons().length === 0);

  // =================================================================
  /* La seconde base : rien tant que CONFIG.RAPPROCHEMENT.FEUILLE est vide.
     Nommée, l'onglet est lu (en-tête = la ligne qui porte la référence,
     sinon la première non vide) et le paquet porte la description que la
     page attend : la référence, les lignes, les colonnes. Rien d'autre ne se
     compare — c'est la page qui croise présence là et avancement ici. On la joue d'abord
     avec un onglet « Base2 » aux colonnes nommées autrement, puis avec SEE
     tel qu'il se colle : titre en ligne 1, en-tête en ligne 3, référence
     sur trois colonnes. */
  section('Rapprochement avec une seconde base');
  verifier('par défaut, la configuration ne nomme aucune seconde base',
    vm.runInContext('CONFIG.RAPPROCHEMENT.FEUILLE === ""', ctxPaquet));
  verifier('mais décrit déjà SEE : la référence sur NAME, SOL. et Cust.V, sans vue essentielle ni champ à comparer — seule la référence sert',
    vm.runInContext('JSON.stringify(CONFIG.RAPPROCHEMENT.CLE_REFERENCE) === \'["NAME","SOL.","Cust.V"]\' && ' +
      'CONFIG.RAPPROCHEMENT.ESSENTIELLES.length === 0 && !("CHAMPS" in CONFIG.RAPPROCHEMENT)', ctxPaquet));
  verifier('le paquet ne porte alors pas de clé « rapprochement »', !('rapprochement' in paquet), Object.keys(paquet).join());
  verifier('getRapprochement rend null', ctxPaquet.getRapprochement(ctxPaquet.SpreadsheetApp.getActiveSpreadsheet()) === null);

  const refs = paquet.plans.slice(0, 3).map(p => p.reference);
  /* L'en-tête est la première ligne non vide : une ligne blanche au-dessus
     ne compte pas, une ligne blanche au milieu non plus. */
  const base2 = new Feuille('Base2', [
    ['', '', '', ''],
    ['REF_UD', 'ATA_CODE', 'STATUT_FWD', 'Colonne en trop'],
    [refs[0].toLowerCase(), paquet.plans[0].ata, 'OK', 'x'],
    ['', '', '', ''],
    [refs[1], '99', 'WIP', ''],
    [refs[2], paquet.plans[2].ata, '', 42],
    ['UD-99-9999', '24', 'TODO', '']
  ]);
  const configRapp = {
    RAPPROCHEMENT: {
      FEUILLE: 'Base2', NOM: '', CLE_REFERENCE: 'ref_ud'
    }
  };
  const avecBase2 = construire({ lignes: 30, feuilles: [base2], config: configRapp, sortie: 'apercu-rapprochement.html' });
  const rapp = avecBase2.paquet.rapprochement;
  verifier('l\'onglet de la seconde base n\'est pas pris pour l\'onglet de données',
    avecBase2.paquet.feuille === 'Données' && avecBase2.paquet.plans.length === 30, avecBase2.paquet.feuille);
  verifier('le paquet porte le rapprochement, nommé d\'après l\'onglet faute de NOM',
    !!rapp && rapp.nom === 'Base2', JSON.stringify(rapp && rapp.nom));
  verifier('la clé de référence est l\'intitulé tel qu\'il est écrit dans l\'onglet',
    rapp && rapp.cleReference === 'REF_UD', rapp && rapp.cleReference);
  verifier('le paquet ne porte aucun champ à comparer : la référence, les lignes, les colonnes, et c\'est tout',
    rapp && !('champs' in rapp) && Object.keys(rapp).sort().join() === 'cleReference,colonnes,essentielles,lignes,nom', JSON.stringify(rapp && Object.keys(rapp)));
  verifier('les lignes : celles sous l\'en-tête, sans les vides, valeurs en chaînes',
    rapp && rapp.lignes.length === 4 && rapp.lignes[0].REF_UD === refs[0].toLowerCase() &&
    rapp.lignes[2].STATUT_FWD === '' && rapp.lignes[2]['Colonne en trop'] === '42' &&
    rapp.lignes[3].REF_UD === 'UD-99-9999', JSON.stringify(rapp && rapp.lignes));
  verifier('les colonnes de l\'onglet, dans son ordre, et pas de vue essentielle faute d\'ESSENTIELLES',
    rapp && rapp.colonnes.join('|') === 'REF_UD|ATA_CODE|STATUT_FWD|Colonne en trop' && JSON.stringify(rapp.essentielles) === '[]',
    JSON.stringify(rapp && [rapp.colonnes, rapp.essentielles]));
  verifier('le paquet reste sérialisable pour la page', /"rapprochement":\{/.test(avecBase2.contexte.donneesJSONPourPage()));
  /* Un onglet nommé mais absent : pas de section, pas d'erreur — la page s'ouvre. */
  const sansOnglet = construire({ lignes: 10, config: { RAPPROCHEMENT: { FEUILLE: 'Nulle part', CLE_REFERENCE: 'REF' } }, sortie: 'apercu-rapprochement-absent.html' });
  verifier('un onglet nommé mais introuvable : le paquet reste valide, sans rapprochement',
    sansOnglet.paquet.ok === true && !('rapprochement' in sansOnglet.paquet));
  /* Une référence introuvable dans l'en-tête : rien à apparier, donc rien. */
  const sansCleRef = construire({ lignes: 10, feuilles: [base2], config: { RAPPROCHEMENT: { FEUILLE: 'Base2', CLE_REFERENCE: 'Pas là' } }, sortie: 'apercu-rapprochement-absent.html' });
  verifier('une clé de référence introuvable dans l\'onglet : pas de rapprochement',
    sansCleRef.paquet.ok === true && !('rapprochement' in sansCleRef.paquet));
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-rapprochement-absent.html'));

  /* SEE tel qu'il se colle : le titre en ligne 1, une ligne vide, l'en-tête
     en ligne 3 ; la référence sur trois colonnes, la solution réduite à « 1 »
     par Excel, l'indice en minuscule ; des cases à cocher TRUE / FALSE. Le
     serveur rend l'onglet tel quel : c'est la page qui recompose. */
  const see = new Feuille('SEE', [
    ['Nommage WD BFLOW', '', '', '', ''],
    ['', '', '', '', ''],
    ['NAME', 'SOL.', 'Cust.V', 'Validated', 'REDRAW'],
    ['CAB181A0005', '1', 'b', 'TRUE', 'FALSE'],
    ['', '', '', '', ''],
    ['HAR253A0011', '002', 'C', 'FALSE', 'TRUE']
  ]);
  const configSEE = { RAPPROCHEMENT: {
    FEUILLE: 'SEE', NOM: '', CLE_REFERENCE: ['name', 'sol.', 'cust.v'],
    ESSENTIELLES: ['NAME', 'Validated', 'Introuvable']
  } };
  const avecSEE = construire({ lignes: 10, feuilles: [see], config: configSEE, sortie: 'apercu-see.html' });
  /* Sans rien configurer, un onglet nommé comme la base — « SEE » — est pris
     pour la seconde base, et n'est pas compté comme un contrat. C'est ainsi
     qu'on la met en place sans toucher au code. */
  const seeParNom = construire({ lignes: 10, feuilles: [see], sortie: 'apercu-see-nom.html' });
  verifier('un onglet « SEE » est reconnu par son nom, sans toucher à la configuration',
    !!seeParNom.paquet.rapprochement && seeParNom.paquet.rapprochement.lignes.length === 2,
    JSON.stringify(seeParNom.paquet.rapprochement && seeParNom.paquet.rapprochement.lignes.length));
  verifier('et il n\'apparaît pas dans la liste des contrats',
    !seeParNom.paquet.contrats.some(c => /^see$/i.test(c.id)), JSON.stringify(seeParNom.paquet.contrats));
  /* Le diagnostic dit ce que le script voit de la seconde base — c'est la
     réponse à « je ne vois pas les deux cercles » : l'onglet lu et compté,
     l'onglet absent (et le geste qui manque), l'onglet vide, l'onglet dont
     l'en-tête ne porte pas la référence (et les en-têtes lus). */
  const diagSEE = seeParNom.contexte.diagnostic();
  verifier('le diagnostic compte la seconde base : onglet, lignes, référence, ligne d\'en-têtes',
    /✓ Seconde base « SEE » : onglet « SEE », 2 ligne\(s\), référence NAME \+ SOL\. \+ Cust\.V \(ligne d'en-têtes : 3\)/.test(diagSEE), diagSEE);
  const diagSans = ctxPaquet.diagnostic();
  verifier('sans onglet SEE, le diagnostic le dit, et dit le geste : un onglet « SEE », l\'extract en A1, ses colonnes',
    /– Seconde base « SEE » : aucun onglet « SEE » — pas de rapprochement\./.test(diagSans) &&
    /→ un onglet nommé « SEE », l'extract collé en A1 tel quel, avec ses colonnes NAME, SOL\., Cust\.V\./.test(diagSans) &&
    /Tout est en place : Suivi FWD/.test(diagSans), diagSans);
  const seeVide = construire({ lignes: 10, feuilles: [new Feuille('SEE', [])], historique: false, sortie: 'apercu-see-vide.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-vide.html'));
  const diagVide = seeVide.contexte.diagnostic();
  verifier('un onglet SEE vide : pas de rapprochement, le diagnostic le dit, et le bilan ne conclut pas « tout est en place » sans réserve',
    !('rapprochement' in seeVide.paquet) && /⚠ Seconde base « SEE » : l'onglet « SEE » est vide — pas de rapprochement\./.test(diagVide) &&
    /Tout est en place pour GATES .* La seconde base, elle, ne se lit pas/.test(diagVide) && !/Tout est en place : Suivi/.test(diagVide), diagVide);
  const diagRef = sansCleRef.contexte.diagnostic();
  verifier('une référence introuvable, et aucun intitulé voulu dans la ligne prise pour en-tête : le diagnostic nomme l\'onglet et la référence cherchée, compte les cellules sans les recopier',
    /⚠ Seconde base « Base2 » : onglet « Base2 » trouvé, mais la référence \(Pas là\) est introuvable dans ses 8 premières lignes/.test(diagRef) &&
    /ligne 2 prise pour en-tête : 4 cellule\(s\), aucune ne porte Pas là — l'extract est-il collé avec ses en-têtes \?/.test(diagRef) &&
    !/en-têtes lus|REF_UD/.test(diagRef), diagRef);
  /* Une référence à moitié trouvée (une colonne renommée) : la ligne est
     bien un en-tête, le diagnostic la recopie pour qu'on voie ce qui manque. */
  const moitie = construire({ lignes: 10, feuilles: [base2], historique: false, config: { RAPPROCHEMENT: { FEUILLE: 'Base2', CLE_REFERENCE: ['REF_UD', 'Pas là'] } }, sortie: 'apercu-see-moitie.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-moitie.html'));
  const diagMoitie = moitie.contexte.diagnostic();
  verifier('une référence à moitié trouvée : la ligne d\'en-têtes est recopiée, pour voir l\'intitulé qui manque',
    !('rapprochement' in moitie.paquet) &&
    /⚠ Seconde base « Base2 » : onglet « Base2 » trouvé, mais la référence \(REF_UD \+ Pas là\) est introuvable/.test(diagMoitie) &&
    /en-têtes lus \(ligne 2\) : REF_UD \| ATA_CODE \| STATUT_FWD \| Colonne en trop/.test(diagMoitie), diagMoitie);
  /* La vraie forme de l'extract SEE — titre en ligne 1, ligne vide, en-têtes
     en ligne 3 — avec une colonne renommée dans l'export. L'en-tête est bien
     là : le diagnostic doit montrer la ligne 3 et l'intitulé qui manque, et
     non le titre de la ligne 1 en demandant si l'extract est collé entier. */
  const seeRenommee = construire({ lignes: 10, historique: false, sortie: 'apercu-see-renommee.html', feuilles: [new Feuille('SEE', [
    ['Nommage WD BFLOW', '', '', '', ''],
    ['', '', '', '', ''],
    ['NAME', 'SOL.', 'Cust. Version', 'Validated', 'REDRAW'],
    ['CAB181A0005', '1', 'b', 'TRUE', 'FALSE']
  ])] });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-renommee.html'));
  const diagRenommee = seeRenommee.contexte.diagnostic();
  verifier('une colonne renommée dans l\'export : le diagnostic montre la ligne des en-têtes, pas le titre, et nomme l\'intitulé qui manque',
    /en-têtes lus \(ligne 3\) : NAME \| SOL\. \| Cust\. Version \| Validated \| REDRAW/.test(diagRenommee) &&
    /il manque Cust\.V — cette colonne a-t-elle un autre intitulé dans l'export \?/.test(diagRenommee) &&
    !/collé avec ses en-têtes|Nommage WD BFLOW/.test(diagRenommee), diagRenommee);
  /* L'extract collé SANS ses en-têtes : la ligne prise pour en-tête est une
     ligne de données. Le diagnostic n'en recopie aucune cellule — il compte,
     et pose la question. */
  const seeSansEntetes = construire({ lignes: 10, historique: false, sortie: 'apercu-see-sans-entetes.html', feuilles: [new Feuille('SEE', [
    ['CAB181A0005', '1', 'b', 'Libellé confidentiel du plan', 'TRUE'],
    ['HAR253A0011', '002', 'C', 'Un autre libellé', 'FALSE']
  ])] });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-sans-entetes.html'));
  const diagNu = seeSansEntetes.contexte.diagnostic();
  verifier('collé sans en-têtes : le diagnostic compte les cellules de la ligne prise pour en-tête, sans en recopier une seule',
    /⚠ Seconde base « SEE » : onglet « SEE » trouvé, mais la référence \(NAME \+ SOL\. \+ Cust\.V\) est introuvable/.test(diagNu) &&
    /ligne 1 prise pour en-tête : 5 cellule\(s\), aucune ne porte NAME, SOL\., Cust\.V — l'extract est-il collé avec ses en-têtes \?/.test(diagNu) &&
    !/CAB181A0005|Libellé confidentiel|en-têtes lus/.test(diagNu), diagNu);
  /* Une configuration à moitié faite : le diagnostic nomme ce qui manque. */
  const cfgSansRef = construire({ lignes: 10, feuilles: [see], historique: false, config: { RAPPROCHEMENT: { FEUILLE: '', NOM: 'SEE', CLE_REFERENCE: [] } }, sortie: 'apercu-see-sans-ref.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-sans-ref.html'));
  const cfgSansNom = construire({ lignes: 10, feuilles: [see], historique: false, config: { RAPPROCHEMENT: { FEUILLE: '', NOM: '', CLE_REFERENCE: ['NAME'] } }, sortie: 'apercu-see-sans-nom.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-sans-nom.html'));
  verifier('sans référence configurée, ou sans nom d\'onglet : pas de rapprochement, et le diagnostic dit lequel des deux manque',
    !('rapprochement' in cfgSansRef.paquet) && /– Seconde base : aucune référence \(RAPPROCHEMENT\.CLE_REFERENCE vide\) — pas de rapprochement\./.test(cfgSansRef.contexte.diagnostic()) &&
    !('rapprochement' in cfgSansNom.paquet) && /– Seconde base : aucun nom d'onglet \(RAPPROCHEMENT\.FEUILLE et NOM vides\) — pas de rapprochement\./.test(cfgSansNom.contexte.diagnostic()),
    cfgSansRef.contexte.diagnostic() + '\n' + cfgSansNom.contexte.diagnostic());
  /* La forme rendue par lireSecondeBase, dans deux états. */
  const formeOk = seeParNom.contexte.lireSecondeBase(seeParNom.contexte.SpreadsheetApp.getActiveSpreadsheet());
  const formeVide = seeVide.contexte.lireSecondeBase(seeVide.contexte.SpreadsheetApp.getActiveSpreadsheet());
  verifier('lireSecondeBase rend { etat, onglet, cles, entetes, ligneEntete, rapprochement } — ligneEntete à 3 pour SEE, null pour un onglet vide',
    Object.keys(formeOk).sort().join() === 'cles,entetes,etat,ligneEntete,onglet,rapprochement' &&
    formeOk.etat === 'ok' && formeOk.onglet === 'SEE' && formeOk.ligneEntete === 3 && formeOk.entetes.join('|') === 'NAME|SOL.|Cust.V|Validated|REDRAW' &&
    formeVide.etat === 'vide' && formeVide.ligneEntete === null && formeVide.rapprochement === null && formeVide.cles.join() === 'NAME,SOL.,Cust.V',
    JSON.stringify([Object.keys(formeOk), formeOk.etat, formeOk.ligneEntete, formeVide]));
  const rSEE = avecSEE.paquet.rapprochement;
  verifier('SEE : l\'en-tête est la ligne 3, celle qui porte NAME, SOL. et Cust.V — pas le titre « Nommage WD BFLOW »',
    !!rSEE && rSEE.lignes.length === 2 && rSEE.colonnes.join('|') === 'NAME|SOL.|Cust.V|Validated|REDRAW',
    JSON.stringify(rSEE && [rSEE.lignes.length, rSEE.colonnes]));
  verifier('la référence est la liste des trois intitulés, tels qu\'ils sont écrits dans l\'onglet',
    !!rSEE && JSON.stringify(rSEE.cleReference) === '["NAME","SOL.","Cust.V"]', JSON.stringify(rSEE && rSEE.cleReference));
  verifier('les essentielles sont résolues, l\'introuvable écartée',
    !!rSEE && rSEE.essentielles.join('|') === 'NAME|Validated', JSON.stringify(rSEE && rSEE.essentielles));
  verifier('les valeurs restent celles de l\'onglet — « 1 », « b », TRUE — c\'est la page qui recompose',
    !!rSEE && rSEE.lignes[0]['SOL.'] === '1' && rSEE.lignes[0]['Cust.V'] === 'b' && rSEE.lignes[1].REDRAW === 'TRUE',
    JSON.stringify(rSEE && rSEE.lignes));
  verifier('nommée d\'après l\'onglet faute de NOM', !!rSEE && rSEE.nom === 'SEE');
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see.html'));

  // =================================================================
  /* Le dépôt automatique : un script envoie un extract à l'application web
     (doPost → deposer). Refusé tant que la configuration n'a pas de secret,
     refusé sans le bon secret, refusé vers un onglet d'historique ; sinon
     l'onglet est vidé et réécrit, et le relevé de la semaine archivé pour ce
     contrat si on le demande. */
  section('Dépôt automatique (doPost)');
  const depotFerme = construire({ lignes: 12, historique: false, sortie: 'apercu-depot.html' });
  const cD = depotFerme.contexte;
  const envoi = (ctx, corps) => ctx.deposer(typeof corps === 'string' ? corps : JSON.stringify(corps));
  verifier('par défaut, aucun secret : tout dépôt est refusé, et le message le dit',
    envoi(cD, { secret: '', onglet: 'Données', lignes: [] }).ok === false &&
    /Dépôt désactivé/.test(envoi(cD, { secret: 'x', onglet: 'Données', lignes: [] }).message));
  const depot = construire({ lignes: 12, historique: false, config: { DEPOT: { SECRET: 'phrase longue et imprévisible', MAX_LIGNES: 50 }, RAPPROCHEMENT: { FEUILLE: 'SEE', NOM: 'SEE', CLE_REFERENCE: ['NAME', 'SOL.', 'Cust.V'], ESSENTIELLES: [] } }, sortie: 'apercu-depot.html' });
  const cO = depot.contexte, clO = cO.SpreadsheetApp.getActiveSpreadsheet();
  const S = 'phrase longue et imprévisible';
  verifier('un mauvais secret est refusé', envoi(cO, { secret: 'autre', onglet: 'Données', lignes: [] }).message === 'Secret refusé.');
  verifier('un corps illisible est refusé sans planter',
    /illisible/.test(envoi(cO, 'pas du json').message) && /illisible/.test(envoi(cO, '[1,2]').message) && /illisible/.test(envoi(cO, '').message));
  verifier('sans onglet, sans lignes : refusés, chacun avec son message',
    envoi(cO, { secret: S, lignes: [] }).message === 'Onglet non nommé.' &&
    /Lignes absentes/.test(envoi(cO, { secret: S, onglet: 'Données' }).message));
  verifier('trop de lignes : refusé (garde-fou MAX_LIGNES)',
    /Trop de lignes : 51/.test(envoi(cO, { secret: S, onglet: 'Données', lignes: new Array(51).fill(['a']) }).message));
  /* Le cas qui détruirait tout : un extract vide. L'onglet ne doit PAS être
     vidé — sinon un export raté effacerait le contrat. */
  const avantVide = cO.getDonneesPourClient('Données').plans.length;
  const refusVide = envoi(cO, { secret: S, onglet: 'Données', lignes: [] });
  const refusSansColonne = envoi(cO, { secret: S, onglet: 'Données', lignes: [[], []] });
  verifier('un extract vide est refusé AVANT que l\'onglet soit touché : les plans sont toujours là',
    refusVide.ok === false && /vide/.test(refusVide.message) && /pas touché/.test(refusVide.message) &&
    refusSansColonne.ok === false && /colonne/.test(refusSansColonne.message) &&
    cO.getDonneesPourClient('Données').plans.length === avantVide,
    JSON.stringify([refusVide, refusSansColonne, avantVide]));
  verifier('un onglet réservé au script n\'est pas une cible non plus',
    /réservé au script/.test(envoi(cO, { secret: S, onglet: 'Paramètres', creer: true, lignes: [['x']] }).message) &&
    clO.getSheetByName('Paramètres') === null,
    envoi(cO, { secret: S, onglet: 'Paramètres', creer: true, lignes: [['x']] }).message);
  verifier('un onglet introuvable n\'est pas créé sans le demander',
    /introuvable/.test(envoi(cO, { secret: S, onglet: 'SEE', lignes: [['NAME']] }).message) && clO.getSheetByName('SEE') === null);
  const creation = envoi(cO, { secret: S, onglet: 'SEE', creer: true, lignes: [['Nommage WD BFLOW'], [], ['NAME', 'SOL.', 'Cust.V'], ['TFE2130A600', 1, 'a', 'en trop']] });
  verifier('avec creer, l\'onglet est créé et rempli : lignes de longueurs inégales, nombres, cellules vides — tout devient du texte, à la même largeur',
    creation.ok === true && creation.onglet === 'SEE' && creation.lignes === 4 && creation.colonnes === 4 &&
    JSON.stringify(clO.getSheetByName('SEE').getDataRange().getDisplayValues()) ===
      JSON.stringify([['Nommage WD BFLOW', '', '', ''], ['', '', '', ''], ['NAME', 'SOL.', 'Cust.V', ''], ['TFE2130A600', '1', 'a', 'en trop']]),
    JSON.stringify(creation));
  const prefixeHisto = vm.runInContext('CONFIG.FEUILLE_HISTORIQUE', cO);
  verifier('un onglet d\'historique n\'est jamais une cible',
    /historique/.test(envoi(cO, { secret: S, onglet: prefixeHisto + ' Données', creer: true, lignes: [['x']] }).message) &&
    /historique/.test(envoi(cO, { secret: S, onglet: prefixeHisto, creer: true, lignes: [['x']] }).message));
  /* Le nom se retrouve comme partout ailleurs : « données » sans accent ni
     majuscule désigne le même onglet, et n'en crée pas un second. */
  const avantNoms = clO.getSheets().length;
  const casse = envoi(cO, { secret: S, onglet: 'donnees', creer: true, lignes: feuilleExemple(6) });
  verifier('un nom d\'onglet sans accent ni majuscule retrouve le même onglet, au lieu d\'en créer un doublon',
    casse.ok && casse.onglet === 'Données' && clO.getSheets().length === avantNoms,
    JSON.stringify([casse.onglet, avantNoms, clO.getSheets().length]));
  /* Une cellule qui commence par « = » ne doit pas devenir une formule. */
  envoi(cO, { secret: S, onglet: 'Données', lignes: [['Réf', 'Note'], ['=1+1', '=SOMME(A:A)']] });
  verifier('l\'onglet est passé en format texte : une cellule « =… » reste du texte, pas une formule',
    clO.getSheetByName('Données').formats[0] === '@' && clO.getSheetByName('Données').formats[1] === '@',
    JSON.stringify(clO.getSheetByName('Données').formats));
  /* Plus de lignes que la grille n'en a : la grille s'agrandit, comme pour les colonnes. */
  const grand = envoi(cO, { secret: S, onglet: 'Grand', creer: true, lignes: new Array(40).fill(['a', 'b']) });
  const feuilleGrande = clO.getSheetByName('Grand');
  feuilleGrande.lignesGrille = 5;                    // une grille étroite, comme un onglet neuf
  const encore = envoi(cO, { secret: S, onglet: 'Grand', lignes: new Array(40).fill(['a', 'b']) });
  verifier('un extract plus long que la grille l\'agrandit au lieu d\'échouer',
    grand.ok && encore.ok && encore.lignes === 40 && feuilleGrande.getDataRange().getDisplayValues().length === 40,
    JSON.stringify([grand.ok, encore, feuilleGrande.getMaxRows()]));
  /* Le geste hebdomadaire par le script : l'onglet du contrat reçoit un
     nouvel export (8 plans au lieu de 12), puis le relevé de la semaine. */
  const avantDepot = cO.getDonneesPourClient('Données').plans.length;
  const hebdo = envoi(cO, { secret: S, onglet: 'Données', lignes: feuilleExemple(8), archiver: true });
  const apresDepot = cO.getDonneesPourClient('Données');
  verifier('déposer sur l\'onglet du contrat remplace l\'export : ' + avantDepot + ' plans avant, 8 après, colonnes détectées comme d\'habitude',
    hebdo.ok === true && avantDepot !== 8 && apresDepot.plans.length === 8 && apresDepot.cleDate === 'date_creation',
    JSON.stringify([avantDepot, hebdo, apresDepot.plans.length]));
  verifier('et archive le relevé de la semaine pour ce contrat : une ligne d\'historique, aux comptes du nouvel export',
    hebdo.archive && hebdo.archive.ok === true && hebdo.archive.total === 8 && /^\d{4}-S\d{2}$/.test(hebdo.archive.semaine) &&
    apresDepot.releves.length === 1 && apresDepot.releves[0].total === 8 && apresDepot.releves[0].semaine === hebdo.archive.semaine,
    JSON.stringify([hebdo.archive, apresDepot.releves.length]));
  const hebdo2 = envoi(cO, { secret: S, onglet: 'Données', lignes: feuilleExemple(9), archiver: true });
  verifier('redéposer la même semaine met la ligne à jour au lieu d\'en empiler une seconde',
    hebdo2.ok && hebdo2.archive.total === 9 && cO.getDonneesPourClient('Données').releves.length === 1 &&
    cO.getDonneesPourClient('Données').releves[0].total === 9, JSON.stringify(hebdo2.archive));
  const surSEE = envoi(cO, { secret: S, onglet: 'SEE', lignes: [['NAME', 'SOL.', 'Cust.V']], archiver: true });
  verifier('demander l\'archivage sur l\'onglet de la seconde base — qui n\'est pas un contrat — écrit quand même, mais dit qu\'il n\'y a rien à archiver',
    surSEE.ok === true && surSEE.archive && surSEE.archive.ok === false && /pas un onglet de contrat/.test(surSEE.archive.message), JSON.stringify(surSEE));
  const reponse = cO.doPost({ postData: { contents: JSON.stringify({ secret: S, onglet: 'Données', lignes: feuilleExemple(5) }) } });
  verifier('doPost répond en JSON, avec le même résultat',
    reponse.getMimeType() === 'application/json' && JSON.parse(reponse.getContent()).ok === true && JSON.parse(reponse.getContent()).lignes === feuilleExemple(5).length,
    reponse.getContent());
  verifier('doPost sans corps répond par un refus lisible, jamais une exception',
    JSON.parse(cO.doPost(undefined).getContent()).ok === false && /illisible/.test(JSON.parse(cO.doPost({}).getContent()).message));
  /* Même quand le classeur lâche : doPost répond du JSON, jamais une page
     d'erreur HTML que le script appelant ne saurait pas lire. */
  const classeurCasse = { getSheetByName: function () { throw new Error('Classeur indisponible'); },
                          getSheets: function () { throw new Error('Classeur indisponible'); },
                          insertSheet: function () { throw new Error('Classeur indisponible'); } };
  const vraiClasseur = cO.SpreadsheetApp.getActiveSpreadsheet;
  cO.SpreadsheetApp.getActiveSpreadsheet = function () { return classeurCasse; };
  const panne = cO.doPost({ postData: { contents: JSON.stringify({ secret: S, onglet: 'Données', lignes: [['a']] }) } });
  cO.SpreadsheetApp.getActiveSpreadsheet = vraiClasseur;
  verifier('une panne du classeur devient un refus en JSON, jamais une page d\'erreur',
    panne.getMimeType() === 'application/json' && JSON.parse(panne.getContent()).ok === false &&
    /indisponible/.test(JSON.parse(panne.getContent()).message), panne.getContent());
  /* MAX_LIGNES à zéro ferme le dépôt : il ne doit pas rouvrir en grand. */
  const ferme = construire({ lignes: 8, historique: false, config: { DEPOT: { SECRET: S, MAX_LIGNES: 0 } }, sortie: 'apercu-depot.html' });
  verifier('MAX_LIGNES à zéro ferme le dépôt au lieu de revenir à la valeur par défaut',
    /Trop de lignes : 1 \(au plus 0\)/.test(ferme.contexte.deposer(JSON.stringify({ secret: S, onglet: 'Données', lignes: [['a']] })).message),
    ferme.contexte.deposer(JSON.stringify({ secret: S, onglet: 'Données', lignes: [['a']] })).message);
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-depot.html'));

  // =================================================================
  section('Feuilles hostiles');
  const sansFWD = serveurSur([
    ['Réf', 'Chose', 'Machin'],
    ['A-1', 'x', 'y'],
    ['A-2', 'z', 'w']
  ]);
  const pSansFWD = sansFWD.contexte.getDonneesPourClient();
  verifier('sans colonne d\'avancement, la page est quand même servie',
    pSansFWD.ok === true && pSansFWD.plans.length === 2);
  verifier('et le message le dit', /avancement FWD/.test(pSansFWD.message), pSansFWD.message);
  verifier('tous les plans sont alors « non renseignés »',
    pSansFWD.plans.every(p => p.avancement === ''));

  const vide = serveurSur([]);
  const pVide = vide.contexte.getDonneesPourClient();
  verifier('une feuille vide renvoie une erreur lisible, pas une exception — qui nomme l\'onglet vide et dit le geste',
    pVide.ok === false && /« Données » est vide — coller l'export GATES en A1/.test(pVide.message), pVide.message);
  verifier('et le paquet d\'erreur porte une liste de contrats vide',
    Array.isArray(pVide.contrats) && pVide.contrats.length === 0 && pVide.contrat === '');

  const doublons = serveurSur([
    ['Réf', 'Statut', 'Statut', 'Avancement FWD'],
    ['A-1', 'ok', 'ko', '100%'],
    ['A-2', 'ok', 'ko', '']
  ]);
  const pDoublons = doublons.contexte.getDonneesPourClient();
  const cles = pDoublons.colonnes.map(c => c.cle);
  verifier('deux colonnes du même nom reçoivent des clés distinctes',
    new Set(cles).size === cles.length, JSON.stringify(cles));
  verifier('les deux valeurs restent lisibles',
    pDoublons.plans[0][cles[1]] === 'ok' && pDoublons.plans[0][cles[2]] === 'ko');

  const sansRef = serveurSur([
    ['Truc', 'Avancement FWD'],
    ['', '100%'],
    ['', '50%']
  ]);
  const pSansRef = sansRef.contexte.getDonneesPourClient();
  verifier('sans référence lisible, une référence de repli est fabriquée',
    pSansRef.plans[0].reference && pSansRef.plans[1].reference &&
    pSansRef.plans[0].reference !== pSansRef.plans[1].reference,
    JSON.stringify(pSansRef.plans.map(p => p.reference)));

  const entetesBizarres = serveurSur([
    ['123', 'Été / Hiver', '   ', 'Avancement FWD'],
    ['a', 'b', 'c', '50%']
  ]);
  const pBizarres = entetesBizarres.contexte.getDonneesPourClient();
  verifier('des en-têtes numériques ou vides donnent des clés utilisables',
    pBizarres.colonnes.every(c => /^[a-z_][a-z0-9_]*$/.test(c.cle)),
    JSON.stringify(pBizarres.colonnes.map(c => c.cle)));

  // =================================================================
  section('Diagnostic');
  /* C'est la fonction qu'on lance quand « ça ne marche pas » : elle doit
     nommer la cause, pas se contenter d'échouer. */
  const dOk = serveurSur(feuilleExemple(30));
  dOk.contexte.enregistrerInstantaneHebdo();
  const rapportOk = dOk.contexte.diagnostic();
  verifier('le diagnostic nomme le classeur et l\'onglet',
    /Classeur/.test(rapportOk) && /Onglet de données/.test(rapportOk));
  verifier('il nomme la colonne d\'avancement',
    /Avancement FWD : colonne/.test(rapportOk), rapportOk.split('\n').find(l => /Avancement/.test(l)));
  verifier('il donne les quatre comptes',
    /terminés, \d+ en cours, \d+ à faire, \d+ non renseignés/.test(rapportOk));
  verifier('il compte les relevés archivés', /Relevés archivés : 1/.test(rapportOk));
  verifier('il donne le poids du paquet', /Paquet envoyé à la page : \d+ Ko/.test(rapportOk));
  verifier('il conclut que tout est en place', /Tout est en place/.test(rapportOk));
  verifier('il passe aussi par l\'alerte à l\'écran (après celle de l\'archivage)',
    dOk.contexte.__alertes.length === 2 && dOk.contexte.__alertes[1] === rapportOk && /^Relevé .* archivé : Données \(30 plans\)/.test(dOk.contexte.__alertes[0]),
    JSON.stringify(dOk.contexte.__alertes.map(a => a.slice(0, 60))));

  const dSansFichiers = serveurSur(feuilleExemple(10), {}, ['Index']);
  const rapportSansFichiers = dSansFichiers.contexte.diagnostic();
  verifier('un fichier HTML manquant est nommé',
    /« Styles » INTROUVABLE/.test(rapportSansFichiers) &&
    /« Javascript » INTROUVABLE/.test(rapportSansFichiers));
  verifier('et la marche à suivre est donnée',
    /sans \.html/.test(rapportSansFichiers));
  verifier('il ne conclut pas que tout va bien',
    /Il manque des fichiers/.test(rapportSansFichiers));

  const dVide = serveurSur([]);
  verifier('un classeur dont le seul onglet est vide est diagnostiqué : l\'onglet nommé, et le geste',
    /Onglet de données : Aucun onglet de données exploitable dans ce classeur : « Données » est vide — coller l'export GATES en A1/.test(dVide.contexte.diagnostic()),
    dVide.contexte.diagnostic());

  const dSansFWD = serveurSur([['Réf', 'Truc'], ['A-1', 'x']]);
  const rapportSansFWD = dSansFWD.contexte.diagnostic();
  verifier('l\'absence de colonne d\'avancement est signalée',
    /Aucune colonne d'avancement FWD/.test(rapportSansFWD));
  verifier('et la conséquence est expliquée',
    /tout sera « non renseigné »/.test(rapportSansFWD));

  const dSansHisto = serveurSur(feuilleExemple(10));
  verifier('l\'absence de relevé est signalée avec la marche à suivre',
    /Relevés archivés : 0/.test(dSansHisto.contexte.diagnostic()) &&
    /Archiver le relevé/.test(dSansHisto.contexte.diagnostic()));

  const dOrphelin = { contexte: chargerServeur(null, {}) };
  const rapportOrphelin = dOrphelin.contexte.diagnostic();
  verifier('un script non lié au classeur est la première chose dite',
    /AUCUN CLASSEUR ATTACHÉ/.test(rapportOrphelin));
  verifier('et la vraie marche à suivre est donnée',
    /Extensions → Apps Script/.test(rapportOrphelin));

  // =================================================================
  section('La page rendue par Apps Script');
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const p = await ctx.newPage();
  p.on('pageerror', e => erreursJS.push(e.message));
  p.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push(m.text()); });
  await p.goto('file://' + path.join(__dirname, '..', 'apercu-addon.html'));
  await p.waitForTimeout(1600);

  const vu = await p.evaluate(() => ({
    semaine: document.getElementById('num-semaine').textContent,
    dates: document.getElementById('dates-semaine').textContent,
    titreSemaine: document.querySelector('.masthead').textContent.replace(/\s+/g, ' '),
    sansMention: !document.getElementById('releve-semaine'),
    repere: ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '',
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    familles: [...document.querySelectorAll('#etats .etat-btn')].map(b => b.dataset.famille),
    libelles: [...document.querySelectorAll('#etats .etat-haut')].map(b => b.textContent.trim()),
    colonnes: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    dims: [...document.querySelectorAll('#dim-critique option')].map(o => o.value),
    dimActive: document.getElementById('dim-critique').value,
    titre: document.getElementById('titre-groupe').textContent,
    groupes: document.querySelectorAll('.critique-ligne').length,
    totauxGroupes: [...document.querySelectorAll('.critique-total')].map(t => +t.textContent),
    jalons: document.querySelectorAll('.jalon-poignee, .jalon-supp, #saisie-jalon').length,
    releves: document.querySelectorAll('.zone-clic').length > 0,
    importe: document.getElementById('import').textContent
  }));
  /* Le gabarit archive la semaine en cours : la page doit donc afficher
     cette semaine-là, se taire sur le dernier relevé, et dire « aujourd'hui »
     sur la courbe. Le numéro attendu est recalculé ici, pas lu dans la page. */
  const semAttendue = (() => {
    const n = new Date(), j = new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()));
    const jour = j.getUTCDay() || 7, t = new Date(j.getTime() + (4 - jour) * 86400000);
    return 'Semaine ' + Math.ceil(((t.getTime() - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86400000 + 1) / 7);
  })();
  verifier('la semaine affichée est celle d’aujourd’hui, au numéro près', vu.semaine === semAttendue, vu.semaine + ' vs ' + semAttendue);
  verifier('le titre ne porte que la semaine d’aujourd’hui, sans mention du dernier relevé, et la courbe dit « aujourd’hui »',
    vu.sansMention && !/dernier relevé/.test(vu.titreSemaine) && vu.repere === 'aujourd’hui', JSON.stringify([vu.sansMention, vu.repere]));
  verifier('les dates de la semaine sont écrites en toutes lettres',
    /^du \d+ .* \d{4}$/.test(vu.dates), vu.dates);
  verifier('les quatre états totalisent les 186 plans',
    vu.etats.reduce((a, b) => a + b, 0) === 186, JSON.stringify(vu.etats));
  verifier('aucun état n\'est vide de sens', vu.etats.every(n => n >= 0));
  verifier('les en-têtes du tableau sont ceux de la feuille, référence en tête',
    vu.colonnes[0] === 'Référence UD' && vu.colonnes.indexOf('Avancement FWD') !== -1,
    JSON.stringify(vu.colonnes));
  verifier('les 186 lignes sont dans le tableau', vu.lignes === 186, String(vu.lignes));
  /* La recherche du haut, sur les données du classeur : même barre, même
     fiche que dans la démonstration. La référence est lue dans la première
     cellule du tableau, pas fabriquée. */
  const refReelle = await p.evaluate(() => document.querySelector('#corps-tableau tr td').textContent.trim());
  await p.click('#champ-plan'); await p.keyboard.type(refReelle); await p.waitForTimeout(250);
  await p.keyboard.press('Enter'); await p.waitForTimeout(400);
  const ficheReelle = await p.evaluate(() => {
    const f = document.getElementById('fiche-plan');
    return { visible: !f.hidden, ref: f.querySelector('.fiche-ref') ? f.querySelector('.fiche-ref').textContent.replace(/\s+/g, '') : '',
             titres: [...f.querySelectorAll('.fiche-bloc h3')].map(h => h.textContent) };
  });
  verifier('données réelles : la recherche du haut trouve un plan du classeur et ouvre sa fiche, semaine par semaine comprise',
    ficheReelle.visible && ficheReelle.ref === refReelle.replace(/\s+/g, '') && ficheReelle.titres.indexOf('Semaine par semaine') !== -1,
    JSON.stringify([refReelle, ficheReelle]));
  await p.click('#fiche-plan [data-fiche-fermer]'); await p.waitForTimeout(150);
  await p.fill('#champ-plan', ''); await p.keyboard.press('Escape');
  verifier('le sélecteur de dimension propose les colonnes détectées', vu.dims.length >= 3, JSON.stringify(vu.dims));
  verifier('l\'ATA est ouvert par défaut', vu.dimActive === 'ata', vu.dimActive);
  verifier('le titre nomme la dimension', /par ATA/.test(vu.titre), vu.titre);
  verifier('le bloc par ATA est rempli', vu.groupes >= 2, String(vu.groupes));
  verifier('la somme des plans par groupe fait 186',
    vu.totauxGroupes.reduce((a, b) => a + b, 0) === 186, String(vu.totauxGroupes.reduce((a, b) => a + b, 0)));
  verifier('le graphique a de quoi tracer', vu.releves);
  verifier('la ligne d\'import annonce les relevés archivés', /relevés archivés/.test(vu.importe), vu.importe);
  verifier('rien ne permet d\'éditer un jalon dans la page', vu.jalons === 0);
  /* Les jalons de CONFIG sont dessinés — ceux qui tombent après le premier
     relevé, puisque l'axe du graphique part de là. Sur « Tout », la fenêtre
     s'étend jusqu'au dernier jalon. */
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  const attendus = paquet.jalons.filter(x => x.semaine >= paquet.releves[0].semaine);
  const jalonsPage = await p.evaluate(() => [...document.querySelectorAll('.jalon .jalon-texte')].map(t => t.textContent));
  verifier('la page affiche les jalons de la configuration',
    jalonsPage.length === attendus.length && attendus.every(x => jalonsPage.indexOf(x.texte) !== -1),
    JSON.stringify(jalonsPage) + ' pour ' + JSON.stringify(attendus.map(x => x.texte)));
  verifier('la configuration livrée en met cinq à l\'écran', jalonsPage.length === 5, String(jalonsPage.length));

  /* Un seul contrat : le sélecteur n'a rien à proposer, il reste caché — et
     le titre ne nomme jamais le contrat. */
  const contratAddon = await p.evaluate(() => ({
    selecteur: document.getElementById('choix-contrat').hidden &&
               document.getElementById('select-contrat').offsetParent === null,
    rappel: !/contrat/i.test(document.querySelector('.masthead').textContent),
    pont: typeof window.SUIVI_FWD_API.chargerContrat === 'function' && !window.SUIVI_FWD_API.sauverJalons
  }));
  verifier('avec un seul contrat, la page ne montre pas de sélecteur', contratAddon.selecteur);
  verifier('ni de rappel du contrat sous le titre', contratAddon.rappel);
  verifier('le pont vers le classeur expose chargerContrat, et plus sauverJalons', contratAddon.pont);
  // Hors du classeur, le pont ne peut pas répondre : il rappelle avec null, sans casser la page.
  verifier('hors classeur, chargerContrat rappelle null au lieu de planter',
    await p.evaluate(() => new Promise(resolve => {
      window.SUIVI_FWD_API.chargerContrat('autre', paquet => resolve(paquet === null));
    })));
  verifier('et la page reste entière',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length === 186));

  /* Cette feuille n'a pas de colonne de domaine : le périmètre n'a rien à
     proposer et reste caché, sans laisser un bouton derrière lui. */
  verifier('sans colonne de domaine, le paquet le dit', paquet.cleDomaine === null, String(paquet.cleDomaine));
  verifier('et la page ne montre pas de sélecteur de périmètre',
    await p.evaluate(() => document.getElementById('perimetre').hidden &&
      document.getElementById('perimetre').offsetParent === null &&
      document.querySelectorAll('#choix-perimetre button').length === 0));

  // Une cellule contenant une balise fermante ne doit pas couper la page en deux.
  verifier('une balise fermante dans une cellule ne casse pas la page',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length === 186 &&
      !!document.querySelector('svg.graphe') &&
      document.querySelectorAll('.critique-ligne').length > 0 &&
      [...document.querySelectorAll('#etats .etat-n')].reduce((t, e) => t + (+e.textContent.replace(/\s/g, '')), 0) === 186));
  verifier('et elle s\'affiche comme du texte dans le tableau',
    await p.evaluate(() => [...document.querySelectorAll('#corps-tableau td')]
      .some(td => td.textContent.includes('</script>'))));

  // Le chiffre affiché doit correspondre à ce que le serveur a compté.
  const attendu = { termine: 0, encours: 0, afaire: 0, vide: 0 };
  paquet.plans.forEach(pl => { attendu[contexte.classerFWD(pl.avancement)]++; });
  /* L'écran montre les valeurs de la colonne ; rangées par famille, elles
     retombent sur les comptes du serveur. */
  const parFamille = { termine: 0, encours: 0, afaire: 0, vide: 0 };
  vu.familles.forEach((f, i) => { parFamille[f] += vu.etats[i]; });
  verifier('l\'écran et le serveur comptent pareil : les valeurs affichées, rangées par famille, font les comptes du serveur',
    JSON.stringify(parFamille) === JSON.stringify(attendu),
    JSON.stringify([vu.libelles, vu.etats]) + ' vs ' + JSON.stringify(attendu));
  verifier('les pourcentages se regroupent — 100 %, entre 0 et 100 %, 0 % — et les mots restent chacun le leur',
    vu.libelles.indexOf('100 %') !== -1 && vu.libelles.indexOf('Entre 0 et 100 %') !== -1 &&
    vu.libelles.indexOf('Terminé') !== -1 && !vu.libelles.some(l => /^\d+\s?%$/.test(l) && l !== '100 %' && l !== '0 %'),
    JSON.stringify(vu.libelles));

  // Les interactions essentielles marchent-elles sur des données réelles ?
  await p.fill('#recherche', 'UD-24'); await p.waitForTimeout(400);
  verifier('la recherche fonctionne sur les données de la feuille',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) < 186);
  await p.fill('#recherche', ''); await p.waitForTimeout(400);
  await p.click('#etats .etat-btn[data-etat="vide"]'); await p.waitForTimeout(400);
  verifier('le filtre « non renseignés » ne garde que des cellules vides',
    await p.evaluate(() => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => /Avancement FWD/.test(t.textContent));
      return [...document.querySelectorAll('#corps-tableau tr')]
        .every(tr => /^(|—|non renseigné|-)$/i.test(tr.children[i].textContent.trim()));
    }));
  await p.click('#etats .etat-btn[data-etat="vide"]'); await p.waitForTimeout(300);
  await p.click('button[data-aide] >> nth=0').catch(() => {}); await p.waitForTimeout(400);
  verifier('le panneau d\'explication s\'ouvre sur des chiffres réels',
    await p.evaluate(() => {
      const el = document.getElementById('panneau-fin');
      return !!el && /Exemple/.test(el.textContent);
    }));
  await p.evaluate(() => { const b = document.getElementById('tout-effacer'); if (b) b.click(); });
  await p.waitForTimeout(400);
  await p.selectOption('#dim-critique', vu.dims[vu.dims.length - 1]); await p.waitForTimeout(500);
  verifier('changer de dimension recalcule le bloc sans rien perdre',
    await p.evaluate(() => [...document.querySelectorAll('.critique-total')]
      .reduce((s, t) => s + (+t.textContent), 0) === 186));

  // =================================================================
  section('La page sur les 138 colonnes réelles');
  construire({ gates: true, sortie: 'apercu-gates.html' });
  /* Contexte neuf : les deux aperçus sont servis depuis file://, donc ils
     partagent le même localStorage. Sans isolation, la page hériterait des
     colonnes et de la dimension choisies par les tests précédents. */
  const ctxGates = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pg = await ctxGates.newPage();
  pg.on('pageerror', e => erreursJS.push('gates : ' + e.message));
  pg.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push('gates : ' + m.text()); });
  await pg.goto('file://' + path.join(__dirname, '..', 'apercu-gates.html'));
  await pg.waitForTimeout(1800);

  const vg = await pg.evaluate(() => ({
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    visibles: document.querySelectorAll('tr.titres th').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    debord: document.documentElement.scrollWidth - window.innerWidth,
    dimActive: document.getElementById('dim-critique').value,
    titre: document.getElementById('titre-groupe').textContent,
    groupes: document.querySelectorAll('.critique-ligne').length,
    totaux: [...document.querySelectorAll('.critique-total')].reduce((s, t) => s + (+t.textContent), 0),
    colFWD: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()).indexOf('Avancement'),
    ordre: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim())
  }));
  verifier('les 186 plans sont là malgré les 138 colonnes', vg.lignes === 186, String(vg.lignes));
  verifier('les quatre états totalisent 186', vg.etats.reduce((a, b) => a + b, 0) === 186, JSON.stringify(vg.etats));
  /* La consigne est explicite : le tableau du bas EST l'extract. Toutes les
     colonnes, les mêmes intitulés, l'ordre de la feuille — c'est ce qui fait
     que tout le monde parle de la même chose. Une seule exception, décidée
     par l'utilisateur : la PREMIÈRE colonne, quand elle est sans intitulé
     (« Colonne 1 ») et vide de bout en bout — celle qu'Excel ajoute. Les
     autres colonnes sans intitulé restent, même vides. Le modèle serveur,
     lui, garde ses 138 : c'est la page qui trie. */
  verifier('le tableau s\'ouvre sur 137 colonnes : les 138 de la feuille, moins « Colonne 1 » vide',
    vg.visibles === 137, String(vg.visibles));
  verifier('« Colonne 1 » n\'est pas dans les en-têtes ; « Colonne 4 » et « Colonne 5 », sans intitulé elles aussi, y restent — c\'est la structure de GATES',
    vg.ordre.indexOf('Colonne 1') === -1 && vg.ordre.indexOf('Colonne 4') !== -1 && vg.ordre.indexOf('Colonne 5') !== -1,
    vg.ordre.slice(0, 5).join(' | '));
  verifier('la colonne « Avancement » est visible au départ', vg.colFWD !== -1, String(vg.colFWD));
  verifier('et dans l\'ordre exact de la feuille, sans autre exception',
    JSON.stringify(vg.ordre) === JSON.stringify(mGates.colonnes.filter(c => c.titre !== 'Colonne 1').map(c => c.titre)),
    vg.ordre.slice(0, 6).join(' | '));
  verifier('pas de débordement horizontal de la page', vg.debord <= 2, vg.debord + ' px');

  /* Données réelles, sur l'en-tête réel : l'interrupteur de l'avancement
     suivi est là, et le concept harnais se compte sur sa colonne du bloc
     HDK AA 011 — recomptée ici dans le modèle serveur, pas dans la page. */
  const mConceptTermine = mGates.plans.filter(x => gates.contexte.classerFWD(x[mGates.cleConcept]) === 'termine').length;
  const interrupteurReel = await pg.evaluate(() => !document.getElementById('choix-indicateur').hidden);
  await pg.click('#choix-indicateur button[data-indicateur="concept"]'); await pg.waitForTimeout(800);
  const vgConcept = await pg.evaluate(() => ({
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    termines: +document.querySelector('#phrase b').textContent.replace(/\s/g, ''),
    titre: document.getElementById('titre-groupe').textContent
  }));
  verifier('données réelles : l’interrupteur est là, et le concept harnais compte ses terminés sur sa colonne (' + mConceptTermine + ')',
    interrupteurReel && vgConcept.termines === mConceptTermine && vgConcept.etats.reduce((x, y) => x + y, 0) === 186 && /^Concept harnais par /.test(vgConcept.titre),
    JSON.stringify([interrupteurReel, vgConcept, mConceptTermine]));
  await pg.click('#choix-indicateur button[data-indicateur="def"]'); await pg.waitForTimeout(700);

  /* Le bloc figé couvre tout ce qui précède la référence, elle comprise — et
     se pose colonne après colonne, sinon la référence recouvrirait ce qui la
     précède. « Colonne 1 » retirée, la référence ouvre le tableau : le bloc
     se réduit à elle, sans que le mécanisme change. */
  const fige = await pg.evaluate(() => {
    const th = [...document.querySelectorAll('tr.titres th')];
    const n = th.findIndex(t => t.textContent.trim() === 'Référence UD');
    return {
      rang: n,
      figees: th.filter(t => t.classList.contains('col-fige')).map(t => t.textContent.trim()),
      gauches: th.filter(t => t.classList.contains('col-fige')).map(t => parseFloat(t.style.left)),
      fin: th[n] && th[n].classList.contains('fige-fin'),
      corpsFigees: [...document.querySelectorAll('#corps-tableau tr:first-child td')]
        .filter(td => td.classList.contains('col-fige')).length,
      groupesFiges: [...document.querySelectorAll('.groupes th.col-fige')]
        .map(t => ({ debut: +t.dataset.debut, span: t.colSpan, gauche: parseFloat(t.style.left) }))
    };
  });
  verifier('le bloc figé couvre tout ce qui précède la référence, elle comprise',
    fige.figees.length === fige.rang + 1 && fige.figees[fige.rang] === 'Référence UD',
    JSON.stringify(fige.figees));
  verifier('la référence ouvre le tableau : elle est seule figée',
    fige.rang === 0 && fige.figees.length === 1, JSON.stringify(fige.figees));
  verifier('chaque colonne figée se pose après la précédente, jamais dessus',
    fige.gauches[0] === 0 && fige.gauches.every((g, i) => i === 0 || g > fige.gauches[i - 1]),
    JSON.stringify(fige.gauches));
  verifier('la dernière colonne figée porte le trait de séparation', fige.fin === true);
  verifier('le corps fige exactement les mêmes colonnes que l\'en-tête',
    fige.corpsFigees === fige.figees.length,
    fige.corpsFigees + ' vs ' + fige.figees.length);
  verifier('la bande de groupes est coupée à la limite du bloc figé',
    fige.groupesFiges.length > 0 &&
    fige.groupesFiges[fige.groupesFiges.length - 1].debut +
      fige.groupesFiges[fige.groupesFiges.length - 1].span === fige.figees.length,
    JSON.stringify(fige.groupesFiges));

  /* Un en-tête figé qui passe SOUS les colonnes qui défilent est invisible :
     la position est bonne mais on lit le mauvais titre. */
  await pg.evaluate(() => { document.getElementById('defile').scrollLeft = 1200; });
  await pg.waitForTimeout(350);
  const apresScroll = await pg.evaluate(() => {
    const cadre = document.getElementById('defile').getBoundingClientRect();
    const th = document.querySelector('tr.titres th.col-fige');
    const dernier = [...document.querySelectorAll('tr.titres th.col-fige')].pop();
    const suivant = dernier.nextElementSibling;
    return {
      x: Math.round(th.getBoundingClientRect().left - cadre.left),
      zFige: +getComputedStyle(dernier).zIndex,
      zLibre: +getComputedStyle(suivant).zIndex || 0,
      titreVisible: document.elementFromPoint(
        cadre.left + 10, dernier.getBoundingClientRect().top + 8)
    };
  });
  verifier('l\'en-tête figé reste collé à gauche après défilement',
    Math.abs(apresScroll.x) <= 2, apresScroll.x + ' px');
  verifier('et il passe au-dessus des colonnes qui défilent',
    apresScroll.zFige > apresScroll.zLibre,
    apresScroll.zFige + ' vs ' + apresScroll.zLibre);
  await pg.evaluate(() => { document.getElementById('defile').scrollLeft = 0; });
  await pg.waitForTimeout(250);

  verifier('l\'ATA est ouvert par défaut', vg.dimActive === 'ata' && /par ATA/.test(vg.titre), vg.titre);
  verifier('tous les ATA sont comptés', vg.totaux === 186 && vg.groupes >= 5,
    vg.groupes + ' groupes, ' + vg.totaux + ' plans');

  /* Plus de « Choisir » : rien ne permet de composer son tableau colonne par
     colonne. Deux vues, et « Toutes les colonnes » rend les 137. */
  verifier('ni bouton « Choisir », ni panneau de colonnes',
    await pg.evaluate(() => !document.getElementById('bascule-colonnes') && !document.getElementById('panneau-colonnes') &&
      !document.getElementById('tout-colonnes') && document.querySelectorAll('.outils input[type="checkbox"]').length === 0));
  await pg.click('#vue-tableau button[data-vue="essentielle"]'); await pg.waitForTimeout(400);
  await pg.click('#vue-tableau button[data-vue="toutes"]'); await pg.waitForTimeout(600);
  verifier('« Toutes les colonnes » ramène les 137 colonnes',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === 137,
    String(await pg.evaluate(() => document.querySelectorAll('tr.titres th').length)));
  verifier('et la page tient toujours', await pg.evaluate(() =>
    document.documentElement.scrollWidth - window.innerWidth <= 2 &&
    document.querySelectorAll('#corps-tableau tr').length === 186));

  // =================================================================
  /* Les jalons du programme sur la vraie structure — colonne « Domaine » à
     BASE/OPTION et PERSO. Sous PERSO, les deux jalons Base passent en retrait
     et l'échéance affichée (data-jalon, en-tête de l'effort demandé) est
     celle que la page calcule ; sous BASE/OPTION, l'inverse. Le solde FWD,
     sans périmètre, reste l'échéance tant qu'il est à venir. */
  const lireJalons = () => pg.evaluate(() => ({
    retrait: [...document.querySelectorAll('.jalon.hors-perimetre .jalon-texte')].map(t => t.textContent).sort(),
    dessines: document.querySelectorAll('svg.graphe .jalon').length,
    zone: document.getElementById('zone-critique').getAttribute('data-jalon'),
    prochain: window.__prochainJalon() && window.__prochainJalon().texte,
    entete: (document.querySelector('.critique-tete button[data-trig="tension"]') || {}).title || ''
  }));
  await pg.click('.segmente button[data-span="0"]'); await pg.waitForTimeout(400);
  const jTout = await lireJalons();
  verifier('sur « Tout », les cinq jalons de la configuration sont dessinés, aucun en retrait, et l\'en-tête de l\'effort demandé nomme l\'échéance',
    jTout.dessines === 5 && jTout.retrait.length === 0 && !!jTout.prochain && jTout.zone === jTout.prochain &&
    jTout.entete.indexOf('«\u00a0' + jTout.prochain + '\u00a0»') !== -1, JSON.stringify(jTout));
  await pg.click('#choix-perimetre button[data-perimetre="PERSO"]'); await pg.waitForTimeout(700);
  const jPerso = await lireJalons();
  verifier('sous PERSO, les deux jalons Base sont en retrait, et l\'échéance affichée est celle que la page calcule',
    jPerso.retrait.join('|') === 'Diffusion PH Base|Diffusion TO Base' && !!jPerso.prochain && jPerso.zone === jPerso.prochain &&
    !/Base$/.test(jPerso.prochain) && jPerso.entete.indexOf('«\u00a0' + jPerso.prochain + '\u00a0»') !== -1, JSON.stringify(jPerso));
  await pg.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await pg.waitForTimeout(700);
  const jBase = await lireJalons();
  verifier('sous BASE/OPTION, les deux jalons Perso sont en retrait',
    jBase.retrait.join('|') === 'Diffusion PH Perso|Diffusion TO Perso' && !!jBase.prochain && jBase.zone === jBase.prochain &&
    !/Perso$/.test(jBase.prochain), JSON.stringify(jBase));
  await pg.click('#choix-perimetre button[data-perimetre=""]'); await pg.waitForTimeout(500);

  section('Journal des changements');
  const ouvertesDEmblee = await pg.evaluate(() => [...document.querySelectorAll('.journal-plier')].map(e => e.getAttribute('aria-expanded')));
  // On déplie la plus récente pour lire ses lignes.
  await pg.click('.journal-plier >> nth=0'); await pg.waitForTimeout(300);
  const jrn = await pg.evaluate(() => ({
    semaines: [...document.querySelectorAll('.journal-tete .sem')].map(e => e.textContent.trim()),
    resumes: [...document.querySelectorAll('.journal-tete .resume')].map(e => e.textContent.trim()),
    ouvertes: [...document.querySelectorAll('.journal-plier')].map(e => e.getAttribute('aria-expanded')),
    lignes: document.querySelectorAll('.journal-ligne').length,
    premiere: (document.querySelector('.journal-ligne') || {}).textContent
  }));
  verifier('une entrée par semaine où quelque chose a bougé',
    jrn.semaines.length >= 2, String(jrn.semaines.length));
  verifier('la semaine la plus récente est en tête',
    jrn.semaines[0] > jrn.semaines[jrn.semaines.length - 1], JSON.stringify(jrn.semaines));
  verifier('toutes les semaines sont repliées d\'emblée',
    ouvertesDEmblee.length >= 2 && ouvertesDEmblee.every(v => v === 'false'), JSON.stringify(ouvertesDEmblee));
  verifier('un clic déplie la plus récente, et elle seule',
    jrn.ouvertes[0] === 'true' && jrn.ouvertes.slice(1).every(v => v === 'false'),
    JSON.stringify(jrn.ouvertes));
  verifier('le résumé est écrit en français correct',
    jrn.resumes.every(r => !/en en cour|passés en terminé/.test(r)) &&
    jrn.resumes.some(r => /passés? à « [^»]+ »/.test(r)),
    JSON.stringify(jrn.resumes[0]));
  verifier('chaque ligne nomme le plan et son passage',
    /UD-/.test(jrn.premiere || ''), jrn.premiere);
  verifier('les états sont au singulier dans une flèche',
    !/Terminés\s*$/.test(jrn.premiere || '') , jrn.premiere);
  /* Les références de cette feuille (UD-24-1037) ne sont pas au format UD :
     elles n'ont pas de racine, donc jamais d'appariement — un plan apparu est
     un nouveau, point. Un appariement de travers ferait un faux changement
     d'indice entre deux plans qui n'ont rien à voir. */
  const appariement = await pg.evaluate(() => {
    const J = window.__journal();
    const types = { indice: 0, nouveau: 0, disparu: 0, change: 0 };
    J.forEach(s => s.evenements.forEach(e => { types[e.type]++; }));
    return {
      types,
      puce: !!document.querySelector('.puce-delta[data-delta="indice"]'),
      compte: !!document.querySelector('.compte-passage[data-passage="indice"]'),
      racines: window.__analyserUD('UD-24-1037')
    };
  });
  verifier('des références hors format ne sont jamais appariées : aucun changement d’indice',
    appariement.types.indice === 0 && !appariement.puce && !appariement.compte, JSON.stringify(appariement.types));
  verifier('les deux plans apparus dans l’historique restent des nouveaux',
    appariement.types.nouveau === 2 && appariement.types.disparu === 0 && appariement.types.change > 0,
    JSON.stringify(appariement.types));
  verifier('et la page lit bien ces références comme hors format',
    appariement.racines.valide === false && appariement.racines.racine === 'UD-24-1037');

  // Replier / déplier
  await pg.click('.journal-plier >> nth=0'); await pg.waitForTimeout(350);
  verifier('replier une semaine cache sa liste',
    await pg.evaluate(() => document.querySelectorAll('.journal-liste').length === 0));
  await pg.click('.journal-plier >> nth=1'); await pg.waitForTimeout(350);
  verifier('déplier une autre semaine montre la sienne',
    await pg.evaluate(() => document.querySelectorAll('.journal-liste').length === 1));

  // Filtrer par type de passage
  /* Les boutons du journal sont les valeurs d'arrivée de la colonne : on
     prend le premier de la famille « fini », quel que soit son nom. */
  const boutonFini = await pg.evaluate(() => {
    const b = document.querySelector('#filtre-journal button[data-famille="termine"]');
    return b ? { cle: b.dataset.journal, mot: b.textContent.trim() } : null;
  });
  await pg.click('#filtre-journal button[data-famille="termine"]'); await pg.waitForTimeout(400);
  verifier('le filtre d’une valeur finie (« ' + (boutonFini && boutonFini.mot) + ' ») ne laisse que des passages vers elle',
    !!boutonFini && await pg.evaluate(m => [...document.querySelectorAll('.journal-ligne .vers')]
      .every(v => v.querySelector('.etiq-etat.apres').textContent.trim() === m), boutonFini.mot));
  verifier('et les résumés ne parlent plus que d’elle',
    !!boutonFini && await pg.evaluate(k => [...document.querySelectorAll('.journal-tete .resume .compte-passage')]
      .every(b => b.dataset.passage === k) &&
      [...document.querySelectorAll('.journal-tete .resume')].every(r => !/effacé/.test(r.textContent)), boutonFini.cle));
  await pg.click('#filtre-journal button[data-journal=""]'); await pg.waitForTimeout(400);

  // Cliquer un plan filtre le tableau sur lui
  await pg.click('.journal-plier >> nth=0'); await pg.waitForTimeout(300);
  const refCliquee = await pg.evaluate(() => document.querySelector('.journal-ligne').dataset.ref);
  await pg.click('.journal-ligne >> nth=0'); await pg.waitForTimeout(600);
  verifier('cliquer un plan du journal réduit le tableau à ce plan',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 1,
    String(await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length)));
  /* On cherche la référence par son en-tête plutôt que de supposer sa
     position : le tableau suit l'ordre de la feuille, pas l'inverse. */
  verifier('et c\'est bien le bon plan',
    await pg.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')]
        .findIndex(t => t.textContent.trim() === 'Référence UD');
      const tr = document.querySelector('#corps-tableau tr');
      return i !== -1 && tr.children[i].textContent.trim() === r;
    }, refCliquee));
  await pg.click('.journal-ligne >> nth=0'); await pg.waitForTimeout(600);
  verifier('re-cliquer rend les 186 plans',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 186);

  // =================================================================
  /* Deux vues, et rien entre les deux : l'extract complet dans l'ordre de la
     feuille, ou la poignee de colonnes qu'on regarde vraiment. */
  section('Les deux vues du tableau');
  const vueDepart = await pg.evaluate(() => ({
    presse: [...document.querySelectorAll('#vue-tableau button')]
      .map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')),
    n: document.querySelectorAll('tr.titres th').length
  }));
  verifier('la vue « toutes les colonnes » est celle de depart',
    vueDepart.presse.join(' ') === 'toutes:true essentielle:false' && vueDepart.n === 137,
    JSON.stringify(vueDepart));

  await pg.click('#vue-tableau button[data-vue="essentielle"]'); await pg.waitForTimeout(600);
  const ess = await pg.evaluate(() => ({
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    presse: [...document.querySelectorAll('#vue-tableau button')]
      .map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    figees: document.querySelectorAll('tr.titres th.col-fige').length
  }));
  verifier('la vue essentielle est exactement celle demandee',
    JSON.stringify(ess.titres) === JSON.stringify(['Référence UD', 'Nom Installation', 'ECP',
      'ATA', 'Séquence', 'Validation Définition Electrique', 'Date création',
      'Avancement Définition Electrique', 'Avancement Concept Harnais']),
    JSON.stringify(ess.titres));
  verifier('ni Statut iBG ni les blocs repetes n\'y entrent',
    ess.titres.indexOf('Statut iBG') === -1 && ess.titres.indexOf('Validité') === -1);
  verifier('aucun plan n\'est perdu au passage', ess.lignes === 186, String(ess.lignes));
  verifier('la reference ouvre la vue essentielle et reste seule figee',
    ess.titres[0] === 'Référence UD' && ess.figees === 1, String(ess.figees));
  verifier('l\'interrupteur dit laquelle des deux est active',
    ess.presse.join(' ') === 'toutes:false essentielle:true', JSON.stringify(ess.presse));

  await pg.click('#vue-tableau button[data-vue="toutes"]'); await pg.waitForTimeout(600);
  const retour = await pg.evaluate(() => ({
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    figees: document.querySelectorAll('tr.titres th.col-fige').length
  }));
  verifier('revenir rend l\'extract entier dans l\'ordre de la feuille',
    JSON.stringify(retour.titres) === JSON.stringify(vg.ordre), String(retour.titres.length));
  verifier('et le bloc fige reste la reference seule', retour.figees === 1, String(retour.figees));

  // Un aller-retour repete ne doit rien laisser derriere lui.
  for (let i = 0; i < 4; i++) {
    await pg.click('#vue-tableau button[data-vue="essentielle"]'); await pg.waitForTimeout(140);
    await pg.click('#vue-tableau button[data-vue="toutes"]'); await pg.waitForTimeout(140);
  }
  await pg.waitForTimeout(500);
  verifier('quatre allers-retours rapides ne derangent rien',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === 137 &&
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 186);
  // Re-cliquer la vue deja active ne doit pas la casser non plus.
  await pg.click('#vue-tableau button[data-vue="toutes"]'); await pg.waitForTimeout(400);
  verifier('re-cliquer la vue active la laisse en place',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === 137);

  // =================================================================
  section('Bandeau des filtres actifs');
  await pg.evaluate(() => { const b = document.getElementById('tout-effacer'); if (b) b.click(); });
  await pg.waitForTimeout(400);
  verifier('aucun bandeau tant que rien n\'est filtré',
    await pg.evaluate(() => document.getElementById('filtres-actifs').hidden));

  /* Les boutons d'état sont les valeurs trouvées dans la colonne suivie :
     on prend la première qui n'est pas « non renseigné ». */
  const etatPose = await pg.evaluate(() => {
    const b = document.querySelector('#etats .etat-btn:not([data-famille="vide"])');
    return b ? { cle: b.dataset.etat } : null;
  });
  verifier('la colonne suivie propose au moins une valeur renseignée', !!etatPose);
  await pg.click('#etats .etat-btn[data-etat="' + etatPose.cle + '"]'); await pg.waitForTimeout(350);
  const libelleEtat = await pg.evaluate(k => window.__valeurs().filter(v => v.cle === k).map(v => v.libelle)[0], etatPose.cle);
  /* Le domaine se choisit par le périmètre du haut ; le filtre de colonne
     reste une porte d'entrée, et son jeton nomme la colonne. */
  await pg.fill('input[data-filtre="domaine"]', 'PERSO'); await pg.waitForTimeout(400);
  await pg.fill('#recherche', 'UD-24'); await pg.waitForTimeout(400);
  const jetons = await pg.evaluate(() => [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()));
  verifier('chaque filtre posé devient un jeton nommé', jetons.length === 3, JSON.stringify(jetons));
  verifier('le jeton dit quelle colonne et quelle valeur',
    jetons.some(t => t.indexOf('État : ' + libelleEtat) !== -1) && jetons.some(t => /Domaine : PERSO/.test(t)) &&
    jetons.some(t => /Recherche : UD-24/.test(t)), JSON.stringify(jetons));
  verifier('le bandeau reste visible en haut de page',
    await pg.evaluate(() => getComputedStyle(document.getElementById('filtres-actifs')).position === 'sticky'));

  const avantCroix = await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  await pg.click('.jeton .x >> nth=0'); await pg.waitForTimeout(450);
  verifier('la croix d\'un jeton ne retire que ce filtre',
    await pg.evaluate(() => document.querySelectorAll('.jeton').length) === 2 &&
    (await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length)) >= avantCroix);
  await pg.click('#tout-effacer'); await pg.waitForTimeout(450);
  verifier('« Tout effacer » rend les 186 plans et cache le bandeau',
    await pg.evaluate(() => document.getElementById('filtres-actifs').hidden &&
      document.querySelectorAll('#corps-tableau tr').length === 186 &&
      document.getElementById('recherche').value === ''));

  // Un filtre venu d'un groupe doit aussi apparaître, avec son libellé lisible.
  await pg.click('.critique-ligne >> nth=0'); await pg.waitForTimeout(500);
  verifier('choisir un groupe pose un jeton nommé',
    await pg.evaluate(() => {
      const j = [...document.querySelectorAll('.jeton')].map(x => x.textContent);
      return j.length === 1 && /ATA/.test(j[0]);
    }));
  await pg.click('#tout-effacer'); await pg.waitForTimeout(450);

  // =================================================================
  /* La feuille GATES a une colonne « Domaine » : le périmètre est proposé à
     droite de la phrase d'avancement, au-dessus de la barre — hors de la zone
     du titre —, une puce par valeur avec son compte, et il restreint toute la
     page.
     Code.gs n'y est pour rien : la page dérive tout du paquet et des cartes. */
  section('Périmètre par domaine');
  const perim = await pg.evaluate(() => ({
    visible: !document.getElementById('perimetre').hidden &&
             document.getElementById('choix-perimetre').offsetParent !== null,
    haut: document.getElementById('perimetre').getBoundingClientRect().top >=
          document.querySelector('.masthead').getBoundingClientRect().bottom &&
          document.getElementById('perimetre').getBoundingClientRect().bottom <=
          document.getElementById('barre').getBoundingClientRect().top + 1 &&
          !document.querySelector('header.masthead #perimetre') &&
          document.getElementById('perimetre').getBoundingClientRect().left >
          document.getElementById('phrase').getBoundingClientRect().right,
    boutons: [...document.querySelectorAll('#choix-perimetre button')].map(b => ({
      val: b.dataset.perimetre, n: +b.querySelector('.n').textContent.replace(/\s/g, ''),
      presse: b.getAttribute('aria-pressed')
    })),
    serieTout: window.__serieAffichee().pts
  }));
  const attenduDom = { 'BASE/OPTION': 0, 'PERSO': 0 };
  mGates.plans.forEach(pl => { attenduDom[pl[mGates.cleDomaine]]++; });
  verifier('le sélecteur est proposé hors du titre, à droite de la phrase d\'avancement, avec une puce par domaine de la feuille',
    perim.visible && perim.haut && perim.boutons.map(b => b.val).join(',') === ',BASE/OPTION,PERSO',
    JSON.stringify(perim.boutons));
  verifier('les comptes sont ceux de la feuille, et il démarre sur Tout',
    perim.boutons[0].n === 186 && perim.boutons[1].n === attenduDom['BASE/OPTION'] &&
    perim.boutons[2].n === attenduDom.PERSO && perim.boutons[0].presse === 'true',
    JSON.stringify(perim.boutons) + ' vs ' + JSON.stringify(attenduDom));

  await pg.click('#choix-perimetre button[data-perimetre="PERSO"]'); await pg.waitForTimeout(700);
  const persoG = await pg.evaluate(() => {
    const iDom = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'domaine');
    const serie = window.__serieAffichee();
    return {
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      domaines: [...new Set([...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[iDom].textContent.trim()))],
      etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
      totalGroupes: [...document.querySelectorAll('.critique-total')].reduce((s, t) => s + (+t.textContent), 0),
      serie: serie.pts,
      note: document.getElementById('note-graphe').textContent,
      jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
      journal: window.__journalAffiche().reduce((l, s) => l.concat(s.evenements), []).map(e => window.__domaineDe(e.ref)),
      phrase: document.getElementById('phrase').textContent
    };
  });
  verifier('choisir PERSO restreint le tableau, la barre et le bloc par groupe aux plans PERSO',
    persoG.lignes === attenduDom.PERSO && persoG.domaines.join() === 'PERSO' &&
    persoG.etats.reduce((a, b) => a + b, 0) === attenduDom.PERSO && persoG.totalGroupes === attenduDom.PERSO,
    JSON.stringify([persoG.lignes, persoG.domaines, persoG.etats, persoG.totalGroupes]));
  verifier('la phrase nomme le périmètre', /dans le périmètre PERSO/.test(persoG.phrase), persoG.phrase);
  const dernierG = persoG.serie[persoG.serie.length - 1];
  verifier('la courbe est dérivée des cartes archivées : autant de relevés, dernier point = terminés PERSO',
    persoG.serie.length === perim.serieTout.length && persoG.serie.length >= 2 &&
    dernierG.total === attenduDom.PERSO && dernierG.termine === persoG.etats[0],
    JSON.stringify(dernierG) + ' / ' + persoG.serie.length);
  verifier('chaque point du périmètre est en deçà du point global',
    persoG.serie.every((pt, k) => pt.total < perim.serieTout[k].total && pt.termine <= perim.serieTout[k].termine));
  verifier('la note du graphique nomme le périmètre', /Historique du périmètre PERSO/.test(persoG.note), persoG.note);
  verifier('le journal ne parle que de plans PERSO',
    persoG.journal.length > 0 && persoG.journal.every(d => d === 'PERSO'), JSON.stringify([...new Set(persoG.journal)]));
  verifier('le bandeau nomme le périmètre', persoG.jetons.length === 1 && /^Périmètre : PERSO$/.test(persoG.jetons[0]),
    JSON.stringify(persoG.jetons));
  await pg.click('#tout-effacer'); await pg.waitForTimeout(600);
  verifier('« Tout effacer » rend les 186 plans et la puce Tout',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length === 186 &&
      document.querySelector('#choix-perimetre button[data-perimetre=""]').getAttribute('aria-pressed') === 'true' &&
      document.getElementById('filtres-actifs').hidden));

  // =================================================================
  section('Liste des UD sous un groupe');
  const grosGroupe = await pg.evaluate(() => {
    const l = [...document.querySelectorAll('.critique-ligne')];
    l.sort((a, b) => +b.querySelector('.critique-total').textContent - +a.querySelector('.critique-total').textContent);
    return l[0].dataset.groupe;
  });
  await pg.click(`.critique-ligne[data-groupe="${grosGroupe}"]`); await pg.waitForTimeout(600);
  const ud = await pg.evaluate(() => ({
    jetons: [...document.querySelectorAll('.jeton-ud[data-ud]')].map(b => b.textContent.trim()),
    total: +document.querySelector('.critique-ligne[aria-pressed="true"] .critique-total').textContent,
    entete: (document.querySelector('.groupe-refs .entete') || {}).textContent || '',
    sousTitres: [...document.querySelectorAll('.groupe-refs .sous-titre')].map(t => t.textContent.replace(/\s+/g, ' ').trim()),
    autres: /autres/.test((document.querySelector('.groupe-refs') || {}).textContent || ''),
    etats: [...document.querySelectorAll('.jeton-ud[data-ud] .pastille')].map(e => e.className),
    tableau: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('choisir un groupe déplie ses références', ud.jetons.length > 0, String(ud.jetons.length));
  verifier('toutes, sans « et N autres », en deux paquets titrés',
    ud.jetons.length === ud.total && !ud.autres && ud.sousTitres.length === 2 &&
    /^Pas encore terminés\s*\(\d+\)$/.test(ud.sousTitres[0]) && /^Terminés\s*\(\d+\)$/.test(ud.sousTitres[1]),
    ud.jetons.length + ' / ' + ud.total + ' ' + JSON.stringify(ud.sousTitres));
  verifier('toutes sont des références de plan', ud.jetons.every(t => /^UD-/.test(t)), JSON.stringify(ud.jetons.slice(0, 3)));
  verifier('l\'en-tête dit combien et combien restent',
    /\d+ plans?/.test(ud.entete) && /(pas encore terminés?|tout est soldé)/.test(ud.entete), ud.entete.trim());
  verifier('le tableau du bas montre exactement le même groupe',
    ud.tableau === Math.min(ud.jetons.length, ud.tableau) && ud.tableau > 0);
  verifier('les non terminés sont en tête de liste',
    await pg.evaluate(() => {
      const ordre = ['afaire', 'vide', 'encours', 'termine'];
      const rang = [...document.querySelectorAll('.jeton-ud[data-ud]')].map(b => {
        const t = b.getAttribute('title') || '';
        if (/À faire/.test(t)) return 0;
        if (/Non renseigné/.test(t)) return 1;
        if (/En cours/.test(t)) return 2;
        return 3;
      });
      return rang.every((v, i) => i === 0 || rang[i - 1] <= v);
    }));
  const refUD = await pg.evaluate(() => document.querySelector('.jeton-ud[data-ud]').dataset.ud);
  await pg.click('.jeton-ud[data-ud] >> nth=0'); await pg.waitForTimeout(700);
  verifier('cliquer une référence réduit le tableau à ce plan',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 1);
  verifier('et c\'est la bonne',
    await pg.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')]
        .findIndex(t => t.dataset.cle === 'reference');
      return i !== -1 && document.querySelector('#corps-tableau tr').children[i].textContent.trim() === r;
    }, refUD));
  await pg.click('#tout-effacer'); await pg.waitForTimeout(450);

  // =================================================================
  section('Repères du bloc par groupe');
  /* Deux colonnes calculées, chacune avec son « ? » : la fin estimée, et la
     dernière, qui est « effort demandé » quand un jalon de la configuration
     est à venir (c'est le cas : CONFIG.JALONS en fournit), « rythme actuel »
     sinon. */
  const reperes = await pg.evaluate(() => ({
    aides: document.querySelectorAll('button[data-aide]').length,
    avecJalon: !document.getElementById('zone-critique').classList.contains('sans-jalon'),
    derniere: [...document.querySelectorAll('.critique-tete button[data-trig]')].slice(-1)[0].textContent.trim()
  }));
  verifier('chaque colonne calculée porte son « ? »', reperes.aides === 2, reperes.aides + ' « ? »');
  verifier('avec un jalon de configuration à venir, la dernière colonne est l\'effort demandé',
    reperes.avecJalon && /effort demandé/.test(reperes.derniere), JSON.stringify(reperes));
  await pg.selectOption('#dim-critique', 'ata'); await pg.waitForTimeout(500);
  const noteA = await pg.textContent('#indice-dim');
  await pg.selectOption('#dim-critique', '_mois'); await pg.waitForTimeout(500);
  const noteM = await pg.textContent('#indice-dim');
  verifier('une dimension ordinaire n\'a pas besoin de note', noteA.trim() === '', noteA);
  verifier('le mois de création, lui, est expliqué',
    /mois/.test(noteM) && /vague|temps/i.test(noteM), noteM);
  const bcp = await pg.evaluate(() => {
    const z = document.getElementById('zone-critique');
    return {
      lignes: document.querySelectorAll('.critique-ligne').length,
      hauteur: Math.round(z.getBoundingClientRect().height),
      defile: z.scrollHeight > z.clientHeight + 4
    };
  });
  verifier('toutes les lignes sont présentes, même nombreuses', bcp.lignes > 15, String(bcp.lignes));
  verifier('le bloc garde une hauteur raisonnable', bcp.hauteur <= 520, bcp.hauteur + ' px');
  verifier('et on y descend au lieu d\'allonger la page', bcp.defile);
  await pg.selectOption('#dim-critique', 'ata'); await pg.waitForTimeout(500);

  // =================================================================
  section('Bulle du graphique');
  const bulle = await pg.evaluate(() => {
    const zones = [...document.querySelectorAll('.zone-clic')];
    return zones.length;
  });
  verifier('le graphique a des semaines survolables', bulle > 0, String(bulle));
  // Le graphique doit être à l'écran : la souris travaille en coordonnées de fenêtre.
  await pg.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' }));
  await pg.waitForTimeout(350);
  let texteBulle = '';
  const zonesG = await pg.$$('.zone-clic');
  for (const z of zonesG) {
    const bb = await z.boundingBox();
    if (!bb || bb.y < 0 || bb.y > 900) continue;
    await pg.mouse.move(bb.x + bb.width / 2, bb.y + bb.height * 0.6);
    await pg.waitForTimeout(120);
    const t = await pg.evaluate(() => document.getElementById('bulle').textContent);
    if (/passés? en terminé/.test(t)) { texteBulle = t; break; }
  }
  verifier('survoler une semaine annonce les passages en terminé',
    /passés? en terminé/.test(texteBulle), texteBulle.slice(0, 90));
  /* La bulle résume : « terminés N / total », l'écart, puis les comptes de la
     semaine. Les références, elles, sont dans le journal, dessous. */
  verifier('en comptes, sans lister les références ni « et N autres »',
    !/UD-/.test(texteBulle) && !/autres/.test(texteBulle) &&
    /terminés\s*\d+\s*\/\s*\d+/.test(texteBulle), texteBulle.slice(0, 120));

  // =================================================================
  section('La seconde base, de l\'onglet à l\'écran');
  /* La page rendue sur le classeur qui porte « Base2 » : la section apparaît,
     nommée d'après l'onglet, et ses comptes sont ceux qu'on peut recalculer
     à la main depuis les trois lignes appariées. Sur la page ordinaire, sans
     seconde base, la section n'existe pas. */
  verifier('sans seconde base, la page n\'a pas de section de rapprochement',
    await p.evaluate(() => document.getElementById('rapprochement').hidden &&
      document.getElementById('rapprochement').offsetParent === null));
  const ctxRapp = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pr = await ctxRapp.newPage();
  pr.on('pageerror', e => erreursJS.push('rapprochement : ' + e.message));
  pr.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push('rapprochement : ' + m.text()); });
  await pr.goto('file://' + path.join(__dirname, '..', 'apercu-rapprochement.html'));
  await pr.waitForTimeout(1600);
  /* Base2 connaît les trois premiers plans (sous leur référence exacte) et
     une référence inédite. Le verdict de chacun se recalcule à la main : un
     plan connu de Base2 est d'accord s'il est terminé ici, « pas terminé ici »
     sinon ; un plan inconnu de Base2 lui manque s'il est terminé ici, attend
     sinon. */
  const classe = avecBase2.contexte.classerFWD;
  const plans30 = avecBase2.paquet.plans;
  const fini = p => classe(p.avancement) === 'termine';
  const attB2 = { accord: plans30.slice(0, 3).filter(fini).length, avance: plans30.slice(0, 3).filter(p => !fini(p)).length,
    manque: plans30.slice(3).filter(fini).length, attente: plans30.slice(3).filter(p => !fini(p)).length };
  const ecran = await pr.evaluate(() => ({
    visible: !document.getElementById('rapprochement').hidden,
    titre: document.getElementById('titre-rapprochement').textContent,
    phrase: !!document.getElementById('phrase-rapprochement'),
    puces: [...document.querySelectorAll('#verdicts-rapprochement button[data-rapp]')].map(b => b.dataset.rapp + '=' + b.querySelector('.verdict-n').textContent),
    figure: (() => { const svg = document.querySelector('#venn-rapprochement svg'); return svg && {
      cercles: svg.querySelectorAll('circle.cercle-ici, circle.cercle-la').length,
      bases: [...svg.querySelectorAll('.base-nom')].map(t => t.textContent).join(),
      commun: +svg.querySelector('.commun-n').textContent,
      parts: [...svg.querySelectorAll('.donut-seg')].map(x => x.getAttribute('data-cle') + '=' + x.getAttribute('data-n')).join(),
      cotes: [...svg.querySelectorAll('.cote')].map(g => g.getAttribute('data-cle') + '=' + (g.querySelector('.grand') || g.querySelector('.moyen')).textContent).join() }; })(),
    sousLeTableau: document.getElementById('rapprochement').getBoundingClientRect().top >= document.getElementById('cadre-tableau').getBoundingClientRect().bottom,
    sous: !!document.getElementById('sous-rapprochement'),
    plans: document.querySelectorAll('#corps-tableau tr').length,
    seconde: !document.getElementById('choix-base').hidden,
    titreSeconde: document.getElementById('bouton-base-la').textContent,
    entetesSeconde: [...document.querySelectorAll('#tete-seconde th')].map(t => t.textContent.trim()).join('|'),
    lignesSeconde: document.querySelectorAll('#corps-seconde tr[data-i]').length,
    vueSeconde: document.getElementById('vue-seconde').hidden
  }));
  verifier('la section est là, sous son titre', ecran.visible && ecran.titre === 'Comparaison des bases de données', ecran.titre);
  verifier('la tête de la section ne porte que le titre : ni phrase ni sous-phrase', !ecran.phrase && !ecran.sous);
  verifier('les verdicts recalculés à la main : d\'accord, aucun autre indice, pas terminés ici, terminés absents, en attente, 1 seulement là',
    ecran.puces.join(' ') === 'accord=' + attB2.accord + ' emission=0 avance=' + attB2.avance + ' manque=' + attB2.manque + ' attente=' + attB2.attente + ' seul=1',
    ecran.puces.join(' ') + ' attB2 ' + JSON.stringify(attB2));
  verifier('la figure : deux cercles GATES et Base2, 3 plans en commun dans l\'anneau, les côtés aux mêmes comptes, sous le tableau des plans',
    ecran.figure && ecran.figure.cercles === 2 && ecran.figure.bases === 'GATES,Base2' && ecran.figure.commun === 3 &&
    ecran.figure.cotes === 'manque=' + attB2.manque + ',attente=' + attB2.attente + ',seul=1' && ecran.sousLeTableau, JSON.stringify([ecran.figure, ecran.sousLeTableau]));
  verifier('l\'interrupteur GATES | Base2 est là, nommé d\'après l\'onglet, le tableau de là a ses quatre colonnes et ses quatre lignes, sans vue essentielle',
    ecran.seconde && ecran.titreSeconde === 'Base2' && ecran.entetesSeconde === 'REF_UD|ATA_CODE|STATUT_FWD|Colonne en trop' &&
    ecran.lignesSeconde === 4 && ecran.vueSeconde, JSON.stringify([ecran.titreSeconde, ecran.entetesSeconde, ecran.lignesSeconde]));
  const lotB2 = attB2.manque ? 'manque' : 'attente', nLotB2 = attB2[lotB2];
  await pr.click('#verdicts-rapprochement button[data-rapp="' + lotB2 + '"]'); await pr.waitForTimeout(500);
  verifier('cliquer un verdict d\'ici filtre le tableau sur ses ' + nLotB2 + ' plans',
    await pr.evaluate(n => document.querySelectorAll('#corps-tableau tr').length === n &&
      [...document.querySelectorAll('.jeton')].some(j => /Comparaison : /.test(j.textContent)), nLotB2));
  await pr.click('#verdicts-rapprochement button[data-rapp="seul"]'); await pr.waitForTimeout(400);
  verifier('« seulement dans Base2 » passe sur Base2, réduit son tableau à UD-99-9999, et celui de GATES dit où la voir',
    await pr.evaluate(() => {
      const l = document.querySelectorAll('#corps-seconde tr[data-i]');
      return l.length === 1 && l[0].querySelector('.verdict .ref').textContent === 'UD-99-9999' &&
        !document.getElementById('cadre-seconde').hidden &&
        /Ces 1 ligne n’a pas de plan dans GATES\. Les voir dans Base2/.test((document.querySelector('#corps-tableau .vide-message') || {}).textContent.replace(/\s+/g, ' ')) &&
        [...document.querySelectorAll('.jeton')].some(j => /Comparaison : ligne de Base2 sans plan dans GATES/.test(j.textContent));
    }));
  /* Plan par plan, sur une référence à une seule colonne : les groupes
     suivent les verdicts (les lots à zéro n'apparaissent pas), et la ligne
     seulement là s'ouvre dans le tableau de Base2, cherchée sur REF_UD. */
  const listeB2 = await pr.evaluate(() => ({
    groupes: [...document.querySelectorAll('#liste-rapprochement .rapp-groupe')].map(g => g.dataset.cle + '=' + g.querySelector('.rapp-groupe-tete b').textContent.replace(/\s/g, '')),
    seul: [...document.querySelectorAll('#liste-rapprochement .rapp-groupe[data-cle="seul"] .rapp-puce')].map(b => ({
      ref: b.querySelector('.rapp-puce-ref').textContent, la: b.dataset.ligneLa, gates: b.dataset.etat || '', bulle: b.title
    }))
  }));
  const attendusB2 = ['manque', 'avance', 'emission', 'seul', 'attente', 'accord']
    .map(c => [c, c === 'seul' ? 1 : (attB2[c] || 0)]).filter(x => x[1] > 0).map(x => x[0] + '=' + x[1]);
  verifier('plan par plan sur Base2 : les groupes non vides des verdicts, dans l\'ordre des priorités, et la ligne seulement là avec REF_UD',
    listeB2.groupes.join(' ') === attendusB2.join(' ') && listeB2.seul.length === 1 && listeB2.seul[0].ref === 'UD-99-9999' &&
    listeB2.seul[0].la === 'UD-99-9999' && listeB2.seul[0].gates === '' && /^aucun plan dans GATES/.test(listeB2.seul[0].bulle), JSON.stringify([listeB2, attendusB2]));
  await pr.click('#liste-rapprochement .rapp-groupe[data-cle="seul"] button[data-ligne-la]'); await pr.waitForTimeout(500);
  verifier('un clic sur cette référence ouvre le tableau de Base2 cherché sur UD-99-9999, le lot retiré, le jeton de recherche posé',
    await pr.evaluate(() => {
      const l = document.querySelectorAll('#corps-seconde tr[data-i]');
      const jetons = [...document.querySelectorAll('.jeton')].map(j => j.textContent);
      return document.getElementById('recherche-seconde').value === 'UD-99-9999' && l.length === 1 && !document.getElementById('cadre-seconde').hidden &&
        jetons.some(j => /Recherche dans Base2 : UD-99-9999/.test(j)) && !jetons.some(j => /Comparaison : /.test(j));
    }));
  await ctxRapp.close();

  // =================================================================
  section('Aperçu quand l\'historique est vide');
  construire({ gates: true, historique: 'premier', sortie: 'apercu-premier.html' });
  const ctxPremier = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pp = await ctxPremier.newPage();
  pp.on('pageerror', e => erreursJS.push('premier : ' + e.message));
  pp.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push('premier : ' + m.text()); });
  await pp.goto('file://' + path.join(__dirname, '..', 'apercu-premier.html'));
  await pp.waitForTimeout(1600);

  /* L'interrupteur porte sur tout — il n'y a plus un bouton par bloc, et on
     ne peut pas se retrouver a moitie en exemple. Devant un classeur, il est
     visible : il y a de quoi comparer. */
  const depart = await pp.evaluate(() => ({
    present: !!document.getElementById('mode-donnees'),
    visible: !document.getElementById('mode-donnees').hidden && document.getElementById('mode-donnees').offsetParent !== null,
    presse: [...document.querySelectorAll('#mode-donnees button')]
      .map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')),
    mot: document.getElementById('mot-mode').textContent.trim(),
    marque: document.body.dataset.exemple
  }));
  verifier('l\'interrupteur est la, visible devant le classeur',
    depart.present && depart.visible, JSON.stringify(depart));
  verifier('il demarre sur les donnees reelles, sans un mot de trop',
    depart.presse.join(' ') === 'reel:true exemple:false' && depart.mot === '' &&
    depart.marque === 'false', JSON.stringify(depart));
  verifier('le journal explique pourquoi il est vide',
    await pp.evaluate(() => /deuxième archivage/.test(document.getElementById('zone-journal').textContent)));

  const avantEx = await pp.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await basculerMode(pp, 'exemple'); await pp.waitForTimeout(900);
  const ex = await pp.evaluate(() => ({
    mot: document.getElementById('mot-mode').textContent,
    marque: document.body.dataset.exemple,
    encadre: getComputedStyle(document.getElementById('bandeau-mode')).borderStyle,
    zones: document.querySelectorAll('.zone-clic').length,
    points: document.querySelectorAll('svg.graphe circle').length,
    presse: [...document.querySelectorAll('#mode-donnees button')]
      .map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')),
    plans: document.querySelectorAll('#corps-tableau tr').length,
    journal: document.getElementById('zone-journal').textContent,
    phrase: document.getElementById('phrase').textContent
  }));
  verifier('l\'apercu trace une vraie courbe', ex.points >= 5, String(ex.points));
  verifier('et remplit aussi le journal des changements',
    /UD-/.test(ex.journal) && !/deuxième archivage/.test(ex.journal), ex.journal.slice(0, 90));
  verifier('la page se marque en exemple, cadre compris',
    ex.marque === 'true' && /dashed/.test(ex.encadre), ex.marque + ' / ' + ex.encadre);
  verifier('l\'interrupteur montre ou l\'on est',
    ex.presse.join(' ') === 'reel:false exemple:true', JSON.stringify(ex.presse));
  /* La phrase doit dire exactement ce qui est fabrique. Elle annoncait
     « tout est fabrique » alors que les plans, eux, restent les vrais : une
     phrase qui exagere se fait prendre en defaut. */
  verifier('et il dit ce qui est fabrique : l\'historique, pas les plans',
    /historique/i.test(ex.mot) && !/tout ce qui est affich/i.test(ex.mot), ex.mot);
  verifier('les plans affiches restent ceux de la feuille',
    ex.plans === 186 && /186 plans/.test(ex.phrase), ex.phrase);

  await basculerMode(pp, 'reel'); await pp.waitForTimeout(800);
  const revenu = await pp.evaluate(() => ({
    mot: document.getElementById('mot-mode').textContent.trim(),
    marque: document.body.dataset.exemple,
    presse: [...document.querySelectorAll('#mode-donnees button')]
      .map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')),
    journal: document.getElementById('zone-journal').textContent,
    zones: document.querySelectorAll('.zone-clic').length
  }));
  verifier('revenir au reel remet tout en place',
    revenu.marque === 'false' && revenu.mot === '' &&
    revenu.presse.join(' ') === 'reel:true exemple:false', JSON.stringify(revenu));
  verifier('le journal redit qu\'il attend un deuxieme archivage',
    /deuxième archivage/.test(revenu.journal));
  verifier('et le graphique retrouve son cadrage', revenu.zones === avantEx,
    avantEx + ' → ' + revenu.zones);

  // Dix bascules d'affilee : ni fuite, ni etat coince.
  for (let i = 0; i < 5; i++) {
    await basculerMode(pp, 'exemple'); await pp.waitForTimeout(160);
    await basculerMode(pp, 'reel'); await pp.waitForTimeout(160);
  }
  await pp.waitForTimeout(700);
  verifier('dix bascules d\'affilee laissent la page intacte',
    await pp.evaluate(() => document.body.dataset.exemple === 'false' &&
      document.querySelectorAll('#corps-tableau tr').length === 186 &&
      document.querySelectorAll('.zone-clic').length > 0));
  // Re-cliquer le mode deja actif ne doit rien recalculer de travers.
  await basculerMode(pp, 'reel'); await pp.waitForTimeout(500);
  verifier('re-cliquer le mode actif ne change rien',
    await pp.evaluate(() => document.body.dataset.exemple === 'false' &&
      document.querySelectorAll('#corps-tableau tr').length === 186));

  /* Le mecanisme reste meme avec de l'historique : il sert a montrer la page
     a quelqu'un, avec une courbe, avant que les releves se soient accumules. */
  verifier('le mecanisme de l\'exemple reste meme avec de l\'historique',
    await pg.evaluate(() => !!document.querySelector('#mode-donnees button[data-mode="exemple"]')));
  await ctxPremier.close();

  // =================================================================
  /* La page assemblée sur le classeur à deux contrats, avec un
     google.script.run factice qui répond par le vrai serveur : le sélecteur
     est là, changer de contrat demande son paquet au classeur par le pont
     d'Index.html et la page passe sur l'autre onglet. Un contrat introuvable
     ou une panne du classeur laissent la page sur le contrat courant. */
  section('Changer de contrat dans la page rendue');
  const ctxMulti = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pm = await ctxMulti.newPage();
  pm.on('pageerror', e => erreursJS.push('contrats : ' + e.message));
  /* La panne simulée passe par le rappel d'échec du pont, qui la journalise
     en console.error : c'est le comportement attendu, pas une erreur du test. */
  pm.on('console', m => {
    if (m.type() === 'error' && !m.text().includes('ERR_FILE') && !/Contrat non chargé/.test(m.text())) {
      erreursJS.push('contrats : ' + m.text());
    }
  });
  await brancherClasseur(pm, multi.contexte);
  await pm.goto('file://' + path.join(__dirname, '..', 'apercu-contrats.html'));
  await pm.waitForTimeout(1600);
  const etatPage = () => pm.evaluate(() => ({
    visible: !document.getElementById('choix-contrat').hidden &&
             document.getElementById('select-contrat').offsetParent !== null,
    options: [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(','),
    courant: document.getElementById('select-contrat').value,
    disabled: document.getElementById('select-contrat').disabled,
    etat: document.getElementById('etat-contrat').textContent,
    nom: document.getElementById('select-contrat').value,
    masthead: document.querySelector('.masthead').textContent,
    plans: document.querySelectorAll('#corps-tableau tr').length,
    etats: [...document.querySelectorAll('#etats .etat-n')].reduce((s, e) => s + (+e.textContent.replace(/\s/g, '')), 0),
    totauxGroupes: [...document.querySelectorAll('.critique-total')].reduce((s, t) => s + (+t.textContent), 0),
    releves: window.__serieAffichee().pts.length,
    phrase: document.getElementById('phrase').textContent,
    appels: window.__appelsClasseur.slice()
  }));
  const departM = await etatPage();
  verifier('avec deux contrats, le sélecteur est visible et les liste dans l\'ordre des onglets',
    departM.visible && departM.options === 'X1,X2' && departM.courant === 'X1', JSON.stringify(departM.options));
  verifier('le contrat courant est celui du sélecteur, sans rappel sous le titre', departM.nom === 'X1' && !/contrat/i.test(departM.masthead), departM.nom);
  verifier('la page s\'ouvre sur le premier contrat, avec ses relevés, sans rien demander au classeur',
    departM.plans === 186 && departM.etats === 186 && departM.releves === pM.releves.length && departM.appels.length === 0,
    JSON.stringify([departM.plans, departM.releves, departM.appels]));

  await pm.selectOption('#select-contrat', 'X2'); await pm.waitForTimeout(1500);
  const x2M = await etatPage();
  verifier('changer de contrat demande le paquet de X2 au classeur, par le pont',
    x2M.appels.join() === 'X2', JSON.stringify(x2M.appels));
  verifier('et la page passe sur X2 : ses 93 plans partout, son nom sous le titre',
    x2M.plans === 93 && x2M.etats === 93 && x2M.totauxGroupes === 93 && x2M.nom === 'X2' &&
    x2M.courant === 'X2' && /93 plans/.test(x2M.phrase), JSON.stringify([x2M.plans, x2M.etats, x2M.totauxGroupes, x2M.nom]));
  /* Le classeur a bougé depuis l'assemblage de la page (suppressions plus
     haut) : le pont sert son état du moment, pas celui de l'ouverture. */
  verifier('le graphique trace l\'historique de X2, tel qu\'il est dans le classeur à cet instant',
    x2M.releves === cM.getHistorique(clM, 'X2').length && x2M.releves >= 2,
    x2M.releves + ' vs ' + cM.getHistorique(clM, 'X2').length);
  verifier('le sélecteur est rendu à la main, sans message', !x2M.disabled && x2M.etat === '', x2M.etat);

  /* Un contrat introuvable — ajouté au sélecteur pour la démonstration : le
     serveur répond par un paquet d'erreur, la page le montre et garde X2. */
  await pm.evaluate(() => {
    const o = document.createElement('option'); o.value = 'Nulle part'; o.textContent = 'Nulle part';
    document.getElementById('select-contrat').appendChild(o);
  });
  await pm.selectOption('#select-contrat', 'Nulle part'); await pm.waitForTimeout(1200);
  const rateM = await etatPage();
  verifier('un contrat introuvable : la page garde X2, remet le sélecteur dessus et montre le message du serveur',
    rateM.plans === 93 && rateM.courant === 'X2' && rateM.nom === 'X2' && !rateM.disabled &&
    /« Nulle part » est introuvable/.test(rateM.etat), JSON.stringify([rateM.plans, rateM.courant, rateM.etat]));
  verifier('une panne du classeur passe par le rappel d\'échec du pont : null, sans casser la page',
    await pm.evaluate(() => new Promise(resolve => {
      window.SUIVI_FWD_API.chargerContrat('__panne__', paquet => resolve(paquet === null));
    })) && (await etatPage()).plans === 93);

  await pm.selectOption('#select-contrat', 'X1'); await pm.waitForTimeout(1500);
  const retourM = await etatPage();
  verifier('revenir à X1 rend ses 186 plans et son historique',
    retourM.plans === 186 && retourM.etats === 186 && retourM.nom === 'X1' &&
    retourM.releves === cM.getHistorique(clM, 'X1').length && retourM.etat === '',
    JSON.stringify([retourM.plans, retourM.nom, retourM.releves]));
  await ctxMulti.close();

  await ctxGates.close();
  await ctx.close();
  await nav.close();

  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
  console.log('\nErreurs JavaScript : ' + (erreursJS.length ? '' : 'aucune'));
  [...new Set(erreursJS)].forEach(e => console.log('  ! ' + e));
  process.exit(echecs.length || erreursJS.length ? 1 : 0);
})();
