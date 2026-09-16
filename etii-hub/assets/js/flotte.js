/* =========================================================================
   ETII Hub — Flotte : fiches retournables et filtre par catégorie

   Ce module rend la flotte sous la forme d'origine du service : des fiches
   d'appareil groupées par catégorie, qui se RETOURNENT pour montrer, au
   dos, les données techniques et économiques.

   HONNÊTETÉ DES DONNÉES — c'est la règle qui prime sur toutes les autres.
   Rien n'est déduit, complété ni plausibilisé. Le module n'affiche que ce
   que porte assets/data/flotte.json :
     - un champ absent ou à `null` s'écrit « à renseigner », en style
       discret, et jamais sous la forme d'une valeur vraisemblable ;
     - les libellés de champ viennent du bloc « champs » du fichier ; s'il
       n'existe pas, le module retombe sur les CLÉS réellement présentes
       dans l'appareil, ce qui reste de la donnée du fichier ;
     - les catégories viennent du tableau « categories » ; s'il n'existe
       pas, elles sont relevées parmi les valeurs du champ « categorie »
       des appareils. Si aucune catégorie n'est déclarée, le module le DIT
       au lieu d'en fabriquer.
   Aucun chiffre, aucune désignation, aucune catégorie n'est écrite en dur
   dans ce fichier.

   ACCESSIBILITÉ DU RETOURNEMENT
     - chaque face porte un bouton explicite : « Voir les données » à
       l'avant, « Revenir » au dos ; ce sont de vrais <button>, donc
       Entrée et Espace retournent nativement ;
     - `aria-expanded` sur ces boutons reflète l'état de la fiche ;
     - la face cachée reçoit `inert` et `aria-hidden` : elle sort de
       l'ordre de tabulation ET de l'arbre d'accessibilité ;
     - le focus est déplacé sur le bouton de la face qui arrive AVANT que
       l'ancienne ne devienne inerte, pour ne jamais le perdre ;
     - Échap ramène à la face avant ;
     - sous `prefers-reduced-motion: reduce`, la rotation 3D disparaît au
       profit d'un simple basculement.

   MISE EN PAGE
   Trois colonnes sur large écran, deux puis une ensuite, par une grille
   `auto-fit` dont la colonne minimale dérive des jetons d'espacement : pas
   de media query, donc pas de point de rupture écrit en dur. Les deux
   faces occupent la MÊME cellule de grille : la hauteur d'une fiche est
   donc celle de sa face la plus haute, et les fiches d'une rangée sont
   toutes étirées à la même hauteur.

   API publique :
     carteAppareil(appareil, champs, options) -> HTMLElement
     grilleFlotte(donnees, options)           -> HTMLElement

   Tout le DOM passe par el()/svg()/frag()/monter() de ui.js : aucune
   chaîne de balisage, aucun innerHTML, aucun gestionnaire en attribut.
   ========================================================================= */

import { el, frag, monter, annoncer } from './ui.js';
import { silhouette } from './helicos.js';

/* -------------------------------------------------------------------------
   0. Constantes de libellé

   Ce sont des textes d'INTERFACE — des intitulés de commande et des états
   vides. Aucun n'est une donnée du service : ils ne décrivent aucun
   appareil, aucune valeur, aucune catégorie.
   ------------------------------------------------------------------------- */

/** Mention posée à la place d'une valeur absente. Jamais autre chose. */
const NON_RENSEIGNE = 'à renseigner';

/** Mention posée sous la silhouette tant qu'aucune photo n'est fournie. */
const PHOTO_ATTENDUE = 'photo à venir';

/** Intitulés des deux boutons de retournement. */
const VERS_ARRIERE = 'Voir les données';
const VERS_AVANT = 'Revenir';

/** Titres de repli des deux groupes du dos, si « champs » n'en propose pas. */
const TITRE_TECHNIQUE = 'Données techniques';
const TITRE_ECONOMIQUE = 'Données économiques';

/** Clé de la facette « toutes catégories ». */
const TOUTES = 'toutes';

/** Clé de la facette regroupant les appareils sans catégorie déclarée. */
const SANS_CATEGORIE = 'sans-categorie';

/** Jetons de couleur des pôles. Seule porte d'entrée d'une couleur ici. */
const COULEUR_POLE = {
  ETIIA: 'var(--pole-etiia)',
  ETIIE: 'var(--pole-etiie)',
  ETIII: 'var(--pole-etiii)',
  ETII: 'var(--pole-etii)'
};

/** Compteur d'identifiants : les relations ARIA doivent être référençables. */
let compteur = 0;

/** Identifiant unique et stable pour la durée de la page. */
function identifiant(prefixe) {
  compteur += 1;
  return `flotte-${prefixe}-${compteur}`;
}

