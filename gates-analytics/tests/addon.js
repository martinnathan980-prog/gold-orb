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
  /* Débrief 15 : « il ne faut pas qu'on se trompe de la source ». Une colonne
     nommée et introuvable n'est remplacée par aucune autre. */
  verifier('un forçage qui ne tombe sur rien ne se rabat sur aucune autre colonne — et le modèle le dit',
    !mInconnu.colonnes.some(c => c.cle === 'avancement') && mInconnu.fwdDemandeeAbsente === true &&
    mInconnu.plans.every(p => p.avancement === '') && /Colonne « Colonne qui n'existe pas » introuvable/.test(mInconnu.avertissement),
    mInconnu.avertissement);
  const paquetInconnu = forceInconnu.contexte.getDonneesPourClient();
  verifier('la page reçoit le message, en haut',
    paquetInconnu.ok === true && /introuvable/.test(paquetInconnu.message) && /archivage est refusé/.test(paquetInconnu.message), paquetInconnu.message);
  const diagInconnu = forceInconnu.contexte.diagnostic();
  verifier('le diagnostic le dit, et nomme les colonnes de même intitulé avec leur groupe',
    /✗ Colonne « Colonne qui n'existe pas » introuvable/.test(diagInconnu) && /Aucune colonne intitulée « colonne qui n'existe pas »/.test(diagInconnu),
    diagInconnu.split('\n').filter(l => /introuvable|intitulée/.test(l)).join(' / '));
  let refusInconnu = '';
  try { forceInconnu.contexte.enregistrerInstantaneHebdo(); } catch (e) { refusInconnu = String(e.message || e); }
  verifier('l’archivage refuse : pas de semaine « non renseignée » dans l’historique',
    /introuvable/.test(refusInconnu) && forceInconnu.contexte.getHistorique(forceInconnu.classeur).length === 0, refusInconnu);
  /* Le groupe a changé de nom dans l'export : le diagnostic montre où se trouve la colonne. */
  const groupeRenomme = serveurGates(20, { COLONNE_FWD: 'HDK AA 11 > Avancement Définition Electrique' });
  const diagRenomme = groupeRenomme.contexte.diagnostic();
  verifier('un groupe mal nommé : le diagnostic liste les groupes où l’intitulé existe, dont « HDK AA 011 »',
    /Colonnes intitulées « Avancement Définition Electrique », par groupe : .*« HDK AA 011 »/.test(diagRenomme),
    diagRenomme.split('\n').filter(l => /intitulées/.test(l)).join(' / ').slice(0, 300));
  const conceptAbsent = serveurGates(20, { COLONNE_CONCEPT: 'HDK AA 011 > Colonne absente' });
  const paquetSansConcept = conceptAbsent.contexte.getDonneesPourClient();
  let refusConcept = '';
  try { conceptAbsent.contexte.enregistrerInstantaneHebdo(); } catch (e) { refusConcept = String(e.message || e); }
  verifier('un concept harnais demandé et introuvable : la page le dit, pas d’interrupteur, pas d’archivage',
    paquetSansConcept.cleConcept === null && /Colonne absente/.test(paquetSansConcept.message) && /introuvable/.test(refusConcept),
    JSON.stringify([paquetSansConcept.message, refusConcept]));

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
    (rapportGates.match(/^  valeurs lues \(comptées comme\) : /gm) || []).length === 2, rapportGates.split('\n').filter(l => /valeurs lues/.test(l)).join(' / '));
  const rapportValide = serveurSur(feuilleExemple(10).map((l, i) => i === 4 ? l.map((c, j) => j === 8 ? 'Validé' : c) : l)).contexte.diagnostic();
  verifier('chaque valeur dit comment elle est comptée : « Validé » 1 → validé',
    /« Validé » 1 → validé/.test(rapportValide) && /→ en cours/.test(rapportValide) && !/Aucune valeur n'est comptée comme validée/.test(rapportValide),
    rapportValide.split('\n').filter(l => /valeurs lues/.test(l)).join(' / '));
  /* Débrief 16 : « 0 sur 600 terminés » sur les vraies données. Un vocabulaire
     que la page ne connaît pas se voit au diagnostic ET sur la page. */
  const vocab = ['Released', 'Checked', 'In work', 'Released', 'Released'];
  // Lignes 0 à 3 : titres, groupes, en-têtes ; les plans commencent ligne 4, avancement en colonne 8.
  const feuilleVocab = feuilleExemple(10).map((l, i) => i >= 4 && i < 9 ? l.map((c, j) => j === 8 ? vocab[i - 4] : c) : l);
  const rapportVocab = serveurSur(feuilleVocab.map(l => l.map((c, j) => j === 8 && /^(Terminé|Validé|OK|100 ?%|Fini|Soldé)$/i.test(c) ? 'Checked' : c))).contexte.diagnostic();
  verifier('un vocabulaire inconnu : le diagnostic l’annonce — « Aucune valeur n’est comptée comme validée »',
    /⚠ Aucune valeur n'est comptée comme validée/.test(rapportVocab) && /« Released » \d+ → en cours/.test(rapportVocab),
    rapportVocab.split('\n').filter(l => /valeurs lues|Aucune valeur/.test(l)).join(' / '));
  verifier('et le bilan du diagnostic le reprend : « À vérifier avant de présenter », au lieu de conclure seul « tout est en place »',
    /\nÀ vérifier avant de présenter \(\d+\) :\n(  ⚠ .*\n?)*  ⚠ Aucune valeur n'est comptée comme validée/.test(rapportVocab),
    rapportVocab.split('\n').slice(-6).join(' / '));
  /* Débrief 19 : la règle de la page — seul un mot rangé « en cours » peut
     cacher un « validé » inconnu ; le concept harnais a son vocabulaire. */
  const ctxDiag19 = serveurSur(feuilleExemple(10)).contexte, lus19 = [];
  const direValeurs19 = (plans, estConcept) => { lus19.length = 0; ctxDiag19.direValeurs(l => lus19.push(l), plans.map(v => ({ c: v })), 'c', estConcept); return lus19.join('\n'); };
  const diag19 = {
    concept: direValeurs19(['À traiter', '', 'À traiter', ''], true),
    afaire: direValeurs19(['Pas commencé', '', 'Pas commencé'], false),
    inconnu: direValeurs19(['Released', 'Pas commencé', ''], false)
  };
  verifier('débrief 19 : au Diagnostic, pas d’avertissement « aucune valeur validée » au concept harnais sans « Traité », ni sur des plans tous à faire ; un mot inconnu le garde',
    !/Aucune valeur n'est comptée/.test(diag19.concept) && !/Aucune valeur n'est comptée/.test(diag19.afaire) && /⚠ Aucune valeur n'est comptée comme validée/.test(diag19.inconnu),
    JSON.stringify(diag19));
  verifier('et celle du concept harnais, avec ses comptes',
    /✓ Concept harnais : colonne « Avancement Concept Harnais », groupe « HDK AA 011 »/.test(rapportGates) &&
    /✓ Concept harnais[^\n]*\n  \d+ validés, \d+ en cours, \d+ à faire, \d+ non renseignés/.test(rapportGates),
    rapportGates.split('\n').filter(l => /Concept harnais/.test(l)).join(' / '));
  verifier('il liste les colonnes d\'analyse en clair',
    /Analyse par : .*ATA/.test(rapportGates), rapportGates.split('\n').find(l => /Analyse par/.test(l)));
  verifier('il signale les lignes ignorées et annonce l\'extract entier',
    /1 ligne\(s\) sans référence ignorée/.test(rapportGates) &&
    /Tableau ouvert sur les 138 colonnes de la feuille, dans son ordre/.test(rapportGates),
    rapportGates.split('\n').find(l => /Tableau ouvert/.test(l)));

  /* Débrief 16 : « deux semaines archivées, et le journal reste vide ». Le
     diagnostic dit combien de plans ont changé entre les deux derniers
     relevés — et quand ils sont identiques, pourquoi le journal est vide. */
  const dj = serveurSur(feuilleExemple(12));
  dj.contexte.enregistrerInstantaneHebdo();
  const fhj = dj.contexte.getFeuilleHistorique(dj.classeur, undefined, false);
  const semJ = dj.contexte.numeroSemaineISO(new Date());
  const precedente = (() => { const [a, w] = semJ.split('-S').map(Number); return w > 1 ? a + '-S' + String(w - 1).padStart(2, '0') : (a - 1) + '-S52'; })();
  fhj.valeurs[1][0] = precedente;                     // le relevé d'avant, même extract
  dj.contexte.enregistrerInstantaneHebdo();
  const diagJ = dj.contexte.diagnostic();
  verifier('deux relevés identiques : le diagnostic le dit, et que le journal restera vide',
    /entre \d{4}-S\d\d et \d{4}-S\d\d : 0 plan\(s\) ont changé de valeur/.test(diagJ) && /⚠ Les deux derniers relevés sont identiques/.test(diagJ),
    diagJ.split('\n').filter(l => /relevé|journal|changé/.test(l)).join(' / '));
  verifier('et il ne recopie ni valeur ni référence : des comptes seulement',
    !diagJ.split('\n').filter(l => /changé de valeur|s'écarte du dernier relevé/.test(l)).some(l => /UD-\d/.test(l)),
    diagJ.split('\n').filter(l => /changé de valeur|s'écarte/.test(l)).join(' / '));

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
  /* Le vrai vocabulaire de GATES, relevé au bureau (débrief 17). */
  const vraiesValeurs = { VALIDATED: 'termine', PWD_IN_PROGRESS: 'encours', PWD_TO_CONTROL: 'encours', TO_CONFIRM: 'encours',
                          FWD_TO_SEIZE: 'afaire', TO_TREAT: 'afaire', EMPTY: 'vide' };
  const ecartsGates = Object.keys(vraiesValeurs).filter(v => contexte.classerFWD(v) !== vraiesValeurs[v]);
  verifier('le vocabulaire réel de GATES : VALIDATED fini, TO_TREAT et FWD_TO_SEIZE pas commencés, le reste en cours',
    !ecartsGates.length, ecartsGates.join(', '));
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
  const ENTETES_H = ['Semaine', 'Date', 'Total', 'Validés', 'En cours', 'À faire', 'Non renseignés', 'Par dimension', 'Plans'];
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
    /^Relevé S\d{1,2} supprimé pour « X1 », « X2 »\. Importez le bon export \(menu Suivi FWD → Importer les exports GATES et SEE…, qui archive dans la foulée\), ou recollez-le puis relancez l'archivage\./.test(cM.__alertes[cM.__alertes.length - 1]),
    cM.__alertes[cM.__alertes.length - 1]);
  const sM2 = cM.supprimerDernierReleve();
  verifier('une seconde suppression n\'a plus rien à retirer, et le dit',
    sM2.supprimes.length === 0 && sM2.sans.join() === 'X1,X2' &&
    /^Aucun relevé pour la semaine en cours \(S\d{1,2}\)\.$/.test(cM.__alertes[cM.__alertes.length - 1]),
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
    /^Relevé S\d{1,2} archivé : X1 \(20 plans\)\. Un second archivage dans la semaine remplace celui-ci\.$/.test(boite), boite);

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
    typeof j.contexte.sauverJalons === 'undefined' && !/CLE_JALONS/.test(fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8')) &&
    /* Les propriétés du document ne gardent que la version des données, les consultations (débrief 18)
       et le jeton de la fenêtre d'import SEE (débrief 20). */
    (fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8').match(/[gs]etProperty\(([A-Z_]+)/g) || []).every(x => /CLE_VERSION_DONNEES|CLE_CONSULTATIONS|CLE_JETON_IMPORT/.test(x)));
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
  section('Débrief 17 (réponses) : des jalons pour HDK seulement');
  /* « THS n'a pas du tout les mêmes (jalons), c'est un autre contrat… les
     autres, il n'y a pas de jalons » : chaque jalon livré porte contrat: 'HDK'.
     Un classeur au vrai nom de contrat — HDK et THS — garde la
     configuration livrée telle quelle (le banc ne l'adapte qu'aux classeurs
     d'essai sans onglet HDK). */
  const fabriquerHT = () => {
    const gH = feuilleGates(40), gT = feuilleGates(30);
    return new Classeur([new Feuille('HDK', gH.valeurs, false, gH.fusions), new Feuille('THS', gT.valeurs, false, gT.fusions)], 'Suivi FWD');
  };
  const clJ = fabriquerHT();
  const cJ = chargerServeur(clJ, {});
  const livres17 = vm.runInContext('CONFIG.JALONS', cJ);
  verifier('les cinq jalons livrés appartiennent au contrat HDK',
    livres17.length === 5 && livres17.every(x => x.contrat === 'HDK'), JSON.stringify(livres17.map(x => x.contrat)));
  const pqH = cJ.getDonneesPourClient('HDK'), pqT = cJ.getDonneesPourClient('THS');
  verifier('la page de HDK reçoit ses cinq jalons, celle de THS aucun',
    pqH.ok && pqT.ok && pqH.jalons.length === 5 && pqT.jalons.length === 0,
    pqH.jalons.length + ' / ' + pqT.jalons.length);
  verifier('le paquet compact (changement de contrat dans la page) dit pareil',
    cJ.getDonneesCompactes('HDK').jalons.length === 5 && cJ.getDonneesCompactes('THS').jalons.length === 0);
  verifier('la clé contrat ne voyage pas jusqu\'à la page : les jalons de HDK sont ceux d\'avant, tels quels',
    pqH.jalons.every(x => !('contrat' in x)) &&
    pqH.jalons.map(x => x.texte + '@' + x.semaine).join() ===
      'Solde FWD@2026-S51,Diffusion PH Base@2027-S02,Diffusion PH Perso@2027-S03,Diffusion TO Base@2027-S05,Diffusion TO Perso@2027-S08',
    JSON.stringify(pqH.jalons));
  verifier('le nom du contrat se compare sans casse ni espaces autour ; sans contrat demandé, tous les jalons',
    cJ.getJalons('hdk').length === 5 && cJ.getJalons(' Hdk ').length === 5 && cJ.getJalons('THS').length === 0 &&
    cJ.getJalons().length === 5);
  vm.runInContext('CONFIG.JALONS = ' + JSON.stringify([
    { semaine: '2026-S50', texte: 'Pour tous' },
    { semaine: '2026-S51', texte: 'Les deux', contrat: ['HDK', 'ths'] },
    { semaine: '2026-S52', texte: 'THS seul', contrat: 'THS' },
    { semaine: '2027-S01', texte: 'Vide', contrat: '  ' },
    { semaine: '2027-S02', texte: 'Fantôme', contrat: 'HDX' }
  ]), cJ);
  verifier('sans contrat (ou vide) : tous ; une liste : chacun des contrats nommés ; un nom : lui seul',
    cJ.getJalons('HDK').map(x => x.texte).join() === 'Pour tous,Les deux,Vide' &&
    cJ.getJalons('THS').map(x => x.texte).join() === 'Pour tous,Les deux,THS seul,Vide',
    cJ.getJalons('HDK').map(x => x.texte).join() + ' | ' + cJ.getJalons('THS').map(x => x.texte).join());
  const diagJ17 = cJ.diagnostic();
  verifier('le Diagnostic dit combien de jalons voit chaque contrat',
    /par contrat : « HDK » 3 jalons · « THS » 4 jalons/.test(diagJ17), (diagJ17.match(/par contrat[^\n]*/) || [''])[0]);
  verifier('et prévient d\'un contrat qu\'aucun onglet ne porte : ce jalon n\'apparaîtrait nulle part',
    /⚠ Jalon « Fantôme » : contrat « HDX » — aucun contrat ne porte ce nom \(onglet absent, masqué ou écarté\)/.test(diagJ17) &&
    !/Jalon « Les deux » : contrat/.test(diagJ17) && !/Jalon « Vide » : contrat/.test(diagJ17), diagJ17);
  /* L'onglet HDK renommé : les cinq jalons ne se voient plus nulle part —
     un seul avertissement, qui les compte. */
  vm.runInContext('CONFIG.JALONS = ' + JSON.stringify(livres17.map(x => Object.assign({}, x, { contrat: 'HDK 2026' }))), cJ);
  const diagRenomme17 = cJ.diagnostic();
  verifier('les cinq jalons d\'un contrat introuvable : un seul avertissement, qui les compte',
    (diagRenomme17.match(/^⚠ [^\n]*: contrat « HDK 2026 »/gm) || []).length === 1 &&
    /⚠ 5 jalons : contrat « HDK 2026 » — aucun contrat ne porte ce nom \(onglet absent, masqué ou écarté\) : ils n'apparaissent sur aucune page\./.test(diagRenomme17),
    (diagRenomme17.match(/[^\n]*HDK 2026[^\n]*/g) || []).join(' | '));
  vm.runInContext('CONFIG.JALONS = ' + JSON.stringify(livres17), cJ);
  const diagLivre = cJ.diagnostic();
  verifier('avec la configuration livrée : « HDK » 5 jalons · « THS » aucun jalon, les périmètres vérifiés sur HDK, sans avertissement de contrat',
    /par contrat : « HDK » 5 jalons · « THS » aucun jalon/.test(diagLivre) &&
    /périmètres des jalons \(« HDK »\) : BASE\/OPTION, PERSO — tous connus de la colonne « Domaine »/.test(diagLivre) &&
    !/: contrat « /.test(diagLivre), diagLivre);
  verifier('tous les plans de HDK ont un Domaine des jalons : pas de ligne « hors des périmètres »',
    !/hors des périmètres des jalons/.test(diagLivre));
  // Trois plans de HDK sans Domaine : le Diagnostic les compte, sans rien recopier.
  const ongletH17 = clJ.getSheetByName('HDK');
  const iDom17 = ongletH17.valeurs[1].indexOf('Domaine');
  ongletH17.valeurs.filter(l => /^UD-/.test(l[1] || '')).slice(0, 3).forEach(l => { l[iDom17] = ''; });
  const diagHors = cJ.diagnostic();
  verifier('trois plans à Domaine vide : le Diagnostic dit qu’aucun jalon à périmètre ne les compte — un nombre, rien de recopié',
    /  3 plans \(« HDK »\) à « Domaine » vide ou hors des périmètres des jalons : aucun jalon à périmètre ne les compte, seuls les jalons sans périmètre\./.test(diagHors),
    (diagHors.match(/[^\n]*hors des périmètres[^\n]*/) || [''])[0]);
  /* La vue d'ensemble charge chaque contrat par son propre paquet : THS n'y
     a donc pas d'échéance. Le banc des classeurs d'essai, lui, garde les
     jalons pour ses contrats sans nom HDK. */
  const cEssai = chargerServeur(new Classeur([new Feuille('X1', feuilleExemple(20))]), {});
  verifier('un classeur d\'essai sans onglet HDK garde les jalons pour ses contrats (banc de test)',
    cEssai.getDonneesPourClient('X1').jalons.length === 5);

  // =================================================================
  section('Débrief 17 (réponses) : archiver l\'onglet affiché pour une semaine passée');
  /* « J'en ai que 2 » : l'export de la semaine dernière et celui de cette
     semaine. S39 et S40 portaient le même : aucun rythme. Le menu remet
     l'export de la semaine dernière à sa semaine. */
  const clP = fabriquerHT();
  const cP = chargerServeur(clP, {});
  const courante17 = cP.numeroSemaineISO(new Date());
  const precedente17 = cP.numeroSemaineISO(new Date(Date.now() - 7 * 864e5));
  const numPrec = parseInt(precedente17.slice(6), 10);
  cP.enregistrerInstantaneHebdo();
  const histoHDK = () => cP.getHistorique(clP, 'HDK'), histoTHS = () => cP.getHistorique(clP, 'THS');
  verifier('le menu propose le geste, et chaque entrée du menu est une fonction du serveur',
    (cP.onOpen(), cP.__menu.indexOf('archiverSemainePassee') !== -1) &&
    cP.__menu.every(f => typeof cP[f] === 'function'), cP.__menu.join(', '));
  // L'export de la semaine dernière : moins de plans validés que celui du jour.
  const ongletHDK = clP.getSheetByName('HDK');
  const bH = ongletHDK.valeurs[0].indexOf('HDK AA 011') + 3;
  const lignesHDK = ongletHDK.valeurs.filter(l => /^UD-/.test(l[1] || ''));
  const avantValides = lignesHDK.filter(l => l[bH] === '100%').length;
  const exportDuJour = lignesHDK.map(l => l[bH]);
  lignesHDK.filter(l => l[bH] === '100%').slice(0, 5).forEach(l => { l[bH] = 'EMPTY'; });
  clP.setActiveSheet(ongletHDK);
  cP.__saisies.push({ bouton: 'OK', texte: 'S' + numPrec });
  cP.__confirmations.push('YES');
  const alertesAvant = cP.__alertes.length;
  const rP = cP.archiverSemainePassee();
  const confirmation = cP.__alertes[alertesAvant], resultatP = cP.__alertes[alertesAvant + 1];
  verifier('« S' + numPrec + ' » tapé : la question confirme le contrat et la semaine, dit qu\'il n\'y a rien à remplacer, et rappelle de remettre l\'export du jour (l\'import d\'abord, le collage ensuite)',
    new RegExp('^Archiver l\'export affiché dans « HDK » comme relevé S' + numPrec + ' \\?').test(confirmation) &&
    /Aucun relevé S\d+ n'existe encore pour « HDK » : il est ajouté\./.test(confirmation) &&
    /remets tout de suite l'export du jour dans « HDK » \(menu Suivi FWD → Importer les exports GATES et SEE…, ou un collage\)/.test(confirmation), confirmation);
  verifier('le relevé de la semaine passée est archivé pour HDK seulement, avec les chiffres de l\'export affiché',
    rP && rP.ok && rP.semaine === precedente17 &&
    histoHDK().map(r => r.semaine).join() === precedente17 + ',' + courante17 &&
    histoHDK()[0].termine === avantValides - 5 && histoHDK()[1].termine === avantValides &&
    histoTHS().map(r => r.semaine).join() === courante17,
    JSON.stringify([rP, histoHDK().map(r => [r.semaine, r.termine]), histoTHS().map(r => r.semaine)]));
  verifier('et le message final redit de remettre l\'export du jour : l\'importer (il archive dans la foulée), ou le recoller puis archiver',
    new RegExp('^Relevé S' + numPrec + ' de « HDK » archivé avec l\'export affiché \\(40 plans\\)\\.').test(resultatP) &&
    /⚠ L'onglet « HDK » porte maintenant l'export de S\d+ : importe l'export du jour \(menu Suivi FWD → Importer les exports GATES et SEE…, qui archive dans la foulée\), ou recolle-le puis Suivi FWD → Archiver le relevé de cette semaine\./.test(resultatP), resultatP);
  verifier('la page de HDK a maintenant deux relevés différents : un rythme',
    cP.getDonneesPourClient('HDK').releves.length === 2 &&
    cP.getDonneesPourClient('HDK').releves[1].termine - cP.getDonneesPourClient('HDK').releves[0].termine === 5);
  // Une seconde fois la même semaine : on remplace, après l'avoir dit.
  lignesHDK.filter(l => l[bH] === 'EMPTY').slice(0, 2).forEach(l => { l[bH] = '100%'; });
  cP.__saisies.push({ bouton: 'OK', texte: String(numPrec) });
  cP.__confirmations.push('YES');
  const a2 = cP.__alertes.length;
  const rP2 = cP.archiverSemainePassee();
  verifier('la même semaine une seconde fois (« ' + numPrec + ' » sans S) : la question dit qu\'elle remplace, et l\'historique garde une seule ligne',
    rP2 && rP2.ok && /Il remplace le relevé S\d+ déjà archivé pour « HDK »\./.test(cP.__alertes[a2]) &&
    /^Relevé S\d+ de « HDK » remplacé/.test(cP.__alertes[a2 + 1]) &&
    histoHDK().length === 2 && histoHDK()[0].termine === avantValides - 3,
    JSON.stringify([cP.__alertes.slice(a2), histoHDK().map(r => [r.semaine, r.termine])]));
  // NON à la confirmation, Annuler à la question : rien n'est écrit.
  const ligneAvant = JSON.stringify(histoHDK());
  cP.__saisies.push({ bouton: 'OK', texte: 'S' + numPrec });
  cP.__confirmations.push('NO');
  const rNon = cP.archiverSemainePassee();
  cP.__saisies.push({ bouton: 'CANCEL', texte: 'S' + numPrec });
  const rAnnule = cP.archiverSemainePassee();
  verifier('« Non » à la confirmation, ou « Annuler » : rien n\'est archivé',
    rNon === null && rAnnule === null && JSON.stringify(histoHDK()) === ligneAvant);
  // Les refus : illisible, à venir, onglet qui n'est pas un contrat.
  const refus = (texte, onglet) => cP.preparerSemainePassee(clP, onglet || 'HDK', texte);
  verifier('une semaine illisible est refusée, et le message dit comment l\'écrire',
    ['semaine 39', 'S60', '', '2026-S99', '2025-S53', 'S53 2025'].every(t => !refus(t).ok &&
      new RegExp('^Semaine illisible \\(ou qui n\'existe pas\\) : « .* »\\. Écrire par exemple S' + parseInt(courante17.slice(6), 10) + ' \\(ou ' + courante17 + '\\)\\.$').test(refus(t).message)),
    refus('S60').message);
  verifier('une semaine à venir (écrite avec son année) est refusée',
    !refus('2099-S10').ok && /n'est pas encore arrivée : rien n'est archivé/.test(refus('2099-S10').message), refus('2099-S10').message);
  const suivante17 = cP.numeroSemaineISO(new Date(Date.now() + 7 * 864e5));
  verifier('la semaine suivante tapée sans année (« S' + parseInt(suivante17.slice(6), 10) + ' ») est à venir : refusée — jamais prise pour celle de l\'an dernier',
    !refus('S' + parseInt(suivante17.slice(6), 10)).ok && /n'est pas encore arrivée/.test(refus('S' + parseInt(suivante17.slice(6), 10)).message),
    JSON.stringify(refus('S' + parseInt(suivante17.slice(6), 10))));
  verifier('« S52 » tapé début janvier : celle de l\'an dernier ; « S53 » seulement si l\'année en a une ; « S52 2026 » se lit aussi',
    cP.semaineSaisie('S52', '2027-S02') === '2026-S52' && cP.semaineSaisie('53', '2027-S02') === '2026-S53' &&
    cP.semaineSaisie('S53', '2026-S40') === '2026-S53' && cP.semaineSaisie('S53', '2027-S40') === null &&
    cP.semaineSaisie('S30', '2027-S02') === '2027-S30' && cP.semaineSaisie('S52 2026', '2027-S02') === '2026-S52' &&
    cP.semaineSaisie('s 39', '2026-S40') === '2026-S39' && cP.semaineSaisie('2026-S39', '2026-S40') === '2026-S39',
    JSON.stringify(['S52', '53', 'S53', 'S53/2027', 'S30', 'S52 2026'].map((t, i) => cP.semaineSaisie(t.split('/')[0], i === 3 ? '2027-S40' : i === 2 ? '2026-S40' : '2027-S02'))));
  verifier('l\'onglet affiché doit être un contrat : un onglet d\'historique est refusé, avec le geste',
    !refus('S' + numPrec, 'Historique_FWD_HDK').ok &&
    /« Historique_FWD_HDK », n'est pas un contrat : afficher l'onglet du contrat \(HDK…\)/.test(refus('S' + numPrec, 'Historique_FWD_HDK').message),
    refus('S' + numPrec, 'Historique_FWD_HDK').message);
  const gCopie = feuilleGates(40);
  const copieS39 = new Feuille('HDK S' + numPrec, gCopie.valeurs, false, gCopie.fusions);
  clP.feuilles.push(copieS39);
  const rCopie = refus('S' + numPrec, 'HDK S' + numPrec);
  verifier('l\'export rattrapé collé dans un nouvel onglet « HDK S' + numPrec + ' » : refusé — ce serait un nouveau contrat —, avec le bon geste',
    !rCopie.ok && new RegExp('« HDK S' + numPrec + ' » n\'a aucun relevé : ce serait un nouveau contrat\\. Mettre l\'export de S' + numPrec + ' dans l\'onglet « HDK » lui-même — menu Suivi FWD → Importer les exports GATES et SEE…, case « Archiver » décochée, ou Ctrl\\+A, Suppr, A1, Ctrl\\+V —').test(rCopie.message) &&
    !clP.getSheetByName('Historique_FWD_HDK S' + numPrec), rCopie.message);
  /* Un nouvel onglet au nom sans rapport (« Semaine 39 ») : pas refusé —
     ce peut être un vrai nouveau contrat —, mais la question le dit. */
  const autreNom = new Feuille('Semaine ' + numPrec, feuilleGates(40).valeurs, false, feuilleGates(40).fusions);
  clP.feuilles.push(autreNom);
  const rAutre = refus('S' + numPrec, 'Semaine ' + numPrec);
  verifier('un nouvel onglet au nom sans rapport : la question prévient que ce sera un NOUVEAU contrat, et dit où coller pour rattraper',
    rAutre.ok && /ce sera un NOUVEAU contrat, avec son propre historique, archivé chaque vendredi\. Pour rattraper une semaine de « HDK », mettre l'export dans son onglet à lui \(par l'import, case « Archiver » décochée, ou par un collage\)\./.test(rAutre.question),
    rAutre.question || rAutre.message);
  clP.feuilles.splice(clP.feuilles.indexOf(autreNom), 1);
  clP.feuilles.splice(clP.feuilles.indexOf(copieS39), 1);
  verifier('la semaine en cours se tape aussi : pas de rappel de recoller, c\'est déjà l\'export du jour',
    refus('S' + parseInt(courante17.slice(6), 10)).ok && !/recolle/.test(refus('S' + parseInt(courante17.slice(6), 10)).question));
  /* L'export rattrapé laissé dans l'onglet : l'archivage de la semaine en
     cours (le vendredi, souvent) écraserait le bon relevé. Refusé, et dit. */
  const s40avant = JSON.stringify(histoHDK().map(r => [r.semaine, r.termine]));
  let refusEcrase = '';
  try { cP.enregistrerInstantaneHebdo(); } catch (e) { refusEcrase = String(e.message || e); }
  verifier('l\'export rattrapé laissé dans l\'onglet : l\'archivage de la semaine refuse d\'écraser le bon relevé, et dit quoi faire',
    new RegExp('« HDK » : l\'onglet « HDK » porte le même export que le relevé S' + numPrec + ' : le relevé S\\d+ déjà archivé, différent, n\'est pas écrasé\\. Importer l\'export du jour \\(menu Suivi FWD → Importer les exports GATES et SEE…, qui archive dans la foulée\\), ou le recoller puis archiver\\.').test(refusEcrase) &&
    JSON.stringify(histoHDK().map(r => [r.semaine, r.termine])) === s40avant && histoTHS().length === 1, refusEcrase);
  // L'export du jour recollé, puis archivé : S40 retrouve ses chiffres.
  lignesHDK.forEach((l, i) => { l[bH] = exportDuJour[i]; });
  cP.enregistrerInstantaneHebdo();
  verifier('recollé puis archivé, l\'export du jour refait la semaine en cours ; la semaine passée garde le sien',
    histoHDK().length === 2 && histoHDK()[1].termine === avantValides && histoHDK()[0].termine === avantValides - 3,
    JSON.stringify(histoHDK().map(r => [r.semaine, r.termine])));

  // =================================================================
  section('Débrief 17 (réponses) : la page est ouverte par tout le monde — elle ne modifie rien');
  /* « Qui ouvre la page ? Tout le monde… c'est que de la consultation. »
     L'application s'exécute au nom de Nathan : google.script.run atteint
     toute fonction publique. Les gestes qui écrivent refusent hors du
     classeur (getUi() lève) ; l'archivage du vendredi passe, reconnu à
     l'identifiant de son déclencheur. */
  const clG = fabriquerHT();
  const cG = chargerServeur(clG, {});
  cG.enregistrerInstantaneHebdo();
  cG.installerSuiviHebdomadaire();
  const declencheurs = () => cG.__declencheurs.filter(d => d.getHandlerFunction() === 'enregistrerInstantaneHebdo');
  verifier('du menu, l\'archivage automatique s\'active : un seul déclencheur, même activé deux fois',
    (cG.installerSuiviHebdomadaire(), declencheurs().length === 1));
  const uid = declencheurs()[0].getUniqueId();
  const histoG = () => JSON.stringify([cG.getHistorique(clG, 'HDK'), cG.getHistorique(clG, 'THS')].map(h => h.map(r => [r.semaine, r.total])));
  const avantG = histoG();
  cG.__sansInterface = true;   // la page, ouverte par un lecteur
  const refuse = (f, arg) => { try { cG[f](arg); return ''; } catch (e) { return String(e.message || e); } };
  const MOT = /^Geste refusé : il ne se lance que dans le classeur, menu Suivi FWD \(ou par l'archivage automatique du vendredi\)\. La page du tableau de bord ne modifie rien\.$/;
  verifier('depuis la page : archiver, supprimer, activer ou couper l\'archivage automatique, archiver une semaine passée — tout est refusé',
    ['enregistrerInstantaneHebdo', 'supprimerDernierReleve', 'installerSuiviHebdomadaire', 'desinstallerSuiviHebdomadaire', 'archiverSemainePassee']
      .every(f => MOT.test(refuse(f))), refuse('desinstallerSuiviHebdomadaire'));
  verifier('et rien n\'a bougé : relevés intacts, déclencheur du vendredi toujours là',
    histoG() === avantG && declencheurs().length === 1 && declencheurs()[0].getUniqueId() === uid);
  verifier('un faux déclencheur (identifiant inventé) est refusé aussi',
    MOT.test(refuse('enregistrerInstantaneHebdo', { triggerUid: 'invente' })) && MOT.test(refuse('enregistrerInstantaneHebdo', { triggerUid: '' })));
  const rVendredi = cG.enregistrerInstantaneHebdo({ triggerUid: uid, authMode: 'FULL' });
  verifier('le vrai déclencheur du vendredi, lui, archive sans interface',
    rVendredi && rVendredi.ok && rVendredi.contrats.length === 2, JSON.stringify(rVendredi && rVendredi.contrats.map(c => c.id)));
  verifier('et la page, elle, se sert toujours : la lecture n\'est pas un geste',
    cG.getDonneesPourClient('HDK').ok && cG.getDonneesCompactes('THS').ok);
  cG.__sansInterface = false;
  cG.desinstallerSuiviHebdomadaire();
  verifier('du menu, couper l\'archivage automatique marche toujours', declencheurs().length === 0);

  // =================================================================
  section('Débrief 18 : le concept harnais — vide, « À traiter », « Traité »');
  const cV18 = chargerServeur(fabriquerHT(), {});
  verifier('« Traité » (et Traitée, TRAITÉS) compte validé ; « À traiter » (ou A traiter) à faire ; vide non renseigné ; « Non traité » jamais validé',
    ['Traité', 'traitée', 'TRAITÉS', ' Traité '].every(v => cV18.classerFWD(v) === 'termine') &&
    ['À traiter', 'A traiter', 'a traiter'].every(v => cV18.classerFWD(v) === 'afaire') &&
    cV18.classerFWD('') === 'vide' && cV18.classerFWD('Non traité') !== 'termine',
    JSON.stringify(['Traité', 'À traiter', '', 'Non traité'].map(v => cV18.classerFWD(v))));

  // =================================================================
  section('Débrief 18 : le paquet de chaque contrat en cache, renouvelé dès que le classeur change');
  /* « Le site est très long à charger » : chaque ouverture relisait tout le
     classeur. Le paquet se garde en cache, sous une clé qui change à la
     moindre modification — un collage (onEdit), un archivage, un onglet. */
  const clK = fabriquerHT();
  const cK = chargerServeur(clK, {});
  cK.enregistrerInstantaneHebdo();
  cK.__activerCache();
  const sansHeure = o => { const c = JSON.parse(JSON.stringify(o)); delete c.genereLe; return JSON.stringify(c); };
  const frais = id => { vm.runInContext('PAGE_FRAICHE = true', cK); try { return sansHeure(cK.getDonneesCompactes(id)); } finally { vm.runInContext('PAGE_FRAICHE = false', cK); } };
  const k1 = cK.getDonneesCompactes('HDK');
  verifier('la première ouverture lit le classeur et garde le paquet en cache',
    k1.ok && Object.keys(cK.__memoireCache).some(k => /:n$/.test(k)), Object.keys(cK.__memoireCache).join(', '));
  const ongletK = clK.getSheetByName('HDK');
  const bK = ongletK.valeurs[0].indexOf('HDK AA 011') + 3;
  const ligneK = ongletK.valeurs.filter(l => /^UD-/.test(l[1] || '') && l[bK] !== '100%')[0];
  ligneK[bK] = '100%';          // un plan de plus validé, sans passer par onEdit
  const k2 = cK.getDonneesCompactes('HDK');
  verifier('la seconde ouverture est servie du cache : rien n\'est relu tant que rien ne dit le classeur modifié',
    JSON.stringify(k2) === JSON.stringify(k1));
  cK.onEdit({});
  const k3 = cK.getDonneesCompactes('HDK');
  verifier('un collage ou une saisie (onEdit) rend le cache caduc : l\'ouverture suivante voit l\'extract du jour',
    JSON.stringify(k3) !== JSON.stringify(k1) && sansHeure(k3) === frais('HDK'));
  cK.enregistrerInstantaneHebdo();
  verifier('un archivage aussi : le paquet suivant porte le relevé tout juste écrit', sansHeure(cK.getDonneesCompactes('HDK')) === frais('HDK') &&
    sansHeure(cK.getDonneesCompactes('HDK')) !== sansHeure(k3));
  clK.getSheetByName('THS').nom = 'THS 2';
  const k5 = cK.getDonneesCompactes('HDK');
  verifier('un onglet renommé aussi (la liste des contrats change) : « THS 2 » dans le paquet servi',
    k5.contrats.map(c => c.id).join() === 'HDK,THS 2', JSON.stringify(k5.contrats));
  clK.getSheetByName('THS 2').nom = 'THS';
  vm.runInContext('CONFIG.JALONS = []', cK);
  verifier('une configuration changée aussi (Code collé de nouveau) : plus de jalon servi',
    cK.getDonneesCompactes('HDK').jalons.length === 0);
  const avantErreur = Object.keys(cK.__memoireCache).length;
  const erreurK = cK.getDonneesCompactes('Nulle part');
  verifier('un paquet d\'erreur n\'est jamais gardé', erreurK.ok === false && Object.keys(cK.__memoireCache).length === avantErreur);
  /* ?frais=1 (relecture du revue 18) : il rend caduc tout le cache — la
     page ouverte relit, garde ce qu'elle a lu, et les ouvertures suivantes
     (et les changements de contrat) en profitent. */
  const ligneF = ongletK.valeurs.filter(l => /^UD-/.test(l[1] || '') && l[bK] !== '100%')[0];
  ligneF[bK] = '100%';          // sans onEdit : le cache est périmé
  const perimeF = sansHeure(cK.getDonneesCompactes('HDK'));
  cK.doGet({ parameter: { frais: '1' } });
  const apresF = sansHeure(cK.getDonneesCompactes('HDK'));
  const ensuiteF = sansHeure(cK.getDonneesCompactes('HDK'));
  verifier('?frais=1 rend tout le cache caduc : l\'ouverture relit le classeur, et les suivantes aussi voient l\'extract du jour',
    perimeF !== frais('HDK') && apresF === frais('HDK') && ensuiteF === apresF && vm.runInContext('PAGE_FRAICHE', cK) === false);
  // Des lignes supprimées ou ajoutées : onEdit ne les voit pas, la taille de l'onglet si.
  const tailleAvant = sansHeure(cK.getDonneesCompactes('HDK'));
  ongletK.deleteRow(ongletK.getLastRow());
  const tailleApres = sansHeure(cK.getDonneesCompactes('HDK'));
  verifier('des lignes supprimées (sans onEdit) : la taille de l\'onglet change, l\'ouverture relit le classeur',
    tailleApres !== tailleAvant && tailleApres === frais('HDK'));
  // Un historique illisible le temps d'une panne : ce paquet-là ne se garde pas.
  cK.onEdit({});
  vm.runInContext("var __hOrig = getHistorique, __hPannes = 1; getHistorique = function () { if (__hPannes-- > 0) throw new Error('Service Spreadsheets timed out'); return __hOrig.apply(this, arguments); };", cK);
  const pannee = cK.getDonneesCompactes('HDK');
  const remise = cK.getDonneesCompactes('HDK');
  vm.runInContext('getHistorique = __hOrig', cK);
  const relevesDe = p => (p.relevesTab ? p.relevesTab.releves : p.releves) || [];
  verifier('un historique illisible le temps d\'une panne n\'est pas gardé : l\'ouverture suivante retrouve la courbe',
    pannee.historiqueIllisible === true && !remise.historiqueIllisible && relevesDe(remise).length > 0,
    JSON.stringify([pannee.historiqueIllisible, remise.historiqueIllisible, relevesDe(remise).length]));
  // Un gros extract : le paquet se découpe sur plusieurs clés et se recolle à l'identique.
  const gG = feuilleGates(640);
  const clG18 = new Classeur([new Feuille('HDK', gG.valeurs, false, gG.fusions)], 'Gros');
  const cG18 = chargerServeur(clG18, {});
  cG18.enregistrerInstantaneHebdo();
  cG18.__activerCache();
  const g1 = cG18.donneesJSONPourPage();
  const nTranches = Number(Object.keys(cG18.__memoireCache).filter(k => /:n$/.test(k)).map(k => cG18.__memoireCache[k])[0]);
  const g2 = cG18.donneesJSONPourPage();
  verifier('un paquet de 640 plans se range sur plusieurs clés (moins de 100 Ko chacune) et se relit à l\'identique',
    nTranches > 1 && Object.keys(cG18.__memoireCache).filter(k => !/:n$/.test(k)).every(k => cG18.__memoireCache[k].length <= 30000) && g2 === g1,
    nTranches + ' tranches, ' + g1.length + ' caractères');

  // =================================================================
  section('Débrief 18 : une ouverture ne lit les en-têtes de chaque onglet qu\'une fois');
  const clE = fabriquerHT();
  clE.feuilles.push(new Feuille('Notes', [['Une note'], ['à côté']]));
  const cE = chargerServeur(clE, {});
  cE.enregistrerInstantaneHebdo();
  vm.runInContext('var __lecturesEntetes = 0; var __aDesEntetesLus = aDesEntetesLus; aDesEntetesLus = function (f) { __lecturesEntetes++; return __aDesEntetesLus(f); };', cE);
  const pqE = cE.getDonneesPourClient('HDK');
  const nE = vm.runInContext('__lecturesEntetes', cE);
  verifier('les premières lignes de chaque onglet lues une fois par ouverture (elles l\'étaient cinq fois)',
    pqE.ok && nE > 0 && nE <= clE.getSheets().filter(f => !f.isSheetHidden()).length, String(nE));
  vm.runInContext('__lecturesEntetes = 0', cE);
  cE.listerContrats(clE); cE.listerContrats(clE);
  verifier('hors d\'une ouverture, rien n\'est gardé : la liste des contrats relit ce qu\'elle doit',
    vm.runInContext('__lecturesEntetes', cE) >= 4 && vm.runInContext('MEMO_ENTETES', cE) === null);

  // =================================================================
  section('Débrief 18 : les consultations, comptées sans nom ni adresse');
  const cS18 = chargerServeur(fabriquerHT(), {});
  cS18.__cleLecteur = 'cle-temporaire-A'; cS18.noterConsultation(); cS18.noterConsultation();
  cS18.__cleLecteur = 'cle-temporaire-B'; cS18.noterConsultation();
  cS18.__cleLecteur = ''; cS18.noterConsultation();
  const diagS18 = cS18.diagnostic();
  verifier('le Diagnostic dit, semaine par semaine, combien d\'ouvertures et de personnes différentes',
    /✓ Consultations de la page \(sans nom ni adresse\) : S\d+ : 4 ouvertures, 2 personnes/.test(diagS18),
    (diagS18.match(/[^\n]*Consultations[^\n]*/) || [''])[0]);
  verifier('rien de ce qui est gardé ne nomme quelqu\'un : ni adresse, ni clé de Google en clair',
    !/cle-temporaire|@/.test(cS18.__proprietes.SUIVI_FWD_CONSULTATIONS || ''), cS18.__proprietes.SUIVI_FWD_CONSULTATIONS);
  cS18.__proprietes.SUIVI_FWD_CONSULTATIONS = JSON.stringify({ '2026-S01': { n: 5, k: ['a', 'b', 'c'] } });
  cS18.noterConsultation();
  const gardees = JSON.parse(cS18.__proprietes.SUIVI_FWD_CONSULTATIONS);
  verifier('une semaine finie ne garde que ses nombres : 5 ouvertures, 3 personnes, plus aucune empreinte',
    gardees['2026-S01'].n === 5 && gardees['2026-S01'].p === 3 && !('k' in gardees['2026-S01']) &&
    /S1 : 5 ouvertures, 3 personnes/.test(cS18.diagnostic()), JSON.stringify(gardees));
  const vieilles = {};
  for (let w = 1; w <= 20; w++) vieilles['2025-S' + String(w).padStart(2, '0')] = { n: 1, p: 1 };
  cS18.__proprietes.SUIVI_FWD_CONSULTATIONS = JSON.stringify(vieilles);
  cS18.noterConsultation();
  verifier('douze semaines au plus', Object.keys(JSON.parse(cS18.__proprietes.SUIVI_FWD_CONSULTATIONS)).length === 12);
  vm.runInContext('LockService = { getDocumentLock: function () { return { tryLock: function () { return false; }, releaseLock: function () {} }; } }', cS18);
  verifier('verrou pris ailleurs : l\'ouverture n\'est pas comptée, et rien ne casse', cS18.noterConsultation() === false);

  // =================================================================
  /* La chasse aux bugs du serveur (débrief 20) : chaque cas rejoue le geste
     qui faisait la panne, sur le vrai Code.gs. */
  section('Débrief 20 : l\'historique protégé, le Diagnostic juste, le serveur fermé à la page');
  const semaineIl = (c, jours) => c.numeroSemaineISO(new Date(Date.now() - jours * 864e5));
  const dite20 = s => 'S' + parseInt(s.slice(6), 10);
  /* La colonne suivie de HDK (bloc HDK AA 011) et ses lignes de plans : on
     y fabrique l'export d'une semaine plus ancienne, avec moins de validés. */
  const exportsDe = (cl, onglet) => {
    const f = cl.getSheetByName(onglet);
    const col = f.valeurs[0].indexOf('HDK AA 011') + 3;
    const lignes = f.valeurs.filter(l => /^UD-/.test(l[1] || ''));
    const duJour = lignes.map(l => l[col]);
    const plusAncien = duJour.slice();
    let n = 0;
    plusAncien.forEach((v, i) => { if (v === '100%' && n < 5) { plusAncien[i] = 'EMPTY'; n++; } });
    return { poser: valeurs => lignes.forEach((l, i) => { l[col] = valeurs[i]; }), duJour, plusAncien };
  };
  const verrouRefuse = c => vm.runInContext('LockService = { getDocumentLock: function () { return { tryLock: function () { __prises++; return false; }, releaseLock: function () {} }; } }', c);
  const verrouAccorde = c => vm.runInContext('LockService = { getDocumentLock: function () { return { tryLock: function () { __prises++; return true; }, releaseLock: function () {} }; } }', c);

  /* R — S38 archivé (5 validés de moins), S39 archivé ; lundi S40, l'export
     de S38 est rattrapé dans l'onglet et laissé là. Le vendredi, S40 n'a pas
     encore de relevé : l'archiver ferait « reculer » les cinq plans. */
  {
    const cl = fabriquerHT(), c = chargerServeur(cl, {});
    const s38 = semaineIl(c, 14), s39 = semaineIl(c, 7), s40 = semaineIl(c, 0);
    const e = exportsDe(cl, 'HDK');
    e.poser(e.plusAncien); c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, s38);
    e.poser(e.duJour);     c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, s39);
    e.poser(e.plusAncien);   // l'export de S38, rattrapé, resté dans l'onglet
    const avant = JSON.stringify(c.getHistorique(cl, 'HDK').map(r => [r.semaine, r.termine]));
    let refus = '';
    try { c.enregistrerInstantaneHebdo(); } catch (err) { refus = String(err.message || err); }
    verifier('R — l\'export d\'une semaine passée laissé dans l\'onglet, la semaine en cours sans relevé : refusé, avec le bon geste',
      new RegExp('« HDK » : l\'onglet « HDK » porte le même export que le relevé ' + dite20(s38) + ', alors que le relevé ' + dite20(s39) +
        ', plus récent, est différent : archivé comme relevé ' + dite20(s40) + ', il ferait reculer les plans qui ont bougé depuis\\. ' +
        'Importer l\'export du jour \\(menu Suivi FWD → Importer les exports GATES et SEE…, qui archive dans la foulée\\), ou le recoller puis archiver\\.').test(refus) &&
      JSON.stringify(c.getHistorique(cl, 'HDK').map(r => [r.semaine, r.termine])) === avant &&
      c.getHistorique(cl, 'THS').map(r => r.semaine).join() === s40, refus);
    const parImport = c.importArchiverReleve(c.ouvrirJetonImport_(), 'HDK');
    verifier('R — même refus par la fenêtre d\'import (« Relevé S40 non archivé : l\'onglet « HDK » porte le même export… »), rien d\'écrit',
      parImport.ok === false && parImport.ancienExport === true &&
      /^l'onglet « HDK » porte le même export que le relevé S\d+, alors que le relevé S\d+, plus récent, est différent/.test(parImport.message) &&
      JSON.stringify(c.getHistorique(cl, 'HDK').map(r => [r.semaine, r.termine])) === avant, JSON.stringify(parImport));
    e.poser(e.duJour);
    const r = c.enregistrerInstantaneHebdo();
    verifier('R — l\'export du jour remis : la semaine en cours s\'archive',
      r.ok && c.getHistorique(cl, 'HDK').map(x => x.semaine).join() === [s38, s39, s40].join(), JSON.stringify(c.getHistorique(cl, 'HDK').map(x => x.semaine)));
  }
  {
    /* Une semaine calme — S38 = S39 = S40, rien n'a bougé — reste acceptée. */
    const cl = fabriquerHT(), c = chargerServeur(cl, {});
    const s38 = semaineIl(c, 14), s39 = semaineIl(c, 7);
    c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, s38);
    c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, s39);
    let refus = '';
    try { c.enregistrerInstantaneHebdo(); } catch (err) { refus = String(err.message || err); }
    verifier('R — une semaine calme (S38 = S39 = S40) s\'archive sans refus',
      !refus && c.getHistorique(cl, 'HDK').length === 3, refus);
  }

  /* S — « Supprimer le relevé de cette semaine » demande d'abord, en ne
     nommant que les contrats qui en ont un ; NON ne touche à rien. */
  {
    const cl = fabriquerHT(), c = chargerServeur(cl, {});
    const s40 = semaineIl(c, 0);
    c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, semaineIl(c, 7));
    c.archiverContrat_(cl, { id: 'HDK', nom: 'HDK' }, s40);
    const avant = JSON.stringify(c.getHistorique(cl, 'HDK').map(r => r.semaine));
    c.__confirmations.push('NO');
    const a0 = c.__alertes.length;
    const rNon = c.supprimerDernierReleve();
    const question = c.__alertes[a0] || '';
    verifier('S — la question vient d\'abord, OUI / NON, et ne nomme que HDK (THS n\'a pas de relevé cette semaine)',
      new RegExp('^Supprimer le relevé ' + dite20(s40) + ' de « HDK » \\?\\n\\nLa ligne ' + dite20(s40) + ' de son historique est retirée ; les semaines d\'avant ne bougent pas\\.$').test(question) &&
      !/THS/.test(question), question);
    verifier('S — « Non » : rien n\'est retiré, et rien d\'autre n\'est dit',
      rNon === null && c.__alertes.length === a0 + 1 && JSON.stringify(c.getHistorique(cl, 'HDK').map(r => r.semaine)) === avant);
    c.__confirmations.push('YES');
    const rOui = c.supprimerDernierReleve();
    verifier('S — « Oui » : la semaine en cours est retirée de HDK seulement, la semaine d\'avant reste',
      rOui && rOui.supprimes.join() === 'HDK' && rOui.sans.join() === 'THS' &&
      c.getHistorique(cl, 'HDK').map(r => r.semaine).join() === semaineIl(c, 7), JSON.stringify(rOui));
    /* Sans relevé cette semaine nulle part : rien à demander. */
    const a1 = c.__alertes.length;
    const rRien = c.supprimerDernierReleve();
    verifier('S — sans relevé cette semaine : pas de question, « Aucun relevé pour la semaine en cours »',
      rRien.supprimes.length === 0 && c.__alertes.length === a1 + 1 && /^Aucun relevé pour la semaine en cours/.test(c.__alertes[a1]));
  }

  /* T — l'ancien onglet « Historique_FWD » d'un classeur à contrat unique, et
     un second contrat ajouté : l'historique ne disparaît plus sans un mot, et
     le vendredi n'ouvre pas « Historique_FWD_HDK » à côté. */
  {
    const gH = feuilleGates(40), gT = feuilleGates(30);
    const c0 = chargerServeur(new Classeur([]), {});
    const ligne = (s, t) => [s, new Date(), 40, t, 40 - t, 0, 0, '{}', '{}'];
    const legacy = new Feuille('Historique_FWD', [ENTETES_H.slice(), ligne(semaineIl(c0, 14), 3), ligne(semaineIl(c0, 7), 6)], true);
    const cl = new Classeur([new Feuille('HDK', gH.valeurs, false, gH.fusions), legacy], 'Ancien classeur');
    const c = chargerServeur(cl, {});
    verifier('T — un seul contrat : l\'ancien onglet est son historique, sans avis',
      c.getDonneesPourClient('HDK').releves.length === 2 && !c.getDonneesPourClient('HDK').avis);
    cl.feuilles.push(new Feuille('THS', gT.valeurs, false, gT.fusions));
    const avis = c.getDonneesPourClient('HDK').avis;
    verifier('T — un second contrat : la page dit que l\'ancien onglet n\'est plus rattaché, et comment le renommer',
      /L'ancien onglet d'historique « Historique_FWD » \(2 relevés\) n'est rattaché à aucun contrat — il servait quand le classeur n'en avait qu'un\. S'il est celui de « HDK », le renommer « Historique_FWD_HDK » lui rend ses relevés/.test(avis), avis);
    let refus = '';
    try { c.enregistrerInstantaneHebdo(); } catch (err) { refus = String(err.message || err); }
    verifier('T — l\'archivage refuse au lieu de couper l\'historique en deux : pas de « Historique_FWD_HDK » ouvert à côté',
      /« HDK » : l'ancien onglet d'historique « Historique_FWD » n'est rattaché à aucun contrat depuis que le classeur en a plusieurs\. S'il est celui de « HDK », le renommer « Historique_FWD_HDK »/.test(refus) &&
      !cl.getSheetByName('Historique_FWD_HDK') && !cl.getSheetByName('Historique_FWD_THS') && legacy.valeurs.length === 3, refus);
    const diag = c.diagnostic();
    verifier('T — le Diagnostic le dit aussi',
      /⚠ L'ancien onglet « Historique_FWD » n'est rattaché à aucun contrat \(2 relevés\) :/.test(diag), diag.split('\n').filter(l => /Historique_FWD/.test(l)).join(' / '));
    legacy.setName('Historique_FWD_HDK');
    const rT = c.enregistrerInstantaneHebdo();
    verifier('T — renommé « Historique_FWD_HDK » : HDK retrouve ses relevés, les deux contrats s\'archivent',
      rT.ok && !c.getDonneesPourClient('HDK').avis && c.getHistorique(cl, 'HDK').length === 3 && c.getHistorique(cl, 'THS').length === 1,
      c.getDonneesPourClient('HDK').avis);
  }

  /* U — le Diagnostic mesure le contrat que la page ouvre vraiment, et un
     onglet d'en-têtes seuls n'a pas de ✓. */
  {
    const gTete = feuilleGates(3), gT = feuilleGates(30);
    const cl = new Classeur([new Feuille('HDK', gTete.valeurs.slice(0, 3), false, gTete.fusions),
                             new Feuille('THS', gT.valeurs, false, gT.fusions)]);
    const c = chargerServeur(cl, {});
    const diag = c.diagnostic();
    const partHDK = diag.slice(diag.indexOf('— Contrat « HDK » —'), diag.indexOf('— Contrat « THS » —'));
    verifier('U — un onglet d\'en-têtes seuls : ⚠ « ne porte aucun plan », pas de ✓, et rien ne l\'envoie archiver',
      /⚠ L'onglet ne porte aucun plan \(en-têtes seuls\) : y importer l'export GATES \(menu Suivi FWD → Importer les exports GATES et SEE…\) ou le coller en A1\./.test(partHDK) &&
      !/✓ \d+ colonnes, 0 plans/.test(partHDK) && !/Archiver le relevé/.test(partHDK), partHDK);
    verifier('U — le paquet mesuré est celui que la page ouvre : THS, le premier qui porte des plans',
      /✓ Paquet envoyé à la page : \d+ Ko \(contrat « THS », le premier qui porte des plans ; les autres se chargent à la demande\)/.test(diag) &&
      c.getDonneesPourClient().contrat === 'THS', (diag.match(/[^\n]*Paquet envoyé[^\n]*/) || [''])[0]);
  }

  /* V — l'ancienneté archivée lit les dates telles qu'une feuille française
     les montre (« 16/07/2020 ») : plus aucun plan daté dans « — ». */
  {
    const g = feuilleGates(186);
    const cl = new Classeur([new Feuille('HDK', g.valeurs, false, g.fusions)]);
    const c = chargerServeur(cl, {});
    const compte = c.compterAvancements('HDK');
    const anc = compte.groupes._anciennete || {};
    const totalAnc = Object.keys(anc).reduce((s, k) => s + anc[k].total, 0);
    verifier('V — relevé de l\'export GATES (dates « JJ/MM/AAAA ») : aucun plan daté dans « — », tous rangés par ancienneté',
      !!c.construireModele('HDK').cleDate && !anc['—'] && totalAnc === compte.total && Object.keys(anc).length >= 1, JSON.stringify(anc));
    const am = (v, md) => JSON.stringify(c.anneeEtMois(v, md));
    verifier('V — même règle que la page : jour d\'abord, ISO, mois/jour quand la colonne l\'est, l\'illisible écarté',
      am('16/07/2020') === '{"annee":2020,"mois":7}' && am('2020-07-16 10:42') === '{"annee":2020,"mois":7}' &&
      am('03/04/2020') === '{"annee":2020,"mois":4}' && am('03/04/2020', true) === '{"annee":2020,"mois":3}' &&
      am('07/16/2020') === '{"annee":2020,"mois":7}' && am('16.07.20') === '{"annee":2020,"mois":7}' &&
      am('31/13/2020') === 'null' && am('') === 'null' && am('à préciser') === 'null');
  }

  /* LOCK — les gestes qui écrivent l'historique passent un à un : le verrou
     du document, pris une fois par geste ; refusé, rien n'est écrit, et on
     le dit. */
  {
    const cl = fabriquerHT(), c = chargerServeur(cl, {});
    vm.runInContext('var __prises = 0;', c);
    const prises = () => vm.runInContext('__prises', c);
    verrouAccorde(c);
    c.enregistrerInstantaneHebdo();
    const p1 = prises();
    c.importArchiverReleve(c.ouvrirJetonImport_(), 'HDK');
    const p2 = prises();
    verifier('LOCK — l\'archivage (deux contrats) prend le verrou une seule fois, l\'import aussi : pas de verrou dans le verrou',
      p1 === 1 && p2 === 2, p1 + ' / ' + p2);
    const histo = () => JSON.stringify([c.getHistorique(cl, 'HDK'), c.getHistorique(cl, 'THS')].map(h => h.map(r => [r.semaine, r.total])));
    const avant = histo();
    verrouRefuse(c);
    const MOT_VERROU = /un autre geste écrit en ce moment dans l'historique de ce classeur \(l'archivage du vendredi, un import ou le menu, lancé au même moment\) : l'historique n'est pas touché\. Relancer dans une minute\./;
    let refusHebdo = '';
    try { c.enregistrerInstantaneHebdo(); } catch (err) { refusHebdo = String(err.message || err); }
    verifier('LOCK — verrou pris ailleurs : l\'archivage de la semaine le dit (« Relevé S40 non archivé : … »)',
      /^Relevé S\d+ non archivé : /.test(refusHebdo) && MOT_VERROU.test(refusHebdo), refusHebdo);
    const parImport = c.importArchiverReleve(c.ouvrirJetonImport_(), 'HDK');
    verifier('LOCK — par la fenêtre d\'import : refus rendu tel quel, l\'import reste fait',
      parImport.ok === false && MOT_VERROU.test(parImport.message), JSON.stringify(parImport));
    cl.setActiveSheet(cl.getSheetByName('HDK'));
    const passee = c.archiverPourSemaine_(cl, 'HDK', dite20(semaineIl(c, 7)));
    verifier('LOCK — une semaine passée : « Relevé S39 non archivé : un autre geste… »',
      passee.ok === false && /^Relevé S\d+ non archivé : un autre geste/.test(passee.message), passee.message);
    c.__confirmations.push('YES');
    const a0 = c.__alertes.length;
    const sup = c.supprimerDernierReleve();
    verifier('LOCK — la suppression : « Relevé S40 non supprimé : un autre geste… », rien de retiré',
      sup === null && /^Relevé S\d+ non supprimé : un autre geste/.test(c.__alertes[c.__alertes.length - 1]) && c.__alertes.length === a0 + 2,
      c.__alertes.slice(a0).join(' | '));
    verifier('LOCK — et l\'historique n\'a pas bougé', histo() === avant);
  }

  /* PRIV — la page, ouverte par toute l'organisation, atteint par
     google.script.run toute fonction dont le nom ne finit pas par « _ ».
     Celles qu'elle n'appelle pas, et qui écrivent ou ne servent qu'au
     Diagnostic, sont privées ; celles que la page, la fenêtre d'import, le
     menu et le déclencheur appellent restent publiques. */
  {
    const c = chargerServeur(fabriquerHT(), {});
    const privees = ['marquerDonneesModifiees', 'resumeConsultations', 'archiverContrat', 'archiverPourSemaine', 'deposer'];
    verifier('PRIV — ' + privees.join(', ') + ' : hors de portée de la page (suffixe « _ »)',
      privees.every(n => typeof c[n] === 'undefined' && typeof c[n + '_'] === 'function'),
      privees.filter(n => typeof c[n] !== 'undefined').join(', '));
    const source = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
    const fenetre = [];
    source.replace(/appeler(?:AvecReprise)?\('([A-Za-z_]+)'/g, (m, n) => { fenetre.push(n); return m; });
    const modele = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
    const page = ['getDonneesCompactes', 'noterConsultation'].filter(n => modele.indexOf('.' + n + '(') !== -1);
    c.onOpen();
    const publiques = fenetre.concat(page, c.__menu, ['enregistrerInstantaneHebdo', 'doGet', 'doPost', 'onOpen', 'onEdit']);
    verifier('PRIV — ce que la page, la fenêtre d\'import, le menu et le déclencheur appellent reste public',
      fenetre.length >= 7 && page.length === 2 && publiques.every(n => !/_$/.test(n) && typeof c[n] === 'function'),
      publiques.filter(n => /_$/.test(n) || typeof c[n] !== 'function').join(', ') || fenetre.join(', '));
  }

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

  /* Une seconde base par contrat : l'onglet « SEE X1 » sert au contrat X1,
     « SEE - X2 » au contrat X2 — écrits comme on veut, tirets, casse. Aucun
     n'est un contrat. Un « SEE » tout court devant plusieurs contrats
     n'appartient à personne : pas de comparaison plutôt qu'une fausse. */
  const seeDe = (nom, lignes) => new Feuille(nom, [['Nommage WD BFLOW', '', '', ''], ['', '', '', ''],
    ['NAME', 'SOL.', 'Cust.V', 'Validated']].concat(lignes));
  const parContrat = construire({ contrats: ['X1', 'X2'], lignes: 20, historique: false, sortie: 'apercu-see-contrats.html',
    feuilles: [seeDe('SEE X1', [['AAA111A0001', '1', 'a', 'TRUE']]),
               seeDe('see - x2', [['BBB222A0002', '1', 'b', 'TRUE'], ['BBB222A0003', '1', 'b', 'FALSE']])] });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-contrats.html'));
  const rX1 = parContrat.contexte.getDonneesPourClient('X1').rapprochement;
  const rX2 = parContrat.contexte.getDonneesPourClient('X2').rapprochement;
  verifier('chaque contrat lit sa propre base : « SEE X1 » pour X1, « see - x2 » pour X2',
    !!rX1 && !!rX2 && rX1.lignes.length === 1 && rX1.lignes[0].NAME === 'AAA111A0001' &&
    rX2.lignes.length === 2 && rX2.lignes[0].NAME === 'BBB222A0002', JSON.stringify([rX1 && rX1.lignes, rX2 && rX2.lignes.length]));
  verifier('et ces onglets ne sont pas des contrats',
    parContrat.contexte.listerContrats(parContrat.classeur).map(c => c.id).join() === 'X1,X2');
  const diagContrats = parContrat.contexte.diagnostic();
  verifier('le diagnostic dit, contrat par contrat, quel onglet est lu',
    /✓ Seconde base « SEE » de « X1 » : onglet « SEE X1 », 1 ligne\(s\)/.test(diagContrats) &&
    /✓ Seconde base « SEE » de « X2 » : onglet « see - x2 », 2 ligne\(s\)/.test(diagContrats), diagContrats);
  const generique = construire({ contrats: ['X1', 'X2'], lignes: 20, historique: false, sortie: 'apercu-see-generique.html',
    feuilles: [seeDe('SEE', [['AAA111A0001', '1', 'a', 'TRUE']])] });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-see-generique.html'));
  const diagGen = generique.contexte.diagnostic();
  verifier('un « SEE » tout court devant deux contrats n\'est lu pour aucun, et le diagnostic dit comment le renommer',
    !generique.contexte.getDonneesPourClient('X1').rapprochement && !generique.contexte.getDonneesPourClient('X2').rapprochement &&
    /aucun onglet « SEE X1 »/.test(diagGen) && /⚠ L'onglet « SEE » ne dit pas à quel contrat il appartient/.test(diagGen) &&
    /le renommer « SEE X1 »/.test(diagGen), diagGen);
  /* Le diagnostic dit ce que le script voit de la seconde base — c'est la
     réponse à « je ne vois pas les deux cercles » : l'onglet lu et compté,
     l'onglet absent (et le geste qui manque), l'onglet vide, l'onglet dont
     l'en-tête ne porte pas la référence (et les en-têtes lus). */
  const diagSEE = seeParNom.contexte.diagnostic();
  verifier('le diagnostic compte la seconde base : onglet, lignes, référence, ligne d\'en-têtes',
    /✓ Seconde base « SEE » : onglet « SEE », 2 ligne\(s\), référence NAME \+ SOL\. \+ Cust\.V \(ligne d'en-têtes : 3\)/.test(diagSEE), diagSEE);
  const diagSans = ctxPaquet.diagnostic();
  verifier('sans onglet SEE, le diagnostic le dit, et dit le geste : le menu d\'import, ou un onglet « SEE », l\'extract en A1, ses colonnes',
    /– Seconde base « SEE » : aucun onglet « SEE » — pas de rapprochement\./.test(diagSans) &&
    /→ menu Suivi FWD → Importer les exports GATES et SEE…, sans ouvrir le fichier dans Excel ; ou un onglet nommé « SEE », l'extract collé en A1 tel quel, avec ses colonnes NAME, SOL\., Cust\.V\./.test(diagSans) &&
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
     (doPost → deposer_). Refusé tant que la configuration n'a pas de secret,
     refusé sans le bon secret, refusé vers un onglet d'historique ; sinon
     l'onglet est vidé et réécrit, et le relevé de la semaine archivé pour ce
     contrat si on le demande. */
  section('Dépôt automatique (doPost)');
  const depotFerme = construire({ lignes: 12, historique: false, sortie: 'apercu-depot.html' });
  const cD = depotFerme.contexte;
  const envoi = (ctx, corps) => ctx.deposer_(typeof corps === 'string' ? corps : JSON.stringify(corps));
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
    /Trop de lignes : 1 \(au plus 0\)/.test(ferme.contexte.deposer_(JSON.stringify({ secret: S, onglet: 'Données', lignes: [['a']] })).message),
    ferme.contexte.deposer_(JSON.stringify({ secret: S, onglet: 'Données', lignes: [['a']] })).message);
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
    pVide.ok === false && /« Données » est vide — menu Suivi FWD → Importer les exports GATES et SEE…, ou coller l'export GATES en A1/.test(pVide.message), pVide.message);
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
    /validés, \d+ en cours, \d+ à faire, \d+ non renseignés/.test(rapportOk));
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
    /Onglet de données : Aucun onglet de données exploitable dans ce classeur : « Données » est vide — menu Suivi FWD → Importer les exports GATES et SEE…, ou coller l'export GATES en A1/.test(dVide.contexte.diagnostic()),
    dVide.contexte.diagnostic());

  const dSansFWD = serveurSur([['Référence UD', 'Truc'], ['A-1', 'x']]);
  const rapportSansFWD = dSansFWD.contexte.diagnostic();
  verifier('l\'absence de colonne d\'avancement est signalée',
    /Aucune colonne d'avancement FWD/.test(rapportSansFWD));
  verifier('et la conséquence est expliquée',
    /tout sera « non renseigné »/.test(rapportSansFWD));
  /* Débrief 16 (confidentialité) : sans aucun intitulé d'export, la « ligne
     d'en-têtes » devinée peut être une ligne de plan — le diagnostic n'en
     recopie rien, et s'arrête là pour cet onglet. */
  const dSansIntitule = serveurSur([['A-1', 'Retard fournisseur, voir M. Dupont', 'x'], ['A-2', 'y', 'z']]);
  const rapportSansIntitule = dSansIntitule.contexte.diagnostic();
  verifier('une ligne d\'en-têtes introuvable : le diagnostic le dit, ne recopie aucune cellule, et dit le geste',
    /✗ Ligne d'en-têtes introuvable/.test(rapportSansIntitule) && !/Dupont|A-1/.test(rapportSansIntitule) && /réimporter l'export \(menu Suivi FWD → Importer les exports GATES et SEE…\), ou le recoller entier en A1/.test(rapportSansIntitule),
    rapportSansIntitule.split('\n').filter(l => /en-têtes|Dupont|A-1/.test(l)).join(' / '));
  /* Un onglet « Notes » à côté d'un vrai export n'est pas un contrat : l'onglet
     « SEE » et le contrat unique restent ce qu'ils sont. */
  const clNotes = new Classeur([new Feuille('HDK', feuilleExemple(10)), new Feuille('Notes', [['réunion du 24/09 : relancer le BE']])]);
  const cNotes = chargerServeur(clNotes, {});
  verifier('un onglet « Notes » à côté de l\'export n\'est pas un contrat — et le diagnostic dit qu\'il est écarté',
    cNotes.listerContrats(clNotes).map(c => c.id).join() === 'HDK' && /Onglet « Notes » écarté/.test(cNotes.diagnostic()) &&
    !/relancer le BE/.test(cNotes.diagnostic()), cNotes.listerContrats(clNotes).map(c => c.id).join());
  /* Un export collé par-dessus l'ancien : des références répétées. Le
     diagnostic les compte, la carte archivée garde la première ligne. */
  const fDoubles = feuilleExemple(10);
  fDoubles.push(fDoubles[5].slice(), fDoubles[6].slice());
  const cDoubles = serveurSur(fDoubles);
  const diagDoubles = cDoubles.contexte.diagnostic();
  cDoubles.contexte.enregistrerInstantaneHebdo();
  const carteDoubles = cDoubles.contexte.getHistorique(cDoubles.classeur)[0].plans;
  verifier('des références en double : « ⚠ 2 ligne(s) répètent une référence déjà vue », et la carte garde la première ligne',
    /⚠ 2 ligne\(s\) répètent une référence déjà vue/.test(diagDoubles) && Object.keys(carteDoubles).length === 10,
    diagDoubles.split('\n').filter(l => /répètent/.test(l)).join(' / ') + ' | carte ' + Object.keys(carteDoubles).length);
  /* Un onglet de contrat renommé après un archivage : son historique porte
     l'ancien nom. Le diagnostic le trouve et dit le geste (débrief 16). */
  const fRenomme = new Feuille('Feuille 1', feuilleExemple(10));
  const clRenomme = new Classeur([fRenomme]);
  const cRenomme = chargerServeur(clRenomme, {});
  cRenomme.enregistrerInstantaneHebdo();
  fRenomme.nom = 'HDK';
  const diagRenomme16 = cRenomme.diagnostic();
  verifier('un onglet renommé : son ancien historique est signalé, avec le geste — « Historique_FWD_Feuille 1 » (1 relevé)',
    /⚠ L'onglet d'historique « Historique_FWD_Feuille 1 » \(1 relevé\) n'est rattaché à aucun contrat/.test(diagRenomme16) &&
    /Historique_FWD_<nom du contrat>/.test(diagRenomme16), diagRenomme16.split('\n').filter(l => /Historique_FWD/.test(l)).join(' / '));

  /* Débrief 17 : ce même onglet renommé, vu de la page et de l'archivage. La
     page le dit au-dessus de la barre ; l'archivage suivant, qui ouvrirait un
     second historique à côté, est refusé tant que l'ancien n'est pas renommé. */
  const paquetRenomme17 = cRenomme.getDonneesPourClient();
  verifier('débrief 17 — la page reçoit l’avis de l’historique orphelin, avec le nom à lui donner',
    /« Historique_FWD_Feuille 1 » \(1 relevé\) n'est rattaché à aucun contrat/.test(paquetRenomme17.avis) &&
    /le renommer « Historique_FWD_HDK »/.test(paquetRenomme17.avis) && paquetRenomme17.plans.length === 10, paquetRenomme17.avis);
  let refusRenomme17 = '';
  try { cRenomme.enregistrerInstantaneHebdo(); } catch (e) { refusRenomme17 = e.message; }
  verifier('… et l’archivage qui couperait l’historique en deux est refusé, avec le geste',
    /« HDK » : l'onglet d'historique « Historique_FWD_Feuille 1 » n'est rattaché à aucun contrat\. S'il est celui de « HDK », le renommer « Historique_FWD_HDK »/.test(refusRenomme17) &&
    !clRenomme.getSheetByName('Historique_FWD_HDK'), refusRenomme17);
  clRenomme.getSheetByName('Historique_FWD_Feuille 1').nom = 'Historique_FWD_HDK';
  cRenomme.enregistrerInstantaneHebdo();
  verifier('une fois renommé : plus d’avis, l’archivage passe et retrouve son relevé',
    !cRenomme.getDonneesPourClient().avis && cRenomme.getHistorique(clRenomme, 'HDK').length === 1);

  /* Un historique dont l'onglet existe encore n'est pas orphelin : un contrat
     masqué, une « Copie de HDK » archivée par une livraison d'avant. */
  const fMasque17 = new Feuille('THS', feuilleExemple(10));
  const clMasque17 = new Classeur([new Feuille('HDK', feuilleExemple(10)), fMasque17,
                                   new Feuille('Copie de HDK', feuilleExemple(10))]);
  const cMasque17 = chargerServeur(clMasque17, {});
  cMasque17.enregistrerInstantaneHebdo();
  clMasque17.insertSheet('Historique_FWD_Copie de HDK').valeurs.push(['Semaine'], ['2026-S39']);
  fMasque17.cachee = true;
  fMasque17.isSheetHidden = function () { return true; };
  clMasque17.feuilles.push(new Feuille('VRK', feuilleExemple(10)));
  let refusMasque17 = '';
  try { cMasque17.enregistrerInstantaneHebdo(); } catch (e) { refusMasque17 = e.message; }
  verifier('débrief 17 — un contrat masqué, une « Copie de HDK » écartée : leurs historiques ne sont pas « orphelins », aucun avis, un nouveau contrat s’archive',
    !cMasque17.getDonneesPourClient().avis && !refusMasque17 && !!clMasque17.getSheetByName('Historique_FWD_VRK') &&
    !/n'est rattaché à aucun contrat/.test(cMasque17.diagnostic()), (cMasque17.getDonneesPourClient().avis || '') + ' | ' + refusMasque17);
  /* Une copie seule dans le classeur reste le contrat. */
  const clCopieSeule17 = new Classeur([new Feuille('Copie de HDK', feuilleExemple(10))]);
  verifier('… et une « Copie de HDK » seule dans le classeur reste le contrat',
    chargerServeur(clCopieSeule17, {}).listerContrats(clCopieSeule17).map(c => c.id).join() === 'Copie de HDK');

  /* Des doublons comptés pareil partout : le relevé compte les références,
     une fois chacune, comme la carte et comme la page. */
  verifier('… et le Diagnostic compte pareil : « 10 plans (12 lignes) »',
    /✓ 11 colonnes, 10 plans \(12 lignes\)/.test(diagDoubles) && /Seule la première ligne de chaque référence compte/.test(diagDoubles),
    diagDoubles.split('\n').filter(l => /plans|première ligne/.test(l)).join(' / '));
  verifier('débrief 17 — des références en double ne comptent qu’une fois dans le relevé (10 plans, pas 12)',
    cDoubles.contexte.getHistorique(cDoubles.classeur)[0].total === 10, String(cDoubles.contexte.getHistorique(cDoubles.classeur)[0].total));

  /* Un onglet d'en-têtes seuls : pas de relevé à zéro plan, et la page s'ouvre
     sur le premier contrat qui a des plans. */
  const enTetesSeuls17 = feuilleExemple(1).slice(0, 4);
  const clVideTete17 = new Classeur([new Feuille('THS', enTetesSeuls17), new Feuille('HDK', feuilleExemple(10))]);
  const cVideTete17 = chargerServeur(clVideTete17, {});
  const pOuverture17 = cVideTete17.getDonneesPourClient();
  const pThs17 = cVideTete17.getDonneesPourClient('THS');
  verifier('débrief 17 — un onglet d’en-têtes seuls en tête : la page s’ouvre sur HDK, pas sur « 0 sur 0 »',
    pOuverture17.contrat === 'HDK' && pOuverture17.plans.length === 10, pOuverture17.contrat);
  verifier('… et demandé, il dit « ne porte aucun plan (en-têtes seuls) »',
    /L'onglet « THS » ne porte aucun plan \(en-têtes seuls\)/.test(pThs17.message), pThs17.message);
  let refusSansPlan17 = '';
  try { cVideTete17.enregistrerInstantaneHebdo(); } catch (e) { refusSansPlan17 = e.message; }
  const confirmation17 = (cVideTete17.__alertes || []).join(' ');
  verifier('… l’archivage ne lui fabrique pas un relevé à zéro plan, archive HDK, et le vendredi n’échoue pas pour autant',
    !refusSansPlan17 && /Relevé S\d+ archivé : HDK \(10 plans\)\..* Non archivé\(s\), en-têtes seuls : THS\./.test(confirmation17) &&
    !clVideTete17.getSheetByName('Historique_FWD_THS'), refusSansPlan17 || confirmation17);
  /* Le même onglet, mais avec la ligne de service de l'export GATES sous ses
     en-têtes : pas de faux plan « ligne-1 ». */
  const gTete17 = require('./feuille-gates').feuilleGates(3);
  const clGatesTete17 = new Classeur([new Feuille('THS', gTete17.valeurs.slice(0, 3), false, gTete17.fusions),
                                      new Feuille('HDK', feuilleGates(12).valeurs, false, feuilleGates(12).fusions)]);
  const cGatesTete17 = chargerServeur(clGatesTete17, {});
  const pGatesTete17 = cGatesTete17.getDonneesPourClient('THS');
  verifier('… et avec la ligne de service de l’export sous les en-têtes : « aucun plan », pas un faux plan « ligne-1 »',
    pGatesTete17.plans.length === 0 && /ne porte aucun plan/.test(pGatesTete17.message) &&
    cGatesTete17.getDonneesPourClient().contrat === 'HDK', pGatesTete17.plans.length + ' / ' + pGatesTete17.message);

  /* La colonne suivie vidée d'une semaine à l'autre : refus, et la page le dit. */
  const fPleine17 = feuilleExemple(10);
  const clVidee17 = new Classeur([new Feuille('HDK', fPleine17)]);
  const cVidee17 = chargerServeur(clVidee17, {});
  cVidee17.enregistrerInstantaneHebdo();
  const colFwd1717 = fPleine17[3].indexOf('Avancement FWD');
  fPleine17.slice(4).forEach(l => { if (l[0]) l[colFwd1717] = ''; });
  let refusColonneVide17 = '';
  try { cVidee17.enregistrerInstantaneHebdo(); } catch (e) { refusColonneVide17 = e.message; }
  verifier('débrief 17 — une colonne suivie vidée alors que le relevé d’avant en avait : archivage refusé, avec la raison',
    /est vide sur les 10 plans de « HDK », alors que le relevé \d{4}-S\d{2} en avait des valeurs/.test(refusColonneVide17) &&
    cVidee17.getHistorique(clVidee17, 'HDK')[0].total - cVidee17.getHistorique(clVidee17, 'HDK')[0].vide > 0, refusColonneVide17);
  const clNeuf17 = new Classeur([new Feuille('HDK', feuilleExemple(10).map((l, i) => i >= 4 && l[0] ? l.map((v, j) => j === colFwd1717 ? '' : v) : l))]);
  const cNeuf17 = chargerServeur(clNeuf17, {});
  let refusNeuf17 = '';
  try { cNeuf17.enregistrerInstantaneHebdo(); } catch (e) { refusNeuf17 = e.message; }
  verifier('… mais un contrat qui démarre, sans relevé d’avant, s’archive', !refusNeuf17 && cNeuf17.getHistorique(clNeuf17, 'HDK').length === 1, refusNeuf17);

  /* Un tableau croisé et une copie d'onglet à côté de l'export : écartés. */
  const tcd17 = [['ATA', 'NBVAL de Référence UD'], ['24', '12'], ['25', '7']];
  const clTcd17 = new Classeur([new Feuille('Tableau croisé 1', tcd17), new Feuille('HDK', feuilleExemple(10)), new Feuille('Copie de HDK', feuilleExemple(10))]);
  const cTcd17 = chargerServeur(clTcd17, {});
  const diagTcd17 = cTcd17.diagnostic();
  verifier('débrief 17 — un tableau croisé (« ATA | NBVAL de Référence UD ») et une « Copie de HDK » ne sont pas des contrats',
    cTcd17.listerContrats(clTcd17).map(c => c.id).join() === 'HDK' && /Onglet « Tableau croisé 1 » écarté : pas de ligne d'en-têtes d'export/.test(diagTcd17) &&
    /Onglet « Copie de HDK » écarté : une copie d'onglet n'est pas un contrat/.test(diagTcd17), cTcd17.listerContrats(clTcd17).map(c => c.id).join());

  /* Un historique illisible n'emporte pas l'extract du jour. */
  const cPanneHisto17 = serveurSur(feuilleExemple(10));
  cPanneHisto17.contexte.enregistrerInstantaneHebdo();
  vm.runInContext('getHistorique = function () { throw new Error("Délai dépassé"); };', cPanneHisto17.contexte);
  const pPanneHisto17 = cPanneHisto17.contexte.getDonneesPourClient();
  verifier('débrief 17 — un historique illisible : l’extract du jour reste, et l’avis le dit',
    pPanneHisto17.ok && pPanneHisto17.plans.length === 10 && pPanneHisto17.releves.length === 0 &&
    /n'a pas pu être lu \(Délai dépassé\)/.test(pPanneHisto17.avis), pPanneHisto17.avis);

  /* Le fuseau du projet, et les relevés d'avant le 22 septembre. */
  const cFuseau17 = serveurSur(feuilleExemple(10));
  cFuseau17.contexte.Session = { getScriptTimeZone: function () { return 'America/Los_Angeles'; } };
  verifier('débrief 17 — un projet hors du fuseau de Paris est signalé',
    /⚠ Le projet Apps Script est réglé sur le fuseau « America\/Los_Angeles »/.test(cFuseau17.contexte.diagnostic()));
  const cBerlin17 = serveurSur(feuilleExemple(10));
  cBerlin17.contexte.Session = { getScriptTimeZone: function () { return 'Europe/Berlin'; } };
  cBerlin17.contexte.Utilities.formatDate = function () { return '+0200'; };
  verifier('… mais pas un fuseau à l’heure de Paris (Berlin, Bruxelles…)', !/fuseau/.test(cBerlin17.contexte.diagnostic()));
  const cAncien17 = serveurSur(feuilleExemple(10));
  cAncien17.contexte.enregistrerInstantaneHebdo();
  const hAncien17 = cAncien17.classeur.getSheetByName('Historique_FWD_Données');
  hAncien17.valeurs[1][1] = new Date(Date.UTC(2026, 8, 18));
  verifier('… et un relevé d’avant le 22 septembre (colonne devinée à l’époque) aussi',
    /⚠ Le relevé \d{4}-S\d{2} date du 2026-09-18 : avant le 22 septembre/.test(cAncien17.contexte.diagnostic()));

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
  /* Chercher un plan dans une section, sur les données du classeur : le
     champ du bloc par groupe trouve un plan comme un groupe. La référence est
     lue dans la première cellule du tableau, pas fabriquée. */
  const refReelle = await p.evaluate(() => document.querySelector('#corps-tableau tr td').textContent.trim());
  await p.fill('#filtre-groupe', refReelle); await p.waitForTimeout(450);
  const trouveReel = await p.evaluate(() => ({
    groupes: document.querySelectorAll('#zone-critique .critique-ligne').length,
    trouves: [...document.querySelectorAll('#zone-critique .groupe-refs.trouves .jeton-ud')].map(b => b.dataset.ud),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    global: !!document.getElementById('champ-plan')
  }));
  verifier('données réelles : le champ du bloc par groupe trouve un plan du classeur, sous son groupe, sans toucher au tableau',
    !trouveReel.global && trouveReel.groupes === 1 && trouveReel.trouves.length === 1 && trouveReel.trouves[0] === refReelle &&
    trouveReel.lignes === 186, JSON.stringify([refReelle, trouveReel]));
  await p.focus('#filtre-groupe'); await p.keyboard.press('Escape'); await p.waitForTimeout(350);
  verifier('le sélecteur de dimension propose les colonnes détectées', vu.dims.length >= 3, JSON.stringify(vu.dims));
  verifier('l\'ATA est ouvert par défaut', vu.dimActive === 'ata', vu.dimActive);
  verifier('le titre nomme la dimension', /par ATA/.test(vu.titre), vu.titre);
  verifier('le bloc par ATA est rempli', vu.groupes >= 2, String(vu.groupes));
  verifier('la somme des plans par groupe fait 186',
    vu.totauxGroupes.reduce((a, b) => a + b, 0) === 186, String(vu.totauxGroupes.reduce((a, b) => a + b, 0)));
  verifier('le graphique a de quoi tracer', vu.releves);
  verifier('le pied nomme le dernier relevé et compte les relevés, comme la note du graphique',
    /^Dernier relevé : S\d{1,2}\u00a0· \S+\u00a0\d{4} · \d+ relevés$/.test(vu.importe), vu.importe);
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
  /* Ici, on compte les lignes du tableau : toutes dessinées d'un coup. Le
     découpage en tranches a ses propres tests (« 640 plans… »). */
  await ctxGates.addInitScript(() => { window.SUIVI_FWD_BUDGET = 1e9; });
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
  /* Débrief 15 : « il ne faut pas qu'on se trompe de la source ». Le vrai
     Code.gs, sur la vraie structure d'export : la page nomme la colonne lue. */
  const colonneLue = await pg.evaluate(() => ({
    pied: document.getElementById('colonne-suivie').textContent,
    alerte: document.getElementById('alerte-source').hidden
  }));
  verifier('sur la vraie structure d’export, la page dit lire « HDK AA 011 › Avancement Définition Electrique », sans alerte',
    colonneLue.pied === 'Colonne suivie : HDK AA 011 \u203a Avancement Définition Electrique' && colonneLue.alerte, JSON.stringify(colonneLue));
  await pg.click('#choix-indicateur button[data-indicateur="concept"]'); await pg.waitForTimeout(600);
  const colonneConcept = await pg.evaluate(() => document.getElementById('colonne-suivie').textContent);
  await pg.click('#choix-indicateur button[data-indicateur="def"]'); await pg.waitForTimeout(600);
  verifier('et « HDK AA 011 › Avancement Concept Harnais » sous le concept harnais',
    colonneConcept === 'Colonne suivie : HDK AA 011 \u203a Avancement Concept Harnais', colonneConcept);
  /* Et si la colonne manque (un groupe renommé dans l'export) : la page le
     dit en haut, ne lit aucune autre colonne à la place, et le pied le redit. */
  construire({ gates: true, lignes: 40, historique: false, config: { COLONNE_FWD: 'HDK AA 11 > Avancement Définition Electrique' },
               sortie: 'apercu-colonne-absente.html' });
  const pAbs = await ctxGates.newPage();
  pAbs.on('pageerror', e => erreursJS.push('colonne absente : ' + e.message));
  await pAbs.goto('file://' + path.join(__dirname, '..', 'apercu-colonne-absente.html'));
  await pAbs.waitForTimeout(1500);
  const abs = await pAbs.evaluate(() => ({
    alerte: document.getElementById('alerte-source').hidden ? '' : document.getElementById('alerte-source').textContent,
    pied: document.getElementById('colonne-suivie').textContent,
    termines: [...document.querySelectorAll('#etats .etat-btn')].filter(b => /termin|valid/i.test(b.textContent)).length,
    phrase: document.getElementById('phrase').textContent.replace(/\s+/g, ' ')
  }));
  verifier('colonne introuvable : l’alerte la nomme en haut de la page, aucun plan n’est dit terminé, le pied dit « introuvable »',
    /Colonne « HDK AA 11 > Avancement Définition Electrique » introuvable/.test(abs.alerte) && abs.termines === 0 &&
    /^0 sur 40 plans/.test(abs.phrase) && /introuvable/.test(abs.pied), JSON.stringify(abs));
  await pAbs.close();
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-colonne-absente.html'));
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
  /* Une seule entorse à l'ordre de la feuille : la colonne suivie vient
     juste après la référence, figée avec elle. */
  const ordreAttendu = (() => {
    /* La colonne suivie, par sa clé : l'export répète « Avancement
       Définition Electrique » bloc après bloc. */
    const cols = mGates.colonnes.filter(c => c.titre !== 'Colonne 1');
    const suivie = cols.filter(c => c.cle === 'avancement')[0];
    const reste = cols.filter(c => c !== suivie);
    const iRef = reste.findIndex(c => c.titre === 'Référence UD');
    reste.splice(iRef + 1, 0, suivie);
    return reste.map(c => c.titre);
  })();
  verifier('et dans l\'ordre de la feuille, la colonne suivie juste après la référence, sans autre exception',
    JSON.stringify(vg.ordre) === JSON.stringify(ordreAttendu), (() => {
      const k = vg.ordre.findIndex((t, i) => t !== ordreAttendu[i]);
      return 'écart au rang ' + k + ' : ' + JSON.stringify(vg.ordre.slice(Math.max(0, k - 1), k + 2)) + ' / attendu ' + JSON.stringify(ordreAttendu.slice(Math.max(0, k - 1), k + 2));
    })());
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
      fin: (() => { const f = th.filter(t => t.classList.contains('col-fige')); return !!f.length && f[f.length - 1].classList.contains('fige-fin'); })(),
      corpsFigees: [...document.querySelectorAll('#corps-tableau tr:first-child td')]
        .filter(td => td.classList.contains('col-fige')).length,
      groupesFiges: [...document.querySelectorAll('.groupes th.col-fige')]
        .map(t => ({ debut: +t.dataset.debut, span: t.colSpan, gauche: parseFloat(t.style.left) }))
    };
  });
  verifier('le bloc figé couvre tout ce qui précède la référence, elle comprise, et la colonne suivie',
    fige.figees.length === fige.rang + 2 && fige.figees[fige.rang] === 'Référence UD' && fige.figees[fige.rang + 1] === 'Avancement Définition Electrique',
    JSON.stringify(fige.figees));
  verifier('la référence ouvre le tableau, l\'avancement la suit : les deux seules colonnes figées',
    fige.rang === 0 && fige.figees.length === 2, JSON.stringify(fige.figees));
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
     sans périmètre, reste l'échéance tant qu'il est à venir. Les diffusions
     TO suivent le concept harnais : sous la définition électrique, elles
     restent dessinées, en retrait ; sous le concept, ce sont les PH. */
  const lireJalons = () => pg.evaluate(() => ({
    retrait: [...document.querySelectorAll('.jalon.hors-perimetre .jalon-texte')].map(t => t.textContent).sort(),
    dessines: document.querySelectorAll('svg.graphe .jalon').length,
    zone: document.getElementById('zone-critique').getAttribute('data-jalon'),
    prochain: window.__prochainJalon() && window.__prochainJalon().texte,
    entete: (document.querySelector('.critique-tete button[data-trig="requis"]') || {}).title || ''
  }));
  await pg.click('.segmente button[data-span="0"]'); await pg.waitForTimeout(400);
  const jTout = await lireJalons();
  verifier('sur « Tout », les cinq jalons sont dessinés ; seules les diffusions TO, du concept harnais, sont en retrait ; l\'en-tête du rythme requis nomme l\'échéance',
    jTout.dessines === 5 && jTout.retrait.join('|') === 'Diffusion TO Base|Diffusion TO Perso' && !!jTout.prochain && jTout.zone === jTout.prochain &&
    jTout.entete.indexOf('«\u00a0' + jTout.prochain + '\u00a0»') !== -1, JSON.stringify(jTout));
  await pg.click('#choix-perimetre button[data-perimetre="PERSO"]'); await pg.waitForTimeout(700);
  const jPerso = await lireJalons();
  verifier('sous PERSO, le jalon PH Base est en retrait (et les TO), et l\'échéance affichée est celle que la page calcule',
    jPerso.retrait.join('|') === 'Diffusion PH Base|Diffusion TO Base|Diffusion TO Perso' && !!jPerso.prochain && jPerso.zone === jPerso.prochain &&
    !/Base$/.test(jPerso.prochain) && jPerso.entete.indexOf('«\u00a0' + jPerso.prochain + '\u00a0»') !== -1, JSON.stringify(jPerso));
  await pg.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await pg.waitForTimeout(700);
  const jBase = await lireJalons();
  verifier('sous BASE/OPTION, le jalon PH Perso est en retrait (et les TO)',
    jBase.retrait.join('|') === 'Diffusion PH Perso|Diffusion TO Base|Diffusion TO Perso' && !!jBase.prochain && jBase.zone === jBase.prochain &&
    !/Perso$/.test(jBase.prochain), JSON.stringify(jBase));
  await pg.click('#choix-perimetre button[data-perimetre=""]'); await pg.waitForTimeout(500);
  // Sous le concept harnais, l'inverse : les PH et le solde FWD en retrait, les TO comptent.
  await pg.click('#choix-indicateur button[data-indicateur="concept"]'); await pg.waitForTimeout(700);
  await pg.click('.segmente button[data-span="0"]'); await pg.waitForTimeout(400);
  const jConcept = await lireJalons();
  verifier('sous le concept harnais, les jalons du FWD sont en retrait et l\'échéance est la diffusion TO',
    jConcept.retrait.join('|') === 'Diffusion PH Base|Diffusion PH Perso|Solde FWD' && /^Diffusion TO/.test(jConcept.prochain || ''),
    JSON.stringify(jConcept));
  await pg.click('#choix-indicateur button[data-indicateur="def"]'); await pg.waitForTimeout(700);

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
    jrn.resumes.every(r => !/en en cour|passés en terminé|passés en validé/.test(r)) &&
    jrn.resumes.some(r => /passés? à « [^»]+ »/.test(r)),
    JSON.stringify(jrn.resumes[0]));
  verifier('chaque ligne nomme le plan et son passage',
    /UD-/.test(jrn.premiere || ''), jrn.premiere);
  verifier('les états sont au singulier dans une flèche',
    !/(Terminés|Validés)\s*$/.test(jrn.premiere || '') , jrn.premiere);
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
      compte: !!document.querySelector('.compte-passage[data-passage="indice"]'),
      racines: window.__analyserUD('UD-24-1037')
    };
  });
  verifier('des références hors format ne sont jamais appariées : aucun changement d’indice',
    appariement.types.indice === 0 && !appariement.compte, JSON.stringify(appariement.types));
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
    const b = document.querySelector('#filtre-journal button[data-famille="termine"]:not([disabled])');
    return b ? { cle: b.dataset.journal, mot: b.querySelector('.libelle').textContent.trim() } : null;
  });
  await pg.click('#filtre-journal button[data-famille="termine"]:not([disabled])'); await pg.waitForTimeout(400);
  verifier('le filtre d’une valeur finie (« ' + (boutonFini && boutonFini.mot) + ' ») ne laisse que des passages vers elle',
    !!boutonFini && await pg.evaluate(m => [...document.querySelectorAll('.journal-ligne .vers')]
      .every(v => v.querySelector('.etiq-etat.apres').textContent.trim() === m), boutonFini.mot));
  /* Débrief 18 : un plan réémis devenu validé est de ceux-là ; dans sa
     semaine, il garde sa case « changement d'indice ». */
  verifier('et les résumés ne parlent plus que d’elle (ou des réémissions arrivées à elle)',
    !!boutonFini && await pg.evaluate(k => [...document.querySelectorAll('.journal-tete .resume .compte-passage')]
      .every(b => b.dataset.passage === k || b.dataset.passage === 'indice') &&
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
  /* Débrief 18 : les petites pastilles de couleur — journal, bloc par
     groupe, graphique —, sur la page servie par Code.gs. */
  section('Débrief 18 : les pastilles du journal, du bloc et du graphique, dans la page servie');
  const past18 = await pg.evaluate(() => {
    const cles = (sel, attr) => [...document.querySelectorAll(sel + ' button')].map(b => b.getAttribute(attr));
    const vals = window.__valeurs();
    /* Ce que chaque rangée doit montrer, recompté ici : les passages du
       journal, les valeurs que portent les plans, celles que les relevés
       ont portées (débrief 19 : rien d'autre). */
    const evts = window.__journalAffiche().reduce((l, s) => l.concat(s.evenements), []);
    const estRecul = e => e.type === 'change' && ((e.avant === 'termine' && e.apres !== 'termine') || (e.avant === 'encours' && e.apres === 'afaire'));
    const arrivees = {};
    evts.forEach(e => { if ((e.type === 'change' || e.type === 'indice') && e.cApres && e.cApres !== e.cAvant) arrivees[e.cApres] = (arrivees[e.cApres] || 0) + 1; });
    const max = k => Math.max(...window.__serieValeur(k).pts.map(p => p.termine));
    return {
      vals: vals.map(v => v.cle), portees: vals.filter(v => v.n > 0).map(v => v.cle),
      seule: vals.filter(v => v.famille === 'termine').length === 1 ? vals.filter(v => v.famille === 'termine')[0].cle : null,
      arrivees, reculs: evts.filter(estRecul).length, indice: evts.filter(e => e.type === 'indice').length,
      releves: vals.filter(v => max(v.cle) > 0).map(v => v.cle),
      journal: cles('#filtre-journal', 'data-journal'),
      bloc: cles('#filtre-valeur-groupe', 'data-valeur-bloc'), blocVisible: !document.getElementById('filtre-valeur-groupe').hidden,
      graphe: cles('#filtre-valeur-graphe', 'data-valeur-graphe'), grapheVisible: !document.getElementById('filtre-valeur-graphe').hidden,
      grapheMax: cles('#filtre-valeur-graphe', 'data-valeur-graphe').filter(Boolean).map(max),
      comptes: [...document.querySelectorAll('#filtre-journal button .n')].map(n => Number(n.textContent.replace(/\D/g, ''))),
      desactives: document.querySelectorAll('#filtre-journal button:disabled, #filtre-valeur-groupe button:disabled, #filtre-valeur-graphe button:disabled').length
    };
  });
  const jAttendu18 = past18.vals.filter(k => past18.arrivees[k]);
  verifier('journal : seulement les passages qu’il y a — « Tout », les valeurs atteintes dans l’ordre des tuiles, puis reculs et indice s’il y en a ; chacune comptée, aucune à zéro',
    past18.journal[0] === '' && past18.journal.slice(1, jAttendu18.length + 1).join() === jAttendu18.join() &&
    past18.journal.indexOf('reculs') === (past18.reculs ? past18.journal.length - (past18.indice ? 2 : 1) : -1) &&
    past18.journal.indexOf('indice') === (past18.indice ? past18.journal.length - 1 : -1) &&
    past18.comptes.length === past18.journal.length - 1 && past18.comptes.every(n => n > 0), JSON.stringify(past18));
  verifier('bloc : « Tout » puis chaque valeur que portent les plans, et elles seules',
    past18.blocVisible && past18.bloc.join() === ['', ...past18.portees].join(), JSON.stringify([past18.bloc, past18.portees]));
  /* Après les valeurs du jour viennent celles « d'hier » : portées par des
     relevés, plus par aucun plan (ici « Entre 0 et 100 % », « À faire »). */
  verifier('graphique : « Validés » (ou la seule valeur validée) en tête, puis une pilule par valeur que les relevés ont portée, et aucune autre',
    past18.grapheVisible && past18.graphe[0] === '' && past18.grapheMax.every(m => m > 0) &&
    past18.releves.every(k => k === past18.seule || past18.graphe.indexOf(k) !== -1),
    JSON.stringify([past18.releves, past18.graphe, past18.grapheMax]));
  verifier('aucune pilule grisée dans les trois rangées', past18.desactives === 0, String(past18.desactives));
  const choix18 = await pg.evaluate(() => window.__valeurs().filter(v => v.famille !== 'termine' && v.n > 0)[0]);
  await pg.evaluate(k => [...document.querySelectorAll('#filtre-valeur-groupe button')].find(b => b.dataset.valeurBloc === k).click(), choix18.cle);
  await pg.waitForTimeout(300);
  const somme18 = await pg.evaluate(() => [...document.querySelectorAll('.critique-ligne .critique-total')].reduce((t, e) => t + Number(e.textContent), 0));
  verifier('bloc sous « ' + choix18.libelle + ' » : les comptes des groupes font ses ' + choix18.n + ' plans', somme18 === choix18.n, String(somme18));
  await pg.click('#filtre-valeur-groupe button[data-valeur-bloc=""]'); await pg.waitForTimeout(300);
  await pg.evaluate(k => [...document.querySelectorAll('#filtre-valeur-graphe button')].find(b => b.dataset.valeurGraphe === k).click(), choix18.cle);
  await pg.waitForTimeout(300);
  const courbe18 = await pg.evaluate(k => { const pts = window.__serieValeur(k).pts; return { fin: pts[pts.length - 1].termine,
    note: document.getElementById('note-graphe').textContent }; }, choix18.cle);
  verifier('graphique sous « ' + choix18.libelle + ' » : la courbe finit à ses ' + choix18.n + ' plans, et la note la nomme',
    courbe18.fin === choix18.n && courbe18.note.indexOf('Plans « ' + choix18.libelle + ' »') === 0, JSON.stringify(courbe18));
  await pg.click('#filtre-valeur-graphe button[data-valeur-graphe=""]'); await pg.waitForTimeout(300);

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
    JSON.stringify(ess.titres) === JSON.stringify(['Référence UD', 'Avancement Définition Electrique', 'Nom Installation', 'ECP',
      'ATA', 'Séquence', 'Validation Définition Electrique', 'Date création',
      'Avancement Concept Harnais']),
    JSON.stringify(ess.titres));
  verifier('ni Statut iBG ni les blocs repetes n\'y entrent',
    ess.titres.indexOf('Statut iBG') === -1 && ess.titres.indexOf('Validité') === -1);
  verifier('aucun plan n\'est perdu au passage', ess.lignes === 186, String(ess.lignes));
  verifier('la reference ouvre la vue essentielle, figee avec la colonne suivie',
    ess.titres[0] === 'Référence UD' && ess.figees === 2, String(ess.figees));
  verifier('l\'interrupteur dit laquelle des deux est active',
    ess.presse.join(' ') === 'toutes:false essentielle:true', JSON.stringify(ess.presse));

  await pg.click('#vue-tableau button[data-vue="toutes"]'); await pg.waitForTimeout(600);
  const retour = await pg.evaluate(() => ({
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    figees: document.querySelectorAll('tr.titres th.col-fige').length
  }));
  verifier('revenir rend l\'extract entier dans l\'ordre de la feuille',
    JSON.stringify(retour.titres) === JSON.stringify(vg.ordre), String(retour.titres.length));
  verifier('et le bloc fige reste la reference et la colonne suivie', retour.figees === 2, String(retour.figees));

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
  verifier('la note du graphique nomme le périmètre', /^Historique · périmètre PERSO · /.test(persoG.note), persoG.note);
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
    /* Une sous-liste par valeur de la colonne (débrief 13) : son libellé, son
       compte, et les titres de ses jetons. */
    /* Débrief 20 : les plans à l'arrêt ouvrent la liste, sous leur propre
       titre, hors des sous-listes par valeur. */
    arret: document.querySelectorAll('.groupe-refs .sous-arret .jeton-ud[data-ud]').length,
    paquets: [...document.querySelectorAll('.groupe-refs .sous-groupe')].map(sg => {
      const t = sg.querySelector('.sous-titre'), n = t.querySelector('.n');
      return { libelle: t.textContent.slice(0, t.textContent.length - (n ? n.textContent.length : 0)).replace(/\s+/g, ' ').trim(),
               n: n ? +n.textContent.replace(/\D/g, '') : NaN, pastille: !!t.querySelector('.pastille'),
               etats: [...sg.querySelectorAll('.jeton-ud[data-ud]')].map(b => (b.getAttribute('title') || '').split(' — ')[0]) };
    }),
    ordre: window.__valeurs().map(v => v.libelle),
    autres: /autres/.test((document.querySelector('.groupe-refs') || {}).textContent || ''),
    etats: [...document.querySelectorAll('.jeton-ud[data-ud] .pastille')].map(e => e.className),
    tableau: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('choisir un groupe déplie ses références', ud.jetons.length > 0, String(ud.jetons.length));
  verifier('toutes, sans « et N autres », une sous-liste par valeur, dans l’ordre de la barre du haut, avec pastille et compte',
    ud.jetons.length === ud.total && !ud.autres && ud.paquets.length >= 2 &&
    ud.paquets.every((q, i) => q.pastille && q.n === q.etats.length && ud.ordre.indexOf(q.libelle) !== -1 &&
      (i === 0 || ud.ordre.indexOf(ud.paquets[i - 1].libelle) < ud.ordre.indexOf(q.libelle))) &&
    ud.paquets.reduce((t, q) => t + q.n, 0) + ud.arret === ud.total,
    ud.jetons.length + ' / ' + ud.total + ' ' + JSON.stringify(ud.paquets.map(q => [q.libelle, q.n])));
  verifier('toutes sont des références de plan', ud.jetons.every(t => /^UD-/.test(t)), JSON.stringify(ud.jetons.slice(0, 3)));
  verifier('l\'en-tête dit combien et combien restent',
    /\d+ plans?/.test(ud.entete) && /(pas encore validés?|tout est validé)/.test(ud.entete), ud.entete.trim());
  verifier('le tableau du bas montre exactement le même groupe',
    ud.tableau === Math.min(ud.jetons.length, ud.tableau) && ud.tableau > 0);
  verifier('chaque sous-liste ne porte que son état : plus de tas où les états se mêlent',
    ud.paquets.every(q => q.etats.every(e => e === q.libelle)), JSON.stringify(ud.paquets.map(q => [q.libelle, q.etats.slice(0, 2)])));
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
  /* Le tableau réduit à ce plan : son historique s'ouvre au-dessus (débrief
     14), lu dans les relevés tels que Code.gs les archive — une case par
     relevé, et depuis quand il est dans sa valeur. */
  const vieUD = await pg.evaluate(r => {
    const f = document.getElementById('fiche-plan');
    return { visible: !f.hidden, ref: (f.querySelector('.ref') || {}).textContent, cases: f.querySelectorAll('.fiche-plan-frise .case').length,
             releves: window.__serieAffichee().pts.length, resume: (f.querySelector('.fiche-plan-resume') || {}).textContent || '' };
  }, refUD);
  verifier('l’historique du plan s’ouvre au-dessus du tableau : une case par relevé archivé, et depuis quand il est dans sa valeur',
    vieUD.visible && vieUD.ref === refUD && vieUD.cases === vieUD.releves && vieUD.releves >= 2 &&
    / depuis (au moins )?S\d{1,2} · \S+ \d{4}/.test(vieUD.resume.replace(/[\u00a0\u202f]/g, ' ')), JSON.stringify(vieUD));
  const ouiNonUD = await pg.evaluate(() => [...document.querySelectorAll('#corps-tableau td')].some(td => /^(true|false)$/i.test(td.textContent.trim())));
  verifier('aucune case du tableau ne dit true ou false : Oui ou Non', !ouiNonUD);
  await pg.click('#tout-effacer'); await pg.waitForTimeout(450);

  // =================================================================
  section('Repères du bloc par groupe');
  /* Deux colonnes calculées, chacune avec son « ? » : la fin estimée, et la
     dernière, qui est « rythme requis » quand un jalon de la configuration
     est à venir (c'est le cas : CONFIG.JALONS en fournit), « rythme tenu »
     sinon. */
  const reperes = await pg.evaluate(() => ({
    aides: document.querySelectorAll('button[data-aide]').length,
    avecJalon: !document.getElementById('zone-critique').classList.contains('sans-jalon'),
    derniere: [...document.querySelectorAll('.critique-tete button[data-trig]')].slice(-1)[0].textContent.trim()
  }));
  verifier('chaque colonne calculée porte son « ? »', reperes.aides === 2, reperes.aides + ' « ? »');
  verifier('avec un jalon de configuration à venir, la dernière colonne est le rythme requis',
    reperes.avecJalon && /rythme requis/.test(reperes.derniere), JSON.stringify(reperes));
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
    if (/passés? à « 100 % »/.test(t.replace(/[\u00a0\u202f]/g, ' '))) { texteBulle = t; break; }
  }
  /* La bulle dit les passages comme le journal : par valeur d'arrivée. */
  verifier('survoler une semaine annonce les passages, dans les mots du journal',
    /passés? à « 100 % »/.test(texteBulle.replace(/[\u00a0\u202f]/g, ' ')), texteBulle.slice(0, 90));
  /* La bulle résume : « terminés N / total », l'écart, puis les comptes de la
     semaine. Les références, elles, sont dans le journal, dessous. */
  verifier('en comptes, sans lister les références ni « et N autres »',
    !/UD-/.test(texteBulle) && !/autres/.test(texteBulle) &&
    /validés\s*\d+\s*\/\s*\d+/.test(texteBulle), texteBulle.slice(0, 120));

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
  /* Une seule liste (débrief 14) : les verdicts. Le clic sur « seulement
     dans Base2 » l'a posé ET déplié sous sa ligne : sa ligne seulement là,
     cherchée sur REF_UD. Plus de « plan par plan » qui répète les verdicts. */
  const listeB2 = await pr.evaluate(() => ({
    ancienne: !!document.querySelector('#liste-rapprochement, .rapp-groupe'),
    ouverts: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]')].map(g => g.dataset.lot).join(),
    chevrons: [...document.querySelectorAll('#verdicts-rapprochement .verdict:not([disabled])')].every(b => !!b.querySelector('.chevron')),
    seul: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-lot="seul"] .rapp-puce')].map(b => ({
      ref: b.querySelector('.rapp-puce-ref').textContent, la: b.dataset.ligneLa, gates: b.dataset.etat || '', bulle: b.title
    }))
  }));
  verifier('une seule liste sur Base2 : les verdicts, chacun son chevron, « seulement dans Base2 » déplié sous sa ligne avec REF_UD',
    !listeB2.ancienne && listeB2.ouverts === 'seul' && listeB2.chevrons && listeB2.seul.length === 1 && listeB2.seul[0].ref === 'UD-99-9999' &&
    listeB2.seul[0].la === 'UD-99-9999' && listeB2.seul[0].gates === '' && /^aucun plan dans GATES/.test(listeB2.seul[0].bulle), JSON.stringify(listeB2));
  await pr.click('#verdicts-rapprochement .verdict-bloc[data-lot="seul"] button[data-ligne-la]'); await pr.waitForTimeout(500);
  verifier('un clic sur cette référence ouvre le tableau de Base2 cherché sur UD-99-9999, le lot retiré, le jeton de recherche posé',
    await pr.evaluate(() => {
      const l = document.querySelectorAll('#corps-seconde tr[data-i]');
      const jetons = [...document.querySelectorAll('.jeton')].map(j => j.textContent);
      return document.getElementById('recherche-seconde').value === 'UD-99-9999' && l.length === 1 && !document.getElementById('cadre-seconde').hidden &&
        jetons.some(j => /Recherche dans Base2 : UD-99-9999/.test(j)) && !jetons.some(j => /Comparaison : /.test(j));
    }));
  await ctxRapp.close();

  // =================================================================
  section('Premier relevé : les vraies données, rien de fabriqué');
  construire({ gates: true, historique: 'premier', sortie: 'apercu-premier.html' });
  const ctxPremier = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pp = await ctxPremier.newPage();
  pp.on('pageerror', e => erreursJS.push('premier : ' + e.message));
  pp.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push('premier : ' + m.text()); });
  await pp.goto('file://' + path.join(__dirname, '..', 'apercu-premier.html'));
  await pp.waitForTimeout(1600);
  /* Plus de mode « Exemple » : devant le classeur, la page montre ses
     données, et seulement elles — pas d'interrupteur, pas d'historique
     inventé. Au premier relevé, le journal dit qu'il attend le deuxième. */
  const premier = await pp.evaluate(() => ({
    interrupteur: !!document.getElementById('mode-donnees') || !!document.querySelector('[data-mode="exemple"]'),
    mot: document.getElementById('mot-mode').textContent.trim(),
    vide: document.body.dataset.vide,
    /* Les plans du tableau, tranche dessinée et lignes à venir comprises
       (débrief 18 : 60 lignes d'abord). */
    plans: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length +
      (Number(((document.querySelector('#corps-tableau tr.ligne-suite') || {}).textContent || '').replace(/[\s\u202f\u00a0]/g, '').replace(/^(\d+).*$/, '$1')) || 0),
    phrase: document.getElementById('phrase').textContent,
    journal: document.getElementById('zone-journal').textContent,
    pied: document.getElementById('avertissement-demo').hidden
  }));
  verifier('plus d\'interrupteur « Exemple » ni de mot de démonstration devant le classeur',
    !premier.interrupteur && premier.mot === '' && premier.pied && premier.vide === 'false', JSON.stringify(premier));
  verifier('les plans affichés sont ceux de la feuille', premier.plans === 186 && /186 plans/.test(premier.phrase), premier.phrase);
  verifier('le journal explique pourquoi il est vide : un seul relevé, nommé, et le suivant le remplira',
    /^Un seul relevé archivé pour l’instant \(S\d{1,2} · \S+ \d{4}\) : le journal se remplira au suivant\./.test(premier.journal.replace(/[\u00a0\u202f]/g, ' ')), premier.journal.slice(0, 160));
  await ctxPremier.close();

  /* Un classeur sans plan : pas de démonstration à la place, mais ce qu'il
     faut faire — le message du script, et les trois gestes. */
  construire({ lignes: 10, historique: false, sortie: 'apercu-classeur-vide.html' });
  const pv = await (await nav.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  pv.on('pageerror', e => erreursJS.push('classeur vide : ' + e.message));
  /* Le paquet d'un classeur qui n'a rien rendu, posé à la place du vrai. */
  const htmlVide = fs.readFileSync(path.join(__dirname, '..', 'apercu-classeur-vide.html'), 'utf8')
    .replace(/window\.SUIVI_FWD_DONNEES = [\s\S]*?;\n/, 'window.SUIVI_FWD_DONNEES = ' +
      JSON.stringify({ ok: false, message: 'Aucun onglet de données exploitable dans ce classeur : « Feuille 1 » est vide.', plans: [], releves: [], jalons: [], contrats: [], contrat: '' }) + ';\n');
  fs.writeFileSync(path.join(__dirname, '..', 'apercu-classeur-vide.html'), htmlVide);
  await pv.goto('file://' + path.join(__dirname, '..', 'apercu-classeur-vide.html')); await pv.waitForTimeout(900);
  const etatVide = await pv.evaluate(() => ({
    vide: document.body.dataset.vide,
    panneau: getComputedStyle(document.getElementById('classeur-vide')).display !== 'none',
    gestes: document.querySelectorAll('#classeur-vide ol li').length,
    alerte: document.getElementById('alerte-source').hidden ? '' : document.getElementById('alerte-source').textContent,
    sections: [...document.querySelectorAll('section.avancement, section.bloc')].every(el => getComputedStyle(el).display === 'none'),
    demo: /Démonstration/.test(document.getElementById('mot-mode').textContent),
    /* Le pied compterait « 1 relevé archivé » là où il n'y en a aucun. */
    pied: getComputedStyle(document.querySelector('.pied')).display === 'none'
  }));
  verifier('un classeur sans plan : le message du script et les trois gestes, pas de sections vides, de pied ni de démonstration',
    etatVide.vide === 'true' && etatVide.panneau && etatVide.gestes === 3 && /Feuille 1/.test(etatVide.alerte) && etatVide.sections && !etatVide.demo && etatVide.pied,
    JSON.stringify(etatVide));
  await pv.context().close();
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-classeur-vide.html'));

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
    /* L'extract recollé après le dernier relevé archivé (débrief 15) : un
       point de plus, à la semaine où l'on est, que le pied annonce. */
    extrait: /pas encore archivé/.test(document.getElementById('import').textContent),
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
    x2M.releves === cM.getHistorique(clM, 'X2').length + (x2M.extrait ? 1 : 0) && x2M.releves >= 2,
    x2M.releves + ' vs ' + cM.getHistorique(clM, 'X2').length + (x2M.extrait ? ' + l’extract du jour' : ''));
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
    retourM.releves === cM.getHistorique(clM, 'X1').length + (retourM.extrait ? 1 : 0) && retourM.etat === '',
    JSON.stringify([retourM.plans, retourM.nom, retourM.releves]));
  /* La vue d'ensemble (débrief 14) : une ligne par contrat, avec les
     chiffres de sa propre page. X1 est affiché ; X2 vient du classeur par
     le pont — une fois : les paquets reçus sont gardés. La page, elle, ne
     bouge pas. */
  const avantEns = await etatPage();
  await pm.click('#voir-ensemble'); await pm.waitForTimeout(2000);
  const ens = await pm.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr => ({
    nom: tr.querySelector('th button').textContent.trim(), courant: tr.classList.contains('courant'),
    termines: (tr.querySelector('td .v') || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim()
  })));
  const apresEns = await etatPage();
  const nouveauxAppels = apresEns.appels.slice(avantEns.appels.length);
  verifier('la vue d’ensemble liste X1 et X2, X1 affiché ; X2 est demandé au classeur par le pont, une fois',
    ens.map(r => r.nom).join() === 'X1,X2' && ens[0].courant && !ens[1].courant && nouveauxAppels.join() === 'X2',
    JSON.stringify([ens, nouveauxAppels]));
  verifier('les terminés de X1 sont ceux de sa page, et la page n’a pas bougé',
    apresEns.phrase.replace(/\s+/g, ' ').indexOf(ens[0].termines.replace(' / ', ' sur ')) === 0 &&
    apresEns.plans === avantEns.plans && apresEns.nom === 'X1' && apresEns.phrase === avantEns.phrase,
    JSON.stringify([ens[0], apresEns.phrase]));
  await pm.click('#ensemble button[data-aller-contrat="X2"]'); await pm.waitForTimeout(1200);
  const x2Ens = await etatPage();
  verifier('un clic sur X2 l’affiche avec les terminés annoncés, sans redemander son paquet au classeur',
    x2Ens.nom === 'X2' && x2Ens.plans === 93 && x2Ens.appels.length === apresEns.appels.length &&
    x2Ens.phrase.replace(/\s+/g, ' ').indexOf(ens[1].termines.replace(' / ', ' sur ')) === 0,
    JSON.stringify([ens[1], x2Ens.phrase, x2Ens.appels]));
  await ctxMulti.close();

  // =================================================================
  /* Débrief 17 (réponses) : HDK a les jalons du programme, THS aucun — de
     bout en bout, par la page servie : le classeur a ses vrais noms
     d'onglets, la configuration livrée n'est pas adaptée. */
  section('Débrief 17 (réponses) : THS sans jalon, dans la page servie');
  const ht17 = construire({ gates: true, contrats: ['HDK', 'THS'], lignes: 60, sortie: 'apercu-hdk-ths.html' });
  const ctxHT = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pht = await ctxHT.newPage();
  pht.on('pageerror', e => erreursJS.push('hdk-ths : ' + e.message));
  await brancherClasseur(pht, ht17.contexte);
  await pht.goto('file://' + path.join(__dirname, '..', 'apercu-hdk-ths.html'));
  await pht.waitForTimeout(1600);
  const etatHT = () => pht.evaluate(() => {
    const b = document.getElementById('echeance-titre');
    return { contrat: document.getElementById('select-contrat').value, puce: getComputedStyle(b).display !== 'none' ? b.textContent.replace(/\s+/g, ' ').trim() : '',
      legende: document.querySelectorAll('#legende-jalons [data-jalon]').length,
      tete: [...document.querySelectorAll('.critique-tete button')].map(x => x.textContent.trim()).join('|') };
  });
  const hdk17 = await etatHT();
  /* Tant qu'un jalon de HDK est à venir (jusqu'en février 2027). */
  const avenir17 = ht17.contexte.getJalons('HDK').some(j => j.semaine >= ht17.contexte.numeroSemaineISO(new Date()));
  verifier('HDK : la puce de la prochaine échéance, les cinq jalons en légende, le rythme requis par groupe',
    hdk17.contrat === 'HDK' && hdk17.legende === 5 && (!avenir17 || (/^Prochaine échéance/.test(hdk17.puce) && /rythme requis/.test(hdk17.tete))), JSON.stringify(hdk17));
  await pht.selectOption('#select-contrat', 'THS'); await pht.waitForTimeout(1500);
  const ths17 = await etatHT();
  verifier('THS : aucune échéance à l’écran — ni puce, ni légende — et le rythme tenu à la place du rythme requis',
    ths17.contrat === 'THS' && ths17.puce === '' && ths17.legende === 0 && /rythme tenu/.test(ths17.tete) && !/rythme requis/.test(ths17.tete),
    JSON.stringify(ths17));
  await pht.click('#voir-ensemble'); await pht.waitForTimeout(2000);
  const ensHT = await pht.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr =>
    tr.querySelector('th button').textContent.trim() + ':' + [...tr.querySelectorAll('td')].map(td => td.textContent.replace(/\s+/g, ' ').trim()).join('|')));
  verifier('vue d’ensemble : HDK a sa prochaine échéance, THS « aucun jalon » (et non « aucune à venir », qui les croirait passées)',
    ensHT.length === 2 && (!avenir17 || /^HDK:.*(Solde FWD|Diffusion)/.test(ensHT[0])) && /^THS:.*aucun jalon/.test(ensHT[1]) &&
    !/Solde FWD|Diffusion|aucune à venir/.test(ensHT[1]),
    JSON.stringify(ensHT));
  await ctxHT.close();
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-hdk-ths.html'));

  // =================================================================
  /* L'ouverture rapide. Le paquet voyage compacté — chaque nom de colonne,
     chaque référence d'un relevé écrit une fois — et la page le rend à
     l'identique. Un gros extract ne dessine d'abord qu'une tranche du
     tableau ; la suite vient en descendant, ou d'un clic. Le diagnostic dit
     le temps de chaque lecture. */
  section('Ouverture rapide : paquet compact, tableau par tranches');
  const complet = gates.contexte.getDonneesPourClient();
  const compactJson = gates.contexte.donneesJSONPourPage();
  verifier('le paquet posé dans la page est compacté : moins de 40 % du poids complet',
    compactJson.length < 0.4 * JSON.stringify(complet).length && /"plansTab":\{"cles":/.test(compactJson) && !/"plans":\[/.test(compactJson),
    Math.round(compactJson.length / 1024) + ' Ko contre ' + Math.round(JSON.stringify(complet).length / 1024) + ' Ko');
  const pCompact = await (await nav.newContext()).newPage();
  await pCompact.goto('file://' + path.join(__dirname, '..', 'prototype', 'apercu.html')); await pCompact.waitForTimeout(600);
  const pourComparer = (o) => JSON.parse(JSON.stringify(o, (k, v) => k === 'genereLe' ? undefined : v));
  const seeCompact = construire({ lignes: 60, gates: true, feuilles: [see], config: configSEE, sortie: 'apercu-compact.html' });
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-compact.html'));
  for (const [nom, ctxS] of [['GATES seul', gates.contexte], ['avec historique et SEE', seeCompact.contexte]]) {
    const attendu = pourComparer(ctxS.getDonneesPourClient());
    const rendu = await pCompact.evaluate(j => window.__deballerPaquet(JSON.parse(j)), ctxS.donneesJSONPourPage());
    const trie = o => Array.isArray(o) ? o.map(trie) : (o && typeof o === 'object') ? Object.keys(o).sort().reduce((r, k) => (r[k] = trie(o[k]), r), {}) : o;
    verifier('déballé par la page, le paquet ' + nom + ' est exactement celui du serveur',
      JSON.stringify(trie(pourComparer(rendu))) === JSON.stringify(trie(attendu)));
  }
  verifier('un contrat demandé par la page arrive compacté lui aussi',
    !!gates.contexte.getDonneesCompactes().plansTab && !gates.contexte.getDonneesCompactes().plans);
  await pCompact.context().close();

  construire({ lignes: 640, gates: true, sortie: 'apercu-gros.html' });
  const pGros = await (await nav.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pGros.on('pageerror', e => erreursJS.push('gros : ' + e.message));
  await pGros.goto('file://' + path.join(__dirname, '..', 'apercu-gros.html')); await pGros.waitForTimeout(1200);
  const tranche1 = await pGros.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
    suite: (document.querySelector('#corps-tableau tr.ligne-suite') || {}).textContent || '',
    compte: document.getElementById('compte').textContent
  }));
  verifier('640 plans sur 138 colonnes : une première tranche de 60 lignes seulement (débrief 18 : l\'ouverture rapide), et le compte dit bien 640',
    tranche1.lignes >= 60 && tranche1.lignes <= 100 && /640 plans/.test(tranche1.compte) &&
    new RegExp((640 - tranche1.lignes) + ' lignes de plus').test(tranche1.suite.replace(/\s/g, ' ')), JSON.stringify(tranche1));
  /* Le bouton est au bas du cadre qui défile : y faire défiler pour le
     cliquer charge déjà la tranche suivante (« descendez, ou cliquez ici »)
     et le remplace sous le pointeur. On le clique donc là où il est, sans
     défiler — c'est son geste à lui qu'on vérifie ; le défilement a son test
     juste après. */
  await pGros.evaluate(() => document.querySelector('#corps-tableau tr.ligne-suite button').click()); await pGros.waitForTimeout(400);
  const tranche2 = await pGros.evaluate(() => document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length);
  verifier('un clic sur « N lignes de plus » ajoute la tranche suivante', tranche2 > tranche1.lignes, tranche1.lignes + ' → ' + tranche2);
  // Comme quelqu'un qui lit : on descend jusqu'au tableau, puis dans le tableau.
  await pGros.evaluate(() => document.getElementById('section-plans').scrollIntoView()); await pGros.waitForTimeout(400);
  for (let k = 0; k < 20; k++) {
    await pGros.evaluate(() => { const d = document.getElementById('defile'); d.scrollTop = d.scrollHeight; });
    await pGros.waitForTimeout(200);
  }
  const toutes = await pGros.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
    suite: !!document.querySelector('#corps-tableau tr.ligne-suite'),
    figees: [...document.querySelectorAll('#corps-tableau tr:last-child td.col-fige')].every(td => td.style.left !== '')
  }));
  verifier('en descendant dans le tableau, les 640 lignes finissent toutes là, colonnes figées comprises',
    toutes.lignes === 640 && !toutes.suite && toutes.figees, JSON.stringify(toutes));
  await pGros.fill('#recherche', 'UD-21'); await pGros.waitForTimeout(500);
  const filtreGros = await pGros.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
    compte: document.getElementById('compte').textContent
  }));
  verifier('un filtre porte sur toutes les lignes, pas sur la tranche dessinée',
    filtreGros.lignes > 0 && new RegExp('^' + filtreGros.lignes + ' plans? sur 640').test(filtreGros.compte.replace(/\s/g, ' ')), JSON.stringify(filtreGros));
  await pGros.context().close();
  fs.unlinkSync(path.join(__dirname, '..', 'apercu-gros.html'));
  const diagTemps = gates.contexte.diagnostic();
  verifier('le diagnostic dit le temps de chaque lecture : GATES, historique, seconde base',
    /préparé en \d+,\d s — lecture de GATES \d+,\d s, de l'historique \d+,\d s, de la seconde base \d+,\d s/.test(diagTemps), diagTemps.slice(-600));

  // =================================================================
  section('Débrief 17 : les quatre fichiers d’une même livraison');
  /* Au bureau, la page est restée blanche : le Javascript du jour avec un
     Index d'avant — l'emplacement de l'alerte des valeurs manquait, le
     démarrage s'arrêtait sur un null, sans un mot. Chaque fichier porte
     désormais sa livraison ; la page nomme celui qui diffère, et une panne
     au démarrage s'affiche en tête de page. */
  const racineRepo = path.join(__dirname, '..');
  const lireFichier = n => fs.readFileSync(path.join(racineRepo, n), 'utf8');
  const livraisons = {
    Code: (/^const EDITION = '([0-9a-f]+)';$/m.exec(lireFichier('Code.gs')) || [])[1],
    Index: (/SUIVI_FWD_LIVRAISON_INDEX = '([0-9a-f]+)';/.exec(lireFichier('Index.html')) || [])[1],
    Styles: (/--suivi-fwd-edition: "([0-9a-f]+)";/.exec(lireFichier('Styles.html')) || [])[1],
    Javascript: (/var EDITION = '([0-9a-f]+)';/.exec(lireFichier('Javascript.html')) || [])[1]
  };
  const ED = livraisons.Code;
  verifier('les quatre fichiers livrés portent la même livraison, posée par la construction',
    /^[0-9a-f]{7}$/.test(ED || '') && Object.keys(livraisons).every(k => livraisons[k] === ED), JSON.stringify(livraisons));
  verifier('le Javascript finit par sa ligne de fin (un fichier coupé au collage se reconnaît)',
    /\nwindow\.SUIVI_FWD_FIN = '[0-9a-f]{7}';\n<\/script>\n$/.test(lireFichier('Javascript.html')));

  construire({ gates: true, lignes: 60, sortie: 'apercu-livraison.html' });
  const pageLivraison = lireFichier('apercu-livraison.html');
  const variantes = {
    normale: t => t,
    indexAncien: t => t.replace("window.SUIVI_FWD_LIVRAISON_INDEX = '" + ED + "';", '')
      .replace('<div class="alerte-valeurs" id="alerte-valeurs" role="status" hidden></div>', ''),
    indexAncienPanne: t => t.replace("window.SUIVI_FWD_LIVRAISON_INDEX = '" + ED + "';", '')
      .replace('<span id="colonne-suivie"></span>', ''),
    jsCoupe: t => {
      const i = t.indexOf("var EDITION = '"), j = t.indexOf('window.SUIVI_FWD_FIN');
      return t.slice(0, i + Math.floor((j - i) / 2)) + t.slice(t.indexOf('</script>', j));
    },
    stylesAncien: t => t.replace('--suivi-fwd-edition: "' + ED + '";', ''),
    /* Un Javascript d'avant le débrief 17 ne s'annonce pas (ni livraison, ni
       démarrage signalé) mais dessine la page : le filet d'Index le nomme sans
       prétendre que la page n'a pas démarré. */
    jsAncien: t => t.replace('window.SUIVI_FWD_DEMARREE = true;', '').replace("var EDITION = '" + ED + "';", "var EDITION = 'source';"),
    codeAncien: t => t.replace('"edition":"' + ED + '"', '"edition":"abcdef0"'),
    /* Coupé sans sa fin : le <script> reste ouvert, avale la suite ; seul un
       filet posé en tête, avant Styles, peut encore parler. */
    jsCoupeSansFin: t => {
      const i = t.indexOf("var EDITION = '"), j = t.indexOf('window.SUIVI_FWD_FIN');
      return t.slice(0, i + Math.floor((j - i) / 2));
    },
    stylesCoupe: t => {
      const i = t.indexOf('<style>'), j = t.indexOf('</style>', i);
      return t.slice(0, i + Math.floor((j - i) / 2)) + t.slice(j + '</style>'.length);
    },
    /* Un Index d'avant le débrief 14 : pas de bouton « Vue d'ensemble », que le
       Javascript branche dès ses premières lignes, avant le démarrage — et
       pas de filet d'Index. Le filet du Javascript, posé en tête, parle. */
    indexTresAncien: t => t.replace("window.SUIVI_FWD_LIVRAISON_INDEX = '" + ED + "';", '')
      .replace('id="voir-ensemble"', 'id="voir-ensemble-absent"')
      .replace(/<script>\s*window\.SUIVI_FWD_ERREURS = \[\];[\s\S]*?<\/script>/, ''),
    /* Collé deux fois (la même livraison) ; puis une copie d'avant laissée
       sous la nouvelle, qui ne s'annonce pas. */
    jsDeuxFois: t => {
      const i = t.indexOf("<script>\n(function () {\n  'use strict';"), j = t.indexOf('</script>', i) + 9;
      return t.slice(0, j) + '\n' + t.slice(i, j) + t.slice(j);
    },
    jsNeufPuisAncien: t => {
      const i = t.indexOf("<script>\n(function () {\n  'use strict';"), j = t.indexOf('</script>', i) + 9;
      const ancien = t.slice(i, j).replace('if (window.SUIVI_FWD_DEMARREE) { DEMARRAGE_FINI = true; montrerDoublon(); return; }', '')
        .replace('window.SUIVI_FWD_DEMARREE = true;', '');
      return t.slice(0, j) + '\n' + ancien + t.slice(j);
    },
    erreur: t => t.replace('window.SUIVI_FWD_API = {',
      'String.prototype.normalize = function () { throw new TypeError(\'panne simulée "HDK-SECRET-42"\'); };\n  window.SUIVI_FWD_API = {')
  };
  const vuLivraison = {};
  for (const nom of Object.keys(variantes)) {
    const texte = variantes[nom](pageLivraison);
    verifier('variante « ' + nom + ' » fabriquée', nom === 'normale' || texte !== pageLivraison);
    const fichier = 'apercu-livraison-' + nom + '.html';
    fs.writeFileSync(path.join(racineRepo, fichier), texte);
    const pv = await ctxGates.newPage();
    const erreursPage = [];
    pv.on('pageerror', e => erreursPage.push(e.message));
    await pv.goto('file://' + path.join(racineRepo, fichier));
    await pv.waitForTimeout(900);
    vuLivraison[nom] = await pv.evaluate(() => ({
      cadre: (document.getElementById('suivi-fwd-panne') || {}).innerText || '',
      phrase: (document.getElementById('phrase') || {}).textContent || '',
      pied: document.getElementById('livraison') && !document.getElementById('livraison').hidden ? document.getElementById('livraison').textContent : ''
    }));
    vuLivraison[nom].erreurs = erreursPage;
    if (nom === 'normale') {
      vuLivraison.luLe = await pv.evaluate(() => { const e = document.getElementById('lu-le'); return e && !e.hidden ? e.textContent : ''; });
      vuLivraison.moisFr = await pv.evaluate(() => window.__anneeEtMois('03/04/2026').mois);
      /* La colonne suivie introuvable : la courbe s'arrête au dernier relevé
         archivé, au lieu d'un point du jour à zéro terminé. */
      vuLivraison.sansColonne = await pv.evaluate(() => {
        const avant = window.__serieAffichee().pts;
        const src = JSON.parse(JSON.stringify(window.SUIVI_FWD_DONNEES));
        src.colonnes = src.colonnes.filter(c => c.cle !== 'avancement');
        window.__chargerSource(src);
        const apres = window.__serieAffichee().pts;
        return { avant: avant[avant.length - 1].termine, apres: apres[apres.length - 1].termine, n: apres.length };
      });
      /* Et vidée alors que le dernier relevé en avait : de même. */
      vuLivraison.videe = await pv.evaluate(() => {
        const src = JSON.parse(JSON.stringify(window.SUIVI_FWD_DONNEES));
        src.plans.forEach(p => { p.avancement = ''; });
        window.__chargerSource(src);
        const pts = window.__serieAffichee().pts;
        return { dernier: pts[pts.length - 1].termine, alerte: document.getElementById('alerte-valeurs').textContent };
      });
    }
    await pv.close();
    fs.unlinkSync(path.join(racineRepo, fichier));
  }
  fs.unlinkSync(path.join(racineRepo, 'apercu-livraison.html'));
  const V = vuLivraison;
  verifier('quatre fichiers concordants : aucun cadre, et le pied dit « Livraison ' + ED + ' »',
    !V.normale.cadre && V.normale.pied === 'Livraison ' + ED && /sur 60 plans/.test(V.normale.phrase) && !V.normale.erreurs.length,
    JSON.stringify(V.normale));
  verifier('le pied dit quand les chiffres ont été lus dans le classeur',
    /^Chiffres lus dans le classeur le \S+ \d+ \S+ à \d{2}:\d{2} — recharger la page/.test(V.luLe || ''), V.luLe);
  verifier('la colonne suivie introuvable : la courbe s’arrête au dernier relevé archivé, pas de point du jour à zéro',
    V.sansColonne.apres === V.sansColonne.avant && V.sansColonne.apres > 0, JSON.stringify(V.sansColonne));
  verifier('la colonne suivie vidée (le relevé d’avant en avait) : pas de point à zéro, et l’alerte le dit',
    V.videe.dernier === V.sansColonne.avant && /est vide sur les 60 plans/.test(V.videe.alerte), JSON.stringify(V.videe));
  const indexLivre = lireFichier('Index.html');
  verifier('le squelette dit « Chargement… », et ni « Démonstration » ni « classeur vide » ne s’y lisent sans le Javascript',
    /id="phrase">Chargement…</.test(indexLivre) && /id="avertissement-demo" hidden/.test(indexLivre) && /id="classeur-vide" hidden/.test(indexLivre));
  verifier('un Index d’avant (le cas du bureau) : la page s’affiche quand même et nomme Index à recoller',
    /sur 60 plans/.test(V.indexAncien.phrase) && !V.indexAncien.erreurs.length &&
    /Les fichiers du tableau de bord ne concordent pas\. Index ne vient pas de la même livraison/.test(V.indexAncien.cadre) &&
    /Nouvelle version/.test(V.indexAncien.cadre), JSON.stringify(V.indexAncien));
  verifier('un Index d’avant qui arrête le démarrage : « La page n’a pas pu s’afficher », cause Index, au lieu d’un squelette vide',
    V.indexAncienPanne.phrase === '—' && V.indexAncienPanne.erreurs.length === 1 &&
    /La page n’a pas pu s’afficher\. Cause la plus probable : Index ne vient pas/.test(V.indexAncienPanne.cadre) &&
    /Détail : TypeError : .* — dans chargerSource/.test(V.indexAncienPanne.cadre), JSON.stringify(V.indexAncienPanne));
  verifier('un Javascript coupé au collage : le filet d’Index dit « incomplet », avec le geste',
    V.jsCoupe.phrase === '—' && /La page n’a pas pu démarrer\. Le fichier Javascript semble incomplet/.test(V.jsCoupe.cadre) &&
    /Javascript\.html\.txt en entier/.test(V.jsCoupe.cadre) && /SyntaxError/.test(V.jsCoupe.cadre), JSON.stringify(V.jsCoupe));
  verifier('un Javascript d’avant, qui ne s’annonce pas : la page s’affiche, et le filet d’Index le nomme',
    /sur 60 plans/.test(V.jsAncien.phrase) && !V.jsAncien.erreurs.length &&
    /Les fichiers du tableau de bord ne concordent pas\. Javascript ne vient pas de la même livraison/.test(V.jsAncien.cadre) &&
    !/pas pu démarrer/.test(V.jsAncien.cadre), JSON.stringify(V.jsAncien));
  verifier('un Javascript coupé SANS sa fin (le <script> reste ouvert) : le filet en tête d’Index parle quand même',
    /La page n’a pas pu démarrer\. Le fichier Javascript semble incomplet/.test(V.jsCoupeSansFin.cadre), JSON.stringify(V.jsCoupeSansFin));
  verifier('des Styles coupés (le <style> reste ouvert et avale la page) : « La page n’a pas pu se construire », Styles nommé',
    /La page n’a pas pu se construire\. Le fichier Styles \(ou Index\) semble incomplet/.test(V.stylesCoupe.cadre), JSON.stringify(V.stylesCoupe));
  verifier('un Index très ancien, sans filet, qui arrête le script dès ses premières lignes : le filet du Javascript nomme Index',
    V.indexTresAncien.erreurs.length === 1 && V.indexTresAncien.phrase === '—' &&
    /La page n’a pas pu s’afficher\. Cause la plus probable : Index ne vient pas de la même livraison/.test(V.indexTresAncien.cadre),
    JSON.stringify(V.indexTresAncien));
  verifier('le Javascript collé deux fois : la seconde copie ne démarre pas, elle le dit',
    /sur 60 plans/.test(V.jsDeuxFois.phrase) && /Le fichier Javascript contient deux copies/.test(V.jsDeuxFois.cadre), JSON.stringify(V.jsDeuxFois));
  verifier('une copie d’avant laissée sous la nouvelle : comptée au chargement, et dite',
    /Le fichier Javascript contient deux copies/.test(V.jsNeufPuisAncien.cadre), JSON.stringify(V.jsNeufPuisAncien));
  verifier('des Styles d’avant : nommés',
    /sur 60 plans/.test(V.stylesAncien.phrase) && /Styles ne vient pas de la même livraison/.test(V.stylesAncien.cadre), V.stylesAncien.cadre);
  verifier('un Code.gs d’une autre livraison : nommé',
    /sur 60 plans/.test(V.codeAncien.phrase) && /Code ne vient pas de la même livraison/.test(V.codeAncien.cadre), V.codeAncien.cadre);
  verifier('une autre erreur au démarrage : dite en tête de page, sans la valeur citée dans le message',
    V.erreur.phrase === '—' && /La page n’a pas pu s’afficher\. Une erreur l’a arrêtée/.test(V.erreur.cadre) &&
    /panne simulée "…"/.test(V.erreur.cadre) && !/HDK-SECRET-42/.test(V.erreur.cadre), JSON.stringify(V.erreur));

  /* Des références en double sur la page : une fois chacune, dites. */
  construire({ lignes: 10, historique: false, sortie: 'apercu-doublons.html',
               retoucher: v => { v.push(v[5].slice(), v[6].slice()); } });
  const pDbl = await ctxGates.newPage();
  pDbl.on('pageerror', e => erreursJS.push('doublons : ' + e.message));
  await pDbl.goto('file://' + path.join(racineRepo, 'apercu-doublons.html'));
  await pDbl.waitForTimeout(900);
  const vDbl = await pDbl.evaluate(() => ({
    phrase: document.getElementById('phrase').textContent.replace(/\s+/g, ' '),
    alerte: document.getElementById('alerte-valeurs').hidden ? '' : document.getElementById('alerte-valeurs').textContent,
    lignes: document.querySelectorAll('#corps-tableau tr').length
  }));
  await pDbl.close();
  fs.unlinkSync(path.join(racineRepo, 'apercu-doublons.html'));
  /* construire() pose au moins 12 plans : 12 références, 14 lignes. */
  verifier('des références en double : la page compte 12 plans, pas 14 lignes, et dit que seule la première ligne compte',
    / sur 12 plans/.test(vDbl.phrase) && vDbl.lignes === 12 && /2 lignes répètent une référence déjà vue\. Seule la première ligne/.test(vDbl.alerte),
    JSON.stringify(vDbl));

  /* Un classeur réglé en anglais (États-Unis) : des dates mois/jour. La
     colonne dit son ordre ; lues jour/mois, 41 % des plans tombaient dans le
     mauvais mois. */
  const enUS = v => v.forEach((l, i) => { if (i >= 4 && /^\d{4}-\d{2}-\d{2}$/.test(l[7])) { const d = l[7].split('-'); l[7] = d[1] + '/' + d[2] + '/' + d[0]; } });
  construire({ lignes: 40, historique: false, sortie: 'apercu-dates-us.html', retoucher: enUS });
  const pUS = await ctxGates.newPage();
  pUS.on('pageerror', e => erreursJS.push('dates US : ' + e.message));
  await pUS.goto('file://' + path.join(racineRepo, 'apercu-dates-us.html'));
  await pUS.waitForTimeout(900);
  const moisUS = await pUS.evaluate(() => window.__anneeEtMois('03/04/2026').mois);
  await pUS.close();
  fs.unlinkSync(path.join(racineRepo, 'apercu-dates-us.html'));
  verifier('des dates écrites mois/jour (classeur « États-Unis ») se lisent mois/jour ; celles d’un classeur français, jour/mois',
    moisUS === 3 && V.moisFr === 4, moisUS + ' / ' + V.moisFr);

  /* Le Diagnostic lit les mêmes marques dans les fichiers du projet. */
  const diagFichiers = contenus => chargerServeur(gates.classeur, {}, contenus).diagnostic();
  const vrais = { Index: lireFichier('Index.html'), Styles: lireFichier('Styles.html'), Javascript: lireFichier('Javascript.html') };
  const diagOk = diagFichiers(vrais);
  verifier('le Diagnostic : « Livraison ' + ED + ' : Code, Index, Styles et Javascript concordent, et sont entiers »',
    diagOk.indexOf('✓ Livraison ' + ED + ' : Code, Index, Styles et Javascript concordent, et sont entiers.') !== -1 && /Tout est en place/.test(diagOk));
  const diagIndex = diagFichiers(Object.assign({}, vrais, { Index: vrais.Index.replace("window.SUIVI_FWD_LIVRAISON_INDEX = '" + ED + "';", '') }));
  verifier('le Diagnostic nomme un Index d’avant, et ne conclut plus « Tout est en place »',
    /✗ « Index » ne vient pas de la même livraison que Code \(sans livraison marquée/.test(diagIndex) &&
    /Les fichiers collés ne concordent pas .* la page s'ouvrira sur un cadre qui dit quoi recoller/.test(diagIndex) && !/Tout est en place/.test(diagIndex) &&
    !/À vérifier avant de présenter/.test(diagIndex), diagIndex.slice(0, 900));
  const jsCoupe = vrais.Javascript.slice(0, Math.floor(vrais.Javascript.length * 0.6));
  const diagCoupe = diagFichiers(Object.assign({}, vrais, { Javascript: jsCoupe }));
  verifier('le Diagnostic reconnaît un Javascript collé en partie',
    /✗ « Javascript » est incomplet : sa fin manque \(\d+ caractères\)/.test(diagCoupe) && !/Tout est en place/.test(diagCoupe),
    diagCoupe.slice(0, 900));
  const jsSansFermeture = vrais.Javascript.replace(/<\/script>\s*$/, '');
  const diagSansFermeture = diagFichiers(Object.assign({}, vrais, { Javascript: jsSansFermeture }));
  verifier('… et un Javascript à qui ne manque que sa dernière ligne « </script> »',
    /✗ « Javascript » est incomplet : sa fin manque/.test(diagSansFermeture), diagSansFermeture.slice(0, 700));
  const diagDouble = diagFichiers(Object.assign({}, vrais, { Javascript: vrais.Javascript + vrais.Javascript }));
  verifier('… un Javascript collé deux fois', /✗ « Javascript » contient deux copies — collé sans tout effacer \?/.test(diagDouble));
  const diagStylesCoupe = diagFichiers(Object.assign({}, vrais, { Styles: vrais.Styles.slice(0, Math.floor(vrais.Styles.length / 2)) }));
  verifier('… des Styles coupés', /✗ « Styles » est incomplet/.test(diagStylesCoupe) && /cadre qui dit quoi recoller/.test(diagStylesCoupe));
  const diagIndexSansJs = diagFichiers(Object.assign({}, vrais, { Index: vrais.Index.replace("<?!= include('Javascript'); ?>", '') }));
  verifier('… un Index qui n’inclut plus le Javascript', /✗ « Index » est incomplet ou abîmé/.test(diagIndexSansJs));

  /* À l'ouverture : la page — sauf s'il manque un fichier au projet, où une
     page dit lequel recréer. Le reste, la page le dit elle-même en tête : on ne
     bloque pas sur une supposition (au bureau, un contrôle trompé par les
     commentaires qu'Apps Script retire a bloqué une page saine). */
  const servie = contenus => chargerServeur(gates.classeur, {}, contenus);
  const cBon = servie(vrais);
  verifier('ouverture, fichiers concordants : la page du tableau de bord', cBon.doGet({ parameter: {} }).source.modele === 'Index');
  const cIndex = servie(Object.assign({}, vrais, { Index: vrais.Index.replace("window.SUIVI_FWD_LIVRAISON_INDEX = '" + ED + "';", '') }));
  verifier('ouverture, Index d’avant : la page s’ouvre — c’est elle qui le dit en tête', cIndex.doGet({ parameter: {} }).source.modele === 'Index');
  const cCoupe = servie(Object.assign({}, vrais, { Javascript: jsSansFermeture }));
  cCoupe.ouvrirTableauDeBord();
  verifier('ouverture depuis le menu, Javascript coupé : la page s’ouvre, son filet dira « incomplet »',
    cCoupe.__dialogue && cCoupe.__dialogue.source.modele === 'Index');
  /* Ce qu'Apps Script rend d'un fichier : son texte SANS SES COMMENTAIRES. Un
     projet sain, relu ainsi, doit rester sain — la marque de fin comprise. */
  const sansCommentaires = t => t.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
  const commeAppsScript = { Index: sansCommentaires(vrais.Index), Styles: sansCommentaires(vrais.Styles), Javascript: sansCommentaires(vrais.Javascript) };
  const cRelu = servie(commeAppsScript);
  verifier('les fichiers relus comme Apps Script les rend (sans commentaires) : entiers, concordants, la page s’ouvre',
    /✓ Livraison [0-9a-f]{7} : Code, Index, Styles et Javascript concordent, et sont entiers\./.test(cRelu.diagnostic()) &&
    cRelu.doGet({ parameter: {} }).source.modele === 'Index', cRelu.diagnostic().split('\n').filter(l => /Javascript|Styles|Index/.test(l)).join(' / '));
  /* Et le Javascript de la livraison 247cc3e (sa marque de fin était un
     commentaire, qu'Apps Script retire) : entier aussi. */
  const js247 = sansCommentaires(vrais.Javascript.replace(/\nwindow\.SUIVI_FWD_FIN = '[0-9a-f]+';\n/, '\n/* suivi-fwd : fin du fichier Javascript, livraison 247cc3e */\n'));
  verifier('… et le Javascript d’avant, dont la marque de fin était un commentaire, n’est plus dit « incomplet »',
    !/« Javascript » est incomplet/.test(servie(Object.assign({}, commeAppsScript, { Javascript: js247 })).diagnostic()));
  const cStyles = servie(Object.assign({}, vrais, { Styles: vrais.Styles.replace('"' + ED + '"', '"abcdef0"') }));
  verifier('ouverture, Styles d’une autre livraison mais entiers : la page s’ouvre (elle le dit en tête)',
    cStyles.doGet({ parameter: {} }).source.modele === 'Index');
  const squelette = t => '<!DOCTYPE html>\n<html>\n  <head>\n    <base target="_top">\n  </head>\n  <body>\n' + t + '\n  </body>\n</html>\n';
  const cSquelette = servie(Object.assign({}, vrais, { Javascript: squelette(vrais.Javascript), Styles: squelette(vrais.Styles) }));
  verifier('le squelette d’un fichier créé par « + → HTML » autour du code : la page s’ouvre (le Diagnostic le signale sans bloquer)',
    cSquelette.doGet({ parameter: {} }).source.modele === 'Index' && /porte du texte hors de « <script>/.test(cSquelette.diagnostic()));
  const cSansFichier = servie({ Index: vrais.Index, Styles: vrais.Styles });
  const pSans = cSansFichier.doGet({ parameter: {} }).source.html || '';
  verifier('ouverture, Javascript introuvable : la page le dit', /« Javascript » est introuvable/.test(pSans), pSans.slice(0, 300));
  const diagStyles = diagFichiers(Object.assign({}, vrais, { Styles: vrais.Styles.replace('"' + ED + '"', '"abcdef0"') }));
  verifier('et des Styles d’une autre livraison', /✗ « Styles » ne vient pas de la même livraison que Code \(livraison abcdef0, Code : /.test(diagStyles));

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
