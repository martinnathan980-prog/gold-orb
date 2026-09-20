/* =========================================================================
   ETII Hub — Module de la page Réunions (SPEC.md §4.3 et §1bis)

   C'est une page TRANSVERSE : un seul gabarit, partagé par le service et
   par ses trois pôles, filtré par le pôle actif. Le pôle voyage dans le
   hash de l'URL — `reunions.html#pole=ETIIA` — et « ETII » désigne le
   niveau service, tous pôles confondus. Toute autre valeur retombe sur
   « ETII » sans erreur.

   Ce module corrige par ailleurs les deux bugs de l'ancienne version
   (SPEC.md §6), et ces correctifs sont conservés intacts :

     BUG 4 — la page ne rendait que les comptes-rendus ; les prochains
             points étaient chargés puis jamais affichés. Ici, DEUX onglets
             réellement fonctionnels sont construits à partir des deux
             tableaux du JSON, chacun avec sa liste, son lecteur, sa
             sélection propre et son état vide.

     BUG 3 — les actions et les décisions existaient dans les données mais
             n'étaient jamais affichées (l'ancien code cherchait des
             marqueurs « ⚡ » / « ✅ » qui n'ont jamais été écrits). Ici,
             chaque compte-rendu rend sa liste d'ACTIONS et sa liste de
             DÉCISIONS, et chaque prochain point rend son OBJECTIF et sa
             liste d'ACTIONS de préparation — dans des blocs visuellement
             distincts du corps du texte, et étiquetés en toutes lettres.

   Responsabilités :
     1. Démarrer le thème et marquer, dans la navigation principale, le
        lien du PÔLE ACTIF (celui du tableau de bord si le pôle est ETII).
     2. Charger reunions.json et en rendre les trois états — chargement,
        erreur, vide — via avecEtat() de data.js.
     3. Offrir un sélecteur de pôle à quatre puces, chacune avec son
        nombre de réunions, et un état vide explicite quand un pôle n'a
        rien inscrit.
     4. Construire les onglets accessibles (tablist / tab / tabpanel,
        flèches, Origine/Fin, une seule tabulation) et les deux volets.
     5. Filtrer la liste de l'onglet courant avec le moteur de search.js
        (creerIndex + rechercher), en surlignant les correspondances.
     6. Refléter dans le hash À LA FOIS le pôle, l'onglet actif, la réunion
        affichée et la requête, et les restaurer au chargement comme au
        retour arrière du navigateur.

   Points de conception notables :

   - Le pôle n'est jamais signalé par la couleur seule : chaque réunion
     porte une pastille ÉTIQUETÉE, où le code du pôle est écrit à côté du
     point teinté, et chaque puce du sélecteur nomme son périmètre.

   - L'index de recherche d'un onglet est construit UNE fois, sur toutes
     ses réunions, et n'est jamais reconstruit : changer de pôle ne fait
     que filtrer les résultats, jamais réindexer.

   - L'impression ne laisse passer que la réunion affichée, par les seuls
     styles @media print de la page : aucune bibliothèque PDF (SPEC §4.3).

   Tout le DOM produit ici passe par el() / frag() / monter() : le texte est
   inséré en textContent, jamais en innerHTML, et aucun gestionnaire n'est
   écrit en attribut HTML (SPEC §8).
   ========================================================================= */

import {
  el, frag, monter, surlignerVers, annoncer, debounce,
  etatUrl, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';

import { creerIndex, rechercher, surligner } from './search.js';

/* -------------------------------------------------------------------------
   1. La structure du service
   ------------------------------------------------------------------------- */

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
  { page: 'organigramme.html', libelle: 'Organigramme' },
  { page: 'faq.html', libelle: 'FAQ' }
];

/* -------------------------------------------------------------------------
   2. Constantes d'affichage
   ------------------------------------------------------------------------- */

/*
   Un seul onglet aujourd'hui — les comptes-rendus : une réunion à venir
   n'a rien à lire. Tout le module boucle sur cette table : en rajouter un
   ne demanderait qu'une entrée de plus, jamais une branche dans le code.

     cle        identifiant court, celui qui part dans le hash de l'URL
     source     clé du tableau correspondant dans reunions.json
     libelle    texte de l'onglet
     champResume nom du champ de synthèse, et son étiquette affichée
     badge      libellé de nature, affiché sur chaque entrée
     etiquetteActions étiquette du bloc d'actions (elle diffère par onglet)
     avecDecisions true si l'onglet porte aussi un bloc de décisions
     ordre      'recent' (du plus récent au plus ancien) ou 'proche'
                (du plus proche au plus lointain)
     nom / noms nom de l'entrée au singulier et au pluriel
*/
const ONGLETS = [
  {
    cle: 'cr',
    source: 'comptesRendus',
    libelle: 'Comptes-rendus',
    champResume: 'synthese',
    etiquetteResume: 'Synthèse',
    badge: 'Compte-rendu',
    etiquetteActions: 'Actions',
    avecDecisions: true,
    ordre: 'recent',
    titreListe: 'Comptes-rendus disponibles',
    nom: 'compte-rendu',
    noms: 'comptes-rendus',
    videTitre: 'Aucun compte-rendu',
    videTexte: 'Aucune réunion passée n’a encore été publiée. Cet onglet '
      + 'se remplira dès le premier compte-rendu diffusé.'
  }
];

/*
   Champs indexés par search.js, du plus fort au plus faible poids. Le champ
   de poids maximal fait office de « titre » pour le moteur (SPEC §5) : il
   porte le bonus « la requête commence le titre ».

   Le moteur n'indexe que des chaînes et des tableaux de chaînes ; les
   sujets, qui sont des objets, sont donc aplatis en amont par
   `documentIndexable()`.
*/
const CHAMPS_INDEXES = [
  { nom: 'titre',     poids: 10 },  // fort
  { nom: 'sujets',    poids: 4 },   // moyen
  { nom: 'actions',   poids: 3 },   // moyen
  { nom: 'decisions', poids: 3 },   // moyen
  { nom: 'lieu',      poids: 2 },   // faible
  { nom: 'resume',    poids: 1 }    // faible
];

/** Clés sous lesquelles l'état de la page est écrit dans le hash. */
const CLE_POLE = 'pole';
const CLE_ONGLET = 'onglet';
const CLE_REUNION = 'reunion';
const CLE_REQUETE = 'q';

/** Nombre de gabarits d'option affichés pendant le chargement. */
const SQUELETTES_LISTE = 4;

/** Délai d'amortissement de la frappe, en millisecondes. */
const DELAI_FRAPPE = 120;

/* -------------------------------------------------------------------------
   3. État du module
   ------------------------------------------------------------------------- */

/**
 * Une « vue » par onglet. Construite au rendu, elle rassemble les données
 * de l'onglet, son index de recherche, ses références DOM et sa sélection
 * propre : changer d'onglet ne perd donc jamais la réunion ouverte dans
 * l'autre.
 *
 * @type {Map<string, object>}
 */
const vues = new Map();

/** Clé de l'onglet actuellement actif. */
let ongletActif = ONGLETS[0].cle;

/** Le pôle actif, toujours l'un des quatre codes admis. */
let poleActif = POLE_SERVICE;

/** Requête de recherche courante, telle que saisie. */
let requete = '';

/** Le champ de recherche, conservé pour la restauration depuis l'URL. */
let champRecherche = null;

