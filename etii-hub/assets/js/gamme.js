/* =========================================================================
   ETII Hub — La gamme : lire les chiffres d'un porteur

   flotte.json range chaque valeur d'une fiche sous la forme
     { valeur, unite, qualificatif?, max?, annee?, prevu?, note?, detail?,
       confiance, source, correction? }
   `valeur` est un nombre propre (2250, 12.94) ou un texte court ; `note`
   la précision qui tient sur une ligne ; `detail` la phrase de la source,
   gardée entière ; `max` la borne haute d'une plage (« 15 à 19 »).
   Ce module ne dessine rien : il lit, met en forme à la française et
   compare. La fiche, la galerie, le comparateur et le bandeau du tableau
   de bord (porteurs.js, fiche-porteur.js) en tirent tous leurs chiffres —
   un appareil se lit donc partout de la même façon.

   Une valeur ancienne écrite en toutes lettres (« 3 000 kg (standard) »,
   saisie dans le formulaire d'édition) se lit encore : son nombre de tête
   et son unité sont repris, le reste devient la précision.
   ========================================================================= */

export const NON_RENSEIGNE = 'à renseigner';

export function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
export function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }

/* Un nombre à la française : « 2 250 », « 12,94 ». Les décimales ne sont
   écrites que si elles existent. */
export function nombreFr(n, decimales) {
  const d = decimales === undefined ? 2 : decimales;
  try { return Number(n).toLocaleString('fr-FR', { maximumFractionDigits: d }); }
  catch (_e) { return String(n); }
}

/* -------------------------------------------------------------------------
   1. Les chiffres : ce que chacun veut dire, en français courant
   ------------------------------------------------------------------------- */

/* Chaque chiffre a son groupe dans la fiche, son libellé, la question à
   laquelle il répond (dite sous le nombre), son unité de référence (celle
   des comparaisons), le comparatif que la jauge lit à voix haute (« plus
   lourd que 8 des 19 autres ») et le superlatif qui marque, dans le
   comparateur, l'appareil en tête. */
export const CHIFFRES = {
  longueur: { groupe: 'dimensions', libelle: 'Longueur hors tout', question: 'rotors tournants, de bout en bout', unite: 'm', plus: 'plus long', lePlus: 'le plus long' },
  longueurFuselage: { groupe: 'dimensions', libelle: 'Longueur du fuselage', question: 'la cellule seule, sans les pales', unite: 'm', plus: 'plus long', lePlus: 'le plus long' },
  hauteur: { groupe: 'dimensions', libelle: 'Hauteur', question: 'posé au sol, jusqu’au sommet', unite: 'm', plus: 'plus haut', lePlus: 'le plus haut' },
  diametreRotor: { groupe: 'dimensions', libelle: 'Diamètre du rotor', question: 'la largeur du disque des pales', unite: 'm', plus: 'plus grand', lePlus: 'le plus grand rotor' },
  masseMaxDecollage: { groupe: 'masses', libelle: 'Masse maximale au décollage', question: 'le plus lourd qu’il peut être pour décoller', unite: 'kg', plus: 'plus lourd', lePlus: 'le plus lourd' },
  masseAVide: { groupe: 'masses', libelle: 'Masse à vide', question: 'l’appareil seul, sans charge ni carburant', unite: 'kg', plus: 'plus lourd', lePlus: 'le plus lourd à vide' },
  chargeUtile: { groupe: 'masses', libelle: 'Charge utile', question: 'ce qu’il emporte : personnes, fret, carburant', unite: 'kg', plus: 'emporte plus', lePlus: 'emporte le plus' },
  passagers: { groupe: 'capacite', libelle: 'Passagers', question: 'places en cabine, en plus de l’équipage', unite: 'passagers', plus: 'emporte plus', lePlus: 'le plus de places' },
  equipage: { groupe: 'capacite', libelle: 'Équipage', question: 'qui le pilote', unite: 'pilotes', plus: 'plus nombreux', lePlus: 'le plus d’équipage' },
  nombreMoteurs: { groupe: 'motorisation', libelle: 'Moteurs', question: 'turbines qui entraînent le rotor', unite: 'moteurs', plus: 'plus de moteurs', lePlus: 'le plus de moteurs' },
  puissance: { groupe: 'motorisation', libelle: 'Puissance par moteur', question: 'au décollage', unite: 'kW', plus: 'plus puissant', lePlus: 'le plus puissant' },
  vitesseCroisiere: { groupe: 'performances', libelle: 'Vitesse de croisière', question: 'son allure normale en vol', unite: 'km/h', plus: 'plus rapide', lePlus: 'le plus rapide' },
  vitesseMax: { groupe: 'performances', libelle: 'Vitesse maximale', question: 'à ne jamais dépasser', unite: 'km/h', plus: 'plus rapide', lePlus: 'le plus rapide' },
  distanceFranchissable: { groupe: 'performances', libelle: 'Distance franchissable', question: 'jusqu’où il vole avec un plein, sans ravitailler', unite: 'km', plus: 'va plus loin', lePlus: 'va le plus loin' },
  rayonAction: { groupe: 'performances', libelle: 'Rayon d’action', question: 'jusqu’où il va, pour revenir', unite: 'km', plus: 'va plus loin', lePlus: 'va le plus loin' },
  autonomie: { groupe: 'performances', libelle: 'Autonomie', question: 'combien de temps il tient en l’air', unite: 'min', plus: 'tient plus longtemps', lePlus: 'tient le plus longtemps' },
  plafond: { groupe: 'performances', libelle: 'Altitude maximale', question: 'le plus haut où il peut voler', unite: 'm', plus: 'monte plus haut', lePlus: 'monte le plus haut' },
  unitesProduites: { groupe: 'production', libelle: 'Exemplaires', question: 'produits ou livrés', unite: 'appareils', plus: 'plus répandu', lePlus: 'le plus répandu' }
};

