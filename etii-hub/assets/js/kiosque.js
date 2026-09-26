/* =========================================================================
   ETII Hub — Le kiosque de communication
   Le « Communication Center » du service : un bandeau d'alertes qui
   défile, puis deux panneaux côte à côte — à gauche la frise de tout ce
   qui a été communiqué (la plus récente d'abord, par mois, le long d'un
   rail), à droite la lecture de la communication choisie. Une
   communication est composée de BLOCS libres, dans l'ordre voulu par son
   auteur : texte (écrit ligne à ligne), image, galerie, chiffres clés,
   courbe, pastilles, encadré ; une marque de fin ferme la lecture. On ne
   montre que ce qui a été dit : l'agenda à venir n'est pas de la
   communication.

   Les deux panneaux ont la même hauteur, et c'est la lecture qui la
   donne : un ResizeObserver la recopie sur la liste, qui défile dans sa
   fenêtre. Rien n'est jamais coupé ni ne déborde sur la section suivante.

   Rien n'est inventé : chaque entrée vient du fichier, de la feuille de
   publication ou de l'éditeur (editeur.js). Tout le DOM est construit
   avec el() — aucun innerHTML, aucun gestionnaire en attribut.
   ========================================================================= */

import { el, monter, mouvementReduit, annoncer, etatUrl } from './ui.js';
import { barreEdition, boutonAjouter } from './edition.js';
import { sparkline } from './indicateurs.js';

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                     'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

/* Libellé humain des types d'entrée d'agenda : de la matière éditoriale,
   pas de la donnée. Un type inconnu est affiché tel quel. */
export const TYPES_AGENDA = {
  jalon: 'Jalon', revue: 'Revue', atelier: 'Atelier', reunion: 'Réunion', formation: 'Formation',
  evenement: 'Événement', mot: 'Édito', succes: 'Succès', alerte: 'Alerte', info: 'Information'
};

const STATUTS = {
  succes: { libelle: 'Validé', classe: 'badge--succes' },
  urgent: { libelle: 'Urgent', classe: 'badge--alerte' },
  info:   { libelle: 'Information', classe: 'badge--info' },
  mot:    { libelle: 'Direction', classe: 'badge--accent' }
};

/* Glyphe posé devant chaque ligne du corps, selon son type. C'est le
   vocabulaire du formulaire d'origine : « ! » alerte, « V » validé,
   « -> » titre, « • » puce. */
const GLYPHES = {
  titre: '→', puce: '•', valide: '✓', alerte: '⚠', texte: '', vide: ''
};

const TENDANCES = {
  hausse: { glyphe: '↗', libelle: 'en hausse' },
  baisse: { glyphe: '↘', libelle: 'en baisse' },
  stable: { glyphe: '→', libelle: 'stable' }
};

/** Les types de bloc connus et leur libellé humain (l'éditeur les liste). */
export const TYPES_BLOC = {
  texte: 'Texte', image: 'Image', galerie: 'Galerie', chiffres: 'Chiffres clés',
  courbe: 'Courbe', pastilles: 'Pastilles', encadre: 'Encadré'
};

const TONS_ENCADRE = ['info', 'succes', 'alerte'];

/* La mise en page d'un bloc : sa largeur dans la grille de six colonnes de
   la lecture, et le côté où il se cale. 'pleine' et '' (dans le flux) sont
   les valeurs par défaut ; tout autre mot est ramené à elles. */
export const LARGEURS_BLOC = ['pleine', 'deux-tiers', 'moitie', 'tiers'];
export const COTES_BLOC = ['', 'gauche', 'droite'];

function miseEnPage(brut, bloc) {
  if (!bloc) return null;
  const largeur = texte(brut.largeur);
  const cote = texte(brut.cote);
  bloc.largeur = LARGEURS_BLOC.includes(largeur) ? largeur : 'pleine';
  bloc.cote = COTES_BLOC.includes(cote) ? cote : '';
  return bloc;
}

/* -------------------------------------------------------------------------
   1. Lecture prudente
   ------------------------------------------------------------------------- */

function texte(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return String(valeur).trim();
}

function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : null; }

function partiesDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  if (!m) return null;
  const annee = Number(m[1]); const mois = Number(m[2]); const jour = Number(m[3]);
  if (mois < 1 || mois > 12 || jour < 1 || jour > 31) return null;
  return { annee, mois, jour };
}

/** « 12 sept. 2026 » — la date courte, en mono. */
export function dateCourte(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_COURTS[p.mois - 1]} ${p.annee}`;
}

/** « 12 septembre 2026 » — la date longue de la lecture. */
export function dateLongue(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_LONGS[p.mois - 1]} ${p.annee}`;
}

/** « Septembre 2026 » — l'intitulé de groupe de la liste. */
function moisLong(iso) {
  const p = partiesDate(iso);
  if (!p) return 'Sans date';
  const m = MOIS_LONGS[p.mois - 1];
  return m[0].toUpperCase() + m.slice(1) + ' ' + p.annee;
}

function aujourdhui() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/* La clé de dédoublonnage d'une entrée : sa date et son titre, casse et
   accents ôtés. Le même événement saisi deux fois ne se lit qu'une fois. */
function cleEntree(date, titre) {
  return texte(date) + '|' + texte(titre).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

/** Jours restants jusqu'à la date, ou null si elle est illisible. */
export function joursRestants(iso) {
  const p = partiesDate(iso);
  if (!p) return null;
  const cible = new Date(p.annee, p.mois - 1, p.jour);
  return Math.round((cible - aujourdhui()) / 86400000);
}

/* Les nombres s'écrivent à la française : espace fine des milliers,
   virgule décimale. Une valeur illisible est rendue telle quelle. */
function nombreLisible(v) {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  }
  return texte(v);
}

/* -------------------------------------------------------------------------
   2. De communications.json aux dossiers du kiosque
   ------------------------------------------------------------------------- */

/**
 * Le corps d'une annonce : un tableau de lignes typées. Une chaîne est
 * découpée sur les retours à la ligne ; chaque ligne garde son type.
 * @param {*} brut
 * @returns {Array<{type:string, texte:string}>}
 */
function lignesDepuis(brut) {
  if (Array.isArray(brut)) {
    return brut
      .filter((l) => l && typeof l === 'object')
      .map((l) => ({ type: GLYPHES[l.type] !== undefined ? l.type : 'texte',
                     texte: texte(l.texte) }));
  }
  const t = texte(brut);
  if (!t) return [];
  return t.split('\n').map((l) => ({ type: l.trim() ? 'texte' : 'vide', texte: l.trim() }));
}

