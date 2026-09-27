// L'assistant documentaire (tools/apps-script/assistant/Code.gs), son
// raccordement au portail (assets/js/assistant.js) et le remplissage du
// classeur des documents (tools/apps-script/index-documents.gs), exécutés
// ici contre des doublures des services Google :
//   node tests/assistant-gemini.test.mjs
//
// Les réponses simulées suivent les formes documentées (vérifiées le
// 26 septembre 2026) : Drive API v3 files.list / files.get / files.export,
// Agent Platform API v1 generateContent (GenerateContentResponse) et
// Discovery Engine v1 streamAssist (un tableau JSON de morceaux).

import { readFileSync } from 'node:fs';
import vm from 'node:vm';

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK   ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };
const lire = (chemin) => readFileSync(new URL(chemin, import.meta.url), 'utf8');
const erreur = (f) => { try { f(); return ''; } catch (e) { return String(e.message); } };
const json = (x) => JSON.stringify(x);

/* ======================================================================
   1. L'assistant : les doublures
   ====================================================================== */

const APP = 'projects/123/locations/eu/collections/default_collection/engines/etii-docs';
const DRIVE_A = '0AdriveA-0123456789';
const DRIVE_B = '0AdriveB-0123456789';

/**
 * Un Code.gs chargé dans une machine virtuelle, avec :
 *  - proprietes  : les propriétés du script ;
 *  - lister      : (params) => fichiers, la réponse de Drive.Files.list ;
 *  - dossiers    : id → { name, parents }, pour files.get ;
 *  - contenus    : id → texte (export ou alt=media) ;
 *  - octets      : id → octets d'un PDF (alt=media) ;
 *  - vertex / enterprise : { code, corps } de l'API du modèle ;
 *  - erreurDrive : le message d'erreur de Drive.Files.list, pour tout Drive,
 *    ou { identifiant du Drive : message } pour certains seulement.
 */
function assistant({ proprietes = {}, lister = () => [], dossiers = {}, contenus = {}, octets = {},
  vertex = { code: 200, corps: '{}' }, enterprise = { code: 200, corps: '[]' }, sansDrive = false, erreurDrive = null } = {}) {
  const etat = { appels: [], listes: [], salves: [], cache: {}, mises: 0 };
  const repondre = (url, options = {}) => {
    etat.appels.push({ url, options });
    const r = (code, corps, brut) => ({
      getResponseCode: () => code,
      getContentText: () => (typeof corps === 'function' ? corps() : corps),
      getBlob: () => ({ getBytes: () => brut || [] })
    });
    let m;
    if (/aiplatform/.test(url)) return r(vertex.code, vertex.corps);
    if (/discoveryengine/.test(url)) return r(enterprise.code, enterprise.corps);
    if ((m = /\/drive\/v3\/files\/([^/?]+)\/export\?mimeType=([^&]+)$/.exec(url))) {
      const id = decodeURIComponent(m[1]);
      return id in contenus ? r(200, contenus[id]) : r(404, '{"error":{"message":"File not found"}}');
    }
    if ((m = /\/drive\/v3\/files\/([^/?]+)\?alt=media&supportsAllDrives=true$/.exec(url))) {
      const id = decodeURIComponent(m[1]);
      if (id in octets) return r(200, '', octets[id]);
      return id in contenus ? r(200, contenus[id]) : r(404, '{}');
    }
    if ((m = /\/drive\/v3\/files\/([^/?]+)\?fields=id%2Cname%2Cparents&supportsAllDrives=true$/.exec(url))) {
      const id = decodeURIComponent(m[1]);
      return id in dossiers ? r(200, json(Object.assign({ id }, dossiers[id]))) : r(404, '{}');
    }
    return r(500, 'adresse inattendue');
  };
  const contexte = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (k in proprietes ? proprietes[k] : null) }) },
    ScriptApp: { getOAuthToken: () => 'jeton-de-la-personne' },
    UrlFetchApp: {
      fetch: (url, options) => repondre(url, options),
      fetchAll: (requetes) => { etat.salves.push(requetes.length); return requetes.map((q) => repondre(q.url, q)); }
    },
    CacheService: { getUserCache: () => ({
      getAll: (cles) => { const o = {}; cles.forEach((k) => { if (k in etat.cache) o[k] = etat.cache[k]; }); return o; },
      putAll: (o, duree) => { Object.assign(etat.cache, o); etat.mises++; etat.duree = duree; }
    }) },
    Utilities: { base64Encode: (b) => Buffer.from(b).toString('base64') },
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
  if (!sansDrive) {
    contexte.Drive = { Files: { list: (params) => {
      etat.listes.push(params);
      const message = typeof erreurDrive === 'string' ? erreurDrive : (erreurDrive && erreurDrive[params.driveId]);
      if (message) throw new Error(message);
      return { files: lister(params) };
    } } };
  }
  vm.createContext(contexte);
  vm.runInContext(lire('../tools/apps-script/assistant/Code.gs'), contexte, { filename: 'assistant/Code.gs' });
  return { gs: contexte, etat };
}

/* Un petit fonds : deux Drive partagés, des dossiers par pôle et par type. */
const DOSSIERS = {
  dA: { name: 'ETIIA', parents: [DRIVE_A] },
  dAg: { name: 'Guides', parents: ['dA'] },
  dAgh: { name: 'Harnais', parents: ['dAg'] },
  dB: { name: 'ETIIE', parents: [DRIVE_B] },
  dBp: { name: 'Procédures', parents: ['dB'] }
};
const doc = (id, name, mimeType, parents, extra = {}) => Object.assign(
  { id, name, mimeType, parents, modifiedTime: '2026-03-03T09:00:00.000Z', webViewLink: 'https://exemple.test/d/' + id }, extra);
