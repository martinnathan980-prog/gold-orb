/* =========================================================================
   ETII Hub — Moteur de recherche (SPEC.md §5)

   Module ES autonome, sans aucune dépendance. Réutilisé par la recherche
   documentaire, la FAQ et les réunions.

   API publique :
     normaliser(texte)                 -> string
     creerIndex(documents, champs)     -> index opaque
     rechercher(index, requete, opts)  -> [{ doc, score, champsTouches }]
     surligner(texte, requete)         -> [{ texte, correspond }]
     suggerer(index, requete)          -> string | null

   Principes de conception :
   - Tout est indexé en une seule passe au chargement (index inversé,
     index de préfixes, index de bigrammes) ; une requête ne parcourt
     jamais le corpus entier, elle part des listes d'affichage (postings)
     et ne score que les documents candidats.
   - Les dictionnaires chauds sont des Map, jamais des objets indexés par
     clé de texte : pas de collision avec la chaîne de prototypes, insertions
     et lectures en temps constant. Les ensembles de champs, eux, sont des
     masques de bits entiers : un champ = un bit, aucun conteneur alloué par
     paire (terme, document) ni par document candidat.
   - Le classement est totalement déterministe : deux appels identiques
     renvoient exactement le même ordre, l'ordre d'insertion n'est jamais
     un critère.
   - surligner() ne produit jamais de HTML : elle renvoie des segments de
     texte brut, l'appelant fabrique les nœuds DOM. C'est la garantie
     anti-XSS du projet.
   ========================================================================= */

/* -------------------------------------------------------------------------
   Constantes de réglage du moteur
   ------------------------------------------------------------------------- */

/** Marqueur interne permettant de reconnaître un index produit ici. */
const MARQUEUR_INDEX = 'etii-index-v1';

/** Longueur maximale des clés de l'index de préfixes (borne la mémoire). */
const PREFIXE_MAX = 10;

/*
   Plafond d'une expansion par préfixe. Il porte sur le VOLUME d'entrées de
   postings parcourues, jamais sur le nombre de termes : c'est le volume qui
   fait le coût d'une frappe, et un plafond en nombre de termes laisse passer
   les listes les plus longues tout en écartant des documents pertinents.
*/
const BUDGET_PREFIXE_POSTINGS = 2000;

/** Nombre maximal de termes retenus lors d'une expansion approximative. */
const EXPANSION_APPROX_MAX = 16;

/** En dessous de cette longueur, aucune tolérance aux fautes (trop de bruit). */
const LONGUEUR_MIN_APPROX = 4;

/** Fraction du poids plein accordée à une correspondance par préfixe. */
const POIDS_PREFIXE = 0.6;

/** Part fixe / part proportionnelle dans le facteur de préfixe. */
const PREFIXE_PART_FIXE = 0.4;

/** Fraction du poids plein accordée à une correspondance approximative. */
const POIDS_APPROX = 0.22;

/** Répétition d'un terme dans un même champ : bonus léger et plafonné. */
const FACTEUR_REPETITION = 0.15;
const MAX_REPETITION = 3;

/** Bonus multiplicatif quand TOUS les termes de la requête sont trouvés. */
const BONUS_TOUS_TERMES = 1.6;

/** Bonus multiplicatif quand la requête est un préfixe du titre. */
const BONUS_TITRE_PREFIXE = 1.3;

/** Bonus multiplicatif quand la requête est exactement le titre. */
const BONUS_TITRE_EXACT = 1.8;

/** Précision de l'arrondi des scores (stabilité du tri en virgule flottante). */
const PRECISION_SCORE = 1e6;

/* -------------------------------------------------------------------------
   1. Normalisation
   ------------------------------------------------------------------------- */

/*
   Les propriétés Unicode (\p{L}, \p{M}) sont disponibles partout depuis
   ES2018 ; on prévoit néanmoins un repli ASCII pour ne jamais casser à
   l'évaluation du module.
*/
let REGEX_MARQUES;
let REGEX_NON_MOT;
try {
  REGEX_MARQUES = new RegExp('\\p{M}', 'gu');
  REGEX_NON_MOT = new RegExp('[^\\p{L}\\p{N}]+', 'gu');
} catch (_e) {
  REGEX_MARQUES = /[̀-ͯ]/g;
  REGEX_NON_MOT = /[^a-z0-9]+/g;
}

