/* =========================================================================
   ETII Hub — Module de l'organigramme (SPEC.md §4.4)

   Responsabilités, et rien d'autre :

     1. Démarrer le thème et marquer la page courante dans la navigation.
     2. Charger organigramme.json et en rendre les trois états —
        chargement, erreur, vide — via avecEtat() de data.js.
     3. Afficher la direction puis les squads, chacune avec son leader mis
        en avant et ses membres.
     4. Permettre la réorganisation : par glisser-déposer À LA SOURIS, et
        par une modale « Déplacer… » AU CLAVIER — les deux chemins mènent
        exactement à la même fonction, deplacer().
     5. Mémoriser les changements localement et pouvoir tout remettre à zéro.

   Points de conception notables :

   - IDENTITÉ PAR RÉFÉRENCE, JAMAIS PAR CHAÎNE (SPEC §6.6). Un nom de
     squad peut contenir une apostrophe, un guillemet ou un chevron. Aucun
     sélecteur, aucun identifiant et aucun gestionnaire n'est donc construit
     par concaténation d'un nom : chaque élément de l'interface est relié à
     son groupe ou à sa personne par des WeakMap, et les noms ne voyagent
     que comme textContent. Le bug legacy est structurellement impossible.

   - LES DONNÉES DU JSON NE SONT JAMAIS MODIFIÉES. Le modèle de travail est
     reconstruit à chaque chargement à partir du JSON ; les personnes qu'il
     contient sont des objets neufs. La réinitialisation n'a donc rien à
     restaurer : elle rebâtit simplement le modèle depuis la source.

   - LA SAUVEGARDE NE PORTE QUE DES IDENTIFIANTS. Elle décrit qui est dans
     quel groupe, pas qui est qui. Si elle ne recouvre pas exactement le
     même ensemble d'identifiants que le JSON, elle est ignorée en bloc :
     une sauvegarde d'une version antérieure des données ne peut ni faire
     disparaître ni ressusciter quelqu'un.

   - LE ZOOM NE DÉFORME RIEN. Il pose un facteur sur une variable CSS, et
     la grille reflue réellement (cf. <style> de la page). Pas de
     transform: scale(), banni par la SPEC §2.

   Tout le DOM produit ici passe par el() / svg() / frag() / monter() : le
   texte est inséré en textContent, jamais en innerHTML, et aucun
   gestionnaire n'est écrit en attribut HTML (SPEC §8).
   ========================================================================= */

