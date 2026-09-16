// NEXUS PLM — version assemblée pour l'éditeur Apps Script.
// Fichiers d'origine : Config.gs, Repository.gs, Api.gs, Setup.gs
// Ne pas modifier ici : éditer src/server/*.gs et relancer `npm run appsscript`.

// ====================================================================
// server/Config.gs
// ====================================================================
/**
 * NEXUS PLM — configuration serveur.
 * Tout ce qui était en dur et dispersé dans le code est regroupé ici.
 */

const CFG = {
  FEUILLES: {
    BOITES: '1_BOITES',
    NOMENCLATURE: '2_NOMENCLATURE',
    JOURNAL: '9_JOURNAL'
  },

  // Colonnes référencées par le code. Le reste des colonnes est traité
  // génériquement : en ajouter une dans le Sheet suffit à la faire apparaître.
  COL: {
    PN: 'PN Global',
    FONCTION: 'Fonction',
    STATUT: 'Statut',
    DS_VCI: 'DS/VCI Associé',
    PORTEUR: 'Porteur',
    NOM_ID: 'ID_Ligne',
    NOM_TYPE: 'Type',
    NOM_PN_TYPE: 'PN du type'
  },

  EN_TETES: {
    // « Composants » : boutons, voyants, interrupteurs — ce qui se voit et
    // se manipule. Une ligne par composant : Fonction | Norme | Référence.
    BOITES: ['Fonction', 'PN Global', 'DS/VCI Associé', 'Porteur', 'Statut',
             'Niveau de qualification', 'Composants', 'Image', 'Commentaires libres'],
    // Superset de toutes les colonnes, tous types confondus : la feuille reste
    // lisible à l'oeil, et chaque type n'utilise que les siennes (voir
    // client/Types.html, qui pilote l'affichage et l'équivalence).
    // Sur la structure, deux familles de composants distinctes :
    //   « Composants mécaniques »      : colonnettes, entretoises, ce qui est dur
    //   « Composants routing »   : colliers, embases, ce qui tient les câbles
    // Même format : Fonction | Norme | Référence, une ligne par composant.
    NOMENCLATURE: ['ID_Ligne', 'PN Global', 'Type', 'PN du type',
                   'Référence', 'Mots-clés',
                   'Montage', 'Nombre de pas', 'Dim Long (mm)', 'Dim Larg (mm)',
                   'Masse (g)', 'HL', 'DAL',
                   'Qualification Brouillard salin', 'Qualification Vibration',
                   'Qualification Explosion',
                   'Composants mécaniques', 'Composants routing',
                   'Image', 'Commentaires libres'],
    JOURNAL: ['Horodatage', 'Utilisateur', 'Action', 'Cible', 'Détail']
  },

  // Champs à valeurs multiples (rendus sous forme de puces).
  MULTI_BOITE: ['Porteur', 'Composants'],
  MULTI_NOM: ['Qualification Brouillard salin', 'Qualification Vibration',
              'Qualification Explosion', 'Mots-clés',
              'Composants mécaniques', 'Composants routing'],

  // Tous les porteurs Airbus Helicopters, et rien d'autre.
  PORTEURS: ['Dauphin', 'H125', 'H130', 'H135', 'H145', 'H145M', 'H160', 'H160M',
             'H175', 'H215', 'H215M', 'H225', 'H225M', 'NH90', 'Tigre'],

  // Types connus. Le libellé écrit dans la feuille ; le client reconnaît
  // aussi les variantes courantes (accents, synonymes).
  TYPES: ['Structure boîte', 'Harnais', 'Plaquette éclairante', 'Autre sous-ensemble'],

  // Colonnes non éditables depuis la fiche.
  LECTURE_SEULE_NOM: ['ID_Ligne', 'PN Global'],

  STATUTS: ['En étude', 'Validé', 'Obsolète'],
  STATUT_DEFAUT: 'En étude',

  CACHE_CATALOGUE_S: 600,   // 10 min
  VERROU_MS: 20000,         // attente max sur LockService
  JOURNAL_MAX_LIGNES: 5000
};

/** URL du catalogue : en Script Property, plus en dur dans le source. */
function urlCatalogue_() {
  const url = PropertiesService.getScriptProperties().getProperty('URL_CATALOGUE');
  if (!url) {
    throw new Error(
      "Catalogue non configuré. Dans l'éditeur : Paramètres du projet > " +
      "Propriétés du script > ajouter URL_CATALOGUE avec l'URL du classeur catalogue.");
  }
  return url;
}

