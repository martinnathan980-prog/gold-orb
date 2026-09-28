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
 *   5. Les documents — votre classeur de documents, un onglet par pôle
 *      (ETIIA, ETIIE, ETIII), lu à chaque ouverture, jamais écrit.
 *   6. Les questions aux experts — « Interroger un expert », dans le site,
 *      ajoute une ligne en haut de l'onglet « Questions aux experts » :
 *      date, qui, pôle, question, contexte, statut « À traiter ». Les
 *      administrateurs y notent le statut et la réponse, et reçoivent un
 *      e-mail à chaque nouvelle question.
 *   7. Le suivi OTQ — l'onglet « Data » de votre Command Center, lu à
 *      chaque ouverture, jamais écrit.
 *   8. L'import des personnes — importerPersonnes(), à lancer UNE fois :
 *      les noms de votre feuille du personnel deviennent l'équipe du pôle,
 *      « à répartir » dans les squads depuis le site.
 *
 * Déploiement : Déployer › Nouveau déploiement › Application web
 *   - Exécuter en tant que : Moi
 *   - Qui a accès : tous les utilisateurs de votre organisation
 * « Exécuter en tant que Moi » : la feuille reste privée (seul le script y
 * écrit) et l'adresse de la personne connectée est connue, puisqu'elle est
 * du même domaine que vous.
 */

/* ======================================================================
   À RENSEIGNER — la ligne obligatoire
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
   Les colonnes sont reconnues par leur titre, où qu'il soit dans les
   premières lignes (« Référence du document », « Titre du document »,
   « Lien d'accès », « Type de document », « Métier », « Applicabilité
   des porteurs », « Sensibilité », « Export Control », « Ajouté par »,
   « Commentaire »…) : voir le guide, étape 9.
   ====================================================================== */
var DOCUMENTS_ID_FEUILLE = '';
var DOCUMENTS_ONGLETS = ['ETIIA', 'ETIIE', 'ETIII'];

/* ======================================================================
   LE SUIVI OTQ — la feuille de votre « Command Center »
   Collez l'identifiant de la feuille qui porte l'onglet « Data » (celui
   que remplit son menu « Airbus Sync »). Le site en lit les mois et les
   nombres (PROD ACCEPTED, MINOR REFUSED, REFUSED ; TVE ACCEPTED, FALSE
   REFUSED, REFUSED). Vide : le site montre des données d'exemple.
   ====================================================================== */
var OTQ_ID_FEUILLE = '';
var OTQ_ONGLET = 'Data';

/* ======================================================================
   LES QUESTIONS AUX EXPERTS — qui reçoit l'e-mail
   Vide : vous, le propriétaire du script. Plusieurs adresses : séparées
   par des virgules.
   ====================================================================== */
var DESTINATAIRES_QUESTIONS = '';

/* ======================================================================
   L'IMPORT DES PERSONNES — pour importerPersonnes(), une seule fois
   La feuille qui liste le personnel du pôle (identifiant entre « /d/ »
   et « /edit »), son onglet (vide : le premier), et le pôle concerné.
   ====================================================================== */
var PERSONNES_ID_FEUILLE = '';
var PERSONNES_ONGLET = '';
var PERSONNES_POLE = 'ETIIE';

/* ----------------------------------------------------------------------
   Rien à modifier en dessous
   ---------------------------------------------------------------------- */

var ONGLET_MODIFICATIONS = 'modifications';
var ONGLET_EDITEURS = 'Éditeurs';
var ONGLET_JOURNAL = 'Journal complet';
var PREFIXE_JOURNAL = 'Journal · ';
var ENTETE_JOURNAL = ['Date', 'Qui', 'Rubrique', 'Pôle', 'Action', 'Élément', 'Ce qui a changé'];
var ENTETE_RUBRIQUE = ['Date', 'Qui', 'Pôle', 'Action', 'Élément', 'Ce qui a changé'];
/* « Interroger un expert » : les questions posées depuis le site, la plus
   récente en haut. Les administrateurs y tiennent le statut et la réponse. */
