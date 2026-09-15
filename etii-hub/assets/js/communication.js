/* =========================================================================
   ETII Hub — Module du Communication Center (SPEC.md §4.2 et §1bis)

   C'est une page TRANSVERSE : un seul gabarit, partagé par le service et
   par ses trois pôles, filtré par le pôle actif. Le pôle voyage dans le
   hash de l'URL — `communication.html#pole=ETIIA` — et « ETII » désigne
   le niveau service, tous pôles confondus.

   Cinq responsabilités, et rien d'autre :

     1. Démarrer le thème et marquer, dans la navigation principale, le
        lien du PÔLE ACTIF (celui du tableau de bord si le pôle est ETII).
     2. Charger communications.json et en rendre les trois états —
        chargement, erreur, vide — via avecEtat() de data.js.
     3. Offrir un sélecteur de pôle à quatre puces, chacune avec son
        nombre d'annonces, et un état vide explicite quand un pôle n'a
        rien publié.
     4. Afficher la liste chronologique des annonces à gauche et le détail
        de l'annonce sélectionnée à droite.
     5. Refléter dans le hash À LA FOIS le pôle et l'annonce sélectionnée,
        et les restaurer au chargement comme au retour arrière.

   Points de conception notables :

   - La liste est une VRAIE liste d'options (role="listbox" / role="option")
     à tabulation glissante : une seule option est dans l'ordre de
     tabulation, les flèches déplacent le focus et la sélection, Entrée
     emmène au détail. L'état est porté par aria-selected, jamais par une
     classe posée ici — l'information visuelle et l'information accessible
     ont une source unique.

   - Le pôle n'est jamais signalé par la couleur seule : chaque annonce
     porte une pastille ÉTIQUETÉE, où le code du pôle est écrit à côté du
     point teinté, et chaque puce du sélecteur nomme son périmètre.

   - Le corps d'une annonce est un tableau de lignes typées. Les puces
     consécutives sont regroupées en un seul <ul> : le lecteur d'écran
     annonce « liste de 2 éléments », ce qu'une suite de paragraphes ne
     ferait jamais. Aucune machine à écrire, aucun marqueur textuel à
     parser : le type est explicite dans la donnée (SPEC §4.2).

   - Le bandeau d'alertes est entièrement en CSS (cf. <style> de la page).
     Ce module ne fait que produire les deux exemplaires de la liste que
     l'animation translate ; il ne pose aucun minuteur.

   Tout le DOM produit ici passe par el() / frag() / monter() : le texte est
   inséré en textContent, jamais en innerHTML, et aucun gestionnaire n'est
   écrit en attribut HTML (SPEC §8).
   ========================================================================= */

import {
  el, frag, monter, annoncer, etatUrl, initTheme, initNav
} from './ui.js';

import { chargerDonnees, avecEtat, verifierForme } from './data.js';

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
  { page: 'reunions.html', libelle: 'Réunions' },
  { page: 'organigramme.html', libelle: 'Organigramme' },
  { page: 'faq.html', libelle: 'FAQ' }
];

/* -------------------------------------------------------------------------
   2. Constantes d'affichage
   ------------------------------------------------------------------------- */

/**
 * Correspondance entre le statut d'une annonce et le vocabulaire visuel de
 * components.css. Le libellé est toujours affiché : le sens n'est jamais
 * porté par la seule couleur.
 */
const STATUTS = {
  info:   { badge: 'badge--info',   carte: 'carte--statut-info',   libelle: 'Information' },
  urgent: { badge: 'badge--alerte', carte: 'carte--statut-alerte', libelle: 'Urgent' },
  succes: { badge: 'badge--succes', carte: 'carte--statut-succes', libelle: 'Validé' }
};

/* Repli si le JSON porte une valeur inattendue : l'annonce s'affiche quand
   même, sans liseré de statut — mieux vaut une carte neutre qu'une classe
   inventée qui n'existe dans aucune feuille de style. */
const STATUT_DEFAUT = { badge: 'badge--neutre', carte: null, libelle: 'Annonce' };

