/* =========================================================================
   ETII Hub — Le kiosque de communication
   Le « Communication Center » du service : un bandeau d'alertes qui
   défile, le mot du chef en vedette (écrit ligne à ligne, à la machine à
   écrire), puis l'historique en cartes — date, pôle, titre, chapeau. Une
   carte s'ouvre en fenêtre pour lire le texte complet. On ne montre que
   ce qui a été dit : l'agenda à venir n'est pas de la communication.

   Rien n'est inventé : chaque entrée vient de communications.json (le mot
   du chef, l'agenda, les annonces). Tout le DOM est construit avec el() —
   aucun innerHTML, aucun gestionnaire en attribut.
   ========================================================================= */

import { el, frag, monter, mouvementReduit, annoncer, ouvrirModale } from './ui.js';

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
  'a-venir': { libelle: 'À venir', classe: 'badge--accent' },
  mot:    { libelle: 'Le mot du chef', classe: 'badge--accent' }
};

/* Glyphe posé devant chaque ligne du corps, selon son type. C'est le
   vocabulaire du formulaire d'origine : « ! » alerte, « V » validé,
   « -> » titre, « • » puce. */
const GLYPHES = {
  titre: '→', puce: '•', valide: '✓', alerte: '⚠', texte: '', vide: ''
};

/* -------------------------------------------------------------------------
   1. Lecture prudente
   ------------------------------------------------------------------------- */

function texte(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return String(valeur).trim();
}

function partiesDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  if (!m) return null;
  const annee = Number(m[1]); const mois = Number(m[2]); const jour = Number(m[3]);
  if (mois < 1 || mois > 12 || jour < 1 || jour > 31) return null;
  return { annee, mois, jour };
}

/** « 12 SEPT. 2026 » — la date courte du fil, en capitales mono. */
export function dateCourte(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_COURTS[p.mois - 1]} ${p.annee}`;
}

/** « jeudi 12 septembre 2026 » — la date longue du projecteur. */
export function dateLongue(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_LONGS[p.mois - 1]} ${p.annee}`;
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

/**
 * Construit la liste des dossiers du kiosque à partir de communications.json.
 *
 * - le mot du chef, en vedette (seulement au niveau service) ;
 * - l'historique : annonces et agenda passé, du plus récent au plus ancien.
 *   L'agenda à venir est ignoré : on communique sur ce qui s'est passé.
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

  const mot = (d.motDuChef && typeof d.motDuChef === 'object') ? d.motDuChef : null;
  if (mot && niveauService && texte(mot.titre)) {
    dossiers.push({
      id: 'mot-du-chef',
      groupe: 'mot',
      date: texte(mot.date),
      titre: texte(mot.titre),
      resume: '',
      programme: 'Service ETII',
      statut: 'mot',
      pole: 'ETII',
      lignes: lignesDepuis(mot.corps),
      auteur: texte(mot.auteur),
      fonction: texte(mot.fonction)
    });
  }

  const agenda = Array.isArray(d.agenda) ? d.agenda.filter((e) => e && typeof e === 'object') : [];
  const annonces = Array.isArray(d.annonces) ? d.annonces.filter((e) => e && typeof e === 'object') : [];

  const historique = [
    ...annonces.filter(garder).map((e) => ({
      id: 'annonce-' + texte(e.id),
      groupe: 'historique',
      date: texte(e.date),
      titre: texte(e.titre),
      resume: texte(e.resume),
      programme: texte(e.categorie) || 'Général',
      statut: STATUTS[texte(e.statut)] ? texte(e.statut) : 'info',
      pole: texte(e.pole).toUpperCase(),
      lede: texte(e.resume),
      lignes: lignesDepuis(e.corps)
    })),
    ...agenda
      .filter((e) => texte(e.statut) !== 'a-venir' && texte(e.type) !== 'mot' && garder(e))
      .map((e) => ({
        id: 'agenda-' + texte(e.id),
        groupe: 'historique',
        date: texte(e.date),
        titre: texte(e.titre),
        resume: texte(e.resume),
        programme: TYPES_AGENDA[texte(e.type)] || texte(e.type) || 'Agenda',
        statut: STATUTS[texte(e.type)] ? texte(e.type) : 'info',
        pole: texte(e.pole).toUpperCase(),
        lede: e.corps ? texte(e.resume) : '',
        lignes: lignesDepuis(e.corps || e.resume)
      }))
  ].sort((a, b) => b.date.localeCompare(a.date));

  /* Un même événement peut être saisi deux fois — comme annonce détaillée
     et comme entrée d'agenda. Même titre à la même date : on garde la
     première venue, l'annonce, qui porte le texte complet. */
  const vus = new Set();
  const uniques = historique.filter((d) => {
    const cle = d.date + '|' + d.titre.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
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
   4. Le corps d'une entrée et la machine à écrire
   ------------------------------------------------------------------------- */

function pastillePole(code) {
  if (!code || code === 'ETII') return null;
  return el('span', { class: 'kiosque__pole', dataset: { pole: code } },
    el('span', { class: 'kiosque__pole-point', 'aria-hidden': 'true' }),
    code);
}

function ligneCorps(ligne, differe) {
  if (ligne.type === 'vide') return el('div', { class: 'kiosque__ligne kiosque__ligne--vide' });
  const glyphe = GLYPHES[ligne.type] || '';
  return el('p', { class: ['kiosque__ligne', 'kiosque__ligne--' + ligne.type] },
    glyphe ? el('span', { class: 'kiosque__glyphe', 'aria-hidden': 'true' }, glyphe) : null,
    el('span', { class: 'kiosque__ligne-texte', dataset: { texte: ligne.texte } }, differe ? '' : ligne.texte));
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
      minuteur = setTimeout(pas, 22);
    } else {
      i += 1; c = 0;
      minuteur = setTimeout(pas, 90);
    }
  };
  pas();
  return terminer;
}

