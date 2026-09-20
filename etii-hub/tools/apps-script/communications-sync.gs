/**
 * ETII Hub — communications : recopie nocturne et service du CSV
 * ---------------------------------------------------------------
 * À coller dans l'éditeur Apps Script du Google Sheet DE PUBLICATION (celui
 * que le site lit). Deux usages, indépendants :
 *
 *   A. `doGet` sert l'onglet « communications » en CSV : à déployer en
 *      « Application web » quand « Publier sur le web » est interdit.
 *      L'URL /exec se colle dans SOURCE.url de assets/js/communications.js.
 *
 *   B. `synchroniser` recopie chaque nuit un onglet SOURCE (par exemple
 *      les réponses d'un Google Form) vers l'onglet « communications »,
 *      en renommant les colonnes et en normalisant les dates. Inutile si
 *      le chef écrit directement dans l'onglet « communications ».
 *
 * Mise en place de B, une fois :
 *   1. Remplacer NOM_ONGLET_SOURCE et, si besoin, ID_FEUILLE_SOURCE (vide :
 *      même classeur) et CORRESPONDANCE (en-tête source → colonne du site).
 *   2. Exécuter une fois `synchroniser` à la main (autoriser l'accès).
 *   3. Exécuter une fois `installerDeclencheur` : déclencheur quotidien
 *      entre minuit et 1 h (fuseau : Paramètres du projet).
 *
 * Colonnes attendues par le site (en-tête en ligne 1) :
 *   type,id,date,pole,categorie,statut,titre,resume,corps,image,imageAlt,
 *   imageLegende,chiffres,serie,auteur,fonction
 */

var ID_FEUILLE_SOURCE = '';                      // vide : un onglet de ce classeur
var NOM_ONGLET_SOURCE = 'Réponses au formulaire 1';
var NOM_ONGLET_PUBLICATION = 'communications';

var COLONNES = ['type', 'id', 'date', 'pole', 'categorie', 'statut', 'titre', 'resume',
  'corps', 'image', 'imageAlt', 'imageLegende', 'chiffres', 'serie', 'auteur', 'fonction'];

/* En-tête de l'onglet source (tel qu'un Google Form le nomme) → colonne du
   site. Les en-têtes sont comparés sans casse ni accents. */
var CORRESPONDANCE = {
  'horodateur': '',                 // ignoré
  'type de communication': 'type',
  'identifiant': 'id',
  'date': 'date',
  'pole': 'pole',
  'categorie': 'categorie',
  'statut': 'statut',
  'titre': 'titre',
  'resume': 'resume',
  'texte': 'corps',
  'corps': 'corps',
  'image': 'image',
  'description de l\'image': 'imageAlt',
  'legende': 'imageLegende',
  'chiffres cles': 'chiffres',
  'chiffres': 'chiffres',
  'serie': 'serie',
  'courbe': 'serie',
  'auteur': 'auteur',
  'fonction': 'fonction'
};

function normaliser(t) {
  return String(t == null ? '' : t).trim().toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function synchroniser() {
  var classeur = ID_FEUILLE_SOURCE ? SpreadsheetApp.openById(ID_FEUILLE_SOURCE) : SpreadsheetApp.getActiveSpreadsheet();
  var source = classeur.getSheetByName(NOM_ONGLET_SOURCE);
  if (!source) throw new Error('Onglet source introuvable : ' + NOM_ONGLET_SOURCE);

  var valeurs = source.getDataRange().getValues();
  if (valeurs.length < 2) return;
  var entete = valeurs[0].map(function (h) {
    var cle = normaliser(h);
    if (CORRESPONDANCE.hasOwnProperty(cle)) return CORRESPONDANCE[cle];
    return COLONNES.indexOf(cle) === -1 ? '' : cle;
  });

  var lignes = valeurs.slice(1)
    .filter(function (l) { return l.some(function (v) { return v !== '' && v !== null; }); })
    .map(function (l) {
      var objet = {};
      entete.forEach(function (colonne, i) { if (colonne) objet[colonne] = l[i]; });
      return COLONNES.map(function (c) {
        var v = objet[c];
        if (c === 'date') return formaterDate(v);
        if (c === 'type') return normaliser(v) || 'annonce';
        if (c === 'pole') return String(v == null ? '' : v).trim().toUpperCase();
        if (c === 'statut') return normaliser(v);
        return v == null ? '' : String(v);
      });
    })
    .filter(function (l) { return l[6] !== '' && (l[0] === 'alerte' || l[2] !== ''); }); // titre, et date sauf alerte

  var cible = SpreadsheetApp.getActiveSpreadsheet();
  var feuille = cible.getSheetByName(NOM_ONGLET_PUBLICATION) || cible.insertSheet(NOM_ONGLET_PUBLICATION);
  feuille.clearContents();
  feuille.getRange(1, 1, 1, COLONNES.length).setValues([COLONNES]);
  if (lignes.length) feuille.getRange(2, 1, lignes.length, COLONNES.length).setValues(lignes);

  // Trace de la dernière synchronisation, lisible dans la feuille.
  feuille.getRange(1, COLONNES.length + 2).setValue('synchronise_le');
  feuille.getRange(2, COLONNES.length + 2).setValue(new Date());
}

function installerDeclencheur() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'synchroniser') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('synchroniser').timeBased().everyDays(1).atHour(0).create();
}

/* Une date Sheets, « 2026-09-12 » ou « 12/09/2026 » : tout devient AAAA-MM-JJ. */
function formaterDate(brut) {
  if (brut instanceof Date) return Utilities.formatDate(brut, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  var t = String(brut == null ? '' : brut).trim();
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t);
  if (m) return m[1] + '-' + m[2] + '-' + m[3];
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(t);
  if (m) return m[3] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[1]).slice(-2);
  return '';
}

/* Option B : l'onglet « communications » servi en CSV (RFC 4180). */
function doGet() {
  var feuille = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NOM_ONGLET_PUBLICATION);
  if (!feuille) return ContentService.createTextOutput('').setMimeType(ContentService.MimeType.CSV);
  var valeurs = feuille.getDataRange().getValues();
  var csv = valeurs.map(function (ligne) {
    return ligne.map(function (v) {
      var t = v instanceof Date ? Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd') : String(v == null ? '' : v);
      return /[",\n\r]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
    }).join(',');
  }).join('\n');
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.CSV);
}
