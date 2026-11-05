/* Débrief 33 — le détail par jour. Nathan : « maintenant qu'on le lance tous
   les jours, est-ce qu'on ne mettrait pas aussi une granulométrie par jour ?
   Autant en profiter. » Le VRAI Code.gs, sur un classeur en mémoire, avec
   une horloge qu'on règle : chaque archivage de la semaine en cours garde ce
   qui a changé CE JOUR-LÀ dans « Jours_FWD_<contrat> » ; le relevé de la
   semaine, lui, ne change pas. On rejoue la semaine du robot — lundi, mardi
   (deux fois), mercredi sans changement, le menu jeudi, le vendredi —, puis
   le lundi suivant, un historique d'avant sans aucun jour, un contrat
   renommé, masqué, un très gros jour, une semaine rattrapée, un relevé
   supprimé, et le poids du paquet de la page. */
'use strict';
process.env.TZ = 'Europe/Paris';

const zlib = require('zlib');
const vm = require('vm');
const { chargerServeur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleGates, colonne } = require('./feuille-gates');

let reussis = 0;
const echecs = [];
let sectionCourante = '';
function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail ? ' — ' + detail : ''));
  }
}
function section(t) { sectionCourante = t; console.log('\n— ' + t + ' —'); }
function erreurDe(fn) { try { fn(); return ''; } catch (e) { return e && e.message ? e.message : String(e); } }

const I_REF = colonne('Référence UD');
const I_ELEC = colonne('Avancement Définition Electrique', 'HDK AA 011');
const I_HARN = colonne('Avancement Concept Harnais', 'HDK AA 011');

/* Un export GATES à la vraie structure ; `prefixe` : ses références. */
function gates(n, prefixe) {
  const g = feuilleGates(n);
  g.valeurs.forEach((l, r) => { if (r >= 3 && prefixe) l[I_REF] = String(l[I_REF]).replace(/^UD-/, prefixe + '-'); });
  return g;
}
const onglet = (nom, g, cache) => new Feuille(nom, g.valeurs.map(l => l.slice()), !!cache, g.fusions.map(f => Object.assign({}, f)));

/* L'horloge du serveur, comme dans le simulateur : une seule classe dont
   « maintenant » se règle, pour que les dates restent des Date. */
function horloge() {
  let maintenant = 0;
  class DateSimulee extends Date {
    constructor() { if (arguments.length === 0) super(maintenant); else super(...arguments); }
    static now() { return maintenant; }
  }
  return { Date: DateSimulee, regler: function (texte) { maintenant = new Date(texte).getTime(); } };
}

/* Le classeur : HDK (40 plans) et THS (30 plans). */
function monde(options) {
  const o = options || {};
  const c = new Classeur([onglet('HDK', gates(o.hdk || 40)), onglet('THS', gates(o.ths || 30, 'THS'))], 'Suivi FWD jours');
  c.proprietaire = 'nathan@airbus.com';
  const ctx = chargerServeur(c, {});
  ctx.__emailScript = 'nathan@airbus.com';
  ctx.__emailLecteur = 'nathan@airbus.com';
  const h = horloge();
  ctx.Date = h.Date;
  return { c, ctx, h };
}
/* L'import du robot (et de la fenêtre à la main) : la fenêtre appelle importArchiverReleve. */
function importer(ctx, id) { return ctx.importArchiverReleve(ctx.ouvrirJetonImport_(), id); }
/* L'archivage du vendredi, par son vrai déclencheur. */
function vendredi(ctx) {
  let d = ctx.ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'enregistrerInstantaneHebdo')[0];
  if (!d) { ctx.installerSuiviHebdomadaire(); d = ctx.ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'enregistrerInstantaneHebdo')[0]; }
  return ctx.enregistrerInstantaneHebdo({ triggerUid: d.getUniqueId() });
}
const ligneDe = (feuille, ref) => feuille.valeurs.findIndex(l => l[I_REF] === ref);
const refs = feuille => feuille.valeurs.slice(3).map(l => l[I_REF]).filter(Boolean);
function poser(feuille, ref, elec, harnais) {
  const i = ligneDe(feuille, ref);
  if (elec !== undefined) feuille.valeurs[i][I_ELEC] = elec;
  if (harnais !== undefined) feuille.valeurs[i][I_HARN] = harnais;
}
/* La carte gardée d'une semaine, brute (chaînes ou [définition, concept]). */
function carteBrute(ctx, c, id, semaine) {
  const h = ctx.getHistorique(c, id).filter(r => r.semaine === semaine)[0];
  if (!h || !h.plans) return null;
  const o = {};
  Object.keys(h.plans).forEach(k => { o[k] = h.plansConcept ? [h.plans[k], h.plansConcept[k]] : h.plans[k]; });
  return o;
}
/* Le relevé d'une semaine refait jour après jour, en partant de la carte d'avant (comme la page). */
function rejouer(depart, jours, quoi) {
  const carte = Object.assign({}, depart);
  let coherent = true;
  jours.forEach(j => {
    const d = quoi === 'concept' ? j.plansConcept : j.plans;
    Object.keys(d || {}).forEach(ref => {
      const p = d[ref];
      if ((p[0] === null) !== !Object.prototype.hasOwnProperty.call(carte, ref) || (p[0] !== null && carte[ref] !== p[0])) coherent = false;
      if (p[1] === null) delete carte[ref]; else carte[ref] = p[1];
    });
  });
  return { carte, coherent };
}
const def = carte => { const o = {}; Object.keys(carte || {}).forEach(k => { o[k] = Array.isArray(carte[k]) ? carte[k][0] : carte[k]; }); return o; };
const concept = carte => { const o = {}; Object.keys(carte || {}).forEach(k => { o[k] = carte[k][1]; }); return o; };
const pareilles = (a, b) => JSON.stringify(Object.keys(a).sort().map(k => [k, a[k]])) === JSON.stringify(Object.keys(b).sort().map(k => [k, b[k]]));

