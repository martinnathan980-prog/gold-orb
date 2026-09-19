/* =========================================================================
   ETII Hub — Boîte à outils DOM partagée (SPEC.md §8)

   Module ES autonome, sans aucune dépendance, sans aucun accès réseau.
   C'est le seul endroit du projet qui fabrique des nœuds DOM : tant que
   les pages passent par ici, trois garanties tiennent structurellement.

     1. Aucun `innerHTML` avec de la donnée. Les enfants de type chaîne
        deviennent des nœuds texte. Écrire du HTML est impossible, donc
        l'injection l'est aussi.
     2. Aucun gestionnaire d'événement en attribut HTML. Les handlers sont
        des fonctions passées par référence : un nom de squad contenant une
        apostrophe ne peut plus casser quoi que ce soit (SPEC.md §6.6).
     3. Aucune valeur de style en dur. Ce module ne pose que des classes et
        des attributs `data-*` ; couleurs, espacements et durées restent
        dans tokens.css. Les rares durées lues en JavaScript le sont depuis
        les jetons via `dureeJeton()`.

   API publique :
     el(balise, props, ...enfants)      -> HTMLElement
     svg(balise, props, ...enfants)     -> SVGElement
     frag(...enfants)                   -> DocumentFragment
     vider(noeud)                       -> noeud
     monter(parent, ...enfants)         -> parent
     surlignerVers(segments)            -> DocumentFragment
     deleguer(racine, sel, type, fn)    -> fonction de retrait
     ouvrirModale(options)              -> { fermer, element, boite }
     toast(message, variante)           -> { fermer }
     annoncer(message)                  -> void
     copierTexte(texte)                 -> Promise<boolean>
     debounce(fn, delai)                -> fonction (+ .annuler, .vider)
     rafThrottle(fn)                    -> fonction (+ .annuler)
     mouvementReduit()                  -> boolean
     dureeJeton(nom, repli)             -> number (ms)
     etatUrl.lire() / .ecrire() / .ecouter()
     stockage.lire() / .ecrire() / .supprimer() / .disponible()
     initTheme()                        -> { theme, definir, basculer }
     initNav(pageCourante)              -> void

   Contrat de classes attendu par components.css :
     .modale  .modale__boite  .modale__entete  .modale__titre
     .modale__fermeture  .modale__corps  .modale__actions
     .toasts  .toast  .toast--info|--succes|--alerte|--critique  .toast__texte
     .bouton  .bouton--primaire|--discret|--danger
   Les états transitoires passent par `data-etat="entree|ouvert|sortie"`,
   et l'ouverture d'une modale pose `data-modale-ouverte` sur <html>.

   Code défensif : chaque fonction tolère un argument manquant ou nul, et
   ne lève jamais d'exception pour une entrée malformée. Le module est
   importable dans un environnement sans DOM (les effets sont différés).
   ========================================================================= */

/* -------------------------------------------------------------------------
   0. Garde-fous d'environnement
   ------------------------------------------------------------------------- */

/** Vrai lorsqu'un DOM utilisable est disponible (faux sous un exécuteur de tests). */
const AVEC_DOM = typeof document !== 'undefined' && !!document.createElement;

/** Espace de noms SVG, requis par createElementNS pour les avatars générés. */
const NS_SVG = 'http://www.w3.org/2000/svg';

/** Préfixe de toutes les clés de stockage, pour ne jamais marcher sur les autres. */
const PREFIXE_STOCKAGE = 'etii:';

/** Clé du choix de thème explicite. */
const CLE_THEME = 'theme';

/** Valeurs de thème reconnues, en miroir exact de tokens.css. */
const THEME_CLAIR = 'clair';
const THEME_SOMBRE = 'sombre';

/** Durées de repli (ms) si les jetons CSS ne sont pas lisibles. */
const REPLI_DUREE = 220;
const REPLI_DUREE_LENTE = 400;

/** Durée d'affichage d'une notification, bornes comprises. */
const TOAST_DUREE_MIN = 4000;
const TOAST_DUREE_MAX = 10000;

/** Nombre maximal de notifications empilées : au-delà, la plus ancienne part. */
const TOAST_MAX = 4;

/* -------------------------------------------------------------------------
   1. Construction d'éléments
   ------------------------------------------------------------------------- */

/*
   Quelques noms doivent être posés comme PROPRIÉTÉ et non comme attribut :
   l'attribut `value` d'un champ ne décrit que sa valeur initiale, et
   `checked`, `disabled` ou `hidden` se comportent mal en concaténation.
   Toute clé absente de cette table est posée en attribut, ce qui est le
   comportement le plus prévisible et le plus proche du HTML écrit à la main.
*/
const PROPRIETES_DIRECTES = new Map([
  ['value', 'value'],
  ['defaultvalue', 'defaultValue'],
  ['checked', 'checked'],
  ['defaultchecked', 'defaultChecked'],
  ['indeterminate', 'indeterminate'],
  ['selected', 'selected'],
  ['disabled', 'disabled'],
  ['readonly', 'readOnly'],
  ['required', 'required'],
  ['multiple', 'multiple'],
  ['hidden', 'hidden'],
  ['open', 'open'],
  ['tabindex', 'tabIndex'],
  ['for', 'htmlFor'],
  ['htmlfor', 'htmlFor'],
  ['textcontent', 'textContent']
]);

/** Clés de `props` traitées à part, jamais posées telles quelles. */
const CLES_RESERVEES = new Set([
  'class', 'classname', 'classes', 'dataset', 'style', 'text', 'enfants',
  'children', 'ref', 'proprietes', 'props'
]);

/**
 * `camelCase` -> `kebab-case`, pour `ariaLabel` -> `aria-label`.
 * @param {string} nom
 * @returns {string}
 */
function enKebab(nom) {
  return String(nom).replace(/[A-Z]/g, (lettre) => '-' + lettre.toLowerCase());
}

/**
 * Applique une valeur de classe : chaîne, tableau, ou objet { nom: booleen }.
 * @param {Element} noeud
 * @param {*} valeur
 */
function poserClasses(noeud, valeur) {
  if (valeur === null || valeur === undefined || valeur === false) return;

  if (typeof valeur === 'string') {
    for (const nom of valeur.split(/\s+/)) {
      if (nom) noeud.classList.add(nom);
    }
    return;
  }
  if (Array.isArray(valeur)) {
    for (const entree of valeur) poserClasses(noeud, entree);
    return;
  }
  if (typeof valeur === 'object') {
    for (const nom of Object.keys(valeur)) {
      if (valeur[nom]) poserClasses(noeud, nom);
    }
  }
}

/**
 * Applique un objet de style. Réservé aux valeurs *calculées* (une largeur
 * de barre, une couleur d'avatar dérivée d'un identifiant) : tout le reste
 * appartient aux feuilles de style. Les propriétés personnalisées `--x`
 * sont acceptées, c'est le bon canal pour piloter un composant en CSS.
 * @param {HTMLElement|SVGElement} noeud
 * @param {*} valeur
 */
