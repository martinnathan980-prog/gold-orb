/**
 * ETII Hub — l'intermédiaire entre le portail et l'API Gemini
 * ------------------------------------------------------------
 * Le portail est un site statique : une clé API posée dedans serait
 * publique. Ce script la détient à sa place. Le site lui envoie une
 * question, il interroge l'API Gemini avec File Search, et renvoie la
 * réponse ET ses citations.
 *
 * Mise en place :
 *   1. Paramètres du projet → Propriétés du script, ajouter :
 *        GEMINI_API_KEY      la clé, créée dans un projet AVEC FACTURATION
 *        FILE_SEARCH_STORE   fileSearchStores/xxxxx (voir creerMagasin)
 *   2. Exécuter `creerMagasin` une fois si vous n'en avez pas encore un ;
 *      recopier le nom renvoyé dans la propriété FILE_SEARCH_STORE.
 *   3. Verser les documents : `importerDepuisDossier` (un dossier Drive).
 *   4. Déployer → Application web, « Exécuter en tant que : moi »,
 *      « Qui a accès : toute personne de <votre domaine> ».
 *   5. Coller l'URL /exec dans SOURCE.url de assets/js/assistant.js.
 *
 * Rappel de sécurité : n'indexez que des documents dont la diffusion à
 * tout porteur du lien d'application est acceptable. Ce proxy ne connaît
 * PAS les droits d'accès document par document — c'est la limite du
 * chemin A, et la raison d'être du chemin B (voir docs/ASSISTANT-IA.md).
 */

var MODELE = 'gemini-flash-latest';
var RACINE = 'https://generativelanguage.googleapis.com/v1beta/';

function cle_() {
  var k = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
  if (!k) throw new Error('Propriété GEMINI_API_KEY absente.');
  return k;
}

function magasin_() {
  var m = PropertiesService.getScriptProperties().getProperty('FILE_SEARCH_STORE');
  if (!m) throw new Error('Propriété FILE_SEARCH_STORE absente.');
  return m;
}

function appel_(chemin, charge, methode) {
  var reponse = UrlFetchApp.fetch(RACINE + chemin, {
    method: methode || 'post',
    contentType: 'application/json',
    headers: { 'x-goog-api-key': cle_() },
    payload: charge ? JSON.stringify(charge) : null,
    muteHttpExceptions: true
  });
  var corps = reponse.getContentText();
  if (reponse.getResponseCode() >= 300) {
    throw new Error('API Gemini ' + reponse.getResponseCode() + ' : ' + corps.slice(0, 400));
  }
  return JSON.parse(corps);
}

/** À exécuter une fois : crée le magasin et renvoie son nom. */
function creerMagasin() {
  var r = appel_('fileSearchStores', { displayName: 'Fonds documentaire ETII' });
  Logger.log('FILE_SEARCH_STORE = ' + r.name);
  return r.name;
}

/**
 * Verse dans le magasin tous les fichiers d'un dossier Drive.
 * À relancer après chaque mise à jour du fonds : l'index ne se met pas
 * à jour tout seul.
 * @param {string} idDossier  l'identifiant du dossier Drive
 */
function importerDepuisDossier(idDossier) {
  var dossier = DriveApp.getFolderById(idDossier);
  var fichiers = dossier.getFiles();
  var faits = 0;
  while (fichiers.hasNext()) {
    var f = fichiers.next();
    // 100 Mo est la limite par document annoncée par Google.
    if (f.getSize() > 100 * 1024 * 1024) { Logger.log('ignoré (trop gros) : ' + f.getName()); continue; }
    var url = RACINE.replace('/v1beta/', '/upload/v1beta/') + magasin_() + ':uploadToFileSearchStore';
    var reponse = UrlFetchApp.fetch(url + '?key=' + cle_(), {
      method: 'post',
      contentType: f.getMimeType(),
      headers: { 'X-Goog-Upload-Protocol': 'raw', 'X-Goog-Upload-File-Name': f.getName() },
      payload: f.getBlob().getBytes(),
      muteHttpExceptions: true
    });
    if (reponse.getResponseCode() >= 300) Logger.log('échec ' + f.getName() + ' : ' + reponse.getContentText().slice(0, 200));
    else faits += 1;
  }
  Logger.log(faits + ' document(s) versés dans ' + magasin_());
}

/** Le portail appelle ceci. Entrée : { question }. Sortie : { reponse, citations }. */
function doPost(e) {
  try {
    var entree = JSON.parse(e.postData.contents || '{}');
    var question = String(entree.question || '').trim();
    if (!question) throw new Error('Question vide.');
    if (question.length > 2000) throw new Error('Question trop longue.');

    var r = appel_('models/' + MODELE + ':generateContent', {
      contents: [{ role: 'user', parts: [{ text: question }] }],
      tools: [{ file_search: { file_search_store_names: [magasin_()] } }],
      systemInstruction: { parts: [{ text:
        'Tu réponds aux ingénieurs du service ETII à partir des seuls documents fournis. '
        + 'Réponds en français, brièvement et précisément. Si les documents ne contiennent pas '
        + 'la réponse, dis-le explicitement : « Le fonds documentaire ne répond pas à cette question. » '
        + 'N’invente jamais une règle, une valeur ou une référence.' }] }
    });

    var candidat = (r.candidates || [])[0] || {};
    var parts = ((candidat.content || {}).parts) || [];
    var texte = parts.map(function (p) { return p.text || ''; }).join('').trim();

    // Les citations : nom du document et passage d'origine.
    var citations = [];
    (candidat.groundingMetadata ? candidat.groundingMetadata.groundingChunks || [] : [])
      .forEach(function (c) {
        var s = c.retrievedContext || c.fileSearch || {};
        if (s.title || s.uri) citations.push({ titre: s.title || s.uri, extrait: (s.text || '').slice(0, 300) });
      });

    return json_({ reponse: texte, citations: citations, modele: MODELE });
  } catch (err) {
    return json_({ erreur: String(err && err.message ? err.message : err) });
  }
}

/* Le navigateur envoie parfois une requête GET de vérification. */
function doGet() {
  return json_({ etat: 'prêt', modele: MODELE });
}

function json_(objet) {
  return ContentService.createTextOutput(JSON.stringify(objet))
    .setMimeType(ContentService.MimeType.JSON);
}
