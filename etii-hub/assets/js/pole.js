/* =========================================================================
   ETII Hub — Gabarit unique des trois espaces de pôle
   (etiia.html, etiie.html, etiii.html)

   Dans l'ancien site, les trois pages de pôle étaient trois copies : une
   correction devait être faite trois fois, et ne l'était jamais qu'une ou
   deux. Ici, un seul module, paramétré par un seul attribut :

       <body data-pole="ETIIA">

   Ce module lit `document.body.dataset.pole`, refuse proprement toute
   valeur qui n'est pas l'un des trois pôles, puis construit l'espace
   correspondant. ETII n'est pas accepté : c'est le niveau service, il a
   son propre tableau de bord (index.html).

   Six zones asynchrones, six cycles d'état indépendants (data.js) :

     #zone-indicateurs    indicateurs.json
     #zone-organigramme   organigramme.json
     #zone-communication  communications.json
     #zone-reunions       reunions.json
     #zone-faq            faq.json

   L'indépendance est délibérée : si reunions.json manque, seule la section
   « Réunions » porte le message d'erreur, et les indicateurs, la
   communication et la FAQ continuent de s'afficher.

   Le pôle actif voyage ensuite dans le hash des pages transverses
   (`communication.html#pole=ETIIA`), conformément au contrat d'URL.

   Tout le DOM est construit avec el(), frag() et monter() : aucun
   innerHTML, aucun gestionnaire en attribut HTML.
   ========================================================================= */

import { el, frag, monter, etatUrl, initTheme, initNav, annoncer } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { tuileIndicateur, graphiqueLignes } from './indicateurs.js';

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/*
   Les trois pôles de l'accord d'équipe. Le libellé, la métaphore et la
   description sont de la matière éditoriale, pas de la donnée : ils vivent
   ici, pas dans un JSON. La couleur est un jeton de tokens.css — jamais
   une valeur brute, et jamais le seul signal du pôle : le code « ETIIA »
   accompagne systématiquement la pastille.
*/
const POLES = {
  ETIIA: {
    cle: 'ETIIA',
    metaphore: 'Squelette & ADN',
    couleur: 'var(--pole-etiia)',
    description: 'Logique et règles d’architecture : découpage '
      + 'fonctionnel, conventions de nommage et principes que tous les '
      + 'autres travaux appliquent ensuite.'
  },
  ETIIE: {
    cle: 'ETIIE',
    metaphore: 'Système nerveux',
    couleur: 'var(--pole-etiie)',
    description: 'Schémas électriques et communication entre systèmes : '
      + 'signaux, interfaces et cohérence des échanges d’un bout à l’autre '
      + 'de la définition.'
  },
  ETIII: {
    cle: 'ETIII',
    metaphore: 'Structure & harnais',
    couleur: 'var(--pole-etiii)',
    description: 'Intégration physique et routage dans la maquette '
      + 'numérique : cheminements, fixations et vérification des '
      + 'interférences avant fabrication.'
  }
};

/* Couleur de série du NIVEAU SERVICE, tous pôles confondus. La moyenne des
   pôles n'emprunte la couleur d'aucun d'entre eux. */
const COULEUR_SERVICE = 'var(--pole-etii)';

/* Ordre d'affichage des indicateurs, identique à celui du tableau de bord :
   l'OTQ en tête, c'est l'indicateur que le service regarde. */
const ORDRE_INDICATEURS = ['otq', 'otd', 'ecarts', 'charge'];

/* Les quatre pages transverses, partagées et filtrées par le pôle actif. */
const PAGES_TRANSVERSES = [
  { page: 'communication.html', libelle: 'Communication' },
  { page: 'reunions.html', libelle: 'Réunions' },
  { page: 'organigramme.html', libelle: 'Organigramme' },
  { page: 'faq.html', libelle: 'FAQ' }
];

/** Nombre d'annonces reprises dans l'aperçu de communication. */
const MAX_ANNONCES = 3;

/** Nombre de questions reprises dans l'aperçu de la FAQ. */
const MAX_QUESTIONS = 3;

/** Statuts d'annonce : libellé lisible et variante de composant. */
const STATUTS = {
  info:   { variante: 'info',   libelle: 'Information' },
  urgent: { variante: 'alerte', libelle: 'Urgent' },
  succes: { variante: 'succes', libelle: 'Succès' }
};

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                     'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

/* -------------------------------------------------------------------------
   2. Formatage
   ------------------------------------------------------------------------- */

/**
 * Libellé d'un mois au format « 2026-09 ».
 *
 * @param {string} code
 * @param {string} [forme] 'long' → « septembre 2026 », sinon « sept. 2026 »
 * @returns {string} le code tel quel s'il est illisible
 */