function poserStyle(noeud, valeur) {
  if (!valeur || !noeud.style) return;

  if (typeof valeur === 'string') {
    // Chaîne brute : on refuse, car c'est la porte d'entrée des valeurs en dur.
    return;
  }
  for (const cle of Object.keys(valeur)) {
    const brut = valeur[cle];
    if (brut === null || brut === undefined || brut === false) continue;
    try {
      if (cle.startsWith('--')) noeud.style.setProperty(cle, String(brut));
      else noeud.style.setProperty(enKebab(cle), String(brut));
    } catch (_e) { /* propriété inconnue : on ignore, jamais d'exception */ }
  }
}

/**
 * Attache un gestionnaire décrit par une clé `onXxx`.
 * Accepte une fonction, un tableau `[fn, options]` ou `{ handler, options }`.
 * @param {EventTarget} noeud
 * @param {string} cle   par exemple 'onClick', 'onKeyDown'
 * @param {*} valeur
 */
function poserEcouteur(noeud, cle, valeur) {
  const type = cle.slice(2).toLowerCase();
  if (!type) return;

  let fn = valeur;
  let options;
  if (Array.isArray(valeur)) {
    fn = valeur[0];
    options = valeur[1];
  } else if (valeur && typeof valeur === 'object' && typeof valeur.handler === 'function') {
    fn = valeur.handler;
    options = valeur.options;
  }
  if (typeof fn !== 'function') return;

  try { noeud.addEventListener(type, fn, options); } catch (_e) { /* ignoré */ }
}

/**
 * Pose une paire clé/valeur de `props` sur un nœud déjà créé.
 * @param {Element} noeud
 * @param {string} cle
 * @param {*} valeur
 * @param {boolean} estSvg  en SVG, tout est attribut (les propriétés sont en lecture seule)
 */
function poserProp(noeud, cle, valeur, estSvg) {
  if (typeof cle !== 'string' || !cle) return;

  const minuscule = cle.toLowerCase();

  // Gestionnaires d'événement : onClick, onInput, onKeyDown…
  // La majuscule après « on » est le marqueur : elle distingue `onClick`
  // d'un attribut légitime comme `open` ou `onglet`.
  if (/^on[A-Z]/.test(cle)) {
    poserEcouteur(noeud, cle, valeur);
    return;
  }

  // Une valeur nulle ou false retire l'attribut : c'est le moyen d'exprimer
  // « pas d'aria-expanded » sans écrire de branche côté appelant.
  if (valeur === null || valeur === undefined || valeur === false) {
    const nom = estSvg ? cle : enKebab(cle);
    try { noeud.removeAttribute(nom); } catch (_e) { /* ignoré */ }
    return;
  }

  // Propriétés qui n'ont de sens qu'en tant que propriétés.
  if (!estSvg && PROPRIETES_DIRECTES.has(minuscule)) {
    try { noeud[PROPRIETES_DIRECTES.get(minuscule)] = valeur; } catch (_e) { /* ignoré */ }
    return;
  }

  // En SVG le nom est repris tel quel (viewBox, stroke-width…), sinon on
  // convertit `ariaLabel` / `dataRole` en `aria-label` / `data-role`.
  const nom = estSvg ? cle : enKebab(cle);
  try {
    noeud.setAttribute(nom, valeur === true ? '' : String(valeur));
  } catch (_e) { /* nom d'attribut invalide : on ignore plutôt que de planter */ }
}

/**
 * Ajoute un enfant quelconque à un parent, en normalisant les formes.
 * Les chaînes et les nombres deviennent des nœuds texte — JAMAIS du HTML.
 * @param {Node} parent
 * @param {*} enfant
 */
function ajouterEnfant(parent, enfant) {
  if (enfant === null || enfant === undefined || enfant === false || enfant === true) return;

  if (typeof enfant === 'string') {
    if (enfant !== '') parent.appendChild(document.createTextNode(enfant));
    return;
  }
  if (typeof enfant === 'number' || typeof enfant === 'bigint') {
    parent.appendChild(document.createTextNode(String(enfant)));
    return;
  }
  if (enfant && typeof enfant === 'object' && typeof enfant.nodeType === 'number') {
    parent.appendChild(enfant);
    return;
  }
  if (Array.isArray(enfant)) {
    for (const sous of enfant) ajouterEnfant(parent, sous);
    return;
  }
  // Itérable (Set, NodeList, résultat de map…).
  if (enfant && typeof enfant[Symbol.iterator] === 'function') {
    for (const sous of enfant) ajouterEnfant(parent, sous);
    return;
  }
  // Dernier recours : représentation textuelle, toujours en texte.
  parent.appendChild(document.createTextNode(String(enfant)));
}

/**
 * Cœur commun à `el` et `svg`.
 * @param {string} ns  espace de noms, ou null pour le HTML
 * @param {string} balise
 * @param {object} props
 * @param {Array} enfants
 * @returns {Element}
 */
function creer(ns, balise, props, enfants) {
  if (!AVEC_DOM) return null;

  const nom = (typeof balise === 'string' && balise.trim()) ? balise.trim() : (ns ? 'g' : 'div');

  let noeud;
  try {
    noeud = ns ? document.createElementNS(ns, nom) : document.createElement(nom);
  } catch (_e) {
    noeud = ns ? document.createElementNS(NS_SVG, 'g') : document.createElement('div');
  }
  const estSvg = !!ns;

  if (props && typeof props === 'object') {
    for (const cle of Object.keys(props)) {
      const valeur = props[cle];
      const minuscule = cle.toLowerCase();

      // Les clés sont acceptées en anglais et en français : le projet est
      // rédigé en français et les deux orthographes coexistent dans le code.
      if (minuscule === 'class' || minuscule === 'classname' || minuscule === 'classes'
          || minuscule === 'classe') {
        poserClasses(noeud, valeur);
      } else if (minuscule === 'dataset') {
        if (valeur && typeof valeur === 'object' && noeud.dataset) {
          for (const cleData of Object.keys(valeur)) {
            const v = valeur[cleData];
            try {
              if (v === null || v === undefined || v === false) delete noeud.dataset[cleData];
              else noeud.dataset[cleData] = v === true ? '' : String(v);
            } catch (_e) { /* ignoré */ }
          }
        }
      } else if (minuscule === 'style') {
        poserStyle(noeud, valeur);
      } else if (minuscule === 'text' || minuscule === 'texte') {
        noeud.textContent = (valeur === null || valeur === undefined) ? '' : String(valeur);
      } else if (minuscule === 'ref') {
        if (typeof valeur === 'function') { try { valeur(noeud); } catch (_e) { /* ignoré */ } }
      } else if (minuscule === 'proprietes' || minuscule === 'props') {
        // Échappatoire explicite : affectation directe de propriétés DOM.
        if (valeur && typeof valeur === 'object') {
          for (const cleProp of Object.keys(valeur)) {
            try { noeud[cleProp] = valeur[cleProp]; } catch (_e) { /* ignoré */ }
          }
        }
      } else if (minuscule === 'enfants' || minuscule === 'children') {
        ajouterEnfant(noeud, valeur);
      } else if (!CLES_RESERVEES.has(minuscule)) {
        poserProp(noeud, cle, valeur, estSvg);
      }
    }
  }

  for (const enfant of enfants) ajouterEnfant(noeud, enfant);
  return noeud;
}

