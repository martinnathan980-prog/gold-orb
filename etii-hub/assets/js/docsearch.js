/* =========================================================================
   ETII Hub — Recherche documentaire (SPEC.md §4.6)

   La page centrale du portail. Tout le travail lourd est déjà fait
   ailleurs : `search.js` indexe et classe, `ui.js` fabrique les nœuds,
   `data.js` charge et gère les états. Ce module ne fait que quatre choses :

     1. construire l'index UNE fois, au chargement ;
     2. proposer des points d'entrée évidents tant que rien n'est demandé —
        par type, par pôle, ou par date de mise à jour ;
     3. traduire l'état (requête + filtres + tri) en résultats, puis en DOM ;
     4. maintenir cet état synchronisé avec l'URL, le clavier et le
        stockage local.

   Ce que la page raconte, dans l'ordre :
     « Que recherchez-vous ? »  — la question, une barre large, trois menus.
     « Par où commencer ? »     — les chiffres du fonds, puis trois façons
                                  d'entrer dedans sans rien taper.
     Dès la deuxième lettre     — des propositions sous le champ.
     Dès qu'il y a un résultat  — une grille de cartes qui montrent
                                  POURQUOI elles sortent.

   Invariants tenus ici :
   - aucun `innerHTML`, aucun `onclick=` : tout passe par el()/svg()/
     frag()/monter() et par la délégation d'événements de ui.js ;
   - aucun appel réseau autre que le chargement de assets/data/documents.json ;
   - RIEN n'est inventé : un champ vide s'écrit « à renseigner », jamais une
     valeur plausible. Tous les chiffres affichés sont comptés sur le JSON ;
   - l'index n'est jamais reconstruit à la frappe ;
   - la grille n'est jamais reconstruite non plus : les cartes sont
     conservées et seulement réordonnées, seul le surlignage est réécrit ;
   - un seul gestionnaire par conteneur, jamais un par carte ;
   - les cartes de résultat ne sont PAS des `role="option"` : elles portent
     des boutons et des liens, ce qu'ARIA interdit dans une option ;
   - tout bouton qui disparaît en se déclenchant rend le focus à un
     élément vivant — jamais à <body>.
   ========================================================================= */

import {
  el, svg, frag, monter, vider, surlignerVers, deleguer,
  ouvrirModale, toast, annoncer, copierTexte,
  debounce, etatUrl, stockage, initTheme, initNav
} from './ui.js';

import { creerIndex, rechercher, surligner, suggerer } from './search.js';

/* -------------------------------------------------------------------------
   0. Accès aux données

   `data.js` est le point d'entrée prévu par la SPEC (§3) et c'est lui que
   l'on utilise. Il est toutefois importé DYNAMIQUEMENT, sous try/catch :
   un module ES qui ne se lie pas (un export manquant, par exemple) fait
   échouer tout le graphe d'import, et la page entière resterait blanche.
   Un repli local, strictement équivalent en comportement et en balisage,
   garantit que la recherche documentaire fonctionne quoi qu'il arrive.
   Le socle n'est pas modifié.
   ------------------------------------------------------------------------- */

/** Dossier des données, résolu depuis l'URL de ce module (comme data.js). */
const DOSSIER_DONNEES = new URL('../data/', import.meta.url);

/** Délai maximal de chargement, en millisecondes. */
const DELAI_CHARGEMENT = 8000;

let chargerDonnees = null;
let avecEtat = null;

try {
  const moduleDonnees = await import('./data.js');
  if (typeof moduleDonnees.avecEtat === 'function'
      && typeof moduleDonnees.chargerDonnees === 'function') {
    avecEtat = moduleDonnees.avecEtat;
    chargerDonnees = moduleDonnees.chargerDonnees;
  }
} catch (cause) {
  console.warn('[docsearch] data.js indisponible, repli local utilisé.', cause);
}

if (!avecEtat) {
  avecEtat = avecEtatLocal;
  chargerDonnees = chargerDonneesLocal;
}

/**
 * Repli de `chargerDonnees` : un seul fetch, local, avec délai maximal et
 * messages d'erreur en français.
 *
 * @param {string} nom nom du fichier, sans chemin ni extension
 * @returns {Promise<object>}
 */
async function chargerDonneesLocal(nom) {
  const chemin = 'assets/data/' + nom + '.json';
  const controleur = typeof AbortController === 'function' ? new AbortController() : null;
  let expire = false;
  const minuteur = controleur
    ? setTimeout(() => { expire = true; controleur.abort(); }, DELAI_CHARGEMENT)
    : null;

  let reponse;
  try {
    reponse = await fetch(new URL(nom + '.json', DOSSIER_DONNEES).href, {
      signal: controleur ? controleur.signal : undefined,
      headers: { Accept: 'application/json' }
    });
  } catch (cause) {
    if (expire) {
      throw new Error('Le chargement de ' + chemin + ' a dépassé le délai imparti.');
    }
    if (typeof location !== 'undefined' && location.protocol === 'file:') {
      throw new Error(
        'Le navigateur bloque la lecture de ' + chemin + ' parce que la page '
        + 'est ouverte directement depuis le disque (file://). Servez le '
        + 'dossier localement, puis rouvrez la page via http://.'
      );
    }
    throw new Error('Impossible de charger ' + chemin + ' : le fichier n’a pas pu être atteint.');
  } finally {
    if (minuteur !== null) clearTimeout(minuteur);
  }

  if (!reponse.ok) {
    throw new Error('Le serveur a refusé le fichier ' + chemin
      + ' (erreur HTTP ' + reponse.status + ').');
  }

  const texte = await reponse.text();
  if (texte.trim() === '') {
    throw new Error('Le fichier ' + chemin + ' est vide : il ne contient aucune donnée.');
  }

  let donnees;
  try {
    donnees = JSON.parse(texte);
  } catch (_cause) {
    throw new Error('Le fichier ' + chemin + ' est illisible : ce n’est pas du JSON valide.');
  }
  if (!donnees || typeof donnees !== 'object') {
    throw new Error('Le fichier ' + chemin + ' ne contient pas un objet JSON.');
  }
  return donnees;
}

/**
 * Repli de `avecEtat` : même contrat, même balisage d'état que data.js —
 * squelette pendant l'attente, bloc `.etat-vide` en cas d'erreur, bouton
 * « Réessayer » qui relance réellement le chargement.
 *
 * @param {Element} cible
 * @param {Function} source fabrique de promesse
 * @param {Function} rendu  (donnees, cible) => void
 * @param {object} [options]
 * @returns {Promise<{etat:string}>} ne rejette jamais
 */
async function avecEtatLocal(cible, source, rendu, options) {
  const reglages = options || {};

  async function executer() {
    vider(cible);
    cible.setAttribute('aria-busy', 'true');
    if (typeof reglages.squelette === 'function') reglages.squelette(cible);
    cible.append(el('p', {
      class: 'visuellement-cache',
      role: 'status'
    }, reglages.texteChargement || 'Chargement des données en cours…'));

    let resultat;
    try {
      const donnees = await source();
      vider(cible);

      const vide = typeof reglages.estVide === 'function'
        ? reglages.estVide(donnees) === true
        : (donnees === null || donnees === undefined);

      if (vide) {
        monter(cible, el('div', { class: 'etat-vide etat-vide--encadre' },
          el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '∅'),
          el('p', { class: 'etat-vide__titre' },
            reglages.titreVide || 'Aucune donnée à afficher'),
          el('p', { class: 'etat-vide__texte' },
            reglages.texteVide || 'Cette section ne contient encore rien.')));
        resultat = { etat: 'vide', donnees };
      } else {
        rendu(donnees, cible);
        resultat = { etat: 'succes', donnees };
      }
    } catch (cause) {
      const message = (cause && cause.message)
        ? cause.message
        : 'Une erreur inattendue est survenue pendant le chargement des données.';
      console.error('[docsearch] ' + message, cause);

      const bouton = el('button', {
        type: 'button',
        class: 'bouton bouton--secondaire',
        onClick: () => { bouton.disabled = true; executer(); }
      }, 'Réessayer');

      monter(cible, el('div', {
        class: 'etat-vide etat-vide--encadre etat-vide--erreur',
        role: 'alert'
      },
      el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '!'),
      el('p', { class: 'etat-vide__titre' },
        reglages.titreErreur || 'Données indisponibles'),
      el('p', { class: 'etat-vide__texte' }, message),
      el('div', { class: 'etat-vide__actions' }, bouton)));

      resultat = { etat: 'erreur', erreur: cause };
    }
    cible.setAttribute('aria-busy', 'false');
    return resultat;
  }

  return executer();
}

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/*
   Pondération de l'index (SPEC §4.6 et §5). Le champ de poids le plus
   fort fait office de « titre » pour le moteur : c'est lui qui porte les
   bonus « la requête commence le titre » et « la requête est le titre ».

   Le champ `pole` est délibérément ABSENT de cet index. Les trois codes
   ETIIA / ETIIE / ETIII sont à une seule substitution les uns des autres :
   indexés, la tolérance aux fautes de frappe (Levenshtein ≤ 1 sur 4 à 7
   caractères, SPEC §5) ferait remonter les documents d'un pôle quand on
   tape le code d'un autre. Le pôle se choisit donc au menu déroulant ou à
   la tuile d'accueil, qui sont exacts, et se lit sur la carte — jamais au
   petit bonheur du classement.
*/
const CHAMPS_INDEXES = [
  { nom: 'titre',       poids: 10 },  // fort
  { nom: 'reference',   poids: 5 },   // moyen
  { nom: 'motsCles',    poids: 5 },   // moyen
  { nom: 'metier',      poids: 4 },   // moyen
  { nom: 'type',        poids: 4 },   // moyen
  { nom: 'porteur',     poids: 2 },   // faible
  { nom: 'perimetre',   poids: 2 },   // faible
  { nom: 'description', poids: 1 }    // faible
];

/*
   Nom lisible de chaque champ indexé. Sert à écrire, sous une carte, POURQUOI
   elle sort : « Correspond dans le titre, les mots-clés ». L'information
   vient de `champsTouches`, renvoyé par le moteur — elle n'est jamais devinée.
*/
const NOMS_CHAMPS = {
  titre: 'le titre',
  reference: 'la référence',
  motsCles: 'les mots-clés',
  metier: 'le métier',
  type: 'le type',
  porteur: 'le porteur',
  perimetre: 'le périmètre',
  description: 'la description'
};

/*
   Les trois menus déroulants de la barre. Ce sont de vrais <select>
   étiquetés, à valeur unique : « Tous les métiers » est la valeur vide.
   Ils se combinent entre eux (ET) et avec la requête.

   `champ` peut désigner une chaîne ou un TABLEAU dans le document : un
   document relève parfois de deux pôles, exactement comme il relève
   parfois de deux métiers. `valeursDoc()` normalise les deux formes, et
   tout le reste de la mécanique — filtrage, jetons, hash, « Tout
   effacer » — est écrit une fois pour les trois dimensions.

   `documents.json` ne déclare pas de clé « porteurs » : `preparerCorpus()`
   déduit alors les valeurs du corpus, comme pour toute source absente.
*/
const DIMENSIONS = [
  { cle: 'metier',  champ: 'metier',  libelle: 'Métier',  source: 'metiers',
    id: 'ds-metier',  tous: 'Tous les métiers' },
  { cle: 'porteur', champ: 'porteur', libelle: 'Porteur', source: 'porteurs',
    id: 'ds-porteur', tous: 'Tous les porteurs' },
  { cle: 'pole',    champ: 'pole',    libelle: 'Pôle',    source: 'poles',
    id: 'ds-pole',    tous: 'Tous les pôles' }
];

/** Raccourci vers la dimension « pôle », affichée sur chaque carte. */
const DIMENSION_POLE = DIMENSIONS.find((dimension) => dimension.cle === 'pole');

