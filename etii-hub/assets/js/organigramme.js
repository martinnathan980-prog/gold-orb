/* =========================================================================
   ETII Hub — Organigramme

   Le service ETII n'est pas plat. Cette page en rend la hiérarchie réelle :

       ETII                          le service
        ├── direction de service
        └── ETIIA | ETIIE | ETIII    un pôle
             ├── responsable de pôle
             └── squads              leader + membres

   Le pôle affiché voyage dans le hash (`organigramme.html#pole=ETIIA`).
   La valeur « ETII » affiche tout le service ; toute valeur inconnue
   retombe sur « ETII » sans erreur, et l'URL est réécrite en conséquence.

   Ce que la page garantit :
     - tout le DOM est construit avec el()/monter() — aucun innerHTML,
       aucun gestionnaire en attribut, aucun sélecteur CSS fabriqué par
       concaténation (un nom de squad peut contenir ' " < > et cassait
       l'ancienne implémentation, SPEC §6.6) ;
     - le glisser-déposer a un équivalent clavier COMPLET : le bouton
       « Déplacer… » de chaque carte ouvre une modale qui fait exactement
       la même chose, y compris d'un pôle à l'autre ;
     - les réorganisations sont locales (mémoire + localStorage) et
       annulables par un bouton de réinitialisation confirmé ;
     - les trois états — chargement, erreur, vide — passent par avecEtat().

   Le lien entre un élément du DOM et l'objet du modèle qu'il représente
   passe TOUJOURS par un WeakMap, jamais par un sélecteur reconstruit.
   ========================================================================= */

