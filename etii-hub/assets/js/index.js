/* =========================================================================
   ETII Hub — La page du service ETII (index.html)

   C'est la vitrine du service, et elle est ordonnée par importance :

     1. LE DISPATCHER — trois cartes de pôle. Le premier geste attendu
        d'un arrivant est de choisir son pôle : rien ne passe avant.
     2. LE MOT DU CHEF DE SERVICE — une parole, dans son propre bloc.
     3. LA FLOTTE — le carrousel des appareils suivis.
     4. LE SUIVI OTQ / OTD — tuiles, douze mois par pôle, comparaison,
        puis une ligne d'état disant d'où viennent ces chiffres.
     5. LES ANNONCES DE SERVICE — en fin de page, deux au plus.
     6. LA RECHERCHE DOCUMENTAIRE — écrite en dur dans la page.

   Cinq zones asynchrones, cinq cycles d'état indépendants (data.js) :

     #zone-poles         organigramme.json (+ indicateurs.json, facultatif)
     #zone-mot           communications.json → motDuChef
     #zone-flotte        flotte.json
     #zone-indicateurs   indicateurs.json
     #zone-communication communications.json → annonces

   L'indépendance est délibérée : chaque section affiche son propre état.
   Si indicateurs.json ne charge pas, les cartes de pôle s'affichent quand
   même — leur effectif vient de l'organigramme, seule la mention d'OTQ
   manque. Si communications.json manque, le mot du chef et les annonces
   le disent chacun de leur côté, et la flotte continue de défiler.

   Tout le DOM est construit avec el() / monter() : aucun innerHTML, aucun
   gestionnaire en attribut HTML, aucune valeur de style en dur — les
   seules propriétés posées sont des `--…` valant un jeton de tokens.css.
   ========================================================================= */

import { el, monter, etatUrl, initTheme, initNav, annoncer } from './ui.js';
import { chargerDonnees, viderCache, avecEtat, verifierForme } from './data.js';
import { tuileIndicateur, graphiqueLignes, barresComparees } from './indicateurs.js';
import { carrousel } from './helicos.js';

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/*
   Les trois pôles, dans l'ordre de l'accord d'équipe. Le libellé, la
   métaphore et la phrase de description sont de la matière éditoriale, pas
   de la donnée : ils vivent ici, pas dans un JSON. La couleur est un jeton
   de tokens.css — jamais une valeur brute, et jamais le seul signal du pôle.
*/
const POLES = [
  {
    cle: 'ETIIA',
    metaphore: 'Squelette & ADN',
    description: 'Les règles d’architecture : découpage fonctionnel, '
      + 'conventions de nommage et principes que tous les autres travaux '
      + 'appliquent ensuite.',
    page: 'etiia.html',
    couleur: 'var(--pole-etiia)'
  },
  {
    cle: 'ETIIE',
    metaphore: 'Système nerveux',
    description: 'Les schémas électriques et la communication entre '
      + 'systèmes : signaux, interfaces et cohérence des échanges d’un bout '
      + 'à l’autre de la définition.',
    page: 'etiie.html',
    couleur: 'var(--pole-etiie)'
  },
  {
    cle: 'ETIII',
    metaphore: 'Structure & harnais',
    description: 'L’intégration physique et le routage dans la maquette '
      + 'numérique : cheminements, fixations et vérification des '
      + 'interférences avant fabrication.',
    page: 'etiii.html',
    couleur: 'var(--pole-etiii)'
  }
];

/* Couleur de série du NIVEAU SERVICE, tous pôles confondus. Les tuiles du
   suivi mesurent le service : elles n'empruntent la couleur d'aucun pôle. */
const COULEUR_SERVICE = 'var(--pole-etii)';

/* Ordre d'affichage des indicateurs. L'OTQ vient en premier : c'est
   l'indicateur que le service regarde, et celui que porte chaque carte de
   pôle. Les autres suivent, ils ne le remplacent pas. */
const ORDRE_INDICATEURS = ['otq', 'otd', 'ecarts', 'charge'];

/** Nombre maximal d'annonces de service reprises en fin de page. */
const MAX_ANNONCES = 2;

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
 * Met une valeur numérique en forme française, unité comprise.
 * Les entiers restent entiers (26 écarts, pas 26,0) ; le reste garde une
 * décimale, ce qui suffit à toutes les séries du service.
 *
 * Volontairement local : indicateurs.js formate ce qu'il affiche lui-même,
 * cette fonction ne sert qu'aux textes propres à cette page.
 *
 * @param {*} valeur
 * @param {string} [unite] '%' ou chaîne vide
 * @returns {string} '93,6 %', '26', ou '—' si la valeur est inexploitable
 */
