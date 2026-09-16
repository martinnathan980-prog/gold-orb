/* =========================================================================
   ETII Hub — Dessin de la flotte
   Silhouettes d'appareils en SVG inline, carte d'appareil, carrousel.

   AUCUNE image, aucun fichier externe, aucune police iconographique : tout
   est tracé par ce module. Le site reste donc utilisable hors ligne, et le
   dessin suit le thème sans une seule couleur littérale — le tracé prend
   `currentColor`, la couleur de texte héritée.

   HONNÊTETÉ DU DESSIN
   Ce sont des SILHOUETTES STYLISÉES, pas des plans. Elles ne portent
   aucune cote, aucune performance, aucune caractéristique chiffrée. Les
   variantes ne se distinguent que par QUATRE traits volontairement
   lisibles, et par rien d'autre :
     1. le train : patins ou roues ;
     2. le rotor de queue : classique (disque libre) ou caréné ;
     3. le nombre de blocs moteur visibles : un ou deux ;
     4. la taille relative du fuselage (une simple homothétie).
   Rotor principal, stabilisateur et détails de cabine sont IDENTIQUES d'une
   variante à l'autre : varier le nombre de pales ou la forme des ouvertures
   reviendrait à prétendre décrire des appareils réels, ce que ce dessin ne
   fait pas.

   CONTRAT DE CLASSES
   Le module pose des classes existantes (`carte`, `badge`, `bouton`,
   `etat-vide`…) et, pour ce qu'il ajoute, une feuille intégrée déposée UNE
   FOIS en tête de `<head>` (voir §7). Elle n'emploie que des `var(--…)` de
   tokens.css — aucune valeur brute. Comme elle est insérée AVANT les
   feuilles du site et les `<style>` de page, toute page hôte peut redéfinir
   ces classes sans lutter contre une spécificité artificielle.

   Classes ajoutées :
     .helico  .flotte-carte  .flotte-carte__figure  .flotte-carte__code
     .flotte-carte__rubrique  .flotte-carte__etiquette  .flotte-carte__liste
     .flotte-pole  .flotte-pole__point  .flotte-jauge  .flotte-jauge__part
     .flotte-carrousel  .flotte-carrousel__barre  .flotte-carrousel__commandes
     .flotte-carrousel__pistes  .flotte-carrousel__piste
     .flotte-carrousel__positions  .flotte-carrousel__etat  .flotte-position

   Tout le DOM passe par `el()` / `svg()` de ui.js : aucune chaîne de balisage,
   aucun `innerHTML`, aucun gestionnaire en attribut.
   ========================================================================= */

import { el, svg, monter, mouvementReduit, rafThrottle } from './ui.js';

/* -------------------------------------------------------------------------
   0. Géométrie du dessin

   Toutes les valeurs sont des coordonnées du `viewBox`, à l'échelle 1:1.
   Ce sont des mesures de tracé, pas des jetons de design : elles n'ont
   aucun équivalent dans tokens.css et n'ont rien à y faire.
   ------------------------------------------------------------------------- */

/** Boîte de dessin. Elle contient la PLUS GRANDE variante, marges comprises. */
const VB_LARGEUR = 240;
const VB_HAUTEUR = 124;

/** Ligne de contact du train : patins et roues s'y posent tous. */
const SOL = 112;

/** Centre de l'homothétie : le bas du dessin, pour que tous les appareils
    reposent sur la même ligne quelle que soit leur taille relative. */
const PIVOT_X = VB_LARGEUR / 2;
const PIVOT_Y = SOL;

/** Épaisseur de trait apparente, compensée de l'échelle dans `silhouette`. */
const TRAIT = 2;

/** Opacités de remplissage : masses pleines, vitrages, pièces lointaines. */
const REMPLISSAGE_MASSE = 0.12;
const REMPLISSAGE_VITRE = 0.2;
const REMPLISSAGE_MOYEU = 0.32;
const TRAIT_LOINTAIN = 0.45;

/* --- Tracés communs à toutes les variantes ------------------------------ */

/** Fuselage : nez, cabine, poutre de queue. */
const D_FUSELAGE =
  'M 20 76 C 20 56 36 44 62 43 L 98 43 C 116 43 126 49 140 53 ' +
  'L 200 59 L 200 67 L 138 71 C 124 80 108 87 86 87 L 46 87 ' +
  'C 30 87 20 84 20 76 Z';

/** Verrière de cabine. */
const D_VERRIERE = 'M 26 74 C 26 58 38 49 60 48 L 60 63 C 44 64 34 68 30 76 Z';

/** Pales du rotor principal, légèrement fléchies vers les extrémités. */
const D_PALES = 'M 22 33 Q 55 25 88 26 Q 121 25 154 33';

/** Seconde paire de pales, vue sous un autre azimut donc raccourcie. */
const D_PALES_SECONDES = 'M 40 30 Q 64 27 88 27 Q 116 28 140 31';

/** Bloc moteur. Dessiné une ou deux fois selon la variante. */
const D_MOTEUR =
  'M 96 43 L 96 36 C 96 33 99 31 103 31 L 126 31 C 133 31 137 35 139 43 Z';

/** Décalage du second bloc moteur, qui se lit derrière et au-dessus du premier. */
const DECALAGE_MOTEUR = 'translate(13 -4)';

/** Stabilisateur horizontal, identique partout. */
const D_STABILISATEUR = 'M 160 57 L 188 54 L 188 58 L 160 61 Z';