/* -------------------------------------------------------------------------
   1. Lecture défensive de la donnée

   Aucune de ces fonctions ne complète une information manquante : elles se
   contentent de reconnaître la forme reçue et de signaler l'absence.
   ------------------------------------------------------------------------- */

/**
 * Chaîne non vide, ou chaîne vide. Ne fabrique jamais de valeur de repli.
 * @param {*} brut
 * @returns {string}
 */
function texte(brut) {
  if (brut === null || brut === undefined) return '';
  if (typeof brut === 'boolean') return brut ? 'oui' : 'non';
  return String(brut).trim();
}

/**
 * Liste de chaînes propre, quelle que soit la forme reçue.
 * @param {*} brut
 * @returns {string[]}
 */
function listeTexte(brut) {
  if (!Array.isArray(brut)) return [];
  return brut.map(texte).filter((v) => v !== '');
}

/**
 * Objet exploitable, ou objet vide.
 * @param {*} brut
 * @returns {object}
 */
function objet(brut) {
  return (brut && typeof brut === 'object' && !Array.isArray(brut)) ? brut : {};
}

/**
 * Chemin d'image acceptable : uniquement une référence LOCALE et relative.
 * Le site doit fonctionner hors ligne (SPEC §1) : une URL absolue, un
 * protocole exotique ou un chemin protocole-relatif sont refusés, et la
 * fiche retombe alors sur la silhouette dessinée.
 * @param {*} brut
 * @returns {string} chemin utilisable, ou chaîne vide
 */
function cheminPhoto(brut) {
  const valeur = texte(brut);
  if (!valeur) return '';
  if (valeur.startsWith('//')) return '';
  if (/^[a-z][a-z0-9+.-]*:/i.test(valeur)) return '';
  return valeur;
}

/**
 * Normalise la liste des catégories.
 *
 * Accepte des chaînes (`"civil"`) comme des objets (`{ id, libelle }`).
 * Ne fabrique AUCUNE entrée : si le fichier n'en déclare pas, la liste est
 * reconstituée à partir des valeurs réellement portées par les appareils,
 * et reste vide si aucun appareil n'en porte.
 *
 * @param {*} brutCategories  contenu de `donnees.categories`
 * @param {Array} appareils   la flotte, pour le relevé de repli
 * @returns {Array<{id: string, libelle: string, description: string}>}
 */
function normaliserCategories(brutCategories, appareils) {
  const vues = new Map();

  const ajouter = (id, libelle, description) => {
    const cle = texte(id);
    if (!cle || vues.has(cle)) return;
    vues.set(cle, {
      id: cle,
      libelle: texte(libelle) || cle,
      description: texte(description)
    });
  };

  if (Array.isArray(brutCategories)) {
    for (const entree of brutCategories) {
      if (entree === null || entree === undefined) continue;
      if (typeof entree === 'object') {
        const source = objet(entree);
        ajouter(
          source.id ?? source.cle ?? source.code ?? source.valeur ?? source.nom
            ?? source.libelle,
          source.libelle ?? source.nom ?? source.titre ?? source.label,
          source.description ?? source.resume
        );
      } else {
        ajouter(entree, entree, '');
      }
    }
  }

  /* Repli : les catégories effectivement portées par les appareils. Ce
     n'est pas une invention, c'est un relevé de ce qui est dans le fichier. */
  if (vues.size === 0) {
    for (const appareil of appareils) {
      const cle = texte(objet(appareil).categorie);
      if (cle) ajouter(cle, cle, '');
    }
  }

  return [...vues.values()];
}

/**
 * Normalise un groupe de descripteurs de champ.
 *
 * Formes acceptées :
 *   ["masse", "vitesse"]                      -> la clé sert de libellé
 *   [{ cle, libelle, unite }]                 -> forme complète
 *   { masse: "Masse maximale" }               -> table clé -> libellé
 *   { titre, champs: [...] }                  -> groupe titré
 *
 * @param {*} brut
 * @returns {{titre: string, champs: Array<{cle: string, libelle: string, unite: string}>}}
 */
