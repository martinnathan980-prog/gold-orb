/* =========================================================================
   ETII Hub — Organigramme

   Le service ETII n'est pas plat, et cette page ne fait pas semblant : elle
   trace l'arbre réel, traits de rattachement compris.

       ETII                            le service
        └── direction de service       le sommet
             ├── ETIIA ─┐
             ├── ETIIE  ├─ un pôle : son responsable, puis ses squads
             └── ETIII ─┘   chaque squad : son leader, puis ses membres

   Ce que la page garantit :

     - Une VRAIE représentation d'arbre. Le sommet, le rail qui fourche
       vers les trois pôles, puis des branches indentées dont chaque
       élément trace son rail vertical et son coude. Les traits sont en
       CSS, posés par des pseudo-éléments : rien à recalculer au
       redimensionnement, rien à repeindre au défilement.

     - Chaque branche se plie et se déplie, au clic comme au clavier, par
       un bouton portant `aria-expanded` et `aria-controls`. Deux boutons
       globaux déplient ou replient tout.

     - Cliquer sur une personne ouvre sa fiche : poste, pôle, squad,
       périmètre, rattachement hiérarchique et collègues de squad. La
       fiche est un complément permanent, pas une fenêtre modale : elle ne
       confisque jamais le focus, Échap la referme et rend le focus à la
       personne qui l'a ouverte.

     - La recherche met en valeur les correspondances ET déplie les
       branches nécessaires pour les révéler. Les non-correspondances sont
       mises en retrait, jamais retirées du flux ni de l'ordre de
       tabulation.

     - Les avatars sont dessinés ici, en SVG : initiales et teinte
       dérivées de l'identifiant. Aucun appel réseau.

     - Le glisser-déposer entre squads a un équivalent clavier COMPLET :
       le bouton « Déplacer… » de chaque personne ouvre une modale qui
       fait exactement la même chose, y compris d'un pôle à l'autre. Les
       réorganisations sont locales (mémoire + localStorage) et annulables
       par un bouton de réinitialisation confirmé.

   Et ce qu'elle n'invente jamais : un champ absent s'affiche « à
   renseigner ». Aucun chiffre n'est écrit dans la page — l'effectif, le
   nombre de squads et les effectifs par pôle sont comptés dans le fichier
   de données, à chaque rendu.

   Contraintes structurelles du projet (SPEC §8) :
     - tout le DOM passe par el()/svg()/frag()/monter() : aucun innerHTML,
       aucun gestionnaire en attribut ;
     - aucun sélecteur ni gestionnaire construit par concaténation de
       chaînes : un nom de squad contenant une apostrophe ou un guillemet
       ne peut rien casser (SPEC §6.6). Le lien entre un élément du DOM et
       l'objet qu'il représente passe par une Map, jamais par un sélecteur
       reconstruit ;
     - aucune valeur de couleur, de dimension ou de durée : ce module ne
       pose que des classes, des attributs data-* et deux nombres sans
       unité (la teinte d'un avatar, le facteur de zoom).
   ========================================================================= */

