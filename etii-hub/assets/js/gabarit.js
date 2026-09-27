/* =========================================================================
   ETII Hub — Le gabarit : les porteurs dessinés à l'échelle

   Un profil d'appareil tracé en mètres, posé sur une ligne de sol, avec
   une personne de 1,80 m pour repère. Le diamètre du rotor est tracé à sa
   vraie longueur ; la longueur hors tout et la hauteur aussi quand la fiche
   les donne. Le reste du dessin — la forme de la cabine, la dérive, le
   train — est STYLISÉ : il suit le type d'appareil (patins ou roues,
   Fenestron ou rotor arrière classique), pas ses plans.

   Seules les valeurs sourcées sont cotées. Une longueur déduite pour
   placer le rotor (quand la fiche ne donne que celle du fuselage, par
   exemple) sert au dessin, jamais à une cote.

   Le dessin est en SVG, en mètres (viewBox) ; les étiquettes sont du HTML
   posé par-dessus, en pourcentages : elles restent lisibles à toutes les
   largeurs, là où un texte SVG rétrécirait avec le dessin.
   ========================================================================= */

import { el, svg } from './ui.js';
import { dimensions, nombreFr, texte } from './gamme.js';

/* La personne de repère, en mètres. */
const PERSONNE = 1.8;
const LARGEUR_PERSONNE = 0.5;
/* Les écarts, en mètres : entre la personne et le premier appareil, entre
   deux appareils, et les marges du dessin. */
const ECART_PERSONNE = 1.4;
const ECART = 2.4;
const MARGE_HAUT = 1.3;
const MARGE_BAS = 1.2;
const MARGE_COTE = 2.6;

/* Un chemin à partir de points en mètres (y vers le haut) : la conversion
   vers le repère SVG (y vers le bas) se fait ici, une fois. */
function traceur(dx, sol) {
  const p = (x, y) => (dx + x).toFixed(3) + ' ' + (sol - y).toFixed(3);
  return { p, X: (x) => dx + x, Y: (y) => sol - y };
}

/**
 * Le profil d'un appareil : cellule, capot moteur, poutre, dérive, train,
 * mât et disque du rotor.
 */
