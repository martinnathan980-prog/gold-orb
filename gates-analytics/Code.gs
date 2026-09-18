/**
 * Suivi FWD — tableau de bord des plans d'intégration électrique
 * =============================================================
 * Côté serveur (Google Apps Script).
 *
 * Ce fichier ne fait que cinq choses :
 *   1. lire l'onglet de données et en déduire un modèle de colonnes
 *      (aucun nom de colonne n'est écrit en dur : tout vient de l'en-tête) ;
 *   2. classer l'avancement FWD de chaque ligne en quatre états ;
 *   3. entretenir un historique hebdomadaire réel (onglet « Historique_FWD ») ;
 *   4. fournir les jalons du programme, fixés ici dans la configuration :
 *      la page les montre, personne ne les modifie à l'écran ;
 *   5. lire, si la configuration en nomme un, l'onglet d'une seconde base à
 *      rapprocher des plans (CONFIG.RAPPROCHEMENT) — la page fait le reste.
 *
 * La page est rendue d'une traite : Index.html injecte le paquet de données
 * dans la page au moment de l'évaluation du modèle, sans aller-retour.
 */

// =====================================================================
//  CONFIGURATION
// =====================================================================
const CONFIG = {
  /** Nom de l'onglet de données. Vide = premier onglet visible qui n'est pas interne. */
  FEUILLE_DONNEES: '',

  /** Onglet où sont stockés les instantanés hebdomadaires. */
  FEUILLE_HISTORIQUE: 'Historique_FWD',

  /** Onglets ignorés lors de la détection automatique de la feuille de données. */
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
   * DATES PROVISOIRES, à remplacer par les vraies échéances du programme.
   */
  JALONS: [
    { semaine: '2026-S44', texte: 'Gel de la définition' },
    { semaine: '2026-S52', texte: 'Revue critique' },
    { semaine: '2027-S12', texte: 'Livraison plateau' },
    { semaine: '2027-S26', texte: 'Premier vol' }
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
   *   'Réalisation FWD > Avancement'.
   * DIMENSIONS : intitulés des colonnes proposées dans « Avancement FWD par… »,
   *   dans l'ordre voulu. Même syntaxe « Groupe > Colonne » en cas de doublon.
   */
  COLONNE_FWD: '',

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
    'Réalisation FWD > Avancement'
  ],

  /**
   * La colonne qui dit si un plan est du perso ou de la base/option. Elle
   * pilote le filtre rapide en haut du tableau. Vide = détection par
   * l'intitulé « domaine ».
   */
  COLONNE_DOMAINE: 'Domaine',

  /**
   * Rapprochement avec une seconde base — l'extract d'un autre outil, collé
   * dans un onglet de ce classeur, dont la structure n'est pas celle de
   * l'export GATES. La page apparie ses lignes aux plans par la racine de la
   * référence UD, puis compare les champs déclarés ici.
   *
   * À RENSEIGNER QUAND LA SECONDE BASE SERA CONNUE. Tant que FEUILLE est
   * vide, rien n'est lu et la section n'apparaît pas dans la page.
   *
   * FEUILLE        : nom de l'onglet qui porte l'extract (en-tête = première
   *                  ligne non vide, données en dessous).
   * NOM            : nom affiché dans la page ; vide = le nom de l'onglet.
   * CLE_REFERENCE  : intitulé, dans cet onglet, de la colonne de référence UD.
   * CHAMPS         : les champs à comparer, [{ ici, la, titre }] :
   *                    ici   = colonne de l'export GATES, désignée comme
   *                            ailleurs dans cette configuration (intitulé,
   *                            ou « Groupe > Colonne » en cas de doublon) ;
   *                    la    = intitulé de la colonne dans le second onglet ;
   *                    titre = comment la page nomme ce champ.
   *                  L'avancement FWD se compare par état (terminé, en
   *                  cours…), les autres champs à la lettre près, sans tenir
   *                  compte de la casse ni des accents.
   *
   * Exemple, pour un extract dont les colonnes seraient REF_UD, ATA_CODE et
   * STATUT_FWD :
   *   FEUILLE: 'Base FWD', CLE_REFERENCE: 'REF_UD',
   *   CHAMPS: [ { ici: 'ATA', la: 'ATA_CODE', titre: 'ATA' },
   *             { ici: 'Réalisation FWD > Avancement', la: 'STATUT_FWD', titre: 'Avancement' } ]
   */
  RAPPROCHEMENT: {
    FEUILLE: '',
    NOM: '',
    CLE_REFERENCE: '',
    CHAMPS: []
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

/** Une cellule de feuille de calcul ne tient pas plus de 50 000 caractères. */
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
  if (s === '' || s === '-') return 'vide';
  if (s.indexOf('a faire') !== -1 || s === 'non commence') return 'afaire';
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
//  LECTURE DE LA FEUILLE
// =====================================================================

/**
 * Renvoie la feuille de données.
 * On résout un onglet déterministe plutôt que getActiveSheet() : sinon le
 * tableau de bord lirait l'onglet cliqué en dernier, « Historique_FWD » compris.
 */
function getFeuilleDonnees(classeur) {
  if (CONFIG.FEUILLE_DONNEES) {
    const nommee = classeur.getSheetByName(CONFIG.FEUILLE_DONNEES);
    if (!nommee) {
      throw new Error('L\'onglet « ' + CONFIG.FEUILLE_DONNEES + ' » est introuvable.');
    }
    return nommee;
  }
  /* L'onglet de la seconde base, s'il est nommé, n'est pas l'onglet de données. */
  const internes = CONFIG.FEUILLES_INTERNES
    .concat(CONFIG.RAPPROCHEMENT && CONFIG.RAPPROCHEMENT.FEUILLE ? [CONFIG.RAPPROCHEMENT.FEUILLE] : [])
    .map(normaliser);
  const candidates = classeur.getSheets().filter(function (f) {
    return !f.isSheetHidden() && internes.indexOf(normaliser(f.getName())) === -1;
  });
  if (candidates.length === 0) {
    throw new Error('Aucun onglet de données exploitable dans ce classeur.');
  }
  return candidates[0];
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

function construireModele() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = getFeuilleDonnees(classeur);
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

  for (let i = 0; i < nbColonnes; i++) {
    const titre = entetes[i] || ('Colonne ' + (i + 1));
    const cle = (i === iRef) ? 'reference'
              : (i === iFWD) ? 'avancement'
              : cleDepuisEntete(titre, deja);
    if (i === iFWD) cleFWD = cle;
    if (i === iDate) cleDate = cle;

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
 * `contrat` désigne le contrat demandé ; pour l'instant le classeur n'en
 * porte qu'un — l'onglet de données — et le paramètre est ignoré. La page
 * reçoit néanmoins la liste des contrats et celui qui est servi, ce qui lui
 * permet d'afficher (ou non) son sélecteur sans rien savoir du classeur.
 */
function getDonneesPourClient(contrat) {
  try {
    const classeur = SpreadsheetApp.getActiveSpreadsheet();
    const modele = construireModele();
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
      dimParDefaut: modele.dimParDefaut,
      lignesIgnorees: modele.lignesIgnorees,
      plans: modele.plans,
      releves: getHistorique(classeur),
      jalons: getJalons(),
      contrats: [{ id: modele.feuille, nom: modele.feuille }],
      contrat: modele.feuille
    };
    /* La seconde base, seulement si la configuration en nomme une : la page
       masque la section quand la clé est absente. */
    const rapprochement = getRapprochement(classeur, modele.colonnes);
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
 * Le paquet, sérialisé pour être posé tel quel dans un <script>.
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

  let feuille = null;
  try {
    feuille = getFeuilleDonnees(classeur);
    dire('✓ Onglet de données : « ' + feuille.getName() + ' »');
  } catch (err) {
    dire('✗ Onglet de données : ' + err.message);
    return terminerDiagnostic(lignes);
  }

  try {
    const donnees = feuille.getDataRange().getDisplayValues();
    dire('  ' + donnees.length + ' lignes lues dans l\'onglet');
    if (donnees.length === 0) {
      dire('✗ L\'onglet est vide : collez l\'export GATES en A1.');
      return terminerDiagnostic(lignes);
    }
    const iEntete = detecterLigneEntete(donnees);
    dire('✓ Ligne d\'en-têtes : ligne ' + (iEntete + 1));
    dire('  ' + donnees[iEntete].filter(function (e) { return String(e).trim(); }).join(' | '));

    const modele = construireModele();
    dire('✓ ' + modele.colonnes.length + ' colonnes, ' + modele.plans.length + ' plans');

    const colFWD = modele.colonnes.filter(function (c) { return c.cle === 'avancement'; })[0];
    if (modele.avertissement) {
      dire('✗ ' + modele.avertissement);
      dire('   → la page s\'affichera, mais tout sera « non renseigné ».');
    } else {
      dire('✓ Avancement FWD : colonne « ' + colFWD.titre + ' »' +
           (colFWD.groupe ? ', groupe « ' + colFWD.groupe + ' »' : ''));
      const compte = { termine: 0, encours: 0, afaire: 0, vide: 0 };
      modele.plans.forEach(function (p) { compte[classerFWD(p.avancement)]++; });
      dire('  ' + compte.termine + ' terminés, ' + compte.encours + ' en cours, ' +
           compte.afaire + ' à faire, ' + compte.vide + ' non renseignés');
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

    const histo = getHistorique(classeur);
    dire('✓ Relevés archivés : ' + histo.length);
    if (histo.length === 0) {
      dire('   → Suivi FWD → Archiver le relevé de cette semaine.');
      dire('     Sans relevé, pas de courbe ni de fin estimée.');
    } else {
      dire('  du ' + histo[0].semaine + ' au ' + histo[histo.length - 1].semaine);
    }
    dire('✓ Jalons de configuration : ' + getJalons().length);

    const poids = donneesJSONPourPage().length;
    dire('✓ Paquet envoyé à la page : ' + Math.round(poids / 1024) + ' Ko');

    dire('');
    dire(nomsFichiers.length === 3
      ? 'Tout est en place : Suivi FWD → Ouvrir le tableau de bord.'
      : 'Il manque des fichiers HTML (voir ci-dessus).');
  } catch (err) {
    dire('✗ ERREUR : ' + (err && err.message ? err.message : err));
    if (err && err.stack) dire(String(err.stack).split('\n').slice(0, 3).join('\n'));
  }

  return terminerDiagnostic(lignes);
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
//  HISTORIQUE
//  L'export ne contient que l'état du jour : on ne sait pas quand un plan est
//  passé à 100 %. L'historique ne peut donc pas être reconstitué, seulement
//  accumulé — un relevé par semaine ISO. Rien n'est jamais supprimé.
// =====================================================================

function getFeuilleHistorique(classeur, creerSiAbsente) {
  let feuille = classeur.getSheetByName(CONFIG.FEUILLE_HISTORIQUE);
  if (!feuille && creerSiAbsente) {
    feuille = classeur.insertSheet(CONFIG.FEUILLE_HISTORIQUE);
    feuille.appendRow(ENTETES_HISTORIQUE);
    feuille.getRange(1, 1, 1, ENTETES_HISTORIQUE.length).setFontWeight('bold');
    feuille.setFrozenRows(1);
    feuille.hideSheet();
  }
  return feuille;
}

/** Lit l'onglet Historique : un objet par relevé, trié par semaine. */
function getHistorique(classeur) {
  const feuille = getFeuilleHistorique(classeur, false);
  if (!feuille || feuille.getLastRow() < 2) return [];

  const valeurs = feuille.getRange(2, 1, feuille.getLastRow() - 1, ENTETES_HISTORIQUE.length).getValues();
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
      groupes: analyserJson(ligne[7]) || {},
      plans: analyserJson(ligne[8])
    };
  });

  return Object.keys(parSemaine).sort().map(function (s) { return parSemaine[s]; });
}

function analyserJson(valeur) {
  if (!valeur) return null;
  try { return JSON.parse(valeur); } catch (err) { return null; }
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

/** Compte l'état du jour : global, par dimension, et plan par plan. */
function compterAvancements() {
  const modele = construireModele();
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
    compte.plans[p.reference] = String(p.avancement || '');
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

/** Sérialise sans jamais dépasser ce qu'une cellule peut contenir. */
function jsonTenable(valeur) {
  const texte = JSON.stringify(valeur);
  return texte.length > MAX_CARACTERES_CELLULE ? '' : texte;
}

/**
 * Archive le relevé de la semaine courante.
 * Idempotent : réimporter dans la même semaine met la ligne à jour au lieu
 * d'en empiler une seconde.
 */
function enregistrerInstantaneHebdo() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const compte = compterAvancements();
  const semaine = numeroSemaineISO(new Date());
  const ligne = [
    semaine, new Date(), compte.total, compte.termine, compte.encours,
    compte.afaire, compte.vide,
    jsonTenable(compte.groupes),
    jsonTenable(compte.plans)
  ];

  const feuille = getFeuilleHistorique(classeur, true);
  const derniere = feuille.getLastRow();
  let indexLigne = -1;
  if (derniere >= 2) {
    const semaines = feuille.getRange(2, 1, derniere - 1, 1).getValues();
    for (let i = 0; i < semaines.length; i++) {
      if (normaliserSemaine(semaines[i][0]) === semaine) { indexLigne = i + 2; break; }
    }
  }

  if (indexLigne === -1) feuille.appendRow(ligne);
  else feuille.getRange(indexLigne, 1, 1, ligne.length).setValues([ligne]);

  return { ok: true, semaine: semaine, compte: compte };
}

/** Retire le relevé de la semaine courante — pour rattraper un mauvais export. */
function supprimerDernierReleve() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = getFeuilleHistorique(classeur, false);
  const ui = SpreadsheetApp.getUi();
  if (!feuille || feuille.getLastRow() < 2) {
    ui.alert('Aucun relevé à supprimer.');
    return;
  }
  const semaine = numeroSemaineISO(new Date());
  const semaines = feuille.getRange(2, 1, feuille.getLastRow() - 1, 1).getValues();
  for (let i = semaines.length - 1; i >= 0; i--) {
    if (normaliserSemaine(semaines[i][0]) === semaine) {
      feuille.deleteRow(i + 2);
      ui.alert('Relevé ' + semaine + ' supprimé. Recollez le bon export puis relancez l\'archivage.');
      return;
    }
  }
  ui.alert('Aucun relevé pour la semaine ' + semaine + '.');
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
 * coupé à 60 caractères, entrées illisibles écartées, tri par semaine,
 * plafond MAX_JALONS. Une faute de frappe dans la configuration ne fait
 * donc jamais tomber la page — le jalon fautif est simplement absent.
 */
function getJalons() {
  const liste = Array.isArray(CONFIG.JALONS) ? CONFIG.JALONS : [];
  return liste
    .map(function (j) {
      const semaine = normaliserSemaine(j && j.semaine);
      if (!semaine) return null;
      return {
        semaine: semaine,
        texte: String((j && j.texte) || 'Jalon').trim().slice(0, 60) || 'Jalon'
      };
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
 * champs, lignes }, ou null tant que CONFIG.RAPPROCHEMENT.FEUILLE est vide
 * — la page n'affiche alors pas la section.
 *
 * L'onglet est lu tel quel : l'en-tête est la première ligne non vide, les
 * lignes suivantes deviennent des objets { intitulé: valeur }. Les intitulés
 * sont conservés à la lettre, puisque c'est par eux que CHAMPS désigne les
 * colonnes de la seconde base. Côté GATES, `ici` est une désignation comme
 * ailleurs dans la configuration (intitulé, ou « Groupe > Colonne ») et se
 * résout en clé de colonne ; un champ dont l'un des deux côtés est introuvable
 * est écarté, pas la section entière.
 *
 * @param {Spreadsheet} classeur
 * @param {Array} colonnes  les colonnes du modèle GATES ({ cle, titre, groupe })
 */
function getRapprochement(classeur, colonnes) {
  const cfg = CONFIG.RAPPROCHEMENT;
  if (!cfg || !cfg.FEUILLE) return null;
  const feuille = classeur.getSheetByName(cfg.FEUILLE);
  if (!feuille) return null;

  const donnees = feuille.getDataRange().getDisplayValues();
  let indexEntete = -1;
  for (let i = 0; i < donnees.length; i++) {
    if (ligneNonVide(donnees[i])) { indexEntete = i; break; }
  }
  if (indexEntete === -1) return null;
  const entetes = donnees[indexEntete].map(function (e) { return String(e).trim(); });

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
  function cleIci(designation) {
    const liste = Array.isArray(colonnes) ? colonnes : [];
    const voulu = normaliser(designation);
    if (!voulu) return '';
    for (let i = 0; i < liste.length; i++) {
      const c = liste[i];
      if (c.cle === designation) return c.cle;
      if (normaliser(c.titre) === voulu) return c.cle;
      if (normaliser((c.groupe || '') + ' > ' + c.titre) === voulu) return c.cle;
    }
    return '';
  }

  const cleReference = enteteLa(cfg.CLE_REFERENCE);
  if (!cleReference) return null;
  const champs = (Array.isArray(cfg.CHAMPS) ? cfg.CHAMPS : [])
    .map(function (c) {
      if (!c) return null;
      const ici = cleIci(c.ici), la = enteteLa(c.la);
      if (!ici || !la) return null;
      return { ici: ici, la: la, titre: String(c.titre || c.la).trim().slice(0, 60) || la };
    })
    .filter(function (c) { return c !== null; });

  return {
    nom: String(cfg.NOM || feuille.getName()).trim().slice(0, 80) || feuille.getName(),
    cleReference: cleReference,
    champs: champs,
    lignes: lignes
  };
}
