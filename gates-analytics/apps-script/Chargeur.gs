/**
 * LE CHARGEUR — un seul fichier à coller, et le tableau de bord tourne.
 *
 * Le tableau de bord tient normalement en quatre fichiers, dont un de 222 Ko.
 * Ici, rien de tout cela : ce fichier va chercher la page et le serveur sur le
 * dépôt public **au moment où on ouvre le tableau de bord**, et les fait
 * tourner. C'est Google qui télécharge, depuis ses serveurs — le réseau de
 * l'entreprise n'est pas concerné.
 *
 * MARCHE À SUIVRE — trois gestes
 *   1. Dans le classeur : Extensions → Apps Script.
 *   2. Tout effacer dans « Code.gs », coller ce fichier, Ctrl+S.
 *   3. Recharger le classeur (F5) → menu « Suivi FWD » → Ouvrir le tableau
 *      de bord. Autoriser quand Google le demande.
 *
 * Rien d'autre : pas de manifeste à modifier, pas d'API à activer.
 *
 * Le code est relu à chaque ouverture, puis gardé en mémoire six heures. Pour
 * forcer la relecture après une mise à jour : menu Suivi FWD → Recharger le
 * code.
 */

/** Le dépôt public, et la branche. */
const DEPOT = 'https://raw.githubusercontent.com/martinnathan980-prog/gold-orb/'
            + 'claude/javascript-gzip-base64-decoder-v0yr1m/gates-analytics/';
const PAGE = 'prototype/suivi-fwd.html';
const SERVEUR = 'Code.gs';
const HEURES = 6 * 3600;          // le cache de Google ne garde pas plus longtemps
const MORCEAU = 70000;            // caractères par morceau : le cache limite chaque clé


// =====================================================================
//  CE QUE LA LECTRICE VOIT
// =====================================================================

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Suivi FWD')
    .addItem('Ouvrir le tableau de bord', 'ouvrirTableauDeBord')
    .addSeparator()
    .addItem('Diagnostic', 'montrerLeDiagnostic')
    .addItem('Recharger le code', 'viderLeCache')
    .addToUi();
}


/** Le tableau de bord, en fenêtre, depuis le classeur. */
function ouvrirTableauDeBord() {
  const page = HtmlService.createHtmlOutput(pageComplete())
    .setTitle('Suivi FWD')
    .setWidth(2000)
    .setHeight(1400);
  SpreadsheetApp.getUi().showModalDialog(page, 'Suivi FWD');
}


/** Le tableau de bord en application web, si on en déploie une. */
function doGet() {
  return HtmlService.createHtmlOutput(pageComplete())
    .setTitle('Suivi FWD')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}


/**
 * Le pont que la page appelle pour changer de contrat sans se recharger.
 * google.script.run cherche une fonction de CE fichier : elle passe la main
 * au vrai serveur.
 */
function getDonneesPourClient(contrat) {
  return serveur().pourClient(contrat);
}


/** Ce que le script voit réellement du classeur, quand la page ne s'ouvre pas. */
function montrerLeDiagnostic() {
  const texte = serveur().diagnostic();
  SpreadsheetApp.getUi().alert('Diagnostic', String(texte), SpreadsheetApp.getUi().ButtonSet.OK);
}


/**
 * Oublie le code gardé en mémoire : la prochaine ouverture relira le dépôt.
 * À lancer après une mise à jour.
 */