// =================================================================
section('La semaine du robot : lundi, mardi deux fois, mercredi sans changement, jeudi au menu, vendredi');
{
  const { c, ctx, h } = monde();
  const hdk = c.getSheetByName('HDK');
  const r = refs(hdk);
  /* S44 : le tout premier relevé, le vendredi 30 octobre. */
  h.regler('2026-10-30T17:05:00+01:00');
  const v44 = vendredi(ctx);
  verifier('le tout premier relevé (S44, vendredi) : archivé, sans jour — il n’y a pas de « matin » à comparer, et pas d’onglet Jours_FWD',
    v44.ok && v44.contrats.length === 2 && v44.contrats.every(x => !x.jour) && !c.getSheetByName('Jours_FWD_HDK') && !c.getSheetByName('Jours_FWD_THS'),
    JSON.stringify(v44.contrats.map(x => [x.id, x.jour])));
  const histo = c.getSheetByName('Historique_FWD_HDK');
  const lignesHisto44 = histo.valeurs.length;

  /* Lundi 2 novembre, 14 h 05 : le robot importe HDK — trois plans
     changent, un disparaît, un nouveau arrive. */
  h.regler('2026-11-02T14:05:00+01:00');
  poser(hdk, r[0], 'PWD_IN_PROGRESS');
  poser(hdk, r[1], 'VALIDATED', 'V');
  poser(hdk, r[2], undefined, 'MR');
  const disparu = hdk.valeurs.splice(ligneDe(hdk, r[3]), 1)[0];
  const neuf = hdk.valeurs[ligneDe(hdk, r[4])].slice(); neuf[I_REF] = 'UD-99-0001'; neuf[I_ELEC] = 'TO_TREAT'; neuf[I_HARN] = ''; hdk.valeurs.push(neuf);
  const lundi = importer(ctx, 'HDK');
  const fj = c.getSheetByName('Jours_FWD_HDK');
  /* Débrief 33 (relu) : une colonne de plus, « Après un import » (oui / non),
     avant le détail — un jour sans changement ne se montre que si un export
     a été lu ce jour-là. */
  verifier('lundi : l’import archive S45 et garde le jour — onglet « Jours_FWD_HDK » créé, masqué, ses en-têtes, une ligne « 2026-S45 · 2026-11-02 · 5 changements · après un import : oui »',
    lundi.ok && lundi.semaine === '2026-S45' && !!fj && fj.isSheetHidden() &&
    JSON.stringify(fj.valeurs[0]) === JSON.stringify(['Semaine', 'Jour', 'Écrit le', 'Changements', 'Onglet historique', 'Après un import', 'Plans']) &&
    fj.valeurs.length === 2 && fj.valeurs[1][0] === '2026-S45' && fj.valeurs[1][1] === '2026-11-02' && fj.valeurs[1][3] === 5 &&
    fj.valeurs[1][4] === histo.getSheetId() && fj.valeurs[1][5] === 'oui' && fj.formats[1] === '@',
    JSON.stringify(fj && fj.valeurs.map(l => l.slice(0, 6))));
  const j1 = ctx.getJours(c, 'HDK');
  const p1 = j1[0] && j1[0].plans;
  verifier('lundi, ce que la page reçoit : la définition électrique de chaque plan changé, [avant, après] — nouveau [null, …], disparu […, null] ; le plan dont seul le concept a bougé n’y est pas',
    j1.length === 1 && j1[0].semaine === '2026-S45' && j1[0].jour === '2026-11-02' &&
    p1[r[0]][1] === 'PWD_IN_PROGRESS' && p1[r[1]][1] === 'VALIDATED' && !(r[2] in p1) &&
    p1['UD-99-0001'][0] === null && p1['UD-99-0001'][1] === 'TO_TREAT' && p1[r[3]][1] === null && p1[r[3]][0] === String(disparu[I_ELEC]) &&
    Object.keys(p1).length === 4, JSON.stringify(j1));
  verifier('… et le concept harnais à part : r[1] (V), r[2] (MR), le nouveau et le disparu',
    !!j1[0].plansConcept && j1[0].plansConcept[r[2]][1] === 'MR' && j1[0].plansConcept[r[1]][1] === 'V' && j1[0].plansConcept['UD-99-0001'][1] === '' &&
    j1[0].plansConcept[r[3]][1] === null && !(r[0] in j1[0].plansConcept), JSON.stringify(j1[0].plansConcept));
  verifier('le relevé de la semaine, lui, reste une ligne par semaine (S44, S45) dans Historique_FWD_HDK',
    histo.valeurs.length === lignesHisto44 + 1 && ctx.getHistorique(c, 'HDK').map(x => x.semaine).join() === '2026-S44,2026-S45');
  verifier('THS, pas importé lundi, n’a pas de jour', !c.getSheetByName('Jours_FWD_THS') && ctx.getJours(c, 'THS').length === 0);

  /* Mardi 14 h 05 : deux plans de plus. */
  h.regler('2026-11-03T14:05:00+01:00');
  poser(hdk, r[5], 'PWD_TO_CONTROL');
  poser(hdk, r[6], 'TO_CONFIRM');
  importer(ctx, 'HDK');
  const j2 = ctx.getJours(c, 'HDK');
  verifier('mardi : un second jour, rien que ses deux changements (comparé au soir de lundi, pas au début de la semaine)',
    j2.length === 2 && j2[1].jour === '2026-11-03' && Object.keys(j2[1].plans).sort().join() === [r[5], r[6]].sort().join() &&
    fj.valeurs.length === 3, JSON.stringify(j2.map(j => [j.jour, Object.keys(j.plans)])));

  /* Mardi 17 h : réimporté le même jour — r[6] est revenu, r[7] a bougé. */
  h.regler('2026-11-03T17:00:00+01:00');
  const avantR6 = j2[1].plans[r[6]][0];
  poser(hdk, r[6], avantR6);
  poser(hdk, r[7], 'VALIDATED');
  importer(ctx, 'HDK');
  const j3 = ctx.getJours(c, 'HDK');
  verifier('mardi, réimporté : le jour est REMPLACÉ, recalculé depuis le matin — r[5] et r[7], plus r[6] (revenu) ; toujours deux lignes',
    j3.length === 2 && Object.keys(j3[1].plans).sort().join() === [r[5], r[7]].sort().join() && fj.valeurs.length === 3 && fj.valeurs[2][3] === 2,
    JSON.stringify(j3.map(j => [j.jour, Object.keys(j.plans)])));

  /* Mercredi : le même export, rien n’a bougé. */
  h.regler('2026-11-04T14:05:00+01:00');
  const mercredi = importer(ctx, 'HDK');
  const j4 = ctx.getJours(c, 'HDK');
  verifier('mercredi, rien n’a changé : le jour s’écrit quand même, vide (« aucun changement », le robot est passé)',
    mercredi.ok && j4.length === 3 && j4[2].jour === '2026-11-04' && Object.keys(j4[2].plans).length === 0 && fj.valeurs[3][3] === 0,
    JSON.stringify(j4.map(j => [j.jour, Object.keys(j.plans).length])));

  /* Jeudi : Nathan archive au menu (Suivi FWD → Archiver le relevé de la semaine). */
  h.regler('2026-11-05T10:30:00+01:00');
  poser(hdk, r[8], 'VALIDATED');
  const menu = ctx.enregistrerInstantaneHebdo();
  const j5 = ctx.getJours(c, 'HDK');
  /* Débrief 33 (relu) : THS, archivé du même geste sans avoir été importé,
     n'a plus de jour « aucun changement » dans la page — aucun export de
     THS n'a été lu ce jour-là. Sa ligne est gardée (« Après un import » :
     non), pour l'état du matin si le robot passe plus tard. Avant, on
     attendait un jour vide montré. */
  verifier('jeudi, au menu : HDK garde son jour (r[8], un vrai changement) ; THS, archivé du même geste sans import, n’a pas de jour dans la page (sa ligne est gardée, « Après un import » : non)',
    menu.ok && j5.length === 4 && j5[3].jour === '2026-11-05' && Object.keys(j5[3].plans).join() === r[8] &&
    ctx.getJours(c, 'THS').length === 0 && !!c.getSheetByName('Jours_FWD_THS') && c.getSheetByName('Jours_FWD_THS').valeurs.length === 2 &&
    c.getSheetByName('Jours_FWD_THS').valeurs[1][3] === 0 && c.getSheetByName('Jours_FWD_THS').valeurs[1][5] === 'non' &&
    menu.contrats.filter(x => x.id === 'THS')[0].jour.montre === false && menu.contrats.filter(x => x.id === 'HDK')[0].jour.montre === true,
    JSON.stringify([j5.map(j => j.jour), ctx.getJours(c, 'THS'), menu.contrats.map(x => [x.id, x.jour])]));

  /* Vendredi 6, le robot à 14 h 05 puis le déclencheur à 17 h 05. */
  h.regler('2026-11-06T14:05:00+01:00');
  poser(hdk, r[9], 'TO_CONFIRM');
  importer(ctx, 'HDK');
  h.regler('2026-11-06T17:05:00+01:00');
  const v45 = vendredi(ctx);
  const j6 = ctx.getJours(c, 'HDK');
  verifier('vendredi : le robot puis le déclencheur — un seul jour du vendredi (r[9]), pas deux ; le relevé S45 est mis à jour sur place',
    v45.ok && j6.length === 5 && j6[4].jour === '2026-11-06' && Object.keys(j6[4].plans).join() === r[9] &&
    fj.valeurs.length === 6 && histo.valeurs.length === lignesHisto44 + 1, JSON.stringify(j6.map(j => [j.jour, Object.keys(j.plans)])));

  /* La page refait la semaine jour par jour : elle doit tomber pile sur le relevé. */
  const depart = carteBrute(ctx, c, 'HDK', '2026-S44'), arrivee = carteBrute(ctx, c, 'HDK', '2026-S45');
  const rd = rejouer(def(depart), j6, 'def'), rc = rejouer(concept(depart), j6, 'concept');
  verifier('S44 + les cinq jours = S45, pile, pour la définition électrique ET pour le concept harnais ; chaque « avant » est bien l’état de la veille',
    rd.coherent && rc.coherent && pareilles(rd.carte, def(arrivee)) && pareilles(rc.carte, concept(arrivee)),
    JSON.stringify([rd.coherent, rc.coherent]));

  /* Le lundi suivant : une nouvelle semaine. */
  h.regler('2026-11-09T14:05:00+01:00');
  poser(hdk, r[10], 'VALIDATED');
  const s46 = importer(ctx, 'HDK');
  const j7 = ctx.getJours(c, 'HDK');
  verifier('lundi 9 (S46) : le premier jour de la semaine se compare au dernier relevé de S45 — seul r[10] y est, pas les changements de S45',
    s46.semaine === '2026-S46' && j7.length === 6 && j7[5].semaine === '2026-S46' && j7[5].jour === '2026-11-09' && Object.keys(j7[5].plans).join() === r[10],
    JSON.stringify(j7.slice(-1)));

  /* Ce que la page reçoit : les jours, compactés avec les relevés. */
  const paquet = ctx.getDonneesPourClient('HDK');
  const compact = ctx.compacterPaquet(paquet);
  const tj = compact.relevesTab && compact.relevesTab.jours;
  verifier('le paquet porte les jours (6) ; compacté, chaque jour est une liste [référence, avant, après] dans les tables des relevés (-1 = absent) — jamais une carte entière',
    Array.isArray(paquet.jours) && paquet.jours.length === 6 && Array.isArray(tj) && tj.length === 6 && !('jours' in compact) &&
    tj[0].s === '2026-S45' && tj[0].j === '2026-11-02' && tj[0].p.length === 12 && tj[0].p.indexOf(-1) !== -1 &&
    tj.every(j => j.p.length % 3 === 0 && j.p.every(n => n === -1 || (n >= 0 && Number.isInteger(n)))) &&
    compact.relevesTab.refs[tj[5].p[0]] === r[10], JSON.stringify(tj && tj.map(j => [j.s, j.j, j.p.length, !!j.c])));
  const diag = ctx.diagnostic('HDK');
  verifier('le diagnostic le dit en une ligne : « ✓ Détail par jour : 6 jours gardés, du 2026-11-02 au 2026-11-09 (onglet « Jours_FWD_HDK ») »',
    /✓ Détail par jour : 6 jours gardés, du 2026-11-02 au 2026-11-09 \(onglet « Jours_FWD_HDK »\)/.test(diag), diag.split('\n').filter(l => /jour/i.test(l)).join(' | '));

  /* Supprimer le relevé de la semaine : ses jours partent avec lui. */
  ctx.__confirmations.push('YES');
  const sup = ctx.supprimerDernierReleve();
  verifier('« Supprimer le relevé de cette semaine » (S46) : le relevé ET son jour partent ; ceux de S45 restent',
    sup && sup.supprimes.indexOf('HDK') !== -1 && ctx.getJours(c, 'HDK').length === 5 && ctx.getJours(c, 'HDK').every(j => j.semaine === '2026-S45'),
    JSON.stringify(ctx.getJours(c, 'HDK').map(j => j.jour)));
  h.regler('2026-11-09T15:00:00+01:00');
  importer(ctx, 'HDK');
  const j8 = ctx.getJours(c, 'HDK');
  verifier('réimporté ensuite : S46 repart du relevé de S45 (r[10] seul)', j8.length === 6 && Object.keys(j8[5].plans).join() === r[10], JSON.stringify(j8.slice(-1)));

  /* Une semaine passée rattrapée : pas de jour (on ne sait pas lequel). */
  const avantRattrape = c.getSheetByName('Jours_FWD_HDK').valeurs.length;
  const rattrape = ctx.archiverPourSemaine_(c, 'HDK', 'S45');
  verifier('une semaine passée rattrapée (S45, en S46) : archivée, sans jour écrit',
    rattrape.ok && c.getSheetByName('Jours_FWD_HDK').valeurs.length === avantRattrape, rattrape.message);
}

