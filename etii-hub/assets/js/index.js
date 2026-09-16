/* =========================================================================
   ETII Hub — La page du service ETII (index.html)

   La page ne porte que trois choses, dans cet ordre :

     1. L'AGENDA DU SERVICE — une frise chronologique unique, filtrable
        par pôle et par période, dont le mot du chef de service est
        l'entrée la plus importante.
     2. LA FLOTTE SUIVIE — rendue par grilleFlotte() de flotte.js, suivie
        de l'avertissement porté par le fichier.
     3. LE SUIVI OTQ / OTD — en attente de raccordement. Aucun graphique,
        aucune donnée d'exemple : un encadré qui dit exactement cela.

   Le choix du pôle et l'accès à la recherche documentaire sont dans la
   navigation du haut : la page ne les répète pas.

   RÈGLE TENUE D'UN BOUT À L'AUTRE : rien n'est inventé. Tout ce qui
   s'affiche vient des fichiers JSON. Un champ absent ou nul s'affiche
   « à renseigner », jamais comme une valeur plausible. Les seules valeurs
   calculées ici — le nombre de jours restants, les compteurs de facette —
   se déduisent de la donnée lue et de la date du jour, rien d'autre.

   Tout le DOM est construit avec el() / svg() / monter() : aucun
   innerHTML, aucun gestionnaire en attribut HTML, aucune valeur de style
   en dur — les seules propriétés posées sont des `--…` valant un jeton de
   tokens.css.

   Deux zones asynchrones, deux cycles d'état indépendants (data.js) :

     #zone-agenda   communications.json → agenda + motDuChef
     #zone-flotte   flotte.json

   La troisième zone, #zone-otq, ne charge rien : elle n'a pas de source.
   ========================================================================= */

import { el, svg, monter, etatUrl, initTheme, initNav } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { grilleFlotte } from './flotte.js';

/* -------------------------------------------------------------------------
   1. Constantes de la page
   ------------------------------------------------------------------------- */

/** Mention unique des champs déclarés mais vides. Jamais de substitut. */
const NON_RENSEIGNE = 'à renseigner';

const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

const JOUR_MS = 24 * 60 * 60 * 1000;

/*
   Les pôles connus du hub. Le libellé et la couleur sont de la matière
   d'interface, pas de la donnée : la couleur est un jeton de tokens.css, et
   elle n'est jamais le seul signal — le libellé l'accompagne toujours.
   Un code absent de cette table s'affiche tel que le fichier l'écrit.
*/
const POLES = {
  ETII:  { libelle: 'Service ETII', couleur: 'var(--pole-etii)' },
  ETIIA: { libelle: 'Pôle ETIIA',   couleur: 'var(--pole-etiia)' },
  ETIIE: { libelle: 'Pôle ETIIE',   couleur: 'var(--pole-etiie)' },
  ETIII: { libelle: 'Pôle ETIII',   couleur: 'var(--pole-etiii)' }
};

/*
   Types d'entrée reconnus. Chaque type a un libellé lisible ET une icône
   en trait : l'information n'est jamais portée par la seule couleur, ni
   par la seule forme. Un type inconnu garde son libellé brut et reçoit
   l'icône générique.
*/
const TYPES = {
  jalon:   'Jalon',
  atelier: 'Atelier',
  reunion: 'Réunion',
  mot:     'Mot du chef de service',
  succes:  'Succès',
  alerte:  'Alerte',
  info:    'Information'
};