/** Dérive portant un rotor de queue classique. */
const D_DERIVE_CLASSIQUE =
  'M 178 62 L 192 34 C 193 31 196 29 199 29 L 204 29 C 208 29 210 32 209 37 ' +
  'L 204 63 Z';

/** Dérive enveloppante d'un rotor de queue caréné. */
const D_DERIVE_CARENEE =
  'M 184 64 L 194 31 C 195 28 197 27 200 27 L 205 27 C 210 27 213 31 213 39 ' +
  'L 213 49 C 213 61 206 69 197 71 L 188 71 Z';

/* -------------------------------------------------------------------------
   1. Table des variantes

   Les clés sont exactement celles du champ `silhouette` de flotte.json.
   `echelle` est une taille RELATIVE, sans unité et sans prétention : elle
   dit « plus gros que », jamais « fait tant de mètres ».
   ------------------------------------------------------------------------- */

const VARIANTES = {
  'patins-monoturbine': {
    train: 'patins', queue: 'classique', moteurs: 1, echelle: 0.8,
    resume: 'appareil léger sur patins, un bloc moteur, rotor de queue classique'
  },
  'patins-fenestron': {
    train: 'patins', queue: 'carenee', moteurs: 1, echelle: 0.84,
    resume: 'appareil léger sur patins, un bloc moteur, rotor de queue caréné'
  },
  'patins-fenestron-bi': {
    train: 'patins', queue: 'carenee', moteurs: 2, echelle: 0.92,
    resume: 'appareil sur patins, deux blocs moteur, rotor de queue caréné'
  },
  'roues-fenestron-bi': {
    train: 'roues', queue: 'carenee', moteurs: 2, echelle: 1,
    resume: 'appareil sur roues, deux blocs moteur, rotor de queue caréné'
  },
  'roues-bi': {
    train: 'roues', queue: 'classique', moteurs: 2, echelle: 1.06,
    resume: 'appareil sur roues, deux blocs moteur, rotor de queue classique'
  },
  'roues-bi-lourd': {
    train: 'roues', queue: 'classique', moteurs: 2, echelle: 1.12,
    resume: 'appareil de grande taille sur roues, deux blocs moteur, '
      + 'rotor de queue classique'
  }
};

/** Variante servie quand le champ `silhouette` est absent ou inconnu. */
const VARIANTE_DEFAUT = 'patins-monoturbine';

/** Mention rappelant, aux lecteurs d'écran aussi, ce que le dessin n'est pas. */
const MENTION_DESSIN = 'Dessin au trait stylisé, non contractuel : '
  + 'il ne représente ni dimension, ni performance, ni détail technique.';

/* -------------------------------------------------------------------------
   2. Petits utilitaires de tracé
   ------------------------------------------------------------------------- */

/**
 * Chemin non rempli : un contour au trait.
 * @param {string} d
 * @param {object} [extra] attributs supplémentaires (opacité, pointillés…)
 * @returns {SVGElement}
 */
function trait(d, extra) {
  return svg('path', Object.assign(
    { d, fill: 'none', stroke: 'currentColor' }, extra || {}));
}

/**
 * Chemin plein ET contourné : une masse, lisible sur fond clair comme sombre
 * puisque le remplissage n'est qu'un voile de la couleur du texte.
 * @param {string} d
 * @param {number} [opacite]
 * @returns {SVGElement}
 */
function masse(d, opacite) {
  return svg('path', {
    d,
    fill: 'currentColor',
    'fill-opacity': opacite === undefined ? REMPLISSAGE_MASSE : opacite,
    stroke: 'currentColor'
  });
}

/**
 * Disque plein (moyeux) : toujours un `fill` explicite.
 * @param {number} cx
 * @param {number} cy
 * @param {number} r
 * @returns {SVGElement}
 */
function moyeu(cx, cy, r) {
  return svg('circle', {
    cx, cy, r,
    fill: 'currentColor',
    'fill-opacity': REMPLISSAGE_MOYEU,
    stroke: 'currentColor'
  });
}

/**
 * Cercle au trait.
 * @param {number} cx
 * @param {number} cy
 * @param {number} r
 * @param {object} [extra]
 * @returns {SVGElement}
 */
function cercle(cx, cy, r, extra) {
  return svg('circle', Object.assign(
    { cx, cy, r, fill: 'none', stroke: 'currentColor' }, extra || {}));
}

/* -------------------------------------------------------------------------
   3. Les pièces du dessin
   ------------------------------------------------------------------------- */

/** Rotor principal : mât, moyeu et deux paires de pales. Identique partout. */
function rotorPrincipal() {
  return svg('g', { class: 'helico__rotor' },
    trait('M 88 43 L 88 29'),
    trait(D_PALES_SECONDES, { 'stroke-opacity': TRAIT_LOINTAIN }),
    trait(D_PALES),
    svg('ellipse', {
      cx: 88, cy: 27, rx: 10, ry: 3.4,
      fill: 'currentColor',
      'fill-opacity': REMPLISSAGE_MOYEU,
      stroke: 'currentColor'
    }));
}

/** Cellule : fuselage, verrière, porte et hublot. */
function cellule() {
  return svg('g', { class: 'helico__cellule' },
    masse(D_FUSELAGE),
    masse(D_VERRIERE, REMPLISSAGE_VITRE),
    svg('rect', {
      x: 68, y: 50, width: 36, height: 32, rx: 4,
      fill: 'none', stroke: 'currentColor'
    }),
    trait('M 97 67 L 101 67'),
    cercle(116, 61, 5));
}