import {
  el, svg, monter, vider, deleguer, debounce, annoncer, toast,
  ouvrirModale, etatUrl, stockage, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';

/* -------------------------------------------------------------------------
   0. Constantes
   ------------------------------------------------------------------------- */

/** Clé de la réorganisation locale. */
const CLE_ETAT = 'organigramme:etat';

/** Clé du niveau de zoom. */
const CLE_ZOOM = 'organigramme:zoom';

/** Version du format enregistré. Un incrément invalide les sauvegardes
    d'un format antérieur au lieu de les appliquer de travers. */
const VERSION_ETAT = 3;

const ZOOM_MIN = 80;
const ZOOM_MAX = 160;
const ZOOM_PAS = 10;
const ZOOM_DEFAUT = 100;

/** Anti-rebond de la recherche filtrante, en millisecondes. */
const DELAI_FILTRE = 120;

/** Code du niveau service : « tous pôles confondus ». */
const SERVICE = 'ETII';

/** Longueur maximale d'un nom de squad saisi. */
const NOM_MAX = 60;

/**
 * Contrat d'URL : les quatre valeurs admises, et le lien de navigation
 * qui porte `aria-current="page"` pour chacune. Le niveau service renvoie
 * au tableau de bord, un pôle à son propre espace.
 */
const PAGE_DE_POLE = {
  ETII: 'index.html',
  ETIIA: 'etiia.html',
  ETIIE: 'etiie.html',
  ETIII: 'etiii.html'
};

/**
 * Libellés de la structure de service (accord d'équipe, SPEC §1bis).
 * Les métaphores sont fixes : elles décrivent le rôle d'un pôle, pas une
 * donnée qui pourrait changer d'une livraison à l'autre.
 */
const DESCRIPTION_POLE = {
  ETII: {
    libelle: 'Tout le service',
    sousTitre: 'ETII — les trois pôles réunis'
  },
  ETIIA: {
    libelle: 'ETIIA',
    sousTitre: 'Squelette & ADN — logique et règles d’architecture'
  },
  ETIIE: {
    libelle: 'ETIIE',
    sousTitre: 'Système nerveux — schémas électriques, communication'
  },
  ETIII: {
    libelle: 'ETIII',
    sousTitre: 'Structure & harnais — intégration physique, routage'
  }
};

/** Ordre d'affichage des puces du sélecteur. */
const CODES_ADMIS = ['ETII', 'ETIIA', 'ETIIE', 'ETIII'];

/* -------------------------------------------------------------------------
   1. État du module
   ------------------------------------------------------------------------- */

/** Données brutes telles que chargées, conservées pour la réinitialisation. */
let donneesSource = null;

/** Modèle de travail, seul objet modifié par les déplacements. */
let modele = null;

/** Pôle affiché. Toujours l'une des quatre valeurs admises. */
let poleActif = SERVICE;

/** Éléments statiques de la page. */
const refs = {
  racine: null,
  conteneur: null,
  selecteur: null,
  puces: null,
  contexte: null,
  recherche: null,
  effacer: null,
  resume: null,
  zoom: null,
  zoomMoins: null,
  zoomPlus: null,
  zoomValeur: null,
  reinitialiser: null
};

/** Puces du sélecteur de pôle, par code. */
const vueParCode = new Map();

/* Ponts DOM -> modèle. Un WeakMap ne retient pas les nœuds détruits à
   chaque rendu, et surtout il évite d'avoir à reconstruire un sélecteur
   à partir d'un identifiant ou d'un nom. */
const personneParElement = new WeakMap();
const squadParElement = new WeakMap();
const poleParElement = new WeakMap();

/** Cartes rendues, par personne : sert au filtre et au retour de focus. */
let vueParPersonne = new Map();

/** Personne en cours de glissement, ou null. */
let personneGlissee = null;

/** Zone de dépôt actuellement survolée pendant un glissement. */
let depotSurvole = null;

/** Compteur d'identifiants uniques (squads, champs de modale). */
let compteur = 0;

/* -------------------------------------------------------------------------
   2. Utilitaires
   ------------------------------------------------------------------------- */

/**
 * Identifiant unique et stable pour un préfixe donné.
 * @param {string} prefixe
 * @returns {string}
 */
function idUnique(prefixe) {
  compteur += 1;
  return prefixe + '-' + compteur;
}

/**
 * Chaîne propre, jamais `undefined` ni `null` dans le DOM.
 * @param {*} valeur
 * @returns {string}
 */
function texte(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return String(valeur);
}

/**
 * Accord en nombre : « 1 personne », « 20 personnes ».
 * @param {number} n
 * @param {string} singulier
 * @param {string} pluriel
 * @returns {string}
 */
function accorder(n, singulier, pluriel) {
  return n + ' ' + (n > 1 ? pluriel : singulier);
}

/** Diacritiques, pour la normalisation de la recherche. */
const MARQUES = new RegExp('[\\u0300-\\u036f]', 'g');

/**
 * Minuscules sans accents : « Intégration » et « integration » se
 * rencontrent. La ponctuation devient de l'espace.
 * @param {*} valeur
 * @returns {string}
 */
function normaliser(valeur) {
  return texte(valeur)
    .normalize('NFD')
    .replace(MARQUES, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

/**
 * Ramène n'importe quelle valeur de hash à un code de pôle admis.
 * Toute valeur inconnue retombe sur « ETII », sans erreur (contrat d'URL).
 * @param {*} valeur
 * @returns {string}
 */
function normaliserPole(valeur) {
  /* Une clé répétée dans le hash est lue comme un tableau : on retient la
     dernière occurrence, comme le ferait un formulaire. */
  const brut = Array.isArray(valeur) ? valeur[valeur.length - 1] : valeur;
  const code = texte(brut).trim().toUpperCase();
  return CODES_ADMIS.indexOf(code) !== -1 ? code : SERVICE;
}

/**
 * Nom d'une squad, entre guillemets français, pour les phrases d'annonce.
 * Le résultat n'est JAMAIS interprété : il finit en textContent.
 * @param {object} squad
 * @returns {string}
 */
function cite(squad) {
  return '« ' + texte(squad && squad.nom) + ' »';
}

/** Donne le focus à un élément, sans jamais lever d'exception. */
function focaliser(element) {
  if (!element || typeof element.focus !== 'function') return false;
  try { element.focus(); return true; } catch (_e) { return false; }
}

/* -------------------------------------------------------------------------
   3. Modèle
   Construit une fois à partir du JSON, puis modifié en place par les
   déplacements. Les identifiants de squad sont GÉNÉRÉS ici : ils ne
   viennent jamais d'une donnée, donc aucun nom saisi ne peut se retrouver
   dans un attribut servant de clé.
   ------------------------------------------------------------------------- */

/**
 * Vérifie la forme du JSON et bâtit le modèle de travail.
 * Lève une Error au message français si la forme est invalide : avecEtat()
 * bascule alors proprement en état d'erreur.
 *
 * @param {object} donnees
 * @returns {object}
 */
function construireModele(donnees) {
  verifierForme(donnees, {
    service: 'chaine?',
    direction: 'objet?',
    poles: {
      type: 'tableau',
      elements: { pole: 'chaine', squads: 'tableau' }
    }
  }, 'organigramme.json');

  const etat = {
    service: texte(donnees.service) || SERVICE,
    direction: donnees.direction ? personneDe(donnees.direction, 'direction') : null,
    poles: [],
    parCode: new Map(),
    squadParId: new Map(),
    personneParId: new Map()
  };

  for (const brutPole of donnees.poles) {
    const code = texte(brutPole.pole).trim().toUpperCase();
    const description = DESCRIPTION_POLE[code] || null;

    const pole = {
      code: code,
      libelle: description ? description.libelle : code,
      sousTitre: description ? description.sousTitre : '',
      responsable: brutPole.responsable
        ? personneDe(brutPole.responsable, 'responsable')
        : null,
      squads: []
    };

    for (const brutSquad of brutPole.squads) {
      if (!brutSquad || typeof brutSquad !== 'object') continue;
      const squad = creerSquad(etat, pole, texte(brutSquad.nom));
      const membres = Array.isArray(brutSquad.membres) ? brutSquad.membres : [];
      for (const brutMembre of membres) {
        if (!brutMembre || typeof brutMembre !== 'object') continue;
        const personne = personneDe(brutMembre, 'membre');
        personne.squad = squad;
        squad.membres.push(personne);
        etat.personneParId.set(personne.id, personne);
      }
      ordonner(squad);
    }

    etat.poles.push(pole);
    etat.parCode.set(pole.code, pole);
  }

  return etat;
}

/**
 * Normalise une personne. Le rôle par défaut dépend de sa place dans la
 * hiérarchie : la donnée le précise, mais ne peut pas le contredire.
 * @param {object} brut
 * @param {string} roleParDefaut
 * @returns {object}
 */
function personneDe(brut, roleParDefaut) {
  const role = texte(brut.role).trim().toLowerCase();
  return {
    id: texte(brut.id),
    nom: texte(brut.nom),
    poste: texte(brut.poste),
    perimetre: texte(brut.perimetre),
    role: role || roleParDefaut,
    squad: null
  };
}

/**
 * Crée une squad et l'enregistre. L'identifiant est généré, jamais dérivé
 * du nom : c'est ce qui rend les apostrophes et les chevrons inoffensifs.
 * @param {object} etat
 * @param {object} pole
 * @param {string} nom
 * @returns {object}
 */
function creerSquad(etat, pole, nom) {
  const squad = {
    id: idUnique('squad'),
    nom: nom || 'Squad sans nom',
    pole: pole,
    membres: []
  };
  pole.squads.push(squad);
  etat.squadParId.set(squad.id, squad);
  return squad;
}

/** Le leader d'une squad, ou null. */
function leaderDe(squad) {
  return squad.membres.find((m) => m.role === 'leader') || null;
}

/** Les membres non leaders d'une squad. */
function membresDe(squad) {
  return squad.membres.filter((m) => m.role !== 'leader');
}

/** Replace le leader en tête de liste : l'ordre du DOM suit la hiérarchie. */
function ordonner(squad) {
  squad.membres.sort((a, b) => {
    const ra = a.role === 'leader' ? 0 : 1;
    const rb = b.role === 'leader' ? 0 : 1;
    return ra - rb;
  });
}

/** Effectif d'un pôle : son responsable et tous les membres de ses squads. */
function effectifPole(pole) {
  let total = pole.responsable ? 1 : 0;
  for (const squad of pole.squads) total += squad.membres.length;
  return total;
}

/** Effectif du service entier, direction comprise. */
function effectifService(etat) {
  let total = etat.direction ? 1 : 0;
  for (const pole of etat.poles) total += effectifPole(pole);
  return total;
}

/** Effectif affiché pour un code du sélecteur. */
function effectifDe(code) {
  if (!modele) return 0;
  if (code === SERVICE) return effectifService(modele);
  const pole = modele.parCode.get(code);
  return pole ? effectifPole(pole) : 0;
}

/** Les pôles visibles dans la vue courante. */
function polesVisibles() {
  if (!modele) return [];
  if (poleActif === SERVICE) return modele.poles;
  const pole = modele.parCode.get(poleActif);
  return pole ? [pole] : [];
}

/* -------------------------------------------------------------------------
   4. Persistance locale
   Le stockage est facultatif : sans lui, la page fonctionne, elle perd
   seulement sa mémoire d'une visite à l'autre.
   ------------------------------------------------------------------------- */

/**
 * Photographie de la répartition courante. Les identifiants de squad,
 * générés à chaque chargement, n'y figurent pas : c'est l'ORDRE des
 * squads dans chaque pôle qui les identifie.
 * @returns {object}
 */
function serialiser() {
  return {
    v: VERSION_ETAT,
    poles: modele.poles.map((pole) => ({
      pole: pole.code,
      squads: pole.squads.map((squad) => ({
        nom: squad.nom,
        membres: squad.membres.map((m) => ({ id: m.id, role: m.role }))
      }))
    }))
  };
}

/** Enregistre la répartition courante, en silence si le stockage est fermé. */
function enregistrer() {
  stockage.ecrire(CLE_ETAT, serialiser());
}

/**
 * Réapplique une sauvegarde au modèle.
 *
 * Tout ou rien : si le moindre écart existe entre les personnes
 * enregistrées et celles du fichier de données (ajout, retrait,
 * renommage d'identifiant), la sauvegarde est refusée en bloc. Appliquer
 * une réorganisation à moitié serait pire que de ne pas l'appliquer.
 *
 * @param {object} sauvegarde
 * @returns {boolean} vrai si la sauvegarde a été appliquée
 */
function appliquerSauvegarde(sauvegarde) {
  if (!sauvegarde || typeof sauvegarde !== 'object') return false;
  if (sauvegarde.v !== VERSION_ETAT) return false;
  if (!Array.isArray(sauvegarde.poles)) return false;

  /* 1. Les pôles enregistrés doivent être exactement ceux du fichier. */
  if (sauvegarde.poles.length !== modele.poles.length) return false;
  const parCodeSauvegarde = new Map();
  for (const entree of sauvegarde.poles) {
    if (!entree || typeof entree !== 'object') return false;
    const code = texte(entree.pole).trim().toUpperCase();
    if (!modele.parCode.has(code)) return false;
    if (parCodeSauvegarde.has(code)) return false;
    if (!Array.isArray(entree.squads) || entree.squads.length === 0) return false;
    parCodeSauvegarde.set(code, entree);
  }

  /* 2. Les personnes enregistrées doivent être exactement les personnes
        déplaçables du fichier, chacune une seule fois. */
  const attendues = new Set(modele.personneParId.keys());
  const vues = new Set();
  for (const entree of parCodeSauvegarde.values()) {
    for (const squad of entree.squads) {
      if (!squad || typeof squad !== 'object') return false;
      if (!Array.isArray(squad.membres)) return false;
      for (const membre of squad.membres) {
        if (!membre || typeof membre !== 'object') return false;
        const id = texte(membre.id);
        if (!attendues.has(id) || vues.has(id)) return false;
        vues.add(id);
      }
    }
  }
  if (vues.size !== attendues.size) return false;

  /* 3. Rien ne cloche : on rebâtit les squads de chaque pôle. */
  modele.squadParId.clear();
  for (const pole of modele.poles) {
    const entree = parCodeSauvegarde.get(pole.code);
    pole.squads = [];

    for (const brutSquad of entree.squads) {
      const squad = creerSquad(modele, pole, texte(brutSquad.nom));
      for (const brutMembre of brutSquad.membres) {
        const personne = modele.personneParId.get(texte(brutMembre.id));
        personne.role = brutMembre.role === 'leader' ? 'leader' : 'membre';
        personne.squad = squad;
        squad.membres.push(personne);
      }
      /* Une squad ne peut pas avoir deux leaders : le premier gagne. */
      let leaderVu = false;
      for (const membre of squad.membres) {
        if (membre.role !== 'leader') continue;
        if (leaderVu) membre.role = 'membre';
        leaderVu = true;
      }
      ordonner(squad);
    }
  }

  return true;
}

/* -------------------------------------------------------------------------
   5. Avatars générés localement (SPEC §4.4)
   ------------------------------------------------------------------------- */

/**
 * Teinte HSL dérivée de l'identifiant, entre 0 et 359.
 *
 * Hachage FNV-1a 32 bits : deux identifiants voisins (« p01 » et « p02 »)
 * donnent des teintes éloignées, là où une somme naïve les rendrait
 * indiscernables. Entièrement déterministe : la même personne a toujours
 * la même couleur, d'une visite à l'autre et d'un poste à l'autre.
 *
 * @param {string} id
 * @returns {number}
 */
function teinteDe(id) {
  const chaine = texte(id);
  let hachage = 2166136261;
  for (let i = 0; i < chaine.length; i += 1) {
    hachage ^= chaine.charCodeAt(i);
    hachage = Math.imul(hachage, 16777619);
  }
  return (hachage >>> 0) % 360;
}

/**
 * Initiales de l'avatar : première lettre, puis le numéro s'il y en a un
 * (« Personne 03 » -> « P03 »). Trois caractères au maximum.
 * @param {object} personne
 * @returns {string}
 */
function initialesDe(personne) {
  const mots = texte(personne.nom || personne.id).split(/\s+/).filter(Boolean);
  if (mots.length === 0) return '?';

  const premier = mots[0].charAt(0).toUpperCase();
  const dernier = mots[mots.length - 1];

  if (mots.length > 1 && /^\d+$/.test(dernier)) return (premier + dernier).slice(0, 3);
  if (mots.length > 1) return premier + dernier.charAt(0).toUpperCase();
  return mots[0].slice(0, 2).toUpperCase();
}

/**
 * Avatar SVG inline : un disque teinté et des initiales.
 *
 * Aucun appel réseau, aucun service tiers, aucune image. Le module ne
 * transmet qu'un NOMBRE (--avatar-teinte) ; la formule de couleur vit
 * dans le <style> de la page, avec une saturation et une clarté fixes qui
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
   6. Sélecteur de pôle
   Quatre puces de facette, avec l'effectif de chacune. Elles sont
   construites une fois puis mises à jour : reconstruire la liste à chaque
   clic ferait perdre le focus de la puce que l'on vient d'activer.
   ------------------------------------------------------------------------- */

/**
 * Construit les puces du sélecteur. Rejoué à chaque chargement réussi —
 * y compris après un « Réessayer » — pour qu'elles décrivent toujours les
 * données réellement affichées.
 */
function construireSelecteur() {
  if (!refs.puces) return;

  vueParCode.clear();
  const elements = [];

  for (const code of CODES_ADMIS) {
    /* Un code absent du fichier de données n'a pas de puce : proposer un
       filtre qui n'affiche rien serait un piège. */
    if (code !== SERVICE && !modele.parCode.has(code)) continue;

    const description = DESCRIPTION_POLE[code];
    const compteurNoeud = el('span', { class: 'facette__compteur' }, '0');

    const bouton = el('button', {
      type: 'button',
      class: 'facette',
      ariaPressed: 'false',
      dataset: { pole: code },
      onClick: () => choisirPole(code, true)
    },
    el('span', { class: 'facette__marque', ariaHidden: 'true' }, '✓'),
    /* Pastille de couleur du pôle. Elle ne porte jamais l'information à
       elle seule : le code du pôle est écrit juste après. */
    code === SERVICE ? null : el('span', { class: 'org-puce', ariaHidden: 'true' }),
    el('span', null, description.libelle),
    compteurNoeud,
    el('span', { class: 'visuellement-cache' }, ' personnes'));

    vueParCode.set(code, { bouton: bouton, compteur: compteurNoeud });
    elements.push(el('li', { dataset: { pole: code } }, bouton));
  }

  monter(refs.puces, elements);
  if (refs.selecteur) refs.selecteur.hidden = elements.length === 0;
}

/** Met à jour effectifs et état pressé des puces, plus la ligne de situation. */
function majSelecteur() {
  for (const [code, vue] of vueParCode) {
    const total = effectifDe(code);
    vue.compteur.textContent = String(total);
    vue.bouton.setAttribute('aria-pressed', code === poleActif ? 'true' : 'false');
  }
  majContexte();
}

/** Phrase de situation sous les puces : périmètre, effectif, profondeur. */
function majContexte() {
  if (!refs.contexte || !modele) return;

  if (poleActif === SERVICE) {
    refs.contexte.textContent = 'Périmètre affiché : tout le service '
      + modele.service + ' — ' + accorder(effectifService(modele), 'personne', 'personnes')
      + ' réparties entre ' + accorder(modele.poles.length, 'pôle', 'pôles') + '.';
    return;
  }

  const pole = modele.parCode.get(poleActif);
  if (!pole) {
    refs.contexte.textContent = '';
    return;
  }

  refs.contexte.textContent = 'Périmètre affiché : ' + modele.service + ' › '
    + pole.code + ' — ' + accorder(effectifPole(pole), 'personne', 'personnes')
    + ', ' + accorder(pole.squads.length, 'squad', 'squads') + '.';
}

/**
 * Change de pôle : hash, navigation principale, puces et contenu.
 * Aucun rechargement.
 *
 * @param {string} code
 * @param {boolean} annonce vrai pour l'annoncer aux lecteurs d'écran
 */
function choisirPole(code, annonce) {
  const suivant = normaliserPole(code);
  const changement = suivant !== poleActif;
  poleActif = suivant;

  /* Contrat d'URL : le pôle actif est toujours écrit, même « ETII », pour
     qu'un lien copié dise explicitement ce qu'il montre. */
  etatUrl.ecrire({ pole: poleActif });

  /* Sur une page transverse, l'entrée courante de la navigation est celle
     du pôle affiché — le tableau de bord au niveau service. */
  initNav(PAGE_DE_POLE[poleActif]);

  if (!modele) return;

  majSelecteur();
  rendre();
  appliquerFiltre(false);

  if (annonce && changement) {
    annoncer('Périmètre ' + DESCRIPTION_POLE[poleActif].libelle + ' affiché : '
      + accorder(effectifDe(poleActif), 'personne', 'personnes') + '.');
  }
}

/* -------------------------------------------------------------------------
   7. Rendu
   ------------------------------------------------------------------------- */

/** Reconstruit entièrement le contenu de la zone d'organigramme. */
function rendre() {
  if (!refs.conteneur || !modele) return;

  vueParPersonne = new Map();
  vider(refs.conteneur);

  const pile = el('div', { class: 'pile pile--section' });
  const poles = polesVisibles();

  if (poleActif === SERVICE) {
    pile.append(vueService(poles));
  } else if (poles.length === 0) {
    pile.append(blocVide(
      'Pôle introuvable',
      'Le pôle demandé n’existe pas dans les données. Choisissez un autre '
      + 'périmètre ci-dessus.'));
  } else {
    for (const pole of poles) pile.append(vuePole(pole));
  }

  monter(refs.conteneur, pile);
}

/**
 * Niveau service : la direction, puis les trois pôles sur un rail commun.
 * @param {Array} poles
 * @returns {Element}
 */
function vueService(poles) {
  /* Le contenu est assemblé AVANT la création de la section : `monter()`
     remplace le contenu d'un parent, il ne l'y ajoute pas. */
  const contenu = [];

  if (modele.direction) {
    contenu.push(
      el('p', { class: 'org-etiquette' }, 'Direction de service'),
      el('ul', { class: 'org-grille' }, vuePersonne(modele.direction, false)));
  }

  if (poles.length === 0) {
    contenu.push(blocVide(
      'Aucun pôle à afficher',
      'Le fichier de données ne décrit aucun pôle : il n’y a pas de '
      + 'hiérarchie à représenter pour le moment.'));
  } else {
    /* Niveau 1 : les pôles pendent du rail du service. */
    contenu.push(el('div', { class: 'org-branche', dataset: { pole: SERVICE } },
      poles.map((pole) => vuePole(pole, true))));
  }

  return el('section', {
    class: 'pile org-service',
    dataset: { pole: SERVICE },
    ariaLabel: 'Service ' + modele.service
  }, contenu);
}

/**
 * Bloc d'un pôle : en-tête, responsable, puis ses squads un cran plus bas.
 * @param {object} pole
 * @param {boolean} [estNoeud] vrai si le bloc pend d'un rail parent
 * @returns {Element}
 */
function vuePole(pole, estNoeud) {
  const effectif = effectifPole(pole);

  const boutonAjout = el('button', {
    type: 'button',
    class: 'bouton bouton--secondaire bouton--compact sans-impression',
    ariaLabel: 'Ajouter une squad au pôle ' + pole.code,
    dataset: { action: 'ajouter-squad' }
  }, 'Ajouter une squad');
  poleParElement.set(boutonAjout, pole);

  const entete = el('header', { class: 'org-pole__entete' },
    el('div', { class: 'org-pole__identite' },
      el('h2', { class: 'org-pole__titre' },
        el('span', { class: 'org-puce', ariaHidden: 'true' }),
        pole.code),
      pole.sousTitre ? el('p', { class: 'org-pole__sous-titre' }, pole.sousTitre) : null),
    el('span', { class: 'badge badge--neutre' },
      accorder(effectif, 'personne', 'personnes')),
    boutonAjout);

  /* Niveau 2 du pôle : le responsable, puis ses squads un cran plus bas.
     Tout est assemblé avant création : `monter()` remplace un contenu, il
     ne l'ajoute pas. */
  const sousNiveau = pole.squads.length === 0
    ? [blocVide(
      'Aucune squad',
      'Ce pôle ne contient encore aucune squad. Le bouton « Ajouter une '
      + 'squad » en crée une.')]
    : [
      el('p', { class: 'org-etiquette' },
        accorder(pole.squads.length, 'squad rattachée', 'squads rattachées')),
      el('div', { class: 'org-branche' },
        pole.squads.map((squad) => vueSquad(squad)))
    ];

  const noeudResponsable = el('div', { class: 'org-noeud' },
    el('p', { class: 'org-etiquette' }, 'Responsable de pôle'),
    pole.responsable
      ? el('ul', { class: 'org-grille' }, vuePersonne(pole.responsable, false))
      : el('p', { class: 'org-depot__vide' },
        'Aucun responsable n’est désigné pour ce pôle.'),
    sousNiveau);

  return el('section', {
    class: ['org-pole', estNoeud ? 'org-noeud' : null],
    dataset: { pole: pole.code }
  }, entete, el('div', { class: 'org-branche' }, noeudResponsable));
}

/**
 * Bloc d'une squad : leader et membres, chacun dans sa zone de dépôt.
 * @param {object} squad
 * @returns {Element}
 */
function vueSquad(squad) {
  const leader = leaderDe(squad);
  const membres = membresDe(squad);

  const boutonRenommer = el('button', {
    type: 'button',
    class: 'bouton bouton--discret bouton--compact sans-impression',
    ariaLabel: 'Renommer la squad ' + squad.nom,
    dataset: { action: 'renommer-squad' }
  }, 'Renommer');
  squadParElement.set(boutonRenommer, squad);

  const entete = el('header', { class: 'org-squad__entete' },
    el('h3', { class: 'org-squad__titre' }, squad.nom),
    el('span', { class: 'badge badge--neutre' },
      accorder(squad.membres.length, 'personne', 'personnes')),
    boutonRenommer);

  const zoneLeader = zoneDepot(squad, 'leader',
    leader ? [vuePersonne(leader, true)] : [],
    'Aucun leader désigné pour cette squad.');
  zoneLeader.classList.add('org-depot--leader');

  const zoneMembres = zoneDepot(squad, 'membre',
    membres.map((membre) => vuePersonne(membre, true)),
    'Aucun membre dans cette squad.');

  const corps = el('div', { class: 'org-squad__corps' },
    el('div', { class: 'org-squad__section' },
      el('p', { class: 'org-etiquette' }, 'Leader'),
      zoneLeader,
      el('p', { class: 'org-indice' },
        'Déposez ici pour confier le rôle de leader.')),
    el('div', { class: 'org-squad__section' },
      el('p', { class: 'org-etiquette' }, 'Membres'),
      zoneMembres,
      el('p', { class: 'org-indice' },
        'Déposez ici pour rattacher à cette squad.')));

  return el('article', {
    class: 'org-squad carte org-noeud',
    dataset: { squad: squad.id }
  }, entete, corps);
}

/**
 * Zone de dépôt d'une squad. Le rôle visé est porté par un `data-`, jamais
 * lu depuis un nom : c'est le WeakMap qui relie l'élément à la squad.
 *
 * @param {object} squad
 * @param {string} role 'leader' | 'membre'
 * @param {Array} cartes
 * @param {string} texteVide
 * @returns {Element}
 */
function zoneDepot(squad, role, cartes, texteVide) {
  const zone = el('div', {
    class: 'org-depot',
    dataset: { depot: role }
  }, cartes.length
    ? el('ul', { class: 'org-grille' }, cartes)
    : el('p', { class: 'org-depot__vide' }, texteVide));

  squadParElement.set(zone, squad);
  return zone;
}

/**
 * Carte d'une personne.
 *
 * @param {object} personne
 * @param {boolean} deplacable  faux pour la direction et les responsables,
 *                              dont le rattachement est structurel
 * @returns {Element}
 */
function vuePersonne(personne, deplacable) {
  const estLeader = personne.role === 'leader';

  let boutonDeplacer = null;
  if (deplacable) {
    boutonDeplacer = el('button', {
      type: 'button',
      class: 'bouton bouton--discret bouton--compact personne__deplacer',
      ariaLabel: 'Déplacer ' + personne.nom + ' vers une autre squad',
      dataset: { action: 'deplacer' }
    }, 'Déplacer…');
    personneParElement.set(boutonDeplacer, personne);
  }

  const carte = el('li', {
    class: 'personne carte',
    draggable: deplacable ? 'true' : null,
    dataset: { personne: personne.id }
  },
  el('div', { class: 'personne__tete' },
    avatarDe(personne),
    el('div', { class: 'personne__identite' },
      el('p', { class: 'personne__nom' }, personne.nom),
      el('p', { class: 'personne__poste' }, personne.poste))),
  el('div', { class: 'personne__pied' },
    personne.perimetre
      ? el('span', { class: 'badge badge--neutre' }, personne.perimetre)
      : null,
    estLeader ? el('span', { class: 'badge badge--accent' }, 'Leader') : null,
    deplacable
      ? null
      : el('span', { class: 'badge badge--contour' }, 'Rattachement fixe'),
    boutonDeplacer));

  personneParElement.set(carte, personne);
  vueParPersonne.set(personne, { carte: carte, bouton: boutonDeplacer });
  return carte;
}

/**
 * Bloc d'information réutilisant l'état vide du design system.
 * @param {string} titre
 * @param {string} explication
 * @returns {Element}
 */
function blocVide(titre, explication) {
  return el('div', { class: 'etat-vide etat-vide--encadre etat-vide--compact' },
    el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '∅'),
    el('p', { class: 'etat-vide__titre' }, titre),
    el('p', { class: 'etat-vide__texte' }, explication));
}

/**
 * Squelette d'attente, purement décoratif : avecEtat() ajoute lui-même
 * `aria-busy` et le texte de statut lisible par un lecteur d'écran.
 * @param {Element} cible
 */
function squelette(cible) {
  const carte = () => el('li', { class: 'personne carte' },
    el('div', { class: 'personne__tete' },
      el('span', { class: 'squelette squelette--avatar' }),
      el('div', { class: 'personne__identite' },
        el('span', { class: 'squelette squelette--ligne squelette--moyen' }),
        el('span', { class: 'squelette squelette--ligne squelette--court' }))));

  const squad = () => el('article', { class: 'org-squad carte' },
    el('div', { class: 'org-squad__entete' },
      el('span', { class: 'squelette squelette--ligne squelette--titre' })),
    el('div', { class: 'org-squad__corps' },
      el('ul', { class: 'org-grille' }, [carte(), carte(), carte(), carte()])));

  monter(cible, el('div', {
    class: 'pile pile--section',
    ariaHidden: 'true'
  }, squad(), squad()));
}

/* -------------------------------------------------------------------------
   8. Déplacement — le cœur, partagé par la souris et le clavier
   ------------------------------------------------------------------------- */

/**
 * Déplace une personne vers une squad, dans le rôle demandé.
 *
 * C'est l'UNIQUE fonction qui modifie la répartition : le glisser-déposer
 * et la modale clavier passent tous deux par ici, donc les deux chemins ne
 * peuvent pas diverger.
 *
 * @param {object} personne
 * @param {object} cible squad de destination
 * @param {string} role  'leader' | 'membre'
 * @returns {boolean} vrai si quelque chose a réellement changé
 */
function deplacer(personne, cible, role) {
  if (!personne || !cible) return false;

  const source = personne.squad;
  const roleVise = role === 'leader' ? 'leader' : 'membre';

  if (source === cible && personne.role === roleVise) {
    toast(personne.nom + ' est déjà ' + (roleVise === 'leader' ? 'leader' : 'membre')
      + ' de ' + cite(cible) + '.', 'info');
    return false;
  }

  const poleSource = source ? source.pole : null;
  const changePole = poleSource !== cible.pole;

  /* Retrait de la squad d'origine. */
  if (source) {
    const position = source.membres.indexOf(personne);
    if (position !== -1) source.membres.splice(position, 1);
  }

  /* Le rôle de leader est unique : l'ancien titulaire redevient membre. */
  let retrograde = null;
  if (roleVise === 'leader') {
    const ancien = leaderDe(cible);
    if (ancien && ancien !== personne) {
      ancien.role = 'membre';
      retrograde = ancien;
    }
  }

  personne.role = roleVise;
  personne.squad = cible;
  cible.membres.push(personne);
  ordonner(cible);

  enregistrer();
  majSelecteur();
  rendre();
  appliquerFiltre(false);

  /* Message : il doit dire ce qui a changé, y compris l'effet de bord sur
     l'ancien leader et le passage d'un pôle à l'autre. */
  let message = personne.nom + ' rejoint ' + cite(cible)
    + ' comme ' + (roleVise === 'leader' ? 'leader' : 'membre')
    + ' (' + cible.pole.code + ').';
  if (retrograde) message += ' ' + retrograde.nom + ' redevient membre.';
  if (changePole && poleSource) {
    message += ' Effectif de ' + poleSource.code + ' : '
      + effectifPole(poleSource) + ', de ' + cible.pole.code + ' : '
      + effectifPole(cible.pole) + '.';
  }

  /* Retour de focus. Si la personne n'est plus visible — déplacée vers un
     pôle que la vue courante ne montre pas — on renvoie vers la puce de ce
     pôle plutôt que de laisser le focus retomber sur le document. */
  const vue = vueParPersonne.get(personne);
  if (vue && vue.bouton && focaliser(vue.bouton)) {
    toast(message, 'succes');
  } else {
    const puce = vueParCode.get(cible.pole.code);
    if (puce) focaliser(puce.bouton);
    message += ' Le périmètre affiché (' + DESCRIPTION_POLE[poleActif].libelle
      + ') ne la montre plus.';
    toast(message, 'info');
  }

  annoncer(message);
  return true;
}

/* -------------------------------------------------------------------------
   9. Glisser-déposer
   Le dépôt ne lit jamais de sélecteur : l'élément survolé est traduit en
   squad par le WeakMap, et le rôle visé est porté par `data-depot`.
   ------------------------------------------------------------------------- */

/** Câble le glisser-déposer, une seule fois, par délégation. */
function cablerGlisserDeposer() {
  const conteneur = refs.conteneur;
  if (!conteneur) return;

  deleguer(conteneur, '.personne[draggable="true"]', 'dragstart', (evt, carte) => {
    const personne = personneParElement.get(carte);
    if (!personne) return;

    personneGlissee = personne;
    carte.dataset.glisse = '';
    try { document.documentElement.dataset.orgGlisse = ''; } catch (_e) { /* ignoré */ }

    try {
      evt.dataTransfer.effectAllowed = 'move';
      /* Un identifiant, pas un nom : rien de ce qui transite ici ne sert
         jamais à fabriquer un sélecteur. */
      evt.dataTransfer.setData('text/plain', personne.id);
    } catch (_e) { /* certains navigateurs refusent setData hors dragstart */ }
  });

  deleguer(conteneur, '.personne[draggable="true"]', 'dragend', (evt, carte) => {
    delete carte.dataset.glisse;
    terminerGlissement();
  });

  deleguer(conteneur, '.org-depot', 'dragover', (evt, zone) => {
    if (!personneGlissee) return;
    /* Sans preventDefault, le navigateur refuse le dépôt. */
    evt.preventDefault();
    try { evt.dataTransfer.dropEffect = 'move'; } catch (_e) { /* ignoré */ }
    survoler(zone);
  });

  deleguer(conteneur, '.org-depot', 'drop', (evt, zone) => {
    evt.preventDefault();

    const squad = squadParElement.get(zone);
    const role = zone.dataset.depot === 'leader' ? 'leader' : 'membre';

    let personne = personneGlissee;
    if (!personne) {
      let id = '';
      try { id = texte(evt.dataTransfer.getData('text/plain')); } catch (_e) { id = ''; }
      personne = modele ? modele.personneParId.get(id) : null;
    }

    terminerGlissement();
    if (personne && squad) deplacer(personne, squad, role);
  });

  /* Un glissement abandonné hors de toute zone doit nettoyer le décor. */
  document.addEventListener('dragend', terminerGlissement);
  document.addEventListener('drop', terminerGlissement);
}

/** Marque une seule zone comme survolée. */
function survoler(zone) {
  if (depotSurvole === zone) return;
  if (depotSurvole) delete depotSurvole.dataset.survol;
  depotSurvole = zone;
  if (zone) zone.dataset.survol = '';
}

/** Retire tout le décor de glissement. */
function terminerGlissement() {
  personneGlissee = null;
  survoler(null);
  try { delete document.documentElement.dataset.orgGlisse; } catch (_e) { /* ignoré */ }
}

/* -------------------------------------------------------------------------
   10. Équivalent clavier : la modale « Déplacer… » (SPEC §4.4)
   Elle fait EXACTEMENT ce que fait le glisser-déposer : choisir une squad
   de destination — dans n'importe quel pôle — et un rôle.
   ------------------------------------------------------------------------- */

/**
 * Ouvre la modale de déplacement d'une personne.
 * @param {object} personne
 * @param {Element} declencheur bouton à refocaliser à la fermeture
 */
function ouvrirModaleDeplacement(personne, declencheur) {
  if (!modele) return;

  const squadActuelle = personne.squad;
  const idSelect = idUnique('org-destination');
  const nomGroupe = idUnique('org-role');

  /* Les options portent l'identifiant GÉNÉRÉ de la squad : le nom, lui,
     n'est que du texte affiché. Une squad nommée « L'équipe <A> » ne
     casse donc rien. */
  const select = el('select', {
    class: 'champ__controle',
    id: idSelect
  }, modele.poles.map((pole) => el('optgroup', {
    label: pole.code + (pole.sousTitre ? ' — ' + pole.sousTitre : '')
  }, pole.squads.map((squad) => el('option', {
    value: squad.id
  }, squad.nom + (squad === squadActuelle ? ' (squad actuelle)' : ''))))));

  /* La valeur est posée après construction : c'est le seul moyen fiable
     de présélectionner une option dans un <select> déjà rempli. */
  if (squadActuelle) select.value = squadActuelle.id;

  const radioMembre = el('input', {
    class: 'case__controle',
    type: 'radio',
    name: nomGroupe,
    value: 'membre',
    checked: personne.role !== 'leader'
  });

  const radioLeader = el('input', {
    class: 'case__controle',
    type: 'radio',
    name: nomGroupe,
    value: 'leader',
    checked: personne.role === 'leader'
  });

  const contenu = el('div', { class: 'org-destination' },
    el('p', { class: 'org-destination__actuelle' },
      squadActuelle
        ? personne.nom + ' est aujourd’hui '
          + (personne.role === 'leader' ? 'leader' : 'membre') + ' de '
          + cite(squadActuelle) + ', dans le pôle ' + squadActuelle.pole.code + '.'
        : personne.nom + ' n’est rattachée à aucune squad.'),

    el('div', { class: 'champ' },
      el('label', { class: 'champ__etiquette', for: idSelect },
        'Squad de destination'),
      el('span', { class: 'champ__select' }, select),
      el('span', { class: 'champ__aide' },
        'Les squads sont regroupées par pôle : un déplacement d’un pôle à '
        + 'un autre est autorisé et met à jour les effectifs.')),

    el('fieldset', { class: 'groupe-champs' },
      el('legend', { class: 'groupe-champs__legende' }, 'Rôle dans la squad'),
      el('label', { class: 'case' }, radioMembre,
        el('span', { class: 'case__texte' }, 'Membre')),
      el('label', { class: 'case' }, radioLeader,
        el('span', { class: 'case__texte' }, 'Leader',
          el('span', { class: 'case__texte-aide' },
            'Le leader actuel de la squad choisie redeviendra membre.')))));

  ouvrirModale({
    titre: 'Déplacer ' + personne.nom,
    contenu: contenu,
    declencheur: declencheur,
    actions: [
      { libelle: 'Annuler', variante: 'discret' },
      {
        libelle: 'Déplacer',
        variante: 'principal',
        onClick: () => {
          const cible = modele.squadParId.get(select.value);
          if (!cible) {
            toast('Cette squad n’existe plus : choisissez une autre '
              + 'destination.', 'alerte');
            return false;   // la modale reste ouverte
          }
          const role = radioLeader.checked ? 'leader' : 'membre';
          /* Le déplacement se fait après la fermeture : il reconstruit le
             DOM, donc le retour de focus doit viser la nouvelle carte. */
          setTimeout(() => deplacer(personne, cible, role), 0);
          return true;
        }
      }
    ]
  });
}

/* -------------------------------------------------------------------------
   11. Nommer une squad : création et renommage
   ------------------------------------------------------------------------- */

/**
 * Modale d'un champ de texte unique, avec validation.
 * @param {object} options { titre, etiquette, valeur, libelleValider, aide,
 *                           declencheur, onValider(nom) }
 */
function ouvrirModaleNom(options) {
  const idChamp = idUnique('org-nom');
  const idErreur = idUnique('org-nom-erreur');

  const champ = el('input', {
    class: 'champ__controle',
    id: idChamp,
    type: 'text',
    value: texte(options.valeur),
    maxlength: NOM_MAX,
    autocomplete: 'off',
    spellcheck: 'false',
    ariaDescribedby: idErreur,
    autofocus: true
  });

  const erreur = el('p', { class: 'champ__erreur', id: idErreur, role: 'alert' });

  const contenu = el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idChamp }, options.etiquette),
    champ,
    el('span', { class: 'champ__aide' }, options.aide || ''),
    erreur);

  /** Valide et applique. Renvoie false pour garder la modale ouverte. */
  const valider = () => {
    const valeur = texte(champ.value).trim();
    if (!valeur) {
      erreur.textContent = 'Un nom est nécessaire : le champ est vide.';
      focaliser(champ);
      return false;
    }
    if (valeur.length > NOM_MAX) {
      erreur.textContent = 'Le nom ne peut pas dépasser ' + NOM_MAX + ' caractères.';
      focaliser(champ);
      return false;
    }
    erreur.textContent = '';
    options.onValider(valeur);
    return true;
  };

  const api = ouvrirModale({
    titre: options.titre,
    contenu: contenu,
    declencheur: options.declencheur,
    actions: [
      { libelle: 'Annuler', variante: 'discret' },
      { libelle: options.libelleValider, variante: 'principal', onClick: valider }
    ]
  });

  /* Entrée valide, comme dans un vrai formulaire. */
  champ.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Enter') return;
    evt.preventDefault();
    if (valider()) api.fermer('action');
  });
}