import {
  el, svg, monter, deleguer, debounce, annoncer, toast, surlignerVers,
  ouvrirModale, etatUrl, stockage, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { normaliser, surligner } from './search.js';

/* -------------------------------------------------------------------------
   0. Constantes
   ------------------------------------------------------------------------- */

/** Clé de la réorganisation locale. */
const CLE_ORGANISATION = 'organigramme:organisation';

/** Clé des réglages d'affichage (densité, zoom). */
const CLE_AFFICHAGE = 'organigramme:affichage';

/**
 * Version du format enregistré. Un incrément invalide les sauvegardes
 * d'un format antérieur au lieu de les appliquer de travers.
 */
const VERSION_ETAT = 4;

/** Code du niveau service : « tous pôles confondus ». */
const SERVICE = 'ETII';

/**
 * Contrat d'URL : les quatre valeurs admises pour `#pole=`, et le lien de
 * navigation qui porte `aria-current="page"` pour chacune. Le niveau
 * service renvoie au tableau de bord, un pôle à son propre espace.
 */
const PAGE_DE_POLE = {
  ETII: 'index.html',
  ETIIA: 'etiia.html',
  ETIIE: 'etiie.html',
  ETIII: 'etiii.html'
};

/** Densités admises, dans l'ordre du sélecteur segmenté. */
const DENSITES = ['compacte', 'normale', 'detaillee'];

/** Bornes du zoom, en pourcentage. Elles doivent coïncider avec les
    attributs min/max/step du curseur déclaré dans la page. */
const ZOOM_MIN = 85;
const ZOOM_MAX = 140;
const ZOOM_DEFAUT = 100;

/** Anti-rebond de la recherche, en millisecondes. */
const DELAI_RECHERCHE = 120;

/**
 * Mention unique d'un champ déclaré mais vide. Toujours la même, partout :
 * le hub ne présente jamais une valeur plausible à la place d'un trou.
 */
const MENTION_VIDE = 'à renseigner';

/* -------------------------------------------------------------------------
   1. État du module
   ------------------------------------------------------------------------- */

/** Données telles que chargées. Jamais modifiées : servent de référence
    pour la réinitialisation et pour détecter une organisation modifiée. */
let donneesSource = null;

/** Modèle de travail : seul objet que les déplacements modifient. */
let modele = null;

/** Pôle affiché. Toujours l'une des quatre valeurs admises. */
let vue = SERVICE;

/** Requête de recherche brute, telle que saisie. */
let requete = '';

/** Termes normalisés de la requête. Vide = aucune recherche en cours. */
let termes = [];

/** Identifiants des personnes correspondant à la recherche. */
let correspondances = new Set();

/** Identifiant de la personne ouverte en fiche, ou null. */
let ficheOuverte = null;

/** Élément à refocaliser quand la fiche se referme. */
let declencheurFiche = null;

/** Densité d'affichage et facteur de zoom. */
let densite = 'normale';
let zoom = ZOOM_DEFAUT;

/** Identifiant de la personne en cours de glissement, ou null. */
let glissement = null;

/** Éléments statiques de la page, résolus une fois. */
const refs = {};

/**
 * Index des personnes : identifiant -> contexte complet.
 * { personne, role, pole, squad } — `pole` et `squad` valent null pour la
 * direction, `squad` vaut null pour un responsable de pôle.
 */
const index = new Map();

/** Identifiant -> bouton principal de la personne dans l'arbre rendu. */
const rendus = new Map();

/** Élément de dépôt -> { pole, squad } qu'il représente. */
const depots = new WeakMap();

/** Groupes pliables du rendu courant : { bouton, liste, type, pole, squad }. */
let groupes = [];

/** Racine de l'arbre rendu (porte densité, zoom et état de glissement). */
let racineArbre = null;

/** État d'ouverture, conservé d'un rendu à l'autre.
    Aucune clé composée : une Map par niveau, donc aucune concaténation. */
const ouverturePoles = new Map();          // code de pôle -> booléen
const ouvertureSquads = new Map();         // code de pôle -> Map(nom -> booléen)

/** Instantané de l'état d'ouverture pris au début d'une recherche. */
let ouvertureAvantRecherche = null;

/** Les contrôles de la barre d'outils sont-ils déjà câblés ? Le bouton
    « Réessayer » d'un état d'erreur rejoue le rendu : sans ce garde-fou,
    chaque tentative doublerait les écouteurs. */
let outilsCables = false;

/** Compteur d'identifiants générés pour aria-controls / aria-labelledby. */
let compteurId = 0;

/** Un identifiant unique et stable dans la page. */
function idLocal() {
  compteurId += 1;
  return 'org-n' + compteurId;
}

/* -------------------------------------------------------------------------
   2. Petits utilitaires de présentation
   ------------------------------------------------------------------------- */

/**
 * Une chaîne non vide, ou null. Sert de porte unique entre la donnée et
 * l'affichage : tout ce qui n'est pas une chaîne utilisable devient un
 * trou déclaré, jamais une valeur inventée.
 *
 * @param {*} valeur
 * @returns {string|null}
 */
function texte(valeur) {
  if (typeof valeur !== 'string') return null;
  const propre = valeur.trim();
  return propre === '' ? null : propre;
}

/**
 * Le nœud à afficher pour un champ : sa valeur, ou la mention « à
 * renseigner » reconnaissable du premier coup d'œil.
 *
 * @param {*} valeur
 * @returns {Node}
 */
function valeurOuVide(valeur) {
  const propre = texte(valeur);
  if (propre !== null) return document.createTextNode(propre);
  return el('span', { class: 'org-vide' }, MENTION_VIDE);
}

/**
 * Même chose, mais surlignée selon la recherche en cours. Le moteur de
 * recherche ne produit que des segments de texte brut ; les `<mark>`
 * naissent dans ui.js. Aucune chaîne ne transite par innerHTML.
 *
 * @param {*} valeur
 * @returns {Node}
 */
function valeurSurlignee(valeur) {
  const propre = texte(valeur);
  if (propre === null) return el('span', { class: 'org-vide' }, MENTION_VIDE);
  if (termes.length === 0) return document.createTextNode(propre);
  return surlignerVers(surligner(propre, requete));
}

/**
 * Accord d'un nom commun sur un effectif.
 *
 * @param {number} n
 * @param {string} singulier
 * @param {string} pluriel
 * @returns {string}
 */
function accord(n, singulier, pluriel) {
  return n + ' ' + (n > 1 ? pluriel : singulier);
}

/* -------------------------------------------------------------------------
   3. Modèle : construction, index, persistance
   ------------------------------------------------------------------------- */

/**
 * Copie de travail du fichier de données. On ne garde que les champs du
 * contrat : rien n'est ajouté, rien n'est deviné.
 *
 * @param {object} donnees
 * @returns {object}
 */
function construireModele(donnees) {
  const poles = [];

  for (const brut of donnees.poles) {
    if (!brut || typeof brut !== 'object') continue;

    const squads = [];
    const listeSquads = Array.isArray(brut.squads) ? brut.squads : [];

    for (const squad of listeSquads) {
      if (!squad || typeof squad !== 'object') continue;
      const membres = Array.isArray(squad.membres) ? squad.membres : [];
      squads.push({
        nom: squad.nom,
        membres: membres.filter((m) => m && typeof m === 'object').map(copiePersonne)
      });
    }

    poles.push({
      pole: brut.pole,
      responsable: (brut.responsable && typeof brut.responsable === 'object')
        ? copiePersonne(brut.responsable)
        : null,
      squads: squads
    });
  }

  return {
    service: donnees.service,
    direction: (donnees.direction && typeof donnees.direction === 'object')
      ? copiePersonne(donnees.direction)
      : null,
    poles: poles
  };
}

/**
 * Copie d'une personne, limitée aux cinq champs du contrat.
 * @param {object} p
 * @returns {object}
 */
function copiePersonne(p) {
  return {
    id: p.id,
    nom: p.nom,
    poste: p.poste,
    role: p.role,
    perimetre: p.perimetre
  };
}

/**
 * Reconstruit l'index des personnes à partir du modèle courant.
 * Tout le reste de la page le consulte : c'est la seule façon d'aller
 * d'un identifiant à son contexte.
 */
function construireIndex() {
  index.clear();

  if (modele.direction && texte(modele.direction.id)) {
    index.set(modele.direction.id, {
      personne: modele.direction,
      role: 'direction',
      pole: null,
      squad: null
    });
  }

  for (const pole of modele.poles) {
    if (pole.responsable && texte(pole.responsable.id)) {
      index.set(pole.responsable.id, {
        personne: pole.responsable,
        role: 'responsable',
        pole: pole.pole,
        squad: null
      });
    }
    for (const squad of pole.squads) {
      for (const membre of squad.membres) {
        if (!texte(membre.id)) continue;
        index.set(membre.id, {
          personne: membre,
          role: membre.role === 'leader' ? 'leader' : 'membre',
          pole: pole.pole,
          squad: squad.nom
        });
      }
    }
  }
}

/**
 * Retrouve l'objet squad d'un pôle par son nom.
 * Comparaison de valeurs, jamais de sélecteur reconstruit : un nom
 * contenant une apostrophe, un guillemet ou un chevron passe sans risque.
 *
 * @param {string} codePole
 * @param {string} nomSquad
 * @returns {object|null}
 */
function trouverSquad(codePole, nomSquad) {
  for (const pole of modele.poles) {
    if (pole.pole !== codePole) continue;
    for (const squad of pole.squads) {
      if (squad.nom === nomSquad) return squad;
    }
  }
  return null;
}

/**
 * Range les membres d'une squad : leader d'abord, le reste dans l'ordre
 * où il est arrivé. Le rang vient du champ `role` du fichier ; il n'est
 * jamais deviné à partir du poste.
 *
 * @param {object} squad
 */
function ordonner(squad) {
  const leaders = squad.membres.filter((m) => m.role === 'leader');
  const autres = squad.membres.filter((m) => m.role !== 'leader');
  squad.membres = leaders.concat(autres);
}

/**
 * Affectation d'origine de chaque membre, telle que le fichier la donne.
 * @returns {Map<string, {pole: string, squad: string}>}
 */
function affectationsSource() {
  const carte = new Map();
  if (!donneesSource || !Array.isArray(donneesSource.poles)) return carte;

  for (const pole of donneesSource.poles) {
    const squads = Array.isArray(pole && pole.squads) ? pole.squads : [];
    for (const squad of squads) {
      const membres = Array.isArray(squad && squad.membres) ? squad.membres : [];
      for (const membre of membres) {
        if (membre && texte(membre.id)) {
          carte.set(membre.id, { pole: pole.pole, squad: squad.nom });
        }
      }
    }
  }
  return carte;
}

/** Affectation courante de chaque membre dans le modèle de travail. */
function affectationsCourantes() {
  const carte = new Map();
  for (const pole of modele.poles) {
    for (const squad of pole.squads) {
      for (const membre of squad.membres) {
        if (texte(membre.id)) carte.set(membre.id, { pole: pole.pole, squad: squad.nom });
      }
    }
  }
  return carte;
}

/**
 * L'organisation affichée diffère-t-elle de celle du fichier ?
 * @returns {boolean}
 */
function organisationModifiee() {
  const origine = affectationsSource();
  const courante = affectationsCourantes();
  if (origine.size !== courante.size) return true;

  for (const [id, place] of origine) {
    const ici = courante.get(id);
    if (!ici || ici.pole !== place.pole || ici.squad !== place.squad) return true;
  }
  return false;
}

/** Enregistre l'organisation courante. L'échec du stockage est sans effet
    sur la page : elle perd sa mémoire, pas ses fonctions. */
function enregistrerOrganisation() {
  const affectations = [];
  for (const [id, place] of affectationsCourantes()) {
    affectations.push({ id: id, pole: place.pole, squad: place.squad });
  }
  stockage.ecrire(CLE_ORGANISATION, {
    version: VERSION_ETAT,
    affectations: affectations
  });
}

/**
 * Rejoue une réorganisation enregistrée sur le modèle fraîchement
 * construit. Toute affectation qui ne correspond plus à rien (squad
 * disparue, identifiant inconnu) est ignorée : la personne reste là où le
 * fichier la place.
 *
 * @returns {boolean} vrai si au moins une affectation a été rejouée
 */
function appliquerOrganisationEnregistree() {
  const brut = stockage.lire(CLE_ORGANISATION, null);
  if (!brut || typeof brut !== 'object') return false;
  if (brut.version !== VERSION_ETAT || !Array.isArray(brut.affectations)) return false;

  const souhait = new Map();
  for (const entree of brut.affectations) {
    if (!entree || typeof entree !== 'object') continue;
    if (!texte(entree.id) || !texte(entree.pole)) continue;
    souhait.set(entree.id, { pole: entree.pole, squad: entree.squad });
  }
  if (souhait.size === 0) return false;

  /* Toutes les personnes sont retirées de leurs squads, puis replacées
     dans l'ordre du fichier : la destination compte, pas l'ordre dans
     lequel les déplacements ont eu lieu. */
  const origine = affectationsCourantes();
  const personnes = new Map();
  for (const pole of modele.poles) {
    for (const squad of pole.squads) {
      for (const membre of squad.membres) personnes.set(membre.id, membre);
      squad.membres = [];
    }
  }

  let rejoue = false;
  for (const [id, membre] of personnes) {
    const depart = origine.get(id);
    const vise = souhait.get(id) || depart;
    let cible = vise ? trouverSquad(vise.pole, vise.squad) : null;
    if (!cible && depart) cible = trouverSquad(depart.pole, depart.squad);
    if (!cible) continue;
    cible.membres.push(membre);
    if (depart && vise && (vise.pole !== depart.pole || vise.squad !== depart.squad)) {
      rejoue = true;
    }
  }

  for (const pole of modele.poles) for (const squad of pole.squads) ordonner(squad);
  return rejoue;
}

/* -------------------------------------------------------------------------
   4. Comptages — lus dans les données, jamais écrits dans la page
   ------------------------------------------------------------------------- */

/** Effectif d'un pôle : son responsable, s'il est déclaré, plus ses membres. */
function effectifPole(pole) {
  let total = pole.responsable ? 1 : 0;
  for (const squad of pole.squads) total += squad.membres.length;
  return total;
}

/** Effectif du service entier. */
function effectifService() {
  let total = modele.direction ? 1 : 0;
  for (const pole of modele.poles) total += effectifPole(pole);
  return total;
}

/** Nombre total de squads déclarées. */
function nombreSquads() {
  let total = 0;
  for (const pole of modele.poles) total += pole.squads.length;
  return total;
}

/* -------------------------------------------------------------------------
   5. Avatar généré localement
   ------------------------------------------------------------------------- */

/**
 * Initiales d'un libellé. « Personne 07 » donne « P07 » : la lettre du
 * premier mot, puis le dernier mot s'il est numérique. Deux personnes
 * différentes ne se confondent donc pas.
 *
 * @param {*} nom
 * @returns {string}
 */
function initiales(nom) {
  const propre = texte(nom);
  if (propre === null) return '?';

  const mots = propre.split(/\s+/).filter(Boolean);
  const premier = Array.from(mots[0])[0].toLocaleUpperCase('fr');
  if (mots.length === 1) return premier;

  const dernier = mots[mots.length - 1];
  if (/^\d+$/.test(dernier)) return premier + dernier.slice(-2);
  return premier + Array.from(dernier)[0].toLocaleUpperCase('fr');
}

/**
 * Teinte d'un avatar : un angle de 0 à 359 dérivé de l'identifiant, par
 * une somme pondérée stable. Le même identifiant donne toujours la même
 * teinte, d'une session à l'autre et d'un navigateur à l'autre.
 *
 * Seul l'angle est calculé ici. La saturation et les clartés restent dans
 * la feuille de style de la page, où elles suivent le thème.
 *
 * @param {*} id
 * @returns {number}
 */
function teinteDe(id) {
  const source = texte(id) || '';
  let somme = 0;
  for (let i = 0; i < source.length; i += 1) {
    somme = (somme * 31 + source.charCodeAt(i)) % 100003;
  }
  return somme % 360;
}

/**
 * L'avatar : un cercle teinté et deux ou trois initiales, en SVG inline.
 * Purement décoratif — le nom est écrit juste à côté — donc masqué aux
 * technologies d'assistance.
 *
 * @param {object} personne
 * @param {boolean} [grand]
 * @returns {SVGElement}
 */
function avatar(personne, grand) {
  return svg('svg', {
    class: ['org-avatar', grand ? 'org-avatar--grand' : null],
    viewBox: '0 0 40 40',
    'aria-hidden': 'true',
    focusable: 'false',
    style: { '--org-teinte': teinteDe(personne && personne.id) }
  },
  svg('circle', { class: 'org-avatar__fond', cx: '20', cy: '20', r: '20' }),
  svg('text', {
    class: 'org-avatar__initiales',
    x: '20',
    y: '20',
    'text-anchor': 'middle',
    'dominant-baseline': 'central'
  }, initiales(personne && personne.nom)));
}

/* -------------------------------------------------------------------------
   6. Recherche : correspondances et dépliage automatique
   ------------------------------------------------------------------------- */

/**
 * Texte indexé d'une personne : tout ce sur quoi la recherche porte,
 * normalisé une fois (minuscules, sans diacritiques).
 *
 * @param {object} entree  une valeur de l'index
 * @returns {string}
 */
function foin(entree) {
  const morceaux = [
    entree.personne.nom,
    entree.personne.poste,
    entree.personne.perimetre,
    entree.pole,
    entree.squad
  ];
  return normaliser(morceaux.filter((m) => texte(m) !== null).join(' '));
}

/**
 * Recalcule les correspondances, puis règle l'ouverture des branches pour
 * que chaque personne trouvée soit visible sans un seul clic.
 *
 * L'état d'ouverture manuel est photographié au début d'une recherche et
 * restitué quand elle se termine : chercher ne détruit pas le travail de
 * pliage de l'utilisateur.
 */
function appliquerRecherche() {
  const avant = termes.length > 0;
  const normalisee = normaliser(requete);
  termes = normalisee ? normalisee.split(' ').filter(Boolean) : [];
  const apres = termes.length > 0;

  correspondances = new Set();
  if (apres) {
    for (const [id, entree] of index) {
      const cible = foin(entree);
      if (termes.every((t) => cible.includes(t))) correspondances.add(id);
    }
  }

  if (!avant && apres) photographierOuverture();

  if (apres) {
    /* Une branche s'ouvre si elle contient une correspondance, et se
       referme sinon : le résultat est lisible d'un coup d'œil. */
    for (const pole of modele.poles) {
      let poleTrouve = pole.responsable ? correspondances.has(pole.responsable.id) : false;
      for (const squad of pole.squads) {
        const trouve = squad.membres.some((m) => correspondances.has(m.id));
        definirOuvertureSquad(pole.pole, squad.nom, trouve);
        if (trouve) poleTrouve = true;
      }
      ouverturePoles.set(pole.pole, poleTrouve);
    }
  } else if (avant && !apres) {
    restituerOuverture();
  }

  rendreArbre();
  annoncerResultat();
}

/** Nombre de personnes trouvées, écrit dans la région d'état de la page. */
function annoncerResultat() {
  if (!refs.resultat) return;

  if (termes.length === 0) {
    refs.resultat.textContent = '';
    return;
  }
  const total = correspondances.size;
  refs.resultat.textContent = total === 0
    ? 'Aucune personne ne correspond à cette recherche.'
    : accord(total, 'personne trouvée', 'personnes trouvées')
      + ' — les branches concernées sont dépliées.';
}

/* -------------------------------------------------------------------------
   7. Pliage : état conservé d'un rendu à l'autre
   ------------------------------------------------------------------------- */

/** Un pôle est-il déplié ? Ouvert par défaut. */
function ouvertPole(code) {
  return ouverturePoles.get(code) !== false;
}

/** Une squad est-elle dépliée ? Ouverte par défaut. */
function ouvertSquad(code, nom) {
  const parPole = ouvertureSquads.get(code);
  if (!parPole) return true;
  return parPole.get(nom) !== false;
}

/** Fixe l'ouverture d'une squad. */
function definirOuvertureSquad(code, nom, ouvert) {
  let parPole = ouvertureSquads.get(code);
  if (!parPole) {
    parPole = new Map();
    ouvertureSquads.set(code, parPole);
  }
  parPole.set(nom, ouvert === true);
}

/** Photographie l'état d'ouverture courant, avant de le remplacer. */
function photographierOuverture() {
  const squads = new Map();
  for (const [code, parPole] of ouvertureSquads) squads.set(code, new Map(parPole));
  ouvertureAvantRecherche = { poles: new Map(ouverturePoles), squads: squads };
}

/** Restitue l'état photographié, s'il y en a un. */
function restituerOuverture() {
  if (!ouvertureAvantRecherche) return;

  ouverturePoles.clear();
  for (const [code, valeur] of ouvertureAvantRecherche.poles) ouverturePoles.set(code, valeur);

  ouvertureSquads.clear();
  for (const [code, parPole] of ouvertureAvantRecherche.squads) {
    ouvertureSquads.set(code, new Map(parPole));
  }
  ouvertureAvantRecherche = null;
}

/**
 * Plie ou déplie une branche et met à jour son bouton.
 * L'état visuel et l'état accessible n'ont qu'une source : aria-expanded.
 *
 * @param {object} groupe  une entrée de `groupes`
 * @param {boolean} ouvert
 */
function appliquerOuverture(groupe, ouvert) {
  groupe.bouton.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  groupe.liste.hidden = !ouvert;

  if (groupe.type === 'pole') ouverturePoles.set(groupe.pole, ouvert);
  else definirOuvertureSquad(groupe.pole, groupe.squad, ouvert);
}

/**
 * Déplie ou replie l'ensemble des branches visibles.
 * @param {boolean} ouvert
 */
function toutBasculer(ouvert) {
  for (const groupe of groupes) appliquerOuverture(groupe, ouvert);
  annoncer(ouvert
    ? 'Toutes les branches sont dépliées.'
    : 'Toutes les branches sont repliées.');
}

/* -------------------------------------------------------------------------
   8. Construction de l'arbre
   ------------------------------------------------------------------------- */

/** Les pôles à afficher, selon le périmètre choisi. */
function polesVisibles() {
  if (vue === SERVICE) return modele.poles;
  return modele.poles.filter((p) => p.pole === vue);
}

/**
 * Le bouton de pliage d'une branche.
 *
 * @param {string} idListe   identifiant de la liste commandée
 * @param {boolean} ouvert
 * @param {string} libelle   ce que le bouton plie ou déplie, en toutes lettres
 * @returns {HTMLElement}
 */
function boutonPliage(idListe, ouvert, libelle) {
  return el('button', {
    type: 'button',
    class: 'org-plier',
    dataPlier: '',
    ariaExpanded: ouvert ? 'true' : 'false',
    ariaControls: idListe,
    ariaLabel: 'Plier ou déplier : ' + libelle
  }, el('span', { class: 'org-plier__chevron', ariaHidden: 'true' }, '▾'));
}

/**
 * Une ligne de personne : avatar, nom, poste, périmètre, et — pour les
 * personnes rattachées à une squad — le bouton « Déplacer… », équivalent
 * clavier intégral du glisser-déposer.
 *
 * @param {object} entree  une valeur de l'index
 * @returns {HTMLElement}
 */
function lignePersonne(entree) {
  const personne = entree.personne;
  const deplacable = entree.squad !== null;

  const principal = el('button', {
    type: 'button',
    class: 'org-personne__principal',
    dataPersonne: personne.id,
    ariaCurrent: ficheOuverte === personne.id ? 'true' : null
  },
  avatar(personne),
  el('span', { class: 'org-personne__identite' },
    el('span', { class: 'org-personne__nom' }, valeurSurlignee(personne.nom)),
    el('span', { class: 'org-personne__poste' }, valeurSurlignee(personne.poste)),
    el('span', { class: 'org-personne__perimetre' },
      'Périmètre : ', valeurOuVide(personne.perimetre))),
  entree.role === 'leader'
    ? el('span', { class: 'org-etiquette' }, 'Leader')
    : null,
  entree.role === 'responsable'
    ? el('span', { class: 'org-etiquette' }, 'Responsable')
    : null,
  entree.role === 'direction'
    ? el('span', { class: 'org-etiquette' }, 'Direction')
    : null);

  if (texte(personne.id)) rendus.set(personne.id, principal);

  const ligne = el('div', {
    class: 'org-personne',
    dataRole: entree.role,
    draggable: deplacable ? 'true' : null,
    dataGlissable: deplacable ? personne.id : null,
    dataTrouve: correspondances.has(personne.id) ? 'true' : null,
    dataRetrait: (termes.length > 0 && !correspondances.has(personne.id)) ? 'true' : null
  },
  principal,
  deplacable
    ? el('button', {
      type: 'button',
      class: 'org-personne__deplacer',
      dataDeplacer: personne.id,
      ariaLabel: 'Déplacer ' + (texte(personne.nom) || 'cette personne')
        + ' vers une autre squad'
    }, el('span', { ariaHidden: 'true' }, '⇄'))
    : null);

  return ligne;
}

/** Le sommet : la direction de service, et le tronc qui en descend. */
function sommet() {
  const entree = modele.direction && index.get(modele.direction.id);

  const carte = entree
    ? el('div', { class: 'org-noeud org-noeud--direction' },
      el('p', { class: 'org-noeud__meta' },
        texte(modele.service) || SERVICE, ' · Direction de service'),
      lignePersonne(entree))
    : el('div', { class: 'org-noeud org-noeud--direction' },
      el('p', { class: 'org-noeud__titre' }, 'Direction'),
      el('p', { class: 'org-noeud__meta' },
        el('span', { class: 'org-vide' }, MENTION_VIDE)));

  return el('div', { class: 'org-sommet' },
    el('div', { class: 'org-sommet__noeud' }, carte),
    el('span', { class: 'org-sommet__tronc', ariaHidden: 'true' }));
}

/** La branche d'une squad : son nœud, sa zone de dépôt, ses membres. */
function brancheSquad(pole, squad) {
  const idListe = idLocal();
  const idTitre = idLocal();
  const ouvert = ouvertSquad(pole.pole, squad.nom);
  const nomLisible = texte(squad.nom) || MENTION_VIDE;

  const noeud = el('div', { class: 'org-noeud org-noeud--squad' },
    el('p', { class: 'org-noeud__titre', id: idTitre }, valeurSurlignee(squad.nom)),
    el('p', { class: 'org-noeud__meta' },
      accord(squad.membres.length, 'personne', 'personnes'),
      el('span', { class: 'org-noeud__depot' }, 'Déposer ici')));

  const bouton = boutonPliage(idListe, ouvert, 'squad ' + nomLisible);

  const liste = el('ul', {
    class: 'org-branches',
    id: idListe,
    ariaLabelledby: idTitre,
    hidden: !ouvert
  },
  squad.membres.map((membre) => {
    const entree = index.get(membre.id);
    return el('li', { class: 'org-branche' }, entree ? lignePersonne(entree) : null);
  }));

  const branche = el('li', {
    class: 'org-branche',
    dataDepot: '',
    dataVide: (termes.length > 0
      && !squad.membres.some((m) => correspondances.has(m.id))) ? 'true' : null
  },
  el('div', { class: 'org-tete' }, bouton, noeud),
  liste);

  depots.set(branche, { pole: pole.pole, squad: squad.nom });
  groupes.push({
    bouton: bouton,
    liste: liste,
    type: 'squad',
    pole: pole.pole,
    squad: squad.nom
  });

  return branche;
}

/** La colonne d'un pôle : son nœud, son responsable, ses squads. */
function branchePole(pole) {
  const idListe = idLocal();
  const idTitre = idLocal();
  const ouvert = ouvertPole(pole.pole);
  const codeLisible = texte(pole.pole) || MENTION_VIDE;
  const responsable = pole.responsable && index.get(pole.responsable.id);

  const bouton = boutonPliage(idListe, ouvert, 'pôle ' + codeLisible);

  /* Le bouton de pliage est DANS la carte du pôle, et non à côté : la
     carte occupe ainsi toute la colonne, et le trait qui descend du rail
     tombe exactement sur son milieu. */
  const noeud = el('div', { class: 'org-noeud org-noeud--pole' },
    bouton,
    el('div', { class: 'org-noeud__corps' },
      el('p', { class: 'org-noeud__titre', id: idTitre }, valeurSurlignee(pole.pole)),
      el('p', { class: 'org-noeud__meta' },
        accord(effectifPole(pole), 'personne', 'personnes'),
        el('span', null, accord(pole.squads.length, 'squad', 'squads')))));

  const liste = el('ul', {
    class: 'org-branches',
    id: idListe,
    ariaLabelledby: idTitre,
    hidden: !ouvert
  },
  el('li', { class: 'org-branche' },
    responsable
      ? lignePersonne(responsable)
      : el('p', { class: 'org-noeud__meta' },
        'Responsable de pôle : ', el('span', { class: 'org-vide' }, MENTION_VIDE))),
  pole.squads.map((squad) => brancheSquad(pole, squad)));

  groupes.push({
    bouton: bouton,
    liste: liste,
    type: 'pole',
    pole: pole.pole,
    squad: null
  });

  return el('li', { class: 'org-pole', dataPole: pole.pole },
    el('span', { class: 'org-pole__attache', ariaHidden: 'true' }),
    noeud,
    liste);
}

/**
 * Rendu complet de l'arbre. Appelé à chaque changement d'état : le DOM
 * n'est jamais rafistolé, il est reconstruit à partir du modèle. Avec
 * quelques dizaines de personnes, c'est instantané — et cela supprime
 * toute possibilité de divergence entre l'affichage et les données.
 */
function rendreArbre() {
  if (!refs.plan || !modele) return;

  rendus.clear();
  groupes = [];

  const visibles = polesVisibles();

  racineArbre = el('div', {
    class: 'organigramme',
    dataDensite: densite,
    style: { '--org-echelle': zoom / 100 }
  },
  sommet(),
  visibles.length
    ? el('ul', { class: 'org-poles' }, visibles.map(branchePole))
    : el('p', { class: 'texte-doux' },
      'Aucun pôle ne correspond au périmètre choisi.'));

  monter(refs.plan, racineArbre);
  marquerPersonneCourante();
}

/* -------------------------------------------------------------------------
   9. Bandeau de repères
   ------------------------------------------------------------------------- */

/** Un repère : une valeur comptée, et ce qu'elle mesure. */
function repere(valeur, libelle, codePole) {
  return el('li', {
    class: ['org-repere', codePole ? 'org-repere--pole' : null],
    dataPole: codePole || null
  },
  el('span', { class: 'org-repere__valeur' }, String(valeur)),
  el('span', { class: 'org-repere__libelle' }, libelle));
}

/** Le bandeau entier. Toutes les valeurs sont comptées dans les données. */
function rendreReperes() {
  if (!refs.reperes || !modele) return;

  const parPole = modele.poles.map((pole) => repere(
    effectifPole(pole),
    (texte(pole.pole) || MENTION_VIDE) + ' · ' + accord(pole.squads.length, 'squad', 'squads'),
    texte(pole.pole)
  ));

  monter(refs.reperes, el('ul', { class: 'org-reperes' },
    repere(effectifService(), 'Effectif du service'),
    repere(modele.poles.length, 'Pôles'),
    repere(nombreSquads(), 'Squads'),
    parPole));

  refs.reperes.setAttribute('aria-busy', 'false');
}

/* -------------------------------------------------------------------------
   10. Fiche de personne
   ------------------------------------------------------------------------- */

/**
 * Le responsable hiérarchique d'une personne, déduit de sa position dans
 * l'arbre — c'est précisément ce que l'arbre dit. Rien n'est inventé :
 * si le niveau supérieur n'est pas déclaré, il n'y a pas de rattachement
 * à afficher.
 *
 * @param {object} entree
 * @returns {object|null} une entrée de l'index, ou null
 */
function superieur(entree) {
  if (entree.role === 'direction') return null;

  if (entree.role === 'responsable') {
    return modele.direction ? index.get(modele.direction.id) || null : null;
  }

  const pole = modele.poles.find((p) => p.pole === entree.pole) || null;
  if (!pole) return null;

  if (entree.role === 'leader') {
    return pole.responsable ? index.get(pole.responsable.id) || null : null;
  }

  const squad = trouverSquad(entree.pole, entree.squad);
  const leader = squad ? squad.membres.find((m) => m.role === 'leader') : null;
  if (leader && leader.id !== entree.personne.id) return index.get(leader.id) || null;
  return pole.responsable ? index.get(pole.responsable.id) || null : null;
}

/** Les autres personnes de la même squad. */
function collegues(entree) {
  if (entree.squad === null) return [];
  const squad = trouverSquad(entree.pole, entree.squad);
  if (!squad) return [];
  return squad.membres
    .filter((m) => m.id !== entree.personne.id)
    .map((m) => index.get(m.id))
    .filter(Boolean);
}

/** Les personnes directement encadrées : pôles pour la direction, leaders
    de squad pour un responsable de pôle. */
function encadres(entree) {
  if (entree.role === 'direction') {
    return modele.poles
      .map((p) => (p.responsable ? index.get(p.responsable.id) : null))
      .filter(Boolean);
  }
  if (entree.role === 'responsable') {
    const pole = modele.poles.find((p) => p.pole === entree.pole);
    if (!pole) return [];
    return pole.squads
      .map((s) => s.membres.find((m) => m.role === 'leader'))
      .filter(Boolean)
      .map((m) => index.get(m.id))
      .filter(Boolean);
  }
  return [];
}

/** Une ligne « clé / valeur » de la fiche. */
function ligneFiche(cle, valeur) {
  return [
    el('dt', { class: 'org-fiche__cle' }, cle),
    el('dd', { class: 'org-fiche__valeur' }, valeur)
  ];
}

/** Une puce ouvrant la fiche d'une autre personne. */
function puceVers(entree) {
  return el('li', null,
    el('button', {
      type: 'button',
      class: 'org-puce',
      dataPersonne: entree.personne.id
    },
    avatar(entree.personne),
    el('span', null, valeurOuVide(entree.personne.nom))));
}

/** Un groupe de puces, ou rien si la liste est vide. */
function groupePuces(intitule, liste) {
  if (liste.length === 0) return null;
  return el('div', { class: 'org-fiche__groupe' },
    el('p', { class: 'org-fiche__intitule' },
      intitule + ' (' + liste.length + ')'),
    el('ul', { class: 'org-fiche__puces' }, liste.map(puceVers)));
}

/**
 * Contenu de la fiche. Aucun champ n'est masqué quand il est vide : il
 * est affiché avec la mention « à renseigner », pour qu'on sache que la
 * donnée manque et non que le champ n'existe pas.
 *
 * @param {object} entree
 * @returns {DocumentFragment|Array}
 */
function contenuFiche(entree) {
  const personne = entree.personne;
  const chef = superieur(entree);

  const lignes = [];
  lignes.push(ligneFiche('Poste', valeurOuVide(personne.poste)));

  if (entree.role === 'direction') {
    lignes.push(ligneFiche('Périmètre organisationnel',
      texte(modele.service) || MENTION_VIDE));
  } else {
    lignes.push(ligneFiche('Pôle',
      el('span', { class: 'org-fiche__pole', dataPole: texte(entree.pole) },
        el('span', { class: 'org-fiche__filet', ariaHidden: 'true' }),
        valeurOuVide(entree.pole))));
  }

  if (entree.role === 'leader' || entree.role === 'membre') {
    lignes.push(ligneFiche('Squad', valeurOuVide(entree.squad)));
  }

  lignes.push(ligneFiche('Périmètre', valeurOuVide(personne.perimetre)));

  /* Le rattachement est un groupe à part, et non une ligne du tableau :
     c'est une personne, donc une puce qui ouvre sa fiche — pas une
     valeur à lire. */
  const rattachement = el('div', { class: 'org-fiche__groupe' },
    el('p', { class: 'org-fiche__intitule' }, 'Rattachement hiérarchique'),
    entree.role === 'direction'
      ? el('p', { class: 'org-fiche__valeur sans-marge' }, 'Sommet du service')
      : (chef
        ? el('ul', { class: 'org-fiche__puces' }, puceVers(chef))
        : el('p', { class: 'org-fiche__valeur sans-marge' },
          el('span', { class: 'org-vide' }, MENTION_VIDE))));

  return [
    el('header', { class: 'org-fiche__entete' },
      el('div', { class: 'org-fiche__identite' },
        avatar(personne, true),
        el('div', null,
          el('h2', { class: 'org-fiche__titre', id: 'org-fiche-titre' },
            valeurOuVide(personne.nom)),
          el('p', { class: 'org-fiche__poste' }, valeurOuVide(personne.poste)))),
      el('button', {
        type: 'button',
        class: 'org-fiche__fermer',
        dataFermerFiche: '',
        ariaLabel: 'Fermer la fiche'
      }, el('span', { ariaHidden: 'true' }, '×'))),

    el('dl', { class: 'org-fiche__liste' }, lignes),

    rattachement,
    groupePuces('Collègues de squad', collegues(entree)),
    groupePuces(entree.role === 'direction' ? 'Responsables de pôle' : 'Leaders de squad',
      encadres(entree)),

    entree.squad !== null
      ? el('div', { class: 'org-fiche__actions' },
        el('button', {
          type: 'button',
          class: 'bouton bouton--secondaire bouton--compact',
          dataDeplacer: personne.id
        }, 'Déplacer vers une autre squad…'))
      : null
  ];
}

/** Reporte `aria-current` sur la personne ouverte, et sur elle seule. */
function marquerPersonneCourante() {
  for (const [id, bouton] of rendus) {
    if (id === ficheOuverte) bouton.setAttribute('aria-current', 'true');
    else bouton.removeAttribute('aria-current');
  }
}

/**
 * Ouvre la fiche d'une personne.
 *
 * @param {string} id
 * @param {Element} [declencheur] élément à refocaliser à la fermeture
 */
function ouvrirFiche(id, declencheur) {
  const entree = index.get(id);
  if (!entree || !refs.fiche) return;

  /* Le déclencheur d'origine est conservé tant que la fiche reste
     ouverte : naviguer de collègue en collègue à l'intérieur de la fiche
     ne doit pas faire perdre le point de retour dans l'arbre. */
  if (declencheur && !ficheOuverte) declencheurFiche = declencheur;

  ficheOuverte = id;
  monter(refs.fiche, contenuFiche(entree));
  refs.fiche.hidden = false;
  if (refs.scene) refs.scene.classList.add('org-scene--fiche-ouverte');

  marquerPersonneCourante();
  refs.fiche.focus();
  majUrl();
}

/**
 * Reconstruit le contenu de la fiche ouverte sans toucher au focus.
 * Appelé après un déplacement : la squad et les collègues ont changé, mais
 * l'utilisateur n'a pas demandé à être emmené ailleurs.
 */
function rafraichirFiche() {
  if (!refs.fiche || refs.fiche.hidden || !ficheOuverte) return;
  const entree = index.get(ficheOuverte);
  if (!entree) { fermerFiche(false); return; }
  monter(refs.fiche, contenuFiche(entree));
  marquerPersonneCourante();
}

/**
 * Referme la fiche et rend le focus à son point de départ.
 * @param {boolean} [rendreFocus=true]
 */
function fermerFiche(rendreFocus) {
  if (!refs.fiche || refs.fiche.hidden) return;

  const precedent = ficheOuverte;
  ficheOuverte = null;
  refs.fiche.hidden = true;
  monter(refs.fiche);
  if (refs.scene) refs.scene.classList.remove('org-scene--fiche-ouverte');
  marquerPersonneCourante();

  if (rendreFocus !== false) {
    const cible = (declencheurFiche && declencheurFiche.isConnected)
      ? declencheurFiche
      : (precedent ? rendus.get(precedent) : null);
    if (cible && cible.isConnected) cible.focus();
    else if (refs.recherche) refs.recherche.focus();
  }
  declencheurFiche = null;
  majUrl();
}

/* -------------------------------------------------------------------------
   11. Déplacement : glisser-déposer et équivalent clavier
   ------------------------------------------------------------------------- */

/** Toutes les squads du service, dans l'ordre de l'arbre. */
function destinations() {
  const liste = [];
  for (const pole of modele.poles) {
    for (const squad of pole.squads) {
      liste.push({
        pole: pole.pole,
        squad: squad.nom,
        effectif: squad.membres.length
      });
    }
  }
  return liste;
}

/**
 * Déplace une personne vers une autre squad. Retourne faux si le
 * déplacement n'a pas de sens (personne inconnue, personne non rattachée
 * à une squad, squad de destination absente, ou destination identique).
 *
 * @param {string} id
 * @param {{pole: string, squad: string}} cible
 * @returns {boolean}
 */
function deplacer(id, cible) {
  const entree = index.get(id);
  if (!entree || entree.squad === null || !cible) return false;
  if (entree.pole === cible.pole && entree.squad === cible.squad) return false;

  const source = trouverSquad(entree.pole, entree.squad);
  const arrivee = trouverSquad(cible.pole, cible.squad);
  if (!source || !arrivee) return false;

  const position = source.membres.findIndex((m) => m.id === id);
  if (position === -1) return false;

  const [personne] = source.membres.splice(position, 1);
  arrivee.membres.push(personne);
  ordonner(source);
  ordonner(arrivee);

  enregistrerOrganisation();
  construireIndex();

  /* La branche d'arrivée s'ouvre : on ne déplace pas quelqu'un dans un
     tiroir fermé. */
  definirOuvertureSquad(cible.pole, cible.squad, true);
  ouverturePoles.set(cible.pole, true);

  if (termes.length > 0) appliquerRecherche();
  else rendreArbre();

  rendreReperes();
  majEtatReinitialisation();

  /* Le focus suit la personne déplacée jusqu'à sa nouvelle place : après
     un déplacement au clavier, on se retrouve exactement là où l'on vient
     d'arriver, et non renvoyé en haut de page. */
  rafraichirFiche();
  const bouton = rendus.get(id);
  if (bouton) bouton.focus();

  const nom = texte(personne.nom) || 'La personne';
  toast(nom + ' rejoint ' + (texte(cible.squad) || MENTION_VIDE)
    + ' (' + (texte(cible.pole) || MENTION_VIDE) + ').', 'succes');
  return true;
}

/**
 * Modale de déplacement : l'équivalent clavier intégral du
 * glisser-déposer. Toutes les squads du service y sont, celle d'origine
 * comprise et signalée comme telle.
 *
 * @param {string} id
 * @param {Element} [declencheur]
 */
function ouvrirDeplacement(id, declencheur) {
  const entree = index.get(id);
  if (!entree || entree.squad === null) return;

  const nom = texte(entree.personne.nom) || 'cette personne';
  const nomGroupe = idLocal();
  const choix = destinations();
  let selection = null;

  const options = choix.map((destination) => {
    const actuelle = destination.pole === entree.pole
      && destination.squad === entree.squad;
    if (actuelle) selection = destination;

    return el('label', { class: 'case' },
      el('input', {
        class: 'case__controle',
        type: 'radio',
        name: nomGroupe,
        checked: actuelle,
        /* La destination est capturée par la fermeture : aucune valeur
           n'est sérialisée dans l'attribut, donc aucun nom de squad n'a
           besoin d'être échappé. */
        onChange: () => { selection = destination; }
      }),
      el('span', { class: 'case__texte' },
        valeurOuVide(destination.pole), ' · ', valeurOuVide(destination.squad),
        el('span', { class: 'case__texte-aide' },
          accord(destination.effectif, 'personne', 'personnes')
          + (actuelle ? ' — squad actuelle' : ''))));
  });

  ouvrirModale({
    titre: 'Déplacer ' + nom,
    declencheur: declencheur,
    classe: 'modale--deplacement',
    contenu: [
      el('p', { class: 'sans-marge texte-doux texte-sm' },
        'Choisissez la squad d’accueil. Le changement reste sur ce poste : '
        + 'rien n’est envoyé sur le réseau.'),
      el('div', { class: 'pile pile--serree', role: 'group',
        ariaLabel: 'Squad d’accueil' }, options)
    ],
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      {
        libelle: 'Déplacer',
        variante: 'principal',
        onClick: (evt, api) => {
          /* La modale se ferme AVANT le déplacement : sa restitution de
             focus ne peut donc pas écraser celle que fait `deplacer`,
             qui vise la carte reconstruite. */
          api.fermer('action');
          if (selection) deplacer(id, selection);
          return false;
        }
      }
    ]
  });
}