/** Ligatures et lettres barrées que NFD ne décompose pas. */
const LIGATURES = new Map([
  ['œ', 'oe'], ['æ', 'ae'], ['ß', 'ss'],
  ['ø', 'o'], ['ł', 'l'], ['đ', 'd'], ['ð', 'd'], ['þ', 'th']
]);
const REGEX_LIGATURES = /[œæßøłđðþ]/g;

/**
 * Normalise un fragment de texte : minuscules, ligatures développées,
 * diacritiques retirés (NFD + suppression des marques combinantes),
 * ponctuation transformée en espace.
 * Ne compacte PAS les espaces : utilisée telle quelle par le surlignage,
 * qui a besoin d'une correspondance caractère par caractère.
 */
function normaliserFragment(fragment) {
  let s = fragment.toLowerCase();
  if (REGEX_LIGATURES.test(s)) {
    REGEX_LIGATURES.lastIndex = 0;
    s = s.replace(REGEX_LIGATURES, (c) => LIGATURES.get(c) || c);
  }
  REGEX_LIGATURES.lastIndex = 0;
  s = s.normalize('NFD').replace(REGEX_MARQUES, '');
  return s.replace(REGEX_NON_MOT, ' ');
}

/**
 * Normalise un texte complet.
 * « Intégration » et « integration » deviennent strictement identiques.
 * Tolère n'importe quelle entrée : renvoie '' si ce n'est pas exploitable.
 *
 * @param {*} texte
 * @returns {string}
 */
export function normaliser(texte) {
  if (typeof texte !== 'string') {
    if (typeof texte === 'number' && Number.isFinite(texte)) texte = String(texte);
    else return '';
  }
  if (texte === '') return '';
  return normaliserFragment(texte).replace(/\s+/g, ' ').trim();
}

/** Découpe une chaîne DÉJÀ normalisée en termes. */
function decouper(normalise) {
  if (!normalise) return [];
  return normalise.split(' ').filter(Boolean);
}

/** Convertit une valeur de champ en texte indexable (chaîne ou tableau). */
function valeurSimple(valeur) {
  if (typeof valeur === 'string') return valeur;
  if (typeof valeur === 'number' && Number.isFinite(valeur)) return String(valeur);
  return '';
}

/* -------------------------------------------------------------------------
   2. Distance d'édition bornée (Levenshtein)
   ------------------------------------------------------------------------- */

/*
   Deux tampons réutilisés d'un appel à l'autre : aucune matrice complète,
   aucune allocation dans la boucle chaude. Le calcul est mono-thread et
   non réentrant, la réutilisation est donc sûre.
*/
let tamponA = new Int32Array(64);
let tamponB = new Int32Array(64);

function assurerTampons(taille) {
  if (tamponA.length < taille) {
    let n = tamponA.length;
    while (n < taille) n *= 2;
    tamponA = new Int32Array(n);
    tamponB = new Int32Array(n);
  }
}

/**
 * Distance de Levenshtein bornée, avec sortie anticipée : dès que la
 * distance minimale encore atteignable dépasse le seuil, on abandonne et
 * on renvoie seuil + 1. Seule une bande de largeur 2·seuil + 1 est
 * calculée autour de la diagonale.
 *
 * @returns {number} la distance si elle est <= seuil, sinon seuil + 1.
 */
function distanceBornee(a, b, seuil) {
  if (a === b) return 0;
  if (seuil <= 0) return 1;

  // On travaille avec la chaîne la plus courte en ligne : bande plus étroite.
  if (a.length > b.length) { const t = a; a = b; b = t; }
  const la = a.length;
  const lb = b.length;

  const INATTEIGNABLE = seuil + 1;
  if (lb - la > seuil) return INATTEIGNABLE;  // écart de longueur rédhibitoire
  if (la === 0) return lb <= seuil ? lb : INATTEIGNABLE;

  assurerTampons(lb + 2);
  let precedente = tamponA;
  let courante = tamponB;

  for (let j = 0; j <= lb; j++) precedente[j] = j;

  for (let i = 1; i <= la; i++) {
    const debut = Math.max(1, i - seuil);
    const fin = Math.min(lb, i + seuil);

    // Bords de la bande : ce qui est hors bande est inatteignable.
    if (debut > 1) courante[debut - 1] = INATTEIGNABLE;
    else courante[0] = i;

    const codeA = a.charCodeAt(i - 1);
    let minLigne = INATTEIGNABLE;

    for (let j = debut; j <= fin; j++) {
      const cout = codeA === b.charCodeAt(j - 1) ? 0 : 1;
      let v = precedente[j - 1] + cout;          // substitution / égalité
      const suppression = precedente[j] + 1;     // suppression
      const insertion = courante[j - 1] + 1;     // insertion
      if (suppression < v) v = suppression;
      if (insertion < v) v = insertion;
      courante[j] = v;
      if (v < minLigne) minLigne = v;
    }

    if (fin < lb) courante[fin + 1] = INATTEIGNABLE;
    if (minLigne > seuil) return INATTEIGNABLE;  // sortie anticipée

    const echange = precedente; precedente = courante; courante = echange;
  }

  const d = precedente[lb];
  return d <= seuil ? d : INATTEIGNABLE;
}