/**
 * Crée une squad dans un pôle.
 * @param {object} pole
 * @param {Element} declencheur
 */
function ouvrirCreationSquad(pole, declencheur) {
  ouvrirModaleNom({
    titre: 'Nouvelle squad dans ' + pole.code,
    etiquette: 'Nom de la squad',
    valeur: '',
    aide: 'Apostrophes, guillemets et chevrons sont acceptés : le nom n’est '
      + 'que du texte, jamais du balisage.',
    libelleValider: 'Créer',
    declencheur: declencheur,
    onValider: (nom) => {
      const squad = creerSquad(modele, pole, nom);
      enregistrer();
      majSelecteur();
      rendre();
      appliquerFiltre(false);

      const message = 'Squad ' + cite(squad) + ' créée dans ' + pole.code
        + '. Elle est vide : déplacez-y des personnes.';
      toast(message, 'succes');
      annoncer(message);
    }
  });
}

/**
 * Renomme une squad.
 * @param {object} squad
 * @param {Element} declencheur
 */
function ouvrirRenommageSquad(squad, declencheur) {
  const ancien = squad.nom;
  ouvrirModaleNom({
    titre: 'Renommer une squad',
    etiquette: 'Nom de la squad',
    valeur: squad.nom,
    aide: 'Apostrophes, guillemets et chevrons sont acceptés : le nom n’est '
      + 'que du texte, jamais du balisage.',
    libelleValider: 'Renommer',
    declencheur: declencheur,
    onValider: (nom) => {
      squad.nom = nom;
      enregistrer();
      rendre();
      appliquerFiltre(false);

      const message = 'Squad ' + cite({ nom: ancien }) + ' renommée en '
        + cite(squad) + '.';
      toast(message, 'succes');
      annoncer(message);
    }
  });
}

