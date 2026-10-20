/* Batterie de l'OUVERTURE, côté serveur (débrief 23 : « le site est très
   très long à charger … beaucoup beaucoup plus rapide »).

   Le vrai Code.gs, dans Node, contre un classeur en mémoire de la taille du
   bureau (HDK 640 plans × 138 colonnes, THS 180, six relevés chacun, une
   base SEE de 3 000 lignes) — et, comme Apps Script :
   - chaque exécution est un contexte neuf (Code.gs réévalué), le classeur,
     ses propriétés, le cache et les déclencheurs étant partagés ;
   - le cache a ses VRAIES limites (CacheReel : clés de 250 caractères,
     valeurs de 102 400 octets, mille éléments, six heures) ;
   - l'horloge est simulée : une nuit, une semaine passent en secondes ;
   - chaque appel à un service Apps Script est compté.

   Ce qui est vérifié : le cache qui sert vraiment (le lendemain, « » puis
   HDK, la fenêtre et le lien …/exec), le préchauffage (déclencheur, verrou,
   import en cours), les gestes qui renouvellent les données, l'enveloppe
   compressée et son aller-retour (accents, U+2028, « </script> », morceaux
   de 100 000 caractères pile), les temps (journal d'exécution, mesures de
   la page, Diagnostic), et les cibles du plan : une semaine simulée, le
   nombre d'appels d'une ouverture servie du cache ou relue.

       node tests/ouverture-serveur.js
*/
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Feuille, Classeur, CacheReel } = require('./faux-classeur');
const { chargerServeur, decoderEnveloppe, donneesPourIndex } = require('./build-addon');
const gates = require('./feuille-gates');

const racine = path.join(__dirname, '..');
let reussis = 0;
const echecs = [];
let sectionCourante = '';
function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail !== undefined ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail !== undefined ? ' — ' + detail : ''));
  }
}
function section(t) { sectionCourante = t; console.log('\n— ' + t + ' —'); }
function noter(t) { console.log('    ' + t); }
const LS = String.fromCharCode(0x2028), PS = String.fromCharCode(0x2029);

/* =====================================================================
   LE COMPTE DES APPELS AUX SERVICES
   Seul l'appel le plus extérieur compte (une méthode du faux classeur qui
   en appelle une autre n'est pas un second appel) — sauf l'évaluation du
   modèle Index, qui exécute du Code.gs : ce qu'il appelle compte.
   ===================================================================== */
const J = { actif: false, appels: [], profondeur: 0 };
const METHODES_RENDUES = ['getProperty', 'setProperty', 'deleteProperty', 'get', 'getAll', 'put', 'putAll', 'remove', 'removeAll',
  'evaluate', 'getContent', 'tryLock', 'releaseLock', 'getBytes', 'setDataFromString', 'getDataAsString',
  'getDisplayValues', 'getValues', 'getMergedRanges', 'setValues', 'setNumberFormat', 'merge', 'setFontWeight',
  'timeBased', 'everyMinutes', 'create', 'getHandlerFunction', 'getUniqueId'];
function envelopper(obj, nom, service) {
  const orig = obj[nom];
  if (typeof orig !== 'function' || orig.__compte) return;
  const sansGarde = nom === 'evaluate';
  const f = function () {
    const exterieur = J.profondeur === 0;
    if (!sansGarde) J.profondeur++;
    let r;
    try { r = orig.apply(this, arguments); } finally { if (!sansGarde) J.profondeur--; }
    if ((exterieur || sansGarde) && J.actif) J.appels.push(service);
    if (r && typeof r === 'object' && !Array.isArray(r) && !(r instanceof Feuille) && !(r instanceof Classeur)) {
      METHODES_RENDUES.forEach(function (m) { if (typeof r[m] === 'function') envelopper(r, m, service.split('.')[0] + '>' + m); });
    }
    return r;
  };
  f.__compte = true;
  obj[nom] = f;
}
['getName', 'isSheetHidden', 'getLastRow', 'getLastColumn', 'getMaxColumns', 'getMaxRows', 'getIndex', 'getRange', 'getDataRange',
 'appendRow', 'insertColumnsAfter', 'insertRowsAfter', 'deleteRow', 'deleteRows', 'deleteColumns', 'clearContents', 'setName', 'hideSheet']
  .forEach(function (m) { envelopper(Feuille.prototype, m, 'Sheet.' + m); });
['getName', 'getSheets', 'getSheetByName', 'getActiveSheet', 'setActiveSheet', 'insertSheet', 'deleteSheet', 'moveActiveSheet']
  .forEach(function (m) { envelopper(Classeur.prototype, m, 'Spreadsheet.' + m); });
const SERVICES = {
  SpreadsheetApp: ['getActiveSpreadsheet', 'getUi'],
  PropertiesService: ['getDocumentProperties'],
  CacheService: ['getScriptCache', 'getDocumentCache'],
  HtmlService: ['createTemplateFromFile', 'createHtmlOutputFromFile', 'createHtmlOutput'],
  Utilities: ['formatDate', 'getUuid', 'newBlob', 'gzip', 'ungzip', 'base64EncodeWebSafe', 'base64DecodeWebSafe'],
  Session: ['getScriptTimeZone', 'getTemporaryActiveUserKey'],
  LockService: ['getScriptLock'],
  ScriptApp: ['getProjectTriggers', 'newTrigger', 'deleteTrigger']
};
function instrumenter(ctx) {
  Object.keys(SERVICES).forEach(function (s) { SERVICES[s].forEach(function (m) { if (ctx[s]) envelopper(ctx[s], m, s + '.' + m); }); });
}
function compter(appels) {
  const n = {};
  appels.forEach(function (a) { n[a] = (n[a] || 0) + 1; });
  return n;
}
function resumeAppels(appels) {
  const n = compter(appels);
  return Object.keys(n).sort(function (a, b) { return n[b] - n[a]; }).map(function (k) { return k + ' ×' + n[k]; }).join(', ');
}

/* =====================================================================
   L'HORLOGE ET LES EXÉCUTIONS
   ===================================================================== */
let maintenant = Date.UTC(2026, 9, 19, 6, 30);      // lundi 19 octobre 2026, 08:30 à Paris
class DateSimulee extends Date {
  constructor() {
    if (arguments.length === 0) super(maintenant);
    else super(...arguments);
  }
  static now() { return maintenant; }
}
const MINUTE = 60000, HEURE = 3600000, JOUR = 86400000;

/** Un monde : le classeur, ses propriétés, le cache du script, les déclencheurs — partagés d'une exécution à l'autre. */
function monde(classeur, proprietes, options) {
  const o = options || {};
  const m = {
    classeur: classeur, proprietes: proprietes || {}, declencheurs: [],
    cache: o.sansCache ? null : new CacheReel(function () { return maintenant; }),
    journal: [], derniers: null
  };
  /** Une exécution Apps Script : un contexte neuf, compté. `fn(ctx)` rend ce que rend l'exécution. */
  m.executer = function (fn, opts) {
    const x = opts || {};
    /* `code` : le Code.gs de cette exécution — m.code (un correctif recollé),
       ou celui d'un lien …/exec resté sur l'ancienne version. */
    const ctx = chargerServeur(m.classeur, m.proprietes, undefined, x.code !== undefined ? x.code : m.code);
    ctx.Date = DateSimulee;
    ctx.console = { log: function (t) { m.journal.push(String(t)); }, error: function () {}, warn: function () {} };
    ctx.__declencheurs = m.declencheurs;
    if (m.cache) ctx.__activerCache({ cache: m.cache, document: x.document });
    /* Ce qui vaut pour toutes les exécutions : la configuration, la même partout, comme le Code collé. */
    if (m.configuration) vm.runInContext(m.configuration, ctx);
    if (x.preparer) x.preparer(ctx);
    instrumenter(ctx);
    J.appels = []; J.actif = true;
    let r, err = null;
    try { r = fn(ctx); } catch (e) { err = e; } finally { J.actif = false; }
    m.derniers = { appels: J.appels.slice(), ctx: ctx, err: err };
    m.declencheurs = ctx.__declencheurs;
    if (err && !x.leve) throw err;
    return r;
  };
  m.appels = function () { return m.derniers.appels; };
  m.lectureComplete = function () { return m.derniers.appels.indexOf('Sheet.getDataRange') !== -1; };
  /** Les passages du déclencheur, toutes les dix minutes, de maintenant jusqu'à `fin` (l'horloge avance). */
  m.declencheur = function (fin) {
    let n = 0;
    while (maintenant + 10 * MINUTE <= fin) {
      maintenant += 10 * MINUTE;
      const uid = (m.declencheurs.filter(function (d) { return d.getHandlerFunction() === 'prechaufferTableau'; })[0] || { getUniqueId: function () { return 'declencheur-test'; } }).getUniqueId();
      m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: uid }); });
      n++;
    }
    maintenant = fin;
    return n;
  };
  return m;
}

/* =====================================================================
   LE CLASSEUR DU BUREAU
   ===================================================================== */