/** Raccourci vers la dimension « métier », multivaluée comme le pôle. */
const DIMENSION_METIER = DIMENSIONS.find((dimension) => dimension.cle === 'metier');

/** Libellé de la dimension « type », filtrée par les tuiles d'accueil. */
const LIBELLE_TYPE = 'Type';

/** Les trois tris proposés. `pertinence` est l'ordre rendu par le moteur. */
const TRIS = [
  { cle: 'pertinence', libelle: 'Pertinence' },
  { cle: 'maj',        libelle: 'Mise à jour' },
  { cle: 'titre',      libelle: 'Titre (A → Z)' }
];

/** Clés de tri reconnues, pour valider ce qui arrive de l'URL. */
const TRIS_CONNUS = new Set(TRIS.map((tri) => tri.cle));

/** Mention unique d'un champ déclaré mais vide. Jamais une valeur plausible. */
const A_RENSEIGNER = 'à renseigner';

/** Anti-rebond de la recherche : court, sous le seuil de perception. */
const DELAI_FRAPPE = 120;

/** Anti-rebond de l'écriture dans l'URL : l'historique n'a pas à suivre la frappe. */
const DELAI_URL = 300;

/** Anti-rebond de l'annonce vocale : on n'annonce pas chaque caractère. */
const DELAI_ANNONCE = 700;

/** Durée du retour visuel d'un bouton de copie, en millisecondes. */
const DELAI_RETOUR_COPIE = 1800;

/** Garde-fou d'affichage : au-delà, on rend une page, pas une liste. */
const LIMITE_AFFICHAGE = 120;

/** Nombre de lettres à partir duquel les propositions s'ouvrent. */
const SEUIL_SUGGESTIONS = 2;

/** Propositions de documents, puis de mots-clés, affichées au maximum. */
const MAX_SUGGESTIONS_DOCUMENT = 6;
const MAX_SUGGESTIONS_TERME = 4;

/** Nombre de documents récents montrés sur l'écran d'accueil. */
const NOMBRE_RECENTS = 6;

/** Un mot-clé est « fréquent » à partir de ce nombre de documents. */
const SEUIL_TERME_FREQUENT = 2;

/** Longueur visée de l'extrait de description, et marge avant la correspondance. */
const LONGUEUR_EXTRAIT = 160;
const MARGE_EXTRAIT = 48;

/** Clé de stockage des propositions locales. */
const CLE_PROPOSITIONS = 'docsearch.propositions';

/** Mise en forme des dates, une seule instance réutilisée. */
const FORMAT_DATE = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric', month: 'long', year: 'numeric'
});

/** Mise en forme courte, pour la liste des documents récents. */
const FORMAT_DATE_COURTE = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit', month: '2-digit', year: 'numeric'
});

/* -------------------------------------------------------------------------
   2. Icônes

   Icônes en trait, dessinées ici en SVG inline : aucune police d'icônes,
   aucune requête réseau, et la couleur suit `currentColor`. Elles sont
   décoratives — le libellé qui les accompagne porte seul l'information.
   ------------------------------------------------------------------------- */

/**
 * Coquille commune des icônes : une grille de 24 unités, un trait unique.
 * @param {...Element} formes
 * @returns {SVGElement}
 */
function iconeSvg(...formes) {
  return svg('svg', {
    class: 'ds-icone',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '1.6',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    focusable: 'false',
    'aria-hidden': 'true'
  }, formes);
}

/** Tracé simple. */
function trace(d) {
  return svg('path', { d });
}

/** Engrenage — les outils. */
function iconeEngrenage() {
  return iconeSvg(
    svg('circle', { cx: '12', cy: '12', r: '5.6' }),
    svg('circle', { cx: '12', cy: '12', r: '2.2' }),
    trace('M17.6 12H20.6 M15.96 8.04L18.08 5.92 M12 6.4V3.4 M8.04 8.04L5.92 5.92 '
      + 'M6.4 12H3.4 M8.04 15.96L5.92 18.08 M12 17.6V20.6 M15.96 15.96L18.08 18.08'));
}

/** Fiche écrite — la documentation technique. */
function iconeFiche() {
  return iconeSvg(
    trace('M13.5 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9'
      + 'A1.5 1.5 0 0 0 18 19V8z'),
    trace('M13.5 3.5V8H18'),
    trace('M9 12.5h6 M9 16h4'));
}

/** Double flèche — les processus. */
function iconeFlux() {
  return iconeSvg(
    trace('M4.5 9.5h13 M14.5 6.5l3 3-3 3'),
    trace('M19.5 15.5h-13 M9.5 12.5l-3 3 3 3'));
}

/** Écusson coché — les normes. */
function iconeSceau() {
  return iconeSvg(
    trace('M12 3.2l7 2.6v5.2c0 4.1-2.9 7.1-7 8.5-4.1-1.4-7-4.4-7-8.5V5.8z'),
    trace('M9.1 12.1l2.2 2.2 3.9-4.2'));
}

/** Toque — les formations. */
function iconeToque() {
  return iconeSvg(
    trace('M12 4 21 8.4 12 12.8 3 8.4z'),
    trace('M6.8 10.3v4.3c0 1.7 2.3 3.1 5.2 3.1s5.2-1.4 5.2-3.1v-4.3'),
    trace('M20.4 8.8v5'));
}

/** Loupe — une proposition qui est un mot-clé du fonds. */
function iconeLoupe() {
  return iconeSvg(
    svg('circle', { cx: '10.5', cy: '10.5', r: '6.5' }),
    trace('M15.4 15.4 L20.5 20.5'));
}

/*
   Habillage d'un type documentaire : le libellé au pluriel de sa tuile et
   son icône. Purement décoratif : le sens est toujours porté par le
   libellé, jamais par la seule icône (SPEC §7). Les pastilles de type
   restent en neutres — la seule couleur catégorielle de la page est celle
   des trois pôles.
*/
const TYPES = {
  'Outil':     { libelle: 'Outils',     icone: iconeEngrenage },
  'Technique': { libelle: 'Technique',  icone: iconeFiche },
  'Processus': { libelle: 'Processus',  icone: iconeFlux },
  'Norme':     { libelle: 'Normes',     icone: iconeSceau },
  'Formation': { libelle: 'Formations', icone: iconeToque }
};

/** Habillage d'un type inconnu du tableau ci-dessus. */
function habillageType(type) {
  const connu = TYPES[type];
  if (connu) return connu;
  return { libelle: type || 'Document', icone: iconeFiche };
}

/* -------------------------------------------------------------------------
   3. État de la page
   ------------------------------------------------------------------------- */

/**
 * Fabrique un objet portant une entrée par dimension. Dérivé de
 * DIMENSIONS plutôt qu'écrit à la main : ajouter un menu ne laisse plus la
 * possibilité d'oublier l'une des tables.
 *
 * @param {() => *} fabrique valeur initiale d'une entrée
 * @returns {Object<string, *>}
 */
function parDimension(fabrique) {
  const objet = {};
  for (const dimension of DIMENSIONS) objet[dimension.cle] = fabrique();
  return objet;
}

const etat = {
  /** Texte saisi, tel quel. */
  requete: '',
  /** Valeur choisie dans chaque menu déroulant ('' = « Tous les … »). */
  filtres: parDimension(() => ''),
  /** Type retenu par une tuile d'accueil ('' = aucun). */
  type: '',
  /** Tri courant : 'pertinence' | 'maj' | 'titre'. */
  tri: 'pertinence',
  /** Mode « parcourir tout le fonds », sans requête ni filtre. */
  tout: false,
  /** Index du résultat courant dans la liste affichée, -1 si aucun. */
  actif: -1,
  /** Documents actuellement affichés. */
  affiches: []
};

/** Données dérivées du JSON, remplies une fois au chargement. */
const corpus = {
  documents: [],
  index: null,
  valeurs: parDimension(() => []),
  connues: parDimension(() => new Set()),
  comptes: parDimension(() => new Map()),
  types: [],
  typesConnus: new Set(),
  comptesType: new Map(),
  /** Mots-clés du fonds, du plus porté au moins porté. */
  termes: [],
  /** Documents datés, du plus récemment mis à jour au plus ancien. */
  recents: [],
  /** Date de mise à jour la plus récente du fonds, ou '' si aucune. */
  derniereMaj: ''
};

/** Références DOM construites une fois par rendu de l'interface. */
const refs = {
  champ: null,
  zone: null,
  suggestions: null,
  jetons: null,
  menus: new Map(),          // clé de dimension -> <select>
  accueil: null,
  resultats: null,           // la section entière
  compteur: null,
  tri: null,
  grille: null,
  messages: null,
  propositionsSection: null,
  propositionsListe: null
};

/** Cartes déjà construites : id de document -> fiche réutilisable. */
const fiches = new Map();

/** Carte portant aria-current. Conservée par référence : une carte sortie
    de la grille doit être nettoyée même si elle n'y est plus. */
let carteActive = null;

/** Annule la frappe en attente (posée au démarrage). */
let annulerFrappe = () => {};

/** Mémoïsation du classement : une requête n'est évaluée qu'une fois. */
let cacheRequete = null;
let cacheClassement = null;

/** Champs touchés par la requête courante : id de document -> [noms]. */
let champsTouches = new Map();

/** Signature des jetons affichés, pour ne les rebâtir qu'au besoin. */
let signatureJetons = null;

/** État du panneau de propositions (motif combobox). */
const boite = {
  ouverte: false,
  liste: [],
  actif: -1
};

/** Propositions locales, source de vérité en mémoire. */
let propositions = [];

/** Vrai une fois l'interface de résultats construite. */
let pretARendre = false;

/* -------------------------------------------------------------------------
   4. Petits utilitaires
   ------------------------------------------------------------------------- */

/** Première valeur d'une entrée d'URL (chaîne ou répétition), en chaîne. */
function premiere(valeur) {
  if (Array.isArray(valeur)) return valeur.length ? String(valeur[0]) : '';
  if (valeur === null || valeur === undefined) return '';
  return String(valeur);
}

/** Chaîne non vide, ou '' — jamais `undefined` ni « null » affiché. */
function texteOuVide(valeur) {
  return (typeof valeur === 'string' && valeur.trim() !== '') ? valeur : '';
}

/**
 * Rend une valeur, ou la mention « à renseigner » si le champ est vide.
 * C'est le SEUL endroit qui décide de l'affichage d'un trou : la page ne
 * présente jamais une valeur plausible à la place d'une donnée absente.
 *
 * @param {*} valeur
 * @returns {Element|string}
 */
function valeurOuManquant(valeur) {
  const texte = texteOuVide(valeur);
  if (texte !== '') return texte;
  return el('span', { class: 'champ-manquant' }, A_RENSEIGNER);
}

/** Valeurs d'un document pour une dimension donnée, toujours en tableau. */
function valeursDoc(doc, dimension) {
  const brut = doc[dimension.champ];
  if (Array.isArray(brut)) return brut.filter((v) => typeof v === 'string' && v);
  return (typeof brut === 'string' && brut) ? [brut] : [];
}

/** Y a-t-il au moins un filtre actif (menu ou tuile) ? */
function auMoinsUnFiltre() {
  if (etat.type !== '') return true;
  return DIMENSIONS.some((dimension) => etat.filtres[dimension.cle] !== '');
}

/** La page est-elle sur son écran d'accueil (rien de demandé) ? */
function surAccueil() {
  return etat.requete.trim() === '' && !auMoinsUnFiltre() && !etat.tout;
}

/**
 * Le document satisfait-il les filtres actifs ?
 * ET entre les dimensions ; à l'intérieur d'une dimension multivaluée, il
 * suffit qu'une des valeurs du document corresponde.
 *
 * @param {object} doc
 * @returns {boolean}
 */