/**
 * Un ou deux blocs moteur. C'est l'une des quatre différences assumées.
 * @param {number} nombre 1 ou 2
 * @returns {SVGElement}
 */
function blocsMoteur(nombre) {
  const groupe = svg('g', { class: 'helico__moteurs' }, masse(D_MOTEUR));
  if (nombre > 1) {
    groupe.appendChild(svg('g', { transform: DECALAGE_MOTEUR }, masse(D_MOTEUR)));
  }
  return groupe;
}

/** Rotor de queue classique : disque libre, esquissé en pointillés. */
function queueClassique() {
  return svg('g', { class: 'helico__queue' },
    masse(D_DERIVE_CLASSIQUE),
    cercle(200, 41, 11, {
      'stroke-dasharray': '3 5',
      'stroke-opacity': TRAIT_LOINTAIN
    }),
    trait('M 200 41 L 199 31'),
    trait('M 200 41 L 209 47'),
    trait('M 200 41 L 191 47'),
    moyeu(200, 41, 3));
}

/** Rotor de queue caréné : le disque est enfermé dans la dérive. */
function queueCarenee() {
  return svg('g', { class: 'helico__queue' },
    masse(D_DERIVE_CARENEE),
    cercle(199, 48, 12),
    cercle(199, 48, 8.5, { 'stroke-opacity': TRAIT_LOINTAIN }),
    trait('M 199 48 L 199 40'),
    trait('M 199 48 L 206 52'),
    trait('M 199 48 L 192 52'),
    moyeu(199, 48, 2.6));
}

/** Train à patins, avec le patin opposé esquissé en retrait. */
function trainPatins() {
  return svg('g', { class: 'helico__train' },
    trait('M 40 108 L 122 108', { 'stroke-opacity': TRAIT_LOINTAIN }),
    trait('M 56 86 L 46 112'),
    trait('M 96 86 L 106 112'),
    trait('M 34 103 C 30 106 29 109 30 112 L 116 112 L 126 108'));
}

/** Train à roues, avec la roue opposée esquissée en retrait. */
function trainRoues() {
  return svg('g', { class: 'helico__train' },
    cercle(126, 103, 9, { 'stroke-opacity': TRAIT_LOINTAIN }),
    trait('M 44 96 L 44 87'),
    trait('M 106 90 L 100 86'),
    cercle(44, 104, 8),
    moyeu(44, 104, 2.6),
    cercle(106, 101, 11),
    moyeu(106, 101, 3.2));
}

/* -------------------------------------------------------------------------
   4. `silhouette()`
   ------------------------------------------------------------------------- */

/** Compteur d'identifiants : `<title>` et `<desc>` doivent être référençables. */
let compteurSvg = 0;

/**
 * Résout une clé de variante, sans jamais échouer.
 * @param {*} brut
 * @returns {string} une clé présente dans VARIANTES
 */
function cleVariante(brut) {
  const cle = String(brut === null || brut === undefined ? '' : brut).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(VARIANTES, cle) ? cle : VARIANTE_DEFAUT;
}

/**
 * Dessine une silhouette d'hélicoptère de profil, stylisée, au trait.
 *
 * Le tracé est entièrement en `currentColor` : il suit la couleur de texte
 * héritée, donc le thème clair comme le thème sombre, sans aucune couleur
 * littérale. L'élément porte `role="img"` et un `<title>` : jamais une image
 * muette.
 *
 * @param {string} variante  'patins-monoturbine', 'patins-fenestron',
 *   'patins-fenestron-bi', 'roues-fenestron-bi', 'roues-bi', 'roues-bi-lourd'
 * @param {{titre?: string, description?: string, classe?: string}} [options]
 * @returns {SVGElement}
 */
export function silhouette(variante, options) {
  assurerStyles();

  const opts = (options && typeof options === 'object') ? options : {};
  const cle = cleVariante(variante);
  const spec = VARIANTES[cle];

  compteurSvg += 1;
  const idTitre = `helico-titre-${compteurSvg}`;
  const idDesc = `helico-desc-${compteurSvg}`;

  const titre = texteOuDefaut(opts.titre, `Silhouette stylisée : ${spec.resume}.`);
  const description = texteOuDefaut(opts.description, MENTION_DESSIN);

  /* L'échelle est une homothétie autour du bas du dessin : la ligne de sol
     reste commune, seule la taille apparente change. L'épaisseur de trait
     est divisée par l'échelle pour rester constante à l'écran. */
  const e = spec.echelle;
  const dessin = svg('g', {
    transform: `translate(${PIVOT_X} ${PIVOT_Y}) scale(${e}) `
      + `translate(${-PIVOT_X} ${-PIVOT_Y})`,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': (TRAIT / e).toFixed(2),
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round'
  },
  rotorPrincipal(),
  blocsMoteur(spec.moteurs),
  cellule(),
  masse(D_STABILISATEUR, REMPLISSAGE_VITRE),
  spec.queue === 'carenee' ? queueCarenee() : queueClassique(),
  spec.train === 'roues' ? trainRoues() : trainPatins());

  return svg('svg', {
    class: ['helico', `helico--${cle}`, opts.classe || null],
    viewBox: `0 0 ${VB_LARGEUR} ${VB_HAUTEUR}`,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-labelledby': `${idTitre} ${idDesc}`,
    focusable: 'false',
    'data-variante': cle
  },
  svg('title', { id: idTitre }, titre),
  svg('desc', { id: idDesc }, description),
  dessin);
}