// ====================================================================
// server/Repository.gs
// ====================================================================
/**
 * NEXUS PLM — accès aux feuilles.
 *
 * Seule couche qui parle à SpreadsheetApp. Trois changements de fond par
 * rapport à la version précédente :
 *   - écriture par LOT (un setValues par ligne au lieu d'un setValue par colonne) ;
 *   - adressage par CLÉ STABLE et non par numéro de ligne, qui se décale à
 *     chaque suppression et faisait viser la mauvaise ligne ;
 *   - toute mutation passe par un verrou.
 */

function classeur_() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

function feuille_(nom) {
  const f = classeur_().getSheetByName(nom);
  if (!f) throw new Error('Feuille introuvable : ' + nom + ". Lancez initialiserBaseDeDonnees().");
  return f;
}

/** Lit une feuille entière -> { enTetes, lignes:[{col:valeur, _ligne:n}] }. */
function lireFeuille_(nom) {
  const f = feuille_(nom);
  const valeurs = f.getDataRange().getValues();
  if (valeurs.length === 0) return { enTetes: [], lignes: [] };

  const enTetes = valeurs[0].map(function (h) { return String(h).trim(); });
  const lignes = [];
  for (let i = 1; i < valeurs.length; i++) {
    const brute = valeurs[i];
    if (brute.every(function (c) { return String(c).trim() === ''; })) continue;
    const obj = { _ligne: i + 1 };
    enTetes.forEach(function (h, j) { if (h) obj[h] = brute[j]; });
    lignes.push(obj);
  }
  return { enTetes: enTetes, lignes: lignes };
}

/**
 * Écrit des modifications sur une ligne, en UN SEUL appel au service Sheets.
 * L'ancien code faisait un setValue par colonne modifiée.
 */
function ecrireLigne_(nom, numLigne, modifications) {
  const f = feuille_(nom);
  const nbCol = f.getLastColumn();
  const plage = f.getRange(numLigne, 1, 1, nbCol);
  const enTetes = f.getRange(1, 1, 1, nbCol).getValues()[0]
                   .map(function (h) { return String(h).trim(); });
  const ligne = plage.getValues()[0];

  let touche = false;
  Object.keys(modifications).forEach(function (cle) {
    const idx = enTetes.indexOf(cle);
    if (idx !== -1) { ligne[idx] = modifications[cle]; touche = true; }
  });
  if (touche) plage.setValues([ligne]);
  return touche;
}

/** Ajoute une ligne à partir d'un objet {colonne: valeur}. */
function ajouterLigne_(nom, objet) {
  const f = feuille_(nom);
  const enTetes = f.getRange(1, 1, 1, f.getLastColumn()).getValues()[0]
                   .map(function (h) { return String(h).trim(); });
  const ligne = enTetes.map(function (h) {
    return Object.prototype.hasOwnProperty.call(objet, h) ? objet[h] : '';
  });
  f.appendRow(ligne);
  return f.getLastRow();
}

/** Ajoute plusieurs lignes en un seul appel (duplication d'assemblage). */
function ajouterLignes_(nom, objets) {
  if (!objets.length) return;
  const f = feuille_(nom);
  const enTetes = f.getRange(1, 1, 1, f.getLastColumn()).getValues()[0]
                   .map(function (h) { return String(h).trim(); });
  const matrice = objets.map(function (o) {
    return enTetes.map(function (h) {
      return Object.prototype.hasOwnProperty.call(o, h) ? o[h] : '';
    });
  });
  f.getRange(f.getLastRow() + 1, 1, matrice.length, enTetes.length).setValues(matrice);
}

function supprimerLigne_(nom, numLigne) {
  feuille_(nom).deleteRow(numLigne);
}

/** Supprime plusieurs lignes en partant du bas, pour ne pas décaler les suivantes. */
function supprimerLignes_(nom, numsLigne) {
  const f = feuille_(nom);
  numsLigne.slice().sort(function (a, b) { return b - a; })
           .forEach(function (n) { f.deleteRow(n); });
}

/**
 * Résout une clé métier -> numéro de ligne, au moment de l'écriture.
 * C'est ce qui rend les suppressions concurrentes sûres : le client n'envoie
 * plus jamais un numéro de ligne qu'il a pu lire il y a dix secondes.
 */
