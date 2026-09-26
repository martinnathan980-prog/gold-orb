/* =========================================================================
   ETII Hub — Les porteurs
   La flotte suivie par le service, en galerie centrée : toutes les fiches
   compactes visibles d'un coup, groupées par catégorie (civil, militaire,
   prototype). Cliquer une carte la DÉPLIE : la fiche détaillée s'ouvre
   juste sous la rangée de la carte, jamais en bas de page — la photo en
   bannière avec le code seul en titre, le résumé sur toute la largeur,
   le rappel d'identité en bandeau, puis les onglets de données telles
   que le fichier les déclare. Une valeur absente s'écrit
   « à renseigner », jamais autre chose.
   ========================================================================= */

import { el, monter, annoncer, etatUrl, rafThrottle, mouvementReduit } from './ui.js';
import { barreEdition, boutonAjouter } from './edition.js';
import { creditPhoto } from './credits.js';
import { silhouette } from './helicos.js';

const NON_RENSEIGNE = 'à renseigner';

/* Au-delà de cette longueur, une valeur du bandeau d'identité ne tient plus
   dans une case : on la garde entière, mais en paragraphe. */
const LONGUEUR_CASE = 90;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }

/* Un nombre s'écrit à la française : « 2 500 », « 12,64 ». */
function nombreLisible(n) {
  try { return n.toLocaleString('fr-FR', { maximumFractionDigits: 2 }); }
  catch (_e) { return String(n); }
}

/* Une valeur numérique ou courte se lit en mono ; une phrase en texte.
   « ≈ 4 000 000 USD » commence par un chiffre ou un signe : mono aussi. */
function estChiffre(t) { return t.length <= 24 && /^[≈~≥≤<>+-]?\s*\d/.test(t); }

/**
 * Rend une valeur brute lisible, en séparant ce qui se lit d'abord
 * (`principal`) de ce qui précise (`complement`).
 *
 * Le fichier accole souvent à l'unité une longue précision :
 * « kW au décollage (952 ch) ; l'EC130 B4 initial disposait… ». La tête
 * de l'unité (jusqu'à la première parenthèse ou point-virgule) reste avec
 * le chiffre, le reste devient un complément en retrait — le chiffre se
 * lit d'abord, la précision ensuite.
 *
 * @returns {{principal: string, complement: string, chiffre: boolean, ok: boolean}}
 */