function profil(dim, t, classe) {
  const { Lf, H, xm, D, train, queue, moteurs } = dim;
  const { p, X, Y } = traceur(t.dx, t.sol);
  const yb = train === 'roues' ? 0.15 * H : 0.19 * H;
  const yt = 0.6 * H;
  const ye = 0.73 * H;
  const yr = 0.93 * H;
  const yq = 0.5 * H;
  const nez = yb + 0.42 * (yt - yb);

  const cellule = ['M', p(0, nez),
    'C', p(0, 0.94 * yt), p(0.07 * Lf, yt), p(0.2 * Lf, yt),
    'L', p(0.55 * Lf, yt),
    'C', p(0.6 * Lf, yt), p(0.6 * Lf, yq + 0.07 * H), p(0.66 * Lf, yq + 0.06 * H),
    'L', p(0.9 * Lf, yq + 0.035 * H),
    'L', p(0.9 * Lf, yq - 0.035 * H),
    'L', p(0.66 * Lf, yq - 0.07 * H),
    'C', p(0.58 * Lf, yq - 0.09 * H), p(0.56 * Lf, yb), p(0.5 * Lf, yb),
    'L', p(0.12 * Lf, yb),
    'C', p(0.03 * Lf, yb), p(0, yb + 0.1 * H), p(0, nez), 'Z'].join(' ');

  const verriere = ['M', p(0.015 * Lf, nez + 0.04 * H),
    'C', p(0.02 * Lf, 0.9 * yt), p(0.08 * Lf, 0.97 * yt), p(0.17 * Lf, 0.97 * yt),
    'L', p(0.17 * Lf, nez + 0.02 * H), 'Z'].join(' ');

  const debutCapot = moteurs > 1 ? 0.21 * Lf : 0.25 * Lf;
  const finCapot = moteurs > 1 ? 0.57 * Lf : 0.52 * Lf;
  const capot = ['M', p(debutCapot, yt),
    'C', p(debutCapot, ye), p(debutCapot + 0.02 * Lf, ye), p(debutCapot + 0.06 * Lf, ye),
    'L', p(finCapot - 0.05 * Lf, ye),
    'C', p(finCapot, ye), p(finCapot, yt + 0.04 * H), p(finCapot + 0.02 * Lf, yt), 'Z'].join(' ');

  /* La dérive : carénée, elle enferme le Fenestron ; classique, elle porte
     un rotor arrière, dessiné en disque pointillé. */
  const derive = queue === 'carenee'
    ? ['M', p(0.84 * Lf, yq - 0.04 * H), 'L', p(0.9 * Lf, 0.84 * H), 'L', p(Lf, 0.87 * H),
      'L', p(Lf, yq - 0.1 * H), 'C', p(0.96 * Lf, yq - 0.16 * H), p(0.88 * Lf, yq - 0.12 * H), p(0.84 * Lf, yq - 0.04 * H), 'Z'].join(' ')
    : ['M', p(0.87 * Lf, yq), 'L', p(0.945 * Lf, 0.8 * H), 'L', p(Lf, 0.82 * H), 'L', p(0.985 * Lf, yq - 0.06 * H), 'Z'].join(' ');

  const elements = [
    svg('path', { d: cellule, class: 'gabarit__masse' }),
    svg('path', { d: verriere, class: 'gabarit__vitre' }),
    svg('path', { d: capot, class: 'gabarit__masse' }),
    svg('path', { d: derive, class: 'gabarit__masse' }),
    svg('line', { x1: X(0.78 * Lf), y1: Y(yq + 0.01 * H), x2: X(0.87 * Lf), y2: Y(yq + 0.02 * H), class: 'gabarit__trait gabarit__trait--epais' })
  ];
  if (queue === 'carenee') {
    elements.push(svg('circle', { cx: X(0.935 * Lf), cy: Y(yq + 0.13 * H), r: (0.1 * H).toFixed(3), class: 'gabarit__fenestron' }));
  } else {
    elements.push(svg('circle', { cx: X(0.975 * Lf), cy: Y(0.72 * H), r: (Math.min(0.085 * D, 0.26 * H)).toFixed(3), class: 'gabarit__disque' }));
  }
  /* Le train. */
  if (train === 'roues') {
    const r = Math.min(0.35, 0.06 * H);
    elements.push(
      svg('line', { x1: X(0.14 * Lf), y1: Y(r), x2: X(0.14 * Lf), y2: Y(yb), class: 'gabarit__trait' }),
      svg('line', { x1: X(0.45 * Lf), y1: Y(r), x2: X(0.44 * Lf), y2: Y(yb), class: 'gabarit__trait' }),
      svg('circle', { cx: X(0.14 * Lf), cy: Y(r), r: r.toFixed(3), class: 'gabarit__roue' }),
      svg('circle', { cx: X(0.45 * Lf), cy: Y(r * 1.15), r: (r * 1.15).toFixed(3), class: 'gabarit__roue' }));
  } else {
    const ys = 0.02 * H;
    elements.push(
      svg('path', { d: ['M', p(0.06 * Lf, 0.07 * H), 'Q', p(0.07 * Lf, ys), p(0.11 * Lf, ys), 'L', p(0.55 * Lf, ys)].join(' '), class: 'gabarit__trait gabarit__trait--epais' }),
      svg('line', { x1: X(0.2 * Lf), y1: Y(ys), x2: X(0.22 * Lf), y2: Y(yb), class: 'gabarit__trait' }),
      svg('line', { x1: X(0.46 * Lf), y1: Y(ys), x2: X(0.44 * Lf), y2: Y(yb), class: 'gabarit__trait' }));
  }
  /* Le mât, le moyeu, et le disque du rotor à sa vraie largeur. */
  elements.push(
    svg('line', { x1: X(xm), y1: Y(ye), x2: X(xm), y2: Y(yr), class: 'gabarit__trait gabarit__trait--epais' }),
    svg('path', { d: ['M', p(xm - D / 2, yr - 0.03 * H), 'Q', p(xm, yr + 0.02 * H), p(xm + D / 2, yr - 0.03 * H)].join(' '), class: 'gabarit__pales' }),
    svg('rect', { x: X(xm - 0.35), y: Y(H), width: 0.7, height: (H - yr + 0.06 * H).toFixed(3), rx: 0.08, class: 'gabarit__moyeu' }));
  return svg('g', { class: ['gabarit__appareil', classe] }, elements);
}