var ONGLET_QUESTIONS = 'Questions aux experts';
var ENTETE_QUESTIONS = ['Date', 'Qui', 'Pôle', 'Question', 'Contexte', 'Statut', 'Réponse'];
var JEUX = ['communications', 'flotte', 'organigramme', 'faq', 'documents', 'reunions', 'reglages'];
/* La rubrique d'une modification, décidée ici d'après le jeu et le type :
   c'est elle qui choisit l'onglet du journal. */
var RUBRIQUES = {
  communications: { annonce: 'Communication center', edito: 'Communication center', alerte: 'Communication center', agenda: 'À venir' },
  flotte: { porteur: 'Porteurs' },
  organigramme: { personne: 'Organigramme', squad: 'Organigramme', pole: 'Organigramme' },
  documents: { document: 'Documents' },
  faq: { question: 'Questions fréquentes' },
  reunions: { 'compte-rendu': 'Réunions' },
  reglages: { carnet: 'Recherche' }
};
var ORDRE_RUBRIQUES = ['Communication center', 'À venir', 'Porteurs', 'Organigramme', 'Documents', 'Questions fréquentes', 'Réunions', 'Recherche'];
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
  /* Le suivi OTQ, lu dans l'onglet « Data » du Command Center. Illisible,
     il ne bloque rien : le site garde son exemple, et le dit. */
  if (OTQ_ID_FEUILLE) {
    try {
      reponse.bases.otq = lireOtq_();
    } catch (e) {
      reponse.basesErreur = (reponse.basesErreur ? reponse.basesErreur + ' ; ' : '') + 'Suivi OTQ illisible : ' + e.message;
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

/**
 * Une question posée à un expert depuis le site (« Interroger un expert ») :
 * une ligne en haut de l'onglet « Questions aux experts », avec la date,
 * l'adresse de la personne, son pôle et le statut « À traiter ». Tout
 * lecteur peut poser une question ; ce sont les administrateurs qui la
 * suivent, dans la feuille.
 * @param {Object} demande  { question, contexte, pole }
 * @return {{ok: boolean}}
 */
function etiiDemande(demande) {
  var d = (demande && typeof demande === 'object') ? demande : {};
  var question = court_(d.question, 2000);
  if (!question) throw new Error('Question vide.');
  var ligne = [new Date(), emailConnecte_() || 'anonyme', court_(d.pole, 20), question, court_(d.contexte, 500), 'À traiter', ''];
  var feuille = ongletJournal_(ONGLET_QUESTIONS, ENTETE_QUESTIONS);
  feuille.insertRowAfter(1);
  var plage = feuille.getRange(2, 1, 1, ligne.length);
  plage.setValues([ligne.map(enTexte_)]);
  plage.setFontWeight('normal').setBackground(null).setFontColor('#2a251f');
  feuille.getRange(2, 1).setNumberFormat('dd/MM/yyyy HH:mm');
  prevenirQuestion_(ligne);
  return { ok: true };
}

/* L'e-mail aux administrateurs : la question, qui la pose, et le lien
   vers l'onglet. Un e-mail qui ne part pas ne fait pas échouer la
   question : elle est déjà dans la feuille. */
function prevenirQuestion_(ligne) {
  try {
    var a = String(DESTINATAIRES_QUESTIONS || '').trim() || Session.getEffectiveUser().getEmail();
    if (!a) return;
    var qui = String(ligne[1] || 'anonyme');
    var pole = String(ligne[2] || '');
    var corps = [
      'Nouvelle question posée depuis ETII Hub' + (pole ? ' (pôle ' + pole + ')' : '') + '.',
      '',
      'De : ' + qui,
      '',
      'Question :',
      String(ligne[3] || ''),
      ligne[4] ? '\nContexte : ' + ligne[4] : '',
      '',
      'Pour la suivre (statut, réponse) : onglet « ' + ONGLET_QUESTIONS + ' » de la feuille',
      classeur_().getUrl()
    ].join('\n');
    var message = { to: a, subject: 'ETII Hub — question' + (pole ? ' ' + pole : '') + ' : ' + court_(ligne[3], 70), body: corps, name: 'ETII Hub' };
    if (/^[^@\s]+@[^@\s]+$/.test(qui)) message.replyTo = qui;
    MailApp.sendEmail(message);
  } catch (e) {
    Logger.log('E-mail de la question non envoyé : ' + e.message);
  }
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
  ongletJournal_(ONGLET_QUESTIONS, ENTETE_QUESTIONS);
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
  if (OTQ_ID_FEUILLE) {
    try {
      var otq = lireOtq_();
      Logger.log('Suivi OTQ lu : ' + otq.mois.length + ' mois' + (otq.mois.length ? ', de ' + otq.mois[0] + ' à ' + otq.mois[otq.mois.length - 1] : '') + '.');
    } catch (e) {
      Logger.log('Suivi OTQ illisible : ' + e.message);
    }
  }
  /* Autorise l'envoi des e-mails des questions (Google le demande ici,
     une fois) : un simple décompte, rien n'est envoyé. */
  try {
    Logger.log('E-mails des questions : autorisés (' + MailApp.getRemainingDailyQuota() + ' restants aujourd’hui).');
  } catch (e) {
    Logger.log('E-mails des questions non autorisés : ' + e.message);
  }
}

/**
 * À exécuter UNE fois, depuis l'éditeur (▶ Exécuter) : les noms de votre
 * feuille du personnel (PERSONNES_ID_FEUILLE) deviennent l'équipe du pôle
 * PERSONNES_POLE. Les personnes d'exemple de ce pôle disparaissent ; les
 * vraies arrivent dans une squad « À répartir », sans porteur ni
 * compétence : dans le site, « ✎ Modifier » les place ensuite dans leurs
 * squads, nomme les squad leaders et les référents.
 * Relancée, elle n'ajoute que les noms nouveaux : une personne déjà
 * placée dans le site n'est jamais remise « à répartir ».
 */
function importerPersonnes() {
  if (!PERSONNES_ID_FEUILLE) throw new Error('Renseignez PERSONNES_ID_FEUILLE en haut du fichier.');
  var pole = String(PERSONNES_POLE || '').trim().toUpperCase();
  if (POLES.indexOf(pole) === -1) throw new Error('PERSONNES_POLE doit valoir ETIIA, ETIIE ou ETIII.');
  var classeur = SpreadsheetApp.openById(PERSONNES_ID_FEUILLE);
  var source = PERSONNES_ONGLET ? classeur.getSheetByName(PERSONNES_ONGLET) : classeur.getSheets()[0];
  if (!source) throw new Error('Onglet « ' + PERSONNES_ONGLET + ' » introuvable.');
  var noms = nomsDePersonnes_(source.getDataRange().getDisplayValues());
  if (!noms.length) throw new Error('Aucun nom trouvé dans « ' + source.getName() + ' ».');

  var email = Session.getEffectiveUser().getEmail();
  var le = new Date().toISOString();
  var squad = pole + '-a-repartir';
  var verrou = LockService.getScriptLock();
  verrou.waitLock(30000);
  var ajoutees = 0;
  try {
    var feuille = onglet_(ONGLET_MODIFICATIONS, EN_TETE);
    var poser = function (type, id, donnees) {
      var cle = type + '~' + id;
      var ligne = trouverLigne_(feuille, 'organigramme', cle);
      var valeurs = ['organigramme', cle, type, id, 'maj', le, email].concat(decouper_(JSON.stringify(donnees)));
      if (ligne) feuille.getRange(ligne, 1, 1, valeurs.length).setValues([valeurs]);
      else feuille.appendRow(valeurs);
    };
    /* Le pôle ne garde rien de l'exemple, et reçoit sa squad d'attente. */
    poser('pole', pole, { id: pole, sansExemple: true });
    if (!trouverLigne_(feuille, 'organigramme', 'squad~' + squad)) poser('squad', squad, { id: squad, pole: pole, nom: 'À répartir', rang: 99 });
    noms.forEach(function (nom) {
      var id = 'imp-' + pole.toLowerCase() + '-' + cleColonne_(nom);
      if (trouverLigne_(feuille, 'organigramme', 'personne~' + id)) return;
      poser('personne', id, { id: id, nom: nom, poste: '', role: 'membre', pole: pole, squad: squad, competences: [] });
      ajoutees += 1;
    });
  } finally {
    verrou.releaseLock();
  }
  journaliser_(email, 'organigramme', 'personne', 'import-' + pole, 'maj',
    { action: 'Ajout', element: 'Import de ' + ajoutees + ' personne' + (ajoutees > 1 ? 's' : ''), pole: pole,
      detail: noms.length + ' noms lus dans « ' + source.getName() + ' » ; ' + ajoutees + ' ajoutés, placés « À répartir ».' }, null);
  Logger.log(noms.length + ' noms lus, ' + ajoutees + ' ajoutés au pôle ' + pole + ' (squad « À répartir »).');
}

/* Les noms d'une feuille du personnel, quelle que soit sa forme : une
   colonne « Nom » et une colonne « Prénom », ou une seule colonne (« Nom
   Prénom », « Collaborateur », « Nom complet »…), l'en-tête dans l'une
   des cinq premières lignes. Sans en-tête reconnu : la première colonne
   remplie. Chaque nom une seule fois. */
function nomsDePersonnes_(valeurs) {
  var PRENOM = ['prenom', 'firstname', 'givenname'];
  var NOM = ['nom', 'name', 'lastname', 'surname', 'familyname', 'nomdefamille'];
  var COMPLET = ['nomprenom', 'prenomnom', 'nomcomplet', 'fullname', 'collaborateur', 'collaborateurs', 'personne', 'salarie', 'employe', 'displayname'];
  var trouver = function (entetes, liste) {
    for (var i = 0; i < entetes.length; i++) if (liste.indexOf(entetes[i]) !== -1) return i;
    return -1;
  };
  var ligneEntete = -1, iPrenom = -1, iNom = -1, iComplet = -1;
  for (var r = 0; r < Math.min(5, valeurs.length) && ligneEntete === -1; r++) {
    var e = valeurs[r].map(cleColonne_);
    iComplet = trouver(e, COMPLET);
    iPrenom = trouver(e, PRENOM);
    iNom = trouver(e, NOM);
    if (iComplet !== -1 || iNom !== -1) ligneEntete = r;
  }
  if (ligneEntete === -1) {
    ligneEntete = -1;
    iComplet = 0;
    for (var c = 0; c < (valeurs[0] || []).length; c++) if (String(valeurs[0][c]).trim()) { iComplet = c; break; }
  }
  var vus = {};
  var noms = [];
  for (var k = ligneEntete + 1; k < valeurs.length; k++) {
    var l = valeurs[k];
    var nom = iComplet !== -1 ? String(l[iComplet] || '').trim()
      : [iPrenom !== -1 ? String(l[iPrenom] || '').trim() : '', String(l[iNom] || '').trim()].filter(function (x) { return x; }).join(' ');
    nom = nom.replace(/\s+/g, ' ');
    if (!nom || nom.length > 80 || /@/.test(nom)) continue;
    var cle = cleColonne_(nom);
    if (!cle || vus[cle]) continue;
    vus[cle] = true;
    noms.push(nom);
  }
  return noms;
}

/* ======================================================================
   Le suivi OTQ : l'onglet « Data » du Command Center
   ====================================================================== */

var NOMS_MOIS_ = {
  jan: 1, janv: 1, janvier: 1, january: 1, feb: 2, fev: 2, fevr: 2, fevrier: 2, february: 2,
  mar: 3, mars: 3, march: 3, apr: 4, avr: 4, avril: 4, april: 4, may: 5, mai: 5,
  jun: 6, juin: 6, june: 6, jul: 7, juil: 7, juillet: 7, july: 7, aug: 8, aou: 8, aout: 8, august: 8,
  sep: 9, sept: 9, septembre: 9, september: 9, oct: 10, octobre: 10, october: 10,
  nov: 11, novembre: 11, november: 11, dec: 12, decembre: 12, december: 12
};

/* « OCT 26 », une date, « 2026-10 », « 10/2026 » → « 2026-10 » ; '' sinon. */
function moisIso_(v) {
  var ok = function (a, m) { return (a > 1900 && a < 2200 && m >= 1 && m <= 12) ? a + '-' + ('0' + m).slice(-2) : ''; };
  var annee = function (y) { return y < 100 ? 2000 + y : y; };
  if (estDate_(v)) return ok(v.getFullYear(), v.getMonth() + 1);
  var t = String(v === null || v === undefined ? '' : v).trim().toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/^'/, '');
  var m = /^(\d{4})[-\/.](\d{1,2})\b/.exec(t);
  if (m) return ok(Number(m[1]), Number(m[2]));
  m = /^([a-z]+)\.?[\s'’\-\/.]*(\d{2}|\d{4})$/.exec(t);
  if (m && NOMS_MOIS_[m[1]]) return ok(annee(Number(m[2])), NOMS_MOIS_[m[1]]);
  m = /^(\d{1,2})[-\/.](\d{2}|\d{4})$/.exec(t);
  if (m) return ok(annee(Number(m[2])), Number(m[1]));
  m = /^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2}|\d{4})$/.exec(t);
  if (m) return ok(annee(Number(m[3])), Number(m[2]));
  return '';
}

/* La colonne d'un titre : « otq.acc », « tve.fref »… (les emoji et la
   casse ne comptent pas). */
function colonneOtq_(titre) {
  var h = ' ' + String(titre || '').toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Z]+/g, ' ').trim() + ' ';
  if (/ (MOIS|MONTH) /.test(h)) return 'mois';
  var g = / TVE /.test(h) ? 'tve' : (/ PROD /.test(h) ? 'otq' : '');
  if (!g) return '';
  if (/ FALSE /.test(h)) return g + '.fref';
  if (/ MINOR /.test(h)) return g + '.min';
  if (/ ACCEPT/.test(h)) return g + '.acc';
  if (/ REFUS/.test(h)) return g + '.ref';
  return '';
}