function libelleMois(code, forme) {
  const brut = String(code === null || code === undefined ? '' : code);
  const parts = /^(\d{4})-(\d{2})$/.exec(brut);
  if (!parts) return brut;

  const index = Number(parts[2]) - 1;
  if (index < 0 || index > 11) return brut;

  if (forme === 'long') return MOIS_LONGS[index] + ' ' + parts[1];
  return MOIS_COURTS[index] + ' ' + parts[1];
}

/**
 * Date longue à partir d'un « 2026-09-12 » → « 12 septembre 2026 ».
 * @param {string} code
 * @returns {string}
 */
function dateLongue(code) {
  const brut = String(code === null || code === undefined ? '' : code);
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(brut);
  if (!parts) return brut;

  const index = Number(parts[2]) - 1;
  if (index < 0 || index > 11) return brut;

  const jour = Number(parts[3]);
  return (jour === 1 ? '1er' : String(jour))
    + ' ' + MOIS_LONGS[index] + ' ' + parts[1];
}

/**
 * Accord du mot « personne ».
 * @param {number} nombre
 * @returns {string}
 */
function effectifLisible(nombre) {
  return nombre + (nombre > 1 ? ' personnes' : ' personne');
}

/**
 * Garde-fou de composant : les fabriques d'indicateurs doivent rendre un
 * nœud. Une signature qui aurait changé casserait la page entière ; ici
 * elle bascule proprement la seule zone concernée en état d'erreur.
 *
 * @param {*} valeur
 * @param {string} origine nom de la fabrique, cité dans le message
 * @returns {Node}
 */
function exigerNoeud(valeur, origine) {
  if (valeur && typeof valeur === 'object' && typeof valeur.nodeType === 'number') {
    return valeur;
  }
  throw new Error(
    'Le composant ' + origine + '() n’a rien renvoyé d’affichable : '
    + 'la section ne peut pas être construite.'
  );
}

/* -------------------------------------------------------------------------
   3. Contrat d'URL — le pôle actif voyage dans le hash
   ------------------------------------------------------------------------- */

/**
 * Lien vers une page transverse, pôle actif porté par le hash.
 * Forme : `communication.html#pole=ETIIA`.
 *
 * @param {string} page   'communication.html', 'faq.html'…
 * @param {string} code   code du pôle
 * @param {object} [extra] paramètre supplémentaire, ex. { annonce: 'c02' }
 * @returns {string}
 */
function lienPole(page, code, extra) {
  let hash = 'pole=' + encodeURIComponent(code);
  if (extra && typeof extra === 'object') {
    for (const cle of Object.keys(extra)) {
      const valeur = extra[cle];
      if (valeur === null || valeur === undefined || valeur === '') continue;
      hash += '&' + encodeURIComponent(cle) + '=' + encodeURIComponent(String(valeur));
    }
  }
  return page + '#' + hash;
}

/**
 * Bouton-lien « voir tout », commun aux quatre aperçus.
 * @param {string} page
 * @param {string} code
 * @param {string} libelle
 * @returns {Element}
 */
function lienSuite(page, code, libelle) {
  return el('p', { class: 'rangee sans-marge' },
    el('a', { class: 'bouton bouton--secondaire', href: lienPole(page, code) },
      libelle));
}

/* -------------------------------------------------------------------------
   4. Lecture des séries d'indicateurs
   ------------------------------------------------------------------------- */

/**
 * Série d'un indicateur pour une source (un pôle, ou le service).
 * Une série de longueur différente de la période est refusée : mieux vaut
 * masquer une courbe que de la décaler d'un mois.
 *
 * @param {*} source
 * @param {string} cle
 * @param {number} longueur nombre de mois attendu
 * @returns {Array<number|null>|null}
 */
function serieDe(source, cle, longueur) {
  if (!source || typeof source !== 'object') return null;
  const serie = source[cle];
  if (!Array.isArray(serie) || serie.length !== longueur) return null;
  return serie;
}

/**
 * Moyenne mensuelle des pôles pour un indicateur.
 *
 * C'est la référence à laquelle un pôle se compare : une MOYENNE, pas le
 * total du service. Sur un indicateur cumulatif comme les écarts ouverts,
 * comparer un pôle à la somme des trois n'aurait aucun sens, et forcerait
 * deux échelles verticales — ce que la SPEC interdit. Une moyenne partage
 * l'échelle et la cible du pôle : une seule graduation suffit.
 *
 * @param {object} poles  bloc « poles » de indicateurs.json
 * @param {string} cle
 * @param {number} longueur
 * @returns {{valeurs: Array<number|null>, nombre: number}|null}
 *          null si moins de deux pôles sont mesurés (une « moyenne » d'un
 *          seul pôle serait ce pôle lui-même).
 */