const I_REF = gates.colonne('Référence UD');
const I_DEF = gates.colonne('Avancement Définition Electrique', 'HDK AA 011');
function alea(graine) { let g = graine >>> 0; return function () { g = (Math.imul(g, 1103515245) + 12345) >>> 0; return g / 4294967296; }; }
function ongletGates(nom, n, prefixe, graine) {
  const g = gates.feuilleGates(n);
  const r = alea(graine);
  for (let i = 3; i < g.valeurs.length; i++) {
    const l = g.valeurs[i];
    if (prefixe) l[I_REF] = String(l[I_REF]).replace(/^UD-/, prefixe + '-');
    const x = r();
    l[I_DEF] = x < 0.45 ? 'VALIDATED' : x < 0.6 ? 'PWD_IN_PROGRESS' : x < 0.7 ? 'PWD_TO_CONTROL' : x < 0.95 ? 'TO_TREAT' : 'FWD_TO_SEIZE';
  }
  return new Feuille(nom, g.valeurs, false, g.fusions);
}
function ongletSee(nom, n) {
  const lignes = [['Trié à l’import : PSN 4530 · DIAGRAM TYPE = WD — ' + n + ' lignes gardées sur 61 234 · « Nommage WD BFLOW.xlsx », le 05/10/2026', '', ''],
                  ['NAME', 'SOL.', 'Cust.V']];
  for (let i = 0; i < n; i++) lignes.push(['TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0'), String((i % 3) + 1).padStart(3, '0'), ['A', 'B', 'C', 'D'][i % 4]]);
  return new Feuille(nom, lignes, false, []);
}
/** HDK, THS, SEE HDK ; un relevé archivé par le vrai Code.gs, recopié sur les cinq semaines d'avant. */
function classeurDuBureau(options) {
  const o = options || {};
  const feuilles = [ongletGates('HDK', o.hdk || 640, null, 7), ongletGates('THS', o.ths || 180, 'THS', 11)];
  if (o.see !== false) feuilles.push(ongletSee('SEE HDK', o.see || 3000));
  const classeur = new Classeur(feuilles, 'Suivi FWD H225');
  const proprietes = {};
  const ctx = chargerServeur(classeur, proprietes);
  ctx.Date = DateSimulee;
  ctx.enregistrerInstantaneHebdo();
  ['HDK', 'THS'].forEach(function (id) {
    const h = classeur.getSheetByName('Historique_FWD_' + id);
    const base = h.valeurs[1];
    const semaine = base[0];
    const lignes = [];
    for (let k = 5; k >= 1; k--) {
      const l = base.slice();
      l[0] = ctx.numeroSemaineISO(new Date(maintenant - k * 7 * JOUR));
      l[3] = Math.round(base[3] * (1 - k * 0.08));
      lignes.push(l);
    }
    h.valeurs.splice(1, 0, ...lignes);
    if (h.valeurs[h.valeurs.length - 1][0] !== semaine) throw new Error('relevés mal rangés');
  });
  return { classeur: classeur, proprietes: proprietes };
}
const lireEnveloppe = decoderEnveloppe;
/** Ce que doGet pose vraiment dans la page : le texte après « window.SUIVI_FWD_DONNEES = ». */
function donneesDeLaPage(ctx) {
  const html = ctx.doGet({ parameter: {} }).getContent();
  const m = /window\.SUIVI_FWD_DONNEES = (.*);\n/.exec(html);
  if (!m) throw new Error('SUIVI_FWD_DONNEES introuvable dans la page servie');
  return m[1];
}
function cellule(classeur, onglet, ligne, col) { return classeur.getSheetByName(onglet).valeurs[ligne][col]; }

