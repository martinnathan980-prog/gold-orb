/* =========================================================================
   ETII Hub — Visualisation des indicateurs de service

   Module partagé par le tableau de bord (index.js) et par les espaces de
   pôle (pole.js). Il ne connaît ni l'URL, ni le pôle actif, ni la page :
   on lui passe des séries déjà filtrées, il rend des figures.

   Cinq fabriques publiques :

     tuileIndicateur({ cle, definition, serie, mois, couleur })  -> HTMLElement
     sparkline(serie, { couleur, cible })                        -> SVGElement
     graphiqueLignes({ mois, series, definition, titre, description })
                                                                 -> HTMLElement
     barresComparees({ categories, valeurs, couleurs, definition, titre })
                                                                 -> HTMLElement
     tableauSeries({ mois, series, definition })                 -> HTMLElement

   -------------------------------------------------------------------------
   RÈGLES DE VISUALISATION APPLIQUÉES ICI

     · UNE SEULE échelle verticale par graphique. Jamais deux axes : deux
       mesures d'échelles différentes, ce sont deux graphiques.
     · La couleur suit l'ENTITÉ, jamais son rang. ETIIA reste violet même
       quand ETIIE est masqué : la couleur arrive par `series[].couleur`,
       elle n'est jamais dérivée d'un index de boucle.
     · Les couleurs de statut (succès / alerte) ne servent qu'à l'ÉTAT d'un
       indicateur. Elles ne sont jamais une quatrième couleur de série.
     · Dès deux séries, une légende est présente. Avec une seule série, pas
       de boîte de légende : c'est le titre qui la nomme.
     · Le texte porte les couleurs de texte des jetons, JAMAIS la couleur de
       la série ; l'identité vient d'une pastille colorée POSÉE À CÔTÉ.
     · Un tableau de valeurs accompagne toujours un graphique : il est
       intégré par `graphiqueLignes` et `barresComparees`, inutile d'en
       ajouter un second.
     · Chaque figure est décrite pour les lecteurs d'écran (role="img" +
       description donnant la tendance et la dernière valeur).
     · Aucune animation : ni transition, ni tracé progressif, ni compteur
       qui s'incrémente. Il n'y a donc rien à neutraliser sous
       `prefers-reduced-motion` — un graphique qui se dessine tout seul est
       un effet, pas une information, et la SPEC (§2) les bannit.

   -------------------------------------------------------------------------
   POURQUOI LES SVG SONT REDESSINÉS À CHAQUE REDIMENSIONNEMENT

   Un SVG mis à l'échelle par `viewBox` rétrécit aussi son texte : à 320 px
   de large, une étiquette de 12 unités tombe sous 6 px réels. On dessine
   donc à l'échelle 1:1 — une unité de `viewBox` = un pixel CSS — et on
   redessine quand la largeur disponible change. Les traits font alors
   vraiment 2 px et les étiquettes vraiment 12 px, à toutes les tailles.
   C'est aussi ce qui permet de mesurer les étiquettes AVANT de réserver
   les marges, donc de garantir qu'aucune ne sort du cadre.

   -------------------------------------------------------------------------
   CONTRAT DE CLASSES attendu des pages hôtes (index.html, pole.html)

   Le module ne pose que des classes et des attributs ; il n'écrit aucune
   valeur de style en dur. Les classes existantes de base.css et
   components.css font l'essentiel (`carte`, `badge`, `pile`, `rangee`,
   `texte-sm`, `visuellement-cache`…). Les classes ci-dessous lui sont
   propres et relèvent du <style> de la page hôte — le rendu reste correct
   et lisible sans elles, la géométrie des figures étant portée par le SVG.

     .ind-tuile  .ind-tuile__corps  .ind-tuile__valeur  .ind-tuile__unite
     .ind-tuile__mesures  .ind-tuile__spark  .ind-spark
     .ind-graphique  .ind-barres  .ind-graphique__entete
     .ind-graphique__titre  .ind-graphique__sous-titre
     .ind-graphique__trace  .ind-graphique__svg
     .ind-legende  .ind-legende__element
     .ind-donnees  .ind-donnees__resume  .ind-donnees__defilement
     .ind-tableau

   La seule exception à « aucun style en ligne » est la PEINTURE des formes
   SVG : `fill="var(--pole-etiia)"` n'est pas résolu par les navigateurs
   dans un attribut de présentation, il faut passer par la propriété
   `style`. Les valeurs posées sont exclusivement des `var(--…)` de
   tokens.css — aucune couleur littérale n'apparaît dans ce fichier.
   ========================================================================= */

import { el, svg, frag, monter, annoncer, rafThrottle } from './ui.js';

/* -------------------------------------------------------------------------
   0. Constantes de dessin

   Toutes en pixels CSS, puisque les SVG sont tracés à l'échelle 1:1.
   Ce sont des mesures de géométrie, pas des jetons de design : elles
   n'ont pas d'équivalent dans tokens.css et n'ont rien à y faire.
   ------------------------------------------------------------------------- */

/** Épaisseur d'une ligne de série. */
const TRAIT = 2;

/** Rayon d'un marqueur de fin : 4 px de rayon = 8 px de diamètre. */
const MARQUEUR = 4;

/** Anneau de couleur de surface autour des marqueurs, pour les décoller. */
const ANNEAU = 2;

/** Taille du texte des axes et des étiquettes directes. */
const TEXTE_AXE = 12;

/** Hauteur d'une ligne d'infobulle. */
const LIGNE_BULLE = 18;

/** Écart vertical minimal entre deux étiquettes de bout de ligne. */
const ECART_ETIQUETTES = 15;

/** Au-delà de ce nombre de séries, plus d'étiquetage direct : la légende suffit. */
const MAX_ETIQUETTES_DIRECTES = 4;

/** En deçà de cette largeur, les étiquettes directes mangeraient le tracé. */
const LARGEUR_MIN_ETIQUETTES = 520;

/** Largeur de repli quand le conteneur n'est pas encore mesurable. */
const LARGEUR_REPLI = 720;

/** Largeur plancher : en deçà, le tracé n'a plus de sens. */
const LARGEUR_MIN = 260;

/** Barres horizontales : hauteur de rangée et épaisseur de barre (≤ 24 px). */
const RANGEE_BARRE = 32;
const EPAISSEUR_BARRE = 20;

/* Une barre n'a pas besoin de toute la largeur d'un tableau de bord : au-delà
   d'une certaine longueur elle devient un ruban, et l'étiquette de valeur se
   retrouve à un écran de son libellé. On plafonne donc le tracé et on le
   laisse aligné à gauche, au lieu de l'étirer. */
const LARGEUR_MAX_BARRES = 640;

/** Rayon de l'extrémité arrondie d'une barre. */
const RAYON_BARRE = 4;

/** Écart minimal de surface entre deux barres adjacentes. */
const ECART_BARRES = 2;

/** Compteur d'identifiants, pour relier une figure à son titre et à son aide. */
let compteurId = 0;

/**
 * Identifiant unique et stable pour la durée de vie de la page.
 * @param {string} prefixe
 * @returns {string}
 */
function idUnique(prefixe) {
  compteurId += 1;
  return prefixe + '-' + compteurId;
}

/* -------------------------------------------------------------------------
   1. Formatage — nombres, mois, valeurs
   ------------------------------------------------------------------------- */

/**
 * Fabrique un formateur Intl, ou null si l'environnement n'en propose pas.
 * @param {object} options
 * @returns {Intl.NumberFormat|null}
 */
function formateurNombre(options) {
  try {
    return new Intl.NumberFormat('fr-FR', options);
  } catch (_e) {
    return null;
  }
}

const NOMBRE_1 = formateurNombre({ maximumFractionDigits: 1 });
const NOMBRE_SIGNE = formateurNombre({
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero'
});

/**
 * Nombre en français, une décimale au plus. Les entiers restent entiers.
 * @param {number} valeur
 * @returns {string}
 */
function formaterNombre(valeur) {
  if (!estNombre(valeur)) return '—';
  if (NOMBRE_1) return NOMBRE_1.format(valeur);
  return String(Math.round(valeur * 10) / 10).replace('.', ',');
}

/**
 * Nombre signé (« +2,3 », « −1,4 »), pour les variations.
 * @param {number} valeur
 * @returns {string}
 */
function formaterSigne(valeur) {
  if (!estNombre(valeur)) return '—';
  if (NOMBRE_SIGNE) return NOMBRE_SIGNE.format(valeur);
  const base = formaterNombre(Math.abs(valeur));
  if (valeur > 0) return '+' + base;
  if (valeur < 0) return '−' + base;
  return base;
}

/**
 * Valeur suivie de son unité, séparée par une espace fine insécable.
 * Une unité vide (nombre d'écarts) ne produit aucun suffixe.
 *
 * @param {number} valeur
 * @param {string} unite
 * @returns {string}
 */
function formaterValeur(valeur, unite) {
  const nombre = formaterNombre(valeur);
  return unite ? nombre + ' ' + unite : nombre;
}

/**
 * Unité d'un ÉCART entre deux valeurs. L'écart entre deux pourcentages
 * s'exprime en points, jamais en pourcents : « +2,3 pts », pas « +2,3 % »,
 * qui voudrait dire tout autre chose.
 *
 * @param {string} unite
 * @returns {string}
 */