/* -------------------------------------------------------------------------
   5. `carteAppareil()`
   ------------------------------------------------------------------------- */

const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
  'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/** Jetons de couleur des pôles. Rien d'autre ne peut entrer dans un style. */
const COULEUR_POLE = {
  ETIIA: 'var(--pole-etiia)',
  ETIIE: 'var(--pole-etiie)',
  ETIII: 'var(--pole-etiii)',
  ETII: 'var(--pole-etii)'
};

/**
 * Chaîne non vide, ou valeur de repli.
 * @param {*} brut
 * @param {string} repli
 * @returns {string}
 */
function texteOuDefaut(brut, repli) {
  const valeur = (brut === null || brut === undefined) ? '' : String(brut).trim();
  return valeur || repli;
}

/**
 * Liste de chaînes propre, quelle que soit la forme reçue.
 * @param {*} brut
 * @returns {string[]}
 */
function listeTexte(brut) {
  if (!Array.isArray(brut)) return [];
  return brut
    .map((v) => (v === null || v === undefined ? '' : String(v).trim()))
    .filter((v) => v !== '');
}

/**
 * Nombre borné à l'intervalle [0, 100], ou null si ce n'en est pas un.
 * @param {*} brut
 * @returns {number|null}
 */
function pourcentage(brut) {
  const n = Number(brut);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, Math.round(n)));
}

/**
 * « 2026-11 » -> « novembre 2026 ». Toute autre forme est rendue telle quelle,
 * car mieux vaut afficher la donnée brute qu'une date inventée.
 * @param {*} brut
 * @returns {{texte: string, machine: string|null}}
 */
function echeanceLisible(brut) {
  const valeur = texteOuDefaut(brut, '');
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(valeur);
  if (!m) return { texte: valeur, machine: null };

  const mois = Number(m[2]);
  if (mois < 1 || mois > 12) return { texte: valeur, machine: null };

  const libelle = m[3]
    ? `${Number(m[3])} ${MOIS[mois - 1]} ${m[1]}`
    : `${MOIS[mois - 1]} ${m[1]}`;
  return { texte: libelle, machine: valeur };
}

/**
 * Rubrique étiquetée d'une carte : un intitulé discret, un contenu.
 * @param {string} etiquette
 * @param {...*} contenu
 * @returns {HTMLElement}
 */
function rubrique(etiquette, ...contenu) {
  return el('div', { class: 'flotte-carte__rubrique' },
    el('span', { class: 'flotte-carte__etiquette' }, etiquette),
    contenu);
}

/**
 * Pastille de pôle ÉTIQUETÉE : le point teinté est décoratif, c'est le
 * libellé « Pôle ETIIA » qui porte l'information. La couleur ne signale
 * donc jamais seule le pôle, et la carte reste lisible en niveaux de gris.
 * @param {string} code
 * @returns {HTMLElement}
 */
function pastillePole(code) {
  const teinte = COULEUR_POLE[code] || COULEUR_POLE.ETII;
  return el('span', {
    class: 'badge badge--contour flotte-pole',
    dataset: { pole: code },
    style: { '--couleur-pole': teinte }
  },
  el('span', { class: 'flotte-pole__point', ariaHidden: 'true' }),
  `Pôle ${code}`);
}

/**
 * Carte complète d'un appareil : silhouette, désignation, segment, usages,
 * pôles concernés en pastilles étiquetées, jalon en cours, avancement et
 * échéance.
 *
 * @param {object} appareil  une entrée de assets/data/flotte.json
 * @param {{niveauTitre?: number, id?: string, classe?: string}} [options]
 * @returns {HTMLElement}
 */
export function carteAppareil(appareil, options) {
  assurerStyles();

  const opts = (options && typeof options === 'object') ? options : {};
  const donnees = (appareil && typeof appareil === 'object') ? appareil : {};

  const code = texteOuDefaut(donnees.code, 'Appareil sans désignation');
  const segment = texteOuDefaut(donnees.segment, '');
  const usages = listeTexte(donnees.usages);
  const poles = listeTexte(donnees.poles);
  const jalon = texteOuDefaut(donnees.jalon, '');
  const avancement = pourcentage(donnees.avancement);
  const echeance = echeanceLisible(donnees.echeance);

  const niveau = Math.min(6, Math.max(2, Number(opts.niveauTitre) || 3));

  const dessin = silhouette(donnees.silhouette, {
    titre: `${code} — silhouette stylisée`,
    description: `Silhouette stylisée : ${VARIANTES[cleVariante(donnees.silhouette)].resume}. `
      + MENTION_DESSIN
  });

  const titre = el(`h${niveau}`, { class: 'carte__titre flotte-carte__code' }, code);
  if (opts.id) titre.id = opts.id;

  return el('article', {
    class: ['carte', 'flotte-carte', opts.classe || null]
  },
  el('figure', { class: 'flotte-carte__figure' }, dessin),

  el('header', { class: 'carte__entete' },
    titre,
    segment ? el('span', { class: 'badge badge--neutre' }, segment) : null),

  el('div', { class: 'carte__corps' },
    usages.length
      ? rubrique('Usages',
        el('ul', { class: 'flotte-carte__liste' },
          usages.map((u) => el('li', {},
            el('span', { class: 'badge badge--contour' }, u)))))
      : null,

    poles.length
      ? rubrique('Pôles concernés',
        el('ul', { class: 'flotte-carte__liste' },
          poles.map((p) => el('li', {}, pastillePole(p)))))
      : null,

    jalon ? rubrique('Jalon en cours', el('p', { class: 'sans-marge' }, jalon)) : null,

    avancement === null ? null : rubrique('Avancement',
      /* La barre est décorative : le chiffre à côté dit tout, elle n'est
         donc pas annoncée deux fois. */
      el('div', { class: 'flotte-jauge', ariaHidden: 'true' },
        el('span', {
          class: 'flotte-jauge__part',
          style: { '--part': `${avancement}%` }
        })),
      el('p', { class: 'sans-marge mono' }, `${avancement} %`))),

  echeance.texte
    ? el('footer', { class: 'carte__pied' },
      el('span', {}, 'Échéance annoncée'),
      echeance.machine
        ? el('time', { class: 'mono', datetime: echeance.machine }, echeance.texte)
        : el('span', { class: 'mono' }, echeance.texte))
    : null);
}