/** Une image : { src, alt, legende } ou null. */
function imageDepuis(brut) {
  const o = objet(brut);
  if (!o) return null;
  const src = texte(o.src);
  /* Une URL publique, un fichier du site, ou l'image intégrée par la
     version autonome (data:) — rien d'autre. */
  if (!/^(https:\/\/|assets\/|data:image\/)/.test(src)) return null;
  const credit = objet(o.credit);
  return { src, alt: texte(o.alt), legende: texte(o.legende),
    credit: credit ? { auteur: texte(credit.auteur), licence: texte(credit.licence), page: texte(credit.page) } : null };
}

/** Les chiffres clés : au plus quatre tuiles { libelle, valeur, unite, tendance }. */
function chiffresDepuis(brut) {
  if (!Array.isArray(brut)) return [];
  return brut
    .map(objet).filter(Boolean)
    .filter((c) => texte(c.libelle) && (typeof c.valeur === 'number' || texte(c.valeur)))
    .slice(0, 4)
    .map((c) => ({
      libelle: texte(c.libelle),
      valeur: typeof c.valeur === 'number' ? c.valeur : texte(c.valeur),
      unite: texte(c.unite),
      tendance: TENDANCES[texte(c.tendance)] ? texte(c.tendance) : ''
    }));
}

/** Une petite série mensuelle : { libelle, mois[], valeurs[], unite } ou null. */
function serieDepuis(brut) {
  const o = objet(brut);
  if (!o || !Array.isArray(o.valeurs) || !o.valeurs.length) return null;
  const valeurs = o.valeurs.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null));
  if (!valeurs.some((v) => v !== null)) return null;
  const mois = Array.isArray(o.mois) ? o.mois.map(texte) : [];
  return { libelle: texte(o.libelle) || 'Série', mois, valeurs, unite: texte(o.unite) };
}

/**
 * Normalise un bloc : un objet { type, … } propre, ou null s'il est vide.
 * @param {*} brut
 */
export function blocDepuis(brut) {
  const b = objet(brut);
  if (!b) return null;
  return miseEnPage(b, blocSansMiseEnPage(b));
}

function blocSansMiseEnPage(b) {
  const type = texte(b.type);
  switch (type) {
    case 'texte': {
      const lignes = lignesDepuis(b.lignes !== undefined ? b.lignes : b.texte);
      return lignes.length ? { type, lignes } : null;
    }
    case 'image': {
      const image = imageDepuis(b.src !== undefined ? b : b.image);
      return image ? Object.assign({ type }, image) : null;
    }
    case 'galerie': {
      const images = (Array.isArray(b.images) ? b.images : []).map(imageDepuis).filter(Boolean);
      return images.length ? { type, images } : null;
    }
    case 'chiffres': {
      const chiffres = chiffresDepuis(b.chiffres);
      return chiffres.length ? { type, chiffres } : null;
    }
    case 'courbe': {
      const serie = serieDepuis(b.serie || b);
      return serie ? { type, serie } : null;
    }
    case 'pastilles': {
      const pastilles = (Array.isArray(b.pastilles) ? b.pastilles : texte(b.pastilles).split(/\s*[;,]\s*/))
        .map(texte).filter(Boolean).slice(0, 12);
      return pastilles.length ? { type, pastilles } : null;
    }
    case 'encadre': {
      const t = texte(b.texte);
      return t ? { type, ton: TONS_ENCADRE.includes(texte(b.ton)) ? texte(b.ton) : 'info', titre: texte(b.titre), texte: t } : null;
    }
    default:
      return null;
  }
}

/**
 * Les blocs d'une entrée. Une entrée écrite avant les blocs (image,
 * chiffres, serie, corps à plat) est convertie dans le même ordre que
 * l'ancien rendu : image, chiffres, courbe, texte.
 * @param {object} e
 * @returns {Array<object>}
 */
export function blocsDepuis(e) {
  if (Array.isArray(e.blocs)) return e.blocs.map(blocDepuis).filter(Boolean);
  const blocs = [];
  const image = imageDepuis(e.image);
  if (image) blocs.push(Object.assign({ type: 'image' }, image));
  const chiffres = chiffresDepuis(e.chiffres);
  if (chiffres.length) blocs.push({ type: 'chiffres', chiffres });
  const serie = serieDepuis(e.serie);
  if (serie) blocs.push({ type: 'courbe', serie });
  const lignes = lignesDepuis(e.corps);
  if (lignes.length) blocs.push({ type: 'texte', lignes });
  return blocs;
}

function dossierDepuis(e, base) {
  const blocs = blocsDepuis(e);
  return Object.assign({
    date: texte(e.date),
    titre: texte(e.titre),
    resume: texte(e.resume),
    pole: texte(e.pole).toUpperCase() || 'ETII',
    blocs,
    /* Repères pour la liste : y a-t-il une image, des chiffres ? */
    avecImage: blocs.some((b) => b.type === 'image' || b.type === 'galerie'),
    avecChiffres: blocs.some((b) => b.type === 'chiffres' || b.type === 'courbe'),
    /* Le jeu d'exemple du dépôt porte ce drapeau : la mention se pose une
       fois, au niveau de l'entrée, au lieu d'être écrite dans la prose. */
    exemple: e.exemple === true
  }, base);
}

/**
 * Construit la liste des dossiers du kiosque à partir de communications.json.
 *
 * - le mot du chef en premier (seulement au niveau service) ;
 * - puis l'historique : annonces et agenda passé, du plus récent au plus
 *   ancien. L'agenda à venir est ignoré : on communique sur ce qui s'est
 *   passé. Un même événement saisi deux fois (annonce et agenda, même titre
 *   à la même date) ne compte qu'une fois : l'annonce, qui porte le texte.
 *
 * @param {object} donnees  contenu de communications.json
 * @param {{pole?: string, serviceSeul?: boolean}} [options]  code de pôle ;
 *   absent ou 'ETII' : tout le service. serviceSeul : au niveau service,
 *   seulement les communications du service lui-même (pas celles des pôles).
 * @returns {Array<object>}
 */