function uniteEcart(unite) {
  return unite === '%' ? 'pts' : '';
}

/** Cache des libellés de mois : douze appels par figure, autant les garder. */
const CACHE_MOIS = new Map();

/**
 * Convertit « 2025-10 » en date UTC. Renvoie null si la forme ne colle pas.
 * @param {string} iso
 * @returns {Date|null}
 */
function dateDeMois(iso) {
  const correspondance = /^(\d{4})-(\d{1,2})/.exec(String(iso || ''));
  if (!correspondance) return null;
  const annee = Number(correspondance[1]);
  const mois = Number(correspondance[2]);
  if (!Number.isFinite(annee) || mois < 1 || mois > 12) return null;
  return new Date(Date.UTC(annee, mois - 1, 1));
}

/**
 * Libellé de mois. Renvoie la chaîne d'origine si elle n'est pas datable :
 * une donnée inattendue s'affiche telle quelle plutôt que de disparaître.
 *
 * @param {string} iso   par exemple « 2025-10 »
 * @param {boolean} long true : « octobre 2025 », false : « oct. 25 »
 * @returns {string}
 */
function formaterMois(iso, long) {
  const cle = (long ? 'L:' : 'C:') + iso;
  if (CACHE_MOIS.has(cle)) return CACHE_MOIS.get(cle);

  let sortie = String(iso == null ? '' : iso);
  const date = dateDeMois(iso);
  if (date) {
    try {
      sortie = new Intl.DateTimeFormat('fr-FR', {
        month: long ? 'long' : 'short',
        year: long ? 'numeric' : '2-digit',
        timeZone: 'UTC'
      }).format(date);
    } catch (_e) { /* on garde la chaîne d'origine */ }
  }

  CACHE_MOIS.set(cle, sortie);
  return sortie;
}

/* -------------------------------------------------------------------------
   2. Normalisation défensive des entrées

   Le module ne lève jamais d'exception pour une donnée malformée : une
   série absente devient une série vide, une valeur non numérique devient
   un trou dans la ligne. Un indicateur illisible vaut mieux qu'une page
   blanche (SPEC §3, contrat de données).
   ------------------------------------------------------------------------- */

/** Vrai pour un nombre fini exploitable. */
function estNombre(valeur) {
  return typeof valeur === 'number' && Number.isFinite(valeur);
}

/**
 * Normalise une série : tableau de nombres finis, `null` pour les trous.
 * @param {*} brut
 * @returns {Array<number|null>}
 */
function normaliserSerie(brut) {
  if (!Array.isArray(brut)) return [];
  return brut.map((valeur) => {
    const nombre = typeof valeur === 'string' ? Number(valeur) : valeur;
    return estNombre(nombre) ? nombre : null;
  });
}

/**
 * Normalise une liste de mois en chaînes.
 * @param {*} brut
 * @returns {string[]}
 */
function normaliserMois(brut) {
  if (!Array.isArray(brut)) return [];
  return brut.map((mois) => String(mois == null ? '' : mois));
}

/**
 * Normalise le bloc « definitions » de indicateurs.json.
 * @param {*} brut
 * @returns {{libelle:string, nom:string, aide:string, unite:string,
 *            cible:number|null, sens:string}}
 */
function normaliserDefinition(brut) {
  const source = (brut && typeof brut === 'object') ? brut : {};
  const sens = source.sens === 'bas' || source.sens === 'cible' ? source.sens : 'haut';
  return {
    libelle: String(source.libelle || source.nom || 'Indicateur'),
    nom: String(source.nom || source.libelle || 'Indicateur'),
    aide: String(source.aide || ''),
    unite: String(source.unite == null ? '' : source.unite),
    cible: estNombre(source.cible) ? source.cible : null,
    sens: sens
  };
}

/**
 * Normalise une série nommée du graphique multi-lignes.
 * La couleur est reprise telle quelle : elle appartient à l'entité, ce
 * module ne l'invente jamais et ne la dérive jamais d'un rang.
 *
 * @param {*} brut
 * @param {number} rang  utilisé UNIQUEMENT pour fabriquer une clé de repli
 * @returns {{cle:string, libelle:string, valeurs:Array<number|null>, couleur:string}}
 */
function normaliserSerieNommee(brut, rang) {
  const source = (brut && typeof brut === 'object') ? brut : {};
  const cle = String(source.cle || source.libelle || 'serie-' + rang);
  return {
    cle: cle,
    libelle: String(source.libelle || source.cle || cle),
    valeurs: normaliserSerie(source.valeurs),
    couleur: couleurSure(source.couleur)
  };
}

/**
 * Couleur de tracé sûre : une `var(--…)` de tokens.css, ou le gris de
 * service par défaut. Aucune couleur littérale ne peut entrer ici.
 *
 * @param {*} brut
 * @returns {string}
 */
function couleurSure(brut) {
  const valeur = String(brut == null ? '' : brut).trim();
  return /^var\(\s*--[a-z0-9-]+\s*\)$/i.test(valeur) ? valeur : 'var(--pole-etii)';
}

/** Dernière valeur non nulle d'une série, ou null. */
function derniereValeur(serie) {
  for (let i = serie.length - 1; i >= 0; i -= 1) {
    if (estNombre(serie[i])) return serie[i];
  }
  return null;
}

/** Index de la dernière valeur non nulle, ou −1. */
function dernierIndex(serie) {
  for (let i = serie.length - 1; i >= 0; i -= 1) {
    if (estNombre(serie[i])) return i;
  }
  return -1;
}

/** Première valeur non nulle d'une série, ou null. */
function premiereValeur(serie) {
  for (let i = 0; i < serie.length; i += 1) {
    if (estNombre(serie[i])) return serie[i];
  }
  return null;
}

/* -------------------------------------------------------------------------
   3. Échelle verticale

   Une seule échelle par figure, calculée sur TOUTES les séries affichées
   plus la cible : les lignes restent comparables entre elles et la cible
   est toujours dans le cadre.
   ------------------------------------------------------------------------- */

/**
 * Arrondit un pas d'échelle à une valeur « ronde » : 1, 2, 2.5, 5 ou 10
 * fois une puissance de dix. C'est ce qui donne des graduations lisibles
 * (80, 85, 90…) plutôt que 83,4 / 88,7.
 *
 * @param {number} brut
 * @returns {number}
 */
function pasRond(brut) {
  if (!estNombre(brut) || brut <= 0) return 1;
  const exposant = Math.floor(Math.log10(brut));
  const puissance = Math.pow(10, exposant);
  const mantisse = brut / puissance;
  let arrondie = 10;
  if (mantisse <= 1) arrondie = 1;
  else if (mantisse <= 2) arrondie = 2;
  else if (mantisse <= 2.5) arrondie = 2.5;
  else if (mantisse <= 5) arrondie = 5;
  return arrondie * puissance;
}

/**
 * Calcule le domaine vertical et ses graduations.
 *
 * @param {Array<Array<number|null>>} series  toutes les séries tracées
 * @param {number|null} cible
 * @param {boolean} depuisZero  true pour les barres : une barre part de 0,
 *                              sinon sa longueur ment sur la proportion
 * @returns {{min:number, max:number, graduations:number[]}}
 */
function echelleVerticale(series, cible, depuisZero) {
  const valeurs = [];
  for (const serie of series) {
    for (const valeur of serie) if (estNombre(valeur)) valeurs.push(valeur);
  }
  if (estNombre(cible)) valeurs.push(cible);

  if (!valeurs.length) return { min: 0, max: 1, graduations: [0, 1] };

  let bas = Math.min.apply(null, valeurs);
  let haut = Math.max.apply(null, valeurs);

  if (depuisZero) bas = Math.min(0, bas);

  let etendue = haut - bas;
  if (etendue <= 0) etendue = Math.max(1, Math.abs(haut) * 0.1);

  const marge = etendue * 0.12;
  haut += marge;
  if (!depuisZero) {
    bas -= marge;
    // Une mesure qui ne peut pas être négative ne descend pas sous zéro :
    // un axe qui passe dans les négatifs pour un compte d'écarts est faux.
    if (Math.min.apply(null, valeurs) >= 0 && bas < 0) bas = 0;
  }

  const pas = pasRond((haut - bas) / 4);
  const min = Math.floor(bas / pas) * pas;
  const max = Math.ceil(haut / pas) * pas;

  const graduations = [];
  // Le compteur entier évite l'accumulation d'erreur des flottants.
  const nombre = Math.round((max - min) / pas);
  for (let i = 0; i <= nombre; i += 1) {
    graduations.push(Math.round((min + i * pas) * 1000) / 1000);
  }

  return { min: min, max: max === min ? min + pas : max, graduations: graduations };
}

/* -------------------------------------------------------------------------
   4. Mesure de texte

   On ne peut pas mesurer un texte SVG avant de l'avoir inséré, et on a
   besoin de sa largeur AVANT de décider des marges. Cette approximation
   par classes de caractères est volontairement généreuse : elle surestime
   légèrement, ce qui réserve un peu trop de place plutôt que de couper une
   étiquette. La vérification visuelle a confirmé la marge de sécurité.
   ------------------------------------------------------------------------- */