/**
 * Seuil de tolérance aux fautes selon la longueur du terme (SPEC §5) :
 * aucune tolérance en dessous de 4 caractères, 1 de 4 à 7, 2 au-delà.
 */
function seuilEdition(terme) {
  const n = terme.length;
  if (n < LONGUEUR_MIN_APPROX) return 0;
  if (n <= 7) return 1;
  return 2;
}

/* -------------------------------------------------------------------------
   3. Construction de l'index
   ------------------------------------------------------------------------- */

/** Enregistre tous les préfixes utiles d'un terme (frappe au fil de l'eau). */
function enregistrerPrefixes(index, terme) {
  const max = Math.min(terme.length, PREFIXE_MAX);
  for (let l = 1; l <= max; l++) {
    const cle = terme.slice(0, l);
    let ensemble = index.prefixes.get(cle);
    if (!ensemble) { ensemble = new Set(); index.prefixes.set(cle, ensemble); }
    ensemble.add(terme);
  }
}

/** Enregistre les bigrammes de caractères d'un terme (tolérance aux fautes). */
function enregistrerBigrammes(index, terme) {
  for (let i = 0; i + 1 < terme.length; i++) {
    const bg = terme.slice(i, i + 2);
    let ensemble = index.bigrammes.get(bg);
    if (!ensemble) { ensemble = new Set(); index.bigrammes.set(bg, ensemble); }
    ensemble.add(terme);
  }
}

/** Bigrammes d'un terme de requête. */
function bigrammesDe(terme) {
  const sortie = [];
  for (let i = 0; i + 1 < terme.length; i++) sortie.push(terme.slice(i, i + 2));
  return sortie;
}

/** Indexe un champ d'un document (chaîne ou tableau de chaînes). */
function indexerChamp(index, id, doc, champ) {
  const brut = doc[champ.nom];
  if (brut === undefined || brut === null) return;   // champ absent : on ignore
  const morceaux = Array.isArray(brut) ? brut : [brut];

  // Comptage des occurrences du terme dans ce champ.
  const occurrences = new Map();
  for (const morceau of morceaux) {
    const texte = valeurSimple(morceau);
    if (!texte) continue;
    for (const terme of decouper(normaliser(texte))) {
      occurrences.set(terme, (occurrences.get(terme) || 0) + 1);
    }
  }

  for (const [terme, n] of occurrences) {
    // Répétition : bonus léger et plafonné, jamais une explosion de score.
    const poids = champ.poids
      * (1 + FACTEUR_REPETITION * Math.min(n - 1, MAX_REPETITION));

    let postings = index.inverse.get(terme);
    if (!postings) {
      postings = new Map();
      index.inverse.set(terme, postings);
      enregistrerPrefixes(index, terme);
      enregistrerBigrammes(index, terme);
    }
    // Une seule entrée par paire (terme, document) : le poids cumulé et le
    // masque des champs touchés. Pas de Set de noms de champs, pas d'index
    // parallèle — c'était l'essentiel du coût de construction et de la
    // pression mémoire.
    let entree = postings.get(id);
    if (!entree) { entree = { poids: 0, champs: 0 }; postings.set(id, entree); }
    entree.poids += poids;
    entree.champs |= champ.bit;
  }
}

/**
 * Construit l'index de recherche en une seule passe.
 *
 * @param {Array<object>} documents  objets possédant au minimum { id }
 * @param {Array<{nom:string, poids:number}>} champs  champs à indexer.
 *        Le champ de poids le plus fort fait office de « titre » : c'est
 *        lui qui porte le bonus « la requête commence le titre ».
 * @returns {object} index opaque (à ne consommer que via ce module)
 */