function correspondFiltres(doc) {
  if (etat.type !== '' && doc.type !== etat.type) return false;

  for (const dimension of DIMENSIONS) {
    const choisie = etat.filtres[dimension.cle];
    if (choisie === '') continue;
    if (!valeursDoc(doc, dimension).includes(choisie)) return false;
  }
  return true;
}

/**
 * Classement pour la requête courante, calculé au plus une fois par
 * requête. La table des champs touchés est remplie dans la foulée : c'est
 * elle qui permettra d'écrire, sous chaque carte, pourquoi elle sort.
 */
function classement() {
  if (cacheRequete === etat.requete && cacheClassement) return cacheClassement;
  cacheRequete = etat.requete;
  cacheClassement = rechercher(corpus.index, etat.requete);
  champsTouches = new Map();
  for (const resultat of cacheClassement) {
    champsTouches.set(String(resultat.doc.id), resultat.champsTouches || []);
  }
  return cacheClassement;
}

/** Date ISO -> « 2 février 2026 ». Une date illisible est rendue telle quelle. */
function formaterDate(iso, court) {
  if (typeof iso !== 'string' || iso === '') return '';
  const date = new Date(iso + 'T00:00:00');
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return (court ? FORMAT_DATE_COURTE : FORMAT_DATE).format(date);
  } catch (_e) {
    return iso;
  }
}

/** Accord singulier/pluriel sans concaténation hasardeuse. */
function pluriel(nombre, singulier, plurielForme) {
  return nombre > 1 ? plurielForme : singulier;
}

/** « 12 documents », ou « 1 document ». */
function compteDocuments(nombre) {
  return nombre + ' ' + pluriel(nombre, 'document', 'documents');
}

/**
 * Retour visuel d'un bouton d'action : le libellé change quelques
 * instants puis revient de lui-même. Le nœud n'est jamais remplacé, donc
 * le focus clavier ne bouge pas.
 *
 * @param {HTMLElement} bouton
 * @param {string} texte
 */
function retourVisuel(bouton, texte) {
  if (!bouton) return;
  if (bouton.libelleOrigine === undefined) bouton.libelleOrigine = bouton.textContent;
  if (bouton.minuteurRetour) clearTimeout(bouton.minuteurRetour);

  bouton.textContent = texte;
  bouton.minuteurRetour = setTimeout(() => {
    bouton.textContent = bouton.libelleOrigine;
    bouton.minuteurRetour = null;
  }, DELAI_RETOUR_COPIE);
}

/* -------------------------------------------------------------------------
   5. Synchronisation avec l'URL

   Format : #q=harnais&metier=Qualité&porteur=Personne%2008&pole=ETIIA
            &type=Norme&tri=maj
   Écriture en replaceState (etatUrl s'en charge) et anti-rebondie : le
   bouton « Précédent » reste utilisable, l'URL reste partageable.
   ------------------------------------------------------------------------- */

/** Clés que cette page reconnaît dans le fragment d'URL. */
const CLES_URL = ['q', 'type', 'tri', 'tout']
  .concat(DIMENSIONS.map((dimension) => dimension.cle));

/** Lit l'état depuis le hash et le recopie dans `etat`. */
function appliquerUrl(brut) {
  const source = brut || etatUrl.lire();

  etat.requete = typeof source.q === 'string' ? source.q : '';

  const type = premiere(source.type);
  etat.type = corpus.typesConnus.has(type) ? type : '';

  const tri = premiere(source.tri);
  etat.tri = TRIS_CONNUS.has(tri) ? tri : 'pertinence';

  etat.tout = premiere(source.tout) === '1';

  for (const dimension of DIMENSIONS) {
    const valeur = premiere(source[dimension.cle]);
    etat.filtres[dimension.cle] = corpus.connues[dimension.cle].has(valeur) ? valeur : '';
  }
}

const ecrireUrl = debounce(() => {
  // Construit depuis DIMENSIONS : ajouter un menu ne demande rien ici.
  const sortie = {
    q: etat.requete.trim(),
    type: etat.type,
    tri: etat.tri === 'pertinence' ? '' : etat.tri,
    tout: etat.tout ? '1' : ''
  };
  for (const dimension of DIMENSIONS) {
    sortie[dimension.cle] = etat.filtres[dimension.cle];
  }
  etatUrl.ecrire(sortie);
}, DELAI_URL);

/* -------------------------------------------------------------------------
   6. Squelettes de chargement
   ------------------------------------------------------------------------- */

/** Une carte grise, gabarit d'un résultat en cours de chargement. */
function carteSquelette() {
  return el('div', { class: 'carte carte--compacte ds-squelette' },
    el('div', { class: 'squelette-groupe' },
      el('span', { class: 'squelette squelette--ligne squelette--court' }),
      el('span', { class: 'squelette squelette--ligne squelette--titre' })),
    el('div', { class: 'squelette-groupe' },
      el('span', { class: 'squelette squelette--ligne' }),
      el('span', { class: 'squelette squelette--ligne squelette--moyen' })),
    el('span', { class: 'squelette squelette--ligne squelette--court' }));
}

/** Grille de squelettes affichée pendant le chargement du corpus. */
function afficherSquelettes(cible) {
  const grille = el('ul', { class: 'ds-grille', ariaHidden: 'true' });
  for (let i = 0; i < 6; i += 1) grille.append(el('li', {}, carteSquelette()));
  monter(cible, grille);
}

/* -------------------------------------------------------------------------
   7. Préparation du corpus

   Tout ce que la page affichera comme chiffre est compté ICI, sur le JSON,
   une fois pour toutes. Aucune valeur n'est estimée, arrondie ni inventée.
   ------------------------------------------------------------------------- */

/** Prépare corpus, index, valeurs de menus, compteurs et repères. */
function preparerCorpus(donnees) {
  if (!donnees || typeof donnees !== 'object' || !Array.isArray(donnees.documents)) {
    throw new Error(
      'Le fichier assets/data/documents.json est mal formé : la clé '
      + '« documents » devrait contenir un tableau.'
    );
  }

  corpus.documents = donnees.documents.filter(
    (doc) => doc && typeof doc === 'object' && doc.id !== undefined
  );

  // L'index est construit ICI, une fois pour toutes : jamais à la frappe.
  corpus.index = creerIndex(corpus.documents, CHAMPS_INDEXES);

  const facettes = (donnees.facettes && typeof donnees.facettes === 'object')
    ? donnees.facettes
    : {};

  for (const dimension of DIMENSIONS) {
    // Les valeurs déclarées font foi ; à défaut, on les déduit du corpus.
    const declarees = Array.isArray(facettes[dimension.source])
      ? facettes[dimension.source].filter((v) => typeof v === 'string' && v)
      : [];

    const valeurs = declarees.length
      ? declarees
      : Array.from(new Set(corpus.documents.flatMap(
        (doc) => valeursDoc(doc, dimension)))).sort((a, b) => a.localeCompare(b, 'fr'));

    corpus.valeurs[dimension.cle] = valeurs;
    corpus.connues[dimension.cle] = new Set(valeurs);

    // Combien de documents par valeur : le chiffre affiché sur les tuiles.
    const comptes = new Map();
    for (const doc of corpus.documents) {
      for (const valeur of valeursDoc(doc, dimension)) {
        comptes.set(valeur, (comptes.get(valeur) || 0) + 1);
      }
    }
    corpus.comptes[dimension.cle] = comptes;
  }

  const typesDeclares = Array.isArray(facettes.types)
    ? facettes.types.filter((v) => typeof v === 'string' && v)
    : [];

  corpus.types = typesDeclares.length
    ? typesDeclares
    : Array.from(new Set(corpus.documents
      .map((doc) => texteOuVide(doc.type))
      .filter(Boolean))).sort((a, b) => a.localeCompare(b, 'fr'));
  corpus.typesConnus = new Set(corpus.types);

  corpus.comptesType = new Map();
  for (const doc of corpus.documents) {
    const type = texteOuVide(doc.type);
    if (!type) continue;
    corpus.comptesType.set(type, (corpus.comptesType.get(type) || 0) + 1);
  }

  /* Mots-clés du fonds. Ce sont les termes réellement portés par les
     documents, comptés en nombre de documents distincts — rien de deviné,
     rien de pondéré : une liste de fréquences. */
  const frequences = new Map();
  for (const doc of corpus.documents) {
    const mots = Array.isArray(doc.motsCles) ? doc.motsCles : [];
    for (const mot of new Set(mots.filter((m) => typeof m === 'string' && m.trim() !== ''))) {
      frequences.set(mot, (frequences.get(mot) || 0) + 1);
    }
  }
  corpus.termes = Array.from(frequences, ([terme, nombre]) => ({ terme, nombre }))
    .filter((entree) => entree.nombre >= SEUIL_TERME_FREQUENT)
    .sort((a, b) => (b.nombre - a.nombre) || a.terme.localeCompare(b.terme, 'fr'));

  /* Documents datés, du plus récent au plus ancien. Un document sans date
     de mise à jour n'entre pas dans cette liste : on ne lui en invente pas. */
  corpus.recents = corpus.documents
    .filter((doc) => texteOuVide(doc.maj) !== '')
    .slice()
    .sort(comparerParMaj);
  corpus.derniereMaj = corpus.recents.length ? texteOuVide(corpus.recents[0].maj) : '';
}

/* -------------------------------------------------------------------------
   8. Tris

   Chaque comparateur est total et déterministe : jamais d'ex aequo laissé
   à l'ordre d'insertion (SPEC §5).
   ------------------------------------------------------------------------- */

/** Date de mise à jour décroissante, puis titre, puis identifiant. */
function comparerParMaj(a, b) {
  const majA = texteOuVide(a.maj);
  const majB = texteOuVide(b.maj);
  if (majA !== majB) return majA < majB ? 1 : -1;
  return comparerParTitreSeul(a, b);
}

/** Titre alphabétique (français), puis identifiant. */
function comparerParTitreSeul(a, b) {
  const titreA = texteOuVide(a.titre);
  const titreB = texteOuVide(b.titre);
  const ecart = titreA.localeCompare(titreB, 'fr');
  if (ecart !== 0) return ecart;
  return String(a.id) < String(b.id) ? -1 : (String(a.id) > String(b.id) ? 1 : 0);
}

/** Titre, puis date de mise à jour décroissante, puis identifiant. */
function comparerParTitre(a, b) {
  const titreA = texteOuVide(a.titre);
  const titreB = texteOuVide(b.titre);
  const ecart = titreA.localeCompare(titreB, 'fr');
  if (ecart !== 0) return ecart;
  return comparerParMaj(a, b);
}

/** Applique le tri courant à une liste de documents déjà filtrée. */
function ordonner(documents) {
  if (etat.tri === 'maj') return documents.slice().sort(comparerParMaj);
  if (etat.tri === 'titre') return documents.slice().sort(comparerParTitre);
  return documents;     // 'pertinence' : l'ordre rendu par le moteur
}

/* -------------------------------------------------------------------------
   9. Construction de l'interface (une seule fois, après chargement)
   ------------------------------------------------------------------------- */

/**
 * Remplit les trois menus déroulants de la barre et les rend actifs.
 * Le balisage vient de la page : seule la liste d'options dépend du JSON.
 */
function remplirMenus() {
  for (const dimension of DIMENSIONS) {
    const select = refs.menus.get(dimension.cle);
    if (!select) continue;

    // Un « Réessayer » repasse ici : on ne garde que l'option « Tous les … ».
    while (select.options.length > 1) select.remove(1);

    select.append(frag(corpus.valeurs[dimension.cle].map(
      (valeur) => el('option', { value: valeur }, valeur))));

    select.disabled = false;
  }
}

/** Une tuile d'accès : un bouton-carte, un chiffre, un libellé. */
function tuile(dataset, libelle, nombre, ornement, etiquetteAria) {
  return el('li', {},
    el('button', {
      type: 'button',
      class: 'carte carte--compacte carte--cliquable pile pile--serree ds-tuile',
      dataset,
      ariaLabel: etiquetteAria
    },
    ornement,
    el('span', { class: 'ds-tuile__nom' }, libelle),
    el('span', { class: 'ds-tuile__compte' }, compteDocuments(nombre))));
}