/** Nœuds durables de la page, hors des vues d'onglet. */
const refs = {
  zone: null,
  sousNav: null,
  /** Code de pôle -> { bouton, compteur } du sélecteur. */
  facettes: new Map()
};

/* -------------------------------------------------------------------------
   4. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

refs.zone = document.getElementById('zone-reunions');
refs.sousNav = document.getElementById('reunions-sous-nav');

/* Le pôle est connu avant même les données : la navigation et la
   sous-navigation sont donc justes dès la première image, y compris si le
   fichier de réunions est introuvable. */
poleActif = poleDepuisEtat(etatUrl.lire());
majNavigation();

/* Enregistré UNE seule fois, hors du rendu : un clic sur « Réessayer »
   relance le rendu, il ne doit pas empiler les écouteurs. `replaceState`
   ne déclenche pas hashchange, donc seules les vraies navigations — retour
   arrière, lien collé — arrivent ici. */
etatUrl.ecouter(appliquerEtatUrl);

/* Raccourci « / » : il est annoncé par le <kbd> de la barre d'outils, il
   doit donc exister réellement. Enregistré une seule fois, il ne fait rien
   tant que le champ n'est pas construit, et laisse évidemment la barre
   oblique atteindre les champs de saisie. */
document.addEventListener('keydown', function (evt) {
  if (evt.key !== '/' || evt.altKey || evt.ctrlKey || evt.metaKey) return;
  if (!champRecherche) return;

  const cible = evt.target;
  if (cible && typeof cible.closest === 'function'
    && cible.closest('input, textarea, select, [contenteditable="true"]')) return;

  evt.preventDefault();
  champRecherche.focus();
  champRecherche.select();
});

demarrer();

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
    () => chargerDonnees('reunions').then((brut) => verifierForme(brut, {
      comptesRendus: {
        type: 'tableau',
        elements: { id: 'chaine', titre: 'chaine', date: 'chaine' }
      }
    }, 'reunions.json')),

    rendre,

    {
      squelette: squeletteDeuxVolets,
      texteChargement: 'Chargement des réunions du service…',
      titreErreur: 'Réunions indisponibles',
      titreVide: 'Aucune réunion enregistrée',
      texteVide: 'Aucun compte-rendu pour l’instant. '
        + 'Cette page se remplira dès la première réunion publiée.',

      /* Vacuité du FICHIER, tous pôles et tous onglets confondus. Un pôle
         sans réunion n'est pas un fichier vide : il a son propre état
         vide, qui sait proposer le retour à tout le service. */
      estVide: (brut) => reunionsValides(brut, 'comptesRendus').length === 0
    }
  );
}

/* -------------------------------------------------------------------------
   5. État de chargement
   ------------------------------------------------------------------------- */

/**
 * Gabarit gris reprenant la disposition finale — sélecteur, barre d'outils,
 * deux volets : la page ne saute pas au moment où les vraies données
 * arrivent. Purement décoratif, donc entièrement masqué aux lecteurs
 * d'écran — avecEtat() ajoute par ailleurs un texte de statut annoncé, et
 * aria-busy sur le conteneur.
 *
 * @param {Element} conteneur
 */
function squeletteDeuxVolets(conteneur) {
  const options = [];
  for (let i = 0; i < SQUELETTES_LISTE; i += 1) {
    options.push(
      el('div', { class: 'carte carte--compacte squelette-groupe' },
        el('span', { class: 'squelette squelette--ligne squelette--court' }),
        el('span', { class: 'squelette squelette--ligne squelette--titre' }),
        el('span', { class: 'squelette squelette--ligne squelette--moyen' })
      )
    );
  }

  monter(conteneur,
    el('div', { class: 'pile pile--lache', 'aria-hidden': 'true' },
      el('span', { class: 'squelette squelette--ligne squelette--court' }),
      el('span', { class: 'squelette squelette--ligne squelette--moyen' }),
      el('div', { class: 'reunions' },
        el('div', { class: 'reunions__volet pile pile--serree' }, options),
        el('div', { class: 'carte carte--ample squelette-groupe' },
          el('span', { class: 'squelette squelette--ligne squelette--court' }),
          el('span', { class: 'squelette squelette--ligne squelette--titre' }),
          el('span', { class: 'squelette squelette--bloc' })
        )
      )
    )
  );
}

/* -------------------------------------------------------------------------
   6. Rendu principal
   ------------------------------------------------------------------------- */

/**
 * Construit le sélecteur de pôle, la barre d'outils, les deux onglets et
 * leurs panneaux, puis applique l'état demandé par l'URL.
 *
 * @param {object} donnees    contenu de reunions.json
 * @param {Element} conteneur zone de page, déjà vidée par avecEtat()
 */
function rendre(donnees, conteneur) {
  vues.clear();
  refs.facettes.clear();

  /* Chaque onglet reçoit sa vue complète : données triées, index de
     recherche prêt, et tous ses nœuds construits. Rien n'est recalculé à
     la frappe ni au changement de pôle hormis le filtrage lui-même. */
  for (const definition of ONGLETS) {
    vues.set(definition.cle, creerVue(definition, donnees));
  }

  /* État initial lu dans le hash. Il peut avoir changé entre le démarrage
     et l'arrivée des données — un lien collé, par exemple : on le relit.
     Un lien du type `#reunion=cr02` venu d'une autre page suffit à ouvrir
     le bon onglet sur la bonne réunion. */
  const demande = etatUrl.lire();
  poleActif = poleDepuisEtat(demande);
  requete = texteSimple(demande[CLE_REQUETE]);
  ongletActif = resoudreOngletInitial(demande);
  majNavigation();

  const selecteur = construireSelecteurPoles();
  const barre = construireBarreOutils();
  const onglets = construireOnglets();

  /* Les listes sont peuplées AVANT l'insertion dans le document : le
     lecteur est une région live, et une région remplie hors du document
     n'énonce rien. On évite ainsi de faire lire toute une réunion au
     chargement de la page — seuls les changements ultérieurs sont annoncés. */
  appliquerPole(texteSimple(demande[CLE_REUNION]), false);

  monter(conteneur, selecteur, barre, onglets);

  const vue = vueActive();
  const n = vue.affichees.length;
  annoncer(libellePole(poleActif) + ' : ' + n + ' '
    + pluriel(n, 'réunion chargée', 'réunions chargées')
    + ' dans l’onglet ' + vue.definition.libelle + '.');
}

/**
 * Prépare la vue d'un onglet : filtrage des entrées exploitables, tri,
 * index de recherche et conteneurs DOM.
 *
 * L'index couvre TOUTES les réunions de l'onglet, tous pôles confondus :
 * il est construit une fois pour toutes, et le filtrage par pôle s'applique
 * ensuite à ses résultats — jamais une réindexation à chaque changement de
 * périmètre.
 *
 * @param {object} definition  entrée de ONGLETS
 * @param {object} donnees     contenu de reunions.json
 * @returns {object} la vue
 */