import {
  el, svg, frag, monter, deleguer, ouvrirModale, toast, annoncer,
  debounce, stockage, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';

/* -------------------------------------------------------------------------
   0. Constantes
   ------------------------------------------------------------------------- */

/** Clé de la réorganisation locale. */
const CLE_ETAT = 'organigramme:etat';

/** Clé du niveau de zoom. */
const CLE_ZOOM = 'organigramme:zoom';

/** Version du format de sauvegarde : une sauvegarde d'un autre format est
    ignorée plutôt que réinterprétée de travers. */
const VERSION_ETAT = 1;

/** Bornes du zoom, en pourcentage. Miroir des attributs du curseur HTML. */
const ZOOM_MIN = 80;
const ZOOM_MAX = 160;
const ZOOM_PAS = 10;
const ZOOM_DEFAUT = 100;

/** Délai d'anti-rebond de la recherche : court, la liste est en mémoire. */
const DELAI_FILTRE = 120;

/** Nom du groupe de direction. Il n'est ni renommable ni supprimable. */
const NOM_DIRECTION = 'Direction';

/* -------------------------------------------------------------------------
   1. État du module
   ------------------------------------------------------------------------- */

/** Données brutes telles que lues dans le JSON. JAMAIS modifiées. */
let donneesSource = null;

/**
 * Modèle de travail.
 * @type {{groupes: Array, parId: Map<string, object>, sequence: number}|null}
 */
let modele = null;

/** Éléments statiques de la page, résolus une fois au démarrage. */
const refs = {
  racine: null,
  conteneur: null,
  recherche: null,
  effacer: null,
  resume: null,
  zoom: null,
  zoomMoins: null,
  zoomPlus: null,
  zoomValeur: null,
  nouvelleSquad: null,
  reinitialiser: null
};

/* Liens élément -> donnée. Une WeakMap plutôt qu'un attribut : la donnée
   n'est jamais sérialisée dans le DOM, donc jamais reparsée, donc jamais
   cassée par un caractère spécial. Les entrées disparaissent d'elles-mêmes
   avec les éléments à chaque nouveau rendu. */
const groupeParElement = new WeakMap();
const personneParElement = new WeakMap();

/** Personne -> parties de sa carte, reconstruite à chaque rendu. */
let vueParPersonne = new Map();

/** Personne actuellement glissée, ou null. */
let personneGlissee = null;

/** Compteur d'identifiants internes (aria-labelledby, groupes de radios). */
let compteurId = 0;

/* -------------------------------------------------------------------------
   2. Utilitaires
   ------------------------------------------------------------------------- */

/**
 * Identifiant technique unique. Ne contient QUE le compteur : aucune
 * donnée, donc aucun caractère à échapper.
 * @param {string} prefixe
 * @returns {string}
 */
function idUnique(prefixe) {
  compteurId += 1;
  return prefixe + '-' + compteurId;
}

/**
 * Chaîne nettoyée, ou chaîne vide si la valeur n'en est pas une.
 * @param {*} valeur
 * @returns {string}
 */
function texte(valeur) {
  return typeof valeur === 'string' ? valeur.trim() : '';
}

/**
 * Accord en nombre, sans dépendance ni Intl.PluralRules.
 * @param {number} n
 * @param {string} singulier
 * @param {string} pluriel
 * @returns {string}
 */
function accorder(n, singulier, pluriel) {
  return n + ' ' + (n > 1 ? pluriel : singulier);
}

/* Marques combinantes laissées par NFD. Construite par RegExp pour que la
   plage de points de code reste lisible dans le source, plutôt que d'y
   inscrire des caractères invisibles. */
const MARQUES = new RegExp('[\\u0300-\\u036f]', 'g');

/**
 * Normalisation de comparaison : minuscules, sans diacritiques.
 * Même principe que search.js, en beaucoup plus simple — l'organigramme
 * n'a pas besoin d'un index inversé pour 65 cartes tenues en mémoire.
 * @param {*} valeur
 * @returns {string}
 */
function normaliser(valeur) {
  const brut = typeof valeur === 'string' ? valeur : String(valeur || '');
  try {
    return brut.normalize('NFD').replace(MARQUES, '').toLowerCase();
  } catch (_e) {
    return brut.toLowerCase();
  }
}

/**
 * Nom d'une squad, encadré de guillemets français pour les messages.
 * La valeur n'est jamais interprétée : elle finit en textContent.
 * @param {object} groupe
 * @returns {string}
 */
function cite(groupe) {
  return '« ' + groupe.nom + ' »';
}

/* -------------------------------------------------------------------------
   3. Modèle
   ------------------------------------------------------------------------- */

/**
 * Construit le modèle de travail à partir du JSON.
 * Les objets produits sont neufs : le JSON reste intact, ce qui permet de
 * réinitialiser sans avoir rien à sauvegarder.
 *
 * @param {object} donnees contenu de organigramme.json
 * @returns {{groupes: Array, parId: Map, sequence: number}}
 */
function construireModele(donnees) {
  verifierForme(donnees, {
    direction: 'tableau',
    squads: { type: 'tableau', elements: { nom: 'chaine', membres: 'tableau' } }
  }, 'organigramme.json');

  const etat = { groupes: [], parId: new Map(), sequence: 0 };

  const direction = creerGroupe(etat, NOM_DIRECTION, true);
  for (const brut of donnees.direction) ajouterPersonne(etat, direction, brut);

  for (const squad of donnees.squads) {
    const groupe = creerGroupe(etat, texte(squad.nom) || 'Squad', false);
    for (const brut of squad.membres) ajouterPersonne(etat, groupe, brut);
  }

  for (const groupe of etat.groupes) normaliserRoles(groupe);
  return etat;
}

/**
 * Crée un groupe et l'ajoute au modèle.
 * @param {object} etat
 * @param {string} nom
 * @param {boolean} direction
 * @returns {object}
 */
function creerGroupe(etat, nom, direction) {
  etat.sequence += 1;
  const groupe = {
    /* Identifiant purement interne, jamais issu du nom : c'est lui, et non
       le libellé, qui circule dans les <option> de la modale. */
    id: 'g' + etat.sequence,
    nom: nom,
    direction: direction === true,
    membres: []
  };
  etat.groupes.push(groupe);
  return groupe;
}

/**
 * Convertit une entrée JSON en personne du modèle.
 * Une entrée sans identifiant, ou dont l'identifiant est déjà pris, est
 * ignorée : mieux vaut une carte de moins qu'un doublon fantôme.
 *
 * @param {object} etat
 * @param {object} groupe
 * @param {*} brut
 */
function ajouterPersonne(etat, groupe, brut) {
  if (!brut || typeof brut !== 'object') return;

  const id = texte(brut.id);
  if (!id || etat.parId.has(id)) return;

  const personne = {
    id: id,
    nom: texte(brut.nom) || id,
    poste: texte(brut.poste),
    perimetre: texte(brut.perimetre),
    role: brut.role === 'leader' ? 'leader' : 'membre'
  };

  etat.parId.set(id, personne);
  groupe.membres.push(personne);
}

/**
 * Garantit l'invariant « au plus un leader par groupe », et place ce
 * leader en tête. Un groupe peut légitimement n'en avoir aucun : c'est le
 * cas juste après avoir déplacé son leader ailleurs.
 * @param {object} groupe
 */
function normaliserRoles(groupe) {
  let trouve = false;
  for (const personne of groupe.membres) {
    if (personne.role !== 'leader') continue;
    if (trouve) personne.role = 'membre';
    else trouve = true;
  }
}

/** Leader d'un groupe, ou null. */
function leaderDe(groupe) {
  for (const personne of groupe.membres) {
    if (personne.role === 'leader') return personne;
  }
  return null;
}

/** Membres non leaders d'un groupe. */
function membresDe(groupe) {
  return groupe.membres.filter((personne) => personne.role !== 'leader');
}

/** Groupe contenant une personne, ou null. */
function groupeDe(personne) {
  if (!modele) return null;
  for (const groupe of modele.groupes) {
    if (groupe.membres.indexOf(personne) !== -1) return groupe;
  }
  return null;
}

/** Nombre total de personnes du modèle. */
function effectif(etat) {
  return etat && etat.parId ? etat.parId.size : 0;
}

/* -------------------------------------------------------------------------
   4. Persistance locale
   ------------------------------------------------------------------------- */

/**
 * Sérialise la réorganisation courante : uniquement la structure et des
 * identifiants. Aucune donnée personnelle n'est recopiée dans le stockage.
 * @returns {object}
 */
function serialiser() {
  return {
    version: VERSION_ETAT,
    groupes: modele.groupes.map((groupe) => {
      const leader = leaderDe(groupe);
      return {
        nom: groupe.nom,
        direction: groupe.direction === true,
        leader: leader ? leader.id : null,
        membres: groupe.membres.map((personne) => personne.id)
      };
    })
  };
}

/** Enregistre la réorganisation. Un stockage indisponible n'est pas une
    erreur : la page reste pleinement utilisable, elle perd sa mémoire. */
function enregistrer() {
  stockage.ecrire(CLE_ETAT, serialiser());
}

/**
 * Applique une sauvegarde au modèle fraîchement construit.
 *
 * Tout ou rien : à la moindre incohérence (identifiant inconnu, personne
 * en double, personne manquante, aucun groupe de direction) la sauvegarde
 * est refusée et le modèle reste celui du JSON.
 *
 * @param {object} etat modèle issu du JSON, modifié sur place en cas de succès
 * @param {*} sauvegarde
 * @returns {boolean} vrai si la sauvegarde a été appliquée
 */
function appliquerSauvegarde(etat, sauvegarde) {
  if (!sauvegarde || typeof sauvegarde !== 'object') return false;
  if (sauvegarde.version !== VERSION_ETAT) return false;
  if (!Array.isArray(sauvegarde.groupes) || sauvegarde.groupes.length === 0) return false;

  const vus = new Set();
  const reconstruits = [];
  let sequence = 0;
  let directions = 0;

  for (const brut of sauvegarde.groupes) {
    if (!brut || typeof brut !== 'object') return false;
    if (!Array.isArray(brut.membres)) return false;

    const membres = [];
    for (const id of brut.membres) {
      if (typeof id !== 'string') return false;
      if (vus.has(id)) return false;                 // personne en double
      const personne = etat.parId.get(id);
      if (!personne) return false;                   // identifiant inconnu
      vus.add(id);
      membres.push(personne);
    }

    const estDirection = brut.direction === true;
    if (estDirection) directions += 1;

    sequence += 1;
    reconstruits.push({
      groupe: {
        id: 'g' + sequence,
        nom: estDirection ? NOM_DIRECTION : (texte(brut.nom) || 'Squad'),
        direction: estDirection,
        membres: membres
      },
      leader: typeof brut.leader === 'string' ? brut.leader : null
    });
  }

  if (directions !== 1) return false;
  if (vus.size !== etat.parId.size) return false;    // quelqu'un manquerait

  /* La sauvegarde est cohérente : on bascule le modèle dessus. Les rôles
     sont réattribués à partir du seul leader déclaré par groupe. */
  for (const entree of reconstruits) {
    for (const personne of entree.groupe.membres) personne.role = 'membre';
    if (entree.leader) {
      const leader = etat.parId.get(entree.leader);
      if (leader && entree.groupe.membres.indexOf(leader) !== -1) leader.role = 'leader';
    }
    normaliserRoles(entree.groupe);
  }

  etat.groupes = reconstruits.map((entree) => entree.groupe);
  etat.sequence = sequence;

  /* La direction d'abord, l'ordre des squads ensuite : la lecture de la
     page ne dépend pas de l'ordre dans lequel la sauvegarde a été écrite. */
  etat.groupes.sort((a, b) => (a.direction === b.direction) ? 0 : (a.direction ? -1 : 1));
  return true;
}

/* -------------------------------------------------------------------------
   5. Avatars générés localement (SPEC §4.4)
   ------------------------------------------------------------------------- */

/**
 * Teinte HSL dérivée de l'identifiant, entre 0 et 359.
 *
 * Hachage FNV-1a 32 bits : deux identifiants voisins (« p01 » et « p02 »)
 * donnent des teintes éloignées, là où une somme pondérée naïve les
 * rendrait indiscernables. Entièrement déterministe : la même personne a
 * toujours la même couleur, d'une visite à l'autre et d'un poste à l'autre.
 *
 * @param {string} id
 * @returns {number}
 */
function teinteDe(id) {
  const chaine = String(id);
  let hachage = 2166136261;
  for (let i = 0; i < chaine.length; i += 1) {
    hachage ^= chaine.charCodeAt(i);
    hachage = Math.imul(hachage, 16777619);
  }
  return (hachage >>> 0) % 360;
}

/**
 * Initiales affichées dans l'avatar : première lettre, puis le numéro s'il
 * y en a un (« Personne 03 » -> « P03 »). Trois caractères au maximum.
 * @param {object} personne
 * @returns {string}
 */
function initialesDe(personne) {
  const mots = String(personne.nom || personne.id || '')
    .split(/\s+/)
    .filter(Boolean);

  if (mots.length === 0) return '?';

  const premier = mots[0].charAt(0).toUpperCase();
  const dernier = mots[mots.length - 1];

  if (mots.length > 1 && /^\d+$/.test(dernier)) {
    return (premier + dernier).slice(0, 3);
  }
  if (mots.length > 1) {
    return premier + dernier.charAt(0).toUpperCase();
  }
  return mots[0].slice(0, 2).toUpperCase();
}

/**
 * Avatar SVG inline : un disque teinté et des initiales.
 *
 * Aucun appel réseau, aucun service tiers, aucune image. Le module ne
 * transmet qu'un NOMBRE (--avatar-teinte) ; la formule de couleur vit dans
 * le <style> de la page, avec une saturation et une clarté fixes qui
 * garantissent le contraste des initiales dans les deux thèmes.
 *
 * L'avatar est décoratif : le nom est écrit juste à côté, donc il est
 * masqué aux lecteurs d'écran plutôt qu'annoncé deux fois.
 *
 * @param {object} personne
 * @returns {SVGElement}
 */
function avatarDe(personne) {
  return svg('svg', {
    class: 'avatar',
    viewBox: '0 0 40 40',
    'aria-hidden': 'true',
    focusable: 'false',
    style: { '--avatar-teinte': teinteDe(personne.id) }
  },
  svg('circle', { class: 'avatar__fond', cx: '20', cy: '20', r: '20' }),
  svg('text', {
    class: 'avatar__initiales',
    x: '20',
    y: '20',
    'text-anchor': 'middle',
    'dominant-baseline': 'central',
    'font-size': '14',
    'font-weight': '700'
  }, initialesDe(personne)));
}

/* -------------------------------------------------------------------------
   6. Rendu
   ------------------------------------------------------------------------- */

/**
 * Rend l'organigramme entier dans le conteneur, en une seule mutation.
 * Appelé par avecEtat() au premier chargement, puis après chaque
 * changement — c'est le seul endroit qui écrit dans le conteneur.
 */
function rendre() {
  if (!modele || !refs.conteneur) return;

  vueParPersonne = new Map();
  monter(refs.conteneur, frag(
    ...modele.groupes.map((groupe) => vueGroupe(groupe))
  ));

  /* Le filtre courant est réappliqué au DOM neuf : une recherche en cours
     ne doit pas être perdue parce qu'une personne a changé de squad. */
  appliquerFiltre(false);
}

/**
 * Bloc d'une squad : en-tête (zone de dépôt « leader »), puis corps
 * (zone de dépôt « membre »).
 * @param {object} groupe
 * @returns {HTMLElement}
 */
function vueGroupe(groupe) {
  const idTitre = idUnique('org-groupe');
  const leader = leaderDe(groupe);
  const membres = membresDe(groupe);

  const titre = el('h2', { class: 'org-groupe__titre', id: idTitre }, groupe.nom);

  const renommer = groupe.direction ? null : el('button', {
    class: 'bouton bouton--discret bouton--compact',
    type: 'button',
    dataset: { action: 'renommer' },
    /* Le nom part en attribut aria-label, donc en texte : le navigateur
       l'échappe lui-même, et aucun sélecteur ne le relira jamais. */
    ariaLabel: 'Renommer la squad ' + cite(groupe)
  }, 'Renommer');
  if (renommer) groupeParElement.set(renommer, groupe);

  const entete = el('header', {
    class: 'org-groupe__entete org-depot',
    dataset: { depot: 'leader' }
  },
  titre,
  el('span', { class: 'badge badge--neutre' },
    accorder(groupe.membres.length, 'personne', 'personnes')),
  renommer,
  el('p', { class: 'org-indice' },
    'Déposer une personne ici pour la nommer leader'));
  groupeParElement.set(entete, groupe);

  const corps = el('div', {
    class: 'org-groupe__corps org-depot',
    dataset: { depot: 'membre' }
  },
  el('p', { class: 'org-etiquette' }, groupe.direction ? 'Responsable' : 'Leader'),
  leader
    ? el('ul', { class: 'org-grille' }, vuePersonne(leader, groupe))
    : etatVide('Aucun leader désigné',
      'Déposez une personne sur le titre de cette squad, ou choisissez le '
      + 'rôle « Leader » depuis le bouton « Déplacer… » d’une carte.'),

  el('p', { class: 'org-etiquette' },
    groupe.direction ? 'Autres membres' : 'Membres (' + membres.length + ')'),
  membres.length
    ? el('ul', { class: 'org-grille' },
      membres.map((personne) => vuePersonne(personne, groupe)))
    : etatVide('Aucun membre',
      'Faites glisser une carte jusqu’ici, ou utilisez le bouton '
      + '« Déplacer… » d’une carte.'));
  groupeParElement.set(corps, groupe);

  return el('section', {
    class: 'carte org-groupe',
    ariaLabelledby: idTitre
  }, entete, corps);
}

/**
 * Carte d'une personne : avatar, libellé, poste, périmètre, et le bouton
 * « Déplacer… » qui est l'équivalent clavier du glisser-déposer.
 *
 * @param {object} personne
 * @param {object} groupe groupe d'appartenance, pour l'étiquette du bouton
 * @returns {HTMLElement} un <li>
 */
function vuePersonne(personne, groupe) {
  const estLeader = personne.role === 'leader';

  const bouton = el('button', {
    class: 'bouton bouton--discret bouton--compact',
    type: 'button',
    dataset: { action: 'deplacer' },
    ariaLabel: 'Déplacer ' + personne.nom + ', '
      + (estLeader ? 'leader' : 'membre') + ' de ' + cite(groupe)
  }, 'Déplacer…');
  personneParElement.set(bouton, personne);

  const carte = el('article', {
    class: ['carte', 'carte--compacte', 'personne',
      estLeader ? 'carte--mise-en-avant' : null],
    draggable: 'true',
    dataset: { personne: '' }
  },
  el('div', { class: 'personne__tete' },
    avatarDe(personne),
    el('div', { class: 'personne__identite' },
      el('p', { class: 'personne__nom' }, personne.nom),
      el('p', { class: 'personne__poste' },
        personne.poste || 'Poste non précisé'))),

  el('div', { class: 'personne__pied' },
    el('div', { class: 'rangee rangee--serree' },
      estLeader ? el('span', { class: 'badge badge--accent' }, 'Leader') : null,
      personne.perimetre
        ? el('span', { class: 'badge badge--neutre' }, personne.perimetre)
        : null),
    bouton));
  personneParElement.set(carte, personne);

  vueParPersonne.set(personne, { carte: carte, bouton: bouton, groupe: groupe });
  return el('li', {}, carte);
}

/**
 * État vide interne à une squad. Réutilise le composant de components.css.
 * @param {string} titre
 * @param {string} explication
 * @returns {HTMLElement}
 */
function etatVide(titre, explication) {
  return el('div', { class: 'etat-vide etat-vide--compact etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '＋'),
    el('p', { class: 'etat-vide__titre' }, titre),
    el('p', { class: 'etat-vide__texte' }, explication));
}

/**
 * Gabarit affiché pendant le chargement. Il a la forme de ce qui va
 * arriver — deux blocs de squad — pour éviter le saut de mise en page.
 * @param {Element} cible
 */
function squelette(cible) {
  const bloc = () => el('section', { class: 'carte org-groupe' },
    el('div', { class: 'org-groupe__entete' },
      el('span', { class: 'squelette squelette--ligne squelette--titre' })),
    el('div', { class: 'org-groupe__corps' },
      el('div', { class: 'org-grille' },
        [0, 1, 2, 3].map(() => el('div', { class: 'carte carte--compacte' },
          el('div', { class: 'personne__tete' },
            el('span', { class: 'squelette squelette--avatar' }),
            el('div', { class: 'squelette-groupe pleine-largeur' },
              el('span', { class: 'squelette squelette--ligne squelette--moyen' }),
              el('span', { class: 'squelette squelette--ligne squelette--court' }))))))));

  const enveloppe = el('div', {
    class: 'pile pile--lache',
    ariaHidden: 'true'
  }, bloc(), bloc());

  monter(cible, enveloppe);
}

/* -------------------------------------------------------------------------
   7. Déplacement — le cœur, partagé par la souris et le clavier
   ------------------------------------------------------------------------- */

/**
 * Déplace une personne vers un groupe, avec un rôle.
 *
 * C'est l'unique point d'entrée : le glisser-déposer et la modale y
 * arrivent tous les deux, donc les deux chemins ne peuvent pas diverger.
 * Promouvoir quelqu'un rétrograde l'ancien leader (SPEC §4.4).
 *
 * @param {object} personne
 * @param {object} cible groupe de destination
 * @param {string} role 'leader' ou 'membre'
 * @returns {boolean} vrai si quelque chose a changé
 */
function deplacer(personne, cible, role) {
  if (!personne || !cible || !modele) return false;

  const source = groupeDe(personne);
  if (!source) return false;

  const versLeader = role === 'leader';
  const etaitLeader = personne.role === 'leader';

  /* Rien à faire : on le dit, plutôt que de laisser croire à un échec. */
  if (source === cible && versLeader === etaitLeader) {
    toast(personne.nom + ' est déjà '
      + (versLeader ? 'leader' : 'membre') + ' de ' + cite(cible) + '.', 'info');
    return false;
  }

  const position = source.membres.indexOf(personne);
  if (position !== -1) source.membres.splice(position, 1);

  let retrograde = null;

  if (versLeader) {
    retrograde = leaderDe(cible);
    if (retrograde) retrograde.role = 'membre';
    personne.role = 'leader';
    cible.membres.unshift(personne);
  } else {
    personne.role = 'membre';
    cible.membres.push(personne);
  }

  normaliserRoles(cible);
  enregistrer();
  rendre();

  /* Un seul message, dans la région vivante des notifications : toast()
     annonce déjà aux lecteurs d'écran, inutile d'y ajouter annoncer(). */
  let message;
  if (source === cible) {
    message = versLeader
      ? personne.nom + ' devient leader de ' + cite(cible) + '.'
      : personne.nom + ' n’est plus leader de ' + cite(cible) + '.';
  } else {
    message = personne.nom + ' rejoint ' + cite(cible)
      + (versLeader ? ' comme leader.' : ' comme membre.');
  }
  if (retrograde) message += ' ' + retrograde.nom + ' redevient membre.';

  toast(message, 'succes');
  return true;
}

/** Redonne le focus au bouton « Déplacer… » d'une personne après un rendu. */
function focaliserPersonne(personne) {
  const vue = vueParPersonne.get(personne);
  if (!vue || !vue.bouton) return;
  try { vue.bouton.focus(); } catch (_e) { /* élément détaché : sans effet */ }
}

/* -------------------------------------------------------------------------
   8. Glisser-déposer
   ------------------------------------------------------------------------- */

/**
 * Câble le glisser-déposer, une fois pour toutes, sur le conteneur.
 * Sept écouteurs au total quel que soit le nombre de cartes : la
 * délégation évite d'en poser 65 × 5 à chaque rendu.
 */
function cablerGlisserDeposer() {
  const racine = refs.conteneur;

  deleguer(racine, '[data-personne]', 'dragstart', (evt, carte) => {
    const personne = personneParElement.get(carte);
    if (!personne) return;

    personneGlissee = personne;
    try {
      /* Le texte transporté n'est qu'un repli : la personne réelle est
         tenue par référence. Rien n'est jamais relu depuis le DOM. */
      evt.dataTransfer.setData('text/plain', personne.id);
      evt.dataTransfer.effectAllowed = 'move';
    } catch (_e) { /* transfert indisponible : le repli suffit */ }

    carte.dataset.glisse = '';
    try { document.documentElement.dataset.orgGlisse = ''; } catch (_e) { /* ignoré */ }
  });

  deleguer(racine, '[data-personne]', 'dragend', (evt, carte) => {
    personneGlissee = null;
    delete carte.dataset.glisse;
    terminerGlissement();
  });

  /* dragenter ET dragover doivent annuler l'événement : sans cela, le
     navigateur refuse le dépôt. */
  const survoler = (evt, zone) => {
    if (!personneGlissee) return;
    evt.preventDefault();
    try { evt.dataTransfer.dropEffect = 'move'; } catch (_e) { /* ignoré */ }
    zone.dataset.survol = '';
  };

  deleguer(racine, '[data-depot]', 'dragenter', survoler);
  deleguer(racine, '[data-depot]', 'dragover', survoler);

  deleguer(racine, '[data-depot]', 'dragleave', (evt, zone) => {
    /* Passer d'un enfant à un autre déclenche un dragleave : on ne retire
       le repère que si le pointeur quitte réellement la zone. */
    const vers = evt.relatedTarget;
    if (vers && vers.nodeType === 1 && zone.contains(vers)) return;
    delete zone.dataset.survol;
  });

  deleguer(racine, '[data-depot]', 'drop', (evt, zone) => {
    evt.preventDefault();
    delete zone.dataset.survol;

    const groupe = groupeParElement.get(zone);
    const personne = personneGlissee || personneDepuisTransfert(evt);
    personneGlissee = null;
    terminerGlissement();

    if (!groupe || !personne) return;
    deplacer(personne, groupe, zone.dataset.depot === 'leader' ? 'leader' : 'membre');
  });
}

/**
 * Repli lorsque la référence glissée s'est perdue (glissement entre deux
 * fenêtres, par exemple) : on retrouve la personne par son identifiant.
 * @param {DragEvent} evt
 * @returns {object|null}
 */
function personneDepuisTransfert(evt) {
  if (!modele) return null;
  let id = '';
  try { id = evt.dataTransfer.getData('text/plain'); } catch (_e) { return null; }
  return (typeof id === 'string' && modele.parId.has(id))
    ? modele.parId.get(id)
    : null;
}

/** Retire tous les repères de glissement encore posés. */
function terminerGlissement() {
  try { delete document.documentElement.dataset.orgGlisse; } catch (_e) { /* ignoré */ }
  if (!refs.conteneur) return;
  for (const zone of refs.conteneur.querySelectorAll('[data-survol]')) {
    delete zone.dataset.survol;
  }
}

/* -------------------------------------------------------------------------
   9. Équivalent clavier : la modale « Déplacer… » (SPEC §4.4)
   ------------------------------------------------------------------------- */

/**
 * Ouvre la modale de déplacement d'une personne.
 * Le glisser-déposer seul serait inaccessible : cette modale est le
 * chemin de plein droit, pas un pis-aller.
 *
 * @param {object} personne
 * @param {Element} declencheur bouton à refocaliser à la fermeture
 */
function ouvrirModaleDeplacement(personne, declencheur) {
  const source = groupeDe(personne);
  if (!source) return;

  const idSelect = idUnique('org-destination');
  const nomRadios = idUnique('org-role');
  const etaitLeader = personne.role === 'leader';

  let select = null;
  let radioLeader = null;

  /* Les <option> portent l'identifiant INTERNE du groupe, jamais son nom :
     un nom contenant une apostrophe ou un chevron n'a donc aucun chemin
     par lequel casser quoi que ce soit (SPEC §6.6). */
  select = el('select', { class: 'champ__controle', id: idSelect },
    modele.groupes.map((groupe) => el('option', { value: groupe.id }, groupe.nom)));
  select.value = source.id;

  const champDestination = el('p', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idSelect }, 'Destination'),
    el('span', { class: 'champ__select' }, select),
    el('span', { class: 'champ__aide' },
      'La liste contient la direction et toutes les squads.'));

  const champRole = el('fieldset', { class: 'groupe-champs' },
    el('legend', { class: 'groupe-champs__legende' }, 'Rôle'),
    el('label', { class: 'case' },
      el('input', {
        class: 'case__controle', type: 'radio', name: nomRadios,
        value: 'membre', checked: !etaitLeader
      }),
      el('span', { class: 'case__texte' }, 'Membre')),
    el('label', { class: 'case' },
      el('input', {
        class: 'case__controle', type: 'radio', name: nomRadios,
        value: 'leader', checked: etaitLeader,
        ref: (noeud) => { radioLeader = noeud; }
      }),
      el('span', { class: 'case__texte' },
        'Leader — l’ancien leader redevient membre')));

  /* Refocalisation à la fermeture, quelle qu'en soit la raison : le bouton
     d'origine a été détruit par le rendu, on vise donc la carte telle
     qu'elle existe MAINTENANT. */
  ouvrirModale({
    titre: 'Déplacer ' + personne.nom,
    declencheur: declencheur,
    contenu: [
      el('p', {}, personne.poste
        ? personne.poste + ' — actuellement '
          + (etaitLeader ? 'leader' : 'membre') + ' de ' + cite(source) + '.'
        : 'Actuellement ' + (etaitLeader ? 'leader' : 'membre')
          + ' de ' + cite(source) + '.'),
      champDestination,
      champRole
    ],
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      {
        libelle: 'Déplacer',
        variante: 'principal',
        onClick: () => {
          const cible = modele.groupes.find((groupe) => groupe.id === select.value);
          if (!cible) return false;
          deplacer(personne, cible, radioLeader && radioLeader.checked ? 'leader' : 'membre');
        }
      }
    ],
    onFermeture: () => focaliserPersonne(personne)
  });
}

