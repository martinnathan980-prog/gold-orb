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

import { readFileSync, writeFileSync, mkdirSync, rmSync, readdirSync, existsSync } from 'node:fs';
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

// Les feuilles sont recopiées dans CHAQUE page intégrée : on retire les
// commentaires et l'indentation, qui n'ont de sens que dans les sources.
// Les règles restent une par ligne, lisibles dans l'inspecteur.
function alleger(css) {
  return css
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n').map((l) => l.trim()).filter(Boolean).join('\n');
}

const cssAssemble = CSS.map(n =>
  `/* ---- ${n}.css ---- */\n` + alleger(lire(`assets/css/${n}.css`))).join('\n');

// La feuille assemblée est publiée UNE fois dans la coquille ; chaque page
// n'en porte que ce jeton, remplacé juste avant d'être posée en srcdoc.
const JETON_CSS = '/*__CSS__*/';

const donneesAssemblees = Object.fromEntries(
  DONNEES.map(n => [n, JSON.parse(lire(`assets/data/${n}.json`))]));

// Les fichiers texte lus par fetch() dans le site multi-pages (le CSV
// d'exemple du suivi OTQ / OTD) sont intégrés eux aussi : sans serveur, un
// fetch relatif échoue depuis file://.
const TEXTES = ['assets/data/otq-exemple.csv'];
const textesAssembles = Object.fromEntries(TEXTES.map(n => [n, lire(n)]));

// Les images du site (assets/img/…) sont des fichiers relatifs : dans un
// cadre srcdoc, rien ne les résout. Elles sont donc intégrées en data URI,
// UNE fois, dans la coquille (voir plus bas) : chaque page les trouve chez
// son parent, et ui.js les résout au rendu d'un <img>. Les données, elles,
// gardent leurs chemins — ce qu'on modifie dans le site n'embarque jamais
// une photo encodée.
const imagesLues = new Map();
function dataUri(chemin) {
  if (!/^assets\/(img|polices)\/[a-z0-9_\-\/]+\.(jpe?g|png|webp|svg|woff2)$/i.test(chemin)) return null;
  if (!imagesLues.has(chemin)) {
    const type = /\.svg$/i.test(chemin) ? 'image/svg+xml'
      : /\.png$/i.test(chemin) ? 'image/png'
      : /\.webp$/i.test(chemin) ? 'image/webp'
      : /\.woff2$/i.test(chemin) ? 'font/woff2' : 'image/jpeg';
    const octets = readFileSync(join(RACINE, chemin));
    imagesLues.set(chemin, `data:${type};base64,${octets.toString('base64')}`);
  }
  return imagesLues.get(chemin);
}

