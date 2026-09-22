// Audit statique du hub ETII — exécuter depuis etii-hub/ :
//   node tests/audit.mjs
// Vérifie les invariants structurels du projet : confidentialité,
// absence de dépendance, jetons CSS, sûreté du DOM, accessibilité de base.
// Aucune dépendance : Node seul suffit.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const RACINE = join(dirname(fileURLToPath(import.meta.url)), '..');
// Mémorisé : dist/etii-hub.html pèse dix mégaoctets et chaque motif interdit
// relit tout le périmètre.
const luParChemin = new Map();
const lire = (p) => {
  if (!luParChemin.has(p)) luParChemin.set(p, readFileSync(join(RACINE, p), 'utf8'));
  return luParChemin.get(p);
};
// Version sans commentaires : un motif interdit cité dans un commentaire
// explicatif ne doit pas être compté comme une infraction.
const lireSansCommentaires = (p) => lire(p)
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ');
const existe = (p) => existsSync(join(RACINE, p));

let ok = 0;
const echecs = [];
const avertissements = [];
function verifier(nom, probleme) {
  // 'probleme' : chaîne décrivant l'échec, ou null si tout va bien.
  if (probleme) { echecs.push(`${nom}\n      ${probleme}`); console.log(`  ÉCHEC ${nom}`); }
  else { ok++; console.log(`  OK    ${nom}`); }
}
// Un AVERTISSEMENT nomme une dérive qui n'a encore rien cassé. Il ne met
// jamais l'audit au rouge : un contrôle qui rougit sur une saisie légitime
// apprend à ignorer la sortie, et le lecteur de ce script n'est pas
// développeur.
function avertir(nom, souci) {
  if (souci) { avertissements.push(`${nom}\n      ${souci}`); console.log(`  ⚠     ${nom}`); }
  else { ok++; console.log(`  OK    ${nom}`); }
}

const pages = readdirSync(RACINE).filter(f => f.endsWith('.html'));
const cssFiles = existe('assets/css') ? readdirSync(join(RACINE,'assets/css')).map(f=>`assets/css/${f}`) : [];
const jsFiles  = existe('assets/js')  ? readdirSync(join(RACINE,'assets/js')).map(f=>`assets/js/${f}`)  : [];
const jsonFiles= existe('assets/data')? readdirSync(join(RACINE,'assets/data')).filter(f => f.endsWith('.json')).map(f=>`assets/data/${f}`): [];
const tous = [...pages, ...cssFiles, ...jsFiles];

console.log(`\n== Périmètre : ${pages.length} pages, ${cssFiles.length} CSS, ${jsFiles.length} JS, ${jsonFiles.length} JSON ==\n`);

// --- 1. Confidentialité -------------------------------------------------
console.log('== Confidentialité ==');

// L'utilisateur DOIT coller son URL de raccordement dans sa copie locale
// avant de fabriquer dist/. Sans échappatoire, l'audit serait rouge
// précisément à ce moment-là, et la règle « les tests restent verts »
// deviendrait intenable. ETII_RACCORDE=1 désarme les seuls contrôles qui
// portent sur le raccordement ; il n'en désarme aucun autre.
const RACCORDE = process.env.ETII_RACCORDE === '1';
const AIDE_RACCORDE =
  '\n      Copie locale raccordée ? ETII_RACCORDE=1 node tests/audit.mjs — '
  + 'mais ne commitez ni ce fichier ni le dist/ fabriqué depuis lui.';

// dist/etii-hub.html est SUIVI par git et c'est le fichier réellement
// republié à chaque tour : une URL de raccordement y voyage aussi, encodée
// dans les pages intégrées. Il entre donc dans le périmètre scanné.
const livrables = ['dist/etii-hub.html'].filter(existe);

