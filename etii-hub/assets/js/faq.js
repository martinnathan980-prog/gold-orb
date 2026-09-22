/* =========================================================================
   ETII Hub — Base de connaissances (faq.html)

   Une COLONNE DE LECTURE unique, et rien d'autre. Pas de face-à-face liste
   étroite / lecteur : on cherche, on filtre, on déplie — la réponse s'ouvre
   exactement sous la question cliquée. Le regard ne traverse jamais l'écran,
   et la mise en page est la même sur téléphone.

   Ce que fait ce module :
     - construit l'index de recherche (search.js) et classe par pertinence,
       avec surlignage des termes trouvés ;
     - croise DEUX facettes, le pôle et la catégorie, chaque puce portant le
       nombre de questions qu'elle donnerait si on la choisissait ;
     - reflète l'état complet dans le hash : pôle, requête, catégories,
       question dépliée — l'URL se colle et se partage ;
     - propose « vouliez-vous dire… » (suggerer) quand la recherche ne donne
       rien, puis l'appel aux experts ;
     - enregistre LOCALEMENT les questions posées et les affiche, avec leur
       date, le pôle visé et un bouton de suppression.

   Deux règles qui ne se discutent pas :

   1. AUCUNE DONNÉE INVENTÉE. Seul ce qui existe dans faq.json est affiché.
      Un champ absent ou vide devient « à renseigner », jamais une valeur
      plausible.
   2. AUCUN ENVOI RÉSEAU pour une question posée, et donc aucune adresse de
      destination écrite en dur — ni courriel, ni `mailto:`, ni serveur. La
      page le dit en toutes lettres à l'endroit où la question se pose.

   Tout le DOM passe par el()/svg()/frag()/monter() : aucun innerHTML, aucun
   gestionnaire en attribut. Les classes nouvelles sont déclarées dans le
   <style> de faq.html, à partir des seuls jetons de tokens.css.
   ========================================================================= */

import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { creerIndex, rechercher, surligner, suggerer } from './search.js';
import {
  el, svg, frag, monter, surlignerVers, deleguer, debounce,
  etatUrl, stockage, initTheme, initNav, ouvrirModale, toast, annoncer
} from './ui.js';

/* -------------------------------------------------------------------------
   1. Périmètres — l'accord d'équipe, pas une donnée
   ------------------------------------------------------------------------- */

/*
   Les quatre périmètres, dans l'ordre : le service puis ses trois pôles.
   Libellé et métaphore sont de la matière éditoriale ; la couleur est un
   jeton rattaché au code par le <style> de la page. Jamais de valeur brute
   écrite en JavaScript.
*/
const POLES = [
  { cle: 'ETII',  libelle: 'Tout le service', metaphore: 'Les quatre périmètres réunis' },
  { cle: 'ETIIA', libelle: 'ETIIA', metaphore: 'Squelette & ADN' },
  { cle: 'ETIIE', libelle: 'ETIIE', metaphore: 'Système nerveux' },
  { cle: 'ETIII', libelle: 'ETIII', metaphore: 'Structure & harnais' }
];

/** Les seuls codes admis dans le hash. Toute autre valeur retombe sur ETII. */
const CODES_POLE = POLES.map((pole) => pole.cle);

/**
 * Le niveau service : « tout le service », et le repli de toute erreur.
 * C'est aussi une valeur possible du champ `pole` d'une question — celles
 * qui concernent le service entier. La puce « Tout le service » ne filtre
 * donc rien : elle montre les quatre périmètres, y compris ces
 * questions-là, que leur pastille désigne en toutes lettres.
 */
const POLE_SERVICE = 'ETII';

/** Page d'espace correspondant à chaque pôle, pour le lien de retour de la
    rangée transverse. La barre du site, elle, ne marque plus rien ici : cette
    page ne figure pas dedans (`<body data-hors-navigation>`). */
const PAGE_DE_POLE = {
  ETII: 'index.html',
  ETIIA: 'etiia.html',
  ETIIE: 'etiie.html',
  ETIII: 'etiii.html'
};

/** Les trois autres pages transverses, pour la sous-navigation. */
const PAGES_TRANSVERSES = [
  { page: 'reunions.html', libelle: 'Réunions' },
  { page: 'organigramme.html', libelle: 'Organigramme' }
];

/* -------------------------------------------------------------------------
   2. Contrats d'URL, de stockage et d'indexation
   ------------------------------------------------------------------------- */

const CLE_POLE = 'pole';
const CLE_REQUETE = 'q';
const CLE_CATEGORIE = 'cat';
const CLE_QUESTION = 'question';

/** Clé de stockage local des questions posées (ui.js préfixe le nom). */
const CLE_STOCKAGE = 'faq-questions';

/**
 * Champs indexés et leur poids. Le plus fort fait office de « titre » au
 * sens de search.js : c'est l'intitulé de la question qui porte le bonus
 * « la requête commence le titre ».
 */
const CHAMPS_INDEX = [
  { nom: 'question', poids: 6 },
  { nom: 'motsCles', poids: 3 },
  { nom: 'categorie', poids: 2 },
  { nom: 'reponse', poids: 1 }
];

/** Attente avant de relancer la recherche, en millisecondes. */
const DELAI_FRAPPE = 120;

/** La mention unique d'un champ déclaré mais vide. Toujours la même. */
const MENTION_MANQUANT = 'à renseigner';

/* -------------------------------------------------------------------------
   3. Lecture défensive des données
   ------------------------------------------------------------------------- */

/**
 * Texte utilisable, ou null. Une chaîne d'espaces n'est pas une valeur.
 * @param {*} valeur
 * @returns {string|null}
 */
function texteNet(valeur) {
  if (typeof valeur !== 'string') return null;
  const net = valeur.trim();
  return net === '' ? null : net;
}

