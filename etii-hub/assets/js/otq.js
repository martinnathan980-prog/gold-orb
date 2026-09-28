/* =========================================================================
   ETII Hub — Le suivi OTQ

   Les plans du service présentés chaque mois, et ce qu'il en est advenu,
   tels que les compte le « Command Center » du service : l'onglet « Data »
   de sa feuille, rempli par son propre script (menu « Airbus Sync ») à
   partir de deux sources, « Drawings Prod » et « Drawings TVE », pour
   toutes les lignes où figure ETII.

     Qualité des plans (OTQ)   Prod : ACCEPTED, MINOR REFUSED, REFUSED
     TVE                       TVE  : ACCEPTED, FALSE REFUSED, REFUSED

   Le site ne recompte rien : il lit ces nombres et en tire le taux
   d'acceptation du mois (acceptés ÷ présentés), son évolution, et les
   barres des mois, empilées par statut.

   D'où viennent les nombres, dans l'ordre :
     1. le serveur du site (Code.gs, OTQ_ID_FEUILLE) quand il est branché
        sur la feuille du Command Center — la vraie mesure ;
     2. un CSV publié (SOURCE.url), s'il est renseigné ;
     3. sinon, assets/data/otq-exemple.csv, annoncé « Données d'exemple ».

   Format du CSV (les titres de colonnes sont reconnus par leurs mots,
   emoji compris : l'onglet « Data » publié tel quel convient) :
     mois,prod_accepted,prod_minor_refused,prod_refused,tve_accepted,tve_false_refused,tve_refused
     2026-08,31,2,1,18,1,1
   Le mois s'écrit AAAA-MM, « AUG 26 », « août 2026 » ou « 08/2026 ».
   ========================================================================= */

import { el, monter, ressourceIntegree } from './ui.js';
import { ouvrirMagasin } from './magasin.js';

/* -------------------------------------------------------------------------
   1. LE POINT DE RACCORDEMENT
   ------------------------------------------------------------------------- */

/* Ce dépôt est public. Ne collez rien ici : sur Google, c'est Code.gs qui
   lit la feuille (OTQ_ID_FEUILLE) ; aucune adresse n'a à paraître dans le
   site. tests/audit.mjs refuse une URL de raccordement commitée. */
export const SOURCE = {
  /* URL d'un CSV publié (facultatif). Vide : le serveur du site, sinon
     l'exemple. */
  url: '',
  /* Fichier d'exemple embarqué. */
  exemple: 'assets/data/otq-exemple.csv'
};

/* Les deux mesures et leurs trois statuts, du meilleur au pire : l'ordre
   de la pile (de bas en haut), de la légende et du tableau. */
const INDICATEURS = {
  otq: {
    cle: 'otq', bouton: 'Qualité des plans (OTQ)', sigle: 'OTQ', titre: 'Qualité des plans',
    source: 'Drawings Prod', unite: 'plans',
    statuts: [
      { cle: 'acc', libelle: 'Acceptés', un: 'accepté', teinte: 'accepte' },
      { cle: 'min', libelle: 'Refus mineurs', un: 'refus mineur', teinte: 'mineur' },
      { cle: 'ref', libelle: 'Refusés', un: 'refusé', teinte: 'refuse' }
    ]
  },
  tve: {
    cle: 'tve', bouton: 'TVE', sigle: 'TVE', titre: 'TVE',
    source: 'Drawings TVE', unite: 'dossiers',
    statuts: [
      { cle: 'acc', libelle: 'Acceptés', un: 'accepté', teinte: 'accepte' },
      { cle: 'fref', libelle: 'Faux refus', un: 'faux refus', teinte: 'mineur' },
      { cle: 'ref', libelle: 'Refusés', un: 'refusé', teinte: 'refuse' }
    ]
  }
};

const PERIODES = [
  { cle: '3', libelle: '3 mois', n: 3 },
  { cle: '6', libelle: '6 mois', n: 6 },
  { cle: '12', libelle: '1 an', n: 12 },
  { cle: 'tout', libelle: 'Tout', n: Infinity }
];

/* Même borne que les chargements de data.js. */
const DELAI_LECTURE = 8000;

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/* Les noms de mois qu'écrit le Command Center (« OCT 26 »), et leurs
   équivalents français, sans accents. */