/* -------------------------------------------------------------------------
   5. La vedette : le mot du chef, sur fond marine
   ------------------------------------------------------------------------- */

function vedette(dossier) {
  const corps = el('div', { class: 'kiosque__vedette-corps' },
    dossier.lignes.length ? dossier.lignes.map((l) => ligneCorps(l, true))
      : el('p', { class: 'kiosque__ligne' }, 'Aucun texte publié.'));
  const curseur = el('span', { class: 'kiosque__curseur', 'aria-hidden': 'true', hidden: true });
  const racine = el('article', { class: 'kiosque__vedette', 'aria-label': 'Le mot du chef' },
    el('p', { class: 'kiosque__vedette-sur-titre' },
      el('span', {}, 'Le mot du chef'),
      dossier.date ? el('time', { datetime: dossier.date }, dateLongue(dossier.date)) : null),
    el('h3', { class: 'kiosque__vedette-titre' }, dossier.titre || 'Sans titre'),
    el('div', { class: 'kiosque__vedette-texte' }, corps, curseur),
    dossier.auteur
      ? el('p', { class: 'kiosque__vedette-signature' },
          el('strong', {}, dossier.auteur),
          dossier.fonction ? el('span', {}, ' — ' + dossier.fonction) : null)
      : null);
  let terminer = () => {};
  /* L'écriture démarre quand la vedette entre à l'écran, pas au chargement. */
  const demarrer = () => { terminer = machineAEcrire(corps, curseur); };
  if (typeof IntersectionObserver === 'function') {
    const obs = new IntersectionObserver((entrees) => {
      if (entrees.some((e) => e.isIntersecting)) { obs.disconnect(); demarrer(); }
    }, { threshold: 0.2 });
    obs.observe(racine);
  } else {
    demarrer();
  }
  racine.addEventListener('click', () => terminer());
  return racine;
}

/* -------------------------------------------------------------------------
   6. Les cartes de l'historique et leur fenêtre de lecture
   ------------------------------------------------------------------------- */

function carte(dossier, prefixe) {
  const statut = STATUTS[dossier.statut] || STATUTS.info;
  const lede = dossier.lede !== undefined && dossier.lede !== '' ? dossier.lede : dossier.resume;
  return el('li', { class: 'kiosque__item', dataset: { pole: dossier.pole || 'ETII' } },
    el('button', {
      type: 'button',
      class: 'kiosque__carte',
      id: prefixe + '-entree-' + dossier.id,
      dataset: { id: dossier.id },
      'aria-haspopup': 'dialog'
    },
    el('span', { class: 'kiosque__carte-meta' },
      el('time', { class: 'kiosque__date', datetime: dossier.date || null },
        dateCourte(dossier.date) || 'Date à renseigner'),
      pastillePole(dossier.pole),
      el('span', { class: ['badge', statut.classe, 'kiosque__carte-statut'] }, statut.libelle)),
    el('span', { class: 'kiosque__carte-titre' }, dossier.titre || 'Sans titre'),
    lede ? el('span', { class: 'kiosque__carte-resume' }, lede) : null,
    el('span', { class: 'kiosque__carte-lire', 'aria-hidden': 'true' },
      el('span', {}, dossier.programme || 'Général'), el('span', {}, 'Lire →'))));
}