/**
 * La mention « à renseigner », en un nœud reconnaissable partout.
 * @param {string} [quoi] précision pour les lecteurs d'écran
 * @returns {Element}
 */
function manquant(quoi) {
  return el('span', {
    class: 'champ-manquant',
    ariaLabel: quoi ? quoi + ' : ' + MENTION_MANQUANT : null
  }, MENTION_MANQUANT);
}

/**
 * Le texte, surligné sur les termes de la requête — ou la mention.
 * Le moteur ne produit que des segments de texte brut ; c'est
 * surlignerVers() qui en fait des <mark>. Aucune chaîne ne transite par
 * innerHTML.
 *
 * @param {string|null} texte
 * @param {string} quoi  nom du champ, pour la mention
 * @returns {Node}
 */
function texteSurligne(texte, quoi) {
  if (!texte) return manquant(quoi);
  return surlignerVers(surligner(texte, requete));
}

/**
 * Normalise une entrée de faq.json en une vue d'affichage.
 *
 * Rien n'est inventé : un champ absent, vide ou d'un type inattendu devient
 * `null`, et l'affichage dira « à renseigner ». L'identifiant de repli ne
 * sert qu'à l'index et au pliage — il n'est jamais montré.
 *
 * @param {*} entree
 * @param {number} rang
 * @returns {object|null}
 */
function vueDeQuestion(entree, rang) {
  if (!entree || typeof entree !== 'object') return null;

  const pole = texteNet(entree.pole);
  const motsCles = Array.isArray(entree.motsCles)
    ? entree.motsCles.map(texteNet).filter(Boolean)
    : [];

  return {
    id: texteNet(entree.id) || ('faq-' + rang),
    question: texteNet(entree.question),
    reponse: texteNet(entree.reponse),
    categorie: texteNet(entree.categorie),
    // Un code de pôle inconnu n'est pas corrigé en silence : il est traité
    // comme absent, et la question reste visible au niveau service.
    pole: (pole && CODES_POLE.includes(pole)) ? pole : null,
    motsCles: motsCles
  };
}

/** Libellé lisible d'un code de pôle. */
function libellePole(code) {
  const pole = POLES.find((item) => item.cle === code);
  return pole ? pole.libelle : code;
}

/* -------------------------------------------------------------------------
   4. État de la page
   ------------------------------------------------------------------------- */

/** Toutes les questions, en vues d'affichage. */
let questions = [];

/** Index de recherche, construit une fois au chargement. */
let index = null;

/** Pôle actif — toujours l'un des quatre codes admis. */
let poleActif = POLE_SERVICE;

/** Requête en cours, telle que saisie. */
let requete = '';

/** Catégories retenues. Vide = aucune restriction. */
const categoriesActives = new Set();

/** Identifiant de la question dépliée, ou null. Une seule à la fois. */
let idOuvert = null;

/** Résultats du dernier calcul : [{ doc, score, champsTouches }]. */
let resultats = [];

/** Compteurs croisés de la dernière passe. */
let comptesPole = new Map();
let compteTousPoles = 0;
let comptesCategorie = new Map();

/** Catégories déclarées dans le fichier, triées, sans doublon. */
let categoriesConnues = [];

/** Questions posées et conservées dans ce navigateur. */
let enAttente = [];

/** Nœuds durables, reconstruits à chaque rendu. */
const refs = {
  sousNav: null,
  appel: null,
  attente: null,
  attenteListe: null,
  champ: null,
  compte: null,
  effacer: null,
  liste: null,
  vide: null,
  facettesPole: null,
  facettesCategorie: null
};

/** Identifiant de question -> { item, bouton, panneau }. */
const noeudsParId = new Map();

/* -------------------------------------------------------------------------
   5. Recherche et compteurs croisés
   ------------------------------------------------------------------------- */

/** La question appartient-elle au périmètre actif ? */
function correspondPole(vue) {
  if (poleActif === POLE_SERVICE) return true;
  return vue.pole === poleActif;
}

/** La question est-elle dans l'une des catégories retenues ? */
function correspondCategorie(vue) {
  if (categoriesActives.size === 0) return true;
  return vue.categorie !== null && categoriesActives.has(vue.categorie);
}

/** Incrémente une entrée de compteur. */
function incrementer(carte, cle) {
  if (!cle) return;
  carte.set(cle, (carte.get(cle) || 0) + 1);
}

/**
 * Recalcule les résultats ET les deux jeux de compteurs.
 *
 * Le compteur d'une facette se calcule en ignorant CETTE facette et en
 * appliquant toutes les autres : c'est ce qui rend les nombres justes quand
 * on combine pôle et catégorie. Deux passes suffisent, et la seconde n'est
 * pas refaite pour obtenir les résultats affichés — ils s'en déduisent par
 * un simple filtre, ce qui garantit qu'affichage et compteurs ne peuvent
 * pas diverger.
 */
function calculer() {
  if (!index) {
    resultats = [];
    return;
  }

  // Toutes catégories retenues appliquées, pôle ignoré : base des compteurs
  // de pôle, et source des résultats affichés.
  const baseDesPoles = rechercher(index, requete, { filtre: correspondCategorie });
  // Pôle actif appliqué, catégories ignorées : base des compteurs de
  // catégorie.
  const baseDesCategories = rechercher(index, requete, { filtre: correspondPole });

  resultats = baseDesPoles.filter((resultat) => correspondPole(resultat.doc));

  comptesPole = new Map();
  compteTousPoles = baseDesPoles.length;
  for (const resultat of baseDesPoles) incrementer(comptesPole, resultat.doc.pole);

  comptesCategorie = new Map();
  for (const resultat of baseDesCategories) {
    incrementer(comptesCategorie, resultat.doc.categorie);
  }
}

/** Une facette est-elle active, quelle qu'elle soit ? */
function filtresActifs() {
  return requete.trim() !== ''
    || poleActif !== POLE_SERVICE
    || categoriesActives.size > 0;
}

