/* =========================================================================
   ETII Hub — La source des communications

   Le site est statique : il ne publie rien, il LIT. Les communications
   viennent soit du fichier assets/data/communications.json (le cas par
   défaut, et la version autonome), soit d'une feuille Google publiée en
   CSV, où le chef ajoute une ligne par communication — c'est la « partie
   administrateur » du service, sans serveur ni compte : une feuille, une
   ligne, et le site se met à jour à l'ouverture. Le point de raccordement
   est SOURCE.url, comme pour le suivi OTQ / OTD (otq.js).

   Ce module porte aussi le vocabulaire du corps d'une communication — les
   préfixes de ligne du formulaire Apps Script d'origine du service :
     ->  titre        •  puce (ou « - », « * »)
     V   validé       !  alerte
   et sa conversion dans les deux sens (texte ↔ lignes typées).

   Forme d'une communication (celle de communications.json) :
     { id, date: 'AAAA-MM-JJ', pole: 'ETII'|'ETIIA'|'ETIIE'|'ETIII',
       categorie, statut: 'info'|'succes'|'urgent', titre, resume,
       corps: [{ type: 'texte'|'titre'|'puce'|'valide'|'alerte'|'vide', texte }],
       image?: { src, alt, legende },
       chiffres?: [{ libelle, valeur, unite, tendance: 'hausse'|'baisse'|'stable' }]  (4 au plus)
       serie?: { libelle, unite, mois: ['2026-01', …], valeurs: [nombre|null, …] } }
   Le mot du chef a la même forme, sans pole ni statut, avec auteur et
   fonction. Une alerte est un texte.
   ========================================================================= */

import { chargerDonnees } from './data.js';

/* -------------------------------------------------------------------------
   1. LE POINT DE RACCORDEMENT — la seule chose à modifier en production
   ------------------------------------------------------------------------- */

export const SOURCE = {
  /* URL du CSV publié (Fichier → Partager → Publier sur le web → CSV) ou
     URL d'une web app Apps Script qui renvoie le même CSV. Vide : le site
     lit assets/data/communications.json. Voir docs/COMMUNICATIONS-GOOGLE-SHEETS.md. */
  url: ''
};

/* Les colonnes de la feuille, dans l'ordre. L'en-tête de la feuille les
   nomme (insensible à la casse et aux accents) ; l'ordre réel des colonnes
   n'a pas d'importance. */
export const COLONNES = [
  'type', 'id', 'date', 'pole', 'categorie', 'statut', 'titre', 'resume',
  'corps', 'image', 'imageAlt', 'imageLegende', 'chiffres', 'serie', 'auteur', 'fonction'
];

const POLES = ['ETII', 'ETIIA', 'ETIIE', 'ETIII'];
const STATUTS = ['info', 'succes', 'urgent'];
const TENDANCES = { hausse: 'hausse', baisse: 'baisse', stable: 'stable', '↗': 'hausse', '↘': 'baisse', '→': 'stable', '=': 'stable', '+': 'hausse', '-': 'baisse' };

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function normaliser(v) { return texte(v).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }

