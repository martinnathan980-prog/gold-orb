/**
 * ETII Hub — synchronisation nocturne du suivi OTQ / OTD
 * ------------------------------------------------------
 * À coller dans l'éditeur Apps Script du Google Sheet DE PUBLICATION (celui
 * que le site lit). Chaque nuit, le script va lire la feuille SOURCE (celle
 * à laquelle on vous a donné accès), en recopie les colonnes utiles dans
 * l'onglet « publication », et le site les lit au chargement.
 *
 * Mise en place, une fois :
 *   1. Remplacer ID_FEUILLE_SOURCE, NOM_ONGLET_SOURCE et PLAGE_SOURCE.
 *   2. Exécuter une fois `synchroniser` à la main (autoriser l'accès).
 *   3. Exécuter une fois `installerDeclencheur` : il crée le déclencheur
 *      quotidien entre minuit et 1 h (fuseau du script — Fichier →
 *      Paramètres du projet → Fuseau horaire).
 *   4. Fichier → Partager → Publier sur le web → onglet « publication »,
 *      format CSV → coller l'URL dans SOURCE.url de assets/js/otq.js.
 *
 * Format produit (en-tête en ligne 1) : mois,otq,otd,cible_otq,cible_otd
 * Le mois est écrit AAAA-MM. Les cases vides restent vides : le site y
 * laisse un trou, jamais un zéro.
 */

var ID_FEUILLE_SOURCE = 'ID-DE-LA-FEUILLE-SOURCE';   // dans l'URL du Sheet source : /d/<ID>/edit
var NOM_ONGLET_SOURCE = 'Indicateurs';               // onglet de la feuille source
var PLAGE_SOURCE = 'A2:E';                           // mois | otq | otd | cible otq | cible otd
var NOM_ONGLET_PUBLICATION = 'publication';

function synchroniser() {
  var source = SpreadsheetApp.openById(ID_FEUILLE_SOURCE).getSheetByName(NOM_ONGLET_SOURCE);
  if (!source) throw new Error('Onglet source introuvable : ' + NOM_ONGLET_SOURCE);

  var lignes = source.getRange(PLAGE_SOURCE).getValues()
    .filter(function (l) { return l[0] !== '' && l[0] !== null; })
    .map(function (l) {
      return [formaterMois(l[0]), nombreOuVide(l[1]), nombreOuVide(l[2]), nombreOuVide(l[3]), nombreOuVide(l[4])];
    })
    .filter(function (l) { return /^\d{4}-\d{2}$/.test(l[0]); });

  var cible = SpreadsheetApp.getActiveSpreadsheet();
  var feuille = cible.getSheetByName(NOM_ONGLET_PUBLICATION) || cible.insertSheet(NOM_ONGLET_PUBLICATION);
  feuille.clearContents();
  feuille.getRange(1, 1, 1, 5).setValues([['mois', 'otq', 'otd', 'cible_otq', 'cible_otd']]);
  if (lignes.length) feuille.getRange(2, 1, lignes.length, 5).setValues(lignes);

  // Trace de la dernière synchronisation, lisible dans la feuille.
  feuille.getRange(1, 7).setValue('synchronise_le');
  feuille.getRange(2, 7).setValue(new Date());
}

function installerDeclencheur() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'synchroniser') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('synchroniser').timeBased().everyDays(1).atHour(0).create();
}

/* Une date Sheets, un texte « 2026-01 », « 01/2026 » ou « janvier 2026 » : tout devient AAAA-MM. */
function formaterMois(brut) {
  if (brut instanceof Date) return Utilities.formatDate(brut, Session.getScriptTimeZone(), 'yyyy-MM');
  var t = String(brut).trim();
  var m = t.match(/^(\d{4})-(\d{2})/);
  if (m) return m[1] + '-' + m[2];
  m = t.match(/^(\d{2})\/(\d{4})$/);
  if (m) return m[2] + '-' + m[1];
  var mois = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin', 'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre'];
  var sansAccent = t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  for (var i = 0; i < mois.length; i += 1) {
    var r = new RegExp('^' + mois[i] + '\\s+(\\d{4})$');
    var mm = sansAccent.match(r);
    if (mm) return mm[1] + '-' + ('0' + (i + 1)).slice(-2);
  }
  return t;
}

function nombreOuVide(brut) {
  if (brut === '' || brut === null || brut === undefined) return '';
  var n = Number(String(brut).replace(',', '.').replace('%', ''));
  return isFinite(n) ? n : '';
}

/* Variante : servir le CSV par une web app (Déployer → Application web,
   accès « Toute personne disposant du lien »). L'URL /exec obtenue va
   alors dans SOURCE.url. Utile si la publication sur le web est interdite
   par la politique du domaine. */
function doGet() {
  var feuille = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NOM_ONGLET_PUBLICATION);
  var valeurs = feuille ? feuille.getRange(1, 1, feuille.getLastRow(), 5).getValues() : [];
  var csv = valeurs.map(function (l) { return l.join(','); }).join('\n');
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.CSV);
}