/* -------------------------------------------------------------------------
   6. Puces de facette
   ------------------------------------------------------------------------- */

/**
 * Une puce de facette : libellé + compteur croisé.
 *
 * L'état est porté par `aria-pressed`, jamais par une classe : information
 * visuelle et information accessible ont une source unique. Une puce dont
 * le compteur vaut zéro reste lisible mais devient inactionnable — sauf si
 * elle est elle-même retenue, sans quoi on ne pourrait plus la relâcher.
 *
 * @param {object} options
 * @returns {Element}
 */
function puceFacette(options) {
  const actif = options.actif === true;
  const compte = typeof options.compte === 'number' ? options.compte : 0;

  return el('li', null,
    el('button', {
      type: 'button',
      class: ['facette', 'facette--compacte'],
      ariaPressed: actif ? 'true' : 'false',
      disabled: (!actif && compte === 0) ? true : null,
      dataset: options.dataset || null,
      onClick: options.onClick
    },
    options.point || null,
    el('span', null, options.libelle),
    el('span', { class: 'facette__compteur' }, String(compte))));
}

/** Point de couleur d'un pôle. Décoratif : le code suit, en toutes lettres. */
function pointPole(code) {
  return el('span', {
    class: 'pole-point',
    dataset: { pole: code },
    ariaHidden: 'true'
  });
}

/** Reconstruit les puces de pôle. */
function rendreFacettesPole() {
  if (!refs.facettesPole) return;

  monter(refs.facettesPole, POLES.map((pole) => {
    const tous = pole.cle === POLE_SERVICE;
    return puceFacette({
      libelle: tous ? pole.libelle : pole.cle,
      compte: tous ? compteTousPoles : (comptesPole.get(pole.cle) || 0),
      actif: poleActif === pole.cle,
      point: tous ? null : pointPole(pole.cle),
      onClick: () => choisirPole(pole.cle)
    });
  }));
}

/** Reconstruit les puces de catégorie. */
function rendreFacettesCategorie() {
  if (!refs.facettesCategorie) return;

  if (categoriesConnues.length === 0) {
    monter(refs.facettesCategorie,
      el('li', null,
        el('p', { class: 'faq__compte sans-marge' },
          'Aucune catégorie n’est renseignée dans le fichier.')));
    return;
  }

  monter(refs.facettesCategorie, categoriesConnues.map((categorie) => puceFacette({
    libelle: categorie,
    compte: comptesCategorie.get(categorie) || 0,
    actif: categoriesActives.has(categorie),
    onClick: () => basculerCategorie(categorie)
  })));
}

/* -------------------------------------------------------------------------
   7. Actions de filtrage
   ------------------------------------------------------------------------- */

/**
 * Change le périmètre. Le focus reste sur la puce cliquée : seules les
 * puces sont reconstruites, et le navigateur retrouve la sienne à l'index
 * équivalent — d'où la reconstruction complète des deux groupes, qui garde
 * l'ordre stable.
 *
 * @param {string} code
 */
function choisirPole(code) {
  const cible = CODES_POLE.includes(code) ? code : POLE_SERVICE;
  if (cible === poleActif) return;
  poleActif = cible;
  rafraichir({ annonce: true, focusFacette: 'pole', valeurFacette: cible });
  initNav();
  rendreSousNav();
}

/**
 * Retient ou relâche une catégorie. Les catégories se cumulent : une
 * question retenue par l'une d'elles suffit.
 * @param {string} categorie
 */
function basculerCategorie(categorie) {
  if (categoriesActives.has(categorie)) categoriesActives.delete(categorie);
  else categoriesActives.add(categorie);
  rafraichir({ annonce: true, focusFacette: 'categorie', valeurFacette: categorie });
}

/** Remet la page à zéro : requête, pôle, catégories. */
function toutEffacer() {
  requete = '';
  poleActif = POLE_SERVICE;
  categoriesActives.clear();
  if (refs.champ) refs.champ.value = '';
  rafraichir({ annonce: true });
  initNav();
  rendreSousNav();
  if (refs.champ) refs.champ.focus();
}

/* -------------------------------------------------------------------------
   8. L'accordéon
   ------------------------------------------------------------------------- */

/** Chevron d'état. Redondant avec aria-expanded, donc masqué aux lecteurs. */
function chevron() {
  return svg('svg', {
    class: 'faq__chevron',
    viewBox: '0 0 16 16',
    'aria-hidden': 'true',
    focusable: 'false'
  },
  svg('path', {
    d: 'M6 3.5 10.5 8 6 12.5',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '1.8',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round'
  }));
}

/** Pastille étiquetée du pôle d'une question, ou la mention. */
function pastillePole(code) {
  if (!code) return manquant('Pôle');
  return el('span', { class: 'pole-pastille', dataset: { pole: code } },
    el('span', { class: 'pole-point', ariaHidden: 'true' }),
    el('span', null, code));
}

/**
 * Une question et sa réponse, pliées.
 *
 * L'intitulé est un vrai <button> dans un <h3> : la structure de titres
 * reste parcourable, et Entrée comme Espace fonctionnent sans code. Le
 * panneau est relié par aria-controls / aria-labelledby, et masqué par
 * l'attribut `hidden` — pas par une classe, pour que les technologies
 * d'assistance le sachent aussi.
 *
 * @param {object} vue
 * @returns {Element}
 */
