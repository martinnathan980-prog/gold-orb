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
/* Le propriétaire du classeur (débrief 26) : celui que pose le test, sinon aucun (un Drive partagé). */
Classeur.prototype.getOwner = function () { const e = this.proprietaire; return e ? { getEmail: function () { return e; } } : null; };
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

/* Un blob d'Apps Script : des octets, un type, un nom. */
const zlib = require('zlib');
function octetsDe(donnees) {
  if (donnees === undefined || donnees === null) return Buffer.alloc(0);
  if (Buffer.isBuffer(donnees)) return Buffer.from(donnees);
  if (Array.isArray(donnees)) return Buffer.from(donnees.map(function (b) { return b & 255; }));
  return Buffer.from(String(donnees), 'utf8');
}
function signes(buf) { return Array.from(buf, function (b) { return b > 127 ? b - 256 : b; }); }
function jeuDeCaracteres(c) {
  const n = String(c || 'UTF-8').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (n === 'utf8') return 'utf8';
  if (n === 'iso88591' || n === 'latin1') return 'latin1';
  if (n === 'usascii' || n === 'ascii') return 'ascii';
  throw new Error('Jeu de caractères non simulé : ' + c);
}
function BlobFactice(octets, type, nom) {
  this.octets = octets;
  this.type = type || null;
  this.nom = nom || null;
}
BlobFactice.prototype.setDataFromString = function (texte, jeu) { this.octets = Buffer.from(String(texte), jeuDeCaracteres(jeu)); return this; };
BlobFactice.prototype.setBytes = function (octets) { this.octets = octetsDe(octets); return this; };
BlobFactice.prototype.getBytes = function () { return signes(this.octets); };
BlobFactice.prototype.getDataAsString = function (jeu) { return this.octets.toString(jeuDeCaracteres(jeu)); };
BlobFactice.prototype.getContentType = function () { return this.type; };
BlobFactice.prototype.setContentType = function (t) { this.type = t; return this; };
BlobFactice.prototype.getName = function () { return this.nom; };
BlobFactice.prototype.setName = function (n) { this.nom = n; return this; };
BlobFactice.prototype.copyBlob = function () { return new BlobFactice(Buffer.from(this.octets), this.type, this.nom); };

/**
 * CacheService avec ses VRAIES limites (débrief 23, d'après la doc Google
 * et les mesures publiées) : une clé de 250 caractères au plus, une valeur
 * de 102 400 octets au plus (au-delà : « Argument too large »), six heures
 * au plus, mille éléments au plus — au-delà, les plus anciens partent, une
 * centaine d'un coup. putAll est tout ou rien. `horloge` : une fonction qui
 * rend l'heure en millisecondes (simulée par les tests).
 */
function CacheReel(horloge) {
  this.m = new Map();        // clé -> { v, expire, cree }
  this.horloge = horloge || Date.now;
  this.evictions = 0;
  this.ecrits = 0;
}
CacheReel.prototype._purger = function () {
  const t = this.horloge();
  for (const [k, e] of this.m) if (e.expire <= t) this.m.delete(k);
};
CacheReel.prototype._verifier = function (k, v) {
  if (k === null || k === undefined || k === '') throw new Error('Invalid argument: key');
  if (String(k).length > 250) throw new Error('Argument too large: key');
  if (Buffer.byteLength(String(v), 'utf8') > 102400) throw new Error('Argument too large: value');
};
CacheReel.prototype._poser = function (k, v, s) {
  const t = this.horloge();
  this.m.delete(String(k));
  this.m.set(String(k), { v: String(v), expire: t + 1000 * Math.min(21600, s || 600), cree: t });
  this.ecrits++;
  if (this.m.size > 1000) {
    let n = this.m.size - 900;
    for (const k2 of this.m.keys()) { if (n-- <= 0) break; this.m.delete(k2); this.evictions++; }
  }
};
CacheReel.prototype.get = function (k) { this._purger(); const e = this.m.get(String(k)); return e ? e.v : null; };
CacheReel.prototype.getAll = function (cles) {
  this._purger();
  const r = {};
  cles.forEach((k) => { const e = this.m.get(String(k)); if (e) r[k] = e.v; });
  return r;
};
CacheReel.prototype.put = function (k, v, s) { this._verifier(k, v); this._poser(k, v, s); };
CacheReel.prototype.putAll = function (o, s) {
  const cles = Object.keys(o);
  cles.forEach((k) => this._verifier(k, o[k]));
  cles.forEach((k) => this._poser(k, o[k], s));
};
CacheReel.prototype.remove = function (k) { this.m.delete(String(k)); };
CacheReel.prototype.removeAll = function (cles) { cles.forEach((k) => this.m.delete(String(k))); };
CacheReel.prototype.octets = function () { let n = 0; for (const [k, e] of this.m) n += k.length + Buffer.byteLength(e.v, 'utf8'); return n; };