function creerVue(definition, donnees) {
  const toutes = reunionsValides(donnees, definition.source)
    .sort(function (a, b) {
      /* Tri explicite et déterministe : jamais l'ordre d'insertion.
         Les comptes-rendus vont du plus récent au plus ancien, les points
         à venir du plus proche au plus lointain. À date égale,
         l'identifiant départage. */
      const parDate = definition.ordre === 'recent'
        ? String(b.date).localeCompare(String(a.date))
        : String(a.date).localeCompare(String(b.date));
      return parDate !== 0 ? parDate : String(a.id).localeCompare(String(b.id));
    });

  const parId = new Map();
  for (const reunion of toutes) parId.set(String(reunion.id), reunion);

  return {
    definition,

    /** Toutes les réunions de l'onglet, tous pôles confondus. */
    toutes,
    parId,

    /* L'index est construit ICI, une fois pour toutes : jamais à la frappe. */
    index: creerIndex(toutes.map(documentIndexable), CHAMPS_INDEXES),

    /** Les réunions du pôle actif — le corpus que la recherche filtre. */
    reunions: [],

    /** Réunions actuellement visibles, après pôle puis recherche. */
    affichees: [],

    /** Identifiant de réunion -> élément <li role="option">. */
    optionsParId: new Map(),

    /** Identifiant de la réunion ouverte dans cet onglet, ou null. */
    selection: null,

    /* Nœuds, créés une seule fois puis réemployés. */
    onglet: null,
    panneau: null,
    pastille: null,
    compteur: null,
    conteneurListe: null,
    lecteur: null
  };
}

/* -------------------------------------------------------------------------
   7. Sélecteur de pôle
   ------------------------------------------------------------------------- */

/**
 * Les quatre puces de facette « Tout le service / ETIIA / ETIIE / ETIII »,
 * chacune avec le nombre de réunions correspondantes, comptes-rendus et
 * points à venir confondus.
 *
 * Ce sont des <button aria-pressed>, jamais des <div> : l'état est donc
 * annoncé aux lecteurs d'écran, et la puce est actionnable au clavier
 * comme à la souris, sans un seul gestionnaire en attribut HTML. Aucune
 * puce n'est jamais désactivée : un pôle à zéro réunion reste sélectionnable
 * et affiche alors son état vide, qui sait proposer le retour au service.
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
      dataset: { pole: pole.cle },
      onClick: () => changerPole(pole.cle)
    },
      el('span', { class: 'facette__marque', 'aria-hidden': 'true' }, '✓'),
      /* Point teinté DÉCORATIF : le libellé qui suit porte seul le sens. */
      el('span', { class: 'pole-point', 'aria-hidden': 'true' }),
      el('span', null, pole.libelle),
      compteur
    );

    refs.facettes.set(pole.cle, { bouton: bouton, compteur: compteur });
    return el('li', null, bouton);
  });

  return el('section', {
    class: 'pile pile--serree sans-impression',
    'aria-labelledby': 'reunions-titre-poles'
  },
    el('h2', { class: 'reunions__titre-section', id: 'reunions-titre-poles' },
      'Périmètre affiché'),
    el('ul', { class: 'facettes' }, puces)
  );
}

/**
 * Met les compteurs, l'état pressé et les libellés accessibles des quatre
 * puces en accord avec les données et le pôle actif.
 */
function majCompteursPoles() {
  for (const [code, puce] of refs.facettes) {
    const nombre = compterPole(code);
    const actif = code === poleActif;

    if (puce.compteur.textContent !== String(nombre)) {
      puce.compteur.textContent = String(nombre);
    }

    puce.bouton.setAttribute('aria-pressed', actif ? 'true' : 'false');
    puce.bouton.setAttribute('aria-label',
      libellePole(code) + ', ' + nombre + ' '
      + pluriel(nombre, 'réunion', 'réunions')
      + ', comptes-rendus et points à venir confondus');
  }
}

/**
 * Nombre de réunions d'un périmètre, les deux onglets réunis. « Tout le
 * service » compte tout ; un pôle ne compte que ses propres entrées.
 *
 * @param {string} code
 * @returns {number}
 */
function compterPole(code) {
  let total = 0;
  for (const vue of vues.values()) {
    total += code === POLE_SERVICE
      ? vue.toutes.length
      : vue.toutes.filter((reunion) => poleDe(reunion) === code).length;
  }
  return total;
}

/**
 * Change le pôle actif : navigation, sous-navigation, listes, lecteurs et
 * URL. Le focus reste sur la puce cliquée — elle n'est jamais reconstruite.
 *
 * @param {string} code
 */
function changerPole(code) {
  const cible = normaliserPole(code);
  if (cible === poleActif) return;

  poleActif = cible;
  majNavigation();
  appliquerPole(null, true);
}

/**
 * Applique le pôle actif aux deux onglets : chaque vue refiltre son corpus,
 * repeint sa liste et son lecteur, et les compteurs se remettent à jour.
 *
 * @param {string|null} prefere     identifiant à ouvrir dans l'onglet actif
 * @param {boolean} avecAnnonce     énoncer le résultat aux lecteurs d'écran
 */
function appliquerPole(prefere, avecAnnonce) {
  for (const vue of vues.values()) {
    vue.reunions = poleActif === POLE_SERVICE
      ? vue.toutes.slice()
      : vue.toutes.filter((reunion) => poleDe(reunion) === poleActif);

    rafraichirVue(vue, vue.definition.cle === ongletActif ? prefere : null);
  }

  majCompteursPoles();
  peindreOnglets(false);

  /* Le hash est normalisé même quand il était absent ou approximatif :
     l'URL porte désormais le pôle, l'onglet, la réunion et la requête, et
     devient partageable telle quelle. */
  ecrireUrl();

  if (!avecAnnonce) return;

  const vue = vueActive();
  const n = vue.affichees.length;

  annoncer(n === 0
    ? 'Aucune réunion pour ' + libellePole(poleActif) + ' dans l’onglet '
      + vue.definition.libelle + '. Revenez à tout le service pour voir '
      + 'les autres réunions.'
    : libellePole(poleActif) + ' : ' + n + ' '
      + pluriel(n, 'réunion', 'réunions') + ' dans l’onglet '
      + vue.definition.libelle + '.');
}

/* -------------------------------------------------------------------------
   8. Barre d'outils : recherche et impression
   ------------------------------------------------------------------------- */

/**
 * Champ de recherche filtrant la liste de l'onglet courant, et bouton
 * d'impression. La barre entière porte `sans-impression` : elle n'a aucun
 * sens sur le papier (base.css la masque alors).
 *
 * @returns {HTMLElement}
 */