/* -------------------------------------------------------------------------
   6. `carrousel()`

   Un carrousel qui avance tout seul est hostile : il vole la lecture, casse
   la copie de texte et déplace la cible sous le curseur. Celui-ci ne tourne
   donc JAMAIS de lui-même. Une rotation peut être proposée par la page hôte
   (`defilementAuto`), mais elle est à l'arrêt au chargement, pilotée par un
   bouton lecture/pause explicite, suspendue au survol comme au focus, et
   purement et simplement absente quand le système demande moins d'animation.
   ------------------------------------------------------------------------- */

/** Cadence de la rotation facultative, en millisecondes. */
const CADENCE_AUTO = 7000;

/** Chemins des chevrons de navigation. */
const D_CHEVRON_GAUCHE = 'M 14.5 5 L 7.5 12 L 14.5 19';
const D_CHEVRON_DROITE = 'M 9.5 5 L 16.5 12 L 9.5 19';

/** Triangle de lecture et barres de pause. */
const D_LECTURE = 'M 8 5.5 L 18 12 L 8 18.5 Z';
const D_PAUSE_1 = 'M 9 5.5 L 9 18.5';
const D_PAUSE_2 = 'M 15 5.5 L 15 18.5';

/**
 * Icône de commande : un tracé en `currentColor`, décoratif, jamais seul —
 * chaque bouton porte aussi un nom accessible.
 * @param {string[]} chemins
 * @param {boolean} plein
 * @returns {SVGElement}
 */
function icone(chemins, plein) {
  return svg('svg', {
    class: 'bouton__icone',
    viewBox: '0 0 24 24',
    'aria-hidden': 'true',
    focusable: 'false',
    fill: plein ? 'currentColor' : 'none',
    stroke: 'currentColor',
    'stroke-width': TRAIT,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round'
  },
  chemins.map((d) => svg('path', {
    d,
    fill: plein ? 'currentColor' : 'none',
    stroke: 'currentColor'
  })));
}

/**
 * Normalise l'entrée : tableau d'appareils, ou objet `{ flotte: [...] }`
 * tel que le livre assets/data/flotte.json.
 * @param {*} brut
 * @returns {object[]}
 */
function listeAppareils(brut) {
  const tableau = Array.isArray(brut) ? brut
    : (brut && typeof brut === 'object' && Array.isArray(brut.flotte)) ? brut.flotte
      : [];
  return tableau.filter((a) => a && typeof a === 'object');
}

/**
 * Le carrousel de la flotte.
 *
 * - défilement horizontal par pistes, boutons précédent/suivant et clavier
 *   complet (flèches gauche/droite, Origine, Fin) ;
 * - une pastille de position par appareil, cliquable, portant la désignation
 *   de l'appareil — jamais un simple point ;
 * - aucune rotation automatique (voir l'en-tête de section) ;
 * - défilement tactile natif par `scroll-snap`, pleine largeur sur écran
 *   étroit ;
 * - l'appareil courant est annoncé en `aria-live="polite"`.
 *
 * @param {object[]|{flotte: object[]}} flotte
 * @param {{titre?: string, etiquette?: string, defilementAuto?: boolean,
 *          index?: number, classe?: string}} [options]
 * @returns {HTMLElement}
 */