/* -------------------------------------------------------------------------
   10. Modale à un champ : création et renommage de squad
   Jamais prompt() : ni stylable, ni traduisible, ni utilisable au clavier
   de façon cohérente — et bloquant pour tout le navigateur.
   ------------------------------------------------------------------------- */

/**
 * Ouvre une modale demandant un nom.
 *
 * @param {object} options
 *        titre, etiquette, valeur, aide, libelleAction, declencheur
 *        onValider(nom) — appelée avec le nom saisi et nettoyé
 */
function ouvrirModaleNom(options) {
  const idChamp = idUnique('org-nom');
  const idErreur = idUnique('org-nom-erreur');

  const erreur = el('span', {
    class: 'champ__erreur',
    id: idErreur,
    role: 'alert',
    hidden: true
  }, 'Saisissez un nom : il ne peut pas être vide.');

  let champ = null;

  /**
   * Valide la saisie. Renvoie false pour laisser la modale ouverte.
   * @param {object} api
   * @returns {boolean|undefined}
   */
  function valider(api) {
    const valeur = texte(champ ? champ.value : '');
    if (!valeur) {
      erreur.hidden = false;
      if (champ) {
        champ.setAttribute('aria-invalid', 'true');
        try { champ.focus(); } catch (_e) { /* ignoré */ }
      }
      return false;
    }
    options.onValider(valeur);
    if (api && typeof api.fermer === 'function') api.fermer('action');
    return true;
  }

  ouvrirModale({
    titre: options.titre,
    declencheur: options.declencheur,
    contenu: (api) => {
      champ = el('input', {
        class: 'champ__controle',
        id: idChamp,
        type: 'text',
        value: options.valeur || '',
        autocomplete: 'off',
        maxlength: '80',
        autofocus: true,
        ariaDescribedby: idErreur,
        onInput: () => {
          erreur.hidden = true;
          champ.removeAttribute('aria-invalid');
        },
        /* Entrée valide, comme dans n'importe quel formulaire. */
        onKeyDown: (evt) => {
          if (evt.key !== 'Enter') return;
          evt.preventDefault();
          valider(api);
        }
      });

      return el('p', { class: 'champ' },
        el('label', { class: 'champ__etiquette', for: idChamp }, options.etiquette),
        champ,
        el('span', { class: 'champ__aide' }, options.aide),
        erreur);
    },
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      {
        libelle: options.libelleAction,
        variante: 'principal',
        /* `ferme: false` : c'est valider() qui décide de refermer, une fois
           la saisie acceptée. */
        ferme: false,
        onClick: (evt, api) => valider(api)
      }
    ]
  });
}