function valeurLisible(brut, unite) {
  const vide = { principal: NON_RENSEIGNE, complement: '', chiffre: false, ok: false };
  if (brut === null || brut === undefined) return vide;
  if (typeof brut === 'number') {
    if (!Number.isFinite(brut)) return vide;
    const u = texte(unite);
    const coupe = u.search(/\s*[;(]/);
    const tete = coupe === -1 ? u : u.slice(0, coupe).trim();
    const reste = coupe === -1 ? '' : u.slice(coupe).trim().replace(/^;\s*/, '');
    /* Une tête d'unité trop bavarde n'en est pas une : tout passe en phrase. */
    if (tete.length > 24) return { principal: nombreLisible(brut) + ' ' + u, complement: '', chiffre: false, ok: true };
    return { principal: tete ? nombreLisible(brut) + ' ' + tete : nombreLisible(brut), complement: reste, chiffre: true, ok: true };
  }
  if (Array.isArray(brut)) {
    const l = brut.map(texte).filter(Boolean);
    return l.length ? { principal: l.join(' · '), complement: '', chiffre: false, ok: true } : vide;
  }
  if (typeof brut === 'object') {
    const o = objet(brut);
    return ('valeur' in o) ? valeurLisible(o.valeur, o.unite ?? unite) : vide;
  }
  const t = texte(brut);
  if (!t) return vide;
  const u = texte(unite);
  /* Une unité ne s'accole qu'à une valeur courte : sur une phrase, elle est
     déjà dans le texte, et « … 1 440 l) kg » n'a aucun sens. */
  const courte = t.length <= 16 && !/\s\S+\s/.test(t);
  const principal = (u && courte) ? `${t} ${u}` : t;
  return { principal, complement: '', chiffre: estChiffre(principal), ok: true };
}

function categories(donnees, appareils) {
  const liste = Array.isArray(donnees.categories) ? donnees.categories : [];
  const vues = new Map();
  for (const c of liste) {
    const o = typeof c === 'object' ? objet(c) : { cle: c, libelle: c };
    const cle = texte(o.cle ?? o.id ?? o.code);
    if (cle && !vues.has(cle)) vues.set(cle, { cle, libelle: texte(o.libelle ?? o.nom) || cle });
  }
  for (const a of appareils) {
    const cle = texte(a.categorie);
    if (cle && !vues.has(cle)) vues.set(cle, { cle, libelle: cle });
  }
  return [...vues.values()];
}

/* -------------------------------------------------------------------------
   La carte de la galerie
   ------------------------------------------------------------------------- */

/* Une photo introuvable — une adresse qui a changé, un réseau d'entreprise
   qui filtre l'extérieur — ne laisse jamais d'icône cassée : la silhouette
   reprend simplement sa place. */
function vignettePhoto(appareil) {
  const repli = () => silhouette(texte(appareil.silhouette), { titre: '' });
  if (!texte(appareil.photo)) return repli();
  const img = el('img', {
    src: texte(appareil.photo), alt: '', loading: 'lazy', decoding: 'async',
    class: 'porteurs__fiche-photo', onError: () => img.replaceWith(repli())
  });
  return img;
}

function fiche(appareil, prefixe) {
  const code = texte(appareil.code) || '—';
  return el('li', { class: 'porteurs__item', dataset: { categorie: texte(appareil.categorie), code } },
    el('button', {
      type: 'button',
      class: 'porteurs__fiche',
      id: prefixe + '-fiche-' + code,
      dataset: { code },
      'aria-pressed': 'false',
      'aria-expanded': 'false'
    },
    el('span', { class: 'porteurs__fiche-visuel', 'aria-hidden': 'true' },
      vignettePhoto(appareil)),
    el('span', { class: 'porteurs__fiche-code' }, code),
    el('span', { class: 'porteurs__fiche-segment' }, texte(appareil.segment) || texte(objet(appareil.fiche).segment) || NON_RENSEIGNE),
    el('span', { class: 'porteurs__fiche-poles', 'aria-label': 'Pôles : ' + (Array.isArray(appareil.poles) ? appareil.poles.join(', ') : '') },
      (Array.isArray(appareil.poles) ? appareil.poles : []).map((p) =>
        el('span', { class: 'porteurs__pole-point', dataset: { pole: texte(p) }, title: 'Pôle ' + texte(p) })))));
}

/* -------------------------------------------------------------------------
   La fiche détaillée

   Deux formes de données cohabitent :
   - `fiche` : la base d'information PUBLIQUE constituée par le service
     (identité, motorisation, masses, capacité, performances, dimensions,
     production et économie, électrique et avionique, insolite). Chaque
     champ porte sa valeur et son unité ; la fiche n'affiche ni sa
     confiance ni sa source, qui restent dans le fichier pour la relecture.
   - `service` (ou l'ancien couple technique / economique) : les données
     INTERNES au service, jamais inventées — « à renseigner » tant que le
     fichier ne les donne pas.
   ------------------------------------------------------------------------- */

const GROUPES_FICHE = [
  { cle: 'motorisation', titre: 'Motorisation', champs: [
    ['moteur', 'Moteur'], ['nombreMoteurs', 'Nombre de moteurs'], ['puissance', 'Puissance'],
    ['rotorPrincipal', 'Rotor principal'], ['rotorArriere', 'Rotor arrière']] },
  { cle: 'masses', titre: 'Masses', champs: [
    ['masseMaxDecollage', 'Masse max. au décollage'], ['masseAVide', 'Masse à vide'], ['chargeUtile', 'Charge utile']] },
  { cle: 'capacite', titre: 'Capacité', champs: [['equipage', 'Équipage'], ['passagers', 'Passagers']] },
  { cle: 'dimensions', titre: 'Dimensions', champs: [
    ['longueur', 'Longueur'], ['hauteur', 'Hauteur'], ['diametreRotor', 'Diamètre du rotor']] },
  /* L'identité (qui le construit, quand il a volé, où il est assemblé,
     son statut, son certificat) se lit ici, avec le reste de la
     technique : plus de bandeau gris entre le résumé et les onglets. */
  { cle: 'identite', titre: 'Identité', champs: [
    ['constructeur', 'Constructeur'], ['premierVol', 'Premier vol'], ['miseEnService', 'Mise en service'],
    ['siteAssemblage', 'Site d’assemblage'], ['statut', 'Statut'], ['certification', 'Certification'],
    ['ancienNom', 'Ancien nom']] },
  { cle: 'performances', titre: 'Performances', champs: [
    ['vitesseCroisiere', 'Vitesse de croisière'], ['vitesseMax', 'Vitesse maximale'], ['rayonAction', 'Rayon d’action'],
    ['autonomie', 'Autonomie'], ['plafond', 'Plafond']] },
  { cle: 'production', titre: 'Production & économie', champs: [
    ['unitesProduites', 'Unités produites'], ['prixIndicatif', 'Prix indicatif'], ['cadence', 'Cadence'],
    ['principauxOperateurs', 'Principaux opérateurs'], ['commandesNotables', 'Commandes notables']] },
  { cle: 'electrique', titre: 'Électrique & avionique', champs: [
    ['reseau', 'Réseau électrique'], ['generation', 'Génération'], ['avionique', 'Avionique'], ['particularites', 'Particularités']] }
];

/* Les libellés de la fiche, par groupe et par champ : le formulaire de
   modification (edition-contenus.js) nomme les champs comme la fiche. */
export function libellesFiche() {
  const r = {};
  for (const g of GROUPES_FICHE) r[g.cle] = Object.fromEntries(g.champs);
  return r;
}

/* Les grands chiffres de l'onglet Performances et de l'onglet Production. */
const CHIFFRES_PERF = [
  ['performances', 'vitesseCroisiere', 'Croisière'],
  ['performances', 'vitesseMax', 'Vitesse max.'],
  ['performances', 'rayonAction', 'Rayon d’action'],
  ['performances', 'plafond', 'Plafond'],
  ['performances', 'autonomie', 'Autonomie']
];
const CHIFFRES_PROD = [
  ['production', 'unitesProduites', 'Unités produites'],
  ['production', 'cadence', 'Cadence']
];

/* Cinq onglets, rien que sur l'appareil : ni sources, ni équipe, ni
   données du service. La fiche ne renvoie vers aucun site
   extérieur. Les crédits des photos, eux, restent dans la fenêtre
   « Crédits photos » du pied de page — c'est une obligation de licence. */
const ONGLETS = [
  { cle: 'technique', titre: 'Technique', groupes: ['motorisation', 'masses', 'capacite', 'dimensions', 'identite'], chiffres: true },
  { cle: 'performances', titre: 'Performances', groupes: ['performances'], chiffres: CHIFFRES_PERF },
  { cle: 'electrique', titre: 'Électrique', groupes: ['electrique'] },
  { cle: 'economie', titre: 'Production & économie', groupes: ['production'], chiffres: CHIFFRES_PROD },
  { cle: 'insolite', titre: 'Insolite' }
];

/* Les chiffres clés en tête de l'onglet Technique : seulement les valeurs
   que le fichier donne en nombre. */
const CHIFFRES_CLES = [
  ['masses', 'masseMaxDecollage', 'Masse max.'],
  ['motorisation', 'nombreMoteurs', 'Moteurs'],
  ['motorisation', 'puissance', 'Puissance'],
  ['capacite', 'passagers', 'Passagers'],
  ['performances', 'vitesseCroisiere', 'Croisière'],
  ['performances', 'rayonAction', 'Rayon d’action'],
  ['dimensions', 'diametreRotor', 'Rotor principal']
];

/* Le nombre en tête d'une valeur écrite en toutes lettres : « 255 km/h
   (138 kt) croisière recommandée » donne 255 et « km/h » ; « 6 096 m »
   donne 6096 ; « 4 h 30 avec réservoirs » donne « 4 h 30 ». */
function nombreEnTete(t) {
  const txt = texte(t);
  const heure = /^(\d{1,2})\s*h\s*(\d{2})?/.exec(txt);
  if (heure) return { nombre: Number(heure[1]) + (heure[2] ? Number(heure[2]) / 60 : 0), affiche: heure[0].trim(), unite: '', heure: true };
  const m = /^(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,](\d+))?\s*([^\s(;,]{1,8})?/.exec(txt);
  if (!m) return null;
  const nombre = Number(m[1].replace(/[ \u00a0\u202f]/g, '') + (m[2] ? '.' + m[2] : ''));
  if (!Number.isFinite(nombre)) return null;
  return { nombre, affiche: nombreLisible(nombre), unite: m[3] || '' };
}

/* Une phrase longue se lit mieux en deux temps : l'essentiel, puis sa
   précision en retrait. On coupe au premier « ; », sinon à la première
   parenthèse, et seulement quand le texte est long. */
function scinder(v) {
  if (!v.ok || v.complement || v.chiffre || v.principal.length <= 64) return v;
  const t = v.principal;
  let coupe = t.search(/\s*;\s/);
  let saut = coupe === -1 ? 0 : (t.slice(coupe).match(/^\s*;\s*/) || [''])[0].length;
  if (coupe === -1) {
    coupe = t.indexOf(' (');
    saut = 1;
    if (coupe < 12) return v;
  }
  return Object.assign({}, v, { principal: t.slice(0, coupe).trim(), complement: t.slice(coupe + saut).trim() });
}

function champFiche(brut) {
  const c = (brut && typeof brut === 'object' && !Array.isArray(brut)) ? brut : { valeur: brut };
  return scinder(valeurLisible(c.valeur, c.unite));
}

/* Une ligne : le libellé dans une colonne étroite, grise, en petites
   capitales ; la valeur à côté, l'essentiel d'abord, la précision dessous
   en plus petit. Toutes les lignes de la fiche ont cette forme. */
/* La valeur chiffrée d'un champ de fiche, ou null. */
function valeurNumerique(brut) {
  const o = objet(brut);
  const v = (brut && typeof brut === 'object' && !Array.isArray(brut)) ? o.valeur : brut;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const n = typeof v === 'string' ? nombreEnTete(v) : null;
  return n ? n.nombre : null;
}

/* Pour chaque champ chiffré, la plus grande valeur de la flotte et le
   nombre d'appareils qui la renseignent : l'échelle des jauges. */
function echellesFlotte(appareils) {
  const e = {};
  for (const a of appareils) {
    const f = objet(objet(a).fiche);
    for (const g of GROUPES_FICHE) {
      for (const [cle] of g.champs) {
        const v = valeurNumerique(objet(f[g.cle])[cle]);
        if (v === null || v <= 0) continue;
        const k = g.cle + '.' + cle;
        const cur = e[k] || { max: 0, n: 0, code: '' };
        if (v > cur.max) { cur.max = v; cur.code = texte(a.code); }
        cur.n += 1;
        e[k] = cur;
      }
    }
  }
  return e;
}

function ligneFiche(libelle, brut, echelle) {
  const c = champFiche(brut);
  const v = valeurNumerique(brut);
  /* La jauge : la valeur rapportée au plus grand de la flotte — on voit
     d'un coup d'œil où se situe l'appareil. Seulement quand au moins trois
     appareils renseignent le champ. */
  const jauge = (v !== null && echelle && echelle.n >= 3 && echelle.max > 0)
    ? el('span', {
        class: ['porteurs__jauge', v >= echelle.max ? 'porteurs__jauge--max' : null],
        style: { '--part': String(Math.min(1, v / echelle.max).toFixed(3)) },
        title: v >= echelle.max ? 'Le plus élevé de la flotte' : 'Le plus élevé de la flotte : ' + echelle.code,
        'aria-hidden': 'true'
      }, el('span', { class: 'porteurs__jauge-barre' }))
    : null;
  return el('div', { class: 'porteurs__ligne' },
    el('dt', { class: 'porteurs__libelle' }, libelle),
    el('dd', { class: 'porteurs__cellule' },
      el('span', { class: ['porteurs__valeur', c.chiffre ? 'porteurs__valeur--chiffre' : null, c.ok ? null : 'porteurs__manquant'] }, c.principal),
      jauge,
      c.complement ? el('span', { class: 'porteurs__complement' }, c.complement) : null));
}

function groupeFiche(titre, lignes) {
  return el('section', { class: 'porteurs__groupe' },
    el('h4', { class: 'porteurs__groupe-titre' }, titre),
    el('dl', { class: 'porteurs__lignes' }, lignes));
}

/* Les chiffres clés : trois à cinq tuiles, quand le fichier les donne en
   nombre. Rien ne s'affiche s'il n'y en a pas au moins deux. */
function chiffresCles(fiche, liste) {
  const tuiles = [];
  for (const [groupe, cle, libelle] of (liste || CHIFFRES_CLES)) {
    const brut = objet(fiche[groupe])[cle];
    const c = (brut && typeof brut === 'object') ? brut : { valeur: brut };
    let nombre;
    let unite;
    if (typeof c.valeur === 'number' && Number.isFinite(c.valeur)) {
      const v = valeurLisible(c.valeur, c.unite);
      [nombre, ...unite] = v.principal.split(' ');
    } else {
      /* Une valeur en toutes lettres : son nombre de tête, et son unité. */
      const n = typeof c.valeur === 'string' ? nombreEnTete(c.valeur) : null;
      if (!n) continue;
      nombre = n.affiche;
      unite = n.heure ? [] : n.unite ? [n.unite] : (texte(c.unite) && texte(c.unite).length <= 8 ? [texte(c.unite)] : []);
    }
    tuiles.push(el('div', { class: 'porteurs__chiffre' },
      el('dt', { class: 'porteurs__chiffre-libelle' }, libelle),
      el('dd', { class: 'porteurs__chiffre-valeur' },
        el('span', { class: 'porteurs__chiffre-nombre' }, nombre),
        unite.length ? el('span', { class: 'porteurs__chiffre-unite' }, ' ' + unite.join(' ')) : null)));
    if (tuiles.length === 5) break;
  }
  return tuiles.length >= 2 ? el('dl', { class: 'porteurs__chiffres', style: { '--nb': String(tuiles.length) } }, tuiles) : null;
}

function tableFiche(titre, champsDuGroupe, valeurs, cleGroupe, echelles) {
  const source = objet(valeurs);
  const e = echelles || {};
  return groupeFiche(titre, champsDuGroupe.map(([cle, libelle]) => ligneFiche(libelle, source[cle], e[cleGroupe + '.' + cle])));
}

/* « Le saviez-vous ? » : une carte par fait, numérotée en grand, dans
   des teintes qui alternent. La première phrase du fait sert d'accroche,
   la suite se lit dessous. */
function panneauInsolite(fiche) {
  const faits = (Array.isArray(fiche.insolites) ? fiche.insolites : []).filter((f) => f && texte(f.texte));
  if (!faits.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucun fait remarquable renseigné.');
  return el('ol', { class: 'porteurs__insolites', role: 'list' }, faits.map((f, i) => {
    const t = texte(f.texte);
    const coupe = t.search(/[.!?:;](\s|$)/);
    const accroche = coupe > 20 && coupe < t.length - 1 ? t.slice(0, coupe + 1) : t;
    const suite = accroche === t ? '' : t.slice(accroche.length).trim();
    return el('li', { class: 'porteurs__insolite', dataset: { teinte: String(i % 4) } },
      el('span', { class: 'porteurs__insolite-numero', 'aria-hidden': 'true' }, String(i + 1).padStart(2, '0')),
      el('p', { class: 'porteurs__insolite-accroche' }, accroche),
      suite ? el('p', { class: 'porteurs__insolite-suite' }, suite) : null);
  }));
}

function onglets(prefixe, panneaux) {
  const boutons = panneaux.map((p, i) => el('button', {
    type: 'button', class: 'onglets__onglet', role: 'tab', id: prefixe + '-onglet-' + p.cle,
    'aria-selected': i === 0 ? 'true' : 'false', 'aria-controls': prefixe + '-panneau-' + p.cle,
    tabIndex: i === 0 ? 0 : -1, dataset: { onglet: p.cle }
  }, p.titre));
  const zones = panneaux.map((p, i) => el('div', {
    class: 'onglets__panneau', role: 'tabpanel', id: prefixe + '-panneau-' + p.cle,
    'aria-labelledby': prefixe + '-onglet-' + p.cle, hidden: i !== 0, tabIndex: 0
  }, p.contenu));
  const liste = el('div', { class: 'onglets__liste', role: 'tablist', 'aria-label': 'Rubriques de la fiche' }, boutons);
  const racine = el('div', { class: 'onglets porteurs__onglets' }, liste, zones);
  const activer = (cle, focus) => {
    boutons.forEach((b) => {
      const actif = b.dataset.onglet === cle;
      b.setAttribute('aria-selected', actif ? 'true' : 'false');
      b.tabIndex = actif ? 0 : -1;
      if (actif && focus) b.focus();
    });
    zones.forEach((z) => { z.hidden = z.id !== prefixe + '-panneau-' + cle; });
  };
  liste.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-onglet]');
    if (b) activer(b.dataset.onglet, false);
  });
  liste.addEventListener('keydown', (evt) => {
    const i = boutons.indexOf(document.activeElement);
    if (i === -1) return;
    let j = i;
    if (evt.key === 'ArrowRight') j = (i + 1) % boutons.length;
    else if (evt.key === 'ArrowLeft') j = (i - 1 + boutons.length) % boutons.length;
    else if (evt.key === 'Home') j = 0;
    else if (evt.key === 'End') j = boutons.length - 1;
    else return;
    evt.preventDefault();
    activer(boutons[j].dataset.onglet, true);
  });
  return racine;
}

