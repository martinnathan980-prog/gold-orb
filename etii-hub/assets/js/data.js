/* =========================================================================
   ETII Hub — Accès aux données (SPEC.md §3, « Contrat de données »)

   Unique point d'entrée vers assets/data/*.json. Aucune page ne doit
   appeler fetch() elle-même : tout passe par ici, afin que le cache, le
   délai maximal et surtout les messages d'erreur soient identiques
   partout.

   API publique :
     chargerDonnees(nom, options)            -> Promise<objet>
     avecEtat(conteneur, source, rendu, opt) -> Promise<resultat>  (ne rejette jamais)
     verifierForme(objet, forme, contexte)   -> objet  (ou lève une erreur)
     viderCache(nom)                         -> void

   Principes de conception :
   - La PROMESSE est mémoïsée, pas seulement son résultat : deux pages (ou
     deux composants d'une même page) qui demandent le même fichier au même
     instant ne déclenchent qu'une seule requête réseau.
   - Une promesse rejetée est immédiatement retirée du cache : un échec ne
     doit jamais être mis en cache, sinon le bouton « Réessayer » ne
     réessaierait rien.
   - Toute erreur remonte avec un message en français, complet, affichable
     tel quel à l'utilisateur, et un code machine (err.code) pour les rares
     cas où une page veut réagir différemment selon la cause.
   - avecEtat() ne rejette JAMAIS. Une page dont les données manquent
     affiche une erreur propre ; elle ne casse ni la navigation, ni le
     reste du site.

   Dépendance : uniquement ./ui.js, dont on n'utilise que deux helpers —
     el(balise, { classe, texte })  -> Element  (importé sous le nom creerElement)
     vider(noeud)                             -> void
   Tout le reste (attributs, enfants) est posé ici avec les API DOM
   natives. Aucun innerHTML : l'injection HTML est structurellement
   impossible (SPEC §8).
   ========================================================================= */

import { el as creerElement, vider } from './ui.js';

/* -------------------------------------------------------------------------
   Constantes de réglage
   ------------------------------------------------------------------------- */

/** Délai maximal par défaut d'un chargement, en millisecondes. */
const DELAI_DEFAUT = 8000;

/** Noms de jeux de données acceptés : pas de chemin, pas de traversée. */
const NOM_VALIDE = /^[a-z0-9][a-z0-9_-]*$/;

/** Nombre de gabarits de squelette affichés par défaut pendant l'attente. */
const SQUELETTES_DEFAUT = 3;

/*
   Le dossier des données est résolu à partir de l'URL du module lui-même :
   assets/js/data.js -> assets/data/. Les pages peuvent donc vivre à
   n'importe quelle profondeur sans qu'aucun chemin ne soit à réécrire.
*/
const DOSSIER_DONNEES = new URL('../data/', import.meta.url);

/** Cache mémoire : nom du jeu de données -> Promise en vol ou résolue. */
const CACHE = new Map();

/** Vrai lorsque la page est ouverte par double-clic (protocole file://). */
const EST_FICHIER_LOCAL =
  typeof location !== 'undefined' && location.protocol === 'file:';

/* -------------------------------------------------------------------------
   1. Erreurs
   ------------------------------------------------------------------------- */

/**
 * Fabrique une Error dont le message est directement affichable.
 *
 * @param {string} code   'introuvable' | 'illisible' | 'delai' | 'bloque'
 *                        | 'reseau' | 'http' | 'nom' | 'forme'
 * @param {string} message texte en français, phrase complète
 * @param {*} [cause]      erreur d'origine, conservée pour la console
 * @returns {Error}
 */
function erreurDonnees(code, message, cause) {
  const erreur = new Error(message);
  erreur.name = 'ErreurDonnees';
  erreur.code = code;
  if (cause !== undefined) {
    erreur.cause = cause;
  }
  return erreur;
}

/**
 * Message affichable à partir de n'importe quoi : une Error, une chaîne,
 * ou un objet inattendu tombé d'un rendu tiers. Ne renvoie jamais ''.
 *
 * @param {*} erreur
 * @returns {string}
 */
