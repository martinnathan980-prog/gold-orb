/* =========================================================================
   ETII Hub — Module de la base de connaissances (SPEC.md §4.5)

   C'est une page TRANSVERSE : un seul gabarit, partagé par le service et
   par ses trois pôles, filtré par le pôle actif. Le pôle voyage dans le
   hash de l'URL — `faq.html#pole=ETIIA` — et « ETII » désigne le niveau
   service, tous pôles confondus.

   Six responsabilités, et rien d'autre :

     1. Démarrer le thème et marquer, dans la navigation principale, le
        lien du PÔLE ACTIF (celui du tableau de bord si le pôle est ETII).
     2. Charger faq.json et en rendre les trois états — chargement, erreur,
        vide — via avecEtat() de data.js.
     3. Classer les questions par pertinence avec le moteur commun
        (search.js) : question en poids fort, mots-clés et catégorie en
        poids moyen, réponse en poids faible. Les correspondances sont
        surlignées via surligner() + surlignerVers().
     4. Filtrer par PÔLE et par CATÉGORIE, en puces de facette avec
        compteur. Les deux filtres se combinent, et chaque compteur est
        calculé en ignorant la dimension qu'il chiffre mais en tenant
        compte de l'autre : les deux séries de compteurs se recalculent
        donc l'une en fonction de l'autre.
     5. Afficher, pour chaque question, son pôle d'origine par une
        pastille ÉTIQUETÉE — jamais par la seule couleur — et proposer un
        état vide explicite quand un pôle n'a aucune question.
     6. Recueillir les questions sans réponse : la modale « Poser la
        question » les enregistre LOCALEMENT (stockage de ui.js) et les
        affiche dans « Vos questions en attente », avec suppression.

   Ce que cette page ne fait PAS, et ne doit jamais refaire :
   l'ancienne version envoyait la question à une adresse interne codée en
   dur. Il n'y a ici aucun envoi réseau, aucun `mailto:`, aucune adresse
   e-mail — le seul accès distant du module est le fetch de faq.json, qui
   passe par data.js (SPEC §0 et §4.5).

   Tout le DOM produit ici passe par el() / frag() / monter() : le texte
   est inséré en textContent, jamais en innerHTML, et aucun gestionnaire
   n'est écrit en attribut HTML (SPEC §8).
   ========================================================================= */