function moyenneDesPoles(poles, cle, longueur) {
  if (!poles || typeof poles !== 'object') return null;

  const series = Object.keys(poles)
    .map((code) => serieDe(poles[code], cle, longueur))
    .filter((serie) => serie !== null);

  if (series.length < 2) return null;

  const valeurs = [];
  for (let i = 0; i < longueur; i += 1) {
    let somme = 0;
    let compte = 0;
    for (const serie of series) {
      const valeur = serie[i];
      if (typeof valeur === 'number' && Number.isFinite(valeur)) {
        somme += valeur;
        compte += 1;
      }
    }
    /* Un mois sans aucune valeur reste un trou : il ne devient pas zéro. */
    valeurs.push(compte ? Math.round((somme / compte) * 100) / 100 : null);
  }

  return { valeurs: valeurs, nombre: series.length };
}

/* -------------------------------------------------------------------------
   5. Section « Indicateurs »
   ------------------------------------------------------------------------- */

/*
   Le sélecteur d'indicateur pilote le graphique. Son état voyage dans le
   hash (#indicateur=otd) pour que la vue soit partageable. La valeur par
   défaut — l'OTQ — n'est pas écrite : l'URL reste nue.
*/
let appliquerIndicateur = null;

/** Lit l'indicateur demandé par l'URL ('' si rien ou illisible). */
function indicateurDemande() {
  const etat = etatUrl.lire();
  return typeof etat.indicateur === 'string' ? etat.indicateur.toLowerCase() : '';
}

/**
 * Construit la section des indicateurs du pôle.
 *
 * @param {object} pole      entrée de POLES
 * @param {object} donnees   contenu de indicateurs.json
 * @param {Element} conteneur
 */
function rendreIndicateurs(pole, donnees, conteneur) {
  verifierForme(donnees, {
    periode: 'objet',
    definitions: 'objet',
    poles: 'objet'
  }, 'indicateurs.json');

  const mois = Array.isArray(donnees.periode.mois) ? donnees.periode.mois : [];
  if (mois.length === 0) {
    throw new Error('« indicateurs.json » : la période ne contient aucun mois.');
  }

  const source = donnees.poles[pole.cle];
  if (!source || typeof source !== 'object') {
    throw new Error('« indicateurs.json » : le pôle ' + pole.cle
      + ' n’est pas suivi dans le fichier des indicateurs.');
  }

  /* Indicateurs exploitables : définis ET mesurés pour CE pôle. */
  const cles = ORDRE_INDICATEURS.filter((cle) =>
    donnees.definitions[cle] && serieDe(source, cle, mois.length));

  if (cles.length === 0) {
    throw new Error(
      '« indicateurs.json » : aucune série du pôle ' + pole.cle
      + ' ne couvre la période annoncée — les valeurs et la liste des mois '
      + 'ne concordent pas.'
    );
  }

  /* --- 5.1 Les quatre tuiles -------------------------------------------
     Elles mesurent CE pôle : leur couleur de série est celle du pôle, et
     la cible du fichier s'applique telle quelle, puisqu'elle est établie
     par pôle. */

  const tuiles = el('div', { class: 'grille grille--compacte' });

  for (const cle of cles) {
    tuiles.append(exigerNoeud(tuileIndicateur({
      cle: cle,
      definition: donnees.definitions[cle],
      serie: source[cle],
      mois: mois,
      couleur: pole.couleur
    }), 'tuileIndicateur'));
  }

  /* --- 5.2 Le sélecteur d'indicateur ---------------------------------- */

  const select = el('select', {
    class: 'champ__controle choix-indicateur',
    id: 'choix-indicateur',
    onChange: (evt) => changer(evt.target.value, true)
  }, cles.map((cle) => el('option', { value: cle },
    donnees.definitions[cle].libelle + ' — ' + donnees.definitions[cle].nom)));

  /* --- 5.3 Le graphique de comparaison -------------------------------- */

  const zoneGraphique = el('div');

  /**
   * Rejoue le graphique pour l'indicateur demandé.
   *
   * Deux séries — le pôle et la moyenne des pôles — donc légende
   * obligatoire : graphiqueLignes() l'ajoute d'elle-même dès deux séries,
   * et chaque courbe porte en outre son étiquette en bout de tracé.
   * Le tableau de valeurs est lui aussi intégré à la figure.
   *
   * @param {string} demande
   * @param {boolean} avecAnnonce annoncer le changement aux lecteurs d'écran
   */
  function appliquer(demande, avecAnnonce) {
    const cle = cles.includes(demande) ? demande : cles[0];
    const definition = donnees.definitions[cle];

    if (select.value !== cle) select.value = cle;

    const series = [{
      cle: pole.cle,
      libelle: pole.cle,
      couleur: pole.couleur,
      valeurs: serieDe(source, cle, mois.length)
    }];

    const moyenne = moyenneDesPoles(donnees.poles, cle, mois.length);
    if (moyenne) {
      series.push({
        cle: 'moyenne',
        libelle: 'Moyenne des ' + moyenne.nombre + ' pôles',
        couleur: COULEUR_SERVICE,
        valeurs: moyenne.valeurs
      });
    }

    monter(zoneGraphique, exigerNoeud(graphiqueLignes({
      mois: mois,
      series: series,
      definition: definition,
      titre: definition.libelle + ' — ' + pole.cle
        + (moyenne ? ' et moyenne des pôles' : '')
    }), 'graphiqueLignes'));

    if (avecAnnonce) annoncer('Indicateur affiché : ' + definition.nom + '.');
  }

  /**
   * Point d'entrée unique des changements : met l'URL à jour, puis
   * reconstruit. Un échec tardif d'une fabrique est journalisé et annoncé
   * plutôt que laissé remonter — la page reste navigable.
   *
   * @param {string} demande
   * @param {boolean} depuisInteraction
   */
  function changer(demande, depuisInteraction) {
    const cle = cles.includes(demande) ? demande : cles[0];
    if (depuisInteraction) {
      // La valeur par défaut ne s'écrit pas : l'URL reste courte.
      etatUrl.ecrire({ indicateur: cle === cles[0] ? null : cle });
    }
    try {
      appliquer(cle, depuisInteraction);
    } catch (erreur) {
      console.error('[pole] ' + erreur.message, erreur);
      annoncer('L’indicateur demandé n’a pas pu être affiché.');
    }
  }

  /* --- 5.4 Assemblage --------------------------------------------------- */

  monter(conteneur,
    tuiles,
    el('div', { class: 'pile' },
      el('div', { class: 'rangee rangee--entre' },
        el('h3', { class: 'sans-marge', id: 'titre-suivi' },
          'Suivi mensuel comparé'),
        el('div', { class: 'rangee rangee--serree pole-choix' },
          el('label', { class: 'champ__etiquette', for: 'choix-indicateur' },
            'Indicateur affiché'),
          select)),
      zoneGraphique));

  /* Le hash fait foi au premier rendu comme après un « Précédent ». */
  appliquerIndicateur = changer;
  changer(indicateurDemande(), false);
}

