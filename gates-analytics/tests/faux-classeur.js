/* Un classeur Google Sheets en mémoire — juste ce dont Code.gs a besoin.
   Il permet de faire tourner le code serveur dans Node, donc de tester pour de
   vrai la détection des colonnes et l'aller-retour de l'historique. */

function Feuille(nom, valeurs, cachee, fusions) {
  this.nom = nom;
  this.valeurs = valeurs;          // tableau de tableaux de chaînes
  this.cachee = !!cachee;
  /* Les plages fusionnées, en 1-based : { ligne, col, larg, haut } (haut :
     1 si absent). La ligne de groupes d'un export GATES en est faite, et
     c'est elle qui dit à quelle famille appartient chaque colonne. */
  this.fusions = fusions || [];
  /* La largeur de la grille, comme dans Sheets : 26 colonnes à la création,
     davantage si les données en occupent plus. Lire ou écrire au-delà lève
     une erreur, comme Sheets ; insertColumnsAfter l'élargit, appendRow aussi. */
  this.colonnesGrille = Math.max(26, plusLarge(valeurs));
  /* Et sa hauteur : 1 000 lignes à la création, comme dans Sheets. Écrire
     au-delà lève une erreur, comme Sheets ; insertRowsAfter l'agrandit. */
  this.lignesGrille = Math.max(1000, (valeurs || []).length);
  this.formats = {};              // le format posé par ligne, quand il y en a un
}
/* Une cellule peut être { valeur, affiche } : un nombre rangé avec un format
   d'affichage (4530 affiché « 4 530 »). getValues rend la valeur,
   getDisplayValues ce qu'affiche Sheets. */
function affichee(v) { return v === null || v === undefined ? '' : v && typeof v === 'object' && 'affiche' in v ? String(v.affiche) : String(v); }
function brute(v) { return v && typeof v === 'object' && 'affiche' in v ? v.valeur : v; }
function plusLarge(lignes) {
  return (lignes || []).reduce(function (m, l) { return Math.max(m, l.length); }, 0);
}
Feuille.prototype.getName = function () { return this.nom; };
Feuille.prototype.isSheetHidden = function () { return this.cachee; };
Feuille.prototype.hideSheet = function () { this.cachee = true; };
Feuille.prototype.showSheet = function () { this.cachee = false; };
Feuille.prototype.setFrozenRows = function () { return this; };
/** La dernière ligne qui porte quelque chose, comme Sheets : les lignes vides du bas ne comptent pas. */
Feuille.prototype.getLastRow = function () {
  let n = this.valeurs.length;
  const vide = function (l) { return !l || l.every(function (v) { return v === '' || v === null || v === undefined; }); };
  while (n > 0 && vide(this.valeurs[n - 1])) n--;
  return n;
};
/** La dernière colonne qui porte quelque chose, 1-based ; 0 si rien. */
Feuille.prototype.getLastColumn = function () {
  return this.valeurs.reduce(function (m, l) {
    let j = l.length;
    while (j > 0 && (l[j - 1] === '' || l[j - 1] === null || l[j - 1] === undefined)) j--;
    return Math.max(m, j);
  }, 0);
};
Feuille.prototype.getMaxColumns = function () { return Math.max(this.colonnesGrille, plusLarge(this.valeurs)); };
/* Sheets compte chaque cellule de la grille, vide ou pas, dans sa limite
   de dix millions par classeur : agrandir au-delà lève, comme Sheets. */