/**
 * Largeur approchée d'un texte, en pixels.
 * @param {string} texte
 * @param {number} taille  taille de police en pixels
 * @returns {number}
 */
function largeurTexte(texte, taille) {
  const chaine = String(texte == null ? '' : texte);
  let unites = 0;
  for (const caractere of chaine) {
    if (' .,:;\'’·|!'.indexOf(caractere) >= 0) unites += 0.32;
    else if ('ijlt'.indexOf(caractere) >= 0) unites += 0.33;
    else if (caractere >= '0' && caractere <= '9') unites += 0.57;
    else if ('mwMW'.indexOf(caractere) >= 0) unites += 0.88;
    else if (caractere === caractere.toUpperCase()
             && caractere !== caractere.toLowerCase()) unites += 0.68;
    else unites += 0.54;
  }
  return unites * taille;
}

/** Largeur du plus long texte d'une liste. */
function largeurMax(textes, taille) {
  let maximum = 0;
  for (const texte of textes) maximum = Math.max(maximum, largeurTexte(texte, taille));
  return maximum;
}

/* -------------------------------------------------------------------------
   5. Primitives SVG

   Chaque forme tracée porte un `fill` explicite : un SVG sans `fill`
   hérite du noir, ce qui remplit les tracés de ligne en thème sombre.
   ------------------------------------------------------------------------- */

/**
 * Un trait droit.
 * @param {number} x1 @param {number} y1 @param {number} x2 @param {number} y2
 * @param {string} couleur  var(--…)
 * @param {number} [epaisseur]
 * @param {string} [pointilles]  valeur de stroke-dasharray
 * @returns {SVGElement}
 */
function trait(x1, y1, x2, y2, couleur, epaisseur, pointilles) {
  return svg('line', {
    x1: x1, y1: y1, x2: x2, y2: y2,
    fill: 'none',
    'stroke-width': epaisseur || 1,
    'stroke-dasharray': pointilles || null,
    'shape-rendering': (epaisseur || 1) <= 1 ? 'crispEdges' : null,
    style: { stroke: couleur }
  });
}

/**
 * Un texte d'axe ou d'étiquette. Le `fill` est toujours un jeton de TEXTE :
 * jamais la couleur d'une série.
 *
 * @param {number} x @param {number} y
 * @param {string} contenu
 * @param {object} options  { ancre, couleur, taille, graisse, ligneBase }
 * @returns {SVGElement}
 */
function texte(x, y, contenu, options) {
  const reglages = options || {};
  return svg('text', {
    x: x, y: y,
    'text-anchor': reglages.ancre || 'start',
    'dominant-baseline': reglages.ligneBase || 'central',
    'font-size': reglages.taille || TEXTE_AXE,
    style: {
      // `fill` et `font-weight` passent par `style` et non par un attribut :
      // un attribut de présentation SVG ne résout pas les `var(--…)`.
      fill: reglages.couleur || 'var(--texte-faible)',
      fontWeight: reglages.graisse || null,
      fontVariantNumeric: 'tabular-nums'
    }
  }, contenu);
}

/**
 * Un disque de série : la SEULE marque qui porte la couleur de l'entité.
 * L'anneau de surface le détache d'une ligne qu'il croiserait.
 *
 * @param {number} cx @param {number} cy @param {number} r
 * @param {string} couleur
 * @param {boolean} [avecAnneau]
 * @returns {SVGElement}
 */
function disque(cx, cy, r, couleur, avecAnneau) {
  return svg('circle', {
    cx: cx, cy: cy, r: r,
    'stroke-width': avecAnneau ? ANNEAU : null,
    style: {
      fill: couleur,
      stroke: avecAnneau ? 'var(--fond-eleve)' : 'none'
    }
  });
}

/**
 * Construit le `d` d'une polyligne en sautant les trous.
 * Une valeur manquante interrompt la ligne au lieu de la faire passer
 * tout droit par-dessus : un trou de donnée n'est pas une droite.
 *
 * @param {Array<number|null>} valeurs
 * @param {(i:number)=>number} px
 * @param {(v:number)=>number} py
 * @returns {string}
 */
function cheminSerie(valeurs, px, py) {
  const morceaux = [];
  let ouvert = false;
  for (let i = 0; i < valeurs.length; i += 1) {
    const valeur = valeurs[i];
    if (!estNombre(valeur)) { ouvert = false; continue; }
    const x = arrondi(px(i));
    const y = arrondi(py(valeur));
    morceaux.push((ouvert ? 'L' : 'M') + x + ' ' + y);
    ouvert = true;
  }
  return morceaux.join(' ');
}

/** Arrondi au dixième de pixel : des `d` courts et des tracés nets. */
function arrondi(valeur) {
  return Math.round(valeur * 10) / 10;
}

/** Contraint une valeur dans un intervalle. */
function borner(valeur, min, max) {
  if (max < min) return min;
  return Math.min(max, Math.max(min, valeur));
}

/**
 * Pastille SVG de légende : un disque coloré de 14 px, autoportant.
 * Aucune feuille de style n'est nécessaire pour qu'il s'affiche.
 *
 * @param {string} couleur
 * @returns {SVGElement}
 */
function pastilleSerie(couleur) {
  return svg('svg', {
    width: 14, height: 14, viewBox: '0 0 14 14',
    'aria-hidden': 'true', focusable: 'false'
  }, disque(7, 7, 5, couleur, false));
}

/* -------------------------------------------------------------------------
   6. Rendu responsive

   Le SVG est reconstruit à la largeur réelle du conteneur. On ne redessine
   que lorsque la largeur CHANGE : un ResizeObserver qui redessine à chaque
   notification entrerait en boucle et brûlerait le processeur, exactement
   ce que la SPEC reproche à l'ancienne version (§2).
   ------------------------------------------------------------------------- */

/**
 * Branche un dessinateur sur un conteneur redimensionnable.
 *
 * @param {HTMLElement} hote
 * @param {(largeur:number)=>SVGElement} dessiner
 */
function brancherRendu(hote, dessiner) {
  let derniereLargeur = 0;

  const rendre = (largeurBrute) => {
    const largeur = Math.max(LARGEUR_MIN, Math.round(largeurBrute) || 0);
    if (largeur === derniereLargeur) return;
    derniereLargeur = largeur;

    // Le redimensionnement ne doit pas voler le focus clavier : si le
    // tracé remplacé était focalisé, le nouveau le reprend.
    const avaitFocus = typeof document !== 'undefined'
      && hote.contains(document.activeElement);

    const nouveau = dessiner(largeur);
    monter(hote, nouveau);

    if (avaitFocus && nouveau && typeof nouveau.focus === 'function') {
      try { nouveau.focus(); } catch (_e) { /* ignoré */ }
    }
  };

  const mesurer = () => {
    const largeur = hote.clientWidth
      || (hote.parentElement ? hote.parentElement.clientWidth : 0)
      || LARGEUR_REPLI;
    rendre(largeur);
  };

  // Premier rendu immédiat : le conteneur n'est jamais vide, même avant
  // que l'observateur n'ait produit sa première mesure.
  mesurer();

  if (typeof ResizeObserver === 'function') {
    const observateur = new ResizeObserver((entrees) => {
      const entree = entrees && entrees[0];
      const largeur = entree && entree.contentRect
        ? entree.contentRect.width
        : hote.clientWidth;
      rendre(largeur);
    });
    try { observateur.observe(hote); } catch (_e) { /* ignoré */ }
  } else if (typeof window !== 'undefined') {
    window.addEventListener('resize', rafThrottle(mesurer));
  }
}

/* -------------------------------------------------------------------------
   7. Lecture d'un indicateur : état, écart, variation, description
   ------------------------------------------------------------------------- */

/**
 * Tolérance autour de la cible pour un indicateur de sens « cible »
 * (se rapprocher, ni au-dessus ni en dessous) : 5 % de la cible.
 * @param {number} cible
 * @returns {number}
 */
function toleranceCible(cible) {
  return Math.max(1, Math.abs(cible) * 0.05);
}

/**
 * Évalue l'état d'un indicateur par rapport à sa cible.
 *
 * Renvoie un libellé EXPLICITE en plus de la variante de couleur : la
 * pastille de la tuile est étiquetée, l'état n'est jamais porté par la
 * seule couleur.
 *
 * @param {number|null} valeur
 * @param {{cible:number|null, sens:string}} definition
 * @returns {{bon:boolean|null, variante:string, libelle:string}}
 */
function etatCible(valeur, definition) {
  const cible = definition.cible;
  if (!estNombre(valeur) || !estNombre(cible)) {
    return { bon: null, variante: 'badge--neutre', libelle: 'Sans cible' };
  }

  if (definition.sens === 'cible') {
    const dans = Math.abs(valeur - cible) <= toleranceCible(cible);
    return dans
      ? { bon: true, variante: 'badge--succes', libelle: 'Dans la cible' }
      : { bon: false, variante: 'badge--alerte', libelle: 'Hors cible' };
  }

  if (definition.sens === 'bas') {
    return valeur <= cible
      ? { bon: true, variante: 'badge--succes', libelle: 'Sous la cible' }
      : { bon: false, variante: 'badge--alerte', libelle: 'Au-dessus de la cible' };
  }

  return valeur >= cible
    ? { bon: true, variante: 'badge--succes', libelle: 'Au-dessus de la cible' }
    : { bon: false, variante: 'badge--alerte', libelle: 'Sous la cible' };
}