function normaliserGroupeChamps(brut) {
  let titre = '';
  let source = brut;

  if (source && typeof source === 'object' && !Array.isArray(source)
      && (source.champs || source.liste || source.titre)) {
    titre = texte(source.titre || source.libelle);
    source = source.champs || source.liste || [];
  }

  const champs = [];
  const vus = new Set();

  const ajouter = (cle, libelle, unite) => {
    const identifiantChamp = texte(cle);
    if (!identifiantChamp || vus.has(identifiantChamp)) return;
    vus.add(identifiantChamp);
    champs.push({
      cle: identifiantChamp,
      libelle: texte(libelle) || identifiantChamp,
      unite: texte(unite)
    });
  };

  if (Array.isArray(source)) {
    for (const entree of source) {
      if (entree === null || entree === undefined) continue;
      if (typeof entree === 'object') {
        const descripteur = objet(entree);
        ajouter(
          descripteur.cle ?? descripteur.id ?? descripteur.champ ?? descripteur.code,
          descripteur.libelle ?? descripteur.nom ?? descripteur.titre ?? descripteur.label,
          descripteur.unite ?? descripteur.symbole
        );
      } else {
        ajouter(entree, entree, '');
      }
    }
  } else if (source && typeof source === 'object') {
    for (const cle of Object.keys(source)) {
      const valeur = source[cle];
      if (valeur && typeof valeur === 'object') {
        const descripteur = objet(valeur);
        ajouter(cle, descripteur.libelle ?? descripteur.nom ?? descripteur.titre,
          descripteur.unite ?? descripteur.symbole);
      } else {
        ajouter(cle, valeur, '');
      }
    }
  }

  return { titre, champs };
}

/**
 * Normalise le bloc « champs » complet en ses deux groupes.
 * @param {*} brut  contenu de `donnees.champs`
 * @returns {{technique: object, economique: object}}
 */
function normaliserChamps(brut) {
  const source = objet(brut);
  return {
    technique: normaliserGroupeChamps(
      source.technique ?? source.techniques ?? source.technic ?? null),
    economique: normaliserGroupeChamps(
      source.economique ?? source.economiques ?? source['économique'] ?? null)
  };
}

/**
 * Descripteurs à employer pour un groupe donné d'un appareil.
 *
 * Si le fichier déclare des champs, ce sont eux qui font foi, dans leur
 * ordre — un champ déclaré mais absent de l'appareil s'affiche « à
 * renseigner », ce qui est précisément l'information utile. Sinon, on
 * relève les clés réellement présentes dans l'appareil.
 *
 * @param {Array} declares
 * @param {object} valeurs
 * @returns {Array<{cle: string, libelle: string, unite: string}>}
 */
function descripteurs(declares, valeurs) {
  if (Array.isArray(declares) && declares.length) return declares;
  return Object.keys(valeurs).map((cle) => ({ cle, libelle: cle, unite: '' }));
}

/**
 * Rend une valeur affichable, sans jamais en inventer une.
 *
 * Une valeur absente, nulle, vide, ou un nombre non fini, sont TOUS
 * signalés comme non renseignés. Une unité n'est accolée que si le
 * fichier la déclare et que la valeur existe.
 *
 * @param {*} brut
 * @param {string} unite
 * @returns {{texte: string, renseignee: boolean}}
 */
function valeurLisible(brut, unite) {
  if (brut === null || brut === undefined) {
    return { texte: NON_RENSEIGNE, renseignee: false };
  }
  if (typeof brut === 'number') {
    if (!Number.isFinite(brut)) return { texte: NON_RENSEIGNE, renseignee: false };
    const suffixe = texte(unite);
    return { texte: suffixe ? `${brut} ${suffixe}` : String(brut), renseignee: true };
  }
  if (Array.isArray(brut)) {
    const elements = listeTexte(brut);
    return elements.length
      ? { texte: elements.join(' · '), renseignee: true }
      : { texte: NON_RENSEIGNE, renseignee: false };
  }
  if (typeof brut === 'object') {
    /* Forme { valeur, unite } : l'unité du fichier l'emporte sur celle du
       descripteur, car elle est attachée à la mesure elle-même. */
    const enveloppe = objet(brut);
    if ('valeur' in enveloppe) {
      return valeurLisible(enveloppe.valeur, enveloppe.unite ?? unite);
    }
    return { texte: NON_RENSEIGNE, renseignee: false };
  }

  const valeur = texte(brut);
  if (!valeur) return { texte: NON_RENSEIGNE, renseignee: false };
  const suffixe = texte(unite);
  return { texte: suffixe ? `${valeur} ${suffixe}` : valeur, renseignee: true };
}

/**
 * Extrait la liste d'appareils, quelle que soit la forme du document.
 * @param {*} donnees
 * @returns {Array}
 */
function listeAppareils(donnees) {
  if (Array.isArray(donnees)) return donnees.filter((a) => a && typeof a === 'object');
  const source = objet(donnees);
  const brut = Array.isArray(source.flotte) ? source.flotte
    : (Array.isArray(source.appareils) ? source.appareils : []);
  return brut.filter((a) => a && typeof a === 'object');
}

/**
 * Accord singulier / pluriel d'un décompte. Règle de langue, pas de donnée.
 * @param {number} n
 * @returns {string}
 */
function accordAppareils(n) {
  return n <= 1 ? `${n} appareil` : `${n} appareils`;
}

/* -------------------------------------------------------------------------
   2. Fragments d'affichage
   ------------------------------------------------------------------------- */