/**
 * Lit l'onglet « Data » : une ligne par mois, les nombres de plans par
 * statut. Les colonnes sont reconnues par leur titre ; à défaut, dans
 * l'ordre qu'écrit le Command Center (mois, 3 × PROD, 3 × TVE).
 * @return {{mois: string[], otq: {acc: number[], min: number[], ref: number[]}, tve: {acc: number[], fref: number[], ref: number[]}}}
 */
function lireOtq_() {
  var feuille = SpreadsheetApp.openById(OTQ_ID_FEUILLE).getSheetByName(OTQ_ONGLET);
  if (!feuille) throw new Error('onglet « ' + OTQ_ONGLET + ' » introuvable');
  var valeurs = feuille.getDataRange().getValues();
  var resultat = { mois: [], otq: { acc: [], min: [], ref: [] }, tve: { acc: [], fref: [], ref: [] } };
  if (valeurs.length < 2) return resultat;
  var colonnes = valeurs[0].map(colonneOtq_);
  var parDefaut = ['mois', 'otq.acc', 'otq.min', 'otq.ref', 'tve.acc', 'tve.fref', 'tve.ref'];
  if (colonnes.filter(function (c) { return c && c !== 'mois'; }).length < 3) colonnes = parDefaut;
  var iMois = colonnes.indexOf('mois') !== -1 ? colonnes.indexOf('mois') : 0;
  var lignes = {};
  for (var r = 1; r < valeurs.length; r++) {
    var mois = moisIso_(valeurs[r][iMois]);
    if (!mois) continue;
    var l = { otq: { acc: 0, min: 0, ref: 0 }, tve: { acc: 0, fref: 0, ref: 0 } };
    colonnes.forEach(function (c, i) {
      var p = c.split('.');
      if (p.length === 2 && l[p[0]] && l[p[0]][p[1]] !== undefined) {
        var n = Number(valeurs[r][i]);
        l[p[0]][p[1]] = isFinite(n) && n > 0 ? Math.round(n) : 0;
      }
    });
    lignes[mois] = l;
  }
  Object.keys(lignes).sort().forEach(function (mois) {
    resultat.mois.push(mois);
    ['otq', 'tve'].forEach(function (g) {
      Object.keys(resultat[g]).forEach(function (k) { resultat[g][k].push(lignes[mois][g][k]); });
    });
  });
  return resultat;
}

