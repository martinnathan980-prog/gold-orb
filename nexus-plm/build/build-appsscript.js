/**
 * Prépare une version « à coller » dans l'éditeur Apps Script.
 *
 * L'éditeur n'a pas d'import : chaque fichier se crée à la main. Coller 20
 * fichiers est long et c'est là qu'on se trompe de nom. On en produit donc
 * DEUX, strictement équivalents :
 *
 *   build/appsscript/Code.gs    les 4 fichiers serveur, à la suite
 *   build/appsscript/Index.html les 12 fichiers client, includes résolus
 *
 * Le code est celui de src/, sans retouche : on concatène, on résout les
 * <?!= include() ?>, rien d'autre. Pour un projet suivi dans le temps,
 * `clasp push` reste la bonne voie — elle garde le découpage en fichiers.
 */
const fs = require('fs');
const path = require('path');

const RACINE = path.join(__dirname, '..');
const lire = function (p) { return fs.readFileSync(path.join(RACINE, p), 'utf8'); };

const SORTIE = path.join(RACINE, 'build', 'appsscript');
fs.mkdirSync(SORTIE, { recursive: true });

// --- 1. Code.gs ---------------------------------------------------------
// Config d'abord : les autres fichiers lisent CFG.
const SERVEUR = ['server/Config.gs', 'server/Repository.gs', 'server/Api.gs', 'server/Setup.gs'];

const entete = function (nom) {
  return '// ' + '='.repeat(68) + '\n' +
         '// ' + nom + '\n' +
         '// ' + '='.repeat(68) + '\n';
};

const code = '// NEXUS PLM — version assemblée pour l\'éditeur Apps Script.\n' +
  '// Fichiers d\'origine : ' + SERVEUR.map(function (f) { return path.basename(f); }).join(', ') + '\n' +
  '// Ne pas modifier ici : éditer src/server/*.gs et relancer `npm run appsscript`.\n\n' +
  SERVEUR.map(function (f) { return entete(f) + lire('src/' + f).trim() + '\n'; }).join('\n');

fs.writeFileSync(path.join(SORTIE, 'Code.gs'), code);

// --- 2. Index.html ------------------------------------------------------
// Mêmes includes qu'en production, résolus une fois pour toutes. Les CDN
// restent : contrairement à l'aperçu Artifact, Apps Script les autorise.
let page = lire('src/Index.html');
const inclus = [];
page = page.replace(/<\?!=\s*include\('([^']+)'\);?\s*\?>/g, function (_, nom) {
  inclus.push(nom);
  return '<!-- ' + nom + '.html -->\n' + lire('src/' + nom + '.html');
});
if (/<\?!=/.test(page)) throw new Error('Un include n\'a pas été résolu');
if (!inclus.length) throw new Error('Aucun include trouvé : Index.html a changé de forme');

fs.writeFileSync(path.join(SORTIE, 'Index.html'), page);

// --- 3. catalogue.csv ---------------------------------------------------
// Le catalogue vit dans un classeur séparé, désigné par la propriété de
// script URL_CATALOGUE. Sans lui, l'application tourne mais le bouton
// « Choisir dans le catalogue » reste vide : on fournit de quoi le remplir.
const faux = lire('demo/FauxServeur.html');
const bloc = faux.slice(faux.indexOf('catalogue: ['), faux.indexOf(']\n};'));
const entrees = bloc.match(/\{[^}]*\}/g) || [];
if (entrees.length < 10) throw new Error('Catalogue de démonstration introuvable');

const champ = function (source, cle) {
  const m = source.match(new RegExp(cle + ":\\s*'((?:[^'\\\\]|\\\\.)*)'"));
  return m ? m[1].replace(/\\'/g, "'") : '';
};
const cellule = function (v) { return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };

const COLONNES = ['Catégorie', 'Fonction', 'Norme', 'Référence', 'Désignation'];
const lignes = [COLONNES.join(';')].concat(entrees.map(function (e) {
  return COLONNES.map(function (c) { return cellule(champ(e, c)); }).join(';');
}));
// BOM : sinon Google Sheets ouvre les accents de travers à l'import.
fs.writeFileSync(path.join(SORTIE, 'catalogue.csv'), '﻿' + lignes.join('\r\n') + '\r\n');

const ko = function (p) { return (fs.statSync(path.join(SORTIE, p)).size / 1024).toFixed(0); };
console.log('build/appsscript/ écrit :');
console.log('  Code.gs        ' + ko('Code.gs') + ' Ko — ' + SERVEUR.length + ' fichiers serveur');
console.log('  Index.html     ' + ko('Index.html') + ' Ko — ' + inclus.length + ' fichiers client');
console.log('  catalogue.csv  ' + ko('catalogue.csv') + ' Ko — ' + entrees.length + ' composants');
