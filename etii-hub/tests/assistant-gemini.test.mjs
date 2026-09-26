// L'assistant documentaire (tools/apps-script/assistant/Code.gs) et le
// remplissage du classeur des documents (tools/apps-script/index-documents.gs),
// exécutés ici contre des doublures des services Google :
//   node tests/assistant-gemini.test.mjs
//
// La réponse simulée de Gemini Enterprise suit la forme documentée de
// streamAssist (v1) : un tableau JSON de morceaux { answer, sessionInfo }.

import { readFileSync } from 'node:fs';
import vm from 'node:vm';

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK   ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };
const lire = (chemin) => readFileSync(new URL(chemin, import.meta.url), 'utf8');

/* ======================================================================
   1. L'assistant
   ====================================================================== */

const APP = 'projects/123/locations/eu/collections/default_collection/engines/etii-docs';

function assistant({ app = APP, code = 200, corps = '[]' } = {}) {
  const etat = { appels: [] };
  const contexte = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (k === 'GEMINI_APP' ? app : null) }) },
    ScriptApp: { getOAuthToken: () => 'jeton-de-la-personne' },
    UrlFetchApp: {
      fetch: (url, options) => {
        etat.appels.push({ url, options });
        return { getResponseCode: () => code, getContentText: () => (typeof corps === 'function' ? corps() : corps) };
      }
    },
    HtmlService: {
      createTemplateFromFile: (nom) => {
        const gabarit = { nom };
        gabarit.evaluate = () => {
          const sortie = { gabarit, titre: '', meta: {} };
          sortie.setTitle = (x) => { sortie.titre = x; return sortie; };
          sortie.addMetaTag = (n, v) => { sortie.meta[n] = v; return sortie; };
          return sortie;
        };
        return gabarit;
      }
    },
    console
  };
  vm.createContext(contexte);
  vm.runInContext(lire('../tools/apps-script/assistant/Code.gs'), contexte, { filename: 'assistant/Code.gs' });
  return { gs: contexte, etat };
}

const FLUX = JSON.stringify([
  { answer: { state: 'IN_PROGRESS', replies: [
    { groundedContent: { content: { role: 'model', thought: true, text: 'Je réfléchis…' } } },
    { groundedContent: { content: { role: 'model', text: 'La distance minimale est de **200 mm**' } } }
  ] } },
  { answer: { state: 'IN_PROGRESS', replies: [
    { groundedContent: {
      content: { role: 'model', text: ' entre les deux faisceaux.' },
      textGroundingMetadata: {
        segments: [{ startIndex: '0', endIndex: '40', referenceIndices: [0] }],
        references: [
          { content: 'Séparer   les faisceaux de puissance et de signal d’au moins 200 mm.',
            documentMetadata: { title: 'Guide de routage harnais', uri: 'https://exemple.test/doc/1', pageIdentifier: '12' } },
          { content: 'doublon', documentMetadata: { title: 'Guide de routage harnais', uri: 'https://exemple.test/doc/1' } },
          { content: 'Sans lien sûr', documentMetadata: { title: 'Note interne', uri: 'javascript:alert(1)' } }
        ]
      }
    } }
  ] } },
  { answer: { state: 'SUCCEEDED' }, sessionInfo: { session: APP + '/sessions/42' } }
]);

console.log('== Assistant : la page ==');
{
  const { gs } = assistant();
  const page = gs.doGet({ parameter: { q: 'Quelle distance ?' } });
  t('doGet() sert Page.html, titrée, avec la question venue du portail',
    page.gabarit.nom === 'Page' && page.gabarit.question === 'Quelle distance ?'
    && page.titre === 'Assistant documentaire ETII' && /width=device-width/.test(page.meta.viewport));
  t('sans question, la page s’ouvre vide', gs.doGet({ parameter: {} }).gabarit.question === '');
  t('une question trop longue est tronquée à 2 000 caractères',
    gs.doGet({ parameter: { q: 'x'.repeat(5000) } }).gabarit.question.length === 2000);
}