// =================================================================
/* Débrief 33 (relu) : « ven. 6 nov. : aucun changement » alors que le PC du
   robot était éteint — le déclencheur du vendredi (ou le menu) reprend
   l'onglet tel qu'il est : rien n'a été lu dans GATES ce jour-là. */
section('PC éteint : le vendredi et le menu n’inventent pas de jour « aucun changement »');
{
  const { c, ctx, h } = monde();
  const hdk = c.getSheetByName('HDK');
  const r = refs(hdk);
  h.regler('2026-10-30T17:05:00+01:00'); vendredi(ctx);
  h.regler('2026-11-02T14:05:00+01:00'); poser(hdk, r[0], 'VALIDATED'); importer(ctx, 'HDK');
  h.regler('2026-11-03T14:05:00+01:00'); poser(hdk, r[1], 'VALIDATED'); importer(ctx, 'HDK');
  /* Mercredi à vendredi : le PC du robot est éteint. Vendredi 17 h 05, le déclencheur. */
  h.regler('2026-11-06T17:05:00+01:00');
  const v = vendredi(ctx);
  const jh = ctx.getJours(c, 'HDK');
  verifier('PC éteint vendredi : le déclencheur n’ajoute pas de jour vide — HDK garde lundi et mardi, rien pour vendredi ; THS (jamais importé de la semaine) n’a aucun jour',
    v.ok && jh.map(j => j.jour).join() === '2026-11-02,2026-11-03' && ctx.getJours(c, 'THS').length === 0 &&
    v.contrats.every(x => !x.jour || x.jour.montre === false),
    JSON.stringify([jh.map(j => [j.jour, Object.keys(j.plans).length]), ctx.getJours(c, 'THS'), v.contrats.map(x => [x.id, x.jour])]));
  verifier('… le relevé S45, lui, est bien archivé (une ligne, mise à jour sur place) ; le paquet de la page n’a que lundi et mardi',
    ctx.getHistorique(c, 'HDK').map(x => x.semaine).join() === '2026-S44,2026-S45' &&
    ctx.getDonneesPourClient('HDK').jours.map(j => j.jour).join() === '2026-11-02,2026-11-03');
  /* Le robot passe quand même vendredi, plus tard (PC rallumé à 17 h 30) : son jour compte, depuis le matin. */
  h.regler('2026-11-06T17:30:00+01:00'); poser(hdk, r[2], 'PWD_TO_CONTROL');
  importer(ctx, 'HDK');
  const jv = ctx.getJours(c, 'HDK');
  verifier('le robot passe vendredi APRÈS le déclencheur : son jour est gardé (r[2], comparé au matin), un seul jour du vendredi',
    jv.length === 3 && jv[2].jour === '2026-11-06' && Object.keys(jv[2].plans).join() === r[2] &&
    c.getSheetByName('Jours_FWD_HDK').valeurs.length === 4 && c.getSheetByName('Jours_FWD_HDK').valeurs[3][5] === 'oui',
    JSON.stringify(jv.map(j => [j.jour, Object.keys(j.plans)])));
  /* Le lundi suivant : la semaine se compare au relevé S45, rien de S45 ne se répète. */
  h.regler('2026-11-09T14:05:00+01:00'); poser(hdk, r[3], 'VALIDATED');
  importer(ctx, 'HDK');
  const j9 = ctx.getJours(c, 'HDK');
  verifier('lundi 9 (S46) : seul r[3]', j9.length === 4 && j9[3].jour === '2026-11-09' && Object.keys(j9[3].plans).join() === r[3], JSON.stringify(j9.slice(-1)));
}
{
  /* Le menu le matin, sans changement, puis le robot à 14 h 05 le même jour. */
  const { c, ctx, h } = monde();
  const hdk = c.getSheetByName('HDK');
  const r = refs(hdk);
  h.regler('2026-10-30T17:05:00+01:00'); vendredi(ctx);
  h.regler('2026-11-02T14:05:00+01:00'); poser(hdk, r[0], 'VALIDATED'); importer(ctx, 'HDK');
  h.regler('2026-11-03T09:30:00+01:00');
  const menu = ctx.enregistrerInstantaneHebdo();
  verifier('mardi 9 h 30, archivé au menu sans changement : pas de jour « aucun changement » dans la page',
    menu.ok && ctx.getJours(c, 'HDK').map(j => j.jour).join() === '2026-11-02', JSON.stringify(ctx.getJours(c, 'HDK').map(j => j.jour)));
  h.regler('2026-11-03T14:05:00+01:00'); poser(hdk, r[1], 'PWD_TO_CONTROL');
  importer(ctx, 'HDK');
  const j = ctx.getJours(c, 'HDK');
  verifier('… puis le robot à 14 h 05 : le jour de mardi est là, avec r[1] — le menu du matin ne lui a pas fait perdre son point de départ',
    j.length === 2 && j[1].jour === '2026-11-03' && Object.keys(j[1].plans).join() === r[1], JSON.stringify(j.map(x => [x.jour, Object.keys(x.plans)])));
  /* Mercredi : l'export du robot ne change rien — le robot est passé, cette fois. */
  h.regler('2026-11-04T14:05:00+01:00');
  importer(ctx, 'HDK');
  h.regler('2026-11-04T17:00:00+01:00');
  ctx.enregistrerInstantaneHebdo();
  const jm = ctx.getJours(c, 'HDK');
  verifier('mercredi, le robot sans changement puis le menu : le jour « aucun changement » reste montré (le robot est passé) — le menu ne l’efface pas',
    jm.length === 3 && jm[2].jour === '2026-11-04' && Object.keys(jm[2].plans).length === 0, JSON.stringify(jm.map(x => [x.jour, Object.keys(x.plans).length])));
  /* Jeudi : Nathan colle un export à la main et archive au menu — un vrai changement se montre. */
  h.regler('2026-11-05T10:00:00+01:00'); poser(hdk, r[2], 'VALIDATED');
  ctx.enregistrerInstantaneHebdo();
  const jj = ctx.getJours(c, 'HDK');
  verifier('jeudi, un export collé à la main puis le menu : le jour se montre, avec son changement (r[2])',
    jj.length === 4 && jj[3].jour === '2026-11-05' && Object.keys(jj[3].plans).join() === r[2], JSON.stringify(jj.map(x => [x.jour, Object.keys(x.plans)])));
}
{
  /* Le dépôt (Apps Script, doPost, archiver: true) : un extract vient d'être déposé. */
  const { c, ctx, h } = monde();
  vm.runInContext("CONFIG.DEPOT = CONFIG.DEPOT || {}; CONFIG.DEPOT.SECRET = 'secret-de-test';", ctx);
  const hdk = c.getSheetByName('HDK');
  h.regler('2026-10-30T17:05:00+01:00'); vendredi(ctx);
  h.regler('2026-11-02T14:05:00+01:00');
  const d = ctx.deposer_(JSON.stringify({ secret: 'secret-de-test', onglet: 'HDK', archiver: true, lignes: hdk.valeurs.map(l => l.map(v => String(v === null || v === undefined ? '' : v))) }));
  verifier('un dépôt sans changement : archivé, et son jour « aucun changement » se montre (un extract a été lu ce jour-là)',
    d.ok && d.archive && d.archive.ok && ctx.getJours(c, 'HDK').length === 1 && Object.keys(ctx.getJours(c, 'HDK')[0].plans).length === 0,
    JSON.stringify([d.ok, d.archive, ctx.getJours(c, 'HDK')]));
}