/* -------------------------------------------------------------------------
   6. Section « Organigramme en résumé »
   ------------------------------------------------------------------------- */

/**
 * Extrait le bloc d'un pôle dans organigramme.json.
 * @param {object} donnees
 * @param {string} code
 * @returns {object|null} null si le pôle est absent du fichier
 */
function blocOrganigramme(donnees, code) {
  verifierForme(donnees, { poles: 'tableau' }, 'organigramme.json');
  const trouve = donnees.poles.find(
    (entree) => entree && typeof entree === 'object' && entree.pole === code);
  return trouve || null;
}

/**
 * Effectif d'une squad, tolérant à une squad malformée.
 * @param {*} squad
 * @returns {number}
 */
function effectifSquad(squad) {
  return squad && Array.isArray(squad.membres) ? squad.membres.length : 0;
}

/**
 * Rend le responsable de pôle, ses squads et leur effectif.
 *
 * @param {object} pole  entrée de POLES
 * @param {object} bloc  entrée de organigramme.json pour ce pôle
 * @param {Element} conteneur
 */
function rendreOrganigramme(pole, bloc, conteneur) {
  const responsable = (bloc.responsable && typeof bloc.responsable === 'object')
    ? bloc.responsable
    : null;
  const squads = Array.isArray(bloc.squads) ? bloc.squads : [];

  const effectif = (responsable ? 1 : 0)
    + squads.reduce((total, squad) => total + effectifSquad(squad), 0);

  /* Le responsable : une carte à part, c'est la tête du pôle. */
  const carteResponsable = responsable
    ? el('article', { class: 'carte carte--compacte' },
        el('div', { class: 'carte__entete' },
          el('h3', { class: 'carte__titre' }, String(responsable.nom || 'Responsable')),
          el('span', { class: 'badge badge--accent' },
            String(responsable.poste || 'Responsable de pôle'))),
        responsable.perimetre
          ? el('p', { class: 'carte__meta sans-marge' },
              el('span', { class: 'badge badge--neutre badge--contour' },
                'Périmètre ' + String(responsable.perimetre)))
          : null)
    : el('p', { class: 'texte-doux sans-marge' },
        'Aucun responsable n’est déclaré pour ce pôle.');

  /* Les squads : nom et effectif, rien de plus — la vue complète est à un
     clic, sur la page dédiée. */
  const listeSquads = squads.length
    ? el('ul', { class: 'grille grille--compacte' },
        squads.map((squad, rang) => el('li', { class: 'carte carte--plate carte--compacte' },
          el('p', { class: 'gras sans-marge' },
            String((squad && squad.nom) || 'Squad ' + (rang + 1))),
          el('p', { class: 'texte-sm texte-doux sans-marge' },
            effectifLisible(effectifSquad(squad))))))
    : el('p', { class: 'texte-doux sans-marge' },
        'Aucune squad n’est encore rattachée à ce pôle.');

  monter(conteneur,
    el('p', { class: 'rangee rangee--serree sans-marge' },
      el('span', { class: 'badge badge--neutre' }, effectifLisible(effectif)),
      el('span', { class: 'badge badge--neutre badge--contour' },
        squads.length + (squads.length > 1 ? ' squads' : ' squad'))),
    carteResponsable,
    listeSquads,
    lienSuite('organigramme.html', pole.cle,
      'Voir l’organigramme complet du pôle'));
}

