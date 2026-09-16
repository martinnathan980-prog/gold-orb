/**
 * Suivi FWD — tableau de bord des plans d'intégration électrique
 * =============================================================
 * Côté serveur (Google Apps Script).
 *
 * Ce fichier ne fait que quatre choses :
 *   1. lire l'onglet de données et en déduire un modèle de colonnes
 *      (aucun nom de colonne n'est écrit en dur : tout vient de l'en-tête) ;
 *   2. classer l'avancement FWD de chaque ligne en quatre états ;
 *   3. entretenir un historique hebdomadaire réel (onglet « Historique_FWD ») ;
 *   4. stocker les jalons, partagés par tous ceux qui ouvrent le classeur.
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

  /** Clé de stockage des jalons dans les propriétés du document. */
  CLE_JALONS: 'SUIVI_FWD_JALONS',

  /** Nombre maximum de jalons conservés. */
  MAX_JALONS: 40,

  /** Au-delà, une colonne est considérée comme un identifiant, pas une catégorie. */
  MAX_VALEURS_DIMENSION: 40,

  /** Nombre maximum de dimensions proposées dans « Grouper par ». */
  MAX_DIMENSIONS: 8,

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
  const internes = CONFIG.FEUILLES_INTERNES.map(normaliser);
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

/** Propage les groupes fusionnés (la ligne au-dessus de l'en-tête) vers la droite. */
function propagerGroupes(groupes, nbColonnes) {
  const resultat = new Array(nbColonnes);
  let dernier = '';
  for (let i = 0; i < nbColonnes; i++) {
    const valeur = groupes && groupes[i] ? String(groupes[i]).trim() : '';
    if (valeur !== '') dernier = valeur;
    resultat[i] = dernier;
  }
  return resultat;
}