// Le troisième élément marque un motif « de raccordement », désarmable.
const INTERDITS = [
  // Le site PUBLIC www.airbus.com est une source citable : les fiches des
  // porteurs s'appuient dessus. Tout le reste — sous-domaine, adresse de
  // courriel, chemin interne — reste interdit.
  [/(?<!https:\/\/www\.)airbus\.com/i, 'domaine d\'entreprise hors site public'],
  [/[a-z0-9._-]+@(?!example\.invalid)[a-z0-9.-]+\.[a-z]{2,}/i, 'adresse e-mail réelle'],
  [/sharepoint|\bplm\b|intranet/i,'référence à un système interne'],
  [/(docs|drive|sites)\.google\.com/i, 'URL Google interne', true],
  // La forme /exec d'une web app Apps Script est précisément celle que les
  // modes d'emploi recommandent quand la publication sur le web est
  // interdite : c'est la seule qui passait jusqu'ici. Une URL /exec de
  // publication est une URL-capacité — elle ÉCRIT dans la feuille du
  // service, et elle part aussi dans dist/etii-hub.html, qui est publié.
  [/script\.google\.com/i, 'URL Apps Script (point de raccordement, à ne jamais commiter)', true],
  [/AKfyc[A-Za-z0-9_-]{20,}/, 'identifiant de web app Apps Script', true],
  [/[?&]id=[A-Za-z0-9_-]{20,}/,   'identifiant Drive'],
  // Gamme civile publique d'Airbus Helicopters. Toute autre désignation
  // en H suivi de trois chiffres est refusée : militaire, prototype ou
  // programme interne n'ont rien à faire dans un dépôt public.
  // Gamme publique d'Airbus Helicopters, civile et militaire. Le suffixe M
  // est pris en compte : sans lui, « H225M » échappait au contrôle par un
  // simple effet de bord de la limite de mot.
  [/\bH(?!(?:125|130|135|145|160|175|215|225)M?\b)\d{3}M?\b/, 'programme non public'],
];
for (const [motif, libelle, raccordement] of INTERDITS) {
  const touches = (raccordement && RACCORDE) ? []
    : [...tous, ...jsonFiles, ...livrables].filter(f => motif.test(lire(f)));
  verifier(`aucun ${libelle}`,
    touches.length
      ? `présent dans : ${touches.join(', ')}` + (raccordement ? AIDE_RACCORDE : '')
      : null);
}

// Les URL de raccordement sont couvertes par les motifs ci-dessus. La clé
// partagée, elle, est une chaîne arbitraire que l'utilisateur invente :
// aucun motif ne peut l'attraper, d'où ce contrôle dédié.
{
  const chemin = 'assets/js/communications.js';
  let souci = null;
  if (!existe(chemin)) souci = `${chemin} introuvable`;
  else if (!RACCORDE) {
    const m = /\bcle\s*:\s*'([^']*)'/.exec(lireSansCommentaires(chemin));
    if (!m) souci = 'SOURCE.cle introuvable — le contrôle ne voit plus ce qu\'il surveille';
    else if (m[1] !== '') souci = `SOURCE.cle vaut une valeur non vide` + AIDE_RACCORDE;
  }
  verifier(`${chemin} : SOURCE.cle est la chaîne vide`, souci);
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
// Le fichier de PALETTE a le droit de porter des valeurs brutes : c'est
// son rôle. Tout le reste passe par var(--…).
const FICHIERS_PALETTE = ['assets/css/tokens.css'];
const brutes = cssFiles.filter(f => !FICHIERS_PALETTE.includes(f))
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

// --- 5b. Parité des deux blocs sombres ----------------------------------
// La règle est écrite depuis toujours : « un nouveau jeton se déclare en
// clair ET dans les deux blocs sombres, à l'identique ». Elle était tenue à
// la main, et elle a été enfreinte : --fond-bande manquait du bloc
// explicite, ce qui affichait le titre du site à 1,17:1 sur huit pages dès
// que l'OS était en clair et le thème choisi sombre.
//
// L'extraction se fait par COMPTAGE D'ACCOLADES depuis le sélecteur, jamais
// par plages de lignes : base.css rouvre « :root, :root[data-theme] » dans
// un @media print, et une extraction naïve le compterait.
function blocDe(source, motif) {
  const m = motif.exec(source);
  if (!m) return null;
  const debut = source.indexOf('{', m.index);
  if (debut < 0) return null;
  let profondeur = 0;
  for (let i = debut; i < source.length; i += 1) {
    if (source[i] === '{') profondeur += 1;
    else if (source[i] === '}' && --profondeur === 0) return source.slice(debut + 1, i);
  }
  return null;
}
function jetonsDe(bloc) {
  const d = new Map();
  if (bloc) for (const m of bloc.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) d.set(m[1], m[2].trim());
  return d;
}