/* Tracés des icônes de type, en trait seul, sur une grille de 24 × 24. */
const TRACES = {
  /* Un fanion sur sa hampe. */
  jalon: ['M6 3.2v17.6', 'M6 4.6h11.2l-2.6 3.5 2.6 3.5H6z'],
  /* Trois participants reliés autour d'une table. */
  atelier: [
    'M12 4.2a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8',
    'M6 14.4a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8',
    'M18 14.4a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8',
    'M10.4 8.3 7.6 14.4', 'M13.6 8.3l2.8 6.1', 'M8.4 16.8h7.2'
  ],
  /* Une bulle de dialogue. */
  reunion: ['M5 5h14v10h-8.6L6 18.6V15H5z', 'M8.4 8.6h7.2', 'M8.4 11.6h4.4'],
  /* Un porte-voix : une parole adressée au service, pas une brève. À
     cette taille, deux guillemets se lisaient « 99 » — la forme doit
     rester reconnaissable dans une pastille de deux centimètres. */
  mot: [
    'M4.6 10.2v3.6a1.4 1.4 0 0 0 1.4 1.4h2l7.6 3.8V5L8 8.8H6a1.4 1.4 0 0 0-1.4 1.4z',
    'M18.6 9.6a3.6 3.6 0 0 1 0 4.8',
    'M8 15.2v3.4a1.4 1.4 0 0 0 1.4 1.4h.6a1.4 1.4 0 0 0 1.4-1.4v-1.8'
  ],
  /* Une coche dans un cercle. */
  succes: ['M12 3.2a8.8 8.8 0 1 0 0 17.6 8.8 8.8 0 0 0 0-17.6',
           'M8.2 12.2l2.6 2.6 5-5.2'],
  /* Un triangle d'avertissement. */
  alerte: ['M12 4.2 20.8 19.4H3.2z', 'M12 10v4.2', 'M12 17.2h.01'],
  /* Un « i » dans un cercle. */
  info: ['M12 3.2a8.8 8.8 0 1 0 0 17.6 8.8 8.8 0 0 0 0-17.6',
         'M12 11.2v5', 'M12 7.8h.01'],
  /* Repli : un cercle et son centre. Il dit « type non reconnu », il ne
     fait pas semblant d'en désigner un. */
  defaut: ['M12 3.2a8.8 8.8 0 1 0 0 17.6 8.8 8.8 0 0 0 0-17.6', 'M12 12h.01'],
  /* Une fiche de raccordement, pour l'encadré d'attente. */
  branchement: ['M9 3v4.4', 'M15 3v4.4', 'M6.2 7.4h11.6v3.2a5.8 5.8 0 0 1-11.6 0z',
                'M12 16.4V21']
};

/** Valeur de facette signifiant « aucun filtre ». */
const TOUS = 'tous';

/** Les trois périodes proposées, dans l'ordre d'affichage. */
const PERIODES = [
  { id: 'tout',    libelle: 'Tout' },
  { id: 'a-venir', libelle: 'À venir' },
  { id: 'passee',  libelle: 'Passées' }
];

/* -------------------------------------------------------------------------
   2. Lecture tolérante
   ------------------------------------------------------------------------- */

/**
 * Chaîne lisible d'une valeur quelconque, ou '' si elle n'en est pas une.
 * Ne remplace jamais une valeur manquante par autre chose que du vide :
 * c'est l'affichage, plus bas, qui écrit « à renseigner ».
 *
 * @param {*} valeur
 * @returns {string}
 */
function txt(valeur) {
  return typeof valeur === 'string' ? valeur.trim() : '';
}

/**
 * Décompose une date ISO courte, sans passer par le fuseau local.
 * @param {*} brut  attendu : 'AAAA-MM-JJ'
 * @returns {{annee:number, mois:number, jour:number, utc:number}|null}
 */
function partiesDate(brut) {
  const m = txt(brut).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;

  const annee = Number(m[1]);
  const mois = Number(m[2]);
  const jour = Number(m[3]);
  if (mois < 1 || mois > 12 || jour < 1 || jour > 31) return null;

  return { annee, mois, jour, utc: Date.UTC(annee, mois - 1, jour) };
}

/**
 * Date en toutes lettres : « 8 octobre 2026 ». Chaîne vide si la date
 * n'est pas exploitable — l'appelant affiche alors « à renseigner ».
 *
 * @param {*} brut
 * @returns {string}
 */
function dateLongue(brut) {
  const p = partiesDate(brut);
  return p ? `${p.jour} ${MOIS_LONGS[p.mois - 1]} ${p.annee}` : '';
}

/** Minuit du jour courant, en UTC, pour comparer des dates sans heure. */
function aujourdhui() {
  const maintenant = new Date();
  return Date.UTC(maintenant.getFullYear(), maintenant.getMonth(),
    maintenant.getDate());
}

/**
 * Nombre de jours entiers séparant une date du jour courant.
 * Ce n'est pas une donnée inventée : c'est une soustraction entre la date
 * lue dans le fichier et la date d'aujourd'hui.
 *
 * @param {*} brut
 * @returns {number|null} positif pour l'avenir, null si la date est illisible
 */
function joursRestants(brut) {
  const p = partiesDate(brut);
  return p ? Math.round((p.utc - aujourdhui()) / JOUR_MS) : null;
}