/**
 * Crée un élément HTML.
 *
 * `props` accepte :
 *   - `class` : chaîne, tableau, ou objet `{ nom: booleen }`
 *   - `dataset` : objet posé sur `element.dataset`
 *   - `onClick`, `onInput`, `onKeyDown`… : gestionnaires par référence
 *   - `ariaLabel`, `'aria-label'`, `role`, `href`… : attributs
 *   - `value`, `checked`, `disabled`, `hidden`, `tabIndex`… : propriétés
 *   - `text` : raccourci `textContent`
 *   - `ref` : fonction recevant l'élément créé
 *   - `proprietes` : objet affecté directement sur l'élément
 * Une valeur `null`, `undefined` ou `false` retire l'attribut correspondant.
 *
 * @param {string} balise
 * @param {object} [props]
 * @param {...*} enfants  chaînes (insérées en texte), nœuds, tableaux
 * @returns {HTMLElement}
 */
export function el(balise, props, ...enfants) {
  return creer(null, balise, props, enfants);
}

/**
 * Crée un élément SVG (avatars générés localement, icônes inline).
 * En SVG, les noms d'attributs sont repris à l'identique : `viewBox`,
 * `stroke-width`, `text-anchor`…
 *
 * @param {string} balise
 * @param {object} [props]
 * @param {...*} enfants
 * @returns {SVGElement}
 */
export function svg(balise, props, ...enfants) {
  return creer(NS_SVG, balise, props, enfants);
}

/**
 * Regroupe des enfants dans un DocumentFragment.
 * @param {...*} enfants
 * @returns {DocumentFragment}
 */
export function frag(...enfants) {
  if (!AVEC_DOM) return null;
  const fragment = document.createDocumentFragment();
  for (const enfant of enfants) ajouterEnfant(fragment, enfant);
  return fragment;
}

/* -------------------------------------------------------------------------
   2. Insertion : une seule opération DOM
   ------------------------------------------------------------------------- */

/**
 * Retire tous les enfants d'un nœud, sans reflow intermédiaire.
 * @param {Node} noeud
 * @returns {Node} le nœud, pour chaîner
 */
export function vider(noeud) {
  if (!noeud || typeof noeud !== 'object') return noeud;

  try {
    if (typeof noeud.replaceChildren === 'function') {
      noeud.replaceChildren();
      return noeud;
    }
    while (noeud.firstChild) noeud.removeChild(noeud.firstChild);
  } catch (_e) { /* nœud détaché ou exotique : rien à faire */ }
  return noeud;
}

/**
 * Vide un parent puis y insère de nouveaux enfants, en **une** mutation.
 * Le contenu est d'abord assemblé hors document (DocumentFragment), ce qui
 * évite la cascade de reflows du `innerHTML +=` de l'ancienne version.
 *
 * @param {Node} parent
 * @param {...*} enfants
 * @returns {Node} le parent
 */
export function monter(parent, ...enfants) {
  if (!AVEC_DOM || !parent || typeof parent !== 'object') return parent;

  const contenu = frag(...enfants);
  try {
    if (typeof parent.replaceChildren === 'function') parent.replaceChildren(contenu);
    else { vider(parent); parent.appendChild(contenu); }
  } catch (_e) { /* ignoré */ }
  return parent;
}

/* -------------------------------------------------------------------------
   3. Pont recherche -> affichage
   ------------------------------------------------------------------------- */

/**
 * Convertit la sortie de `search.js#surligner` en nœuds DOM.
 *
 * C'est le **seul** pont autorisé entre le moteur de recherche et
 * l'affichage : le moteur ne produit que des segments de texte brut, et
 * c'est ici, et nulle part ailleurs, que naissent les `<mark>`. Aucune
 * chaîne ne transite jamais par `innerHTML`.
 *
 * @param {Array<{texte:string, correspond:boolean}>|string} segments
 * @returns {DocumentFragment}
 */
export function surlignerVers(segments) {
  if (!AVEC_DOM) return null;

  const fragment = document.createDocumentFragment();
  if (typeof segments === 'string') {
    if (segments) fragment.appendChild(document.createTextNode(segments));
    return fragment;
  }
  if (!Array.isArray(segments)) return fragment;

  for (const segment of segments) {
    if (!segment || typeof segment !== 'object') continue;
    const texte = typeof segment.texte === 'string' ? segment.texte : '';
    if (texte === '') continue;

    if (segment.correspond) {
      const marque = document.createElement('mark');
      marque.textContent = texte;
      fragment.appendChild(marque);
    } else {
      fragment.appendChild(document.createTextNode(texte));
    }
  }
  return fragment;
}

/* -------------------------------------------------------------------------
   4. Événements délégués
   ------------------------------------------------------------------------- */

/**
 * Délégation d'événement : un seul écouteur pour une liste entière.
 * Le gestionnaire reçoit `(evenement, cible)` où `cible` est l'ancêtre
 * correspondant au sélecteur. Indispensable pour les listes longues, et
 * seule façon d'éviter les `onclick="…"` construits par concaténation.
 *
 * @param {Element|Document} racine
 * @param {string} selecteur
 * @param {string} type
 * @param {(evt: Event, cible: Element) => void} gestionnaire
 * @param {object|boolean} [options]
 * @returns {() => void} fonction de retrait de l'écouteur
 */
export function deleguer(racine, selecteur, type, gestionnaire, options) {
  const inerte = () => {};
  if (!racine || typeof racine.addEventListener !== 'function') return inerte;
  if (typeof selecteur !== 'string' || !selecteur) return inerte;
  if (typeof type !== 'string' || !type) return inerte;
  if (typeof gestionnaire !== 'function') return inerte;

  const relais = (evt) => {
    const depart = evt.target;
    if (!depart || typeof depart.closest !== 'function') return;
    let cible;
    try { cible = depart.closest(selecteur); } catch (_e) { return; }
    if (!cible || !racine.contains(cible)) return;
    gestionnaire(evt, cible);
  };

  try { racine.addEventListener(type, relais, options); } catch (_e) { return inerte; }
  return () => {
    try { racine.removeEventListener(type, relais, options); } catch (_e) { /* ignoré */ }
  };
}

/* -------------------------------------------------------------------------
   5. Mouvement et jetons lus depuis le CSS
   ------------------------------------------------------------------------- */

/**
 * L'utilisateur demande-t-il une réduction des animations ?
 * @returns {boolean}
 */
export function mouvementReduit() {
  if (!AVEC_DOM || typeof window === 'undefined' || !window.matchMedia) return false;
  try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
  catch (_e) { return false; }
}

/**
 * Lit une durée déclarée dans tokens.css et la rend en millisecondes.
 * Les durées restent ainsi déclarées à un seul endroit, même quand c'est
 * JavaScript qui doit attendre la fin d'une transition.
 *
 * @param {string} nom   par exemple '--duree-lente'
 * @param {number} repli valeur si le jeton est absent ou illisible
 * @returns {number} millisecondes
 */
export function dureeJeton(nom, repli) {
  const defaut = typeof repli === 'number' && Number.isFinite(repli) ? repli : 0;
  if (!AVEC_DOM || typeof getComputedStyle !== 'function') return defaut;
  if (typeof nom !== 'string' || !nom) return defaut;

  try {
    const brut = getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
    if (!brut) return defaut;
    const nombre = parseFloat(brut);
    if (!Number.isFinite(nombre)) return defaut;
    if (brut.endsWith('ms')) return nombre;
    if (brut.endsWith('s')) return nombre * 1000;
    return nombre;
  } catch (_e) {
    return defaut;
  }
}