export function dossiersDepuisCommunications(donnees, options) {
  const opts = options || {};
  const pole = texte(opts.pole).toUpperCase();
  const niveauService = !pole || pole === 'ETII';
  const garder = (entree) => {
    const sien = texte(entree.pole).toUpperCase() || 'ETII';
    if (!niveauService) return sien === pole;
    return !opts.serviceSeul || sien === 'ETII';
  };

  const dossiers = [];
  const d = (donnees && typeof donnees === 'object') ? donnees : {};

  /* La déduplication commence au dossier du mot : un édito rétrogradé en
     annonce (voir versAnnonceEdito) ne doit pas se lire deux fois, en
     vedette puis dans la frise. */
  const vus = new Set();

  const mot = objet(d.motDuChef);
  if (mot && niveauService && texte(mot.titre)) {
    dossiers.push(dossierDepuis(mot, {
      id: 'mot-du-chef', groupe: 'mot', programme: 'Service ETII', statut: 'mot', pole: 'ETII',
      source: { type: 'edito', id: texte(mot.id) || 'mot-du-chef', entree: mot }
    }));
    vus.add(cleEntree(mot.date, mot.titre));
  }

  const agenda = Array.isArray(d.agenda) ? d.agenda.filter((e) => e && typeof e === 'object') : [];
  const annonces = Array.isArray(d.annonces) ? d.annonces.filter((e) => e && typeof e === 'object') : [];

  /* Écarté par la DATE, et pas seulement par le statut : une faute de frappe
     sur l'année (2062 pour 2026) épinglait sinon la communication juste sous
     l'édito pour toujours, et coupait la frise en deux. Une date illisible
     passe : la carte « Sans date » vaut mieux qu'une disparition muette. */
  const passee = (e) => {
    const j = joursRestants(e.date);
    return j === null || j <= 0;
  };

  const historique = [
    ...annonces.filter((e) => garder(e) && passee(e)).map((e) => dossierDepuis(e, {
      id: 'annonce-' + texte(e.id),
      groupe: 'historique',
      programme: texte(e.categorie) || 'Général',
      statut: STATUTS[texte(e.statut)] ? texte(e.statut) : 'info',
      /* Un édito rétrogradé dans la frise reste un édito : on le modifie
         comme tel. */
      source: { type: e.typeSource === 'edito' ? 'edito' : 'annonce', id: texte(e.id), entree: e }
    })),
    ...agenda
      .filter((e) => texte(e.statut) !== 'a-venir' && texte(e.type) !== 'mot' && garder(e) && passee(e))
      .map((e) => dossierDepuis(Object.assign({}, e, { corps: e.corps || e.resume }), {
        id: 'agenda-' + texte(e.id),
        groupe: 'historique',
        programme: TYPES_AGENDA[texte(e.type)] || texte(e.type) || 'Agenda',
        statut: STATUTS[texte(e.type)] ? texte(e.type) : 'info',
        source: { type: 'agenda', id: texte(e.id), entree: e }
      }))
  ].sort((a, b) => b.date.localeCompare(a.date));

  const uniques = historique.filter((x) => {
    const cle = cleEntree(x.date, x.titre);
    if (vus.has(cle)) return false;
    vus.add(cle);
    return true;
  });

  return dossiers.concat(uniques);
}

/**
 * La ligne d'avertissement à poser sous le titre de la section
 * Communication, ou null s'il n'y a rien à dire. Deux cas seulement, et
 * jamais en configuration de démonstration (aucune feuille branchée) :
 * la feuille est injoignable, ou elle a été lue mais des lignes n'ont pas
 * pu l'être. Le second nomme le REMÈDE : c'est ce qui permet au chef d'agir
 * seul au lieu d'ouvrir la console.
 *
 * @param {object} donnees  le retour de chargerCommunications()
 * @returns {HTMLElement|null}
 */
export function noteOrigine(donnees) {
  const d = objet(donnees);
  if (!d) return null;
  const ligne = (t) => el('p', { class: 'kiosque-note texte-sm texte-doux', role: 'note' }, t);
  if (d.echecFeuille === true) {
    return ligne('Feuille du service injoignable : voici la dernière version embarquée.');
  }
  const ecartees = Number(d.ecartees) || 0;
  if (ecartees > 0) {
    return ligne(ecartees === 1
      ? 'Une ligne de la feuille n\u2019a pas été lue : la colonne date doit être au format AAAA-MM-JJ.'
      : ecartees + ' lignes de la feuille n\u2019ont pas été lues : la colonne date doit être au format AAAA-MM-JJ.');
  }
  return null;
}

/** Les alertes en cours, sous forme de chaînes. */
export function alertesDepuisCommunications(donnees) {
  const d = (donnees && typeof donnees === 'object') ? donnees : {};
  return (Array.isArray(d.alertes) ? d.alertes : []).map(texte).filter(Boolean);
}

/* -------------------------------------------------------------------------
   3. Le bandeau d'alertes
   ------------------------------------------------------------------------- */

/** Le bandeau seul, pour l'aperçu de l'éditeur. */
export function apercuAlertes(alertes) { return bandeauAlertes(Array.isArray(alertes) ? alertes : []); }

function bandeauAlertes(alertes, surAlertes) {
  /* Sans alerte, le bandeau n'existe pas ; en mode édition, un bouton
     permet d'en écrire une. */
  if (!alertes.length) {
    return typeof surAlertes === 'function'
      ? el('div', { class: 'kiosque__alertes-vide edition-seulement' }, boutonAjouter('Ajouter une alerte', surAlertes))
      : null;
  }
  /* Une ligne qui défile : la piste porte deux fois la liste, et glisser
     d'une demi-piste ramène exactement au départ — la boucle est sans
     couture. La copie est cachée aux lecteurs d'écran, qui lisent la
     liste une fois. Sous « mouvement réduit », la feuille arrête tout et
     masque la copie : les messages s'écrivent alors sur plusieurs lignes. */
  const liste = (copie) => el('ul', {
    class: ['kiosque__alertes-liste', copie ? 'kiosque__alertes-liste--copie' : null],
    'aria-hidden': copie ? 'true' : null
  }, alertes.map((a) => el('li', { class: 'kiosque__alerte' }, a)));

  /* Le survol arrête le défilement ; au doigt et au clavier, il faut un
     bouton : un texte qui bouge plus de cinq secondes doit pouvoir être
     arrêté (WCAG 2.2.2), et c'est le seul moyen de lire une alerte longue
     sur un téléphone. */
  const racine = el('div', { class: 'kiosque__alertes', role: 'region', 'aria-label': 'Alertes en cours' });
  const pause = el('button', {
    type: 'button', class: 'kiosque__alertes-pause',
    'aria-pressed': 'false', 'aria-label': 'Mettre le défilement en pause', title: 'Mettre en pause'
  }, el('span', { 'aria-hidden': 'true' }, '❚❚'));
  pause.addEventListener('click', () => {
    const arrete = pause.getAttribute('aria-pressed') !== 'true';
    pause.setAttribute('aria-pressed', arrete ? 'true' : 'false');
    pause.title = arrete ? 'Reprendre le défilement' : 'Mettre en pause';
    monter(pause, el('span', { 'aria-hidden': 'true' }, arrete ? '▶' : '❚❚'));
    racine.classList.toggle('kiosque__alertes--pause', arrete);
  });

  const modifier = typeof surAlertes === 'function'
    ? el('button', { type: 'button', class: 'kiosque__alertes-modifier edition-seulement', 'aria-label': 'Modifier les alertes', title: 'Modifier les alertes',
        onClick: (evt) => surAlertes(evt.currentTarget) }, el('span', { 'aria-hidden': 'true' }, '✎'))
    : null;

  return monter(racine,
    el('span', { class: 'kiosque__alertes-etiquette' },
      el('span', { class: 'kiosque__alertes-point', 'aria-hidden': 'true' }),
      alertes.length > 1 ? 'Alertes' : 'Alerte'),
    el('div', { class: 'kiosque__alertes-fenetre' },
      el('div', { class: 'kiosque__alertes-piste' }, liste(false), liste(true))),
    pause, modifier);
}