/**
 * Libellé du délai restant.
 * @param {number|null} jours
 * @returns {string} '' si le délai n'est pas calculable
 */
function libelleDelai(jours) {
  if (jours === null) return '';
  if (jours > 1) return `dans ${jours} jours`;
  if (jours === 1) return 'dans 1 jour';
  if (jours === 0) return 'aujourd’hui';
  return 'échéance dépassée';
}

/**
 * Normalise une entrée d'agenda : rien n'est complété, tout est seulement
 * mis dans une forme sûre à manipuler.
 *
 * @param {*} brut
 * @param {number} rang
 * @returns {{id:string, date:string, statut:string, pole:string,
 *            type:string, titre:string, resume:string}}
 */
function normaliserEntree(brut, rang) {
  const source = (brut && typeof brut === 'object') ? brut : {};
  const statut = txt(source.statut).toLowerCase();

  return {
    id: txt(source.id) || `agenda-${rang}`,
    date: txt(source.date),
    /* Un statut non reconnu n'est pas redressé : il reste vide, et
       l'entrée n'est classée ni dans l'avenir ni dans le passé. */
    statut: (statut === 'a-venir' || statut === 'passee') ? statut : '',
    pole: txt(source.pole),
    type: txt(source.type).toLowerCase(),
    titre: txt(source.titre),
    resume: txt(source.resume)
  };
}

/**
 * Normalise le mot du chef de service. Les lignes de corps sans texte sont
 * écartées : ce sont des séparateurs, pas des paragraphes vides.
 *
 * @param {*} brut
 * @returns {{auteur:string, fonction:string, date:string, titre:string,
 *            corps:string[]}|null}
 */
function normaliserMot(brut) {
  if (!brut || typeof brut !== 'object') return null;

  const corps = Array.isArray(brut.corps)
    ? brut.corps
      .map((ligne) => (ligne && typeof ligne === 'object')
        ? txt(ligne.texte)
        : txt(ligne))
      .filter((ligne) => ligne !== '')
    : [];

  return {
    auteur: txt(brut.auteur),
    fonction: txt(brut.fonction),
    date: txt(brut.date),
    titre: txt(brut.titre),
    corps
  };
}

/**
 * Ordre d'affichage : un seul axe du temps, descendant. Les entrées sans
 * date exploitable ferment la marche — elles ne sont pas datées d'office.
 *
 * @param {object} a
 * @param {object} b
 * @returns {number}
 */
function parRecence(a, b) {
  const da = partiesDate(a.date);
  const db = partiesDate(b.date);

  if (da && db && da.utc !== db.utc) return db.utc - da.utc;
  if (da && !db) return -1;
  if (!da && db) return 1;

  /* Égalité départagée explicitement, jamais par l'ordre d'insertion. */
  return a.titre.localeCompare(b.titre, 'fr') || a.id.localeCompare(b.id, 'fr');
}

/* -------------------------------------------------------------------------
   3. Fragments d'affichage
   ------------------------------------------------------------------------- */

/**
 * Mention « à renseigner », avec le nom du champ pour les lecteurs
 * d'écran : « Pôle : à renseigner » est utile, « à renseigner » seul ne
 * l'est pas.
 *
 * @param {string} champ
 * @returns {HTMLElement}
 */
function champManquant(champ) {
  return el('span', { class: 'champ-manquant' },
    el('span', { class: 'visuellement-cache' }, `${champ} : `),
    NON_RENSEIGNE);
}

/**
 * Icône d'un type d'entrée, en trait seul, dans la couleur du texte.
 * Purement visuelle : le libellé du type est écrit juste à côté.
 *
 * @param {string} nom  clé de TRACES
 * @returns {SVGElement}
 */
function icone(nom) {
  const traces = TRACES[nom] || TRACES.defaut;

  return svg('svg', {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '1.6',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    focusable: 'false',
    'aria-hidden': 'true'
  }, traces.map((d) => svg('path', { d })));
}

/**
 * Pastille de pôle ÉTIQUETÉE : un point teinté, décoratif, et le libellé
 * qui porte réellement l'information (SPEC §1bis).
 *
 * @param {string} code  code du pôle tel qu'il est écrit dans le fichier
 * @returns {HTMLElement}
 */
function pastillePole(code) {
  const connu = POLES[code];

  return el('span', {
    class: 'badge badge--contour pastille-pole',
    style: connu ? { '--couleur-pole': connu.couleur } : null
  },
  el('span', { class: 'pastille-pole__point', 'aria-hidden': 'true' }),
  connu ? connu.libelle : code);
}