/* Les groupes de la fiche, dans l'ordre où on les lit : la taille, le
   poids, qui monte à bord, ce qui le fait voler, ce qu'il sait faire,
   puis ce qui intéresse le service (l'électrique), et d'où il vient.
   Les libellés servent aussi au formulaire de modification. */
export const GROUPES = [
  { cle: 'dimensions', titre: 'Dimensions', champs: [
    ['longueur', 'Longueur hors tout'], ['longueurFuselage', 'Longueur du fuselage'], ['hauteur', 'Hauteur'], ['diametreRotor', 'Diamètre du rotor']] },
  { cle: 'masses', titre: 'Masses', champs: [
    ['masseMaxDecollage', 'Masse maximale au décollage'], ['masseAVide', 'Masse à vide'], ['chargeUtile', 'Charge utile']] },
  { cle: 'capacite', titre: 'À bord', champs: [['passagers', 'Passagers'], ['equipage', 'Équipage']] },
  { cle: 'motorisation', titre: 'Motorisation', champs: [
    ['nombreMoteurs', 'Moteurs'], ['moteur', 'Moteur'], ['puissance', 'Puissance par moteur'],
    ['rotorPrincipal', 'Rotor principal'], ['rotorArriere', 'Rotor arrière']] },
  { cle: 'performances', titre: 'Performances', champs: [
    ['vitesseCroisiere', 'Vitesse de croisière'], ['vitesseMax', 'Vitesse maximale'], ['distanceFranchissable', 'Distance franchissable'],
    ['rayonAction', 'Rayon d’action'], ['autonomie', 'Autonomie'], ['plafond', 'Altitude maximale']] },
  { cle: 'electrique', titre: 'Électrique & avionique', champs: [
    ['reseau', 'Réseau de bord'], ['generation', 'Génération électrique'], ['avionique', 'Avionique'], ['particularites', 'Particularités']] },
  { cle: 'identite', titre: 'Identité', champs: [
    ['constructeur', 'Constructeur'], ['premierVol', 'Premier vol'], ['miseEnService', 'Mise en service'],
    ['certification', 'Certification'], ['siteAssemblage', 'Assemblé à']] },
  { cle: 'production', titre: 'Production', champs: [
    ['unitesProduites', 'Exemplaires'], ['prixIndicatif', 'Prix indicatif'], ['cadence', 'Cadence'],
    ['principauxOperateurs', 'Principaux opérateurs'], ['commandesNotables', 'Commandes notables']] }
];