const NOMS_MOIS = {
  JAN: 1, JANV: 1, JANVIER: 1, JANUARY: 1, FEB: 2, FEV: 2, FEVR: 2, FEVRIER: 2, FEBRUARY: 2,
  MAR: 3, MARS: 3, MARCH: 3, APR: 4, AVR: 4, AVRIL: 4, APRIL: 4, MAY: 5, MAI: 5,
  JUN: 6, JUIN: 6, JUNE: 6, JUL: 7, JUIL: 7, JUILLET: 7, JULY: 7, AUG: 8, AOU: 8, AOUT: 8, AUGUST: 8,
  SEP: 9, SEPT: 9, SEPTEMBRE: 9, SEPTEMBER: 9, OCT: 10, OCTOBRE: 10, OCTOBER: 10,
  NOV: 11, NOVEMBRE: 11, NOVEMBER: 11, DEC: 12, DECEMBRE: 12, DECEMBER: 12
};

/* -------------------------------------------------------------------------
   2. Lire
   ------------------------------------------------------------------------- */

function sansAccents(t) { return String(t).normalize('NFD').replace(/[̀-ͯ]/g, ''); }

/** « OCT 26 », « 2026-10 », « octobre 2026 », « 10/2026 », « 24/10/2026 » → « 2026-10 » ; '' sinon. */
export function moisIso(valeur) {
  const deux = (n) => String(n).padStart(2, '0');
  const ok = (a, m) => (a > 1900 && a < 2200 && m >= 1 && m <= 12 ? a + '-' + deux(m) : '');
  const annee = (y) => (y < 100 ? 2000 + y : y);
  const t = sansAccents(String(valeur === null || valeur === undefined ? '' : valeur)).trim().toUpperCase().replace(/^'/, '');
  let m = /^(\d{4})[-/.](\d{1,2})\b/.exec(t);
  if (m) return ok(Number(m[1]), Number(m[2]));
  m = /^([A-Z]+)\.?[\s'’\-/.]*(\d{2}|\d{4})$/.exec(t);
  if (m && NOMS_MOIS[m[1]]) return ok(annee(Number(m[2])), NOMS_MOIS[m[1]]);
  m = /^(\d{1,2})[-/.](\d{2}|\d{4})$/.exec(t);
  if (m) return ok(annee(Number(m[2])), Number(m[1]));
  m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$/.exec(t);
  if (m) return ok(annee(Number(m[3])), Number(m[2]));
  return '';
}

function entier(brut) {
  const t = String(brut === null || brut === undefined ? '' : brut).trim().replace(',', '.');
  if (t === '') return 0;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : 0;
}

/**
 * Analyse un CSV simple (guillemets pris en charge, séparateur , ou ;).
 * Rend les lignes en tableaux de cellules, l'en-tête compris.
 */
export function analyserCsv(texte) {
  const brut = String(texte || '').replace(/^﻿/, '');
  const lignes = brut.split(/\r?\n/).filter((l) => l.trim() !== '');
  if (!lignes.length) return [];
  const separateur = (lignes[0].match(/;/g) || []).length > (lignes[0].match(/,/g) || []).length ? ';' : ',';
  return lignes.map((ligne) => {
    const cellules = []; let courante = ''; let entreGuillemets = false;
    for (let i = 0; i < ligne.length; i += 1) {
      const c = ligne[i];
      if (c === '"') {
        if (entreGuillemets && ligne[i + 1] === '"') { courante += '"'; i += 1; }
        else entreGuillemets = !entreGuillemets;
      } else if (c === separateur && !entreGuillemets) { cellules.push(courante); courante = ''; }
      else courante += c;
    }
    cellules.push(courante);
    return cellules.map((x) => x.trim());
  });
}

/* Ce que dit un titre de colonne : « mois », « otq.acc », « tve.fref »…
   Les mots suffisent : « ✅ PROD ACCEPTED », « prod_accepted » et
   « Prod accepted » se valent. */
export function colonneDe(titre) {
  const h = ' ' + sansAccents(titre).toUpperCase().replace(/[^A-Z]+/g, ' ').trim() + ' ';
  if (/ (MOIS|MONTH|DATE) /.test(h)) return 'mois';
  const groupe = / TVE /.test(h) ? 'tve' : / PROD /.test(h) ? 'otq' : '';
  if (!groupe) return '';
  if (/ FALSE /.test(h)) return groupe + '.fref';
  if (/ MINOR /.test(h)) return groupe + '.min';
  if (/ ACCEPT/.test(h)) return groupe + '.acc';
  if (/ REFUS/.test(h)) return groupe + '.ref';
  return '';
}

function seriesVides() {
  return { mois: [], otq: { acc: [], min: [], ref: [] }, tve: { acc: [], fref: [], ref: [] } };
}

/**
 * Les lignes d'un CSV (en-tête en première ligne) → les séries mensuelles,
 * triées, un mois une seule fois (la dernière ligne l'emporte). Une ligne
 * sans mois lisible est écartée.
 */
export function seriesDepuisCsv(lignes) {
  const s = seriesVides();
  if (!lignes.length) return s;
  const colonnes = lignes[0].map(colonneDe);
  const iMois = colonnes.indexOf('mois') >= 0 ? colonnes.indexOf('mois') : 0;
  const parMois = new Map();
  for (const cellules of lignes.slice(1)) {
    const mois = moisIso(cellules[iMois]);
    if (!mois) continue;
    const ligne = { otq: { acc: 0, min: 0, ref: 0 }, tve: { acc: 0, fref: 0, ref: 0 } };
    colonnes.forEach((c, i) => {
      const [g, k] = c.split('.');
      if (k && ligne[g] && k in ligne[g]) ligne[g][k] = entier(cellules[i]);
    });
    parMois.set(mois, ligne);
  }
  return seriesDepuisLignes([...parMois.entries()].map(([mois, l]) => Object.assign({ mois }, l)));
}

/* [{ mois, otq: {acc, min, ref}, tve: {acc, fref, ref} }] → séries. */
function seriesDepuisLignes(lignes) {
  const s = seriesVides();
  lignes.slice().sort((a, b) => a.mois.localeCompare(b.mois)).forEach((l) => {
    s.mois.push(l.mois);
    for (const g of ['otq', 'tve']) for (const k of Object.keys(s[g])) s[g][k].push(entier(l[g] && l[g][k]));
  });
  return s;
}

/**
 * Ce que rend le serveur du site (Code.gs, lireOtq_) → les séries. La
 * forme est vérifiée : une base mal formée vaut une base absente.
 */
export function seriesDepuisBase(base) {
  const b = base && typeof base === 'object' ? base : null;
  if (!b || !Array.isArray(b.mois)) return null;
  const lignes = [];
  b.mois.forEach((m, i) => {
    const mois = moisIso(m);
    if (!mois) return;
    const val = (g, k) => (b[g] && Array.isArray(b[g][k]) ? b[g][k][i] : 0);
    lignes.push({
      mois,
      otq: { acc: val('otq', 'acc'), min: val('otq', 'min'), ref: val('otq', 'ref') },
      tve: { acc: val('tve', 'acc'), fref: val('tve', 'fref'), ref: val('tve', 'ref') }
    });
  });
  return lignes.length ? seriesDepuisLignes(lignes) : null;
}

async function lireCsv(url) {
  /* Le fichier autonome embarque ses textes : un fetch relatif n'y
     résoudrait rien. */
  const integres = ressourceIntegree('__TEXTES_INTEGRES');
  if (integres && typeof integres[url] === 'string') return integres[url];
  const controleur = typeof AbortController === 'function' ? new AbortController() : null;
  const minuteur = controleur ? setTimeout(() => controleur.abort(), DELAI_LECTURE) : null;
  try {
    const r = await fetch(url, { cache: 'no-store', signal: controleur ? controleur.signal : undefined });
    if (!r.ok) throw new Error('réponse ' + r.status);
    return await r.text();
  } finally {
    if (minuteur !== null) clearTimeout(minuteur);
  }
}

/**
 * Charge les nombres : le serveur du site, sinon le CSV publié, sinon
 * l'exemple. Rend { series, origine: 'feuille' | 'source' | 'exemple' }.
 */
export async function chargerSuivi() {
  try {
    const m = await ouvrirMagasin();
    const series = m && typeof m.base === 'function' ? seriesDepuisBase(m.base('otq')) : null;
    if (series) return { series, origine: 'feuille' };
  } catch (_e) { /* pas de serveur : on passe à la suite */ }
  const url = String(SOURCE.url || '').trim();
  let texte;
  try {
    texte = await lireCsv(url || SOURCE.exemple);
  } catch (cause) {
    console.error('[otq] lecture impossible', cause);
    /* Un message d'erreur ne porte jamais l'adresse de la feuille. */
    throw new Error('Impossible de lire le suivi OTQ : ' + (url ? 'la feuille du service' : 'le fichier d’exemple')
      + ' n’a pas pu être lu. Vérifiez votre connexion, puis réessayez.');
  }
  return { series: seriesDepuisCsv(analyserCsv(texte)), origine: url ? 'source' : 'exemple' };
}

/* -------------------------------------------------------------------------
   3. Compter
   ------------------------------------------------------------------------- */

function fr(v, decimales) {
  return Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: decimales === undefined ? 0 : decimales });
}
function libelleMois(iso, long) {
  const m = /^(\d{4})-(\d{2})$/.exec(iso);
  return m ? (long ? MOIS_LONGS : MOIS_COURTS)[Number(m[2]) - 1] + ' ' + m[1] : iso;
}
function moisCourant() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

