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
  verifier('les huit colonnes d\'analyse sont celles prévues, dans l\'ordre',
    JSON.stringify(titresDim) === JSON.stringify(['ATA', 'Séquence',
      'Validation Définition Electrique', 'Statut iBG', 'Etape', 'Produit',
      'Chapitre', 'Redraw']), JSON.stringify(titresDim));
  verifier('l\'ATA est ouvert par défaut', mGates.dimParDefaut === 'ata', mGates.dimParDefaut);
  verifier('le « Redraw » retenu est celui du groupe FWD',
    mGates.colonnes.find(c => c.cle === mGates.clesDim[7]).groupe === 'Réalisation FWD');
  verifier('l\'ancienneté s\'ajoute grâce à la date de création',
    mGates.cleDate && mGates.colonnes.find(c => c.cle === mGates.cleDate).titre === 'Date création',
    String(mGates.cleDate));
  verifier('aucune colonne de texte libre n\'est une dimension',
    !titresDim.some(t => /Commentaire|Libellé|Raison|Désignation/i.test(t)), JSON.stringify(titresDim));
  verifier('aucun intitulé répété n\'est une dimension',
    !titresDim.some(t => ['Validité', 'Quantité', 'A traiter par', 'Configuration officielle',
                          'Avancement Définition Electrique', 'Avancement Concept Harnais',
                          'Type'].indexOf(t) !== -1), JSON.stringify(titresDim));
  verifier('ni la référence, ni le FWD, ni la date',
    !titresDim.some(t => ['Référence UD', 'Avancement', 'Date création'].indexOf(t) !== -1));
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
  verifier('les en-têtes du tableau sont ceux de la feuille',
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
  await p.click('#aide-fin').catch(() => {}); await p.waitForTimeout(400);
  verifier('le panneau d\'explication s\'ouvre sur des chiffres réels',
    await p.evaluate(() => {
      const el = document.getElementById('panneau-fin');
      return !!el && /Exemple/.test(el.textContent);
    }));
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