const sourceJetons = lireSansCommentaires('assets/css/tokens.css');
const BLOCS = {
  clair:  blocDe(sourceJetons, /(?:^|\n):root\s*\{/),
  media:  blocDe(sourceJetons, /:root:not\(\[data-theme="clair"\]\)\s*\{/),
  sombre: blocDe(sourceJetons, /:root\[data-theme="sombre"\]\s*\{/)
};
const JETONS = {
  clair:  jetonsDe(BLOCS.clair),
  media:  jetonsDe(BLOCS.media),
  sombre: jetonsDe(BLOCS.sombre)
};

{
  const absents = Object.entries(BLOCS).filter(([, b]) => b === null).map(([n]) => n);
  if (absents.length) {
    verifier('tokens.css : les trois blocs de thème sont lisibles',
      `bloc(s) introuvable(s) : ${absents.join(', ')} — le sélecteur a changé, `
      + 'les contrôles de parité et de contraste ne voient plus rien');
  } else {
    const manquePartout = (source, cible) =>
      [...source.keys()].filter(k => !cible.has(k));
    const divergents = [...JETONS.media.keys()]
      .filter(k => JETONS.sombre.has(k) && JETONS.sombre.get(k) !== JETONS.media.get(k))
      .map(k => `${k} (@media « ${JETONS.media.get(k)} » ≠ explicite « ${JETONS.sombre.get(k)} »)`);
    const soucis = [];
    const versExplicite = manquePartout(JETONS.media, JETONS.sombre);
    const versMedia = manquePartout(JETONS.sombre, JETONS.media);
    if (versExplicite.length)
      soucis.push(`absents du bloc explicite :root[data-theme="sombre"] : ${versExplicite.join(', ')}`);
    if (versMedia.length)
      soucis.push(`absents du bloc @media (prefers-color-scheme: dark) : ${versMedia.join(', ')}`);
    if (divergents.length)
      soucis.push(`valeurs divergentes : ${divergents.join(' ; ')}`);
    verifier(
      `les deux blocs sombres déclarent les mêmes jetons aux mêmes valeurs `
      + `(${JETONS.media.size} dans le @media, ${JETONS.sombre.size} dans l'explicite)`,
      soucis.length
        ? soucis.join('\n      ')
          + '\n      Recopier la ligne manquante à l\'identique dans l\'autre bloc de tokens.css.'
        : null);
  }
}

// --- 5c. Contraste des textes sur les fonds -----------------------------
// Arithmétique pure, sans navigateur : luminance relative WCAG. Produit
// croisé complet plutôt que liste choisie — moins de code, et toute paire
// future est couverte d'avance sans qu'une table se périme en silence.
function canal(v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
function luminance({ r, g, b }) {
  return 0.2126 * canal(r / 255) + 0.7152 * canal(g / 255) + 0.0722 * canal(b / 255);
}
function contraste(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
function surFond(couleur, fond) {
  // Une couleur translucide ne veut rien dire tant qu'elle n'est pas posée
  // sur son fond : on la compose avant de mesurer.
  if (couleur.a >= 1) return couleur;
  return {
    r: couleur.r * couleur.a + fond.r * (1 - couleur.a),
    g: couleur.g * couleur.a + fond.g * (1 - couleur.a),
    b: couleur.b * couleur.a + fond.b * (1 - couleur.a),
    a: 1
  };
}
function lireCouleur(valeur) {
  if (!valeur) return null;
  const t = valeur.trim();
  let m = /^#([0-9a-f]{3,8})$/i.exec(t);
  if (m) {
    let h = m[1];
    if (h.length === 3 || h.length === 4) h = [...h].map(c => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    return {
      r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
      a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1
    };
  }
  m = /^rgba?\(([^)]+)\)$/i.exec(t);
  if (!m) return null;
  const parts = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
  if (parts.length < 3 || parts.some(Number.isNaN)) return null;
  return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
}
// Un jeton non redéfini par un bloc sombre garde sa valeur claire : c'est
// exactement le mécanisme qui a laissé passer --fond-bande.
function valeurJeton(nom, theme) {
  let courant = nom;
  for (let i = 0; i < 12; i += 1) {
    const brut = JETONS[theme].has(courant) ? JETONS[theme].get(courant)
      : JETONS.clair.has(courant) ? JETONS.clair.get(courant) : null;
    if (brut === null) return null;
    const m = /^var\(\s*(--[a-z0-9-]+)\s*\)$/.exec(brut);
    if (!m) return brut;
    courant = m[1];
  }
  return null;
}
function couleurJeton(nom, theme) { return lireCouleur(valeurJeton(nom, theme)); }

if (BLOCS.clair && BLOCS.media && BLOCS.sombre) {
  const TEXTES = ['--texte', '--texte-doux', '--texte-faible'];
  const FONDS = ['--fond', '--fond-bande', '--fond-eleve', '--fond-enfonce', '--fond-profond'];
  const SEUIL = 4.5;
  const THEMES = { clair: 'clair', media: '@media sombre', sombre: 'thème sombre explicite' };
  const faibles = [];
  const introuvables = [];
  for (const theme of Object.keys(THEMES)) {
    const page = couleurJeton('--fond', theme);
    for (const nf of FONDS) {
      const brut = couleurJeton(nf, theme);
      if (!brut) { introuvables.push(`${nf} (${THEMES[theme]})`); continue; }
      const fond = surFond(brut, page || { r: 255, g: 255, b: 255, a: 1 });
      for (const nt of TEXTES) {
        const brutTexte = couleurJeton(nt, theme);
        if (!brutTexte) { introuvables.push(`${nt} (${THEMES[theme]})`); continue; }
        const r = contraste(surFond(brutTexte, fond), fond);
        if (r < SEUIL) faibles.push(`${nt} sur ${nf} en ${THEMES[theme]} : ${r.toFixed(2)}:1`);
      }
    }
  }
  const soucis = [];
  if (introuvables.length) soucis.push(`jetons illisibles : ${[...new Set(introuvables)].join(', ')}`);
  if (faibles.length) soucis.push(`sous ${SEUIL}:1 — ${[...new Set(faibles)].join(' ; ')}`);
  verifier(
    `les ${TEXTES.length * FONDS.length * 3} couples texte/fond tiennent ${SEUIL}:1 dans les trois thèmes`,
    soucis.length ? soucis.join('\n      ') : null);

  // Sans cet écart, une valeur qui aplatit la hiérarchie à deux niveaux
  // passerait sans broncher : --texte-faible a déjà été à 1,07:1 de
  // --texte-doux, deux gris que plus personne ne distinguait.
  const ECART = 1.25;
  const plats = [];
  for (const theme of Object.keys(THEMES)) {
    const doux = couleurJeton('--texte-doux', theme);
    const faible = couleurJeton('--texte-faible', theme);
    if (!doux || !faible) continue;
    const r = contraste(doux, faible);
    if (r < ECART) plats.push(`${THEMES[theme]} : ${r.toFixed(2)}:1`);
  }
  verifier(`--texte-doux et --texte-faible restent distincts (${ECART}:1 au moins)`,
    plats.length ? `hiérarchie aplatie — ${plats.join(' ; ')}` : null);
}

// --- 5d. Les classes fabriquées par ui.js sont stylées ------------------
// Un seul contrôle GLOBAL, jamais un par page : les huit pages chargent les
// mêmes six feuilles, donc une boucle produirait huit résultats qui ne
// peuvent pas diverger — et elle accepterait le mauvais correctif, recoller
// le CSS dans six <style> en ligne, c'est-à-dire la duplication même qui a
// cassé les toasts sur six pages sur huit.
{
  const classesUi = new Set();
  const srcUi = lireSansCommentaires('assets/js/ui.js');
  for (const m of srcUi.matchAll(/class:\s*'([^']+)'/g))
    for (const c of m[1].split(/\s+/)) if (c) classesUi.add(c);
  for (const m of srcUi.matchAll(/class:\s*\[([^\]]+)\]/g))
    for (const part of m[1].split(',')) {
      // Littéral PUR seulement : 'toast--' + nom est un opérande de
      // concaténation, donc écarté d'office.
      const q = /^'([^']+)'$/.exec(part.trim());
      if (q) for (const c of q[1].split(/\s+/)) if (c) classesUi.add(c);
    }
  const cssUi = cssFiles.map(lireSansCommentaires).join('\n');
  const orphelines = [...classesUi].filter(c =>
    !new RegExp('\\.' + c.replace(/-/g, '\\-') + '(?![\\w-])').test(cssUi));
  verifier(`les ${classesUi.size} classes fabriquées par ui.js sont stylées dans assets/css`,
    orphelines.length
      ? `aucun sélecteur pour : ${orphelines.join(', ')}`
        + '\n      ui.js est partagé : son CSS doit l\'être aussi, dans assets/css et non '
        + 'dans un <style> de page.'
      : null);

  // Non-régression : l'ancien nom du composant ne doit pas revenir.
  const anciens = cssFiles.filter(f => /\.notification(?![\w-])/.test(lireSansCommentaires(f)));
  verifier('aucun résidu de l\'ancien nom .notification dans assets/css',
    anciens.length ? `présent dans : ${anciens.join(', ')} — le composant s'appelle .toast` : null);

  // Non-régression : et il ne doit pas être recollé page par page.
  const enLigne = pages.filter(p =>
    (lire(p).match(/<style[\s\S]*?<\/style>/g) || [])
      .some(bloc => /\.toast(?![\w-])/.test(bloc)));
  verifier('aucune règle .toast dans un <style> de page',
    enLigne.length
      ? `copie en ligne dans : ${enLigne.join(', ')} — la règle appartient à assets/css`
      : null);
}

// --- 5e. Un libellé ne se masque pas en display: none -------------------
// display: none retire l'élément de l'arbre d'accessibilité : le bouton
// perd son nom au lieu de perdre son texte visible.
{
  const fautifs = [];
  for (const f of [...cssFiles, ...pages])
    for (const m of lireSansCommentaires(f).matchAll(/([^{}]*__libelle)\s*\{([^}]*)\}/g))
      if (/display\s*:\s*none/.test(m[2])) fautifs.push(`${f} — ${m[1].trim().split(/\s*,\s*/).pop()}`);
  verifier('aucun display: none sur un sélecteur en __libelle',
    fautifs.length
      ? `${fautifs.join(' ; ')}\n      Utiliser la classe « visuellement-cache » de base.css : elle retire `
        + 'le texte de l\'écran en le laissant dans le nom accessible du bouton.'
      : null);
}

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
  // Une page hors navigation (admin.html) n'a, par construction, aucune
  // entrée courante : elle le déclare sur <body data-hors-navigation>.
  const horsNav = /<body[^>]*\sdata-hors-navigation[\s>]/.test(h);
  if (!horsNav && !/aria-current\s*=\s*["']page["']/.test(h)) soucis.push('aria-current="page" absent de la nav');
  verifier(`${p} : structure`, soucis.length ? soucis.join(' ; ') : null);
}


// --- 6b. Cohérence de la navigation --------------------------------------
// Neuf pages doivent porter exactement le même en-tête. Une divergence ne
// casse rien visiblement, mais déplace un lien d'une page à l'autre.
console.log('\n== Navigation partagée ==');
if (pages.length) {
  const signature = (h) => {
    const nav = h.match(/<nav class="site-nav"[\s\S]*?<\/nav>/);
    if (!nav) return null;
    return [...nav[0].matchAll(/<a[^>]+href="([^"]+)"[^>]*>([^<]*)<\/a>/g)]
      .map(m => `${m[1]}|${m[2].trim()}`).join(' · ');
  };
  const refPage = pages.includes('index.html') ? 'index.html' : pages[0];
  const ref = signature(lire(refPage));
  verifier(`${refPage} : navigation présente`, ref ? null : '<nav class="site-nav"> introuvable');
  if (ref) {
    const divergentes = pages.filter(p => p !== refPage && signature(lire(p)) !== ref);
    verifier(`les ${pages.length} pages partagent la même navigation`,
      divergentes.length
        ? `divergent de ${refPage} : ${divergentes.join(', ')}`
        : null);
    verifier('la navigation couvre le service et les trois pôles',
      ['index.html','etiia.html','etiie.html','etiii.html','docsearch.html']
        .every(c => ref.includes(c + '|'))
        ? null : `liens attendus manquants dans : ${ref}`);
  }
  // Chaque page marque exactement une entrée courante.
  for (const p of pages) {
    const h = lire(p);
    const attendu = /<body[^>]*\sdata-hors-navigation[\s>]/.test(h) ? 0 : 1;
    const n = (h.match(/aria-current="page"/g) || []).length;
    if (n !== attendu) verifier(`${p} : ${attendu ? 'une seule' : 'aucune'} entrée courante`, `${n} aria-current="page"`);
  }
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


// --- 7b. Symboles importés -----------------------------------------------
// Vérifier que le FICHIER importé existe ne suffit pas : un import portant
// sur un symbole que le module n'exporte pas casse la page entière au
// chargement, sans que rien d'autre ne le signale.
console.log('\n== Symboles importés ==');
const exportsPar = new Map();
for (const j of jsFiles) {
  const noms = new Set();
  const src = lireSansCommentaires(j);
  for (const m of src.matchAll(/export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z0-9_$]+)/g))
    noms.add(m[1]);
  for (const m of src.matchAll(/export\s*\{([^}]*)\}/g))
    for (const part of m[1].split(','))
      { const n = part.trim().split(/\s+as\s+/).pop().trim(); if (n) noms.add(n); }
  exportsPar.set(j.replace('assets/js/',''), noms);
}
for (const j of jsFiles) {
  const manquants = [];
  for (const m of lireSansCommentaires(j).matchAll(/import\s*\{([^}]*)\}\s*from\s*["']\.\/([^"']+)["']/g)) {
    const cible = m[2];
    const dispo = exportsPar.get(cible);
    if (!dispo) { manquants.push(`module ${cible} introuvable`); continue; }
    for (const part of m[1].split(',')) {
      const nom = part.trim().split(/\s+as\s+/)[0].trim();
      if (nom && !dispo.has(nom)) manquants.push(`${nom} absent de ${cible}`);
    }
  }
  verifier(`${j} : symboles importés résolus`, manquants.length ? manquants.join(' ; ') : null);
}