function ouvrirLecture(dossier, declencheur) {
  const statut = STATUTS[dossier.statut] || STATUTS.info;
  const lede = dossier.lede !== undefined && dossier.lede !== '' ? dossier.lede : dossier.resume;
  ouvrirModale({
    titre: dossier.titre || 'Sans titre',
    classe: 'modale--large modale--lecture',
    declencheur: declencheur || null,
    contenu: () => frag(
      el('p', { class: 'kiosque__lecture-meta' },
        el('time', { class: 'mono', datetime: dossier.date || null }, dateLongue(dossier.date) || 'Date à renseigner'),
        el('span', { class: 'badge badge--accent' }, dossier.programme || 'Général'),
        el('span', { class: ['badge', statut.classe] }, statut.libelle),
        pastillePole(dossier.pole)),
      lede ? el('p', { class: 'kiosque__lecture-lede' }, lede) : null,
      el('div', { class: 'kiosque__lecture-corps' },
        dossier.lignes.length ? dossier.lignes.map((l) => ligneCorps(l, false))
          : el('p', { class: 'texte-doux sans-marge' }, 'Aucun détail publié pour cette entrée.')),
      dossier.auteur
        ? el('p', { class: 'kiosque__lecture-signature' }, el('strong', {}, dossier.auteur),
            dossier.fonction ? el('span', { class: 'texte-doux' }, ' — ' + dossier.fonction) : null)
        : null),
    actions: [{ libelle: 'Fermer', variante: 'principal', ferme: true }]
  });
}

/* -------------------------------------------------------------------------
   7. Le kiosque complet
   ------------------------------------------------------------------------- */

/**
 * @param {object} options
 * @param {object[]} options.dossiers      voir dossiersDepuisCommunications()
 * @param {string[]} [options.alertes]
 * @param {string} [options.id]            préfixe d'identifiants (défaut 'kiosque')
 * @param {string} [options.titreFil]      intitulé de l'historique (défaut « Historique »)
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
  const mot = tous.find((d) => d.groupe === 'mot') || null;
  const historique = tous.filter((d) => d.groupe !== 'mot');

  let filtre = '';

  const compteur = el('span', { class: 'kiosque__compte mono' }, '');
  const grille = el('ul', { class: 'kiosque__grille', role: 'list' });

  const puces = filtres.length
    ? el('ul', { class: 'facettes kiosque__filtres', 'aria-label': 'Filtrer l’historique par pôle' },
        [{ cle: '', libelle: 'Tout' }].concat(filtres).map((f) => el('li', {},
          el('button', {
            type: 'button', class: 'facette facette--compacte',
            'aria-pressed': f.cle === '' ? 'true' : 'false',
            dataset: { filtre: f.cle }
          }, f.libelle))))
    : null;

  const visibles = () => historique.filter((d) => !filtre || d.pole === filtre);

  function rendre() {
    const liste = visibles();
    compteur.textContent = String(liste.length);
    monter(grille, liste.length
      ? liste.map((d) => carte(d, prefixe))
      : el('li', { class: 'kiosque__vide texte-doux' }, 'Rien à lire pour ce pôle pour le moment.'));
  }

  grille.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('.kiosque__carte');
    if (!bouton) return;
    const dossier = historique.find((d) => d.id === bouton.dataset.id);
    if (!dossier) return;
    ouvrirLecture(dossier, bouton);
    annoncer(dossier.titre);
    if (typeof opts.surSelection === 'function') opts.surSelection(dossier);
  });

  if (puces) {
    puces.addEventListener('click', (evt) => {
      const bouton = evt.target.closest('[data-filtre]');
      if (!bouton) return;
      filtre = bouton.dataset.filtre || '';
      puces.querySelectorAll('[data-filtre]').forEach((b) => {
        b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false');
      });
      rendre();
    });
  }

  const racine = el('section', { class: 'kiosque', id: prefixe },
    bandeauAlertes(alertes),
    mot ? vedette(mot) : null,
    el('div', { class: 'kiosque__barre' },
      el('h3', { class: 'kiosque__titre-fil' }, texte(opts.titreFil) || 'Historique', ' ', compteur),
      puces),
    grille);

  rendre();
  return racine;
}