function messageLisible(erreur) {
  if (erreur instanceof Error && typeof erreur.message === 'string'
      && erreur.message.trim() !== '') {
    return erreur.message;
  }
  if (typeof erreur === 'string' && erreur.trim() !== '') {
    return erreur;
  }
  return 'Une erreur inattendue est survenue pendant le chargement des données.';
}

/* -------------------------------------------------------------------------
   2. Chargement
   ------------------------------------------------------------------------- */

/**
 * Charge assets/data/<nom>.json.
 *
 * Deux appels concurrents pour le même nom ne déclenchent qu'une seule
 * requête : c'est la promesse qui est mise en cache, pas son résultat.
 *
 * @param {string} nom            nom du fichier, sans extension ni chemin
 * @param {{delai?:number, rafraichir?:boolean}} [options]
 *        delai       — délai maximal en ms (0 ou négatif : aucun délai)
 *        rafraichir  — ignore le cache et relance une requête
 * @returns {Promise<object>} le contenu JSON analysé
 * @throws  rejette avec une Error au message français explicite, portant
 *          un code : 'nom', 'introuvable', 'http', 'illisible', 'delai',
 *          'bloque' ou 'reseau'.
 */
export function chargerDonnees(nom, options) {
  const reglages = options || {};

  /* La validation du nom est volontairement stricte : elle interdit toute
     traversée de dossier (« ../ ») et tout nom construit dynamiquement à
     partir d'une saisie utilisateur. */
  if (typeof nom !== 'string' || !NOM_VALIDE.test(nom)) {
    return Promise.reject(erreurDonnees(
      'nom',
      'Nom de jeu de données invalide : « ' + String(nom) + ' ». '
      + 'Attendu : un nom de fichier simple, sans chemin ni extension.'
    ));
  }

  if (!reglages.rafraichir && CACHE.has(nom)) {
    return CACHE.get(nom);
  }

  const delai = typeof reglages.delai === 'number' ? reglages.delai : DELAI_DEFAUT;
  const promesse = recuperer(nom, delai);

  CACHE.set(nom, promesse);

  /* Un échec ne se met pas en cache : sans cette purge, « Réessayer »
     renverrait éternellement la première erreur. Le .catch() ci-dessous ne
     consomme QUE la promesse dérivée — l'appelant reçoit bien le rejet. */
  promesse.catch(function () {
    if (CACHE.get(nom) === promesse) {
      CACHE.delete(nom);
    }
  });

  return promesse;
}

/**
 * Retire un jeu de données du cache (ou vide le cache entier).
 * Utile après une modification locale, ou dans un test.
 *
 * @param {string} [nom] si omis, le cache est entièrement vidé
 */
export function viderCache(nom) {
  if (typeof nom === 'string') {
    CACHE.delete(nom);
  } else {
    CACHE.clear();
  }
}

/**
 * Requête effective. Séparée de chargerDonnees() pour que la mémoïsation
 * reste lisible d'un seul coup d'œil.
 *
 * @param {string} nom
 * @param {number} delai
 * @returns {Promise<object>}
 */