/* Les six chiffres de « L'essentiel », les mêmes pour tous les appareils :
   combien il mesure, combien il pèse, combien il emporte, à quelle
   vitesse, jusqu'où, avec quoi. */
export const ESSENTIEL = ['longueur', 'masseMaxDecollage', 'passagers', 'vitesseCroisiere', 'distanceFranchissable', 'puissance'];

/* Les phases d'un programme, telles que la fiche les nomme. */
export const PHASES = {
  production: 'En production',
  service: 'En service',
  developpement: 'En développement',
  commande: 'Commandé',
  demonstrateur: 'Démonstrateur'
};

/* -------------------------------------------------------------------------
   2. Lire un champ
   ------------------------------------------------------------------------- */

/* Les unités qui se comptent : singulier, pluriel, et ce qu'on dit quand
   il n'y en a aucun. */
const COMPTES = {
  passagers: ['passager', 'passagers', 'aucun passager'],
  pilotes: ['pilote', 'pilotes', 'aucun à bord'],
  navigants: ['navigant', 'navigants', 'aucun'],
  moteurs: ['moteur', 'moteurs', 'aucun'],
  appareils: ['appareil', 'appareils', 'aucun'],
  personnes: ['personne', 'personnes', 'aucune']
};

/* Conversions vers l'unité de référence d'un chiffre (celle de CHIFFRES) :
   une puissance donnée en chevaux se compare en kilowatts, une masse en
   tonnes en kilogrammes, une durée en heures en minutes. */
const CONVERSIONS = {
  ch: ['kW', 0.7355], shp: ['kW', 0.7457], t: ['kg', 1000], h: ['min', 60], kt: ['km/h', 1.852], NM: ['km', 1.852]
};

/* Le nombre en tête d'un texte : « 255 km/h (138 kt) » → 255 et « km/h » ;
   « 6 096 m » → 6096 ; « 4 h 30 » → 270 minutes. Seules les unités
   connues sont prises pour des unités, et un nombre suivi d'un autre mot
   (« 1 démonstrateur », « 2, en tandem » mis à part) reste une phrase. */
const UNITES_CONNUES = /^(km\/h|kg|km|kW|kt|NM|ft|shp|ch|min|t|m|h|V|passagers?|pilotes?|moteurs?|appareils?|places?|personnes?|soldats)(?=[\s,;.)]|$)/;

/* Une unité comptée, ramenée à la forme que COMPTES connaît. */
const SINGULIERS = {
  passager: 'passagers', places: 'passagers', place: 'passagers', soldats: 'passagers',
  pilote: 'pilotes', moteur: 'moteurs', appareil: 'appareils', personne: 'personnes'
};

function nombreEnTete(t) {
  const txt = texte(t).replace(/^(?:≈|~|environ|plus de|jusqu[’']à|de l[’']ordre de)\s*/i, '');
  const heure = /^(\d{1,2})\s*h\s*(\d{1,2})?(?:\s*min)?(?=[\s,;.)]|$)/.exec(txt);
  if (heure) return { nombre: Number(heure[1]) * 60 + (heure[2] ? Number(heure[2]) : 0), unite: 'min', reste: txt.slice(heure[0].length) };
  const m = /^(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](\d+))?/.exec(txt);
  if (!m) return null;
  const nombre = Number(m[1].replace(/[   ]/g, '') + (m[2] ? '.' + m[2] : ''));
  if (!Number.isFinite(nombre)) return null;
  const apres = txt.slice(m[0].length).replace(/^\s+/, '');
  const u = UNITES_CONNUES.exec(apres);
  if (!u && /^\p{L}/u.test(apres)) return null;
  return { nombre, unite: u ? u[1] : '', reste: u ? apres.slice(u[0].length) : apres };
}

/* La précision tirée d'un reste de texte : « (138 kt) croisière » →
   « 138 kt, croisière ». Rien si le reste est vide. */
