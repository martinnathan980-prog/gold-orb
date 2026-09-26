/**
 * ETII Hub — remplir le classeur des documents depuis le Drive partagé
 * --------------------------------------------------------------------
 * Des milliers de documents ne se recopient pas à la main. Ce script
 * parcourt le dossier Drive de chaque pôle (et tous ses sous-dossiers) et
 * ajoute au classeur une ligne par fichier qui n'y figure pas encore :
 * Titre, Référence (lue dans le nom du fichier), Type (le nom du
 * sous-dossier), Mise à jour, Lien. Le site lit ensuite ces lignes comme
 * les autres.
 *
 * Il n'efface ni ne modifie JAMAIS une ligne existante : ce que vous avez
 * complété à la main (Métier, Porteur, Description, Mots-clés…) reste.
 * Un fichier est reconnu par son identifiant Drive dans la colonne Lien.
 *
 * Où le coller : dans le classeur des documents (celui que lit le site),
 * Extensions › Apps Script, un nouveau fichier « index-documents ».
 * Mode d'emploi : docs/ASSISTANT-IA.md, étape 1.3.
 *
 * Des milliers de fichiers : Apps Script arrête un script après 6 minutes.
 * Celui-ci s'interrompt proprement vers 5 minutes, note où il en est, et
 * se relance tout seul une minute plus tard jusqu'à la fin.
 */

/* ======================================================================
   À RENSEIGNER — l'identifiant du dossier Drive de chaque pôle
   (dans son adresse, la suite qui suit « /folders/ »). Un pôle laissé
   vide est sauté. Le nom de l'onglet du classeur est la clé.
   ====================================================================== */
var DOSSIERS_POLES = {
  ETIIA: '',
  ETIIE: '',
  ETIII: ''
};

/* ----------------------------------------------------------------------
   Rien à modifier en dessous
   ---------------------------------------------------------------------- */

var COLONNES_INDEX = ['Titre', 'Référence', 'Type', 'Métier', 'Porteur', 'Périmètre',
  'Mise à jour', 'Lien', 'Description', 'Mots-clés', 'Remplacé par'];
var DUREE_MAX_MS = 5 * 60 * 1000;
var PROPRIETE_REPRISE = 'INDEX_REPRISE';
var FONCTION_REPRISE = 'reprendreIndexation';
/* Une référence en tête de nom : lettres, chiffres, tirets, au moins un
   tiret (ETII-TEC-001, ETIIE-NT-0042…), suivie de « _ », d'une espace ou
   de la fin du nom. */
var MOTIF_REFERENCE = /^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:[_ ]|$)/;
var MOTIF_ID_DRIVE = /[-\w]{25,}/;

/** À lancer à la main (ou chaque nuit, voir planifierChaqueNuit). */
function indexerDocuments() {
  supprimerReprises_();
  var proprietes = PropertiesService.getScriptProperties();
  var reprise = null;
  try { reprise = JSON.parse(proprietes.getProperty(PROPRIETE_REPRISE) || 'null'); } catch (e) { reprise = null; }
  var file = reprise && reprise.file ? reprise.file : fileInitiale_();
  var bilan = reprise && reprise.bilan ? reprise.bilan : { ajoutes: 0, deja: 0 };
  if (!file.length) {
    Logger.log('Aucun dossier renseigné dans DOSSIERS_POLES : rien à faire.');
    return bilan;
  }

  var debut = Date.now();
  var onglets = {};
  var interrompu = false;

  while (file.length) {
    var tache = file[0];
    var onglet = onglets[tache.pole] || (onglets[tache.pole] = ouvrirOnglet_(tache.pole));
    var dossier = DriveApp.getFolderById(tache.dossier);

    if (!tache.sousDossiers) {
      var sous = dossier.getFolders();
      while (sous.hasNext()) {
        var s = sous.next();
        file.push({ pole: tache.pole, dossier: s.getId(), type: tache.type || s.getName() });
      }
      tache.sousDossiers = true;
    }

    var fichiers = tache.jeton ? DriveApp.continueFileIterator(tache.jeton) : dossier.getFiles();
    while (fichiers.hasNext()) {
      if (Date.now() - debut > DUREE_MAX_MS) {
        tache.jeton = fichiers.getContinuationToken();
        interrompu = true;
        break;
      }
      var f = fichiers.next();
      if (onglet.connus[f.getId()]) { bilan.deja += 1; continue; }
      onglet.connus[f.getId()] = true;
      onglet.nouvelles.push(ligneDe_(onglet.position, onglet.largeur, f, tache.type));
      bilan.ajoutes += 1;
    }
    if (interrompu) break;
    file.shift();
  }

  Object.keys(onglets).forEach(function (pole) { ecrire_(onglets[pole]); });

  if (interrompu) {
    proprietes.setProperty(PROPRIETE_REPRISE, JSON.stringify({ file: file, bilan: bilan }));
    ScriptApp.newTrigger(FONCTION_REPRISE).timeBased().after(60 * 1000).create();
    Logger.log('Pause après 5 minutes : ' + bilan.ajoutes + ' fichiers ajoutés jusqu’ici. Reprise automatique dans une minute.');
  } else {
    proprietes.deleteProperty(PROPRIETE_REPRISE);
    Logger.log('Terminé : ' + bilan.ajoutes + ' fichiers ajoutés, ' + bilan.deja + ' déjà présents.');
  }
  return bilan;
}

