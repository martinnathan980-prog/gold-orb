/* Batterie de l'add-on : on fait tourner le VRAI Code.gs contre un classeur en
   mémoire, puis on charge la page qu'Apps Script rendrait, dans un vrai
   navigateur. Ce qui est testé ici, c'est la chaîne feuille → serveur → écran. */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const vm = require('vm');
const { construire, chargerServeur } = require('./build-addon');
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

function serveurSur(valeurs, proprietes, fichiers) {
  const classeur = new Classeur([new Feuille('Données', valeurs)]);
  return { contexte: chargerServeur(classeur, proprietes || {}, fichiers), classeur: classeur };
}

(async () => {
  // =================================================================
  section('Détection des colonnes');
  const { paquet } = construire();
  verifier('le paquet est valide', paquet.ok === true, paquet.message);
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

  const colFwd = mGates.colonnes.find(c => c.cle === 'avancement');
  verifier('la bonne colonne d\'avancement est retenue',
    colFwd && colFwd.titre === 'Avancement', colFwd && colFwd.titre);
  verifier('elle est bien celle du groupe « Réalisation FWD »',
    colFwd && colFwd.groupe === 'Réalisation FWD', colFwd && colFwd.groupe);
  verifier('ni « Avancement Définition Electrique » ni « Avancement Concept Harnais »',
    colFwd && !/Définition|Concept/.test(colFwd.titre));

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
    JSON.stringify(titresDim) === JSON.stringify(['ATA', 'Avancement', 'CC',
      'Chapitre', 'ECP']), JSON.stringify(titresDim));
  verifier('l\'ATA est ouvert par défaut', mGates.dimParDefaut === 'ata', mGates.dimParDefaut);
  verifier('l\'« Avancement » retenu est celui du groupe FWD',
    mGates.colonnes.find(c => c.cle === mGates.clesDim[1]).groupe === 'Réalisation FWD');
  verifier('la vue essentielle tient en moins de dix colonnes',
    mGates.clesEssentielles.length <= 10 && mGates.clesEssentielles.length >= 5,
    String(mGates.clesEssentielles.length));
  verifier('elle contient la référence, l\'avancement et la date',
    ['reference', 'avancement', mGates.cleDate].every(c => mGates.clesEssentielles.indexOf(c) !== -1),
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
  /* L'avancement FWD lui-même est une dimension demandée : regrouper par sa
     valeur brute montre d'un coup les façons de l'écrire, donc les saisies
     qui divergent. */
  verifier('l\'avancement FWD est bien proposé comme dimension',
    titresDim.indexOf('Avancement') !== -1);
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

  verifier('les 91 colonnes des blocs répétés s\'ouvrent repliées',
    mGates.colonnes.filter(c => c.masqueeAuDepart).length === 91,
    String(mGates.colonnes.filter(c => c.masqueeAuDepart).length));
  verifier('la ligne sans référence est bien celle du parasite',
    mGates.plans.every(p => /^UD-/.test(p.reference)),
    JSON.stringify(mGates.plans.filter(p => !/^UD-/.test(p.reference)).map(p => p.reference).slice(0, 3)));
  verifier('les dates ISO avec heure sont reconnues comme dates',
    mGates.plans.every(p => /^\d{4}-\d{2}-\d{2}T/.test(p[mGates.cleDate])));
  verifier('aucune colonne utile n\'est repliée',
    !mGates.colonnes.filter(c => c.masqueeAuDepart)
      .some(c => ['reference', 'avancement'].indexOf(c.cle) !== -1));

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
  verifier('un forçage qui ne tombe sur rien retombe sur la détection',
    forceInconnu.contexte.construireModele().colonnes.find(c => c.cle === 'avancement').titre === 'Avancement');

  // L'archivage doit tenir sur 137 colonnes et treize blocs répétés.
  gates.contexte.enregistrerInstantaneHebdo();
  const hg = gates.contexte.getHistorique(gates.classeur);
  verifier('le relevé s\'archive sur la structure réelle',
    hg.length === 1 && hg[0].total === 186 &&
    hg[0].termine + hg[0].encours + hg[0].afaire + hg[0].vide === 186);
  verifier('les comptes par ATA sont archivés',
    hg[0].groupes.ata && Object.keys(hg[0].groupes.ata).length >= 5,
    JSON.stringify(Object.keys(hg[0].groupes.ata || {})));

  const rapportGates = gates.contexte.diagnostic();
  verifier('le diagnostic nomme la colonne FWD et son groupe',
    /Avancement FWD : colonne « Avancement », groupe « Réalisation FWD »/.test(rapportGates),
    rapportGates.split('\n').find(l => /Avancement FWD/.test(l)));
  verifier('il liste les colonnes d\'analyse en clair',
    /Analyse par : .*ATA/.test(rapportGates), rapportGates.split('\n').find(l => /Analyse par/.test(l)));
  verifier('il signale les lignes ignorées et les colonnes repliées',
    /1 ligne\(s\) sans référence ignorée/.test(rapportGates) &&
    /91 colonnes repliées/.test(rapportGates));

  // =================================================================
  section('Classement des quatre états, côté serveur');
  const { contexte } = serveurSur(feuilleExemple(10));
  const cas = [
    ['100%', 'termine'], ['100 %', 'termine'], ['Terminé', 'termine'], ['TERMINE', 'termine'],
    ['achevé', 'termine'], ['soldé', 'termine'],
    ['50%', 'encours'], ['75 %', 'encours'], ['En cours', 'encours'], ['0,5', 'encours'],
    ['À faire', 'afaire'], ['à faire', 'afaire'], ['A FAIRE', 'afaire'], ['0%', 'afaire'],
    ['Non commencé', 'afaire'],
    ['', 'vide'], ['   ', 'vide'], ['-', 'vide'], [null, 'vide'], [undefined, 'vide']
  ];
  let tousBons = true, mauvais = '';
  cas.forEach(([valeur, attendu]) => {
    const obtenu = contexte.classerFWD(valeur);
    if (obtenu !== attendu) { tousBons = false; mauvais += ' ' + JSON.stringify(valeur) + '→' + obtenu; }
  });
  verifier('les vingt cas de classement tombent juste', tousBons, mauvais);
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
  const h = serveurSur(feuilleExemple(50));
  const r1 = h.contexte.enregistrerInstantaneHebdo();
  verifier('un relevé est écrit', r1.ok && r1.compte.total === 50, JSON.stringify(r1.semaine));
  verifier('l\'onglet historique est créé et masqué',
    h.classeur.getSheetByName('Historique_FWD') !== null &&
    h.classeur.getSheetByName('Historique_FWD').isSheetHidden());
  const avant = h.classeur.getSheetByName('Historique_FWD').valeurs.length;
  h.contexte.enregistrerInstantaneHebdo();
  h.contexte.enregistrerInstantaneHebdo();
  verifier('réimporter la même semaine ne crée pas de doublon',
    h.classeur.getSheetByName('Historique_FWD').valeurs.length === avant,
    avant + ' → ' + h.classeur.getSheetByName('Historique_FWD').valeurs.length);
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

  // Une feuille énorme ne doit pas faire exploser la cellule d'historique.
  const gros = serveurSur(feuilleExemple(4000));
  gros.contexte.enregistrerInstantaneHebdo();
  const ligneGrosse = gros.classeur.getSheetByName('Historique_FWD').valeurs[1];
  verifier('4 000 plans s\'archivent sans dépasser la taille d\'une cellule',
    String(ligneGrosse[7]).length <= 45000 && String(ligneGrosse[8]).length <= 45000,
    'dimensions ' + String(ligneGrosse[7]).length + ' car., plans ' + String(ligneGrosse[8]).length + ' car.');
  verifier('les comptes restent justes sur 4 000 plans', Number(ligneGrosse[2]) === 4000);

  // =================================================================
  section('Historique : relecture tolérante');
  const abime = serveurSur(feuilleExemple(20));
  abime.contexte.enregistrerInstantaneHebdo();
  const f = abime.classeur.getSheetByName('Historique_FWD');
  f.valeurs.push(['pas une semaine', new Date(), 1, 1, 0, 0, 0, '{', '{']);
  f.valeurs.push(['', '', '', '', '', '', '', '', '']);
  f.valeurs.push(['2026-S02', new Date(), 5, 1, 1, 1, 2, 'JSON cassé {[', 'idem']);
  const relu = abime.contexte.getHistorique(abime.classeur);
  verifier('les lignes illisibles sont ignorées', relu.length === 2, relu.length + ' relevés');
  verifier('un JSON cassé ne fait pas tomber la lecture',
    relu[0].semaine === '2026-S02' && relu[0].plans === null && JSON.stringify(relu[0].groupes) === '{}');

  // =================================================================
  section('Jalons partagés');
  const j = serveurSur(feuilleExemple(10));
  const ecrits = j.contexte.sauverJalons([
    { semaine: '2026-s8', texte: '  Revue de définition  ' },
    { semaine: '2026-S02', texte: '' },
    { semaine: 'nawak', texte: 'ignoré' },
    null,
    { semaine: '2026-S40', texte: 'X'.repeat(200) }
  ]);
  verifier('les entrées invalides sont écartées', ecrits.length === 3, String(ecrits.length));
  verifier('les jalons sont triés par semaine',
    ecrits.map(x => x.semaine).join(',') === '2026-S02,2026-S08,2026-S40', ecrits.map(x => x.semaine).join(','));
  verifier('un texte vide reçoit un libellé', ecrits[0].texte === 'Jalon');
  verifier('un texte à rallonge est coupé à 60 caractères', ecrits[2].texte.length === 60);
  verifier('chaque jalon reçoit un identifiant', ecrits.every(x => !!x.id));
  verifier('les jalons se relisent', j.contexte.getJalons().length === 3);
  const idPremier = ecrits[0].id;
  j.contexte.sauverJalons(ecrits.slice(0, 2));
  verifier('supprimer revient à renvoyer la liste amputée', j.contexte.getJalons().length === 2);
  verifier('les identifiants sont conservés', j.contexte.getJalons()[0].id === idPremier);
  const trop = [];
  for (let i = 1; i <= 60; i++) trop.push({ semaine: '2026-S' + String((i % 52) + 1).padStart(2, '0'), texte: 'j' + i });
  verifier('le nombre de jalons est plafonné', j.contexte.sauverJalons(trop).length === 40);
  const casse = serveurSur(feuilleExemple(5), { SUIVI_FWD_JALONS: 'ceci n\'est pas du JSON' });
  verifier('une propriété illisible renvoie une liste vide',
    Array.isArray(casse.contexte.getJalons()) && casse.contexte.getJalons().length === 0);

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
  verifier('une feuille vide renvoie une erreur lisible, pas une exception',
    pVide.ok === false && /vide/i.test(pVide.message), pVide.message);

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
  verifier('il passe aussi par l\'alerte à l\'écran', dOk.contexte.__alertes.length === 1);

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
  verifier('une feuille vide est diagnostiquée',
    /L'onglet est vide/.test(dVide.contexte.diagnostic()));

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
    etats: [...document.querySelectorAll('.etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    colonnes: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    dims: [...document.querySelectorAll('#dim-critique option')].map(o => o.value),
    dimActive: document.getElementById('dim-critique').value,
    titre: document.getElementById('titre-groupe').textContent,
    groupes: document.querySelectorAll('.critique-ligne').length,
    totauxGroupes: [...document.querySelectorAll('.critique-total')].map(t => +t.textContent),
    jalons: document.querySelectorAll('.jalon-supp').length,
    releves: document.querySelectorAll('.zone-clic').length > 0,
    importe: document.getElementById('import').textContent
  }));
  verifier('la semaine affichée vient du dernier relevé', /^Semaine \d+$/.test(vu.semaine), vu.semaine);
  verifier('les dates de la semaine sont écrites en toutes lettres',
    /^du \d+ .* \d{4}$/.test(vu.dates), vu.dates);
  verifier('les quatre états totalisent les 186 plans',
    vu.etats.reduce((a, b) => a + b, 0) === 186, JSON.stringify(vu.etats));
  verifier('aucun état n\'est vide de sens', vu.etats.every(n => n >= 0));
  verifier('les en-têtes du tableau sont ceux de la feuille, référence en tête',
    vu.colonnes[0] === 'Référence UD' && vu.colonnes.indexOf('Avancement FWD') !== -1,
    JSON.stringify(vu.colonnes));
  verifier('les 186 lignes sont dans le tableau', vu.lignes === 186, String(vu.lignes));
  verifier('le sélecteur de dimension propose les colonnes détectées', vu.dims.length >= 3, JSON.stringify(vu.dims));
  verifier('l\'ATA est ouvert par défaut', vu.dimActive === 'ata', vu.dimActive);
  verifier('le titre nomme la dimension', /par ATA/.test(vu.titre), vu.titre);
  verifier('le bloc par ATA est rempli', vu.groupes >= 2, String(vu.groupes));
  verifier('la somme des plans par groupe fait 186',
    vu.totauxGroupes.reduce((a, b) => a + b, 0) === 186, String(vu.totauxGroupes.reduce((a, b) => a + b, 0)));
  verifier('le graphique a de quoi tracer', vu.releves);
  verifier('la ligne d\'import annonce les relevés archivés', /relevés archivés/.test(vu.importe), vu.importe);

  // Une cellule contenant une balise fermante ne doit pas couper la page en deux.
  verifier('une balise fermante dans une cellule ne casse pas la page',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length === 186 &&
      !!document.querySelector('svg.graphe') &&
      document.querySelectorAll('.critique-ligne').length > 0 &&
      document.querySelectorAll('.etat-n').length === 4));
  verifier('et elle s\'affiche comme du texte dans le tableau',
    await p.evaluate(() => [...document.querySelectorAll('#corps-tableau td')]
      .some(td => td.textContent.includes('</script>'))));

  // Le chiffre affiché doit correspondre à ce que le serveur a compté.
  const attendu = { termine: 0, encours: 0, afaire: 0, vide: 0 };
  paquet.plans.forEach(pl => { attendu[contexte.classerFWD(pl.avancement)]++; });
  verifier('l\'écran et le serveur comptent pareil',
    vu.etats[0] === attendu.termine && vu.etats[1] === attendu.encours &&
    vu.etats[2] === attendu.afaire && vu.etats[3] === attendu.vide,
    JSON.stringify(vu.etats) + ' vs ' + JSON.stringify(attendu));

  // Les interactions essentielles marchent-elles sur des données réelles ?
  await p.fill('#recherche', 'UD-24'); await p.waitForTimeout(400);
  verifier('la recherche fonctionne sur les données de la feuille',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) < 186);
  await p.fill('#recherche', ''); await p.waitForTimeout(400);
  await p.click('.etat-btn[data-etat="vide"]'); await p.waitForTimeout(400);
  verifier('le filtre « non renseignés » ne garde que des cellules vides',
    await p.evaluate(() => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => /Avancement FWD/.test(t.textContent));
      return [...document.querySelectorAll('#corps-tableau tr')]
        .every(tr => /^(|—|non renseigné|-)$/i.test(tr.children[i].textContent.trim()));
    }));
  await p.click('.etat-btn[data-etat="vide"]'); await p.waitForTimeout(300);
  await p.click('button[data-aide] >> nth=0').catch(() => {}); await p.waitForTimeout(400);
  verifier('le panneau d\'explication s\'ouvre sur des chiffres réels',
    await p.evaluate(() => {
      const el = document.getElementById('panneau-fin');
      return !!el && /Exemple/.test(el.textContent);
    }));
  await p.evaluate(() => { const b = document.getElementById('tout-effacer'); if (b) b.click(); });
  await p.waitForTimeout(400);
  await p.selectOption('#dim-critique', vu.dims[vu.dims.length - 1]); await p.waitForTimeout(500);
  const plusDim = await p.$('#plus-groupes');
  if (plusDim) { await plusDim.click(); await p.waitForTimeout(400); }
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
    etats: [...document.querySelectorAll('.etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    visibles: document.querySelectorAll('tr.titres th').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    debord: document.documentElement.scrollWidth - window.innerWidth,
    dimActive: document.getElementById('dim-critique').value,
    titre: document.getElementById('titre-groupe').textContent,
    groupes: document.querySelectorAll('.critique-ligne').length,
    totaux: [...document.querySelectorAll('.critique-total')].reduce((s, t) => s + (+t.textContent), 0),
    colFWD: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()).indexOf('Avancement')
  }));
  verifier('les 186 plans sont là malgré les 138 colonnes', vg.lignes === 186, String(vg.lignes));
  verifier('les quatre états totalisent 186', vg.etats.reduce((a, b) => a + b, 0) === 186, JSON.stringify(vg.etats));
  verifier('le tableau s\'ouvre sur 47 colonnes, pas 138', vg.visibles === 47, String(vg.visibles));
  verifier('la colonne « Avancement » est visible au départ', vg.colFWD !== -1, String(vg.colFWD));
  verifier('la référence figée ouvre le tableau, malgré la colonne vide n° 1',
    await pg.evaluate(() => {
      const th = document.querySelector('tr.titres th');
      return th.textContent.trim() === 'Référence UD' && th.classList.contains('col-fige');
    }));
  verifier('pas de débordement horizontal de la page', vg.debord <= 2, vg.debord + ' px');
  verifier('l\'ATA est ouvert par défaut', vg.dimActive === 'ata' && /par ATA/.test(vg.titre), vg.titre);
  verifier('tous les ATA sont comptés', vg.totaux === 186 && vg.groupes >= 5,
    vg.groupes + ' groupes, ' + vg.totaux + ' plans');

  await pg.click('#tout-colonnes').catch(async () => {
    await pg.click('#bascule-colonnes'); await pg.waitForTimeout(250); await pg.click('#tout-colonnes');
  });
  await pg.waitForTimeout(600);
  verifier('« tout afficher » ramène les 138 colonnes',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === 138,
    String(await pg.evaluate(() => document.querySelectorAll('tr.titres th').length)));
  verifier('et la page tient toujours', await pg.evaluate(() =>
    document.documentElement.scrollWidth - window.innerWidth <= 2 &&
    document.querySelectorAll('#corps-tableau tr').length === 186));

  // =================================================================
  section('Journal des changements');
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
  verifier('elle est la seule ouverte d\'emblée',
    jrn.ouvertes[0] === 'true' && jrn.ouvertes.slice(1).every(v => v === 'false'),
    JSON.stringify(jrn.ouvertes));
  verifier('le résumé est écrit en français correct',
    jrn.resumes.every(r => !/en en cour|passés en terminé/.test(r)) &&
    jrn.resumes.some(r => /terminés?|passés? en cours|repassés? à faire/.test(r)),
    JSON.stringify(jrn.resumes[0]));
  verifier('chaque ligne nomme le plan et son passage',
    /UD-/.test(jrn.premiere || ''), jrn.premiere);
  verifier('les états sont au singulier dans une flèche',
    !/Terminés\s*$/.test(jrn.premiere || '') , jrn.premiere);

  // Replier / déplier
  await pg.click('.journal-plier >> nth=0'); await pg.waitForTimeout(350);
  verifier('replier une semaine cache sa liste',
    await pg.evaluate(() => document.querySelectorAll('.journal-liste').length === 0));
  await pg.click('.journal-plier >> nth=1'); await pg.waitForTimeout(350);
  verifier('déplier une autre semaine montre la sienne',
    await pg.evaluate(() => document.querySelectorAll('.journal-liste').length === 1));

  // Filtrer par type de passage
  await pg.click('#filtre-journal button[data-journal="termine"]'); await pg.waitForTimeout(400);
  verifier('le filtre « Terminés » ne laisse que des passages en terminé',
    await pg.evaluate(() => [...document.querySelectorAll('.journal-ligne .vers')]
      .every(v => /Terminé/.test(v.textContent))));
  verifier('et les résumés ne parlent plus que de terminés',
    await pg.evaluate(() => [...document.querySelectorAll('.journal-tete .resume')]
      .every(r => !/passé|repassé|effacé/.test(r.textContent))));
  await pg.click('#filtre-journal button[data-journal=""]'); await pg.waitForTimeout(400);

  // Cliquer un plan filtre le tableau sur lui
  await pg.click('.journal-plier >> nth=0'); await pg.waitForTimeout(300);
  const refCliquee = await pg.evaluate(() => document.querySelector('.journal-ligne').dataset.ref);
  await pg.click('.journal-ligne >> nth=0'); await pg.waitForTimeout(600);
  verifier('cliquer un plan du journal réduit le tableau à ce plan',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 1,
    String(await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length)));
  verifier('et c\'est bien le bon plan',
    await pg.evaluate(r => document.querySelector('#corps-tableau td').textContent.trim() === r, refCliquee));
  await pg.click('.journal-ligne >> nth=0'); await pg.waitForTimeout(600);
  verifier('re-cliquer rend les 186 plans',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 186);

  // =================================================================
  section('Filtres rapides : domaine et reconduits');
  const rap = await pg.evaluate(() => ({
    puces: [...document.querySelectorAll('.puce-rapide')].map(b => b.textContent.trim()),
    domaines: [...document.querySelectorAll('.puce-rapide[data-domaine]')].map(b => b.dataset.domaine)
  }));
  verifier('le domaine propose ses valeurs réelles',
    rap.domaines.indexOf('PERSO') !== -1 && rap.domaines.indexOf('BASE/OPTION') !== -1,
    JSON.stringify(rap.domaines));
  verifier('et un « Tous » pour revenir', rap.domaines.indexOf('') !== -1);
  verifier('les terminés reconduits sont comptés',
    rap.puces.some(t => /Terminésreconduits\d+/.test(t.replace(/\s/g, ''))), JSON.stringify(rap.puces));

  await pg.click('.puce-rapide[data-domaine="PERSO"]'); await pg.waitForTimeout(500);
  const nPerso = await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  verifier('filtrer sur un domaine réduit le tableau', nPerso > 0 && nPerso < 186, String(nPerso));
  verifier('et le tableau ne contient que ce domaine',
    await pg.evaluate(() => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.textContent.trim() === 'Domaine');
      return i !== -1 && [...document.querySelectorAll('#corps-tableau tr')]
        .every(tr => tr.children[i].textContent.trim() === 'PERSO');
    }));
  await pg.click('.puce-rapide[data-domaine="PERSO"]'); await pg.waitForTimeout(450);
  verifier('re-cliquer lève le filtre',
    await pg.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === 186);

  await pg.click('.puce-rapide[data-reconduits]'); await pg.waitForTimeout(500);
  verifier('les reconduits ne sont que des plans terminés et vieux',
    await pg.evaluate(() => {
      const ths = [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim());
      const iA = ths.indexOf('Avancement'), iD = ths.indexOf('Date création');
      if (iA === -1 || iD === -1) return false;
      const lignes = [...document.querySelectorAll('#corps-tableau tr')];
      if (!lignes.length) return false;
      return lignes.every(tr => {
        const a = tr.children[iA].textContent.trim().toLowerCase();
        const an = Number((tr.children[iD].textContent.match(/^(\d{4})/) || [])[1]);
        return (/^100|termin/.test(a)) && an <= 2025;
      });
    }));
  await pg.click('.puce-rapide[data-reconduits]'); await pg.waitForTimeout(450);

  // =================================================================
  section('Vue essentielle du tableau');
  const toutes = await pg.evaluate(() => document.querySelectorAll('tr.titres th').length);
  await pg.click('#bascule-essentielles'); await pg.waitForTimeout(600);
  const ess = await pg.evaluate(() => ({
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    presse: document.getElementById('bascule-essentielles').getAttribute('aria-pressed'),
    lignes: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('la vue essentielle ne garde que les colonnes utiles',
    ess.titres.length >= 5 && ess.titres.length <= 10, String(ess.titres.length));
  verifier('la référence ouvre le tableau et l\'avancement y est',
    ess.titres[0] === 'Référence UD' && ess.titres.indexOf('Avancement') !== -1,
    JSON.stringify(ess.titres));
  verifier('la vue essentielle est exactement celle demandée',
    JSON.stringify(ess.titres) === JSON.stringify(['Référence UD', 'Nom Installation', 'ECP',
      'ATA', 'Séquence', 'Validation Définition Electrique', 'Date création', 'Avancement']),
    JSON.stringify(ess.titres));
  verifier('ni Statut iBG ni les blocs répétés n\'y entrent',
    ess.titres.indexOf('Statut iBG') === -1 && ess.titres.indexOf('Validité') === -1);
  verifier('aucun plan n\'est perdu au passage', ess.lignes === 186, String(ess.lignes));
  verifier('le bouton dit qu\'il est enfoncé', ess.presse === 'true');
  await pg.click('#bascule-essentielles'); await pg.waitForTimeout(600);
  verifier('le relâcher remet exactement la disposition d\'avant',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === toutes,
    toutes + ' → ' + (await pg.evaluate(() => document.querySelectorAll('tr.titres th').length)));

  // Une disposition personnalisée doit survivre à l'aller-retour.
  await pg.click('#bascule-colonnes'); await pg.waitForTimeout(250);
  await pg.click('#panneau-colonnes input[data-col="ata"]'); await pg.waitForTimeout(350);
  await pg.click('body', { position: { x: 5, y: 5 } }); await pg.waitForTimeout(250);
  const sansAta = await pg.evaluate(() => document.querySelectorAll('tr.titres th').length);
  await pg.click('#bascule-essentielles'); await pg.waitForTimeout(500);
  await pg.click('#bascule-essentielles'); await pg.waitForTimeout(500);
  verifier('une colonne masquée à la main le reste après l\'aller-retour',
    await pg.evaluate(() => document.querySelectorAll('tr.titres th').length) === sansAta,
    sansAta + ' → ' + (await pg.evaluate(() => document.querySelectorAll('tr.titres th').length)));
  await pg.click('#bascule-colonnes'); await pg.waitForTimeout(250);
  await pg.click('#tout-colonnes'); await pg.waitForTimeout(400);
  await pg.click('body', { position: { x: 5, y: 5 } }); await pg.waitForTimeout(250);

  // =================================================================
  section('Bandeau des filtres actifs');
  await pg.evaluate(() => { const b = document.getElementById('tout-effacer'); if (b) b.click(); });
  await pg.waitForTimeout(400);
  verifier('aucun bandeau tant que rien n\'est filtré',
    await pg.evaluate(() => document.getElementById('filtres-actifs').hidden));

  await pg.click('.etat-btn[data-etat="encours"]'); await pg.waitForTimeout(350);
  await pg.click('.puce-rapide[data-domaine="PERSO"]'); await pg.waitForTimeout(350);
  await pg.fill('#recherche', 'UD-24'); await pg.waitForTimeout(400);
  const jetons = await pg.evaluate(() => [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()));
  verifier('chaque filtre posé devient un jeton nommé', jetons.length === 3, JSON.stringify(jetons));
  verifier('le jeton dit quelle colonne et quelle valeur',
    jetons.some(t => /État : En cours/.test(t)) && jetons.some(t => /Domaine : PERSO/.test(t)) &&
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
  section('Liste des UD sous un groupe');
  const grosGroupe = await pg.evaluate(() => {
    const l = [...document.querySelectorAll('.critique-ligne')];
    l.sort((a, b) => +b.querySelector('.critique-total').textContent - +a.querySelector('.critique-total').textContent);
    return l[0].dataset.groupe;
  });
  await pg.click(`.critique-ligne[data-groupe="${grosGroupe}"]`); await pg.waitForTimeout(600);
  const ud = await pg.evaluate(() => ({
    jetons: [...document.querySelectorAll('.jeton-ud[data-ud]')].map(b => b.textContent.trim()),
    entete: (document.querySelector('.groupe-refs .entete') || {}).textContent || '',
    etats: [...document.querySelectorAll('.jeton-ud[data-ud] .pastille')].map(e => e.className),
    tableau: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('choisir un groupe déplie ses références', ud.jetons.length > 0, String(ud.jetons.length));
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
    await pg.evaluate(r => document.querySelector('#corps-tableau td').textContent.trim() === r, refUD));
  await pg.click('#tout-effacer'); await pg.waitForTimeout(450);

  // =================================================================
  section('Repères du bloc par groupe');
  /* Sans jalon, le bloc n'a que deux colonnes calculées ; avec un jalon, trois.
     Chacune porte son « ? ». */
  const nbAides = await pg.evaluate(() => document.querySelectorAll('button[data-aide]').length);
  const avecJalon = await pg.evaluate(() => !document.getElementById('zone-critique').classList.contains('sans-jalon'));
  verifier('chaque colonne calculée porte son « ? »',
    nbAides === (avecJalon ? 3 : 2), nbAides + ' pour ' + (avecJalon ? 'trois' : 'deux') + ' colonnes');
  await pg.selectOption('#dim-critique', '_anciennete'); await pg.waitForTimeout(500);
  const noteA = await pg.textContent('#indice-dim');
  await pg.selectOption('#dim-critique', '_mois'); await pg.waitForTimeout(500);
  const noteM = await pg.textContent('#indice-dim');
  verifier('l\'ancienneté est expliquée', /tranches/.test(noteA), noteA);
  verifier('le mois de création aussi, et la différence est dite',
    /mois/.test(noteM) && /ancienneté/i.test(noteM), noteM);
  verifier('les deux notes ne disent pas la même chose', noteA !== noteM);
  const bcp = await pg.evaluate(() => ({
    lignes: document.querySelectorAll('.critique-ligne').length,
    plus: !!document.getElementById('plus-groupes')
  }));
  verifier('une dimension à beaucoup de groupes n\'en ouvre qu\'une quinzaine',
    bcp.lignes <= 15, String(bcp.lignes));
  verifier('et propose de voir les autres', bcp.plus);
  await pg.click('#plus-groupes'); await pg.waitForTimeout(500);
  verifier('« voir les autres » les montre tous',
    await pg.evaluate(() => document.querySelectorAll('.critique-ligne').length) > bcp.lignes &&
    await pg.evaluate(() => !document.getElementById('plus-groupes')));
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
  verifier('et donne les références, pas seulement le compte',
    /UD-/.test(texteBulle), texteBulle.slice(0, 120));

  // =================================================================
  section('Aperçu quand l\'historique est vide');
  construire({ gates: true, historique: 'premier', sortie: 'apercu-premier.html' });
  const ctxPremier = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const pp = await ctxPremier.newPage();
  pp.on('pageerror', e => erreursJS.push('premier : ' + e.message));
  pp.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push('premier : ' + m.text()); });
  await pp.goto('file://' + path.join(__dirname, '..', 'apercu-premier.html'));
  await pp.waitForTimeout(1600);

  verifier('avec un seul relevé, le bouton d\'aperçu est proposé',
    await pp.evaluate(() => !document.getElementById('bascule-exemple').hidden));
  verifier('le bandeau n\'est pas là tant qu\'on n\'a rien demandé',
    await pp.evaluate(() => document.getElementById('bandeau-exemple').hidden));
  verifier('le journal explique pourquoi il est vide',
    await pp.evaluate(() => /deuxième archivage/.test(document.getElementById('zone-journal').textContent)));

  const avantEx = await pp.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await pp.click('#bascule-exemple'); await pp.waitForTimeout(800);
  const ex = await pp.evaluate(() => ({
    bandeau: !document.getElementById('bandeau-exemple').hidden,
    texteBandeau: document.getElementById('bandeau-exemple').textContent,
    zones: document.querySelectorAll('.zone-clic').length,
    points: document.querySelectorAll('svg.graphe circle').length,
    presse: document.getElementById('bascule-exemple').getAttribute('aria-pressed'),
    plans: document.querySelectorAll('#corps-tableau tr').length,
    phrase: document.getElementById('phrase').textContent
  }));
  verifier('l\'aperçu trace une vraie courbe', ex.points >= 5, String(ex.points));
  verifier('le bandeau dit que c\'est un exemple',
    ex.bandeau && /exemple/i.test(ex.texteBandeau) && /réel/i.test(ex.texteBandeau));
  verifier('le bouton se marque enfoncé', ex.presse === 'true');
  verifier('le tableau, lui, reste sur les vraies données',
    ex.plans === 186 && /186 plans/.test(ex.phrase), ex.phrase);
  await pp.click('#fermer-exemple'); await pp.waitForTimeout(700);
  verifier('« revenir au réel » remet tout en place',
    await pp.evaluate(() => document.getElementById('bandeau-exemple').hidden &&
      document.getElementById('bascule-exemple').getAttribute('aria-pressed') === 'false'));
  verifier('et le graphique retrouve son cadrage',
    await pp.evaluate(() => document.querySelectorAll('.zone-clic').length) === avantEx,
    avantEx + ' → ' + (await pp.evaluate(() => document.querySelectorAll('.zone-clic').length)));
  verifier('avec cinq relevés, le bouton d\'aperçu ne s\'affiche pas',
    await pg.evaluate(() => document.getElementById('bascule-exemple').hidden));
  await ctxPremier.close();

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