import {
  el, frag, monter, vider, deleguer, surlignerVers,
  ouvrirModale, toast, annoncer, debounce,
  etatUrl, stockage, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';

import { creerIndex, rechercher, surligner, suggerer } from './search.js';

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/*
   Pondération de l'index (SPEC §5). Le champ de poids le plus fort fait
   office de « titre » pour le moteur : c'est lui qui porte les bonus
   « la requête commence le titre » et « la requête est le titre ». Ici
   c'est l'intitulé de la question, ce qui est exactement l'intention.
*/
const CHAMPS_INDEXES = [
  { nom: 'question',  poids: 10 },  // fort
  { nom: 'motsCles',  poids: 5 },   // moyen
  { nom: 'categorie', poids: 5 },   // moyen
  { nom: 'reponse',   poids: 1 }    // faible
];

/*
   Les quatre périmètres de l'accord d'équipe, dans l'ordre : le service
   puis ses trois pôles. Le libellé et la métaphore sont de la matière
   éditoriale, pas de la donnée — ils vivent ici, pas dans un JSON. La
   couleur, elle, est un jeton de tokens.css, rattaché au code du pôle par
   le <style> de la page : jamais une valeur brute écrite en JavaScript.
*/
const POLES = [
  { cle: 'ETII',  libelle: 'Tout le service', metaphore: 'Les quatre périmètres réunis' },
  { cle: 'ETIIA', libelle: 'ETIIA', metaphore: 'Squelette & ADN' },
  { cle: 'ETIIE', libelle: 'ETIIE', metaphore: 'Système nerveux' },
  { cle: 'ETIII', libelle: 'ETIII', metaphore: 'Structure & harnais' }
];

/** Les seuls codes admis dans le hash. Toute autre valeur retombe sur ETII. */
const CODES_POLE = POLES.map((pole) => pole.cle);

/** Le niveau service : « tout le service », et le repli de toute erreur. */
const POLE_SERVICE = 'ETII';

/** Page d'espace correspondant à chaque pôle, pour marquer la navigation. */
const PAGE_DE_POLE = {
  ETII: 'index.html',
  ETIIA: 'etiia.html',
  ETIIE: 'etiie.html',
  ETIII: 'etiii.html'
};

/** Les trois autres pages transverses, pour la sous-navigation. */
const PAGES_TRANSVERSES = [
  { page: 'communication.html', libelle: 'Communication' },
  { page: 'reunions.html', libelle: 'Réunions' },
  { page: 'organigramme.html', libelle: 'Organigramme' }
];

/** Clés sous lesquelles l'état est écrit dans le hash de l'URL. */
const CLE_POLE = 'pole';
const CLE_REQUETE = 'q';
const CLE_CATEGORIE = 'cat';
const CLE_QUESTION = 'question';

/** Clé de stockage local des questions posées et non encore traitées. */
const CLE_ATTENTE = 'faq.questions-en-attente';

/** Délai de regroupement des frappes, en millisecondes. */
const DELAI_FRAPPE = 120;

/** Délai avant écriture de l'URL : on n'empile pas une entrée par frappe. */
const DELAI_URL = 260;

/** Délai avant annonce du nombre de résultats, pour ne pas hacher la voix. */
const DELAI_ANNONCE = 500;

/** Nombre de gabarits d'option affichés pendant le chargement. */
const SQUELETTES_LISTE = 4;

/** Longueur maximale d'une question posée : une question, pas un rapport. */
const LONGUEUR_MAX_QUESTION = 600;

/* -------------------------------------------------------------------------
   2. État du module
   ------------------------------------------------------------------------- */

/** Corpus et index, construits une seule fois au premier rendu réussi. */
const corpus = {
  questions: [],
  index: null,
  categories: []
};

/** État courant de l'interface, reflété dans le hash de l'URL. */
const etat = {
  /** Pôle actif, toujours l'un des quatre codes admis. */
  pole: POLE_SERVICE,
  requete: '',
  categories: new Set(),
  idSelection: null,
  /** Questions réellement affichées, déjà classées par pertinence. */
  affichees: []
};

/** Références vers les nœuds durables de la page. */
const refs = {
  zone: null,
  sousNav: null,
  champ: null,
  compteur: null,
  agencement: null,
  liste: null,
  detail: null,
  messages: null,
  poles: new Map(),         // code de pôle -> { bouton, compteur }
  facettes: new Map(),      // catégorie -> { bouton, compteur }
  attenteSection: null,
  attenteListe: null
};

/** Identifiant de question -> élément <li role="option"> correspondant. */
const optionsParId = new Map();

/** Questions posées localement, les plus récentes en tête. */
let enAttente = [];

/** Empreinte du volet de réponse déjà peint (sélection + surlignage). */
let detailPeint = null;

/** Identifiant de la question déjà peinte, pour ne pas rejouer le fondu. */
let detailIdPeint = null;

/* -------------------------------------------------------------------------
   3. Démarrage
   ------------------------------------------------------------------------- */

/*
   Le démarrage est une FONCTION, appelée à la toute fin du module et non
   ici : les `const` déclarés plus bas (ecrireUrl, annoncerResultats,
   FORMAT_DATE) ne sont initialisés qu'à leur ligne de déclaration, et
   rendreEnAttente() les atteint dès le premier affichage. Exécuter le
   démarrage en tête du fichier les prendrait dans leur zone morte
   temporelle et casserait la page au chargement.
*/

/** Amorce la page : thème, navigation, questions locales, écouteurs. */
function demarrerPage() {
  initTheme();

  refs.zone = document.getElementById('zone-faq');
  refs.sousNav = document.getElementById('faq-sous-nav');
  refs.attenteSection = document.getElementById('faq-attente');
  refs.attenteListe = document.getElementById('faq-attente-liste');

  /* Le pôle est connu avant même les données : la navigation principale et
     la sous-navigation sont donc justes dès la première image, y compris
     si faq.json est introuvable. */
  etat.pole = poleDepuisEtat(etatUrl.lire());
  majNavigation();

  /* Les questions locales sont indépendantes de faq.json : elles
     s'affichent même si le fichier de données est introuvable ou
     invalide. */
  enAttente = lireEnAttente();
  rendreEnAttente();

  brancherDelegations();
  brancherRaccourciGlobal();

  /* Enregistré UNE seule fois, hors du rendu : un clic sur « Réessayer »
     relance le rendu, il ne doit pas empiler les écouteurs.
     `replaceState` ne déclenche pas hashchange, donc seules les vraies
     navigations — retour arrière, lien collé — arrivent ici. */
  etatUrl.ecouter(surNavigationHash);

  demarrer();
}

/**
 * Lance le cycle chargement -> succès | vide | erreur sur la zone de page.
 * avecEtat() ne rejette jamais : quelle que soit l'issue, la page reste
 * navigable et l'erreur est lisible et actionnable.
 */
function demarrer() {
  avecEtat(
    refs.zone,

    /* Fabrique de promesse, et non promesse : le bouton « Réessayer » de
       l'état d'erreur peut ainsi relancer un vrai chargement. */
    () => chargerDonnees('faq').then((brut) => verifierForme(brut, {
      questions: {
        type: 'tableau',
        elements: { id: 'chaine', question: 'chaine', reponse: 'chaine' }
      }
    }, 'faq.json')),

    rendre,

    {
      squelette: squeletteDeuxVolets,
      texteChargement: 'Chargement des questions fréquentes…',
      titreErreur: 'Base de connaissances indisponible',
      titreVide: 'Aucune question publiée',
      texteVide: 'La base de connaissances ne contient encore aucune '
        + 'question. Vous pouvez néanmoins poser la vôtre : elle sera '
        + 'conservée dans ce navigateur.',
      estVide: (brut) => !brut || !Array.isArray(brut.questions)
        || brut.questions.filter(estQuestion).length === 0
    }
  );
}

/* -------------------------------------------------------------------------
   4. État de chargement
   ------------------------------------------------------------------------- */

/**
 * Gabarit gris reprenant la disposition en deux volets : la page ne saute
 * pas au moment où les vraies données arrivent. Purement décoratif, donc
 * entièrement masqué aux lecteurs d'écran — avecEtat() ajoute par ailleurs
 * un texte de statut annoncé, et aria-busy sur le conteneur.
 *
 * @param {Element} conteneur
 */
function squeletteDeuxVolets(conteneur) {
  const colonne = [];
  for (let i = 0; i < SQUELETTES_LISTE; i += 1) {
    colonne.push(
      el('div', { class: 'carte carte--compacte squelette-groupe' },
        el('span', { class: 'squelette squelette--ligne squelette--titre' }),
        el('span', { class: 'squelette squelette--ligne squelette--moyen' })
      )
    );
  }

  monter(conteneur,
    el('div', { class: 'faq', 'aria-hidden': 'true' },
      el('div', { class: 'faq__volet pile pile--serree' }, colonne),
      el('div', { class: 'carte squelette-groupe' },
        el('span', { class: 'squelette squelette--ligne squelette--court' }),
        el('span', { class: 'squelette squelette--ligne squelette--titre' }),
        el('span', { class: 'squelette squelette--bloc' })
      )
    )
  );
}

/* -------------------------------------------------------------------------
   5. Rendu principal
   ------------------------------------------------------------------------- */

/**
 * Construit le corpus, l'index, puis la structure durable de la page :
 * barre de recherche, facettes de catégorie, et les deux volets.
 *
 * @param {object} donnees    contenu de faq.json
 * @param {Element} conteneur zone de page, déjà vidée par avecEtat()
 */
function rendre(donnees, conteneur) {
  corpus.questions = donnees.questions.filter(estQuestion);

  /* Index construit une fois pour toutes : la frappe ne fait plus que le
     consulter (SPEC §5). */
  corpus.index = creerIndex(corpus.questions, CHAMPS_INDEXES);

  /* Catégories réellement présentes, triées de façon déterministe : jamais
     l'ordre d'apparition dans le fichier. */
  corpus.categories = Array.from(new Set(
    corpus.questions
      .map((question) => texteSimple(question.categorie))
      .filter((valeur) => valeur !== '')
  )).sort((a, b) => a.localeCompare(b, 'fr'));

  /* L'état vient de l'URL : un lien collé restitue requête, filtres et
     question sélectionnée. */
  lireUrl();
  majNavigation();

  optionsParId.clear();
  refs.poles.clear();
  refs.facettes.clear();
  detailPeint = null;
  detailIdPeint = null;

  monter(conteneur,
    /* Le sélecteur de pôle est en tête : c'est lui qui fixe le périmètre
       dans lequel la recherche et les catégories travaillent ensuite. */
    construireSelecteurPoles(),
    construireBarre(),
    corpus.categories.length > 0 ? construireFacettes() : null,
    construireMessages(),
    construireAgencement()
  );

  appliquer();
}

/**
 * Les quatre puces de facette « Tout le service / ETIIA / ETIIE / ETIII »,
 * chacune avec le nombre de questions correspondantes.
 *
 * Ce sont des <button aria-pressed>, jamais des <div> : l'état est donc
 * annoncé aux lecteurs d'écran, et la puce est actionnable au clavier
 * comme à la souris. Aucune puce n'est jamais désactivée : un pôle à zéro
 * question reste sélectionnable et affiche alors son état vide, qui sait
 * proposer le retour à tout le service.
 *
 * @returns {HTMLElement}
 */
function construireSelecteurPoles() {
  const puces = POLES.map((pole) => {
    const compteur = el('span', { class: 'facette__compteur' }, '0');

    const bouton = el('button', {
      class: 'facette',
      type: 'button',
      'aria-pressed': 'false',
      dataset: { pole: pole.cle }
    },
      el('span', { class: 'facette__marque', 'aria-hidden': 'true' }, '✓'),
      /* Point teinté DÉCORATIF : le libellé qui suit porte seul le sens. */
      el('span', { class: 'pole-point', 'aria-hidden': 'true' }),
      el('span', null, pole.libelle),
      compteur
    );

    refs.poles.set(pole.cle, { bouton: bouton, compteur: compteur });
    return el('li', null, bouton);
  });

  return el('section', {
    class: 'pile pile--serree sans-impression',
    'aria-labelledby': 'faq-titre-poles'
  },
    el('h2', { class: 'faq__titre-section', id: 'faq-titre-poles' },
      'Périmètre affiché'),
    el('ul', { class: 'facettes' }, puces)
  );
}

/**
 * Barre de recherche : champ, compteur de résultats et accès permanent à
 * « Poser la question ».
 *
 * @returns {HTMLElement}
 */
function construireBarre() {
  const surFrappe = debounce(() => {
    /* Changer la requête change le classement : la sélection courante
       n'est plus forcément pertinente, appliquer() la réévalue. */
    appliquer();
  }, DELAI_FRAPPE);

  refs.champ = el('input', {
    class: 'recherche__champ',
    id: 'faq-recherche',
    type: 'search',
    /* `placeholder` est requis par la règle :not(:placeholder-shown) de
       components.css, qui fait apparaître le bouton d'effacement. */
    placeholder: 'Corrosion, validation, tolérance…',
    autocomplete: 'off',
    autocapitalize: 'none',
    spellcheck: 'false',
    enterkeyhint: 'search',
    value: etat.requete,
    'aria-describedby': 'faq-recherche-aide',
    onInput: (evt) => {
      etat.requete = texteSimple(evt.target.value);
      surFrappe();
    },
    onKeyDown: surClavierChamp
  });

  /* Compteur purement visuel : l'annonce aux lecteurs d'écran passe par la
     région unique d'annoncer(), différée — sans quoi chaque frappe serait
     énoncée deux fois. */
  refs.compteur = el('p', {
    class: 'texte-sm texte-doux sans-marge',
    id: 'faq-compteur'
  });

  return el('div', { class: 'faq__barre pile pile--serree sans-impression' },

    el('label', { class: 'visuellement-cache', for: 'faq-recherche' },
      'Rechercher une question dans la base de connaissances'),

    el('div', { class: 'recherche recherche--proeminente' },
      el('span', { class: 'recherche__icone', 'aria-hidden': 'true' }, '⌕'),
      refs.champ,
      el('kbd', { class: 'recherche__raccourci', 'aria-hidden': 'true' }, '/'),
      el('button', {
        class: 'bouton bouton--discret bouton--icone bouton--rond recherche__effacer',
        type: 'button',
        'aria-label': 'Effacer la recherche',
        dataset: { action: 'effacer-recherche' }
      }, el('span', { 'aria-hidden': 'true' }, '×'))
    ),

    el('p', { class: 'champ__aide', id: 'faq-recherche-aide' },
      'La recherche porte sur l’intitulé, les mots-clés, la catégorie et '
      + 'le texte de la réponse, et tolère les fautes de frappe.'),

    el('div', { class: 'rangee rangee--serree rangee--entre' },
      refs.compteur,
      el('button', {
        class: 'bouton bouton--secondaire bouton--compact',
        type: 'button',
        dataset: { action: 'poser' }
      }, 'Poser la question')
    )
  );
}

/**
 * Puces de facette par catégorie. Ce sont des <button aria-pressed>, dont
 * l'état est lu sur l'attribut ARIA : l'information visuelle et
 * l'information accessible ont une source unique.
 *
 * @returns {HTMLElement}
 */
function construireFacettes() {
  const puces = corpus.categories.map((categorie) => {
    const compteur = el('span', { class: 'facette__compteur' }, '0');

    const bouton = el('button', {
      class: 'facette',
      type: 'button',
      'aria-pressed': 'false',
      dataset: { categorie: categorie }
    },
      el('span', { class: 'facette__marque', 'aria-hidden': 'true' }, '✓'),
      el('span', null, categorie),
      compteur
    );

    refs.facettes.set(categorie, { bouton: bouton, compteur: compteur });
    return el('li', null, bouton);
  });

  return el('div', {
    class: 'pile pile--serree',
    role: 'group',
    'aria-labelledby': 'faq-titre-categories'
  },
    el('h2', { class: 'faq__titre-section', id: 'faq-titre-categories' },
      'Catégories'),
    el('ul', { class: 'facettes' }, puces)
  );
}

/**
 * Conteneur des messages d'absence de résultat. Vide et masqué tant que la
 * recherche renvoie quelque chose.
 *
 * @returns {HTMLElement}
 */
function construireMessages() {
  refs.messages = el('div', { id: 'faq-messages', hidden: true });
  return refs.messages;
}

/**
 * Les deux volets : liste d'options à gauche, réponse à droite.
 *
 * @returns {HTMLElement}
 */
function construireAgencement() {
  refs.liste = el('ul', {
    class: 'faq__options',
    role: 'listbox',
    id: 'faq-liste',
    'aria-labelledby': 'faq-titre-liste',
    /* Un seul écouteur pour toute la liste : l'événement remonte depuis
       l'option qui a le focus. */
    onKeyDown: surClavierListe
  });

  /* Région nommée, focalisable par programme seulement : la touche Entrée
     y emmène depuis la liste, mais elle reste hors de l'ordre de
     tabulation. Volontairement PAS de aria-live : le contenu se réécrit à
     chaque frappe (le surlignage suit la requête), et une région vivante
     ferait relire la réponse entière à chaque fois. Le parcours de la
     listbox énonce déjà l'intitulé de chaque option. */
  refs.detail = el('section', {
    class: 'faq__volet faq__detail carte carte--ample',
    id: 'faq-detail',
    tabindex: '-1',
    'aria-label': 'Réponse à la question sélectionnée'
  });

  refs.agencement = el('div', { class: 'faq' },
    el('div', { class: 'faq__volet faq__liste pile pile--serree' },
      el('h2', { class: 'faq__titre-section', id: 'faq-titre-liste' },
        'Questions'),
      refs.liste
    ),
    refs.detail
  );

  return refs.agencement;
}

/* -------------------------------------------------------------------------
   6. Traduction de l'état en affichage
   ------------------------------------------------------------------------- */

/**
 * Recalcule tout à partir de `etat` : classement, compteurs de facettes,
 * liste, réponse, messages, URL et annonce. C'est le seul point d'entrée
 * du rendu incrémental — aucun autre chemin ne peint l'interface.
 */
function appliquer() {
  if (!corpus.index) return;

  /* Classement complet, AVANT tout filtrage : c'est ce résultat qui sert
     de base aux deux séries de compteurs. */
  const base = rechercher(corpus.index, etat.requete);

  /* Chaque compteur ignore la dimension qu'il chiffre, mais tient compte
     de l'autre : les puces de pôle se recalculent selon les catégories
     actives, les puces de catégorie selon le pôle actif. C'est ce qui fait
     que les deux filtres se combinent honnêtement — un compteur affiché
     est toujours le nombre de questions que la puce donnerait réellement
     si on la pressait. */
  majCompteursPoles(base.filter((resultat) => correspondCategories(resultat.doc)));
  majCompteursFacettes(base.filter((resultat) => correspondPole(resultat.doc)));

  etat.affichees = base
    .filter((resultat) => correspondPole(resultat.doc)
      && correspondCategories(resultat.doc))
    .map((resultat) => resultat.doc);

  /* La sélection survit tant qu'elle reste affichée ; sinon on retombe sur
     la question la mieux classée. */
  if (!etat.affichees.some((question) => question.id === etat.idSelection)) {
    etat.idSelection = etat.affichees.length ? etat.affichees[0].id : null;
  }

  rendreListe();
  rendreDetail();
  rendreEtatRecherche();

  ecrireUrl();
  annoncerResultats();
}

/**
 * Compteurs des quatre puces de pôle : nombre de questions que chacune
 * donnerait si on la pressait, les catégories actives restant en place.
 * « Tout le service » montre tout ; un pôle ne montre que ses entrées.
 *
 * @param {Array<{doc:object}>} base résultats classés, filtrés par
 *        catégorie mais PAS par pôle
 */
function majCompteursPoles(base) {
  const comptes = new Map();
  for (const resultat of base) {
    const code = poleDe(resultat.doc);
    comptes.set(code, (comptes.get(code) || 0) + 1);
  }

  for (const [code, puce] of refs.poles) {
    const nombre = code === POLE_SERVICE ? base.length : (comptes.get(code) || 0);
    const actif = code === etat.pole;

    if (puce.compteur.textContent !== String(nombre)) {
      puce.compteur.textContent = String(nombre);
    }

    puce.bouton.setAttribute('aria-pressed', actif ? 'true' : 'false');
    puce.bouton.setAttribute('aria-label',
      libellePole(code) + ', ' + nombre + ' '
      + pluriel(nombre, 'question', 'questions'));
  }
}

/**
 * Compteur d'une facette de catégorie : nombre de résultats qu'elle
 * donnerait si elle était la seule catégorie active, à pôle inchangé. Il
 * est donc calculé en IGNORANT la dimension « catégorie » elle-même, comme
 * dans toute recherche à facettes digne de ce nom.
 *
 * @param {Array<{doc:object}>} base résultats classés, filtrés par pôle
 *        mais PAS par catégorie
 */
function majCompteursFacettes(base) {
  const comptes = new Map();
  for (const resultat of base) {
    const categorie = texteSimple(resultat.doc.categorie);
    if (categorie === '') continue;
    comptes.set(categorie, (comptes.get(categorie) || 0) + 1);
  }

  for (const [categorie, puce] of refs.facettes) {
    const nombre = comptes.get(categorie) || 0;
    const active = etat.categories.has(categorie);

    if (puce.compteur.textContent !== String(nombre)) {
      puce.compteur.textContent = String(nombre);
    }

    puce.bouton.setAttribute('aria-pressed', active ? 'true' : 'false');
    puce.bouton.setAttribute('aria-label',
      'Catégorie ' + categorie + ', ' + nombre + ' '
      + pluriel(nombre, 'question', 'questions'));

    /* Une facette sans résultat est désactivée, pas retirée — sauf si elle
       est active : il faut toujours pouvoir la relâcher. */
    puce.bouton.disabled = nombre === 0 && !active;
  }
}

/** La question satisfait-elle les catégories actives ? */
function correspondCategories(question) {
  if (etat.categories.size === 0) return true;
  return etat.categories.has(texteSimple(question.categorie));
}

/**
 * La question appartient-elle au périmètre actif ? Au niveau service, tout
 * passe ; sur un pôle, seules ses propres entrées.
 *
 * @param {object} question
 * @returns {boolean}
 */
function correspondPole(question) {
  if (etat.pole === POLE_SERVICE) return true;
  return poleDe(question) === etat.pole;
}

/**
 * Reconstruit la liste d'options. Chaque option est une vraie option de
 * listbox à tabulation glissante : une seule est dans l'ordre de
 * tabulation, les flèches déplacent le focus et la sélection.
 */
function rendreListe() {
  optionsParId.clear();

  const options = etat.affichees.map((question) => {
    const actif = question.id === etat.idSelection;

    const option = el('li', {
      class: 'carte carte--compacte faq__option',
      role: 'option',
      id: 'faq-option-' + question.id,
      'aria-selected': actif ? 'true' : 'false',
      tabindex: actif ? '0' : '-1',
      dataset: { id: question.id },
      onClick: () => selectionner(question.id, true)
    },
      el('p', { class: 'carte__meta' },
        pastillePole(question),
        question.categorie
          ? el('span', { class: 'badge badge--neutre' }, question.categorie)
          : null
      ),

      el('p', { class: 'faq__intitule' },
        surlignerVers(surligner(question.question, etat.requete)))
    );

    optionsParId.set(question.id, option);
    return option;
  });

  monter(refs.liste, options);
}

/**
 * Peint le volet de droite à partir de la sélection courante.
 *
 * Deux garde-fous évitent de retravailler le DOM pour rien à la frappe :
 * on ne repeint que si la sélection OU le surlignage ont réellement
 * changé, et le fondu n'est rejoué que lorsque la question change — sinon
 * il clignoterait à chaque caractère saisi.
 */
function rendreDetail() {
  const question = corpus.questions.find((item) => item.id === etat.idSelection);
  /* JSON.stringify sépare sans ambiguïté : aucun séparateur choisi à la
     main ne peut être confondu avec un caractère de la requête. */
  const signature = JSON.stringify([etat.idSelection, etat.requete]);

  if (signature === detailPeint) return;

  const changeDeQuestion = etat.idSelection !== detailIdPeint;
  detailPeint = signature;
  detailIdPeint = etat.idSelection;

  if (!question) {
    monter(refs.detail, el('p', { class: 'texte-faible texte-sm' },
      'Choisissez une question dans la liste pour afficher sa réponse.'));
    return;
  }

  monter(refs.detail, contenuDetail(question, changeDeQuestion));
}

/**
 * Contenu de la réponse : catégorie, intitulé, réponse, puis les mots-clés
 * transformés en rebonds de recherche.
 *
 * @param {object} question
 * @param {boolean} anime  rejouer le fondu (changement de question)
 * @returns {DocumentFragment}
 */
function contenuDetail(question, anime) {
  const motsCles = Array.isArray(question.motsCles)
    ? question.motsCles.map(texteSimple).filter((mot) => mot !== '')
    : [];

  return frag(
    el('div', {
      class: 'faq__contenu pile',
      dataset: { anime: anime ? '' : null }
    },

      el('p', { class: 'carte__meta' },
        pastillePole(question),
        question.categorie
          ? el('span', { class: 'badge badge--accent' }, question.categorie)
          : null
      ),

      el('h2', null, surlignerVers(surligner(question.question, etat.requete))),

      el('p', { class: 'faq__reponse' },
        surlignerVers(surligner(texteSimple(question.reponse), etat.requete))),

      motsCles.length
        ? el('div', { class: 'pile pile--serree' },
          el('h3', { class: 'faq__titre-section' }, 'Mots-clés'),
          el('ul', { class: 'facettes' }, motsCles.map((mot) =>
            el('li', null,
              el('button', {
                class: 'facette facette--compacte',
                type: 'button',
                dataset: { action: 'mot-cle', valeur: mot },
                'aria-label': 'Rechercher « ' + mot + ' »'
              }, mot))))
        )
        : null,

      el('div', { class: 'carte__pied sans-impression' },
        el('p', { class: 'texte-sm texte-doux sans-marge' },
          'Cette réponse ne répond pas tout à fait à votre besoin ?'),
        el('button', {
          class: 'bouton bouton--discret bouton--compact pousse',
          type: 'button',
          dataset: { action: 'poser' }
        }, 'Poser la question')
      )
    )
  );
}

/**
 * Pastille ÉTIQUETÉE du pôle d'origine d'une question.
 *
 * Le point coloré est décoratif ; l'information est portée par le texte
 * qui l'accompagne — « Pôle ETIIA », ou « Service ETII » au niveau
 * service. La couleur ne signale donc jamais seule le pôle (SPEC §1bis).
 *
 * @param {object} question
 * @returns {HTMLElement}
 */
function pastillePole(question) {
  const code = poleDe(question);

  return el('span', {
    class: 'badge badge--pole',
    dataset: { pole: code }
  },
    el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
    (code === POLE_SERVICE ? 'Service ' : 'Pôle ') + code
  );
}

/**
 * Compteur, masquage des volets, et état vide de recherche. Les trois
 * états de la page — chargement, erreur, vide — sont pris en charge par
 * avecEtat() ; celui-ci est le quatrième, propre à la recherche : « la
 * base est bien chargée, mais la requête ne donne rien ».
 */
function rendreEtatRecherche() {
  const aucun = etat.affichees.length === 0;

  refs.compteur.textContent = texteCompteur(etat.affichees.length);
  refs.agencement.hidden = aucun;
  refs.messages.hidden = !aucun;

  if (aucun) monter(refs.messages, blocAucunResultat());
  else vider(refs.messages);
}

/**
 * Bloc « aucun résultat » : suggestion orthographique du moteur, rappel
 * des filtres actifs retirables un à un, et proposition de poser la
 * question.
 *
 * @returns {HTMLElement}
 */
function blocAucunResultat() {
  /* Cas particulier, et le plus fréquent d'un lien collé : le pôle
     demandé n'a AUCUNE question, quoi que l'on cherche. Le dire
     franchement vaut mieux que de laisser croire à une recherche
     infructueuse, et la seule action utile est de revenir au service. */
  if (etat.pole !== POLE_SERVICE && comptePole(etat.pole) === 0) {
    return blocPoleVide();
  }

  const bloc = el('div', { class: 'etat-vide etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '∅'),
    el('p', { class: 'etat-vide__titre' }, 'Aucune question ne correspond'),
    el('p', { class: 'etat-vide__texte' }, texteAucunResultat())
  );

  /* « Vouliez-vous dire… » : proposé par le moteur, jamais deviné ici.
     suggerer() ne s'appelle qu'à zéro résultat, comme son contrat l'exige. */
  const suggestion = etat.requete.trim() === ''
    ? null
    : suggerer(corpus.index, etat.requete);

  if (suggestion) {
    bloc.append(el('p', { class: 'etat-vide__texte' },
      'Vouliez-vous dire ',
      el('button', {
        class: 'bouton bouton--discret bouton--compact',
        type: 'button',
        dataset: { action: 'suggestion', valeur: suggestion }
      }, suggestion),
      ' ?'));
  }

  /* Rappel des filtres actifs — pôle compris — retirables un à un : sans
     lui, un filtre oublié ressemble à une base vide. */
  const actifs = [];

  if (etat.pole !== POLE_SERVICE) {
    actifs.push(el('li', null,
      el('button', {
        class: 'facette facette--compacte',
        type: 'button',
        dataset: { action: 'retirer-pole' },
        'aria-label': 'Revenir à tout le service, en quittant le pôle '
          + etat.pole
      },
        el('span', { class: 'pole-point', 'aria-hidden': 'true' }),
        el('span', null, 'Pôle : ' + etat.pole),
        el('span', { 'aria-hidden': 'true' }, '×')
      )));
  }

  for (const categorie of etat.categories) {
    actifs.push(el('li', null,
      el('button', {
        class: 'facette facette--compacte',
        type: 'button',
        dataset: { action: 'retirer-categorie', valeur: categorie },
        'aria-label': 'Retirer le filtre de catégorie ' + categorie
      },
        el('span', null, 'Catégorie : ' + categorie),
        el('span', { 'aria-hidden': 'true' }, '×')
      )));
  }

  if (actifs.length > 0) {
    bloc.append(
      el('p', { class: 'texte-sm texte-doux sans-marge' }, 'Filtres actifs :'),
      el('ul', {
        class: 'facettes',
        dataset: { pole: etat.pole }
      }, actifs));
  }

  const actions = el('div', { class: 'etat-vide__actions' });

  if (etat.requete !== '' || etat.categories.size > 0
      || etat.pole !== POLE_SERVICE) {
    actions.append(el('button', {
      class: 'bouton bouton--secondaire',
      type: 'button',
      dataset: { action: 'tout-effacer' }
    }, 'Tout effacer'));
  }

  actions.append(el('button', {
    class: 'bouton bouton--principal',
    type: 'button',
    dataset: { action: 'poser' }
  }, 'Poser la question'));

  bloc.append(actions);
  return bloc;
}

/**
 * État vide d'un pôle qui n'a aucune question, quelle que soit la
 * recherche. Explicite, et actionnable : il propose de revenir à tout le
 * service, là où les questions existent.
 *
 * @returns {HTMLElement}
 */
function blocPoleVide() {
  const total = corpus.questions.length;

  return el('div', { class: 'etat-vide etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '∅'),
    el('p', { class: 'etat-vide__titre' },
      'Aucune question pour ' + libellePole(etat.pole)),
    el('p', { class: 'etat-vide__texte' },
      'Le pôle ' + etat.pole + ' — ' + metaphorePole(etat.pole)
      + ' — n’a encore aucune question dans la base. Le service en compte '
      + 'par ailleurs ' + total + ' au total.'),
    el('div', { class: 'etat-vide__actions' },
      el('button', {
        class: 'bouton bouton--principal',
        type: 'button',
        dataset: { action: 'retirer-pole' }
      }, 'Voir tout le service'),
      el('button', {
        class: 'bouton bouton--secondaire',
        type: 'button',
        dataset: { action: 'poser' }
      }, 'Poser la question')
    )
  );
}

/**
 * Nombre de questions d'un périmètre, toutes recherches et catégories
 * confondues.
 *
 * @param {string} code
 * @returns {number}
 */
function comptePole(code) {
  if (code === POLE_SERVICE) return corpus.questions.length;
  return corpus.questions.filter((question) => poleDe(question) === code).length;
}

/** Phrase expliquant pourquoi rien ne s'affiche. */
function texteAucunResultat() {
  const avecRequete = etat.requete.trim() !== '';
  const avecFiltre = etat.categories.size > 0;
  const dans = etat.pole === POLE_SERVICE
    ? ''
    : ' pour le pôle ' + etat.pole;

  if (avecRequete && avecFiltre) {
    return 'Aucune question ne correspond à « ' + etat.requete.trim()
      + ' » dans les catégories sélectionnées' + dans + '.';
  }
  if (avecRequete) {
    return 'Aucune question ne correspond à « ' + etat.requete.trim() + ' »'
      + dans + '.';
  }
  if (avecFiltre) {
    return 'Aucune question dans les catégories sélectionnées' + dans + '.';
  }
  if (dans !== '') {
    return 'Aucune question à afficher' + dans + '.';
  }
  return 'La base de connaissances ne contient aucune question à afficher.';
}

/* -------------------------------------------------------------------------
   7. Sélection
   ------------------------------------------------------------------------- */

/**
 * Sélectionne une question : met à jour la liste, la réponse et l'URL.
 *
 * @param {string} id
 * @param {boolean} focaliser  replacer le focus sur l'option choisie
 */
function selectionner(id, focaliser) {
  if (!optionsParId.has(id)) return;

  if (id !== etat.idSelection) {
    etat.idSelection = id;
    peindreSelection();
    rendreDetail();
    ecrireUrl();
  }

  if (focaliser) {
    const option = optionsParId.get(id);
    if (option) option.focus();
  }
}

/**
 * Applique la sélection aux options, sans toucher ni à l'URL ni au focus.
 * Tabulation glissante : une seule option reste dans l'ordre de
 * tabulation, les autres n'y sont atteignables qu'aux flèches.
 */
function peindreSelection() {
  for (const [cle, option] of optionsParId) {
    const actif = cle === etat.idSelection;
    option.setAttribute('aria-selected', actif ? 'true' : 'false');
    option.setAttribute('tabindex', actif ? '0' : '-1');
  }
}

/* -------------------------------------------------------------------------
   8. Clavier
   ------------------------------------------------------------------------- */

/**
 * Clavier de la listbox, conforme au motif standard :
 *   ↓ / ↑        question suivante / précédente (la sélection suit le focus)
 *   Origine/Fin  première / dernière question
 *   Entrée       confirme et emmène au volet de réponse
 *   Espace       confirme sans quitter la liste
 *
 * @param {KeyboardEvent} evt
 */
function surClavierListe(evt) {
  /* Une combinaison avec une touche de modification appartient au
     navigateur ou au lecteur d'écran, pas à ce composant. */
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  const position = etat.affichees.findIndex(
    (question) => question.id === etat.idSelection);
  if (position < 0) return;

  let cible = null;

  switch (evt.key) {
    case 'ArrowDown':
      cible = Math.min(position + 1, etat.affichees.length - 1);
      break;

    case 'ArrowUp':
      cible = Math.max(position - 1, 0);
      break;

    case 'Home':
      cible = 0;
      break;

    case 'End':
      cible = etat.affichees.length - 1;
      break;

    case 'Enter':
      evt.preventDefault();
      /* La réponse peut être longue : y emmener le focus évite de la
         retraverser à la tabulation depuis le haut de la liste. */
      refs.detail.focus();
      return;

    case ' ':
    case 'Spacebar':
      evt.preventDefault();
      selectionner(etat.idSelection, true);
      return;

    default:
      return;
  }

  evt.preventDefault();
  selectionner(etat.affichees[cible].id, true);
}

/**
 * Clavier du champ de recherche :
 *   Échap    efface la recherche sans quitter le champ
 *   ↓        descend dans la liste des résultats
 *   Entrée   ouvre la réponse la mieux classée
 *
 * @param {KeyboardEvent} evt
 */
function surClavierChamp(evt) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  if (evt.key === 'Escape' && etat.requete !== '') {
    evt.preventDefault();
    effacerRecherche();
    return;
  }

  if (evt.key === 'ArrowDown' && etat.idSelection) {
    evt.preventDefault();
    const option = optionsParId.get(etat.idSelection);
    if (option) option.focus();
    return;
  }

  if (evt.key === 'Enter' && etat.idSelection) {
    evt.preventDefault();
    refs.detail.focus();
  }
}

/**
 * Raccourci global « / » : place le curseur dans le champ de recherche.
 * Ignoré dès que la frappe a lieu dans un champ de saisie — sans quoi il
 * deviendrait impossible d'écrire une barre oblique.
 */
function brancherRaccourciGlobal() {
  document.addEventListener('keydown', (evt) => {
    if (evt.key !== '/' || evt.altKey || evt.ctrlKey || evt.metaKey) return;
    if (!refs.champ || estSaisie(document.activeElement)) return;

    evt.preventDefault();
    refs.champ.focus();
    refs.champ.select();
  });
}

/** L'élément est-il une zone de saisie ? */
function estSaisie(element) {
  if (!element || element.nodeType !== 1) return false;
  const balise = element.tagName;
  if (balise === 'INPUT' || balise === 'TEXTAREA' || balise === 'SELECT') return true;
  return element.isContentEditable === true;
}

/* -------------------------------------------------------------------------
   9. Actions déléguées
   ------------------------------------------------------------------------- */

/**
 * Un seul écouteur par zone durable, plutôt qu'un gestionnaire par nœud
 * recréé à chaque frappe. `#zone-faq` et la liste des questions en attente
 * existent dans le HTML de la page : les écouteurs survivent donc aussi
 * bien au rendu des données qu'à un clic sur « Réessayer ».
 *
 * Aucun gestionnaire n'est construit par concaténation de chaîne : c'est
 * précisément ce qui cassait l'ancienne version (SPEC §6.6).
 */
function brancherDelegations() {
  if (refs.zone) {
    /* Les deux sélecteurs sont disjoints : une puce de pôle porte
       data-pole, une puce de catégorie data-categorie. Aucune ne porte les
       deux, donc aucun clic n'est traité deux fois. */
    deleguer(refs.zone, '.facette[data-pole]', 'click', (evt, bouton) => {
      changerPole(bouton.dataset.pole);
    });

    deleguer(refs.zone, '.facette[data-categorie]', 'click', (evt, bouton) => {
      basculerCategorie(bouton.dataset.categorie);
    });

    deleguer(refs.zone, '[data-action]', 'click', (evt, bouton) => {
      executerAction(bouton.dataset.action, bouton);
    });
  }

  if (refs.attenteListe) {
    deleguer(refs.attenteListe, '[data-action]', 'click', (evt, bouton) => {
      executerAction(bouton.dataset.action, bouton);
    });
  }
}

/**
 * Aiguillage des actions déclarées en `data-action`.
 *
 * @param {string} action
 * @param {Element} bouton  élément déclencheur, pour la restitution du focus
 */
function executerAction(action, bouton) {
  switch (action) {
    case 'poser':
      ouvrirModaleQuestion(bouton);
      break;

    case 'effacer-recherche':
      effacerRecherche();
      break;

    case 'suggestion':
      appliquerRequete(bouton.dataset.valeur || '');
      break;

    case 'mot-cle':
      appliquerRequete(bouton.dataset.valeur || '');
      break;

    case 'retirer-categorie': {
      /* Le bouton qui portait le focus disparaît avec l'état vide : on le
         rend à la puce de facette correspondante, jamais au document nu. */
      const categorie = bouton.dataset.valeur;
      etat.categories.delete(categorie);
      appliquer();
      const puce = refs.facettes.get(categorie);
      if (puce && !puce.bouton.disabled) puce.bouton.focus();
      else if (refs.champ) refs.champ.focus();
      break;
    }

    case 'retirer-pole': {
      /* Le bouton qui portait le focus disparaît avec l'état vide : on le
         rend à la puce « Tout le service », jamais au document nu. */
      changerPole(POLE_SERVICE);
      const puce = refs.poles.get(POLE_SERVICE);
      if (puce) puce.bouton.focus();
      else if (refs.champ) refs.champ.focus();
      break;
    }

    case 'tout-effacer':
      /* Tout, c'est aussi le périmètre : on revient au service entier,
         sans quoi « Tout effacer » laisserait un filtre en place. */
      etat.pole = POLE_SERVICE;
      etat.requete = '';
      etat.categories.clear();
      if (refs.champ) refs.champ.value = '';
      majNavigation();
      appliquer();
      if (refs.champ) refs.champ.focus();
      break;

    case 'supprimer-attente':
      confirmerSuppression(bouton.dataset.id, bouton);
      break;

    default:
      /* Action inconnue : on ne fait rien plutôt que d'échouer bruyamment. */
  }
}

/** Remplace la requête courante, champ compris, puis réapplique. */
function appliquerRequete(valeur) {
  etat.requete = texteSimple(valeur);
  if (refs.champ) {
    refs.champ.value = etat.requete;
    refs.champ.focus();
  }
  appliquer();
}

/** Vide la recherche et rend le focus au champ. */
function effacerRecherche() {
  etat.requete = '';
  if (refs.champ) {
    refs.champ.value = '';
    refs.champ.focus();
  }
  appliquer();
}

/**
 * Change le périmètre affiché. Les catégories actives survivent au
 * changement de pôle : les deux filtres se combinent, l'un ne chasse pas
 * l'autre. Une catégorie devenue introuvable dans le nouveau pôle voit
 * simplement son compteur tomber à zéro — et l'état vide l'explique.
 *
 * @param {string} code
 */
function changerPole(code) {
  const cible = normaliserPole(code);
  if (cible === etat.pole) return;

  etat.pole = cible;
  majNavigation();
  appliquer();
}

/** Active ou désactive une catégorie de filtre. */
function basculerCategorie(categorie) {
  if (typeof categorie !== 'string' || categorie === '') return;

  if (etat.categories.has(categorie)) etat.categories.delete(categorie);
  else etat.categories.add(categorie);

  appliquer();
}

/* -------------------------------------------------------------------------
   10. Questions posées, enregistrées LOCALEMENT
   ------------------------------------------------------------------------- */

/**
 * Ouvre la modale « Poser la question ».
 *
 * La validation n'envoie rien : elle écrit dans le stockage local de
 * ui.js, puis réaffiche la section « Vos questions en attente ». Il n'y a
 * ni requête réseau, ni adresse e-mail, ni `mailto:` — l'adresse interne
 * codée en dur de l'ancienne version a été retirée et ne doit pas revenir
 * (SPEC §0 et §4.5).
 *
 * @param {Element} declencheur  élément auquel rendre le focus à la fermeture
 */
function ouvrirModaleQuestion(declencheur) {
  const idChamp = 'faq-nouvelle-question';

  const erreur = el('span', {
    class: 'champ__erreur',
    id: idChamp + '-erreur',
    role: 'alert',
    hidden: true
  }, 'Merci de saisir votre question avant de l’enregistrer.');

  const zone = el('textarea', {
    class: 'champ__controle',
    id: idChamp,
    rows: 4,
    maxlength: LONGUEUR_MAX_QUESTION,
    /* Pré-remplissage avec la recherche restée sans réponse : la personne
       n'a pas à retaper ce qu'elle vient de chercher. */
    value: etat.requete,
    'aria-describedby': idChamp + '-aide ' + idChamp + '-erreur',
    onInput: () => {
      erreur.hidden = true;
      zone.removeAttribute('aria-invalid');
    }
  });

  /**
   * Enregistre la question si elle est exploitable.
   * @returns {boolean} faux pour laisser la modale ouverte
   */
  function valider() {
    const texte = texteSimple(zone.value);

    if (texte === '') {
      erreur.hidden = false;
      zone.setAttribute('aria-invalid', 'true');
      zone.focus();
      return false;
    }

    enAttente = [{
      id: identifiantLocal(),
      texte: texte.slice(0, LONGUEUR_MAX_QUESTION),
      cree: new Date().toISOString()
    }].concat(enAttente);

    const ecrit = enregistrerEnAttente();
    rendreEnAttente();

    toast(ecrit
      ? 'Question enregistrée dans ce navigateur.'
      : 'Question ajoutée, mais le stockage de ce navigateur est '
        + 'indisponible : elle disparaîtra au rechargement.',
    ecrit ? 'succes' : 'alerte');

    return true;
  }

  const formulaire = el('form', {
    class: 'pile',
    novalidate: true,
    onSubmit: (evt) => {
      evt.preventDefault();
      if (valider()) instance.fermer('action');
    }
  },
    el('p', { class: 'champ' },
      el('label', { class: 'champ__etiquette', for: idChamp },
        'Votre question'),
      zone,
      el('span', { class: 'champ__aide', id: idChamp + '-aide' },
        'Elle est conservée dans ce navigateur uniquement. Aucun envoi, '
        + 'aucun message, aucun destinataire.'),
      erreur
    ),

    /* Bouton de soumission implicite : permet la validation à la touche
       Entrée sans être atteignable à la tabulation — l'action réelle est
       dans le pied de la modale. */
    el('button', { type: 'submit', class: 'visuellement-cache', tabindex: '-1' },
      'Enregistrer')
  );

  const instance = ouvrirModale({
    titre: 'Poser la question',
    declencheur: declencheur,
    contenu: formulaire,
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      { libelle: 'Enregistrer', variante: 'principal', onClick: () => valider() }
    ]
  });
}

/**
 * Suppression d'une question locale : action destructrice, donc confirmée
 * explicitement (SPEC §6.5).
 *
 * @param {string} id
 * @param {Element} declencheur
 */
function confirmerSuppression(id, declencheur) {
  const question = enAttente.find((item) => item.id === id);
  if (!question) return;

  ouvrirModale({
    titre: 'Supprimer cette question ?',
    declencheur: declencheur,
    classe: 'modale--etroite',
    contenu: el('p', null,
      '« ' + question.texte + ' » sera définitivement retirée de vos '
      + 'questions en attente. Cette action est irréversible.'),
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', autofocus: true },
      {
        libelle: 'Supprimer',
        variante: 'danger',
        onClick: () => {
          enAttente = enAttente.filter((item) => item.id !== id);
          enregistrerEnAttente();
          rendreEnAttente();
          toast('Question supprimée.', 'info');
        }
      }
    ]
  });
}

