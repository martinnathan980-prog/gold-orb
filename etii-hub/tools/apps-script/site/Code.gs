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

/* ======================================================================
   FACULTATIF — votre liste de documents existante
   Si vos documents sont déjà tenus dans une feuille Google, le site peut
   les lire là, à chaque ouverture, à la place des documents d'exemple.
   Collez l'identifiant de cette feuille (dans son adresse, entre « /d/ »
   et « /edit ») et, si les documents ne sont pas dans le premier onglet,
   le nom de l'onglet. Laissez vide pour garder les documents du fichier.
   Les colonnes sont reconnues par leur titre (Titre, Référence, Type,
   Métier, Porteur, Périmètre, Pôle, Mise à jour, Lien, Description,
   Mots-clés, Remplacé par) : voir le guide.
   ====================================================================== */
var DOCUMENTS_ID_FEUILLE = '';
var DOCUMENTS_ONGLET = '';

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
  var reponse = {
    email: email,
    peutModifier: peutModifier_(email),
    modifications: lireModifications_(),
    bases: {}
  };
  /* La liste des documents tenue ailleurs, si elle est branchée. Une
     feuille illisible ne bloque pas le site : il garde ses documents. */
  if (DOCUMENTS_ID_FEUILLE) {
    try { reponse.bases.documents = lireDocumentsExternes_(); }
    catch (e) { reponse.basesErreur = 'Liste des documents illisible : ' + e.message; }
  }
  return reponse;
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

/* Les titres de colonne reconnus pour chaque champ d'un document, écrits
   sans accents, sans espaces ni ponctuation, en minuscules. */
var COLONNES_DOCUMENTS = {
  id: ['id', 'identifiantunique'],
  titre: ['titre', 'title', 'intitule', 'nomdudocument', 'document', 'nom', 'libelle'],
  reference: ['reference', 'ref', 'numero', 'no', 'code', 'identifiant'],
  type: ['type', 'typedocument', 'typededocument', 'nature', 'categorie'],
  metier: ['metier', 'metiers', 'domaine', 'discipline'],
  porteur: ['porteur', 'responsable', 'auteur', 'proprietaire', 'redacteur'],
  perimetre: ['perimetre', 'programme', 'appareil', 'produit', 'helicoptere'],
  pole: ['pole', 'poles', 'equipe'],
  maj: ['maj', 'miseajour', 'datemaj', 'datedemiseajour', 'derniereversion', 'modifiele', 'date'],
  lien: ['lien', 'url', 'link', 'adresse', 'chemin'],
  description: ['description', 'resume', 'objet', 'commentaire'],
  motsCles: ['motscles', 'motcle', 'tags', 'keywords'],
  remplacePar: ['remplacepar', 'supersededby']
};
var CHAMPS_LISTES = ['metier', 'pole', 'motsCles'];

function cleColonne_(t) {
  return String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
}

/**
 * Lit la feuille des documents : une ligne par document, les colonnes
 * reconnues par leur titre (ligne 1). Les autres colonnes sont ignorées.
 */
function lireDocumentsExternes_() {
  var classeur = SpreadsheetApp.openById(DOCUMENTS_ID_FEUILLE);
  var feuille = DOCUMENTS_ONGLET ? classeur.getSheetByName(DOCUMENTS_ONGLET) : classeur.getSheets()[0];
  if (!feuille) throw new Error('onglet « ' + DOCUMENTS_ONGLET + ' » introuvable');
  if (feuille.getLastRow() < 2) return [];
  var valeurs = feuille.getRange(1, 1, feuille.getLastRow(), feuille.getLastColumn()).getValues();
  var entetes = valeurs[0].map(cleColonne_);
  var position = {};
  Object.keys(COLONNES_DOCUMENTS).forEach(function (champ) {
    var noms = COLONNES_DOCUMENTS[champ];
    for (var i = 0; i < noms.length; i++) {
      var j = entetes.indexOf(noms[i]);
      if (j !== -1) { position[champ] = j; return; }
    }
  });
  if (position.titre === undefined) throw new Error('aucune colonne « Titre »');
  var fuseau = Session.getScriptTimeZone ? Session.getScriptTimeZone() : 'Europe/Paris';
  var vus = {};
  var documents = [];
  for (var r = 1; r < valeurs.length; r++) {
    var ligne = valeurs[r];
    var doc = {};
    Object.keys(position).forEach(function (champ) {
      var v = ligne[position[champ]];
      if (Object.prototype.toString.call(v) === '[object Date]') v = Utilities.formatDate(v, fuseau, 'yyyy-MM-dd');
      v = String(v === null || v === undefined ? '' : v).trim();
      if (champ === 'maj') {
        var fr = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);
        if (fr) v = fr[3] + '-' + ('0' + fr[2]).slice(-2) + '-' + ('0' + fr[1]).slice(-2);
      }
      if (CHAMPS_LISTES.indexOf(champ) !== -1) {
        doc[champ] = v ? v.split(/\s*[,;\n]\s*/).filter(function (x) { return x; }) : [];
      } else if (v) {
        doc[champ] = v;
      }
    });
    if (!doc.titre) continue;
    /* L'identifiant : la colonne « id », sinon la référence, sinon la
       ligne. C'est lui qui relie une modification faite dans le site. */
    var id = doc.id || doc.reference || ('ligne-' + (r + 1));
    while (vus[id]) id = id + '-' + (r + 1);
    vus[id] = true;
    doc.id = id;
    documents.push(doc);
  }
  return documents;
}

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