// =================================================================
section('Un historique d’avant, sans aucun jour');
{
  const { c, ctx, h } = monde();
  const H = ['Semaine', 'Date', 'Total', 'Validés', 'En cours', 'À faire', 'Non renseignés', 'Par dimension', 'Plans'];
  const carte = {}; refs(c.getSheetByName('HDK')).forEach(ref => { carte[ref] = ['EMPTY', '-']; });
  c.feuilles.push(new Feuille('Historique_FWD_HDK', [H.slice(),
    ['2026-S41', new Date(2026, 9, 9, 17), 40, 0, 0, 0, 40, '{}', JSON.stringify(carte)],
    ['2026-S42', new Date(2026, 9, 16, 17), 40, 0, 0, 0, 40, '{}', JSON.stringify(carte)]], true));
  c.feuilles[c.feuilles.length - 1].classeur = c;
  h.regler('2026-11-05T13:15:00+01:00');
  const p = ctx.getDonneesPourClient('HDK');
  const compact = ctx.compacterPaquet(p);
  verifier('lu tel quel : deux relevés, pas de jours — ni dans le paquet, ni dans le paquet compact (le paquet reste celui d’avant)',
    p.releves.length === 2 && !('jours' in p) && ctx.getJours(c, 'HDK').length === 0 && !('jours' in compact.relevesTab) && !('jours' in compact),
    JSON.stringify(Object.keys(p)));
  h.regler('2026-11-05T14:05:00+01:00');
  importer(ctx, 'HDK');
  const j = ctx.getJours(c, 'HDK');
  verifier('le premier import de la semaine (S45) part du dernier relevé gardé (S42) : tous les plans dont la valeur a changé depuis',
    j.length === 1 && j[0].semaine === '2026-S45' && Object.keys(j[0].plans).length > 0 &&
    Object.keys(j[0].plans).every(ref => j[0].plans[ref][0] === 'EMPTY' || j[0].plans[ref][0] === null), JSON.stringify(j[0] && Object.keys(j[0].plans).length));
}

