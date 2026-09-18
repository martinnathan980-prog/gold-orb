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

   Composition de la page, dans cet ordre :

     1. En-tête        code du pôle, métaphore, une phrase, filet coloré
     2. Communication  #zone-communication   communications.json (« agenda »)
     3. Organigramme   #zone-organigramme    organigramme.json
     4. Questions      #zone-faq             faq.json

   La communication vient en premier : c'est la raison d'être de la page.
   Les trois zones ont trois cycles d'état indépendants (data.js). Si
   organigramme.json manque, seule cette section porte le message ; la
   frise et les questions continuent de s'afficher.

   RIEN N'EST INVENTÉ. Ce module n'affiche que ce que les fichiers JSON
   contiennent. Un champ déclaré mais vide s'affiche « à renseigner » :
   jamais une valeur plausible, jamais un compte reconstitué, jamais une
   étiquette de remplacement. Les seuls textes rédigés ici sont le libellé
   éditorial des trois pôles et les phrases d'interface.

   Le pôle actif voyage ensuite dans le hash des pages transverses
   (`communication.html#pole=ETIIA`), conformément au contrat d'URL.

   Tout le DOM est construit avec el(), frag() et monter() : aucun
   innerHTML, aucun gestionnaire en attribut HTML.
   ========================================================================= */

import { el, frag, monter, initTheme, initNav } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/*
   Les trois pôles de l'accord d'équipe. Le libellé, la métaphore et la
   phrase de présentation sont de la matière éditoriale, pas de la donnée :
   ils vivent ici, pas dans un JSON. La couleur est un jeton de tokens.css —
   jamais une valeur brute, et jamais le seul signal du pôle : le filet est
   toujours accompagné du libellé « Pôle ETIIA ».
*/
const POLES = {
  ETIIA: {
    cle: 'ETIIA',
    metaphore: 'Squelette & ADN',
    description: 'Logique et règles d’architecture : découpage '
      + 'fonctionnel, conventions de nommage et principes que tous les '
      + 'autres travaux appliquent ensuite.'
  },
  ETIIE: {
    cle: 'ETIIE',
    metaphore: 'Système nerveux',
    description: 'Schémas électriques et communication entre systèmes : '
      + 'signaux, interfaces et cohérence des échanges d’un bout à l’autre '
      + 'de la définition.'
  },
  ETIII: {
    cle: 'ETIII',
    metaphore: 'Structure & harnais',
    description: 'Intégration physique et routage dans la maquette '
      + 'numérique : cheminements, fixations et vérification des '
      + 'interférences avant fabrication.'
  }
};

/** Nombre de questions reprises dans l'aperçu de la FAQ. */
const MAX_QUESTIONS = 3;

/** Mention unique d'un champ attendu mais vide. Jamais autre chose. */
const MANQUANT = 'à renseigner';

const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

/* -------------------------------------------------------------------------
   2. Lecture prudente des champs
   ------------------------------------------------------------------------- */

/**
 * Chaîne exploitable, ou null. Une chaîne d'espaces ne vaut pas mieux
 * qu'un champ absent : dans les deux cas il n'y a rien à afficher.
 *
 * @param {*} valeur
 * @returns {string|null}
 */
function texteNet(valeur) {
  if (typeof valeur !== 'string') return null;
  const net = valeur.trim();
  return net === '' ? null : net;
}

/**
 * La clé est-elle réellement déclarée sur l'entrée ?
 *
 * La distinction porte tout le contrat de données de cette page : une clé
 * absente du fichier n'a rien à dire, une clé présente mais vide est un
 * trou à combler, et se signale comme tel.
 *
 * @param {*} objet
 * @param {string} cle
 * @returns {boolean}
 */
function declare(objet, cle) {
  return !!objet && typeof objet === 'object'
    && Object.prototype.hasOwnProperty.call(objet, cle);
}

/** Mention « à renseigner », toujours identique, toujours reconnaissable. */
function manquant() {
  return el('span', { class: 'champ-manquant' }, MANQUANT);
}

/**
 * Le texte du champ, ou la mention « à renseigner ».
 * @param {*} valeur
 * @returns {string|Element}
 */
function texteOuManquant(valeur) {
  return texteNet(valeur) || manquant();
}