/**
 * Pastille de pôle ÉTIQUETÉE. Le point teinté est décoratif : c'est le
 * libellé « Pôle ETIIA » qui porte l'information, de sorte que la couleur
 * ne signale jamais seule le pôle (SPEC §1bis).
 * @param {string} code
 * @returns {HTMLElement}
 */
function pastillePole(code) {
  return el('span', {
    class: 'badge badge--contour fiche-pole',
    dataset: { pole: code },
    style: { '--couleur-pole': COULEUR_POLE[code] || COULEUR_POLE.ETII }
  },
  el('span', { class: 'fiche-pole__point', ariaHidden: 'true' }),
  `Pôle ${code}`);
}

/**
 * Rubrique étiquetée d'une face : un intitulé discret, un contenu.
 * @param {string} etiquette
 * @param {...*} contenu
 * @returns {HTMLElement}
 */
function rubrique(etiquette, ...contenu) {
  return el('div', { class: 'fiche__rubrique' },
    el('span', { class: 'fiche__etiquette' }, etiquette),
    contenu);
}

/**
 * Emplacement de la photo.
 *
 * Tant que le champ « photo » est vide, l'emplacement est TENU par la
 * silhouette dessinée de helicos.js, accompagnée d'une mention discrète :
 * la fiche montre ainsi qu'une photo est attendue, sans faire passer le
 * dessin pour une photographie.
 *
 * @param {object} appareil
 * @param {string} designation
 * @returns {HTMLElement}
 */
function emplacementPhoto(appareil, designation) {
  const chemin = cheminPhoto(appareil.photo);

  if (chemin) {
    return el('figure', { class: 'fiche__visuel fiche__visuel--photo' },
      el('img', {
        class: 'fiche__photo',
        src: chemin,
        alt: `${designation} — photographie`,
        loading: 'lazy',
        decoding: 'async'
      }));
  }

  return el('figure', { class: 'fiche__visuel' },
    silhouette(appareil.silhouette, {
      titre: `${designation} — silhouette stylisée`,
      classe: 'fiche__silhouette'
    }),
    el('figcaption', { class: 'fiche__mention' }, PHOTO_ATTENDUE));
}

/**
 * Groupe de données du dos : un titre, puis une liste de définitions.
 *
 * La liste est un `<dl>` : chaque libellé est structurellement associé à sa
 * valeur, ce qu'un lecteur d'écran restitue correctement. Une valeur
 * absente porte `data-vide` et reste une valeur manquante explicite.
 *
 * @param {string} titre
 * @param {Array} descripteursChamps
 * @param {object} valeurs
 * @param {string} idTitre
 * @returns {HTMLElement}
 */
function groupeDonnees(titre, descripteursChamps, valeurs, idTitre) {
  const lignes = descripteursChamps.map((champ) => {
    const rendu = valeurLisible(valeurs[champ.cle], champ.unite);
    return frag(
      el('dt', { class: 'fiche-donnees__libelle' }, champ.libelle),
      el('dd', {
        class: 'fiche-donnees__valeur',
        dataset: { vide: rendu.renseignee ? null : 'oui' }
      }, rendu.texte));
  });

  return el('section', { class: 'fiche-groupe', ariaLabelledby: idTitre },
    el('h4', { class: 'fiche__etiquette fiche-groupe__titre', id: idTitre }, titre),
    lignes.length
      ? el('dl', { class: 'fiche-donnees' }, lignes)
      : el('p', { class: 'fiche__mention sans-marge' },
        'Aucun champ déclaré dans les données.'));
}

/* -------------------------------------------------------------------------
   3. `carteAppareil()` — la fiche retournable
   ------------------------------------------------------------------------- */

/**
 * Fiche d'un appareil, retournable.
 *
 * Face avant : emplacement de la photo, désignation, segment, catégorie et
 * pôles concernés en pastilles étiquetées.
 * Face arrière : les données techniques et économiques, en deux groupes
 * distincts et titrés, dont les libellés viennent du bloc « champs ».
 *
 * @param {object} appareil  une entrée de assets/data/flotte.json
 * @param {object} [champs]  le bloc « champs » du même fichier
 * @param {{niveauTitre?: number, id?: string, classe?: string,
 *          categories?: Array}} [options]
 * @returns {HTMLElement}
 */
