/**
 * Suivi FWD — tableau de bord des plans d'intégration électrique
 * =============================================================
 * Côté serveur (Google Apps Script).
 *
 * Ce fichier ne fait que sept choses :
 *   1. reconnaître les contrats du classeur : chaque onglet VISIBLE qui n'est
 *      pas un onglet de service est un contrat, et le nom de l'onglet est à la
 *      fois son identifiant et son nom (« X1 ») ;
 *   2. lire l'onglet d'un contrat et en déduire un modèle de colonnes
 *      (aucun nom de colonne n'est écrit en dur : tout vient de l'en-tête) ;
 *   3. classer l'avancement FWD de chaque ligne en quatre états ;
 *   4. entretenir, pour chaque contrat, un historique hebdomadaire réel dans
 *      un onglet masqué « Historique_FWD_<nom du contrat> » — l'archivage
 *      passe sur tous les contrats d'un coup, une ligne par contrat dans son
 *      onglet, et l'historique ne se reconstruit jamais, il s'accumule ;
 *   5. fournir les jalons du programme, fixés ici dans la configuration :
 *      la page les montre, personne ne les modifie à l'écran ;
 *   6. lire, si la configuration en nomme un, l'onglet d'une seconde base à
 *      rapprocher des plans (CONFIG.RAPPROCHEMENT), avec les seules lignes du
 *      contrat — son PSN, les schémas WD — quand l'onglet porte l'extract de
 *      tous les porteurs ; la page fait le reste ;
 *   7. importer, sans Excel, les exports de la semaine posés sur le poste,
 *      chacun dans sa case (menu Suivi FWD → Importer les exports GATES et
 *      SEE) : l'export GATES de chaque contrat dans son onglet, puis le
 *      relevé de la semaine archivé ; l'extract SEE de tous les porteurs,
 *      trié pour chaque contrat qui a un PSN.
 *
 * La page est rendue d'une traite : Index.html injecte le paquet du PREMIER
 * contrat (l'ordre des onglets) au moment de l'évaluation du modèle, sans
 * aller-retour. Les autres contrats se chargent à la demande, quand la
 * lectrice change de contrat : google.script.run → getDonneesPourClient(id).
 *
 * Rétro-compatibilité : un classeur à contrat unique qui porte encore
 * l'ancien onglet « Historique_FWD » tout court continue de s'en servir —
 * rien n'est renommé, rien n'est reconstruit. Le jour où un second onglet de
 * contrat apparaît, cet ancien onglet n'appartient plus à personne : le
 * renommer « Historique_FWD_<nom> » rend ses relevés au contrat qui les a
 * produits (la page et le diagnostic le rappellent ; d'ici là, un contrat
 * sans historique ne s'archive pas, pour ne pas couper l'historique en deux).
 */

/**
 * La livraison. Les quatre fichiers collés dans Apps Script — Code, Index,
 * Styles, Javascript — portent la même édition, posée par la construction
 * (tests/split-prototype.js) : NE PAS LA MODIFIER À LA MAIN. La page et le
 * Diagnostic comparent les quatre : un fichier resté à une livraison
 * précédente, ou coupé au collage, est nommé — au lieu d'une page blanche.
 */
const EDITION = '7962d60';

// =====================================================================
//  CONFIGURATION
// =====================================================================
const CONFIG = {
  /**
   * Nom de l'onglet de données. Vide = chaque onglet visible qui n'est pas un
   * onglet de service est un contrat, nommé comme l'onglet, dans l'ordre des
   * onglets. Renseigné = un seul contrat, cet onglet-là, quoi qu'il y ait à
   * côté.
   */
  FEUILLE_DONNEES: '',

  /**
   * Préfixe des onglets d'historique : celui d'un contrat s'appelle
   * « Historique_FWD_<nom du contrat> ». Tout onglet dont le nom commence par
   * ce préfixe est un onglet de service, jamais un contrat. Un classeur à
   * contrat unique qui porte encore l'onglet « Historique_FWD » tout court le
   * garde tel quel.
   */
  FEUILLE_HISTORIQUE: 'Historique_FWD',

  /**
   * Onglets de service, jamais pris pour des contrats — en plus de ceux du
   * préfixe d'historique et de l'onglet de la seconde base (RAPPROCHEMENT).
   */
  FEUILLES_INTERNES: ['Historique_FWD', 'Paramètres', 'Parametres', 'Config'],

  /** Nombre de lignes scannées en haut de feuille pour trouver la ligne d'en-têtes. */
  LIGNES_SCAN_ENTETE: 8,

  /** Mots-clés qui identifient la ligne d'en-têtes (normalisés, sans accents). */
  MOTS_CLES_ENTETE: ['reference ud', 'reference', 'ata', 'nom installation'],

  /**
   * Les jalons du programme, affichés sur le graphique et utilisés pour
   * l'« effort demandé » du bloc par groupe (le prochain jalon à venir fait
   * l'échéance). Ils ne s'éditent pas à l'écran : c'est ici qu'on les
   * change. Semaine ISO « AAAA-SNN », texte de 60 caractères au plus.
   *
   * perimetre (facultatif) : la valeur de la colonne de domaine à laquelle
   * le jalon s'applique — « BASE/OPTION » ou « PERSO », écrite comme dans
   * l'extract (casse et accents indifférents). Sous ce périmètre, c'est ce
   * jalon qui fait l'échéance ; sous l'autre, il est dessiné en retrait et
   * ne compte pas ; sur « Tout », tous comptent. Sans perimetre, le jalon
   * vaut pour tous les plans. Le Diagnostic dit si chaque valeur est bien
   * l'une de celles de la colonne.
   *
   * date (facultatif) : le jour exact, « AAAA-MM-JJ » ou « JJ/MM/AAAA ».
   * La page compte les jours jusqu'à lui ; sans date, jusqu'au vendredi de
   * la semaine. Donnée, la date fixe aussi la semaine.
   *
   * suivi (facultatif) : l'avancement auquel le jalon appartient.
   * « concept » pour le concept harnais — les diffusions TO, la table
   * outil ; sans suivi, la définition électrique, le FWD. Sous l'autre
   * avancement, le jalon reste dessiné, en retrait, et ne compte pas.
   *
   * contrat (facultatif) : le contrat auquel le jalon appartient, écrit
   * comme le nom de son onglet (« HDK » ; casse et accents indifférents),
   * ou une liste de contrats ['HDK', 'X2']. Les autres contrats ne le
   * voient pas. Sans contrat, le jalon vaut pour tous les contrats. Le
   * Diagnostic dit combien de jalons a chaque contrat, et prévient quand
   * aucun onglet ne porte le nom donné.
   *
   * Les échéances du programme HDK, telles que transmises le 17/09/2026.
   * THS est un autre contrat, à d'autres dates : sans jalon pour l'instant
   * (débrief 17), comme tout autre contrat.
   */
  JALONS: [
    { contrat: 'HDK', semaine: '2026-S51', date: '2026-12-15', texte: 'Solde FWD' },
    { contrat: 'HDK', semaine: '2027-S02', date: '2027-01-15', texte: 'Diffusion PH Base',  perimetre: 'BASE/OPTION' },
    { contrat: 'HDK', semaine: '2027-S03', date: '2027-01-22', texte: 'Diffusion PH Perso', perimetre: 'PERSO' },
    { contrat: 'HDK', semaine: '2027-S05', date: '2027-02-05', texte: 'Diffusion TO Base',  perimetre: 'BASE/OPTION', suivi: 'concept' },
    { contrat: 'HDK', semaine: '2027-S08', date: '2027-02-26', texte: 'Diffusion TO Perso', perimetre: 'PERSO',       suivi: 'concept' }
  ],

  /** Nombre maximum de jalons transmis à la page. */
  MAX_JALONS: 40,

  /** Au-delà, une colonne est considérée comme un identifiant, pas une catégorie. */
  MAX_VALEURS_DIMENSION: 40,

  /** Nombre maximum de dimensions proposées dans « Grouper par ». */
  MAX_DIMENSIONS: 8,

  /**
   * Forçages. Vides, tout est déduit de l'en-tête — ce qui suffit dans la
   * plupart des cas. À remplir seulement si la détection se trompe.
   *
   * COLONNE_FWD : intitulé exact de la colonne d'avancement FWD. Si deux
   *   colonnes portent le même intitulé, préfixer par le groupe :
   *   'Réalisation FWD > Avancement'. Introuvable dans un extract, aucune
   *   autre colonne n'est lue à sa place (des chiffres justes d'allure,
   *   mais faux) : la page le dit en haut, l'archivage refuse, et le
   *   Diagnostic montre les colonnes de même intitulé avec leur groupe.
   *   Vide, la détection automatique choisit seule.
   * COLONNE_CONCEPT : la colonne du second avancement suivi, le concept
   *   harnais. La page propose alors l'interrupteur « Définition électrique |
   *   Concept harnais », et l'archivage garde les deux valeurs plan par plan.
   *   Vide, ou introuvable : pas d'interrupteur, rien d'autre ne change.
   * DIMENSIONS : intitulés des colonnes proposées dans « Avancement FWD par… »,
   *   dans l'ordre voulu. Même syntaxe « Groupe > Colonne » en cas de doublon.
   */
  /* Le FWD se suit dans le bloc HDK AA 011, colonne « Avancement Définition
     Electrique » — et non plus dans « Réalisation FWD > Avancement ». */
  COLONNE_FWD: 'HDK AA 011 > Avancement Définition Electrique',
  COLONNE_CONCEPT: 'HDK AA 011 > Avancement Concept Harnais',

  /* Les valeurs qui veulent dire « fini » dans la colonne suivie, écrites
     comme dans l'extract (accents, majuscules, féminin et pluriel
     indifférents : « Validé » vaut aussi « Validée », « Validés » ; valeur
     entière : « Non validé » n'en fait pas partie). S'ajoutent aux mots
     reconnus d'eux-mêmes : Terminé, Fini, Soldé, Clôturé, OK, 100 %. Les
     autres valeurs de la colonne s'affichent telles quelles, sans rien
     déclarer : la page les lit.
     ⚠ Une valeur « finie » absente d'ici compte « en cours » : la page le
     signale en haut quand AUCUN plan n'est compté terminé, et le Diagnostic
     dit, valeur par valeur, comment chacune est comptée.
     Les vraies valeurs de GATES (relevées au bureau le 29/09) : VALIDATED
     est fini ; PWD_IN_PROGRESS, PWD_TO_CONTROL, TO_CONFIRM sont en cours
     (rien à déclarer : c'est la famille par défaut). Le concept harnais
     (débrief 18) : vide, « À traiter » (pas commencé, reconnu de lui-même),
     « Traité » — fini. */
  VALEURS_FINIES: ['Validé', 'VALIDATED', 'Traité'],

  /* Les valeurs qui veulent dire « pas commencé », même règle. S'ajoutent à
     « À faire », « A traiter », « Non commencé », 0 %. Dans GATES : TO_TREAT
     (à traiter) et FWD_TO_SEIZE (FWD à saisir). */
  VALEURS_A_FAIRE: ['TO_TREAT', 'FWD_TO_SEIZE'],

  /*
   * Les colonnes proposées dans « Avancement FWD par… », dans l'ordre du
   * sélecteur. Relevées sur l'export réel : le découpage métier (ATA,
   * Séquence, Chapitre), les deux pré-requis amont du FWD (définition
   * électrique validée, statut iBG), l'état du cycle (Étape), la variante
   * (Produit) et la charge cachée (Redraw). L'ancienneté s'ajoute d'elle-même
   * à partir de la date de création.
   *
   * Vider cette liste rend la main à la détection automatique.
   */
  DIMENSIONS: [
    'ATA',
    'Séquence',
    'CC',
    'ECP'
  ],

  /**
   * Les colonnes que garde le bouton « Vue essentielle » du tableau, dans
   * l'ordre voulu. La référence figée y est toujours ajoutée en tête.
   * Vide = la référence, l'avancement, la date et les colonnes analysées.
   */
  COLONNES_ESSENTIELLES: [
    'Nom Installation',
    'ECP',
    'ATA',
    'Séquence',
    'Validation Définition Electrique',
    'Date création',
    'HDK AA 011 > Avancement Définition Electrique',
    'HDK AA 011 > Avancement Concept Harnais'
  ],

  /**
   * La colonne qui dit si un plan est du perso ou de la base/option. Elle
   * pilote le filtre rapide en haut du tableau. Vide = détection par
   * l'intitulé « domaine ».
   */
  COLONNE_DOMAINE: 'Domaine',

  /**
   * Rapprochement avec une seconde base : SEE, l'extract Excel de l'intranet
   * (« Nommage WD BFLOW »), collé tel quel dans un onglet du classeur — titre
   * en ligne 1, en-têtes en ligne 3, données dessous. Rien tant qu'aucun
   * onglet ne porte le nom configuré (FEUILLE, sinon NOM) : la page
   * n'affiche alors ni le rapprochement ni le tableau de la seconde base —
   * le Diagnostic dit pourquoi.
   *
   * Un plan présent dans SEE est un plan créé, donc terminé : la page croise
   * cette présence avec l'avancement FWD de GATES (terminés que SEE ignore,
   * plans que SEE connaît sans que GATES les dise terminés, indices qui
   * diffèrent). Seules les colonnes de la référence servent au
   * rapprochement ; les autres s'affichent, c'est tout.
   *
   * FEUILLE        : nom de l'onglet qui porte l'extract. Vide, c'est
   *                  l'onglet qui porte le NOM de la base (« SEE ») qui est
   *                  pris, s'il existe : on le crée, on colle, rien à régler.
   *                  L'en-tête est la
   *                  première ligne (parmi les LIGNES_SCAN_ENTETE premières)
   *                  qui porte tous les intitulés de CLE_REFERENCE — dans SEE
   *                  la ligne 3, sous le titre ; à défaut, la première ligne
   *                  non vide. Les intitulés sont conservés à la lettre.
   * NOM            : nom affiché dans la page ; vide = le nom de l'onglet.
   * CLE_REFERENCE  : intitulé de la colonne qui porte la référence UD
   *                  entière — ou la liste des intitulés qui la composent,
   *                  recomposée dans cet ordre. Dans SEE : NAME (la racine),
   *                  SOL. (la solution, remise sur trois chiffres si Excel
   *                  l'a réduite à « 1 ») et Cust.V (l'indice).
   * ESSENTIELLES   : les intitulés d'une « vue essentielle » du tableau de
   *                  la seconde base, dans l'ordre voulu ; vide = pas de vue
   *                  essentielle — c'est le choix pour SEE, dont l'extract
   *                  n'a qu'une vingtaine de colonnes.
   *
   * L'extract SEE est celui de TOUS les porteurs (débrief 21) : chaque
   * contrat n'en garde que ses lignes. Deux tris, faits par la fenêtre
   * d'import pendant la lecture du fichier — seules les lignes gardées vont
   * au classeur, et l'onglet le dit en ligne 1 (« Trié à l’import : PSN 4530
   * · DIAGRAM TYPE = WD — … ») —, et refaits à la lecture quand l'onglet
   * porte lui-même ces colonnes (un extract collé à la main, ou importé avec
   * toutes ses colonnes). Une colonne de tri absente de l'onglet n'écarte
   * rien ; absente du fichier, la fenêtre le dit et attend qu'on coche
   * « importer sans ce tri ».
   * COLONNE_PSN    : l'intitulé de la colonne qui dit pour quelles machines
   *                  (PSN) une ligne vaut : dans SEE, « VALIDITY PSN FULL »,
   *                  plusieurs numéros séparés par des virgules. Vide = pas
   *                  de tri par machine : l'extract va tout entier au
   *                  contrat, s'il n'y en a qu'un.
   * PSN            : le PSN de chaque contrat, nommé comme son onglet (casse
   *                  et accents indifférents) — '4530', ou une liste
   *                  ['4530', '4531']. Une ligne va au contrat quand sa
   *                  cellule COLONNE_PSN, coupée aux virgules, points-virgules
   *                  et espaces, porte l'un de ses PSN EN ENTIER : 4530 se
   *                  lit dans « 4520,4530, 4540 », jamais dans 14530 ni
   *                  45301 ; une cellule vide ne va à personne. Un contrat
   *                  sans PSN n'a pas de base SEE. Le PSN tapé dans la
   *                  fenêtre d'import (case SEE) est gardé dans le classeur
   *                  et l'emporte sur celui d'ici — vide compris ; le
   *                  Diagnostic dit lequel vaut.
   * FILTRES        : les colonnes qui doivent porter l'une des valeurs
   *                  données — DIAGRAM TYPE vaut GH, WD ou PH, seuls les WD
   *                  comptent. Intitulés et valeurs se comparent sans tenir
   *                  compte de la casse, des accents ni des espaces. Vide =
   *                  rien n'est écarté.
   */
  RAPPROCHEMENT: {
    FEUILLE: '',
    NOM: 'SEE',
    CLE_REFERENCE: ['NAME', 'SOL.', 'Cust.V'],
    ESSENTIELLES: [],
    COLONNE_PSN: 'VALIDITY PSN FULL',
    PSN: { HDK: '4530' },
    FILTRES: { 'DIAGRAM TYPE': ['WD'] }
  },

  /**
   * Dépôt automatique des extracts par un script (voir import/deposer.py) :
   * le script envoie les lignes d'un extract à l'application web (doPost),
   * qui les écrit dans l'onglet nommé et, si on le lui demande, archive le
   * relevé de la semaine pour ce contrat. Rien tant que SECRET est vide :
   * toute requête est refusée. Le même secret se met dans le script.
   *
   * SECRET      : une phrase longue et imprévisible, la même des deux côtés.
   * MAX_LIGNES  : au-delà, le dépôt est refusé — un garde-fou, pas une limite
   *               métier (un extract GATES fait quelques centaines de lignes).
   */
  DEPOT: {
    SECRET: '',
    MAX_LIGNES: 20000
  },

  /** Intitulés de texte libre : jamais des catégories, quoi qu'en dise le contenu. */
  MOTS_TEXTE_LIBRE: ['commentaire', 'libelle', 'raison', 'designation', 'remarque',
                     'note', 'description', 'observation'],

  /**
   * true = la page peut être embarquée dans n'importe quel site (Google Sites).
   * false = protection anti-clickjacking (recommandé si l'appli est ouverte directement).
   */
  AUTORISER_INTEGRATION_EXTERNE: false
};

const ENTETES_HISTORIQUE = [
  'Semaine', 'Date', 'Total', 'Validés', 'En cours', 'À faire', 'Non renseignés',
  'Par dimension', 'Plans'
];

/**
 * Une cellule de feuille de calcul ne tient pas plus de 50 000 caractères.
 * La carte plan par plan d'un relevé dépasse cette taille dès 1 500 à
 * 2 000 plans : elle est donc découpée en tranches de cette longueur, écrites
 * sur autant de cellules qu'il faut à droite de la colonne « Plans », puis
 * recollées à la lecture (voir enregistrerInstantaneHebdo et getHistorique).
 * Les comptes par dimension, eux, tiennent dans leur cellule.
 */
const MAX_CARACTERES_CELLULE = 45000;

// =====================================================================
//  POINTS D'ENTRÉE
// =====================================================================

/** Déploiement en application web. `?forcer=1` passe outre le contrôle des fichiers. */
function doGet(e) {
  /* ?frais=1 : tout ce qui est en cache devient caduc — cette ouverture
     relit le classeur et garde ce qu'elle a lu ; les suivantes, et les
     changements de contrat, en profitent. */
  if (e && e.parameter && e.parameter.frais) marquerDonneesModifiees_();
  const page = pageDuTableau(!!(e && e.parameter && e.parameter.forcer))
    .setTitle('Suivi FWD')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');

  return CONFIG.AUTORISER_INTEGRATION_EXTERNE
    ? page.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    : page;
}

/** Ouverture depuis le classeur, en fenêtre. */
function ouvrirTableauDeBord() {
  const page = pageDuTableau(false)
    .setTitle('Suivi FWD')
    .setWidth(2000)
    .setHeight(1400);
  SpreadsheetApp.getUi().showModalDialog(page, 'Suivi FWD');
}

/**
 * La page du tableau de bord — ou, si un fichier MANQUE au projet (la page
 * ne pourrait pas se construire), une page qui dit lequel recréer. Tout le
 * reste — un fichier coupé, collé deux fois, d'une autre livraison — la page
 * le dit elle-même en tête, sans qu'on bloque sur une supposition : c'en est
 * une qui, au bureau, a bloqué une page entière et saine (débrief 17). Le
 * contrôle ne peut pas empêcher la page : s'il échoue lui-même, elle s'ouvre.
 */
function pageDuTableau(forcer) {
  if (!forcer) {
    let verdict = null;
    try { verdict = verifierLivraison(lireFichiersDuProjet(), true); } catch (err) { verdict = null; }
    if (verdict && verdict.manquant) return HtmlService.createHtmlOutput(pageDePanne(verdict.lignes));
  }
  return HtmlService.createTemplateFromFile('Index').evaluate();
}

/** Le texte des trois fichiers HTML du projet ; un fichier introuvable manque. */
function lireFichiersDuProjet() {
  const contenus = {};
  ['Index', 'Styles', 'Javascript'].forEach(function (nom) {
    try { contenus[nom] = HtmlService.createHtmlOutputFromFile(nom).getContent(); } catch (err) { /* introuvable */ }
  });
  return contenus;
}

/** La page qui remplace le tableau de bord quand ses fichiers ne tiennent pas ensemble. */
function pageDePanne(lignes) {
  const ech = function (t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Suivi FWD</title></head>' +
    '<body style="margin:0;padding:40px 20px;background:#f4f2ed;color:#191915;font:15px/1.6 system-ui,sans-serif">' +
    '<div id="suivi-fwd-panne" role="alert" style="max-width:880px;margin:0 auto;padding:18px 24px;' +
    'background:#fff4e5;border-left:4px solid #b54708">' +
    '<p style="margin:0 0 10px"><b>Le tableau de bord ne peut pas s\u2019ouvrir : les fichiers collés dans Apps Script ' +
    'ne tiennent pas ensemble.</b> Rien n\u2019est touché dans le classeur.</p>' +
    '<pre style="margin:0 0 12px;white-space:pre-wrap;font:13px/1.6 ui-monospace,Consolas,monospace">' +
    ech(lignes.join('\n')) + '</pre>' +
    '<p style="margin:0 0 6px">À chaque livraison, recoller <b>les quatre fichiers</b> (Code, Index, Styles, Javascript), ' +
    'Ctrl+S sur chacun. Par un lien <b>…/exec</b> : ensuite, Déployer → Gérer les déploiements → ✏️ → Version : ' +
    'Nouvelle version → Déployer.</p>' +
    '<p style="margin:0;color:#57564e;font-size:13px">Le menu Suivi FWD → Diagnostic refait ce contrôle. Pour ouvrir ' +
    'la page quand même, par le lien …/exec : ajouter <code>?forcer=1</code> à la fin du lien.</p>' +
    '</div></body></html>';
}

/** Permet d'inclure Styles.html / Javascript.html depuis Index.html. */
function include(nomFichier) {
  return HtmlService.createHtmlOutputFromFile(nomFichier).getContent();
}

/** Menu ajouté au classeur à l'ouverture. */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Suivi FWD')
    .addItem('Ouvrir le tableau de bord', 'ouvrirTableauDeBord')
    .addSeparator()
    /* Le geste de chaque semaine d'abord : les exports, et le relevé avec. */
    .addItem(libelleImport(), 'importerSecondeBase')
    .addSeparator()
    .addItem('Archiver le relevé de cette semaine', 'enregistrerInstantaneHebdo')
    .addItem('Supprimer le relevé de cette semaine', 'supprimerDernierReleve')
    .addItem('Archiver l\'onglet affiché pour une semaine passée…', 'archiverSemainePassee')
    .addSeparator()
    .addItem('Activer l\'archivage automatique (vendredi 17 h)', 'installerSuiviHebdomadaire')
    .addItem('Désactiver l\'archivage automatique', 'desinstallerSuiviHebdomadaire')
    .addSeparator()
    .addItem('Diagnostic', 'diagnostic')
    .addToUi();
}

// =====================================================================
//  OUTILS GÉNÉRIQUES
// =====================================================================

/** Minuscules, sans accents, sans espaces superflus. */
function normaliser(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return valeur
    .toString()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Classe une valeur d'avancement FWD en quatre états.
 *
 * « À faire » est une valeur saisie ; une cellule vide est un défaut de saisie.
 * Les confondre masquerait le second, qui est précisément ce qu'on veut voir.
 *
 * ⚠ Cette fonction est volontairement dupliquée à l'identique dans
 *    Javascript.html : le serveur s'en sert pour archiver les relevés, le
 *    client pour les compteurs filtrés. Toute modification va des deux côtés.
 */
function classerFWD(valeur) {
  const s = normaliser(valeur);
  if (s === '' || s === '-' || s === 'empty') return 'vide';
  /* Un numéro devant l'état (« 3 - Validé », « 1. En cours ») ne compte pas. */
  const t = s.replace(/^\d+\s*[-.)]\s*/, '');
  const k = sansAccord(t);
  if (formesDeclarees(CONFIG.VALEURS_FINIES, ['Validé']).indexOf(k) !== -1) return 'termine';
  if (formesDeclarees(CONFIG.VALEURS_A_FAIRE, []).indexOf(k) !== -1) return 'afaire';
  if (/\ba (faire|traiter)\b/.test(t) || /^(non|pas) commence/.test(t)) return 'afaire';
  /* Un nombre, seul : un pourcentage. « 3 - Validé » ou une date n'en sont pas. */
  if (/^-?\d+(?:[.,]\d+)?\s*%?$/.test(s)) {
    const n = parseFloat(s.replace(/[\s%]/g, '').replace(',', '.'));
    if (n >= 100) return 'termine';
    if (n <= 0) return 'afaire';
    return 'encours';
  }
  /* Les mots qui disent « fini », en mots entiers — et pas après « non » ou
     « pas » : « Non OK », « Non terminé » ne sont pas finis. */
  if (!/^(non|pas)\b/.test(t) && /\b(?:(?:termine|acheve|cloture|solde|fini)e?s?|ok)\b/.test(t)) return 'termine';
  return 'encours';
}

/** Une valeur sans ses marques d'accord : « validee », « valides » → « valid ». */
function sansAccord(s) { return s.replace(/(?:ee?s?|s)$/, ''); }

/** Les valeurs d'une liste de CONFIG, normalisées et sans accord. */
function formesDeclarees(liste, defaut) {
  return (liste && liste.length ? liste : defaut)
    .map(function (v) { return sansAccord(normaliser(v)); })
    .filter(function (v) { return v !== ''; });
}

/** Numéro de semaine ISO-8601 au format « 2026-S07 ». */
function numeroSemaineISO(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const jour = d.getUTCDay() || 7;             // lundi = 1 … dimanche = 7
  d.setUTCDate(d.getUTCDate() + 4 - jour);     // jeudi de la semaine ISO
  const debutAnnee = Date.UTC(d.getUTCFullYear(), 0, 1);
  const semaine = Math.ceil(((d.getTime() - debutAnnee) / 86400000 + 1) / 7);
  return d.getUTCFullYear() + '-S' + (semaine < 10 ? '0' : '') + semaine;
}

/** Normalise « 2026-s8 » en « 2026-S08 ». Renvoie null si le format est invalide. */
function normaliserSemaine(texte) {
  const m = /^\s*(\d{4})\s*-?\s*[sS]\s*(\d{1,2})\s*$/.exec(String(texte || ''));
  if (!m) return null;
  const semaine = parseInt(m[2], 10);
  if (semaine < 1 || semaine > 53) return null;
  return m[1] + '-S' + (semaine < 10 ? '0' : '') + semaine;
}

/** Identifiant de colonne stable, tiré du libellé d'en-tête. */
function cleDepuisEntete(titre, deja) {
  let base = normaliser(titre).replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  if (!base) base = 'colonne';
  if (/^\d/.test(base)) base = 'c_' + base;
  let cle = base, n = 2;
  while (deja[cle]) { cle = base + '_' + n; n++; }
  deja[cle] = true;
  return cle;
}

// =====================================================================
//  CONTRATS ET LECTURE DE LA FEUILLE
//  Un contrat = un onglet visible qui n'est pas un onglet de service. Son
//  identifiant et son nom sont le nom de l'onglet. Les onglets d'historique
//  sont masqués, mais un onglet d'historique démasqué par curiosité ne doit
//  pas devenir un contrat pour autant : le préfixe le protège.
// =====================================================================

/** Vrai si l'onglet est un onglet de service, jamais un contrat. */
/**
 * L'onglet de la seconde base : celui que nomme FEUILLE, sinon un onglet qui
 * porte le NOM de la base (« SEE ») — c'est ainsi qu'on le crée sans toucher
 * au code. Vide quand rien n'est configuré.
 */
function feuilleRapprochement() {
  const cfg = CONFIG.RAPPROCHEMENT;
  if (!cfg) return '';
  return String(cfg.FEUILLE || cfg.NOM || '').trim();
}

/**
 * Un nom d'onglet réduit pour être comparé : minuscules, sans accents, les
 * séparateurs (espaces, tirets, soulignés, points) ramenés à une espace —
 * « SEE - HDK », « SEE_HDK » et « see hdk » se valent.
 */
function nomCompact(nom) {
  return normaliser(nom).replace(/[\s_\-\u2013\u2014.:\/]+/g, ' ').trim();
}

/**
 * La seconde base est propre à chaque contrat : l'onglet « SEE HDK » (ou
 * « SEE - HDK », « SEE_HDK », « HDK SEE ») sert au contrat HDK, et à lui
 * seul. Un onglet « SEE » tout court ne vaut que pour un classeur d'un seul
 * contrat : devant plusieurs, il ne dirait pas à qui il appartient, et la
 * page comparerait un contrat à l'extract d'un autre. Rien plutôt que faux.
 *
 * @return {Sheet|null}
 */
function ongletSecondeBase(classeur, contrat) {
  const base = feuilleRapprochement();
  if (!base) return null;
  const b = nomCompact(base);
  const c = contrat ? nomCompact(contrat) : '';
  const feuilles = classeur.getSheets();
  if (c) {
    for (let i = 0; i < feuilles.length; i++) {
      const n = nomCompact(feuilles[i].getName());
      if (n === b + ' ' + c || n === c + ' ' + b) return feuilles[i];
    }
  }
  let generique = null;
  for (let i = 0; i < feuilles.length && !generique; i++) {
    if (nomCompact(feuilles[i].getName()) === b) generique = feuilles[i];
  }
  if (!generique) return null;
  let nbContrats = 1;
  try { nbContrats = listerContrats(classeur).length; } catch (err) { nbContrats = 1; }
  return nbContrats <= 1 ? generique : null;
}

/** L'onglet qu'on attend pour la seconde base d'un contrat, pour le dire. */
function nomAttenduSecondeBase(classeur, contrat) {
  const base = feuilleRapprochement();
  let plusieurs = false;
  try { plusieurs = listerContrats(classeur).length > 1; } catch (err) { plusieurs = false; }
  return plusieurs && contrat ? base + ' ' + contrat : base;
}

function estOngletInterne(nom) {
  const n = normaliser(nom);
  /* Le reste d'un import, « HDK (import 3f2a9c) » ou « HDK (ancien 3f2a9c) »,
     n'est jamais un contrat : un import interrompu ne doit pas en faire
     apparaître un de plus, ni l'archivage lui ouvrir un historique. */
  if (estOngletImport(nom)) return true;
  /* L'onglet de la seconde base n'est pas un contrat non plus — ni celui
     d'un contrat, « SEE HDK ». */
  const internes = CONFIG.FEUILLES_INTERNES
    .concat(feuilleRapprochement() ? [feuilleRapprochement()] : [])
    .map(normaliser);
  if (internes.indexOf(n) !== -1) return true;
  const base = feuilleRapprochement() ? nomCompact(feuilleRapprochement()) : '';
  if (base) {
    const compact = nomCompact(nom);
    if (compact === base || compact.indexOf(base + ' ') === 0 ||
        compact.slice(-(base.length + 1)) === ' ' + base) return true;
  }
  const prefixe = normaliser(CONFIG.FEUILLE_HISTORIQUE);
  return !!prefixe && n.indexOf(prefixe) === 0;
}

/**
 * Les contrats du classeur, [{ id, nom }], dans l'ordre des onglets.
 * CONFIG.FEUILLE_DONNEES renseigné impose un contrat unique : cet onglet-là.
 */
function listerContrats(classeur) {
  if (CONFIG.FEUILLE_DONNEES) {
    const nommee = classeur.getSheetByName(CONFIG.FEUILLE_DONNEES);
    if (!nommee) {
      throw new Error('L\'onglet « ' + CONFIG.FEUILLE_DONNEES + ' » est introuvable.');
    }
    return [{ id: nommee.getName(), nom: nommee.getName() }];
  }
  /* Un onglet visible et VIDE n'est pas un contrat : c'est la « Feuille 1 »
     d'un classeur neuf, restée en tête quand on a ajouté l'onglet du premier
     contrat à côté. Sans cela, la page s'ouvrirait sur elle. Et dès qu'un
     onglet porte une ligne d'en-têtes d'export (Référence UD, ATA…), seuls
     ceux-là sont des contrats (débrief 16) : un onglet « Notes » ou un tableau
     croisé, compté comme contrat, faisait perdre l'onglet « SEE » et l'ancien
     historique d'un classeur à contrat unique. */
  return ongletsDeDonnees(classeur).contrats
    .map(function (f) { return { id: f.getName(), nom: f.getName() }; });
}

/** Les onglets candidats, partagés entre contrats et onglets écartés. */
function ongletsDeDonnees(classeur) {
  const visibles = classeur.getSheets()
    .filter(function (f) { return !f.isSheetHidden() && !estOngletInterne(f.getName()) && f.getLastRow() > 0; });
  /* « Copie de HDK » : l'onglet dupliqué pour garder une sauvegarde. Compté
     comme contrat, il s'archivait chaque vendredi dans un historique à lui. */
  let copies = visibles.filter(function (f) { return estCopieDOnglet(f.getName()); });
  let candidats = visibles.filter(function (f) { return copies.indexOf(f) === -1; });
  /* Seule, une copie est le contrat : on ne l'écarte pas. */
  if (!candidats.length) { candidats = copies; copies = []; }
  const exports = candidats.filter(aDesEntetes);
  return {
    contrats: exports.length ? exports : candidats,
    ecartes: (exports.length ? candidats.filter(function (f) { return exports.indexOf(f) === -1; }) : [])
      .map(function (f) { return { feuille: f, raison: 'export' }; })
      .concat(copies.map(function (f) { return { feuille: f, raison: 'copie' }; }))
  };
}

/** « Copie de HDK », « Copy of HDK » : un onglet dupliqué par Sheets. */
function estCopieDOnglet(nom) {
  return /^(copie de|copy of) /.test(normaliser(nom));
}

/** L'onglet porte-t-il, dans ses premières lignes, une ligne d'intitulés d'export ? */
/* Les en-têtes de chaque onglet, lus une fois par lecture (débrief 18) :
   la liste des contrats est demandée cinq fois par ouverture, et relisait
   chaque fois les premières lignes de chaque onglet — dix lectures du
   classeur pour rien. Le mémo ne vit que le temps d'une lecture (enLecture),
   jamais pendant une écriture ni d'une exécution à l'autre. */
let MEMO_ENTETES = null;
function enLecture(fn) {
  const dejaOuvert = !!MEMO_ENTETES;
  if (!dejaOuvert) MEMO_ENTETES = {};
  try { return fn(); } finally { if (!dejaOuvert) MEMO_ENTETES = null; }
}

function aDesEntetes(feuille) {
  if (!MEMO_ENTETES) return aDesEntetesLus(feuille);
  const k = '\u0001' + feuille.getName();
  if (!Object.prototype.hasOwnProperty.call(MEMO_ENTETES, k)) MEMO_ENTETES[k] = aDesEntetesLus(feuille);
  return MEMO_ENTETES[k];
}

function aDesEntetesLus(feuille) {
  const n = Math.min(CONFIG.LIGNES_SCAN_ENTETE, feuille.getLastRow());
  const largeur = feuille.getLastColumn();
  if (n < 1 || largeur < 1) return false;
  return feuille.getRange(1, 1, n, largeur).getDisplayValues().some(ligneDEnteteDExport);
}

/**
 * Une ligne d'en-têtes d'EXPORT : au moins deux intitulés attendus, chacun
 * seul dans sa cellule (« ATA », « Référence UD »), sur une ligne large — un
 * export GATES en porte plus de cent. Un tableau croisé (« ATA | NBVAL de
 * Référence UD ») ou une synthèse de quelques colonnes n'en est pas un : ils
 * devenaient des contrats (débrief 17).
 */
function ligneDEnteteDExport(ligne) {
  const cellules = (ligne || []).map(normaliser).filter(Boolean);
  if (cellules.length < ENTETE_EXPORT_MIN_INTITULES) return false;
  return CONFIG.MOTS_CLES_ENTETE.map(normaliser)
    .filter(function (m) { return cellules.indexOf(m) !== -1; }).length >= ENTETE_EXPORT_MIN_MOTS;
}
/* Les deux nombres de la règle, écrits une fois : la fenêtre d'import les
   reçoit tels quels pour reconnaître un export GATES dans un fichier. */
const ENTETE_EXPORT_MIN_INTITULES = 10;
const ENTETE_EXPORT_MIN_MOTS = 2;

/** Les onglets visibles écartés des contrats, et pourquoi : [{ nom, raison: 'export' | 'copie' }]. */
function ongletsEcartes(classeur) {
  return ongletsDeDonnees(classeur).ecartes.map(function (e) { return { nom: e.feuille.getName(), raison: e.raison }; });
}

/**
 * Pourquoi il n'y a aucun contrat : des onglets visibles mais vides — le
 * cas d'un classeur neuf, « Feuille 1 » —, ou aucun onglet visible du tout.
 * Le message nomme les onglets vides et dit le geste.
 */
function messageSansContrat(classeur) {
  const vides = classeur.getSheets()
    .filter(function (f) { return !f.isSheetHidden() && !estOngletInterne(f.getName()) && f.getLastRow() === 0; })
    .map(function (f) { return '« ' + f.getName() + ' »'; });
  /* Le geste d'abord par le menu d'import — il crée l'onglet du contrat —,
     le collage ensuite. */
  return 'Aucun onglet de données exploitable dans ce classeur : ' +
    (vides.length
      ? vides.join(', ') + (vides.length > 1 ? ' sont vides' : ' est vide') +
        ' — ' + cheminImport() + ', ou coller l\'export GATES en A1 d\'un onglet nommé du contrat.'
      : 'aucun onglet visible — ' + cheminImport() + ' crée l\'onglet du contrat.');
}

/**
 * Renvoie l'onglet de données d'un contrat — le premier si aucun n'est
 * demandé. On résout un onglet déterministe plutôt que getActiveSheet() :
 * sinon le tableau de bord lirait l'onglet cliqué en dernier, un onglet
 * d'historique compris. Un contrat demandé qui n'existe pas est une erreur
 * franche, pas un repli silencieux sur un autre contrat : la page la montre.
 */
function getFeuilleDonnees(classeur, contrat) {
  const contrats = listerContrats(classeur);
  if (contrats.length === 0) {
    throw new Error(messageSansContrat(classeur));
  }
  const voulu = contrat === undefined || contrat === null ? '' : String(contrat).trim();
  if (!voulu) return classeur.getSheetByName(contrats[0].id);
  for (let i = 0; i < contrats.length; i++) {
    if (contrats[i].id === voulu || normaliser(contrats[i].id) === normaliser(voulu)) {
      return classeur.getSheetByName(contrats[i].id);
    }
  }
  throw new Error('Le contrat « ' + voulu + ' » est introuvable : aucun onglet visible de ce nom.');
}

/** Trouve la ligne d'en-têtes dans les premières lignes de la feuille. */
/**
 * Une ligne porte-t-elle un intitulé d'en-tête attendu (Référence UD, ATA,
 * Nom installation) ? Un mot-clé compte s'il occupe une cellule à lui seul,
 * ou y figure comme mot entier : « ata » ne doit pas se lire dans
 * « catalogue » ou « constatation » d'une ligne de groupes.
 */
function ligneAIntitule(ligne) {
  const motsCles = CONFIG.MOTS_CLES_ENTETE.map(function (m) {
    return new RegExp('(^|[^a-z0-9])' + normaliser(m).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([^a-z0-9]|$)');
  });
  const cellules = (ligne || []).map(normaliser);
  return motsCles.some(function (m) { return cellules.some(function (c) { return m.test(c); }); });
}

function detecterLigneEntete(donnees) {
  const limite = Math.min(CONFIG.LIGNES_SCAN_ENTETE, donnees.length);
  for (let i = 0; i < limite; i++) {
    if (ligneAIntitule(donnees[i])) return i;
  }
  // Repli : première ligne qui contient au moins 3 libellés non vides.
  for (let i = 0; i < limite; i++) {
    const remplies = donnees[i].filter(function (c) { return String(c).trim() !== ''; }).length;
    if (remplies >= 3) return i;
  }
  return 0;
}

/**
 * Le groupe de chaque colonne, d'après la ligne au-dessus de l'en-tête.
 *
 * Cette ligne est faite de cellules fusionnées : « Réalisation FWD » couvre
 * quatre colonnes, chaque variante HDK AA en couvre sept. On lit donc les
 * fusions réelles de la feuille. Propager le dernier libellé vers la droite,
 * comme on le faisait, étalait un groupe sur tout ce qui le suivait — et
 * l'export GATES compte vingt-sept colonnes dont l'intitulé contient
 * « avancement » : sans le bon groupe, impossible de désigner la bonne.
 */
function groupesParColonne(feuille, ligneGroupes, nbColonnes) {
  const resultat = new Array(nbColonnes).fill('');
  let fusions = [];
  try {
    fusions = feuille.getRange(ligneGroupes, 1, 1, nbColonnes).getMergedRanges();
  } catch (err) {
    fusions = [];
  }

  if (fusions.length) {
    const valeurs = feuille.getRange(ligneGroupes, 1, 1, nbColonnes).getDisplayValues()[0];
    // Une cellule seule porte son propre libellé ; une fusion le porte sur toute sa largeur.
    for (let i = 0; i < nbColonnes; i++) {
      resultat[i] = valeurs[i] ? String(valeurs[i]).trim() : '';
    }
    fusions.forEach(function (plage) {
      const debut = plage.getColumn();
      const largeur = plage.getNumColumns();
      const texte = String(valeurs[debut - 1] || '').trim();
      for (let i = debut - 1; i < debut - 1 + largeur && i < nbColonnes; i++) resultat[i] = texte;
    });
    return resultat;
  }

  /* Pas de fusion lisible (feuille copiée, export brut) : on retombe sur la
     propagation vers la droite, en s'arrêtant sur les cellules vides s'il y en
     a autant que de colonnes — signe que la ligne est déjà complète. */
  const brut = ligneGroupes >= 1 ? feuille.getRange(ligneGroupes, 1, 1, nbColonnes).getDisplayValues()[0] : [];
  let dernier = '';
  for (let i = 0; i < nbColonnes; i++) {
    const valeur = brut && brut[i] ? String(brut[i]).trim() : '';
    if (valeur !== '') dernier = valeur;
    resultat[i] = dernier;
  }
  return resultat;
}

/**
 * Désigne une colonne par son intitulé, ou par « Groupe > Colonne » quand
 * l'intitulé seul est ambigu. Renvoie -1 si la désignation ne tombe sur rien.
 */
function indexParDesignation(designation, entetes, groupes) {
  const voulu = normaliser(designation);
  if (!voulu) return -1;
  const coupe = voulu.split('>');
  if (coupe.length === 2) {
    const g = coupe[0].trim(), c = coupe[1].trim();
    for (let i = 0; i < entetes.length; i++) {
      if (normaliser(entetes[i]) === c && normaliser(groupes[i] || '') === g) return i;
    }
    return -1;
  }
  for (let i = 0; i < entetes.length; i++) {
    if (normaliser(entetes[i]) === voulu) return i;
  }
  return -1;
}

/**
 * Index de la colonne d'avancement FWD : celle de CONFIG.COLONNE_FWD quand
 * elle est remplie (introuvable : -1, aucune autre) ; vide, la détection
 * automatique ci-dessous.
 *
 * L'export GATES compte vingt-sept colonnes dont l'intitulé contient
 * « avancement ». Sans CONFIG.COLONNE_FWD, le FWD est « Avancement », sous
 * le groupe « Réalisation FWD » ; les autres appartiennent aux blocs répétés par
 * variante (« Avancement Définition Electrique », « Avancement Concept
 * Harnais »). Le groupe est donc le critère décisif, et les intitulés qui
 * nomment explicitement un autre sujet sont écartés d'office.
 */
function trouverIndexFWD(entetes, groupes) {
  /* Une colonne nommée dans CONFIG.COLONNE_FWD est la seule qu'on suive :
     introuvable, on n'en suit aucune — la page le dit en haut, l'archivage
     refuse. Se rabattre sur une autre colonne (« Réalisation FWD >
     Avancement ») montrerait des chiffres justes d'allure, mais faux. */
  if (CONFIG.COLONNE_FWD) return indexParDesignation(CONFIG.COLONNE_FWD, entetes, groupes);

  const autreSujet = /(definition|concept|harnais|electrique|ibg|documentaire)/;
  const criteres = [
    function (col, grp) { return col === 'avancement' && grp.indexOf('fwd') !== -1; },
    function (col, grp) { return col.indexOf('avancement') !== -1 && grp.indexOf('fwd') !== -1 && !autreSujet.test(col); },
    function (col) { return col.indexOf('avancement') !== -1 && col.indexOf('fwd') !== -1; },
    function (col, grp) { return col.indexOf('realisation') !== -1 && (grp.indexOf('fwd') !== -1 || col.indexOf('fwd') !== -1); },
    function (col, grp) { return col.indexOf('avancement') !== -1 && !autreSujet.test(col) && grp.indexOf('concept') === -1; },
    function (col) { return col.indexOf('fwd') !== -1; }
  ];
  for (let c = 0; c < criteres.length; c++) {
    for (let i = 0; i < entetes.length; i++) {
      if (criteres[c](normaliser(entetes[i]), normaliser(groupes[i] || ''))) return i;
    }
  }
  return -1;
}

/** Index de la colonne qui identifie un plan : elle sera figée à gauche. */
function trouverIndexReference(entetes) {
  for (let m = 0; m < MOTIFS_REFERENCE.length; m++) {
    for (let i = 0; i < entetes.length; i++) {
      if (normaliser(entetes[i]).indexOf(MOTIFS_REFERENCE[m]) !== -1) return i;
    }
  }
  return 0;
}
/* Les intitulés de la colonne de référence, dans l'ordre de préférence. La
   fenêtre d'import choisit la même colonne dans un fichier, pour rattacher
   un export GATES au contrat dont il partage les plans. */
const MOTIFS_REFERENCE = ['reference ud', 'reference', 'ref', 'identifiant', 'numero de plan', 'plan'];

/** Index de la colonne qui distingue le perso de la base/option. */
function trouverIndexDomaine(entetes, groupes) {
  const force = indexParDesignation(CONFIG.COLONNE_DOMAINE, entetes, groupes);
  if (force !== -1) return force;
  for (let i = 0; i < entetes.length; i++) {
    if (normaliser(entetes[i]).indexOf('domaine') !== -1) return i;
  }
  return -1;
}

/** Index d'une colonne de date de création, pour la dimension « ancienneté ». */
function trouverIndexDate(entetes, lignes) {
  for (let i = 0; i < entetes.length; i++) {
    const n = normaliser(entetes[i]);
    if (n.indexOf('creation') === -1 && n.indexOf('ouverture') === -1) continue;
    if (colonneRessembleAUneDate(lignes, i)) return i;
  }
  for (let j = 0; j < entetes.length; j++) {
    if (normaliser(entetes[j]).indexOf('date') !== -1 && colonneRessembleAUneDate(lignes, j)) return j;
  }
  return -1;
}

/* La feuille est lue en `getDisplayValues()` : on reçoit ce que la cellule
   MONTRE, donc toujours du texte, déjà mis en forme par le classeur. Une date
   arrive telle qu'elle s'affiche — `16/07/2020` sur une feuille française,
   `2020-07-16` ailleurs — et c'est la page qui sait lire les deux ordres. */
function valeurCellule(v) {
  return v === undefined || v === null ? '' : String(v).trim();
}

function colonneRessembleAUneDate(lignes, index) {
  let vues = 0, dates = 0;
  for (let i = 0; i < lignes.length && vues < 40; i++) {
    const v = valeurCellule(lignes[i][index]);
    if (!v) continue;
    vues++;
    if (/\d{4}[-\/.]\d{1,2}|\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4}/.test(v)) dates++;
  }
  return vues > 0 && dates / vues >= 0.7;
}

/** Une ligne est significative si au moins une cellule est renseignée. */
function ligneNonVide(ligne) {
  for (let i = 0; i < ligne.length; i++) {
    if (String(ligne[i]).trim() !== '') return true;
  }
  return false;
}

// =====================================================================
//  MODÈLE DE COLONNES
//  Rien n'est écrit en dur : le nom, le groupe, le type et le rôle de chaque
//  colonne se déduisent de l'en-tête et du contenu.
// =====================================================================

/** Le modèle d'un contrat — le premier si aucun n'est demandé. */
function construireModele(contrat) {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = getFeuilleDonnees(classeur, contrat);
  const donnees = feuille.getDataRange().getDisplayValues();
  if (donnees.length === 0) {
    throw new Error('La feuille « ' + feuille.getName() + ' » est vide.');
  }

  const indexEntete = detecterLigneEntete(donnees);
  const entetes = donnees[indexEntete].map(function (e) { return String(e).trim(); });
  const nbColonnes = entetes.length;
  const groupes = indexEntete > 0
    ? groupesParColonne(feuille, indexEntete, nbColonnes)   // 1-based : la ligne au-dessus
    : new Array(nbColonnes).fill('');

  const iFWD = trouverIndexFWD(entetes, groupes);
  const fwdDemandeeAbsente = !!CONFIG.COLONNE_FWD && iFWD === -1;
  let iConcept = CONFIG.COLONNE_CONCEPT ? indexParDesignation(CONFIG.COLONNE_CONCEPT, entetes, groupes) : -1;
  if (iConcept === iFWD) iConcept = -1;
  const conceptDemandeAbsent = !!CONFIG.COLONNE_CONCEPT && iConcept === -1;
  const iRef = trouverIndexReference(entetes);
  const iDomaine = trouverIndexDomaine(entetes, groupes);
  const lignesBrutes = donnees.slice(indexEntete + 1);
  const iDate = trouverIndexDate(entetes, lignesBrutes);

  /* Une ligne est un plan si elle porte une référence. L'export intercale des
     lignes de service sous l'en-tête ; sans ce filtre elles compteraient comme
     des plans et fausseraient tous les totaux. */
  let lignes = lignesBrutes.filter(function (l) {
    return valeurCellule(l[iRef]) !== '';
  });
  /* Aucune référence nulle part, et pas de colonne de référence reconnue par
     son intitulé : on retombe sur « la ligne dit quelque chose ». Avec une
     colonne « Référence UD » bien là mais vide, l'onglet n'a que ses en-têtes
     (et sa ligne de service, qui devenait un faux plan « ligne-1 »). */
  const refReconnue = /reference|ref|identifiant|numero de plan|plan/.test(normaliser(entetes[iRef]));
  if (lignes.length === 0 && !refReconnue) {
    lignes = lignesBrutes.filter(ligneNonVide);
  }

  // Statistiques par colonne : longueur moyenne et nombre de valeurs distinctes.
  const stats = [];
  for (let c = 0; c < nbColonnes; c++) {
    const distinctes = {};
    let nDistinctes = 0, somme = 0, remplies = 0;
    for (let l = 0; l < lignes.length; l++) {
      const v = valeurCellule(lignes[l][c]);
      if (!v) continue;
      remplies++;
      somme += v.length;
      if (!distinctes[v]) { distinctes[v] = true; nDistinctes++; }
    }
    stats.push({
      distinctes: nDistinctes,
      remplies: remplies,
      longueurMoyenne: remplies ? somme / remplies : 0
    });
  }

  // Un intitulé qui revient à l'identique ne peut pas nommer une dimension :
  // « A traiter par » apparaît treize fois, personne ne saurait laquelle c'est.
  const occurrences = {};
  entetes.forEach(function (t) {
    const n = normaliser(t);
    occurrences[n] = (occurrences[n] || 0) + 1;
  });

  /* « reference » et « avancement » sont réservées d'emblée : sinon une colonne
     intitulée « Avancement » située avant celle du FWD s'emparerait de la clé,
     et le reste du code désignerait la mauvaise. L'export GATES en compte une
     par variante. */
  const deja = { reference: true, avancement: true };
  const colonnes = [];
  let cleFWD = null;
  let cleDate = null;
  let cleConcept = null;

  for (let i = 0; i < nbColonnes; i++) {
    const titre = entetes[i] || ('Colonne ' + (i + 1));
    const cle = (i === iRef) ? 'reference'
              : (i === iFWD) ? 'avancement'
              : cleDepuisEntete(titre, deja);
    if (i === iFWD) cleFWD = cle;
    if (i === iDate) cleDate = cle;
    if (i === iConcept) cleConcept = cle;

    const s = stats[i];
    let classe = '';
    if (i === iRef) classe = 'ref';
    else if (s.longueurMoyenne > 28) classe = 'large';
    else if (s.longueurMoyenne <= 12) classe = 'num';

    const col = { cle: cle, groupe: groupes[i] || '', titre: titre, classe: classe };
    if (i === iRef) col.fige = true;
    col.__i = i;
    col.__score = scoreDimension(i, titre, s, lignes.length, occurrences, iRef, iFWD, iDate);
    colonnes.push(col);
  }

  /* Les dimensions sont choisies par pertinence, pas par position. Prendre les
     premières de gauche épuiserait le quota bien avant d'atteindre l'ATA, qui
     est en vingt-cinquième colonne. */
  const forcees = CONFIG.DIMENSIONS && CONFIG.DIMENSIONS.length
    ? CONFIG.DIMENSIONS
        .map(function (d) { return indexParDesignation(d, entetes, groupes); })
        .filter(function (i) { return i !== -1; })
    : null;

  if (forcees) {
    forcees.forEach(function (i) { colonnes[i].dim = true; });
  } else {
    colonnes.slice()
      .filter(function (c) { return c.__score > 0; })
      .sort(function (a, b) { return b.__score - a.__score || a.__i - b.__i; })
      .slice(0, CONFIG.MAX_DIMENSIONS)
      .forEach(function (c) { c.dim = true; });
  }

  /* Ordre du sélecteur : celui de la feuille, pour qu'on s'y retrouve —
     sauf si la liste a été forcée, auquel cas c'est l'ordre demandé. */
  const clesDim = forcees
    ? forcees.map(function (i) { return colonnes[i].cle; })
    : colonnes.filter(function (c) { return c.dim; }).map(function (c) { return c.cle; });

  colonnes.forEach(function (c) { delete c.__score; delete c.__i; });

  const plans = lignes.map(function (ligne, n) {
    const p = {};
    for (let i = 0; i < nbColonnes; i++) {
      p[colonnes[i].cle] = valeurCellule(ligne[i]);
    }
    // Une référence vide rendrait le comparatif faux : on en fabrique une stable.
    if (!p.reference) p.reference = 'ligne-' + (n + 1);
    // Sans colonne d'avancement reconnue, tout est « non renseigné », et le
    // message d'avertissement dit pourquoi plutôt que de laisser deviner.
    if (cleFWD === null) p.avancement = '';
    return p;
  });

  return {
    feuille: feuille.getName(),
    colonnes: colonnes,
    plans: plans,
    cleDate: cleDate,
    clesDim: clesDim,
    dimParDefaut: choisirDimensionParDefaut(colonnes, clesDim),
    /* La « vue essentielle » du tableau : ce qu'on regarde vraiment, sans les
       cent trente-huit colonnes de l'export. */
    clesEssentielles: choisirEssentielles(colonnes, entetes, groupes, cleDate),
    cleDomaine: iDomaine === -1 ? null : colonnes[iDomaine].cle,
    cleConcept: cleConcept,
    fwdDemandeeAbsente: fwdDemandeeAbsente,
    conceptDemandeAbsent: conceptDemandeAbsent,
    avertissement: fwdDemandeeAbsente
      ? 'Colonne « ' + CONFIG.COLONNE_FWD + ' » introuvable dans l\'onglet « ' + feuille.getName() +
        ' » : aucun avancement n\'est lu plutôt qu\'un autre, et l\'archivage est refusé. Suivi FWD → Diagnostic montre l\'en-tête lu.'
      : cleFWD === null
        ? 'Aucune colonne d\'avancement FWD n\'a été reconnue dans l\'en-tête.'
        : '',
    avertissementConcept: conceptDemandeAbsent
      ? 'Colonne « ' + CONFIG.COLONNE_CONCEPT + ' » introuvable dans l\'onglet « ' + feuille.getName() +
        ' » : pas de concept harnais, et l\'archivage est refusé. Suivi FWD → Diagnostic montre l\'en-tête lu.'
      : '',
    lignesIgnorees: lignesBrutes.length - lignes.length,
    /* Une référence présente sur plusieurs lignes (export collé par-dessus
       l'ancien, sans Ctrl+A / Suppr) : chaque ligne compte, la carte garde la
       première — et le diagnostic comme la page le disent (débrief 16). */
    doublons: (function () {
      const vues = {}; let n = 0;
      plans.forEach(function (p) { if (vues[p.reference]) n++; else vues[p.reference] = true; });
      return n;
    })()
  };
}

/**
 * Note de « catégoricité » d'une colonne : 0 = jamais une dimension.
 *
 * Une bonne dimension découpe la population en quelques paquets comparables.
 * Deux valeurs, c'est déjà un découpage ; deux cents, c'est un identifiant.
 * Une colonne de texte libre n'en est jamais une, même si l'export n'en a
 * rempli que trois cases.
 */
function scoreDimension(index, titre, stats, nbLignes, occurrences, iRef, iFWD, iDate) {
  if (index === iRef || index === iFWD || index === iDate) return 0;
  if (!titre) return 0;

  const n = normaliser(titre);
  if (occurrences[n] > 1) return 0;                       // intitulé ambigu
  for (let m = 0; m < CONFIG.MOTS_TEXTE_LIBRE.length; m++) {
    if (n.indexOf(CONFIG.MOTS_TEXTE_LIBRE[m]) !== -1) return 0;
  }
  if (stats.distinctes < 2) return 0;                     // une seule valeur : rien à découper
  if (stats.distinctes > CONFIG.MAX_VALEURS_DIMENSION) return 0;
  if (stats.distinctes > Math.max(2, nbLignes / 2)) return 0;
  if (stats.longueurMoyenne > 28) return 0;
  if (stats.remplies < nbLignes * 0.5) return 0;          // trop de trous pour trancher

  /* On préfère ce qui parle au métier, puis ce qui se lit d'un coup d'œil :
     une dizaine de paquets, des valeurs courtes, une colonne bien remplie. */
  const metier = ['ata', 'sequence', 'chapitre', 'statut', 'validation', 'etape',
                  'produit', 'domaine', 'groupage', 'zone', 'lot', 'type'];
  let score = 10;
  for (let k = 0; k < metier.length; k++) {
    if (n.indexOf(metier[k]) !== -1) { score += 100 - k * 4; break; }
  }
  score += Math.max(0, 30 - Math.abs(stats.distinctes - 10) * 2);
  score += Math.max(0, 20 - stats.longueurMoyenne);
  score += (stats.remplies / Math.max(1, nbLignes)) * 20;
  return score;
}

/**
 * Les colonnes de la vue essentielle, dans l'ordre demandé.
 * La colonne figée ouvre toujours la liste : elle reste verrouillée à gauche.
 */
function choisirEssentielles(colonnes, entetes, groupes, cleDate) {
  const figee = colonnes.filter(function (c) { return c.fige; }).map(function (c) { return c.cle; });
  let reste;
  if (CONFIG.COLONNES_ESSENTIELLES && CONFIG.COLONNES_ESSENTIELLES.length) {
    reste = CONFIG.COLONNES_ESSENTIELLES
      .map(function (d) { return indexParDesignation(d, entetes, groupes); })
      .filter(function (i) { return i !== -1; })
      .map(function (i) { return colonnes[i].cle; });
    /* La colonne suivie est toujours de la vue essentielle, même si la
       liste ne la nomme pas (ou nomme une colonne absente de l'extract). */
    if (reste.indexOf('avancement') === -1 && colonnes.some(function (c) { return c.cle === 'avancement'; })) reste.push('avancement');
  } else {
    reste = colonnes
      .filter(function (c) { return c.cle === 'avancement' || c.cle === cleDate || c.dim; })
      .map(function (c) { return c.cle; });
  }
  return figee.concat(reste.filter(function (c) { return figee.indexOf(c) === -1; }));
}

/**
 * Dimension ouverte par défaut dans « Avancement FWD par… ».
 * C'est le découpage métier qu'on regarde en premier — l'ATA, à défaut le
 * lot ou la zone —, pas simplement la colonne la plus à gauche.
 */
function choisirDimensionParDefaut(colonnes, clesDim) {
  if (!clesDim.length) return '';
  const motifs = ['ata', 'chapitre', 'lot', 'zone', 'section', 'systeme'];
  for (let m = 0; m < motifs.length; m++) {
    for (let i = 0; i < colonnes.length; i++) {
      if (clesDim.indexOf(colonnes[i].cle) === -1) continue;
      if (normaliser(colonnes[i].titre).indexOf(motifs[m]) !== -1) return colonnes[i].cle;
    }
  }
  return clesDim[0];
}

// =====================================================================
//  PAQUET ENVOYÉ À LA PAGE
// =====================================================================

/**
 * Le paquet complet d'un contrat, tel que la page le consomme.
 *
 * `contrat` est l'identifiant du contrat demandé (le nom de son onglet) ;
 * absent, c'est le premier contrat du classeur qui est servi — celui que la
 * page reçoit à l'ouverture. Le paquet porte la liste des contrats et celui
 * qui est servi : la page en déduit s'il y a un sélecteur à montrer, sans
 * rien savoir du classeur. Un contrat inconnu donne un paquet d'erreur
 * (ok: false, message), que la page affiche sans quitter le contrat courant.
 */
function getDonneesPourClient(contrat) {
  return enLecture(function () { return getDonneesPourClientLues(contrat); });
}

function getDonneesPourClientLues(contrat) {
  try {
    const classeur = SpreadsheetApp.getActiveSpreadsheet();
    const contrats = listerContrats(classeur);
    const modele = modeleAOuvrir(contrat, contrats);
    /* L'historique à part : illisible (délai dépassé…), il ne doit pas
       emporter l'extract du jour avec lui. */
    let releves = [], avisHistorique = '';
    try {
      releves = getHistorique(classeur, modele.feuille);
    } catch (err) {
      avisHistorique = 'L\'historique de « ' + modele.feuille + ' » n\'a pas pu être lu (' +
        (err && err.message ? err.message : err) + ') : la page montre l\'extract du jour, sans courbe ni journal. Recharger la page.';
    }
    const paquet = {
      ok: true,
      edition: EDITION,
      message: [modele.avertissement, modele.avertissementConcept,
                modele.plans.length ? '' : 'L\'onglet « ' + modele.feuille + ' » ne porte aucun plan (en-têtes seuls) : ' +
                  'importer l\'export GATES du contrat (' + cheminImport() + '), ou l\'y coller en A1.'].filter(Boolean).join(' '),
      avis: [avisHistorique, avisOrphelins(historiquesOrphelins(classeur, contrats), modele.feuille,
               contratsSansHistorique(classeur, contrats).map(function (c) { return c.id; }))].filter(Boolean).join(' '),
      historiqueIllisible: !!avisHistorique,
      feuille: modele.feuille,
      genereLe: new Date().toISOString(),
      colonnes: modele.colonnes,
      cleDate: modele.cleDate,
      clesDim: modele.clesDim,
      clesEssentielles: modele.clesEssentielles,
      cleDomaine: modele.cleDomaine,
      cleConcept: modele.cleConcept,
      valeursFinies: CONFIG.VALEURS_FINIES,
      valeursAFaire: CONFIG.VALEURS_A_FAIRE || [],
      dimParDefaut: modele.dimParDefaut,
      lignesIgnorees: modele.lignesIgnorees,
      doublons: modele.doublons,
      plans: modele.plans,
      releves: releves,
      jalons: getJalons(modele.feuille),
      contrats: contrats,
      contrat: modele.feuille
    };
    /* La seconde base, seulement si la configuration en nomme une : la page
       masque la section quand la clé est absente. */
    const rapprochement = getRapprochement(classeur, modele.feuille);
    if (rapprochement) paquet.rapprochement = rapprochement;
    return paquet;
  } catch (err) {
    return {
      ok: false,
      edition: EDITION,
      message: err && err.message ? err.message : String(err),
      feuille: '',
      genereLe: new Date().toISOString(),
      colonnes: [], cleDate: null, clesDim: [], clesEssentielles: [], cleDomaine: null,
      dimParDefaut: '', plans: [], releves: [], jalons: [],
      contrats: [], contrat: ''
    };
  }
}

/**
 * Le modèle du contrat demandé. Sans demande — l'ouverture de la page —, le
 * premier contrat qui porte des plans : un onglet préparé d'avance, en-têtes
 * seuls, placé en tête, ouvrait la page sur « 0 sur 0 » alors que les plans
 * du contrat suivant étaient là (débrief 17).
 */
function modeleAOuvrir(contrat, contrats) {
  if (contrat !== undefined && contrat !== null && contrat !== '') return construireModele(contrat);
  let premier = null;
  for (let i = 0; i < contrats.length; i++) {
    const modele = construireModele(contrats[i].id);
    if (modele.plans.length) return modele;
    if (!premier) premier = modele;
  }
  return premier || construireModele(contrat);
}

/**
 * Le paquet d'un autre contrat, demandé par la page sans se recharger —
 * compacté comme celui de l'ouverture.
 */
function getDonneesCompactes(contrat) {
  return JSON.parse(paquetCompactJson(contrat));
}

/* =====================================================================
   LE PAQUET EN CACHE (débrief 18 : « le site est très long à charger »)
   Chaque ouverture relisait tout le classeur : l'extract entier, son
   historique, la seconde base. Le paquet de chaque contrat se garde donc
   six heures dans le cache du classeur — mais sous une clé qui change dès
   que quelque chose change : un collage ou une saisie (onEdit), un
   archivage, une suppression, un dépôt (marquerDonneesModifiees_), un onglet
   ajouté, renommé, masqué, des lignes ou des colonnes ajoutées ou
   supprimées (la taille de chaque onglet est dans la clé : onEdit ne voit
   pas ces gestes-là), la configuration ou la livraison, le jour. Ce que la
   page montre est donc ce que le classeur contient ; « lus dans le classeur
   le … », en bas de page, dit quand. Ce qui y échapperait — une version
   restaurée depuis l'historique de Google — se rattrape par ?frais=1, qui
   rend caduc tout le cache. Un paquet incomplet (historique illisible le
   temps d'une panne de Google) ne se garde jamais.
   ===================================================================== */
const CACHE_SECONDES = 21600;          // six heures : le plafond de CacheService
const CACHE_TRANCHE = 30000;           // caractères par clé : moins de 100 Ko même à 3 octets
const CLE_VERSION_DONNEES = 'SUIVI_FWD_VERSION_DONNEES';
let PAGE_FRAICHE = false;           // le Diagnostic mesure une lecture sans le cache

/**
 * Toute modification du classeur rend caducs les paquets en cache. Le « _ »
 * final la cache de google.script.run : un lecteur ne peut pas, depuis la
 * page, vider le cache en boucle et faire relire tout le classeur à chaque
 * ouverture.
 */
function marquerDonneesModifiees_() {
  try {
    PropertiesService.getDocumentProperties().setProperty(CLE_VERSION_DONNEES,
      String(new Date().getTime()) + '-' + Math.floor(Math.random() * 1e6));
  } catch (err) { /* pas de propriétés : pas de cache non plus (versionDonnees) */ }
}

/**
 * Déclencheur simple : chaque modification faite à la main — coller un
 * export, effacer, saisir — renouvelle la version des données. Une ligne,
 * pour ne rien ralentir.
 */
function onEdit(e) {
  marquerDonneesModifiees_();
}

/* =====================================================================
   LES CONSULTATIONS, SANS NOM (débrief 18 : « pour avoir des stats »)
   Chaque ouverture de la page est comptée, semaine par semaine, avec le
   nombre de personnes différentes — reconnues par la clé temporaire que
   Google donne à chaque lecteur (Session.getTemporaryActiveUserKey : elle
   ne dit pas qui il est, et change tous les 30 jours), elle-même réduite à
   une empreinte. Aucune adresse, aucun nom n'est lu ni gardé. Douze
   semaines au plus ; pour les semaines finies, seul le nombre reste. Le
   Diagnostic les montre ; le pied de la page dit que l'ouverture est
   comptée.
   ===================================================================== */
const CLE_CONSULTATIONS = 'SUIVI_FWD_CONSULTATIONS';
const MAX_SEMAINES_CONSULTATIONS = 12;
const MAX_PERSONNES_SEMAINE = 400;

/** Appelée par la page une fois affichée : compte l'ouverture. Ne lève jamais. */
function noterConsultation() {
  try {
    const verrou = verrouDuClasseur_();   // le même que les autres gestes : la page servie par …/exec est une application web
    if (!verrou.tryLock(3000)) return false;
    try {
      const props = PropertiesService.getDocumentProperties();
      const semaine = numeroSemaineISO(new Date());
      let cle = '';
      try { cle = String(Session.getTemporaryActiveUserKey() || ''); } catch (err) { cle = ''; }
      const stats = analyserJson(props.getProperty(CLE_CONSULTATIONS)) || {};
      const s = stats[semaine] && typeof stats[semaine] === 'object' ? stats[semaine] : (stats[semaine] = { n: 0, k: [] });
      if (!Array.isArray(s.k)) s.k = [];
      s.n = (Number(s.n) || 0) + 1;
      if (cle) {
        const e = empreinte('consultation\u0001' + cle);
        if (s.k.indexOf(e) === -1 && s.k.length < MAX_PERSONNES_SEMAINE) s.k.push(e);
      }
      /* Les semaines finies ne gardent que leurs nombres. */
      Object.keys(stats).sort().reverse().forEach(function (w, i) {
        if (i >= MAX_SEMAINES_CONSULTATIONS) { delete stats[w]; return; }
        if (w !== semaine && stats[w] && Array.isArray(stats[w].k)) { stats[w].p = stats[w].k.length; delete stats[w].k; }
      });
      props.setProperty(CLE_CONSULTATIONS, JSON.stringify(stats));
      return true;
    } finally {
      verrou.releaseLock();
    }
  } catch (err) {
    return false;
  }
}

/** Pour le Diagnostic : « S40 : 37 ouvertures, 12 personnes · S39 : … », les plus récentes d'abord.
    Le « _ » : ces chiffres ne sortent que par le Diagnostic, pas par la page. */
function resumeConsultations_() {
  let stats = null;
  try { stats = analyserJson(PropertiesService.getDocumentProperties().getProperty(CLE_CONSULTATIONS)); } catch (err) { stats = null; }
  if (!stats || typeof stats !== 'object') return '';
  return Object.keys(stats).filter(function (w) { return normaliserSemaine(w); }).sort().reverse().slice(0, 6).map(function (w) {
    const s = stats[w] || {};
    const n = Number(s.n) || 0;
    const p = Array.isArray(s.k) ? s.k.length : Number(s.p) || 0;
    return 'S' + parseInt(w.slice(6), 10) + ' : ' + n + ' ouverture' + (n > 1 ? 's' : '') +
      (p ? ', ' + p + ' personne' + (p > 1 ? 's' : '') : '');
  }).join(' · ');
}

/** Une empreinte courte d'un texte (clé de cache : 250 caractères au plus). */
function empreinte(texte) {
  let h1 = 5381, h2 = 52711;
  for (let i = 0; i < texte.length; i++) {
    const c = texte.charCodeAt(i);
    h1 = ((h1 << 5) + h1 + c) | 0;
    h2 = ((h2 << 5) + h2 + (c ^ 0x5bd1)) | 0;
  }
  return (h1 >>> 0).toString(36) + (h2 >>> 0).toString(36) + texte.length.toString(36);
}

/** Ce qui fait la version des données : la marque, les onglets et leur taille, la configuration, le jour. */
function versionDonnees(classeur) {
  const marque = PropertiesService.getDocumentProperties().getProperty(CLE_VERSION_DONNEES) || '0';
  const onglets = classeur.getSheets().map(function (f) {
    return f.getName() + (f.isSheetHidden() ? '~' : '') + ':' + f.getLastRow() + 'x' + f.getLastColumn();
  }).join('\u0001');
  return [EDITION, marque, onglets, JSON.stringify(CONFIG), Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd')].join('\u0002');
}

function cacheDuClasseur() {
  try {
    if (typeof CacheService === 'undefined') return null;
    return CacheService.getDocumentCache() || CacheService.getScriptCache();
  } catch (err) { return null; }
}

function lireCache(cache, cle) {
  try {
    const n = Number(cache.get(cle + ':n'));
    if (!n) return null;
    const cles = [];
    for (let i = 0; i < n; i++) cles.push(cle + ':' + i);
    const lus = cache.getAll(cles);
    let texte = '';
    for (let i = 0; i < n; i++) {
      if (typeof lus[cles[i]] !== 'string') return null;
      texte += lus[cles[i]];
    }
    return texte;
  } catch (err) { return null; }
}

function ecrireCache(cache, cle, texte) {
  try {
    const valeurs = {};
    let n = 0;
    for (let i = 0; i < texte.length; i += CACHE_TRANCHE) valeurs[cle + ':' + (n++)] = texte.slice(i, i + CACHE_TRANCHE);
    cache.putAll(valeurs, CACHE_SECONDES);
    cache.put(cle + ':n', String(n), CACHE_SECONDES);   // en dernier : un paquet n'est lisible qu'entier
  } catch (err) { /* trop gros, ou cache indisponible : la page se sert sans */ }
}

/** Le paquet compact d'un contrat, en JSON : du cache s'il est à jour, sinon lu et gardé. */
function paquetCompactJson(contrat) {
  const cache = PAGE_FRAICHE ? null : cacheDuClasseur();
  let cle = null;
  if (cache) {
    try { cle = 'SFWD:' + empreinte(String(contrat || '') + '\u0003' + versionDonnees(SpreadsheetApp.getActiveSpreadsheet())); }
    catch (err) { cle = null; }
  }
  if (cle) {
    const lu = lireCache(cache, cle);
    if (lu) return lu;
  }
  const paquet = compacterPaquet(getDonneesPourClient(contrat));
  const json = JSON.stringify(paquet);
  /* Un paquet en erreur, ou lu à moitié — l'historique illisible le temps
     d'une panne passagère —, n'est pas gardé : la prochaine ouverture
     relira, comme la page le conseille. */
  if (cle && paquet && paquet.ok && !paquet.historiqueIllisible) ecrireCache(cache, cle, json);
  return json;
}

/**
 * Le paquet, en plus léger pour le voyage — la page le rend à l'identique
 * (deballerPaquet). Un plan portait le nom de ses 138 colonnes, un relevé
 * celui de chacun de ses plans, une ligne de SEE ses intitulés : chaque nom
 * ne s'écrit plus qu'une fois. Sur 640 plans et un an d'archives, le poids
 * de la page est divisé par trois ou plus — et la page s'ouvre d'autant
 * plus vite. Le paquet reçu n'est pas modifié.
 *
 *   plansTab   : { cles: [...], lignes: [[valeur | null, ...], ...] }
 *   relevesTab : { refs: [...], vals: [...], releves: [{ ..., p: [iRef, iVal, ...], c: [...] }] }
 *   rapprochement.lignesTab : comme plansTab
 */
function compacterPaquet(paquet) {
  if (!paquet || !paquet.ok) return paquet;
  const sortie = {};
  Object.keys(paquet).forEach(function (k) { sortie[k] = paquet[k]; });

  function tableau(objets) {
    const cles = [], rang = {};
    objets.forEach(function (o) {
      Object.keys(o).forEach(function (k) {
        if (rang[k] === undefined) { rang[k] = cles.length; cles.push(k); }
      });
    });
    return {
      cles: cles,
      lignes: objets.map(function (o) {
        return cles.map(function (k) { return Object.prototype.hasOwnProperty.call(o, k) ? o[k] : null; });
      })
    };
  }

  if (Array.isArray(paquet.plans)) {
    sortie.plansTab = tableau(paquet.plans);
    delete sortie.plans;
  }

  if (Array.isArray(paquet.releves) && paquet.releves.length) {
    const refs = [], rangRef = {}, vals = [], rangVal = {};
    const indexer = function (carte) {
      if (!carte || typeof carte !== 'object') return carte;
      const plat = [];
      Object.keys(carte).forEach(function (ref) {
        const v = carte[ref];
        const cleV = JSON.stringify(v === undefined ? null : v);
        if (rangRef[ref] === undefined) { rangRef[ref] = refs.length; refs.push(ref); }
        if (rangVal[cleV] === undefined) { rangVal[cleV] = vals.length; vals.push(v); }
        plat.push(rangRef[ref], rangVal[cleV]);
      });
      return plat;
    };
    sortie.relevesTab = {
      refs: refs, vals: vals,
      releves: paquet.releves.map(function (r) {
        const o = {};
        Object.keys(r).forEach(function (k) {
          if (k === 'plans') o.p = indexer(r.plans);
          else if (k === 'plansConcept') o.c = indexer(r.plansConcept);
          else o[k] = r[k];
        });
        return o;
      })
    };
    delete sortie.releves;
  }

  if (paquet.rapprochement && Array.isArray(paquet.rapprochement.lignes)) {
    const rap = {};
    Object.keys(paquet.rapprochement).forEach(function (k) { if (k !== 'lignes') rap[k] = paquet.rapprochement[k]; });
    rap.lignesTab = tableau(paquet.rapprochement.lignes);
    sortie.rapprochement = rap;
  }
  return sortie;
}

/**
 * Le paquet du premier contrat, sérialisé pour être posé tel quel dans un
 * <script> — c'est ce que la page reçoit à l'ouverture.
 *
 * Une cellule du classeur peut contenir n'importe quoi — y compris la chaîne
 * qui ferme une balise script. Sans échappement, une seule ligne de commentaire
 * mal choisie couperait la page en deux et rien ne s'afficherait.
 */
function donneesJSONPourPage() {
  return paquetCompactJson()
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

// =====================================================================
//  DIAGNOSTIC
// =====================================================================

/**
 * À lancer depuis l'éditeur (▷ Exécuter) ou depuis le menu quand la page ne
 * s'ouvre pas. Dit ce que le script voit réellement, plutôt que de laisser
 * deviner.
 */
function diagnostic() {
  const lignes = [];
  function dire(texte) { lignes.push(texte); }

  let classeur = null;
  try {
    classeur = SpreadsheetApp.getActiveSpreadsheet();
  } catch (err) {
    classeur = null;
  }

  if (!classeur) {
    dire('✗ AUCUN CLASSEUR ATTACHÉ À CE SCRIPT.');
    dire('');
    dire('C\'est la cause la plus fréquente : le projet a été créé depuis');
    dire('script.google.com au lieu du classeur lui-même.');
    dire('');
    dire('Il faut repartir du classeur : Extensions → Apps Script, puis');
    dire('recoller les quatre fichiers dans le projet qui s\'ouvre.');
    return terminerDiagnostic(lignes);
  }
  dire('✓ Classeur : ' + classeur.getName());
  /* Les semaines se comptent dans le fuseau du projet : hors de Paris, un
     archivage du lundi matin peut tomber dans la semaine d'avant et remplacer
     son relevé (débrief 17). */
  let fuseau = '';
  try { fuseau = Session.getScriptTimeZone(); } catch (err) { fuseau = ''; }
  let decale = !!fuseau && fuseau !== 'Europe/Paris';
  if (decale) {
    /* Berlin, Bruxelles, Madrid… ont l'heure de Paris : mêmes semaines. */
    try {
      const maintenant = new Date();
      decale = Utilities.formatDate(maintenant, fuseau, 'Z') !== Utilities.formatDate(maintenant, 'Europe/Paris', 'Z');
    } catch (err) { /* sans formatDate, on le dit quand même */ }
  }
  if (decale) {
    dire('⚠ Le projet Apps Script est réglé sur le fuseau « ' + fuseau + ' », pas « Europe/Paris » : un archivage ' +
         'du lundi matin peut tomber dans la semaine d\'avant et remplacer son relevé.');
    dire('   → Apps Script → ⚙ Paramètres du projet → Fuseau horaire : (GMT+01:00) Paris.');
  }

  const nomsFichiers = [], contenus = {};
  ['Index', 'Styles', 'Javascript'].forEach(function (nom) {
    try {
      const contenu = HtmlService.createHtmlOutputFromFile(nom).getContent();
      dire('✓ Fichier « ' + nom +' » : ' + contenu.length + ' caractères');
      nomsFichiers.push(nom);
      contenus[nom] = contenu;
    } catch (err) {
      dire('✗ Fichier « ' + nom + ' » INTROUVABLE.');
      dire('   → + → HTML, et le nommer exactement « ' + nom + ' », sans .html');
    }
  });

  /* La livraison : les quatre fichiers viennent-ils de la même ? Un fichier
     resté à une livraison précédente, ou coupé au collage, donne une page
     blanche (débrief 17 : un Index d'avant avec le Javascript du jour). */
  const livraison = verifierLivraison(contenus, false);
  livraison.lignes.forEach(dire);
  /* L'application web (lien …/exec) sert la version DÉPLOYÉE, pas celle qui
     vient d'être collée : la page affiche sa livraison en bas, à comparer. */
  let urlWeb = null;
  try { urlWeb = ScriptApp.getService().getUrl(); } catch (err) { urlWeb = null; }
  if (urlWeb) {
    dire('– Application web déployée : son lien (…/exec) sert la version déployée, pas forcément celle-ci.');
    dire('   → après chaque collage : Déployer → Gérer les déploiements → ✏️ → Version : Nouvelle version → ' +
      'Déployer. En bas de la page, « Livraison ' + EDITION + ' » dit que c\'est fait.');
  }

  /* Les contrats : un onglet visible chacun. Sans aucun, rien à diagnostiquer
     — sauf le reste d'un premier import interrompu, qui dit pourquoi. */
  let contrats = [];
  try {
    contrats = listerContrats(classeur);
    if (contrats.length === 0) {
      throw new Error(messageSansContrat(classeur));
    }
  } catch (err) {
    dire('✗ Onglet de données : ' + err.message);
    direRestesDImport(classeur, dire);
    return terminerDiagnostic(lignes);
  }
  if (CONFIG.FEUILLE_DONNEES) {
    dire('✓ Contrat unique, onglet imposé par CONFIG.FEUILLE_DONNEES : « ' + contrats[0].nom + ' »');
  } else {
    dire('✓ ' + contrats.length + ' contrat(s), un onglet visible chacun : ' +
         contrats.map(function (c) { return '« ' + c.nom + ' »'; }).join(', '));
  }
  ongletsEcartes(classeur).forEach(function (e) {
    if (e.raison === 'copie') {
      dire('– Onglet « ' + e.nom + ' » écarté : une copie d\'onglet n\'est pas un contrat. Pour en faire un, ' +
           'le renommer du nom du contrat.');
    } else {
      dire('– Onglet « ' + e.nom + ' » écarté : pas de ligne d\'en-têtes d\'export dans ses ' + CONFIG.LIGNES_SCAN_ENTETE +
           ' premières lignes (au moins deux de Référence UD, ATA, Nom installation, chacun seul dans sa cellule, sur une ' +
           'ligne d\'au moins dix intitulés). Si c\'est un export, le réimporter (' + cheminImport() + ') ou le recoller entier en A1.');
    }
  });
  direRestesDImport(classeur, dire);

  let tousLisibles = true;
  contrats.forEach(function (c) {
    if (contrats.length > 1) { dire(''); dire('— Contrat « ' + c.nom + ' » —'); }
    if (!diagnostiquerContrat(classeur, c, dire)) tousLisibles = false;
  });

  /* Un onglet de contrat renommé (« Feuille 1 » devenu « HDK ») laisse son
     historique sous l'ancien nom : la page repart d'un seul relevé, le
     journal reste vide (débrief 16). L'ancien onglet « Historique_FWD »,
     à côté de plusieurs contrats, n'appartient plus à personne non plus.
     On le dit, on ne le renomme pas à la place de quelqu'un. */
  historiquesOrphelins(classeur, contrats).forEach(function (o) {
    dire('');
    const releves = o.releves + ' relevé' + (o.releves > 1 ? 's' : '');
    dire(o.ancien
      ? '⚠ L\'ancien onglet « ' + o.nom + ' » n\'est rattaché à aucun contrat (' + releves + ') :'
      : '⚠ L\'onglet d\'historique « ' + o.nom + ' » (' + releves + ') n\'est rattaché à aucun contrat :');
    dire('   ' + (o.ancien ? 'il servait quand le classeur n\'avait qu\'un contrat. Le renommer « '
                           : 'l\'onglet de son contrat a sans doute été renommé. Le renommer « ') +
         nomFeuilleHistorique('<nom du contrat>') +
         ' » lui rend ses relevés — avant le prochain archivage, qui est refusé d\'ici là.');
  });

  dire('');
  const jalons = getJalons();
  dire('✓ Jalons de configuration : ' + jalons.length);
  /* Chaque contrat a les siens (débrief 17 : HDK a les jalons du programme,
     THS aucun) : le Diagnostic dit qui voit quoi, et prévient d'un nom de
     contrat qu'aucun onglet ne porte — ce jalon-là n'apparaîtrait nulle part. */
  if (jalons.length && contrats.length) {
    dire('  par contrat : ' + contrats.map(function (c) {
      const n = getJalons(c.id).length;
      return '« ' + c.nom + ' » ' + (n ? n + ' jalon' + (n > 1 ? 's' : '') : 'aucun jalon');
    }).join(' · '));
  }
  /* Une ligne par nom de contrat introuvable, pas une par jalon : les cinq
     jalons de HDK, l'onglet renommé, ne font qu'un avertissement. */
  const introuvables = {}, ordreIntrouvables = [];
  (Array.isArray(CONFIG.JALONS) ? CONFIG.JALONS : []).forEach(function (j) {
    (contratsDuJalon(j) || []).forEach(function (nom) {
      if (contrats.some(function (c) { return normaliser(c.id) === normaliser(nom); })) return;
      const k = normaliser(nom);
      if (!introuvables[k]) { introuvables[k] = { nom: nom.slice(0, 40), textes: [] }; ordreIntrouvables.push(k); }
      introuvables[k].textes.push(String((j && j.texte) || 'Jalon').trim().slice(0, 60));
    });
  });
  ordreIntrouvables.forEach(function (k) {
    const x = introuvables[k], n = x.textes.length;
    dire('⚠ ' + (n > 1 ? n + ' jalons' : 'Jalon « ' + x.textes[0] + ' »') + ' : contrat « ' + x.nom +
         ' » — aucun contrat ne porte ce nom (onglet absent, masqué ou écarté) : ' + (n > 1 ? 'ils n\'apparaissent' : 'il n\'apparaît') +
         ' sur aucune page. Corriger contrat dans CONFIG.JALONS, ou l\'onglet.');
  });
  /* Les périmètres se vérifient contre la colonne de domaine du contrat qui
     porte les jalons — chacun le sien. */
  contrats.forEach(function (c) {
    diagnostiquerPerimetresDesJalons(c, getJalons(c.id), dire, contrats.length > 1);
  });
  dire('');
  const secondeLisible = diagnostiquerSecondeBase(classeur, dire);
  try {
    /* Le temps de chaque lecture, mesuré ici même : c'est ce qui dit où
       l'ouverture de la page passe son temps, sur ce classeur-là. */
    const secondes = function (ms) { return (ms / 1000).toFixed(1).replace('.', ',') + ' s'; };
    /* Le contrat que la page ouvre vraiment (modeleAOuvrir) : le premier qui
       porte des plans, pas forcément le premier onglet. */
    const t0 = Date.now();
    const modele = modeleAOuvrir(undefined, contrats);
    const t1 = Date.now();
    getHistorique(classeur, modele.feuille);
    const t2 = Date.now();
    getRapprochement(classeur, modele.feuille);
    const t3 = Date.now();
    /* Mesuré sans le cache : c'est le coût d'une vraie lecture qu'on veut voir. */
    const etaitFraiche = PAGE_FRAICHE;
    PAGE_FRAICHE = true;
    let poids = 0;
    try { poids = donneesJSONPourPage().length; } finally { PAGE_FRAICHE = etaitFraiche; }
    const t4 = Date.now();
    dire('✓ Paquet envoyé à la page : ' + Math.round(poids / 1024) + ' Ko' +
         (contrats.length > 1
           ? ' (contrat « ' + contrats.filter(function (c) { return c.id === modele.feuille; }).concat([{ nom: modele.feuille }])[0].nom + ' », ' +
             (modele.feuille === contrats[0].id ? 'le premier' : 'le premier qui porte des plans') +
             ' ; les autres se chargent à la demande)'
           : ''));
    dire('   préparé en ' + secondes(t4 - t3) + ' — lecture de GATES ' + secondes(t1 - t0) +
         ', de l\'historique ' + secondes(t2 - t1) + ', de la seconde base ' + secondes(t3 - t2));
    if (cacheDuClasseur()) dire('   ensuite gardé en cache (6 h) : les ouvertures suivantes ne relisent rien, tant que le classeur ne change pas');
  } catch (err) {
    dire('✗ Paquet envoyé à la page : ' + (err && err.message ? err.message : err));
    tousLisibles = false;
  }

  /* Les consultations de la page, sans nom (débrief 18). */
  const consultations = resumeConsultations_();
  dire('');
  dire('✓ Consultations de la page (sans nom ni adresse) : ' + (consultations || 'aucune encore comptée'));

  /* Les ⚠ ne bloquent rien, mais faussent ce qu'on montrerait (0 terminé,
     journal vide…) : le bilan les reprend, au lieu de conclure « tout est en
     place » juste en dessous (débrief 16). */
  const aVerifier = lignes.filter(function (l) { return l.charAt(0) === '⚠'; });
  dire('');
  if (nomsFichiers.length !== 3) dire('Il manque des fichiers HTML (voir ci-dessus).');
  else if (livraison.bloquant) dire('Les fichiers collés ne concordent pas (voir ci-dessus) : la page s\'ouvrira sur un cadre qui dit quoi recoller, tant qu\'ils ne sont pas recollés.');
  else if (!livraison.bonne) dire('Les fichiers collés ne concordent pas (voir ci-dessus) : la page s\'ouvrira avec un avertissement en tête tant qu\'ils ne sont pas recollés.');
  else if (!tousLisibles) dire('Un contrat au moins n\'est pas lisible (voir ci-dessus).');
  else if (!secondeLisible) dire('Tout est en place pour GATES : Suivi FWD → Ouvrir le tableau de bord. La seconde base, elle, ne se lit pas (voir ci-dessus).');
  else dire('Tout est en place : Suivi FWD → Ouvrir le tableau de bord.');
  if (nomsFichiers.length === 3 && livraison.bonne && tousLisibles && aVerifier.length) {
    dire('');
    dire('À vérifier avant de présenter (' + aVerifier.length + ') :');
    aVerifier.forEach(function (l) { dire('  ' + l); });
  }

  return terminerDiagnostic(lignes);
}

/**
 * Les périmètres des jalons d'un contrat contre sa colonne de domaine.
 * Un jalon dont le périmètre n'est aucune des valeurs de la colonne ne
 * ferait jamais l'échéance sous un périmètre : on le dit, avec les valeurs
 * vues, pour corriger `perimetre` dans CONFIG.JALONS. Rien à dire tant
 * qu'aucun jalon n'a de périmètre, ni quand le contrat ne se lit pas (son
 * propre diagnostic l'a déjà dit).
 */
/** Un périmètre se compare comme sur la page : sans casse, accents ni espaces. */
function clePerimetre(v) { return normaliser(v).replace(/\s+/g, ''); }

function diagnostiquerPerimetresDesJalons(contrat, jalons, dire, nommer) {
  const avecPerimetre = jalons.filter(function (j) { return j.perimetre; });
  if (!avecPerimetre.length || !contrat) return;
  const de = nommer ? ' (« ' + contrat.nom + ' »)' : '';
  let modele;
  try {
    modele = construireModele(contrat.id);
  } catch (err) {
    return;
  }
  /* Un onglet d'en-têtes seuls n'a aucune valeur de domaine à comparer : son
     propre diagnostic le dit déjà ; pas de faux « périmètre inconnu ». */
  if (!modele.plans.length) return;
  if (!modele.cleDomaine) {
    dire('⚠ ' + avecPerimetre.length + ' jalon(s) à périmètre, mais l\'onglet « ' + modele.feuille +
         ' » n\'a pas de colonne de domaine : ils ne feront l\'échéance que sur « Tout ».');
    return;
  }
  const vues = {};
  modele.plans.forEach(function (p) {
    const v = String(p[modele.cleDomaine] === undefined || p[modele.cleDomaine] === null ? '' : p[modele.cleDomaine]).trim();
    if (v && !vues[clePerimetre(v)]) vues[clePerimetre(v)] = v;
  });
  const valeurs = Object.keys(vues).map(function (k) { return vues[k]; });
  const inconnus = avecPerimetre.filter(function (j) { return !vues[clePerimetre(j.perimetre)]; });
  const colonne = modele.colonnes.filter(function (c) { return c.cle === modele.cleDomaine; })[0];
  const titre = colonne ? colonne.titre : modele.cleDomaine;
  /* Les plans qu'aucun jalon à périmètre ne compte — domaine vide, ou
     autre que ceux des jalons : seuls les jalons sans périmètre les voient.
     Un nombre seulement, jamais une valeur de cellule (débrief 17). */
  const cles = {};
  avecPerimetre.forEach(function (j) { cles[clePerimetre(j.perimetre)] = true; });
  const horsPerimetres = plansUniques(modele.plans).filter(function (p) {
    const v = p[modele.cleDomaine];
    return !cles[clePerimetre(v === undefined || v === null ? '' : v)];
  }).length;
  const dirHors = function () {
    if (!horsPerimetres) return;
    dire('  ' + horsPerimetres + ' plan' + (horsPerimetres > 1 ? 's' : '') + de + ' à « ' + titre + ' » vide ou hors des périmètres des jalons : ' +
         'aucun jalon à périmètre ne ' + (horsPerimetres > 1 ? 'les' : 'le') + ' compte, seuls les jalons sans périmètre.');
  };
  if (!inconnus.length) {
    dire('  périmètres des jalons' + de + ' : ' + avecPerimetre.map(function (j) { return j.perimetre; })
      .filter(function (v, i, t) { return t.indexOf(v) === i; }).join(', ') +
      ' — tous connus de la colonne « ' + titre + ' »');
    dirHors();
    return;
  }
  dirHors();
  inconnus.forEach(function (j) {
    dire('⚠ Jalon « ' + j.texte + ' »' + de + ' : périmètre « ' + j.perimetre + ' » inconnu de la colonne « ' + titre + ' »');
  });
  /* Même garde que pour les valeurs d'état : des valeurs courtes et peu
     nombreuses se recopient ; au-delà, ce n'est pas une colonne de domaine. */
  if (valeurs.length > 20 || valeurs.some(function (v) { return v.length > 30; })) {
    dire('   → ' + valeurs.length + ' valeurs différentes dans « ' + titre + ' » : trop, ou trop longues, pour être des périmètres — rien n\'est recopié.');
  } else {
    dire('   → valeurs vues dans « ' + titre + ' » : ' + (valeurs.length ? valeurs.slice(0, 8).join(', ') : 'aucune') +
         (valeurs.length > 8 ? ', …' : '') + ' — à recopier dans perimetre (CONFIG.JALONS).');
  }
}

/**
 * La seconde base telle que le script la voit — c'est la réponse à « je ne
 * vois pas les deux cercles » : l'onglet manque, il est vide, ou sa
 * référence ne s'y trouve pas. Renvoie faux quand un onglet est là mais ne
 * se lit pas : le bilan final le redit, pour ne pas conclure « tout est en
 * place » sous un avertissement.
 */
function diagnostiquerSecondeBase(classeur, dire) {
  /* Une seconde base par contrat : on dit, pour chacun, quel onglet est lu.
     Un onglet « SEE » tout court devant plusieurs contrats n'appartient à
     personne : on le dit, et comment le renommer. */
  let contrats = [];
  try { contrats = listerContrats(classeur); } catch (err) { contrats = []; }
  const plusieurs = contrats.length > 1;
  let tout = true;
  /* Le tri de l'extract de tous les porteurs (débrief 21) : sur quoi, et le
     PSN de chaque contrat — d'où il vient, celui de la fenêtre l'emportant. */
  const colPsn = colonnePsnSecondeBase(), filtres = filtresSecondeBase();
  if (feuilleRapprochement() && clesSecondeBase().length && (colPsn || filtres.length)) {
    const sur = (colPsn ? ['le PSN du contrat dans ' + colPsn] : [])
      .concat(filtres.map(function (f) { return f.colonne + ' ' + f.valeurs.join(' ou '); }));
    dire('– Tri de ' + feuilleRapprochement() + ' (l’extract de tous les porteurs) : ' + sur.join(', ') + '.');
    if (colPsn && contrats.length) {
      dire('   PSN : ' + contrats.map(function (c) {
        const p = psnDuContrat(c.id);
        return '« ' + c.nom + ' » ' + (p.psn.length ? p.psn.join(', ') + (p.source === 'fenetre' ? ' (tapé dans la fenêtre d’import)' : ' (configuration)')
          : p.source === 'fenetre' ? 'aucun (vidé dans la fenêtre d’import)' : 'aucun');
      }).join(' · '));
    }
  }
  (plusieurs ? contrats : [contrats[0] || null]).forEach(function (c) {
    if (!diagnostiquerSecondeBaseDe(classeur, c ? c.id : undefined, plusieurs ? ' de « ' + c.nom + ' »' : '', dire)) tout = false;
  });
  const base = feuilleRapprochement();
  if (plusieurs && base) {
    const generique = classeur.getSheets().filter(function (f) { return nomCompact(f.getName()) === nomCompact(base); })[0];
    if (generique) {
      dire('⚠ L\'onglet « ' + generique.getName() + ' » ne dit pas à quel contrat il appartient : il n\'est lu pour aucun.');
      dire('   → le renommer « ' + base + ' ' + contrats[0].nom + ' » (ou le nom de son contrat) : chaque contrat a sa base.');
    }
  }
  return tout;
}

/**
 * Un import interrompu — la fenêtre fermée en cours d'envoi, un échange
 * coupé — laisse son onglet temporaire, « HDK (import 3f2a9c) », ou l'ancien
 * mis de côté, « HDK (ancien 3f2a9c) » : ni l'un ni l'autre n'est lu. On le
 * dit ; le prochain import du même onglet les retire de lui-même.
 */
function direRestesDImport(classeur, dire) {
  classeur.getSheets().filter(function (f) { return estOngletImport(f.getName()); }).forEach(function (f) {
    const ancien = IMPORT_MOTIF.exec(f.getName())[1] === 'ancien';
    dire('⚠ L\'onglet « ' + f.getName() + ' » est le reste d\'un import interrompu' +
         (ancien ? ' (l\'ancien onglet, mis de côté le temps de l\'échange)' : '') +
         ' : il n\'est pas lu. Le supprimer, ou relancer l\'import (il le retire).');
  });
}

function diagnostiquerSecondeBaseDe(classeur, contrat, pour, dire) {
  const base = lireSecondeBase(classeur, contrat);
  const cfg = CONFIG.RAPPROCHEMENT || {};
  const nom = '« ' + (String(cfg.NOM || feuilleRapprochement() || '').trim() || 'seconde base') + ' »' + pour;
  /* Le contrat de cet onglet, nommé : celui qu'on diagnostique, ou le seul. */
  let qui = contrat || '';
  if (!qui) { try { const seuls = listerContrats(classeur); if (seuls.length === 1) qui = seuls[0].id; } catch (err) { qui = ''; } }
  const sansPsn = !!colonnePsnSecondeBase() && !!qui && !psnDuContrat(qui).psn.length;
  const geste = cheminImport() + ' : taper le PSN de « ' + qui + ' » dans la case SEE (il y est gardé), ou le mettre dans CONFIG.RAPPROCHEMENT.PSN.';
  switch (base.etat) {
    case 'sans-configuration':
      dire('– Seconde base : ' + (!base.onglet
        ? 'aucun nom d\'onglet (RAPPROCHEMENT.FEUILLE et NOM vides)'
        : 'aucune référence (RAPPROCHEMENT.CLE_REFERENCE vide)') + ' — pas de rapprochement.');
      return true;
    case 'absent':
      dire('– Seconde base ' + nom + ' : aucun onglet « ' + base.onglet + ' » — pas de rapprochement.');
      dire('   → ' + cheminImport() + ', sans ouvrir le fichier dans Excel ; ou un onglet nommé « ' +
           base.onglet + ' », l\'extract collé en A1 tel quel, avec ses colonnes ' + base.cles.join(', ') + '.');
      if (sansPsn) dire('   « ' + qui + ' » n’a pas de PSN : la fenêtre d’import ne lui fera pas de base ' + feuilleRapprochement() + ' tant qu’il n’est pas donné — ' + geste);
      return true;
    case 'sans-psn':
      dire('⚠ Seconde base ' + nom + ' : l’onglet « ' + base.onglet + ' » porte la colonne ' + base.tri.colonnePsn + ' — l’extract de tous les porteurs —, ' +
           'mais « ' + qui + ' » n’a pas de PSN : pas de comparaison tant qu’il n’est pas donné (ce seraient les plans des autres).');
      dire('   → ' + geste);
      return false;
    case 'vide':
      dire('⚠ Seconde base ' + nom + ' : l\'onglet « ' + base.onglet + ' » est vide — pas de rapprochement.');
      dire('   → ' + cheminImport() + ', ou coller l\'extract en A1.');
      return false;
    case 'sans-reference': {
      dire('⚠ Seconde base ' + nom + ' : onglet « ' + base.onglet + ' » trouvé, mais la référence (' +
           base.cles.join(' + ') + ') est introuvable dans ses ' + CONFIG.LIGNES_SCAN_ENTETE + ' premières lignes — pas de rapprochement.');
      /* La ligne prise pour en-tête ne s'imprime que si elle en est une —
         au moins un des intitulés voulus s'y lit (une colonne renommée, une
         autre manquante). Sinon c'est peut-être la première ligne de
         DONNÉES d'un extract collé sans ses en-têtes : des valeurs, qu'on
         ne recopie pas ici. */
      const manquantes = base.cles.filter(function (k) {
        return !base.entetes.some(function (e) { return normaliser(e) === normaliser(k); });
      });
      const enTete = manquantes.length < base.cles.length;
      dire(enTete
        ? '   en-têtes lus (ligne ' + base.ligneEntete + ') : ' + base.entetes.slice(0, 12).join(' | ') +
          (base.entetes.length > 12 ? ' | …' : '')
        : '   ligne ' + base.ligneEntete + ' prise pour en-tête : ' + base.entetes.length +
          ' cellule(s), aucune ne porte ' + base.cles.join(', ') + ' — l\'extract est-il collé avec ses en-têtes ?');
      /* Une colonne renommée dans l'export est le cas courant : le dire, plutôt
         que d'envoyer recoller un extract qui est déjà là, entier. */
      dire(enTete
        ? '   il manque ' + manquantes.join(', ') + ' — cette colonne a-t-elle un autre intitulé dans l\'export ?'
        : '   → vérifier que l\'extract est collé entier, en-têtes compris.');
      return false;
    }
    default:
      dire('✓ Seconde base « ' + base.rapprochement.nom + ' »' + pour + ' : onglet « ' + base.onglet + ' », ' +
           base.rapprochement.lignes.length + ' ligne(s), référence ' +
           [].concat(base.rapprochement.cleReference).join(' + ') + ' (ligne d\'en-têtes : ' + base.ligneEntete + ')');
      direTriSecondeBase(base, qui, sansPsn, geste, dire);
      return true;
  }
}

/**
 * Le tri d'une base lue, en une ligne : « SEE HDK : 60 000 lignes, 1 234
 * gardées (PSN 4530 · DIAGRAM TYPE WD) » quand l'onglet a été trié à la
 * lecture ; « 1 234 lignes, triées à l’import sur 60 000 (…) » quand c'est
 * la fenêtre qui l'a fait ; sans tri, pourquoi. Et ce qui cloche : aucune
 * ligne gardée, un PSN changé depuis l'import, un contrat sans PSN.
 */
function direTriSecondeBase(base, qui, sansPsn, geste, dire) {
  const colPsn = colonnePsnSecondeBase(), filtres = filtresSecondeBase();
  if (!colPsn && !filtres.length) return;
  const tri = base.tri, nb = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); };
  const ligne = function (n) { return nb(n) + ' ligne' + (n > 1 ? 's' : ''); };
  const onglet = base.onglet;
  if (!tri) {
    dire('   ' + onglet + ' : ' + ligne(base.rapprochement.lignes.length) + ', sans tri — l’onglet ne porte ni ' +
         (colPsn ? [colPsn] : []).concat(filtres.map(function (f) { return f.colonne; })).join(' ni ') +
         ', et n’a pas été trié par la fenêtre d’import : il est lu tel quel.');
    if (sansPsn) dire('   « ' + qui + ' » n’a pas de PSN : le prochain import de l’extract SEE ne lui fera pas de base — ' + geste);
    return;
  }
  if (tri.source === 'lecture') {
    dire('   ' + onglet + ' : ' + ligne(tri.lues) + ', ' + nb(tri.gardees) + ' gardée' + (tri.gardees > 1 ? 's' : '') + ' (' + tri.detail + ')');
    if (tri.absentes.length) dire('   ' + tri.absentes.join(', ') + ' : absente' + (tri.absentes.length > 1 ? 's' : '') + ' de l’onglet — pas de tri sur ' + (tri.absentes.length > 1 ? 'ces colonnes' : 'cette colonne') + '.');
    if (!tri.gardees && tri.lues) {
      dire('⚠ ' + onglet + ' : aucune ligne gardée sur ' + ligne(tri.lues) + (tri.psn ? ' — le PSN ' + tri.psn.join(', ') + ' n’est dans aucune ligne gardée par les autres tris : est-ce le bon ?' : '.'));
    }
    return;
  }
  dire('   ' + onglet + ' : ' + ligne(tri.gardees) + ', triée' + (tri.gardees > 1 ? 's' : '') + ' à l’import' +
       (tri.lues !== null && tri.lues !== undefined ? ' sur ' + ligne(tri.lues) : '') + ' (' + tri.detail + ')');
  if (colPsn && tri.psn && !memesPsn(tri.psn, tri.psnContrat)) {
    dire('⚠ ' + onglet + ' a été trié à l’import sur le PSN ' + tri.psn.join(', ') + ', mais celui de « ' + qui + ' » est maintenant ' +
         (tri.psnContrat.length ? tri.psnContrat.join(', ') : 'vide') + ' : réimporter l’extract SEE (' + cheminImport() + ').');
  }
}

/**
 * Le diagnostic d'un contrat : son onglet, ses colonnes, ses comptes, son
 * historique. Renvoie faux quand l'onglet n'est pas exploitable — le
 * diagnostic continue avec les autres contrats plutôt que de s'arrêter.
 */
/* Les valeurs d'une colonne suivie, avec leur compte et ce qu'elles
   valent pour la page (fini ou pas) : c'est ce qui permet de vérifier que
   « Validé » compte bien comme fini. Seulement des valeurs d'état — peu
   nombreuses et courtes ; une colonne de texte libre ne se recopie pas. */
function direValeurs(dire, plans, cle, estConcept) {
  const par = {}, ordre = [];
  plans.forEach(function (p) {
    const brut = String(p[cle] === null || p[cle] === undefined ? '' : p[cle]).trim();
    const k = normaliser(brut);
    if (!(k in par)) { par[k] = { brut: brut, n: 0, famille: classerFWD(brut) }; ordre.push(k); }
    par[k].n++;
  });
  const remplies = ordre.filter(function (k) { return par[k].famille !== 'vide'; });
  /* La règle de la page (débrief 19) : seul un mot rangé « en cours » faute
     d'être reconnu peut cacher un « validé » inconnu ; des plans tous « à
     faire » ou vides n'ont rien de suspect, et le concept harnais a son
     vocabulaire connu — aucun « Traité » y est un vrai zéro. */
  const aucunFini = !estConcept && remplies.some(function (k) { return par[k].famille === 'encours'; }) &&
    !remplies.some(function (k) { return par[k].famille === 'termine'; });
  if (ordre.length > 20 || ordre.some(function (k) { return par[k].brut.length > 30; })) {
    dire('  ' + ordre.length + ' valeurs différentes : trop, ou trop longues, pour être des états — rien n\'est recopié.');
  } else {
    /* Chaque valeur avec la façon dont elle est comptée : c'est ce qui dit,
       d'un coup d'œil, qu'un mot « validé » n'est pas reconnu. */
    const MOT = { termine: 'validé', encours: 'en cours', afaire: 'à faire', vide: 'non renseigné' };
    ordre.sort(function (a, b) { return par[b].n - par[a].n; });
    dire('  valeurs lues (comptées comme) : ' + ordre.map(function (k) {
      const v = par[k];
      return (v.brut === '' ? '(vide)' : '« ' + v.brut + ' »') + ' ' + v.n + ' → ' + MOT[v.famille];
    }).join(' · '));
  }
  if (aucunFini) {
    dire('⚠ Aucune valeur n\'est comptée comme validée : la page dira « 0 validé ». Si l\'une de ces valeurs veut dire « validé »,');
    dire('   l\'ajouter à CONFIG.VALEURS_FINIES (aujourd\'hui : ' +
         (CONFIG.VALEURS_FINIES && CONFIG.VALEURS_FINIES.length ? CONFIG.VALEURS_FINIES : ['Validé']).join(', ') + ').');
  }
}

function diagnostiquerContrat(classeur, contrat, dire) {
  let feuille = null;
  try {
    feuille = getFeuilleDonnees(classeur, contrat.id);
    dire('✓ Onglet de données : « ' + feuille.getName() + ' »');
  } catch (err) {
    dire('✗ Onglet de données : ' + err.message);
    return false;
  }

  try {
    const donnees = feuille.getDataRange().getDisplayValues();
    dire('  ' + donnees.length + ' lignes lues dans l\'onglet');
    if (donnees.length === 0) {
      dire('✗ L\'onglet est vide : importer l\'export GATES (' + cheminImport() + '), ou le coller en A1.');
      return false;
    }
    const iEntete = detecterLigneEntete(donnees);
    /* Confidentialité : on ne recopie la ligne que si c'est bien une ligne
       d'intitulés. Devinée (aucun intitulé attendu), ce peut être une ligne
       de plan — libellés, commentaires : rien n'en sort. */
    if (ligneAIntitule(donnees[iEntete])) {
      dire('✓ Ligne d\'en-têtes : ligne ' + (iEntete + 1));
      dire('  ' + donnees[iEntete].filter(function (e) { return String(e).trim(); }).join(' | '));
    } else {
      dire('✗ Ligne d\'en-têtes introuvable : aucun intitulé attendu (Référence UD, ATA, Nom installation) dans les ' +
           CONFIG.LIGNES_SCAN_ENTETE + ' premières lignes.');
      dire('   → réimporter l\'export (' + cheminImport() + '), ou le recoller entier en A1, avec ses lignes de groupes et');
      dire('     d\'en-têtes. Le reste de cet onglet n\'est pas détaillé : ses « intitulés » seraient des cellules de plans,');
      dire('     qui ne sortent pas d\'ici.');
      return false;
    }

    const modele = construireModele(contrat.id);
    /* Une référence répétée ne compte qu'une fois, comme dans le relevé et sur la page. */
    const uniques = plansUniques(modele.plans);
    /* En-têtes seuls (un contrat préparé d'avance, un export revenu vide) :
       pas un ✓ — et rien à archiver tant que l'export n'y est pas. */
    const sansPlan = !uniques.length;
    if (sansPlan) {
      dire('⚠ L\'onglet ne porte aucun plan (en-têtes seuls) : y importer l\'export GATES (' + cheminImport() + ') ou le coller en A1.');
    } else {
      dire('✓ ' + modele.colonnes.length + ' colonnes, ' + uniques.length + ' plans' +
           (uniques.length < modele.plans.length ? ' (' + modele.plans.length + ' lignes)' : ''));
    }

    const colFWD = modele.colonnes.filter(function (c) { return c.cle === 'avancement'; })[0];
    if (modele.avertissement) {
      dire('✗ ' + modele.avertissement);
      dire('   → la page s\'affichera, mais tout sera « non renseigné », et rien ne sera archivé.');
      if (modele.fwdDemandeeAbsente) direColonnesProches(dire, modele.colonnes, CONFIG.COLONNE_FWD);
    } else {
      dire('✓ Avancement FWD : colonne « ' + colFWD.titre + ' »' +
           (colFWD.groupe ? ', groupe « ' + colFWD.groupe + ' »' : '') +
           (CONFIG.COLONNE_FWD ? ' — celle de CONFIG.COLONNE_FWD' : ' — trouvée d\'elle-même (CONFIG.COLONNE_FWD est vide)'));
      direDoublon(dire, modele.colonnes, CONFIG.COLONNE_FWD);
      if (!sansPlan) {
        const compte = { termine: 0, encours: 0, afaire: 0, vide: 0 };
        uniques.forEach(function (p) { compte[classerFWD(p.avancement)]++; });
        dire('  ' + compte.termine + ' validés, ' + compte.encours + ' en cours, ' +
             compte.afaire + ' à faire, ' + compte.vide + ' non renseignés');
        direValeurs(dire, uniques, 'avancement');
      }
    }
    if (CONFIG.COLONNE_CONCEPT) {
      const colConcept = modele.cleConcept ? modele.colonnes.filter(function (c) { return c.cle === modele.cleConcept; })[0] : null;
      if (colConcept) {
        const compteC = { termine: 0, encours: 0, afaire: 0, vide: 0 };
        uniques.forEach(function (p) { compteC[classerFWD(p[modele.cleConcept])]++; });
        dire('✓ Concept harnais : colonne « ' + colConcept.titre + ' »' + (colConcept.groupe ? ', groupe « ' + colConcept.groupe + ' »' : ''));
        if (!sansPlan) {
          dire('  ' + compteC.termine + ' validés, ' + compteC.encours + ' en cours, ' +
               compteC.afaire + ' à faire, ' + compteC.vide + ' non renseignés');
          direValeurs(dire, uniques, modele.cleConcept, true);
        }
        direDoublon(dire, modele.colonnes, CONFIG.COLONNE_CONCEPT);
      } else {
        dire('✗ ' + modele.avertissementConcept);
        direColonnesProches(dire, modele.colonnes, CONFIG.COLONNE_CONCEPT);
      }
    }

    const colRef = modele.colonnes.filter(function (c) { return c.fige; })[0];
    dire('✓ Référence figée : colonne « ' + (colRef ? colRef.titre : '?') + ' »');
    if (modele.lignesIgnorees > 0) {
      dire('  ' + modele.lignesIgnorees + ' ligne(s) sans référence ignorée(s)');
    }
    if (modele.doublons > 0) {
      dire('⚠ ' + modele.doublons + ' ligne(s) répètent une référence déjà vue : un export collé par-dessus l\'ancien, sans Ctrl+A puis Suppr ?');
      dire('   Seule la première ligne de chaque référence compte, comme sur la page et dans le relevé. Réimporter l\'export (' +
           cheminImport() + ' : l\'onglet est remplacé en entier), ou le recoller sur un onglet vidé.');
    }
    if (colRef && /^Colonne \d+$/.test(colRef.titre)) {
      dire('⚠ La référence est lue dans « ' + colRef.titre + ' », une colonne sans intitulé : l\'en-tête « Référence UD » n\'a pas été trouvé.');
    }
    const titresDim = modele.colonnes
      .filter(function (c) { return c.dim; })
      .map(function (c) { return c.titre; });
    dire('✓ Analyse par : ' + (titresDim.length ? titresDim.join(' · ') : 'aucune colonne')
         + (modele.cleDate ? ' · ancienneté' : ''));
    dire('  Ouverte par défaut : ' + (modele.dimParDefaut || 'aucune'));
    dire('  Tableau ouvert sur les ' + modele.colonnes.length +
         ' colonnes de la feuille, dans son ordre');

    const feuilleHisto = getFeuilleHistorique(classeur, contrat.id, false);
    const histo = getHistorique(classeur, contrat.id);
    dire('✓ Relevés archivés : ' + histo.length + (feuilleHisto
      ? ' (onglet « ' + feuilleHisto.getName() + ' »)'
      : ' (onglet « ' + nomFeuilleHistorique(contrat.id) + ' », créé au premier archivage)'));
    if (histo.length === 0) {
      /* Sans plan, l'archivage refuserait : on ne l'envoie pas archiver. */
      if (!sansPlan) {
        dire('   → Suivi FWD → Archiver le relevé de cette semaine.');
        dire('     Sans relevé, pas de courbe ni de fin estimée.');
      }
    } else {
      dire('  du ' + histo[0].semaine + ' au ' + histo[histo.length - 1].semaine);
      const cellulesCarte = feuilleHisto.getLastColumn() - ENTETES_HISTORIQUE.length + 1;
      if (cellulesCarte > 1) {
        dire('  carte plan par plan sur ' + cellulesCarte + ' cellules par relevé, au plus');
      }
      direJournal(dire, histo, modele, sansPlan);
    }
    return true;
  } catch (err) {
    dire('✗ ERREUR : ' + (err && err.message ? err.message : err));
    if (err && err.stack) dire(String(err.stack).split('\n').slice(0, 3).join('\n'));
    return false;
  }
}

/**
 * Une colonne demandée introuvable : les colonnes de même intitulé, avec
 * leur groupe, pour voir d'un coup d'œil si c'est le groupe qui a changé
 * de nom. Seulement des intitulés d'en-tête, jamais de contenu de cellule.
 */
function direColonnesProches(dire, colonnes, designation) {
  const voulu = normaliser(designation).split('>');
  const titre = voulu[voulu.length - 1].trim();
  const memes = colonnes.filter(function (c) { return normaliser(c.titre) === titre; });
  if (!memes.length) {
    dire('   Aucune colonne intitulée « ' + titre + ' » dans l\'en-tête.');
    return;
  }
  dire('   Colonnes intitulées « ' + memes[0].titre + ' », par groupe : ' +
       memes.map(function (c) { return '« ' + (c.groupe || 'sans groupe') + ' »'; }).join(', ') + '.');
  dire('   → corriger le groupe dans CONFIG (partie avant « > ») s\'il a changé de nom dans l\'export.');
}

/** Deux colonnes répondant à la même désignation : la première est suivie, on le dit. */
function direDoublon(dire, colonnes, designation) {
  const voulu = normaliser(designation);
  if (!voulu) return;
  const coupe = voulu.split('>');
  const n = colonnes.filter(function (c) {
    return coupe.length === 2
      ? normaliser(c.titre) === coupe[1].trim() && normaliser(c.groupe) === coupe[0].trim()
      : normaliser(c.titre) === voulu;
  }).length;
  if (n > 1) dire('⚠ ' + n + ' colonnes répondent à « ' + designation + ' » : la page suit la première, à gauche.');
}

/**
 * Ce que le journal aura à dire : combien de plans ont changé de valeur entre
 * les deux derniers relevés, si la semaine en cours est archivée, et de
 * combien l'extract du jour s'écarte du dernier relevé. Des comptes
 * seulement, jamais une valeur ni une référence.
 */
function direJournal(dire, histo, modele, sansPlan) {
  const semaine = numeroSemaineISO(new Date());
  const dernier = histo[histo.length - 1];
  /* Un onglet sans plan ne s'archive pas : ni « archiver », ni un écart
     avec l'extract du jour, qui n'a rien. */
  if (dernier.semaine !== semaine && !sansPlan) {
    dire('  pas encore de relevé pour la semaine en cours (' + semaine + ') : Suivi FWD → Archiver le relevé de cette semaine.');
  }
  if (histo.length === 1) {
    dire('  un seul relevé : le journal des changements se remplira au suivant (deux archivages la même semaine n\'en font qu\'un).');
  } else {
    const avant = histo[histo.length - 2];
    if (!avant.plans || !dernier.plans) {
      dire('⚠ ' + (!avant.plans ? avant.semaine : dernier.semaine) + ' n\'a pas de carte plan par plan : le journal ne peut rien comparer entre '
           + avant.semaine + ' et ' + dernier.semaine + '.');
    } else {
      const n = plansQuiChangent(avant.plans, dernier.plans);
      dire('  entre ' + avant.semaine + ' et ' + dernier.semaine + ' : ' + n + ' plan(s) ont changé de valeur — c\'est ce que dit le journal.');
      if (n === 0) {
        dire('⚠ Les deux derniers relevés sont identiques, plan par plan : le même extract a sans doute été archivé deux fois.');
        dire('   Le journal restera vide. Importer le dernier export de GATES (' + cheminImport() + ', qui archive dans la foulée),');
        dire('   ou le recoller, puis archiver de nouveau.');
      }
    }
  }
  /* Avant le 22 septembre (débrief 8), la colonne suivie se devinait seule :
     « Réalisation FWD > Avancement », pas le bloc HDK AA 011. Un relevé de
     cette époque, relu aujourd'hui, fabrique de faux passages et de faux
     reculs (débrief 17). */
  histo.filter(function (r) { return /^\d{4}-\d{2}-\d{2}$/.test(r.date) && r.date < '2026-09-23'; }).forEach(function (r) {
    dire('⚠ Le relevé ' + r.semaine + ' date du ' + r.date + ' : avant le 22 septembre, la page suivait « Réalisation FWD > ' +
         'Avancement », pas « ' + CONFIG.COLONNE_FWD + ' ».');
    dire('   S\'il fausse la courbe ou le journal (faux reculs), supprimer sa ligne dans l\'onglet d\'historique.');
  });
  if (dernier.plans && !sansPlan) {
    const jour = {};
    plansUniques(modele.plans).forEach(function (p) { jour[p.reference] = p.avancement; });
    dire('  l\'extract du jour s\'écarte du dernier relevé (' + dernier.semaine + ') sur ' + plansQuiChangent(dernier.plans, jour) + ' plan(s).');
  }
}

/** Combien de plans diffèrent entre deux cartes { référence: valeur } : autre valeur, apparu, disparu. */
function plansQuiChangent(a, b) {
  let n = 0;
  Object.keys(b).forEach(function (r) {
    if (!Object.prototype.hasOwnProperty.call(a, r) || normaliser(a[r]) !== normaliser(b[r])) n++;
  });
  Object.keys(a).forEach(function (r) { if (!Object.prototype.hasOwnProperty.call(b, r)) n++; });
  return n;
}

/**
 * Les fichiers collés tiennent-ils ensemble ? (débrief 17 — une page blanche
 * au bureau : un Index d'avant avec le Javascript du jour.) Chaque fichier
 * porte la livraison posée par la construction : l'Index dans son premier
 * script (Apps Script ignore les balises meta d'un fichier), les Styles dans
 * une propriété CSS, le Javascript dans sa première déclaration. Et chacun
 * doit être ENTIER : un <style> ou un <script> resté ouvert avale tout ce qui
 * le suit, et la page reste vide sans une erreur. Tous les « < » du code
 * étant échappés, le Javascript n'a qu'une balise d'ouverture et une de
 * fermeture — deux, c'est deux copies (collé sans tout effacer).
 *
 * `contenus` : { Index, Styles, Javascript }, le texte des fichiers trouvés
 * — tel qu'Apps Script le rend, SANS SES COMMENTAIRES : rien ici ne s'appuie
 * sur un commentaire (débrief 17 : la marque de fin en était un, et un
 * Javascript entier passait pour coupé). Renvoie les lignes à dire, si tout
 * concorde (`bonne`), si la page a toutes les chances de ne pas tenir
 * (`bloquant` : fichier abîmé, ou Index et Javascript de livraisons
 * différentes — la page le dit elle-même en tête), et si un fichier manque
 * (`manquant` : seul cas où l'ouverture sert une page d'explication au lieu
 * du tableau de bord, qui ne pourrait pas se construire). `direManquants` :
 * dire aussi les fichiers introuvables (le Diagnostic les dit de son côté).
 */
function verifierLivraison(contenus, direManquants) {
  const marques = {
    Index: /SUIVI_FWD_LIVRAISON_INDEX = '([^']*)';/,
    Styles: /--suivi-fwd-edition:\s*"([^"]*)"/,
    Javascript: /var EDITION = '([^']*)';/
  };
  const lignes = [];
  let bonne = true, bloquant = false, manquant = false;
  function ecart(nom, texte, geste, bloque) {
    bonne = false;
    if (bloque) bloquant = true;
    lignes.push('✗ « ' + nom + ' » ' + texte);
    lignes.push('   → ' + geste);
  }
  function recoller(nom) {
    return 'le recoller en entier depuis la dernière livraison : dans ' + nom + '.html.txt, Ctrl+A, Ctrl+C ; ' +
      'dans Apps Script, « ' + nom + ' », tout effacer, Ctrl+V, Ctrl+S.';
  }
  function compter(texte, motif) { return texte.split(motif).length - 1; }
  Object.keys(marques).forEach(function (nom) {
    const texte = contenus[nom];
    if (typeof texte !== 'string') {
      bonne = false;
      bloquant = true;
      manquant = true;
      if (direManquants) ecart(nom, 'est introuvable dans le projet.', '+ → HTML, le nommer exactement « ' + nom +
        ' » (sans .html), puis y coller ' + nom + '.html.txt.', true);
      return;
    }
    const lignesDuFichier = texte.split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean);
    const premiere = lignesDuFichier[0] || '', derniere = lignesDuFichier[lignesDuFichier.length - 1] || '';
    const m = marques[nom].exec(texte);
    const edition = m ? m[1] : '';
    if (edition !== EDITION) {
      ecart(nom, 'ne vient pas de la même livraison que Code (' +
        (edition ? 'livraison ' + edition : 'sans livraison marquée : d\'avant le 29 septembre 2026') +
        ', Code : ' + EDITION + ').', recoller(nom) + ' Sinon la page s\'ouvre blanche ou incomplète.', nom !== 'Styles');
    }
    /* Bloquant : ce qui empêche la page de tenir — deux copies, un début ou
       une fin perdus. Du texte inerte autour des balises (le squelette d'un
       fichier créé par + → HTML, collé sans tout effacer) ne l'empêche pas :
       on le dit sans bloquer. */
    const iMarque = m ? m.index : -1;
    if (nom === 'Javascript') {
      const iOuverture = texte.indexOf('<script>');
      if (compter(texte, '<script') > 1 || compter(texte, FIN_DU_JAVASCRIPT) > 1) {
        ecart(nom, 'contient deux copies — collé sans tout effacer ?', recoller(nom), true);
      } else if (iOuverture === -1 || (iMarque !== -1 && iOuverture > iMarque)) {
        ecart(nom, 'a perdu sa première ligne « <script> » — début perdu au collage ?', recoller(nom), true);
      } else if (!new RegExp(FIN_DU_JAVASCRIPT + "\\s*=\\s*'[^']*';?\\s*</script>").test(texte) &&
                 !/\}\)\(\);\s*<\/script>\s*$/.test(texte)) {
        ecart(nom, 'est incomplet : sa fin manque (' + texte.length + ' caractères) — collé en partie ?', recoller(nom), true);
      } else if (premiere !== '<script>' || derniere !== '</script>') {
        ecart(nom, 'porte du texte hors de « <script> … </script> » (le squelette d\'un fichier créé par + → HTML ?).',
          recoller(nom), false);
      }
    } else if (nom === 'Styles') {
      const iOuverture = texte.indexOf('<style>'), iFermeture = texte.lastIndexOf('</style>');
      if (compter(texte, '<style') > 1) ecart(nom, 'contient deux copies — collé sans tout effacer ?', recoller(nom), true);
      else if (iOuverture === -1 || iFermeture === -1 || (iMarque !== -1 && (iOuverture > iMarque || iFermeture < iMarque))) {
        ecart(nom, 'est incomplet (il doit commencer par « <style> » et finir par « </style> ») — collé en partie ?',
          recoller(nom), true);
      } else if (premiere !== '<style>' || derniere !== '</style>') {
        ecart(nom, 'porte du texte hors de « <style> … </style> » (le squelette d\'un fichier créé par + → HTML ?).',
          recoller(nom), false);
      }
    } else if (texte.indexOf("include('Styles')") === -1 || texte.indexOf("include('Javascript')") === -1 ||
               texte.indexOf('donneesJSONPourPage()') === -1 || derniere !== '</html>') {
      ecart(nom, 'est incomplet ou abîmé (il doit inclure Styles et Javascript, et finir par « </html> »).',
        recoller(nom), true);
    }
  });
  if (bonne) lignes.push('✓ Livraison ' + EDITION + ' : Code, Index, Styles et Javascript concordent, et sont entiers.');
  return { lignes: lignes, bonne: bonne, bloquant: bloquant, manquant: manquant };
}

/** La dernière ligne du fichier Javascript, posée par la construction. */
/* Une instruction, pas un commentaire : Apps Script retire les commentaires. */
const FIN_DU_JAVASCRIPT = 'SUIVI_FWD_FIN';

function terminerDiagnostic(lignes) {
  const rapport = lignes.join('\n');
  console.log(rapport);
  try {
    SpreadsheetApp.getUi().alert('Diagnostic — Suivi FWD', rapport,
      SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (err) {
    // Lancé depuis l'éditeur sans interface : le journal d'exécution suffit.
  }
  return rapport;
}

// =====================================================================
//  HISTORIQUE — UN ONGLET PAR CONTRAT
//  L'export ne contient que l'état du jour : on ne sait pas quand un plan est
//  passé à 100 %. L'historique ne peut donc pas être reconstitué, seulement
//  accumulé — un relevé par semaine ISO, par contrat, dans l'onglet masqué
//  « Historique_FWD_<nom du contrat> ». Rien n'est jamais supprimé.
// =====================================================================

/** Le nom de l'onglet d'historique d'un contrat. */
function nomFeuilleHistorique(contrat) {
  return CONFIG.FEUILLE_HISTORIQUE + '_' + String(contrat);
}

/**
 * L'identifiant d'un contrat : le nom de son onglet de données, résolu comme
 * partout ailleurs — sans tenir compte de la casse ni des accents, le premier
 * du classeur si aucun n'est donné. Sinon « x1 » n'aurait pas l'historique de
 * « X1 ». Un identifiant inconnu est une erreur franche, pas un onglet
 * d'historique fantôme.
 */
function idContrat(classeur, contrat) {
  return getFeuilleDonnees(classeur, contrat).getName();
}

/**
 * L'onglet d'historique d'un contrat.
 *
 * Rétro-compatibilité : un classeur à contrat unique qui porte encore
 * l'ancien onglet « Historique_FWD » tout court le garde — ses relevés sont
 * ceux de ce contrat, rien n'est renommé ni recopié. Dès qu'il y a plusieurs
 * contrats, chacun a le sien, et l'ancien onglet n'est plus lu : il devient
 * orphelin (historiquesOrphelins) — la page et le diagnostic disent comment
 * le rattacher. L'onglet propre au contrat l'emporte toujours
 * s'il existe.
 */
function getFeuilleHistorique(classeur, contrat, creerSiAbsente) {
  const id = idContrat(classeur, contrat);
  const nom = nomFeuilleHistorique(id);
  let feuille = classeur.getSheetByName(nom);
  if (!feuille && contratUnique(classeur)) {
    feuille = classeur.getSheetByName(CONFIG.FEUILLE_HISTORIQUE);
  }
  if (!feuille && creerSiAbsente) {
    feuille = classeur.insertSheet(nom);
    feuille.appendRow(ENTETES_HISTORIQUE);
    feuille.getRange(1, 1, 1, ENTETES_HISTORIQUE.length).setFontWeight('bold');
    feuille.setFrozenRows(1);
    feuille.hideSheet();
  }
  return feuille;
}

/**
 * Les onglets d'historique rattachés à aucun contrat, [{ nom, releves }] — le
 * plus souvent celui d'un onglet de contrat renommé (« Feuille 1 » devenu
 * « HDK ») : ses relevés ne s'affichent plus nulle part, et le prochain
 * archivage ouvrirait un second historique à côté (débrief 17).
 */
function historiquesOrphelins(classeur, contrats) {
  /* N'est orphelin que l'historique dont l'onglet n'existe PLUS : un onglet
     de contrat masqué, une « Copie de HDK » ou un tableau croisé écartés
     gardent le leur — ce ne sont pas des renommages. Un onglet vide qui
     reprendrait l'ancien nom ne compte pas. */
  const attendus = {};
  classeur.getSheets().forEach(function (f) {
    if (!estOngletHistorique(f.getName()) && f.getLastRow() > 0) attendus[normaliser(nomFeuilleHistorique(f.getName()))] = true;
  });
  contrats.forEach(function (c) { attendus[normaliser(nomFeuilleHistorique(c.id))] = true; });
  /* L'ancien onglet sans suffixe, « Historique_FWD », est celui d'un
     classeur à contrat unique. Dès qu'il y a plusieurs contrats, plus
     personne ne le lit : orphelin lui aussi — sinon tout l'historique
     disparaissait de la page sans un mot, et le vendredi ouvrait
     « Historique_FWD_HDK » à côté (l'historique coupé en deux, le renommage
     devenu impossible). */
  const ancien = normaliser(CONFIG.FEUILLE_HISTORIQUE);
  return classeur.getSheets()
    .filter(function (f) {
      const n = normaliser(f.getName());
      if (n === ancien) return contrats.length > 1;
      return estOngletHistorique(f.getName()) && !attendus[n];
    })
    .map(function (f) {
      const o = { nom: f.getName(), releves: Math.max(0, f.getLastRow() - 1) };
      if (normaliser(f.getName()) === ancien) o.ancien = true;
      return o;
    });
}

/** Les contrats qui n'ont pas encore d'onglet d'historique : ceux qu'un orphelin empêche d'archiver. */
function contratsSansHistorique(classeur, contrats) {
  return contrats.filter(function (c) { return !getFeuilleHistorique(classeur, c.id, false); });
}

/**
 * Ce que la page dit des historiques orphelins, au-dessus de la barre. Le
 * renommage n'est proposé que vers un contrat qui n'a pas encore
 * d'historique — le contrat affiché d'abord : c'est lui dont l'archivage est
 * refusé d'ici là (archiverContrat_). Sinon, rien à faire.
 */
function avisOrphelins(orphelins, contrat, sansHistorique) {
  if (!orphelins.length) return '';
  const cible = sansHistorique.indexOf(contrat) !== -1 ? contrat : sansHistorique[0];
  return orphelins.map(function (o) {
    return (o.ancien ? 'L\'ancien onglet d\'historique « ' : 'L\'onglet d\'historique « ') + o.nom + ' » (' + o.releves +
      ' relevé' + (o.releves > 1 ? 's' : '') + ') n\'est rattaché à aucun contrat — ' +
      (o.ancien ? 'il servait quand le classeur n\'en avait qu\'un.' : 'un onglet de contrat renommé ?');
  }).join(' ') + (cible
    ? ' S\'il est celui de « ' + cible + ' », le renommer « ' + nomFeuilleHistorique(cible) + ' » lui rend ses relevés ' +
      '(Affichage → Onglets masqués pour le voir) ; d\'ici là, « ' + cible + ' » ne s\'archive pas.'
    : ' Ses relevés ne s\'affichent nulle part ; il peut rester tel quel.');
}

/** Vrai si le classeur ne porte qu'un contrat. */
function contratUnique(classeur) {
  try { return listerContrats(classeur).length === 1; } catch (err) { return false; }
}

/** Lit l'historique d'un contrat : un objet par relevé, trié par semaine. */
function getHistorique(classeur, contrat) {
  const feuille = getFeuilleHistorique(classeur, contrat, false);
  if (!feuille || feuille.getLastRow() < 2) return [];

  /* La carte plan par plan d'un relevé occupe une cellule ou plusieurs, à
     partir de la colonne « Plans » : on lit jusqu'à la dernière colonne
     occupée de l'onglet et on recolle. */
  const nbColonnes = Math.max(ENTETES_HISTORIQUE.length, feuille.getLastColumn());
  const valeurs = feuille.getRange(2, 1, feuille.getLastRow() - 1, nbColonnes).getValues();
  const parSemaine = {};

  valeurs.forEach(function (ligne) {
    const semaine = normaliserSemaine(ligne[0]);
    if (!semaine) return;
    parSemaine[semaine] = {          // le dernier relevé d'une semaine l'emporte
      semaine: semaine,
      date: ligne[1] instanceof Date ? ligne[1].toISOString().slice(0, 10) : String(ligne[1] || ''),
      total: Number(ligne[2]) || 0,
      termine: Number(ligne[3]) || 0,
      encours: Number(ligne[4]) || 0,
      afaire: Number(ligne[5]) || 0,
      vide: Number(ligne[6]) || 0,
      groupes: analyserJson(ligne[7]) || {}
    };
    const cartes = separerCartes(analyserJson(recoller(ligne.slice(ENTETES_HISTORIQUE.length - 1))));
    parSemaine[semaine].plans = cartes.plans;
    if (cartes.plansConcept) parSemaine[semaine].plansConcept = cartes.plansConcept;
  });

  return Object.keys(parSemaine).sort().map(function (s) { return parSemaine[s]; });
}

/**
 * Une carte archivée, en deux cartes : la définition électrique (plans) et,
 * si le relevé l'a gardé, le concept harnais (plansConcept). Un relevé
 * d'avant l'interrupteur porte des chaînes : il n'a pas de concept, et ne
 * s'invente pas.
 */
function separerCartes(carte) {
  if (!carte || typeof carte !== 'object' || Array.isArray(carte)) return { plans: carte || null, plansConcept: null };
  const def = {}, concept = {};
  let avecConcept = false;
  Object.keys(carte).forEach(function (ref) {
    const v = carte[ref];
    if (Array.isArray(v)) {
      def[ref] = String(v[0] === null || v[0] === undefined ? '' : v[0]);
      concept[ref] = String(v[1] === null || v[1] === undefined ? '' : v[1]);
      avecConcept = true;
    } else {
      def[ref] = v;
    }
  });
  return { plans: def, plansConcept: avecConcept ? concept : null };
}

function analyserJson(valeur) {
  if (!valeur) return null;
  try { return JSON.parse(valeur); } catch (err) { return null; }
}

/**
 * Recolle les cellules d'une carte plan par plan, dans l'ordre des colonnes.
 * Une seule cellule (ancien relevé) se lit telle quelle ; des cellules vides
 * donnent une chaîne vide, donc pas de carte.
 */
function recoller(cellules) {
  return cellules.map(function (v) { return v === null || v === undefined ? '' : String(v); }).join('');
}

/**
 * L'année et le mois d'une date de cellule, { annee, mois } — ou null. La
 * cellule arrive telle que le classeur l'affiche : « 16/07/2020 » sur une
 * feuille française, « 2020-07-16 » ailleurs. Ne lire que l'année d'abord
 * rangeait tous les plans d'un classeur français dans « — » au relevé.
 * ⚠ Même règle que anneeEtMois et ordreDesDates du script de la page : toute
 *    modification va des deux côtés.
 */
function anneeEtMois(valeur, moisDabord) {
  const t = String(valeur === null || valeur === undefined ? '' : valeur).trim();
  const iso = /^(\d{4})[-\/.](\d{1,2})/.exec(t);
  if (iso) {
    const mi = Number(iso[2]);
    return mi >= 1 && mi <= 12 ? { annee: Number(iso[1]), mois: mi } : null;
  }
  const fr = /^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2,4})/.exec(t);
  if (!fr) return null;
  let an = Number(fr[3]);
  if (an < 100) an += an < 70 ? 2000 : 1900;
  /* Jour puis mois, comme en France — sauf si le premier nombre dépasse
     douze (c'est alors le jour), ou si la colonne s'écrit mois/jour. */
  const a = Number(fr[1]), b = Number(fr[2]);
  const mois = a > 12 ? b : (b > 12 ? a : (moisDabord ? a : b));
  return mois >= 1 && mois <= 12 ? { annee: an, mois: mois } : null;
}

/**
 * Une colonne de dates écrite mois/jour (un classeur réglé en anglais) ? Les
 * cellules dont un nombre dépasse douze disent l'ordre ; à défaut, le jour
 * d'abord, comme en France.
 */
function ordreDesDates(plans, cle) {
  if (!cle) return false;
  let jourDabord = 0, moisDabord = 0;
  plans.forEach(function (p) {
    const m = /^(\d{1,2})[-\/.](\d{1,2})[-\/.]\d{2,4}/.exec(String(p[cle] === null || p[cle] === undefined ? '' : p[cle]).trim());
    if (!m) return;
    if (Number(m[1]) > 12) jourDabord++;
    else if (Number(m[2]) > 12) moisDabord++;
  });
  return moisDabord > jourDabord;
}

/** Ancienneté d'un plan, en toutes lettres — même découpage que côté page. */
function ancienneteDepuis(valeur, reference, moisDabord) {
  const v = anneeEtMois(valeur, moisDabord);
  if (!v) return '—';
  const mois = (reference.getUTCFullYear() - v.annee) * 12 +
               (reference.getUTCMonth() + 1 - v.mois);
  if (mois >= 6) return 'plus de 6 mois';
  if (mois >= 3) return '3 à 6 mois';
  if (mois >= 1) return '1 à 3 mois';
  return 'moins d’un mois';
}

/** Compte l'état du jour d'un contrat : global, par dimension, et plan par plan. */
function compterAvancements(contrat) {
  const modele = construireModele(contrat);
  /* Sans la colonne suivie, chaque plan serait archivé « non renseigné » :
     une semaine fausse dans l'historique, des reculs partout la semaine
     d'après. Mieux vaut ne rien archiver et le dire. */
  if (modele.avertissement) throw new Error(modele.avertissement);
  if (modele.avertissementConcept) throw new Error(modele.avertissementConcept);
  /* Un onglet qui n'a que ses en-têtes (un export revenu vide, un contrat
     préparé d'avance) : un relevé à zéro plan fabriquerait six cents
     « disparus », puis six cents « nouveaux » (débrief 17). */
  const plans = plansUniques(modele.plans);
  if (!plans.length) {
    const erreur = new Error('L\'onglet « ' + modele.feuille + ' » ne porte aucun plan (en-têtes seuls) : rien à archiver.');
    /* Préparé d'avance, sans relevé encore : pas une panne, le vendredi n'a
       pas à échouer. Un contrat qui avait des relevés et dont l'export revient
       vide, si. */
    const historique = getFeuilleHistorique(SpreadsheetApp.getActiveSpreadsheet(), modele.feuille, false);
    erreur.sansPlan = !historique || historique.getLastRow() < 2;
    throw erreur;
  }
  /* La colonne suivie vide sur TOUS les plans, alors que le dernier relevé en
     avait des valeurs : un export fait sans elle, pas un contrat qui démarre.
     L'archiver ferait reculer chaque plan. */
  if (plans.every(function (p) { return classerFWD(p.avancement) === 'vide'; })) {
    const precedents = getHistorique(SpreadsheetApp.getActiveSpreadsheet(), modele.feuille);
    const dernier = precedents[precedents.length - 1];
    if (dernier && dernier.total - dernier.vide > 0) {
      throw new Error('La colonne « ' + CONFIG.COLONNE_FWD + ' » est vide sur les ' + plans.length +
        ' plans de « ' + modele.feuille + ' », alors que le relevé ' + dernier.semaine + ' en avait des valeurs : ' +
        'l\'export a-t-il été fait sans elle ? Relevé non archivé.');
    }
  }
  const clesDim = modele.clesDim.concat(modele.cleDate ? ['_anciennete'] : []);
  const maintenant = new Date();
  const reference = new Date(Date.UTC(maintenant.getFullYear(), maintenant.getMonth(), maintenant.getDate()));
  const moisDabord = ordreDesDates(plans, modele.cleDate);

  const compte = {
    total: plans.length,
    termine: 0, encours: 0, afaire: 0, vide: 0,
    groupes: {}, plans: {}
  };
  clesDim.forEach(function (d) { compte.groupes[d] = {}; });

  plans.forEach(function (p) {
    const etat = classerFWD(p.avancement);
    compte[etat]++;
    /* Avec le concept harnais, chaque plan garde ses deux avancements :
       [définition électrique, concept harnais]. Les relevés d'avant n'en
       ont qu'un, une chaîne : les deux formes se relisent (separerCartes). */
    compte.plans[p.reference] = modele.cleConcept
      ? [String(p.avancement || ''), String(p[modele.cleConcept] || '')]
      : String(p.avancement || '');
    clesDim.forEach(function (d) {
      const v = String((d === '_anciennete'
        ? ancienneteDepuis(p[modele.cleDate], reference, moisDabord)
        : p[d]) || '—');
      if (!compte.groupes[d][v]) compte.groupes[d][v] = { total: 0, termine: 0 };
      compte.groupes[d][v].total++;
      if (etat === 'termine') compte.groupes[d][v].termine++;
    });
  });

  return compte;
}

/**
 * Les plans, une fois chacun : une référence répétée — un export collé
 * par-dessus l'ancien sans le vider, dont la queue reste en dessous — ne
 * compte qu'à sa première ligne, la plus fraîche. Partout pareil : dans les
 * comptes, les groupes et la carte du relevé, comme sur la page ; sinon le
 * point du jour et les semaines archivées ne comptent pas la même chose
 * (débrief 17). Une ligne sans référence n'a pas de double.
 */
function plansUniques(plans) {
  const vues = {};
  return plans.filter(function (p) {
    const ref = String(p.reference || '');
    if (!ref) return true;
    if (Object.prototype.hasOwnProperty.call(vues, ref)) return false;
    vues[ref] = true;
    return true;
  });
}

/**
 * Sérialise ce qui doit tenir dans UNE cellule, sans jamais dépasser ce
 * qu'elle peut contenir : les comptes par dimension. La carte plan par plan,
 * elle, ne se jette pas — elle se découpe (decouper).
 */
function jsonTenable(valeur) {
  const texte = JSON.stringify(valeur);
  return texte.length > MAX_CARACTERES_CELLULE ? '' : texte;
}

/**
 * Découpe un texte en tranches d'au plus `taille` caractères, une par
 * cellule ; le recollage (recoller) les remet bout à bout. Une tranche ne
 * commence jamais par un caractère que Sheets interprète en tête de cellule :
 * « = », « + », « - », « @ » (une formule) ou « ' » (la marque de texte, qu'il
 * avale) — la carte deviendrait illisible, et le relevé perdrait son détail.
 */
function decouper(texte, taille) {
  const morceaux = [];
  let debut = 0;
  while (debut < texte.length) {
    let fin = Math.min(debut + taille, texte.length);
    while (fin < texte.length && fin > debut + 1 && '=+-@\''.indexOf(texte.charAt(fin)) !== -1) fin--;
    morceaux.push(texte.slice(debut, fin));
    debut = fin;
  }
  return morceaux;
}

/**
 * Élargit la grille de l'onglet s'il lui manque des colonnes : écrire au-delà
 * de la grille est une erreur dans Sheets, pas un agrandissement.
 */
function assurerColonnes(feuille, nbColonnes) {
  const actuelles = feuille.getMaxColumns();
  if (nbColonnes > actuelles) feuille.insertColumnsAfter(actuelles, nbColonnes - actuelles);
}

/** La ligne de l'onglet (1-based) qui porte cette semaine, ou -1. */
function ligneDeLaSemaine(feuille, semaine) {
  const derniere = feuille.getLastRow();
  if (derniere < 2) return -1;
  const semaines = feuille.getRange(2, 1, derniere - 1, 1).getValues();
  for (let i = semaines.length - 1; i >= 0; i--) {
    if (normaliserSemaine(semaines[i][0]) === semaine) return i + 2;
  }
  return -1;
}

/**
 * Les gestes qui écrivent dans le classeur — archiver, supprimer un relevé,
 * activer ou couper l'archivage automatique — ne se lancent que du menu
 * Suivi FWD, ou, pour l'archivage, par le vrai déclencheur du vendredi.
 * La page est ouverte par tout le monde et s'exécute au nom du propriétaire :
 * sans cette garde, un lecteur pourrait les appeler depuis la console de son
 * navigateur (google.script.run atteint toute fonction dont le nom ne finit
 * pas par « _ »). Hors du classeur, SpreadsheetApp.getUi() lève : c'est ce
 * qui les distingue. Un déclencheur se reconnaît à son identifiant, qui doit
 * être celui d'un déclencheur de ce projet.
 */
function gesteDuClasseur(e) {
  if (e && typeof e === 'object' && e.triggerUid) {
    const uid = String(e.triggerUid);
    if (ScriptApp.getProjectTriggers().some(function (t) { return String(t.getUniqueId()) === uid; })) return;
  }
  try {
    SpreadsheetApp.getUi();
  } catch (err) {
    throw new Error('Geste refusé : il ne se lance que dans le classeur, menu Suivi FWD (ou par l\'archivage automatique ' +
      'du vendredi). La page du tableau de bord ne modifie rien.');
  }
}

/**
 * Les gestes qui écrivent dans l'historique — l'archivage du vendredi,
 * celui du menu, une semaine passée, la suppression, l'import, le dépôt —
 * passent un à un. Sans verrou, le déclencheur du vendredi et un archivage
 * lancé au même moment trouvaient tous deux la semaine absente et ajoutaient
 * chacun sa ligne : deux relevés pour une semaine. Le verrou se prend au
 * niveau du geste, une seule fois : archiverContrat_ ne le prend pas
 * lui-même (ceux qui l'appellent le tiennent déjà). Pas obtenu en trente
 * secondes : rien n'est écrit, et on le dit.
 */
const MESSAGE_VERROU = 'un autre geste écrit en ce moment dans l\'historique de ce classeur (l\'archivage du vendredi, ' +
  'un import ou le menu, lancé au même moment) : l\'historique n\'est pas touché. Relancer dans une minute.';
/**
 * LE verrou de tous ces gestes : celui du script, pas celui du document. Le
 * dépôt automatique (doPost) tourne en application web, où
 * LockService.getDocumentLock() rend null (doc Google : « null if called
 * from a standalone script or webapp ») — le dépôt plantait sur ce null et
 * n'archivait plus rien. Le verrou du script, lui, existe partout ; et pour
 * un script lié à un seul classeur, il couvre exactement les mêmes gestes.
 * Il faut que TOUS prennent le même : un dépôt sous le verrou du script et
 * un vendredi sous celui du document ne s'attendraient pas l'un l'autre.
 */
function verrouDuClasseur_() {
  return LockService.getScriptLock();
}
function sousVerrou_(fn) {
  const verrou = verrouDuClasseur_();
  if (!verrou.tryLock(30000)) {
    const erreur = new Error(MESSAGE_VERROU);
    erreur.verrou = true;
    throw erreur;
  }
  try { return fn(); } finally { verrou.releaseLock(); }
}

/**
 * Archive le relevé de la semaine courante, pour TOUS les contrats du
 * classeur : une ligne par contrat, dans l'onglet d'historique du contrat.
 * Idempotent : réimporter dans la même semaine met la ligne à jour au lieu
 * d'en empiler une seconde.
 *
 * Chaque contrat s'archive pour lui-même : un onglet illisible n'empêche pas
 * les autres d'être relevés. Mais l'erreur n'est pas tue pour autant — elle
 * est relancée à la fin, une fois les autres archivés, pour que le déclencheur
 * hebdomadaire la signale. Renvoie le détail, contrat par contrat.
 */
function enregistrerInstantaneHebdo(e) {
  gesteDuClasseur(e);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const semaine = numeroSemaineISO(new Date());
  const contrats = listerContrats(classeur);
  if (contrats.length === 0) {
    throw new Error(messageSansContrat(classeur));
  }
  /* Lancé du menu, quelqu'un est devant l'écran : on peut lui poser une
     question. Le déclencheur du vendredi (son identifiant, ou pas
     d'interface du tout) n'a personne à qui la poser. */
  let ui = null;
  if (!(e && typeof e === 'object' && e.triggerUid)) {
    try { ui = SpreadsheetApp.getUi(); } catch (err) { ui = null; }
  }

  const detail = [];
  const erreurs = [];
  const sansPlan = [];
  const aConfirmer = [];
  const declines = [];
  /* La semaine se dit comme sur la page : « S39 », pas l'étiquette 2026-S39. */
  const dite = 'S' + parseInt(semaine.slice(6), 10);
  const archiverTous = function (liste, forcer) {
    liste.forEach(function (c) {
      try {
        detail.push(archiverContrat_(classeur, c, semaine, forcer));
      } catch (err) {
        if (err && err.sansPlan) sansPlan.push(c.nom);
        else if (err && err.ancienExport && ui && !forcer) aConfirmer.push({ c: c, err: err });
        else erreurs.push('« ' + c.nom + ' » : ' + (err && err.message ? err.message : err));
      }
    });
  };
  try {
    sousVerrou_(function () { archiverTous(contrats, false); });
  } catch (err) {
    /* Le verrou refusé : le déclencheur du vendredi le signale par son
       courriel d'échec, le menu par sa boîte d'erreur. */
    if (!err || !err.verrou) throw err;
    throw new Error('Relevé ' + dite + ' non archivé : ' + err.message);
  }
  /* L'export identique à un relevé plus ancien est refusé par prudence —
     c'est souvent l'export de la semaine dernière, pris par erreur. Mais il
     peut être juste : GATES est vraiment revenu à cet état (une validation
     retirée), ou le relevé déjà pris cette semaine venait d'un mauvais
     export. Sans issue, la semaine ne s'archivait plus par aucun chemin. Du
     menu, on demande donc, contrat par contrat — APRÈS avoir rendu le
     verrou : une question laissée ouverte ne doit pas bloquer le classeur —,
     puis on archive ceux qui sont confirmés, sous le verrou. Le vendredi,
     lui, continue de refuser. */
  const confirmes = [];
  aConfirmer.forEach(function (a) {
    const anc = a.err.ancien;
    const question = 'L’export de « ' + a.c.nom + ' » est identique au relevé ' + semaineDite(anc.semaine, semaine) +
      (anc.ecrase ? ', alors que le relevé ' + dite + ' déjà archivé cette semaine est différent.'
                  : ', plus ancien que le relevé ' + semaineDite(anc.dernier, semaine) + ', qui est différent.') +
      '\n\nL’archiver quand même comme relevé ' + dite + (anc.ecrase ? ', à la place de celui-ci' : '') + ' ? ' +
      'Oui seulement si GATES est vraiment revenu à cet état' +
      (anc.ecrase ? ', ou si le relevé ' + dite + ' déjà pris vient d’un mauvais export.' : ' (une validation retirée, par exemple).') +
      '\n\nSinon, répondre Non, puis importer l’export du jour (' + cheminImport() + ').';
    if (ui.alert('Suivi FWD', question, ui.ButtonSet.YES_NO) === ui.Button.YES) confirmes.push(a.c);
    else declines.push(a.c.nom);
  });
  if (confirmes.length) {
    try {
      sousVerrou_(function () { archiverTous(confirmes, true); });
    } catch (err) {
      if (!err || !err.verrou) throw err;
      confirmes.forEach(function (c) { erreurs.push('« ' + c.nom + ' » : ' + err.message); });
    }
  }
  const nonConfirmes = declines.length ? ' Non archivé(s), à votre demande : ' + declines.join(', ') + '.' : '';

  if (erreurs.length) {
    throw new Error('Relevé ' + dite + ' — ' +
      (detail.length ? detail.length + ' contrat(s) archivé(s), ' : '') +
      erreurs.length + ' en erreur : ' + erreurs.join(' ; ') + nonConfirmes);
  }
  /* Lancé du menu, le geste doit se voir : sans cela, Sheets n'affiche que
     « Script terminé », et on ne sait pas si c'est fait. Lancé par le
     déclencheur du vendredi, il n'y a personne devant : pas d'interface, et
     l'appel ci-dessous échoue en silence. */
  const mot = (!detail.length
    ? 'Aucun relevé archivé en ' + dite + '.'
    : 'Relevé ' + dite + ' archivé : ' + detail.map(function (d) {
      return d.nom + ' (' + d.compte.total + ' plans)';
    }).join(', ') + '. Un second archivage dans la semaine remplace celui-ci.') +
    (sansPlan.length ? ' Non archivé(s), en-têtes seuls : ' + sansPlan.join(', ') + '.' : '') + nonConfirmes;
  try {
    SpreadsheetApp.getUi().alert('Suivi FWD', mot, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    /* Pas d'interface (déclencheur, test) : rien à montrer. */
  }
  return { ok: true, semaine: semaine, contrats: detail, nonConfirmes: declines };
}

/**
 * Archive le relevé d'UN contrat pour la semaine donnée, dans son onglet
 * d'historique : la ligne de la semaine est créée ou mise à jour. Renvoie
 * { id, nom, historique, semaine, compte }. Sert au geste hebdomadaire
 * (tous les contrats) comme au dépôt automatique et à l'import (un seul).
 * Ceux qui l'appellent tiennent déjà le verrou (sousVerrou_) ; le « _ » la
 * garde hors de portée de la page.
 */
function archiverContrat_(classeur, c, semaine, forcer) {
  const compte = compterAvancements(c.id);
  /* L'export d'une semaine passée, rattrapé et laissé dans l'onglet
     (débrief 17) : archivé pour la semaine en cours, il écraserait en
     silence le bon relevé déjà pris — ou, la semaine n'ayant pas encore le
     sien, ferait reculer tout ce qui a bougé depuis. Même carte, plan par
     plan, qu'un relevé plus ancien, alors que le relevé de la semaine (ou, à
     défaut, le dernier) diffère : on refuse — sauf `forcer`, que seul le
     menu passe, après avoir demandé (enregistrerInstantaneHebdo). */
  const ancien = forcer ? null : exportDejaArchive(classeur, c, semaine, compte.plans);
  if (ancien) {
    const courante = numeroSemaineISO(new Date());
    const constat = 'l\'onglet « ' + c.nom + ' » porte le même export que le relevé ' + semaineDite(ancien.semaine, courante) +
      (ancien.ecrase
        ? ' : le relevé ' + semaineDite(semaine, courante) + ' déjà archivé, différent, n\'est pas écrasé.'
        : ', alors que le relevé ' + semaineDite(ancien.dernier, courante) + ', plus récent, est différent : archivé comme relevé ' +
          semaineDite(semaine, courante) + ', il ferait reculer les plans qui ont bougé depuis.');
    /* Le conseil dépend du cas : refaire le geste qui vient d'échouer
       (« importer l'export du jour ») ne sert à rien si l'export est
       juste. Pour la semaine en cours, le menu Archiver demande
       confirmation et passe outre ; pour une semaine passée, c'est
       l'export collé qu'il faut revoir. */
    const voulu = semaine === courante
      ? 'Si c\'est voulu (GATES est vraiment revenu à cet état' +
        (ancien.ecrase ? ', ou le relevé ' + semaineDite(semaine, courante) + ' déjà pris vient d\'un mauvais export' : '') +
        ') : menu Suivi FWD → Archiver le relevé de cette semaine, qui demandera confirmation.'
      : '';
    const erreur = new Error(constat + ' ' + (voulu
      ? voulu + ' Sinon, importer l\'export du jour (' + cheminImport() + ', qui archive dans la foulée).'
      : 'Vérifier que l\'onglet porte bien l\'export tiré de GATES en ' + semaineDite(semaine, courante) + '.'));
    erreur.ancienExport = true;
    erreur.ancien = ancien;
    erreur.constat = constat;
    erreur.voulu = voulu;
    throw erreur;
  }
  /* La carte plan par plan ne tient plus dans une cellule au-delà de
     quelques milliers de plans : elle s'étale sur autant de cellules
     qu'il faut, à partir de la colonne « Plans ». La jeter, comme avant,
     privait ces relevés de périmètre, de journal et de comparatif. */
  const ligne = [
    semaine, new Date(), compte.total, compte.termine, compte.encours,
    compte.afaire, compte.vide,
    jsonTenable(compte.groupes)
  ].concat(decouper(JSON.stringify(compte.plans), MAX_CARACTERES_CELLULE));
  /* Un historique à ouvrir alors qu'un autre n'est rattaché à rien : c'est
     presque toujours celui de ce contrat, sous son ancien nom. En ouvrir un
     second couperait l'historique en deux, et le renommage deviendrait
     impossible (le nom serait pris). On le dit au lieu d'archiver. */
  if (!getFeuilleHistorique(classeur, c.id, false)) {
    const contrats = listerContrats(classeur);
    const orphelins = historiquesOrphelins(classeur, contrats);
    if (orphelins.length) throw new Error(messageOrphelin(orphelins[0], c, classeur, contrats));
  }
  const feuille = getFeuilleHistorique(classeur, c.id, true);
  const indexLigne = ligneDeLaSemaine(feuille, semaine);
  if (indexLigne === -1) {
    assurerColonnes(feuille, ligne.length);
    feuille.appendRow(ligne);
  } else {
    /* Mise à jour de la semaine : on couvre aussi les colonnes qu'une
       écriture précédente, plus longue, aurait occupées — sinon la queue
       de l'ancienne carte resterait collée à la nouvelle. */
    while (ligne.length < feuille.getLastColumn()) ligne.push('');
    assurerColonnes(feuille, ligne.length);
    feuille.getRange(indexLigne, 1, 1, ligne.length).setValues([ligne]);
  }
  marquerDonneesModifiees_();
  return { id: c.id, nom: c.nom, historique: feuille.getName(), semaine: semaine, compte: compte };
}

/**
 * Ce qu'on dit d'un historique orphelin, à l'archivage comme avant. Ceux qui
 * l'appellent disent déjà « Relevé S40 non archivé : » devant.
 *
 * L'ancien « Historique_FWD » servait quand le classeur n'avait qu'un
 * contrat : ses relevés sont ceux d'un contrat qui n'a pas encore
 * d'historique à son nom. Lequel ? Celui dont les plans recoupent la carte
 * de son dernier relevé ; à défaut, pas le contrat que l'import vient de
 * créer (`c.nouveau`) : lui donner ces relevés grefferait sur sa courbe le
 * passé d'un autre. Sans indice, on nomme tous les candidats plutôt que de
 * désigner, au hasard, l'un à l'archivage de HDK et l'autre à celui de THS.
 * Et jamais « retirer le préfixe » tant que l'onglet peut être l'historique
 * d'un contrat : ce serait faire sortir de la page tous ses relevés, et le
 * vendredi ouvrirait un historique vide à côté.
 */
function messageOrphelin(o, c, classeur, contrats) {
  const masques = ' (Affichage → Onglets masqués pour le voir)';
  const nommer = function (liste) { return liste.map(function (k) { return '« ' + k.nom + ' »'; }).join(', '); };
  if (o.ancien) {
    let candidats = [];
    try { candidats = classeur && contrats ? contratsSansHistorique(classeur, contrats) : []; } catch (err) { candidats = []; }
    if (!candidats.some(function (k) { return k.id === c.id; })) candidats.push(c);
    const autres = candidats.filter(function (k) { return k.id !== c.id; });
    const tete = 'l\'ancien onglet d\'historique « ' + o.nom + ' » n\'est rattaché à aucun contrat depuis que le classeur en a plusieurs : ' +
      'il servait quand le classeur n\'en avait qu\'un. ';
    const rendre = function (k, sontCeux) {
      return tete + sontCeux + ' : le renommer « ' + nomFeuilleHistorique(k.id) + ' »' + masques + ' les lui rend, puis relancer l\'archivage.';
    };
    const proprio = candidats.length > 1 ? proprietaireProbable_(classeur, o.nom, candidats) : null;
    if (proprio) {
      return rendre(proprio.contrat, 'Ses relevés sont ceux de « ' + proprio.contrat.nom + ' » (le dernier a ' + proprio.commun +
        ' plan' + (proprio.commun > 1 ? 's' : '') + ' en commun avec l\'onglet « ' + proprio.contrat.nom + ' »)');
    }
    if (c.nouveau && autres.length === 1) return rendre(autres[0], 'Ses relevés sont sans doute ceux de « ' + autres[0].nom + ' »');
    if (candidats.length > 1) {
      const liste = c.nouveau ? autres : candidats;
      return tete + 'Le renommer « ' + nomFeuilleHistorique('<le contrat qui a produit ces relevés>') + ' » — l\'un de ' + nommer(liste) +
        masques + ', puis relancer l\'archivage.';
    }
    if (c.nouveau) {
      /* Aucun autre contrat sans historique : chacun a déjà le sien,
         l'ancien onglet n'est plus lu par personne. Le garder à part ne
         cache rien. */
      return tete + 'Il ne peut pas être celui de « ' + c.nom + ' », qui vient d\'être créé, et les autres contrats ont déjà leur propre ' +
        'historique : le renommer sans le préfixe « ' + CONFIG.FEUILLE_HISTORIQUE + ' » (par exemple « Ancien historique ») pour le garder à part.';
    }
    return tete + 'S\'il est celui de « ' + c.nom + ' », le renommer « ' + nomFeuilleHistorique(c.id) + ' »' + masques +
      ', puis relancer l\'archivage.';
  }
  return 'l\'onglet d\'historique « ' + o.nom + ' » n\'est rattaché à aucun contrat. ' +
    'S\'il est celui de « ' + c.nom + ' », le renommer « ' + nomFeuilleHistorique(c.id) + ' » ; sinon, le renommer ' +
    'sans le préfixe « ' + CONFIG.FEUILLE_HISTORIQUE + '_ » pour le garder à part.';
}

/**
 * Le contrat dont les plans recoupent nettement la carte du dernier relevé
 * d'un onglet d'historique — { contrat, commun } —, ou null : au moins
 * IMPORT_SEUIL_RECOUVREMENT des plans du relevé, et au moins le double du
 * suivant (la règle de la fenêtre d'import). Une carte vide ou illisible ne
 * désigne personne.
 */
function proprietaireProbable_(classeur, nomOnglet, candidats) {
  try {
    const f = classeur.getSheetByName(nomOnglet);
    if (!f || f.getLastRow() < 2) return null;
    const ligne = f.getRange(f.getLastRow(), 1, 1, Math.max(ENTETES_HISTORIQUE.length, f.getLastColumn())).getValues()[0];
    const carte = separerCartes(analyserJson(recoller(ligne.slice(ENTETES_HISTORIQUE.length - 1)))).plans;
    const cles = carte && typeof carte === 'object' ? Object.keys(carte).map(normaliser).filter(Boolean) : [];
    if (!cles.length) return null;
    const parts = enLecture(function () {
      return candidats.map(function (k) {
        const ici = {};
        referencesDeLOnglet(classeur.getSheetByName(k.id)).forEach(function (r) { ici[normaliser(r)] = true; });
        const commun = cles.filter(function (x) { return ici[x]; }).length;
        return { contrat: k, commun: commun, part: commun / cles.length };
      });
    }).sort(function (a, b) { return b.part - a.part; });
    const a = parts[0], b = parts[1];
    return a && a.part >= IMPORT_SEUIL_RECOUVREMENT && (!b || b.part * 2 <= a.part) ? { contrat: a.contrat, commun: a.commun } : null;
  } catch (err) {
    return null;
  }
}

/** Une carte plan par plan, en texte stable : pour comparer deux relevés. */
function carteCanonique(carte) {
  if (!carte || typeof carte !== 'object') return '';
  return Object.keys(carte).sort().map(function (k) { return k + '\u0001' + carte[k]; }).join('\u0002');
}

/**
 * L'export d'un relevé PLUS ANCIEN, revenu dans l'onglet : { semaine (celle
 * de ce relevé), ecrase (vrai si `semaine` a déjà un relevé, différent),
 * dernier (sinon, la semaine du dernier relevé, qui diffère) } — sinon null.
 * Deux cas :
 *   – `semaine` a déjà un relevé, autre que cette carte : l'écraser avec un
 *     export plus ancien effacerait le bon relevé ;
 *   – `semaine` n'a pas encore de relevé, mais le dernier relevé d'avant
 *     diffère de cette carte, qu'un relevé plus ancien porte exactement :
 *     c'est l'export rattrapé (S38) laissé dans l'onglet après coup, et
 *     l'archiver ferait reculer tout ce qui a bougé depuis (S39). Une semaine
 *     calme — S38 = S39 = S40 — reste acceptée : le dernier relevé est pareil.
 * Un historique illisible ne bloque rien.
 */
function exportDejaArchive(classeur, c, semaine, plans) {
  let releves;
  try { releves = getHistorique(classeur, c.id); } catch (err) { return null; }
  const neuves = separerCartes(plans);
  const cle = carteCanonique(neuves.plans) + '\u0003' + carteCanonique(neuves.plansConcept);
  const cleDe = function (r) { return carteCanonique(r.plans) + '\u0003' + carteCanonique(r.plansConcept); };
  const avant = releves.filter(function (r) { return r.semaine < semaine; });
  const actuel = releves.filter(function (r) { return r.semaine === semaine; })[0];
  const dernier = avant[avant.length - 1];
  if (actuel) {
    if (!actuel.plans || cleDe(actuel) === cle) return null;
  } else if (!dernier || !dernier.plans || cleDe(dernier) === cle) {
    /* Sans carte au dernier relevé, rien ne dit s'il diffère : on laisse passer. */
    return null;
  }
  const pareils = avant.filter(function (r) { return r.plans && cleDe(r) === cle; });
  return pareils.length
    ? { semaine: pareils[pareils.length - 1].semaine, ecrase: !!actuel, dernier: actuel ? null : dernier.semaine }
    : null;
}

/**
 * Retire le relevé de la semaine courante — pour rattraper un mauvais export —
 * de tous les contrats, et récapitule à l'écran ce qui a été retiré et ce qui
 * n'avait rien. D'un clic, tous les contrats perdaient leur relevé : on
 * demande d'abord, OUI / NON, en nommant ceux qui en ont un cette semaine ;
 * NON ne touche à rien.
 */
function supprimerDernierReleve() {
  gesteDuClasseur();
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const semaine = numeroSemaineISO(new Date());
  let contrats = [];
  try { contrats = listerContrats(classeur); } catch (err) { contrats = []; }
  const nommer = function (liste) { return liste.map(function (n) { return '« ' + n + ' »'; }).join(', '); };
  /* La semaine se dit comme sur la page : « S39 ». */
  const dite = 'S' + parseInt(semaine.slice(6), 10);
  const avecReleve = contrats.filter(function (c) {
    const feuille = getFeuilleHistorique(classeur, c.id, false);
    return !!feuille && ligneDeLaSemaine(feuille, semaine) !== -1;
  }).map(function (c) { return c.nom; });
  if (!avecReleve.length) {
    ui.alert('Aucun relevé pour la semaine en cours (' + dite + ').');
    return { semaine: semaine, supprimes: [], sans: contrats.map(function (c) { return c.nom; }) };
  }
  const question = 'Supprimer le relevé ' + dite + ' de ' + nommer(avecReleve) + ' ?\n\n' +
    'La ligne ' + dite + ' de ' + (avecReleve.length > 1 ? 'leur' : 'son') + ' historique est retirée ; ' +
    'les semaines d\'avant ne bougent pas.';
  if (ui.alert('Suivi FWD', question, ui.ButtonSet.YES_NO) !== ui.Button.YES) return null;

  const supprimes = [];
  const sans = [];
  try {
    sousVerrou_(function () {
      /* Relu sous le verrou : un archivage a pu passer pendant la question.
         Seuls les contrats nommés dans la question perdent leur relevé. */
      contrats.forEach(function (c) {
        const feuille = avecReleve.indexOf(c.nom) !== -1 ? getFeuilleHistorique(classeur, c.id, false) : null;
        const indexLigne = feuille ? ligneDeLaSemaine(feuille, semaine) : -1;
        if (indexLigne === -1) { sans.push(c.nom); return; }
        feuille.deleteRow(indexLigne);
        supprimes.push(c.nom);
      });
      if (supprimes.length) marquerDonneesModifiees_();
    });
  } catch (err) {
    /* Seul le verrou refusé se dit ici : rien n'a été retiré. Toute autre
       panne remonte telle quelle, sans prétendre que rien n'a bougé. */
    if (!err || !err.verrou) throw err;
    ui.alert('Relevé ' + dite + ' non supprimé : ' + err.message);
    return null;
  }

  let message;
  if (!supprimes.length) {
    message = 'Aucun relevé pour la semaine en cours (' + dite + ').';
  } else if (contrats.length === 1) {
    message = 'Relevé ' + dite + ' supprimé. Importez le bon export (' + cheminImport() + ', qui archive dans la foulée), ' +
      'ou recollez-le puis relancez l\'archivage.';
  } else {
    message = 'Relevé ' + dite + ' supprimé pour ' + nommer(supprimes) +
      (sans.length ? ' ; aucun relevé pour ' + nommer(sans) : '') +
      '. Importez le bon export (' + cheminImport() + ', qui archive dans la foulée), ou recollez-le puis relancez l\'archivage.';
  }
  ui.alert(message);
  return { semaine: semaine, supprimes: supprimes, sans: sans };
}

/**
 * Rattraper une semaine (débrief 17) : l'export d'une semaine passée —
 * celui de la semaine dernière, gardé de côté —, recollé après coup dans
 * l'onglet d'un contrat, devient le relevé de cette semaine-là. Sans lui,
 * un relevé S39 identique à celui de S40 ne donne aucun rythme. Seul le
 * contrat de l'onglet affiché est archivé ; la ligne de la semaine est créée
 * ou remplacée, après confirmation. Une semaine à venir est refusée.
 */
function archiverSemainePassee() {
  gesteDuClasseur();
  const ui = SpreadsheetApp.getUi();
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const onglet = classeur.getActiveSheet().getName();
  if (!listerContrats(classeur).some(function (c) { return normaliser(c.id) === normaliser(onglet); })) {
    ui.alert('Suivi FWD', 'L\'onglet affiché, « ' + onglet + ' », n\'est pas un contrat : afficher l\'onglet du contrat ' +
      '(HDK…) où l\'export de la semaine passée est collé, puis relancer.', ui.ButtonSet.OK);
    return null;
  }
  const reponse = ui.prompt('Archiver pour une semaine passée',
    'L\'export collé dans l\'onglet affiché (« ' + onglet + ' ») devient le relevé de la semaine où il a été ' +
    'tiré de GATES.\nSemaine (par exemple S39) :', ui.ButtonSet.OK_CANCEL);
  if (reponse.getSelectedButton() !== ui.Button.OK) return null;
  const saisie = reponse.getResponseText();
  const prevu = preparerSemainePassee(classeur, onglet, saisie);
  if (!prevu.ok) {
    ui.alert('Suivi FWD', prevu.message, ui.ButtonSet.OK);
    return prevu;
  }
  if (ui.alert('Suivi FWD', prevu.question, ui.ButtonSet.YES_NO) !== ui.Button.YES) return null;
  const resultat = archiverPourSemaine_(classeur, onglet, saisie);
  ui.alert('Suivi FWD', resultat.message, ui.ButtonSet.OK);
  return resultat;
}

/**
 * La semaine tapée : « S39 », « s 39 », « 39 » (de l'année en cours — ou
 * de la précédente si elle tomberait plus tard qu'aujourd'hui : S52 tapé en
 * janvier), ou « 2026-S39 ». Null si illisible.
 */
function semaineSaisie(texte, courante) {
  const t = String(texte || '').trim();
  let semaine = normaliserSemaine(t);
  /* « S52 2025 », « S52-2025 » : la forme que la boîte affiche elle-même. */
  const avecAnnee = /^[sS]?\s*(\d{1,2})\s*[-/ ]\s*(\d{4})$/.exec(t);
  if (!semaine && avecAnnee) semaine = normaliserSemaine(avecAnnee[2] + '-S' + avecAnnee[1]);
  const m = /^[sS]?\s*(\d{1,2})$/.exec(t);
  if (!semaine && m) {
    const annee = Number(courante.slice(0, 4));
    semaine = normaliserSemaine(annee + '-S' + m[1]);
    /* À venir cette année : celle de l'an dernier seulement si elle est
       toute proche (« S52 » tapé début janvier) ; sinon elle reste à venir,
       et sera refusée — « S41 » tapé en S40 n'est pas S41 de l'an dernier. */
    const derniere = normaliserSemaine((annee - 1) + '-S' + m[1]);
    if (semaine && semaine > courante && derniere && semaineExiste(derniere) && semainesEntre(derniere, courante) <= 8) semaine = derniere;
  }
  return semaine && semaineExiste(semaine) ? semaine : null;
}

/** Le lundi d'une semaine ISO « AAAA-SNN », en millisecondes UTC. */
function lundiDeSemaine(semaine) {
  const a = Number(semaine.slice(0, 4)), n = Number(semaine.slice(6));
  const j4 = new Date(Date.UTC(a, 0, 4));
  return j4.getTime() - ((j4.getUTCDay() || 7) - 1) * 864e5 + (n - 1) * 7 * 864e5;
}

/** La semaine existe-t-elle ? Une S53 seulement dans une année qui en a une. */
function semaineExiste(semaine) {
  const jeudi = new Date(lundiDeSemaine(semaine) + 3 * 864e5);
  return numeroSemaineISO(new Date(jeudi.getUTCFullYear(), jeudi.getUTCMonth(), jeudi.getUTCDate())) === semaine;
}

/** Semaines de a à b (b après a : positif). */
function semainesEntre(a, b) {
  return Math.round((lundiDeSemaine(b) - lundiDeSemaine(a)) / (7 * 864e5));
}

/** « S39 », et l'année quand ce n'est pas celle d'aujourd'hui : « S52 2025 ». */
function semaineDite(semaine, courante) {
  const dite = 'S' + parseInt(semaine.slice(6), 10);
  return semaine.slice(0, 4) === String(courante || '').slice(0, 4) ? dite : dite + ' ' + semaine.slice(0, 4);
}

/**
 * Ce que ferait l'archivage d'une semaine passée, sans rien écrire :
 * { ok, semaine, contrat, existe, question } — ou { ok: false, message }.
 */
function preparerSemainePassee(classeur, nomOnglet, saisie) {
  const courante = numeroSemaineISO(new Date());
  const texte = String(saisie || '').trim();
  const semaine = semaineSaisie(texte, courante);
  if (!semaine) {
    return { ok: false, semaine: null, message: 'Semaine illisible (ou qui n\'existe pas) : « ' + texte.slice(0, 20) + ' ». ' +
      'Écrire par exemple S' + parseInt(courante.slice(6), 10) + ' (ou ' + courante + ').' };
  }
  const dite = semaineDite(semaine, courante);
  if (semaine > courante) {
    return { ok: false, semaine: semaine, message: 'La semaine ' + dite + ' n\'est pas encore arrivée : rien n\'est archivé.' };
  }
  const contrat = listerContrats(classeur).filter(function (c) { return normaliser(c.id) === normaliser(nomOnglet); })[0];
  if (!contrat) {
    return { ok: false, semaine: semaine, message: 'L\'onglet affiché, « ' + nomOnglet + ' », n\'est pas un contrat : ' +
      'afficher l\'onglet du contrat (HDK…) où l\'export de ' + dite + ' est collé, puis relancer.' };
  }
  const contrats = listerContrats(classeur);
  const historique = getFeuilleHistorique(classeur, contrat.id, false);
  if (!historique) {
    /* « HDK S39 » : l'export rattrapé collé dans un nouvel onglet deviendrait
       un contrat à part, avec son propre historique (débrief 17). */
    const parent = contrats.filter(function (k) {
      const n = normaliser(k.id);
      return k.id !== contrat.id && normaliser(contrat.id).indexOf(n) === 0 && /^[\s\-_]/.test(normaliser(contrat.id).slice(n.length));
    })[0];
    if (parent) {
      return { ok: false, semaine: semaine, message: 'L\'onglet « ' + contrat.nom + ' » n\'a aucun relevé : ce serait un nouveau contrat. ' +
        'Mettre l\'export de ' + dite + ' dans l\'onglet « ' + parent.nom + ' » lui-même — ' + cheminImport() + ', case « Archiver » ' +
        'décochée, ou Ctrl+A, Suppr, A1, Ctrl+V —, l\'afficher, puis relancer. L\'onglet « ' + contrat.nom + ' » peut être supprimé.' };
    }
    const orphelins = historiquesOrphelins(classeur, contrats);
    if (orphelins.length) {
      return { ok: false, semaine: semaine, message: 'Relevé ' + dite + ' non archivé : ' + messageOrphelin(orphelins[0], contrat, classeur, contrats) };
    }
  }
  const existe = !!historique && ligneDeLaSemaine(historique, semaine) !== -1;
  const actuelle = semaine === courante;
  const autresAvecHistorique = historique ? [] : contrats.filter(function (k) {
    return k.id !== contrat.id && !!getFeuilleHistorique(classeur, k.id, false);
  });
  return {
    ok: true, semaine: semaine, contrat: contrat, existe: existe,
    question: 'Archiver l\'export affiché dans « ' + contrat.nom + ' » comme relevé ' + dite + ' ?\n\n' +
      (existe ? 'Il remplace le relevé ' + dite + ' déjà archivé pour « ' + contrat.nom + ' ».'
              : 'Aucun relevé ' + dite + ' n\'existe encore pour « ' + contrat.nom + ' » : il est ajouté.' +
                (historique ? '' : autresAvecHistorique.length
                  ? '\n\n⚠ « ' + contrat.nom + ' » n\'a encore aucun relevé : ce sera un NOUVEAU contrat, avec son propre ' +
                    'historique, archivé chaque vendredi. Pour rattraper une semaine de « ' + autresAvecHistorique[0].nom +
                    ' », mettre l\'export dans son onglet à lui (par l\'import, case « Archiver » décochée, ou par un collage).'
                  : ' C\'est le tout premier relevé de ce contrat.')) +
      (actuelle ? '' : '\n\nEnsuite, remets tout de suite l\'export du jour dans « ' + contrat.nom + ' » (' + cheminImport() +
        ', ou un collage) : sinon l\'archivage du vendredi prendrait cet export-là pour celui de la semaine en cours.')
  };
}

/** Le geste d'archiverSemainePassee, sans interface, sous le verrou : { ok, semaine, message }. */
function archiverPourSemaine_(classeur, nomOnglet, saisie) {
  const prevu = preparerSemainePassee(classeur, nomOnglet, saisie);
  if (!prevu.ok) return { ok: false, semaine: prevu.semaine, message: prevu.message };
  const courante = numeroSemaineISO(new Date());
  const dite = semaineDite(prevu.semaine, courante);
  try {
    const detail = sousVerrou_(function () { return archiverContrat_(classeur, prevu.contrat, prevu.semaine); });
    return { ok: true, semaine: prevu.semaine, message: 'Relevé ' + dite + ' de « ' + prevu.contrat.nom + ' » ' +
      (prevu.existe ? 'remplacé' : 'archivé') + ' avec l\'export affiché (' + detail.compte.total + ' plans).' +
      (prevu.semaine === courante ? '' : '\n\n⚠ L\'onglet « ' + prevu.contrat.nom + ' » porte maintenant l\'export de ' + dite +
        ' : importe l\'export du jour (' + cheminImport() + ', qui archive dans la foulée), ou recolle-le puis Suivi FWD → ' +
        'Archiver le relevé de cette semaine.') };
  } catch (err) {
    const pourquoi = err && err.sansPlan ? 'l\'onglet « ' + prevu.contrat.nom + ' » ne porte aucun plan (en-têtes seuls)'
      : (err && err.message ? err.message : err);
    return { ok: false, semaine: prevu.semaine, message: 'Relevé ' + dite + ' non archivé : ' + pourquoi };
  }
}

function installerSuiviHebdomadaire() {
  gesteDuClasseur();
  desinstallerSuiviHebdomadaire();
  ScriptApp.newTrigger('enregistrerInstantaneHebdo')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.FRIDAY)
    .atHour(17)
    .create();
  SpreadsheetApp.getUi().alert('Archivage automatique activé : chaque vendredi vers 17 h.');
}

function desinstallerSuiviHebdomadaire() {
  gesteDuClasseur();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'enregistrerInstantaneHebdo') ScriptApp.deleteTrigger(t);
  });
}

// =====================================================================
//  JALONS (fixés dans CONFIG, identiques pour tous les lecteurs)
// =====================================================================

/**
 * Les jalons de CONFIG.JALONS, validés : semaine normalisée, texte épuré et
 * coupé à 60 caractères, périmètre épuré (et absent quand il n'est pas
 * donné : un jalon sans périmètre vaut pour tous les plans, et n'a pas de
 * clé de plus), entrées illisibles écartées, tri par semaine, plafond
 * MAX_JALONS. Une faute de frappe dans la configuration ne fait donc jamais
 * tomber la page — le jalon fautif est simplement absent.
 */
/** Le jour d'un jalon, « AAAA-MM-JJ » ou « JJ/MM/AAAA », en date UTC — ou null. */
function dateDeJalon(valeur) {
  const t = String(valeur || '').trim();
  let m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/), a, mo, j;
  if (m) { a = +m[1]; mo = +m[2]; j = +m[3]; }
  else if ((m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/))) { a = +m[3]; mo = +m[2]; j = +m[1]; }
  else return null;
  const d = new Date(Date.UTC(a, mo - 1, j));
  return d.getUTCFullYear() === a && d.getUTCMonth() === mo - 1 && d.getUTCDate() === j ? d : null;
}

/**
 * Les contrats d'un jalon de CONFIG.JALONS (clé contrat : un nom d'onglet,
 * ou une liste), épurés — null quand il n'en nomme aucun : il vaut alors
 * pour tous les contrats.
 */
function contratsDuJalon(j) {
  const brut = j && typeof j === 'object' ? j.contrat : null;
  const liste = (Array.isArray(brut) ? brut : [brut])
    .map(function (c) { return c === null || c === undefined || typeof c === 'object' ? '' : String(c).trim(); })
    .filter(Boolean);
  return liste.length ? liste : null;
}

/** Le jalon vaut-il pour ce contrat ? Sans contrat demandé : oui, tous. */
function jalonPourContrat(j, contrat) {
  if (contrat === undefined || contrat === null) return true;
  const pour = contratsDuJalon(j);
  return !pour || pour.some(function (c) { return normaliser(c) === normaliser(contrat); });
}

/**
 * Les jalons d'un contrat (le nom de son onglet), prêts pour la page ; sans
 * contrat, tous ceux de la configuration. La clé contrat ne voyage pas : la
 * page ne reçoit que les jalons du contrat qu'elle montre.
 */
function getJalons(contrat) {
  const liste = Array.isArray(CONFIG.JALONS) ? CONFIG.JALONS : [];
  return liste
    .filter(function (j) { return jalonPourContrat(j, contrat); })
    .map(function (j) {
      const date = dateDeJalon(j && j.date);
      const semaine = date ? numeroSemaineISO(date) : normaliserSemaine(j && j.semaine);
      if (!semaine) return null;
      const jalon = {
        semaine: semaine,
        texte: String((j && j.texte) || 'Jalon').trim().slice(0, 60) || 'Jalon'
      };
      if (date) jalon.date = date.toISOString().slice(0, 10);
      const perimetre = String((j && j.perimetre) || '').trim().slice(0, 40);
      if (perimetre) jalon.perimetre = perimetre;
      if (j && j.suivi && normaliser(j.suivi).indexOf('concept') === 0) jalon.suivi = 'concept';
      return jalon;
    })
    .filter(function (j) { return j !== null; })
    .sort(function (a, b) { return a.semaine < b.semaine ? -1 : (a.semaine > b.semaine ? 1 : 0); })
    .slice(0, CONFIG.MAX_JALONS);
}

// =====================================================================
//  RAPPROCHEMENT AVEC UNE SECONDE BASE (CONFIG.RAPPROCHEMENT)
// =====================================================================

/**
 * La description de la seconde base pour la page : { nom, cleReference,
 * lignes, colonnes, essentielles }, ou null tant qu'aucun onglet ne porte
 * le nom configuré (FEUILLE, sinon NOM) — la page n'affiche alors rien.
 * Tout est dans lireSecondeBase(), qui dit aussi POURQUOI il n'y a rien.
 *
 * @param {Spreadsheet} classeur
 */
function getRapprochement(classeur, contrat) {
  return lireSecondeBase(classeur, contrat).rapprochement;
}

/**
 * La seconde base, lue, et son état — pour le paquet comme pour le
 * diagnostic :
 *   { etat, onglet, cles, entetes, ligneEntete, tri, rapprochement }
 * etat : 'sans-configuration' (pas de nom d'onglet, ou pas de référence
 *        configurée), 'absent' (aucun onglet de ce nom), 'vide' (l'onglet
 *        ne porte rien), 'sans-reference' (l'en-tête ne porte pas la
 *        référence), 'sans-psn' (l'onglet porte la colonne des PSN — un
 *        extract de tous les porteurs — mais le contrat n'a pas de PSN :
 *        rien plutôt que les plans des autres), 'ok' — et alors
 *        `rapprochement` est la description pour la page, avec `filtre`
 *        (« PSN 4530 · WD ») quand on sait comment elle a été triée.
 *        ligneEntete : le numéro (à partir de 1) de la ligne prise pour
 *        en-tête, null tant qu'aucune ne l'est. tri : voir trierSecondeBase,
 *        null quand rien n'est trié.
 *
 * L'onglet est lu tel quel : l'en-tête est la première ligne qui porte tous
 * les intitulés de la référence (dans SEE, la ligne 3, sous le titre), sinon
 * la première ligne non vide ; les lignes suivantes deviennent des objets
 * { intitulé: valeur }. Les intitulés sont conservés à la lettre, puisque
 * c'est par eux que ESSENTIELLES désigne les colonnes de la seconde base, et
 * `colonnes` les rend dans l'ordre de l'onglet. La référence : une chaîne
 * quand une colonne la porte entière, la liste des intitulés quand elle se
 * recompose. C'est la page qui rapproche : présence dans la seconde base
 * contre avancement FWD d'ici.
 *
 * @param {Spreadsheet} classeur
 */
function lireSecondeBase(classeur, contrat) {
  const cfg = CONFIG.RAPPROCHEMENT;
  const nomFeuille = feuilleRapprochement();
  const clesVoulues = clesSecondeBase();
  const rendu = { etat: 'sans-configuration', onglet: nomFeuille, cles: clesVoulues, entetes: [], ligneEntete: null, tri: null, rapprochement: null };
  if (!cfg || !nomFeuille || !clesVoulues.length) return rendu;
  const feuille = ongletSecondeBase(classeur, contrat);
  if (!feuille) { rendu.etat = 'absent'; rendu.onglet = nomAttenduSecondeBase(classeur, contrat); return rendu; }
  rendu.onglet = feuille.getName();

  const donnees = feuille.getDataRange().getDisplayValues();
  const t = lireTableauSecondeBase(donnees, clesVoulues);
  if (t.etat === 'vide') { rendu.etat = 'vide'; return rendu; }
  rendu.entetes = t.entetes.filter(Boolean);
  rendu.ligneEntete = t.ligneEntete;
  if (t.etat === 'sans-reference') { rendu.etat = 'sans-reference'; return rendu; }
  const essentielles = (Array.isArray(cfg.ESSENTIELLES) ? cfg.ESSENTIELLES : [])
    .map(t.enteteLa).filter(Boolean);

  /* Le tri du contrat (débrief 21) : refait ici quand l'onglet en porte les
     colonnes, sinon celui que la fenêtre d'import a noté en tête. Sans
     contrat nommé, celui du classeur s'il est seul — c'est à lui qu'est
     l'onglet « SEE » tout court. */
  let idContrat = contrat === undefined || contrat === null ? '' : String(contrat);
  if (!idContrat) {
    try { const seuls = listerContrats(classeur); if (seuls.length === 1) idContrat = seuls[0].id; } catch (err) { idContrat = ''; }
  }
  const tri = trierSecondeBase(t, donnees, idContrat);
  let lignes = t.lignes;
  if (tri) {
    if (tri.lignes) lignes = tri.lignes;
    delete tri.lignes;
    rendu.tri = tri;
    if (tri.sansPsn) { rendu.etat = 'sans-psn'; return rendu; }
  }

  rendu.etat = 'ok';
  rendu.rapprochement = {
    nom: String(cfg.NOM || feuille.getName()).trim().slice(0, 80) || feuille.getName(),
    cleReference: t.clesReference.length === 1 ? t.clesReference[0] : t.clesReference,
    lignes: lignes,
    colonnes: t.entetes.filter(Boolean),
    essentielles: essentielles
  };
  /* Pour que la page puisse dire, plus tard, de quelles lignes elle parle. */
  if (tri && tri.texte) rendu.rapprochement.filtre = tri.texte;
  return rendu;
}

/* =====================================================================
   LE TRI DE LA SECONDE BASE (débrief 21)
   « On a énormément de données. Il va falloir faire deux tris » : la
   machine (VALIDITY PSN FULL, plein de numéros séparés par des virgules ;
   HDK, c'est 4530) et le type de schéma (DIAGRAM TYPE : GH, WD ou PH ;
   seuls les WD). Les règles sont dans CONFIG.RAPPROCHEMENT (COLONNE_PSN,
   PSN, FILTRES) ; la fenêtre d'import les reçoit telles quelles
   (parametresImport_) et trie pendant la lecture du fichier ; la lecture
   d'un onglet les refait quand il en porte les colonnes.
   ===================================================================== */
const CLE_PSN = 'SUIVI_FWD_PSN';           // les PSN tapés dans la fenêtre, { contrat: ['4530'] }
const PSN_MAX = 20;                        // PSN par contrat
const PSN_FORME = /^[0-9A-Za-z][0-9A-Za-z._\/-]{0,19}$/;
/* La ligne que la fenêtre pose en tête d'une base triée — le serveur la
   relit : « Trié à l’import : PSN 4530 · DIAGRAM TYPE = WD — 1 234 lignes
   gardées sur 60 000 · « Nommage WD BFLOW.xlsx », le 05/10/2026 ». */
const MARQUE_TRI = 'Trié à l’import : ';

/** Un intitulé ou une valeur de tri, réduit pour être comparé : sans casse, accents ni espaces (« Diagram  type » = « DIAGRAM TYPE », « wd » = « WD »). */
function cleTri(v) { return normaliser(v).replace(/\s+/g, ''); }

/**
 * Les PSN d'une cellule (« 4520,4530; 4540 »), coupés aux virgules,
 * points-virgules et espaces, réduits (casse, accents) : on les compare EN
 * ENTIER — 4530 n'est ni 14530 ni 45301.
 */
function jetonsPsn(texte) {
  return String(texte === undefined || texte === null ? '' : texte).split(/[\s,;]+/)
    .map(function (j) { return normaliser(j); }).filter(Boolean);
}

/** La cellule porte-t-elle l'un de ces PSN (des jetons réduits, en objet { jeton: true }) ? Une cellule vide, aucun. */
function cellulePorteUnPsn(cellule, voulus) {
  return jetonsPsn(cellule).some(function (j) { return Object.prototype.hasOwnProperty.call(voulus, j); });
}

/** La colonne des PSN configurée (COLONNE_PSN), ou ''. */
function colonnePsnSecondeBase() {
  const cfg = CONFIG.RAPPROCHEMENT;
  return cfg && cfg.COLONNE_PSN ? String(cfg.COLONNE_PSN).trim() : '';
}

/** Les filtres configurés (FILTRES) : [{ colonne, cle, valeurs, permises: { valeur réduite: true } }]. */
function filtresSecondeBase() {
  const cfg = CONFIG.RAPPROCHEMENT, brut = cfg && cfg.FILTRES && typeof cfg.FILTRES === 'object' ? cfg.FILTRES : {};
  return Object.keys(brut).map(function (colonne) {
    const valeurs = [].concat(brut[colonne] === undefined || brut[colonne] === null ? [] : brut[colonne])
      .map(function (v) { return String(v).trim(); }).filter(Boolean);
    const permises = {};
    valeurs.forEach(function (v) { permises[cleTri(v)] = true; });
    return { colonne: String(colonne).trim(), cle: cleTri(colonne), valeurs: valeurs, permises: permises };
  }).filter(function (f) { return f.cle && f.valeurs.length; });
}

/** Un PSN écrit dans la configuration ou tapé : '4530', ['4530', '4531'] ou « 4530, 4531 » → ['4530', '4531'], sans doublon. */
function listePsn(brut) {
  const vus = {}, liste = [];
  [].concat(brut === undefined || brut === null ? [] : brut).forEach(function (x) {
    String(x).split(/[\s,;]+/).forEach(function (j) {
      const k = normaliser(j);
      if (k && !vus[k]) { vus[k] = true; liste.push(j.trim()); }
    });
  });
  return liste;
}

/** Les PSN gardés par la fenêtre d'import : { contrat: ['4530'] } ({} si rien, ou illisible). */
function psnEnregistres_() {
  let lu = null;
  try { lu = analyserJson(PropertiesService.getDocumentProperties().getProperty(CLE_PSN)); } catch (err) { lu = null; }
  return lu && typeof lu === 'object' && !Array.isArray(lu) ? lu : {};
}

/**
 * Le PSN d'un contrat : { psn: ['4530'], source: 'fenetre' | 'configuration' | '' }.
 * Celui tapé dans la fenêtre l'emporte — vide compris : on a voulu qu'il
 * n'en ait pas —, sinon celui de CONFIG.RAPPROCHEMENT.PSN, cherché par le
 * nom du contrat sans tenir compte de la casse ni des accents.
 */
function psnDuContrat(contrat) {
  const n = normaliser(contrat === undefined || contrat === null ? '' : contrat);
  const enregistres = psnEnregistres_();
  const k = Object.keys(enregistres).filter(function (x) { return normaliser(x) === n; })[0];
  if (k !== undefined && Array.isArray(enregistres[k])) return { psn: listePsn(enregistres[k]), source: 'fenetre' };
  const cfg = CONFIG.RAPPROCHEMENT, parConfig = cfg && cfg.PSN && typeof cfg.PSN === 'object' ? cfg.PSN : {};
  const c = Object.keys(parConfig).filter(function (x) { return normaliser(x) === n; })[0];
  if (c !== undefined) {
    const psn = listePsn(parConfig[c]);
    if (psn.length) return { psn: psn, source: 'configuration' };
  }
  return { psn: [], source: '' };
}

/** Un PSN tapé dans la fenêtre, vérifié : la liste de ses PSN, ou une erreur qui dit pourquoi. */
function psnSaisi(texte) {
  const psn = listePsn(String(texte === undefined || texte === null ? '' : texte).slice(0, 500));
  const faux = psn.filter(function (j) { return !PSN_FORME.test(j); });
  if (faux.length) {
    throw new Error('« ' + faux[0].slice(0, 30) + ' » n’est pas un PSN : des chiffres (des lettres au besoin), 20 caractères au plus, ' +
      'plusieurs séparés par des virgules — comme « 4530 ».');
  }
  if (psn.length > PSN_MAX) throw new Error('Trop de PSN : ' + psn.length + ' (au plus ' + PSN_MAX + ').');
  return psn;
}

/**
 * La fenêtre garde le PSN tapé pour un contrat (« il faudra demander le
 * PSN ») : dans les propriétés du classeur, sous le verrou des gestes. Il
 * vaut pour la prochaine ouverture comme pour la lecture des onglets SEE
 * qui portent la colonne des PSN — le paquet en cache est donc oublié.
 * @return {{ok: boolean, contrat: string, psn: string[], source: string}}
 */
function importEnregistrerPsn(jeton, idContrat, texte) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  /* Le contrat se retrouve casse et accents indifférents (« hdk » est HDK), comme psnDuContrat le cherche ;
     le PSN se range sous le nom de son onglet. */
  const id = String(idContrat === undefined || idContrat === null ? '' : idContrat), tous = listerContrats(classeur);
  const contrat = tous.filter(function (c) { return c.id === id; })[0] ||
    tous.filter(function (c) { return normaliser(c.id) === normaliser(id); })[0] || contratPourImport(classeur, id);
  const psn = psnSaisi(texte);
  const verrou = verrouDuClasseur_();
  if (!verrou.tryLock(15000)) throw new Error('Le classeur est occupé par un autre geste (archivage, import…) : le PSN n’est pas enregistré. Le retaper dans une minute.');
  try {
    const props = PropertiesService.getDocumentProperties();
    const tous = psnEnregistres_();
    Object.keys(tous).forEach(function (k) { if (normaliser(k) === normaliser(contrat.id)) delete tous[k]; });
    tous[contrat.id] = psn;
    props.setProperty(CLE_PSN, JSON.stringify(tous));
  } finally {
    verrou.releaseLock();
  }
  marquerDonneesModifiees_();
  const effectif = psnDuContrat(contrat.id);
  return { ok: true, contrat: contrat.id, psn: effectif.psn, source: effectif.source };
}

/* Le tri dit en clair, d'après ses parts [{ psn: [...] } | { colonne, valeurs }] :
   court pour la page (« PSN 4530 · WD »), détaillé pour le Diagnostic
   (« PSN 4530 · DIAGRAM TYPE WD »). */
function triCourt(parts) {
  return parts.map(function (p) { return p.psn ? 'PSN ' + p.psn.join(', ') : p.valeurs.join(', '); }).join(' · ');
}
function triDetaille(parts) {
  return parts.map(function (p) { return p.psn ? 'PSN ' + p.psn.join(', ') : p.colonne + ' ' + p.valeurs.join(', '); }).join(' · ');
}

/**
 * La ligne « Trié à l’import : … » posée par la fenêtre au-dessus de
 * l'en-tête d'une base triée, relue : { parts, lues, gardees, phrase }, ou
 * null. Seule la fenêtre l'écrit ; un extract collé à la main ne l'a pas.
 */
function marqueDeTri(donnees, ligneEntete) {
  const nombre = function (t) { const n = parseInt(String(t).replace(/[^\d]/g, ''), 10); return isNaN(n) ? null : n; };
  for (let i = 0; i < Math.min(Math.max(0, (ligneEntete || 1) - 1), donnees.length); i++) {
    const phrase = String(donnees[i] && donnees[i][0] !== undefined ? donnees[i][0] : '').trim();
    if (phrase.indexOf(MARQUE_TRI) !== 0) continue;
    const reste = phrase.slice(MARQUE_TRI.length), coupe = reste.indexOf(' — ');
    const parts = [];
    (coupe === -1 ? reste : reste.slice(0, coupe)).split(' · ').forEach(function (p) {
      let m = /^PSN (.+)$/.exec(p.trim());
      if (m) { parts.push({ psn: listePsn(m[1]) }); return; }
      m = /^(.+?) = (.+)$/.exec(p.trim());
      if (m) parts.push({ colonne: m[1].trim(), valeurs: m[2].split(/\s*,\s*/).filter(Boolean) });
    });
    const n = /([\d\s  ]+) lignes? gardées? sur ([\d\s  ]+)/.exec(reste);
    return { parts: parts, gardees: n ? nombre(n[1]) : null, lues: n ? nombre(n[2]) : null, phrase: phrase };
  }
  return null;
}

/**
 * Le tri d'une seconde base lue (t : lireTableauSecondeBase), pour un
 * contrat :
 *   – l'onglet porte la colonne des PSN ou une colonne de FILTRES (un
 *     extract collé à la main, ou importé avec toutes ses colonnes) : le tri
 *     est refait ici, avec le PSN du contrat — { source: 'lecture', lignes
 *     (gardées), lues, gardees, parts, texte, detail, psn, absentes
 *     (colonnes de tri configurées que l'onglet n'a pas) } ; la colonne des
 *     PSN sans PSN pour le contrat : { sansPsn: true } — rien n'est gardé ;
 *   – sinon, la ligne « Trié à l’import » de la fenêtre : { source:
 *     'import', lues (celles du fichier), gardees, parts, texte, detail,
 *     psn (celui de l'import) } — les lignes sont celles de l'onglet ;
 *   – sinon null : l'onglet est lu tel quel.
 * psnContrat : le PSN du contrat aujourd'hui, pour dire un écart.
 */
function trierSecondeBase(t, donnees, contrat) {
  const colPsn = colonnePsnSecondeBase(), filtres = filtresSecondeBase();
  const psnContrat = colPsn ? psnDuContrat(contrat).psn : [];
  const titreDe = function (cle) { return t.entetes.filter(function (e) { return e && cleTri(e) === cle; })[0] || ''; };
  const titrePsn = colPsn ? titreDe(cleTri(colPsn)) : '';
  const presents = filtres.map(function (f) { return { f: f, titre: titreDe(f.cle) }; }).filter(function (x) { return x.titre; });
  if (titrePsn || presents.length) {
    const absentes = (colPsn && !titrePsn ? [colPsn] : [])
      .concat(filtres.filter(function (f) { return !titreDe(f.cle); }).map(function (f) { return f.colonne; }));
    if (titrePsn && !psnContrat.length) {
      return { source: 'lecture', sansPsn: true, colonnePsn: titrePsn, lues: t.lignes.length, gardees: 0, parts: [], texte: '', detail: '',
               psn: [], psnContrat: [], absentes: absentes };
    }
    const voulus = {};
    psnContrat.forEach(function (j) { voulus[normaliser(j)] = true; });
    /* Les cellules de PSN se répètent d'une ligne à l'autre : chacune n'est découpée qu'une fois. */
    const memo = {};
    const lignes = t.lignes.filter(function (l) {
      for (let k = 0; k < presents.length; k++) {
        if (!presents[k].f.permises[cleTri(l[presents[k].titre])]) return false;
      }
      if (!titrePsn) return true;
      const cellule = String(l[titrePsn] === undefined || l[titrePsn] === null ? '' : l[titrePsn]);
      if (!Object.prototype.hasOwnProperty.call(memo, cellule)) memo[cellule] = cellulePorteUnPsn(cellule, voulus);
      return memo[cellule];
    });
    const parts = (titrePsn ? [{ psn: psnContrat }] : []).concat(presents.map(function (x) { return { colonne: x.f.colonne, valeurs: x.f.valeurs }; }));
    return { source: 'lecture', lignes: lignes, lues: t.lignes.length, gardees: lignes.length, parts: parts, texte: triCourt(parts), detail: triDetaille(parts),
             psn: titrePsn ? psnContrat : null, psnContrat: psnContrat, absentes: absentes };
  }
  const marque = marqueDeTri(donnees, t.ligneEntete);
  if (!marque || !marque.parts.length) return null;
  const psnImport = marque.parts.filter(function (p) { return p.psn; })[0];
  return { source: 'import', lues: marque.lues, gardees: t.lignes.length, parts: marque.parts, texte: triCourt(marque.parts),
           detail: triDetaille(marque.parts), psn: psnImport ? psnImport.psn : null, psnContrat: psnContrat, absentes: [], phrase: marque.phrase };
}

/** Deux listes de PSN disent-elles la même chose (ordre, casse et doublons indifférents) ? */
function memesPsn(a, b) {
  const k = function (l) { return listePsn(l).map(normaliser).sort().join(','); };
  return k(a || []) === k(b || []);
}

/**
 * Le tableau d'une seconde base, lu dans ses valeurs (un tableau de lignes) :
 *   { etat: 'vide' | 'sans-reference' | 'ok', entetes, ligneEntete,
 *     lignes: [{ intitulé: valeur }], clesReference, enteteLa }.
 * Sert à lireSecondeBase (l'onglet du classeur) et à la fin d'un import
 * (importSecondeBaseFin relit l'onglet posé) — les deux lisent de la même
 * façon.
 */
function lireTableauSecondeBase(donnees, clesVoulues) {
  let indexEntete = -1, premiereNonVide = -1, presque = -1, mieuxPortes = 0;
  const limite = Math.min(CONFIG.LIGNES_SCAN_ENTETE, donnees.length);
  for (let i = 0; i < limite && indexEntete === -1; i++) {
    if (!ligneNonVide(donnees[i])) continue;
    if (premiereNonVide === -1) premiereNonVide = i;
    const cellules = donnees[i].map(function (c) { return normaliser(String(c).trim()); });
    const portes = clesVoulues.filter(function (k) { return cellules.indexOf(normaliser(k)) !== -1; }).length;
    if (portes === clesVoulues.length) indexEntete = i;
    else if (portes > mieuxPortes) { mieuxPortes = portes; presque = i; }
  }
  /* Aucune ligne ne porte toute la référence. On retient alors celle qui en
     porte le plus, et non la première ligne non vide : dans SEE, celle-là est
     le titre « Nommage WD BFLOW », qui ne dit rien. Il suffit qu'une colonne
     ait été renommée dans l'export pour que le diagnostic montre le titre et
     conclue à un collage sans en-têtes — alors que l'en-tête est bien là,
     deux lignes plus bas, avec un intitulé de moins. */
  if (indexEntete === -1) indexEntete = presque !== -1 ? presque : premiereNonVide;
  if (indexEntete === -1) {
    for (let i = 0; i < donnees.length; i++) {
      if (ligneNonVide(donnees[i])) { indexEntete = i; break; }
    }
  }
  if (indexEntete === -1) {
    return { etat: 'vide', entetes: [], ligneEntete: null, lignes: [], clesReference: [], enteteLa: function () { return ''; } };
  }
  const entetes = donnees[indexEntete].map(function (e) { return String(e).trim(); });

  /* Un intitulé de la seconde base, retrouvé sans tenir compte de la casse ni
     des accents, mais rendu tel qu'il est écrit dans l'onglet. */
  function enteteLa(voulu) {
    const n = normaliser(voulu);
    for (let j = 0; j < entetes.length; j++) {
      if (entetes[j] && normaliser(entetes[j]) === n) return entetes[j];
    }
    return '';
  }
  const clesReference = clesVoulues.map(enteteLa);
  const rendu = { etat: 'ok', entetes: entetes, ligneEntete: indexEntete + 1, lignes: [], clesReference: clesReference, enteteLa: enteteLa };
  if (clesReference.some(function (c) { return !c; })) { rendu.etat = 'sans-reference'; return rendu; }

  for (let i = indexEntete + 1; i < donnees.length; i++) {
    if (!ligneNonVide(donnees[i])) continue;
    const ligne = {};
    /* Deux colonnes du même intitulé : la première compte — la même que
       retient l'import de la base (menu Suivi FWD). */
    entetes.forEach(function (titre, j) {
      if (!titre || Object.prototype.hasOwnProperty.call(ligne, titre)) return;
      ligne[titre] = String(donnees[i][j] === undefined ? '' : donnees[i][j]);
    });
    rendu.lignes.push(ligne);
  }
  return rendu;
}

// =====================================================================
//  DÉPÔT AUTOMATIQUE (application web, doPost)
// =====================================================================

/**
 * Point d'entrée des dépôts : un script (import/deposer.py) envoie un
 * extract en JSON, { secret, onglet, lignes: [[…], …], archiver, creer }.
 * La réponse est du JSON : { ok, onglet, lignes, colonnes, archive } ou
 * { ok: false, message }. Tout passe par deposer_(), testable sans requête.
 */
function doPost(e) {
  let reponse;
  try {
    const texte = e && e.postData && e.postData.contents ? String(e.postData.contents) : '';
    reponse = deposer_(texte);
  } catch (err) {
    /* Sans ce filet, Apps Script répondrait une page HTML d'erreur : le script
       appelant n'y comprendrait rien. */
    reponse = { ok: false, message: err && err.message ? err.message : String(err) };
  }
  return ContentService.createTextOutput(JSON.stringify(reponse))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Écrit les lignes reçues dans l'onglet nommé — vidé d'abord, comme le geste
 * Ctrl+A, Suppr, coller en A1 — puis, si `archiver` est vrai et que l'onglet
 * est un contrat, archive le relevé de la semaine pour ce contrat. Refuse
 * tout tant que CONFIG.DEPOT.SECRET est vide, et tout ce qui ne porte pas ce
 * secret. Un onglet d'historique n'est jamais une cible. Le « _ » : doPost
 * est sa seule porte, la page n'en ouvre pas une seconde.
 */
function deposer_(texte) {
  const cfg = CONFIG.DEPOT || {};
  const secret = String(cfg.SECRET || '');
  if (!secret) return { ok: false, message: 'Dépôt désactivé : CONFIG.DEPOT.SECRET est vide.' };
  const corps = analyserJson(texte);
  if (!corps || typeof corps !== 'object' || Array.isArray(corps)) return { ok: false, message: 'Corps illisible : un objet JSON est attendu.' };
  if (!memeSecret(String(corps.secret === undefined || corps.secret === null ? '' : corps.secret), secret)) {
    return { ok: false, message: 'Secret refusé.' };
  }
  const onglet = String(corps.onglet || '').trim();
  if (!onglet) return { ok: false, message: 'Onglet non nommé.' };
  if (!Array.isArray(corps.lignes)) return { ok: false, message: 'Lignes absentes : une liste de lignes est attendue.' };
  if (!corps.lignes.length) return { ok: false, message: 'Extract vide : rien à déposer. L\'onglet n\'est pas touché.' };
  /* MAX_LIGNES vaut ce qu'on y a mis, zéro compris : un zéro ferme le dépôt
     au lieu de rouvrir en grand. Absent ou illisible, la valeur par défaut. */
  const voulu = Number(cfg.MAX_LIGNES);
  const maxLignes = isNaN(voulu) || voulu < 0 ? 20000 : voulu;
  if (corps.lignes.length > maxLignes) return { ok: false, message: 'Trop de lignes : ' + corps.lignes.length + ' (au plus ' + maxLignes + ').' };

  /* Chaque ligne devient une rangée de chaînes, toutes de même largeur. Tout
     est préparé AVANT de toucher à l'onglet : un extract mal formé ne doit
     jamais laisser un onglet vidé. */
  const largeur = corps.lignes.reduce(function (m, l) { return Math.max(m, Array.isArray(l) ? l.length : 0); }, 0);
  if (!largeur) return { ok: false, message: 'Extract sans aucune colonne : rien à déposer. L\'onglet n\'est pas touché.' };
  const valeurs = corps.lignes.map(function (l) {
    const t = Array.isArray(l) ? l : [], out = [];
    for (let j = 0; j < largeur; j++) {
      const v = t[j];
      out.push(v === null || v === undefined || typeof v === 'object' ? '' : String(v));
    }
    return out;
  });

  /* Un onglet protégé n'est jamais une cible — même s'il n'existe pas
     encore : on ne le crée pas non plus. L'onglet de la seconde base, lui,
     se dépose comme un contrat. */
  const protege = ongletProtege(onglet);
  if (protege) return { ok: false, message: 'On ne dépose pas dans ' + protege + ' : « ' + onglet + ' ».' };
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  /* L'onglet se retrouve comme partout ailleurs : sans tenir compte de la
     casse ni des accents. Sinon « hdk » créerait un doublon de « HDK ». */
  let feuille = classeur.getSheetByName(onglet) || ongletNormalise(classeur, onglet);
  if (!feuille) {
    if (!corps.creer) return { ok: false, message: 'Onglet introuvable : « ' + onglet + ' ». Passer creer: true pour le créer.' };
    feuille = classeur.insertSheet(onglet);
  }
  feuille.clearContents();
  assurerColonnes(feuille, largeur);
  assurerLignes(feuille, valeurs.length);
  const plage = feuille.getRange(1, 1, valeurs.length, largeur);
  /* En format texte, une cellule qui commence par « = » reste ce qu'elle est :
     un extract ne doit pas se transformer en formules. */
  if (plage.setNumberFormat) plage.setNumberFormat('@');
  plage.setValues(valeurs);
  marquerDonneesModifiees_();
  const resultat = { ok: true, onglet: feuille.getName(), lignes: valeurs.length, colonnes: largeur };
  if (corps.archiver) {
    const contrat = listerContrats(classeur).filter(function (c) { return c.id === feuille.getName(); })[0];
    if (!contrat) {
      resultat.archive = { ok: false, message: '« ' + feuille.getName() + ' » n\'est pas un onglet de contrat : rien à archiver.' };
    } else {
      try {
        const detail = sousVerrou_(function () { return archiverContrat_(classeur, contrat, numeroSemaineISO(new Date())); });
        resultat.archive = { ok: true, semaine: detail.semaine, historique: detail.historique,
                             total: detail.compte.total, termine: detail.compte.termine };
      } catch (err) {
        resultat.archive = { ok: false, message: err && err.message ? err.message : String(err) };
      }
    }
  }
  return resultat;
}

/**
 * Deux secrets sont-ils le même ? La comparaison parcourt toujours la même
 * longueur : le temps de réponse ne dit pas combien de caractères sont justes.
 */
function memeSecret(donne, attendu) {
  if (donne.length !== attendu.length) return false;
  let ecart = 0;
  for (let i = 0; i < attendu.length; i++) ecart |= donne.charCodeAt(i) ^ attendu.charCodeAt(i);
  return ecart === 0;
}

/** Un onglet d'historique (le préfixe de CONFIG.FEUILLE_HISTORIQUE). */
function estOngletHistorique(nom) {
  const prefixe = normaliser(CONFIG.FEUILLE_HISTORIQUE);
  return !!prefixe && normaliser(nom).indexOf(prefixe) === 0;
}

/**
 * Ce qu'un dépôt n'a pas le droit d'écraser, dit en toutes lettres pour le
 * message d'erreur — ou '' si l'onglet est déposable. L'onglet de la seconde
 * base est déposable, lui : c'est une des cibles prévues.
 */
function ongletProtege(nom) {
  if (estOngletHistorique(nom)) return 'un onglet d\'historique';
  const n = normaliser(nom);
  const seconde = feuilleRapprochement() ? normaliser(feuilleRapprochement()) : '';
  if (seconde && n === seconde) return '';
  const internes = (CONFIG.FEUILLES_INTERNES || []).map(normaliser);
  return internes.indexOf(n) !== -1 ? 'un onglet réservé au script' : '';
}

/** L'onglet dont le nom correspond, sans tenir compte de la casse ni des accents. */
function ongletNormalise(classeur, nom) {
  const n = normaliser(nom);
  const feuilles = classeur.getSheets();
  for (let i = 0; i < feuilles.length; i++) {
    if (normaliser(feuilles[i].getName()) === n) return feuilles[i];
  }
  return null;
}

/** Élargit la grille en lignes, comme assurerColonnes le fait en colonnes. */
function assurerLignes(feuille, nbLignes) {
  if (!feuille.getMaxRows || !feuille.insertRowsAfter) return;
  const actuelles = feuille.getMaxRows();
  if (nbLignes > actuelles) feuille.insertRowsAfter(actuelles, nbLignes - actuelles);
}

// =====================================================================
//  IMPORT DES EXPORTS GATES ET SEE, SANS EXCEL
// =====================================================================

/**
 * « Je sélectionne les fichiers Excel qu'il faut, et directement ça les met
 * dans la bonne position, la sauvegarde, tout : j'ai même plus à les
 * copier-coller » (débrief 20) ; « le GATES de HDK, il ne faut pas qu'il le
 * devine : c'est le GATES HDK, et ça va direct dans HDK » (débrief 21). Le
 * menu Suivi FWD → Importer les exports GATES et SEE ouvre une fenêtre à
 * cases : une par contrat pour son export GATES, une pour l'extract SEE de
 * tous les porteurs. Chrome lit chaque fichier sur le poste, l'un après
 * l'autre — un .xlsx est un zip, il se décompresse et se lit au fil de
 * l'eau, sans Excel et sans tout charger —, vérifie à sa ligne d'en-têtes
 * qu'il est de la sorte de sa case, et l'envoie là où sa case le dit :
 *   – l'export GATES d'un contrat remplace l'onglet du contrat tel quel,
 *     comme un collage : chaque ligne à son numéro, chaque colonne de A à la
 *     dernière remplie, et les cellules fusionnées de la ligne des groupes —
 *     c'est par elles que la page reconnaît la colonne suivie (HDK AA 011).
 *     Puis, si la case est cochée, le relevé de la semaine de ce contrat est
 *     archivé ;
 *   – l'extract SEE est trié pour chaque contrat (son PSN, les schémas WD :
 *     CONFIG.RAPPROCHEMENT) et n'envoie, dans la base de chacun, que la ligne
 *     du tri, sa ligne d'en-tête et les colonnes de la comparaison (NAME,
 *     SOL., Cust.V) : quelques mégaoctets au lieu de centaines.
 * Les fichiers eux-mêmes ne quittent pas le poste.
 *
 * L'écriture se fait par lots dans un onglet temporaire — « HDK (import
 * 3f2a9c) », « SEE HDK (import 3f2a9c) » —, taillé d'avance à la mesure des
 * données ; l'onglet visé n'est remplacé qu'une fois toutes les lignes
 * reçues, à sa place et sous son nom : l'historique, rangé sous ce nom
 * (Historique_FWD_HDK), suit sans rien faire. Un import interrompu laisse
 * l'ancien en place. Chaque appel de la fenêtre présente le jeton reçu à son
 * ouverture, ou passe la garde des gestes qui écrivent : rien de tout cela
 * n'est possible depuis la page du tableau de bord.
 *
 * Les fonctions gardent leur nom d'origine (importSecondeBase…) : SEE a été
 * importé le premier, et une fenêtre ouverte avant une livraison les appelle
 * encore ainsi. Elles servent désormais aux deux sortes d'export.
 */
/* L'étiquette des onglets d'un import : six chiffres hexadécimaux, dont au
   moins une lettre (etiquetteImport) — ce qu'un onglet nommé à la main,
   « HDK (ancien export) » ou « HDK (ancien 041026) », n'a pas : celui-là
   reste un onglet comme un autre, jamais retiré par un import. */
const IMPORT_MOTIF = / \((import|ancien) ((?=[0-9a-f]*[a-f])[0-9a-f]{6})\)$/;
const IMPORT_MAX_LIGNES_LOT = 20000;
const IMPORT_MAX_COLONNES = 400;
const IMPORT_MAX_FUSIONS = 2000;
const IMPORT_MAX_REFERENCES = 30000;       // par contrat : ce que la fenêtre reçoit pour compter les plans en commun
/* La part de ses plans qu'un export GATES doit partager avec l'onglet qu'il
   remplace pour que la fenêtre ne pose pas la question « est-ce bien son
   export ? » — et celle qu'il faut à l'historique orphelin pour désigner
   son contrat (proprietaireProbable_). */
const IMPORT_SEUIL_RECOUVREMENT = 0.2;
const IMPORT_LIMITE_CELLULES = 10000000;   // la limite d'un classeur Google Sheets, cellules vides comprises
/* Un vrai .xls (ou une page web archivée) se lit en entier dans la fenêtre :
   au-delà, ce n'est pas un export (un .xls s'arrête à 65 536 lignes). */
const IMPORT_MAX_OCTETS_XLS = 200 * 1048576;
const CLE_JETON_IMPORT = 'SUIVI_FWD_JETON_IMPORT';
const IMPORT_JETON_DUREE = 6 * 3600 * 1000;
/* Le nom d'un nouveau contrat devient celui de son onglet, de son historique
   (« Historique_FWD_ » devant) et de l'onglet temporaire de ses imports
   (« (import xxxxxx) » derrière) : 80 caractères laissent les trois sous la
   centaine qu'accepte un nom d'onglet. */
const NOM_CONTRAT_MAX = 80;

/** Le libellé de l'article du menu — le même au menu, en titre de la fenêtre et dans le Diagnostic. */
function libelleImport() {
  const base = feuilleRapprochement();
  return 'Importer les exports GATES' + (base ? ' et ' + base : '') + '…';
}

/** Le chemin du menu, pour les messages qui disent le geste : l'import d'abord, le collage ensuite. */
function cheminImport() {
  return 'menu Suivi FWD → ' + libelleImport();
}

/**
 * Un onglet laissé par un import : le temporaire, « HDK (import 3f2a9c) »,
 * ou l'ancien mis de côté le temps de l'échange, « HDK (ancien 3f2a9c) ».
 * Ni l'un ni l'autre n'est jamais un contrat ni une base SEE : un import
 * interrompu ne fait pas apparaître un contrat de plus.
 */
function estOngletImport(nom) {
  return IMPORT_MOTIF.test(String(nom === undefined || nom === null ? '' : nom));
}

/** Six chiffres hexadécimaux, dont au moins une lettre : l'étiquette d'un import (voir IMPORT_MOTIF). */
function etiquetteImport() {
  let id = ('00000' + Math.floor(Math.random() * 0x1000000).toString(16)).slice(-6);
  if (!/[a-f]/.test(id)) id = 'a' + id.slice(1);
  return id;
}

/** Le nom visé par un onglet d'import (« HDK » pour « HDK (import 3f2a9c) »), ou null. */
function soucheDOngletImport(nom) {
  const n = String(nom === undefined || nom === null ? '' : nom), m = IMPORT_MOTIF.exec(n);
  return m ? n.slice(0, m.index) : null;
}

/** Le nom de la base d'un contrat, écrit en toutes lettres : « SEE HDK ». */
function souchePourImport(idContrat) {
  return feuilleRapprochement() + ' ' + idContrat;
}

/** Les intitulés de la référence de la seconde base (CONFIG.RAPPROCHEMENT.CLE_REFERENCE), épurés. */
function clesSecondeBase() {
  const cfg = CONFIG.RAPPROCHEMENT;
  return !cfg ? [] : [].concat(cfg.CLE_REFERENCE === undefined || cfg.CLE_REFERENCE === null ? [] : cfg.CLE_REFERENCE)
    .map(function (c) { return String(c).trim(); }).filter(Boolean);
}

/**
 * Le jeton de la fenêtre d'import, posé par le menu (dans le classeur). Les
 * appels de la fenêtre le présentent ; sans lui, ils doivent passer la garde
 * des gestes qui écrivent. La page du tableau de bord n'a ni l'un ni
 * l'autre : le jeton ne s'écrit que dans la fenêtre ouverte par le menu.
 */
function ouvrirJetonImport_() {
  /* Le « _ » final la cache de google.script.run : la page du tableau de
     bord, ouverte par toute l'organisation, ne peut pas se faire donner un
     jeton (débrief 20). Seul le menu, côté serveur, l'appelle. */
  const jeton = (Utilities.getUuid() + Utilities.getUuid()).replace(/[^0-9a-z]/gi, '');
  PropertiesService.getDocumentProperties().setProperty(CLE_JETON_IMPORT,
    JSON.stringify({ jeton: jeton, expire: new Date().getTime() + IMPORT_JETON_DUREE }));
  return jeton;
}
function gesteImport_(jeton) {
  let valide = false;
  try {
    const v = JSON.parse(PropertiesService.getDocumentProperties().getProperty(CLE_JETON_IMPORT) || 'null');
    valide = !!v && typeof v.jeton === 'string' && typeof jeton === 'string' && jeton.length >= 8 &&
      memeSecret(jeton, v.jeton) && Number(v.expire) > new Date().getTime();
  } catch (err) { valide = false; }
  if (!valide) gesteDuClasseur();
}

/**
 * Menu : la fenêtre d'import. Elle s'ouvre même sans contrat ni seconde base
 * configurée — « Ajouter un contrat… » crée le premier ; sans seconde base,
 * elle n'a que les cases GATES. Le nom de la fonction est resté celui de
 * l'import SEE, le premier : le menu l'appelle ainsi.
 */
function importerSecondeBase() {
  gesteDuClasseur();
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const page = HtmlService.createHtmlOutput(pageImportSecondeBase(parametresImport_(classeur))).setWidth(760).setHeight(700);
  SpreadsheetApp.getUi().showModalDialog(page, libelleImport().replace(/…$/, ''));
}

/**
 * Ce que la fenêtre reçoit à son ouverture. Les règles qui reconnaissent un
 * export sont celles du serveur, transmises et non recopiées : la ligne
 * d'en-têtes d'un export GATES (ligneDEnteteDExport), la colonne de
 * référence (trouverIndexReference), les colonnes de la seconde base, et son
 * tri (COLONNE_PSN, FILTRES, le PSN de la configuration pour un contrat qui
 * naît dans la fenêtre). Et, pour chaque contrat, sa case : son onglet SEE,
 * son PSN, et les références de ses plans, normalisées — de quoi dire qu'un
 * export GATES posé dans sa case partage peu de plans avec lui.
 */
function parametresImport_(classeur) {
  const cfg = CONFIG.RAPPROCHEMENT;
  const base = feuilleRapprochement();
  const cles = clesSecondeBase();
  const avecBase = !!base && cles.length > 0;
  const semaine = numeroSemaineISO(new Date());
  const parConfig = {};
  if (avecBase && cfg && cfg.PSN && typeof cfg.PSN === 'object') {
    Object.keys(cfg.PSN).forEach(function (k) { const p = listePsn(cfg.PSN[k]); if (p.length) parConfig[normaliser(k)] = p; });
  }
  return {
    jeton: ouvrirJetonImport_(),
    base: avecBase ? base : '',
    cles: avecBase ? cles : [],
    essentielles: avecBase ? (Array.isArray(cfg.ESSENTIELLES) ? cfg.ESSENTIELLES : []).map(function (c) { return String(c).trim(); }).filter(Boolean) : [],
    colonnePsn: avecBase ? colonnePsnSecondeBase() : '',
    filtres: avecBase ? filtresSecondeBase().map(function (f) { return { colonne: f.colonne, valeurs: f.valeurs }; }) : [],
    psnConfig: parConfig,
    psnForme: PSN_FORME.source,
    psnMax: PSN_MAX,
    marqueTri: MARQUE_TRI,
    lignesScan: CONFIG.LIGNES_SCAN_ENTETE,
    motsCles: CONFIG.MOTS_CLES_ENTETE.map(normaliser),
    minIntitules: ENTETE_EXPORT_MIN_INTITULES,
    minMotsCles: ENTETE_EXPORT_MIN_MOTS,
    motifsReference: MOTIFS_REFERENCE,
    maxLignesLot: IMPORT_MAX_LIGNES_LOT,
    maxColonnes: IMPORT_MAX_COLONNES,
    maxCellulesToutes: 4000000,
    maxOctetsXls: IMPORT_MAX_OCTETS_XLS,
    pausesReprise: [2000, 6000],
    seuilRecouvrement: IMPORT_SEUIL_RECOUVREMENT,
    contrats: contratsPourImport_(classeur),
    nouveauPermis: !CONFIG.FEUILLE_DONNEES,
    nomMax: NOM_CONTRAT_MAX,
    semaine: semaineDite(semaine, semaine)
  };
}

/**
 * Les contrats tels que la fenêtre les voit, un par case : [{ id, onglet (sa
 * base SEE, existante ou à créer), existe, refs, psn, psnSource }]. Sans
 * jeton : parametresImport_ en ouvre un, et importContrats, qui relit la
 * liste après un import, n'en ouvre pas.
 */
function contratsPourImport_(classeur) {
  const base = feuilleRapprochement();
  const avecBase = !!base && clesSecondeBase().length > 0;
  let contrats = [];
  try { contrats = listerContrats(classeur); } catch (err) { contrats = []; }
  return enLecture(function () {
    return contrats.map(function (c) {
      const f = avecBase ? ongletSecondeBase(classeur, c.id) : null;
      let refs = [];
      try { refs = referencesNormalisees(classeur.getSheetByName(c.id)); } catch (err) { refs = []; }
      const p = avecBase ? psnDuContrat(c.id) : { psn: [], source: '' };
      return { id: c.id, onglet: f ? f.getName() : souchePourImport(c.id), existe: !!f, refs: refs, psn: p.psn, psnSource: p.source };
    });
  });
}

/**
 * La fenêtre relit la liste des contrats après chaque import : un contrat
 * créé au premier tour a sa case au second, et sa base SEE son nom. Le même
 * jeton : aucun nouveau n'est ouvert.
 */
function importContrats(jeton) {
  gesteImport_(jeton);
  return contratsPourImport_(SpreadsheetApp.getActiveSpreadsheet());
}

/**
 * Les références des plans d'un onglet de contrat, lues comme la page les
 * lit : la ligne d'en-têtes (detecterLigneEntete), la colonne de référence
 * (trouverIndexReference), les cellules non vides dessous. Deux lectures
 * étroites — le haut de l'onglet, puis une colonne —, pas l'onglet entier.
 */
function referencesDeLOnglet(feuille) {
  if (!feuille) return [];
  const derniere = feuille.getLastRow(), largeur = feuille.getLastColumn();
  if (derniere < 2 || largeur < 1) return [];
  const haut = feuille.getRange(1, 1, Math.min(CONFIG.LIGNES_SCAN_ENTETE, derniere), largeur).getDisplayValues();
  const iEntete = detecterLigneEntete(haut);
  const iRef = trouverIndexReference(haut[iEntete].map(function (e) { return String(e).trim(); }));
  if (derniere <= iEntete + 1) return [];
  return feuille.getRange(iEntete + 2, iRef + 1, derniere - iEntete - 1, 1).getDisplayValues()
    .map(function (l) { return String(l[0]).trim(); }).filter(Boolean);
}

/** Les mêmes, normalisées et sans doublon, pour la fenêtre. */
function referencesNormalisees(feuille) {
  const vues = {}, liste = [];
  referencesDeLOnglet(feuille).forEach(function (r) {
    const n = normaliser(r);
    if (n && !Object.prototype.hasOwnProperty.call(vues, n)) { vues[n] = true; liste.push(n); }
  });
  return liste.slice(0, IMPORT_MAX_REFERENCES);
}

/** Le contrat nommé, ou une erreur qui le nomme. */
function contratPourImport(classeur, idContrat) {
  const id = String(idContrat === undefined || idContrat === null ? '' : idContrat);
  const contrat = listerContrats(classeur).filter(function (c) { return c.id === id; })[0];
  if (!contrat) throw new Error('Contrat introuvable : « ' + id + ' ». Rouvrir le ' + cheminImport());
  return contrat;
}

/**
 * Le nom d'un nouveau contrat, vérifié : il deviendra le nom d'un onglet, et
 * le contrat n'existe que par lui. Refusé s'il est vide ou trop long, s'il
 * est celui d'un onglet de service, d'une base SEE, d'un historique, d'un
 * import ou d'une copie (aucun ne serait un contrat), ou d'un onglet qui
 * existe déjà — casse et accents indifférents, comme partout.
 */
function nomNouveauContrat(classeur, brut) {
  const nom = String(brut === undefined || brut === null ? '' : brut).trim();
  if (!nom) throw new Error('Le nouveau contrat n’a pas de nom : écrire celui de son onglet, comme « HDK ».');
  if (nom.length > NOM_CONTRAT_MAX) throw new Error('Nom trop long : ' + nom.length + ' caractères (au plus ' + NOM_CONTRAT_MAX + ').');
  if (estOngletInterne(nom) || estOngletImport(nom) || estCopieDOnglet(nom)) {
    throw new Error('« ' + nom + ' » est un nom réservé (base ' + (feuilleRapprochement() || 'SEE') + ', historique, onglet de service, ' +
      'd’import ou copie) : il ne serait pas un contrat. Donner au contrat le nom de son onglet, comme « HDK ».');
  }
  const deja = classeur.getSheetByName(nom) || ongletNormalise(classeur, nom);
  if (deja) {
    let estContrat = false;
    try { estContrat = listerContrats(classeur).some(function (c) { return c.id === deja.getName(); }); } catch (err) { estContrat = false; }
    throw new Error(estContrat
      ? 'Le contrat « ' + deja.getName() + ' » existe déjà : son export va dans sa case, « GATES ' + deja.getName() + ' ».'
      : 'Un onglet « ' + deja.getName() + ' » existe déjà : choisir un autre nom, ou renommer cet onglet.');
  }
  return nom;
}

/** La fenêtre vérifie le nom d'un nouveau contrat dès qu'il est tapé : { ok, nom } ou { ok: false, message }. */
function importVerifierNouveauContrat(jeton, nom) {
  gesteImport_(jeton);
  try {
    return { ok: true, nom: nomNouveauContrat(SpreadsheetApp.getActiveSpreadsheet(), nom) };
  } catch (err) {
    return { ok: false, message: err && err.message ? err.message : String(err) };
  }
}

/**
 * La cible d'un import, résolue et vérifiée — ce que la fenêtre envoie, un
 * objet { sorte: 'gates' | 'see', contrat, nouveau }, ou l'identifiant d'un
 * contrat tout court (une base SEE : la forme d'avant le débrief 20) :
 *   { sorte, contrat, nouveau, onglet (le nom visé), souche (le nom qui
 *     préfixe l'onglet temporaire), existant (l'onglet remplacé, ou null) }.
 */
function cibleImport(classeur, cible) {
  const c = cible !== null && typeof cible === 'object' ? cible : { sorte: 'see', contrat: cible };
  if (c.sorte === 'see') {
    if (!feuilleRapprochement() || !clesSecondeBase().length) {
      throw new Error('Aucune seconde base n’est configurée (CONFIG.RAPPROCHEMENT dans Code) : rien à importer comme ' + (feuilleRapprochement() || 'SEE') + '.');
    }
    const contrat = contratPourImport(classeur, c.contrat);
    const existant = ongletSecondeBase(classeur, contrat.id);
    const souche = souchePourImport(contrat.id);
    return { sorte: 'see', contrat: contrat.id, nouveau: false, onglet: existant ? existant.getName() : souche, souche: souche, existant: existant };
  }
  if (c.sorte !== 'gates') throw new Error('Sorte d’import inconnue : « ' + String(c.sorte).slice(0, 20) + ' ».');
  if (c.nouveau) {
    if (CONFIG.FEUILLE_DONNEES) throw new Error('CONFIG.FEUILLE_DONNEES impose un seul contrat, « ' + CONFIG.FEUILLE_DONNEES + ' » : pas de nouveau contrat.');
    const nom = nomNouveauContrat(classeur, c.contrat);
    return { sorte: 'gates', contrat: nom, nouveau: true, onglet: nom, souche: nom, existant: null };
  }
  const contrat = contratPourImport(classeur, c.contrat);
  return { sorte: 'gates', contrat: contrat.id, nouveau: false, onglet: contrat.id, souche: contrat.id,
           existant: classeur.getSheetByName(contrat.id) };
}

/** L'onglet temporaire d'un import en cours — jamais un autre onglet, ni l'ancien mis de côté. */
function feuilleImportEnCours(classeur, nom) {
  const n = String(nom === undefined || nom === null ? '' : nom), m = IMPORT_MOTIF.exec(n);
  if (!m || m[1] !== 'import') throw new Error('Onglet d’import non reconnu : « ' + n + ' ».');
  const feuille = classeur.getSheetByName(n);
  if (!feuille) {
    throw new Error('L’onglet d’import « ' + n + ' » a disparu (un autre import de ce contrat a-t-il été lancé ?) : relancer l’import.');
  }
  return feuille;
}

/** Les cellules de la grille du classeur, vides comprises : ce que compte Sheets. */
function cellulesDuClasseur(classeur) {
  return classeur.getSheets().reduce(function (s, f) { return s + f.getMaxRows() * f.getMaxColumns(); }, 0);
}

/**
 * Les restes d'un import du même onglet — fenêtre fermée en cours d'envoi,
 * échange coupé, ou import lancé en même temps : retirés. Un envoi encore en
 * cours s'arrête net (« a disparu »), sans jamais mêler deux fichiers.
 */
function retirerRestesDImport(classeur, souche) {
  classeur.getSheets().slice().forEach(function (f) {
    const s = soucheDOngletImport(f.getName());
    if (s !== null && nomCompact(s) === nomCompact(souche)) classeur.deleteSheet(f);
  });
}

/**
 * Début d'un import : un onglet temporaire taillé à la mesure des données —
 * `largeur` colonnes, `total` lignes —, en bas du classeur. Sheets compte
 * chaque cellule de la grille, vide ou pas, dans sa limite de dix millions :
 * un onglet neuf en a 26 colonnes, d'où la taille posée d'avance, et le
 * compte fait avant le moindre envoi — sans l'onglet remplacé, qui s'en ira,
 * mais en sachant que l'ancien et le nouveau coexistent le temps de
 * l'import. `cible` : voir cibleImport.
 * @return {{feuille: string, onglet: string}}
 */
function importSecondeBaseDebut(jeton, cible, largeur, total) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const larg = Math.floor(Number(largeur)), lignes = Math.floor(Number(total));
  if (!(larg >= 1 && larg <= IMPORT_MAX_COLONNES)) throw new Error('Nombre de colonnes illisible : ' + largeur + ' (au plus ' + IMPORT_MAX_COLONNES + ').');
  if (!(lignes >= 2)) throw new Error('Rien à importer : l’en-tête seul.');
  /* Le début ne touche qu'à l'onglet temporaire : sans le verrou, il passe
     quand même (seule la fin, qui échange les onglets, l'exige). */
  const verrou = verrouDuClasseur_();
  const tenu = verrou.tryLock(30000);
  try {
    const c = cibleImport(classeur, cible);
    retirerRestesDImport(classeur, c.souche);
    const occupees = cellulesDuClasseur(classeur), voulues = lignes * larg;
    const remplacees = c.existant ? c.existant.getMaxRows() * c.existant.getMaxColumns() : 0;
    const geste = (c.sorte === 'see' && larg > clesSecondeBase().length ? 'Décocher « Garder aussi les autres colonnes », ou ' : '') +
      'supprimer les onglets qui ne servent plus.';
    if (occupees - remplacees + voulues > IMPORT_LIMITE_CELLULES) {
      throw new Error('Le classeur dépasserait la limite de Google Sheets : 10 millions de cellules, vides comprises. Il en compte déjà ' +
        (occupees - remplacees) + (remplacees ? ' (sans l’onglet « ' + c.onglet + ' », qu’il remplacera)' : '') + ', l’import en demande ' +
        voulues + ' (' + lignes + ' lignes × ' + larg + ' colonnes). ' + geste);
    }
    if (occupees + voulues > IMPORT_LIMITE_CELLULES) {
      throw new Error('Le classeur dépasserait la limite de Google Sheets : 10 millions de cellules, vides comprises. Le temps de l’import, ' +
        'l’ancien onglet « ' + c.onglet + ' » (' + remplacees + ' cellules) et le nouveau (' + voulues + ') coexistent : il en faudrait ' +
        (occupees + voulues) + '. ' + geste);
    }
    const nom = c.souche + ' (import ' + etiquetteImport() + ')';
    const feuille = classeur.insertSheet(nom, classeur.getSheets().length);
    if (feuille.getMaxColumns() > larg) feuille.deleteColumns(larg + 1, feuille.getMaxColumns() - larg);
    else assurerColonnes(feuille, larg);
    if (feuille.getMaxRows() > lignes) feuille.deleteRows(lignes + 1, feuille.getMaxRows() - lignes);
    else assurerLignes(feuille, lignes);
    return { feuille: nom, onglet: c.onglet };
  } finally {
    if (tenu) verrou.releaseLock();
  }
}

/**
 * Un lot de lignes, écrit à partir de la ligne `premiere` (1-based) de
 * l'onglet temporaire. Tout est vérifié avant d'écrire ; chaque cellule
 * est posée en texte (une valeur « =… » ne devient pas une formule, « 01 »
 * reste « 01 ») : ce que la fenêtre envoie est déjà ce que la cellule doit
 * montrer.
 * @return {{ecrites: number}}
 */
function importSecondeBaseLot(jeton, nomFeuille, premiere, lignes) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = feuilleImportEnCours(classeur, nomFeuille);
  const debut = Number(premiere);
  if (!(debut >= 1) || Math.floor(debut) !== debut) throw new Error('Ligne de départ illisible : ' + premiere);
  if (!Array.isArray(lignes) || !lignes.length) throw new Error('Lot vide.');
  if (lignes.length > IMPORT_MAX_LIGNES_LOT) throw new Error('Lot trop grand : ' + lignes.length + ' lignes (au plus ' + IMPORT_MAX_LIGNES_LOT + ').');
  const largeur = lignes.reduce(function (m, l) { return Math.max(m, Array.isArray(l) ? l.length : 0); }, 0);
  if (!largeur) throw new Error('Lot sans colonne.');
  if (largeur > IMPORT_MAX_COLONNES) throw new Error('Trop de colonnes : ' + largeur + ' (au plus ' + IMPORT_MAX_COLONNES + ').');
  const valeurs = lignes.map(function (l) {
    const t = Array.isArray(l) ? l : [], out = [];
    for (let j = 0; j < largeur; j++) {
      const v = t[j];
      /* Une cellule de Sheets ne tient pas plus de 50 000 caractères. */
      out.push(v === null || v === undefined || typeof v === 'object' ? '' : String(v).slice(0, 50000));
    }
    return out;
  });
  assurerColonnes(feuille, largeur);
  assurerLignes(feuille, debut + valeurs.length - 1);
  const plage = feuille.getRange(debut, 1, valeurs.length, largeur);
  if (plage.setNumberFormat) plage.setNumberFormat('@');
  plage.setValues(valeurs);
  return { ecrites: valeurs.length };
}

/**
 * Les cellules fusionnées qu'envoie la fenêtre, { ligne, col, nbLignes,
 * nbCols } en 1-based, vérifiées et rognées à l'onglet ; celles d'une seule
 * cellule sont laissées.
 */
function fusionsAPoser(fusions, nbLignes, nbColonnes) {
  return (Array.isArray(fusions) ? fusions : []).slice(0, IMPORT_MAX_FUSIONS).map(function (f) {
    const o = f !== null && typeof f === 'object' ? f : {};
    const ligne = Math.floor(Number(o.ligne)), col = Math.floor(Number(o.col));
    const finLigne = Math.min(nbLignes, ligne + Math.floor(Number(o.nbLignes)) - 1);
    const finCol = Math.min(nbColonnes, col + Math.floor(Number(o.nbCols)) - 1);
    return { ligne: ligne, col: col, nbLignes: finLigne - ligne + 1, nbCols: finCol - col + 1 };
  }).filter(function (f) {
    return f.ligne >= 1 && f.col >= 1 && f.nbLignes >= 1 && f.nbCols >= 1 && f.nbLignes * f.nbCols > 1;
  });
}

/**
 * Fin d'un import : si l'onglet temporaire a bien toutes ses lignes, il
 * prend la place — et le nom — de l'onglet visé, à sa position. Rien ne se
 * perd en route : l'ancien est d'abord mis de côté sous un autre nom, le
 * nouveau prend le sien, puis l'ancien s'en va. Pour un export GATES, les
 * cellules fusionnées de la ligne des groupes sont recréées AVANT l'échange :
 * la page lit l'onglet dès qu'il porte son nom. Un nouveau contrat se range
 * après le dernier onglet de contrat.
 *
 * Ensuite, l'onglet en place est relu — une panne ici ne défait rien : pour
 * SEE, sa ligne d'en-tête (la page la lira-t-elle ?) ; pour GATES, tout,
 * avec la logique même de la page (construireModele) : le nombre de plans,
 * la colonne suivie « groupe > intitulé » ou null, le concept harnais.
 */
function importSecondeBaseFin(jeton, nomFeuille, cible, lignesAttendues, fusions) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = feuilleImportEnCours(classeur, nomFeuille);
  const verrou = verrouDuClasseur_();
  if (!verrou.tryLock(30000)) {
    /* Un autre geste tient le classeur (le vendredi archive peut-être
       l'onglet que l'import remplacerait) : échanger quand même pouvait
       retirer l'onglet sous ses yeux. On refuse, avant tout échange ;
       l'onglet temporaire s'en va, l'onglet visé reste ce qu'il était. */
    let vise = soucheDOngletImport(feuille.getName()) || '', existe = true;
    try { const k = cibleImport(classeur, cible); vise = k.onglet; existe = !!k.existant; } catch (err) { /* le nom de l'import suffit */ }
    classeur.deleteSheet(feuille);
    throw new Error('Le classeur est occupé par un autre geste (archivage…) : l’onglet « ' + vise + ' » n’a pas été ' +
      (existe ? 'remplacé' : 'créé') + '. Relancer l’import dans une minute.');
  }
  let c = null, recues = 0, derniereColonne = 1, remplace = false, posees = 0, ratees = 0;
  const renommes = [];
  try {
    try {
      c = cibleImport(classeur, cible);
    } catch (err) {
      /* Le contrat a disparu, ou le nom du nouveau est pris depuis : rien
         n'est échangé, l'onglet temporaire ne sert plus. */
      classeur.deleteSheet(feuille);
      throw err;
    }
    if (nomCompact(soucheDOngletImport(feuille.getName())) !== nomCompact(c.souche)) {
      throw new Error('Onglet d’import non reconnu : « ' + feuille.getName() + ' » n’est pas celui de « ' + c.onglet + ' ».');
    }
    recues = feuille.getLastRow();
    if (recues !== Number(lignesAttendues)) {
      classeur.deleteSheet(feuille);
      throw new Error('Import incomplet : ' + recues + ' lignes reçues sur ' + lignesAttendues + '.');
    }
    derniereColonne = Math.max(1, feuille.getLastColumn());
    if (feuille.getMaxRows() > recues) feuille.deleteRows(recues + 1, feuille.getMaxRows() - recues);
    if (feuille.getMaxColumns() > derniereColonne) feuille.deleteColumns(derniereColonne + 1, feuille.getMaxColumns() - derniereColonne);
    if (c.sorte === 'gates') {
      fusionsAPoser(fusions, recues, derniereColonne).forEach(function (f) {
        try { feuille.getRange(f.ligne, f.col, f.nbLignes, f.nbCols).merge(); posees++; } catch (err) { ratees++; }
      });
    }
    const existant = c.existant;
    /* Un export où la page ne trouverait pas la colonne suivie ne remplace
       pas un onglet où elle la trouve : ce serait échanger un contrat qui se
       lit contre un contrat muet (un export d'un autre programme, un export
       sans le bloc suivi). L'ancien reste ; l'onglet temporaire s'en va. */
    if (c.sorte === 'gates' && existant && CONFIG.COLONNE_FWD &&
        colonneSuivieLue_(existant) && !colonneSuivieLue_(feuille)) {
      classeur.deleteSheet(feuille);
      throw new Error('Colonne suivie absente de cet export : « ' + CONFIG.COLONNE_FWD.replace('>', '›') + ' » n’y est pas, alors que l’onglet « ' +
        c.onglet + ' » l’a. Est-ce bien l’export de ce contrat, avec son bloc suivi ?');
    }
    if (c.sorte === 'gates' && c.nouveau) rattacherAuContratUnique_(classeur, renommes);
    remplace = !!existant;
    let position = 0;
    if (existant) {
      position = existant.getIndex();
      existant.setName(c.souche + ' (ancien ' + IMPORT_MOTIF.exec(feuille.getName())[2] + ')');
    } else if (c.sorte === 'gates') {
      /* Un nouveau contrat : juste après le dernier onglet de contrat (un
         onglet d'import n'en est jamais un). */
      listerContrats(classeur).forEach(function (k) {
        const f = classeur.getSheetByName(k.id);
        if (f) position = Math.max(position, f.getIndex());
      });
      position += 1;
    }
    feuille.setName(c.onglet);
    if (position) {
      classeur.setActiveSheet(feuille);
      classeur.moveActiveSheet(position);
    }
    if (existant) classeur.deleteSheet(existant);
    marquerDonneesModifiees_();
  } finally {
    verrou.releaseLock();
  }
  if (c.sorte === 'see') {
    /* L'en-tête relu comme la page le cherchera : en ligne 1, ou en ligne 2
       sous la ligne « Trié à l’import » d'une base triée (débrief 21). */
    let etat = 'ok', entete = 1;
    try {
      const tete = feuille.getRange(1, 1, Math.min(CONFIG.LIGNES_SCAN_ENTETE, recues), derniereColonne).getDisplayValues();
      const t = lireTableauSecondeBase(tete, clesSecondeBase());
      if (t.etat !== 'ok') etat = 'sans-reference';
      else entete = t.ligneEntete;
    } catch (err) { etat = 'non relu'; }
    return { onglet: c.onglet, remplace: remplace, lignes: recues - entete, colonnes: derniereColonne, etat: etat };
  }
  const rendu = { sorte: 'gates', onglet: c.onglet, nouveau: c.nouveau, remplace: remplace, lignes: recues, colonnes: derniereColonne,
                  fusions: posees, fusionsRatees: ratees, etat: 'ok', plans: 0, colonneSuivie: null, concept: false,
                  conceptDemande: !!CONFIG.COLONNE_CONCEPT, renommes: renommes };
  try {
    enLecture(function () {
      const m = construireModele(c.onglet);
      const col = m.colonnes.filter(function (k) { return k.cle === 'avancement'; })[0];
      rendu.plans = plansUniques(m.plans).length;
      rendu.colonneSuivie = !m.fwdDemandeeAbsente && col ? (col.groupe ? col.groupe + ' > ' : '') + col.titre : null;
      rendu.concept = !!m.cleConcept;
    });
  } catch (err) {
    rendu.etat = 'non relu';
    rendu.message = err && err.message ? err.message : String(err);
  }
  return rendu;
}

/**
 * Un deuxième contrat va naître. Tant que le classeur n'en avait qu'un, X,
 * deux onglets lui appartenaient sans porter son nom : l'onglet « SEE » tout
 * court (sa base) et l'ancien « Historique_FWD » (ses relevés). Dès qu'il y
 * en a deux, ni l'un ni l'autre n'est plus lu (ongletSecondeBase,
 * getFeuilleHistorique) : la comparaison de X disparaissait de la page, un
 * « SEE X » neuf s'ouvrait à côté d'un « SEE » orphelin, et ses relevés
 * sortaient de la page. Le propriétaire est certain — c'était le seul
 * contrat — : ils prennent son nom, avant l'échange. Seulement si le nom
 * propre n'existe pas encore (sinon c'est lui qu'on lit déjà). Appelé sous
 * le verrou ; chaque renommage est noté dans `renommes` ({ de, vers }) pour
 * que la fenêtre le dise.
 */
function rattacherAuContratUnique_(classeur, renommes) {
  let avant = [];
  try { avant = listerContrats(classeur); } catch (err) { avant = []; }
  if (avant.length !== 1) return;
  const x = avant[0].id;
  const feuilles = classeur.getSheets();
  const renommer = function (f, nom) {
    const de = f.getName();
    try { f.setName(nom); renommes.push({ de: de, vers: nom }); } catch (err) { /* laissé tel quel : le Diagnostic le signalera */ }
  };
  const base = feuilleRapprochement();
  if (base) {
    const b = nomCompact(base), cx = nomCompact(x);
    const propre = feuilles.some(function (f) { const n = nomCompact(f.getName()); return n === b + ' ' + cx || n === cx + ' ' + b; });
    const generique = feuilles.filter(function (f) { return nomCompact(f.getName()) === b; })[0];
    if (generique && !propre) renommer(generique, base + ' ' + x);
  }
  const ancien = classeur.getSheetByName(CONFIG.FEUILLE_HISTORIQUE);
  if (ancien && !classeur.getSheetByName(nomFeuilleHistorique(x))) renommer(ancien, nomFeuilleHistorique(x));
}

/**
 * La page lirait-elle la colonne suivie (CONFIG.COLONNE_FWD) dans cet
 * onglet ? Les mêmes gestes que construireModele — la ligne d'en-têtes dans
 * les premières lignes, les groupes par leurs fusions —, sur ces seules
 * lignes : de quoi trancher avant d'échanger deux onglets.
 */
function colonneSuivieLue_(feuille) {
  const n = Math.min(CONFIG.LIGNES_SCAN_ENTETE, feuille.getLastRow());
  const largeur = feuille.getLastColumn();
  if (n < 1 || largeur < 1) return false;
  const tete = feuille.getRange(1, 1, n, largeur).getDisplayValues();
  const i = detecterLigneEntete(tete);
  const entetes = tete[i].map(function (e) { return String(e).trim(); });
  const groupes = i > 0 ? groupesParColonne(feuille, i, entetes.length) : new Array(entetes.length).fill('');
  return trouverIndexFWD(entetes, groupes) !== -1;
}

/** Abandon : l'onglet temporaire est retiré, l'onglet visé reste ce qu'il était. */
function importSecondeBaseAbandon(jeton, nomFeuille) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const n = String(nomFeuille === undefined || nomFeuille === null ? '' : nomFeuille), m = IMPORT_MOTIF.exec(n);
  const feuille = m && m[1] === 'import' ? classeur.getSheetByName(n) : null;
  if (feuille) classeur.deleteSheet(feuille);
  return true;
}

/**
 * Après l'import d'un export GATES : le relevé de la semaine en cours, pour
 * ce contrat seulement (archiverContrat_, sous le verrou du document). Ses
 * refus — l'export est celui d'un relevé plus ancien, un historique orphelin
 * attend d'être rattaché, l'onglet n'a pas de plan — reviennent comme tels,
 * { ok: false, message } : l'import, lui, est fait. Archiver deux fois dans
 * la semaine remplace la ligne de la semaine : renvoyer l'appel ne double rien.
 */
function importArchiverReleve(jeton, idContrat, nouveau) {
  gesteImport_(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const contrat = contratPourImport(classeur, idContrat);
  /* Un contrat que cet import vient de créer : un ancien historique
     orphelin ne peut pas être le sien (messageOrphelin). */
  if (nouveau === true) contrat.nouveau = true;
  const semaine = numeroSemaineISO(new Date());
  const dite = semaineDite(semaine, semaine);
  /* Le verrou se prend ici, une fois (sousVerrou_) : pas obtenu, rien n'est
     écrit et la fenêtre le dit — l'archivage n'avance plus sans lui. */
  try {
    const d = sousVerrou_(function () { return archiverContrat_(classeur, contrat, semaine); });
    return { ok: true, semaine: semaine, dite: dite, plans: d.compte.total, valides: d.compte.termine, historique: d.historique };
  } catch (err) {
    /* L'export identique à un relevé plus ancien, juste après l'avoir
       importé : « importer l'export du jour » serait le geste qui vient
       d'échouer. Si ce fichier n'est pas l'export du jour, c'est le bon
       qu'il faut importer ; s'il l'est, le menu Archiver passe outre après
       confirmation. */
    const message = err && err.sansPlan ? 'l’onglet « ' + contrat.nom + ' » ne porte aucun plan (en-têtes seuls).'
      : err && err.ancienExport && err.voulu ? err.constat + ' ' + err.voulu + ' Sinon, ce fichier n’est pas l’export du jour : importer le bon.'
      : (err && err.message ? err.message : String(err));
    return { ok: false, semaine: semaine, dite: dite, ancienExport: !!(err && err.ancienExport), message: message };
  }
}

/**
 * La fenêtre d'import : son HTML, ses styles, et son programme avec ses
 * paramètres. Deux blocs bien séparés, numérotés dans l'ordre où l'import
 * les passe : les exports GATES, une case par contrat ; l'extract SEE, une
 * seule case pour tous les porteurs, avec le PSN de chaque contrat. En bas,
 * toujours visibles, ce qu'attend « Importer » et les boutons.
 */
function pageImportSecondeBase(parametres) {
  const json = JSON.stringify(parametres).replace(/</g, '\\u003c');
  const ech = function (t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  const base = parametres.base ? ech(parametres.base) : '';
  const tri = [].concat(parametres.colonnePsn ? ['le PSN de chaque contrat'] : [])
    .concat(parametres.filtres.map(function (f) { return ech(f.colonne) + ' ' + f.valeurs.map(ech).join(' ou '); }));
  return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><base target="_top"><style>' +
    ':root{--papier:#f4f2ed;--surface:#fff;--case:#faf9f5;--survol:#eeebe2;--encre:#191915;--encre-2:#57564e;--encre-3:#77756c;--filet:#e2dfd6;' +
    '--filet-2:#cfcbc0;--fait:#2f6b4f;--fait-fond:#eef5f0;--alerte:#b5462e;--alerte-fond:#fbefeb;--attention:#80560a;--attention-fond:#fbf3e2;' +
    '--see:#3f51a3;--teinte:#191915;--ombre:0 1px 2px rgba(25,25,21,.06)}' +
    '@media (prefers-color-scheme:dark){:root{--papier:#1b1b18;--surface:#23231f;--case:#292924;--survol:#31312b;--encre:#efede6;--encre-2:#c4c1b6;' +
    '--encre-3:#a19e93;--filet:#3a3933;--filet-2:#4d4c45;--fait:#6fbf94;--fait-fond:#1f2c25;--alerte:#e8907a;--alerte-fond:#36221e;' +
    '--attention:#e0b25a;--attention-fond:#352b17;--see:#9aa8ec;--teinte:#efede6;--ombre:none}}' +
    'html,body{margin:0;background:var(--papier);color:var(--encre);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}' +
    'body{padding:6px 18px 0}p{margin:0 0 10px}b{font-weight:600}' +
    'input[type=text]{font:inherit;font-size:13px;padding:3px 7px;border:1px solid var(--filet-2);border-radius:6px;background:var(--surface);color:var(--encre)}' +
    'input[type=text].refus{border-color:var(--alerte)}input:disabled{opacity:.6}' +
    'button{font:inherit;font-size:13px;padding:5px 12px;border-radius:7px;border:1px solid var(--filet-2);background:var(--surface);color:var(--encre);cursor:pointer}' +
    'button.principal{background:var(--teinte);border-color:var(--teinte);color:var(--papier);font-size:14px;padding:6px 18px}button:disabled{opacity:.45;cursor:default}' +
    'button:focus-visible,input:focus-visible{outline:2px solid var(--encre);outline-offset:2px}' +
    '.intro{color:var(--encre-2);font-size:13.5px;margin:2px 0 12px}' +
    '.bloc{background:var(--surface);border:1px solid var(--filet);border-radius:12px;box-shadow:var(--ombre);padding:12px 14px 10px;margin:0 0 14px}' +
    '.bloc h2{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;margin:0 0 10px;font-size:15.5px;font-weight:650;letter-spacing:.01em}' +
    '.bloc h2 .num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;flex:none;' +
    'background:var(--teinte);color:var(--papier);font-size:12.5px;font-weight:700}' +
    '.bloc h2 .aide{font-size:12.5px;font-weight:400;color:var(--encre-3);letter-spacing:0}' +
    '.cases{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}' +
    '.case{border:1.5px dashed var(--filet-2);border-radius:10px;background:var(--case);padding:9px 12px;transition:background .15s,border-color .15s}' +
    '.case.survol{border-color:var(--encre-2);background:var(--survol)}' +
    '.case:not([data-etat=vide]){border-style:solid;border-left-width:4px;border-left-color:var(--fait)}' +
    '.case.see:not([data-etat=vide]){border-left-color:var(--see)}' +
    '.case[data-etat=erreur],.case[data-etat=echec]{border-left-color:var(--alerte)!important;background:var(--alerte-fond)}' +
    '.case[data-etat=fait]{background:var(--fait-fond)}' +
    '.tete{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-height:30px}' +
    '.etiquette{flex:none;font-size:12px;font-weight:700;letter-spacing:.04em;padding:1px 8px;border-radius:5px;color:var(--fait);border:1.5px solid currentColor;white-space:nowrap}' +
    '.see .etiquette{color:var(--see)}' +
    '.fichier-nom{flex:1;font-weight:600;word-break:break-all}.fichier-nom:empty{display:none}' +
    '.date,.taille{color:var(--encre-3);font-size:12px;white-space:nowrap}.date:empty,.taille:empty{display:none}' +
    '.invite{flex:1;color:var(--encre-3);font-size:13px;text-align:right}' +
    '.tete .retirer,.tete .annuler{padding:2px 9px;font-size:12px;color:var(--encre-2)}' +
    '.case.nouvelle .nom{width:15em}' +
    '.verif-nom{font-size:12.5px;color:var(--encre-3);margin-top:3px}.verif-nom.refus{color:var(--alerte)}' +
    '.lu{font-size:13px;color:var(--encre-2);margin-top:3px}.lu.erreur{color:var(--alerte)}' +
    '.barre{height:4px;border-radius:2px;background:var(--filet);overflow:hidden;margin:6px 0 2px}' +
    '.barre div{height:100%;width:0;background:var(--fait);transition:width .2s}.see .barre div{background:var(--see)}' +
    '.cible{font-size:13px;color:var(--encre-2);margin-top:3px}' +
    '.note{font-size:13px;color:var(--attention);background:var(--attention-fond);border-radius:6px;padding:4px 8px;margin-top:6px}' +
    '.note::before{content:"⚠ "}' +
    '.manque{margin-top:6px;font-size:13px;color:var(--alerte)}.sans-tri{display:flex;gap:7px;align-items:flex-start;color:var(--encre);margin-top:4px}' +
    '.tri-aide{font-size:12.5px;color:var(--encre-3);margin-top:8px}.tri-aide:empty{display:none}' +
    '.porteurs{list-style:none;margin:6px 0 0;padding:0;border-top:1px solid var(--filet)}' +
    '.porteur{display:flex;align-items:center;gap:6px 10px;flex-wrap:wrap;padding:6px 2px;border-bottom:1px solid var(--filet);font-size:13px}' +
    '.porteur:last-child{border-bottom:0}.porteur .contrat{font-weight:650;min-width:58px}' +
    '.porteur .psn{display:inline-flex;align-items:center;gap:5px;color:var(--encre-3);font-size:12px;font-weight:600;letter-spacing:.04em}' +
    '.porteur .psn input{width:8.5em;letter-spacing:0;font-weight:400}' +
    '.porteur .enr{font-size:12px;color:var(--encre-3)}.porteur .enr.refus{color:var(--alerte)}.porteur .enr:empty{display:none}' +
    '.porteur .part{flex:1;min-width:200px;color:var(--encre-2)}.porteur .part.rien{color:var(--encre-3)}.porteur .part.attention{color:var(--attention)}' +
    '.resultat{font-size:13px;margin-top:6px}.resultat > div{margin:0 0 3px}.resultat.ok,.resultat .ok{color:var(--fait)}' +
    '.resultat.erreur,.resultat .erreur{color:var(--alerte)}.resultat.avertissement,.resultat .avertissement{color:var(--attention)}.resultat .neutre{color:var(--encre-2)}' +
    '.ajouter{margin-top:8px;border-style:dashed;color:var(--encre-2);background:transparent}' +
    '.option{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--encre-2);margin:10px 0 2px}' +
    '.etat{font-size:13.5px;margin:0 0 6px}.etat:empty{display:none}.etat > div{margin:0 0 4px}.etat.ok,.etat .ok{color:var(--fait)}' +
    '.etat.erreur,.etat .erreur{color:var(--alerte)}.etat .avertissement{color:var(--attention)}.etat .neutre{color:var(--encre-2)}.etat .suite{color:var(--encre);margin-top:6px}' +
    '.pied{position:sticky;bottom:0;background:var(--papier);border-top:1px solid var(--filet);padding:8px 0 12px;margin-top:4px}' +
    '.pied .ligne{display:flex;align-items:center;gap:12px}.blocage{flex:1;font-size:13px;color:var(--encre-2)}' +
    '.progres{font-size:13px;color:var(--encre-2)}.progres:empty{display:none}.consigne{font-size:13px;color:var(--encre);font-weight:600;margin:2px 0 0}' +
    '.boutons{display:flex;gap:8px;flex:none}[hidden]{display:none!important}' +
    '</style></head><body>' +
    '<p class="intro">Chaque export dans <b>sa case</b>, tel que téléchargé (.xlsx, .xls, .csv ou page web), <b>sans l’ouvrir dans Excel</b>&nbsp;: ' +
    'il est lu ici, sur ce poste, et va dans l’onglet de sa case — rien n’est deviné.</p>' +
    '<section class="bloc" id="bloc-gates" aria-labelledby="titre-gates"><h2 id="titre-gates"><span class="num">1</span>Exports GATES' +
    '<span class="aide">un par contrat : il remplace l’onglet du contrat, tel quel</span></h2>' +
    '<ul class="cases" id="cases-gates"></ul>' +
    '<button type="button" class="ajouter" id="ajouter">+ Ajouter un contrat…</button>' +
    '<label class="option" id="option-archiver" hidden><input type="checkbox" id="archiver" checked> <span>Archiver le relevé de la semaine ' +
    ech(parametres.semaine) + ' pour les contrats importés</span></label></section>' +
    (base ? '<section class="bloc" id="bloc-see" aria-labelledby="titre-see"><h2 id="titre-see"><span class="num">2</span>Export ' + base +
      '<span class="aide">tous les porteurs, un seul fichier' + (tri.length ? ' — trié ici : ' + tri.join(' · ') : '') + '</span></h2>' +
      '<div id="case-see"></div>' +
      '<label class="option" id="option-toutes"><input type="checkbox" id="toutes"> <span>Garder aussi les autres colonnes — plus lourd, seulement pour regarder ' +
      'tout l’extract dans le tableau ' + base + ' de la page ; sinon, seules ' + parametres.cles.map(ech).join(', ') + ' vont au classeur.</span></label></section>' : '') +
    '<div class="etat" id="etat" role="status" aria-live="polite"></div>' +
    '<div class="pied"><div class="progres" id="progres" aria-live="polite"></div>' +
    '<p class="consigne" id="consigne" hidden>Ne pas fermer cette fenêtre avant la fin.</p>' +
    '<div class="ligne"><span class="blocage" id="blocage" aria-live="polite"></span>' +
    '<div class="boutons"><button type="button" id="fermer">Fermer</button>' +
    '<button type="button" class="principal" id="importer" disabled>Importer</button></div></div></div>' +
    '<script>(' + scriptImportSecondeBase_.toString() + ')(' + json + ');</script>' +
    '</body></html>';
}

/**
 * Le programme de la fenêtre d'import. Il ne tourne jamais dans Apps
 * Script : la fonction n'est là que pour son texte, que la fenêtre reçoit
 * (Function.prototype.toString) avec ses paramètres. Écrit en ES5, pour le
 * Chrome ou l'Edge du poste ; il lui faut DecompressionStream (2022 et
 * après). Un .xlsx est un zip : on en lit le répertoire à la fin du fichier,
 * puis on décompresse au fil de l'eau les seules parties utiles — la liste
 * des onglets, les styles, les chaînes partagées, et l'onglet qui porte
 * l'en-tête — sans jamais tenir le fichier entier en mémoire. Un vrai .xls
 * (Excel 97-2003, ou Excel 5 / 95) est un conteneur OLE : lu en entier, son
 * flux « Workbook » ou « Book » recomposé, puis parcouru enregistrement par
 * enregistrement. Les « Excel » qui n'en sont pas (une page web, une page
 * web archivée .mht, un XML 2003 nommés .xls) et les CSV se lisent aussi.
 * Chaque fichier est posé dans sa case — « GATES HDK », « SEE » — et lu
 * tout de suite, un à la fois ; « Importer » envoie ensuite les exports
 * GATES, puis la base SEE de chaque contrat.
 */
function scriptImportSecondeBase_(P) {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var N_CLES = P.cles.map(norm), N_ESS = P.essentielles.map(norm);

  // ------------------------------------------------------------ petits outils
  function norm(t) {
    return String(t === null || t === undefined ? '' : t).toLowerCase().normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim();
  }
  function nb(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f'); }
  function ech(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function erreur(message) { var e = new Error(message); e.pourLecteur = true; return e; }
  function dire(html, classe) { var z = $('etat'); z.className = 'etat' + (classe ? ' ' + classe : ''); z.innerHTML = html; }
  /* L'avancement de ce qui se fait — la lecture d'un fichier, puis son envoi
     au classeur —, dit dans la ligne de ce fichier. */
  var suivi = null;
  function progres(part, texte) { if (suivi) suivi(part, texte); }
  function souffle() { return new Promise(function (ok) { setTimeout(ok, 0); }); }
  /* Une valeur gardée est recopiée : une sous-chaîne d'un morceau de XML le
     tiendrait tout entier en mémoire, et un gros fichier ferait tomber
     l'onglet du navigateur. */
  function plat(v) { return v.length > 12 ? (' ' + v).slice(1) : v; }
  function taille(octets) {
    return octets < 1048576 ? Math.max(1, Math.round(octets / 1024)) + ' Ko' : (octets / 1048576).toFixed(1).replace('.', ',') + ' Mo';
  }
  function sansExtension(nom) { return String(nom).replace(/\.[^.]*$/, ''); }
  /* La date d'un fichier, « 3 oct. 14:20 » (l'année si ce n'est pas celle-ci) :
     deux exports du même contrat, « Export GATES.xlsx » et « Export GATES
     (1).xlsx », ne se distinguent que par elle. */
  var MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  function dateFichier(f) {
    if (!f || !f.lastModified) return '';
    var d = new Date(f.lastModified), deuxC = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getDate() + ' ' + MOIS[d.getMonth()] + (d.getFullYear() !== new Date().getFullYear() ? ' ' + d.getFullYear() : '') +
      ' ' + deuxC(d.getHours()) + ':' + deuxC(d.getMinutes());
  }
  /* Un nom d'onglet réduit pour être comparé, comme nomCompact côté serveur. */
  function compact(t) { return norm(t).replace(/[\s_\-\u2013\u2014.:\/]+/g, ' ').trim(); }
  var ABIME = 'Le fichier est abîmé (il ne se décompresse pas en entier) : le retélécharger depuis GATES ou SEE.';
  // ------------------------------------------------------------ lecture du fichier
  function lireOctets(f, debut, fin) {
    return new Promise(function (ok, ko) {
      var r = new FileReader();
      r.onload = function () { ok(new Uint8Array(r.result)); };
      r.onerror = function () { ko(erreur('Le fichier n\u2019a pas pu être lu (est-il encore ouvert ailleurs, ou déplacé ?).')); };
      r.readAsArrayBuffer(f.slice(debut, fin));
    });
  }
  function u16(b, i) { return b[i] | (b[i + 1] << 8); }
  function u32(b, i) { return (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16)) + b[i + 3] * 16777216; }
  function u64(b, i) { return u32(b, i) + u32(b, i + 4) * 4294967296; }

  /* Le répertoire du zip : chaque partie, sa méthode, ses tailles, sa place. */
  function lireZip(f) {
    var lu = Math.min(f.size, 65536 + 22);
    return lireOctets(f, f.size - lu, f.size).then(function (fin) {
      var p = -1, i;
      for (i = fin.length - 22; i >= 0; i--) {
        if (fin[i] === 0x50 && fin[i + 1] === 0x4b && fin[i + 2] === 5 && fin[i + 3] === 6) { p = i; break; }
      }
      if (p < 0) throw erreur('Ce fichier n\u2019est pas un classeur .xlsx lisible : abîmé, ou pas fini de télécharger ? Le retélécharger.');
      var nbEntrees = u16(fin, p + 10), tailleCD = u32(fin, p + 12), debutCD = u32(fin, p + 16);
      var avant = Promise.resolve();
      if (debutCD === 0xFFFFFFFF || tailleCD === 0xFFFFFFFF || nbEntrees === 0xFFFF) {
        var l = p - 20;
        if (l >= 0 && u32(fin, l) === 0x07064b50) {
          var o = u64(fin, l + 8);
          avant = lireOctets(f, o, o + 56).then(function (z) {
            if (u32(z, 0) !== 0x06064b50) throw erreur(ABIME);
            tailleCD = u64(z, 40); debutCD = u64(z, 48);
          });
        }
      }
      return avant.then(function () { return lireOctets(f, debutCD, debutCD + tailleCD); }).then(function (cd) {
        var entrees = {}, j = 0, dec = new TextDecoder('utf-8');
        while (j + 46 <= cd.length && u32(cd, j) === 0x02014b50) {
          var methode = u16(cd, j + 10), tc = u32(cd, j + 20), tu = u32(cd, j + 24);
          var ln = u16(cd, j + 28), lx = u16(cd, j + 30), lc = u16(cd, j + 32), off = u32(cd, j + 42);
          var nom = dec.decode(cd.subarray(j + 46, j + 46 + ln));
          var x = j + 46 + ln, xf = x + lx;
          while (x + 4 <= xf) {
            var id = u16(cd, x), lg = u16(cd, x + 2), q = x + 4;
            if (id === 1) {
              if (tu === 0xFFFFFFFF) { tu = u64(cd, q); q += 8; }
              if (tc === 0xFFFFFFFF) { tc = u64(cd, q); q += 8; }
              if (off === 0xFFFFFFFF) { off = u64(cd, q); q += 8; }
            }
            x += 4 + lg;
          }
          entrees[nom] = { nom: nom, methode: methode, tc: tc, tu: tu, off: off };
          j += 46 + ln + lx + lc;
        }
        return entrees;
      });
    });
  }
  /* Une partie du zip, décompressée au fil de la lecture. */
  function fluxPartie(f, e) {
    return lireOctets(f, e.off, e.off + 30).then(function (h) {
      if (u32(h, 0) !== 0x04034b50) throw erreur(ABIME);
      var debut = e.off + 30 + u16(h, 26) + u16(h, 28);
      var brut = f.slice(debut, debut + e.tc).stream();
      if (e.methode === 0) return brut;
      if (e.methode === 8) return brut.pipeThrough(new DecompressionStream('deflate-raw'));
      throw erreur('Compression inconnue (' + e.methode + ') dans « ' + e.nom + ' ».');
    });
  }
  /* Lit un flux d'octets comme du texte, morceau par morceau. surTexte(texte,
     fini) rend false pour arrêter là. surAvance(octets lus) dit l'avancée ;
     attendu, la taille annoncée par le zip : lu jusqu'au bout, un compte qui
     n'y est pas dit un fichier abîmé. Avec strict, un octet qui n'est pas de
     l'UTF-8 lève une erreur (marquée pasUtf8). */
  function lireFlux(flux, encodage, surTexte, surAvance, attendu, strict) {
    var lecteur = flux.getReader(), dec = new TextDecoder(encodage, strict ? { fatal: true } : undefined), lus = 0, repos = Date.now();
    function decoder(octets, fin) {
      try { return fin ? dec.decode() : dec.decode(octets, { stream: true }); }
      catch (e) { var x = new Error('pas utf-8'); x.pasUtf8 = true; throw x; }
    }
    function suite() {
      return lecteur.read().then(function (r) {
        if (r.done) {
          if (typeof attendu === 'number' && attendu > 0 && attendu !== 0xFFFFFFFF && lus !== attendu) throw erreur(ABIME);
          surTexte(decoder(null, true), true);
          return;
        }
        lus += r.value.length;
        if (surTexte(decoder(r.value, false), false) === false) { lecteur.cancel().catch(function () {}); return; }
        if (surAvance) surAvance(lus);
        if (Date.now() - repos > 120) { repos = Date.now(); return souffle().then(suite); }
        return suite();
      }, function (e) {
        if (e && e.pourLecteur) throw e;
        throw erreur(ABIME);
      });
    }
    return suite();
  }
  function lirePartie(f, e, surTexte, surAvance) {
    return fluxPartie(f, e).then(function (flux) { return lireFlux(flux, 'utf-8', surTexte, surAvance, e.tu); });
  }
  function partieEntiere(f, e) {
    var t = [];
    return lirePartie(f, e, function (x) { t.push(x); }).then(function () { return t.join(''); });
  }

  // ------------------------------------------------------------ XML
  var ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: '\'', nbsp: '\u00a0' };
  function decoderXml(s) {
    /* Le texte d'une section CDATA est pris tel quel. */
    if (s.indexOf('<![CDATA[') !== -1) {
      return s.split(/<!\[CDATA\[([\s\S]*?)\]\]>/).map(function (p, i) { return i % 2 ? p : decoderXml(p); }).join('');
    }
    if (s.indexOf('&') !== -1) {
      s = s.replace(/&(?:(amp|lt|gt|quot|apos|nbsp)|#(\d+)|#x([0-9a-fA-F]+));/g, function (m, n, d, h) {
        return n ? ENT[n] : String.fromCodePoint(d ? parseInt(d, 10) : parseInt(h, 16));
      });
    }
    return s;
  }
  /* Excel écrit un caractère de contrôle « _x000D_ » dans une chaîne. */
  function decoderChaine(s) {
    s = decoderXml(s);
    return s.indexOf('_x') === -1 ? s : s.replace(/_x([0-9A-Fa-f]{4})_/g, function (m, h) { return String.fromCharCode(parseInt(h, 16)); });
  }
  /* La valeur d'un attribut, entre guillemets — ou sans, comme Excel écrit
     les nombres de ses pages web (colspan=16). */
  function attribut(s, nom) {
    var m = new RegExp('\\s(?:[\\w.-]+:)?' + nom + '\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\'|([^\\s"\'>]+))', 'i').exec(' ' + s);
    return m ? decoderXml(m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2] : m[3]) : null;
  }
  /* Les éléments complets <nom …>…</nom> d'un texte qui arrive par morceaux ;
     un préfixe d'espace de noms (« x:row ») est toléré. Ce qui ne se termine
     pas encore attend le morceau suivant — mais ce qui suit le dernier
     élément (des liens, des fusions après les lignes) n'est pas gardé : le
     relire à chaque morceau rendait la lecture quadratique. */
  function decoupeur(nom, surElement, sansCasse) {
    var drapeaux = sansCasse ? 'gi' : 'g';
    var re = new RegExp('<(?:[\\w.-]+:)?' + nom + '(?=[\\s/>])([^>]*?)(?:\\/>|>([\\s\\S]*?)<\\/(?:[\\w.-]+:)?' + nom + '\\s*>)', drapeaux);
    var ouvre = new RegExp('<(?:[\\w.-]+:)?' + nom + '(?=[\\s/>])', drapeaux);
    var reste = '';
    return function (texte, fini) {
      var tampon = reste + texte, fin = 0, m;
      re.lastIndex = 0;
      while ((m = re.exec(tampon))) {
        fin = re.lastIndex;
        if (surElement(m[1], m[2] === undefined ? '' : m[2]) === false) { reste = ''; return false; }
      }
      reste = tampon.slice(fin);
      if (reste.length > 262144) {
        var dernier = -1, o;
        ouvre.lastIndex = 0;
        while ((o = ouvre.exec(reste))) dernier = o.index;
        reste = dernier >= 0 ? reste.slice(dernier) : reste.slice(-512);
      }
      return true;
    };
  }
  var RE_RPH = /<(?:[\w.-]+:)?rPh(?=[\s>])[\s\S]*?<\/(?:[\w.-]+:)?rPh\s*>/g;
  var RE_T = /<(?:[\w.-]+:)?t(?=[\s>\/])[^>]*?(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?t\s*>)/g;
  /* Le texte d'une chaîne riche (<r><t>…</t></r>…), sans sa lecture phonétique. */
  function texteRiche(x) {
    if (x.indexOf('rPh') !== -1) x = x.replace(RE_RPH, '');
    var s = '', m;
    RE_T.lastIndex = 0;
    while ((m = RE_T.exec(x))) if (m[1]) s += m[1];
    return plat(decoderChaine(s));
  }

  // ------------------------------------------------------------ nombres et dates
  var FORMATS_DATE = { 14: 1, 15: 1, 16: 1, 17: 1, 18: 2, 19: 2, 20: 2, 21: 2, 22: 3, 45: 2, 46: 2, 47: 2 };
  var FORMATS_INTEGRES = { 1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 9: '0%', 10: '0.00%', 11: '0.00E+00',
    37: '#,##0', 38: '#,##0', 39: '#,##0.00', 40: '#,##0.00', 48: '##0.0E+0' };
  function lireStyles(texte) {
    var formats = {}, xfs = [], m;
    var re = /<(?:[\w.-]+:)?numFmt\s([^>]*?)\/?>/g;
    while ((m = re.exec(texte))) {
      var id = attribut(m[1], 'numFmtId');
      if (id !== null) formats[+id] = attribut(m[1], 'formatCode') || '';
    }
    var bloc = /<(?:[\w.-]+:)?cellXfs\b[\s\S]*?<\/(?:[\w.-]+:)?cellXfs\s*>/.exec(texte);
    if (bloc) {
      var rx = /<(?:[\w.-]+:)?xf(?=[\s>\/])([^>]*?)\/?>/g;
      while ((m = rx.exec(bloc[0]))) { var n = attribut(m[1], 'numFmtId'); xfs.push(n === null ? 0 : +n); }
    }
    return { formats: formats, xfs: xfs };
  }
  /* Ce qu'un format fait d'un nombre, pour l'écrire comme Excel l'affiche :
     date (1 jour, 2 heure, 3 les deux), zéros de tête (« 000 »), texte, ou
     nombre — décimales, séparateur des milliers, pourcentage, notation
     scientifique, et le texte autour (« € »). */
  function formeDuFormat(styles, s) {
    var id = styles && styles.xfs[s] !== undefined ? styles.xfs[s] : 0;
    if (FORMATS_DATE[id]) return { type: 'date', parties: FORMATS_DATE[id] };
    if (id === 49) return { type: 'texte' };
    var code = styles && styles.formats[id] !== undefined ? styles.formats[id] : (FORMATS_INTEGRES[id] || '');
    if (!code || /^general$/i.test(code)) return { type: 'general' };
    var section = code.split(';')[0];
    var nu = section.replace(/"[^"]*"/g, '').replace(/\[\$([^\]-]*)[^\]]*\]/g, '').replace(/\[[^\]]*\]/g, '')
      .replace(/\\./g, '').replace(/[_*]./g, '');
    if (/^0+$/.test(nu)) return { type: 'zeros', largeur: nu.length };
    if (/^@$/.test(nu.trim())) return { type: 'texte' };
    if (/^general$/i.test(nu.trim())) return { type: 'general' };
    var jour = /[dy]/i.test(nu) || /m/i.test(nu) && !/[hs]/i.test(nu), heure = /[hs]/i.test(nu);
    if (jour || heure) return { type: 'date', parties: (jour ? 1 : 0) | (heure ? 2 : 0) };
    if (!/[0#?]/.test(nu)) return { type: 'general' };
    /* Le texte autour des chiffres : entre guillemets, échappé, ou le
       symbole d'une devise [$€-40C]. */
    var litteral = section.replace(/\[\$([^\]-]*)[^\]]*\]/g, '"$1"').replace(/\[[^\]]*\]/g, '').replace(/\\(.)/g, '"$1"').replace(/[_*]./g, '');
    var premier = litteral.search(/[0#?]/), dernier = Math.max(litteral.lastIndexOf('0'), litteral.lastIndexOf('#'), litteral.lastIndexOf('?'));
    var lit = function (t) { var r = '', m, re = /"([^"]*)"/g; while ((m = re.exec(t))) r += m[1]; return r; };
    var expo = /E[+-]/i.test(nu);
    var partie = (/\.([0#?]+)/.exec(nu.split(/E/i)[0]) || [null, ''])[1];
    return { type: 'nombre', min: (partie.match(/0/g) || []).length, max: partie.length, mille: /[0#?],[0#?]/.test(nu),
             pourcent: nu.indexOf('%') !== -1, expo: expo,
             avant: lit(litteral.slice(0, Math.max(0, premier))), apres: lit(litteral.slice(dernier + 1)).replace(/%/g, '') };
  }
  function deux(n) { return (n < 10 ? '0' : '') + n; }
  function exposant(v, dec) {
    var t = v.toExponential(dec).split('e'), e = parseInt(t[1], 10);
    return t[0].replace('.', ',') + 'E' + (e < 0 ? '-' : '+') + deux(Math.abs(e));
  }
  function milliers(t) { return t.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f'); }
  function texteNombre(brut, forme, en1904) {
    var v = Number(brut);
    if (brut === '' || isNaN(v)) return brut;
    if (forme.type === 'texte') return brut;
    if (forme.type === 'zeros') {
      var z = String(Math.round(Math.abs(v)));
      while (z.length < forme.largeur) z = '0' + z;
      return (v < 0 ? '-' : '') + z;
    }
    if (forme.type === 'date') {
      var d = new Date(Math.round(((en1904 ? v + 1462 : v) - 25569) * 86400000));
      if (isNaN(d.getTime())) return brut;
      var jour = deux(d.getUTCDate()) + '/' + deux(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear();
      var heure = deux(d.getUTCHours()) + ':' + deux(d.getUTCMinutes()) + (d.getUTCSeconds() ? ':' + deux(d.getUTCSeconds()) : '');
      return forme.parties === 2 ? heure : forme.parties === 3 ? jour + ' ' + heure : jour;
    }
    if (forme.type === 'nombre') {
      var x = forme.pourcent ? v * 100 : v, signe = x < 0 ? '-' : '', a = Math.abs(x), corps;
      if (forme.expo) corps = exposant(a, forme.max);
      else {
        var t = a.toFixed(forme.max).split('.'), entier = t[0], frac = t[1] || '';
        while (frac.length > forme.min && frac.charAt(frac.length - 1) === '0') frac = frac.slice(0, -1);
        corps = (forme.mille ? milliers(entier) : entier) + (frac ? ',' + frac : '');
      }
      return signe + forme.avant + corps + (forme.pourcent ? '\u202f%' : '') + forme.apres;
    }
    /* Standard : l'entier tel quel ; quinze chiffres significatifs au plus,
       la virgule décimale, et l'exposant à la manière d'Excel. */
    if (Math.floor(v) === v && Math.abs(v) < 1e15) return String(v);
    var p = Number(v.toPrecision(15));
    if (Math.abs(p) >= 1e15 || String(p).indexOf('e') !== -1) return exposant(p, 5).replace(/,?0+E/, 'E');
    return String(p).replace('.', ',');
  }

  // ------------------------------------------------------------ reconnaître l'export à sa ligne d'en-têtes
  /* Les deux règles du serveur, reçues avec les paramètres — rien n'est
     recopié ici : un export SEE porte, sur une même ligne, toutes les
     colonnes de la référence (P.cles) ; un export GATES, la ligne
     d'en-têtes d'un export (ligneDEnteteDExport dans Code.gs) — au moins
     P.minIntitules intitulés, dont P.minMotsCles de P.motsCles, chacun seul
     dans sa cellule. `ns` : les cellules de la ligne, normalisées. */
  function enteteSee(ns) {
    if (!N_CLES.length) return false;
    for (var i = 0; i < N_CLES.length; i++) if (ns.indexOf(N_CLES[i]) === -1) return false;
    return true;
  }
  function enteteGates(ns) {
    var remplies = ns.filter(Boolean);
    if (remplies.length < P.minIntitules) return false;
    return P.motsCles.filter(function (m) { return remplies.indexOf(m) !== -1; }).length >= P.minMotsCles;
  }
  /* La colonne de référence d'un en-tête, choisie comme trouverIndexReference
     la choisit : le premier motif reconnu, dans l'ordre de P.motifsReference. */
  function indexReference(entete) {
    var ns = entete.map(norm);
    for (var m = 0; m < P.motifsReference.length; m++) {
      for (var i = 0; i < ns.length; i++) if (ns[i].indexOf(P.motifsReference[m]) !== -1) return i;
    }
    return 0;
  }
  /* Au-delà des P.lignesScan premières lignes, on regarde encore celles-ci,
     seulement pour dire « l'en-tête est trop bas » au lieu de « pas d'en-tête ». */
  var LIGNES_SONDE = 30;

  /* Le tri de l'extract SEE, reçu du serveur (CONFIG.RAPPROCHEMENT) : la
     colonne des machines (P.colonnePsn) et les colonnes à valeurs permises
     (P.filtres, DIAGRAM TYPE : WD). Intitulés et valeurs se comparent sans
     casse, accents ni espaces — comme cleTri côté serveur. */
  function cleTri(t) { return norm(t).replace(/\s+/g, ''); }
  var TRI_PSN = P.colonnePsn ? cleTri(P.colonnePsn) : '';
  var TRI_FILTRES = P.filtres.map(function (f) {
    var permises = {};
    f.valeurs.forEach(function (v) { permises[cleTri(v)] = true; });
    return { colonne: f.colonne, cle: cleTri(f.colonne), valeurs: f.valeurs, permises: permises };
  });
  /* Les PSN d'une cellule, « 4520,4530; 4540 » : coupés aux virgules,
     points-virgules et espaces, comparés en entier (4530 n'est ni 14530 ni
     45301) — comme jetonsPsn côté serveur. */
  function jetonsPsn(t) {
    var out = [];
    String(t === null || t === undefined ? '' : t).split(/[\s,;]+/).forEach(function (j) { var k = norm(j); if (k) out.push(k); });
    return out;
  }

  /* Reçoit les lignes d'un onglet une à une (numéro 1-based, valeurs par
     colonne) et reconnaît l'export à sa ligne d'en-têtes, cherchée comme
     Code.gs la cherche, dans les P.lignesScan premières lignes :
       – SEE : la première colonne d'un intitulé en double compte ; on garde
         les colonnes voulues des lignes suivantes, les lignes vides laissées
         — et seulement les lignes que laissent passer les FILTRES (DIAGRAM
         TYPE : WD), avec leur cellule de PSN : l'extract de tous les
         porteurs peut faire des centaines de milliers de lignes, seules
         celles-là restent en mémoire, et le PSN de chaque contrat les trie
         ensuite sans relire le fichier ;
       – GATES : on garde tout, tel quel — les lignes au-dessus de l'en-tête
         (titre, groupes), l'en-tête, les données —, chaque ligne à son
         numéro, chaque colonne à sa place : c'est ce qu'un collage poserait.
     Une ligne qui répond aux deux règles est SEE : ses intitulés propres
     sont plus sûrs que deux mots courants. Les cellules fusionnées
     (c.fusion) sont notées au passage ; on ne garde, pour GATES, que celles
     qui commencent sur l'en-tête ou au-dessus. `o` : { toutes (garder
     toutes les colonnes de SEE), attendu ('gates' ou 'see' : la case où le
     fichier est posé — l'autre sorte arrête la lecture dès l'en-tête) }. */
  function collecteur(o) {
    var toutes = !!(o && o.toutes), attendu = o && o.attendu ? o.attendu : null;
    var c = { sorte: null, ligneEntete: 0, entete: null, colonnes: null, voulues: null, cles: null, lignes: [], fusions: [],
              avant: [], largeur: 0, iRef: -1, formulesVides: 0, formulesAilleurs: 0, trop: false, tropBas: null, autre: false,
              tri: null, lues: 0, ecartees: 0, psn: [], psnCellules: [], psnCompte: [], rangPsn: {},
              meilleur: { portes: 0, ligne: 0, noms: [], manquent: P.cles.slice() } };
    function poserSee(num, valeurs, ns) {
      var prises = {}, cles = {}, voulues = {}, j;
      N_CLES.forEach(function (k) { prises[ns.indexOf(k)] = true; cles[ns.indexOf(k)] = true; });
      N_ESS.forEach(function (k) { var x = ns.indexOf(k); if (x !== -1) prises[x] = true; });
      if (toutes) ns.forEach(function (k, x) { if (k) prises[x] = true; });
      /* Les colonnes du tri, cherchées sur la même ligne (la première d'un
         intitulé en double) : lues, même quand elles ne partent pas. */
      var cleCol = valeurs.map(function (v) { return cleTri(v); });
      var jPsn = TRI_PSN ? cleCol.indexOf(TRI_PSN) : -1, filtres = [], manquent = [];
      TRI_FILTRES.forEach(function (f) {
        var x = cleCol.indexOf(f.cle);
        if (x === -1) manquent.push(f.colonne);
        else filtres.push({ j: x, colonne: f.colonne, valeurs: f.valeurs, permises: f.permises });
      });
      c.tri = { jPsn: jPsn, filtres: filtres, manquePsn: !!TRI_PSN && jPsn === -1, manquent: manquent, triees: {} };
      for (j in prises) if (Object.prototype.hasOwnProperty.call(prises, j)) voulues[j] = true;
      if (jPsn !== -1) { voulues[jPsn] = true; c.tri.triees[jPsn] = true; }
      filtres.forEach(function (f) { voulues[f.j] = true; c.tri.triees[f.j] = true; });
      c.sorte = 'see';
      c.ligneEntete = num;
      c.colonnes = Object.keys(prises).map(Number).sort(function (a, b) { return a - b; });
      c.voulues = voulues; c.cles = cles;
      c.entete = c.colonnes.map(function (x) { return plat(String(valeurs[x] === undefined ? '' : valeurs[x]).trim()); });
    }
    function ligneSee(valeurs, sansValeur) {
      var t = c.tri, k, v;
      var formules = sansValeur ? sansValeur.filter(function (x) { return c.voulues[x]; }) : [];
      var vide = !formules.length;
      for (k in c.voulues) {
        if (!vide) break;
        if (!Object.prototype.hasOwnProperty.call(c.voulues, k)) continue;
        v = valeurs[k];
        if (v !== undefined && v !== null && String(v).trim() !== '') vide = false;
      }
      if (vide) return true;
      c.lues++;
      /* Une formule sans valeur calculée dans une colonne du tri fausserait
         le tri lui-même : comptée sur toutes les lignes ; dans NAME, SOL.,
         Cust.V, seulement sur les lignes gardées. Une ligne ne compte qu'une
         fois. */
      var dansTri = formules.some(function (x) { return t.triees[x]; });
      for (var i = 0; i < t.filtres.length; i++) {
        if (!t.filtres[i].permises[cleTri(valeurs[t.filtres[i].j])]) {
          if (dansTri) c.formulesVides++;
          c.ecartees++;
          return true;
        }
      }
      if (dansTri || formules.some(function (x) { return c.cles[x]; })) c.formulesVides++;
      var l = c.colonnes.map(function (x) { var w = valeurs[x]; return w === undefined || w === null ? '' : plat(String(w)); });
      if (!l.some(function (w) { return w.trim() !== ''; })) return true;
      c.lignes.push(l);
      if (t.jPsn !== -1) {
        /* La cellule de PSN, gardée une fois pour toutes les lignes qui la
           partagent : un extract en répète peu de différentes. */
        var p = valeurs[t.jPsn] === undefined || valeurs[t.jPsn] === null ? '' : String(valeurs[t.jPsn]);
        var r = c.rangPsn['\u0001' + p];
        if (r === undefined) { r = c.rangPsn['\u0001' + p] = c.psnCellules.length; c.psnCellules.push(plat(p)); c.psnCompte.push(0); }
        c.psnCompte[r]++;
        c.psn.push(r);
      }
      if (toutes && (c.lignes.length + 1) * c.entete.length > P.maxCellulesToutes) { c.trop = true; return false; }
      return true;
    }
    /* Une ligne d'un export GATES, gardée à son numéro. Une ligne vide n'est
       pas gardée : son numéro suffit, le trou se comble à la fin. Une formule
       sans valeur calculée compte à part si elle tombe dans ce qui fait
       reconnaître l'export — l'en-tête, les lignes au-dessus (les groupes),
       la colonne de référence. */
    function ligneGates(num, valeurs, sansValeur) {
      var j = valeurs.length;
      while (j > 0 && (valeurs[j - 1] === '' || valeurs[j - 1] === undefined)) j--;
      if (sansValeur) {
        sansValeur.forEach(function (col) {
          if (num <= c.ligneEntete || col === c.iRef) c.formulesVides++; else c.formulesAilleurs++;
        });
      }
      if (!j) return true;
      if (j > c.largeur) c.largeur = j;
      c.lignes[num - 1] = valeurs;
      if (num * c.largeur > P.maxCellulesToutes) { c.trop = true; return false; }
      return true;
    }
    function poserGates(num, valeurs) {
      c.sorte = 'gates';
      c.ligneEntete = num;
      c.entete = valeurs.map(function (v) { return String(v === undefined || v === null ? '' : v).trim(); });
      c.iRef = indexReference(c.entete);
      var avant = c.avant;
      c.avant = [];
      for (var i = 0; i < avant.length; i++) if (!ligneGates(avant[i].num, avant[i].valeurs, avant[i].sansValeur)) return false;
      return true;
    }
    c.ligne = function (num, valeurs, sansValeur) {
      if (c.sorte === 'gates') return ligneGates(num, valeurs, sansValeur);
      if (c.sorte === 'see') return ligneSee(valeurs, sansValeur);
      var ns = valeurs.map(norm);
      if (num <= P.lignesScan) {
        /* L'autre sorte que celle de la case : la lecture s'arrête là, la
           case dira où mettre le fichier — sans lire l'extract entier. */
        var sorte = enteteSee(ns) ? 'see' : enteteGates(ns) ? 'gates' : null;
        if (sorte && attendu && sorte !== attendu) { c.sorte = sorte; c.ligneEntete = num; c.autre = true; return false; }
        if (sorte === 'see') { poserSee(num, valeurs, ns); return true; }
        if (sorte === 'gates') return poserGates(num, valeurs) && ligneGates(num, valeurs, sansValeur);
        c.avant.push({ num: num, valeurs: valeurs, sansValeur: sansValeur });
        var portes = N_CLES.filter(function (k) { return ns.indexOf(k) !== -1; });
        if (portes.length > c.meilleur.portes) {
          c.meilleur = { portes: portes.length, ligne: num,
            noms: valeurs.filter(function (v) { return String(v === undefined || v === null ? '' : v).trim(); }).slice(0, 12),
            manquent: P.cles.filter(function (k, i) { return portes.indexOf(N_CLES[i]) === -1; }) };
        }
        return true;
      }
      if (!c.tropBas && (enteteSee(ns) || enteteGates(ns))) c.tropBas = { sorte: enteteSee(ns) ? 'see' : 'gates', ligne: num };
      return !c.tropBas && num < P.lignesScan + LIGNES_SONDE;
    };
    c.fusion = function (ligne, col, nbLignes, nbCols) {
      /* Sous un en-tête déjà trouvé, une fusion ne sert à rien : ne pas la
         garder, pour que des milliers de fusions dans les plans ne fassent
         pas oublier celles de la ligne des groupes. */
      if (c.ligneEntete && ligne > c.ligneEntete) return;
      if (ligne >= 1 && col >= 1 && nbLignes >= 1 && nbCols >= 1 && nbLignes * nbCols > 1 && c.fusions.length < 5000) {
        c.fusions.push({ ligne: ligne, col: col, nbLignes: nbLignes, nbCols: nbCols });
      }
    };
    return c;
  }

  /* Un export GATES lu, mis en forme pour partir : les lignes de 1 à la
     dernière remplie, les trous comblés par des lignes vides ; les cellules
     fusionnées gardées (celles qui commencent sur l'en-tête ou au-dessus),
     rognées au bloc, leurs cellules cachées vidées — Sheets, en fusionnant,
     ne garde que celle du coin ; les références des plans (la colonne de
     référence, sous l'en-tête), pour compter celles qu'il partage avec
     l'onglet de sa case ; et le mot de ses groupes « XXX AA … », le nom
     proposé à un contrat ajouté dans la fenêtre. */
  function bilanGates(c) {
    var lignes = c.lignes, i, j;
    for (i = 0; i < lignes.length; i++) if (!lignes[i]) lignes[i] = [];
    var fusions = c.fusions.filter(function (f) { return f.ligne <= c.ligneEntete && f.ligne <= lignes.length && f.col <= c.largeur; })
      .map(function (f) {
        return { ligne: f.ligne, col: f.col, nbLignes: Math.min(f.nbLignes, lignes.length - f.ligne + 1), nbCols: Math.min(f.nbCols, c.largeur - f.col + 1) };
      })
      .filter(function (f) { return f.nbLignes * f.nbCols > 1; });
    fusions.forEach(function (f) {
      for (var a = f.ligne; a < f.ligne + f.nbLignes; a++) {
        for (var b = f.col; b < f.col + f.nbCols; b++) {
          if ((a !== f.ligne || b !== f.col) && lignes[a - 1][b - 1] !== undefined) lignes[a - 1][b - 1] = '';
        }
      }
    });
    /* La largeur et la hauteur, recomptées après coup : de A à la dernière
       colonne remplie, de 1 à la dernière ligne remplie. */
    var largeur = 0, hauteur = 0;
    for (i = 0; i < lignes.length; i++) {
      for (j = lignes[i].length; j > 0 && (lignes[i][j - 1] === '' || lignes[i][j - 1] === undefined); j--) { /* vide */ }
      if (j) { hauteur = i + 1; if (j > largeur) largeur = j; }
    }
    lignes.length = hauteur;
    var vues = {}, refs = [], donnees = 0;
    for (i = c.ligneEntete; i < hauteur; i++) {
      if (lignes[i].some(function (v) { return v !== '' && v !== undefined; })) donnees++;
      var r = norm(lignes[i][c.iRef]);
      if (r && !Object.prototype.hasOwnProperty.call(vues, r)) { vues[r] = true; refs.push(r); }
    }
    var compte = {}, mot = '', meilleur = 0;
    for (i = 0; i < c.ligneEntete - 1 && i < hauteur; i++) {
      lignes[i].forEach(function (v) {
        var t = String(v === undefined || v === null ? '' : v).trim();
        if (!t) return;
        var m = /^(\S+)\s+AA(?:\s|$)/i.exec(t);
        if (m) {
          var k = norm(m[1]);
          compte[k] = (compte[k] || 0) + 1;
          if (compte[k] > meilleur) { meilleur = compte[k]; mot = m[1]; }
        }
      });
    }
    return { sorte: 'gates', ligneEntete: c.ligneEntete, entete: c.entete, lignes: lignes, largeur: largeur, fusions: fusions,
             refs: refs, donnees: donnees, motGroupe: mot, onglet: c.onglet,
             formulesAilleurs: c.formulesAilleurs };
  }
  function colonneDe(ref) {
    var n = 0, i, k;
    for (i = 0; i < ref.length; i++) {
      k = ref.charCodeAt(i);
      if (k >= 65 && k <= 90) n = n * 26 + k - 64;
      else if (k >= 97 && k <= 122) n = n * 26 + k - 96;
      else break;
    }
    return n - 1;
  }
  function valeurAttr(s, motif) {
    var i = s.indexOf(motif);
    if (i === -1) return null;
    i += motif.length;
    return s.slice(i, s.indexOf(s.charAt(i - 1), i));
  }
  var RE_C = /<(?:[\w.-]+:)?c(?=[\s\/>])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?c\s*>)/g;
  var RE_V = /<(?:[\w.-]+:)?v(?:\s[^>]*)?>([\s\S]*?)<\/(?:[\w.-]+:)?v\s*>/;
  var RE_F = /<(?:[\w.-]+:)?f(?=[\s>\/])/;
  var RE_V_VIDE = /<(?:[\w.-]+:)?v\s*\/>/;
  var RE_FIN_DONNEES = /<\/(?:[\w.-]+:)?sheetData\s*>/;
  var RE_FIN_FUSIONS = /<\/(?:[\w.-]+:)?mergeCells\s*>/;
  /* Une plage écrite à la manière d'Excel (« B1:Q1 », « $A$2 ») : { ligne, col, nbLignes, nbCols } en 1-based, ou null. */
  function plageA1(ref) {
    var m = /^\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?$/.exec(String(ref === null || ref === undefined ? '' : ref).trim());
    if (!m) return null;
    var c1 = colonneDe(m[1]) + 1, l1 = parseInt(m[2], 10);
    var c2 = m[3] ? colonneDe(m[3]) + 1 : c1, l2 = m[4] ? parseInt(m[4], 10) : l1;
    return { ligne: Math.min(l1, l2), col: Math.min(c1, c2), nbLignes: Math.abs(l2 - l1) + 1, nbCols: Math.abs(c2 - c1) + 1 };
  }

  /* Un onglet du classeur, ligne à ligne. Rend le collecteur ; il dit si
     l'en-tête a été trouvé. Les cellules fusionnées s'écrivent APRÈS les
     lignes (<mergeCells>) : pour un export GATES, on lit jusqu'à elles ;
     pour SEE, ce qui suit les lignes — liens, fusions, mise en page — ne
     sert à rien, la lecture s'arrête là. */
  function lireOnglet(f, e, chaines, styles, en1904, toutes, avance) {
    var c = collecteur(toutes), numPrec = 0, formes = {};
    function forme(s) { return formes[s] || (formes[s] = formeDuFormat(styles, s)); }
    var surLigne = decoupeur('row', function (attrs, corps) {
      var rr = valeurAttr(attrs, ' r="') || valeurAttr(attrs, ' r=\'');
      var num = rr ? parseInt(rr, 10) : numPrec + 1;
      numPrec = num;
      var valeurs = [], sansValeur = null, colPrec = -1, m, voulues = c.voulues;
      RE_C.lastIndex = 0;
      while ((m = RE_C.exec(corps))) {
        var a = m[1], ref = valeurAttr(a, ' r="') || valeurAttr(a, ' r=\'');
        var col = ref ? colonneDe(ref) : colPrec + 1;
        colPrec = col;
        if (voulues && !voulues[col]) continue;
        var dedans = m[2] || '', t = valeurAttr(a, ' t="') || valeurAttr(a, ' t=\'') || 'n', v = '';
        if (t === 'inlineStr') v = texteRiche(dedans);
        else {
          var mv = RE_V.exec(dedans), brut = mv ? mv[1] : '';
          /* Sans valeur calculée : une formule sans <v>, ou dont le <v> vide
             n'est pas une chaîne (Excel écrit t="str" et <v></v> pour « "" »). */
          if (!brut && RE_F.test(dedans) && !(t === 'str' && (mv || RE_V_VIDE.test(dedans)))) (sansValeur || (sansValeur = [])).push(col);
          if (t === 's') { v = brut === '' ? '' : chaines[parseInt(brut, 10)]; if (v === undefined) v = ''; }
          else if (t === 'str' || t === 'e' || t === 'd') v = decoderChaine(brut);
          else if (t === 'b') v = brut === '1' ? 'VRAI' : brut === '0' ? 'FAUX' : '';
          else v = texteNombre(brut, forme(+(valeurAttr(a, ' s="') || valeurAttr(a, ' s=\'') || 0)), en1904);
        }
        valeurs[col] = v;
      }
      for (var j = 0; j < valeurs.length; j++) if (valeurs[j] === undefined) valeurs[j] = '';
      return c.ligne(num, valeurs, sansValeur);
    });
    var surFusion = decoupeur('mergeCell', function (attrs) {
      var z = plageA1(attribut(attrs, 'ref'));
      if (z) c.fusion(z.ligne, z.col, z.nbLignes, z.nbCols);
    });
    /* `queue` : la fin du morceau précédent, pour voir une balise coupée en deux. */
    var apresLignes = false, queue = '';
    return lirePartie(f, e, function (texte, fini) {
      var vu;
      if (!apresLignes) {
        if (surLigne(texte, fini) === false) return false;
        vu = queue + texte;
        var i = vu.search(RE_FIN_DONNEES);
        if (i === -1) { queue = vu.slice(-40); return true; }
        if (c.sorte !== 'gates') return false;
        apresLignes = true;
        texte = vu.slice(i);
        queue = '';
      }
      surFusion(texte, fini);
      vu = queue + texte;
      queue = vu.slice(-40);
      return !RE_FIN_FUSIONS.test(vu);
    }, avance).then(function () { return c; });
  }
  function chercher(entrees, chemin) {
    if (entrees[chemin]) return entrees[chemin];
    var b = chemin.toLowerCase();
    for (var k in entrees) if (Object.prototype.hasOwnProperty.call(entrees, k) && k.toLowerCase() === b) return entrees[k];
    return null;
  }
  function cible(dossier, t) {
    if (t.charAt(0) === '/') return t.slice(1);
    var parts = (dossier + t).split('/'), out = [];
    parts.forEach(function (p) { if (p === '..') out.pop(); else if (p && p !== '.') out.push(p); });
    return out.join('/');
  }

  var DOSSIER_COMPRESSE = 'C’est un dossier compressé (.zip), pas un classeur : l’ouvrir (double-clic, ou clic droit → Extraire tout) et ' +
    'glisser ici le fichier .xls, .xlsx ou .csv qu’il contient.';
  function lireXlsx(f, toutes) {
    progres(0.02, 'Ouverture du fichier…');
    return lireZip(f).then(function (entrees) {
      var wb = chercher(entrees, 'xl/workbook.xml');
      if (!wb) {
        if (chercher(entrees, 'xl/workbook.bin')) {
          throw erreur('C’est un classeur binaire (.xlsb), que ni la fenêtre ni Google Sheets ne lisent. Il faut l’export en .xlsx ou en .csv — ' +
            'ou l’ouvrir dans Excel et l’enregistrer en classeur Excel (.xlsx).');
        }
        /* Un « dossier compressé » de Windows (un .zip), peut-être renommé :
           dire de l'ouvrir, et ce qu'il renferme. */
        var dedans = [];
        for (var k in entrees) {
          if (Object.prototype.hasOwnProperty.call(entrees, k) && /\.(xlsx|xlsm|xls|csv|mht|mhtml)$/i.test(k)) dedans.push(k.replace(/^.*\//, ''));
        }
        throw erreur(DOSSIER_COMPRESSE + (dedans.length ? ' Il renferme : ' + dedans.slice(0, 4).join(', ') + (dedans.length > 4 ? ', …' : '') + '.' : ''));
      }
      var rels = chercher(entrees, 'xl/_rels/workbook.xml.rels');
      return Promise.all([partieEntiere(f, wb), rels ? partieEntiere(f, rels) : '']).then(function (r) {
        var classeur = r[0], liens = {}, m;
        var reL = /<(?:[\w.-]+:)?Relationship\s([^>]*?)\/?>/g;
        while ((m = reL.exec(r[1]))) liens[attribut(m[1], 'Id')] = { type: attribut(m[1], 'Type') || '', cible: cible('xl/', attribut(m[1], 'Target') || '') };
        var parType = function (fin) { for (var k in liens) if (liens[k].type.slice(-fin.length) === fin) return liens[k].cible; return null; };
        var onglets = [], reS = /<(?:[\w.-]+:)?sheet\s([^>]*?)\/?>/g;
        while ((m = reS.exec(classeur))) {
          var lien = liens[attribut(m[1], 'id')];
          var e = lien ? chercher(entrees, lien.cible) : null;
          if (e) onglets.push({ nom: attribut(m[1], 'name') || '', cache: !!attribut(m[1], 'state') && attribut(m[1], 'state') !== 'visible', e: e });
        }
        if (!onglets.length) {
          for (var k in entrees) if (/^xl\/worksheets\/[^\/]+\.xml$/i.test(k)) onglets.push({ nom: k, cache: false, e: entrees[k] });
        }
        onglets.sort(function (a, b) { return (a.cache ? 1 : 0) - (b.cache ? 1 : 0); });
        var en1904 = /date1904\s*=\s*"(?:1|true)"/.test(classeur);
        var eChaines = chercher(entrees, parType('/sharedStrings') || 'xl/sharedStrings.xml');
        var eStyles = chercher(entrees, parType('/styles') || 'xl/styles.xml');
        var total = (eChaines ? eChaines.tu : 0) + onglets.reduce(function (s, o) { return s + o.e.tu; }, 0) || 1, fait = 0;
        var chaines = [];
        var etapeStyles = eStyles ? partieEntiere(f, eStyles).then(lireStyles) : Promise.resolve(null);
        return etapeStyles.then(function (styles) {
          if (!eChaines) return styles;
          progres(0.05, 'Lecture des textes du classeur…');
          var surSi = decoupeur('si', function (a, corps) { chaines.push(texteRiche(corps)); });
          return lirePartie(f, eChaines, surSi, function (n) { progres(0.05 + 0.9 * n / total); }).then(function () {
            fait = eChaines.tu;
            return styles;
          });
        }).then(function (styles) {
          var meilleur = null, tropBas = null, i = 0;
          function suivant() {
            if (i >= onglets.length) return { trouve: false, meilleur: meilleur, tropBas: tropBas, onglets: onglets.map(function (o) { return o.nom; }) };
            var o = onglets[i++];
            progres(0.05 + 0.9 * fait / total, 'Lecture de l’onglet « ' + o.nom + ' »…');
            return lireOnglet(f, o.e, chaines, styles, en1904, toutes, function (n) { progres(0.05 + 0.9 * (fait + n) / total); }).then(function (c) {
              fait += o.e.tu;
              if (c.sorte) { c.onglet = o.nom; c.trouve = true; c.format = 'xlsx'; return c; }
              if (c.tropBas && !tropBas) { tropBas = c.tropBas; tropBas.onglet = o.nom; }
              if (!meilleur || c.meilleur.portes > meilleur.portes) { meilleur = c.meilleur; meilleur.onglet = o.nom; }
              return suivant();
            });
          }
          return suivant();
        });
      });
    });
  }

  // ------------------------------------------------------------ fichiers texte : CSV, page web, XML 2003
  function analyseurCsv(sep, surLigne) {
    var champ = '', ligne = [], dans = false, attente = false, egal = false, cr = false, num = 0, arret = false;
    function finLigne() { ligne.push(champ); champ = ''; var l = ligne; ligne = []; num++; if (surLigne(num, l) === false) arret = true; }
    return function (texte, fini) {
      for (var i = 0; i < texte.length && !arret; i++) {
        var ch = texte.charAt(i), etaitCr = cr;
        cr = false;
        if (attente) {
          attente = false;
          if (ch === '"') { champ += '"'; continue; }
          dans = false;
        }
        /* ="001" : la façon d'un export de garder ses zéros — le champ vaut 001. */
        if (egal) {
          egal = false;
          if (ch === '"') { dans = true; continue; }
          champ += '=';
        }
        if (dans) { if (ch === '"') attente = true; else champ += ch; continue; }
        if (ch === '"' && champ === '') { dans = true; continue; }
        if (ch === '=' && champ === '') { egal = true; continue; }
        if (ch === sep) { ligne.push(champ); champ = ''; continue; }
        if (ch === '\r') { finLigne(); cr = true; continue; }
        if (ch === '\n') { if (!etaitCr) finLigne(); continue; }
        champ += ch;
      }
      if (fini && !arret) {
        if (egal) { champ += '='; egal = false; }
        if (champ !== '' || ligne.length) finLigne();
      }
      return !arret;
    };
  }
  var ENTITES_HTML = { amp: '&', lt: '<', gt: '>', quot: '"', apos: '\'', nbsp: '\u00a0', eacute: 'é', egrave: 'è', ecirc: 'ê',
    agrave: 'à', acirc: 'â', ccedil: 'ç', ocirc: 'ô', ucirc: 'û', ugrave: 'ù', icirc: 'î', iuml: 'ï', euml: 'ë', Eacute: 'É',
    laquo: '«', raquo: '»', deg: '°', euro: '€', ndash: '–', mdash: '—', rsquo: '’', lsquo: '‘', hellip: '…' };
  var zoneEntites = null;
  function decoderHtml(s) {
    return s.replace(/&(#\d+|#x[0-9a-fA-F]+|[A-Za-z]\w*);/g, function (m, n) {
      if (n.charAt(0) === '#') return String.fromCodePoint(n.charAt(1) === 'x' || n.charAt(1) === 'X' ? parseInt(n.slice(2), 16) : parseInt(n.slice(1), 10));
      if (ENTITES_HTML[n] !== undefined) return ENTITES_HTML[n];
      zoneEntites = zoneEntites || document.createElement('textarea');
      zoneEntites.innerHTML = m;
      return zoneEntites.value;
    });
  }
  function texteCellule(x) {
    var t = x.replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]*>/g, '');
    return plat(decoderHtml(t).replace(/[ \t\r\n]+/g, ' ').trim());
  }
  /* La taille d'une fusion (colspan, rowspan, MergeAcross…), bornée — en
     largeur, par le plus grand nombre de colonnes accepté : un titre sur
     toute la largeur d'un export GATES (138 colonnes) reste entier ; un
     nombre illisible vaut une cellule. */
  function etendue(texte, max) {
    var n = parseInt(texte, 10);
    return n >= 1 ? Math.min(n, max) : 1;
  }
  var RE_TD = /<(?:[\w.-]+:)?t[dh](?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?t[dh]\s*>)/gi;
  /* Une page web : une ligne par <tr>, une cellule par <td>. Une cellule
     étendue (colspan, rowspan) occupe toutes ses places — vides, sauf la
     première — et devient une fusion, comme dans un collage ; les cellules
     des lignes suivantes passent après celles qu'un rowspan occupe. */
  function analyseurHtml(c) {
    var num = 0, occupees = {};
    return decoupeur('tr', function (attrs, corps) {
      num++;
      var valeurs = [], col = 0, prises = occupees[num] || {}, m, k;
      delete occupees[num];
      RE_TD.lastIndex = 0;
      while ((m = RE_TD.exec(corps))) {
        while (prises[col]) valeurs[col++] = '';
        var large = etendue(attribut(m[1], 'colspan'), P.maxColonnes), haut = etendue(attribut(m[1], 'rowspan'), 1000);
        valeurs[col] = m[2] ? texteCellule(m[2]) : '';
        for (k = 1; k < large; k++) valeurs[col + k] = '';
        /* « mso-ignore:colspan » : Excel regroupe ainsi des cases vides, ou
           les voisines sur lesquelles un texte déborde — ce n'est pas une
           fusion. La cellule occupe quand même ses colonnes. */
        if ((large > 1 || haut > 1) && !/mso-ignore\s*:\s*colspan/i.test(m[1])) c.fusion(num, col + 1, haut, large);
        for (var r = 1; r < haut; r++) {
          var o = occupees[num + r] || (occupees[num + r] = {});
          for (k = 0; k < large; k++) o[col + k] = true;
        }
        col += large;
      }
      for (k in prises) if (Object.prototype.hasOwnProperty.call(prises, k) && +k >= valeurs.length) valeurs[+k] = '';
      for (k = 0; k < valeurs.length; k++) if (valeurs[k] === undefined) valeurs[k] = '';
      return c.ligne(num, valeurs);
    }, true);
  }
  var RE_CELL = /<(?:[\w.-]+:)?Cell(?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?Cell\s*>)/g;
  var RE_DATA = /<(?:[\w.-]+:)?Data(?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?Data\s*>)/;
  /* Le XML 2003 d'Excel : un onglet après l'autre ; l'en-tête est cherché
     dans chacun tant qu'il n'est pas trouvé, et la lecture s'arrête à la fin
     de celui qui le porte. MergeAcross et MergeDown font des fusions ; une
     cellule sans ss:Index passe après celles qu'un MergeDown occupe. */
  function analyseurXml2003(nouveauCollecteur, surFin) {
    var c = nouveauCollecteur(), num = 0, garde = { c: c }, occupees = {};
    var lignes = decoupeur('Row', function (attrs, corps) {
      var idx = attribut(attrs, 'Index');
      num = idx ? parseInt(idx, 10) : num + 1;
      var valeurs = [], col = -1, m, prises = occupees[num] || {};
      delete occupees[num];
      RE_CELL.lastIndex = 0;
      while ((m = RE_CELL.exec(corps))) {
        var ci = attribut(m[1], 'Index');
        if (ci) col = parseInt(ci, 10) - 1;
        else { col++; while (prises[col]) col++; }
        var d = m[2] ? RE_DATA.exec(m[2]) : null, v = '';
        if (d) {
          var type = attribut(d[1], 'Type') || 'String', brut = d[2] ? d[2].replace(/<!\[CDATA\[[\s\S]*?\]\]>|<[^>]*>/g, function (x) { return x.charAt(1) === '!' ? x : ''; }) : '';
          if (type === 'Number') v = texteNombre(decoderXml(brut).trim(), { type: 'general' }, false);
          else if (type === 'DateTime') {
            var mm = /^(\d{4})-(\d\d)-(\d\d)(?:T(\d\d):(\d\d))?/.exec(brut);
            v = mm ? mm[3] + '/' + mm[2] + '/' + mm[1] + (mm[4] && (mm[4] !== '00' || mm[5] !== '00') ? ' ' + mm[4] + ':' + mm[5] : '') : brut;
          } else if (type === 'Boolean') v = brut.trim() === '1' ? 'VRAI' : 'FAUX';
          else v = plat(decoderXml(brut));
        }
        valeurs[col] = v;
        var large = etendue(String(1 + (parseInt(attribut(m[1], 'MergeAcross') || '0', 10) || 0)), P.maxColonnes);
        var haut = etendue(String(1 + (parseInt(attribut(m[1], 'MergeDown') || '0', 10) || 0)), 1001);
        if (large > 1 || haut > 1) garde.c.fusion(num, col + 1, haut, large);
        for (var r = 1; r < haut; r++) {
          var o = occupees[num + r] || (occupees[num + r] = {});
          for (var k = 0; k < large; k++) o[col + k] = true;
        }
        col += large - 1;
      }
      for (var j = 0; j < valeurs.length; j++) if (valeurs[j] === undefined) valeurs[j] = '';
      return garde.c.ligne(num, valeurs);
    });
    var reOnglet = /<(?:[\w.-]+:)?Worksheet(?=[\s>])/g;
    var analyse = function (texte, fini) {
      var debut = 0, m;
      reOnglet.lastIndex = 0;
      while ((m = reOnglet.exec(texte))) {
        if (lignes(texte.slice(debut, m.index), false) === false && garde.c.sorte) return false;
        debut = m.index;
        if (num > 0) {
          if (garde.c.sorte) { surFin(garde.c); return false; }
          surFin(garde.c);
          garde.c = nouveauCollecteur(); num = 0; occupees = {};
        }
      }
      var r = lignes(texte.slice(debut), fini);
      return r === false && !garde.c.sorte ? true : r;
    };
    analyse.courant = function () { return garde.c; };
    return analyse;
  }

  /* Ce qu'est un fichier texte : son encodage (une marque d'ordre, sinon de
     l'UTF-8 s'il en est, sinon du Windows-1252), puis sa sorte — page web,
     XML 2003 d'Excel, autre XML, ou CSV. */
  function sonderTexte(f) {
    return lireOctets(f, 0, Math.min(f.size, 1048576)).then(function (b) {
      var encodage = 'utf-8', saut = 0;
      if (b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF) saut = 3;
      else if (b[0] === 0xFF && b[1] === 0xFE) { encodage = 'utf-16le'; saut = 2; }
      else if (b[0] === 0xFE && b[1] === 0xFF) { encodage = 'utf-16be'; saut = 2; }
      else {
        try { new TextDecoder('utf-8', { fatal: true }).decode(b.subarray(0, b.length === f.size ? b.length : Math.max(0, b.length - 4))); }
        catch (e) { encodage = 'windows-1252'; }
      }
      var tete = new TextDecoder(encodage).decode(b.subarray(saut, Math.min(b.length, saut + 65536))).replace(/^\ufeff/, '');
      var debut = tete.replace(/^\s+/, '').slice(0, 4096).toLowerCase();
      var sorte = 'csv';
      /* Une page web archivée (.mht) : des en-têtes de courriel, dont
         MIME-Version ou un Content-Type multipart, avant la première ligne vide. */
      var entetes = tete.replace(/^\s+/, '').split(/\r?\n\r?\n/)[0].slice(0, 8192);
      if (/^[\w-]+[ \t]*:/.test(entetes) && /(^|\n)(mime-version[ \t]*:|content-type[ \t]*:[ \t]*multipart\/)/i.test(entetes)) sorte = 'mhtml';
      else if (debut.charAt(0) === '<') {
        if (/urn:schemas-microsoft-com:office:spreadsheet/.test(tete) && /<(?:\w+:)?(?:workbook|worksheet)[\s>]/i.test(tete) && !/<html|<!doctype html/.test(debut)) sorte = 'xml2003';
        else if (/<html|<table|<!doctype html|<body/.test(debut) || /<table[\s>]/i.test(tete)) sorte = 'html';
        else sorte = 'xml';
      }
      return { encodage: encodage, saut: saut, tete: tete, sorte: sorte };
    });
  }
  /* Les champs d'une ligne, guillemets compris (« "NAME" », « ="001" »,
     un séparateur entre guillemets) — pour choisir le séparateur. */
  function champsCsv(l, sep) {
    var out = [], cur = '', q = false;
    for (var i = 0; i < l.length; i++) {
      var ch = l.charAt(i);
      if (q) { if (ch !== '"') cur += ch; else if (l.charAt(i + 1) === '"') { cur += '"'; i++; } else q = false; }
      else if (ch === '"') q = true;
      else if (ch === sep) { out.push(cur); cur = ''; }
      else cur += ch;
    }
    out.push(cur);
    return out;
  }
  function lireTexte(f, toutes, sonde) {
    progres(0.02, 'Lecture du fichier…');
    if (sonde.sorte === 'xml') throw erreur('Ce fichier est du XML, mais pas un classeur Excel que la fenêtre connaisse. Il faut l’export en .xlsx ou en .csv.');
    function lecture(encodage, strict) {
      var c = null, fin = null, tropBas = null, nouveau = function () { return collecteur(toutes); };
      var analyse, premier = true;
      var retenir = function (x) {
        if (x.tropBas && !tropBas) tropBas = x.tropBas;
        if (!fin || (x.sorte && !fin.sorte) || (!fin.sorte && x.meilleur.portes > fin.meilleur.portes)) fin = x;
      };
      if (sonde.sorte === 'html') { c = nouveau(); analyse = analyseurHtml(c); }
      else if (sonde.sorte === 'xml2003') analyse = analyseurXml2003(nouveau, retenir);
      else {
        /* Le séparateur : celui qui fait le mieux apparaître une ligne
           d'en-têtes — les colonnes de SEE, les mots d'un en-tête GATES —,
           puis le plus de champs. */
        var lignes = sonde.tete.split(/\r\n|\n|\r/).slice(0, P.lignesScan + 1), sep = ';', meilleur = -1;
        [';', ',', '\t', '|'].forEach(function (s) {
          var score = Math.max.apply(null, lignes.map(function (l) {
            var ns = champsCsv(l, s).map(function (x) { return norm(x.replace(/^=/, '')); });
            return (N_CLES.filter(function (k) { return ns.indexOf(k) !== -1; }).length +
                    P.motsCles.filter(function (k) { return ns.indexOf(k) !== -1; }).length) * 1000 + Math.min(999, ns.length);
          }));
          if (score > meilleur) { meilleur = score; sep = s; }
        });
        c = nouveau();
        analyse = analyseurCsv(sep, function (num, l) { return c.ligne(num, l); });
      }
      var flux = f.slice(sonde.saut).stream();
      return lireFlux(flux, encodage, function (texte, fini) {
        if (premier) { texte = texte.replace(/^\ufeff/, ''); premier = false; }
        return analyse(texte, fini);
      }, function (n) { progres(0.05 + 0.9 * n / (f.size || 1)); }, null, strict).then(function () {
        if (sonde.sorte === 'xml2003') retenir(analyse.courant());
        var r = sonde.sorte === 'xml2003' ? (fin && fin.sorte ? fin : null) : c;
        if (!r) return { trouve: false, meilleur: fin ? fin.meilleur : { portes: 0 }, tropBas: tropBas, onglets: [f.name] };
        if (r.sorte) { r.trouve = true; r.onglet = f.name; r.format = sonde.sorte; return r; }
        r.meilleur.onglet = f.name;
        return { trouve: false, meilleur: r.meilleur, tropBas: r.tropBas || tropBas, onglets: [f.name] };
      });
    }
    /* De l'UTF-8 qui n'en est plus, loin dans le fichier : on relit en
       Windows-1252 plutôt que d'écrire des « � ». */
    if (sonde.encodage === 'utf-8') {
      return lecture('utf-8', true).catch(function (e) {
        if (e && e.pasUtf8) { progres(0.02, 'Lecture du fichier (accents Windows)…'); return lecture('windows-1252', false); }
        throw e;
      });
    }
    return lecture(sonde.encodage, false);
  }

  // ------------------------------------------------------------ vrais .xls : le conteneur OLE
  /* Un vrai .xls — Excel 97 à 2003 (BIFF8), ou Excel 5 et 95 (BIFF5) — n'est
     ni un zip ni du texte : c'est un « conteneur OLE », un petit système de
     fichiers fait de secteurs de 512 ou 4 096 octets. Sa table d'allocation
     (la FAT) dit, pour chaque secteur, celui qui le suit ; les secteurs de la
     FAT eux-mêmes sont listés par la DIFAT (109 places dans l'en-tête, puis
     des secteurs chaînés pour les gros fichiers). Le répertoire — des entrées
     de 128 octets, aux noms en UTF-16 — nomme les flux : le classeur est
     « Workbook » (Excel 97-2003) ou « Book » (Excel 5 / 95). Un flux de moins
     de 4 096 octets loge dans le « mini-flux », par blocs de 64 octets que
     chaîne la mini-FAT. Il faut sauter d'un secteur à l'autre : le fichier
     est lu en entier — un .xls ne dépasse pas 65 536 lignes, et au-delà de
     P.maxOctetsXls ce n'est pas un export. Chaque chaîne est suivie sous
     garde : un secteur hors du fichier, une boucle, une chaîne trop courte
     pour le flux annoncé disent un fichier abîmé — le plus souvent un
     téléchargement coupé. */
  var FIN_DE_CHAINE = 0xFFFFFFFE, SECTEUR_SPECIAL = 0xFFFFFFFA;
  var ABIME_XLS = 'Le fichier est abîmé (sa structure de classeur .xls ne se suit pas jusqu’au bout : téléchargement interrompu ?) : ' +
    'le retélécharger depuis GATES ou SEE.';
  var PROTEGE = 'Ce fichier Excel est protégé (mot de passe ou étiquette de confidentialité) : la fenêtre ne peut pas le lire, ' +
    'Google Sheets non plus. Demander l’export sans protection, ou en .csv.';
  var TRES_ANCIEN = 'C’est un très ancien format Excel (Excel 2 à 4, d’avant 1993), que la fenêtre ne lit pas : demander l’export en .xlsx, ' +
    'en .xls ou en .csv — ou l’ouvrir dans Excel et l’enregistrer en classeur Excel (.xlsx).';
  var SANS_CLASSEUR = 'Ce fichier est un document Office (conteneur OLE), mais il ne renferme aucun classeur Excel : est-ce un document Word, ' +
    'ou un autre fichier renommé ? Demander l’export en .xlsx, en .xls ou en .csv.';
  function tropGros(f) {
    return erreur('Ce fichier fait ' + taille(f.size) + ' : bien plus qu’un export (au plus ' + taille(P.maxOctetsXls) + ' pour un .xls ou une ' +
      'page web archivée). Est-ce bien l’export GATES ou SEE ? Sinon, demander l’export en .xlsx ou en .csv.');
  }
  function entreeOle(b, o, version) {
    var lg = Math.min(64, u16(b, o + 64)), nom = '';
    for (var j = 0; j < lg - 2; j += 2) nom += String.fromCharCode(u16(b, o + j));
    return { nom: nom, gauche: u32(b, o + 68), droite: u32(b, o + 72), enfant: u32(b, o + 76), debut: u32(b, o + 116),
             taille: u32(b, o + 120) + (version === 4 ? u32(b, o + 124) * 4294967296 : 0) };
  }
  /* Le conteneur d'un fichier lu en entier (`b`) : { nomme(noms), flux(entrée) }. */
  function ouvrirOle(b) {
    var decalage = b.length >= 512 ? u16(b, 0x1E) : 0;
    if (decalage !== 9 && decalage !== 12) throw erreur(ABIME_XLS);
    var taille = decalage === 9 ? 512 : 4096, parSecteur = taille / 4, version = u16(b, 0x1A);
    var nbFat = u32(b, 0x2C), difat = [], vus = {}, n, o, i, k;
    /* Un secteur entier dans le fichier : sinon, le fichier a été coupé. */
    function present(s) { return s < SECTEUR_SPECIAL && (s + 2) * taille <= b.length; }
    for (i = 0; i < 109 && difat.length < nbFat; i++) difat.push(u32(b, 0x4C + 4 * i));
    n = u32(b, 0x44);
    while (difat.length < nbFat && n < SECTEUR_SPECIAL) {
      if (vus[n] || !present(n)) throw erreur(ABIME_XLS);
      vus[n] = true;
      o = (n + 1) * taille;
      for (i = 0; i < parSecteur - 1 && difat.length < nbFat; i++) difat.push(u32(b, o + 4 * i));
      n = u32(b, o + taille - 4);
    }
    var fat = new Uint32Array(difat.length * parSecteur);
    for (k = 0; k < difat.length; k++) {
      var la = present(difat[k]);
      o = (difat[k] + 1) * taille;
      for (i = 0; i < parSecteur; i++) fat[k * parSecteur + i] = la ? u32(b, o + 4 * i) : 0xFFFFFFFF;
    }
    /* La chaîne qui part du secteur `depart` dans `table`, au plus `besoin` secteurs. */
    function suivre(depart, table, besoin) {
      var l = [], s = depart, vu = new Uint8Array(table.length);
      while (s !== FIN_DE_CHAINE && l.length < besoin) {
        if (!(s < table.length) || vu[s]) throw erreur(ABIME_XLS);
        vu[s] = 1;
        l.push(s);
        s = table[s];
      }
      return l;
    }
    var dir, repertoireCasse = false;
    try { dir = suivre(u32(b, 0x30), fat, Infinity); } catch (e) { dir = []; repertoireCasse = true; }
    /* Une FAT illisible : le premier secteur du répertoire dit encore ce que
       renferme le fichier (un classeur chiffré, le plus souvent). Mais le
       classeur peut être nommé plus loin : s'il manque, le fichier est abîmé
       (repertoireCasse), pas un document sans classeur. */
    if (!dir.length) dir = [u32(b, 0x30)];
    var entrees = [];
    for (k = 0; k < dir.length && present(dir[k]); k++) {
      o = (dir[k] + 1) * taille;
      for (i = 0; i < taille; i += 128) entrees.push(entreeOle(b, o + i, version));
    }
    if (!entrees.length) throw erreur(ABIME_XLS);
    /* Les flux de la racine : un arbre (frères à gauche et à droite) qui part
       de l'enfant de la première entrée. */
    var racine = [], pile = [entrees[0].enfant], dejaVu = {};
    while (pile.length) {
      k = pile.pop();
      if (k > 0 && k < entrees.length && !dejaVu[k]) {
        dejaVu[k] = true;
        racine.push(entrees[k]);
        pile.push(entrees[k].gauche, entrees[k].droite);
      }
    }
    /* La première entrée qui porte l'un de ces noms (en minuscules : un nom
       OLE se compare sans la casse), à la racine d'abord, puis — répertoire
       mal chaîné — parmi toutes. */
    function nomme(noms) {
      var listes = [racine, entrees.slice(1)];
      for (var a = 0; a < listes.length; a++) {
        for (var j = 0; j < noms.length; j++) {
          for (var e = 0; e < listes[a].length; e++) if (listes[a][e].nom.toLowerCase() === noms[j]) return listes[a][e];
        }
      }
      return null;
    }
    var coupure = u32(b, 0x38) || 4096, miniFat = null, miniFlux = null;
    function copierSecteurs(l, t, sortie) {
      var fait = 0, j, s, o2, m;
      if (l.length * taille < t) throw erreur(ABIME_XLS);
      /* Les secteurs qui se suivent dans le fichier sont copiés d'un bloc. */
      for (j = 0; j < l.length && fait < t; j = s) {
        for (s = j + 1; s < l.length && l[s] === l[s - 1] + 1; s++) { /* même bloc */ }
        o2 = (l[j] + 1) * taille;
        m = Math.min((s - j) * taille, t - fait);
        if (o2 + m > b.length) throw erreur(ABIME_XLS);
        sortie.set(b.subarray(o2, o2 + m), fait);
        fait += m;
      }
      return sortie;
    }
    function depuisMiniFlux(e, sortie) {
      var t = e.taille, fait = 0, j, s, o2, m, l;
      if (!miniFlux) {
        miniFlux = suivre(entrees[0].debut, fat, Math.ceil(entrees[0].taille / taille));
        var lm = suivre(u32(b, 0x3C), fat, Infinity);
        miniFat = new Uint32Array(lm.length * parSecteur);
        for (j = 0; j < lm.length; j++) {
          if (!present(lm[j])) throw erreur(ABIME_XLS);
          for (var q = 0; q < parSecteur; q++) miniFat[j * parSecteur + q] = u32(b, (lm[j] + 1) * taille + 4 * q);
        }
      }
      l = suivre(e.debut, miniFat, Math.ceil(t / 64));
      if (l.length * 64 < t) throw erreur(ABIME_XLS);
      for (j = 0; j < l.length; j++) {
        s = Math.floor(l[j] * 64 / taille);
        if (s >= miniFlux.length) throw erreur(ABIME_XLS);
        o2 = (miniFlux[s] + 1) * taille + (l[j] * 64) % taille;
        m = Math.min(64, t - fait);
        if (o2 + m > b.length) throw erreur(ABIME_XLS);
        sortie.set(b.subarray(o2, o2 + m), fait);
        fait += m;
      }
      return sortie;
    }
    /* Le contenu d'un flux, recomposé secteur après secteur. */
    function flux(e) {
      var t = e.taille;
      if (t > b.length) throw erreur(ABIME_XLS);
      var sortie = new Uint8Array(t);
      if (!t) return sortie;
      if (t >= coupure) return copierSecteurs(suivre(e.debut, fat, Math.ceil(t / taille)), t, sortie);
      /* Un petit flux rangé hors du mini-flux, contre la règle : on le
         cherche aussi dans les secteurs ordinaires. */
      try { return depuisMiniFlux(e, sortie); }
      catch (x) { return copierSecteurs(suivre(e.debut, fat, Math.ceil(t / taille)), t, sortie); }
    }
    return { nomme: nomme, flux: flux, repertoireCasse: repertoireCasse };
  }

  // ------------------------------------------------------------ vrais .xls : les enregistrements BIFF
  /* Le classeur est une suite d'enregistrements : un type et une longueur
     sur deux octets chacun, puis les données. D'abord la partie commune
     (BOF … EOF) : les onglets et leur place dans le flux (BOUNDSHEET), la
     page de codes (CODEPAGE), le calendrier 1904 (DATEMODE), les formats de
     nombres (FORMAT, et XF qui donne le format de chaque cellule), un mot de
     passe (FILEPASS : le fichier est chiffré) et, en BIFF8, la table des
     textes partagés (SST). Puis chaque onglet (BOF … EOF) : ses cellules,
     ligne après ligne, et ses cellules fusionnées (MERGEDCELLS, après les
     cellules, en plusieurs enregistrements s'il le faut). Lignes et colonnes
     y comptent depuis 0 : la ligne 0 est la ligne 1 de l'onglet. */
  var ERREURS_XLS = { 0: '#NULL!', 7: '#DIV/0!', 15: '#VALUE!', 23: '#REF!', 29: '#NAME?', 36: '#NUM!', 42: '#N/A', 43: '#GETTING_DATA' };
  /* FORMULA porte aussi les numéros 0x0206 et 0x0406 (ceux d'Excel 3 et 4) :
     Apple Numbers, entre autres, les écrit encore dans un .xls d'Excel 97,
     avec la disposition de BIFF5/8 — les vrais BIFF3/4 sont refusés plus
     haut (TRES_ANCIEN). */
  var FORMULES_XLS = { 0x0006: 1, 0x0206: 1, 0x0406: 1 };
  var CELLULES_XLS = { 0x0006: 1, 0x0206: 1, 0x0406: 1, 0x0201: 1, 0x00BE: 1, 0x0203: 1, 0x027E: 1, 0x00BD: 1, 0x00FD: 1, 0x0204: 1, 0x00D6: 1, 0x0205: 1 };
  var PAGES_DE_CODES = { 367: 'windows-1252', 874: 'windows-874', 932: 'shift_jis', 936: 'gbk', 949: 'euc-kr', 950: 'big5',
    1250: 'windows-1250', 1251: 'windows-1251', 1252: 'windows-1252', 1253: 'windows-1253', 1254: 'windows-1254', 1255: 'windows-1255',
    1256: 'windows-1256', 1257: 'windows-1257', 1258: 'windows-1258', 10000: 'macintosh', 10007: 'x-mac-cyrillic', 20866: 'koi8-r',
    21866: 'koi8-u', 28591: 'windows-1252', 32768: 'macintosh', 32769: 'windows-1252', 65001: 'utf-8' };
  /* Deux pages de codes du DOS que le navigateur ne connaît pas : leur moitié haute, octets 128 à 255. */
  var PAGES_DOS = {
    437: '\u00c7\u00fc\u00e9\u00e2\u00e4\u00e0\u00e5\u00e7\u00ea\u00eb\u00e8\u00ef\u00ee\u00ec\u00c4\u00c5\u00c9\u00e6\u00c6\u00f4\u00f6\u00f2\u00fb\u00f9' +
      '\u00ff\u00d6\u00dc\u00a2\u00a3\u00a5\u20a7\u0192\u00e1\u00ed\u00f3\u00fa\u00f1\u00d1\u00aa\u00ba\u00bf\u2310\u00ac\u00bd\u00bc\u00a1\u00ab\u00bb' +
      '\u2591\u2592\u2593\u2502\u2524\u2561\u2562\u2556\u2555\u2563\u2551\u2557\u255d\u255c\u255b\u2510\u2514\u2534\u252c\u251c\u2500\u253c\u255e\u255f' +
      '\u255a\u2554\u2569\u2566\u2560\u2550\u256c\u2567\u2568\u2564\u2565\u2559\u2558\u2552\u2553\u256b\u256a\u2518\u250c\u2588\u2584\u258c\u2590\u2580' +
      '\u03b1\u00df\u0393\u03c0\u03a3\u03c3\u00b5\u03c4\u03a6\u0398\u03a9\u03b4\u221e\u03c6\u03b5\u2229\u2261\u00b1\u2265\u2264\u2320\u2321\u00f7\u2248' +
      '\u00b0\u2219\u00b7\u221a\u207f\u00b2\u25a0\u00a0',
    850: '\u00c7\u00fc\u00e9\u00e2\u00e4\u00e0\u00e5\u00e7\u00ea\u00eb\u00e8\u00ef\u00ee\u00ec\u00c4\u00c5\u00c9\u00e6\u00c6\u00f4\u00f6\u00f2\u00fb\u00f9' +
      '\u00ff\u00d6\u00dc\u00f8\u00a3\u00d8\u00d7\u0192\u00e1\u00ed\u00f3\u00fa\u00f1\u00d1\u00aa\u00ba\u00bf\u00ae\u00ac\u00bd\u00bc\u00a1\u00ab\u00bb' +
      '\u2591\u2592\u2593\u2502\u2524\u00c1\u00c2\u00c0\u00a9\u2563\u2551\u2557\u255d\u00a2\u00a5\u2510\u2514\u2534\u252c\u251c\u2500\u253c\u00e3\u00c3' +
      '\u255a\u2554\u2569\u2566\u2560\u2550\u256c\u00a4\u00f0\u00d0\u00ca\u00cb\u00c8\u0131\u00cd\u00ce\u00cf\u2518\u250c\u2588\u2584\u00a6\u00cc\u2580' +
      '\u00d3\u00df\u00d4\u00d2\u00f5\u00d5\u00b5\u00fe\u00de\u00da\u00db\u00d9\u00fd\u00dd\u00af\u00b4\u00ad\u00b1\u2017\u00be\u00b6\u00a7\u00f7\u00b8' +
      '\u00b0\u00a8\u00b7\u00b9\u00b3\u00b2\u25a0\u00a0'
  };
  /* Les octets d'un texte d'Excel 5 / 95, lus dans la page de codes du
     classeur (Windows-1252 si elle est absente ou inconnue). */
  function decodeur8(page) {
    var table = PAGES_DOS[page];
    if (table) {
      return function (w, p, n) {
        var s = '';
        for (var i = 0; i < n; i++) s += w[p + i] < 128 ? String.fromCharCode(w[p + i]) : table.charAt(w[p + i] - 128);
        return s;
      };
    }
    var d;
    try { d = new TextDecoder(PAGES_DE_CODES[page] || 'windows-1252'); } catch (e) { d = new TextDecoder('windows-1252'); }
    return function (w, p, n) { return d.decode(w.subarray(p, p + n)); };
  }
  /* Un texte BIFF8 « compressé » : de l'Unicode dont l'octet de poids fort,
     nul, est omis — donc du Latin-1 exact, pas du Windows-1252. */
  function texteLatin1(w, p, n) {
    var s = '';
    for (var i = 0; i < n; i += 4096) s += String.fromCharCode.apply(null, w.subarray(p + i, p + Math.min(n, i + 4096)));
    return s;
  }
  /* Un texte BIFF8 « large » : des unités UTF-16, recopiées telles quelles.
     Pas de TextDecoder : un émoji (deux unités) coupé entre deux
     enregistrements CONTINUE deviendrait deux « � » ; ses deux moitiés,
     gardées, se rejoignent quand les morceaux sont mis bout à bout. */
  function texteUtf16(w, p, n) {
    var s = '', i;
    if (n < 16) {
      for (i = 0; i < n; i++) s += String.fromCharCode(w[p + 2 * i] | (w[p + 2 * i + 1] << 8));
      return s;
    }
    var u = new Uint16Array(n);
    for (i = 0; i < n; i++) u[i] = w[p + 2 * i] | (w[p + 2 * i + 1] << 8);
    for (i = 0; i < n; i += 4096) s += String.fromCharCode.apply(null, u.subarray(i, Math.min(n, i + 4096)));
    return s;
  }
  /* Une chaîne BIFF8 qui peut continuer dans les enregistrements CONTINUE
     qui suivent le sien (un enregistrement ne dépasse pas 8 224 octets) :
     `morceaux`, ses données puis celles de chaque CONTINUE, [début, fin[
     dans le flux. L'en-tête d'une chaîne et ce qui suit ses caractères (mises
     en forme, phonétique) passent d'un morceau au suivant sans rien de plus ;
     les caractères, eux, reprennent après un octet d'options qui redit leur
     largeur, un ou deux octets — elle peut changer en route. */
  function curseurBiff(w, morceaux) {
    var k = 0, p = morceaux[0][0], fin = morceaux[0][1];
    function suivant() {
      if (++k >= morceaux.length) throw erreur(ABIME_XLS);
      p = morceaux[k][0];
      fin = morceaux[k][1];
    }
    function octet() { while (p >= fin) suivant(); return w[p++]; }
    return {
      octet: octet,
      u16: function () { var a = octet(); return a | (octet() << 8); },
      u32: function () { var a = octet(), b1 = octet(), c1 = octet(); return a + b1 * 256 + c1 * 65536 + octet() * 16777216; },
      sauter: function (n) {
        while (n > 0) {
          while (p >= fin) suivant();
          var d = Math.min(n, fin - p);
          p += d;
          n -= d;
        }
      },
      caracteres: function (cch, larges) {
        var parts = [], reste = cch, n;
        while (reste > 0) {
          if (p >= fin) { suivant(); if (p < fin) larges = w[p++] & 1; continue; }
          n = Math.min(reste, larges ? (fin - p) >> 1 : fin - p);
          if (!n) { p = fin; continue; }
          parts.push(larges ? texteUtf16(w, p, n) : texteLatin1(w, p, n));
          p += larges ? 2 * n : n;
          reste -= n;
        }
        return parts.length === 1 ? parts[0] : parts.join('');
      },
      fini: function () { return p >= fin && k + 1 >= morceaux.length; }
    };
  }
  /* La table des textes partagés (SST) : chaque cellule LABELSST y appelle
     son texte par son rang. Lue par tranches — elle peut en compter des
     centaines de milliers — : avancer(ms) rend true une fois tout lu. Un
     texte riche porte ses mises en forme après ses caractères (4 octets
     chacune), un texte étendu sa lecture phonétique (cbExtRst octets) :
     sautées, même à cheval sur deux enregistrements. */
  function lecteurSst(w, morceaux) {
    var c = curseurBiff(w, morceaux), chaines = [], total;
    c.sauter(4);
    total = c.u32();
    return {
      chaines: chaines,
      avancer: function (budget) {
        var t0 = Date.now(), n = 0;
        while (chaines.length < total && !c.fini()) {
          var cch = c.u16(), options = c.octet();
          var runs = options & 8 ? c.u16() : 0, etendu = options & 4 ? c.u32() : 0;
          chaines.push(c.caracteres(cch, options & 1));
          if (runs || etendu) c.sauter(4 * runs + etendu);
          if (++n % 2000 === 0 && Date.now() - t0 > budget) return false;
        }
        return true;
      }
    };
  }
  /* Les lignes d'un onglet .xls, telles qu'elles arrivent : Excel les écrit
     dans l'ordre, chaque ligne part au collecteur dès que la suivante
     commence. Une ligne qui reviendrait en arrière (`desordre`) arrête tout :
     l'onglet est alors relu par puitsEnOrdre. */
  function puitsEnFlux(c) {
    var rang = -1, valeurs = null, sansValeur = null, fusions = [];
    var puits = { arret: false, desordre: false };
    function vider() {
      if (!valeurs) return;
      for (var j = 0; j < valeurs.length; j++) if (valeurs[j] === undefined) valeurs[j] = '';
      var v = valeurs;
      valeurs = null;
      if (!puits.arret && c.ligne(rang + 1, v, sansValeur) === false) puits.arret = true;
    }
    puits.cellule = function (r, col, v) {
      if (r !== rang) {
        if (r < rang) { puits.desordre = puits.arret = true; return; }
        vider();
        rang = r;
        valeurs = [];
        sansValeur = null;
      }
      valeurs[col] = v;
    };
    puits.sansCalcul = function (r, col) { if (r === rang && valeurs) (sansValeur || (sansValeur = [])).push(col); };
    puits.fusion = function (l1, l2, c1, c2) { fusions.push([l1, l2, c1, c2]); };
    /* Les fusions arrivent après les cellules ; le collecteur les trie
       d'après la ligne d'en-têtes, connue à ce moment-là. */
    puits.fin = function () {
      vider();
      if (puits.arret) return;
      fusions.forEach(function (f) { if (f[1] >= f[0] && f[3] >= f[2]) c.fusion(f[0] + 1, f[2] + 1, f[1] - f[0] + 1, f[3] - f[2] + 1); });
    };
    return puits;
  }
  function puitsEnOrdre(c) {
    var lignes = {}, rangs = [], fusions = [];
    return {
      arret: false, desordre: false,
      cellule: function (r, col, v) {
        var x = lignes[r];
        if (!x) { x = lignes[r] = { v: [], s: null }; rangs.push(r); }
        x.v[col] = v;
      },
      sansCalcul: function (r, col) { var x = lignes[r]; if (x) (x.s || (x.s = [])).push(col); },
      fusion: function (l1, l2, c1, c2) { fusions.push([l1, l2, c1, c2]); },
      fin: function () {
        rangs.sort(function (a, b) { return a - b; });
        for (var i = 0; i < rangs.length; i++) {
          var x = lignes[rangs[i]];
          for (var j = 0; j < x.v.length; j++) if (x.v[j] === undefined) x.v[j] = '';
          if (c.ligne(rangs[i] + 1, x.v, x.s) === false) return;
        }
        fusions.forEach(function (f) { if (f[1] >= f[0] && f[3] >= f[2]) c.fusion(f[0] + 1, f[2] + 1, f[1] - f[0] + 1, f[3] - f[2] + 1); });
      }
    };
  }
  // ------------------------------------------------------------ .xls chiffré sans mot de passe à l'ouverture
  /* Excel chiffre un .xls dont seule la structure est protégée, ou qui n'a
     de mot de passe que pour la modification, avec un mot de passe par
     défaut, toujours le même : « VelvetSweatshop » (MS-XLS 2.2.10). Excel et
     LibreOffice l'ouvrent sans rien demander ; la fenêtre aussi, donc. Le
     chiffrement est du RC4, sa clé tirée du mot de passe par MD5 (« RC4 »
     d'Excel 97) ou par SHA-1 (« RC4 CryptoAPI », Excel 2002 et suivants) :
     les trois, écrits ici en quelques lignes. Un vrai mot de passe, lui,
     reste illisible (PROTEGE). */
  var MOT_DE_PASSE_PAR_DEFAUT = 'VelvetSweatshop';
  var MD5_K = (function () { var k = []; for (var i = 0; i < 64; i++) k[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0; return k; })();
  var MD5_R = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
  /* Le message `m` complété comme le veulent MD5 et SHA-1 : un octet 0x80,
     des zéros, puis sa longueur en bits sur 8 octets (petit-boutiste pour
     MD5, gros-boutiste pour SHA-1). */
  function completer(m, gros) {
    var n = m.length, lg = ((n + 8) >> 6 << 6) + 64, x = new Uint8Array(lg), bits = n * 8;
    x.set(m);
    x[n] = 0x80;
    for (var i = 0; i < 4; i++) x[gros ? lg - 1 - i : lg - 8 + i] = (bits >>> (8 * i)) & 255;
    return x;
  }
  function md5(m) {
    var x = completer(m, false), h = [0x67452301, 0xEFCDAB89 | 0, 0x98BADCFE | 0, 0x10325476], w = [], i, o;
    for (o = 0; o < x.length; o += 64) {
      for (i = 0; i < 16; i++) w[i] = x[o + 4 * i] | (x[o + 4 * i + 1] << 8) | (x[o + 4 * i + 2] << 16) | (x[o + 4 * i + 3] << 24);
      var a = h[0], b = h[1], c = h[2], d = h[3], f, g, t, s, r;
      for (i = 0; i < 64; i++) {
        if (i < 16) { f = (b & c) | (~b & d); g = i; }
        else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) & 15; }
        else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) & 15; }
        else { f = c ^ (b | ~d); g = (7 * i) & 15; }
        r = MD5_R[(i >> 4) * 4 + (i & 3)];
        s = (a + f + MD5_K[i] + w[g]) | 0;
        t = d; d = c; c = b;
        b = (b + ((s << r) | (s >>> (32 - r)))) | 0;
        a = t;
      }
      h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
    }
    var out = new Uint8Array(16);
    for (i = 0; i < 16; i++) out[i] = (h[i >> 2] >>> (8 * (i & 3))) & 255;
    return out;
  }
  function sha1(m) {
    var x = completer(m, true), h = [0x67452301, 0xEFCDAB89 | 0, 0x98BADCFE | 0, 0x10325476, 0xC3D2E1F0 | 0], w = [], i, o, t;
    for (o = 0; o < x.length; o += 64) {
      for (i = 0; i < 16; i++) w[i] = (x[o + 4 * i] << 24) | (x[o + 4 * i + 1] << 16) | (x[o + 4 * i + 2] << 8) | x[o + 4 * i + 3];
      for (i = 16; i < 80; i++) { t = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]; w[i] = (t << 1) | (t >>> 31); }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f, k;
      for (i = 0; i < 80; i++) {
        if (i < 20) { f = (b & c) | (~b & d); k = 0x5A827999; }
        else if (i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC | 0; }
        else { f = b ^ c ^ d; k = 0xCA62C1D6 | 0; }
        t = (((a << 5) | (a >>> 27)) + f + e + k + w[i]) | 0;
        e = d; d = c; c = (b << 30) | (b >>> 2); b = a; a = t;
      }
      h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0; h[4] = (h[4] + e) | 0;
    }
    var out = new Uint8Array(20);
    for (i = 0; i < 20; i++) out[i] = (h[i >> 2] >>> (24 - 8 * (i & 3))) & 255;
    return out;
  }
  /* RC4 : la suite d'octets qui, par OU exclusif, chiffre et déchiffre. */
  function rc4(cle) {
    var s = new Uint8Array(256), i, j = 0, t;
    for (i = 0; i < 256; i++) s[i] = i;
    for (i = 0; i < 256; i++) { j = (j + s[i] + cle[i % cle.length]) & 255; t = s[i]; s[i] = s[j]; s[j] = t; }
    i = j = 0;
    return function (n) {
      var o = new Uint8Array(n);
      for (var k = 0; k < n; k++) {
        i = (i + 1) & 255; j = (j + s[i]) & 255;
        t = s[i]; s[i] = s[j]; s[j] = t;
        o[k] = s[(s[i] + s[j]) & 255];
      }
      return o;
    };
  }
  function concat(a, b) { var x = new Uint8Array(a.length + b.length); x.set(a); x.set(b, a.length); return x; }
  function petitBoutiste32(n) { return new Uint8Array([n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]); }
  function egaux(a, b) { if (a.length !== b.length) return false; for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false; return true; }
  function enUtf16(t) { var o = new Uint8Array(2 * t.length); for (var i = 0; i < t.length; i++) { o[2 * i] = t.charCodeAt(i) & 255; o[2 * i + 1] = t.charCodeAt(i) >> 8; } return o; }
  /* La clé du bloc n (1 024 octets du flux chacun) pour le mot de passe par
     défaut, d'après l'enregistrement FILEPASS (ses données : [d, fin[) ; null
     si ce n'est pas lui — un vrai mot de passe —, ou un chiffrement inconnu. */
  function cleParDefaut(w, d, fin) {
    if (fin - d < 6 || u16(w, d) !== 1) return null;
    var maj = u16(w, d + 2), min = u16(w, d + 4), mdp = enUtf16(MOT_DE_PASSE_PAR_DEFAUT), cle, verif, empreinte, taille;
    if (maj === 1 && min === 1 && fin - d >= 54) {
      /* RC4 d'Excel 97 : MD5. */
      var sel = w.subarray(d + 6, d + 22), h0 = md5(mdp).subarray(0, 5), inter = new Uint8Array(21 * 16);
      for (var k = 0; k < 16; k++) { inter.set(h0, 21 * k); inter.set(sel, 21 * k + 5); }
      var h1 = md5(inter).subarray(0, 5);
      cle = function (n) { return md5(concat(h1, petitBoutiste32(n))); };
      verif = w.subarray(d + 22, d + 38);
      empreinte = w.subarray(d + 38, d + 54);
      var flux = rc4(cle(0)), v = flux(16), e = flux(16), x;
      for (x = 0; x < 16; x++) { v[x] ^= verif[x]; e[x] ^= empreinte[x]; }
      return egaux(md5(v), e) ? cle : null;
    }
    if (maj >= 2 && maj <= 4 && min === 2 && fin - d >= 14) {
      /* RC4 CryptoAPI : SHA-1, une clé de 40 à 128 bits. */
      var tete = u32(w, d + 10), q = d + 14 + tete;
      if (tete < 32 || q + 60 > fin) return null;
      taille = u32(w, d + 14 + 16) || 40;
      if (taille % 8 || taille < 40 || taille > 128) return null;
      var sel2 = w.subarray(q + 4, q + 20), h = sha1(concat(sel2, mdp));
      cle = function (n) {
        var hf = sha1(concat(h, petitBoutiste32(n)));
        if (taille === 40) { var c40 = new Uint8Array(16); c40.set(hf.subarray(0, 5)); return c40; }
        return hf.subarray(0, taille / 8);
      };
      verif = w.subarray(q + 20, q + 36);
      empreinte = w.subarray(q + 40, q + 60);
      var flux2 = rc4(cle(0)), v2 = flux2(16), e2 = flux2(20), y;
      for (y = 0; y < 16; y++) v2[y] ^= verif[y];
      for (y = 0; y < 20; y++) e2[y] ^= empreinte[y];
      return egaux(sha1(v2), e2) ? cle : null;
    }
    return null;
  }
  /* Déchiffre le flux `w` sur place, après le FILEPASS (qui finit en
     `depart`) : les données de chaque enregistrement, octet du flux par
     octet du flux — la suite RC4 avance aussi sous les en-têtes, et repart
     d'une nouvelle clé tous les 1 024 octets —, sauf celles que le format
     laisse en clair (BOF, FILEPASS, INTERFACEHDR…, et la place de chaque
     onglet dans BOUNDSHEET). Par tranches : un gros fichier ne fige pas la
     fenêtre. */
  var EN_CLAIR_XLS = { 0x0809: 1, 0x002F: 1, 0x0194: 1, 0x0195: 1, 0x00E1: 1, 0x0196: 1, 0x0138: 1 };
  function dechiffrerXls(w, cle, depart) {
    var p = depart, bloc = -1, suite = null;
    function xor(a, b) {
      while (a < b) {
        var n = Math.floor(a / 1024);
        if (n !== bloc) { bloc = n; suite = rc4(cle(n))(1024); }
        for (var fin = Math.min(b, (n + 1) * 1024); a < fin; a++) w[a] ^= suite[a & 1023];
      }
    }
    function tranche() {
      var t0 = Date.now(), k = 0;
      while (p + 4 <= w.length) {
        var t = u16(w, p), d = p + 4, fin = d + u16(w, p + 2);
        if (fin > w.length) break;
        if (!EN_CLAIR_XLS[t]) xor(t === 0x0085 ? Math.min(fin, d + 4) : d, fin);
        p = fin;
        if (++k % 2000 === 0 && Date.now() - t0 > 40) {
          progres(0.05 * p / w.length, 'Ouverture du classeur (protégé, sans mot de passe à l’ouverture)…');
          return souffle().then(tranche);
        }
      }
      return null;
    }
    return Promise.resolve().then(tranche);
  }
  /* « General » a des noms locaux (Standard, Standaard, Allmänt, Yleinen,
     Standardowy, Общий…), que formeDuFormat prendrait pour une date (le
     « d » de « Standard ») : un code fait de lettres seules — rien d'un
     format de nombre (0 # ? @, guillemets, crochets, séparateurs) — qui
     n'est pas une suite de jetons de date ou d'heure (« dddd », « yyyy »). */
  function nomDeGeneral(code) {
    var t = String(code).trim();
    if (/^(general|g\/standard)$/i.test(t)) return true;
    return /^[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u052F]{2,}$/.test(t) && !/^[dmyhsbeag]+$/i.test(t);
  }
  /* Lit le flux d'un classeur .xls (`w`) comme lireXlsx lit un .xlsx : les
     onglets visibles d'abord, le premier qui porte l'en-tête l'emporte ; les
     cellules vont au collecteur, chaque nombre écrit comme Excel l'affiche
     — formeDuFormat et texteNombre, les mêmes que pour un .xlsx —, les
     fusions ensuite. La lecture rend la main à la fenêtre toutes les
     quelques milliers d'enregistrements : un gros fichier ne la fige pas. */
  function lireBiff(w, toutes) {
    if (w.length < 8) throw erreur(ABIME_XLS);
    var t = u16(w, 0), l = u16(w, 2);
    if (t === 0x0009 || t === 0x0209 || t === 0x0409) throw erreur(TRES_ANCIEN);
    if (t !== 0x0809 || l < 4 || 4 + l > w.length || u16(w, 6) !== 0x0005) throw erreur(ABIME_XLS);
    var vers = u16(w, 4), biff = vers === 0x0500 || (vers !== 0x0600 && l < 16) ? 5 : 8;
    /* Un FILEPASS dans la partie commune : le classeur est chiffré. Avec le
       mot de passe par défaut d'Excel, il est déchiffré, puis lu comme un
       autre ; sinon, il est protégé. */
    for (var q = 4 + l; q + 4 <= w.length; q += 4 + u16(w, q + 2)) {
      var tq = u16(w, q);
      if (tq === 0x000A || tq === 0x0809) break;
      if (tq === 0x002F) {
        var finFp = Math.min(w.length, q + 4 + u16(w, q + 2)), cle = biff === 8 ? cleParDefaut(w, q + 4, finFp) : null;
        if (!cle) throw erreur(PROTEGE);
        return dechiffrerXls(w, cle, finFp).then(function () { return lireBiffClair(w, toutes, biff, l); });
      }
    }
    return lireBiffClair(w, toutes, biff, l);
  }
  function lireBiffClair(w, toutes, biff, l) {
    var t;
    var vue = new DataView(w.buffer, w.byteOffset, w.byteLength), tampon = new DataView(new ArrayBuffer(8));
    var page = biff === 8 ? 1200 : 1252, en1904 = false, formats = {}, xfs = [], onglets = [], bruts = [], sstMorceaux = null, p = 4 + l, d, fin;
    for (;;) {
      if (p + 4 > w.length) throw erreur(ABIME_XLS);
      t = u16(w, p);
      l = u16(w, p + 2);
      d = p + 4;
      fin = d + l;
      if (fin > w.length) throw erreur(ABIME_XLS);
      p = fin;
      if (t === 0x000A) break;
      if (t === 0x0042 && l >= 2) page = u16(w, d);
      else if (t === 0x0022 && l >= 2) en1904 = u16(w, d) === 1;
      else if (t === 0x00E0 && l >= 4) xfs.push(u16(w, d + 2));
      else if ((t === 0x041E || t === 0x001E) && l >= 2) bruts.push({ t: t, d: d, fin: fin });
      else if (t === 0x0085 && l >= 7) onglets.push({ pos: u32(w, d), cache: (w[d + 4] & 3) !== 0, type: w[d + 5], d: d + 6, fin: fin });
      else if (t === 0x00FC && l >= 8) {
        sstMorceaux = [[d, fin]];
        while (p + 4 <= w.length && u16(w, p) === 0x003C) {
          var lc = u16(w, p + 2);
          if (p + 4 + lc > w.length) throw erreur(ABIME_XLS);
          sstMorceaux.push([p + 4, p + 4 + lc]);
          p += 4 + lc;
        }
      }
    }
    var dec8 = decodeur8(page);
    /* Un texte court, borné à son enregistrement : en BIFF5, des octets dans
       la page de codes ; en BIFF8, un octet d'options (la largeur) puis les
       caractères. */
    function texte8(debut, borne, cch) { return dec8(w, debut, Math.max(0, Math.min(cch, borne - debut))); }
    function texteU(debut, borne, cch) {
      var larges = w[debut] & 1, n = Math.max(0, Math.min(cch, larges ? (borne - debut - 1) >> 1 : borne - debut - 1));
      return larges ? texteUtf16(w, debut + 1, n) : texteLatin1(w, debut + 1, n);
    }
    onglets.forEach(function (o) { o.nom = biff === 8 ? texteU(o.d + 1, o.fin, w[o.d]) : texte8(o.d + 1, o.fin, w[o.d]); });
    var implicite = 0;
    bruts.forEach(function (x) {
      var id, code, n = x.fin - x.d;
      if (biff === 8) {
        if (x.t !== 0x041E || n < 5) return;
        id = u16(w, x.d);
        code = texteU(x.d + 4, x.fin, u16(w, x.d + 2));
      } else if (n >= 3 && (x.t === 0x041E || n === 3 + w[x.d + 2])) {
        id = u16(w, x.d);
        code = texte8(x.d + 3, x.fin, w[x.d + 2]);
      } else {
        /* Le FORMAT d'Excel 2 et 3, sans numéro : les formats se suivent. */
        id = implicite++;
        code = texte8(x.d + 1, x.fin, w[x.d]);
      }
      formats[id] = id === 0 || nomDeGeneral(code) ? 'General' : code;
    });
    var styles = { formats: formats, xfs: xfs }, formes = {}, sst = [];
    function forme(x) { return formes[x] || (formes[x] = formeDuFormat(styles, x)); }
    function nombre(v, x) { return texteNombre(String(v), forme(x), en1904); }
    /* Un RK : un entier sur 30 bits, ou les 30 bits de tête d'un nombre à
       virgule — et, dans les deux cas, peut-être à diviser par cent. */
    function rk(o) {
      var x = w[o] | (w[o + 1] << 8) | (w[o + 2] << 16) | (w[o + 3] << 24), v;
      if (x & 2) v = x >> 2;
      else {
        tampon.setInt32(0, 0, true);
        tampon.setInt32(4, x & -4, true);
        v = tampon.getFloat64(0, true);
      }
      return x & 1 ? v / 100 : v;
    }
    /* Un enregistrement et les CONTINUE qui le suivent : ses morceaux. */
    function avecSuites(debut, borne, apres) {
      var m = [[debut, borne]], q = apres;
      while (q + 4 <= w.length && u16(w, q) === 0x003C && q + 4 + u16(w, q + 2) <= w.length) {
        m.push([q + 4, q + 4 + u16(w, q + 2)]);
        q += 4 + u16(w, q + 2);
      }
      return m;
    }
    /* Le texte d'une cellule LABEL ou RSTRING, ou d'un résultat de formule
       (STRING) : en BIFF8 une chaîne Unicode qui peut continuer plus loin,
       en BIFF5 des octets dans la page de codes. */
    function texteCellule(debut, borne, apres) {
      if (biff === 5) return texte8(debut + 2, borne, u16(w, debut));
      var c = curseurBiff(w, avecSuites(debut, borne, apres)), cch = c.u16();
      /* Un texte vide : certains programmes n'écrivent pas l'octet d'options
         qui suivrait — le lire prendrait l'enregistrement pour abîmé. */
      if (!cch) return '';
      return c.caracteres(cch, c.octet() & 1);
    }
    /* Un onglet, enregistrement après enregistrement, de son BOF à son EOF :
       les cellules vont au puits, les sous-parties (un graphique posé sur
       l'onglet, avec ses propres BOF et EOF) sont sautées. Rend false pour
       un onglet qui n'a pas de cellules (graphique, macros). */
    function parcourir(o, puits, c) {
      var pos = o.pos, profondeur = 0, attente = null;
      if (pos + 8 > w.length || u16(w, pos) !== 0x0809) throw erreur(ABIME_XLS);
      if (u16(w, pos + 6) !== 0x0010) return Promise.resolve(false);
      pos += 4 + u16(w, pos + 2);
      function veut(col) { return !c.voulues || c.voulues[col]; }
      function tranche() {
        var t0 = Date.now(), n = 0, ty, lg, db, fn, r, col, x, k, nb;
        for (;;) {
          if (++n % 4000 === 0 && Date.now() - t0 > 40) {
            progres(0.06 + 0.9 * pos / w.length);
            return souffle().then(tranche);
          }
          if (pos + 4 > w.length) throw erreur(ABIME_XLS);
          ty = u16(w, pos);
          lg = u16(w, pos + 2);
          db = pos + 4;
          fn = db + lg;
          if (fn > w.length) throw erreur(ABIME_XLS);
          pos = fn;
          if (ty === 0x0809) { profondeur++; continue; }
          if (ty === 0x000A) { if (profondeur) { profondeur--; continue; } break; }
          if (profondeur) continue;
          if (ty === 0x0207) {
            if (attente) { puits.cellule(attente.r, attente.col, texteCellule(db, fn, pos)); attente = null; }
            continue;
          }
          if (ty === 0x00E5) {
            nb = lg >= 2 ? u16(w, db) : 0;
            for (k = 0; k < nb && db + 10 + 8 * k <= fn; k++) puits.fusion(u16(w, db + 2 + 8 * k), u16(w, db + 4 + 8 * k), u16(w, db + 6 + 8 * k), u16(w, db + 8 + 8 * k));
            continue;
          }
          if (!CELLULES_XLS[ty] || lg < 6) continue;
          /* Une formule qui disait un texte sans l'enregistrement STRING qui le
             porte : une formule sans valeur calculée. */
          if (attente) { puits.sansCalcul(attente.r, attente.col); attente = null; }
          r = u16(w, db);
          col = u16(w, db + 2);
          x = u16(w, db + 4);
          if (ty === 0x00BD) {
            nb = Math.floor((lg - 6) / 6);
            for (k = 0; k < nb; k++) if (veut(col + k)) puits.cellule(r, col + k, nombre(rk(db + 6 + 6 * k), u16(w, db + 4 + 6 * k)));
          } else if (ty === 0x00BE) {
            nb = (lg - 6) >> 1;
            for (k = 0; k < nb; k++) if (veut(col + k)) puits.cellule(r, col + k, '');
          } else if (!veut(col)) {
            /* une colonne que l'export SEE ne garde pas */
          } else if (ty === 0x0203) {
            if (lg >= 14) puits.cellule(r, col, nombre(vue.getFloat64(db + 6, true), x));
          } else if (ty === 0x027E) {
            if (lg >= 10) puits.cellule(r, col, nombre(rk(db + 6), x));
          } else if (ty === 0x00FD) {
            if (lg >= 10) { var s = sst[u32(w, db + 6)]; puits.cellule(r, col, s === undefined ? '' : s); }
          } else if (ty === 0x0204 || ty === 0x00D6) {
            if (lg >= 8) puits.cellule(r, col, texteCellule(db + 6, fn, pos));
          } else if (ty === 0x0205) {
            if (lg >= 8) puits.cellule(r, col, w[db + 7] ? ERREURS_XLS[w[db + 6]] || '#N/A' : w[db + 6] ? 'VRAI' : 'FAUX');
          } else if (ty === 0x0201) {
            puits.cellule(r, col, '');
          } else if (FORMULES_XLS[ty] && lg >= 20) {
            /* Le résultat gardé de la formule : un nombre, ou — les deux
               derniers octets à FFFF — un texte (dans le STRING qui suit),
               un booléen, une erreur, un texte vide. */
            if (u16(w, db + 12) !== 0xFFFF) puits.cellule(r, col, nombre(vue.getFloat64(db + 6, true), x));
            else if (w[db + 6] === 0) { puits.cellule(r, col, ''); attente = { r: r, col: col }; }
            else if (w[db + 6] === 1) puits.cellule(r, col, w[db + 8] ? 'VRAI' : 'FAUX');
            else if (w[db + 6] === 2) puits.cellule(r, col, ERREURS_XLS[w[db + 8]] || '#N/A');
            else puits.cellule(r, col, '');
          }
          if (puits.arret) break;
        }
        if (attente && !puits.arret) puits.sansCalcul(attente.r, attente.col);
        puits.fin();
        return true;
      }
      return Promise.resolve().then(tranche);
    }
    function lireOngletXls(o) {
      var c = collecteur(toutes), puits = puitsEnFlux(c);
      return parcourir(o, puits, c).then(function (lu) {
        if (lu === false) return null;
        if (!puits.desordre) return c;
        /* Des lignes dans le désordre (Excel ne le fait pas, d'autres
           programmes si) : l'onglet est relu, ses lignes rangées avant de
           passer au collecteur. */
        var c2 = collecteur(toutes);
        return parcourir(o, puitsEnOrdre(c2), c2).then(function () { return c2; });
      });
    }
    var liste = onglets.filter(function (o) { return o.type === 0; });
    liste.sort(function (a, b) { return (a.cache ? 1 : 0) - (b.cache ? 1 : 0); });
    var etapeSst = Promise.resolve();
    if (biff === 8 && sstMorceaux) {
      var lecteur = lecteurSst(w, sstMorceaux);
      sst = lecteur.chaines;
      progres(0.05, 'Lecture des textes du classeur…');
      var tranche = function () { if (!lecteur.avancer(60)) return souffle().then(tranche); };
      etapeSst = etapeSst.then(tranche);
    }
    return etapeSst.then(function () {
      var meilleur = null, tropBas = null, i = 0;
      function suivant() {
        if (i >= liste.length) return { trouve: false, meilleur: meilleur, tropBas: tropBas, onglets: liste.map(function (o) { return o.nom; }) };
        var o = liste[i++];
        progres(0.06 + 0.9 * o.pos / w.length, 'Lecture de l’onglet « ' + o.nom + ' »…');
        return lireOngletXls(o).then(function (c) {
          if (!c) return suivant();
          if (c.sorte) { c.onglet = o.nom; c.trouve = true; c.format = biff === 8 ? 'xls' : 'xls95'; return c; }
          if (c.tropBas && !tropBas) { tropBas = c.tropBas; tropBas.onglet = o.nom; }
          if (!meilleur || c.meilleur.portes > meilleur.portes) { meilleur = c.meilleur; meilleur.onglet = o.nom; }
          return suivant();
        });
      }
      return suivant();
    });
  }
  /* Un fichier OLE : un vrai .xls — ou un .xlsx chiffré (« EncryptionInfo »),
     protégé par un mot de passe ou une étiquette de confidentialité. */
  function lireOle(f, toutes) {
    var nomXlsx = /\.xls[xmb]$/i.test(f.name);
    if (f.size > P.maxOctetsXls) throw nomXlsx ? erreur(PROTEGE) : tropGros(f);
    progres(0.02, 'Ouverture du classeur…');
    return lireOctets(f, 0, f.size).then(function (b) {
      var ole;
      /* Un .xlsx qui est un conteneur OLE est chiffré : même illisible, c'est
         ce qu'il est presque toujours. */
      try { ole = ouvrirOle(b); } catch (e) { throw nomXlsx && e && e.pourLecteur ? erreur(PROTEGE) : e; }
      if (ole.nomme(['encryptioninfo', 'encryptedpackage'])) throw erreur(PROTEGE);
      var entree = ole.nomme(['workbook', 'book']);
      if (!entree) throw erreur(nomXlsx ? PROTEGE : ole.repertoireCasse ? ABIME_XLS : SANS_CLASSEUR);
      var w = ole.flux(entree);
      b = null;
      ole = null;
      progres(0.05, 'Lecture du classeur…');
      return lireBiff(w, toutes);
    }).catch(abimeSiHorsLimites);
  }
  /* Un flux BIFF sans conteneur (certains vieux outils l'écrivent ainsi). */
  function lireBiffNu(f, toutes) {
    if (f.size > P.maxOctetsXls) throw tropGros(f);
    progres(0.02, 'Ouverture du classeur…');
    return lireOctets(f, 0, f.size).then(function (b) { return lireBiff(b, toutes); }).catch(abimeSiHorsLimites);
  }
  /* Un octet lu hors du flux (un DataView qui proteste) : la structure
     promettait plus que le fichier n'en a. */
  function abimeSiHorsLimites(e) {
    if (e instanceof RangeError) throw erreur(ABIME_XLS);
    throw e;
  }

  // ------------------------------------------------------------ page web archivée (.mht, ou .xls qui en est une)
  /* « Page web, fichier unique » : un message MIME, comme un courriel, dont
     une partie au moins est la page HTML — en quoted-printable ou en
     base64, avec son jeu de caractères. Un export web la nomme parfois .xls ;
     Excel lui-même y range une page par onglet, après un cadre sans tableau.
     Chaque page passe au lecteur de pages web : la première qui porte
     l'en-tête l'emporte. */
  function entetesMime(texte) {
    var h = {};
    texte.replace(/\r?\n[ \t]+/g, ' ').split(/\r?\n/).forEach(function (l) {
      var m = /^([\w-]+)[ \t]*:[ \t]*(.*)$/.exec(l);
      if (m && h[m[1].toLowerCase()] === undefined) h[m[1].toLowerCase()] = m[2].trim();
    });
    return h;
  }
  function parametreMime(valeur, nom) {
    var m = new RegExp(';\\s*' + nom + '\\s*=\\s*(?:"([^"]*)"|([^;\\s]+))', 'i').exec(valeur || '');
    return m ? (m[1] !== undefined ? m[1] : m[2]) : '';
  }
  /* Le décodage d'une page web archivée se fait par tranches de quelques
     mégaoctets, la fenêtre respirant entre elles (souffle) : un export de
     80 Mo, décodé d'un bloc, la figeait une à deux secondes. */
  var TRANCHE_MHT = 4194304;
  /* Fait `pas(debut, fin)` sur [0, n[ par tranches de `taille` (que `coupe`
     peut avancer jusqu'à une frontière sûre), en rendant la main toutes les
     40 ms ; `avance(part)` suit la progression. */
  function parTranches(n, taille, pas, avance, coupe) {
    var p = 0;
    function tranche() {
      var t0 = Date.now();
      while (p < n) {
        var q = Math.min(n, p + taille);
        if (coupe && q < n) q = coupe(q);
        pas(p, q);
        p = q;
        if (p < n && Date.now() - t0 > 40) {
          if (avance) avance(p / n);
          return souffle().then(tranche);
        }
      }
      return null;
    }
    return Promise.resolve().then(tranche);
  }
  /* Le fichier lu en entier, un caractère par octet (« x-user-defined ») :
     les positions dans le texte sont celles du fichier. */
  function texteParOctet(b) {
    var d = new TextDecoder('x-user-defined'), parts = [];
    return parTranches(b.length, TRANCHE_MHT, function (p, q) { parts.push(d.decode(b.subarray(p, q))); },
      function (x) { progres(0.02 + 0.02 * x); }).then(function () { return parts.join(''); });
  }
  /* Les pages HTML d'une page web archivée (son texte `t`, un caractère par
     octet) : [{ nom, entetes, debut, fin }], [debut, fin[ étant le corps de
     la page dans le fichier. */
  function pagesMhtml(t) {
    var pages = [];
    function separer(debut, borne) {
      var nl = /^\r?\n/.exec(t.slice(debut, debut + 2));
      if (nl) return { entetes: {}, debut: debut + nl[0].length, fin: borne };
      var re = /\r?\n\r?\n/g;
      re.lastIndex = debut;
      var x = re.exec(t);
      if (!x || x.index >= borne) return null;
      return { entetes: entetesMime(t.slice(debut, x.index)), debut: x.index + x[0].length, fin: borne };
    }
    function estPage(h) {
      var type = (h['content-type'] || '').toLowerCase();
      return type.indexOf('text/html') === 0 || type.indexOf('application/xhtml') === 0 || (!type && /\.html?$/i.test(h['content-location'] || ''));
    }
    function ajouterPage(x) {
      var lieu = (x.entetes['content-location'] || '').replace(/[?#].*$/, '');
      x.nom = lieu.replace(/^.*[\/\\]/, '') || 'page ' + (pages.length + 1);
      pages.push(x);
    }
    var haut = separer(t.search(/\S|$/), t.length);
    if (!haut) return pages;
    var type = haut.entetes['content-type'] || '';
    if (/^multipart\//i.test(type)) {
      var delim = '--' + parametreMime(type, 'boundary'), pos = delim.length > 2 ? t.indexOf(delim, haut.debut) : -1;
      while (pos !== -1) {
        if (t.substr(pos + delim.length, 2) === '--') break;
        var ligne = t.indexOf('\n', pos + delim.length);
        if (ligne === -1) break;
        var suite = t.indexOf('\n' + delim, ligne);
        var x = separer(ligne + 1, suite === -1 ? t.length : t.charAt(suite - 1) === '\r' ? suite - 1 : suite);
        if (x && estPage(x.entetes)) ajouterPage(x);
        pos = suite === -1 ? -1 : suite + 1;
      }
    } else if (estPage(haut.entetes) || !type) ajouterPage(haut);
    return pages;
  }
  function chiffreHexa(o) { return o >= 48 && o <= 57 ? o - 48 : o >= 65 && o <= 70 ? o - 55 : o >= 97 && o <= 102 ? o - 87 : -1; }
  function deQuotedPrintable(o, out, n) {
    var i = 0, j;
    while (i < o.length) {
      if (o[i] === 61) {
        /* « = » en fin de ligne (des blancs après lui compris) : la ligne continue. */
        for (j = i + 1; o[j] === 32 || o[j] === 9; j++) { /* blancs */ }
        if (o[j] === 13 && o[j + 1] === 10) { i = j + 2; continue; }
        if (o[j] === 10 || j >= o.length) { i = j + 1; continue; }
        if (chiffreHexa(o[i + 1]) >= 0 && chiffreHexa(o[i + 2]) >= 0) { out[n++] = chiffreHexa(o[i + 1]) * 16 + chiffreHexa(o[i + 2]); i += 3; continue; }
      }
      out[n++] = o[i++];
    }
    return n;
  }
  /* Les octets d'une page, son codage de transfert défait, par tranches :
     en quoted-printable, chaque tranche finit sur une fin de ligne (un
     « =XX » ou un « = » de fin de ligne n'y est jamais coupé) ; en base64,
     les caractères utiles qui ne font pas un groupe de quatre passent à la
     tranche suivante. */
  function octetsDePage(b, x) {
    var codage = (x.entetes['content-transfer-encoding'] || '').toLowerCase(), o = b.subarray(x.debut, x.fin), n = 0, out;
    var avance = function (part) { progres(0.04 + 0.01 * part); };
    if (codage === 'quoted-printable') {
      out = new Uint8Array(o.length);
      return parTranches(o.length, TRANCHE_MHT, function (p, q) { n = deQuotedPrintable(o.subarray(p, q), out, n); }, avance,
        function (q) { var k = o.indexOf(10, q); return k === -1 ? o.length : k + 1; }).then(function () { return out.subarray(0, n); });
    }
    if (codage === 'base64') {
      var reste = '';
      out = new Uint8Array(Math.ceil(o.length * 3 / 4) + 3);
      return parTranches(o.length, TRANCHE_MHT, function (p, q) {
        var s = reste + texteLatin1(o, p, q - p).replace(/[^A-Za-z0-9+\/]/g, ''), plein = q >= o.length ? s.length : s.length - s.length % 4;
        reste = s.slice(plein);
        s = s.slice(0, plein);
        if (s.length % 4 === 1) s = s.slice(0, -1);
        var bin = atob(s);
        for (var i = 0; i < bin.length; i++) out[n++] = bin.charCodeAt(i);
      }, avance).then(function () { return out.subarray(0, n); });
    }
    return Promise.resolve(o);
  }
  /* Des octets lus dans un jeu de caractères, par tranches (le décodeur en
     flux garde un caractère coupé entre deux tranches) : les morceaux du
     texte. `fatal` : un octet impossible fait échouer la lecture. */
  function decoderParTranches(o, jeu, fatal) {
    var d = new TextDecoder(jeu, fatal ? { fatal: true } : {}), parts = [];
    return parTranches(o.length, TRANCHE_MHT, function (p, q) { parts.push(d.decode(o.subarray(p, q), { stream: true })); },
      function (part) { progres(0.045 + 0.005 * part); }).then(function () { parts.push(d.decode()); return parts; });
  }
  /* Le texte d'une page (ses morceaux) : son codage de transfert défait, puis
     lu dans son jeu de caractères — celui de ses en-têtes, sinon celui de sa
     balise <meta>, sinon de l'UTF-8 s'il en est, sinon du Windows-1252. */
  function texteDePage(b, x) {
    return octetsDePage(b, x).then(function (o) {
      var jeu = parametreMime(x.entetes['content-type'], 'charset');
      if (!jeu) {
        var m = /<meta[^>]+charset\s*=\s*["']?\s*([\w.:-]+)/i.exec(texteLatin1(o, 0, Math.min(o.length, 4096)));
        if (m) jeu = m[1];
      }
      if (jeu) {
        try { new TextDecoder(jeu.trim()); return decoderParTranches(o, jeu.trim(), false); } catch (e) { /* jeu inconnu du navigateur : on devine */ }
      }
      return decoderParTranches(o, 'utf-8', true).catch(function () { return decoderParTranches(o, 'windows-1252', false); });
    });
  }
  function lireMhtml(f, toutes) {
    if (f.size > P.maxOctetsXls) throw tropGros(f);
    progres(0.02, 'Ouverture de la page web archivée…');
    return lireOctets(f, 0, f.size).then(function (b) {
      return texteParOctet(b).then(function (t) {
        var pages = pagesMhtml(t), i = 0, meilleur = null, tropBas = null;
        t = null;
        if (!pages.length) throw erreur('Cette page web archivée ne renferme aucune page HTML lisible : demander l’export en .xlsx, en .xls ou en .csv.');
        function suivante() {
          if (i >= pages.length) return { trouve: false, meilleur: meilleur, tropBas: tropBas, onglets: pages.map(function (x) { return x.nom; }) };
          var pg = pages[i++], c = collecteur(toutes), analyse = analyseurHtml(c);
          progres(0.04 + 0.9 * (i - 1) / pages.length, 'Lecture de « ' + pg.nom + ' »…');
          return texteDePage(b, pg).then(function (parts) {
            /* Les morceaux passent à la lecture des lignes par tranches de 256 Ko. */
            var k = 0, pos = 0, total = 0, lus = 0;
            parts.forEach(function (x) { total += x.length; });
            function morceau() {
              var t0 = Date.now();
              while (k < parts.length) {
                var x = parts[k], finMorceau = Math.min(x.length, pos + 262144);
                var dernier = finMorceau === x.length && k === parts.length - 1;
                if (analyse(x.slice(pos, finMorceau), dernier) === false) return c;
                lus += finMorceau - pos;
                pos = finMorceau;
                if (pos >= x.length) { k++; pos = 0; }
                if (k < parts.length && Date.now() - t0 > 50) {
                  progres(0.05 + 0.9 * (i - 1 + lus / (total || 1)) / pages.length);
                  return souffle().then(morceau);
                }
              }
              return c;
            }
            return morceau();
          }).then(function () {
            if (c.sorte) { c.onglet = pg.nom; c.trouve = true; c.format = 'mhtml'; return c; }
            if (c.tropBas && !tropBas) { tropBas = c.tropBas; tropBas.onglet = pg.nom; }
            if (!meilleur || c.meilleur.portes > meilleur.portes) { meilleur = c.meilleur; meilleur.onglet = pg.nom; }
            return suivante();
          });
        }
        return suivante();
      });
    });
  }
  // ------------------------------------------------------------ envoi au classeur
  function appeler(nom, args) {
    return new Promise(function (ok, ko) {
      var r = google.script.run.withSuccessHandler(ok).withFailureHandler(function (e) {
        var x = erreur(e && e.message ? e.message : String(e));
        x.duServeur = true;
        ko(x);
      });
      r[nom].apply(r, [P.jeton].concat(args));
    });
  }
  /* Un appel qui échoue en route (classeur lent, réseau de l'entreprise) est
     renvoyé, deux fois au plus, après une pause : un lot s'écrit toujours aux
     mêmes lignes, un début retire l'onglet temporaire d'un début perdu, un
     archivage remplace la ligne de sa semaine, un PSN se réécrit tel quel —
     les renvoyer ne double rien. Les refus du serveur, eux, sont définitifs ;
     la fin n'est jamais renvoyée (elle a pu échanger les onglets). */
  var DEFINITIF = /a disparu|non reconnu|Geste refusé|Contrat introuvable|limite de Google Sheets|illisible|Lot vide|Lot trop grand|Lot sans colonne|Trop de colonnes|Rien à importer|Import incomplet|existe déjà|nom réservé|Nom trop long|pas de nom|seconde base|Sorte d.import|FEUILLE_DONNEES|n.est pas un PSN|Trop de PSN|PERMISSION_DENIED|reading from storage|autoris|authoriz/i;
  function appelerAvecReprise(nom, args, surReprise) {
    var essai = 0;
    function tenter() {
      return appeler(nom, args).catch(function (e) {
        if (essai >= P.pausesReprise.length || DEFINITIF.test(e.message)) throw e;
        var pause = P.pausesReprise[essai++];
        if (surReprise) surReprise(essai);
        return new Promise(function (ok) { setTimeout(ok, pause); }).then(tenter);
      });
    }
    return tenter();
  }
  /* Un bloc de lignes vers son onglet : le début (l'onglet temporaire), les
     lots, puis la fin, qui échange les onglets — avec, pour GATES, les
     cellules fusionnées à recréer. */
  function envoyer(cible, bloc, largeur, fusions, etat) {
    var total = bloc.length, feuille = null, envoyees = 0;
    var reprise = function (n) {
      progres(envoyees / total, 'Le classeur n’a pas répondu : nouvel essai (' + n + ' sur ' + P.pausesReprise.length + ')…');
    };
    progres(0, 'Préparation de l’onglet…');
    return appelerAvecReprise('importSecondeBaseDebut', [cible, largeur, total], reprise).then(function (d) {
      feuille = d.feuille;
      var i = 0;
      function lot() {
        if (i >= total) return null;
        var paquet = [], poids = 0, premiere = i + 1;
        while (i < total && paquet.length < P.maxLignesLot && poids < 900000) {
          var l = bloc[i];
          paquet.push(l);
          for (var j = 0; j < l.length; j++) poids += l[j].length + 3;
          i++;
        }
        return appelerAvecReprise('importSecondeBaseLot', [feuille, premiere, paquet], reprise).then(function () {
          envoyees = i;
          progres(envoyees / total, 'Envoi au classeur : ' + nb(envoyees) + ' lignes sur ' + nb(total) + '…');
          return lot();
        });
      }
      return lot();
    }).then(function () {
      progres(1, 'Mise en place de l’onglet…');
      etat.fin = true;
      return appeler('importSecondeBaseFin', [feuille, cible, total].concat(fusions ? [fusions] : []));
    }).catch(function (e) {
      if (feuille && !etat.fin) appeler('importSecondeBaseAbandon', [feuille]).catch(function () {});
      throw e;
    });
  }

  // ------------------------------------------------------------ ce qu'est un fichier
  /* À ses premiers octets : un zip (.xlsx, .xlsm, .xlsb), un conteneur OLE
     (un vrai .xls, même nommé .xlsx, ou un .xlsx chiffré), un flux BIFF nu
     (un .xls sans conteneur, ou un classeur d'Excel 2 à 4, très ancien), ou
     du texte (CSV, page web, page web archivée, XML 2003). */
  function sorteDuFichier(f) {
    return lireOctets(f, 0, 16).then(function (b) {
      if (b[0] === 0x50 && b[1] === 0x4b) return 'zip';
      if (b[0] === 0xD0 && b[1] === 0xCF && b[2] === 0x11 && b[3] === 0xE0) return 'ole';
      /* Le premier enregistrement d'un flux BIFF : BOF (09 08 en BIFF5 et 8 ;
         09 00, 09 02, 09 04 en BIFF2, 3, 4), de longueur fixe. */
      if (b.length >= 8 && b[0] === 0x09 && b[3] === 0) {
        if (b[1] === 0x08 && (b[2] === 8 || b[2] === 16)) return 'biff';
        if ((b[1] === 0x00 && b[2] === 4) || ((b[1] === 0x02 || b[1] === 0x04) && b[2] === 6)) return 'biff-ancien';
      }
      return 'texte';
    });
  }
  /* Lit un fichier et dit ce qu'il est : un export GATES ou SEE prêt à
     partir, ou une erreur qui dit pourquoi — et rien n'est encore envoyé.
     `o` : { toutes, attendu } (voir collecteur). */
  function lireFichier(f, o) {
    /* Un téléchargement raté (derrière le proxy de l'entreprise, souvent)
       laisse un fichier vide : le dire, plutôt que « ni GATES ni SEE ». */
    if (!f.size) return Promise.reject(erreur('Ce fichier est vide (0 octet) : le téléchargement n’a sans doute pas abouti. Le retélécharger depuis GATES ou SEE.'));
    return sorteDuFichier(f).then(function (sorte) {
      if (sorte === 'ole') return lireOle(f, o);
      if (sorte === 'biff') return lireBiffNu(f, o);
      if (sorte === 'biff-ancien') throw erreur(TRES_ANCIEN);
      if (sorte === 'zip') {
        var vieux = 'Ce navigateur est trop ancien pour décompresser un .xlsx. Le mettre à jour, ou passer par un export .csv.';
        if (typeof DecompressionStream !== 'function') throw erreur(vieux);
        try { new DecompressionStream('deflate-raw'); } catch (e) { throw erreur(vieux); }
        return lireXlsx(f, o);
      }
      return sonderTexte(f).then(function (s) { return s.sorte === 'mhtml' ? lireMhtml(f, o) : lireTexte(f, o, s); });
    }).then(function (c) { return bilan(c, f); });
  }
  function bilan(c, f) {
    /* Posé dans la mauvaise case : la lecture s'est arrêtée à l'en-tête. */
    if (c.trouve && c.autre) {
      throw erreur(c.sorte === 'see'
        ? 'C’est un export ' + P.base + ' (« ' + P.cles.join(' », « ') + ' » en ligne ' + c.ligneEntete + ' de « ' + c.onglet + ' ») : le mettre dans la case ' +
          P.base + ', plus bas.'
        : 'C’est un export GATES (ses en-têtes en ligne ' + c.ligneEntete + ' de « ' + c.onglet + ' ») : le mettre dans la case de son contrat, « GATES … », plus haut.');
    }
    if (!c.trouve) {
      var t = c.tropBas;
      if (t) {
        throw erreur(t.sorte === 'gates'
          ? 'La ligne d’en-têtes de cet export GATES est en ligne ' + t.ligne + ' de « ' + (t.onglet || f.name) + ' » : la page ne la trouverait pas — ' +
            'elle la cherche dans les ' + P.lignesScan + ' premières lignes. Le fichier a-t-il été retouché (des lignes ajoutées en haut) ? Le retélécharger de GATES tel quel.'
          : 'Aucune ligne d’en-tête avec ' + P.cles.join(', ') + ' dans les ' + P.lignesScan + ' premières lignes : elle est en ligne ' + t.ligne +
            ' de « ' + (t.onglet || f.name) + ' », trop bas pour la page. Le retélécharger de ' + P.base + ' tel quel.');
      }
      var m = c.meilleur || { portes: 0 };
      throw erreur('Ni un export GATES ni un export ' + (P.base || 'SEE') + ' : ' +
        (P.cles.length ? 'aucune ligne d’en-tête avec ' + P.cles.join(', ') + ', ni avec ' : 'aucune ligne d’en-tête avec ') +
        'au moins deux de Référence UD, ATA, Nom installation (chacun seul dans sa cellule, sur une ligne d’au moins dix intitulés), dans les ' +
        P.lignesScan + ' premières lignes' + (c.onglets && c.onglets.length > 1 ? ' des onglets (' + c.onglets.join(', ') + ')' : '') + '.' +
        (m.portes ? ' La ligne ' + m.ligne + ' de « ' + m.onglet + ' » en porte ' + m.portes + ' sur ' + P.cles.length + ' — il manque : ' +
          m.manquent.join(', ') + ' (intitulés lus : ' + m.noms.join(', ') + ').' : ''));
    }
    if (c.sorte === 'gates') {
      if (c.trop) throw erreur('Plus de ' + nb(P.maxCellulesToutes) + ' cellules : trop pour le classeur. Est-ce bien l’export GATES d’un contrat ?');
      var d = bilanGates(c);
      d.format = c.format;
      if (d.largeur > P.maxColonnes) throw erreur(d.largeur + ' colonnes : trop pour un export GATES (au plus ' + P.maxColonnes + ').');
      if (!d.donnees) {
        throw erreur('L’en-tête GATES est là (ligne ' + d.ligneEntete + ' de « ' + c.onglet + ' »), mais aucun plan dessous : ' +
          'l’onglet du contrat n’est pas remplacé par un export vide.');
      }
      if (c.formulesVides) {
        throw erreur(nb(c.formulesVides) + ' cellule(s) de l’en-tête, des lignes au-dessus ou de la colonne de référence sont des formules sans ' +
          'valeur calculée : le fichier a été écrit par un programme qui ne calcule pas. Demander l’export GATES en .csv, ou en .xlsx enregistré une fois par Excel.');
      }
      return d;
    }
    var tri = c.tri, filtres = tri.filtres.map(function (x) { return { colonne: x.colonne, valeurs: x.valeurs }; });
    if (c.trop) throw erreur('Plus de ' + nb(P.maxCellulesToutes) + ' cellules avec toutes les colonnes, même triées : trop pour le classeur. ' +
      'Décocher « Garder aussi les autres colonnes » : seules ' + P.cles.join(', ') + ' iront.');
    if (!c.lues) throw erreur('L’en-tête est là (« ' + c.onglet + ' »), mais aucune ligne dessous.');
    if (c.formulesVides) {
      var lues = P.cles.concat(tri.jPsn !== -1 ? [P.colonnePsn] : []).concat(filtres.map(function (x) { return x.colonne; }));
      throw erreur(nb(c.formulesVides) + ' ligne(s) ont une formule sans valeur calculée dans ' + lues.join(', ') + ' : le fichier ' +
        'a été écrit par un programme qui ne calcule pas. Demander l’export ' + P.base + ' en .csv, ou en .xlsx enregistré une fois par Excel.');
    }
    if (!c.lignes.length) {
      throw erreur(c.ecartees ? 'Aucune des ' + nb(c.lues) + ' lignes de « ' + c.onglet + ' » n’est en ' + texteFiltres(filtres) + ' : rien n’est gardé. ' +
        'Est-ce bien l’extract ' + P.base + ' (« Nommage WD BFLOW ») ?' : 'L’en-tête est là (« ' + c.onglet + ' »), mais aucune ligne dessous.');
    }
    return { sorte: 'see', entete: c.entete, lignes: c.lignes, onglet: c.onglet, format: c.format, lues: c.lues, ecartees: c.ecartees,
             tri: { psn: tri.jPsn !== -1, filtres: filtres, manquePsn: tri.manquePsn, manquent: tri.manquent },
             psn: c.psn, psnCellules: c.psnCellules, psnCompte: c.psnCompte, psnJetons: c.psnCellules.map(jetonsPsn) };
  }
  /* « DIAGRAM TYPE WD », « DIAGRAM TYPE WD ou GH, X 3 » : les filtres en clair. */
  function texteFiltres(filtres) {
    return filtres.map(function (x) { return x.colonne + ' ' + x.valeurs.join(' ou '); }).join(', ');
  }
  function messageDeLecture(e) {
    var texte = e && e.message ? e.message : String(e);
    if (e && e.name === 'TypeError' && /compress|decompress|deflate/i.test(texte)) return ABIME;
    return e && e.pourLecteur ? texte : 'Erreur inattendue : ' + texte;
  }
  /* `existe` : l'onglet visé était déjà là (il serait remplacé) — sinon
     l'import l'aurait créé, et rien n'a été créé. */
  function messageDErreur(e, etat, onglet, existe) {
    var texte = e && e.message ? e.message : String(e);
    if (/PERMISSION_DENIED|reading from storage|ScriptError.*autoris|authoriz/i.test(texte)) {
      return 'Google refuse l’appel : plusieurs comptes Google sont sans doute ouverts dans ce navigateur, ce qu’Apps Script ne supporte pas. ' +
        'Ouvrir le classeur dans une fenêtre où seul le compte du classeur est connecté (ou une fenêtre de navigation privée), puis relancer.';
    }
    var t = e && e.pourLecteur ? texte : 'Erreur inattendue : ' + texte;
    var rien = existe ? ' Rien n’a été remplacé dans le classeur.' : ' Rien n’a été créé dans le classeur.';
    /* Après l'appel de fin, l'onglet a pu être échangé — sauf pour ces refus,
       qui arrivent avant tout échange. */
    if (etat.fin && !/Import incomplet|a disparu|non reconnu|Contrat introuvable|Geste refusé|existe déjà|nom réservé|Colonne suivie absente|occupé par un autre geste/.test(texte)) {
      return t + ' L’import est peut-être allé au bout : regarder l’onglet « ' + onglet + ' » (ou menu Suivi FWD → Diagnostic) avant de relancer.';
    }
    if (etat.fin) return t + (existe ? ' L’ancien onglet « ' + onglet + ' » est intact.' : rien);
    if (e && e.duServeur && !/limite de Google Sheets|Import incomplet/.test(texte)) t += ' Relancer l’import ; si ça recommence : menu Suivi FWD → Diagnostic.';
    return t + (/Rien n.(a été|est) (remplacé|créé)|intact/.test(t) ? '' : rien);
  }

  // ------------------------------------------------------------ les cases
  /* Une case par export (débrief 21 : « il faut mettre que c'est le GATES
     HDK, et ça va direct dans HDK, ce sera plus simple ») : « GATES HDK »
     pour chaque contrat du classeur, une case par contrat ajouté (« Ajouter
     un contrat… »), et la case SEE — l'extract de tous les porteurs, trié
     ici par le PSN de chaque contrat. Rien n'est deviné : le fichier va là
     où on le pose. La fenêtre vérifie seulement que c'est le bon genre
     d'export, et prévient — sans bloquer — quand un export GATES partage peu
     de plans avec l'onglet qu'il remplacerait.
     Une case : { n, sorte ('gates' | 'see'), id (le contrat), nouveau (un
     contrat ajouté ici), nom (son nom, vérifié par le serveur), f (le
     fichier), etat ('vide', 'attente', 'lecture', 'lu', 'erreur', 'envoi',
     'fait', 'echec'), lu (ce que la lecture a rendu), lecture (le numéro de
     la lecture en cours : un fichier remplacé ou retiré en pleine lecture la
     rend caduque), sansTri, resultat, el }. */
  var cases = [], caseSee = null, aLire = [], enLecture = null, enCours = false, numero = 0, lectures = 0;
  /* La liste des contrats, relue après chaque import (relireContrats) :
     `relecture` pendant qu'elle est demandée, `contratsPerimes` si elle n'a
     pas pu l'être. */
  var relecture = null, contratsPerimes = false;
  /* Le PSN de chaque contrat tel qu'il est dans la fenêtre, par nom réduit :
     { texte, jetons, etat ('ok', 'attente', 'refus'), message, source,
     touche (tapé ici), demande, minuteur, enregistre }. */
  var saisiesPsn = {};
  var TABLEAUX = /\.(xlsx|xlsm|xls|xlsb|csv|txt|xml|html?|mht|mhtml|zip)$/i;
  var EXTENSIONS = '.xlsx,.xlsm,.csv,.txt,.xls,.xlsb,.xml,.htm,.html,.mht,.mhtml,.zip';
  var PSN_FORME = new RegExp(P.psnForme);

  function contratExistant(id) {
    var n = norm(id);
    return P.contrats.filter(function (k) { return norm(k.id) === n; })[0] || null;
  }
  var ENSEMBLES = {};
  function ensembleDe(k) {
    if (!ENSEMBLES[k.id]) { var e = {}; k.refs.forEach(function (r) { e[r] = true; }); ENSEMBLES[k.id] = e; }
    return ENSEMBLES[k.id];
  }
  function communs(d, k) {
    var e = ensembleDe(k), n = 0;
    d.refs.forEach(function (x) { if (e[x]) n++; });
    return n;
  }
  /* Le nom du contrat d'une case : celui de son onglet, ou celui tapé pour un contrat ajouté (vérifié). */
  function contratDe(k) { return k.nouveau ? (k.nom.etat === 'ok' ? k.nom.valeur : '') : k.id; }
  function libelleCase(k) {
    if (k.sorte === 'see') return P.base;
    return 'GATES' + (contratDe(k) ? ' ' + contratDe(k) : '');
  }

  function creerCase(k) {
    var el = document.createElement(k.sorte === 'see' ? 'div' : 'li');
    el.className = 'case ' + k.sorte + (k.nouveau ? ' nouvelle' : '');
    el.innerHTML = '<div class="tete"><span class="etiquette"></span>' +
      (k.nouveau ? '<input type="text" class="nom" maxlength="' + P.nomMax + '" placeholder="Nom du contrat (celui de son onglet)" aria-label="Nom du nouveau contrat">' : '') +
      '<span class="fichier-nom"></span><span class="date"></span><span class="taille"></span>' +
      '<span class="invite"></span>' +
      '<button type="button" class="choisir">Choisir le fichier…</button>' +
      '<button type="button" class="retirer" hidden>Retirer</button>' +
      (k.nouveau ? '<button type="button" class="annuler" title="Retirer cette case">Annuler</button>' : '') + '</div>' +
      (k.nouveau ? '<div class="verif-nom"></div>' : '') +
      '<div class="lu"></div><div class="barre" hidden><div></div></div>' +
      (k.sorte === 'see' ? '<div class="manque" hidden><div class="manque-texte"></div><label class="sans-tri"><input type="checkbox"> <span></span></label></div>' +
        '<div class="tri-aide"></div><ul class="porteurs"></ul>' : '<div class="cible"></div>') +
      '<div class="note" hidden></div><div class="resultat" hidden></div>' +
      '<input type="file" class="fichier" hidden accept="' + EXTENSIONS + '">';
    k.el = el;
    var q = function (s) { return el.querySelector(s); };
    q('.choisir').addEventListener('click', function () { if (!enCours) q('.fichier').click(); });
    q('.fichier').addEventListener('change', function () {
      var l = q('.fichier').files, choisis = [];
      for (var i = 0; i < l.length; i++) choisis.push(l[i]);
      q('.fichier').value = '';
      poserFichiers(k, choisis);
    });
    q('.retirer').addEventListener('click', function () { retirerFichier(k); });
    el.addEventListener('dragover', function (e) { e.preventDefault(); e.stopPropagation(); if (!enCours) el.classList.add('survol'); });
    el.addEventListener('dragleave', function () { el.classList.remove('survol'); });
    el.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.classList.remove('survol');
      if (enCours || !e.dataTransfer || !e.dataTransfer.files) return;
      var choisis = [];
      for (var i = 0; i < e.dataTransfer.files.length; i++) choisis.push(e.dataTransfer.files[i]);
      poserFichiers(k, choisis);
    });
    if (k.nouveau) {
      q('.nom').addEventListener('input', function () { saisirNom(k, this.value, false); });
      q('.nom').addEventListener('change', function () { saisirNom(k, this.value, true); });
      q('.annuler').addEventListener('click', function () { annulerCase(k); });
    }
    if (k.sorte === 'see') {
      q('.sans-tri input').addEventListener('change', function () { k.sansTri = this.checked; majTout(); });
    }
    return el;
  }
  function nouvelleCase(sorte, id, nouveau) {
    var k = { n: ++numero, sorte: sorte, id: id || '', nouveau: !!nouveau, f: null, etat: 'vide', lu: null, erreur: '', lecture: 0,
              texteLecture: '', texteEnvoi: '', resultat: null, sansTri: false, avis: '', el: null,
              nom: { valeur: '', etat: 'vide', message: '', demande: 0, minuteur: null, propose: '' } };
    creerCase(k);
    return k;
  }
  /* Les cases GATES dans l'ordre : celles des contrats du classeur, dans
     l'ordre des onglets, puis celles des contrats ajoutés. */
  function rangerCases() {
    var ul = $('cases-gates');
    cases.forEach(function (k) { ul.appendChild(k.el); });
  }
  function ajouterContrat() {
    if (enCours || !P.nouveauPermis) return null;
    var k = nouvelleCase('gates', '', true);
    cases.push(k);
    rangerCases();
    dessiner(k);
    majTout();
    return k;
  }
  function annulerCase(k) {
    if (enCours) return;
    /* Sa lecture en cours devient caduque, celle qui attendait n'a pas lieu. */
    k.lecture = ++lectures;
    aLire = aLire.filter(function (x) { return x !== k; });
    clearTimeout(k.nom.minuteur);
    cases = cases.filter(function (x) { return x !== k; });
    if (k.el && k.el.parentNode) k.el.parentNode.removeChild(k.el);
    dire('');
    majTout();
  }

  // ------------------------------------------------------------ poser un fichier dans sa case
  /* Un seul fichier par case. Ce qui n'est pas un tableau n'est pas lu ; un
     fichier posé dans une case qui en avait un le remplace (une lecture en
     cours devient caduque). */
  function poserFichiers(k, liste) {
    if (enCours || !liste.length) return;
    var f = liste[0], mots = [];
    if (liste.length > 1) {
      mots.push('Une case prend un seul fichier : « ' + f.name + ' » va dans « ' + libelleCase(k) + ' », ' +
        liste.slice(1).map(function (x) { return '« ' + x.name + ' »'; }).slice(0, 4).join(', ') + (liste.length > 5 ? ', …' : '') +
        ' laissé' + (liste.length > 2 ? 's' : '') + ' de côté — chacun dans sa case.');
    }
    dire(ech(mots.join(' ')));
    /* Après un import, « Importer » redevient le bouton principal. */
    $('importer').classList.add('principal');
    $('fermer').classList.remove('principal');
    k.f = f;
    k.lu = null;
    k.erreur = '';
    k.resultat = null;
    k.avis = '';
    k.sansTri = false;
    k.lecture = ++lectures;
    if (k.sorte === 'see') { var s = k.el.querySelector('.sans-tri input'); s.checked = false; }
    if (!TABLEAUX.test(f.name)) {
      k.etat = 'erreur';
      k.erreur = '« ' + f.name + ' » n’est pas un tableau (.xlsx, .xls, .csv ou page web) : rien n’est lu.';
    } else {
      k.etat = 'attente';
      if (aLire.indexOf(k) === -1) aLire.push(k);
    }
    dessiner(k);
    majTout();
    /* La liste des contrats n'a pas pu être relue après l'import d'avant :
       on la redemande avant de lire. */
    if (contratsPerimes && !relecture) relireContrats().then(function () { majTout(); lireSuivant(); });
    else lireSuivant();
  }
  function retirerFichier(k) {
    if (enCours) return;
    k.lecture = ++lectures;
    k.f = null;
    k.lu = null;
    k.erreur = '';
    k.resultat = null;
    k.avis = '';
    k.sansTri = false;
    k.etat = 'vide';
    aLire = aLire.filter(function (x) { return x !== k; });
    dire('');
    dessiner(k);
    majTout();
  }
  /* Lit les fichiers posés, un à la fois. */
  function lireSuivant() {
    if (enLecture || relecture) return;
    var k = aLire.shift();
    while (k && k.etat !== 'attente') k = aLire.shift();
    if (!k) { majTout(); return; }
    var numeroLecture = k.lecture, debut = Date.now(), toutes = k.sorte === 'see' && !!$('toutes') && $('toutes').checked;
    enLecture = k;
    k.etat = 'lecture';
    k.texteLecture = 'Lecture…';
    suivi = function (part, texte) {
      /* Un fichier remplacé ou retiré pendant sa lecture : elle s'arrête là. */
      if (k.lecture !== numeroLecture) { var x = new Error('lecture caduque'); x.caduque = true; throw x; }
      avancer(k, part);
      if (texte !== undefined) { k.texteLecture = texte; k.el.querySelector('.lu').textContent = texte; }
    };
    dessiner(k);
    majTout();
    lireFichier(k.f, { toutes: toutes, attendu: k.sorte }).then(function (d) {
      if (k.lecture !== numeroLecture) return;
      d.duree = (Date.now() - debut) / 1000;
      d.toutes = toutes;
      k.lu = d;
      k.etat = 'lu';
    }, function (e) {
      if (k.lecture !== numeroLecture) return;
      k.lu = null;
      k.etat = 'erreur';
      k.erreur = messageDeLecture(e);
    }).then(function () {
      suivi = null;
      enLecture = null;
      if (k.lecture === numeroLecture && k.sorte === 'see' && $('toutes') && toutes !== $('toutes').checked) {
        /* « Garder aussi les autres colonnes » a changé pendant la lecture :
           l'extract est relu avec le nouveau réglage. */
        k.etat = 'attente';
        k.lu = null;
        aLire.unshift(k);
      } else if (k.lecture === numeroLecture && k.etat === 'lu' && k.nouveau) {
        /* Un contrat ajouté, encore sans nom : celui de ses groupes
           (« NEO AA 011 » → NEO), s'il n'est pas déjà un contrat — proposé,
           le champ reste modifiable. */
        var mot = k.lu.motGroupe;
        if (!k.nom.valeur && mot && !contratExistant(mot) && !cases.some(function (x) { return x !== k && x.nouveau && norm(x.nom.valeur) === norm(mot); })) {
          k.nom.propose = mot;
          saisirNom(k, mot, true);
        }
      }
      dessiner(k);
      majTout();
      lireSuivant();
    });
  }
  function avancer(k, part) {
    var b = k.el.querySelector('.barre');
    b.hidden = false;
    b.firstChild.style.width = Math.round(Math.max(0, Math.min(1, part)) * 100) + '%';
  }

  // ------------------------------------------------------------ le nom d'un contrat ajouté
  /* Vérifié par le serveur dès qu'il est tapé (nom réservé, onglet qui
     existe déjà…) : « Importer » attend sa réponse. */
  function saisirNom(k, valeur, aussitot) {
    var n = k.nom, v = String(valeur === undefined || valeur === null ? '' : valeur).trim();
    /* Le même nom, déjà vérifié ou en cours de l'être : rien à redemander.
       Sinon, cliquer « Importer » juste après l'avoir tapé — le champ perd
       le focus, « change » part — éteindrait le bouton sous le clic. */
    if (v === n.valeur && n.etat !== 'vide') return;
    if (norm(v) !== norm(n.propose)) n.propose = '';
    n.valeur = v;
    n.etat = n.valeur ? 'attente' : 'vide';
    n.message = '';
    clearTimeout(n.minuteur);
    var demande = ++n.demande;
    var champ = k.el.querySelector('.nom');
    if (champ.value.trim() !== n.valeur) champ.value = n.valeur;
    if (!n.valeur) { dessiner(k); majTout(); return; }
    n.minuteur = setTimeout(function () {
      appeler('importVerifierNouveauContrat', [n.valeur]).then(function (rep) {
        if (demande !== n.demande) return;
        n.etat = rep && rep.ok ? 'ok' : 'refus';
        n.message = rep && rep.ok ? '' : String(rep && rep.message ? rep.message : 'Nom refusé.');
        if (rep && rep.ok) n.valeur = rep.nom;
      }, function (e) {
        if (demande !== n.demande) return;
        n.etat = 'refus';
        n.message = 'Le nom n’a pas pu être vérifié (' + e.message + ') : le retaper.';
        n.valeur = '';   // oublié : le même nom, retapé, est redemandé
      }).then(function () {
        if (demande !== n.demande || cases.indexOf(k) === -1) return;
        dessiner(k);
        majTout();
      });
    }, aussitot ? 0 : 400);
    dessiner(k);
    majTout();
  }

  // ------------------------------------------------------------ le PSN de chaque contrat
  /* « Si on en fait d'autres, il faudra demander le PSN » : chaque contrat
     a le sien, celui de la configuration ou celui tapé ici — gardé dans le
     classeur pour les fois suivantes (importEnregistrerPsn), sitôt tapé.
     Changer un PSN retrie l'extract déjà lu sur-le-champ : seules les lignes
     qui passent les FILTRES sont en mémoire, chacune avec sa cellule de PSN. */
  function saisiePsn(id) {
    var cle = norm(id), s = saisiesPsn[cle];
    if (!s) {
      var k = contratExistant(id), initial = k ? (k.psn || []) : (P.psnConfig[cle] || []);
      s = saisiesPsn[cle] = { texte: initial.join(', '), jetons: initial.map(norm), etat: 'ok', message: '', touche: false, enregistre: false,
                              source: k ? k.psnSource : (initial.length ? 'configuration' : ''), demande: 0, minuteur: null };
    }
    return s;
  }
  /* Un PSN tapé : ses jetons, ou un message qui dit pourquoi il n'en est pas un (la règle du serveur, reçue). */
  function lirePsn(texte) {
    var vus = {}, jetons = [], faux = '';
    String(texte).split(/[\s,;]+/).forEach(function (j) {
      if (!j) return;
      if (!PSN_FORME.test(j) && !faux) faux = j;
      var n = norm(j);
      if (!vus[n]) { vus[n] = true; jetons.push(n); }
    });
    if (faux) return { message: '« ' + faux.slice(0, 30) + ' » n’est pas un PSN : des chiffres (des lettres au besoin), plusieurs séparés par des virgules — comme « 4530 ».' };
    if (jetons.length > P.psnMax) return { message: 'Trop de PSN : ' + jetons.length + ' (au plus ' + P.psnMax + ').' };
    return { jetons: jetons };
  }
  function saisirPsn(id, texte, aussitot) {
    var s = saisiePsn(id), lu = lirePsn(texte);
    if (texte === s.texte && s.touche && (s.etat === 'ok' || (s.etat === 'attente' && !aussitot))) return;
    s.texte = texte;
    s.touche = true;
    s.enregistre = false;
    clearTimeout(s.minuteur);
    var demande = ++s.demande;
    if (lu.message) {
      s.etat = 'refus';
      s.message = lu.message;
      dessinerSee();
      majTout();
      return;
    }
    s.jetons = lu.jetons;
    s.message = '';
    /* Un contrat qui naît dans la fenêtre : son PSN est gardé sitôt le contrat créé. */
    if (!contratExistant(id)) { s.etat = 'ok'; dessinerSee(); majTout(); return; }
    s.etat = 'attente';
    s.minuteur = setTimeout(function () {
      appelerAvecReprise('importEnregistrerPsn', [contratExistant(id).id, texte]).then(function (rep) {
        if (demande !== s.demande) return;
        s.etat = 'ok';
        s.enregistre = true;
        s.source = rep && rep.source ? rep.source : 'fenetre';
        var k = contratExistant(id);
        if (k && rep) { k.psn = rep.psn; k.psnSource = rep.source; }
      }, function (e) {
        if (demande !== s.demande) return;
        s.etat = 'refus';
        s.message = 'Le PSN de « ' + id + ' » n’a pas pu être enregistré (' + e.message + ') : le retaper.';
      }).then(function () {
        if (demande !== s.demande) return;
        dessinerSee();
        majTout();
      });
    }, aussitot ? 0 : 700);
    dessinerSee();
    majTout();
  }

  // ------------------------------------------------------------ la base SEE de chaque contrat
  /* Les contrats qui peuvent recevoir une base SEE : ceux du classeur, puis
     ceux qu'un export GATES de la fenêtre va créer (nom vérifié, fichier lu).
     { id, nouveau, onglet (visé), existe, avant (son nom d'aujourd'hui, s'il
     sera renommé) }. */
  function ciblesSee() {
    var liste = P.contrats.map(function (k) { return { id: k.id, nouveau: false, onglet: k.onglet, existe: k.existe }; });
    cases.forEach(function (k) {
      if (k.nouveau && k.nom.etat === 'ok' && k.f && k.etat !== 'erreur' && k.etat !== 'echec' &&
          !liste.some(function (c) { return norm(c.id) === norm(k.nom.valeur); })) {
        liste.push({ id: k.nom.valeur, nouveau: true, onglet: P.base + ' ' + k.nom.valeur, existe: false });
      }
    });
    /* Le seul contrat du classeur a pour base l'onglet « SEE » tout court, et
       la fenêtre crée un deuxième contrat : le serveur renommera « SEE » en
       « SEE HDK » avant d'y créer le nouveau (rattacherAuContratUnique_), et
       c'est ce nom-là que l'extract de HDK remplacera. */
    var g = baseGeneriqueRenommee();
    if (g) liste.forEach(function (c) { if (c.id === g.id) { c.avant = c.onglet; c.onglet = g.vers; } });
    return liste;
  }
  function nouveauxContrats() {
    return cases.filter(function (k) { return k.nouveau && k.nom.etat === 'ok' && k.f && k.etat !== 'erreur' && k.etat !== 'echec'; });
  }
  function baseGeneriqueRenommee() {
    if (P.contrats.length !== 1 || !P.base || !nouveauxContrats().length) return null;
    var k = P.contrats[0];
    return k.existe && compact(k.onglet) === compact(P.base) ? { id: k.id, de: k.onglet, vers: P.base + ' ' + k.id } : null;
  }
  /* Ce que le tri de l'extract lu demande : les colonnes qui manquent au
     fichier, et s'il se partage par PSN. Sans la colonne des PSN (cochée
     « importer sans ce tri »), ou sans PSN dans la configuration, l'extract
     va tout entier au contrat — s'il n'y en a qu'un. */
  function etatTri(d) {
    var manquent = (d.tri.manquePsn ? [P.colonnePsn] : []).concat(d.tri.manquent);
    return { manquent: manquent, parPsn: !!P.colonnePsn && d.tri.psn };
  }
  /* Les lignes de l'extract lu qui vont à un contrat : pour chaque cellule
     de PSN différente, porte-t-elle l'un des siens — calculé une fois par
     PSN, puis gardé. */
  function cellulesDe(d, jetons) {
    var cle = jetons.slice().sort().join(',');
    d.parPsn = d.parPsn || {};
    if (!d.parPsn[cle]) {
      var voulus = {};
      jetons.forEach(function (j) { voulus[j] = true; });
      var oui = d.psnJetons.map(function (js) { return js.some(function (j) { return voulus[j] === true; }); });
      var n = 0;
      oui.forEach(function (o, i) { if (o) n += d.psnCompte[i]; });
      d.parPsn[cle] = { oui: oui, n: n };
    }
    return d.parPsn[cle];
  }
  /* La part de l'extract qui revient à chaque contrat :
     [{ cible, jetons (null : sans tri par PSN), n, raison ('sans-psn' |
     'aucune' | 'sans-tri-plusieurs' | '') }]. */
  function partsSee(d) {
    var tri = etatTri(d), cibles = ciblesSee();
    return cibles.map(function (c) {
      if (!tri.parPsn) return { cible: c, jetons: null, n: cibles.length === 1 ? d.lignes.length : 0, raison: cibles.length === 1 ? '' : 'sans-tri-plusieurs' };
      var s = saisiePsn(c.id);
      if (!s.jetons.length || s.etat === 'refus') return { cible: c, jetons: [], n: 0, raison: 'sans-psn' };
      var n = cellulesDe(d, s.jetons).n;
      return { cible: c, jetons: s.jetons, n: n, raison: n ? '' : 'aucune' };
    });
  }
  /* « WD », « WD ou GH » : les valeurs gardées, pour dire les lignes. */
  function motFiltres(d) {
    return d.tri.filtres.length ? ' ' + d.tri.filtres.map(function (x) { return x.valeurs.join(' ou '); }).join(', ') : '';
  }
  /* Le tri d'une base, en parts : [{ psn }] puis [{ colonne, valeurs }] — la ligne « Trié à l’import » le dit en tête de l'onglet. */
  function partsTri(d, jetons) {
    var parts = [];
    if (jetons && jetons.length) parts.push('PSN ' + saisieTexte(jetons));
    d.tri.filtres.forEach(function (x) { parts.push(x.colonne + ' = ' + x.valeurs.join(', ')); });
    return parts;
  }
  function saisieTexte(jetons) { return jetons.join(', ').toUpperCase(); }

  // ------------------------------------------------------------ dessiner
  function majuscule(t) { return t.charAt(0).toUpperCase() + t.slice(1); }
  /* Un export GATES dans un format qui ne garde pas les cellules fusionnées
     (un .csv ; un .xls d'Excel 95, les fusions étant venues avec Excel 97) :
     la page déduit alors les groupes de proche en proche. Rend ce format tel
     que les messages le nomment (« un .csv »), ou '' si les fusions sont là. */
  function perteFusions(d) {
    return d.format === 'csv' ? 'un .csv' : d.format === 'xls95' && !d.fusions.length ? 'un .xls d’Excel 95' : '';
  }
  function resumeLu(d) {
    var dit = d.duree >= 0 ? ' · lu en ' + Math.max(1, Math.round(d.duree)) + ' s' : '';
    if (d.sorte === 'see') {
      var trie = d.tri.filtres.length ? nb(d.lues) + ' lignes lues, ' + nb(d.lignes.length) + ' en' + motFiltres(d) + ' (' +
        texteFiltres(d.tri.filtres) + ')' : nb(d.lignes.length) + ' ligne' + (d.lignes.length > 1 ? 's' : '');
      return trie + ', colonnes ' + d.entete.join(', ') + dit;
    }
    return (d.refs.length ? nb(d.refs.length) + ' plan' + (d.refs.length > 1 ? 's' : '') : nb(d.donnees) + ' lignes') + ' · ' + d.largeur + ' colonnes' +
      ' · en-têtes en ligne ' + d.ligneEntete + (d.fusions.length ? ' · ' + d.fusions.length + ' cellules fusionnées' : '') + dit +
      (perteFusions(d) ? ' · ' + perteFusions(d) + ' ne garde pas les cellules fusionnées de la ligne des groupes : l’export Excel (.xlsx, ou .xls d’Excel 97-2003) est plus sûr' : '') +
      (d.formulesAilleurs ? ' · ' + nb(d.formulesAilleurs) + ' formule(s) sans valeur calculée, laissée(s) vide(s)' : '');
  }
  /* Le mot qui dit l'état d'une case, pour la tête : rien tant qu'elle attend un fichier. */
  function dessinerTete(k) {
    var el = k.el, q = function (s) { return el.querySelector(s); }, f = k.f;
    el.setAttribute('data-etat', k.etat);
    el.setAttribute('data-case', k.sorte === 'see' ? 'see' : k.nouveau ? 'n' + k.n : 'g:' + k.id);
    q('.etiquette').textContent = libelleCase(k);
    q('.fichier-nom').textContent = f ? f.name : '';
    q('.date').textContent = f && dateFichier(f) ? 'du ' + dateFichier(f) : '';
    q('.taille').textContent = f ? taille(f.size) : '';
    var invite = q('.invite');
    invite.hidden = !!f;
    invite.textContent = k.sorte === 'see' ? 'glisser ici l’extract « Nommage WD BFLOW », le même pour tous les contrats — ou'
      : k.nouveau ? 'glisser ici son export GATES — ou' : 'glisser ici l’export GATES de ' + k.id + ' — ou';
    var choisir = q('.choisir');
    choisir.textContent = f ? 'Changer…' : 'Choisir le fichier…';
    choisir.hidden = enCours;
    choisir.setAttribute('aria-label', (f ? 'Changer le fichier de la case ' : 'Choisir le fichier de la case ') + libelleCase(k));
    var retirer = q('.retirer');
    retirer.hidden = enCours || !f || k.etat === 'fait' || k.etat === 'echec';
    retirer.setAttribute('aria-label', 'Retirer le fichier de la case ' + libelleCase(k));
    var lu = q('.lu');
    lu.className = 'lu' + (k.etat === 'erreur' ? ' erreur' : '');
    lu.textContent = k.etat === 'attente' ? 'En attente de lecture…' : k.etat === 'lecture' ? k.texteLecture :
      k.etat === 'erreur' ? '✗ ' + k.erreur : k.lu ? resumeLu(k.lu) : '';
    lu.hidden = !lu.textContent;
    q('.barre').hidden = k.etat !== 'lecture' && k.etat !== 'envoi';
    var res = q('.resultat');
    res.hidden = !k.resultat && k.etat !== 'envoi';
    if (k.resultat) { res.className = 'resultat ' + k.resultat.classe; res.innerHTML = k.resultat.html; }
    else if (k.etat === 'envoi') { res.className = 'resultat'; res.textContent = k.texteEnvoi || ''; }
  }
  function dessiner(k) {
    if (!k || !k.el) return;
    if (k === caseSee) { dessinerSee(); return; }
    var el = k.el, q = function (s) { return el.querySelector(s); }, d = k.lu;
    if (k.nouveau && k.nom.etat === 'attente') el.setAttribute('data-occupe', '1'); else el.removeAttribute('data-occupe');
    dessinerTete(k);
    if (k.nouveau) {
      var champ = q('.nom');
      champ.disabled = enCours || k.etat === 'fait';
      q('.annuler').hidden = enCours || k.etat === 'fait';
      var v = q('.verif-nom'), n = k.nom;
      v.className = 'verif-nom' + (n.etat === 'refus' ? ' refus' : '');
      v.textContent = n.etat === 'refus' ? n.message : n.etat === 'attente' ? 'Vérification du nom…' :
        n.etat === 'ok' && n.propose && norm(n.propose) === norm(n.valeur) ? 'Nom tiré de ses groupes « ' + n.valeur + ' AA … » : le changer au besoin — c’est celui de son onglet.' :
        n.etat === 'vide' ? 'Le nom du contrat est celui de son onglet, comme « HDK ».' : '';
      v.hidden = !v.textContent;
    }
    var avant = k.etat === 'lu' && d, texte = '', note = '';
    var contrat = contratDe(k);
    if (avant && contrat) {
      if (!k.nouveau) {
        texte = 'Remplacera l’onglet <b>« ' + ech(k.id) + ' »</b> — l’ancien ne s’en va qu’une fois tout reçu ; son historique est gardé.';
      } else {
        texte = 'Créera l’onglet <b>« ' + ech(contrat) + ' »</b> : un nouveau contrat, rangé après les autres.';
        var g = baseGeneriqueRenommee();
        if (g) texte += ' L’onglet « ' + ech(g.de) + ' » de « ' + ech(g.id) + ' » deviendra « ' + ech(g.vers) + ' » : avec deux contrats, chaque base porte le nom du sien.';
      }
      note = recouvrement(k);
    }
    q('.cible').innerHTML = texte;
    q('.cible').hidden = !texte;
    var zone = q('.note');
    zone.textContent = note;
    zone.hidden = !note;
  }
  /* Le doute, dit sans bloquer : un export GATES qui partage peu de plans
     avec l'onglet qu'il va remplacer — l'export d'un autre contrat, peut-être
     (« seulement 3 plans sur 186 en commun avec « HDK » : est-ce bien son
     export ? ») ; pour un contrat ajouté, un export dont les plans sont déjà
     ceux d'un contrat du classeur. */
  function recouvrement(k) {
    var d = k.lu, i;
    if (!d || !d.refs.length) return '';
    var ailleurs = null;
    for (i = 0; i < P.contrats.length; i++) {
      var o = P.contrats[i];
      if (!k.nouveau && o.id === k.id) continue;
      var no = o.refs.length ? communs(d, o) : 0;
      if (no / d.refs.length >= P.seuilRecouvrement && (!ailleurs || no > ailleurs.n)) ailleurs = { id: o.id, n: no };
    }
    if (k.nouveau) {
      return ailleurs ? nb(ailleurs.n) + ' de ses ' + nb(d.refs.length) + ' plans sont déjà dans « ' + ailleurs.id + ' » : est-ce l’export de « ' + ailleurs.id +
        ' » ? Il irait alors dans sa case, « GATES ' + ailleurs.id + ' ».' : '';
    }
    var c = contratExistant(k.id);
    if (!c || !c.refs.length) return '';
    var n = communs(d, c);
    if (n / d.refs.length >= P.seuilRecouvrement) return '';
    return (n ? 'seulement ' + nb(n) + ' plan' + (n > 1 ? 's' : '') + ' sur ' + nb(d.refs.length) + ' en commun' : 'aucun de ses ' + nb(d.refs.length) + ' plans en commun') +
      ' avec « ' + k.id + ' » : est-ce bien son export ?' + (ailleurs ? ' ' + nb(ailleurs.n) + ' sont dans « ' + ailleurs.id + ' » : sa place serait plutôt la case « GATES ' +
      ailleurs.id + ' ».' : '');
  }
  function dessinerSee() {
    var k = caseSee;
    if (!k) return;
    var el = k.el, q = function (s) { return el.querySelector(s); }, d = k.etat === 'lu' || k.etat === 'envoi' ? k.lu : null;
    dessinerTete(k);
    var manque = q('.manque'), aide = q('.tri-aide'), boite = q('.sans-tri input');
    var tri = d ? etatTri(d) : null, cibles = ciblesSee(), parts = d ? partsSee(d) : null;
    /* Ce qui manque au fichier pour le trier : bloquant, sauf « importer sans ce tri ». */
    if (d && tri.manquent.length) {
      var seul = cibles.length === 1, possible = !d.tri.manquePsn || seul;
      q('.manque-texte').textContent = '✗ « ' + k.f.name + ' » n’a pas de colonne ' + tri.manquent.join(', ni de colonne ') + ' : ' +
        (d.tri.manquePsn ? 'l’extract ne se trie pas par machine (le PSN de chaque contrat)' : 'les lignes ne se trient pas sur ' + tri.manquent.join(', ')) + '.';
      q('.sans-tri span').textContent = 'importer sans ce tri — ' + (d.tri.manquePsn
        ? (seul ? 'tout l’extract ira dans « ' + cibles[0].onglet + ' »' : cibles.length ? 'impossible avec ' + cibles.length + ' contrats : l’extract ne se partage pas sans ' + P.colonnePsn
          : 'impossible : aucun contrat pour le recevoir')
        : 'toutes les lignes, quel que soit leur ' + d.tri.manquent.join(', '));
      boite.disabled = enCours || !possible;
      if (!possible) { boite.checked = false; k.sansTri = false; }
      manque.hidden = false;
    } else manque.hidden = true;
    /* Une ligne par contrat : son PSN (modifiable), et ce que l'extract lu lui donne. */
    aide.hidden = !P.colonnePsn;
    aide.textContent = P.colonnePsn ? 'Le PSN de chaque contrat — le numéro de sa machine dans ' + P.colonnePsn + ' — choisit ses lignes' +
      (P.filtres.length ? ', parmi celles en ' + texteFiltres(P.filtres) : '') + '. Un PSN tapé ici est gardé pour les fois suivantes.' : '';
    var ul = q('.porteurs'), vus = {};
    cibles.forEach(function (c, i) {
      var cle = norm(c.id);
      vus[cle] = true;
      var li = ul.querySelector('[data-cle="' + cle.replace(/["\\]/g, '') + '"]');
      if (!li) li = creerPorteur(c);
      if (ul.children[i] !== li) ul.insertBefore(li, ul.children[i] || null);
      dessinerPorteur(li, c, parts ? parts[i] : null, d);
    });
    Array.prototype.slice.call(ul.children).forEach(function (li) { if (!vus[li.getAttribute('data-cle')]) ul.removeChild(li); });
    ul.hidden = !cibles.length || (!P.colonnePsn && !d);
    var res = q('.resultat');
    if (k.resultat) { res.className = 'resultat ' + k.resultat.classe; res.innerHTML = k.resultat.html; res.hidden = false; }
    /* Ce que la lecture garde en mémoire (les lignes qui passent les FILTRES), et un PSN en cours d'enregistrement. */
    el.setAttribute('data-gardees', d ? String(d.lignes.length) : '');
    if (P.colonnePsn && cibles.some(function (c) { return saisiePsn(c.id).etat === 'attente'; })) el.setAttribute('data-occupe', '1');
    else el.removeAttribute('data-occupe');
  }
  function creerPorteur(c) {
    var li = document.createElement('li');
    li.className = 'porteur';
    li.setAttribute('data-cle', norm(c.id).replace(/["\\]/g, ''));
    li.setAttribute('data-contrat', c.id);
    li.innerHTML = '<span class="contrat"></span>' +
      (P.colonnePsn ? '<label class="psn"><span>PSN</span> <input type="text" spellcheck="false" autocomplete="off"></label><span class="enr"></span>' : '') +
      '<span class="part"></span>';
    if (P.colonnePsn) {
      var champ = li.querySelector('input');
      champ.setAttribute('aria-label', 'PSN de ' + c.id);
      champ.value = saisiePsn(c.id).texte;
      champ.addEventListener('input', function () { saisirPsn(li.getAttribute('data-contrat'), this.value, false); });
      champ.addEventListener('change', function () { saisirPsn(li.getAttribute('data-contrat'), this.value, true); });
    }
    return li;
  }
  function dessinerPorteur(li, c, p, d) {
    var q = function (s) { return li.querySelector(s); };
    li.setAttribute('data-contrat', c.id);
    q('.contrat').textContent = c.id + (c.nouveau ? ' (nouveau)' : '');
    var s = P.colonnePsn ? saisiePsn(c.id) : null;
    if (s) {
      var champ = q('input');
      if (document.activeElement !== champ && champ.value !== s.texte) champ.value = s.texte;
      champ.disabled = enCours;
      champ.className = s.etat === 'refus' ? 'refus' : '';
      var enr = q('.enr');
      enr.className = 'enr' + (s.etat === 'refus' ? ' refus' : '');
      enr.textContent = s.etat === 'refus' ? s.message : s.etat === 'attente' ? 'enregistrement…' :
        s.enregistre || (!s.touche && s.source === 'fenetre') ? 'enregistré' : !s.touche && s.source === 'configuration' && s.jetons.length ? 'de la configuration' : '';
    }
    var part = q('.part'), texte = '', classe = 'part';
    var vers = function () {
      return (c.existe ? 'remplacera « ' : 'créera « ') + c.onglet + ' »' + (c.avant ? ' (aujourd’hui « ' + c.avant + ' », renommé à la création du nouveau contrat)' : '');
    };
    if (!d) {
      if (s && !s.jetons.length) { texte = 'pas de PSN : pas de base ' + P.base + ' pour ce contrat'; classe += ' rien'; }
    } else if (!p.jetons && p.raison === 'sans-tri-plusieurs') {
      texte = 'pas de base : l’extract ne se partage pas sans ' + (P.colonnePsn || 'PSN'); classe += ' rien';
    } else if (!p.jetons) {
      var attend = etatTri(d).manquent.length && !caseSee.sansTri;
      texte = '— tout l’extract : ' + nb(p.n) + ' ligne' + (p.n > 1 ? 's' : '') + motFiltres(d) + ' → ' + vers() + (attend ? ', une fois « importer sans ce tri » coché' : '');
      if (attend) classe += ' attention';
    } else if (p.raison === 'sans-psn') {
      texte = s && s.etat === 'refus' ? '' : ': pas de base ' + P.base + ' tant que le PSN n’est pas donné';
      classe += ' rien';
    } else if (p.raison === 'aucune') {
      texte = '— aucune ligne' + motFiltres(d) + ' pour ce PSN : « ' + c.onglet + ' » ne sera pas touché';
      classe += ' attention';
    } else {
      texte = '— ' + nb(p.n) + ' ligne' + (p.n > 1 ? 's' : '') + motFiltres(d) + ' → ' + vers();
    }
    part.className = classe;
    part.textContent = texte;
    li.setAttribute('data-lignes', p ? String(p.n) : '');
  }

  /* Pourquoi « Importer » attend : rien à importer (pas de message), une
     lecture en cours, un fichier qui ne s'importe pas, un nom à vérifier, un
     PSN à enregistrer, un extract SEE qui ne se trie pas. */
  function raisonDAttendre() {
    var gates = cases.filter(function (k) { return k.f && k.etat !== 'fait' && k.etat !== 'echec'; });
    var see = caseSee && caseSee.f && caseSee.etat !== 'fait' && caseSee.etat !== 'echec' ? caseSee : null;
    var actives = gates.concat(see ? [see] : []), i;
    if (relecture) return 'Relecture de la liste des contrats…';
    if (contratsPerimes) return 'La liste des contrats n’a pas pu être relue après l’import : fermer cette fenêtre et la rouvrir (menu Suivi FWD) avant d’importer d’autres fichiers.';
    var sansFichier = cases.filter(function (k) { return k.nouveau && !k.f && k.etat !== 'fait' && k.nom.valeur; })[0];
    if (!actives.length) return sansFichier ? 'Choisir l’export GATES du nouveau contrat « ' + sansFichier.nom.valeur + ' » dans sa case.' : ' ';
    if (actives.some(function (k) { return k.etat === 'attente' || k.etat === 'lecture'; })) return 'Lecture des fichiers…';
    var ko = actives.filter(function (k) { return k.etat === 'erreur'; });
    if (ko.length) {
      return ko.length === 1 ? 'Retirer « ' + ko[0].f.name + ' » de la case « ' + libelleCase(ko[0]) + ' », qui ne s’importe pas (✗) — ou y mettre le bon fichier.'
        : ko.length + ' cases portent un fichier qui ne s’importe pas (✗) : retirer chacun, ou y mettre le bon.';
    }
    /* Le même fichier dans deux cases : chaque contrat a son export. */
    for (i = 0; i < actives.length; i++) {
      for (var j = i + 1; j < actives.length; j++) {
        var a = actives[i].f, b = actives[j].f;
        if (a.name === b.name && a.size === b.size && a.lastModified === b.lastModified) {
          return 'Le même fichier, « ' + a.name + ' », est dans les cases « ' + libelleCase(actives[i]) + ' » et « ' + libelleCase(actives[j]) + ' » : chaque contrat a son propre export.';
        }
      }
    }
    var noms = {};
    for (i = 0; i < cases.length; i++) {
      var k = cases[i];
      if (!k.nouveau || k.etat === 'fait') continue;
      if (k.f && k.nom.etat === 'vide') return 'Donner un nom au nouveau contrat de « ' + k.f.name + ' ».';
      if (k.nom.etat === 'attente') return 'Vérification du nom « ' + k.nom.valeur + ' »…';
      if (k.nom.etat === 'refus' && (k.f || k.nom.valeur)) return 'Nouveau contrat' + (k.f ? ' de « ' + k.f.name + ' »' : '') + ' : ' + k.nom.message;
      if (k.nom.etat === 'ok') {
        if (noms[norm(k.nom.valeur)]) return 'Deux cases pour le même nouveau contrat « ' + k.nom.valeur + ' » : en annuler une.';
        noms[norm(k.nom.valeur)] = true;
        if (!k.f) return 'Choisir l’export GATES du nouveau contrat « ' + k.nom.valeur + ' » dans sa case — ou l’annuler.';
      }
    }
    var cibles = ciblesSee();
    if (P.colonnePsn) {
      for (i = 0; i < cibles.length; i++) {
        var s = saisiePsn(cibles[i].id);
        if (s.etat === 'attente') return 'Enregistrement du PSN de « ' + cibles[i].id + ' »…';
        if (s.etat === 'refus') return 'PSN de « ' + cibles[i].id + ' » : ' + s.message;
      }
    }
    if (see && see.lu) {
      var d = see.lu, tri = etatTri(d), parts = partsSee(d);
      if (tri.manquent.length && !see.sansTri) {
        var possible = !d.tri.manquePsn || cibles.length === 1;
        return '« ' + see.f.name + ' » n’a pas de colonne ' + tri.manquent.join(', ni de colonne ') + ' : ' + (possible
          ? 'cocher « importer sans ce tri » dans la case ' + P.base + ', ou retirer le fichier.'
          : cibles.length ? 'sans elle, l’extract ne se partage pas entre les ' + cibles.length + ' contrats — demander l’extract ' + P.base + ' avec cette colonne, ou retirer le fichier.'
            : 'aucun contrat pour le recevoir — retirer le fichier.');
      }
      if (!cibles.length) return 'Aucun contrat pour la base ' + P.base + ' : ajouter d’abord l’export GATES d’un contrat (« Ajouter un contrat… »).';
      if (!tri.parPsn && cibles.length !== 1) return 'L’extract ' + P.base + ' va tout entier à un seul contrat, et le classeur en a ' + cibles.length + ' : il faut la colonne ' + (P.colonnePsn || 'des PSN') + ' pour le partager.';
      if (tri.parPsn && !parts.some(function (p) { return p.jetons && p.jetons.length; })) {
        return 'Aucun contrat n’a de PSN : taper celui de chaque contrat (le numéro de sa machine) dans la case ' + P.base + ', ou retirer le fichier.';
      }
      if (!parts.some(function (p) { return p.n > 0; })) {
        return 'Aucune ligne de l’extract ' + P.base + ' ne porte le PSN des contrats (' + parts.filter(function (p) { return p.jetons && p.jetons.length; })
          .map(function (p) { return p.cible.id + ' ' + saisieTexte(p.jetons); }).join(', ') + ') : vérifier les PSN, ou retirer le fichier.';
      }
    }
    return '';
  }
  function majTout() {
    cases.forEach(dessiner);
    dessinerSee();
    var raison = raisonDAttendre();
    $('blocage').textContent = raison.trim();
    $('importer').disabled = enCours || !!raison;
    $('option-archiver').hidden = !cases.some(function (k) { return k.etat === 'lu'; });
    $('ajouter').hidden = !P.nouveauPermis;
    $('ajouter').disabled = enCours;
  }
  function verrouiller(oui) {
    ['toutes', 'archiver', 'fermer', 'importer', 'ajouter'].forEach(function (id) { if ($(id)) $(id).disabled = oui; });
    cases.forEach(dessiner);
    dessinerSee();
  }

  // ------------------------------------------------------------ la liste des contrats, relue
  /* Après un import, la liste des contrats est relue : un contrat créé à ce
     tour-là a désormais sa case, une base SEE renommée son nom. La case qui
     l'a créé devient la sienne, avec son résultat ; ce que la fenêtre
     savait de leurs plans (ENSEMBLES) est oublié. */
  function relireContrats() {
    relecture = appelerAvecReprise('importContrats', []).then(function (liste) {
      if (!Array.isArray(liste)) throw erreur('liste illisible');
      P.contrats = liste;
      ENSEMBLES = {};
      contratsPerimes = false;
      reconstruireCases();
    }).catch(function () {
      contratsPerimes = true;
    }).then(function () {
      relecture = null;
    });
    return relecture;
  }
  function reconstruireCases() {
    var gardees = [];
    P.contrats.forEach(function (c) {
      var k = cases.filter(function (x) { return !x.nouveau && norm(x.id) === norm(c.id); })[0];
      if (!k) {
        k = cases.filter(function (x) { return x.nouveau && x.nom.etat === 'ok' && norm(x.nom.valeur) === norm(c.id) && x.etat === 'fait'; })[0];
        if (k) {
          var vieux = k.el;
          k.nouveau = false;
          k.id = c.id;
          creerCase(k);
          if (vieux.parentNode) vieux.parentNode.replaceChild(k.el, vieux);
        }
      }
      if (!k) k = nouvelleCase('gates', c.id, false);
      k.id = c.id;
      gardees.push(k);
      /* Le PSN gardé par le serveur devient celui de la fenêtre, sauf s'il est en cours de saisie. */
      var s = saisiesPsn[norm(c.id)];
      if (s && s.etat !== 'attente' && s.etat !== 'refus' && !s.touche) { s.texte = (c.psn || []).join(', '); s.jetons = (c.psn || []).map(norm); s.source = c.psnSource; }
    });
    cases.forEach(function (x) {
      if (gardees.indexOf(x) !== -1) return;
      if (x.nouveau) gardees.push(x);
      else if (x.el && x.el.parentNode) x.el.parentNode.removeChild(x.el);
    });
    cases = gardees;
    rangerCases();
  }

  // ------------------------------------------------------------ importer
  /* Les exports GATES d'abord — un nouveau contrat existe avant sa base SEE
     —, case par case ; puis la base SEE de chaque contrat qui a un PSN,
     tirée de l'extract lu. Chacun pour lui-même : un échec n'arrête pas les
     suivants. À la fin, une ligne par case et par base. */
  function importerTout() {
    if (enCours || $('importer').disabled) return;
    var gates = cases.filter(function (k) { return k.etat === 'lu'; });
    var see = caseSee && caseSee.etat === 'lu' ? caseSee : null;
    var parts = see ? partsSee(see.lu) : [];
    var archiver = !$('option-archiver').hidden && $('archiver').checked, bilans = [], kg = 0, ks = 0;
    var envois = parts.filter(function (p) { return p.n > 0; }), nombre = gates.length + envois.length, rang = 0;
    enCours = true;
    verrouiller(true);
    $('consigne').hidden = false;
    dire('');
    function suivantGates() {
      if (kg >= gates.length) return Promise.resolve();
      var k = gates[kg++];
      return importerGates(k, archiver, ++rang, nombre).then(function (b) { bilans.push(b); return suivantGates(); });
    }
    function suivantSee() {
      if (!see) return Promise.resolve();
      if (ks >= parts.length) return Promise.resolve();
      var p = parts[ks++];
      /* Un contrat que cet import devait créer, et qui ne l'a pas été : pas de base. */
      if (p.cible.nouveau && !cases.some(function (k) { return k.nouveau && norm(k.nom.valeur) === norm(p.cible.id) && k.etat === 'fait'; })) {
        bilans.push({ ok: false, see: true, classe: 'erreur', html: '✗ « ' + ech(p.cible.onglet) + ' » : pas créé — le contrat « ' + ech(p.cible.id) + ' » n’a pas été créé (voir sa case).' });
        return suivantSee();
      }
      if (!p.n) {
        bilans.push(p.raison === 'aucune'
          ? { ok: true, see: true, avertissement: true, classe: 'avertissement', html: '⚠ « ' + ech(p.cible.id) + ' » : aucune ligne' + ech(motFiltres(see.lu)) + ' pour le PSN ' +
              ech(saisieTexte(p.jetons)) + ' — « ' + ech(p.cible.onglet) + ' » n’est pas touché.' }
          : { ok: true, see: true, neutre: true, classe: 'neutre', html: '– « ' + ech(p.cible.id) + ' » : ' + (p.raison === 'sans-psn' ? 'pas de PSN, pas de base ' + ech(P.base) : 'pas de base ' + ech(P.base)) +
              ' — « ' + ech(p.cible.onglet) + ' » n’est pas touché.' });
        return suivantSee();
      }
      return importerSee(see, p, ++rang, nombre).then(function (b) { bilans.push(b); return suivantSee(); });
    }
    suivantGates().then(function () {
      return enregistrerPsnDesNouveaux(bilans);
    }).then(suivantSee).then(function () {
      if (see) {
        var lignesSee = bilans.filter(function (b) { return b.see; });
        see.etat = lignesSee.some(function (b) { return !b.ok; }) ? 'echec' : 'fait';
        see.resultat = { classe: see.etat === 'fait' ? 'ok' : 'erreur', html: bilans.filter(function (b) { return b.see; })
          .map(function (b) { return '<div class="' + b.classe + '">' + b.html + '</div>'; }).join('') };
      }
      var echec = bilans.some(function (b) { return !b.ok; }), alerte = bilans.some(function (b) { return b.avertissement; });
      dire(bilans.map(function (b) { return '<div class="' + b.classe + '">' + b.html + '</div>'; }).join('') +
        (bilans.some(function (b) { return b.ok && !b.neutre; }) ? '<div class="suite">Rouvrir le tableau de bord pour voir les nouveaux chiffres : menu Suivi FWD → Ouvrir le tableau de bord.</div>' : ''),
        echec ? 'erreur' : 'ok' + (alerte ? ' avertissement' : ''));
      $('fermer').classList.add('principal');
      $('importer').classList.remove('principal');
    }, function (e) {
      dire(ech('Erreur inattendue : ' + (e && e.message ? e.message : e)), 'erreur');
    }).then(function () {
      /* Un contrat a pu naître, une base changer de nom : le tour suivant
         doit le savoir. */
      return relireContrats();
    }).then(function () {
      enCours = false;
      suivi = null;
      $('consigne').hidden = true;
      $('progres').textContent = '';
      verrouiller(false);
      majTout();
      try { $('etat').scrollIntoView({ block: 'nearest' }); } catch (e) { /* rien */ }
    });
  }
  /* Le PSN tapé pour un contrat ajouté : gardé une fois le contrat créé. */
  function enregistrerPsnDesNouveaux(bilans) {
    if (!P.colonnePsn) return Promise.resolve();
    var faits = cases.filter(function (k) { return k.nouveau && k.etat === 'fait' && k.nom.etat === 'ok'; });
    var i = 0;
    function suivant() {
      if (i >= faits.length) return Promise.resolve();
      var k = faits[i++], s = saisiesPsn[norm(k.nom.valeur)];
      if (!s || !s.touche || s.etat === 'refus') return suivant();
      return appelerAvecReprise('importEnregistrerPsn', [k.nom.valeur, s.texte]).then(function (rep) {
        s.enregistre = true;
        s.source = rep && rep.source ? rep.source : 'fenetre';
      }, function (e) {
        bilans.push({ ok: true, avertissement: true, classe: 'avertissement', html: '⚠ Le PSN de « ' + ech(k.nom.valeur) + ' » (' + ech(s.texte) +
          ') n’a pas été gardé pour les fois suivantes (' + ech(e.message) + ') : le retaper à la prochaine ouverture.' });
      }).then(suivant);
    }
    return suivant();
  }
  function importerGates(k, archiver, rang, nombre) {
    var d = k.lu, contrat = contratDe(k), etat = { fin: false }, nom = '« ' + ech(k.f.name) + ' »';
    var cible = { sorte: 'gates', contrat: contrat, nouveau: k.nouveau };
    /* Le pied nomme toujours la case qui part — et son rang quand il y en a plusieurs. */
    var avant = (nombre > 1 ? rang + ' sur ' + nombre + ' — ' : '') + '« ' + libelleCase(k) + ' » : ';
    k.etat = 'envoi';
    k.texteEnvoi = '';
    suivi = function (part, texte) {
      avancer(k, part);
      if (texte !== undefined) {
        k.texteEnvoi = texte;
        k.el.querySelector('.resultat').textContent = texte;
        $('progres').textContent = avant + texte;
      }
    };
    dessiner(k);
    var largeur = d.largeur;
    var bloc = d.lignes.map(function (l) {
      var out = [];
      for (var j = 0; j < largeur; j++) out.push(l[j] === undefined || l[j] === null ? '' : String(l[j]));
      return out;
    });
    return envoyer(cible, bloc, largeur, d.fusions, etat).then(function (fin) {
      return bilanGatesImporte(k, fin, archiver);
    }).then(function (b) {
      k.etat = 'fait';
      k.resultat = b;
      return b;
    }, function (e) {
      var b = { ok: false, classe: 'erreur', html: '✗ ' + nom + ' → « ' + ech(contrat) + ' » : ' + ech(messageDErreur(e, etat, contrat, !k.nouveau)) };
      k.etat = 'echec';
      k.resultat = b;
      return b;
    }).then(function (b) {
      suivi = null;
      dessiner(k);
      return b;
    });
  }
  /* La base SEE d'un contrat : la ligne « Trié à l’import » quand l'extract
     a été trié — le serveur la relit, la page dira de quelles lignes elle
     parle —, l'en-tête, puis les lignes de ce contrat. */
  function importerSee(k, p, rang, nombre) {
    var d = k.lu, c = p.cible, etat = { fin: false };
    /* Un seul extract fait plusieurs bases : le pied et la case nomment toujours celle qui part. */
    var avant = (nombre > 1 ? rang + ' sur ' + nombre + ' — ' : '') + '« ' + c.onglet + ' » : ';
    k.etat = 'envoi';
    k.texteEnvoi = '';
    suivi = function (part, texte) {
      avancer(k, part);
      if (texte !== undefined) {
        k.texteEnvoi = avant + texte;
        k.el.querySelector('.resultat').textContent = avant + texte;
        $('progres').textContent = avant + texte;
      }
    };
    dessinerSee();
    var lignes = d.lignes;
    if (p.jetons) {
      var oui = cellulesDe(d, p.jetons).oui;
      lignes = d.lignes.filter(function (l, i) { return oui[d.psn[i]]; });
    }
    var largeur = d.entete.length, tri = partsTri(d, p.jetons), bloc = [d.entete].concat(lignes);
    if (tri.length) {
      var jour = new Date(), deuxC = function (n) { return (n < 10 ? '0' : '') + n; };
      var marque = [P.marqueTri + tri.join(' · ') + ' — ' + nb(lignes.length) + ' ligne' + (lignes.length > 1 ? 's' : '') + ' gardée' + (lignes.length > 1 ? 's' : '') +
        ' sur ' + nb(d.lues) + ' · « ' + k.f.name + ' », le ' + deuxC(jour.getDate()) + '/' + deuxC(jour.getMonth() + 1) + '/' + jour.getFullYear()];
      while (marque.length < largeur) marque.push('');
      bloc.unshift(marque);
    }
    var court = tri.length ? (p.jetons ? 'PSN ' + saisieTexte(p.jetons) : '') + (p.jetons && d.tri.filtres.length ? ' · ' : '') +
      d.tri.filtres.map(function (x) { return x.valeurs.join(', '); }).join(' · ') : '';
    return envoyer({ sorte: 'see', contrat: c.id }, bloc, largeur, null, etat).then(function (fin) {
      var bon = fin.etat === 'ok' || fin.etat === 'non relu';
      return { ok: bon, see: true, classe: bon ? 'ok' : 'erreur', html: (bon ? '✓ ' : '✗ ') + '« ' + ech(k.f.name) + ' » → <b>' + nb(fin.lignes) + ' ligne' +
        (fin.lignes > 1 ? 's' : '') + '</b> dans l’onglet <b>« ' + ech(fin.onglet) + ' »</b> (' + fin.colonnes + ' colonne' + (fin.colonnes > 1 ? 's' : '') +
        (court ? ' ; ' + ech(court) : '') + ')' + (bon ? ' : la comparaison est prête.' : '. Mais la page ne la lit pas (' + ech(fin.etat) + ') : menu Suivi FWD → Diagnostic.') };
    }, function (e) {
      return { ok: false, see: true, classe: 'erreur', html: '✗ « ' + ech(k.f.name) + ' » → « ' + ech(c.onglet) + ' » : ' + ech(messageDErreur(e, etat, c.onglet, c.existe)) };
    }).then(function (b) {
      suivi = null;
      k.etat = 'lu';
      return b;
    });
  }
  /* Un export GATES posé : ce que la page y lit (le serveur l'a relu avec sa
     propre logique), puis le relevé de la semaine — seulement si la colonne
     suivie est là : sans elle, l'archivage refuserait de toute façon. */
  function bilanGatesImporte(k, fin, archiver) {
    var d = k.lu, debut = '« ' + ech(k.f.name) + ' » → onglet <b>« ' + ech(fin.onglet) + ' »</b> ' + (fin.nouveau ? 'créé (nouveau contrat)' : 'remplacé') +
      (fin.renommes && fin.renommes.length ? ' ; ' + fin.renommes.map(function (x) {
        return 'l’onglet « ' + ech(x.de) + ' » devient « ' + ech(x.vers) + ' »';
      }).join(', ') + ' (il servait au seul contrat d’avant)' : '') + ' : ';
    var avis = function (html) { return { ok: true, avertissement: true, classe: 'avertissement', html: '⚠ ' + html }; };
    if (fin.etat !== 'ok') return avis(debut + nb(fin.lignes) + ' lignes posées, mais l’onglet n’a pas pu être relu (' + ech(fin.message || fin.etat) + ') : menu Suivi FWD → Diagnostic.');
    var texte = debut + '<b>' + nb(fin.plans) + ' plan' + (fin.plans > 1 ? 's' : '') + '</b>';
    if (fin.fusionsRatees) texte += ', ' + fin.fusionsRatees + ' cellule(s) fusionnée(s) non recréée(s)';
    var perte = perteFusions(d);
    if (!fin.colonneSuivie) {
      return avis(texte + ', mais la colonne suivie est introuvable : la page n’en lira aucune' + (archiver ? ', et le relevé n’est pas archivé' : '') + '. ' +
        (perte ? majuscule(perte) + ' ne garde pas les cellules fusionnées de la ligne des groupes, par lesquelles la page la reconnaît : importer plutôt l’export Excel (.xlsx, ou .xls d’Excel 97-2003) de GATES.'
          : 'Menu Suivi FWD → Diagnostic dit quelles colonnes il a lues.'));
    }
    texte += ', colonne suivie ' + ech(fin.colonneSuivie.replace(' > ', ' › ')) +
      (fin.conceptDemande ? (fin.concept ? ', concept harnais lu' : ', mais le concept harnais est introuvable') : '');
    var csv = perte ? ' ' + majuscule(perte) + ' ne garde pas les cellules fusionnées : la page a déduit les groupes de proche en proche ; l’export Excel (.xlsx, ou .xls d’Excel 97-2003) est plus sûr.' : '';
    var fini = function (html) { return csv ? avis(html + csv) : { ok: true, classe: 'ok', html: '✓ ' + html }; };
    if (!archiver) return fini(texte + '.');
    progres(1, 'Archivage du relevé ' + P.semaine + ' de « ' + fin.onglet + ' »…');
    return appelerAvecReprise('importArchiverReleve', [fin.onglet, !!fin.nouveau]).then(function (a) {
      if (a && a.ok) return fini(texte + '. Relevé ' + ech(a.dite) + ' archivé (' + nb(a.plans) + ' plans, ' + nb(a.valides) + ' validés).');
      return avis(texte + '. Relevé ' + ech(a && a.dite ? a.dite : P.semaine) + ' non archivé : ' + ech(a && a.message ? a.message : '?') + ' L’import, lui, est fait.' + csv);
    }, function (e) {
      return avis(texte + '. Relevé ' + ech(P.semaine) + ' non archivé (' + ech(e.message) + ') : menu Suivi FWD → Archiver le relevé de cette semaine. ' +
        'L’import, lui, est fait.' + csv);
    });
  }

  // ------------------------------------------------------------ la fenêtre
  P.contrats.forEach(function (c) { cases.push(nouvelleCase('gates', c.id, false)); });
  rangerCases();
  if (P.base) {
    caseSee = nouvelleCase('see', '', false);
    $('case-see').appendChild(caseSee.el);
  }
  /* Un classeur sans contrat : la case du premier, ouverte d'office. */
  if (!P.contrats.length && P.nouveauPermis) cases.push(nouvelleCase('gates', '', true));
  rangerCases();
  $('ajouter').addEventListener('click', function () {
    var k = ajouterContrat();
    if (k) k.el.querySelector('.nom').focus();
  });
  /* Un fichier lâché à côté des cases : rien n'est deviné, la fenêtre dit où le poser. */
  document.addEventListener('dragover', function (e) { e.preventDefault(); });
  document.addEventListener('drop', function (e) {
    e.preventDefault();
    if (enCours) return;
    dire(ech('Déposer chaque fichier sur sa case : l’export GATES d’un contrat sur « GATES » suivi de son nom' + (P.base ? ', l’extract ' + P.base + ' sur la case « ' + P.base + ' »' : '') + '.'));
  });
  /* « Garder aussi les autres colonnes » se lit à la lecture : l'extract
     SEE déjà lu — ou en erreur, trop gros peut-être — est relu. */
  if ($('toutes')) {
    $('toutes').addEventListener('change', function () {
      var k = caseSee;
      if (k && k.f && (k.etat === 'lu' || k.etat === 'erreur')) {
        k.etat = 'attente';
        k.lu = null;
        k.resultat = null;
        k.lecture = ++lectures;
        aLire.push(k);
      }
      majTout();
      lireSuivant();
    });
  }
  $('importer').addEventListener('click', importerTout);
  $('fermer').addEventListener('click', function () { if (!enCours && window.google && google.script && google.script.host) google.script.host.close(); });
  cases.forEach(dessiner);
  dessinerSee();
  majTout();
}