/* -------------------------------------------------------------------------
   6. Focus : détection des éléments atteignables
   ------------------------------------------------------------------------- */

const SELECTEUR_FOCUSABLE = [
  'a[href]',
  'area[href]',
  'button',
  'input',
  'select',
  'textarea',
  'iframe',
  'summary',
  'audio[controls]',
  'video[controls]',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[tabindex]'
].join(',');

/**
 * Un élément est-il réellement atteignable au clavier ici et maintenant ?
 * @param {Element} noeud
 * @returns {boolean}
 */
function estFocusable(noeud) {
  if (!noeud || noeud.nodeType !== 1) return false;
  if (noeud.disabled) return false;
  if (noeud.getAttribute && noeud.getAttribute('tabindex') === '-1') return false;
  if (noeud.type === 'hidden') return false;

  try {
    if (noeud.closest('[hidden], [aria-hidden="true"], [inert]')) return false;
    // Un élément sans boîte n'est pas rendu : ni visible, ni tabulable.
    if (typeof noeud.getClientRects === 'function' && noeud.getClientRects().length === 0) {
      return false;
    }
  } catch (_e) { /* on reste permissif en cas de moteur limité */ }
  return true;
}

/**
 * Liste ordonnée des éléments focusables contenus dans une racine.
 * @param {Element} racine
 * @returns {Element[]}
 */
function elementsFocusables(racine) {
  if (!racine || typeof racine.querySelectorAll !== 'function') return [];
  let trouves;
  try { trouves = Array.from(racine.querySelectorAll(SELECTEUR_FOCUSABLE)); }
  catch (_e) { return []; }
  return trouves.filter(estFocusable);
}

/**
 * Donne le focus à un élément sans provoquer de saut de défilement.
 * @param {Element} noeud
 */
function focaliser(noeud) {
  if (!noeud || typeof noeud.focus !== 'function') return;
  try { noeud.focus({ preventScroll: true }); }
  catch (_e) { try { noeud.focus(); } catch (_e2) { /* ignoré */ } }
}

/* -------------------------------------------------------------------------
   7. Modale accessible
   ------------------------------------------------------------------------- */

/** Pile des modales ouvertes : seule celle du sommet capte le clavier. */
const pileModales = [];

/** Compteur d'identifiants, pour relier titre et dialogue sans collision. */
let compteurId = 0;

/** Identifiant unique et stable pour un préfixe donné. */
function idUnique(prefixe) {
  compteurId += 1;
  return String(prefixe || 'etii') + '-' + compteurId;
}

/**
 * Construit un bouton d'action de modale à partir de sa description.
 * @param {object} action
 * @param {object} api  l'API de la modale ({ fermer })
 * @returns {HTMLElement|null}
 */
function boutonAction(action, api) {
  if (!action) return null;
  if (action.nodeType === 1) return action;          // élément déjà construit
  if (typeof action !== 'object') return null;

  const libelle = typeof action.libelle === 'string' && action.libelle
    ? action.libelle
    : 'OK';
  const variante = typeof action.variante === 'string' && action.variante
    ? action.variante
    : 'discret';
  // `ferme` vaut true par défaut : une action de modale referme la modale,
  // sauf demande contraire explicite (validation de formulaire en échec).
  const ferme = action.ferme !== false;

  return el('button', {
    type: 'button',
    class: ['bouton', 'bouton--' + variante],
    dataset: action.valeur ? { valeur: String(action.valeur) } : null,
    autofocus: action.autofocus ? true : null,
    onClick: (evt) => {
      let resultat;
      if (typeof action.onClick === 'function') {
        try { resultat = action.onClick(evt, api); } catch (_e) { resultat = undefined; }
      }
      // Un gestionnaire peut annuler la fermeture en renvoyant `false`.
      if (ferme && resultat !== false) api.fermer('action');
    }
  }, libelle);
}

/**
 * Ouvre une modale accessible.
 *
 * Garanties : `role="dialog"`, `aria-modal="true"`, titre relié par
 * `aria-labelledby`, piège de focus réel (tabulation cyclique **et**
 * rattrapage d'un focus qui s'échappe), fermeture par `Échap` et par clic
 * sur le fond, restitution du focus à l'élément déclencheur.
 *
 * @param {object} [options]
 * @param {string} [options.titre]
 * @param {*} [options.contenu]   nœud, chaîne, tableau, ou fonction(api)
 * @param {Array} [options.actions] descriptions de boutons ou éléments
 * @param {Element} [options.declencheur] élément à refocaliser (défaut : le focus courant)
 * @param {boolean} [options.fermetureFond=true]
 * @param {boolean} [options.fermetureEchap=true]
 * @param {string} [options.classe] classe supplémentaire sur la boîte
 * @param {(raison:string)=>void} [options.onFermeture]
 * @returns {{fermer: Function, element: Element, boite: Element}}
 */
