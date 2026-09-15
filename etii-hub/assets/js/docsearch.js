/* =========================================================================
   ETII Hub — Recherche documentaire (SPEC.md §4.6)

   La page centrale du portail. Tout le travail lourd est déjà fait
   ailleurs : `search.js` indexe et classe, `ui.js` fabrique les nœuds,
   `data.js` charge et gère les états. Ce module ne fait que trois choses :

     1. construire l'index UNE fois, au chargement ;
     2. traduire l'état (requête + facettes) en résultats, puis en DOM ;
     3. maintenir cet état synchronisé avec l'URL, le clavier et le
        stockage local.

   Invariants tenus ici :
   - aucun `innerHTML`, aucun `onclick=` : tout passe par el()/frag()/
     monter() et par la délégation d'événements de ui.js ;
   - aucun appel réseau autre que le chargement de assets/data/documents.json ;
   - l'index n'est jamais reconstruit à la frappe ;
   - la grille n'est jamais reconstruite non plus : les cartes sont
     conservées et seulement réordonnées, seul le surlignage est réécrit ;
   - un seul gestionnaire par conteneur, jamais un par carte.
   ========================================================================= */

import {
  el, monter, vider, surlignerVers, deleguer,
  ouvrirModale, toast, annoncer, copierTexte,
  debounce, etatUrl, stockage, initTheme, initNav
} from './ui.js';

import { creerIndex, rechercher, surligner, suggerer, normaliser } from './search.js';

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
   tape le code d'un autre. Le pôle se choisit donc à la facette, qui est
   exacte, et se lit sur la carte — jamais au petit bonheur du classement.
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
   Les dimensions de facettes : les quatre exigées par la SPEC §4.6, plus
   le pôle, qui est l'axe structurel du service (SPEC §1bis). Le pôle vient
   en tête parce que c'est la première question que l'on se pose devant le
   fonds : « qu'est-ce qui relève de chez moi ? ».

   `champ` peut désigner une chaîne ou un TABLEAU dans le document : un
   document relève parfois de deux pôles, exactement comme il relève
   parfois de deux métiers. `valeursDoc()` normalise les deux formes, et
   tout le reste de la mécanique — compteurs croisés, désactivation à zéro,
   hash, « Tout effacer » — est écrit une fois pour toutes les dimensions.

   `filtrable` marque les dimensions à forte cardinalité (le porteur : une
   cinquantaine de valeurs) : leur liste reçoit un champ de filtrage et un
   repli « afficher tout », sans quoi la colonne deviendrait impraticable.
   `teinte` marque les dimensions dont les valeurs ont une couleur propre.
   `documents.json` ne déclare pas de clé « porteurs » : `preparerCorpus()`
   déduit alors les valeurs du corpus, comme pour toute source absente.
*/
const DIMENSIONS = [
  { cle: 'pole',      champ: 'pole',      libelle: 'Pôle',      source: 'poles',
    teinte: true },
  { cle: 'type',      champ: 'type',      libelle: 'Type',      source: 'types' },
  { cle: 'metier',    champ: 'metier',    libelle: 'Métier',    source: 'metiers' },
  { cle: 'porteur',   champ: 'porteur',   libelle: 'Porteur',   source: 'porteurs',
    filtrable: true, pluriel: 'porteurs' },
  { cle: 'perimetre', champ: 'perimetre', libelle: 'Périmètre', source: 'perimetres' }
];

/** Raccourci vers la dimension « pôle », affichée sur chaque carte. */
const DIMENSION_POLE = DIMENSIONS.find((dimension) => dimension.cle === 'pole');

/** Raccourci vers la dimension « métier », multivaluée comme le pôle. */
const DIMENSION_METIER = DIMENSIONS.find((dimension) => dimension.cle === 'metier');

/** Nombre de valeurs montrées d'emblée dans une facette filtrable. */
const VALEURS_FACETTE_VISIBLES = 12;

/*
   Habillage des types documentaires. Purement décoratif : le sens est
   toujours porté par le libellé, jamais par la seule couleur ou le seul
   glyphe (SPEC §7). Un type inconnu retombe sur la variante neutre.
*/
const STYLE_TYPE = {
  'Technique': { glyphe: '◆', badge: 'badge--accent' },
  'Outil':     { glyphe: '⚙', badge: 'badge--info' },
  'Processus': { glyphe: '⇄', badge: 'badge--succes' },
  'Norme':     { glyphe: '§', badge: 'badge--alerte' },
  'Formation': { glyphe: '✻', badge: 'badge--neutre' }
};
const STYLE_TYPE_DEFAUT = { glyphe: '▪', badge: 'badge--neutre' };

/** Anti-rebond de la recherche : court, sous le seuil de perception. */
const DELAI_FRAPPE = 120;

/** Anti-rebond de l'écriture dans l'URL : l'historique n'a pas à suivre la frappe. */
const DELAI_URL = 300;

/** Anti-rebond de l'annonce vocale : on n'annonce pas chaque caractère. */
const DELAI_ANNONCE = 700;

/** Garde-fou d'affichage : au-delà, on rend une page, pas une liste. */
const LIMITE_AFFICHAGE = 120;