console.log('\n== Assistant : la question ==');
{
  const { gs, etat } = assistant({ corps: FLUX });
  const r = gs.etiiRepondre('  Quelle distance entre puissance et signal ?  ');
  const appel = etat.appels[0];
  t('l’appel part vers streamAssist v1, à l’adresse régionale de l’application',
    appel.url === 'https://eu-discoveryengine.googleapis.com/v1/' + APP + '/assistants/default_assistant:streamAssist', appel.url);
  t('au nom de la personne connectée (son jeton, aucune clé)',
    appel.options.headers.Authorization === 'Bearer jeton-de-la-personne' && !/key/i.test(appel.url));
  const corps = JSON.parse(appel.options.payload);
  t('le corps porte la question nettoyée, sans session au premier tour',
    corps.query.text === 'Quelle distance entre puissance et signal ?' && corps.session === undefined);
  t('la réponse assemble les morceaux dans l’ordre, sans la « pensée » du modèle',
    r.reponse === 'La distance minimale est de **200 mm** entre les deux faisceaux.', r.reponse);
  t('les sources : titre, lien, page, extrait resserré — sans doublon',
    r.sources.length === 2 && r.sources[0].titre === 'Guide de routage harnais'
    && r.sources[0].lien === 'https://exemple.test/doc/1' && r.sources[0].page === '12'
    && r.sources[0].extrait === 'Séparer les faisceaux de puissance et de signal d’au moins 200 mm.', JSON.stringify(r.sources));
  t('un lien qui n’est pas https n’est jamais rendu cliquable', r.sources[1].lien === '');
  t('la conversation est renvoyée pour les questions de suite', r.session === APP + '/sessions/42');

  gs.etiiRepondre('Et pour le blindage ?', r.session);
  t('une question de suite reprend la conversation', JSON.parse(etat.appels[1].options.payload).session === APP + '/sessions/42');
  gs.etiiRepondre('Autre ?', 'projects/autre/locations/eu/collections/c/engines/x/sessions/1');
  t('une conversation d’une autre application est ignorée', JSON.parse(etat.appels[2].options.payload).session === undefined);
}

console.log('\n== Assistant : les refus et les erreurs ==');
{
  const erreur = (f) => { try { f(); return ''; } catch (e) { return String(e.message); } };
  const { gs } = assistant({ corps: FLUX });
  t('une question vide est refusée', /vide/.test(erreur(() => gs.etiiRepondre('   '))));
  t('une question de plus de 2 000 caractères est refusée', /2000/.test(erreur(() => gs.etiiRepondre('x'.repeat(2001)))));
  t('sans propriété GEMINI_APP, l’assistant dit qu’il n’est pas relié',
    /pas encore relié/.test(erreur(() => assistant({ app: null }).gs.etiiRepondre('Q ?'))));
  t('une propriété mal formée est signalée',
    /doit avoir la forme/.test(erreur(() => assistant({ app: 'mon-app' }).gs.etiiRepondre('Q ?'))));
  const g = assistant({ app: 'projects/1/locations/global/collections/default_collection/engines/a' });
  g.gs.etiiRepondre('Q ?');
  t('une application « global » est appelée sans préfixe régional',
    g.etat.appels[0].url.indexOf('https://discoveryengine.googleapis.com/v1/projects/1/locations/global/') === 0);
  t('403 : licence ou rôle manquant, avec le message de Google',
    /licence Gemini Enterprise.*Permission denied/.test(erreur(() => assistant({ code: 403,
      corps: JSON.stringify([{ error: { code: 403, message: 'Permission denied' } }]) }).gs.etiiRepondre('Q ?'))));
  t('404 : application introuvable', /introuvable/.test(erreur(() => assistant({ code: 404, corps: '{}' }).gs.etiiRepondre('Q ?'))));
  t('une réponse illisible est signalée', /illisible/.test(erreur(() => assistant({ corps: '<html>' }).gs.etiiRepondre('Q ?'))));
  t('SKIPPED : la raison est traduite',
    /reformulez/.test(erreur(() => assistant({ corps: JSON.stringify([{ answer: { state: 'SKIPPED',
      assistSkippedReasons: ['NON_ASSIST_SEEKING_QUERY_IGNORED'] } }]) }).gs.etiiRepondre('Bonjour'))));
  t('FAILED : un échec est dit, pas une réponse vide',
    /pas pu terminer/.test(erreur(() => assistant({ corps: JSON.stringify([{ answer: { state: 'FAILED' } }]) }).gs.etiiRepondre('Q ?'))));
  const seul = assistant({ corps: JSON.stringify({ answer: { state: 'SUCCEEDED', replies: [
    { groundedContent: { content: { text: 'Réponse sans source.' } } }] } }) }).gs.etiiRepondre('Q ?');
  t('un objet unique (hors tableau) se lit aussi ; sans source, la liste est vide',
    seul.reponse === 'Réponse sans source.' && seul.sources.length === 0);
}

console.log('\n== Assistant : la page ne fabrique jamais de HTML à partir du texte ==');
{
  const page = lire('../tools/apps-script/assistant/Page.html');
  t('aucun innerHTML ni insertAdjacentHTML', !/innerHTML|insertAdjacentHTML|document\.write/.test(page));
  t('la question du portail passe par un scriptlet échappé (<?= ?>), jamais brut (<?!= ?>)',
    /<\?= question \?>/.test(page) && !/<\?!=/.test(page));
  t('les liens de sources s’ouvrent dans un nouvel onglet, sans opener', /noopener noreferrer/.test(page));
  const manifeste = JSON.parse(lire('../tools/apps-script/assistant/appsscript.json'));
  t('le manifeste : exécution en tant que l’utilisateur qui accède, réservée au domaine',
    manifeste.webapp.executeAs === 'USER_ACCESSING' && manifeste.webapp.access === 'DOMAIN');
  t('le manifeste demande les deux portées nécessaires, et elles seules',
    JSON.stringify(manifeste.oauthScopes.slice().sort()) === JSON.stringify([
      'https://www.googleapis.com/auth/cloud-platform',
      'https://www.googleapis.com/auth/script.external_request']));
}