/** Clés sous lesquelles l'état est écrit dans le hash de l'URL. */
const CLE_POLE = 'pole';
const CLE_URL = 'annonce';

/** Nombre de gabarits d'option affichés pendant le chargement. */
const SQUELETTES_LISTE = 4;

/* -------------------------------------------------------------------------
   3. État du module
   ------------------------------------------------------------------------- */

/** Toutes les annonces exploitables, de la plus récente à la plus ancienne. */
let toutes = [];

/** Celles du pôle actif — c'est ce tableau qu'affiche la liste. */
let annonces = [];

/** Le pôle actif, toujours l'un des quatre codes admis. */
let poleActif = POLE_SERVICE;

/** Identifiant de l'annonce actuellement sélectionnée, ou null. */
let idSelection = null;

/** Identifiant d'annonce -> élément <li role="option"> correspondant. */
const optionsParId = new Map();

/** Nœuds durables de la page, reconstruits à chaque rendu de données. */
const refs = {
  zone: null,
  sousNav: null,
  /** Conteneur des deux volets — ou de l'état vide d'un pôle sans annonce. */
  corps: null,
  /** Code de pôle -> { bouton, compteur } du sélecteur. */
  facettes: new Map(),
  /** Volet de détail, recréé à chaque changement de pôle. */
  detail: null
};

/* -------------------------------------------------------------------------
   4. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

refs.zone = document.getElementById('zone-communication');
refs.sousNav = document.getElementById('comm-sous-nav');

/* Le pôle est connu avant même les données : la navigation et la
   sous-navigation sont donc justes dès la première image, y compris si le
   fichier d'annonces est introuvable. */
poleActif = poleDepuisEtat(etatUrl.lire());
majNavigation();

/* Enregistré UNE seule fois, hors du rendu : un clic sur « Réessayer »
   relance le rendu, il ne doit pas empiler les écouteurs. `replaceState`
   ne déclenche pas hashchange, donc seules les vraies navigations — retour
   arrière, lien collé — arrivent ici. */
etatUrl.ecouter(surNavigationHash);

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
    () => chargerDonnees('communications').then((brut) => verifierForme(brut, {
      alertes: 'tableau?',
      annonces: {
        type: 'tableau',
        elements: { id: 'chaine', date: 'chaine', titre: 'chaine' }
      }
    }, 'communications.json')),

    rendre,

    {
      squelette: squeletteDeuxVolets,
      texteChargement: 'Chargement des annonces du service…',
      titreErreur: 'Annonces indisponibles',
      titreVide: 'Aucune annonce publiée',
      texteVide: 'Le service n’a encore publié aucune annonce. Cette page '
        + 'se remplira dès la première communication.',
      /* Vacuité du FICHIER, tous pôles confondus. Un pôle sans annonce
         n'est pas un fichier vide : il a son propre état vide, qui sait
         proposer le retour à tout le service. */
      estVide: (brut) => !brut || !Array.isArray(brut.annonces)
        || brut.annonces.filter(estAnnonce).length === 0
    }
  );
}

/* -------------------------------------------------------------------------
   5. État de chargement
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
        el('span', { class: 'squelette squelette--ligne squelette--court' }),
        el('span', { class: 'squelette squelette--ligne squelette--titre' }),
        el('span', { class: 'squelette squelette--ligne squelette--moyen' })
      )
    );
  }

  monter(conteneur,
    el('div', { class: 'comm', 'aria-hidden': 'true' },
      el('div', { class: 'comm__volet pile pile--serree' }, colonne),
      el('div', { class: 'carte squelette-groupe' },
        el('span', { class: 'squelette squelette--ligne squelette--court' }),
        el('span', { class: 'squelette squelette--ligne squelette--titre' }),
        el('span', { class: 'squelette squelette--bloc' })
      )
    )
  );
}

/* -------------------------------------------------------------------------
   6. Rendu principal
   ------------------------------------------------------------------------- */