/** Clé de stockage des propositions locales. */
const CLE_PROPOSITIONS = 'docsearch.propositions';

/** Mise en forme des dates, une seule instance réutilisée. */
const FORMAT_DATE = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric', month: 'long', year: 'numeric'
});

/* -------------------------------------------------------------------------
   2. État de la page
   ------------------------------------------------------------------------- */

/**
 * Fabrique un objet portant une entrée par dimension. Dérivé de
 * DIMENSIONS plutôt qu'écrit à la main : ajouter une facette ne laisse
 * plus la possibilité d'oublier l'une des trois tables.
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
  /** Valeurs actives par dimension : une entrée par clé de DIMENSIONS. */
  facettes: parDimension(() => new Set()),
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
  comptesType: new Map()
};

/** Références DOM construites une fois par rendu de l'interface. */
const refs = {
  champ: null,
  zone: null,
  barre: null,
  compteur: null,
  resultats: null,
  messages: null,
  effacerTout: null,
  facettes: new Map(),        // 'dim|valeur' -> bouton
  outilsFacette: new Map(),   // clé de dimension filtrable -> { champ, bouton… }
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

/** Propositions locales, source de vérité en mémoire. */
let propositions = [];

/** Vrai une fois l'interface de résultats construite. */
let pretARendre = false;

/* -------------------------------------------------------------------------
   3. Petits utilitaires
   ------------------------------------------------------------------------- */

/** Normalise une valeur d'URL (chaîne ou répétition) en tableau. */
function enTableau(valeur) {
  if (Array.isArray(valeur)) return valeur;
  if (valeur === null || valeur === undefined || valeur === '') return [];
  return [String(valeur)];
}

/** Valeurs d'un document pour une dimension donnée, toujours en tableau. */
function valeursDoc(doc, dimension) {
  const brut = doc[dimension.champ];
  if (Array.isArray(brut)) return brut.filter((v) => typeof v === 'string' && v);
  return (typeof brut === 'string' && brut) ? [brut] : [];
}

/** Y a-t-il au moins une facette active ? */
function auMoinsUneFacette() {
  return DIMENSIONS.some((d) => etat.facettes[d.cle].size > 0);
}

/**
 * Le document satisfait-il les facettes actives ?
 * OU à l'intérieur d'une dimension, ET entre les dimensions.
 *
 * @param {object} doc
 * @param {string} [dimensionIgnoree] dimension exclue du test — c'est ce
 *        qui permet de compter les résultats d'une facette « comme si »
 *        elle n'était pas déjà appliquée.
 * @returns {boolean}
 */
function correspondFacettes(doc, dimensionIgnoree) {
  for (const dimension of DIMENSIONS) {
    if (dimension.cle === dimensionIgnoree) continue;
    const actives = etat.facettes[dimension.cle];
    if (actives.size === 0) continue;
    const valeurs = valeursDoc(doc, dimension);
    if (!valeurs.some((v) => actives.has(v))) return false;
  }
  return true;
}

/** Classement pour la requête courante, calculé au plus une fois par requête. */
function classement() {
  if (cacheRequete === etat.requete && cacheClassement) return cacheClassement;
  cacheRequete = etat.requete;
  cacheClassement = rechercher(corpus.index, etat.requete);
  return cacheClassement;
}

/** Date ISO -> « 2 février 2026 ». Une date illisible est rendue telle quelle. */
function formaterDate(iso) {
  if (typeof iso !== 'string' || iso === '') return '';
  const date = new Date(iso + 'T00:00:00');
  if (Number.isNaN(date.getTime())) return iso;
  try { return FORMAT_DATE.format(date); } catch (_e) { return iso; }
}

/** Accord singulier/pluriel sans concaténation hasardeuse. */
function pluriel(nombre, singulier, plurielForme) {
  return nombre > 1 ? plurielForme : singulier;
}

/** Habillage d'un type documentaire. */
function styleType(type) {
  return STYLE_TYPE[type] || STYLE_TYPE_DEFAUT;
}

/* -------------------------------------------------------------------------
   4. Synchronisation avec l'URL

   Format : #q=harnais&type=Technique&metier=Qualité&tout=1
   Écriture en replaceState (etatUrl s'en charge) et anti-rebondie : le
   bouton « Précédent » reste utilisable, l'URL reste partageable.
   ------------------------------------------------------------------------- */

/** Lit l'état depuis le hash et le recopie dans `etat`. */
function appliquerUrl(brut) {
  const source = brut || etatUrl.lire();

  etat.requete = typeof source.q === 'string' ? source.q : '';
  for (const dimension of DIMENSIONS) {
    const connues = corpus.connues[dimension.cle];
    etat.facettes[dimension.cle] = new Set(
      enTableau(source[dimension.cle]).filter((v) => connues.has(v))
    );
  }
  etat.tout = String(source.tout || '') === '1';
}

/** Clés que cette page reconnaît dans le fragment d'URL. */
const CLES_URL = ['q', 'tout'].concat(DIMENSIONS.map((dimension) => dimension.cle));

const ecrireUrl = debounce(() => {
  // Construit depuis DIMENSIONS : ajouter une facette ne demande rien ici.
  const sortie = { q: etat.requete.trim(), tout: etat.tout ? '1' : '' };
  for (const dimension of DIMENSIONS) {
    sortie[dimension.cle] = Array.from(etat.facettes[dimension.cle]);
  }
  etatUrl.ecrire(sortie);
}, DELAI_URL);

/* -------------------------------------------------------------------------
   5. Squelettes de chargement
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
  const grille = el('div', {
    class: 'grille grille--ample',
    ariaHidden: 'true'
  });
  for (let i = 0; i < 6; i += 1) grille.append(carteSquelette());
  monter(cible, grille);
}

/* -------------------------------------------------------------------------
   6. Construction de l'interface (une seule fois, après chargement)
   ------------------------------------------------------------------------- */

/**
 * Bâtit la colonne de facettes et la colonne de résultats, puis les monte
 * dans le conteneur piloté par avecEtat().
 *
 * @param {object} donnees contenu de documents.json
 * @param {Element} cible
 */
function construireInterface(donnees, cible) {
  preparerCorpus(donnees);

  // Un « Réessayer » rebâtit tout : les cartes mises en cache appartiennent
  // à une grille désormais jetée, on repart donc d'un cache vierge.
  fiches.clear();
  carteActive = null;
  cacheRequete = null;
  cacheClassement = null;

  /* --- Colonne de gauche : les facettes -------------------------------- */

  refs.facettes.clear();
  refs.outilsFacette.clear();

  refs.effacerTout = el('button', {
    type: 'button',
    class: 'bouton bouton--discret bouton--compact',
    onClick: () => toutEffacer()
  }, 'Tout effacer');

  const groupes = DIMENSIONS.map((dimension) => {
    const idTitre = 'ds-facette-' + dimension.cle;

    const liste = el('ul', {
      class: 'facettes',
      ariaLabelledby: idTitre
    }, corpus.valeurs[dimension.cle].map((valeur) => {
      const compteur = el('span', { class: 'facette__compteur' }, '0');
      const bouton = el('button', {
        type: 'button',
        class: 'facette',
        ariaPressed: 'false',
        // `data-pole` n'est posé que sur les dimensions teintées : c'est
        // lui qui résout --pole-teinte en CSS. Le point qui en découle est
        // décoratif, le code du pôle est écrit juste à côté.
        dataset: {
          dimension: dimension.cle,
          valeur,
          pole: dimension.teinte ? valeur : null
        }
      },
      el('span', { class: 'facette__marque', ariaHidden: 'true' }, '✓'),
      dimension.teinte
        ? el('span', { class: 'pole-point', ariaHidden: 'true' })
        : null,
      el('span', {}, valeur),
      compteur);

      const element = el('li', {}, bouton);
      bouton.compteurNoeud = compteur;
      bouton.elementListe = element;
      bouton.nombreCourant = 0;
      refs.facettes.set(dimension.cle + '|' + valeur, bouton);
      return element;
    }));

    // Dimension à forte cardinalité : champ de filtrage + repli d'affichage.
    const outils = dimension.filtrable ? outilsFacette(dimension, idTitre) : null;

    return el('section', { class: 'pile pile--serree' },
      el('h3', { class: 'ds-titre-facette', id: idTitre }, dimension.libelle),
      outils ? outils.champBloc : null,
      liste,
      outils ? outils.vide : null,
      outils ? outils.bouton : null);
  });

  const filtres = el('aside', {
    class: 'ds-filtres pile',
    ariaLabel: 'Filtres'
  },
  el('div', { class: 'rangee rangee--entre rangee--serree' },
    el('h2', { class: 'ds-titre-facette' }, 'Filtres'),
    refs.effacerTout),
  ...groupes);

  /* --- Colonne de droite : compteur, résultats, messages --------------- */

  refs.compteur = el('p', { class: 'ds-compteur' }, '');

  refs.barre = el('div', { class: 'rangee rangee--entre' },
    refs.compteur,
    el('button', {
      type: 'button',
      class: 'bouton bouton--discret bouton--compact',
      onClick: (evt) => ouvrirModaleProposition(evt.currentTarget)
    }, 'Proposer un document'));

  // Une liste de cartes actionnables, pas un listbox : les options ARIA
  // imposent « Children Presentational: True », ce qui effacerait les
  // boutons « Ouvrir » et « Copier le lien » de l'arbre d'accessibilité.
  refs.resultats = el('ul', {
    class: 'grille grille--ample ds-liste',
    id: 'ds-resultats',
    role: 'list',
    ariaLabel: 'Résultats de la recherche'
  });

  refs.messages = el('div', {});

  const colonne = el('div', { class: 'pile pile--lache' },
    refs.barre, refs.resultats, refs.messages);

  monter(cible, el('div', { class: 'ds-agencement' }, filtres, colonne));

  /* --- Délégations : un gestionnaire par conteneur, jamais par carte --- */

  deleguer(filtres, '.facette[data-dimension]', 'click', (evt, bouton) => {
    basculerFacette(bouton.dataset.dimension, bouton.dataset.valeur);
  });

  deleguer(refs.resultats, '[data-action]', 'click', (evt, bouton) => {
    surActionCarte(evt, bouton);
  });

  // Un clic dans une carte (hors bouton) la désigne comme résultat courant :
  // souris et clavier partagent ainsi la même notion de « courant ».
  deleguer(refs.resultats, '.ds-carte', 'click', (evt, carte) => {
    if (evt.target.closest('[data-action]')) return;
    const position = etat.affiches.findIndex((doc) => String(doc.id) === carte.dataset.id);
    if (position !== -1) definirActif(position, false);
  });

  // Une fois le focus posé sur une carte, le parcours continue au clavier.
  refs.resultats.addEventListener('keydown', surToucheResultats);

  deleguer(refs.messages, '[data-action]', 'click', (evt, bouton) => {
    surActionMessage(evt, bouton);
  });

  pretARendre = true;
}

/**
 * Outils d'une facette à forte cardinalité : un champ pour filtrer les
 * valeurs, un bouton pour déplier le reste, un mot quand rien ne
 * correspond. Sans cela, les 51 porteurs du fonds rendraient la colonne
 * de filtres inutilisable.
 *
 * @param {object} dimension entrée de DIMENSIONS
 * @param {string} idTitre   identifiant du titre du groupe
 * @returns {object} accès conservés dans refs.outilsFacette
 */
function outilsFacette(dimension, idTitre) {
  const idChamp = idTitre + '-filtre';
  const nom = dimension.pluriel || dimension.libelle.toLowerCase();

  const champ = el('input', {
    class: 'champ__controle',
    id: idChamp,
    type: 'search',
    autocomplete: 'off',
    autocapitalize: 'none',
    spellcheck: 'false',
    placeholder: 'Filtrer les ' + nom + '…',
    onInput: () => {
      outils.etendu = false;
      majVisibiliteValeurs(dimension);
    }
  });

  const champBloc = el('div', { class: 'champ' },
    el('label', { class: 'visuellement-cache', for: idChamp },
      'Restreindre la liste des ' + nom),
    champ);

  const vide = el('p', {
    class: 'texte-xs texte-doux sans-marge',
    hidden: true
  }, 'Aucune valeur ne correspond.');

  const bouton = el('button', {
    type: 'button',
    class: 'bouton bouton--discret bouton--compact',
    hidden: true,
    onClick: () => {
      outils.etendu = !outils.etendu;
      majVisibiliteValeurs(dimension);
      // Le bouton survit au basculement : le focus n'est jamais perdu.
      bouton.focus();
    }
  }, '');

  const outils = { champ, champBloc, vide, bouton, etendu: false };
  refs.outilsFacette.set(dimension.cle, outils);
  return outils;
}

/**
 * Applique le filtre textuel et le repli d'affichage à une facette
 * filtrable. Une valeur active reste toujours visible : il faut pouvoir
 * la relâcher, même si elle ne correspond plus au filtre saisi.
 *
 * @param {object} dimension entrée de DIMENSIONS
 */
function majVisibiliteValeurs(dimension) {
  const outils = refs.outilsFacette.get(dimension.cle);
  if (!outils) return;

  const filtre = normaliser(outils.champ.value || '');
  const actives = etat.facettes[dimension.cle];
  const candidats = [];

  for (const valeur of corpus.valeurs[dimension.cle]) {
    const bouton = refs.facettes.get(dimension.cle + '|' + valeur);
    if (!bouton || !bouton.elementListe) continue;

    const active = actives.has(valeur);
    const correspond = filtre === '' || normaliser(valeur).indexOf(filtre) !== -1;

    if (active) {
      bouton.elementListe.hidden = false;
    } else if (bouton.nombreCourant > 0 && correspond) {
      candidats.push(bouton.elementListe);
    } else {
      bouton.elementListe.hidden = true;
    }
  }

  const limite = outils.etendu ? candidats.length : VALEURS_FACETTE_VISIBLES;
  candidats.forEach((element, position) => { element.hidden = position >= limite; });

  const reste = candidats.length - VALEURS_FACETTE_VISIBLES;
  outils.bouton.hidden = reste <= 0;
  if (!outils.bouton.hidden) {
    outils.bouton.textContent = outils.etendu
      ? 'Réduire la liste'
      : 'Afficher ' + reste + ' ' + pluriel(reste, 'valeur de plus', 'valeurs de plus');
  }

  outils.vide.hidden = candidats.length > 0 || actives.size > 0;
}

/** Prépare corpus, index et valeurs de facettes. Appelé une seule fois. */
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
      : Array.from(new Set(corpus.documents.flatMap((doc) => valeursDoc(doc, dimension)))).sort();

    corpus.valeurs[dimension.cle] = valeurs;
    corpus.connues[dimension.cle] = new Set(valeurs);
  }

  corpus.comptesType = new Map();
  for (const doc of corpus.documents) {
    const type = typeof doc.type === 'string' ? doc.type : '';
    if (!type) continue;
    corpus.comptesType.set(type, (corpus.comptesType.get(type) || 0) + 1);
  }
}