/** Active ou désactive le bouton de réinitialisation selon l'état réel. */
function majEtatReinitialisation() {
  if (!refs.reinitialiser) return;
  refs.reinitialiser.disabled = !organisationModifiee();
}

/**
 * Réinitialisation, confirmée explicitement : aucune action destructrice
 * ne part d'un simple clic (SPEC §6.5).
 * @param {Element} [declencheur]
 */
function confirmerReinitialisation(declencheur) {
  ouvrirModale({
    titre: 'Réinitialiser l’organisation ?',
    declencheur: declencheur,
    contenu: el('p', { class: 'sans-marge' },
      'Tous les déplacements effectués sur ce poste seront oubliés et '
      + 'l’organigramme reviendra à celui du fichier de données. '
      + 'Cette action ne peut pas être annulée.'),
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', autofocus: true },
      {
        libelle: 'Réinitialiser',
        variante: 'danger',
        onClick: (evt, api) => {
          api.fermer('action');
          reinitialiser();
          return false;
        }
      }
    ]
  });
}

/** Revient à l'organisation du fichier de données. */
function reinitialiser() {
  stockage.supprimer(CLE_ORGANISATION);
  modele = construireModele(donneesSource);
  for (const pole of modele.poles) for (const squad of pole.squads) ordonner(squad);
  construireIndex();

  if (ficheOuverte && !index.has(ficheOuverte)) fermerFiche(false);

  if (termes.length > 0) appliquerRecherche();
  else rendreArbre();

  rendreReperes();
  majEtatReinitialisation();
  rafraichirFiche();

  toast('Organigramme rétabli tel qu’il figure dans les données.', 'info');

  /* Le bouton de réinitialisation vient d'être désactivé : il ne peut plus
     recevoir le focus. On le rend au champ de recherche, qui est le
     premier contrôle de la barre d'outils. */
  if (refs.recherche) refs.recherche.focus();
}