function itemQuestion(vue) {
  const idBouton = 'faq-bouton-' + vue.id;
  const idPanneau = 'faq-panneau-' + vue.id;
  const ouvert = idOuvert === vue.id;

  const bouton = el('button', {
    type: 'button',
    class: 'faq__bascule',
    id: idBouton,
    ariaExpanded: ouvert ? 'true' : 'false',
    ariaControls: idPanneau,
    dataset: { bascule: vue.id }
  },
  el('span', { class: 'faq__enonce' }, texteSurligne(vue.question, 'Question')),
  chevron());

  const motsCles = vue.motsCles.length
    ? el('ul', { class: 'faq__mots', ariaLabel: 'Mots-clés' },
        vue.motsCles.map((mot) => el('li', null,
          el('span', { class: 'badge badge--neutre badge--contour' },
            surlignerVers(surligner(mot, requete))))))
    : null;

  const panneau = el('div', {
    class: 'faq__reponse',
    id: idPanneau,
    role: 'region',
    ariaLabelledby: idBouton,
    hidden: ouvert ? null : true
  },
  el('p', { class: 'faq__texte' }, texteSurligne(vue.reponse, 'Réponse')),
  el('p', { class: 'faq__meta' },
    pastillePole(vue.pole),
    vue.categorie ? el('span', null, vue.categorie) : manquant('Catégorie'),
    motsCles));

  const item = el('li', {
    class: 'faq__item',
    dataset: { ouvert: ouvert ? 'oui' : 'non' }
  }, el('h3', { class: 'faq__intitule' }, bouton), panneau);

  noeudsParId.set(vue.id, { item: item, bouton: bouton, panneau: panneau });
  return item;
}

/**
 * Déplie une question et replie l'autre. Le DOM est modifié sur place :
 * la liste n'est PAS reconstruite, donc le focus ne bouge pas et la page
 * ne saute pas sous le doigt.
 *
 * @param {string} id
 */
function basculerQuestion(id) {
  idOuvert = (idOuvert === id) ? null : id;

  for (const [cle, noeuds] of noeudsParId) {
    const ouvert = cle === idOuvert;
    noeuds.bouton.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
    noeuds.panneau.hidden = !ouvert;
    noeuds.item.dataset.ouvert = ouvert ? 'oui' : 'non';
  }

  ecrireUrl();
}

/* -------------------------------------------------------------------------
   9. Absence de résultat : suggestion, puis appel aux experts
   ------------------------------------------------------------------------- */

/**
 * Bloc affiché quand rien ne correspond.
 *
 * suggerer() n'est appelé qu'ici, c'est-à-dire uniquement lorsque la
 * recherche a réellement donné zéro résultat : c'est son contrat d'appel.
 *
 * @returns {Element}
 */
function blocAucunResultat() {
  const saisie = requete.trim();
  const suggestion = (index && saisie) ? suggerer(index, saisie) : null;

  const actions = [];

  if (suggestion) {
    actions.push(el('button', {
      type: 'button',
      class: 'bouton bouton--secondaire',
      onClick: () => {
        requete = suggestion;
        if (refs.champ) refs.champ.value = suggestion;
        rafraichir({ annonce: true });
        if (refs.champ) refs.champ.focus();
      }
    }, 'Rechercher « ' + suggestion + ' »'));
  }

  actions.push(el('button', {
    type: 'button',
    class: 'bouton bouton--principal',
    onClick: (evt) => ouvrirDemande(saisie, evt.currentTarget)
  }, 'Poser la question aux experts'));

  if (filtresActifs()) {
    actions.push(el('button', {
      type: 'button',
      class: 'bouton bouton--discret',
      onClick: () => toutEffacer()
    }, 'Effacer les filtres'));
  }

  return el('div', { class: 'etat-vide etat-vide--encadre' },
    el('span', { class: 'etat-vide__illustration', ariaHidden: 'true' }, '∅'),
    el('h3', { class: 'etat-vide__titre' }, 'Aucune question ne correspond'),
    el('p', { class: 'etat-vide__texte mesure' },
      suggestion
        ? 'Rien ne correspond à cette recherche dans le périmètre affiché. '
          + 'Vouliez-vous dire « ' + suggestion + ' » ?'
        : 'Rien ne correspond à cette recherche dans le périmètre affiché. '
          + 'Élargissez les filtres, ou posez la question aux experts : elle '
          + 'sera conservée dans ce navigateur.'),
    el('div', { class: 'etat-vide__actions' }, actions));
}

/* -------------------------------------------------------------------------
   10. Rendu : ce qui change à chaque frappe
   ------------------------------------------------------------------------- */

/** Phrase de décompte, toujours exacte, jamais arrondie. */
function phraseCompte() {
  const total = questions.length;
  const n = resultats.length;

  if (!filtresActifs()) {
    return n === 1
      ? '1 question dans la base de connaissances.'
      : n + ' questions dans la base de connaissances.';
  }
  return (n === 0 ? 'Aucune question' : (n === 1 ? '1 question' : n + ' questions'))
    + ' sur ' + total
    + ' — périmètre ' + libellePole(poleActif)
    + (categoriesActives.size
      ? ', catégories : ' + Array.from(categoriesActives).join(', ')
      : '')
    + '.';
}

/**
 * Recalcule, puis repeint ce qui dépend de l'état : puces, décompte, liste.
 * Le reste de la page — barre de recherche, appel aux experts, questions en
 * attente — est durable et n'est jamais reconstruit.
 *
 * @param {object} [options]
 *        annonce        annoncer le nombre de résultats aux lecteurs d'écran
 *        focusFacette   'pole' | 'categorie' : refocaliser la puce agie
 *        valeurFacette  valeur de la puce à refocaliser
 */
function rafraichir(options) {
  const reglages = options || {};

  calculer();

  // La question dépliée n'a plus lieu d'être si elle a quitté la liste.
  if (idOuvert && !resultats.some((resultat) => resultat.doc.id === idOuvert)) {
    idOuvert = null;
  }

  rendreFacettesPole();
  rendreFacettesCategorie();

  if (refs.compte) refs.compte.textContent = phraseCompte();
  if (refs.effacer) refs.effacer.hidden = !filtresActifs();

  noeudsParId.clear();
  if (refs.liste) {
    monter(refs.liste, resultats.map((resultat) => itemQuestion(resultat.doc)));
    refs.liste.hidden = resultats.length === 0;
  }
  if (refs.vide) {
    monter(refs.vide, resultats.length === 0 ? blocAucunResultat() : null);
    refs.vide.hidden = resultats.length !== 0;
  }

  ecrireUrl();

  if (reglages.annonce) annoncer(phraseCompte());

  // Une puce reconstruite perd le focus : on le lui rend, pour que le
  // parcours au clavier ne reparte pas du haut de la page à chaque clic.
  if (reglages.focusFacette) rendreFocusFacette(reglages);
}