/** Affiche — ou masque — la section « Vos questions en attente ». */
function rendreEnAttente() {
  if (!refs.attenteSection || !refs.attenteListe) return;

  if (enAttente.length === 0) {
    refs.attenteSection.hidden = true;
    vider(refs.attenteListe);
    return;
  }

  refs.attenteSection.hidden = false;

  monter(refs.attenteListe, enAttente.map((question) =>
    el('li', { class: 'carte carte--compacte' },
      el('div', { class: 'carte__entete' },
        el('p', { class: 'faq__attente-texte' }, question.texte),
        el('span', { class: 'badge badge--neutre' }, 'En attente')
      ),
      el('div', { class: 'carte__pied' },
        question.cree
          ? el('span', { class: 'texte-sm texte-doux' },
            'Posée le ',
            el('time', { datetime: question.cree }, formaterDate(question.cree)))
          : el('span', { class: 'texte-sm texte-doux' }, 'Question locale'),
        el('button', {
          class: 'bouton bouton--danger-discret bouton--compact pousse',
          type: 'button',
          dataset: { action: 'supprimer-attente', id: question.id },
          'aria-label': 'Supprimer la question « ' + question.texte + ' »'
        }, 'Supprimer')
      )
    )));
}

/**
 * Relit les questions locales, en écartant tout ce qui n'a pas la forme
 * attendue : une version antérieure ou une édition manuelle du stockage ne
 * doit pas casser la page.
 *
 * @returns {Array<{id:string, texte:string, cree:string}>}
 */