/** Les chiffres du fonds, tous comptés sur le JSON. */
function ligneChiffres() {
  const total = corpus.documents.length;
  const chiffre = (nombre, libelle) => el('li', { class: 'ds-chiffre' },
    el('b', {}, String(nombre)), ' ' + libelle);

  const derniere = corpus.derniereMaj
    ? el('li', { class: 'ds-chiffre' },
      'dernière mise à jour le ',
      el('time', { datetime: corpus.derniereMaj }, formaterDate(corpus.derniereMaj)))
    : el('li', { class: 'ds-chiffre' },
      'dernière mise à jour : ', valeurOuManquant(''));

  return el('ul', { class: 'ds-chiffres' },
    chiffre(total, pluriel(total, 'document référencé', 'documents référencés')),
    chiffre(corpus.types.length, pluriel(corpus.types.length, 'type', 'types')),
    chiffre(corpus.valeurs.pole.length, pluriel(corpus.valeurs.pole.length, 'pôle', 'pôles')),
    chiffre(corpus.valeurs.porteur.length,
      pluriel(corpus.valeurs.porteur.length, 'porteur', 'porteurs')),
    derniere);
}

/** Bloc « Parcourir par type » : une tuile par type déclaré. */
function blocTypes() {
  return el('div', { class: 'pile' },
    el('div', { class: 'pile pile--serree' },
      el('h3', { class: 'ds-depart__titre' }, 'Parcourir par type'),
      el('p', { class: 'ds-depart__aide' },
        'À quoi sert le document que vous cherchez ?')),
    el('ul', { class: 'ds-tuiles' }, corpus.types.map((type) => {
      const habillage = habillageType(type);
      const nombre = corpus.comptesType.get(type) || 0;
      return tuile(
        { action: 'filtrer-type', valeur: type },
        habillage.libelle,
        nombre,
        el('span', { class: 'ds-tuile__icone', ariaHidden: 'true' }, habillage.icone()),
        'Voir les documents de type ' + type + ', ' + compteDocuments(nombre));
    })));
}

/** Bloc « Parcourir par pôle » : une tuile par pôle déclaré. */
function blocPoles() {
  return el('div', { class: 'pile' },
    el('div', { class: 'pile pile--serree' },
      el('h3', { class: 'ds-depart__titre' }, 'Parcourir par pôle'),
      el('p', { class: 'ds-depart__aide' },
        'Quelle équipe du service porte ce sujet ?')),
    el('ul', { class: 'ds-tuiles ds-tuiles--poles' }, corpus.valeurs.pole.map((code) => {
      const nombre = corpus.comptes.pole.get(code) || 0;
      return tuile(
        { action: 'filtrer-pole', valeur: code, pole: code },
        code,
        nombre,
        // Un filet dans la couleur du pôle ; le code écrit juste dessous
        // porte seul l'information (SPEC §1bis).
        el('span', { class: 'ds-tuile__filet', ariaHidden: 'true' }),
        'Voir les documents du pôle ' + code + ', ' + compteDocuments(nombre));
    })));
}

/** Bloc « Récemment mis à jour » : les N documents datés les plus récents. */
function blocRecents() {
  const liste = corpus.recents.slice(0, NOMBRE_RECENTS);

  const corps = liste.length === 0
    ? el('p', { class: 'ds-depart__aide' },
      'Aucun document ne porte de date de mise à jour : ', valeurOuManquant(''), '.')
    : el('ul', { class: 'ds-recents' }, liste.map((doc) => {
      const maj = texteOuVide(doc.maj);
      const titre = texteOuVide(doc.titre);
      return el('li', {},
        el('button', {
          type: 'button',
          class: 'ds-recent',
          dataset: { action: 'voir-document', id: String(doc.id) }
        },
        el('span', { class: 'ds-recent__titre' },
          titre !== '' ? titre : valeurOuManquant('')),
        el('time', { class: 'ds-recent__date', datetime: maj },
          formaterDate(maj, true))));
    }));

  const pied = corpus.recents.length > liste.length
    ? el('div', { class: 'rangee rangee--serree' },
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'parcourir-recents' }
      }, 'Tout voir, du plus récent au plus ancien'))
    : null;

  return el('div', { class: 'pile' },
    el('div', { class: 'pile pile--serree' },
      el('h3', { class: 'ds-depart__titre' }, 'Récemment mis à jour'),
      el('p', { class: 'ds-depart__aide' },
        'Ce qui a bougé en dernier dans le fonds.')),
    corps,
    pied);
}

/**
 * Bâtit l'écran d'accueil et la section de résultats, puis les monte dans
 * le conteneur piloté par avecEtat().
 *
 * @param {object} donnees contenu de documents.json
 * @param {Element} cible
 */
function construireInterface(donnees, cible) {
  preparerCorpus(donnees);
  remplirMenus();

  // Un « Réessayer » rebâtit tout : les cartes mises en cache appartiennent
  // à une grille désormais jetée, on repart donc d'un cache vierge.
  fiches.clear();
  carteActive = null;
  cacheRequete = null;
  cacheClassement = null;
  champsTouches = new Map();
  signatureJetons = null;

  /* --- Écran d'accueil : savoir où aller ------------------------------- */

  const total = corpus.documents.length;

  refs.accueil = el('section', {
    class: 'ds-bloc pile pile--lache',
    ariaLabelledby: 'ds-depart-titre'
  },
  el('div', { class: 'pile pile--serree' },
    el('h2', { class: 'separateur-titre', id: 'ds-depart-titre' },
      'Par où commencer ?'),
    ligneChiffres()),
  el('div', { class: 'ds-depart' },
    blocTypes(),
    el('div', { class: 'ds-depart__duo' }, blocPoles(), blocRecents())),
  // Sorties de l'accueil : tout parcourir, ou signaler un document absent.
  // La proposition doit rester atteignable ICI : le seul autre bouton vit
  // dans le bandeau de résultats, qui n'existe pas sur l'écran d'accueil.
  el('div', { class: 'rangee rangee--centree' },
    el('button', {
      type: 'button',
      class: 'bouton bouton--secondaire',
      dataset: { action: 'parcourir-tout' }
    }, 'Parcourir les ' + total + ' documents'),
    el('button', {
      type: 'button',
      class: 'bouton bouton--discret',
      dataset: { action: 'proposer' }
    }, 'Proposer un document')));

  /* --- Résultats : compteur, tri, grille, messages --------------------- */

  refs.compteur = el('h2', { class: 'ds-compteur', id: 'ds-compteur' }, '');

  refs.tri = el('select', {
    class: 'champ__controle',
    id: 'ds-tri',
    name: 'tri'
  }, TRIS.map((tri) => el('option', { value: tri.cle }, tri.libelle)));

  refs.tri.addEventListener('change', () => {
    etat.tri = TRIS_CONNUS.has(refs.tri.value) ? refs.tri.value : 'pertinence';
    rendre();
  });

  const bandeauTri = el('div', { class: 'ds-tri pousse' },
    el('label', { class: 'champ__etiquette ds-tri__etiquette', for: 'ds-tri' },
      'Trier par'),
    el('span', { class: 'champ__select ds-tri__menu' }, refs.tri));

  const proposer = el('button', {
    type: 'button',
    class: 'bouton bouton--discret bouton--compact',
    onClick: (evt) => ouvrirModaleProposition(evt.currentTarget)
  }, 'Proposer un document');

  // Une liste de cartes actionnables, pas un listbox : les options ARIA
  // imposent « Children Presentational: True », ce qui effacerait les
  // boutons « Ouvrir » et « Copier le lien » de l'arbre d'accessibilité.
  refs.grille = el('ul', {
    class: 'ds-grille',
    id: 'ds-resultats',
    role: 'list'
  });

  refs.messages = el('div', {});

  refs.resultats = el('section', {
    class: 'ds-bloc pile',
    ariaLabelledby: 'ds-compteur',
    hidden: true
  },
  el('div', { class: 'rangee rangee--serree' },
    refs.compteur, bandeauTri, proposer),
  el('div', { class: 'separateur', role: 'presentation' }),
  refs.grille,
  refs.messages);

  monter(cible, el('div', { class: 'pile pile--lache' },
    refs.accueil, refs.resultats));

  /* --- Délégations : un gestionnaire par conteneur, jamais par carte --- */

  deleguer(refs.accueil, '[data-action]', 'click', (evt, bouton) => {
    surActionAccueil(bouton);
  });

  deleguer(refs.grille, '[data-action]', 'click', (evt, bouton) => {
    surActionCarte(evt, bouton);
  });

  // Un clic dans une carte (hors bouton) la désigne comme résultat courant :
  // souris et clavier partagent ainsi la même notion de « courant ».
  deleguer(refs.grille, '.ds-carte', 'click', (evt, carte) => {
    if (evt.target.closest('[data-action]')) return;
    const position = etat.affiches.findIndex((doc) => String(doc.id) === carte.dataset.id);
    if (position !== -1) definirActif(position, false);
  });

  // Une fois le focus posé sur une carte, le parcours continue au clavier.
  refs.grille.addEventListener('keydown', surToucheResultats);

  deleguer(refs.messages, '[data-action]', 'click', (evt, bouton) => {
    surActionMessage(evt, bouton);
  });

  pretARendre = true;
}

/* -------------------------------------------------------------------------
   10. Rendu : état -> affichage
   ------------------------------------------------------------------------- */

/** Recalcule tout ce qui dépend de l'état, dans l'ordre le moins coûteux. */
function rendre() {
  if (!pretARendre) return;

  const base = classement();
  const retenus = base
    .filter((resultat) => correspondFiltres(resultat.doc))
    .map((resultat) => resultat.doc);

  // L'accueil ne rend aucune liste : `affiches` doit donc rester vide,
  // sinon ↑/↓ désigneraient des cartes détachées du DOM et Entrée ouvrirait
  // un document que la page n'affiche nulle part.
  const accueil = surAccueil();
  etat.affiches = accueil ? [] : ordonner(retenus);

  majMenus();
  majTri();
  majJetons();

  refs.accueil.hidden = !accueil;
  refs.resultats.hidden = accueil;

  if (accueil) {
    definirActif(-1, false);
    vider(refs.grille);
    vider(refs.messages);
  } else if (etat.affiches.length === 0) {
    afficherAucunResultat();
  } else {
    afficherResultats();
  }

  ecrireUrl();
  annoncerResultats();
}

/** Reporte l'état dans les trois menus déroulants. */
function majMenus() {
  for (const dimension of DIMENSIONS) {
    const select = refs.menus.get(dimension.cle);
    if (!select) continue;
    const valeur = etat.filtres[dimension.cle];
    if (select.value !== valeur) select.value = valeur;
  }
}

/** Reporte l'état dans le menu de tri. */
function majTri() {
  if (refs.tri && refs.tri.value !== etat.tri) refs.tri.value = etat.tri;
}

/** Liste des filtres actifs, sous forme de descripteurs affichables. */
function filtresActifs() {
  const actifs = [];
  if (etat.type !== '') {
    actifs.push({ cle: 'type', libelle: LIBELLE_TYPE, valeur: etat.type });
  }
  for (const dimension of DIMENSIONS) {
    const valeur = etat.filtres[dimension.cle];
    if (valeur !== '') {
      actifs.push({ cle: dimension.cle, libelle: dimension.libelle, valeur });
    }
  }
  return actifs;
}

