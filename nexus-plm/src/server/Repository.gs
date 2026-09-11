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
