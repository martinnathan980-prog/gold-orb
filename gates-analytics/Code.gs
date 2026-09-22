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
   * Les échéances du programme, telles que transmises le 17/09/2026.
   */
  JALONS: [
    { semaine: '2026-S51', texte: 'Solde FWD' },                                    // 15/12/2026
    { semaine: '2027-S02', texte: 'Diffusion PH Base',  perimetre: 'BASE/OPTION' },  // 15/01/2027
    { semaine: '2027-S03', texte: 'Diffusion PH Perso', perimetre: 'PERSO' },        // 22/01/2027
    { semaine: '2027-S05', texte: 'Diffusion TO Base',  perimetre: 'BASE/OPTION' },  // 05/02/2027
    { semaine: '2027-S08', texte: 'Diffusion TO Perso', perimetre: 'PERSO' }         // 26/02/2027
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
     comme dans l'extract (accents et majuscules indifférents, valeur
     entière : « Non validé » n'en fait pas partie). S'ajoutent aux mots
     reconnus d'eux-mêmes : Terminé, Fini, Soldé, Clôturé, OK, 100 %. Les
     autres valeurs de la colonne s'affichent telles quelles, sans rien
     déclarer : la page les lit. */
  VALEURS_FINIES: ['Validé'],

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
  'Semaine', 'Date', 'Total', 'Terminés', 'En cours', 'À faire', 'Non renseignés',
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

/** Déploiement en application web. */
function doGet() {
  const page = HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Suivi FWD')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');

  return CONFIG.AUTORISER_INTEGRATION_EXTERNE
    ? page.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    : page;
}