function precision(reste) {
  let t = texte(reste).replace(/^[\s;,:–-]+/, '');
  const m = /^\(([^)]*)\)\s*(.*)$/.exec(t);
  if (m) t = [m[1], m[2]].filter(Boolean).join(', ');
  return t.replace(/^[\s;,:–-]+/, '').trim();
}

/**
 * Le champ `groupe.cle` d'un appareil, sous sa forme propre, ou null.
 * Le statut et l'ancien nom, rangés à la racine de la fiche, se lisent
 * comme des champs de l'identité.
 * @returns {null|{valeur:*, nombre:number|null, max:number|null, unite:string,
 *   qualificatif:string, annee:number|null, prevu:boolean, note:string,
 *   detail:string, confiance:string, source:string, correction:string}}
 */
export function champ(appareil, groupe, cle) {
  const f = objet(objet(appareil).fiche);
  let brut = objet(f[groupe])[cle];
  if (brut === undefined && groupe === 'identite' && (cle === 'statut' || cle === 'ancienNom')) brut = f[cle];
  if (brut === null || brut === undefined) return null;
  const c = (typeof brut === 'object' && !Array.isArray(brut)) ? brut : { valeur: brut };
  const v = c.valeur;
  if (v === null || v === undefined || (typeof v === 'string' && !v.trim())) return null;
  const sortie = {
    valeur: v, nombre: null, max: typeof c.max === 'number' && Number.isFinite(c.max) ? c.max : null,
    unite: texte(c.unite), qualificatif: texte(c.qualificatif),
    annee: Number.isFinite(c.annee) ? c.annee : null, prevu: c.prevu === true,
    note: texte(c.note), detail: texte(c.detail), confiance: texte(c.confiance),
    source: texte(c.source), correction: texte(c.correction)
  };
  if (typeof v === 'number' && Number.isFinite(v)) {
    sortie.nombre = v;
    /* L'ancienne forme accolait à l'unité sa précision : « kg (3 050 kg
       avec charge externe) ». La tête reste l'unité, le reste la note. */
    const coupe = sortie.unite.search(/\s*[;(]/);
    if (coupe > 0) {
      if (!sortie.note) sortie.note = precision(sortie.unite.slice(coupe));
      sortie.unite = sortie.unite.slice(0, coupe).trim();
    }
    if (sortie.unite.length > 12) { sortie.note = sortie.note || sortie.unite; sortie.unite = ''; }
  } else if (Array.isArray(v)) {
    sortie.valeur = v.map(texte).filter(Boolean).join(' · ');
  } else if (typeof v === 'string') {
    const def = CHIFFRES[cle];
    const n = def ? nombreEnTete(v) : null;
    if (n) {
      /* Un chiffre écrit en toutes lettres : le nombre de tête et son
         unité ; le texte entier reste le détail. */
      sortie.nombre = n.nombre;
      sortie.unite = SINGULIERS[n.unite] || n.unite || sortie.unite;
      if (!sortie.note) sortie.note = precision(n.reste).slice(0, 140);
      if (!sortie.detail && v.length > 24) sortie.detail = v;
      if (/^\s*(?:≈|~|environ)/i.test(v)) sortie.qualificatif = sortie.qualificatif || 'environ';
    }
  }
  return sortie;
}

/**
 * Un chiffre de CHIFFRES, prêt à comparer : `ref` est sa valeur dans
 * l'unité de référence (kW, kg, min…), `refMax` la borne haute d'une plage.
 */
export function chiffre(appareil, cle) {
  const def = CHIFFRES[cle];
  if (!def) return null;
  const c = champ(appareil, def.groupe, cle);
  if (!c) return null;
  let ref = c.nombre;
  let refMax = c.max;
  const conv = CONVERSIONS[c.unite];
  if (ref !== null && conv && conv[0] === def.unite) {
    ref = ref * conv[1];
    if (refMax !== null) refMax = refMax * conv[1];
  }
  return Object.assign(c, { cle, def, ref, refMax });
}

/* -------------------------------------------------------------------------
   3. Mettre en forme
   ------------------------------------------------------------------------- */

/* Une durée en minutes s'écrit « 4 h 27 ». */
function duree(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes - h * 60);
  return m ? h + ' h ' + String(m).padStart(2, '0') : h + ' h';
}

