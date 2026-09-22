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
import { portrait } from './portraits.js';

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

function champs(donnees, groupe) {
  const c = objet(objet(donnees.champs)[groupe]);
  const liste = Array.isArray(objet(donnees.champs)[groupe]) ? objet(donnees.champs)[groupe]
    : (Array.isArray(c.champs) ? c.champs : []);
  return liste.filter((d) => d && typeof d === 'object' && texte(d.cle))
    .map((d) => ({ cle: texte(d.cle), libelle: texte(d.libelle) || texte(d.cle), unite: texte(d.unite) }));
}

function pastillePole(code) {
  return el('span', { class: 'porteurs__pole', dataset: { pole: code } },
    el('span', { class: 'porteurs__pole-point', 'aria-hidden': 'true' }),
    'Pôle ' + code);
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
  /* L'identité longue (certificat, ancien nom) n'a pas sa place dans le
     bandeau : elle se lit ici, avec le reste de la technique. */
  { cle: 'identite', titre: 'Identité', champs: [
    ['certification', 'Certification'], ['ancienNom', 'Ancien nom']] },
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
  r.identite = Object.assign({}, r.identite || {}, Object.fromEntries(IDENTITE));
  return r;
}

/* Le bandeau d'identité : les essentiels, rien d'autre. */
const IDENTITE = [
  ['constructeur', 'Constructeur'], ['premierVol', 'Premier vol'],
  ['miseEnService', 'Mise en service'], ['siteAssemblage', 'Site d’assemblage']];

/* Pas d'onglet « Sources » : la fiche ne renvoie vers aucun site
   extérieur. Les crédits des photos, eux, restent dans la fenêtre
   « Crédits photos » du pied de page — c'est une obligation de licence. */
const ONGLETS = [
  { cle: 'technique', titre: 'Technique', groupes: ['motorisation', 'masses', 'capacite', 'dimensions', 'identite'], chiffres: true },
  { cle: 'performances', titre: 'Performances', groupes: ['performances'] },
  { cle: 'electrique', titre: 'Électrique', groupes: ['electrique'] },
  { cle: 'economie', titre: 'Production & économie', groupes: ['production'] },
  { cle: 'insolite', titre: 'Insolite' },
  { cle: 'equipe', titre: 'Équipe & documents' },
  { cle: 'service', titre: 'Données service' }
];

/* Les chiffres clés en tête de l'onglet Technique : seulement les valeurs
   que le fichier donne en nombre. */
const CHIFFRES_CLES = [
  ['masses', 'masseMaxDecollage', 'Masse max. au décollage'],
  ['motorisation', 'nombreMoteurs', 'Moteurs'],
  ['motorisation', 'puissance', 'Puissance'],
  ['capacite', 'passagers', 'Passagers'],
  ['performances', 'vitesseCroisiere', 'Vitesse de croisière'],
  ['performances', 'rayonAction', 'Rayon d’action'],
  ['dimensions', 'diametreRotor', 'Diamètre du rotor']
];

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
function ligneFiche(libelle, brut) {
  const c = champFiche(brut);
  return el('div', { class: 'porteurs__ligne' },
    el('dt', { class: 'porteurs__libelle' }, libelle),
    el('dd', { class: 'porteurs__cellule' },
      el('span', { class: ['porteurs__valeur', c.chiffre ? 'porteurs__valeur--chiffre' : null, c.ok ? null : 'porteurs__manquant'] }, c.principal),
      c.complement ? el('span', { class: 'porteurs__complement' }, c.complement) : null));
}

function groupeFiche(titre, lignes) {
  return el('section', { class: 'porteurs__groupe' },
    el('h4', { class: 'porteurs__groupe-titre' }, titre),
    el('dl', { class: 'porteurs__lignes' }, lignes));
}

/* Les chiffres clés : trois à cinq tuiles, quand le fichier les donne en
   nombre. Rien ne s'affiche s'il n'y en a pas au moins deux. */