/* -------------------------------------------------------------------------
   7. Section « Communication »
   ------------------------------------------------------------------------- */

/**
 * Annonces de CE pôle, les plus récentes d'abord.
 * Les annonces de niveau service restent sur le tableau de bord ETII :
 * un espace de pôle ne montre que ce qui lui appartient.
 *
 * @param {object} donnees contenu de communications.json
 * @param {string} code
 * @returns {object[]}
 */
function annoncesDuPole(donnees, code) {
  verifierForme(donnees, { annonces: 'tableau' }, 'communications.json');

  return donnees.annonces
    .filter((annonce) => annonce && typeof annonce === 'object'
      && annonce.pole === code)
    .slice()
    /* Tri stable et explicite : date décroissante, puis titre — jamais
       l'ordre d'insertion du fichier. */
    .sort((a, b) => {
      const parDate = String(b.date || '').localeCompare(String(a.date || ''));
      if (parDate !== 0) return parDate;
      return String(a.titre || '').localeCompare(String(b.titre || ''), 'fr');
    })
    .slice(0, MAX_ANNONCES);
}

/**
 * Carte d'aperçu d'une annonce.
 * @param {object} annonce
 * @param {string} code
 * @returns {Element}
 */
function carteAnnonce(annonce, code) {
  const statut = STATUTS[annonce.statut] || { variante: 'neutre', libelle: 'Annonce' };
  const classeStatut = statut.variante === 'neutre'
    ? ''
    : ' carte--statut-' + statut.variante;

  return el('article', { class: 'carte carte--compacte carte--cliquable' + classeStatut },
    el('p', { class: 'carte__meta sans-marge' },
      annonce.date
        ? el('time', { datetime: String(annonce.date) }, dateLongue(annonce.date))
        : null,
      /* La variante colore le badge, mais son texte dit déjà le statut :
         rien ne repose sur la seule couleur. */
      el('span', { class: 'badge badge--' + statut.variante }, statut.libelle),
      annonce.categorie
        ? el('span', { class: 'badge badge--neutre badge--contour' },
            String(annonce.categorie))
        : null),

    el('h3', { class: 'carte__titre' },
      el('a', {
        class: 'carte__lien',
        href: lienPole('communication.html', code, { annonce: annonce.id })
      }, String(annonce.titre || 'Annonce'))),

    annonce.resume
      ? el('p', { class: 'sans-marge texte-doux' }, String(annonce.resume))
      : null);
}

/**
 * Rend l'aperçu de communication du pôle.
 * @param {object} pole
 * @param {object[]} annonces
 * @param {Element} conteneur
 */
function rendreCommunication(pole, annonces, conteneur) {
  monter(conteneur,
    el('div', { class: 'pile' },
      annonces.map((annonce) => carteAnnonce(annonce, pole.cle))),
    lienSuite('communication.html', pole.cle,
      'Toute la communication du pôle'));
}

/* -------------------------------------------------------------------------
   8. Section « Réunions »
   ------------------------------------------------------------------------- */

/** Date du jour au format « 2026-09-15 », comparable telle quelle. */
function aujourdhui() {
  const maintenant = new Date();
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return maintenant.getFullYear() + '-' + mois + '-' + jour;
}

/** Filtre sur le pôle, en ignorant les entrées malformées. */
function duPole(liste, code) {
  return (Array.isArray(liste) ? liste : []).filter(
    (entree) => entree && typeof entree === 'object' && entree.pole === code);
}

/** Tri par date, croissant ou décroissant, égalités départagées par titre. */
function parDate(croissant) {
  return (a, b) => {
    const da = String(a.date || '');
    const db = String(b.date || '');
    const ordre = croissant ? da.localeCompare(db) : db.localeCompare(da);
    if (ordre !== 0) return ordre;
    return String(a.titre || '').localeCompare(String(b.titre || ''), 'fr');
  };
}

/**
 * Le prochain point et le dernier compte-rendu de ce pôle.
 *
 * « Prochain » se lit par rapport à la date du jour : le point à venir le
 * plus proche. Si tous les points annoncés sont passés, on montre le plus
 * récent d'entre eux plutôt que rien — l'information reste vraie, et la
 * date affichée permet de le constater.
 *
 * @param {object} donnees contenu de reunions.json
 * @param {string} code
 * @returns {{prochain: object|null, dernier: object|null}}
 */