/* Le nombre d'une unité donnée, avec ses décimales utiles : un mètre au
   centimètre, une masse au kilo. */
function nombreDe(n, unite) {
  if (unite === 'min') return duree(n);
  if (unite === 'm' && n < 100) return nombreFr(n, 2);
  return nombreFr(n, n < 10 ? 1 : 0);
}

/**
 * Ce qu'on écrit pour un champ : le qualificatif (« environ », « jusqu'à »),
 * le nombre (ou la plage), l'unité — séparés pour que la fiche mette le
 * nombre en grand et l'unité en petit. `texte` est la forme d'une ligne.
 * @returns {{avant:string, nombre:string, unite:string, texte:string, chiffre:boolean}}
 */
export function formater(c) {
  if (!c) return { avant: '', nombre: '', unite: '', texte: NON_RENSEIGNE, chiffre: false };
  if (c.nombre === null) {
    const t = texte(c.valeur);
    return { avant: '', nombre: t, unite: '', texte: t, chiffre: false };
  }
  const u = c.unite;
  const compte = COMPTES[u];
  let nombre;
  let unite = u === 'min' ? '' : u;
  if (compte && c.nombre === 0 && c.max === null) {
    return { avant: '', nombre: compte[2], unite: '', texte: compte[2], chiffre: false };
  }
  if (c.max !== null && c.max !== c.nombre) {
    /* « 1 ou 2 pilotes », « 15 à 19 passagers », « 8 600 à 9 350 kg ». */
    const lien = (compte && c.max - c.nombre === 1) ? ' ou ' : ' à ';
    nombre = nombreDe(c.nombre, u) + lien + nombreDe(c.max, u);
  } else {
    nombre = nombreDe(c.nombre, u);
  }
  if (compte) unite = (c.max !== null ? c.max : c.nombre) > 1 ? compte[1] : compte[0];
  const avant = c.qualificatif;
  return { avant, nombre, unite, texte: [avant, nombre, unite].filter(Boolean).join(' '), chiffre: true };
}

/* La valeur d'un chiffre dans l'unité de référence, écrite : sert aux
   légendes des jauges (« 700 kg », « 11 000 kg »). */
export function formaterRef(cle, valeur) {
  const def = CHIFFRES[cle];
  if (!def || !Number.isFinite(valeur)) return '';
  const compte = COMPTES[def.unite];
  const n = nombreDe(valeur, def.unite);
  if (compte) return n + ' ' + (valeur > 1 ? compte[1] : compte[0]);
  return def.unite === 'min' ? n : n + ' ' + def.unite;
}

/* -------------------------------------------------------------------------
   4. La gamme : situer un appareil parmi les autres
   ------------------------------------------------------------------------- */

/**
 * Pour chaque chiffre, les valeurs de toute la flotte (dans l'unité de
 * référence), triées : l'échelle des jauges « par rapport à la gamme » et
 * des tris de la galerie.
 * @returns {Object<string, {valeurs: Array<{code:string, v:number, max:number|null}>, min:number, max:number}>}
 */
export function echelles(appareils) {
  const e = {};
  for (const cle of Object.keys(CHIFFRES)) {
    const valeurs = [];
    for (const a of appareils) {
      const c = chiffre(a, cle);
      if (c && c.ref !== null && c.ref >= 0) valeurs.push({ code: texte(a.code), v: c.ref, max: c.refMax });
    }
    valeurs.sort((x, y) => x.v - y.v);
    if (!valeurs.length) continue;
    e[cle] = { valeurs, min: valeurs[0].v, max: Math.max(...valeurs.map((x) => (x.max !== null ? x.max : x.v))) };
  }
  return e;
}

/**
 * Le rang d'un appareil sur un chiffre : combien d'appareils renseignés
 * ont une valeur strictement plus petite. « Plus lourd que 8 des 20 ».
 */
export function rang(echelle, code) {
  if (!echelle) return null;
  const moi = echelle.valeurs.find((x) => x.code === code);
  if (!moi) return null;
  return { dessous: echelle.valeurs.filter((x) => x.v < moi.v).length, total: echelle.valeurs.length };
}