export function carteAppareil(appareil, champs, options) {
  assurerStyles();

  const opts = objet(options);
  const source = objet(appareil);
  const modele = normaliserChamps(champs);

  /* --- Lecture, sans le moindre complément ------------------------------ */
  const designation = texte(source.designation) || texte(source.code)
    || texte(source.nom) || NON_RENSEIGNE;
  const segment = texte(source.segment);
  const cleCategorie = texte(source.categorie);
  const poles = listeTexte(source.poles);

  const categories = Array.isArray(opts.categories) ? opts.categories : [];
  const trouvee = categories.find((c) => c.id === cleCategorie);
  const libelleCategorie = trouvee ? trouvee.libelle : cleCategorie;

  const technique = objet(source.technique);
  const economique = objet(source.economique);

  const niveau = Math.min(5, Math.max(2, Number(opts.niveauTitre) || 3));

  /* --- Identifiants des relations ARIA ---------------------------------- */
  const idFiche = texte(opts.id) || identifiant('fiche');
  const idAvant = `${idFiche}-avant`;
  const idArriere = `${idFiche}-arriere`;
  const idTitre = `${idFiche}-titre`;
  const idTechnique = `${idFiche}-technique`;
  const idEconomique = `${idFiche}-economique`;

  /* --- Face avant -------------------------------------------------------- */
  let boutonAvant = null;

  const faceAvant = el('section', {
    class: 'fiche__face fiche__face--avant',
    id: idAvant,
    ariaLabelledby: idTitre
  },
  emplacementPhoto(source, designation),

  el('div', { class: 'fiche__corps' },
    el(`h${niveau}`, { class: 'fiche__designation', id: idTitre },
      designation),

    el('ul', { class: 'fiche__liste' },
      segment ? el('li', {}, el('span', { class: 'badge badge--neutre' }, segment)) : null,
      libelleCategorie
        ? el('li', {}, el('span', { class: 'badge badge--contour fiche__categorie' },
          libelleCategorie))
        : null),

    poles.length
      ? rubrique('Pôles concernés',
        el('ul', { class: 'fiche__liste' },
          poles.map((p) => el('li', {}, pastillePole(p)))))
      : rubrique('Pôles concernés',
        el('p', { class: 'fiche__mention sans-marge' }, NON_RENSEIGNE))),

  el('div', { class: 'fiche__actions' },
    el('button', {
      class: 'bouton bouton--secondaire bouton--bloc fiche__bascule',
      type: 'button',
      ariaExpanded: 'false',
      ariaControls: idArriere,
      onClick: () => retourner(true),
      ref: (noeud) => { boutonAvant = noeud; }
    },
    VERS_ARRIERE,
    el('span', { class: 'visuellement-cache' }, ` de ${designation}`))));

  /* --- Face arrière ------------------------------------------------------ */
  let boutonArriere = null;

  const faceArriere = el('section', {
    class: 'fiche__face fiche__face--arriere',
    id: idArriere,
    ariaLabel: `${designation} — données`
  },
  el('div', { class: 'fiche__corps' },
    el('p', { class: 'fiche__etiquette sans-marge' }, designation),

    groupeDonnees(modele.technique.titre || TITRE_TECHNIQUE,
      descripteurs(modele.technique.champs, technique), technique, idTechnique),

    groupeDonnees(modele.economique.titre || TITRE_ECONOMIQUE,
      descripteurs(modele.economique.champs, economique), economique, idEconomique)),

  el('div', { class: 'fiche__actions' },
    el('button', {
      class: 'bouton bouton--secondaire bouton--bloc fiche__bascule',
      type: 'button',
      ariaExpanded: 'false',
      ariaControls: idArriere,
      onClick: () => retourner(false),
      ref: (noeud) => { boutonArriere = noeud; }
    },
    VERS_AVANT,
    el('span', { class: 'visuellement-cache' }, ` à la présentation de ${designation}`))));

  /* --- Assemblage -------------------------------------------------------- */
  const pivot = el('div', { class: 'fiche__pivot' }, faceAvant, faceArriere);

  const fiche = el('article', {
    class: ['fiche', opts.classe || null],
    id: idFiche,
    dataset: { face: 'avant', categorie: cleCategorie || null },
    onKeyDown: (evenement) => {
      /* Échap referme la fiche : raccourci attendu partout ailleurs dans le
         hub, et seule action clavier ajoutée — Entrée et Espace sont pris
         en charge nativement par les <button>. */
      if (evenement.key !== 'Escape') return;
      if (fiche.dataset.face !== 'arriere') return;
      evenement.stopPropagation();
      retourner(false);
    }
  }, pivot);

  /**
   * Retourne la fiche.
   *
   * L'ordre des opérations est celui qui préserve le focus : on réveille
   * d'abord la face qui arrive, on y place le focus, et seulement ensuite
   * on rend inerte celle qui part. L'inverse enverrait le focus sur
   * <body> à chaque retournement.
   *
   * @param {boolean} versArriere
   * @param {boolean} [avecFocus=true]
   */
  function retourner(versArriere, avecFocus) {
    const deplacerFocus = avecFocus !== false;
    const entrante = versArriere ? faceArriere : faceAvant;
    const sortante = versArriere ? faceAvant : faceArriere;
    const boutonEntrant = versArriere ? boutonArriere : boutonAvant;

    fiche.dataset.face = versArriere ? 'arriere' : 'avant';

    entrante.toggleAttribute('inert', false);
    entrante.removeAttribute('aria-hidden');
    entrante.dataset.visible = 'oui';

    if (deplacerFocus && boutonEntrant && typeof boutonEntrant.focus === 'function') {
      try { boutonEntrant.focus(); } catch (_e) { /* focus refusé : sans gravité */ }
    }

    sortante.toggleAttribute('inert', true);
    sortante.setAttribute('aria-hidden', 'true');
    sortante.dataset.visible = 'non';

    const etat = versArriere ? 'true' : 'false';
    if (boutonAvant) boutonAvant.setAttribute('aria-expanded', etat);
    if (boutonArriere) boutonArriere.setAttribute('aria-expanded', etat);

    if (deplacerFocus) {
      annoncer(versArriere
        ? `${designation} : données techniques et économiques affichées.`
        : `${designation} : présentation affichée.`);
    }
  }

  /* État initial : face avant lisible, face arrière hors d'atteinte. */
  retourner(false, false);

  return fiche;
}