export function creerIndex(documents, champs) {
  const liste = Array.isArray(documents) ? documents : [];
  const declares = (Array.isArray(champs) ? champs : [])
    .filter((c) => c && typeof c === 'object' && typeof c.nom === 'string' && c.nom)
    .map((c, i) => ({
      nom: c.nom,
      poids: (typeof c.poids === 'number' && Number.isFinite(c.poids) && c.poids > 0)
        ? c.poids : 1,
      // Un bit par champ : les champs touchés tiennent dans un entier au lieu
      // d'un Set par paire (terme, document). Au-delà de 31 champs déclarés
      // — cas qui ne se présente pas ici, le corpus en compte 8 — le bit vaut
      // 0 : le champ reste indexé et scoré, il n'apparaît simplement plus
      // dans « champsTouches ».
      bit: i < 31 ? (1 << i) : 0
    }));

  const index = {
    type: MARQUEUR_INDEX,
    champs: declares,
    ordreChamps: new Map(),   // nom de champ -> rang d'affichage
    champPrincipal: null,     // champ de poids le plus fort (le titre)
    meta: new Map(),          // id -> { doc, cle, maj }
    // terme -> Map(id -> { poids cumulé, masque des champs touchés })
    // La taille de cette Map est aussi la fréquence documentaire du terme.
    inverse: new Map(),
    prefixes: new Map(),      // préfixe -> Set(terme)
    bigrammes: new Map(),     // bigramme -> Set(terme)
    ordreBase: [],            // ids pré-triés par le critère de départage
    documents: []
  };

  declares.forEach((c, i) => index.ordreChamps.set(c.nom, i));

  let poidsMax = -Infinity;
  for (const c of declares) {
    if (c.poids > poidsMax) { poidsMax = c.poids; index.champPrincipal = c.nom; }
  }

  for (const doc of liste) {
    if (!doc || typeof doc !== 'object') continue;
    if (doc.id === undefined || doc.id === null) continue;
    const id = String(doc.id);
    if (index.meta.has(id)) continue;                 // doublon d'identifiant

    const brutTitre = index.champPrincipal ? doc[index.champPrincipal] : '';
    const titre = Array.isArray(brutTitre)
      ? brutTitre.map(valeurSimple).join(' ')
      : valeurSimple(brutTitre);

    // Date de départage : 'maj' (documents) ou, à défaut, 'date' (réunions).
    let maj = '';
    if (typeof doc.maj === 'string') maj = doc.maj;
    else if (typeof doc.date === 'string') maj = doc.date;

    index.meta.set(id, {
      doc,
      cle: normaliser(titre),   // titre normalisé, pour le départage
      maj
    });
    index.documents.push(doc);

    for (const champ of declares) indexerChamp(index, id, doc, champ);
  }

  // Ordre de repli (requête vide, ex aequo) calculé une fois pour toutes.
  index.ordreBase = Array.from(index.meta.keys())
    .sort((a, b) => departager(index, a, b));

  return index;
}

/** Vrai si l'objet reçu est bien un index produit par creerIndex(). */
function estIndex(index) {
  return !!index && typeof index === 'object' && index.type === MARQUEUR_INDEX;
}

/* -------------------------------------------------------------------------
   4. Départage stable des ex aequo
   ------------------------------------------------------------------------- */

/**
 * Critère de départage explicite et déterministe (SPEC §5) :
 * date de mise à jour décroissante, puis titre alphabétique, puis
 * identifiant. Jamais l'ordre d'insertion.
 * Les comparaisons se font sur des chaînes normalisées avec < / > afin de
 * rester indépendantes de la locale de l'utilisateur.
 */
function departager(index, idA, idB) {
  const a = index.meta.get(idA);
  const b = index.meta.get(idB);
  if (a.maj !== b.maj) return a.maj < b.maj ? 1 : -1;   // plus récent d'abord
  if (a.cle !== b.cle) return a.cle < b.cle ? -1 : 1;   // titre croissant
  if (idA !== idB) return idA < idB ? -1 : 1;           // filet de sécurité
  return 0;
}

/** Arrondi du score : évite que le bruit flottant ne perturbe le tri. */
function arrondir(valeur) {
  return Math.round(valeur * PRECISION_SCORE) / PRECISION_SCORE;
}

/* -------------------------------------------------------------------------
   5. Expansion d'un terme de requête
   ------------------------------------------------------------------------- */