function construireBarreOutils() {
  const surFrappe = debounce(function () {
    for (const vue of vues.values()) rafraichirVue(vue, null);
    peindreOnglets(false);
    ecrireUrl();
    annoncerResultats();
  }, DELAI_FRAPPE);

  champRecherche = el('input', {
    class: 'recherche__champ',
    id: 'recherche-reunions',
    type: 'search',
    /* `placeholder` est requis par la règle :not(:placeholder-shown) de
       components.css, qui fait apparaître le bouton d'effacement. */
    placeholder: 'Titre, sujet, action, décision…',
    autocomplete: 'off',
    autocorrect: 'off',
    autocapitalize: 'none',
    spellcheck: 'false',
    enterkeyhint: 'search',
    value: requete,
    'aria-describedby': 'recherche-reunions-aide',
    onInput: function (evt) {
      requete = texteSimple(evt.target.value);
      surFrappe();
    },
    onKeyDown: function (evt) {
      /* Échap efface la recherche sans quitter le champ : le geste
         habituel d'un champ de recherche, ici rendu explicite parce que la
         croix native de WebKit est neutralisée par components.css. */
      if (evt.key === 'Escape' && requete !== '') {
        evt.preventDefault();
        effacerRecherche();
      }
    }
  });

  return el('div', { class: 'barre-outils sans-impression' },

    el('div', { class: 'barre-outils__recherche pile pile--serree' },
      el('label', {
        class: 'visuellement-cache',
        for: 'recherche-reunions'
      }, 'Rechercher une réunion dans l’onglet affiché'),

      el('div', { class: 'recherche' },
        el('span', { class: 'recherche__icone', 'aria-hidden': 'true' }, '⌕'),
        champRecherche,
        el('kbd', { class: 'recherche__raccourci', 'aria-hidden': 'true' }, '/'),
        el('button', {
          class: 'bouton bouton--discret bouton--icone bouton--rond recherche__effacer',
          type: 'button',
          'aria-label': 'Effacer la recherche',
          onClick: effacerRecherche
        }, el('span', { 'aria-hidden': 'true' }, '×'))
      ),

      el('p', {
        class: 'champ__aide',
        id: 'recherche-reunions-aide'
      }, 'La recherche porte sur le titre, le lieu, les sujets, les actions '
        + 'et les décisions, dans le périmètre choisi.')
    ),

    el('button', {
      class: 'bouton bouton--secondaire pousse',
      type: 'button',
      onClick: imprimer
    },
      el('span', { class: 'bouton__icone', 'aria-hidden': 'true' }, '⎙'),
      'Imprimer'
    )
  );
}

/** Vide la recherche, remet les listes à plat et rend le focus au champ. */
function effacerRecherche() {
  requete = '';
  if (champRecherche) {
    champRecherche.value = '';
    champRecherche.focus();
  }
  for (const vue of vues.values()) rafraichirVue(vue, null);
  peindreOnglets(false);
  ecrireUrl();
  annoncerResultats();
}

/**
 * Lance l'impression du navigateur. Les styles @media print de la page ne
 * laissent passer que la réunion affichée : ni en-tête, ni navigation, ni
 * sélecteur de pôle, ni liste latérale, ni boutons. Aucune bibliothèque
 * PDF (SPEC §4.3).
 */
function imprimer() {
  try {
    window.print();
  } catch (_e) {
    /* Certains navigateurs embarqués refusent l'appel : on le dit plutôt
       que de laisser croire à un bouton mort. */
    annoncer('L’impression n’est pas disponible dans ce navigateur. '
      + 'Utilisez le menu Fichier puis Imprimer.');
  }
}

/* -------------------------------------------------------------------------
   9. Onglets accessibles
   ------------------------------------------------------------------------- */

/**
 * Construit le tablist et les deux panneaux.
 *
 * Motif standard : `role="tablist"` / `role="tab"` / `role="tabpanel"`,
 * `aria-controls` et `aria-labelledby` croisés, tabulation glissante — un
 * seul onglet dans l'ordre de tabulation — et activation automatique au
 * déplacement du focus, les deux panneaux étant déjà construits.
 *
 * @returns {HTMLElement}
 */
function construireOnglets() {
  const liste = el('div', {
    class: 'onglets__liste',
    role: 'tablist',
    'aria-label': 'Catégories de réunions',
    onKeyDown: surClavierOnglets
  });

  const panneaux = [];

  for (const definition of ONGLETS) {
    const vue = vues.get(definition.cle);

    vue.pastille = el('span', {
      class: 'pastille',
      /* Le nombre est déjà porté par le texte accessible de l'onglet :
         le répéter ne ferait qu'alourdir l'annonce. */
      'aria-hidden': 'true'
    });

    vue.onglet = el('button', {
      class: 'onglets__onglet',
      type: 'button',
      role: 'tab',
      id: 'onglet-' + definition.cle,
      'aria-controls': 'panneau-' + definition.cle,
      'aria-selected': 'false',
      tabindex: '-1',
      dataset: { onglet: definition.cle },
      onClick: function () { activerOnglet(definition.cle, true); }
    },
      el('span', null, definition.libelle),
      vue.pastille
    );

    liste.append(vue.onglet);
    panneaux.push(construirePanneau(vue));
  }

  return el('div', { class: 'onglets' }, liste, panneaux);
}

/**
 * Le panneau d'un onglet : liste à gauche, lecteur à droite.
 *
 * @param {object} vue
 * @returns {HTMLElement}
 */
function construirePanneau(vue) {
  const cle = vue.definition.cle;

  vue.compteur = el('p', {
    class: 'reunions__compteur',
    id: 'compteur-' + cle
  });

  vue.conteneurListe = el('div', { class: 'pile pile--serree' });

  vue.lecteur = el('article', {
    class: 'reunions__volet lecteur carte carte--ample',
    id: 'lecteur-' + cle,
    tabindex: '-1',
    'aria-live': 'polite',
    'aria-label': 'Réunion affichée — ' + vue.definition.libelle
  });

  vue.panneau = el('div', {
    class: 'onglets__panneau',
    role: 'tabpanel',
    id: 'panneau-' + cle,
    'aria-labelledby': 'onglet-' + cle,
    tabindex: '0',
    hidden: true
  },
    el('div', { class: 'reunions' },
      el('div', { class: 'reunions__volet reunions__liste pile pile--serree' },
        el('div', { class: 'pile pile--serree' },
          el('h2', {
            class: 'reunions__titre-section',
            id: 'titre-liste-' + cle
          }, vue.definition.titreListe),
          vue.compteur
        ),
        vue.conteneurListe
      ),
      vue.lecteur
    )
  );

  return vue.panneau;
}

/**
 * Reporte l'onglet actif sur le DOM : sélection, tabulation glissante et
 * affichage des panneaux.
 *
 * @param {boolean} focaliser  placer le focus sur l'onglet devenu actif
 */
function peindreOnglets(focaliser) {
  for (const vue of vues.values()) {
    const actif = vue.definition.cle === ongletActif;

    vue.onglet.setAttribute('aria-selected', actif ? 'true' : 'false');
    vue.onglet.setAttribute('tabindex', actif ? '0' : '-1');
    vue.panneau.hidden = !actif;

    /* Le décompte accompagne toujours le libellé dans le texte accessible :
       la pastille seule serait muette une fois masquée aux lecteurs. */
    const n = vue.affichees.length;
    vue.pastille.textContent = String(n);
    vue.onglet.setAttribute('aria-label',
      vue.definition.libelle + ' — ' + n + ' '
      + pluriel(n, 'réunion', 'réunions'));
  }

  if (focaliser) vueActive().onglet.focus();
}

/**
 * Active un onglet.
 *
 * @param {string} cle
 * @param {boolean} focaliser
 */
function activerOnglet(cle, focaliser) {
  if (!vues.has(cle)) return;
  if (cle === ongletActif) {
    if (focaliser) vues.get(cle).onglet.focus();
    return;
  }

  ongletActif = cle;
  peindreOnglets(focaliser);
  ecrireUrl();
}

/**
 * Clavier du tablist, conforme au motif standard :
 *   ← / →        onglet précédent / suivant, en boucle
 *   Origine/Fin  premier / dernier onglet
 *   Bas          descend du tablist vers le panneau associé
 * Espace et Entrée sont déjà gérés nativement par les <button>.
 *
 * @param {KeyboardEvent} evt
 */