(async () => {
  // =================================================================
  section('La compression : un aller-retour exact');
  {
    const { classeur, proprietes } = classeurDuBureau({ hdk: 40, ths: 20, see: 10 });
    const m = monde(classeur, proprietes);
    const texte = '{"a":"éàç — € ' + LS + ' ' + PS + ' </script> « Référence UD » \ud834\udd1e"}';
    const relu = m.executer(function (ctx) { return ctx.decompresserJson_(ctx.compresserJson_(texte)); });
    verifier('accents, « — », « € », U+2028, U+2029, « </script> », un caractère hors du plan de base : tout revient à l’identique', relu === texte);
    const b64 = m.executer(function (ctx) { return ctx.compresserJson_(texte); });
    verifier('le base64 n’a que l’alphabet « web », sans « = » final : rien à échapper dans un <script>', /^[A-Za-z0-9_-]+$/.test(b64), b64.slice(-12));
    verifier('l’essai de compression du serveur réussit', m.executer(function (ctx) { return ctx.essaiCompression_(); }) === true);
    /* Les morceaux : 100 000 caractères pile, et un caractère jamais coupé en deux. */
    const t = m.executer(function (ctx) {
      const a = 'x'.repeat(100000), b = 'y'.repeat(100001), c = 'z'.repeat(200000);
      const d = 'w'.repeat(29999) + '\ud834\udd1e' + 'v'.repeat(10);
      return { a: ctx.trancher_(a, 100000).map(x => x.length), b: ctx.trancher_(b, 100000).map(x => x.length),
               c: ctx.trancher_(c, 100000).map(x => x.length), d: ctx.trancher_(d, 30000), d0: d };
    });
    verifier('100 000 caractères : un morceau ; 100 001 : deux ; 200 000 : deux morceaux pleins',
      JSON.stringify(t.a) === '[100000]' && JSON.stringify(t.b) === '[100000,1]' && JSON.stringify(t.c) === '[100000,100000]', JSON.stringify([t.a, t.b, t.c]));
    verifier('une paire de substitution à la frontière reste entière, et le tout se recolle', t.d[0].length === 29999 && t.d.join('') === t.d0, t.d.map(x => x.length).join());
  }

  // =================================================================
  section('L’enveloppe : ce que reçoit la page');
  {
    const { classeur, proprietes } = classeurDuBureau({ hdk: 120, ths: 30, see: 50 });
    /* Une cellule qui contient de quoi couper une page en deux. */
    const iLib = gates.colonne('Libellé');
    classeur.getSheetByName('HDK').valeurs[5][iLib] = 'Câble « pilote » </script><script>alert(1)</script> ' + LS + ' fin' + PS;
    const m = monde(classeur, proprietes);
    const lit = m.executer(function (ctx) { return donneesDeLaPage(ctx); });
    verifier('le modèle Index reçoit l’enveloppe : { format: 2, edition, contrat, cle, mesures, gz }, en une expression JavaScript',
      /^\{"format":2,"edition":"[0-9a-f]+","contrat":"HDK","cle":"SFWD2:[0-9a-z]+:[0-9a-z]+","mesures":\{"serveur":\{/.test(lit) && /,"gz":"[A-Za-z0-9_-]+"\}$/.test(lit),
      lit.slice(0, 160));
    verifier('ni « </script> », ni « < », ni U+2028 en clair dans ce qui est posé dans la page',
      lit.indexOf('<') === -1 && lit.indexOf(LS) === -1 && lit.indexOf(PS) === -1);
    const env = JSON.parse(lit);
    const paquet = lireEnveloppe(env);
    const clair = JSON.parse(m.executer(function (ctx) { return ctx.getDonneesCompactesJson('HDK'); }));
    const sansHeure = o => { const c = JSON.parse(JSON.stringify(o)); delete c.genereLe; return JSON.stringify(c); };
    verifier('décompressée, l’enveloppe porte le paquet compact entier, la cellule piégée comprise, à l’identique du repli en clair',
      paquet.ok === true && sansHeure(paquet) === sansHeure(clair) && JSON.stringify(paquet).indexOf('</script><script>alert(1)</script> ' + LS) !== -1);
    const s = env.mesures.serveur;
    verifier('les temps du serveur voyagent avec : début, fin, résultat du cache, étapes, octets',
      typeof s.debut === 'number' && s.fin >= s.debut && ['trouvé', 'alias', 'manqué', 'sans cache'].indexOf(s.cache) !== -1 &&
      s.etapes && typeof s.etapes.version === 'number' && s.octets === env.gz.length, JSON.stringify(s));
    const autre = m.executer(function (ctx) { return ctx.getDonneesCompactes('THS'); });
    verifier('getDonneesCompactes rend la même enveloppe, pour le contrat demandé', autre.format === 2 && autre.contrat === 'THS' && lireEnveloppe(autre).contrat === 'THS');
    const erreur = m.executer(function (ctx) { return ctx.getDonneesCompactes('Nulle part'); });
    verifier('un contrat introuvable : le paquet d’erreur, en clair, sans enveloppe', erreur.ok === false && !erreur.format && /introuvable/.test(erreur.message));
    const horsIndex = m.executer(function (ctx) { return ctx.donneesJSONPourPage(); });
    verifier('hors du modèle Index (le chargeur), donneesJSONPourPage reste le paquet en clair, échappé, que toute page sait lire',
      /^\{"ok":true,/.test(horsIndex) && horsIndex.indexOf('<') === -1 && horsIndex.indexOf('\\u003c/script\\u003e') !== -1 && sansHeure(JSON.parse(horsIndex)) === sansHeure(clair));
    /* Sans compression (un Apps Script qui ne l'aurait pas, ou l'essai raté) : tout en clair, comme avant. */
    const sans = m.executer(function (ctx) { ctx.onEdit({}); return donneesPourIndex(ctx); }, { preparer: function (ctx) { delete ctx.Utilities.gzip; } });
    verifier('sans Utilities.gzip : la page reçoit le paquet en clair', /^\{"ok":true,/.test(sans));
    m.cache.m.forEach(function (v, k) { if (/^SFWD:gz:/.test(k)) m.cache.m.delete(k); });
    const rate = m.executer(function (ctx) { ctx.onEdit({}); return { lit: donneesPourIndex(ctx), env: ctx.getDonneesCompactes('THS') }; },
      { preparer: function (ctx) { ctx.Utilities.ungzip = function () { throw new Error('Unexpected error'); }; } });
    verifier('l’essai aller-retour raté : la page et le pont reçoivent le paquet en clair, et l’échec est retenu (dix minutes)',
      /^\{"ok":true,/.test(rate.lit) && rate.env.ok === true && !rate.env.format && [...m.cache.m.keys()].some(k => /^SFWD:gz:/.test(k) && m.cache.m.get(k).v === '0'));
    m.cache.m.forEach(function (v, k) { if (/^SFWD:gz:/.test(k)) m.cache.m.delete(k); });
  }

  // =================================================================
  section('Le paquet en cache : rangé compressé, sous un manifeste, aux vraies limites');
  {
    const { classeur, proprietes } = classeurDuBureau();
    const m = monde(classeur, proprietes);
    m.executer(function (ctx) { return ctx.doGet({ parameter: {} }); });
    const cles = [...m.cache.m.keys()];
    const manifestes = cles.filter(k => /^SFWD2:[0-9a-z]+:[0-9a-z]+:m$/.test(k)).map(k => JSON.parse(m.cache.m.get(k).v));
    const hdk = manifestes.filter(x => x.contrat === 'HDK')[0];
    verifier('640 plans, six relevés, 3 000 lignes SEE : un ou deux morceaux au lieu de vingt-quatre', !!hdk && hdk.format === 'gz' && hdk.n <= 2,
      JSON.stringify(hdk));
    verifier('chaque valeur sous 100 000 caractères, chaque clé sous 250', cles.every(k => k.length <= 250 && m.cache.m.get(k).v.length <= 102400));
    noter('HDK : ' + Math.round(hdk.brut / 1024) + ' Ko de JSON → ' + Math.round(hdk.octets / 1024) + ' Ko compressés, ' + hdk.n + ' morceau(x)');
    verifier('l’ouverture (contrat « ») a son alias, vers le contrat qu’elle montre', cles.some(k => /^SFWD2:[0-9a-z]+:\*$/.test(k) && m.cache.m.get(k).v === 'HDK'));
    /* Un morceau évincé : le paquet n'est plus servi, il est relu. */
    const morceau = cles.filter(k => /^SFWD2:[0-9a-z]+:[0-9a-z]+:0$/.test(k))[0];
    m.cache.m.delete(morceau);
    m.executer(function (ctx) { return ctx.doGet({ parameter: {} }); });
    verifier('un morceau évincé : le paquet n’est pas servi à moitié, l’ouverture relit le classeur', m.lectureComplete());
    /* Trop gros pour le cache (une valeur de plus de 102 400 octets) : rien
       n'est rangé à moitié, et la page se sert sans. */
    const refuse = m.executer(function (ctx) {
      vm.runInContext('CACHE_TAILLES.gz = 200000', ctx);
      return ctx.ecrireEntree_(ctx.cacheDuClasseur(), 'essai', 'HDK', { gz: 'A'.repeat(150000), json: '{}', contrat: 'HDK', plans: 1 });
    });
    verifier('une valeur de plus de 102 400 octets : le cache la refuse (tout ou rien), aucun manifeste n’est écrit',
      refuse === '' && ![...m.cache.m.keys()].some(k => /^SFWD2:essai:/.test(k)), refuse);
    const servi = m.executer(function (ctx) { ctx.onEdit({}); return ctx.getDonneesCompactes('HDK'); }, { preparer: function (ctx) {
      const c = m.cache;
      ctx.CacheService = { getDocumentCache: function () { return null; }, getScriptCache: function () {
        return { get: c.get.bind(c), getAll: c.getAll.bind(c), put: c.put.bind(c), putAll: function () { throw new Error('Argument too large: value'); } }; } };
    } });
    verifier('un paquet que le cache refuse est quand même servi, entier — sans clé, rien à prolonger', servi.format === 2 && servi.cle === '' && lireEnveloppe(servi).ok === true,
      JSON.stringify([servi.format, servi.cle]));
  }

  // =================================================================
  section('Le cache qui sert : le lendemain, « » puis HDK, la fenêtre et le lien …/exec');
  {
    maintenant = Date.UTC(2026, 9, 19, 6, 30);
    const { classeur, proprietes } = classeurDuBureau();
    const m = monde(classeur, proprietes);
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    verifier('lundi 08:30, la première ouverture relit le classeur (cache vide)', m.lectureComplete());
    m.executer(function (ctx) { return ctx.getDonneesCompactes('HDK'); });
    verifier('« » puis HDK : un seul paquet — le retour sur HDK est servi du cache', !m.lectureComplete(), resumeAppels(m.appels()));
    /* Sans déclencheur, une nuit : le cache a expiré (six heures). */
    maintenant += JOUR;
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    verifier('sans préchauffage, le lendemain 08:30 : le paquet a expiré, l’ouverture relit (la date, elle, n’est plus dans la clé)', m.lectureComplete());
    /* Avec le déclencheur : la nuit passe, le paquet reste prêt. */
    m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
    const fin = maintenant + JOUR;
    const passages = m.declencheur(fin);
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    const lus = m.appels().filter(a => /getDisplayValues|getValues/.test(a)).length;
    verifier('avec le préchauffage (' + passages + ' passages), le surlendemain 08:30, rien n’a changé : aucune lecture du classeur à l’ouverture',
      !m.lectureComplete() && lus === 0, resumeAppels(m.appels()));
    /* La fenêtre du menu et le lien …/exec : le même cache, même si celui du document n'existe pas pour le lien. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); }, { document: 'nul' });
    verifier('le lien …/exec (cache du document absent) relit après une saisie, et garde ce qu’il a lu', m.lectureComplete());
    m.executer(function (ctx) { ctx.ouvrirTableauDeBord(); }, { document: 'autre' });
    verifier('la fenêtre du menu (un autre cache du document) trouve ce que le lien a gardé : le cache du script, le même pour les deux',
      !m.lectureComplete() && !!m.derniers.ctx.__dialogue && m.derniers.ctx.__dialogue.source.modele === 'Index', resumeAppels(m.appels()));
    verifier('… et rien n’est rangé dans le cache du document', m.derniers.ctx.CacheService.getDocumentCache().m.size === 0);
  }

  // =================================================================
  section('Les données qui changent : jamais un paquet d’avant');
  {
    maintenant = Date.UTC(2026, 9, 20, 6, 30);
    const { classeur, proprietes } = classeurDuBureau();
    const m = monde(classeur, proprietes);
    m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
    const avancement = l => cellule(classeur, 'HDK', l, I_DEF);
    const ouvrir = function () { return lireEnveloppe(m.executer(function (ctx) { return JSON.parse(donneesPourIndex(ctx)); })); };
    const valeurDe = (p, ligne) => {
      const i = p.plansTab.cles.indexOf('avancement'), r = p.plansTab.cles.indexOf('reference');
      const ref = cellule(classeur, 'HDK', ligne, I_REF);
      const l = p.plansTab.lignes.filter(x => x[r] === ref)[0];
      return l ? l[i] : undefined;
    };
    ouvrir();
    /* Une saisie : onEdit. */
    classeur.getSheetByName('HDK').valeurs[10][I_DEF] = 'TO_CONFIRM';
    m.executer(function (ctx) { ctx.onEdit({}); });
    const p1 = ouvrir();
    verifier('une saisie (onEdit) : l’ouverture suivante montre la valeur du jour', valeurDe(p1, 10) === 'TO_CONFIRM' && m.lectureComplete());
    m.declencheur(maintenant + 10 * MINUTE);
    classeur.getSheetByName('HDK').valeurs[11][I_DEF] = 'TO_CONFIRM';   // sans onEdit, la même taille : invisible
    const p2 = ouvrir();
    verifier('… et le passage suivant ne relit rien de plus : le paquet du jour est déjà là', !m.lectureComplete());
    noter('(une valeur changée sans onEdit ni changement de taille — un script tiers — reste invisible jusqu’au lendemain au plus tard, comme avant : ' + valeurDe(p2, 11) + ')');
    /* L'archivage du menu : relevé écrit, marque, puis le préchauffage tout de suite. */
    const relevesAvant = ouvrir().relevesTab.releves.length;
    classeur.getSheetByName('Historique_FWD_HDK').valeurs.splice(-1, 1);   // la semaine en cours retirée…
    m.executer(function (ctx) { ctx.onEdit({}); });
    ouvrir();
    m.executer(function (ctx) { ctx.enregistrerInstantaneHebdo(); });
    verifier('l’archivage du menu prépare le tableau de bord juste après le OK', m.journal.some(l => /^Suivi FWD · préchauffage · .*préparé/.test(l)) && m.lectureComplete());
    const p3 = ouvrir();
    verifier('… et l’ouverture suivante, servie du cache, porte le relevé tout juste archivé', !m.lectureComplete() && p3.relevesTab.releves.length === relevesAvant);
    /* La suppression du relevé de la semaine. */
    m.executer(function (ctx) { ctx.supprimerDernierReleve(); });
    const p4 = ouvrir();
    verifier('la suppression du relevé : l’ouverture suivante ne le montre plus (préparé juste après le geste)', p4.relevesTab.releves.length === relevesAvant - 1 && !m.lectureComplete());
    /* Le dépôt automatique (doPost). */
    const valeursDepot = classeur.getSheetByName('THS').valeurs.map(l => l.map(v => String(v)));
    valeursDepot[5][I_DEF] = 'TO_CONFIRM';
    m.configuration = "CONFIG.DEPOT.SECRET = 'secret-de-test';";
    m.executer(function (ctx) { ctx.onEdit({}); });
    m.declencheur(maintenant + 10 * MINUTE);
    m.executer(function (ctx) {
      return ctx.doPost({ postData: { contents: JSON.stringify({ secret: 'secret-de-test', onglet: 'THS', lignes: valeursDepot }) } });
    });
    const p5 = lireEnveloppe(m.executer(function (ctx) { return ctx.getDonneesCompactes('THS'); }));
    const iA = p5.plansTab.cles.indexOf('avancement'), iR = p5.plansTab.cles.indexOf('reference');
    verifier('un dépôt : le tableau de bord se prépare à la fin, et THS montre l’extract déposé, sans relire',
      p5.plansTab.lignes.some(l => l[iR] === valeursDepot[5][I_REF] && l[iA] === 'TO_CONFIRM') && !m.lectureComplete());
    /* L'import de la fenêtre : le temporaire, les lots, la fin (échange et marque). */
    const nouvelles = classeur.getSheetByName('HDK').valeurs.map(l => l.map(v => String(v)));
    nouvelles[12][I_DEF] = 'PWD_TO_CONTROL';
    const fusions = gates.feuilleGates(1).fusions.map(f => ({ ligne: f.ligne, col: f.col, nbLignes: f.haut || 1, nbCols: f.larg }));
    m.executer(function (ctx) {
      const jeton = ctx.ouvrirJetonImport_();
      const d = ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'HDK' }, nouvelles[0].length, nouvelles.length);
      ctx.importSecondeBaseLot(jeton, d.feuille, 1, nouvelles);
      return ctx.importSecondeBaseFin(jeton, d.feuille, { sorte: 'gates', contrat: 'HDK' }, nouvelles.length, fusions);
    });
    const p6 = ouvrir();
    verifier('un import GATES : l’ouverture suivante montre l’export importé', valeurDe(p6, 12) === 'PWD_TO_CONTROL');
    /* Une lecture prise de vitesse par un geste qui écrit : la version est
       calculée AVANT de lire, le geste marque APRÈS avoir écrit — ce qui a
       été lu pendant l'écriture est rangé sous une clé que personne ne
       redemandera. */
    classeur.getSheetByName('HDK').valeurs[13][I_DEF] = 'TO_TREAT';
    m.executer(function (ctx) { ctx.onEdit({}); });
    m.executer(function (ctx) {
      ctx.__ecrire = function () { classeur.getSheetByName('HDK').valeurs[13][I_DEF] = 'VALIDATED'; };
      vm.runInContext('var __construire = construireEntree_; construireEntree_ = function () { const r = __construire.apply(this, arguments); __ecrire(); marquerDonneesModifiees_(); return r; };', ctx);
      return ctx.getDonneesCompactes('');
    });
    const p7 = ouvrir();
    verifier('un geste qui écrit pendant une lecture : l’ouverture suivante ne sert jamais le paquet lu à moitié', valeurDe(p7, 13) === 'VALIDATED' && m.lectureComplete());
    /* ?frais=1, et la lecture du Diagnostic. */
    classeur.getSheetByName('HDK').valeurs[14][I_DEF] = 'TO_CONFIRM';   // sans onEdit
    m.executer(function (ctx) { ctx.doGet({ parameter: { frais: '1' } }); });
    verifier('?frais=1 relit le classeur', m.lectureComplete());
    const p8 = ouvrir();
    verifier('… et les ouvertures suivantes en profitent', valeurDe(p8, 14) === 'TO_CONFIRM' && !m.lectureComplete());
    const avantDiag = m.cache.ecrits;
    const diag = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('le Diagnostic mesure une vraie lecture (sans le cache, rien n’y est rangé)',
      /préparé en \d+,\d s — lecture de GATES/.test(diag) && m.lectureComplete() && m.cache.ecrits === avantDiag, String(m.cache.ecrits - avantDiag));
  }

  // =================================================================
  section('Un correctif de Code recollé seul : jamais les paquets de l’ancien Code');
  {
    /* MODE-D-EMPLOI : « quand je ne corrige que Code, on ne recolle que
       Code » — EDITION (la page) ne change pas. Le correctif d'essai change
       un nombre du paquet, comme un correctif de lecture le ferait. */
    const ancien = fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8');
    const motif = 'lignesIgnorees: modele.lignesIgnorees,';
    const corrige = ancien.replace(motif, 'lignesIgnorees: 999,');
    verifier('(le correctif d’essai change bien un nombre du paquet)', ancien.indexOf(motif) !== -1 && corrige !== ancien);
    [false, true].forEach(function (avecPrechauffage) {
      maintenant = Date.UTC(2026, 9, 19, 6, 30);
      const { classeur, proprietes } = classeurDuBureau({ hdk: 80, ths: 20, see: 20 });
      const m = monde(classeur, proprietes);
      m.code = ancien;
      const dit = avecPrechauffage ? ' (ouverture rapide activée)' : ' (sans préchauffage)';
      if (avecPrechauffage) m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
      m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
      m.executer(function (ctx) { ctx.getDonneesCompactes('THS'); });
      /* 08:40 : Code.gs recollé, Ctrl+S. Rien d'autre ne change. */
      m.code = corrige;
      if (avecPrechauffage) m.declencheur(maintenant + 10 * MINUTE); else maintenant += 10 * MINUTE;
      const env = m.executer(function (ctx) { return JSON.parse(donneesDeLaPage(ctx)); });
      const p = lireEnveloppe(env);
      if (avecPrechauffage) {
        verifier('le passage qui suit le recollage prépare le paquet du nouveau Code : l’ouverture de 08:40 le sert du cache' + dit,
          p.lignesIgnorees === 999 && !m.lectureComplete(), JSON.stringify([p.lignesIgnorees, m.lectureComplete()]));
      } else {
        verifier('la première ouverture après le recollage relit le classeur avec le nouveau Code — et dit pourquoi : « livraison »' + dit,
          p.lignesIgnorees === 999 && m.lectureComplete() && env.mesures.serveur.raison === 'livraison',
          JSON.stringify([p.lignesIgnorees, m.lectureComplete(), env.mesures.serveur.raison]));
      }
      const ths = lireEnveloppe(m.executer(function (ctx) { return ctx.getDonneesCompactes('THS'); }));
      verifier('… THS aussi : le paquet de l’ancien Code n’est plus servi' + dit, ths.lignesIgnorees === 999, String(ths.lignesIgnorees));
      /* Le lien …/exec resté sur l'ancienne version du déploiement : il
         partage le cache du script, mais pas les clés. */
      m.executer(function (ctx) { ctx.onEdit({}); }, { code: ancien });
      m.executer(function (ctx) { ctx.doGet({ parameter: {} }); }, { code: ancien });
      m.executer(function (ctx) { ctx.doGet({ parameter: {} }); }, { code: ancien });
      const vieux = lireEnveloppe(m.executer(function (ctx) { return JSON.parse(donneesDeLaPage(ctx)); }, { code: ancien }));
      const fenetre = lireEnveloppe(m.executer(function (ctx) { return JSON.parse(donneesPourIndex(ctx)); }));
      verifier('un lien …/exec encore sur l’ancien Code range ses paquets à part : la fenêtre du menu (nouveau Code) ne les reçoit jamais' + dit,
        vieux.lignesIgnorees !== 999 && fenetre.lignesIgnorees === 999, JSON.stringify([vieux.lignesIgnorees, fenetre.lignesIgnorees]));
    });
  }

  // =================================================================
  section('Une ouverture qui relit le classeur dit pourquoi — jamais « il venait de changer » à tort');
  {
    maintenant = Date.UTC(2026, 9, 19, 6, 0);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 80, ths: 20, see: 20 });
    const m = monde(classeur, proprietes);
    const servi = function (parametres) {
      let env = null;
      m.executer(function (ctx) {
        const html = ctx.doGet({ parameter: parametres || {} }).getContent();
        env = JSON.parse(/window\.SUIVI_FWD_DONNEES = (.*);\n/.exec(html)[1]);
      });
      return env.mesures.serveur;
    };
    maintenant += 30 * MINUTE;                       // lundi 08:30 : l'archivage d'il y a une demi-heure, rien en cache
    const s1 = servi();
    verifier('lundi 08:30, première ouverture, rien de prêt : « manqué », sans raison inventée (ni « modifié » ni heure de changement)',
      s1.cache === 'manqué' && s1.raison === '' && !s1.modifie, JSON.stringify(s1));
    maintenant += MINUTE;
    const t1 = m.executer(function (ctx) { return ctx.getDonneesCompactes('THS'); }).mesures.serveur;
    verifier('THS, jamais préparé, le classeur n’ayant pas bougé : « expiré » (rien de prêt pour ce contrat)', t1.cache === 'manqué' && t1.raison === 'expiré', JSON.stringify(t1));
    maintenant += 24 * HEURE;                        // mardi 08:31 : rien n'a bougé, pas de préchauffage, le cache a expiré
    const s2 = servi();
    verifier('le lendemain, rien de touché, le cache expiré : pas « il venait de changer »', s2.cache === 'manqué' && s2.raison === '' && !s2.modifie, JSON.stringify(s2));
    m.executer(function (ctx) {
      ctx.noterConsultation({ quand: maintenant, contrat: 'HDK', cache: s2.cache, raison: s2.raison, debut: s2.debut, serveur: 9000, transfert: 300,
        synthese: 900, tout: 1800, plans: 80, releves: 6, octets: 1000, largeur: 1440 });
    });
    const diag = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('… et le Diagnostic ne lui donne pas « classeur modifié » pour cause',
      /au pire 9,0 s \([^)]*cache manqué : rien de prêt en cache\)/.test(diag) && !/classeur modifié/.test(diag), diag.slice(diag.indexOf('Les '), diag.indexOf('Les ') + 260));
    maintenant += 30 * MINUTE;
    classeur.getSheetByName('HDK').valeurs[10][I_DEF] = 'TO_CONFIRM';
    m.executer(function (ctx) { ctx.onEdit({}); });
    const marque = maintenant;
    maintenant += 4 * MINUTE;
    const s3 = servi();
    verifier('une saisie, puis une ouverture quatre minutes après : « modifié », à l’heure de la saisie', s3.cache === 'manqué' && s3.raison === 'modifié' && s3.modifie === marque,
      JSON.stringify(s3));
    maintenant += MINUTE;
    classeur.getSheetByName('SEE HDK').valeurs.push(['TFE399A9999', '001', 'A']);   // une ligne ajoutée, sans onEdit
    const s4 = servi();
    verifier('le classeur changé sans saisie (une ligne de plus) : « modifié », sans heure — on ne la connaît pas', s4.raison === 'modifié' && !s4.modifie, JSON.stringify(s4));
    maintenant += MINUTE;
    const s5 = servi({ frais: '1' });
    verifier('?frais=1 : « demandé »', s5.cache === 'manqué' && s5.raison === 'demandé', JSON.stringify(s5));
    const s6 = servi();
    verifier('… et l’ouverture suivante est servie du cache, sans raison à dire', s6.cache === 'alias' && s6.raison === undefined, JSON.stringify(s6));
  }

  // =================================================================
  section('Le Diagnostic juste après « Activer l’ouverture rapide », et juste après un geste qui préchauffe');
  {
    maintenant = Date.UTC(2026, 9, 19, 6, 30);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 80, ths: 20, see: 20 });
    const m = monde(classeur, proprietes);
    const ligneA = d => (d.split('\n').filter(l => /Ouverture rapide/.test(l))[0] || '').trim();
    const aVerifier = d => { const i = d.indexOf('À vérifier avant de présenter'); return i === -1 ? '' : d.slice(i); };
    m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
    maintenant += 2 * MINUTE;
    const d1 = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('deux minutes après l’activation : ✓ — le premier préchauffage est fait, le déclencheur prend le relais ; aucune alerte, rien « à vérifier »',
      /^✓ Ouverture rapide : activée il y a 2 min — premier préchauffage fait il y a 2 min, 2 contrats prêts \(« HDK », « THS »\) ; le déclencheur prend le relais/.test(ligneA(d1)) &&
      !/⚠ Ouverture rapide/.test(d1) && !/Ouverture rapide/.test(aVerifier(d1)), ligneA(d1));
    m.declencheur(maintenant + 115 * MINUTE);
    maintenant += MINUTE;
    m.executer(function (ctx) { ctx.enregistrerInstantaneHebdo(); });       // l'archivage du menu : le préchauffage suit le OK
    maintenant += MINUTE;
    const d2 = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('une minute après un archivage du menu (qui préchauffe, sans déclencheur) : ✓, le déclencheur toujours vu en vie',
      /^✓ Ouverture rapide : activée — dernier préchauffage il y a (1 min|moins d'une minute), 2 contrats prêts/.test(ligneA(d2)) && !/⚠ Ouverture rapide/.test(d2), ligneA(d2));
    /* Le déclencheur arrêté pour de bon, mais des gestes préchauffent encore. */
    const fin = maintenant + 90 * MINUTE;
    while (maintenant + 10 * MINUTE <= fin) { maintenant += 10 * MINUTE; m.executer(function (ctx) { ctx.prechaufferTableau(); }); }
    const d3 = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('le déclencheur muet depuis une heure et demie, même si des gestes préchauffent : ⚠, avec où regarder',
      /^⚠ Ouverture rapide : activée, mais aucun préchauffage depuis \d+ (min|h) — Apps Script → Exécutions/.test(ligneA(d3)), ligneA(d3));
  }

  // =================================================================
  section('Le Diagnostic (b) : « prêt » veut dire entier');
  {
    maintenant = Date.UTC(2026, 9, 19, 6, 30);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 200, ths: 30, see: 50 });
    const m = monde(classeur, proprietes);
    m.configuration = 'CACHE_TAILLES.gz = 8000;';      // des morceaux plus petits : HDK en plusieurs
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    m.executer(function (ctx) { ctx.getDonneesCompactes('THS'); });
    const manifeste = [...m.cache.m.keys()].filter(k => /^SFWD2:[0-9a-z]+:[0-9a-z]+:m$/.test(k))
      .map(k => [k, JSON.parse(m.cache.m.get(k).v)]).filter(x => x[1].contrat === 'HDK')[0];
    verifier('(HDK est rangé en plusieurs morceaux)', !!manifeste && manifeste[1].n >= 2, manifeste ? String(manifeste[1].n) : '');
    const avant = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('entier : « HDK » prêt, c’est lui que la page ouvre ; 2 contrats sur 2', /« HDK » : prêt — .*c'est lui que la page ouvre/.test(avant) && /2 contrats sur 2/.test(avant));
    m.cache.m.delete(manifeste[0].replace(/:m$/, ':' + (manifeste[1].n - 1)));   // le dernier morceau évincé
    const apres = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('un morceau évincé : « HDK » incomplet — ni « prêt », ni « c’est lui que la page ouvre » ; 1 contrat sur 2',
      /« HDK » : incomplet — /.test(apres) && !/« HDK » : prêt/.test(apres) && /En cache, pour le classeur tel qu'il est : 1 contrat sur 2/.test(apres),
      apres.slice(apres.indexOf('En cache'), apres.indexOf('En cache') + 400));
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    verifier('… et, en effet, l’ouverture suivante relit le classeur', m.lectureComplete());
  }

  // =================================================================
  section('Les mesures de la page : deux ouvertures à quelques secondes, une ligne chacune');
  {
    maintenant = Date.UTC(2026, 9, 19, 7, 0);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 60, ths: 20, see: 10 });
    const m = monde(classeur, proprietes);
    m.executer(function (ctx) { ctx.onEdit({}); });
    maintenant += MINUTE;
    const a = m.executer(function (ctx) { return JSON.parse(donneesDeLaPage(ctx)); });   // A relit le classeur
    maintenant += 4000;
    const b = m.executer(function (ctx) { return JSON.parse(donneesDeLaPage(ctx)); });   // B, quatre secondes après : servie par l'alias
    /* Ce que la page envoie (mesuresOuverture) : le début de l'ouverture au serveur, lu dans l'enveloppe. */
    const page = function (env, tout) {
      const s = env.mesures.serveur;
      return { quand: maintenant, contrat: 'HDK', cache: s.cache, raison: s.raison, debut: s.debut, serveur: s.fin - s.debut, transfert: 300,
               synthese: 900, tout: tout, plans: 60, releves: 6, octets: env.gz.length, largeur: 1440, cle: env.cle };
    };
    maintenant += 2000;
    m.executer(function (ctx) { ctx.noterConsultation(page(b, 1200)); });              // B parle d'abord
    maintenant += 1000;
    m.executer(function (ctx) { ctx.noterConsultation(page(a, 2600)); });              // puis A
    m.executer(function (ctx) { ctx.noterConsultation(page(a, 2600)); });              // A, une seconde fois (un double envoi)
    const liste = JSON.parse(proprietes.SUIVI_FWD_MESURES || '[]');
    const manque = liste.filter(x => x.cache === 'manqué');
    verifier('A (cache manqué) et B (l’alias), B signalée la première : deux lignes, aucune « non signalée », A avec ses temps de page',
      a.mesures.serveur.cache === 'manqué' && b.mesures.serveur.cache === 'alias' && liste.length === 2 && !liste.some(x => x.seule) &&
      manque.length === 1 && manque[0].tout === 2600 && manque[0].raison === 'modifié' && manque[0].modifie > 0, JSON.stringify(liste));
    const diag = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('… et le Diagnostic compte deux ouvertures, la moitié du cache, aucune « que la page n’a pas signalée »',
      /Les 2 dernières ouvertures : 1 servie du cache \(50 %\)/.test(diag) && !/n'a pas signalée/.test(diag), diag.slice(diag.indexOf('Les 2'), diag.indexOf('Les 2') + 200));
  }

  // =================================================================
  section('Le préchauffage : sans danger, sans attendre');
  {
    maintenant = Date.UTC(2026, 9, 21, 6, 30);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 200, ths: 50, see: 100 });
    const m = monde(classeur, proprietes);
    m.executer(function (ctx) { ctx.installerOuvertureRapide(); ctx.installerOuvertureRapide(); ctx.installerSuiviHebdomadaire(); });
    const prechauffeurs = m.declencheurs.filter(d => d.getHandlerFunction() === 'prechaufferTableau');
    verifier('« Activer l’ouverture rapide » deux fois : un seul déclencheur, toutes les dix minutes ; celui du vendredi n’est pas touché',
      prechauffeurs.length === 1 && prechauffeurs[0].__horaire.minutes === 10 && m.declencheurs.some(d => d.getHandlerFunction() === 'enregistrerInstantaneHebdo'),
      JSON.stringify(m.declencheurs.map(d => d.getHandlerFunction())));
    verifier('… le premier passage se fait tout de suite, et le dit dans le journal d’exécution',
      m.journal.some(l => /^Suivi FWD · préchauffage · 2 contrats prêts \(HDK, THS\), préparés : /.test(l)), m.journal.slice(-3).join(' | '));
    verifier('… sans nouvelle autorisation : le même déclencheur horaire que celui du vendredi (ScriptApp)', /ScriptApp\.newTrigger\('prechaufferTableau'\)/.test(fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8')));
    /* Rien à faire : aucune lecture. */
    m.declencheur(maintenant + 10 * MINUTE);
    verifier('un passage sans rien de changé : rien n’est relu', !m.lectureComplete() && /rien à relire/.test(m.journal[m.journal.length - 1]), m.journal[m.journal.length - 1]);
    noter('passage à vide : ' + m.appels().length + ' appels (' + resumeAppels(m.appels()) + ')');
    /* Le verrou pris par un geste : il passe son tour, sans lire, sans attendre. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    const pris = m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: 'x' }); },
      { preparer: function (ctx) { ctx.LockService = { getScriptLock: function () { return { tryLock: function (ms) { pris.attente = ms; return false; }, releaseLock: function () {} }; } }; } });
    verifier('le verrou tenu par un geste (l’archivage du vendredi…) : le préchauffage passe son tour, sans rien lire',
      pris.raison === 'verrou' && !m.lectureComplete() && m.appels().indexOf('Spreadsheet.getSheets') === -1, JSON.stringify(pris));
    let tenu = 0, rendu = 0;
    m.executer(function (ctx) { return ctx.prechaufferTableau(); },
      { preparer: function (ctx) { ctx.LockService = { getScriptLock: function () { return { tryLock: function (ms) { tenu = ms; return true; }, releaseLock: function () { rendu++; } }; } }; } });
    verifier('libre, le verrou n’est qu’essayé (0 ms) et rendu aussitôt — jamais tenu pendant la lecture', tenu === 0 && rendu === 1 && m.lectureComplete());
    /* Un import en cours d'envoi : l'onglet temporaire grandit d'un passage à l'autre. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    const temp = new Feuille('HDK (import 3f2a9c)', [['a'], ['b']]);
    temp.classeur = classeur;
    classeur.feuilles.push(temp);
    const t1 = m.executer(function (ctx) { return ctx.prechaufferTableau(); });
    temp.valeurs.push(['c']);
    const t2 = m.executer(function (ctx) { return ctx.prechaufferTableau(); });
    const t3 = m.executer(function (ctx) { return ctx.prechaufferTableau(); });
    verifier('un import en cours d’envoi : le préchauffage attend ; un reste qui ne bouge plus ne l’arrête qu’un passage',
      t1.raison === 'import' && t2.raison === 'import' && t3.raison === '' && t3.construits.length >= 1, JSON.stringify([t1.raison, t2.raison, t3.raison, t3.construits]));
    classeur.feuilles.splice(classeur.feuilles.indexOf(temp), 1);
    /* Un contrat illisible pour cette version : pas relu à chaque passage. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    const nb = { lectures: 0 };
    const casser = function (ctx) { vm.runInContext("var __g = getDonneesPourClient; getDonneesPourClient = function (c) { if (c === 'THS') { __illisible(); return { ok: false, message: 'illisible' }; } return __g.apply(this, arguments); };", ctx); ctx.__illisible = function () { nb.lectures++; }; };
    m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: 'x' }); }, { preparer: casser });
    m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: 'x' }); }, { preparer: casser });
    verifier('un contrat qui ne se lit pas : essayé une fois par version des données, pas à chaque passage', nb.lectures === 1, String(nb.lectures));
    /* Un historique illisible le temps d'une panne de Google (l'onglet ne se
       lit pas : c'est le classeur qui fait défaut, pas le Code) : pas gardé,
       et réessayé au passage suivant. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    const histo = classeur.getSheetByName('Historique_FWD_HDK');
    const hdk = classeur.getSheetByName('HDK');
    let lecturesHDK = 0;
    hdk.getDataRange = function () { lecturesHDK++; return Feuille.prototype.getDataRange.apply(this, arguments); };
    histo.getRange = function () { throw new Error('Service Spreadsheets timed out while accessing document'); };
    const b1 = m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: 'x' }); });
    const l1 = m.journal[m.journal.length - 1];
    verifier('un historique illisible le temps d’une panne : rien n’est gardé ; HDK lu une fois dans le passage (l’ouverture, c’est lui), et le journal le dit — pas « rien à relire »',
      b1.construits.length === 1 && b1.construits[0] === 'THS' && b1.echecs.length === 0 && lecturesHDK === 1 &&
      /relu sans pouvoir le garder en cache : HDK .*réessayé dans 10 min/.test(l1) && !/rien à relire/.test(l1), JSON.stringify([b1.construits, b1.echecs, lecturesHDK]) + ' ' + l1);
    const avantJour = lecturesHDK, lignesJour = m.journal.length;
    const passagesJour = m.declencheur(maintenant + 24 * HEURE);
    const journee = m.journal.slice(lignesJour).filter(l => /^Suivi FWD · préchauffage/.test(l));
    verifier('la panne dure une journée : HDK relu de plus en plus rarement (passage suivant, puis 20, 40, 80 min, deux heures au plus) — ' +
      (lecturesHDK - avantJour) + ' lectures en ' + passagesJour + ' passages, au lieu de deux par passage',
      passagesJour === 144 && lecturesHDK - avantJour >= 5 && lecturesHDK - avantJour <= 20 &&
      journee.every(l => !/rien à relire/.test(l)) && journee.some(l => /en attente : HDK/.test(l)), String(lecturesHDK - avantJour));
    delete histo.getRange;
    const lignesFin = m.journal.length;
    m.declencheur(maintenant + 2 * HEURE + 10 * MINUTE);
    verifier('la panne finie, HDK est prêt au plus tard deux heures après', m.journal.slice(lignesFin).some(l => /préparés? : HDK/.test(l)),
      m.journal.slice(lignesFin).filter(l => /préparé/.test(l)).join(' | '));
    delete hdk.getDataRange;
    /* Le cache qui refuse le paquet de HDK : même retenue. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    let lecturesRefus = 0;
    hdk.getDataRange = function () { lecturesRefus++; return Feuille.prototype.getDataRange.apply(this, arguments); };
    const refuser = function (ctx) {
      const c = m.cache;
      ctx.CacheService = { getDocumentCache: function () { return null; }, getScriptCache: function () {
        return { get: c.get.bind(c), getAll: c.getAll.bind(c), put: c.put.bind(c), putAll: function (o, sec) {
          if (Object.keys(o).some(k => String(o[k]).length > 5000)) throw new Error('Argument too large: value');
          return c.putAll(o, sec); } }; } };
    };
    for (let i = 0; i < 36; i++) { maintenant += 10 * MINUTE; m.executer(function (ctx) { return ctx.prechaufferTableau({ triggerUid: 'x' }); }, { preparer: refuser }); }
    verifier('le cache qui refuse le paquet : six heures de passages, HDK relu ' + lecturesRefus + ' fois — et non à chaque passage', lecturesRefus >= 3 && lecturesRefus <= 10, String(lecturesRefus));
    delete hdk.getDataRange;
    /* Le budget : un paquet préparé il y a plus de vingt heures est refait, hors du chemin des lectrices. */
    m.declencheur(maintenant + 10 * MINUTE);
    const avant = m.journal.length;
    m.declencheur(maintenant + 21 * HEURE);
    const refaits = m.journal.slice(avant).filter(l => /préparés? : /.test(l));
    verifier('vingt et une heures sans changement : le préchauffage refait les paquets une fois (rattrape ce que la clé ne voit pas)',
      refaits.length >= 1 && refaits.length <= 2, refaits.join(' | '));
    m.executer(function (ctx) { ctx.desinstallerOuvertureRapide(); });
    verifier('« Désactiver l’ouverture rapide » retire son déclencheur, et lui seul',
      !m.declencheurs.some(d => d.getHandlerFunction() === 'prechaufferTableau') && m.declencheurs.some(d => d.getHandlerFunction() === 'enregistrerInstantaneHebdo'));
    verifier('le menu porte les deux gestes, et ils sont publics (le menu les appelle)',
      m.executer(function (ctx) { ctx.onOpen(); return ctx.__menu; }).join().indexOf('installerOuvertureRapide,desinstallerOuvertureRapide') !== -1);
    let refus = '';
    try { m.executer(function (ctx) { ctx.__sansInterface = true; ctx.installerOuvertureRapide(); }); } catch (e) { refus = e.message; }
    verifier('installer le déclencheur depuis la page (google.script.run) est refusé : c’est un geste du classeur', /Geste refusé/.test(refus), refus);
  }

  // =================================================================
  section('Les temps : le journal d’exécution, la page, le Diagnostic');
  {
    maintenant = Date.UTC(2026, 9, 22, 6, 30);
    const { classeur, proprietes } = classeurDuBureau({ hdk: 200, ths: 50, see: 100 });
    const m = monde(classeur, proprietes);
    const env = m.executer(function (ctx) { ctx.doGet({ parameter: {} }); return JSON.parse(donneesPourIndex(ctx)); });
    const ligne = m.journal.filter(l => /^Suivi FWD · ouverture /.test(l))[0] || '';
    verifier('une ligne par ouverture dans Apps Script → Exécutions : le contrat, le cache, le total, les étapes, le poids',
      /^Suivi FWD · ouverture HDK · cache manqué · \d+,\d\d s \(version \d+,\d\d · cache \d+,\d\d · gates \d+,\d\d · historique \d+,\d\d · see \d+,\d\d · compactage \d+,\d\d · compression \d+,\d\d · écriture \d+,\d\d · page \d+,\d\d\) · \d+ Ko$/.test(ligne), ligne);
    m.executer(function (ctx) { ctx.getDonneesCompactes('HDK'); });
    verifier('… et pour un changement de contrat servi du cache', /^Suivi FWD · contrat HDK · cache trouvé · \d+,\d\d s \(version \d+,\d\d · cache \d+,\d\d\) · \d+ Ko$/.test(m.journal[m.journal.length - 1]), m.journal[m.journal.length - 1]);
    /* La page renvoie ses temps. */
    maintenant += 2000;
    const ok = m.executer(function (ctx) {
      return ctx.noterConsultation({ quand: maintenant, contrat: 'HDK', cache: env.mesures.serveur.cache, serveur: env.mesures.serveur, transfert: 600, synthese: 1100,
        tout: 1900, plans: 200, releves: 6, octets: env.gz.length, largeur: 1440, cle: env.cle, nom: 'quelqu’un@airbus.com' });
    });
    const gardees = JSON.parse(proprietes.SUIVI_FWD_MESURES || '[]');
    const g = gardees[gardees.length - 1] || {};
    verifier('noterConsultation(mesures) compte l’ouverture et garde ses temps : serveur, transfert, synthèse, tout affiché',
      ok === true && typeof g.serveur === 'number' && g.transfert === 600 && g.synthese === 1100 && g.tout === 1900 && g.plans === 200, JSON.stringify(g));
    verifier('… sans rien qui nomme quelqu’un : ce que la page ajoute d’autre est ignoré, la clé de cache n’est pas gardée',
      !/airbus|quelqu|SFWD/.test(proprietes.SUIVI_FWD_MESURES), proprietes.SUIVI_FWD_MESURES);
    m.executer(function (ctx) {
      ctx.noterConsultation({ serveur: 'beaucoup', tout: -5, synthese: 1e12, cle: 'SFWD2:x:y:0' + '</script>' });
    });
    const g2 = JSON.parse(proprietes.SUIVI_FWD_MESURES).slice(-1)[0];
    verifier('des mesures fantaisistes sont bornées ou écartées', g2.serveur === undefined && g2.tout === 0 && g2.synthese === 3600000 && !('cle' in g2), JSON.stringify(g2));
    for (let i = 0; i < 40; i++) m.executer(function (ctx) { ctx.noterConsultation({ serveur: 300 + i, transfert: 400, synthese: 900, tout: 1500 + 100 * i, cache: 'alias', contrat: 'HDK' }); });
    const trente = JSON.parse(proprietes.SUIVI_FWD_MESURES);
    verifier('les trente dernières ouvertures au plus, sous la limite d’une propriété (9 Ko)', trente.length === 30 && proprietes.SUIVI_FWD_MESURES.length < 9000,
      trente.length + ' / ' + proprietes.SUIVI_FWD_MESURES.length);
    /* Une page fermée avant d'avoir parlé : son ouverture, qui a relu, est quand même comptée au passage suivant. */
    m.executer(function (ctx) { ctx.onEdit({}); });
    maintenant += MINUTE;
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    /* (l'horloge simulée ne court pas pendant une exécution : on donne à cette relecture la durée d'une vraie) */
    const derniere = JSON.parse(m.cache.get('SFWD:mesure'));
    derniere.serveur = 4200;
    m.cache.put('SFWD:mesure', JSON.stringify(derniere), 21600);
    m.executer(function (ctx) { ctx.noterConsultation(); });
    const seule = JSON.parse(proprietes.SUIVI_FWD_MESURES).filter(x => x.seule);
    verifier('une ouverture qui a relu le classeur et dont la page n’a rien dit : gardée quand même, avec le moment où le classeur a changé',
      seule.length === 1 && seule[0].cache === 'manqué' && seule[0].modifie > 0, JSON.stringify(seule));
    /* Le paquet prolongé par l'ouverture (débrief 23 : un cache servi toute la journée n'expire pas).
       Quelques secondes plus tard : une autre ouverture, un autre début au serveur. */
    maintenant += 5000;
    const env2 = m.executer(function (ctx) { return JSON.parse(donneesPourIndex(ctx)); });
    const kbase = env2.cle;
    const avantTouche = JSON.parse(m.cache.get(kbase + ':m')).toucheLe;
    maintenant += 2 * HEURE;
    m.executer(function (ctx) { ctx.noterConsultation({ cle: kbase, serveur: env2.mesures.serveur, tout: 1000 }); });
    const apres2h = JSON.parse(m.cache.get(kbase + ':m')).toucheLe;
    maintenant += 2 * HEURE;
    m.executer(function (ctx) { ctx.noterConsultation({ cle: kbase, tout: 1000 }); });
    const apres4h = JSON.parse(m.cache.get(kbase + ':m')).toucheLe;
    maintenant += 5 * HEURE;
    const encore = m.executer(function (ctx) { return ctx.getDonneesCompactes(''); });
    verifier('l’ouverture prolonge son paquet s’il a été posé il y a plus de trois heures — et le paquet est encore là neuf heures après',
      apres2h === avantTouche && apres4h > avantTouche && !m.lectureComplete() && encore.cle === kbase, JSON.stringify([avantTouche, apres2h, apres4h]));
    /* Le Diagnostic. */
    m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
    m.declencheur(maintenant + 20 * MINUTE);
    const diag = m.executer(function (ctx) { return ctx.diagnostic(); });
    const bloc = diag.slice(diag.indexOf('Vitesse d\'ouverture :'), diag.indexOf('Consultations de la page'));
    verifier('Diagnostic (a) : « Ouverture rapide : activée — dernier préchauffage il y a … min, 2 contrats prêts »',
      /✓ Ouverture rapide : activée — dernier préchauffage il y a (\d+ min|moins d'une minute), 2 contrats prêts \(« HDK », « THS »\)\./.test(bloc), bloc);
    verifier('Diagnostic (b) : chaque contrat, prêt ou non, compressé et en clair, ses morceaux, quand il a été préparé',
      /« HDK » : prêt — \d+ Ko compressés \([\d  ]+ Ko de données\), \d morceaux?, préparé (à|le) /.test(bloc) && /« THS » : prêt/.test(bloc), bloc);
    verifier('Diagnostic (c) : les dernières ouvertures — part servie du cache, serveur médian et au pire, avec sa cause ; puis l’affichage',
      /✓ Les 30 dernières ouvertures : \d+ servies? du cache \(\d+ %\) ; serveur médian \d+,\d s, au pire 4,2 s \(.* — cache manqué, classeur modifié (à|le) /.test(bloc) &&
      /à l'écran : synthèse affichée en \d+,\d s, tout affiché en \d+,\d s \(médianes\) ; \d+ ouvertures? sur \d+ au-delà de 3 s/.test(bloc) &&
      /dont 1 que la page n'a pas signalée/.test(bloc), bloc);
    verifier('Diagnostic (d) : l’essai de compression', /✓ Compression du paquet : essai aller-retour réussi/.test(bloc), bloc);
    verifier('Diagnostic (e) : les temps d’une vraie lecture restent là, et le poids envoyé est celui de l’enveloppe',
      /✓ Paquet envoyé à la page : \d+ Ko \(contrat « HDK »/.test(diag) && /compressé : \d+ Ko de données en clair/.test(diag) && /préparé en \d+,\d s — lecture de GATES/.test(diag), diag.slice(0, 0));
    m.executer(function (ctx) { ctx.desinstallerOuvertureRapide(); });
    maintenant += 2 * HEURE;
    const diag2 = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('désactivée : « non activée → menu Suivi FWD → Activer l’ouverture rapide », sans en faire un point à vérifier avant de présenter',
      /– Ouverture rapide : non activée → menu Suivi FWD → Activer l'ouverture rapide/.test(diag2) && !/À vérifier avant de présenter[\s\S]*Ouverture rapide/.test(diag2));
    proprietes.SUIVI_FWD_PRECHAUFFAGE = JSON.stringify({ active: true, dernierDeclencheur: maintenant - 3 * HEURE });
    const diag3 = m.executer(function (ctx) { return ctx.diagnostic(); });
    verifier('activée mais muette depuis trois heures : le Diagnostic le signale (⚠), avec où regarder', /⚠ Ouverture rapide : activée, mais aucun préchauffage depuis \d+ h — Apps Script → Exécutions/.test(diag3), diag3.slice(diag3.indexOf('Vitesse'), diag3.indexOf('Vitesse') + 300));
  }

  // =================================================================
  section('Les cibles du plan : une semaine, et le nombre d’appels d’une ouverture');
  {
    /* La semaine de semaine.js (scratchpad d23/serveur) : neuf appels comptés par jour,
       un import le lundi, une saisie chaque matin, l'archivage du vendredi. */
    const semaine = function (avecPrechauffage) {
      maintenant = Date.UTC(2026, 9, 26, 0, 0);   // lundi 26/10/2026, minuit (heure d'hiver : UTC+1)
      const lundi = maintenant;
      const { classeur, proprietes } = classeurDuBureau();
      const m = monde(classeur, proprietes);
      if (avecPrechauffage) m.executer(function (ctx) { ctx.installerOuvertureRapide(); });
      const h = (j, hh, mm) => lundi + j * JOUR + ((hh - 1) * 60 + mm) * MINUTE;
      const evts = [];
      for (let j = 0; j < 5; j++) {
        if (j === 0) evts.push([h(j, 8, 0), 'import (marque)', c => c.marquerDonneesModifiees_()]);
        evts.push([h(j, 8, 30), 'Nathan ouvre (menu)', c => c.ouvrirTableauDeBord(), 1]);
        evts.push([h(j, 8, 32), '  → THS', c => c.getDonneesCompactes('THS'), 1]);
        evts.push([h(j, 8, 33), '  → retour HDK', c => c.getDonneesCompactes('HDK'), 1]);
        evts.push([h(j, 9, 15), 'saisie (onEdit)', c => c.onEdit({})]);
        evts.push([h(j, 10, 0), 'collègue …/exec', c => c.doGet({ parameter: {} }), 1]);
        evts.push([h(j, 11, 30), 'Nathan ouvre', c => c.ouvrirTableauDeBord(), 1]);
        evts.push([h(j, 14, 0), 'collègue …/exec', c => c.doGet({ parameter: {} }), 1]);
        evts.push([h(j, 14, 1), '  → Vue d’ensemble (THS)', c => c.getDonneesCompactes('THS'), 1]);
        evts.push([h(j, 15, 30), 'Nathan ouvre', c => c.ouvrirTableauDeBord(), 1]);
        evts.push([h(j, 16, 45), 'Nathan ouvre', c => c.ouvrirTableauDeBord(), 1]);
        if (j === 4) evts.push([h(j, 17, 0), 'archivage du vendredi', c => c.enregistrerInstantaneHebdo({ triggerUid: 'vendredi' }), 0, true]);
      }
      let appels = 0, relues = 0, passages = 0;
      const rates = [];
      evts.forEach(function (e) {
        if (avecPrechauffage) passages += m.declencheur(e[0]); else maintenant = e[0];
        m.executer(function (ctx) { if (e[4]) { ctx.__sansInterface = true; ctx.ScriptApp.getProjectTriggers = function () { return [{ getUniqueId: function () { return 'vendredi'; } }]; }; } return e[2](ctx); });
        if (!e[3]) return;
        appels++;
        if (m.lectureComplete()) { relues++; rates.push(new Date(e[0]).toISOString().slice(5, 16) + ' ' + e[1]); }
      });
      return { appels: appels, relues: relues, rates: rates, passages: passages };
    };
    const sans = semaine(false);
    noter('sans préchauffage : ' + sans.relues + ' lectures complètes sur ' + sans.appels + ' appels (avant le débrief 23 : 30 sur 45)');
    const avec = semaine(true);
    noter('avec préchauffage : ' + avec.relues + ' sur ' + avec.appels + (avec.rates.length ? ' (' + avec.rates.join(' ; ') + ')' : '') + ', ' + avec.passages + ' passages du déclencheur');
    verifier('une semaine simulée, avec le préchauffage : au plus 2 lectures complètes sur 45 appels comptés (30 avant)', avec.appels === 45 && avec.relues <= 2,
      avec.relues + ' / ' + avec.appels);
    verifier('… et sans lui, déjà moins (la date sortie de la clé, l’alias, le cache du script : 25 au plus, 30 avant)', sans.relues <= 25, String(sans.relues));

    /* Les appels d'une ouverture. */
    maintenant = Date.UTC(2026, 10, 2, 7, 30);
    const { classeur, proprietes } = classeurDuBureau();
    const m = monde(classeur, proprietes);
    const nbOnglets = classeur.getSheets().length;
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    const froid = m.appels().slice();
    m.executer(function (ctx) { ctx.doGet({ parameter: {} }); });
    const chaud = m.appels().slice();
    m.executer(function (ctx) { ctx.getDonneesCompactes('THS'); });
    const thsFroid = m.appels().slice();
    m.executer(function (ctx) { ctx.getDonneesCompactes('THS'); });
    const thsChaud = m.appels().slice();
    const n = compter(chaud);
    noter('ouverture servie du cache (' + nbOnglets + ' onglets) : ' + chaud.length + ' appels — ' + resumeAppels(chaud));
    noter('ouverture qui relit le classeur : ' + froid.length + ' appels — ' + resumeAppels(froid));
    noter('changement de contrat : ' + thsFroid.length + ' appels à froid, ' + thsChaud.length + ' du cache');
    verifier('servie du cache : aucune lecture du classeur, deux fichiers HTML lus (Styles, Javascript — plus les trois du contrôle)',
      !chaud.some(a => /getDisplayValues|getValues|getDataRange|getRange/.test(a)) && n['HtmlService.createHtmlOutputFromFile'] === 2 && n['HtmlService>getContent'] === 2, resumeAppels(chaud));
    verifier('servie du cache : un seul appel au cache (l’alias, le manifeste et les morceaux ensemble)', n['CacheService>getAll'] === 1 && !n['CacheService>get'] && !n['CacheService>put'] && !n['CacheService>putAll'],
      resumeAppels(chaud));
    /* La version des données lit le nom, l'état et la taille de chaque onglet (quatre appels chacun) : c'est ce qui
       garantit qu'aucun chiffre périmé n'est servi (§ 6 du plan). Le reste tient en douze appels. */
    verifier('servie du cache : 12 appels + 4 par onglet (' + (12 + 4 * nbOnglets) + ' ici ; 41 avant le débrief 23)', chaud.length <= 12 + 4 * nbOnglets, String(chaud.length));
    verifier('qui relit le classeur : au plus 70 appels (201 avant)', froid.length <= 70, String(froid.length));
    verifier('un changement de contrat qui relit : au plus 70 appels (210 avant) ; servi du cache : la version et un appel au cache',
      thsFroid.length <= 70 && thsChaud.length <= 6 + 4 * nbOnglets, thsFroid.length + ' / ' + thsChaud.length);
  }

  // =================================================================
  section('La fenêtre d’import reste en ES5, et le chargeur garde son paquet en clair');
  {
    let acorn = null;
    for (const lieu of ['acorn', '/opt/node-tools/node_modules/acorn']) { try { acorn = require(lieu); break; } catch (e) { /* suivant */ } }
    const { classeur, proprietes } = classeurDuBureau({ hdk: 20, ths: 10, see: 5 });
    const m = monde(classeur, proprietes);
    const source = m.executer(function (ctx) { return ctx.scriptImportSecondeBase_.toString(); });
    verifier('la fenêtre d’import lance le préchauffage après un import réussi, sans l’attendre', /google\.script\.run\.withFailureHandler\(function \(\) \{\}\)\.prechaufferTableau\(\)/.test(source));
    if (acorn) {
      let erreur = '';
      try { acorn.parse('(' + source + ')', { ecmaVersion: 5 }); } catch (e) { erreur = e.message; }
      verifier('le programme de la fenêtre d’import se lit en ES5 (acorn, ecmaVersion 5)', !erreur, erreur);
      const index = fs.readFileSync(path.join(__dirname, 'Index.modele.html'), 'utf8');
      const pont = /<script>\s*\/\* La livraison de ce fichier[\s\S]*?<\/script>/.exec(index);
      let erreurPont = '';
      try { acorn.parse(pont[0].replace(/^<script>|<\/script>$/g, '').replace(/<\?!=[\s\S]*?\?>/g, 'null'), { ecmaVersion: 5 }); } catch (e) { erreurPont = e.message; }
      verifier('le pont d’Index (chargerContrat, chargerContratJson, noterConsultation) aussi', !!pont && !erreurPont, erreurPont);
    } else {
      console.log('  – acorn introuvable : la lecture ES5 n’est pas refaite ici');
    }
  }

  // =================================================================
  section('Le mode d’emploi dit ce que fait l’ouverture rapide, sans promettre plus');
  {
    const doc = fs.readFileSync(path.join(racine, 'MODE-D-EMPLOI.md'), 'utf8').replace(/\s+/g, ' ');
    const page = fs.readFileSync(path.join(racine, 'prototype', 'suivi-fwd.html'), 'utf8');
    /* Une saisie ne fait que changer la marque (onEdit) : le préchauffage
       passe au plus dix minutes après ; une ouverture entre-temps relit. */
    verifier('pas de promesse qu’il s’ouvre « tout de suite … comme après une saisie » : juste après une saisie, il relit',
      !/tout de suite, le matin comme après une saisie/.test(doc) &&
      /il s'ouvre sans relire le classeur — le matin, juste après un import ou un archivage, et au plus tard dix minutes après une saisie ou un collage \(juste après, il relit le classeur, et le pied le dit\)/.test(doc));
    const corps = /function motCache\(cache, raison\) \{([\s\S]*?)\n  \}/.exec(page);
    /* Les mots d'un cache manqué (« relu : … », « relu à la demande ») ; « relu, sans cache » est le cache de Google absent. */
    const mots = corps ? (corps[1].match(/' \(relu( :| à)[^']*\)'/g) || []).map(m => m.slice(3, -2)) : [];
    verifier('chaque raison que le pied peut donner d’une relecture (' + mots.length + ') est expliquée dans le mode d’emploi',
      mots.length >= 4 && mots.every(m => doc.indexOf('« ' + m + ' »') !== -1), JSON.stringify(mots));
  }

  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
  process.exit(echecs.length ? 1 : 0);
})().catch(function (e) { console.error(e); process.exit(1); });
