/**
 * ETII Hub — l'assistant documentaire (Gemini Enterprise)
 * -------------------------------------------------------
 * Une petite application web à part, distincte de celle qui sert le site.
 * Elle affiche une page de questions (Page.html) ; chaque question part
 * vers l'application Gemini Enterprise du service, qui lit les documents
 * du Drive partagé et répond en citant ses sources.
 *
 * Pourquoi une application à part : le site s'exécute « en tant que Moi »
 * (il écrit dans une feuille privée). Un assistant exécuté ainsi lirait
 * les documents avec VOS droits, pour tout le monde. Celle-ci s'exécute
 * « en tant que l'utilisateur qui accède » : chacun interroge Gemini avec
 * son propre compte, sa propre licence, et ne reçoit que des passages de
 * documents qu'il a le droit d'ouvrir.
 *
 * Aucune clé : l'appel porte le jeton de la personne connectée
 * (ScriptApp.getOAuthToken). Rien n'est enregistré ici.
 *
 * Mise en place : docs/ASSISTANT-IA.md, partie 3.
 *   - appsscript.json : copier celui de ce dossier (portées, exécution).
 *   - Paramètres du projet › Projet Google Cloud : le projet standard où
 *     vit l'application Gemini Enterprise (fourni par la DSI).
 *   - Paramètres du projet › Propriétés du script : GEMINI_APP, le nom
 *     complet de l'application, de la forme
 *       projects/123456789/locations/eu/collections/default_collection/engines/mon-app
 *
 * Format vérifié le 26 septembre 2026 sur la référence REST
 * « projects.locations.collections.engines.assistants.streamAssist » (v1).
 */

var PROPRIETE_APP = 'GEMINI_APP';
var ASSISTANT = 'default_assistant';
var LIMITE_QUESTION = 2000;
var LIMITE_EXTRAIT = 320;
var MOTIF_APP = /^projects\/[^\/]+\/locations\/(global|us|eu)\/collections\/[^\/]+\/engines\/[^\/]+$/;

/* Les raisons pour lesquelles Gemini peut choisir de ne pas répondre. */
var RAISONS_SILENCE = {
  NON_ASSIST_SEEKING_QUERY_IGNORED: 'Gemini n’a pas reconnu une question dans ce message : reformulez-le en une phrase interrogative.',
  CUSTOMER_POLICY_VIOLATION: 'La question ou la réponse a été bloquée par une règle de l’entreprise.'
};

/* ======================================================================
   La page
   ====================================================================== */