/**
 * Termes du vocabulaire commençant par le terme donné.
 *
 * Tri par longueur croissante — donc par proximité au terme saisi — puis
 * alphabétique. La fréquence globale serait ici le critère exactement
 * anti-pertinent : les complétions les plus fréquentes sont les moins
 * discriminantes, et les couper par le bas fait disparaître des documents
 * dont le mot commence pourtant littéralement par ce qui a été tapé.
 * Le terme saisi lui-même, s'il existe au vocabulaire, est la complétion la
 * plus courte : il est toujours en tête.
 *
 * La coupe se fait sur le budget de postings, pas sur le nombre de termes :
 * un préfixe rare n'est jamais tronqué (aucun document perdu au fil de la
 * frappe), un préfixe très commun s'arrête dès le budget atteint, ce qui
 * garantit qu'une requête ne parcourt jamais le corpus entier.
 */
function termesParPrefixe(index, terme) {
  const cle = terme.slice(0, PREFIXE_MAX);
  const ensemble = index.prefixes.get(cle);
  if (!ensemble) return [];

  let liste = Array.from(ensemble);
  if (terme.length > PREFIXE_MAX) {
    liste = liste.filter((t) => t.startsWith(terme));
  }
  liste.sort((x, y) => (x.length - y.length) || (x < y ? -1 : (x > y ? 1 : 0)));

  let budget = BUDGET_PREFIXE_POSTINGS;
  const retenus = [];
  for (const autre of liste) {
    retenus.push(autre);
    const postings = index.inverse.get(autre);
    budget -= postings ? postings.size : 0;
    if (budget <= 0) break;
  }
  return retenus;
}

/**
 * Termes du vocabulaire proches du terme donné (tolérance aux fautes).
 * Les bigrammes servent de pré-filtre : une édition ne peut détruire que
 * deux bigrammes, on exige donc un recouvrement minimal avant de payer le
 * prix d'un calcul de distance.
 *
 * @param {Set<string>} exclus termes déjà comptés (exact / préfixe)
 * @returns {Array<{terme:string, distance:number}>}
 */
function termesApproches(index, terme, seuil, exclus) {
  const bigrammes = bigrammesDe(terme);
  if (bigrammes.length === 0) return [];

  const partages = new Map();
  for (const bg of bigrammes) {
    const ensemble = index.bigrammes.get(bg);
    if (!ensemble) continue;
    for (const autre of ensemble) {
      if (autre === terme || exclus.has(autre)) continue;
      if (Math.abs(autre.length - terme.length) > seuil) continue;
      partages.set(autre, (partages.get(autre) || 0) + 1);
    }
  }

  const minimum = Math.max(1, bigrammes.length - 2 * seuil);
  const retenus = [];
  for (const [autre, n] of partages) {
    if (n < minimum) continue;
    const d = distanceBornee(terme, autre, seuil);
    // La fréquence documentaire est la taille de la liste de postings :
    // elle est relevée ici une fois, pas à chaque comparaison du tri.
    if (d <= seuil) {
      const postings = index.inverse.get(autre);
      retenus.push({
        terme: autre,
        distance: d,
        frequence: postings ? postings.size : 0
      });
    }
  }

  retenus.sort((x, y) => {
    if (x.distance !== y.distance) return x.distance - y.distance;
    if (x.frequence !== y.frequence) return y.frequence - x.frequence;
    return x.terme < y.terme ? -1 : 1;
  });
  return retenus.length > EXPANSION_APPROX_MAX
    ? retenus.slice(0, EXPANSION_APPROX_MAX)
    : retenus;
}

/* -------------------------------------------------------------------------
   6. Recherche
   ------------------------------------------------------------------------- */

/**
 * Recherche dans l'index.
 *
 * @param {object} index      index produit par creerIndex()
 * @param {string} requete    texte saisi par l'utilisateur
 * @param {{limite?:number, filtre?:(doc:object)=>boolean}} [options]
 *        'filtre' est appliqué AVANT le classement : un document écarté
 *        n'est jamais scoré.
 * @returns {Array<{doc:object, score:number, champsTouches:string[]}>}
 *          trié par score décroissant, ex aequo départagés de façon stable.
 *          Requête vide : tous les documents filtrés, dans l'ordre de
 *          départage.
 */