/* -------------------------------------------------------------------------
   7. Rendu : état -> affichage
   ------------------------------------------------------------------------- */

/** Recalcule tout ce qui dépend de l'état, dans l'ordre le moins coûteux. */
function rendre() {
  if (!pretARendre) return;

  const base = classement();

  majCompteursFacettes(base);

  const filtres = base.filter((resultat) => correspondFacettes(resultat.doc));

  const accueil = etat.requete.trim() === '' && !auMoinsUneFacette() && !etat.tout;

  // L'accueil ne rend aucune liste : `affiches` doit donc rester vide, sinon
  // ↑/↓ désigneraient des cartes détachées du DOM et Entrée ouvrirait un
  // document que la page n'affiche nulle part.
  etat.affiches = accueil ? [] : filtres.map((resultat) => resultat.doc);

  refs.effacerTout.disabled = !auMoinsUneFacette() && etat.requete === '' && !etat.tout;

  if (accueil) {
    afficherAccueil();
  } else if (etat.affiches.length === 0) {
    afficherAucunResultat();
  } else {
    afficherResultats();
  }

  ecrireUrl();
  annoncerResultats();
}

/** Met à jour libellés, compteurs et état activé/désactivé des facettes. */
function majCompteursFacettes(base) {
  for (const dimension of DIMENSIONS) {
    // Compteur d'une facette : calculé en IGNORANT sa propre dimension,
    // comme dans toute recherche à facettes digne de ce nom.
    const comptes = new Map();
    for (const resultat of base) {
      if (!correspondFacettes(resultat.doc, dimension.cle)) continue;
      for (const valeur of valeursDoc(resultat.doc, dimension)) {
        comptes.set(valeur, (comptes.get(valeur) || 0) + 1);
      }
    }

    const actives = etat.facettes[dimension.cle];
    for (const valeur of corpus.valeurs[dimension.cle]) {
      const bouton = refs.facettes.get(dimension.cle + '|' + valeur);
      if (!bouton) continue;

      const nombre = comptes.get(valeur) || 0;
      const active = actives.has(valeur);

      bouton.nombreCourant = nombre;
      if (bouton.compteurNoeud.textContent !== String(nombre)) {
        bouton.compteurNoeud.textContent = String(nombre);
      }
      bouton.setAttribute('aria-pressed', active ? 'true' : 'false');
      bouton.setAttribute('aria-label',
        dimension.libelle + ' ' + valeur + ', ' + nombre + ' '
        + pluriel(nombre, 'résultat', 'résultats'));

      // Une facette sans résultat est désactivée, pas retirée — sauf si
      // elle est active : il faut toujours pouvoir la relâcher.
      bouton.disabled = nombre === 0 && !active;
    }

    // Les dimensions à forte cardinalité ne montrent qu'une part de leurs
    // valeurs : la sélection dépend des compteurs qu'on vient de poser.
    if (dimension.filtrable) majVisibiliteValeurs(dimension);
  }
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
  monter(refs.resultats, noeuds);

  refs.resultats.hidden = false;
  refs.barre.hidden = false;
  refs.compteur.textContent = texteCompteur(total);

  vider(refs.messages);
  if (tronque) {
    monter(refs.messages, el('p', { class: 'texte-sm texte-doux texte-centre' },
      'Seuls les ' + LIMITE_AFFICHAGE + ' documents les plus pertinents sont '
      + 'affichés. Affinez la recherche pour voir les suivants.'));
  }

  definirActif(-1, false);
}