export function ouvrirModale(options) {
  const opts = (options && typeof options === 'object') ? options : {};

  // Sans DOM, on renvoie une API inerte : l'appelant n'a pas à s'en soucier.
  if (!AVEC_DOM || !document.body) {
    return { fermer: () => {}, element: null, boite: null };
  }

  const declencheur = (opts.declencheur && opts.declencheur.nodeType === 1)
    ? opts.declencheur
    : (document.activeElement && document.activeElement !== document.body
      ? document.activeElement
      : null);

  const avecTitre = typeof opts.titre === 'string' && opts.titre.trim() !== '';
  const idTitre = idUnique('modale-titre');

  let ferme = false;
  // `pret` passe à vrai une fois la structure bâtie et insérée. Tant qu'il
  // est faux, une demande de fermeture (un contenu qui se referme lui-même
  // dès sa construction) est mise en attente au lieu de laisser la modale
  // dans un état à moitié fermé.
  let pret = false;
  let fermetureDemandee = null;

  const instance = {
    fermer: (raison) => fermerModale(raison),
    element: null,
    boite: null
  };
  const api = instance;

  /* --- Structure ------------------------------------------------------- */

  const titreNoeud = avecTitre
    ? el('h2', { class: 'modale__titre', id: idTitre }, opts.titre)
    : null;

  const boutonFermeture = el('button', {
    type: 'button',
    class: 'modale__fermeture',
    ariaLabel: 'Fermer la fenêtre',
    onClick: () => fermerModale('bouton')
  }, el('span', { ariaHidden: 'true' }, '×'));

  const corps = el('div', { class: 'modale__corps' });
  const contenu = typeof opts.contenu === 'function'
    ? (() => { try { return opts.contenu(api); } catch (_e) { return null; } })()
    : opts.contenu;
  monter(corps, contenu);

  const listeActions = Array.isArray(opts.actions) ? opts.actions : [];
  const boutons = listeActions
    .map((action) => boutonAction(action, api))
    .filter(Boolean);
  const piedActions = boutons.length
    ? el('footer', { class: 'modale__actions' }, boutons)
    : null;

  const boite = el('div', {
    class: ['modale__boite', opts.classe || null],
    role: 'dialog',
    ariaModal: 'true',
    ariaLabelledby: avecTitre ? idTitre : null,
    ariaLabel: avecTitre ? null : 'Fenêtre de dialogue',
    tabIndex: -1
  },
  el('header', { class: 'modale__entete' }, titreNoeud, boutonFermeture),
  corps,
  piedActions);

  const fond = el('div', {
    class: 'modale',
    dataset: { modale: '', etat: 'entree' }
  }, boite);

  /* --- Fermetures ------------------------------------------------------ */

  let cibleAppui = null;

  const surAppui = (evt) => {
    cibleAppui = evt.target;
  };

  const surClic = (evt) => {
    if (opts.fermetureFond === false) return;
    // On ne ferme que si l'appui ET le relâchement ont eu lieu sur le fond :
    // une sélection de texte qui déborde de la boîte ne ferme pas la modale.
    if (evt.target === fond && cibleAppui === fond) fermerModale('fond');
    cibleAppui = null;
  };

  const surTouche = (evt) => {
    if (pileModales[pileModales.length - 1] !== instance) return;

    if (evt.key === 'Escape' || evt.key === 'Esc') {
      if (opts.fermetureEchap === false) return;
      evt.preventDefault();
      evt.stopPropagation();
      fermerModale('echap');
      return;
    }
    if (evt.key !== 'Tab') return;

    // Piège de focus : la tabulation tourne en boucle dans la boîte.
    const focusables = elementsFocusables(boite);
    if (focusables.length === 0) {
      evt.preventDefault();
      focaliser(boite);
      return;
    }
    const premier = focusables[0];
    const dernier = focusables[focusables.length - 1];
    const actif = document.activeElement;
    const dedans = boite.contains(actif);

    if (evt.shiftKey && (!dedans || actif === premier || actif === boite)) {
      evt.preventDefault();
      focaliser(dernier);
    } else if (!evt.shiftKey && (!dedans || actif === dernier)) {
      evt.preventDefault();
      focaliser(premier);
    }
  };

  // Rattrapage : si le focus sort malgré tout (clic ailleurs, barre du
  // navigateur, extension), on le ramène dans la boîte. C'est ce qui fait
  // la différence entre un vrai piège de focus et une simple boucle de Tab.
  const surFocusExterieur = (evt) => {
    if (pileModales[pileModales.length - 1] !== instance) return;
    if (!evt.target || boite.contains(evt.target)) return;
    const focusables = elementsFocusables(boite);
    focaliser(focusables[0] || boite);
  };

  /**
   * Ferme la modale, retire les écouteurs et restitue le focus.
   * @param {string} [raison] 'echap' | 'fond' | 'bouton' | 'action' | 'api'
   */
  function fermerModale(raison) {
    if (ferme) return;
    if (!pret) { fermetureDemandee = raison || 'api'; return; }
    ferme = true;

    const position = pileModales.indexOf(instance);
    if (position !== -1) pileModales.splice(position, 1);

    try {
      document.removeEventListener('keydown', surTouche, true);
      document.removeEventListener('focusin', surFocusExterieur, true);
      fond.removeEventListener('mousedown', surAppui);
      fond.removeEventListener('click', surClic);
    } catch (_e) { /* ignoré */ }

    if (pileModales.length === 0 && document.documentElement) {
      try { delete document.documentElement.dataset.modaleOuverte; } catch (_e) { /* ignoré */ }
    }

    const retirer = () => {
      try { if (fond.parentNode) fond.parentNode.removeChild(fond); } catch (_e) { /* ignoré */ }
    };

    if (mouvementReduit()) {
      retirer();
    } else {
      try { fond.dataset.etat = 'sortie'; } catch (_e) { /* ignoré */ }
      setTimeout(retirer, dureeJeton('--duree', REPLI_DUREE));
    }

    // Restitution du focus : au déclencheur s'il est toujours là, sinon au
    // contenu principal, pour ne jamais rendre le focus au document nu.
    const cible = (declencheur && declencheur.isConnected && estFocusable(declencheur))
      ? declencheur
      : document.getElementById('contenu');
    focaliser(cible);

    if (typeof opts.onFermeture === 'function') {
      try { opts.onFermeture(raison || 'api'); } catch (_e) { /* ignoré */ }
    }
  }

  /* --- Ouverture ------------------------------------------------------- */

  instance.element = fond;
  instance.boite = boite;
  pret = true;

  fond.addEventListener('mousedown', surAppui);
  fond.addEventListener('click', surClic);
  document.addEventListener('keydown', surTouche, true);
  document.addEventListener('focusin', surFocusExterieur, true);

  pileModales.push(instance);
  try { document.documentElement.dataset.modaleOuverte = ''; } catch (_e) { /* ignoré */ }
  document.body.appendChild(fond);

  // Passage à l'état « ouvert » à la frame suivante : la transition CSS a
  // besoin d'un état de départ effectivement rendu.
  if (mouvementReduit() || typeof requestAnimationFrame !== 'function') {
    try { fond.dataset.etat = 'ouvert'; } catch (_e) { /* ignoré */ }
  } else {
    requestAnimationFrame(() => {
      if (!ferme) { try { fond.dataset.etat = 'ouvert'; } catch (_e) { /* ignoré */ } }
    });
  }

  // Focus initial : le premier élément demandé, sinon le premier focusable
  // du corps, sinon la boîte elle-même.
  const demande = boite.querySelector('[autofocus]');
  if (demande && estFocusable(demande)) focaliser(demande);
  else {
    const focusables = elementsFocusables(corps);
    focaliser(focusables[0] || boite);
  }

  // Fermeture demandée avant la fin de la construction : on l'honore ici.
  if (fermetureDemandee !== null) fermerModale(fermetureDemandee);

  return instance;
}

/* -------------------------------------------------------------------------
   8. Notifications éphémères et annonces
   ------------------------------------------------------------------------- */

/** Région d'annonce unique, créée à la première utilisation puis réutilisée. */
let regionAnnonce = null;

/**
 * Récupère (ou crée) l'unique région `aria-live="polite"`.
 * Une seule région pour tout le site : les lecteurs d'écran annoncent
 * chaque ajout sans que l'on ait à multiplier les zones vivantes.
 * @returns {HTMLElement|null}
 */
function region() {
  if (!AVEC_DOM || !document.body) return null;
  if (regionAnnonce && regionAnnonce.isConnected) return regionAnnonce;

  const existante = document.querySelector('[data-toasts]');
  if (existante) {
    regionAnnonce = existante;
    return regionAnnonce;
  }

  regionAnnonce = el('div', {
    class: 'toasts',
    dataset: { toasts: '' },
    role: 'status',
    ariaLive: 'polite',
    ariaAtomic: 'false'
  });
  document.body.appendChild(regionAnnonce);
  return regionAnnonce;
}

/** Notifications actuellement affichées, de la plus ancienne à la plus récente. */
const toastsVisibles = [];

/**
 * Affiche une notification éphémère, annoncée aux lecteurs d'écran.
 *
 * @param {string} message
 * @param {string|object} [variante] 'info' | 'succes' | 'alerte' | 'critique',
 *        ou un objet { variante, duree }
 * @returns {{fermer: Function}}
 */