export function rechercher(index, requete, options) {
  if (!estIndex(index)) return [];

  const opts = (options && typeof options === 'object') ? options : {};
  const limite = (typeof opts.limite === 'number' && Number.isFinite(opts.limite)
    && opts.limite >= 0) ? Math.floor(opts.limite) : Infinity;
  const filtre = typeof opts.filtre === 'function' ? opts.filtre : null;

  // Le filtre n'est évalué qu'une fois par document, et ne peut pas faire
  // tomber la recherche s'il lève une exception.
  const cacheFiltre = filtre ? new Map() : null;
  const accepte = (id) => {
    if (!filtre) return true;
    let valeur = cacheFiltre.get(id);
    if (valeur === undefined) {
      try { valeur = !!filtre(index.meta.get(id).doc); }
      catch (_e) { valeur = false; }
      cacheFiltre.set(id, valeur);
    }
    return valeur;
  };

  const requeteNormalisee = normaliser(requete);
  const termes = Array.from(new Set(decouper(requeteNormalisee)));

  // --- Requête vide (ou uniquement des espaces / de la ponctuation) -------
  if (termes.length === 0) {
    const sortie = [];
    for (const id of index.ordreBase) {
      if (sortie.length >= limite) break;
      if (!accepte(id)) continue;
      sortie.push({ doc: index.meta.get(id).doc, score: 0, champsTouches: [] });
    }
    return sortie;
  }

  // --- Accumulation, terme par terme -------------------------------------
  // id -> { id, score, champs:masque de bits, termes:number }
  const cumul = new Map();

  for (const terme of termes) {
    // Contributions du terme courant, séparées par nature : on doit
    // pouvoir écarter l'approximatif si une correspondance exacte existe.
    // Trois accumulateurs scalaires et deux masques de bits : aucune
    // allocation de conteneur par document candidat, et une forme d'objet
    // unique donc monomorphe.
    const partiel = new Map();
    const entree = (id) => {
      let e = partiel.get(id);
      if (!e) {
        e = { exact: 0, prefixe: 0, approx: 0, champs: 0, champsApprox: 0 };
        partiel.set(id, e);
      }
      return e;
    };

    // Trois versements distincts plutôt qu'un accès dynamique e[nature] par
    // clé chaîne dans la boucle la plus chaude du moteur.
    const verserExact = (termeIndexe) => {
      const postings = index.inverse.get(termeIndexe);
      if (!postings) return;
      for (const [id, p] of postings) {
        if (!accepte(id)) continue;
        const e = entree(id);
        e.exact += p.poids;
        e.champs |= p.champs;
      }
    };

    const verserPrefixe = (termeIndexe, facteur) => {
      const postings = index.inverse.get(termeIndexe);
      if (!postings) return;
      for (const [id, p] of postings) {
        if (!accepte(id)) continue;
        const e = entree(id);
        e.prefixe += p.poids * facteur;
        e.champs |= p.champs;
      }
    };

    const verserApprox = (termeIndexe, facteur) => {
      const postings = index.inverse.get(termeIndexe);
      if (!postings) return;
      for (const [id, p] of postings) {
        if (!accepte(id)) continue;
        const e = entree(id);
        e.approx += p.poids * facteur;
        e.champsApprox |= p.champs;
      }
    };

    // (a) correspondance exacte : poids plein
    verserExact(terme);

    // (b) correspondance par préfixe : fraction du poids plein, d'autant
    //     plus forte que le terme indexé est proche en longueur.
    const utilises = new Set([terme]);
    for (const autre of termesParPrefixe(index, terme)) {
      if (autre === terme) continue;
      utilises.add(autre);
      const rapport = terme.length / autre.length;
      const facteur = POIDS_PREFIXE
        * (PREFIXE_PART_FIXE + (1 - PREFIXE_PART_FIXE) * rapport);
      verserPrefixe(autre, facteur);
    }

    // (c) correspondance approximative : fraction faible, dégressive avec
    //     la distance. Jamais pour les termes trop courts.
    const seuil = seuilEdition(terme);
    if (seuil > 0) {
      for (const { terme: autre, distance } of termesApproches(index, terme, seuil, utilises)) {
        verserApprox(autre, POIDS_APPROX / (1 + distance));
      }
    }

    // Fusion dans le cumul général.
    for (const [id, e] of partiel) {
      // Règle SPEC : l'approximatif n'est JAMAIS retenu si une
      // correspondance exacte existe pour ce terme dans ce document.
      const approxRetenu = e.exact === 0;
      const apport = e.exact + e.prefixe + (approxRetenu ? e.approx : 0);
      if (apport <= 0) continue;

      let c = cumul.get(id);
      if (!c) { c = { id, score: 0, champs: 0, termes: 0 }; cumul.set(id, c); }
      c.score += apport;
      c.termes += 1;
      c.champs |= e.champs;
      if (approxRetenu) c.champs |= e.champsApprox;
    }
  }

  if (cumul.size === 0) return [];

  // --- Bonus de requête complète et de titre ------------------------------
  const resultats = [];
  for (const c of cumul.values()) {
    let score = c.score;
    if (termes.length > 1 && c.termes === termes.length) score *= BONUS_TOUS_TERMES;

    const cle = index.meta.get(c.id).cle;
    if (cle && requeteNormalisee) {
      if (cle === requeteNormalisee) score *= BONUS_TITRE_EXACT;
      else if (cle.startsWith(requeteNormalisee)) score *= BONUS_TITRE_PREFIXE;
    }
    c.score = arrondir(score);
    resultats.push(c);
  }

  // --- Classement --------------------------------------------------------
  resultats.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return departager(index, a.id, b.id);
  });

  const retenus = (limite < resultats.length) ? resultats.slice(0, limite) : resultats;
  // Le masque de bits n'est reconverti en noms de champs que pour les seuls
  // résultats effectivement renvoyés, jamais pour tous les candidats.
  return retenus.map((c) => ({
    doc: index.meta.get(c.id).doc,
    score: c.score,
    champsTouches: nomsDeMasque(index, c.champs)
  }));
}