/* La personne de 1,80 m : une silhouette sans visage, au trait plein. */
function personne(x, sol) {
  const { p } = traceur(x, sol);
  const w = LARGEUR_PERSONNE;
  return svg('g', { class: 'gabarit__personne' },
    svg('circle', { cx: (x + w / 2).toFixed(3), cy: (sol - 1.66).toFixed(3), r: 0.12 }),
    svg('path', { d: ['M', p(0.02, 0.92), 'L', p(0.02, 1.4), 'Q', p(0.02, 1.52), p(0.14, 1.52), 'L', p(w - 0.14, 1.52),
      'Q', p(w - 0.02, 1.52), p(w - 0.02, 1.4), 'L', p(w - 0.02, 0.92), 'Z'].join(' ') }),
    svg('rect', { x: (x + 0.09).toFixed(3), y: (sol - 0.96).toFixed(3), width: 0.13, height: 0.96, rx: 0.05 }),
    svg('rect', { x: (x + w - 0.22).toFixed(3), y: (sol - 0.96).toFixed(3), width: 0.13, height: 0.96, rx: 0.05 }));
}

/* Une cote : un trait fin entre deux petits traits de rappel. */
function cote(x1, y1, x2, y2, vertical) {
  const t = 0.18;
  return svg('g', { class: 'gabarit__cote' },
    svg('line', { x1, y1, x2, y2 }),
    vertical
      ? [svg('line', { x1: x1 - t, y1, x2: x1 + t, y2: y1 }), svg('line', { x1: x2 - t, y1: y2, x2: x2 + t, y2 })]
      : [svg('line', { x1, y1: y1 - t, x2: x1, y2: y1 + t }), svg('line', { x1: x2, y1: y2 - t, x2, y2: y2 + t })]);
}

/* Une étiquette HTML posée sur le dessin, en pourcentages de la scène. */
function etiquette(texteEtiquette, x, y, boite, classe) {
  return el('span', {
    class: ['gabarit__etiquette', classe],
    style: { left: ((x - boite.x0) / boite.w * 100).toFixed(2) + '%', top: (y / boite.h * 100).toFixed(2) + '%' }
  }, texteEtiquette);
}

function metres(c) {
  return (c.qualificatif ? c.qualificatif + ' ' : '') + nombreFr(c.ref, 2) + ' m';
}

/**
 * Dessine un ou plusieurs appareils à la même échelle, côte à côte sur une
 * même ligne de sol, avec la personne de repère à gauche.
 *
 * @param {Array<object>} appareils   les appareils (flotte.json), dans l'ordre
 * @param {{cotes?: boolean, scene?: {largeur:number, hauteur:number}, titre?: string}} [options]
 *   `cotes` : cotes du premier appareil (la fiche) ; `scene` : une taille de
 *   scène commune, en mètres, pour que deux fiches se lisent à la même
 *   échelle (le plus grand de la gamme y tient).
 * @returns {HTMLElement|null}  null si aucun appareil n'a de quoi être dessiné
 */
