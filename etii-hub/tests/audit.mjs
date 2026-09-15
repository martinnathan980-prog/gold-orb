// Audit statique du hub ETII — exécuter depuis etii-hub/ :
//   node tests/audit.mjs
// Vérifie les invariants structurels du projet : confidentialité,
// absence de dépendance, jetons CSS, sûreté du DOM, accessibilité de base.
// Aucune dépendance : Node seul suffit.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const RACINE = join(dirname(fileURLToPath(import.meta.url)), '..');
const lire = (p) => readFileSync(join(RACINE, p), 'utf8');
// Version sans commentaires : un motif interdit cité dans un commentaire
// explicatif ne doit pas être compté comme une infraction.
const lireSansCommentaires = (p) => lire(p)
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ');
const existe = (p) => existsSync(join(RACINE, p));

let ok = 0;
const echecs = [];
function verifier(nom, probleme) {
  // 'probleme' : chaîne décrivant l'échec, ou null si tout va bien.
  if (probleme) { echecs.push(`${nom}\n      ${probleme}`); console.log(`  ÉCHEC ${nom}`); }
  else { ok++; console.log(`  OK    ${nom}`); }
}

const pages = readdirSync(RACINE).filter(f => f.endsWith('.html'));
const cssFiles = existe('assets/css') ? readdirSync(join(RACINE,'assets/css')).map(f=>`assets/css/${f}`) : [];
const jsFiles  = existe('assets/js')  ? readdirSync(join(RACINE,'assets/js')).map(f=>`assets/js/${f}`)  : [];
const jsonFiles= existe('assets/data')? readdirSync(join(RACINE,'assets/data')).map(f=>`assets/data/${f}`): [];
const tous = [...pages, ...cssFiles, ...jsFiles];

console.log(`\n== Périmètre : ${pages.length} pages, ${cssFiles.length} CSS, ${jsFiles.length} JS, ${jsonFiles.length} JSON ==\n`);

// --- 1. Confidentialité -------------------------------------------------
console.log('== Confidentialité ==');
const INTERDITS = [
  [/airbus\.com/i,                'domaine d\'entreprise'],
  [/[a-z0-9._-]+@(?!example\.invalid)[a-z0-9.-]+\.[a-z]{2,}/i, 'adresse e-mail réelle'],
  [/sharepoint|\bplm\b|intranet/i,'référence à un système interne'],
  [/(docs|drive|sites)\.google\.com/i, 'URL Google interne'],
  [/[?&]id=[A-Za-z0-9_-]{20,}/,   'identifiant Drive'],
  [/\bH1(?!60\b|75\b)\d\d\b/,     'programme non public'],
];
for (const [motif, libelle] of INTERDITS) {
  const touches = [...tous, ...jsonFiles].filter(f => motif.test(lire(f)));
  verifier(`aucun ${libelle}`, touches.length ? `présent dans : ${touches.join(', ')}` : null);
}

