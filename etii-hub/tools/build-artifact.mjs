// Construit une version AUTONOME du hub, en un seul fichier HTML.
//
//   node tools/build-artifact.mjs
//   -> dist/etii-hub.html
//
// Pourquoi : le site multi-pages a besoin d'un serveur (les navigateurs
// bloquent fetch sur file://) et d'URL relatives qui résolvent. Le fichier
// produit ici n'a aucune de ces contraintes : tout est intégré, il s'ouvre
// par double-clic et se publie n'importe où.
//
// Le site multi-pages de la racine reste la source de vérité. Ce script ne
// le modifie jamais : il lit et assemble.

import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const RACINE = join(dirname(fileURLToPath(import.meta.url)), '..');
const lire = (p) => readFileSync(join(RACINE, p), 'utf8');

const PAGES = ['index', 'etiia', 'etiie', 'etiii',
               'reunions', 'organigramme', 'faq', 'docsearch'];
const CSS = ['polices', 'tokens', 'base', 'components', 'skin', 'modules'];
const DONNEES = ['communications', 'reunions', 'organigramme', 'faq',
                 'documents', 'indicateurs', 'flotte'];

/* ---------------------------------------------------------------------
   1. Mini-assembleur de modules ES
   Les modules du projet n'utilisent qu'une seule forme d'import :
   `import { a, b } from './x.js';`. On peut donc les assembler sans
   outillage : chaque module devient un bloc qui publie ses exports dans
   un registre, et chaque import devient une déstructuration de ce registre.
   -------------------------------------------------------------------- */

function nomsExportes(source) {
  const noms = new Set();
  for (const m of source.matchAll(
      /^export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z0-9_$]+)/gm)) {
    noms.add(m[1]);
  }
  for (const m of source.matchAll(/^export\s*\{([^}]*)\}/gm)) {
    for (const part of m[1].split(',')) {
      const n = part.trim().split(/\s+as\s+/).pop().trim();
      if (n) noms.add(n);
    }
  }
  return [...noms];
}