function formaterValeur(valeur, unite) {
  if (typeof valeur !== 'number' || !Number.isFinite(valeur)) return '—';

  const decimales = Number.isInteger(valeur) ? 0 : 1;
  let texte;
  try {
    texte = valeur.toLocaleString('fr-FR', {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales
    });
  } catch (_e) {
    texte = valeur.toFixed(decimales).replace('.', ',');
  }

  // Espace insécable avant l'unité : « 93,6 % » ne doit jamais se couper.
  return unite ? texte + ' ' + unite : texte;
}

/**
 * Libellé d'un mois au format « 2026-09 ».
 *
 * @param {string} code
 * @param {string} [forme] 'long' → « septembre 2026 », 'court' →
 *                         « sept. 26 », sinon « sept. 2026 »
 * @returns {string} le code tel quel s'il est illisible
 */
function libelleMois(code, forme) {
  const brut = String(code === null || code === undefined ? '' : code);
  const parts = /^(\d{4})-(\d{2})$/.exec(brut);
  if (!parts) return brut;

  const index = Number(parts[2]) - 1;
  if (index < 0 || index > 11) return brut;

  if (forme === 'long') return MOIS_LONGS[index] + ' ' + parts[1];
  if (forme === 'court') return MOIS_COURTS[index] + ' ' + parts[1].slice(2);
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
 * Heure de l'horloge locale, en « 14:07 » et en valeur machine.
 * Aucune dépendance à une locale disponible : les chiffres sont composés
 * à la main, donc identiques partout.
 *
 * @param {Date} instant
 * @returns {{affichage:string, machine:string}}
 */
function heureDe(instant) {
  const deuxChiffres = (n) => (n < 10 ? '0' : '') + n;
  const h = deuxChiffres(instant.getHours());
  const m = deuxChiffres(instant.getMinutes());
  const s = deuxChiffres(instant.getSeconds());
  return { affichage: h + ' h ' + m, machine: h + ':' + m + ':' + s };
}

/**
 * Garde-fou de composant : les fabriques d'indicateurs et de flotte
 * doivent rendre un nœud. Une signature qui aurait changé casserait la
 * page entière ; ici elle bascule proprement la zone concernée en état
 * d'erreur, et les autres sections continuent de vivre.
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
    + 'cette section ne peut pas être construite.'
  );
}

/* -------------------------------------------------------------------------
   3. Lecture des séries
   ------------------------------------------------------------------------- */

/**
 * Série d'un indicateur pour une source (un pôle, ou le service).
 * Une série de longueur différente de la période est refusée : mieux vaut
 * masquer une courbe que de la décaler d'un mois.
 *
 * @param {*} source
 * @param {string} cle
 * @param {number} longueur nombre de mois attendu
 * @returns {number[]|null}
 */
function serieDe(source, cle, longueur) {
  if (!source || typeof source !== 'object') return null;
  const serie = source[cle];
  if (!Array.isArray(serie) || serie.length !== longueur) return null;
  return serie;
}

/**
 * Liste des mois couverts par un jeu d'indicateurs, ou [] si illisible.
 * @param {*} indicateurs
 * @returns {string[]}
 */
function moisDe(indicateurs) {
  if (!indicateurs || typeof indicateurs !== 'object') return [];
  const periode = indicateurs.periode;
  if (!periode || typeof periode !== 'object') return [];
  return Array.isArray(periode.mois) ? periode.mois : [];
}

/* =========================================================================
   4. LE DISPATCHER — les trois cartes de pôle
   ========================================================================= */

/**
 * Effectif réel d'un pôle : son responsable, plus les membres de chaque
 * squad. Lu dans organigramme.json, jamais recopié en dur.
 *
 * @param {object} organigramme
 * @param {string} cle 'ETIIA' | 'ETIIE' | 'ETIII'
 * @returns {number|null} null si le pôle est absent des données
 */
function effectifDe(organigramme, cle) {
  const liste = Array.isArray(organigramme.poles) ? organigramme.poles : [];
  const bloc = liste.find((entree) => entree && entree.pole === cle);
  if (!bloc) return null;

  let total = bloc.responsable ? 1 : 0;
  for (const squad of Array.isArray(bloc.squads) ? bloc.squads : []) {
    if (squad && Array.isArray(squad.membres)) total += squad.membres.length;
  }
  return total;
}

/**
 * OTQ du dernier mois pour un pôle, avec sa cible et son unité.
 * Tolère un jeu d'indicateurs absent : la carte s'affichera sans la mesure.
 *
 * @param {object|null} indicateurs
 * @param {string} cle
 * @returns {{valeur:number, unite:string, cible:number|null, mois:string}|null}
 */
function otqDuMois(indicateurs, cle) {
  if (!indicateurs || typeof indicateurs !== 'object') return null;

  const source = indicateurs.poles && indicateurs.poles[cle];
  const serie = source && Array.isArray(source.otq) ? source.otq : null;
  if (!serie || serie.length === 0) return null;

  const index = serie.length - 1;
  if (typeof serie[index] !== 'number') return null;

  const def = (indicateurs.definitions && indicateurs.definitions.otq) || {};
  const mois = moisDe(indicateurs);

  return {
    valeur: serie[index],
    unite: typeof def.unite === 'string' ? def.unite : '%',
    cible: typeof def.cible === 'number' ? def.cible : null,
    mois: mois[index] || ''
  };
}

/**
 * Une mesure du pied de carte : une valeur lisible, son libellé, et
 * éventuellement une pastille d'état.
 *
 * @param {string} libelle
 * @param {string} valeur
 * @param {Element|null} [complement]
 * @returns {Element}
 */
function mesureDePole(libelle, valeur, complement) {
  return el('div', { class: 'carte-pole__mesure' },
    el('span', { class: 'carte-pole__valeur' }, valeur),
    el('span', { class: 'carte-pole__libelle' }, libelle),
    complement || null);
}

/**
 * Carte d'entrée vers l'espace d'un pôle — la brique du dispatcher.
 *
 * La couleur du pôle est portée par le filet de tête et par la pastille du
 * titre, toujours collée au libellé « ETIIA » : elle confirme, elle ne dit
 * jamais seule. Une seule zone cliquable, le lien de titre étiré par
 * .carte__lien::after — aucun gestionnaire posé sur la carte.
 *
 * @param {object} pole entrée de POLES
 * @param {number|null} effectif
 * @param {object|null} otq
 * @returns {Element}
 */
function carteDePole(pole, effectif, otq) {
  const mesures = el('div', { class: 'carte-pole__mesures' });

  mesures.append(mesureDePole(
    'Effectif',
    effectif === null ? '—' : formaterValeur(effectif, ''),
    el('span', { class: 'texte-xs texte-faible' },
      effectif === null
        ? 'Organigramme indisponible'
        : (effectif > 1 ? 'personnes du pôle' : 'personne du pôle'))));

  if (otq) {
    /* La variante colore la pastille, mais le texte dit déjà tout : valeur,
       unité, mois et position par rapport à la cible. Rien ne repose sur la
       seule couleur. */
    const atteinte = typeof otq.cible === 'number' && otq.valeur >= otq.cible;
    mesures.append(mesureDePole(
      'OTQ' + (otq.mois ? ' ' + libelleMois(otq.mois) : '')
        + (typeof otq.cible === 'number'
          ? ' · cible ' + formaterValeur(otq.cible, otq.unite)
          : ''),
      formaterValeur(otq.valeur, otq.unite),
      typeof otq.cible === 'number'
        ? el('span', { class: 'badge ' + (atteinte ? 'badge--succes' : 'badge--alerte') },
            el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
            atteinte ? 'Cible atteinte' : 'Sous la cible')
        : null));
  } else {
    mesures.append(mesureDePole('OTQ', '—',
      el('span', { class: 'texte-xs texte-faible' }, 'Indicateurs indisponibles')));
  }

  return el('article', {
    class: 'carte carte--ample carte--cliquable carte-pole',
    style: { '--couleur-pole': pole.couleur }
  },
    el('div', { class: 'carte__entete' },
      el('h3', { class: 'carte__titre carte-pole__code' },
        el('span', { class: 'carte-pole__point', 'aria-hidden': 'true' }),
        el('a', { class: 'carte__lien', href: pole.page }, pole.cle)),
      el('p', { class: 'carte__sous-titre carte-pole__metaphore' }, pole.metaphore)),

    el('div', { class: 'carte__corps' }, el('p', null, pole.description)),

    mesures);
}

/**
 * Rend les trois cartes du dispatcher.
 * @param {[object, object|null]} ressources [organigramme, indicateurs]
 * @param {Element} conteneur
 */
function rendrePoles(ressources, conteneur) {
  const organigramme = ressources[0];
  const indicateurs = ressources[1];

  verifierForme(organigramme, { poles: 'tableau' }, 'organigramme.json');

  monter(conteneur, el('div', { class: 'grille dispatch' },
    POLES.map((pole) => carteDePole(
      pole,
      effectifDe(organigramme, pole.cle),
      otqDuMois(indicateurs, pole.cle)))));
}

/* =========================================================================
   5. LE MOT DU CHEF DE SERVICE
   ========================================================================= */

/**
 * Le mot, extrait de communications.json.
 * Il est distinct des annonces : un fichier sans « motDuChef » n'est pas
 * une erreur, c'est un mot non publié — d'où un état vide, pas un échec.
 *
 * @param {object} donnees
 * @returns {object|null}
 */
function motDuChef(donnees) {
  if (!donnees || typeof donnees !== 'object') return null;
  const mot = donnees.motDuChef;
  if (!mot || typeof mot !== 'object') return null;
  if (!Array.isArray(mot.corps) || mot.corps.length === 0) return null;
  return mot;
}

/**
 * Une ligne du corps du mot. Les types sont explicites, exactement comme
 * pour le corps d'une annonce : aucun préfixe à interpréter.
 *
 * @param {*} ligne
 * @returns {Element|null}
 */
function ligneDuMot(ligne) {
  if (!ligne || typeof ligne !== 'object') return null;

  const texte = String(ligne.texte === null || ligne.texte === undefined
    ? '' : ligne.texte).trim();
  if (texte === '') return null;

  if (ligne.type === 'titre') return el('h4', { class: 'sans-marge' }, texte);
  return el('p', { class: 'sans-marge' }, texte);
}

/**
 * Rend le mot du chef de service dans son bloc dédié.
 * @param {object} mot
 * @param {Element} conteneur
 */
function rendreMot(mot, conteneur) {
  const paragraphes = mot.corps.map(ligneDuMot).filter(Boolean);

  const signature = el('p', { class: 'mot__signature sans-marge texte-sm' },
    el('span', { class: 'mot__auteur' }, String(mot.auteur || 'Le chef de service')));

  if (mot.fonction) {
    signature.append(el('span', { class: 'texte-doux' }, String(mot.fonction)));
  }
  if (mot.date) {
    signature.append(el('time', {
      class: 'texte-faible',
      datetime: String(mot.date)
    }, dateLongue(mot.date)));
  }

  monter(conteneur, el('article', { class: 'carte carte--ample mot' },
    el('div', { class: 'mot__entete' },
      el('h3', { class: 'carte__titre mot__titre' },
        String(mot.titre || 'Le mot du chef de service')),
      el('span', { class: 'badge badge--accent' }, 'Parole du service')),

    el('div', { class: 'mot__corps' },
      // Guillemet ouvrant : décoratif, donc masqué aux lecteurs d'écran.
      el('span', { class: 'mot__marque', 'aria-hidden': 'true' }, '«'),
      paragraphes),

    signature));
}

/* =========================================================================
   6. LA FLOTTE
   ========================================================================= */

/**
 * Rend le carrousel des appareils, suivi de l'avertissement du fichier.
 *
 * L'avertissement n'est pas décoratif : les désignations sont publiques,
 * le contexte de service ne l'est pas — il est fictif. Le texte vient du
 * champ « avertissement » de flotte.json, jamais d'une chaîne recopiée.
 *
 * @param {object} donnees contenu de flotte.json
 * @param {Element} conteneur
 */
function rendreFlotte(donnees, conteneur) {
  verifierForme(donnees, { flotte: 'tableau' }, 'flotte.json');

  const avertissement = typeof donnees.avertissement === 'string'
    ? donnees.avertissement.trim()
    : '';

  monter(conteneur, el('div', { class: 'pile' },
    exigerNoeud(carrousel(donnees.flotte, {
      etiquette: 'Flotte suivie par le service ETII'
    }), 'carrousel'),

    avertissement
      ? el('p', { class: 'flotte-note sans-marge' },
          el('span', { 'aria-hidden': 'true' }, '※'),
          el('span', null, avertissement))
      : null));
}

/* =========================================================================
   7. LE SUIVI OTQ / OTD
   ========================================================================= */

/*
   Le sélecteur d'indicateur pilote le graphique, le tableau et les barres.
   Son état voyage dans le hash (#indicateur=otd) pour que la vue soit
   partageable, exactement comme le pôle actif sur les pages transverses.
   La valeur par défaut — l'OTQ — n'est pas écrite : l'URL reste nue.
*/
let appliquerIndicateur = null;

/** Lit l'indicateur demandé par l'URL ('' si rien ou illisible). */
function indicateurDemande() {
  const etat = etatUrl.lire();
  return typeof etat.indicateur === 'string' ? etat.indicateur.toLowerCase() : '';
}

/**
 * Construit la zone complète des indicateurs : quatre tuiles, le suivi
 * mensuel par pôle avec son sélecteur, puis la comparaison des pôles.
 *
 * @param {object} donnees contenu de indicateurs.json
 * @param {Element} conteneur
 */
function rendreIndicateurs(donnees, conteneur) {
  verifierForme(donnees, {
    periode: 'objet',
    definitions: 'objet',
    poles: 'objet',
    service: 'objet'
  }, 'indicateurs.json');

  const mois = moisDe(donnees);
  if (mois.length === 0) {
    throw new Error('« indicateurs.json » : la période ne contient aucun mois.');
  }
  const dernier = mois.length - 1;

  /* Pôles réellement mesurés, dans l'ordre de l'accord d'équipe. */
  const polesMesures = POLES.filter(
    (pole) => donnees.poles[pole.cle] && typeof donnees.poles[pole.cle] === 'object');

  /* Indicateurs exploitables : définis ET suivis au niveau du service. */
  const cles = ORDRE_INDICATEURS.filter((cle) =>
    donnees.definitions[cle] && serieDe(donnees.service, cle, mois.length));

  if (cles.length === 0) {
    throw new Error(
      '« indicateurs.json » : aucun indicateur ne couvre la période '
      + 'annoncée — les séries et la liste des mois ne concordent pas.'
    );
  }

  /**
   * L'indicateur est-il une SOMME des pôles plutôt qu'une moyenne ?
   * Le test porte sur la donnée, pas sur le nom : un total d'écarts se
   * reconnaît à ce que le service vaut la somme des trois pôles. La cible
   * du service s'en déduit — sinon, comparer 26 écarts à une cible de 12
   * établie par pôle n'aurait aucun sens.
   *
   * @param {string} cle
   * @returns {boolean}
   */
  function estSomme(cle) {
    const service = serieDe(donnees.service, cle, mois.length);
    if (!service || polesMesures.length < 2) return false;

    let total = 0;
    for (const pole of polesMesures) {
      const serie = serieDe(donnees.poles[pole.cle], cle, mois.length);
      if (!serie) return false;
      total += Number(serie[dernier]) || 0;
    }
    return Math.abs(total - Number(service[dernier])) < 0.5;
  }

  /**
   * Définition d'un indicateur AU NIVEAU DU SERVICE.
   *
   * Pour un indicateur sommé, la cible du fichier est établie par pôle :
   * l'appliquer telle quelle au total du service ferait dire n'importe
   * quoi à la tuile. On la multiplie donc par le nombre de pôles, et on le
   * dit dans le texte d'aide. Pour tous les autres, la définition est
   * reprise sans y toucher.
   *
   * @param {string} cle
   * @returns {object}
   */
  function definitionService(cle) {
    const def = donnees.definitions[cle];
    if (!estSomme(cle) || typeof def.cible !== 'number') return def;

    return Object.assign({}, def, {
      cible: def.cible * polesMesures.length,
      aide: def.aide + ' Total des ' + polesMesures.length
        + ' pôles : la cible de ' + formaterValeur(def.cible, def.unite)
        + ' s’entend par pôle.'
    });
  }

  /* --- 7.1 La ligne de tuiles -----------------------------------------
     Quatre tuiles, l'OTQ en tête. Elles mesurent le SERVICE : leur couleur
     de série est donc celle du niveau service, pas celle d'un pôle. */

  const tuiles = el('div', { class: 'grille grille--compacte' });

  for (const cle of cles) {
    tuiles.append(exigerNoeud(tuileIndicateur({
      cle: cle,
      definition: definitionService(cle),
      serie: donnees.service[cle],
      mois: mois,
      couleur: COULEUR_SERVICE
    }), 'tuileIndicateur'));
  }

  /* --- 7.2 Le sélecteur d'indicateur ---------------------------------- */

  const select = el('select', {
    class: 'champ__controle choix-indicateur',
    id: 'choix-indicateur',
    onChange: (evt) => changer(evt.target.value, true)
  }, cles.map((cle) => el('option', { value: cle },
    donnees.definitions[cle].libelle + ' — ' + donnees.definitions[cle].nom)));

  /* --- 7.3 Les réceptacles pilotés par le sélecteur ------------------- */

  const zoneGraphique = el('div');
  const zoneBarres = el('div');

  /**
   * Rejoue le graphique et les barres pour l'indicateur demandé.
   *
   * Le tableau de valeurs n'est pas construit ici : graphiqueLignes() et
   * barresComparees() intègrent déjà le leur, replié dans un `<details>`
   * sous la figure. En ajouter un second ferait doublon.
   *
   * @param {string} demande
   * @param {boolean} avecAnnonce annoncer le changement aux lecteurs d'écran
   */
  function appliquer(demande, avecAnnonce) {
    const cle = cles.includes(demande) ? demande : cles[0];
    const def = donnees.definitions[cle];

    if (select.value !== cle) select.value = cle;

    /* Une série par pôle. La couleur suit l'entité, jamais son rang, et
       chaque série porte son libellé : une courbe n'est jamais identifiée
       par la seule couleur. */
    const series = polesMesures
      .map((pole) => ({
        cle: pole.cle,
        libelle: pole.cle,
        couleur: pole.couleur,
        valeurs: serieDe(donnees.poles[pole.cle], cle, mois.length)
      }))
      .filter((serie) => serie.valeurs !== null);

    monter(zoneGraphique, exigerNoeud(graphiqueLignes({
      mois: mois,
      series: series,
      definition: def,
      titre: def.libelle + ' par pôle'
    }), 'graphiqueLignes'));

    monter(zoneBarres, exigerNoeud(barresComparees({
      categories: series.map((serie) => serie.libelle),
      valeurs: series.map((serie) => serie.valeurs[dernier]),
      couleurs: series.map((serie) => serie.couleur),
      definition: def,
      titre: def.libelle + ' par pôle en ' + libelleMois(mois[dernier], 'long')
    }), 'barresComparees'));

    if (avecAnnonce) annoncer('Indicateur affiché : ' + def.nom + '.');
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
      console.error('[index] ' + erreur.message, erreur);
      annoncer('L’indicateur demandé n’a pas pu être affiché.');
    }
  }

  /* --- 7.4 Assemblage -------------------------------------------------- */

  monter(conteneur,
    tuiles,

    el('section', { class: 'pile', 'aria-labelledby': 'titre-suivi' },
      el('div', { class: 'rangee rangee--entre' },
        el('h3', { class: 'sans-marge', id: 'titre-suivi' },
          'Suivi sur douze mois, par pôle'),
        el('div', { class: 'rangee rangee--serree suivi-choix' },
          el('label', { class: 'champ__etiquette', for: 'choix-indicateur' },
            'Indicateur affiché'),
          select)),
      zoneGraphique),

    el('section', { class: 'pile', 'aria-labelledby': 'titre-comparaison' },
      el('h3', { class: 'sans-marge', id: 'titre-comparaison' },
        'Comparaison des pôles'),
      zoneBarres));

  /* Le hash fait foi au premier rendu comme après un « Précédent ». */
  appliquerIndicateur = changer;
  changer(indicateurDemande(), false);
}