function reunionsDuPole(donnees, code) {
  verifierForme(donnees, {
    comptesRendus: 'tableau',
    prochainsPoints: 'tableau'
  }, 'reunions.json');

  const points = duPole(donnees.prochainsPoints, code).sort(parDate(true));
  const jour = aujourdhui();
  const aVenir = points.filter((point) => String(point.date || '') >= jour);

  const comptesRendus = duPole(donnees.comptesRendus, code).sort(parDate(false));

  return {
    prochain: aVenir[0] || points[points.length - 1] || null,
    dernier: comptesRendus[0] || null
  };
}

/**
 * Compte d'éléments d'une réunion, rendu en badge étiqueté.
 * @param {*} liste
 * @param {string} singulier
 * @param {string} pluriel
 * @returns {Element|null}
 */
function badgeCompte(liste, singulier, pluriel) {
  const nombre = Array.isArray(liste) ? liste.length : 0;
  if (nombre === 0) return null;
  return el('span', { class: 'badge badge--neutre badge--contour' },
    nombre + ' ' + (nombre > 1 ? pluriel : singulier));
}

/**
 * Carte d'une réunion — prochain point ou compte-rendu.
 *
 * @param {object} reunion
 * @param {string} code
 * @param {string} nature  'Prochain point' ou 'Dernier compte-rendu'
 * @returns {Element}
 */
function carteReunion(reunion, code, nature) {
  const resume = reunion.synthese || reunion.objectif || '';

  return el('article', { class: 'carte carte--compacte' },
    el('div', { class: 'carte__entete' },
      el('h3', { class: 'carte__titre' },
        el('a', {
          class: 'carte__lien',
          href: lienPole('reunions.html', code, { reunion: reunion.id })
        }, String(reunion.titre || nature))),
      el('span', { class: 'badge badge--accent' }, nature)),

    el('p', { class: 'carte__meta sans-marge' },
      reunion.date
        ? el('time', { datetime: String(reunion.date) }, dateLongue(reunion.date))
        : null,
      reunion.lieu ? el('span', null, String(reunion.lieu)) : null),

    resume ? el('p', { class: 'sans-marge texte-doux' }, String(resume)) : null,

    el('p', { class: 'rangee rangee--serree sans-marge' },
      badgeCompte(reunion.sujets, 'sujet', 'sujets'),
      badgeCompte(reunion.actions, 'action', 'actions'),
      badgeCompte(reunion.decisions, 'décision', 'décisions')));
}

/**
 * Carte d'absence : la moitié manquante garde sa place et son titre.
 *
 * Un trou dans une grille se lit mal ; une carte qui dit ce qui manque se
 * lit tout de suite. Les deux colonnes restent alignées.
 *
 * @param {string} nature
 * @param {string} explication
 * @returns {Element}
 */
function carteReunionAbsente(nature, explication) {
  return el('article', { class: 'carte carte--plate carte--compacte' },
    el('div', { class: 'carte__entete' },
      el('h3', { class: 'carte__titre texte-lg' }, nature),
      el('span', { class: 'badge badge--neutre' }, 'Aucun')),
    el('p', { class: 'sans-marge texte-doux texte-sm' }, explication));
}

/**
 * Rend le prochain point et le dernier compte-rendu.
 *
 * Les deux moitiés sont indépendantes : un pôle qui n'a pas encore de
 * compte-rendu garde son prochain point, et réciproquement.
 *
 * @param {object} pole
 * @param {{prochain: object|null, dernier: object|null}} reunions
 * @param {Element} conteneur
 */
function rendreReunions(pole, reunions, conteneur) {
  const cartes = el('div', { class: 'grille grille--ample' });

  cartes.append(reunions.prochain
    ? carteReunion(reunions.prochain, pole.cle, 'Prochain point')
    : carteReunionAbsente('Prochain point',
        'Aucun point n’est programmé pour ce pôle à ce jour.'));

  cartes.append(reunions.dernier
    ? carteReunion(reunions.dernier, pole.cle, 'Dernier compte-rendu')
    : carteReunionAbsente('Dernier compte-rendu',
        'Aucun compte-rendu n’est encore publié pour ce pôle.'));

  monter(conteneur,
    cartes,
    lienSuite('reunions.html', pole.cle, 'Toutes les réunions du pôle'));
}

/* -------------------------------------------------------------------------
   9. Section « FAQ »
   ------------------------------------------------------------------------- */