function surClavierOnglets(evt) {
  /* Une combinaison avec une touche de modification appartient au
     navigateur ou au lecteur d'écran, pas à ce composant. */
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  const cles = ONGLETS.map((definition) => definition.cle);
  const position = cles.indexOf(ongletActif);
  if (position < 0) return;

  let cible = null;

  switch (evt.key) {
    case 'ArrowRight':
      cible = (position + 1) % cles.length;
      break;

    case 'ArrowLeft':
      cible = (position - 1 + cles.length) % cles.length;
      break;

    case 'Home':
      cible = 0;
      break;

    case 'End':
      cible = cles.length - 1;
      break;

    case 'ArrowDown':
      /* Raccourci habituel : le panneau est le contenu de l'onglet, on y
         descend sans avoir à tabuler. */
      evt.preventDefault();
      vueActive().panneau.focus();
      return;

    default:
      return;
  }

  evt.preventDefault();
  activerOnglet(cles[cible], true);
}

/* -------------------------------------------------------------------------
   10. Volet de gauche : la liste filtrée
   ------------------------------------------------------------------------- */

/**
 * Recalcule la liste d'un onglet selon le pôle actif et la requête
 * courante, puis repeint le lecteur. Appelé au rendu initial, à chaque
 * changement de pôle, à chaque frappe et à l'effacement.
 *
 * @param {object} vue
 * @param {string|null} prefere  identifiant à sélectionner s'il est visible
 */
function rafraichirVue(vue, prefere) {
  vue.affichees = filtrer(vue);
  vue.optionsParId.clear();

  const n = vue.affichees.length;
  vue.compteur.textContent = requete.trim() === ''
    ? n + ' ' + pluriel(n, 'réunion', 'réunions')
      + ' — ' + libellePole(poleActif)
    : n + ' ' + pluriel(n, 'réunion trouvée', 'réunions trouvées')
      + ' sur ' + vue.reunions.length + ' — ' + libellePole(poleActif);

  if (n === 0) {
    /* Aucun résultat : un état vide explicite, jamais une colonne blanche.
       Le discours change selon la cause — corpus vide, pôle sans réunion,
       ou recherche infructueuse. */
    monter(vue.conteneurListe, etatVideListe(vue));
    vue.selection = null;
    peindreLecteur(vue);
    return;
  }

  /* On conserve la réunion ouverte si elle reste visible : filtrer ne doit
     pas faire perdre sa lecture en cours. */
  const souhaite = prefere || vue.selection;
  const conserve = souhaite && vue.affichees.some(
    (reunion) => String(reunion.id) === souhaite);

  vue.selection = conserve ? souhaite : String(vue.affichees[0].id);

  const liste = el('ul', {
    class: 'reunions__options',
    role: 'listbox',
    id: 'liste-' + vue.definition.cle,
    'aria-labelledby': 'titre-liste-' + vue.definition.cle,
    /* Un seul écouteur pour toute la liste : l'événement remonte depuis
       l'option qui a le focus. */
    onKeyDown: function (evt) { surClavierListe(evt, vue); }
  });

  for (const reunion of vue.affichees) {
    const option = construireOption(vue, reunion);
    vue.optionsParId.set(String(reunion.id), option);
    liste.append(option);
  }

  monter(vue.conteneurListe, liste);
  peindreSelection(vue);
}

/**
 * Applique le pôle actif puis la requête courante à un onglet.
 *
 * Le pôle filtre le corpus ; la recherche est ensuite déléguée à search.js
 * — insensible à la casse et aux accents, tolérante aux fautes de frappe,
 * classée par pertinence : pas de filtre maison (SPEC §5). L'index couvre
 * tous les pôles, ses résultats sont donc restreints au périmètre après
 * coup, ce qui préserve à la fois l'index et le classement. Requête vide :
 * l'ordre chronologique choisi pour l'onglet est conservé.
 *
 * @param {object} vue
 * @returns {Array<object>} les réunions à afficher, dans l'ordre d'affichage
 */
function filtrer(vue) {
  const q = requete.trim();
  if (q === '') return vue.reunions.slice();

  const sortie = [];
  for (const resultat of rechercher(vue.index, q)) {
    const reunion = vue.parId.get(String(resultat.doc.id));
    if (!reunion) continue;
    if (poleActif !== POLE_SERVICE && poleDe(reunion) !== poleActif) continue;
    sortie.push(reunion);
  }
  return sortie;
}

/**
 * L'état vide de la liste d'un onglet, dans sa variante juste :
 *   - recherche infructueuse : on propose d'élargir la requête ;
 *   - pôle sans réunion : on propose de revenir à tout le service ;
 *   - onglet vide pour tout le service : le corpus est simplement vide.
 *
 * @param {object} vue
 * @returns {HTMLElement}
 */
function etatVideListe(vue) {
  const definition = vue.definition;

  if (requete.trim() !== '') {
    return etatVide('Aucune réunion trouvée',
      'Aucun ' + definition.nom + ' de ' + libellePole(poleActif)
      + ' ne correspond à « ' + requete.trim()
      + ' ». Essayez un autre terme, ou effacez la recherche.', '⌕');
  }

  if (poleActif !== POLE_SERVICE) {
    const total = vue.toutes.length;

    return etatVide(
      'Aucun ' + definition.nom + ' pour ' + poleActif,
      'Le pôle ' + poleActif + ' — ' + metaphorePole(poleActif)
      + ' — n’a aucun ' + definition.nom + ' enregistré. Le service en '
      + 'compte par ailleurs ' + total + ' au total.',
      '∅',
      el('div', { class: 'etat-vide__actions' },
        el('button', {
          class: 'bouton bouton--principal',
          type: 'button',
          onClick: function () {
            changerPole(POLE_SERVICE);
            /* Le bouton cliqué vient d'être détruit : le focus est rendu à
               la puce correspondante, jamais laissé sur le <body>. */
            const puce = refs.facettes.get(POLE_SERVICE);
            if (puce) puce.bouton.focus();
          }
        }, 'Voir tout le service')
      )
    );
  }

  return etatVide(definition.videTitre, definition.videTexte, '📄');
}

/**
 * Une option de la liste : date, lieu, pôle, titre et extrait de synthèse.
 * Aucun élément interactif à l'intérieur — une option de listbox ne
 * contient jamais de lien ni de bouton.
 *
 * @param {object} vue
 * @param {object} reunion
 * @returns {HTMLElement} <li role="option">
 */
function construireOption(vue, reunion) {
  const resume = texteSimple(reunion[vue.definition.champResume]);

  return el('li', {
    class: 'carte carte--compacte reunion-option',
    role: 'option',
    id: 'option-' + vue.definition.cle + '-' + reunion.id,
    'aria-selected': 'false',
    tabindex: '-1',
    dataset: { id: String(reunion.id) },
    onClick: function () { selectionner(vue, String(reunion.id), true); }
  },
    el('p', { class: 'carte__meta' },
      el('time', { datetime: reunion.date }, formaterDate(reunion.date)),
      reunion.lieu
        ? el('span', null, surligne(texteSimple(reunion.lieu)))
        : null,
      pastillePole(reunion)
    ),

    el('p', { class: 'carte__titre' }, surligne(texteSimple(reunion.titre))),

    resume
      ? el('p', { class: 'reunion-option__extrait' }, surligne(resume))
      : null,

    /* Le décompte rappelle, dès la liste, que les actions et les décisions
       sont bien là — c'est précisément ce que l'ancienne version perdait. */
    el('p', { class: 'carte__meta' },
      el('span', { class: 'badge badge--neutre' },
        compte(reunion.actions) + ' '
        + pluriel(compte(reunion.actions), 'action', 'actions')),
      vue.definition.avecDecisions
        ? el('span', { class: 'badge badge--neutre' },
          compte(reunion.decisions) + ' '
          + pluriel(compte(reunion.decisions), 'décision', 'décisions'))
        : null
    )
  );
}