/* -------------------------------------------------------------------------
   4. La frise chronologique
   ------------------------------------------------------------------------- */

/**
 * Ligne de méta d'une entrée : date, délai restant, pôle, type.
 *
 * @param {object} entree
 * @param {boolean} avecDate  faux pour le mot du chef, dont la date est
 *                            portée par la signature
 * @returns {HTMLElement}
 */
function metaEntree(entree, avecDate) {
  const lisible = dateLongue(entree.date);
  const delai = entree.statut === 'a-venir'
    ? libelleDelai(joursRestants(entree.date))
    : '';

  const libelleType = TYPES[entree.type] || entree.type;

  return el('p', { class: 'chrono__meta sans-marge' },
    avecDate
      ? (lisible
        ? el('time', { datetime: entree.date }, lisible)
        : champManquant('Date'))
      : null,

    delai ? el('span', { class: 'chrono__delai' }, delai) : null,

    entree.pole ? pastillePole(entree.pole) : champManquant('Pôle'),

    libelleType
      ? el('span', { class: 'chrono__type' }, libelleType)
      : champManquant('Type'));
}

/**
 * Le mot du chef de service, tel qu'il paraît dans la frise : une carte à
 * part, une typographie plus grande, une attribution détachée.
 *
 * @param {object} entree  l'entrée d'agenda qui le porte
 * @param {object} mot     le bloc motDuChef normalisé
 * @returns {HTMLElement}
 */
function blocMot(entree, mot) {
  const titre = mot.titre || entree.titre;
  const lisible = dateLongue(mot.date);

  const signature = el('p', { class: 'mot__signature sans-marge' },
    mot.auteur
      ? el('span', { class: 'mot__auteur' }, mot.auteur)
      : champManquant('Auteur'),
    mot.fonction ? el('span', null, mot.fonction) : champManquant('Fonction'),
    lisible
      ? el('time', { datetime: mot.date }, lisible)
      : champManquant('Date'));

  /* Pas de guillemet décoratif ici : la pastille de la frise porte déjà
     l'icône de guillemets du type « mot », et deux fois le même signe à
     dix centimètres l'un de l'autre n'ajoute rien. */
  return el('div', { class: 'chrono__bloc mot' },
    metaEntree(entree, false),

    el('h3', { class: 'mot__titre' },
      titre || champManquant('Titre')),

    mot.corps.length
      ? el('div', { class: 'mot__corps' },
        mot.corps.map((ligne) => el('p', { class: 'sans-marge' }, ligne)))
      : el('p', { class: 'sans-marge' }, champManquant('Texte du mot')),

    signature);
}

/**
 * Une entrée ordinaire de la frise.
 *
 * @param {object} entree
 * @returns {HTMLElement}
 */
function blocEntree(entree) {
  return el('div', { class: 'chrono__bloc' },
    metaEntree(entree, true),

    el('h3', { class: 'chrono__titre' },
      entree.titre || champManquant('Titre')),

    entree.resume
      ? el('p', { class: 'chrono__resume sans-marge' }, entree.resume)
      : el('p', { class: 'sans-marge' }, champManquant('Résumé')));
}

/**
 * Ligne complète de la frise : le rail, la pastille de type, le contenu.
 *
 * @param {object} entree
 * @param {object|null} mot  motDuChef, s'il est porté par cette entrée
 * @returns {HTMLElement}
 */
function ligneChrono(entree, mot) {
  return el('li', {
    class: ['chrono__entree',
      entree.statut === 'a-venir' ? 'chrono__entree--a-venir' : null,
      mot ? 'chrono__entree--mot' : null],
    dataset: { statut: entree.statut || 'inconnu' }
  },
  el('span', { class: 'chrono__rail' },
    el('span', { class: 'chrono__puce' }, icone(entree.type))),

  el('div', { class: 'chrono__corps' },
    mot ? blocMot(entree, mot) : blocEntree(entree)));
}

/**
 * Le repère « aujourd'hui », posé entre l'avenir et le passé.
 * La date affichée est celle du poste qui consulte la page : c'est le seul
 * élément de la frise qui ne vienne pas d'un fichier, et il n'annonce rien
 * d'autre que la date du jour.
 *
 * @returns {HTMLElement}
 */