/**
 * Le modèle évalué comme HtmlService : chaque <?!= expr ?> exécuté dans le
 * serveur (le contexte vm), <?= expr ?> échappé, <? … ?> exécuté. Une
 * exception — include() d'un fichier introuvable — fait échouer
 * l'évaluation entière, comme dans Apps Script.
 */
function evaluerModele(source, contexte) {
  const vm = require('vm');
  const ech = function (t) { return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); };
  return String(source).replace(/<\?(!=|=)?([\s\S]*?)\?>/g, function (tout, sorte, code) {
    const expr = code.trim().replace(/;\s*$/, '');
    const v = vm.runInContext(expr, contexte);
    if (!sorte) return '';
    const t = v === undefined || v === null ? '' : String(v);
    return sorte === '!=' ? t : ech(t);
  });
}

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
      /* Le jour, l'heure et leurs séparateurs (débrief 23 : « préparé à
         09:12 ») ; un autre motif (le décalage « Z » des fuseaux) n'existe
         pas ici, comme avant. Le fuseau est celui du processus. */
      if (typeof motif !== 'string' || /[^yMdHms\-\/:. ]/.test(motif)) throw new Error('formatDate : motif non simulé');
      return motif.replace(/yyyy|MM|dd|HH|mm|ss/g, function (t) {
        return t === 'yyyy' ? String(d.getFullYear()) : t === 'MM' ? deux(d.getMonth() + 1) : t === 'dd' ? deux(d.getDate())
          : t === 'HH' ? deux(d.getHours()) : t === 'mm' ? deux(d.getMinutes()) : deux(d.getSeconds());
      });
    },
    /* Débrief 23 : le paquet voyage gzippé, en base64 « web ». Les blobs et
       leurs octets comme dans Apps Script : des octets signés (-128…127),
       un type, un nom ; ungzip refuse un blob sans le type gzip, et le
       décodage refuse un base64 sans son « = » final — Code.gs le remet. */
    newBlob: function (donnees, type, nom) { return new BlobFactice(octetsDe(donnees), type, nom); },
    gzip: function (blob, nom) {
      return new BlobFactice(zlib.gzipSync(blob.octets), 'application/x-gzip', nom || (blob.nom ? blob.nom + '.gz' : 'archive.gz'));
    },
    ungzip: function (blob) {
      if (!blob || blob.type !== 'application/x-gzip') throw new Error('Blob object must have non-null content type for this operation.');
      return new BlobFactice(zlib.gunzipSync(blob.octets), null, blob.nom ? blob.nom.replace(/\.gz$/, '') : null);
    },
    base64EncodeWebSafe: function (donnees) {
      return octetsDe(donnees).toString('base64').replace(/\+/g, '-').replace(/\//g, '_');
    },
    base64DecodeWebSafe: function (texte) {
      const t = String(texte);
      if (t.length % 4 !== 0 || /[^A-Za-z0-9_\-=]/.test(t)) throw new Error('Could not decode string.');
      return signes(Buffer.from(t.replace(/-/g, '+').replace(/_/g, '/'), 'base64'));
    }
  };
  /* La session : le fuseau du projet, et la clé temporaire du lecteur (celle
     que posent les tests, sinon vide — un lecteur que Google ne nomme pas). */
  contexte.__cleLecteur = '';
  /* Débrief 26 : l'adresse du lecteur (celle que posent les tests, sinon
     vide — Google ne le nomme pas) et celle au nom de qui le script tourne. */
  contexte.__emailLecteur = '';
  contexte.__emailScript = 'responsable@exemple.fr';
  contexte.Session = {
    getScriptTimeZone: function () { return 'Europe/Paris'; },
    getTemporaryActiveUserKey: function () { return contexte.__cleLecteur; },
    getActiveUser: function () { return { getEmail: function () { return contexte.__emailLecteur; } }; },
    getEffectiveUser: function () { return { getEmail: function () { return contexte.__emailScript; } }; }
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
  /* Options (débrief 23) : { cache } un cache déjà fait, partagé entre
     plusieurs contextes (deux exécutions) ; { reel: true, horloge } le cache
     aux vraies limites (CacheReel) ; { document: 'nul' } le cache du
     document absent, comme pour une application web (lien …/exec), ou
     { document: 'autre' } un cache à part. Sans option : un cache sans
     limite, le même des deux côtés, comme avant. */
  contexte.__activerCache = function (options) {
    const o = options || {};
    let cache = o.cache || null;
    if (!cache && o.reel) cache = new CacheReel(o.horloge || Date.now);
    if (!cache) {
      const memoire = {};
      contexte.__memoireCache = memoire;
      cache = {
        get: function (k) { return Object.prototype.hasOwnProperty.call(memoire, k) ? memoire[k] : null; },
        getAll: function (cles) { const r = {}; cles.forEach(function (k) { if (Object.prototype.hasOwnProperty.call(memoire, k)) r[k] = memoire[k]; }); return r; },
        put: function (k, v) { memoire[k] = String(v); },
        putAll: function (o) { Object.keys(o).forEach(function (k) { memoire[k] = String(o[k]); }); },
        remove: function (k) { delete memoire[k]; },
        removeAll: function (cles) { cles.forEach(function (k) { delete memoire[k]; }); }
      };
    }
    contexte.__cache = cache;
    const autre = o.document === 'autre' ? new CacheReel(o.horloge || Date.now) : null;
    contexte.CacheService = {
      getDocumentCache: function () { return o.document === 'nul' ? null : autre || cache; },
      getScriptCache: function () { return cache; }
    };
    return cache;
  };
  contexte.HtmlService = {
    /* Une page servie se reconnaît à sa source : le modèle Index, ou une page
       écrite par le script (celle qui dit quoi recoller, débrief 17).
       Débrief 23 : comme Apps Script, un modèle introuvable lève, et
       l'évaluation exécute ses balises dans le serveur — un include() d'un
       fichier introuvable la fait échouer. */
    createTemplateFromFile: function (nom) {
      if (presents.indexOf(nom) === -1) throw new Error('No HTML file named ' + nom + ' was found.');
      const source = contenuDe(nom);
      return { evaluate: function () { return pageServie({ modele: nom, html: evaluerModele(source, contexte) }); } };
    },
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
      const horaire = {};
      const t = { timeBased: function () { return t; }, onWeekDay: function (j) { horaire.jour = j; return t; }, atHour: function (h) { horaire.heure = h; return t; },
        /* Le préchauffage (débrief 23) : toutes les N minutes. Apps Script
           n'accepte que 1, 5, 10, 15 ou 30. */
        everyMinutes: function (n) {
          if ([1, 5, 10, 15, 30].indexOf(n) === -1) throw new Error('Invalid argument: everyMinutes ' + n);
          horaire.minutes = n; return t;
        },
        everyHours: function (n) { horaire.heures = n; return t; },
        create: function () {
          numeroDeclencheur++;
          const uid = 'declencheur-' + numeroDeclencheur;
          const d = { getHandlerFunction: function () { return fonction; }, getUniqueId: function () { return uid; }, __horaire: horaire };
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

module.exports = { Feuille, Classeur, poserEnvironnement, CacheReel, evaluerModele };
