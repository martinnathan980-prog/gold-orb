/* =========================================================================
   ETII Hub — Le suivi OTQ / OTD

   Deux taux mensuels, On Time Quality et On Time Delivery, lus dans un
   fichier CSV. En production, ce CSV est un onglet d'un Google Sheet publié
   sur le web, rempli chaque nuit par un script Apps Script depuis la
   feuille source du service (voir docs/OTQ-GOOGLE-SHEETS.md et
   tools/apps-script/otq-sync.gs). Tant que SOURCE.url est vide, la page lit
   assets/data/otq-exemple.csv et le dit : un bandeau « Données d'exemple »
   reste affiché, impossible de prendre ces chiffres pour une mesure.

   Format attendu, une ligne par mois, en-tête obligatoire :
     mois,otq,otd,cible_otq,cible_otd
     2026-01,91.5,92.0,95,92
   « mois » est AAAA-MM. Les décimales acceptent le point ou la virgule. Les
   colonnes de cible sont facultatives ; le séparateur peut être « ; ».
   ========================================================================= */

import { el, monter, titreSection } from './ui.js';
import { tuileIndicateur, graphiqueLignes } from './indicateurs.js';

/* -------------------------------------------------------------------------
   1. LE POINT DE RACCORDEMENT — la seule chose à modifier en production
   ------------------------------------------------------------------------- */

/* Ce dépôt est public. Ne collez rien ici : renseignez la copie locale,
   puis ne commitez ni ce fichier ni le dist/ fabriqué depuis lui.
   tests/audit.mjs refuse une URL de raccordement commitée ; sur une copie
   raccordée, lancez ETII_RACCORDE=1 node tests/audit.mjs. */
export const SOURCE = {
  /* URL du CSV publié (Fichier → Partager → Publier sur le web → CSV) ou
     URL d'une web app Apps Script qui renvoie le même CSV. Vide : exemple. */
  url: '',
  /* Fichier d'exemple embarqué, lu quand url est vide. */
  exemple: 'assets/data/otq-exemple.csv'
};

const DEFINITIONS = {
  otq: { cle: 'otq', libelle: 'OTQ', nom: 'On Time Quality',
    aide: 'Part des livrables conformes dès la première présentation.', unite: '%', sens: 'haut' },
  otd: { cle: 'otd', libelle: 'OTD', nom: 'On Time Delivery',
    aide: 'Part des livrables remis à la date engagée.', unite: '%', sens: 'haut' }
};

/* Même borne que les chargements de data.js : une feuille de calcul publiée
   qui met plus de huit secondes à répondre est de fait injoignable. */
const DELAI_LECTURE = 8000;

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                     'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

/* -------------------------------------------------------------------------
   1bis. Le seul appel réseau du module, borné dans le temps
   ------------------------------------------------------------------------- */

/**
 * fetch() borné dans le temps. Sans borne, une feuille qui ne répond jamais
 * laisse la section en squelette pour toujours : avecEtat() attend la
 * promesse sans minuteur. Le délai est levé dès l'arrivée des en-têtes ; un
 * corps qui se bloque ensuite n'est pas couvert — cas bien plus rare, assumé.
 * @param {string} url
 * @param {object} [options] options de fetch(), plus `delai` en millisecondes
 * @returns {Promise<Response>}
 */
async function recupererReponse(url, options) {
  const opt = options || {};
  const delai = typeof opt.delai === 'number' ? opt.delai : DELAI_LECTURE;
  const controleur = typeof AbortController === 'function' ? new AbortController() : null;
  let expire = false;
  const minuteur = controleur && delai > 0
    ? setTimeout(() => { expire = true; controleur.abort(); }, delai)
    : null;
  try {
    return await fetch(url, Object.assign({}, opt, {
      delai: undefined,
      signal: controleur ? controleur.signal : undefined
    }));
  } catch (cause) {
    throw new Error(expire
      ? 'délai de ' + Math.round(delai / 1000) + ' s dépassé'
      : 'réseau injoignable');
  } finally {
    if (minuteur !== null) clearTimeout(minuteur);
  }
}

/* -------------------------------------------------------------------------
   2. Lecture du CSV
   ------------------------------------------------------------------------- */

function nombre(brut) {
  const t = String(brut === null || brut === undefined ? '' : brut).trim().replace(',', '.').replace('%', '');
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/**
 * Analyse un CSV simple (guillemets pris en charge, séparateur , ou ;).
 * @param {string} texte
 * @returns {Array<object>} une ligne = un objet clé → chaîne
 */
export function analyserCsv(texte) {
  const brut = String(texte || '').replace(/^﻿/, '');
  const lignes = brut.split(/\r?\n/).filter((l) => l.trim() !== '');
  if (!lignes.length) return [];
  const separateur = (lignes[0].match(/;/g) || []).length > (lignes[0].match(/,/g) || []).length ? ';' : ',';
  const decouper = (ligne) => {
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
  };
  const entetes = decouper(lignes[0]).map((h) => h.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, '_'));
  return lignes.slice(1).map((l) => {
    const cellules = decouper(l);
    const objet = {};
    entetes.forEach((h, i) => { objet[h] = cellules[i] === undefined ? '' : cellules[i]; });
    return objet;
  });
}

/**
 * Transforme les lignes CSV en séries mensuelles triées.
 * Une ligne sans mois AAAA-MM valide est ignorée ; une valeur illisible
 * devient null (un trou dans la courbe, jamais un zéro).
 */
