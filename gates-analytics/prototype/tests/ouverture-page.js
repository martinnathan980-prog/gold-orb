/* L'ouverture de la page, en deux temps (débrief 23 : « le site est très
   très long à charger ») — Playwright, navigateur réel.
   La page lit désormais son paquet compressé (une enveloppe gzip + base64),
   peint la synthèse d'abord et le reste juste après. Ces tests vérifient
   qu'elle n'y perd rien : une fois prête, chaque section dit exactement ce
   que dit le rendu d'un seul bloc d'avant (window.SUIVI_FWD_DIFFERER =
   false), sur la démonstration, sur 640 plans servis par le vrai Code.gs et
   sur un an d'archives (52 relevés) ; qu'un geste pendant l'ouverture ne
   laisse jamais une page à moitié dessinée ; que l'enveloppe se lit sous
   toutes ses formes, et que la page le dit quand elle ne peut pas ; que le
   pied dit la durée de l'ouverture et que l'ouverture comptée l'emporte ;
   que changer de contrat demande le paquet dès qu'on ouvre le sélecteur ;
   que les tris et les nombres sont ceux d'avant.
   Après la construction (Index, Javascript, Styles et apercu.html), comme
   la batterie :
       node tests/split-prototype.js && node prototype/tests/build-apercu.js
       node prototype/tests/ouverture-page.js */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const zlib = require('zlib');
const racine = path.join(__dirname, '..', '..');
const { construire } = require(path.join(racine, 'tests', 'build-addon.js'));

let reussis = 0;
const echecs = [];
const erreursJS = [];
let sectionCourante = '';
function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail ? ' — ' + String(detail).slice(0, 1500) : ''));
  }
}
function section(titre) { sectionCourante = titre; console.log('\n— ' + titre + ' —'); }