/** Un jeton retirable : « Pôle : ETIIA × ». */
function jetonFiltre(filtre, compacte) {
  return el('li', {},
    el('button', {
      type: 'button',
      class: compacte ? 'facette facette--compacte' : 'facette',
      dataset: { action: 'retirer-filtre', cle: filtre.cle },
      ariaLabel: 'Retirer le filtre ' + filtre.libelle + ' ' + filtre.valeur
    },
    el('span', { class: 'ds-jeton__cle' }, filtre.libelle + ' :'),
    el('span', {}, filtre.valeur),
    el('span', { ariaHidden: 'true' }, '×')));
}

/**
 * Ligne de jetons sous la barre : ce qui est actif est écrit en toutes
 * lettres, retirable un à un, avec un « Tout effacer » en bout de ligne.
 * La liste n'est rebâtie que lorsqu'elle change réellement : un jeton qui
 * a le focus n'est pas détruit à chaque caractère saisi.
 */
function majJetons() {
  const actifs = filtresActifs();
  const signature = actifs.map((f) => f.cle + '=' + f.valeur).join('&');
  if (signature === signatureJetons) return;
  signatureJetons = signature;

  if (actifs.length === 0) {
    refs.jetons.hidden = true;
    vider(refs.jetons);
    return;
  }

  refs.jetons.hidden = false;
  monter(refs.jetons,
    actifs.map((filtre) => jetonFiltre(filtre, true)),
    el('li', {},
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'tout-effacer' }
      }, 'Tout effacer')));
}

/** Affiche la grille de résultats (réutilisation maximale des cartes). */
function afficherResultats() {
  const total = etat.affiches.length;
  const tronque = total > LIMITE_AFFICHAGE;
  const visibles = tronque ? etat.affiches.slice(0, LIMITE_AFFICHAGE) : etat.affiches;

  const noeuds = visibles.map((doc) => {
    const fiche = obtenirFiche(doc);
    majSurlignage(fiche, etat.requete);
    return fiche.carte;
  });

  // Une seule mutation : les cartes existantes sont déplacées, pas recréées.
  monter(refs.grille, noeuds);
  refs.grille.hidden = false;
  refs.compteur.textContent = texteCompteur(total);

  vider(refs.messages);
  if (tronque) {
    monter(refs.messages, el('p', { class: 'texte-sm texte-doux texte-centre' },
      'Seuls les ' + LIMITE_AFFICHAGE + ' premiers documents sont affichés. '
      + 'Affinez la recherche pour voir les suivants.'));
  }

  definirActif(-1, false);
}

/** Aucun résultat : suggestion, retrait des filtres, proposition. */
function afficherAucunResultat() {
  vider(refs.grille);
  // Une grille vide laisserait une gouttière béante au-dessus du message.
  refs.grille.hidden = true;
  refs.compteur.textContent = texteCompteur(0);
  definirActif(-1, false);

  const bloc = el('div', { class: 'etat-vide etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '∅'),
    el('p', { class: 'etat-vide__titre' }, 'Aucun document ne correspond'),
    el('p', { class: 'etat-vide__texte' }, texteAucunResultat()));

  // « Vouliez-vous dire… » : proposé par le moteur, jamais deviné ici.
  const suggestion = etat.requete.trim() === ''
    ? null
    : suggerer(corpus.index, etat.requete);

  if (suggestion) {
    bloc.append(el('p', { class: 'etat-vide__texte' },
      'Vouliez-vous dire ',
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'appliquer-suggestion', valeur: suggestion }
      }, suggestion),
      ' ?'));
  }

  // Rappel des filtres actifs, retirables un à un.
  const actifs = filtresActifs();
  if (actifs.length) {
    bloc.append(
      el('p', { class: 'texte-sm texte-doux sans-marge' }, 'Filtres actifs :'),
      el('ul', { class: 'facettes' },
        actifs.map((filtre) => jetonFiltre(filtre, true))));
  }

  const actions = el('div', { class: 'etat-vide__actions' });
  if (etat.requete !== '' || auMoinsUnFiltre() || etat.tout) {
    actions.append(el('button', {
      type: 'button',
      class: 'bouton bouton--secondaire',
      dataset: { action: 'tout-effacer' }
    }, 'Tout effacer'));
  }
  actions.append(el('button', {
    type: 'button',
    class: 'bouton bouton--principal',
    dataset: { action: 'proposer' }
  }, 'Proposer un document'));
  bloc.append(actions);

  monter(refs.messages, bloc);
}

/** Phrase du compteur, au-dessus de la grille. */
function texteCompteur(nombre) {
  if (nombre === 0) return 'Aucun document trouvé';
  return nombre + ' ' + pluriel(nombre, 'document trouvé', 'documents trouvés');
}

/** Explication de l'absence de résultat, adaptée à ce qui est actif. */
function texteAucunResultat() {
  const avecRequete = etat.requete.trim() !== '';
  const avecFiltres = auMoinsUnFiltre();

  if (avecRequete && avecFiltres) {
    return 'Aucun document ne répond à la fois à « ' + etat.requete.trim()
      + ' » et aux filtres actifs. Essayez d’en retirer un.';
  }
  if (avecRequete) {
    return 'Aucun document ne correspond à « ' + etat.requete.trim()
      + ' », même en tolérant les fautes de frappe.';
  }
  return 'Aucun document ne correspond aux filtres actifs.';
}

/* -------------------------------------------------------------------------
   11. Propositions à la frappe (motif combobox)

   Le champ garde le focus et reste tapable : c'est `aria-activedescendant`
   qui désigne la proposition courante, comme le veut le motif ARIA
   « combobox + listbox ». Les propositions sont de VRAIES options : elles
   ne contiennent que du texte, aucun contrôle imbriqué — ARIA l'interdit,
   et un bouton à l'intérieur serait de toute façon effacé de l'arbre
   d'accessibilité.
   ------------------------------------------------------------------------- */

/**
 * Calcule les propositions pour une requête : d'abord les documents dont
 * le TITRE correspond, puis les mots-clés fréquents du fonds. Rien n'est
 * inventé : les titres viennent des documents, les mots-clés et leur
 * nombre d'occurrences sont comptés sur le JSON.
 *
 * @param {string} requete
 * @returns {Array<object>}
 */
function calculerPropositions(requete) {
  const texte = requete.trim();
  if (texte.length < SEUIL_SUGGESTIONS || !corpus.index) return [];

  const sorties = [];

  // (a) Documents dont le titre correspond. Le classement du moteur est
  //     déjà calculé pour cette requête : on ne relance rien.
  for (const resultat of classement()) {
    if (sorties.length >= MAX_SUGGESTIONS_DOCUMENT) break;
    const titre = texteOuVide(resultat.doc.titre);
    if (titre === '') continue;
    const segments = surligner(titre, texte);
    if (!segments.some((segment) => segment.correspond)) continue;
    sorties.push({
      genre: 'document',
      id: String(resultat.doc.id),
      texte: titre,
      segments,
      complement: texteOuVide(resultat.doc.type) || 'Document'
    });
  }

  // (b) Mots-clés fréquents du fonds, avec leur nombre de documents.
  let ajoutes = 0;
  for (const entree of corpus.termes) {
    if (ajoutes >= MAX_SUGGESTIONS_TERME) break;
    const segments = surligner(entree.terme, texte);
    if (!segments.some((segment) => segment.correspond)) continue;
    sorties.push({
      genre: 'terme',
      texte: entree.terme,
      segments,
      nombre: entree.nombre
    });
    ajoutes += 1;
  }

  return sorties;
}

/** Recalcule et (r)ouvre le panneau, ou le referme s'il n'y a rien. */
function majPropositions() {
  if (!refs.suggestions) return;
  const liste = calculerPropositions(etat.requete);

  if (liste.length === 0) {
    fermerPropositions();
    return;
  }

  boite.liste = liste;
  boite.actif = -1;
  boite.ouverte = true;

  monter(refs.suggestions, liste.map((proposition, position) => el('li', {
    class: 'ds-suggestion',
    id: 'ds-proposition-' + position,
    role: 'option',
    ariaSelected: 'false',
    dataset: { position: String(position) }
  },
  el('span', { class: 'ds-suggestion__icone', ariaHidden: 'true' },
    proposition.genre === 'terme'
      ? iconeLoupe()
      : habillageType(proposition.complement).icone()),
  el('span', { class: 'ds-suggestion__texte' },
    surlignerVers(proposition.segments)),
  el('span', { class: 'ds-suggestion__genre' },
    proposition.genre === 'terme'
      ? frag(el('span', { class: 'visuellement-cache' }, 'mot-clé du fonds, '),
        compteDocuments(proposition.nombre))
      : proposition.complement))));

  refs.suggestions.hidden = false;
  refs.champ.setAttribute('aria-expanded', 'true');
  refs.champ.removeAttribute('aria-activedescendant');
}

/** Referme le panneau et rend au champ son état de repos. */
function fermerPropositions() {
  if (!refs.suggestions) return;
  boite.ouverte = false;
  boite.liste = [];
  boite.actif = -1;
  refs.suggestions.hidden = true;
  vider(refs.suggestions);
  refs.champ.setAttribute('aria-expanded', 'false');
  refs.champ.removeAttribute('aria-activedescendant');
}

/** Désigne la proposition de rang `position` (-1 : aucune). */
function designerProposition(position) {
  const options = refs.suggestions.children;

  const ancienne = options[boite.actif];
  if (ancienne) ancienne.setAttribute('aria-selected', 'false');

  boite.actif = position;

  const option = options[position];
  if (!option) {
    refs.champ.removeAttribute('aria-activedescendant');
    return;
  }
  option.setAttribute('aria-selected', 'true');
  refs.champ.setAttribute('aria-activedescendant', option.id);
  // 'auto' et non 'smooth' : base.css active le défilement doux au niveau
  // du document, ce qui rendrait le parcours à la flèche pâteux.
  try { option.scrollIntoView({ block: 'nearest', behavior: 'auto' }); }
  catch (_e) { /* moteur sans options : le défaut suffit */ }
}

/** Déplace la désignation, en bouclant aux extrémités. */
function deplacerProposition(pas) {
  const nombre = boite.liste.length;
  if (nombre === 0) return;
  let position = boite.actif + pas;
  if (position < 0) position = nombre - 1;
  if (position >= nombre) position = 0;
  designerProposition(position);
}

/**
 * Ouvre la proposition de rang `position` : un mot-clé devient la requête,
 * un document devient le résultat courant et reçoit le focus réel.
 */
function activerProposition(position) {
  const proposition = boite.liste[position];
  if (!proposition) return;
  fermerPropositions();

  if (proposition.genre === 'terme') {
    definirRequete(proposition.texte);
    refs.champ.focus();
    return;
  }
  allerAuDocument(proposition.id);
}

/* -------------------------------------------------------------------------
   12. Cartes de résultat

   Une carte est construite au plus une fois par document et conservée
   dans `fiches`. À la frappe suivante, seuls les fragments dépendant de la
   requête sont réécrits : la structure, les pastilles et les boutons ne
   bougent pas.
   ------------------------------------------------------------------------- */

/**
 * Fenêtre de description centrée sur la première correspondance. Les
 * bornes sont ramenées sur des espaces pour ne jamais couper un mot.
 *
 * @param {string} texte
 * @param {string} requete
 * @returns {{texte:string, avant:boolean, apres:boolean}}
 */
function extraitPertinent(texte, requete) {
  const entier = { texte, avant: false, apres: false };
  if (texte === '' || requete.trim() === '' || texte.length <= LONGUEUR_EXTRAIT) {
    return entier;
  }

  const segments = surligner(texte, requete);
  let curseur = 0;
  let correspondance = -1;
  for (const segment of segments) {
    if (segment.correspond) { correspondance = curseur; break; }
    curseur += segment.texte.length;
  }
  if (correspondance < 0) correspondance = 0;

  let debut = Math.max(0, correspondance - MARGE_EXTRAIT);
  if (debut > 0) {
    const espace = texte.indexOf(' ', debut);
    if (espace !== -1 && espace < correspondance) debut = espace + 1;
  }

  let fin = Math.min(texte.length, debut + LONGUEUR_EXTRAIT);
  if (fin < texte.length) {
    const espace = texte.lastIndexOf(' ', fin);
    if (espace > correspondance) fin = espace;
  }

  return { texte: texte.slice(debut, fin), avant: debut > 0, apres: fin < texte.length };
}