/* Le mois i d'un indicateur : chaque statut, le total, le taux (null
   sans plan présenté). */
function mesure(s, def, i) {
  const n = {};
  let total = 0;
  for (const st of def.statuts) { n[st.cle] = s[def.cle][st.cle][i] || 0; total += n[st.cle]; }
  return { mois: s.mois[i], n, total, taux: total ? (n.acc / total) * 100 : null, enCours: s.mois[i] === moisCourant() };
}

/* Des graduations rondes : 0, 20, 40, 60 plutôt que 0, 17, 34, 51. */
function graduations(max) {
  if (!(max > 0)) return [0, 1];
  const brut = max / 3;
  const puissance = Math.pow(10, Math.floor(Math.log10(brut)));
  const pas = [1, 2, 2.5, 5, 10].map((k) => k * puissance).find((p) => p >= brut) || 10 * puissance;
  const haut = Math.ceil(max / pas) * pas;
  const ticks = [];
  for (let v = 0; v <= haut + 1e-9; v += pas) ticks.push(Math.round(v * 100) / 100);
  return ticks;
}

/* -------------------------------------------------------------------------
   4. Montrer
   ------------------------------------------------------------------------- */

function bandeauOrigine(origine) {
  if (origine === 'exemple') {
    return el('div', { class: 'otq__origine otq__origine--exemple', role: 'note' },
      el('span', { class: 'otq__origine-marque' }, 'Données d’exemple'),
      el('span', {}, 'Ces barres illustrent la présentation ; elles ne mesurent rien.'));
  }
  return el('div', { class: 'otq__origine otq__origine--source', role: 'note' },
    el('span', { class: 'otq__origine-point', 'aria-hidden': 'true' }),
    el('span', {}, origine === 'feuille'
      ? 'Command Center du service, onglet « Data », relu à chaque ouverture.'
      : 'Feuille publiée du service, relue à chaque ouverture.'));
}