function ligneParCle_(nom, colonneCle, valeurCle) {
  const f = feuille_(nom);
  const valeurs = f.getDataRange().getValues();
  if (!valeurs.length) return -1;
  const idx = valeurs[0].map(function (h) { return String(h).trim(); }).indexOf(colonneCle);
  if (idx === -1) throw new Error('Colonne clé absente : ' + colonneCle);
  const cible = String(valeurCle).trim();
  for (let i = 1; i < valeurs.length; i++) {
    if (String(valeurs[i][idx]).trim() === cible) return i + 1;
  }
  return -1;
}

function ligneParCleObligatoire_(nom, colonneCle, valeurCle) {
  const n = ligneParCle_(nom, colonneCle, valeurCle);
  if (n === -1) {
    throw new Error('Élément introuvable (' + colonneCle + ' = ' + valeurCle +
                    '). Il a peut-être été supprimé entre-temps ; rechargez la page.');
  }
  return n;
}

/** Lit une seule cellule d'une ligne, par nom de colonne. */
function lireCellule_(nom, numLigne, colonne) {
  const f = feuille_(nom);
  const enTetes = f.getRange(1, 1, 1, f.getLastColumn()).getValues()[0]
                   .map(function (h) { return String(h).trim(); });
  const idx = enTetes.indexOf(colonne);
  return idx === -1 ? null : f.getRange(numLigne, idx + 1).getValue();
}

/** [2,3,4,9,10] -> [{debut:2,fin:4},{debut:9,fin:10}] : écritures groupées. */
function decouperEnPlages_(numeros) {
  const tries = numeros.slice().sort(function (a, b) { return a - b; });
  const plages = [];
  tries.forEach(function (n) {
    const derniere = plages[plages.length - 1];
    if (derniere && n === derniere.fin + 1) derniere.fin = n;
    else plages.push({ debut: n, fin: n });
  });
  return plages;
}

/** Identifiant stable, sans collision possible entre deux appels de la même ms. */
function nouvelId_(prefixe) {
  return prefixe + '-' + Date.now().toString(36) + '-' +
         Utilities.getUuid().slice(0, 8);
}

/** Sérialise les écritures concurrentes. */
function avecVerrou_(operation) {
  const verrou = LockService.getDocumentLock();
  if (!verrou.tryLock(CFG.VERROU_MS)) {
    throw new Error('Une autre modification est en cours. Réessayez dans un instant.');
  }
  try {
    return operation();
  } finally {
    verrou.releaseLock();
  }
}

/** Journal des modifications : qui a changé quoi, et quand. */
function journaliser_(action, cible, detail) {
  try {
    let f = classeur_().getSheetByName(CFG.FEUILLES.JOURNAL);
    if (!f) {
      f = classeur_().insertSheet(CFG.FEUILLES.JOURNAL);
      f.getRange(1, 1, 1, CFG.EN_TETES.JOURNAL.length).setValues([CFG.EN_TETES.JOURNAL]);
      f.setFrozenRows(1);
    }
    let utilisateur = '';
    try { utilisateur = Session.getActiveUser().getEmail() || ''; } catch (e) { utilisateur = '(inconnu)'; }
    f.appendRow([new Date(), utilisateur, action, cible, detail || '']);

    if (f.getLastRow() > CFG.JOURNAL_MAX_LIGNES) {
      f.deleteRows(2, f.getLastRow() - CFG.JOURNAL_MAX_LIGNES);
    }
  } catch (e) {
    // Le journal ne doit jamais faire échouer l'opération métier.
    console.error('Journalisation impossible : ' + e.message);
  }
}

// ====================================================================
// server/Api.gs
// ====================================================================
/**
 * NEXUS PLM — API exposée au client.
 *
 * Seules les fonctions de ce fichier sont appelables depuis l'interface.
 * Chacune valide ses entrées, prend le verrou, journalise, et renvoie le
 * MINIMUM nécessaire : l'ancien code relisait les deux feuilles entières après
 * chaque frappe, y compris pour l'ajout d'une puce.
 */

function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('NEXUS PLM - Ingénierie')
    // DEFAULT et non ALLOWALL : ALLOWALL autorisait l'intégration de l'outil
    // dans n'importe quel site tiers (clickjacking).
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}

/** Permet de découper Index.html en plusieurs fichiers. */
function include(nomFichier) {
  return HtmlService.createHtmlOutputFromFile(nomFichier).getContent();
}

// ============================================================
// Lecture
// ============================================================