/* ======================================================================
   2. Le remplissage du classeur des documents
   ====================================================================== */

function feuille(nom, lignes = []) {
  const f = {
    _lignes: lignes, nom,
    getName: () => nom,
    getLastRow: () => f._lignes.length,
    getLastColumn: () => Math.max(0, ...f._lignes.map((l) => l.length)),
    setFrozenRows: () => f,
    getRange: (l, c, nl = 1, nc = 1) => ({
      getValues: () => Array.from({ length: nl }, (_x, i) => Array.from({ length: nc }, (_y, j) => {
        const v = (f._lignes[l - 1 + i] || [])[c - 1 + j]; return v === undefined ? '' : v;
      })),
      setValues: (v) => v.forEach((ligne, i) => ligne.forEach((x, j) => {
        while (f._lignes.length < l + i) f._lignes.push([]);
        f._lignes[l - 1 + i][c - 1 + j] = x;
      }))
    })
  };
  return f;
}

function fichier(id, nom, date = new Date('2026-09-01T08:00:00Z')) {
  return { getId: () => id, getName: () => nom, getLastUpdated: () => date, getUrl: () => 'https://exemple.test/file/d/' + id + '/view' };
}

function indexeur({ dossiers, arbre, onglets = {}, horloge }) {
  const classeur = {
    onglets,
    getSheetByName: (n) => onglets[n] || null,
    insertSheet: (n) => (onglets[n] = feuille(n))
  };
  const etat = { declencheurs: [], proprietes: {}, journal: [] };
  const contexte = {
    SpreadsheetApp: { getActiveSpreadsheet: () => classeur },
    DriveApp: {
      getFolderById: (id) => ({
        getFolders: () => parcours((arbre[id].dossiers || []).map((s) => ({ getId: () => s.id, getName: () => s.nom })), id),
        getFiles: () => parcours(arbre[id].fichiers || [], id)
      }),
      continueFileIterator: (jeton) => { const [id, pos] = jeton.split(':'); return parcours(arbre[id].fichiers, id, Number(pos)); }
    },
    PropertiesService: { getScriptProperties: () => ({
      getProperty: (k) => (k in etat.proprietes ? etat.proprietes[k] : null),
      setProperty: (k, v) => { etat.proprietes[k] = v; },
      deleteProperty: (k) => { delete etat.proprietes[k]; }
    }) },
    ScriptApp: {
      getProjectTriggers: () => etat.declencheurs,
      deleteTrigger: (d) => { etat.declencheurs = etat.declencheurs.filter((x) => x !== d); },
      newTrigger: (fn) => {
        const d = { getHandlerFunction: () => fn };
        const b = { timeBased: () => b, after: () => b, everyDays: () => b, atHour: () => b, create: () => { etat.declencheurs.push(d); return d; } };
        return b;
      }
    },
    Logger: { log: (m) => etat.journal.push(String(m)) },
    Date: horloge ? class extends Date { static now() { return horloge(); } } : Date,
    console
  };
  function parcours(liste, id, depart = 0) {
    let i = depart;
    return { hasNext: () => i < liste.length, next: () => liste[i++], getContinuationToken: () => id + ':' + i };
  }
  vm.createContext(contexte);
  const code = lire('../tools/apps-script/index-documents.gs')
    .replace(/var DOSSIERS_POLES = \{[^}]*\};/, 'var DOSSIERS_POLES = ' + JSON.stringify(dossiers) + ';');
  vm.runInContext(code, contexte, { filename: 'index-documents.gs' });
  return { gs: contexte, classeur, etat };
}