function lireEnAttente() {
  const brut = stockage.lire(CLE_ATTENTE, []);
  if (!Array.isArray(brut)) return [];

  return brut
    .filter((item) => item && typeof item === 'object'
      && typeof item.id === 'string' && item.id !== ''
      && typeof item.texte === 'string' && item.texte.trim() !== '')
    .map((item) => ({
      id: item.id,
      texte: item.texte,
      cree: typeof item.cree === 'string' ? item.cree : ''
    }));
}

/**
 * Enregistre les questions locales.
 * @returns {boolean} vrai si l'écriture a réellement eu lieu
 */
function enregistrerEnAttente() {
  return stockage.ecrire(CLE_ATTENTE, enAttente);
}

/**
 * Identifiant local, sans collision pratique et sans dépendance.
 * @returns {string}
 */
function identifiantLocal() {
  return 'q-' + Date.now().toString(36)
    + '-' + Math.random().toString(36).slice(2, 7);
}

/* -------------------------------------------------------------------------
   11. État dans l'URL
   ------------------------------------------------------------------------- */

/** Lit pôle, requête, catégories et question sélectionnée depuis le hash. */
function lireUrl() {
  const lu = etatUrl.lire();

  etat.pole = poleDepuisEtat(lu);
  etat.requete = texteSimple(lu[CLE_REQUETE]);

  const brut = lu[CLE_CATEGORIE];
  const valeurs = Array.isArray(brut)
    ? brut
    : (typeof brut === 'string' && brut !== '' ? [brut] : []);

  /* Seules les catégories réellement présentes sont retenues : un lien
     ancien ne doit pas produire un filtre fantôme qui vide la page. */
  etat.categories = new Set(
    valeurs.filter((valeur) => corpus.categories.includes(valeur)));

  const id = typeof lu[CLE_QUESTION] === 'string' ? lu[CLE_QUESTION] : '';
  etat.idSelection = id !== '' ? id : null;
}