/* -------------------------------------------------------------------------
   4. `grilleFlotte()` — filtre par catégorie et grille de fiches
   ------------------------------------------------------------------------- */

/**
 * Rend le filtre par catégorie et la grille des fiches retournables.
 *
 * Le filtre est un groupe de puces de facette, chacune portant le nombre
 * d'appareils qu'elle sélectionne ; « Toutes » est active par défaut. Si le
 * fichier ne déclare aucune catégorie, le module l'écrit plutôt que d'en
 * inventer, et la grille reste complète.
 *
 * @param {object|Array} donnees  contenu de assets/data/flotte.json
 * @param {{categorieInitiale?: string, surChangement?: Function,
 *          niveauTitre?: number, etiquette?: string}} [options]
 * @returns {HTMLElement}
 */
export function grilleFlotte(donnees, options) {
  assurerStyles();

  const opts = objet(options);
  const source = objet(donnees);
  const appareils = listeAppareils(donnees);
  const champs = source.champs ?? source.colonnes ?? null;
  const categories = normaliserCategories(source.categories, appareils);
  const niveau = Math.min(5, Math.max(2, Number(opts.niveauTitre) || 3));

  const etiquetteFiltre = texte(opts.etiquette) || 'Filtrer par catégorie';

  /* --- Décomptes : relevés sur la donnée, jamais estimés ----------------- */
  const compte = new Map();
  let sansCategorie = 0;
  for (const appareil of appareils) {
    const cle = texte(objet(appareil).categorie);
    if (!cle) { sansCategorie += 1; continue; }
    compte.set(cle, (compte.get(cle) || 0) + 1);
  }

  /* Facettes : « toutes », puis chaque catégorie déclarée, puis — s'il y en
     a — le reliquat des appareils dont la catégorie n'est pas renseignée.
     Cette dernière puce est un constat d'affichage, pas une catégorie. */
  const facettes = [{ id: TOUTES, libelle: 'Toutes', total: appareils.length }];
  for (const categorie of categories) {
    facettes.push({
      id: categorie.id,
      libelle: categorie.libelle,
      total: compte.get(categorie.id) || 0
    });
  }
  if (categories.length && sansCategorie > 0) {
    facettes.push({
      id: SANS_CATEGORIE,
      libelle: 'Catégorie à renseigner',
      total: sansCategorie
    });
  }

  /* --- État --------------------------------------------------------------- */
  const demandee = texte(opts.categorieInitiale);
  let active = facettes.some((f) => f.id === demandee) ? demandee : TOUTES;

  const idFiltre = identifiant('filtre');
  const grille = el('ul', { class: 'flotte-grille' });
  const resume = el('p', { class: 'flotte-resume texte-doux sans-marge', role: 'status' });
  const boutons = new Map();

  /**
   * Appareils correspondant à la facette active.
   * @returns {Array}
   */
  function selection() {
    if (active === TOUTES) return appareils;
    if (active === SANS_CATEGORIE) {
      return appareils.filter((a) => !texte(objet(a).categorie));
    }
    return appareils.filter((a) => texte(objet(a).categorie) === active);
  }

  /** Reconstruit la grille et le résumé pour la facette active. */
  function rendre(avecAnnonce) {
    const visibles = selection();

    for (const [cle, bouton] of boutons) {
      bouton.setAttribute('aria-pressed', cle === active ? 'true' : 'false');
    }

    if (visibles.length) {
      monter(grille, visibles.map((appareil) => el('li', { class: 'flotte-grille__case' },
        carteAppareil(appareil, champs, { niveauTitre: niveau + 1, categories }))));
    } else {
      monter(grille, el('li', { class: 'flotte-grille__case flotte-grille__case--vide' },
        el('p', { class: 'fiche__mention sans-marge' },
          'Aucun appareil dans cette catégorie.')));
    }

    const facetteActive = facettes.find((f) => f.id === active);
    const suffixe = (active === TOUTES || !facetteActive)
      ? '' : ` — ${facetteActive.libelle}`;
    resume.textContent = `${accordAppareils(visibles.length)}${suffixe}`;

    if (avecAnnonce && typeof opts.surChangement === 'function') {
      try { opts.surChangement(active, visibles); } catch (_e) { /* hôte fautif : ignoré */ }
    }
  }

  /**
   * Fabrique une puce de facette.
   * @param {{id: string, libelle: string, total: number}} facette
   * @returns {HTMLElement}
   */
  function puce(facette) {
    const bouton = el('button', {
      class: 'facette',
      type: 'button',
      ariaPressed: 'false',
      onClick: () => {
        if (active === facette.id) return;
        active = facette.id;
        rendre(true);
      }
    },
    el('span', { class: 'facette__marque', ariaHidden: 'true' }, '✓'),
    el('span', {}, facette.libelle),
    el('span', { class: 'facette__compteur' }, String(facette.total)),
    el('span', { class: 'visuellement-cache' }, ` (${accordAppareils(facette.total)})`));

    boutons.set(facette.id, bouton);
    return el('li', {}, bouton);
  }

  /* --- Assemblage --------------------------------------------------------- */
  const barre = categories.length
    ? el('div', { class: 'flotte-barre', role: 'group', ariaLabelledby: idFiltre },
      el('h3', { class: 'fiche__etiquette sans-marge', id: idFiltre }, etiquetteFiltre),
      el('ul', { class: 'facettes' }, facettes.map(puce)))
    : el('p', { class: 'fiche__mention sans-marge' },
      'Aucune catégorie déclarée dans les données : la flotte est présentée '
      + 'sans filtre.');

  const racine = el('div', { class: 'flotte' }, barre, resume, grille);

  rendre(false);
  return racine;
}