export function toast(message, variante) {
  const inerte = { fermer: () => {} };
  const texte = (message === null || message === undefined) ? '' : String(message);
  if (texte.trim() === '') return inerte;

  const opts = (variante && typeof variante === 'object') ? variante : {};
  const nom = typeof variante === 'string' && variante
    ? variante
    : (typeof opts.variante === 'string' && opts.variante ? opts.variante : 'info');

  const hote = region();
  if (!hote) return inerte;

  // Durée proportionnelle à la longueur du message, bornée : un message
  // long reste lisible, un message court ne s'éternise pas.
  const duree = (typeof opts.duree === 'number' && Number.isFinite(opts.duree))
    ? opts.duree
    : Math.min(TOAST_DUREE_MAX, Math.max(TOAST_DUREE_MIN, texte.length * 70));

  let parti = false;
  let minuteur = null;

  const noeud = el('div', {
    class: ['toast', 'toast--' + nom],
    dataset: { etat: 'entree', variante: nom }
  },
  el('span', { class: 'toast__texte' }, texte),
  el('button', {
    type: 'button',
    class: 'toast__fermeture',
    ariaLabel: 'Fermer la notification',
    onClick: () => fermer()
  }, el('span', { ariaHidden: 'true' }, '×')));

  /** Retire la notification, une seule fois. */
  function fermer() {
    if (parti) return;
    parti = true;
    if (minuteur !== null) { clearTimeout(minuteur); minuteur = null; }

    const position = toastsVisibles.indexOf(entree);
    if (position !== -1) toastsVisibles.splice(position, 1);

    const retirer = () => {
      try { if (noeud.parentNode) noeud.parentNode.removeChild(noeud); } catch (_e) { /* ignoré */ }
    };
    if (mouvementReduit()) retirer();
    else {
      try { noeud.dataset.etat = 'sortie'; } catch (_e) { /* ignoré */ }
      setTimeout(retirer, dureeJeton('--duree', REPLI_DUREE));
    }
  }

  const entree = { fermer };

  hote.appendChild(noeud);
  toastsVisibles.push(entree);

  // Au-delà de la pile maximale, la plus ancienne cède la place.
  while (toastsVisibles.length > TOAST_MAX) {
    const ancienne = toastsVisibles[0];
    toastsVisibles.splice(0, 1);
    ancienne.fermer();
  }

  if (mouvementReduit() || typeof requestAnimationFrame !== 'function') {
    try { noeud.dataset.etat = 'visible'; } catch (_e) { /* ignoré */ }
  } else {
    requestAnimationFrame(() => {
      if (!parti) { try { noeud.dataset.etat = 'visible'; } catch (_e) { /* ignoré */ } }
    });
  }

  minuteur = setTimeout(fermer, Math.max(dureeJeton('--duree-lente', REPLI_DUREE_LENTE), duree));
  return entree;
}

/**
 * Annonce un message aux seuls lecteurs d'écran (nombre de résultats,
 * changement d'onglet…), via la même région vivante que les notifications.
 * Rien n'apparaît à l'écran : l'information y est déjà.
 *
 * @param {string} message
 */
export function annoncer(message) {
  const texte = (message === null || message === undefined) ? '' : String(message);
  if (texte.trim() === '') return;

  const hote = region();
  if (!hote) return;

  const noeud = el('span', { class: 'visuellement-cache' }, texte);
  hote.appendChild(noeud);
  setTimeout(() => {
    try { if (noeud.parentNode) noeud.parentNode.removeChild(noeud); } catch (_e) { /* ignoré */ }
  }, TOAST_DUREE_MIN);
}

/* -------------------------------------------------------------------------
   9. Copie dans le presse-papiers (aucun réseau)
   ------------------------------------------------------------------------- */

/**
 * Copie un texte dans le presse-papiers.
 * L'API moderne n'existe pas partout (et pas du tout en `file://` sur
 * certains navigateurs) : on retombe sur une zone de texte hors écran.
 *
 * @param {string} texte
 * @returns {Promise<boolean>} succès réel de la copie
 */
export function copierTexte(texte) {
  const valeur = (texte === null || texte === undefined) ? '' : String(texte);
  if (!AVEC_DOM || valeur === '') return Promise.resolve(false);

  if (typeof navigator !== 'undefined' && navigator.clipboard
      && typeof navigator.clipboard.writeText === 'function') {
    try {
      return navigator.clipboard.writeText(valeur)
        .then(() => true)
        .catch(() => copieDeSecours(valeur));
    } catch (_e) { /* on bascule sur le repli */ }
  }
  return Promise.resolve(copieDeSecours(valeur));
}

/**
 * Repli de copie : sélection d'un champ hors écran + commande d'édition.
 * @param {string} valeur
 * @returns {boolean}
 */
function copieDeSecours(valeur) {
  if (!document.body) return false;
  const champ = el('textarea', {
    class: 'visuellement-cache',
    ariaHidden: 'true',
    tabIndex: -1,
    readOnly: true,
    value: valeur
  });
  document.body.appendChild(champ);

  let ok = false;
  try {
    champ.readOnly = false;
    champ.select();
    champ.setSelectionRange(0, valeur.length);
    ok = !!document.execCommand && document.execCommand('copy');
  } catch (_e) {
    ok = false;
  }
  try { document.body.removeChild(champ); } catch (_e) { /* ignoré */ }
  return ok;
}

/* -------------------------------------------------------------------------
   10. Limitation de fréquence
   ------------------------------------------------------------------------- */

/**
 * Anti-rebond : n'exécute `fn` qu'après `delai` millisecondes sans appel.
 * La fonction retournée expose `.annuler()` (oublie l'appel en attente) et
 * `.vider()` (exécute immédiatement l'appel en attente).
 *
 * @param {Function} fn
 * @param {number} [delai=150]
 * @returns {Function}
 */
export function debounce(fn, delai) {
  if (typeof fn !== 'function') {
    const inerte = () => {};
    inerte.annuler = () => {};
    inerte.vider = () => {};
    return inerte;
  }
  const attente = (typeof delai === 'number' && Number.isFinite(delai) && delai >= 0)
    ? delai
    : 150;

  let minuteur = null;
  let dernierContexte = null;
  let derniersArguments = null;

  const enveloppe = function (...args) {
    dernierContexte = this;
    derniersArguments = args;
    if (minuteur !== null) clearTimeout(minuteur);
    minuteur = setTimeout(() => {
      minuteur = null;
      const contexte = dernierContexte;
      const parametres = derniersArguments;
      dernierContexte = null;
      derniersArguments = null;
      try { fn.apply(contexte, parametres); } catch (_e) { /* ignoré */ }
    }, attente);
  };

  enveloppe.annuler = () => {
    if (minuteur !== null) clearTimeout(minuteur);
    minuteur = null;
    dernierContexte = null;
    derniersArguments = null;
  };

  enveloppe.vider = () => {
    if (minuteur === null) return;
    clearTimeout(minuteur);
    minuteur = null;
    const contexte = dernierContexte;
    const parametres = derniersArguments;
    dernierContexte = null;
    derniersArguments = null;
    try { fn.apply(contexte, parametres); } catch (_e) { /* ignoré */ }
  };

  return enveloppe;
}