/** Récupère la fiche d'un document, en la construisant au besoin. */
function obtenirFiche(doc) {
  const id = String(doc.id);
  const existante = fiches.get(id);
  if (existante) return existante;

  const titre = el('h3', { class: 'ds-carte__titre' });
  const reference = el('span', { class: 'badge badge--carre badge--contour' });
  const extrait = el('p', { class: 'ds-carte__extrait' });
  const raison = el('p', { class: 'ds-carte__meta', hidden: true });

  /* Le ou les pôles dont relève le document. Une pastille ÉTIQUETÉE : le
     point teinté est décoratif, c'est « Pôle ETIIA » écrit à côté qui
     porte l'information. La couleur ne signale donc jamais seule le pôle
     (SPEC §1bis), et la carte reste lisible en niveaux de gris. */
  const poles = valeursDoc(doc, DIMENSION_POLE).map(
    (code) => el('li', {},
      el('span', { class: 'badge badge--pole', dataset: { pole: code } },
        el('span', { class: 'pole-point', ariaHidden: 'true' }),
        'Pôle ' + code)));

  /* Les métiers, étiquetés eux aussi : le préfixe reste hors écran, mais
     un lecteur d'écran annonce bien « Métier : Harnais ». */
  const metiers = valeursDoc(doc, DIMENSION_METIER).map(
    (metier) => el('li', {},
      el('span', { class: 'badge badge--contour' },
        el('span', { class: 'visuellement-cache' }, 'Métier : '),
        metier)));

  const lien = texteOuVide(doc.lien);
  const actions = el('div', { class: 'ds-carte__actions' });

  if (lien !== '') {
    actions.append(
      el('a', {
        class: 'bouton bouton--secondaire bouton--compact',
        href: lien,
        target: '_blank',
        rel: 'noopener noreferrer',
        dataset: { action: 'ouvrir' }
      }, 'Ouvrir'),
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'copier-lien' }
      }, 'Copier le lien'));
  } else {
    // Les documents sans lien : une mention claire, aucun bouton mort.
    actions.append(
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'copier-reference' }
      }, 'Copier la référence'));
  }

  const sansLien = lien !== '' ? null : el('p', { class: 'ds-sans-lien' },
    el('span', { ariaHidden: 'true' }, '✉'),
    'Lien : ', valeurOuManquant(''));

  const maj = texteOuVide(doc.maj);
  const porteur = texteOuVide(doc.porteur);
  const type = texteOuVide(doc.type);

  // Un élément de liste, focalisable par programme seulement : le parcours
  // ↑/↓ y déplace un tabindex glissant, sans imposer d'arrêt de tabulation
  // supplémentaire. Aucun aria-label global : il masquerait l'extrait, les
  // métiers et la date de mise à jour.
  const carte = el('li', {
    class: 'carte carte--compacte ds-carte',
    id: 'ds-document-' + id,
    dataset: { id },
    tabIndex: -1
  },
  el('div', { class: 'carte__meta' },
    el('span', { class: 'badge badge--neutre' },
      el('span', { class: 'visuellement-cache' }, 'Type : '),
      valeurOuManquant(type)),
    reference),
  titre,
  extrait,
  raison,
  el('ul', { class: 'facettes' }, poles, metiers),
  el('div', { class: 'carte__pied ds-carte__pied' },
    el('p', { class: 'ds-carte__meta' },
      el('span', {}, 'Porteur : ', valeurOuManquant(porteur)),
      maj !== ''
        ? el('span', {}, 'Mis à jour le ',
          el('time', { datetime: maj }, formaterDate(maj)))
        : el('span', {}, 'Mise à jour : ', valeurOuManquant(''))),
    sansLien,
    actions));

  const fiche = { doc, carte, titre, reference, extrait, raison, requete: null };
  fiches.set(id, fiche);
  return fiche;
}

/**
 * Réécrit les seuls fragments dépendant de la requête : le titre surligné,
 * la référence surlignée, l'extrait de description le plus pertinent, et
 * la ligne qui dit POURQUOI la carte sort. Si la requête n'a pas changé
 * depuis le dernier rendu de cette carte, il n'y a rien à faire.
 */
function majSurlignage(fiche, requete) {
  if (fiche.requete === requete) return;
  fiche.requete = requete;

  const doc = fiche.doc;
  const titre = texteOuVide(doc.titre);
  const reference = texteOuVide(doc.reference);
  const description = texteOuVide(doc.description);
  const vide = requete.trim() === '';

  if (titre !== '') {
    if (vide) fiche.titre.textContent = titre;
    else monter(fiche.titre, surlignerVers(surligner(titre, requete)));
  } else {
    monter(fiche.titre, valeurOuManquant(''));
  }

  if (reference !== '') {
    if (vide) fiche.reference.textContent = reference;
    else monter(fiche.reference, surlignerVers(surligner(reference, requete)));
  } else {
    monter(fiche.reference, valeurOuManquant(''));
  }

  if (description === '') {
    monter(fiche.extrait, valeurOuManquant(''));
  } else if (vide) {
    // Cas le plus fréquent au repos : aucun découpage, aucun nœud créé.
    fiche.extrait.textContent = description;
  } else {
    const morceau = extraitPertinent(description, requete);
    monter(fiche.extrait,
      morceau.avant ? '… ' : null,
      surlignerVers(surligner(morceau.texte, requete)),
      morceau.apres ? ' …' : null);
  }

  // Pourquoi cette carte sort : les champs que le moteur a réellement
  // touchés pour cette requête. Jamais une explication reconstituée ici.
  const touches = vide ? [] : (champsTouches.get(String(doc.id)) || []);
  const noms = touches.map((champ) => NOMS_CHAMPS[champ]).filter(Boolean);
  if (noms.length === 0) {
    fiche.raison.hidden = true;
    vider(fiche.raison);
  } else {
    fiche.raison.hidden = false;
    monter(fiche.raison, el('span', {}, 'Correspond dans ' + noms.join(', ')));
  }
}

/* -------------------------------------------------------------------------
   13. Actions
   ------------------------------------------------------------------------- */

/** Clic sur un bouton de l'écran d'accueil. */
function surActionAccueil(bouton) {
  const action = bouton.dataset.action;

  if (action === 'filtrer-type') { choisirType(bouton.dataset.valeur); return; }
  if (action === 'filtrer-pole') { choisirPole(bouton.dataset.valeur); return; }
  if (action === 'voir-document') { allerAuDocument(bouton.dataset.id); return; }
  if (action === 'parcourir-tout') { parcourirTout('pertinence'); return; }
  if (action === 'parcourir-recents') { parcourirTout('maj'); return; }
  if (action === 'proposer') ouvrirModaleProposition(bouton);
}

/** Clic sur un bouton d'une carte de résultat. */
function surActionCarte(evt, bouton) {
  const carte = bouton.closest('[data-id]');
  if (!carte) return;
  const doc = corpus.documents.find((d) => String(d.id) === carte.dataset.id);
  if (!doc) return;

  const action = bouton.dataset.action;

  if (action === 'copier-lien') {
    evt.preventDefault();
    copier(doc.lien, 'Lien copié dans le presse-papiers.', bouton, 'Lien copié');
    return;
  }
  if (action === 'copier-reference') {
    evt.preventDefault();
    copier(doc.reference, 'Référence copiée dans le presse-papiers.',
      bouton, 'Référence copiée');
  }
  // « Ouvrir » est une vraie ancre : on ne lui coupe pas son comportement.
}

/** Clic sur un bouton de la zone de messages (aucun résultat, troncature). */
function surActionMessage(evt, bouton) {
  const action = bouton.dataset.action;

  if (action === 'appliquer-suggestion') {
    definirRequete(bouton.dataset.valeur);
    // Le bloc « aucun résultat » vient d'être remplacé : le bouton cliqué
    // n'existe plus, le focus doit être replacé explicitement.
    refs.champ.focus();
    return;
  }
  if (action === 'retirer-filtre') { retirerFiltre(bouton.dataset.cle); return; }
  if (action === 'tout-effacer') { toutEffacer(); return; }
  if (action === 'proposer') ouvrirModaleProposition(bouton);
}

/**
 * Copie un texte, avec retour visuel explicite dans les deux cas : une
 * notification, et le libellé du bouton lui-même.
 *
 * @param {string} texte
 * @param {string} messageSucces
 * @param {HTMLElement} [bouton]
 * @param {string} [libelleSucces]
 */
function copier(texte, messageSucces, bouton, libelleSucces) {
  const valeur = texteOuVide(texte).trim();
  if (valeur === '') {
    toast('Rien à copier pour ce document.', 'alerte');
    return;
  }
  copierTexte(valeur).then((ok) => {
    if (ok) {
      toast(messageSucces, 'succes');
      if (libelleSucces) retourVisuel(bouton, libelleSucces);
    } else {
      toast('La copie a échoué. Sélectionnez le texte puis copiez-le manuellement.',
        'critique');
    }
  });
}

/** Une tuile de type a été choisie : elle filtre le fonds sur ce type. */
function choisirType(valeur) {
  if (!corpus.typesConnus.has(valeur)) return;
  etat.type = valeur;
  etat.tout = false;
  rendre();
  // L'accueil disparaît : la tuile cliquée n'est plus affichée, donc plus
  // focalisable. Le focus revient au champ, jamais à <body>.
  refs.champ.focus();
}

/** Une tuile de pôle a été choisie : elle alimente le menu « Pôle ». */
function choisirPole(valeur) {
  if (!DIMENSION_POLE || !corpus.connues.pole.has(valeur)) return;
  etat.filtres.pole = valeur;
  etat.tout = false;
  rendre();
  refs.champ.focus();
}

/**
 * Parcourir tout le fonds, avec un tri donné. Le bouton cliqué vient
 * d'être masqué avec l'accueil : le focus est replacé explicitement.
 *
 * @param {string} tri
 */
function parcourirTout(tri) {
  etat.tout = true;
  etat.tri = TRIS_CONNUS.has(tri) ? tri : 'pertinence';
  rendre();
  refs.champ.focus();
}

/**
 * Amène la page sur un document précis : sa requête devient son titre, et
 * sa carte devient le résultat courant, avec le focus réel dessus. Si la
 * carte n'a pas pu être construite, le focus revient au champ — jamais à
 * <body>.
 *
 * @param {string} id
 */
function allerAuDocument(id) {
  const doc = corpus.documents.find((d) => String(d.id) === String(id));
  if (!doc) { refs.champ.focus(); return; }

  annulerFrappe();
  etat.requete = texteOuVide(doc.titre);
  refs.champ.value = etat.requete;
  etat.type = '';
  // Un document dont le titre est vide laisserait une requête vide : on
  // bascule alors en « parcourir tout », sinon la page retomberait sur son
  // écran de départ et le document ne serait affiché nulle part.
  etat.tout = etat.requete.trim() === '';
  for (const dimension of DIMENSIONS) etat.filtres[dimension.cle] = '';
  rendre();

  const position = etat.affiches.findIndex((d) => String(d.id) === String(id));
  if (position !== -1) definirActif(position, true, true);
  else refs.champ.focus();
}

/**
 * Retire un filtre, puis replace le focus sur un élément vivant : le menu
 * déroulant correspondant s'il existe, le champ de recherche sinon.
 *
 * @param {string} cle 'type', ou la clé d'une dimension
 */
