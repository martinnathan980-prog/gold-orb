/* =========================================================================
   ETII Hub — Les portraits

   Une seule fonction, `portrait(personne, options)`, utilisée partout où
   une personne se montre : l'arbre d'un pôle, l'organigramme (arbre,
   trombinoscope, compétences, fiche, piles de visages) et l'onglet Équipe
   d'un porteur.

     - Si la personne a une `photo` (un chemin `assets/…` ou une URL
       https), c'est une image : `<img class="portrait">`.
     - Sinon, un PORTRAIT ILLUSTRÉ en SVG : plat, géométrique, sobre. Un
       fond teinté du pôle, des épaules, un cou, une tête, une coupe de
       cheveux. Quelques variantes (coupe, teinte de peau, couleur de
       cheveux, tenue, lunettes) choisies de façon déterministe depuis
       l'identifiant : la même personne a toujours le même portrait, et
       deux voisines ne se ressemblent pas.

   Ce sont les « photos test » du site : lisibles, variées, jamais des
   visages réels. Aucune couleur n'est écrite ici : chaque forme porte un
   `fill="var(--portrait-…)"` défini dans tokens.css (clair et sombre), et
   le fond suit la teinte du pôle par la CSS (`--portrait-fond`).

   Les initiales restent le texte accessible du portrait (`<title>` et
   `aria-label` sur le SVG, `alt` sur l'image) : un lecteur d'écran y
   trouve ce qu'il trouvait dans l'avatar aux initiales.

   API publique :
     portrait(personne, { taille })  -> SVGElement | HTMLImageElement
     initiales(nom)                  -> string
   ========================================================================= */

import { el, svg } from './ui.js';

/** Tailles connues, en miroir des classes `.portrait--…` de modules.css. */
const TAILLES = new Set(['xs', 'sm', 'md', 'lg', 'xl']);

/** Nombre de jetons de couleur par famille (tokens.css : --portrait-peau-1…4). */
const NUANCES = 4;

/** Les coupes de cheveux disponibles, dessinées plus bas. */
const COUPES = ['courte', 'frange', 'longue', 'chignon', 'degarnie', 'bouclee'];

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/**
 * Les initiales d'un nom : « Personne 03 » donne P03 (un numéro vaut
 * mieux qu'un chiffre isolé), « Marie Dupont » donne MD.
 * @param {string} nom
 * @returns {string}
 */
export function initiales(nom) {
  const parts = texte(nom).split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  const dernier = parts[parts.length - 1];
  if (parts.length > 1 && /^\d+$/.test(dernier)) return parts[0][0].toUpperCase() + dernier;
  return [parts[0], dernier].slice(0, parts.length > 1 ? 2 : 1).map((p) => p[0].toUpperCase()).join('');
}

/**
 * Une empreinte entière, stable, d'une chaîne (FNV-1a sur 32 bits). Elle
 * ne sert qu'à choisir des variantes : aucun besoin cryptographique.
 * @param {string} chaine
 * @returns {number} entier positif
 */