// --- 8. Données ---------------------------------------------------------
console.log('\n== Données ==');
const donnees = {};
for (const j of jsonFiles) {
  try { donnees[j.replace('assets/data/', '').replace('.json', '')] = JSON.parse(lire(j)); verifier(`${j} : JSON valide`, null); }
  catch (e) { verifier(`${j} : JSON valide`, e.message); }
}

// --- 8b. Cohérence des données ------------------------------------------
// Les fichiers sont joints entre eux par des CHAÎNES : un document désigne
// son porteur par son nom affiché, un document déclare un type qui doit
// exister dans les facettes. Rien ne le vérifiait. Un « Personne 7 » pour
// « Personne 07 » fait disparaître les documents de cette personne en
// silence — pas d'erreur, pas de page blanche, juste « Documents portés 0 ».
//
// Deux niveaux : ERREUR là où la perte est silencieuse et certaine,
// AVERTISSEMENT ailleurs.
console.log('\n== Cohérence des données ==');
const liste = (v) => (Array.isArray(v) ? v : []);
const chaine = (v) => (typeof v === 'string' ? v.trim() : '');

const org = donnees.organigramme;
const docs = donnees.documents;
const flotte = donnees.flotte;
const faq = donnees.faq;

// Tous les noms de personnes de l'organigramme, et tous leurs identifiants.
const personnes = [];
if (org) {
  if (org.direction) personnes.push(org.direction);
  for (const p of liste(org.poles)) {
    if (p.responsable) personnes.push(p.responsable);
    for (const s of liste(p.squads)) {
      if (s.lead) personnes.push(s.lead);
      for (const m of liste(s.membres)) personnes.push(m);
    }
  }
}
const nomsPersonnes = new Set(personnes.map(p => chaine(p && p.nom)).filter(Boolean));