/* -------------------------------------------------------------------------
   5. Feuille intégrée

   Déposée une seule fois, EN TÊTE de <head> : une page hôte peut redéfinir
   ces classes sans surenchère de spécificité. Aucune valeur brute —
   uniquement des `var(--…)` de tokens.css, ou des calculs dérivés de ces
   jetons — et toute animation est levée sous `prefers-reduced-motion`.
   ------------------------------------------------------------------------- */

const ID_STYLES = 'flotte-styles';

const STYLES = `
/* --- Grille : trois colonnes, puis deux, puis une -----------------------
   Aucune media query, donc aucun point de rupture écrit en dur : la
   largeur minimale de colonne dérive de l'échelle d'espacement. Dans le
   conteneur de contenu du hub, elle laisse place à trois colonnes au plus,
   à deux en tablette, à une en téléphone. */
.flotte {
  display: flex;
  flex-direction: column;
  gap: var(--e-5);
}

.flotte-barre {
  display: flex;
  flex-direction: column;
  gap: var(--e-3);
}

.flotte-resume {
  font-size: var(--texte-sm);
}

.flotte-grille {
  display: grid;
  gap: var(--e-5);
  align-items: stretch;
  grid-template-columns: repeat(
    auto-fit,
    minmax(min(calc(var(--e-16) * 3.4), 100%), 1fr)
  );

  /* Plafond à trois colonnes : une quatrième demanderait plus de largeur
     que cette borne, elle-même plus large que le conteneur de contenu du
     hub — la borne ne se voit donc jamais et ne fait que garantir le
     nombre de colonnes si une page hôte s'élargissait. */
  max-inline-size: calc(var(--e-16) * 14);
  margin: 0;
  padding: 0;
  list-style: none;
}

/* La case s'étire : toutes les fiches d'une rangée montent à la même
   hauteur, faces avant et arrière comprises. */
.flotte-grille__case {
  display: grid;
}

.flotte-grille__case--vide {
  padding: var(--e-6);
  border: 1px dashed var(--bordure);
  border-radius: var(--rayon-lg);
  text-align: center;
}

/* --- La fiche et son retournement ---------------------------------------
   Les deux faces partagent la MÊME cellule de grille : la hauteur de la
   fiche est celle de la face la plus haute, et le retournement ne provoque
   aucun saut de mise en page. */
.fiche {
  display: grid;
  perspective: calc(var(--e-16) * 8);
}

.fiche__pivot {
  display: grid;
  block-size: 100%;
  transform-style: preserve-3d;
  transition: transform var(--duree-lente) var(--courbe);
}

.fiche[data-face="arriere"] .fiche__pivot {
  transform: rotateY(180deg);
}

.fiche__face {
  grid-area: 1 / 1;
  display: flex;
  flex-direction: column;
  gap: var(--e-4);
  padding: var(--e-5);

  background-color: var(--carte-fond);
  border: 1px solid var(--carte-bord);
  border-radius: var(--rayon-lg);
  box-shadow: var(--ombre-sm);

  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.fiche__face--arriere {
  transform: rotateY(180deg);
}

/* Le focus doit rester lisible alors même que la face est en rotation. */
.fiche__face:focus-within {
  border-color: var(--bordure-forte);
}

.fiche__corps {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: var(--e-4);
}

.fiche__actions {
  display: flex;
  margin-block-start: auto;
}

/* --- Face avant ---------------------------------------------------------- */

.fiche__visuel {
  display: flex;
  flex-direction: column;
  gap: var(--e-2);
  align-items: center;
  margin: 0;
  padding: var(--e-3);
  color: var(--texte-doux);
  background-color: var(--fond-enfonce);
  border: 1px solid var(--bordure-douce);
  border-radius: var(--rayon-md);
}

.fiche__visuel--photo {
  padding: 0;
  overflow: hidden;
}

.fiche__photo {
  display: block;
  inline-size: 100%;
  block-size: auto;
}

.fiche__silhouette {
  display: block;
  inline-size: 100%;
  block-size: auto;
}

.fiche__mention {
  font-size: var(--texte-xs);
  color: var(--texte-faible);
}

.fiche__designation {
  font-size: var(--texte-xl);
  font-weight: var(--graisse-extra);
  letter-spacing: var(--lettrage-titre);
  font-variant-numeric: tabular-nums;
  margin: 0;
}

.fiche__etiquette {
  font-size: var(--texte-xs);
  font-weight: var(--graisse-forte);
  letter-spacing: var(--lettrage-etiquette);
  text-transform: uppercase;
  color: var(--texte-faible);
}

.fiche__rubrique {
  display: flex;
  flex-direction: column;
  gap: var(--e-2);
}

.fiche__liste {
  display: flex;
  flex-wrap: wrap;
  gap: var(--e-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.fiche__categorie {
  color: var(--texte-doux);
}

.fiche-pole {
  --couleur-pole: var(--pole-etii);
  display: inline-flex;
  align-items: center;
  gap: var(--e-2);
  border-color: color-mix(in srgb, var(--couleur-pole) 38%, transparent);
}

.fiche-pole__point {
  flex: none;
  inline-size: var(--e-2);
  block-size: var(--e-2);
  border-radius: var(--rayon-plein);
  background-color: var(--couleur-pole);
}

/* --- Face arrière -------------------------------------------------------- */

.fiche-groupe {
  display: flex;
  flex-direction: column;
  gap: var(--e-2);
}

.fiche-groupe__titre {
  margin: 0;
  padding-block-end: var(--e-2);
  border-block-end: 1px solid var(--bordure-douce);
}

.fiche-donnees {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--e-1) var(--e-4);
  margin: 0;
  font-size: var(--texte-sm);
}

.fiche-donnees__libelle {
  color: var(--texte-doux);
}

.fiche-donnees__valeur {
  margin: 0;
  text-align: end;
  font-variant-numeric: tabular-nums;
  color: var(--texte);
}

/* Une valeur absente se lit comme absente : discrète, en italique, jamais
   confondable avec une mesure. */
.fiche-donnees__valeur[data-vide="oui"] {
  color: var(--texte-faible);
  font-style: italic;
}

/* --- Mouvement réduit ----------------------------------------------------
   Plus de rotation, plus de perspective : un simple basculement, la face
   cachée devenant invisible tout en continuant d'occuper sa cellule, pour
   que la hauteur de la fiche ne bouge pas. */
@media (prefers-reduced-motion: reduce) {
  .fiche {
    perspective: none;
  }

  .fiche__pivot,
  .fiche[data-face="arriere"] .fiche__pivot {
    transition: none;
    transform: none;
  }

  .fiche__face,
  .fiche__face--arriere {
    transform: none;
    backface-visibility: visible;
    -webkit-backface-visibility: visible;
  }

  .fiche__face[data-visible="non"] {
    visibility: hidden;
  }
}
`;

/** Dépose la feuille intégrée au premier rendu, et une seule fois. */
function assurerStyles() {
  if (typeof document === 'undefined' || !document.head) return;
  if (document.getElementById(ID_STYLES)) return;

  /* `textContent` sur un <style> : c'est une constante du module, jamais de
     la donnée, et rien ne passe par innerHTML. */
  const feuille = el('style', { id: ID_STYLES });
  feuille.textContent = STYLES;
  document.head.insertBefore(feuille, document.head.firstChild);
}