async function recuperer(nom, delai) {
  const fichier = nom + '.json';
  const url = new URL(fichier, DOSSIER_DONNEES);
  const chemin = 'assets/data/' + fichier;

  /* AbortController est disponible partout depuis 2019 ; s'il manquait, on
     préfère charger sans délai maximal plutôt que de ne pas charger. */
  const controleur =
    typeof AbortController === 'function' ? new AbortController() : null;

  let expire = false;
  let minuteur = null;

  if (controleur && delai > 0) {
    minuteur = setTimeout(function () {
      expire = true;
      controleur.abort();
    }, delai);
  }

  let reponse;
  try {
    reponse = await fetch(url.href, {
      signal: controleur ? controleur.signal : undefined,
      headers: { Accept: 'application/json' }
    });
  } catch (cause) {
    throw traduireEchecReseau(cause, chemin, delai, expire);
  } finally {
    if (minuteur !== null) {
      clearTimeout(minuteur);
    }
  }

  /*
     Sous file://, certains navigateurs ne lèvent pas : ils renvoient une
     réponse opaque de statut 0. C'est le même problème, avec le même
     remède, donc le même message.
  */
  if (reponse.status === 0 && EST_FICHIER_LOCAL) {
    throw erreurDonnees('bloque', messageFichierLocal(chemin));
  }

  if (reponse.status === 404) {
    throw erreurDonnees(
      'introuvable',
      'Fichier de données introuvable : ' + chemin + '. '
      + 'Il a peut-être été renommé ou supprimé.'
    );
  }

  if (!reponse.ok) {
    throw erreurDonnees(
      'http',
      'Le serveur a refusé le fichier ' + chemin
      + ' (erreur HTTP ' + reponse.status + ').'
    );
  }

  /* On lit le texte brut avant d'analyser : cela permet de distinguer un
     fichier vide d'un fichier mal formé, et de citer la cause exacte. */
  let texte;
  try {
    texte = await reponse.text();
  } catch (cause) {
    throw traduireEchecReseau(cause, chemin, delai, expire);
  }

  if (texte.trim() === '') {
    throw erreurDonnees(
      'illisible',
      'Le fichier ' + chemin + ' est vide : il ne contient aucune donnée.'
    );
  }

  let donnees;
  try {
    donnees = JSON.parse(texte);
  } catch (cause) {
    throw erreurDonnees(
      'illisible',
      'Le fichier ' + chemin + ' est illisible : ce n’est pas du JSON '
      + 'valide (' + messageLisible(cause) + ').',
      cause
    );
  }

  if (donnees === null || typeof donnees !== 'object') {
    throw erreurDonnees(
      'illisible',
      'Le fichier ' + chemin + ' ne contient pas un objet JSON : '
      + 'la racine devrait être un objet ou un tableau.'
    );
  }

  return donnees;
}

/**
 * Traduit l'échec d'un fetch() en message français utile. C'est le point
 * délicat : le navigateur dit seulement « Failed to fetch », il faut
 * reconstituer la cause à partir du contexte.
 *
 * @param {*} cause
 * @param {string} chemin
 * @param {number} delai
 * @param {boolean} expire  vrai si notre propre minuteur a interrompu
 * @returns {Error}
 */
function traduireEchecReseau(cause, chemin, delai, expire) {
  const nomCause = cause && cause.name ? cause.name : '';

  if (expire) {
    return erreurDonnees(
      'delai',
      'Le chargement de ' + chemin + ' a dépassé le délai de '
      + formaterDelai(delai) + '. Le réseau est peut-être très lent.',
      cause
    );
  }

  if (nomCause === 'AbortError') {
    return erreurDonnees(
      'delai',
      'Le chargement de ' + chemin + ' a été interrompu avant la fin.',
      cause
    );
  }

  if (EST_FICHIER_LOCAL) {
    return erreurDonnees('bloque', messageFichierLocal(chemin), cause);
  }

  return erreurDonnees(
    'reseau',
    'Impossible de charger ' + chemin + ' : le fichier n’a pas pu être '
    + 'atteint. Vérifiez votre connexion, puis réessayez.',
    cause
  );
}

/**
 * Met un délai en forme pour un message destiné à un humain : en secondes
 * dès qu'elles sont lisibles, en millisecondes en dessous.
 *
 * @param {number} ms
 * @returns {string}
 */
function formaterDelai(ms) {
  if (ms >= 1000) {
    const secondes = Math.round(ms / 100) / 10;
    return String(secondes).replace('.', ',') + ' s';
  }
  return Math.round(ms) + ' ms';
}

/**
 * Message unique du cas file:// — la seule erreur dont la solution
 * n'est pas « réessayer », donc la seule qui mérite une consigne.
 *
 * @param {string} chemin
 * @returns {string}
 */
