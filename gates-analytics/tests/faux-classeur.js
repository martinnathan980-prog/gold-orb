/* Un classeur Google Sheets en mémoire — juste ce dont Code.gs a besoin.
   Il permet de faire tourner le code serveur dans Node, donc de tester pour de
   vrai la détection des colonnes et l'aller-retour de l'historique. */

function Feuille(nom, valeurs, cachee) {
  this.nom = nom;
  this.valeurs = valeurs;          // tableau de tableaux de chaînes
  this.cachee = !!cachee;
}
Feuille.prototype.getName = function () { return this.nom; };
Feuille.prototype.isSheetHidden = function () { return this.cachee; };
Feuille.prototype.hideSheet = function () { this.cachee = true; };
Feuille.prototype.setFrozenRows = function () { return this; };
Feuille.prototype.getLastRow = function () { return this.valeurs.length; };
Feuille.prototype.appendRow = function (ligne) { this.valeurs.push(ligne.slice()); };
Feuille.prototype.deleteRow = function (n) { this.valeurs.splice(n - 1, 1); };
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
  return {
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
    setFontWeight: function () { return this; }
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
  contexte.__alertes = [];
  contexte.__proprietes = props;
  return contexte;
}

module.exports = { Feuille, Classeur, poserEnvironnement };