/**
 * Replace le focus sur la puce qui vient d'être agie.
 * @param {object} reglages
 */
function rendreFocusFacette(reglages) {
  const hote = reglages.focusFacette === 'pole'
    ? refs.facettesPole
    : refs.facettesCategorie;
  if (!hote) return;

  const boutons = Array.from(hote.querySelectorAll('button'));
  const cible = reglages.focusFacette === 'pole'
    ? boutons[CODES_POLE.indexOf(reglages.valeurFacette)]
    : boutons[categoriesConnues.indexOf(reglages.valeurFacette)];

  if (cible && typeof cible.focus === 'function' && !cible.disabled) cible.focus();
}

/* -------------------------------------------------------------------------
   11. Construction de la colonne de lecture
   ------------------------------------------------------------------------- */

/** La barre de recherche, seule commande du haut de page. */
function barreRecherche() {
  const relancer = debounce(() => {
    requete = refs.champ ? refs.champ.value : '';
    rafraichir({ annonce: true });
  }, DELAI_FRAPPE);

  const champ = el('input', {
    class: 'recherche__champ',
    type: 'search',
    id: 'faq-champ',
    name: 'q',
    placeholder: 'Rechercher une question, un mot-clé…',
    autocomplete: 'off',
    spellcheck: 'false',
    value: requete,
    ariaLabel: 'Rechercher dans la base de connaissances',
    ariaDescribedby: 'faq-compte',
    onInput: relancer,
    onKeyDown: (evt) => {
      if (evt.key !== 'Escape') return;
      if (champ.value === '') return;
      evt.preventDefault();
      champ.value = '';
      requete = '';
      rafraichir({ annonce: true });
    }
  });
  refs.champ = champ;

  return el('div', { class: 'faq__barre' },
    el('div', { class: 'recherche recherche--proeminente' },
      el('span', { class: 'recherche__icone', ariaHidden: 'true' }, '⌕'),
      champ,
      el('button', {
        type: 'button',
        class: 'recherche__effacer bouton bouton--icone bouton--compact',
        ariaLabel: 'Effacer la recherche',
        onClick: () => {
          champ.value = '';
          requete = '';
          rafraichir({ annonce: true });
          champ.focus();
        }
      }, el('span', { ariaHidden: 'true' }, '×')),
      el('kbd', { class: 'recherche__raccourci', ariaHidden: 'true' }, '/')));
}

/** Les deux groupes de facettes, chacun annoncé par son intitulé. */
function blocFacettes() {
  const idPole = 'faq-legende-pole';
  const idCategorie = 'faq-legende-categorie';

  refs.facettesPole = el('ul', { class: 'facettes', ariaLabelledby: idPole });
  refs.facettesCategorie = el('ul', { class: 'facettes', ariaLabelledby: idCategorie });

  return el('div', { class: 'faq__filtres' },
    el('div', { class: 'faq__groupe' },
      el('p', { class: 'faq__legende', id: idPole }, 'Pôle'),
      refs.facettesPole),
    el('div', { class: 'faq__groupe' },
      el('p', { class: 'faq__legende', id: idCategorie }, 'Catégorie'),
      refs.facettesCategorie));
}

/** La ligne de décompte et le bouton de remise à zéro. */
function blocResume() {
  refs.compte = el('p', { class: 'faq__compte', id: 'faq-compte' });
  refs.effacer = el('button', {
    type: 'button',
    class: 'bouton bouton--discret bouton--compact',
    hidden: true,
    onClick: () => toutEffacer()
  }, 'Effacer les filtres');

  return el('div', { class: 'faq__resume' }, refs.compte, refs.effacer);
}

/**
 * Construit la colonne complète dans #zone-faq, puis pose les écouteurs
 * délégués — un seul pour toute la liste, jamais un par question.
 *
 * @param {Element} conteneur
 */
function construireColonne(conteneur) {
  refs.liste = el('ul', { class: 'faq__liste' });
  refs.vide = el('div', { hidden: true });

  monter(conteneur,
    barreRecherche(),
    blocFacettes(),
    blocResume(),
    refs.liste,
    refs.vide);

  deleguer(refs.liste, '[data-bascule]', 'click', (evt, cible) => {
    basculerQuestion(cible.dataset.bascule);
  });

  deleguer(refs.liste, '[data-bascule]', 'keydown', (evt, cible) => {
    naviguerListe(evt, cible);
  });
}

/* -------------------------------------------------------------------------
   12. Clavier
   ------------------------------------------------------------------------- */

/**
 * Flèches, Début, Fin et Échap dans l'accordéon.
 * Entrée et Espace sont assurés par le <button> natif : rien à écrire.
 *
 * @param {KeyboardEvent} evt
 * @param {Element} cible  le bouton qui a la main
 */
function naviguerListe(evt, cible) {
  const boutons = Array.from(refs.liste.querySelectorAll('[data-bascule]'));
  const position = boutons.indexOf(cible);
  if (position === -1) return;

  let suivant = null;
  if (evt.key === 'ArrowDown') suivant = boutons[position + 1] || boutons[0];
  else if (evt.key === 'ArrowUp') suivant = boutons[position - 1] || boutons[boutons.length - 1];
  else if (evt.key === 'Home') suivant = boutons[0];
  else if (evt.key === 'End') suivant = boutons[boutons.length - 1];
  else if (evt.key === 'Escape' && cible.getAttribute('aria-expanded') === 'true') {
    evt.preventDefault();
    basculerQuestion(cible.dataset.bascule);
    return;
  } else {
    return;
  }

  if (suivant) {
    evt.preventDefault();
    suivant.focus();
  }
}

