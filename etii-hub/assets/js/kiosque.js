/* =========================================================================
   ETII Hub — Le kiosque de communication
   Le « Communication Center » du service : un bandeau d'alertes qui
   défile, puis deux panneaux côte à côte — à gauche la liste de tout ce
   qui a été communiqué (la plus récente d'abord, par mois), à droite la
   lecture de la communication choisie : son image si elle en a une, sa
   date, son titre, son résumé, ses chiffres clés, sa courbe, puis le corps
   écrit ligne à ligne. On ne montre que ce qui a été dit : l'agenda à
   venir n'est pas de la communication.

   Rien n'est inventé : chaque entrée vient du fichier ou de la feuille de
   communications (le mot du chef, les annonces, les alertes). Tout le DOM
   est construit avec el() — aucun innerHTML, aucun gestionnaire en
   attribut.
   ========================================================================= */

import { el, monter, mouvementReduit, annoncer, etatUrl } from './ui.js';
import { sparkline } from './indicateurs.js';

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                     'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

/* Libellé humain des types d'entrée d'agenda : de la matière éditoriale,
   pas de la donnée. Un type inconnu est affiché tel quel. */
const TYPES_AGENDA = {
  jalon: 'Jalon', atelier: 'Atelier', reunion: 'Réunion', mot: 'Mot du chef',
  succes: 'Succès', alerte: 'Alerte', info: 'Information'
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

/** L'image d'une communication : { src, alt, legende } ou null. */
function imageDepuis(brut) {
  const o = objet(brut);
  if (!o) return null;
  const src = texte(o.src);
  if (!/^(https:\/\/|assets\/)/.test(src)) return null;
  return { src, alt: texte(o.alt), legende: texte(o.legende) };
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

function dossierDepuis(e, base) {
  return Object.assign({
    date: texte(e.date),
    titre: texte(e.titre),
    resume: texte(e.resume),
    pole: texte(e.pole).toUpperCase() || 'ETII',
    lignes: lignesDepuis(e.corps),
    image: imageDepuis(e.image),
    chiffres: chiffresDepuis(e.chiffres),
    serie: serieDepuis(e.serie)
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
 * @param {{pole?: string}} [options]  code de pôle ; absent ou 'ETII' : tout le service
 * @returns {Array<object>}
 */
export function dossiersDepuisCommunications(donnees, options) {
  const opts = options || {};
  const pole = texte(opts.pole).toUpperCase();
  const niveauService = !pole || pole === 'ETII';
  const garder = (entree) => niveauService || texte(entree.pole).toUpperCase() === pole;

  const dossiers = [];
  const d = (donnees && typeof donnees === 'object') ? donnees : {};

  const mot = objet(d.motDuChef);
  if (mot && niveauService && texte(mot.titre)) {
    dossiers.push(dossierDepuis(mot, {
      id: 'mot-du-chef', groupe: 'mot', programme: 'Service ETII', statut: 'mot', pole: 'ETII'
    }));
  }

  const agenda = Array.isArray(d.agenda) ? d.agenda.filter((e) => e && typeof e === 'object') : [];
  const annonces = Array.isArray(d.annonces) ? d.annonces.filter((e) => e && typeof e === 'object') : [];

  const historique = [
    ...annonces.filter(garder).map((e) => dossierDepuis(e, {
      id: 'annonce-' + texte(e.id),
      groupe: 'historique',
      programme: texte(e.categorie) || 'Général',
      statut: STATUTS[texte(e.statut)] ? texte(e.statut) : 'info'
    })),
    ...agenda
      .filter((e) => texte(e.statut) !== 'a-venir' && texte(e.type) !== 'mot' && garder(e))
      .map((e) => dossierDepuis(e, {
        id: 'agenda-' + texte(e.id),
        groupe: 'historique',
        programme: TYPES_AGENDA[texte(e.type)] || texte(e.type) || 'Agenda',
        statut: STATUTS[texte(e.type)] ? texte(e.type) : 'info',
        lignes: lignesDepuis(e.corps || e.resume)
      }))
  ].sort((a, b) => b.date.localeCompare(a.date));

  const vus = new Set();
  const uniques = historique.filter((x) => {
    const cle = x.date + '|' + x.titre.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    if (vus.has(cle)) return false;
    vus.add(cle);
    return true;
  });

  return dossiers.concat(uniques);
}

/** Les alertes en cours, sous forme de chaînes. */
export function alertesDepuisCommunications(donnees) {
  const d = (donnees && typeof donnees === 'object') ? donnees : {};
  return (Array.isArray(d.alertes) ? d.alertes : []).map(texte).filter(Boolean);
}

/* -------------------------------------------------------------------------
   3. Le bandeau d'alertes
   ------------------------------------------------------------------------- */

function bandeauAlertes(alertes) {
  if (!alertes.length) return null;
  const liste = (copie) => el('ul', {
    class: ['kiosque__alertes-liste', copie ? 'kiosque__alertes-liste--copie' : null],
    'aria-hidden': copie ? 'true' : null
  }, alertes.map((a) => el('li', { class: 'kiosque__alerte' }, a)));

  return el('div', { class: 'kiosque__alertes', role: 'region', 'aria-label': 'Alertes en cours' },
    el('span', { class: 'kiosque__alertes-etiquette' },
      el('span', { class: 'kiosque__alertes-point', 'aria-hidden': 'true' }),
      alertes.length > 1 ? 'Alertes' : 'Alerte'),
    el('div', { class: 'kiosque__alertes-fenetre' },
      el('div', { class: 'kiosque__alertes-piste' }, liste(false), liste(true))));
}

/* -------------------------------------------------------------------------
   4. La liste (à gauche) : par mois, la plus récente d'abord
   ------------------------------------------------------------------------- */

function pastillePole(code) {
  if (!code || code === 'ETII') return null;
  return el('span', { class: 'kiosque__pole', dataset: { pole: code } },
    el('span', { class: 'kiosque__pole-point', 'aria-hidden': 'true' }),
    code);
}

function carteListe(dossier, prefixe) {
  const p = partiesDate(dossier.date);
  return el('li', { class: 'kiosque__entree', dataset: { pole: dossier.pole || 'ETII' } },
    el('button', {
      type: 'button',
      class: 'kiosque__carte',
      id: prefixe + '-entree-' + dossier.id,
      dataset: { id: dossier.id },
      'aria-current': 'false'
    },
    el('span', { class: 'kiosque__quand', 'aria-hidden': 'true' },
      el('span', { class: 'kiosque__jour' }, p ? String(p.jour) : '—'),
      el('span', { class: 'kiosque__mois' }, p ? MOIS_COURTS[p.mois - 1] : '')),
    el('span', { class: 'kiosque__carte-corps' },
      el('span', { class: 'kiosque__carte-titre' }, dossier.titre || 'Sans titre'),
      dossier.resume ? el('span', { class: 'kiosque__carte-resume' }, dossier.resume) : null,
      el('span', { class: 'kiosque__carte-meta' },
        el('time', { class: 'visuellement-cache', datetime: dossier.date || null }, dateLongue(dossier.date)),
        pastillePole(dossier.pole),
        el('span', {}, dossier.programme || 'Général'),
        dossier.image ? el('span', { class: 'kiosque__carte-glyphe', title: 'Avec image', 'aria-hidden': 'true' }, '▣') : null,
        dossier.chiffres.length || dossier.serie ? el('span', { class: 'kiosque__carte-glyphe', title: 'Avec chiffres', 'aria-hidden': 'true' }, '▮') : null))));
}

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
   5. La lecture (à droite) et la machine à écrire
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
  if (!chiffres.length) return null;
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

/* La petite série : la courbe validée d'indicateurs.js, avec son libellé,
   sa première et sa dernière valeur — assez pour lire une tendance. */
function blocSerie(serie) {
  if (!serie) return null;
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

function lecture(prefixe) {
  const image = el('figure', { class: 'kiosque__image', hidden: true });
  const meta = el('p', { class: 'kiosque__lecture-meta' });
  const titre = el('h3', { class: 'kiosque__lecture-titre', id: prefixe + '-lecture-titre' }, '');
  const chapeau = el('p', { class: 'kiosque__chapeau', hidden: true });
  const extras = el('div', { class: 'kiosque__extras' });
  const corps = el('div', { class: 'kiosque__corps' });
  const curseur = el('span', { class: 'kiosque__curseur', 'aria-hidden': 'true', hidden: true });

  const racine = el('article', {
    class: 'kiosque__lecture',
    'aria-labelledby': titre.id,
    tabIndex: -1
  },
  image,
  el('div', { class: 'kiosque__lecture-interieur' },
    meta, titre, chapeau, extras,
    el('div', { class: 'kiosque__lecture-corps' }, corps, curseur)));

  return { racine, image, meta, titre, chapeau, extras, corps, curseur };
}

/* -------------------------------------------------------------------------
   6. Le kiosque complet
   ------------------------------------------------------------------------- */

/**
 * @param {object} options
 * @param {object[]} options.dossiers      voir dossiersDepuisCommunications()
 * @param {string[]} [options.alertes]
 * @param {string} [options.id]            préfixe d'identifiants (défaut 'kiosque')
 * @param {string} [options.titreFil]      intitulé de la liste (défaut « Communications »)
 * @param {Array<{cle:string, libelle:string}>} [options.filtres]  puces de pôle
 * @param {(dossier:object)=>void} [options.surSelection]
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

  const visibles = () => tous.filter((d) => !filtre || d.pole === filtre || d.groupe === 'mot');

  function lire(dossier) {
    courant = dossier;
    arreterEcriture();
    zoneListe.querySelectorAll('.kiosque__carte').forEach((b) => {
      b.setAttribute('aria-current', b.dataset.id === dossier.id ? 'true' : 'false');
    });
    const statut = STATUTS[dossier.statut] || STATUTS.info;

    if (dossier.image) {
      monter(lect.image,
        el('img', { src: dossier.image.src, alt: dossier.image.alt, loading: 'lazy', decoding: 'async' }),
        dossier.image.legende ? el('figcaption', {}, dossier.image.legende) : null);
      lect.image.hidden = false;
    } else {
      monter(lect.image);
      lect.image.hidden = true;
    }

    monter(lect.meta,
      el('time', { class: 'mono', datetime: dossier.date || null }, dateLongue(dossier.date) || 'Date à renseigner'),
      el('span', { class: 'badge badge--accent' }, dossier.programme || 'Général'),
      dossier.groupe === 'mot' ? null : el('span', { class: ['badge', statut.classe] }, statut.libelle),
      pastillePole(dossier.pole));
    lect.titre.textContent = dossier.titre || 'Sans titre';
    lect.chapeau.textContent = dossier.resume || '';
    lect.chapeau.hidden = !dossier.resume;
    monter(lect.extras, blocChiffres(dossier.chiffres), blocSerie(dossier.serie));
    lect.extras.hidden = !lect.extras.childNodes.length;
    monter(lect.corps, dossier.lignes.length
      ? dossier.lignes.map(ligneCorps)
      : el('p', { class: 'kiosque__ligne texte-doux' }, 'Aucun détail publié pour cette communication.'));

    lect.racine.classList.remove('kiosque__lecture--entre');
    void lect.racine.offsetWidth; // relance la transition d'entrée
    lect.racine.classList.add('kiosque__lecture--entre');
    arreterEcriture = machineAEcrire(lect.corps, lect.curseur);
    if (typeof opts.surSelection === 'function') opts.surSelection(dossier);
  }

  function viderLecture() {
    courant = null;
    monter(lect.image); lect.image.hidden = true;
    monter(lect.meta);
    lect.titre.textContent = 'Aucune communication';
    lect.chapeau.hidden = true;
    monter(lect.extras); lect.extras.hidden = true;
    monter(lect.corps, el('p', { class: 'texte-doux sans-marge' }, 'Rien à lire pour ce pôle pour le moment.'));
  }

  function rendreListe(cibleDemandee) {
    const dossiers = visibles();
    compteur.textContent = dossiers.length ? String(dossiers.length) : '';
    monter(zoneListe, dossiers.length
      ? liste(dossiers, prefixe)
      : el('p', { class: 'kiosque__vide texte-doux' }, 'Rien à lire pour ce pôle pour le moment.'));
    const cible = (cibleDemandee && dossiers.find((d) => d.id === cibleDemandee))
      || dossiers.find((d) => courant && d.id === courant.id) || dossiers[0];
    if (cible) lire(cible); else viderLecture();
  }

  zoneListe.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('.kiosque__carte');
    if (!bouton) return;
    const dossier = tous.find((d) => d.id === bouton.dataset.id);
    if (dossier) { lire(dossier); annoncer(dossier.titre); }
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
    boutons[suivant].focus();
    boutons[suivant].click();
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

  const racine = el('section', { class: 'kiosque', id: prefixe },
    bandeauAlertes(alertes),
    el('div', { class: 'kiosque__grille' },
      el('aside', { class: 'kiosque__flux', 'aria-label': texte(opts.titreFil) || 'Communications' },
        el('div', { class: 'kiosque__flux-tete' },
          el('h3', { class: 'kiosque__flux-titre' }, texte(opts.titreFil) || 'Communications', ' ', compteur),
          puces),
        zoneListe),
      lect.racine));

  /* Arrivée par un lien : #communication=ID lit cette entrée. */
  const demandee = texte(etatUrl.lire().communication);
  rendreListe(demandee || null);
  return racine;
}
