/**
 * GATES Analytics — Suivi des plans d'intégration électrique
 * ============================================================
 * Côté serveur (Google Apps Script).
 *
 * Responsabilités :
 *   - lire la feuille de données (détection automatique des en-têtes et des groupes) ;
 *   - classer l'avancement FWD de chaque ligne ;
 *   - entretenir un historique hebdomadaire réel (feuille « Historique_FWD ») ;
 *   - stocker les jalons de façon persistante (propriétés du document).
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
  CLE_JALONS: 'GATES_JALONS',

  /** Nombre maximum de jalons conservés. */
  MAX_JALONS: 40,

  /**
   * true = la page peut être embarquée dans n'importe quel site (Google Sites, iframe tierce).
   * false = protection anti-clickjacking (recommandé si l'appli est ouverte directement).
   */
  AUTORISER_INTEGRATION_EXTERNE: false,

  /**
   * Le rythme se mesure sur TOUS les intervalles observés depuis le premier
   * relevé, pas sur une fenêtre fixe : la saisie est irrégulière (une semaine
   * un lot entier, la suivante rien), et une moyenne glissante mesurerait
   * surtout la date du dernier lot.
   */
};

const ENTETES_HISTORIQUE = [
  'Semaine', 'Date', 'Total', 'Terminés', 'En cours', 'À faire', 'Non renseignés',
  'Par ATA', 'Plans'
];

// =====================================================================
//  POINT D'ENTRÉE WEB
// =====================================================================
function doGet() {
  const page = HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('GATES Analytics')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');

  return CONFIG.AUTORISER_INTEGRATION_EXTERNE
    ? page.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    : page;
}

/** Permet d'inclure Styles.html / Javascript.html depuis Index.html. */
function include(nomFichier) {
  return HtmlService.createHtmlOutputFromFile(nomFichier).getContent();
}

/** Menu ajouté au classeur à l'ouverture. */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('GATES Analytics')
    .addItem('Enregistrer un instantané maintenant', 'enregistrerInstantaneHebdo')
    .addItem('Activer le suivi hebdomadaire automatique', 'installerSuiviHebdomadaire')
    .addItem('Désactiver le suivi automatique', 'desinstallerSuiviHebdomadaire')
    .addSeparator()
    .addItem('Supprimer le dernier relevé', 'supprimerDernierReleve')
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
 * Convertit une cellule affichée en nombre.
 * Gère « 75 % », « 1 234,5 », l'espace insécable et la virgule décimale.
 * Renvoie NaN si la valeur n'est pas numérique.
 */
function valeurNumerique(valeur) {
  if (valeur === null || valeur === undefined) return NaN;
  const texte = valeur
    .toString()
    .replace(/[\s  ]/g, '')
    .replace(/%$/, '')
    .replace(',', '.');
  if (texte === '' || !/^[-+]?\d*\.?\d+$/.test(texte)) return NaN;
  return parseFloat(texte);
}

/**
 * Classe un avancement FWD : 'termine' | 'encours' | 'vide'.
 *
 * Règle numérique d'abord (>= 100 terminé, <= 0 vide), sinon mots-clés.
 * Évite le faux positif de l'ancienne version où « 1000 » contenait « 100 ».
 *
 * ⚠ Cette fonction est volontairement dupliquée à l'identique dans Javascript.html :
 *    le serveur l'utilise pour les instantanés, le client pour les KPI filtrés.
 *    Toute modification doit être reportée des deux côtés.
 */