/**
 * Évalue la variation par rapport au mois précédent.
 * Le sens de lecture dépend de l'indicateur : pour « écarts ouverts », une
 * baisse est une bonne nouvelle. Pour un indicateur de sens « cible », une
 * variation n'est ni bonne ni mauvaise en soi : elle reste neutre.
 *
 * @param {Array<number|null>} serie
 * @param {{sens:string}} definition
 * @returns {{delta:number|null, fleche:string, variante:string, sens:string}}
 */
function variationMensuelle(serie, definition) {
  const index = dernierIndex(serie);
  let precedent = null;
  for (let i = index - 1; i >= 0; i -= 1) {
    if (estNombre(serie[i])) { precedent = serie[i]; break; }
  }

  if (index < 0 || !estNombre(precedent)) {
    return { delta: null, fleche: '', variante: 'badge--neutre', sens: 'stable' };
  }

  const delta = Math.round((serie[index] - precedent) * 1000) / 1000;
  if (delta === 0) {
    return { delta: 0, fleche: '→', variante: 'badge--neutre', sens: 'stable' };
  }

  const monte = delta > 0;
  const fleche = monte ? '▲' : '▼';
  const sens = monte ? 'en hausse' : 'en baisse';

  if (definition.sens === 'cible') {
    return { delta: delta, fleche: fleche, variante: 'badge--neutre', sens: sens };
  }

  const favorable = definition.sens === 'bas' ? !monte : monte;
  return {
    delta: delta,
    fleche: fleche,
    variante: favorable ? 'badge--succes' : 'badge--alerte',
    sens: sens
  };
}

/**
 * Description textuelle d'une série, pour les lecteurs d'écran.
 * Donne toujours la période, la tendance et la DERNIÈRE valeur.
 *
 * @param {string[]} mois
 * @param {Array<{libelle:string, valeurs:Array<number|null>}>} series
 * @param {{libelle:string, unite:string, cible:number|null}} definition
 * @returns {string}
 */
function decrire(mois, series, definition) {
  const phrases = [];
  const debut = mois.length ? formaterMois(mois[0], true) : null;
  const fin = mois.length ? formaterMois(mois[mois.length - 1], true) : null;

  phrases.push('Graphique de l’indicateur ' + definition.libelle
    + (definition.unite ? ', en ' + definition.unite : '') + '.');
  if (debut && fin) {
    phrases.push(mois.length + ' mois, de ' + debut + ' à ' + fin + '.');
  }

  for (const serie of series) {
    const premiere = premiereValeur(serie.valeurs);
    const derniere = derniereValeur(serie.valeurs);
    if (!estNombre(derniere)) {
      phrases.push(serie.libelle + ' : aucune valeur disponible.');
      continue;
    }
    let tendance = 'stable';
    if (estNombre(premiere)) {
      const ecart = derniere - premiere;
      const seuil = Math.max(Math.abs(premiere) * 0.01, 0.05);
      if (ecart > seuil) tendance = 'en hausse';
      else if (ecart < -seuil) tendance = 'en baisse';
    }
    phrases.push(serie.libelle + ' : ' + tendance
      + (estNombre(premiere) ? ', de ' + formaterNombre(premiere) : '')
      + ' à ' + formaterValeur(derniere, definition.unite)
      + ' au dernier mois.');
  }

  if (estNombre(definition.cible)) {
    phrases.push('Cible : ' + formaterValeur(definition.cible, definition.unite) + '.');
  }

  return phrases.join(' ');
}

/* =========================================================================
   8. sparkline — tracé compact, sans axe ni étiquette
   ========================================================================= */

/** Dimensions fixes de la vignette : elle est toujours dessinée en 1:1. */
const SPARK_LARGEUR = 132;
const SPARK_HAUTEUR = 36;
const SPARK_MARGE_X = 5;
const SPARK_MARGE_Y = 6;

/**
 * Trace une sparkline : la forme de la série, rien d'autre. Pas d'axe, pas
 * de graduation, pas d'étiquette — les chiffres sont à côté, dans la tuile.
 * Le dernier point est accentué, c'est lui que l'œil doit trouver.
 *
 * La cible n'est tracée que si elle tombe dans l'amplitude de la série :
 * une cible très éloignée écraserait la courbe sur une ligne plate et
 * détruirait l'information que la vignette est censée porter.
 *
 * @param {Array<number|null>} serie
 * @param {{couleur?:string, cible?:number}} [options]
 * @returns {SVGElement}
 */
export function sparkline(serie, options) {
  const reglages = options || {};
  const valeurs = normaliserSerie(serie);
  const couleur = couleurSure(reglages.couleur);
  const cible = estNombre(reglages.cible) ? reglages.cible : null;

  const racine = svg('svg', {
    class: 'ind-spark',
    width: SPARK_LARGEUR,
    height: SPARK_HAUTEUR,
    viewBox: '0 0 ' + SPARK_LARGEUR + ' ' + SPARK_HAUTEUR,
    role: 'img',
    focusable: 'false'
  });

  const connues = valeurs.filter(estNombre);
  if (!connues.length) {
    racine.setAttribute('aria-label', 'Aucune donnée d’évolution.');
    return racine;
  }

  let bas = Math.min.apply(null, connues);
  let haut = Math.max.apply(null, connues);
  if (haut - bas < 1e-9) { bas -= 0.5; haut += 0.5; }

  // La cible n'entre dans le domaine que si elle est déjà proche.
  if (estNombre(cible) && cible >= bas - (haut - bas) && cible <= haut + (haut - bas)) {
    bas = Math.min(bas, cible);
    haut = Math.max(haut, cible);
  }

  const x0 = SPARK_MARGE_X;
  const x1 = SPARK_LARGEUR - SPARK_MARGE_X;
  const y0 = SPARK_MARGE_Y;
  const y1 = SPARK_HAUTEUR - SPARK_MARGE_Y;

  const px = (i) => valeurs.length > 1
    ? x0 + (x1 - x0) * (i / (valeurs.length - 1))
    : (x0 + x1) / 2;
  const py = (v) => y1 - ((v - bas) / (haut - bas)) * (y1 - y0);

  const pieces = [];

  if (estNombre(cible) && cible >= bas && cible <= haut) {
    pieces.push(trait(x0, arrondi(py(cible)), x1, arrondi(py(cible)),
      'var(--bordure-forte)', 1, '3 3'));
  }

  pieces.push(svg('path', {
    d: cheminSerie(valeurs, px, py),
    fill: 'none',
    'stroke-width': 1.75,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    style: { stroke: couleur }
  }));

  const index = dernierIndex(valeurs);
  if (index >= 0) {
    pieces.push(disque(arrondi(px(index)), arrondi(py(valeurs[index])), 3, couleur, true));
  }

  const premiere = premiereValeur(valeurs);
  const derniere = derniereValeur(valeurs);
  racine.setAttribute('aria-label', 'Évolution sur ' + valeurs.length
    + ' mois, de ' + formaterNombre(premiere) + ' à ' + formaterNombre(derniere) + '.');

  monter(racine, pieces);
  return racine;
}

/* =========================================================================
   9. tuileIndicateur — la synthèse d'un indicateur
   ========================================================================= */

/**
 * Tuile de synthèse d'un indicateur : libellé, dernière valeur, unité,
 * écart à la cible, variation mensuelle et sparkline.
 *
 * L'état par rapport à la cible est porté par une pastille ÉTIQUETÉE
 * (« Au-dessus de la cible »), accompagnée d'un point coloré décoratif :
 * la couleur confirme, elle ne dit jamais seule.
 *
 * La tuile émet un `<h3>` : elle est conçue pour vivre dans une section
 * titrée par un `<h2>`.
 *
 * @param {object} options
 * @param {string} options.cle         clé de l'indicateur (otq, otd, …)
 * @param {object} options.definition  entrée du bloc « definitions »
 * @param {Array<number|null>} options.serie
 * @param {string[]} options.mois
 * @param {string} options.couleur     var(--pole-…) de l'entité mesurée
 * @returns {HTMLElement}
 */
