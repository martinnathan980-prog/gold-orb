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
 *      fichier : pages, styles, données, photos. L'adresse /exec du
 *      déploiement EST le site : aucun Google Sites n'est nécessaire.
 *   2. La base des modifications — tout ce qu'on ajoute, modifie ou
 *      supprime dans le site (bouton « Modifier ») est rangé dans l'onglet
 *      « modifications » de cette feuille. Les lecteurs ne voient jamais la
 *      feuille : le site la lit et l'écrit pour eux.
 *   3. Les profils — le serveur sait qui est connecté (son compte Google de
 *      l'entreprise). Seules les adresses de l'onglet « Éditeurs », et le
 *      propriétaire du script, peuvent modifier ; les autres lisent.
 *   4. Le journal — chaque modification laisse une ligne lisible, la plus
 *      récente en haut : dans « Journal complet », et dans l'onglet de sa
 *      rubrique (« Journal · Communication center », « Journal · À venir »,
 *      « Journal · Porteurs »…). Date, qui, pôle, action, élément, et ce
 *      qui a changé. Le site l'affiche aussi à ses éditeurs (Historique).
 *   5. Les documents — la seule source extérieure : votre classeur de
 *      documents, un onglet par pôle (ETIIA, ETIIE, ETIII), lu à chaque
 *      ouverture.
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
   VOS DOCUMENTS — le classeur qui les liste, un onglet par pôle
   Collez l'identifiant du classeur (dans son adresse, entre « /d/ » et
   « /edit »). Le site lit les trois onglets ci-dessous à chaque
   ouverture ; le nom de l'onglet donne le pôle des documents qu'il liste.
   Renommez les onglets ici s'ils s'appellent autrement chez vous (le code
   du pôle doit figurer dans le nom : « Documents ETIIA » convient).
   Laissez l'identifiant vide pour garder les documents d'exemple.
   Les colonnes sont reconnues par leur titre (Titre, Référence, Type,
   Métier, Porteur, Périmètre, Mise à jour, Lien, Description, Mots-clés,
   Remplacé par) : voir le guide, étape 9.
   ====================================================================== */
var DOCUMENTS_ID_FEUILLE = '';
var DOCUMENTS_ONGLETS = ['ETIIA', 'ETIIE', 'ETIII'];

/* ----------------------------------------------------------------------
   Rien à modifier en dessous
   ---------------------------------------------------------------------- */

var ONGLET_MODIFICATIONS = 'modifications';
var ONGLET_EDITEURS = 'Éditeurs';
var ONGLET_JOURNAL = 'Journal complet';
var PREFIXE_JOURNAL = 'Journal · ';
var ENTETE_JOURNAL = ['Date', 'Qui', 'Rubrique', 'Pôle', 'Action', 'Élément', 'Ce qui a changé'];
var ENTETE_RUBRIQUE = ['Date', 'Qui', 'Pôle', 'Action', 'Élément', 'Ce qui a changé'];
var JEUX = ['communications', 'flotte', 'organigramme', 'faq', 'documents', 'reunions'];
/* La rubrique d'une modification, décidée ici d'après le jeu et le type :
   c'est elle qui choisit l'onglet du journal. */
var RUBRIQUES = {
  communications: { annonce: 'Communication center', edito: 'Communication center', alerte: 'Communication center', agenda: 'À venir' },
  flotte: { porteur: 'Porteurs' },
  organigramme: { personne: 'Organigramme', squad: 'Organigramme' },
  documents: { document: 'Documents' },
  faq: { question: 'Questions fréquentes' },
  reunions: { 'compte-rendu': 'Réunions' }
};
var ORDRE_RUBRIQUES = ['Communication center', 'À venir', 'Porteurs', 'Organigramme', 'Documents', 'Questions fréquentes', 'Réunions'];
var ACTIONS = ['Ajout', 'Modification', 'Suppression', 'Annulation'];
var COULEURS_ACTION = { 'Ajout': '#e2efe3', 'Modification': '#f7ecd4', 'Suppression': '#f6dfdb', 'Annulation': '#e6e2ef' };
var POLES = ['ETIIA', 'ETIIE', 'ETIII'];
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
    // Le site s'ouvre par son adresse /exec. Pour l'intégrer un jour dans
    // une autre page (Google Sites), remplacer DEFAULT par ALLOWALL.
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
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
  /* Les documents, lus dans leur classeur, s'il est branché. Un classeur
     illisible ne bloque pas le site : il garde ses documents. Un onglet
     manquant n'empêche pas de lire les autres ; le site le signale. */
  if (DOCUMENTS_ID_FEUILLE) {
    try {
      var lecture = lireDocumentsExternes_();
      reponse.bases.documents = lecture.documents;
      if (lecture.avertissements.length) reponse.basesErreur = 'Documents : ' + lecture.avertissements.join(' ; ');
    } catch (e) {
      reponse.basesErreur = 'Liste des documents illisible : ' + e.message;
    }
  }
  return reponse;
}

