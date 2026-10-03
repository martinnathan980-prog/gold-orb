/**
 * Suivi FWD — tableau de bord des plans d'intégration électrique
 * =============================================================
 * Côté serveur (Google Apps Script).
 *
 * Ce fichier ne fait que six choses :
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
 *      rapprocher des plans (CONFIG.RAPPROCHEMENT) — la page fait le reste.
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
 * produits (le diagnostic le rappelle).
 */

/**
 * La livraison. Les quatre fichiers collés dans Apps Script — Code, Index,
 * Styles, Javascript — portent la même édition, posée par la construction
 * (tests/split-prototype.js) : NE PAS LA MODIFIER À LA MAIN. La page et le
 * Diagnostic comparent les quatre : un fichier resté à une livraison
 * précédente, ou coupé au collage, est nommé — au lieu d'une page blanche.
 */
const EDITION = '4bf7a55';

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
   *   'Réalisation FWD > Avancement'. Introuvable dans un extract, la
   *   détection reprend la main — et le Diagnostic le dit.
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
   */
  RAPPROCHEMENT: {
    FEUILLE: '',
    NOM: 'SEE',
    CLE_REFERENCE: ['NAME', 'SOL.', 'Cust.V'],
    ESSENTIELLES: []
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
  if (e && e.parameter && e.parameter.frais) marquerDonneesModifiees();
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
    .addItem('Archiver le relevé de cette semaine', 'enregistrerInstantaneHebdo')
    .addItem('Supprimer le relevé de cette semaine', 'supprimerDernierReleve')
    .addItem('Archiver l\'onglet affiché pour une semaine passée…', 'archiverSemainePassee')
    .addSeparator()
    .addItem(libelleImport(), 'importerSecondeBase')
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
  if (cellules.length < 10) return false;
  return CONFIG.MOTS_CLES_ENTETE.map(normaliser)
    .filter(function (m) { return cellules.indexOf(m) !== -1; }).length >= 2;
}

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
  return 'Aucun onglet de données exploitable dans ce classeur : ' +
    (vides.length
      ? vides.join(', ') + (vides.length > 1 ? ' sont vides' : ' est vide') +
        ' — coller l\'export GATES en A1 d\'un onglet nommé du contrat.'
      : 'aucun onglet visible.');
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
 * Index de la colonne d'avancement FWD.
 *
 * L'export GATES compte vingt-sept colonnes dont l'intitulé contient
 * « avancement » : une seule est le FWD (« Avancement », sous le groupe
 * « Réalisation FWD »), les autres appartiennent aux blocs répétés par
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
  const motifs = ['reference ud', 'reference', 'ref', 'identifiant', 'numero de plan', 'plan'];
  for (let m = 0; m < motifs.length; m++) {
    for (let i = 0; i < entetes.length; i++) {
      if (normaliser(entetes[i]).indexOf(motifs[m]) !== -1) return i;
    }
  }
  return 0;
}

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
                  'y coller l\'export GATES du contrat en A1.'].filter(Boolean).join(' '),
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
   archivage, une suppression, un dépôt (marquerDonneesModifiees), un onglet
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

/** Toute modification du classeur rend caducs les paquets en cache. */
function marquerDonneesModifiees() {
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
  marquerDonneesModifiees();
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
    const verrou = LockService.getDocumentLock();
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

/** Pour le Diagnostic : « S40 : 37 ouvertures, 12 personnes · S39 : … », les plus récentes d'abord. */
function resumeConsultations() {
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

  /* Les contrats : un onglet visible chacun. Sans aucun, rien à diagnostiquer. */
  let contrats = [];
  try {
    contrats = listerContrats(classeur);
    if (contrats.length === 0) {
      throw new Error(messageSansContrat(classeur));
    }
  } catch (err) {
    dire('✗ Onglet de données : ' + err.message);
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
           'ligne d\'au moins dix intitulés). Si c\'est un export, le recoller entier en A1.');
    }
  });

  let tousLisibles = true;
  contrats.forEach(function (c) {
    if (contrats.length > 1) { dire(''); dire('— Contrat « ' + c.nom + ' » —'); }
    if (!diagnostiquerContrat(classeur, c, dire)) tousLisibles = false;
  });

  /* L'ancien onglet d'historique, à côté de plusieurs contrats, n'appartient
     à personne : ses relevés ne s'afficheront nulle part tant qu'il n'est pas
     renommé. On le dit, on ne le renomme pas à la place de quelqu'un. */
  if (contrats.length > 1 && classeur.getSheetByName(CONFIG.FEUILLE_HISTORIQUE)) {
    dire('');
    dire('⚠ L\'ancien onglet « ' + CONFIG.FEUILLE_HISTORIQUE + ' » n\'est rattaché à aucun contrat.');
    dire('   → le renommer « ' + nomFeuilleHistorique('<nom du contrat>') +
         ' » rend ses relevés au contrat qui les a produits.');
  }
  /* Un onglet de contrat renommé (« Feuille 1 » devenu « HDK ») laisse son
     historique sous l'ancien nom : la page repart d'un seul relevé, le
     journal reste vide. On le dit (débrief 16). */
  historiquesOrphelins(classeur, contrats).forEach(function (o) {
    dire('');
    dire('⚠ L\'onglet d\'historique « ' + o.nom + ' » (' + o.releves + ' relevé' + (o.releves > 1 ? 's' : '') +
         ') n\'est rattaché à aucun contrat :');
    dire('   l\'onglet de son contrat a sans doute été renommé. Le renommer « ' + nomFeuilleHistorique('<nom du contrat>') +
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
    const t0 = Date.now();
    const modele = construireModele(contrats[0].id);
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
           ? ' (contrat « ' + contrats[0].nom + ' », le premier ; les autres se chargent à la demande)'
           : ''));
    dire('   préparé en ' + secondes(t4 - t3) + ' — lecture de GATES ' + secondes(t1 - t0) +
         ', de l\'historique ' + secondes(t2 - t1) + ', de la seconde base ' + secondes(t3 - t2));
    if (cacheDuClasseur()) dire('   ensuite gardé en cache (6 h) : les ouvertures suivantes ne relisent rien, tant que le classeur ne change pas');
  } catch (err) {
    dire('✗ Paquet envoyé à la page : ' + (err && err.message ? err.message : err));
    tousLisibles = false;
  }

  /* Les consultations de la page, sans nom (débrief 18). */
  const consultations = resumeConsultations();
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
  (plusieurs ? contrats : [contrats[0] || null]).forEach(function (c) {
    if (!diagnostiquerSecondeBaseDe(classeur, c ? c.id : undefined, plusieurs ? ' de « ' + c.nom + ' »' : '', dire)) tout = false;
  });
  const base = feuilleRapprochement();
  /* Un import interrompu (la fenêtre fermée en cours d'envoi) laisse son
     onglet temporaire : le dire, il ne sert à rien. Le prochain import le
     retire de lui-même. */
  classeur.getSheets().filter(function (f) { return estOngletImport(f.getName()); }).forEach(function (f) {
    dire('⚠ L\'onglet « ' + f.getName() + ' » est le reste d\'un import interrompu : le supprimer, ou relancer l\'import (il le retire).');
  });
  if (plusieurs && base) {
    const generique = classeur.getSheets().filter(function (f) { return nomCompact(f.getName()) === nomCompact(base); })[0];
    if (generique) {
      dire('⚠ L\'onglet « ' + generique.getName() + ' » ne dit pas à quel contrat il appartient : il n\'est lu pour aucun.');
      dire('   → le renommer « ' + base + ' ' + contrats[0].nom + ' » (ou le nom de son contrat) : chaque contrat a sa base.');
    }
  }
  return tout;
}