/**
 * Les premières questions de ce pôle, dans l'ordre éditorial du fichier.
 *
 * L'ordre du fichier est ici un choix de rédaction — les questions y sont
 * rangées de la plus générale à la plus pointue. La page FAQ, elle, classe
 * par pertinence dès qu'une recherche est saisie.
 *
 * @param {object} donnees contenu de faq.json
 * @param {string} code
 * @returns {object[]}
 */
function questionsDuPole(donnees, code) {
  verifierForme(donnees, { questions: 'tableau' }, 'faq.json');

  return donnees.questions
    .filter((entree) => entree && typeof entree === 'object'
      && entree.pole === code)
    .slice(0, MAX_QUESTIONS);
}

/**
 * Rend l'aperçu de la FAQ du pôle.
 * @param {object} pole
 * @param {object[]} questions
 * @param {Element} conteneur
 */
function rendreFaq(pole, questions, conteneur) {
  monter(conteneur,
    el('ul', { class: 'pile' },
      questions.map((question) => el('li', { class: 'carte carte--compacte carte--cliquable' },
        el('h3', { class: 'carte__titre' },
          el('a', {
            class: 'carte__lien',
            href: lienPole('faq.html', pole.cle, { question: question.id })
          }, String(question.question || 'Question'))),

        question.categorie
          ? el('p', { class: 'carte__meta sans-marge' },
              el('span', { class: 'badge badge--neutre badge--contour' },
                String(question.categorie)))
          : null,

        question.reponse
          ? el('p', { class: 'sans-marge texte-doux' }, String(question.reponse))
          : null))),
    lienSuite('faq.html', pole.cle, 'Toute la FAQ du pôle'));
}

/* -------------------------------------------------------------------------
   10. En-tête de la page et sous-navigation
   ------------------------------------------------------------------------- */

/**
 * Renseigne le titre, la métaphore et la description du pôle.
 *
 * Le `<h1>` existe déjà dans le HTML — il y a exactement un titre de
 * premier niveau par page, qu'il y ait ou non du JavaScript. On ne fait
 * ici que le préciser. La pastille colorée est décorative : le code du
 * pôle, juste à côté, porte seul l'information.
 *
 * @param {object} pole
 */
function rendreEntete(pole) {
  const titre = document.getElementById('pole-titre');
  if (titre) {
    monter(titre,
      el('span', { class: 'pole-titre__pastille', 'aria-hidden': 'true' }),
      el('span', { class: 'pole-titre__code' }, pole.cle),
      el('span', { class: 'pole-titre__metaphore' }, pole.metaphore));
  }

  const description = document.getElementById('pole-description');
  if (description) description.textContent = pole.description;

  /* L'onglet du navigateur nomme lui aussi le pôle : les trois espaces
     sont distinguables dans l'historique et dans les favoris. */
  try {
    document.title = pole.cle + ' — ' + pole.metaphore + ' — ETII Hub';
  } catch (_e) { /* ignoré */ }
}

/**
 * Construit la sous-navigation vers les quatre pages transverses, chaque
 * lien portant le pôle actif dans son hash.
 *
 * @param {object} pole
 */
function rendreSousNav(pole) {
  const hote = document.getElementById('pole-sous-nav');
  if (!hote) return;

  hote.setAttribute('aria-label', 'Pages du pôle ' + pole.cle);
  monter(hote,
    el('ul', { class: 'rangee rangee--serree' },
      PAGES_TRANSVERSES.map((entree) => el('li', null,
        el('a', {
          class: 'bouton bouton--secondaire bouton--compact',
          href: lienPole(entree.page, pole.cle)
        }, entree.libelle)))));
}

/**
 * Refus propre d'un paramètre inconnu.
 *
 * `data-pole` absent, mal orthographié, ou valant « ETII » (le niveau
 * service, qui a son propre tableau de bord) : la page ne charge aucune
 * donnée, explique ce qui manque et propose les trois destinations
 * valides. Elle reste entièrement navigable.
 *
 * @param {string} brut valeur lue sur <body>
 */
function refuser(brut) {
  const hote = document.getElementById('pole-alerte');
  const codes = Object.keys(POLES);

  const message = brut
    ? 'Le paramètre « ' + brut + ' » ne désigne aucun pôle du service.'
    : 'Cette page n’indique aucun pôle : son attribut data-pole est absent.';

  if (hote) {
    hote.hidden = false;
    monter(hote,
      el('div', { class: 'etat-vide etat-vide--encadre etat-vide--erreur', role: 'alert' },
        el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '!'),
        el('p', { class: 'etat-vide__titre' }, 'Espace de pôle inconnu'),
        el('p', { class: 'etat-vide__texte' },
          message + ' Les espaces de pôle sont ' + codes.join(', ')
          + '. Le niveau service, lui, est le tableau de bord ETII.'),
        el('div', { class: 'etat-vide__actions' },
          frag(
            codes.map((code) => el('a', {
              class: 'bouton bouton--secondaire',
              href: code.toLowerCase() + '.html'
            }, code)),
            el('a', { class: 'bouton bouton--principal', href: 'index.html' },
              'Tableau de bord ETII')))));
  }

  /* Les sections vides n'ont plus lieu d'être : on les retire du document
     plutôt que de les laisser tourner indéfiniment sur un squelette. */
  const sections = document.querySelectorAll('[data-section-pole]');
  for (const section of sections) section.remove();

  console.error('[pole] ' + message);
}