/**
 * Enregistre un élément ajouté, modifié ou supprimé.
 * @param {string} jeu    communications, flotte, organigramme, faq, documents, reunions
 * @param {Object} modif  { type, id, op: 'maj'|'suppr', donnees, journal }
 *   journal : ce que le site a vu changer, en clair —
 *   { action: 'Ajout'|'Modification'|'Suppression', element, pole, detail }
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
    journaliser_(email, jeu, type, id, op, modif.journal, modif.donnees);
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
    journaliser_(email, jeu, String(type || ''), String(id || ''), 'annulation',
      { detail: 'L’élément redevient celui du fichier d’origine.' }, null);
  } finally {
    verrou.releaseLock();
  }
  return { ok: true };
}

/**
 * Les dernières lignes du journal, la plus récente d'abord : l'Historique
 * du site. Réservé aux éditeurs (il porte des adresses).
 * @param {number} limite  combien de lignes (200 par défaut, 1000 au plus)
 */
function etiiJournal(limite) {
  var email = emailConnecte_();
  if (!peutModifier_(email)) throw new Error('NON_AUTORISE');
  var n = Math.min(Math.max(Number(limite) || 200, 1), 1000);
  var feuille = classeur_().getSheetByName(ONGLET_JOURNAL);
  if (!feuille || feuille.getLastRow() < 2) return [];
  var lignes = feuille.getRange(2, 1, Math.min(n, feuille.getLastRow() - 1), ENTETE_JOURNAL.length).getValues();
  return lignes.map(function (l) {
    var quand = l[0];
    return {
      le: estDate_(quand) ? quand.toISOString() : String(quand || ''),
      par: String(l[1] || ''),
      rubrique: String(l[2] || ''),
      pole: String(l[3] || ''),
      action: String(l[4] || ''),
      element: String(l[5] || ''),
      detail: String(l[6] || '')
    };
  });
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
  var editeurs = onglet_(ONGLET_EDITEURS, ['adresse', 'nom (facultatif)']);
  ongletJournal_(ONGLET_JOURNAL, ENTETE_JOURNAL);
  ORDRE_RUBRIQUES.forEach(function (r) { ongletJournal_(PREFIXE_JOURNAL + r, ENTETE_RUBRIQUE); });
  onglet_(ONGLET_MODIFICATIONS, EN_TETE);
  /* L'onglet vide que Google crée avec le classeur (« Feuille 1 ») ne
     sert à rien : on le retire, la feuille ne montre que les nôtres. */
  var classeur = classeur_();
  classeur.getSheets().forEach(function (f) {
    if (/^(Feuille|Sheet)\s*\d+$/i.test(f.getName()) && f.getLastRow() === 0 && classeur.getSheets().length > 1) classeur.deleteSheet(f);
  });
  var moi = Session.getEffectiveUser().getEmail();
  if (moi && listeEditeurs_().indexOf(moi.toLowerCase()) === -1) editeurs.appendRow([moi, 'propriétaire']);
  var fichier = DriveApp.getFileById(ID_FICHIER_SITE);
  Logger.log('Onglets prêts. Premier éditeur : ' + moi);
  Logger.log('Fichier du site trouvé : ' + fichier.getName() + ' (' + Math.round(fichier.getSize() / 1024) + ' Ko).');
  if (DOCUMENTS_ID_FEUILLE) {
    try {
      var lecture = lireDocumentsExternes_();
      Logger.log('Documents lus : ' + lecture.documents.length
        + (lecture.avertissements.length ? ' (' + lecture.avertissements.join(' ; ') + ')' : '') + '.');
    } catch (e) {
      Logger.log('Documents illisibles : ' + e.message);
    }
  }
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
 * Lit le classeur des documents : un onglet par pôle (DOCUMENTS_ONGLETS),
 * une ligne par document, les colonnes reconnues par leur titre (ligne 1).
 * Les autres colonnes sont ignorées. Un onglet absent ou sans colonne
 * « Titre » est signalé et sauté ; si aucun ne se lit, c'est une erreur.
 * @return {{documents: Object[], avertissements: string[]}}
 */
function lireDocumentsExternes_() {
  var classeur = SpreadsheetApp.openById(DOCUMENTS_ID_FEUILLE);
  var documents = [];
  var avertissements = [];
  var vus = {};
  var lus = 0;
  DOCUMENTS_ONGLETS.forEach(function (nom) {
    var feuille = classeur.getSheetByName(nom);
    if (!feuille) { avertissements.push('onglet « ' + nom + ' » introuvable'); return; }
    try {
      lireOngletDocuments_(feuille, nom, documents, vus);
      lus += 1;
    } catch (e) {
      avertissements.push('onglet « ' + nom + ' » : ' + e.message);
    }
  });
  if (!lus) throw new Error(avertissements.join(' ; ') || 'aucun onglet de documents');
  return { documents: documents, avertissements: avertissements };
}

function lireOngletDocuments_(feuille, nom, documents, vus) {
  if (feuille.getLastRow() < 1 || feuille.getLastColumn() < 1) return;
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
  /* Le pôle de l'onglet : son nom contient le code (« ETIIA »,
     « Documents ETIIE »). Une colonne Pôle remplie a le dernier mot. */
  var trouve = /ETII[AEI]/i.exec(String(nom));
  var poleOnglet = trouve ? trouve[0].toUpperCase() : '';
  var fuseau = Session.getScriptTimeZone ? Session.getScriptTimeZone() : 'Europe/Paris';
  for (var r = 1; r < valeurs.length; r++) {
    var ligne = valeurs[r];
    var doc = {};
    Object.keys(position).forEach(function (champ) {
      var v = ligne[position[champ]];
      if (estDate_(v)) v = Utilities.formatDate(v, fuseau, 'yyyy-MM-dd');
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
    if ((!doc.pole || !doc.pole.length) && poleOnglet) doc.pole = [poleOnglet];
    /* L'identifiant : la colonne « id », sinon la référence, sinon
       l'onglet et la ligne. C'est lui qui relie une modification faite
       dans le site. */
    var id = doc.id || doc.reference || (nom + '-ligne-' + (r + 1));
    while (vus[id]) id = id + '-' + (r + 1);
    vus[id] = true;
    doc.id = id;
    documents.push(doc);
  }
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

function poleDe_(donnees) {
  if (!donnees || typeof donnees !== 'object') return '';
  var v = donnees.poles !== undefined ? donnees.poles : donnees.pole;
  return (Array.isArray(v) ? v : [v]).map(function (x) { return String(x === null || x === undefined ? '' : x).trim(); })
    .filter(function (x) { return x; }).join(', ');
}

function court_(v, n) {
  var t = String(v === null || v === undefined ? '' : v).trim();
  return t.length > n ? t.substring(0, n - 1) + '…' : t;
}

function estDate_(v) {
  return Object.prototype.toString.call(v) === '[object Date]';
}

/* Une cellule qui commence par « = », « + », « - » ou « @ » serait lue
   comme une formule : l'apostrophe la garde en texte (elle ne s'affiche
   pas). */
function enTexte_(v) {
  return (typeof v === 'string' && /^[=+\-@]/.test(v)) ? "'" + v : v;
}

/**
 * Une ligne de journal, la plus récente en haut, dans « Journal complet »
 * et dans l'onglet de sa rubrique. La rubrique est décidée ici ; le site
 * ne fournit que le récit (action, élément, pôle, ce qui a changé).
 */
function journaliser_(email, jeu, type, id, op, infos, donnees) {
  var j = (infos && typeof infos === 'object') ? infos : {};
  var rubrique = (RUBRIQUES[jeu] && RUBRIQUES[jeu][type]) || 'Autres';
  var action = op === 'annulation' ? 'Annulation'
    : (op === 'suppr' ? 'Suppression' : (j.action === 'Ajout' ? 'Ajout' : 'Modification'));
  var element = court_(j.element, 200) || titreDe_(donnees) || id;
  var pole = court_(j.pole, 60) || poleDe_(donnees);
  var detail = court_(j.detail, 3000);
  var quand = new Date();
  ecrireJournal_(ONGLET_JOURNAL, ENTETE_JOURNAL, [quand, email, rubrique, pole, action, element, detail]);
  ecrireJournal_(PREFIXE_JOURNAL + rubrique, ENTETE_RUBRIQUE, [quand, email, pole, action, element, detail]);
}

function ecrireJournal_(nom, entete, ligne) {
  var feuille = ongletJournal_(nom, entete);
  feuille.insertRowAfter(1);
  var plage = feuille.getRange(2, 1, 1, ligne.length);
  plage.setValues([ligne.map(enTexte_)]);
  plage.setFontWeight('normal').setBackground(null).setFontColor('#2a251f');
  feuille.getRange(2, 1).setNumberFormat('dd/MM/yyyy HH:mm');
  var colonneAction = entete.indexOf('Action') + 1;
  feuille.getRange(2, colonneAction).setBackground(COULEURS_ACTION[ligne[colonneAction - 1]] || null);
}

/* Un onglet de journal, mis en forme à sa création : en-tête figé et
   teinté, colonnes à leur largeur, le détail qui passe à la ligne. */
function ongletJournal_(nom, entete) {
  var classeur = classeur_();
  var feuille = classeur.getSheetByName(nom);
  if (feuille) return feuille;
  feuille = classeur.insertSheet(nom);
  feuille.getRange(1, 1, 1, entete.length).setValues([entete])
    .setFontWeight('bold').setBackground('#e9e1d3').setFontColor('#2a251f');
  feuille.setFrozenRows(1);
  var largeurs = { 'Date': 130, 'Qui': 210, 'Rubrique': 170, 'Pôle': 90, 'Action': 110, 'Élément': 300, 'Ce qui a changé': 560 };
  entete.forEach(function (t, i) { if (largeurs[t]) feuille.setColumnWidth(i + 1, largeurs[t]); });
  feuille.getRange(1, entete.length, feuille.getMaxRows(), 1).setWrap(true);
  return feuille;
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