const GUIDE = doc('gd1', 'Guide de routage harnais', 'application/vnd.google-apps.document', ['dAg']);
const TEC = doc('pdf1', 'ETII-TEC-001_indice-C_routage-harnais.pdf', 'application/pdf', ['dAgh'], { size: '2048' });
const NOTE = doc('w1', 'Note blindage.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', ['dA']);
const RACINE = doc('t1', 'Lisez-moi.txt', 'text/plain', [DRIVE_A], { size: '120', webViewLink: 'javascript:alert(1)' });
const FEUILLE = doc('sh1', 'Tableau des distances', 'application/vnd.google-apps.spreadsheet', ['dBp'], { description: 'Distances   de ségrégation' });
const TEXTE_GUIDE = 'Introduction. Le présent guide fixe les règles de routage. '.repeat(8)
  + 'Il faut séparer les faisceaux de puissance et les faisceaux de signal d’au moins 200 mm, '
  + 'sauf dérogation écrite. ' + 'Annexe sans rapport. '.repeat(20);

/* ======================================================================
   2. L'assistant : les tests
   ====================================================================== */

console.log('== Assistant : le niveau et la page ==');
{
  const texte = assistant();
  const page = texte.gs.doGet({ parameter: { q: 'Quelle distance ?' } });
  t('doGet() sert Page.html, titrée, avec la question venue du portail',
    page.gabarit.nom === 'Page' && page.gabarit.question === 'Quelle distance ?'
    && page.titre === 'Assistant documentaire ETII' && /width=device-width/.test(page.meta.viewport));
  t('sans propriété, le niveau est « texte » et la page dit « Chercher dans le texte des documents »',
    page.gabarit.mode === 'texte' && page.gabarit.titre === 'Chercher dans le texte des documents' && page.gabarit.bouton === 'Chercher');
  t('sans question, la page s’ouvre vide', texte.gs.doGet({ parameter: {} }).gabarit.question === '');
  t('une question trop longue est tronquée à 2 000 caractères',
    texte.gs.doGet({ parameter: { q: 'x'.repeat(5000) } }).gabarit.question.length === 2000);
  const vertex = assistant({ proprietes: { VERTEX_PROJET: 'etii-docs', DRIVE_PARTAGE: DRIVE_A } }).gs.doGet({});
  t('VERTEX_PROJET renseigné : niveau « vertex », la page demande', vertex.gabarit.mode === 'vertex' && vertex.gabarit.bouton === 'Demander');
  const tout = assistant({ proprietes: { GEMINI_APP: APP, VERTEX_PROJET: 'etii-docs', DRIVE_PARTAGE: DRIVE_A } }).gs.doGet({});
  t('GEMINI_APP l’emporte sur tout : niveau « enterprise »', tout.gabarit.mode === 'enterprise');
  t('des propriétés faites d’espaces ne comptent pas',
    assistant({ proprietes: { GEMINI_APP: '   ', VERTEX_PROJET: ' ' } }).gs.doGet({}).gabarit.mode === 'texte');
}

console.log('\n== Niveau 1 : la question devient des mots ==');
{
  const { gs } = assistant();
  const mots = (q) => json(gs.analyser_(q).map((m) => m.texte));
  t('les mots vides tombent, l’apostrophe sépare, les doublons aussi',
    mots('Quelle est la distance entre l’intégration et les faisceaux ? Distance !') === json(['distance', 'intégration', 'faisceaux']),
    mots('Quelle est la distance entre l’intégration et les faisceaux ? Distance !'));
  t('une référence, un nombre décimal et un mot composé restent entiers',
    mots('ETII-TEC-001 indice 0,5 mm anti-parasitage') === json(['ETII-TEC-001', 'indice', '0,5', 'mm', 'anti-parasitage']));
  t('une expression entre guillemets (droits ou français) reste entière',
    mots('« routage harnais » "plan de masse" cuivre') === json(['routage harnais', 'plan de masse', 'cuivre']));
  t('au plus six mots', gs.analyser_('un deux trois quatre cinq six sept huit neuf dix onze douze')
    .length === 6);
  const f = gs.analyser_('Intégrations')[0];
  t('chaque mot porte ses variantes : accent et nombre',
    json(f.variantes) === json(['intégrations', 'integrations', 'intégration', 'integration']), json(f.variantes));
  t('pluriels en -aux et -eaux', json(gs.analyser_('signaux')[0].variantes) === json(['signaux', 'signal'])
    && json(gs.analyser_('réseau')[0].variantes) === json(['réseau', 'reseau', 'réseaux', 'reseaux']));
  t('une expression ne change que d’accents', json(gs.analyser_('"câble blindé"')[0].variantes) === json(['câble blindé', 'cable blinde']));
  const nfd = 'Quelle re\u0301sistance d’isolement ?';
  t('une question aux accents décomposés (NFD, collée d’un PDF) garde ses mots entiers',
    mots(nfd) === json(['résistance', 'isolement']) && gs.analyser_(nfd)[0].variantes.indexOf('resistance') !== -1, mots(nfd));
  t('une question sans mot utile est refusée clairement',
    /Précisez ce qu’il faut chercher/.test(erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A } }).gs.etiiRepondre('Est-ce que c’est quoi ?'))));
}