function detail(appareil, donnees, categoriesConnues, contexte) {
  const code = texte(appareil.code) || '—';
  const fiche = objet(appareil.fiche);
  const avecFiche = Object.keys(fiche).length > 0;
  const photo = texte(appareil.photo);
  const prefixe = 'porteur-' + code.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const echelles = echellesFlotte(Array.isArray(objet(donnees).flotte) ? objet(donnees).flotte : []);

  /* Les valeurs de l'onglet Technique : les groupes de la fiche ; le
     statut et l'ancien nom, rangés à la racine de la fiche, rejoignent
     l'identité. */
  const valeursGroupe = (cle) => cle === 'identite'
    ? Object.assign({}, objet(fiche.identite), { statut: fiche.statut, ancienNom: fiche.ancienNom })
    : fiche[cle];

  const panneaux = ONGLETS.map((o) => {
    if (o.groupes) {
      const groupes = o.groupes.map((g) => GROUPES_FICHE.find((x) => x.cle === g)).filter(Boolean);
      return { cle: o.cle, titre: o.titre,
        contenu: avecFiche
          ? el('div', { class: 'porteurs__panneau' },
              o.chiffres ? chiffresCles(fiche, Array.isArray(o.chiffres) ? o.chiffres : CHIFFRES_CLES) : null,
              el('div', { class: 'porteurs__groupes' }, groupes.map((g) => tableFiche(g.titre, g.champs, valeursGroupe(g.cle), g.cle, echelles))))
          : el('p', { class: 'texte-doux sans-marge' }, 'Fiche publique non encore constituée pour ce porteur.') };
    }
    return { cle: o.cle, titre: o.titre, contenu: panneauInsolite(fiche) };
  });

  /* La relecture contradictoire non faite : un badge discret, expliqué au
     survol — pas un encadré qui coupe la lecture. */
  const relecture = texte(fiche.relecture) === 'non effectuée'
    ? el('span', {
        class: 'badge badge--alerte porteurs__relecture',
        title: 'Fiche constituée depuis des sources publiques, pas encore relue par le service : '
          + 'vérifiez une valeur avant de vous en servir.'
      }, 'Relecture à faire')
    : null;

  /* Le titre de la bannière, c'est le code seul — « H125 », en grand. Le
     nom complet, la catégorie et le segment se lisent dans le bandeau de
     rappel, sous le résumé. */
  const titreBloc = el('div', { class: 'porteurs__banniere-texte' },
    el('div', { class: 'porteurs__titre-ligne' },
      el('h3', { class: 'porteurs__titre sans-marge' }, code),
      relecture));

  /* La bannière de repli, fabriquée à la demande : c'est elle qui prend la
     place de la photo si celle-ci ne se charge pas — sinon l'icône cassée
     et le voile se posent sur 384 px de vide, le défaut le plus voyant du
     site. */
  const banniereSilhouette = () => el('div', { class: 'porteurs__banniere porteurs__banniere--silhouette' },
    el('div', { class: 'porteurs__silhouette' },
      silhouette(texte(appareil.silhouette), { titre: 'Silhouette du ' + code }),
      el('span', { class: 'porteurs__photo-attente' }, 'Photo à venir')),
    titreBloc);

  const banniere = photo
    ? el('figure', { class: 'porteurs__banniere porteurs__banniere--photo' },
        el('img', { src: photo, alt: 'Photo du ' + code, class: 'porteurs__photo', decoding: 'async',
          onError: () => banniere.replaceWith(banniereSilhouette()) }),
        el('div', { class: 'porteurs__banniere-voile', 'aria-hidden': 'true' }),
        titreBloc)
    : banniereSilhouette();

  /* En mode édition : modifier la fiche, ou retirer le porteur. */
  const ctx = contexte || {};
  const commandes = (typeof ctx.surModifier === 'function' || typeof ctx.surSupprimer === 'function')
    ? barreEdition({
        classe: 'porteurs__edition',
        quoi: code,
        surModifier: typeof ctx.surModifier === 'function' ? (b) => ctx.surModifier(appareil, b) : null,
        surSupprimer: typeof ctx.surSupprimer === 'function' ? () => ctx.surSupprimer(appareil) : null
      })
    : null;

  return el('article', { class: 'porteurs__detail', 'aria-label': 'Fiche ' + code, id: prefixe + '-detail' },
    banniere,
    el('div', { class: 'porteurs__contenu' },
      commandes,
      texte(fiche.resume) ? el('p', { class: 'porteurs__resume sans-marge' }, texte(fiche.resume)) : null,
      onglets(prefixe, panneaux)));
}