/**
 * Convertit un masque de champs en noms, dans l'ordre de déclaration :
 * stable, lisible, et indépendant de tout ordre d'insertion.
 */
function nomsDeMasque(index, masque) {
  const sortie = [];
  if (!masque) return sortie;
  const champs = index.champs;
  for (let i = 0; i < champs.length; i++) {
    if (masque & champs[i].bit) sortie.push(champs[i].nom);
  }
  return sortie;
}

/* -------------------------------------------------------------------------
   7. Surlignage (sans HTML)
   ------------------------------------------------------------------------- */

/**
 * Construit la forme normalisée d'un texte AVEC la table de correspondance
 * vers les positions d'origine : indices[i] donne la position, dans le
 * texte source, du caractère dont provient le i-ième caractère normalisé.
 * La normalisation se fait caractère par caractère (un caractère source
 * peut produire 0 caractère — un accent combinant — ou 2 — une ligature).
 */
function carteNormalisation(texte) {
  let normalise = '';
  const indices = [];
  let position = 0;
  for (const caractere of Array.from(texte)) {
    const morceau = normaliserFragment(caractere);
    for (let k = 0; k < morceau.length; k++) indices.push(position);
    normalise += morceau;
    position += caractere.length;   // gère les paires de substitution
  }
  return { normalise, indices };
}

/** Longueur, en unités de code, du caractère commençant à la position p. */
function tailleCaractere(texte, p) {
  const point = texte.codePointAt(p);
  return (point !== undefined && point > 0xffff) ? 2 : 1;
}

/**
 * Découpe un texte en segments selon les termes d'une requête.
 * Ne renvoie JAMAIS de HTML : l'appelant crée les nœuds DOM lui-même
 * (textContent / <mark>), ce qui rend l'injection impossible.
 * Les chevauchements de plusieurs termes sont fusionnés, donc aucun
 * fragment de texte n'est dupliqué ni perdu : la concaténation des
 * segments redonne exactement le texte d'origine.
 *
 * @param {string} texte
 * @param {string} requete
 * @returns {Array<{texte:string, correspond:boolean}>}
 */