/**
 * Construit le bandeau d'alertes, le sélecteur de pôle, puis délègue le
 * reste à peindrePole() — qui sait aussi bien peindre les deux volets que
 * l'état vide d'un pôle sans annonce.
 *
 * @param {object} donnees    contenu de communications.json
 * @param {Element} conteneur zone de page, déjà vidée par avecEtat()
 */
function rendre(donnees, conteneur) {
  /* `filter` produit un tableau neuf : le tri ne touche pas aux données
     d'origine, qui restent réutilisables par les autres pages via le cache
     de data.js. Tri décroissant sur la date ISO — la comparaison
     lexicographique suffit et reste déterministe. À date égale,
     l'identifiant départage : jamais l'ordre d'insertion. */
  toutes = donnees.annonces
    .filter(estAnnonce)
    .sort(function (a, b) {
      const parDate = String(b.date).localeCompare(String(a.date));
      return parDate !== 0 ? parDate : String(a.id).localeCompare(String(b.id));
    });

  /* Le hash peut avoir changé entre le démarrage et l'arrivée des
     données — un lien collé, par exemple. On le relit. */
  poleActif = poleDepuisEtat(etatUrl.lire());
  majNavigation();

  refs.facettes.clear();
  refs.corps = el('div', { class: 'pile pile--lache' });

  monter(conteneur,
    construireBandeau(donnees.alertes),
    construireSelecteur(),
    refs.corps
  );

  peindrePole(true);
}

/* -------------------------------------------------------------------------
   7. Sélecteur de pôle
   ------------------------------------------------------------------------- */

/**
 * Les quatre puces de facette « Tout le service / ETIIA / ETIIE / ETIII »,
 * chacune avec le nombre d'annonces correspondantes.
 *
 * Ce sont des <button aria-pressed>, jamais des <div> : l'état est donc
 * annoncé aux lecteurs d'écran, et la puce est actionnable au clavier
 * comme à la souris, sans un seul gestionnaire en attribut HTML. Aucune
 * puce n'est jamais désactivée : un pôle à zéro annonce reste sélectionnable
 * et affiche alors son état vide, qui explique la situation.
 *
 * @returns {HTMLElement}
 */
function construireSelecteur() {
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
    'aria-labelledby': 'comm-titre-poles'
  },
    el('h2', { class: 'comm__titre-section', id: 'comm-titre-poles' },
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
      + pluriel(nombre, 'annonce', 'annonces'));
  }
}

/**
 * Nombre d'annonces d'un périmètre. « Tout le service » montre tout ; un
 * pôle ne montre que ses propres entrées.
 *
 * @param {string} code
 * @returns {number}
 */
function compterPole(code) {
  if (code === POLE_SERVICE) return toutes.length;
  return toutes.filter((annonce) => poleDe(annonce) === code).length;
}

/**
 * Change le pôle actif : navigation, sous-navigation, liste, détail, URL.
 * Le focus reste sur la puce cliquée — elle n'est jamais reconstruite.
 *
 * @param {string} code
 */
function changerPole(code) {
  const cible = normaliserPole(code);
  if (cible === poleActif) return;

  poleActif = cible;
  majNavigation();
  peindrePole(true);
}

/* -------------------------------------------------------------------------
   8. Peinture du pôle actif
   ------------------------------------------------------------------------- */

/**
 * Filtre les annonces sur le pôle actif, puis peint soit les deux volets,
 * soit l'état vide du pôle.
 *
 * La sélection initiale est peinte AVANT l'insertion dans le document : le
 * volet de détail est une région live, et une région remplie hors du
 * document n'énonce rien. On évite ainsi de faire lire toute l'annonce au
 * chargement de la page — seuls les changements ultérieurs sont annoncés.
 *
 * @param {boolean} avecAnnonce  énoncer le résultat aux lecteurs d'écran
 */