/* Écriture différée : `replaceState` n'empile pas l'historique, mais rien
   ne sert d'écrire l'URL à chaque frappe. */
const ecrireUrl = debounce(() => {
  etatUrl.ecrire({
    /* Le pôle est toujours écrit, même au niveau service : l'URL dit alors
       explicitement « tout le service », et reste partageable telle quelle. */
    [CLE_POLE]: etat.pole,
    [CLE_REQUETE]: etat.requete,
    [CLE_CATEGORIE]: Array.from(etat.categories),
    [CLE_QUESTION]: etat.idSelection
  });
}, DELAI_URL);

/**
 * Navigation réelle de l'utilisateur : « Précédent », « Suivant », lien
 * collé. `replaceState` ne déclenche pas cet événement, donc aucune boucle
 * de rétroaction n'est possible avec ecrireUrl().
 */
function surNavigationHash() {
  if (!corpus.index) return;

  const avant = signatureEtat();
  lireUrl();
  if (signatureEtat() === avant) return;

  if (refs.champ) refs.champ.value = etat.requete;
  majNavigation();
  appliquer();
}

/** Empreinte compacte de l'état, pour détecter un changement réel. */
function signatureEtat() {
  return etat.pole
    + '|' + etat.requete
    + '|' + Array.from(etat.categories).sort().join(',')
    + '|' + (etat.idSelection || '');
}