export function carrousel(flotte, options) {
  assurerStyles();

  const opts = (options && typeof options === 'object') ? options : {};
  const appareils = listeAppareils(flotte);
  const total = appareils.length;
  const etiquette = texteOuDefaut(opts.etiquette || opts.titre, 'Flotte suivie par le service');

  /* État vide explicite : la page reste utilisable si le JSON manque. */
  if (total === 0) {
    return el('div', { class: 'etat-vide etat-vide--compact etat-vide--encadre' },
      el('p', { class: 'etat-vide__titre' }, 'Aucun appareil à afficher'),
      el('p', { class: 'etat-vide__texte' },
        'La liste de la flotte est vide ou indisponible.'));
  }

  let index = Math.max(0, Math.min(total - 1, Number(opts.index) || 0));
  const pistes = [];
  const positions = [];

  /* --- Les pistes ------------------------------------------------------- */
  const voie = el('div', {
    class: 'flotte-carrousel__pistes',
    tabIndex: 0,
    role: 'group',
    ariaLabel: `${etiquette} : liste défilante de ${total} appareil`
      + `${total > 1 ? 's' : ''}`,
    onKeyDown: surClavier,
    onMouseEnter: geler,
    onMouseLeave: degeler
  });

  appareils.forEach((appareil, i) => {
    const code = texteOuDefaut(appareil.code, `Appareil ${i + 1}`);
    const piste = el('div', {
      class: 'flotte-carrousel__piste',
      role: 'group',
      'aria-roledescription': 'diapositive',
      ariaLabel: `${i + 1} sur ${total} : ${code}`
    }, carteAppareil(appareil));
    pistes.push(piste);
    voie.appendChild(piste);
  });

  /* --- Commandes -------------------------------------------------------- */
  const boutonPrecedent = el('button', {
    type: 'button',
    class: 'bouton bouton--secondaire bouton--icone bouton--rond',
    ariaLabel: 'Appareil précédent',
    onClick: () => allerA(index - 1)
  }, icone([D_CHEVRON_GAUCHE], false));

  const boutonSuivant = el('button', {
    type: 'button',
    class: 'bouton bouton--secondaire bouton--icone bouton--rond',
    ariaLabel: 'Appareil suivant',
    onClick: () => allerA(index + 1)
  }, icone([D_CHEVRON_DROITE], false));

  /* --- Rotation facultative, à l'arrêt par défaut ------------------------ */
  const rotationProposee = opts.defilementAuto === true && !mouvementReduit();
  let minuterie = null;       // identifiant d'intervalle, null si rien ne tourne
  let rotationVoulue = false; // l'intention de l'utilisateur, portée par le bouton
  let gele = false;           // survol ou focus DANS le contenu : rien n'avance
  let boutonLecture = null;

  if (rotationProposee) {
    boutonLecture = el('button', {
      type: 'button',
      class: 'bouton bouton--secondaire bouton--icone bouton--rond',
      ariaPressed: 'false',
      ariaLabel: 'Lancer le défilement automatique',
      onClick: basculerRotation
    }, icone([D_LECTURE], true));
  }

  const commandes = el('div', { class: 'flotte-carrousel__commandes' },
    boutonLecture, boutonPrecedent, boutonSuivant);

  /* --- Pastilles de position -------------------------------------------- */
  const groupePositions = el('div', {
    class: 'flotte-carrousel__positions',
    role: 'group',
    ariaLabel: 'Aller à un appareil',
    onKeyDown: surClavierPositions,
    onMouseEnter: geler,
    onMouseLeave: degeler
  });

  appareils.forEach((appareil, i) => {
    const code = texteOuDefaut(appareil.code, `Appareil ${i + 1}`);
    const pastille = el('button', {
      type: 'button',
      class: 'flotte-position',
      ariaLabel: `Aller à l'appareil ${code}, ${i + 1} sur ${total}`,
      tabIndex: i === index ? 0 : -1,
      onClick: () => { allerA(i, { focus: true }); }
    }, code);
    positions.push(pastille);
    groupePositions.appendChild(pastille);
  });

  /* --- Annonce de l'appareil courant ------------------------------------ */
  const etat = el('p', {
    class: 'flotte-carrousel__etat',
    ariaLive: 'polite',
    ariaAtomic: 'true'
  });

  /* --- Assemblage -------------------------------------------------------- */
  const racine = el('section', {
    class: ['flotte-carrousel', opts.classe || null],
    role: 'group',
    'aria-roledescription': 'carrousel',
    ariaLabel: etiquette,
    onFocusIn: surEntreeFocus,
    onFocusOut: surSortieFocus
  },
  el('div', { class: 'flotte-carrousel__barre' }, commandes),
  voie,
  groupePositions,
  etat);

  /* Le défilement à la souris, au doigt ou à la molette fait foi : on
     recalcule la piste la plus proche du bord d'entrée plutôt que de
     supposer que seuls nos boutons déplacent la vue. */
  voie.addEventListener('scroll', rafThrottle(() => {
    const proche = pisteLaPlusProche();
    if (proche !== index) {
      index = proche;
      majEtat();
    }
  }), { passive: true });

  majEtat();
  /* Première mesure après mise en page : avant, tous les rectangles sont nuls. */
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(() => { majEtat(); });
  }

  return racine;

  /* --- Fonctions internes ------------------------------------------------ */

  /**
   * Indice de la piste dont le bord gauche est le plus proche du bord
   * d'entrée de la vue.
   * @returns {number}
   */
  function pisteLaPlusProche() {
    const reference = voie.getBoundingClientRect().left;
    let meilleur = index;
    let ecartMin = Infinity;
    for (let i = 0; i < pistes.length; i += 1) {
      const ecart = Math.abs(pistes[i].getBoundingClientRect().left - reference);
      if (ecart < ecartMin) { ecartMin = ecart; meilleur = i; }
    }
    return meilleur;
  }

  /**
   * Amène une piste en tête de vue.
   * @param {number} cible
   * @param {{focus?: boolean}} [reglages]
   */
  function allerA(cible, reglages) {
    const borne = Math.max(0, Math.min(total - 1, cible));
    index = borne;

    const piste = pistes[borne];
    const dx = piste.getBoundingClientRect().left - voie.getBoundingClientRect().left;
    try {
      voie.scrollTo({
        left: voie.scrollLeft + dx,
        behavior: mouvementReduit() ? 'auto' : 'smooth'
      });
    } catch (_e) {
      /* Navigateur sans options de défilement : on se rabat sur l'affectation. */
      voie.scrollLeft += dx;
    }

    majEtat();
    if (reglages && reglages.focus && positions[borne]) positions[borne].focus();
  }

  /** Reflète l'indice courant : pastilles, boutons, ligne d'annonce. */
  function majEtat() {
    for (let i = 0; i < positions.length; i += 1) {
      const actif = i === index;
      positions[i].setAttribute('aria-current', actif ? 'true' : 'false');
      positions[i].tabIndex = actif ? 0 : -1;
    }

    /* Un bouton désactivé sous le doigt perd le focus sans prévenir : on le
       rend à son voisin quand celui-ci reste utilisable, à la vue sinon. */
    const auDebut = index === 0;
    const auxFins = index === total - 1;
    const actif = document.activeElement;
    if (auDebut && actif === boutonPrecedent) {
      if (auxFins) voie.focus(); else boutonSuivant.focus();
    }
    if (auxFins && actif === boutonSuivant) {
      if (auDebut) voie.focus(); else boutonPrecedent.focus();
    }
    boutonPrecedent.disabled = auDebut;
    boutonSuivant.disabled = auxFins;

    const appareil = appareils[index] || {};
    const code = texteOuDefaut(appareil.code, `Appareil ${index + 1}`);
    const segment = texteOuDefaut(appareil.segment, '');
    const annonce = segment
      ? `Appareil ${index + 1} sur ${total} : ${code} — ${segment}`
      : `Appareil ${index + 1} sur ${total} : ${code}`;
    /* Réécrire le même texte relancerait l'annonce pour rien. */
    if (etat.textContent !== annonce) etat.textContent = annonce;
  }

  /**
   * Clavier sur la vue défilante : flèches, Origine, Fin.
   * @param {KeyboardEvent} evt
   */
  function surClavier(evt) {
    const suivant = indiceClavier(evt);
    if (suivant === null) return;
    evt.preventDefault();
    allerA(suivant);
  }

  /**
   * Clavier sur les pastilles : mêmes touches, plus le déplacement du focus
   * (tabulation unique dans le groupe, flèches à l'intérieur).
   * @param {KeyboardEvent} evt
   */
  function surClavierPositions(evt) {
    const suivant = indiceClavier(evt);
    if (suivant === null) return;
    evt.preventDefault();
    allerA(suivant, { focus: true });
  }

  /**
   * Traduit une touche en indice cible, ou null si la touche ne nous concerne pas.
   * @param {KeyboardEvent} evt
   * @returns {number|null}
   */
  function indiceClavier(evt) {
    if (evt.altKey || evt.ctrlKey || evt.metaKey) return null;
    switch (evt.key) {
      case 'ArrowLeft': return Math.max(0, index - 1);
      case 'ArrowRight': return Math.min(total - 1, index + 1);
      case 'Home': return 0;
      case 'End': return total - 1;
      default: return null;
    }
  }

  /* --- Rotation facultative ---------------------------------------------- */

  /** Bascule l'intention de l'utilisateur : lecture ou pause. */
  function basculerRotation() {
    rotationVoulue = !rotationVoulue;
    if (boutonLecture) {
      boutonLecture.setAttribute('aria-pressed', rotationVoulue ? 'true' : 'false');
      boutonLecture.setAttribute('aria-label', rotationVoulue
        ? 'Mettre le défilement automatique en pause'
        : 'Lancer le défilement automatique');
      const remplacement = rotationVoulue
        ? icone([D_PAUSE_1, D_PAUSE_2], false)
        : icone([D_LECTURE], true);
      monter(boutonLecture, remplacement);
    }
    if (rotationVoulue) demarrer(); else arreter();
    majEtat();
  }

  /**
   * Démarre la minuterie. Trois conditions, toutes nécessaires : l'utilisateur
   * l'a demandé, rien ne la gèle, et le système ne réclame pas moins
   * d'animation.
   */
  function demarrer() {
    if (!rotationVoulue || gele || minuterie !== null || mouvementReduit()) return;
    minuterie = setInterval(() => {
      /* Onglet en arrière-plan : rien ne bouge, rien ne se consomme. */
      if (typeof document !== 'undefined' && document.hidden) return;
      allerA(index + 1 >= total ? 0 : index + 1);
    }, CADENCE_AUTO);
  }

  /** Arrête la minuterie sans toucher à l'intention de l'utilisateur. */
  function arreter() {
    if (minuterie === null) return;
    clearInterval(minuterie);
    minuterie = null;
  }

  /**
   * Gèle la rotation : le pointeur survole le contenu, ou le focus y est
   * entré. On ne gèle PAS pour la barre de commandes : c'est là que se
   * trouve le bouton lecture, et l'atteindre ne doit pas rendre le bouton
   * inopérant.
   */
  function geler() {
    gele = true;
    arreter();
  }

  /** Dégèle, et relance seulement si la lecture avait été demandée. */
  function degeler() {
    gele = false;
    demarrer();
  }

  /**
   * Le focus entre dans le carrousel : tout sauf le bouton lecture gèle.
   * @param {FocusEvent} evt
   */
  function surEntreeFocus(evt) {
    if (boutonLecture && evt && evt.target === boutonLecture) return;
    geler();
  }

  /**
   * Le focus quitte-t-il vraiment le carrousel ? `focusout` remonte aussi
   * pour un déplacement interne : dégeler alors serait faux.
   * @param {FocusEvent} evt
   */
  function surSortieFocus(evt) {
    if (evt && evt.relatedTarget && racine.contains(evt.relatedTarget)) return;
    degeler();
  }
}