function limiteCellules(feuille, ajout) {
  if (feuille.classeur && feuille.classeur.cellulesGrille() + ajout > 10000000) {
    throw new Error('This action would increase the number of cells in the workbook above the limit of 10000000 cells.');
  }
}
Feuille.prototype.insertColumnsAfter = function (apres, nombre) {
  limiteCellules(this, nombre * this.getMaxRows());
  this.colonnesGrille = this.getMaxColumns() + nombre;
};
Feuille.prototype.getMaxRows = function () { return Math.max(this.lignesGrille, this.valeurs.length); };
Feuille.prototype.insertRowsAfter = function (apres, nombre) {
  limiteCellules(this, nombre * this.getMaxColumns());
  this.lignesGrille = this.getMaxRows() + nombre;
};
Feuille.prototype.appendRow = function (ligne) {
  if (ligne.length > this.getMaxColumns()) this.colonnesGrille = ligne.length;
  this.valeurs.push(ligne.slice());
};
Feuille.prototype.deleteRow = function (n) { this.valeurs.splice(n - 1, 1); };
Feuille.prototype.setName = function (nom) {
  const self = this;
  if (this.classeur && this.classeur.feuilles.some(function (f) { return f !== self && f.getName() === nom; })) {
    throw new Error('A sheet with the name "' + nom + '" already exists. Please enter another name.');
  }
  this.nom = nom;
  return this;
};
/** La place de l'onglet dans le classeur, 1-based, comme Sheets. */
Feuille.prototype.getIndex = function () { return this.classeur ? this.classeur.feuilles.indexOf(this) + 1 : 1; };
/* Retirer des lignes ou des colonnes de la grille, comme Sheets : hors de la
   grille, ou toutes, c'est une erreur. */
Feuille.prototype.deleteRows = function (debut, nombre) {
  const max = this.getMaxRows();
  if (debut < 1 || nombre < 1 || debut + nombre - 1 > max) throw new Error('Those rows are out of bounds.');
  if (nombre >= max) throw new Error('You can\'t delete all the rows on the sheet.');
  this.valeurs.splice(debut - 1, nombre);
  this.lignesGrille = max - nombre;
};
Feuille.prototype.deleteColumns = function (debut, nombre) {
  const max = this.getMaxColumns();
  if (debut < 1 || nombre < 1 || debut + nombre - 1 > max) throw new Error('Those columns are out of bounds.');
  if (nombre >= max) throw new Error('You can\'t delete all the columns on the sheet.');
  this.valeurs.forEach(function (l) { l.splice(debut - 1, nombre); });
  this.colonnesGrille = max - nombre;
};
/** Vide les cellules ; la grille garde sa largeur, comme dans Sheets. */
Feuille.prototype.clearContents = function () {
  this.colonnesGrille = this.getMaxColumns();
  this.lignesGrille = this.getMaxRows();
  this.valeurs = [];
  return this;
};
Feuille.prototype.getDataRange = function () {
  const self = this;
  return {
    getDisplayValues: function () {
      return self.valeurs.map(function (l) {
        return l.map(affichee);
      });
    }
  };
};
Feuille.prototype.getRange = function (ligne, colonne, nbLignes, nbColonnes) {
  const self = this;
  if (colonne + nbColonnes - 1 > this.getMaxColumns() || ligne + nbLignes - 1 > this.getMaxRows()) {
    throw new Error('The coordinates of the range are outside the dimensions of the sheet.');
  }
  /* Comme Sheets : les fusions qui touchent la plage, même en partie. */
  function touche(f) {
    const haut = f.haut || 1;
    return f.ligne <= ligne + nbLignes - 1 && f.ligne + haut - 1 >= ligne &&
           f.col <= colonne + nbColonnes - 1 && f.col + f.larg - 1 >= colonne;
  }
  function fusionsDansLaPlage() {
    return self.fusions
      .filter(touche)
      .map(function (f) {
        return {
          getColumn: function () { return f.col; },
          getNumColumns: function () { return f.larg; },
          getRow: function () { return f.ligne; },
          getNumRows: function () { return f.haut || 1; }
        };
      });
  }
  return {
    getMergedRanges: fusionsDansLaPlage,
    /* Fusionner, comme Sheets : une fusion qui déborde de la plage est une
       erreur ; celles qu'elle contient sont absorbées ; seule la cellule du
       coin garde sa valeur. */
    merge: function () {
      if (nbLignes * nbColonnes < 2) return this;
      const dedans = function (f) {
        return f.ligne >= ligne && f.ligne + (f.haut || 1) - 1 <= ligne + nbLignes - 1 &&
               f.col >= colonne && f.col + f.larg - 1 <= colonne + nbColonnes - 1;
      };
      if (self.fusions.some(function (f) { return touche(f) && !dedans(f); })) {
        throw new Error('You must select all cells in a merged range to merge or unmerge them.');
      }
      self.fusions = self.fusions.filter(function (f) { return !dedans(f); });
      for (let i = 0; i < nbLignes; i++) {
        const l = self.valeurs[ligne - 1 + i];
        if (!l) continue;
        for (let j = 0; j < nbColonnes; j++) {
          if ((i || j) && l[colonne - 1 + j] !== undefined) l[colonne - 1 + j] = '';
        }
      }
      self.fusions.push({ ligne: ligne, col: colonne, larg: nbColonnes, haut: nbLignes });
      return this;
    },
    getDisplayValues: function () {
      const out = [];
      for (let i = 0; i < nbLignes; i++) {
        const source = self.valeurs[ligne - 1 + i] || [];
        const l = [];
        for (let j = 0; j < nbColonnes; j++) l.push(affichee(source[colonne - 1 + j]));
        out.push(l);
      }
      return out;
    },
    getValues: function () {
      const out = [];
      for (let i = 0; i < nbLignes; i++) {
        const source = self.valeurs[ligne - 1 + i] || [];
        const l = [];
        for (let j = 0; j < nbColonnes; j++) l.push(source[colonne - 1 + j] === undefined ? '' : brute(source[colonne - 1 + j]));
        out.push(l);
      }
      return out;
    },
    setValues: function (donnees) {
      donnees.forEach(function (l, i) {
        const cible = ligne - 1 + i;
        if (!self.valeurs[cible]) self.valeurs[cible] = [];
        l.forEach(function (v, j) { self.valeurs[cible][colonne - 1 + j] = v; });
      });
    },
    setFontWeight: function () { return this; },
    /* Le format d'une plage : la batterie vérifie qu'un dépôt passe bien
       l'onglet en texte, pour qu'une cellule « =… » ne devienne pas formule. */
    setNumberFormat: function (format) {
      for (let i = 0; i < nbLignes; i++) self.formats[ligne - 1 + i] = format;
      return this;
    }
  };
};