/* -------------------------------------------------------------------------
   5. Le programme : marché, phase, dates
   ------------------------------------------------------------------------- */

/* La phase du programme : la clé du fichier, sinon une lecture du statut
   écrit en toutes lettres. */
export function phase(appareil) {
  const f = objet(objet(appareil).fiche);
  let cle = texte(f.phase);
  if (!PHASES[cle]) {
    const s = texte(f.statut).toLowerCase();
    if (/démonstrateur|laboratoire|banc/.test(s)) cle = 'demonstrateur';
    else if (/développement|essais/.test(s)) cle = 'developpement';
    else if (/command/.test(s)) cle = 'commande';
    else if (/production/.test(s)) cle = 'production';
    else if (/service/.test(s)) cle = 'service';
    else cle = '';
  }
  return { cle, libelle: PHASES[cle] || texte(f.statut) || NON_RENSEIGNE, statut: texte(f.statut) };
}

/* L'année de mise en service (ou prévue), sinon celle du premier vol :
   le tri « depuis quand » de la galerie. */
export function anneeService(appareil) {
  const m = champ(appareil, 'identite', 'miseEnService');
  if (m && m.annee) return { annee: m.annee, prevu: m.prevu, quoi: 'service' };
  const p = champ(appareil, 'identite', 'premierVol');
  if (p && p.annee) return { annee: p.annee, prevu: p.prevu, quoi: 'vol' };
  const lire = (c) => { const n = c && /\b(19|20)\d{2}\b/.exec(texte(c.valeur)); return n ? Number(n[0]) : null; };
  const a = lire(m) || lire(p);
  return a ? { annee: a, prevu: false, quoi: m ? 'service' : 'vol' } : null;
}

/* La frise du programme : les événements de la fiche, dans l'ordre. Sans
   frise dans le fichier, le premier vol et la mise en service suffisent. */
export function chronologie(appareil) {
  const f = objet(objet(appareil).fiche);
  const liste = Array.isArray(f.chronologie) ? f.chronologie : [];
  let sortie = liste.filter((e) => e && Number.isFinite(e.annee) && texte(e.texte))
    .map((e) => ({ annee: e.annee, texte: texte(e.texte), prevu: e.prevu === true, source: texte(e.source) }));
  if (!sortie.length) {
    const p = champ(appareil, 'identite', 'premierVol');
    const m = champ(appareil, 'identite', 'miseEnService');
    const an = (c) => (c && (c.annee || Number((/\b(19|20)\d{2}\b/.exec(texte(c.valeur)) || [])[0]))) || null;
    if (an(p)) sortie.push({ annee: an(p), texte: 'Premier vol', prevu: p.prevu, source: p.source });
    if (an(m)) sortie.push({ annee: an(m), texte: 'Mise en service', prevu: m.prevu, source: m.source });
  }
  sortie = sortie.sort((a, b) => a.annee - b.annee);
  return sortie;
}

/* L'accroche : la phrase courte de la fiche ; à défaut, la première phrase
   de la présentation, coupée proprement. */
export function accroche(appareil) {
  const f = objet(objet(appareil).fiche);
  const a = texte(f.accroche);
  if (a) return a;
  const r = texte(f.resume);
  if (!r) return '';
  const fin = r.search(/[.!?](\s|$)/);
  const phrase = fin > 0 ? r.slice(0, fin + 1) : r;
  if (phrase.length <= 170) return phrase;
  const coupe = phrase.lastIndexOf(' ', 160);
  return phrase.slice(0, coupe > 80 ? coupe : 160) + '…';
}

/* -------------------------------------------------------------------------
   6. Les dimensions du dessin à l'échelle
   ------------------------------------------------------------------------- */

/* La position du mât sur la longueur du fuselage, relevée sur les appareils
   dont on connaît à la fois la longueur hors tout, celle du fuselage et le
   diamètre du rotor (H125, H135, H145, H160, H175, Tigre : 0,30 à 0,36). */
const MAT = 0.325;