function chiffresCles(fiche) {
  const tuiles = [];
  for (const [groupe, cle, libelle] of CHIFFRES_CLES) {
    const brut = objet(fiche[groupe])[cle];
    const c = (brut && typeof brut === 'object') ? brut : { valeur: brut };
    if (typeof c.valeur !== 'number' || !Number.isFinite(c.valeur)) continue;
    const v = valeurLisible(c.valeur, c.unite);
    const [nombre, ...unite] = v.principal.split(' ');
    tuiles.push(el('div', { class: 'porteurs__chiffre' },
      el('dt', { class: 'porteurs__chiffre-libelle' }, libelle),
      el('dd', { class: 'porteurs__chiffre-valeur' },
        el('span', { class: 'porteurs__chiffre-nombre' }, nombre),
        unite.length ? el('span', { class: 'porteurs__chiffre-unite' }, ' ' + unite.join(' ')) : null)));
    if (tuiles.length === 5) break;
  }
  return tuiles.length >= 2 ? el('dl', { class: 'porteurs__chiffres' }, tuiles) : null;
}

function tableFiche(titre, champsDuGroupe, valeurs) {
  const source = objet(valeurs);
  return groupeFiche(titre, champsDuGroupe.map(([cle, libelle]) => ligneFiche(libelle, source[cle])));
}