/**
 * Limite `fn` à un appel par frame d'affichage, avec les derniers arguments
 * reçus. À réserver à ce qui touche à la mise en page (défilement, zoom,
 * panoramique de l'organigramme) : jamais plus d'un calcul par image.
 *
 * @param {Function} fn
 * @returns {Function} avec `.annuler()`
 */
export function rafThrottle(fn) {
  if (typeof fn !== 'function') {
    const inerte = () => {};
    inerte.annuler = () => {};
    return inerte;
  }
  const planifier = (typeof requestAnimationFrame === 'function')
    ? requestAnimationFrame
    : (rappel) => setTimeout(() => rappel(Date.now()), 16);
  const annulerPlan = (typeof cancelAnimationFrame === 'function')
    ? cancelAnimationFrame
    : clearTimeout;

  let ticket = null;
  let dernierContexte = null;
  let derniersArguments = null;

  const enveloppe = function (...args) {
    dernierContexte = this;
    derniersArguments = args;
    if (ticket !== null) return;
    ticket = planifier(() => {
      ticket = null;
      const contexte = dernierContexte;
      const parametres = derniersArguments;
      dernierContexte = null;
      derniersArguments = null;
      try { fn.apply(contexte, parametres); } catch (_e) { /* ignoré */ }
    });
  };

  enveloppe.annuler = () => {
    if (ticket !== null) annulerPlan(ticket);
    ticket = null;
    dernierContexte = null;
    derniersArguments = null;
  };

  return enveloppe;
}

/* -------------------------------------------------------------------------
   11. État dans le hash de l'URL
   ------------------------------------------------------------------------- */

/**
 * Sérialise l'état courant dans le fragment de l'URL.
 *
 * Deux exigences guident l'implémentation :
 *   - ne pas provoquer de saut de défilement : on n'écrit jamais dans
 *     `location.hash`, uniquement via `history.replaceState`.
 *   - ne pas empiler l'historique à chaque frappe : `replaceState`, jamais
 *     `pushState`. Le bouton « Précédent » reste utilisable.
 *
 * Forme : `#q=integration&type=procedure&metier=qualite&metier=methodes`
 * Une clé répétée devient un tableau à la lecture.
 */
export const etatUrl = {
  /**
   * Lit l'état encodé dans le hash.
   * @returns {Object<string, string|string[]>} objet nu ({} si rien)
   */
  lire() {
    if (typeof location === 'undefined') return {};
    try {
      const brut = String(location.hash || '').replace(/^#/, '');
      if (!brut) return {};
      const params = new URLSearchParams(brut);
      const etat = Object.create(null);
      for (const [cle, valeur] of params) {
        if (!cle) continue;
        if (cle in etat) {
          if (Array.isArray(etat[cle])) etat[cle].push(valeur);
          else etat[cle] = [etat[cle], valeur];
        } else {
          etat[cle] = valeur;
        }
      }
      return etat;
    } catch (_e) {
      return {};
    }
  },

  /**
   * Écrit l'état dans le hash, en remplaçant l'entrée d'historique courante.
   * Les valeurs vides, nulles ou `false` sont omises : l'URL reste courte
   * et lisible. Les tableaux deviennent des clés répétées.
   *
   * @param {object} objet
   */
  ecrire(objet) {
    if (typeof location === 'undefined') return;

    const source = (objet && typeof objet === 'object') ? objet : {};
    let params;
    try { params = new URLSearchParams(); } catch (_e) { return; }

    for (const cle of Object.keys(source)) {
      const valeur = source[cle];
      if (valeur === null || valeur === undefined || valeur === false || valeur === '') continue;

      if (Array.isArray(valeur) || valeur instanceof Set) {
        for (const item of valeur) {
          if (item === null || item === undefined || item === '') continue;
          params.append(cle, String(item));
        }
      } else {
        params.append(cle, valeur === true ? '1' : String(valeur));
      }
    }

    // URLSearchParams encode l'espace en '+' : lisible et parfaitement
    // symétrique avec la lecture ci-dessus.
    const hash = params.toString();
    const actuel = String(location.hash || '').replace(/^#/, '');
    if (hash === actuel) return;   // rien à écrire : pas d'appel inutile

    try {
      const url = location.pathname + location.search + (hash ? '#' + hash : '');
      if (typeof history !== 'undefined' && typeof history.replaceState === 'function') {
        history.replaceState(history.state, '', url);
      }
      // Si replaceState est indisponible, on s'abstient : écrire dans
      // location.hash ferait défiler la page et empilerait l'historique,
      // ce qui est pire que de ne pas partager l'état.
    } catch (_e) { /* ignoré */ }
  },

  /**
   * Écoute les changements de hash provoqués par l'utilisateur
   * (« Précédent », « Suivant », lien collé). `replaceState` ne déclenche
   * pas cet événement : seules les vraies navigations arrivent ici.
   *
   * @param {(etat: object) => void} rappel
   * @returns {() => void} fonction de retrait
   */
  ecouter(rappel) {
    if (typeof window === 'undefined' || typeof rappel !== 'function') return () => {};
    const relais = () => {
      try { rappel(etatUrl.lire()); } catch (_e) { /* ignoré */ }
    };
    window.addEventListener('hashchange', relais);
    return () => window.removeEventListener('hashchange', relais);
  }
};

/* -------------------------------------------------------------------------
   12. Stockage local tolérant aux pannes
   ------------------------------------------------------------------------- */

/**
 * Enveloppe de `localStorage` entièrement protégée.
 *
 * En navigation privée, avec les cookies tiers bloqués, en `file://` sur
 * certains navigateurs ou quand le quota est plein, l'accès à
 * `localStorage` lève une exception — parfois dès la lecture de la
 * propriété. Ici, tout échec est silencieux : `lire()` rend le défaut,
 * `ecrire()` renvoie `false`. **Le site doit rester pleinement
 * fonctionnel sans stockage** ; il perd seulement sa mémoire.
 */
export const stockage = {
  /**
   * Le stockage est-il réellement utilisable ?
   * @returns {boolean}
   */
  disponible() {
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return false;
      const sonde = PREFIXE_STOCKAGE + '__sonde';
      localStorage.setItem(sonde, '1');
      localStorage.removeItem(sonde);
      return true;
    } catch (_e) {
      return false;
    }
  },

  /**
   * Lit et désérialise une valeur.
   * @param {string} cle
   * @param {*} [defaut] rendu si absent, illisible ou invalide
   * @returns {*}
   */
  lire(cle, defaut) {
    const repli = defaut === undefined ? null : defaut;
    if (typeof cle !== 'string' || !cle) return repli;
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return repli;
      const brut = localStorage.getItem(PREFIXE_STOCKAGE + cle);
      if (brut === null) return repli;
      return JSON.parse(brut);
    } catch (_e) {
      // Stockage bloqué, ou JSON corrompu par une version antérieure.
      return repli;
    }
  },

  /**
   * Sérialise et enregistre une valeur.
   * @param {string} cle
   * @param {*} valeur
   * @returns {boolean} vrai si l'écriture a réellement eu lieu
   */
  ecrire(cle, valeur) {
    if (typeof cle !== 'string' || !cle) return false;
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return false;
      if (valeur === undefined) {
        localStorage.removeItem(PREFIXE_STOCKAGE + cle);
        return true;
      }
      localStorage.setItem(PREFIXE_STOCKAGE + cle, JSON.stringify(valeur));
      return true;
    } catch (_e) {
      return false;
    }
  },

  /**
   * Supprime une valeur.
   * @param {string} cle
   * @returns {boolean}
   */
  supprimer(cle) {
    if (typeof cle !== 'string' || !cle) return false;
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return false;
      localStorage.removeItem(PREFIXE_STOCKAGE + cle);
      return true;
    } catch (_e) {
      return false;
    }
  }
};

