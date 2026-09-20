/* Un classeur Google Sheets en mémoire — juste ce dont Code.gs a besoin.
   Il permet de faire tourner le code serveur dans Node, donc de tester pour de
   vrai la détection des colonnes et l'aller-retour de l'historique. */

function Feuille(nom, valeurs, cachee, fusions) {
  this.nom = nom;
  this.valeurs = valeurs;          // tableau de tableaux de chaînes
  this.cachee = !!cachee;
  /* Les plages fusionnées, en 1-based : { ligne, col, larg }. La ligne de
     groupes d'un export GATES en est faite, et c'est elle qui dit à quelle
     famille appartient chaque colonne. */
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
function plusLarge(lignes) {
  return (lignes || []).reduce(function (m, l) { return Math.max(m, l.length); }, 0);
}
Feuille.prototype.getName = function () { return this.nom; };
Feuille.prototype.isSheetHidden = function () { return this.cachee; };
Feuille.prototype.hideSheet = function () { this.cachee = true; };
Feuille.prototype.showSheet = function () { this.cachee = false; };
Feuille.prototype.setFrozenRows = function () { return this; };
Feuille.prototype.getLastRow = function () { return this.valeurs.length; };
/** La dernière colonne qui porte quelque chose, 1-based ; 0 si rien. */
Feuille.prototype.getLastColumn = function () {
  return this.valeurs.reduce(function (m, l) {
    let j = l.length;
    while (j > 0 && (l[j - 1] === '' || l[j - 1] === null || l[j - 1] === undefined)) j--;
    return Math.max(m, j);
  }, 0);
};
Feuille.prototype.getMaxColumns = function () { return Math.max(this.colonnesGrille, plusLarge(this.valeurs)); };
Feuille.prototype.insertColumnsAfter = function (apres, nombre) { this.colonnesGrille = this.getMaxColumns() + nombre; };
Feuille.prototype.getMaxRows = function () { return Math.max(this.lignesGrille, this.valeurs.length); };
Feuille.prototype.insertRowsAfter = function (apres, nombre) { this.lignesGrille = this.getMaxRows() + nombre; };
Feuille.prototype.appendRow = function (ligne) {
  if (ligne.length > this.getMaxColumns()) this.colonnesGrille = ligne.length;
  this.valeurs.push(ligne.slice());
};
Feuille.prototype.deleteRow = function (n) { this.valeurs.splice(n - 1, 1); };
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
        return l.map(function (v) { return v === null || v === undefined ? '' : String(v); });
      });
    }
  };
};
Feuille.prototype.getRange = function (ligne, colonne, nbLignes, nbColonnes) {
  const self = this;
  if (colonne + nbColonnes - 1 > this.getMaxColumns() || ligne + nbLignes - 1 > this.getMaxRows()) {
    throw new Error('The coordinates of the range are outside the dimensions of the sheet.');
  }
  function fusionsDansLaPlage() {
    return self.fusions
      .filter(function (f) {
        return f.ligne >= ligne && f.ligne < ligne + nbLignes &&
               f.col >= colonne && f.col < colonne + nbColonnes;
      })
      .map(function (f) {
        return {
          getColumn: function () { return f.col; },
          getNumColumns: function () { return f.larg; },
          getRow: function () { return f.ligne; },
          getNumRows: function () { return 1; }
        };
      });
  }
  return {
    getMergedRanges: fusionsDansLaPlage,
    getDisplayValues: function () {
      return this.getValues().map(function (l) {
        return l.map(function (v) { return v === null || v === undefined ? '' : String(v); });
      });
    },
    getValues: function () {
      const out = [];
      for (let i = 0; i < nbLignes; i++) {
        const source = self.valeurs[ligne - 1 + i] || [];
        const l = [];
        for (let j = 0; j < nbColonnes; j++) l.push(source[colonne - 1 + j] === undefined ? '' : source[colonne - 1 + j]);
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

function Classeur(feuilles, nom) { this.feuilles = feuilles; this.nom = nom || 'Classeur de test'; }
Classeur.prototype.getName = function () { return this.nom; };
Classeur.prototype.getSheets = function () { return this.feuilles; };
Classeur.prototype.getSheetByName = function (nom) {
  return this.feuilles.filter(function (f) { return f.getName() === nom; })[0] || null;
};
Classeur.prototype.insertSheet = function (nom) {
  const f = new Feuille(nom, []);
  this.feuilles.push(f);
  return f;
};

/** Installe les globales Apps Script dans un contexte, autour d'un classeur. */
function poserEnvironnement(contexte, classeur, proprietes, fichiers) {
  const props = proprietes || {};
  /* Les fichiers HTML du projet. Apps Script lève une exception sur un nom
     inconnu : c'est exactement ce que le diagnostic doit savoir détecter. */
  const presents = fichiers || ['Index', 'Styles', 'Javascript'];
  contexte.SpreadsheetApp = {
    getActiveSpreadsheet: function () { return classeur; },
    getUi: function () {
      return {
        alert: function (a, b) { contexte.__alertes.push(b === undefined ? a : b); },
        ButtonSet: { OK: 'OK' },
        createMenu: function () {
          const menu = { addItem: function () { return menu; }, addSeparator: function () { return menu; }, addToUi: function () {} };
          return menu;
        },
        showModalDialog: function () {}
      };
    }
  };
  contexte.PropertiesService = {
    getDocumentProperties: function () {
      return {
        getProperty: function (k) { return Object.prototype.hasOwnProperty.call(props, k) ? props[k] : null; },
        setProperty: function (k, v) { props[k] = v; }
      };
    }
  };
  let compteur = 0;
  contexte.Utilities = { getUuid: function () { compteur++; return 'uuid-' + compteur; } };
  contexte.HtmlService = {
    createTemplateFromFile: function () { return { evaluate: function () { return { setTitle: function () { return this; }, addMetaTag: function () { return this; }, setWidth: function () { return this; }, setHeight: function () { return this; }, setXFrameOptionsMode: function () { return this; } }; } }; },
    createHtmlOutputFromFile: function (nom) {
      if (presents.indexOf(nom) === -1) throw new Error('Fichier introuvable : ' + nom);
      return { getContent: function () { return '<!-- ' + nom + ' -->'; } };
    },
    XFrameOptionsMode: { ALLOWALL: 'ALLOWALL' }
  };
  contexte.ScriptApp = {
    newTrigger: function () { const t = { timeBased: function () { return t; }, onWeekDay: function () { return t; }, atHour: function () { return t; }, create: function () {} }; return t; },
    getProjectTriggers: function () { return []; },
    deleteTrigger: function () {},
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
  contexte.__proprietes = props;
  return contexte;
}

module.exports = { Feuille, Classeur, poserEnvironnement };