function Classeur(feuilles, nom) {
  this.feuilles = feuilles;
  this.nom = nom || 'Classeur de test';
  const self = this;
  feuilles.forEach(function (f) { f.classeur = self; });
}
Classeur.prototype.getName = function () { return this.nom; };
Classeur.prototype.cellulesGrille = function () {
  return this.feuilles.reduce(function (s, f) { return s + f.getMaxRows() * f.getMaxColumns(); }, 0);
};
Classeur.prototype.getSheets = function () { return this.feuilles; };
Classeur.prototype.getSheetByName = function (nom) {
  return this.feuilles.filter(function (f) { return f.getName() === nom; })[0] || null;
};
/* L'onglet affiché : celui qu'on a posé (setActiveSheet), sinon le premier. */
Classeur.prototype.getActiveSheet = function () { return this.active || this.feuilles[0] || null; };
Classeur.prototype.setActiveSheet = function (f) { this.active = f; return f; };
Classeur.prototype.insertSheet = function (nom, index) {
  if (this.getSheetByName(nom)) throw new Error('A sheet with the name "' + nom + '" already exists.');
  const f = new Feuille(nom, []);
  if (this.cellulesGrille() + 26000 > 10000000) throw new Error('This action would increase the number of cells in the workbook above the limit of 10000000 cells.');
  f.classeur = this;
  if (typeof index === 'number' && index >= 0 && index < this.feuilles.length) this.feuilles.splice(index, 0, f);
  else this.feuilles.push(f);
  return f;
};
Classeur.prototype.deleteSheet = function (f) {
  const i = this.feuilles.indexOf(f);
  if (i === -1) throw new Error('Sheet not found.');
  if (this.feuilles.length === 1) throw new Error('You can\'t remove all the sheets in a document.');
  this.feuilles.splice(i, 1);
  if (this.active === f) this.active = null;
};
/** Déplace l'onglet affiché à la place donnée, 1-based, comme Sheets. */
Classeur.prototype.moveActiveSheet = function (position) {
  const f = this.getActiveSheet();
  const i = this.feuilles.indexOf(f);
  this.feuilles.splice(i, 1);
  this.feuilles.splice(Math.max(0, Math.min(this.feuilles.length, position - 1)), 0, f);
};