function pastille(teinte) {
  return el('span', { class: 'otq-pastille', dataset: { teinte }, 'aria-hidden': 'true' });
}

/* L'une : le dernier mois complet, en grand. */
function une(s, def, indices) {
  const complets = indices.filter((i) => s.mois[i] !== moisCourant());
  const iUne = (complets.length ? complets : indices).slice(-1)[0];
  const m = mesure(s, def, iUne);
  const iAvant = indices[indices.indexOf(iUne) - 1];
  const avant = iAvant === undefined ? null : mesure(s, def, iAvant);
  const ecart = avant && m.taux !== null && avant.taux !== null ? m.taux - avant.taux : null;
  let presentes = 0; let acceptes = 0;
  indices.forEach((i) => { const x = mesure(s, def, i); presentes += x.total; acceptes += x.n.acc; });
  const periode = indices.length > 1 ? 'du ' + libelleMois(s.mois[indices[0]]) + ' au ' + libelleMois(s.mois[indices[indices.length - 1]]) : '';
  return el('article', { class: 'otq-une', dataset: { indicateur: def.cle } },
    el('header', { class: 'otq-une__tete' },
      el('p', { class: 'otq-une__sigle' }, def.sigle),
      el('h3', { class: 'otq-une__titre' }, def.titre),
      el('p', { class: 'otq-une__mois' }, libelleMois(m.mois, true) + (m.enCours ? ' (en cours)' : ''))),
    m.taux === null
      ? el('p', { class: 'otq-une__vide' }, 'Aucun ' + def.unite.replace(/s$/, '') + ' présenté ce mois-là.')
      : el('div', { class: 'otq-une__mesure' },
        el('p', { class: 'otq-une__valeur' }, fr(m.taux), el('span', { class: 'otq-une__unite' }, ' %')),
        el('p', { class: 'otq-une__phrase' },
          el('strong', {}, fr(m.n.acc)), ' acceptés sur ', el('strong', {}, fr(m.total)), ' ' + def.unite + ' présentés')),
    ecart === null ? null : el('p', { class: ['otq-une__ecart', ecart > 0.05 ? 'otq-une__ecart--hausse' : ecart < -0.05 ? 'otq-une__ecart--baisse' : null] },
      el('span', { 'aria-hidden': 'true' }, ecart > 0.05 ? '↗ ' : ecart < -0.05 ? '↘ ' : '→ '),
      (ecart > 0 ? '+' : ecart < 0 ? '−' : '') + fr(Math.abs(ecart)) + (Math.abs(ecart) >= 2 ? ' points' : ' point') + ' par rapport à ' + libelleMois(avant.mois, true).replace(/ \d{4}$/, '')),
    el('ul', { class: 'otq-une__repartition', role: 'list' },
      def.statuts.map((st) => el('li', {},
        pastille(st.teinte),
        el('span', { class: 'otq-une__statut' }, st.libelle),
        el('span', { class: 'otq-une__nombre' }, fr(m.n[st.cle]))))),
    presentes && indices.length > 1
      ? el('p', { class: 'otq-une__periode' },
        'Sur la période, ' + periode + ' : ', el('strong', {}, fr(acceptes / presentes * 100) + ' %'),
        ' (' + fr(acceptes) + ' sur ' + fr(presentes) + ').')
      : null,
    el('p', { class: 'otq-une__calcul' }, 'Taux = acceptés ÷ ' + def.unite + ' présentés, d’après « ' + def.source + ' », lignes ETII.'));
}