/** Modale de création d'une squad. */
function ouvrirCreationSquad(declencheur) {
  ouvrirModaleNom({
    titre: 'Nouvelle squad',
    etiquette: 'Nom de la squad',
    valeur: '',
    aide: 'Tous les caractères sont acceptés, apostrophes et guillemets compris.',
    libelleAction: 'Créer',
    declencheur: declencheur,
    onValider: (nom) => {
      const groupe = creerGroupe(modele, nom, false);
      enregistrer();
      rendre();
      toast('Squad ' + cite(groupe) + ' créée. Elle attend ses membres.', 'succes');
    }
  });
}

/** Modale de renommage d'une squad. */
function ouvrirRenommageSquad(groupe, declencheur) {
  const ancien = groupe.nom;
  ouvrirModaleNom({
    titre: 'Renommer la squad',
    etiquette: 'Nouveau nom',
    valeur: ancien,
    aide: 'Tous les caractères sont acceptés, apostrophes et guillemets compris.',
    libelleAction: 'Renommer',
    declencheur: declencheur,
    onValider: (nom) => {
      if (nom === ancien) return;
      groupe.nom = nom;
      enregistrer();
      rendre();
      toast('« ' + ancien +' » s’appelle désormais ' + cite(groupe) + '.', 'succes');
    }
  });
}