function messageFichierLocal(chemin) {
  return 'Le navigateur bloque la lecture de ' + chemin
    + ' parce que la page est ouverte directement depuis le disque '
    + '(file://). Servez le dossier localement — par exemple avec '
    + '« python3 -m http.server » — puis rouvrez la page via http://.';
}

/* -------------------------------------------------------------------------
   3. Validation de forme
   ------------------------------------------------------------------------- */

/** Vocabulaire de types, et sa traduction pour les messages d'erreur. */
const LIBELLES_TYPE = {
  chaine: 'une chaîne de caractères',
  nombre: 'un nombre',
  booleen: 'un booléen',
  tableau: 'un tableau',
  objet: 'un objet',
  fonction: 'une fonction',
  nul: 'la valeur null',
  indefini: 'absente',
  tout: 'une valeur quelconque'
};

/**
 * Type d'une valeur, exprimé dans le vocabulaire ci-dessus.
 *
 * @param {*} valeur
 * @returns {string}
 */
function typeDe(valeur) {
  if (valeur === null) return 'nul';
  if (Array.isArray(valeur)) return 'tableau';
  switch (typeof valeur) {
    case 'undefined': return 'indefini';
    case 'string':    return 'chaine';
    case 'number':    return 'nombre';
    case 'boolean':   return 'booleen';
    case 'function':  return 'fonction';
    default:          return 'objet';
  }
}

/**
 * Décompose un descripteur de forme en sa version canonique.
 * Formes acceptées :
 *   'chaine'                       type obligatoire
 *   'chaine?'                      type facultatif
 *   { type, optionnel, elements }  'elements' = forme des éléments d'un
 *                                  tableau, vérifiée un par un
 *
 * @param {*} descripteur
 * @param {string} cle
 * @returns {{type:string, optionnel:boolean, elements:object|null}}
 */
function normaliserDescripteur(descripteur, cle) {
  if (typeof descripteur === 'string') {
    const optionnel = descripteur.endsWith('?');
    return {
      type: optionnel ? descripteur.slice(0, -1) : descripteur,
      optionnel: optionnel,
      elements: null
    };
  }

  if (descripteur && typeof descripteur === 'object'
      && typeof descripteur.type === 'string') {
    return {
      type: descripteur.type,
      optionnel: descripteur.optionnel === true,
      elements: descripteur.elements || null
    };
  }

  /* Erreur de programmation, pas de donnée : le message vise le
     développeur, mais reste en français comme le reste du projet. */
  throw erreurDonnees(
    'forme',
    'Descripteur de forme invalide pour la clé « ' + cle + ' ».'
  );
}

/** Préfixe de message : « faq.json » : … , ou rien si aucun contexte. */
function prefixe(contexte) {
  return contexte ? '« ' + contexte + ' » : ' : '';
}

/**
 * Contrôle la présence et le type des clés attendues.
 * Lève une Error au message français nommant la clé fautive ; les pages
 * s'en servent pour échouer proprement sur un JSON malformé plutôt que de
 * planter plus tard, à l'affichage.
 *
 * Exemple :
 *   verifierForme(donnees, {
 *     titre: 'chaine',
 *     maj: 'chaine?',
 *     documents: { type: 'tableau', elements: { id: 'chaine', titre: 'chaine' } }
 *   }, 'documents.json');
 *
 * @param {*} objet          valeur à contrôler (doit être un objet)
 * @param {object} forme     { cle: descripteur, … }
 * @param {string} [contexte] nom affiché dans les messages, ex. 'faq.json'
 * @returns {object} l'objet lui-même, pour permettre l'enchaînement
 */