/* Les barres : un mois par colonne, empilée de bas en haut par statut,
   séparée de 2 px. Une bulle au survol ou au focus dit tout le mois ; le
   tableau, replié, redit tous les nombres. */
function barres(s, def, indices) {
  const mesures = indices.map((i) => mesure(s, def, i));
  const ticks = graduations(Math.max(1, ...mesures.map((m) => m.total)));
  const haut = ticks[ticks.length - 1] || 1;
  const bulle = el('div', { class: 'otq-barres__bulle', role: 'status', hidden: true });
  const phrase = (m) => libelleMois(m.mois, true) + (m.enCours ? ' (en cours)' : '') + ' : ' + fr(m.total) + ' ' + def.unite
    + (m.taux === null ? '' : ', ' + fr(m.taux) + ' % acceptés') + ' — '
    + def.statuts.map((st) => fr(m.n[st.cle]) + ' ' + st.libelle.toLowerCase()).join(', ') + '.';
  const montrer = (m, colonne) => {
    monter(bulle,
      el('p', { class: 'otq-barres__bulle-mois' }, libelleMois(m.mois, true) + (m.enCours ? ' · en cours' : '')),
      m.taux === null ? null : el('p', { class: 'otq-barres__bulle-taux' }, fr(m.taux) + ' % acceptés'),
      el('ul', { role: 'list' }, def.statuts.slice().reverse().map((st) => el('li', {},
        pastille(st.teinte), el('span', {}, st.libelle), el('strong', {}, fr(m.n[st.cle]))))),
      el('p', { class: 'otq-barres__bulle-total' }, fr(m.total) + ' ' + def.unite + ' présentés'));
    bulle.hidden = false;
    const cadre = colonne.closest('.otq-barres__cadre');
    const r = colonne.getBoundingClientRect();
    const rc = cadre.getBoundingClientRect();
    const x = r.left + r.width / 2 - rc.left;
    bulle.style.left = Math.round(Math.max(90, Math.min(rc.width - 90, x))) + 'px';
  };
  const cacher = () => { bulle.hidden = true; };
  const dernier = mesures.length - 1 - [...mesures].reverse().findIndex((m) => !m.enCours);
  const colonnes = mesures.map((m, k) => {
    const annee = k === 0 || m.mois.slice(5) === '01';
    const colonne = el('button', {
      type: 'button', class: ['otq-barres__colonne', m.enCours ? 'otq-barres__colonne--en-cours' : null],
      style: { '--part': (m.total / haut).toFixed(4) },
      'aria-label': phrase(m),
      onPointerenter: (e) => montrer(m, e.currentTarget), onPointerleave: cacher,
      onFocus: (e) => montrer(m, e.currentTarget), onBlur: cacher
    },
    el('span', { class: 'otq-barres__pile' },
      def.statuts.map((st) => (m.n[st.cle]
        ? el('span', { class: 'otq-barres__segment', dataset: { teinte: st.teinte }, style: { flexGrow: String(m.n[st.cle]) } })
        : null))),
    k === dernier && m.taux !== null ? el('span', { class: 'otq-barres__etiquette', 'aria-hidden': 'true' }, fr(m.taux) + ' %') : null);
    return el('li', { class: 'otq-barres__mois' },
      colonne,
      el('span', { class: 'otq-barres__libelle', 'aria-hidden': 'true' },
        MOIS_COURTS[Number(m.mois.slice(5)) - 1].replace('.', ''),
        annee ? el('span', { class: 'otq-barres__annee' }, m.mois.slice(0, 4)) : null));
  });
  const legende = el('ul', { class: 'otq-barres__legende', role: 'list' },
    def.statuts.map((st) => el('li', {}, pastille(st.teinte), st.libelle)));
  const tableau = el('details', { class: 'otq-barres__tableau' },
    el('summary', {}, 'Le tableau des nombres'),
    el('div', { class: 'otq-barres__tableau-cadre' },
      el('table', {},
        el('thead', {}, el('tr', {},
          el('th', { scope: 'col' }, 'Mois'),
          def.statuts.map((st) => el('th', { scope: 'col' }, st.libelle)),
          el('th', { scope: 'col' }, 'Présentés'), el('th', { scope: 'col' }, 'Taux'))),
        el('tbody', {}, mesures.slice().reverse().map((m) => el('tr', {},
          el('th', { scope: 'row' }, libelleMois(m.mois, true) + (m.enCours ? ' (en cours)' : '')),
          def.statuts.map((st) => el('td', {}, fr(m.n[st.cle]))),
          el('td', {}, fr(m.total)),
          el('td', {}, m.taux === null ? '—' : fr(m.taux) + ' %')))))));
  return el('figure', { class: 'otq-barres' },
    el('figcaption', { class: 'otq-barres__tete' },
      el('span', { class: 'otq-barres__titre' }, def.unite.charAt(0).toUpperCase() + def.unite.slice(1) + ' présentés, mois par mois'),
      legende),
    el('div', { class: 'otq-barres__cadre', style: { '--colonnes': String(mesures.length) } },
      el('div', { class: 'otq-barres__grille', 'aria-hidden': 'true' },
        ticks.map((v) => el('span', { class: 'otq-barres__graduation', style: { '--y': (v / haut).toFixed(4) } },
          el('span', { class: 'otq-barres__graduation-texte' }, fr(v))))),
      el('ol', { class: 'otq-barres__mois-liste', role: 'list' }, colonnes),
      bulle),
    tableau);
}

