/**
 * ETII Hub — le site, servi par Google Apps Script
 * ------------------------------------------------
 * Ce fichier est TOUT le code serveur du site. À coller dans l'éditeur
 * Apps Script d'une feuille Google (Extensions › Apps Script), à la place
 * du contenu de « Code.gs ». Le guide pas à pas est dans
 * docs/INSTALLER-SUR-GOOGLE.txt.
 *
 * Ce qu'il fait :
 *   1. doGet — sert le site : le fichier etii-hub.html (déposé sur Google
 *      Drive) est lu et renvoyé tel quel. Le site entier tient dans ce
 *      fichier : pages, styles, données, photos.
 *   2. La base des modifications — tout ce qu'on ajoute, modifie ou
 *      supprime dans le site (bouton « Modifier ») est rangé dans l'onglet
 *      « modifications » de cette feuille. Les lecteurs ne voient jamais la
 *      feuille : le site la lit et l'écrit pour eux.
 *   3. Les profils — le serveur sait qui est connecté (son compte Google de
 *      l'entreprise). Seules les adresses de l'onglet « Éditeurs », et le
 *      propriétaire du script, peuvent modifier ; les autres lisent.
 *   4. Le journal — chaque modification laisse une ligne dans l'onglet
 *      « journal » : quoi, qui, quand.
 *
 * Déploiement : Déployer › Nouveau déploiement › Application web
 *   - Exécuter en tant que : Moi
 *   - Qui a accès : tous les utilisateurs de votre organisation
 * « Exécuter en tant que Moi » : la feuille reste privée (seul le script y
 * écrit) et l'adresse de la personne connectée est connue, puisqu'elle est
 * du même domaine que vous.
 */

/* ======================================================================
   À RENSEIGNER — une seule ligne
   L'identifiant du fichier etii-hub.html déposé sur Google Drive : dans
   son lien de partage, la suite de lettres et de chiffres entre « /d/ »
   et « /view ».
   ====================================================================== */
var ID_FICHIER_SITE = 'COLLEZ_ICI_L_IDENTIFIANT_DU_FICHIER';

/* ----------------------------------------------------------------------
   Rien à modifier en dessous
   ---------------------------------------------------------------------- */

var ONGLET_MODIFICATIONS = 'modifications';
var ONGLET_EDITEURS = 'Éditeurs';
var ONGLET_JOURNAL = 'journal';
var JEUX = ['communications', 'flotte', 'organigramme', 'faq', 'documents', 'reunions'];
/* Une cellule de feuille Google tient 50 000 caractères : un élément plus
   long (une communication riche, une fiche de porteur) est découpé sur
   plusieurs colonnes. Chaque morceau commence par « ~ », retiré à la
   lecture : ainsi la feuille ne prend jamais un morceau pour une formule,
   un nombre ou une date. */
var TRANCHE = 40000;
var MARQUE = '~';
var EN_TETE = ['jeu', 'cle', 'type', 'id', 'op', 'le', 'par', 'donnees'];

/* ======================================================================
   1. Servir le site
   ====================================================================== */