export function gabarit(appareils, options) {
  const o = options || {};
  const liste = appareils.map((a) => ({ a, dim: dimensions(a) })).filter((x) => x.dim);
  if (!liste.length) return null;
  const avecCotes = o.cotes === true && liste.length === 1;

  /* La largeur utile : la personne, puis chaque appareil de bout en bout. */
  let curseur = LARGEUR_PERSONNE + ECART_PERSONNE;
  const places = liste.map((x) => {
    const debut = curseur;
    curseur += x.dim.L + ECART;
    return Object.assign(x, { dx: debut + x.dim.avant });
  });
  let largeur = curseur - ECART + (avecCotes && liste[0].dim.cotes.hauteur ? MARGE_COTE : 0.8);
  const hauteurMax = Math.max(PERSONNE, ...liste.map((x) => x.dim.H));
  let hauteur = hauteurMax;
  if (o.scene) {
    largeur = Math.max(largeur, o.scene.largeur);
    hauteur = Math.max(hauteur, o.scene.hauteur);
  }
  const sol = MARGE_HAUT + hauteur;
  const boite = { x0: -0.6, w: largeur + 0.6, h: sol + MARGE_BAS };

  const traces = [
    svg('line', { x1: boite.x0, y1: sol, x2: largeur, y2: sol, class: 'gabarit__sol' }),
    personne(0, sol)
  ];
  const etiquettes = [etiquette('1,80 m', LARGEUR_PERSONNE / 2, sol + 0.35, boite, 'gabarit__etiquette--personne')];

  places.forEach((x, i) => {
    traces.push(profil(x.dim, { dx: x.dx, sol }, 'gabarit__appareil--' + Math.min(i, 2)));
    const centre = x.dx + x.dim.xm;
    const code = texte(x.a.code);
    if (!avecCotes) {
      etiquettes.push(etiquette(code, centre, sol - x.dim.H - 0.55, boite, ['gabarit__etiquette--code', 'gabarit__etiquette--' + Math.min(i, 2)]));
      const c = x.dim.cotes.longueur || x.dim.cotes.fuselage;
      if (c) etiquettes.push(etiquette(metres(c) + (x.dim.cotes.longueur ? '' : ' (fuselage)'), x.dx - x.dim.avant + x.dim.L / 2, sol + 0.35, boite, 'gabarit__etiquette--sous'));
    }
  });

  if (avecCotes) {
    const x = places[0];
    const { cotes, L, H, D, xm, avant, Lf } = x.dim;
    const gauche = x.dx - avant;
    /* La longueur, sous le sol : hors tout si la fiche la donne, sinon
       celle du fuselage, du nez à la dérive. */
    if (cotes.longueur) {
      traces.push(cote(gauche, sol + 0.55, gauche + L, sol + 0.55));
      etiquettes.push(etiquette(metres(cotes.longueur) + ' hors tout', gauche + L / 2, sol + 0.55, boite, 'gabarit__etiquette--cote'));
    } else if (cotes.fuselage) {
      traces.push(cote(x.dx, sol + 0.55, x.dx + Lf, sol + 0.55));
      etiquettes.push(etiquette(metres(cotes.fuselage) + ' de fuselage', x.dx + Lf / 2, sol + 0.55, boite, 'gabarit__etiquette--cote'));
    }
    /* Le rotor, au-dessus du disque. */
    const yRotor = sol - H - 0.5;
    traces.push(cote(x.dx + xm - D / 2, yRotor, x.dx + xm + D / 2, yRotor));
    etiquettes.push(etiquette(metres(cotes.rotor) + ' de rotor', x.dx + xm, yRotor, boite, 'gabarit__etiquette--cote gabarit__etiquette--dessus'));
    /* La hauteur, à droite de l'appareil. */
    if (cotes.hauteur) {
      const xh = gauche + L + 0.7;
      traces.push(cote(xh, sol, xh, sol - H, true));
      etiquettes.push(etiquette(metres(cotes.hauteur), xh + 0.3, sol - H / 2, boite, 'gabarit__etiquette--cote gabarit__etiquette--droite'));
    }
  }

  const titre = o.titre || ('Silhouettes à l’échelle : ' + places.map((x) => texte(x.a.code)).join(', ') + ', à côté d’une personne de 1,80 m.');
  return el('figure', {
    class: 'gabarit',
    style: { '--gabarit-ratio': (boite.w / boite.h).toFixed(4) }
  },
  el('div', { class: 'gabarit__scene' },
    svg('svg', {
      class: 'gabarit__dessin', viewBox: [boite.x0, 0, boite.w, boite.h].map((n) => n.toFixed(3)).join(' '),
      preserveAspectRatio: 'xMidYMax meet', role: 'img', 'aria-label': titre, focusable: 'false'
    }, traces),
    el('div', { class: 'gabarit__etiquettes', 'aria-hidden': 'true' }, etiquettes)));
}

/**
 * La scène commune de la gamme : assez large et haute pour que le plus
 * grand appareil y tienne. Deux fiches dessinées sur cette scène se lisent
 * à la même échelle — passer d'un H125 à un NH90 fait grandir le dessin.
 */
export function sceneGamme(appareils) {
  let L = 0;
  let H = PERSONNE;
  let avecHauteur = false;
  for (const a of appareils) {
    const d = dimensions(a);
    if (!d) continue;
    L = Math.max(L, d.L);
    H = Math.max(H, d.H);
    if (d.cotes.hauteur) avecHauteur = true;
  }
  if (!L) return null;
  return { largeur: LARGEUR_PERSONNE + ECART_PERSONNE + L + (avecHauteur ? MARGE_COTE : 0.8), hauteur: H };
}