function ligneAujourdhui() {
  const maintenant = new Date();
  const iso = [
    String(maintenant.getFullYear()),
    String(maintenant.getMonth() + 1).padStart(2, '0'),
    String(maintenant.getDate()).padStart(2, '0')
  ].join('-');

  return el('li', { class: 'chrono__jour' },
    el('span', { class: 'chrono__rail' },
      el('span', { class: 'chrono__puce' },
        el('span', { class: 'chrono__point-jour', 'aria-hidden': 'true' }))),

    el('p', { class: 'separateur-titre chrono__jour-texte sans-marge' },
      el('span', null, 'Aujourd’hui'),
      el('time', { datetime: iso }, dateLongue(iso))));
}

/* -------------------------------------------------------------------------
   5. L'agenda : filtres et rendu
   ------------------------------------------------------------------------- */

/**
 * Une puce de facette, avec son compteur.
 *
 * Le compteur visible est doublé d'un texte pour les lecteurs d'écran :
 * « 3 » seul ne dit pas ce qu'il compte.
 *
 * @param {{id:string, libelle:string}} facette
 * @param {Map<string, object>} registre  reçoit les nœuds de la puce
 * @param {function(string): void} choisir
 * @returns {HTMLElement} l'élément de liste
 */
function puceFacette(facette, registre, choisir) {
  const compteur = el('span', { class: 'facette__compteur' }, '0');
  const detail = el('span', { class: 'visuellement-cache' }, '');

  const bouton = el('button', {
    class: 'facette',
    type: 'button',
    ariaPressed: 'false',
    dataset: { facette: facette.id },
    onClick: () => choisir(facette.id)
  },
  el('span', { class: 'facette__marque', 'aria-hidden': 'true' }, '✓'),
  el('span', null, facette.libelle),
  compteur,
  detail);

  registre.set(facette.id, { bouton, compteur, detail });

  return el('li', null, bouton);
}

/**
 * Groupe de facettes : un intitulé, puis les puces.
 *
 * @param {string} intitule
 * @param {string} id
 * @param {HTMLElement[]} puces
 * @returns {HTMLElement}
 */
function groupeFacettes(intitule, id, puces) {
  return el('div', {
    class: 'agenda-filtres__groupe',
    role: 'group',
    ariaLabelledby: id
  },
  el('p', { class: 'champ__etiquette sans-marge', id }, intitule),
  el('ul', { class: 'facettes' }, puces));
}

/*
   Les filtres de l'agenda voyagent dans le hash — #pole=ETIIA&periode=a-venir
   — pour que la vue soit partageable. L'agenda peut être reconstruit, après
   un « Réessayer » par exemple : c'est donc le module qui garde le lien vers
   la vue courante, et l'écouteur de hashchange n'est posé qu'une seule fois,
   au démarrage.
*/
let appliquerUrl = null;

/**
 * Construit l'agenda complet : les deux groupes de filtres, le résumé, et
 * la frise. Tout l'état vit dans cette fermeture ; rien n'est global.
 *
 * @param {object[]} entrees  entrées normalisées, déjà triées
 * @param {object|null} mot   motDuChef normalisé
 * @returns {HTMLElement}
 */