function getToutLeContenu() {
  const boites = lireFeuille_(CFG.FEUILLES.BOITES);
  const nomenclature = lireFeuille_(CFG.FEUILLES.NOMENCLATURE);
  garantirIdsNomenclature_(nomenclature);

  return {
    boites: boites.lignes.map(nettoyer_),
    nomenclature: nomenclature.lignes.map(nettoyer_),
    headersBoites: boites.enTetes.filter(String),
    headersNom: nomenclature.enTetes.filter(String),
    config: {
      multiBoite: CFG.MULTI_BOITE,
      multiNom: CFG.MULTI_NOM,
      lectureSeuleNom: CFG.LECTURE_SEULE_NOM,
      statuts: CFG.STATUTS,
      porteurs: CFG.PORTEURS
    }
  };
}

/**
 * Le numéro de ligne ne quitte plus le serveur : il se décale à chaque
 * suppression, et le client pouvait le renvoyer périmé.
 */
function nettoyer_(ligne) {
  const copie = {};
  Object.keys(ligne).forEach(function (k) {
    if (k !== '_ligne') copie[k] = ligne[k];
  });
  return copie;
}

/** Donne un ID aux lignes qui n'en ont pas (reprise de l'existant). */
function garantirIdsNomenclature_(lues) {
  const sansId = lues.lignes.filter(function (l) {
    return !String(l[CFG.COL.NOM_ID] || '').trim();
  });
  if (!sansId.length) return;

  const f = feuille_(CFG.FEUILLES.NOMENCLATURE);
  const idxId = lues.enTetes.indexOf(CFG.COL.NOM_ID) + 1;

  // Écriture par plages contiguës plutôt qu'un setValue par ligne.
  sansId.forEach(function (l) { l[CFG.COL.NOM_ID] = nouvelId_('L'); });
  decouperEnPlages_(sansId.map(function (l) { return l._ligne; }))
    .forEach(function (plage) {
      const valeurs = sansId
        .filter(function (l) { return l._ligne >= plage.debut && l._ligne <= plage.fin; })
        .map(function (l) { return [l[CFG.COL.NOM_ID]]; });
      f.getRange(plage.debut, idxId, valeurs.length, 1).setValues(valeurs);
    });
  journaliser_('MIGRATION', CFG.FEUILLES.NOMENCLATURE,
               sansId.length + ' ligne(s) sans ID_Ligne complétée(s)');
}

function getCatalogueComposants() {
  const cache = CacheService.getScriptCache();
  const enCache = cache.get('catalogue');
  if (enCache) {
    try { return JSON.parse(enCache); } catch (e) { /* cache illisible, on relit */ }
  }

  const classeur = SpreadsheetApp.openByUrl(urlCatalogue_());
  const valeurs = classeur.getSheets()[0].getDataRange().getValues();
  if (!valeurs.length) return [];

  const enTetes = valeurs[0].map(function (h) { return String(h).trim(); });
  const composants = [];
  for (let i = 1; i < valeurs.length; i++) {
    if (valeurs[i].every(function (c) { return String(c).trim() === ''; })) continue;
    const obj = {};
    enTetes.forEach(function (h, j) { if (h) obj[h] = valeurs[i][j]; });
    composants.push(obj);
  }

  try {
    cache.put('catalogue', JSON.stringify(composants), CFG.CACHE_CATALOGUE_S);
  } catch (e) {
    // Dépassement de la taille de cache : sans gravité, on relira.
  }
  return composants;
}

// ============================================================
// Écriture — boîtes
// ============================================================

function saveBoite(pn, modifications) {
  return avecVerrou_(function () {
    const ligne = ligneParCleObligatoire_(CFG.FEUILLES.BOITES, CFG.COL.PN, pn);
    const modifs = Object.assign({}, modifications);

    // Renommage du PN : il sert de clé étrangère à la nomenclature.
    const nouveauPn = modifs[CFG.COL.PN] !== undefined ? String(modifs[CFG.COL.PN]).trim() : null;
    if (nouveauPn !== null && nouveauPn !== String(pn).trim()) {
      exigerPnLibre_(nouveauPn);
      modifs[CFG.COL.PN] = nouveauPn;
    }

    // On ne valide que si le statut a effectivement changé : une valeur
    // héritée hors liste ne doit pas bloquer l'édition des autres champs.
    if (modifs[CFG.COL.STATUT] !== undefined) {
      const statutActuel = String(lireCellule_(CFG.FEUILLES.BOITES, ligne, CFG.COL.STATUT) || '').trim();
      const statutVoulu = String(modifs[CFG.COL.STATUT]).trim();
      if (statutVoulu !== statutActuel) modifs[CFG.COL.STATUT] = validerStatut_(statutVoulu);
      else delete modifs[CFG.COL.STATUT];
    }

    ecrireLigne_(CFG.FEUILLES.BOITES, ligne, modifs);

    if (nouveauPn !== null && nouveauPn !== String(pn).trim()) {
      repercuterRenommage_(pn, nouveauPn);
      journaliser_('RENOMMAGE', pn, '-> ' + nouveauPn);
    }
    journaliser_('MODIF_BOITE', nouveauPn || pn, Object.keys(modifs).join(', '));

    return { ok: true, boite: relireBoite_(nouveauPn || pn), pnPrecedent: pn };
  });
}