/** Retire la marque de survol de toutes les zones de dépôt. */
function nettoyerSurvol() {
  if (!racineArbre) return;
  for (const zone of racineArbre.querySelectorAll('[data-survol]')) {
    zone.removeAttribute('data-survol');
  }
}

/** Termine un glissement, quelle qu'en soit l'issue. */
function finirGlissement() {
  glissement = null;
  nettoyerSurvol();
  if (!racineArbre) return;
  racineArbre.removeAttribute('data-glissement');
  for (const ligne of racineArbre.querySelectorAll('[data-glisse]')) {
    ligne.removeAttribute('data-glisse');
  }
}

/* -------------------------------------------------------------------------
   12. Réglages : périmètre, densité, zoom
   ------------------------------------------------------------------------- */

/** Écrit le périmètre et la fiche ouverte dans le hash de l'URL. */
function majUrl() {
  etatUrl.ecrire({ pole: vue, personne: ficheOuverte });
}

/** Applique un périmètre, met à jour les puces, l'arbre et l'URL. */
function definirVue(code, avecUrl) {
  vue = Object.prototype.hasOwnProperty.call(PAGE_DE_POLE, code) ? code : SERVICE;

  if (refs.vues) {
    for (const puce of refs.vues.querySelectorAll('[data-vue]')) {
      puce.setAttribute('aria-pressed', puce.dataset.vue === vue ? 'true' : 'false');
    }
  }
  initNav(PAGE_DE_POLE[vue]);

  /* Une fiche ouverte sur une personne désormais hors périmètre n'a plus
     de carte de retour dans l'arbre : on la referme sans voler le focus. */
  rendreArbre();
  if (ficheOuverte && !rendus.has(ficheOuverte)) fermerFiche(false);
  if (avecUrl !== false) majUrl();
}