/* -------------------------------------------------------------------------
   11. Réinitialisation — confirmée explicitement (SPEC §6 point 5)
   ------------------------------------------------------------------------- */

/**
 * Demande confirmation avant de défaire toutes les réorganisations.
 * Le bouton par défaut est « Annuler » : une validation par réflexe ne
 * détruit rien.
 * @param {Element} declencheur
 */
function confirmerReinitialisation(declencheur) {
  ouvrirModale({
    titre: 'Réinitialiser l’organigramme ?',
    declencheur: declencheur,
    contenu: [
      el('p', {},
        'Toutes les réorganisations faites sur ce poste — changements de '
        + 'squad, promotions, squads créées ou renommées — seront perdues.'),
      el('p', {},
        'L’organigramme reviendra exactement à ce que décrit le fichier de '
        + 'données. Cette action ne peut pas être annulée.')
    ],
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', autofocus: true },
      {
        libelle: 'Réinitialiser',
        variante: 'danger',
        onClick: () => reinitialiser()
      }
    ]
  });
}

/** Rebâtit le modèle depuis le JSON d'origine et oublie la sauvegarde. */
function reinitialiser() {
  if (!donneesSource) return;

  stockage.supprimer(CLE_ETAT);
  try {
    modele = construireModele(donneesSource);
  } catch (cause) {
    console.error('[organigramme] ' + cause.message, cause);
    toast('Les données d’origine sont illisibles : rien n’a été changé.', 'critique');
    return;
  }

  rendre();
  toast('Organigramme réinitialisé : la répartition d’origine est rétablie.',
    'succes');
}