console.log('\n== Classeur des documents : remplissage depuis Drive ==');
{
  const arbre = {
    racineA: { dossiers: [{ id: 'guidesA', nom: 'Guides' }], fichiers: [fichier('A'.repeat(28), 'Organisation du pôle.pdf')] },
    guidesA: { dossiers: [{ id: 'harnaisA', nom: 'Harnais' }], fichiers: [fichier('B'.repeat(28), 'ETII-TEC-001_indice-C_routage-harnais.pdf')] },
    harnaisA: { fichiers: [fichier('C'.repeat(28), 'ETIIA-NT-0042 Blindage.docx')] }
  };
  const existant = feuille('ETIIA', [
    ['Titre', 'Référence', 'Type', 'Métier', 'Porteur', 'Périmètre', 'Mise à jour', 'Lien', 'Description'],
    ['Organisation (complétée à la main)', '', 'Note', 'Harnais', 'Personne 01', '', '2026-01-01',
      'https://exemple.test/file/d/' + 'A'.repeat(28) + '/view', 'Décrite à la main']
  ]);
  const { gs, classeur, etat } = indexeur({ dossiers: { ETIIA: 'racineA', ETIIE: '', ETIII: '' }, arbre, onglets: { ETIIA: existant } });
  const bilan = gs.indexerDocuments();
  const l = classeur.onglets.ETIIA._lignes;
  t('les fichiers nouveaux sont ajoutés, celui déjà listé est reconnu par son identifiant Drive',
    bilan.ajoutes === 2 && bilan.deja === 1 && l.length === 4, JSON.stringify(bilan));
  t('la ligne existante, complétée à la main, n’est pas touchée',
    l[1][0] === 'Organisation (complétée à la main)' && l[1][8] === 'Décrite à la main' && l[1][4] === 'Personne 01');
  const guide = l.find((x) => /routage/.test(x[0]));
  t('titre sans extension, référence lue dans le nom, type = premier sous-dossier, date et lien',
    guide && guide[0] === 'ETII-TEC-001_indice-C_routage-harnais' && guide[1] === 'ETII-TEC-001' && guide[2] === 'Guides'
    && guide[6] instanceof Date && /B{28}/.test(guide[7]), JSON.stringify(guide));
  const blindage = l.find((x) => /Blindage/.test(x[0]));
  t('un sous-sous-dossier garde le type de son premier niveau ; « ETIIA-NT-0042 » suivi d’une espace est lu',
    blindage && blindage[2] === 'Guides' && blindage[1] === 'ETIIA-NT-0042', JSON.stringify(blindage));
  t('les pôles sans dossier sont sautés, sans créer d’onglet', !classeur.onglets.ETIIE && !classeur.onglets.ETIII);
  const encore = gs.indexerDocuments();
  t('relancé, rien n’est ajouté deux fois', encore.ajoutes === 0 && encore.deja === 3 && classeur.onglets.ETIIA._lignes.length === 4);
  t('le bilan est écrit dans le journal', etat.journal.some((m) => /Terminé : 0 fichiers ajoutés, 3 déjà présents/.test(m)));
}

console.log('\n== Classeur des documents : onglet vide et milliers de fichiers ==');
{
  const beaucoup = Array.from({ length: 30 }, (_x, i) => fichier(String(i).padStart(28, 'x'), 'Doc ' + i + '.pdf'));
  let temps = 0;
  const { gs, classeur, etat } = indexeur({
    dossiers: { ETIIA: '', ETIIE: 'racineE', ETIII: '' },
    arbre: { racineE: { fichiers: beaucoup } },
    horloge: () => (temps += 20 * 1000)       // chaque fichier « coûte » 20 s
  });
  gs.indexerDocuments();
  const e = classeur.onglets.ETIIE;
  t('un onglet absent est créé avec l’en-tête que lit le site',
    e._lignes[0].join('|') === 'Titre|Référence|Type|Métier|Porteur|Périmètre|Mise à jour|Lien|Description|Mots-clés|Remplacé par');
  const avant = e._lignes.length - 1;
  t('passé 5 minutes, le script s’arrête proprement en gardant ce qu’il a lu',
    avant > 0 && avant < 30 && etat.proprietes.INDEX_REPRISE, String(avant));
  t('et programme sa reprise', etat.declencheurs.some((d) => d.getHandlerFunction() === 'reprendreIndexation'));
  temps = 0;
  let tours = 0;
  while (etat.proprietes.INDEX_REPRISE && tours++ < 20) { temps = 0; gs.reprendreIndexation(); }
  const ids = e._lignes.slice(1).map((l) => l[7]);
  t('les reprises vont jusqu’au bout : 30 fichiers, chacun une seule fois',
    ids.length === 30 && new Set(ids).size === 30, String(ids.length));
  t('à la fin, plus de déclencheur de reprise ni de note de reprise',
    !etat.declencheurs.some((d) => d.getHandlerFunction() === 'reprendreIndexation') && !etat.proprietes.INDEX_REPRISE);
  gs.planifierChaqueNuit(); gs.planifierChaqueNuit();
  t('planifierChaqueNuit() ne pose qu’un seul déclencheur, même relancée',
    etat.declencheurs.filter((d) => d.getHandlerFunction() === 'indexerDocuments').length === 1);
}

console.log(`\n  ${ok} réussis, ${ko} échoués`);
process.exit(ko ? 1 : 0);