function peindrePole(avecAnnonce) {
  annonces = poleActif === POLE_SERVICE
    ? toutes.slice()
    : toutes.filter((annonce) => poleDe(annonce) === poleActif);

  majCompteursPoles();

  optionsParId.clear();
  idSelection = null;
  refs.detail = null;

  if (annonces.length === 0) {
    monter(refs.corps, blocPoleVide());
    ecrireUrl();
    if (avecAnnonce) {
      annoncer('Aucune annonce pour ' + libellePole(poleActif)
        + '. Revenez à tout le service pour voir les autres annonces.');
    }
    return;
  }

  const liste = construireListe();
  refs.detail = construireVoletDetail();

  /* Sélection initiale : celle du hash si elle désigne une annonce du pôle
     affiché, la plus récente sinon. */
  const demande = idDepuisEtat(etatUrl.lire());
  const initiale = (demande && optionsParId.has(demande))
    ? demande
    : annonces[0].id;

  peindreSelection(initiale);

  monter(refs.corps,
    el('div', { class: 'comm' },
      el('div', { class: 'comm__volet comm__liste pile pile--serree' },
        el('div', { class: 'rangee rangee--serree rangee--entre' },
          el('h2', { class: 'comm__titre-section', id: 'comm-titre-liste' },
            'Annonces publiées'),
          el('span', { class: 'pastille' }, String(annonces.length))
        ),
        liste
      ),
      refs.detail
    )
  );

  /* Le hash est normalisé même quand il était absent ou approximatif :
     l'URL porte désormais à la fois le pôle et l'annonce, et devient
     partageable telle quelle. */
  ecrireUrl();

  if (avecAnnonce) {
    annoncer(libellePole(poleActif) + ' : ' + annonces.length + ' '
      + pluriel(annonces.length, 'annonce', 'annonces')
      + (annonces.length > 1
        ? '. Utilisez les flèches haut et bas pour parcourir la liste.'
        : '.'));
  }
}

/**
 * État vide d'un pôle qui n'a rien publié. Explicite, et actionnable : il
 * propose de revenir à tout le service, là où les annonces existent.
 *
 * @returns {HTMLElement}
 */
