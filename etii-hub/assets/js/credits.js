/* =========================================================================
   ETII Hub — Le crédit d'une photo

   Les photos du site viennent de Wikimedia Commons sous licence libre
   (CC BY, CC BY-SA) : l'auteur et la licence DOIVENT apparaître, c'est la
   condition de réutilisation. Trois endroits en ont besoin — la fiche d'un
   porteur (porteurs.js), le pied d'une communication (kiosque.js) et la
   fenêtre « Crédits photos » (index.js) — d'où ce module d'une fonction
   plutôt que trois écritures du même paragraphe.

   Il ne dépend que de ui.js : le kiosque peut l'importer sans tirer avec
   lui la galerie des porteurs et ses silhouettes.
   ========================================================================= */

import { el } from './ui.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/**
 * « Photo : auteur · licence · Wikimedia Commons », en une ligne discrète.
 *
 * @param {{auteur?:string, licence?:string, page?:string, note?:string}} credit
 * @returns {HTMLElement|null} null si rien n'est à déclarer
 */
export function creditPhoto(credit) {
  const c = (credit && typeof credit === 'object' && !Array.isArray(credit)) ? credit : {};
  const auteur = texte(c.auteur);
  const licence = texte(c.licence);
  const page = texte(c.page);
  if (!auteur && !licence && !page) return null;
  const note = texte(c.note);
  return el('p', { class: 'porteurs__credit sans-marge' },
    el('span', { class: 'porteurs__credit-mot' }, 'Photo : '),
    auteur || 'auteur à renseigner',
    licence ? [' · ', licence] : null,
    page ? [' · ', el('a', { href: page, target: '_blank', rel: 'noopener noreferrer' }, 'Wikimedia Commons')] : null,
    note ? el('span', { class: 'porteurs__credit-note' }, note) : null);
}

/**
 * Les crédits distincts des images d'une entrée (image en bannière, blocs
 * « image », diapositives d'un bloc « galerie »), dédoublonnés par
 * auteur · licence · page — une même photo créditée deux fois ne se lit
 * qu'une fois.
 *
 * @param {Array<{credit?:object}>} images
 * @returns {Array<object>} les crédits, dans l'ordre de première apparition
 */
export function creditsDistincts(images) {
  const vus = new Set();
  const credits = [];
  for (const image of (Array.isArray(images) ? images : [])) {
    const c = image && typeof image === 'object' ? image.credit : null;
    if (!c || typeof c !== 'object') continue;
    const cle = texte(c.auteur) + '|' + texte(c.licence) + '|' + texte(c.page);
    if (cle === '||' || vus.has(cle)) continue;
    vus.add(cle);
    credits.push(c);
  }
  return credits;
}