/**
 * « / » place le curseur dans le champ de recherche, où que l'on soit —
 * sauf si l'on est déjà en train d'écrire quelque part.
 */
function raccourciGlobal() {
  document.addEventListener('keydown', (evt) => {
    if (evt.key !== '/' || evt.ctrlKey || evt.metaKey || evt.altKey) return;

    const actif = document.activeElement;
    if (actif && (actif.isContentEditable
      || /^(input|textarea|select)$/i.test(actif.tagName || ''))) return;

    if (!refs.champ) return;
    evt.preventDefault();
    refs.champ.focus();
    refs.champ.select();
  });
}

/* -------------------------------------------------------------------------
   13. Appel aux experts — le bloc durable
   ------------------------------------------------------------------------- */

/**
 * Le bloc « une question sans réponse ? ». Il vit hors de la zone de
 * données : il reste disponible même si faq.json est introuvable, ce qui
 * est précisément le moment où l'on a le plus besoin de demander.
 */
function rendreAppel() {
  if (!refs.appel) return;

  monter(refs.appel,
    el('div', { class: 'faq__appel' },
      el('div', { class: 'faq__appel-texte pile pile--serree' },
        el('h2', { class: 'sans-marge', id: 'faq-appel-titre' },
          'Une question sans réponse ?'),
        el('p', { class: 'texte-doux sans-marge' },
          'Décrivez-la, indiquez le pôle concerné, et elle rejoindra votre '
          + 'liste ci-dessous.')),
      el('button', {
        type: 'button',
        class: 'bouton bouton--principal faq__demander',
        onClick: (evt) => ouvrirDemande(requete.trim(), evt.currentTarget)
      }, 'Poser une question aux experts')));
}

/* -------------------------------------------------------------------------
   14. La modale « Poser une question aux experts »
   ------------------------------------------------------------------------- */

/**
 * Formulaire de question, dans une modale accessible fournie par ui.js :
 * role="dialog", aria-modal, titre relié, piège de focus réel, fermeture
 * par Échap et par le fond, focus rendu au bouton d'origine.
 *
 * @param {string} [texteInitial] la recherche en cours, pour ne pas la
 *        retaper — c'est bien la saisie de la personne, pas une invention
 * @param {Element} [declencheur]
 */
function ouvrirDemande(texteInitial, declencheur) {
  let champQuestion = null;
  let champPole = null;
  let champContexte = null;
  let groupeQuestion = null;
  let messageErreur = null;

  /** Vérifie la saisie ; en cas d'échec, le dit et rend la main. */
  function valider() {
    const texte = champQuestion ? champQuestion.value.trim() : '';

    if (texte === '') {
      if (groupeQuestion) groupeQuestion.classList.add('champ--erreur');
      if (messageErreur) messageErreur.hidden = false;
      if (champQuestion) {
        champQuestion.setAttribute('aria-invalid', 'true');
        champQuestion.focus();
      }
      return false;
    }

    enregistrerQuestion({
      question: texte,
      pole: champPole ? champPole.value : POLE_SERVICE,
      contexte: champContexte ? champContexte.value.trim() : ''
    });
    return true;
  }

  const idAide = 'faq-demande-aide';
  const idErreur = 'faq-demande-erreur';

  ouvrirModale({
    titre: 'Poser une question aux experts',
    classe: 'modale--etroite',
    declencheur: declencheur || null,
    contenu: (api) => {
      messageErreur = el('p', {
        class: 'champ__erreur',
        id: idErreur,
        role: 'alert',
        hidden: true
      }, 'Écrivez votre question avant d’enregistrer.');

      champQuestion = el('textarea', {
        class: 'champ__controle',
        id: 'faq-demande-question',
        name: 'question',
        rows: 4,
        required: true,
        value: typeof texteInitial === 'string' ? texteInitial : '',
        ariaDescribedby: idAide + ' ' + idErreur,
        onInput: () => {
          if (groupeQuestion) groupeQuestion.classList.remove('champ--erreur');
          if (messageErreur) messageErreur.hidden = true;
          champQuestion.removeAttribute('aria-invalid');
        }
      });

      groupeQuestion = el('p', { class: 'champ' },
        el('label', { class: 'champ__etiquette', for: 'faq-demande-question' },
          'Votre question ',
          el('span', { class: 'champ__requis', ariaHidden: 'true' }, '*')),
        champQuestion,
        el('span', { class: 'champ__aide', id: idAide },
          'Formulez-la comme vous la poseriez à l’oral : c’est ce texte qui '
          + 'sera conservé, mot pour mot.'),
        messageErreur);

      champPole = el('select', {
        class: 'champ__select',
        id: 'faq-demande-pole',
        name: 'pole',
        value: poleActif
      }, POLES.map((pole) => el('option', {
        value: pole.cle,
        selected: pole.cle === poleActif ? true : null
      }, pole.cle === POLE_SERVICE
        ? pole.libelle
        : pole.cle + ' — ' + pole.metaphore)));

      champContexte = el('textarea', {
        class: 'champ__controle',
        id: 'faq-demande-contexte',
        name: 'contexte',
        rows: 3
      });

      // Le <form> n'a aucune action ni méthode : il n'existe que pour que
      // la touche Entrée d'un champ déclenche la même validation que le
      // bouton. Rien ne part sur le réseau, jamais.
      return el('form', {
        class: 'pile',
        novalidate: true,
        onSubmit: (evt) => {
          evt.preventDefault();
          if (valider()) api.fermer('validation');
        }
      },
      groupeQuestion,

      el('p', { class: 'champ' },
        el('label', { class: 'champ__etiquette', for: 'faq-demande-pole' },
          'Pôle concerné'),
        champPole),

      el('p', { class: 'champ' },
        el('label', { class: 'champ__etiquette', for: 'faq-demande-contexte' },
          'Contexte (facultatif)'),
        champContexte,
        el('span', { class: 'champ__aide' },
          'Ce qui aiderait à répondre : ce que vous avez déjà cherché, le '
          + 'cas rencontré.')),

      el('p', { class: 'faq__note' },
        'Ce portail est une démonstration hors ligne : il n’a aucune '
        + 'destination configurée. Votre question ne part donc nulle part — '
        + 'ni message, ni courriel, ni requête vers un serveur. Elle est '
        + 'enregistrée dans ce navigateur, sur cet appareil seulement, et '
        + 'vous pouvez la supprimer à tout moment. Tant qu’une destination '
        + 'n’aura pas été configurée par l’équipe qui administre le portail, '
        + 'aucun envoi n’aura lieu.'));
    },
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      {
        libelle: 'Enregistrer la question',
        variante: 'principal',
        ferme: false,
        onClick: (evt, api) => { if (valider()) api.fermer('validation'); }
      }
    ]
  });
}