export function tuileIndicateur(options) {
  const reglages = options || {};
  const definition = normaliserDefinition(reglages.definition);
  const serie = normaliserSerie(reglages.serie);
  const mois = normaliserMois(reglages.mois);
  const couleur = couleurSure(reglages.couleur);
  const cle = String(reglages.cle || definition.libelle);

  const index = dernierIndex(serie);
  const valeur = index >= 0 ? serie[index] : null;
  const etat = etatCible(valeur, definition);
  const variation = variationMensuelle(serie, definition);
  const moisCourant = index >= 0 && mois[index] ? formaterMois(mois[index], true) : null;

  const idTitre = idUnique('ind-tuile-' + cle.replace(/[^a-z0-9-]/gi, ''));

  /* --- En-tête : libellé + pastille d'état ------------------------------ */

  /* `carte__entete` place déjà le titre à gauche et le badge à droite, et
     renvoie le sous-titre à la ligne : aucune classe supplémentaire ici. */
  const entete = el('div', { class: 'carte__entete' },
    el('h3', { class: 'carte__titre', id: idTitre },
      definition.libelle,
      definition.nom && definition.nom !== definition.libelle
        ? el('span', { class: 'visuellement-cache' }, ', ' + definition.nom)
        : null
    ),
    el('span', { class: ['badge', etat.variante] },
      el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
      etat.libelle
    ),
    definition.aide
      ? el('p', { class: 'carte__sous-titre mesure' }, definition.aide)
      : null
  );

  /* --- Valeur du dernier mois ------------------------------------------- */

  const valeurAffichee = estNombre(valeur)
    ? el('p', { class: 'ind-tuile__valeur sans-marge' },
        el('strong', null, formaterNombre(valeur)),
        definition.unite
          ? el('span', { class: 'ind-tuile__unite texte-doux' }, ' ' + definition.unite)
          : null
      )
    : el('p', { class: 'ind-tuile__valeur sans-marge texte-doux' },
        el('strong', null, '—'));

  /* --- Écart à la cible et variation ------------------------------------ */

  const mesures = el('ul', { class: 'pile pile--serree ind-tuile__mesures texte-sm' });

  if (estNombre(definition.cible)) {
    const ecart = estNombre(valeur)
      ? Math.round((valeur - definition.cible) * 1000) / 1000
      : null;
    const unite = uniteEcart(definition.unite);
    mesures.append(el('li', { class: 'rangee rangee--serree' },
      el('span', { class: 'texte-faible' }, 'Cible'),
      el('span', { class: 'mono' }, formaterValeur(definition.cible, definition.unite)),
      estNombre(ecart)
        ? el('span', { class: 'texte-doux' },
            '(' + formaterSigne(ecart) + (unite ? ' ' + unite : '') + ')')
        : null
    ));
  }

  if (estNombre(variation.delta)) {
    const unite = uniteEcart(definition.unite);
    mesures.append(el('li', { class: 'rangee rangee--serree' },
      el('span', { class: 'texte-faible' }, 'Sur un mois'),
      el('span', { class: ['badge', 'badge--contour', variation.variante] },
        el('span', { 'aria-hidden': 'true' }, variation.fleche),
        formaterSigne(variation.delta) + (unite ? ' ' + unite : ''),
        el('span', { class: 'visuellement-cache' }, ', ' + variation.sens)
      )
    ));
  }

  /* --- Vignette d'évolution --------------------------------------------- */

  const vignette = sparkline(serie, { couleur: couleur, cible: definition.cible });
  vignette.classList.add('ind-tuile__spark');

  return el('article', {
    class: 'carte carte--compacte ind-tuile',
    'aria-labelledby': idTitre,
    dataset: { indicateur: cle }
  },
    entete,
    // `carte__corps` est une pile verticale : ici on veut chiffre et
    // vignette côte à côte, donc une `rangee` qui s'enroule sur mobile.
    el('div', { class: 'rangee rangee--entre rangee--haut ind-tuile__corps' },
      el('div', { class: 'pile pile--serree' },
        valeurAffichee,
        moisCourant
          ? el('p', { class: 'texte-xs texte-faible sans-marge' }, moisCourant)
          : null,
        mesures
      ),
      vignette
    )
  );
}

/* =========================================================================
   10. tableauSeries — la même donnée, en lisible
   ========================================================================= */

/**
 * Vue tabulaire d'un jeu de séries mensuelles, repliée dans un `<details>`.
 *
 * C'est le filet de sécurité de toute cette page : aucune information
 * n'existe UNIQUEMENT dans un graphique. Un lecteur d'écran, un rendu sans
 * SVG, une impression en noir et blanc — le tableau reste.
 *
 * @param {object} options
 * @param {string[]} options.mois
 * @param {Array<{cle:string, libelle:string, valeurs:Array<number|null>, couleur:string}>} options.series
 * @param {object} options.definition
 * @returns {HTMLElement}  un élément <details>
 */
export function tableauSeries(options) {
  const reglages = options || {};
  const definition = normaliserDefinition(reglages.definition);
  const mois = normaliserMois(reglages.mois);
  const series = Array.isArray(reglages.series)
    ? reglages.series.map(normaliserSerieNommee)
    : [];

  const suffixe = definition.unite ? ' (' + definition.unite + ')' : '';

  const enTetes = [el('th', { scope: 'col' }, 'Mois')];
  for (const serie of series) {
    enTetes.push(el('th', { scope: 'col' },
      el('span', { class: 'rangee rangee--serree' },
        pastilleSerie(serie.couleur),
        el('span', null, serie.libelle + suffixe)
      )
    ));
  }

  const lignes = mois.map((etiquette, i) => el('tr', null,
    el('th', { scope: 'row' }, formaterMois(etiquette, true)),
    series.map((serie) => {
      const valeur = serie.valeurs[i];
      return el('td', { class: 'mono' },
        estNombre(valeur) ? formaterNombre(valeur) : '—');
    })
  ));

  const legende = [
    definition.aide,
    estNombre(definition.cible)
      ? 'Cible : ' + formaterValeur(definition.cible, definition.unite) + '.'
      : ''
  ].filter(Boolean).join(' ');

  return el('details', { class: 'ind-donnees' },
    el('summary', { class: 'ind-donnees__resume' },
      'Voir les valeurs — ' + definition.libelle),
    el('div', { class: 'ind-donnees__defilement' },
      el('table', { class: 'ind-tableau texte-sm' },
        el('caption', { class: 'texte-sm texte-doux' },
          definition.nom + suffixe + (legende ? '. ' + legende : '')),
        el('thead', null, el('tr', null, enTetes)),
        el('tbody', null, lignes)
      )
    )
  );
}

/* =========================================================================
   11. graphiqueLignes — le suivi mensuel
   ========================================================================= */

/**
 * Graphique de suivi mensuel, une ligne par série.
 *
 * UNE SEULE échelle verticale, commune à toutes les séries. Si un jour
 * deux mesures d'unités différentes devaient cohabiter, ce serait deux
 * appels à cette fonction, jamais un second axe.
 *
 * La figure inclut déjà sa légende (dès deux séries) et son tableau de
 * valeurs : il est inutile d'appeler `tableauSeries` en plus.
 *
 * @param {object} options
 * @param {string[]} options.mois
 * @param {Array<{cle:string, libelle:string, valeurs:Array<number|null>, couleur:string}>} options.series
 * @param {object} options.definition
 * @param {string} [options.titre]
 * @param {string} [options.description]  description lue par les lecteurs d'écran
 * @returns {HTMLElement}
 */
export function graphiqueLignes(options) {
  const reglages = options || {};
  const definition = normaliserDefinition(reglages.definition);
  const mois = normaliserMois(reglages.mois);
  const series = (Array.isArray(reglages.series) ? reglages.series : [])
    .map(normaliserSerieNommee)
    .filter((serie) => serie.valeurs.length > 0);

  const titre = String(reglages.titre || definition.nom || definition.libelle);
  const description = String(reglages.description || decrire(mois, series, definition));

  const idTitre = idUnique('ind-graphe-titre');
  const idAide = idUnique('ind-graphe-aide');

  const hote = el('div', { class: 'ind-graphique__trace' });
  const vide = !series.length || !mois.length;
  const sousTitre = sousTitreFigure(definition, mois);

  const figure = el('figure', {
    class: 'ind-graphique pile',
    role: 'group',
    'aria-labelledby': idTitre
  },
    el('figcaption', { class: 'ind-graphique__entete pile pile--serree' },
      el('p', { class: 'ind-graphique__titre gras sans-marge', id: idTitre }, titre),
      sousTitre
        ? el('p', { class: 'ind-graphique__sous-titre texte-sm texte-doux sans-marge mesure' },
            sousTitre)
        : null
    ),
    // Dès deux séries, la légende est présente : l'identité ne dépend
    // jamais du seul appariement de couleurs.
    series.length >= 2 ? legende(series) : null,
    hote,
    vide ? null : el('p', { class: 'visuellement-cache', id: idAide },
      'Graphique interactif. Au clavier, utilisez les flèches gauche et droite '
      + 'pour parcourir les mois, Échap pour quitter la lecture. '
      + 'Le tableau qui suit contient les mêmes valeurs.'),
    // Un tableau sans ligne n'apprend rien : l'état vide se suffit.
    vide ? null : tableauSeries({ mois: mois, series: series, definition: definition })
  );

  if (vide) {
    monter(hote, el('p', { class: 'texte-sm texte-doux' },
      'Aucune valeur à représenter pour cet indicateur.'));
    return figure;
  }

  brancherRendu(hote, (largeur) => dessinerLignes({
    largeur: largeur,
    mois: mois,
    series: series,
    definition: definition,
    description: description,
    idAide: idAide
  }));

  return figure;
}

/**
 * Sous-titre commun aux figures : unité, période et cible, en clair.
 * @param {object} definition
 * @param {string[]} mois
 * @returns {string}
 */
function sousTitreFigure(definition, mois) {
  const morceaux = [];
  if (definition.unite) morceaux.push('En ' + definition.unite);
  if (mois.length >= 2) {
    morceaux.push(formaterMois(mois[0], true) + ' – ' + formaterMois(mois[mois.length - 1], true));
  }
  if (estNombre(definition.cible)) {
    morceaux.push('cible ' + formaterValeur(definition.cible, definition.unite));
  }
  const phrase = morceaux.join(' · ');
  return phrase ? phrase.charAt(0).toUpperCase() + phrase.slice(1) : '';
}

