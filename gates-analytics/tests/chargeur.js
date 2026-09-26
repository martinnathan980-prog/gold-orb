/* Batterie du CHARGEUR — le fichier unique qu'on colle dans Apps Script.
   On ne peut pas déployer un vrai Apps Script depuis ici, alors on en
   fabrique un : un classeur en mémoire, un faux UrlFetchApp qui sert les
   fichiers du dépôt depuis le disque, un faux cache. Puis on lance le VRAI
   apps-script/Chargeur.gs dedans, et on regarde la page qu'il fabrique —
   dans un vrai navigateur, avec les vraies données du classeur.

   C'est la seule façon de vérifier, sans Apps Script, que l'astuce tient :
   le serveur lu sur le dépôt est exécuté, et la page du prototype reçoit son
   paquet avant de s'initialiser.

       node tests/chargeur.js
*/
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { chromium } = require('playwright');
const { Feuille, Classeur, poserEnvironnement } = require('./faux-classeur');
const { feuilleGates } = require('./feuille-gates');

const racine = path.join(__dirname, '..');
const echecs = [];
const faits = [];

function verifier(nom, condition, detail) {
  if (condition) {
    faits.push(nom);
    console.log('  ✓ ' + nom);
  } else {
    echecs.push(nom);
    console.log('  ✗ ' + nom + (detail !== undefined ? ' — ' + JSON.stringify(detail) : ''));
  }
}

function section(titre) {
  console.log('\n— ' + titre + ' —');
}