function construireAgenda(entrees, mot) {
  /* --- Facettes de pôle : relevées sur la donnée, dans l'ordre du hub --- */
  const codes = [];
  for (const entree of entrees) {
    if (entree.pole && !codes.includes(entree.pole)) codes.push(entree.pole);
  }
  const ordre = Object.keys(POLES);
  codes.sort((a, b) => {
    const ia = ordre.indexOf(a);
    const ib = ordre.indexOf(b);
    if (ia !== ib) return (ia < 0 ? ordre.length : ia) - (ib < 0 ? ordre.length : ib);
    return a.localeCompare(b, 'fr');
  });

  const facettesPole = [{ id: TOUS, libelle: 'Tous' }].concat(
    codes.map((code) => ({ id: code, libelle: code })));

  /* --- État, restauré depuis l'URL ------------------------------------- */
  let poleActif = TOUS;
  let periodeActive = 'tout';

  const registrePole = new Map();
  const registrePeriode = new Map();

  const zoneListe = el('div');
  const resume = el('p', { class: 'agenda-resume sans-marge', role: 'status' });

  /** L'entrée correspond-elle au pôle demandé ? */
  const selonPole = (entree, pole) => pole === TOUS || entree.pole === pole;

  /** L'entrée correspond-elle à la période demandée ? */
  const selonPeriode = (entree, periode) =>
    periode === 'tout' || entree.statut === periode;

  /** Le mot du chef est-il porté par cette entrée ? */
  const motDe = (entree) =>
    (mot && entree.type === 'mot' && mot.date === entree.date) ? mot : null;

  /**
   * Écrit l'état courant dans le hash, pour que la vue soit partageable.
   * Les valeurs par défaut ne sont pas écrites : l'URL reste nue.
   */
  function refleterUrl() {
    etatUrl.ecrire({
      pole: poleActif === TOUS ? '' : poleActif,
      periode: periodeActive === 'tout' ? '' : periodeActive
    });
  }

  /**
   * Applique l'état lu dans l'URL. Une valeur inconnue est ignorée sans
   * erreur : le filtre correspondant retombe sur sa valeur par défaut.
   *
   * @returns {boolean} vrai si quelque chose a changé
   */
  function lireUrl() {
    const etat = etatUrl.lire();

    const pole = typeof etat.pole === 'string' ? etat.pole : '';
    const periode = typeof etat.periode === 'string' ? etat.periode : '';

    const nouveauPole = facettesPole.some((f) => f.id === pole) ? pole : TOUS;
    const nouvellePeriode = PERIODES.some((p) => p.id === periode)
      ? periode : 'tout';

    if (nouveauPole === poleActif && nouvellePeriode === periodeActive) {
      return false;
    }
    poleActif = nouveauPole;
    periodeActive = nouvellePeriode;
    return true;
  }

  /**
   * Met à jour les compteurs des deux groupes de facettes.
   *
   * Chaque compteur est relevé sur la donnée réelle, en tenant compte de
   * l'AUTRE filtre : le nombre annoncé est donc exactement le nombre
   * d'entrées qu'un clic ferait apparaître.
   */
  function majCompteurs() {
    for (const facette of facettesPole) {
      const n = entrees.filter((e) =>
        selonPole(e, facette.id) && selonPeriode(e, periodeActive)).length;
      const cible = registrePole.get(facette.id);
      cible.compteur.textContent = String(n);
      cible.detail.textContent = ` (${n} ${n <= 1 ? 'entrée' : 'entrées'})`;
    }

    for (const periode of PERIODES) {
      const n = entrees.filter((e) =>
        selonPole(e, poleActif) && selonPeriode(e, periode.id)).length;
      const cible = registrePeriode.get(periode.id);
      cible.compteur.textContent = String(n);
      cible.detail.textContent = ` (${n} ${n <= 1 ? 'entrée' : 'entrées'})`;
    }
  }

  /** Remet les deux filtres à leur valeur par défaut. */
  function reinitialiser() {
    poleActif = TOUS;
    periodeActive = 'tout';
    rendre();
  }

  /** État vide : les filtres ne laissent rien passer. */
  function etatVide() {
    return el('div', { class: 'etat-vide etat-vide--compact' },
      el('p', { class: 'etat-vide__titre' }, 'Aucune entrée'),
      el('p', { class: 'etat-vide__texte' },
        'Aucune entrée de l’agenda ne correspond aux filtres actifs.'),
      el('div', { class: 'etat-vide__actions' },
        el('button', {
          class: 'bouton bouton--secondaire',
          type: 'button',
          onClick: reinitialiser
        }, 'Réinitialiser les filtres')));
  }

  /**
   * Reconstruit la frise et tout ce qui en dépend.
   *
   * L'ordre est celui d'un axe du temps unique et descendant : les
   * échéances à venir d'abord, de la plus lointaine à la plus proche, le
   * repère du jour, puis le passé du plus récent au plus ancien. Les
   * entrées dont le statut n'est pas renseigné ferment la frise, sans être
   * rangées d'office d'un côté ou de l'autre.
   */
  function rendre() {
    const visibles = entrees.filter((e) =>
      selonPole(e, poleActif) && selonPeriode(e, periodeActive));

    const aVenir = visibles.filter((e) => e.statut === 'a-venir');
    const passees = visibles.filter((e) => e.statut === 'passee');
    const indecises = visibles.filter((e) => e.statut === '');

    const lignes = [];
    /* Les à-venir sont triées par récence décroissante comme le reste :
       l'échéance la plus lointaine ouvre la frise, la plus proche touche
       le repère du jour. */
    for (const entree of aVenir) lignes.push(ligneChrono(entree, motDe(entree)));
    if (aVenir.length && passees.length) lignes.push(ligneAujourdhui());
    for (const entree of passees) lignes.push(ligneChrono(entree, motDe(entree)));
    for (const entree of indecises) lignes.push(ligneChrono(entree, motDe(entree)));

    monter(zoneListe, lignes.length
      ? el('ol', {
        class: 'chrono',
        ariaLabel: 'Frise chronologique de l’agenda du service'
      }, lignes)
      : etatVide());

    for (const [cle, noeuds] of registrePole) {
      noeuds.bouton.setAttribute('aria-pressed',
        cle === poleActif ? 'true' : 'false');
    }
    for (const [cle, noeuds] of registrePeriode) {
      noeuds.bouton.setAttribute('aria-pressed',
        cle === periodeActive ? 'true' : 'false');
    }

    majCompteurs();

    const nomPole = poleActif === TOUS
      ? 'tous les pôles'
      : (POLES[poleActif] ? POLES[poleActif].libelle : poleActif);
    const nomPeriode = (PERIODES.find((p) => p.id === periodeActive) || {})
      .libelle || 'Tout';

    const accord = visibles.length <= 1 ? 'entrée affichée' : 'entrées affichées';
    resume.textContent =
      `${visibles.length} ${accord} — ${nomPole}, ${nomPeriode.toLowerCase()}.`;

    refleterUrl();
  }

  /* --- Puces ------------------------------------------------------------ */
  const pucesPole = facettesPole.map((facette) =>
    puceFacette(facette, registrePole, (id) => {
      if (poleActif === id) return;
      poleActif = id;
      rendre();
    }));

  const pucesPeriode = PERIODES.map((periode) =>
    puceFacette(periode, registrePeriode, (id) => {
      if (periodeActive === id) return;
      periodeActive = id;
      rendre();
    }));

  const filtres = el('div', { class: 'agenda-filtres' },
    groupeFacettes('Pôle', 'agenda-filtre-pole', pucesPole),
    groupeFacettes('Période', 'agenda-filtre-periode', pucesPeriode));

  /* La navigation par l'historique est relayée au module : l'écouteur de
     hashchange, lui, est posé une seule fois au démarrage. */
  appliquerUrl = () => {
    if (lireUrl()) rendre();
  };

  lireUrl();
  rendre();

  return el('div', { class: 'pile' }, filtres, resume, zoneListe);
}

