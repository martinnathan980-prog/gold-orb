/* =========================================================================
   ETII Hub — Le crédit d'une photo

   Les photos du site viennent de Wikimedia Commons sous licence libre
   (CC BY, CC BY-SA) : l'auteur et la licence DOIVENT apparaître, c'est la
   condition de réutilisation. Deux endroits en ont besoin — la fiche d'un
   porteur (porteurs.js) et la fenêtre « Crédits photos » du pied de page,
   ouverte depuis le tableau de bord (index.js) comme depuis un espace de
   pôle (pole.js) — d'où ce module plutôt que plusieurs écritures du même
   paragraphe. Aucune communication ne porte son crédit sous elle : c'est
   un choix de l'utilisateur, et la fenêtre tient l'obligation.

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

/**
 * La section « Images des communications » de la fenêtre « Crédits
 * photos » : chaque image d'une communication qui porte un crédit (photo
 * sous licence libre), une seule fois. Une photo du service, sans crédit,
 * n'a rien à déclarer.
 *
 * @param {object|null} communications  le retour de chargerCommunications()
 * @returns {HTMLElement|null} null si aucune image n'est créditée
 */
export function creditsCommunications(communications) {
  const c = (communications && typeof communications === 'object') ? communications : {};
  const entrees = [c.motDuChef].concat(Array.isArray(c.annonces) ? c.annonces : [])
    .filter((e) => e && typeof e === 'object');
  const images = [];
  for (const e of entrees) {
    const blocs = Array.isArray(e.blocs) ? e.blocs : [];
    const candidates = [e.image]
      .concat(blocs.filter((b) => b && b.type === 'image'),
        blocs.filter((b) => b && b.type === 'galerie').flatMap((b) => b.images || []));
    for (const im of candidates) {
      if (!im || typeof im !== 'object' || !im.credit || typeof im.credit !== 'object') continue;
      if (images.some((x) => x.src === im.src)) continue;
      images.push({ src: texte(im.src), credit: im.credit, titre: texte(e.titre) });
    }
  }
  if (!images.length) return null;
  return el('div', { class: 'pile pile--serree' },
    el('h3', { class: 'sans-marge' }, 'Images des communications'),
    el('ul', { class: 'porteurs__credits', role: 'list' }, images.map((im) => el('li', { class: 'porteurs__credits-item' },
      el('img', { src: im.src, alt: '', loading: 'lazy', decoding: 'async', class: 'porteurs__credits-vignette' }),
      el('div', { class: 'porteurs__credits-texte' },
        el('span', { class: 'porteurs__credits-nom' }, im.titre),
        creditPhoto(im.credit))))));
}