export function seriesDepuisLignes(lignes) {
  const valides = lignes
    .map((l) => ({ mois: String(l.mois || l.month || l.date || '').slice(0, 7), otq: nombre(l.otq), otd: nombre(l.otd),
                   cibleOtq: nombre(l.cible_otq), cibleOtd: nombre(l.cible_otd) }))
    .filter((l) => /^\d{4}-\d{2}$/.test(l.mois))
    .sort((a, b) => a.mois.localeCompare(b.mois));
  const derniere = valides[valides.length - 1] || {};
  return {
    mois: valides.map((l) => l.mois),
    otq: valides.map((l) => l.otq),
    otd: valides.map((l) => l.otd),
    cibleOtq: derniere.cibleOtq ?? null,
    cibleOtd: derniere.cibleOtd ?? null
  };
}

/**
 * Charge la source configurée, ou l'exemple. Renvoie les séries et
 * l'origine (« exemple » ou « source »), plus la date de mise à jour si
 * le serveur la donne.
 */
export async function chargerSuivi() {
  const url = String(SOURCE.url || '').trim();
  const cible = url || SOURCE.exemple;
  /* Un message d'erreur ne doit jamais porter l'URL de la feuille : cent
     caractères illisibles à l'écran de tout le service, qui partent dans la
     première capture — et une URL-capacité si l'intermédiaire est branché. */
  const nomCible = url ? 'la feuille du service' : 'le fichier ' + SOURCE.exemple;
  const atteint = url ? 'n’a pas pu être atteinte' : 'n’a pas pu être atteint';
  let reponse;
  try {
    reponse = await recupererReponse(cible, { cache: 'no-store' });
  } catch (cause) {
    console.error('[otq] ' + cible + ' injoignable', cause);
    throw new Error('Impossible de lire le suivi OTQ / OTD : ' + nomCible + ' '
      + atteint + '. Vérifiez votre connexion, puis réessayez.');
  }
  if (!reponse.ok) throw new Error('Suivi OTQ / OTD : réponse ' + reponse.status + ' pour ' + nomCible);
  const texte = await reponse.text();
  const lignes = analyserCsv(texte);
  const series = seriesDepuisLignes(lignes);
  /* Aucune levée sur une série vide : l'état vide d'avecEtat dit déjà
     « Aucune mesure », et il le dit sans citer l'URL. */
  let maj = reponse.headers.get('last-modified') || '';
  if (maj) { const d = new Date(maj); maj = Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10); }
  return { series, origine: url ? 'source' : 'exemple', maj, url: cible };
}

/* -------------------------------------------------------------------------
   3. Rendu
   ------------------------------------------------------------------------- */

function libelleMois(iso) {
  const m = /^(\d{4})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return MOIS_COURTS[Number(m[2]) - 1] + ' ' + m[1];
}

function bandeauOrigine(suivi) {
  if (suivi.origine === 'exemple') {
    return el('div', { class: 'otq__origine otq__origine--exemple', role: 'note' },
      el('span', { class: 'badge badge--alerte' }, 'Données d’exemple'),
      el('span', {}, 'Ces courbes illustrent le rendu. Elles ne mesurent rien. La source réelle se branche dans ',
        el('span', { class: 'mono' }, 'assets/js/otq.js'), ' (', el('span', { class: 'mono' }, 'SOURCE.url'), ') — voir ',
        el('span', { class: 'mono' }, 'docs/OTQ-GOOGLE-SHEETS.md'), '.'));
  }
  return el('div', { class: 'otq__origine', role: 'note' },
    el('span', { class: 'badge badge--succes' }, 'Source du service'),
    el('span', {}, 'Feuille publiée, relue à chaque ouverture de la page',
      suivi.maj ? ' — dernière modification le ' + suivi.maj : '', '.'));
}

/**
 * Construit la section complète : origine, deux tuiles, le graphique.
 * @param {{series:object, origine:string, maj:string}} suivi
 * @returns {HTMLElement}
 */
export function rendreSuivi(suivi) {
  const s = suivi.series;
  const mois = s.mois;
  const defOtq = Object.assign({}, DEFINITIONS.otq, { cible: s.cibleOtq });
  const defOtd = Object.assign({}, DEFINITIONS.otd, { cible: s.cibleOtd });
  const dernierMois = mois[mois.length - 1];

  const tuiles = el('div', { class: 'otq__tuiles' },
    tuileIndicateur({ cle: 'otq', definition: defOtq, serie: s.otq, mois, couleur: 'var(--serie-otq)' }),
    tuileIndicateur({ cle: 'otd', definition: defOtd, serie: s.otd, mois, couleur: 'var(--serie-otd)' }));

  const graphe = graphiqueLignes({
    mois,
    series: [
      { cle: 'otq', libelle: 'OTQ — On Time Quality', valeurs: s.otq, couleur: 'var(--serie-otq)' },
      { cle: 'otd', libelle: 'OTD — On Time Delivery', valeurs: s.otd, couleur: 'var(--serie-otd)' }
    ],
    definition: { libelle: 'OTQ et OTD', nom: 'Taux mensuels', unite: '%', sens: 'haut',
      cible: (s.cibleOtq !== null && s.cibleOtq === s.cibleOtd) ? s.cibleOtq : null },
    titre: 'Douze derniers mois — ' + (mois.length ? libelleMois(mois[0]) + ' à ' + libelleMois(dernierMois) : '')
  });

  return el('div', { class: 'otq' },
    bandeauOrigine(suivi),
    tuiles,
    graphe,
    el('p', { class: 'otq__note texte-faible texte-xs sans-marge' },
      'Cibles : OTQ ', s.cibleOtq === null ? 'non déclarée' : s.cibleOtq + ' %',
      ' · OTD ', s.cibleOtd === null ? 'non déclarée' : s.cibleOtd + ' %',
      '. Une valeur manquante laisse un trou dans la courbe : rien n’est interpolé.'));
}