/* -------------------------------------------------------------------------
   7bis. Ligne d'état des données

   Deux informations, et pas une de plus : jusqu'où va la donnée, et quand
   elle a été lue. Le bouton relit le fichier — il n'interroge rien. La
   nuance est écrite noir sur blanc dans la page, sous cette ligne.

   Les nœuds sont créés UNE fois et seul leur texte change : le bouton
   « Actualiser » survit donc à ses propres rafraîchissements, et le focus
   ne saute nulle part.
   ------------------------------------------------------------------------- */

/** Texte variable de la ligne d'état. */
const majTexte = el('p', {
  class: 'maj__texte texte-sm texte-doux',
  role: 'status'
});

/** Libellé du bouton, remplacé pendant le chargement. */
const majLibelle = el('span', null, 'Actualiser');

/** Vrai pendant un rechargement : le bouton ne se déclenche pas deux fois. */
let majEnCours = false;

const majBouton = el('button', {
  type: 'button',
  class: 'bouton bouton--secondaire bouton--compact',
  onClick: actualiserIndicateurs
},
  el('span', { class: 'bouton__icone', 'aria-hidden': 'true' }, '⟳'),
  majLibelle);

/**
 * Reflète l'état du dernier cycle de chargement des indicateurs.
 * Branchée en `surEtat` de la zone : elle est donc rejouée à chaque
 * tentative, y compris après un « Réessayer » du bloc d'erreur.
 *
 * @param {{etat:string, donnees?:*, erreur?:Error}} [resultat]
 *        omis ou nul : le premier chargement n'a pas encore abouti.
 */