function repercuterRenommage_(ancienPn, nouveauPn) {
  const lues = lireFeuille_(CFG.FEUILLES.NOMENCLATURE);
  lues.lignes
    .filter(function (l) { return String(l[CFG.COL.PN]).trim() === String(ancienPn).trim(); })
    .forEach(function (l) {
      const modif = {};
      modif[CFG.COL.PN] = nouveauPn;
      ecrireLigne_(CFG.FEUILLES.NOMENCLATURE, l._ligne, modif);
    });
}

function addBoite(pn, fonction, dsVci) {
  return avecVerrou_(function () {
    const propre = exigerTexte_(pn, 'Le PN Global');
    exigerPnLibre_(propre);

    const objet = {};
    objet[CFG.COL.PN] = propre;
    objet[CFG.COL.FONCTION] = String(fonction || '').trim();
    objet[CFG.COL.DS_VCI] = String(dsVci || '').trim();
    objet[CFG.COL.STATUT] = CFG.STATUT_DEFAUT;
    ajouterLigne_(CFG.FEUILLES.BOITES, objet);

    journaliser_('CREATION_BOITE', propre, '');
    return { ok: true, boite: relireBoite_(propre) };
  });
}

function deleteBoiteEntiere(pn) {
  return avecVerrou_(function () {
    const ligne = ligneParCleObligatoire_(CFG.FEUILLES.BOITES, CFG.COL.PN, pn);

    const lues = lireFeuille_(CFG.FEUILLES.NOMENCLATURE);
    const aSupprimer = lues.lignes
      .filter(function (l) { return String(l[CFG.COL.PN]).trim() === String(pn).trim(); })
      .map(function (l) { return l._ligne; });

    supprimerLignes_(CFG.FEUILLES.NOMENCLATURE, aSupprimer);
    supprimerLigne_(CFG.FEUILLES.BOITES, ligne);

    journaliser_('SUPPRESSION_BOITE', pn, aSupprimer.length + ' sous-ensemble(s)');
    return { ok: true, pnSupprime: pn, nbNomenclature: aSupprimer.length };
  });
}

// ============================================================
// Écriture — nomenclature
// ============================================================

function saveNomenclature(idLigne, modifications) {
  return avecVerrou_(function () {
    const ligne = ligneParCleObligatoire_(CFG.FEUILLES.NOMENCLATURE, CFG.COL.NOM_ID, idLigne);

    // On ne laisse jamais le client réécrire l'identité de la ligne.
    const modifs = {};
    Object.keys(modifications).forEach(function (k) {
      if (CFG.LECTURE_SEULE_NOM.indexOf(k) === -1) modifs[k] = modifications[k];
    });

    ecrireLigne_(CFG.FEUILLES.NOMENCLATURE, ligne, modifs);
    journaliser_('MODIF_NOMENCLATURE', idLigne, Object.keys(modifs).join(', '));
    return { ok: true, ligne: relireNomenclature_(idLigne) };
  });
}

function addSousEnsemble(pn, type, pnType) {
  return avecVerrou_(function () {
    if (ligneParCle_(CFG.FEUILLES.BOITES, CFG.COL.PN, pn) === -1) {
      throw new Error('Assemblage introuvable : ' + pn);
    }
    const id = nouvelId_('L');
    const objet = {};
    objet[CFG.COL.NOM_ID] = id;
    objet[CFG.COL.PN] = pn;
    objet[CFG.COL.NOM_TYPE] = String(type || '').trim();
    objet[CFG.COL.NOM_PN_TYPE] = String(pnType || '').trim();
    ajouterLigne_(CFG.FEUILLES.NOMENCLATURE, objet);

    journaliser_('CREATION_NOMENCLATURE', id, pn + ' / ' + objet[CFG.COL.NOM_TYPE]);
    return { ok: true, ligne: relireNomenclature_(id) };
  });
}