function groupe(libelle, choix, actif, surChoisir) {
  return el('div', { class: 'otq-bascule', role: 'group', 'aria-label': libelle },
    choix.map((c) => el('button', {
      type: 'button', class: 'otq-bascule__choix', 'aria-pressed': c.cle === actif ? 'true' : 'false',
      onClick: () => surChoisir(c.cle)
    }, c.libelle)));
}

/**
 * La section : l'origine des nombres, deux bascules (la mesure, la
 * période), puis le mois en grand et ses barres.
 * @param {{series:object, origine:string}} suivi
 * @returns {HTMLElement}
 */
export function rendreSuivi(suivi) {
  const s = suivi.series;
  const etat = { ind: 'otq', periode: '12' };
  const commandes = el('div', { class: 'otq__commandes' });
  const vue = el('div', { class: 'otq__vue' });
  const dessiner = () => {
    const def = INDICATEURS[etat.ind];
    const p = PERIODES.find((x) => x.cle === etat.periode) || PERIODES[2];
    const tous = s.mois.map((_m, i) => i);
    const indices = tous.slice(Math.max(0, tous.length - p.n));
    monter(commandes,
      groupe('Mesure', Object.values(INDICATEURS).map((d) => ({ cle: d.cle, libelle: d.bouton })), etat.ind, (cle) => { etat.ind = cle; dessiner(); }),
      groupe('Période', PERIODES, etat.periode, (cle) => { etat.periode = cle; dessiner(); }));
    monter(vue, indices.length ? [une(s, def, indices), barres(s, def, indices)] : el('p', { class: 'texte-doux' }, 'Aucun mois à montrer.'));
  };
  dessiner();
  return el('div', { class: 'otq' }, bandeauOrigine(suivi.origine), commandes, vue);
}