/* ------------------------------------------------------------------ */
/*  Les paquets et les pages                                           */
/* ------------------------------------------------------------------ */
function b64web(octets) { return octets.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
function deB64web(s) { return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64'); }
/* Le paquet compacté, quelle que soit la forme que le serveur donne : son
   JSON, l'objet, ou déjà l'enveloppe de la livraison B. */
function paquetCompact(x) {
  let p = typeof x === 'string' ? JSON.parse(x) : x;
  if (p && p.format === 2 && typeof p.gz === 'string') p = JSON.parse(zlib.gunzipSync(deB64web(p.gz)).toString('utf8'));
  return JSON.parse(JSON.stringify(p));
}
/* `raison` : pourquoi le classeur a relu (Code.gs, raisonDuManque_), pour un cache manqué. */
function mesuresServeur(cache, raison) {
  const fin = Date.now() - 120;
  const s = { debut: fin - 240, fin: fin, cache: cache || 'trouvé', etapes: { version: 90, cache: 40, page: 110 }, octets: 0 };
  if (raison !== undefined) s.raison = raison;
  return { serveur: s };
}
/* L'enveloppe v2, comme le serveur la pose : gzip, base64 « web », sans « = ». */
function enveloppe(paquet, opts) {
  const o = opts || {};
  const gz = o.gz || b64web(zlib.gzipSync(Buffer.from(JSON.stringify(paquet), 'utf8')));
  return { format: 2, edition: paquet.edition, contrat: paquet.contrat, cle: o.cle || 'cle-essai', gz: gz,
           mesures: o.mesures === undefined ? mesuresServeur() : o.mesures };
}
/* Un objet écrit dans un <script> : rien ne doit pouvoir le fermer. */
function litteral(objet) {
  return JSON.stringify(objet).replace(/</g, '\\u003c').replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
}
const fichiers = [];
const DEBUT_JS = "<script>\n(function () {\n  'use strict';";
function ecrirePage(nom, base, donnees, avantJs) {
  let h = base.replace(/window\.SUIVI_FWD_DONNEES = [\s\S]*?;\n/, () => 'window.SUIVI_FWD_DONNEES = ' + donnees + ';\n');
  if (avantJs) {
    if (h.split(DEBUT_JS).length !== 2) throw new Error('début du Javascript introuvable');
    h = h.replace(DEBUT_JS, () => avantJs + '\n' + DEBUT_JS);
  }
  const f = path.join(racine, 'sonde-tmp-ouverture-' + nom + '.html');
  fs.writeFileSync(f, h);
  fichiers.push(f);
  return 'file://' + f;
}
/* Ce que la page passe à l'ouverture comptée, relevé avant le pont d'Index. */
const NOTER = '<script>(function () { var api = window.SUIVI_FWD_API; if (!api || !api.noterConsultation) return;' +
  ' var o = api.noterConsultation; api.noterConsultation = function (m) {' +
  ' (window.__notes = window.__notes || []).push({ m: m, t: performance.now() }); return o.apply(this, arguments); }; })();</script>';
/* Un an d'archives : cinquante-deux relevés, une semaine d'écart, qui
   avancent, reculent, voient arriver et partir des plans. */
function etalerSurUnAn(contexte, classeur, id, n, bloques) {
  const histo = contexte.getFeuilleHistorique(classeur, id, false);
  const base = histo.valeurs[histo.valeurs.length - 1].slice();
  const carte = JSON.parse(base.slice(8).join('') || '{}');
  const refs = Object.keys(carte);
  const max = vm.runInContext('MAX_CARACTERES_CELLULE', contexte);
  const ecrire = (v, def) => Array.isArray(v) ? [def, v[1]] : def;
  histo.valeurs.length = 1;
  for (let k = 0; k < n; k++) {
    const d = new Date(Date.now() - (n - 1 - k) * 7 * 86400000);
    const plans = JSON.parse(JSON.stringify(carte));
    const part = 0.3 + 0.7 * k / (n - 1);
    refs.forEach((ref, r) => {
      if (((r * 37 + k * 11) % 100) / 100 > part) plans[ref] = ecrire(plans[ref], 'À faire');
      else if (k < n - 1 && (r * 13 + k) % 23 === 0) plans[ref] = ecrire(plans[ref], '50%');
    });
    if (k < 12) refs.slice(0, 5).forEach(ref => { delete plans[ref]; });
    /* Des plans en cours qui ne bougent plus depuis dix semaines : à l'arrêt. */
    if (k >= n - 10) bloques.forEach(ref => { if (plans[ref] !== undefined) plans[ref] = ecrire(plans[ref], '50%'); });
    const l = base.slice(0, 8);
    l[0] = contexte.numeroSemaineISO(d);
    l[1] = d;
    contexte.decouper(JSON.stringify(plans), max).forEach(t => l.push(t));
    histo.valeurs.push(l);
  }
}
/* La page telle que construire() l'assemble, avec le paquet du moment. */
function assembler(contexte, nom) {
  let index = fs.readFileSync(path.join(racine, 'Index.html'), 'utf8');
  index = index.replace(/<\?!=\s*include\('(\w+)'\);?\s*\?>/g, (_, n) => fs.readFileSync(path.join(racine, n + '.html'), 'utf8'));
  index = index.replace(/<\?!=\s*donneesJSONPourPage\(\)\s*\?>/, () => contexte.donneesJSONPourPage());
  if (fs.existsSync(path.join(racine, 'prototype', 'fonts', 'local.css'))) {
    index = index.replace(/<link rel="stylesheet"[^>]*href="https:\/\/fonts\.googleapis\.com[^>]*>/, '<link rel="stylesheet" href="prototype/fonts/local.css">');
  }
  const f = path.join(racine, 'sonde-tmp-ouverture-' + nom + '.html');
  fs.writeFileSync(f, index);
  fichiers.push(f);
  return index;
}

/* ------------------------------------------------------------------ */
/*  Le navigateur                                                      */
/* ------------------------------------------------------------------ */
/* L'état de l'ouverture, relevé à chaque changement ; « à la synthèse », un
   geste posé par le test au moment même où la synthèse est prête. */
function veilleOuverture() {
  window.__etats = [];
  /* Plusieurs changements dans une même tâche (la page d'un bloc) arrivent
     ensemble : la valeur de chacun est l'ancienne du suivant. */
  new MutationObserver(function (changements) {
    const actuel = document.documentElement && document.documentElement.getAttribute('data-suivi-fwd');
    changements.forEach(function (c, i) {
      const e = i + 1 < changements.length ? changements[i + 1].oldValue : actuel;
      if (window.__etats[window.__etats.length - 1] !== e) window.__etats.push(e);
    });
    if (actuel === 'synthese' && window.__aLaSynthese) { const f = window.__aLaSynthese; window.__aLaSynthese = null; f(); }
  }).observe(document, { attributes: true, subtree: true, attributeFilter: ['data-suivi-fwd'], attributeOldValue: true });
}
/* Ce que la page montre et a déduit : la méthode de d23/page/verifier-variantes.js,
   et le texte de chaque section. */
function lireEtat() {
  const t = id => { const e = document.getElementById(id); return e ? e.innerText.replace(/\s+/g, ' ').trim() : null; };
  const h = id => { const e = document.getElementById(id); return e ? e.innerHTML : null; };
  const rap = window.__rapprochement();
  return {
    journal: JSON.stringify(window.__journal().map(s => [s.i, s.evenements.length,
      s.evenements.map(e => e.type + ':' + e.ref + ':' + (e.cAvant || '') + '>' + (e.cApres || '')).sort().join(',')])),
    arret: window.__plansALArret().map(x => x.ref + '@' + x.depuis + '/' + x.semaines + (x.auMoins ? '+' : '')).join(','),
    comparatif: JSON.stringify(window.__comparatif()),
    rapp: rap ? [rap.accord.length, rap.emission.length, rap.avance.length, rap.manque.length, rap.attente.length, rap.seul.length].join(',') : null,
    serie: JSON.stringify(window.__serieAffichee().pts),
    phrase: document.getElementById('phrase').innerText, note: document.getElementById('note-graphe').textContent,
    etatsTexte: document.getElementById('etats').innerText,
    synthese: t('section-synthese'), tendance: t('section-tendance'), journalTexte: t('section-journal'),
    repartition: t('section-repartition'), plans: t('section-plans'), comparaison: t('rapprochement'),
    filtres: t('filtres-actifs'), bandeau: t('bandeau-mode'),
    /* Les décalages des en-têtes figés se posent quand le tableau paraît à
       l'écran : selon ce que la page a montré avant, ils y sont déjà ou pas
       encore — même valeur dans les deux cas. */
    corps: h('corps-tableau'), tete: h('tete-tableau').replace(/ style="[^"]*"/g, ''), seconde: h('corps-seconde'),
    zoneJournal: h('zone-journal'), zoneCritique: h('zone-critique'), barre: h('barre'), etats: h('etats'),
    cellules: document.querySelectorAll('#corps-tableau td').length, see: document.querySelectorAll('#corps-seconde td').length,
    /* Débrief 27, lot G : le pied a deux colonnes, les temps de l'ouverture
       repliés dans « Infos techniques » : on compare ses morceaux nommés. */
    pied: [...document.querySelectorAll('.pied [id]:not(#mesure-ouverture):not(#pied-technique)')].map(e => e.hidden ? '' : e.textContent).join('|'),
    sommaire: [...document.querySelectorAll('#sommaire-liste li')].map(li => li.hidden ? '-' : li.textContent.trim()).join('|')
  };
}
function ecarts(a, b) {
  return Object.keys(a).filter(k => a[k] !== b[k]).map(k => k + ' : « ' + String(a[k]).slice(0, 160) + ' » ≠ « ' + String(b[k]).slice(0, 160) + ' »');
}
/* Une erreur d'essai glissée dans la page : `motif` doit y être une fois. */
function injecter(html, motif, ajout) {
  if (html.split(motif).length !== 2) throw new Error('motif d’injection introuvable : ' + motif);
  return html.replace(motif, () => motif + ajout);
}
/* Ce que montre la première image après la synthèse (débrief 23, revue) :
   « À surveiller », où commence la courbe, le sommaire. Relevé à l'image qui
   suit l'état « synthese », comme l'écran la montre. */
function photoDeLaSynthese() {
  const photo = () => {
    const a = document.getElementById('a-surveiller'), t = document.getElementById('section-tendance');
    return { surveiller: a.hidden ? '(caché)' : a.innerText.replace(/\s+/g, ' ').trim(), haut: Math.round(t.getBoundingClientRect().top + window.scrollY),
             sommaire: [...document.querySelectorAll('#sommaire-liste li')].map(li => li.hidden ? '-' : li.textContent.trim()).join('|'),
             comparaison: !document.getElementById('rapprochement').hidden };
  };
  window.__photo = photo;
  window.__aLaSynthese = () => { requestAnimationFrame(() => setTimeout(() => { window.__photoSynthese = photo(); }, 0)); };
}

(async () => {
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  function brancher(pg, etiquette) {
    /* Les pannes d'essai (section « Une erreur pendant l'ouverture ») sont voulues. */
    pg.on('pageerror', e => { if (!/panne d’essai/.test(e.message)) erreursJS.push(etiquette + ' : ' + e.message); });
    pg.on('console', m => {
      if (m.type() === 'error' && !/ERR_FILE|net::|Contrat non chargé/.test(m.text())) erreursJS.push(etiquette + ' : ' + m.text());
    });
  }
  /* bloc : la page d'un bloc, comme avant (et comme la batterie) ; sinon en
     deux temps, comme au bureau. */
  async function ouvrir(url, opts) {
    const o = opts || {};
    const ctx = await nav.newContext(Object.assign({ viewport: { width: 1280, height: 950 } }, o.contexte || {}));
    await ctx.addInitScript(veilleOuverture);
    if (o.bloc) await ctx.addInitScript(() => { window.SUIVI_FWD_DIFFERER = false; });
    if (o.init) await ctx.addInitScript(o.init, o.arg);
    const pg = await ctx.newPage();
    brancher(pg, o.etiquette || 'page');
    if (o.avant) await o.avant(pg);
    await pg.goto(url + (o.suffixe || ''));
    return pg;
  }
  async function attendre(pg, etats) {
    const voulus = etats || ['pret', 'panne'];
    await pg.waitForFunction(v => v.indexOf(document.documentElement.getAttribute('data-suivi-fwd')) !== -1, voulus, { timeout: 60000 })
      .catch(() => {});
    return pg.evaluate(() => document.documentElement.getAttribute('data-suivi-fwd'));
  }
  /* Prête, puis tout ce que l'ouverture gardait pour la fin : c'est alors le
     rendu d'un bloc, à comparer. */
  async function etatFinal(pg) {
    await attendre(pg);
    await pg.evaluate(() => { if (window.__finirRendu) window.__finirRendu(); });
    await pg.waitForTimeout(120);
    return pg.evaluate(lireEtat);
  }
  async function fermer(pg) { await pg.context().close(); }

  /* Les pages : la démonstration, 640 plans sur la vraie structure d'export,
     un an d'archives, deux contrats. */
  const g640 = construire({ lignes: 640, gates: true, sortie: 'sonde-tmp-ouverture-g640-base.html' });
  fichiers.push(path.join(racine, 'sonde-tmp-ouverture-g640-base.html'));
  const base640 = fs.readFileSync(path.join(racine, 'sonde-tmp-ouverture-g640-base.html'), 'utf8');
  const compact640 = paquetCompact(g640.contexte.donneesJSONPourPage());
  const complet640 = JSON.parse(JSON.stringify(g640.contexte.getDonneesPourClient()));
  complet640.genereLe = compact640.genereLe;
  const urlJson640 = ecrirePage('g640-json', base640, litteral(compact640));
  const enveloppe640 = enveloppe(compact640);
  const urlEnv640 = ecrirePage('g640-env', base640, litteral(enveloppe640), NOTER);
  const urlDemo = 'file://' + path.join(racine, 'prototype', 'apercu.html');

  // =================================================================
  section('Deux temps sur 640 plans : une fois prête, la page d’un bloc, mot pour mot');
  const pRef = await ouvrir(urlJson640, { bloc: true, etiquette: 'g640 d’un bloc' });
  const ref640 = await etatFinal(pRef);
  const etatsRef = await pRef.evaluate(() => window.__etats);
  await fermer(pRef);
  verifier('d’un bloc (window.SUIVI_FWD_DIFFERER = false) : « synthese » puis « pret », la page entière, 60 lignes au tableau',
    etatsRef.join() === 'chargement,synthese,pret' && ref640.cellules === 60 * 137 + 1 && /sur 640 plans/.test(ref640.synthese),
    JSON.stringify([etatsRef, ref640.cellules, ref640.synthese.slice(0, 80)]));

  const pEnv = await ouvrir(urlEnv640, {
    etiquette: 'g640 en deux temps',
    init: () => {
      window.__aLaSynthese = () => {
        const z = document.getElementById('zone-journal');
        window.__vuALaSynthese = {
          phrase: document.getElementById('phrase').innerText, etats: document.getElementById('etats').innerText,
          barre: document.getElementById('barre').innerHTML, note: document.getElementById('note-graphe').textContent,
          lignes: document.querySelectorAll('#corps-tableau tr').length, journal: z.children.length,
          critique: document.getElementById('zone-critique').children.length, graphe: !!document.querySelector('#zone-graphe svg')
        };
      };
    }
  });
  const etatALaPret = await attendre(pEnv);
  const aPret = await pEnv.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
    suite: (document.querySelector('#corps-tableau tr.ligne-suite') || {}).textContent || '', etats: window.__etats.slice(), vu: window.__vuALaSynthese }));
  await pEnv.waitForTimeout(900);
  const apresRepos = await pEnv.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
    suite: (document.querySelector('#corps-tableau tr.ligne-suite') || {}).textContent || '', ouverture: window.__ouverture() }));
  const env640 = await etatFinal(pEnv);
  const ecartsEnv = ecarts(env640, ref640);
  verifier('l’enveloppe se lit, l’ouverture passe par « chargement », « synthese », « pret »',
    etatALaPret === 'pret' && aPret.etats.join() === 'chargement,synthese,pret' && apresRepos.ouverture.enveloppe && apresRepos.ouverture.enveloppe.cle === 'cle-essai',
    JSON.stringify([etatALaPret, aPret.etats, apresRepos.ouverture.enveloppe]));
  verifier('à la synthèse, ses chiffres sont déjà ceux de la page entière : la phrase, les tuiles, la barre, la note de la courbe',
    !!aPret.vu && aPret.vu.graphe && aPret.vu.phrase === ref640.phrase && aPret.vu.etats === ref640.etatsTexte &&
    aPret.vu.barre === ref640.barre && aPret.vu.note === ref640.note,
    JSON.stringify(aPret.vu && [aPret.vu.phrase, ref640.phrase, aPret.vu.etats === ref640.etatsTexte, aPret.vu.barre === ref640.barre, aPret.vu.note, ref640.note]));
  verifier('à la synthèse, le tableau des plans, le journal et le bloc par groupe ne sont pas encore dessinés',
    !!aPret.vu && aPret.vu.lignes === 0 && aPret.vu.journal === 0 && aPret.vu.critique === 0, JSON.stringify(aPret.vu));
  verifier('prête : vingt lignes au tableau, et la ligne « N lignes de plus » dit les 620 autres',
    aPret.lignes === 20 && /620 lignes de plus/.test(aPret.suite.replace(/[\s\u202f\u00a0]+/g, ' ')), JSON.stringify(aPret));
  verifier('puis, la page au repos, la première tranche d’avant : 60 lignes, « 580 lignes de plus »',
    apresRepos.lignes === 60 && /580 lignes de plus/.test(apresRepos.suite.replace(/[\s\u202f\u00a0]+/g, ' ')) && !apresRepos.ouverture.enCours, JSON.stringify(apresRepos));
  verifier('prête et au repos, chaque section dit mot pour mot ce que dit la page d’un bloc — journal, à l’arrêt, comparatif, courbe, groupes, tableau',
    ecartsEnv.length === 0, ecartsEnv.join(' ; '));
  await fermer(pEnv);

  // =================================================================
  section('Un geste pendant l’ouverture : elle se finit d’abord, jamais à moitié');
  /* La première tuile cliquée au moment où la synthèse est prête, le reste
     encore à dessiner ; puis la même tuile, sur la page d’un bloc. */
  const cliquerTuile = () => {
    window.__aLaSynthese = () => {
      const b = document.querySelectorAll('#etats .etat-btn')[1] || document.querySelector('#etats .etat-btn');
      window.__avantClic = { journal: document.getElementById('zone-journal').children.length, lignes: document.querySelectorAll('#corps-tableau tr').length };
      b.click();
      window.__apresClic = { etat: document.documentElement.getAttribute('data-suivi-fwd'), journal: document.getElementById('zone-journal').children.length,
        lignes: document.querySelectorAll('#corps-tableau tr').length, ouverture: window.__ouverture().enCours };
    };
  };
  for (const [nom, url] of [['640 plans', urlEnv640], ['démonstration', urlDemo]]) {
    const pG = await ouvrir(url, { etiquette: 'geste ' + nom, init: cliquerTuile });
    const finG = await etatFinal(pG);
    const clic = await pG.evaluate(() => ({ avant: window.__avantClic, apres: window.__apresClic }));
    await fermer(pG);
    const pB = await ouvrir(url, { bloc: true, etiquette: 'geste ' + nom + ' d’un bloc' });
    await attendre(pB);
    await pB.evaluate(() => { const b = document.querySelectorAll('#etats .etat-btn')[1] || document.querySelector('#etats .etat-btn'); b.click(); });
    const finB = await etatFinal(pB);
    await fermer(pB);
    verifier(nom + ' : une tuile cliquée pendant l’ouverture — le reste n’était pas dessiné, il l’est dès le clic, d’un coup, et la page est prête',
      !!clic.avant && clic.avant.journal === 0 && clic.avant.lignes === 0 && clic.apres.journal > 0 && clic.apres.lignes > 0 &&
      clic.apres.etat === 'pret' && !clic.apres.ouverture, JSON.stringify(clic));
    const e = ecarts(finG, finB);
    verifier(nom + ' : la page qui en résulte est celle de la même tuile cliquée sur la page d’un bloc', e.length === 0, e.join(' ; '));
  }

  /* Le sommaire mène au tableau des plans : il se dessine, et la page y va. */
  const pS = await ouvrir(urlEnv640, {
    etiquette: 'sommaire', contexte: { reducedMotion: 'reduce' },
    init: () => {
      window.__aLaSynthese = () => {
        document.querySelector('#sommaire-liste a[data-chapitre="section-plans"]').click();
        const s = document.getElementById('section-plans').getBoundingClientRect();
        window.__sommaire = { lignes: document.querySelectorAll('#corps-tableau tr').length, haut: Math.round(s.top), vue: window.innerHeight, y: window.scrollY };
      };
    }
  });
  await attendre(pS);
  const vuS = await pS.evaluate(() => window.__sommaire);
  await fermer(pS);
  verifier('le lien « Plans » du sommaire pendant l’ouverture : le tableau se dessine, et la page descend jusqu’à lui',
    !!vuS && vuS.lignes > 20 && vuS.y > 0 && vuS.haut >= 0 && vuS.haut < vuS.vue / 2, JSON.stringify(vuS));

  /* L'impression demande la page entière. */
  const pI = await ouvrir(urlDemo, {
    etiquette: 'impression',
    init: () => {
      window.__aLaSynthese = () => {
        window.dispatchEvent(new Event('beforeprint'));
        window.__impression = { lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length, see: document.querySelectorAll('#corps-seconde tr').length,
          journal: document.getElementById('zone-journal').children.length, critique: document.getElementById('zone-critique').children.length,
          comparaison: !document.getElementById('rapprochement').hidden, ouverture: window.__ouverture().enCours };
      };
    }
  });
  await attendre(pI);
  const vuI = await pI.evaluate(() => window.__impression);
  await fermer(pI);
  /* Débrief 27, lot G : la page imprimée porte le tableau entier — toutes
     ses lignes, en vue essentielle —, plus seulement sa première tranche. */
  verifier('avant l’impression, tout se dessine : tableau entier (toutes ses lignes), seconde base, journal, groupes, comparaison',
    !!vuI && vuI.lignes === 640 && vuI.see > 0 && vuI.journal > 0 && vuI.critique > 0 && vuI.comparaison && !vuI.ouverture, JSON.stringify(vuI));

  // =================================================================
  section('La démonstration, en deux temps et d’un bloc');
  const pDb = await ouvrir(urlDemo, { bloc: true, etiquette: 'démo d’un bloc' });
  const refDemo = await etatFinal(pDb);
  await fermer(pDb);
  const pDd = await ouvrir(urlDemo, { etiquette: 'démo en deux temps', init: photoDeLaSynthese });
  const etatDemo = await etatFinal(pDd);
  const piedDemo = await pDd.evaluate(() => ({ cache: document.getElementById('mesure-ouverture').hidden, attente: document.body.getAttribute('data-attente') }));
  const photosDemo = await pDd.evaluate(() => ({ synthese: window.__photoSynthese, fin: window.__photo() }));
  await fermer(pDd);
  const eDemo = ecarts(etatDemo, refDemo);
  verifier('démonstration (seconde base comprise) : chaque section dit mot pour mot ce que dit la page d’un bloc', eDemo.length === 0, eDemo.join(' ; '));
  verifier('démonstration : dès la première image de la synthèse, le sommaire est celui de la page finie — « Comparaison » comprise',
    !!photosDemo.synthese && photosDemo.synthese.comparaison && photosDemo.synthese.sommaire === photosDemo.fin.sommaire &&
    photosDemo.synthese.sommaire === refDemo.sommaire, JSON.stringify(photosDemo));
  verifier('démonstration : pas de ligne de durée au pied (aucun classeur derrière la page)', piedDemo.cache === true, JSON.stringify(piedDemo));

  // =================================================================
  section('L’enveloppe, sous toutes ses formes');
  const caracteres = 'Câble « éàç—€ » \u2028ligne\u2029 </script><b>gras</b> & fin';
  const special = JSON.parse(JSON.stringify(compact640));
  const iLib = special.plansTab.cles.indexOf('libelle');
  special.plansTab.lignes[0][iLib] = caracteres;
  const urlSpecJson = ecrirePage('special-json', base640, litteral(special));
  const urlSpecEnv = ecrirePage('special-env', base640, litteral(enveloppe(special)));
  const pSj = await ouvrir(urlSpecJson, { bloc: true, etiquette: 'caractères, JSON' });
  const sJ = await etatFinal(pSj);
  await fermer(pSj);
  const pSe = await ouvrir(urlSpecEnv, { etiquette: 'caractères, enveloppe' });
  const sE = await etatFinal(pSe);
  const celluleSpec = await pSe.evaluate(() => {
    const ref = window.__deballerPaquet(JSON.parse(JSON.stringify(window.SUIVI_FWD_DONNEES))).plans[0].libelle;
    return { ref: ref, texte: [...document.querySelectorAll('#corps-tableau td')].some(td => td.getAttribute('title') === ref || td.textContent === ref), gras: !!document.querySelector('#corps-tableau b') };
  });
  await fermer(pSe);
  const eSpec = ecarts(sE, sJ);
  verifier('accents, « — € », U+2028 et U+2029, une cellule « </script><b>… » : l’enveloppe les rend tels quels, la page est celle du JSON',
    celluleSpec.ref === caracteres && celluleSpec.texte && !celluleSpec.gras && eSpec.length === 0, JSON.stringify(celluleSpec) + ' ' + eSpec.join(' ; '));

  /* Le paquet écrit en JSON (une chaîne), et le paquet complet du Chargeur. */
  for (const [nom, donnees] of [['le paquet en texte JSON', JSON.stringify(JSON.stringify(compact640)).replace(/</g, '\\u003c')],
                                ['le paquet complet (Chargeur)', litteral(complet640)]]) {
    const u = ecrirePage(nom === 'le paquet en texte JSON' ? 'chaine' : 'complet', base640, donnees);
    const pF = await ouvrir(u, { etiquette: nom });
    const eF = ecarts(await etatFinal(pF), ref640);
    await fermer(pF);
    verifier(nom + ' : la page est celle du paquet compacté', eF.length === 0, eF.join(' ; '));
  }

  /* Sans DecompressionStream : la page redemande le paquet en JSON au classeur. */
  const sansDecompression = () => { try { delete window.DecompressionStream; } catch (e) { /* … */ } window.DecompressionStream = undefined; };
  const serveurJson = async pg => {
    await pg.exposeFunction('__serveurJson', () => JSON.stringify(compact640));
    await pg.addInitScript(() => {
      window.__appels = [];
      const chaine = (ok, ko) => ({
        withSuccessHandler: cb => chaine(cb, ko), withFailureHandler: cb => chaine(ok, cb),
        getDonneesCompactesJson: id => { window.__appels.push('json:' + id); window.__serveurJson().then(j => ok && ok(j), e => ko && ko(e)); },
        getDonneesCompactes: id => { window.__appels.push('compactes:' + id); },
        noterConsultation: () => { window.__appels.push('noter'); }
      });
      window.google = { script: { run: chaine(null, null) } };
    });
  };
  const pSec = await ouvrir(urlEnv640, { etiquette: 'secours JSON', init: sansDecompression, avant: serveurJson });
  const etatSec = await etatFinal(pSec);
  const infoSec = await pSec.evaluate(() => ({ appels: window.__appels.slice(), env: window.__ouverture().enveloppe }));
  await fermer(pSec);
  const eSec = ecarts(etatSec, ref640);
  verifier('sans DecompressionStream : le paquet redemandé en JSON (getDonneesCompactesJson) au classeur, une fois, et la même page',
    infoSec.appels.filter(a => /^json:/.test(a)).join() === 'json:' + compact640.contrat && infoSec.env && infoSec.env.secours && eSec.length === 0,
    JSON.stringify(infoSec) + ' ' + eSec.join(' ; '));

  /* Le pont d'Index propose chargerContratJson (livraison B) : la page passe
     par lui ; s'il rend null (le classeur n'a pas répondu), elle le dit. */
  const pontJson = rendNull => '<script>(function () { var api = window.SUIVI_FWD_API; if (!api) return;' +
    ' api.chargerContratJson = function (id, cb) { window.__appels.push("pont:" + id);' +
    (rendNull ? ' setTimeout(function () { cb(null); }, 20); };' : ' window.__serveurJson().then(cb, function () { cb(null); }); };') +
    ' })();</script>';
  const urlPont = ecrirePage('g640-pont', base640, litteral(enveloppe(compact640)), pontJson(false));
  const pPont = await ouvrir(urlPont, { etiquette: 'secours par le pont', init: sansDecompression, avant: serveurJson });
  const etatPont = await etatFinal(pPont);
  const infoPont = await pPont.evaluate(() => ({ appels: window.__appels.slice(), env: window.__ouverture().enveloppe }));
  await fermer(pPont);
  const ePont = ecarts(etatPont, ref640);
  verifier('le pont d’Index propose chargerContratJson : le paquet en clair passe par lui, une fois, et la page est la même',
    infoPont.appels.join() === 'pont:' + compact640.contrat && infoPont.env && infoPont.env.secours && ePont.length === 0,
    JSON.stringify(infoPont) + ' ' + ePont.join(' ; '));
  const urlPontNul = ecrirePage('g640-pont-nul', base640, litteral(enveloppe(compact640)), pontJson(true));
  const pPontNul = await ouvrir(urlPontNul, { etiquette: 'pont sans réponse', init: sansDecompression, avant: serveurJson });
  const etatPontNul = await attendre(pPontNul);
  const vuPontNul = await pPontNul.evaluate(() => ({ cadre: (document.getElementById('suivi-fwd-panne') || {}).innerText || '', phrase: document.getElementById('phrase').textContent }));
  await fermer(pPontNul);
  verifier('le pont rend null : « La page n’a pas pu s’afficher », l’état « panne », jamais une page à moitié chargée',
    etatPontNul === 'panne' && /La page n’a pas pu s’afficher/.test(vuPontNul.cadre) && vuPontNul.phrase === '—', JSON.stringify([etatPontNul, vuPontNul]));

  /* Une enveloppe abîmée : le décodage échoue, le secours prend le relais. */
  const abimee = enveloppe(compact640, { gz: b64web(Buffer.from('ceci n’est pas du gzip, mais il en a la longueur'.repeat(40))) });
  const urlAbimee = ecrirePage('abimee', base640, litteral(abimee));
  const pAb = await ouvrir(urlAbimee, { etiquette: 'enveloppe abîmée', avant: serveurJson });
  const eAb = ecarts(await etatFinal(pAb), ref640);
  const infoAb = await pAb.evaluate(() => window.__appels.slice());
  await fermer(pAb);
  verifier('une enveloppe abîmée : le décodage échoue, le paquet est redemandé en JSON, la page est la même', infoAb.indexOf('json:' + compact640.contrat) !== -1 && eAb.length === 0,
    JSON.stringify(infoAb) + ' ' + eAb.join(' ; '));

  /* Ni décodage ni classeur : la page le dit, en tête, au lieu d'un squelette. */
  const pPanne = await ouvrir(urlEnv640, { etiquette: 'sans secours', init: sansDecompression });
  const etatPanne = await attendre(pPanne);
  const vuPanne = await pPanne.evaluate(() => ({ cadre: (document.getElementById('suivi-fwd-panne') || {}).innerText || '', phrase: document.getElementById('phrase').textContent }));
  await fermer(pPanne);
  verifier('ni décodage ni classeur : « La page n’a pas pu s’afficher », l’état « panne », plus de « Chargement… »',
    etatPanne === 'panne' && /La page n’a pas pu s’afficher/.test(vuPanne.cadre) && vuPanne.phrase === '—', JSON.stringify([etatPanne, vuPanne]));

  // =================================================================
  section('Le pied dit la durée de l’ouverture');
  /* Débrief 27, lot G : les temps sont repliés dans « Infos techniques » —
     on la déplie pour les lire comme on les lit à l'écran. */
  const lirePied = pg => pg.evaluate(() => {
    const d = document.getElementById('pied-technique');
    if (d) d.open = true;
    const z = document.getElementById('mesure-ouverture');
    return { cache: z.hidden, texte: z.innerText, luLe: document.getElementById('lu-le').textContent };
  });
  const pPied = await ouvrir(urlEnv640, { etiquette: 'pied' });
  await attendre(pPied); await pPied.waitForTimeout(300);
  const pied1 = await lirePied(pPied);
  await fermer(pPied);
  const S = '[\\s\\u00a0]s';
  verifier('« Ouverture : 1,9 s — classeur 0,2 s (en cache) · transfert ≈ 0,6 s · affichage 1,1 s », sous « Chiffres lus dans le classeur le … »',
    !pied1.cache && new RegExp('^Ouverture : \\d+,\\d+' + S + ' — classeur 0,2\\d?' + S + ' \\(en cache\\) · transfert ≈ \\d+,\\d+' + S + ' · affichage \\d+,\\d+' + S + '$').test(pied1.texte) &&
    /^Chiffres lus dans le classeur le \S+ \d+ \S+ à \d{2}:\d{2} — recharger la page/.test(pied1.luLe), JSON.stringify(pied1));
  const urlManque = ecrirePage('manque', base640, litteral(enveloppe(compact640, { mesures: mesuresServeur('manqué', 'modifié') })));
  const pM = await ouvrir(urlManque, { etiquette: 'pied, cache manqué', suffixe: '?mesure=1' });
  await attendre(pM); await pM.waitForTimeout(300);
  const pied2 = await lirePied(pM);
  await fermer(pM);
  verifier('le classeur relu parce qu’il venait de changer : « (relu : il venait de changer) » ; avec ?mesure=1, le détail sur une seconde ligne',
    /classeur 0,2\d?[\s\u00a0]s \(relu : il venait de changer\)/.test(pied2.texte) &&
    /\nDétail : données \d+[\s\u00a0]Ko compressées, décodées en .* · synthèse peinte à .* · plus longue tâche .* · classeur : version 0,09[\s\u00a0]s, cache 0,04[\s\u00a0]s, page 0,1[\s\u00a0]s$/.test(pied2.texte),
    JSON.stringify(pied2));
  /* Débrief 23, revue : « il venait de changer » seulement quand c'est vrai. */
  for (const [raison, dit] of [['', 'relu : rien de prêt en cache'], ['expiré', 'relu : rien de prêt en cache'], [undefined, 'relu : rien de prêt en cache'],
                               ['livraison', 'relu : nouvelle livraison'], ['demandé', 'relu à la demande']]) {
    const pR = await ouvrir(ecrirePage('manque-' + (raison || String(raison)), base640, litteral(enveloppe(compact640, { mesures: mesuresServeur('manqué', raison) }))),
      { etiquette: 'pied, relu (' + raison + ')' });
    await attendre(pR); await pR.waitForTimeout(300);
    const piedR = await lirePied(pR);
    await fermer(pR);
    verifier('relu, raison « ' + raison + ' » : « (' + dit + ') », jamais « il venait de changer »',
      piedR.texte.indexOf('(' + dit + ')') !== -1 && !/venait de changer/.test(piedR.texte), JSON.stringify(piedR));
  }
  const pL = await ouvrir(urlJson640, { etiquette: 'pied, JSON d’avant' });
  await attendre(pL); await pL.waitForTimeout(300);
  const pied3 = await lirePied(pL);
  await fermer(pL);
  verifier('un paquet sans durées du serveur (JSON d’avant, Chargeur) : « Ouverture : affichage 0,4 s »',
    !pied3.cache && /^Ouverture : affichage \d+,\d+[\s\u00a0]s$/.test(pied3.texte), JSON.stringify(pied3));
  const hier = JSON.parse(JSON.stringify(compact640));
  hier.genereLe = new Date(Date.now() - 86400000 * 1.5).toISOString();
  const pH = await ouvrir(ecrirePage('hier', base640, litteral(enveloppe(hier))), { etiquette: 'pied, lu hier' });
  await attendre(pH);
  const pied4 = await lirePied(pH);
  await fermer(pH);
  verifier('des chiffres lus un autre jour (le classeur n’a pas changé depuis) : « …, classeur inchangé depuis — recharger la page… »',
    /à \d{2}:\d{2}, classeur inchangé depuis — recharger la page pour les chiffres du moment\.$/.test(pied4.luLe) && !/inchangé/.test(pied1.luLe), pied4.luLe);

  // =================================================================
  section('L’ouverture comptée part avec ses durées');
  const pN = await ouvrir(urlEnv640, { etiquette: 'consultation' });
  await attendre(pN);
  await pN.waitForTimeout(2300);
  const notes = await pN.evaluate(() => ({ notes: window.__notes || [], synthese: performance.getEntriesByName('suivi-fwd:synthese')[0].startTime,
    pret: performance.getEntriesByName('suivi-fwd:pret')[0].startTime }));
  await fermer(pN);
  const m = notes.notes[0] && notes.notes[0].m;
  const champs = ['quand', 'contrat', 'cache', 'raison', 'debut', 'serveur', 'transfert', 'synthese', 'tout', 'plans', 'releves', 'octets', 'largeur', 'cle'];
  verifier('une seule fois, une seconde et demie après la synthèse et jamais avant la fin : noterConsultation(mesures)',
    notes.notes.length === 1 && notes.notes[0].t - notes.synthese >= 1450 && notes.notes[0].t >= notes.pret, JSON.stringify(notes));
  verifier('les mesures : { quand, contrat, cache, raison, debut, serveur, transfert, synthese, tout, plans, releves, octets, largeur, cle } — sans nom ni adresse ; ' +
    '« debut », celui de l’ouverture au serveur (le classeur y reconnaît une ouverture déjà gardée)',
    !!m && champs.every(k => k in m) && Object.keys(m).length === champs.length && m.contrat === compact640.contrat && m.cache === 'trouvé' &&
    m.raison === '' && m.debut === enveloppe640.mesures.serveur.debut &&
    m.serveur === 240 && m.transfert >= 0 && m.synthese > 0 && m.tout >= m.synthese && m.plans === 640 && m.releves === 5 &&
    m.octets > 1000 && m.largeur === 1280 && m.cle === 'cle-essai' && typeof m.quand === 'number', JSON.stringify(m));

  // =================================================================
  section('Changer de contrat : la demande part dès qu’on ouvre le sélecteur');
  const deux = construire({ gates: true, contrats: ['HDK', 'THS'], lignes: 60, sortie: 'sonde-tmp-ouverture-deux.html' });
  fichiers.push(path.join(racine, 'sonde-tmp-ouverture-deux.html'));
  const baseDeux = fs.readFileSync(path.join(racine, 'sonde-tmp-ouverture-deux.html'), 'utf8');
  const compactDeux = paquetCompact(deux.contexte.donneesJSONPourPage());
  const urlDeux = ecrirePage('deux-env', baseDeux, litteral(enveloppe(compactDeux)));
  const serveurDeux = delai => async pg => {
    await pg.exposeFunction('__serveurContrat', async id => {
      await new Promise(r => setTimeout(r, delai));
      const p = paquetCompact(deux.contexte.getDonneesCompactes(id));
      return JSON.stringify(p && p.ok !== false ? enveloppe(p, { cle: 'contrat-' + id }) : p);
    });
    await pg.addInitScript(() => {
      window.__appels = [];
      const chaine = (ok, ko) => ({
        withSuccessHandler: cb => chaine(cb, ko), withFailureHandler: cb => chaine(ok, cb),
        getDonneesCompactes: id => { window.__appels.push(id); window.__serveurContrat(id).then(j => ok && ok(JSON.parse(j)), e => ko && ko(e)); },
        noterConsultation: () => {}
      });
      window.google = { script: { run: chaine(null, null) } };
    });
  };
  const pC = await ouvrir(urlDeux, { etiquette: 'contrats', avant: serveurDeux(800) });
  await attendre(pC);
  await pC.waitForTimeout(400);
  const appels0 = await pC.evaluate(() => window.__appels.slice());
  await pC.dispatchEvent('#select-contrat', 'mousedown');
  await pC.waitForTimeout(60);
  const appels1 = await pC.evaluate(() => window.__appels.slice());
  await pC.selectOption('#select-contrat', 'THS');
  await pC.waitForTimeout(250);
  const pendant = await pC.evaluate(() => ({ attente: document.body.getAttribute('data-attente'), etat: document.getElementById('etat-contrat').textContent,
    opacite: getComputedStyle(document.getElementById('section-synthese')).opacity, grise: document.getElementById('select-contrat').disabled,
    valeur: document.getElementById('select-contrat').value, barre: !document.getElementById('barre-chargement').hidden,
    masque: document.getElementById('etat-contrat').getBoundingClientRect().width <= 1 }));
  await pC.waitForFunction(() => document.getElementById('select-contrat').value === 'THS' && !document.body.hasAttribute('data-attente') &&
    /sur 30 plans/.test(document.getElementById('phrase').textContent), null, { timeout: 10000 }).catch(() => {});
  const apresC = await pC.evaluate(() => ({ appels: window.__appels.slice(), phrase: document.getElementById('phrase').textContent, attente: document.body.getAttribute('data-attente'),
    etat: document.getElementById('etat-contrat').textContent, valeur: document.getElementById('select-contrat').value }));
  verifier('à l’ouverture, rien n’est demandé au classeur', appels0.length === 0, JSON.stringify(appels0));
  verifier('le sélecteur ouvert (mousedown) : le paquet de THS est demandé tout de suite, avant le choix', appels1.join() === 'THS', JSON.stringify(appels1));
  /* Débrief 27 (lot H, A-F4, X-A4) : le menu n'est plus grisé pendant
     l'attente — il garde le contrat demandé et le focus clavier ; l'attente
     se voit au trait du haut de l'écran (et « Chargement… » reste dit aux
     lecteurs d'écran, sans s'écrire à côté du menu). */
  verifier('pendant l’attente : « Chargement… » (pour les lecteurs d’écran), le sélecteur à portée sur THS, le trait d’attente, la page d’avant estompée (jamais blanche)',
    pendant.attente === 'contrat' && pendant.etat === 'Chargement…' && !pendant.grise && pendant.valeur === 'THS' && pendant.barre && pendant.masque &&
    Number(pendant.opacite) < 1, JSON.stringify(pendant));
  verifier('THS choisi : la réponse déjà demandée sert (une seule demande), décodée, la page passe sur THS et retrouve sa clarté',
    apresC.appels.join() === 'THS' && /sur 30 plans/.test(apresC.phrase) && apresC.attente === null && apresC.etat === '' && apresC.valeur === 'THS', JSON.stringify(apresC));
  /* Une demande d'avance trop ancienne ne sert pas : la page redemande. */
  await pC.dispatchEvent('#select-contrat', 'mousedown');
  await pC.waitForTimeout(500);
  await pC.evaluate(() => { const vrai = Date.now; Date.now = () => vrai() + 60000; });
  await pC.selectOption('#select-contrat', 'HDK');
  await pC.waitForFunction(() => document.getElementById('select-contrat').value === 'HDK' && /sur 60 plans/.test(document.getElementById('phrase').textContent) &&
    !document.body.hasAttribute('data-attente'), null, { timeout: 10000 }).catch(() => {});
  const vieille = await pC.evaluate(() => ({ appels: window.__appels.slice(), phrase: document.getElementById('phrase').textContent }));
  verifier('une réponse demandée il y a plus d’une demi-minute ne sert pas : le paquet est redemandé (jamais de chiffres d’avant)',
    vieille.appels.join() === 'THS,HDK,HDK' && /sur 60 plans/.test(vieille.phrase), JSON.stringify(vieille));
  await pC.click('#voir-ensemble');
  await pC.waitForFunction(() => document.querySelectorAll('#ensemble tbody tr').length === 2 && !/chargement/.test(document.getElementById('ensemble').textContent), null, { timeout: 10000 }).catch(() => {});
  const ensemble = await pC.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr => tr.textContent.replace(/\s+/g, ' ').trim()));
  verifier('la vue d’ensemble décode les paquets reçus : HDK et THS, leurs chiffres', ensemble.length === 2 && ensemble.every(l => /\d+ \/ \d+/.test(l)) && !ensemble.some(l => /impossible/.test(l)),
    JSON.stringify(ensemble));
  await fermer(pC);

  // =================================================================
  section('Les tris et les nombres : ceux d’avant, exactement');
  const pT = await ouvrir(urlDemo, { bloc: true, etiquette: 'tris' });
  await attendre(pT);
  const tris = await pT.evaluate(() => {
    const src = window.__jeuDExemple('HDK');
    const mots = [];
    src.plans.forEach(p => { ['reference', 'ata', 'ecp', 'sequence', 'cc', 'libelle', 'domaine'].forEach(k => { if (p[k] !== undefined && p[k] !== null) mots.push(String(p[k])); }); });
    (src.rapprochement && src.rapprochement.lignes || []).forEach(l => Object.keys(l).forEach(k => mots.push(String(l[k] == null ? '' : l[k]))));
    ['Écp', 'ecp', 'ECP', 'e', 'é', 'É', 'A10', 'a9', 'a10', 'Œuvre', 'oeuvre', '', ' ', '10', '9', '-1', 'Z', 'z', 'ß', 'ss', 'Ä', 'ä', 'Aa', 'aA'].forEach(m => mots.push(m));
    const c = window.__comparateurs();
    const pareil = (f, g) => JSON.stringify(mots.slice().sort(f)) === JSON.stringify(mots.slice().sort(g));
    const r = {
      n: mots.length,
      num: pareil((a, b) => a.localeCompare(b, 'fr', { numeric: true }), c.num),
      ref: pareil((a, b) => a.localeCompare(b, 'fr', { numeric: true, sensitivity: 'base' }), c.ref),
      fr: pareil((a, b) => a.localeCompare(b, 'fr'), c.fr),
      local: pareil((a, b) => a.localeCompare(b), c.local)
    };
    /* Chaque paire, pas seulement l'ordre final. */
    let paires = 0, differentes = 0;
    for (let i = 0; i < mots.length; i += 7) for (let j = 0; j < mots.length; j += 11) {
      paires++;
      if (Math.sign(mots[i].localeCompare(mots[j], 'fr', { numeric: true })) !== Math.sign(c.num(mots[i], mots[j]))) differentes++;
      if (Math.sign(mots[i].localeCompare(mots[j], 'fr', { numeric: true, sensitivity: 'base' })) !== Math.sign(c.ref(mots[i], mots[j]))) differentes++;
    }
    r.paires = paires; r.differentes = differentes;
    return r;
  });
  const nombres = await pT.evaluate(() => {
    const essai = [0, -0, 1, 7, 12, 999, 1000, 12345, 1234567, -42, 0.5, 2.25, 1 / 3, 1e21, NaN, Infinity, -Infinity, 98.765432];
    for (let i = 0; i < 500; i++) essai.push(Math.round(Math.sin(i) * 1e6) / (i % 7 ? 1 : 1000));
    /* nb() de la page, lu dans ce qu'elle écrit : la tuile « Validés » et ses comptes. */
    return essai.every(x => new Intl.NumberFormat('fr-FR').format(x) === x.toLocaleString('fr-FR'));
  });
  await fermer(pT);
  verifier('Intl.Collator construit une fois donne exactement l’ordre de localeCompare, options comprises (' + tris.n + ' valeurs, ' + tris.paires + ' paires)',
    tris.num && tris.ref && tris.fr && tris.local && tris.differentes === 0, JSON.stringify(tris));
  verifier('Intl.NumberFormat("fr-FR") écrit chaque nombre exactement comme toLocaleString("fr-FR")', nombres === true);

  // =================================================================
  section('Un an d’archives (52 relevés) : la même page, en deux temps et d’un bloc');
  const an = construire({ lignes: 300, gates: true, sortie: 'sonde-tmp-ouverture-an-base.html' });
  fichiers.push(path.join(racine, 'sonde-tmp-ouverture-an-base.html'));
  const { colonne } = require(path.join(racine, 'tests', 'feuille-gates.js'));
  const iRef = colonne('Référence UD'), iAv = colonne('Avancement Définition Electrique', 'HDK AA 011');
  const bloques = [];
  an.classeur.getSheets()[0].valeurs.forEach((l, r) => {
    if (r >= 2 && l[iRef] && r % 9 === 0) { l[iAv] = '50%'; bloques.push(String(l[iRef])); }
  });
  etalerSurUnAn(an.contexte, an.classeur, an.contexte.listerContrats(an.classeur)[0].id, 52, bloques);
  const baseAn = assembler(an.contexte, 'an-assemble');
  const compactAn = paquetCompact(an.contexte.donneesJSONPourPage());
  const urlAnJson = ecrirePage('an-json', baseAn, litteral(compactAn));
  const urlAnEnv = ecrirePage('an-env', baseAn, litteral(enveloppe(compactAn)));
  const pAb1 = await ouvrir(urlAnJson, { bloc: true, etiquette: 'un an, d’un bloc' });
  const refAn = await etatFinal(pAb1);
  const nbReleves = await pAb1.evaluate(() => window.__indicateur().releves);
  await fermer(pAb1);
  const pAd = await ouvrir(urlAnEnv, { etiquette: 'un an, en deux temps', init: photoDeLaSynthese });
  const etatAn = await etatFinal(pAd);
  const photosAn = await pAd.evaluate(() => ({ synthese: window.__photoSynthese, fin: window.__photo() }));
  await fermer(pAd);
  verifier('un an d’archives : dès la première image de la synthèse, « À surveiller » y est, déjà entier, et la courbe ne bougera plus',
    !!photosAn.synthese && /^À surveiller : \d+ plans? en cours/.test(photosAn.synthese.surveiller) && photosAn.synthese.surveiller === photosAn.fin.surveiller &&
    photosAn.synthese.haut === photosAn.fin.haut && photosAn.synthese.sommaire === photosAn.fin.sommaire, JSON.stringify(photosAn));
  const eAn = ecarts(etatAn, refAn);
  verifier('52 relevés archivés lus', nbReleves >= 52, String(nbReleves));
  verifier('un an d’archives : journal, plans à l’arrêt, comparatif, courbe, groupes, tableau — mot pour mot ceux de la page d’un bloc',
    eAn.length === 0 && JSON.parse(refAn.journal).length >= 40 && refAn.arret.length > 0, eAn.join(' ; ') || JSON.stringify([JSON.parse(refAn.journal).length, refAn.arret.slice(0, 80)]));

  // =================================================================
  section('Une erreur pendant l’ouverture : le cadre de panne, et la page répond encore');
  {
    /* Une erreur dans la synthèse de HDK seulement (phase 1) : le cadre de
       panne paraît, et l'on peut encore passer sur THS, ouvrir la vue
       d'ensemble — comme quand la page se dessinait d'un bloc. */
    const htmlPanne = injecter(baseDeux, 'function rendreEcheanceTitre() {',
      " if (CONTRAT === 'HDK') throw new Error('panne d’essai dans la synthèse de HDK');");
    const urlPanne1 = ecrirePage('panne-synthese', htmlPanne, litteral(enveloppe(compactDeux)));
    for (const bloc of [false, true]) {
      const dit = bloc ? ' (d’un bloc)' : ' (en deux temps)';
      const pP = await ouvrir(urlPanne1, { etiquette: 'panne à la synthèse' + dit, bloc: bloc, avant: serveurDeux(50) });
      const etat = await attendre(pP, ['panne']);
      const cadre = await pP.evaluate(() => (document.getElementById('suivi-fwd-panne') || {}).innerText || '');
      await pP.selectOption('#select-contrat', 'THS');
      await pP.waitForFunction(() => /sur 30 plans/.test(document.getElementById('phrase').textContent), null, { timeout: 10000 }).catch(() => {});
      const ths = await pP.evaluate(() => ({ valeur: document.getElementById('select-contrat').value, phrase: document.getElementById('phrase').textContent,
        ouverture: window.__ouverture().enCours }));
      await pP.click('#voir-ensemble');
      await pP.waitForFunction(() => document.querySelectorAll('#ensemble tbody tr').length === 2, null, { timeout: 10000 }).catch(() => {});
      const ens = await pP.evaluate(() => ({ ouverte: !document.getElementById('ensemble').hidden, lignes: document.querySelectorAll('#ensemble tbody tr').length,
        aria: document.getElementById('voir-ensemble').getAttribute('aria-expanded') }));
      await fermer(pP);
      verifier('une erreur dans la synthèse de HDK' + dit + ' : « La page n’a pas pu s’afficher », puis THS se choisit et s’affiche, la vue d’ensemble s’ouvre',
        etat === 'panne' && /La page n’a pas pu s’afficher/.test(cadre) && ths.valeur === 'THS' && /sur 30 plans/.test(ths.phrase) && !ths.ouverture &&
        ens.ouverte && ens.lignes === 2 && ens.aria === 'true', JSON.stringify([etat, cadre.slice(0, 80), ths, ens]));
    }
    /* Une erreur dans ce que l'ouverture garde pour la fin (le tableau de la
       seconde base) : le cadre de panne, comme avant, et l'ouverture finie. */
    const htmlTard = injecter(fs.readFileSync(path.join(racine, 'prototype', 'apercu.html'), 'utf8'), 'function rendreSeconde() {',
      " throw new Error('panne d’essai dans le tableau de la seconde base');");
    const fTard = path.join(racine, 'prototype', 'sonde-tmp-ouverture-tardive.html');
    fs.writeFileSync(fTard, htmlTard);
    fichiers.push(fTard);
    const pT2 = await ouvrir('file://' + fTard, { etiquette: 'panne tardive' });
    await attendre(pT2, ['panne']);
    await pT2.waitForTimeout(800);
    const tard = await pT2.evaluate(() => ({ etat: document.documentElement.getAttribute('data-suivi-fwd'), cadre: (document.getElementById('suivi-fwd-panne') || {}).innerText || '',
      ouverture: window.__ouverture().enCours }));
    await fermer(pT2);
    verifier('une erreur dans le tableau de la seconde base, dessiné après « pret » : le cadre de panne paraît, l’ouverture n’est plus « en cours »',
      tard.etat === 'panne' && /La page n’a pas pu s’afficher/.test(tard.cadre) && tard.ouverture === false, JSON.stringify(tard));
  }

  // =================================================================
  section('Une page rechargée revient où on l’avait laissée');
  for (const bloc of [false, true]) {
    const dit = bloc ? ' (d’un bloc)' : ' (en deux temps)';
    const pR = await ouvrir(urlEnv640, { etiquette: 'rechargée' + dit, bloc: bloc });
    await attendre(pR);
    await pR.waitForTimeout(500);
    /* Tout en bas : le cas le plus dur — la dernière ligne du pied compte. */
    await pR.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await pR.waitForTimeout(400);
    const avant = await pR.evaluate(() => ({ y: Math.round(window.scrollY), hauteur: document.documentElement.scrollHeight }));
    await pR.reload();
    await attendre(pR);
    await pR.waitForTimeout(1500);
    const apres = await pR.evaluate(() => ({ y: Math.round(window.scrollY), hauteur: document.documentElement.scrollHeight,
      minHeight: document.documentElement.style.minHeight, nav: performance.getEntriesByType('navigation')[0].type }));
    await fermer(pR);
    verifier('descendue tout en bas puis rechargée (F5)' + dit + ' : la page revient au même endroit (' + avant.y + ' px), et reprend sa hauteur',
      avant.y > 1500 && apres.nav === 'reload' && Math.abs(apres.y - avant.y) <= 2 && apres.minHeight === '' && apres.hauteur === avant.hauteur, JSON.stringify([avant, apres]));
  }

  // =================================================================
  section('Erreurs JavaScript');
  verifier('aucune erreur JavaScript sur toutes ces pages', erreursJS.length === 0, erreursJS.slice(0, 5).join(' | '));

  await nav.close();
  fichiers.forEach(f => { try { fs.unlinkSync(f); } catch (e) { /* déjà parti */ } });
  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e.slice(0, 2000))); }
  process.exit(echecs.length ? 1 : 0);
})().catch(e => {
  console.error(e);
  fichiers.forEach(f => { try { fs.unlinkSync(f); } catch (er) { /* déjà parti */ } });
  process.exit(1);
});