/* ======================================================================
   4. Outils internes (le « _ » final les rend invisibles depuis le site)
   ====================================================================== */

/* Les titres de colonne reconnus pour chaque champ d'un document, écrits
   sans accents, sans espaces ni ponctuation, en minuscules. Un titre plus
   long qui commence par l'un d'eux convient aussi (« Référence du
   document », « Ajouté par (@ devant votre nom) : »). Dans l'ordre : un
   champ déjà servi ne reprend pas une colonne. */
var COLONNES_DOCUMENTS = {
  id: ['id', 'identifiantunique'],
  titre: ['titredudocument', 'titre', 'title', 'intitule', 'nomdudocument', 'document', 'nom', 'libelle'],
  reference: ['referencedudocument', 'reference', 'ref', 'numero', 'no', 'code', 'identifiant'],
  lien: ['liendacces', 'lien', 'url', 'link', 'adresse', 'chemin'],
  type: ['typededocument', 'typedocument', 'type', 'nature', 'categorie'],
  metier: ['metier', 'metiers', 'domaine', 'discipline'],
  perimetre: ['applicabilitedesporteurs', 'applicabilite', 'perimetre', 'programme', 'appareil', 'produit', 'helicoptere', 'porteurs'],
  sensibilite: ['sensibilite', 'classification', 'confidentialite'],
  exportControl: ['exportcontrol', 'controleexport', 'export'],
  porteur: ['ajoutepar', 'ajoutpar', 'deposepar', 'misenlignepar', 'responsable', 'auteur', 'proprietaire', 'redacteur', 'porteur'],
  pole: ['pole', 'poles', 'equipe'],
  maj: ['maj', 'miseajour', 'datemaj', 'datedemiseajour', 'derniereversion', 'modifiele', 'dateajout', 'date'],
  description: ['description', 'commentaire', 'commentaires', 'resume', 'objet'],
  motsCles: ['motscles', 'motcle', 'tags', 'keywords'],
  remplacePar: ['remplacepar', 'supersededby']
};
var CHAMPS_LISTES = ['metier', 'pole', 'motsCles'];