console.log('\n== Niveau 1 : la requête Drive ==');
{
  const { gs } = assistant();
  t('\\ et \' sont échappés', gs.echapper_('quinn\'s paper\\essay') === 'quinn\\\'s paper\\\\essay');
  const q = gs.requeteDrive_(gs.analyser_('faisceaux "l\'avion" ETII-TEC-001'), 'and');
  t('une requête : hors corbeille, sans dossiers ni raccourcis, un groupe par mot, variantes en « or », expressions entre guillemets',
    q === 'trashed = false and mimeType != \'application/vnd.google-apps.folder\''
      + ' and mimeType != \'application/vnd.google-apps.shortcut\' and ('
      + 'fullText contains \'"l\\\'avion"\' and (fullText contains \'faisceaux\' or fullText contains \'faisceau\')'
      + ' and fullText contains \'"etii-tec-001"\')', q);
  t('liaison « or » pour la recherche élargie',
    / or fullText contains 'faisceau'\) or \(fullText contains 'avion'/.test(gs.requeteDrive_(gs.analyser_('faisceaux avion'), 'or')));
  t('entre guillemets, même un mot courant est cherché, tel quel',
    gs.requeteDrive_(gs.analyser_('"sans"'), 'and').indexOf('fullText contains \'"sans"\'') !== -1);

  const e = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, lister: () => [] });
  e.gs.etiiRepondre('faisceaux puissance');
  const p = e.etat.listes[0];
  t('Drive.Files.list : Drive partagé ciblé, champs choisis, 20 au plus, aucun tri (refusé avec fullText)',
    p.corpora === 'drive' && p.driveId === DRIVE_A && p.includeItemsFromAllDrives === true && p.supportsAllDrives === true
    && p.pageSize === 20 && p.orderBy === undefined
    && p.fields === 'files(id,name,mimeType,modifiedTime,webViewLink,parents,description,size)', json(p));
  t('aucun résultat avec tous les mots : une seconde requête, avec au moins un mot',
    e.etat.listes.length === 2 && / and \(\(fullText/.test(e.etat.listes[0].q) && /\) or \(fullText/.test(e.etat.listes[1].q));
  const seul = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A } });
  seul.gs.etiiRepondre('faisceaux');
  t('un seul mot : pas de seconde requête', seul.etat.listes.length === 1);
}

console.log('\n== Niveau 1 : les documents, leur place, leur extrait ==');
{
  const lister = (p) => (p.driveId === DRIVE_A ? [GUIDE, TEC, NOTE, RACINE] : [FEUILLE]);
  const { gs, etat } = assistant({
    proprietes: { DRIVE_PARTAGE: 'https://exemple.test/drive/folders/' + DRIVE_A + ' , ' + DRIVE_B },
    lister, dossiers: DOSSIERS,
    contenus: { gd1: TEXTE_GUIDE, sh1: 'Distance;Valeur\nPuissance-signal;200 mm', t1: 'rien' }
  });
  const r = gs.etiiRepondre('distance faisceau puissance signal');
  const titres = r.documents.map((d) => d.titre);
  t('le mode est dit, les mots aussi', r.mode === 'texte' && json(r.mots) === json(['distance', 'faisceau', 'puissance', 'signal']));
  t('l’adresse collée depuis Drive vaut identifiant ; deux Drive partagés sont interrogés',
    etat.listes.length === 2 && etat.listes[0].driveId === DRIVE_A && etat.listes[1].driveId === DRIVE_B);
  t('les deux Drive sont entrelacés, dans leur ordre de pertinence',
    json(titres) === json(['Guide de routage harnais', 'Tableau des distances', 'ETII-TEC-001_indice-C_routage-harnais', 'Note blindage', 'Lisez-moi']), json(titres));
  const guide = r.documents[0];
  const tec = r.documents[2];
  t('la place d’un document : pôle, puis type, depuis la racine du Drive partagé',
    guide.lieu === 'ETIIA › Guides' && guide.pole === 'ETIIA' && guide.type === 'Guides'
    && tec.lieu === 'ETIIA › Guides' && r.documents[1].lieu === 'ETIIE › Procédures', json(r.documents.map((d) => d.lieu)));
  t('un fichier à la racine n’a pas de lieu', r.documents[4].lieu === '');
  t('les dossiers sont lus par étage, en salves, puis gardés dans le cache de la personne (6 h)',
    etat.salves.length >= 3 && etat.cache['dossier:dAg'] && JSON.parse(etat.cache['dossier:dAg']).nom === 'Guides' && etat.duree === 21600);
  t('format, date, lien https ; l’extension tombe du titre d’un fichier importé',
    tec.format === 'PDF' && guide.format === 'Google Docs' && r.documents[3].format === 'Word'
    && guide.modifie === '2026-03-03T09:00:00.000Z' && guide.lien === 'https://exemple.test/d/gd1' && r.documents[4].lien === '');
  t('un Google Docs est lisible, un PDF ou un Word ne l’est pas sans ouvrir',
    guide.lisible === true && tec.lisible === false && r.documents[3].lisible === false);
  const marques = guide.extrait.filter((s) => s.marque).map((s) => s.texte);
  t('l’extrait du Google Docs est la fenêtre où se trouvent les mots, marqués sans HTML',
    json(marques) === json(['faisceaux', 'puissance', 'faisceaux', 'signal']) && guide.extrait[0].texte === '…'
    && guide.extrait.every((s) => typeof s.texte === 'string' && !/</.test(s.texte)), json(guide.extrait));
  t('« faisceau » marque « faisceaux » ; « distance » (absent du passage) n’est pas inventé',
    !guide.extrait.some((s) => s.marque && /distance/i.test(s.texte)));
  t('un Google Sheets est exporté en CSV et donne son extrait',
    r.documents[1].extrait.some((s) => s.marque && /Distance/.test(s.texte)));
  t('seuls les formats lisibles sont téléchargés (export Docs/Sheets, texte brut)',
    etat.appels.filter((a) => /export|alt=media/.test(a.url)).length === 3
    && etat.appels.some((a) => /files\/gd1\/export\?mimeType=text%2Fplain$/.test(a.url))
    && etat.appels.some((a) => /files\/sh1\/export\?mimeType=text%2Fcsv$/.test(a.url))
    && !etat.appels.some((a) => /pdf1|w1/.test(a.url) && /export|alt=media/.test(a.url)));
  t('chaque appel à Drive porte le jeton de la personne, jamais de clé',
    etat.appels.every((a) => a.options.headers.Authorization === 'Bearer jeton-de-la-personne' && !/key=/i.test(a.url)));
  t('la description Drive est rendue, resserrée', r.documents[1].description === 'Distances de ségrégation');

  const ex = gs.extrait_('Début. ' + 'abcdefghij '.repeat(40) + 'Le CÂBLE blindé est relié à la masse. ' + 'klmnopqrst '.repeat(40), gs.analyser_('cable masse'));
  t('l’extrait ignore accents et casse, et ne coupe pas les mots à ses bords',
    ex.filter((s) => s.marque).map((s) => s.texte).join('|') === 'CÂBLE|masse'
    && ex[0].texte === '…' && /^(abcdefghij )+Le $/.test(ex[1].texte)
    && /\. (klmnopqrst )*klmnopqrst$/.test(ex[ex.length - 2].texte) && ex[ex.length - 1].texte === '…', json(ex));
  const decompose = gs.extrait_('La re\u0301sistance d’isolement est mesurée sous 500 V.', gs.analyser_('résistance'));
  t('un texte aux accents décomposés (NFD) est marqué quand même, et rendu composé',
    decompose.some((s) => s.marque && s.texte === 'résistance'), json(decompose));
  const aucun = gs.extrait_('Un texte sans les mots cherchés.', gs.analyser_('harnais'));
  t('sans occurrence, l’extrait est le début du texte, sans marque', aucun.length === 1 && !aucun[0].marque);
  t('un mot marqué doit commencer un mot (« signal » ne marque pas « désignal »)',
    !gs.extrait_('désignal et signal', gs.analyser_('signal')).some((s) => s.marque && s.texte === 'désignal'));

  const encore = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, lister: () => [GUIDE], dossiers: DOSSIERS, contenus: { gd1: TEXTE_GUIDE } });
  encore.etat.cache['dossier:dAg'] = json({ nom: 'Guides', parent: 'dA' });
  encore.etat.cache['dossier:dA'] = json({ nom: 'ETIIA', parent: DRIVE_A });
  const r2 = encore.gs.etiiRepondre('faisceaux');
  t('un dossier déjà en cache n’est pas relu', r2.documents[0].lieu === 'ETIIA › Guides'
    && !encore.etat.appels.some((a) => /fields=id%2Cname/.test(a.url)));
  const perdu = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, lister: () => [GUIDE], dossiers: { dAg: DOSSIERS.dAg } });
  t('un chemin qui n’atteint pas la racine n’est pas montré (plutôt rien que faux)',
    perdu.gs.etiiRepondre('faisceaux').documents[0].lieu === '');
}