/* -------------------------------------------------------------------------
   4. La liste (à gauche) : par mois, la plus récente d'abord
   ------------------------------------------------------------------------- */

/* Une communication dans la liste : un carré à gauche — sa photo, avec
   le jour posé dessus, ou à défaut une tuile au jour et au mois —, puis
   la date en petites capitales, le titre et une ligne de résumé. */
function carteListe(dossier, prefixe) {
  const p = partiesDate(dossier.date);
  const image = premiereImage(dossier);
  const jour = el('span', { class: 'kiosque__jour' }, p ? String(p.jour) : '—');
  const mois = el('span', { class: 'kiosque__mois' }, p ? MOIS_COURTS[p.mois - 1] : '');
  const visuel = el('span', { class: ['kiosque__visuel', image ? 'kiosque__visuel--photo' : null], 'aria-hidden': 'true' },
    image
      ? el('img', { class: 'kiosque__vignette', src: image, alt: '', loading: 'lazy', decoding: 'async',
          onError: (evt) => { const v = evt.currentTarget.parentNode; evt.currentTarget.remove(); if (v) v.classList.remove('kiosque__visuel--photo'); } })
      : null,
    el('span', { class: 'kiosque__quand' }, jour, mois));
  return el('li', {
    class: 'kiosque__entree',
    dataset: { pole: dossier.pole || 'ETII', statut: STATUTS[dossier.statut] ? dossier.statut : 'info' }
  },
    el('button', {
      type: 'button',
      class: 'kiosque__carte',
      id: prefixe + '-entree-' + dossier.id,
      dataset: { id: dossier.id },
      'aria-current': 'false'
    },
    visuel,
    el('span', { class: 'kiosque__carte-corps' },
      el('time', { class: 'kiosque__carte-date', datetime: dossier.date || null }, dateLongue(dossier.date)),
      el('span', { class: 'kiosque__carte-titre' }, dossier.titre || 'Sans titre'),
      dossier.resume ? el('span', { class: 'kiosque__carte-resume' }, dossier.resume) : null)));
}

/* La liste, par mois : le libellé du mois en en-tête collant, puis les
   communications du mois, la plus récente d'abord. */
function liste(dossiers, prefixe) {
  const enfants = [];
  let moisCourant = null;
  for (const d of dossiers) {
    const m = moisLong(d.date);
    if (m !== moisCourant) {
      moisCourant = m;
      enfants.push(el('li', { class: 'kiosque__groupe', role: 'presentation' }, m));
    }
    enfants.push(carteListe(d, prefixe));
  }
  return el('ol', { class: 'kiosque__liste', role: 'list' }, enfants);
}

/* -------------------------------------------------------------------------
   5. Les blocs et la machine à écrire
   ------------------------------------------------------------------------- */

function ligneCorps(ligne) {
  if (ligne.type === 'vide') return el('div', { class: 'kiosque__ligne kiosque__ligne--vide' });
  const glyphe = GLYPHES[ligne.type] || '';
  return el('p', { class: ['kiosque__ligne', 'kiosque__ligne--' + ligne.type] },
    glyphe ? el('span', { class: 'kiosque__glyphe', 'aria-hidden': 'true' }, glyphe) : null,
    el('span', { class: 'kiosque__ligne-texte', dataset: { texte: ligne.texte } }, ''));
}

/**
 * Écrit les lignes une à une, mot par mot. Sous « mouvement réduit », tout
 * s'affiche d'un coup. Renvoie une fonction qui termine l'écriture.
 */
function machineAEcrire(conteneur, curseur) {
  const spans = Array.from(conteneur.querySelectorAll('.kiosque__ligne-texte'));
  const textes = spans.map((s) => s.dataset.texte || '');
  let annule = false;
  let minuteur = 0;

  const terminer = () => {
    annule = true;
    clearTimeout(minuteur);
    spans.forEach((s, i) => { s.textContent = textes[i]; });
    if (curseur) curseur.hidden = true;
  };

  if (mouvementReduit() || !spans.length) { terminer(); return terminer; }

  let i = 0; let c = 0;
  if (curseur) curseur.hidden = false;
  const pas = () => {
    if (annule) return;
    if (i >= spans.length) { if (curseur) curseur.hidden = true; return; }
    const cible = textes[i];
    if (c < cible.length) {
      const suivant = cible.indexOf(' ', c + 1);
      c = suivant === -1 ? cible.length : suivant;
      spans[i].textContent = cible.slice(0, c);
      minuteur = setTimeout(pas, 18);
    } else {
      i += 1; c = 0;
      minuteur = setTimeout(pas, 70);
    }
  };
  pas();
  return terminer;
}

/* Les chiffres clés : une tuile par chiffre, la valeur en grand. */
function blocChiffres(chiffres) {
  return el('ul', { class: 'kiosque__chiffres', role: 'list', 'aria-label': 'Chiffres clés' },
    chiffres.map((c) => {
      const t = TENDANCES[c.tendance];
      return el('li', { class: 'kiosque__chiffre' },
        el('span', { class: 'kiosque__chiffre-valeur mono' },
          nombreLisible(c.valeur),
          c.unite ? el('span', { class: 'kiosque__chiffre-unite' }, ' ' + c.unite) : null),
        el('span', { class: 'kiosque__chiffre-libelle' }, c.libelle),
        t ? el('span', { class: ['kiosque__chiffre-tendance', 'kiosque__chiffre-tendance--' + c.tendance] },
              el('span', { 'aria-hidden': 'true' }, t.glyphe), ' ', t.libelle) : null);
    }));
}

/* La série : la courbe validée d'indicateurs.js, avec son libellé, sa
   première et sa dernière valeur — assez pour lire une tendance. */