function pageServie(source) {
  const page = { source: source, getContent: function () { return source.html || ''; } };
  ['setTitle', 'addMetaTag', 'setWidth', 'setHeight', 'setXFrameOptionsMode'].forEach(function (m) {
    page[m] = function () { return page; };
  });
  return page;
}

/** Installe les globales Apps Script dans un contexte, autour d'un classeur. */
function poserEnvironnement(contexte, classeur, proprietes, fichiers) {
  const props = proprietes || {};
  /* Les fichiers HTML du projet. Apps Script lève une exception sur un nom
     inconnu : c'est exactement ce que le diagnostic doit savoir détecter.
     Leur contenu est celui du dépôt — le Diagnostic y lit la livraison de
     chacun — sauf si `fichiers` est un objet { nom: contenu }, pour un Index
     d'une autre livraison ou un Javascript coupé au collage. */
  const contenus = fichiers && !Array.isArray(fichiers) ? fichiers : null;
  const presents = contenus ? Object.keys(contenus) : (fichiers || ['Index', 'Styles', 'Javascript']);
  function contenuDe(nom) {
    if (contenus) return contenus[nom];
    const chemin = require('path').join(__dirname, '..', nom + '.html');
    return require('fs').existsSync(chemin) ? require('fs').readFileSync(chemin, 'utf8') : '<!-- ' + nom + ' -->';
  }
  contexte.SpreadsheetApp = {
    getActiveSpreadsheet: function () { return classeur; },
    /* Hors du classeur — la page ouverte par un lecteur, google.script.run —
       Apps Script refuse l'interface : __sansInterface le simule. Une
       question (prompt) prend sa réponse dans __saisies, une confirmation
       (OUI/NON) dans __confirmations, OUI par défaut. */
    getUi: function () {
      if (contexte.__sansInterface) throw new Error('Cannot call SpreadsheetApp.getUi() from this context.');
      return {
        alert: function (a, b, boutons) {
          contexte.__alertes.push(b === undefined ? a : b);
          if (boutons === 'YES_NO') return contexte.__confirmations.length ? contexte.__confirmations.shift() : 'YES';
          return 'OK';
        },
        prompt: function (titre, texte) {
          contexte.__invites.push(texte);
          const r = contexte.__saisies.length ? contexte.__saisies.shift() : { bouton: 'CANCEL', texte: '' };
          return { getSelectedButton: function () { return r.bouton; }, getResponseText: function () { return r.texte; } };
        },
        ButtonSet: { OK: 'OK', OK_CANCEL: 'OK_CANCEL', YES_NO: 'YES_NO' },
        Button: { OK: 'OK', CANCEL: 'CANCEL', YES: 'YES', NO: 'NO', CLOSE: 'CLOSE' },
        createMenu: function () {
          const menu = { addItem: function (texte, fonction) { contexte.__menu.push(fonction); return menu; },
                         addSeparator: function () { return menu; }, addToUi: function () {} };
          return menu;
        },
        showModalDialog: function (page, titre) { contexte.__dialogue = page; contexte.__titreDialogue = titre; }
      };
    }
  };
  contexte.PropertiesService = {
    getDocumentProperties: function () {
      return {
        getProperty: function (k) { return Object.prototype.hasOwnProperty.call(props, k) ? props[k] : null; },
        setProperty: function (k, v) { props[k] = String(v); }
      };
    }
  };
  let compteur = 0;
  contexte.Utilities = {
    getUuid: function () { compteur++; return 'uuid-' + compteur; },
    formatDate: function (d, fuseau, motif) {
      const deux = function (n) { return (n < 10 ? '0' : '') + n; };
      /* Seul le jour est simulé : un autre motif (le décalage « Z » des
         fuseaux) n'existe pas ici, comme avant. */
      if (motif !== 'yyyy-MM-dd') throw new Error('formatDate : motif non simulé');
      return d.getFullYear() + '-' + deux(d.getMonth() + 1) + '-' + deux(d.getDate());
    }
  };
  /* La session : le fuseau du projet, et la clé temporaire du lecteur (celle
     que posent les tests, sinon vide — un lecteur que Google ne nomme pas). */
  contexte.__cleLecteur = '';
  contexte.Session = {
    getScriptTimeZone: function () { return 'Europe/Paris'; },
    getTemporaryActiveUserKey: function () { return contexte.__cleLecteur; }
  };
  /* Le verrou du script est celui que prennent les gestes (verrouDuClasseur_) ;
     celui du document reste là, comme dans Apps Script, mais personne ne
     devrait plus s'y fier : en application web (doPost), il vaut null. */
  contexte.LockService = {
    getScriptLock: function () { return { tryLock: function () { return true; }, releaseLock: function () {} }; },
    getDocumentLock: function () { return { tryLock: function () { return true; }, releaseLock: function () {} }; }
  };
  /* Le cache du classeur n'existe que si un test l'allume : ailleurs, chaque
     test relit le classeur qu'il vient de modifier à la main. */
  contexte.__activerCache = function () {
    const memoire = {};
    contexte.__memoireCache = memoire;
    const cache = {
      get: function (k) { return Object.prototype.hasOwnProperty.call(memoire, k) ? memoire[k] : null; },
      getAll: function (cles) { const r = {}; cles.forEach(function (k) { if (Object.prototype.hasOwnProperty.call(memoire, k)) r[k] = memoire[k]; }); return r; },
      put: function (k, v) { memoire[k] = String(v); },
      putAll: function (o) { Object.keys(o).forEach(function (k) { memoire[k] = String(o[k]); }); }
    };
    contexte.CacheService = { getDocumentCache: function () { return cache; }, getScriptCache: function () { return cache; } };
  };
  contexte.HtmlService = {
    /* Une page servie se reconnaît à sa source : le modèle Index, ou une page
       écrite par le script (celle qui dit quoi recoller, débrief 17). */
    createTemplateFromFile: function (nom) { return { evaluate: function () { return pageServie({ modele: nom }); } }; },
    createHtmlOutput: function (html) { return pageServie({ html: String(html) }); },
    createHtmlOutputFromFile: function (nom) {
      if (presents.indexOf(nom) === -1) throw new Error('Fichier introuvable : ' + nom);
      return { getContent: function () { return contenuDe(nom); } };
    },
    XFrameOptionsMode: { ALLOWALL: 'ALLOWALL' }
  };
  /* Les déclencheurs du projet, vrais objets : l'archivage du vendredi se
     reconnaît à l'identifiant du sien. */
  let numeroDeclencheur = 0;
  contexte.__declencheurs = [];
  contexte.ScriptApp = {
    newTrigger: function (fonction) {
      const t = { timeBased: function () { return t; }, onWeekDay: function () { return t; }, atHour: function () { return t; },
        create: function () {
          numeroDeclencheur++;
          const uid = 'declencheur-' + numeroDeclencheur;
          const d = { getHandlerFunction: function () { return fonction; }, getUniqueId: function () { return uid; } };
          contexte.__declencheurs.push(d);
          return d;
        } };
      return t;
    },
    getProjectTriggers: function () { return contexte.__declencheurs.slice(); },
    deleteTrigger: function (d) { contexte.__declencheurs = contexte.__declencheurs.filter(function (x) { return x !== d; }); },
    WeekDay: { FRIDAY: 'FRIDAY' }
  };
  /* La réponse d'une application web : le texte et son type, lisibles par la batterie. */
  contexte.ContentService = {
    MimeType: { JSON: 'application/json', TEXT: 'text/plain' },
    createTextOutput: function (texte) {
      const sortie = { texte: String(texte), mime: 'text/plain',
        setMimeType: function (m) { sortie.mime = m; return sortie; },
        getContent: function () { return sortie.texte; },
        getMimeType: function () { return sortie.mime; } };
      return sortie;
    }
  };
  contexte.__alertes = [];
  contexte.__invites = [];
  contexte.__menu = [];
  contexte.__saisies = [];
  contexte.__confirmations = [];
  contexte.__sansInterface = false;
  contexte.__proprietes = props;
  return contexte;
}

module.exports = { Feuille, Classeur, poserEnvironnement };