/**
 * Ce qu'il faut pour dessiner l'appareil à l'échelle : le diamètre du rotor
 * et une longueur (hors tout ou du fuselage) sont indispensables ; la
 * hauteur, si elle manque, suit une proportion stylisée. `cotes` ne porte
 * que les valeurs sourcées — le dessin ne cote jamais une valeur déduite.
 * @returns {null|{D:number, Lf:number, L:number, H:number, xm:number, avant:number,
 *   train:string, queue:string, moteurs:number, cotes:{longueur?:object, fuselage?:object, rotor:object, hauteur?:object}}}
 */
export function dimensions(appareil) {
  const D = chiffre(appareil, 'diametreRotor');
  const Lo = chiffre(appareil, 'longueur');
  const Lfu = chiffre(appareil, 'longueurFuselage');
  const Hc = chiffre(appareil, 'hauteur');
  const d = D && D.ref;
  if (!d || !((Lo && Lo.ref) || (Lfu && Lfu.ref))) return null;
  let Lf = Lfu && Lfu.ref;
  if (!Lf) Lf = (Lo.ref - d / 2) / (1 - MAT);
  const xm = MAT * Lf;
  /* Le disque du rotor dépasse le nez : c'est ce débord qui fait la
     longueur hors tout. */
  const avant = Math.max(0, d / 2 - xm);
  const arriere = Math.max(Lf, xm + d / 2);
  const L = avant + arriere;
  const H = (Hc && Hc.ref) || Lf * 0.32;
  const s = texte(objet(appareil).silhouette);
  return {
    D: d, Lf, L, H, xm, avant,
    train: /^roues/.test(s) ? 'roues' : 'patins',
    queue: /fenestron/.test(s) ? 'carenee' : 'classique',
    moteurs: /-bi/.test(s) ? 2 : 1,
    cotes: {
      longueur: Lo && Lo.ref ? Lo : null,
      fuselage: !(Lo && Lo.ref) && Lfu && Lfu.ref ? Lfu : null,
      rotor: D,
      hauteur: Hc && Hc.ref ? Hc : null
    }
  };
}

/* -------------------------------------------------------------------------
   7. Les marchés
   ------------------------------------------------------------------------- */

/* Les marchés du fichier, dans son ordre ; un appareil d'un marché inconnu
   en ajoute un, pour ne jamais disparaître. */
export function marches(donnees, appareils) {
  const liste = Array.isArray(objet(donnees).categories) ? donnees.categories : [];
  const vus = new Map();
  for (const c of liste) {
    const o = typeof c === 'object' ? objet(c) : { cle: c, libelle: c };
    const cle = texte(o.cle ?? o.id ?? o.code);
    if (cle && !vus.has(cle)) vus.set(cle, { cle, libelle: texte(o.libelle ?? o.nom) || cle });
  }
  for (const a of appareils) {
    const cle = texte(a.categorie);
    if (cle && !vus.has(cle)) vus.set(cle, { cle, libelle: cle.charAt(0).toUpperCase() + cle.slice(1) });
  }
  return [...vus.values()].map((m) => Object.assign(m, { membres: appareils.filter((a) => texte(a.categorie) === m.cle) }));
}

/* La source d'une valeur, lisible sans être un lien : « fr.wikipedia.org ›
   Airbus_Helicopters_H125 ». La fiche ne mène jamais hors du site. */
export function sourcesLisibles(source) {
  return texte(source).split(/\s;\s/).map((s) => s.trim()).filter(Boolean).map((s) => {
    const m = /^https?:\/\/(?:www\.)?([^/\s]+)(\/[^\s]*)?(.*)$/.exec(s);
    if (!m) return s;
    let chemin = '';
    try { chemin = decodeURIComponent((m[2] || '').replace(/\/$/, '')); } catch (_e) { chemin = m[2] || ''; }
    const morceaux = chemin.split('/').filter(Boolean);
    const fin = morceaux.length ? morceaux[morceaux.length - 1] : '';
    return (m[1] + (fin ? ' › ' + fin.replace(/_/g, ' ') : '') + texte(m[3] ? ' ' + m[3] : '')).trim();
  });
}