/* -------------------------------------------------------------------------
   11bis. Navigation et sous-navigation
   ------------------------------------------------------------------------- */

/**
 * Reporte le pôle actif sur la navigation principale et la
 * sous-navigation.
 *
 * Sur une page transverse, c'est le lien du PÔLE ACTIF qui porte
 * `aria-current="page"` — celui du tableau de bord quand le pôle est
 * « ETII ». initNav() se charge de poser l'attribut sur ce seul lien et de
 * le retirer partout ailleurs : il n'y en a jamais deux.
 */
function majNavigation() {
  initNav(PAGE_DE_POLE[etat.pole] || 'index.html');
  rendreSousNav();
}

/**
 * Sous-navigation vers les trois autres pages transverses, chaque lien
 * portant le pôle actif dans son hash : on change de page sans perdre son
 * périmètre.
 */
function rendreSousNav() {
  if (!refs.sousNav) return;

  refs.sousNav.setAttribute('aria-label',
    'Autres pages — ' + libellePole(etat.pole));

  monter(refs.sousNav,
    el('ul', { class: 'rangee rangee--serree' },
      PAGES_TRANSVERSES.map((entree) => el('li', null,
        el('a', {
          class: 'bouton bouton--secondaire bouton--compact',
          href: entree.page + '#' + CLE_POLE + '=' + encodeURIComponent(etat.pole)
        }, entree.libelle))),
      el('li', null,
        el('a', {
          class: 'bouton bouton--discret bouton--compact',
          href: PAGE_DE_POLE[etat.pole] || 'index.html'
        }, etat.pole === POLE_SERVICE
          ? 'Tableau de bord ETII'
          : 'Espace ' + etat.pole))
    )
  );
}