/** Un nombre écrit à la française ou à l'anglaise ; null s'il est illisible. */
export function nombre(brut) {
  const t = texte(brut).replace(/\s/g, '').replace('%', '').replace(',', '.');
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/* -------------------------------------------------------------------------
   2. Le corps : texte à préfixes ↔ lignes typées
   ------------------------------------------------------------------------- */

const PREFIXES = [
  { type: 'titre', motif: /^(->|→|#)\s*/ },
  { type: 'valide', motif: /^(V|✓|\[x\])\s+/i },
  { type: 'alerte', motif: /^(!|⚠)\s*/ },
  { type: 'puce', motif: /^([•·\-*])\s*/ }
];

const MARQUES = { titre: '-> ', puce: '• ', valide: 'V ', alerte: '! ', texte: '', vide: '' };

/**
 * Découpe un texte multi-lignes en lignes typées selon les préfixes du
 * service. Une ligne vide devient `vide` ; une ligne sans préfixe, `texte`.
 * @param {string} brut
 * @returns {Array<{type:string, texte:string}>}
 */
export function analyserCorps(brut) {
  const t = String(brut === null || brut === undefined ? '' : brut).replace(/\r\n?/g, '\n');
  if (!t.trim()) return [];
  const lignes = t.split('\n').map((l) => {
    const propre = l.trim();
    if (!propre) return { type: 'vide', texte: '' };
    for (const p of PREFIXES) {
      const m = p.motif.exec(propre);
      if (m) return { type: p.type, texte: propre.slice(m[0].length).trim() };
    }
    return { type: 'texte', texte: propre };
  });
  /* Les vides de tête et de queue n'ont aucun sens. */
  while (lignes.length && lignes[0].type === 'vide') lignes.shift();
  while (lignes.length && lignes[lignes.length - 1].type === 'vide') lignes.pop();
  return lignes;
}

/**
 * L'inverse : des lignes typées vers le texte à préfixes, tel qu'on le
 * saisit dans la feuille ou dans le formulaire.
 * @param {Array<{type:string, texte:string}>} lignes
 * @returns {string}
 */
export function corpsEnTexte(lignes) {
  if (!Array.isArray(lignes)) return '';
  return lignes
    .filter((l) => l && typeof l === 'object')
    .map((l) => (l.type === 'vide' ? '' : (MARQUES[l.type] || '') + texte(l.texte)))
    .join('\n');
}

/* -------------------------------------------------------------------------
   3. CSV (RFC 4180) : guillemets, virgules et retours à la ligne dans les
      cellules ; séparateur « , » « ; » ou tabulation, détecté sur l'en-tête
   ------------------------------------------------------------------------- */

/**
 * @param {string} brut
 * @returns {Array<object>} une ligne = un objet { colonne normalisée → chaîne }
 */
export function analyserCsv(brut) {
  const t = String(brut === null || brut === undefined ? '' : brut).replace(/^﻿/, '');
  if (!t.trim()) return [];
  const premiereLigne = t.split(/\r?\n/)[0];
  const separateur = premiereLigne.includes('\t') ? '\t'
    : (premiereLigne.split(';').length > premiereLigne.split(',').length ? ';' : ',');

  const rangees = [];
  let rangee = [];
  let cellule = '';
  let entreGuillemets = false;
  for (let i = 0; i < t.length; i += 1) {
    const c = t[i];
    if (entreGuillemets) {
      if (c === '"') {
        if (t[i + 1] === '"') { cellule += '"'; i += 1; } else { entreGuillemets = false; }
      } else {
        cellule += c;
      }
    } else if (c === '"') {
      entreGuillemets = true;
    } else if (c === separateur) {
      rangee.push(cellule); cellule = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && t[i + 1] === '\n') i += 1;
      rangee.push(cellule); cellule = '';
      rangees.push(rangee); rangee = [];
    } else {
      cellule += c;
    }
  }
  if (cellule !== '' || rangee.length) { rangee.push(cellule); rangees.push(rangee); }

  const entete = (rangees.shift() || []).map((h) => normaliser(h).replace(/[^a-z0-9]/g, ''));
  const alias = { imagealt: 'imageAlt', imagelegende: 'imageLegende', legende: 'imageLegende', resume: 'resume',
    categorie: 'categorie', programme: 'categorie', theme: 'categorie', chiffresclés: 'chiffres', chiffrescles: 'chiffres' };
  return rangees
    .filter((r) => r.some((v) => texte(v) !== ''))
    .map((r) => {
      const o = {};
      entete.forEach((h, i) => { if (h) o[alias[h] || h] = texte(r[i]); });
      return o;
    });
}

/* -------------------------------------------------------------------------
   4. Les champs composés : chiffres clés et série
   ------------------------------------------------------------------------- */

/**
 * « OTQ du service = 95,4 % hausse ; Semaines d'essais = 6 ; Écarts = 3 ↘ »
 * → [{ libelle, valeur, unite, tendance }]. Une partie illisible est ignorée.
 * @param {string} brut
 */
export function analyserChiffres(brut) {
  return texte(brut).split(/\s*;\s*/).filter(Boolean).map((part) => {
    const i = part.indexOf('=');
    if (i === -1) return null;
    const libelle = texte(part.slice(0, i));
    const jetons = texte(part.slice(i + 1)).split(/\s+/).filter(Boolean);
    if (!libelle || !jetons.length) return null;
    /* Le premier jeton est la valeur ; le dernier peut être une tendance ;
       ce qui reste entre les deux est l'unité. « 95,4 % » : le « % » collé
       ou séparé va dans l'unité. */
    let valeurBrute = jetons.shift();
    let unite = '';
    if (/%$/.test(valeurBrute) && valeurBrute.length > 1) { valeurBrute = valeurBrute.slice(0, -1); unite = '%'; }
    const valeur = nombre(valeurBrute);
    if (valeur === null) return null;
    let tendance = '';
    if (jetons.length && TENDANCES[normaliser(jetons[jetons.length - 1])]) tendance = TENDANCES[normaliser(jetons.pop())];
    unite = [unite, jetons.join(' ')].filter(Boolean).join(' ');
    return { libelle, valeur, unite, tendance };
  }).filter(Boolean).slice(0, 4);
}

/**
 * « OTQ mensuel (%) | 2026-04 = 92,1 ; 2026-05 = 92,8 ; 2026-06 = »
 * → { libelle, unite, mois, valeurs } ou null. Un mois sans valeur donne null.
 * @param {string} brut
 */
export function analyserSerie(brut) {
  const t = texte(brut);
  if (!t) return null;
  const barre = t.indexOf('|');
  let libelle = barre === -1 ? 'Série' : texte(t.slice(0, barre));
  let unite = '';
  const mU = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(libelle);
  if (mU) { libelle = texte(mU[1]) || 'Série'; unite = texte(mU[2]); }
  const points = (barre === -1 ? t : t.slice(barre + 1)).split(/\s*;\s*/).filter(Boolean)
    .map((p) => {
      const i = p.indexOf('=');
      if (i === -1) return null;
      const mois = texte(p.slice(0, i));
      if (!/^\d{4}-\d{2}$/.test(mois)) return null;
      return { mois, valeur: nombre(p.slice(i + 1)) };
    }).filter(Boolean);
  if (!points.length || !points.some((p) => p.valeur !== null)) return null;
  return { libelle, unite, mois: points.map((p) => p.mois), valeurs: points.map((p) => p.valeur) };
}

/** L'inverse, pour la ligne de la feuille. */
export function chiffresEnTexte(chiffres) {
  if (!Array.isArray(chiffres)) return '';
  return chiffres.filter((c) => c && texte(c.libelle)).map((c) =>
    [texte(c.libelle) + ' = ' + String(c.valeur).replace('.', ','), texte(c.unite), texte(c.tendance)].filter(Boolean).join(' ')).join(' ; ');
}

/** L'inverse, pour la ligne de la feuille. */
export function serieEnTexte(serie) {
  if (!serie || typeof serie !== 'object' || !Array.isArray(serie.mois)) return '';
  const tete = texte(serie.libelle) + (texte(serie.unite) ? ' (' + texte(serie.unite) + ')' : '');
  return tete + ' | ' + serie.mois.map((m, i) => {
    const v = Array.isArray(serie.valeurs) ? serie.valeurs[i] : null;
    return texte(m) + ' = ' + (typeof v === 'number' ? String(v).replace('.', ',') : '');
  }).join(' ; ');
}

/* -------------------------------------------------------------------------
   5. Des lignes de la feuille à l'objet de communications.json
   ------------------------------------------------------------------------- */

function dateIso(brut) {
  const t = texte(brut);
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(t); // 12/09/2026, tel que Google Sheets l'exporte en français
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  return '';
}

/**
 * Convertit une ligne de la feuille en annonce (forme de communications.json).
 * Renvoie null si la ligne n'a ni titre ni date lisible.
 * @param {object} ligne  objet issu de analyserCsv()
 * @param {number} rang   pour fabriquer un identifiant quand il manque
 */
export function annonceDepuisLigne(ligne, rang) {
  const l = (ligne && typeof ligne === 'object') ? ligne : {};
  const titre = texte(l.titre);
  const date = dateIso(l.date);
  if (!titre || !date) return null;
  const pole = POLES.includes(texte(l.pole).toUpperCase()) ? texte(l.pole).toUpperCase() : 'ETII';
  const statut = STATUTS.includes(normaliser(l.statut)) ? normaliser(l.statut) : 'info';
  const image = /^https:\/\/|^assets\//.test(texte(l.image))
    ? { src: texte(l.image), alt: texte(l.imageAlt), legende: texte(l.imageLegende) }
    : null;
  const annonce = {
    id: texte(l.id) || ('f' + date.replace(/-/g, '') + '-' + (Number(rang) + 1)),
    date, pole,
    categorie: texte(l.categorie) || 'Général',
    statut,
    titre,
    resume: texte(l.resume),
    corps: analyserCorps(l.corps)
  };
  if (image) annonce.image = image;
  const chiffres = analyserChiffres(l.chiffres);
  if (chiffres.length) annonce.chiffres = chiffres;
  const serie = analyserSerie(l.serie);
  if (serie) annonce.serie = serie;
  return annonce;
}

/**
 * L'objet complet à partir des lignes de la feuille :
 * - type « mot » : le mot du chef — le plus récent l'emporte ;
 * - type « alerte » : un texte du bandeau (titre, ou résumé) ;
 * - type « annonce » (ou vide) : une annonce.
 * Une ligne illisible est ignorée avec un avertissement, jamais une exception.
 * @param {Array<object>} lignes
 * @returns {{motDuChef: object|null, alertes: string[], annonces: object[], agenda: object[]}}
 */
export function communicationsDepuisLignes(lignes) {
  const resultat = { motDuChef: null, alertes: [], annonces: [], agenda: [] };
  const mots = [];
  (Array.isArray(lignes) ? lignes : []).forEach((ligne, i) => {
    const type = normaliser(ligne && ligne.type) || 'annonce';
    if (type === 'alerte') {
      const t = texte(ligne.titre) || texte(ligne.resume);
      if (t) resultat.alertes.push(t);
      return;
    }
    const annonce = annonceDepuisLigne(ligne, i);
    if (!annonce) {
      if (typeof console !== 'undefined') console.warn('[communications] ligne ' + (i + 2) + ' ignorée : titre ou date manquant.');
      return;
    }
    if (type === 'mot' || type === 'motduchef') {
      mots.push(Object.assign(annonce, { auteur: texte(ligne.auteur), fonction: texte(ligne.fonction) }));
    } else {
      resultat.annonces.push(annonce);
    }
  });
  if (mots.length) {
    mots.sort((a, b) => b.date.localeCompare(a.date));
    const m = mots[0];
    resultat.motDuChef = { auteur: m.auteur, fonction: m.fonction, date: m.date, titre: m.titre, resume: m.resume, corps: m.corps };
    if (m.image) resultat.motDuChef.image = m.image;
    if (m.chiffres) resultat.motDuChef.chiffres = m.chiffres;
    if (m.serie) resultat.motDuChef.serie = m.serie;
  }
  resultat.annonces.sort((a, b) => b.date.localeCompare(a.date));
  return resultat;
}

/**
 * La ligne de la feuille pour une annonce (ou un mot du chef, ou une
 * alerte), colonnes dans l'ordre de COLONNES, séparées par des tabulations
 * — à coller telle quelle dans Google Sheets.
 * @param {object} annonce  forme de communications.json
 * @param {'annonce'|'mot'|'alerte'} [type]
 */
export function ligneDepuisAnnonce(annonce, type) {
  const a = (annonce && typeof annonce === 'object') ? annonce : {};
  const image = (a.image && typeof a.image === 'object') ? a.image : {};
  const valeurs = {
    type: type || 'annonce', id: texte(a.id), date: texte(a.date), pole: texte(a.pole),
    categorie: texte(a.categorie), statut: texte(a.statut), titre: texte(a.titre), resume: texte(a.resume),
    corps: corpsEnTexte(a.corps), image: texte(image.src), imageAlt: texte(image.alt), imageLegende: texte(image.legende),
    chiffres: chiffresEnTexte(a.chiffres), serie: serieEnTexte(a.serie), auteur: texte(a.auteur), fonction: texte(a.fonction)
  };
  /* Une cellule qui contient un retour à la ligne ou une tabulation est
     mise entre guillemets, comme Sheets s'y attend au collage. */
  return COLONNES.map((c) => {
    const v = valeurs[c] || '';
    return /[\t\n"]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }).join('\t');
}

/* -------------------------------------------------------------------------
   6. Le chargement
   ------------------------------------------------------------------------- */

/**
 * Lit les communications : la feuille publiée si SOURCE.url est renseignée,
 * sinon le fichier du site. La feuille injoignable ou vide retombe sur le
 * fichier, avec un avertissement en console — le service ne doit jamais
 * voir une page blanche à cause d'une URL.
 * @returns {Promise<object>} objet de la forme de communications.json,
 *   avec `origine` : 'feuille' ou 'fichier'
 */
export async function chargerCommunications() {
  const url = texte(SOURCE.url);
  if (url) {
    try {
      const reponse = await fetch(url, { cache: 'no-store' });
      if (!reponse.ok) throw new Error('réponse ' + reponse.status);
      const objet = communicationsDepuisLignes(analyserCsv(await reponse.text()));
      if (!objet.motDuChef && !objet.annonces.length && !objet.alertes.length) throw new Error('aucune ligne lisible');
      objet.origine = 'feuille';
      return objet;
    } catch (e) {
      if (typeof console !== 'undefined') console.warn('[communications] feuille illisible (' + (e && e.message) + ') : lecture du fichier du site.');
    }
  }
  const local = await chargerDonnees('communications');
  return Object.assign({}, local, { origine: 'fichier' });
}