/* -------------------------------------------------------------------------
   13. Thème clair / sombre
   ------------------------------------------------------------------------- */

/** Le système est-il en thème sombre ? */
function systemeSombre() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  try { return window.matchMedia('(prefers-color-scheme: dark)').matches; }
  catch (_e) { return false; }
}

/**
 * Applique le thème mémorisé, câble la bascule de l'en-tête, et respecte
 * `prefers-color-scheme` tant qu'aucun choix explicite n'a été fait.
 *
 * Trois états possibles :
 *   - `null` (automatique)  : aucun `data-theme` sur `<html>`, le CSS suit
 *     la préférence système (tokens.css §thème sombre automatique) ;
 *   - `'clair'` / `'sombre'` : `data-theme` posé sur `<html>`, choix
 *     mémorisé qui l'emporte sur le système.
 *
 * Le bouton attendu est celui du contrat de balisage de base.css :
 * `<button class="bascule-theme" data-bascule-theme aria-pressed="false">`.
 * `aria-pressed` reflète « le thème sombre est actif », et reste juste même
 * en mode automatique.
 *
 * @returns {{theme: Function, definir: Function, basculer: Function}}
 */
export function initTheme() {
  const inerte = {
    theme: () => null,
    definir: () => {},
    basculer: () => {}
  };
  if (!AVEC_DOM || !document.documentElement) return inerte;

  const racine = document.documentElement;

  /** Choix explicite mémorisé, ou null si automatique. */
  let choix = stockage.lire(CLE_THEME, null);
  if (choix !== THEME_CLAIR && choix !== THEME_SOMBRE) choix = null;

  /** Thème réellement affiché, choix explicite ou préférence système. */
  const effectif = () => choix || (systemeSombre() ? THEME_SOMBRE : THEME_CLAIR);

  /** Reporte l'état courant sur `<html>` et sur toutes les bascules. */
  function appliquer() {
    try {
      if (choix) racine.setAttribute('data-theme', choix);
      else racine.removeAttribute('data-theme');
    } catch (_e) { /* ignoré */ }

    const sombre = effectif() === THEME_SOMBRE;
    for (const bouton of boutons()) {
      try {
        bouton.setAttribute('aria-pressed', sombre ? 'true' : 'false');
      } catch (_e) { /* ignoré */ }
    }
  }

  /** Toutes les bascules présentes dans la page (en pratique : une). */
  function boutons() {
    try { return Array.from(document.querySelectorAll('[data-bascule-theme]')); }
    catch (_e) { return []; }
  }

  /**
   * Fixe le thème. `null` (ou 'auto') rend la main au système.
   * @param {string|null} valeur
   */
  function definir(valeur) {
    const normalise = (valeur === THEME_CLAIR || valeur === THEME_SOMBRE) ? valeur : null;
    choix = normalise;
    if (normalise) stockage.ecrire(CLE_THEME, normalise);
    else stockage.supprimer(CLE_THEME);
    appliquer();
  }

  /** Bascule vers le thème opposé à celui actuellement affiché. */
  function basculer() {
    definir(effectif() === THEME_SOMBRE ? THEME_CLAIR : THEME_SOMBRE);
  }

  // Câblage : une délégation sur le document couvre aussi les bascules
  // insérées après coup, et ne dépend d'aucun attribut `onclick`.
  deleguer(document, '[data-bascule-theme]', 'click', (evt) => {
    evt.preventDefault();
    basculer();
  });

  // En mode automatique, un changement de préférence système doit mettre
  // `aria-pressed` à jour : l'affichage change, l'information aussi.
  if (typeof window !== 'undefined' && window.matchMedia) {
    try {
      const requete = window.matchMedia('(prefers-color-scheme: dark)');
      const surChangement = () => { if (!choix) appliquer(); };
      if (typeof requete.addEventListener === 'function') {
        requete.addEventListener('change', surChangement);
      } else if (typeof requete.addListener === 'function') {
        requete.addListener(surChangement);   // repli pour moteurs anciens
      }
    } catch (_e) { /* ignoré */ }
  }

  appliquer();
  return { theme: () => choix, definir, basculer };
}

/* -------------------------------------------------------------------------
   14. Navigation : page courante
   ------------------------------------------------------------------------- */

/**
 * Extrait le nom de fichier d'un chemin, en normalisant les cas limites.
 * @param {string} chemin
 * @returns {string} par exemple 'docsearch.html' ('' si indéterminable)
 */
function nomDeFichier(chemin) {
  if (typeof chemin !== 'string' || !chemin) return '';
  const sansAncre = chemin.split('#')[0].split('?')[0];
  const morceaux = sansAncre.split('/');
  const dernier = morceaux[morceaux.length - 1].trim().toLowerCase();
  if (!dernier) return 'index.html';                  // '/' ou '/dossier/'
  if (!dernier.includes('.')) return dernier + '.html'; // 'docsearch' -> fichier
  return dernier;
}

/**
 * Marque le lien de navigation actif avec `aria-current="page"`.
 *
 * L'état courant n'est porté que par cet attribut : base.css le stylise
 * directement (`.site-nav__liste a[aria-current="page"]`). Information
 * visuelle et information accessible ont ainsi une source unique, et
 * aucune classe n'est ajoutée en JavaScript.
 *
 * @param {string} [pageCourante] 'faq', 'faq.html'… déduit de l'URL si omis
 */
export function initNav(pageCourante) {
  if (!AVEC_DOM) return;

  const courant = nomDeFichier(pageCourante)
    || nomDeFichier(typeof location !== 'undefined' ? location.pathname : '')
    || 'index.html';

  let liens;
  try { liens = Array.from(document.querySelectorAll('.site-nav a[href]')); }
  catch (_e) { return; }

  for (const lien of liens) {
    let cible = '';
    try { cible = nomDeFichier(lien.getAttribute('href') || ''); } catch (_e) { cible = ''; }

    try {
      if (cible && cible === courant) lien.setAttribute('aria-current', 'page');
      else if (lien.getAttribute('aria-current') === 'page') lien.removeAttribute('aria-current');
    } catch (_e) { /* ignoré */ }
  }
}

/* =========================================================================
   Titre de section « — TITRE — »
   Le motif des outils du service : un filet, l'intitulé en capitales
   espacées, un filet. Rendu par une fonction pour que les pages et les
   modules produisent exactement la même chose.
   ========================================================================= */

/**
 * @param {string} intitule
 * @param {{niveau?: number, id?: string, classe?: string}} [options]
 * @returns {HTMLElement}
 */
export function titreSection(intitule, options) {
  const opts = options || {};
  const niveau = Math.min(6, Math.max(1, Number(opts.niveau) || 2));
  return el('h' + niveau, {
    class: ['titre-section', opts.classe || null],
    id: opts.id || null
  }, el('span', { class: 'titre-section__texte' }, String(intitule || '')));
}
