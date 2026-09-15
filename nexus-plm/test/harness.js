/**
 * Charge les fichiers client RÉELLEMENT livrés (extraction du <script> des
 * .html) et les évalue dans un contexte isolé. On teste le code expédié,
 * pas une copie qui pourrait diverger.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const RACINE = path.join(__dirname, '..', 'src');

function scriptDe(fichier) {
  const source = fs.readFileSync(path.join(RACINE, fichier), 'utf8');
  const morceaux = [];
  const motif = /<script>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = motif.exec(source)) !== null) morceaux.push(m[1]);
  if (!morceaux.length) throw new Error('Aucun <script> dans ' + fichier);
  return morceaux.join('\n');
}

/** DOM minimal : aucun test n'appelle de fonction qui touche vraiment au DOM. */
function faussesGlobales() {
  const noeud = {
    innerHTML: '', textContent: '', value: '', style: {}, dataset: {},
    classList: { add: function () {}, remove: function () {} },
    appendChild: function () {}, removeChild: function () {},
    addEventListener: function () {}, querySelectorAll: function () { return []; },
    closest: function () { return null; }
  };
  // localStorage simulé : les réglages y sont mémorisés.
  const memoire = {};
  return {
    console: console,
    localStorage: {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(memoire, k) ? memoire[k] : null; },
      setItem: function (k, v) { memoire[k] = String(v); },
      removeItem: function (k) { delete memoire[k]; }
    },
    document: {
      getElementById: function () { return Object.assign({}, noeud); },
      querySelector: function () { return null; },
      querySelectorAll: function () { return []; },
      createElement: function () { return Object.assign({}, noeud); },
      addEventListener: function () {},
      body: noeud
    },
    window: {}, setTimeout: setTimeout, clearTimeout: clearTimeout,
    Blob: function () {}, URL: { createObjectURL: function () { return ''; },
                                 revokeObjectURL: function () {} },
    bootstrap: { Modal: { getOrCreateInstance: function () { return { show: function () {} }; },
                          getInstance: function () { return null; } },
                 Offcanvas: { getOrCreateInstance: function () { return { show: function () {} }; },
                              getInstance: function () { return null; } } }
  };
}

// Les liaisons `const` de premier niveau existent dans la portée lexicale du
// contexte mais ne sont pas des propriétés de globalThis : on les y recopie
// pour que les tests puissent les lire.
const LIAISONS = ['Store', 'STATUTS', 'CSV_SEPARATEUR', 'ACTIONS', 'Api',
                  'ETAT', 'SEUIL_DEFAUT', 'MM_PAR_PAS', 'CATALOGUE_MAX',
                  'TYPES', 'MODE', 'GENRE', 'CRITERES_BOITE', 'PORTEES',
                  'CHAMPS_QUALIF', 'CLES_QUALIF', 'TRIS', 'SEUIL_DOUBLON', 'PLAFOND_PAIRES',
                  'SIGNE_ETAT', 'CLE_REGLAGES', 'porteeReglee', 'PORTEURS', 'CHAMPS_BOITE',
                  'CATEGORIES_COMPOSANT', 'NIVEAUX', 'INDEX_COMPOSANTS'];

function chargerClient(fichiers) {
  const contexte = vm.createContext(faussesGlobales());
  fichiers.forEach(function (f) {
    try {
      vm.runInContext(scriptDe(f), contexte, { filename: f });
    } catch (e) {
      throw new Error('Échec du chargement de ' + f + ' : ' + e.message);
    }
  });

  const exposition = LIAISONS.map(function (n) {
    return 'try { globalThis.' + n + ' = ' + n + '; } catch (e) {}';
  }).join('\n');
  vm.runInContext(exposition, contexte, { filename: '(exposition)' });

  return contexte;
}

/** Contrôle syntaxique d'un fichier serveur, sans l'exécuter. */
function verifierSyntaxeServeur(fichier) {
  const source = fs.readFileSync(path.join(RACINE, fichier), 'utf8');
  new vm.Script(source, { filename: fichier });   // lève si la syntaxe est invalide
  return source;
}

module.exports = { chargerClient, scriptDe, verifierSyntaxeServeur, RACINE };