function blocSerie(serie) {
  const premiere = serie.valeurs.find((v) => v !== null);
  const derniere = serie.valeurs.slice().reverse().find((v) => v !== null);
  const debut = serie.mois[0] ? dateCourte(serie.mois[0] + '-01').replace(/^1 /, '') : '';
  const fin = serie.mois[serie.mois.length - 1] ? dateCourte(serie.mois[serie.mois.length - 1] + '-01').replace(/^1 /, '') : '';
  return el('figure', { class: 'kiosque__serie' },
    el('figcaption', { class: 'kiosque__serie-tete' },
      el('span', { class: 'kiosque__serie-libelle' }, serie.libelle),
      el('span', { class: 'kiosque__serie-bornes mono' },
        nombreLisible(premiere), serie.unite ? ' ' + serie.unite : '', ' → ',
        el('strong', {}, nombreLisible(derniere), serie.unite ? ' ' + serie.unite : ''))),
    sparkline(serie.valeurs, { couleur: 'var(--accent)' }),
    debut || fin ? el('span', { class: 'kiosque__serie-periode mono' }, debut, ' – ', fin) : null);
}

/* Une image introuvable ne laisse jamais d'icône cassée : l'absence se met
   en mots. L'adresse d'une photo est souvent distante (l'éditeur invite une
   URL) et un réseau qui filtre l'extérieur casserait l'en-tête pour tous
   les lecteurs d'un coup. */
function ligneImageAbsente() {
  return el('p', { class: 'kiosque__ligne texte-doux' }, 'Image introuvable à cette adresse.');
}

/* Une image dans le fil du texte : sa légende sous elle, jamais dessus. */
function blocImage(image) {
  const figure = el('figure', { class: 'kiosque__figure' },
    el('img', { src: image.src, alt: image.alt, loading: 'lazy', decoding: 'async',
      onError: () => figure.replaceWith(ligneImageAbsente()) }),
    image.legende ? el('figcaption', {}, image.legende) : null);
  return figure;
}

/* La galerie : des diapositives qu'on fait défiler, avec leurs repères. */
function blocGalerie(images) {
  const piste = el('div', { class: 'kiosque__galerie-piste', tabIndex: 0, role: 'group', 'aria-label': 'Galerie de ' + images.length + ' images' },
    images.map((img, i) => {
      /* La diapositive reste dans la piste, avec son rang : c'est lui que
         les boutons et les points de repère suivent. */
      const diapo = el('figure', { class: 'kiosque__diapo', dataset: { rang: String(i) } },
        el('img', { src: img.src, alt: img.alt, loading: 'lazy', decoding: 'async',
          onError: () => monter(diapo, ligneImageAbsente()) }),
        img.legende ? el('figcaption', {}, img.legende) : null);
      return diapo;
    }));
  const points = el('div', { class: 'kiosque__galerie-points', 'aria-hidden': 'true' },
    images.map((_i, i) => el('span', { class: ['kiosque__galerie-point', i === 0 ? 'kiosque__galerie-point--actif' : null] })));
  const racine = el('div', { class: 'kiosque__galerie' }, piste,
    el('div', { class: 'kiosque__galerie-barre' },
      el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Image précédente', dataset: { sens: '-1' } }, '‹'),
      points,
      el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Image suivante', dataset: { sens: '1' } }, '›')));
  const aller = (rang) => {
    const diapo = piste.querySelector('.kiosque__diapo[data-rang="' + rang + '"]');
    if (diapo) piste.scrollTo({ left: diapo.offsetLeft - piste.offsetLeft, behavior: mouvementReduit() ? 'auto' : 'smooth' });
  };
  const courant = () => Math.round(piste.scrollLeft / Math.max(1, piste.clientWidth));
  racine.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-sens]');
    if (!b) return;
    aller(Math.max(0, Math.min(images.length - 1, courant() + Number(b.dataset.sens))));
  });
  piste.addEventListener('scroll', () => {
    const c = courant();
    points.querySelectorAll('.kiosque__galerie-point').forEach((p, i) => p.classList.toggle('kiosque__galerie-point--actif', i === c));
  }, { passive: true });
  return racine;
}

function blocPastilles(pastilles) {
  return el('ul', { class: 'kiosque__pastilles', role: 'list', 'aria-label': 'Mots-clés' },
    pastilles.map((p) => el('li', { class: 'badge badge--accent' }, p)));
}

function blocEncadre(bloc) {
  return el('div', { class: ['kiosque__encadre', 'kiosque__encadre--' + bloc.ton], role: bloc.ton === 'alerte' ? 'note' : null },
    bloc.titre ? el('p', { class: 'kiosque__encadre-titre' }, bloc.titre) : null,
    el('p', { class: 'kiosque__encadre-texte' }, bloc.texte));
}

/**
 * Rend un bloc. Un bloc de texte s'écrit à la machine ; les autres
 * s'affichent d'un coup.
 * @param {object} bloc
 * @returns {Node|null}
 */
export function rendreBloc(bloc) {
  const contenu = rendreContenuBloc(bloc);
  if (!contenu) return null;
  const largeur = LARGEURS_BLOC.includes(bloc.largeur) ? bloc.largeur : 'pleine';
  const cote = COTES_BLOC.includes(bloc.cote) ? bloc.cote : '';
  return el('div', {
    class: ['kiosque__bloc', 'kiosque__bloc--' + largeur, cote ? 'kiosque__bloc--' + cote : null],
    dataset: { type: bloc.type, largeur, cote }
  }, contenu);
}

function rendreContenuBloc(bloc) {
  switch (bloc.type) {
    case 'texte': return el('div', { class: 'kiosque__corps' }, bloc.lignes.map(ligneCorps));
    case 'image': return blocImage(bloc);
    case 'galerie': return blocGalerie(bloc.images);
    case 'chiffres': return blocChiffres(bloc.chiffres);
    case 'courbe': return blocSerie(bloc.serie);
    case 'pastilles': return blocPastilles(bloc.pastilles);
    case 'encadre': return blocEncadre(bloc);
    default: return null;
  }
}

/* -------------------------------------------------------------------------
   6. La lecture (à droite)
   ------------------------------------------------------------------------- */