export function verifierForme(objet, forme, contexte) {
  const ou = prefixe(contexte);

  if (typeDe(objet) !== 'objet') {
    throw erreurDonnees(
      'forme',
      ou + 'les données sont mal formées : la racine devrait être un objet, '
      + 'or elle est ' + LIBELLES_TYPE[typeDe(objet)] + '.'
    );
  }

  if (!forme || typeof forme !== 'object') {
    return objet;
  }

  for (const cle of Object.keys(forme)) {
    const attendu = normaliserDescripteur(forme[cle], cle);
    const valeur = objet[cle];
    const reel = typeDe(valeur);

    /* Clé absente : tolérée si le descripteur est facultatif. */
    if (reel === 'indefini' || reel === 'nul') {
      if (attendu.optionnel) continue;
      throw erreurDonnees(
        'forme',
        ou + 'la clé « ' + cle + ' » est absente alors qu’elle est '
        + 'obligatoire (attendu : ' + libelleAttendu(attendu.type) + ').'
      );
    }

    if (attendu.type === 'tout') continue;

    if (reel !== attendu.type) {
      throw erreurDonnees(
        'forme',
        ou + 'la clé « ' + cle + ' » devrait être '
        + libelleAttendu(attendu.type) + ', or c’est '
        + LIBELLES_TYPE[reel] + '.'
      );
    }

    /* Un NaN passe le typeof « number » sans être un nombre exploitable :
       mieux vaut le signaler ici que de l'afficher tel quel. */
    if (attendu.type === 'nombre' && Number.isNaN(valeur)) {
      throw erreurDonnees(
        'forme',
        ou + 'la clé « ' + cle + ' » devrait être un nombre, '
        + 'or ce n’est pas une valeur numérique valide.'
      );
    }

    /* Contrôle élément par élément d'un tableau d'objets. */
    if (attendu.elements && reel === 'tableau') {
      for (let i = 0; i < valeur.length; i += 1) {
        const sousContexte = (contexte ? contexte + ' → ' : '')
          + cle + '[' + i + ']';
        verifierForme(valeur[i], attendu.elements, sousContexte);
      }
    }
  }

  return objet;
}

/** Libellé d'un type attendu, même si le descripteur est inconnu. */
function libelleAttendu(type) {
  return LIBELLES_TYPE[type] || 'de type « ' + type + ' »';
}

/* -------------------------------------------------------------------------
   4. Cycle d'affichage : chargement -> succès | vide | erreur
   ------------------------------------------------------------------------- */

/**
 * Orchestre le cycle de vie d'un conteneur alimenté par des données
 * asynchrones. Ne rejette jamais : quel que soit l'échec, le conteneur
 * finit par afficher quelque chose de lisible et d'actionnable.
 *
 * @param {Element|string} conteneur élément ou sélecteur CSS
 * @param {Promise<*>|function(): Promise<*>} source
 *        Une promesse, ou — de préférence — une fabrique de promesse. Une
 *        fabrique permet au bouton « Réessayer » de relancer réellement le
 *        chargement ; une simple promesse ne pouvant être rejouée, le
 *        bouton proposera alors de recharger la page.
 * @param {function(*, Element): void} rendu
 *        Appelé avec (donnees, conteneur) une fois le conteneur vidé.
 * @param {object} [options]
 *        squelette      nombre de gabarits, ou fonction (conteneur) => void
 *        texteChargement texte annoncé aux lecteurs d'écran
 *        titreErreur    titre du bloc d'erreur
 *        titreVide      titre du bloc « aucune donnée »
 *        texteVide      explication du bloc « aucune donnée »
 *        estVide        (donnees) => boolean, prédicat de vacuité
 *        compact        true : variante resserrée des états
 *        surEtat        (resultat) => void, appelé à chaque cycle, y
 *                       compris après un « Réessayer »
 * @returns {Promise<{etat:string, donnees?:*, erreur?:Error}>}
 *          etat vaut 'succes', 'vide' ou 'erreur'.
 */