console.log('\n== Niveau 1 : la recherche élargie et les erreurs ==');
{
  const lister = (p) => (/\) or \(/.test(p.q) || / or fullText contains 'puissance'\)?$/.test(p.q) ? [GUIDE] : []);
  const e = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, lister, dossiers: DOSSIERS, contenus: { gd1: TEXTE_GUIDE } });
  const r = e.gs.etiiRepondre('faisceaux puissance');
  t('rien avec tous les mots, quelque chose avec l’un d’eux : la réponse est dite « élargie »',
    r.elargie === true && r.documents.length === 1, json(r));
  const rien = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A } }).gs.etiiRepondre('faisceaux puissance');
  t('rien du tout : une liste vide, pas « élargie »', rien.documents.length === 0 && rien.elargie === false);
  t('sans DRIVE_PARTAGE, l’assistant dit qu’il n’est pas relié',
    /pas encore relié.*DRIVE_PARTAGE/.test(erreur(() => assistant().gs.etiiRepondre('harnais'))));
  t('une valeur qui n’est pas un identifiant ne compte pas',
    /DRIVE_PARTAGE/.test(erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: 'mon drive' } }).gs.etiiRepondre('harnais'))));
  t('sans le service avancé Drive, le message dit quoi recopier',
    /service avancé Drive.*appsscript\.json/.test(erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, sansDrive: true }).gs.etiiRepondre('harnais'))));
  t('un Drive partagé introuvable est nommé',
    /Drive partagé introuvable \(0AdriveA/.test(erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A },
      erreurDrive: 'API call to drive.files.list failed with error: Shared drive not found: 0AdriveA' }).gs.etiiRepondre('harnais'))));
  const fermeB = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B }, dossiers: DOSSIERS, contenus: { gd1: TEXTE_GUIDE },
    lister: (p) => (p.driveId === DRIVE_A ? [GUIDE] : [FEUILLE]),
    erreurDrive: { [DRIVE_B]: 'API call to drive.files.list failed with error: Shared drive not found: ' + DRIVE_B } });
  const rB = fermeB.gs.etiiRepondre('faisceaux');
  t('deux Drive partagés, dont un fermé à la personne : les résultats de l’autre, et le Drive sauté est compté',
    rB.documents.length === 1 && rB.documents[0].titre === 'Guide de routage harnais' && rB.ignores === 1, json(rB));
  const refusA = assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B },
    lister: (p) => (/\) or \(/.test(p.q) ? [FEUILLE] : []),
    erreurDrive: { [DRIVE_A]: 'The user does not have sufficient permissions for this file' } });
  const rA = refusA.gs.etiiRepondre('faisceaux puissance');
  t('la recherche élargie ne réinterroge pas le Drive fermé',
    rA.elargie === true && rA.ignores === 1 && refusA.etat.listes.filter((l) => l.driveId === DRIVE_A).length === 1
    && refusA.etat.listes.filter((l) => l.driveId === DRIVE_B).length === 2, json(refusA.etat.listes.map((l) => l.driveId)));
  const tousFermes = erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B },
    erreurDrive: 'Shared drive not found' }).gs.etiiRepondre('harnais'));
  t('tous les Drive partagés fermés : une erreur claire, qui les compte', /Aucun des 2 Drive partagés/.test(tousFermes), tousFermes);
  const autreErreur = erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B }, lister: () => [GUIDE],
    erreurDrive: { [DRIVE_B]: 'Invalid Value' } }).gs.etiiRepondre('harnais'));
  t('une erreur qui ne tient pas aux droits arrête tout, même si l’autre Drive répond',
    /La recherche dans Drive a échoué : Invalid Value/.test(autreErreur), autreErreur);
  const portee = erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B },
    erreurDrive: 'Request had insufficient authentication scopes.' }).gs.etiiRepondre('harnais'));
  t('une portée Drive manquante n’est pas prise pour un Drive fermé : le manifeste est nommé',
    /portée « drive\.readonly » manque/.test(portee) && !/membre/.test(portee), portee);
  t('un seul Drive partagé et tout va bien : rien d’ignoré',
    assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A }, lister: () => [GUIDE], dossiers: DOSSIERS }).gs.etiiRepondre('faisceaux').ignores === 0);
  t('un refus de Drive dit qu’il faut en être membre',
    /il faut en être membre/.test(erreur(() => assistant({ proprietes: { DRIVE_PARTAGE: DRIVE_A },
      erreurDrive: 'The user does not have sufficient permissions' }).gs.etiiRepondre('harnais'))));
}