/**
 * Légende : une pastille colorée + un libellé en couleur de texte.
 * @param {Array<{libelle:string, couleur:string}>} series
 * @returns {HTMLElement}
 */
function legende(series) {
  return el('ul', {
    class: 'rangee rangee--serree ind-legende',
    'aria-label': 'Légende des séries'
  },
    series.map((serie) => el('li', { class: 'rangee rangee--serree ind-legende__element' },
      pastilleSerie(serie.couleur),
      el('span', { class: 'texte-sm' }, serie.libelle)
    ))
  );
}

/**
 * Dessine le graphique de lignes à une largeur donnée, en 1:1.
 *
 * @param {object} ctx
 * @returns {SVGElement}
 */
function dessinerLignes(ctx) {
  const { largeur, mois, series, definition, description, idAide } = ctx;

  const nb = mois.length;
  const echelle = echelleVerticale(series.map((s) => s.valeurs), definition.cible, false);

  /* --- Marges : elles découlent de la MESURE des étiquettes ------------- */

  const textesGrad = echelle.graduations.map(formaterNombre);
  const gauche = Math.ceil(largeurMax(textesGrad, TEXTE_AXE)) + 14;

  // Étiquetage direct tant qu'il y a au plus quatre séries ET que le tracé
  // garde une largeur utile. En dessous, la légende porte seule l'identité.
  const directes = series.length <= MAX_ETIQUETTES_DIRECTES
    && largeur >= LARGEUR_MIN_ETIQUETTES;

  const textesBout = series.map((serie) => {
    const derniere = derniereValeur(serie.valeurs);
    return serie.libelle + (estNombre(derniere) ? ' ' + formaterNombre(derniere) : '');
  });

  const DECALAGE_PASTILLE = 22;
  const DECALAGE_TEXTE = 32;
  const droite = directes
    ? DECALAGE_TEXTE + Math.ceil(largeurMax(textesBout, TEXTE_AXE)) + 10
    : 14;

  const haut = 16;
  const bas = 32;
  const hauteurTrace = Math.round(borner(largeur * 0.42, 170, 280));
  const hauteur = haut + hauteurTrace + bas;

  const x0 = gauche;
  const x1 = Math.max(gauche + 40, largeur - droite);
  const y0 = haut;
  const y1 = haut + hauteurTrace;

  const px = (i) => nb > 1 ? x0 + (x1 - x0) * (i / (nb - 1)) : (x0 + x1) / 2;
  const py = (v) => y1 - ((v - echelle.min) / (echelle.max - echelle.min)) * hauteurTrace;

  const racine = svg('svg', {
    class: 'ind-graphique__svg',
    width: largeur,
    height: hauteur,
    viewBox: '0 0 ' + largeur + ' ' + hauteur,
    role: 'img',
    tabindex: '0',
    'aria-label': description,
    'aria-describedby': idAide
  });

  /* --- Grille et axes, en retrait --------------------------------------- */

  const fond = svg('g', { 'aria-hidden': 'true' });
  for (const graduation of echelle.graduations) {
    const y = Math.round(py(graduation)) + 0.5;
    fond.append(trait(x0, y, x1, y, 'var(--bordure-douce)', 1));
    fond.append(texte(x0 - 8, py(graduation), formaterNombre(graduation), {
      ancre: 'end', couleur: 'var(--texte-faible)'
    }));
  }
  fond.append(trait(x0, Math.round(y1) + 0.5, x1, Math.round(y1) + 0.5,
    'var(--bordure)', 1));

  /* --- Étiquettes de mois : une sur n, la dernière toujours ------------- */

  const textesMois = mois.map((m) => formaterMois(m, false));
  const largeurMois = Math.max(28, largeurMax(textesMois, TEXTE_AXE - 1));
  const tenables = Math.max(2, Math.floor((x1 - x0) / (largeurMois + 16)) + 1);
  const pas = Math.max(1, Math.ceil((nb - 1) / Math.max(1, tenables - 1)));

  for (let i = nb - 1; i >= 0; i -= pas) {
    const demi = largeurTexte(textesMois[i], TEXTE_AXE - 1) / 2;
    fond.append(texte(borner(px(i), demi + 2, largeur - demi - 2), y1 + 16,
      textesMois[i], { ancre: 'middle', taille: TEXTE_AXE - 1 }));
  }

  /* --- Repère de cible : le TRAIT passe derrière les lignes -------------- */

  const cibleVisible = estNombre(definition.cible)
    && definition.cible >= echelle.min && definition.cible <= echelle.max;

  if (cibleVisible) {
    const yCible = arrondi(py(definition.cible));
    fond.append(trait(x0, yCible, x1, yCible, 'var(--bordure-forte)', 1, '5 4'));
  }

  racine.append(fond);

  /* --- Les lignes ------------------------------------------------------- */

  const traces = svg('g', { 'aria-hidden': 'true' });
  for (const serie of series) {
    traces.append(svg('path', {
      d: cheminSerie(serie.valeurs, px, py),
      fill: 'none',
      'stroke-width': TRAIT,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      style: { stroke: serie.couleur }
    }));
  }
  for (const serie of series) {
    const index = dernierIndex(serie.valeurs);
    if (index >= 0) {
      traces.append(disque(arrondi(px(index)), arrondi(py(serie.valeurs[index])),
        MARQUEUR, serie.couleur, true));
    }
  }
  racine.append(traces);

  /* --- ... mais l'ÉTIQUETTE de cible passe devant ------------------------
     Sans cela une ligne de série la traverserait et la rendrait illisible.
     Le cartouche opaque est donc posé après les tracés.                    */

  if (cibleVisible) {
    const yCible = arrondi(py(definition.cible));
    // Le cartouche est opaque : sur un tracé étroit il masquerait plusieurs
    // mois. On l'abrège alors — la période et la cible restent en toutes
    // lettres dans le sous-titre et dans le tableau.
    const complet = 'Cible ' + formaterValeur(definition.cible, definition.unite);
    const libelle = largeurTexte(complet, TEXTE_AXE - 1) <= (x1 - x0) * 0.3
      ? complet
      : 'Cible';
    const largeurLibelle = largeurTexte(libelle, TEXTE_AXE - 1);
    // Au-dessus de la ligne, sauf si l'on toucherait le bord haut du tracé.
    const yLibelle = yCible - 11 > y0 + 8 ? yCible - 11 : yCible + 12;

    racine.append(svg('g', { 'aria-hidden': 'true' },
      svg('rect', {
        x: x0 + 4, y: yLibelle - 8,
        width: arrondi(largeurLibelle + 10), height: 16,
        rx: 4,
        'stroke-width': 1,
        style: { fill: 'var(--fond-eleve)', stroke: 'var(--bordure-douce)' }
      }),
      texte(x0 + 9, yLibelle, libelle, {
        taille: TEXTE_AXE - 1, couleur: 'var(--texte-doux)'
      })
    ));
  }

  /* --- Étiquetage direct en bout de ligne ------------------------------- */

  if (directes) {
    const bouts = series
      .map((serie, rang) => {
        const index = dernierIndex(serie.valeurs);
        if (index < 0) return null;
        return {
          y: py(serie.valeurs[index]),
          yEtiquette: py(serie.valeurs[index]),
          xFin: px(index),
          couleur: serie.couleur,
          texte: textesBout[rang]
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);

    // Écartement : on pousse vers le bas, puis on retasse vers le haut si
    // la pile a débordé. Les étiquettes ne se chevauchent jamais, et la
    // ligne de rappel dit laquelle appartient à quelle courbe.
    for (let i = 1; i < bouts.length; i += 1) {
      bouts[i].yEtiquette = Math.max(bouts[i].yEtiquette,
        bouts[i - 1].yEtiquette + ECART_ETIQUETTES);
    }
    for (let i = bouts.length - 2; i >= 0; i -= 1) {
      bouts[i].yEtiquette = Math.min(bouts[i].yEtiquette,
        bouts[i + 1].yEtiquette - ECART_ETIQUETTES);
    }
    for (const bout of bouts) {
      bout.yEtiquette = borner(bout.yEtiquette, y0 + 7, y1 - 2);
    }

    const groupe = svg('g', { 'aria-hidden': 'true' });
    for (const bout of bouts) {
      groupe.append(svg('path', {
        d: 'M' + arrondi(bout.xFin + MARQUEUR + 2) + ' ' + arrondi(bout.y)
           + ' L' + arrondi(x1 + DECALAGE_PASTILLE - 6) + ' ' + arrondi(bout.yEtiquette),
        fill: 'none',
        'stroke-width': 1,
        style: { stroke: 'var(--bordure-forte)' }
      }));
      // La pastille porte la couleur ; le texte reste en encre.
      groupe.append(disque(x1 + DECALAGE_PASTILLE, arrondi(bout.yEtiquette),
        3.5, bout.couleur, false));
      groupe.append(texte(x1 + DECALAGE_TEXTE, arrondi(bout.yEtiquette), bout.texte, {
        couleur: 'var(--texte-doux)'
      }));
    }
    racine.append(groupe);
  }

  /* --- Survol : repère vertical et infobulle ---------------------------- */

  const survol = svg('g', { 'aria-hidden': 'true', 'pointer-events': 'none' });
  racine.append(survol);

  let indexActif = -1;

  const effacer = () => {
    if (indexActif === -1) return;
    indexActif = -1;
    monter(survol);
  };

  const montrer = (index, avecAnnonce) => {
    const borne = borner(Math.round(index), 0, nb - 1);
    if (borne === indexActif) return;
    indexActif = borne;
    monter(survol, bulleSurvol({
      index: borne, mois: mois, series: series, definition: definition,
      px: px, py: py, x0: x0, x1: x1, y0: y0, y1: y1, largeur: largeur
    }));
    if (avecAnnonce) annoncer(texteSurvol(borne, mois, series, definition));
  };

  const indexDepuisX = (x) => {
    if (nb <= 1) return 0;
    const ratio = (x - x0) / Math.max(1, x1 - x0);
    return borner(Math.round(ratio * (nb - 1)), 0, nb - 1);
  };

  racine.addEventListener('pointermove', (evenement) => {
    const cadre = racine.getBoundingClientRect();
    if (!cadre.width) return;
    // Le SVG est dessiné en 1:1 : l'abscisse écran EST l'abscisse du tracé.
    montrer(indexDepuisX(evenement.clientX - cadre.left), false);
  });
  racine.addEventListener('pointerleave', effacer);
  racine.addEventListener('blur', effacer);

  racine.addEventListener('keydown', (evenement) => {
    const touche = evenement.key;
    if (touche === 'ArrowRight' || touche === 'ArrowUp') {
      evenement.preventDefault();
      montrer(indexActif < 0 ? 0 : indexActif + 1, true);
    } else if (touche === 'ArrowLeft' || touche === 'ArrowDown') {
      evenement.preventDefault();
      montrer(indexActif < 0 ? nb - 1 : indexActif - 1, true);
    } else if (touche === 'Home') {
      evenement.preventDefault();
      montrer(0, true);
    } else if (touche === 'End') {
      evenement.preventDefault();
      montrer(nb - 1, true);
    } else if (touche === 'Escape') {
      effacer();
    }
  });

  return racine;
}

/**
 * Texte lu par les lecteurs d'écran lors d'un déplacement au clavier.
 * @returns {string}
 */
function texteSurvol(index, mois, series, definition) {
  const morceaux = [formaterMois(mois[index], true)];
  for (const serie of series) {
    const valeur = serie.valeurs[index];
    morceaux.push(serie.libelle + ' ' + (estNombre(valeur)
      ? formaterValeur(valeur, definition.unite)
      : 'valeur manquante'));
  }
  return morceaux.join(', ') + '.';
}

/**
 * Construit le repère vertical et l'infobulle d'un mois.
 *
 * L'infobulle est dessinée DANS le SVG plutôt qu'en HTML positionné : elle
 * est ainsi toujours dans le cadre, sans dépendre d'une règle de style de
 * la page hôte, et ne peut pas déborder du conteneur.
 *
 * @param {object} ctx
 * @returns {DocumentFragment}
 */
function bulleSurvol(ctx) {
  const { index, mois, series, definition, px, py, x0, x1, y0, y1, largeur } = ctx;

  const x = arrondi(px(index));
  const pieces = [trait(x, y0, x, y1, 'var(--bordure-forte)', 1)];

  const visibles = [];
  for (const serie of series) {
    const valeur = serie.valeurs[index];
    if (!estNombre(valeur)) continue;
    visibles.push({ serie: serie, valeur: valeur, y: py(valeur) });
    pieces.push(disque(x, arrondi(py(valeur)), MARQUEUR + 0.5, serie.couleur, true));
  }

  /* --- Géométrie de la boîte, calculée sur la MESURE des textes --------- */

  const enTete = formaterMois(mois[index], true);
  const MARGE = 9;
  const PASTILLE = 16;
  const ESPACE = 14;

  let corpsLargeur = largeurTexte(enTete, TEXTE_AXE);
  const lignes = (visibles.length ? visibles : series.map((serie) => ({
    serie: serie, valeur: null
  }))).map((entree) => {
    const valeur = estNombre(entree.valeur)
      ? formaterValeur(entree.valeur, definition.unite)
      : '—';
    corpsLargeur = Math.max(corpsLargeur,
      PASTILLE + largeurTexte(entree.serie.libelle, TEXTE_AXE)
      + ESPACE + largeurTexte(valeur, TEXTE_AXE));
    return { serie: entree.serie, valeur: valeur };
  });

  const boiteLargeur = Math.ceil(corpsLargeur) + MARGE * 2;
  const boiteHauteur = MARGE * 2 + LIGNE_BULLE * (lignes.length + 1);

  // À droite du repère si la place y est, à gauche sinon ; jamais hors cadre.
  let boiteX = x + 14;
  if (boiteX + boiteLargeur > largeur - 4) boiteX = x - 14 - boiteLargeur;
  boiteX = borner(boiteX, 4, Math.max(4, largeur - boiteLargeur - 4));

  // En haut ou en bas selon l'endroit où se concentrent les points, pour
  // masquer le moins de donnée possible.
  const moyenne = visibles.length
    ? visibles.reduce((somme, v) => somme + v.y, 0) / visibles.length
    : (y0 + y1) / 2;
  const boiteY = moyenne > (y0 + y1) / 2 ? y0 + 4 : y1 - boiteHauteur - 4;

  pieces.push(svg('rect', {
    x: boiteX, y: boiteY, width: boiteLargeur, height: boiteHauteur,
    rx: 8,
    'stroke-width': 1,
    style: { fill: 'var(--fond-eleve)', stroke: 'var(--bordure-forte)' }
  }));

  pieces.push(texte(boiteX + MARGE, boiteY + MARGE + LIGNE_BULLE / 2, enTete, {
    couleur: 'var(--texte)', graisse: 'var(--graisse-forte)'
  }));

  lignes.forEach((ligne, rang) => {
    const y = boiteY + MARGE + LIGNE_BULLE * (rang + 1) + LIGNE_BULLE / 2;
    pieces.push(disque(boiteX + MARGE + 4, y, 4, ligne.serie.couleur, false));
    pieces.push(texte(boiteX + MARGE + PASTILLE, y, ligne.serie.libelle, {
      couleur: 'var(--texte-doux)'
    }));
    pieces.push(texte(boiteX + boiteLargeur - MARGE, y, ligne.valeur, {
      ancre: 'end', couleur: 'var(--texte)'
    }));
  });

  return frag(pieces);
}

/* =========================================================================
   12. barresComparees — les trois pôles sur un indicateur
   ========================================================================= */

/**
 * Barres horizontales comparant des entités sur un même indicateur.
 *
 * Les barres partent de la LIGNE DE BASE (zéro) : une barre tronquée
 * exagère les écarts et ment sur la proportion. Le repère de cible donne
 * la lecture fine que la troncature aurait donnée, sans la déformation.
 *
 * La figure inclut déjà son tableau de valeurs.
 *
 * @param {object} options
 * @param {string[]} options.categories  libellés des entités comparées
 * @param {Array<number|null>} options.valeurs
 * @param {string[]} options.couleurs    var(--pole-…), une par catégorie
 * @param {object} options.definition
 * @param {string} [options.titre]
 * @returns {HTMLElement}
 */
export function barresComparees(options) {
  const reglages = options || {};
  const definition = normaliserDefinition(reglages.definition);
  const categories = (Array.isArray(reglages.categories) ? reglages.categories : [])
    .map((categorie) => String(categorie == null ? '' : categorie));
  const valeurs = normaliserSerie(reglages.valeurs);
  const couleursBrutes = Array.isArray(reglages.couleurs) ? reglages.couleurs : [];
  // La couleur reste attachée à la CATÉGORIE : c'est l'appelant qui la
  // fournit, position par position. Aucun cycle de palette ici.
  const couleurs = categories.map((_c, i) => couleurSure(couleursBrutes[i]));

  const titre = String(reglages.titre
    || (definition.nom + ' par pôle'));

  const idTitre = idUnique('ind-barres-titre');
  const hote = el('div', { class: 'ind-graphique__trace' });
  const sousTitre = sousTitreFigure(definition, []);

  const figure = el('figure', {
    class: 'ind-graphique ind-barres pile',
    role: 'group',
    'aria-labelledby': idTitre
  },
    el('figcaption', { class: 'ind-graphique__entete pile pile--serree' },
      el('p', { class: 'ind-graphique__titre gras sans-marge', id: idTitre }, titre),
      sousTitre
        ? el('p', { class: 'ind-graphique__sous-titre texte-sm texte-doux sans-marge mesure' },
            sousTitre)
        : null
    ),
    hote,
    categories.length
      ? tableauComparaison(categories, valeurs, couleurs, definition)
      : null
  );

  if (!categories.length) {
    monter(hote, el('p', { class: 'texte-sm texte-doux' },
      'Aucune valeur à comparer pour cet indicateur.'));
    return figure;
  }

  const description = descriptionBarres(categories, valeurs, definition);

  brancherRendu(hote, (largeur) => dessinerBarres({
    largeur: largeur,
    categories: categories,
    valeurs: valeurs,
    couleurs: couleurs,
    definition: definition,
    description: description
  }));

  return figure;
}

/**
 * Description textuelle de la comparaison, pour les lecteurs d'écran.
 * @returns {string}
 */
function descriptionBarres(categories, valeurs, definition) {
  const morceaux = ['Comparaison de ' + definition.libelle
    + (definition.unite ? ', en ' + definition.unite : '')
    + ', entre ' + categories.length + ' entités.'];
  categories.forEach((categorie, i) => {
    morceaux.push(categorie + ' : ' + (estNombre(valeurs[i])
      ? formaterValeur(valeurs[i], definition.unite)
      : 'valeur manquante') + '.');
  });
  if (estNombre(definition.cible)) {
    morceaux.push('Cible : ' + formaterValeur(definition.cible, definition.unite) + '.');
  }
  return morceaux.join(' ');
}

/**
 * Tableau d'accompagnement d'une comparaison ponctuelle.
 * @returns {HTMLElement}
 */
function tableauComparaison(categories, valeurs, couleurs, definition) {
  const suffixe = definition.unite ? ' (' + definition.unite + ')' : '';

  return el('details', { class: 'ind-donnees' },
    el('summary', { class: 'ind-donnees__resume' },
      'Voir les valeurs — ' + definition.libelle),
    el('div', { class: 'ind-donnees__defilement' },
      el('table', { class: 'ind-tableau texte-sm' },
        el('caption', { class: 'texte-sm texte-doux' },
          definition.nom + suffixe
          + (estNombre(definition.cible)
            ? '. Cible : ' + formaterValeur(definition.cible, definition.unite) + '.'
            : '')),
        el('thead', null, el('tr', null,
          el('th', { scope: 'col' }, 'Pôle'),
          el('th', { scope: 'col' }, definition.libelle + suffixe),
          estNombre(definition.cible)
            ? el('th', { scope: 'col' }, 'Écart à la cible'
                + (uniteEcart(definition.unite) ? ' (pts)' : ''))
            : null
        )),
        el('tbody', null, categories.map((categorie, i) => {
          const valeur = valeurs[i];
          return el('tr', null,
            el('th', { scope: 'row' },
              el('span', { class: 'rangee rangee--serree' },
                pastilleSerie(couleurs[i]),
                el('span', null, categorie))),
            el('td', { class: 'mono' },
              estNombre(valeur) ? formaterNombre(valeur) : '—'),
            estNombre(definition.cible)
              ? el('td', { class: 'mono' }, estNombre(valeur)
                  ? formaterSigne(Math.round((valeur - definition.cible) * 1000) / 1000)
                  : '—')
              : null
          );
        }))
      )
    )
  );
}

/**
 * Chemin d'une barre horizontale : extrémité arrondie côté valeur, carrée
 * côté ligne de base. La barre ne « flotte » jamais.
 *
 * @param {number} xBase @param {number} xFin @param {number} y @param {number} h
 * @returns {string}
 */
function cheminBarre(xBase, xFin, y, h) {
  // `sens` vaut 1 vers la droite, −1 vers la gauche : une valeur négative
  // produit la même barre, miroir, arrondie du bon côté.
  const sens = xFin >= xBase ? 1 : -1;
  const longueur = Math.abs(xFin - xBase);
  const r = Math.min(RAYON_BARRE, longueur, h / 2);
  const haut = arrondi(y);
  const basY = arrondi(y + h);
  const debut = arrondi(xBase);
  const fin = arrondi(xBase + sens * longueur);
  const avantArc = arrondi(xBase + sens * (longueur - r));
  const balayage = sens > 0 ? 1 : 0;

  if (r <= 0.5) {
    return 'M' + debut + ' ' + haut + ' H' + fin + ' V' + basY + ' H' + debut + ' Z';
  }
  return 'M' + debut + ' ' + haut
    + ' H' + avantArc
    + ' A' + r + ' ' + r + ' 0 0 ' + balayage + ' ' + fin + ' ' + arrondi(y + r)
    + ' V' + arrondi(y + h - r)
    + ' A' + r + ' ' + r + ' 0 0 ' + balayage + ' ' + avantArc + ' ' + basY
    + ' H' + debut + ' Z';
}

/**
 * Dessine les barres comparées à une largeur donnée, en 1:1.
 * @param {object} ctx
 * @returns {SVGElement}
 */
function dessinerBarres(ctx) {
  const { categories, valeurs, couleurs, definition, description } = ctx;

  // Le tracé s'arrête au plafond et reste aligné à gauche du conteneur.
  const largeur = Math.min(ctx.largeur, LARGEUR_MAX_BARRES);

  /* Domaine des barres : la LIGNE DE BASE est zéro, toujours. Une barre
     tronquée transformerait un écart de deux points en un rapport du
     simple au double. Pas de graduation ici — il n'y a pas de grille à
     aligner —, seulement un plafond avec un peu d'air pour l'étiquette. */
  const connues = valeurs.filter(estNombre);
  if (estNombre(definition.cible)) connues.push(definition.cible);
  const sommet = connues.length ? Math.max.apply(null, connues) : 1;
  const plancher = connues.length ? Math.min.apply(null, connues) : 0;
  const min = Math.min(0, plancher * 1.12);
  const max = sommet > 0 ? sommet * 1.12 : Math.max(1, Math.abs(plancher) * 0.12);

  const textesValeur = valeurs.map((valeur) => estNombre(valeur)
    ? formaterValeur(valeur, definition.unite)
    : '—');

  const PASTILLE_X = 4;
  const gauche = Math.ceil(16 + largeurMax(categories, TEXTE_AXE)) + 14;
  const droite = Math.ceil(largeurMax(textesValeur, TEXTE_AXE)) + 18;

  const haut = estNombre(definition.cible) ? 24 : 10;
  const bas = 8;
  const hauteur = haut + categories.length * RANGEE_BARRE + bas;

  const x0 = gauche;
  const x1 = Math.max(gauche + 40, largeur - droite);
  const px = (v) => x0 + ((borner(v, min, max) - min) / (max - min)) * (x1 - x0);

  /* Abscisse du zéro : c'est là que toutes les barres sont ancrées. */
  const xBase = arrondi(px(0));

  const racine = svg('svg', {
    class: 'ind-graphique__svg',
    width: largeur,
    height: hauteur,
    viewBox: '0 0 ' + largeur + ' ' + hauteur,
    role: 'img',
    'aria-label': description
  });

  const pieces = [];

  /* --- Repère de cible, tracé SOUS les barres --------------------------- */

  if (estNombre(definition.cible) && definition.cible > min && definition.cible <= max) {
    const xCible = arrondi(px(definition.cible));
    pieces.push(trait(xCible, haut - 4, xCible, hauteur - bas,
      'var(--bordure-forte)', 1, '5 4'));

    const libelle = 'Cible ' + formaterValeur(definition.cible, definition.unite);
    const demi = largeurTexte(libelle, TEXTE_AXE - 1) / 2;
    pieces.push(texte(borner(xCible, demi + 2, largeur - demi - 2), haut - 13, libelle, {
      ancre: 'middle', taille: TEXTE_AXE - 1, couleur: 'var(--texte-doux)'
    }));
  }

  /* --- Les barres -------------------------------------------------------- */

  categories.forEach((categorie, i) => {
    // L'air entre deux rangées vaut RANGEE_BARRE − EPAISSEUR_BARRE, soit
    // bien plus que l'écart de surface minimal de 2 px exigé entre deux
    // barres adjacentes.
    const yRangee = haut + i * RANGEE_BARRE;
    const y = yRangee + (RANGEE_BARRE - EPAISSEUR_BARRE) / 2;
    const milieu = yRangee + RANGEE_BARRE / 2;
    const valeur = valeurs[i];

    // Pastille de couleur + libellé en encre : le pôle n'est jamais
    // désigné par la seule couleur.
    pieces.push(disque(PASTILLE_X + 5, milieu, 5, couleurs[i], false));
    pieces.push(texte(PASTILLE_X + 16, milieu, categorie, {
      couleur: 'var(--texte)', graisse: 'var(--graisse-moyenne)'
    }));

    if (estNombre(valeur)) {
      pieces.push(svg('path', {
        d: cheminBarre(xBase, px(valeur), y, EPAISSEUR_BARRE),
        'stroke-width': ECART_BARRES,
        style: { fill: couleurs[i], stroke: 'var(--fond-eleve)' }
      }));
      // Étiquette de valeur directe, posée au bout de la barre, à
      // l'extérieur : elle ne peut donc jamais être rognée par le remplissage.
      const dirige = px(valeur) >= xBase;
      pieces.push(texte(px(valeur) + (dirige ? 9 : -9), milieu, textesValeur[i], {
        ancre: dirige ? 'start' : 'end',
        couleur: 'var(--texte)'
      }));
    } else {
      pieces.push(texte(xBase + 6, milieu, 'Valeur manquante', {
        couleur: 'var(--texte-faible)', taille: TEXTE_AXE - 1
      }));
    }
  });

  /* --- Ligne de base, par-dessus le pied des barres ---------------------- */

  pieces.push(trait(Math.round(xBase) + 0.5, haut - 4,
    Math.round(xBase) + 0.5, hauteur - bas, 'var(--bordure)', 1));

  monter(racine, pieces);
  return racine;
}