/* -------------------------------------------------------------------------
   15. Questions en attente — stockage local, aucun réseau
   ------------------------------------------------------------------------- */

/** Relit la liste conservée, en se méfiant de tout. */
function lireAttente() {
  const brut = stockage.lire(CLE_STOCKAGE, []);
  if (!Array.isArray(brut)) return [];

  return brut
    .map((entree, rang) => {
      if (!entree || typeof entree !== 'object') return null;
      const question = texteNet(entree.question);
      if (!question) return null;
      const pole = texteNet(entree.pole);
      return {
        id: texteNet(entree.id) || ('attente-' + rang),
        question: question,
        contexte: texteNet(entree.contexte),
        pole: (pole && CODES_POLE.includes(pole)) ? pole : null,
        date: texteNet(entree.date)
      };
    })
    .filter(Boolean);
}

/** Écrit la liste, sans jamais faire échouer la page si le stockage refuse. */
function ecrireAttente() {
  const enregistre = stockage.ecrire(CLE_STOCKAGE, enAttente);
  if (!enregistre) {
    toast('Ce navigateur refuse le stockage local : la question restera '
      + 'affichée jusqu’à la fermeture de l’onglet.', 'alerte');
  }
}

/** Compteur d'appoint : deux questions posées dans la même milliseconde. */
let rangAttente = 0;

/**
 * Enregistre une question posée et rafraîchit la section.
 * @param {{question:string, pole:string, contexte:string}} saisie
 */
function enregistrerQuestion(saisie) {
  rangAttente += 1;

  enAttente.unshift({
    id: 'q-' + Date.now() + '-' + rangAttente,
    question: saisie.question,
    contexte: saisie.contexte || null,
    pole: CODES_POLE.includes(saisie.pole) ? saisie.pole : POLE_SERVICE,
    date: new Date().toISOString()
  });

  ecrireAttente();
  rendreAttente();
  toast('Question enregistrée dans ce navigateur. Aucun envoi n’a eu lieu.',
    'succes');
  annoncer('Question ajoutée à vos questions en attente.');
}

/**
 * Supprime une question, après confirmation explicite : une action
 * destructrice ne se déclenche jamais d'un seul clic (SPEC §6.5).
 *
 * @param {string} id
 * @param {Element} declencheur
 */
function supprimerQuestion(id, declencheur) {
  const cible = enAttente.find((entree) => entree.id === id);
  if (!cible) return;

  ouvrirModale({
    titre: 'Supprimer cette question ?',
    classe: 'modale--etroite',
    declencheur: declencheur || null,
    contenu: () => frag(
      el('p', { class: 'sans-marge texte-doux' },
        'Elle sera retirée de ce navigateur. Cette suppression est '
        + 'définitive.'),
      el('p', { class: 'faq__attente-texte' }, cible.question)),
    actions: [
      { libelle: 'Annuler', variante: 'secondaire' },
      {
        libelle: 'Supprimer',
        variante: 'danger',
        onClick: () => {
          enAttente = enAttente.filter((entree) => entree.id !== id);
          ecrireAttente();
          rendreAttente();
          annoncer('Question supprimée.');
        }
      }
    ]
  });
}

/** Date longue en français, ou la mention si la date est illisible. */
function noeudDate(iso) {
  if (!iso) return manquant('Date');

  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return manquant('Date');

  let libelle;
  try {
    libelle = new Intl.DateTimeFormat('fr-FR', {
      day: 'numeric', month: 'long', year: 'numeric'
    }).format(date);
  } catch (_e) {
    libelle = iso.slice(0, 10);
  }
  return el('time', { datetime: iso }, libelle);
}

/** Repeint la section « Vos questions en attente ». */
function rendreAttente() {
  if (!refs.attente || !refs.attenteListe) return;

  refs.attente.hidden = enAttente.length === 0;
  if (enAttente.length === 0) {
    monter(refs.attenteListe);
    return;
  }

  monter(refs.attenteListe, enAttente.map((entree) => el('li', {
    class: 'faq__attente-item'
  },
  el('div', { class: 'faq__attente-haut' },
    el('p', { class: 'faq__attente-texte' }, entree.question),
    // Volontairement neutre : la seule couleur vive de l'écran est celle
    // de l'appel aux experts. Le caractère destructeur est porté par le
    // mot et par la confirmation, pas par un rouge de plus.
    el('button', {
      type: 'button',
      class: 'bouton bouton--secondaire bouton--compact',
      dataset: { supprimer: entree.id },
      ariaLabel: 'Supprimer cette question en attente'
    }, 'Supprimer')),

  entree.contexte
    ? el('p', { class: 'faq__attente-contexte' }, entree.contexte)
    : null,

  el('p', { class: 'faq__attente-meta' },
    pastillePole(entree.pole),
    noeudDate(entree.date),
    el('span', null, 'En attente — aucun envoi')))));
}