function deleteNomenclature(idLigne) {
  return avecVerrou_(function () {
    const ligne = ligneParCleObligatoire_(CFG.FEUILLES.NOMENCLATURE, CFG.COL.NOM_ID, idLigne);
    supprimerLigne_(CFG.FEUILLES.NOMENCLATURE, ligne);
    journaliser_('SUPPRESSION_NOMENCLATURE', idLigne, '');
    return { ok: true, idSupprime: idLigne };
  });
}

// ============================================================
// Validation et relecture ciblée
// ============================================================

function exigerTexte_(valeur, libelle) {
  const propre = String(valeur === null || valeur === undefined ? '' : valeur).trim();
  if (!propre) throw new Error(libelle + ' est obligatoire.');
  return propre;
}

function exigerPnLibre_(pn) {
  if (ligneParCle_(CFG.FEUILLES.BOITES, CFG.COL.PN, pn) !== -1) {
    throw new Error('Le PN Global "' + pn + '" existe déjà.');
  }
}

function validerStatut_(statut) {
  const propre = String(statut || '').trim();
  if (!propre) return CFG.STATUT_DEFAUT;
  const trouve = CFG.STATUTS.find(function (s) {
    return s.toLowerCase() === propre.toLowerCase();
  });
  if (!trouve) {
    throw new Error('Statut invalide : "' + propre + '". Attendu : ' + CFG.STATUTS.join(', ') + '.');
  }
  return trouve;
}

function relireBoite_(pn) {
  const lues = lireFeuille_(CFG.FEUILLES.BOITES);
  const b = lues.lignes.find(function (l) {
    return String(l[CFG.COL.PN]).trim() === String(pn).trim();
  });
  return b ? nettoyer_(b) : null;
}

function relireNomenclature_(id) {
  const lues = lireFeuille_(CFG.FEUILLES.NOMENCLATURE);
  const l = lues.lignes.find(function (x) {
    return String(x[CFG.COL.NOM_ID]).trim() === String(id).trim();
  });
  return l ? nettoyer_(l) : null;
}

// ====================================================================
// server/Setup.gs
// ====================================================================
/**
 * NEXUS PLM — initialisation et maintenance.
 *
 * L'ancienne initialiserBaseDeDonnees() faisait sheet.clear() puis réinjectait
 * le jeu de démo SANS AUCUNE CONFIRMATION : un lancement accidentel depuis
 * l'éditeur effaçait tout. Elle est désormais scindée en deux :
 *   - creerStructureSiAbsente()  : sûre, ne touche à aucune donnée existante ;
 *   - reinitialiserAvecDemo()    : destructive, exige une confirmation écrite.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('NEXUS PLM')
    .addItem('Créer / compléter la structure', 'creerStructureSiAbsente')
    .addSeparator()
    .addItem('Réinitialiser avec le jeu de démo…', 'demanderReinitialisation')
    .addToUi();
}

/** Crée les feuilles et en-têtes manquants. Ne supprime jamais de données. */
function creerStructureSiAbsente() {
  const ss = classeur_();
  [[CFG.FEUILLES.BOITES, CFG.EN_TETES.BOITES],
   [CFG.FEUILLES.NOMENCLATURE, CFG.EN_TETES.NOMENCLATURE],
   [CFG.FEUILLES.JOURNAL, CFG.EN_TETES.JOURNAL]].forEach(function (paire) {
    const nom = paire[0], enTetes = paire[1];
    let f = ss.getSheetByName(nom);
    if (!f) {
      f = ss.insertSheet(nom);
      f.getRange(1, 1, 1, enTetes.length).setValues([enTetes]);
      habillerEnTete_(f, enTetes.length);
    } else {
      // Complète les colonnes absentes sans toucher aux colonnes existantes.
      const actuels = f.getRange(1, 1, 1, Math.max(1, f.getLastColumn())).getValues()[0]
                       .map(function (h) { return String(h).trim(); });
      const manquants = enTetes.filter(function (h) { return actuels.indexOf(h) === -1; });
      if (manquants.length) {
        f.getRange(1, actuels.filter(String).length + 1, 1, manquants.length)
         .setValues([manquants]);
      }
    }
  });
  SpreadsheetApp.getActiveSpreadsheet().toast('Structure vérifiée.', 'NEXUS PLM');
}