/**
 * Date longue à partir d'un « 2026-09-12 » → « 12 septembre 2026 ».
 * Une date non conforme est rendue telle quelle : on montre ce que le
 * fichier contient, on ne le corrige pas.
 *
 * @param {string} code
 * @returns {string}
 */
function dateLongue(code) {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(code);
  if (!parts) return code;

  const index = Number(parts[2]) - 1;
  if (index < 0 || index > 11) return code;

  const jour = Number(parts[3]);
  return (jour === 1 ? '1er' : String(jour))
    + ' ' + MOIS_LONGS[index] + ' ' + parts[1];
}

/**
 * Élément de date, ou mention « à renseigner ».
 * @param {*} valeur
 * @returns {Element}
 */
function noeudDate(valeur) {
  const net = texteNet(valeur);
  if (!net) return manquant();
  return el('time', { datetime: net }, dateLongue(net));
}

/** Date du jour au format « 2026-09-16 », comparable telle quelle. */
function aujourdhui() {
  const maintenant = new Date();
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return maintenant.getFullYear() + '-' + mois + '-' + jour;
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
 * @param {object} [extra] paramètre supplémentaire, ex. { annonce: 'a02' }
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
 * Bouton-lien « voir tout », commun aux trois sections.
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
   4. Section « Communication » — la frise de l'agenda du pôle
   ------------------------------------------------------------------------- */

/*
   Les entrées viennent du tableau « agenda » de communications.json, filtré
   sur ce pôle. Les communications de niveau service restent sur le tableau
   de bord ETII : un espace de pôle ne montre que ce qui lui appartient.

   Le classement suit d'abord le champ « statut » du fichier, qui fait foi.
   S'il est absent, la date est comparée au jour courant. Si les deux
   manquent, l'entrée n'est pas devinée : elle rejoint un troisième groupe
   qui dit exactement cela.
*/

/** Les trois groupes de la frise, dans l'ordre d'affichage. */
const GROUPES = [
  {
    cle: 'aVenir',
    id: 'frise-a-venir',
    titre: 'À venir',
    vide: 'Aucune communication à venir n’est publiée pour ce pôle.'
  },
  {
    cle: 'passees',
    id: 'frise-passees',
    titre: 'Passées',
    vide: 'Aucune communication passée n’est publiée pour ce pôle.'
  },
  {
    cle: 'sansDate',
    id: 'frise-sans-date',
    titre: 'Non situées dans le temps',
    vide: ''
  }
];

/**
 * Tri par date, égalités départagées par le titre — jamais par l'ordre
 * d'insertion du fichier (SPEC §5).
 *
 * @param {boolean} croissant
 * @returns {(a: object, b: object) => number}
 */
function parDate(croissant) {
  return (a, b) => {
    const da = texteNet(a.date) || '';
    const db = texteNet(b.date) || '';
    const ordre = croissant ? da.localeCompare(db) : db.localeCompare(da);
    if (ordre !== 0) return ordre;
    return String(a.titre || '').localeCompare(String(b.titre || ''), 'fr');
  };
}

/**
 * Répartit les entrées d'agenda de ce pôle en trois groupes.
 *
 * @param {object} donnees contenu de communications.json
 * @param {string} code
 * @returns {{aVenir: object[], passees: object[], sansDate: object[]}}
 */
function agendaDuPole(donnees, code) {
  verifierForme(donnees, { agenda: 'tableau' }, 'communications.json');

  const jour = aujourdhui();
  const groupes = { aVenir: [], passees: [], sansDate: [] };

  for (const entree of donnees.agenda) {
    if (!entree || typeof entree !== 'object' || entree.pole !== code) continue;

    const statut = texteNet(entree.statut);
    const date = texteNet(entree.date);

    if (statut === 'a-venir') groupes.aVenir.push(entree);
    else if (statut === 'passee') groupes.passees.push(entree);
    else if (date) (date >= jour ? groupes.aVenir : groupes.passees).push(entree);
    else groupes.sansDate.push(entree);
  }

  /* À venir : la plus proche en tête. Passées : antichronologique. */
  groupes.aVenir.sort(parDate(true));
  groupes.passees.sort(parDate(false));
  groupes.sansDate.sort((a, b) =>
    String(a.titre || '').localeCompare(String(b.titre || ''), 'fr'));

  return groupes;
}

/**
 * Une entrée de la frise : un point sur le rail, une date, un type, un
 * titre, un résumé.
 *
 * Le point du rail est plein pour ce qui vient, creux pour ce qui est
 * passé. Cette nuance est décorative : le groupe auquel l'entrée appartient
 * porte déjà l'information, en toutes lettres.
 *
 * @param {object} entree
 * @param {string} code
 * @param {string} groupe  clé du groupe ('aVenir', 'passees', 'sansDate')
 * @returns {Element}
 */
function entreeFrise(entree, code, groupe) {
  const identifiant = texteNet(entree.id);

  /* Le titre mène à la communication complète, avec le pôle et l'entrée
     dans le hash. Sans identifiant, il n'y a rien à cibler : le titre
     reste alors du texte, et le lien de section suffit. */
  const titre = texteOuManquant(entree.titre);
  const titreNoeud = identifiant
    ? el('a', {
        class: 'frise__lien',
        href: lienPole('communication.html', code, { annonce: identifiant })
      }, titre)
    : titre;

  return el('li', {
    class: ['frise__entree', groupe === 'aVenir' ? 'frise__entree--a-venir' : null]
  },
  el('span', { class: 'frise__rail', 'aria-hidden': 'true' },
    el('span', { class: 'frise__point' })),

  el('div', { class: 'frise__corps' },
    el('p', { class: 'frise__meta sans-marge' },
      noeudDate(entree.date),
      declare(entree, 'type')
        ? el('span', { class: 'frise__type' }, texteOuManquant(entree.type))
        : null),

    el('h4', { class: 'frise__titre sans-marge' }, titreNoeud),

    declare(entree, 'resume')
      ? el('p', { class: 'frise__resume sans-marge' },
          texteOuManquant(entree.resume))
      : null));
}

/**
 * Un groupe de la frise : son intitulé, son compte, ses entrées.
 * Un groupe vide garde sa place et dit qu'il est vide — sauf le troisième,
 * qui n'a de sens que s'il contient quelque chose.
 *
 * @param {object} definition entrée de GROUPES
 * @param {object[]} entrees
 * @param {string} code
 * @returns {Element|null}
 */
function groupeFrise(definition, entrees, code) {
  if (entrees.length === 0 && !definition.vide) return null;

  return el('div', { class: 'frise__groupe' },
    el('div', { class: 'frise__entete' },
      el('h3', { class: 'frise__intitule sans-marge', id: definition.id },
        definition.titre),
      el('span', { class: 'badge badge--neutre' },
        entrees.length + (entrees.length > 1 ? ' entrées' : ' entrée'))),

    entrees.length
      ? el('ol', { class: 'frise__liste', 'aria-labelledby': definition.id },
          entrees.map((entree) => entreeFrise(entree, code, definition.cle)))
      : el('p', { class: 'texte-doux texte-sm sans-marge' }, definition.vide));
}

/**
 * Rend la frise de communication du pôle.
 *
 * @param {object} pole
 * @param {{aVenir: object[], passees: object[], sansDate: object[]}} groupes
 * @param {Element} conteneur
 */
function rendreCommunication(pole, groupes, conteneur) {
  monter(conteneur,
    el('div', { class: 'frise' },
      GROUPES.map((definition) =>
        groupeFrise(definition, groupes[definition.cle] || [], pole.cle))),
    lienSuite('communication.html', pole.cle,
      'Toute la communication du pôle'));
}

/* -------------------------------------------------------------------------
   5. Section « Organigramme en résumé »
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
 * Effectif d'une squad, ou null si le fichier ne le dit pas.
 * Un effectif inconnu n'est pas zéro : il est inconnu.
 *
 * @param {*} squad
 * @returns {number|null}
 */
function effectifSquad(squad) {
  if (!squad || typeof squad !== 'object') return null;
  return Array.isArray(squad.membres) ? squad.membres.length : null;
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
 * Identifiant lisible d'une personne : « p03 » s'écrit P03, comme sur la
 * page de l'organigramme. Sans identifiant, la mention « à renseigner ».
 *
 * @param {*} personne
 * @returns {string|Element}
 */
function identifiantLisible(personne) {
  const id = texteNet(personne && personne.id);
  return id ? id.toUpperCase() : manquant();
}

/**
 * Rend l'équipe du pôle : le responsable en tête, puis chaque squad sous
 * forme d'un volet qui se déplie sur la liste de ses membres — identifiant,
 * nom, poste et périmètre, tels que le fichier les déclare. Le lead de la
 * squad est nommé dès le volet fermé : c'est lui qu'on cherche le plus
 * souvent. Les volets sont des <details> natifs : ouverts et fermés au
 * clavier comme à la souris, sans un octet de script.
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
  const effectifs = squads.map(effectifSquad);

  /* L'effectif total n'est affiché que s'il est entièrement connu : un
     total partiel se lirait comme un total, et serait faux. */
  const totalConnu = effectifs.every((nombre) => nombre !== null);
  const total = totalConnu
    ? (responsable ? 1 : 0) + effectifs.reduce((somme, n) => somme + n, 0)
    : null;

  const compteurs = el('p', { class: 'rangee rangee--serree sans-marge' },
    total === null
      ? null
      : el('span', { class: 'badge badge--neutre' }, effectifLisible(total)),
    el('span', { class: 'badge badge--neutre badge--contour' },
      squads.length + (squads.length > 1 ? ' squads' : ' squad')));

  /* Le responsable : une ligne de tête, marquée du filet du pôle. */
  const ligneResponsable = responsable
    ? el('div', { class: 'equipe__tete' },
        el('span', { class: 'equipe__id mono' }, identifiantLisible(responsable)),
        el('span', { class: 'equipe__nom' }, texteOuManquant(responsable.nom)),
        el('span', { class: 'equipe__poste' }, texteOuManquant(responsable.poste)),
        declare(responsable, 'perimetre')
          ? el('span', { class: 'equipe__perimetre mono' },
              texteOuManquant(responsable.perimetre))
          : null)
    : el('p', { class: 'texte-doux sans-marge' },
        'Ce pôle n’a pas de responsable déclaré dans l’organigramme.');

  /* Les squads : un volet chacune, le lead nommé dès le volet fermé. */
  const listeSquads = squads.length
    ? el('div', { class: 'equipe__squads' },
        squads.map((squad, rang) => {
          const membres = Array.isArray(squad && squad.membres) ? squad.membres : [];
          const lead = membres.find((m) => m && typeof m === 'object' && m.role === 'leader') || null;

          return el('details', { class: 'squad' },
            el('summary', { class: 'squad__resume' },
              el('span', { class: 'chevron', 'aria-hidden': 'true' }),
              el('span', { class: 'squad__nom' }, texteOuManquant(squad && squad.nom)),
              el('span', { class: 'squad__effectif mono' },
                effectifs[rang] === null ? manquant() : effectifLisible(effectifs[rang])),
              lead
                ? el('span', { class: 'squad__lead' },
                    el('span', { class: 'texte-faible' }, texteOuManquant(lead.poste), ' · '),
                    texteOuManquant(lead.nom))
                : null),
            membres.length
              ? el('ol', { class: 'squad__membres' },
                  membres.map((membre) => el('li', {
                    class: ['squad__membre',
                      membre && membre.role === 'leader' ? 'squad__membre--lead' : null]
                  },
                    el('span', { class: 'squad__id mono' }, identifiantLisible(membre)),
                    el('span', { class: 'squad__membre-nom' },
                      texteOuManquant(membre && membre.nom)),
                    el('span', { class: 'squad__membre-poste' },
                      texteOuManquant(membre && membre.poste)),
                    el('span', { class: 'squad__membre-perimetre mono' },
                      declare(membre, 'perimetre') ? texteOuManquant(membre.perimetre) : ''))))
              : el('p', { class: 'texte-doux texte-sm squad__vide sans-marge' },
                  'Aucun membre déclaré pour cette squad.'));
        }))
    : el('p', { class: 'texte-doux sans-marge' },
        'Aucune squad n’est rattachée à ce pôle dans l’organigramme.');

  monter(conteneur,
    compteurs,
    ligneResponsable,
    listeSquads,
    lienSuite('organigramme.html', pole.cle,
      'Voir l’organigramme complet du pôle'));
}

/* -------------------------------------------------------------------------
   6. Section « Questions fréquentes »
   ------------------------------------------------------------------------- */

/**
 * Les trois premières questions de ce pôle, dans l'ordre du fichier.
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
 * Rend l'aperçu de la FAQ du pôle : chaque question est un volet qui se
 * déplie sur sa réponse, avec un lien vers la fiche complète. En pied,
 * deux actions : toute la FAQ du pôle, et poser une question aux experts —
 * le lien ouvre directement la fenêtre de demande, pôle présélectionné.
 *
 * @param {object} pole
 * @param {object[]} questions
 * @param {Element} conteneur
 */
function rendreFaq(pole, questions, conteneur) {
  const volets = questions.length
    ? el('div', { class: 'faq-apercu' },
        questions.map((question) => {
          const identifiant = texteNet(question.id);

          return el('details', { class: 'faq-apercu__entree' },
            el('summary', { class: 'faq-apercu__question' },
              el('span', { class: 'chevron', 'aria-hidden': 'true' }),
              el('span', { class: 'faq-apercu__intitule' },
                texteOuManquant(question.question)),
              declare(question, 'categorie')
                ? el('span', { class: 'badge badge--neutre badge--contour' },
                    texteOuManquant(question.categorie))
                : null),
            el('div', { class: 'faq-apercu__reponse' },
              el('p', { class: 'mesure sans-marge' },
                declare(question, 'reponse') ? texteOuManquant(question.reponse) : manquant()),
              identifiant
                ? el('a', {
                    class: 'faq-apercu__lien',
                    href: lienPole('faq.html', pole.cle, { question: identifiant })
                  }, 'Ouvrir dans la base de connaissances')
                : null));
        }))
    : el('p', { class: 'texte-doux sans-marge' },
        'Aucune question n’est encore rattachée à ce pôle.');

  monter(conteneur,
    volets,
    el('p', { class: 'rangee sans-marge' },
      el('a', { class: 'bouton bouton--secondaire', href: lienPole('faq.html', pole.cle) },
        'Toute la FAQ du pôle'),
      el('a', {
        class: 'bouton bouton--principal',
        href: lienPole('faq.html', pole.cle, { proposer: 1 })
      }, 'Poser une question aux experts')));
}

/* -------------------------------------------------------------------------
   7. En-tête de la page
   ------------------------------------------------------------------------- */

/**
 * Renseigne le libellé, le titre, la métaphore et la phrase du pôle.
 *
 * Le `<h1>` existe déjà dans le HTML — il y a exactement un titre de
 * premier niveau par page, qu'il y ait ou non du JavaScript. On ne fait
 * ici que le préciser. Le filet coloré est posé par le CSS à partir de
 * `data-pole` : il est donc juste avant le premier octet de script, et le
 * reste si celui-ci ne vient jamais. Il n'est jamais seul — le libellé
 * « Pôle ETIIA » l'accompagne.
 *
 * @param {object} pole
 */
function rendreEntete(pole) {
  const libelle = document.getElementById('pole-libelle');
  if (libelle) libelle.textContent = 'Pôle ' + pole.cle;

  const titre = document.getElementById('pole-titre');
  if (titre) {
    monter(titre,
      el('span', null, pole.cle),
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
   8. Démarrage
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

  /* 4 — Communication du pôle. C'est la section qui compte : elle est en
     tête de page, et son squelette est le plus généreux. */
  avecEtat('#zone-communication',
    async () => agendaDuPole(await chargerDonnees('communications'), POLE.cle),
    (groupes, conteneur) => rendreCommunication(POLE, groupes, conteneur), {
      squelette: 4,
      estVide: (groupes) => !groupes
        || (groupes.aVenir.length + groupes.passees.length
            + groupes.sansDate.length) === 0,
      texteChargement: 'Chargement de la communication du pôle ' + POLE.cle + '…',
      titreErreur: 'Communication indisponible',
      titreVide: 'Aucune communication pour ce pôle',
      texteVide: 'Les communications publiées par ce pôle apparaîtront ici. '
        + 'Celles du service restent sur le tableau de bord ETII.'
    });

  /* 5 — Organigramme en résumé. */
  avecEtat('#zone-organigramme',
    async () => blocOrganigramme(await chargerDonnees('organigramme'), POLE.cle),
    (bloc, conteneur) => rendreOrganigramme(POLE, bloc, conteneur), {
      squelette: 2,
      compact: true,
      texteChargement: 'Chargement de l’organigramme du pôle…',
      titreErreur: 'Organigramme indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans '
        + 'l’organigramme du service.'
    });

  /* 6 — Questions fréquentes du pôle. */
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