/* -------------------------------------------------------------------------
   12. Recherche filtrante
   Les cartes hors filtre sont mises en RETRAIT, jamais retirées du flux ni
   de l'ordre de tabulation (SPEC §4.4).
   ------------------------------------------------------------------------- */

/**
 * Applique la recherche courante aux cartes rendues.
 * @param {boolean} annonce vrai pour annoncer le résultat aux lecteurs d'écran
 */
function appliquerFiltre(annonce) {
  if (!refs.recherche || !refs.resume) return;

  const brut = refs.recherche.value || '';
  const requete = normaliser(brut).trim();
  const total = vueParPersonne.size;

  if (!requete) {
    for (const vue of vueParPersonne.values()) delete vue.carte.dataset.horsFiltre;
    refs.resume.textContent = '';
    refs.resume.hidden = true;
    if (annonce) annoncer('Filtre effacé, ' + accorder(total, 'personne affichée', 'personnes affichées') + '.');
    return;
  }

  /* Tous les termes doivent être trouvés : « h160 essais » ne renvoie que
     les personnes qui cumulent les deux. */
  const termes = requete.split(/\s+/).filter(Boolean);
  let trouves = 0;

  for (const [personne, vue] of vueParPersonne) {
    const foin = normaliser([
      personne.nom, personne.poste, personne.perimetre,
      personne.role === 'leader' ? 'leader' : 'membre',
      vue.groupe.nom
    ].join(' '));

    const correspond = termes.every((terme) => foin.indexOf(terme) !== -1);
    if (correspond) {
      trouves += 1;
      delete vue.carte.dataset.horsFiltre;
    } else {
      vue.carte.dataset.horsFiltre = '';
    }
  }

  const message = trouves === 0
    ? 'Aucune personne ne correspond à « ' + brut.trim()
      +' ». Toutes les cartes restent affichées, en retrait.'
    : accorder(trouves, 'personne correspond', 'personnes correspondent')
      + ' à « ' + brut.trim() + ' » sur ' + total
      + '. Les autres sont mises en retrait.';

  refs.resume.textContent = message;
  refs.resume.hidden = false;
  if (annonce) annoncer(message);
}