/* -------------------------------------------------------------------------
   12. Annonces
   ------------------------------------------------------------------------- */

/* Différée et regroupée : à la frappe, seul le dernier état est énoncé. */
const annoncerResultats = debounce(() => {
  const nombre = etat.affichees.length;

  const perimetre = etat.pole === POLE_SERVICE
    ? ''
    : ' pour le pôle ' + etat.pole;

  if (nombre === 0) {
    annoncer('Aucune question ne correspond' + perimetre + '. '
      + (etat.pole === POLE_SERVICE
        ? 'Vous pouvez poser votre question.'
        : 'Revenez à tout le service, ou posez votre question.'));
    return;
  }

  annoncer(nombre + ' ' + pluriel(nombre, 'question trouvée', 'questions trouvées')
    + perimetre
    + '. Utilisez les flèches haut et bas pour parcourir la liste.');
}, DELAI_ANNONCE);

/* -------------------------------------------------------------------------
   13. Petits utilitaires
   ------------------------------------------------------------------------- */

/**
 * Une question exploitable : un objet doté d'un identifiant, d'un intitulé
 * et d'une réponse. Les entrées malformées sont écartées silencieusement
 * plutôt que d'interrompre l'affichage des autres.
 *
 * @param {*} question
 * @returns {boolean}
 */