export function avecEtat(conteneur, source, rendu, options) {
  const cible = resoudreConteneur(conteneur);
  const reglages = options || {};

  /* Un conteneur absent est une erreur de page, pas de donnée : on le dit
     en console sans interrompre le reste du script — la navigation doit
     survivre à une section manquante. */
  if (!cible) {
    const erreur = erreurDonnees(
      'forme',
      'Conteneur d’affichage introuvable : la section ne peut pas être rendue.'
    );
    console.error('[data] ' + erreur.message, conteneur);
    return Promise.resolve({ etat: 'erreur', erreur: erreur });
  }

  const relancer = typeof source === 'function' ? source : null;

  /**
   * Un tour complet du cycle. Le paramètre indique si l'on vient d'un clic
   * sur « Réessayer » : dans ce cas le focus était sur un bouton que l'on
   * s'apprête à détruire, il faut donc le replacer après le rendu.
   *
   * @param {boolean} depuisReessai
   */
  async function executer(depuisReessai) {
    afficherSquelette(cible, reglages);

    let resultat;

    try {
      const promesse = relancer ? relancer() : source;
      const donnees = await promesse;

      if (estVide(donnees, reglages)) {
        resultat = { etat: 'vide', donnees: donnees };
        vider(cible);
        cible.append(construireEtatVide(reglages));
      } else {
        /* Le rendu est exécuté sous surveillance : une donnée malformée
           détectée par verifierForme() à l'intérieur du rendu bascule
           proprement en état d'erreur au lieu de laisser un conteneur à
           moitié rempli. */
        vider(cible);
        rendu(donnees, cible);
        resultat = { etat: 'succes', donnees: donnees };
      }
    } catch (cause) {
      const erreur = cause instanceof Error
        ? cause
        : erreurDonnees('reseau', messageLisible(cause), cause);

      console.error('[data] ' + erreur.message, erreur);

      resultat = { etat: 'erreur', erreur: erreur };
      vider(cible);
      cible.append(construireEtatErreur(erreur, reglages, relancer, executer,
        depuisReessai));
    }

    cible.setAttribute('aria-busy', 'false');

    if (typeof reglages.surEtat === 'function') {
      try {
        reglages.surEtat(resultat);
      } catch (cause) {
        console.error('[data] Rappel surEtat en échec.', cause);
      }
    }

    return resultat;
  }

  return executer(false);
}

/**
 * Résout un conteneur donné par élément ou par sélecteur.
 *
 * @param {Element|string} conteneur
 * @returns {Element|null}
 */
function resoudreConteneur(conteneur) {
  if (typeof conteneur === 'string') {
    return typeof document !== 'undefined'
      ? document.querySelector(conteneur)
      : null;
  }
  return conteneur && conteneur.nodeType === 1 ? conteneur : null;
}

/**
 * Vacuité par défaut : rien, ou un tableau sans élément. Volontairement
 * prudent — un objet vide peut être une donnée légitime, donc une page qui
 * veut un autre critère fournit son propre prédicat.
 *
 * @param {*} donnees
 * @param {object} reglages
 * @returns {boolean}
 */
function estVide(donnees, reglages) {
  if (typeof reglages.estVide === 'function') {
    return reglages.estVide(donnees) === true;
  }
  if (donnees === null || donnees === undefined) return true;
  return Array.isArray(donnees) && donnees.length === 0;
}

/* -------------------------------------------------------------------------
   5. Fabriques d'états (aucun innerHTML, tout en textContent)
   ------------------------------------------------------------------------- */

/**
 * Remplit le conteneur de gabarits gris pendant l'attente.
 * Le squelette est purement décoratif (aria-hidden) : l'information
 * « ça charge » est portée par aria-busy et par un texte de statut, donc
 * elle reste disponible sans animation et sans vision (SPEC §7).
 *
 * @param {Element} cible
 * @param {object} reglages
 */
function afficherSquelette(cible, reglages) {
  vider(cible);
  cible.setAttribute('aria-busy', 'true');

  if (typeof reglages.squelette === 'function') {
    reglages.squelette(cible);
  } else {
    const nombre = typeof reglages.squelette === 'number'
      ? Math.max(1, reglages.squelette)
      : SQUELETTES_DEFAUT;

    const enveloppe = creerElement('div', { classe: 'pile' });
    enveloppe.setAttribute('aria-hidden', 'true');

    for (let i = 0; i < nombre; i += 1) {
      const groupe = creerElement('div', { classe: 'squelette-groupe' });
      groupe.append(
        creerElement('span', { classe: 'squelette squelette--ligne squelette--titre' }),
        creerElement('span', { classe: 'squelette squelette--ligne squelette--moyen' }),
        creerElement('span', { classe: 'squelette squelette--ligne squelette--court' })
      );
      enveloppe.append(groupe);
    }

    cible.append(enveloppe);
  }

  const statut = creerElement('p', {
    classe: 'visuellement-cache',
    texte: reglages.texteChargement || 'Chargement des données en cours…'
  });
  statut.setAttribute('role', 'status');
  cible.append(statut);
}