/* -------------------------------------------------------------------------
   12. Réinitialisation
   Action destructrice : elle est TOUJOURS confirmée (SPEC §6.5).
   ------------------------------------------------------------------------- */

/**
 * Demande confirmation avant de tout remettre en place.
 * @param {Element} declencheur
 */
function confirmerReinitialisation(declencheur) {
  ouvrirModale({
    titre: 'Réinitialiser l’organigramme ?',
    declencheur: declencheur,
    contenu: el('p', { class: 'mesure sans-marge' },
      'Toutes les réorganisations faites sur ce poste seront perdues : '
      + 'déplacements, changements de leader, squads créées et renommées. '
      + 'L’organigramme d’origine sera rétabli. Cette action ne peut pas '
      + 'être annulée.'),
    actions: [
      { libelle: 'Annuler', variante: 'discret' },
      {
        libelle: 'Réinitialiser',
        variante: 'danger',
        onClick: () => { reinitialiser(); }
      }
    ]
  });
}

/** Rétablit l'organigramme d'origine. */
function reinitialiser() {
  stockage.supprimer(CLE_ETAT);
  modele = construireModele(donneesSource);

  majSelecteur();
  rendre();
  appliquerFiltre(false);

  const message = 'Organigramme réinitialisé : '
    + accorder(effectifService(modele), 'personne', 'personnes')
    + ' réparties comme dans les données d’origine.';
  toast(message, 'succes');
  annoncer(message);
  focaliser(refs.reinitialiser);
}