/**
 * Rend l'agenda du service à partir de communications.json.
 *
 * @param {object} donnees
 * @param {Element} conteneur
 */
function rendreAgenda(donnees, conteneur) {
  verifierForme(donnees, { agenda: 'tableau', motDuChef: 'objet?' },
    'communications.json');

  const entrees = donnees.agenda.map(normaliserEntree).sort(parRecence);
  const mot = normaliserMot(donnees.motDuChef);

  monter(conteneur, construireAgenda(entrees, mot));
}

/* -------------------------------------------------------------------------
   6. La flotte suivie
   ------------------------------------------------------------------------- */

/**
 * Rend la grille des appareils, suivie de l'avertissement du fichier.
 *
 * L'avertissement n'est pas décoratif : les désignations sont publiques, le
 * contexte de service ne l'est pas — il est fictif. Le texte vient du champ
 * « avertissement » de flotte.json, jamais d'une chaîne recopiée ici.
 *
 * @param {object} donnees contenu de flotte.json
 * @param {Element} conteneur
 */
function rendreFlotte(donnees, conteneur) {
  verifierForme(donnees, { flotte: 'tableau' }, 'flotte.json');

  const grille = grilleFlotte(donnees, {
    etiquette: 'Filtrer la flotte par catégorie',
    niveauTitre: 3
  });

  if (!grille || grille.nodeType !== 1) {
    throw new Error('La grille de la flotte n’a pas pu être construite.');
  }

  const avertissement = txt(donnees.avertissement);

  monter(conteneur, el('div', { class: 'pile' },
    grille,
    avertissement
      ? el('p', { class: 'flotte-note sans-marge' },
        el('span', { 'aria-hidden': 'true' }, '※'),
        el('span', null, avertissement))
      : null));
}

/* -------------------------------------------------------------------------
   7. Le suivi OTQ / OTD — en attente de raccordement
   ------------------------------------------------------------------------- */