function doGet(e) {
  var page = HtmlService.createTemplateFromFile('Page');
  var q = (e && e.parameter && e.parameter.q) ? String(e.parameter.q) : '';
  page.question = q.slice(0, LIMITE_QUESTION);
  return page.evaluate()
    .setTitle('Assistant documentaire ETII')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/* ======================================================================
   La question — appelée par la page (google.script.run)
   ====================================================================== */

/**
 * Pose une question à Gemini Enterprise, au nom de la personne connectée.
 * @param {string} question
 * @param {string} [session]  la conversation en cours, pour les questions de suite
 * @returns {{reponse:string, sources:Array<{titre:string, lien:string, extrait:string, page:string}>, session:string}}
 */
function etiiRepondre(question, session) {
  var q = String(question || '').trim();
  if (!q) throw new Error('La question est vide.');
  if (q.length > LIMITE_QUESTION) throw new Error('La question dépasse ' + LIMITE_QUESTION + ' caractères.');

  var app = application_();
  var corps = { query: { text: q } };
  var s = String(session || '');
  if (s && s.indexOf(app + '/sessions/') === 0) corps.session = s;

  var reponse = UrlFetchApp.fetch(adresse_(app), {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify(corps),
    muteHttpExceptions: true
  });
  var code = reponse.getResponseCode();
  var texte = reponse.getContentText();
  if (code === 401 || code === 403) {
    throw new Error('Gemini Enterprise refuse l’accès (' + code + ') : il faut une licence Gemini Enterprise et le rôle « Discovery Engine User » sur le projet. ' + motifErreur_(texte));
  }
  if (code === 404) throw new Error('Application Gemini introuvable : vérifiez la propriété ' + PROPRIETE_APP + '. ' + motifErreur_(texte));
  if (code >= 300) throw new Error('Gemini Enterprise a répondu ' + code + '. ' + motifErreur_(texte));
  return lireFlux_(texte);
}

/* ======================================================================
   Lecture de la réponse
   ====================================================================== */

/**
 * La réponse arrive en flux : un tableau JSON de morceaux, chacun portant
 * une partie de la réponse (answer.replies) et, une fois, la conversation
 * (sessionInfo.session). Les passages « pensée » du modèle sont écartés ;
 * les sources viennent de textGroundingMetadata.references.
 */
function lireFlux_(texte) {
  var morceaux;
  try { morceaux = JSON.parse(texte); } catch (err) { throw new Error('Réponse illisible de Gemini Enterprise.'); }
  if (!Array.isArray(morceaux)) morceaux = [morceaux];

  var parties = [];
  var sources = [];
  var vues = {};
  var etat = '';
  var raisons = [];
  var session = '';

  morceaux.forEach(function (m) {
    if (!m) return;
    if (m.sessionInfo && m.sessionInfo.session) session = String(m.sessionInfo.session);
    var a = m.answer;
    if (!a) return;
    if (a.state) etat = String(a.state);
    (a.assistSkippedReasons || []).forEach(function (r) { raisons.push(String(r)); });
    (a.replies || []).forEach(function (reply) {
      var g = reply && reply.groundedContent;
      if (!g) return;
      var c = g.content || {};
      if (typeof c.text === 'string' && !c.thought) parties.push(c.text);
      var refs = (g.textGroundingMetadata && g.textGroundingMetadata.references) || [];
      refs.forEach(function (ref) {
        var d = (ref && ref.documentMetadata) || {};
        var cle = d.uri || d.document || d.title;
        if (!cle || vues[cle]) return;
        vues[cle] = true;
        sources.push({
          titre: String(d.title || d.uri || 'Document'),
          lien: lienSur_(d.uri),
          extrait: court_(ref.content, LIMITE_EXTRAIT),
          page: d.pageIdentifier ? String(d.pageIdentifier) : ''
        });
      });
    });
  });

  if (etat === 'SKIPPED') {
    throw new Error(raisons.map(function (r) { return RAISONS_SILENCE[r] || r; }).join(' ')
      || 'Gemini a choisi de ne pas répondre à cette question.');
  }
  if (etat === 'FAILED') throw new Error('Gemini n’a pas pu terminer sa réponse. Réessayez.');

  return { reponse: parties.join('').trim(), sources: sources, session: session };
}

/* ======================================================================
   Outils
   ====================================================================== */

function application_() {
  var app = String(PropertiesService.getScriptProperties().getProperty(PROPRIETE_APP) || '').trim();
  if (!app) throw new Error('L’assistant n’est pas encore relié : la propriété du script ' + PROPRIETE_APP + ' est vide.');
  if (!MOTIF_APP.test(app)) throw new Error('La propriété ' + PROPRIETE_APP + ' doit avoir la forme projects/…/locations/eu/collections/default_collection/engines/….');
  return app;
}

/* L'adresse régionale : eu-… et us-… pour les multi-régions, sans préfixe
   pour « global ». */
function adresse_(app) {
  var region = MOTIF_APP.exec(app)[1];
  var hote = region === 'global' ? 'discoveryengine.googleapis.com' : region + '-discoveryengine.googleapis.com';
  return 'https://' + hote + '/v1/' + app + '/assistants/' + ASSISTANT + ':streamAssist';
}

function lienSur_(uri) {
  var u = String(uri || '');
  return /^https:\/\//i.test(u) ? u : '';
}

function court_(v, n) {
  var t = String(v || '').replace(/\s+/g, ' ').trim();
  return t.length > n ? t.slice(0, n - 1).trim() + '…' : t;
}

function motifErreur_(texte) {
  try {
    var e = JSON.parse(texte);
    if (Array.isArray(e)) e = e[0];
    if (e && e.error && e.error.message) return String(e.error.message).slice(0, 300);
  } catch (err) { /* corps non JSON */ }
  return '';
}