function lecture(prefixe) {
  const image = el('figure', { class: 'kiosque__image', hidden: true });
  /* La bannière ne se charge pas toujours (une adresse distante, un réseau
     qui filtre l'extérieur) : plutôt qu'une icône cassée, la figure se
     masque et l'absence se lit en toutes lettres, alignée sur le texte. */
  const avisImage = el('p', { class: 'kiosque__ligne texte-doux', hidden: true },
    'Image introuvable à cette adresse.');
  const meta = el('p', { class: 'kiosque__lecture-meta' });
  const titre = el('h3', { class: 'kiosque__lecture-titre', id: prefixe + '-lecture-titre' }, '');
  const chapeau = el('p', { class: 'kiosque__chapeau', hidden: true });
  const blocs = el('div', { class: 'kiosque__blocs' });
  const curseur = el('span', { class: 'kiosque__curseur', 'aria-hidden': 'true', hidden: true });
  /* Pas de crédit sous la lecture : l'utilisateur ne veut pas de mention
     au pied de chaque communication. L'obligation de licence (CC BY,
     CC BY-SA) est tenue par la fenêtre « Crédits photos » du pied de page,
     présente sur le tableau de bord ET sur les trois espaces de pôle. */
  /* La marque de fin : un court filet terre cuite, centré, après le
     dernier bloc — le lecteur sait qu'il a tout lu. Pas de signature. */
  const fin = el('div', { class: 'kiosque__fin', 'aria-hidden': 'true', hidden: true });
  /* Sous la marque de fin : la communication plus récente et la plus
     ancienne, par leur titre — on lit la suite sans remonter à la liste
     (kiosque() branche les boutons). */
  const suite = el('nav', { class: 'kiosque__suite', 'aria-label': 'Autres communications', hidden: true });

  const racine = el('article', {
    class: 'kiosque__lecture',
    'aria-labelledby': titre.id,
    tabIndex: -1
  },
  image,
  el('div', { class: 'kiosque__lecture-interieur' }, avisImage, meta, titre, chapeau, blocs, curseur, fin, suite));

  return { racine, image, avisImage, meta, titre, chapeau, blocs, curseur, fin, suite };
}

/* Tout le texte d'un dossier, pour estimer le temps de lecture : titre,
   chapeau et les chaînes des blocs (sans les adresses d'image). */
function motsDe(valeur, sortie) {
  if (typeof valeur === 'string') { sortie.push(valeur); return sortie; }
  if (Array.isArray(valeur)) { valeur.forEach((v) => motsDe(v, sortie)); return sortie; }
  if (valeur && typeof valeur === 'object') {
    for (const [cle, v] of Object.entries(valeur)) if (!['type', 'src', 'alt', 'id', 'couleur', 'tendance'].includes(cle)) motsDe(v, sortie);
  }
  return sortie;
}

/* « 2 min de lecture » : 200 mots par minute, une minute au moins. */
export function dureeLecture(dossier) {
  const texteComplet = motsDe([dossier.titre, dossier.resume, dossier.blocs], []).join(' ');
  const mots = texteComplet.split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(mots / 200)) + ' min de lecture';
}

/* La photo d'un dossier, s'il en a une : sa vignette dans la liste. */
function premiereImage(dossier) {
  const bloc = (Array.isArray(dossier.blocs) ? dossier.blocs : []).find((b) => b && b.type === 'image' && texte(b.src));
  return bloc ? texte(bloc.src) : '';
}

/* Remplit une lecture avec un dossier. La première image ouvre la lecture
   en bannière, sans légende dessus ; les autres blocs suivent dans l'ordre. */
function remplirLecture(lect, dossier) {
  const blocs = dossier.blocs.slice();
  const premiere = blocs.findIndex((b) => b.type === 'image');
  const hero = premiere === 0 ? blocs.shift() : null;

  lect.avisImage.hidden = true;
  if (hero) {
    /* lect.image est créée une seule fois et resservie à chaque sélection :
       on remplace son CONTENU, jamais la figure — sinon une seule photo
       cassée priverait d'en-tête toutes les lectures suivantes. Le test du
       parent écarte l'échec d'une image déjà remplacée par une autre. */
    const photo = el('img', { src: hero.src, alt: hero.alt, loading: 'lazy', decoding: 'async',
      onError: () => {
        if (photo.parentNode !== lect.image) return;
        lect.image.hidden = true;
        lect.avisImage.hidden = false;
      } });
    monter(lect.image, photo);
    lect.image.hidden = false;
  } else {
    monter(lect.image);
    lect.image.hidden = true;
  }

  /* Au-dessus du titre, la date et rien d'autre : le pôle, le porteur, la
     catégorie et la mention d'exemple chargeaient la lecture sans rien
     apprendre au lecteur (le pied de page dit que les données sont fictives). */
  monter(lect.meta,
    el('time', { class: 'mono', datetime: dossier.date || null }, dateLongue(dossier.date) || 'Date à renseigner'),
    el('span', { class: 'kiosque__duree' }, dureeLecture(dossier)));
  lect.titre.textContent = dossier.titre || 'Sans titre';
  lect.chapeau.textContent = dossier.resume || '';
  lect.chapeau.hidden = !dossier.resume;
  monter(lect.blocs, blocs.length
    ? blocs.map(rendreBloc)
    : el('p', { class: 'kiosque__ligne texte-doux' }, 'Aucun détail publié pour cette communication.'));
  lect.fin.hidden = false;
}

/**
 * Une lecture autonome, telle que le kiosque la rend, texte écrit d'un
 * coup : l'aperçu de l'éditeur.
 * @param {object} dossier  un dossier de dossiersDepuisCommunications()
 * @returns {HTMLElement}
 */
export function apercuLecture(dossier) {
  const lect = lecture('apercu');
  remplirLecture(lect, dossier);
  lect.racine.querySelectorAll('.kiosque__ligne-texte').forEach((s) => { s.textContent = s.dataset.texte || ''; });
  return lect.racine;
}

/* -------------------------------------------------------------------------
   7. Le kiosque complet
   ------------------------------------------------------------------------- */

/**
 * @param {object} options
 * @param {object[]} options.dossiers      voir dossiersDepuisCommunications()
 * @param {string[]} [options.alertes]
 * @param {string} [options.id]            préfixe d'identifiants (défaut 'kiosque')
 * @param {string} [options.titreFil]      intitulé de la liste (défaut « Communications »)
 * @param {Array<{cle:string, libelle:string}>} [options.filtres]  puces de pôle
 * @param {(dossier:object)=>void} [options.surSelection]
 * @param {(declencheur:HTMLElement)=>void} [options.surAjout]  ouvre l'éditeur ;
 *        absent, pas de bouton « Ajouter une communication »
 * @param {(dossier:object, declencheur:HTMLElement)=>void} [options.surModifier]
 * @param {(dossier:object)=>void} [options.surSupprimer]
 * @param {(declencheur:HTMLElement)=>void} [options.surAlertes]  modifie les alertes
 *        Les quatre commandes ne se voient qu'en mode édition (edition.js).
 * @returns {HTMLElement}
 */