/**
 * Pastille ÉTIQUETÉE du pôle d'une réunion : le point teinté n'est que
 * décoratif, le code du pôle est toujours écrit à côté. La couleur ne
 * porte donc jamais seule l'information (SPEC §1bis).
 *
 * @param {object} reunion
 * @returns {HTMLElement}
 */
function pastillePole(reunion) {
  const code = poleDe(reunion);

  return el('span', {
    class: 'badge badge--pole',
    dataset: { pole: code }
  },
    el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
    (code === POLE_SERVICE ? 'Service ' : 'Pôle ') + code
  );
}

/* -------------------------------------------------------------------------
   11. Volet de droite : le lecteur
   ------------------------------------------------------------------------- */

/**
 * Sélectionne une réunion dans un onglet : met à jour la liste, le lecteur
 * et l'URL.
 *
 * @param {object} vue
 * @param {string} id
 * @param {boolean} focaliser  replacer le focus sur l'option choisie
 */
function selectionner(vue, id, focaliser) {
  if (!vue.optionsParId.has(id)) return;

  if (id !== vue.selection) {
    vue.selection = id;
    peindreSelection(vue);
    ecrireUrl();
  }

  if (focaliser) {
    const option = vue.optionsParId.get(id);
    if (option) option.focus();
  }
}

/**
 * Applique la sélection au DOM, sans toucher ni à l'URL ni au focus.
 * Séparée de selectionner() pour pouvoir peindre la sélection initiale
 * pendant que le lecteur est encore hors du document.
 *
 * @param {object} vue
 */
function peindreSelection(vue) {
  /* Tabulation glissante : une seule option reste dans l'ordre de
     tabulation, les autres n'y sont atteignables qu'aux flèches. */
  for (const [cle, option] of vue.optionsParId) {
    const actif = cle === vue.selection;
    option.setAttribute('aria-selected', actif ? 'true' : 'false');
    option.setAttribute('tabindex', actif ? '0' : '-1');
  }

  peindreLecteur(vue);
}

/**
 * Remplit le lecteur d'un onglet avec la réunion sélectionnée, ou avec un
 * état vide si aucune ne l'est.
 *
 * @param {object} vue
 */
function peindreLecteur(vue) {
  const reunion = vue.selection ? vue.parId.get(vue.selection) : null;

  if (!reunion) {
    monter(vue.lecteur, etatVide(
      'Aucune réunion affichée',
      'Sélectionnez une réunion dans la liste pour en lire le détail.',
      '←'
    ));
    return;
  }

  monter(vue.lecteur, contenuLecteur(vue, reunion));
}

/**
 * Contenu complet d'une réunion : entête, synthèse ou objectif, sujets,
 * puis les blocs d'actions et de décisions.
 *
 * C'est ici que le BUG 3 de la SPEC est corrigé : les trois listes du JSON
 * — sujets, actions, decisions — sont rendues, chacune dans une section
 * étiquetée, sans dépendre d'aucun marqueur textuel.
 *
 * @param {object} vue
 * @param {object} reunion
 * @returns {DocumentFragment}
 */
function contenuLecteur(vue, reunion) {
  const definition = vue.definition;
  const resume = texteSimple(reunion[definition.champResume]);

  return frag(
    el('div', { class: 'lecteur__contenu pile pile--lache' },

      /* --- Entête : date, lieu, pôle, nature --------------------------- */
      el('div', { class: 'pile pile--serree' },
        el('p', { class: 'carte__meta' },
          el('time', { datetime: reunion.date }, formaterDate(reunion.date)),
          reunion.lieu
            ? el('span', { class: 'badge badge--neutre' },
              el('span', { class: 'visuellement-cache' }, 'Lieu : '),
              surligne(texteSimple(reunion.lieu)))
            : null,
          pastillePole(reunion),
          el('span', { class: 'badge badge--accent' }, definition.badge)
        ),
        el('h2', { class: 'sans-marge' }, surligne(texteSimple(reunion.titre)))
      ),

      /* --- Synthèse (comptes-rendus) ou objectif (points à venir) ------- */
      el('section', { class: 'pile pile--serree' },
        el('h3', { class: 'lecteur__titre-section' }, definition.etiquetteResume),
        resume
          ? el('p', { class: 'mesure texte-doux sans-marge' }, surligne(resume))
          : el('p', { class: 'texte-faible texte-sm sans-marge' },
            'Aucune ' + definition.etiquetteResume.toLowerCase()
            + ' n’a été renseignée pour cette réunion.')
      ),

      /* --- Sujets ------------------------------------------------------- */
      sectionSujets(reunion),

      /* --- Actions : toujours affichées, même vides --------------------- */
      blocCle('actions', definition.etiquetteActions, '⚑',
        'Ce qui reste à faire.', reunion.actions,
        'Aucune action n’est rattachée à cette réunion.'),

      /* --- Décisions : propres aux comptes-rendus ----------------------- */
      definition.avecDecisions
        ? blocCle('decisions', 'Décisions', '✓',
          'Ce qui a été acté en séance.', reunion.decisions,
          'Aucune décision n’a été actée lors de cette réunion.')
        : null
    )
  );
}

/**
 * La section des sujets : un titre et des notes par sujet.
 *
 * @param {object} reunion
 * @returns {HTMLElement}
 */
function sectionSujets(reunion) {
  const sujets = Array.isArray(reunion.sujets)
    ? reunion.sujets.filter((sujet) => sujet && typeof sujet === 'object')
    : [];

  return el('section', { class: 'pile pile--serree' },
    el('h3', { class: 'lecteur__titre-section' },
      'Sujets abordés',
      ' ',
      sujets.length > 0
        ? el('span', { class: 'pastille', 'aria-hidden': 'true' },
          String(sujets.length))
        : null
    ),

    sujets.length === 0
      ? el('p', { class: 'texte-faible texte-sm sans-marge' },
        'Aucun sujet n’a été détaillé pour cette réunion.')
      : el('ul', { class: 'sujets' },
        sujets.map(function (sujet) {
          const titre = texteSimple(sujet.titre);
          const notes = texteSimple(sujet.notes);
          return el('li', { class: 'sujet pile pile--serree' },
            titre ? el('h4', { class: 'sujet__titre' }, surligne(titre)) : null,
            notes ? el('p', { class: 'sujet__notes' }, surligne(notes)) : null
          );
        })
      )
  );
}