function viderLeCache() {
  const cache = CacheService.getScriptCache();
  [PAGE, SERVEUR].forEach(function (chemin) {
    const compte = Number(cache.get(cle(chemin) + ':n') || 0);
    const cles = [cle(chemin) + ':n'];
    for (let i = 0; i < compte; i++) {
      cles.push(cle(chemin) + ':' + i);
    }
    cache.removeAll(cles);
  });
  const mot = 'Code oublié. La prochaine ouverture ira le relire sur le dépôt.';
  try {
    SpreadsheetApp.getUi().alert('Suivi FWD', mot, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    Logger.log(mot);
  }
  return mot;
}


/**
 * À lancer depuis l'éditeur (▶ Exécuter) pour vérifier que tout est en place,
 * sans rien ouvrir. Dit ce qui marche et ce qui ne marche pas.
 */
function verifier() {
  const dire = [];
  try {
    const html = duDepot(PAGE);
    dire.push('Page      : ' + Math.round(html.length / 1024) + ' Ko lus'
              + (html.indexOf('SUIVI_FWD_DONNEES') === -1 ? '  ← ATTENTION : page inattendue' : ''));
  } catch (err) {
    dire.push('Page      : ÉCHEC — ' + err.message);
  }
  try {
    const api = serveur();
    dire.push('Serveur   : chargé, ' + Object.keys(api).length + ' fonctions');
    const paquet = api.pourClient();
    dire.push('Classeur  : ' + (paquet.ok
      ? paquet.plans.length + ' plan(s) dans l\'onglet « ' + paquet.feuille + ' »'
      : 'rien à lire — ' + paquet.message));
  } catch (err) {
    dire.push('Serveur   : ÉCHEC — ' + err.message);
  }
  const rapport = dire.join('\n');
  Logger.log(rapport);
  return rapport;
}


// =====================================================================
//  LA PAGE : celle du dépôt, avec les données du classeur posées dedans
// =====================================================================

function pageComplete() {
  const corps = duDepot(PAGE);
  if (corps.indexOf('SUIVI_FWD_DONNEES') === -1) {
    throw new Error('La page lue sur le dépôt n\'est pas celle attendue : elle ne sait pas '
                    + 'recevoir les données du classeur. Lancer « Recharger le code », puis me '
                    + 'le dire si cela persiste.');
  }
  // La page du dépôt est un CORPS de document : elle s'enveloppe ici, comme
  // le fait l'aperçu autonome — même en-tête, mêmes réglages. On ajoute
  // seulement « base target=_top », parce qu'ici la page vit dans un cadre.
  return '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
    + '<base target="_top">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    + '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui;background:#fafaf9}'
    + 'img{max-width:100%}[hidden]{display:none!important}</style>'
    // Les données sont posées AVANT le script de la page : elle les trouve
    // en s'initialisant, sans aller-retour et sans écran d'attente.
    + '<script>\n'
    + 'window.SUIVI_FWD_DONNEES = ' + serveur().json() + ';\n'
    + 'window.SUIVI_FWD_API = { chargerContrat: function (id, cb) {\n'
    + '  try {\n'
    + '    google.script.run.withSuccessHandler(cb)\n'
    + '      .withFailureHandler(function () { cb(null); })\n'
    + '      .getDonneesPourClient(id);\n'
    + '  } catch (e) { cb(null); }\n'
    + '} };\n'
    + '</scr' + 'ipt>'
    + '</head><body>' + corps + '\n</body></html>';
}


// =====================================================================
//  LE SERVEUR : le vrai Code.gs, lu sur le dépôt et exécuté ici
// =====================================================================

/**
 * Rend les trois fonctions du serveur dont on a besoin.
 *
 * Le code du dépôt est évalué, et l'objet rendu est construit DANS cette
 * évaluation : c'est ainsi qu'on en ressort les fonctions, sans dépendre de
 * la façon dont le moteur traite les déclarations d'un eval.
 */
function serveur() {
  const source = duDepot(SERVEUR);
  const api = eval(source + '\n;({ pourClient: getDonneesPourClient, '
                          + 'json: donneesJSONPourPage, diagnostic: diagnostic })');
  if (!api || typeof api.pourClient !== 'function') {
    throw new Error('Le serveur lu sur le dépôt n\'a pas la forme attendue. '
                    + 'Lancer « Recharger le code ».');
  }
  return api;
}


// =====================================================================
//  ALLER CHERCHER, ET GARDER SOUS LA MAIN
// =====================================================================

function cle(chemin) {
  return 'suivifwd:' + chemin;
}


/** Le contenu d'un fichier du dépôt — de la mémoire si possible, sinon du réseau. */
function duDepot(chemin) {
  const garde = duCache(chemin);
  if (garde) {
    return garde;
  }
  const reponse = UrlFetchApp.fetch(DEPOT + chemin,
                                    { muteHttpExceptions: true, followRedirects: true });
  const code = reponse.getResponseCode();
  if (code !== 200) {
    throw new Error('Le dépôt a répondu ' + code + ' pour ' + chemin + '.\n'
      + (code === 404
         ? 'La branche a changé de nom : corriger la constante DEPOT en haut du fichier.'
         : 'Réessayer dans un instant ; si cela persiste, me le dire.'));
  }
  const texte = reponse.getContentText();
  versLeCache(chemin, texte);
  return texte;
}


/** Ce que le cache a gardé, ou rien. Le cache est un confort : jamais une dépendance. */
function duCache(chemin) {
  try {
    const cache = CacheService.getScriptCache();
    const compte = Number(cache.get(cle(chemin) + ':n') || 0);
    if (!compte) {
      return null;
    }
    const morceaux = [];
    for (let i = 0; i < compte; i++) {
      const bout = cache.get(cle(chemin) + ':' + i);
      if (bout === null) {
        return null;              // un morceau a expiré : le tout ne vaut plus rien
      }
      morceaux.push(bout);
    }
    return morceaux.join('');
  } catch (e) {
    return null;
  }
}


/** Garde le fichier en morceaux : le cache limite la taille de chaque clé. */
function versLeCache(chemin, texte) {
  try {
    const cache = CacheService.getScriptCache();
    const morceaux = {};
    let compte = 0;
    for (let i = 0; i < texte.length; i += MORCEAU) {
      morceaux[cle(chemin) + ':' + compte] = texte.slice(i, i + MORCEAU);
      compte++;
    }
    cache.putAll(morceaux, HEURES);
    cache.put(cle(chemin) + ':n', String(compte), HEURES);
  } catch (e) {
    /* Cache plein ou indisponible : tant pis, on relira le dépôt. */
  }
}