function retirerFiltre(cle) {
  if (cle === 'type') {
    if (etat.type === '') return;
    etat.type = '';
    rendre();
    refs.champ.focus();
    return;
  }

  if (!Object.prototype.hasOwnProperty.call(etat.filtres, cle)) return;
  if (etat.filtres[cle] === '') return;
  etat.filtres[cle] = '';
  rendre();

  const select = refs.menus.get(cle);
  if (select && select.isConnected && !select.disabled) select.focus();
  else refs.champ.focus();
}

/** Remet la page à zéro : requête, menus, tri, accueil. */
function toutEffacer() {
  annulerFrappe();
  fermerPropositions();
  etat.requete = '';
  refs.champ.value = '';
  etat.type = '';
  etat.tout = false;
  etat.tri = 'pertinence';
  for (const dimension of DIMENSIONS) etat.filtres[dimension.cle] = '';
  rendre();
  refs.champ.focus();
}

/** Fixe la requête depuis le code (proposition, suggestion, effacement). */
function definirRequete(texte) {
  // Une frappe en attente lirait de nouveau le champ : on la jette.
  annulerFrappe();
  fermerPropositions();
  etat.requete = typeof texte === 'string' ? texte : '';
  refs.champ.value = etat.requete;
  rendre();
}

/* -------------------------------------------------------------------------
   14. Clavier

   Deux parcours, deux mécaniques, et c'est voulu :
   - dans le panneau de propositions, le focus RESTE dans le champ pour
     qu'on puisse continuer à taper ; aria-activedescendant désigne l'option ;
   - dans la grille de résultats, le focus se DÉPLACE réellement sur la
     carte : c'est elle qui porte ensuite ses propres boutons.
   ------------------------------------------------------------------------- */

/**
 * Désigne le résultat courant : aria-current et tabindex glissant.
 *
 * @param {number} position index dans `etat.affiches`, -1 pour aucun
 * @param {boolean} [defiler=true] amener le résultat dans le champ de vision
 * @param {boolean} [prendreFocus=false] y déplacer aussi le focus clavier
 */
function definirActif(position, defiler, prendreFocus) {
  const nombre = Math.min(etat.affiches.length, LIMITE_AFFICHAGE);

  // Nettoyage de l'ancien : une seule carte est courante, et une seule est
  // atteignable à la tabulation.
  if (carteActive) {
    carteActive.removeAttribute('aria-current');
    carteActive.tabIndex = -1;
  }
  carteActive = null;

  if (position < -1) position = -1;
  if (position >= nombre) position = nombre - 1;
  etat.actif = nombre === 0 ? -1 : position;

  if (etat.actif < 0) return;

  const doc = etat.affiches[etat.actif];
  const fiche = doc ? fiches.get(String(doc.id)) : null;

  // Garde-fou : une carte absente de la grille ne peut être ni désignée
  // ni ouverte, quoi qu'ait pu laisser `etat.affiches`.
  if (!fiche || !fiche.carte.isConnected) {
    etat.actif = -1;
    return;
  }

  fiche.carte.setAttribute('aria-current', 'true');
  fiche.carte.tabIndex = 0;
  carteActive = fiche.carte;

  if (prendreFocus) {
    try { fiche.carte.focus(); } catch (_e) { /* moteur sans focus() : ignoré */ }
  }

  if (defiler !== false) {
    // 'auto' et non 'smooth' : base.css active le défilement doux au niveau
    // du document, ce qui rendrait le parcours à la flèche pâteux.
    try { fiche.carte.scrollIntoView({ block: 'nearest', behavior: 'auto' }); }
    catch (_e) { /* moteur sans options : le défaut suffit */ }
  }
}

/** Ouvre le résultat courant, ou explique pourquoi il n'y a rien à ouvrir. */
function ouvrirCourant() {
  if (etat.actif < 0) return;
  const doc = etat.affiches[etat.actif];
  const fiche = fiches.get(String(doc.id));
  if (!fiche) return;

  const lien = fiche.carte.querySelector('a[data-action="ouvrir"]');
  if (lien) {
    lien.click();
    return;
  }
  toast('« ' + texteOuVide(doc.titre) + ' » ne porte aucun lien : sa référence '
    + texteOuVide(doc.reference) + ' est copiable depuis sa carte.', 'info');
}

/** Touches gérées depuis le champ de recherche. */
function surToucheChamp(evt) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  switch (evt.key) {
    case 'ArrowDown':
      evt.preventDefault();
      // Les propositions d'abord ; une fois le panneau refermé, la même
      // touche parcourt les résultats et y déplace le focus réel.
      if (boite.ouverte) deplacerProposition(1);
      else definirActif(etat.actif + 1, true, true);
      break;
    case 'ArrowUp':
      evt.preventDefault();
      if (boite.ouverte) deplacerProposition(-1);
      else definirActif(etat.actif - 1, true, true);
      break;
    case 'Home':
      if (boite.ouverte) { evt.preventDefault(); designerProposition(0); break; }
      if (etat.actif < 0) return;      // sinon on empêche le retour au début du texte
      evt.preventDefault();
      definirActif(0, true, true);
      break;
    case 'End':
      if (boite.ouverte) {
        evt.preventDefault();
        designerProposition(boite.liste.length - 1);
        break;
      }
      if (etat.actif < 0) return;
      evt.preventDefault();
      definirActif(Math.min(etat.affiches.length, LIMITE_AFFICHAGE) - 1, true, true);
      break;
    case 'Enter':
      evt.preventDefault();
      if (boite.ouverte && boite.actif >= 0) activerProposition(boite.actif);
      else if (boite.ouverte) fermerPropositions();
      else ouvrirCourant();
      break;
    case 'Escape':
      // Échap referme d'abord les propositions ; puis efface la requête ;
      // puis lève ce qui reste (menus, tri, parcours) plutôt que rien.
      evt.preventDefault();
      if (boite.ouverte) fermerPropositions();
      else if (etat.requete !== '') definirRequete('');
      else if (auMoinsUnFiltre() || etat.tout) toutEffacer();
      else definirActif(-1);
      break;
    default:
      break;
  }
}

/**
 * Touches gérées une fois le focus posé sur une carte de résultat.
 * Les touches d'un bouton ou d'un lien de la carte ne sont pas captées :
 * Entrée doit continuer d'activer « Ouvrir » ou « Copier le lien ».
 */
function surToucheResultats(evt) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  const carte = (evt.target && typeof evt.target.closest === 'function')
    ? evt.target.closest('.ds-carte')
    : null;
  if (!carte || evt.target !== carte) return;

  const dernier = Math.min(etat.affiches.length, LIMITE_AFFICHAGE) - 1;

  switch (evt.key) {
    case 'ArrowDown':
      evt.preventDefault();
      definirActif(etat.actif + 1, true, true);
      break;
    case 'ArrowUp':
      evt.preventDefault();
      // Remonter au-dessus du premier résultat rend la main au champ.
      if (etat.actif <= 0) {
        definirActif(-1, false);
        refs.champ.focus();
      } else {
        definirActif(etat.actif - 1, true, true);
      }
      break;
    case 'Home':
      evt.preventDefault();
      definirActif(0, true, true);
      break;
    case 'End':
      evt.preventDefault();
      definirActif(dernier, true, true);
      break;
    case 'Enter':
      evt.preventDefault();
      ouvrirCourant();
      break;
    case 'Escape':
      evt.preventDefault();
      definirActif(-1, false);
      refs.champ.focus();
      break;
    default:
      // Reprendre la frappe depuis une carte ramène au champ : personne ne
      // doit taper dans le vide après avoir parcouru les résultats.
      if (evt.key.length === 1 || evt.key === 'Backspace') {
        definirActif(-1, false);
        refs.champ.focus();
      }
      break;
  }
}

/** Raccourcis disponibles depuis n'importe où dans la page. */
function surToucheDocument(evt) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  // Une modale ouverte capte le clavier. Sans ce garde-fou, « / »
  // donnerait le focus au champ situé derrière le voile, et le rattrapage
  // de focus de ui.js renverrait ensuite l'utilisateur au bouton de
  // fermeture. (ui.js pose `data-modale` sur le voile.)
  if (document.querySelector('[data-modale]')) return;

  const cible = evt.target;
  const dansUneSaisie = cible && (
    cible.tagName === 'INPUT' || cible.tagName === 'TEXTAREA'
    || cible.tagName === 'SELECT' || cible.isContentEditable);

  if (evt.key === '/' && !dansUneSaisie) {
    evt.preventDefault();
    refs.champ.focus();
    refs.champ.select();
    return;
  }

  // Échap hors du champ : on efface et on rend la main au champ. Le
  // parcours des résultats gère Échap avant d'arriver ici.
  if (evt.key === 'Escape' && cible !== refs.champ && !dansUneSaisie
      && !(cible && typeof cible.closest === 'function' && cible.closest('.ds-carte'))) {
    if (surAccueil()) return;
    evt.preventDefault();
    toutEffacer();
  }
}

/* -------------------------------------------------------------------------
   15. Annonce aux lecteurs d'écran

   Une seule annonce, anti-rebondie : sans cela, chaque caractère saisi
   déclencherait une interruption vocale.
   ------------------------------------------------------------------------- */

const annoncerResultats = debounce(() => {
  const nombre = etat.affiches.length;
  if (surAccueil()) {
    annoncer('Écran de départ, ' + compteDocuments(corpus.documents.length)
      + ' référencés.');
    return;
  }
  if (nombre === 0) {
    annoncer('Aucun résultat.');
    return;
  }
  annoncer(nombre + ' ' + pluriel(nombre, 'résultat', 'résultats') + '.');
}, DELAI_ANNONCE);

/* -------------------------------------------------------------------------
   16. Propositions locales (aucun envoi réseau)
   ------------------------------------------------------------------------- */

/** Charge les propositions mémorisées dans ce navigateur. */
function chargerPropositions() {
  const brut = stockage.lire(CLE_PROPOSITIONS, []);
  propositions = Array.isArray(brut)
    ? brut.filter((p) => p && typeof p === 'object' && typeof p.titre === 'string')
    : [];
}

/** Enregistre la liste courante (silencieux si le stockage est indisponible). */
function enregistrerPropositions() {
  stockage.ecrire(CLE_PROPOSITIONS, propositions);
}