export function kiosque(options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'kiosque';
  const tous = Array.isArray(opts.dossiers) ? opts.dossiers : [];
  const alertes = Array.isArray(opts.alertes) ? opts.alertes : [];
  const filtres = Array.isArray(opts.filtres) ? opts.filtres : [];

  let filtre = '';
  let courant = null;
  let arreterEcriture = () => {};

  const lect = lecture(prefixe);
  const zoneListe = el('div', { class: 'kiosque__defile', tabIndex: 0 });
  const compteur = el('span', { class: 'kiosque__compte mono' }, '');

  const puces = filtres.length
    ? el('ul', { class: 'facettes kiosque__filtres', 'aria-label': 'Filtrer les communications par pôle' },
        [{ cle: '', libelle: 'Tout' }].concat(filtres).map((f) => el('li', {},
          el('button', {
            type: 'button', class: 'facette facette--compacte',
            'aria-pressed': f.cle === '' ? 'true' : 'false',
            dataset: { filtre: f.cle }
          }, f.libelle))))
    : null;

  const boutonAjout = typeof opts.surAjout === 'function'
    ? el('button', { type: 'button', class: 'bouton bouton--principal bouton--compact kiosque__ajout edition-seulement',
        onClick: (evt) => opts.surAjout(evt.currentTarget) },
        el('span', { 'aria-hidden': 'true' }, '+ '), 'Ajouter une communication')
    : null;

  /* « Modifier » et « Supprimer » la communication lue, en haut de la
     lecture, en mode édition seulement. Elles visent toujours la lecture
     du moment. */
  const barreLecture = (typeof opts.surModifier === 'function' || typeof opts.surSupprimer === 'function')
    ? barreEdition({
        classe: 'kiosque__edition',
        quoi: 'cette communication',
        surModifier: typeof opts.surModifier === 'function' ? (b) => { if (courant) opts.surModifier(courant, b); } : null,
        surSupprimer: typeof opts.surSupprimer === 'function' ? () => { if (courant) opts.surSupprimer(courant); } : null
      })
    : null;
  if (barreLecture) {
    const interieur = lect.racine.querySelector('.kiosque__lecture-interieur');
    if (interieur) interieur.prepend(barreLecture);
  }

  const visibles = () => tous.filter((d) => !filtre || d.pole === filtre || d.groupe === 'mot');

  /* Fait défiler la liste — et seulement elle, jamais la page — pour que la
     carte soit visible, sous l'en-tête de mois collant. Renvoie vrai quand
     il n'y avait plus rien à faire défiler. */
  function montrerCarte(bouton) {
    if (!bouton) return true;
    const zone = zoneListe.getBoundingClientRect();
    const carte = bouton.getBoundingClientRect();
    const groupe = zoneListe.querySelector('.kiosque__groupe');
    const marge = (groupe ? groupe.getBoundingClientRect().height : 0) + 8;
    let decalage = 0;
    if (carte.top < zone.top + marge) decalage = carte.top - zone.top - marge;
    else if (carte.bottom > zone.bottom - 8) decalage = carte.bottom - zone.bottom + 8;
    if (!decalage) return true;
    zoneListe.scrollTo({ top: zoneListe.scrollTop + decalage, behavior: mouvementReduit() ? 'auto' : 'smooth' });
    return false;
  }

  /* La carte à faire défiler en vue dès que la liste a pris la hauteur de
     la nouvelle lecture (voir suivreHauteur) : mesurer avant serait mesurer
     une fenêtre qui va changer. */
  let carteAMontrer = null;
  const montrerEnAttente = () => {
    if (!carteAMontrer) return;
    /* La lecture peut encore grandir après le premier ajustement (image
       chargée, texte qui s'écrit) : on garde la carte en attente jusqu'à
       ce qu'elle soit vraiment dans la fenêtre, sinon un défilement
       mesuré trop tôt la laisse à quelques pixels du bord. */
    if (montrerCarte(carteAMontrer)) carteAMontrer = null;
  };

  function lire(dossier, options) {
    const o = options || {};
    courant = dossier;
    carteAMontrer = null;   // chaque sélection décide seule de ce qu'elle montre
    arreterEcriture();
    zoneListe.querySelectorAll('.kiosque__carte').forEach((b) => {
      const actif = b.dataset.id === dossier.id;
      b.setAttribute('aria-current', actif ? 'true' : 'false');
      const entree = b.closest('.kiosque__entree');
      if (entree) entree.classList.toggle('kiosque__entree--active', actif);
      if (actif && o.montrer) carteAMontrer = b;
    });
    remplirLecture(lect, dossier);
    poserSuite(dossier);
    if (barreLecture) barreLecture.hidden = false;
    /* La lecture défile dans son cadre : une nouvelle communication se lit
       depuis son début, pas depuis là où la précédente avait été laissée. */
    lect.racine.scrollTop = 0;
    /* Déjà dans la page : on ajuste tout de suite, puis on montre la carte.
       Pas encore montée (arrivée par un lien) : l'observateur le fera. */
    if (racine.isConnected) ajusterHauteur();
    lect.racine.classList.remove('kiosque__lecture--entre');
    void lect.racine.offsetWidth; // relance la transition d'entrée
    lect.racine.classList.add('kiosque__lecture--entre');
    arreterEcriture = machineAEcrire(lect.blocs, lect.curseur);
    if (typeof opts.surSelection === 'function') opts.surSelection(dossier);
  }

  /* « Plus récente » / « Plus ancienne » : les voisines dans la liste
     affichée (le filtre compris). */
  function poserSuite(dossier) {
    const liste = visibles();
    const i = liste.findIndex((d) => d.id === dossier.id);
    const bouton = (voisin, sens) => voisin
      ? el('button', {
          type: 'button', class: ['kiosque__suite-bouton', 'kiosque__suite-bouton--' + sens],
          onClick: () => { lire(voisin, { montrer: true }); annoncer(voisin.titre); lect.racine.scrollTop = 0; }
        },
        el('span', { class: 'kiosque__suite-sens' }, sens === 'avant' ? '← Plus récente' : 'Plus ancienne →'),
        el('span', { class: 'kiosque__suite-titre' }, voisin.titre || 'Sans titre'))
      : el('span', { class: 'kiosque__suite-vide' });
    const avant = i > 0 ? liste[i - 1] : null;
    const apres = i >= 0 && i < liste.length - 1 ? liste[i + 1] : null;
    monter(lect.suite, bouton(avant, 'avant'), bouton(apres, 'apres'));
    lect.suite.hidden = !avant && !apres;
  }

  function viderLecture() {
    courant = null;
    lect.suite.hidden = true;
    if (barreLecture) barreLecture.hidden = true;
    monter(lect.image); lect.image.hidden = true;
    lect.avisImage.hidden = true;
    monter(lect.meta);
    lect.titre.textContent = 'Aucune communication';
    lect.chapeau.hidden = true;
    monter(lect.blocs, el('p', { class: 'texte-doux sans-marge' }, 'Rien à lire pour ce pôle pour le moment.'));
    lect.fin.hidden = true;
  }

  function rendreListe(cibleDemandee) {
    const dossiers = visibles();
    compteur.textContent = dossiers.length ? String(dossiers.length) : '';
    monter(zoneListe, dossiers.length
      ? liste(dossiers, prefixe)
      : el('p', { class: 'kiosque__vide texte-doux' }, 'Rien à lire pour ce pôle pour le moment.'));
    const cible = (cibleDemandee && dossiers.find((d) => d.id === cibleDemandee))
      || dossiers.find((d) => courant && d.id === courant.id) || dossiers[0];
    if (cible) lire(cible, { montrer: !!cibleDemandee }); else viderLecture();
  }

  /* Sur une colonne, la lecture est SOUS la liste : toucher une carte
     changeait le contenu sans que rien n'arrive à l'écran. On amène donc la
     lecture sous la barre du site, dont on MESURE la hauteur réelle — le
     jeton --hauteur-barre-site vaut 57 px là où la barre en mesure 97. */
  const uneColonne = () => typeof window.matchMedia === 'function'
    && window.matchMedia(REQUETE_UNE_COLONNE).matches;
  let auClavier = false;

  function amenerLecture() {
    const barre = document.querySelector('.site-entete');
    const marge = (barre ? barre.getBoundingClientRect().height : 0) + 8;
    const cible = lect.racine.getBoundingClientRect().top + window.scrollY - marge;
    window.scrollTo({ top: Math.max(0, cible), behavior: mouvementReduit() ? 'auto' : 'smooth' });
  }

  zoneListe.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('.kiosque__carte');
    if (!bouton) return;
    const dossier = tous.find((d) => d.id === bouton.dataset.id);
    if (dossier) {
      lire(dossier, { montrer: true });
      annoncer(dossier.titre);
      /* Au clavier, non : chaque flèche arracherait la liste de l'écran et
         rendrait le parcours impraticable. */
      if (!auClavier && uneColonne()) amenerLecture();
    }
  });

  zoneListe.addEventListener('keydown', (evt) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(evt.key)) return;
    const boutons = Array.from(zoneListe.querySelectorAll('.kiosque__carte'));
    if (!boutons.length) return;
    const position = boutons.findIndex((b) => b === document.activeElement);
    let suivant = position;
    if (evt.key === 'ArrowDown') suivant = Math.min(boutons.length - 1, position + 1);
    if (evt.key === 'ArrowUp') suivant = Math.max(0, position - 1);
    if (evt.key === 'Home') suivant = 0;
    if (evt.key === 'End') suivant = boutons.length - 1;
    evt.preventDefault();
    /* Le focus ne fait pas sauter la page : c'est lire() qui fait défiler
       la liste, et elle seule, jusqu'à la carte. */
    boutons[suivant].focus({ preventScroll: true });
    auClavier = true;
    boutons[suivant].click();
    auClavier = false;
  });

  if (puces) {
    puces.addEventListener('click', (evt) => {
      const bouton = evt.target.closest('[data-filtre]');
      if (!bouton) return;
      filtre = bouton.dataset.filtre || '';
      puces.querySelectorAll('[data-filtre]').forEach((b) => {
        b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false');
      });
      rendreListe();
    });
  }

  /* Un clic dans la lecture termine l'écriture : on veut lire, pas attendre. */
  lect.racine.addEventListener('click', () => arreterEcriture());

  const flux = el('aside', { class: 'kiosque__flux', 'aria-label': texte(opts.titreFil) || 'Communications' },
    el('div', { class: 'kiosque__flux-tete' },
      el('h3', { class: 'kiosque__flux-titre' }, texte(opts.titreFil) || 'Communications', ' ', compteur),
      puces,
      boutonAjout),
    zoneListe);

  const racine = el('section', { class: 'kiosque', id: prefixe },
    bandeauAlertes(alertes, opts.surAlertes),
    el('div', { class: 'kiosque__grille' }, flux, lect.racine));

  const ajusterHauteur = suivreHauteur(flux, lect.racine, montrerEnAttente);

  /* Arrivée par un lien : #communication=ID lit cette entrée. */
  const demandee = texte(etatUrl.lire().communication);
  rendreListe(demandee || null);
  /* …et un lien suivi alors qu'on est DÉJÀ sur la page, ou le bouton
     Précédent : sans cette écoute, ni l'un ni l'autre n'avait d'effet. */
  etatUrl.ecouter((e) => {
    const id = texte(e.communication);
    if (id) rendreListe(id);
  });
  return racine;
}