function cleColonne_(t) {
  return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]/g, '');
}

/* Les colonnes d'une ligne d'en-tête : { champ: index }. D'abord les
   titres exacts, puis ceux qui commencent par un nom connu (5 lettres au
   moins, pour ne pas prendre « Nombre » pour « Nom »). */
function positionsDocuments_(entetes) {
  var position = {};
  var prises = {};
  [false, true].forEach(function (prefixe) {
    Object.keys(COLONNES_DOCUMENTS).forEach(function (champ) {
      if (position[champ] !== undefined) return;
      var noms = COLONNES_DOCUMENTS[champ];
      for (var n = 0; n < noms.length; n++) {
        for (var j = 0; j < entetes.length; j++) {
          if (prises[j] || !entetes[j]) continue;
          var ok = prefixe ? (noms[n].length >= 5 && entetes[j].indexOf(noms[n]) === 0) : entetes[j] === noms[n];
          if (ok) { position[champ] = j; prises[j] = true; return; }
        }
      }
    });
  });
  return position;
}

/**
 * Lit le classeur des documents : un onglet par pôle (DOCUMENTS_ONGLETS),
 * une ligne par document, les colonnes reconnues par leur titre. Les
 * autres colonnes sont ignorées. Un onglet absent ou sans colonne
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
    var feuille = ongletDocuments_(classeur, nom);
    if (!feuille) { avertissements.push('onglet « ' + nom + ' » introuvable'); return; }
    try {
      lireOngletDocuments_(feuille, feuille.getName(), documents, vus);
      lus += 1;
    } catch (e) {
      avertissements.push('onglet « ' + feuille.getName() + ' » : ' + e.message);
    }
  });
  if (!lus) throw new Error(avertissements.join(' ; ') || 'aucun onglet de documents');
  return { documents: documents, avertissements: avertissements };
}

/* L'onglet d'un pôle : son nom exact, sinon le même aux espaces et à la
   casse près, sinon le seul onglet dont le nom contient le code. */