// =================================================================
section('Un contrat renommé garde ses jours ; masqué, il les garde aussi');
{
  const { c, ctx, h } = monde();
  const hdk = c.getSheetByName('HDK');
  const r = refs(hdk);
  h.regler('2026-10-30T17:05:00+01:00'); vendredi(ctx);
  h.regler('2026-11-02T14:05:00+01:00'); poser(hdk, r[0], 'VALIDATED'); importer(ctx, 'HDK');
  h.regler('2026-11-03T14:05:00+01:00'); poser(hdk, r[1], 'VALIDATED'); importer(ctx, 'HDK');
  const fj = c.getSheetByName('Jours_FWD_HDK');
  verifier('Jours_FWD_HDK n’est ni un contrat, ni un contrat masqué, ni un historique orphelin ; un dépôt ne peut pas l’écraser',
    ctx.estOngletInterne('Jours_FWD_HDK') && ctx.listerContrats(c).map(x => x.id).join() === 'HDK,THS' &&
    ctx.contratsRetires_(c).indexOf('Jours_FWD_HDK') === -1 && ctx.historiquesOrphelins(c, ctx.listerContrats(c)).length === 0 &&
    ctx.ongletProtege('Jours_FWD_HDK') === 'un onglet du détail par jour' && ctx.getDonneesPourClient('HDK').avis === '',
    JSON.stringify([ctx.listerContrats(c), ctx.historiquesOrphelins(c, ctx.listerContrats(c)), ctx.getDonneesPourClient('HDK').avis]));
  fj.showSheet();
  verifier('même démasqué, ce n’est toujours pas un contrat', ctx.listerContrats(c).map(x => x.id).join() === 'HDK,THS');
  fj.hideSheet();
  const diag = ctx.diagnostic('HDK');
  verifier('le diagnostic ne le prend ni pour un contrat ni pour un orphelin', !/Jours_FWD_HDK[^»]*» \(.*\) n'est rattaché|contrat « Jours_FWD/.test(diag) && !/rattaché à aucun contrat/.test(diag),
    diag.split('\n').filter(l => /Jours_FWD|rattaché/.test(l)).join(' | '));

  /* Nathan renomme l'onglet HDK en « HDK-NEO » dans Sheets, puis son historique, comme la page le lui dit. */
  hdk.setName('HDK-NEO');
  verifier('l’onglet renommé seul : son historique devient orphelin (comme avant), ses jours ne sont pas pris pour un orphelin',
    ctx.historiquesOrphelins(c, ctx.listerContrats(c)).map(o => o.nom).join() === 'Historique_FWD_HDK',
    JSON.stringify(ctx.historiquesOrphelins(c, ctx.listerContrats(c))));
  c.getSheetByName('Historique_FWD_HDK').setName('Historique_FWD_HDK-NEO');
  const jr = ctx.getJours(c, 'HDK-NEO');
  verifier('son historique renommé à son tour : « HDK-NEO » retrouve ses deux jours (l’onglet des jours suit le numéro de son historique)',
    jr.length === 2 && jr.map(j => j.jour).join() === '2026-11-02,2026-11-03' && ctx.getDonneesPourClient('HDK-NEO').jours.length === 2,
    JSON.stringify(jr.map(j => j.jour)));
  h.regler('2026-11-04T14:05:00+01:00'); poser(hdk, r[2], 'VALIDATED'); importer(ctx, 'HDK-NEO');
  verifier('au prochain import, son onglet des jours prend le nouveau nom (« Jours_FWD_HDK-NEO »), avec ses trois jours',
    !c.getSheetByName('Jours_FWD_HDK') && !!c.getSheetByName('Jours_FWD_HDK-NEO') && ctx.getJours(c, 'HDK-NEO').length === 3 &&
    Object.keys(ctx.getJours(c, 'HDK-NEO')[2].plans).join() === r[2], c.getSheets().map(f => f.getName()).join(', '));

  /* Masquer puis réafficher THS (Administration → Contrats). */
  const ths = c.getSheetByName('THS');
  h.regler('2026-11-04T15:00:00+01:00'); poser(ths, refs(ths)[0], 'VALIDATED'); importer(ctx, 'THS');
  ctx.adminRetirerContrat('THS', true);
  verifier('THS masqué : ni contrat, ni paquet ; son onglet des jours reste là, intact',
    ctx.listerContrats(c).every(x => x.id !== 'THS') && !!c.getSheetByName('Jours_FWD_THS') && c.getSheetByName('Jours_FWD_THS').valeurs.length === 2);
  ctx.adminRetirerContrat('THS', false);
  verifier('réaffiché : ses jours reviennent dans son paquet', (ctx.getDonneesPourClient('THS').jours || []).length === 1);
}