/* -------------------------------------------------------------------------
   Les crédits de toutes les photos, pour la fenêtre « Crédits photos »
   ------------------------------------------------------------------------- */

/**
 * Construit la liste des crédits de toutes les photos de la flotte.
 * C'est l'obligation de licence rendue lisible en un seul endroit : le
 * pied de page l'ouvre dans une fenêtre.
 *
 * @param {object} donnees   contenu de flotte.json
 * @returns {HTMLElement}
 */
export function creditsPhotos(donnees) {
  const d = objet(donnees);
  const appareils = (Array.isArray(d.flotte) ? d.flotte : [])
    .filter((a) => a && typeof a === 'object' && texte(a.photo));
  if (!appareils.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucune photo dans la flotte.');
  return el('div', { class: 'pile' },
    el('p', { class: 'texte-doux texte-sm sans-marge mesure' },
      'Les photos des porteurs viennent de Wikimedia Commons, sous licence libre. '
      + 'Chaque auteur et chaque licence sont indiqués ici, comme la licence l’exige.'),
    el('ul', { class: 'porteurs__credits', role: 'list' }, appareils.map((a) => {
      const credit = creditPhoto(a.credit) || el('p', { class: 'porteurs__credit sans-marge porteurs__manquant' }, 'Crédit ' + NON_RENSEIGNE);
      return el('li', { class: 'porteurs__credits-item' },
        el('img', { src: texte(a.photo), alt: '', loading: 'lazy', decoding: 'async', class: 'porteurs__credits-vignette' }),
        el('div', { class: 'porteurs__credits-texte' },
          el('span', { class: 'porteurs__credits-nom' }, texte(objet(a.fiche).nom) || texte(a.code)),
          credit));
    })));
}

/* -------------------------------------------------------------------------
   Le composant
   ------------------------------------------------------------------------- */

/**
 * @param {object} donnees   contenu de flotte.json
 * @param {{id?: string, surAjouter?: Function, surModifier?: Function, surSupprimer?: Function}} [options]
 *   Les trois commandes d'édition ne se voient qu'en mode édition
 *   (edition.js).
 * @returns {HTMLElement}
 */
export function porteurs(donnees, options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'porteurs';
  const d = objet(donnees);
  const appareils = (Array.isArray(d.flotte) ? d.flotte : []).filter((a) => a && typeof a === 'object' && texte(a.code));
  const cats = categories(d, appareils);

  let categorie = '';
  /* Le porteur déplié, s'il y en a un, et l'élément de galerie qui porte
     sa fiche — un seul à la fois. */
  let courant = null;
  let itemDetail = null;

  /* La galerie : un groupe par catégorie, toutes les fiches visibles d'un
     coup — pas de piste à faire défiler. */
  const groupesGalerie = cats.map((c) => {
    const membres = appareils.filter((a) => texte(a.categorie) === c.cle);
    return { cle: c.cle, libelle: c.libelle, membres };
  }).filter((g) => g.membres.length);
  const horsCategorie = appareils.filter((a) => !cats.some((c) => c.cle === texte(a.categorie)));
  if (horsCategorie.length) groupesGalerie.push({ cle: '', libelle: 'Autres', membres: horsCategorie });

  /* Une seule galerie, sans découpage par famille : les appareils se
     suivent (civils, militaires, prototypes, dans cet ordre) et les
     filtres du dessus font le tri. */
  const piste = el('div', { class: 'porteurs__galerie' },
    el('section', { class: 'porteurs__groupe-galerie', dataset: { categorie: '' }, 'aria-label': 'Tous les porteurs' },
      el('ul', { class: 'porteurs__grille', role: 'list' },
        groupesGalerie.flatMap((g) => g.membres).map((a) => fiche(a, prefixe)))));

  const puces = el('ul', { class: 'facettes porteurs__facettes', 'aria-label': 'Filtrer les porteurs par catégorie' },
    [{ cle: '', libelle: 'Tous' }].concat(cats).map((c) => el('li', {},
      el('button', {
        type: 'button', class: 'facette facette--compacte',
        'aria-pressed': c.cle === '' ? 'true' : 'false',
        dataset: { categorie: c.cle }
      }, c.libelle, ' ',
      el('span', { class: 'facette__compteur' },
        String(c.cle ? appareils.filter((a) => texte(a.categorie) === c.cle).length : appareils.length))))));

  const itemDe = (appareil) => piste.querySelector('.porteurs__item[data-code="' + CSS.escape(texte(appareil.code)) + '"]');

  function marquer() {
    const code = courant ? texte(courant.code) : '';
    piste.querySelectorAll('.porteurs__fiche').forEach((b) => {
      const ouvert = code !== '' && b.dataset.code === code;
      b.setAttribute('aria-pressed', ouvert ? 'true' : 'false');
      b.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
      b.closest('.porteurs__item').classList.toggle('porteurs__item--ouvert', ouvert);
    });
  }

  /**
   * Place la fiche dépliée juste sous la RANGÉE de la carte ouverte : les
   * cartes d'une même rangée visuelle partagent le même offsetTop ; la
   * fiche, sur toute la largeur, s'insère après la dernière d'entre elles.
   * Idempotent : rappelé au redimensionnement, il ne bouge rien si la
   * fiche est déjà au bon endroit.
   */
  function positionner() {
    if (!courant || !itemDetail) return;
    const item = itemDe(courant);
    if (!item) return;
    const liste = item.parentNode;
    /* La fiche déjà en place fausse la mesure : elle repousse à la ligne
       les cartes qui la suivent, qui semblent alors d'une autre rangée.
       On mesure donc hors de son flux, puis on la remet. */
    const enPlace = itemDetail.parentNode === liste;
    if (enPlace) itemDetail.hidden = true;
    const cartes = Array.from(liste.querySelectorAll('.porteurs__item:not([hidden]):not(.porteurs__item--detail)'));
    const haut = item.offsetTop;
    let dernier = item;
    for (const c of cartes) if (c.offsetTop === haut) dernier = c;
    if (enPlace) itemDetail.hidden = false;
    if (dernier.nextSibling !== itemDetail) liste.insertBefore(itemDetail, dernier.nextSibling);
  }
  const repositionner = rafThrottle(positionner);

  function replier() {
    if (itemDetail && itemDetail.parentNode) itemDetail.parentNode.removeChild(itemDetail);
    itemDetail = null;
    courant = null;
    marquer();
  }

  /* Amène la carte à l'écran quand sa fiche dépliée ne s'y voit pas. */
  function montrer(appareil, forcer) {
    const item = itemDe(appareil);
    if (!item || typeof item.scrollIntoView !== 'function') return;
    const comportement = mouvementReduit() ? 'auto' : 'smooth';
    if (forcer) { item.scrollIntoView({ block: 'start', behavior: comportement }); return; }
    const bas = itemDetail ? itemDetail.getBoundingClientRect().bottom : 0;
    const haut = item.getBoundingClientRect().top;
    const fenetre = window.innerHeight || document.documentElement.clientHeight;
    if (haut < 0 || bas > fenetre) item.scrollIntoView({ block: 'start', behavior: comportement });
  }

  function deplier(appareil, options) {
    const o = options || {};
    if (itemDetail && itemDetail.parentNode) itemDetail.parentNode.removeChild(itemDetail);
    courant = appareil;
    itemDetail = el('li', { class: 'porteurs__item porteurs__item--detail' },
      detail(appareil, d, cats, { surModifier: opts.surModifier, surSupprimer: opts.surSupprimer }));
    if (!mouvementReduit()) {
      itemDetail.dataset.etat = 'entree';
      itemDetail.addEventListener('animationend', () => { delete itemDetail.dataset.etat; }, { once: true });
    }
    marquer();
    positionner();
    montrer(appareil, Boolean(o.defiler));
  }

  function visibles() {
    return appareils.filter((a) => !categorie || texte(a.categorie) === categorie);
  }

  function filtrer() {
    const liste = visibles();
    piste.querySelectorAll('.porteurs__item:not(.porteurs__item--detail)').forEach((li) => {
      li.hidden = Boolean(categorie) && li.dataset.categorie !== categorie;
    });
    piste.querySelectorAll('.porteurs__groupe-galerie').forEach((g) => {
      g.hidden = Boolean(categorie) && g.dataset.categorie !== categorie;
    });
    if (courant && !liste.includes(courant)) replier(); else positionner();
  }

  piste.addEventListener('click', (evt) => {
    const b = evt.target.closest('.porteurs__fiche');
    if (!b) return;
    const a = appareils.find((x) => texte(x.code) === b.dataset.code);
    if (!a) return;
    if (a === courant) { replier(); annoncer('Fiche ' + b.dataset.code + ' repliée'); return; }
    deplier(a);
    annoncer('Fiche ' + b.dataset.code + ' dépliée');
  });

  /* Les flèches parcourent les cartes visibles et déplient celle qui
     reçoit le focus ; le dépliage n'est pas un bascule ici, sinon revenir
     sur la carte ouverte la fermerait. */
  piste.addEventListener('keydown', (evt) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(evt.key)) return;
    const boutons = Array.from(piste.querySelectorAll('.porteurs__item:not([hidden]):not(.porteurs__item--detail) .porteurs__fiche'));
    const i = boutons.indexOf(document.activeElement);
    if (i === -1) return;
    let j = i;
    if (evt.key === 'ArrowLeft') j = Math.max(0, i - 1);
    if (evt.key === 'ArrowRight') j = Math.min(boutons.length - 1, i + 1);
    if (evt.key === 'Home') j = 0;
    if (evt.key === 'End') j = boutons.length - 1;
    evt.preventDefault();
    boutons[j].focus();
    const a = appareils.find((x) => texte(x.code) === boutons[j].dataset.code);
    if (a && a !== courant) deplier(a);
  });

  puces.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-categorie]');
    if (!b) return;
    categorie = b.dataset.categorie || '';
    puces.querySelectorAll('[data-categorie]').forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
    filtrer();
  });

  const racine = el('section', { class: 'porteurs', id: prefixe },
    el('div', { class: 'porteurs__barre' }, puces,
      typeof opts.surAjouter === 'function' ? boutonAjouter('Ajouter un porteur', opts.surAjouter) : null),
    piste);

  /* La rangée d'une carte change avec la largeur : la fiche dépliée suit. */
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(() => repositionner()).observe(piste);
  } else if (typeof window !== 'undefined') {
    window.addEventListener('resize', repositionner);
  }

  /* Arrivée par la palette ou un lien : #porteur=CODE déplie la fiche et
     amène la carte à l'écran. */
  const suivreHash = () => {
    const demande = texte(etatUrl.lire().porteur).toUpperCase();
    if (!demande) return false;
    const a = appareils.find((x) => texte(x.code).toUpperCase() === demande);
    if (!a) return false;
    if (categorie && texte(a.categorie) !== categorie) {
      categorie = '';
      puces.querySelectorAll('[data-categorie]').forEach((x) => x.setAttribute('aria-pressed', x.dataset.categorie === '' ? 'true' : 'false'));
      filtrer();
    }
    if (a !== courant) deplier(a, { defiler: true });
    else montrer(a, true);
    return true;
  };

  filtrer();
  /* Le composant n'est pas encore dans le document : le hash se suit une
     fois monté, sinon offsetTop et scrollIntoView ne veulent rien dire. */
  setTimeout(suivreHash, 0);
  etatUrl.ecouter(suivreHash);
  return racine;
}