/** Appelée par le déclencheur de reprise. */
function reprendreIndexation() {
  return indexerDocuments();
}

/** Une fois : relance l'indexation chaque nuit vers 6 h, pour les nouveaux fichiers. */
function planifierChaqueNuit() {
  ScriptApp.getProjectTriggers().forEach(function (d) {
    if (d.getHandlerFunction() === 'indexerDocuments') ScriptApp.deleteTrigger(d);
  });
  ScriptApp.newTrigger('indexerDocuments').timeBased().everyDays(1).atHour(6).create();
  Logger.log('Indexation programmée chaque nuit vers 6 h.');
}

/* ======================================================================
   Outils
   ====================================================================== */

function fileInitiale_() {
  return Object.keys(DOSSIERS_POLES)
    .filter(function (pole) { return String(DOSSIERS_POLES[pole] || '').trim(); })
    .map(function (pole) { return { pole: pole, dossier: String(DOSSIERS_POLES[pole]).trim(), type: '' }; });
}

function supprimerReprises_() {
  ScriptApp.getProjectTriggers().forEach(function (d) {
    if (d.getHandlerFunction() === FONCTION_REPRISE) ScriptApp.deleteTrigger(d);
  });
}

function cleIndex_(t) {
  return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]/g, '');
}

/**
 * L'onglet du pôle, son en-tête (complété des colonnes manquantes) et les
 * fichiers qu'il connaît déjà, par identifiant Drive lu dans « Lien ».
 */
function ouvrirOnglet_(pole) {
  var classeur = SpreadsheetApp.getActiveSpreadsheet();
  var feuille = classeur.getSheetByName(pole) || classeur.insertSheet(pole);
  var largeur = feuille.getLastColumn();
  var entete = largeur ? feuille.getRange(1, 1, 1, largeur).getValues()[0] : [];
  if (!entete.some(function (c) { return String(c).trim(); })) entete = [];
  var cles = entete.map(cleIndex_);
  ['Titre', 'Référence', 'Type', 'Mise à jour', 'Lien'].forEach(function (nom) {
    if (cles.indexOf(cleIndex_(nom)) === -1) { entete.push(nom); cles.push(cleIndex_(nom)); }
  });
  if (!largeur) {
    entete = COLONNES_INDEX.slice();
    cles = entete.map(cleIndex_);
  }
  feuille.getRange(1, 1, 1, entete.length).setValues([entete]);
  feuille.setFrozenRows(1);

  var position = {};
  cles.forEach(function (c, i) { if (position[c] === undefined) position[c] = i; });
  var connus = {};
  var hauteur = feuille.getLastRow();
  if (hauteur > 1) {
    feuille.getRange(2, position.lien + 1, hauteur - 1, 1).getValues().forEach(function (l) {
      var id = MOTIF_ID_DRIVE.exec(String(l[0] || ''));
      if (id) connus[id[0]] = true;
    });
  }
  return { feuille: feuille, position: position, largeur: entete.length, connus: connus, nouvelles: [] };
}

function ligneDe_(position, largeur, fichier, type) {
  var ligne = [];
  for (var i = 0; i < largeur; i++) ligne.push('');
  var nom = String(fichier.getName());
  var titre = nom.replace(/\.[A-Za-z0-9]{2,5}$/, '');
  var ref = MOTIF_REFERENCE.exec(titre);
  ligne[position.titre] = titre;
  if (ref) ligne[position.reference] = ref[1];
  if (type) ligne[position.type] = type;
  ligne[position.miseajour] = fichier.getLastUpdated();
  ligne[position.lien] = fichier.getUrl();
  return ligne;
}

function ecrire_(onglet) {
  if (!onglet.nouvelles.length) return;
  var depart = Math.max(onglet.feuille.getLastRow(), 1) + 1;
  onglet.feuille.getRange(depart, 1, onglet.nouvelles.length, onglet.largeur).setValues(onglet.nouvelles);
  onglet.nouvelles = [];
}