/* -------------------------------------------------------------------------
   11. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

/** Valeur brute du paramètre de page, telle qu'écrite dans le HTML. */
const PARAMETRE = (document.body && document.body.dataset
  ? String(document.body.dataset.pole || '')
  : '').trim();

/** Le pôle correspondant, ou null si le paramètre est inconnu. */
const POLE = Object.prototype.hasOwnProperty.call(POLES, PARAMETRE.toUpperCase())
  ? POLES[PARAMETRE.toUpperCase()]
  : null;

/* La navigation principale marque le lien du pôle courant. L'attribut est
   déjà posé dans le HTML ; initNav() le confirme et garantit qu'il n'y en
   a jamais deux. */
initNav(POLE ? POLE.cle.toLowerCase() + '.html' : '');

if (!POLE) {
  refuser(PARAMETRE);
} else {
  rendreEntete(POLE);
  rendreSousNav(POLE);

  /* Retour arrière, avance, ou lien collé : le hash reste la source de
     vérité de l'indicateur affiché. L'écouteur est posé une seule fois,
     même si la zone est reconstruite par un « Réessayer ». */
  etatUrl.ecouter(() => {
    if (typeof appliquerIndicateur === 'function') {
      appliquerIndicateur(indicateurDemande(), true);
    }
  });

  /* 5 — Indicateurs du pôle. */
  avecEtat('#zone-indicateurs', () => chargerDonnees('indicateurs'),
    (donnees, conteneur) => rendreIndicateurs(POLE, donnees, conteneur), {
      squelette: 2,
      texteChargement: 'Chargement des indicateurs du pôle ' + POLE.cle + '…',
      titreErreur: 'Indicateurs indisponibles',
      titreVide: 'Aucun indicateur publié',
      texteVide: 'Les indicateurs de ce pôle apparaîtront ici dès qu’une '
        + 'première période aura été publiée.'
    });

  /* 6 — Organigramme en résumé. */
  avecEtat('#zone-organigramme',
    async () => blocOrganigramme(await chargerDonnees('organigramme'), POLE.cle),
    (bloc, conteneur) => rendreOrganigramme(POLE, bloc, conteneur), {
      squelette: 2,
      texteChargement: 'Chargement de l’organigramme du pôle…',
      titreErreur: 'Organigramme indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans '
        + 'l’organigramme du service.'
    });

  /* 7 — Communication du pôle. */
  avecEtat('#zone-communication',
    async () => annoncesDuPole(await chargerDonnees('communications'), POLE.cle),
    (annonces, conteneur) => rendreCommunication(POLE, annonces, conteneur), {
      squelette: 2,
      compact: true,
      texteChargement: 'Chargement des annonces du pôle…',
      titreErreur: 'Annonces indisponibles',
      titreVide: 'Aucune annonce pour ce pôle',
      texteVide: 'Les annonces publiées par ce pôle apparaîtront ici. '
        + 'Celles du service restent sur le tableau de bord ETII.'
    });

  /* 8 — Réunions du pôle. Un seul cycle pour les deux moitiés : elles
     viennent du même fichier, et l'absence de l'une n'est pas une erreur. */
  avecEtat('#zone-reunions',
    async () => reunionsDuPole(await chargerDonnees('reunions'), POLE.cle),
    (reunions, conteneur) => rendreReunions(POLE, reunions, conteneur), {
      squelette: 2,
      compact: true,
      estVide: (reunions) => !reunions || (!reunions.prochain && !reunions.dernier),
      texteChargement: 'Chargement des réunions du pôle…',
      titreErreur: 'Réunions indisponibles',
      titreVide: 'Aucune réunion pour ce pôle',
      texteVide: 'Ni point à venir, ni compte-rendu publié pour ce pôle '
        + 'à ce jour.'
    });

  /* 9 — FAQ du pôle. */
  avecEtat('#zone-faq',
    async () => questionsDuPole(await chargerDonnees('faq'), POLE.cle),
    (questions, conteneur) => rendreFaq(POLE, questions, conteneur), {
      squelette: 3,
      compact: true,
      texteChargement: 'Chargement des questions du pôle…',
      titreErreur: 'Questions indisponibles',
      titreVide: 'Aucune question pour ce pôle',
      texteVide: 'Les questions fréquentes de ce pôle apparaîtront ici. '
        + 'La base de connaissances complète reste accessible.'
    });
}