/**
 * POINT DE RACCORDEMENT UNIQUE du suivi OTQ / OTD.
 *
 * Le graphe d'origine de cette section interrogeait une source en direct du
 * service, dont le code n'a pas été fourni au projet. Tant que ce code
 * manque, la page n'affiche NI graphique, NI valeur, NI indicateur : aucune
 * donnée d'exemple ne doit pouvoir être prise pour une mesure du service.
 *
 * C'est ici, et nulle part ailleurs, que le raccordement se fera : cette
 * fonction est le seul endroit à modifier. Elle devra alors renvoyer les
 * données de la source — ou une promesse — et rendreSuiviOTQ() sera le seul
 * autre endroit à compléter, pour les afficher.
 *
 * @returns {null} toujours null tant que la source n'est pas fournie
 */
function chargerSuiviOTQ() {
  return null;
}

/** Encadré d'attente : il dit ce qu'il en est, et rien de plus. */
function encadreAttente() {
  return el('div', { class: 'attente' },
    el('span', { class: 'attente__icone', 'aria-hidden': 'true' },
      icone('branchement')),

    el('div', { class: 'attente__texte' },
      el('p', { class: 'attente__titre sans-marge' },
        'En attente du raccordement à la source du service'),

      el('p', { class: 'texte-doux sans-marge' },
        'Le suivi OTQ / OTD était alimenté par une source interrogée en '
        + 'direct, dont le code n’a pas encore été fourni. La section reste '
        + 'donc vide : aucun graphique, aucune valeur et aucun indicateur '
        + 'ne sont affichés ici, pour qu’aucun chiffre d’exemple ne puisse '
        + 'être pris pour une mesure du service.'),

      el('p', { class: 'texte-doux texte-sm sans-marge' },
        'Le branchement se fera en un seul point : la fonction ',
        el('span', { class: 'mono' }, 'chargerSuiviOTQ()'),
        ' de ',
        el('span', { class: 'mono' }, 'assets/js/index.js'),
        ', qui renvoie null aujourd’hui.')));
}

/**
 * Rend la section du suivi OTQ / OTD.
 *
 * @param {Element} conteneur
 */
function rendreSuiviOTQ(conteneur) {
  if (!conteneur) return;

  const suivi = chargerSuiviOTQ();

  /* Le jour où la source sera branchée, `suivi` cessera d'être nul et
     l'affichage viendra se construire ICI, à partir de lui seul. Tant que
     cet affichage n'est pas écrit, la section continue d'annoncer son
     attente : une vue à moitié vraie serait pire que pas de vue du tout. */
  if (suivi !== null) {
    console.info('[index] Source de suivi OTQ / OTD fournie : '
      + 'le rendu de la section reste à écrire.');
  }

  monter(conteneur, encadreAttente());
}

/* =========================================================================
   8. Démarrage — une section, un cycle d'état
   ========================================================================= */

initTheme();
initNav('index.html');

/* Retour arrière, avance, ou lien collé : le hash reste la source de vérité
   des filtres de l'agenda. L'écouteur est posé une seule fois, même si
   l'agenda est reconstruit par un « Réessayer ». */
etatUrl.ecouter(() => {
  if (typeof appliquerUrl === 'function') appliquerUrl();
});

/* 1 — L'agenda du service. */
avecEtat('#zone-agenda', () => chargerDonnees('communications'), rendreAgenda, {
  squelette: 3,
  texteChargement: 'Chargement de l’agenda du service…',
  titreErreur: 'Agenda indisponible',
  titreVide: 'Aucune entrée à l’agenda',
  texteVide: 'Les points du service, les jalons et le mot du chef de '
    + 'service apparaîtront ici dès qu’ils auront été publiés.',
  estVide: (donnees) => !donnees
    || (!Array.isArray(donnees.agenda) || donnees.agenda.length === 0)
});

/* 2 — La flotte suivie. */
avecEtat('#zone-flotte', () => chargerDonnees('flotte'), rendreFlotte, {
  squelette: 2,
  texteChargement: 'Chargement de la flotte…',
  titreErreur: 'Flotte indisponible',
  titreVide: 'Aucun appareil suivi',
  texteVide: 'Les appareils suivis par le service apparaîtront ici.',
  estVide: (donnees) => !donnees || !Array.isArray(donnees.flotte)
    || donnees.flotte.length === 0
});

/* 3 — Le suivi OTQ / OTD. Aucune source : aucun cycle de chargement. */
rendreSuiviOTQ(document.getElementById('zone-otq'));