/** Applique une densité d'affichage et la mémorise. */
function definirDensite(valeur) {
  densite = DENSITES.includes(valeur) ? valeur : 'normale';
  if (racineArbre) racineArbre.dataset.densite = densite;
  for (const radio of refs.densites) radio.checked = (radio.value === densite);
  enregistrerAffichage();
}

/** Applique un facteur de zoom et le mémorise. */
function definirZoom(valeur) {
  const nombre = Number(valeur);
  zoom = Number.isFinite(nombre)
    ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(nombre)))
    : ZOOM_DEFAUT;

  if (racineArbre) racineArbre.style.setProperty('--org-echelle', String(zoom / 100));
  if (refs.zoom) refs.zoom.value = String(zoom);
  if (refs.zoomValeur) refs.zoomValeur.textContent = zoom + ' %';
  enregistrerAffichage();
}

/** Mémorise densité et zoom. */
function enregistrerAffichage() {
  stockage.ecrire(CLE_AFFICHAGE, { version: VERSION_ETAT, densite: densite, zoom: zoom });
}

/** Relit densité et zoom, en refusant toute valeur hors contrat. */
function lireAffichage() {
  const brut = stockage.lire(CLE_AFFICHAGE, null);
  if (!brut || typeof brut !== 'object' || brut.version !== VERSION_ETAT) return;
  if (DENSITES.includes(brut.densite)) densite = brut.densite;
  const nombre = Number(brut.zoom);
  if (Number.isFinite(nombre)) {
    zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(nombre)));
  }
}