/**
 * Un bloc clé — actions ou décisions. Surface propre, liseré teinté,
 * étiquette en toutes lettres et liste numérotée : impossible de le
 * confondre avec le corps du texte.
 *
 * L'icône est décorative ; le sens est porté par l'étiquette et par le
 * décompte, jamais par la seule couleur (SPEC §7).
 *
 * @param {string} variante  'actions' | 'decisions'
 * @param {string} etiquette libellé affiché
 * @param {string} icone     glyphe décoratif
 * @param {string} aide      une phrase expliquant ce que contient le bloc
 * @param {*} entrees        tableau attendu de chaînes
 * @param {string} texteVide message si le tableau est vide ou absent
 * @returns {HTMLElement}
 */
function blocCle(variante, etiquette, icone, aide, entrees, texteVide) {
  const lignes = Array.isArray(entrees)
    ? entrees.map(texteSimple).filter((texte) => texte !== '')
    : [];

  return el('section', { class: ['bloc-cle', 'bloc-cle--' + variante] },
    el('div', { class: 'bloc-cle__entete' },
      el('span', { class: 'bloc-cle__icone', 'aria-hidden': 'true' }, icone),
      el('h3', { class: 'bloc-cle__titre' }, etiquette),
      el('span', { class: 'pastille' }, String(lignes.length)),
      el('span', { class: 'texte-xs texte-doux' }, aide)
    ),

    lignes.length === 0
      ? el('p', { class: 'texte-sm texte-doux sans-marge' }, texteVide)
      : el('ol', { class: 'bloc-cle__liste' },
        lignes.map((texte) => el('li', null, surligne(texte)))
      )
  );
}

/* -------------------------------------------------------------------------
   12. Navigation au clavier dans la liste
   ------------------------------------------------------------------------- */

/**
 * Clavier de la listbox, conforme au motif standard :
 *   ↓ / ↑        réunion suivante / précédente (la sélection suit le focus)
 *   Origine/Fin  première / dernière réunion
 *   Entrée       confirme et emmène au lecteur
 *   Espace       confirme sans quitter la liste
 *
 * @param {KeyboardEvent} evt
 * @param {object} vue
 */
function surClavierListe(evt, vue) {
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  const position = vue.affichees.findIndex(
    (reunion) => String(reunion.id) === vue.selection);
  if (position < 0) return;

  let cible = null;

  switch (evt.key) {
    case 'ArrowDown':
      cible = Math.min(position + 1, vue.affichees.length - 1);
      break;

    case 'ArrowUp':
      cible = Math.max(position - 1, 0);
      break;

    case 'Home':
      cible = 0;
      break;

    case 'End':
      cible = vue.affichees.length - 1;
      break;

    case 'Enter':
      evt.preventDefault();
      /* Le lecteur est long : y emmener le focus évite d'avoir à le
         retraverser à la tabulation depuis le haut de la liste. */
      vue.lecteur.focus();
      return;

    case ' ':
    case 'Spacebar':
      evt.preventDefault();
      selectionner(vue, vue.selection, true);
      return;

    default:
      return;
  }

  evt.preventDefault();
  selectionner(vue, String(vue.affichees[cible].id), true);
}

/* -------------------------------------------------------------------------
   13. Navigation et sous-navigation
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
  initNav(PAGE_DE_POLE[poleActif] || 'index.html');
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
    'Autres pages — ' + libellePole(poleActif));

  monter(refs.sousNav,
    el('ul', { class: 'rangee rangee--serree' },
      PAGES_TRANSVERSES.map((entree) => el('li', null,
        el('a', {
          class: 'bouton bouton--secondaire bouton--compact',
          href: entree.page + '#' + CLE_POLE + '=' + encodeURIComponent(poleActif)
        }, entree.libelle))),
      el('li', null,
        el('a', {
          class: 'bouton bouton--secondaire bouton--compact',
          href: PAGE_DE_POLE[poleActif] || 'index.html'
        }, poleActif === POLE_SERVICE
          ? 'Tableau de bord ETII'
          : 'Espace ' + poleActif))
    )
  );
}

/* -------------------------------------------------------------------------
   14. État reflété dans l'URL
   ------------------------------------------------------------------------- */

/**
 * Écrit le pôle, l'onglet actif, la réunion ouverte et la requête dans le
 * hash. etatUrl.ecrire() remplace l'entrée d'historique courante et omet
 * les valeurs vides : l'URL reste courte, lisible et partageable telle
 * quelle.
 */
function ecrireUrl() {
  const vue = vueActive();
  etatUrl.ecrire({
    [CLE_POLE]: poleActif,
    [CLE_ONGLET]: ongletActif,
    [CLE_REUNION]: vue ? vue.selection : null,
    [CLE_REQUETE]: requete.trim()
  });
}

/**
 * Restaure l'état depuis le hash après une vraie navigation (retour
 * arrière, lien collé). `replaceState` ne déclenche pas hashchange : seules
 * les navigations de l'utilisateur arrivent ici, aucune boucle de
 * rétroaction n'est donc possible avec ecrireUrl().
 *
 * @param {object} etat  résultat de etatUrl.lire()
 */
function appliquerEtatUrl(etat) {
  const pole = poleDepuisEtat(etat);

  if (vues.size === 0) {
    /* Données pas encore chargées — ou état d'erreur affiché : il n'y a
       rien à repeindre, mais la navigation, elle, doit déjà suivre le
       pôle demandé. rendre() relira le hash au moment voulu. */
    if (pole !== poleActif) {
      poleActif = pole;
      majNavigation();
    }
    return;
  }

  const nouvelleRequete = texteSimple(etat[CLE_REQUETE]);
  const changementRequete = nouvelleRequete.trim() !== requete.trim();

  if (changementRequete) {
    requete = nouvelleRequete;
    if (champRecherche) champRecherche.value = nouvelleRequete;
  }

  const cible = resoudreOngletInitial(etat);
  const reunion = texteSimple(etat[CLE_REUNION]);

  ongletActif = cible;

  if (pole !== poleActif) {
    /* Le pôle refiltre tout : inutile de rafraîchir deux fois,
       appliquerPole() repeint les deux onglets et réécrit l'URL. */
    poleActif = pole;
    majNavigation();
    appliquerPole(reunion || null, false);
    return;
  }

  if (changementRequete) {
    for (const vue of vues.values()) {
      rafraichirVue(vue, vue.definition.cle === cible ? reunion : null);
    }
  } else {
    const vue = vues.get(cible);
    if (vue && reunion && vue.optionsParId.has(reunion)) {
      vue.selection = reunion;
      peindreSelection(vue);
    }
  }

  peindreOnglets(false);
}

/**
 * Onglet à ouvrir d'après l'état d'URL.
 *
 * Trois sources, dans l'ordre : l'onglet explicitement demandé, l'onglet
 * qui contient la réunion demandée — un lien `#reunion=cr02` venu d'une
 * autre page ouvre ainsi le bon onglet — et à défaut le premier onglet.
 *
 * @param {object} etat
 * @returns {string} une clé d'onglet toujours valide
 */
function resoudreOngletInitial(etat) {
  const demande = texteSimple(etat && etat[CLE_ONGLET]);
  if (vues.has(demande)) return demande;

  const reunion = texteSimple(etat && etat[CLE_REUNION]);
  if (reunion) {
    for (const vue of vues.values()) {
      if (vue.parId.has(reunion)) return vue.definition.cle;
    }
  }

  return ONGLETS[0].cle;
}

/**
 * Pôle lu dans l'état d'URL. Toute valeur absente ou inconnue retombe sur
 * « ETII », le niveau service, sans erreur ni message (SPEC §1bis).
 *
 * @param {object} etat
 * @returns {string}
 */