function panneauInsolite(fiche) {
  const faits = (Array.isArray(fiche.insolites) ? fiche.insolites : []).filter((f) => f && texte(f.texte));
  if (!faits.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucun fait remarquable renseigné.');
  return el('ul', { class: 'porteurs__insolites' }, faits.map((f) => el('li', { class: 'porteurs__insolite' },
    el('span', { class: 'porteurs__insolite-glyphe', 'aria-hidden': 'true' }, '✦'),
    el('span', {}, texte(f.texte)))));
}

function tableau(titre, descripteurs, valeurs) {
  const source = objet(valeurs);
  const lignes = descripteurs.length ? descripteurs
    : Object.keys(source).map((cle) => ({ cle, libelle: cle, unite: '' }));
  if (!lignes.length) {
    return el('section', { class: 'porteurs__groupe' },
      el('h4', { class: 'porteurs__groupe-titre' }, titre),
      el('p', { class: 'texte-doux texte-sm sans-marge' }, 'Aucun champ déclaré.'));
  }
  return groupeFiche(titre, lignes.map((d) => ligneFiche(d.libelle, { valeur: source[d.cle], unite: d.unite })));
}

/**
 * L'équipe et les documents rattachés à ce porteur.
 *
 * Le lien se fait sur le périmètre : une personne dont le périmètre vaut
 * « H160 » travaille sur le H160, un document de périmètre « H160 » le
 * concerne. Les entrées « Transverse » ne sont pas rattachées à un
 * porteur : elles n'apparaissent donc pas ici.
 *
 * @param {object} appareil
 * @param {{equipe?: object, documents?: object}} contexte
 * @returns {Node}
 */
function panneauEquipe(appareil, contexte) {
  const code = texte(appareil.code);
  const ctx = objet(contexte);

  const gens = [];
  const ajouter = (p, pole, squad) => {
    if (p && typeof p === 'object' && texte(p.perimetre) === code) {
      gens.push({ id: texte(p.id), nom: texte(p.nom), poste: texte(p.poste), photo: texte(p.photo), pole, squad });
    }
  };
  const orga = objet(ctx.equipe);
  ajouter(orga.direction, 'ETII', '');
  for (const pole of (Array.isArray(orga.poles) ? orga.poles : [])) {
    ajouter(pole && pole.responsable, texte(pole && pole.pole), '');
    for (const squad of (Array.isArray(pole && pole.squads) ? pole.squads : [])) {
      for (const m of (Array.isArray(squad && squad.membres) ? squad.membres : [])) {
        ajouter(m, texte(pole.pole), texte(squad.nom));
      }
    }
  }

  const documents = (Array.isArray(objet(ctx.documents).documents) ? ctx.documents.documents : [])
    .filter((d) => d && texte(d.perimetre) === code);

  const bloc = (titre, contenu) => el('section', { class: 'porteurs__groupe' },
    el('h4', { class: 'porteurs__groupe-titre' }, titre),
    contenu);

  return el('div', { class: 'porteurs__groupes' },
    bloc('Qui travaille dessus', gens.length
      ? el('ul', { class: 'porteurs__equipe', role: 'list' }, gens.map((g) => el('li', {},
          /* data-pole donne au portrait la teinte du pôle (modules.css §11). */
          el('a', { class: 'porteurs__personne', dataPole: g.pole, href: 'organigramme.html#pole=' + encodeURIComponent(g.pole) + '&personne=' + encodeURIComponent(g.id) },
            portrait(g),
            el('span', { class: 'porteurs__personne-infos' },
              el('span', { class: 'porteurs__personne-nom' }, g.nom),
              el('span', { class: 'porteurs__personne-poste' }, g.poste),
              el('span', { class: 'porteurs__personne-pole mono' }, [g.pole, g.squad].filter(Boolean).join(' · ')))))))
      : el('p', { class: 'texte-doux texte-sm sans-marge' }, 'Personne n’a ce porteur pour périmètre dans l’organigramme.')),
    bloc('Documents concernés', documents.length
      ? el('ul', { class: 'porteurs__documents', role: 'list' }, documents.slice(0, 15).map((d) => el('li', {},
          el('a', { class: 'porteurs__document', href: 'docsearch.html#q=' + encodeURIComponent(texte(d.reference) || texte(d.titre)) },
            el('span', {}, texte(d.titre)),
            el('span', { class: 'porteurs__document-meta mono' }, [texte(d.type), texte(d.reference)].filter(Boolean).join(' · '))))))
      : el('p', { class: 'texte-doux texte-sm sans-marge' }, 'Aucun document du fonds n’a ce porteur pour périmètre.')));
}

function panneauService(appareil, donnees) {
  const service = objet(appareil.service);
  const technique = ('technique' in service) ? service.technique : appareil.technique;
  const economique = ('economique' in service) ? service.economique : appareil.economique;
  return el('div', { class: 'pile' },
    el('p', { class: 'texte-doux texte-sm sans-marge mesure' },
      'Les données propres au service (harnais, connecteurs, charge, coûts) ne sont jamais '
      + 'inventées : elles restent « à renseigner » tant que le fichier ne les donne pas.'),
    el('div', { class: 'porteurs__groupes' },
      /* Le jalon et l'avancement sont des données du service : ils se
         lisent ici, pas dans le bandeau, tant qu'ils sont vides. */
      tableau('Suivi', [{ cle: 'jalon', libelle: 'Jalon en cours', unite: '' }, { cle: 'avancement', libelle: 'Avancement', unite: '%' }],
        { jalon: appareil.jalon, avancement: appareil.avancement }),
      tableau('Données techniques du service', champs(donnees, 'technique'), technique),
      tableau('Données économiques du service', champs(donnees, 'economique'), economique)));
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

/* La carte d'identité : le nom complet, la catégorie et le segment, le
   statut, les pôles, puis l'identité (constructeur, premier vol, mise en
   service, site d'assemblage). Les mêmes lignes que les groupes de la
   fiche — libellé à gauche, valeur à côté, précision dessous — sur deux
   colonnes quand la place le permet. */
function bandeauIdentite(appareil, fiche, avecFiche, categorie) {
  const identite = objet(fiche.identite);
  const code = texte(appareil.code) || '—';
  const poles = Array.isArray(appareil.poles) ? appareil.poles.map(texte).filter(Boolean) : [];
  const nom = texte(fiche.nom);
  const segment = texte(appareil.segment) || texte(fiche.segment);
  const libelleCategorie = categorie ? categorie.libelle : texte(appareil.categorie);
  const categorieSegment = [libelleCategorie, segment].filter(Boolean).join(' · ');
  return el('section', { class: 'porteurs__identite', 'aria-label': 'Identité du ' + code },
    el('dl', { class: 'porteurs__lignes porteurs__lignes--identite' },
      ligneFiche('Nom', nom || code),
      ligneFiche('Catégorie', categorieSegment),
      ligneFiche('Statut', avecFiche ? texte(fiche.statut) : ''),
      el('div', { class: 'porteurs__ligne' },
        el('dt', { class: 'porteurs__libelle' }, 'Pôles'),
        el('dd', { class: 'porteurs__cellule porteurs__poles' }, poles.length ? poles.map(pastillePole)
          : el('span', { class: 'porteurs__manquant' }, NON_RENSEIGNE))),
      IDENTITE.map(([cle, libelle]) => ligneFiche(libelle, identite[cle]))));
}

function detail(appareil, donnees, categoriesConnues, contexte) {
  const code = texte(appareil.code) || '—';
  const fiche = objet(appareil.fiche);
  const avecFiche = Object.keys(fiche).length > 0;
  const photo = texte(appareil.photo);
  const categorie = categoriesConnues.find((c) => c.cle === texte(appareil.categorie));
  const prefixe = 'porteur-' + code.toLowerCase().replace(/[^a-z0-9]+/g, '-');

  /* Les valeurs de l'onglet Technique : les groupes de la fiche, plus
     l'identité longue (certificat, ancien nom) rapatriée ici. */
  const valeursGroupe = (cle) => cle === 'identite'
    ? { certification: objet(fiche.identite).certification, ancienNom: fiche.ancienNom }
    : fiche[cle];

  const panneaux = ONGLETS.map((o) => {
    if (o.groupes) {
      const groupes = o.groupes.map((g) => GROUPES_FICHE.find((x) => x.cle === g)).filter(Boolean);
      return { cle: o.cle, titre: o.titre,
        contenu: avecFiche
          ? el('div', { class: 'porteurs__panneau' },
              o.chiffres ? chiffresCles(fiche) : null,
              el('div', { class: 'porteurs__groupes' }, groupes.map((g) => tableFiche(g.titre, g.champs, valeursGroupe(g.cle)))))
          : el('p', { class: 'texte-doux sans-marge' }, 'Fiche publique non encore constituée pour ce porteur.') };
    }
    if (o.cle === 'insolite') return { cle: o.cle, titre: o.titre, contenu: panneauInsolite(fiche) };
    if (o.cle === 'equipe') return { cle: o.cle, titre: o.titre, contenu: panneauEquipe(appareil, contexte) };
    return { cle: o.cle, titre: o.titre, contenu: panneauService(appareil, donnees) };
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
      bandeauIdentite(appareil, fiche, avecFiche, categorie),
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
 * @param {{id?: string, equipe?: object, documents?: object,
 *          surAjouter?: Function, surModifier?: Function, surSupprimer?: Function}} [options]
 *   `equipe` est organigramme.json et `documents` documents.json : ils
 *   servent à relier le porteur à ceux qui travaillent dessus. Les trois
 *   commandes d'édition ne se voient qu'en mode édition (edition.js).
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

  const piste = el('div', { class: 'porteurs__galerie' }, groupesGalerie.map((g) =>
    el('section', { class: 'porteurs__groupe-galerie', dataset: { categorie: g.cle }, 'aria-label': g.libelle },
      el('h3', { class: 'porteurs__groupe-galerie-titre' },
        el('span', { class: 'porteurs__groupe-galerie-nom' }, g.libelle),
        el('span', { class: 'mono porteurs__groupe-galerie-compte' }, String(g.membres.length))),
      el('ul', { class: 'porteurs__grille', role: 'list' }, g.membres.map((a) => fiche(a, prefixe))))));

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
      detail(appareil, d, cats, { equipe: opts.equipe, documents: opts.documents, surModifier: opts.surModifier, surSupprimer: opts.surSupprimer }));
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