function empreinte(chaine) {
  let h = 0x811c9dc5;
  for (let i = 0; i < chaine.length; i += 1) {
    h ^= chaine.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/**
 * Les traits d'un portrait, tirés de l'identifiant. Chaque trait lit un
 * paquet de bits différent de l'empreinte, pour que deux identifiants
 * proches (p03, p04) ne partagent pas tout.
 * @param {string} cle
 * @returns {{coupe: string, peau: number, cheveux: number, tenue: number, lunettes: boolean, col: boolean}}
 */
function traits(cle) {
  const h = empreinte(cle);
  return {
    coupe: COUPES[h % COUPES.length],
    peau: 1 + ((h >>> 4) % NUANCES),
    cheveux: 1 + ((h >>> 8) % NUANCES),
    tenue: 1 + ((h >>> 12) % NUANCES),
    lunettes: ((h >>> 16) % 5) === 0,
    col: ((h >>> 20) % 2) === 0
  };
}

/** Une photo n'est acceptée que depuis le site ou en https : jamais autre chose. */
function photoValide(chemin) {
  const c = texte(chemin);
  return /^assets\/[A-Za-z0-9_./-]+$/.test(c) || /^https:\/\/[^\s"'<>]+$/.test(c);
}

/* -------------------------------------------------------------------------
   Le dessin : un carré de 64 × 64, le visage centré, les épaules coupées
   par le bord bas. Tout est en formes pleines, sans trait ni détail de
   visage — c'est un pictogramme, pas un portrait-robot.
   ------------------------------------------------------------------------- */

function cheveuxDerriere(coupe, teinte) {
  /* Ce qui se dessine DERRIÈRE la tête : les cheveux longs, le chignon. */
  if (coupe === 'longue') {
    return svg('path', { fill: teinte,
      d: 'M17 26 C17 12 24 7 32 7 C40 7 47 12 47 26 L47 48 C47 50 45 51 43 51 L21 51 C19 51 17 50 17 48 Z' });
  }
  if (coupe === 'chignon') {
    return svg('circle', { fill: teinte, cx: 32, cy: 9, r: 6 });
  }
  return null;
}

function cheveuxDevant(coupe, teinte) {
  /* Ce qui se dessine DEVANT la tête : la calotte, la frange, les boucles. */
  if (coupe === 'courte' || coupe === 'chignon') {
    return svg('path', { fill: teinte,
      d: 'M20 24 C20 12 25 8 32 8 C39 8 44 12 44 24 C42 18 38 15 32 15 C26 15 22 18 20 24 Z' });
  }
  if (coupe === 'frange' || coupe === 'longue') {
    return svg('path', { fill: teinte,
      d: 'M19 27 C19 12 25 7 32 7 C39 7 45 12 45 27 L45 22 C42 16 38 14 32 14 C26 14 22 16 19 22 Z' });
  }
  if (coupe === 'degarnie') {
    return svg('path', { fill: teinte,
      d: 'M20 25 C20 18 22 13 26 11 C24 15 23 19 23 25 Z M44 25 C44 18 42 13 38 11 C40 15 41 19 41 25 Z' });
  }
  /* bouclée : une calotte faite de ronds. */
  return svg('g', { fill: teinte },
    svg('circle', { cx: 22, cy: 20, r: 5 }),
    svg('circle', { cx: 27, cy: 13, r: 5.5 }),
    svg('circle', { cx: 32, cy: 10, r: 6 }),
    svg('circle', { cx: 37, cy: 13, r: 5.5 }),
    svg('circle', { cx: 42, cy: 20, r: 5 }),
    svg('path', { d: 'M20 24 C22 14 26 11 32 11 C38 11 42 14 44 24 Z' }));
}

function lunettes() {
  return svg('g', { fill: 'none', stroke: 'var(--portrait-trait)', 'stroke-width': 1.6 },
    svg('circle', { cx: 26.5, cy: 25, r: 4.2 }),
    svg('circle', { cx: 37.5, cy: 25, r: 4.2 }),
    svg('path', { d: 'M30.7 25 L33.3 25' }));
}

function dessiner(t) {
  const peau = 'var(--portrait-peau-' + t.peau + ')';
  const cheveux = 'var(--portrait-cheveux-' + t.cheveux + ')';
  const tenue = 'var(--portrait-tenue-' + t.tenue + ')';
  return [
    svg('rect', { fill: 'var(--portrait-fond)', x: 0, y: 0, width: 64, height: 64 }),
    cheveuxDerriere(t.coupe, cheveux),
    /* Les épaules : un dôme coupé par le bord bas. */
    svg('path', { fill: tenue, d: 'M6 64 C6 50 16 43 32 43 C48 43 58 50 58 64 Z' }),
    /* Le col : en V ou rond, un creux de la teinte de peau. */
    t.col
      ? svg('path', { fill: peau, d: 'M25 43 L32 52 L39 43 Z' })
      : svg('path', { fill: peau, d: 'M25 43 C25 48 39 48 39 43 Z' }),
    /* Le cou. */
    svg('rect', { fill: peau, x: 27, y: 30, width: 10, height: 15, rx: 3 }),
    /* La tête. */
    svg('ellipse', { fill: peau, cx: 32, cy: 24, rx: 11.5, ry: 13 }),
    cheveuxDevant(t.coupe, cheveux),
    t.lunettes ? lunettes() : null
  ];
}

/* -------------------------------------------------------------------------
   L'API
   ------------------------------------------------------------------------- */

/**
 * Le portrait d'une personne.
 *
 * @param {object} personne  { id, nom, photo? } — les autres champs sont ignorés
 * @param {{taille?: 'xs'|'sm'|'md'|'lg'|'xl', decoratif?: boolean}} [options]
 *   taille     la classe de taille (sm par défaut, 2 rem)
 *   decoratif  vrai pour cacher le portrait aux lecteurs d'écran (dans une
 *              pile, où le nom n'est pas affiché mais l'effectif l'est)
 * @returns {SVGElement|HTMLImageElement}
 */
export function portrait(personne, options) {
  const p = (personne && typeof personne === 'object') ? personne : {};
  const opts = options || {};
  const taille = TAILLES.has(opts.taille) ? opts.taille : 'sm';
  const nom = texte(p.nom);
  const ini = initiales(nom);
  const classes = ['portrait', 'portrait--' + taille];

  if (photoValide(p.photo)) {
    return el('img', {
      class: classes.concat('portrait--photo'),
      src: texte(p.photo),
      alt: opts.decoratif ? '' : ini,
      loading: 'lazy',
      decoding: 'async',
      draggable: 'false'
    });
  }

  /* La clé de tirage : l'identifiant, sinon le nom — jamais vide, pour
     qu'une personne sans identifiant ait quand même un visage stable. */
  const cle = texte(p.id) || nom || '?';
  const t = traits(cle);
  return svg('svg', {
    class: classes.concat('portrait--illustre', 'portrait--' + t.coupe),
    viewBox: '0 0 64 64',
    role: 'img',
    'aria-label': opts.decoratif ? null : ini,
    'aria-hidden': opts.decoratif ? 'true' : null,
    focusable: 'false'
  },
  svg('title', {}, ini),
  dessiner(t));
}