/* -------------------------------------------------------------------------
   13. Recherche filtrante
   Les cartes hors filtre sont mises en RETRAIT, jamais retirées du flux ni
   de l'ordre de tabulation (SPEC §4.4).
   ------------------------------------------------------------------------- */

/**
 * Applique la recherche courante aux cartes rendues.
 * @param {boolean} annonce vrai pour annoncer le résultat
 */
function appliquerFiltre(annonce) {
  if (!refs.recherche || !refs.resume) return;

  const brut = refs.recherche.value || '';
  const requete = normaliser(brut);
  const total = vueParPersonne.size;

  if (!requete) {
    for (const vue of vueParPersonne.values()) delete vue.carte.dataset.horsFiltre;
    refs.resume.textContent = '';
    refs.resume.hidden = true;
    if (annonce) {
      annoncer('Filtre effacé, '
        + accorder(total, 'personne affichée', 'personnes affichées') + '.');
    }
    return;
  }

  /* Tous les termes doivent être trouvés : « h160 essais » ne renvoie que
     les personnes qui cumulent les deux. */
  const termes = requete.split(' ').filter(Boolean);
  let trouves = 0;

  for (const [personne, vue] of vueParPersonne) {
    const squad = personne.squad;
    const foin = normaliser([
      personne.nom,
      personne.poste,
      personne.perimetre,
      personne.role,
      squad ? squad.nom : '',
      squad ? squad.pole.code : poleActif
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
      + ' » dans le périmètre affiché. Toutes les cartes restent visibles, '
      + 'en retrait.'
    : accorder(trouves, 'personne correspond', 'personnes correspondent')
      + ' à « ' + brut.trim() + ' » sur ' + total
      + ' affichées. Les autres sont mises en retrait.';

  refs.resume.textContent = message;
  refs.resume.hidden = false;
  if (annonce) annoncer(message);
}

/* -------------------------------------------------------------------------
   14. Zoom
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
   15. Câblage
   ------------------------------------------------------------------------- */

/** Active les contrôles, une fois les données réellement affichées. */
function activerOutils(actif) {
  const controles = [
    refs.recherche, refs.zoom, refs.zoomMoins, refs.zoomPlus, refs.reinitialiser
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
      focaliser(refs.recherche);
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
  if (refs.reinitialiser) {
    refs.reinitialiser.addEventListener('click',
      (evt) => confirmerReinitialisation(evt.currentTarget));
  }
}

/** Câble les boutons des cartes et des blocs, par délégation. */
function cablerActions() {
  deleguer(refs.conteneur, '[data-action="deplacer"]', 'click', (evt, bouton) => {
    const personne = personneParElement.get(bouton);
    if (personne) ouvrirModaleDeplacement(personne, bouton);
  });

  deleguer(refs.conteneur, '[data-action="renommer-squad"]', 'click', (evt, bouton) => {
    const squad = squadParElement.get(bouton);
    if (squad) ouvrirRenommageSquad(squad, bouton);
  });

  deleguer(refs.conteneur, '[data-action="ajouter-squad"]', 'click', (evt, bouton) => {
    const pole = poleParElement.get(bouton);
    if (pole) ouvrirCreationSquad(pole, bouton);
  });
}

/* -------------------------------------------------------------------------
   16. Démarrage
   ------------------------------------------------------------------------- */

/** Résout les éléments statiques de la page. */
function resoudreRefs() {
  refs.racine = document.querySelector('.organigramme');
  refs.conteneur = document.getElementById('organigramme');
  refs.selecteur = document.getElementById('org-selecteur');
  refs.puces = document.getElementById('org-poles');
  refs.contexte = document.getElementById('org-contexte');
  refs.recherche = document.getElementById('org-recherche');
  refs.effacer = document.getElementById('org-effacer');
  refs.resume = document.getElementById('org-resume');
  refs.zoom = document.getElementById('org-zoom');
  refs.zoomMoins = document.getElementById('org-zoom-moins');
  refs.zoomPlus = document.getElementById('org-zoom-plus');
  refs.zoomValeur = document.getElementById('org-zoom-valeur');
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
  if (sauvegarde && !appliquerSauvegarde(sauvegarde)) {
    /* Sauvegarde incohérente avec les données : on la jette plutôt que de
       l'appliquer à moitié, et on le dit — le contenu affiché n'est pas
       celui que la personne avait laissé. */
    stockage.supprimer(CLE_ETAT);
    toast('La réorganisation enregistrée ne correspond plus aux données : '
      + 'l’organigramme d’origine est affiché.', 'alerte');
  }

  construireSelecteur();
  majSelecteur();
  rendre();
}

/** Point d'entrée. */
function demarrer() {
  initTheme();

  resoudreRefs();
  if (!refs.conteneur) return;

  /* Le pôle actif vient du hash avant tout affichage : la navigation
     principale doit déjà porter la bonne entrée courante. */
  poleActif = normaliserPole(etatUrl.lire().pole);
  etatUrl.ecrire({ pole: poleActif });
  initNav(PAGE_DE_POLE[poleActif]);

  appliquerZoom(stockage.lire(CLE_ZOOM, ZOOM_DEFAUT), false);
  cablerOutils();
  cablerActions();
  cablerGlisserDeposer();

  /* « Précédent », « Suivant » ou lien collé : le pôle suit l'URL. */
  etatUrl.ecouter((etat) => choisirPole(etat.pole, true));

  avecEtat(refs.conteneur, () => chargerDonnees('organigramme'), (donnees) => {
    rendreDepuisDonnees(donnees);
  }, {
    squelette: squelette,
    texteChargement: 'Chargement de l’organigramme en cours…',
    titreErreur: 'Organigramme indisponible',
    titreVide: 'Aucune équipe à afficher',
    texteVide: 'Le fichier de données ne décrit ni direction ni pôle. '
      + 'Il n’y a pas de hiérarchie à représenter pour le moment.',
    estVide: (donnees) => {
      if (!donnees || typeof donnees !== 'object') return true;
      const poles = Array.isArray(donnees.poles) ? donnees.poles.length : 0;
      return poles === 0 && !donnees.direction;
    },
    surEtat: (resultat) => {
      const pret = resultat.etat === 'succes';
      activerOutils(pret);

      if (!pret) {
        /* Ni modèle ni cartes : le filtre, le résumé et le sélecteur de
           pôle n'ont plus d'objet. */
        vueParPersonne = new Map();
        if (refs.selecteur) refs.selecteur.hidden = true;
        if (refs.resume) {
          refs.resume.textContent = '';
          refs.resume.hidden = true;
        }
        return;
      }

      annoncer('Organigramme chargé. Périmètre '
        + DESCRIPTION_POLE[poleActif].libelle + ' : '
        + accorder(effectifDe(poleActif), 'personne', 'personnes') + '.');
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