// Les url() des feuilles de style pointent vers des fichiers voisins
// (assets/polices/*.woff2, appelés en ../polices/ depuis assets/css/). Dans
// un cadre srcdoc, qui n'a AUCUNE URL de base, rien ne les résout : sans
// cette passe, l'artefact perdrait ses quatre polices sans le moindre
// message. Elles sont donc intégrées, comme les images.
const cssIntegre = cssAssemble.replace(
  /url\(\s*(['"]?)([^'")]+)\1\s*\)/g,
  (tout, _guillemet, brut) => {
    if (/^(data:|https?:|#)/i.test(brut)) return tout;
    const uri = dataUri(brut.replace(/^\.\.\//, 'assets/'));
    return uri ? `url(${uri})` : tout;
  });

// Aucun chemin relatif ne doit survivre : il serait muet dans un srcdoc.
const restant = cssIntegre.match(/url\(\s*['"]?(?!data:)[^'")]+\)/);
if (restant) {
  throw new Error(
    `feuille de style : ${restant[0]} n'a pas pu être intégré — un cadre `
    + `srcdoc ne le résoudrait pas. Élargissez le garde-fou de dataUri().`);
}

// Toutes les images de assets/img/, une seule fois pour les huit pages.
function imagesDuSite() {
  const table = {};
  const parcourir = (dossier) => {
    for (const entree of readdirSync(join(RACINE, dossier), { withFileTypes: true })) {
      const chemin = dossier + '/' + entree.name;
      if (entree.isDirectory()) parcourir(chemin);
      else {
        const uri = dataUri(chemin);
        if (uri) table[chemin] = uri;
      }
    }
  };
  if (existsSync(join(RACINE, 'assets/img'))) parcourir('assets/img');
  return table;
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

  // Les six feuilles deviennent un seul bloc de style intégré. Le style
  // n'est pas recopié ici : le jeton est remplacé par la coquille au moment
  // de poser le srcdoc, sinon les huit pages porteraient huit copies de la
  // même feuille — plus de 3 Mo.
  html = html.replace(
    /[ \t]*<link rel="stylesheet" href="assets\/css\/[a-z]+\.css">\n?/g, '');
  html = html.replace(/(<\/title>)/, `$1\n  <style>${JETON_CSS}</style>`);

  // Le module de page devient un script intégré, dépendances comprises.
  const moduleDePage = bles(modulesDeLaPage(nom, html), nom);
  // Tous les modules sont fondus dans un seul script ; les balises
  // d'origine disparaissent.
  html = html.replace(
    /[ \t]*<script type="module" src="assets\/js\/[a-z0-9-]+\.js"><\/script>\n?/g, '');
  html = html.replace(/([ \t]*)<\/body>/,
    `  <script type="module">\n${moduleDePage}\n  </script>\n$1</body>`);

  verifierSyntaxe(nom, moduleDePage);

  return html;
}

function bles(noms, page) {
  // Les modules d'entrée viennent en dernier ; leurs dépendances les
  // précèdent, chacune une seule fois, dans l'ordre d'évaluation.
  const entrees = Array.isArray(noms) ? noms : [noms];
  const vues = new Set();
  const ordre = [];
  for (const entree of entrees) dependances(entree, vues, ordre);
  const socle = ordre.filter((n) => !entrees.includes(n))
    .map(n => bloc(n, lire(`assets/js/${n}.js`))).join('\n');
  // Les jeux de données et les images sont dans la coquille, une seule
  // fois : data.js lit window.parent.__DONNEES_INTEGREES au lieu de faire
  // un fetch, et applique par-dessus les modifications faites dans le site.
  return `const __M = {};

${socle}

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

// Le charset vient EN TÊTE, avant tout le reste. Sans lui, le document ne
// se décode en UTF-8 que par chance : le premier <meta charset> du fichier
// est celui de la page index intégrée, et il ne tombe dans la fenêtre de
// pré-analyse de 1024 octets du navigateur que tant que rien de volumineux
// ne le précède. Servi en HTTP sans en-tête de charset, l'artefact
// mojibake — et la classe de caractères combinants écrite en clair dans
// sept modules devient une expression régulière invalide, ce qui tue tout
// le JavaScript du fichier.
const coquille = `<meta charset="utf-8">
<title>ETII Hub</title>
<style>
  html, body { height: 100%; margin: 0; background: #06080f; }
  #cadre { display: block; width: 100%; height: 100%; border: 0; }
</style>

<iframe id="cadre" title="ETII Hub"></iframe>

<script>
(function () {
  var PAGES = ${json(pagesAssemblees)};
  // La feuille de style, une seule fois pour les huit pages.
  var CSS = ${json(cssIntegre)};
  // Les jeux de données et les images, une seule fois : chaque page les lit
  // chez son parent (data.js, ui.js). Même origine, pas de copie.
  window.__DONNEES_INTEGREES = ${json(donneesAssemblees)};
  window.__IMAGES_INTEGREES = ${json(imagesDuSite())};
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
    ancre = ancre && ancre.charAt(0) === '#' ? ancre : '';
    try { history.replaceState(null, '', '#' + nom + ancre); } catch (e) {}
    // Fonction de remplacement, et non chaîne : un « $& » dans la feuille
    // serait interprété par String.replace s'il s'agissait d'une chaîne.
    var html = PAGES[nom].replace('${JETON_CSS}', function () { return CSS; });
    // Un lien vers « index.html#porteur=H160 » garde son ancre : elle est
    // posée dans l'adresse de la page avant que ses modules ne la lisent.
    // Pas de history.replaceState : dans un srcdoc, l'adresse relative se
    // résout contre celle de la coquille et le navigateur refuse ; un
    // location.replace vers « about:srcdoc#… » n'est qu'un saut d'ancre.
    // L'ancre attend chez la coquille : aucun texte venu d'un lien n'est
    // recopié dans un script.
    window.__ETII_ANCRE = ancre;
    if (ancre) {
      html = html.replace('<head>', function () {
        return '<head><script>try{var a=parent.__ETII_ANCRE;if(a)location.replace(location.href.split("#")[0]+a)}catch(e){}<\\/script>';
      });
    }
    cadre.srcdoc = html;
  }

  // Les liens internes du site changent de page sans quitter le fichier.
  cadre.addEventListener('load', function () {
    var doc;
    try { doc = cadre.contentDocument; } catch (e) { return; }
    if (!doc) return;

    doc.addEventListener('click', function (evt) {
      var lien = evt.target && evt.target.closest && evt.target.closest('a[href]');
      if (!lien) return;
      var href = lien.getAttribute('href');
      // Une ancre de la page (« #section-documents », « #q=… »). Dans un
      // srcdoc, elle se résout contre l'adresse de la COQUILLE : laissé
      // faire, le navigateur chargerait le fichier entier dans le cadre.
      // On fait donc le geste nous-mêmes : défiler jusqu'à l'élément s'il
      // existe, sinon poser l'ancre (la page suit son adresse).
      if (href && href.charAt(0) === '#') {
        if (evt.defaultPrevented) return;
        evt.preventDefault();
        var fragment = href.slice(1);
        if (!fragment) return;
        var cible = null;
        try { cible = doc.getElementById(decodeURIComponent(fragment)); } catch (e) { cible = null; }
        if (cible) { cible.scrollIntoView({ block: 'start' }); return; }
        try { cadre.contentWindow.location.hash = fragment; } catch (e) {}
        return;
      }
      var nom = nomDepuisHref(href);
      if (!nom) return;
      evt.preventDefault();
      var i = href.indexOf('#');
      var ancre = i >= 0 ? href.slice(i) : '';
      if (nom !== courante) { afficher(nom, ancre); return; }
      // Même page, autre ancre : la page suit son adresse (hashchange).
      if (ancre) { try { cadre.contentWindow.location.hash = ancre; } catch (e) {} }
    });
  });

  var brut = (location.hash || '').replace(/^#/, '');
  var coupe = brut.indexOf('#');
  var depart = (coupe >= 0 ? brut.slice(0, coupe) : brut).split('?')[0];
  afficher(PAGES[depart] ? depart : 'index', coupe >= 0 ? brut.slice(coupe) : '');
})();
</script>`;

/* La coquille elle-même : un « </script> » venu d'une chaîne la couperait
   en deux sans erreur de construction. On vérifie qu'elle tient d'un bloc
   et qu'elle se lit. */
{
  const debut = coquille.indexOf('<script>') + '<script>'.length;
  const corps = coquille.slice(debut, coquille.lastIndexOf('</script>'));
  if (/<\/script/i.test(corps)) throw new Error('La coquille contient un « </script> » : il faut l’échapper.');
  try { new Function(corps); } catch (e) { throw new Error('Script de la coquille invalide : ' + e.message); }
}

mkdirSync(join(RACINE, 'dist'), { recursive: true });
writeFileSync(join(RACINE, 'dist/etii-hub.html'), coquille);

// La taille est le seul chiffre qui compte au moment de publier : la limite
// est de 16 Mo et le projet se donne 15 Mo. Elle s'affiche ici, pas au pire
// moment, et l'alerte tombe à 13 Mo pour laisser deux photos de marge.
const octets = Buffer.byteLength(coquille);
const mo = octets / 1048576;
console.log(`dist/etii-hub.html : ${mo.toFixed(2)} Mo, ${PAGES.length} pages intégrées`);
if (mo > 13) {
  console.log(`\n  ⚠  ATTENTION — le fichier dépasse 13 Mo (plafond de publication : 15 Mo).`);
  console.log(`     Allégez avant de publier : les photos pèsent le plus lourd.\n`);
}