function transformer(source) {
  return source
    // Les imports deviennent des déstructurations du registre.
    .replace(/^import\s*\{([\s\S]*?)\}\s*from\s*['"]\.\/([A-Za-z0-9_-]+)\.js['"]\s*;?/gm,
      (_t, noms, cible) => {
        const paires = noms.split(',').map(s => s.trim()).filter(Boolean)
          .map(s => {
            const [src, alias] = s.split(/\s+as\s+/).map(x => x.trim());
            return alias ? `${src}: ${alias}` : src;
          });
        return `const { ${paires.join(', ')} } = __M["${cible}"];`;
      })
    // Les imports dynamiques `await import('./x.js')` deviennent une
    // promesse déjà résolue sur le registre : même sémantique, sans réseau.
    .replace(/\bimport\s*\(\s*['"]\.\/([A-Za-z0-9_-]+)\.js['"]\s*\)/g,
      (_t, cible) => `Promise.resolve(__M["${cible}"])`)
    // `export` disparaît : la publication se fait via le registre.
    .replace(/^export\s+(?=(?:async\s+)?(?:function|const|let|var|class)\b)/gm, '')
    .replace(/^export\s*\{[^}]*\}\s*;?\s*$/gm, '');
}

// Certains modules de page utilisent `await` au niveau racine (le module ES
// l'autorise, pas une fonction ordinaire). Ceux-là sont enveloppés dans une
// fonction asynchrone. Les modules du socle doivent rester synchrones : leurs
// exports sont consommés immédiatement par les pages.
function bloc(nom, source, { asynchrone = false } = {}) {
  const noms = nomsExportes(source);
  const corps = transformer(source);
  if (asynchrone) {
    return `/* ===== module ${nom}.js ===== */\n(async function () {\n`
         + corps + `\n})();\n`;
  }
  return `/* ===== module ${nom}.js ===== */\n__M["${nom}"] = (function () {\n`
       + corps + `\nreturn { ${noms.join(', ')} };\n})();\n`;
}

/* Le script assemblé est analysé avec les sémantiques d'un module ES —
   `import.meta` et `await` racine y sont licites — avant d'être scellé dans
   le fichier. Une erreur de syntaxe échoue ici, pas chez l'utilisateur. */
function verifierSyntaxe(nom, code) {
  const fichier = join(tmpdir(), `etii-verif-${nom}.mjs`);
  try {
    writeFileSync(fichier, code);
    execFileSync(process.execPath, ['--check', fichier], { stdio: 'pipe' });
  } catch (e) {
    const detail = (e.stderr ? e.stderr.toString() : e.message).split('\n')
      .filter(l => l.trim()).slice(0, 4).join('\n    ');
    throw new Error(`Script assemblé invalide pour ${nom}.html :\n    ${detail}`);
  } finally {
    try { rmSync(fichier, { force: true }); } catch (_e) { /* sans importance */ }
  }
}

/* ---------------------------------------------------------------------
   2. Assemblage d'une page complète et autonome
   -------------------------------------------------------------------- */

const cssAssemble = CSS.map(n =>
  `/* ---- ${n}.css ---- */\n` + lire(`assets/css/${n}.css`)).join('\n\n');

const donneesAssemblees = Object.fromEntries(
  DONNEES.map(n => [n, JSON.parse(lire(`assets/data/${n}.json`))]));

// Les fichiers texte lus par fetch() dans le site multi-pages (le CSV
// d'exemple du suivi OTQ / OTD) sont intégrés eux aussi : sans serveur, un
// fetch relatif échoue depuis file://.
const TEXTES = ['assets/data/otq-exemple.csv'];
const textesAssembles = Object.fromEntries(TEXTES.map(n => [n, lire(n)]));

// Les photos des porteurs (flotte.json → `photo`) sont des fichiers image
// relatifs : dans un cadre srcdoc, rien ne les résout. Elles sont donc
// intégrées en data URI — mais seulement dans les pages qui affichent la
// flotte, sinon chaque page en porterait une copie.
const imagesLues = new Map();
function dataUri(chemin) {
  if (!/^assets\/img\/[a-z0-9_\-\/]+\.(jpe?g|png|webp|svg)$/i.test(chemin)) return null;
  if (!imagesLues.has(chemin)) {
    const type = /\.svg$/i.test(chemin) ? 'image/svg+xml'
      : /\.png$/i.test(chemin) ? 'image/png'
      : /\.webp$/i.test(chemin) ? 'image/webp' : 'image/jpeg';
    const octets = readFileSync(join(RACINE, chemin));
    imagesLues.set(chemin, `data:${type};base64,${octets.toString('base64')}`);
  }
  return imagesLues.get(chemin);
}

function donneesAvecImages(noms) {
  const copie = { ...donneesAssemblees };
  if (noms.includes('porteurs')) {
    const flotte = JSON.parse(JSON.stringify(donneesAssemblees.flotte));
    for (const appareil of (Array.isArray(flotte.flotte) ? flotte.flotte : [])) {
      const uri = dataUri(String(appareil.photo || '').trim());
      if (uri) appareil.photo = uri;
    }
    copie.flotte = flotte;
  }
  if (noms.includes('kiosque')) {
    const comms = JSON.parse(JSON.stringify(donneesAssemblees.communications));
    const entrees = [comms.motDuChef].concat(comms.annonces || [], comms.agenda || []).filter(Boolean);
    for (const e of entrees) {
      if (!e.image || typeof e.image !== 'object') continue;
      const uri = dataUri(String(e.image.src || '').trim());
      if (uri) e.image.src = uri;
    }
    copie.communications = comms;
  }
  return copie;
}

/* Résolution TRANSITIVE des dépendances.
   Une liste de modules écrite en dur se périme au premier module partagé
   ajouté au projet — et l'échec est silencieux à la construction, visible
   seulement à l'exécution. On part donc du module de la page et on suit
   ses imports, en profondeur d'abord, pour obtenir un ordre topologique. */
function dependances(nom, vues = new Set(), ordre = []) {
  if (vues.has(nom)) return ordre;
  vues.add(nom);
  const source = lire(`assets/js/${nom}.js`);
  const cibles = new Set();
  for (const m of source.matchAll(/^import\s*\{[\s\S]*?\}\s*from\s*['"]\.\/([A-Za-z0-9_-]+)\.js['"]/gm))
    cibles.add(m[1]);
  for (const m of source.matchAll(/\bimport\s*\(\s*['"]\.\/([A-Za-z0-9_-]+)\.js['"]\s*\)/g))
    cibles.add(m[1]);
  for (const cible of cibles) dependances(cible, vues, ordre);
  ordre.push(nom);
  return ordre;
}

// Une page peut charger PLUSIEURS modules — la page elle-même, et des
// modules transverses comme le sélecteur de direction. On les lit tous,
// dans l'ordre du document, plutôt que de supposer qu'il n'y en a qu'un :
// prendre le premier ferait passer un module transverse pour la page.
function modulesDeLaPage(nom, html) {
  const noms = [...html.matchAll(
    /<script type="module" src="assets\/js\/([a-z0-9-]+)\.js"><\/script>/g)]
    .map((m) => m[1]);
  if (!noms.length) {
    throw new Error(`${nom}.html : aucun module <script type="module" src="assets/js/…"> trouvé`);
  }
  return noms;
}

function construirePage(nom) {
  let html = lire(`${nom}.html`);

  // Les quatre feuilles deviennent un seul bloc de style intégré.
  html = html.replace(
    /[ \t]*<link rel="stylesheet" href="assets\/css\/[a-z]+\.css">\n?/g, '');
  html = html.replace(/(<\/title>)/,
    `$1\n  <style>\n${cssAssemble}\n  </style>`);

  // Le module de page devient un script intégré, dépendances comprises.
  const moduleDePage = bles(modulesDeLaPage(nom, html));
  // Tous les modules sont fondus dans un seul script ; les balises
  // d'origine disparaissent.
  html = html.replace(
    /[ \t]*<script type="module" src="assets\/js\/[a-z0-9-]+\.js"><\/script>\n?/g, '');
  html = html.replace(/([ \t]*)<\/body>/,
    `  <script type="module">\n${moduleDePage}\n  </script>\n$1</body>`);

  verifierSyntaxe(nom, moduleDePage);

  return html;
}

function bles(noms) {
  // Les modules d'entrée viennent en dernier ; leurs dépendances les
  // précèdent, chacune une seule fois, dans l'ordre d'évaluation.
  const entrees = Array.isArray(noms) ? noms : [noms];
  const vues = new Set();
  const ordre = [];
  for (const entree of entrees) dependances(entree, vues, ordre);
  const socle = ordre.filter((n) => !entrees.includes(n))
    .map(n => bloc(n, lire(`assets/js/${n}.js`))).join('\n');
  return `const __M = {};
// Les données sont intégrées : aucun fetch, donc aucune contrainte file://
// ni d'URL de base. chargerDonnees est remplacée par une lecture directe.
const __DONNEES = ${json(donneesAvecImages(ordre))};

${socle}

__M["data"].chargerDonnees = function (nomJeu) {
  const jeu = __DONNEES[nomJeu];
  return jeu
    ? Promise.resolve(jeu)
    : Promise.reject(new Error(
        'Jeu de données « ' + nomJeu + ' » absent de la version autonome.'));
};

// Le suivi OTQ / OTD : si une source réelle est configurée, on la lit
// comme sur le site ; sinon l'exemple embarqué remplace le fetch.
const __TEXTES = ${json(textesAssembles)};
if (__M["otq"] && typeof __M["otq"].chargerSuivi === 'function') {
  const chargerSuiviReseau = __M["otq"].chargerSuivi;
  __M["otq"].chargerSuivi = function () {
    const source = __M["otq"].SOURCE || {};
    if (String(source.url || '').trim()) return chargerSuiviReseau();
    const texte = __TEXTES[source.exemple || 'assets/data/otq-exemple.csv'];
    if (typeof texte !== 'string') {
      return Promise.reject(new Error('Exemple OTQ / OTD absent de la version autonome.'));
    }
    const series = __M["otq"].seriesDepuisLignes(__M["otq"].analyserCsv(texte));
    return Promise.resolve({ series, origine: 'exemple', maj: '', url: source.exemple || '' });
  };
}

${entrees.map((n) => bloc(n, lire(`assets/js/${n}.js`), { asynchrone: true })).join('\n')}`;
}

/* Sérialisation sûre pour une insertion DANS une balise <script>.
   Sans cela, le « </script> » contenu dans les pages intégrées fermerait
   la balise englobante et le HTML fuirait dans le document parent.
   On neutralise aussi « <!-- », que l'analyseur traite spécialement. */
function json(valeur) {
  return JSON.stringify(valeur)
    .replace(/<\//g, '<\\/')
    .replace(/<!--/g, '<\\u0021--')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/* ---------------------------------------------------------------------
   3. Coquille : navigation entre les pages, chacune dans son cadre isolé
   Chaque page est servie telle quelle dans un iframe srcdoc. L'isolation
   est totale : aucune collision d'identifiants, aucun gestionnaire global
   qui déborde d'une page sur l'autre, et le rendu est exactement celui du
   site multi-pages.
   -------------------------------------------------------------------- */

const pagesAssemblees = Object.fromEntries(
  PAGES.map(n => [n, construirePage(n)]));

const coquille = `<title>ETII Hub</title>
<style>
  html, body { height: 100%; margin: 0; background: #06080f; }
  #cadre { display: block; width: 100%; height: 100%; border: 0; }
</style>

<iframe id="cadre" title="ETII Hub"></iframe>

<script>
(function () {
  var PAGES = ${json(pagesAssemblees)};
  var cadre = document.getElementById('cadre');
  var courante = null;

  function nomDepuisHref(href) {
    if (!href) return null;
    var m = String(href).match(/([a-z-]+)\\.html(?:[?#].*)?$/i);
    return m && PAGES[m[1]] ? m[1] : null;
  }

  function afficher(nom, ancre) {
    if (!PAGES[nom]) nom = 'index';
    courante = nom;
    try { history.replaceState(null, '', '#' + nom + (ancre || '')); } catch (e) {}
    cadre.srcdoc = PAGES[nom];
  }

  // Les liens internes du site changent de page sans quitter le fichier.
  cadre.addEventListener('load', function () {
    var doc;
    try { doc = cadre.contentDocument; } catch (e) { return; }
    if (!doc) return;

    doc.addEventListener('click', function (evt) {
      var lien = evt.target && evt.target.closest && evt.target.closest('a[href]');
      if (!lien) return;
      var nom = nomDepuisHref(lien.getAttribute('href'));
      if (!nom) return;
      evt.preventDefault();
      if (nom !== courante) afficher(nom);
    });
  });

  var depart = (location.hash || '').replace('#', '').split('?')[0];
  afficher(PAGES[depart] ? depart : 'index');
})();
</script>`;

mkdirSync(join(RACINE, 'dist'), { recursive: true });
writeFileSync(join(RACINE, 'dist/etii-hub.html'), coquille);

const ko = (Buffer.byteLength(coquille) / 1024).toFixed(0);
console.log(`dist/etii-hub.html écrit — ${ko} ko, ${PAGES.length} pages intégrées`);