/* -------------------------------------------------------------------------
   13. Zoom
   Il agit sur la TAILLE DES CARTES via une variable CSS, donc la grille
   reflue pour de bon. Aucun transform sur la page (SPEC §2).
   ------------------------------------------------------------------------- */

/**
 * Ramène une valeur dans les bornes du zoom, arrondie au pas.
 * @param {*} valeur
 * @returns {number}
 */
function bornerZoom(valeur) {
  const nombre = Number(valeur);
  if (!Number.isFinite(nombre)) return ZOOM_DEFAUT;
  const arrondi = Math.round(nombre / ZOOM_PAS) * ZOOM_PAS;
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, arrondi));
}

/**
 * Applique un niveau de zoom.
 * @param {*} valeur pourcentage
 * @param {boolean} memoriser vrai pour l'enregistrer
 */
function appliquerZoom(valeur, memoriser) {
  const pourcent = bornerZoom(valeur);

  if (refs.zoom) refs.zoom.value = String(pourcent);
  if (refs.zoomValeur) refs.zoomValeur.textContent = pourcent + ' %';
  if (refs.racine) {
    /* Un nombre, pas une couleur ni une dimension : la formule qui en tire
       des tailles vit entièrement dans le <style> de la page. */
    refs.racine.style.setProperty('--org-echelle', String(pourcent / 100));
  }
  if (memoriser) stockage.ecrire(CLE_ZOOM, pourcent);
}

/* -------------------------------------------------------------------------
   14. Câblage de la barre d'outils
   ------------------------------------------------------------------------- */

/** Active les contrôles, une fois les données réellement affichées. */
function activerOutils(actif) {
  const controles = [
    refs.recherche, refs.zoom, refs.zoomMoins, refs.zoomPlus,
    refs.nouvelleSquad, refs.reinitialiser
  ];
  for (const controle of controles) {
    if (controle) controle.disabled = !actif;
  }
}