console.log('\n== Niveau 2 : Gemini lit les documents trouvés ==');
const REPONSE_VERTEX = json({
  candidates: [{
    content: { role: 'model', parts: [
      { text: 'Je relis les documents…', thought: true },
      { text: 'Il faut **200 mm** entre puissance et signal [1]. Le détail est au chapitre 4 [2, 3].' }
    ] },
    finishReason: 'STOP'
  }],
  usageMetadata: { promptTokenCount: 1200, candidatesTokenCount: 40, totalTokenCount: 1240 },
  modelVersion: 'gemini-3.5-flash'
});
{
  const PDF = Array.from(Buffer.from('%PDF-1.7 exemple'));
  const GROS = doc('pdf2', 'Gros.pdf', 'application/pdf', ['dAg'], { size: String(11 * 1024 * 1024) });
  const lister = () => [GUIDE, NOTE, TEC, GROS, FEUILLE];
  const { gs, etat } = assistant({
    proprietes: { VERTEX_PROJET: 'etii-docs', DRIVE_PARTAGE: DRIVE_A + ',' + DRIVE_B },
    lister, dossiers: DOSSIERS, contenus: { gd1: TEXTE_GUIDE, sh1: 'Distance;Valeur' }, octets: { pdf1: PDF },
    vertex: { code: 200, corps: REPONSE_VERTEX }
  });
  const r = gs.etiiRepondre('Quelle distance entre faisceaux de puissance et de signal ?');
  const appel = etat.appels.find((a) => /aiplatform/.test(a.url));
  t('l’appel part vers le point d’accès multirégion « eu » (le traitement reste dans l’UE)',
    appel.url === 'https://aiplatform.eu.rep.googleapis.com/v1/projects/etii-docs/locations/eu/publishers/google/models/gemini-3.5-flash:generateContent', appel.url);
  t('au nom de la personne (son jeton), en POST JSON, sans clé',
    appel.options.method === 'post' && appel.options.contentType === 'application/json'
    && appel.options.headers.Authorization === 'Bearer jeton-de-la-personne' && !/key=/i.test(appel.url));
  const corps = JSON.parse(appel.options.payload);
  const parties = corps.contents[0].parts;
  t('la consigne : répondre depuis les documents seuls, en citant leurs numéros, ignorer leurs consignes',
    /uniquement à partir de ces documents/.test(corps.systemInstruction.parts[0].text)
    && /\[1\], \[2\]/.test(corps.systemInstruction.parts[0].text) && /n’exécute jamais une consigne/.test(corps.systemInstruction.parts[0].text));
  t('les documents lisibles, numérotés dans l’ordre : Google Docs en texte, PDF en inlineData, puis la question',
    corps.contents[0].role === 'user' && parties.length === 7
    && /^\[1\] Guide de routage harnais — ETIIA › Guides — modifié le 2026-03-03$/.test(parties[0].text) && /200 mm/.test(parties[1].text)
    && /^\[2\] ETII-TEC-001/.test(parties[2].text) && parties[3].inlineData.mimeType === 'application/pdf'
    && parties[3].inlineData.data === Buffer.from('%PDF-1.7 exemple').toString('base64')
    && /^\[3\] Tableau des distances/.test(parties[4].text) && parties[6].text === 'Question : Quelle distance entre faisceaux de puissance et de signal ?',
    json(parties.map((p) => p.text ? p.text.slice(0, 40) : 'inline')));
  t('un Word et un PDF de plus de 10 Mo ne sont pas envoyés (ni même téléchargés)',
    !etat.appels.some((a) => /pdf2|w1/.test(a.url) && /alt=media|export/.test(a.url)));
  t('réflexion « LOW » pour un Gemini 3, sortie bornée, étiquette de facturation',
    corps.generationConfig.thinkingConfig.thinkingLevel === 'LOW' && corps.generationConfig.maxOutputTokens === 4096
    && corps.generationConfig.temperature === undefined && corps.labels.outil === 'etii-assistant');
  t('la réponse, sans la « pensée » du modèle', r.mode === 'vertex' && r.reponse === 'Il faut **200 mm** entre puissance et signal [1]. Le détail est au chapitre 4 [2, 3].');
  const lus = r.documents.filter((d) => d.numero);
  t('les documents lus portent leur numéro et s’ils sont cités ; les autres restent listés',
    lus.length === 3 && lus.every((d) => d.cite) && r.documents.length === 5
    && r.documents.find((d) => d.titre === 'Note blindage').numero === undefined, json(r.documents.map((d) => [d.titre, d.numero, d.cite])));
  t('le Google Docs lu garde son extrait', lus[0].extrait.some((s) => s.marque));
  t('le modèle qui a répondu est dit', r.modele === 'gemini-3.5-flash' && r.tronquee === false);

  const citations = gs.citations_('A [1]. B [2; 4] et [3,5]. Pas [x].');
  t('les renvois [1], [2; 4], [3,5] sont tous lus', json(Object.keys(citations).sort()) === json(['1', '2', '3', '4', '5']));
}