function doGet() {
  var html = DriveApp.getFileById(ID_FICHIER_SITE).getBlob().getDataAsString('UTF-8');
  return HtmlService.createHtmlOutput(html)
    .setTitle('ETII Hub')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    // Permet d'intégrer le site dans une page Google Sites.
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/* ======================================================================
   2. Ce que le site appelle (google.script.run)
   ====================================================================== */

/**
 * Au chargement de chaque page : qui est connecté, peut-il modifier, et
 * toutes les modifications, jeu par jeu.
 */
function etiiDemarrer() {
  var email = emailConnecte_();
  return {
    email: email,
    peutModifier: peutModifier_(email),
    modifications: lireModifications_()
  };
}

/**
 * Enregistre un élément ajouté, modifié ou supprimé.
 * @param {string} jeu    communications, flotte, organigramme, faq, documents, reunions
 * @param {Object} modif  { type, id, op: 'maj'|'suppr', donnees }
 * @return {{le: string, par: string}}
 */
function etiiPoser(jeu, modif) {
  var email = emailConnecte_();
  if (!peutModifier_(email)) throw new Error('NON_AUTORISE');
  verifierJeu_(jeu);
  if (!modif || typeof modif !== 'object') throw new Error('Modification illisible.');
  var type = String(modif.type || '').trim();
  var id = String(modif.id || '').trim();
  var op = modif.op === 'suppr' ? 'suppr' : (modif.op === 'maj' ? 'maj' : '');
  if (!type || !id || !op) throw new Error('Modification illisible.');
  var donnees = op === 'maj' ? JSON.stringify(modif.donnees || {}) : '';
  var le = new Date().toISOString();

  var verrou = LockService.getScriptLock();
  verrou.waitLock(20000);
  try {
    var feuille = onglet_(ONGLET_MODIFICATIONS, EN_TETE);
    var cle = type + '~' + id;
    var ligne = trouverLigne_(feuille, jeu, cle);
    var valeurs = [jeu, cle, type, id, op, le, email].concat(decouper_(donnees));
    if (ligne) {
      // L'ancienne version peut avoir occupé plus de colonnes : on les vide.
      var largeur = Math.max(feuille.getLastColumn(), valeurs.length);
      feuille.getRange(ligne, 1, 1, largeur).clearContent();
      feuille.getRange(ligne, 1, 1, valeurs.length).setValues([valeurs]);
    } else {
      feuille.appendRow(valeurs);
    }
    onglet_(ONGLET_JOURNAL, ['le', 'par', 'jeu', 'type', 'id', 'op', 'titre'])
      .appendRow([le, email, jeu, type, id, op, titreDe_(modif.donnees)]);
  } finally {
    verrou.releaseLock();
  }
  return { le: le, par: email };
}

/**
 * Annule une modification : l'élément redevient celui du fichier d'origine.
 */
function etiiRetirer(jeu, type, id) {
  var email = emailConnecte_();
  if (!peutModifier_(email)) throw new Error('NON_AUTORISE');
  verifierJeu_(jeu);
  var cle = String(type || '').trim() + '~' + String(id || '').trim();
  var verrou = LockService.getScriptLock();
  verrou.waitLock(20000);
  try {
    var feuille = onglet_(ONGLET_MODIFICATIONS, EN_TETE);
    var ligne = trouverLigne_(feuille, jeu, cle);
    if (ligne) feuille.deleteRow(ligne);
    onglet_(ONGLET_JOURNAL, ['le', 'par', 'jeu', 'type', 'id', 'op', 'titre'])
      .appendRow([new Date().toISOString(), email, jeu, type, id, 'annulation', '']);
  } finally {
    verrou.releaseLock();
  }
  return { ok: true };
}

/* ======================================================================
   3. Mise en place — à exécuter UNE fois depuis l'éditeur (▶ Exécuter)
   ====================================================================== */

/**
 * Crée les onglets, s'inscrit comme premier éditeur et vérifie que le
 * fichier du site est lisible. Le journal d'exécution dit ce qui a été fait.
 */
function installer() {
  PropertiesService.getScriptProperties().setProperty('ID_CLASSEUR', SpreadsheetApp.getActiveSpreadsheet().getId());
  onglet_(ONGLET_MODIFICATIONS, EN_TETE);
  onglet_(ONGLET_JOURNAL, ['le', 'par', 'jeu', 'type', 'id', 'op', 'titre']);
  var editeurs = onglet_(ONGLET_EDITEURS, ['adresse', 'nom (facultatif)']);
  var moi = Session.getEffectiveUser().getEmail();
  if (moi && listeEditeurs_().indexOf(moi.toLowerCase()) === -1) editeurs.appendRow([moi, 'propriétaire']);
  var fichier = DriveApp.getFileById(ID_FICHIER_SITE);
  Logger.log('Onglets prêts. Premier éditeur : ' + moi);
  Logger.log('Fichier du site trouvé : ' + fichier.getName() + ' (' + Math.round(fichier.getSize() / 1024) + ' Ko).');
}

/* ======================================================================
   4. Outils internes (le « _ » final les rend invisibles depuis le site)
   ====================================================================== */

function emailConnecte_() {
  var email = '';
  try { email = Session.getActiveUser().getEmail() || ''; } catch (e) { email = ''; }
  return String(email).trim().toLowerCase();
}

function peutModifier_(email) {
  if (!email) return false;
  var proprietaire = String(Session.getEffectiveUser().getEmail() || '').toLowerCase();
  if (email === proprietaire) return true;
  return listeEditeurs_().indexOf(email) !== -1;
}

function listeEditeurs_() {
  var feuille = classeur_().getSheetByName(ONGLET_EDITEURS);
  if (!feuille || feuille.getLastRow() < 2) return [];
  return feuille.getRange(2, 1, feuille.getLastRow() - 1, 1).getValues()
    .map(function (l) { return String(l[0] || '').trim().toLowerCase(); })
    .filter(function (a) { return a.indexOf('@') > 0; });
}

function lireModifications_() {
  var resultat = {};
  JEUX.forEach(function (j) { resultat[j] = []; });
  var feuille = classeur_().getSheetByName(ONGLET_MODIFICATIONS);
  if (!feuille || feuille.getLastRow() < 2) return resultat;
  var lignes = feuille.getRange(2, 1, feuille.getLastRow() - 1, feuille.getLastColumn()).getValues();
  lignes.forEach(function (l) {
    var jeu = String(l[0] || '');
    if (!resultat[jeu]) return;
    var op = String(l[4] || '');
    var donnees = null;
    if (op === 'maj') {
      var json = l.slice(7).map(function (c) {
        var t = String(c === null || c === undefined ? '' : c);
        return t.charAt(0) === MARQUE ? t.substring(1) : t;
      }).join('');
      try { donnees = JSON.parse(json); } catch (e) { return; }
    }
    resultat[jeu].push({ type: String(l[2]), id: String(l[3]), op: op, donnees: donnees, le: String(l[5] || ''), par: String(l[6] || '') });
  });
  return resultat;
}

function trouverLigne_(feuille, jeu, cle) {
  var n = feuille.getLastRow();
  if (n < 2) return 0;
  var valeurs = feuille.getRange(2, 1, n - 1, 2).getValues();
  for (var i = 0; i < valeurs.length; i++) {
    if (String(valeurs[i][0]) === jeu && String(valeurs[i][1]) === cle) return i + 2;
  }
  return 0;
}

function decouper_(texte) {
  if (!texte) return [''];
  var morceaux = [];
  for (var i = 0; i < texte.length; i += TRANCHE) morceaux.push(MARQUE + texte.substring(i, i + TRANCHE));
  return morceaux;
}

function titreDe_(donnees) {
  if (!donnees || typeof donnees !== 'object') return '';
  return String(donnees.titre || donnees.nom || donnees.question || donnees.code || donnees.texte || '').slice(0, 120);
}

function verifierJeu_(jeu) {
  if (JEUX.indexOf(jeu) === -1) throw new Error('Jeu de données inconnu : ' + jeu);
}

/* La feuille où vit ce script. Son identifiant est retenu par
   installer() : l'application web la retrouve ainsi à coup sûr. */
function classeur_() {
  var id = PropertiesService.getScriptProperties().getProperty('ID_CLASSEUR');
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
}

function onglet_(nom, entete) {
  var classeur = classeur_();
  var feuille = classeur.getSheetByName(nom);
  if (!feuille) {
    feuille = classeur.insertSheet(nom);
    feuille.getRange(1, 1, 1, entete.length).setValues([entete]).setFontWeight('bold');
    feuille.setFrozenRows(1);
    // Tout en texte brut : un identifiant « 007 » reste « 007 », une date
    // reste la chaîne écrite par le site.
    if (nom === ONGLET_MODIFICATIONS) feuille.getRange(1, 1, feuille.getMaxRows(), feuille.getMaxColumns()).setNumberFormat('@');
  }
  return feuille;
}