function blocPoleVide() {
  const total = toutes.length;

  return el('div', { class: 'etat-vide etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '∅'),
    el('p', { class: 'etat-vide__titre' },
      'Aucune annonce pour ' + libellePole(poleActif)),
    el('p', { class: 'etat-vide__texte' },
      'Le pôle ' + poleActif + ' — ' + metaphorePole(poleActif)
      + ' — n’a encore rien publié. Le service compte par ailleurs '
      + total + ' ' + pluriel(total, 'annonce', 'annonces') + '.'),
    el('div', { class: 'etat-vide__actions' },
      el('button', {
        class: 'bouton bouton--principal',
        type: 'button',
        onClick: () => {
          changerPole(POLE_SERVICE);
          const puce = refs.facettes.get(POLE_SERVICE);
          if (puce) puce.bouton.focus();
        }
      }, 'Voir tout le service')
    )
  );
}

/* -------------------------------------------------------------------------
   9. Volet de gauche : la liste d'options
   ------------------------------------------------------------------------- */

/**
 * Construit la liste d'annonces sous forme de listbox à tabulation
 * glissante, et mémorise chaque option dans `optionsParId`.
 *
 * @returns {HTMLElement} l'élément <ul role="listbox">
 */
function construireListe() {
  const liste = el('ul', {
    class: 'comm__options',
    role: 'listbox',
    id: 'liste-annonces',
    'aria-label': 'Annonces publiées — ' + libellePole(poleActif),
    /* Un seul écouteur pour toute la liste : l'événement remonte depuis
       l'option qui a le focus. */
    onKeyDown: surClavierListe
  });

  for (const annonce of annonces) {
    const option = construireOption(annonce);
    optionsParId.set(annonce.id, option);
    liste.append(option);
  }

  return liste;
}

/**
 * Une option de la liste : date, pastille de statut, pastille étiquetée du
 * pôle d'origine, catégorie, titre, résumé. Aucun élément interactif à
 * l'intérieur — une option de listbox ne contient jamais de lien ni de
 * bouton.
 *
 * @param {object} annonce
 * @returns {HTMLElement} <li role="option">
 */
function construireOption(annonce) {
  const statut = STATUTS[annonce.statut] || STATUT_DEFAUT;

  return el('li', {
    class: ['carte', 'carte--compacte', 'annonce', statut.carte],
    role: 'option',
    id: 'annonce-' + annonce.id,
    'aria-selected': 'false',
    tabindex: '-1',
    dataset: { id: annonce.id },
    onClick: function () { selectionner(annonce.id, true); }
  },
    el('p', { class: 'carte__meta' },
      el('time', { datetime: annonce.date }, formaterDate(annonce.date)),
      el('span', { class: ['badge', statut.badge] },
        el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
        statut.libelle
      ),
      pastillePole(annonce),
      annonce.categorie ? el('span', null, annonce.categorie) : null
    ),

    el('p', { class: 'carte__titre annonce__titre' }, annonce.titre),

    annonce.resume
      ? el('p', { class: 'annonce__resume' }, annonce.resume)
      : null
  );
}

/**
 * Pastille ÉTIQUETÉE du pôle d'origine d'une annonce.
 *
 * Le point coloré est décoratif ; l'information est portée par le texte
 * qui l'accompagne — « Pôle ETIIA », ou « Service ETII » au niveau
 * service. La couleur ne signale donc jamais seule le pôle (SPEC §1bis).
 *
 * @param {object} annonce
 * @returns {HTMLElement}
 */
function pastillePole(annonce) {
  const code = poleDe(annonce);

  return el('span', {
    class: 'badge badge--pole',
    dataset: { pole: code }
  },
    el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
    (code === POLE_SERVICE ? 'Service ' : 'Pôle ') + code
  );
}

/* -------------------------------------------------------------------------
   10. Volet de droite : le détail
   ------------------------------------------------------------------------- */

/**
 * Enveloppe du détail. C'est une région nommée et annoncée poliment : à
 * chaque changement de sélection, son contenu est relu sans interrompre la
 * personne en cours de frappe ou de lecture.
 *
 * `tabindex="-1"` la rend focalisable par programme uniquement : la touche
 * Entrée y emmène depuis la liste, mais elle reste hors de l'ordre de
 * tabulation.
 *
 * @returns {HTMLElement}
 */
function construireVoletDetail() {
  return el('section', {
    class: 'comm__volet comm__detail carte carte--ample',
    id: 'detail-annonce',
    tabindex: '-1',
    'aria-live': 'polite',
    'aria-label': 'Détail de l’annonce sélectionnée'
  });
}

/**
 * Contenu du détail : date, statut, pôle d'origine, catégorie, titre,
 * résumé, puis le corps typé.
 *
 * @param {object} annonce
 * @returns {DocumentFragment}
 */
function contenuDetail(annonce) {
  const statut = STATUTS[annonce.statut] || STATUT_DEFAUT;

  return frag(
    el('div', { class: 'comm__contenu pile' },

      el('p', { class: 'carte__meta' },
        el('time', { datetime: annonce.date }, formaterDate(annonce.date)),
        el('span', { class: ['badge', statut.badge] },
          el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
          statut.libelle
        ),
        pastillePole(annonce),
        annonce.categorie ? el('span', null, annonce.categorie) : null
      ),

      el('h2', null, annonce.titre),

      annonce.resume
        ? el('p', { class: 'mesure texte-doux' }, annonce.resume)
        : null,

      corpsOuNote(annonce.corps)
    )
  );
}

/**
 * Le corps rendu, ou une note explicite s'il est absent ou vide : une
 * annonce sans détail reste une information, pas un panneau blanc.
 *
 * @param {*} corps
 * @returns {HTMLElement}
 */
function corpsOuNote(corps) {
  const lignes = Array.isArray(corps)
    ? corps.filter((ligne) => ligne && typeof ligne === 'object')
    : [];

  if (lignes.length === 0) {
    return el('p', { class: 'texte-faible texte-sm' },
      'Cette annonce ne comporte pas de détail supplémentaire.');
  }

  return el('div', { class: 'pile' }, rendreCorps(lignes));
}

/**
 * Transforme le tableau de lignes typées en nœuds DOM.
 *
 * Les puces consécutives sont regroupées dans un seul <ul> : c'est la
 * raison d'être du parcours séquentiel plutôt que d'un simple `map`. Toute
 * ligne d'un autre type referme la liste en cours.
 *
 * Types reconnus (SPEC §4.2) :
 *   titre  -> sous-titre de section
 *   puce   -> élément d'une vraie liste à puces
 *   alerte -> ligne accentuée en couleur d'alerte, avec icône
 *   valide -> ligne accentuée en couleur de succès, avec icône
 *   vide   -> séparation visuelle
 *
 * @param {Array<{type:string, texte:string}>} lignes
 * @returns {Array<Node>}
 */
function rendreCorps(lignes) {
  const noeuds = [];
  let puces = null;

  for (const ligne of lignes) {
    const type = typeof ligne.type === 'string' ? ligne.type : '';
    const texte = typeof ligne.texte === 'string' ? ligne.texte : '';

    if (type === 'puce') {
      if (!puces) {
        puces = el('ul', { class: 'corps__liste' });
        noeuds.push(puces);
      }
      puces.append(el('li', null, texte));
      continue;
    }

    /* Toute autre ligne clôt la liste à puces en cours. */
    puces = null;

    switch (type) {
      case 'titre':
        noeuds.push(el('h3', { class: 'corps__titre' }, texte));
        break;

      case 'alerte':
        noeuds.push(ligneAccentuee('alerte', '!', 'Point de vigilance :', texte));
        break;

      case 'valide':
        noeuds.push(ligneAccentuee('valide', '✓', 'Validé :', texte));
        break;

      case 'vide':
        /* Séparation purement visuelle : masquée aux lecteurs d'écran,
           qui perçoivent déjà la structure par les éléments eux-mêmes. */
        noeuds.push(el('div', {
          class: 'separateur',
          'aria-hidden': 'true'
        }));
        break;

      default:
        /* Type inconnu : le texte reste lisible plutôt que perdu. */
        if (texte) noeuds.push(el('p', null, texte));
    }
  }

  return noeuds;
}

/**
 * Ligne accentuée, alerte ou validation. L'icône est décorative ; le sens
 * est porté par un préfixe textuel réservé aux lecteurs d'écran, afin que
 * l'information ne repose jamais sur la seule couleur.
 *
 * @param {string} variante 'alerte' | 'valide'
 * @param {string} icone    glyphe décoratif
 * @param {string} prefixe  libellé annoncé, non affiché
 * @param {string} texte
 * @returns {HTMLElement}
 */
function ligneAccentuee(variante, icone, prefixe, texte) {
  return el('p', { class: ['ligne', 'ligne--' + variante] },
    el('span', { class: 'ligne__icone', 'aria-hidden': 'true' }, icone),
    el('span', { class: 'visuellement-cache' }, prefixe + ' '),
    el('span', { class: 'ligne__texte' }, texte)
  );
}

/* -------------------------------------------------------------------------
   11. Sélection
   ------------------------------------------------------------------------- */

/**
 * Sélectionne une annonce : met à jour la liste, le détail et l'URL.
 *
 * @param {string} id
 * @param {boolean} focaliser  replacer le focus sur l'option choisie
 */
function selectionner(id, focaliser) {
  if (!optionsParId.has(id)) return;

  if (id !== idSelection) {
    peindreSelection(id);
    ecrireUrl();
  }

  if (focaliser) {
    const option = optionsParId.get(id);
    if (option) option.focus();
  }
}

/**
 * Applique la sélection au DOM, sans toucher ni à l'URL ni au focus.
 * Séparée de selectionner() pour pouvoir peindre la sélection initiale
 * pendant que le volet de détail est encore hors du document.
 *
 * @param {string} id
 */
function peindreSelection(id) {
  idSelection = id;

  /* Tabulation glissante : une seule option reste dans l'ordre de
     tabulation, les autres n'y sont atteignables qu'aux flèches. */
  for (const [cle, option] of optionsParId) {
    const actif = cle === id;
    option.setAttribute('aria-selected', actif ? 'true' : 'false');
    option.setAttribute('tabindex', actif ? '0' : '-1');
  }

  const annonce = annonces.find((item) => item.id === id);
  if (annonce && refs.detail) {
    monter(refs.detail, contenuDetail(annonce));
  }
}

/* -------------------------------------------------------------------------
   12. Navigation au clavier dans la liste
   ------------------------------------------------------------------------- */

/**
 * Clavier de la listbox, conforme au motif standard :
 *   ↓ / ↑        annonce suivante / précédente (la sélection suit le focus)
 *   Origine/Fin  première / dernière annonce
 *   Entrée       confirme et emmène au volet de détail
 *   Espace       confirme sans quitter la liste
 *
 * @param {KeyboardEvent} evt
 */
function surClavierListe(evt) {
  /* Une combinaison avec une touche de modification appartient au
     navigateur ou au lecteur d'écran, pas à ce composant. */
  if (evt.altKey || evt.ctrlKey || evt.metaKey) return;

  const position = annonces.findIndex((item) => item.id === idSelection);
  if (position < 0) return;

  let cible = null;

  switch (evt.key) {
    case 'ArrowDown':
      cible = Math.min(position + 1, annonces.length - 1);
      break;

    case 'ArrowUp':
      cible = Math.max(position - 1, 0);
      break;

    case 'Home':
      cible = 0;
      break;

    case 'End':
      cible = annonces.length - 1;
      break;

    case 'Enter':
      evt.preventDefault();
      /* Le détail est long : y emmener le focus évite d'avoir à le
         retraverser à la tabulation depuis le haut de la liste. */
      if (refs.detail) refs.detail.focus();
      return;

    case ' ':
    case 'Spacebar':
      evt.preventDefault();
      selectionner(idSelection, true);
      return;

    default:
      return;
  }

  evt.preventDefault();
  selectionner(annonces[cible].id, true);
}

/* -------------------------------------------------------------------------
   13. Bandeau d'alertes
   ------------------------------------------------------------------------- */

/**
 * Bandeau des alertes en cours. Le défilement est intégralement en CSS :
 * la piste contient deux exemplaires identiques de la liste et se translate
 * de la moitié de sa largeur, ce qui boucle sans saut. Le second exemplaire
 * porte aria-hidden — les alertes ne sont énoncées qu'une fois.
 *
 * La fenêtre est focalisable : c'est ce qui permet de mettre le défilement
 * en pause au clavier (`:focus-within` côté CSS), exactement comme le
 * survol le fait à la souris.
 *
 * Les alertes valent pour tout le service : elles ne sont pas filtrées par
 * le pôle actif, et le bandeau reste donc visible d'un périmètre à l'autre.
 *
 * @param {*} alertes  contenu attendu du champ « alertes »
 * @returns {HTMLElement|null} null si aucune alerte : pas de bandeau vide
 */
function construireBandeau(alertes) {
  const textes = Array.isArray(alertes)
    ? alertes.filter((texte) => typeof texte === 'string' && texte.trim() !== '')
    : [];

  if (textes.length === 0) return null;

  return el('div', { class: 'bandeau' },
    el('span', { class: 'badge badge--alerte' },
      el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
      'Alertes'
    ),
    el('div', {
      class: 'bandeau__fenetre',
      tabindex: '0',
      role: 'region',
      'aria-label': 'Alertes en cours du service'
    },
      el('div', { class: 'bandeau__piste' },
        listeAlertes(textes, false),
        listeAlertes(textes, true)
      )
    )
  );
}

/**
 * Un exemplaire de la liste d'alertes.
 *
 * @param {string[]} textes
 * @param {boolean} copie  vrai pour le doublon purement visuel
 * @returns {HTMLElement}
 */
function listeAlertes(textes, copie) {
  return el('ul', {
    class: ['bandeau__liste', copie ? 'bandeau__liste--copie' : null],
    'aria-hidden': copie ? 'true' : null
  },
    textes.map((texte) => el('li', { class: 'bandeau__item' }, texte))
  );
}

/* -------------------------------------------------------------------------
   14. Navigation et sous-navigation
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
          class: 'bouton bouton--discret bouton--compact',
          href: PAGE_DE_POLE[poleActif] || 'index.html'
        }, poleActif === POLE_SERVICE
          ? 'Tableau de bord ETII'
          : 'Espace ' + poleActif))
    )
  );
}

/* -------------------------------------------------------------------------
   15. État dans l'URL
   ------------------------------------------------------------------------- */

/**
 * Écrit le pôle ET l'annonce sélectionnée dans le hash. `replaceState`
 * n'empile pas l'historique et ne fait pas défiler la page (ui.js).
 */
function ecrireUrl() {
  etatUrl.ecrire({
    [CLE_POLE]: poleActif,
    [CLE_URL]: idSelection
  });
}

/**
 * Navigation réelle de l'utilisateur : « Précédent », « Suivant », lien
 * collé. `replaceState` ne déclenche pas cet événement, donc aucune boucle
 * de rétroaction n'est possible avec ecrireUrl().
 *
 * @param {object} etat  résultat de etatUrl.lire()
 */
function surNavigationHash(etat) {
  const code = poleDepuisEtat(etat);

  if (code !== poleActif) {
    poleActif = code;
    majNavigation();
    /* Avant l'arrivée des données — ou après un état d'erreur, qui a
       remplacé la zone — il n'y a rien à repeindre : rendre() relira le
       hash au moment voulu. */
    if (refs.corps && refs.corps.isConnected) peindrePole(true);
    return;
  }

  const id = idDepuisEtat(etat);
  if (id && optionsParId.has(id) && id !== idSelection) {
    selectionner(id, false);
  }
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
 * Identifiant d'annonce lu depuis l'état d'URL.
 *
 * Deux formes sont acceptées : la forme canonique `#pole=ETII&annonce=c02`
 * écrite par cette page, et la forme abrégée `#c02` que produisent
 * d'anciens liens. Un hash abrégé se lit comme une clé sans valeur : c'est
 * cette clé qui porte alors l'identifiant — la clé de pôle, elle, n'est
 * jamais confondue avec un identifiant.
 *
 * @param {object} etat  résultat de etatUrl.lire()
 * @returns {string|null}
 */
function idDepuisEtat(etat) {
  if (!etat || typeof etat !== 'object') return null;

  const canonique = etat[CLE_URL];
  if (typeof canonique === 'string' && canonique !== '') return canonique;

  for (const cle of Object.keys(etat)) {
    if (etat[cle] === '' && cle !== '' && cle !== CLE_POLE) return cle;
  }

  return null;
}

/* -------------------------------------------------------------------------
   16. Petits utilitaires
   ------------------------------------------------------------------------- */

/**
 * Une annonce exploitable : un objet doté au moins d'un identifiant et
 * d'un titre. Les entrées malformées sont écartées silencieusement plutôt
 * que d'interrompre l'affichage des autres.
 *
 * @param {*} annonce
 * @returns {boolean}
 */
function estAnnonce(annonce) {
  return !!annonce && typeof annonce === 'object'
    && typeof annonce.id === 'string' && annonce.id !== ''
    && typeof annonce.titre === 'string';
}

/**
 * Pôle d'origine d'une annonce. Une annonce sans pôle, ou dont le pôle est
 * inconnu, appartient au niveau service.
 *
 * @param {object} annonce
 * @returns {string}
 */
function poleDe(annonce) {
  return normaliserPole(annonce ? annonce.pole : null);
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

/** Accord au pluriel, sans bibliothèque ni table. */
function pluriel(nombre, singulier, pluriels) {
  return nombre > 1 ? pluriels : singulier;
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
 * @param {string} iso  par exemple '2026-09-12'
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