/* ------------------------------------------------------------------ */
/*  Le faux Apps Script : ce que le chargeur croit avoir autour de lui  */
/* ------------------------------------------------------------------ */
function monterLeChargeur(options) {
  const opts = options || {};
  const classeur = new Classeur([new Feuille('HDK', feuilleGates(opts.lignes || 120).valeurs, false,
                                             feuilleGates(opts.lignes || 120).fusions)],
                                'Suivi FWD H225');
  const journal = [];
  const alertes = [];
  const appels = [];            // ce qui est allé chercher quoi, et dans quel ordre
  const cache = new Map();

  const base = poserEnvironnement({ console: { log: function () {} }, JSON: JSON, Date: Date, Math: Math },
                                  classeur, {}, {});
  const contexte = vm.createContext(Object.assign(base, {
    UrlFetchApp: {
      fetch: function (url, params) {
        appels.push(url);
        if (opts.panne) {
          return { getResponseCode: function () { return opts.panne; },
                   getContentText: function () { return 'rien'; } };
        }
        const relatif = url.replace(/^.*gates-analytics\//, '');
        const fichier = path.join(racine, relatif);
        if (!fs.existsSync(fichier)) {
          return { getResponseCode: function () { return 404; },
                   getContentText: function () { return 'Not Found'; } };
        }
        const texte = fs.readFileSync(fichier, 'utf8');
        return { getResponseCode: function () { return 200; },
                 getContentText: function () { return texte; } };
      }
    },
    CacheService: {
      getScriptCache: function () {
        return {
          get: function (c) { return cache.has(c) ? cache.get(c) : null; },
          put: function (c, v) { cache.set(c, v); },
          putAll: function (o) { Object.keys(o).forEach(function (c) { cache.set(c, o[c]); }); },
          removeAll: function (cles) { cles.forEach(function (c) { cache.delete(c); }); }
        };
      }
    },
    HtmlService: {
      createHtmlOutput: function (html) {
        const sortie = {
          html: html,
          setTitle: function () { return sortie; },
          setWidth: function () { return sortie; },
          setHeight: function () { return sortie; },
          addMetaTag: function () { return sortie; }
        };
        return sortie;
      }
    },
    Logger: { log: function (m) { journal.push(String(m)); } }
  }));
  /* Une interface de classeur stable : le faux classeur en rend une neuve à
     chaque appel, or on veut retenir ce qui aurait été montré à la lectrice —
     les menus posés, les fenêtres ouvertes, les messages affichés. */
  const menus = [];
  const dialogues = [];
  const ui = {
    ButtonSet: { OK: 'OK' },
    alert: function (titre, message) { alertes.push(titre + ' | ' + message); },
    createMenu: function (nom) {
      const menu = { nom: nom, entrees: [] };
      menu.addItem = function (libelle, fonction) {
        menu.entrees.push(libelle + ' \u2192 ' + fonction);
        return menu;
      };
      menu.addSeparator = function () { return menu; };
      menu.addToUi = function () { menus.push(menu); return menu; };
      return menu;
    },
    showModalDialog: function (sortie, titre) { dialogues.push({ titre: titre, html: sortie.html }); }
  };
  contexte.SpreadsheetApp.getUi = function () { return ui; };

  vm.runInContext(fs.readFileSync(path.join(racine, 'apps-script', 'Chargeur.gs'), 'utf8'), contexte);
  return { contexte: contexte, appels: appels, cache: cache, journal: journal,
           alertes: alertes, classeur: classeur, menus: menus, dialogues: dialogues };
}

/* ------------------------------------------------------------------ */
(async function () {
  section('Le chargeur va chercher le code, et le garde');
  let monte = monterLeChargeur();
  const page = monte.contexte.pageComplete();
  verifier('il lit la page ET le serveur sur le dépôt',
    monte.appels.some(function (u) { return /suivi-fwd\.html$/.test(u); }) &&
    monte.appels.some(function (u) { return /Code\.gs$/.test(u); }), monte.appels);
  verifier('et il garde tout en mémoire, en morceaux',
    monte.cache.size > 4 && monte.cache.get('suivifwd:Code.gs:n') !== undefined,
    [monte.cache.size, monte.cache.get('suivifwd:Code.gs:n')]);
  const avant = monte.appels.length;
  monte.contexte.pageComplete();
  verifier('la deuxième ouverture ne redemande rien au dépôt',
    monte.appels.length === avant, monte.appels.length - avant);
  monte.contexte.viderLeCache();
  monte.contexte.pageComplete();
  verifier('« Recharger le code » le fait vraiment retourner au dépôt',
    monte.appels.length > avant && monte.alertes.some(function (a) { return /Code oublié/.test(a); }),
    monte.alertes);

  section('La page fabriquée est un document complet');
  verifier('doctype, tête, corps — et la page du dépôt dedans',
    /^<!doctype html>/i.test(page) && page.indexOf('<body>') !== -1 &&
    page.indexOf('</body></html>') === page.length - 14, page.slice(0, 60));
  verifier('« base target=_top » est posé : la page vit dans un cadre',
    page.indexOf('<base target="_top">') !== -1);
  verifier('les données sont posées AVANT le corps de la page',
    page.indexOf('SUIVI_FWD_DONNEES') < page.indexOf('<body>'),
    [page.indexOf('SUIVI_FWD_DONNEES'), page.indexOf('<body>')]);
  verifier('le pont vers le classeur est tendu, avec un repli si le classeur ne répond pas',
    /SUIVI_FWD_API/.test(page) && /getDonneesPourClient/.test(page) && /cb\(null\)/.test(page));
  verifier('le paquet du classeur est dedans, pas un jeu d\'exemple',
    /"ok":true/.test(page) && /"contrat":"HDK"/.test(page));
  verifier('rien n\'échappe au JSON : pas de balise qui coupe la page en deux',
    page.split('<script>').length === page.split('</scr' + 'ipt>').length,
    [page.split('<script>').length, page.split('</scr' + 'ipt>').length]);

  section('Le serveur du dépôt est bien exécuté, pas seulement lu');
  const api = monte.contexte.serveur();
  verifier('les trois fonctions attendues en sortent',
    typeof api.pourClient === 'function' && typeof api.json === 'function' &&
    typeof api.diagnostic === 'function');
  const paquet = api.pourClient();
  verifier('et elles lisent vraiment le classeur',
    paquet.ok === true && paquet.plans.length > 100 && paquet.colonnes.length > 100,
    [paquet.ok, paquet.plans.length, paquet.colonnes.length]);
  verifier('le pont getDonneesPourClient du chargeur passe la main au vrai serveur',
    monte.contexte.getDonneesPourClient('HDK').plans.length === paquet.plans.length);
  verifier('le diagnostic répond quelque chose de lisible',
    typeof api.diagnostic() === 'string' && api.diagnostic().length > 50);
  verifier('« verifier » dit l\'état de tout, en trois lignes',
    /Page {6}:/.test(monte.contexte.verifier()) && /Classeur {2}:/.test(monte.contexte.verifier()),
    monte.contexte.verifier());

  section('Quand le dépôt ne répond pas, il le dit');
  const casse = monterLeChargeur({ panne: 404 });
  let message = '';
  try { casse.contexte.pageComplete(); } catch (err) { message = err.message; }
  verifier('un 404 nomme le fichier et dit quoi corriger',
    /404/.test(message) && /branche/.test(message), message);
  const coupe = monterLeChargeur({ panne: 503 });
  message = '';
  try { coupe.contexte.pageComplete(); } catch (err) { message = err.message; }
  verifier('une panne passagère invite à réessayer', /503/.test(message) && /Réessayer/.test(message), message);

  section('Le menu du classeur, et ce qu\'il ouvre');
  monte.contexte.onOpen();
  verifier('le menu « Suivi FWD » est posé, avec ses trois entrées',
    monte.menus.length === 1 && monte.menus[0].nom === 'Suivi FWD' &&
    monte.menus[0].entrees.length === 3, monte.menus.map(function (m) { return m.entrees; }));
  verifier('chaque entrée vise une fonction qui existe vraiment',
    monte.menus[0].entrees.every(function (e) {
      return typeof monte.contexte[e.split(' \u2192 ')[1]] === 'function';
    }), monte.menus[0].entrees);
  monte.contexte.ouvrirTableauDeBord();
  verifier('« Ouvrir le tableau de bord » montre la page, avec les données dedans',
    monte.dialogues.length === 1 && monte.dialogues[0].titre === 'Suivi FWD' &&
    /"ok":true/.test(monte.dialogues[0].html),
    monte.dialogues.map(function (d) { return d.titre; }));
  monte.contexte.montrerLeDiagnostic();
  verifier('« Diagnostic » affiche ce que le script voit du classeur',
    monte.alertes.some(function (a) { return /^Diagnostic \| /.test(a) && a.length > 100; }),
    monte.alertes.map(function (a) { return a.slice(0, 40); }));

  section('Et dans un vrai navigateur');
  let html = page;
  if (fs.existsSync(path.join(racine, 'prototype', 'fonts', 'local.css'))) {
    html = html.replace(/<link rel="stylesheet"[^>]*href="https:\/\/fonts\.googleapis\.com[^>]*>/,
                        '<link rel="stylesheet" href="fonts/local.css">');
  }
  const cible = path.join(racine, 'prototype', 'apercu-chargeur.html');
  fs.writeFileSync(cible, html);
  const erreurs = [];
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 1000 } });
  const p = await ctx.newPage();
  p.on('pageerror', function (e) { erreurs.push(e.message); });
  p.on('console', function (m) {
    if (m.type() === 'error' && !/ERR_FILE|net::/.test(m.text())) erreurs.push(m.text());
  });
  await p.goto('file://' + cible);
  await p.waitForTimeout(1800);
  const vu = await p.evaluate(function () {
    return {
      titre: document.querySelector('h1') && document.querySelector('h1').textContent.trim(),
      etats: [].slice.call(document.querySelectorAll('#etats .etat-n'))
        .map(function (e) { return +e.textContent.replace(/\s/g, ''); }),
      colonnes: [].slice.call(document.querySelectorAll('tr.titres th'))
        .map(function (t) { return t.textContent.trim(); }),
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      graphe: !!document.querySelector('svg.graphe'),
      journal: document.querySelectorAll('#zone-journal *').length,
      demo: document.getElementById('avertissement-demo') &&
            document.getElementById('avertissement-demo').offsetParent !== null
    };
  });
  await nav.close();

  verifier('la page s\'affiche, sans une seule erreur JavaScript', erreurs.length === 0, erreurs);
  verifier('les quatre états comptent exactement les plans du classeur',
    vu.etats.reduce(function (a, b) { return a + b; }, 0) === paquet.plans.length,
    [vu.etats, paquet.plans.length]);
  /* La page retire la première colonne de l'extract — celle qu'Excel ajoute,
     sans intitulé et vide. Toutes les autres restent, dans l'ordre. */
  const attendues = paquet.colonnes.map(function (c) { return c.titre; });
  const sansLaPremiere = attendues.slice(1);
  verifier('le tableau porte toutes les lignes de l\'extract',
    vu.colonnes.length > 0 && vu.lignes === paquet.plans.length,
    [vu.lignes, paquet.plans.length]);
  verifier('et toutes ses colonnes, dans l\'ordre, sauf la première que la page retire',
    JSON.stringify(vu.colonnes) === JSON.stringify(sansLaPremiere),
    [vu.colonnes.slice(0, 4), sansLaPremiere.slice(0, 4),
     vu.colonnes.length, sansLaPremiere.length]);
  /* Le serveur baptise « Colonne N » une colonne que l'extract n'a pas nommée :
     c'est cela, « sans intitulé ». */
  verifier('la colonne retirée est bien celle d\'Excel : sans intitulé, et vide partout',
    /^Colonne \d+$/.test(attendues[0]) && paquet.plans.every(function (plan) {
      const v = plan[paquet.colonnes[0].cle];
      return v === undefined || v === null || String(v).trim() === '';
    }), [attendues[0], paquet.colonnes[0].cle,
         paquet.plans.slice(0, 2).map(function (p) { return p[paquet.colonnes[0].cle]; })]);
  verifier('le graphe est tracé et le journal rempli', vu.graphe && vu.journal > 0,
    [vu.graphe, vu.journal]);
  verifier('l\'avertissement « jeu d\'exemple » reste caché : ce sont de vraies données',
    !vu.demo);
  verifier('le titre est là', vu.titre === 'Suivi FWD', vu.titre);

  console.log('\n' + (faits.length + echecs.length) + ' vérifications, ' + echecs.length + ' échec(s).');
  process.exit(echecs.length ? 1 : 0);
})();