if (org) {
  const vus = new Set(); const doubles = [];
  for (const p of personnes) {
    const id = chaine(p && p.id);
    if (!id) continue;
    if (vus.has(id)) doubles.push(id); else vus.add(id);
  }
  verifier(`organigramme.json : les ${vus.size} identifiants de personne sont uniques`,
    doubles.length ? `en double : ${[...new Set(doubles)].join(', ')}` : null);
}

if (docs && org) {
  // ERREUR 1 — la jointure par nom, celle qui perd des documents en silence.
  const orphelins = liste(docs.documents)
    .filter(d => !nomsPersonnes.has(chaine(d.porteur)))
    .map(d => `${chaine(d.id) || '(sans id)'} → porteur « ${chaine(d.porteur)} »`);
  verifier(`documents.json : les ${liste(docs.documents).length} porteurs existent dans organigramme.json`,
    orphelins.length
      ? `${orphelins.join(' ; ')}\n      La jointure se fait par égalité du nom affiché : `
        + 'un nom qui ne correspond pas fait disparaître ses documents sans erreur.'
      : null);
}

if (docs) {
  // ERREUR 2 — les valeurs déclarées font foi : hors facette, le document
  // sort des filtres sans que rien ne le dise.
  const facettes = docs.facettes || {};
  const paires = [
    ['type', 'types', d => [chaine(d.type)]],
    ['metier', 'metiers', d => liste(d.metier).map(chaine)],
    ['pole', 'poles', d => [chaine(d.pole)]],
    ['perimetre', 'perimetres', d => [chaine(d.perimetre)]]
  ];
  const hors = [];
  for (const [champ, facette, extraire] of paires) {
    const connues = new Set(liste(facettes[facette]).map(chaine));
    for (const d of liste(docs.documents))
      for (const v of extraire(d).filter(Boolean))
        if (!connues.has(v)) hors.push(`${chaine(d.id)} : ${champ} « ${v} » absent de facettes.${facette}`);
  }
  verifier('documents.json : chaque valeur de filtre est déclarée dans les facettes',
    hors.length
      ? `${[...new Set(hors)].join(' ; ')}\n      Ajouter la valeur dans documents.json → facettes, `
        + 'sinon le document reste trouvable au texte mais sort des filtres.'
      : null);

  // ERREUR 3 — références et identifiants uniques.
  for (const champ of ['reference', 'id']) {
    const vus = new Set(); const doubles = [];
    for (const d of liste(docs.documents)) {
      const v = chaine(d[champ]);
      if (!v) continue;
      if (vus.has(v)) doubles.push(v); else vus.add(v);
    }
    verifier(`documents.json : les ${vus.size} valeurs de « ${champ} » sont uniques`,
      doubles.length ? `en double : ${[...new Set(doubles)].join(', ')}` : null);
  }

  // ERREUR 4 — le successeur déclaré, quand il existe. Un seul invariant
  // interdit d'un coup l'auto-référence, les cycles et les chaînes à
  // plusieurs sauts : il n'y a jamais qu'une version en vigueur.
  const parId = new Map(liste(docs.documents).map(d => [chaine(d.id), d]));
  const porteursRemplacement = liste(docs.documents).filter(d => chaine(d.remplacePar));
  const soucis = [];
  for (const d of porteursRemplacement) {
    const cible = chaine(d.remplacePar);
    if (!parId.has(cible)) { soucis.push(`${chaine(d.id)} → « ${cible} » n'existe pas`); continue; }
    if (cible === chaine(d.id)) { soucis.push(`${chaine(d.id)} se remplace lui-même`); continue; }
    if (chaine(parId.get(cible).remplacePar))
      soucis.push(`${chaine(d.id)} → ${cible}, qui est lui-même remplacé — la version en vigueur est unique`);
  }
  verifier(`documents.json : les ${porteursRemplacement.length} renvois « remplacePar » désignent une version en vigueur`,
    soucis.length ? soucis.join(' ; ') : null);
}

