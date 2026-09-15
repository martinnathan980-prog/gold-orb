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