function classerFWD(valeur) {
  const s = normaliser(valeur);
  if (s === '' || s === '-' || s === 'na' || s === 'n/a' ||
      s.indexOf('non renseigne') !== -1 || s.indexOf('a faire') !== -1) {
    return 'vide';
  }
  const n = valeurNumerique(s);
  if (!isNaN(n)) {
    if (n >= 100) return 'termine';
    if (n <= 0) return 'vide';
    return 'encours';
  }
  if (/(termine|acheve|cloture|clos|fini|valide|done|complete|ok)/.test(s)) return 'termine';
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

// =====================================================================
//  LECTURE DE LA FEUILLE
// =====================================================================

/**
 * Renvoie la feuille de données.
 * L'ancienne version utilisait getActiveSheet() : le tableau de bord lisait
 * alors l'onglet sur lequel l'utilisateur avait cliqué en dernier — y compris
 * « Historique_FWD ». On résout désormais un onglet déterministe.
 */
function getFeuilleDonnees(classeur) {
  if (CONFIG.FEUILLE_DONNEES) {
    const nommee = classeur.getSheetByName(CONFIG.FEUILLE_DONNEES);
    if (!nommee) {
      throw new Error("L'onglet « " + CONFIG.FEUILLE_DONNEES + " » est introuvable.");
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

/**
 * Propage les groupes fusionnés vers la droite.
 * Fait côté serveur une seule fois, au lieu d'être recalculé par le client.
 */
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

/**
 * Index de la colonne « Avancement FWD ».
 * Recherche croisée groupe + colonne, du plus précis au plus permissif.
 */
function trouverIndexFWD(entetes, groupes) {
  const criteres = [
    function (col, grp) { return col.indexOf('avancement') !== -1 && (grp.indexOf('fwd') !== -1 || col.indexOf('fwd') !== -1); },
    function (col, grp) { return col.indexOf('realisation') !== -1 && (grp.indexOf('fwd') !== -1 || col.indexOf('fwd') !== -1); },
    function (col) { return col.indexOf('fwd') !== -1; }
  ];
  for (let c = 0; c < criteres.length; c++) {
    for (let i = 0; i < entetes.length; i++) {
      if (criteres[c](normaliser(entetes[i]), normaliser(groupes[i] || ''))) return i;
    }
  }
  return -1;
}

/** Une ligne est significative si au moins une cellule est renseignée. */
function ligneNonVide(ligne) {
  for (let i = 0; i < ligne.length; i++) {
    if (String(ligne[i]).trim() !== '') return true;
  }
  return false;
}

// =====================================================================
//  API APPELÉE PAR LE CLIENT
// =====================================================================

/**
 * Charge tout ce dont la page a besoin, en un seul aller-retour.
 * Ne provoque aucune écriture : la lecture du tableau de bord ne doit pas
 * modifier le classeur (l'ancienne version écrivait l'historique à chaque ouverture).
 */
function getDonneesPlans() {
  try {
    const classeur = SpreadsheetApp.getActiveSpreadsheet();
    const feuille = getFeuilleDonnees(classeur);
    const donnees = feuille.getDataRange().getDisplayValues();

    if (donnees.length === 0) {
      return paquetVide(feuille.getName(), 'La feuille « ' + feuille.getName() + ' » est vide.');
    }

    const indexEntete = detecterLigneEntete(donnees);
    const entetes = donnees[indexEntete].map(function (e) { return String(e).trim(); });
    const nbColonnes = entetes.length;
    const groupes = propagerGroupes(indexEntete > 0 ? donnees[indexEntete - 1] : [], nbColonnes);
    const lignes = donnees.slice(indexEntete + 1).filter(ligneNonVide);
    const indexFWD = trouverIndexFWD(entetes, groupes);

    return {
      ok: true,
      message: '',
      feuille: feuille.getName(),
      genereLe: new Date().toISOString(),
      groupes: groupes,
      entetes: entetes,
      lignes: lignes,
      indexFWD: indexFWD,
      historique: getHistorique(classeur),
      jalons: getJalons()
    };
  } catch (err) {
    return paquetVide('', err && err.message ? err.message : String(err));
  }
}

function paquetVide(nomFeuille, message) {
  return {
    ok: false,
    message: message,
    feuille: nomFeuille,
    genereLe: new Date().toISOString(),
    groupes: [],
    entetes: [],
    lignes: [],
    indexFWD: -1,
    historique: [],
    jalons: getJalons()
  };
}

// =====================================================================
//  HISTORIQUE
//  L'export ne contient que l'état du jour : on ne sait pas quand un plan est
//  passé à 100 %. L'historique ne peut donc pas être reconstitué, seulement
//  accumulé — un relevé par semaine ISO, écrit à chaque import.
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
      parAta: analyserJson(ligne[7]),
      plans: analyserJson(ligne[8])
    };
  });

  return Object.keys(parSemaine).sort().map(function (s) { return parSemaine[s]; });
}