function ongletDocuments_(classeur, nom) {
  var exact = classeur.getSheetByName(nom);
  if (exact) return exact;
  var cle = cleColonne_(nom);
  var feuilles = classeur.getSheets();
  for (var i = 0; i < feuilles.length; i++) if (cleColonne_(feuilles[i].getName()) === cle) return feuilles[i];
  var contient = feuilles.filter(function (f) { return cleColonne_(f.getName()).indexOf(cle) !== -1; });
  return contient.length === 1 ? contient[0] : null;
}

/* Le lien d'une cellule : son lien hypertexte (« Lien » cliquable), une
   formule =HYPERLINK(…), ou l'adresse écrite en clair. */
function lienDeCellule_(riche, formule, texte) {
  try {
    if (riche) {
      var direct = riche.getLinkUrl();
      if (direct) return direct;
      var morceaux = riche.getRuns();
      for (var i = 0; i < morceaux.length; i++) if (morceaux[i].getLinkUrl()) return morceaux[i].getLinkUrl();
    }
  } catch (e) { /* cellule sans texte riche */ }
  var f = /^=\s*HYPERLINK\s*\(\s*"([^"]+)"/i.exec(String(formule || ''));
  if (f) return f[1];
  var t = String(texte || '').trim();
  return /^https?:\/\//i.test(t) ? t : '';
}