/** Index de la colonne d'avancement FWD, du critère le plus précis au plus large. */
function trouverIndexFWD(entetes, groupes) {
  const criteres = [
    function (col, grp) { return col.indexOf('avancement') !== -1 && (grp.indexOf('fwd') !== -1 || col.indexOf('fwd') !== -1); },
    function (col, grp) { return col.indexOf('realisation') !== -1 && (grp.indexOf('fwd') !== -1 || col.indexOf('fwd') !== -1); },
    function (col) { return col.indexOf('fwd') !== -1; },
    function (col) { return col.indexOf('avancement') !== -1; }
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

function colonneRessembleAUneDate(lignes, index) {
  let vues = 0, dates = 0;
  for (let i = 0; i < lignes.length && vues < 40; i++) {
    const v = String(lignes[i][index] || '').trim();
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
  const groupes = propagerGroupes(indexEntete > 0 ? donnees[indexEntete - 1] : [], nbColonnes);
  const lignes = donnees.slice(indexEntete + 1).filter(ligneNonVide);

  const iFWD = trouverIndexFWD(entetes, groupes);
  const iRef = trouverIndexReference(entetes);
  const iDate = trouverIndexDate(entetes, lignes);

  // Statistiques par colonne : longueur moyenne et nombre de valeurs distinctes.
  const stats = [];
  for (let c = 0; c < nbColonnes; c++) {
    const distinctes = {};
    let nDistinctes = 0, somme = 0, remplies = 0;
    for (let l = 0; l < lignes.length; l++) {
      const v = String(lignes[l][c] === undefined ? '' : lignes[l][c]).trim();
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

  const deja = {};
  const colonnes = [];
  let cleFWD = null, cleRef = null, cleDate = null;
  let nbDims = 0;

  for (let i = 0; i < nbColonnes; i++) {
    const titre = entetes[i] || ('Colonne ' + (i + 1));
    const cle = (i === iRef) ? 'reference'
              : (i === iFWD) ? 'avancement'
              : cleDepuisEntete(titre, deja);
    if (i === iRef) { deja.reference = true; cleRef = cle; }
    if (i === iFWD) { deja.avancement = true; cleFWD = cle; }
    if (i === iDate) cleDate = cle;

    const s = stats[i];
    let classe = '';
    if (i === iRef) classe = 'ref';
    else if (s.longueurMoyenne > 28) classe = 'large';
    else if (s.longueurMoyenne <= 12) classe = 'num';

    /* Une colonne est une « dimension » si elle se comporte comme une
       catégorie : assez de valeurs pour distinguer, assez peu pour regrouper. */
    const categorielle = i !== iRef && i !== iFWD && i !== iDate &&
      s.distinctes >= 2 &&
      s.distinctes <= CONFIG.MAX_VALEURS_DIMENSION &&
      s.distinctes <= Math.max(2, lignes.length / 2) &&
      s.longueurMoyenne <= 28 &&
      nbDims < CONFIG.MAX_DIMENSIONS;
    if (categorielle) nbDims++;

    const col = { cle: cle, groupe: groupes[i] || '', titre: titre, classe: classe };
    if (i === iRef) col.fige = true;
    if (categorielle) col.dim = true;
    colonnes.push(col);
  }

  const plans = lignes.map(function (ligne, n) {
    const p = {};
    for (let i = 0; i < nbColonnes; i++) {
      p[colonnes[i].cle] = String(ligne[i] === undefined ? '' : ligne[i]).trim();
    }
    // Une référence vide rendrait le comparatif faux : on en fabrique une stable.
    if (!p.reference) p.reference = 'ligne-' + (n + 1);
    // Sans colonne d'avancement reconnue, tout est « non renseigné », et le
    // message d'avertissement dit pourquoi plutôt que de laisser deviner.
    if (cleFWD === null) p.avancement = '';
    return p;
  });

  const clesDim = colonnes.filter(function (c) { return c.dim; }).map(function (c) { return c.cle; });

  return {
    feuille: feuille.getName(),
    colonnes: colonnes,
    plans: plans,
    cleDate: cleDate,
    clesDim: clesDim,
    dimParDefaut: choisirDimensionParDefaut(colonnes, clesDim),
    avertissement: cleFWD === null
      ? 'Aucune colonne d\'avancement FWD n\'a été reconnue dans l\'en-tête.'
      : ''
  };
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

function getDonneesPourClient() {
  try {
    const classeur = SpreadsheetApp.getActiveSpreadsheet();
    const modele = construireModele();
    return {
      ok: true,
      message: modele.avertissement,
      feuille: modele.feuille,
      genereLe: new Date().toISOString(),
      colonnes: modele.colonnes,
      cleDate: modele.cleDate,
      dimParDefaut: modele.dimParDefaut,
      plans: modele.plans,
      releves: getHistorique(classeur),
      jalons: getJalons()
    };
  } catch (err) {
    return {
      ok: false,
      message: err && err.message ? err.message : String(err),
      feuille: '',
      genereLe: new Date().toISOString(),
      colonnes: [], cleDate: null, dimParDefaut: '', plans: [], releves: [], jalons: []
    };
  }
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
//  JALONS (persistants, partagés par tous les utilisateurs du classeur)
// =====================================================================

function getJalons() {
  try {
    const brut = PropertiesService.getDocumentProperties().getProperty(CONFIG.CLE_JALONS);
    if (!brut) return [];
    const liste = JSON.parse(brut);
    return Array.isArray(liste) ? liste : [];
  } catch (err) {
    return [];
  }
}

/**
 * Remplace la liste entière. La page envoie toujours son état complet :
 * poser, déplacer et retirer passent par le même chemin, donc il n'y a pas
 * de demi-état possible entre le classeur et l'écran.
 */
function sauverJalons(liste) {
  const propres = (Array.isArray(liste) ? liste : [])
    .map(function (j) {
      const semaine = normaliserSemaine(j && j.semaine);
      if (!semaine) return null;
      return {
        id: (j && j.id) ? String(j.id) : Utilities.getUuid(),
        semaine: semaine,
        texte: String((j && j.texte) || 'Jalon').trim().slice(0, 60) || 'Jalon'
      };
    })
    .filter(function (j) { return j !== null; })
    .sort(function (a, b) { return a.semaine < b.semaine ? -1 : (a.semaine > b.semaine ? 1 : 0); })
    .slice(0, CONFIG.MAX_JALONS);

  PropertiesService.getDocumentProperties()
    .setProperty(CONFIG.CLE_JALONS, JSON.stringify(propres));
  return propres;
}