/* -------------------------------------------------------------------------
   16. État dans l'URL
   ------------------------------------------------------------------------- */

/** Écrit le périmètre, la recherche, les catégories et la question dépliée. */
function ecrireUrl() {
  etatUrl.ecrire({
    [CLE_POLE]: poleActif,
    [CLE_REQUETE]: requete.trim(),
    [CLE_CATEGORIE]: Array.from(categoriesActives),
    [CLE_QUESTION]: idOuvert
  });
}

/**
 * Applique un état venu de l'URL. Toute valeur inconnue est ignorée sans
 * erreur : un lien vieilli ouvre une page utilisable, jamais une page
 * cassée.
 *
 * @param {object} etat  résultat de etatUrl.lire()
 */
function appliquerUrl(etat) {
  const source = etat || {};

  const pole = typeof source[CLE_POLE] === 'string' ? source[CLE_POLE] : '';
  poleActif = CODES_POLE.includes(pole) ? pole : POLE_SERVICE;

  requete = typeof source[CLE_REQUETE] === 'string' ? source[CLE_REQUETE] : '';
  if (refs.champ) refs.champ.value = requete;

  categoriesActives.clear();
  const brutCategories = source[CLE_CATEGORIE];
  const listeCategories = Array.isArray(brutCategories)
    ? brutCategories
    : (typeof brutCategories === 'string' && brutCategories ? [brutCategories] : []);
  for (const categorie of listeCategories) {
    if (categoriesConnues.includes(categorie)) categoriesActives.add(categorie);
  }

  const question = typeof source[CLE_QUESTION] === 'string' ? source[CLE_QUESTION] : '';
  idOuvert = questions.some((vue) => vue.id === question) ? question : null;
}

/* -------------------------------------------------------------------------
   17. Navigation et sous-navigation
   ------------------------------------------------------------------------- */

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
          : 'Espace ' + poleActif))));
}

/* -------------------------------------------------------------------------
   18. Amorçage
   ------------------------------------------------------------------------- */

/**
 * Rendu de la zone de données : index, colonne, premier affichage.
 * @param {object} donnees contenu de faq.json
 * @param {Element} conteneur
 */
function rendreDonnees(donnees, conteneur) {
  verifierForme(donnees, { questions: 'tableau' }, 'faq.json');

  questions = donnees.questions
    .map((entree, rang) => vueDeQuestion(entree, rang))
    .filter(Boolean);

  categoriesConnues = Array.from(new Set(
    questions.map((vue) => vue.categorie).filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'fr'));

  index = creerIndex(questions, CHAMPS_INDEX);

  construireColonne(conteneur);

  // L'URL est relue MAINTENANT : les catégories connues et les
  // identifiants de questions n'existaient pas avant le chargement.
  appliquerUrl(etatUrl.lire());
  if (refs.champ) refs.champ.value = requete;

  initNav();
  rendreSousNav();
  rafraichir({ annonce: false });

  // Une question désignée par le lien d'un espace de pôle se déplie et se
  // place sous les yeux, sans voler le focus.
  if (idOuvert && noeudsParId.has(idOuvert)) {
    const noeuds = noeudsParId.get(idOuvert);
    try { noeuds.item.scrollIntoView({ block: 'center' }); } catch (_e) { /* ignoré */ }
  }
}

function demarrer() {
  initTheme();

  refs.sousNav = document.getElementById('faq-sous-nav');
  refs.appel = document.getElementById('faq-appel');
  refs.attente = document.getElementById('faq-attente');
  refs.attenteListe = document.getElementById('faq-attente-liste');

  // Le pôle est lu tout de suite pour que la navigation et la
  // sous-navigation soient justes dès la première image, avant même que
  // faq.json ne réponde.
  const etatInitial = etatUrl.lire();
  const poleInitial = typeof etatInitial[CLE_POLE] === 'string' ? etatInitial[CLE_POLE] : '';
  poleActif = CODES_POLE.includes(poleInitial) ? poleInitial : POLE_SERVICE;
  initNav();
  rendreSousNav();

  // Ces deux sections vivent hors de la zone de données : elles restent
  // utilisables même si faq.json est introuvable ou invalide.
  rendreAppel();
  enAttente = lireAttente();
  rendreAttente();

  // Venu d'une page de pôle par « Poser une question aux experts » : le
  // hash porte proposer=1. La fenêtre s'ouvre, pôle présélectionné ; la clé
  // disparaît de l'URL à la première écriture d'état.
  if (etatInitial.proposer === '1') {
    requestAnimationFrame(() => ouvrirDemande('', null));
  }

  deleguer(refs.attenteListe, '[data-supprimer]', 'click', (evt, cible) => {
    supprimerQuestion(cible.dataset.supprimer, cible);
  });

  raccourciGlobal();

  avecEtat('#zone-faq', () => chargerDonnees('faq'), rendreDonnees, {
    squelette: 4,
    texteChargement: 'Chargement de la base de connaissances…',
    titreErreur: 'Base de connaissances indisponible',
    titreVide: 'Aucune question publiée',
    texteVide: 'Le fichier ne contient encore aucune question. Vous pouvez '
      + 'tout de même poser la vôtre : elle sera conservée dans ce '
      + 'navigateur.',
    estVide: (donnees) => !donnees
      || !Array.isArray(donnees.questions)
      || donnees.questions.length === 0
  });

  // « Précédent », « Suivant », lien collé : replaceState ne déclenche pas
  // cet événement, donc aucune boucle de rétroaction n'est possible.
  etatUrl.ecouter((etat) => {
    if (!index) return;
    appliquerUrl(etat);
    initNav();
    rendreSousNav();
    rafraichir({ annonce: false });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', demarrer, { once: true });
} else {
  demarrer();
}