/* -------------------------------------------------------------------------
   7. Feuille intégrée

   Déposée une seule fois, EN TÊTE de `<head>` : une page hôte qui veut
   redéfinir ces classes le fait sans surenchère de spécificité. Aucune
   valeur brute — uniquement des `var(--…)` de tokens.css — et toute
   transition est levée sous `prefers-reduced-motion: reduce`.
   ------------------------------------------------------------------------- */

const ID_STYLES = 'helicos-styles';

const STYLES = `
.helico {
  display: block;
  inline-size: 100%;
  block-size: auto;
}

.flotte-carte {
  block-size: 100%;
}

.flotte-carte__figure {
  margin: 0;
  padding: var(--e-2) var(--e-3);
  color: var(--texte-doux);
  background-color: var(--fond-enfonce);
  border: 1px solid var(--bordure-douce);
  border-radius: var(--rayon-md);
}

.flotte-carte__code {
  font-size: var(--texte-xl);
  font-weight: var(--graisse-extra);
  letter-spacing: var(--lettrage-titre);
  font-variant-numeric: tabular-nums;
}

.flotte-carte__rubrique {
  display: flex;
  flex-direction: column;
  gap: var(--e-2);
}

.flotte-carte__etiquette {
  font-size: var(--texte-xs);
  font-weight: var(--graisse-forte);
  letter-spacing: var(--lettrage-etiquette);
  text-transform: uppercase;
  color: var(--texte-faible);
}

.flotte-carte__liste {
  display: flex;
  flex-wrap: wrap;
  gap: var(--e-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.flotte-pole {
  --couleur-pole: var(--pole-etii);
  display: inline-flex;
  align-items: center;
  gap: var(--e-2);
  border-color: color-mix(in srgb, var(--couleur-pole) 38%, transparent);
}

.flotte-pole__point {
  flex: none;
  inline-size: var(--e-2);
  block-size: var(--e-2);
  border-radius: var(--rayon-plein);
  background-color: var(--couleur-pole);
}

.flotte-jauge {
  block-size: var(--e-2);
  overflow: hidden;
  background-color: var(--bordure-douce);
  border-radius: var(--rayon-plein);
}

.flotte-jauge__part {
  display: block;
  inline-size: var(--part, 0%);
  block-size: 100%;
  background-color: var(--accent);
  border-radius: var(--rayon-plein);
}

.flotte-carrousel {
  display: flex;
  flex-direction: column;
  gap: var(--e-4);
}

.flotte-carrousel__barre {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--e-3);
}

.flotte-carrousel__commandes {
  display: flex;
  gap: var(--e-2);
  margin-inline-start: auto;
}

/* La barre de défilement reste visible : la masquer priverait la souris et
   le trackpad de tout repère (SPEC §2). */
.flotte-carrousel__pistes {
  display: flex;
  gap: var(--e-4);
  padding-block-end: var(--e-2);
  overflow-x: auto;
  overscroll-behavior-inline: contain;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  border-radius: var(--rayon-lg);
}

.flotte-carrousel__piste {
  display: flex;
  flex: none;
  inline-size: min(100%, calc(var(--e-16) * 5.5));
  scroll-snap-align: start;
}

.flotte-carrousel__piste > .carte {
  inline-size: 100%;
}

.flotte-carrousel__positions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--e-2);
}

.flotte-position {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-inline-size: var(--cible-tactile);
  min-block-size: var(--cible-tactile);
  padding-inline: var(--e-3);
  font: inherit;
  font-size: var(--texte-xs);
  font-weight: var(--graisse-forte);
  color: var(--texte-doux);
  background-color: var(--fond-eleve);
  border: 1px solid var(--bordure);
  border-radius: var(--rayon-plein);
  cursor: pointer;
  transition: color var(--duree-rapide) var(--courbe),
              border-color var(--duree-rapide) var(--courbe);
}

.flotte-position:hover {
  color: var(--texte);
  border-color: var(--bordure-forte);
}

.flotte-position[aria-current="true"] {
  color: var(--accent-contenu);
  background-color: var(--accent);
  border-color: var(--accent);
}

.flotte-carrousel__etat {
  margin: 0;
  text-align: center;
  font-size: var(--texte-sm);
  color: var(--texte-doux);
}

@media (prefers-reduced-motion: reduce) {
  .flotte-carrousel__pistes { scroll-behavior: auto; }
  .flotte-position { transition: none; }
}
`;

/** Dépose la feuille intégrée au premier dessin, et une seule fois. */
function assurerStyles() {
  if (typeof document === 'undefined' || !document.head) return;
  if (document.getElementById(ID_STYLES)) return;

  /* `textContent` sur un <style> : c'est une constante du module, jamais de
     la donnée, et rien ne passe par innerHTML. */
  const feuille = el('style', { id: ID_STYLES });
  feuille.textContent = STYLES;
  document.head.insertBefore(feuille, document.head.firstChild);
}