/* -------------------------------------------------------------------------
   13. Câblage des contrôles
   ------------------------------------------------------------------------- */

/**
 * Tous les écouteurs de l'arbre sont posés une fois, par délégation, sur
 * un conteneur qui ne change jamais. Les sélecteurs sont des littéraux :
 * aucun n'est construit à partir d'une donnée.
 */
function cablerArbre() {
  const plan = refs.plan;

  deleguer(plan, '[data-personne]', 'click', (evt, cible) => {
    evt.preventDefault();
    ouvrirFiche(cible.dataset.personne, cible);
  });

  deleguer(plan, '[data-deplacer]', 'click', (evt, cible) => {
    evt.preventDefault();
    ouvrirDeplacement(cible.dataset.deplacer, cible);
  });

  deleguer(plan, '[data-plier]', 'click', (evt, cible) => {
    const groupe = groupes.find((g) => g.bouton === cible);
    if (!groupe) return;
    appliquerOuverture(groupe, cible.getAttribute('aria-expanded') !== 'true');
  });

  /* Conventions d'arborescence : Flèche droite déplie, Flèche gauche
     replie. Le bouton reste par ailleurs un bouton ordinaire, actionnable
     par Entrée et Espace. */
  deleguer(plan, '[data-plier]', 'keydown', (evt, cible) => {
    if (evt.key !== 'ArrowRight' && evt.key !== 'ArrowLeft') return;
    const groupe = groupes.find((g) => g.bouton === cible);
    if (!groupe) return;
    evt.preventDefault();
    appliquerOuverture(groupe, evt.key === 'ArrowRight');
  });

  /* --- Glisser-déposer ------------------------------------------------- */

  deleguer(plan, '[data-glissable]', 'dragstart', (evt, cible) => {
    const id = cible.dataset.glissable;
    if (!index.has(id)) return;
    glissement = id;
    cible.dataset.glisse = 'true';
    if (racineArbre) racineArbre.dataset.glissement = 'true';
    try {
      evt.dataTransfer.effectAllowed = 'move';
      evt.dataTransfer.setData('text/plain', id);
    } catch (_e) { /* certains navigateurs refusent : le glissement marche quand même */ }
  });

  deleguer(plan, '[data-glissable]', 'dragend', () => finirGlissement());

  deleguer(plan, '[data-depot]', 'dragover', (evt, cible) => {
    if (!glissement) return;
    const cibleDepot = depots.get(cible);
    const entree = index.get(glissement);
    if (!cibleDepot || !entree) return;
    if (entree.pole === cibleDepot.pole && entree.squad === cibleDepot.squad) return;

    evt.preventDefault();
    try { evt.dataTransfer.dropEffect = 'move'; } catch (_e) { /* ignoré */ }
    cible.dataset.survol = 'true';
  });

  deleguer(plan, '[data-depot]', 'dragleave', (evt, cible) => {
    if (cible.contains(evt.relatedTarget)) return;
    cible.removeAttribute('data-survol');
  });

  deleguer(plan, '[data-depot]', 'drop', (evt, cible) => {
    if (!glissement) return;
    const cibleDepot = depots.get(cible);
    if (!cibleDepot) return;
    evt.preventDefault();
    const id = glissement;
    finirGlissement();
    deplacer(id, cibleDepot);
  });
}