/**
 * Bloc commun aux états vide et erreur : glyphe, titre, texte, actions.
 *
 * @param {{glyphe:string, titre:string, texte:string, variante:string,
 *          compact:boolean}} contenu
 * @returns {{bloc:Element, actions:Element}}
 */
function construireBlocEtat(contenu) {
  let classe = 'etat-vide etat-vide--encadre';
  if (contenu.variante) classe += ' ' + contenu.variante;
  if (contenu.compact) classe += ' etat-vide--compact';

  const bloc = creerElement('div', { classe: classe });

  const illustration = creerElement('span', {
    classe: 'etat-vide__illustration',
    texte: contenu.glyphe
  });
  illustration.setAttribute('aria-hidden', 'true');

  const titre = creerElement('p', {
    classe: 'etat-vide__titre',
    texte: contenu.titre
  });

  const texte = creerElement('p', {
    classe: 'etat-vide__texte',
    texte: contenu.texte
  });

  const actions = creerElement('div', { classe: 'etat-vide__actions' });

  bloc.append(illustration, titre, texte, actions);
  return { bloc: bloc, actions: actions };
}

/**
 * État « aucune donnée » : la requête a réussi, il n'y a simplement rien.
 *
 * @param {object} reglages
 * @returns {Element}
 */
function construireEtatVide(reglages) {
  const { bloc } = construireBlocEtat({
    glyphe: '∅',
    titre: reglages.titreVide || 'Aucune donnée à afficher',
    texte: reglages.texteVide
      || 'Cette section ne contient encore rien. Elle se remplira dès que '
       + 'des éléments y seront publiés.',
    variante: '',
    compact: reglages.compact === true
  });
  return bloc;
}

/**
 * État d'erreur : message explicite + bouton d'action. Jamais de page
 * vide, jamais de page figée.
 *
 * @param {Error} erreur
 * @param {object} reglages
 * @param {function|null} relancer   fabrique de promesse, si disponible
 * @param {function} executer        relance un cycle complet
 * @param {boolean} depuisReessai    le focus doit-il être replacé
 * @returns {Element}
 */
function construireEtatErreur(erreur, reglages, relancer, executer,
    depuisReessai) {
  const { bloc, actions } = construireBlocEtat({
    glyphe: '!',
    titre: reglages.titreErreur || 'Données indisponibles',
    texte: messageLisible(erreur),
    variante: 'etat-vide--erreur',
    compact: reglages.compact === true
  });

  /* role="alert" : le bloc apparaît après le chargement, il doit donc être
     annoncé sans que la personne ait à partir à sa recherche. */
  bloc.setAttribute('role', 'alert');

  const bouton = creerElement('button', {
    classe: 'bouton bouton--secondaire',
    texte: relancer ? 'Réessayer' : 'Recharger la page'
  });
  bouton.type = 'button';

  /* Gestionnaire posé en JavaScript, jamais en attribut HTML : c'est
     exactement ce qui cassait l'ancienne version (SPEC §6.6). */
  bouton.addEventListener('click', function () {
    if (relancer) {
      bouton.disabled = true;
      executer(true);
    } else {
      location.reload();
    }
  });

  actions.append(bouton);

  /* Le focus était sur le bouton que l'on vient de détruire : sans ce
     replacement, un second échec renverrait la personne au début du
     document. On attend la fin de l'insertion pour pouvoir focaliser. */
  if (depuisReessai) {
    queueMicrotask(function () {
      if (bouton.isConnected) bouton.focus();
    });
  }

  return bloc;
}