function habillerEnTete_(f, nbCol) {
  const enTete = f.getRange(1, 1, 1, nbCol);
  enTete.setFontWeight('bold').setFontColor('#ffffff').setBackground('#0f172a')
        .setHorizontalAlignment('center').setVerticalAlignment('middle');
  f.setFrozenRows(1);
  // Bornage sur le nombre de lignes réel : setRowHeights lève au-delà.
  const nbLignes = Math.max(1, f.getMaxRows() - 1);
  f.getRange(2, 1, nbLignes, nbCol)
   .setHorizontalAlignment('center').setVerticalAlignment('middle')
   .setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
  f.setRowHeights(2, nbLignes, 35);
  for (let i = 1; i <= nbCol; i++) f.setColumnWidth(i, 150);
  // applyRowBanding lève si la plage est déjà bandée : on retire l'existant.
  f.getBandings().forEach(function (b) { b.remove(); });
  f.getRange(1, 1, Math.min(f.getMaxRows(), Math.max(100, f.getLastRow())), nbCol)
   .applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);
}

function demanderReinitialisation() {
  const ui = SpreadsheetApp.getUi();
  const reponse = ui.prompt(
    'Réinitialisation complète',
    'Cette action EFFACE toutes les boîtes et toute la nomenclature, puis ' +
    'réinstalle le jeu de démonstration.\n\nTapez EFFACER pour confirmer :',
    ui.ButtonSet.OK_CANCEL);

  if (reponse.getSelectedButton() !== ui.Button.OK) return;
  if (reponse.getResponseText().trim().toUpperCase() !== 'EFFACER') {
    ui.alert('Confirmation incorrecte : rien n\'a été modifié.');
    return;
  }
  reinitialiserAvecDemo();
  ui.alert('Base réinitialisée avec le jeu de démonstration.');
}