/** Ouverture depuis le classeur, en fenêtre. */
function ouvrirTableauDeBord() {
  const page = HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Suivi FWD')
    .setWidth(2000)
    .setHeight(1400);
  SpreadsheetApp.getUi().showModalDialog(page, 'Suivi FWD');
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
    .replace(/[̀-ͯ]/g, '')
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
  const finies = (CONFIG.VALEURS_FINIES && CONFIG.VALEURS_FINIES.length ? CONFIG.VALEURS_FINIES : ['Validé']).map(normaliser);
  if (finies.indexOf(s) !== -1) return 'termine';
  if (s.indexOf('a faire') !== -1 || s.indexOf('a traiter') !== -1 || s === 'non commence') return 'afaire';
  const n = parseFloat(s.replace(/[\s%]/g, '').replace(',', '.'));
  if (!isNaN(n)) {
    if (n >= 100) return 'termine';
    if (n <= 0) return 'afaire';
    return 'encours';
  }
  if (/(termine|acheve|cloture|solde|fini|ok)/.test(s)) return 'termine';
  return 'encours';
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

function estOngletInterne(nom) {
  const n = normaliser(nom);
  /* L'onglet de la seconde base n'est pas un contrat non plus. */
  const internes = CONFIG.FEUILLES_INTERNES
    .concat(feuilleRapprochement() ? [feuilleRapprochement()] : [])
    .map(normaliser);
  if (internes.indexOf(n) !== -1) return true;
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
     contrat à côté. Sans cela, la page s'ouvrirait sur elle. */
  return classeur.getSheets()
    .filter(function (f) { return !f.isSheetHidden() && !estOngletInterne(f.getName()) && f.getLastRow() > 0; })
    .map(function (f) { return { id: f.getName(), nom: f.getName() }; });
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
function detecterLigneEntete(donnees) {
  const limite = Math.min(CONFIG.LIGNES_SCAN_ENTETE, donnees.length);
  for (let i = 0; i < limite; i++) {
    const ligne = normaliser(donnees[i].join(' '));
    for (let k = 0; k < CONFIG.MOTS_CLES_ENTETE.length; k++) {
      if (ligne.indexOf(CONFIG.MOTS_CLES_ENTETE[k]) !== -1) return i;
    }
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
  const force = indexParDesignation(CONFIG.COLONNE_FWD, entetes, groupes);
  if (force !== -1) return force;

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
  const fwdDemandeeAbsente = !!CONFIG.COLONNE_FWD && indexParDesignation(CONFIG.COLONNE_FWD, entetes, groupes) === -1;
  let iConcept = CONFIG.COLONNE_CONCEPT ? indexParDesignation(CONFIG.COLONNE_CONCEPT, entetes, groupes) : -1;
  if (iConcept === iFWD) iConcept = -1;
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
  if (lignes.length === 0) {
    // Aucune référence nulle part : on retombe sur « la ligne dit quelque chose ».
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
    avertissement: cleFWD === null
      ? 'Aucune colonne d\'avancement FWD n\'a été reconnue dans l\'en-tête.'
      : '',
    lignesIgnorees: lignesBrutes.length - lignes.length
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
  try {
    const classeur = SpreadsheetApp.getActiveSpreadsheet();
    const contrats = listerContrats(classeur);
    const modele = construireModele(contrat);
    const paquet = {
      ok: true,
      message: modele.avertissement,
      feuille: modele.feuille,
      genereLe: new Date().toISOString(),
      colonnes: modele.colonnes,
      cleDate: modele.cleDate,
      clesDim: modele.clesDim,
      clesEssentielles: modele.clesEssentielles,
      cleDomaine: modele.cleDomaine,
      cleConcept: modele.cleConcept,
      valeursFinies: CONFIG.VALEURS_FINIES,
      dimParDefaut: modele.dimParDefaut,
      lignesIgnorees: modele.lignesIgnorees,
      plans: modele.plans,
      releves: getHistorique(classeur, modele.feuille),
      jalons: getJalons(),
      contrats: contrats,
      contrat: modele.feuille
    };
    /* La seconde base, seulement si la configuration en nomme une : la page
       masque la section quand la clé est absente. */
    const rapprochement = getRapprochement(classeur);
    if (rapprochement) paquet.rapprochement = rapprochement;
    return paquet;
  } catch (err) {
    return {
      ok: false,
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
 * Le paquet du premier contrat, sérialisé pour être posé tel quel dans un
 * <script> — c'est ce que la page reçoit à l'ouverture.
 *
 * Une cellule du classeur peut contenir n'importe quoi — y compris la chaîne
 * qui ferme une balise script. Sans échappement, une seule ligne de commentaire
 * mal choisie couperait la page en deux et rien ne s'afficherait.
 */
function donneesJSONPourPage() {
  return JSON.stringify(getDonneesPourClient())
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

  const nomsFichiers = [];
  ['Index', 'Styles', 'Javascript'].forEach(function (nom) {
    try {
      const contenu = HtmlService.createHtmlOutputFromFile(nom).getContent();
      dire('✓ Fichier « ' + nom +' » : ' + contenu.length + ' caractères');
      nomsFichiers.push(nom);
    } catch (err) {
      dire('✗ Fichier « ' + nom + ' » INTROUVABLE.');
      dire('   → + → HTML, et le nommer exactement « ' + nom + ' », sans .html');
    }
  });

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

  dire('');
  const jalons = getJalons();
  dire('✓ Jalons de configuration : ' + jalons.length);
  diagnostiquerPerimetresDesJalons(contrats[0], jalons, dire);
  dire('');
  const secondeLisible = diagnostiquerSecondeBase(classeur, dire);
  try {
    const poids = donneesJSONPourPage().length;
    dire('✓ Paquet envoyé à la page : ' + Math.round(poids / 1024) + ' Ko' +
         (contrats.length > 1
           ? ' (contrat « ' + contrats[0].nom + ' », le premier ; les autres se chargent à la demande)'
           : ''));
  } catch (err) {
    dire('✗ Paquet envoyé à la page : ' + (err && err.message ? err.message : err));
    tousLisibles = false;
  }

  dire('');
  if (nomsFichiers.length !== 3) dire('Il manque des fichiers HTML (voir ci-dessus).');
  else if (!tousLisibles) dire('Un contrat au moins n\'est pas lisible (voir ci-dessus).');
  else if (!secondeLisible) dire('Tout est en place pour GATES : Suivi FWD → Ouvrir le tableau de bord. La seconde base, elle, ne se lit pas (voir ci-dessus).');
  else dire('Tout est en place : Suivi FWD → Ouvrir le tableau de bord.');

  return terminerDiagnostic(lignes);
}

/**
 * Les périmètres des jalons contre la colonne de domaine du premier contrat.
 * Un jalon dont le périmètre n'est aucune des valeurs de la colonne ne
 * ferait jamais l'échéance sous un périmètre : on le dit, avec les valeurs
 * vues, pour corriger `perimetre` dans CONFIG.JALONS. Rien à dire tant
 * qu'aucun jalon n'a de périmètre, ni quand le contrat ne se lit pas (son
 * propre diagnostic l'a déjà dit).
 */
function diagnostiquerPerimetresDesJalons(contrat, jalons, dire) {
  const avecPerimetre = jalons.filter(function (j) { return j.perimetre; });
  if (!avecPerimetre.length || !contrat) return;
  let modele;
  try {
    modele = construireModele(contrat.id);
  } catch (err) {
    return;
  }
  if (!modele.cleDomaine) {
    dire('⚠ ' + avecPerimetre.length + ' jalon(s) à périmètre, mais l\'onglet « ' + modele.feuille +
         ' » n\'a pas de colonne de domaine : ils ne feront l\'échéance que sur « Tout ».');
    return;
  }
  const vues = {};
  modele.plans.forEach(function (p) {
    const v = String(p[modele.cleDomaine] === undefined || p[modele.cleDomaine] === null ? '' : p[modele.cleDomaine]).trim();
    if (v && !vues[normaliser(v)]) vues[normaliser(v)] = v;
  });
  const valeurs = Object.keys(vues).map(function (k) { return vues[k]; });
  const inconnus = avecPerimetre.filter(function (j) { return !vues[normaliser(j.perimetre)]; });
  const colonne = modele.colonnes.filter(function (c) { return c.cle === modele.cleDomaine; })[0];
  const titre = colonne ? colonne.titre : modele.cleDomaine;
  if (!inconnus.length) {
    dire('  périmètres des jalons : ' + avecPerimetre.map(function (j) { return j.perimetre; })
      .filter(function (v, i, t) { return t.indexOf(v) === i; }).join(', ') +
      ' — tous connus de la colonne « ' + titre + ' »');
    return;
  }
  inconnus.forEach(function (j) {
    dire('⚠ Jalon « ' + j.texte + ' » : périmètre « ' + j.perimetre + ' » inconnu de la colonne « ' + titre + ' »');
  });
  dire('   → valeurs vues dans « ' + titre + ' » : ' + (valeurs.length ? valeurs.slice(0, 8).join(', ') : 'aucune') +
       (valeurs.length > 8 ? ', …' : '') + ' — à recopier dans perimetre (CONFIG.JALONS).');
}

/**
 * La seconde base telle que le script la voit — c'est la réponse à « je ne
 * vois pas les deux cercles » : l'onglet manque, il est vide, ou sa
 * référence ne s'y trouve pas. Renvoie faux quand un onglet est là mais ne
 * se lit pas : le bilan final le redit, pour ne pas conclure « tout est en
 * place » sous un avertissement.
 */
function diagnostiquerSecondeBase(classeur, dire) {
  const base = lireSecondeBase(classeur);
  const cfg = CONFIG.RAPPROCHEMENT || {};
  const nom = '« ' + (String(cfg.NOM || base.onglet || '').trim() || 'seconde base') + ' »';
  switch (base.etat) {
    case 'sans-configuration':
      dire('– Seconde base : ' + (!base.onglet
        ? 'aucun nom d\'onglet (RAPPROCHEMENT.FEUILLE et NOM vides)'
        : 'aucune référence (RAPPROCHEMENT.CLE_REFERENCE vide)') + ' — pas de rapprochement.');
      return true;
    case 'absent':
      dire('– Seconde base ' + nom + ' : aucun onglet « ' + base.onglet + ' » — pas de rapprochement.');
      dire('   → un onglet nommé « ' + base.onglet + ' », l\'extract collé en A1 tel quel, avec ses colonnes ' +
           base.cles.join(', ') + '.');
      return true;
    case 'vide':
      dire('⚠ Seconde base ' + nom + ' : l\'onglet « ' + base.onglet + ' » est vide — pas de rapprochement.');
      dire('   → coller l\'extract en A1.');
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
      dire('✓ Seconde base « ' + base.rapprochement.nom + ' » : onglet « ' + base.onglet + ' », ' +
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
function direValeurs(dire, plans, cle) {
  const par = {}, ordre = [];
  plans.forEach(function (p) {
    const brut = String(p[cle] === null || p[cle] === undefined ? '' : p[cle]).trim();
    const k = normaliser(brut);
    if (!(k in par)) { par[k] = { brut: brut, n: 0 }; ordre.push(k); }
    par[k].n++;
  });
  if (ordre.length > 20 || ordre.some(function (k) { return par[k].brut.length > 30; })) {
    dire('  ' + ordre.length + ' valeurs différentes : trop, ou trop longues, pour être des états — rien n\'est recopié.');
    return;
  }
  ordre.sort(function (a, b) { return par[b].n - par[a].n; });
  dire('  valeurs lues : ' + ordre.map(function (k) {
    const v = par[k];
    return (v.brut === '' ? '(vide)' : '« ' + v.brut + ' »') + ' ' + v.n + (classerFWD(v.brut) === 'termine' ? ' = fini' : '');
  }).join(' · '));
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
    dire('✓ Ligne d\'en-têtes : ligne ' + (iEntete + 1));
    dire('  ' + donnees[iEntete].filter(function (e) { return String(e).trim(); }).join(' | '));

    const modele = construireModele(contrat.id);
    dire('✓ ' + modele.colonnes.length + ' colonnes, ' + modele.plans.length + ' plans');

    const colFWD = modele.colonnes.filter(function (c) { return c.cle === 'avancement'; })[0];
    if (modele.avertissement) {
      dire('✗ ' + modele.avertissement);
      dire('   → la page s\'affichera, mais tout sera « non renseigné ».');
    } else {
      dire('✓ Avancement FWD : colonne « ' + colFWD.titre + ' »' +
           (colFWD.groupe ? ', groupe « ' + colFWD.groupe + ' »' : ''));
      if (modele.fwdDemandeeAbsente) {
        dire('⚠ La colonne demandée (CONFIG.COLONNE_FWD « ' + CONFIG.COLONNE_FWD + ' ») est introuvable dans cet extract :');
        dire('   la page suit celle ci-dessus, trouvée d\'elle-même. Vérifier le nom du groupe et de la colonne.');
      }
      const compte = { termine: 0, encours: 0, afaire: 0, vide: 0 };
      modele.plans.forEach(function (p) { compte[classerFWD(p.avancement)]++; });
      dire('  ' + compte.termine + ' terminés, ' + compte.encours + ' en cours, ' +
           compte.afaire + ' à faire, ' + compte.vide + ' non renseignés');
      direValeurs(dire, modele.plans, 'avancement');
    }
    if (CONFIG.COLONNE_CONCEPT) {
      const colConcept = modele.cleConcept ? modele.colonnes.filter(function (c) { return c.cle === modele.cleConcept; })[0] : null;
      if (colConcept) {
        const compteC = { termine: 0, encours: 0, afaire: 0, vide: 0 };
        modele.plans.forEach(function (p) { compteC[classerFWD(p[modele.cleConcept])]++; });
        dire('✓ Concept harnais : colonne « ' + colConcept.titre + ' »' + (colConcept.groupe ? ', groupe « ' + colConcept.groupe + ' »' : ''));
        dire('  ' + compteC.termine + ' terminés, ' + compteC.encours + ' en cours, ' +
             compteC.afaire + ' à faire, ' + compteC.vide + ' non renseignés');
        direValeurs(dire, modele.plans, modele.cleConcept);
      } else {
        dire('– Concept harnais : colonne « ' + CONFIG.COLONNE_CONCEPT + ' » introuvable dans cet extract — pas d\'interrupteur.');
      }
    }

    const colRef = modele.colonnes.filter(function (c) { return c.fige; })[0];
    dire('✓ Référence figée : colonne « ' + (colRef ? colRef.titre : '?') + ' »');
    if (modele.lignesIgnorees > 0) {
      dire('  ' + modele.lignesIgnorees + ' ligne(s) sans référence ignorée(s)');
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
    }
    return true;
  } catch (err) {
    dire('✗ ERREUR : ' + (err && err.message ? err.message : err));
    if (err && err.stack) dire(String(err.stack).split('\n').slice(0, 3).join('\n'));
    return false;
  }
}

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
  const clesDim = modele.clesDim.concat(modele.cleDate ? ['_anciennete'] : []);
  const maintenant = new Date();
  const reference = new Date(Date.UTC(maintenant.getFullYear(), maintenant.getMonth(), maintenant.getDate()));

  const compte = {
    total: modele.plans.length,
    termine: 0, encours: 0, afaire: 0, vide: 0,
    groupes: {}, plans: {}
  };
  clesDim.forEach(function (d) { compte.groupes[d] = {}; });

  modele.plans.forEach(function (p) {
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
 * commence jamais par « = » : Sheets la prendrait pour une formule.
 */
function decouper(texte, taille) {
  const morceaux = [];
  let debut = 0;
  while (debut < texte.length) {
    let fin = Math.min(debut + taille, texte.length);
    while (fin < texte.length && fin > debut + 1 && texte.charAt(fin) === '=') fin--;
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
function enregistrerInstantaneHebdo() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const semaine = numeroSemaineISO(new Date());
  const contrats = listerContrats(classeur);
  if (contrats.length === 0) {
    throw new Error(messageSansContrat(classeur));
  }

  const detail = [];
  const erreurs = [];
  contrats.forEach(function (c) {
    try {
      detail.push(archiverContrat(classeur, c, semaine));
    } catch (err) {
      erreurs.push('« ' + c.nom + ' » : ' + (err && err.message ? err.message : err));
    }
  });

  if (erreurs.length) {
    throw new Error('Relevé ' + semaine + ' — ' +
      (detail.length ? detail.length + ' contrat(s) archivé(s), ' : '') +
      erreurs.length + ' en erreur : ' + erreurs.join(' ; '));
  }
  /* Lancé du menu, le geste doit se voir : sans cela, Sheets n'affiche que
     « Script terminé », et on ne sait pas si c'est fait. Lancé par le
     déclencheur du vendredi, il n'y a personne devant : pas d'interface, et
     l'appel ci-dessous échoue en silence. */
  const mot = 'Relevé ' + semaine + ' archivé : ' + detail.map(function (d) {
    return d.nom + ' (' + d.compte.total + ' plans)';
  }).join(', ') + '.' + (detail.length ? ' Un second archivage dans la semaine remplace celui-ci.' : '');
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
  /* La carte plan par plan ne tient plus dans une cellule au-delà de
     quelques milliers de plans : elle s'étale sur autant de cellules
     qu'il faut, à partir de la colonne « Plans ». La jeter, comme avant,
     privait ces relevés de périmètre, de journal et de comparatif. */
  const ligne = [
    semaine, new Date(), compte.total, compte.termine, compte.encours,
    compte.afaire, compte.vide,
    jsonTenable(compte.groupes)
  ].concat(decouper(JSON.stringify(compte.plans), MAX_CARACTERES_CELLULE));
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
  return { id: c.id, nom: c.nom, historique: feuille.getName(), semaine: semaine, compte: compte };
}

/**
 * Retire le relevé de la semaine courante — pour rattraper un mauvais export —
 * de tous les contrats, et récapitule à l'écran ce qui a été retiré et ce qui
 * n'avait rien.
 */
function supprimerDernierReleve() {
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

  const nommer = function (liste) { return liste.map(function (n) { return '« ' + n + ' »'; }).join(', '); };
  let message;
  if (!supprimes.length) {
    message = 'Aucun relevé pour la semaine ' + semaine + '.';
  } else if (contrats.length === 1) {
    message = 'Relevé ' + semaine + ' supprimé. Recollez le bon export puis relancez l\'archivage.';
  } else {
    message = 'Relevé ' + semaine + ' supprimé pour ' + nommer(supprimes) +
      (sans.length ? ' ; aucun relevé pour ' + nommer(sans) : '') +
      '. Recollez le bon export puis relancez l\'archivage.';
  }
  ui.alert(message);
  return { semaine: semaine, supprimes: supprimes, sans: sans };
}

function installerSuiviHebdomadaire() {
  desinstallerSuiviHebdomadaire();
  ScriptApp.newTrigger('enregistrerInstantaneHebdo')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.FRIDAY)
    .atHour(17)
    .create();
  SpreadsheetApp.getUi().alert('Archivage automatique activé : chaque vendredi vers 17 h.');
}

function desinstallerSuiviHebdomadaire() {
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
function getJalons() {
  const liste = Array.isArray(CONFIG.JALONS) ? CONFIG.JALONS : [];
  return liste
    .map(function (j) {
      const semaine = normaliserSemaine(j && j.semaine);
      if (!semaine) return null;
      const jalon = {
        semaine: semaine,
        texte: String((j && j.texte) || 'Jalon').trim().slice(0, 60) || 'Jalon'
      };
      const perimetre = String((j && j.perimetre) || '').trim().slice(0, 40);
      if (perimetre) jalon.perimetre = perimetre;
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
function getRapprochement(classeur) {
  return lireSecondeBase(classeur).rapprochement;
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
function lireSecondeBase(classeur) {
  const cfg = CONFIG.RAPPROCHEMENT;
  const nomFeuille = feuilleRapprochement();
  const clesVoulues = !cfg ? [] : [].concat(cfg.CLE_REFERENCE === undefined || cfg.CLE_REFERENCE === null ? [] : cfg.CLE_REFERENCE)
    .map(function (c) { return String(c).trim(); }).filter(Boolean);
  const rendu = { etat: 'sans-configuration', onglet: nomFeuille, cles: clesVoulues, entetes: [], ligneEntete: null, rapprochement: null };
  if (!cfg || !nomFeuille || !clesVoulues.length) return rendu;
  const feuille = classeur.getSheetByName(nomFeuille);
  if (!feuille) { rendu.etat = 'absent'; return rendu; }
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
    entetes.forEach(function (titre, j) {
      if (!titre) return;
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