if (flotte) {
  // ERREUR 5 — une photo sans phrase décrivant ce qu'on y voit. Pas un
  // booléen : « verifie: true » se coche par réflexe en recopiant la ligne
  // du dessus, une phrase ne s'écrit pas sans avoir ouvert le fichier. Le
  // garde-fou manquant le jour où le H225M s'est retrouvé illustré par la
  // photo d'un caracal — le félin — apparié sur son surnom.
  const sansVu = liste(flotte.flotte)
    .filter(a => a && chaine(a.photo))
    .filter(a => !chaine((a.credit || {}).vu))
    .map(a => chaine(a.code));
  verifier('flotte.json : chaque appareil qui a une photo dit ce qu\'on y voit (credit.vu)',
    sansVu.length
      ? `credit.vu vide ou absent sur : ${sansVu.join(', ')}`
        + '\n      Ouvrir l\'image et écrire une phrase : « H175 au sol au Bourget, trois quarts avant ».'
      : null);
}

// AVERTISSEMENTS — la dérive est nommée, rien n'est cassé, l'audit ne
// passe pas au rouge devant quelqu'un qui n'est pas développeur.
if (org && flotte) {
  const codes = new Map(liste(flotte.flotte).map(a => [chaine(a.code).toLowerCase(), chaine(a.code)]));
  codes.set('transverse', 'Transverse');
  const inconnus = []; const casse = [];
  for (const p of personnes) {
    const v = chaine(p && p.perimetre);
    if (!v) continue;
    const exact = codes.get(v.toLowerCase());
    if (exact === undefined) inconnus.push(`${chaine(p.id)} : « ${v} »`);
    else if (exact !== v) casse.push(`« ${v} » pour « ${exact} »`);
  }
  const souci = [];
  if (inconnus.length) souci.push(`périmètre inconnu de flotte.json : ${[...new Set(inconnus)].join(', ')}`);
  if (casse.length) souci.push(`casse différente de flotte.json : ${[...new Set(casse)].join(', ')}`);
  avertir('organigramme.json : les périmètres des personnes suivent flotte.json',
    souci.length ? souci.join(' ; ') : null);
}