// =================================================================
section('Un très gros jour : la limite de 50 000 caractères par cellule');
{
  const { c, ctx, h } = monde({ ths: 3000 });
  const ths = c.getSheetByName('THS');
  h.regler('2026-10-30T17:05:00+01:00'); vendredi(ctx);
  h.regler('2026-11-02T14:05:00+01:00');
  ths.valeurs.slice(3).forEach(l => { if (l[I_REF]) { l[I_ELEC] = 'PWD_IN_PROGRESS_LONG_' + l[I_REF]; } });
  importer(ctx, 'THS');
  const fj = c.getSheetByName('Jours_FWD_THS');
  /* Débrief 33 (relu) : le détail commence à la 7e colonne (« Après un import » avant lui). */
  const cellules = fj.valeurs[1].slice(6).filter(v => v !== '' && v !== undefined);
  const j = ctx.getJours(c, 'THS');
  verifier('3 000 plans changés le même jour : le détail s’étale sur plusieurs cellules, aucune au-delà de 45 000 caractères, et se relit entier',
    cellules.length >= 2 && cellules.every(v => String(v).length <= 45000) && j.length === 1 && Object.keys(j[0].plans).length === 3000,
    cellules.length + ' cellules : ' + cellules.map(v => String(v).length).join(' + '));
  h.regler('2026-11-02T17:00:00+01:00');
  /* Réimporté le même jour avec presque tout revenu : la queue des cellules est vidée. */
  const depart = carteBrute(ctx, c, 'THS', '2026-S44');
  ths.valeurs.slice(3).forEach((l, i) => { if (l[I_REF] && i >= 2) l[I_ELEC] = depart[l[I_REF]][0]; });
  importer(ctx, 'THS');
  const j2 = ctx.getJours(c, 'THS');
  verifier('réimporté le même jour, presque tout revenu : une seule ligne, deux plans, les cellules d’avant vidées',
    fj.valeurs.length === 2 && j2.length === 1 && Object.keys(j2[0].plans).length === 2 && fj.valeurs[1].slice(7).every(v => v === ''),
    JSON.stringify([fj.valeurs.length, j2[0] && Object.keys(j2[0].plans).length]));
}