/** Écran d'accueil : accès rapides par type, plus le volume du fonds. */
function afficherAccueil() {
  vider(refs.resultats);
  refs.resultats.hidden = true;
  refs.barre.hidden = true;
  definirActif(-1, false);

  const total = corpus.documents.length;

  const tuiles = el('ul', { class: 'grille grille--compacte' },
    corpus.valeurs.type.map((type) => {
      const nombre = corpus.comptesType.get(type) || 0;
      const habillage = styleType(type);
      return el('li', {},
        el('button', {
          type: 'button',
          class: 'carte carte--compacte carte--cliquable ds-tuile',
          dataset: { action: 'filtrer-type', valeur: type },
          ariaLabel: 'Filtrer sur le type ' + type + ', ' + nombre + ' '
            + pluriel(nombre, 'document', 'documents')
        },
        el('span', { class: 'ds-tuile__glyphe', ariaHidden: 'true' }, habillage.glyphe),
        el('span', { class: 'ds-tuile__nom' }, type),
        el('span', { class: 'ds-tuile__compte' },
          nombre + ' ' + pluriel(nombre, 'document', 'documents'))));
    }));

  monter(refs.messages, el('div', { class: 'pile pile--lache' },
    el('div', { class: 'pile pile--serree' },
      el('h2', {}, 'Accès rapides'),
      el('p', { class: 'texte-doux mesure sans-marge' },
        total + ' ' + pluriel(total, 'document référencé', 'documents référencés')
        + '. Choisissez un type pour commencer, ou tapez directement votre '
        + 'recherche dans le champ ci-dessus.')),
    tuiles,
    el('div', { class: 'rangee' },
      el('button', {
        type: 'button',
        class: 'bouton bouton--secondaire',
        dataset: { action: 'parcourir-tout' }
      }, 'Parcourir les ' + total + ' documents'),
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret',
        dataset: { action: 'proposer' }
      }, 'Proposer un document'))));
}

