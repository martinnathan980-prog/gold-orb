/* =========================================================================
   ETII Hub — Module du Communication Center (SPEC.md §4.2)

   Quatre responsabilités, et rien d'autre :

     1. Démarrer le thème et marquer la page courante dans la navigation.
     2. Charger communications.json et en rendre les trois états —
        chargement, erreur, vide — via avecEtat() de data.js.
     3. Afficher la liste chronologique des annonces à gauche et le détail
        de l'annonce sélectionnée à droite.
     4. Refléter la sélection dans le hash de l'URL, et la restaurer au
        chargement comme au retour arrière du navigateur.

   Points de conception notables :

   - La liste est une VRAIE liste d'options (role="listbox" / role="option")
     à tabulation glissante : une seule option est dans l'ordre de
     tabulation, les flèches déplacent le focus et la sélection, Entrée
     emmène au détail. L'état est porté par aria-selected, jamais par une
     classe posée ici — l'information visuelle et l'information accessible
     ont une source unique.

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
   Constantes d'affichage
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

/** Clé sous laquelle la sélection est écrite dans le hash de l'URL. */
const CLE_URL = 'annonce';

/** Nombre de gabarits d'option affichés pendant le chargement. */
const SQUELETTES_LISTE = 4;

/* -------------------------------------------------------------------------
   État du module
   ------------------------------------------------------------------------- */

/** Annonces triées, de la plus récente à la plus ancienne. */
let annonces = [];

/** Identifiant de l'annonce actuellement sélectionnée, ou null. */
let idSelection = null;

/** Identifiant d'annonce -> élément <li role="option"> correspondant. */
const optionsParId = new Map();

/** Conteneur du détail, rempli à chaque changement de sélection. */
let voletDetail = null;

/* -------------------------------------------------------------------------
   1. Démarrage
   ------------------------------------------------------------------------- */

initTheme();
initNav('communication');

/* Enregistré UNE seule fois, hors du rendu : un clic sur « Réessayer »
   relance le rendu, il ne doit pas empiler les écouteurs. `replaceState`
   ne déclenche pas hashchange, donc seules les vraies navigations — retour
   arrière, lien collé — arrivent ici. */
etatUrl.ecouter(function (etat) {
  const id = idDepuisEtat(etat);
  if (id && optionsParId.has(id) && id !== idSelection) {
    selectionner(id, false);
  }
});

demarrer();

/**
 * Lance le cycle chargement -> succès | vide | erreur sur la zone de page.
 * avecEtat() ne rejette jamais : quelle que soit l'issue, la page reste
 * navigable et l'erreur est lisible et actionnable.
 */
function demarrer() {
  avecEtat(
    document.getElementById('zone-communication'),

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
      estVide: (brut) => !brut || !Array.isArray(brut.annonces)
        || brut.annonces.filter(estAnnonce).length === 0
    }
  );
}

/* -------------------------------------------------------------------------
   2. État de chargement
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
   3. Rendu principal
   ------------------------------------------------------------------------- */

/**
 * Construit le bandeau d'alertes puis les deux volets, et applique la
 * sélection initiale.
 *
 * La sélection initiale est peinte AVANT l'insertion dans le document :
 * le volet de détail est une région live, et une région remplie hors du
 * document n'énonce rien. On évite ainsi de faire lire toute l'annonce au
 * chargement de la page — seuls les changements ultérieurs sont annoncés.
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
  annonces = donnees.annonces
    .filter(estAnnonce)
    .sort(function (a, b) {
      const parDate = String(b.date).localeCompare(String(a.date));
      return parDate !== 0 ? parDate : String(a.id).localeCompare(String(b.id));
    });

  optionsParId.clear();
  idSelection = null;

  const liste = construireListe();
  voletDetail = construireVoletDetail();

  /* Sélection initiale : celle du hash si elle désigne une annonce
     existante, la plus récente sinon. */
  const demande = idDepuisEtat(etatUrl.lire());
  const initiale = (demande && optionsParId.has(demande))
    ? demande
    : annonces[0].id;

  peindreSelection(initiale);

  monter(conteneur,
    construireBandeau(donnees.alertes),
    el('div', { class: 'comm' },
      el('div', { class: 'comm__volet comm__liste pile pile--serree' },
        el('div', { class: 'rangee rangee--serree rangee--entre' },
          el('h2', { class: 'texte-sm texte-doux gras', id: 'titre-liste' },
            'Annonces publiées'),
          el('span', { class: 'pastille' }, String(annonces.length))
        ),
        liste
      ),
      voletDetail
    )
  );

  /* Le hash est normalisé même quand il était absent ou approximatif :
     l'URL devient partageable telle quelle. */
  etatUrl.ecrire({ [CLE_URL]: initiale });

  annoncer(annonces.length > 1
    ? annonces.length + ' annonces chargées. Utilisez les flèches haut et '
      + 'bas pour parcourir la liste.'
    : 'Une annonce chargée.');
}

/* -------------------------------------------------------------------------
   4. Volet de gauche : la liste d'options
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
    'aria-labelledby': 'titre-liste',
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
 * Une option de la liste : date, pastille de statut, catégorie, titre,
 * résumé. Aucun élément interactif à l'intérieur — une option de listbox
 * ne contient jamais de lien ni de bouton.
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
      annonce.categorie ? el('span', null, annonce.categorie) : null
    ),

    el('p', { class: 'carte__titre annonce__titre' }, annonce.titre),

    annonce.resume
      ? el('p', { class: 'annonce__resume' }, annonce.resume)
      : null
  );
}

/* -------------------------------------------------------------------------
   5. Volet de droite : le détail
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
 * Contenu du détail : titre, date, catégorie, statut, résumé, puis le
 * corps typé.
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
   6. Sélection
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
    etatUrl.ecrire({ [CLE_URL]: id });
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
  if (annonce && voletDetail) {
    monter(voletDetail, contenuDetail(annonce));
  }
}

/* -------------------------------------------------------------------------
   7. Navigation au clavier dans la liste
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
      if (voletDetail) voletDetail.focus();
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
   8. Bandeau d'alertes
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
   9. Petits utilitaires
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
 * Identifiant d'annonce lu depuis l'état d'URL.
 *
 * Deux formes sont acceptées : la forme canonique `#annonce=c02` écrite
 * par cette page, et la forme abrégée `#c02` que produisent les liens
 * d'autres pages du site. Un hash abrégé se lit comme une clé sans
 * valeur : c'est cette clé qui porte alors l'identifiant.
 *
 * @param {object} etat  résultat de etatUrl.lire()
 * @returns {string|null}
 */
function idDepuisEtat(etat) {
  if (!etat || typeof etat !== 'object') return null;

  const canonique = etat[CLE_URL];
  if (typeof canonique === 'string' && canonique !== '') return canonique;

  for (const cle of Object.keys(etat)) {
    if (etat[cle] === '' && cle !== '') return cle;
  }

  return null;
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