function lireOngletDocuments_(feuille, nom, documents, vus) {
  var nLignes = feuille.getLastRow();
  var nColonnes = feuille.getLastColumn();
  if (nLignes < 1 || nColonnes < 1) return;
  var plage = feuille.getRange(1, 1, nLignes, nColonnes);
  var valeurs = plage.getValues();
  var affiches = plage.getDisplayValues();
  /* La ligne des titres : parmi les six premières, celle qui en reconnaît
     le plus (au-dessus, des bandeaux comme « IDENTIFICATION » sont
     ignorés). */
  var ligneTitres = -1;
  var position = null;
  for (var h = 0; h < Math.min(6, valeurs.length); h++) {
    var p = positionsDocuments_(affiches[h].map(cleColonne_));
    if (p.titre === undefined) continue;
    if (!position || Object.keys(p).length > Object.keys(position).length) { position = p; ligneTitres = h; }
  }
  if (!position) throw new Error('aucune colonne « Titre »');
  var debut = ligneTitres + 1;
  if (debut >= valeurs.length) return;
  var riches = null, formules = null;
  if (position.lien !== undefined) {
    var colonneLien = feuille.getRange(debut + 1, position.lien + 1, valeurs.length - debut, 1);
    riches = colonneLien.getRichTextValues();
    formules = colonneLien.getFormulas();
  }
  /* Le pôle de l'onglet : son nom contient le code (« ETIIA »,
     « Documents ETIIE »). Une colonne Pôle remplie a le dernier mot. */
  var trouve = /ETII[AEI]/i.exec(String(nom));
  var poleOnglet = trouve ? trouve[0].toUpperCase() : '';
  var fuseau = Session.getScriptTimeZone ? Session.getScriptTimeZone() : 'Europe/Paris';
  for (var r = debut; r < valeurs.length; r++) {
    var doc = {};
    Object.keys(position).forEach(function (champ) {
      var brut = valeurs[r][position[champ]];
      var v;
      if (champ === 'lien') {
        v = lienDeCellule_(riches ? riches[r - debut][0] : null, formules ? formules[r - debut][0] : '', affiches[r][position[champ]]);
      } else if (estDate_(brut)) {
        v = Utilities.formatDate(brut, fuseau, 'yyyy-MM-dd');
      } else {
        v = String(affiches[r][position[champ]] || '').trim();
      }
      if (champ === 'maj') {
        var fr = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);
        if (fr) v = fr[3] + '-' + ('0' + fr[2]).slice(-2) + '-' + ('0' + fr[1]).slice(-2);
      }
      /* « Ajouté par » : une puce @personne s'affiche par son nom. */
      if (champ === 'porteur') v = v.replace(/^@\s*/, '');
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
    /* Le rang de la ligne : sans colonne de date, la dernière ligne
       ajoutée est le document le plus récent. */
    doc.ligne = r + 1;
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
  var largeurs = { 'Date': 130, 'Qui': 210, 'Rubrique': 170, 'Pôle': 90, 'Action': 110, 'Élément': 300, 'Ce qui a changé': 560,
    'Question': 420, 'Contexte': 220, 'Statut': 110, 'Réponse': 420 };
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