/** Aucun résultat : suggestion, retrait des filtres, proposition. */
function afficherAucunResultat() {
  vider(refs.resultats);
  refs.resultats.hidden = true;
  refs.barre.hidden = false;
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
  const actifs = [];
  for (const dimension of DIMENSIONS) {
    for (const valeur of etat.facettes[dimension.cle]) {
      actifs.push(el('li', {},
        el('button', {
          type: 'button',
          class: 'facette facette--compacte',
          dataset: { action: 'retirer-facette', dimension: dimension.cle, valeur },
          ariaLabel: 'Retirer le filtre ' + dimension.libelle + ' ' + valeur
        },
        el('span', {}, dimension.libelle + ' : ' + valeur),
        el('span', { ariaHidden: 'true' }, '×'))));
    }
  }
  if (actifs.length) {
    bloc.append(
      el('p', { class: 'texte-sm texte-doux sans-marge' }, 'Filtres actifs :'),
      el('ul', { class: 'facettes' }, actifs));
  }

  const actions = el('div', { class: 'etat-vide__actions' });
  if (etat.requete !== '' || auMoinsUneFacette() || etat.tout) {
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

/** Phrase du compteur visible. */
function texteCompteur(nombre) {
  const total = corpus.documents.length;
  if (nombre === 0) return 'Aucun document';
  const debut = nombre + ' ' + pluriel(nombre, 'document', 'documents');
  return nombre === total ? debut : debut + ' sur ' + total;
}

/** Explication de l'absence de résultat, adaptée à ce qui est actif. */
function texteAucunResultat() {
  const avecRequete = etat.requete.trim() !== '';
  const avecFiltres = auMoinsUneFacette();

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
   8. Cartes de résultat

   Une carte est construite au plus une fois par document et conservée
   dans `fiches`. À la frappe suivante, seuls les fragments surlignés sont
   réécrits : la structure, les badges et les boutons ne bougent pas.
   ------------------------------------------------------------------------- */

/** Récupère la fiche d'un document, en la construisant au besoin. */
function obtenirFiche(doc) {
  const id = String(doc.id);
  const existante = fiches.get(id);
  if (existante) return existante;

  const habillage = styleType(doc.type);

  const titre = el('h3', { class: 'ds-carte__titre' });
  const reference = el('span', { class: 'badge badge--carre badge--contour' });
  const resume = el('p', { class: 'ds-carte__resume' });

  /* Le ou les pôles dont relève le document. Une pastille ÉTIQUETÉE : le
     point teinté est décoratif, c'est « Pôle ETIIA » écrit à côté qui
     porte l'information. La couleur ne signale donc jamais seule le pôle
     (SPEC §1bis), et la carte reste lisible en niveaux de gris. */
  const poles = valeursDoc(doc, DIMENSION_POLE).map(
    (code) => el('li', {},
      el('span', { class: 'badge badge--pole', dataset: { pole: code } },
        el('span', { class: 'pole-point', ariaHidden: 'true' }),
        'Pôle ' + code)));

  const metiers = valeursDoc(doc, DIMENSION_METIER).map(
    (metier) => el('li', {}, el('span', { class: 'badge badge--contour' }, metier)));

  const perimetre = typeof doc.perimetre === 'string' && doc.perimetre
    ? el('li', {}, el('span', { class: 'badge badge--info' }, doc.perimetre))
    : null;

  const actions = el('div', { class: 'ds-carte__actions' });

  if (typeof doc.lien === 'string' && doc.lien.trim() !== '') {
    actions.append(
      el('a', {
        class: 'bouton bouton--secondaire bouton--compact',
        href: doc.lien,
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
    // Les six documents sans lien : une mention claire, aucun bouton mort.
    actions.append(
      el('p', { class: 'ds-sans-lien' },
        el('span', { ariaHidden: 'true' }, '✉'),
        'Communiqué sur demande auprès du porteur'),
      el('button', {
        type: 'button',
        class: 'bouton bouton--discret bouton--compact',
        dataset: { action: 'copier-reference' }
      }, 'Copier la référence'));
  }

  const maj = typeof doc.maj === 'string' ? doc.maj : '';

  // Un élément de liste, focalisable par programme seulement : le parcours
  // ↑/↓ y déplace un tabindex glissant, sans imposer d'arrêt de tabulation
  // supplémentaire. Aucun aria-label global : il masquerait le résumé, les
  // métiers et la date de mise à jour.
  const carte = el('li', {
    class: 'carte carte--compacte ds-carte',
    id: 'ds-option-' + id,
    dataset: { id },
    tabIndex: -1
  },
  el('div', { class: 'carte__meta' },
    el('span', { class: 'badge ' + habillage.badge },
      el('span', { class: 'badge__point', ariaHidden: 'true' }),
      typeof doc.type === 'string' ? doc.type : 'Document'),
    reference),
  titre,
  resume,
  el('ul', { class: 'facettes' }, poles, metiers, perimetre),
  el('div', { class: 'carte__pied' },
    el('span', {}, 'Porteur : ' + (doc.porteur || '—')),
    maj ? el('span', {}, 'Mis à jour le ',
      el('time', { datetime: maj }, formaterDate(maj))) : null,
    actions));

  const fiche = { doc, carte, titre, reference, resume, requete: null };
  fiches.set(id, fiche);
  return fiche;
}

/**
 * Réécrit les seuls fragments dépendant de la requête. Si la requête n'a
 * pas changé depuis le dernier rendu de cette carte, il n'y a rien à faire.
 */
function majSurlignage(fiche, requete) {
  if (fiche.requete === requete) return;
  fiche.requete = requete;

  const doc = fiche.doc;
  const titre = typeof doc.titre === 'string' ? doc.titre : '';
  const reference = typeof doc.reference === 'string' ? doc.reference : '';
  const description = typeof doc.description === 'string' ? doc.description : '';

  if (requete.trim() === '') {
    // Cas le plus fréquent au repos : aucun découpage, aucun nœud créé.
    fiche.titre.textContent = titre;
    fiche.reference.textContent = reference;
    fiche.resume.textContent = description;
    return;
  }

  monter(fiche.titre, surlignerVers(surligner(titre, requete)));
  monter(fiche.reference, surlignerVers(surligner(reference, requete)));
  monter(fiche.resume, surlignerVers(surligner(description, requete)));
}

/* -------------------------------------------------------------------------
   9. Actions
   ------------------------------------------------------------------------- */

/** Clic sur un bouton d'une carte de résultat. */
function surActionCarte(evt, bouton) {
  const carte = bouton.closest('[data-id]');
  if (!carte) return;
  const doc = corpus.documents.find((d) => String(d.id) === carte.dataset.id);
  if (!doc) return;

  const action = bouton.dataset.action;

  if (action === 'copier-lien') {
    evt.preventDefault();
    copier(doc.lien, 'Lien copié dans le presse-papiers.');
    return;
  }
  if (action === 'copier-reference') {
    evt.preventDefault();
    copier(doc.reference, 'Référence copiée dans le presse-papiers.');
  }
  // « Ouvrir » est une vraie ancre : on ne lui coupe pas son comportement.
}

/** Clic sur un bouton de la zone de messages (accueil, aucun résultat). */
function surActionMessage(evt, bouton) {
  const action = bouton.dataset.action;

  if (action === 'filtrer-type') {
    etat.facettes.type = new Set([bouton.dataset.valeur]);
    etat.tout = false;
    rendre();
    refs.champ.focus();
    return;
  }
  if (action === 'parcourir-tout') {
    etat.tout = true;
    rendre();
    // `rendre()` remplace le contenu de refs.messages : le bouton cliqué
    // n'existe plus, le focus doit être replacé explicitement.
    refs.champ.focus();
    return;
  }
  if (action === 'appliquer-suggestion') {
    definirRequete(bouton.dataset.valeur);
    refs.champ.focus();
    return;
  }
  if (action === 'retirer-facette') {
    const dimension = bouton.dataset.dimension;
    const valeur = bouton.dataset.valeur;
    const actives = etat.facettes[dimension];
    if (!actives) return;
    actives.delete(valeur);
    rendre();

    // Le bouton cliqué vient d'être détruit par le rendu. On vise la puce
    // de facette correspondante, qui lui survit ; à défaut, le champ.
    const equivalent = refs.facettes.get(dimension + '|' + valeur);
    const visible = equivalent && !equivalent.disabled && equivalent.isConnected
      && !(equivalent.elementListe && equivalent.elementListe.hidden);
    if (visible) equivalent.focus();
    else refs.champ.focus();
    return;
  }
  if (action === 'tout-effacer') {
    toutEffacer();
    return;
  }
  if (action === 'proposer') {
    ouvrirModaleProposition(bouton);
  }
}

/** Copie un texte, avec retour visuel explicite dans les deux cas. */
function copier(texte, messageSucces) {
  const valeur = typeof texte === 'string' ? texte.trim() : '';
  if (valeur === '') {
    toast('Rien à copier pour ce document.', 'alerte');
    return;
  }
  copierTexte(valeur).then((ok) => {
    if (ok) toast(messageSucces, 'succes');
    else toast('La copie a échoué. Sélectionnez le texte puis copiez-le manuellement.', 'critique');
  });
}

/** Active ou désactive une valeur de facette. */
function basculerFacette(dimension, valeur) {
  const actives = etat.facettes[dimension];
  if (!actives) return;
  if (actives.has(valeur)) actives.delete(valeur);
  else actives.add(valeur);
  etat.tout = false;
  rendre();
}

/** Remet la page à zéro : requête, facettes, mode parcours. */
function toutEffacer() {
  annulerFrappe();
  etat.requete = '';
  refs.champ.value = '';
  for (const dimension of DIMENSIONS) etat.facettes[dimension.cle].clear();
  etat.tout = false;
  rendre();
  refs.champ.focus();
}

/** Fixe la requête depuis le code (suggestion, effacement). */
function definirRequete(texte) {
  // Une frappe en attente lirait de nouveau le champ : on la jette.
  annulerFrappe();
  etat.requete = typeof texte === 'string' ? texte : '';
  refs.champ.value = etat.requete;
  rendre();
}

/* -------------------------------------------------------------------------
   10. Clavier : parcours des résultats depuis le champ de recherche
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
  toast('« ' + doc.titre + ' » est communiqué sur demande auprès de '
    + (doc.porteur || 'son porteur') + '.', 'info');
}

/** Touches gérées depuis le champ de recherche. */
function surToucheChamp(evt) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  switch (evt.key) {
    case 'ArrowDown':
      evt.preventDefault();
      // Le focus suit la carte courante : c'est lui qui porte désormais
      // l'information, faute de motif combobox.
      definirActif(etat.actif + 1, true, true);
      break;
    case 'ArrowUp':
      evt.preventDefault();
      definirActif(etat.actif - 1, true, true);
      break;
    case 'Home':
      if (etat.actif < 0) return;      // sinon on empêche le retour au début du texte
      evt.preventDefault();
      definirActif(0, true, true);
      break;
    case 'End':
      if (etat.actif < 0) return;
      evt.preventDefault();
      definirActif(Math.min(etat.affiches.length, LIMITE_AFFICHAGE) - 1, true, true);
      break;
    case 'Enter':
      evt.preventDefault();
      ouvrirCourant();
      break;
    case 'Escape':
      // Échap efface la requête ; si elle est déjà vide, il lève ce qui
      // reste (facettes, parcours) plutôt que de ne rien faire.
      evt.preventDefault();
      if (etat.requete !== '') definirRequete('');
      else if (auMoinsUneFacette() || etat.tout) toutEffacer();
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
    if (etat.requete === '' && !auMoinsUneFacette() && !etat.tout) return;
    evt.preventDefault();
    toutEffacer();
  }
}

/* -------------------------------------------------------------------------
   11. Annonce aux lecteurs d'écran

   Une seule annonce, anti-rebondie : sans cela, chaque caractère saisi
   déclencherait une interruption vocale.
   ------------------------------------------------------------------------- */

const annoncerResultats = debounce(() => {
  const nombre = etat.affiches.length;
  if (etat.requete.trim() === '' && !auMoinsUneFacette() && !etat.tout) {
    annoncer('Accueil de la recherche, ' + corpus.documents.length + ' documents référencés.');
    return;
  }
  if (nombre === 0) {
    annoncer('Aucun résultat.');
    return;
  }
  annoncer(nombre + ' ' + pluriel(nombre, 'résultat', 'résultats') + '.');
}, DELAI_ANNONCE);

/* -------------------------------------------------------------------------
   12. Propositions locales (aucun envoi réseau)
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
    corpus.valeurs.type.map((type) => el('option', { value: type }, type)));

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
      'Facultatif. Laissez vide si le document est communiqué sur demande.')),
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

/** Ouvre la modale « Proposer un document ». */
function ouvrirModaleProposition(declencheur) {
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
  champs.formulaire.addEventListener('submit', () => { if (valider()) instance.fermer('action'); });

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
        ? el('p', { class: 'ds-carte__resume' }, proposition.remarque)
        : null,
      el('div', { class: 'carte__pied' },
        el('span', {}, 'Ajoutée le ', el('time',
          { datetime: proposition.cree }, formaterDate(proposition.cree))),
        el('div', { class: 'ds-carte__actions' },
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
        }
      }
    ]
  });
}

/* -------------------------------------------------------------------------
   13. Démarrage
   ------------------------------------------------------------------------- */

function demarrer() {
  initTheme();
  initNav('docsearch');

  refs.champ = document.getElementById('ds-champ');
  refs.zone = document.getElementById('ds-zone');
  refs.propositionsSection = document.getElementById('ds-propositions');
  refs.propositionsListe = document.getElementById('ds-propositions-liste');

  if (!refs.champ || !refs.zone) return;

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

  // Champ focalisé dès l'arrivée : c'est la raison d'être de la page.
  refs.champ.focus();
  if (refs.champ.value) refs.champ.select();

  // Recherche instantanée, anti-rebondie sous le seuil de perception.
  const surFrappe = debounce(() => {
    etat.requete = refs.champ.value;
    etat.tout = false;
    rendre();
  }, DELAI_FRAPPE);

  annulerFrappe = () => surFrappe.annuler();

  refs.champ.addEventListener('input', surFrappe);
  refs.champ.addEventListener('keydown', surToucheChamp);
  document.addEventListener('keydown', surToucheDocument);

  deleguer(document, '[data-action="effacer-requete"]', 'click', () => {
    definirRequete('');
    refs.champ.focus();
  });

  avecEtat(
    refs.zone,
    () => chargerDonnees('documents'),
    (donnees, cible) => {
      construireInterface(donnees, cible);

      // L'état complet n'est restauré qu'ici : les valeurs de facettes de
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
    rendre();
  });
}

demarrer();