// =================================================================
section('Le poids du paquet : 700 plans, 8 semaines de jours');
{
  const { c, ctx, h } = monde({ hdk: 700, ths: 20 });
  const hdk = c.getSheetByName('HDK');
  const r = refs(hdk);
  let graine = 33;
  const alea = () => { graine = (graine * 1103515245 + 12345) % 2147483648; return graine / 2147483648; };
  const VALEURS = ['TO_TREAT', 'FWD_TO_SEIZE', 'PWD_IN_PROGRESS', 'PWD_TO_CONTROL', 'TO_CONFIRM', 'VALIDATED'];
  /* Huit semaines à partir du lundi 7 septembre : le robot chaque jour ouvré, une douzaine de plans par jour. */
  h.regler('2026-09-04T17:05:00+02:00'); vendredi(ctx);
  const lundi0 = new Date('2026-09-07T14:05:00+02:00').getTime();
  for (let s = 0; s < 8; s++) {
    for (let d = 0; d < 5; d++) {
      h.regler(new Date(lundi0 + (s * 7 + d) * 86400000).toISOString());
      const n = 6 + Math.floor(alea() * 12);
      for (let k = 0; k < n; k++) poser(hdk, r[Math.floor(alea() * r.length)], VALEURS[Math.floor(alea() * VALEURS.length)]);
      importer(ctx, 'HDK');
    }
  }
  const paquet = ctx.getDonneesPourClient('HDK');
  const sans = JSON.parse(JSON.stringify(paquet)); delete sans.jours;
  const avec = JSON.stringify(ctx.compacterPaquet(paquet)), avant = JSON.stringify(ctx.compacterPaquet(sans));
  const gz = t => zlib.gzipSync(Buffer.from(t, 'utf8')).length;
  const ko = n => (n / 1024).toFixed(1) + ' Ko';
  const hausse = (gz(avec) - gz(avant)) / gz(avant);
  console.log('    paquet compact : ' + ko(avant.length) + ' → ' + ko(avec.length) + ' en clair ; ' + ko(gz(avant)) + ' → ' + ko(gz(avec)) +
    ' compressé (+' + (100 * hausse).toFixed(1) + ' %), ' + paquet.jours.length + ' jours, ' + paquet.releves.length + ' relevés');
  verifier('8 semaines de jours (40 jours) : le paquet compressé grossit de moins de 8 % — la première ouverture ne ralentit pas',
    paquet.jours.length === 40 && paquet.releves.length === 9 && hausse < 0.08, (100 * hausse).toFixed(1) + ' %');
}

console.log('\n═══════════════════════════════════════');
console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
process.exit(echecs.length ? 1 : 0);