function refleterEtatDonnees(resultat) {
  if (!resultat) {
    monter(majTexte, 'Lecture du jeu de données en cours…');
    return;
  }

  const heure = heureDe(new Date());
  const horodatage = el('time', { datetime: heure.machine }, heure.affichage);

  if (resultat.etat !== 'succes') {
    monter(majTexte,
      'Jeu de données indisponible — dernière tentative à ', horodatage, '.');
    return;
  }

  const mois = moisDe(resultat.donnees);
  const dernier = mois.length ? mois[mois.length - 1] : '';

  monter(majTexte,
    'Instantané arrêté à ',
    dernier
      ? el('time', { datetime: String(dernier) }, libelleMois(dernier, 'long'))
      : el('span', null, 'une période non précisée'),
    ' · relu à ', horodatage, '.');
}

/**
 * Recharge réellement indicateurs.json.
 *
 * data.js mémoïse la PROMESSE : sans purge du cache, « Actualiser »
 * réafficherait la même réponse sans jamais toucher au fichier. On vide
 * donc l'entrée avant de relancer, puis on rejoue les deux zones qui
 * vivent de ce jeu — les indicateurs, et l'OTQ des cartes de pôle.
 */
async function actualiserIndicateurs() {
  if (majEnCours) return;

  /* `aria-disabled` plutôt que `disabled` : un bouton désactivé sous le
     doigt perd le focus au profit du corps du document, et le clavier se
     retrouve au début de la page. Ici le bouton reste focalisable, la
     garde ci-dessus suffit à ignorer un second clic. */
  majEnCours = true;
  majBouton.setAttribute('aria-disabled', 'true');
  majTexte.setAttribute('aria-busy', 'true');
  majLibelle.textContent = 'Actualisation…';

  try {
    viderCache('indicateurs');
    /* avecEtat() ne rejette jamais : les deux zones afficheront leur propre
       état, quoi qu'il arrive au fichier. Le résultat est annoncé par la
       ligne d'état elle-même (role="status") — en ajouter un second par
       annoncer() ferait parler le lecteur d'écran deux fois. */
    await Promise.all([lancerIndicateurs(), lancerPoles()]);
  } finally {
    majEnCours = false;
    majBouton.removeAttribute('aria-disabled');
    majTexte.setAttribute('aria-busy', 'false');
    majLibelle.textContent = 'Actualiser';
  }
}