function reinitialiserAvecDemo() {
  const ss = classeur_();
  journaliser_('REINITIALISATION', '(base entière)', 'jeu de démo réinstallé');

  [[CFG.FEUILLES.BOITES, CFG.EN_TETES.BOITES],
   [CFG.FEUILLES.NOMENCLATURE, CFG.EN_TETES.NOMENCLATURE]].forEach(function (paire) {
    const nom = paire[0], enTetes = paire[1];
    let f = ss.getSheetByName(nom);
    if (!f) f = ss.insertSheet(nom);
    else { f.getBandings().forEach(function (b) { b.remove(); }); f.clear(); f.clearFormats(); }
    f.getRange(1, 1, 1, enTetes.length).setValues([enTetes]);
    habillerEnTete_(f, enTetes.length);
  });

  // Colonnes boîte : Fonction, PN Global, DS/VCI, Porteur, Statut, Niveau,
  //                  Composants (Fonction | Norme | Référence), Image, Commentaires
  const boites = [
    ['APU',     '332P20001',   '332P20051',   'H225',        'Validé',   'Qualified to H225', 'Bouton poussoir | ECS 7251 | MS24523-22\nBouton poussoir | ECS 0763 | MS24523-31\nVoyant | ECS 4410 | LED-G-28', '', ''],
    ['EOS',     '332P94101',   '332P94051',   'H225\nH215',  'En étude', 'Qualified to H225', 'Interrupteur | ASNE 0567 | 8500K12\nVoyant | ECS 4411 | LED-R-28', '', ''],
    ['APU',     'U880A240101', 'U880A240051', 'H160',        'Obsolète', 'Qualified to H160', 'Bouton poussoir | ECS 7251 | MS24523-22\nVoyant | ECS 4410 | LED-G-05', '', ''],
    ['NAV',     '332N10001',   '332N10051',   'H225',        'Validé',   'Qualified to H225', 'Relais | ECS 1120 | RLY-28-2C\nInterrupteur | ASNE 0571 | TGL-2P', '', ''],
    ['COM',     '332C50001',   '332C50051',   'H145\nH145M', 'En étude', 'Qualified to H160', 'Bouton poussoir | ECS 0780 | MS24523-40\nBouton poussoir | ECS 7251 | MS24523-22', '', ''],
    ['RADAR',   'U880R30001',  'U880R30051',  'H160',        'Validé',   'Qualified to H160', 'Voyant | ECS 4410 | LED-G-28\nFusible | NSA 9350 | F5A', '', ''],
    ['FLIGHT',  '332F40001',   '332F40051',   'H225',        'Validé',   'Qualified to H225', 'Interrupteur | ASNE 0567 | 8500K12\nBouton poussoir | ECS 7251 | MS24523-22', '', ''],
    ['POWER',   'U880P50001',  'U880P50051',  'H160\nH160M', 'En étude', 'Qualified to H160', 'Double commande | FRF 772-034 | DC-IG-2\nFusible | NSA 9350 | F5A', '', ''],
    ['SENSOR',  '332S60001',   '332S60051',   'H175',        'Obsolète', 'Qualified to H225', 'Voyant | ECS 4411 | LED-R-05', '', ''],
    ['DISPLAY', 'U880D70001',  'U880D70051',  'H160',        'Validé',   'Qualified to H160', 'Bouton poussoir | ECS 7251 | MS24523-22\nVoyant | ECS 4410 | LED-G-28\nRelais | ECS 1120 | RLY-28-2C', '', '']
  ];
  ss.getSheetByName(CFG.FEUILLES.BOITES)
    .getRange(2, 1, boites.length, boites[0].length).setValues(boites);

  // Colonnes nomenclature : PN Global, Type, PN du type, Référence, Mots-clés,
  //   Montage, Nb pas, Long, Larg, Masse, HL, DAL, 3 qualifications,
  //   Composants mécaniques, Composants routing, Image, Commentaires
  const nom = [
    ['332P20001',   'Structure boîte',      '332P20001.01',   '', '', 'Console STD',  '1', '500', '140', '500',  'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332P20001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332P20001',   'Plaquette éclairante', '332P20001.05',   '', 'APU, démarrage, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332P94101',   'Structure boîte',      '332P94101.01',   '', '', 'Hors console', '5', '400', '200', '400',  'B', 'C', 'Cat. T', 'Qual. H225', '', 'Colonnette | NSA 5512 | COL-M4-30\nInsert | NSA 5591 | INS-M4', 'Collier | NSA 8420 | CT-120\nPasse-fil | ECS 2230 | PF-8', '', ''],
    ['332P94101',   'Plaquette éclairante', '332P94101.02',   '', 'EOS, optronique, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880A240101', 'Harnais',              'U880A240401',    'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880A240101', 'Structure boîte',      'U880A240101.01', '', '', 'Console STD',  '2', '480', '140', '520',  'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-B', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332N10001',   'Structure boîte',      '332N10001.01',   '', '', 'Rack',         '2', '300', '200', '800',  'B', 'B', 'Cat. S', 'Qual. H225', '', 'Colonnette | NSA 5512 | COL-M5-25\nEntretoise | NSA 5520 | ENT-10', 'Collier | NSA 8421 | CT-200\nEmbase | ECS 2210 | EMB-6', '', ''],
    ['332N10001',   'Plaquette éclairante', '332N10001.03',   '', 'NAV, navigation, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332C50001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880R30001',  'Structure boîte',      'U880R30001.01',  '', '', 'Nez',          '1', '600', '400', '1500', 'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M6-40\nÉquerre | EN 2491 | EQ-90-A\nInsert | NSA 5591 | INS-M6', 'Collier | NSA 8421 | CT-200\nPasse-fil | ECS 2230 | PF-12', '', ''],
    ['332F40001',   'Plaquette éclairante', '332F40001.02',   '', 'FLIGHT, pilotage, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332F40001',   'Structure boîte',      '332F40001.01',   '', '', 'Console STD',  '1', '500', '140', '495',  'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332F40001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880P50001',  'Harnais',              'U880P50001.03',  'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332S60001',   'Plaquette éclairante', '332P94101.02',   '', 'EOS, optronique, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880D70001',  'Structure boîte',      'U880D70001.01',  '', '', 'Console STD',  '1', '500', '145', '510',  'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-22\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['U880D70001',  'Plaquette éclairante', 'U880D70001.04',  '', 'DISPLAY, affichage, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', '', '']
  ].map(function (l) { return [nouvelId_('L')].concat(l); });

  ss.getSheetByName(CFG.FEUILLES.NOMENCLATURE)
    .getRange(2, 1, nom.length, nom[0].length).setValues(nom);

  SpreadsheetApp.getActiveSpreadsheet().toast('Base NEXUS PLM déployée.', 'Système opérationnel');
}