if (faq && org) {
  const codesPole = new Set(['ETII', ...liste(org.poles).map(p => chaine(p.pole))]);
  const hors = liste(faq.questions)
    .filter(q => chaine(q.pole) && !codesPole.has(chaine(q.pole)))
    .map(q => `${chaine(q.id)} : « ${chaine(q.pole)} »`);
  avertir('faq.json : chaque question vise ETII ou un pôle existant',
    hors.length
      ? `${[...new Set(hors)].join(', ')} — la question reste visible au niveau service, `
        + 'mais elle ne remontera dans aucun espace de pôle'
      : null);
}

console.log(`\n${'='.repeat(58)}`);
console.log(`  ${ok} contrôles réussis, ${echecs.length} échec(s)`
  + (avertissements.length ? `, ${avertissements.length} avertissement(s)` : ''));
if (echecs.length) { console.log('='.repeat(58)); echecs.forEach((e,i)=>console.log(`\n  ${i+1}. ${e}`)); }
// Les avertissements viennent APRÈS les échecs et ne changent pas le code de
// sortie : ils signalent une dérive, ils ne bloquent rien.
if (avertissements.length) {
  console.log(`\n${'='.repeat(58)}\n  Avertissements — rien n'est cassé, mais ça dérive :`);
  avertissements.forEach((a,i)=>console.log(`\n  ${i+1}. ${a}`));
}
console.log('='.repeat(58));
process.exit(echecs.length ? 1 : 0);