/* =========================================================================
   8. LES ANNONCES DE SERVICE
   ========================================================================= */

/**
 * Annonces de NIVEAU SERVICE, les plus récentes d'abord.
 * Les annonces de pôle appartiennent à l'espace de leur pôle : elles n'ont
 * rien à faire sur la page du service.
 *
 * @param {object} donnees contenu de communications.json
 * @returns {object[]} deux annonces au plus
 */
function annoncesDeService(donnees) {
  verifierForme(donnees, { annonces: 'tableau' }, 'communications.json');

  return donnees.annonces
    .filter((annonce) => annonce && typeof annonce === 'object'
      && annonce.pole === 'ETII')
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
 * Lien vers l'annonce dans le Communication Center, pôle « ETII » actif.
 * Le paramètre d'annonce est un bonus : si la page cible ne le connaît pas,
 * le lien mène malgré tout à la bonne liste filtrée.
 *
 * @param {object} annonce
 * @returns {string}
 */
function lienAnnonce(annonce) {
  const base = 'communication.html#pole=ETII';
  return annonce.id ? base + '&annonce=' + encodeURIComponent(String(annonce.id)) : base;
}

/**
 * Carte d'aperçu d'une annonce.
 * @param {object} annonce
 * @returns {Element}
 */
function carteAnnonce(annonce) {
  const statut = STATUTS[annonce.statut] || { variante: 'neutre', libelle: 'Annonce' };
  const classeStatut = statut.variante === 'neutre'
    ? ''
    : ' carte--statut-' + statut.variante;

  return el('article', { class: 'carte carte--compacte carte--cliquable' + classeStatut },
    el('p', { class: 'carte__meta sans-marge' },
      annonce.date
        ? el('time', { datetime: String(annonce.date) }, dateLongue(annonce.date))
        : null,
      el('span', { class: 'badge badge--' + statut.variante }, statut.libelle),
      annonce.categorie
        ? el('span', { class: 'badge badge--neutre badge--contour' },
            String(annonce.categorie))
        : null),

    el('h3', { class: 'carte__titre' },
      el('a', { class: 'carte__lien', href: lienAnnonce(annonce) },
        String(annonce.titre || 'Annonce'))),

    annonce.resume
      ? el('p', { class: 'sans-marge texte-doux' }, String(annonce.resume))
      : null);
}

/**
 * Rend les annonces de service.
 * @param {object[]} annonces
 * @param {Element} conteneur
 */
function rendreCommunication(annonces, conteneur) {
  monter(conteneur, el('div', { class: 'pile' }, annonces.map(carteAnnonce)));
}

/* =========================================================================
   9. Démarrage — une section, un cycle d'état
   ========================================================================= */

initTheme();
initNav('index.html');

/* Retour arrière, avance, ou lien collé : le hash reste la source de
   vérité de l'indicateur affiché. L'écouteur est posé une seule fois, même
   si la zone est reconstruite par un « Réessayer » ou une actualisation. */
etatUrl.ecouter(() => {
  if (typeof appliquerIndicateur === 'function') {
    appliquerIndicateur(indicateurDemande(), true);
  }
});

/**
 * Le dispatcher. L'organigramme est indispensable (c'est lui qui donne
 * l'effectif) ; les indicateurs sont un bonus, leur échec est absorbé pour
 * que les trois cartes s'affichent quand même.
 *
 * @returns {Promise<object>}
 */
function lancerPoles() {
  return avecEtat('#zone-poles',
    () => Promise.all([
      chargerDonnees('organigramme'),
      chargerDonnees('indicateurs').catch(() => null)
    ]),
    rendrePoles, {
      squelette: 3,
      texteChargement: 'Chargement des pôles…',
      titreErreur: 'Pôles indisponibles',
      titreVide: 'Aucun pôle déclaré',
      texteVide: 'Les trois espaces de pôle apparaîtront ici dès que '
        + 'l’organigramme du service aura été publié.'
    });
}

/**
 * Le suivi OTQ / OTD. La ligne d'état est rejouée à chaque cycle.
 * @returns {Promise<object>}
 */
function lancerIndicateurs() {
  return avecEtat('#zone-indicateurs', () => chargerDonnees('indicateurs'),
    rendreIndicateurs, {
      squelette: 2,
      texteChargement: 'Chargement des indicateurs du service…',
      titreErreur: 'Indicateurs indisponibles',
      titreVide: 'Aucun indicateur publié',
      texteVide: 'Les indicateurs du service apparaîtront ici dès qu’une '
        + 'première période aura été publiée.',
      surEtat: refleterEtatDonnees
    });
}

/* 2 — Le dispatcher, tout en haut. */
lancerPoles();

/* 3 — Le mot du chef de service. */
avecEtat('#zone-mot',
  async () => motDuChef(await chargerDonnees('communications')),
  rendreMot, {
    squelette: 1,
    texteChargement: 'Chargement du mot du chef de service…',
    titreErreur: 'Mot du chef de service indisponible',
    titreVide: 'Aucun mot publié',
    texteVide: 'Le prochain mot du chef de service paraîtra ici. Les '
      + 'annonces, elles, restent en bas de page.'
  });

/* 4 — La flotte. */
avecEtat('#zone-flotte', () => chargerDonnees('flotte'), rendreFlotte, {
  squelette: 1,
  texteChargement: 'Chargement de la flotte…',
  titreErreur: 'Flotte indisponible',
  titreVide: 'Aucun appareil suivi',
  texteVide: 'Les appareils suivis par le service apparaîtront ici.',
  estVide: (donnees) => !donnees || !Array.isArray(donnees.flotte)
    || donnees.flotte.length === 0
});

/* 5 — Le suivi OTQ / OTD, et sa ligne d'état. */
monter(document.getElementById('zone-maj'),
  el('div', { class: 'maj' }, majTexte, majBouton));
refleterEtatDonnees();
lancerIndicateurs();

/* 6 — Les annonces de service, en fin de page. */
avecEtat('#zone-communication',
  async () => annoncesDeService(await chargerDonnees('communications')),
  rendreCommunication, {
    squelette: 2,
    compact: true,
    texteChargement: 'Chargement des annonces de service…',
    titreVide: 'Aucune annonce de service',
    titreErreur: 'Annonces indisponibles',
    texteVide: 'Les annonces publiées au niveau du service apparaîtront '
      + 'ici. Celles des pôles restent dans leur espace.'
  });