/** Écouteurs de la fiche latérale. */
function cablerFiche() {
  deleguer(refs.fiche, '[data-fermer-fiche]', 'click', (evt) => {
    evt.preventDefault();
    fermerFiche();
  });

  deleguer(refs.fiche, '[data-personne]', 'click', (evt, cible) => {
    evt.preventDefault();
    ouvrirFiche(cible.dataset.personne);
  });

  deleguer(refs.fiche, '[data-deplacer]', 'click', (evt, cible) => {
    evt.preventDefault();
    ouvrirDeplacement(cible.dataset.deplacer, cible);
  });
}

/** Écouteurs de la barre d'outils, posés une seule fois. */
function cablerOutils() {
  if (outilsCables) return;
  outilsCables = true;

  const chercher = debounce(() => {
    requete = refs.recherche.value;
    appliquerRecherche();
  }, DELAI_RECHERCHE);

  refs.recherche.addEventListener('input', chercher);

  /* Échap vide le champ ; s'il est déjà vide, le comportement natif de
     la croix du champ de recherche s'applique. */
  refs.recherche.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Escape' && evt.key !== 'Esc') return;
    if (refs.recherche.value === '') return;
    evt.preventDefault();
    evt.stopPropagation();
    refs.recherche.value = '';
    chercher.annuler();
    requete = '';
    appliquerRecherche();
  });

  deleguer(refs.vues, '[data-vue]', 'click', (evt, cible) => {
    evt.preventDefault();
    definirVue(cible.dataset.vue);
  });

  refs.toutDeplier.addEventListener('click', () => toutBasculer(true));
  refs.toutReplier.addEventListener('click', () => toutBasculer(false));

  for (const radio of refs.densites) {
    radio.addEventListener('change', () => {
      if (radio.checked) definirDensite(radio.value);
    });
  }

  refs.zoom.addEventListener('input', () => definirZoom(refs.zoom.value));

  refs.reinitialiser.addEventListener('click', (evt) => {
    confirmerReinitialisation(evt.currentTarget);
  });
}