function estQuestion(question) {
  return !!question && typeof question === 'object'
    && typeof question.id === 'string' && question.id !== ''
    && typeof question.question === 'string' && question.question !== ''
    && typeof question.reponse === 'string';
}

/**
 * Pôle lu dans l'état d'URL. Toute valeur absente ou inconnue retombe sur
 * « ETII », le niveau service, sans erreur ni message (SPEC §1bis).
 *
 * @param {object} lu  résultat de etatUrl.lire()
 * @returns {string}
 */
function poleDepuisEtat(lu) {
  if (!lu || typeof lu !== 'object') return POLE_SERVICE;
  const brut = Array.isArray(lu[CLE_POLE]) ? lu[CLE_POLE][0] : lu[CLE_POLE];
  return normaliserPole(brut);
}

/**
 * Pôle d'origine d'une question. Une question sans pôle, ou dont le pôle
 * est inconnu, appartient au niveau service.
 *
 * @param {object} question
 * @returns {string}
 */
function poleDe(question) {
  return normaliserPole(question ? question.pole : null);
}

/**
 * Ramène n'importe quelle valeur à l'un des quatre codes admis.
 * @param {*} valeur
 * @returns {string}
 */
function normaliserPole(valeur) {
  const code = typeof valeur === 'string' ? valeur.trim().toUpperCase() : '';
  return CODES_POLE.includes(code) ? code : POLE_SERVICE;
}

/** Libellé lisible d'un périmètre, pour les annonces et les aria-label. */
function libellePole(code) {
  const pole = POLES.find((item) => item.cle === code);
  return pole ? pole.libelle : POLE_SERVICE;
}

/** Métaphore d'un pôle, matière éditoriale de l'accord d'équipe. */
function metaphorePole(code) {
  const pole = POLES.find((item) => item.cle === code);
  return pole ? pole.metaphore : '';
}

/** Chaîne nettoyée, quelle que soit la valeur reçue. */
function texteSimple(valeur) {
  return typeof valeur === 'string' ? valeur.trim() : '';
}

/** Accord au pluriel, sans bibliothèque ni table. */
function pluriel(nombre, singulier, pluriels) {
  return nombre > 1 ? pluriels : singulier;
}

/** Libellé du compteur de résultats, périmètre compris. */
function texteCompteur(nombre) {
  const perimetre = etat.pole === POLE_SERVICE
    ? ''
    : ' — pôle ' + etat.pole;

  if (nombre === 0) return 'Aucune question' + perimetre;
  return nombre + ' ' + pluriel(nombre, 'question', 'questions')
    + (etat.requete.trim() !== '' ? ', classées par pertinence' : '')
    + perimetre;
}

/** Formateur de date en français, construit une seule fois. */
const FORMAT_DATE = (function () {
  try {
    return new Intl.DateTimeFormat('fr-FR', {
      day: 'numeric', month: 'long', year: 'numeric'
    });
  } catch (_e) {
    return null;   // moteur sans Intl : on retombera sur la date brute
  }
})();

/**
 * Met une date ISO en forme lisible. En cas de doute, la valeur d'origine
 * est rendue telle quelle : mieux vaut une date brute qu'un « Invalid Date ».
 *
 * @param {string} iso
 * @returns {string}
 */
function formaterDate(iso) {
  if (typeof iso !== 'string' || iso === '') return '';
  if (!FORMAT_DATE) return iso;

  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;

  try {
    return FORMAT_DATE.format(date);
  } catch (_e) {
    return iso;
  }
}

/* -------------------------------------------------------------------------
   14. Amorçage
   Dernière ligne du module : tout ce qui précède est déclaré et initialisé.
   ------------------------------------------------------------------------- */

demarrerPage();