function analyserJson(valeur) {
  if (!valeur) return null;
  try { return JSON.parse(valeur); } catch (err) { return null; }
}

/** Compte l'état du jour, globalement et par ATA, et relève chaque plan. */
function compterAvancements() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  const feuille = getFeuilleDonnees(classeur);
  const donnees = feuille.getDataRange().getDisplayValues();
  const vide = { total: 0, termine: 0, encours: 0, afaire: 0, vide: 0, parAta: {}, plans: {} };
  if (donnees.length === 0) return vide;

  const indexEntete = detecterLigneEntete(donnees);
  const entetes = donnees[indexEntete];
  const groupes = propagerGroupes(indexEntete > 0 ? donnees[indexEntete - 1] : [], entetes.length);
  const indexFWD = trouverIndexFWD(entetes, groupes);
  const indexRef = entetes.findIndex(function (e) { return normaliser(e).indexOf('reference') !== -1; });
  const indexAta = entetes.findIndex(function (e) {
    const n = normaliser(e);
    return n === 'ata' || n.indexOf('chapitre') !== -1;
  });
  const lignes = donnees.slice(indexEntete + 1).filter(ligneNonVide);

  const compte = { total: lignes.length, termine: 0, encours: 0, afaire: 0, vide: 0, parAta: {}, plans: {} };

  lignes.forEach(function (ligne, n) {
    const brut = indexFWD === -1 ? '' : ligne[indexFWD];
    const etat = classerFWD(brut);
    compte[etat]++;

    const reference = indexRef === -1 ? 'ligne-' + (n + 1) : String(ligne[indexRef]).trim();
    if (reference) compte.plans[reference] = String(brut).trim();

    const ata = indexAta === -1 ? '—' : (String(ligne[indexAta]).trim() || '—');
    if (!compte.parAta[ata]) compte.parAta[ata] = { total: 0, termine: 0 };
    compte.parAta[ata].total++;
    if (etat === 'termine') compte.parAta[ata].termine++;
  });

  return compte;
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
    JSON.stringify(compte.parAta),
    JSON.stringify(compte.plans)
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

  if (indexLigne === -1) {
    feuille.appendRow(ligne);
  } else {
    feuille.getRange(indexLigne, 1, 1, ligne.length).setValues([ligne]);
  }

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

function sauvegarderJalons(liste) {
  PropertiesService.getDocumentProperties()
    .setProperty(CONFIG.CLE_JALONS, JSON.stringify(liste.slice(0, CONFIG.MAX_JALONS)));
  return liste;
}

function ajouterJalon(semaineBrute, texte) {
  const semaine = normaliserSemaine(semaineBrute);
  if (!semaine) {
    throw new Error('Semaine invalide : utilisez le format AAAA-Sxx (ex. 2026-S38).');
  }
  const libelle = String(texte || '').trim().slice(0, 60) || 'Jalon';
  const jalons = getJalons();
  if (jalons.length >= CONFIG.MAX_JALONS) {
    throw new Error('Nombre maximum de jalons atteint (' + CONFIG.MAX_JALONS + ').');
  }
  jalons.push({ id: Utilities.getUuid(), semaine: semaine, texte: libelle });
  jalons.sort(function (a, b) { return a.semaine < b.semaine ? -1 : (a.semaine > b.semaine ? 1 : 0); });
  return sauvegarderJalons(jalons);
}

function supprimerJalon(id) {
  return sauvegarderJalons(getJalons().filter(function (j) { return j.id !== id; }));
}