// --- 2. Aucune dépendance externe --------------------------------------
console.log('\n== Indépendance ==');
// Une URL n'est une dépendance que si elle est CHARGÉE : attribut src/href,
// @import, url() ou import de module. Une URL citée dans un message affiché
// à l'utilisateur n'en est pas une.
const CHARGEMENT = /(?:\b(?:src|href)\s*=\s*["']|@import\s+["']|url\(\s*["']?|from\s+["'])https?:\/\/(?!example\.invalid)/;
const reseau = tous.filter(f => CHARGEMENT.test(lireSansCommentaires(f)));
verifier('aucune ressource distante chargée', reseau.length ? `références externes dans : ${reseau.join(', ')}` : null);
const libs = tous.filter(f => /jquery|bootstrap|fuse\.js|html2pdf|cdnjs|jsdelivr|unpkg/i.test(lireSansCommentaires(f)));
verifier('aucune bibliothèque tierce', libs.length ? `détectée dans : ${libs.join(', ')}` : null);

// --- 3. Patterns legacy interdits (SPEC §2) -----------------------------
console.log('\n== Patterns legacy bannis ==');
const scrollCache = [...cssFiles, ...pages].filter(f =>
  /scrollbar-width\s*:\s*none|::-webkit-scrollbar\s*\{[^}]*display\s*:\s*none/.test(lireSansCommentaires(f)));
verifier('barres de défilement jamais masquées',
  scrollCache.length ? `masquage dans : ${scrollCache.join(', ')}` : null);
const overflowForce = [...cssFiles, ...pages].filter(f =>
  /(html|body)[^{]*\{[^}]*overflow\s*:\s*hidden\s*!important/.test(lireSansCommentaires(f)));
verifier('pas d\'overflow:hidden!important sur html/body',
  overflowForce.length ? `présent dans : ${overflowForce.join(', ')}` : null);
const scaleCanvas = [...cssFiles, ...pages, ...jsFiles].filter(f =>
  /lockHeightResize|smartScale|scalable-canvas/.test(lireSansCommentaires(f)));
verifier('pas de mise en page par transform:scale()',
  scaleCanvas.length ? `résidu legacy dans : ${scaleCanvas.join(', ')}` : null);

// --- 4. Sûreté du DOM ---------------------------------------------------
console.log('\n== Sûreté du DOM ==');
const onattr = pages.filter(f => /\son(click|change|input|submit|load|mouseover)\s*=\s*["']/i.test(lire(f)));
verifier('aucun gestionnaire en attribut HTML',
  onattr.length ? `attributs on*= dans : ${onattr.join(', ')}` : null);
const innerHtml = jsFiles.filter(f => {
  // innerHTML = '' pour vider est toléré ; toute autre affectation ne l'est pas.
  const m = lire(f).match(/\.innerHTML\s*(\+?=)\s*(.*)/g) || [];
  return m.some(l => !/innerHTML\s*=\s*(''|""|``)\s*;?\s*$/.test(l.trim()));
});
verifier('aucune affectation innerHTML avec de la donnée',
  innerHtml.length ? `dans : ${innerHtml.join(', ')}` : null);
const evals = tous.filter(f => /\beval\s*\(|new\s+Function\s*\(/.test(lire(f)));
verifier('ni eval ni new Function', evals.length ? `dans : ${evals.join(', ')}` : null);

// --- 5. Jetons CSS ------------------------------------------------------
console.log('\n== Jetons CSS ==');
const brutes = cssFiles.filter(f => f !== 'assets/css/tokens.css')
  .filter(f => lireSansCommentaires(f).split('\n').some(l =>
    /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(l) && !/var\(|currentColor/.test(l)));
verifier('aucune couleur brute hors tokens.css',
  brutes.length ? `valeurs en dur dans : ${brutes.join(', ')}` : null);
// Les variables locales de composant (ex. .bouton--principal { --bouton-fond: … })
// sont un pattern légitime : on collecte TOUTE définition, pas seulement
// celles de tokens.css. Seule une variable utilisée sans être définie
// nulle part est une erreur.
const tokens = new Set();
for (const f of [...cssFiles, ...pages])
  for (const m of lireSansCommentaires(f).matchAll(/(--[a-z0-9-]+)\s*:/g)) tokens.add(m[1]);
const tokensGlobaux = new Set([...lire('assets/css/tokens.css').matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m=>m[1]));
const utilises = new Set();
for (const f of [...cssFiles, ...pages]) for (const m of lireSansCommentaires(f).matchAll(/var\((--[a-z0-9-]+)/g)) utilises.add(m[1]);
const inconnus = [...utilises].filter(t => !tokens.has(t));
verifier(`tous les var(--) sont définis (${tokensGlobaux.size} jetons globaux, ${tokens.size - tokensGlobaux.size} locaux, ${utilises.size} utilisés)`,
  inconnus.length ? `jetons utilisés mais jamais définis : ${inconnus.join(', ')}` : null);

// --- 6. Structure des pages --------------------------------------------
console.log('\n== Structure HTML ==');
for (const p of pages) {
  const h = lire(p);
  const soucis = [];
  const h1 = (h.match(/<h1[\s>]/g) || []).length;
  if (h1 !== 1) soucis.push(`${h1} <h1> au lieu de 1`);
  if (!/<html[^>]+lang\s*=\s*["']fr["']/.test(h)) soucis.push('lang="fr" absent');
  if (!/<meta[^>]+charset/i.test(h)) soucis.push('meta charset absent');
  if (!/<meta[^>]+name\s*=\s*["']viewport["']/i.test(h)) soucis.push('meta viewport absent');
  if (!/<title>[^<]+<\/title>/.test(h)) soucis.push('title vide ou absent');
  if (!/<main[\s>]/.test(h)) soucis.push('<main> absent');
  if (!/<nav[\s>]/.test(h)) soucis.push('<nav> absent');
  if (!/aria-current\s*=\s*["']page["']/.test(h)) soucis.push('aria-current="page" absent de la nav');
  verifier(`${p} : structure`, soucis.length ? soucis.join(' ; ') : null);
}

// --- 7. Références de fichiers ------------------------------------------
console.log('\n== Références ==');
for (const p of pages) {
  const h = lire(p);
  const refs = [...h.matchAll(/(?:href|src)\s*=\s*["'](?!https?:|#|mailto:|data:)([^"']+)["']/g)].map(m=>m[1]);
  const morts = refs.filter(r => !existe(r.split(/[?#]/)[0]));
  verifier(`${p} : ${refs.length} référence(s) locale(s)`,
    morts.length ? `introuvables : ${morts.join(', ')}` : null);
}
for (const j of jsFiles) {
  const imports = [...lire(j).matchAll(/from\s+["'](\.[^"']+)["']/g)].map(m=>m[1]);
  const morts = imports.filter(i => !existe(join('assets/js', i).replace(/^assets\/js\/\.\//,'assets/js/')));
  verifier(`${j} : ${imports.length} import(s)`, morts.length ? `introuvables : ${morts.join(', ')}` : null);
}

// --- 8. Données ---------------------------------------------------------
console.log('\n== Données ==');
for (const j of jsonFiles) {
  try { JSON.parse(lire(j)); verifier(`${j} : JSON valide`, null); }
  catch (e) { verifier(`${j} : JSON valide`, e.message); }
}

console.log(`\n${'='.repeat(58)}`);
console.log(`  ${ok} contrôles réussis, ${echecs.length} échec(s)`);
if (echecs.length) { console.log('='.repeat(58)); echecs.forEach((e,i)=>console.log(`\n  ${i+1}. ${e}`)); }
console.log('='.repeat(58));
process.exit(echecs.length ? 1 : 0);