/* -------------------------------------------------------------------------
   8. La même hauteur pour la liste et la lecture
   ------------------------------------------------------------------------- */

/* Sous cette largeur, la grille passe sur une colonne (voir modules.css §2) :
   la liste a alors une hauteur bornée fixe et l'observateur ne fait rien. */
const REQUETE_UNE_COLONNE = '(max-width: 900px)';

/**
 * La lecture donne sa hauteur ; la liste la recopie et défile à l'intérieur.
 * Déterministe et sans pourcentage : la hauteur mesurée de la lecture est
 * posée en style en ligne sur la liste, à chaque changement — nouvelle
 * entrée, image chargée, texte qui s'écrit, fenêtre redimensionnée. La
 * liste ne peut donc ni dépasser la lecture ni la laisser seule. Sans
 * ResizeObserver (très vieux navigateur), on mesure une fois puis à
 * chaque redimensionnement.
 * @param {HTMLElement} flux     la liste (.kiosque__flux)
 * @param {HTMLElement} lecture  la lecture (.kiosque__lecture)
 * @param {() => void} [apres]   appelé après chaque ajustement
 * @returns {() => void} la fonction d'ajustement, pour l'appeler soi-même
 */
function suivreHauteur(flux, lecture, apres) {
  if (!flux || !lecture || typeof window === 'undefined') return () => {};
  const uneColonne = typeof window.matchMedia === 'function' ? window.matchMedia(REQUETE_UNE_COLONNE) : null;

  const ajuster = () => {
    if (uneColonne && uneColonne.matches) {
      flux.style.removeProperty('block-size');
      flux.style.removeProperty('max-block-size');
    } else {
      const hauteur = Math.round(lecture.getBoundingClientRect().height);
      if (hauteur > 0) {
        flux.style.setProperty('block-size', hauteur + 'px');
        flux.style.setProperty('max-block-size', hauteur + 'px');
      }
    }
    if (typeof apres === 'function') apres();
  };

  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(ajuster).observe(lecture);
  } else {
    window.addEventListener('resize', ajuster, { passive: true });
    setTimeout(ajuster, 0);
  }
  if (uneColonne) {
    if (typeof uneColonne.addEventListener === 'function') uneColonne.addEventListener('change', ajuster);
    else if (typeof uneColonne.addListener === 'function') uneColonne.addListener(ajuster);
  }
  return ajuster;
}