/** Construit le formulaire de la modale et renvoie ses accès. */
function formulaireProposition() {
  const idBase = 'ds-prop-' + Date.now().toString(36);

  const champTitre = el('input', {
    class: 'champ__controle',
    id: idBase + '-titre',
    type: 'text',
    required: true,
    autocomplete: 'off',
    ariaDescribedby: idBase + '-titre-erreur'
  });

  const erreurTitre = el('p', {
    class: 'champ__erreur',
    id: idBase + '-titre-erreur',
    role: 'alert',
    hidden: true
  }, 'Indiquez au moins un titre pour la proposition.');

  // L'erreur disparaît dès que la personne corrige : elle ne reste pas
  // affichée en travers d'un champ désormais valide.
  champTitre.addEventListener('input', () => {
    if (erreurTitre.hidden) return;
    erreurTitre.hidden = true;
    champTitre.removeAttribute('aria-invalid');
  });

  const champType = el('select', { class: 'champ__controle', id: idBase + '-type' },
    el('option', { value: '' }, 'Non précisé'),
    corpus.types.map((type) => el('option', { value: type }, type)));

  const casesMetier = corpus.valeurs.metier.map((metier) => el('label', { class: 'case' },
    el('input', {
      class: 'case__controle',
      type: 'checkbox',
      value: metier
    }),
    el('span', { class: 'case__texte' }, metier)));

  const champPorteur = el('input', {
    class: 'champ__controle',
    id: idBase + '-porteur',
    type: 'text',
    autocomplete: 'off',
    placeholder: 'Personne 00'
  });

  const champLien = el('input', {
    class: 'champ__controle',
    id: idBase + '-lien',
    type: 'text',
    autocomplete: 'off',
    placeholder: 'Emplacement ou référence du document'
  });

  const champRemarque = el('textarea', {
    class: 'champ__controle',
    id: idBase + '-remarque',
    rows: 3
  });

  const groupeMetier = el('fieldset', { class: 'groupe-champs' },
    el('legend', { class: 'groupe-champs__legende' }, 'Métiers concernés'),
    ...casesMetier);

  const avertissement = stockage.disponible()
    ? null
    : el('p', { class: 'champ__aide' },
      'Le stockage local est indisponible dans ce navigateur : la proposition '
      + 'ne sera conservée que le temps de cette visite.');

  const formulaire = el('form', {
    class: 'pile',
    novalidate: true,
    onSubmit: (evt) => { evt.preventDefault(); }
  },
  el('p', { class: 'texte-sm texte-doux sans-marge' },
    'Cette proposition reste dans ce navigateur. Rien n’est envoyé : '
    + 'servez-vous-en comme d’un pense-bête avant d’en parler au porteur.'),
  avertissement,
  el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idBase + '-titre' },
      'Titre du document ',
      el('span', { class: 'champ__requis', ariaHidden: 'true' }, '*')),
    champTitre,
    erreurTitre),
  el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idBase + '-type' }, 'Type'),
    el('span', { class: 'champ__select' }, champType)),
  groupeMetier,
  el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idBase + '-porteur' }, 'Porteur'),
    champPorteur),
  el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idBase + '-lien' }, 'Lien'),
    champLien,
    el('span', { class: 'champ__aide' },
      'Facultatif. Laissez vide si le document ne porte aucun lien.')),
  el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: idBase + '-remarque' }, 'Remarque'),
    champRemarque),
  // Bouton de soumission implicite : permet la validation à la touche
  // Entrée sans être atteignable à la tabulation (l'action réelle est
  // dans le pied de la modale).
  el('button', { type: 'submit', class: 'visuellement-cache', tabIndex: -1 },
    'Enregistrer'));

  return {
    formulaire,
    champTitre,
    erreurTitre,
    lire: () => ({
      titre: champTitre.value.trim(),
      type: champType.value,
      metier: casesMetier
        .map((label) => label.querySelector('input'))
        .filter((c) => c.checked)
        .map((c) => c.value),
      porteur: champPorteur.value.trim(),
      lien: champLien.value.trim(),
      remarque: champRemarque.value.trim()
    })
  };
}

/** Ouvre la modale « Proposer un document » (enregistrement LOCAL). */
function ouvrirModaleProposition(declencheur) {
  // Le panneau de propositions ne doit pas rester ouvert derrière le voile.
  fermerPropositions();

  const champs = formulaireProposition();

  const valider = () => {
    const valeurs = champs.lire();
    if (valeurs.titre === '') {
      champs.erreurTitre.hidden = false;
      champs.champTitre.setAttribute('aria-invalid', 'true');
      champs.champTitre.focus();
      return false;        // la modale reste ouverte
    }

    propositions = propositions.concat([{
      id: 'p-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7),
      titre: valeurs.titre,
      type: valeurs.type,
      metier: valeurs.metier,
      porteur: valeurs.porteur,
      lien: valeurs.lien,
      remarque: valeurs.remarque,
      cree: new Date().toISOString().slice(0, 10)
    }]);

    enregistrerPropositions();
    rendrePropositions();
    toast('Proposition enregistrée localement.', 'succes');
    return true;
  };

  // La touche Entrée dans le formulaire déclenche la même validation.
  champs.formulaire.addEventListener('submit', () => {
    if (valider()) instance.fermer('action');
  });

  const instance = ouvrirModale({
    titre: 'Proposer un document',
    declencheur,
    contenu: champs.formulaire,
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      { libelle: 'Enregistrer', variante: 'principal', onClick: () => valider() }
    ]
  });
}

/** Affiche (ou masque) la section « Vos propositions ». */
function rendrePropositions() {
  if (!refs.propositionsSection || !refs.propositionsListe) return;

  if (propositions.length === 0) {
    refs.propositionsSection.hidden = true;
    vider(refs.propositionsListe);
    return;
  }
  refs.propositionsSection.hidden = false;

  monter(refs.propositionsListe, propositions.map((proposition) => {
    const details = [proposition.type, (proposition.metier || []).join(', '),
      proposition.porteur].filter((v) => typeof v === 'string' && v !== '');

    return el('article', { class: 'carte carte--compacte' },
      el('div', { class: 'carte__entete' },
        el('p', { class: 'carte__titre' }, proposition.titre),
        el('span', { class: 'badge badge--neutre' }, 'Brouillon local')),
      details.length ? el('p', { class: 'carte__meta' },
        details.map((valeur) => el('span', {}, valeur))) : null,
      proposition.remarque
        ? el('p', { class: 'ds-carte__extrait' }, proposition.remarque)
        : null,
      el('div', { class: 'carte__pied' },
        el('span', {}, 'Ajoutée le ', el('time',
          { datetime: proposition.cree }, formaterDate(proposition.cree))),
        el('div', { class: 'ds-carte__actions pousse' },
          el('button', {
            type: 'button',
            class: 'bouton bouton--danger-discret bouton--compact',
            dataset: { action: 'supprimer-proposition', id: proposition.id },
            ariaLabel: 'Supprimer la proposition « ' + proposition.titre + ' »'
          }, 'Supprimer'))));
  }));
}

/** Suppression d'une proposition : destructive, donc confirmée (SPEC §6.5). */
function confirmerSuppression(id, declencheur) {
  const proposition = propositions.find((p) => p.id === id);
  if (!proposition) return;

  ouvrirModale({
    titre: 'Supprimer cette proposition ?',
    declencheur,
    classe: 'modale--etroite',
    contenu: el('p', {},
      '« ' + proposition.titre + ' » sera définitivement retirée de vos '
      + 'propositions locales. Cette action est irréversible.'),
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', autofocus: true },
      {
        libelle: 'Supprimer',
        variante: 'danger',
        onClick: () => {
          propositions = propositions.filter((p) => p.id !== id);
          enregistrerPropositions();
          rendrePropositions();
          toast('Proposition supprimée.', 'info');
          // La carte supprimée emportait le bouton déclencheur : ui.js ne
          // pourra pas lui rendre le focus. On vise le champ de recherche.
          refs.champ.focus();
        }
      }
    ]
  });
}

/* -------------------------------------------------------------------------
   17. Démarrage
   ------------------------------------------------------------------------- */

function demarrer() {
  initTheme();
  initNav('docsearch');

  refs.champ = document.getElementById('ds-champ');
  refs.zone = document.getElementById('ds-zone');
  refs.suggestions = document.getElementById('ds-suggestions');
  refs.jetons = document.getElementById('ds-jetons');
  refs.propositionsSection = document.getElementById('ds-propositions');
  refs.propositionsListe = document.getElementById('ds-propositions-liste');

  for (const dimension of DIMENSIONS) {
    const select = document.getElementById(dimension.id);
    if (select) refs.menus.set(dimension.cle, select);
  }

  if (!refs.champ || !refs.zone || !refs.suggestions || !refs.jetons) return;

  // Propositions locales : indépendantes du corpus, donc affichées tout
  // de suite, même si le JSON n'arrive jamais.
  chargerPropositions();
  rendrePropositions();
  deleguer(refs.propositionsListe, '[data-action="supprimer-proposition"]', 'click',
    (evt, bouton) => confirmerSuppression(bouton.dataset.id, bouton));

  // La requête de l'URL est appliquée avant même le chargement : le champ
  // est déjà rempli quand les squelettes s'affichent.
  const initial = etatUrl.lire();
  if (typeof initial.q === 'string') refs.champ.value = initial.q;

  // Le champ n'est focalisé d'office que si l'URL porte déjà une requête :
  // sur un premier passage, les points d'entrée doivent pouvoir être lus
  // avant que le clavier mobile ne recouvre l'écran. « / » y revient.
  if (refs.champ.value) {
    refs.champ.focus();
    refs.champ.select();
  }

  // Recherche instantanée, anti-rebondie sous le seuil de perception. Les
  // propositions sont calculées dans la foulée : le classement de la
  // requête est déjà en cache, elles ne coûtent donc presque rien.
  const surFrappe = debounce(() => {
    etat.requete = refs.champ.value;
    rendre();
    majPropositions();
  }, DELAI_FRAPPE);

  annulerFrappe = () => surFrappe.annuler();

  refs.champ.addEventListener('input', surFrappe);
  refs.champ.addEventListener('keydown', surToucheChamp);
  refs.champ.addEventListener('blur', () => fermerPropositions());
  document.addEventListener('keydown', surToucheDocument);

  // Un appui sur une proposition ne doit pas faire perdre le focus au
  // champ : sans cela, le `blur` refermerait le panneau avant le clic.
  refs.suggestions.addEventListener('mousedown', (evt) => evt.preventDefault());

  deleguer(refs.suggestions, '.ds-suggestion', 'click', (evt, option) => {
    activerProposition(Number(option.dataset.position));
  });

  // Survoler une proposition la désigne : souris et clavier partagent la
  // même notion de « proposition courante ».
  deleguer(refs.suggestions, '.ds-suggestion', 'mousemove', (evt, option) => {
    const position = Number(option.dataset.position);
    if (position !== boite.actif) designerProposition(position);
  });

  deleguer(refs.jetons, '[data-action]', 'click', (evt, bouton) => {
    if (bouton.dataset.action === 'retirer-filtre') retirerFiltre(bouton.dataset.cle);
    else if (bouton.dataset.action === 'tout-effacer') toutEffacer();
  });

  // Les trois menus déroulants : ils se combinent entre eux et avec la
  // recherche, et ne survivent jamais à un état qu'ils ne décrivent pas.
  for (const dimension of DIMENSIONS) {
    const select = refs.menus.get(dimension.cle);
    if (!select) continue;
    select.addEventListener('change', () => {
      const valeur = select.value;
      etat.filtres[dimension.cle] =
        corpus.connues[dimension.cle].has(valeur) ? valeur : '';
      fermerPropositions();
      rendre();
    });
  }

  deleguer(document, '[data-action="effacer-requete"]', 'click', () => {
    definirRequete('');
    refs.champ.focus();
  });

  avecEtat(
    refs.zone,
    () => chargerDonnees('documents'),
    (donnees, cible) => {
      construireInterface(donnees, cible);

      // L'état complet n'est restauré qu'ici : les valeurs de menus de
      // l'URL doivent être confrontées à celles que le corpus déclare.
      appliquerUrl();
      // Ce que la personne a pu taper pendant le chargement l'emporte.
      if (refs.champ.value !== etat.requete) etat.requete = refs.champ.value;
      else refs.champ.value = etat.requete;

      rendre();
    },
    {
      squelette: afficherSquelettes,
      texteChargement: 'Chargement du fonds documentaire…',
      titreErreur: 'Fonds documentaire indisponible',
      estVide: (donnees) => !donnees || !Array.isArray(donnees.documents)
        || donnees.documents.length === 0,
      titreVide: 'Aucun document référencé',
      texteVide: 'Le fonds documentaire est vide pour le moment. '
        + 'Vous pouvez néanmoins préparer une proposition ci-dessous.'
    }
  );

  // Navigation « Précédent » / « Suivant » et liens partagés.
  etatUrl.ecouter((brut) => {
    if (!pretARendre) return;
    // Une ancre de page (le lien d'évitement « #contenu », par exemple) ne
    // porte aucune de nos clés : ce n'est pas notre état, et l'appliquer
    // effacerait la recherche en cours. `etatUrl.ecrire` n'empilant jamais
    // d'historique, aucun retour arrière légitime n'arrive sans ces clés.
    if (!CLES_URL.some((cle) => cle in brut)) return;
    appliquerUrl(brut);
    refs.champ.value = etat.requete;
    fermerPropositions();
    rendre();
  });
}

demarrer();
