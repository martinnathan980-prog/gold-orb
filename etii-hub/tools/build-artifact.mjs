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

// Les photos des porteurs (flotte.json → `photo`) sont des fichiers image
// relatifs : dans un cadre srcdoc, rien ne les résout. Elles sont donc
// intégrées en data URI — mais seulement dans les pages qui affichent la
// flotte, sinon chaque page en porterait une copie. Un espace de pôle
// (pole.js) ne montre que ses propres porteurs : il n'embarque qu'eux.
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

// Une page n'embarque que les jeux de données que ses modules lisent
// (chargerDonnees('…') dans leurs sources) : la recherche n'a que faire de
// la flotte, la FAQ de l'organigramme. Les communications suivent leur
// module, qui les lit par sa propre fonction.
// Le sélecteur « Rechercher partout » (palette.js) lit ses jeux par une
// liste, pas par des appels littéraux : on la reprend telle quelle.
const JEUX_PALETTE = ['documents', 'faq', 'organigramme', 'reunions', 'flotte', 'communications'];

function jeuxUtilises(noms) {
  const jeux = new Set();
  for (const n of noms) {
    const source = lire(`assets/js/${n}.js`);
    for (const m of source.matchAll(/chargerDonnees\(\s*['"]([a-z0-9_-]+)['"]/g)) jeux.add(m[1]);
    if (n === 'communications') jeux.add('communications');
    if (n === 'palette') JEUX_PALETTE.forEach((j) => jeux.add(j));
  }
  return jeux;
}

// La flotte pèse surtout par ses fiches détaillées, que seul le tableau de
// bord (porteurs.js) déplie. Ailleurs — un espace de pôle, le sélecteur —
// on ne garde de la fiche que ce qui se lit ou se cherche.
function flotteAllegee(flotte) {
  const copie = JSON.parse(JSON.stringify(flotte));
  copie.flotte = (Array.isArray(copie.flotte) ? copie.flotte : []).map((a) => {
    if (!a || typeof a !== 'object' || !a.fiche || typeof a.fiche !== 'object') return a;
    const f = a.fiche;
    return { ...a, fiche: {
      nom: f.nom, segment: f.segment, ancienNom: f.ancienNom, resume: f.resume,
      insolites: (Array.isArray(f.insolites) ? f.insolites : []).map((i) => ({ texte: i && i.texte }))
    } };
  });
  return copie;
}

function donneesAvecImages(noms) {
  const utiles = jeuxUtilises(noms);
  const copie = Object.fromEntries(Object.entries(donneesAssemblees).filter(([n]) => utiles.has(n)));
  if (copie.flotte && !noms.includes('porteurs')) copie.flotte = flotteAllegee(copie.flotte);
  // Seul le tableau de bord (porteurs.js) montre les photos de la flotte :
  // un espace de pôle n'en affiche plus depuis que « Porteurs du pôle » a
  // disparu, il n'a donc rien à embarquer.
  if (noms.includes('porteurs')) {
    const flotte = JSON.parse(JSON.stringify(copie.flotte || donneesAssemblees.flotte));
    for (const appareil of (Array.isArray(flotte.flotte) ? flotte.flotte : [])) {
      const uri = dataUri(String(appareil.photo || '').trim());
      if (uri) appareil.photo = uri;
    }
    copie.flotte = flotte;
  }
  if (noms.includes('kiosque')) {
    const comms = JSON.parse(JSON.stringify(donneesAssemblees.communications));
    const entrees = [comms.motDuChef].concat(comms.annonces || [], comms.agenda || []).filter(Boolean);
    // L'image à plat d'une entrée, et celles de ses blocs libres (une
    // image, ou les diapositives d'une galerie) : toutes deviennent des
    // data URI, sinon rien ne les résout dans un cadre srcdoc.
    for (const e of entrees) {
      const blocs = Array.isArray(e.blocs) ? e.blocs : [];
      const images = [e.image].concat(blocs.flatMap((b) => {
        if (!b || typeof b !== 'object') return [];
        if (b.type === 'image') return [b];
        if (b.type === 'galerie') return Array.isArray(b.images) ? b.images : [];
        return [];
      }));
      for (const im of images) {
        if (!im || typeof im !== 'object') continue;
        const uri = dataUri(String(im.src || '').trim());
        if (uri) im.src = uri;
      }
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

// Les communications : une feuille configurée se lit comme sur le site ;
// sinon le fichier intégré, sans fetch.
if (__M["communications"] && typeof __M["communications"].chargerCommunications === 'function') {
  const chargerReseau = __M["communications"].chargerCommunications;
  __M["communications"].chargerCommunications = function () {
    const source = __M["communications"].SOURCE || {};
    if (String(source.url || '').trim()) return chargerReseau();
    return Promise.resolve(Object.assign({}, __DONNEES.communications, { origine: 'fichier' }));
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
  var CSS = ${json(cssAssemble)};
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
    // Fonction de remplacement, et non chaîne : un « $& » dans la feuille
    // serait interprété par String.replace s'il s'agissait d'une chaîne.
    cadre.srcdoc = PAGES[nom].replace('${JETON_CSS}', function () { return CSS; });
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