/** Raccourcis globaux : « / » focalise la recherche, Échap ferme la fiche. */
function cablerRaccourcis() {
  document.addEventListener('keydown', (evt) => {
    if (evt.defaultPrevented || evt.ctrlKey || evt.metaKey || evt.altKey) return;

    const actif = document.activeElement;
    const saisie = actif && (actif.tagName === 'INPUT' || actif.tagName === 'TEXTAREA'
      || actif.tagName === 'SELECT' || actif.isContentEditable);

    if (evt.key === '/' && !saisie && !refs.recherche.disabled) {
      evt.preventDefault();
      refs.recherche.focus();
      refs.recherche.select();
      return;
    }

    if ((evt.key === 'Escape' || evt.key === 'Esc')
        && refs.fiche && !refs.fiche.hidden) {
      evt.preventDefault();
      fermerFiche();
    }
  });
}

/** Rend les contrôles utilisables : ils n'existaient que désactivés. */
function activerOutils() {
  const controles = [
    refs.recherche, refs.toutDeplier, refs.toutReplier,
    refs.zoom, refs.reinitialiser
  ];
  for (const controle of controles) if (controle) controle.disabled = false;
  for (const radio of refs.densites) radio.disabled = false;
  if (refs.vues) {
    for (const puce of refs.vues.querySelectorAll('[data-vue]')) puce.disabled = false;
  }
}

/* -------------------------------------------------------------------------
   14. Amorçage
   ------------------------------------------------------------------------- */

/** Résout une fois pour toutes les éléments statiques de la page. */
function resoudreRefs() {
  refs.plan = document.getElementById('zone-arbre');
  refs.reperes = document.getElementById('zone-reperes');
  refs.recherche = document.getElementById('org-recherche');
  refs.resultat = document.getElementById('org-resultat');
  refs.vues = document.getElementById('org-vues');
  refs.toutDeplier = document.getElementById('org-tout-deplier');
  refs.toutReplier = document.getElementById('org-tout-replier');
  refs.zoom = document.getElementById('org-zoom');
  refs.zoomValeur = document.getElementById('org-zoom-valeur');
  refs.reinitialiser = document.getElementById('org-reinitialiser');
  refs.fiche = document.getElementById('org-fiche');
  refs.scene = document.getElementById('org-scene');
  refs.densites = Array.from(
    document.querySelectorAll('input[name="org-densite"]')
  );
}

/**
 * Construit la page à partir des données. Appelé par `avecEtat`, donc
 * uniquement quand le chargement a réussi et que le contenu n'est pas
 * vide : les états de chargement, d'erreur et de vacuité sont à sa charge.
 *
 * @param {object} donnees
 */
function rendre(donnees) {
  donneesSource = verifierForme(donnees, {
    service: 'chaine?',
    direction: 'objet?',
    poles: {
      type: 'tableau',
      elements: { pole: 'chaine', squads: 'tableau' }
    }
  }, 'organigramme.json');

  modele = construireModele(donneesSource);
  for (const pole of modele.poles) for (const squad of pole.squads) ordonner(squad);

  const rejoue = appliquerOrganisationEnregistree();
  construireIndex();

  const etat = etatUrl.lire();
  vue = (typeof etat.pole === 'string'
    && Object.prototype.hasOwnProperty.call(PAGE_DE_POLE, etat.pole))
    ? etat.pole
    : SERVICE;

  if (refs.vues) {
    for (const puce of refs.vues.querySelectorAll('[data-vue]')) {
      puce.setAttribute('aria-pressed', puce.dataset.vue === vue ? 'true' : 'false');
    }
  }
  initNav(PAGE_DE_POLE[vue]);

  rendreReperes();
  rendreArbre();

  activerOutils();
  definirDensite(densite);
  definirZoom(zoom);
  majEtatReinitialisation();
  cablerOutils();

  if (rejoue) {
    toast('Une réorganisation enregistrée sur ce poste a été rétablie.', 'info');
  }

  /* Fiche partagée par l'URL : elle s'ouvre, mais sans voler le focus au
     chargement de la page. */
  const demandee = typeof etat.personne === 'string' ? etat.personne : null;
  if (demandee && index.has(demandee) && rendus.has(demandee)) {
    const bouton = rendus.get(demandee);
    ouvrirFiche(demandee, bouton);
    if (bouton && bouton.isConnected) bouton.focus();
  } else {
    majUrl();
  }
}

/** Point d'entrée. */
function demarrer() {
  initTheme();
  initNav();
  resoudreRefs();

  if (!refs.plan) return;

  lireAffichage();
  cablerArbre();
  cablerFiche();
  cablerRaccourcis();

  /* Le périmètre voyage dans le hash : un lien collé, un retour arrière
     ou un lien depuis un espace de pôle doivent tous être honorés. */
  etatUrl.ecouter((etat) => {
    if (!modele) return;
    const code = (typeof etat.pole === 'string'
      && Object.prototype.hasOwnProperty.call(PAGE_DE_POLE, etat.pole))
      ? etat.pole
      : SERVICE;
    if (code !== vue) definirVue(code, false);

    const demandee = typeof etat.personne === 'string' ? etat.personne : null;
    if (demandee && index.has(demandee)) {
      if (demandee !== ficheOuverte) ouvrirFiche(demandee);
    } else if (ficheOuverte) {
      fermerFiche(false);
    }
  });

  avecEtat(refs.plan, () => chargerDonnees('organigramme'), rendre, {
    squelette: 4,
    texteChargement: 'Chargement de l’organigramme du service…',
    titreErreur: 'L’organigramme n’a pas pu être chargé',
    titreVide: 'Aucune équipe déclarée',
    texteVide: 'Le fichier organigramme.json ne décrit aucun pôle. '
      + 'Rien n’est affiché : la page ne devine pas de structure.',
    estVide: (donnees) => !donnees || !Array.isArray(donnees.poles)
      || donnees.poles.length === 0
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', demarrer, { once: true });
} else {
  demarrer();
}