function diagnostiquerSecondeBaseDe(classeur, contrat, pour, dire) {
  const base = lireSecondeBase(classeur, contrat);
  const cfg = CONFIG.RAPPROCHEMENT || {};
  const nom = '« ' + (String(cfg.NOM || feuilleRapprochement() || '').trim() || 'seconde base') + ' »' + pour;
  switch (base.etat) {
    case 'sans-configuration':
      dire('– Seconde base : ' + (!base.onglet
        ? 'aucun nom d\'onglet (RAPPROCHEMENT.FEUILLE et NOM vides)'
        : 'aucune référence (RAPPROCHEMENT.CLE_REFERENCE vide)') + ' — pas de rapprochement.');
      return true;
    case 'absent':
      dire('– Seconde base ' + nom + ' : aucun onglet « ' + base.onglet + ' » — pas de rapprochement.');
      dire('   → menu Suivi FWD → ' + libelleImport() + ', sans ouvrir le fichier dans Excel ; ou un onglet nommé « ' +
           base.onglet + ' », l\'extract collé en A1 tel quel, avec ses colonnes ' + base.cles.join(', ') + '.');
      return true;
    case 'vide':
      dire('⚠ Seconde base ' + nom + ' : l\'onglet « ' + base.onglet + ' » est vide — pas de rapprochement.');
      dire('   → menu Suivi FWD → ' + libelleImport() + ', ou coller l\'extract en A1.');
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
      return true;
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
      dire('✗ L\'onglet est vide : collez l\'export GATES en A1.');
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
      dire('   → recoller l\'extract entier en A1, avec ses lignes de groupes et d\'en-têtes. Le reste de cet onglet n\'est pas');
      dire('     détaillé : ses « intitulés » seraient des cellules de plans, qui ne sortent pas d\'ici.');
      return false;
    }

    const modele = construireModele(contrat.id);
    /* Une référence répétée ne compte qu'une fois, comme dans le relevé et sur la page. */
    const uniques = plansUniques(modele.plans);
    dire('✓ ' + modele.colonnes.length + ' colonnes, ' + uniques.length + ' plans' +
         (uniques.length < modele.plans.length ? ' (' + modele.plans.length + ' lignes)' : ''));

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
      const compte = { termine: 0, encours: 0, afaire: 0, vide: 0 };
      uniques.forEach(function (p) { compte[classerFWD(p.avancement)]++; });
      dire('  ' + compte.termine + ' validés, ' + compte.encours + ' en cours, ' +
           compte.afaire + ' à faire, ' + compte.vide + ' non renseignés');
      direValeurs(dire, uniques, 'avancement');
    }
    if (CONFIG.COLONNE_CONCEPT) {
      const colConcept = modele.cleConcept ? modele.colonnes.filter(function (c) { return c.cle === modele.cleConcept; })[0] : null;
      if (colConcept) {
        const compteC = { termine: 0, encours: 0, afaire: 0, vide: 0 };
        uniques.forEach(function (p) { compteC[classerFWD(p[modele.cleConcept])]++; });
        dire('✓ Concept harnais : colonne « ' + colConcept.titre + ' »' + (colConcept.groupe ? ', groupe « ' + colConcept.groupe + ' »' : ''));
        dire('  ' + compteC.termine + ' validés, ' + compteC.encours + ' en cours, ' +
             compteC.afaire + ' à faire, ' + compteC.vide + ' non renseignés');
        direValeurs(dire, uniques, modele.cleConcept, true);
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
      dire('   Seule la première ligne de chaque référence compte, comme sur la page et dans le relevé. Recoller l\'export sur un onglet vidé.');
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
      dire('   → Suivi FWD → Archiver le relevé de cette semaine.');
      dire('     Sans relevé, pas de courbe ni de fin estimée.');
    } else {
      dire('  du ' + histo[0].semaine + ' au ' + histo[histo.length - 1].semaine);
      const cellulesCarte = feuilleHisto.getLastColumn() - ENTETES_HISTORIQUE.length + 1;
      if (cellulesCarte > 1) {
        dire('  carte plan par plan sur ' + cellulesCarte + ' cellules par relevé, au plus');
      }
      direJournal(dire, histo, modele);
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
function direJournal(dire, histo, modele) {
  const semaine = numeroSemaineISO(new Date());
  const dernier = histo[histo.length - 1];
  if (dernier.semaine !== semaine) {
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
        dire('   Le journal restera vide. Recoller le dernier export de GATES, puis archiver de nouveau.');
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
  if (dernier.plans) {
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
 * contrats, chacun a le sien, et l'ancien onglet n'est plus lu (le diagnostic
 * dit comment le rattacher). L'onglet propre au contrat l'emporte toujours
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
  attendus[normaliser(CONFIG.FEUILLE_HISTORIQUE)] = true;       // l'ancien onglet sans suffixe : traité à part
  return classeur.getSheets()
    .filter(function (f) { return estOngletHistorique(f.getName()) && !attendus[normaliser(f.getName())]; })
    .map(function (f) { return { nom: f.getName(), releves: Math.max(0, f.getLastRow() - 1) }; });
}

/** Les contrats qui n'ont pas encore d'onglet d'historique : ceux qu'un orphelin empêche d'archiver. */
function contratsSansHistorique(classeur, contrats) {
  return contrats.filter(function (c) { return !getFeuilleHistorique(classeur, c.id, false); });
}

/**
 * Ce que la page dit des historiques orphelins, au-dessus de la barre. Le
 * renommage n'est proposé que vers un contrat qui n'a pas encore
 * d'historique — le contrat affiché d'abord : c'est lui dont l'archivage est
 * refusé d'ici là (archiverContrat). Sinon, rien à faire.
 */
function avisOrphelins(orphelins, contrat, sansHistorique) {
  if (!orphelins.length) return '';
  const cible = sansHistorique.indexOf(contrat) !== -1 ? contrat : sansHistorique[0];
  return orphelins.map(function (o) {
    return 'L\'onglet d\'historique « ' + o.nom + ' » (' + o.releves + ' relevé' + (o.releves > 1 ? 's' : '') +
      ') n\'est rattaché à aucun contrat — un onglet de contrat renommé ?';
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

/** Ancienneté d'un plan, en toutes lettres — même découpage que côté page. */
function ancienneteDepuis(valeur, reference) {
  const m = /(\d{4})[-\/.](\d{1,2})/.exec(String(valeur || ''));
  if (!m) return '—';
  const mois = (reference.getUTCFullYear() - Number(m[1])) * 12 +
               (reference.getUTCMonth() + 1 - Number(m[2]));
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
        ? ancienneteDepuis(p[modele.cleDate], reference)
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

  const detail = [];
  const erreurs = [];
  const sansPlan = [];
  contrats.forEach(function (c) {
    try {
      detail.push(archiverContrat(classeur, c, semaine));
    } catch (err) {
      if (err && err.sansPlan) sansPlan.push(c.nom);
      else erreurs.push('« ' + c.nom + ' » : ' + (err && err.message ? err.message : err));
    }
  });

  /* La semaine se dit comme sur la page : « S39 », pas l'étiquette 2026-S39. */
  const dite = 'S' + parseInt(semaine.slice(6), 10);
  if (erreurs.length) {
    throw new Error('Relevé ' + dite + ' — ' +
      (detail.length ? detail.length + ' contrat(s) archivé(s), ' : '') +
      erreurs.length + ' en erreur : ' + erreurs.join(' ; '));
  }
  /* Lancé du menu, le geste doit se voir : sans cela, Sheets n'affiche que
     « Script terminé », et on ne sait pas si c'est fait. Lancé par le
     déclencheur du vendredi, il n'y a personne devant : pas d'interface, et
     l'appel ci-dessous échoue en silence. */
  const mot = !detail.length ? 'Aucun relevé archivé en ' + dite + ' : ' + (sansPlan.length ? 'en-têtes seuls dans ' +
      sansPlan.join(', ') + '.' : 'aucun contrat.') : 'Relevé ' + dite + ' archivé : ' + detail.map(function (d) {
    return d.nom + ' (' + d.compte.total + ' plans)';
  }).join(', ') + '.' + (detail.length ? ' Un second archivage dans la semaine remplace celui-ci.' : '') +
    (sansPlan.length ? ' Non archivé(s), en-têtes seuls : ' + sansPlan.join(', ') + '.' : '');
  try {
    SpreadsheetApp.getUi().alert('Suivi FWD', mot, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    /* Pas d'interface (déclencheur, test) : rien à montrer. */
  }
  return { ok: true, semaine: semaine, contrats: detail };
}

/**
 * Archive le relevé d'UN contrat pour la semaine donnée, dans son onglet
 * d'historique : la ligne de la semaine est créée ou mise à jour. Renvoie
 * { id, nom, historique, semaine, compte }. Sert au geste hebdomadaire
 * (tous les contrats) comme au dépôt automatique (un seul).
 */
function archiverContrat(classeur, c, semaine) {
  const compte = compterAvancements(c.id);
  /* L'export d'une semaine passée, rattrapé et laissé dans l'onglet
     (débrief 17) : archivé pour la semaine en cours, il écraserait en
     silence le bon relevé déjà pris. Même carte, plan par plan, qu'un
     relevé plus ancien, alors que celui de la semaine diffère : on refuse. */
  const ancien = exportDejaArchive(classeur, c, semaine, compte.plans);
  if (ancien) {
    const courante = numeroSemaineISO(new Date());
    const erreur = new Error('l\'onglet « ' + c.nom + ' » porte le même export que le relevé ' + semaineDite(ancien, courante) +
      ' : le relevé ' + semaineDite(semaine, courante) + ' déjà archivé, différent, n\'est pas écrasé. ' +
      'Recoller l\'export du jour, puis archiver.');
    erreur.ancienExport = true;
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
    const orphelins = historiquesOrphelins(classeur, listerContrats(classeur));
    if (orphelins.length) throw new Error(messageOrphelin(orphelins[0], c));
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
  marquerDonneesModifiees();
  return { id: c.id, nom: c.nom, historique: feuille.getName(), semaine: semaine, compte: compte };
}

/** Ce qu'on dit d'un historique orphelin, à l'archivage comme avant. */
function messageOrphelin(o, c) {
  return 'l\'onglet d\'historique « ' + o.nom + ' » n\'est rattaché à aucun contrat. ' +
    'S\'il est celui de « ' + c.nom + ' », le renommer « ' + nomFeuilleHistorique(c.id) + ' » ; sinon, le renommer ' +
    'sans le préfixe « ' + CONFIG.FEUILLE_HISTORIQUE + '_ » pour le garder à part. Relevé non archivé.';
}

/** Une carte plan par plan, en texte stable : pour comparer deux relevés. */
function carteCanonique(carte) {
  if (!carte || typeof carte !== 'object') return '';
  return Object.keys(carte).sort().map(function (k) { return k + '\u0001' + carte[k]; }).join('\u0002');
}

/**
 * La semaine d'un relevé PLUS ANCIEN dont la carte est exactement celle-ci,
 * quand le relevé de `semaine`, déjà archivé, en a une autre — sinon null.
 * Un historique illisible ne bloque rien.
 */
function exportDejaArchive(classeur, c, semaine, plans) {
  let releves;
  try { releves = getHistorique(classeur, c.id); } catch (err) { return null; }
  const actuel = releves.filter(function (r) { return r.semaine === semaine; })[0];
  if (!actuel || !actuel.plans) return null;
  const neuves = separerCartes(plans);
  const cle = carteCanonique(neuves.plans) + '\u0003' + carteCanonique(neuves.plansConcept);
  const cleDe = function (r) { return carteCanonique(r.plans) + '\u0003' + carteCanonique(r.plansConcept); };
  if (cleDe(actuel) === cle) return null;
  const pareils = releves.filter(function (r) { return r.semaine < semaine && r.plans && cleDe(r) === cle; });
  return pareils.length ? pareils[pareils.length - 1].semaine : null;
}

/**
 * Retire le relevé de la semaine courante — pour rattraper un mauvais export —
 * de tous les contrats, et récapitule à l'écran ce qui a été retiré et ce qui
 * n'avait rien.
 */
function supprimerDernierReleve() {
  gesteDuClasseur();
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const semaine = numeroSemaineISO(new Date());
  const supprimes = [];
  const sans = [];
  let contrats = [];
  try { contrats = listerContrats(classeur); } catch (err) { contrats = []; }

  contrats.forEach(function (c) {
    const feuille = getFeuilleHistorique(classeur, c.id, false);
    const indexLigne = feuille ? ligneDeLaSemaine(feuille, semaine) : -1;
    if (indexLigne === -1) { sans.push(c.nom); return; }
    feuille.deleteRow(indexLigne);
    supprimes.push(c.nom);
  });
  if (supprimes.length) marquerDonneesModifiees();

  const nommer = function (liste) { return liste.map(function (n) { return '« ' + n + ' »'; }).join(', '); };
  /* La semaine se dit comme sur la page : « S39 ». */
  const dite = 'S' + parseInt(semaine.slice(6), 10);
  let message;
  if (!supprimes.length) {
    message = 'Aucun relevé pour la semaine en cours (' + dite + ').';
  } else if (contrats.length === 1) {
    message = 'Relevé ' + dite + ' supprimé. Recollez le bon export puis relancez l\'archivage.';
  } else {
    message = 'Relevé ' + dite + ' supprimé pour ' + nommer(supprimes) +
      (sans.length ? ' ; aucun relevé pour ' + nommer(sans) : '') +
      '. Recollez le bon export puis relancez l\'archivage.';
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
  const resultat = archiverPourSemaine(classeur, onglet, saisie);
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
        'Coller l\'export de ' + dite + ' dans l\'onglet « ' + parent.nom + ' » lui-même (Ctrl+A, Suppr, A1, Ctrl+V), ' +
        'l\'afficher, puis relancer. L\'onglet « ' + contrat.nom + ' » peut être supprimé.' };
    }
    const orphelins = historiquesOrphelins(classeur, contrats);
    if (orphelins.length) {
      return { ok: false, semaine: semaine, message: messageOrphelin(orphelins[0], contrat) };
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
                    ' », coller l\'export dans son onglet à lui.'
                  : ' C\'est le tout premier relevé de ce contrat.')) +
      (actuelle ? '' : '\n\nEnsuite, recolle tout de suite l\'export du jour dans « ' + contrat.nom + ' » : sinon l\'archivage ' +
        'du vendredi prendrait cet export-là pour celui de la semaine en cours.')
  };
}

/** Le geste d'archiverSemainePassee, sans interface : { ok, semaine, message }. */
function archiverPourSemaine(classeur, nomOnglet, saisie) {
  const prevu = preparerSemainePassee(classeur, nomOnglet, saisie);
  if (!prevu.ok) return { ok: false, semaine: prevu.semaine, message: prevu.message };
  const courante = numeroSemaineISO(new Date());
  const dite = semaineDite(prevu.semaine, courante);
  try {
    const detail = archiverContrat(classeur, prevu.contrat, prevu.semaine);
    return { ok: true, semaine: prevu.semaine, message: 'Relevé ' + dite + ' de « ' + prevu.contrat.nom + ' » ' +
      (prevu.existe ? 'remplacé' : 'archivé') + ' avec l\'export affiché (' + detail.compte.total + ' plans).' +
      (prevu.semaine === courante ? '' : '\n\n⚠ L\'onglet « ' + prevu.contrat.nom + ' » porte maintenant l\'export de ' + dite +
        ' : recolle l\'export du jour, puis Suivi FWD → Archiver le relevé de cette semaine.') };
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
 *   { etat, onglet, cles, entetes, ligneEntete, rapprochement }
 * etat : 'sans-configuration' (pas de nom d'onglet, ou pas de référence
 *        configurée), 'absent' (aucun onglet de ce nom), 'vide' (l'onglet
 *        ne porte rien), 'sans-reference' (l'en-tête ne porte pas la
 *        référence), 'ok' — et alors `rapprochement` est la description
 *        pour la page. ligneEntete : le numéro (à partir de 1) de la ligne
 *        prise pour en-tête, null tant qu'aucune ne l'est.
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
  const clesVoulues = !cfg ? [] : [].concat(cfg.CLE_REFERENCE === undefined || cfg.CLE_REFERENCE === null ? [] : cfg.CLE_REFERENCE)
    .map(function (c) { return String(c).trim(); }).filter(Boolean);
  const rendu = { etat: 'sans-configuration', onglet: nomFeuille, cles: clesVoulues, entetes: [], ligneEntete: null, rapprochement: null };
  if (!cfg || !nomFeuille || !clesVoulues.length) return rendu;
  const feuille = ongletSecondeBase(classeur, contrat);
  if (!feuille) { rendu.etat = 'absent'; rendu.onglet = nomAttenduSecondeBase(classeur, contrat); return rendu; }
  rendu.onglet = feuille.getName();

  const donnees = feuille.getDataRange().getDisplayValues();
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
  if (indexEntete === -1) { rendu.etat = 'vide'; return rendu; }
  const entetes = donnees[indexEntete].map(function (e) { return String(e).trim(); });
  rendu.entetes = entetes.filter(Boolean);
  rendu.ligneEntete = indexEntete + 1;

  const lignes = [];
  for (let i = indexEntete + 1; i < donnees.length; i++) {
    if (!ligneNonVide(donnees[i])) continue;
    const ligne = {};
    /* Deux colonnes du même intitulé : la première compte — la même que
       retient l'import de la base (menu Suivi FWD). */
    entetes.forEach(function (titre, j) {
      if (!titre || Object.prototype.hasOwnProperty.call(ligne, titre)) return;
      ligne[titre] = String(donnees[i][j] === undefined ? '' : donnees[i][j]);
    });
    lignes.push(ligne);
  }

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
  if (clesReference.some(function (c) { return !c; })) { rendu.etat = 'sans-reference'; return rendu; }
  const essentielles = (Array.isArray(cfg.ESSENTIELLES) ? cfg.ESSENTIELLES : [])
    .map(enteteLa).filter(Boolean);

  rendu.etat = 'ok';
  rendu.rapprochement = {
    nom: String(cfg.NOM || feuille.getName()).trim().slice(0, 80) || feuille.getName(),
    cleReference: clesReference.length === 1 ? clesReference[0] : clesReference,
    lignes: lignes,
    colonnes: entetes.filter(Boolean),
    essentielles: essentielles
  };
  return rendu;
}

// =====================================================================
//  DÉPÔT AUTOMATIQUE (application web, doPost)
// =====================================================================

/**
 * Point d'entrée des dépôts : un script (import/deposer.py) envoie un
 * extract en JSON, { secret, onglet, lignes: [[…], …], archiver, creer }.
 * La réponse est du JSON : { ok, onglet, lignes, colonnes, archive } ou
 * { ok: false, message }. Tout passe par deposer(), testable sans requête.
 */
function doPost(e) {
  let reponse;
  try {
    const texte = e && e.postData && e.postData.contents ? String(e.postData.contents) : '';
    reponse = deposer(texte);
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
 * secret. Un onglet d'historique n'est jamais une cible.
 */
function deposer(texte) {
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
  marquerDonneesModifiees();
  const resultat = { ok: true, onglet: feuille.getName(), lignes: valeurs.length, colonnes: largeur };
  if (corps.archiver) {
    const contrat = listerContrats(classeur).filter(function (c) { return c.id === feuille.getName(); })[0];
    if (!contrat) {
      resultat.archive = { ok: false, message: '« ' + feuille.getName() + ' » n\'est pas un onglet de contrat : rien à archiver.' };
    } else {
      try {
        const detail = archiverContrat(classeur, contrat, numeroSemaineISO(new Date()));
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
//  IMPORT DE LA SECONDE BASE, SANS EXCEL
// =====================================================================

/**
 * « Les données de SEE sont tellement grosses, l'Excel bug à l'ouverture,
 * j'arrive pas à les copier. » Le menu Suivi FWD → Importer la base SEE
 * ouvre une petite fenêtre où l'on choisit le fichier : Chrome le lit sur le
 * poste — un .xlsx est un zip, il se décompresse et se lit au fil de l'eau,
 * sans Excel et sans tout charger —, et n'envoie au classeur que la ligne
 * d'en-tête et les colonnes de la comparaison (NAME, SOL., Cust.V) : quelques
 * mégaoctets au lieu de centaines. Le fichier lui-même ne quitte pas le poste.
 *
 * L'écriture se fait par lots dans un onglet temporaire, « SEE HDK (import
 * 3f2a9c) », taillé d'avance à la mesure des données ; l'onglet de la base
 * n'est remplacé qu'une fois toutes les lignes reçues. Un import interrompu
 * laisse l'ancien en place. Chaque appel de la fenêtre présente le jeton
 * reçu à son ouverture, ou passe la garde des gestes qui écrivent : rien de
 * tout cela n'est possible depuis la page du tableau de bord.
 */
const IMPORT_MOTIF = / \(import ([0-9a-z]{4,12})\)$/;
const IMPORT_MAX_LIGNES_LOT = 20000;
const IMPORT_MAX_COLONNES = 400;
const IMPORT_LIMITE_CELLULES = 10000000;   // la limite d'un classeur Google Sheets, cellules vides comprises
const CLE_JETON_IMPORT = 'SUIVI_FWD_JETON_IMPORT';
const IMPORT_JETON_DUREE = 6 * 3600 * 1000;

/** Le libellé de l'article du menu — le même au menu et dans le Diagnostic. */
function libelleImport() {
  return 'Importer la base ' + (feuilleRapprochement() || 'SEE') + ' (fichier Excel ou CSV)…';
}

/** Un onglet temporaire d'import : « SEE HDK (import 3f2a9c) ». */
function estOngletImport(nom) {
  const base = feuilleRapprochement();
  const n = String(nom === undefined || nom === null ? '' : nom);
  const m = IMPORT_MOTIF.exec(n);
  return !!base && !!m && nomCompact(n.slice(0, m.index)).indexOf(nomCompact(base)) === 0;
}

/** Le nom de la base d'un contrat, écrit en toutes lettres : « SEE HDK ». */
function souchePourImport(idContrat) {
  return feuilleRapprochement() + ' ' + idContrat;
}

/**
 * Le jeton de la fenêtre d'import, posé par le menu (dans le classeur). Les
 * appels de la fenêtre le présentent ; sans lui, ils doivent passer la garde
 * des gestes qui écrivent. La page du tableau de bord n'a ni l'un ni
 * l'autre : le jeton ne s'écrit que dans la fenêtre ouverte par le menu.
 */
function ouvrirJetonImport() {
  const jeton = (Utilities.getUuid() + Utilities.getUuid()).replace(/[^0-9a-z]/gi, '');
  PropertiesService.getDocumentProperties().setProperty(CLE_JETON_IMPORT,
    JSON.stringify({ jeton: jeton, expire: new Date().getTime() + IMPORT_JETON_DUREE }));
  return jeton;
}
function gesteImport(jeton) {
  let valide = false;
  try {
    const v = JSON.parse(PropertiesService.getDocumentProperties().getProperty(CLE_JETON_IMPORT) || 'null');
    valide = !!v && typeof v.jeton === 'string' && typeof jeton === 'string' && jeton.length >= 8 &&
      memeSecret(jeton, v.jeton) && Number(v.expire) > new Date().getTime();
  } catch (err) { valide = false; }
  if (!valide) gesteDuClasseur();
}

/** Menu : la fenêtre d'import, sur la base du contrat affiché. */
function importerSecondeBase() {
  gesteDuClasseur();
  const ui = SpreadsheetApp.getUi();
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const cfg = CONFIG.RAPPROCHEMENT;
  const nomBase = feuilleRapprochement();
  const cles = !cfg ? [] : [].concat(cfg.CLE_REFERENCE === undefined || cfg.CLE_REFERENCE === null ? [] : cfg.CLE_REFERENCE)
    .map(function (c) { return String(c).trim(); }).filter(Boolean);
  if (!nomBase || !cles.length) {
    ui.alert('Importer la seconde base', 'Aucune seconde base n’est configurée (CONFIG.RAPPROCHEMENT dans Code).', ui.ButtonSet.OK);
    return;
  }
  const contrats = listerContrats(classeur);
  if (!contrats.length) {
    ui.alert('Importer la base ' + nomBase, 'Aucun contrat dans le classeur : coller d’abord l’extract GATES dans un onglet.', ui.ButtonSet.OK);
    return;
  }
  /* Le contrat proposé : celui de l'onglet affiché, ou dont la base est
     affichée ; sinon le premier. */
  const active = classeur.getActiveSheet() ? classeur.getActiveSheet().getName() : '';
  let choisi = contrats[0].id;
  const liste = contrats.map(function (c) {
    const f = ongletSecondeBase(classeur, c.id);
    const onglet = f ? f.getName() : souchePourImport(c.id);
    if (c.id === active || onglet === active) choisi = c.id;
    return { id: c.id, onglet: onglet, existe: !!f };
  });
  const parametres = {
    jeton: ouvrirJetonImport(),
    base: nomBase,
    cles: cles,
    essentielles: (Array.isArray(cfg.ESSENTIELLES) ? cfg.ESSENTIELLES : []).map(function (c) { return String(c).trim(); }).filter(Boolean),
    lignesScan: CONFIG.LIGNES_SCAN_ENTETE,
    maxLignesLot: IMPORT_MAX_LIGNES_LOT,
    maxCellulesToutes: 4000000,
    pausesReprise: [2000, 6000],
    contrats: liste,
    choisi: choisi
  };
  const page = HtmlService.createHtmlOutput(pageImportSecondeBase(parametres)).setWidth(640).setHeight(540);
  ui.showModalDialog(page, 'Importer la base ' + nomBase);
}

/** Le contrat nommé, ou une erreur qui le nomme. */
function contratPourImport(classeur, idContrat) {
  const id = String(idContrat === undefined || idContrat === null ? '' : idContrat);
  const contrat = listerContrats(classeur).filter(function (c) { return c.id === id; })[0];
  if (!contrat) throw new Error('Contrat introuvable : « ' + id + ' ». Rouvrir le menu Suivi FWD → Importer la base.');
  return contrat;
}

/** L'onglet temporaire d'un import en cours — jamais un autre onglet. */
function feuilleImportEnCours(classeur, nom) {
  const n = String(nom === undefined || nom === null ? '' : nom);
  if (!estOngletImport(n)) throw new Error('Onglet d’import non reconnu : « ' + n + ' ».');
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
 * Début d'un import : un onglet temporaire taillé à la mesure des données —
 * `largeur` colonnes, `total` lignes (en-tête comprise) —, à côté de la base
 * qu'il remplacera. Sheets compte chaque cellule de la grille, vide ou pas,
 * dans sa limite de dix millions : un onglet neuf en a 26 colonnes, d'où la
 * taille posée d'avance, et le compte fait avant le moindre envoi. Les restes
 * d'un import interrompu de ce contrat sont retirés d'abord.
 * @return {{feuille: string, onglet: string}}
 */
function importSecondeBaseDebut(jeton, idContrat, largeur, total) {
  gesteImport(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const contrat = contratPourImport(classeur, idContrat);
  const larg = Math.floor(Number(largeur)), lignes = Math.floor(Number(total));
  if (!(larg >= 1 && larg <= IMPORT_MAX_COLONNES)) throw new Error('Nombre de colonnes illisible : ' + largeur + ' (au plus ' + IMPORT_MAX_COLONNES + ').');
  if (!(lignes >= 2)) throw new Error('Rien à importer : l’en-tête seul.');
  const verrou = LockService.getDocumentLock();
  const tenu = verrou.tryLock(30000);
  try {
    /* Les restes d'un import de ce contrat — fenêtre fermée en cours d'envoi,
       ou import lancé en même temps : un envoi encore en cours s'arrête net
       (« a disparu »), sans jamais mêler deux fichiers. */
    const souche = souchePourImport(contrat.id);
    classeur.getSheets().slice().forEach(function (f) {
      const n = f.getName(), m = IMPORT_MOTIF.exec(n);
      if (m && estOngletImport(n) && nomCompact(n.slice(0, m.index)) === nomCompact(souche)) classeur.deleteSheet(f);
    });
    const occupees = cellulesDuClasseur(classeur), voulues = lignes * larg;
    if (occupees + voulues > IMPORT_LIMITE_CELLULES) {
      throw new Error('Le classeur dépasserait la limite de Google Sheets : 10 millions de cellules, vides comprises. Il en compte déjà ' +
        occupees + ', l’import en demande ' + voulues + ' (' + lignes + ' lignes × ' + larg + ' colonnes). ' +
        (larg > 3 ? 'Décocher « Garder aussi les autres colonnes », ou ' : '') + 'supprimer les onglets qui ne servent plus.');
    }
    const nom = souche + ' (import ' + Utilities.getUuid().replace(/[^0-9a-z]/gi, '').slice(0, 6).toLowerCase() + ')';
    const feuille = classeur.insertSheet(nom, classeur.getSheets().length);
    if (feuille.getMaxColumns() > larg) feuille.deleteColumns(larg + 1, feuille.getMaxColumns() - larg);
    else assurerColonnes(feuille, larg);
    if (feuille.getMaxRows() > lignes) feuille.deleteRows(lignes + 1, feuille.getMaxRows() - lignes);
    else assurerLignes(feuille, lignes);
    const existant = ongletSecondeBase(classeur, contrat.id);
    return { feuille: nom, onglet: existant ? existant.getName() : souche };
  } finally {
    if (tenu) verrou.releaseLock();
  }
}

/**
 * Un lot de lignes, écrit à partir de la ligne `premiere` (1-based) de
 * l'onglet temporaire. Tout est vérifié avant d'écrire ; chaque cellule
 * est posée en texte (une valeur « =… » ne devient pas une formule, « 01 »
 * reste « 01 »).
 * @return {{ecrites: number}}
 */
function importSecondeBaseLot(jeton, nomFeuille, premiere, lignes) {
  gesteImport(jeton);
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
 * Fin d'un import : si l'onglet temporaire a bien toutes ses lignes, il
 * prend la place — et le nom — de la base du contrat, à sa position. Rien
 * ne se perd en route : l'ancienne base est d'abord mise de côté sous un
 * autre nom, la nouvelle prend le sien, puis l'ancienne s'en va. La relecture
 * finale est légère (la ligne d'en-tête) : la base est en place avant elle.
 */
function importSecondeBaseFin(jeton, nomFeuille, idContrat, lignesAttendues) {
  gesteImport(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = feuilleImportEnCours(classeur, nomFeuille);
  const contrat = contratPourImport(classeur, idContrat);
  const verrou = LockService.getDocumentLock();
  const tenu = verrou.tryLock(30000);
  let recues = 0, derniereColonne = 1, onglet = '', remplace = false;
  try {
    recues = feuille.getLastRow();
    if (recues !== Number(lignesAttendues)) {
      classeur.deleteSheet(feuille);
      throw new Error('Import incomplet : ' + recues + ' lignes reçues sur ' + lignesAttendues + '.');
    }
    derniereColonne = Math.max(1, feuille.getLastColumn());
    if (feuille.getMaxRows() > recues) feuille.deleteRows(recues + 1, feuille.getMaxRows() - recues);
    if (feuille.getMaxColumns() > derniereColonne) feuille.deleteColumns(derniereColonne + 1, feuille.getMaxColumns() - derniereColonne);
    const existant = ongletSecondeBase(classeur, contrat.id);
    onglet = existant ? existant.getName() : souchePourImport(contrat.id);
    remplace = !!existant;
    let position = 0;
    if (existant) {
      position = existant.getIndex();
      existant.setName(souchePourImport(contrat.id) + ' (ancien ' + IMPORT_MOTIF.exec(feuille.getName())[1] + ')');
    }
    feuille.setName(onglet);
    if (position) {
      classeur.setActiveSheet(feuille);
      classeur.moveActiveSheet(position);
    }
    if (existant) classeur.deleteSheet(existant);
    marquerDonneesModifiees();
  } finally {
    if (tenu) verrou.releaseLock();
  }
  /* La base est en place. Sa ligne d'en-tête, relue, dit si la page la
     lira ; une panne ici ne défait rien. */
  let etat = 'ok';
  try {
    const ligne = feuille.getRange(1, 1, 1, derniereColonne).getDisplayValues()[0].map(function (c) { return normaliser(String(c).trim()); });
    const cles = [].concat(CONFIG.RAPPROCHEMENT.CLE_REFERENCE || []).map(function (c) { return normaliser(String(c).trim()); });
    if (cles.some(function (k) { return ligne.indexOf(k) === -1; })) etat = 'sans-reference';
  } catch (err) { etat = 'non relu'; }
  return { onglet: onglet, remplace: remplace, lignes: recues - 1, colonnes: derniereColonne, etat: etat };
}

/** Abandon : l'onglet temporaire est retiré, la base reste ce qu'elle était. */
function importSecondeBaseAbandon(jeton, nomFeuille) {
  gesteImport(jeton);
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const n = String(nomFeuille === undefined || nomFeuille === null ? '' : nomFeuille);
  const feuille = estOngletImport(n) ? classeur.getSheetByName(n) : null;
  if (feuille) classeur.deleteSheet(feuille);
  return true;
}

/** La fenêtre d'import : son HTML, ses styles, et son programme avec ses paramètres. */
function pageImportSecondeBase(parametres) {
  const json = JSON.stringify(parametres).replace(/</g, '\\u003c');
  const ech = function (t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  const cles = parametres.cles.map(ech).join(', ');
  return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><base target="_top"><style>' +
    ':root{--papier:#f4f2ed;--surface:#fff;--encre:#191915;--encre-2:#57564e;--encre-3:#8a887e;--filet:#e2dfd6;' +
    '--fait:#2f6b4f;--alerte:#b5462e;--teinte:#191915}' +
    '@media (prefers-color-scheme:dark){:root{--papier:#1b1b18;--surface:#23231f;--encre:#efede6;--encre-2:#c4c1b6;' +
    '--encre-3:#8f8c82;--filet:#3a3933;--fait:#6fbf94;--alerte:#e2846d;--teinte:#efede6}}' +
    'html,body{margin:0;background:var(--papier);color:var(--encre);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}' +
    'body{padding:4px 18px 16px}p{margin:0 0 12px}.doux{color:var(--encre-2)}b{font-weight:600}' +
    '.ligne{display:flex;align-items:center;gap:10px;margin:0 0 6px}select{font:inherit;padding:4px 6px;border:1px solid var(--filet);' +
    'border-radius:6px;background:var(--surface);color:var(--encre)}.cible{margin:0 0 12px;color:var(--encre-2);font-size:13px}' +
    '.depot{border:1.5px dashed var(--filet);border-radius:10px;background:var(--surface);padding:18px;text-align:center;margin:0 0 10px}' +
    '.depot.survol{border-color:var(--encre-3)}.depot input{display:none}.nom{margin-top:8px;font-size:13px;color:var(--encre-2);word-break:break-all}' +
    'button{font:inherit;padding:6px 14px;border-radius:7px;border:1px solid var(--filet);background:var(--surface);color:var(--encre);cursor:pointer}' +
    'button.principal{background:var(--teinte);border-color:var(--teinte);color:var(--papier)}button:disabled{opacity:.45;cursor:default}' +
    'button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--encre);outline-offset:2px}' +
    '.option{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--encre-2);margin:0 0 12px}' +
    '.barre{height:6px;border-radius:3px;background:var(--filet);overflow:hidden;margin:4px 0 6px}.barre div{height:100%;width:0;background:var(--fait);transition:width .2s}' +
    '.progres{font-size:13px;color:var(--encre-2);min-height:20px}.consigne{font-size:13px;color:var(--encre);font-weight:600;margin:2px 0 0}' +
    '.etat{margin:8px 0 0;font-size:13.5px}.etat.ok{color:var(--fait)}' +
    '.etat.erreur{color:var(--alerte)}.boutons{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}[hidden]{display:none!important}' +
    '</style></head><body>' +
    '<p>Choisir l’export ' + ech(parametres.base) + ' <b>de ce contrat</b> (.xlsx, ou .csv). Il est lu ici, sur ce poste, ' +
    '<b>sans ouvrir Excel</b> : seules la ligne d’en-tête et les colonnes de la comparaison — ' + cles + ' — vont dans le classeur.</p>' +
    '<div class="ligne" id="ligne-contrat"><label for="contrat">Contrat</label><select id="contrat"></select></div>' +
    '<p class="cible" id="cible"></p>' +
    '<div class="depot" id="depot"><input type="file" id="fichier" accept=".xlsx,.xlsm,.csv,.txt,.xls,.xlsb,.xml,.htm,.html">' +
    '<button type="button" id="choisir">Choisir le fichier…</button> <span class="doux">ou le glisser ici</span>' +
    '<div class="nom" id="nom-fichier"></div></div>' +
    '<label class="option"><input type="checkbox" id="toutes"> <span>Garder aussi les autres colonnes — plus lourd, ' +
    'seulement pour regarder tout l’extract dans le tableau ' + ech(parametres.base) + ' de la page.</span></label>' +
    '<div class="barre" id="barre" hidden><div id="barre-plein"></div></div>' +
    '<div class="progres" id="progres" aria-live="polite"></div>' +
    '<p class="consigne" id="consigne" hidden>Ne pas fermer cette fenêtre avant la fin.</p>' +
    '<div class="etat" id="etat" role="status" aria-live="polite"></div>' +
    '<div class="boutons"><button type="button" id="fermer">Fermer</button>' +
    '<button type="button" class="principal" id="importer" disabled>Importer</button></div>' +
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
 * l'en-tête — sans jamais tenir le fichier entier en mémoire. Les « Excel »
 * qui n'en sont pas (une page web, un XML 2003 nommés .xls) et les CSV se
 * lisent aussi, au fil de l'eau.
 */
function scriptImportSecondeBase_(P) {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var fichier = null, enCours = false;

  // ------------------------------------------------------------ petits outils
  function norm(t) {
    return String(t === null || t === undefined ? '' : t).toLowerCase().normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim();
  }
  function nb(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f'); }
  function ech(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function erreur(message) { var e = new Error(message); e.pourLecteur = true; return e; }
  function dire(html, classe) { var z = $('etat'); z.className = 'etat' + (classe ? ' ' + classe : ''); z.innerHTML = html; }
  function progres(part, texte) {
    $('barre').hidden = false;
    $('barre-plein').style.width = Math.round(Math.max(0, Math.min(1, part)) * 100) + '%';
    if (texte !== undefined) $('progres').textContent = texte;
  }
  function souffle() { return new Promise(function (ok) { setTimeout(ok, 0); }); }
  /* Une valeur gardée est recopiée : une sous-chaîne d'un morceau de XML le
     tiendrait tout entier en mémoire, et un gros fichier ferait tomber
     l'onglet du navigateur. */
  function plat(v) { return v.length > 12 ? (' ' + v).slice(1) : v; }
  var ABIME = 'Le fichier est abîmé (il ne se décompresse pas en entier) : le retélécharger depuis SEE.';

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
      if (p < 0) throw erreur('Ce fichier n\u2019est pas un classeur .xlsx lisible : abîmé, ou pas fini de télécharger ? Le retélécharger depuis SEE.');
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
  function attribut(s, nom) {
    var m = new RegExp('\\s(?:[\\w.-]+:)?' + nom + '\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\')', 'i').exec(' ' + s);
    return m ? decoderXml(m[1] !== undefined ? m[1] : m[2]) : null;
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

  // ------------------------------------------------------------ en-tête et lignes
  /* Reçoit les lignes une à une (numéro 1-based, valeurs par colonne) :
     cherche l'en-tête comme Code.gs le cherche — la première des premières
     lignes qui porte toutes les colonnes de la référence, la première
     colonne d'un intitulé en double —, puis garde les colonnes voulues des
     lignes suivantes. */
  function collecteur(toutes) {
    var nCles = P.cles.map(norm), nEss = P.essentielles.map(norm);
    var c = { entete: null, colonnes: null, voulues: null, cles: null, lignes: [], meilleur: { portes: 0, ligne: 0, noms: [], manquent: P.cles.slice() },
              formulesVides: 0, trop: false };
    c.ligne = function (num, valeurs, sansValeur) {
      if (!c.colonnes) {
        if (num > P.lignesScan) return false;
        var ns = valeurs.map(norm), portes = nCles.filter(function (k) { return ns.indexOf(k) !== -1; });
        if (portes.length === nCles.length) {
          var prises = {}, cles = {};
          nCles.forEach(function (k) { prises[ns.indexOf(k)] = true; cles[ns.indexOf(k)] = true; });
          nEss.forEach(function (k) { var j = ns.indexOf(k); if (j !== -1) prises[j] = true; });
          if (toutes) ns.forEach(function (k, j) { if (k) prises[j] = true; });
          c.colonnes = Object.keys(prises).map(Number).sort(function (a, b) { return a - b; });
          c.voulues = prises; c.cles = cles;
          c.entete = c.colonnes.map(function (j) { return plat(String(valeurs[j] === undefined ? '' : valeurs[j]).trim()); });
        } else if (portes.length > c.meilleur.portes) {
          c.meilleur = { portes: portes.length, ligne: num,
            noms: valeurs.filter(function (v) { return String(v === undefined || v === null ? '' : v).trim(); }).slice(0, 12),
            manquent: P.cles.filter(function (k, i) { return portes.indexOf(nCles[i]) === -1; }) };
        }
        return true;
      }
      if (sansValeur && sansValeur.some(function (j) { return c.cles[j]; })) c.formulesVides++;
      var l = c.colonnes.map(function (j) { var v = valeurs[j]; return v === undefined || v === null ? '' : plat(String(v)); });
      if (l.some(function (v) { return v.trim() !== ''; })) {
        c.lignes.push(l);
        if (toutes && (c.lignes.length + 1) * c.entete.length > P.maxCellulesToutes) { c.trop = true; return false; }
      }
      return true;
    };
    return c;
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

  /* Un onglet du classeur, ligne à ligne. Rend le collecteur ; il dit si
     l'en-tête a été trouvé. La lecture s'arrête après les lignes (ce qui
     suit — liens, fusions, mise en page — ne sert à rien). */
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
    var finDonnees = false;
    return lirePartie(f, e, function (texte, fini) {
      if (finDonnees) return false;
      var r = surLigne(texte, fini);
      if (r !== false && RE_FIN_DONNEES.test(texte)) { finDonnees = true; return false; }
      return r;
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

  function lireXlsx(f, toutes) {
    progres(0.02, 'Ouverture du fichier…');
    return lireZip(f).then(function (entrees) {
      var wb = chercher(entrees, 'xl/workbook.xml');
      if (!wb) {
        if (chercher(entrees, 'xl/workbook.bin')) throw erreur('C\u2019est un classeur binaire (.xlsb), que ni la fenêtre ni Google Sheets ne lisent. Il faut l\u2019export SEE en .xlsx ou en .csv.');
        throw erreur('Ce zip n\u2019est pas un classeur Excel (pas de xl/workbook.xml).');
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
          var meilleur = null, i = 0;
          function suivant() {
            if (i >= onglets.length) return { trouve: false, meilleur: meilleur, onglets: onglets.map(function (o) { return o.nom; }) };
            var o = onglets[i++];
            progres(0.05 + 0.9 * fait / total, 'Lecture de l\u2019onglet « ' + o.nom + ' »…');
            return lireOnglet(f, o.e, chaines, styles, en1904, toutes, function (n) { progres(0.05 + 0.9 * (fait + n) / total); }).then(function (c) {
              fait += o.e.tu;
              if (c.colonnes) { c.onglet = o.nom; c.trouve = true; return c; }
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
  var RE_TD = /<(?:[\w.-]+:)?t[dh](?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?t[dh]\s*>)/gi;
  function analyseurHtml(c) {
    var num = 0;
    return decoupeur('tr', function (attrs, corps) {
      var valeurs = [], m;
      RE_TD.lastIndex = 0;
      while ((m = RE_TD.exec(corps))) {
        var span = parseInt(attribut(m[1], 'colspan') || '1', 10);
        valeurs.push(m[2] ? texteCellule(m[2]) : '');
        for (var k = 1; k < span && k < 50; k++) valeurs.push('');
      }
      return c.ligne(++num, valeurs);
    }, true);
  }
  var RE_CELL = /<(?:[\w.-]+:)?Cell(?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?Cell\s*>)/g;
  var RE_DATA = /<(?:[\w.-]+:)?Data(?=[\s>\/])([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:[\w.-]+:)?Data\s*>)/;
  /* Le XML 2003 d'Excel : un onglet après l'autre ; l'en-tête est cherché
     dans chacun tant qu'il n'est pas trouvé, et la lecture s'arrête à la fin
     de celui qui le porte. */
  function analyseurXml2003(nouveauCollecteur, surFin) {
    var c = nouveauCollecteur(), num = 0, garde = { c: c };
    var lignes = decoupeur('Row', function (attrs, corps) {
      var idx = attribut(attrs, 'Index');
      num = idx ? parseInt(idx, 10) : num + 1;
      var valeurs = [], col = -1, m;
      RE_CELL.lastIndex = 0;
      while ((m = RE_CELL.exec(corps))) {
        var ci = attribut(m[1], 'Index');
        col = ci ? parseInt(ci, 10) - 1 : col + 1;
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
        var span = parseInt(attribut(m[1], 'MergeAcross') || '0', 10);
        col += Math.min(span, 50);
      }
      for (var j = 0; j < valeurs.length; j++) if (valeurs[j] === undefined) valeurs[j] = '';
      return garde.c.ligne(num, valeurs);
    });
    var reOnglet = /<(?:[\w.-]+:)?Worksheet(?=[\s>])/g;
    var analyse = function (texte, fini) {
      var debut = 0, m;
      reOnglet.lastIndex = 0;
      while ((m = reOnglet.exec(texte))) {
        if (lignes(texte.slice(debut, m.index), false) === false && garde.c.colonnes) return false;
        debut = m.index;
        if (num > 0) {
          if (garde.c.colonnes) { surFin(garde.c); return false; }
          surFin(garde.c);
          garde.c = nouveauCollecteur(); num = 0;
        }
      }
      var r = lignes(texte.slice(debut), fini);
      return r === false && !garde.c.colonnes ? true : r;
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
      if (debut.charAt(0) === '<') {
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
    if (sonde.sorte === 'xml') throw erreur('Ce fichier est du XML, mais pas un classeur Excel que la fenêtre connaisse. Il faut l\u2019export SEE en .xlsx ou en .csv.');
    function lecture(encodage, strict) {
      var c = null, fin = null, nouveau = function () { return collecteur(toutes); };
      var analyse, premier = true;
      var retenir = function (x) { if (!fin || (x.colonnes && !fin.colonnes) || (!fin.colonnes && x.meilleur.portes > fin.meilleur.portes)) fin = x; };
      if (sonde.sorte === 'html') { c = nouveau(); analyse = analyseurHtml(c); }
      else if (sonde.sorte === 'xml2003') analyse = analyseurXml2003(nouveau, retenir);
      else {
        var lignes = sonde.tete.split(/\r\n|\n|\r/).slice(0, P.lignesScan + 1), nCles = P.cles.map(norm), sep = ';', meilleur = -1;
        [';', ',', '\t', '|'].forEach(function (s) {
          var score = Math.max.apply(null, lignes.map(function (l) {
            var ns = champsCsv(l, s).map(function (x) { return norm(x.replace(/^=/, '')); });
            return nCles.filter(function (k) { return ns.indexOf(k) !== -1; }).length * 1000 + Math.min(999, ns.length);
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
        var r = sonde.sorte === 'xml2003' ? (fin && fin.colonnes ? fin : null) : c;
        if (sonde.sorte === 'xml2003' && !r) {
          var dernier = fin;
          return { trouve: false, meilleur: dernier ? dernier.meilleur : { portes: 0 }, onglets: [f.name] };
        }
        if (r.colonnes) { r.trouve = true; r.onglet = f.name; return r; }
        r.meilleur.onglet = f.name;
        return { trouve: false, meilleur: r.meilleur, onglets: [f.name] };
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
     mêmes lignes, et un début retire l'onglet temporaire d'un début perdu —
     les renvoyer ne double rien. Les refus du serveur, eux, sont définitifs ;
     la fin n'est jamais renvoyée (elle a pu échanger les onglets). */
  var DEFINITIF = /a disparu|non reconnu|Geste refusé|Contrat introuvable|limite de Google Sheets|illisible|Lot vide|Lot trop grand|Lot sans colonne|Trop de colonnes|Rien à importer|Import incomplet|PERMISSION_DENIED|reading from storage|autoris|authoriz/i;
  function appelerAvecReprise(nom, args, surReprise) {
    var essai = 0;
    function tenter() {
      return appeler(nom, args).catch(function (e) {
        if (essai >= P.pausesReprise.length || DEFINITIF.test(e.message)) throw e;
        var pause = P.pausesReprise[essai++];
        surReprise(essai);
        return new Promise(function (ok) { setTimeout(ok, pause); }).then(tenter);
      });
    }
    return tenter();
  }
  function envoyer(contrat, entete, lignes, etat) {
    var total = lignes.length + 1, feuille = null, envoyees = 0;
    var reprise = function (n) {
      progres(envoyees / lignes.length, 'Le classeur n\u2019a pas répondu : nouvel essai (' + n + ' sur ' + P.pausesReprise.length + ')…');
    };
    progres(0, 'Préparation de l\u2019onglet…');
    return appelerAvecReprise('importSecondeBaseDebut', [contrat, entete.length, total], reprise).then(function (d) {
      feuille = d.feuille;
      var i = -1;
      function lot() {
        if (i >= lignes.length) return null;
        var paquet = [], taille = 0, premiere = i + 2, donnees = 0;
        while (i < lignes.length && paquet.length < P.maxLignesLot && taille < 900000) {
          var l = i < 0 ? entete : lignes[i];
          if (i >= 0) donnees++;
          paquet.push(l);
          for (var j = 0; j < l.length; j++) taille += l[j].length + 3;
          i++;
        }
        return appelerAvecReprise('importSecondeBaseLot', [feuille, premiere, paquet], reprise).then(function () {
          envoyees += donnees;
          progres(envoyees / lignes.length, 'Envoi au classeur : ' + nb(envoyees) + ' lignes sur ' + nb(lignes.length) + '…');
          return lot();
        });
      }
      return lot();
    }).then(function () {
      progres(1, 'Mise en place de l\u2019onglet…');
      etat.fin = true;
      return appeler('importSecondeBaseFin', [feuille, contrat, total]);
    }).catch(function (e) {
      if (feuille && !etat.fin) appeler('importSecondeBaseAbandon', [feuille]).catch(function () {});
      throw e;
    });
  }

  // ------------------------------------------------------------ la fenêtre
  function contratChoisi() { return $('contrat').value; }
  function cibleChoisie() { return P.contrats.filter(function (x) { return x.id === contratChoisi(); })[0] || null; }
  function majCible() {
    var c = cibleChoisie();
    $('cible').innerHTML = c ? (c.existe ? 'Remplacera l\u2019onglet' : 'Créera l\u2019onglet') + ' <b>« ' + ech(c.onglet) + ' »</b>' +
      (c.existe ? ' — l\u2019ancien ne s\u2019en va qu\u2019une fois tout reçu.' : '.') : '';
  }
  function poserFichier(f) {
    fichier = f || null;
    $('nom-fichier').textContent = fichier ? fichier.name + ' — ' + (fichier.size / 1048576).toFixed(1).replace('.', ',') + ' Mo' : '';
    $('importer').disabled = !fichier || enCours;
    dire('');
  }
  function sorteDuFichier(f) {
    return lireOctets(f, 0, 512).then(function (b) {
      if (b[0] === 0x50 && b[1] === 0x4b) return 'zip';
      if (!(b[0] === 0xD0 && b[1] === 0xCF && b[2] === 0x11 && b[3] === 0xE0)) return 'texte';
      /* Un conteneur OLE : un vieux classeur (flux « Workbook » ou « Book »),
         même nommé .xlsx, ou un .xlsx chiffré (« EncryptionInfo »). Le
         premier secteur du répertoire le dit ; à défaut, l'extension. */
      var parExtension = /\.xls[xmb]$/i.test(f.name) ? 'protege' : 'xls';
      if (b.length < 512 || (u16(b, 0x1E) !== 9 && u16(b, 0x1E) !== 12)) return parExtension;
      var taille = 1 << u16(b, 0x1E), debut = (u32(b, 0x30) + 1) * taille;
      if (debut + taille > f.size) return parExtension;
      return lireOctets(f, debut, debut + taille).then(function (d) {
        var noms = [];
        for (var k = 0; k + 128 <= d.length; k += 128) {
          var lg = Math.min(64, u16(d, k + 64)), n = '';
          for (var j = 0; j < lg - 2; j += 2) n += String.fromCharCode(u16(d, k + j));
          noms.push(n);
        }
        if (noms.indexOf('Workbook') !== -1 || noms.indexOf('Book') !== -1) return 'xls';
        if (noms.indexOf('EncryptionInfo') !== -1 || noms.indexOf('EncryptedPackage') !== -1) return 'protege';
        return parExtension;
      }, function () { return parExtension; });
    });
  }
  function messageDErreur(e, etat) {
    var c = cibleChoisie(), onglet = c ? c.onglet : P.base, texte = e && e.message ? e.message : String(e);
    if (e && e.name === 'TypeError' && /compress|decompress|deflate/i.test(texte)) return ABIME + ' Rien n\u2019a été remplacé dans le classeur.';
    if (/PERMISSION_DENIED|reading from storage|ScriptError.*autoris|authoriz/i.test(texte)) {
      return 'Google refuse l\u2019appel : plusieurs comptes Google sont sans doute ouverts dans ce navigateur, ce qu\u2019Apps Script ne supporte pas. ' +
        'Ouvrir le classeur dans une fenêtre où seul le compte du classeur est connecté (ou une fenêtre de navigation privée), puis relancer.';
    }
    var t = e && e.pourLecteur ? texte : 'Erreur inattendue : ' + texte;
    /* Après l'appel de fin, la base a pu être échangée — sauf pour ces refus,
       qui arrivent avant tout échange. */
    if (etat.fin && !/Import incomplet|a disparu|non reconnu|Contrat introuvable|Geste refusé/.test(texte)) {
      return t + ' L\u2019import est peut-être allé au bout : regarder l\u2019onglet « ' + onglet + ' » (ou menu Suivi FWD → Diagnostic) avant de relancer.';
    }
    if (etat.fin) return t + ' L\u2019ancien onglet « ' + onglet + ' » est intact.';
    if (e && e.duServeur && !/limite de Google Sheets|Import incomplet/.test(texte)) t += ' Relancer l\u2019import ; si ça recommence : menu Suivi FWD → Diagnostic.';
    return t + (/Rien n.(a été|est) remplacé|intact/.test(t) ? '' : ' Rien n\u2019a été remplacé dans le classeur.');
  }
  function importer() {
    if (!fichier || enCours) return;
    var toutes = $('toutes').checked, f = fichier, contrat = contratChoisi(), etat = { fin: false }, c0 = cibleChoisie();
    enCours = true;
    $('importer').disabled = true; $('choisir').disabled = true; $('contrat').disabled = true; $('toutes').disabled = true; $('fermer').disabled = true;
    $('consigne').hidden = false;
    dire('');
    var debut = Date.now();
    sorteDuFichier(f).then(function (sorte) {
      var onglet = c0 ? c0.onglet : P.base + ' ' + contrat;
      if (sorte === 'protege') throw erreur('Ce fichier Excel est protégé (mot de passe ou étiquette de confidentialité) : la fenêtre ne peut pas le lire, ' +
        'Google Sheets non plus. Demander l\u2019export SEE sans protection, ou en .csv.');
      if (sorte === 'xls') throw erreur('C\u2019est un ancien fichier Excel (' + (/\.xls[xmb]$/i.test(f.name) ? 'format .xls, malgré son nom' : '.xls') + '), que la fenêtre ne sait pas lire. Il faut l\u2019export en .xlsx ou en .csv — ' +
        'ou, dans le classeur : Fichier → Importer → ce fichier → « Insérer de nouvelles feuilles » (surtout pas « Remplacer la feuille de calcul » : ' +
        'elle remplace tout le classeur), puis supprimer l\u2019ancien onglet « ' + onglet + ' » et donner ce nom au nouveau.');
      if (sorte === 'zip') {
        if (typeof DecompressionStream !== 'function') throw erreur('Ce navigateur est trop ancien pour décompresser un .xlsx. Le mettre à jour, ou passer par un export .csv.');
        try { new DecompressionStream('deflate-raw'); } catch (e) { throw erreur('Ce navigateur est trop ancien pour décompresser un .xlsx. Le mettre à jour, ou passer par un export .csv.'); }
        return lireXlsx(f, toutes);
      }
      return sonderTexte(f).then(function (s) { return lireTexte(f, toutes, s); });
    }).then(function (c) {
      if (!c.trouve) {
        var m = c.meilleur || { portes: 0 };
        throw erreur('Aucune ligne d\u2019en-tête avec ' + P.cles.join(', ') + ' dans les ' + P.lignesScan + ' premières lignes' +
          (c.onglets && c.onglets.length > 1 ? ' des onglets (' + c.onglets.join(', ') + ')' : '') + '. Est-ce bien l\u2019export ' + P.base + ' ?' +
          (m.portes ? ' La ligne ' + m.ligne + ' de « ' + m.onglet + ' » en porte ' + m.portes + ' sur ' + P.cles.length +
            ' — il manque : ' + m.manquent.join(', ') + ' (intitulés lus : ' + m.noms.join(', ') + ').' : ''));
      }
      if (c.trop) throw erreur('Plus de ' + nb(P.maxCellulesToutes) + ' cellules avec toutes les colonnes : trop pour le classeur. ' +
        'Décocher « Garder aussi les autres colonnes » : seules ' + P.cles.join(', ') + ' iront.');
      if (!c.lignes.length) throw erreur('L\u2019en-tête est là (« ' + c.onglet + ' »), mais aucune ligne dessous.');
      if (c.formulesVides) throw erreur(nb(c.formulesVides) + ' ligne(s) ont une formule sans valeur calculée dans ' + P.cles.join(', ') + ' : le fichier ' +
        'a été écrit par un programme qui ne calcule pas. Demander l\u2019export SEE en .csv, ou en .xlsx enregistré une fois par Excel.');
      var lu = (Date.now() - debut) / 1000;
      dire('Fichier lu en ' + Math.max(1, Math.round(lu)) + ' s : <b>' + nb(c.lignes.length) + ' lignes</b>, colonnes ' + ech(c.entete.join(', ')) + '.');
      return envoyer(contrat, c.entete, c.lignes, etat).then(function (r) {
        $('barre').hidden = true;
        $('progres').textContent = '';
        dire('✓ <b>' + nb(r.lignes) + ' lignes</b> dans l\u2019onglet <b>« ' + ech(r.onglet) + ' »</b> (' + r.colonnes + ' colonne' + (r.colonnes > 1 ? 's' : '') + ').' +
          (r.etat === 'ok' || r.etat === 'non relu' ? ' La comparaison est prête : rouvrir le tableau de bord (menu Suivi FWD → Ouvrir le tableau de bord).'
            : ' Mais la page ne la lit pas (' + ech(r.etat) + ') : menu Suivi FWD → Diagnostic.'), r.etat === 'ok' || r.etat === 'non relu' ? 'ok' : 'erreur');
        $('fermer').classList.add('principal');
        $('importer').classList.remove('principal');
      });
    }).catch(function (e) {
      $('barre').hidden = true;
      $('progres').textContent = '';
      dire(ech(messageDErreur(e, etat)), 'erreur');
    }).then(function () {
      enCours = false;
      $('consigne').hidden = true;
      $('choisir').disabled = false; $('contrat').disabled = false; $('toutes').disabled = false; $('fermer').disabled = false;
      $('importer').disabled = !fichier;
    });
  }

  P.contrats.forEach(function (c) {
    var o = document.createElement('option');
    o.value = c.id; o.textContent = c.id;
    if (c.id === P.choisi) o.selected = true;
    $('contrat').appendChild(o);
  });
  $('ligne-contrat').hidden = P.contrats.length < 2;
  majCible();
  $('contrat').addEventListener('change', majCible);
  $('choisir').addEventListener('click', function () { $('fichier').click(); });
  $('fichier').addEventListener('change', function () { poserFichier($('fichier').files[0]); });
  var depot = $('depot');
  depot.addEventListener('dragover', function (e) { e.preventDefault(); depot.classList.add('survol'); });
  depot.addEventListener('dragleave', function () { depot.classList.remove('survol'); });
  depot.addEventListener('drop', function (e) {
    e.preventDefault(); depot.classList.remove('survol');
    if (!enCours && e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) poserFichier(e.dataTransfer.files[0]);
  });
  $('importer').addEventListener('click', importer);
  $('fermer').addEventListener('click', function () { if (!enCours && window.google && google.script && google.script.host) google.script.host.close(); });
}