/** Câble la barre d'outils. Appelé une seule fois. */
function cablerOutils() {
  const filtrer = debounce(() => appliquerFiltre(true), DELAI_FILTRE);

  if (refs.recherche) {
    refs.recherche.addEventListener('input', filtrer);
    refs.recherche.addEventListener('keydown', (evt) => {
      /* Échap efface le filtre sans quitter le champ. */
      if (evt.key !== 'Escape' && evt.key !== 'Esc') return;
      if (!refs.recherche.value) return;
      evt.preventDefault();
      refs.recherche.value = '';
      filtrer.annuler();
      appliquerFiltre(true);
    });
  }

  if (refs.effacer) {
    refs.effacer.addEventListener('click', () => {
      refs.recherche.value = '';
      filtrer.annuler();
      appliquerFiltre(true);
      try { refs.recherche.focus(); } catch (_e) { /* ignoré */ }
    });
  }

  if (refs.zoom) {
    refs.zoom.addEventListener('input', () => appliquerZoom(refs.zoom.value, true));
  }
  if (refs.zoomMoins) {
    refs.zoomMoins.addEventListener('click',
      () => appliquerZoom(Number(refs.zoom.value) - ZOOM_PAS, true));
  }
  if (refs.zoomPlus) {
    refs.zoomPlus.addEventListener('click',
      () => appliquerZoom(Number(refs.zoom.value) + ZOOM_PAS, true));
  }

  if (refs.nouvelleSquad) {
    refs.nouvelleSquad.addEventListener('click',
      (evt) => ouvrirCreationSquad(evt.currentTarget));
  }
  if (refs.reinitialiser) {
    refs.reinitialiser.addEventListener('click',
      (evt) => confirmerReinitialisation(evt.currentTarget));
  }
}

/** Câble les boutons des cartes, par délégation : deux écouteurs en tout. */
function cablerCartes() {
  deleguer(refs.conteneur, '[data-action="deplacer"]', 'click', (evt, bouton) => {
    const personne = personneParElement.get(bouton);
    if (personne) ouvrirModaleDeplacement(personne, bouton);
  });

  deleguer(refs.conteneur, '[data-action="renommer"]', 'click', (evt, bouton) => {
    const groupe = groupeParElement.get(bouton);
    if (groupe) ouvrirRenommageSquad(groupe, bouton);
  });
}

/* -------------------------------------------------------------------------
   15. Démarrage
   ------------------------------------------------------------------------- */

/** Résout les éléments statiques de la page. */
function resoudreRefs() {
  refs.racine = document.querySelector('.organigramme');
  refs.conteneur = document.getElementById('organigramme');
  refs.recherche = document.getElementById('org-recherche');
  refs.effacer = document.getElementById('org-effacer');
  refs.resume = document.getElementById('org-resume');
  refs.zoom = document.getElementById('org-zoom');
  refs.zoomMoins = document.getElementById('org-zoom-moins');
  refs.zoomPlus = document.getElementById('org-zoom-plus');
  refs.zoomValeur = document.getElementById('org-zoom-valeur');
  refs.nouvelleSquad = document.getElementById('org-nouvelle-squad');
  refs.reinitialiser = document.getElementById('org-reinitialiser');
}

/**
 * Rendu appelé par avecEtat() : construit le modèle, y applique la
 * sauvegarde si elle est cohérente, puis affiche.
 * @param {object} donnees
 */
function rendreDepuisDonnees(donnees) {
  donneesSource = donnees;
  modele = construireModele(donnees);

  const sauvegarde = stockage.lire(CLE_ETAT, null);
  if (sauvegarde && !appliquerSauvegarde(modele, sauvegarde)) {
    /* Sauvegarde incohérente avec les données : on la jette plutôt que de
       l'appliquer à moitié, et on le dit — le contenu affiché n'est pas
       celui que la personne avait laissé. */
    stockage.supprimer(CLE_ETAT);
    toast('La réorganisation enregistrée ne correspond plus aux données : '
      + 'l’organigramme d’origine est affiché.', 'alerte');
  }

  rendre();
}

/** Point d'entrée. */
function demarrer() {
  initTheme();
  initNav('organigramme');

  resoudreRefs();
  if (!refs.conteneur) return;

  appliquerZoom(stockage.lire(CLE_ZOOM, ZOOM_DEFAUT), false);
  cablerOutils();
  cablerCartes();
  cablerGlisserDeposer();

  avecEtat(refs.conteneur, () => chargerDonnees('organigramme'), (donnees) => {
    rendreDepuisDonnees(donnees);
  }, {
    squelette: squelette,
    texteChargement: 'Chargement de l’organigramme en cours…',
    titreErreur: 'Organigramme indisponible',
    titreVide: 'Aucune équipe à afficher',
    texteVide: 'Le fichier de données ne contient ni direction ni squad. '
      + 'Rien ne peut être organisé pour le moment.',
    estVide: (donnees) => {
      if (!donnees || typeof donnees !== 'object') return true;
      const direction = Array.isArray(donnees.direction) ? donnees.direction.length : 0;
      const squads = Array.isArray(donnees.squads) ? donnees.squads.length : 0;
      return direction === 0 && squads === 0;
    },
    surEtat: (resultat) => {
      const pret = resultat.etat === 'succes';
      activerOutils(pret);
      if (!pret) {
        /* Ni modèle ni cartes : le filtre et le résumé n'ont plus d'objet. */
        vueParPersonne = new Map();
        if (refs.resume) {
          refs.resume.textContent = '';
          refs.resume.hidden = true;
        }
        return;
      }
      annoncer('Organigramme chargé : '
        + accorder(effectif(modele), 'personne', 'personnes') + ' réparties en '
        + accorder(modele.groupes.length, 'groupe', 'groupes') + '.');
    }
  });
}

/* Le module est chargé en `type="module"`, donc différé : le DOM est déjà
   analysé. Le garde-fou couvre le cas d'une insertion manuelle plus tôt. */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', demarrer, { once: true });
} else {
  demarrer();
}