export function surligner(texte, requete) {
  if (typeof texte !== 'string' || texte === '') return [];

  let termes;
  try {
    termes = Array.from(new Set(decouper(normaliser(requete))));
  } catch (_e) {
    termes = [];
  }
  if (termes.length === 0) return [{ texte, correspond: false }];

  try {
    const { normalise, indices } = carteNormalisation(texte);
    if (!normalise) return [{ texte, correspond: false }];

    // Plages correspondantes, en coordonnées normalisées.
    const plages = [];
    let position = 0;
    while (position < normalise.length) {
      // Saut des séparateurs.
      while (position < normalise.length && normalise[position] === ' ') position++;
      if (position >= normalise.length) break;
      let fin = position;
      while (fin < normalise.length && normalise[fin] !== ' ') fin++;

      const mot = normalise.slice(position, fin);
      for (const terme of termes) {
        if (terme.length > mot.length) continue;
        if (mot === terme || mot.startsWith(terme)) {
          // Exact ou préfixe : on ne surligne que la partie correspondante.
          plages.push([position, position + terme.length]);
        } else {
          // Faute de frappe tolérée : le mot entier est surligné.
          const seuil = seuilEdition(terme);
          if (seuil > 0 && distanceBornee(mot, terme, seuil) <= seuil) {
            plages.push([position, fin]);
          }
        }
      }
      position = fin;
    }

    if (plages.length === 0) return [{ texte, correspond: false }];

    // Fusion des plages qui se chevauchent ou se touchent.
    plages.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
    const fusionnees = [];
    for (const plage of plages) {
      const derniere = fusionnees[fusionnees.length - 1];
      if (derniere && plage[0] <= derniere[1]) {
        if (plage[1] > derniere[1]) derniere[1] = plage[1];
      } else {
        fusionnees.push([plage[0], plage[1]]);
      }
    }

    // Retour aux coordonnées du texte d'origine, puis construction des
    // segments. On prend la fin du dernier caractère source concerné, ce
    // qui conserve les accents et les ligatures avec leur lettre.
    const segments = [];
    let curseur = 0;
    for (const [debutN, finN] of fusionnees) {
      const debut = indices[debutN];
      const dernier = indices[finN - 1];
      if (debut === undefined || dernier === undefined) continue;
      const fin = dernier + tailleCaractere(texte, dernier);
      if (fin <= curseur) continue;                 // déjà couvert
      const depart = Math.max(debut, curseur);
      if (depart > curseur) {
        segments.push({ texte: texte.slice(curseur, depart), correspond: false });
      }
      segments.push({ texte: texte.slice(depart, fin), correspond: true });
      curseur = fin;
    }
    if (curseur < texte.length) {
      segments.push({ texte: texte.slice(curseur), correspond: false });
    }
    return segments.length ? segments : [{ texte, correspond: false }];
  } catch (_e) {
    // Le surlignage est un confort : en cas d'imprévu, on rend le texte brut.
    return [{ texte, correspond: false }];
  }
}

/* -------------------------------------------------------------------------
   8. Suggestion « vouliez-vous dire… »
   ------------------------------------------------------------------------- */

/**
 * Terme du vocabulaire le plus proche d'un terme saisi, ou null.
 * La tolérance est ici volontairement PLUS large que celle du scoring :
 * on n'arrive dans cette fonction que si la recherche n'a rien trouvé,
 * donc au-delà de ce que le moteur sait déjà rattraper tout seul.
 */
function meilleurVoisin(index, terme) {
  if (index.inverse.has(terme)) return terme;          // déjà connu
  if (terme.length < 3) return null;                   // trop court pour deviner
  const seuil = Math.min(3, Math.max(1, Math.ceil(terme.length / 3)));
  const candidats = termesApproches(index, terme, seuil, new Set());
  return candidats.length ? candidats[0].terme : null;
}

/**
 * Propose une reformulation quand la requête ne donne aucun résultat.
 * Chaque terme inconnu est remplacé par le terme du vocabulaire le plus
 * proche (distance d'édition, puis fréquence, puis ordre alphabétique :
 * la suggestion est donc déterministe).
 *
 * CONTRAT D'APPEL : à n'appeler que lorsque la recherche de l'appelant a
 * renvoyé zéro résultat. C'est l'appelant, et lui seul, qui sait avec quelles
 * facettes la recherche affichée a été faite ; relancer ici une recherche
 * interne reviendrait à en refaire une AUTRE, non filtrée, dix fois plus
 * coûteuse que celle de la page, à chaque frappe, pour n'en tirer aucune
 * information utile. Les termes déjà présents au vocabulaire sont de toute
 * façon renvoyés inchangés, donc une requête parfaitement orthographiée ne
 * produit jamais de suggestion.
 *
 * @param {object} index
 * @param {string} requete
 * @returns {string|null} la requête corrigée, ou null s'il n'y a rien à
 *          proposer.
 */
export function suggerer(index, requete) {
  if (!estIndex(index)) return null;

  const requeteNormalisee = normaliser(requete);
  const termes = decouper(requeteNormalisee);
  if (termes.length === 0) return null;

  const corriges = [];
  let modifie = false;
  for (const terme of termes) {
    const voisin = meilleurVoisin(index, terme);
    if (voisin && voisin !== terme) { corriges.push(voisin); modifie = true; }
    else corriges.push(terme);
  }
  if (!modifie) return null;

  const suggestion = corriges.join(' ');
  return suggestion === requeteNormalisee ? null : suggestion;
}