console.log('\n== Niveau 2 : l’adresse, les coûts évités, les refus ==');
{
  const cible = (p) => assistant().gs.cibleVertex_(Object.assign({ projet: 'etii-docs', region: '', modele: '' }, p));
  t('région « europe-west3 » : l’adresse régionale', cible({ region: 'europe-west3' }).adresse
    === 'https://europe-west3-aiplatform.googleapis.com/v1/projects/etii-docs/locations/europe-west3/publishers/google/models/gemini-3.5-flash:generateContent');
  t('« global » : sans préfixe', cible({ region: 'global' }).adresse.indexOf('https://aiplatform.googleapis.com/v1/projects/etii-docs/locations/global/') === 0);
  t('VERTEX_MODELE remplace le modèle par défaut', /models\/gemini-3\.5-flash-lite:generateContent$/.test(cible({ modele: 'gemini-3.5-flash-lite' }).adresse));
  t('des propriétés mal formées sont refusées avant tout appel',
    /VERTEX_PROJET/.test(erreur(() => cible({ projet: 'Mon Projet!' })))
    && /VERTEX_REGION/.test(erreur(() => cible({ region: 'paris' })))
    && /VERTEX_MODELE/.test(erreur(() => cible({ modele: '../autre' }))));

  const base = { proprietes: { VERTEX_PROJET: 'etii-docs', DRIVE_PARTAGE: DRIVE_A }, dossiers: DOSSIERS, contenus: { gd1: TEXTE_GUIDE } };
  const sansDoc = assistant(Object.assign({}, base, { lister: () => [] }));
  const r0 = sansDoc.gs.etiiRepondre('faisceaux puissance');
  t('aucun document trouvé : aucun appel au modèle, donc aucun coût',
    r0.documents.length === 0 && r0.reponse === '' && !sansDoc.etat.appels.some((a) => /aiplatform/.test(a.url)));
  const office = assistant(Object.assign({}, base, { lister: () => [NOTE] }));
  const r1 = office.gs.etiiRepondre('blindage');
  t('rien de lisible (Word seul) : pas d’appel, la réponse le dit et liste le document',
    r1.illisibles === true && r1.documents.length === 1 && !office.etat.appels.some((a) => /aiplatform/.test(a.url)));
  const avec = (vertex, q = 'faisceaux') => assistant(Object.assign({}, base, { lister: () => [GUIDE], vertex }));
  const modele3 = avec({ code: 200, corps: REPONSE_VERTEX });
  modele3.gs.etiiRepondre('faisceaux');
  const ancien = assistant(Object.assign({}, base, { proprietes: Object.assign({ VERTEX_MODELE: 'gemini-2.5-flash', VERTEX_REGION: 'europe-west1' }, base.proprietes),
    lister: () => [GUIDE], vertex: { code: 200, corps: REPONSE_VERTEX } }));
  ancien.gs.etiiRepondre('faisceaux');
  t('un modèle d’avant Gemini 3 ne reçoit pas de thinkingLevel',
    JSON.parse(ancien.etat.appels.find((a) => /aiplatform/.test(a.url)).options.payload).generationConfig.thinkingConfig === undefined);
  const tronque = avec({ code: 200, corps: json({ candidates: [{ content: { parts: [{ text: 'Début [1]' }] }, finishReason: 'MAX_TOKENS' }] }) });
  t('une réponse coupée est signalée', tronque.gs.etiiRepondre('faisceaux').tronquee === true);
  const sansCite = avec({ code: 200, corps: json({ candidates: [{ content: { parts: [{ text: 'Réponse sans renvoi.' }] }, finishReason: 'STOP' }] }) });
  t('sans renvoi, aucun document n’est marqué cité', sansCite.gs.etiiRepondre('faisceaux').documents.every((d) => !d.cite));
  t('403 de portée : il faut ajouter la portée au manifeste',
    /portée « aiplatform »/.test(erreur(() => avec({ code: 403, corps: json({ error: { code: 403, message: 'Request had insufficient authentication scopes.', status: 'PERMISSION_DENIED', details: [{ reason: 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' }] } }) }).gs.etiiRepondre('faisceaux'))));
  t('403 de droits : le rôle à demander est nommé, avec le message de Google',
    /Agent Platform User.*Permission denied/.test(erreur(() => avec({ code: 403, corps: json({ error: { code: 403, message: 'Permission denied on resource' } }) }).gs.etiiRepondre('faisceaux'))));
  t('404 : modèle retiré ou projet faux', /VERTEX_MODELE \(gemini-3\.5-flash, peut-être retiré\)/.test(erreur(() => avec({ code: 404, corps: '{}' }).gs.etiiRepondre('faisceaux'))));
  t('429 : le quota, réessayer', /réessayez dans une minute/.test(erreur(() => avec({ code: 429, corps: '{}' }).gs.etiiRepondre('faisceaux'))));
  t('une question bloquée par les filtres est dite',
    /bloquée par les filtres de Google \(SAFETY\)/.test(erreur(() => avec({ code: 200, corps: json({ promptFeedback: { blockReason: 'SAFETY' } }) }).gs.etiiRepondre('faisceaux'))));
  t('une réponse interrompue sans texte est une erreur, pas une réponse vide',
    /interrompu sa réponse \(SAFETY\)/.test(erreur(() => avec({ code: 200, corps: json({ candidates: [{ content: { parts: [] }, finishReason: 'FINISH_REASON_SAFETY' }] }) }).gs.etiiRepondre('faisceaux'))));
  t('une réponse illisible est signalée', /illisible/.test(erreur(() => avec({ code: 200, corps: '<html>' }).gs.etiiRepondre('faisceaux'))));
}

console.log('\n== Niveau 3 : Gemini Enterprise ==');
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
const enterprise = (o = {}) => assistant({ proprietes: { GEMINI_APP: 'app' in o ? o.app : APP, VERTEX_PROJET: 'etii-docs', DRIVE_PARTAGE: DRIVE_A },
  enterprise: { code: o.code || 200, corps: o.corps || FLUX } });
{
  const { gs, etat } = enterprise();
  const r = gs.etiiRepondre('  Quelle distance entre puissance et signal ?  ');
  const appel = etat.appels[0];
  t('l’appel part vers streamAssist v1, à l’adresse régionale de l’application',
    appel.url === 'https://eu-discoveryengine.googleapis.com/v1/' + APP + '/assistants/default_assistant:streamAssist', appel.url);
  t('au nom de la personne connectée (son jeton, aucune clé)',
    appel.options.headers.Authorization === 'Bearer jeton-de-la-personne' && !/key/i.test(appel.url));
  t('Gemini Enterprise lit lui-même le Drive : ni recherche Drive ni appel au modèle Agent Platform',
    etat.listes.length === 0 && etat.appels.length === 1);
  const corps = JSON.parse(appel.options.payload);
  t('le corps porte la question nettoyée, sans session au premier tour',
    corps.query.text === 'Quelle distance entre puissance et signal ?' && corps.session === undefined);
  t('la réponse assemble les morceaux dans l’ordre, sans la « pensée » du modèle',
    r.mode === 'enterprise' && r.reponse === 'La distance minimale est de **200 mm** entre les deux faisceaux.', r.reponse);
  t('les sources : titre, lien, page, extrait resserré — sans doublon',
    r.sources.length === 2 && r.sources[0].titre === 'Guide de routage harnais'
    && r.sources[0].lien === 'https://exemple.test/doc/1' && r.sources[0].page === '12'
    && r.sources[0].extrait === 'Séparer les faisceaux de puissance et de signal d’au moins 200 mm.', json(r.sources));
  t('un lien qui n’est pas https n’est jamais rendu cliquable', r.sources[1].lien === '');
  t('la conversation est renvoyée pour les questions de suite', r.session === APP + '/sessions/42');

  gs.etiiRepondre('Et pour le blindage ?', r.session);
  t('une question de suite reprend la conversation', JSON.parse(etat.appels[1].options.payload).session === APP + '/sessions/42');
  gs.etiiRepondre('Autre ?', 'projects/autre/locations/eu/collections/c/engines/x/sessions/1');
  t('une conversation d’une autre application est ignorée', JSON.parse(etat.appels[2].options.payload).session === undefined);
}
{
  const { gs } = enterprise();
  t('une question vide est refusée', /vide/.test(erreur(() => gs.etiiRepondre('   '))));
  t('une question de plus de 2 000 caractères est refusée', /2000/.test(erreur(() => gs.etiiRepondre('x'.repeat(2001)))));
  t('une propriété GEMINI_APP mal formée est signalée',
    /doit avoir la forme/.test(erreur(() => enterprise({ app: 'mon-app' }).gs.etiiRepondre('Q ?'))));
  const g = enterprise({ app: 'projects/1/locations/global/collections/default_collection/engines/a' });
  g.gs.etiiRepondre('Q ?');
  t('une application « global » est appelée sans préfixe régional',
    g.etat.appels[0].url.indexOf('https://discoveryengine.googleapis.com/v1/projects/1/locations/global/') === 0);
  t('403 : licence ou rôle manquant, avec le message de Google',
    /licence Gemini Enterprise.*Permission denied/.test(erreur(() => enterprise({ code: 403,
      corps: JSON.stringify([{ error: { code: 403, message: 'Permission denied' } }]) }).gs.etiiRepondre('Q ?'))));
  t('403 de portée : la portée discoveryengine à ajouter est nommée',
    /discoveryengine\.assist\.readwrite/.test(erreur(() => enterprise({ code: 403,
      corps: JSON.stringify({ error: { code: 403, message: 'Request had insufficient authentication scopes.' } }) }).gs.etiiRepondre('Q ?'))));
  t('404 : application introuvable', /introuvable/.test(erreur(() => enterprise({ code: 404, corps: '{}' }).gs.etiiRepondre('Q ?'))));
  t('une réponse illisible est signalée', /illisible/.test(erreur(() => enterprise({ corps: '<html>' }).gs.etiiRepondre('Q ?'))));
  t('SKIPPED : la raison est traduite',
    /reformulez/.test(erreur(() => enterprise({ corps: JSON.stringify([{ answer: { state: 'SKIPPED',
      assistSkippedReasons: ['NON_ASSIST_SEEKING_QUERY_IGNORED'] } }]) }).gs.etiiRepondre('Bonjour'))));
  t('FAILED : un échec est dit, pas une réponse vide',
    /pas pu terminer/.test(erreur(() => enterprise({ corps: JSON.stringify([{ answer: { state: 'FAILED' } }]) }).gs.etiiRepondre('Q ?'))));
  const seul = enterprise({ corps: JSON.stringify({ answer: { state: 'SUCCEEDED', replies: [
    { groundedContent: { content: { text: 'Réponse sans source.' } } }] } }) }).gs.etiiRepondre('Q ?');
  t('un objet unique (hors tableau) se lit aussi ; sans source, la liste est vide',
    seul.reponse === 'Réponse sans source.' && seul.sources.length === 0);
}

console.log('\n== Assistant : la page ne fabrique jamais de HTML à partir du texte ==');
{
  const page = lire('../tools/apps-script/assistant/Page.html');
  t('aucun innerHTML ni insertAdjacentHTML', !/innerHTML|insertAdjacentHTML|document\.write/.test(page));
  t('la question du portail et les textes du niveau passent par des scriptlets échappés (<?= ?>), jamais bruts (<?!= ?>)',
    ['question', 'mode', 'titre', 'chapo', 'bouton', 'exemple'].every((v) => page.indexOf('<?= ' + v + ' ?>') !== -1) && !/<\?!=/.test(page));
  t('les liens vers Drive s’ouvrent dans un nouvel onglet, sans opener, et seulement en https',
    /noopener noreferrer/.test(page) && /\^https:\\\/\\\/\/i\.test/.test(page));
  t('les renvois [n] restent dans la page (target _self, malgré <base target="_top">)', /a\.target = '_self'/.test(page));
  t('l’animation d’attente ne tourne que sans « réduire les animations »',
    /@media \(prefers-reduced-motion: no-preference\)\s*\{[\s\S]*animation:/.test(page) && !/animation:[^;]*;[\s\S]*@media \(prefers-reduced-motion: no-preference\)/.test(page.split('@media (prefers-reduced-motion: no-preference)')[0]));
  t('les couleurs ne sont écrites qu’une fois, en variables, avec leur thème sombre',
    /@media \(prefers-color-scheme: dark\)/.test(page)
    && !page.replace(/:root\s*\{[^}]*\}/g, '').replace(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{[^}]*\}\s*\}/, '').match(/#[0-9a-f]{3,8}\b|rgb\(/i));
  t('au niveau 1, la page renvoie vers « Demander à Gemini » dans Drive', /Demander à Gemini/.test(page));
  t('au niveau 1, la page mène à la barre de recherche de Drive (aperçu IA) avec la même question, encodée, en https',
    /barre de recherche de Google Drive/.test(page)
    && /lienExterne\('https:\/\/drive\.google\.com\/drive\/search\?q=' \+ encodeURIComponent\(q\)/.test(page));
  t('une question venue du portail ne part seule qu’au niveau 1 : aux niveaux 2 et 3, elle attend un clic',
    /else if \(MODE === 'texte'\) poser\(\);/.test(page) && !/if \(champ\.value\.trim\(\)\) poser\(\)/.test(page)
    && /bouton\.focus\(\)/.test(page));
  t('un Drive partagé sauté est dit (« Drive partagé ignoré »), aux niveaux 1 et 2',
    /Drive partagé ignoré/.test(page) && (page.match(/ignores\(echange, r\.ignores\)/g) || []).length >= 4);
  t('un PDF lu par Gemini ne se dit pas « aperçu indisponible »',
    /else if \(d\.numero\) \{[\s\S]{0,160}Lu en entier par Gemini[\s\S]{0,80}\} else if \(!d\.lisible && INDISPONIBLE/.test(page));

  const manifeste = JSON.parse(lire('../tools/apps-script/assistant/appsscript.json'));
  t('le manifeste : exécution en tant que l’utilisateur qui accède, réservée au domaine',
    manifeste.webapp.executeAs === 'USER_ACCESSING' && manifeste.webapp.access === 'DOMAIN');
  t('le manifeste active le service avancé Drive v3',
    json(manifeste.dependencies.enabledAdvancedServices) === json([{ userSymbol: 'Drive', serviceId: 'drive', version: 'v3' }]));
  t('le manifeste demande les portées nécessaires aux trois niveaux, les plus étroites, et elles seules',
    json(manifeste.oauthScopes.slice().sort()) === json([
      'https://www.googleapis.com/auth/aiplatform',
      'https://www.googleapis.com/auth/discoveryengine.assist.readwrite',
      'https://www.googleapis.com/auth/drive.readonly',
      'https://www.googleapis.com/auth/script.external_request']));
}

/* ======================================================================
   3. Le raccordement au portail (assets/js/assistant.js)
   ====================================================================== */

console.log('\n== Portail : le bloc et le lien vers l’assistant ==');
{
  const portail = await import('../assets/js/assistant.js');
  const { SOURCE } = portail;
  t('dans ce dépôt public, l’assistant n’est pas raccordé', SOURCE.url === '' && portail.raccorde() === false && portail.adresseQuestion('x') === '');
  t('niveau 1 par défaut : « Chercher dans le texte des documents ↗ », et « Chercher ↗ » sous le titre du bloc',
    SOURCE.niveau === 1 && portail.libelles().action === 'Chercher dans le texte des documents ↗'
    && portail.libelles().titre === 'Chercher dans le texte des documents' && portail.libelles().bouton === 'Chercher ↗');
  SOURCE.url = 'https://exemple.test/exec';
  t('raccordé : la question part en paramètre q, encodée et bornée à 2 000 caractères',
    portail.raccorde() && portail.adresseQuestion(' distance & signal ') === 'https://exemple.test/exec?q=distance%20%26%20signal'
    && portail.adresseQuestion('x'.repeat(3000)).length === 'https://exemple.test/exec?q='.length + 2000
    && portail.adresseQuestion('') === 'https://exemple.test/exec');
  SOURCE.url = 'https://exemple.test/exec?mode=1';
  t('une adresse qui a déjà des paramètres reçoit &q=', portail.adresseQuestion('a') === 'https://exemple.test/exec?mode=1&q=a');
  SOURCE.niveau = 2;
  t('niveau 2 : « Demander à Gemini ↗ »', portail.libelles().action === 'Demander à Gemini ↗'
    && portail.libelles().bouton === 'Demander ↗' && /Gemini/.test(portail.libelles().badge));
  SOURCE.niveau = 3;
  t('niveau 3 : Gemini Enterprise est nommé', /Gemini Enterprise/.test(portail.libelles().badge));
  SOURCE.action = '  Chercher dans Drive ↗ ';
  t('SOURCE.action remplace le libellé du lien et du bouton',
    portail.libelles().action === 'Chercher dans Drive ↗' && portail.libelles().bouton === 'Chercher dans Drive ↗');
  SOURCE.niveau = 9; SOURCE.action = '';
  t('un niveau inconnu vaut le niveau 1', portail.libelles().action === 'Chercher dans le texte des documents ↗');
  Object.assign(SOURCE, { url: '', niveau: 1, action: '' });
  const source = lire('../assets/js/assistant.js');
  t('le module n’appelle rien lui-même et ne contient aucune adresse Google',
    !/fetch\(|XMLHttpRequest|google\.com|googleapis/.test(source));
  const encadre = source.slice(source.indexOf('function encadreNonRaccorde'), source.indexOf('export function blocAssistant'));
  t('non raccordé, le bloc dit quoi faire dès aujourd’hui : la question dans la barre de recherche de Drive, puis « Demander à Gemini »',
    /Dès aujourd’hui/.test(encadre) && /barre de recherche de Google Drive/.test(encadre) && /Demander à Gemini/.test(encadre)
    && /niveaux 0 et 1/.test(encadre));
}

/* ======================================================================
   4. Le remplissage du classeur des documents
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