function poleDepuisEtat(etat) {
  if (!etat || typeof etat !== 'object') return POLE_SERVICE;
  const brut = Array.isArray(etat[CLE_POLE]) ? etat[CLE_POLE][0] : etat[CLE_POLE];
  return normaliserPole(brut);
}

/**
 * Ramène n'importe quelle valeur à l'un des quatre codes admis.
 *
 * @param {*} valeur
 * @returns {string}
 */
function normaliserPole(valeur) {
  const code = typeof valeur === 'string' ? valeur.trim().toUpperCase() : '';
  return CODES_POLE.includes(code) ? code : POLE_SERVICE;
}

/**
 * Pôle d'une réunion. Une réunion sans pôle, ou dont le pôle est inconnu,
 * appartient au niveau service.
 *
 * @param {object} reunion
 * @returns {string}
 */
function poleDe(reunion) {
  return normaliserPole(reunion ? reunion.pole : null);
}

/** Libellé lisible d'un périmètre, pour les compteurs et les aria-label. */
function libellePole(code) {
  const pole = POLES.find((item) => item.cle === code);
  return pole ? pole.libelle : POLE_SERVICE;
}

/** Métaphore d'un pôle, matière éditoriale de l'accord d'équipe. */
function metaphorePole(code) {
  const pole = POLES.find((item) => item.cle === code);
  return pole ? pole.metaphore : '';
}

/* -------------------------------------------------------------------------
   15. Petits utilitaires
   ------------------------------------------------------------------------- */

/** La vue de l'onglet actif. */
function vueActive() {
  return vues.get(ongletActif) || vues.get(ONGLETS[0].cle);
}

/**
 * Les entrées exploitables d'un des deux tableaux du JSON : un objet doté
 * au moins d'un identifiant et d'un titre. Les entrées malformées sont
 * écartées silencieusement plutôt que d'interrompre l'affichage des autres.
 *
 * @param {*} donnees
 * @param {string} source  'comptesRendus' | 'prochainsPoints'
 * @returns {Array<object>}
 */
function reunionsValides(donnees, source) {
  if (!donnees || typeof donnees !== 'object') return [];
  const brut = donnees[source];
  if (!Array.isArray(brut)) return [];

  return brut.filter((reunion) => !!reunion && typeof reunion === 'object'
    && typeof reunion.id === 'string' && reunion.id !== ''
    && typeof reunion.titre === 'string');
}

/**
 * Projection d'une réunion vers la forme attendue par search.js : le
 * moteur n'indexe que des chaînes et des tableaux de chaînes, les sujets —
 * qui sont des objets — sont donc aplatis ici.
 *
 * Le champ `date` est conservé : search.js s'en sert pour départager les
 * ex aequo de façon déterministe (SPEC §5).
 *
 * @param {object} reunion
 * @returns {object} document indexable
 */
function documentIndexable(reunion) {
  const sujets = Array.isArray(reunion.sujets) ? reunion.sujets : [];

  return {
    id: String(reunion.id),
    date: texteSimple(reunion.date),
    titre: texteSimple(reunion.titre),
    lieu: texteSimple(reunion.lieu),
    resume: texteSimple(reunion.synthese) || texteSimple(reunion.objectif),
    sujets: sujets
      .filter((sujet) => sujet && typeof sujet === 'object')
      .map((sujet) => (texteSimple(sujet.titre) + ' ' + texteSimple(sujet.notes)).trim())
      .filter((texte) => texte !== ''),
    actions: Array.isArray(reunion.actions) ? reunion.actions.map(texteSimple) : [],
    decisions: Array.isArray(reunion.decisions) ? reunion.decisions.map(texteSimple) : []
  };
}

/**
 * Texte surligné selon la requête courante.
 *
 * surligner() de search.js ne produit que des segments de texte brut ;
 * surlignerVers() de ui.js est le seul endroit du projet où naissent les
 * <mark>. Aucune chaîne ne transite jamais par innerHTML.
 *
 * @param {string} texte
 * @returns {DocumentFragment}
 */
function surligne(texte) {
  return surlignerVers(surligner(texte, requete.trim()));
}

/**
 * Bloc d'état vide, au vocabulaire de components.css. Le glyphe est
 * décoratif : le sens est dans le titre et le texte.
 *
 * @param {string} titre
 * @param {string} texte
 * @param {string} glyphe
 * @param {*} [actions]  bloc d'actions facultatif
 * @returns {HTMLElement}
 */
function etatVide(titre, texte, glyphe, actions) {
  return el('div', { class: 'etat-vide etat-vide--compact etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, glyphe),
    el('p', { class: 'etat-vide__titre' }, titre),
    el('p', { class: 'etat-vide__texte' }, texte),
    actions || null
  );
}

/**
 * Annonce le nombre de résultats après une frappe, sans harceler les
 * lecteurs d'écran : l'annonce est amortie et ne part qu'une fois la
 * saisie stabilisée.
 */
const annoncerResultats = debounce(function () {
  const vue = vueActive();
  if (!vue) return;

  const n = vue.affichees.length;
  const perimetre = ' dans l’onglet ' + vue.definition.libelle
    + ' pour ' + libellePole(poleActif) + '.';

  if (requete.trim() === '') {
    annoncer('Recherche effacée. ' + n + ' '
      + pluriel(n, 'réunion affichée', 'réunions affichées') + perimetre);
    return;
  }

  annoncer(n === 0
    ? 'Aucune réunion trouvée' + perimetre
    : n + ' ' + pluriel(n, 'réunion trouvée', 'réunions trouvées') + perimetre);
}, DELAI_FRAPPE * 4);

/**
 * Nombre d'éléments d'un tableau, 0 pour toute autre valeur.
 *
 * @param {*} valeur
 * @returns {number}
 */
function compte(valeur) {
  return Array.isArray(valeur) ? valeur.length : 0;
}

/** Accord au pluriel, sans bibliothèque ni table. */
function pluriel(nombre, singulier, pluriels) {
  return nombre > 1 ? pluriels : singulier;
}

/**
 * Chaîne exploitable, jamais `undefined` ni `[object Object]`.
 *
 * @param {*} valeur
 * @returns {string}
 */
function texteSimple(valeur) {
  return typeof valeur === 'string' ? valeur : '';
}

/** Formateur de date en français, construit une seule fois. */
const FORMAT_DATE = (function () {
  try {
    return new Intl.DateTimeFormat('fr-FR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
  } catch (_e) {
    return null;   // moteur sans Intl : on retombera sur la date brute
  }
})();

/**
 * Met une date ISO en forme lisible. En cas de doute, la valeur d'origine
 * est rendue telle quelle : mieux vaut une date brute qu'un « Invalid Date ».
 *
 * @param {string} iso  par exemple '2026-09-10'
 * @returns {string}
 */
function formaterDate(iso) {
  if (typeof iso !== 'string' || iso === '') return '';
  if (!FORMAT_DATE) return iso;

  /* Heure explicite : sans elle, une date seule est interprétée en UTC et
     peut reculer d'un jour selon le fuseau de la personne. */
  const date = new Date(iso + 'T12:00:00');
  if (Number.isNaN(date.getTime())) return iso;

  try {
    return FORMAT_DATE.format(date);
  } catch (_e) {
    return iso;
  }
}
